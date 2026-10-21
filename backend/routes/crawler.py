"""Site crawler and preservation-stack routes (TODO-266)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import db as database
from backend import (
    preservation,
    site_crawler,
)

_log = logging.getLogger(__name__)

bp = Blueprint("crawler", __name__)


# ── Site Crawler ─────────────────────────────────────────────────────────


@bp.route("/api/crawler/start", methods=["POST"])
def crawler_start():
    """Start a full-domain crawl in a background thread.

    Body JSON (all optional):
        scope     (str):  "full" or "incremental".  Default "incremental".
        force     (bool): Re-fetch cached pages.  Default false.
        delay_ms  (int):  Base ms between requests.  Default 1500.
        daily_cap (int):  Max requests this session.  Default 99999.

    Returns:
        JSON: {ok: true}  or  {ok: false, error: "already running"}
    """
    try:
        data = request.get_json() or {}
        scope     = data.get("scope", "incremental")
        force     = bool(data.get("force", False))
        delay_ms  = int(data.get("delay_ms", 1500))
        daily_cap = int(data.get("daily_cap", 99999))
        if not site_crawler.start_crawl_async(
            scope=scope, force=force, delay_ms=delay_ms, daily_cap=daily_cap,
        ):
            return jsonify({"ok": False, "error": "Crawler already running"}), 409
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/crawler/status", methods=["GET"])
def crawler_status():
    """Return a snapshot of the current crawler state."""
    return jsonify(site_crawler.get_crawler_status())


@bp.route("/api/crawler/stop", methods=["POST"])
def crawler_stop():
    """Request the crawler to stop after the current URL."""
    site_crawler.stop_crawler()
    return jsonify({"ok": True})


@bp.route("/api/crawler/sessions", methods=["GET"])
def crawler_sessions():
    """Return recent scrape session rows.

    Query params:
        limit (int): Max rows to return.  Default 20, max 100.
    """
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        return jsonify(database.get_scrape_sessions(limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/crawler/inventory", methods=["GET"])
def crawler_inventory():
    """Paginated site_inventory rows.

    Query params:
        status      (str): Filter by status (downloaded, pending, failed, not_found, skipped).
        path_prefix (str): Filter by relative_path prefix.
        limit       (int): Default 200, max 1000.
        offset      (int): Default 0.
    """
    try:
        rows, total = database.get_inventory_page(
            status=request.args.get("status") or None,
            path_prefix=request.args.get("path_prefix") or None,
            limit=min(int(request.args.get("limit", 200)), 1000),
            offset=int(request.args.get("offset", 0)),
        )
        return jsonify({"rows": rows, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/crawler/inventory/stats", methods=["GET"])
def crawler_inventory_stats():
    """Return aggregate counts from site_inventory grouped by status."""
    try:
        return jsonify(database.get_inventory_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Preservation stack (TODO-266) ────────────────────────────────────────

@bp.route("/api/preservation/start", methods=["POST"])
def preservation_start():
    """Start a preservation job in a background thread.

    Only one job may run at a time (they all hash or hardlink large parts of
    the mirror).

    Body JSON:
        job          (str):  "verify" | "baseline" | "linkcheck" | "snapshot".
        limit        (int):  baseline only — cap on rows processed.
        full         (bool): linkcheck only — check every page, not a sample.
        sample_size  (int):  linkcheck only — size of the non-seed sample.
        with_db      (bool): snapshot only — include a DB export. Default true.
        verify_first (bool): snapshot only — refuse to seal a broken mirror.
            Default true; clearing it is logged loudly by the tool.
        tar          (bool): snapshot only — also build a .tar.gz.

    Returns:
        JSON {ok: true} — or 409 if a job is already running, 400 on a bad
        job name.
    """
    try:
        data = request.get_json() or {}
        job = data.get("job", "")
        opts: dict = {}
        if job == "baseline" and data.get("limit") is not None:
            opts["limit"] = int(data["limit"])
        elif job == "linkcheck":
            opts["full"] = bool(data.get("full", False))
            if data.get("sample_size") is not None:
                opts["sample_size"] = int(data["sample_size"])
        elif job == "snapshot":
            opts["with_db"] = bool(data.get("with_db", True))
            opts["verify_first"] = bool(data.get("verify_first", True))
            opts["tar"] = bool(data.get("tar", False))
        preservation.start_job(job, **opts)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/preservation/status", methods=["GET"])
def preservation_status():
    """Return the current preservation job state plus mirror figures."""
    try:
        status = preservation.get_status()
        status["mirror"] = preservation.mirror_stats()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/preservation/stop", methods=["POST"])
def preservation_stop():
    """Ask the running preservation job to stop at its next checkpoint.

    Returns:
        JSON {ok: true, stopping: bool} — ``stopping`` is false when no job
        was running.
    """
    try:
        return jsonify({"ok": True, "stopping": preservation.request_stop()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/preservation/snapshots", methods=["GET"])
def preservation_snapshots():
    """List sealed snapshots on disk, newest first."""
    try:
        return jsonify(preservation.list_snapshots())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/preservation/reports", methods=["GET"])
def preservation_reports():
    """List recent preservation report files.

    Query params:
        limit (int): Max reports to return.  Default 10, max 50.
    """
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
        return jsonify(preservation.last_reports(limit=limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/preservation/report", methods=["GET"])
def preservation_report():
    """Return the text of one preservation report.

    Query params:
        path (str): Report path as handed out by /api/preservation/reports.
            Paths outside data/exports/ are rejected.
    """
    try:
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path required"}), 400
        return jsonify({"path": path, "text": preservation.read_report(path)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError:
        return jsonify({"error": "report not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
