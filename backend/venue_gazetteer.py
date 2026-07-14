"""Venue-level geocoding gazetteer (TODO-223).

A venue is played many times, so geocoding each *show* separately re-solves the
same coordinate over and over and scatters manual fixes across dates. This
module builds a ``venue_geocoded`` table keyed by normalized ``(venue, city)``
so each distinct venue is solved **once** and every show/entry at that venue
inherits the pin; a manual fix on the venue then persists for all its dates.

This first slice only **seeds** the table: it enumerates the distinct concert
venues Dylan has played from the three structured sources and inserts them
unresolved (``source='seeded'``, ``lat``/``lon`` NULL). A later slice adds the
resolution ladder (bounded Nominatim search near the setlist.fm city coord,
Wikidata SPARQL for demolished venues, setlist.fm city-coord fallback) and wires
the resolved pins into the geocoder's per-location cascade.

Sources, richest first (so a conflicting key keeps the most complete fields):
  1. ``olof_events`` concerts — clean, pre-split venue/city/region/country.
  2. ``setlistfm_shows`` — ``venue_name`` / ``city`` / ``city_state`` / ``country``.
  3. ``bobdylan_shows`` — ``venue`` / ``location`` (a bare city string; no split).
"""
from __future__ import annotations

import logging
import re

from backend.db import get_connection, init_db

logger = logging.getLogger(__name__)

# Conservative normalization: casefold, drop punctuation (unicode letters and
# digits survive, so accented international venue names are preserved), collapse
# whitespace. Deliberately does NOT canonicalize spelling variants
# ("Theater"/"Theatre") — over-merging distinct venues is worse than a few
# duplicate keys the ladder/manual pass can reconcile.
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _normalize(text: str | None) -> str:
    """Return the gazetteer key form of a venue or city string.

    Args:
        text: Raw venue or city text (may be ``None`` or empty).

    Returns:
        Casefolded, punctuation-stripped, whitespace-collapsed key (``''`` when
        the input is empty or all punctuation).
    """
    if not text:
        return ""
    folded = text.casefold().strip()
    folded = _NON_WORD_RE.sub(" ", folded)
    return _WS_RE.sub(" ", folded).strip()


def _norm_venue(venue: str | None) -> str:
    """Normalize a venue name into its gazetteer key (see :func:`_normalize`)."""
    return _normalize(venue)


def _norm_city(city: str | None) -> str:
    """Normalize a city string into its gazetteer key.

    Takes only the first comma-segment before normalizing, so the same city
    keys identically regardless of an embedded state/country that varies by
    source (``bobdylan_shows.location`` is comma-soup ``"Birmingham, Alabama"``
    while olof/setlist.fm carry a bare ``"Birmingham"``). Without this the same
    venue fragments into a row per city-string variant, defeating the
    solve-each-venue-once goal.
    """
    if not city:
        return ""
    return _normalize(city.split(",", 1)[0])


def _table_exists(conn, table_name: str) -> bool:
    """True if *table_name* exists (feature-detect optional source tables)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


# (table, SQL) pairs, richest source first. Each SELECT yields
# (venue, city, region, country) with blanks where a source lacks the field.
_SEED_SOURCES: tuple[tuple[str, str], ...] = (
    (
        "olof_events",
        """SELECT venue, city, region, country FROM olof_events
           WHERE event_type = 'concert' AND TRIM(COALESCE(venue, '')) <> ''""",
    ),
    (
        "setlistfm_shows",
        """SELECT venue_name, city, city_state, country FROM setlistfm_shows
           WHERE TRIM(COALESCE(venue_name, '')) <> ''""",
    ),
    (
        "bobdylan_shows",
        """SELECT venue, location, '', '' FROM bobdylan_shows
           WHERE TRIM(COALESCE(venue, '')) <> ''""",
    ),
)


def seed_venues(db_path: str | None = None) -> dict:
    """Seed ``venue_geocoded`` with distinct concert venues, unresolved.

    Enumerates ``(venue, city, region, country)`` from each structured source
    (richest first), normalizes to a ``(venue_norm, city_norm)`` key, and
    inserts one placeholder row per distinct key with ``source='seeded'`` and
    NULL coordinates. Uses ``ON CONFLICT DO NOTHING`` so already-present rows —
    resolved pins or ``manual_override=1`` fixes — are never disturbed, making
    the seed safe to re-run. Rows whose venue normalizes to empty are skipped
    (no usable key).

    Args:
        db_path: Optional DB path override (defaults to the app DB).

    Returns:
        Summary dict: ``per_source`` (candidate rows read per table),
        ``distinct_candidates`` (unique keys across all sources),
        ``inserted`` (new rows added), ``already_present`` (kept as-is),
        ``total_rows`` (venue_geocoded row count after seeding).
    """
    init_db(db_path)
    conn = get_connection(db_path)

    # Dedup keeping the first (richest-source) occurrence of each key.
    candidates: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    per_source: dict[str, int] = {}
    for table, sql in _SEED_SOURCES:
        if not _table_exists(conn, table):
            per_source[table] = 0
            continue
        rows = conn.execute(sql).fetchall()
        per_source[table] = len(rows)
        for venue, city, region, country in rows:
            key = (_norm_venue(venue), _norm_city(city))
            if not key[0]:
                continue
            candidates.setdefault(
                key,
                (
                    (venue or "").strip(),
                    (city or "").strip(),
                    (region or "").strip(),
                    (country or "").strip(),
                ),
            )

    before = conn.execute("SELECT COUNT(*) FROM venue_geocoded").fetchone()[0]
    conn.executemany(
        """INSERT INTO venue_geocoded
               (venue_norm, city_norm, venue, city, region, country,
                source, confidence, manual_override)
           VALUES (?, ?, ?, ?, ?, ?, 'seeded', NULL, 0)
           ON CONFLICT(venue_norm, city_norm) DO NOTHING""",
        [
            (vn, cn, venue, city, region, country)
            for (vn, cn), (venue, city, region, country) in candidates.items()
        ],
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM venue_geocoded").fetchone()[0]

    summary = {
        "per_source": per_source,
        "distinct_candidates": len(candidates),
        "inserted": after - before,
        "already_present": len(candidates) - (after - before),
        "total_rows": after,
    }
    logger.info("venue_gazetteer seed: %s", summary)
    return summary


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(seed_venues())
