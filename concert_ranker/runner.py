"""Scan run loops — minimal, crash=scrap.

Two entry points share one unit of work (:func:`process_recording`):

* :func:`scan_folders` — direct driver. A pool of worker processes scans a
  worklist of folders in place. This is what the CLI uses for ``--lb`` / a
  curated sample / any case where the audio is already on fast storage.

* :func:`run_staged` — the full-corpus loop for 15k recordings spread over slow
  HDDs. Producer processes (one per drive) walk their drive in on-disk order and
  copy each folder to fast staging, blocking on a bounded queue; consumer
  processes drain it, scan, persist ONE transaction, and delete the staged copy.

Crash=scrap (design decision #6): a worker computes the whole folder in memory
and commits a single transaction at the end. A crash before commit persists
nothing, so there is nothing half-written to clean up. Restarts simply skip LBs
already present for the scan (``repo.done_lbs``). No watermark/state machine.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import shutil
from pathlib import Path

from concert_ranker.lb import repo
from concert_ranker.scan import scan_folder

log = logging.getLogger("concert_ranker.runner")

# Work item: (lb_number, folder_path, source_class). source_class may be None.
WorkItem = tuple[int, str, "str | None"]


def group_by_device(items: list[WorkItem]) -> dict[str, list[WorkItem]]:
    """Group work items by the physical device their folder lives on.

    Uses ``st_dev`` so each producer in :func:`run_staged` walks exactly one
    spindle — the point of staging is that one producer per drive copies forward
    while consumers decode from fast storage, instead of N readers thrashing one
    HDD head. Folders that can't be stat'd are bucketed under ``"?"``.
    """
    import os

    buckets: dict[str, list[WorkItem]] = {}
    for item in items:
        try:
            key = str(os.stat(item[1]).st_dev)
        except OSError:
            key = "?"
        buckets.setdefault(key, []).append(item)
    return buckets


def process_recording(item: WorkItem, scan_id: int, db_path: str | None) -> dict:
    """Scan one folder and persist its raw metrics in a single transaction.

    Returns a status dict; never raises — a failed recording is logged and
    skipped (crash=scrap at the granularity of one recording).
    """
    lb_number, folder, source_class = item
    try:
        result = scan_folder(folder)
        metric_json = repo.build_metric_json(
            result["metrics"], result["tracks"],
            completeness=None, duration_sec=result["duration_sec"],
        )
        conn = repo.connect(db_path)
        try:
            repo.persist_recording(
                conn, scan_id, lb_number, source_class, metric_json,
                completeness=None, duration_sec=result["duration_sec"],
            )
        finally:
            conn.close()
        return {"lb_number": lb_number, "status": "done",
                "n_tracks": result["n_tracks"]}
    except Exception as e:  # noqa: BLE001 — crash=scrap: log and move on
        log.warning("LB%s scan failed (%s): %s", lb_number, folder, e)
        return {"lb_number": lb_number, "status": "failed", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Direct driver (worklist already on fast storage)
# ─────────────────────────────────────────────────────────────────────────────
def _scan_one(packed):
    item, scan_id, db_path = packed
    return process_recording(item, scan_id, db_path)


def scan_folders(items: list[WorkItem], scan_id: int, *, db_path: str | None = None,
                 workers: int = 16, skip_done: bool = True) -> list[dict]:
    """Scan a worklist of folders with a process pool.

    Args:
        items: ``(lb_number, folder_path, source_class)`` tuples.
        scan_id: The ``quality_scans`` row these belong to.
        db_path: Target DB (None = default LosslessBob DB).
        workers: Consumer process count.
        skip_done: Skip LBs already persisted for this scan (restart-safe).
    """
    if skip_done:
        conn = repo.connect(db_path)
        try:
            done = repo.done_lbs(conn, scan_id)
        finally:
            conn.close()
        items = [it for it in items if it[0] not in done]
    if not items:
        return []
    packed = [(it, scan_id, db_path) for it in items]
    results: list[dict] = []
    n = max(1, min(workers, len(packed)))
    if n == 1:
        return [_scan_one(p) for p in packed]
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=n) as pool:
        for res in pool.imap_unordered(_scan_one, packed):
            results.append(res)
            log.info("LB%s: %s", res["lb_number"], res["status"])
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Staged producer/consumer loop (slow HDDs → fast staging → scan → delete)
# ─────────────────────────────────────────────────────────────────────────────
_STOP = "__STOP__"


def _producer(items: list[WorkItem], staging_dir: str, queue: mp.Queue,
              done: set[int]) -> None:
    """Copy each pending folder to staging and enqueue the staged work item."""
    staging = Path(staging_dir)
    for lb_number, folder, source_class in items:
        if lb_number in done:
            continue
        dest = staging / str(lb_number)
        try:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(folder, dest)
        except Exception as e:  # noqa: BLE001
            log.warning("LB%s stage copy failed (%s): %s", lb_number, folder, e)
            continue
        queue.put((lb_number, str(dest), source_class))  # blocks when queue full


def _consumer(queue: mp.Queue, scan_id: int, db_path: str | None) -> None:
    """Drain staged work items, scan, persist, delete the staged copy."""
    while True:
        item = queue.get()
        if item == _STOP:
            return
        lb_number, staged_path, source_class = item
        process_recording((lb_number, staged_path, source_class), scan_id, db_path)
        shutil.rmtree(staged_path, ignore_errors=True)


def run_staged(items_by_drive: dict[str, list[WorkItem]], staging_dir: str,
               scan_id: int, *, db_path: str | None = None,
               n_consumers: int = 16, queue_max: int = 40) -> None:
    """Run the full staging loop: one producer per drive, N consumers.

    Args:
        items_by_drive: ``{drive_label: [WorkItem, ...]}`` — each list is walked
            by a dedicated producer in the order given (caller sorts by on-disk
            layout to keep the HDD head moving forward).
        staging_dir: Fast (NVMe) directory folders are copied into.
        scan_id: Target scan.
        db_path: Target DB.
        n_consumers: Consumer process count.
        queue_max: Bounded-queue size (back-pressure on producers).
    """
    Path(staging_dir).mkdir(parents=True, exist_ok=True)
    conn = repo.connect(db_path)
    try:
        done = repo.done_lbs(conn, scan_id)
    finally:
        conn.close()

    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue(maxsize=queue_max)

    producers = [
        ctx.Process(target=_producer, args=(items, staging_dir, queue, done))
        for items in items_by_drive.values() if items
    ]
    consumers = [
        ctx.Process(target=_consumer, args=(queue, scan_id, db_path))
        for _ in range(n_consumers)
    ]
    for c in consumers:
        c.start()
    for p in producers:
        p.start()
    for p in producers:
        p.join()
    # Producers done → tell every consumer to stop, then wait them out.
    for _ in consumers:
        queue.put(_STOP)
    for c in consumers:
        c.join()
    log.info("staged scan %s complete", scan_id)
