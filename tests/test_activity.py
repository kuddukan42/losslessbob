"""Tests for backend/activity.py (TODO-262, FABLE_ACTIVITY_CENTER.md §B1).

Monkeypatches each worker's own status function (through its module, matching
how backend.activity's wrapper functions look them up at call time) rather
than spinning up a Flask app — pure unit tests of the aggregator logic.
"""
import backend.activity as activity
import backend.archive_org as archive_org
import backend.bobdylan_scraper as bobdylan_scraper
import backend.bootleg_scraper as bootleg_scraper
import backend.filer as filer
import backend.geocoder as geocoder
import backend.importer as importer
import backend.integrity_monitor as integrity_monitor
import backend.scraper as scraper
import backend.setlistfm as setlistfm
import backend.site_crawler as site_crawler


def _reset_activity_state():
    """Clear the module-level ring buffer / transition-tracking dicts.

    Each test starts from a clean slate so history/observed-start-time
    bookkeeping from a previous test can't leak in.
    """
    activity._history.clear()
    activity._last_running.clear()
    activity._observed_started_at.clear()


def test_normalize_running_bool_shape(monkeypatch):
    """A {"running": bool} worker (e.g. scraper) normalizes to state='running'."""
    _reset_activity_state()
    monkeypatch.setattr(
        scraper, "get_scrape_status",
        lambda: {
            "running": True, "current_lb": 42, "last_lb": None, "total": 100,
            "done": 10, "errors": 0, "skipped": 0, "last_action": None,
            "last_source": None, "stop_requested": False,
        },
    )
    result = activity.snapshot()
    scraping_jobs = [j for j in result["jobs"] if j["kind"] == "scraping"]
    assert len(scraping_jobs) == 1
    job = scraping_jobs[0]
    assert job["state"] == "running"
    assert job["id"] == "scraping"
    assert job["screen"] == "/scraper"
    assert job["cancel_route"] == "/api/scrape/stop"
    assert job["progress"] == {"current": 10, "total": 100, "label": 42}
    assert result["busy"] is True


def test_normalize_status_enum_shape(monkeypatch):
    """A {"status": "idle|running|..."} worker (e.g. setlistfm) normalizes too."""
    _reset_activity_state()
    monkeypatch.setattr(
        setlistfm, "get_status",
        lambda: {
            "status": "running", "page": 3, "total_pages": 10, "shows_stored": 5,
            "tracks_stored": 20, "errors": 0, "stop_requested": False, "message": "",
        },
    )
    result = activity.snapshot()
    jobs = [j for j in result["jobs"] if j["kind"] == "setlistfm_syncing"]
    assert len(jobs) == 1
    job = jobs[0]
    assert job["state"] == "running"
    assert job["progress"] == {"current": 3, "total": 10, "label": ""}
    assert result["busy"] is True


def test_progress_omits_missing_fields(monkeypatch):
    """Fields the worker doesn't expose are omitted, never fabricated."""
    _reset_activity_state()
    monkeypatch.setattr(
        site_crawler, "get_crawler_status",
        lambda: {
            "running": True, "stage": "crawling", "current_url": None,
            "queue_size": 0, "fetched": 5, "not_modified": 0, "skipped": 0,
            "failed": 0, "not_found": 0, "session_id": 1, "message": "",
            "stop_requested": False,
        },
    )
    result = activity.snapshot()
    job = next(j for j in result["jobs"] if j["kind"] == "crawling")
    # current_url is None -> "label" must be omitted, not present as None.
    assert "label" not in job.get("progress", {})
    assert job["progress"]["current"] == 5
    assert job["progress"]["total"] == 0


