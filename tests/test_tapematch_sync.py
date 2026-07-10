"""Tests for backend/tapematch_sync.py.

Covers the regex-based ``_parse_verdict`` helper that extracts the
tapematch-batch skill's "needs review" flag + reason from each run's
analysis.md; the ``similarity_pct`` banded-blend calibration (LISTENING §1);
and ``sync_tapematch_pairs``'s round-trip / wholesale-replace-per-date
semantics against a tmp observations.db fixture.
"""

import os
import shutil
import sqlite3
import tempfile

import backend.db as db
import backend.paths as _paths
from backend.tapematch_sync import _parse_verdict, similarity_pct, sync_tapematch_pairs


def test_parse_verdict_clean_looks_correct():
    text = "## Verdict: 3 recordings — 2 families — result looks correct\n"
    assert _parse_verdict(text) == (False, None)


def test_parse_verdict_clean_all_confirmed_different():
    text = "## Verdict: 2 recordings — 2 families — all sources confirmed different\n"
    assert _parse_verdict(text) == (False, None)


def test_parse_verdict_needs_review_with_reason():
    text = (
        "## Verdict: 2 recordings — 2 families — result needs review — "
        "LB-04776's claimed same-source identity with LB-04053 is contradicted "
        "by near-zero correlation\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == (
        "LB-04776's claimed same-source identity with LB-04053 is contradicted "
        "by near-zero correlation"
    )


def test_parse_verdict_needs_review_reason_contains_em_dash():
    # The reason clause can itself contain "—"-joined sub-clauses; the parser
    # must rejoin everything after "needs review" rather than truncating at
    # the first dash.
    text = (
        "## Verdict: 7 recordings — 7 families — result needs review — "
        "LB-10613's claimed identity with LB-807/LB-1940 is contradicted — "
        "and LB-4210's claim is also unresolved\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == (
        "LB-10613's claimed identity with LB-807/LB-1940 is contradicted — "
        "and LB-4210's claim is also unresolved"
    )


def test_parse_verdict_needs_review_no_reason():
    text = "## Verdict: 3 recordings — 3 families — result needs review\n"
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason is None


def test_parse_verdict_no_verdict_line():
    assert _parse_verdict("# Analysis — 1991-01-01 — Nowhere\n\nNo verdict here.\n") == (False, None)


