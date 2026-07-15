"""Tests for backend.taper_fingerprints: Layer-2 vocabulary fingerprints —
tokenization, profile gating, DF/alias stopword filtering, the three write
gates (score, margin, reliability), poisoned-component exclusion,
never-overwrite, and integration with backend.taper_attribution.recompute().

Layer 2's real gates (INFERRED_SCORE_THRESHOLD=150.0,
INFERRED_MARGIN_THRESHOLD=80.0, and the cross-validated reliability set) are
calibrated against live-scale data and are too data-hungry to clear on a tiny
synthetic fixture, so every direct infer() call below passes explicit low
threshold/margin values and an explicit reliable_tapers set — exactly as the
module docstring recommends for tests.
"""
import json
import os
import tempfile
from collections import Counter

import backend.db as db
import backend.paths as _paths
import backend.taper_attribution as taper_attribution
import backend.taper_fingerprints as taper_fingerprints


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_taper_fp_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_description(conn, lb: int, description: str) -> None:
    """Insert a bare entries row (lb_number + description only).

    infer()/_load_descriptions only ever reads the entries table, so tests
    that hand-build attrs directly (bypassing Layer 0/1) never need an
    entry_lineage row at all.
    """
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, description) VALUES (?, ?)",
        (lb, description),
    )
    conn.commit()


def _seed_entry(conn, lb, description, taper_name=None, taper_normalised=None,
                 same_as=None, derived_from=None):
    """Insert matching entries + entry_lineage rows (mirrors
    tests/test_taper_attribution.py's helper) — needed only by tests that
    exercise the full recompute() pipeline, where Layer 0 must actually
    confirm the seeded tapers from entry_lineage."""
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, description) VALUES (?, ?)",
        (lb, description),
    )
    conn.execute(
        """INSERT OR REPLACE INTO entry_lineage
           (lb_number, taper_name, source_chain, taper_normalised, mentions_lb,
            same_as_lb, derived_from_lb, better_than_lb, parse_confidence, source_text_hash)
           VALUES (?, ?, NULL, ?, '[]', ?, ?, '[]', 'medium', 'test')""",
        (lb, taper_name, taper_normalised,
         json.dumps(same_as or []), json.dumps(derived_from or [])),
    )
    conn.commit()


def _get_attr(conn, lb):
    row = conn.execute("SELECT * FROM taper_attributions WHERE lb_number = ?", (lb,)).fetchone()
    return dict(row) if row else None


def _attrs_row(taper: str, tier: str = "confirmed") -> dict:
    """Minimal in-memory attrs row, shaped like taper_attribution's own rows."""
    return {"taper": taper, "tier": tier, "conflict": 0,
            "evidence": [{"kind": "test", "detail": "seeded for test"}],
            "confirmed_at": None}


# Three synthetic tokens, never colliding with any real _KNOWN_TAPER_ALIASES
# entry, shared by every seeded 'spot' source doc below so a profile forms.
_DISCRIMINATIVE_TOKENS = ["microphonesignature", "cableharnessalpha", "reelcasingbeta"]

# Every doc (filler, spot source, and scoring target) shares this exact
# wrapper text verbatim — only the discriminative tokens spliced into the
# middle differ. That keeps every non-discriminative word's document
# frequency at (essentially) 100% of the background corpus, so
# _excluded_by_df drops all of them and only the spliced-in tokens are ever
# candidates for a profile — without this, incidental shared wrapper words
# (e.g. "recording", "show") would also clear Z_THRESHOLD and leak into the
# profile, over-matching targets that were only meant to carry a subset of
# _DISCRIMINATIVE_TOKENS.
_WRAPPER_PREFIX = "Audience recording, no taper information given for this show, "
_WRAPPER_SUFFIX = (", just a plain tape that circulated among collectors informally "
                    "without further documentation.")

_FILLER_TEXT = _WRAPPER_PREFIX.rstrip(", ") + _WRAPPER_SUFFIX


def _wrapped(tokens) -> str:
    return _WRAPPER_PREFIX + " ".join(tokens) + _WRAPPER_SUFFIX


