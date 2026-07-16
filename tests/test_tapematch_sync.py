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

import pytest

import backend.db as db
import backend.paths as _paths
from backend.tapematch_sync import (
    _has_quality_match,
    _load_latest_abs_scores,
    _parse_verdict,
    duplicate_encode_candidates,
    similarity_pct,
    sync_tapematch_families,
    sync_tapematch_pairs,
)


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


def test_parse_verdict_needs_review_colon_reason():
    # Variant form observed in the written corpus (run 20260616_090656):
    # "needs review: <reason>" — pre-2026-07-16 the parser dropped these
    # reasons, leaving NULL review_reason (TODO-242 tooltip gap).
    text = (
        "## Verdict: 6 recordings — 3 families — result needs review: "
        "low-confidence merge in Family 2, LB-12842 not found on disk\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == "low-confidence merge in Family 2, LB-12842 not found on disk"


def test_parse_verdict_needs_review_parenthesized_reason():
    # Variant form observed in the written corpus (runs 20260616_19xxxx):
    # "needs review (<reason>)".
    text = (
        "## Verdict: 2 recordings — 2 families — result needs review "
        "(commentary contradicts the distinct-source split; 1 DB entry missing from disk)\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == "commentary contradicts the distinct-source split; 1 DB entry missing from disk"


def test_parse_verdict_bare_needs_review_mid_line():
    # Bare "needs review" with a parenthetical earlier in the line (run
    # 20260615_154028): the "(1 not on disk)" count is NOT the reason.
    text = "## Verdict: 7 recordings (1 not on disk) — 5 families — needs review\n"
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


# ── TODO-210(a): quality-match confidence bump ──────────────────────────────

_FAMILY_RUNS_SCHEMA = (
    "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
    "n_sources_ran INTEGER, archive_dir TEXT)"
)
_SOURCES_SCHEMA = (
    "CREATE TABLE sources (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
    "concert_date TEXT NOT NULL, lb_number INTEGER, family_id INTEGER)"
)
_FAMILY_PAIRS_SCHEMA = (
    "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
    "concert_date TEXT NOT NULL, lb_a INTEGER, lb_b INTEGER, corr REAL, "
    "tapematch_verdict TEXT, family_id_a INTEGER, family_id_b INTEGER, lb_says_same INTEGER)"
)


def _make_family_obs_db(tmp_dir, filename, run, sources, pairs):
    """observations.db fixture with runs/sources/pairs for sync_tapematch_families.

    Args:
        run: (run_id, concert_date, n_sources_ran, archive_dir) tuple.
        sources: list of (run_id, concert_date, lb_number, family_id) tuples.
        pairs: list of (run_id, concert_date, lb_a, lb_b, corr, tapematch_verdict,
            family_id_a, family_id_b, lb_says_same) tuples.
    """
    obs_path = os.path.join(tmp_dir, filename)
    conn = sqlite3.connect(obs_path)
    conn.execute(_FAMILY_RUNS_SCHEMA)
    conn.execute(_SOURCES_SCHEMA)
    conn.execute(_FAMILY_PAIRS_SCHEMA)
    conn.execute(
        "INSERT INTO runs (run_id, concert_date, n_sources_ran, archive_dir) VALUES (?, ?, ?, ?)",
        run,
    )
    conn.executemany(
        "INSERT INTO sources (run_id, concert_date, lb_number, family_id) VALUES (?, ?, ?, ?)",
        sources,
    )
    conn.executemany(
        "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, corr, tapematch_verdict, "
        "family_id_a, family_id_b, lb_says_same) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        pairs,
    )
    conn.commit()
    conn.close()
    return obs_path


def _seed_abs_score(conn, lb_number, scan_id, abs_score, abs_grade):
    """Insert a quality_recording_scores row with abs_score/abs_grade columns
    added (mirrors tests/test_show_picks.py's _seed_quality pattern).

    Also inserts a placeholder ``entries`` row since
    ``quality_recording_scores.lb_number`` is FK-constrained to it.
    """
    from concert_ranker.lb import repo as cr_repo

    cr_repo.ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO entries (lb_number, status) VALUES (?, 'ok')", (lb_number,)
    )
    conn.execute(
        "INSERT OR REPLACE INTO quality_recording_scores"
        " (lb_number, scan_id, abs_score, abs_grade) VALUES (?, ?, ?, ?)",
        (lb_number, scan_id, abs_score, abs_grade),
    )
    conn.commit()


def test_load_latest_abs_scores_missing_columns_returns_empty():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        # No cr_repo.ensure_schema() call -> abs_score/abs_grade don't exist yet.
        assert _load_latest_abs_scores(conn) == {}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_load_latest_abs_scores_picks_each_lbs_newest_scan():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_abs_score(conn, 100, scan_id=1, abs_score=80.0, abs_grade="B+")
        _seed_abs_score(conn, 100, scan_id=2, abs_score=85.0, abs_grade="A-")
        _seed_abs_score(conn, 200, scan_id=1, abs_score=79.5, abs_grade="B")

        result = _load_latest_abs_scores(conn)
        assert result[100] == (2, 85.0, "A-")
        assert result[200] == (1, 79.5, "B")
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_has_quality_match_true_within_tolerance_and_same_grade_letter():
    abs_scores = {10: (5, 80.0, "B+"), 20: (5, 80.3, "B-")}
    assert _has_quality_match([10, 20], abs_scores) is True


def test_has_quality_match_false_different_scan_id():
    abs_scores = {10: (5, 80.0, "B+"), 20: (6, 80.3, "B-")}
    assert _has_quality_match([10, 20], abs_scores) is False


def test_has_quality_match_false_outside_tolerance():
    abs_scores = {10: (5, 80.0, "B"), 20: (5, 81.0, "B")}
    assert _has_quality_match([10, 20], abs_scores) is False


def test_has_quality_match_false_different_grade_letter():
    abs_scores = {10: (5, 80.0, "B"), 20: (5, 80.1, "C")}
    assert _has_quality_match([10, 20], abs_scores) is False


def test_has_quality_match_false_missing_lb():
    abs_scores = {10: (5, 80.0, "B")}
    assert _has_quality_match([10, 20], abs_scores) is False


def test_sync_families_applies_quality_match_bump():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_abs_score(conn, 10, scan_id=1, abs_score=80.0, abs_grade="B+")
        _seed_abs_score(conn, 20, scan_id=1, abs_score=80.3, abs_grade="B-")

        obs_path = _make_family_obs_db(
            tmp_dir,
            "observations.db",
            run=("20260101_000000", "1991-01-01", 2, None),
            sources=[
                ("20260101_000000", "1991-01-01", 10, 1),
                ("20260101_000000", "1991-01-01", 20, 1),
            ],
            pairs=[
                ("20260101_000000", "1991-01-01", 10, 20, 0.5, "same_family", 1, 1, None),
            ],
        )
        stats = sync_tapematch_families(db_path=db_path, observations_db_path=obs_path)
        assert stats["errors"] == []

        row = conn.execute(
            "SELECT conf FROM tapematch_family_meta WHERE concert_date = '1991-01-01'"
        ).fetchone()
        assert row["conf"] == pytest.approx(0.55)
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sync_families_no_bump_when_quality_scores_dont_match():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_abs_score(conn, 10, scan_id=1, abs_score=80.0, abs_grade="B")
        _seed_abs_score(conn, 20, scan_id=1, abs_score=95.0, abs_grade="A")

        obs_path = _make_family_obs_db(
            tmp_dir,
            "observations.db",
            run=("20260101_000000", "1991-01-01", 2, None),
            sources=[
                ("20260101_000000", "1991-01-01", 10, 1),
                ("20260101_000000", "1991-01-01", 20, 1),
            ],
            pairs=[
                ("20260101_000000", "1991-01-01", 10, 20, 0.5, "same_family", 1, 1, None),
            ],
        )
        stats = sync_tapematch_families(db_path=db_path, observations_db_path=obs_path)
        assert stats["errors"] == []

        row = conn.execute(
            "SELECT conf FROM tapematch_family_meta WHERE concert_date = '1991-01-01'"
        ).fetchone()
        assert row["conf"] == pytest.approx(0.5)
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sync_families_bump_clamps_to_one():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_abs_score(conn, 10, scan_id=1, abs_score=80.0, abs_grade="A")
        _seed_abs_score(conn, 20, scan_id=1, abs_score=80.0, abs_grade="A")

        obs_path = _make_family_obs_db(
            tmp_dir,
            "observations.db",
            run=("20260101_000000", "1991-01-01", 2, None),
            sources=[
                ("20260101_000000", "1991-01-01", 10, 1),
                ("20260101_000000", "1991-01-01", 20, 1),
            ],
            pairs=[
                ("20260101_000000", "1991-01-01", 10, 20, 0.98, "same_family", 1, 1, None),
            ],
        )
        stats = sync_tapematch_families(db_path=db_path, observations_db_path=obs_path)
        assert stats["errors"] == []

        row = conn.execute(
            "SELECT conf FROM tapematch_family_meta WHERE concert_date = '1991-01-01'"
        ).fetchone()
        assert row["conf"] == pytest.approx(1.0)
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sync_families_no_bump_when_abs_columns_missing():
    # No cr_repo.ensure_schema() call anywhere -> quality_recording_scores has
    # no abs_score/abs_grade columns -> _load_latest_abs_scores degrades to {}
    # -> sync must proceed with the raw mean conf, not crash.
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)

        obs_path = _make_family_obs_db(
            tmp_dir,
            "observations.db",
            run=("20260101_000000", "1991-01-01", 2, None),
            sources=[
                ("20260101_000000", "1991-01-01", 10, 1),
                ("20260101_000000", "1991-01-01", 20, 1),
            ],
            pairs=[
                ("20260101_000000", "1991-01-01", 10, 20, 0.5, "same_family", 1, 1, None),
            ],
        )
        stats = sync_tapematch_families(db_path=db_path, observations_db_path=obs_path)
        assert stats["errors"] == []

        row = conn.execute(
            "SELECT conf FROM tapematch_family_meta WHERE concert_date = '1991-01-01'"
        ).fetchone()
        assert row["conf"] == pytest.approx(0.5)
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── TODO-210(b): duplicate_encode_candidates ────────────────────────────────


