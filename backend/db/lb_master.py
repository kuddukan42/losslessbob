"""lb_master status/reconcile/overrides, lb_missing, curator flag (from backend.db, TODO-369 S2)."""

import logging

from backend.db import backup_database, get_connection, get_meta, set_meta
from backend.db_queue import get_write_queue

logger = logging.getLogger(__name__)


def _compute_lb_status(has_web: bool, has_chk: bool, has_att: bool) -> tuple[str, int]:
    """Apply status-precedence rules. Returns (status, needs_review)."""
    if has_web or has_att:
        status = "public"
        # Attachments-only without a confirmed webpage → flag for review
        needs_review = 1 if (has_att and not has_web) else 0
    elif has_chk:
        status = "private"
        needs_review = 0
    else:
        status = "missing"
        needs_review = 0
    return status, needs_review


def _keep_unscraped_public(auto_status: str, old_status: str | None, unscraped: bool) -> str:
    """Stop reconcile demoting a never-scraped LB from 'public' to 'private'.

    'private' means "checksums but no webpage". An LB with no ``entries`` row has
    not been checked against the site yet, so its missing webpage is unknown, not
    absent -- flat-file apply marks such LBs 'public' and the first scrape settles
    them. Without this, Reconcile run before Scrape flipped new LBs to 'private'
    and the scrape planner then skipped them.

    Args:
        auto_status: Status computed from live data.
        old_status: Current lb_master status, or None for a new row.
        unscraped: True when the LB has no ``entries`` row of any status.

    Returns:
        The status to store.
    """
    if unscraped and auto_status == "private" and old_status == "public":
        return "public"
    return auto_status


def migrate_lb_master(db_path=None, wait: bool = True) -> int:
    """Backfill lb_master for integers 1..MAX(lb_number) from existing data.

    Skipped when lb_master already contains rows (idempotent guard).
    Deletes entries.status='missing' tombstones after populating lb_master.

    Args:
        db_path: Optional database path override.
        wait: If False, submit the write via the queue's fire-and-forget
            execute_async() instead of blocking on execute()'s up-to-30s
            wait (BUG-262). init_db()'s background-thread caller sets this —
            nothing waits on that thread's result, so blocking it against a
            write queue a fast-moving caller (e.g. a test) may already be
            tearing down just piles up threads for no benefit. Synchronous
            callers (importer.py, flat_file.py) that need the write committed
            before this function returns keep the default.

    Returns:
        Number of rows inserted, or 0 if skipped. When wait=False this counts
        rows about to be submitted, not necessarily yet committed.
    """
    conn = get_connection(db_path)

    existing = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
    if existing > 0:
        return 0

    max_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0]
    if not max_lb:
        return 0

    backup_database("pre_lb_master_migration", db_path)

    public_set = {r[0] for r in conn.execute(
        "SELECT lb_number FROM entries WHERE status='ok'")}
    checksum_set = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM checksums")}
    attach_set = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM entry_files")}

    missing_set = {r[0] for r in conn.execute("SELECT lb_number FROM lb_missing")}

    rows = []
    for n in range(1, max_lb + 1):
        if n in missing_set:
            status, needs_review = "nonexistent", 0
            hw = hc = ha = 0
        else:
            has_web = n in public_set
            has_chk = n in checksum_set
            has_att = n in attach_set
            status, needs_review = _compute_lb_status(has_web, has_chk, has_att)
            hw, hc, ha = int(has_web), int(has_chk), int(has_att)
        pnc = int(status == "public" and hc == 0)
        rows.append((n, status, hw, hc, ha, needs_review, pnc))

    _rows = rows

    def _run(c):
        c.executemany(
            """INSERT OR REPLACE INTO lb_master
               (lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                needs_review, public_no_checksums)
               VALUES (?,?,?,?,?,?,?)""",
            _rows,
        )
        # Remove tombstone rows — lb_master is now authoritative
        c.execute("DELETE FROM entries WHERE status='missing'")

    if wait:
        get_write_queue().execute(_run)
    else:
        get_write_queue().execute_async(_run)

    logger.info(
        "lb_master populated: %d rows (%d public, %d private, %d missing)",
        len(rows),
        sum(1 for r in rows if r[1] == "public"),
        sum(1 for r in rows if r[1] == "private"),
        sum(1 for r in rows if r[1] == "missing"),
    )
    return len(rows)


