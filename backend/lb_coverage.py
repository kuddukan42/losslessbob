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
