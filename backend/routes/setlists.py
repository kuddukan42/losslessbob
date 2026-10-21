"""Setlist-source routes: bobdylan.com, setlist.fm, Olof Björner corpus, setlist fingerprint suggestions (TODO-369)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import bobdylan_scraper
from backend import db as database
from backend import setlist_fingerprint as _setlist_fingerprint
from backend import setlistfm as setlistfm_mod

_log = logging.getLogger(__name__)

bp = Blueprint("setlists", __name__)


# ------------------------------------------------------------------
# bobdylan.com setlist routes
# ------------------------------------------------------------------

@bp.route("/api/bobdylan/update", methods=["POST"])
def bobdylan_update():
    """Start background discover + scrape of bobdylan.com setlists.

    Body: {force: bool}  — if true, re-scrapes already-scraped shows.
    Long-running; poll GET /api/bobdylan/status for progress.

    Returns:
        JSON: {ok: true, running: true}
    """
    try:
        data = request.get_json() or {}
        force = bool(data.get("force", False))
        if not bobdylan_scraper.start_update_async(force=force):
            return jsonify({"ok": False, "error": "Already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bobdylan/discover", methods=["POST"])
def bobdylan_discover():
    """Start background sitemap URL discovery (no page scraping).

    Returns:
        JSON: {ok: true, running: true}
    """
    try:
        if not bobdylan_scraper.start_discover_async():
            return jsonify({"ok": False, "error": "Already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bobdylan/scrape", methods=["POST"])
def bobdylan_scrape():
    """Start background scrape of unscraped show pages.

    Body: {force: bool}  — if true, re-scrapes all shows.

    Returns:
        JSON: {ok: true, running: true}
    """
    try:
        data = request.get_json() or {}
        force = bool(data.get("force", False))
        if not bobdylan_scraper.start_scrape_async(force=force):
            return jsonify({"ok": False, "error": "Already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bobdylan/stop", methods=["POST"])
def bobdylan_stop():
    """Signal the active bobdylan scrape worker to stop."""
    bobdylan_scraper.stop()
    return jsonify({"ok": True})


@bp.route("/api/bobdylan/status", methods=["GET"])
def bobdylan_status():
    """Return the current bobdylan scraper progress state."""
    return jsonify(bobdylan_scraper.get_status())


@bp.route("/api/bobdylan/show", methods=["GET"])
def bobdylan_show():
    """Return the bobdylan.com show record and setlist for a given date.

    Query params:
        date (str) — YYYY-MM-DD

    Returns:
        JSON: {bobdylan_url, venue, location, notes, scraped_at, tracks: [{name, song_url}]}
        204 (no body) if no show is found for this date.
    """
    try:
        date = request.args.get("date", "").strip()
        if not date:
            return jsonify({"error": "date param required"}), 400
        conn = database.get_connection()
        show = conn.execute(
            """SELECT bobdylan_url, venue, location, notes, scraped_at
                   FROM bobdylan_shows WHERE date_str=? LIMIT 1""",
            (date,),
        ).fetchone()
        if not show:
            return "", 204
        tracks = conn.execute(
            """SELECT track_name, song_url
                   FROM bobdylan_setlist WHERE bobdylan_url=? ORDER BY position""",
            (show["bobdylan_url"],),
        ).fetchall()
        return jsonify({
            "bobdylan_url": show["bobdylan_url"],
            "venue": show["venue"],
            "location": show["location"],
            "notes": show["notes"],
            "scraped_at": show["scraped_at"],
            "tracks": [{"name": r["track_name"], "song_url": r["song_url"]} for r in tracks],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bobdylan/stats", methods=["GET"])
def bobdylan_stats():
    """Return counts for bobdylan_shows coverage.

    Returns:
        JSON: {total: int, scraped: int, pending: int}
    """
    try:
        conn = database.get_connection()
        total = conn.execute("SELECT COUNT(*) FROM bobdylan_shows").fetchone()[0]
        scraped = conn.execute(
            "SELECT COUNT(*) FROM bobdylan_shows WHERE scraped_at IS NOT NULL"
        ).fetchone()[0]
        return jsonify({"total": total, "scraped": scraped, "pending": total - scraped})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------
# setlist.fm routes
# ------------------------------------------------------------------

@bp.route("/api/setlistfm/key", methods=["POST"])
def setlistfm_set_key():
    """Store the setlist.fm API key. Body: {api_key: str}.

    Returns:
        JSON: {ok: true}
    """
    try:
        data = request.get_json() or {}
        key = (data.get("api_key") or "").strip()
        if not key:
            return jsonify({"error": "api_key is required"}), 400
        setlistfm_mod.save_api_key(key)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/setlistfm/key", methods=["GET"])
def setlistfm_get_key():
    """Return whether an API key is configured (never returns the key itself).

    Returns:
        JSON: {configured: bool}
    """
    return jsonify({"configured": bool(setlistfm_mod.get_api_key())})


@bp.route("/api/setlistfm/update", methods=["POST"])
def setlistfm_update():
    """Start background fetch of all setlist.fm setlists.

    Body: {force: bool, api_key: str (optional override)}
    Long-running; poll GET /api/setlistfm/status for progress.

    Returns:
        JSON: {ok: true, running: true}
    """
    try:
        data = request.get_json() or {}
        force = bool(data.get("force", False))
        api_key = (data.get("api_key") or "").strip() or None
        if not setlistfm_mod.start_update_async(force=force, api_key=api_key):
            return jsonify({"ok": False, "error": "Already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/setlistfm/stop", methods=["POST"])
def setlistfm_stop():
    """Signal the active setlistfm worker to stop."""
    setlistfm_mod.stop()
    return jsonify({"ok": True})


@bp.route("/api/setlistfm/status", methods=["GET"])
def setlistfm_status():
    """Return the current setlistfm worker progress state."""
    return jsonify(setlistfm_mod.get_status())


@bp.route("/api/setlistfm/show", methods=["GET"])
def setlistfm_show():
    """Return setlist.fm show + structured setlist for a given date.

    Query params:
        date (str) — YYYY-MM-DD

    Returns:
        JSON: {setlistfm_id, date_str, tour_name, venue_name, city, country,
               info, setlistfm_url,
               sets: [{set_index, set_name, is_encore,
                       songs: [{position, set_position, track_name, info,
                                is_cover, cover_artist, is_tape}]}]}
        204 if no show found for this date.
    """
    try:
        date = request.args.get("date", "").strip()
        if not date:
            return jsonify({"error": "date param required"}), 400
        conn = database.get_connection()
        show = conn.execute(
            """SELECT setlistfm_id, date_str, tour_name, venue_name,
                          city, country, info, setlistfm_url
                   FROM setlistfm_shows WHERE date_str=? LIMIT 1""",
            (date,),
        ).fetchone()
        if not show:
            return "", 204
        songs = conn.execute(
            """SELECT set_index, set_name, is_encore, position, set_position,
                          track_name, info, is_cover, cover_artist, is_tape
                   FROM setlistfm_setlist
                   WHERE setlistfm_id=?
                   ORDER BY position""",
            (show["setlistfm_id"],),
        ).fetchall()
        # Group songs by set_index
        sets: dict[int, dict] = {}
        for s in songs:
            idx = s["set_index"]
            if idx not in sets:
                sets[idx] = {
                    "set_index": idx,
                    "set_name": s["set_name"],
                    "is_encore": s["is_encore"],
                    "songs": [],
                }
            sets[idx]["songs"].append({
                "position": s["position"],
                "set_position": s["set_position"],
                "track_name": s["track_name"],
                "info": s["info"],
                "is_cover": s["is_cover"],
                "cover_artist": s["cover_artist"],
                "is_tape": s["is_tape"],
            })
        return jsonify({
            "setlistfm_id": show["setlistfm_id"],
            "date_str": show["date_str"],
            "tour_name": show["tour_name"],
            "venue_name": show["venue_name"],
            "city": show["city"],
            "country": show["country"],
            "info": show["info"],
            "setlistfm_url": show["setlistfm_url"],
            "sets": list(sets.values()),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/setlistfm/stats", methods=["GET"])
def setlistfm_stats():
    """Return setlistfm coverage counts.

    Returns:
        JSON: {shows: int, tracks: int, tours: int}
    """
    try:
        conn = database.get_connection()
        shows  = conn.execute("SELECT COUNT(*) FROM setlistfm_shows").fetchone()[0]
        tracks = conn.execute("SELECT COUNT(*) FROM setlistfm_setlist").fetchone()[0]
        tours  = conn.execute(
            "SELECT COUNT(DISTINCT tour_name) FROM setlistfm_shows WHERE tour_name != ''"
        ).fetchone()[0]
        return jsonify({"shows": shows, "tracks": tracks, "tours": tours})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Olof Björner (Still On The Road + Yearly Chronicles) ──────────────────
# olof_* tables are local-only (not in MASTER_TABLES); every route here
# degrades to empty lists/counts rather than 404ing when they're empty.

@bp.route("/api/olof/date/<date_str>", methods=["GET"])
def olof_date(date_str: str):
    """Return everything Olof's corpus knows about a show date.

    Returns:
        JSON: {date_str, events: [olof_events row + songs: [...]],
               chronicle: [olof_chronicle rows], new_tapes: [olof_new_tapes
               rows]}. Lists are empty (not 404) when nothing matches.
    """
    try:
        return jsonify(database.get_olof_date(date_str))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/olof/event/<int:event_id>", methods=["GET"])
def olof_event(event_id: int):
    """Return one olof_events row (all columns) plus its ordered songs.

    Returns:
        JSON: olof_events columns + {songs: [...]}. 404 if event_id is
        unknown.
    """
    try:
        event = database.get_olof_event(event_id)
        if event is None:
            return jsonify({"error": "event not found"}), 404
        return jsonify(event)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/olof/chronicle/<int:year>", methods=["GET"])
def olof_chronicle_year(year: int):
    """Return one chronicle year's entries in calendar order.

    Returns:
        JSON: {year, entries: [olof_chronicle rows]}. Empty list if the
        year has no chronicle page parsed.
    """
    try:
        return jsonify({"year": year, "entries": database.get_olof_chronicle_year(year)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/olof/status", methods=["GET"])
def olof_status():
    """Return per-table Olof row counts + max DSN year, for GUI gating.

    Returns:
        JSON: {pages, events, songs, chronicle_rows, new_tapes,
               chronicle_years, max_dsn_year}
    """
    try:
        return jsonify(database.get_olof_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/olof/bobtalk_search", methods=["GET"])
def olof_bobtalk_search():
    """Search olof_events.bobtalk/notes for "Bob said X — which night?" lookups.

    Query params:
        q (str, required) — search text, min 2 chars after strip.
        limit (int, optional, default 50, capped at 200).

    Returns:
        JSON: {q, hits: [{event_id, date_str, venue, city, country,
               event_type, concert_no_net, field, snippet}]}.
        400 if q is missing or shorter than 2 chars.
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "q must be at least 2 characters"}), 400
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    try:
        hits = database.get_olof_bobtalk_search(q, limit=limit)
        return jsonify({"q": q, "hits": hits})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/olof/compare", methods=["POST"])
