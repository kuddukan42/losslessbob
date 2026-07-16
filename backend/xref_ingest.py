"""Reviewed import path for site-mirror xref checksum files (TODO-252 / B8).

Site-mirror crawls occasionally pull down xref checksum text files
(``data/site/files/LBF-{lb:05d}-xref-{xref:05d}-text.txt``) that describe
copy-level filesets never captured in the live ``checksums`` table (new xref
ids, or gaps among described-but-uncaptured entries). This module stages
those filesets for review — nothing here writes to ``checksums`` except via
an explicit, per-fileset :func:`approve_filesets` call. The staging tables
(``xref_ingest_filesets`` / ``xref_ingest_rows``) are the audit trail /
provenance record; they never appear in a master export/import.

Follows the same staging-table + review + audited-apply architecture as
backend/flat_file.py.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import checksum_utils
from . import db as database
from .paths import SITE_FILES_DIR

logger = logging.getLogger(__name__)

# LBF-{lb:05d}-xref-{xref:05d}-text.txt — digit count kept flexible (\d+)
# rather than hard-coded to 5, since the glob below is the real filter.
_FILENAME_RE = re.compile(r"^LBF-(\d+)-xref-(\d+)-text\.txt$", re.IGNORECASE)


def _run_write(fn, db_path: str | None):
    """Route a write callable through the write queue.

    Matches the BUG-246 guard used elsewhere (flat_file.py, song_index.py,
    setlist_fingerprint.py, taper_attribution.py): the write queue singleton
    is first-caller-wins, so under pytest (each test its own temp DB) it may
    be bound to a different DB than *db_path*.

    Args:
        fn: Callable taking a sqlite3.Connection and performing writes.
        db_path: Optional DB path override the caller intended to target.

    Returns:
        Whatever *fn* returns.
    """
    queue = database.get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        logger.warning(
            "xref_ingest: write queue bound to %s but this write targets %s"
            " — writing directly", queue.db_path, db_path,
        )
        conn = database.get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _insert_staged_fileset(
    lb_number: int,
    xref: int,
    source_file: str,
    row_count: int,
    new_count: int,
    rows: list[tuple[str, str, str, int]],
    db_path: str | None,
) -> None:
    """Insert a brand-new staged fileset plus its parsed rows."""

    def _write(c) -> None:
        cur = c.execute(
            """INSERT INTO xref_ingest_filesets
               (lb_number, xref, source_file, row_count, new_count, status)
               VALUES (?,?,?,?,?,'staged')""",
            (lb_number, xref, source_file, row_count, new_count),
        )
        fileset_id = cur.lastrowid
        if rows:
            c.executemany(
                """INSERT INTO xref_ingest_rows
                   (fileset_id, checksum, filename, chk_type, is_new)
                   VALUES (?,?,?,?,?)""",
                [(fileset_id, chk, fn, ct, is_new) for chk, fn, ct, is_new in rows],
            )

    _run_write(_write, db_path)


def _update_staged_fileset(
    lb_number: int,
    xref: int,
    source_file: str,
    row_count: int,
    new_count: int,
    rows: list[tuple[str, str, str, int]],
    db_path: str | None,
) -> None:
    """Refresh counts/rows for a fileset that is still in 'staged' status."""

    def _write(c) -> None:
        row = c.execute(
            "SELECT id FROM xref_ingest_filesets WHERE lb_number=? AND xref=? AND status='staged'",
            (lb_number, xref),
        ).fetchone()
        if row is None:
            return
        fileset_id = row[0]
        c.execute(
            """UPDATE xref_ingest_filesets
               SET source_file=?, row_count=?, new_count=?
               WHERE id=?""",
            (source_file, row_count, new_count, fileset_id),
        )
        c.execute("DELETE FROM xref_ingest_rows WHERE fileset_id=?", (fileset_id,))
        if rows:
            c.executemany(
                """INSERT INTO xref_ingest_rows
                   (fileset_id, checksum, filename, chk_type, is_new)
                   VALUES (?,?,?,?,?)""",
                [(fileset_id, chk, fn, ct, is_new) for chk, fn, ct, is_new in rows],
            )

    _run_write(_write, db_path)


def scan_mirror(db_path: str | None = None) -> dict:
    """Scan the site mirror for xref checksum filesets and stage new ones.

    Globs ``SITE_FILES_DIR`` for ``LBF-{lb:05d}-xref-{xref:05d}-text.txt``
    files, reads each with :func:`backend.checksum_utils._read_checksum_text`
    (handles cp1252 legacy encodings) and parses it with
    :func:`backend.db.parse_checksum_text`. Each parsed row is compared
    against the live ``checksums`` table: a row is "new" iff no ``checksums``
    row exists with the same ``(checksum, lb_number)`` pair — the table's
    unique index — so a file shared across filesets is not double-counted as
    new.

    Only filesets with at least one new row are staged. Re-scanning is
    idempotent: filesets still in 'staged' status have their counts/rows
    refreshed in place; 'approved' and 'rejected' filesets are never
    touched, and unparseable files are logged, counted, and skipped.

    Args:
        db_path: Optional DB path override.

    Returns:
        dict with keys: scanned (int), staged_new (int), updated (int),
        skipped_no_new (int), skipped_decided (int), unparseable (int),
        unparseable_files (list[str]), rows_new_total (int).
    """
    conn = database.get_connection(db_path)

    summary: dict = {
        "scanned": 0,
        "staged_new": 0,
        "updated": 0,
        "skipped_no_new": 0,
        "skipped_decided": 0,
        "unparseable": 0,
        "unparseable_files": [],
        "rows_new_total": 0,
    }

    if not SITE_FILES_DIR.exists():
        logger.warning("xref_ingest: SITE_FILES_DIR does not exist: %s", SITE_FILES_DIR)
        return summary

    decided_status = {
        (r["lb_number"], r["xref"]): r["status"]
        for r in conn.execute("SELECT lb_number, xref, status FROM xref_ingest_filesets")
    }
    existing_by_lb: dict[int, set[str]] = {}

    def _existing_checksums(lb_number: int) -> set[str]:
        if lb_number not in existing_by_lb:
            existing_by_lb[lb_number] = {
                r[0]
                for r in conn.execute(
                    "SELECT checksum FROM checksums WHERE lb_number=?", (lb_number,)
                )
            }
        return existing_by_lb[lb_number]

    for path in sorted(SITE_FILES_DIR.glob("LBF-*-xref-*-text.txt")):
        try:
            m = _FILENAME_RE.match(path.name)
            if not m:
                raise ValueError(f"filename does not match LBF-*-xref-*-text.txt: {path.name}")
            lb_number, xref = int(m.group(1)), int(m.group(2))
            text = checksum_utils._read_checksum_text(path)
            parsed = database.parse_checksum_text(text)
        except (OSError, ValueError, UnicodeError) as exc:
            summary["unparseable"] += 1
            summary["unparseable_files"].append(path.name)
            logger.warning("xref_ingest: failed to parse %s: %s", path.name, exc)
            continue

        summary["scanned"] += 1

        prior_status = decided_status.get((lb_number, xref))
        if prior_status in ("approved", "rejected"):
            summary["skipped_decided"] += 1
            continue

        existing = _existing_checksums(lb_number)
        rows: list[tuple[str, str, str, int]] = []
        new_count = 0
        for checksum, filename, chk_type in parsed:
            is_new = 1 if checksum not in existing else 0
            new_count += is_new
            rows.append((checksum, filename, chk_type, is_new))

        if prior_status == "staged":
            _update_staged_fileset(
                lb_number, xref, str(path), len(parsed), new_count, rows, db_path
            )
            summary["updated"] += 1
            summary["rows_new_total"] += new_count
            continue

        if new_count == 0:
            summary["skipped_no_new"] += 1
            continue

        _insert_staged_fileset(
            lb_number, xref, str(path), len(parsed), new_count, rows, db_path
        )
        summary["staged_new"] += 1
        summary["rows_new_total"] += new_count

    logger.info(
        "xref_ingest scan: scanned=%d staged_new=%d updated=%d skipped_no_new=%d "
        "skipped_decided=%d unparseable=%d",
        summary["scanned"], summary["staged_new"], summary["updated"],
        summary["skipped_no_new"], summary["skipped_decided"], summary["unparseable"],
    )
    return summary


def get_filesets(status: str | None = None, db_path: str | None = None) -> list[dict]:
    """Return staging rows (with counts) for the review UI.

    Args:
        status: Optional status filter ('staged', 'approved', 'rejected').
        db_path: Optional DB path override.

    Returns:
        List of dicts, one per xref_ingest_filesets row, newest-staged first.
    """
    conn = database.get_connection(db_path)
    if status:
        rows = conn.execute(
            """SELECT * FROM xref_ingest_filesets WHERE status=?
               ORDER BY staged_at DESC, id DESC""",
            (status,),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM xref_ingest_filesets ORDER BY staged_at DESC, id DESC"
        )
    return [dict(r) for r in rows]


def approve_filesets(ids: list[int], db_path: str | None = None) -> dict:
    """Approve staged filesets: write their new rows into ``checksums``.

    Only rows flagged ``is_new=1`` in ``xref_ingest_rows`` are inserted, via
    the same ``INSERT OR IGNORE INTO checksums (checksum, filename, chk_type,
    lb_number, xref)`` write backend/flat_file.py's apply step uses. Ids not
    currently in 'staged' status are refused — never approved, never
    stamped — and reported back separately so nothing is silently skipped.

    Args:
        ids: xref_ingest_filesets row ids to approve.
        db_path: Optional DB path override.

    Returns:
        dict with keys: approved (list[int]), refused (list[int]),
        rows_inserted (int).
    """
    conn = database.get_connection(db_path)
    if not ids:
        return {"approved": [], "refused": [], "rows_inserted": 0}

    placeholders = ",".join("?" for _ in ids)
    fileset_rows = {
        r["id"]: dict(r)
        for r in conn.execute(
            f"SELECT * FROM xref_ingest_filesets WHERE id IN ({placeholders})", list(ids)
        )
    }

    approved: list[int] = []
    refused: list[int] = []
    rows_inserted = 0

    for fid in ids:
        row = fileset_rows.get(fid)
        if row is None or row["status"] != "staged":
            refused.append(fid)
            continue

        new_rows = [
            (r["checksum"], r["filename"], r["chk_type"], row["lb_number"], row["xref"])
            for r in conn.execute(
                "SELECT checksum, filename, chk_type FROM xref_ingest_rows "
                "WHERE fileset_id=? AND is_new=1",
                (fid,),
            )
        ]

        def _write(c, _fid=fid, _rows=new_rows) -> None:
            if _rows:
                c.executemany(
                    "INSERT OR IGNORE INTO checksums "
                    "(checksum, filename, chk_type, lb_number, xref) VALUES (?,?,?,?,?)",
                    _rows,
                )
            c.execute(
                """UPDATE xref_ingest_filesets
                   SET status='approved', decided_at=CURRENT_TIMESTAMP
                   WHERE id=? AND status='staged'""",
                (_fid,),
            )

        _run_write(_write, db_path)
        approved.append(fid)
        rows_inserted += len(new_rows)

    logger.info(
        "xref_ingest approve: approved=%s refused=%s rows_inserted=%d",
        approved, refused, rows_inserted,
    )
    return {"approved": approved, "refused": refused, "rows_inserted": rows_inserted}


def reject_filesets(ids: list[int], db_path: str | None = None) -> dict:
    """Reject staged filesets: mark them decided without touching ``checksums``.

    Ids not currently in 'staged' status are refused — never re-decided.

    Args:
        ids: xref_ingest_filesets row ids to reject.
        db_path: Optional DB path override.

    Returns:
        dict with keys: rejected (list[int]), refused (list[int]).
    """
    conn = database.get_connection(db_path)
    if not ids:
        return {"rejected": [], "refused": []}

    placeholders = ",".join("?" for _ in ids)
    statuses = {
        r["id"]: r["status"]
        for r in conn.execute(
            f"SELECT id, status FROM xref_ingest_filesets WHERE id IN ({placeholders})",
            list(ids),
        )
    }

    rejected: list[int] = []
    refused: list[int] = []

    for fid in ids:
        if statuses.get(fid) != "staged":
            refused.append(fid)
            continue

        def _write(c, _fid=fid) -> None:
            c.execute(
                """UPDATE xref_ingest_filesets
                   SET status='rejected', decided_at=CURRENT_TIMESTAMP
                   WHERE id=? AND status='staged'""",
                (_fid,),
            )

        _run_write(_write, db_path)
        rejected.append(fid)

    logger.info("xref_ingest reject: rejected=%s refused=%s", rejected, refused)
    return {"rejected": rejected, "refused": refused}