def _seed_entry_date(conn, lb_number, date_str):
    conn.execute(
        "INSERT OR REPLACE INTO entries (lb_number, date_str, status) VALUES (?, ?, 'ok')",
        (lb_number, date_str),
    )
    conn.commit()


def _seed_metric(conn, lb_number, scan_id, metric_json):
    conn.execute(
        "INSERT OR REPLACE INTO quality_recording_metrics"
        " (lb_number, scan_id, metric_json) VALUES (?, ?, ?)",
        (lb_number, scan_id, metric_json),
    )
    conn.commit()


def test_duplicate_encode_candidates_finds_identical_metric_json_same_scan():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "7/8/78")
        _seed_entry_date(conn, 200, "7/8/78")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')
        _seed_metric(conn, 200, scan_id=1, metric_json='{"a": 1}')

        candidates = duplicate_encode_candidates(conn)
        assert candidates == [
            {
                "date": "7/8/78",
                "lb_a": 100,
                "lb_b": 200,
                "scan_id": 1,
                "same_family": False,
                "reason": "likely duplicate encode",
            }
        ]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_encode_candidates_ignores_different_scan_id():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "7/8/78")
        _seed_entry_date(conn, 200, "7/8/78")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')
        _seed_metric(conn, 200, scan_id=2, metric_json='{"a": 1}')

        assert duplicate_encode_candidates(conn) == []
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_encode_candidates_ignores_different_date():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "7/8/78")
        _seed_entry_date(conn, 200, "7/9/78")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')
        _seed_metric(conn, 200, scan_id=1, metric_json='{"a": 1}')

        assert duplicate_encode_candidates(conn) == []
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_encode_candidates_ignores_non_identical_metric_json():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "7/8/78")
        _seed_entry_date(conn, 200, "7/8/78")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')
        _seed_metric(conn, 200, scan_id=1, metric_json='{"a": 2}')

        assert duplicate_encode_candidates(conn) == []
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_encode_candidates_flags_already_same_family():
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "11/20/96")
        _seed_entry_date(conn, 200, "11/20/96")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')
        _seed_metric(conn, 200, scan_id=1, metric_json='{"a": 1}')
        conn.execute(
            "INSERT INTO recording_families (lb_number, fam_id, concert_date) "
            "VALUES (100, 'fam-a', '1996-11-20')"
        )
        conn.execute(
            "INSERT INTO recording_families (lb_number, fam_id, concert_date) "
            "VALUES (200, 'fam-a', '1996-11-20')"
        )
        conn.commit()

        candidates = duplicate_encode_candidates(conn)
        assert len(candidates) == 1
        assert candidates[0]["same_family"] is True
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_encode_candidates_distinct_lb_numbers_only_one_row_each():
    # A single lb_number scored once must never pair with itself.
    db_path, tmp_dir = _make_app_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry_date(conn, 100, "7/8/78")
        _seed_metric(conn, 100, scan_id=1, metric_json='{"a": 1}')

        assert duplicate_encode_candidates(conn) == []
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