def test_busy_parity_with_old_semantics(monkeypatch):
    """busy_snapshot() finds the same first-running worker the legacy
    activity_busy() would have, using the same precedence order, including
    a gap worker the old endpoint never saw.
    """
    _reset_activity_state()
    # Everything idle except integrity scan (4th in the original 11-worker
    # precedence order) -> old activity_busy() would report "scanning".
    monkeypatch.setattr(importer, "get_import_status", lambda: {"running": False})
    monkeypatch.setattr(scraper, "get_scrape_status", lambda: {"running": False})
    monkeypatch.setattr(bootleg_scraper, "get_scrape_status", lambda: {"running": False})
    monkeypatch.setattr(
        integrity_monitor, "get_scan_status",
        lambda: {"running": True, "mount_id": None, "folders_done": 1,
                  "folders_total": 10, "current_folder": "/x", "result": None},
    )
    monkeypatch.setattr(filer, "get_file_job_status", lambda: {"running": False})
    monkeypatch.setattr(site_crawler, "get_crawler_status", lambda: {"running": False})
    monkeypatch.setattr(geocoder, "get_progress", lambda: {"running": False})
    monkeypatch.setattr(bobdylan_scraper, "get_status", lambda: {"status": "idle"})
    monkeypatch.setattr(setlistfm, "get_status", lambda: {"status": "idle"})
    monkeypatch.setattr(archive_org, "get_status", lambda: {"running": False, "status": "idle"})

    result = activity.busy_snapshot()
    assert result == {"busy": True, "activity": "scanning"}


def test_busy_includes_gap_worker(monkeypatch):
    """A gap worker (spectrogram batch) makes the busy dot busy — D-3."""
    _reset_activity_state()
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
        lambda: {"status": "running", "current": "foo.flac", "done": 1, "total": 5,
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

    result = activity.busy_snapshot()
    assert result == {"busy": True, "activity": "spectrogram_generating"}


def test_running_to_finished_edge_lands_in_history(monkeypatch):
    """A worker that stops between two snapshot() calls gets a history entry."""
    _reset_activity_state()
    state = {"running": True, "done": 3, "total": 10, "errors": 0, "skipped": 0,
              "rows_total": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0,
              "stage": "applying", "message": "", "error": None}
    monkeypatch.setattr(bootleg_scraper, "get_scrape_status", lambda: dict(state))

    result = activity.snapshot()
    assert any(j["kind"] == "scraping_bootlegs" and j["state"] == "running"
               for j in result["jobs"])
    assert not any(j["kind"] == "scraping_bootlegs" and j["state"] != "running"
                   for j in result["jobs"])

    # Worker finishes.
    state["running"] = False
    state["stage"] = "done"
    result = activity.snapshot()

    finished = [j for j in result["jobs"]
                if j["kind"] == "scraping_bootlegs" and j["state"] == "done"]
    assert len(finished) == 1
    assert "finished_at" in finished[0]
    assert not any(j["kind"] == "scraping_bootlegs" and j["state"] == "running"
                   for j in result["jobs"])

    # And it stays in history on the next poll even once idle.
    result = activity.snapshot()
    assert any(j["kind"] == "scraping_bootlegs" and j["state"] == "done"
               for j in result["jobs"])


def test_raising_status_getter_is_skipped_not_500(monkeypatch):
    """A worker whose status_getter raises is dropped from the snapshot, and
    every other worker is still reported (never a 500 for the whole batch)."""
    _reset_activity_state()

    def _boom():
        raise RuntimeError("worker is on fire")

    monkeypatch.setattr(importer, "get_import_status", _boom)
    monkeypatch.setattr(
        scraper, "get_scrape_status",
        lambda: {"running": True, "current_lb": 1, "total": 1, "done": 0,
                  "errors": 0, "skipped": 0, "last_action": None, "last_source": None,
                  "stop_requested": False, "last_lb": None},
    )

    result = activity.snapshot()  # must not raise
    assert not any(j["kind"] == "importing" for j in result["jobs"])
    assert any(j["kind"] == "scraping" and j["state"] == "running" for j in result["jobs"])
    assert result["busy"] is True


def test_job_adapters_cover_original_11_plus_gap_workers():
    """JOB_ADAPTERS preserves the original 11-worker precedence order and
    includes all four spec §1a gap workers."""
    kinds = [a.kind for a in activity.JOB_ADAPTERS]
    original_11 = [
        "importing", "scraping", "scraping_bootlegs", "scanning", "filing",
        "crawling", "geocoding", "bobdylan_scraping", "setlistfm_syncing",
        "updating_app", "downloading_data",
    ]
    assert kinds[:11] == original_11
    for gap_kind in (
        "spectrogram_generating", "tapematch_crawling",
        "pipeline_running", "archive_uploading",
    ):
        assert gap_kind in kinds
    assert len(kinds) == 15
