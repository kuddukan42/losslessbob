"""Timeline navigator (FABLE_IDEAS UI-2, instructions/FABLE_TIMELINE.md).

Decade -> Tour -> Night browsing of the concert archive, colored by the best
grade held for each night. Read-only end to end: no derived/materialized
table, computed live per request -- mirrors ``backend/gap_analysis.py``'s
read-only philosophy (spec §D1). Concert-only ``olof_events`` rows (reusing
``gap_analysis``' event-side filter) are joined to ``entries`` by resolved
ISO date, excluding ``nonexistent``-status ``lb_master`` rows (mirroring
``gap_analysis._entry_coverage_maps``' entry-side exclusion) to find each
night's held tapes and reduce them to a single best grade.

Entry points: :func:`get_summary` (decade grid), :func:`get_decade_detail`
(tours within a decade), :func:`get_tour_detail` (nights within a tour).
"""
from __future__ import annotations

import datetime
import logging
import sqlite3

from backend.db import get_connection
from backend.gap_analysis import _olof_concert_events, _table_exists
from backend.geocoder import entry_date_to_iso

log = logging.getLogger(__name__)

# entries.rating letter scale, best to worst -- see spec §1: no shared
# backend/frontend ordinal exists yet, every occurrence (ScreenSongs.tsx
# GRADE_ORDER, ScreenSearch.tsx RATING_RANK, DetailPanel.tsx,
# ScreenLibrary.tsx) is frontend-local and duplicated. This is the first
# backend table; a fresh Python dict, not an import of a frontend file.
_GRADE_ORDER = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F")
GRADE_RANK: dict[str, int] = {grade: rank for rank, grade in enumerate(_GRADE_ORDER)}


def _now_iso() -> str:
    """Return the current local timestamp as an ISO string (second precision)."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _decade_of(date_iso: str) -> int:
    """Return the decade (e.g. ``1960``) a ``'YYYY-MM-DD'`` date falls in."""
    return (int(date_iso[:4]) // 10) * 10


def _group_by_date(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    """Group olof event rows by date_str, preserving row order within a date."""
    by_date: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_date.setdefault(row["date_str"], []).append(row)
    return by_date


def _entry_grade_map(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Map ISO concert dates to the raw ratings of entries that resolve to them.

    Mirrors ``gap_analysis._entry_coverage_maps``' entry-side exclusion:
    entries whose ``lb_master`` status is ``'nonexistent'`` are dropped (a
    confirmed non-existent LB number proves nothing about the night);
    private/missing entries still count -- and their rating still
    contributes to the night's best grade (spec §1). Only entries with a
    clean (non-``'xx'``-partial) ``date_str`` contribute, since a night's
    grade needs an exact date, not a month.

    Args:
        conn: SQLite connection.

    Returns:
        Mapping of ``'YYYY-MM-DD'`` -> list of raw ``entries.rating`` values
        (may include ``''`` for ungraded tapes) for every counted entry on
        that date. A date present in the map with an empty/ungraded-only
        list still means "circulating, no legible grade."
    """
    rows = conn.execute(
        """
        SELECT e.date_str, e.rating
        FROM entries e
        LEFT JOIN lb_master m ON m.lb_number = e.lb_number
        WHERE e.date_str IS NOT NULL AND e.date_str != ''
          AND (m.lb_status IS NULL OR m.lb_status != 'nonexistent')
        """
    ).fetchall()
    by_date: dict[str, list[str]] = {}
    for row in rows:
        iso = entry_date_to_iso(row["date_str"])
        if iso:
            by_date.setdefault(iso, []).append(row["rating"] or "")
    return by_date


def _best_grade(ratings: list[str]) -> str | None:
    """Reduce raw rating strings to the single best (lowest-rank) grade.

    Args:
        ratings: Raw ``entries.rating`` values; may include ``''`` or other
            unrecognized strings for ungraded tapes, which are ignored.

    Returns:
        The best-ranked grade letter present, or ``None`` if none of the
        ratings are recognized (e.g. every held tape on that night/tour/
        decade is ungraded).
    """
    ranks = [GRADE_RANK[r] for r in ratings if r in GRADE_RANK]
    if not ranks:
        return None
    return _GRADE_ORDER[min(ranks)]


