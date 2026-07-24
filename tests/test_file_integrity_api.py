"""Tests for the file-integrity API routes and rolling-verify scheduler (TODO-267).

Covers:
  - /api/file-integrity/scan argument validation and the one-scan-per-mount 409.
  - A real background index scan driven through the route, polled to completion.
  - /api/file-integrity/{summary,problems,history} payload shapes.
  - /api/file-integrity/rebaseline clearing a sticky rot flag — the only path by
    which a rot verdict may be replaced, since scans deliberately never do it.
  - The rolling scheduler being opt-in, and reading its interval only from
    'verify' runs so a manual index scan cannot defer the deep verify.

Never touches the real data/losslessbob.db — all tests use temp-file DBs.
"""

import os
import tempfile
import time

import pytest

import backend.db as db
import backend.paths as _paths


@pytest.fixture(autouse=True)
def _reset_file_integrity_state():
    """Clear file_integrity's module-level job registries between tests.

    Mount ids restart at 1 in each temp DB, so a finished progress dict left
    over from a previous test would otherwise be mistaken for this test's run.
    """
    from backend import file_integrity
    with file_integrity._JOB_LOCK:
        file_integrity._JOBS.clear()
        file_integrity._CANCEL.clear()
        file_integrity._THREADS.clear()
    yield
    with file_integrity._JOB_LOCK:
        file_integrity._JOBS.clear()
        file_integrity._CANCEL.clear()
        file_integrity._THREADS.clear()