def test_parse_verdict_finds_line_anywhere_in_document():
    text = (
        "# Analysis — 1991-01-01 — Nowhere\n"
        "*Claude claude-sonnet-4-6 — 2026-06-22*\n\n"
        "## Verdict: 4 recordings — 4 families — result needs review — reason text\n\n"
        "| LB | Rating |\n|----|----|\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == "reason text"


# ── similarity_pct (LISTENING §1.2 banded blend) ─────────────────────────────


def test_similarity_pct_same_family_both_null_is_floor():
    assert similarity_pct(None, None, True) == 85


def test_similarity_pct_same_family_corr_at_lower_breakpoint_is_floor():
    assert similarity_pct(0.05, None, True) == 85


def test_similarity_pct_same_family_corr_at_upper_breakpoint_is_ceiling():
    assert similarity_pct(0.90, None, True) == 100


def test_similarity_pct_same_family_corr_below_floor_clamps():
    assert similarity_pct(0.0, None, True) == 85


def test_similarity_pct_same_family_corr_above_ceiling_clamps():
    assert similarity_pct(5.0, None, True) == 100


def test_similarity_pct_same_family_uses_max_of_corr_and_emb_terms():
    # Low corr signal, strong emb signal -> emb term wins the max().
    assert similarity_pct(0.05, 0.95, True) == similarity_pct(None, 0.95, True)


def test_similarity_pct_same_family_emb_only():
    assert similarity_pct(None, 0.30, True) == 85
    assert similarity_pct(None, 0.95, True) == 100


def test_similarity_pct_different_family_both_null_is_not_comparable():
    assert similarity_pct(None, None, False) is None


def test_similarity_pct_different_family_emb_takes_priority_over_corr():
    # emb present -> corr ignored entirely, even if corr alone would differ.
    assert similarity_pct(0.9, 0.65, False) == 40
    assert similarity_pct(None, 0.65, False) == 40


def test_similarity_pct_different_family_emb_zero_floor():
    assert similarity_pct(None, 0.0, False) == 0


def test_similarity_pct_different_family_emb_above_ceiling_clamps():
    assert similarity_pct(None, 5.0, False) == 40


def test_similarity_pct_different_family_corr_fallback():
    assert similarity_pct(0.041, None, False) == 20


def test_similarity_pct_different_family_corr_fallback_clamps():
    assert similarity_pct(1.0, None, False) == 20


def test_similarity_pct_different_family_corr_zero():
    assert similarity_pct(0.0, None, False) == 0


# ── sync_tapematch_pairs round trip / wholesale-replace-per-date ────────────

_RUNS_SCHEMA = (
    "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
    "n_sources_ran INTEGER, archive_dir TEXT)"
)
_PAIRS_SCHEMA = (
    "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
    "concert_date TEXT NOT NULL, lb_a INTEGER, lb_b INTEGER, corr REAL, "
    "tapematch_verdict TEXT, emb_score REAL, fp_score REAL)"
)


def _make_app_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_tapematch_pairs_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _make_obs_db(tmp_dir, filename, runs, pairs):
    """Minimal observations.db fixture: just the columns sync_tapematch_pairs
    reads (``runs.run_id/concert_date/n_sources_ran`` for `_pick_best_run`,
    ``pairs.run_id/concert_date/lb_a/lb_b/corr/tapematch_verdict/emb_score/
    fp_score``).
    """
    obs_path = os.path.join(tmp_dir, filename)
    conn = sqlite3.connect(obs_path)
    conn.execute(_RUNS_SCHEMA)
    conn.execute(_PAIRS_SCHEMA)
    conn.executemany(
        "INSERT INTO runs (run_id, concert_date, n_sources_ran, archive_dir) "
        "VALUES (?, ?, ?, ?)",
        runs,
    )
    conn.executemany(
        "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, corr, tapematch_verdict, "
        "emb_score, fp_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        pairs,
    )
    conn.commit()
    conn.close()
    return obs_path


def test_sync_tapematch_pairs_round_trip_and_wholesale_replace():
    db_path, tmp_dir = _make_app_db()
    try:
        obs_path = _make_obs_db(
            tmp_dir,
            "observations.db",
            runs=[("20260101_000000", "1991-01-01", 2, None)],
            pairs=[
                ("20260101_000000", "1991-01-01", 20, 10, 0.9, "same_family", 0.95, 0.8),
            ],
        )
        stats = sync_tapematch_pairs(db_path=db_path, observations_db_path=obs_path)
        assert stats["dates_processed"] == 1
        assert stats["pairs_written"] == 1
        assert stats["errors"] == []

        conn = db.get_connection(db_path)
        rows = conn.execute(
            "SELECT * FROM tapematch_pairs WHERE concert_date = '1991-01-01'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        # lb_a/lb_b are normalised so lb_a < lb_b, even though the source row
        # had lb_a=20 > lb_b=10.
        assert row["lb_a"] == 10
        assert row["lb_b"] == 20
        assert row["same_family"] == 1
        assert row["run_id"] == "20260101_000000"
        assert row["similarity_pct"] == similarity_pct(0.9, 0.95, True)

        # Re-sync with a newer, more-complete run for the same date -> the
        # date's rows must be wholesale-replaced, never blended across runs.
        obs_path_2 = _make_obs_db(
            tmp_dir,
            "observations2.db",
            runs=[("20260102_000000", "1991-01-01", 3, None)],
            pairs=[
                ("20260102_000000", "1991-01-01", 10, 30, 0.03, "different_family", 0.6, None),
            ],
        )
        stats2 = sync_tapematch_pairs(db_path=db_path, observations_db_path=obs_path_2)
        assert stats2["pairs_written"] == 1

        rows2 = conn.execute(
            "SELECT * FROM tapematch_pairs WHERE concert_date = '1991-01-01'"
        ).fetchall()
        assert len(rows2) == 1
        row2 = rows2[0]
        assert row2["run_id"] == "20260102_000000"
        assert row2["lb_a"] == 10
        assert row2["lb_b"] == 30
        assert row2["same_family"] == 0
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sync_tapematch_pairs_multiple_dates_and_null_similarity():
    db_path, tmp_dir = _make_app_db()
    try:
        obs_path = _make_obs_db(
            tmp_dir,
            "observations.db",
            runs=[
                ("20260101_000000", "1991-01-01", 2, None),
                ("20260101_000100", "1991-02-02", 2, None),
            ],
            pairs=[
                ("20260101_000000", "1991-01-01", 1, 2, 0.9, "same_family", None, None),
                # No corr, no emb_score, different_family -> "not comparable".
                ("20260101_000100", "1991-02-02", 3, 4, None, "different_family", None, None),
            ],
        )
        stats = sync_tapematch_pairs(db_path=db_path, observations_db_path=obs_path)
        assert stats["dates_processed"] == 2
        assert stats["pairs_written"] == 2
        assert stats["errors"] == []

        conn = db.get_connection(db_path)
        row = conn.execute(
            "SELECT similarity_pct FROM tapematch_pairs WHERE concert_date = '1991-02-02'"
        ).fetchone()
        assert row["similarity_pct"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
