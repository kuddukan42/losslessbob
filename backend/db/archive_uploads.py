"""Archive.org upload history (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── Archive.org upload history ────────────────────────────────────────────────

def create_archive_upload(lb_number: int, identifier: str, folder_path: str,
                          files_total: int, db_path=None) -> int:
    """Insert a new archive_org_uploads row in 'running' status and return its id.

    Args:
        lb_number: LosslessBob entry number.
        identifier: Internet Archive item identifier.
        folder_path: Absolute path to the source folder.
        files_total: Total number of files to upload.
        db_path: Optional database path override.

    Returns:
        New row id.
    """
    _lb, _id, _fp, _ft = lb_number, identifier, folder_path, files_total

    def _run(c):
        cur = c.execute(
            "INSERT INTO archive_org_uploads(lb_number, identifier, folder_path, files_total, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            (_lb, _id, _fp, _ft),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_archive_upload(upload_id: int, status: str, error: str | None = None,
                          files_uploaded: int | None = None, db_path=None) -> None:
    """Mark an archive upload row as finished.

    Args:
        upload_id: Row id of the archive_org_uploads row.
        status: Final status string — 'done', 'failed', 'stopped'.
        error: Error message if status is 'failed'.
        files_uploaded: Files successfully uploaded (None = leave unchanged).
        db_path: Optional database path override.
    """
    _uid, _st, _err, _fu = upload_id, status, error, files_uploaded

    def _run(c):
        if _fu is not None:
            c.execute(
                "UPDATE archive_org_uploads "
                "SET status=?, error=?, files_uploaded=?, finished_at=datetime('now') "
                "WHERE id=?",
                (_st, _err, _fu, _uid),
            )
        else:
            c.execute(
                "UPDATE archive_org_uploads "
                "SET status=?, error=?, finished_at=datetime('now') WHERE id=?",
                (_st, _err, _uid),
            )

    get_write_queue().execute(_run)


def get_archive_uploads(lb_number: int | None = None, db_path=None) -> list:
    """Return archive upload rows, newest first.

    Args:
        lb_number: If given, restrict to uploads for this LB. Otherwise return all.
        db_path: Optional database path override.

    Returns:
        List of row dicts.
    """
    with get_connection(db_path) as conn:
        if lb_number is not None:
            rows = conn.execute(
                "SELECT * FROM archive_org_uploads WHERE lb_number=? ORDER BY started_at DESC",
                (lb_number,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT au.*, e.date_str, e.location "
                "FROM archive_org_uploads au "
                "LEFT JOIN entries e ON e.lb_number = au.lb_number "
                "ORDER BY au.started_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]
