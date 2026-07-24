"""File-level collection integrity — bit-rot detection over every file (TODO-267).

Complements, rather than replaces, the two hash stores that already exist:

* ``pipeline_file_hash`` is a **cache** keyed on ``(size, mtime)``. Bit rot does
  not touch mtime, so a stat-keyed cache can never observe it — a rotted file
  looks identical to a clean one and the cached hash is simply returned.
* ``collection_integrity_status`` (:mod:`backend.integrity_monitor`) is
  **manifest-driven**: it checks only files claimed by an ``lbdir*.txt``, folder
  by folder, and decodes FLAC audio to compute ffp. That decode is what makes it
  slow, and folders with no manifest are skipped entirely.

This module walks every file under a collection mount and keeps a durable hash
inventory in ``file_inventory``, so a later full re-read can be compared against
a known-good baseline.

Three entry points, and the distinction between the first two is the whole point:

:func:`scan_mount` with ``mode='index'``
    Stat-driven. Hashes only files that are new or whose ``(size, mtime)``
    moved. Cheap (minutes) — keeps the inventory current. Cannot detect rot.

:func:`scan_mount` with ``mode='verify'``
    Re-reads every file and compares to the stored hash. The only thing that
    detects rot. I/O-bound end to end (~11 h per mount here).

:func:`verify_batch`
    The rolling nightly slice. Picks files in oldest-``last_verified`` order
    from ``file_inventory`` rather than walking the tree, so successive nights
    advance through the collection instead of re-checking the same head of the
    walk forever.

The triage that makes a mismatch actionable:

===================  ==================  ==========================================
hash                 size + mtime        verdict
===================  ==================  ==========================================
differs              unchanged           ``rot`` — silent corruption; baseline kept
differs              changed             ``changed`` — legitimate edit; re-baselined
unreadable           n/a                 ``unreadable`` — I/O error, likely failing disk
row present, no file n/a                 ``missing``
===================  ==================  ==========================================

On ``rot`` the stored hash is deliberately **not** overwritten: it is the
known-good baseline you need to confirm a restore actually fixed the file.

Speed comes from I/O strategy, not the digest. Measured on this collection:
disk reads run ~181 MB/s while xxh3_128 runs ~23.9 GB/s and sha256 ~2.2 GB/s, so
both digests are computed in a single read pass and the second one is free.
Scans run one worker per mount — parallel across spindles, strictly serial
within a mount, because concurrent readers on one HDD trade sequential
throughput for seek thrash.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import xxhash

from backend import db as database
from backend.filer import normalise_path

_log = logging.getLogger(__name__)

#: Read size per chunk. Large enough to keep a spinning disk streaming, small
#: enough that cancellation stays responsive on a slow mount.
CHUNK_SIZE = 4 * 1024 * 1024

#: Rows accumulated before a write-queue round trip. A per-file write would
#: dominate the runtime of an index scan.
BATCH_SIZE = 500

#: Directory names never walked — none of these hold collection audio.
SKIP_DIRS = frozenset({".git", "$RECYCLE.BIN", "System Volume Information", ".Trash-1000"})

_JOB_LOCK = threading.Lock()
_JOBS: dict[int, dict] = {}          # mount_id -> progress dict
_CANCEL: dict[int, threading.Event] = {}
_THREADS: dict[int, threading.Thread] = {}

ProgressCb = Callable[[dict], None]


def hash_file(path: Path, chunk_size: int = CHUNK_SIZE) -> dict[str, Any]:
    """Compute xxh3_128 and sha256 for one file in a single read pass.

    Args:
        path: File to read.
        chunk_size: Bytes per read call.

    Returns:
        Dict with keys ``xxh3``, ``sha256``, ``size``, ``mtime``, ``bytes_read``.
        Size and mtime are stat'd *before* the read, so they describe the bytes
        just hashed.

    Raises:
        OSError: If the file cannot be stat'd or read.
    """
    st = path.stat()
    x = xxhash.xxh3_128()
    s = hashlib.sha256()
    read = 0
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            x.update(block)
            s.update(block)
            read += len(block)
    return {
        "xxh3": x.hexdigest(),
        "sha256": s.hexdigest(),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "bytes_read": read,
    }


def _new_counts() -> dict[str, int]:
    """Return a zeroed aggregate-counts dict for a scan."""
    return {
        "files_seen": 0, "files_hashed": 0, "files_new": 0, "files_ok": 0,
        "files_rot": 0, "files_changed": 0, "files_missing": 0,
        "files_unreadable": 0, "bytes_hashed": 0,
    }


class _Sink:
    """Batches per-file verdicts and flushes them through the write queue.

    Shared by the tree-walking scan and the rolling batch verify so both apply
    identical triage and identical write batching.

    Args:
        mount_id: Mount these rows belong to.
    """

    def __init__(self, mount_id: int) -> None:
        self.mount_id = mount_id
        self.counts = _new_counts()
        self._upserts: list[dict] = []
        self._verified: list[tuple[int, str]] = []
        self._flagged: list[tuple[str, int, str]] = []

    def _baseline(self, rel: str, lb_number: int | None, h: dict) -> None:
        """Queue a full row write for a new or legitimately-changed file."""
        self._upserts.append({
            "mount_id": self.mount_id, "rel_path": rel, "lb_number": lb_number,
            "size": h["size"], "mtime": h["mtime"], "xxh3": h["xxh3"],
            "sha256": h["sha256"], "status": "ok", "last_verified": None,
        })

    def triage(
        self, full: Path, rel: str, row: dict | None, lb_number: int | None,
        h: dict, stat_same: bool,
    ) -> None:
        """Classify one freshly-hashed file and queue the resulting writes.

        Args:
            full: Absolute path, for logging and event rows.
            rel: Path relative to the mount root — the inventory key.
            row: Existing ``file_inventory`` row, or None if never seen.
            lb_number: Owning LB number, if resolvable.
            h: Result of :func:`hash_file`.
            stat_same: Whether size and mtime match the stored row. Only
                meaningful when ``row`` is not None.
        """
        self.counts["files_hashed"] += 1
        self.counts["bytes_hashed"] += h["bytes_read"]

        if row is None:
            self.counts["files_new"] += 1
            self._baseline(rel, lb_number, h)
        elif h["xxh3"] == row["xxh3"]:
            self.counts["files_ok"] += 1
            self._verified.append((self.mount_id, rel))
        elif stat_same:
            # Content moved while size and mtime did not — this is bit rot. The
            # stored hash is preserved as the known-good baseline.
            self.counts["files_rot"] += 1
            self._flagged.append(("rot", self.mount_id, rel))
            _log.error("file_integrity: BIT ROT %s (stored %s, now %s)",
                       full, row["xxh3"], h["xxh3"])
            database.log_integrity_event(
                lb_number or 0, str(full), "file_rot",
                f"content changed with identical size/mtime — "
                f"baseline xxh3 {row['xxh3']}, now {h['xxh3']}",
                self.mount_id,
            )
        else:
            # Size or mtime moved too: a legitimate edit (retag, replace).
            self.counts["files_changed"] += 1
            self._baseline(rel, lb_number, h)
            database.log_integrity_event(
                lb_number or 0, str(full), "file_changed",
                f"file edited since baseline — re-hashed (xxh3 {h['xxh3']})",
                self.mount_id,
            )

    def unreadable(self, full: Path, rel: str, row: dict | None, exc: OSError) -> None:
        """Record a file that could not be read — usually a failing disk.

        Args:
            full: Absolute path.
            rel: Inventory key.
            row: Existing row, if any.
            exc: The raised OSError.
        """
        self.counts["files_unreadable"] += 1
        _log.warning("file_integrity: unreadable %s: %s", full, exc)
        if row is not None:
            self._flagged.append(("unreadable", self.mount_id, rel))
            database.log_integrity_event(
                row.get("lb_number") or 0, str(full), "file_unreadable",
                f"I/O error reading file: {exc}", self.mount_id,
            )

    def missing(self, full: Path, rel: str, row: dict) -> None:
        """Record an inventoried file that is no longer on disk.

        Args:
            full: Absolute path it used to occupy.
            rel: Inventory key.
            row: The stored row.
        """
        self.counts["files_missing"] += 1
        self._flagged.append(("missing", self.mount_id, rel))
        database.log_integrity_event(
            row.get("lb_number") or 0, str(full), "file_missing",
            "file in inventory no longer present on disk", self.mount_id,
        )

    def flush(self, force: bool = False) -> None:
        """Write queued rows once any batch is full, or unconditionally.

        Args:
            force: Flush every queue regardless of size.
        """
        if self._upserts and (force or len(self._upserts) >= BATCH_SIZE):
            database.upsert_file_inventory(self._upserts)
            self._upserts = []
        if self._verified and (force or len(self._verified) >= BATCH_SIZE):
            database.touch_file_inventory_verified(self._verified)
            self._verified = []
        if self._flagged and (force or len(self._flagged) >= BATCH_SIZE):
            database.mark_file_inventory_status(self._flagged)
            self._flagged = []


def _lb_index(mount_root: Path) -> dict[str, int]:
    """Map normalised folder path -> lb_number for entries under one mount.

    Args:
        mount_root: Absolute mount root path.

    Returns:
        Mapping of normalised absolute folder path to LB number.
    """
    root = normalise_path(str(mount_root)).rstrip("/")
    index: dict[str, int] = {}
    for row in database.get_collection():
        disk_path = row.get("disk_path")
        if not disk_path:
            continue
        norm = normalise_path(disk_path).rstrip("/")
        if norm == root or norm.startswith(root + "/"):
            index[norm] = row["lb_number"]
    return index


def _resolve_lb(file_path: Path, mount_root: Path, index: dict[str, int]) -> int | None:
    """Find the LB number owning a file by walking up to the mount root.

    Args:
        file_path: Absolute path of the file.
        mount_root: Absolute mount root — the walk stops here.
        index: Mapping from :func:`_lb_index`.

    Returns:
        The owning LB number, or None if the file sits outside any LB folder.
    """
    root = normalise_path(str(mount_root)).rstrip("/")
    parent = file_path.parent
    for _ in range(6):  # LB folders sit shallow; bail rather than walk forever
        norm = normalise_path(str(parent)).rstrip("/")
        if norm in index:
            return index[norm]
        if norm == root or parent == parent.parent:
            return None
        parent = parent.parent
    return None


def _walk_files(mount_root: Path):
    """Yield every regular file under a mount root, skipping symlinks.

    Symlinks are skipped so a link farm cannot double-count bytes or loop.

    Args:
        mount_root: Directory to walk.

    Yields:
        Absolute ``Path`` objects.
    """
    for dirpath, dirnames, filenames in os.walk(mount_root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.is_symlink() or not full.is_file():
                    continue
            except OSError:
                continue
            yield full


def _stat_matches(row: dict | None, size: int, mtime: float) -> bool:
    """Return whether a stored row's size and mtime match a fresh stat.

    Args:
        row: Stored inventory row, or None.
        size: Fresh ``st_size``.
        mtime: Fresh ``st_mtime``.
    """
    return (
        row is not None and row["size"] == size
        and abs(row["mtime"] - mtime) < 1e-6
    )


def _resolve_mount(mount_id: int) -> tuple[dict, Path]:
    """Look up a mount and confirm its root is currently readable.

    Args:
        mount_id: ``collection_mounts.id``.

    Returns:
        The mount row and its root ``Path``.

    Raises:
        ValueError: If the mount id is unknown.
        FileNotFoundError: If the root is not present (disk offline).
    """
    mounts = {m["id"]: m for m in database.get_collection_mounts()}
    mount = mounts.get(mount_id)
    if mount is None:
        raise ValueError(f"unknown mount_id {mount_id}")
    root = Path(mount["root_path"])
    if not root.is_dir():
        raise FileNotFoundError(f"mount root not available (offline?): {root}")
    return mount, root


def _begin_progress(mount_id: int, mode: str, scan_id: int, label: str | None,
                    counts: dict) -> dict:
    """Register and return the live progress dict for a run.

    Args:
        mount_id: Mount being scanned.
        mode: Scan mode.
        scan_id: Row id in ``file_integrity_scans``.
        label: Mount label for display.
        counts: The live counts dict (shared by reference).
    """
    progress = {
        "running": True, "mount_id": mount_id, "mode": mode, "scan_id": scan_id,
        "label": label, "current": None, "counts": counts, "total": None,
        "elapsed": 0.0, "stopped_reason": None,
    }
    with _JOB_LOCK:
        _JOBS[mount_id] = progress
    return progress


def _end_progress(progress: dict, status: str, started: float,
                  error: str | None) -> None:
    """Mark a run finished in the progress dict.

    Args:
        progress: The dict from :func:`_begin_progress`.
        status: Final status.
        started: ``time.monotonic()`` at start.
        error: Error message, if any.
    """
    progress.update({
        "running": False, "current": None, "status": status,
        "elapsed": time.monotonic() - started, "error": error,
    })
    with _JOB_LOCK:
        _JOBS[progress["mount_id"]] = progress


def _log_result(mode: str, mount_id: int, status: str, counts: dict) -> None:
    """Emit the one-line summary for a finished run.

    Args:
        mode: Scan mode.
        mount_id: Mount scanned.
        status: Final status.
        counts: Aggregate counts.
    """
    _log.info(
        "file_integrity: %s scan of mount %s finished (%s) — %s files, %s hashed, "
        "%.1f GB, %s new, %s rot, %s changed, %s missing, %s unreadable",
        mode, mount_id, status, counts["files_seen"], counts["files_hashed"],
        counts["bytes_hashed"] / 1e9, counts["files_new"], counts["files_rot"],
        counts["files_changed"], counts["files_missing"], counts["files_unreadable"],
    )


def scan_mount(
    mount_id: int,
    mode: str = "index",
    cancel_event: threading.Event | None = None,
    progress_cb: ProgressCb | None = None,
    max_seconds: float | None = None,
) -> dict:
    """Index or deep-verify every file on one collection mount.

    Blocking — run from a background thread via :func:`start_scan`.

    Missing-file detection only runs on a **complete** pass: a cancelled or
    budget-stopped run would otherwise declare the untouched remainder missing.

    Args:
        mount_id: ``collection_mounts.id`` to scan.
        mode: ``index`` (stat-skip, fast) or ``verify`` (full re-read).
        cancel_event: Set to stop the scan early and mark it cancelled.
        progress_cb: Called with the live progress dict as work proceeds.
        max_seconds: Wall-clock budget; the scan stops cleanly when exceeded.

    Returns:
        The aggregate counts dict recorded on the scan row.

    Raises:
        ValueError: If the mount is unknown or ``mode`` is not index/verify.
        FileNotFoundError: If the mount root is not present (disk offline).
    """
    if mode not in ("index", "verify"):
        raise ValueError(f"mode must be 'index' or 'verify', got {mode!r}")

    mount, mount_root = _resolve_mount(mount_id)
    scan_id = database.record_file_scan_start(mount_id, mode)
    sink = _Sink(mount_id)
    counts = sink.counts
    started = time.monotonic()
    final_status = "done"
    error: str | None = None

    known = database.get_file_inventory_rows(mount_id)
    lb_index = _lb_index(mount_root)
    seen: set[str] = set()
    root_prefix = normalise_path(str(mount_root)).rstrip("/") + "/"
    progress = _begin_progress(mount_id, mode, scan_id, mount.get("label"), counts)

    try:
        for full in _walk_files(mount_root):
            if cancel_event is not None and cancel_event.is_set():
                final_status = "cancelled"
                progress["stopped_reason"] = "cancelled"
                break
            if max_seconds is not None and time.monotonic() - started > max_seconds:
                final_status = "partial"
                progress["stopped_reason"] = "time_budget"
                break

            norm = normalise_path(str(full))
            rel = norm[len(root_prefix):] if norm.startswith(root_prefix) else norm
            seen.add(rel)
            counts["files_seen"] += 1
            progress["current"] = rel
            progress["elapsed"] = time.monotonic() - started

            row = known.get(rel)
            try:
                st = full.stat()
            except OSError:
                continue  # vanished mid-walk; the missing sweep will catch it

            stat_same = _stat_matches(row, st.st_size, st.st_mtime)

            # Index mode reads only what it must; verify mode always re-reads.
            if mode == "index" and stat_same:
                continue

            try:
                h = hash_file(full)
            except OSError as exc:
                sink.unreadable(full, rel, row, exc)
                sink.flush()
                continue

            lb_number = (
                row["lb_number"] if row else _resolve_lb(full, mount_root, lb_index)
            )
            sink.triage(full, rel, row, lb_number, h, stat_same)
            sink.flush()
            if progress_cb is not None:
                progress_cb(progress)

        # Missing-file detection needs a complete pass: a cancelled or
        # budget-stopped run never reached the tail of the walk and would
        # otherwise declare every untouched file missing.
        if final_status == "done":
            for rel, row in known.items():
                if rel in seen or row["status"] == "missing":
                    continue
                sink.missing(mount_root / rel, rel, row)

        sink.flush(force=True)

    except Exception as exc:  # noqa: BLE001 — recorded on the scan row
        final_status = "error"
        error = str(exc)
        _log.exception("file_integrity: scan failed for mount %s", mount_id)
        try:
            sink.flush(force=True)
        except Exception:
            _log.exception("file_integrity: final flush failed for mount %s", mount_id)
    finally:
        database.finish_file_scan(scan_id, final_status, counts, error)
        _end_progress(progress, final_status, started, error)

    _log_result(mode, mount_id, final_status, counts)
    return counts


def verify_batch(
    mount_id: int,
    limit: int = 5000,
    cancel_event: threading.Event | None = None,
    progress_cb: ProgressCb | None = None,
    max_seconds: float | None = None,
) -> dict:
    """Deep-verify the files most overdue for a check on one mount.

    The rolling nightly slice. Unlike :func:`scan_mount`, this does not walk the
    tree — it pulls rows in oldest-``last_verified`` order, so each run advances
    through the collection instead of re-checking the head of the walk. Files
    that verify clean have ``last_verified`` moved to now and drop to the back of
    the queue.

    Never-verified rows sort first (SQLite orders NULLs first on ASC), so a fresh
    baseline drains completely before anything is re-checked.

    Args:
        mount_id: ``collection_mounts.id`` to draw from.
        limit: Maximum files to examine this run.
        cancel_event: Set to stop early.
        progress_cb: Called with the live progress dict as work proceeds.
        max_seconds: Wall-clock budget; stops cleanly when exceeded.

    Returns:
        The aggregate counts dict recorded on the scan row.

    Raises:
        ValueError: If the mount is unknown.
        FileNotFoundError: If the mount root is not present (disk offline).
    """
    mount, mount_root = _resolve_mount(mount_id)
    scan_id = database.record_file_scan_start(mount_id, "verify")
    sink = _Sink(mount_id)
    counts = sink.counts
    started = time.monotonic()
    final_status = "done"
    error: str | None = None

    rows = database.get_rolling_verify_batch(mount_id, limit)
    progress = _begin_progress(mount_id, "verify", scan_id, mount.get("label"), counts)
    progress["total"] = len(rows)

    try:
        for row in rows:
            if cancel_event is not None and cancel_event.is_set():
                final_status = "cancelled"
                progress["stopped_reason"] = "cancelled"
                break
            if max_seconds is not None and time.monotonic() - started > max_seconds:
                final_status = "partial"
                progress["stopped_reason"] = "time_budget"
                break

            rel = row["rel_path"]
            full = mount_root / rel
            counts["files_seen"] += 1
            progress["current"] = rel
            progress["elapsed"] = time.monotonic() - started

            try:
                st = full.stat()
            except OSError:
                sink.missing(full, rel, row)
                sink.flush()
                continue

            try:
                h = hash_file(full)
            except OSError as exc:
                sink.unreadable(full, rel, row, exc)
                sink.flush()
                continue

            sink.triage(
                full, rel, row, row["lb_number"], h,
                _stat_matches(row, st.st_size, st.st_mtime),
            )
            sink.flush()
            if progress_cb is not None:
                progress_cb(progress)

        sink.flush(force=True)

    except Exception as exc:  # noqa: BLE001 — recorded on the scan row
        final_status = "error"
        error = str(exc)
        _log.exception("file_integrity: rolling verify failed for mount %s", mount_id)
        try:
            sink.flush(force=True)
        except Exception:
            _log.exception("file_integrity: final flush failed for mount %s", mount_id)
    finally:
        database.finish_file_scan(scan_id, final_status, counts, error)
        _end_progress(progress, final_status, started, error)

    _log_result("verify(rolling)", mount_id, final_status, counts)
    return counts


def start_scan(
    mount_id: int,
    mode: str = "index",
    max_seconds: float | None = None,
    limit: int | None = None,
) -> bool:
    """Start a background scan of one mount, if none is already running on it.

    One worker per mount: concurrent scans of *different* mounts are allowed and
    encouraged (separate spindles), a second scan of the *same* mount is refused.

    Args:
        mount_id: Mount to scan.
        mode: ``index``, ``verify`` (full sweep), or ``rolling`` (overdue slice).
        max_seconds: Optional wall-clock budget.
        limit: Row cap for ``rolling`` mode.

    Returns:
        True if a scan was started, False if one was already running.
    """
    with _JOB_LOCK:
        existing = _THREADS.get(mount_id)
        if existing is not None and existing.is_alive():
            return False
        cancel = threading.Event()
        _CANCEL[mount_id] = cancel

    def _run() -> None:
        try:
            if mode == "rolling":
                verify_batch(mount_id, limit=limit or 5000, cancel_event=cancel,
                             max_seconds=max_seconds)
            else:
                scan_mount(mount_id, mode, cancel_event=cancel,
                           max_seconds=max_seconds)
        except Exception:
            _log.exception("file_integrity: background scan crashed (mount %s)", mount_id)

    thread = threading.Thread(
        target=_run, name=f"file-integrity-{mount_id}", daemon=True
    )
    with _JOB_LOCK:
        _THREADS[mount_id] = thread
    thread.start()
    return True


def cancel_scan(mount_id: int) -> bool:
    """Signal a running scan on one mount to stop.

    Args:
        mount_id: Mount whose scan should stop.

    Returns:
        True if a running scan was signalled.
    """
    with _JOB_LOCK:
        thread = _THREADS.get(mount_id)
        event = _CANCEL.get(mount_id)
    if thread is not None and thread.is_alive() and event is not None:
        event.set()
        return True
    return False


def get_status(mount_id: int | None = None) -> dict:
    """Return live progress for one mount, or all mounts.

    Args:
        mount_id: If given, return just that mount's progress dict.

    Returns:
        The mount's progress dict, or ``{mount_id: progress}`` for all mounts.
    """
    with _JOB_LOCK:
        if mount_id is not None:
            return dict(_JOBS.get(mount_id, {"running": False, "mount_id": mount_id}))
        return {mid: dict(p) for mid, p in _JOBS.items()}


def rolling_verify(
    budget_seconds: float = 7200.0, files_per_mount: int = 5000
) -> dict[int, bool]:
    """Kick off a budgeted rolling deep verify on every online mount.

    The nightly job. Each mount gets its own worker and its own slice of the
    budget; files are drawn oldest-``last_verified`` first, so successive nights
    sweep the whole collection without any single long blocking run.

    Args:
        budget_seconds: Wall-clock budget per mount.
        files_per_mount: Cap on files examined per mount per run.

    Returns:
        Mapping of mount_id -> whether a scan was started.
    """
    started: dict[int, bool] = {}
    for mount in database.get_collection_mounts():
        root = Path(mount["root_path"])
        if not root.is_dir():
            _log.info("file_integrity: skipping offline mount %s", mount["label"])
            started[mount["id"]] = False
            continue
        started[mount["id"]] = start_scan(
            mount["id"], "rolling",
            max_seconds=budget_seconds, limit=files_per_mount,
        )
    return started
