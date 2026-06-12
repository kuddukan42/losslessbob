"""Collection integrity monitor (TODO-111).

Reuses the existing lbdir batch-verify machinery (checksum_utils.verify_folder_lbdir)
to detect, per collection folder:

- content_issue  — FLAC audio fingerprint (ffp) mismatch: bitrot/corruption/re-encode.
- tag_issue      — full-file MD5 mismatch with ffp pass/na: tags/metadata edited only.
- missing_files  — lbdir-listed files no longer present on disk (deleted/moved).
- no_lbdir       — no lbdir*.txt manifest found for the folder.

Files with overall == 'extra' (on disk but not claimed by the lbdir) are ignored —
this monitor tracks the integrity of known key files, not folder tidiness.
"""

import logging
import threading
from pathlib import Path

from backend import checksum_utils
from backend import db as database
from backend.filer import normalise_path
from backend.paths import find_lbdir_attachment

_log = logging.getLogger(__name__)

_SCAN_LOCK = threading.Lock()
_SCAN_JOB: dict = {
    "running": False,
    "mount_id": None,
    "folders_done": 0,
    "folders_total": 0,
    "current_folder": None,
    "result": None,
}
_CANCEL_EVENT: "threading.Event | None" = None
_SCAN_THREAD: "threading.Thread | None" = None


def _find_lbdir_in_folder(folder: Path) -> "Path | None":
    """Return the first lbdir*.txt found directly in folder, or None."""
    if not folder.exists():
        return None
    for f in folder.iterdir():
        if f.is_file() and "lbdir" in f.name.lower() and f.suffix.lower() == ".txt":
            return f
    return None


def _find_lbdir(folder: Path, lb_number: int) -> "Path | None":
    """Locate the lbdir manifest for a collection folder.

    Tries the folder itself first, then falls back to the lbdir attachment
    stored alongside the site's scraped data files.

    Args:
        folder: Collection folder on disk.
        lb_number: LB number, used to locate the attached lbdir file.

    Returns:
        Path to the lbdir*.txt manifest, or None if not found.
    """
    lbdir = _find_lbdir_in_folder(folder)
    if lbdir is not None:
        return lbdir
    return find_lbdir_attachment(lb_number)


def _classify_verify_result(result: dict) -> dict:
    """Classify a verify_folder_lbdir() result into integrity-monitor categories.

    Files with overall == 'extra' are ignored entirely.

    Args:
        result: Return value of checksum_utils.verify_folder_lbdir().

    Returns:
        Dict with keys status, content_issues, tag_issues, missing_count, total_files.
        status is one of pass, content_issue, tag_issue, missing_files.
    """
    content_issues = 0
    tag_issues = 0
    missing_count = 0
    total_files = 0

    for f in result.get("files", []):
        if f.get("overall") == "extra":
            continue
        total_files += 1
        if f.get("overall") == "missing":
            missing_count += 1
            continue
        if f.get("ffp_status") == "fail":
            content_issues += 1
        elif f.get("md5_status") == "fail":
            tag_issues += 1

    if content_issues > 0:
        status = "content_issue"
    elif missing_count > 0:
        status = "missing_files"
    elif tag_issues > 0:
        status = "tag_issue"
    else:
        status = "pass"

    return {
        "status": status,
        "content_issues": content_issues,
        "tag_issues": tag_issues,
        "missing_count": missing_count,
        "total_files": total_files,
    }


def _mount_for_path(disk_path: str, mounts: list[dict]) -> "int | None":
    """Return the collection_mounts.id whose root_path best matches disk_path.

    Args:
        disk_path: A my_collection.disk_path value.
        mounts: Rows from database.get_collection_mounts().

    Returns:
        The matching mount id, or None if no mount's root_path is a prefix
        of disk_path.
    """
    norm_path = normalise_path(disk_path)
    best_id = None
    best_len = -1
    for m in mounts:
        norm_root = normalise_path(m["root_path"]).rstrip("/")
        if norm_path == norm_root or norm_path.startswith(norm_root + "/"):
            if len(norm_root) > best_len:
                best_len = len(norm_root)
                best_id = m["id"]
    return best_id


def _maybe_log_transition(
    lb_number: int,
    disk_path: str,
    mount_id: "int | None",
    prev_status: "str | None",
    status: str,
    classification: dict,
) -> None:
    """Log an integrity_events row if status represents a meaningful transition."""
    if prev_status == status:
        return
    if status == "content_issue":
        event_type = "content_changed"
        detail = f"{classification['content_issues']} file(s) failed audio fingerprint check"
    elif status == "missing_files":
        event_type = "files_missing"
        detail = f"{classification['missing_count']} file(s) missing from disk"
    elif status == "tag_issue":
        event_type = "tags_changed"
        detail = f"{classification['tag_issues']} file(s) have changed tags/metadata"
    elif status == "pass" and prev_status not in (None, "pass", "no_lbdir"):
        event_type = "restored"
        detail = "Folder now passes integrity verification"
    else:
        return
    database.log_integrity_event(lb_number, disk_path, event_type, detail, mount_id=mount_id)