def olof_compare():
    """Compare a folder's track titles against Olof's setlist for a date.

    Body JSON:
        date_str (str, required) — ISO yyyy-mm-dd.
        titles (list[str], optional) — track titles in any order.
        lb_number (int, optional) — resolves titles server-side from the
            catalog entry's stored ``entries.setlist`` tracklist text.
            Used only when ``titles`` is omitted/empty.

    Returns:
        JSON: {date_str, olof_event_id, olof_setlist: [{position,
               song_title}], matches: [{input_title, matched_position,
               matched_title}], olof_missing: [song_title, ...],
               match_pct, recording_info, recording_kind, recording_mins}
        400 if neither titles nor a resolvable lb_number is given.
    """
    try:
        data = request.get_json() or {}
        date_str = (data.get("date_str") or "").strip()
        if not date_str:
            return jsonify({"error": "date_str required"}), 400
        titles = data.get("titles") or []
        if not titles and data.get("lb_number") is not None:
            titles = database.resolve_lb_number_titles(int(data["lb_number"])) or []
        if not titles:
            return jsonify({"error": "titles or a resolvable lb_number required"}), 400
        return jsonify(database.compare_olof_setlist(date_str, titles))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/fingerprint/scan", methods=["POST"])
def fingerprint_scan():
    """TODO-225: (re)scan candidate entries and rebuild the suggestion queue.

    Candidates are entries with no clean parseable date or a location in
    the TODO-221 skipped_not_concert bucket — see
    backend/setlist_fingerprint.py:_find_candidate_entries. Wholesale-
    replaces setlist_fingerprint_suggestions; not curator-gated, like
    POST /api/derived/recompute — it only rebuilds a local-only derived
    suggestion table, no master data or curator decision involved.

    Body JSON (optional): {limit: int} — cap on candidates scanned.

    Returns:
        JSON: {candidates_scanned, candidates_matched,
               suggestions_written, skipped_no_titles}
    """
    try:
        data = request.get_json(silent=True) or {}
        limit = data.get("limit")
        stats = _setlist_fingerprint.run_fingerprint_scan(limit=int(limit) if limit else None)
        return jsonify(stats)
    except Exception as e:
        _log.exception("fingerprint_scan failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/fingerprint/suggestions", methods=["GET"])
def fingerprint_suggestions():
    """List the setlist-fingerprint curator review queue.

    Query param ``status`` (optional): 'pending' (default), 'dismissed',
    or 'all'.

    Returns:
        JSON: {suggestions: [...]} — see
        backend.setlist_fingerprint.get_suggestions for the row shape.
    """
    try:
        status = request.args.get("status", "pending")
        return jsonify({"suggestions": _setlist_fingerprint.get_suggestions(status=status)})
    except Exception as e:
        _log.exception("fingerprint_suggestions failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/fingerprint/suggestions/dismiss", methods=["POST"])
def fingerprint_dismiss():
    """Curator-only. Dismiss one suggestion; sticky across rescans.

    Body JSON: {lb_number: int, event_id: int}

    Returns:
        JSON: {ok}. 404 if no matching row existed.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        data = request.get_json(force=True)
        lb_number = int(data["lb_number"])
        event_id = int(data["event_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lb_number and event_id are required"}), 400
    try:
        found = _setlist_fingerprint.dismiss_suggestion(lb_number, event_id)
        if not found:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        _log.exception("fingerprint_dismiss failed")
        return jsonify({"error": str(e)}), 500