def reconcile_lb_status(lb_number: int, trigger: str = "reconcile", db_path=None) -> str:
    """Recompute lb_master status for a single LB from live data.

    Respects manual_override=1: updates has_* columns but does NOT change lb_status.
    Logs transitions to lb_status_history.
    Returns the final (possibly unchanged) lb_status string.
    """
    _lb, _trigger = lb_number, trigger

    def _run(conn) -> str:
        unscraped = False
        if conn.execute(
            "SELECT 1 FROM lb_missing WHERE lb_number=?", (_lb,)
        ).fetchone():
            auto_status, needs_review = "nonexistent", 0
            has_web = has_chk = has_att = False
        else:
            has_web = bool(conn.execute(
                "SELECT 1 FROM entries WHERE lb_number=? AND status='ok'", (_lb,)
            ).fetchone())
            has_chk = bool(conn.execute(
                "SELECT 1 FROM checksums WHERE lb_number=?", (_lb,)
            ).fetchone())
            has_att = bool(conn.execute(
                "SELECT 1 FROM entry_files WHERE lb_number=?", (_lb,)
            ).fetchone())
            auto_status, needs_review = _compute_lb_status(has_web, has_chk, has_att)
            unscraped = not conn.execute(
                "SELECT 1 FROM entries WHERE lb_number=?", (_lb,)
            ).fetchone()

        existing = conn.execute(
            "SELECT lb_status, manual_override FROM lb_master WHERE lb_number=?",
            (_lb,),
        ).fetchone()

        if existing is None:
            initial_status = (
                "public"
                if _trigger == "flat_file_apply" and auto_status == "private"
                else auto_status
            )
            pnc = int(initial_status == "public" and not has_chk)
            conn.execute(
                """INSERT INTO lb_master
                   (lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                    needs_review, public_no_checksums)
                   VALUES (?,?,?,?,?,?,?)""",
                (_lb, initial_status, int(has_web), int(has_chk), int(has_att),
                 needs_review, pnc),
            )
            conn.execute(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
                "VALUES (?,NULL,?,?)",
                (_lb, initial_status, _trigger),
            )
            return initial_status

        old_status = existing["lb_status"]
        manual_override = existing["manual_override"]

        if manual_override:
            pnc = int(old_status == "public" and not has_chk)
            conn.execute(
                """UPDATE lb_master
                   SET has_webpage=?, has_checksums=?, has_attachments=?,
                       needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
            return old_status

        final_status = _keep_unscraped_public(auto_status, old_status, unscraped)
        pnc = int(final_status == "public" and not has_chk)
        if final_status != old_status:
            conn.execute(
                """UPDATE lb_master
                   SET lb_status=?, previous_status=?, has_webpage=?, has_checksums=?,
                       has_attachments=?, needs_review=?, public_no_checksums=?,
                       last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (final_status, old_status,
                 int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
            conn.execute(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
                "VALUES (?,?,?,?)",
                (_lb, old_status, final_status, _trigger),
            )
        else:
            conn.execute(
                """UPDATE lb_master
                   SET has_webpage=?, has_checksums=?, has_attachments=?,
                       needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
        return final_status

    return get_write_queue().execute(_run)


def batch_reconcile_lb_status(lb_numbers: list[int], trigger: str = "reconcile", db_path=None) -> None:
    """Reconcile lb_master for a batch of LB numbers in a single write transaction.

    Equivalent to calling reconcile_lb_status() for each entry individually, but
    uses bulk IN-queries so the total DB work is O(1) queries regardless of batch size
    instead of O(N). Designed for use by scrape_range() to avoid per-entry lock churn.

    Args:
        lb_numbers: LB numbers to reconcile. Duplicates are harmless.
        trigger: Value written to lb_status_history.trigger_event.
        db_path: Override the default database path (used in tests).
    """
    if not lb_numbers:
        return
    ph = ",".join("?" * len(lb_numbers))
    _lbs = lb_numbers
    _trigger = trigger

    def _run(conn) -> None:
        missing_set = {r[0] for r in conn.execute(
            f"SELECT lb_number FROM lb_missing WHERE lb_number IN ({ph})",
            _lbs,
        )}
        web_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM entries WHERE lb_number IN ({ph}) AND status='ok'",
            _lbs,
        )}
        chk_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM checksums WHERE lb_number IN ({ph})",
            _lbs,
        )}
        att_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM entry_files WHERE lb_number IN ({ph})",
            _lbs,
        )}
        existing = {r[0]: r for r in conn.execute(
            f"SELECT lb_number, lb_status, manual_override FROM lb_master WHERE lb_number IN ({ph})",
            _lbs,
        )}
        entry_set = {r[0] for r in conn.execute(
            f"SELECT lb_number FROM entries WHERE lb_number IN ({ph})",
            _lbs,
        )}

        insert_rows: list[tuple] = []
        history_rows: list[tuple] = []
        upd_override: list[tuple] = []
        upd_changed: list[tuple] = []
        upd_same: list[tuple] = []

        for lb in _lbs:
            if lb in missing_set:
                auto_status, needs_review = "nonexistent", 0
                hw = hc = ha = 0
            else:
                has_web = lb in web_set
                has_chk = lb in chk_set
                has_att = lb in att_set
                auto_status, needs_review = _compute_lb_status(has_web, has_chk, has_att)
                hw, hc, ha = int(has_web), int(has_chk), int(has_att)
            pnc = int(auto_status == "public" and hc == 0)

            if lb not in existing:
                initial_status = (
                    "public"
                    if _trigger == "flat_file_apply" and auto_status == "private"
                    else auto_status
                )
                pnc_initial = int(initial_status == "public" and hc == 0)
                insert_rows.append((lb, initial_status, hw, hc, ha, needs_review, pnc_initial))
                history_rows.append((lb, None, initial_status, _trigger))
                continue

            old_status = existing[lb]["lb_status"]
            manual = existing[lb]["manual_override"]
            if manual:
                pnc_manual = int(old_status == "public" and hc == 0)
                upd_override.append((hw, hc, ha, needs_review, pnc_manual, lb))
                continue
            auto_status = _keep_unscraped_public(
                auto_status, old_status, lb not in missing_set and lb not in entry_set
            )
            pnc = int(auto_status == "public" and hc == 0)
            if auto_status != old_status:
                upd_changed.append((auto_status, old_status, hw, hc, ha, needs_review, pnc, lb))
                history_rows.append((lb, old_status, auto_status, _trigger))
            else:
                upd_same.append((hw, hc, ha, needs_review, pnc, lb))

        if insert_rows:
            conn.executemany(
                "INSERT INTO lb_master"
                " (lb_number, lb_status, has_webpage, has_checksums, has_attachments,"
                "  needs_review, public_no_checksums)"
                " VALUES (?,?,?,?,?,?,?)",
                insert_rows,
            )
        if history_rows:
            conn.executemany(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event)"
                " VALUES (?,?,?,?)",
                history_rows,
            )
        if upd_override:
            conn.executemany(
                "UPDATE lb_master SET has_webpage=?, has_checksums=?, has_attachments=?,"
                " needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP"
                " WHERE lb_number=?",
                upd_override,
            )
        if upd_changed:
            conn.executemany(
                "UPDATE lb_master SET lb_status=?, previous_status=?, has_webpage=?,"
                " has_checksums=?, has_attachments=?, needs_review=?, public_no_checksums=?,"
                " last_status_at=CURRENT_TIMESTAMP WHERE lb_number=?",
                upd_changed,
            )
        if upd_same:
            conn.executemany(
                "UPDATE lb_master SET has_webpage=?, has_checksums=?, has_attachments=?,"
                " needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP"
                " WHERE lb_number=?",
                upd_same,
            )

    get_write_queue().execute(_run)


def reconcile_all_lb_master(db_path=None) -> dict:
    """Full rebuild of lb_master, extending to new max lb_number.

    Respects existing manual_override rows.
    Returns counts by status.
    """
    backup_database("pre_reconcile_all", db_path)

    conn = get_connection(db_path)
    max_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0
    # Also include LBs already in lb_master (they may exceed checksums max after deletions)
    master_max = conn.execute("SELECT MAX(lb_number) FROM lb_master").fetchone()[0] or 0
    # Also include scraped entries (public pages with no checksums would be missed otherwise)
    entries_max = conn.execute("SELECT MAX(lb_number) FROM entries").fetchone()[0] or 0
    effective_max = max(max_lb, master_max, entries_max)
    if effective_max == 0:
        return {"public": 0, "private": 0, "missing": 0, "max_lb": 0}

    batch_reconcile_lb_status(list(range(1, effective_max + 1)), trigger="reconcile", db_path=db_path)

    stats = get_lb_master_stats(db_path)
    return stats


def set_lb_manual_override(lb_number: int, status: str, notes: str,
                           set_by: str = "user", db_path=None) -> None:
    """Set a manual override on an lb_master row."""
    from datetime import UTC
    from datetime import datetime as _dt
    _lb, _status, _notes, _set_by = lb_number, status, notes, set_by
    _now = _dt.now(UTC).isoformat()

    def _run(conn) -> None:
        existing = conn.execute(
            "SELECT lb_status FROM lb_master WHERE lb_number=?", (_lb,)
        ).fetchone()
        old_status = existing["lb_status"] if existing else None
        conn.execute(
            """INSERT INTO lb_master(lb_number, lb_status, manual_override, manual_status,
                   manual_notes, manual_set_by, manual_set_at, needs_review,
                   has_webpage, has_checksums, has_attachments)
               VALUES(?,?,1,?,?,?,?,0,0,0,0)
               ON CONFLICT(lb_number) DO UPDATE SET
                   lb_status=excluded.lb_status,
                   manual_override=1,
                   manual_status=excluded.manual_status,
                   manual_notes=excluded.manual_notes,
                   manual_set_by=excluded.manual_set_by,
                   manual_set_at=excluded.manual_set_at,
                   last_status_at=CURRENT_TIMESTAMP""",
            (_lb, _status, _status, _notes, _set_by, _now),
        )
        conn.execute(
            "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
            "VALUES(?,?,?,'manual')",
            (_lb, old_status, _status),
        )

    get_write_queue().execute(_run)


def clear_lb_manual_override(lb_number: int, db_path=None) -> str:
    """Clear a manual override and immediately reconcile. Returns new auto status."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute(
            """UPDATE lb_master SET manual_override=0, manual_status=NULL,
                   manual_notes=NULL, manual_set_by=NULL, manual_set_at=NULL
               WHERE lb_number=?""",
            (_lb,),
        )
    )
    return reconcile_lb_status(lb_number, trigger="manual_clear", db_path=db_path)


def export_overrides(db_path=None) -> list[dict]:
    """Return all manual overrides as a list of dicts for JSON export.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        List of dicts with keys: lb_number, manual_status, manual_notes,
        manual_set_by, manual_set_at — one per lb_master row where
        manual_override=1, ordered by lb_number ascending.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT lb_number, manual_status, manual_notes, manual_set_by, manual_set_at
           FROM lb_master WHERE manual_override=1 ORDER BY lb_number"""
    ).fetchall()
    return [dict(r) for r in rows]