def _seed_spot_background(conn, filler_count=100, spot_count=8,
                           filler_start=5000, spot_start=6000):
    """Seed a background corpus (entries-only) plus hand-built confirmed attrs
    for a 'spot' source-doc set sharing _DISCRIMINATIVE_TOKENS.

    filler_count/spot_count are sized so the discriminative tokens both clear
    the MAX_GLOBAL_DF stopword filter (spot_count docs out of a background of
    filler_count + spot_count is well under 10%) and reach Z_THRESHOLD despite
    the Dirichlet prior (a background of only a few dozen docs would dilute
    the z-score below significance — see _build_profile).

    Returns:
        {lb: confirmed-tier attrs row} for the seeded spot lb range — pass
        this straight into infer() as *attrs*.
    """
    for i in range(filler_count):
        _seed_description(conn, filler_start + i, _FILLER_TEXT)

    attrs = {}
    for i in range(spot_count):
        lb = spot_start + i
        _seed_description(conn, lb, _wrapped(_DISCRIMINATIVE_TOKENS))
        attrs[lb] = _attrs_row("spot")
    return attrs


def _seed_spot_confirmed_docs(conn, count=8, start=6000):
    """Seed *count* Layer-0-confirmed 'spot' entries (entries + entry_lineage)
    sharing _DISCRIMINATIVE_TOKENS — for tests that exercise the full
    recompute() pipeline, where Layer 0/1 must actually confirm them from
    entry_lineage rather than having attrs hand-built."""
    for i in range(count):
        lb = start + i
        desc = "Taper: Spot\n" + _wrapped(_DISCRIMINATIVE_TOKENS)
        _seed_entry(conn, lb, desc, taper_name="spot", taper_normalised="spot")


def _seed_target(conn, lb, tokens):
    """Seed one unattributed candidate doc containing *tokens*."""
    _seed_description(conn, lb, _wrapped(tokens))


# ── _tokenize ────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_joins_internal_punctuation():
    tokens = taper_fingerprints._tokenize(
        "Hello WORLD! Schoeps-CMC64 b&o co-op don't 99 a x1"
    )
    assert tokens == ["hello", "world", "schoeps-cmc64", "b&o", "co-op", "don't", "x1"]


def test_tokenize_drops_pure_digits_and_short_tokens():
    tokens = taper_fingerprints._tokenize("2023 1975 a I ok b2 42x")
    assert tokens == ["ok", "b2", "42x"]


# ── DF stopword filter ──────────────────────────────────────────────────────

def test_excluded_by_df_boundary():
    doc_freq = Counter({"common": 3, "rare": 2, "verycommon": 10})
    excluded = taper_fingerprints._excluded_by_df(doc_freq, total_docs=20)
    # limit = 0.10 * 20 = 2.0; df > limit excluded, df <= limit kept.
    assert "verycommon" in excluded   # 10 > 2.0
    assert "common" in excluded       # 3 > 2.0
    assert "rare" not in excluded     # 2 > 2.0 is False (boundary, kept)


def test_excluded_by_df_zero_docs_returns_empty():
    assert taper_fingerprints._excluded_by_df(Counter({"x": 5}), total_docs=0) == set()


# ── Profile building: alias exclusion + DF exclusion ────────────────────────

def test_build_profile_excludes_all_known_alias_tokens():
    """Profiles now exclude EVERY known taper alias token, not just the
    profiled taper's own — cross-taper handle mentions in boilerplate must
    not leak into any profile's vocabulary."""
    docs = [["spot", "hide", "mjs", "uniquesignal"] for _ in range(8)]
    global_counts = Counter()
    for d in docs:
        global_counts.update(d)
    global_counts.update({"filler": 5000})
    total_bg_tokens = sum(global_counts.values())

    profile = taper_fingerprints._build_profile(
        docs, global_counts, total_bg_tokens, taper_fingerprints._ALL_ALIAS_TOKENS
    )

    for alias_tok in ("spot", "hide", "mjs"):
        assert alias_tok not in profile
    assert "uniquesignal" in profile


def test_build_profile_respects_df_excluded_tokens():
    docs = [["distinctiveterm", "commonchatter"] for _ in range(8)]
    global_counts = Counter({"distinctiveterm": 8, "commonchatter": 8, "filler": 5000})
    total_bg_tokens = sum(global_counts.values())

    profile = taper_fingerprints._build_profile(
        docs, global_counts, total_bg_tokens, excluded_tokens={"commonchatter"}
    )

    assert "commonchatter" not in profile
    assert "distinctiveterm" in profile


