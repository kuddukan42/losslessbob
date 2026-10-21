"""Bootleg-CD catalog routes (scrape, status, browse)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import bootleg_scraper
from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("bootlegs", __name__)


# ── Bootleg-CD Catalog ────────────────────────────────────────────────────

@bp.route("/api/bootlegs/scrape", methods=["POST"])
def bootlegs_scrape():
    """Trigger a bootleg catalog scrape. Body: {force: bool}.

    Long-running — runs in a background thread so the HTTP response
    returns immediately.  Poll ``GET /api/bootlegs/scrape/status`` for
    progress.

    Returns:
        JSON: {ok: true, running: true}
    """
    try:
        data = request.get_json() or {}
        force = bool(data.get("force", False))
        if not bootleg_scraper.start_scrape_async(force=force):
            return jsonify({"ok": False, "error": "Scrape already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bootlegs/scrape/status", methods=["GET"])
def bootlegs_scrape_status():
    """Poll the bootleg scrape progress state."""
    return jsonify(bootleg_scraper.get_scrape_status())


@bp.route("/api/bootlegs", methods=["GET"])
def bootlegs_list():
    """Paginated, filtered bootleg title list.

    Query params: q, year_min, year_max, cd_min, cd_max, lb_status,
    owned (true/false), has_lbbcd (true/false), sort_col, sort_dir,
    limit (default 200, max 1000), offset (default 0).

    Returns:
        JSON: {rows: [...], total: int}
    """
    try:
        def _bool(key: str) -> bool | None:
            v = request.args.get(key, "").lower()
            if v == "true":
                return True
            if v == "false":
                return False
            return None

        rows, total = database.get_bootlegs(
            q=request.args.get("q", ""),
            year_min=int(request.args["year_min"]) if "year_min" in request.args else None,
            year_max=int(request.args["year_max"]) if "year_max" in request.args else None,
            cd_min=int(request.args["cd_min"]) if "cd_min" in request.args else None,
            cd_max=int(request.args["cd_max"]) if "cd_max" in request.args else None,
            lb_status=request.args.get("lb_status") or None,
            owned=_bool("owned"),
            has_lbbcd=_bool("has_lbbcd"),
            sort_col=request.args.get("sort_col", "lb_number"),
            sort_dir=request.args.get("sort_dir", "ASC"),
            limit=min(int(request.args.get("limit", 200)), 1000),
            offset=int(request.args.get("offset", 0)),
        )
        return jsonify({"rows": rows, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bootlegs/by_lb/<int:lb>", methods=["GET"])
def bootlegs_by_lb(lb: int):
    """All bootleg titles for one LB number."""
    try:
        return jsonify(database.get_bootlegs_for_lb(lb))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bootlegs/scrapes", methods=["GET"])
def bootlegs_scrape_history():
    """Recent bootleg_scrapes rows (newest first). Query param: limit (default 20)."""
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        return jsonify(database.get_bootleg_scrape_history(limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/bootlegs/stats", methods=["GET"])
def bootlegs_stats():
    """Summary counts: total rows, last scrape timestamp and status."""
    try:
        return jsonify(database.get_bootleg_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
