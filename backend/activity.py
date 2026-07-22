"""Unified activity aggregator (TODO-262, FABLE_ACTIVITY_CENTER.md §B1).

The activity center *observes* jobs — it never owns them (spec's "one rule").
Every worker below keeps its own start/stop/status routes exactly as they
were; this module only reads their in-memory status dicts and normalizes
them into one shape (spec §2 A1). ``GET /api/activity/jobs`` reads
:func:`snapshot`; the legacy ``GET /api/activity/busy`` (AppShell's only
consumer, byte-compatible response shape) is re-based on the same table via
:func:`busy_snapshot` so the two views can never drift.

Adding a new job (spec §5 item 4):

1. Polled worker (thread + module-level status dict + GET status route):
   write a tiny ``_get_<kind>_status() -> dict`` wrapper below that calls the
   worker's own status function through its *module* (``_module.get_x()``,
   not a bare function reference) — this is what lets tests monkeypatch the
   worker's function and have it take effect here. Add one row to
   ``JOB_ADAPTERS``: ``(kind, wrapper, cancel_route_or_None, screen_route)``.
   If the worker's progress field names don't match ``current``/``total``/
   ``pct``/``label``, add a ``kind: {...}`` entry to ``_PROGRESS_FIELDS``
   mapping the normalized output keys to the worker's raw dict keys — omit
   any pair the worker doesn't expose, never invent one.
2. Request-scoped SSE stream (no status route): that's spec §A2/B2 — the
   ``track()``/``update()`` registry isn't implemented yet in this bite.
3. Pick a ``kind`` that reads naturally as an i18n key suffix under
   ``appShell.statusBar.activity.<kind>`` — the original 11 workers reuse
   their existing locale keys; anything new needs a locale entry (later bite).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import NamedTuple

from backend import archive_org as _archive_org
from backend import bobdylan_scraper as _bobdylan_scraper
from backend import bootleg_scraper as _bootleg_scraper
from backend import filer as _filer
from backend import geocoder as _geocoder
from backend import importer as _importer
from backend import integrity_monitor as _integrity_monitor
from backend import scraper as _scraper
from backend import setlistfm as _setlistfm
from backend import site_crawler as _site_crawler

_log = logging.getLogger(__name__)


class JobAdapter(NamedTuple):
    """One row of the declarative worker table (spec §2 A1).

    Attributes:
        kind: i18n key suffix / job identity, e.g. ``'scraping'``.
        status_getter: Zero-arg callable returning the worker's raw status
            dict. Synchronous in-memory read — no network/DB calls.
        cancel_route: POST-able route that stops the job, or ``None``.
        screen_route: gui_next router path that owns this job's own UI.
    """

    kind: str
    status_getter: Callable[[], dict]
    cancel_route: str | None
    screen_route: str


# ── Status-getter wrappers ──────────────────────────────────────────────────
# Each wrapper calls the worker's status function through the *module*
# object (not a captured function reference) so monkeypatching the worker's
# module attribute in tests takes effect here too.

def _get_import_status() -> dict:
    return _importer.get_import_status()


def _get_scrape_status() -> dict:
    return _scraper.get_scrape_status()


def _get_bootleg_scrape_status() -> dict:
    return _bootleg_scraper.get_scrape_status()


def _get_integrity_scan_status() -> dict:
    return _integrity_monitor.get_scan_status()


def _get_filing_status() -> dict:
    return _filer.get_file_job_status()


def _get_crawler_status() -> dict:
    return _site_crawler.get_crawler_status()


def _get_geocode_status() -> dict:
    return _geocoder.get_progress()


def _get_bobdylan_status() -> dict:
    return _bobdylan_scraper.get_status()


def _get_setlistfm_status() -> dict:
    return _setlistfm.get_status()


def _get_archive_org_status() -> dict:
    return _archive_org.get_status()


# These five live in backend.app (module-level state, no dedicated module of
# their own). Imported lazily inside the wrapper — by the time a Flask route
# calls snapshot()/busy_snapshot(), backend.app has already finished loading,
# so this is not a circular import, just a deferred one (same pattern the
# old activity_busy() used for backend.geocoder).
def _get_update_status() -> dict:
    from backend import app as _app
    return _app.get_update_status()


def _get_data_download_status() -> dict:
    from backend import app as _app
    return _app.get_data_dl_status()


def _get_spectrogram_status() -> dict:
    from backend import app as _app
    return _app.get_spectrogram_status()


def _get_tapematch_crawl_status() -> dict:
    from backend import app as _app
    return _app.get_tapematch_crawl_status()


def _get_pipeline_run_status() -> dict:
    from backend import app as _app
    return _app.get_pipeline_run_status()


# ── The adapter table ────────────────────────────────────────────────────────
# Order matters: it is the precedence order for the legacy busy_snapshot()
# "first running worker wins" response, preserved byte-for-byte from the old
# activity_busy() for the first 11 rows. The four gap workers (spec §1a
# "Missing from activity/busy today") are appended after — closing those
# blind spots is spec's D-3 default.
JOB_ADAPTERS: list[JobAdapter] = [
    JobAdapter("importing", _get_import_status, None, "/setup"),
    JobAdapter("scraping", _get_scrape_status, "/api/scrape/stop", "/scraper"),
    JobAdapter("scraping_bootlegs", _get_bootleg_scrape_status, None, "/bootlegs"),
    JobAdapter(
        "scanning", _get_integrity_scan_status,
        "/api/collection/integrity/scan/cancel", "/collection",
    ),
    JobAdapter("filing", _get_filing_status, None, "/pipeline"),
    JobAdapter("crawling", _get_crawler_status, "/api/crawler/stop", "/scraper"),
    JobAdapter("geocoding", _get_geocode_status, "/api/geocode/stop", "/map"),
    JobAdapter(
        "bobdylan_scraping", _get_bobdylan_status, "/api/bobdylan/stop", "/scraper",
    ),
    JobAdapter(
        "setlistfm_syncing", _get_setlistfm_status, "/api/setlistfm/stop", "/scraper",
    ),
    JobAdapter("updating_app", _get_update_status, None, "/setup"),
    JobAdapter("downloading_data", _get_data_download_status, None, "/setup"),
    # --- gap workers (spec §1a "Missing from activity/busy today") ---------
    JobAdapter(
        "spectrogram_generating", _get_spectrogram_status,
        "/api/spectrogram/stop", "/spectrograms",
    ),
    JobAdapter(
        "tapematch_crawling", _get_tapematch_crawl_status,
        "/api/tapematch/crawl/stop", "/tapematch",
    ),
    JobAdapter(
        "pipeline_running", _get_pipeline_run_status,
        "/api/pipeline/run/cancel", "/pipeline",
    ),
    JobAdapter(
        "archive_uploading", _get_archive_org_status,
        "/api/archive_org/stop", "/sharing",
    ),
]


# ── Per-kind progress field mapping (spec §2 A1: "per-worker field mapping
# lives in the adapter") — normalized output key -> raw status-dict key.
# A kind with no entry (or a missing raw key at read time) simply gets no
# `progress` field — never fabricated. ───────────────────────────────────────
_PROGRESS_FIELDS: dict[str, dict[str, str]] = {
    "importing": {"current": "rows_merged", "total": "rows_total", "label": "stage"},
    "scraping": {"current": "done", "total": "total", "label": "current_lb"},
    "scraping_bootlegs": {"current": "rows_added", "total": "rows_total", "label": "stage"},
    "scanning": {
        "current": "folders_done", "total": "folders_total", "label": "current_folder",
    },
    "filing": {"current": "files_done", "total": "files_total", "label": "current_file"},
    "crawling": {"current": "fetched", "total": "queue_size", "label": "current_url"},
    "geocoding": {"current": "done", "total": "total", "label": "current"},
    "bobdylan_scraping": {"current": "done", "total": "total", "label": "current_url"},
    "setlistfm_syncing": {"current": "page", "total": "total_pages", "label": "message"},
    "updating_app": {"pct": "progress", "label": "message"},
    "downloading_data": {
        "pct": "progress", "label": "message",
        "current": "downloaded_bytes", "total": "total_bytes",
    },
    "spectrogram_generating": {"current": "done", "total": "total", "label": "current"},
    "tapematch_crawling": {"current": "runs_on_disk"},
    "pipeline_running": {"current": "folders_done", "total": "folders_total"},
    "archive_uploading": {"current": "files_done", "total": "files_total", "label": "current_file"},
}


def _extract_progress(kind: str, raw: dict) -> dict | None:
    """Best-effort progress extraction for *kind* from its raw status dict.

    Args:
        kind: Adapter kind, keys into ``_PROGRESS_FIELDS``.
        raw: The worker's raw status dict.

    Returns:
        A ``{current?, total?, pct?, label?}`` dict with only the keys the
        worker actually exposed (non-None), or ``None`` if none were present.
    """
    field_map = _PROGRESS_FIELDS.get(kind)
    if not field_map:
        return None
    progress: dict = {}
    for out_key, raw_key in field_map.items():
        value = raw.get(raw_key)
        if value is not None:
            progress[out_key] = value
    return progress or None


# ── Running / terminal-state classification ─────────────────────────────────

def _default_is_running(raw: dict) -> bool:
    """Generic running check for the two shape families in spec §1a.

    ``{"running": bool}`` workers and ``{"status": "idle|running|..."}``
    workers — the split the legacy ``activity_busy()`` already handled.
    """
    return bool(raw.get("running")) or raw.get("status") == "running"


def _not_idle_is_running(raw: dict) -> bool:
    """Legacy semantics for the app-updater / data-download workers.

    The original ``activity_busy()`` treated *any* non-idle status
    (downloading/extracting/done/error, not just "running") as busy for
    these two. Preserved byte-for-byte here — repo rule requires exact
    semantic parity, not just the same two-family split. In practice both
    workers only ever reach "done"/"error" right before the app restarts
    itself (self-update / data-package apply), so this never causes a
    stuck-busy dot in normal use.
    """
    return raw.get("status", "idle") != "idle"


_IS_RUNNING_OVERRIDES: dict[str, Callable[[dict], bool]] = {
    "updating_app": _not_idle_is_running,
    "downloading_data": _not_idle_is_running,
}


def _is_running(kind: str, raw: dict) -> bool:
    """Return whether *kind*'s raw status dict represents a running job."""
    check = _IS_RUNNING_OVERRIDES.get(kind, _default_is_running)
    return check(raw)


