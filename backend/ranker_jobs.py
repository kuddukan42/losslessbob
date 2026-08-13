"""Backend-side wrapper around concert_ranker (TODO-306 Phase 2).

Wraps ``concert_ranker scan``/``rerank`` behind ``JobState``-backed progress
so the Home freshness card's copyable CLI strings for those two steps can
become "Run" buttons. ``concert_ranker/`` stays standalone: this module never
calls ``concert_ranker.cli.main()`` (it calls ``logging.basicConfig()``,
which would stomp the backend process's own logging config) and instead
reuses ``concert_ranker.cli.collection_worklist``/``rerank`` directly — those
two were promoted from private names (``_collection_worklist``/``_rerank``)
specifically so this module isn't reaching into underscore names, and so the
non-concert/non-public exclusion logic lives in exactly one place.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

from backend import config_version
from backend.db import record_step_run
from backend.job_progress import JobState, JobStopped
from concert_ranker import config as cr_config
from concert_ranker.cli import collection_worklist, rerank
from concert_ranker.lb import repo

logger = logging.getLogger(__name__)

_JOB = JobState("ranker-scan")


def get_status() -> dict:
    """Return the current scan job's progress snapshot."""
    return _JOB.snapshot()


def stop() -> None:
    """Request that the active scan job stop as soon as possible."""
    _JOB.stop()


def try_begin(**fields) -> bool:
    """Atomically claim the scan job. See JobState.try_begin."""
    return _JOB.try_begin(**fields)


def finish(**fields) -> None:
    """Release a claim taken by try_begin() without running a scan.

    Used by the route when plan_scan() (synchronous) finds nothing to do or
    fails, so the claim doesn't wedge the job in 'running' state forever —
    the normal case (a scan thread was actually started) finishes via
    run_scan_claimed's own call to this instead.
    """
    _JOB.finish(**fields)


def _default_workers() -> int:
    """Default consumer-process count for a server-side scan.

    The CLI's default of 16 is right for a dedicated terminal run, wrong for
    a process also serving the GUI and holding a write queue.
    """
    return max(1, min(8, (os.cpu_count() or 4) - 1))


def _resolve_workers(requested: int | None) -> int:
    """Clamp *requested* worker count, or use :func:`_default_workers`.

    ``workers = 1`` when packaged/frozen (decision 4): that takes
    ``scan_folders``'s in-process branch and spawns no Pool at all, which
    matters because a frozen build's bundled Python may not support
    ``multiprocessing.get_context("spawn")`` re-launching the frozen exe.
    """
    if getattr(sys, "frozen", False):
        return 1
    if requested is None:
        return _default_workers()
    return max(1, min(requested, 16))


def plan_scan(
    mode: str = "backlog", lbs: list[int] | None = None, db_path: str | None = None,
) -> dict:
    """Build the worklist for a ranker scan without running it (decision 1).

    Args:
        mode: 'backlog' (default) reuses the latest scan_id and filters to
            LBs not yet scanned under it, unless the effective config has
            drifted since that scan was created (in which case a *new* scan
            is created instead of appending — mixing two extraction configs
            inside one scan_id silently corrupts rankings). 'all' always
            creates a new scan with the full collection worklist.
        lbs: Explicit LB filter — reuses the latest scan_id (creating one if
            none exists), no done-lbs filtering (an explicit re-scan request
            should re-scan even if already done).
        db_path: Optional database path override.

    Returns:
        ``{"scan_id", "worklist", "planned", "reused_scan", "config_changed"}``.

    Raises:
        ValueError: *mode* is neither 'backlog' nor 'all'.
    """
    conn = repo.connect(db_path)
    repo.ensure_schema(conn)
    config_now = vars(cr_config.default_config())
    config_json_now = json.dumps(config_now, sort_keys=True)

    reused_scan = False
    config_changed = False

    if lbs:
        scan_id = repo.latest_scan_id(conn)
        if scan_id is None:
            scan_id = repo.create_scan(conn, config=config_now)
        else:
            reused_scan = True
        worklist = collection_worklist(conn, lbs)
    elif mode == "all":
        scan_id = repo.create_scan(conn, config=config_now)
        worklist = collection_worklist(conn)
    elif mode == "backlog":
        scan_id = repo.latest_scan_id(conn)
        if scan_id is None:
            scan_id = repo.create_scan(conn, config=config_now)
            worklist = collection_worklist(conn)
        else:
            row = conn.execute(
                "SELECT config_json FROM quality_scans WHERE scan_id=?", (scan_id,)
            ).fetchone()
            stored_config_json = row["config_json"] if row else None
            if stored_config_json != config_json_now:
                scan_id = repo.create_scan(conn, config=config_now)
                config_changed = True
                worklist = collection_worklist(conn)
            else:
                reused_scan = True
                done = repo.done_lbs(conn, scan_id)
                worklist = [w for w in collection_worklist(conn) if w[0] not in done]
    else:
        raise ValueError(f"mode must be 'backlog' or 'all', got {mode!r}")

    return {
        "scan_id": scan_id,
        "worklist": worklist,
        "planned": len(worklist),
        "reused_scan": reused_scan,
        "config_changed": config_changed,
    }


