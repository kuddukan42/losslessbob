"""Tests for the SSE tee registry in backend/activity.py.

(TODO-262, FABLE_ACTIVITY_CENTER.md §B2). Drives ``track()``-wrapped
generators by hand (``next()``) to interleave with ``snapshot()`` calls the
same way a real request-scoped SSE route interleaves with a polling GUI
client — without spinning up Flask or touching any real worker.
"""
import pytest

import backend.activity as activity
from backend import archive_org as archive_org
from backend import bobdylan_scraper as bobdylan_scraper
from backend import bootleg_scraper as bootleg_scraper
from backend import filer as filer
from backend import geocoder as geocoder
from backend import importer as importer
from backend import integrity_monitor as integrity_monitor
from backend import scraper as scraper
from backend import setlistfm as setlistfm
from backend import site_crawler as site_crawler


def _reset_activity_state():
    """Clear ring buffer / transition-tracking / SSE-registry state."""
    activity._history.clear()
    activity._last_running.clear()
    activity._observed_started_at.clear()
    activity._tracked_jobs.clear()


def _mock_all_adapters_idle(monkeypatch):
    """Idle out every polled adapter so only the tracked job is 'running'.

    Keeps these tests deterministic regardless of any real worker state in
    the environment (e.g. a detached tapematch crawl running outside this
    test process) — mirrors the pattern already used in test_activity.py.
    """
    for mod, fn, val in [
        (importer, "get_import_status", {"running": False}),
        (scraper, "get_scrape_status", {"running": False}),
        (bootleg_scraper, "get_scrape_status", {"running": False}),
        (integrity_monitor, "get_scan_status", {"running": False}),
        (filer, "get_file_job_status", {"running": False}),
        (site_crawler, "get_crawler_status", {"running": False}),
        (geocoder, "get_progress", {"running": False}),
        (bobdylan_scraper, "get_status", {"status": "idle"}),
        (setlistfm, "get_status", {"status": "idle"}),
        (archive_org, "get_status", {"running": False, "status": "idle"}),
    ]:
        monkeypatch.setattr(mod, fn, (lambda v: (lambda: v))(val))

    from backend import app as app_module
    monkeypatch.setattr(app_module, "get_update_status", lambda: {"status": "idle"})
    monkeypatch.setattr(app_module, "get_data_dl_status", lambda: {"status": "idle"})
    monkeypatch.setattr(
        app_module, "get_spectrogram_status",
        lambda: {"status": "idle", "current": None, "done": 0, "total": 0,
                  "errors": 0, "skipped": 0, "stop_requested": False},
    )
    monkeypatch.setattr(
        app_module, "get_tapematch_crawl_status",
        lambda: {"running": False, "pid": None, "runs_on_disk": 0,
                  "distinct_dates": 0, "log_tail": []},
    )
    monkeypatch.setattr(
        app_module, "get_pipeline_run_status",
        lambda: {"running": False, "folders_total": 0, "folders_done": 0,
                  "in_progress": [], "results": {}, "errors": [], "steps": [],
                  "started_at": None, "cancelled": False},
    )


def test_tracked_job_running_mid_stream_then_done():
    """A track()-wrapped generator shows up as 'running' while its `with`
    block is still open, then flips to 'done' once it exits normally."""
    _reset_activity_state()

    def _fake_sse_route():
        with activity.track("master_install", screen="/setup") as job:
            job.update({"pct": 10, "label": "Downloading…"})
            yield "data: progress-1\n\n"
            job.update({"pct": 100, "label": "Applying…"})
            yield "data: progress-2\n\n"

    gen = _fake_sse_route()
    assert next(gen) == "data: progress-1\n\n"

    mid = activity.snapshot()
    live = [j for j in mid["jobs"] if j["kind"] == "master_install"]
    assert len(live) == 1
    job_rec = live[0]
    assert job_rec["state"] == "running"
    assert job_rec["id"].startswith("master_install-")
    assert job_rec["screen"] == "/setup"
    assert "cancel_route" not in job_rec
    assert job_rec["progress"] == {"pct": 10, "label": "Downloading…"}
    assert mid["busy"] is True

    assert next(gen) == "data: progress-2\n\n"
    with pytest.raises(StopIteration):
        next(gen)  # generator returns -> track() exits normally -> 'done'

    after = activity.snapshot()
    assert not any(j["kind"] == "master_install" and j["state"] == "running"
                   for j in after["jobs"])
    finished = [j for j in after["jobs"]
                if j["kind"] == "master_install" and j["state"] == "done"]
    assert len(finished) == 1
    assert finished[0]["progress"] == {"pct": 100, "label": "Applying…"}
    assert "finished_at" in finished[0]
    assert "cancel_route" not in finished[0]


