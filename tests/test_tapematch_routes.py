"""Tests for the LISTENING §1 read routes added to backend/app.py:
GET /api/tapematch/pairs, GET /api/tapematch/analysis, and
GET /api/tapematch/crawl/status. Follows tests/test_library_picks_api.py's
_AppClient pattern for wiring backend.app's create_app() to a temp DB path.
"""
import os
import shutil
import sqlite3
import subprocess
import tempfile

import backend.app as app_module
import backend.db as db
import backend.paths as _paths
import backend.tapematch_sync as tapematch_sync


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_tapematch_routes_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


class _AppClient:
    """Context manager wiring backend.app's create_app() to a temp DB path."""

    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self._orig_db_path = _paths.DB_PATH
        self._orig_module_db_path = getattr(db, "DB_PATH", None)
        _paths.DB_PATH = self.db_path
        db.DB_PATH = self.db_path
        from backend.app import create_app
        app = create_app()
        return app.test_client()

    def __exit__(self, *exc):
        _paths.DB_PATH = self._orig_db_path
        if self._orig_module_db_path is not None:
            db.DB_PATH = self._orig_module_db_path


# ── GET /api/tapematch/dup_encodes ───────────────────────────────────────────


def test_dup_encodes_route_returns_candidates():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, status) VALUES (100, '7/8/78', 'ok')"
        )
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, status) VALUES (200, '7/8/78', 'ok')"
        )
        conn.execute(
            "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json) "
            "VALUES (100, 1, '{\"a\": 1}')"
        )
        conn.execute(
            "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json) "
            "VALUES (200, 1, '{\"a\": 1}')"
        )
        conn.commit()

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/dup_encodes")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body == {
                "candidates": [
                    {
                        "date": "7/8/78", "lb_a": 100, "lb_b": 200, "scan_id": 1,
                        "same_family": False, "reason": "likely duplicate encode",
                    }
                ]
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dup_encodes_route_empty_when_no_matches():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/dup_encodes")
            assert resp.status_code == 200
            assert resp.get_json() == {"candidates": []}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/pairs ─────────────────────────────────────────────────


def test_pairs_route_returns_synced_rows_for_date(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO tapematch_pairs "
            "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
            " similarity_pct, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("1991-01-01", 10, 20, 0.9, 0.95, 0.8, 1, 100, "20260101_000000"),
        )
        conn.commit()
        # No observations.db -> human feedback + ab_eligible enrichment skipped.
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "nope.db"),
        )

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["date"] == "1991-01-01"
            assert body["run_id"] == "20260101_000000"
            assert body["pairs"] == [
                {
                    "lb_a": 10, "lb_b": 20, "corr": 0.9, "emb_score": 0.95,
                    "fp_score": 0.8, "same_family": True, "similarity_pct": 100,
                    "human_judgment": None, "human_notes": None,
                    "lb_says_same": None, "lb_relation_text": None,
                    "windowed_frac": None, "hiss_median": None,
                    "ab_eligible": None,
                }
            ]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _make_enriched_pairs_db(
    tmp_dir, run_id, concert_date, lb_a, lb_b, secondary_cols=True
):
    """Create an observations.db whose enrichment block can fully succeed.

    Seeds a 'pairs' row carrying human_judgment/lb_says_same/lb_relation_text
    (the fields GET /api/tapematch/pairs copies onto each returned pair) and a
    minimal 'sources' table with one row per LB on the same run_id, which is
    what backend.ab_clips.get_pair_source_info needs to resolve without
    raising — an exception there would make the whole enrichment block fall
    back to nulls, hiding whatever this test is meant to prove.

    Args:
        tmp_dir: Directory to create observations.db in.
        run_id: Run identifier shared by the pairs row and both sources rows.
        concert_date: ISO concert date to seed on the rows.
        lb_a: First LB number of the pair.
        lb_b: Second LB number of the pair.
        secondary_cols: When False, omit the windowed_frac/hiss_median columns
            entirely, reproducing an observations.db written before they were
            added — the route probes for them with PRAGMA table_info.

    Returns:
        Path to the created observations.db file.
    """
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
        "concert_date TEXT NOT NULL, lb_a INTEGER, lb_b INTEGER, "
        "human_judgment TEXT, human_notes TEXT, "
        "lb_says_same INTEGER, lb_relation_text TEXT"
        + (", windowed_frac REAL, hiss_median REAL)" if secondary_cols else ")")
    )
    conn.execute(
        "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, human_judgment, "
        "human_notes, lb_says_same, lb_relation_text"
        + (", windowed_frac, hiss_median) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
           if secondary_cols else ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
        (run_id, concert_date, lb_a, lb_b, "confirmed_same", "clean match", 1,
         "LB page lists these as the same recording")
        + ((0.83, 0.71) if secondary_cols else ()),
    )
    conn.execute(
        "CREATE TABLE sources (concert_date TEXT, run_id TEXT, lb_number INTEGER, "
        "trim_head_sec REAL, speed_kind TEXT, speed_ppm REAL, "
        "perf_dur_sec REAL, total_dur_sec REAL, folder_name TEXT)"
    )
    for lb in (lb_a, lb_b):
        conn.execute(
            "INSERT INTO sources (concert_date, run_id, lb_number, trim_head_sec, "
            "speed_kind, speed_ppm, perf_dur_sec, total_dur_sec, folder_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (concert_date, run_id, lb, 0.0, "reference", 0.0, 100.0, 110.0,
             f"lb{lb}"),
        )
    conn.commit()
    conn.close()
    return obs_path


