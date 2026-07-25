"""Concert-date coverage classification (originally TODO-256's Gaps view;
instructions/complete/FABLE_GAPS_VIEW.md). Every known Dylan concert date
(``olof_events``) classified by whether a recording circulates (an
``entries`` row resolves to that date). Read-only end to end: no derived
table, no writes, no recompute-chain hook. Computed live per request —
sub-second at this scale (~4-5k events, ~16k entries), so there's nothing to
keep in sync or go stale (see spec §D1).

The standalone Gaps screen was retired once its coverage grid became a
Library performance-lens view: :func:`uncirculated_dates` feeds the
recording-less ``uncirculated``/``upcoming`` rows `db.get_performances`
unions into the Library, and :func:`get_date_detail` backs the Library
DetailPanel's Olof tab for those rows via ``GET /api/shows/<iso>/olof``.

Entry points: :func:`classify_date` (pure classifier, kept free of DB access
so it's trivially unit-testable), :func:`uncirculated_dates` (gap/future
dates the Library appends as recording-less rows), :func:`get_date_detail`
(drill-down: olof event rows, entries, family data for one date).
"""
from __future__ import annotations

import datetime
import logging
import sqlite3

from backend.db import get_connection
from backend.geocoder import entry_date_month_key, entry_date_to_iso

log = logging.getLogger(__name__)

# olof_events emits compound labels for festival-slot concerts (e.g.
# "concert - outlaw music festival") — match both plain and compound.
# Some private rehearsal sessions (Rundown/NBC Studios, 1978-1980) are
# mistyped event_type='concert' upstream because they logged a numbered
# setlist; tour_name still says "... Rehearsals" for every event in those
# segments, so exclude on that instead of trusting event_type alone.
_CONCERT_TYPE_FILTER = (
    "((event_type = 'concert' OR event_type LIKE 'concert - %') "
    "AND tour_name NOT LIKE '%ehearsal%')"
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return True if *table_name* exists in the connected SQLite database.

    Local copy of the geocoder.py feature-detect pattern (olof_events,
    recording_families may be absent on older installs).

    Args:
        conn: SQLite connection.
        table_name: Table name to check for.

    Returns:
        True if a table with that name exists, False otherwise.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD``."""
    return datetime.date.today().isoformat()


def _now_iso() -> str:
    """Return the current local timestamp as an ISO string (second precision)."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def classify_date(
    date_iso: str,
    today_iso: str,
    exact_dates: set[str],
    partial_month_keys: set[str],
) -> str:
    """Classify one concert date's coverage. Pure function — see spec §D1.

    Args:
        date_iso: The concert date, ``'YYYY-MM-DD'``.
        today_iso: Today's date, ``'YYYY-MM-DD'`` — dates after this are
            ``'future'`` regardless of coverage.
        exact_dates: ISO dates with >=1 exact-matching entry (private/missing
            entries count; nonexistent lb_master rows are pre-excluded by
            the caller).
        partial_month_keys: ``'YYYY-MM'`` keys with >=1 ``xx``-partial entry.

    Returns:
        One of ``'future'``, ``'covered'``, ``'partial'``, ``'gap'``.
    """
    if date_iso > today_iso:
        return "future"
    if date_iso in exact_dates:
        return "covered"
    if date_iso[:7] in partial_month_keys:
        return "partial"
    return "gap"


