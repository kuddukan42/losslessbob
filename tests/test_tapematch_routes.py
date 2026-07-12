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
                    "ab_eligible": None,
                }
            ]
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
            }
            assert d_feb == {
                "date": "1991-02-02", "run_id": "20260102_000000",
                "n_lbs": 2, "n_pairs": 1, "has_analysis": False,
                "needs_review": None, "location": None,
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
