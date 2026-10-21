"""Curated best-of lists, show picks, song index, show detail and timeline routes (TODO-369)."""

import logging
import re

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend import gap_analysis as _gap_analysis
from backend import song_index as _song_index
from backend import timeline as _timeline

_log = logging.getLogger(__name__)

bp = Blueprint("ranking", __name__)


# ── Curated "best of" lists (TODO-181 remainder + FABLE_UNIFIED_RANKING §6) ──

@bp.route("/api/curated_lists", methods=["GET"])
def curated_lists_list() -> Response:
    """List curated lists with entry counts (carbonbit, 10haaf, ...)."""
    try:
        return jsonify(database.get_curated_lists())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/curated_lists", methods=["POST"])
def curated_lists_create() -> Response:
    """Curator-only. Create (or fetch, if it already exists) a curated list.

    Body: {name, label?, source?}
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        body = request.get_json(force=True) or {}
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "name is required"}), 400
        list_id = database.get_or_create_curated_list(
            name.strip(), body.get("label", ""), body.get("source", "")
        )
        return jsonify({"ok": True, "id": list_id, "name": name.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/curated_lists/<string:name>", methods=["DELETE"])
def curated_lists_delete(name: str) -> Response:
    """Curator-only. Delete a curated list and all its entries."""
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        deleted = database.delete_curated_list(name)
        if not deleted:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Show picks lookup (FABLE_UNIFIED_RANKING §6) ─────────────────────────────

@bp.route("/api/picks/for/<int:lb_number>", methods=["GET"])
def picks_for_lb(lb_number: int) -> Response:
    """Return this LB's show-pick rank/score/evidence, for DetailPanel's
    EvidenceList (per SPEC_INTEGRATION_NOTES.md F3). 204 when show_picks
    has no row for this LB yet (pre-recompute, or no usable date).
    """
    try:
        pick = database.get_show_pick_for_lb(lb_number)
        if pick is None:
            return "", 204
        return jsonify(pick)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/picks", methods=["GET"])
def picks_for_date() -> Response:
    """Return all show picks for one ISO concert date, rank-ordered.

    Query param ``date`` (``YYYY-MM-DD``) is required; missing or
    malformed values are a 400. No computed picks for that date is a
    normal 200 with an empty list.
    """
    date_param = request.args.get("date", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_param):
        return jsonify({"error": "date query param (YYYY-MM-DD) is required"}), 400
    from datetime import date as _date
    try:
        _date.fromisoformat(date_param)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400
    try:
        picks = database.get_picks_for_date(date_param)
        return jsonify(picks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/picks/tonight", methods=["GET"])
def picks_tonight() -> Response:
    """"This night in Dylan history" (LISTENING spec §9): rank-1 show
    picks whose concert date falls on today's calendar day (MM-DD)
    across all years, best-scored first. Accepts ``?mmdd=MM-DD`` to
    override "today" for testing. No matches is a normal 200 with an
    empty candidates list.
    """
    mmdd = request.args.get("mmdd", "")
    if mmdd and not re.match(r"^\d{2}-\d{2}$", mmdd):
        return jsonify({"error": "mmdd must be MM-DD"}), 400
    if not mmdd:
        from datetime import date as _date
        mmdd = _date.today().strftime("%m-%d")
    try:
        candidates = database.get_tonight_picks(mmdd)
        return jsonify({"mmdd": mmdd, "candidates": candidates})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Song index (LISTENING spec §3, TODO-230 — song-centric catalog view) ────

@bp.route("/api/songs", methods=["GET"])
def songs_list() -> Response:
    """List distinct songs from song_performances, most-performed first.

    Query param ``q`` (optional): substring filter against the canonical
    display spelling or the normalised key. No ``q`` returns every song.
    """
    try:
        songs = _song_index.get_songs(q=request.args.get("q") or None)
        return jsonify({"songs": songs})
    except Exception as e:
        _log.exception("songs_list failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/songs/performances", methods=["GET"])
def song_performances() -> Response:
    """Every performance of one song, joined to venue + circulating recordings.

    Query param ``song`` (required, the normalised ``song_norm`` key
    from ``GET /api/songs``). 404 if unknown.
    """
    song_norm = request.args.get("song", "")
    if not song_norm:
        return jsonify({"error": "song query param is required"}), 400
    try:
        result = _song_index.get_song_performances(song_norm)
        if result is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(result)
    except Exception as e:
        _log.exception("song_performances failed for song_norm=%r", song_norm)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/songs/alias", methods=["POST"])
def songs_alias() -> Response:
    """Curator-only. Map an alias spelling to a canonical display spelling.

    Body: {alias, canonical}. Normalises the alias, upserts song_canonical
    with source='curator' (sticky against future auto-seeding), then
    re-runs the song_performances recompute so the new spelling is live
    immediately. Returns the recompute stats dict.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        body = request.get_json(silent=True) or {}
        stats = _song_index.upsert_alias(body.get("alias", ""), body.get("canonical", ""))
        return jsonify({"ok": True, "stats": stats})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as e:
        _log.exception("songs_alias failed")
        return jsonify({"error": str(e)}), 500


# ── Show detail (Library performance lens — backend/gap_analysis.py) ───────
# Read-only: no writes, no derived table. Degrades to an empty/
# available:false response when olof_events is absent. This route is a
# rename/survivor of the standalone Gaps screen's four routes, retired
# once its coverage grid/detail became a Library performance-lens view
# (uncirculated/upcoming rows, Coverage facet) — this drill-down is what
# DetailPanel.tsx now calls for those rows.

@bp.route("/api/shows/<date_iso>/olof", methods=["GET"])
def show_olof_detail(date_iso: str) -> Response:
    """Drill-down: olof event rows, entries, and family data for one date."""
    try:
        return jsonify(_gap_analysis.get_date_detail(date_iso))
    except Exception as e:
        _log.exception("show_olof_detail failed for date_iso=%r", date_iso)
        return jsonify({"error": str(e)}), 500


# ── Timeline navigator (instructions/FABLE_TIMELINE.md) ─────────────────────
# Read-only: no writes, no derived table. All three routes degrade to an
# empty/available:false response when olof_events is absent.

@bp.route("/api/timeline/summary", methods=["GET"])
def timeline_summary() -> Response:
    """Decade-by-decade summary (night/circulating counts, best grade)."""
    try:
        return jsonify(_timeline.get_summary())
    except Exception as e:
        _log.exception("timeline_summary failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/timeline/decade/<int:decade>", methods=["GET"])
def timeline_decade(decade: int) -> Response:
    """Tour-by-tour breakdown for one decade."""
    try:
        return jsonify(_timeline.get_decade_detail(decade))
    except Exception as e:
        _log.exception("timeline_decade failed for decade=%r", decade)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/timeline/tour", methods=["GET"])
def timeline_tour() -> Response:
    """Night-by-night breakdown for one tour, scoped by decade.

    Query params: name (required, exact olof_events.tour_name), decade
    (required, int -- the decade of the tour's earliest show).
    """
    try:
        name = request.args.get("name", "")
        decade = request.args.get("decade", type=int)
        return jsonify(_timeline.get_tour_detail(name, decade))
    except Exception as e:
        _log.exception(
            "timeline_tour failed for name=%r decade=%r",
            request.args.get("name"), request.args.get("decade"),
        )
        return jsonify({"error": str(e)}), 500
