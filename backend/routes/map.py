"""Map feature + geocode routes (/map, /leaflet, /api/map, /api/geocode/*)"""

import logging
from pathlib import Path

from flask import (
    Blueprint,
    jsonify,
    request,
    send_from_directory,
)

from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("map", __name__)


# ── Map feature routes — added 2026-05-18 ──────────────────────────────────────

@bp.route("/map")
def serve_map():
    """Serve backend/resources/map.html for the gui_next map iframe and system browser."""
    resources_dir = (Path(__file__).parent.parent / "resources").resolve()
    return send_from_directory(str(resources_dir), "map.html")


@bp.route("/leaflet/<path:filename>")
def serve_leaflet(filename: str):
    """Serve bundled Leaflet JS/CSS assets from backend/resources/leaflet/."""
    leaflet_dir = (Path(__file__).parent.parent / "resources" / "leaflet").resolve()
    return send_from_directory(str(leaflet_dir), filename)


@bp.route("/api/map/data")
def api_map_data():
    """Return geocoded concert entries filtered by status, owned, year, and free text.

    Query params:
        status (str): lb_master status filter (public/private/missing).
        owned (str): "true" to restrict to my_collection entries.
        year_min (int): inclusive lower year bound.
        year_max (int): inclusive upper year bound.
        q (str): free-text search against location/date fields.

    Returns:
        JSON list of map marker dicts from db.get_map_data().
    """
    _owned_param = request.args.get("owned")
    filters = {
        "status":   request.args.get("status") or None,
        "owned":    True if _owned_param in ("true", "1") else None,
        "year_min": int(request.args.get("year_min")) if request.args.get("year_min") else None,
        "year_max": int(request.args.get("year_max")) if request.args.get("year_max") else None,
        "q":        request.args.get("q") or None,
    }
    try:
        result = database.get_map_data(filters)
    except AttributeError:
        return jsonify({"error": "get_map_data not yet available in db module"}), 503
    return jsonify(result)


@bp.route("/api/geocode/run", methods=["POST"])
def api_geocode_run():
    """Start a background geocode batch.

    Body (optional): {retry_failed: bool, limit: int|null}

    Returns:
        {status: "started"} or 409 if already running, 503 if module unavailable.
    """
    try:
        import backend.geocoder as _geocoder
    except ImportError:
        return jsonify({"error": "geocoder module not available"}), 503

    body = request.get_json(silent=True) or {}
    retry_failed = bool(body.get("retry_failed", False))
    limit = body.get("limit")

    if not _geocoder.start_batch_async(limit=limit, retry_failed=retry_failed):
        return jsonify({"error": "already running"}), 409
    return jsonify({"status": "started"})


@bp.route("/api/geocode/stop", methods=["POST"])
def api_geocode_stop():
    """Signal the active geocode batch to stop; mirrors /api/bobdylan/stop.

    Returns:
        The current _geocoder._progress dict (with stop_requested=True
        once the flag is set) or 503 if the geocoder module is
        unavailable.
    """
    try:
        import backend.geocoder as _geocoder
    except ImportError:
        return jsonify({"error": "geocoder module not available"}), 503

    _geocoder.stop()
    return jsonify(_geocoder.get_progress())


@bp.route("/api/geocode/status")
def api_geocode_status():
    """Return current geocode batch progress dict.

    Returns:
        _geocoder._progress dict or 503 if module unavailable.
    """
    try:
        import backend.geocoder as _geocoder
        return jsonify(_geocoder._progress)
    except ImportError:
        return jsonify({"error": "geocoder module not available"}), 503


