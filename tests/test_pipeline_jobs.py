"""Tests for backend/job_progress.py + the Phase 2 fetch/ranker routes and
workers (TODO-306). Everything network- and audio-touching is monkeypatched:
zero network, zero audio decode.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

import backend.db as db
import backend.paths as _paths
from backend.job_progress import JobState, JobStopped


def test_try_begin_claims_once():
    job = JobState("test-job")
    assert job.try_begin(stage="queued") is True
    assert job.snapshot()["running"] is True
    assert job.snapshot()["stage"] == "queued"


def test_try_begin_twice_fails():
    job = JobState("test-job")
    assert job.try_begin() is True
    assert job.try_begin() is False


def test_try_begin_after_finish_succeeds():
    job = JobState("test-job")
    job.try_begin()
    job.finish()
    assert job.try_begin() is True


def test_finish_clears_running_and_stop_flag():
    job = JobState("test-job")
    job.try_begin()
    job.stop()
    job.finish(stage="done")
    snap = job.snapshot()
    assert snap["running"] is False
    assert snap["stop_requested"] is False
    assert snap["stage"] == "done"


def test_update_and_bump():
    job = JobState("test-job")
    job.try_begin(total=10)
    job.update(current="item-1")
    job.bump("done")
    job.bump("errors", 2)
    snap = job.snapshot()
    assert snap["current"] == "item-1"
    assert snap["done"] == 1
    assert snap["errors"] == 2


def test_check_stop_raises_after_stop():
    job = JobState("test-job")
    job.try_begin()
    job.check_stop()  # no-op, not requested yet
    job.stop()
    with pytest.raises(JobStopped):
        job.check_stop()


def test_sleep_with_stop_flag_returns_quickly():
    job = JobState("test-job")
    job.try_begin()
    job.stop()
    start = time.monotonic()
    with pytest.raises(JobStopped):
        job.sleep(30, slice_s=0.1)
    assert time.monotonic() - start < 0.5


def test_sleep_completes_without_stop():
    job = JobState("test-job")
    job.try_begin()
    job.sleep(0.05, slice_s=0.02)  # should not raise


# ── Flask routes (fetch + ranker) ────────────────────────────────────────


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_pipeline_jobs_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


class _AppClient:
    """Wires backend.app's create_app() to a temp DB path (see test_tapematch_routes.py)."""

    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self._orig_db_path = _paths.DB_PATH
        self._orig_module_db_path = getattr(db, "DB_PATH", None)
        _paths.DB_PATH = self.db_path
        db.DB_PATH = self.db_path
        from backend.app import create_app
        self.app = create_app()
        return self.app.test_client()

    def __exit__(self, *exc):
        _paths.DB_PATH = self._orig_db_path
        if self._orig_module_db_path is not None:
            db.DB_PATH = self._orig_module_db_path


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_olof_fetch_route_200_then_409_and_stop(monkeypatch):
    import backend.olof_fetcher as olof_fetcher

    release = threading.Event()

    def _slow_discover(corpus, pages_dir, refresh, persist):
        release.wait(timeout=2.0)
        return []

    monkeypatch.setattr(olof_fetcher, "_discover", _slow_discover)

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp1 = client.post("/api/olof/fetch", json={"dry_run": True})
        assert resp1.status_code == 200
        assert resp1.get_json()["status"] == "started"

        resp2 = client.post("/api/olof/fetch", json={"dry_run": True})
        assert resp2.status_code == 409

        status = client.get("/api/olof/fetch/status").get_json()
        assert status["running"] is True

        stop_resp = client.post("/api/olof/fetch/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.get_json()["stop_requested"] is True

        release.set()
        assert _wait_until(lambda: not olof_fetcher.get_status()["running"])


def test_bobserve_fetch_route_200_then_409(monkeypatch):
    import backend.bobserve_fetcher as bobserve_fetcher

    release = threading.Event()

    def _fake_fetch(url, retries=3):
        release.wait(timeout=2.0)
        return None  # discovery treats a failed period fetch as "no ids this year"

    monkeypatch.setattr(bobserve_fetcher, "_fetch", _fake_fetch)

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp1 = client.post(
            "/api/bobserve/fetch",
            json={"start_year": 2022, "end_year": 2022, "dry_run": True},
        )
        assert resp1.status_code == 200
        resp2 = client.post(
            "/api/bobserve/fetch",
            json={"start_year": 2022, "end_year": 2022, "dry_run": True},
        )
        assert resp2.status_code == 409

        release.set()
        assert _wait_until(lambda: not bobserve_fetcher.get_status()["running"])


def test_ranker_scan_route_empty_backlog_is_noop(monkeypatch):
    """An empty collection means plan_scan().planned == 0 -> 'noop', no thread,
    and the claim is released immediately (not left wedged 'running')."""
    import backend.ranker_jobs as ranker_jobs

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp = client.post("/api/ranker/scan", json={"mode": "backlog"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "noop"
        assert body["planned"] == 0
        assert ranker_jobs.get_status()["running"] is False


def test_ranker_rerank_route_409_during_scan(monkeypatch):
    import backend.ranker_jobs as ranker_jobs

    db_path, _tmp = _make_db()
    ranker_jobs._JOB.try_begin(stage="scanning")
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/ranker/rerank", json={})
            assert resp.status_code == 409
    finally:
        ranker_jobs._JOB.finish()


def _seed_collection(db_path, lbs):
    """Insert *lbs* as eligible (public, uncategorised) collection rows."""
    from concert_ranker.lb import repo

    conn = repo.connect(db_path)
    for lb in lbs:
        conn.execute(
            "INSERT OR REPLACE INTO my_collection(lb_number, folder_name, disk_path)"
            " VALUES(?, ?, ?)",
            (lb, f"lb{lb}", f"/nope/{lb}"),
        )
    conn.commit()
    return conn


def test_plan_scan_skips_folders_already_measured(monkeypatch):
    """TODO-311: a scoring-only config change must not re-measure the corpus.

    Metrics stored under the current extraction config are reused, so the plan
    contains only the folders that have none — even after `polarity` changes,
    which previously forked an empty scan and re-planned everything.
    """
    import backend.ranker_jobs as ranker_jobs
    from concert_ranker import config as cr_config
    from concert_ranker.lb import repo

    db_path, _tmp = _make_db()
    conn = _seed_collection(db_path, [1, 2, 3])

    first = ranker_jobs.plan_scan(mode="backlog", db_path=db_path)
    assert sorted(w[0] for w in first["worklist"]) == [1, 2, 3]

    # Two of the three get measured.
    for lb in (1, 2):
        repo.persist_recording(conn, first["scan_id"], lb, "SBD",
                               repo.build_metric_json({"crowd_snr_db": 1.0}))

    # A scoring-only config change lands.
    base = cr_config.default_config()
    tweaked = cr_config.Config(**dict(vars(base), polarity=dict(base.polarity, lr_corr=1)))
    monkeypatch.setattr(cr_config, "default_config", lambda: tweaked)

    second = ranker_jobs.plan_scan(mode="backlog", db_path=db_path)
    assert second["scan_id"] == first["scan_id"], "must append, not fork"
    assert second["reused_scan"] is True
    assert second["config_changed"] is False
    assert [w[0] for w in second["worklist"]] == [3]
    assert ranker_jobs.count_scan_backlog(conn) == 1  # pill agrees with `planned`


def test_plan_scan_adopts_metrics_stranded_in_a_sibling_scan():
    """Rows a stopped/older scan already measured are adopted, not re-measured
    (TODO-311) — ranking is per-scan_id, so they must land in the active scan."""
    import backend.ranker_jobs as ranker_jobs
    from concert_ranker import config as cr_config
    from concert_ranker.lb import repo

    db_path, _tmp = _make_db()
    conn = _seed_collection(db_path, [1, 2, 3])
    cfg = vars(cr_config.default_config())

    big = repo.create_scan(conn, config=cfg)
    for lb in (1, 3):
        repo.persist_recording(conn, big, lb, "SBD", repo.build_metric_json({"crowd_snr_db": 1.0}))
    stranded = repo.create_scan(conn, config=cfg)  # e.g. a fork that was stopped early
    repo.persist_recording(conn, stranded, 2, "AUD", repo.build_metric_json({"crowd_snr_db": 2.0}))

    plan = ranker_jobs.plan_scan(mode="backlog", db_path=db_path)
    assert plan["scan_id"] == big
    assert plan["planned"] == 0, "nothing left to measure — LB 2 was adopted"
    assert repo.done_lbs(conn, big) == {1, 2, 3}
    assert repo.load_metrics(conn, big)[2]["metrics"]["crowd_snr_db"] == 2.0
    assert ranker_jobs.count_scan_backlog(conn) == 0


def test_plan_scan_forks_on_a_real_extraction_change(monkeypatch):
    """A change to what gets measured still forks a new scan — old metrics are
    not valid under it."""
    import backend.ranker_jobs as ranker_jobs
    from concert_ranker import config as cr_config
    from concert_ranker.lb import repo

    db_path, _tmp = _make_db()
    conn = _seed_collection(db_path, [1])
    first = ranker_jobs.plan_scan(mode="backlog", db_path=db_path)
    repo.persist_recording(conn, first["scan_id"], 1, "SBD",
                           repo.build_metric_json({"crowd_snr_db": 1.0}))

    base = cr_config.default_config()
    monkeypatch.setattr(
        cr_config, "default_config",
        lambda: cr_config.Config(**dict(vars(base), bulk_sr=base.bulk_sr * 2)),
    )
    second = ranker_jobs.plan_scan(mode="backlog", db_path=db_path)
    assert second["scan_id"] != first["scan_id"]
    assert second["config_changed"] is True
    assert [w[0] for w in second["worklist"]] == [1]


def test_ranker_rerank_route_404_no_scans():
    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp = client.post("/api/ranker/rerank", json={})
        assert resp.status_code == 404


def test_derived_recompute_writes_run_records_and_stamps_version(monkeypatch):
    """The four /api/derived/recompute steps must record a refresh_step_runs
    row per step using the exact registry step_ids, and stamp the
    attribute_tapers version hash on success."""
    import backend.app as app_module

    db_path, _tmp = _make_db()

    def _trivial_run():
        return {"n": 1}

    fake_modules = {
        "tools.parse_lineage": _trivial_run,
        "tools.attribute_tapers": _trivial_run,
        "tools.compute_show_picks": _trivial_run,
        "backend.song_index": _trivial_run,
    }

    class _FakeModule:
        def __init__(self, fn):
            self.run = fn

    def _fake_import_module(name):
        if name in fake_modules:
            return _FakeModule(fake_modules[name])
        raise ImportError(name)

    monkeypatch.setattr(app_module.importlib, "import_module", _fake_import_module)

    with _AppClient(db_path) as client:
        resp = client.post("/api/derived/recompute")
        # Drain the SSE stream fully.
        resp.get_data(as_text=True)

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, status FROM refresh_step_runs ORDER BY id"
    ).fetchall()
    step_ids = [r["step_id"] for r in rows]
    assert step_ids == ["parse_lineage", "attribute_tapers", "compute_show_picks", "song_index"]
    assert all(r["status"] == "ok" for r in rows)
    assert db.get_meta("refresh_version_taper_aliases", db_path) is not None


# ── Pipeline refresh Phase 3: parser routes (TODO-306 / spec §3.3) ──────────


def test_olof_parse_route_writes_one_run_record(monkeypatch):
    """POST /api/olof/parse writes exactly one refresh_step_runs row for
    step_id='olof_parse' with the coverage summary as counters."""
    import backend.olof_parser as olof_parser

    fake_summary = {"pages_parsed": 3, "pages_ok": 3, "events_emitted": 5}
    monkeypatch.setattr(olof_parser, "run_parse", lambda file=None: fake_summary)

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp = client.post("/api/olof/parse", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["pages_parsed"] == 3

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, status FROM refresh_step_runs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["step_id"] == "olof_parse"
    assert rows[0]["status"] == "ok"


def test_olof_parse_route_409_while_fetch_running(monkeypatch):
    """A running olof-fetch job must block /api/olof/parse — parsing a
    half-written mirror directory would look like data loss."""
    import backend.olof_fetcher as olof_fetcher

    db_path, _tmp = _make_db()
    olof_fetcher._JOB.try_begin(stage="fetching")
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/olof/parse", json={})
            assert resp.status_code == 409
    finally:
        olof_fetcher._JOB.finish()

    conn = db.get_connection(db_path)
    rows = conn.execute("SELECT COUNT(*) AS n FROM refresh_step_runs").fetchall()
    assert rows[0]["n"] == 0


def test_olof_chronicle_parse_route_writes_one_run_record(monkeypatch):
    """POST /api/olof/chronicle_parse records a run under its OWN step_id —
    the chronicle corpus has a separate parser from olof_parse (TODO-309)."""
    import backend.olof_chronicle_parser as chronicle_parser

    fake_summary = {"years_parsed": 4, "pages_ok": 4, "appendix_events": 12}
    monkeypatch.setattr(chronicle_parser, "run_parse", lambda file=None: fake_summary)

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp = client.post("/api/olof/chronicle_parse", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["years_parsed"] == 4

    conn = db.get_connection(db_path)
    rows = conn.execute("SELECT step_id, status FROM refresh_step_runs").fetchall()
    assert len(rows) == 1
    assert rows[0]["step_id"] == "olof_chronicle_parse"
    assert rows[0]["status"] == "ok"


def test_olof_chronicle_parse_route_409_while_fetch_running(monkeypatch):
    """Same half-written-mirror guard as /api/olof/parse — both corpora are
    written by the one olof fetch job."""
    import backend.olof_fetcher as olof_fetcher

    db_path, _tmp = _make_db()
    olof_fetcher._JOB.try_begin(stage="fetching")
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/olof/chronicle_parse", json={})
            assert resp.status_code == 409
    finally:
        olof_fetcher._JOB.finish()

    conn = db.get_connection(db_path)
    rows = conn.execute("SELECT COUNT(*) AS n FROM refresh_step_runs").fetchall()
    assert rows[0]["n"] == 0


def test_bobserve_parse_route_writes_one_run_record(monkeypatch):
    """POST /api/bobserve/parse writes exactly one refresh_step_runs row for
    step_id='bobserve_parse' with the coverage summary as counters."""
    import backend.bobserve_parser as bobserve_parser

    fake_summary = {"pages_parsed": 2, "pages_ok": 2, "events_emitted": 2}
    monkeypatch.setattr(bobserve_parser, "run_parse", lambda file=None: fake_summary)

    db_path, _tmp = _make_db()
    with _AppClient(db_path) as client:
        resp = client.post("/api/bobserve/parse", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["pages_parsed"] == 2

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, status FROM refresh_step_runs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["step_id"] == "bobserve_parse"
    assert rows[0]["status"] == "ok"


def test_bobserve_parse_route_409_while_fetch_running(monkeypatch):
    """A running bobserve-fetch job must block /api/bobserve/parse."""
    import backend.bobserve_fetcher as bobserve_fetcher

    db_path, _tmp = _make_db()
    bobserve_fetcher._JOB.try_begin(stage="fetching")
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/bobserve/parse", json={})
            assert resp.status_code == 409
    finally:
        bobserve_fetcher._JOB.finish()

    conn = db.get_connection(db_path)
    rows = conn.execute("SELECT COUNT(*) AS n FROM refresh_step_runs").fetchall()
    assert rows[0]["n"] == 0
