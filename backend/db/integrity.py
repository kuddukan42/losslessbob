"""Collection integrity monitor + file-level integrity inventory (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── TODO-284: Collection Integrity Monitor ───────────────────────────────────

def upsert_collection_integrity_status(
    lb_number: int,
    mount_id: int | None,
    disk_path: str,
    status: str,
    content_issues: int = 0,
    tag_issues: int = 0,
    missing_count: int = 0,
    total_files: int = 0,
    db_path=None,
) -> None:
    """Insert or replace the latest integrity-scan result for a collection entry.

    Args:
        lb_number: Collection entry LB number (primary key of the status row).
        mount_id: Owning collection_mounts.id, or None if unmatched.
        disk_path: Folder path that was verified.
        status: One of pass, content_issue, tag_issue, missing_files, no_lbdir, error.
        content_issues: Count of files with ffp_status == 'fail' (audio/bitrot).
        tag_issues: Count of files with md5 fail but ffp pass/na (tags only).
        missing_count: Count of lbdir-listed files missing from disk.
        total_files: Total lbdir-listed files considered (excluding 'extra').
    """
    _args = (lb_number, mount_id, disk_path, status, content_issues, tag_issues,
             missing_count, total_files)
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_integrity_status "
            "(lb_number, mount_id, disk_path, status, content_issues, tag_issues, "
            " missing_count, total_files, checked_at) "
            "VALUES(?,?,?,?,?,?,?,?,datetime('now')) "
            "ON CONFLICT(lb_number) DO UPDATE SET "
            "mount_id=excluded.mount_id, disk_path=excluded.disk_path, "
            "status=excluded.status, content_issues=excluded.content_issues, "
            "tag_issues=excluded.tag_issues, missing_count=excluded.missing_count, "
            "total_files=excluded.total_files, checked_at=excluded.checked_at",
            _args,
        )
    )


def get_collection_integrity_status(
    mount_id: int | None = None, status: str | None = None, db_path=None
) -> list[dict]:
    """Return collection_integrity_status rows, optionally filtered by mount and status.

    Args:
        mount_id: If given, only rows for this collection_mounts.id.
        status: If given, only rows with this status value.

    Returns:
        List of row dicts, ordered by lb_number.
    """
    where = []
    params: list = []
    if mount_id is not None:
        where.append("mount_id=?")
        params.append(mount_id)
    if status is not None:
        where.append("status=?")
        params.append(status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM collection_integrity_status {clause} ORDER BY lb_number",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_mount_integrity_summary(db_path=None) -> dict[int, dict[str, int]]:
    """Return per-mount counts of integrity statuses for GUI badges.

    Returns:
        Mapping of mount_id (or 0 for unmatched/None) to a dict with keys
        pass, content_issue, tag_issue, missing_files, no_lbdir, error — each
        the count of collection_integrity_status rows with that status.
    """
    statuses = ("pass", "content_issue", "tag_issue", "missing_files", "no_lbdir", "error")
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT COALESCE(mount_id, 0) AS mid, status, COUNT(*) AS n "
            "FROM collection_integrity_status GROUP BY mid, status"
        ).fetchall()
    summary: dict[int, dict[str, int]] = {}
    for r in rows:
        bucket = summary.setdefault(r["mid"], {s: 0 for s in statuses})
        if r["status"] in bucket:
            bucket[r["status"]] = r["n"]
    return summary


def record_integrity_scan_start(mount_id: int | None = None, db_path=None) -> int:
    """Insert a new collection_integrity_scans row in 'running' state.

    Args:
        mount_id: Mount being scanned, or None for a whole-collection scan.

    Returns:
        The new scan row's id.
    """
    def _run(c):
        cur = c.execute(
            "INSERT INTO collection_integrity_scans(mount_id, status) VALUES(?, 'running')",
            (mount_id,),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_integrity_scan(
    scan_id: int,
    status: str,
    counts: dict[str, int],
    error: str | None = None,
    db_path=None,
) -> None:
    """Mark a collection_integrity_scans row finished and record aggregate counts.

    Args:
        scan_id: Row id returned by record_integrity_scan_start.
        status: Final scan status — done, error, or cancelled.
        counts: Dict with keys folders_checked, folders_pass, folders_content_issue,
            folders_tag_issue, folders_missing, folders_no_lbdir.
        error: Optional error message if status == 'error'.
    """
    get_write_queue().execute(
        lambda c: c.execute(
            "UPDATE collection_integrity_scans SET "
            "status=?, finished_at=datetime('now'), "
            "folders_checked=?, folders_pass=?, folders_content_issue=?, "
            "folders_tag_issue=?, folders_missing=?, folders_no_lbdir=?, error=? "
            "WHERE id=?",
            (
                status,
                counts.get("folders_checked", 0),
                counts.get("folders_pass", 0),
                counts.get("folders_content_issue", 0),
                counts.get("folders_tag_issue", 0),
                counts.get("folders_missing", 0),
                counts.get("folders_no_lbdir", 0),
                error,
                scan_id,
            ),
        )
    )


def get_integrity_scan_history(
    mount_id: int | None = None, limit: int = 20, db_path=None
) -> list[dict]:
    """Return recent collection_integrity_scans rows, newest first.

    Args:
        mount_id: If given, only scans for this mount (None matches whole-collection
            scans where mount_id IS NULL).
        limit: Maximum number of rows to return.
    """
    with get_connection(db_path) as conn:
        if mount_id is None:
            rows = conn.execute(
                "SELECT * FROM collection_integrity_scans "
                "WHERE mount_id IS NULL ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM collection_integrity_scans "
                "WHERE mount_id=? ORDER BY started_at DESC LIMIT ?",
                (mount_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


# ── File-level integrity inventory (TODO-267) ────────────────────────────────

def get_file_inventory_rows(mount_id: int, db_path=None) -> dict[str, dict]:
    """Return every file_inventory row for a mount, keyed by rel_path.

    Loaded once per scan so the walk can diff against it in memory — 16k folders
    means hundreds of thousands of rows, and a per-file SELECT would dominate the
    scan's runtime.

    Args:
        mount_id: collection_mounts.id to load.

    Returns:
        Mapping of rel_path -> row dict.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM file_inventory WHERE mount_id=?", (mount_id,)
        ).fetchall()
    return {r["rel_path"]: dict(r) for r in rows}