_ERROR_STATUS_VALUES = frozenset({"error", "failed"})
_CANCELLED_STATUS_VALUES = frozenset({"stopped", "cancelled"})


def _terminal_state(raw: dict) -> str:
    """Classify a just-finished job as done/error/cancelled, best-effort.

    Prefers the worker's own explicit ``status``/``stage`` value when
    present (authoritative); falls back to a generic ``cancelled``/``error``
    flag; defaults to ``'done'`` when the worker gives no terminal signal at
    all (e.g. the tapematch crawl, which is pure observation with no status
    concept) — a job that simply stopped running is the sane default, never
    fabricated as an error.
    """
    status_val = raw.get("status") or raw.get("stage")
    if status_val in _ERROR_STATUS_VALUES:
        return "error"
    if status_val in _CANCELLED_STATUS_VALUES:
        return "cancelled"
    if status_val == "done":
        return "done"
    if raw.get("cancelled") is True:
        return "cancelled"
    if raw.get("error"):
        return "error"
    if raw.get("stop_requested") is True:
        return "cancelled"
    return "done"


# ── Finished-job history: in-memory ring buffer (D-4 default: 50, memory-only,
# cleared on restart) ────────────────────────────────────────────────────────
_HISTORY_MAXLEN = 50
_history: deque[dict] = deque(maxlen=_HISTORY_MAXLEN)