# ── _best_candidate: MIN_MATCHED_TOKENS gate ────────────────────────────────

def test_best_candidate_requires_min_matched_tokens():
    profiles = {"spot": {"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0}}
    assert taper_fingerprints._best_candidate(["a", "b", "x", "y"], profiles) is None

    result = taper_fingerprints._best_candidate(["a", "b", "c", "x"], profiles)
    assert result is not None
    winner, score, margin, matched = result
    assert winner == "spot"
    assert score == 15.0
    assert margin == 15.0  # no runner-up profile -> margin == score
    assert sorted(matched) == ["a", "b", "c"]


# ── Poisoned-component exclusion (TODO-234) ─────────────────────────────────

def test_poisoned_lbs_excludes_conflict_component():
    attrs = {
        10: {"taper": "spot", "tier": "confirmed", "conflict": 0},
        11: {"taper": "hide", "tier": "confirmed", "conflict": 1},
    }
    fam_members = {"F1": [10, 11]}

    poisoned = taper_fingerprints._poisoned_lbs(attrs, fam_members, {}, {}, set())
    assert poisoned == {10, 11}

    token_cache = {10: ["spot", "gear"], 11: ["hide", "gear"]}
    source_docs = taper_fingerprints._source_docs_by_taper(attrs, token_cache, poisoned)
    assert "spot" not in source_docs  # lb 10 itself has conflict=0 but shares 11's component


def test_poisoned_lbs_includes_edgeless_unresolved_regression():
    """Regression: an unresolved lb with no same-source edges never enters the
    DSU/component loop, so _poisoned_lbs must union `unresolved` in directly
    rather than relying solely on the component scan finding it."""
    attrs = {99: {"taper": "spot", "tier": "confirmed", "conflict": 0}}

    poisoned = taper_fingerprints._poisoned_lbs(attrs, {}, {}, {}, {99})
    assert 99 in poisoned

    token_cache = {99: ["spot", "gear"]}
    source_docs = taper_fingerprints._source_docs_by_taper(attrs, token_cache, poisoned)
    assert "spot" not in source_docs


# ── Profile gate (MIN_PROFILE_ENTRIES) ──────────────────────────────────────

def test_profile_gate_below_min_entries_builds_no_profile():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=7)  # one short of 8
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=0.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )

    assert result["profiles"] == 0
    assert result["inferred"] == 0
    assert 7000 not in attrs


# ── Scoring no-ops ───────────────────────────────────────────────────────────

def test_scoring_requires_min_matched_tokens():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS[:2])  # only 2 of 3 -> below MIN_MATCHED_TOKENS

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=0.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )

    assert result["profiles"] == 1  # confirms the fixture itself is valid
    assert 7000 not in attrs


def test_scoring_below_score_threshold_writes_no_row():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)  # all 3 -> matches MIN_MATCHED_TOKENS

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=1_000_000.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )

    assert result["profiles"] == 1
    assert 7000 not in attrs


def test_scoring_winner_not_in_reliable_tapers_writes_no_row():
    """Winner clears the score and margin gates but isn't in the caller's
    reliable_tapers set -> gate 3 still blocks the write."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=0.0, margin_threshold=0.0, reliable_tapers=set(),
    )

    assert result["profiles"] == 1
    assert result["reliable_tapers"] == 0
    assert 7000 not in attrs


def test_infer_writes_inferred_row_when_all_gates_pass():
    """Positive control: with all three gates trivially satisfied, infer()
    actually writes the row (proves the fixture, not just the negative paths,
    is sound)."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=0.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )

    assert result["profiles"] == 1
    assert result["inferred"] == 1
    row = attrs[7000]
    assert row["taper"] == "spot"
    assert row["tier"] == "inferred"
    assert any(e["kind"] == "fingerprint" for e in row["evidence"])


# ── Never-overwrite ──────────────────────────────────────────────────────────

def test_infer_never_overwrites_existing_attrs_entry():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)  # would otherwise clearly win as spot
    existing_row = {"taper": "hide", "tier": "propagated", "conflict": 0,
                     "evidence": [{"kind": "mention", "detail": "pre-existing"}],
                     "confirmed_at": None}
    attrs[7000] = existing_row

    result = taper_fingerprints.infer(
        attrs, conn, {}, {}, {}, set(),
        threshold=0.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )

    assert attrs[7000] == existing_row
    assert result["inferred"] == 0


