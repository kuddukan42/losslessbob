"""Nominatim geocoder for LosslessBob location data.

Provides single-location lookup, manual pin placement, and a batch runner
that reads un-geocoded entries.location values from the database and writes
results back via UPSERT.  Respects the Nominatim ToS 1-second rate limit.

Structured-source integration: before calling Nominatim, run_batch() checks
three tables, in priority order, for a structured venue/city/state/country
string that matches any entry associated with the location being geocoded:
bobdylan_shows (most standardized), then setlistfm_shows, then
dylan_performances as a last resort.  When found, that structured string is
used as the Nominatim query (better accuracy than the raw LB metadata
location) and the result is stored with source set to the matching table
name ('bobdylan_shows' / 'setlistfm_shows' / 'performances').
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _RateLimitError(Exception):
    """Raised by geocode_one() when Nominatim returns HTTP 429."""


_MAX_429_RETRIES = 3      # max retries per location after a 429
_RATE_LIMIT_SLEEP = 60    # seconds to sleep after a 429 before retrying

# ---------------------------------------------------------------------------
# Module-level thread-safe progress state
# ---------------------------------------------------------------------------

_progress: dict = {
    "running": False,
    "done": 0,
    "total": 0,
    "current": "",
    "errors": 0,
    "stage": "",       # "querying" | "saving" | "sleeping" | "rate_limited" | "done" | ""
    "succeeded": 0,
}
_lock = threading.Lock()

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "LosslessBob-Geocoder/1.0 (tjjenkin42@gmail.com)"


# ---------------------------------------------------------------------------
# Performances-table helpers
# ---------------------------------------------------------------------------

def _entry_date_to_iso(date_str: str) -> str | None:
    """Convert an entries.date_str (M/D/YY) to YYYY-MM-DD for performances lookup.

    Returns None for partial dates containing 'xx' or for unparseable strings,
    since those can never match an exact performance record.

    Args:
        date_str: LosslessBob date string, e.g. ``'7/28/00'`` or ``'5/xx/87'``.

    Returns:
        ISO date string ``'YYYY-MM-DD'``, or ``None`` if conversion fails.
    """
    if not date_str or "xx" in date_str.lower():
        return None
    parts = date_str.split("/")
    if len(parts) != 3:
        return None
    try:
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year = 1900 + year if year >= 49 else 2000 + year
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def _entries_iso_dates(location_text: str, conn) -> list[str]:
    """Return the distinct ISO dates (YYYY-MM-DD) of entries at this location.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        List of ISO date strings, one per distinct entries.date_str that
        converts cleanly. Unparseable / partial dates are skipped.
    """
    date_rows = conn.execute(
        "SELECT DISTINCT date_str FROM entries WHERE location = ? AND date_str != ''",
        (location_text,),
    ).fetchall()
    isos = []
    for row in date_rows:
        iso = _entry_date_to_iso(row["date_str"])
        if iso is not None:
            isos.append(iso)
    return isos


def _get_performance_location_string(location_text: str, conn) -> str | None:
    """Return a structured geocoding string from dylan_performances for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks dylan_performances for a match.  On the first hit,
    builds a comma-joined ``"venue, city, state, country"`` string (blank / ``"?"``
    parts dropped) and returns it.  Returns ``None`` if no performance record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        Structured geocoding string (e.g. ``"Massey Hall, Toronto, ON, Canada"``),
        or ``None`` if no matching performance exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        perf = conn.execute(
            "SELECT venue, city, state, country FROM dylan_performances WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if perf is None:
            continue
        parts = [
            p for p in (perf["venue"], perf["city"], perf["state"], perf["country"])
            if p and p.strip() and p.strip() != "?"
        ]
        if parts:
            return ", ".join(parts)

    return None


def _get_bobdylan_shows_location_string(location_text: str, conn) -> str | None:
    """Return a structured geocoding string from bobdylan_shows for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks bobdylan_shows for a match.  On the first hit,
    builds a comma-joined ``"venue, location"`` string (blank parts dropped) and
    returns it — ``bobdylan_shows.location`` is already a ``"City, ST"``-style string.
    Returns ``None`` if no show record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        Structured geocoding string (e.g. ``"The Purple Onion, St. Paul, MN"``),
        or ``None`` if no matching show exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        show = conn.execute(
            "SELECT venue, location FROM bobdylan_shows WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if show is None:
            continue
        parts = [p for p in (show["venue"], show["location"]) if p and p.strip()]
        if parts:
            return ", ".join(parts)

    return None


def _get_setlistfm_location_string(location_text: str, conn) -> str | None:
    """Return a structured geocoding string from setlistfm_shows for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks setlistfm_shows for a match.  On the first hit,
    builds a comma-joined ``"venue_name, city, country"`` string (blank parts dropped)
    and returns it.  Returns ``None`` if no setlist record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        Structured geocoding string (e.g. ``"Thalia Mara Hall, Jackson, United States"``),
        or ``None`` if no matching setlist exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        show = conn.execute(
            "SELECT venue_name, city, country FROM setlistfm_shows WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if show is None:
            continue
        parts = [
            p for p in (show["venue_name"], show["city"], show["country"])
            if p and p.strip()
        ]
        if parts:
            return ", ".join(parts)

    return None


# Structured-source lookups tried in priority order before falling back to the
# raw entries.location text. The key becomes location_geocoded.source on a hit.
# bobdylan_shows is the most standardized (curated "City, ST" location strings),
# setlistfm_shows is the backup, and dylan_performances is the last resort.
_STRUCTURED_SOURCES = (
    ("bobdylan_shows", _get_bobdylan_shows_location_string),
    ("setlistfm_shows", _get_setlistfm_location_string),
    ("performances", _get_performance_location_string),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def geocode_one(location_text: str) -> dict:
    """Perform a single Nominatim geocoding lookup.

    Args:
        location_text: Free-text location string (e.g. "Denver, Colorado").

    Returns:
        Dict with keys: location_text, lat, lon, display_name, source,
        confidence, and optionally note (on error).
        ``source`` is 'nominatim' on success, 'failed' on empty result or
        network error.  ``confidence`` is 'high' / 'medium' / 'low' based
        on the Nominatim importance score, or None when source='failed'.
    """
    encoded = urllib.parse.urlencode({"q": location_text, "format": "json", "limit": 1})
    url = f"{_NOMINATIM_URL}?{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            logger.warning("Nominatim rate-limited (429) for %r", location_text)
            raise _RateLimitError(location_text) from exc
        logger.warning("Nominatim HTTP %d for %r: %s", exc.code, location_text, exc)
        return {
            "location_text": location_text,
            "lat": None,
            "lon": None,
            "display_name": None,
            "source": "failed",
            "confidence": None,
            "note": str(exc),
        }
    except Exception as exc:
        logger.warning("Nominatim request failed for %r: %s", location_text, exc)
        return {
            "location_text": location_text,
            "lat": None,
            "lon": None,
            "display_name": None,
            "source": "failed",
            "confidence": None,
            "note": str(exc),
        }

    if not data:
        logger.debug("Nominatim returned no results for %r", location_text)
        return {
            "location_text": location_text,
            "lat": None,
            "lon": None,
            "display_name": None,
            "source": "failed",
            "confidence": None,
        }

    result = data[0]
    lat = float(result.get("lat", 0))
    lon = float(result.get("lon", 0))
    display_name = result.get("display_name", "")
    importance = float(result.get("importance", 0))

    if importance >= 0.5:
        confidence = "high"
    elif importance >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    logger.debug(
        "Geocoded %r → (%.4f, %.4f) importance=%.3f confidence=%s",
        location_text, lat, lon, importance, confidence,
    )
    return {
        "location_text": location_text,
        "lat": lat,
        "lon": lon,
        "display_name": display_name,
        "source": "nominatim",
        "confidence": confidence,
    }


def place_manual(
    location_text: str,
    lat: float,
    lon: float,
    note: str = "",
    lb_number: str | None = None,
) -> None:
    """Insert or replace a geocoding result with a user-supplied coordinate.

    Manual entries are never overwritten by batch geocoding because
    ``manual_override=1`` is set.

    Args:
        location_text: The location string that matches entries.location.
        lat: WGS-84 latitude.
        lon: WGS-84 longitude.
        note: Optional freeform note (e.g. reason for the override).
        lb_number: Optional LB number that prompted this override, for traceability.
    """
    from backend.db_queue import get_write_queue

    _loc, _lat, _lon, _note, _lb = location_text, lat, lon, note, lb_number
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT INTO location_geocoded
                   (location_text, lat, lon, source, confidence, manual_override, note,
                    lb_number, geocoded_at)
               VALUES (?, ?, ?, 'manual', 'high', 1, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(location_text) DO UPDATE SET
                   lat=excluded.lat,
                   lon=excluded.lon,
                   source='manual',
                   confidence='high',
                   manual_override=1,
                   note=excluded.note,
                   lb_number=COALESCE(excluded.lb_number, location_geocoded.lb_number),
                   geocoded_at=CURRENT_TIMESTAMP""",
            (_loc, _lat, _lon, _note, _lb),
        )
    )
    logger.info("Manual geocode saved: %r → (%.4f, %.4f)", location_text, lat, lon)


def run_batch(
    limit: int | None = None,
    retry_failed: bool = False,
    dry_run: bool = False,
    db_path=None,
) -> None:
    """Batch-geocode un-geocoded entries.location values via Nominatim.

    Reads distinct location strings from ``entries`` that have no row in
    ``location_geocoded`` (or whose ``source='failed'`` when ``retry_failed``
    is True).  Rows with ``manual_override=1`` are always skipped.

    For each location, three structured sources are checked in priority order:
    bobdylan_shows (most standardized), then setlistfm_shows, then
    dylan_performances as a last resort. If any entry with that location has
    a matching record (by ISO date) in one of these tables, the structured
    venue/city/state/country string is used as the Nominatim query and the
    result is stored with ``source`` set to the matching table name.
    Otherwise the raw ``entries.location`` text is geocoded as before.

    Sleeps 1.1 seconds between each Nominatim request to comply with the
    Nominatim Usage Policy (max 1 request/second).

    Args:
        limit: Maximum number of locations to process in this run.
               None means process all eligible locations.
        retry_failed: When True, also re-attempt locations whose previous
                      geocoding attempt produced source='failed'.
        dry_run: When True, perform the lookup but do not write to the DB.
                 Useful for testing / previewing results.
        db_path: Optional path to the SQLite database. Defaults to DB_PATH.
    """
    from backend.db import get_connection
    from backend.db_queue import get_write_queue

    conn = get_connection(db_path)

    if retry_failed:
        sql = """
            SELECT DISTINCT e.location
            FROM entries e
            LEFT JOIN location_geocoded geo
                ON e.location = geo.location_text
            WHERE e.location IS NOT NULL
              AND e.location != ''
              AND (geo.location_text IS NULL
                   OR (geo.source = 'failed' AND geo.manual_override = 0))
            ORDER BY e.location
        """
    else:
        sql = """
            SELECT DISTINCT e.location
            FROM entries e
            LEFT JOIN location_geocoded geo
                ON e.location = geo.location_text
            WHERE e.location IS NOT NULL
              AND e.location != ''
              AND geo.location_text IS NULL
            ORDER BY e.location
        """

    rows = conn.execute(sql).fetchall()
    locations = [r[0] for r in rows]

    if limit is not None:
        locations = locations[:limit]

    total = len(locations)
    logger.info(
        "Batch geocode starting: %d location(s) to process (retry_failed=%s, dry_run=%s)",
        total, retry_failed, dry_run,
    )

    with _lock:
        _progress["running"] = True
        _progress["done"] = 0
        _progress["total"] = total
        _progress["current"] = ""
        _progress["errors"] = 0
        _progress["succeeded"] = 0
        _progress["stage"] = "starting"

    try:
        for i, location_text in enumerate(locations):
            with _lock:
                _progress["current"] = location_text
                _progress["stage"] = "querying"

            # Check structured sources in priority order (dylan_performances,
            # bobdylan_shows, setlistfm_shows) for a matching venue/city string.
            # If one is found, geocode that structured string rather than the
            # raw LB metadata text.
            structured_query = None
            matched_source = None
            for source_name, lookup_fn in _STRUCTURED_SOURCES:
                structured_query = lookup_fn(location_text, conn)
                if structured_query:
                    matched_source = source_name
                    break

            if structured_query:
                geocode_input = structured_query
                logger.debug(
                    "%s hit for %r → geocoding %r", matched_source, location_text, structured_query
                )
            else:
                geocode_input = location_text

            for attempt in range(_MAX_429_RETRIES + 1):
                try:
                    result = geocode_one(geocode_input)
                    break
                except _RateLimitError:
                    if attempt < _MAX_429_RETRIES:
                        logger.warning(
                            "Rate-limited on %r; sleeping %ds (retry %d/%d)",
                            geocode_input, _RATE_LIMIT_SLEEP,
                            attempt + 1, _MAX_429_RETRIES,
                        )
                        with _lock:
                            _progress["stage"] = "rate_limited"
                        time.sleep(_RATE_LIMIT_SLEEP)
                        with _lock:
                            _progress["stage"] = "querying"
                    else:
                        logger.error(
                            "Still rate-limited after %d retries on %r; marking failed",
                            _MAX_429_RETRIES, geocode_input,
                        )
                        result = {
                            "location_text": geocode_input,
                            "lat": None,
                            "lon": None,
                            "display_name": None,
                            "source": "failed",
                            "confidence": None,
                            "note": f"HTTP 429: rate-limited after {_MAX_429_RETRIES} retries",
                        }

            # When a structured source supplied the query, override the source flag
            # and record the structured query in note for provenance.
            # Also promote 'low' confidence to 'medium': Nominatim importance scores
            # penalise specific venues even when the structured query is accurate.
            if structured_query and result.get("source") == "nominatim":
                result["source"] = matched_source
                result["note"] = f"{matched_source}: {structured_query}"
                if result.get("confidence") == "low":
                    result["confidence"] = "medium"

            with _lock:
                _progress["stage"] = "saving"

            if not dry_run:
                # Always key by the raw entries.location so the map JOIN still works.
                _loc = location_text
                _r = result
                get_write_queue().execute(
                    lambda c, _loc=_loc, _r=_r: c.execute(
                        """INSERT INTO location_geocoded
                               (location_text, lat, lon, source, confidence, display_name,
                                manual_override, note, geocoded_at)
                           VALUES (?, ?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(location_text) DO UPDATE SET
                               lat=excluded.lat,
                               lon=excluded.lon,
                               source=excluded.source,
                               confidence=excluded.confidence,
                               display_name=excluded.display_name,
                               note=excluded.note,
                               geocoded_at=CURRENT_TIMESTAMP
                           WHERE manual_override = 0""",
                        (
                            _loc,
                            _r.get("lat"),
                            _r.get("lon"),
                            _r["source"],
                            _r.get("confidence"),
                            _r.get("display_name"),
                            _r.get("note"),
                        ),
                    )
                )

            with _lock:
                _progress["done"] = i + 1
                if result["source"] == "failed":
                    _progress["errors"] += 1
                else:
                    _progress["succeeded"] += 1

            if (i + 1) % 10 == 0:
                logger.info(
                    "Geocoding progress: %d/%d done, %d errors",
                    i + 1, total, _progress["errors"],
                )

            # Nominatim ToS: maximum 1 request per second
            if i < total - 1:
                with _lock:
                    _progress["stage"] = "sleeping"
                time.sleep(1.1)

    finally:
        with _lock:
            _progress["running"] = False
            _progress["current"] = ""
            _progress["stage"] = "done"

    logger.info(
        "Batch geocode complete: %d/%d processed, %d errors, dry_run=%s",
        _progress["done"], total, _progress["errors"], dry_run,
    )


def get_progress() -> dict:
    """Return a snapshot of the current batch geocoding progress state.

    Returns:
        Dict with keys: running (bool), done (int), total (int),
        current (str), errors (int).
    """
    with _lock:
        return dict(_progress)