def test_pairs_route_live_enrichment_carries_lb_says_same(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO tapematch_pairs "
            "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
            " similarity_pct, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("1991-01-01", 10, 20, 0.9, 0.95, 0.8, 1, 100, "20260101_000000"),
        )
        conn.commit()
        obs_path = _make_enriched_pairs_db(
            tmp_dir, "20260101_000000", "1991-01-01", 10, 20
        )
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path
        )

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            pair = body["pairs"][0]
            # human_judgment only gets set by the same live-read block that sets
            # lb_says_same/lb_relation_text, so a populated value here proves the
            # enrichment block actually ran rather than failing silently to null.
            assert pair["human_judgment"] == "confirmed_same"
            assert pair["lb_says_same"] is True
            assert pair["lb_relation_text"] == (
                "LB page lists these as the same recording"
            )
            # Secondary-evidence metrics ride the same live read (README §8d).
            assert pair["windowed_frac"] == 0.83
            assert pair["hiss_median"] == 0.71
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pairs_route_enrichment_survives_missing_secondary_columns(monkeypatch):
    """An observations.db predating windowed_frac/hiss_median still enriches.

    The two metrics come back null, but the rest of the live read
    (human_judgment, lb_says_same) must survive — a hard SELECT on the absent
    columns would raise and collapse the whole block to nulls.
    """
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO tapematch_pairs "
            "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
            " similarity_pct, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("1991-01-01", 10, 20, 0.9, 0.95, 0.8, 1, 100, "20260101_000000"),
        )
        conn.commit()
        obs_path = _make_enriched_pairs_db(
            tmp_dir, "20260101_000000", "1991-01-01", 10, 20, secondary_cols=False
        )
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path
        )

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1991-01-01")
            assert resp.status_code == 200
            pair = resp.get_json()["pairs"][0]
            assert pair["human_judgment"] == "confirmed_same"
            assert pair["lb_says_same"] is True
            assert pair["windowed_frac"] is None
            assert pair["hiss_median"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pairs_route_unknown_date_returns_empty_list_not_error():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1900-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body == {"date": "1900-01-01", "run_id": None, "pairs": []}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _make_sources_db(tmp_dir, concert_date, rows, runs=("20260101_000000",),
                     speed_cols=True):
    """Create an observations.db with a 'sources' table for the speed strip.

    Args:
        tmp_dir: Directory to create observations.db in.
        concert_date: ISO concert date to seed the rows on.
        rows: Iterable of (lb_number, speed_kind, speed_ppm) tuples, written
            once per run_id in *runs* so multi-run dates can be exercised.
        runs: Run ids to seed, in any order — the route must pick the max.
        speed_cols: When False, omit speed_kind/speed_ppm entirely,
            reproducing an observations.db written before they were added.

    Returns:
        Path to the created observations.db file.
    """
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE sources (concert_date TEXT, run_id TEXT, lb_number INTEGER, "
        "family_id TEXT, folder_name TEXT, lag_ref_lb INTEGER"
        + (", speed_kind TEXT, speed_ppm REAL)" if speed_cols else ")")
    )
    for run_id in runs:
        for lb, kind, ppm in rows:
            conn.execute(
                "INSERT INTO sources (concert_date, run_id, lb_number, family_id, "
                "folder_name, lag_ref_lb"
                + (", speed_kind, speed_ppm) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                   if speed_cols else ") VALUES (?, ?, ?, ?, ?, ?)"),
                (concert_date, run_id, lb, "F1", f"lb{lb}", 10)
                + ((kind, ppm) if speed_cols else ()),
            )
    conn.commit()
    conn.close()
    return obs_path


def test_sources_route_returns_latest_runs_speed_rows(monkeypatch):
    """The strip's data comes from the newest run, not the oldest one seeded."""
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_sources_db(
            tmp_dir, "1991-01-01",
            [(10, "reference", 0.0), (20, "constant-speed-offset", -1512.0)],
            runs=("20260101_000000", "20260201_000000"),
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/sources?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["run_id"] == "20260201_000000"
            # One row per LB — the older run's duplicate rows must not appear.
            assert [s["lb_number"] for s in body["sources"]] == [10, 20]
            assert body["sources"][1]["speed_kind"] == "constant-speed-offset"
            assert body["sources"][1]["speed_ppm"] == -1512.0
            assert body["sources"][0]["family_id"] == "F1"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sources_route_survives_missing_speed_columns(monkeypatch):
    """A pre-speed_ppm observations.db nulls those fields, keeps the rest."""
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_sources_db(
            tmp_dir, "1991-01-01", [(10, None, None)], speed_cols=False,
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/sources?date=1991-01-01")
            assert resp.status_code == 200
            source = resp.get_json()["sources"][0]
            assert source["lb_number"] == 10
            assert source["speed_kind"] is None
            assert source["speed_ppm"] is None
            assert source["folder_name"] == "lb10"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sources_route_unknown_date_is_empty_not_error(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_sources_db(tmp_dir, "1991-01-01", [(10, "reference", 0.0)])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/sources?date=1900-01-01")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "date": "1900-01-01", "run_id": None, "sources": [],
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sources_route_no_observations_db_is_empty(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "absent.db"),
        )
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/sources?date=1991-01-01")
            assert resp.status_code == 200
            assert resp.get_json()["sources"] == []
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sources_route_missing_date_param_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            assert client.get("/api/tapematch/sources").status_code == 400
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pairs_route_missing_date_param_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs")
            assert resp.status_code == 400
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/analysis ──────────────────────────────────────────────


def _make_obs_db_with_run(tmp_dir, run_id, concert_date, archive_dir):
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
        "n_sources_ran INTEGER, archive_dir TEXT)"
    )
    conn.execute(
        "INSERT INTO runs (run_id, concert_date, n_sources_ran, archive_dir) "
        "VALUES (?, ?, ?, ?)",
        (run_id, concert_date, 2, str(archive_dir)),
    )
    conn.commit()
    conn.close()
    return obs_path


def test_analysis_route_reads_verdict_and_full_text(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        run_dir = os.path.join(tmp_dir, "run_archive")
        os.makedirs(run_dir, exist_ok=True)
        analysis_text = (
            "# Analysis — 1991-01-01 — Nowhere\n\n"
            "## Verdict: 2 recordings — 2 families — result needs review — "
            "reason text\n"
        )
        with open(os.path.join(run_dir, "analysis.md"), "w", encoding="utf-8") as fh:
            fh.write(analysis_text)

        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", run_dir
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/analysis?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["date"] == "1991-01-01"
            assert body["run_id"] == "20260101_000000"
            assert body["verdict"] == {"needs_review": True, "reason": "reason text"}
            assert body["analysis_md"] == analysis_text
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_analysis_route_missing_analysis_md_is_null(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        run_dir = os.path.join(tmp_dir, "run_archive_no_analysis")
        os.makedirs(run_dir, exist_ok=True)

        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", run_dir
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/analysis?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["run_id"] == "20260101_000000"
            assert body["verdict"] is None
            assert body["analysis_md"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_analysis_route_unknown_date_is_all_null(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", os.path.join(tmp_dir, "unused")
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/analysis?date=1900-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body == {
                "date": "1900-01-01", "run_id": None, "verdict": None,
                "analysis_md": None,
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_analysis_route_no_observations_db_is_all_null(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "does_not_exist.db"),
        )

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/analysis?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body == {
                "date": "1991-01-01", "run_id": None, "verdict": None,
                "analysis_md": None,
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/report (§11) ──────────────────────────────────────────


def test_report_route_reads_text_and_run_dir(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        run_dir = os.path.join(tmp_dir, "run_archive")
        os.makedirs(run_dir, exist_ok=True)
        report_text = (
            "# tapematch session — 1991-01-01 — Nowhere\n"
            "*Generated: 2026-06-04 13:20:30*\n\n"
            "## Coverage\nDB entries: **2** | Found on disk: **2**\n"
        )
        with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write(report_text)

        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", run_dir
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/report?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["date"] == "1991-01-01"
            assert body["run_id"] == "20260101_000000"
            assert body["run_dir"] == run_dir
            assert body["report_md"] == report_text
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_report_route_missing_report_md_keeps_run_identity(monkeypatch):
    """A run that never wrote report.md still names itself — the sheet says
    which run it looked in rather than pretending the date has no run."""
    db_path, tmp_dir = _make_db()
    try:
        run_dir = os.path.join(tmp_dir, "run_archive_no_report")
        os.makedirs(run_dir, exist_ok=True)
        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", run_dir
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/report?date=1991-01-01")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["run_id"] == "20260101_000000"
            assert body["run_dir"] == run_dir
            assert body["report_md"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_report_route_unknown_date_and_absent_db_are_all_null(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db_with_run(
            tmp_dir, "20260101_000000", "1991-01-01", os.path.join(tmp_dir, "unused")
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        with _AppClient(db_path) as client:
            body = client.get("/api/tapematch/report?date=1900-01-01").get_json()
            assert body == {
                "date": "1900-01-01", "run_id": None, "run_dir": None,
                "report_md": None,
            }

        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "does_not_exist.db"),
        )
        with _AppClient(db_path) as client:
            body = client.get("/api/tapematch/report?date=1991-01-01").get_json()
            assert body == {
                "date": "1991-01-01", "run_id": None, "run_dir": None,
                "report_md": None,
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/runs + /api/tapematch/run_snapshot (§12) ─────────────


def _make_obs_db_with_two_runs(tmp_dir):
    """Two runs of one date: the head run merges the pair the base split."""
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
        "n_sources_db INTEGER, n_sources_found INTEGER, n_sources_ran INTEGER, "
        "n_families INTEGER, duration_sec REAL, run_at TEXT, archive_dir TEXT)"
    )
    conn.execute(
        "CREATE TABLE sources (id INTEGER PRIMARY KEY, run_id TEXT, concert_date TEXT, "
        "lb_number INTEGER, family_id INTEGER, folder_name TEXT, speed_kind TEXT, "
        "speed_ppm REAL)"
    )
    conn.execute(
        "CREATE TABLE pairs (id INTEGER PRIMARY KEY, run_id TEXT, concert_date TEXT, "
        "lb_a INTEGER, lb_b INTEGER, corr REAL, emb_score REAL, windowed_frac REAL, "
        "hiss_median REAL, fp_score REAL, family_id_a INTEGER, family_id_b INTEGER, "
        "tapematch_verdict TEXT, human_judgment TEXT)"
    )
    for run_id, n_fam, fam_b, verdict, corr in (
        ("20260101_000000", 2, 2, "different_family", 0.11),
        ("20260202_000000", 1, 1, "same_family", 0.61),
    ):
        conn.execute(
            "INSERT INTO runs (run_id, concert_date, n_sources_db, n_sources_found, "
            "n_sources_ran, n_families, duration_sec, run_at) "
            "VALUES (?, '1991-01-01', 2, 2, 2, ?, 12.5, '2026-01-01T00:00:00')",
            (run_id, n_fam),
        )
        conn.execute(
            "INSERT INTO sources (run_id, concert_date, lb_number, family_id, folder_name, "
            "speed_kind, speed_ppm) VALUES (?, '1991-01-01', 101, 1, 'a', 'reference', 0)",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO sources (run_id, concert_date, lb_number, family_id, folder_name, "
            "speed_kind, speed_ppm) VALUES (?, '1991-01-01', 202, ?, 'b', 'aligned', 12)",
            (run_id, fam_b),
        )
        conn.execute(
            "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, corr, family_id_a, "
            "family_id_b, tapematch_verdict, human_judgment) "
            "VALUES (?, '1991-01-01', 101, 202, ?, 1, ?, ?, 'uncertain')",
            (run_id, corr, fam_b, verdict),
        )
    conn.commit()
    conn.close()
    return obs_path


def test_runs_route_lists_every_run_newest_first(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db_with_two_runs(tmp_dir)
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        with _AppClient(db_path) as client:
            body = client.get("/api/tapematch/runs?date=1991-01-01").get_json()
            assert [r["run_id"] for r in body["runs"]] == [
                "20260202_000000", "20260101_000000",
            ]
            assert body["runs"][0]["n_families"] == 1
            assert body["runs"][1]["n_families"] == 2
            assert body["runs"][0]["n_sources_ran"] == 2

            # Unknown date is empty, not an error.
            assert client.get("/api/tapematch/runs?date=1900-01-01").get_json() == {
                "date": "1900-01-01", "runs": [],
            }
            assert client.get("/api/tapematch/runs").status_code == 400
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_run_snapshot_returns_that_run_only(monkeypatch):
    """The snapshot must be the named run's own rows — the whole point of §12
    is comparing two runs, which a latest-run query could never express."""
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db_with_two_runs(tmp_dir)
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        with _AppClient(db_path) as client:
            base = client.get(
                "/api/tapematch/run_snapshot?date=1991-01-01&run_id=20260101_000000"
            ).get_json()
            head = client.get(
                "/api/tapematch/run_snapshot?date=1991-01-01&run_id=20260202_000000"
            ).get_json()

            assert base["run"]["n_families"] == 2
            assert head["run"]["n_families"] == 1
            assert [s["lb_number"] for s in base["sources"]] == [101, 202]
            assert base["sources"][1]["family_id"] == 2
            assert head["sources"][1]["family_id"] == 1
            assert len(base["pairs"]) == 1 and len(head["pairs"]) == 1
            assert base["pairs"][0]["tapematch_verdict"] == "different_family"
            assert head["pairs"][0]["tapematch_verdict"] == "same_family"
            assert base["pairs"][0]["corr"] == 0.11
            assert head["pairs"][0]["corr"] == 0.61
            # The judgment rides along for §12.5's reconciliation.
            assert head["pairs"][0]["human_judgment"] == "uncertain"
            # Columns this observations.db doesn't have degrade to null.
            assert head["pairs"][0]["windowed_frac"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_run_snapshot_unknown_run_and_missing_params(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db_with_two_runs(tmp_dir)
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        with _AppClient(db_path) as client:
            body = client.get(
                "/api/tapematch/run_snapshot?date=1991-01-01&run_id=nope"
            ).get_json()
            assert body["run"] is None
            assert body["sources"] == [] and body["pairs"] == []
            assert client.get(
                "/api/tapematch/run_snapshot?date=1991-01-01"
            ).status_code == 400
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_report_route_missing_date_param_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/report")
            assert resp.status_code == 400
            assert resp.get_json()["error"] == "missing_date"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/dates ─────────────────────────────────────────────────


def _seed_pairs(conn, rows):
    conn.executemany(
        "INSERT INTO tapematch_pairs "
        "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
        " similarity_pct, run_id) VALUES (?, ?, ?, NULL, NULL, NULL, 1, 90, ?)",
        rows,
    )
    conn.commit()


def _make_obs_db_with_runs(tmp_dir, runs):
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
        "n_sources_ran INTEGER, archive_dir TEXT)"
    )
    conn.executemany(
        "INSERT INTO runs (run_id, concert_date, n_sources_ran, archive_dir) "
        "VALUES (?, ?, 2, ?)",
        runs,
    )
    conn.commit()
    conn.close()
    return obs_path


def test_dates_route_aggregates_pairs_locations_and_analysis(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_pairs(conn, [
            ("1991-01-01", 10, 20, "20260101_000000"),
            ("1991-01-01", 10, 30, "20260101_000000"),
            ("1991-01-01", 20, 30, "20260101_000000"),
            ("1991-02-02", 40, 50, "20260102_000000"),
        ])
        # date_str is deliberately US-format (real entries data is "1/1/91",
        # never ISO) — the location lookup must go via lb_number, not date.
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, location) VALUES (?, ?, ?)",
            (10, "1/1/91", "Hamburg, Germany"),
        )
        conn.commit()

        # Run dir with a needs-review analysis.md for 1991-01-01; the
        # 1991-02-02 run dir exists but holds no analysis.md.
        run_dir_1 = os.path.join(tmp_dir, "run1")
        run_dir_2 = os.path.join(tmp_dir, "run2")
        os.makedirs(run_dir_1)
        os.makedirs(run_dir_2)
        with open(os.path.join(run_dir_1, "analysis.md"), "w", encoding="utf-8") as fh:
            fh.write(
                "## Verdict: 3 recordings — 1 family — result needs review — reason\n"
            )
        obs_path = _make_obs_db_with_runs(tmp_dir, [
            ("20260101_000000", "1991-01-01", run_dir_1),
            ("20260102_000000", "1991-02-02", run_dir_2),
        ])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/dates")
            assert resp.status_code == 200
            body = resp.get_json()
            # Sorted date DESC.
            assert [d["date"] for d in body["dates"]] == ["1991-02-02", "1991-01-01"]
            d_feb, d_jan = body["dates"]
            assert d_jan == {
                "date": "1991-01-01", "run_id": "20260101_000000",
                "n_lbs": 3, "n_pairs": 3, "has_analysis": True,
                "needs_review": True, "location": "Hamburg, Germany",
                "curated": False, "curated_at": None,
            }
            assert d_feb == {
                "date": "1991-02-02", "run_id": "20260102_000000",
                "n_lbs": 2, "n_pairs": 1, "has_analysis": False,
                "needs_review": None, "location": None,
                "curated": False, "curated_at": None,
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dates_route_missing_observations_db_nulls_analysis_fields(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_pairs(conn, [("1991-01-01", 10, 20, "20260101_000000")])
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "does_not_exist.db"),
        )

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/dates")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["dates"] == [
                {
                    "date": "1991-01-01", "run_id": "20260101_000000",
                    "n_lbs": 2, "n_pairs": 1, "has_analysis": None,
                    "needs_review": None, "location": None,
                    "curated": False, "curated_at": None,
                }
            ]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dates_route_no_synced_pairs_is_empty_list(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "does_not_exist.db"),
        )
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/dates")
            assert resp.status_code == 200
            assert resp.get_json() == {"dates": []}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/tapematch/crawl/status ──────────────────────────────────────────


def test_crawl_status_route_not_running_no_runs_no_log(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        runs_dir = os.path.join(tmp_dir, "no_runs_here")  # does not exist

        def _fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(app_module, "TAPEMATCH_RUNS_DIR", _paths.Path(runs_dir))

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/crawl/status")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body == {
                "running": False, "pid": None, "runs_on_disk": 0,
                "distinct_dates": 0, "log_tail": [],
            }
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crawl_status_route_running_with_runs_and_log_tail(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        runs_dir = os.path.join(tmp_dir, "tapematch_runs")
        os.makedirs(os.path.join(runs_dir, "20260101_000000_1991-01-01"))
        os.makedirs(os.path.join(runs_dir, "20260102_000000_1991-01-01"))
        os.makedirs(os.path.join(runs_dir, "20260103_000000_1991-02-02"))
        with open(os.path.join(tmp_dir, "crawl.log"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(f"line {i}" for i in range(1, 8)) + "\n")

        def _fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="4242\n", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(app_module, "TAPEMATCH_RUNS_DIR", _paths.Path(runs_dir))

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/crawl/status")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["running"] is True
            assert body["pid"] == 4242
            assert body["runs_on_disk"] == 3
            assert body["distinct_dates"] == 2
            assert body["log_tail"] == [f"line {i}" for i in range(3, 8)]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── POST /api/tapematch/pairs/judgment ───────────────────────────────────────


def _make_pairs_db(tmp_dir: str, run_id: str, concert_date: str, lb_a: int, lb_b: int) -> str:
    """Create an observations.db with a single 'pairs' row for judgment-route tests.

    Only the columns the judgment route touches are created (id, run_id,
    concert_date, lb_a, lb_b, human_judgment, human_notes) — the real schema in
    tools/tapematch/tapematch_session.py has many more, all irrelevant here.

    Args:
        tmp_dir: Directory to create observations.db in.
        run_id: Run identifier to seed on the row.
        concert_date: ISO concert date to seed on the row.
        lb_a: First LB number of the pair.
        lb_b: Second LB number of the pair.

    Returns:
        Path to the created observations.db file.
    """
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
        "concert_date TEXT NOT NULL, lb_a INTEGER, lb_b INTEGER, "
        "human_judgment TEXT, human_notes TEXT)"
    )
    conn.execute(
        "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b) VALUES (?, ?, ?, ?)",
        (run_id, concert_date, lb_a, lb_b),
    )
    conn.commit()
    conn.close()
    return obs_path


def test_judgment_route_sets_and_clears_judgment(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_pairs_db(tmp_dir, "20260101_000000", "1991-01-01", 10, 20)
        monkeypatch.setattr(app_module, "TAPEMATCH_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/pairs/judgment",
                json={
                    "date": "1991-01-01", "lb_a": 10, "lb_b": 20,
                    "run_id": "20260101_000000", "judgment": "confirmed_same",
                    "notes": "clean match",
                },
            )
            assert resp.status_code == 200
            assert resp.get_json() == {
                "ok": True, "rows_updated": 1,
                "judgment": "confirmed_same", "notes": "clean match",
            }

            conn = sqlite3.connect(obs_path)
            row = conn.execute(
                "SELECT human_judgment, human_notes FROM pairs WHERE lb_a=10 AND lb_b=20"
            ).fetchone()
            conn.close()
            assert row == ("confirmed_same", "clean match")

            # Clearing: judgment=null (notes omitted) should null out both columns.
            resp2 = client.post(
                "/api/tapematch/pairs/judgment",
                json={
                    "date": "1991-01-01", "lb_a": 10, "lb_b": 20,
                    "run_id": "20260101_000000", "judgment": None,
                },
            )
            assert resp2.status_code == 200
            assert resp2.get_json() == {
                "ok": True, "rows_updated": 1, "judgment": None, "notes": None,
            }

            conn = sqlite3.connect(obs_path)
            row2 = conn.execute(
                "SELECT human_judgment, human_notes FROM pairs WHERE lb_a=10 AND lb_b=20"
            ).fetchone()
            conn.close()
            assert row2 == (None, None)
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_judgment_route_bad_judgment_is_400(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_pairs_db(tmp_dir, "20260101_000000", "1991-01-01", 10, 20)
        monkeypatch.setattr(app_module, "TAPEMATCH_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/pairs/judgment",
                json={
                    "date": "1991-01-01", "lb_a": 10, "lb_b": 20,
                    "run_id": "20260101_000000", "judgment": "not_a_real_judgment",
                },
            )
            assert resp.status_code == 400
            assert resp.get_json() == {"error": "bad_judgment"}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_judgment_route_missing_fields_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/pairs/judgment",
                json={"date": "1991-01-01", "lb_a": 10},
            )
            assert resp.status_code == 400
            assert resp.get_json() == {"error": "missing_fields"}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_judgment_route_pair_not_found_is_404(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_pairs_db(tmp_dir, "20260101_000000", "1991-01-01", 10, 20)
        monkeypatch.setattr(app_module, "TAPEMATCH_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/pairs/judgment",
                json={
                    "date": "1991-01-01", "lb_a": 10, "lb_b": 99,
                    "run_id": "20260101_000000", "judgment": "uncertain",
                },
            )
            assert resp.status_code == 404
            assert resp.get_json() == {"error": "pair_not_found"}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── POST /api/tapematch/dates/accept ─────────────────────────────────────────


def _make_accept_db(tmp_dir, run_id, concert_date, judgments):
    """Create an observations.db with runs + pairs rows for accept-route tests.

    Args:
        tmp_dir: Directory to create observations.db in.
        run_id: Run identifier seeded on both the run and its pairs.
        concert_date: ISO concert date seeded on both.
        judgments: One human_judgment value (or None) per seeded pair; pairs
            are numbered LB 10/20, 10/30, 20/30… in order.

    Returns:
        Path to the created observations.db file.
    """
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT NOT NULL, "
        "n_sources_ran INTEGER, n_families INTEGER, archive_dir TEXT)"
    )
    conn.execute(
        "INSERT INTO runs (run_id, concert_date, n_sources_ran, n_families, archive_dir) "
        "VALUES (?, ?, 3, 2, ?)",
        (run_id, concert_date, os.path.join(tmp_dir, "run1")),
    )
    conn.execute(
        "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
        "concert_date TEXT NOT NULL, lb_a INTEGER, lb_b INTEGER, "
        "human_judgment TEXT, human_notes TEXT)"
    )
    lbs = [(10, 20), (10, 30), (20, 30)]
    for (lb_a, lb_b), judgment in zip(lbs, judgments):
        conn.execute(
            "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, human_judgment) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, concert_date, lb_a, lb_b, judgment),
        )
    conn.commit()
    conn.close()
    return obs_path


def test_accept_route_records_date_and_counts_judgments(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_accept_db(
            tmp_dir, "20260101_000000", "1991-01-01",
            ["confirmed_same", None, "lb_wrong"],
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/dates/accept",
                json={"date": "1991-01-01", "run_id": "20260101_000000"},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["ok"] is True
            assert body["date"] == "1991-01-01"
            assert body["run_id"] == "20260101_000000"
            # Counted server-side from pairs.human_judgment, not from the client.
            assert body["n_judged"] == 2
            assert body["n_families"] == 2
            assert body["accepted_at"]

            # The record lands in the APP DB, not observations.db — nothing in
            # the tapematch pipeline reads it and a running batch must not be
            # able to block an accept.
            row = db.get_connection(db_path).execute(
                "SELECT run_id, n_judged, n_families FROM tapematch_date_curation "
                "WHERE concert_date = '1991-01-01'"
            ).fetchone()
            assert tuple(row) == ("20260101_000000", 2, 2)

            obs = sqlite3.connect(obs_path)
            names = {r[0] for r in obs.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            obs.close()
            assert names - {"sqlite_sequence"} == {"runs", "pairs"}, \
                "observations.db schema must be untouched"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_accept_route_resolves_run_id_when_omitted(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_accept_db(
            tmp_dir, "20260101_000000", "1991-01-01", [None, None, None],
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/dates/accept", json={"date": "1991-01-01"})
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["run_id"] == "20260101_000000"
            # §10.5: a date with nothing judged is still acceptable.
            assert body["n_judged"] == 0
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_accept_route_reaccept_replaces_the_row(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_accept_db(
            tmp_dir, "20260101_000000", "1991-01-01", [None, None, None],
        )
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            first = client.post("/api/tapematch/dates/accept", json={"date": "1991-01-01"})
            assert first.get_json()["n_judged"] == 0

            obs = sqlite3.connect(obs_path)
            obs.execute("UPDATE pairs SET human_judgment = 'uncertain' WHERE lb_a = 10")
            obs.commit()
            obs.close()

            second = client.post(
                "/api/tapematch/dates/accept",
                json={"date": "1991-01-01", "note": "revisited"},
            )
            assert second.get_json()["n_judged"] == 2

            rows = db.get_connection(db_path).execute(
                "SELECT n_judged, note FROM tapematch_date_curation "
                "WHERE concert_date = '1991-01-01'"
            ).fetchall()
            assert [tuple(r) for r in rows] == [(2, "revisited")]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_accept_route_missing_date_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/dates/accept", json={})
            assert resp.status_code == 400
            assert resp.get_json() == {"error": "missing_fields"}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_accept_route_no_observations_db_is_404(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "does_not_exist.db"),
        )
        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/dates/accept", json={"date": "1991-01-01"})
            assert resp.status_code == 404
            assert resp.get_json() == {"error": "no_run"}
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dates_route_reports_accepted_dates_as_curated(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_pairs(conn, [
            ("1991-01-01", 10, 20, "20260101_000000"),
            ("1991-02-02", 40, 50, "20260102_000000"),
        ])
        obs_path = _make_accept_db(
            tmp_dir, "20260101_000000", "1991-01-01", ["confirmed_same", None, None],
        )
        obs_conn = sqlite3.connect(obs_path)
        obs_conn.execute(
            "INSERT INTO runs (run_id, concert_date, n_sources_ran, n_families, archive_dir) "
            "VALUES (?, ?, 2, 1, ?)",
            ("20260102_000000", "1991-02-02", os.path.join(tmp_dir, "run2")),
        )
        obs_conn.commit()
        obs_conn.close()
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            # Before accepting, tapematch_date_curation is empty — not an error.
            before = client.get("/api/tapematch/dates").get_json()["dates"]
            assert all(d["curated"] is False for d in before)
            assert all(d["curated_at"] is None for d in before)

            client.post(
                "/api/tapematch/dates/accept",
                json={"date": "1991-01-01", "run_id": "20260101_000000"},
            )

            after = {d["date"]: d for d in client.get("/api/tapematch/dates").get_json()["dates"]}
            assert after["1991-01-01"]["curated"] is True
            assert after["1991-01-01"]["curated_at"]
            assert after["1991-02-02"]["curated"] is False
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── POST /api/tapematch/crawl/start ──────────────────────────────────────────


def test_crawl_start_route_success(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            _paths.Path(tmp_dir) / "observations.db",
        )
        captured = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(
                cmd, returncode=0, stdout="Started (pid 4242)\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/crawl/start",
                json={"min_entries": 5, "allow_missing": True},
            )
            assert resp.status_code == 200
            assert resp.get_json() == {"ok": True, "message": "Started (pid 4242)"}
            assert captured["cmd"][0].endswith("crawl_start.sh")
            assert captured["cmd"][1:] == ["--min-entries", "5", "--allow-missing"]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crawl_start_route_already_running_is_409(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            _paths.Path(tmp_dir) / "observations.db",
        )

        def _fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="already running (pid 111)\n"
            )

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/crawl/start", json={})
            assert resp.status_code == 409
            body = resp.get_json()
            assert body["error"] == "already_running"
            assert "already running" in body["message"]
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crawl_start_route_bad_min_entries_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.post(
                "/api/tapematch/crawl/start", json={"min_entries": "not-an-int"}
            )
            assert resp.status_code == 400
            assert resp.get_json()["error"] == "bad_request"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crawl_start_route_subprocess_error_is_500(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            _paths.Path(tmp_dir) / "observations.db",
        )

        def _fake_run(cmd, **kwargs):
            raise FileNotFoundError("crawl_start.sh not found")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/crawl/start", json={})
            assert resp.status_code == 500
            assert resp.get_json()["error"] == "internal_error"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── POST /api/tapematch/crawl/stop ───────────────────────────────────────────


def test_crawl_stop_route_success(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            _paths.Path(tmp_dir) / "observations.db",
        )
        captured = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="Stopped\n", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/crawl/stop")
            assert resp.status_code == 200
            assert resp.get_json() == {"ok": True, "message": "Stopped"}
            assert captured["cmd"][0].endswith("crawl_stop.sh")
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crawl_stop_route_subprocess_error_is_500(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            _paths.Path(tmp_dir) / "observations.db",
        )

        def _fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=15)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with _AppClient(db_path) as client:
            resp = client.post("/api/tapematch/crawl/stop")
            assert resp.status_code == 500
            assert resp.get_json()["error"] == "internal_error"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
