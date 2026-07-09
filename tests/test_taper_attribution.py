"""Tests for backend.taper_attribution: Layer 0 seeding, Layer 1 propagation,
conflict detection, taper_confirmations (confirm/reject), and idempotency.
"""
import json
import os
import tempfile

import backend.db as db
import backend.paths as _paths
import backend.taper_attribution as taper_attribution


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_taper_attr_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, description, taper_name=None, taper_normalised=None,
                 same_as=None, derived_from=None):
    """Insert matching entries + entry_lineage rows, bypassing real text parsing
    so tests can exercise Layer 0/1 logic against controlled inputs."""
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


def _seed_family(conn, fam_id, concert_date, members, review_flag=0):
    conn.executemany(
        "INSERT OR REPLACE INTO recording_families(lb_number, fam_id, concert_date)"
        " VALUES (?, ?, ?)",
        [(lb, fam_id, concert_date) for lb in members],
    )
    conn.execute(
        """INSERT OR REPLACE INTO tapematch_family_meta
           (fam_id, concert_date, member_count, review_flag) VALUES (?, ?, ?, ?)""",
        (fam_id, concert_date, len(members), review_flag),
    )
    conn.commit()


def _get_attr(conn, lb):
    row = conn.execute("SELECT * FROM taper_attributions WHERE lb_number = ?", (lb,)).fetchone()
    return dict(row) if row else None


# ── Layer 0 ────────────────────────────────────────────────────────────────────

def test_layer0_explicit_label_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 100, "Taper: Spot\nSource: Schoeps > DAT > FLAC",
                taper_name="spot", taper_normalised="spot")

    stats = taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 100)
    assert row is not None
    assert row["confidence"] == "confirmed"
    assert row["taper_normalised"] == "spot"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "explicit" for e in evidence)
    assert stats["confirmed"] == 1


def test_layer0_series_code_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 101, "LTB, DAT > FLAC, no further info.",
                taper_name="ltb", taper_normalised="ltb")

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 101)
    assert row["confidence"] == "confirmed"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "series_code" for e in evidence)


def test_layer0_bare_mention_propagated():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 102, "Great show, thanks to spot for the tape.",
                taper_name="spot", taper_normalised="spot")

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 102)
    assert row["confidence"] == "propagated"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "mention" for e in evidence)


def test_unknown_taper_not_seeded():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 103, "Taper: J. Random Fan\nSource: unknown",
                taper_name="j random fan", taper_normalised="j random fan")

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 103) is None


def test_dolphinsmile_excluded_from_universe():
    assert "dolphinsmile" not in taper_attribution._TAPER_UNIVERSE

    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 104, "Taper: dolphinsmile\nSource: X",
                taper_name="dolphinsmile", taper_normalised="dolphinsmile")

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 104) is None


# ── Layer 1 propagation ────────────────────────────────────────────────────────

def test_layer1_family_propagation():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 200, "Taper: Spot\nSource: Schoeps > DAT",
                taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 201, "Audience recording, no taper info given.")
    _seed_entry(conn, 202, "Another copy, no taper listed.")
    _seed_family(conn, "F1", "1975-01-01", [200, 201, 202])

    taper_attribution.recompute(db_path=db_path)

    for lb in (201, 202):
        row = _get_attr(conn, lb)
        assert row is not None, f"LB-{lb} should have been propagated"
        assert row["confidence"] == "propagated"
        assert row["taper_normalised"] == "spot"
        assert row["conflict"] == 0
        evidence = json.loads(row["evidence_json"])
        assert any(e["kind"] == "family" and e.get("fam_id") == "F1" for e in evidence)

    # confirmed row itself is untouched
    row200 = _get_attr(conn, 200)
    assert row200["confidence"] == "confirmed"


def test_layer1_same_as_and_derived_from():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 300, "Taper: Hide\nSource: Neumann > DAT",
                taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 301, "Exact same recording as LB-300.", same_as=[300])
    _seed_entry(conn, 302, "Transferred from LB-300 master.", derived_from=[300])

    taper_attribution.recompute(db_path=db_path)

    row301 = _get_attr(conn, 301)
    assert row301["taper_normalised"] == "hide"
    assert row301["confidence"] == "propagated"
    assert any(e["kind"] == "same_as" for e in json.loads(row301["evidence_json"]))

    row302 = _get_attr(conn, 302)
    assert row302["taper_normalised"] == "hide"
    assert any(e["kind"] == "derived_from" for e in json.loads(row302["evidence_json"]))


