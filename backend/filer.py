"""backend/filer.py — Pipeline step 5: file a folder into the collection."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import shutil
from pathlib import Path, PurePosixPath

from backend import db as database

logger = logging.getLogger(__name__)

MOUNT_CHECK_TIMEOUT = 2.0  # seconds; prevents Flask thread hang on dead UNC paths


# ── Path normalisation ─────────────────────────────────────────────────────────

def normalise_path(raw: str) -> str:
    """Store paths as POSIX strings so they round-trip correctly on Windows and Linux.

    \\\\NAS\\archive is stored as //NAS/archive and pathlib.Path() resolves it back
    to the correct OS-native form on read.
    """
    return PurePosixPath(Path(raw)).as_posix()


# ── Mount reachability (timeout-guarded) ──────────────────────────────────────

def _path_reachable(path: str, timeout: float = MOUNT_CHECK_TIMEOUT) -> bool:
    """Return True if path is an accessible directory, with a hard timeout.

    Uses a thread so a dead NAS/UNC share cannot block the calling thread for
    the OS-level network timeout (which can be 20–30 s on Windows).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(os.path.isdir, path)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return False


# ── Year extraction ────────────────────────────────────────────────────────────

def year_from_date_str(date_str: str) -> int | None:
    """Extract 4-digit year from entries.date_str (M/D/YY or M/D/YYYY).

    The day and month components may be 'xx'; only the year field matters.
    2-digit cutoff: >= 49 → 19xx, else 20xx (matches project convention).
    Returns None only if date_str is empty, missing, or the year field is non-numeric.
    """
    if not date_str:
        return None
    parts = date_str.split("/")
    if len(parts) != 3:
        return None
    y = parts[2].strip()
    if not y.isdigit():
        return None
    y_int = int(y)
    if y_int < 100:
        y_int = 1900 + y_int if y_int >= 49 else 2000 + y_int
    return y_int


# ── Route resolution ───────────────────────────────────────────────────────────

def resolve_destination_for_lb(
    lb_number: int,
    folder_path: str,
    db_path=None,
) -> dict:
    """Resolve the filing destination for a known LB entry.

    Returns a dict with keys:
        ok (bool), year (int|None), mount_id (int|None), mount_label (str),
        mount_root (str), sub_path (str), dest_parent (str), dest (str),
        error (str|None), error_code (str|None)

    error_code is one of: no_date | no_route | mount_offline | dest_exists | db_error
    """
    folder = Path(folder_path)
    folder_name = folder.name

    try:
        entry_data = database.get_entry(lb_number, db_path=db_path)
    except Exception as exc:
        return _err("db_error", f"DB error reading LB-{lb_number:05d}: {exc}")

    if not entry_data:
        return _err("db_error", f"LB-{lb_number:05d} not found in entries")

    date_str = (entry_data.get("entry") or {}).get("date_str") or ""

    year = year_from_date_str(date_str)
    if year is None:
        return _err(
            "no_date",
            f"Cannot determine year from date_str '{date_str}' — no route can be selected",
        )

    try:
        with database.get_connection(db_path) as conn:
            route = conn.execute(
                """SELECT r.year, r.mount_id, r.sub_path,
                          m.label, m.root_path
                   FROM collection_routes r
                   JOIN collection_mounts m ON m.id = r.mount_id
                   WHERE r.year = ?""",
                (year,),
            ).fetchone()
    except Exception as exc:
        return _err("db_error", f"DB error reading routes: {exc}")

    if route is None:
        return _err(
            "no_route",
            f"No route configured for year {year} — add one in Settings → Mounts & Routes",
        )

    mount_label = route["label"]
    mount_root = route["root_path"]
    sub_path = route["sub_path"] or ""

    if not _path_reachable(mount_root):
        return _err(
            "mount_offline",
            f"Mount '{mount_label}' is not accessible at {mount_root}",
        )

    dest_parent = Path(mount_root) / sub_path if sub_path else Path(mount_root)
    dest = dest_parent / folder_name

    if dest.exists():
        return _err("dest_exists", f"Destination already exists: {dest}")

    return {
        "ok": True,
        "year": year,
        "mount_id": route["mount_id"],
        "mount_label": mount_label,
        "mount_root": mount_root,
        "sub_path": sub_path,
        "dest_parent": str(dest_parent),
        "dest": str(dest),
        "error": None,
        "error_code": None,
    }


def _err(code: str, message: str) -> dict:
    return {
        "ok": False,
        "year": None,
        "mount_id": None,
        "mount_label": "",
        "mount_root": "",
        "sub_path": "",
        "dest_parent": "",
        "dest": "",
        "error": message,
        "error_code": code,
    }


# ── Filing execution ───────────────────────────────────────────────────────────

def file_folder(
    lb_number: int,
    folder_path: str,
    file_mode: str = "move",
    db_path=None,
) -> dict:
    """Resolve destination and physically move or copy the folder.

    Args:
        lb_number:   LB number (must be in entries table).
        folder_path: Absolute path to the source folder on disk.
        file_mode:   "move" (default) or "copy".
        db_path:     Optional SQLite path override.

    Returns dict with keys: ok, filed_to, dest, file_mode, error, error_code.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Source folder not found: {folder_path}",
            "error_code": "src_missing",
        }

    resolution = resolve_destination_for_lb(lb_number, folder_path, db_path)
    if not resolution["ok"]:
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": resolution["error"],
            "error_code": resolution["error_code"],
        }

    dest_parent = Path(resolution["dest_parent"])
    dest = Path(resolution["dest"])
    mount_label = resolution["mount_label"]

    try:
        dest_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Cannot create destination directory {dest_parent}: {exc}",
            "error_code": "mkdir_failed",
        }

    try:
        if file_mode == "copy":
            shutil.copytree(str(folder), str(dest))
        else:
            shutil.move(str(folder), str(dest))
    except Exception as exc:
        if file_mode == "copy" and dest.exists():
            try:
                shutil.rmtree(str(dest))
            except Exception:
                pass
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Filesystem {file_mode} failed: {exc}",
            "error_code": "fs_error",
        }

    folder_name = folder.name
    try:
        database.add_to_collection(
            lb_number,
            folder_name,
            str(dest),
            notes=None,
            db_path=db_path,
        )
    except Exception as exc:
        logger.error(
            "file_folder: filesystem %s succeeded but my_collection insert failed "
            "for LB-%05d at %s: %s",
            file_mode,
            lb_number,
            dest,
            exc,
        )
        return {
            "ok": False,
            "filed_to": mount_label,
            "dest": str(dest),
            "file_mode": file_mode,
            "error": (
                f"Folder {file_mode}d to {dest} but collection registration failed: {exc}. "
                "The folder exists on disk — use My Collection → Add folder to register it manually."
            ),
            "error_code": "db_write_failed",
        }

    logger.info(
        "file_folder: LB-%05d %sd to %s (mount: %s)",
        lb_number,
        file_mode,
        dest,
        mount_label,
    )

    return {
        "ok": True,
        "filed_to": mount_label,
        "dest": str(dest),
        "file_mode": file_mode,
        "error": None,
        "error_code": None,
    }
