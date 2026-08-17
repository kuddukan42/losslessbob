"""Read-only LB-catalogue coverage summary (GET /api/lb/coverage).

Aggregates lb_master / my_collection / checksums / recording_families / entries
into a single snapshot+coverage+stats payload for the coverage-award screen.
Every query is defensive: a fresh or partial DB returns a valid zeroed payload
rather than raising, since this endpoint is read-only and must never 500.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import sqlite3

from backend.torrent_maker import _parse_date
from backend.version import VERSION

logger = logging.getLogger(__name__)

# Only 'nonexistent' is excluded from the denominator: the LB number was
# allocated but no release ever existed, so it is not a gap the user can fill.
# 'missing' (tape exists, LB page gone) IS a fillable gap and stays counted —
# same rule as backend.db.get_missing_from_collection / gap_analysis / timeline.
_HELD_EXCLUDED_STATUSES = ("nonexistent",)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """Return True if `name` exists as a table in the connected DB."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _decade_bucket(date_str: str | None) -> int | None:
    """Return the decade (e.g. 1950, 2020) for a LosslessBob date_str, or None.

    Reuses backend.torrent_maker._parse_date's M/D/YY-vs-M/D/YYYY 2-digit-year
    rule rather than re-implementing it. Unparseable or missing dates yield None
    so the caller can skip them.
    """
    if not date_str:
        return None
    parsed = _parse_date(date_str)
    year_part = parsed[:4]
    if not year_part.isdigit():
        return None
    year = int(year_part)
    return (year // 10) * 10


def _decade_label(decade: int) -> str:
    """Return the two-digit decade label, e.g. 1950 -> "50s", 2020 -> "20s"."""
    return f"{decade % 100:02d}s"


def _get_snapshot(conn: sqlite3.Connection) -> dict:
    """Return the {label, version, published_at, last_import, entry_count} block."""
    meta: dict[str, str | None] = {
        "master_published_at": None,
        "master_version": None,
        "last_import_date": None,
    }
    if _table_exists(conn, "meta"):
        try:
            rows = conn.execute(
                "SELECT key, value FROM meta WHERE key IN "
                "('master_published_at', 'master_version', 'last_import_date')"
            ).fetchall()
            for row in rows:
                meta[row["key"]] = row["value"]
        except sqlite3.Error:
            logger.exception("lb_coverage: failed reading meta table")

    entry_count = 0
    if _table_exists(conn, "entries"):
        try:
            entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        except sqlite3.Error:
            logger.exception("lb_coverage: failed counting entries")

    published_at = meta["master_published_at"]
    label = None
    if published_at and len(published_at) >= 7:
        label = published_at[:7].replace("-", ".")

    return {
        "label": label,
        "version": meta["master_version"],
        "published_at": published_at,
        "last_import": meta["last_import_date"],
        "entry_count": entry_count,
    }


def _held_sql(conn: sqlite3.Connection) -> str:
    """Return the SQL expression deciding whether `lm.lb_number` is held.

    An LB counts as held when it is in ``my_collection`` directly *or* via an
    ``lb_alias`` link in either direction — the same alias folding
    ``backend.db.get_missing_from_collection`` applies, so the coverage figure
    and the Collection screen's "Not in collection" list agree. Degrades to the
    direct-membership test when ``lb_alias`` is absent.
    """
    direct = "EXISTS (SELECT 1 FROM my_collection mc WHERE mc.lb_number = lm.lb_number)"
    if not _table_exists(conn, "lb_alias"):
        return direct
    return f"""(
        {direct}
        OR EXISTS (SELECT 1 FROM lb_alias la JOIN my_collection mc
                     ON la.canonical_lb = mc.lb_number
                   WHERE la.alias_lb = lm.lb_number)
        OR EXISTS (SELECT 1 FROM lb_alias la JOIN my_collection mc
                     ON la.alias_lb = mc.lb_number
                   WHERE la.canonical_lb = lm.lb_number)
    )"""


def _get_coverage(conn: sqlite3.Connection) -> dict:
    """Return the {entries_total, entries_held, ..., by_decade, ledger, signed_by} block."""
    entries_total = 0
    entries_held = 0
    by_decade: dict[int, dict[str, int]] = {}

    if _table_exists(conn, "lb_master"):
        try:
            placeholders = ",".join("?" for _ in _HELD_EXCLUDED_STATUSES)
            entries_total = conn.execute(
                f"SELECT COUNT(*) FROM lb_master WHERE lb_status NOT IN ({placeholders})",
                _HELD_EXCLUDED_STATUSES,
            ).fetchone()[0]

            held_sql = _held_sql(conn)

            if _table_exists(conn, "my_collection"):
                entries_held = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM lb_master lm
                    WHERE lm.lb_status NOT IN ({placeholders})
                      AND {held_sql}
                    """,
                    _HELD_EXCLUDED_STATUSES,
                ).fetchone()[0]

            if _table_exists(conn, "entries"):
                held_expr = held_sql if _table_exists(conn, "my_collection") else "0"
                rows = conn.execute(
                    f"""
                    SELECT e.date_str AS date_str,
                           CASE WHEN {held_expr} THEN 1 ELSE 0 END AS held
                    FROM lb_master lm
                    JOIN entries e ON e.lb_number = lm.lb_number
                    WHERE lm.lb_status NOT IN ({placeholders})
                    """,
                    _HELD_EXCLUDED_STATUSES,
                ).fetchall()
                for row in rows:
                    decade = _decade_bucket(row["date_str"])
                    if decade is None:
                        continue
                    bucket = by_decade.setdefault(decade, {"total": 0, "held": 0})
                    bucket["total"] += 1
                    bucket["held"] += row["held"]
        except sqlite3.Error:
            logger.exception("lb_coverage: failed computing entries_total/held")

    entries_missing = entries_total - entries_held

    recordings = 0
    if _table_exists(conn, "checksums"):
        try:
            recordings = conn.execute("SELECT COUNT(*) FROM checksums").fetchone()[0]
        except sqlite3.Error:
            logger.exception("lb_coverage: failed counting checksums")

    families = 0
    ledger_pairs: list[str] = []
    if _table_exists(conn, "recording_families"):
        try:
            families = conn.execute(
                "SELECT COUNT(DISTINCT fam_id) FROM recording_families"
            ).fetchone()[0]
            rows = conn.execute("SELECT lb_number, fam_id FROM recording_families").fetchall()
            ledger_pairs = sorted(f"{row['lb_number']}|{row['fam_id']}" for row in rows)
        except sqlite3.Error:
            logger.exception("lb_coverage: failed computing families/ledger")

    ledger_sha256 = hashlib.sha256("\n".join(ledger_pairs).encode("utf-8")).hexdigest()

    coverage_pct = round(entries_held / entries_total, 4) if entries_total else 0.0

    by_decade_list = [
        {"decade": decade, "label": _decade_label(decade),
         "total": bucket["total"], "held": bucket["held"]}
        for decade, bucket in sorted(by_decade.items())
    ]

    return {
        "entries_total": entries_total,
        "entries_held": entries_held,
        "entries_missing": entries_missing,
        "recordings": recordings,
        "families": families,
        "coverage_pct": coverage_pct,
        "complete": entries_missing == 0,
        "by_decade": by_decade_list,
        "ledger_sha256": ledger_sha256,
        "signed_by": f"losslessbob {VERSION}",
    }


def _get_stats(conn: sqlite3.Connection) -> dict:
    """Return the {first_entry_filed_at, days_active} block."""
    first_entry_filed_at = None
    days_active = 0

    if _table_exists(conn, "my_collection"):
        try:
            row = conn.execute(
                "SELECT MIN(confirmed_at) AS min_confirmed FROM my_collection"
            ).fetchone()
            min_confirmed = row["min_confirmed"] if row else None
            if min_confirmed:
                first_entry_filed_at = str(min_confirmed)[:10]
                try:
                    filed_date = _dt.date.fromisoformat(first_entry_filed_at)
                    days_active = max(0, (_dt.date.today() - filed_date).days)
                except ValueError:
                    first_entry_filed_at = None
                    days_active = 0
        except sqlite3.Error:
            logger.exception("lb_coverage: failed computing first_entry_filed_at")

    return {"first_entry_filed_at": first_entry_filed_at, "days_active": days_active}


#: Ledger filters (TODO-305). "unmatched" = held but with no recording family,
#: i.e. the entry is in the collection but TapeMatch has not filed it yet.
LEDGER_FILTERS = ("all", "held", "missing", "unmatched", "review")

#: Hard ceiling on ``per_page`` so a hand-written URL cannot ask for the whole
#: catalogue in one response.
LEDGER_MAX_PER_PAGE = 500


def _ledger_where(filt: str, held_sql: str) -> str:
    """Return the SQL predicate for one ledger filter (already-validated)."""
    return {
        "all": "1",
        "held": held_sql,
        "missing": f"NOT {held_sql}",
        "unmatched": f"{held_sql} AND rf.fam_id IS NULL",
        "review": "lm.needs_review = 1",
    }[filt]


def get_ledger(conn: sqlite3.Connection, *, page: int = 1, per_page: int = 50,
               filt: str = "all", q: str = "", lb: int | None = None) -> dict:
    """Return one page of the per-entry LB ledger for GET /api/lb/coverage/ledger.

    Every non-``nonexistent`` LB number is a row, held or not — the ledger is the
    audit surface behind the coverage percentage, so the gaps have to be visible
    alongside what is filed.

    Args:
        conn: An open sqlite3 connection (``sqlite3.Row`` row_factory expected).
        page: 1-based page number; values below 1 are clamped.
        per_page: Rows per page, clamped to [1, :data:`LEDGER_MAX_PER_PAGE`].
        filt: One of :data:`LEDGER_FILTERS`; anything else falls back to "all".
        q: Free-text filter over LB number, date and location.
        lb: Deep-link target. When given, the returned ``page`` is the one
            holding that LB number (``q``/``page`` are ignored), so a "jump to
            LB#" link lands on the row rather than on page 1.

    Returns:
        ``{rows, page, pages, per_page, total, filter, q, lb}``. Missing tables
        yield an empty page rather than raising.
    """
    if filt not in LEDGER_FILTERS:
        filt = "all"
    per_page = max(1, min(int(per_page or 50), LEDGER_MAX_PER_PAGE))
    page = max(1, int(page or 1))

    empty = {"rows": [], "page": 1, "pages": 0, "per_page": per_page,
             "total": 0, "filter": filt, "q": q, "lb": lb}
    if not _table_exists(conn, "lb_master"):
        return empty

    has_collection = _table_exists(conn, "my_collection")
    has_families = _table_exists(conn, "recording_families")
    has_entries = _table_exists(conn, "entries")

    held_sql = _held_sql(conn) if has_collection else "0"
    placeholders = ",".join("?" for _ in _HELD_EXCLUDED_STATUSES)

    joins = []
    if has_entries:
        joins.append("LEFT JOIN entries e ON e.lb_number = lm.lb_number")
    if has_families:
        # One family per LB in practice; MIN keeps the join single-valued.
        joins.append("""LEFT JOIN (SELECT lb_number, MIN(fam_id) AS fam_id
                                     FROM recording_families GROUP BY lb_number) rf
                          ON rf.lb_number = lm.lb_number""")
    if has_collection:
        joins.append("""LEFT JOIN (SELECT lb_number, MIN(folder_name) AS folder_name,
                                          MIN(confirmed_at) AS confirmed_at,
                                          MAX(lbdir_verified_at) AS lbdir_verified_at
                                     FROM my_collection GROUP BY lb_number) mcx
                          ON mcx.lb_number = lm.lb_number""")
    join_sql = "\n".join(joins)

    date_expr = "e.date_str" if has_entries else "NULL"
    loc_expr = "e.location" if has_entries else "NULL"
    fam_expr = "rf.fam_id" if has_families else "NULL"
    folder_expr = "mcx.folder_name" if has_collection else "NULL"
    filed_expr = "mcx.confirmed_at" if has_collection else "NULL"
    verified_expr = "mcx.lbdir_verified_at" if has_collection else "NULL"
    # "unmatched" reads rf.fam_id; without the families table nothing qualifies.
    where_extra = _ledger_where(filt, held_sql) if (has_families or filt != "unmatched") else "0"

    params: list = list(_HELD_EXCLUDED_STATUSES)
    where = [f"lm.lb_status NOT IN ({placeholders})", f"({where_extra})"]

    if lb is not None:
        pass
    elif q:
        needle = f"%{q.strip().lower()}%"
        where.append(
            f"(CAST(lm.lb_number AS TEXT) LIKE ? OR LOWER(COALESCE({date_expr}, '')) LIKE ?"
            f" OR LOWER(COALESCE({loc_expr}, '')) LIKE ?)"
        )
        params += [needle, needle, needle]

    where_sql = " AND ".join(where)

    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM lb_master lm\n{join_sql}\nWHERE {where_sql}", params
        ).fetchone()[0]
    except sqlite3.Error:
        logger.exception("lb_coverage: ledger count failed")
        return empty

    pages = (total + per_page - 1) // per_page

    if lb is not None:
        try:
            before = conn.execute(
                f"SELECT COUNT(*) FROM lb_master lm\n{join_sql}\n"
                f"WHERE {where_sql} AND lm.lb_number < ?", [*params, lb]
            ).fetchone()[0]
            page = before // per_page + 1
        except sqlite3.Error:
            logger.exception("lb_coverage: ledger deep-link page lookup failed")
            page = 1
    if pages:
        page = min(page, pages)

    offset = (page - 1) * per_page
    try:
        rows = conn.execute(
            f"""
            SELECT lm.lb_number                       AS lb_number,
                   lm.lb_status                       AS lb_status,
                   lm.needs_review                    AS needs_review,
                   {date_expr}                        AS date_str,
                   {loc_expr}                         AS location,
                   {fam_expr}                         AS fam_id,
                   {folder_expr}                      AS folder_name,
                   {filed_expr}                       AS filed_at,
                   {verified_expr}                    AS verified_at,
                   CASE WHEN {held_sql} THEN 1 ELSE 0 END AS held
            FROM lb_master lm
            {join_sql}
            WHERE {where_sql}
            ORDER BY lm.lb_number
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()
    except sqlite3.Error:
        logger.exception("lb_coverage: ledger page query failed")
        return empty

    out = []
    for row in rows:
        held = bool(row["held"])
        out.append({
            "lb_number": row["lb_number"],
            "lb_status": row["lb_status"],
            "date_str": row["date_str"],
            "location": row["location"],
            "fam_id": row["fam_id"],
            "folder_name": row["folder_name"],
            "filed_at": str(row["filed_at"])[:10] if row["filed_at"] else None,
            "verified": bool(row["verified_at"]),
            "needs_review": bool(row["needs_review"]),
            "held": held,
            "state": ("missing" if not held
                      else "unmatched" if row["fam_id"] is None
                      else "verified" if row["verified_at"] else "held"),
        })

    return {"rows": out, "page": page, "pages": pages, "per_page": per_page,
            "total": total, "filter": filt, "q": q, "lb": lb}


def get_snapshots(conn: sqlite3.Connection, *, limit: int = 50) -> dict:
    """Return LB-catalogue snapshot history for GET /api/lb/snapshots.

    Reads ``lb_snapshot_history`` (written by ``backend.db.import_master_db``),
    newest first. A DB whose master predates that table — or which has never
    imported one — still gets a single ``synthetic`` row derived from ``meta``,
    so ``/lbdir/sync`` shows the installed catalogue instead of an empty page.

    Args:
        conn: An open sqlite3 connection (``sqlite3.Row`` row_factory expected).
        limit: Maximum rows to return, clamped to [1, 200].

    Returns:
        ``{snapshots, current, total}`` — ``current`` is the live meta block
        from :func:`_get_snapshot`.
    """
    import json

    limit = max(1, min(int(limit or 50), 200))
    current = _get_snapshot(conn)

    snapshots: list[dict] = []
    if _table_exists(conn, "lb_snapshot_history"):
        try:
            rows = conn.execute(
                "SELECT * FROM lb_snapshot_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            for row in rows:
                keys = row.keys()

                def _loads(key: str, row=row, keys=keys) -> dict:
                    if key not in keys or not row[key]:
                        return {}
                    try:
                        return json.loads(row[key])
                    except (ValueError, TypeError):
                        return {}

                snapshots.append({
                    "id": row["id"],
                    "label": (row["master_published_at"] or "")[:7].replace("-", ".") or None,
                    "master_version": row["master_version"],
                    "master_published_at": row["master_published_at"],
                    "imported_at": row["imported_at"],
                    "source": row["source"] or "unknown",
                    "entries_total": row["entries_total"],
                    "entries_held": row["entries_held"],
                    "entries_added": row["entries_added"],
                    "lb_status_changes": row["lb_status_changes"],
                    "status_counts": _loads("status_counts_json"),
                    "row_counts": _loads("row_counts_json"),
                    "backup_path": row["backup_path"],
                    "synthetic": False,
                })
        except sqlite3.Error:
            logger.exception("lb_coverage: failed reading lb_snapshot_history")

    if not snapshots and current["version"]:
        cov = _get_coverage(conn)
        snapshots.append({
            "id": None,
            "label": current["label"],
            "master_version": current["version"],
            "master_published_at": current["published_at"],
            "imported_at": current["last_import"],
            "source": "unknown",
            "entries_total": cov["entries_total"],
            "entries_held": cov["entries_held"],
            "entries_added": None,
            "lb_status_changes": None,
            "status_counts": {},
            "row_counts": {},
            "backup_path": None,
            # No history row covers this catalogue — it was installed before
            # TODO-305 shipped. Flagged so the GUI can say so rather than
            # implying a real import record exists.
            "synthetic": True,
        })

    return {"snapshots": snapshots, "current": current, "total": len(snapshots)}


def get_coverage(conn: sqlite3.Connection) -> dict:
    """Return the full LB-catalogue coverage payload for GET /api/lb/coverage.

    Args:
        conn: An open sqlite3 connection (row_factory sqlite3.Row expected).

    Returns:
        A dict with "snapshot", "coverage", and "stats" keys. Every field is
        defensively computed: missing tables or empty results yield zeroed or
        null values instead of raising.
    """
    return {
        "snapshot": _get_snapshot(conn),
        "coverage": _get_coverage(conn),
        "stats": _get_stats(conn),
    }