def upsert_file_inventory(records: list[dict], db_path=None) -> None:
    """Insert or update a batch of file_inventory rows in one transaction.

    Batched deliberately: a per-file write-queue round trip would make a
    whole-collection index scan far slower than the disk reads it wraps.

    ``first_seen`` is preserved across updates via COALESCE on the existing row.
    ``last_verified`` is only advanced when the caller passes it — an index-mode
    scan records content it has not compared, so it must not claim a verify.

    Args:
        records: Dicts with keys mount_id, rel_path, lb_number, size, mtime,
            xxh3, sha256, status, and optionally last_verified (ISO string).
    """
    if not records:
        return

    def _run(c):
        c.executemany(
            "INSERT INTO file_inventory "
            "(mount_id, rel_path, lb_number, size, mtime, xxh3, sha256, status, "
            " first_seen, last_hashed, last_verified) "
            "VALUES (:mount_id, :rel_path, :lb_number, :size, :mtime, :xxh3, :sha256, "
            "        :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :last_verified) "
            "ON CONFLICT(mount_id, rel_path) DO UPDATE SET "
            "  lb_number=excluded.lb_number, size=excluded.size, mtime=excluded.mtime, "
            "  xxh3=excluded.xxh3, sha256=excluded.sha256, status=excluded.status, "
            "  last_hashed=CURRENT_TIMESTAMP, "
            "  last_verified=COALESCE(excluded.last_verified, file_inventory.last_verified)",
            [{"last_verified": None, **r} for r in records],
        )

    get_write_queue().execute(_run)


def touch_file_inventory_verified(keys: list[tuple[int, str]], db_path=None) -> None:
    """Mark a batch of files as verified-now without rewriting their hashes.

    The hot path of a deep verify: the file matched, so only last_verified moves.

    Args:
        keys: (mount_id, rel_path) pairs that verified clean.
    """
    if not keys:
        return
    get_write_queue().execute(
        lambda c: c.executemany(
            "UPDATE file_inventory SET last_verified=CURRENT_TIMESTAMP, status='ok' "
            "WHERE mount_id=? AND rel_path=?",
            keys,
        )
    )


def mark_file_inventory_status(
    updates: list[tuple[str, int, str]], db_path=None
) -> None:
    """Set the status column for a batch of files.

    Args:
        updates: (status, mount_id, rel_path) tuples.
    """
    if not updates:
        return
    get_write_queue().execute(
        lambda c: c.executemany(
            "UPDATE file_inventory SET status=? WHERE mount_id=? AND rel_path=?",
            updates,
        )
    )


def delete_file_inventory_rows(keys: list[tuple[int, str]], db_path=None) -> None:
    """Remove file_inventory rows whose files are confirmed gone.

    Only called when the caller has decided a disappearance is legitimate; the
    default for an unexpectedly missing file is status='missing', not deletion.

    Args:
        keys: (mount_id, rel_path) pairs to delete.
    """
    if not keys:
        return
    get_write_queue().execute(
        lambda c: c.executemany(
            "DELETE FROM file_inventory WHERE mount_id=? AND rel_path=?", keys
        )
    )