def import_overrides(overrides: list[dict], db_path=None) -> dict:
    """Upsert a list of override dicts into lb_master.

    Skips entries whose lb_number is out of the valid range (< 1 or greater
    than the current MAX(lb_number) in lb_master).  Writes an
    lb_status_history row with trigger_event='import' for each upserted row.

    Args:
        overrides: List of dicts, each containing at minimum ``lb_number``.
            Optional keys: ``manual_status``, ``manual_notes``,
            ``manual_set_by``.
        db_path: Optional path to the SQLite database file.

    Returns:
        Dict ``{imported: int, skipped: int}``.
    """
    conn = get_connection(db_path)
    max_lb = conn.execute("SELECT MAX(lb_number) FROM lb_master").fetchone()[0] or 0
    imported = 0
    skipped = 0
    for item in overrides:
        lb = item.get("lb_number")
        if not isinstance(lb, int) or lb < 1 or lb > max_lb:
            skipped += 1
            continue
        set_lb_manual_override(
            lb,
            item.get("manual_status", ""),
            item.get("manual_notes", ""),
            item.get("manual_set_by", "import"),
            db_path,
        )
        # The history row for the manual call is already written by
        # set_lb_manual_override; add a second row to record the import event.
        get_write_queue().execute(
            lambda c, _lb=lb: c.execute(
                """INSERT INTO lb_status_history (lb_number, old_status, new_status, trigger_event)
                   SELECT lb_number, previous_status, lb_status, 'import'
                   FROM lb_master WHERE lb_number=?""",
                (_lb,),
            )
        )
        imported += 1
    logger.info(
        "import_overrides: %d imported, %d skipped", imported, skipped
    )
    return {"imported": imported, "skipped": skipped}


