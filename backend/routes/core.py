"""Core routes — checksum lookup, status/uptime, activity, DB management (/api/db/*)."""

import logging
import time
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend import importer
from backend.paths import DATA_DIR
from backend.routes import _state as _route_state
from backend.scrape_worker import _start_scrape_thread

_log = logging.getLogger(__name__)

bp = Blueprint("core", __name__)


# ── Checksum Lookup ──────────────────────────────────────────────────────

@bp.route("/api/lookup", methods=["POST"])
def lookup() -> Response:
    """Look up checksums from pasted text and return match results.

    Body: {text: <raw checksum block>}
    Returns:
        JSON with summary and detail match lists, or 400/500 on error.
    """
    try:
        data = request.get_json()
        text = data.get("text", "")
        parsed = database.parse_checksum_text(text)
        if not parsed:
            return jsonify({"error": "No valid checksums found in input"}), 400
        summary, detail = database.lookup_checksums(parsed)
        alias_map = {
            r["alias_lb"]: r["canonical_lb"]
            for r in database.get_lb_aliases()
        }
        for d in detail:
            lb = d["lb_number"]
            d["is_alias_lb"] = lb in alias_map
            d["canonical_lb"] = alias_map.get(lb)
        return jsonify({"summary": summary, "detail": detail})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Database Management ──────────────────────────────────────────────────

@bp.route("/api/status", methods=["GET"])
def api_status() -> Response:
    """Return combined DB and bootleg stats in one round-trip.

    Merges /api/db/stats and /api/bootlegs/stats to halve loopback
    overhead for the GUI status-bar poller (two GETs → one GET).

    Returns:
        JSON dict: all keys from get_stats() plus a 'bootlegs' sub-key
        containing get_bootleg_stats().
    """
    try:
        data = database.get_stats()
        data["bootlegs"] = database.get_bootleg_stats()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/system/uptime", methods=["GET"])
def system_uptime() -> Response:
    """Return how long the backend process has been running.

    Returns:
        JSON dict with uptime_seconds (int) since this Flask process
        started, for confirming whether a restart actually happened
        after a backend code change.
    """
    return jsonify({"uptime_seconds": round(time.monotonic() - _route_state.process_start_time)})