# Per-kind bookkeeping for the running->finished edge detection, and for
# reporting started_at on workers whose own status dict carries no timestamp
# (an observed start time, not sourced from the worker — the closest we can
# get without touching worker internals, per the one rule).
_last_running: dict[str, bool] = {}
_observed_started_at: dict[str, float] = {}
_state_lock = threading.Lock()


def _build_record(
    kind: str, raw: dict, adapter: JobAdapter, *, state: str, finished_at: float | None = None,
) -> dict:
    """Assemble one normalized job record (spec §2 A1 shape)."""
    record: dict = {"id": kind, "kind": kind, "state": state, "screen": adapter.screen_route}
    started_at = _observed_started_at.get(kind)
    if started_at is not None:
        record["started_at"] = started_at
    if finished_at is not None:
        record["finished_at"] = finished_at
    progress = _extract_progress(kind, raw)
    if progress:
        record["progress"] = progress
    if state == "running" and adapter.cancel_route:
        record["cancel_route"] = adapter.cancel_route
    return record


def snapshot() -> dict:
    """Poll every adapter once and return the normalized §2 A1 shape.

    Synchronous in-memory reads only, same as the legacy ``activity_busy()``
    — no server-side polling loop. A worker whose ``status_getter`` raises is
    logged and skipped; it never turns into a 500 for the rest of the jobs.
    A running->idle transition for any adapter is recorded into the
    finished-job history ring buffer.

    Returns:
        ``{busy: bool, jobs: [...]}`` — currently running jobs first (adapter
        table order), then finished/error/cancelled jobs newest-first.
    """
    running_jobs: list[dict] = []
    busy = False

    with _state_lock:
        for adapter in JOB_ADAPTERS:
            try:
                raw = adapter.status_getter()
            except Exception:
                _log.warning(
                    "activity: status_getter for %r raised, skipping", adapter.kind,
                    exc_info=True,
                )
                continue

            running = _is_running(adapter.kind, raw)
            was_running = _last_running.get(adapter.kind, False)

            if running:
                busy = True
                if not was_running:
                    _observed_started_at[adapter.kind] = time.time()
                running_jobs.append(_build_record(adapter.kind, raw, adapter, state="running"))
            elif was_running:
                state = _terminal_state(raw)
                record = _build_record(
                    adapter.kind, raw, adapter, state=state, finished_at=time.time(),
                )
                _observed_started_at.pop(adapter.kind, None)
                _history.appendleft(record)

            _last_running[adapter.kind] = running

        history_jobs = list(_history)

    return {"busy": busy, "jobs": running_jobs + history_jobs}


def busy_snapshot() -> dict:
    """Legacy ``{busy, activity}`` shape, re-based on :func:`snapshot`.

    ``activity`` is the ``kind`` of the first running job in adapter-table
    order (same precedence the old ``activity_busy()`` used), or ``None``.
    Response shape is byte-compatible with the pre-TODO-262 endpoint —
    AppShell's ``StatusBar`` is its only consumer.
    """
    result = snapshot()
    if not result["busy"]:
        return {"busy": False, "activity": None}
    first_running = next((j for j in result["jobs"] if j["state"] == "running"), None)
    return {"busy": True, "activity": first_running["kind"] if first_running else None}