def get_summary(db_path: str | None = None) -> dict:
    """Decade-by-decade summary for the Timeline top-level grid.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{available, generated_at, decades}``. ``available`` is False
        (still HTTP 200 at the route level) when ``olof_events`` is absent
        or empty. Each ``decades[]`` entry carries ``decade`` (int, e.g.
        ``1960``), ``label`` (e.g. ``'1960s'``), ``night_count`` (distinct
        concert dates in that decade), ``circulating_count`` (nights with
        >=1 held tape), and ``best_grade`` (best grade held across the
        decade's circulating nights, or ``None``).
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "olof_events"):
        return {"available": False, "generated_at": _now_iso(), "decades": []}

    grade_map = _entry_grade_map(conn)
    by_date = _group_by_date(_olof_concert_events(conn))

    decade_dates: dict[int, list[str]] = {}
    for date_str in by_date:
        decade_dates.setdefault(_decade_of(date_str), []).append(date_str)

    decades = []
    for decade in sorted(decade_dates):
        dates = decade_dates[decade]
        circulating = [d for d in dates if d in grade_map]
        ratings: list[str] = []
        for date_str in circulating:
            ratings.extend(grade_map[date_str])
        decades.append(
            {
                "decade": decade,
                "label": f"{decade}s",
                "night_count": len(dates),
                "circulating_count": len(circulating),
                "best_grade": _best_grade(ratings),
            }
        )
    return {"available": True, "generated_at": _now_iso(), "decades": decades}


def get_decade_detail(decade: int, db_path: str | None = None) -> dict:
    """Tour-by-tour breakdown for one decade.

    A tour spanning a decade boundary is attributed wholly to the decade of
    its earliest show (spec §D1, rare enough not to split) -- so this scans
    every concert event regardless of decade, groups into tours, and keeps
    only the tours whose earliest night lands in *decade*.

    Args:
        decade: The decade to break down, e.g. ``1980``.
        db_path: Optional database path override.

    Returns:
        ``{available, decade, label, tours}``. Each ``tours[]`` entry
        carries ``tour_name``, ``start_date``, ``end_date``, ``night_count``
        (distinct concert dates for that tour, across all decades it spans),
        ``circulating_count`` (of those, how many have a held tape -- lets
        the frontend paint an ungraded-but-circulating tour distinctly from a
        genuine no-tape tour, same three-state rule as the decade/night
        tiers), and ``best_grade`` (or ``None``); sorted by ``start_date``.
    """
    conn = get_connection(db_path)
    label = f"{decade}s"
    if not _table_exists(conn, "olof_events"):
        return {"available": False, "decade": decade, "label": label, "tours": []}

    grade_map = _entry_grade_map(conn)
    by_date = _group_by_date(_olof_concert_events(conn))

    tour_dates: dict[str, set[str]] = {}
    for date_str, rows in by_date.items():
        for row in rows:
            tour_dates.setdefault(row["tour_name"], set()).add(date_str)

    tours = []
    for tour_name, dates in tour_dates.items():
        sorted_dates = sorted(dates)
        start_date = sorted_dates[0]
        if _decade_of(start_date) != decade:
            continue
        ratings: list[str] = []
        for date_str in sorted_dates:
            ratings.extend(grade_map.get(date_str, []))
        circulating_count = sum(1 for d in sorted_dates if d in grade_map)
        tours.append(
            {
                "tour_name": tour_name,
                "start_date": start_date,
                "end_date": sorted_dates[-1],
                "night_count": len(sorted_dates),
                "circulating_count": circulating_count,
                "best_grade": _best_grade(ratings),
            }
        )
    tours.sort(key=lambda t: t["start_date"])
    return {"available": True, "decade": decade, "label": label, "tours": tours}


def get_tour_detail(tour_name: str, decade: int, db_path: str | None = None) -> dict:
    """Night-by-night breakdown for one tour.

    Scoped by *decade* (the decade of the tour's earliest show, same
    attribution rule as :func:`get_decade_detail`) because tour names are
    not guaranteed globally unique (spec §D2) -- a *tour_name* whose
    earliest show falls in a different decade than requested is treated as
    "not this tour" and returns an empty night list, even if a
    same-named-but-different tour exists elsewhere.

    Args:
        tour_name: Exact ``olof_events.tour_name`` value to look up.
        decade: The decade of the tour's earliest show, e.g. ``1980``.
        db_path: Optional database path override.

    Returns:
        ``{available, tour_name, decade, nights}``. Each ``nights[]`` entry
        carries ``date_iso``, ``venue``, ``city``, ``best_grade``, and
        ``circulating`` -- three distinct states: a graded night has
        ``best_grade`` set and ``circulating`` True; a held-but-ungraded
        night (a non-``nonexistent`` entry resolves to the date but none of
        its ratings are recognized, e.g. blank) has ``best_grade`` ``None``
        and ``circulating`` True; a true no-tape night has both ``None``/
        False. ``circulating`` lets the frontend distinguish "no dossier"
        from "dossier exists, just ungraded" -- ``best_grade`` alone can't.
        Nights are chronological and include every night of the tour, even
        ones that fall past a decade boundary.
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "olof_events"):
        return {"available": False, "tour_name": tour_name, "decade": decade, "nights": []}

    grade_map = _entry_grade_map(conn)
    by_date = _group_by_date(_olof_concert_events(conn))

    tour_rows: dict[str, list[sqlite3.Row]] = {}
    for date_str, rows in by_date.items():
        matching = [row for row in rows if row["tour_name"] == tour_name]
        if matching:
            tour_rows[date_str] = matching

    if not tour_rows or _decade_of(min(tour_rows)) != decade:
        return {"available": True, "tour_name": tour_name, "decade": decade, "nights": []}

    nights = []
    for date_str in sorted(tour_rows):
        row = tour_rows[date_str][0]
        nights.append(
            {
                "date_iso": date_str,
                "venue": row["venue"],
                "city": row["city"],
                "best_grade": _best_grade(grade_map.get(date_str, [])),
                "circulating": date_str in grade_map,
            }
        )
    return {"available": True, "tour_name": tour_name, "decade": decade, "nights": nights}