def _entry_coverage_maps(
    conn: sqlite3.Connection,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Map ISO dates and month keys to the lb_numbers that cover them.

    Excludes entries whose lb_master status is ``nonexistent`` (a confirmed
    non-existent LB number proves nothing about the show); private/missing
    entries still count as coverage — see spec §1.

    Args:
        conn: SQLite connection.

    Returns:
        ``(exact, partial)`` — ``exact`` maps ``'YYYY-MM-DD'`` -> lb_numbers
        for entries with a clean date_str; ``partial`` maps ``'YYYY-MM'`` ->
        lb_numbers for entries whose date_str contains ``xx``.
    """
    rows = conn.execute(
        """
        SELECT e.lb_number, e.date_str
        FROM entries e
        LEFT JOIN lb_master m ON m.lb_number = e.lb_number
        WHERE e.date_str IS NOT NULL AND e.date_str != ''
          AND (m.lb_status IS NULL OR m.lb_status != 'nonexistent')
        """
    ).fetchall()
    exact: dict[str, list[int]] = {}
    partial: dict[str, list[int]] = {}
    for row in rows:
        lb_number, date_str = row["lb_number"], row["date_str"]
        iso = entry_date_to_iso(date_str)
        if iso:
            exact.setdefault(iso, []).append(lb_number)
            continue
        month_key = entry_date_month_key(date_str)
        if month_key:
            partial.setdefault(month_key, []).append(lb_number)
    return exact, partial


def _olof_concert_events(
    conn: sqlite3.Connection, year: int | None = None
) -> list[sqlite3.Row]:
    """All olof_events concert rows with a clean ISO date_str.

    Args:
        conn: SQLite connection.
        year: Optional year filter (``date_str LIKE 'YYYY-%'``).

    Returns:
        Rows ordered by date_str then event_id, one row per event (two-show
        dates yield two rows — group by date_str for per-date cells).
    """
    query = f"""
        SELECT event_id, date_str, event_type, venue, city, region, country,
               tour_name, recording_kind, recording_mins
        FROM olof_events
        WHERE {_CONCERT_TYPE_FILTER} AND date_str != ''
    """
    params: tuple = ()
    if year is not None:
        query += " AND date_str LIKE ?"
        params = (f"{year:04d}-%",)
    query += " ORDER BY date_str, event_id"
    return conn.execute(query, params).fetchall()


def _group_by_date(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    """Group olof event rows by date_str, preserving row order within a date."""
    by_date: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_date.setdefault(row["date_str"], []).append(row)
    return by_date


def uncirculated_dates(db_path: str | None = None) -> list[dict]:
    """Olof concert dates with no circulating recording (gap or future).

    Used by the Library's performance lens to surface known Dylan concerts
    that have zero ``entries`` coverage as recording-less rows, plus the
    not-yet-happened future dates, so they're first-class Library rows —
    this is what replaced the retired standalone Gaps screen.

    Args:
        db_path: Optional database path override.

    Returns:
        One dict per olof concert date classified ``'gap'`` or ``'future'``
        by :func:`classify_date` — ``'covered'`` and ``'partial'`` dates are
        skipped since those already have entries rows in the Library. Each
        dict is ``{date_iso, coverage, venue, city, tour}`` where
        ``coverage`` is ``'uncirculated'`` (was ``'gap'``) or ``'upcoming'``
        (was ``'future'``); ``venue``/``city``/``tour`` come from the first
        olof row on that date (``None`` for empty strings). Returns ``[]``
        if olof_events is absent.
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "olof_events"):
        return []

    exact, partial = _entry_coverage_maps(conn)
    exact_dates = set(exact)
    partial_month_keys = set(partial)
    today_iso = _today_iso()

    by_date = _group_by_date(_olof_concert_events(conn))
    results = []
    for date_iso in sorted(by_date):
        cls = classify_date(date_iso, today_iso, exact_dates, partial_month_keys)
        if cls not in ("gap", "future"):
            continue
        first = by_date[date_iso][0]
        results.append(
            {
                "date_iso": date_iso,
                "coverage": "uncirculated" if cls == "gap" else "upcoming",
                "venue": first["venue"] or None,
                "city": first["city"] or None,
                "tour": first["tour_name"] or None,
            }
        )
    return results


def get_date_detail(date_iso: str, db_path: str | None = None) -> dict:
    """Drill-down for one date: olof event rows, entries, and family data.

    Backs ``GET /api/shows/<date_iso>/olof``, called by the Library
    DetailPanel's Olof tab for uncirculated/upcoming (olof-only, no
    recordings) performance rows — see ``gui_next``'s ``OlofShowZone``.

    Args:
        date_iso: The date to drill into, ``'YYYY-MM-DD'``.
        db_path: Optional database path override.

    Returns:
        ``{available, date_iso, events, entries, partial_entries,
        recording_families}``. ``events`` is the full olof_events rows
        (incl. notes/bobtalk/recording fields) for exact-date concerts.
        ``entries`` is every entries row resolving exactly to this date
        (lb_number, date_str, rating, status, taper_name); ``partial_entries``
        is ``xx``-partial entries whose month matches. ``recording_families``
        is empty if the table doesn't exist (older installs). ``available``
        is False if olof_events itself is absent.
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "olof_events"):
        return {"available": False, "date_iso": date_iso}

    event_rows = conn.execute(
        f"SELECT * FROM olof_events WHERE {_CONCERT_TYPE_FILTER} AND date_str = ? "
        "ORDER BY event_id",
        (date_iso,),
    ).fetchall()

    month_key = date_iso[:7]
    entries = []
    partial_entries = []
    for row in conn.execute(
        "SELECT lb_number, date_str, rating, status, taper_name FROM entries "
        "WHERE date_str IS NOT NULL AND date_str != ''"
    ).fetchall():
        iso = entry_date_to_iso(row["date_str"])
        if iso == date_iso:
            entries.append(dict(row))
        elif iso is None and entry_date_month_key(row["date_str"]) == month_key:
            partial_entries.append(dict(row))

    families = []
    if _table_exists(conn, "recording_families"):
        families = [
            dict(r)
            for r in conn.execute(
                "SELECT lb_number, fam_id, run_id FROM recording_families "
                "WHERE concert_date = ?",
                (date_iso,),
            ).fetchall()
        ]

    return {
        "available": True,
        "date_iso": date_iso,
        "events": [dict(e) for e in event_rows],
        "entries": entries,
        "partial_entries": partial_entries,
        "recording_families": families,
    }
