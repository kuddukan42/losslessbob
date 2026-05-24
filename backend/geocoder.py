"""Nominatim geocoder for LosslessBob location data.

Provides single-location lookup, manual pin placement, and a batch runner
that reads un-geocoded entries.location values from the database and writes
results back via UPSERT.  Respects the Nominatim ToS 1-second rate limit.
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


def place_manual(location_text: str, lat: float, lon: float, note: str = "") -> None:
    """Insert or replace a geocoding result with a user-supplied coordinate.

    Manual entries are never overwritten by batch geocoding because
    ``manual_override=1`` is set.

    Args:
        location_text: The location string that matches entries.location.
        lat: WGS-84 latitude.
        lon: WGS-84 longitude.
        note: Optional freeform note (e.g. reason for the override).
    """
    from backend.db_queue import get_write_queue

    _loc, _lat, _lon, _note = location_text, lat, lon, note
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT INTO location_geocoded
                   (location_text, lat, lon, source, confidence, manual_override, note,
                    geocoded_at)
               VALUES (?, ?, ?, 'manual', 'high', 1, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(location_text) DO UPDATE SET
                   lat=excluded.lat,
                   lon=excluded.lon,
                   source='manual',
                   confidence='high',
                   manual_override=1,
                   note=excluded.note,
                   geocoded_at=CURRENT_TIMESTAMP""",
            (_loc, _lat, _lon, _note),
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

            for attempt in range(_MAX_429_RETRIES + 1):
                try:
                    result = geocode_one(location_text)
                    break
                except _RateLimitError:
                    if attempt < _MAX_429_RETRIES:
                        logger.warning(
                            "Rate-limited on %r; sleeping %ds (retry %d/%d)",
                            location_text, _RATE_LIMIT_SLEEP,
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
                            _MAX_429_RETRIES, location_text,
                        )
                        result = {
                            "location_text": location_text,
                            "lat": None,
                            "lon": None,
                            "display_name": None,
                            "source": "failed",
                            "confidence": None,
                            "note": f"HTTP 429: rate-limited after {_MAX_429_RETRIES} retries",
                        }

            with _lock:
                _progress["stage"] = "saving"

            if not dry_run:
                _r = result
                get_write_queue().execute(
                    lambda c: c.execute(
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
                            _r["location_text"],
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