def get_lb_master_row(lb_number: int, db_path=None) -> dict | None:
    """Return the lb_master row for an LB number, or None if absent."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM lb_master WHERE lb_number=?", (lb_number,)
    ).fetchone()
    return dict(row) if row else None


def get_lb_master_stats(db_path=None) -> dict:
    """Return {public, private, missing, max_lb, overrides, needs_review} counts."""
    conn = get_connection(db_path)
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN lb_status='public'      THEN 1 ELSE 0 END), 0) AS public,
            COALESCE(SUM(CASE WHEN lb_status='private'     THEN 1 ELSE 0 END), 0) AS private,
            COALESCE(SUM(CASE WHEN lb_status='missing'     THEN 1 ELSE 0 END), 0) AS missing,
            COALESCE(SUM(CASE WHEN lb_status='nonexistent' THEN 1 ELSE 0 END), 0) AS nonexistent,
            COALESCE(MAX(lb_number), 0)                                             AS max_lb,
            COALESCE(SUM(manual_override), 0)                                       AS overrides,
            COALESCE(SUM(needs_review), 0)                                          AS needs_review,
            COALESCE(SUM(public_no_checksums), 0)                                   AS public_no_checksums
        FROM lb_master
    """).fetchone()
    return dict(row) if row else {
        "public": 0, "private": 0, "missing": 0, "nonexistent": 0,
        "max_lb": 0, "overrides": 0, "needs_review": 0, "public_no_checksums": 0,
    }