def run_scan_claimed(
    worklist: list[tuple], scan_id: int, workers: int | None = None,
    db_path: str | None = None,
) -> dict:
    """Thread target for POST /api/ranker/scan — job already claimed by the route.

    A plain ``threading.Thread`` (the route's job, not this function's) is
    mandatory because ``runner.scan_folders`` uses
    ``multiprocessing.get_context("spawn")``, which needs a real OS thread to
    call from. ``scan_folders`` has no cancel hook and reports nothing until
    it returns, so the worklist is scanned in chunks of ``4 * workers``,
    checking for a stop request between chunks (one Pool teardown per chunk —
    negligible against chunks that take minutes of audio decode).

    After the scan — including after a stop, since a partial scan is worth
    scoring — always reranks. Records two ``refresh_step_runs`` rows
    (``ranker_scan``, ``ranker_rerank``) and stamps both version hashes on
    success.

    Args:
        worklist: ``(lb, disk_path, source_class)`` tuples, from ``plan_scan``.
        scan_id: The ``quality_scans`` row to scan into, from ``plan_scan``.
        workers: Requested consumer-process count; resolved via
            ``_resolve_workers`` (clamped, frozen-build override).
        db_path: Optional database path override.

    Returns:
        ``{"scan_status", "scanned_ok", "planned", "rerank_rows", "stopped"}``.
    """
    resolved_workers = _resolve_workers(workers)
    scan_started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = repo.connect(db_path)
    repo.ensure_schema(conn)

    from concert_ranker.runner import scan_folders

    total = len(worklist)
    chunk_size = max(1, 4 * resolved_workers)
    _JOB.update(stage="scanning", total=total, done=0, errors=0)

    scanned_ok = 0
    stopped = False
    try:
        try:
            for i in range(0, total, chunk_size):
                chunk = worklist[i:i + chunk_size]
                results = scan_folders(
                    chunk, scan_id, db_path=db_path, workers=resolved_workers, skip_done=False,
                )
                scanned_ok += sum(1 for r in results if r["status"] == "done")
                _JOB.update(done=min(i + len(chunk), total))
                _JOB.check_stop()
        except JobStopped:
            stopped = True

        scan_status = "stopped" if stopped else "ok"
        record_step_run(
            "ranker_scan", status=scan_status, started_at=scan_started_at,
            counters={"planned": total, "scanned_ok": scanned_ok}, trigger_source="route",
            db_path=db_path,
        )
        if scan_status == "ok":
            config_version.stamp_for_step("ranker_scan", db_path)

        _JOB.update(stage="reranking")
        rerank_started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        rerank_status = "ok"
        n = 0
        try:
            n = rerank(conn, scan_id)
        except Exception:
            rerank_status = "error"
            raise
        finally:
            record_step_run(
                "ranker_rerank", status=rerank_status, started_at=rerank_started_at,
                counters={"rows": n}, trigger_source="route", db_path=db_path,
            )
            if rerank_status == "ok":
                config_version.stamp_for_step("ranker_rerank", db_path)

        return {
            "scan_status": scan_status, "scanned_ok": scanned_ok, "planned": total,
            "rerank_rows": n, "stopped": stopped,
        }
    finally:
        _JOB.finish(stage="done")


def run_rerank(scan_id: int | None = None, db_path: str | None = None) -> dict:
    """Re-band/rank from stored metrics only (no audio). Synchronous, pure-DB.

    The route calls this inline (not via a thread) and 409s while a scan is
    running, so as not to race the scan's own trailing rerank.

    Args:
        scan_id: Scan to rerank; defaults to the latest scan.
        db_path: Optional database path override.

    Returns:
        ``{"ok": True, "scan_id", "rows"}``.

    Raises:
        ValueError: no scans exist and *scan_id* was not given.
    """
    conn = repo.connect(db_path)
    repo.ensure_schema(conn)
    resolved_scan_id = scan_id if scan_id is not None else repo.latest_scan_id(conn)
    if resolved_scan_id is None:
        raise ValueError("no scans exist")

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "ok"
    n = 0
    try:
        n = rerank(conn, resolved_scan_id)
    except Exception:
        status = "error"
        raise
    finally:
        record_step_run(
            "ranker_rerank", status=status, started_at=started_at,
            counters={"rows": n}, trigger_source="route", db_path=db_path,
        )
        if status == "ok":
            config_version.stamp_for_step("ranker_rerank", db_path)

    return {"ok": True, "scan_id": resolved_scan_id, "rows": n}
