"""Admin page + standalone review pages (/admin, /taper-review, /taper-curation, /qc-review, /api/admin/*)"""

import logging
import time
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    send_from_directory,
)

from backend import (
    bobdylan_scraper,
    importer,
    scraper,
    site_crawler,
)
from backend import db as database
from backend.routes import _state as _route_state

_log = logging.getLogger(__name__)

bp = Blueprint("admin", __name__)


# ── Restart callback (set by run_backend.py so only the Flask server restarts) ─
_restart_callback = None


def set_restart_callback(cb) -> None:
    """Register a function the backend launcher calls to restart the Flask server in-process.

    When set, admin_restart invokes this instead of os.execv so the GUI is not affected.
    If not set (standalone/Windows), os.execv restarts the whole process as before.
    """
    global _restart_callback
    _restart_callback = cb


# ── Admin page ───────────────────────────────────────────────────────────

@bp.route("/admin")
def admin_page() -> Response:
    """Serve the mobile-friendly admin control panel."""
    admin_html = Path(__file__).parent.parent / "admin.html"
    return send_from_directory(str(admin_html.parent), admin_html.name)


@bp.route("/taper-review")
def taper_review_page() -> Response:
    """Serve the mobile-friendly taper conflict curation queue.

    One-card-at-a-time review of ``taper_attributions`` rows with
    ``conflict=1``, backed entirely by the existing curator confirm/reject
    API (TAPER phase 2) — each decision persists immediately server-side,
    so the queue can be worked in short sessions across page reloads.
    """
    review_html = Path(__file__).parent.parent / "taper_review.html"
    return send_from_directory(str(review_html.parent), review_html.name)


@bp.route("/taper-curation")
def taper_curation_page() -> Response:
    """Serve the taper curation workbench (TODO-327).

    A wide, keyboard-driven grid over all 16.7k entries: every source's
    taper opinion side by side with the raw LB description text, plus the
    isolated-text views for vocabulary work. Decisions post to the same
    curator-gated routes /taper-review uses.
    """
    page_html = Path(__file__).parent.parent / "taper_curation.html"
    return send_from_directory(str(page_html.parent), page_html.name)


@bp.route("/qc-review")
def qc_review_page() -> Response:
    """Serve the QC review console (TODO-342 Phase 2b, experimental).

    v1: Queue (one card at a time) and Findings (workbench table) tabs,
    both curator-gated for writes via the /api/qc/* routes above.
    """
    page_html = Path(__file__).parent.parent / "qc_review.html"
    return send_from_directory(str(page_html.parent), page_html.name)


@bp.route("/api/admin/status", methods=["GET"])
def admin_status() -> Response:
    """Return combined server/DB/scraper status for the admin dashboard.

    Returns:
        JSON dict with db stats, scrape status, import status, master stats,
        and server uptime in seconds.
    """
    try:
        result: dict = {}
        result["uptime_seconds"] = round(time.monotonic() - _route_state.process_start_time)
        try:
            result["db"] = database.get_stats()
        except Exception:
            result["db"] = None
        try:
            result["scrape"] = scraper.get_scrape_status()
        except Exception:
            result["scrape"] = None
        try:
            result["import_status"] = importer.get_import_status()
        except Exception:
            result["import_status"] = None
        try:
            result["crawler"] = site_crawler.get_crawler_status()
        except Exception:
            result["crawler"] = None
        try:
            result["bobdylan"] = bobdylan_scraper.get_status()
        except Exception:
            result["bobdylan"] = None
        try:
            conn = database.get_connection()
            total = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
            result["master"] = {"total": total}
        except Exception:
            result["master"] = None
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/admin/restart", methods=["POST"])
def admin_restart() -> Response:
    """Restart the entire application process to pick up code changes.

    Uses os.execv to replace the current process with a fresh copy.
    Returns a 202 before the restart so the client can handle it.
    """
    import os as _os
    import sys as _sys
    import threading as _threading

    def _do_restart():
        time.sleep(0.3)
        if _restart_callback is not None:
            _restart_callback()
        else:
            _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

    _threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "Restarting…"}), 202

_AUDIO_EXTS = frozenset({
    ".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".aiff", ".wv", ".m4a",
})