@bp.route("/api/db/stats", methods=["GET"])
def db_stats() -> Response:
    """Return database row counts and metadata statistics.

    Returns:
        JSON dict with counts for entries, checksums, and other DB stats.
    """
    try:
        return jsonify(database.get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/home/stats", methods=["GET"])
def home_stats() -> Response:
    """Return all counts needed by the Home / Dashboard screen in one query.

    Returns:
        JSON with collection_count, wishlist_count, missing_count, bootleg_count,
        checksum_count, latest_lb, last_import, and collection_size (bytes/human/
        computed_at/computing — cached, refreshed in the background when stale).
    """
    try:
        from backend.filer import get_collection_size_stats
        with database.get_connection() as conn:
            collection_count = conn.execute(
                "SELECT COUNT(*) FROM my_collection"
            ).fetchone()[0]
            wishlist_count = conn.execute(
                "SELECT COUNT(*) FROM my_wishlist"
            ).fetchone()[0]
            missing_count = conn.execute(
                "SELECT COUNT(*) FROM lb_master WHERE lb_status='missing'"
            ).fetchone()[0]
            bootleg_count = conn.execute(
                "SELECT COUNT(*) FROM bootleg_titles"
            ).fetchone()[0]
            checksum_count = conn.execute(
                "SELECT COUNT(*) FROM checksums"
            ).fetchone()[0]
            latest_lb = conn.execute(
                "SELECT MAX(lb_number) FROM lb_master"
            ).fetchone()[0] or 0
        last_import = database.get_meta("last_import_date")
        return jsonify({
            "collection_count": collection_count,
            "wishlist_count": wishlist_count,
            "missing_count": missing_count,
            "bootleg_count": bootleg_count,
            "checksum_count": checksum_count,
            "latest_lb": latest_lb,
            "last_import": last_import,
            "collection_size": get_collection_size_stats(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/activity/jobs", methods=["GET"])
def activity_jobs() -> Response:
    """Return every worker's normalized activity, plus recent history.

    TODO-262 / FABLE_ACTIVITY_CENTER.md §2 A1. One poll, no server-side
    polling loop — every adapter's status_getter is a synchronous
    in-memory read, same as ``/api/activity/busy``.

    Returns:
        JSON {busy: bool, jobs: [...]}. See ``backend/activity.py``'s
        module docstring for the per-job record shape.
    """
    from backend import activity

    return jsonify(activity.snapshot())


@bp.route("/api/activity/log", methods=["GET"])
def activity_log() -> Response:
    """Return a unified activity log: DB imports, renames, and forum posts.

    Query params:
        limit: max rows to return (default 20; 0 = unlimited)

    Returns:
        JSON array of {when, action, target, result, type}.
    """
    limit = int(request.args.get("limit", 20))
    rows: list[dict] = []
    try:
        with database.get_connection() as conn:
            for row in conn.execute(
                "SELECT applied_at, zip_filename, rows_added, rows_changed"
                " FROM flat_file_releases"
                " WHERE status='applied' AND applied_at IS NOT NULL"
                " ORDER BY applied_at DESC"
            ):
                added = row[2] or 0
                changed = row[3] or 0
                result_str = f"+{added} rows"
                if changed:
                    result_str += f", ~{changed} updated"
                rows.append({
                    "when": row[0], "action": "DB import",
                    "target": row[1] or "", "result": result_str, "type": "import",
                })
            for row in conn.execute(
                "SELECT renamed_at, lb_number, old_path, new_path"
                " FROM rename_history ORDER BY renamed_at DESC"
            ):
                lb = f"LB-{row[1]:05d}" if row[1] else "—"
                old_name = (row[2] or "").split("/")[-1]
                new_name = (row[3] or "").split("/")[-1]
                rows.append({
                    "when": row[0], "action": "Rename",
                    "target": f"{lb} · {old_name}", "result": new_name, "type": "rename",
                })
            for row in conn.execute(
                "SELECT posted_at, lb_number, subject"
                " FROM forum_posts ORDER BY posted_at DESC"
            ):
                lb = f"LB-{row[1]:05d}" if row[1] else "—"
                rows.append({
                    "when": row[0], "action": "Forum post",
                    "target": lb, "result": row[2] or "", "type": "forum",
                })
        rows.sort(key=lambda x: x["when"] or "", reverse=True)
        if limit > 0:
            rows = rows[:limit]
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/db/missing_lb_numbers", methods=["GET"])
def db_missing_lb_numbers() -> Response:
    """Return a list of LB numbers in the checksums table that have no entries row.

    Returns:
        JSON list of integer LB numbers.
    """
    try:
        return jsonify(database.get_missing_lb_numbers())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/db/import", methods=["POST"])
def db_import() -> Response:
    """Trigger an async import of a flat-file checksum DB.

    Body: {file_path: "/abs/path/to/file"}
    Returns:
        JSON {ok, running} or 404 if file not found.
    """
    try:
        data = request.get_json()
        file_path = data.get("file_path", "")
        path = Path(file_path)
        if not path.exists():
            return jsonify({"error": f"File not found: {file_path}"}), 404

        def on_complete(result):
            if result.get("scrape_queued"):
                # Treat None (never set / DB reset) as enabled — matches UI default.
                # Only "0" disables auto-scrape.
                _val = database.get_meta("auto_scrape")
                auto_scrape = _val is None or _val != "0"
                if auto_scrape:
                    new_lbs = result.get("new_lb_numbers", [])
                    delay = int(database.get_meta("scrape_delay_ms") or 1500)
                    if new_lbs and not _start_scrape_thread(new_lbs, delay_ms=delay):
                        # Not lost: they stay in the scrape_entries backlog and
                        # "Scrape All Missing" (plan_range) picks them up.
                        _log.warning(
                            "db import: auto-scrape of %d new LB(s) skipped — a scrape "
                            "is already running; run Scrape All Missing afterwards",
                            len(new_lbs),
                        )

        if not importer.start_import_async(path, on_complete=on_complete):
            return jsonify({"ok": False, "error": "Import already running"}), 409
        return jsonify({"ok": True, "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/db/import/status", methods=["GET"])
def db_import_status() -> Response:
    """Return current status of the background import worker.

    Returns:
        JSON import status dict from importer.get_import_status().
    """
    try:
        return jsonify(importer.get_import_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/db/settings", methods=["GET", "POST"])
def db_settings() -> Response:
    """Get or update persistent application settings stored in the meta table.

    GET returns a dict of known setting keys and their current values.
    POST body: {key: value, ...} — writes each pair via set_meta().
    Returns:
        JSON settings dict (GET) or {ok: true} (POST).
    """
    try:
        if request.method == "POST":
            data = request.get_json() or {}
            for key, value in data.items():
                database.set_meta(key, str(value))
            return jsonify({"ok": True})
        else:
            keys = ["scrape_attachments", "scrape_delay_ms", "auto_scrape", "use_local_pages",
                    "force_scrape", "search_page_size",
                    "qbt_host", "qbt_port", "qbt_category", "qbt_tags",
                    "tracker_list", "wtrf_board_id", "ui_language",
                    "pipeline_file_mode", "integrity_scan_interval_hours",
                    "file_verify_enabled", "file_verify_interval_hours",
                    "file_verify_budget_seconds", "file_verify_files_per_mount",
                    "scanner_roots", "scanner_excludes"]
            result = {k: database.get_meta(k) for k in keys}
            # Return "set" or "" for web_password — never expose the actual value
            result["web_password"] = "set" if database.get_meta("web_password") else ""
            result["data_dir"] = str(DATA_DIR)
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/db/reset", methods=["POST"])
def db_reset() -> Response:
    """Wipe all master-data tables and reinitialise the schema from scratch.

    Uses MASTER_TABLES as the canonical list so the reset stays in sync
    as new master tables are added.  User data (collection, wishlist,
    mounts, routes, rename history, torrents, forum posts, etc.) is
    preserved.

    Returns:
        JSON {ok: true} or 500 on error.
    """
    try:
        with database._write_lock:
            conn = database.get_connection()
            # Drop FTS triggers + virtual table linked to entries.
            # executescript() issues an implicit COMMIT before running.
            fts_script = (
                "PRAGMA foreign_keys=OFF;"
                "DROP TRIGGER IF EXISTS entries_fts_insert;"
                "DROP TRIGGER IF EXISTS entries_fts_update;"
                "DROP TRIGGER IF EXISTS entries_fts_delete;"
                "DROP TABLE IF EXISTS entries_fts;"
            )
            master_drops = "".join(
                f"DROP TABLE IF EXISTS {tbl};"
                for tbl in database.MASTER_TABLES
            )
            conn.executescript(fts_script + master_drops)
            # Wipe master meta keys; leave user meta keys intact.
            placeholders = ",".join("?" * len(database.MASTER_META_KEYS))
            conn.execute(
                f"DELETE FROM meta WHERE key IN ({placeholders})",
                tuple(database.MASTER_META_KEYS),
            )
            conn.commit()
            # executescript() doesn't restore PRAGMAs — re-enable explicitly
            # before init_db() recreates the schema.
            conn.execute("PRAGMA foreign_keys=ON")
            database.init_db()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NOTE: /api/db/check_update removed — replaced by /api/flat_file/discover
# (old route called scraper.check_for_update() which only counted LB links on
# the bynumber page and missed corrections/checksum additions).
# See backend/flat_file.py for the full discover→download→diff→apply pipeline.
