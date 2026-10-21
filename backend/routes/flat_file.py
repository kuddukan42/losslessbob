"""Flat-file update pipeline (/api/flat_file/*) and site-mirror xref ingest (/api/xref_ingest/*)."""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend.scrape_worker import _start_scrape_thread

_log = logging.getLogger(__name__)

bp = Blueprint("flat_file", __name__)


# ── Flat file update pipeline ─────────────────────────────────────────────

@bp.route("/api/flat_file/discover", methods=["GET"])
def flat_file_discover() -> Response:
    """Live check for a new flat-file release on the LosslessBob download page."""
    from backend import flat_file as ff
    try:
        result = ff.discover_flat_file_release()
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/download/<int:release_id>", methods=["POST"])
def flat_file_download(release_id):
    """Download the zip for a detected release (may be long-running)."""
    from backend import flat_file as ff
    try:
        path = ff.download_flat_file_release(release_id)
        return jsonify({"path": str(path), "release_id": release_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/diff/<int:release_id>", methods=["GET"])
def flat_file_diff(release_id):
    """Return diff counts (rows_added/changed/removed) without applying."""
    from backend import flat_file as ff
    try:
        return jsonify(ff.diff_flat_file_release(release_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/apply/<int:release_id>", methods=["POST"])
def flat_file_apply(release_id):
    """Apply a downloaded flat-file release, then scrape its never-scraped LBs.

    The scrape runs in the background and batch-reconciles lb_master when it
    finishes, so a release needs no separate Scrape or Reconcile step.
    ``scrape_started`` is False when another scrape already holds the worker.
    """
    from backend import flat_file as ff
    try:
        result = ff.apply_flat_file_release(release_id)
        new_lbs = result.get("new_lb_numbers") or []
        result["scrape_started"] = False
        if new_lbs:
            result["scrape_started"] = _start_scrape_thread(
                new_lbs,
                force=True,
                delay_ms=int(database.get_meta("scrape_delay_ms") or 1500),
                download=database.get_meta("scrape_attachments") != "0",
            )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/defer/<int:release_id>", methods=["POST"])
def flat_file_defer(release_id):
    """Defer prompting for a release. Body: {days: int} or {until_next: true}."""
    from backend import flat_file as ff
    body = request.get_json(force=True) or {}
    try:
        ff.defer_flat_file_release(
            release_id,
            days=body.get("days"),
            until_next=body.get("until_next", False),
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/api/flat_file/releases", methods=["GET"])
def flat_file_releases():
    """List all flat file release history rows, newest first."""
    from backend import flat_file as ff
    try:
        return jsonify(ff.get_releases())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/changelog/<int:release_id>", methods=["GET"])
def flat_file_changelog(release_id):
    """Paginated changelog for a release. Query params: limit, offset."""
    from backend import flat_file as ff
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    try:
        return jsonify(ff.get_release_changelog(release_id, limit, offset))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Site-mirror xref ingest (TODO-252 / B8) ───────────────────────────────

@bp.route("/api/xref_ingest/scan", methods=["POST"])
def xref_ingest_scan() -> Response:
    """Scan the site mirror for new xref checksum filesets and stage them."""
    from backend import xref_ingest as xi
    try:
        return jsonify(xi.scan_mirror())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/xref_ingest/filesets", methods=["GET"])
def xref_ingest_filesets() -> Response:
    """List staged/approved/rejected filesets. Query param: status (optional)."""
    from backend import xref_ingest as xi
    status = request.args.get("status")
    try:
        return jsonify(xi.get_filesets(status=status))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/xref_ingest/approve", methods=["POST"])
def xref_ingest_approve() -> Response:
    """Approve staged filesets. Body: {ids: [int, ...]}."""
    from backend import xref_ingest as xi
    body = request.get_json(force=True) or {}
    try:
        ids = [int(i) for i in body.get("ids", [])]
    except (TypeError, ValueError):
        return jsonify({"error": "ids must be a list of integers"}), 400
    try:
        return jsonify(xi.approve_filesets(ids))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/xref_ingest/reject", methods=["POST"])
def xref_ingest_reject() -> Response:
    """Reject staged filesets. Body: {ids: [int, ...]}."""
    from backend import xref_ingest as xi
    body = request.get_json(force=True) or {}
    try:
        ids = [int(i) for i in body.get("ids", [])]
    except (TypeError, ValueError):
        return jsonify({"error": "ids must be a list of integers"}), 400
    try:
        return jsonify(xi.reject_filesets(ids))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
