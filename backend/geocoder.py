"""Nominatim geocoder for LosslessBob location data.

Provides single-location lookup, manual pin placement, and a batch runner
that reads un-geocoded entries.location values from the database and writes
results back via UPSERT.  Respects the Nominatim ToS 1-second rate limit.

Concert-only eligibility (TODO-221, made authoritative by olof_events in
TODO-224): geocoding exists to answer "where did Bob play this show", not to
plot studio bootlegs, interviews, or multi-date compilation reissues.  When a
location's date matches an olof_events row, that row's event_type decides
outright (event_type='concert' is eligible; anything else is skipped with
the event_type recorded in note).  When no olof_events row matches, run_batch()
falls back to the original heuristic: eligible only when the location does
not match an obvious non-venue keyword AND at least one entry sharing that
location has a single clean, parseable date matching a row in bobdylan_shows
or setlistfm_shows.  Everything ineligible is written with
source='skipped_not_concert' (lat/lon NULL) so it is cached and never
retried, and is excluded from the errors stat.

Structured-source cascade (TODO-220, +olof_events TODO-224): before calling
Nominatim, run_batch() checks four tables, in priority order, for a
structured venue/city/state/country string that matches any entry
associated with the location being geocoded: bobdylan_shows (most
standardized), then olof_events (clean separate venue/city/region/country
fields, 1956-2021), then setlistfm_shows, then dylan_performances as a last
resort.  Every structured hit's full string is tried first (in priority
order); on an all-miss, a venue-stripped city/state/country-only variant of
each is tried next (source suffixed '-city', confidence capped at medium);
the raw entries.location text is tried last.  Every attempted query is
recorded in ``note`` on both success and failure, and the 1.1s Nominatim
rate-limit sleep applies between every attempt, including fallbacks.

Stop support (TODO-219): stop() sets a module-level flag (guarded by
_lock) that run_batch() checks at the top of every location and inside the
rate-limited 429 backoff sleep (sliced so a stop request is honored
promptly); get_progress() exposes stop_requested for the GUI.
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


class _StopSignal(Exception):
    """Internal control-flow signal: a stop was requested mid-sleep."""


_MAX_429_RETRIES = 3      # max retries per location after a 429
_RATE_LIMIT_SLEEP = 60    # seconds to sleep after a 429 before retrying
_STOP_CHECK_SLICE = 1.0   # seconds; granularity for the interruptible 429 sleep

# Non-venue keywords: locations whose text matches one of these are never
# concerts (studio bootlegs, interview/TV appearances, multi-date reissue
# compilations) and are skipped outright, regardless of date match (TODO-221).
_NON_VENUE_KEYWORDS = (
    "compilation", "outtakes", "interview", "rehearsal",
    "soundcheck", "demos", "various",
)

# Confidence rank used to cap city-only fallback results at 'medium' (TODO-220).
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

# ---------------------------------------------------------------------------
# Module-level thread-safe progress state
# ---------------------------------------------------------------------------

_progress: dict = {
    "running": False,
    "done": 0,
    "total": 0,
    "current": "",
    "errors": 0,
    "skipped": 0,
    "stage": "",       # "querying" | "saving" | "sleeping" | "rate_limited" | "done" | ""
    "succeeded": 0,
    "stop_requested": False,
}
_lock = threading.Lock()

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "LosslessBob-Geocoder/1.0 (tjjenkin42@gmail.com)"


def stop() -> None:
    """Signal the active batch geocode run to stop as soon as possible.

    Sets the module-level stop flag; run_batch() checks it at the top of
    every location-loop iteration and inside the 429 rate-limit backoff
    sleep, then breaks cleanly (its ``finally`` block resets progress).
    """
    with _lock:
        _progress["stop_requested"] = True
    logger.info("Geocode batch stop requested")


def _rate_limit_sleep() -> None:
    """Sleep ``_RATE_LIMIT_SLEEP`` seconds in small slices, honoring a stop.

    Raises:
        _StopSignal: if a stop is requested while sleeping.
    """
    remaining = _RATE_LIMIT_SLEEP
    while remaining > 0:
        with _lock:
            if _progress.get("stop_requested"):
                raise _StopSignal()
        chunk = min(_STOP_CHECK_SLICE, remaining)
        time.sleep(chunk)
        remaining -= chunk
    with _lock:
        if _progress.get("stop_requested"):
            raise _StopSignal()


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


def _table_exists(conn, table_name: str) -> bool:
    """Return True if *table_name* exists in the connected SQLite database.

    Used to feature-detect optional tables (``olof_events``, TODO-224) that
    may be absent on installs whose database predates the table's migration,
    so callers can degrade to prior behavior instead of raising
    ``sqlite3.OperationalError``.

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