def test_layer1_multi_hop_propagation():
    """Propagated nodes push too (spec §4.2): confirmed -> A -> B via two hops."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 400, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 401, "No taper info.", same_as=[400])
    _seed_entry(conn, 402, "No taper info either.", same_as=[401])

    taper_attribution.recompute(db_path=db_path)

    row402 = _get_attr(conn, 402)
    assert row402 is not None
    assert row402["taper_normalised"] == "spot"
    assert row402["confidence"] == "propagated"


# ── Conflicts ──────────────────────────────────────────────────────────────────

def test_conflict_two_confirmed_tapers_in_family():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 500, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 501, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 502, "No taper info.")
    _seed_family(conn, "F2", "1976-01-01", [500, 501, 502])

    stats = taper_attribution.recompute(db_path=db_path)

    row500 = _get_attr(conn, 500)
    row501 = _get_attr(conn, 501)
    assert row500["confidence"] == "confirmed" and row500["conflict"] == 0
    assert row501["confidence"] == "confirmed" and row501["conflict"] == 0

    row502 = _get_attr(conn, 502)
    assert row502 is not None
    assert row502["conflict"] == 1
    evidence = json.loads(row502["evidence_json"])
    candidates = {e["detail"] for e in evidence if e["kind"] == "conflict"}
    assert any("spot" in d for d in candidates)
    assert any("hide" in d for d in candidates)
    assert stats["conflict"] == 1


def test_weak_edge_does_not_override_strong_resolution():
    """A review-flagged (weak) family with a candidate taper must not touch a
    node the strong pass already resolved (spec: weak loses to strong, no conflict)."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 600, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 601, "No taper info.", same_as=[600])  # strong: resolves to spot
    _seed_entry(conn, 602, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    # Weak (review-flagged) family linking the already-strong-resolved 601 to 602 (hide).
    _seed_family(conn, "F3-weak", "1977-01-01", [601, 602], review_flag=1)

    taper_attribution.recompute(db_path=db_path)

    row601 = _get_attr(conn, 601)
    assert row601["taper_normalised"] == "spot"
    assert row601["conflict"] == 0


# ── taper_confirmations (MASTER, F2) ───────────────────────────────────────────

def test_confirmation_is_sticky_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 700, "Plain audience recording, no taper info at all.")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (700, "spot", "confirm"),
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 700)
    assert row["confidence"] == "confirmed"
    assert row["taper_normalised"] == "spot"
    assert row["confirmed_at"] is not None
    assert any(e["kind"] == "confirmation" for e in json.loads(row["evidence_json"]))


def test_rejection_suppresses_output():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 701, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (701, "spot", "reject"),
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 701) is None


def test_rejection_does_not_suppress_different_taper():
    """A reject on (lb, taper=X) must not block a legitimately different taper Y
    for the same lb — only the specific rejected pair is suppressed."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 702, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (702, "spot", "reject"),  # rejects a taper this entry doesn't even have
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 702)
    assert row is not None
    assert row["taper_normalised"] == "hide"


# ── Idempotency (spec §7) ───────────────────────────────────────────────────────

def test_idempotent_rerun():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 800, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 801, "No taper info.", same_as=[800])
    _seed_entry(conn, 802, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 803, "No taper info.")
    _seed_family(conn, "F4", "1978-01-01", [802, 803])
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (900, "mjs", "confirm"),
    )
    _seed_entry(conn, 900, "No taper info.")

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
        assert stats1[key] == stats2[key], f"Mismatch on {key}: {stats1[key]} vs {stats2[key]}"


def test_dry_run_does_not_write():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1000, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")

    stats = taper_attribution.recompute(db_path=db_path, dry_run=True)

    assert stats["confirmed"] == 1
    assert _get_attr(conn, 1000) is None
