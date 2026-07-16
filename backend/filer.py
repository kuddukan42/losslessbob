"""backend/filer.py — Pipeline step 5: file a folder into the collection."""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

from backend import db as database

logger = logging.getLogger(__name__)

MOUNT_CHECK_TIMEOUT = 2.0  # seconds; prevents Flask thread hang on dead UNC paths


# ── Path normalisation ─────────────────────────────────────────────────────────

def normalise_path(raw: str) -> str:
    """Store paths as forward-slash strings so they round-trip correctly on Windows and Linux.

    Uses Path.as_posix() which correctly converts Windows separators (c:\\ → c:/)
    and UNC paths (\\\\NAS\\archive → //NAS/archive).
    PurePosixPath(Path(raw)) is intentionally avoided: on Windows it receives the
    backslash-formatted str() of a WindowsPath, treats backslashes as literal chars,
    and returns them unchanged.
    """
    return Path(raw).as_posix()


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


# ── Mount stats (for the Collect mount picker) ─────────────────────────────────

def _human_bytes(n: float) -> str:
    """Format a byte count as a short human-readable string, e.g. '6.4 TB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def get_disk_usage_stats(root_path: str, online: bool) -> dict:
    """Return free/total/used_pct for a mount root, or placeholders if offline/unreadable.

    Args:
        root_path: Filesystem path backing the mount.
        online: Whether the path is currently reachable.

    Returns:
        Dict with free (str), total (str), used_pct (int | None).
    """
    if online:
        try:
            usage = shutil.disk_usage(root_path)
            return {
                "free": _human_bytes(usage.free),
                "total": _human_bytes(usage.total),
                "used_pct": round(usage.used / usage.total * 100) if usage.total else 0,
            }
        except OSError:
            pass
    return {"free": "—", "total": "—", "used_pct": None}


def _year_span_label(years: list[int]) -> str:
    """Format a list of years as a decade-range label, e.g. '1970s-1980s'."""
    lo_decade, hi_decade = (min(years) // 10) * 10, (max(years) // 10) * 10
    if lo_decade == hi_decade:
        return f"{lo_decade}s"
    return f"{lo_decade}s–{hi_decade}s"


def get_mounts_with_stats(db_path=None) -> list[dict]:
    """Return all collection mounts with online status, free space, and span.

    Each mount dict gains:
        span (str): decade range of years routed to this mount, or "—" if none.
        free (str): human-readable free space, or "—" if offline/unreadable.
        online (bool): whether root_path is currently reachable.
    """
    mounts = database.get_collection_mounts(db_path)
    years_by_mount: dict[int, list[int]] = {}
    for route in database.get_collection_routes(db_path):
        years_by_mount.setdefault(route["mount_id"], []).append(route["year"])

    for mount in mounts:
        years = years_by_mount.get(mount["id"])
        mount["span"] = _year_span_label(years) if years else "—"
        mount["online"] = _path_reachable(mount["root_path"])
        mount.update(get_disk_usage_stats(mount["root_path"], mount["online"]))
    return mounts


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
    mount_id_override: int | None = None,
    db_path=None,
) -> dict:
    """Resolve the filing destination for a known LB entry.

    Args:
        lb_number: LB number (must be in entries table).
        folder_path: Absolute path to the source folder on disk.
        mount_id_override: If given and different from the year-routed mount,
            file under this mount's root instead — keeping the same sub_path
            (e.g. year subfolder) the route would otherwise use.
        db_path: Optional SQLite path override.

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

    mount_id = route["mount_id"]
    mount_label = route["label"]
    mount_root = route["root_path"]
    sub_path = route["sub_path"] or ""

    if mount_id_override is not None and mount_id_override != mount_id:
        try:
            with database.get_connection(db_path) as conn:
                override = conn.execute(
                    "SELECT id, label, root_path FROM collection_mounts WHERE id = ?",
                    (mount_id_override,),
                ).fetchone()
        except Exception as exc:
            return _err("db_error", f"DB error reading mount {mount_id_override}: {exc}")
        if override is None:
            return _err("db_error", f"Mount {mount_id_override} not found")
        mount_id = override["id"]
        mount_label = override["label"]
        mount_root = override["root_path"]

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
        "mount_id": mount_id,
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


# ── Filing execution (background job with progress) ────────────────────────────