def test_tracked_job_flips_to_error_and_reraises():
    """A track()-wrapped generator that raises moves to 'error' in history,
    disappears from the running jobs, and the exception still propagates
    unchanged to the caller (never swallowed)."""
    _reset_activity_state()

    def _fake_sse_route():
        with activity.track("sitedata_install", screen="/setup") as job:
            job.update({"label": "Extracting…"})
            yield "data: progress-1\n\n"
            raise RuntimeError("disk full")

    gen = _fake_sse_route()
    assert next(gen) == "data: progress-1\n\n"

    mid = activity.snapshot()
    assert any(j["kind"] == "sitedata_install" and j["state"] == "running"
               for j in mid["jobs"])

    with pytest.raises(RuntimeError, match="disk full"):
        next(gen)

    after = activity.snapshot()
    assert not any(j["kind"] == "sitedata_install" and j["state"] == "running"
                   for j in after["jobs"])
    errored = [j for j in after["jobs"]
               if j["kind"] == "sitedata_install" and j["state"] == "error"]
    assert len(errored) == 1
    assert "finished_at" in errored[0]


def test_multiple_concurrent_tracked_jobs_are_independent():
    """Two SSE routes tracked at once each get their own id/state and don't
    clobber each other (thread-safety of the registry dict)."""
    _reset_activity_state()

    def _route(kind, screen):
        with activity.track(kind, screen=screen) as job:
            job.update({"label": f"{kind} working"})
            yield f"data: {kind}\n\n"

    gen_a = _route("master_publish", "/setup")
    gen_b = _route("derived_recompute", "/dbeditor")
    next(gen_a)
    next(gen_b)

    mid = activity.snapshot()
    kinds_running = {j["kind"] for j in mid["jobs"] if j["state"] == "running"}
    assert {"master_publish", "derived_recompute"} <= kinds_running

    with pytest.raises(StopIteration):
        next(gen_a)
    still_running = {j["kind"] for j in activity.snapshot()["jobs"] if j["state"] == "running"}
    assert "master_publish" not in still_running
    assert "derived_recompute" in still_running

    with pytest.raises(StopIteration):
        next(gen_b)
    none_running = {j["kind"] for j in activity.snapshot()["jobs"] if j["state"] == "running"}
    assert "derived_recompute" not in none_running


def test_busy_snapshot_sees_live_tracked_job(monkeypatch):
    """busy_snapshot() (D-3 contract) reports busy=True and names the
    tracked job's kind while an SSE route is live, with every polled
    adapter idle."""
    _reset_activity_state()
    _mock_all_adapters_idle(monkeypatch)

    def _fake_sse_route():
        with activity.track("wtrf_crawl", screen="/scraper") as job:
            job.update({"current": 1, "total": 5})
            yield "data: progress\n\n"

    gen = _fake_sse_route()
    next(gen)

    result = activity.busy_snapshot()
    assert result == {"busy": True, "activity": "wtrf_crawl"}

    with pytest.raises(StopIteration):
        next(gen)

    result = activity.busy_snapshot()
    assert result == {"busy": False, "activity": None}