# ── calibrate(): smoke test only (per spec — not exercised deeply) ─────────

def test_calibrate_smoke_does_not_crash_or_mutate_attrs():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    attrs = _seed_spot_background(conn, filler_count=100, spot_count=8)
    attrs_before = {lb: dict(row) for lb, row in attrs.items()}

    result = taper_fingerprints.calibrate(conn, attrs, {}, {}, {}, set())

    assert attrs == attrs_before
    assert "holdout" in result
    assert "rows" in result
    assert isinstance(result["rows"], list)
    assert "reliable_tapers" in result


# ── recompute() integration ─────────────────────────────────────────────────

def test_recompute_runs_green_and_is_idempotent_with_fingerprint_layer():
    """recompute()'s default gates (150.0/80.0) plus real 5-fold
    cross-validated reliability are far too data-hungry for a tiny fixture,
    so this only asserts the pipeline runs cleanly and stays idempotent —
    the gate-bypassed test below proves the fingerprint layer itself writes
    correctly."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)

    for i in range(100):
        _seed_description(conn, 5000 + i, _FILLER_TEXT)
    _seed_spot_confirmed_docs(conn, count=8, start=6000)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)

    stats1 = taper_attribution.recompute(db_path=db_path)
    rows1 = {
        r["lb_number"]: (r["taper_normalised"], r["confidence"], r["conflict"])
        for r in conn.execute("SELECT * FROM taper_attributions")
    }

    stats2 = taper_attribution.recompute(db_path=db_path)
    rows2 = {
        r["lb_number"]: (r["taper_normalised"], r["confidence"], r["conflict"])
        for r in conn.execute("SELECT * FROM taper_attributions")
    }

    assert rows1 == rows2
    for key in ("total", "confirmed", "propagated", "inferred", "conflict"):
        assert stats1[key] == stats2[key]
    # The 8 explicit-label confirmed docs land regardless of the (likely-empty
    # on this fixture) fingerprint layer.
    assert stats1["confirmed"] == 8


def test_layer2_integration_via_recompute_internals_reject_suppresses_row():
    """Drives recompute()'s exact Layer0/1 -> Layer2 -> reject-reapply
    sequence (taper_attribution._compute_layers01 + taper_fingerprints.infer
    + _apply_rejects/_apply_unresolved + _write_attributions), with explicit
    gate overrides in place of recompute()'s data-hungry defaults, to prove:
    (1) an inferred row lands with tier='inferred' / kind='fingerprint'
    evidence, and (2) a curator 'reject' row suppresses a would-be inferred
    row exactly as it suppresses a Layer 0/1 one.
    """
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)

    for i in range(100):
        _seed_description(conn, 5000 + i, _FILLER_TEXT)
    _seed_spot_confirmed_docs(conn, count=8, start=6000)
    _seed_target(conn, 7000, _DISCRIMINATIVE_TOKENS)  # expected to be inferred
    _seed_target(conn, 7001, _DISCRIMINATIVE_TOKENS)  # curator-rejected before recompute
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (7001, "spot", "reject"),
    )
    conn.commit()

    attrs, fam_members, same_as_adj, derived_from_adj, rejects, unresolved = (
        taper_attribution._compute_layers01(conn))
    taper_fingerprints.infer(
        attrs, conn, fam_members, same_as_adj, derived_from_adj, unresolved,
        threshold=0.0, margin_threshold=0.0, reliable_tapers={"spot"},
    )
    taper_attribution._apply_rejects(attrs, rejects)
    taper_attribution._apply_unresolved(attrs, unresolved)
    taper_attribution._write_attributions(attrs, db_path)

    row7000 = _get_attr(conn, 7000)
    assert row7000 is not None
    assert row7000["confidence"] == "inferred"
    assert row7000["taper_normalised"] == "spot"
    evidence = json.loads(row7000["evidence_json"])
    assert any(e["kind"] == "fingerprint" for e in evidence)

    assert _get_attr(conn, 7001) is None  # curator reject suppressed the inferred row