def find_ok_inventory_by_xxh3(xxh3_values: list[str], db_path=None) -> dict[str, tuple[int, str]]:
    """Look up an existing 'ok' file_inventory row for each hash, if any.

    Used by the missing-file sweep (TODO-297) to tell a genuine deletion from a
    relocation: if the content that used to live at a now-absent rel_path is
    already sitting under an 'ok' row somewhere else (any mount), the old row
    is stale bookkeeping, not a real loss.

    Args:
        xxh3_values: Hashes to look up. Duplicates are fine.

    Returns:
        Mapping of xxh3 -> (mount_id, rel_path) for one matching row per hash.
        Hashes with no 'ok' row, or with no match at all, are absent.
    """
    if not xxh3_values:
        return {}
    with get_connection(db_path) as conn:
        placeholders = ",".join("?" * len(set(xxh3_values)))
        rows = conn.execute(
            f"SELECT xxh3, mount_id, rel_path FROM file_inventory "
            f"WHERE status='ok' AND xxh3 IN ({placeholders})",
            list(set(xxh3_values)),
        ).fetchall()
    return {r["xxh3"]: (r["mount_id"], r["rel_path"]) for r in rows}


def get_rolling_verify_batch(
    mount_id: int, limit: int, db_path=None
) -> list[dict]:
    """Return the files most overdue for a deep verify on one mount.

    Never-verified rows (last_verified IS NULL) sort first under SQLite's ASC
    NULL ordering, so a fresh baseline drains before anything is re-checked.

    Args:
        mount_id: Mount to draw from.
        limit: Maximum rows to return.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM file_inventory WHERE mount_id=? AND status != 'missing' "
            "ORDER BY last_verified ASC LIMIT ?",
            (mount_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_file_integrity_summary(db_path=None) -> dict[int, dict[str, int]]:
    """Return per-mount file counts by status, for GUI badges.

    Returns:
        Mapping of mount_id -> {status: count}.
    """
    summary: dict[int, dict[str, int]] = {}
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT mount_id, status, COUNT(*) AS n, "
            "       COALESCE(SUM(size), 0) AS bytes "
            "FROM file_inventory GROUP BY mount_id, status"
        ).fetchall()
    for r in rows:
        summary.setdefault(r["mount_id"], {})[r["status"]] = r["n"]
        summary[r["mount_id"]]["bytes"] = summary[r["mount_id"]].get("bytes", 0) + r["bytes"]
    return summary


def get_file_integrity_problems(
    limit: int = 200, status: str | None = None, db_path=None
) -> list[dict]:
    """Return files currently flagged as anything other than ok, worst first.

    Args:
        limit: Maximum rows.
        status: If given, restrict to this one status.
    """
    clause = "status=?" if status else "status != 'ok'"
    params: list = [status] if status else []
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM file_inventory WHERE {clause} "
            "ORDER BY CASE status WHEN 'rot' THEN 0 WHEN 'unreadable' THEN 1 "
            "         WHEN 'missing' THEN 2 ELSE 3 END, rel_path LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def record_file_scan_start(mount_id: int, mode: str, db_path=None) -> int:
    """Insert a file_integrity_scans row in 'running' state.

    Args:
        mount_id: Mount being scanned.
        mode: 'index' (stat-skip) or 'verify' (full re-read).

    Returns:
        The new scan row's id.
    """
    return get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO file_integrity_scans(mount_id, mode, status) "
            "VALUES(?,?,'running')",
            (mount_id, mode),
        ).lastrowid
    )


_FILE_SCAN_COUNTS = (
    "files_seen", "files_hashed", "files_new", "files_ok", "files_rot",
    "files_changed", "files_missing", "files_moved", "files_unreadable", "bytes_hashed",
)


def finish_file_scan(
    scan_id: int, status: str, counts: dict[str, int], error: str | None = None,
    db_path=None,
) -> None:
    """Mark a file_integrity_scans row finished and record its aggregate counts.

    Args:
        scan_id: Row id from record_file_scan_start.
        status: Final status — done, partial (stopped by a budget), cancelled,
            or error. Only 'done' means the pass was complete enough for
            missing-file detection to be trustworthy.
        counts: Keys from _FILE_SCAN_COUNTS; missing keys default to 0.
        error: Message when status == 'error'.
    """
    assignments = ", ".join(f"{c}=?" for c in _FILE_SCAN_COUNTS)
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE file_integrity_scans SET status=?, finished_at=datetime('now'), "
            f"{assignments}, error=? WHERE id=?",
            (status, *(counts.get(k, 0) for k in _FILE_SCAN_COUNTS), error, scan_id),
        )
    )


def get_file_scan_history(
    mount_id: int | None = None, limit: int = 20, mode: str | None = None,
    db_path=None,
) -> list[dict]:
    """Return recent file_integrity_scans rows, newest first.

    Args:
        mount_id: If given, only scans for this mount.
        limit: Maximum rows.
        mode: If given, only scans of this mode ('index' or 'verify'). The
            rolling scheduler filters on this so a manual index scan does not
            reset its "when did we last deep-verify" clock.
    """
    where = []
    params: list = []
    if mount_id is not None:
        where.append("mount_id=?")
        params.append(mount_id)
    if mode is not None:
        where.append("mode=?")
        params.append(mode)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM file_integrity_scans {clause} "
            "ORDER BY started_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [dict(r) for r in rows]
