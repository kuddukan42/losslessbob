"""Disk Scanner — find audio folders on disk for bulk collection add (TODO-250).

Walks user-defined root paths with ``os.scandir()`` and early pruning, and
reports every directory that *directly* contains lossless audio files. The
result is a candidate list for the "Add Selected to Collection" flow; nothing
is indexed or persisted — each scan is one-shot on demand.

The background-job shape (module-level job dict + lock, ``start_scan_async`` /
``get_scan_status`` / ``cancel_scan``) deliberately mirrors
``integrity_monitor``, so the GUI polls both the same way.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

from backend import db as database
from backend.filer import normalise_path

_log = logging.getLogger(__name__)

# Lossless containers only — the scanner exists to find *collection* material,
# and an mp3 folder is never that.
DEFAULT_EXTENSIONS: tuple[str, ...] = (".flac", ".wav", ".ape", ".m4a", ".aiff", ".aif", ".shn")

# Directory names never worth descending into. Matched case-insensitively
# against the directory's own name, so they prune at any depth.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "node_modules", ".git", ".svn", "__pycache__", ".cache", "venv", ".venv",
    "proc", "sys", "dev", "run", "snap", "lost+found", "$recycle.bin",
    "system volume information", "windows", "program files", "program files (x86)",
    "appdata",
)

_LB_RE = re.compile(r"LB-(\d+)", re.IGNORECASE)

_SCAN_LOCK = threading.Lock()
_SCAN_JOB: dict = {
    "running": False,
    "roots": [],
    "dirs_scanned": 0,
    "found": 0,
    "current_dir": None,
    "results": None,
    "error": None,
    "cancelled": False,
}
_CANCEL_EVENT: threading.Event | None = None
_SCAN_THREAD: threading.Thread | None = None


def _collection_paths(db_path=None) -> dict[str, int]:
    """Map every my_collection disk_path to its LB number, normalised for compare.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        Dict of normalised disk path → lb_number.
    """
    out: dict[str, int] = {}
    with database.get_connection(db_path) as conn:
        for row in conn.execute("SELECT lb_number, disk_path FROM my_collection"):
            if row["disk_path"]:
                out[normalise_path(row["disk_path"]).rstrip("/").lower()] = row["lb_number"]
    return out


def _resolve_lb(folder: Path, known: dict[str, int], db_path=None) -> int | None:
    """Best-effort LB number for a scanned folder.

    Order matches the pipeline's own resolution: an existing my_collection row
    for the path wins (it is a confirmed fact), then an explicit folder→LB pin,
    then the ``LB-NNNNN`` convention in the folder name. Folders that resolve to
    nothing are still listed — they just can't be added, since my_collection
    keys on lb_number.

    Args:
        folder: The scanned directory.
        known: Output of ``_collection_paths`` (avoids a query per folder).
        db_path: Optional path to the SQLite database file.

    Returns:
        LB number, or None if the folder can't be attributed.
    """
    key = normalise_path(str(folder)).rstrip("/").lower()
    if key in known:
        return known[key]
    links = database.get_folder_links(str(folder), db_path=db_path)
    if len(links) == 1:
        return links[0]["lb_number"]
    m = _LB_RE.search(folder.name)
    return int(m.group(1)) if m else None


def _is_excluded(name: str, excludes: set[str]) -> bool:
    """Return True if a directory name should be pruned (hidden or excluded)."""
    lower = name.lower()
    return lower in excludes or (name.startswith(".") and name not in (".", ".."))


def scan_roots(
    roots: list[str],
    extensions: list[str] | None = None,
    excludes: list[str] | None = None,
    cancel_event: threading.Event | None = None,
    db_path=None,
) -> list[dict]:
    """Walk roots and return every directory directly holding lossless audio.

    Symlinked directories are never followed — a symlink into an already-walked
    tree would otherwise loop or double-report folders.

    Args:
        roots: Absolute paths to walk.
        extensions: Audio suffixes to look for (default ``DEFAULT_EXTENSIONS``).
        excludes: Extra directory names to prune, on top of ``DEFAULT_EXCLUDES``.
        cancel_event: Set to abort the walk early; partial results are returned.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of dicts: ``{path, name, file_count, extensions, size_bytes,
        in_collection, lb_number}``, sorted by path.
    """
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in (extensions or DEFAULT_EXTENSIONS)}
    skip = {e.lower() for e in DEFAULT_EXCLUDES} | {e.lower() for e in (excludes or ())}
    known = _collection_paths(db_path)

    results: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        stack = [Path(root)]
        while stack:
            if cancel_event is not None and cancel_event.is_set():
                results.sort(key=lambda r: r["path"])
                return results
            current = stack.pop()
            key = normalise_path(str(current))
            if key in seen:
                continue
            seen.add(key)
            with _SCAN_LOCK:
                _SCAN_JOB["dirs_scanned"] += 1
                _SCAN_JOB["current_dir"] = key
            try:
                entries = list(os.scandir(current))
            except OSError as e:
                _log.debug("disk_scanner: cannot read %s (%s)", current, e)
                continue

            found_exts: set[str] = set()
            file_count = 0
            size_bytes = 0
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not _is_excluded(entry.name, skip):
                            stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        suffix = os.path.splitext(entry.name)[1].lower()
                        if suffix in exts:
                            file_count += 1
                            found_exts.add(suffix)
                            size_bytes += entry.stat().st_size
                except OSError:
                    continue

            if file_count:
                lb = _resolve_lb(current, known, db_path=db_path)
                results.append({
                    "path": key,
                    "name": current.name,
                    "file_count": file_count,
                    "extensions": sorted(found_exts),
                    "size_bytes": size_bytes,
                    "in_collection": key.rstrip("/").lower() in known,
                    "lb_number": lb,
                })
                with _SCAN_LOCK:
                    _SCAN_JOB["found"] = len(results)

    results.sort(key=lambda r: r["path"])
    return results


def start_scan_async(
    roots: list[str],
    extensions: list[str] | None = None,
    excludes: list[str] | None = None,
    db_path=None,
) -> bool:
    """Start a background disk scan if one isn't already running.

    Args:
        roots: Absolute paths to walk.
        extensions: Audio suffixes to look for (default ``DEFAULT_EXTENSIONS``).
        excludes: Extra directory names to prune.
        db_path: Optional path to the SQLite database file.

    Returns:
        True if a new scan was started, False if one is already running.
    """
    global _SCAN_THREAD, _CANCEL_EVENT
    with _SCAN_LOCK:
        if _SCAN_JOB["running"]:
            return False
        _CANCEL_EVENT = threading.Event()
        cancel_event = _CANCEL_EVENT
        _SCAN_JOB.update({
            "running": True,
            "roots": list(roots),
            "dirs_scanned": 0,
            "found": 0,
            "current_dir": None,
            "results": None,
            "error": None,
            "cancelled": False,
        })

    def _run():
        try:
            results = scan_roots(roots, extensions, excludes, cancel_event, db_path)
            with _SCAN_LOCK:
                _SCAN_JOB["results"] = results
                _SCAN_JOB["cancelled"] = cancel_event.is_set()
        except Exception as e:
            _log.exception("disk_scanner: background scan crashed")
            with _SCAN_LOCK:
                _SCAN_JOB["error"] = str(e)
                _SCAN_JOB["results"] = []
        finally:
            with _SCAN_LOCK:
                _SCAN_JOB["running"] = False
                _SCAN_JOB["current_dir"] = None

    _SCAN_THREAD = threading.Thread(target=_run, daemon=True, name="disk-scan")
    _SCAN_THREAD.start()
    return True


def get_scan_status() -> dict:
    """Return a snapshot of the current/last scan for GUI polling."""
    with _SCAN_LOCK:
        return dict(_SCAN_JOB)


def cancel_scan() -> bool:
    """Request cancellation of the running scan.

    Returns:
        True if a running scan was signalled to stop, False if none was running.
    """
    with _SCAN_LOCK:
        if not _SCAN_JOB["running"] or _CANCEL_EVENT is None:
            return False
        _CANCEL_EVENT.set()
        return True


def add_paths_to_collection(paths: list[str], db_path=None) -> list[dict]:
    """Add scanned folders to my_collection, resolving each one's LB number.

    Args:
        paths: Absolute folder paths, as returned by ``scan_roots``.
        db_path: Optional path to the SQLite database file.

    Returns:
        One dict per input path: ``{path, ok, lb_number, error}``. ``ok`` is
        False with ``error='no_lb'`` when the folder can't be attributed, and
        with ``error='already_in_collection'`` when its LB is already filed.
    """
    known = _collection_paths(db_path)
    out: list[dict] = []
    for raw in paths:
        folder = Path(raw)
        lb = _resolve_lb(folder, known, db_path=db_path)
        if lb is None:
            out.append({"path": raw, "ok": False, "lb_number": None, "error": "no_lb"})
            continue
        try:
            added = database.add_to_collection(
                lb, folder.name, normalise_path(str(folder)), db_path=db_path,
            )
        except Exception as e:
            out.append({"path": raw, "ok": False, "lb_number": lb, "error": str(e)})
            continue
        out.append({
            "path": raw,
            "ok": bool(added),
            "lb_number": lb,
            "error": None if added else "already_in_collection",
        })
    return out