@bp.route("/api/geocode/stats")
def api_geocode_stats():
    """Return cache and coverage stats for the geocoder tab.

    Returns:
        JSON dict with keys: total_cached, geocoded, failed, manual,
        skipped (TODO-221 source='skipped_not_concert', excluded from
        failed), entries_total, entries_covered, pct_covered.
    """
    try:
        conn = database.get_connection()
        row = conn.execute("""
                SELECT
                    COUNT(*)                                                   AS total_cached,
                    COALESCE(SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END), 0) AS geocoded,
                    COALESCE(SUM(CASE WHEN lat IS NULL
                                       AND source != 'skipped_not_concert'
                                  THEN 1 ELSE 0 END), 0)                       AS failed,
                    COALESCE(SUM(CASE WHEN manual_override = 1 THEN 1 ELSE 0 END), 0) AS manual,
                    COALESCE(SUM(CASE WHEN source = 'skipped_not_concert'
                                  THEN 1 ELSE 0 END), 0)                       AS skipped
                FROM location_geocoded
            """).fetchone()
        cov = conn.execute("""
                SELECT
                    COUNT(DISTINCT e.location)                       AS entries_total,
                    COUNT(DISTINCT CASE WHEN g.lat IS NOT NULL
                        THEN e.location END)                         AS entries_covered
                FROM entries e
                LEFT JOIN location_geocoded g ON g.location_text = e.location
                WHERE e.location IS NOT NULL AND e.location != ''
            """).fetchone()
        result = dict(row) if row else {}
        if cov:
            result["entries_total"]   = cov["entries_total"]
            result["entries_covered"] = cov["entries_covered"]
            total = cov["entries_total"] or 0
            covered = cov["entries_covered"] or 0
            result["pct_covered"] = round(covered / total * 100, 1) if total else 0
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/geocode/location", methods=["POST"])
def api_geocode_location():
    """Manually place a location's coordinates.

    Body: {location: str, lat: float, lon: float, note: str (optional)}

    Returns:
        {ok: true} or 400/503 on error.
    """
    try:
        import backend.geocoder as _geocoder
    except ImportError:
        return jsonify({"error": "geocoder module not available"}), 503

    body = request.get_json(silent=True) or {}
    location = body.get("location", "").strip()
    lat = body.get("lat")
    lon = body.get("lon")
    note = body.get("note", "")
    lb_number = body.get("lb_number") or None

    if not location or lat is None or lon is None:
        return jsonify({"error": "location, lat, lon required"}), 400

    _geocoder.place_manual(location, float(lat), float(lon), note, lb_number)
    return jsonify({"ok": True})


@bp.route("/api/geocode/purge", methods=["POST"])
def api_geocode_purge():
    """Purge cached geocoding data from location_geocoded.

    Requires curator mode. Body: {scope: "failed"|"all"}.
    - "failed": removes rows where source='failed' OR lat IS NULL.
    - "all": removes every row (manual overrides included).

    Returns:
        {ok: true, deleted: int} or 400/403 on error.
    """
    if not database.get_meta("is_curator"):
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "failed")
    if scope not in ("failed", "all"):
        return jsonify({"error": "scope must be 'failed' or 'all'"}), 400
    try:
        conn = database.get_connection()
        if scope == "all":
            cur = conn.execute("DELETE FROM location_geocoded")
        else:
            cur = conn.execute(
                "DELETE FROM location_geocoded WHERE source = 'failed' OR lat IS NULL"
            )
        deleted = cur.rowcount
        conn.commit()
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/geocode/locations")
def api_geocode_locations():
    """Return rows from location_geocoded for the curator geocode management UI.

    Query params:
        filter (str): all | failed | low_confidence | manual (default: all)

    Returns:
        {"locations": [<row dicts>]}
    """
    filter_type = request.args.get("filter", "all")
    try:
        conn = database.get_connection()
        where_map = {
            "failed":         "WHERE lg.source = 'failed'",
            "low_confidence": "WHERE lg.confidence = 'low'",
            "manual":         "WHERE lg.manual_override = 1",
            "all":            "",
        }
        where = where_map.get(filter_type, "")
        rows = conn.execute(f"""
                SELECT lg.*,
                       lg.manual_override AS is_manual,
                       GROUP_CONCAT(e.lb_number, ', ') AS lb_numbers
                FROM location_geocoded lg
                LEFT JOIN entries e ON e.location = lg.location_text
                {where}
                GROUP BY lg.location_text
                ORDER BY lg.location_text
            """).fetchall()
        return jsonify({"locations": [dict(r) for r in rows]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