def is_lb_missing(lb_number: int, db_path=None) -> bool:
    """Return True if lb_number is in lb_missing (confirmed to not exist on the LB site)."""
    conn = get_connection(db_path)
    return bool(conn.execute(
        "SELECT 1 FROM lb_missing WHERE lb_number=?", (lb_number,)
    ).fetchone())


def get_lb_missing_list(db_path=None) -> list[dict]:
    """Return all rows in lb_missing ordered by lb_number."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT lb_number, confirmed_date, notes FROM lb_missing ORDER BY lb_number"
    ).fetchall()
    return [dict(r) for r in rows]


def add_lb_missing(lb_number: int, confirmed_date: str = "", notes: str = "",
                   db_path=None) -> None:
    """Add an lb_number to lb_missing and immediately reconcile its lb_master status."""
    _lb, _date, _notes = lb_number, confirmed_date, notes

    def _run(conn) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO lb_missing(lb_number, confirmed_date, notes) VALUES(?,?,?)",
            (_lb, _date, _notes),
        )

    get_write_queue().execute(_run)
    reconcile_lb_status(lb_number, trigger="lb_missing_add", db_path=db_path)


def remove_lb_missing(lb_number: int, db_path=None) -> None:
    """Remove an lb_number from lb_missing and immediately reconcile its lb_master status."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_missing WHERE lb_number=?", (_lb,))
    )
    reconcile_lb_status(lb_number, trigger="lb_missing_remove", db_path=db_path)