def _make_db():
    """Create a temp DB with the full schema and point the module globals at it.

    Returns:
        (db_path, tmp_dir, restore) — call restore() in a finally block.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lb_fileintegrity_api_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)

    orig_paths, orig_db = _paths.DB_PATH, db.DB_PATH
    _paths.DB_PATH = db_path
    db.DB_PATH = db_path

    def _restore():
        _paths.DB_PATH = orig_paths
        db.DB_PATH = orig_db

    return db_path, tmp_dir, _restore


def _make_mount(tmp_dir: str, n_files: int = 3) -> tuple[int, str]:
    """Create an on-disk mount plus its collection_mounts / my_collection rows.

    Args:
        tmp_dir: Directory to build under.
        n_files: Number of .flac files to create.

    Returns:
        (mount_id, mount_root).
    """
    root = os.path.join(tmp_dir, "MOUNT")
    folder = os.path.join(root, "1975-05-03 Somewhere (LB-99999)")
    os.makedirs(folder)
    for i in range(n_files):
        with open(os.path.join(folder, f"t{i:02d}.flac"), "wb") as f:
            f.write(f"track-{i}-".encode() * 400)

    mount_id = db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_mounts(label, root_path) VALUES('TEST', ?)",
            (root,),
        ).lastrowid
    )
    db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO entries(lb_number, date_str) VALUES(99999, '1975-05-03')"
        )
    )
    db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path) "
            "VALUES(99999, ?, ?)",
            (os.path.basename(folder), folder),
        )
    )
    return mount_id, root


def _client(db_path):
    """Build a Flask test client bound to the temp DB."""
    from backend.app import create_app
    return create_app().test_client()


def _wait_idle(mount_id: int, timeout: float = 20.0) -> dict:
    """Poll until the background scan on a mount reports not-running.

    Args:
        mount_id: Mount whose scan to await.
        timeout: Seconds before giving up.

    Returns:
        The final progress dict.
    """
    from backend import file_integrity
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = file_integrity.get_status(mount_id)
        # "status" only appears once the run has actually finished; before the
        # background thread registers, get_status returns a not-running stub.
        if status.get("status") is not None and not status.get("running"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"scan on mount {mount_id} did not finish within {timeout}s")


def _rot_file(path: str) -> None:
    """Corrupt a file in place, preserving size and mtime exactly."""
    st = os.stat(path)
    with open(path, "r+b") as f:
        f.seek(0)
        first = f.read(1)
        f.seek(0)
        f.write(b"\x00" if first != b"\x00" else b"\xff")
    os.utime(path, (st.st_atime, st.st_mtime))


def test_scan_route_validates_arguments():
    """Missing mount_id and an unknown mode are both rejected before any work."""
    db_path, tmp_dir, restore = _make_db()
    try:
        client = _client(db_path)
        assert client.post("/api/file-integrity/scan", json={}).status_code == 400
        resp = client.post("/api/file-integrity/scan",
                           json={"mount_id": 1, "mode": "sideways"})
        assert resp.status_code == 400
        assert "sideways" in resp.get_json()["error"]
    finally:
        restore()


def test_scan_route_runs_index_and_populates_inventory():
    """A route-driven index scan baselines the mount's files."""
    db_path, tmp_dir, restore = _make_db()
    try:
        mount_id, _root = _make_mount(tmp_dir, n_files=3)
        client = _client(db_path)

        resp = client.post("/api/file-integrity/scan",
                           json={"mount_id": mount_id, "mode": "index"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        final = _wait_idle(mount_id)
        assert final["status"] == "done"
        assert final["counts"]["files_new"] == 3

        conn = db.get_connection(db_path)
        assert conn.execute(
            "SELECT COUNT(*) c FROM file_inventory"
        ).fetchone()["c"] == 3

        summary = client.get("/api/file-integrity/summary").get_json()
        assert summary[str(mount_id)]["ok"] == 3

        history = client.get("/api/file-integrity/history").get_json()["history"]
        assert history[0]["mode"] == "index"
        assert history[0]["status"] == "done"
    finally:
        restore()


def test_scan_route_rejects_second_scan_on_same_mount():
    """One worker per mount — a concurrent scan of the same mount gets a 409."""
    db_path, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity

        mount_id, _root = _make_mount(tmp_dir, n_files=2)
        client = _client(db_path)

        # Hold the mount busy with a stub thread so the guard has something live.
        import threading
        gate = threading.Event()
        holder = threading.Thread(target=gate.wait, daemon=True)
        holder.start()
        with file_integrity._JOB_LOCK:
            file_integrity._THREADS[mount_id] = holder

        resp = client.post("/api/file-integrity/scan",
                           json={"mount_id": mount_id, "mode": "index"})
        assert resp.status_code == 409
        assert resp.get_json()["ok"] is False

        gate.set()
        holder.join(timeout=5)
        with file_integrity._JOB_LOCK:
            file_integrity._THREADS.pop(mount_id, None)
    finally:
        restore()


def test_problems_route_and_rebaseline_clears_rot():
    """Rot surfaces on /problems and only rebaseline can clear it."""
    db_path, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity

        mount_id, root = _make_mount(tmp_dir, n_files=2)
        client = _client(db_path)
        file_integrity.scan_mount(mount_id, "index")

        victim_rel = "1975-05-03 Somewhere (LB-99999)/t00.flac"
        _rot_file(os.path.join(root, victim_rel))
        file_integrity.scan_mount(mount_id, "verify")

        problems = client.get("/api/file-integrity/problems").get_json()["problems"]
        assert len(problems) == 1
        assert problems[0]["status"] == "rot"
        assert problems[0]["rel_path"] == victim_rel

        conn = db.get_connection(db_path)
        rotted_hash = conn.execute(
            "SELECT xxh3 FROM file_inventory WHERE rel_path=?", (victim_rel,)
        ).fetchone()["xxh3"]

        # Another verify must NOT launder the rot away.
        file_integrity.scan_mount(mount_id, "verify")
        assert conn.execute(
            "SELECT status FROM file_inventory WHERE rel_path=?", (victim_rel,)
        ).fetchone()["status"] == "rot"

        resp = client.post("/api/file-integrity/rebaseline",
                           json={"mount_id": mount_id, "rel_paths": [victim_rel]})
        assert resp.status_code == 200
        assert resp.get_json()["rebaselined"] == 1

        row = conn.execute(
            "SELECT * FROM file_inventory WHERE rel_path=?", (victim_rel,)
        ).fetchone()
        assert row["status"] == "ok"
        assert row["xxh3"] != rotted_hash, "baseline moved to current content"

        assert client.get("/api/file-integrity/problems").get_json()["problems"] == []
    finally:
        restore()


def test_rebaseline_route_validates_arguments():
    """Both mount_id and a non-empty rel_paths list are required."""
    db_path, tmp_dir, restore = _make_db()
    try:
        client = _client(db_path)
        assert client.post("/api/file-integrity/rebaseline",
                           json={"mount_id": 1}).status_code == 400
        assert client.post("/api/file-integrity/rebaseline",
                           json={"rel_paths": ["x"]}).status_code == 400
    finally:
        restore()


def test_scan_history_filters_by_mode():
    """The scheduler's clock must read verify runs only, not index runs."""
    db_path, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity

        mount_id, _root = _make_mount(tmp_dir, n_files=2)
        file_integrity.scan_mount(mount_id, "index")
        file_integrity.scan_mount(mount_id, "verify")
        file_integrity.scan_mount(mount_id, "index")

        all_runs = db.get_file_scan_history(db_path=db_path)
        assert len(all_runs) == 3
        assert all_runs[0]["mode"] == "index", "newest overall is the index run"

        verify_runs = db.get_file_scan_history(mode="verify", db_path=db_path)
        assert len(verify_runs) == 1
        assert verify_runs[0]["mode"] == "verify"
    finally:
        restore()


def test_rolling_scheduler_is_opt_in():
    """With file_verify_enabled unset, the worker dispatches nothing."""
    db_path, tmp_dir, restore = _make_db()
    try:
        import threading

        from backend import scheduler

        calls = []
        from backend import file_integrity
        orig = file_integrity.rolling_verify
        file_integrity.rolling_verify = lambda **kw: calls.append(kw) or {}
        try:
            # Drive one worker iteration directly rather than waiting an hour.
            scheduler._FILE_VERIFY_CHECK_INTERVAL = 0.01
            stop = threading.Event()
            t = threading.Thread(
                target=scheduler._file_verify_worker,
                args=(stop,), kwargs={"db_path": db_path}, daemon=True,
            )
            t.start()
            time.sleep(0.2)
            stop.set()
            t.join(timeout=5)
            assert calls == [], "must not run until explicitly enabled"

            db.set_meta("file_verify_enabled", "1", db_path=db_path)
            stop = threading.Event()
            t = threading.Thread(
                target=scheduler._file_verify_worker,
                args=(stop,), kwargs={"db_path": db_path}, daemon=True,
            )
            t.start()
            time.sleep(0.3)
            stop.set()
            t.join(timeout=5)
            assert calls, "enabled worker should dispatch a rolling verify"
            assert calls[0]["budget_seconds"] == 7200.0
            assert calls[0]["files_per_mount"] == 5000
        finally:
            file_integrity.rolling_verify = orig
            scheduler._FILE_VERIFY_CHECK_INTERVAL = 3600
    finally:
        restore()


def test_meta_float_falls_back_on_garbage():
    """A non-numeric meta value must not take down the scheduler."""
    db_path, tmp_dir, restore = _make_db()
    try:
        from backend import scheduler

        assert scheduler._meta_float("nope", 12.0, db_path) == 12.0
        db.set_meta("file_verify_budget_seconds", "banana", db_path=db_path)
        assert scheduler._meta_float(
            "file_verify_budget_seconds", 42.0, db_path
        ) == 42.0
        db.set_meta("file_verify_budget_seconds", "900", db_path=db_path)
        assert scheduler._meta_float(
            "file_verify_budget_seconds", 42.0, db_path
        ) == 900.0
    finally:
        restore()