def scan_collection(mount_id: "int | None" = None, cancel_event: "threading.Event | None" = None) -> dict:
    """Run an lbdir-based integrity scan over the collection (or one mount).

    Blocking — intended to be run from a background thread via start_scan_async().
    Updates the module-level progress dict (see get_scan_status()) as it proceeds,
    and persists per-folder results via database.upsert_collection_integrity_status
    plus transition events via database.log_integrity_event.

    Args:
        mount_id: If given, only scan collection entries under this mount.
            If None, scan the whole collection.
        cancel_event: If set during the scan, stop early and mark the scan cancelled.

    Returns:
        Aggregate folder counts dict, as passed to database.finish_integrity_scan.
    """
    mounts = database.get_collection_mounts()
    rows = database.get_collection()
    if mount_id is not None:
        rows = [r for r in rows if _mount_for_path(r["disk_path"], mounts) == mount_id]

    scan_id = database.record_integrity_scan_start(mount_id)
    counts = {
        "folders_checked": 0,
        "folders_pass": 0,
        "folders_content_issue": 0,
        "folders_tag_issue": 0,
        "folders_missing": 0,
        "folders_no_lbdir": 0,
    }
    final_status = "done"

    with _SCAN_LOCK:
        _SCAN_JOB.update({
            "running": True,
            "mount_id": mount_id,
            "folders_done": 0,
            "folders_total": len(rows),
            "current_folder": None,
            "result": None,
        })

    try:
        prev_rows = {r["lb_number"]: r for r in database.get_collection_integrity_status()}
        for row in rows:
            if cancel_event is not None and cancel_event.is_set():
                final_status = "cancelled"
                break

            lb_number = row["lb_number"]
            disk_path = row["disk_path"]
            with _SCAN_LOCK:
                _SCAN_JOB["current_folder"] = disk_path

            folder = Path(disk_path)
            entry_mount_id = _mount_for_path(disk_path, mounts)
            lbdir_path = _find_lbdir(folder, lb_number)

            if lbdir_path is None:
                classification = {
                    "status": "no_lbdir", "content_issues": 0, "tag_issues": 0,
                    "missing_count": 0, "total_files": 0,
                }
            else:
                try:
                    result = checksum_utils.verify_folder_lbdir(str(folder), str(lbdir_path))
                    classification = _classify_verify_result(result)
                except Exception:
                    _log.exception("integrity_monitor: verify failed for %s", disk_path)
                    classification = {
                        "status": "error", "content_issues": 0, "tag_issues": 0,
                        "missing_count": 0, "total_files": 0,
                    }

            status = classification["status"]
            counts["folders_checked"] += 1
            if status == "pass":
                counts["folders_pass"] += 1
            elif status == "content_issue":
                counts["folders_content_issue"] += 1
            elif status == "tag_issue":
                counts["folders_tag_issue"] += 1
            elif status == "missing_files":
                counts["folders_missing"] += 1
            elif status == "no_lbdir":
                counts["folders_no_lbdir"] += 1

            prev = prev_rows.get(lb_number)
            prev_status = prev["status"] if prev else None
            _maybe_log_transition(lb_number, disk_path, entry_mount_id, prev_status, status, classification)

            database.upsert_collection_integrity_status(
                lb_number=lb_number,
                mount_id=entry_mount_id,
                disk_path=disk_path,
                status=status,
                content_issues=classification["content_issues"],
                tag_issues=classification["tag_issues"],
                missing_count=classification["missing_count"],
                total_files=classification["total_files"],
            )
            if status == "pass":
                database.set_lbdir_verified(disk_path)

            with _SCAN_LOCK:
                _SCAN_JOB["folders_done"] += 1
    except Exception as exc:
        _log.exception("integrity_monitor: scan failed")
        database.finish_integrity_scan(scan_id, "error", counts, error=str(exc))
        with _SCAN_LOCK:
            _SCAN_JOB["running"] = False
            _SCAN_JOB["current_folder"] = None
            _SCAN_JOB["result"] = counts
        return counts

    database.finish_integrity_scan(scan_id, final_status, counts)
    with _SCAN_LOCK:
        _SCAN_JOB["running"] = False
        _SCAN_JOB["current_folder"] = None
        _SCAN_JOB["result"] = counts
    return counts


def start_scan_async(mount_id: "int | None" = None) -> bool:
    """Start a background integrity scan if one isn't already running.

    Args:
        mount_id: If given, scan only this mount; otherwise scan the whole collection.

    Returns:
        True if a new scan was started, False if a scan is already running.
    """
    global _SCAN_THREAD, _CANCEL_EVENT
    with _SCAN_LOCK:
        if _SCAN_JOB["running"]:
            return False
        _CANCEL_EVENT = threading.Event()
        cancel_event = _CANCEL_EVENT

    def _run():
        try:
            scan_collection(mount_id, cancel_event)
        except Exception:
            _log.exception("integrity_monitor: background scan crashed")

    _SCAN_THREAD = threading.Thread(target=_run, daemon=True, name="integrity-scan")
    _SCAN_THREAD.start()
    return True


def get_scan_status() -> dict:
    """Return a snapshot of the current/last scan progress for GUI polling."""
    with _SCAN_LOCK:
        return dict(_SCAN_JOB)


def cancel_scan() -> bool:
    """Request cancellation of the currently running scan, if any.

    Returns:
        True if a running scan was signalled to stop, False if none was running.
    """
    with _SCAN_LOCK:
        if not _SCAN_JOB["running"] or _CANCEL_EVENT is None:
            return False
        _CANCEL_EVENT.set()
        return True