def get_lb_status(lb_number: int, db_path=None) -> str | None:
    """Return lb_master.lb_status for a single LB, or None if not in table."""
    row = get_lb_master_row(lb_number, db_path)
    return row["lb_status"] if row else None


def is_postable_to_forum(lb_number: int, db_path=None) -> tuple[bool, str | None]:
    """Return (allowed, reason) for forum posting.

    Blocks private and missing LBs; passes public ones.
    Blocks with 'status_unknown' if the LB has no lb_master row at all.
    """
    status = get_lb_status(lb_number, db_path)
    if status is None:
        return False, "status_unknown"
    if status == "private":
        return False, "lb_private"
    if status == "missing":
        return False, "lb_missing"
    return True, None


def is_seedable_to_tracker(lb_number: int, db_path=None) -> tuple[bool, str | None]:
    """Return (allowed, reason) for seeding a recording to a public tracker.

    The seeding counterpart of :func:`is_postable_to_forum`: ``lb_status`` is
    the authority on what may leave the collection. Only 'public' passes.

    Args:
        lb_number: LB number being seeded.
        db_path: Optional DB path override.

    Returns:
        (allowed, reason). ``reason`` is None when allowed, otherwise one of
        'status_unknown', 'lb_private', 'lb_missing', 'lb_nonexistent'.
    """
    status = get_lb_status(lb_number, db_path)
    if status is None:
        return False, "status_unknown"
    if status == "private":
        return False, "lb_private"
    if status == "missing":
        return False, "lb_missing"
    if status == "nonexistent":
        return False, "lb_nonexistent"
    return True, None


def get_lb_master_list(status: str | None = None, override_only: bool = False,
                       review_only: bool = False, limit: int = 500,
                       offset: int = 0, db_path=None) -> list[dict]:
    """Return paginated lb_master rows with optional filters."""
    conn = get_connection(db_path)
    clauses = []
    params: list = []
    if status:
        clauses.append("lb_status=?")
        params.append(status)
    if override_only:
        clauses.append("manual_override=1")
    if review_only:
        clauses.append("needs_review=1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM lb_master {where} ORDER BY lb_number LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def get_lb_status_history(lb_number: int, limit: int = 50, db_path=None) -> list[dict]:
    """Return transition history for a single LB, newest first."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM lb_status_history WHERE lb_number=? ORDER BY changed_at DESC LIMIT ?",
        (lb_number, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Curator mode (user-local meta flag) ────────────────────────────────────────

def is_curator(db_path=None) -> bool:
    """Return True if the local install is flagged as the curator.

    Curator mode unlocks master-data publishing UI in Setup tab and
    write access to alias/override editing once those features ship.
    The flag is stored in `meta.is_curator='1'|'0'` and never ships in
    a master export (it's in USER_META_KEYS).
    """
    return (get_meta("is_curator", db_path) or "0") == "1"


def set_curator(enabled: bool, db_path=None) -> None:
    """Toggle the curator flag for this install."""
    set_meta("is_curator", "1" if enabled else "0", db_path)
