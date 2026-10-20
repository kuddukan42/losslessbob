"""Scraper control routes (start/stop/status, page download, private re-scrape)."""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend import scraper
from backend.scrape_worker import _start_download_pages_thread, _start_scrape_thread

_log = logging.getLogger(__name__)

bp = Blueprint("scrape", __name__)


# ── Scraper Control ──────────────────────────────────────────────────────

@bp.route("/api/scrape/start", methods=["POST"])
def scrape_start() -> Response:
    """Start a background scrape over a range of LB numbers.

    Excludes LBs whose lb_master.lb_status is 'private' — those are handled
    exclusively by /api/scrape/private_rescrape.

    Body: {start_lb?, end_lb?, force?}
    Returns:
        JSON {ok, total} where total is the number of LBs queued.
    """
    try:
        data = request.get_json() or {}
        start_lb = data.get("start_lb", 1)
        end_lb = data.get("end_lb", None)
        force = data.get("force", False)
        # The Scraper screen sends its own delay / download choices; the saved
        # settings are only the fallback for callers that don't.
        delay = int(data.get("delay_ms") or database.get_meta("scrape_delay_ms") or 1500)
        if "download_files" in data:
            download = bool(data["download_files"])
        else:
            download = database.get_meta("scrape_attachments") != "0"
        if "use_local_pages" in data:
            use_local_pages = bool(data["use_local_pages"])
        else:
            use_local_pages = database.get_meta("use_local_pages") == "1"

        lb_numbers = scraper.plan_range(start_lb, end_lb)

        if not _start_scrape_thread(
            lb_numbers, force=force, delay_ms=delay,
            download=download, use_local_pages=use_local_pages,
        ):
            return jsonify({"ok": False, "error": "A scrape is already running"}), 409
        return jsonify({"ok": True, "total": len(lb_numbers)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/scrape/status", methods=["GET"])
def scrape_status() -> Response:
    """Return current status of the background scrape worker.

    Returns:
        JSON status dict from scraper.get_scrape_status().
    """
    return jsonify(scraper.get_scrape_status())


@bp.route("/api/scrape/stop", methods=["POST"])
def scrape_stop() -> Response:
    """Signal the background scrape worker to stop after the current entry.

    Returns:
        JSON {ok: true}.
    """
    scraper.stop_scrape()
    return jsonify({"ok": True})


@bp.route("/api/scrape/download_pages", methods=["POST"])
def scrape_download_pages():
    """Fetch and cache HTML detail pages for a range of LB numbers.

    Body JSON keys (all optional):
        start_lb (int): First LB number to attempt.  Default 1.
        end_lb   (int): Last LB number (inclusive).  Default: max lb_number
                        in the checksums table.
        force    (bool): Re-download pages that already exist.  Default false.

    Existing ``data/site/detail/LB-{n:05d}.html`` files are skipped unless
    ``force`` is true.  No metadata is parsed and nothing is written to the
    database.

    Returns:
        JSON: {ok: true, total: int}  — number of LB numbers queued.
    """
    try:
        data = request.get_json() or {}
        start_lb = int(data.get("start_lb", 1))
        force = bool(data.get("force", False))
        delay = int(database.get_meta("scrape_delay_ms") or 1500)

        with database.get_connection() as conn:
            max_lb = conn.execute(
                "SELECT MAX(lb_number) FROM checksums"
            ).fetchone()[0] or 1

        end_lb = int(data.get("end_lb", max_lb))
        if end_lb < start_lb:
            return jsonify({"error": "end_lb must be >= start_lb"}), 400

        lb_numbers = list(range(start_lb, end_lb + 1))
        if not _start_download_pages_thread(lb_numbers, force=force, delay_ms=delay):
            return jsonify({"ok": False, "error": "A scrape is already running"}), 409
        return jsonify({"ok": True, "total": len(lb_numbers)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/scrape/private_rescrape", methods=["POST"])
def scrape_private_rescrape() -> Response:
    """Force re-scrape of all currently-Private LBs to detect newly-published pages.

    Uses force=True so LBs with a prior 'missing' result are re-attempted.
    Returns {ok, total} where total is the number of private LBs queued.
    """
    try:
        with database.get_connection() as conn:
            lb_numbers = [
                r[0] for r in conn.execute(
                    "SELECT lb_number FROM lb_master WHERE lb_status='private' "
                        "ORDER BY lb_number"
                ).fetchall()
            ]
        if not lb_numbers:
            return jsonify({"ok": True, "total": 0})
        delay = int(database.get_meta("scrape_delay_ms") or 1500)
        download = database.get_meta("scrape_attachments") != "0"
        use_local_pages = database.get_meta("use_local_pages") == "1"
        if not _start_scrape_thread(
            lb_numbers, force=True, delay_ms=delay,
            download=download, use_local_pages=use_local_pages,
        ):
            return jsonify({"ok": False, "error": "A scrape is already running"}), 409
        return jsonify({"ok": True, "total": len(lb_numbers)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