def _get_performance_location_string(location_text: str, conn) -> tuple[str, str | None] | None:
    """Return structured geocoding strings from dylan_performances for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks dylan_performances for a match.  On the first hit,
    builds a comma-joined ``"venue, city, state, country"`` full string (blank / ``"?"``
    parts dropped) plus a venue-stripped ``"city, state, country"`` variant for the
    TODO-220 fallback cascade.  Returns ``None`` if no performance record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        ``(full, city_only)`` tuple, e.g. ``("Massey Hall, Toronto, ON, Canada",
        "Toronto, ON, Canada")`` — ``city_only`` is ``None`` if venue is the only
        non-blank part.  ``None`` if no matching performance exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        perf = conn.execute(
            "SELECT venue, city, state, country FROM dylan_performances WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if perf is None:
            continue
        venue = (perf["venue"] or "").strip()
        if venue == "?":
            venue = ""
        city_parts = [
            p.strip() for p in (perf["city"], perf["state"], perf["country"])
            if p and p.strip() and p.strip() != "?"
        ]
        full_parts = ([venue] if venue else []) + city_parts
        if full_parts:
            full = ", ".join(full_parts)
            city_only = ", ".join(city_parts) if city_parts else None
            return full, city_only

    return None


def _get_bobdylan_shows_location_string(
    location_text: str, conn
) -> tuple[str, str | None] | None:
    """Return structured geocoding strings from bobdylan_shows for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks bobdylan_shows for a match.  On the first hit,
    builds a comma-joined ``"venue, location"`` full string (blank parts dropped) —
    ``bobdylan_shows.location`` is already a ``"City, ST"``-style string — plus a
    venue-stripped city-only variant (the ``location`` column alone) for the
    TODO-220 fallback cascade.  Returns ``None`` if no show record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        ``(full, city_only)`` tuple, e.g. ``("The Purple Onion, St. Paul, MN",
        "St. Paul, MN")``.  ``city_only`` is ``None`` if ``location`` is blank.
        ``None`` if no matching show exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        show = conn.execute(
            "SELECT venue, location FROM bobdylan_shows WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if show is None:
            continue
        venue = (show["venue"] or "").strip()
        loc = (show["location"] or "").strip()
        parts = [p for p in (venue, loc) if p]
        if parts:
            full = ", ".join(parts)
            city_only = loc or None
            return full, city_only

    return None


def _get_olof_events_location_string(
    location_text: str, conn
) -> tuple[str, str | None] | None:
    """Return structured geocoding strings from olof_events for this location.

    Scans all distinct date_str values in entries that share this location,
    converts each to ISO format, and checks ``olof_events`` for a matching
    row (preferring an ``event_type='concert'`` row when a date has more
    than one event, mirroring the tie-break in
    :func:`backend.db.compare_olof_setlist`). On the first hit, builds a
    comma-joined ``"venue, city, region, country"`` full string (blank parts
    dropped) plus a venue-stripped ``"city, region, country"`` variant for
    the TODO-220 fallback cascade. Feature-detects the ``olof_events`` table
    (TODO-224) so installs whose database predates it fall through cleanly.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        ``(full, city_only)`` tuple, e.g. ``("Massey Hall, Toronto, ON,
        Canada", "Toronto, ON, Canada")``. ``city_only`` is ``None`` if venue
        is the only non-blank part. ``None`` if ``olof_events`` doesn't
        exist or no matching event exists.
    """
    if not _table_exists(conn, "olof_events"):
        return None

    for iso in _entries_iso_dates(location_text, conn):
        event = conn.execute(
            """SELECT venue, city, region, country FROM olof_events
               WHERE date_str = ?
               ORDER BY (event_type != 'concert'), event_id LIMIT 1""",
            (iso,),
        ).fetchone()
        if event is None:
            continue
        venue = (event["venue"] or "").strip()
        city_parts = [
            p.strip() for p in (event["city"], event["region"], event["country"])
            if p and p.strip()
        ]
        full_parts = ([venue] if venue else []) + city_parts
        if full_parts:
            full = ", ".join(full_parts)
            city_only = ", ".join(city_parts) if city_parts else None
            return full, city_only

    return None


def _get_setlistfm_location_string(
    location_text: str, conn
) -> tuple[str, str | None] | None:
    """Return structured geocoding strings from setlistfm_shows for this location.

    Scans all distinct date_str values in entries that share this location, converts
    each to ISO format, and checks setlistfm_shows for a match.  On the first hit,
    builds a comma-joined ``"venue_name, city, country"`` full string (blank parts
    dropped) plus a venue-stripped ``"city, country"`` variant for the TODO-220
    fallback cascade.  Returns ``None`` if no setlist record matches.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        ``(full, city_only)`` tuple, e.g. ``("Thalia Mara Hall, Jackson, United
        States", "Jackson, United States")``.  ``city_only`` is ``None`` if city
        and country are both blank.  ``None`` if no matching setlist exists.
    """
    for iso in _entries_iso_dates(location_text, conn):
        show = conn.execute(
            "SELECT venue_name, city, country FROM setlistfm_shows WHERE date_str = ?",
            (iso,),
        ).fetchone()
        if show is None:
            continue
        venue_name = (show["venue_name"] or "").strip()
        city_parts = [
            p.strip() for p in (show["city"], show["country"]) if p and p.strip()
        ]
        full_parts = ([venue_name] if venue_name else []) + city_parts
        if full_parts:
            full = ", ".join(full_parts)
            city_only = ", ".join(city_parts) if city_parts else None
            return full, city_only

    return None


# Structured-source lookups tried in priority order before falling back to the
# raw entries.location text. The key becomes location_geocoded.source on a hit.
# bobdylan_shows is the most standardized (curated "City, ST" location strings),
# olof_events is next (clean separate venue/city/region/country fields, TODO-224),
# setlistfm_shows is the backup, and dylan_performances is the last resort.
# Each lookup function returns (full_query, city_only_query | None) on a hit,
# or None on a miss — see TODO-220 cascading fallback in run_batch().
_STRUCTURED_SOURCES = (
    ("bobdylan_shows", _get_bobdylan_shows_location_string),
    ("olof_events", _get_olof_events_location_string),
    ("setlistfm_shows", _get_setlistfm_location_string),
    ("performances", _get_performance_location_string),
)


def _is_concert_location(location_text: str, conn) -> tuple[bool, str | None]:
    """Return whether *location_text* represents a documented, dated concert.

    Applies the TODO-221 "concert-only" eligibility test, made authoritative
    for olof_events-matched dates by TODO-224: geocoding exists to answer
    "where did Bob play this show", not to plot studio bootlegs, interviews,
    rehearsals, or multi-date compilation reissues.

    Priority:

    1. If the ``olof_events`` table exists (feature-detected — some installs
       may predate it, TODO-224) and at least one entry sharing this location
       has a date matching an ``olof_events`` row (preferring an
       ``event_type='concert'`` row when a date has more than one), that
       row's ``event_type`` is authoritative: ``'concert'`` is eligible;
       any other event_type (session/rehearsal/broadcast/interview/other)
       is not, and the event_type is returned as the skip note.
    2. Otherwise (no olof_events table, or no olof_events row matches any
       of this location's dates), fall back to the original TODO-221
       heuristic, unchanged: the location must not match an obvious
       non-venue keyword (see ``_NON_VENUE_KEYWORDS``), and at least one
       entry sharing this location must have a single clean, parseable date
       (no 'xx', no ranges — enforced by ``_entry_date_to_iso``) that
       matches a row in ``bobdylan_shows`` or ``setlistfm_shows``.
       ``dylan_performances`` alone does NOT count: it also carries
       non-concert dates (TV/radio interviews etc.) that would otherwise
       geocode to a venue that was never actually played.

    Args:
        location_text: Raw location string from ``entries.location``.
        conn: SQLite connection (read-only usage).

    Returns:
        ``(eligible, skip_note)``. ``eligible`` is True if this location
        should be geocoded via Nominatim; False if it should instead be
        written with ``source='skipped_not_concert'``. ``skip_note`` is a
        specific reason to store in ``location_geocoded.note`` when an
        olof_events non-concert row forced the skip (e.g.
        ``"olof_events: non-concert event_type=interview"``); ``None`` when
        eligible, or when the generic TODO-221 heuristic note should be used
        instead.
    """
    if _table_exists(conn, "olof_events"):
        for iso in _entries_iso_dates(location_text, conn):
            event = conn.execute(
                """SELECT event_type FROM olof_events WHERE date_str = ?
                   ORDER BY (event_type != 'concert'), event_id LIMIT 1""",
                (iso,),
            ).fetchone()
            if event is not None:
                event_type = (event["event_type"] or "").strip()
                if event_type == "concert":
                    return True, None
                return (
                    False,
                    f"olof_events: non-concert event_type={event_type or 'unknown'}",
                )

    lowered = location_text.lower()
    if any(keyword in lowered for keyword in _NON_VENUE_KEYWORDS):
        return False, None

    for iso in _entries_iso_dates(location_text, conn):
        hit = conn.execute(
            "SELECT 1 FROM bobdylan_shows WHERE date_str = ? LIMIT 1", (iso,)
        ).fetchone()
        if hit is None:
            hit = conn.execute(
                "SELECT 1 FROM setlistfm_shows WHERE date_str = ? LIMIT 1", (iso,)
            ).fetchone()
        if hit is not None:
            return True, None

    return False, None


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


def _save_geocode_result(write_queue, location_text: str, result: dict) -> None:
    """UPSERT one batch-geocode result into ``location_geocoded``.

    Always keys by the raw ``entries.location`` text so the map JOIN and the
    "already geocoded" candidate-selection query in ``run_batch()`` still
    work, regardless of which query string actually succeeded. Never
    overwrites a manually-placed row (``manual_override=1``).

    Args:
        write_queue: The shared DB write queue (``get_write_queue()``).
        location_text: Raw ``entries.location`` string to key the row by.
        result: A geocode result dict as returned by ``geocode_one()`` (or
                the synthetic ``skipped_not_concert`` / rate-limit-failed dicts
                built in ``run_batch()``).
    """
    _loc = location_text
    _r = result
    write_queue.execute(
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

    Each candidate location is first checked for TODO-221 concert-only
    eligibility (see ``_is_concert_location``), made authoritative by an
    olof_events date match (TODO-224): when the location's date matches an
    olof_events row, that row's event_type decides outright (non-concert
    types are skipped with the event_type recorded in note). Otherwise,
    locations that are not tied to a documented, single-dated show in
    bobdylan_shows or setlistfm_shows (or that match an obvious non-venue
    keyword) are written with ``source='skipped_not_concert'`` and never
    sent to Nominatim.

    For eligible locations, a TODO-220 cascading fallback is used: every
    structured source (bobdylan_shows, then olof_events, then
    setlistfm_shows, then dylan_performances) that has a matching record
    contributes its full
    venue/city/state/country query string, tried in priority order; if all
    of those miss, each source's venue-stripped city-only variant is tried
    next (source suffixed ``-city``, confidence capped at ``medium``); the
    raw ``entries.location`` text is tried last. The result is stored with
    ``source`` set to whichever query actually succeeded (or 'failed' if
    every attempt missed), and ``note`` records every query attempted, on
    both success and failure.

    Sleeps 1.1 seconds between every Nominatim request — including fallback
    attempts — to comply with the Nominatim Usage Policy (max 1 req/second).

    A stop request (see ``stop()``) is checked at the top of every location
    and inside the 429 rate-limit backoff sleep, and breaks the batch
    cleanly without losing already-written results.

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
        _progress["skipped"] = 0
        _progress["succeeded"] = 0
        _progress["stage"] = "starting"
        _progress["stop_requested"] = False

    try:
        for i, location_text in enumerate(locations):
            with _lock:
                if _progress.get("stop_requested"):
                    break
                _progress["current"] = location_text
                _progress["stage"] = "querying"

            # TODO-221: concert-only eligibility filter, made authoritative by
            # an olof_events date match (TODO-224). Locations that are not
            # tied to a documented, single-dated concert never reach Nominatim.
            eligible, skip_note = _is_concert_location(location_text, conn)
            if not eligible:
                result = {
                    "location_text": location_text,
                    "lat": None,
                    "lon": None,
                    "display_name": None,
                    "source": "skipped_not_concert",
                    "confidence": None,
                    "note": skip_note or (
                        "no single clean date matching bobdylan_shows/setlistfm_shows, "
                        "or non-venue keyword"
                    ),
                }
                with _lock:
                    _progress["stage"] = "saving"
                if not dry_run:
                    _save_geocode_result(get_write_queue(), location_text, result)
                with _lock:
                    _progress["done"] = i + 1
                    _progress["skipped"] += 1
                if (i + 1) % 10 == 0:
                    logger.info(
                        "Geocoding progress: %d/%d done, %d errors, %d skipped",
                        i + 1, total, _progress["errors"], _progress["skipped"],
                    )
                continue

            # TODO-220: gather every structured-source hit (not just the first),
            # each as (source_name, full_query, city_only_query | None).
            structured_hits = []
            for source_name, lookup_fn in _STRUCTURED_SOURCES:
                hit = lookup_fn(location_text, conn)
                if hit:
                    structured_hits.append((source_name, hit[0], hit[1]))

            # Cascade order: every structured source's full string first (in
            # priority order), then each source's venue-stripped city-only
            # variant, then the raw entries.location text last. Skip a query
            # string that duplicates one already queued.
            candidate_queries: list[tuple[str, str | None]] = (
                [(name, full_q) for name, full_q, _ in structured_hits]
                + [(f"{name}-city", city_q) for name, _, city_q in structured_hits]
                + [("entries.location", location_text)]
            )
            attempts: list[tuple[str, str]] = []
            seen_queries: set[str] = set()
            for tag, query in candidate_queries:
                if query and query not in seen_queries:
                    attempts.append((tag, query))
                    seen_queries.add(query)

            tried_log: list[str] = []
            matched_tag: str | None = None
            result: dict = {}
            for query_tag, query in attempts:
                for attempt in range(_MAX_429_RETRIES + 1):
                    try:
                        result = geocode_one(query)
                        break
                    except _RateLimitError:
                        if attempt < _MAX_429_RETRIES:
                            logger.warning(
                                "Rate-limited on %r; sleeping %ds (retry %d/%d)",
                                query, _RATE_LIMIT_SLEEP,
                                attempt + 1, _MAX_429_RETRIES,
                            )
                            with _lock:
                                _progress["stage"] = "rate_limited"
                            _rate_limit_sleep()
                            with _lock:
                                _progress["stage"] = "querying"
                        else:
                            logger.error(
                                "Still rate-limited after %d retries on %r; marking failed",
                                _MAX_429_RETRIES, query,
                            )
                            result = {
                                "location_text": query,
                                "lat": None,
                                "lon": None,
                                "display_name": None,
                                "source": "failed",
                                "confidence": None,
                                "note": f"HTTP 429: rate-limited after {_MAX_429_RETRIES} retries",
                            }

                tried_log.append(f"{query_tag}:{query}")

                is_last_attempt_of_run = (i == total - 1) and (
                    (query_tag, query) == attempts[-1]
                )
                if not is_last_attempt_of_run:
                    with _lock:
                        _progress["stage"] = "sleeping"
                    time.sleep(1.1)
                    with _lock:
                        _progress["stage"] = "querying"

                if result.get("source") == "nominatim":
                    matched_tag = query_tag
                    break
                logger.debug("Cascade miss for %r on %s:%r", location_text, query_tag, query)

            # Apply source/confidence overrides based on which attempt succeeded.
            # A plain 'entries.location' hit needs no override (source stays
            # 'nominatim', as when there was no structured match at all).
            if result.get("source") == "nominatim" and matched_tag not in (
                None, "entries.location",
            ):
                result["source"] = matched_tag
                if matched_tag.endswith("-city"):
                    # Venue-stripped variant: cap confidence at medium.
                    if _CONFIDENCE_RANK.get(result.get("confidence"), 0) > (
                        _CONFIDENCE_RANK["medium"]
                    ):
                        result["confidence"] = "medium"
                else:
                    # Full structured-source hit: promote 'low' to 'medium' —
                    # Nominatim importance scores penalise specific venues even
                    # when the structured query is accurate.
                    if result.get("confidence") == "low":
                        result["confidence"] = "medium"

            result["note"] = "tried: " + " | ".join(tried_log)

            with _lock:
                _progress["stage"] = "saving"

            if not dry_run:
                _save_geocode_result(get_write_queue(), location_text, result)

            with _lock:
                _progress["done"] = i + 1
                if result["source"] == "failed":
                    _progress["errors"] += 1
                else:
                    _progress["succeeded"] += 1

            if (i + 1) % 10 == 0:
                logger.info(
                    "Geocoding progress: %d/%d done, %d errors, %d skipped",
                    i + 1, total, _progress["errors"], _progress["skipped"],
                )

    except _StopSignal:
        logger.info("Batch geocode stopped by request at %d/%d", _progress["done"], total)
    finally:
        with _lock:
            _progress["running"] = False
            _progress["current"] = ""
            _progress["stage"] = "done"

    logger.info(
        "Batch geocode complete: %d/%d processed, %d errors, %d skipped, dry_run=%s",
        _progress["done"], total, _progress["errors"], _progress["skipped"], dry_run,
    )


def get_progress() -> dict:
    """Return a snapshot of the current batch geocoding progress state.

    Returns:
        Dict with keys: running (bool), done (int), total (int),
        current (str), errors (int), skipped (int) — locations written as
        source='skipped_not_concert' (TODO-221) — and stop_requested (bool),
        so the GUI can show a "stopping" state after ``stop()`` is called.
    """
    with _lock:
        return dict(_progress)
