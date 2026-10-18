"""TODO-366: one-run-at-a-time guard for the background workers.

Before this, six start routes checked a status dict and then spawned a thread
whose worker only set ``running`` once it got going, so two quick POSTs could
both pass the check and start the same job twice. ``SingleFlight`` claims
before the thread exists.
"""

import importlib
import os
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.job_progress import SingleFlight


def _wait_released(flight: SingleFlight, timeout: float = 5.0) -> None:
    """Spin until ``flight`` is idle (the worker thread's ``finally`` ran)."""
    deadline = threading.Event()
    for _ in range(int(timeout / 0.01)):
        if not flight.active:
            return
        deadline.wait(0.01)
    raise AssertionError("flight never released")


# ── SingleFlight itself ──────────────────────────────────────────────────────

def test_claim_is_exclusive_until_released():
    flight = SingleFlight("t")
    assert flight.try_claim() is True
    assert flight.active is True
    assert flight.try_claim() is False
    flight.release()
    assert flight.active is False
    assert flight.try_claim() is True


def test_start_thread_refuses_second_start_while_running():
    flight = SingleFlight("t")
    gate = threading.Event()
    assert flight.start_thread(gate.wait, timeout=5) is True
    assert flight.start_thread(gate.wait, timeout=5) is False
    gate.set()
    _wait_released(flight)
    assert flight.start_thread(lambda: None) is True


def test_start_thread_releases_when_worker_raises():
    flight = SingleFlight("t")

    def _boom() -> None:
        raise ValueError("boom")

    assert flight.start_thread(_boom) is True
    _wait_released(flight)
    assert flight.try_claim() is True


def test_concurrent_claims_admit_exactly_one():
    flight = SingleFlight("t")
    barrier = threading.Barrier(16)
    wins: list[bool] = []
    lock = threading.Lock()

    def _race() -> None:
        barrier.wait()
        got = flight.try_claim()
        with lock:
            wins.append(got)

    threads = [threading.Thread(target=_race) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1


# ── Each wired worker ────────────────────────────────────────────────────────

# (module, async starter, private body the starter runs, sync entry point,
#  value the sync entry point returns when busy — or an exception type)
WORKERS = [
    ("backend.bootleg_scraper", "start_scrape_async", "_scrape_bootlegs",
     "scrape_bootlegs", {"status": "failed", "error": "already running"}),
    ("backend.bobdylan_scraper", "start_scrape_async", "_run_scrape", "run_scrape", 0),
    ("backend.bobdylan_scraper", "start_update_async", "_run_update", "run_update", None),
    ("backend.setlistfm", "start_update_async", "_run_update", "run_update", 0),
    ("backend.site_crawler", "start_crawl_async", "_crawl", "crawl", {"status": "busy"}),
    ("backend.geocoder", "start_batch_async", "_run_batch", "run_batch", None),
]


@pytest.mark.parametrize("modname,starter,body,sync_fn,busy", WORKERS)
def test_worker_refuses_second_start(monkeypatch, modname, starter, body, sync_fn, busy):
    mod = importlib.import_module(modname)
    gate = threading.Event()
    started = threading.Event()
    calls: list[dict] = []

    def _fake_body(**kwargs):
        calls.append(kwargs)
        started.set()
        gate.wait(timeout=5)

    monkeypatch.setattr(mod, body, _fake_body)
    _wait_released(mod._flight)  # an earlier test's worker may still be finishing
    try:
        assert getattr(mod, starter)() is True
        assert started.wait(timeout=5)
        assert getattr(mod, starter)() is False
        assert getattr(mod, sync_fn)() == busy
        assert len(calls) == 1
    finally:
        gate.set()
        _wait_released(mod._flight)
    assert getattr(mod, starter)() is True
    _wait_released(mod._flight)


def test_bobdylan_is_running_covers_the_gap_between_phases(monkeypatch):
    """run_update's status passes through 'done' between discover and scrape;
    the claim keeps is_running() true across that gap."""
    from backend import bobdylan_scraper as bd

    _wait_released(bd._flight)
    assert bd._flight.try_claim()
    try:
        with bd._state_lock:
            bd._state["status"] = "done"
        assert bd.is_running() is True
        assert bd.start_discover_async() is False
    finally:
        bd._flight.release()
    assert bd.is_running() is False


def test_importer_sync_run_raises_while_async_import_holds_claim(monkeypatch):
    from backend import importer

    gate = threading.Event()
    started = threading.Event()

    def _fake_import(source_path, progress_callback=None, db_path=None):
        started.set()
        gate.wait(timeout=5)
        return {"new_lb_count": 0}

    monkeypatch.setattr(importer, "_run_import", _fake_import)
    _wait_released(importer._flight)
    try:
        assert importer.start_import_async("x.txt") is True
        assert started.wait(timeout=5)
        assert importer.start_import_async("x.txt") is False
        with pytest.raises(RuntimeError, match="already running"):
            importer.run_import("x.txt")
    finally:
        gate.set()
        _wait_released(importer._flight)


# ── Route level: a quick double POST ─────────────────────────────────────────

@pytest.fixture()
def client():
    """Flask test client backed by a disposable temp DB."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_flight_")
    import backend.db as _db
    import backend.paths as _paths
    orig_data, orig_db = _paths.DATA_DIR, _db.DB_PATH
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(os.path.join(tmp_dir, "test.db"))
    with patch("backend.scheduler.start_file_watcher"):
        from backend.app import create_app
        flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
    _paths.DATA_DIR, _db.DB_PATH = orig_data, orig_db
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_geocode_run_double_post_starts_one_batch(client, monkeypatch):
    from backend import geocoder

    gate = threading.Event()
    calls: list[dict] = []

    def _fake_batch(**kwargs):
        calls.append(kwargs)
        gate.wait(timeout=5)

    monkeypatch.setattr(geocoder, "_run_batch", _fake_batch)
    _wait_released(geocoder._flight)
    try:
        first = client.post("/api/geocode/run", json={})
        second = client.post("/api/geocode/run", json={})
        assert first.status_code == 200
        assert second.status_code == 409
        assert len(calls) == 1
    finally:
        gate.set()
        _wait_released(geocoder._flight)