_FILE_JOB_LOCK = threading.Lock()
_FILE_JOB: dict = {
    "running": False,
    "stage": "idle",  # idle | scanning | copying | moving | done | failed
    "path": None,
    "dest": None,
    "file_mode": None,
    "lb_number": None,
    "files_done": 0,
    "files_total": 0,
    "bytes_done": 0,
    "bytes_total": 0,
    "current_file": None,
    "result": None,
}


def get_file_job_status() -> dict:
    """Return a snapshot of the current/last filing job for GUI polling."""
    with _FILE_JOB_LOCK:
        return dict(_FILE_JOB)


def _scan_tree(root: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for every file under root."""
    total_files = 0
    total_bytes = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total_bytes += (Path(dirpath) / name).stat().st_size
            except OSError:
                pass
            total_files += 1
    return total_files, total_bytes



# ── Collection size (total bytes across all my_collection folders) ────────────
# A full disk walk over every owned folder is too slow to run per-request
# (thousands of folders, possibly on network mounts) — the result is cached in
# the meta table and refreshed in the background when stale.

COLLECTION_SIZE_STALE_HOURS = 24

_SIZE_JOB_LOCK = threading.Lock()
_SIZE_JOB_RUNNING = False


def _compute_collection_size() -> tuple[int, int]:
    """Sum on-disk bytes across every my_collection folder.

    Returns:
        (folder_count, total_bytes) — folder_count only includes folders that
        were actually reachable; missing/offline paths are skipped.
    """
    with database.get_connection() as conn:
        paths = [r[0] for r in conn.execute("SELECT disk_path FROM my_collection").fetchall()]
    folder_count = 0
    total_bytes = 0
    for disk_path in paths:
        if not _path_reachable(disk_path):
            continue
        _, size = _scan_tree(Path(disk_path))
        total_bytes += size
        folder_count += 1
    return folder_count, total_bytes


def _run_collection_size_job() -> None:
    global _SIZE_JOB_RUNNING
    try:
        folder_count, total_bytes = _compute_collection_size()
        database.set_meta("collection_size_bytes", str(total_bytes))
        database.set_meta("collection_size_folders", str(folder_count))
        database.set_meta("collection_size_computed_at", datetime.now(UTC).isoformat())
    except Exception:
        logger.exception("Collection size scan failed")
    finally:
        with _SIZE_JOB_LOCK:
            _SIZE_JOB_RUNNING = False


def start_collection_size_scan_async() -> bool:
    """Kick off a background collection-size scan if one isn't already running.

    Returns:
        True if a new scan was started, False if one was already in progress.
    """
    global _SIZE_JOB_RUNNING
    with _SIZE_JOB_LOCK:
        if _SIZE_JOB_RUNNING:
            return False
        _SIZE_JOB_RUNNING = True
    threading.Thread(target=_run_collection_size_job, daemon=True).start()
    return True


def get_collection_size_stats() -> dict:
    """Return the cached total collection size, refreshing in the background if stale.

    Returns:
        Dict with bytes (int | None), human (str | None), folders (int | None),
        computed_at (str | None), and computing (bool) — True while a background
        scan is in flight (including one just triggered by this call).
    """
    bytes_raw = database.get_meta("collection_size_bytes")
    folders_raw = database.get_meta("collection_size_folders")
    computed_at = database.get_meta("collection_size_computed_at")

    stale = True
    if computed_at:
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(computed_at)
            stale = age.total_seconds() / 3600 > COLLECTION_SIZE_STALE_HOURS
        except ValueError:
            stale = True

    with _SIZE_JOB_LOCK:
        running = _SIZE_JOB_RUNNING
    if stale and not running:
        running = start_collection_size_scan_async()

    total_bytes = int(bytes_raw) if bytes_raw else None
    return {
        "bytes": total_bytes,
        "human": _human_bytes(total_bytes) if total_bytes else None,
        "folders": int(folders_raw) if folders_raw else None,
        "computed_at": computed_at,
        "computing": running,
    }


def _progress_copy_file(src: str, dst: str, *, follow_symlinks: bool = True) -> str:
    """shutil.copy2-compatible copy_function that updates _FILE_JOB progress."""
    result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
    try:
        size = os.path.getsize(result)
    except OSError:
        size = 0
    with _FILE_JOB_LOCK:
        _FILE_JOB["bytes_done"] += size
        _FILE_JOB["files_done"] += 1
        _FILE_JOB["current_file"] = os.path.basename(src)
    return result


class _HashVerificationError(Exception):
    """Raised when a copied folder's hash does not match its source."""

    def __init__(self, dest: Path):
        super().__init__(f"copied folder hash does not match source: {dest}")
        self.dest = dest


def hash_tree(root: Path) -> str:
    """Compute a deterministic SHA-256 digest over every file's contents under root.

    Combines each file's path (relative to root) and content hash, sorted by
    path, so the result changes if any file is added, removed, renamed, or
    its content differs. Used to verify a copied folder is byte-identical to
    its source before the source is removed.
    """
    root = Path(root)
    tree_digest = hashlib.sha256()
    rel_paths = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    for rel_path in rel_paths:
        file_digest = hashlib.sha256()
        with open(root / rel_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                file_digest.update(chunk)
        tree_digest.update(rel_path.encode("utf-8", "surrogatepass"))
        tree_digest.update(file_digest.digest())
    return tree_digest.hexdigest()


def _source_tree_digest(folder: Path) -> str:
    """Source-side tree digest for filing verification, served from the P1 cache.

    Source-only + fallback: derives the digest from cached per-file sha256s
    (byte-for-byte identical to hash_tree — design §2c) and falls back to a
    fresh hash_tree on ANY cache-layer error. The destination side must never
    use this — it is always freshly hash_tree'd on real bytes after the copy
    (hash-verify-before-remove invariant, design §2c).

    Args:
        folder: Absolute source folder path.

    Returns:
        Hex digest equal to hash_tree(folder).
    """
    try:
        return database.derive_tree_digest(str(folder))
    except Exception as exc:  # noqa: BLE001 — never let the cache break filing
        logger.warning(
            "_source_tree_digest: cache derive failed for %s, hashing fresh: %s",
            folder, exc,
        )
        return hash_tree(folder)


def _sync_qbt_location(lb_number: int, old_folder: Path, new_folder: Path, db_path=None) -> tuple[bool, str | None]:
    """Best-effort qBittorrent save-path sync after a successful filing move.

    No-ops (returns (False, None)) unless this folder is currently tracked
    in qBittorrent (torrents.added_to_qbt=1 with a known infohash). Never
    raises — a sync failure is logged and surfaced via the returned error
    string but does not affect the filing job's own success/failure.

    Returns:
        Tuple of (synced, error). synced is True if qBittorrent's save path
        was updated; error is a message if the sync was attempted but failed.
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import relocate_tracked_torrent

        host = database.get_meta("qbt_host", db_path=db_path) or "localhost"
        port = int(database.get_meta("qbt_port", db_path=db_path) or 8080)
        _, api_key = get_credentials(SERVICE_QBT_KEY)
        username, password = ("", "")
        if not api_key:
            username, password = get_credentials(SERVICE_QBT)

        result = relocate_tracked_torrent(
            lb_number, old_folder, new_folder,
            host=host, port=port, username=username, password=password, api_key=api_key,
            db_path=db_path,
        )
        if not result["ok"]:
            logger.warning(
                "start_file_job: LB-%05d filed to %s but qBittorrent location sync failed: %s",
                lb_number, new_folder, result["error"],
            )
            return False, result["error"]
        if result["synced"]:
            logger.info("start_file_job: LB-%05d qBittorrent save path synced to %s", lb_number, new_folder)
        return result["synced"], None
    except Exception as exc:
        logger.warning("start_file_job: LB-%05d qBittorrent sync raised: %s", lb_number, exc)
        return False, str(exc)


def _sync_qbt_file_renames(
    lb_number: int, folder: Path, renames: list[tuple[str, str]], db_path=None
) -> tuple[bool, str | None]:
    """Best-effort qBittorrent file-path sync after files moved within a folder.

    Companion to _sync_qbt_location() for changes that leave a torrent's
    root folder in place but rename/move files under it — LBDIR reconcile's
    "rename to match lbdir" and "move extras/" actions. No-ops unless folder
    is currently tracked in qBittorrent. Never raises.

    Returns:
        Tuple of (synced, error) — see qbittorrent.sync_file_renames().
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import sync_file_renames

        host = database.get_meta("qbt_host", db_path=db_path) or "localhost"
        port = int(database.get_meta("qbt_port", db_path=db_path) or 8080)
        _, api_key = get_credentials(SERVICE_QBT_KEY)
        username, password = ("", "")
        if not api_key:
            username, password = get_credentials(SERVICE_QBT)

        result = sync_file_renames(
            lb_number, folder, renames,
            host=host, port=port, username=username, password=password, api_key=api_key,
            db_path=db_path,
        )
        if not result["ok"]:
            logger.warning(
                "LB-%05d: file rename(s) applied in %s but qBittorrent file sync failed: %s",
                lb_number, folder, result["error"],
            )
            return False, result["error"]
        if result["synced"]:
            logger.info("LB-%05d: qBittorrent file path(s) synced for %s", lb_number, folder)
        return result["synced"], None
    except Exception as exc:
        logger.warning("LB-%05d: qBittorrent file sync raised: %s", lb_number, exc)
        return False, str(exc)


def start_file_job(
    lb_number: int,
    folder_path: str,
    file_mode: str = "move",
    mount_id_override: int | None = None,
    xref: int = 0,
    db_path=None,
) -> dict:
    """Resolve destination and start a background move/copy with progress tracking.

    Returns immediately with {ok, error?, error_code?}. On success, poll
    get_file_job_status() until "running" is False, then read its "result"
    key — a dict with the same shape previously returned synchronously:
    {ok, filed_to, dest, file_mode, error, error_code}.

    Whenever data is actually copied (file_mode="copy", or a cross-device
    "move" that falls back to copy+delete), the copy is hash-verified against
    the source with hash_tree() before the source is removed (move) or the
    job is reported done (copy). A same-device "move" uses os.rename(), which
    is atomic and rewrites no file content, so it is not hash-verified.

    Args:
        lb_number:   LB number (must be in entries table).
        folder_path: Absolute path to the source folder on disk.
        file_mode:   "move" (default) or "copy".
        mount_id_override: If given, file under this mount instead of the
            year-routed default (see resolve_destination_for_lb).
        xref: Copy-level xref fileset id this folder matched (0 = canonical),
            carried into my_collection.xref (FABLE_XREF_INCORPORATION.md D3).
        db_path:     Optional SQLite path override.
    """
    with _FILE_JOB_LOCK:
        if _FILE_JOB["running"]:
            return {"ok": False, "error": "A filing job is already in progress", "error_code": "busy"}

    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {
            "ok": False,
            "error": f"Source folder not found: {folder_path}",
            "error_code": "src_missing",
        }

    # Stale-verify guard (design §3a auto-collect hard rule, enforced server-side
    # for ALL filing). This closes the window where an auto-collect (or File-all)
    # fires on a row whose verify verdict predates an on-disk change: recomputing
    # the fingerprint here IS the design's R3 sweep, run in the same request that
    # arms the collect. A folder that never went through the pipeline has no
    # state — proceed with no opinion. Cache-layer failure logs and proceeds:
    # it must never block filing.
    try:
        state = database.get_folder_state(folder_path)
        if state is not None and database.folder_fingerprint(folder_path) != state["fingerprint"]:
            return {
                "ok": False,
                "error": ("Folder contents changed since the last pipeline check — "
                          "re-run the pipeline for this folder"),
                "error_code": "stale_verify",
            }
    except Exception as exc:  # noqa: BLE001 — never block filing on a cache error
        logger.warning(
            "start_file_job: stale-verify guard failed for %s, proceeding: %s",
            folder_path, exc,
        )

    resolution = resolve_destination_for_lb(lb_number, folder_path, mount_id_override, db_path)
    if not resolution["ok"]:
        return {"ok": False, "error": resolution["error"], "error_code": resolution["error_code"]}

    dest_parent = Path(resolution["dest_parent"])
    dest = Path(resolution["dest"])
    mount_label = resolution["mount_label"]

    with _FILE_JOB_LOCK:
        _FILE_JOB.update({
            "running": True,
            "stage": "scanning",
            "path": folder_path,
            "dest": str(dest),
            "file_mode": file_mode,
            "lb_number": lb_number,
            "files_done": 0,
            "files_total": 0,
            "bytes_done": 0,
            "bytes_total": 0,
            "current_file": None,
            "result": None,
        })

    def _finish(result: dict) -> None:
        with _FILE_JOB_LOCK:
            _FILE_JOB["running"] = False
            _FILE_JOB["stage"] = "done" if result["ok"] else "failed"
            _FILE_JOB["current_file"] = None
            _FILE_JOB["result"] = result

    def _run() -> None:
        files_total, bytes_total = _scan_tree(folder)
        with _FILE_JOB_LOCK:
            _FILE_JOB["files_total"] = files_total
            _FILE_JOB["bytes_total"] = bytes_total
            _FILE_JOB["stage"] = "copying" if file_mode == "copy" else "moving"

        try:
            dest_parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _finish({
                "ok": False, "filed_to": "", "dest": "", "file_mode": file_mode,
                "error": f"Cannot create destination directory {dest_parent}: {exc}",
                "error_code": "mkdir_failed",
            })
            return

        try:
            if file_mode == "copy":
                shutil.copytree(str(folder), str(dest), copy_function=_progress_copy_file)
                with _FILE_JOB_LOCK:
                    _FILE_JOB["stage"] = "verifying"
                if hash_tree(dest) != _source_tree_digest(folder):
                    raise _HashVerificationError(dest)
            else:
                try:
                    os.rename(str(folder), str(dest))
                    with _FILE_JOB_LOCK:
                        _FILE_JOB["files_done"] = files_total
                        _FILE_JOB["bytes_done"] = bytes_total
                except OSError:
                    # Cross-device move: copy with progress, verify the copy's
                    # hash against the source, then remove the source.
                    shutil.copytree(str(folder), str(dest), copy_function=_progress_copy_file)
                    with _FILE_JOB_LOCK:
                        _FILE_JOB["stage"] = "verifying"
                    if hash_tree(dest) != _source_tree_digest(folder):
                        raise _HashVerificationError(dest) from None
                    with _FILE_JOB_LOCK:
                        _FILE_JOB["stage"] = "removing"
                    try:
                        shutil.rmtree(str(folder))
                    except OSError as exc:
                        logger.warning(
                            "start_file_job: LB-%05d copy verified at %s but removing "
                            "the original at %s failed: %s",
                            lb_number, dest, folder, exc,
                        )
        except _HashVerificationError as exc:
            try:
                shutil.rmtree(str(exc.dest))
            except Exception:
                pass
            _finish({
                "ok": False, "filed_to": "", "dest": "", "file_mode": file_mode,
                "error": (
                    f"Integrity check failed: {file_mode}d copy at {exc.dest} does not "
                    "match the source folder's hash. The copy was removed; the "
                    "original is untouched."
                ),
                "error_code": "hash_mismatch",
            })
            return
        except Exception as exc:
            # Only clean up a partial dest while the source is still intact —
            # if folder is gone, dest is the only remaining copy of the data.
            if dest.exists() and folder.exists():
                try:
                    shutil.rmtree(str(dest))
                except Exception:
                    pass
            _finish({
                "ok": False, "filed_to": "", "dest": "", "file_mode": file_mode,
                "error": f"Filesystem {file_mode} failed: {exc}",
                "error_code": "fs_error",
            })
            return

        existing_disk_path: str | None = None
        try:
            with database.get_connection(db_path) as conn:
                existing_row = conn.execute(
                    "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb_number,)
                ).fetchone()
            if existing_row:
                existing_disk_path = existing_row["disk_path"]
                database.update_collection(
                    lb_number,
                    {"folder_name": folder.name, "disk_path": str(dest), "xref": xref},
                )
                logger.info(
                    "start_file_job: LB-%05d already in collection at %s — updated path to %s",
                    lb_number, existing_disk_path, dest,
                )
            else:
                database.add_to_collection(
                    lb_number, folder.name, str(dest), notes=None, xref=xref, db_path=db_path,
                )
        except Exception as exc:
            logger.error(
                "start_file_job: filesystem %s succeeded but my_collection write failed "
                "for LB-%05d at %s: %s",
                file_mode, lb_number, dest, exc,
            )
            _finish({
                "ok": False, "filed_to": mount_label, "dest": str(dest), "file_mode": file_mode,
                "error": (
                    f"Folder {file_mode}d to {dest} but collection registration failed: {exc}. "
                    "The folder exists on disk — use My Collection → Add folder to register it manually."
                ),
                "error_code": "db_write_failed",
            })
            return

        logger.info("start_file_job: LB-%05d %sd to %s (mount: %s)", lb_number, file_mode, dest, mount_label)

        qbt_synced, qbt_error = _sync_qbt_location(lb_number, folder, dest, db_path)

        _finish({
            "ok": True, "filed_to": mount_label, "dest": str(dest), "file_mode": file_mode,
            "error": None, "error_code": None,
            "qbt_synced": qbt_synced, "qbt_error": qbt_error,
            "existing_disk_path": existing_disk_path,
        })

    threading.Thread(target=_run, name=f"pipeline-file-lb{lb_number}", daemon=True).start()
    return {"ok": True}
