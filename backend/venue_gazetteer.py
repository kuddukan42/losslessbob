"""Venue-level geocoding gazetteer (TODO-223).

A venue is played many times, so geocoding each *show* separately re-solves the
same coordinate over and over and scatters manual fixes across dates. This
module builds a ``venue_geocoded`` table keyed by normalized ``(venue, city)``
so each distinct venue is solved **once** and every show/entry at that venue
inherits the pin; a manual fix on the venue then persists for all its dates.

The first slice (bite 1) only **seeds** the table: it enumerates the distinct
concert venues Dylan has played from the three structured sources and inserts
them unresolved (``source='seeded'``, ``lat``/``lon`` NULL). The second slice
(bite 2) adds the resolution ladder (bounded Nominatim search near the
setlist.fm city coord, Wikidata SPARQL for demolished venues, setlist.fm
city-coord fallback). The third slice (bite 3, see
:mod:`backend.geocoder`'s ``_venue_key_for_location``/``run_batch``/
``place_manual``) wires the resolved pins into the geocoder's per-location
cascade: a resolved venue is inherited by every show at that venue with no
further Nominatim call, and a manual per-location fix propagates back to
every other show sharing the venue.

Sources, richest first (so a conflicting key keeps the most complete fields):
  1. ``olof_events`` concerts — clean, pre-split venue/city/region/country.
  2. ``setlistfm_shows`` — ``venue_name`` / ``city`` / ``city_state`` / ``country``.
  3. ``bobdylan_shows`` — ``venue`` / ``location`` (a bare city string; no split).
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from backend.db import get_connection, init_db
from backend.geocoder import (
    _MAX_429_RETRIES,
    _RATE_LIMIT_SLEEP,
    _USER_AGENT,
    _city_viewbox,
    _RateLimitError,
    geocode_one,
)

logger = logging.getLogger(__name__)

# Politeness delay between Nominatim requests (OSM usage policy: <= 1 req/s).
_NOMINATIM_DELAY = 1.1
# Wikidata Query Service endpoint (SPARQL). Reached only as ladder step 2, when
# the bounded Nominatim search misses — so request volume stays low.
_WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_WIKIDATA_DELAY = 1.1
# A Wikidata coordinate is accepted only if it lands within this radius of the
# venue's city anchor — rejects same-name venues in the wrong city.
_WIKIDATA_MAX_KM = 50.0
# WKT point literal Wikidata returns for P625, e.g. "Point(-73.9857 40.7484)".
_WKT_POINT_RE = re.compile(r"Point\(\s*([-\d.]+)\s+([-\d.]+)\s*\)")

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


_NUMERIC_VENUE_RE = re.compile(r"^[\d\s]+$")


def _is_numeric_or_empty_venue(venue_norm: str) -> bool:
    """True if *venue_norm* is junk: empty, or nothing but digits/spaces.

    A handful of seeded rows come from scraper artifacts where a stray
    number (a day-of-month, a set number) landed in the venue field instead
    of a real venue name — these are not usable gazetteer keys and pollute
    the table. Real venue names retain at least one letter after
    normalization (e.g. ``"o2 arena"``), so a purely-numeric key is safe to
    treat as junk.

    Args:
        venue_norm: A normalized venue key, as produced by :func:`_norm_venue`.

    Returns:
        True if the key is empty or purely numeric/whitespace.
    """
    return not venue_norm or bool(_NUMERIC_VENUE_RE.fullmatch(venue_norm))


def _cleanup_numeric_junk(conn) -> int:
    """Delete existing ``venue_geocoded`` rows with a numeric/empty venue key.

    Cleans up rows seeded before :func:`seed_venues` started filtering them
    out (TODO-223 bite 3). Deletes regardless of ``source`` (seeded,
    resolved, whatever a stray earlier resolve run produced), but never a
    ``manual_override=1`` row — a manual fix, however oddly keyed, is a
    deliberate user action and is left alone.

    Args:
        conn: SQLite connection.

    Returns:
        Number of rows deleted.
    """
    rows = conn.execute(
        "SELECT venue_norm, city_norm FROM venue_geocoded WHERE manual_override = 0"
    ).fetchall()
    junk = [(r[0], r[1]) for r in rows if _is_numeric_or_empty_venue(r[0])]
    if junk:
        conn.executemany(
            "DELETE FROM venue_geocoded WHERE venue_norm = ? AND city_norm = ? "
            "AND manual_override = 0",
            junk,
        )
    if junk:
        logger.info("venue_gazetteer cleanup: deleted %d numeric/empty-venue junk row(s)",
                     len(junk))
    return len(junk)


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
    the seed safe to re-run. Rows whose venue normalizes to empty, or to
    nothing but digits/spaces (scraper artifacts — see
    :func:`_is_numeric_or_empty_venue`), are skipped as unusable keys. Also
    runs :func:`_cleanup_numeric_junk` to delete any such junk rows seeded by
    an earlier run, before this filter existed.

    Args:
        db_path: Optional DB path override (defaults to the app DB).

    Returns:
        Summary dict: ``per_source`` (candidate rows read per table),
        ``distinct_candidates`` (unique keys across all sources),
        ``inserted`` (new rows added), ``already_present`` (kept as-is),
        ``cleaned_numeric_junk`` (pre-existing numeric/empty-venue rows
        deleted), ``total_rows`` (venue_geocoded row count after seeding and
        cleanup).
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
            if _is_numeric_or_empty_venue(key[0]):
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
    after_insert = conn.execute("SELECT COUNT(*) FROM venue_geocoded").fetchone()[0]
    inserted = after_insert - before

    cleaned = _cleanup_numeric_junk(conn)
    conn.commit()
    total_rows = conn.execute("SELECT COUNT(*) FROM venue_geocoded").fetchone()[0]

    summary = {
        "per_source": per_source,
        "distinct_candidates": len(candidates),
        "inserted": inserted,
        "already_present": len(candidates) - inserted,
        "cleaned_numeric_junk": cleaned,
        "total_rows": total_rows,
    }
    logger.info("venue_gazetteer seed: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Resolution ladder (bite 2): one coordinate per seeded venue.
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers between two WGS-84 points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _geocode_retry(query: str, viewbox: str | None = None, bounded: bool = False) -> dict:
    """Call :func:`geocoder.geocode_one`, retrying a 429 with a backoff sleep.

    Mirrors ``run_batch``'s rate-limit handling but standalone (no shared
    progress/stop state — this is an operational batch, not the live run).
    A polite ``_NOMINATIM_DELAY`` sleep follows every attempt.
    """
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            result = geocode_one(query, viewbox=viewbox, bounded=bounded)
            time.sleep(_NOMINATIM_DELAY)
            return result
        except _RateLimitError:
            if attempt < _MAX_429_RETRIES:
                logger.warning("Nominatim 429 on %r; sleeping %ds (retry %d/%d)",
                               query, _RATE_LIMIT_SLEEP, attempt + 1, _MAX_429_RETRIES)
                time.sleep(_RATE_LIMIT_SLEEP)
            else:
                logger.error("Nominatim still 429 after %d retries on %r", _MAX_429_RETRIES, query)
                return {"lat": None, "lon": None, "source": "failed", "confidence": None,
                        "note": f"HTTP 429 after {_MAX_429_RETRIES} retries"}
    return {"lat": None, "lon": None, "source": "failed", "confidence": None}


def _setlistfm_city_coord(conn, city_norm: str) -> tuple[float, float] | None:
    """Return a stored setlist.fm city coordinate for *city_norm*, if any.

    setlist.fm ships ``venue.city.coords`` which :mod:`backend.setlistfm` stores
    in ``setlistfm_shows.city_lat``/``city_lon`` (TODO-222). Those are NULL until
    a force re-scrape backfills them, so this is best-effort — the ladder falls
    back to a Nominatim city geocode when it returns ``None``.
    """
    if not _table_exists(conn, "setlistfm_shows"):
        return None
    cols = {r[1] for r in conn.execute("PRAGMA table_info(setlistfm_shows)")}
    if "city_lat" not in cols:
        return None
    for row in conn.execute(
        "SELECT city, city_lat, city_lon FROM setlistfm_shows "
        "WHERE city_lat IS NOT NULL AND city_lon IS NOT NULL"
    ):
        if _norm_city(row[0]) == city_norm:
            return float(row[1]), float(row[2])
    return None


def _city_anchor(conn, row, cache: dict) -> tuple[tuple[float, float] | None, str]:
    """Return a city-level anchor coordinate for a venue row, plus its source.

    Anchors the bounded venue search and the city fallback. Prefers a stored
    setlist.fm city coordinate; when absent, geocodes the city text once via
    Nominatim. Cached by ``city_norm`` so each city costs at most one Nominatim
    call across all its venues.

    Returns:
        ``((lat, lon), anchor_source)`` where ``anchor_source`` is
        ``'setlistfm_city'`` or ``'city_geocode'``; ``(None, '')`` if the city
        cannot be anchored (empty city, or the city geocode failed).
    """
    city_norm = row["city_norm"]
    if city_norm in cache:
        return cache[city_norm]

    coord = _setlistfm_city_coord(conn, city_norm)
    if coord is not None:
        cache[city_norm] = (coord, "setlistfm_city")
        return cache[city_norm]

    city_query = ", ".join(
        p for p in (row["city"], row["region"], row["country"]) if (p or "").strip()
    ).strip()
    if not city_query:
        cache[city_norm] = (None, "")
        return cache[city_norm]

    res = _geocode_retry(city_query)
    if res.get("lat") is not None:
        cache[city_norm] = ((float(res["lat"]), float(res["lon"])), "city_geocode")
    else:
        cache[city_norm] = (None, "")
    return cache[city_norm]


def _wikidata_venue_coord(venue: str, anchor: tuple[float, float]) -> tuple[float, float] | None:
    """Look up a venue coordinate via Wikidata (P625), validated against *anchor*.

    Searches Wikidata entities by venue name (mwapi EntitySearch inside SPARQL)
    and returns the first coordinate landing within ``_WIKIDATA_MAX_KM`` of the
    anchor — covering demolished venues OSM/Nominatim lack. Best-effort: any
    network/parse error returns ``None`` so the ladder falls through.
    """
    query = (
        "SELECT ?place ?coord WHERE { "
        "SERVICE wikibase:mwapi { "
        'bd:serviceParam wikibase:api "EntitySearch" ; '
        'wikibase:endpoint "www.wikidata.org" ; '
        f'mwapi:search "{venue}" ; mwapi:language "en" . '
        "?place wikibase:apiOutputItem mwapi:item . } "
        "?place wdt:P625 ?coord . } LIMIT 10"
    )
    url = f"{_WIKIDATA_SPARQL_URL}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        logger.warning("Wikidata query failed for %r: %s", venue, exc)
        return None
    finally:
        time.sleep(_WIKIDATA_DELAY)

    for binding in data.get("results", {}).get("bindings", []):
        m = _WKT_POINT_RE.search(binding.get("coord", {}).get("value", ""))
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        if _haversine_km(lat, lon, anchor[0], anchor[1]) <= _WIKIDATA_MAX_KM:
            return lat, lon
    return None


def resolve_one(conn, row, cache: dict) -> dict:
    """Resolve one seeded venue row to a coordinate via the ladder.

    Ladder (stop at first hit): (1) bounded Nominatim venue-name search near the
    city anchor; (2) Wikidata P625 validated against the anchor; (3) the city
    anchor itself as a city-level pin. Yields ``source='failed'`` when the city
    cannot be anchored at all.

    Args:
        conn: SQLite connection.
        row: A ``venue_geocoded`` row (needs venue/city/region/country/*_norm).
        cache: Per-run city-anchor cache (see :func:`_city_anchor`).

    Returns:
        Dict with ``lat``, ``lon``, ``source``, ``confidence``, ``note``.
    """
    venue = (row["venue"] or "").strip()
    anchor, anchor_source = _city_anchor(conn, row, cache)

    if anchor is None:
        return {"lat": None, "lon": None, "source": "failed", "confidence": "none",
                "note": "no city anchor (setlist.fm coord absent, city geocode failed)"}

    # Step 1 — bounded Nominatim venue search near the anchor.
    if venue:
        res = _geocode_retry(venue, viewbox=_city_viewbox(*anchor), bounded=True)
        if res.get("lat") is not None:
            return {"lat": float(res["lat"]), "lon": float(res["lon"]),
                    "source": "bounded_venue", "confidence": res.get("confidence") or "medium",
                    "note": res.get("display_name")}

    # Step 2 — Wikidata (demolished venues OSM lacks), validated against anchor.
    if venue:
        wd = _wikidata_venue_coord(venue, anchor)
        if wd is not None:
            return {"lat": wd[0], "lon": wd[1], "source": "wikidata",
                    "confidence": "high", "note": "Wikidata P625"}

    # Step 3 — city-level fallback pin (anchor coordinate).
    return {"lat": anchor[0], "lon": anchor[1], "source": anchor_source,
            "confidence": "city", "note": f"city-level pin ({anchor_source})"}


def resolve_venues(db_path: str | None = None, limit: int | None = None,
                   retry_failed: bool = False) -> dict:
    """Run the resolution ladder over unresolved venues, updating ``venue_geocoded``.

    Processes rows with ``source='seeded'`` (and ``source='failed'`` when
    ``retry_failed``), skipping ``manual_override=1``. Updates in place; never
    touches a manual row. Network-bound (Nominatim + Wikidata) — use ``limit``
    for a smoke test.

    Args:
        db_path: Optional DB path override.
        limit: Max venues to process this run (``None`` = all).
        retry_failed: Also re-attempt rows previously marked ``source='failed'``.

    Returns:
        Summary dict with per-source resolved counts and totals.
    """
    init_db(db_path)
    conn = get_connection(db_path)

    sources = "('seeded','failed')" if retry_failed else "('seeded')"
    sql = (f"SELECT * FROM venue_geocoded WHERE source IN {sources} "
           f"AND manual_override = 0 ORDER BY venue_norm, city_norm")
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()

    cache: dict = {}
    by_source: dict[str, int] = {}
    processed = 0
    for row in rows:
        result = resolve_one(conn, row, cache)
        conn.execute(
            """UPDATE venue_geocoded
                   SET lat=?, lon=?, source=?, confidence=?, note=?,
                       geocoded_at=CURRENT_TIMESTAMP
                   WHERE venue_norm=? AND city_norm=? AND manual_override=0""",
            (result["lat"], result["lon"], result["source"], result["confidence"],
             result.get("note"), row["venue_norm"], row["city_norm"]),
        )
        by_source[result["source"]] = by_source.get(result["source"], 0) + 1
        processed += 1
        # Commit per venue: each row's UPDATE otherwise holds the SQLite write
        # lock across the NEXT venues' network waits (a 25-row batch = minutes
        # locked), starving the live backend's writes.
        conn.commit()
        if processed % 25 == 0:
            logger.info("venue resolve progress: %d/%d", processed, len(rows))
    conn.commit()

    summary = {
        "processed": processed,
        "by_source": by_source,
        "cities_anchored": sum(1 for v in cache.values() if v[0] is not None),
        "cities_seen": len(cache),
    }
    logger.info("venue_gazetteer resolve: %s", summary)
    return summary


if __name__ == "__main__":  # pragma: no cover
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
        print(resolve_venues(limit=lim))
    else:
        print(seed_venues())
