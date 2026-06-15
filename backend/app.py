import base64
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import UTC
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    request,
    send_file,
    send_from_directory,
    stream_with_context,
)
from flask_cors import CORS

from backend import archive_org as _archive_org
from backend import (
    bobdylan_scraper,
    bootleg_scraper,
    checksum_utils,
    importer,
    scheduler,
    scraper,
    sharing,
    site_crawler,
)
from backend import db as database
from backend import setlistfm as setlistfm_mod
from backend.paths import (
    BATCH_VERIFY_DB_PATH,
    DATA_DIR,
    SITE_DIR,
    SITE_FILES_DIR,
    attachment_path,
    find_lbdir_attachment,
)

_log = logging.getLogger(__name__)

# Rate-limit for /api/db/backup (#3): reject if last manual backup was < 60 s ago
_last_backup_at: float = 0.0
_backup_lock = threading.Lock()

_reconcile_lock = threading.Lock()  # prevents concurrent lb_master reconcile runs

_scrape_thread = None

_update_state = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "latest_version": None,
    "update_available": False,
}
_update_lock = threading.Lock()

_data_dl_state = {
    "status": "idle",
    "progress": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "message": "",
    "files_extracted": [],
    "files_skipped": [],
}
_data_dl_lock = threading.Lock()

# ── Restart callback (set by main.py so only the Flask server restarts) ───────
_restart_callback = None


def set_restart_callback(cb) -> None:
    """Register a function that main.py calls to restart the Flask server in-process.

    When set, admin_restart invokes this instead of os.execv so the GUI is not affected.
    If not set (standalone/Windows), os.execv restarts the whole process as before.
    """
    global _restart_callback
    _restart_callback = cb


# ── FEAT-14: DB Editor table classification ───────────────────────────────────
_DBEDIT_READONLY = frozenset({"entries_fts"})
_DBEDIT_AUDIT    = frozenset({"entry_changes", "integrity_events"})
_DBEDIT_WARN     = frozenset({"checksums", "entries", "entry_files"})


def _dbedit_db_path() -> str:
    """Return the SQLite path for the current dbedit request based on ?db= param."""
    if request.args.get("db", "").lower() == "batchverify":
        return str(BATCH_VERIFY_DB_PATH)
    return str(database.DB_PATH)


def _dbedit_is_batchverify() -> bool:
    return request.args.get("db", "").lower() == "batchverify"

_spectro_state = {
    "status":    "idle",
    "current":   "",
    "done":      0,
    "total":     0,
    "errors":    [],
    "skipped":   0,
    "stop_requested": False,
}
_spectro_lock = __import__("threading").Lock()

_fp_build_state = {
    "status": "idle", "current": "", "done": 0,
    "total": 0, "skipped": 0, "errors": [], "stop_requested": False,
    "queue_preview": [],
}
_fp_build_lock = threading.Lock()
_fp_build_stop = threading.Event()

_fp_dup_state: dict = {"status": "idle", "message": "", "results": [], "stop_requested": False}
_fp_dup_lock  = threading.Lock()
_fp_dup_stop  = threading.Event()

_fp_id_state: dict = {
    "status": "idle", "current": "", "done": 0, "total": 0,
    "errors": [], "results": [], "stop_requested": False,
}
_fp_id_lock = threading.Lock()
_fp_id_stop = threading.Event()


def _find_lbdir_in_folder(folder: Path) -> "Path | None":
    """Return the first lbdir*.txt (or LBF-*-lbdir.txt) found in folder, or None."""
    if not folder.exists():
        return None
    for f in folder.iterdir():
        if f.is_file() and 'lbdir' in f.name.lower() and f.suffix.lower() == '.txt':
            return f
    return None


def create_app() -> Flask:
    """Create and configure the Flask application."""
    import backend.startup_log as _slog
    _slog.t("Flask: create_app start")
    app = Flask(__name__)
    CORS(app)

    # Process start time, used by /api/system/uptime and /api/admin/status to
    # show how long the backend has been running (TODO-112).
    _process_start_time = time.monotonic()

    # ── Web GUI basic-auth (TODO-064) ─────────────────────────────────────────
    # Protects /web/* and /frontend/* when meta key web_password is set.
    # /api/* routes are intentionally left open (desktop app calls them directly).
    @app.before_request
    def _enforce_web_auth() -> "Response | None":
        path = request.path
        if not (path.startswith("/web/") or path.startswith("/frontend/")):
            return None
        try:
            pw = database.get_meta("web_password") or ""
        except Exception:
            pw = ""
        if not pw:
            return None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode("utf-8", errors="replace")
                _, _, supplied = decoded.partition(":")
                if supplied == pw:
                    return None
            except Exception:
                pass
        return Response(
            "Authentication required",
            401,
            {"WWW-Authenticate": 'Basic realm="LosslessBob Web"'},
        )

    _slog.t("Flask: init_db start")
    database.init_db()
    _slog.t("Flask: init_db done")
    from backend import fingerprint as _fp_mod
    _fp_mod.init_fp_db()
    _slog.t("Flask: init_fp_db done")
    _slog.t("Flask: start_file_watcher start")
    scheduler.start_file_watcher()
    scheduler.start_collection_watcher()
    scheduler.start_integrity_scan_scheduler()
    _slog.t("Flask: routes registering")

    # ── Checksum Lookup ──────────────────────────────────────────────────────

    @app.route("/api/lookup", methods=["POST"])
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

    @app.route("/api/lookup/scan_folders", methods=["POST"])
    def lookup_scan_folders() -> Response:
        """Recursively scan folders for checksum sidecar files and return combined text.

        Body: {folders: ["/abs/path", ...]}
        Returns:
            JSON {content: str, files: [str, ...]}
        """
        _CHECKSUM_EXTS = {".ffp", ".md5", ".st5", ".sha1"}
        try:
            data = request.get_json(force=True) or {}
            folders = data.get("folders", [])
            all_content: list[str] = []
            files_found: list[str] = []
            for folder in folders:
                p = Path(folder)
                if not p.is_dir():
                    continue
                for f in sorted(p.rglob("*")):
                    if f.is_file() and f.suffix.lower() in _CHECKSUM_EXTS:
                        try:
                            all_content.append(f.read_text(errors="replace"))
                            files_found.append(str(f))
                        except OSError:
                            pass
            return jsonify({"content": "\n".join(all_content), "files": files_found})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Database Management ──────────────────────────────────────────────────

    @app.route("/api/status", methods=["GET"])
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

    @app.route("/api/system/uptime", methods=["GET"])
    def system_uptime() -> Response:
        """Return how long the backend process has been running.

        Returns:
            JSON dict with uptime_seconds (int) since this Flask process
            started, for confirming whether a restart actually happened
            after a backend code change.
        """
        return jsonify({"uptime_seconds": round(time.monotonic() - _process_start_time)})

    @app.route("/api/db/stats", methods=["GET"])
    def db_stats() -> Response:
        """Return database row counts and metadata statistics.

        Returns:
            JSON dict with counts for entries, checksums, and other DB stats.
        """
        try:
            return jsonify(database.get_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/home/stats", methods=["GET"])
    def home_stats() -> Response:
        """Return all counts needed by the Home / Dashboard screen in one query.

        Returns:
            JSON with collection_count, wishlist_count, missing_count, bootleg_count,
            checksum_count, latest_lb, and last_import.
        """
        try:
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
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/activity/busy", methods=["GET"])
    def activity_busy() -> Response:
        """Report whether any background worker is currently running.

        Polls the in-memory status of the import, scrape, bootleg-scrape,
        integrity-scan, file-job, and update/data-download workers.

        Returns:
            JSON {busy: bool, activity: str|None}. ``activity`` is a short
            machine-readable key identifying the first running job found,
            or None if every worker is idle.
        """
        from backend import integrity_monitor
        from backend.filer import get_file_job_status

        checks = [
            (importer.get_import_status(), "importing"),
            (scraper.get_scrape_status(), "scraping"),
            (bootleg_scraper.get_scrape_status(), "scraping_bootlegs"),
            (integrity_monitor.get_scan_status(), "scanning"),
            (get_file_job_status(), "filing"),
        ]
        for status, activity in checks:
            if status.get("running"):
                return jsonify({"busy": True, "activity": activity})
        with _update_lock:
            if _update_state.get("status", "idle") != "idle":
                return jsonify({"busy": True, "activity": "updating_app"})
        with _data_dl_lock:
            if _data_dl_state.get("status", "idle") != "idle":
                return jsonify({"busy": True, "activity": "downloading_data"})
        return jsonify({"busy": False, "activity": None})

    @app.route("/api/activity/log", methods=["GET"])
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

    @app.route("/api/db/missing_lb_numbers", methods=["GET"])
    def db_missing_lb_numbers() -> Response:
        """Return a list of LB numbers in the checksums table that have no entries row.

        Returns:
            JSON list of integer LB numbers.
        """
        try:
            return jsonify(database.get_missing_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/import", methods=["POST"])
    def db_import() -> Response:
        """Trigger an async import of a flat-file checksum DB.

        Body: {file_path: "/abs/path/to/file"}
        Returns:
            JSON {ok, running} or 404 if file not found.
        """
        try:
            if importer.get_import_status().get("running"):
                return jsonify({"ok": False, "error": "Import already running"}), 409

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
                        _start_scrape_thread(new_lbs, delay_ms=delay)

            importer.start_import_async(path, on_complete=on_complete)
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/import/status", methods=["GET"])
    def db_import_status() -> Response:
        """Return current status of the background import worker.

        Returns:
            JSON import status dict from importer.get_import_status().
        """
        try:
            return jsonify(importer.get_import_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/settings", methods=["GET", "POST"])
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
                        "force_scrape", "search_page_size", "github_repo", "data_zip_url",
                        "qbt_host", "qbt_port", "qbt_category", "qbt_tags",
                        "tracker_list", "wtrf_board_id", "ui_language",
                        "pipeline_file_mode", "integrity_scan_interval_hours"]
                result = {k: database.get_meta(k) for k in keys}
                # Return "set" or "" for web_password — never expose the actual value
                result["web_password"] = "set" if database.get_meta("web_password") else ""
                result["data_dir"] = str(DATA_DIR)
                return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/reset", methods=["POST"])
    def db_reset() -> Response:
        """Drop all checksum/entry tables and reinitialise the schema from scratch.

        Preserves collection, wishlist, and personal metadata.
        Returns:
            JSON {ok: true} or 500 on error.
        """
        try:
            with database._write_lock:
                conn = database.get_connection()
                # Disable FK enforcement for the duration of the drop so that
                # my_collection's FK on entries(lb_number) doesn't block the drop.
                conn.executescript(
                    "PRAGMA foreign_keys=OFF;"
                    "DROP TABLE IF EXISTS entry_changes;"
                    "DROP TABLE IF EXISTS rename_history;"
                    "DROP TABLE IF EXISTS torrents;"
                    "DROP TRIGGER IF EXISTS entries_fts_insert;"
                    "DROP TRIGGER IF EXISTS entries_fts_update;"
                    "DROP TRIGGER IF EXISTS entries_fts_delete;"
                    "DROP TABLE IF EXISTS entries_fts;"
                    "DROP TABLE IF EXISTS checksums;"
                    "DROP TABLE IF EXISTS entries;"
                    "DROP TABLE IF EXISTS entry_files;"
                    "DROP TABLE IF EXISTS meta;"
                )
                # executescript() doesn't restore PRAGMAs — re-enable explicitly on
                # the persistent connection before init_db() recreates the schema.
                conn.execute("PRAGMA foreign_keys=ON")
                database.init_db()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # NOTE: /api/db/check_update removed — replaced by /api/flat_file/discover
    # (old route called scraper.check_for_update() which only counted LB links on
    # the bynumber page and missed corrections/checksum additions).
    # See backend/flat_file.py for the full discover→download→diff→apply pipeline.

    # ── Flat file update pipeline ─────────────────────────────────────────────

    @app.route("/api/flat_file/discover", methods=["GET"])
    def flat_file_discover() -> Response:
        """Live check for a new flat-file release on the LosslessBob download page."""
        from . import flat_file as ff
        try:
            result = ff.discover_flat_file_release()
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/download/<int:release_id>", methods=["POST"])
    def flat_file_download(release_id):
        """Download the zip for a detected release (may be long-running)."""
        from . import flat_file as ff
        try:
            path = ff.download_flat_file_release(release_id)
            return jsonify({"path": str(path), "release_id": release_id})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/diff/<int:release_id>", methods=["GET"])
    def flat_file_diff(release_id):
        """Return diff counts (rows_added/changed/removed) without applying."""
        from . import flat_file as ff
        try:
            return jsonify(ff.diff_flat_file_release(release_id))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/apply/<int:release_id>", methods=["POST"])
    def flat_file_apply(release_id):
        """Apply a downloaded flat-file release to the main database."""
        from . import flat_file as ff
        try:
            result = ff.apply_flat_file_release(release_id)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/defer/<int:release_id>", methods=["POST"])
    def flat_file_defer(release_id):
        """Defer prompting for a release. Body: {days: int} or {until_next: true}."""
        from . import flat_file as ff
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

    @app.route("/api/flat_file/releases", methods=["GET"])
    def flat_file_releases():
        """List all flat file release history rows, newest first."""
        from . import flat_file as ff
        try:
            return jsonify(ff.get_releases())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/changelog/<int:release_id>", methods=["GET"])
    def flat_file_changelog(release_id):
        """Paginated changelog for a release. Query params: limit, offset."""
        from . import flat_file as ff
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        try:
            return jsonify(ff.get_release_changelog(release_id, limit, offset))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Entry Detail & Attachments ───────────────────────────────────────────

    @app.route("/api/entry/<int:lb_number>", methods=["GET"])
    def get_entry(lb_number: int) -> Response:
        """Return metadata for a single LB entry.

        Args:
            lb_number: The LB number to look up.

        Returns:
            JSON dict with entry fields, or 404 if not found.
        """
        try:
            data = database.get_entry(lb_number)
            if not data:
                return jsonify({"error": "Entry not found"}), 404
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entry/<int:lb_number>/files", methods=["GET"])
    def get_entry_files(lb_number: int) -> Response:
        """Return all entry_files rows for a single LB entry.

        Args:
            lb_number: The LB number whose files to retrieve.

        Returns:
            JSON list of entry_files dicts.
        """
        try:
            with database.get_connection() as conn:
                files = conn.execute(
                    "SELECT * FROM entry_files WHERE lb_number=?", (lb_number,)
                ).fetchall()
            return jsonify([dict(f) for f in files])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/attachment/<int:lb_number>/<path:filename>", methods=["GET"])
    def get_attachment(lb_number: int, filename: str) -> Response:
        """Serve a downloaded attachment file for an LB entry.

        Args:
            lb_number: The LB number owning the attachment.
            filename: Clean filename (no LBF- prefix); looked up in entry_files.

        Returns:
            The file contents, or 404 if not found.
        """
        # filename is the clean_name (no LBF- prefix); look up original filename
        row = database.get_connection().execute(
            "SELECT filename FROM entry_files WHERE lb_number=? AND clean_name=?",
            (lb_number, filename),
        ).fetchone()
        if not row:
            abort(404)
        file_path = attachment_path(row["filename"])
        if not file_path.exists():
            abort(404)
        return send_file(str(file_path))

    @app.route("/api/attachments/reconcile", methods=["POST"])
    def attachments_reconcile() -> Response:
        """Mark entry_files.downloaded=1 for rows present in site_inventory.

        Returns:
            JSON {updated: N} with the number of rows updated.
        """
        try:
            with database.get_connection() as conn:
                cur = conn.execute(
                    """
                    UPDATE entry_files
                    SET downloaded = 1
                    WHERE downloaded = 0
                      AND file_url IN (
                          SELECT url FROM site_inventory WHERE status = 'downloaded'
                      )
                    """
                )
                updated = cur.rowcount
            return jsonify({"updated": updated})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/attachments/cached", methods=["GET"])
    def attachments_cached() -> Response:
        """Return downloaded entry_files grouped by LB number, plus total entry count.

        Returns:
            JSON {entries: [{lb_number, files: [{filename, clean_name}], lb_status}],
                  total: int}.
        """
        try:
            conn = database.get_connection()
            rows = conn.execute(
                """
                SELECT ef.lb_number, ef.filename, ef.clean_name, ef.downloaded, lm.lb_status
                FROM entry_files ef
                LEFT JOIN lb_master lm ON lm.lb_number = ef.lb_number
                WHERE ef.downloaded = 1
                ORDER BY ef.lb_number, ef.clean_name
                """
            ).fetchall()
            grouped: dict = {}
            for r in rows:
                lb = r["lb_number"]
                if lb not in grouped:
                    grouped[lb] = {
                        "lb_number": lb,
                        "files": [],
                        "lb_status": r["lb_status"],
                    }
                grouped[lb]["files"].append(
                    {"filename": r["filename"], "clean_name": r["clean_name"], "downloaded": r["downloaded"]}
                )
            all_entries = [v for _, v in sorted(grouped.items())]
            total = conn.execute(
                "SELECT COUNT(DISTINCT lb_number) FROM checksums"
            ).fetchone()[0]
            return jsonify({"entries": all_entries, "total": total})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entry/<int:lb_number>/changes", methods=["GET"])
    def entry_changes(lb_number: int) -> Response:
        """Return field-level change history for a single LB entry.

        Args:
            lb_number: The LB number to query.

        Returns:
            JSON list of {field, old_value, new_value, changed_at} dicts,
            ordered by changed_at DESC. Query param: limit (default 50).
        """
        try:
            limit = int(request.args.get("limit", 50))
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT field, old_value, new_value, changed_at "
                "FROM entry_changes WHERE lb_number=? "
                "ORDER BY changed_at DESC LIMIT ?",
                (lb_number, limit)
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entry/<int:lb_number>/scrape", methods=["POST"])
    def scrape_entry_route(lb_number: int) -> Response:
        """Scrape (or force re-scrape) a single LB entry from the source site.

        Args:
            lb_number: The LB number to scrape.

        Body: {force: bool}
        Returns:
            JSON result dict from scraper.scrape_entry().
        """
        try:
            data = request.get_json() or {}
            force = data.get("force", False)
            download = database.get_meta("scrape_attachments") != "0"
            use_local_pages = database.get_meta("use_local_pages") == "1"
            result = scraper.scrape_entry(lb_number, force=force, download_files=download, use_local_pages=use_local_pages)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Search ───────────────────────────────────────────────────────────────

    @app.route("/api/search", methods=["GET"])
    def search() -> Response:
        """Search entries by keyword, field filter, and optional year.

        Query params: q (text), field (all|title|location|etc.), year (int).
        Returns:
            JSON list of matching entry dicts.
        """
        # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
        # performs in-memory sorting on the full result set.
        try:
            q = request.args.get("q", "")
            field = request.args.get("field", "all")
            year_str = request.args.get("year")
            year = int(year_str) if year_str else None
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
            _SEARCH_SORT_COLS = {
                "lb_number": "e.lb_number",
                "date_str":  "e.date_str",
                "location":  "e.location",
                "lb_status": (
                    "CASE lm.lb_status WHEN 'public' THEN 0 "
                    "WHEN 'private' THEN 1 WHEN 'missing' THEN 2 END"
                ),
            }
            results = database.search_entries(q, field, year=year)
            if sort_col and sort_col in _SEARCH_SORT_COLS:
                reverse = sort_dir == "DESC"
                key_map = {
                    "lb_number": lambda r: r.get("lb_number") or 0,
                    "date_str":  lambda r: (r.get("date_str") or "").lower(),
                    "location":  lambda r: (r.get("location") or "").lower(),
                    "lb_status": lambda r: {"public": 0, "private": 1,
                                            "missing": 2}.get(
                                           r.get("lb_status") or "", 99),
                }
                results.sort(key=key_map[sort_col], reverse=reverse)
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/search/years", methods=["GET"])
    def search_years() -> Response:
        """Return the distinct years present in the entries table.

        Returns:
            JSON list of year strings for populating filter dropdowns.
        """
        try:
            return jsonify(database.get_distinct_years())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/checksums/xref_lb_numbers", methods=["GET"])
    def xref_lb_numbers() -> Response:
        """Return LB numbers that have at least one xref checksum record.

        Returns:
            JSON list of integer LB numbers.
        """
        try:
            return jsonify(database.get_xref_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/checksums/xref_map", methods=["GET"])
    def xref_map() -> Response:
        """Return a mapping of xref identifiers to their canonical LB numbers.

        Returns:
            JSON dict {xref_id: lb_number}.
        """
        try:
            return jsonify(database.get_xref_map())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entries/year/<year>", methods=["GET"])
    def entries_by_year(year: str) -> Response:
        """Return all entries for a given year string.

        Args:
            year: The year to filter by (e.g. "1979").

        Returns:
            JSON list of entry dicts for that year.
        """
        try:
            results = database.get_entries_by_year(year)
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entries/reclassify", methods=["POST"])
    def entries_reclassify() -> Response:
        """Re-classify all entries lb_category using bobdylan_shows + dylan_performances + keywords.

        Curator-only. Returns classification counts.
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            counts = database.classify_entry_categories()
            return jsonify({"ok": True, **counts})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── My Collection ────────────────────────────────────────────────────────

    @app.route("/api/collection", methods=["GET"])
    def collection_list() -> Response:
        """Return all entries in the user's collection.

        Returns:
            JSON list of my_collection row dicts.
        """
        # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
        # performs in-memory sorting on the full result set.
        try:
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
            _COLL_SORT_COLS = {
                "lb_number":   lambda r: r.get("lb_number") or 0,
                "date_str":    lambda r: (r.get("date_str") or "").lower(),
                "location":    lambda r: (r.get("location") or "").lower(),
                "folder_name": lambda r: (r.get("folder_name") or "").lower(),
                "lb_status":   lambda r: {"public": 0, "private": 1,
                                          "missing": 2}.get(
                                         r.get("lb_status") or "", 99),
            }
            results = database.get_collection()
            if sort_col and sort_col in _COLL_SORT_COLS:
                results.sort(key=_COLL_SORT_COLS[sort_col],
                             reverse=(sort_dir == "DESC"))
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection", methods=["POST"])
    def collection_add() -> Response:
        """Add an LB entry to the user's collection.

        Body: {lb_number, folder_name, disk_path, notes?}
        Returns:
            JSON {ok, added} or 400 if required fields are missing.
        """
        try:
            data = request.get_json() or {}
            lb = data.get("lb_number")
            folder_name = data.get("folder_name", "")
            disk_path = data.get("disk_path", "")
            notes = data.get("notes")
            if not lb or not folder_name or not disk_path:
                return jsonify({"error": "lb_number, folder_name, disk_path required"}), 400
            added = database.add_to_collection(int(lb), folder_name, disk_path, notes)
            return jsonify({"ok": True, "added": added > 0})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>", methods=["PATCH"])
    def collection_update(lb: int) -> Response:
        """Update fields on an existing collection entry.

        Args:
            lb: The LB number to update.

        Body: {field: value, ...}
        Returns:
            JSON {ok: true}.
        """
        try:
            data = request.get_json() or {}
            database.update_collection(lb, data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>", methods=["DELETE"])
    def collection_delete(lb: int) -> Response:
        """Remove an LB entry from the user's collection.

        Args:
            lb: The LB number to remove.

        Returns:
            JSON {ok: true}.
        """
        try:
            database.delete_from_collection(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/missing", methods=["GET"])
    def collection_missing() -> Response:
        """Return collection entries whose disk_path no longer exists on disk.

        Returns:
            JSON list of collection row dicts with missing paths.
        """
        # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
        # performs in-memory sorting on the full result set.
        try:
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
            _MISS_SORT_COLS = {
                "lb_number": lambda r: r.get("lb_number") or 0,
                "date_str":  lambda r: (r.get("date_str") or "").lower(),
                "location":  lambda r: (r.get("location") or "").lower(),
                "lb_status": lambda r: {"public": 0, "private": 1,
                                        "missing": 2}.get(
                                       r.get("lb_status") or "", 99),
            }
            results = database.get_missing_from_collection()
            if sort_col and sort_col in _MISS_SORT_COLS:
                results.sort(key=_MISS_SORT_COLS[sort_col],
                             reverse=(sort_dir == "DESC"))
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/search", methods=["GET"])
    def collection_search() -> Response:
        """Search the user's collection by keyword.

        Query params: q (text).
        Returns:
            JSON list of matching collection row dicts.
        """
        try:
            q = request.args.get("q", "")
            return jsonify(database.search_collection(q))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/lb_numbers", methods=["GET"])
    def collection_lb_numbers() -> Response:
        """Return all LB numbers currently in the user's collection.

        Returns:
            JSON list of integer LB numbers.
        """
        try:
            return jsonify(database.get_owned_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-03: Personal Metadata ───────────────────────────────────────────

    @app.route("/api/collection/<int:lb>/meta", methods=["GET"])
    def get_coll_meta(lb: int) -> Response:
        """Return personal metadata for a collection entry.

        Args:
            lb: The LB number to retrieve metadata for.

        Returns:
            JSON dict of personal metadata key/value pairs.
        """
        try:
            return jsonify(database.get_collection_meta(lb))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>/meta", methods=["POST"])
    def set_coll_meta(lb: int) -> Response:
        """Set personal metadata for a collection entry.

        Args:
            lb: The LB number to update metadata for.

        Body: {key: value, ...}
        Returns:
            JSON {ok: true}.
        """
        try:
            database.set_collection_meta(lb, request.get_json() or {})
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>/listen", methods=["POST"])
    def log_listen(lb: int) -> Response:
        """Increment the listen count for a collection entry.

        Args:
            lb: The LB number to log a listen for.

        Returns:
            JSON {ok: true}.
        """
        try:
            database.increment_listen_count(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Audio info cache (in-memory, keyed by disk_path + mtime fingerprint) ──
    _audioinfo_cache: dict = {}

    @app.route("/api/collection/<int:lb>/audioinfo", methods=["GET"])
    def collection_audioinfo(lb: int) -> Response:
        """Return audio format / bit-depth / sample-rate for a collection entry.

        Args:
            lb: LB number of the collection entry.

        Returns:
            JSON {format, bit_depth, sample_rate, mixed, files_probed, offline?}.
        """
        import json as _json
        import os
        import subprocess

        import soundfile as sf

        _empty = {"format": None, "bit_depth": None, "sample_rate": None,
                  "mixed": False, "files_probed": 0}
        try:
            with database.get_connection() as conn:
                row = conn.execute(
                    "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb,)
                ).fetchone()
            if not row or not row["disk_path"]:
                return jsonify(_empty)
            disk_path = row["disk_path"]
            if not os.path.isdir(disk_path):
                return jsonify({**_empty, "offline": True})

            AUDIO_EXTS = {'.flac', '.wav', '.aiff', '.aif', '.shn', '.ape', '.ogg', '.mp3'}
            audio_files = [
                os.path.join(root, f)
                for root, _, files in os.walk(disk_path)
                for f in files
                if os.path.splitext(f.lower())[1] in AUDIO_EXTS
            ]
            if not audio_files:
                return jsonify(_empty)

            try:
                mtime_sum = sum(int(os.path.getmtime(f) * 1000) for f in audio_files[:20])
            except Exception:
                mtime_sum = 0
            cache_key = (disk_path, mtime_sum)
            if cache_key in _audioinfo_cache:
                return jsonify(_audioinfo_cache[cache_key])

            sample = audio_files[:5]
            results = []
            for fpath in sample:
                ext = os.path.splitext(fpath.lower())[1]
                fmt = bit_depth = rate = None
                try:
                    info = sf.info(fpath)
                    fmt = info.format.upper()
                    rate = info.samplerate
                    st = info.subtype.upper()
                    if 'PCM_16' in st:
                        bit_depth = 16
                    elif 'PCM_24' in st:
                        bit_depth = 24
                    elif 'PCM_32' in st:
                        bit_depth = 32
                    elif 'FLOAT' in st or 'DOUBLE' in st:
                        bit_depth = 32
                    elif '8' in st:
                        bit_depth = 8
                except Exception:
                    try:
                        out = subprocess.run(
                            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                             '-show_streams', '-select_streams', 'a:0', fpath],
                            capture_output=True, text=True, timeout=10,
                        )
                        if out.returncode == 0:
                            streams = _json.loads(out.stdout).get('streams', [])
                            if streams:
                                s = streams[0]
                                fmt = ext.lstrip('.').upper()
                                rate = int(s.get('sample_rate', 0)) or None
                                bits = s.get('bits_per_raw_sample') or s.get('bits_per_sample')
                                bit_depth = int(bits) if bits else None
                    except Exception:
                        pass
                if fmt:
                    results.append({'format': fmt, 'bit_depth': bit_depth, 'sample_rate': rate})

            if not results:
                return jsonify({**_empty, "files_probed": len(sample)})

            fmts   = {r['format']      for r in results if r['format']}
            depths = {r['bit_depth']   for r in results if r['bit_depth']}
            rates  = {r['sample_rate'] for r in results if r['sample_rate']}
            mixed  = len(fmts) > 1 or len(depths) > 1 or len(rates) > 1
            result = {
                "format":       sorted(fmts)[0]   if fmts   else None,
                "bit_depth":    sorted(depths)[0] if depths else None,
                "sample_rate":  round(sorted(rates)[0] / 1000, 1) if rates else None,
                "mixed":        mixed,
                "files_probed": len(sample),
            }
            _audioinfo_cache[cache_key] = result
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-04: Wishlist ────────────────────────────────────────────────────

    @app.route("/api/wishlist", methods=["GET"])
    def wishlist_list() -> Response:
        """Return all entries in the user's wishlist.

        Returns:
            JSON list of wishlist row dicts.
        """
        try:
            return jsonify(database.get_wishlist())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/wishlist", methods=["POST"])
    def wishlist_add() -> Response:
        """Add an LB entry to the user's wishlist.

        Body: {lb_number, priority?, notes?}
        Returns:
            JSON {ok, added} or 400 if lb_number is missing.
        """
        try:
            data = request.get_json() or {}
            lb = data.get("lb_number")
            if not lb:
                return jsonify({"error": "lb_number required"}), 400
            added = database.add_to_wishlist(int(lb), data.get("priority", 3), data.get("notes"))
            return jsonify({"ok": True, "added": added > 0})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/wishlist/<int:lb>", methods=["PATCH"])
    def wishlist_update(lb: int) -> Response:
        """Update priority and/or notes on a wishlist entry.

        Body: {priority?, notes?}
        Returns:
            JSON {ok: true}.
        """
        try:
            data = request.get_json() or {}
            database.update_wishlist(lb, data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/wishlist/<int:lb>", methods=["DELETE"])
    def wishlist_remove(lb: int) -> Response:
        """Remove an LB entry from the user's wishlist.

        Args:
            lb: The LB number to remove.

        Returns:
            JSON {ok: true}.
        """
        try:
            database.remove_from_wishlist(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-05: Duplicate Detector ──────────────────────────────────────────

    @app.route("/api/collection/duplicates", methods=["GET"])
    def collection_duplicates() -> Response:
        """Return collection entries that share the same LB number (duplicates).

        Returns:
            JSON list of duplicate collection row dicts.
        """
        try:
            return jsonify(database.get_collection_duplicates())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/prefetch", methods=["GET"])
    def collection_prefetch() -> Response:
        """Return all data needed by the Collection screen in a single request.

        Bundles collection, missing, fingerprints, wishlist, duplicates,
        forum_posts, torrents, xref_lb_numbers, and years so the GUI only
        needs one round-trip to warm its React Query cache.

        Returns:
            JSON dict with one key per dataset.
        """
        try:
            torrents = database.get_all_torrents()
            for row in torrents:
                row["source_folder_exists"] = (
                    bool(row.get("source_folder"))
                    and Path(row["source_folder"]).is_dir()
                )
                row["torrent_file_exists"] = (
                    bool(row.get("torrent_path"))
                    and Path(row["torrent_path"]).exists()
                )
            try:
                from backend import fingerprint as _fp
                fp_conn = _fp._get_fp_conn()
                fp_rows = fp_conn.execute(
                    "SELECT lb_number, SUM(n_hashes) AS n "
                    "FROM audio_tracks GROUP BY lb_number"
                ).fetchall()
                fingerprints: dict = {str(r["lb_number"]): r["n"] for r in fp_rows}
            except Exception:
                fingerprints = {}
            return jsonify({
                "collection":     database.get_collection(),
                "missing":        database.get_missing_from_collection(),
                "fingerprints":   fingerprints,
                "wishlist":       database.get_wishlist(),
                "duplicates":     database.get_collection_duplicates(),
                "forum_posts":    database.get_all_forum_posts(),
                "torrents":       torrents,
                "xref_lb_numbers": database.get_xref_lb_numbers(),
                "years":          database.get_distinct_years(),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-13: Granular Collection Data Management ─────────────────────────

    @app.route("/api/collection/purge", methods=["POST"])
    def collection_purge() -> Response:
        """Purge all rows from a named user-data table.

        Body: {scope: collection|wishlist|personal_meta|integrity_events|entry_changes}
        Returns:
            JSON {ok, scope} or 400 for unknown scope.
        """
        try:
            scope = (request.get_json() or {}).get("scope", "collection")
            dispatch = {
                "collection":       database.purge_collection,
                "wishlist":         database.purge_wishlist,
                "personal_meta":    database.purge_collection_meta,
                "integrity_events": database.purge_integrity_events,
                "entry_changes":    database.purge_entry_changes,
            }
            if scope not in dispatch:
                return jsonify({"error": f"Unknown scope: {scope}"}), 400
            dispatch[scope]()
            return jsonify({"ok": True, "scope": scope})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/rename_history/purge", methods=["POST"])
    def purge_rename_history() -> Response:
        """Purge all rows from rename_history (lookup history)."""
        try:
            with database._write_lock:
                conn = database.get_connection()
                conn.execute("DELETE FROM rename_history")
                conn.commit()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/flat_file/purge", methods=["POST"])
    def purge_flat_file_history() -> Response:
        """Purge all flat_file_releases and flat_file_changelog rows (import log)."""
        try:
            with database._write_lock:
                conn = database.get_connection()
                conn.execute("DELETE FROM flat_file_changelog")
                conn.execute("DELETE FROM flat_file_releases")
                conn.commit()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/scraper/purge", methods=["POST"])
    def purge_scraper_cache() -> Response:
        """Purge all scrape_sessions and site_inventory rows (scraper cache)."""
        try:
            with database._write_lock:
                conn = database.get_connection()
                conn.execute("DELETE FROM site_inventory")
                conn.execute("DELETE FROM scrape_sessions")
                conn.commit()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/purge", methods=["POST"])
    def purge_fingerprint_cache() -> Response:
        """Delete the fingerprints.db file (fingerprint cache)."""
        try:
            import os

            from backend.paths import FP_DB_PATH
            if FP_DB_PATH.exists():
                os.remove(FP_DB_PATH)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/purge/stats", methods=["GET"])
    def purge_stats() -> Response:
        """Return row counts for each purgeable data group, plus recoverable disk bytes."""
        try:
            conn = database.get_connection()

            def count(table: str) -> int:
                return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            lookup = count("rename_history")
            import_log = count("flat_file_releases") + count("flat_file_changelog")
            scraper = count("scrape_sessions") + count("site_inventory")
            collection_rows = (
                count("my_collection") + count("my_wishlist") + count("collection_meta")
                + count("integrity_events") + count("entry_changes")
            )

            fp_count = 0
            try:
                from backend import fingerprint as _fp
                fp_count = _fp.get_fp_stats().get("track_count", 0)
            except Exception:
                pass

            # Recoverable disk bytes: scraper HTML cache + fingerprint DB
            from backend.paths import FP_DB_PATH, SITE_DIR
            recoverable = 0
            if SITE_DIR.exists():
                recoverable += sum(f.stat().st_size for f in SITE_DIR.rglob("*") if f.is_file())
            if FP_DB_PATH.exists():
                recoverable += FP_DB_PATH.stat().st_size

            return jsonify({
                "lookup_history":    lookup,
                "import_log":        import_log,
                "scraper_cache":     scraper,
                "fingerprint_cache": fp_count,
                "all_user_data":     lookup + import_log + scraper + fp_count + collection_rows,
                "recoverable_bytes": recoverable,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/collection/delete_bulk", methods=["POST"])
    def collection_delete_bulk() -> Response:
        """Delete multiple collection entries by LB number in one request.

        Body: {lb_numbers: [int, ...]}
        Returns:
            JSON {ok, deleted} count, or 400 if lb_numbers is empty.
        """
        try:
            lb_numbers = (request.get_json() or {}).get("lb_numbers", [])
            if not lb_numbers:
                return jsonify({"error": "lb_numbers required"}), 400
            deleted = database.delete_collection_entries(
                [int(lb) for lb in lb_numbers]
            )
            return jsonify({"ok": True, "deleted": deleted})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/audit", methods=["GET"])
    def collection_audit() -> Response:
        """Cross-check my_collection against the checksums table.

        Returns:
            JSON {total, missing_checksums, entries:[{lb_number, folder_name,
            disk_path, date_str, location, lb_status}]} listing every
            collection entry that has no checksum rows in the DB.
        """
        try:
            return jsonify(database.audit_collection_checksums())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/export/html", methods=["GET"])
    def collection_export_html() -> Response:
        """Export My Collection as a modern, interactive single-file HTML report.

        The file embeds all entries as JSON and renders via client-side JS:
        live search with highlight, column sorting, status/decade/year filters,
        100-row pagination (adjustable), CSV download, LB# clipboard copy, dark
        mode, and keyboard shortcuts. Handles 16k+ entries without DOM thrashing.

        Returns:
            HTML file attachment (collection.html), fully self-contained.
        """
        try:
            import json as _json
            from datetime import datetime

            rows = database.get_collection()
            entries = []
            for r in rows:
                lb = r.get("lb_number", 0) or 0
                date_str = r.get("date_str", "") or ""
                year = date_str[:4] if len(date_str) >= 4 and date_str[:4].isdigit() else ""
                if not year:
                    _fm = re.search(r'\b((?:19|20)\d{2})\b', r.get("folder_name", "") or "")
                    if _fm:
                        year = _fm.group(1)
                entries.append({
                    "lb": lb,
                    "lb_str": f"LB-{lb:05d}",
                    "url": (
                        "http://www.losslessbob.wonderingwhattochoose.com"
                        f"/detail/LB-{lb:05d}.html"
                    ),
                    "status": r.get("lb_status") or "unknown",
                    "date": date_str,
                    "year": year,
                    "location": r.get("location", "") or "",
                    "folder": r.get("folder_name", "") or "",
                    "notes": r.get("notes", "") or "",
                })

            data_json = _json.dumps(entries, ensure_ascii=False)
            generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            html = (
                _COLLECTION_HTML_TEMPLATE
                .replace("__DATA_JSON__", data_json)
                .replace("__GENERATED_AT__", generated_at)
            )
            return Response(
                html,
                mimetype="text/html",
                headers={"Content-Disposition": "attachment; filename=collection.html"},
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/export/m3u", methods=["GET"])
    def collection_export_m3u() -> Response:
        """Export the full My Collection as an M3U playlist.

        Iterates each entry's disk_path folder and includes all audio files
        (FLAC, SHN, APE, WAV, MP3) in sorted order.  Entries with no valid
        disk_path are silently skipped.

        Returns:
            M3U file attachment (collection.m3u).
        """
        try:
            rows = database.get_collection()
            audio_exts = {".flac", ".shn", ".ape", ".wav", ".mp3"}
            lines = ["#EXTM3U"]
            for r in rows:
                dp = r.get("disk_path", "")
                if not dp or not Path(dp).is_dir():
                    continue
                for f in sorted(Path(dp).iterdir()):
                    if f.suffix.lower() in audio_exts:
                        lines.append(
                            f"#EXTINF:-1,{r.get('date_str', '')} - "
                            f"{r.get('location', '')}"
                        )
                        lines.append(str(f))
            return Response(
                "\n".join(lines),
                mimetype="audio/x-mpegurl",
                headers={"Content-Disposition": "attachment; filename=collection.m3u"},
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-10: Application version + update ─────────────────────────────────

    @app.route("/api/app/version", methods=["GET"])
    def app_version() -> Response:
        """Return current app version and runtime info."""
        import platform
        import sys

        from backend.version import VERSION as _VER
        try:
            from PyQt6.QtCore import QT_VERSION_STR
        except Exception:
            QT_VERSION_STR = "n/a"
        return jsonify({
            "version": _VER,
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "qt": QT_VERSION_STR,
        })

    @app.route("/api/update/check", methods=["GET"])
    def update_check() -> Response:
        """Query GitHub releases API for a newer version.

        Requires github_repo setting (owner/repo).
        Returns:
            JSON with current, latest, update_available, release_notes, zipball_url.
        """
        try:
            import requests as _req

            from backend.version import VERSION as _VER
            repo = database.get_meta("github_repo") or ""
            if not repo or "/" not in repo:
                return jsonify({"error": "github_repo not configured"}), 400
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            resp = _req.get(api_url, timeout=10,
                            headers={"Accept": "application/vnd.github+json",
                                     "X-GitHub-Api-Version": "2022-11-28"})
            if resp.status_code == 404:
                return jsonify({"error": "No releases found for this repository"}), 404
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            release_notes = data.get("body", "")
            zipball_url = data.get("zipball_url", "")

            def _ver(v):
                try:
                    return tuple(int(x) for x in v.split(".")[:3])
                except Exception:
                    return (0, 0, 0)

            update_available = _ver(latest_tag) > _ver(_VER)
            with _update_lock:
                _update_state.update({
                    "latest_version": latest_tag,
                    "update_available": update_available,
                })
            return jsonify({
                "current": _VER, "latest": latest_tag,
                "update_available": update_available,
                "release_notes": release_notes,
                "zipball_url": zipball_url,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/update/status", methods=["GET"])
    def update_status() -> Response:
        """Return current update download/apply progress."""
        with _update_lock:
            return jsonify(dict(_update_state))

    @app.route("/api/update/apply", methods=["POST"])
    def update_apply() -> Response:
        """Start a background download + apply of the update.

        Body: {zipball_url: str}
        Returns:
            JSON {ok: true} immediately; poll /api/update/status for progress.
        """
        try:
            repo = database.get_meta("github_repo") or ""
            if not repo:
                return jsonify({"error": "github_repo not configured"}), 400
            data = request.get_json() or {}
            zipball_url = data.get("zipball_url", "")
            if not zipball_url:
                return jsonify({"error": "zipball_url required"}), 400
            threading.Thread(target=_do_update, args=(zipball_url,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-11: Remote Data ZIP ──────────────────────────────────────────────

    @app.route("/api/data/download", methods=["POST"])
    def data_download() -> Response:
        """Start a background download+extract of the configured data_zip_url.

        Returns:
            JSON {ok: true} immediately; poll /api/data/download/status for progress.
        """
        try:
            url = database.get_meta("data_zip_url") or ""
            if not url:
                return jsonify({"error": "data_zip_url not configured"}), 400
            with _data_dl_lock:
                if _data_dl_state["status"] in ("downloading", "extracting"):
                    return jsonify({"error": "Download already in progress"}), 409
            threading.Thread(target=_do_data_download, args=(url,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/data/download/status", methods=["GET"])
    def data_download_status() -> Response:
        """Return current data ZIP download/extract progress."""
        with _data_dl_lock:
            return jsonify(dict(_data_dl_state))

    # ── FEAT-09: Collection Folder Integrity ──────────────────────────────────

    @app.route("/api/integrity/events", methods=["GET"])
    def integrity_events_route() -> Response:
        """Return watchdog integrity events.

        Query params:
            unacked (default 1): 1 = unacknowledged only, 0 = all
        Returns:
            JSON list of event rows.
        """
        unacked = request.args.get("unacked", "1") == "1"
        return jsonify(database.get_integrity_events(unacked_only=unacked))

    @app.route("/api/integrity/ack", methods=["POST"])
    def integrity_ack() -> Response:
        """Acknowledge integrity events by ID.

        Body: {ids: [int, ...]}
        Returns:
            JSON {ok: true}
        """
        ids = (request.get_json() or {}).get("ids", [])
        database.ack_integrity_events(ids)
        return jsonify({"ok": True})

    # ── Scraper Control ──────────────────────────────────────────────────────

    @app.route("/api/scrape/start", methods=["POST"])
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
            delay = int(database.get_meta("scrape_delay_ms") or 1500)
            download = database.get_meta("scrape_attachments") != "0"
            use_local_pages = database.get_meta("use_local_pages") == "1"

            with database.get_connection() as conn:
                q = (
                    "SELECT DISTINCT c.lb_number FROM checksums c "
                    "LEFT JOIN lb_master m ON m.lb_number = c.lb_number "
                    "WHERE c.lb_number >= ? "
                    "AND (m.lb_status IS NULL OR m.lb_status != 'private')"
                )
                params: list = [start_lb]
                if end_lb:
                    q += " AND c.lb_number <= ?"
                    params.append(end_lb)
                q += " ORDER BY c.lb_number"
                lb_numbers = [r[0] for r in conn.execute(q, params).fetchall()]

            # Always fill every sequential gap so no LB number is left out of
            # the database. Derive the upper bound from the highest checksum entry
            # when no explicit end_lb was given ("Scrape All Missing" path).
            effective_end = end_lb or (lb_numbers[-1] if lb_numbers else None)
            if effective_end:
                known = set(lb_numbers)
                for n in range(start_lb, effective_end + 1):
                    if n not in known:
                        database.insert_missing_entry(n)

            _start_scrape_thread(lb_numbers, force=force, delay_ms=delay, download=download, use_local_pages=use_local_pages)
            return jsonify({"ok": True, "total": len(lb_numbers)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scrape/status", methods=["GET"])
    def scrape_status() -> Response:
        """Return current status of the background scrape worker.

        Returns:
            JSON status dict from scraper.get_scrape_status().
        """
        return jsonify(scraper.get_scrape_status())

    @app.route("/api/scrape/stop", methods=["POST"])
    def scrape_stop() -> Response:
        """Signal the background scrape worker to stop after the current entry.

        Returns:
            JSON {ok: true}.
        """
        scraper.stop_scrape()
        return jsonify({"ok": True})

    @app.route("/api/scrape/download_pages", methods=["POST"])
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
            _start_download_pages_thread(lb_numbers, force=force, delay_ms=delay)
            return jsonify({"ok": True, "total": len(lb_numbers)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scrape/private_rescrape", methods=["POST"])
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
            _start_scrape_thread(
                lb_numbers, force=True, delay_ms=delay,
                download=download, use_local_pages=use_local_pages,
            )
            return jsonify({"ok": True, "total": len(lb_numbers)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Bootleg-CD Catalog ────────────────────────────────────────────────────

    @app.route("/api/bootlegs/scrape", methods=["POST"])
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
            if bootleg_scraper.get_scrape_status().get("running"):
                return jsonify({"ok": False, "error": "Scrape already running"}), 409
            threading.Thread(
                target=bootleg_scraper.scrape_bootlegs,
                kwargs={"force": force},
                daemon=True,
            ).start()
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bootlegs/scrape/status", methods=["GET"])
    def bootlegs_scrape_status():
        """Poll the bootleg scrape progress state."""
        return jsonify(bootleg_scraper.get_scrape_status())

    @app.route("/api/bootlegs/lb_numbers", methods=["GET"])
    def bootlegs_lb_numbers():
        """Return sorted list of lb_numbers that have at least one bootleg title.

        Used by the Search and Collection tabs to populate the 🎵 badge set
        without an expensive per-row lookup.
        """
        try:
            return jsonify(database.get_bootleg_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bootlegs", methods=["GET"])
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

    @app.route("/api/bootlegs/by_lb/<int:lb>", methods=["GET"])
    def bootlegs_by_lb(lb: int):
        """All bootleg titles for one LB number."""
        try:
            return jsonify(database.get_bootlegs_for_lb(lb))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bootlegs/scrapes", methods=["GET"])
    def bootlegs_scrape_history():
        """Recent bootleg_scrapes rows (newest first). Query param: limit (default 20)."""
        try:
            limit = min(int(request.args.get("limit", 20)), 100)
            return jsonify(database.get_bootleg_scrape_history(limit))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bootlegs/stats", methods=["GET"])
    def bootlegs_stats():
        """Summary counts: total rows, last scrape timestamp and status."""
        try:
            return jsonify(database.get_bootleg_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Site Crawler ─────────────────────────────────────────────────────────

    _crawler_thread: list[threading.Thread] = []  # single-element list for mutability in closure

    @app.route("/api/crawler/start", methods=["POST"])
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
            if site_crawler.get_crawler_status().get("running"):
                return jsonify({"ok": False, "error": "Crawler already running"}), 409
            data = request.get_json() or {}
            scope     = data.get("scope", "incremental")
            force     = bool(data.get("force", False))
            delay_ms  = int(data.get("delay_ms", 1500))
            daily_cap = int(data.get("daily_cap", 99999))
            t = threading.Thread(
                target=site_crawler.crawl,
                kwargs={"scope": scope, "force": force,
                        "delay_ms": delay_ms, "daily_cap": daily_cap},
                daemon=True,
            )
            t.start()
            _crawler_thread[:] = [t]
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/crawler/status", methods=["GET"])
    def crawler_status():
        """Return a snapshot of the current crawler state."""
        return jsonify(site_crawler.get_crawler_status())

    @app.route("/api/crawler/stop", methods=["POST"])
    def crawler_stop():
        """Request the crawler to stop after the current URL."""
        site_crawler.stop_crawler()
        return jsonify({"ok": True})

    @app.route("/api/crawler/sessions", methods=["GET"])
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

    @app.route("/api/crawler/inventory", methods=["GET"])
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

    @app.route("/api/crawler/inventory/stats", methods=["GET"])
    def crawler_inventory_stats():
        """Return aggregate counts from site_inventory grouped by status."""
        try:
            return jsonify(database.get_inventory_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Verify ───────────────────────────────────────────────────────────────

    @app.route("/api/verify", methods=["POST"])
    def verify() -> Response:
        """Verify checksums for a list of local folders against the DB.

        Body: {folders: ["/path/to/folder", ...]}
        Returns:
            JSON {results: [verify_result, ...]} or 400 if folders is empty.
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400
            results = [checksum_utils.verify_folder(f) for f in folders]
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/verify/generate", methods=["POST"])
    def verify_generate() -> Response:
        """Generate checksum files (_mychecksums_*) for a list of folders.

        Body: {folders: ["/path/to/folder", ...]}
        Returns:
            JSON {results: [generate_result, ...]} or 400 if folders is empty.
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400
            results = [checksum_utils.generate_checksums(f) for f in folders]
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── LBDir ────────────────────────────────────────────────────────────────

    @app.route("/api/lbdir/check", methods=["POST"])
    def lbdir_check() -> Response:
        """Verify each folder's files against its lbdir*.txt checksum list.

        Body: {folders: ["/path/to/folder", ...], lb_number_hint?: int}
        Returns:
            JSON {results: [lbdir_check_result, ...]} or 400 if folders is empty.
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400

            # Optional single-folder hint: pipeline passes this when LB is known from
            # lookup but the folder has not yet been renamed (LBDIR now runs before
            # Rename, so neither my_collection nor the folder name has the LB# yet).
            lb_number_hint: int | None = None
            raw_hint = data.get("lb_number_hint")
            if raw_hint is not None:
                try:
                    lb_number_hint = int(raw_hint)
                except (ValueError, TypeError):
                    pass

            results = []
            for folder_path in folders:
                folder = Path(folder_path)

                # Look up LB number: try my_collection first, then parse folder name,
                # then fall back to the caller-supplied hint (pipeline lookup result).
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?",
                        (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None

                if lb_number is None:
                    m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                    if m:
                        lb_number = int(m.group(1))

                if lb_number is None and lb_number_hint is not None:
                    lb_number = lb_number_hint

                lbdir_path = _find_lbdir_in_folder(folder)

                if not lbdir_path:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": lb_number,
                        "lbdir_found": False,
                        "lbdir_path": None,
                        "status": "no_lbdir",
                        "mode": "unknown",
                        "total": 0, "pass": 0, "mismatch": 0, "missing": 0,
                        "extra": 0, "missing_types": [], "files": [],
                        "error": "No lbdir*.txt found in folder",
                    })
                    continue

                result = checksum_utils.verify_folder_lbdir(folder_path, lbdir_path)
                result["lb_number"] = lb_number
                result["lbdir_found"] = True
                result["lbdir_path"] = str(lbdir_path)

                lbdir_verified_at = None
                if result["status"] == "pass" and lb_number is not None:
                    database.set_lbdir_verified(str(folder))
                    with database.get_connection() as _c:
                        _row = _c.execute(
                            "SELECT lbdir_verified_at FROM my_collection WHERE lb_number=?",
                            (lb_number,)
                        ).fetchone()
                    lbdir_verified_at = _row["lbdir_verified_at"] if _row else None
                result["lbdir_verified_at"] = lbdir_verified_at

                results.append(result)

            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/retrieve", methods=["POST"])
    def lbdir_retrieve() -> Response:
        """Copy the lbdir*.txt from the attachments cache into each folder.

        Scrapes the LB entry first if the attachment has not yet been downloaded.
        Body: {folders: ["/path/to/folder", ...]}
        Returns:
            JSON {results: [retrieve_result, ...]} or 400 if folders is empty.
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400

            # Optional single-folder hint: pipeline passes this when LB is known from
            # lookup but the folder has not yet been renamed or filed.
            lb_number_hint: int | None = None
            raw_hint = data.get("lb_number_hint")
            if raw_hint is not None:
                try:
                    lb_number_hint = int(raw_hint)
                except (ValueError, TypeError):
                    pass

            results = []
            for folder_path in folders:
                folder = Path(folder_path)

                # Look up LB number: try my_collection first, then parse folder name,
                # then fall back to the caller-supplied hint (pipeline lookup result).
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?",
                        (str(folder),)
                    ).fetchone()

                lb_number = row["lb_number"] if row else None

                if lb_number is None:
                    m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                    if m:
                        lb_number = int(m.group(1))

                if lb_number is None and lb_number_hint is not None:
                    lb_number = lb_number_hint

                if lb_number is None:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": None,
                        "status": "no_lb_number",
                        "lbdir_filename": None,
                    })
                    continue
                lbdir_src = find_lbdir_attachment(lb_number)
                was_scraped = False

                if not lbdir_src:
                    scraper.scrape_entry(lb_number, force=False, download_files=True)
                    lbdir_src = find_lbdir_attachment(lb_number)
                    was_scraped = True

                if not lbdir_src:
                    # This LB has no lbdir — try the canonical if this is an alias.
                    canonical_list = database.resolve_aliases([lb_number])
                    canonical = (
                        canonical_list[0]
                        if canonical_list and canonical_list[0] != lb_number
                        else None
                    )
                    if canonical:
                        lbdir_src = find_lbdir_attachment(canonical)
                        if not lbdir_src:
                            scraper.scrape_entry(canonical, force=False, download_files=True)
                            lbdir_src = find_lbdir_attachment(canonical)
                            was_scraped = True
                        if lbdir_src:
                            lb_number = canonical

                if not lbdir_src:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": lb_number,
                        "status": "not_found",
                        "lbdir_filename": None,
                    })
                    continue

                dest = folder / lbdir_src.name
                existing = _find_lbdir_in_folder(folder)
                if existing:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": lb_number,
                        "status": "already_present",
                        "lbdir_filename": existing.name,
                    })
                    continue

                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(lbdir_src), str(dest))

                results.append({
                    "folder": str(folder_path),
                    "lb_number": lb_number,
                    "status": "scraped_and_copied" if was_scraped else "copied",
                    "lbdir_filename": lbdir_src.name,
                })

            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/reconcile", methods=["POST"])
    def lbdir_reconcile() -> Response:
        """Preview: find disk/site files whose MD5 matches missing lbdir entries. Does NOT move files.

        Body: {folders: ["/path/to/folder", ...], lb_number_hint?: int}
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400

            # Optional single-folder hint: pipeline passes this when LB is known from
            # lookup but the folder has not yet been renamed (LBDIR now runs before
            # Rename, so neither my_collection nor the folder name has the LB# yet).
            lb_number_hint: int | None = None
            raw_hint = data.get("lb_number_hint")
            if raw_hint is not None:
                try:
                    lb_number_hint = int(raw_hint)
                except (ValueError, TypeError):
                    pass

            results = []
            for folder_path in folders:
                folder = Path(folder_path)
                lbdir_path = _find_lbdir_in_folder(folder)
                if not lbdir_path:
                    results.append({"folder": str(folder), "error": "No lbdir*.txt found"})
                    continue
                result = checksum_utils.find_reconcilable_files(folder, lbdir_path)
                result["folder"] = str(folder)

                # Look up lb_number to scan site/files for still-missing entries
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?", (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None
                if lb_number is None:
                    m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                    if m:
                        lb_number = int(m.group(1))

                if lb_number is None and lb_number_hint is not None:
                    lb_number = lb_number_hint

                if lb_number is not None:
                    site_result = checksum_utils.find_site_recoverable_files(
                        folder, lbdir_path, SITE_FILES_DIR, lb_number
                    )
                    result["site_proposals"] = site_result.get("site_proposals", [])
                else:
                    result["site_proposals"] = []

                results.append(result)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/apply_reconcile", methods=["POST"])
    def lbdir_apply_reconcile() -> Response:
        """Apply verified rename/move/copy proposals inside a single folder. Never deletes files."""
        try:
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            renames = data.get("renames", [])      # [{"from": rel, "to": rel}, ...]
            site_copies = data.get("site_copies", [])  # [{"site_path": abs, "lbdir_rel": rel}, ...]
            applied, errors = [], []

            for r in renames:
                src = folder / r["from"]
                dst = folder / r["to"]
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    applied.append(r)
                except Exception as e:
                    errors.append({"rename": r, "error": str(e)})

            site_copied = []
            for sc in site_copies:
                src = Path(sc["site_path"])
                dst = folder / sc["lbdir_rel"]
                # Security: only allow copies from within SITE_FILES_DIR
                try:
                    src.relative_to(SITE_FILES_DIR)
                except ValueError:
                    errors.append({"site_copy": sc, "error": "site_path outside SITE_FILES_DIR"})
                    continue
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    site_copied.append(sc["lbdir_rel"])
                except Exception as e:
                    errors.append({"site_copy": sc, "error": str(e)})

            return jsonify({"applied": len(applied), "site_copied": len(site_copied), "errors": errors})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/find_extra", methods=["POST"])
    def lbdir_find_extra() -> Response:
        """List files in each folder that are not referenced in the lbdir MD5 section."""
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400

            results = []
            for folder_path in folders:
                folder = Path(folder_path)
                lbdir_path = _find_lbdir_in_folder(folder)
                if not lbdir_path:
                    results.append({"folder": str(folder), "error": "No lbdir*.txt found"})
                    continue
                result = checksum_utils.find_extra_files(folder, lbdir_path)
                result["folder"] = str(folder)
                results.append(result)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/delete_extra", methods=["POST"])
    def lbdir_delete_extra() -> Response:
        """Permanently delete specified extra files and any resulting empty subdirectories."""
        try:
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            files = data.get("files", [])  # list of relative paths
            deleted, errors = [], []
            for rel in files:
                target = folder / rel
                try:
                    target.unlink()
                    deleted.append(rel)
                except Exception as e:
                    errors.append({"file": rel, "error": str(e)})
            # Prune subdirectories that are now empty (bottom-up, never touch folder root)
            removed_dirs = []
            for dirpath, _dirnames, _filenames in os.walk(str(folder), topdown=False):
                d = Path(dirpath)
                if d == folder:
                    continue
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                        removed_dirs.append(d.relative_to(folder).as_posix())
                except Exception:
                    pass
            return jsonify({"deleted": len(deleted), "removed_dirs": removed_dirs, "errors": errors})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/verified_status", methods=["POST"])
    def lbdir_verified_status() -> Response:
        """Return lbdir_verified_at timestamp for each requested folder path."""
        try:
            data = request.get_json() or {}
            folder_list = data.get("folders", [])
            if not folder_list:
                return jsonify({})
            placeholders = ",".join("?" * len(folder_list))
            with database.get_connection() as conn:
                rows = conn.execute(
                    f"SELECT disk_path, lbdir_verified_at FROM my_collection"
                    f" WHERE disk_path IN ({placeholders})",
                    folder_list,
                ).fetchall()
            result: dict = {f: None for f in folder_list}
            for row in rows:
                result[row["disk_path"]] = row["lbdir_verified_at"]
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/move_extras", methods=["POST"])
    def lbdir_move_extras() -> Response:
        """Move extra files (not in lbdir) to <folder>/extras/, preserving relative path structure."""
        try:
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            files = data.get("files", [])  # list of relative paths
            extras_dir = folder / "extras"
            extras_dir.mkdir(parents=True, exist_ok=True)
            moved, errors = [], []
            for rel in files:
                src = folder / rel
                dst = extras_dir / rel
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    moved.append(rel)
                except Exception as e:
                    errors.append({"file": rel, "error": str(e)})
            # Prune empty subdirectories (never touch folder root or extras_dir)
            for dirpath, _dirs, _files in os.walk(str(folder), topdown=False):
                d = Path(dirpath)
                if d == folder or d == extras_dir or str(d).startswith(str(extras_dir)):
                    continue
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass
            return jsonify({"moved": len(moved), "errors": errors})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Platform helpers ─────────────────────────────────────────────────────

    @app.route("/api/open/vlc", methods=["POST"])
    def open_vlc_route() -> Response:
        """Launch VLC with a list of paths.

        Body: {paths: ["/absolute/path", ...]}
        Returns:
            JSON {ok: true} or {ok: false, error: "..."}.
        """
        try:
            paths = (request.get_json(silent=True) or {}).get("paths", [])
            if not paths:
                return jsonify({"ok": False, "error": "No paths provided"}), 400
            from gui.platform_utils import open_in_vlc
            ok, err = open_in_vlc(paths)
            return jsonify({"ok": ok, "error": err if not ok else None})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Spectrogram ──────────────────────────────────────────────────────────

    @app.route("/api/spectrogram/check", methods=["GET"])
    def spectrogram_check() -> Response:
        """Return tool availability for the Setup tab indicator."""
        import shutil as _shutil

        from backend.checksum_utils import check_shntool_version
        from backend.sox_utils import check_sox_version, get_ffmpeg
        sox_ver     = check_sox_version()
        ffmpeg      = get_ffmpeg()
        shntool_ver = check_shntool_version()
        flac_ver    = _shutil.which("flac")
        return jsonify({
            "sox_available":      bool(sox_ver),
            "sox_version":        sox_ver,
            "ffmpeg_available":   ffmpeg is not None,
            "shntool_available":  bool(shntool_ver),
            "shntool_version":    shntool_ver,
            "flac_available":     flac_ver is not None,
        })

    @app.route("/api/spectrogram/generate", methods=["POST"])
    def spectrogram_generate() -> Response:
        """
        Start batch spectrogram generation for a list of folders.
        Body: {
            folders:    ["/path/to/folder", ...],
            width:      1500,
            height:     513,
            dyn_range:  120,
            force:      false,
        }
        """
        with _spectro_lock:
            if _spectro_state["status"] not in ("idle", "done", "error"):
                return jsonify({"error": "Generation already running"}), 409
            _spectro_state["status"] = "running"

        data    = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        opts = {
            "width":     int(data.get("width",    1500)),
            "height":    int(data.get("height",    513)),
            "dyn_range": int(data.get("dyn_range", 120)),
            "force":     bool(data.get("force",  False)),
        }
        import threading as _t
        _t.Thread(target=_do_spectro_batch,
                  args=([str(f) for f in folders], opts),
                  daemon=True).start()
        return jsonify({"ok": True})

    @app.route("/api/spectrogram/status", methods=["GET"])
    def spectrogram_status() -> Response:
        """Return current status of the spectrogram batch generation worker.

        Returns:
            JSON copy of the _spectro_state dict.
        """
        with _spectro_lock:
            return jsonify(dict(_spectro_state))

    @app.route("/api/spectrogram/stop", methods=["POST"])
    def spectrogram_stop() -> Response:
        """Request the spectrogram batch worker to stop after the current file.

        Returns:
            JSON {ok: true}.
        """
        with _spectro_lock:
            _spectro_state["stop_requested"] = True
        return jsonify({"ok": True})

    @app.route("/api/spectrogram/list", methods=["POST"])
    def spectrogram_list() -> Response:
        """
        Return a dict of {folder -> [entry, ...]} for the viewer.
        Body: {folders: [...]}
        """
        from backend.sox_utils import AUDIO_EXTS_ALL
        folders = (request.get_json() or {}).get("folders", [])
        result  = {}
        for folder in folders:
            p = Path(folder)
            if not p.is_dir():
                continue
            spectro_dir = p / "spectrograms"
            audio_files = sorted(
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS_ALL
            )
            pngs = {
                png.stem: str(png)
                for png in (spectro_dir.iterdir() if spectro_dir.is_dir() else [])
                if png.suffix.lower() == ".png"
            }
            entries = []
            for af in audio_files:
                png_path = pngs.get(af.stem, None)
                entries.append({
                    "audio_file": str(af),
                    "audio_name": af.name,
                    "png_path":   png_path,
                    "has_png":    png_path is not None,
                })
            if entries:
                result[folder] = entries
        return jsonify(result)

    @app.route("/api/spectrogram/png", methods=["GET"])
    def spectrogram_png() -> Response:
        """Serve a spectrogram PNG from an arbitrary absolute path on disk.

        Query param: path (absolute path to the PNG file)
        Returns:
            The PNG file bytes with image/png content-type, or 404.
        """
        path_str = request.args.get("path", "")
        if not path_str:
            abort(400)
        p = Path(path_str)
        if not p.exists() or not p.is_file() or p.suffix.lower() != ".png":
            abort(404)
        return send_file(str(p), mimetype="image/png")

    @app.route("/api/rename/apply", methods=["POST"])
    def rename_apply() -> Response:
        """Apply a list of folder/file renames on disk and log each to rename_history.

        Body: {renames: [{old_path, new_path, lb_number?}]}
        Returns:
            JSON {applied: N, errors: [...string]}
        """
        import shutil

        from backend.rename import write_rename_log
        data = request.get_json() or {}
        renames = data.get("renames", [])
        applied = 0
        errors: list[str] = []
        for item in renames:
            old_path = item.get("old_path", "")
            new_path = item.get("new_path", "")
            lb_number = item.get("lb_number")
            if not old_path or not new_path:
                errors.append(f"Missing old_path or new_path in item: {item}")
                continue
            try:
                src = Path(old_path)
                dst = Path(new_path)
                if not src.exists():
                    errors.append(f"Source not found: {old_path}")
                    continue
                if dst.exists():
                    errors.append(f"Destination already exists: {new_path}")
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                write_rename_log(
                    folder_path=str(dst.parent),
                    old_name=src.name,
                    new_name=dst.name,
                    source="rename_tab",
                    lb_number=lb_number,
                )
                applied += 1
            except Exception as exc:
                errors.append(f"{old_path}: {exc}")
        return jsonify({"applied": applied, "errors": errors})

    # ── FEAT-14: DB Editor ───────────────────────────────────────────────────

    @app.route("/api/dbedit/tables", methods=["GET"])
    def dbedit_tables() -> Response:
        """List all user-visible tables and views with row counts and edit flags.

        Returns:
            JSON list of {name, row_count, readonly, audit, warn} dicts.
        """
        try:
            is_bv = _dbedit_is_batchverify()
            conn = database.get_connection(_dbedit_db_path())
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('table','view') ORDER BY name"
            ).fetchall()
            result = []
            for r in rows:
                name = r["name"]
                if (name.startswith("sqlite_")
                        or any(name.endswith(sfx) for sfx in
                               ("_fts_data", "_fts_idx", "_fts_content",
                                "_fts_docsize", "_fts_config"))):
                    continue
                try:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM [{name}]"
                    ).fetchone()[0]
                except Exception:
                    count = -1
                result.append({
                    "name":      name,
                    "row_count": count,
                    "readonly":  is_bv or name in _DBEDIT_READONLY,
                    "audit":     not is_bv and name in _DBEDIT_AUDIT,
                    "warn":      not is_bv and name in _DBEDIT_WARN,
                })
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/schema", methods=["GET"])
    def dbedit_schema(name: str) -> Response:
        """Return PRAGMA table_info columns for a named table.

        Args:
            name: The SQLite table name to inspect.

        Returns:
            JSON list of column info dicts from PRAGMA table_info.
        """
        try:
            conn = database.get_connection(_dbedit_db_path())
            cols = conn.execute(
                f"PRAGMA table_info([{name}])"
            ).fetchall()
            return jsonify([dict(c) for c in cols])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/rows", methods=["GET"])
    def dbedit_rows(name: str) -> Response:
        """Return a paginated, searchable, sortable slice of a table's rows.

        Args:
            name: The SQLite table name to query.

        Query params: page, limit (max 500), search, sort_col, sort_dir, lb_number.
        Returns:
            JSON {columns, rows, total, page, limit}.
        """
        try:
            page     = int(request.args.get("page", 0))
            limit    = min(int(request.args.get("limit", 100)), 500)
            search   = request.args.get("search", "").strip()
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
            conn     = database.get_connection(_dbedit_db_path())

            lb_filter = request.args.get("lb_number", "").strip()
            where, params = "", []
            if search:
                text_cols = [
                    c["name"] for c in
                    conn.execute(f"PRAGMA table_info([{name}])").fetchall()
                    if "TEXT" in (c["type"] or "").upper() or not c["type"]
                ]
                if text_cols:
                    clauses = [f"CAST([{c}] AS TEXT) LIKE ?" for c in text_cols]
                    where   = "WHERE " + " OR ".join(clauses)
                    params  = [f"%{search}%"] * len(text_cols)
            if lb_filter and lb_filter.lstrip("-").isdigit():
                col_names = [c["name"] for c in
                             conn.execute(f"PRAGMA table_info([{name}])").fetchall()]
                if "lb_number" in col_names:
                    lb_clause = "lb_number = ?"
                    where = (f"WHERE {lb_clause}" if not where
                             else where + f" AND {lb_clause}")
                    params.append(int(lb_filter))

            order = f"ORDER BY [{sort_col}] {sort_dir}" if sort_col else ""
            total = conn.execute(
                f"SELECT COUNT(*) FROM [{name}] {where}", params
            ).fetchone()[0]
            cur = conn.execute(
                f"SELECT rowid, * FROM [{name}] {where} {order} LIMIT ? OFFSET ?",
                params + [limit, page * limit]
            )
            rows = cur.fetchall()

            # cur.description is always populated after execute, even for empty result sets
            cols = ([d[0] for d in cur.description] if cur.description else
                    ["rowid"] + [c["name"] for c in
                     conn.execute(f"PRAGMA table_info([{name}])").fetchall()])
            return jsonify({
                "columns": cols,
                "rows":    [list(r) for r in rows],
                "total":   total,
                "page":    page,
                "limit":   limit,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/row", methods=["PATCH"])
    def dbedit_update_row(name: str) -> Response:
        """Update a single row in a named table by rowid.

        Args:
            name: The SQLite table name to update.

        Body: {rowid: int, updates: {col: value, ...}}
        Returns:
            JSON {ok, affected} or 403/400 on permission/validation error.
        """
        if _dbedit_is_batchverify() or name in _DBEDIT_READONLY or name in _DBEDIT_AUDIT:
            return jsonify({"error": f"Table {name!r} is not editable"}), 403
        try:
            data    = request.get_json() or {}
            rowid   = data.get("rowid")
            updates = data.get("updates", {})
            if rowid is None or not updates:
                return jsonify({"error": "rowid and updates required"}), 400
            rconn = database.get_connection()
            valid = {c["name"] for c in
                     rconn.execute(f"PRAGMA table_info([{name}])").fetchall()}
            bad = [k for k in updates if k not in valid]
            if bad:
                return jsonify({"error": f"Unknown columns: {bad}"}), 400
            set_clause = ", ".join(f"[{k}]=?" for k in updates)
            _tbl, _sc, _vals = name, set_clause, list(updates.values()) + [rowid]
            affected = database.get_write_queue().execute(
                lambda c: c.execute(
                    f"UPDATE [{_tbl}] SET {_sc} WHERE rowid=?", _vals
                ).rowcount
            )
            return jsonify({"ok": True, "affected": affected})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/rows", methods=["DELETE"])
    def dbedit_delete_rows(name: str) -> Response:
        """Delete one or more rows from a named table by rowid list.

        Args:
            name: The SQLite table name to delete from.

        Body: {rowids: [int, ...]}
        Returns:
            JSON {ok, deleted} or 403/400 on permission/validation error.
        """
        if _dbedit_is_batchverify() or name in _DBEDIT_READONLY:
            return jsonify({"error": f"Table {name!r} cannot be modified"}), 403
        try:
            rowids = (request.get_json() or {}).get("rowids", [])
            if not rowids:
                return jsonify({"error": "rowids list required"}), 400
            ph = ",".join("?" * len(rowids))
            _tbl, _ph, _rids = name, ph, list(rowids)
            deleted = database.get_write_queue().execute(
                lambda c: c.execute(
                    f"DELETE FROM [{_tbl}] WHERE rowid IN ({_ph})", _rids
                ).rowcount
            )
            return jsonify({"ok": True, "deleted": deleted})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/export", methods=["GET"])
    def dbedit_export(name: str) -> Response:
        """Export all rows of a named table as a CSV file download.

        Args:
            name: The SQLite table name to export.

        Returns:
            CSV file attachment with Content-Disposition header.
        """
        try:
            import csv
            import io
            conn = database.get_connection(_dbedit_db_path())
            rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
            buf  = io.StringIO()
            if rows:
                writer = csv.writer(buf)
                writer.writerow(rows[0].keys())
                writer.writerows(rows)
            return Response(
                buf.getvalue(), mimetype="text/csv",
                headers={"Content-Disposition":
                         f"attachment; filename={name}.csv"}
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/query", methods=["POST"])
    def dbedit_query() -> Response:
        """Execute an arbitrary SQL query against losslessbob.db.

        Body: {sql: str, limit: int (optional, default 500, max 2000)}
        Returns:
            SELECT/PRAGMA/WITH: {columns, rows, row_count, truncated}
            DML (INSERT/UPDATE/DELETE): {ok, rows_affected}
            Error: {error: str} with 400 status.
        """
        body = request.get_json(force=True, silent=True) or {}
        sql: str = (body.get("sql") or "").strip()
        if not sql:
            return jsonify({"error": "No SQL provided."}), 400

        limit = min(int(body.get("limit", 500)), 2000)
        query_db = str(BATCH_VERIFY_DB_PATH) if (body.get("db") or "").lower() == "batchverify" else str(database.DB_PATH)
        is_bv_query = query_db == str(BATCH_VERIFY_DB_PATH)

        upper = sql.upper()
        for blocked in ("DROP ", "TRUNCATE ", "VACUUM", "ATTACH ", "DETACH "):
            if upper.startswith(blocked):
                return jsonify({
                    "error": f"Statement type blocked: {blocked.strip()}."
                             " Use the schema editor for structural changes."
                }), 400

        is_read = any(upper.startswith(kw) for kw in
                      ("SELECT", "PRAGMA", "WITH", "EXPLAIN", "VALUES"))
        if is_bv_query and not is_read:
            return jsonify({"error": "batch_verify.db is read-only."}), 403
        try:
            if is_read:
                conn = database.get_connection(query_db)
                cur = conn.execute(sql)
            else:
                result_holder: list = []

                def _run(c: object) -> None:
                    cur = c.execute(sql)  # type: ignore[attr-defined]
                    result_holder.append(cur)

                database.get_write_queue().execute(_run)
                cur = result_holder[0] if result_holder else None

            if cur is not None and cur.description:
                columns = [d[0] for d in cur.description]
                rows = [list(r) for r in cur.fetchmany(limit)]
                return jsonify({
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": len(rows) >= limit,
                })
            else:
                affected = cur.rowcount if cur is not None else 0
                return jsonify({"ok": True, "rows_affected": affected, "columns": [], "rows": []})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # ── Torrent Generation ───────────────────────────────────────────────────

    @app.route("/api/torrent/create", methods=["POST"])
    def torrent_create() -> Response:
        """Generate a .torrent for one LB entry.

        Body: {lb_number, source_folder, tracker_list?}
        Returns: {ok, torrent_path, infohash, torrent_id, name, excluded_files}
        """
        try:
            from backend.torrent_maker import make_torrent
            data = request.get_json() or {}
            lb = data.get("lb_number")
            folder = data.get("source_folder", "")
            tracker_list = data.get("tracker_list") or database.get_meta("tracker_list") or "best"
            if not lb or not folder:
                return jsonify({"error": "lb_number and source_folder required"}), 400
            result = make_torrent(int(lb), folder, tracker_list=tracker_list)
            # Null out torrent_path on older sibling records that share the new file path
            # so they stop falsely reporting torrent_file_exists=True.
            database.clear_superseded_torrent_paths(
                int(lb), result["torrent_id"], result["torrent_path"]
            )
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/torrent/<int:lb>", methods=["GET"])
    def torrent_list(lb: int) -> Response:
        """List all torrent records for an LB entry."""
        try:
            rows = database.get_torrents_for_lb(lb)
            # Annotate each row with source_folder_exists for the history panel
            for row in rows:
                row["source_folder_exists"] = (
                    bool(row.get("source_folder"))
                    and Path(row["source_folder"]).is_dir()
                )
                row["torrent_file_exists"] = (
                    bool(row.get("torrent_path"))
                    and Path(row["torrent_path"]).exists()
                )
            return jsonify(rows)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/torrent/<int:torrent_id>", methods=["PATCH"])
    def torrent_update(torrent_id: int) -> Response:
        """Update a torrents row (e.g. source_folder after path relocation)."""
        try:
            fields = request.get_json() or {}
            database.update_torrent_record(torrent_id, fields)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/trackers", methods=["GET"])
    def trackers_get() -> Response:
        """Return the cached tracker list.

        Query params: list_name, force_refresh (0/1).
        """
        try:
            from backend.torrent_maker import fetch_trackers
            list_name = request.args.get("list_name") or database.get_meta("tracker_list") or "best"
            force = request.args.get("force_refresh", "0") == "1"
            trackers = fetch_trackers(list_name, force_refresh=force)
            return jsonify({"list_name": list_name, "count": len(trackers), "trackers": trackers})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── qBittorrent Integration ───────────────────────────────────────────────

    @app.route("/api/qbt/test", methods=["POST"])
    def qbt_test() -> Response:
        """Test qBittorrent WebUI connectivity.

        Body: {host, port, username?, password?, api_key?} — credentials optional (uses keyring).
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
            from backend.qbittorrent import test_connection
            data = request.get_json() or {}
            host = data.get("host") or database.get_meta("qbt_host") or "localhost"
            port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
            api_key = data.get("api_key") or ""
            if not api_key:
                _, api_key = get_credentials(SERVICE_QBT_KEY)
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not api_key and not username:
                username, password = get_credentials(SERVICE_QBT)
            return jsonify(test_connection(host, port, username, password, api_key))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/qbt/add", methods=["POST"])
    def qbt_add() -> Response:
        """Add one or more torrents to qBittorrent.

        Body: {torrent_id?, lb_numbers?, host?, port?, username?, password?,
               api_key?, category?, tags?}
        Use torrent_id for a single known record, or lb_numbers to add all
        torrents for those entries (latest record per LB).
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
            from backend.qbittorrent import add_torrent_from_db
            data = request.get_json() or {}
            host = data.get("host") or database.get_meta("qbt_host") or "localhost"
            port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
            category = data.get("category") or database.get_meta("qbt_category") or ""
            tags = data.get("tags") or database.get_meta("qbt_tags") or ""
            api_key = data.get("api_key") or ""
            if not api_key:
                _, api_key = get_credentials(SERVICE_QBT_KEY)
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not api_key and not username:
                username, password = get_credentials(SERVICE_QBT)

            results = []
            if data.get("torrent_id"):
                r = add_torrent_from_db(
                    int(data["torrent_id"]), host, port, username, password, category, tags,
                    api_key=api_key,
                )
                results.append(r)
            elif data.get("lb_numbers"):
                for lb in data["lb_numbers"]:
                    rows = database.get_torrents_for_lb(int(lb))
                    if rows:
                        r = add_torrent_from_db(
                            rows[0]["id"], host, port, username, password, category, tags,
                            api_key=api_key,
                        )
                        results.append({**r, "lb_number": lb})
            else:
                return jsonify({"error": "torrent_id or lb_numbers required"}), 400

            ok_count = sum(1 for r in results if r.get("ok"))
            return jsonify({"ok": True, "added": ok_count, "total": len(results), "results": results})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/torrent/<int:torrent_id>/qbt_remove", methods=["POST"])
    def qbt_remove(torrent_id: int) -> Response:
        """Remove a torrent from qBittorrent (content files are NOT deleted).

        Uses the stored infohash. Clears added_to_qbt on success, and also
        when qBittorrent confirms the torrent is already gone (manual removal).
        Body: {host?, port?, username?, password?, api_key?}
        Returns: {ok, error?}
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
            from backend.qbittorrent import check_torrent_presence, remove_torrent
            data = request.get_json(silent=True) or {}
            host = data.get("host") or database.get_meta("qbt_host") or "localhost"
            port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
            api_key = data.get("api_key") or ""
            if not api_key:
                _, api_key = get_credentials(SERVICE_QBT_KEY)
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not api_key and not username:
                username, password = get_credentials(SERVICE_QBT)

            conn = database.get_connection()
            row = conn.execute(
                "SELECT infohash FROM torrents WHERE id=?", (torrent_id,)
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404

            result = remove_torrent(
                infohash=row["infohash"] or "",
                host=host, port=port,
                username=username, password=password, api_key=api_key,
            )
            if result["ok"]:
                database.update_torrent_record(
                    torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
                )
            else:
                # Remove failed — check if the torrent is simply already gone from qBittorrent
                # (e.g. user removed it manually). If absent, still clear the DB flag.
                check = check_torrent_presence(
                    infohash=row["infohash"] or "",
                    host=host, port=port,
                    username=username, password=password, api_key=api_key,
                )
                if check.get("ok") and not check.get("present"):
                    database.update_torrent_record(
                        torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
                    )
                    result = {"ok": True}
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/torrent/<int:torrent_id>/qbt_check", methods=["GET"])
    def qbt_check(torrent_id: int) -> Response:
        """Check whether a torrent is present in qBittorrent and sync the DB flag.

        Returns: {ok, present, synced, error?}
        synced=True means added_to_qbt was cleared because the torrent was gone.
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
            from backend.qbittorrent import check_torrent_presence
            host = database.get_meta("qbt_host") or "localhost"
            port = int(database.get_meta("qbt_port") or 8080)
            _, api_key = get_credentials(SERVICE_QBT_KEY)
            username, password = "", ""
            if not api_key:
                username, password = get_credentials(SERVICE_QBT)

            conn = database.get_connection()
            row = conn.execute(
                "SELECT infohash, added_to_qbt FROM torrents WHERE id=?", (torrent_id,)
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "present": False, "synced": False,
                                "error": f"No torrent record id={torrent_id}"}), 404

            result = check_torrent_presence(
                infohash=row["infohash"] or "",
                host=host, port=port,
                username=username, password=password, api_key=api_key,
            )

            synced = False
            if result.get("ok") and not result.get("present") and row["added_to_qbt"]:
                database.update_torrent_record(
                    torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
                )
                synced = True

            return jsonify({**result, "synced": synced})
        except Exception as exc:
            return jsonify({"ok": False, "present": False, "synced": False,
                            "error": str(exc)}), 500

    @app.route("/api/torrent/<int:torrent_id>/file", methods=["DELETE"])
    def torrent_file_delete(torrent_id: int) -> Response:
        """Delete the .torrent file from disk and clear torrent_path in the DB.

        Does not remove from qBittorrent.
        Returns: {ok, error?}
        """
        try:
            conn = database.get_connection()
            row = conn.execute(
                "SELECT torrent_path FROM torrents WHERE id=?", (torrent_id,)
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404

            torrent_path = row["torrent_path"]
            if torrent_path:
                p = Path(torrent_path)
                if p.exists():
                    p.unlink()
            database.update_torrent_record(torrent_id, {"torrent_path": None})
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/torrent/<int:torrent_id>", methods=["DELETE"])
    def torrent_record_delete(torrent_id: int) -> Response:
        """Delete a torrent DB record and its .torrent file if present.

        Blocked when added_to_qbt=1 — remove from qBittorrent first.
        Returns: {ok, error?}
        """
        try:
            conn = database.get_connection()
            row = conn.execute(
                "SELECT torrent_path, added_to_qbt FROM torrents WHERE id=?", (torrent_id,)
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404
            if row["added_to_qbt"]:
                return jsonify({
                    "ok": False,
                    "error": "Remove from qBittorrent before deleting this record.",
                }), 400

            torrent_path = row["torrent_path"]
            if torrent_path:
                p = Path(torrent_path)
                if p.exists():
                    p.unlink()
            database.delete_torrent_record(torrent_id)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Forum Posting ─────────────────────────────────────────────────────────

    @app.route("/api/wtrf/test", methods=["POST"])
    def wtrf_test() -> Response:
        """Test WTRF forum credentials by attempting a login (no post is made).

        Body: {username?, password?} — falls back to stored keyring credentials.
        Returns: {ok, username} or {ok=False, error}.
        """
        try:
            from backend.credentials import SERVICE_WTRF, get_credentials
            from backend.forum_poster import _get_session
            data = request.get_json() or {}
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not username:
                username, password = get_credentials(SERVICE_WTRF)
            if not username:
                return jsonify({"ok": False, "error": "No credentials provided"}), 400
            session = _get_session(username, password)
            if session is None:
                return jsonify({"ok": False, "error": "Login failed — check username and password."})
            return jsonify({"ok": True, "username": username})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/credentials/wtrf", methods=["POST"])
    def credentials_wtrf_save() -> Response:
        """Save WTRF forum credentials to the OS keyring.

        Body: {username, password}
        Returns: {ok: true} or {error}.
        """
        try:
            from backend.credentials import SERVICE_WTRF, save_credentials
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            password = data.get("password", "")
            if not username:
                return jsonify({"ok": False, "error": "Username required"}), 400
            save_credentials(SERVICE_WTRF, username, password)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/credentials/qbt", methods=["POST"])
    def credentials_qbt_save() -> Response:
        """Save qBittorrent credentials to the OS keyring.

        Body: {username, password} or {api_key}
        Returns: {ok: true} or {error}.
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, save_credentials
            data = request.get_json() or {}
            api_key = data.get("api_key", "").strip()
            username = data.get("username", "").strip()
            password = data.get("password", "")
            if api_key:
                save_credentials(SERVICE_QBT_KEY, "", api_key)
            elif username:
                save_credentials(SERVICE_QBT, username, password)
            else:
                return jsonify({"ok": False, "error": "Username or api_key required"}), 400
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/credentials/qbt", methods=["DELETE"])
    def credentials_qbt_delete() -> Response:
        """Remove qBittorrent credentials from the OS keyring.

        Returns:
            JSON {ok: true} or {error}.
        """
        try:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, delete_credentials
            delete_credentials(SERVICE_QBT)
            delete_credentials(SERVICE_QBT_KEY)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/credentials/wtrf", methods=["DELETE"])
    def credentials_wtrf_delete() -> Response:
        """Remove WTRF forum credentials from the OS keyring.

        Returns:
            JSON {ok: true} or {error}.
        """
        try:
            from backend.credentials import SERVICE_WTRF, delete_credentials
            delete_credentials(SERVICE_WTRF)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/entry/<int:lb>/preview_forum", methods=["GET"])
    def preview_forum(lb: int) -> Response:
        """Return the forum post subject and body for an LB entry without posting.

        Returns: {subject, body}.
        Blocked (HTTP 403) for private and missing LBs.
        """
        try:
            allowed, reason = database.is_postable_to_forum(lb)
            if not allowed:
                _msg = {
                    "lb_private": f"LB-{lb:05d} is marked Private. Forum posting is blocked.",
                    "lb_missing": f"LB-{lb:05d} is marked as not existing. Nothing to post.",
                    "status_unknown": f"LB-{lb:05d} has no master status record. Cannot post.",
                }.get(reason, f"LB-{lb:05d} cannot be posted.")
                return jsonify({"error": reason, "message": _msg}), 403

            from backend.forum_poster import preview_lb_topic
            entry_data = database.get_entry(lb)
            if not entry_data:
                return jsonify({"ok": False, "error": f"Entry LB-{lb} not found"}), 404
            entry = dict(entry_data["entry"])
            bootlegs = database.get_bootlegs_for_lb(lb)
            if bootlegs:
                entry["bootleg_title"] = bootlegs[0]["title"]
            result = preview_lb_topic(lb_number=lb, entry=entry, attachments_dir=SITE_FILES_DIR)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/entry/<int:lb>/post_forum", methods=["POST"])
    def post_forum(lb: int) -> Response:
        """Post a topic to the WTRF forum for one LB entry.

        Body: {username?, password?, torrent_id?}
        Requires a torrents record for the entry to exist.
        Returns: {ok, topic_url} or {ok=False, error}.
        """
        try:
            # Guard: block private and missing LBs from being posted to the forum
            allowed, reason = database.is_postable_to_forum(lb)
            if not allowed:
                _msg = {
                    "lb_private": (
                        f"LB-{lb:05d} is marked Private. "
                        "Forum posting is blocked to avoid exposing unreleased content."
                    ),
                    "lb_missing": (
                        f"LB-{lb:05d} is marked as not existing. There is nothing to post about."
                    ),
                    "status_unknown": (
                        f"LB-{lb:05d} has no master status record. Cannot determine postability."
                    ),
                }.get(reason, f"LB-{lb:05d} cannot be posted.")
                return jsonify({"error": reason, "message": _msg}), 403

            from backend.credentials import SERVICE_WTRF, get_credentials
            from backend.forum_poster import post_lb_topic
            data = request.get_json() or {}

            # Resolve credentials
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not username:
                username, password = get_credentials(SERVICE_WTRF)
            if not username:
                return jsonify({"ok": False, "error": "WTRF credentials not set"}), 400

            # Get entry metadata
            entry_data = database.get_entry(lb)
            if not entry_data:
                return jsonify({"ok": False, "error": f"Entry LB-{lb} not found"}), 404
            entry = dict(entry_data["entry"])
            bootlegs = database.get_bootlegs_for_lb(lb)
            if bootlegs:
                entry["bootleg_title"] = bootlegs[0]["title"]

            # Resolve torrent file
            torrent_id = data.get("torrent_id")
            if torrent_id:
                conn = database.get_connection()
                row = conn.execute(
                    "SELECT torrent_path FROM torrents WHERE id=?", (torrent_id,)
                ).fetchone()
                torrent_path = row["torrent_path"] if row else None
            else:
                rows = database.get_torrents_for_lb(lb)
                torrent_path = rows[0]["torrent_path"] if rows else None

            if not torrent_path:
                return jsonify({"ok": False, "error": "No torrent file found for this entry. Create one first."}), 400

            board_id = int(database.get_meta("wtrf_board_id") or 0)
            if not board_id:
                return jsonify({"ok": False, "error": "Forum board ID not set. Configure it in Setup → WTRF Forum."}), 400

            result = post_lb_topic(
                lb_number=lb,
                torrent_path=torrent_path,
                username=username,
                password=password,
                entry=entry,
                board_id=board_id,
                attachments_dir=SITE_FILES_DIR,
                subject_override=data.get("subject") or None,
                body_override=data.get("body") or None,
            )
            if result.get("ok"):
                from backend.torrent_maker import _parse_date
                subj = data.get("subject") or ""
                if not subj:
                    iso_date = _parse_date(entry.get("date_str") or "")
                    loc = (entry.get("location") or "").strip()
                    lb_id = f"LB-{lb:05d}"
                    subj = (f"{iso_date} {loc} ({lb_id})" if iso_date and loc
                            else f"{loc} ({lb_id})" if loc else lb_id)
                database.add_forum_post(
                    lb_number=lb,
                    subject=subj,
                    topic_url=result.get("topic_url", ""),
                    board_id=board_id,
                )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/entry/<int:lb>/forum_posts", methods=["GET"])
    def forum_posts_list(lb: int) -> Response:
        """Return all logged forum posts for an LB entry, newest first."""
        try:
            return jsonify(database.get_forum_posts_for_lb(lb))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/forum_post/<int:post_id>", methods=["DELETE"])
    def forum_post_delete(post_id: int) -> Response:
        """Delete a forum post log record by id."""
        try:
            database.delete_forum_post(post_id)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/forum_posts", methods=["GET"])
    def all_forum_posts() -> Response:
        """Return all logged forum posts across every LB entry, newest first."""
        try:
            return jsonify(database.get_all_forum_posts())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/torrents", methods=["GET"])
    def all_torrents() -> Response:
        """Return all torrent records across every LB entry, newest first."""
        try:
            rows = database.get_all_torrents()
            for row in rows:
                row["source_folder_exists"] = (
                    bool(row.get("source_folder"))
                    and Path(row["source_folder"]).is_dir()
                )
                row["torrent_file_exists"] = (
                    bool(row.get("torrent_path"))
                    and Path(row["torrent_path"]).exists()
                )
            return jsonify(rows)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── lb_master integrity API ────────────────────────────────────────────────

    @app.route("/api/lb_master/stats", methods=["GET"])
    def lb_master_stats() -> Response:
        """Return {public, private, missing, max_lb, overrides, needs_review} counts."""
        try:
            return jsonify(database.get_lb_master_stats())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/<int:lb>", methods=["GET"])
    def lb_master_get(lb: int) -> Response:
        """Return a single lb_master row joined with entry metadata."""
        try:
            row = database.get_lb_master_row(lb)
            if row is None:
                return jsonify({"error": "not_found"}), 404
            entry = database.get_entry(lb)
            row["entry"] = entry["entry"] if entry else None
            return jsonify(row)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master", methods=["GET"])
    def lb_master_list() -> Response:
        """Return paginated lb_master rows.

        Query params: status (public|private|missing), override=1, review=1,
                      limit (default 500), offset (default 0).
        """
        try:
            status = request.args.get("status") or None
            if status and status not in ("public", "private", "missing"):  # #6
                return jsonify({"error": "invalid_status",
                                "message": "status must be public, private, or missing"}), 400
            override_only = request.args.get("override") == "1"
            review_only = request.args.get("review") == "1"
            limit = max(1, min(int(request.args.get("limit", 500)), 2000))
            offset = max(0, int(request.args.get("offset", 0)))  # #7
            rows = database.get_lb_master_list(
                status=status, override_only=override_only, review_only=review_only,
                limit=limit, offset=offset,
            )
            return jsonify(rows)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/reconcile", methods=["POST"])
    def lb_master_reconcile() -> Response:
        """Full rebuild of lb_master. Backs up DB first. Returns status counts."""
        if not database.is_curator():  # #3
            return jsonify({"error": "curator_required"}), 403
        if not _reconcile_lock.acquire(blocking=False):
            return jsonify({"error": "already running"}), 409
        try:
            stats = database.reconcile_all_lb_master()
            return jsonify({"ok": True, "stats": stats})
        except Exception:
            _log.exception("lb_master_reconcile failed")  # #9
            return jsonify({"error": "internal_error"}), 500
        finally:
            _reconcile_lock.release()

    @app.route("/api/lb_master/history/<int:lb>", methods=["GET"])
    def lb_master_history(lb: int) -> Response:
        """Return transition history for an LB, newest first."""
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 500))  # #7
            rows = database.get_lb_status_history(lb, limit=limit)
            return jsonify(rows)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/<int:lb>/manual", methods=["PUT"])
    def lb_master_set_manual(lb: int) -> Response:
        """Set a manual override. Body: {status, notes}."""
        try:
            body = request.get_json(silent=True) or {}
            status = body.get("status")
            notes = str(body.get("notes", ""))[:1000]  # #11
            if status not in ("public", "private", "missing"):
                return jsonify({"error": "status must be public, private, or missing"}), 400
            database.set_lb_manual_override(lb, status, notes)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/<int:lb>/manual", methods=["DELETE"])
    def lb_master_clear_manual(lb: int) -> Response:
        """Clear a manual override and immediately reconcile."""
        try:
            new_status = database.clear_lb_manual_override(lb)
            return jsonify({"ok": True, "new_status": new_status})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/overrides/export", methods=["GET"])
    def lb_master_overrides_export():
        """Export all manual overrides as a JSON array.

        Returns every lb_master row where manual_override=1, serialised as a
        list of dicts suitable for re-import via POST /api/lb_master/overrides/import.
        Read-only — no curator check required.
        """
        try:
            data = database.export_overrides()
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/overrides/import", methods=["POST"])
    def lb_master_overrides_import():
        """Import manual overrides from a JSON array body.  Curator-only.

        Body: list of ``{lb_number, manual_status, manual_notes, manual_set_by}``.
        Entries whose lb_number is outside the current lb_master range are
        silently skipped and counted.

        Returns:
            ``{imported: int, skipped: int}``
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        payload = request.get_json(force=True)
        if not isinstance(payload, list):
            return jsonify({"error": "expected JSON array"}), 400
        try:
            result = database.import_overrides(payload)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_master/<int:lb>/nft", methods=["GET"])
    def lb_master_nft(lb: int) -> Response:
        """Return {nft: bool, reason: str|null} for folder naming guidance."""
        try:
            status = database.get_lb_status(lb)
            nft = status == "private"
            reason = "private" if nft else None
            return jsonify({"nft": nft, "reason": reason})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── lb_missing management ─────────────────────────────────────────────────

    @app.route("/api/lb_missing", methods=["GET"])
    def lb_missing_list() -> Response:
        """List all entries in lb_missing ordered by lb_number."""
        try:
            return jsonify(database.get_lb_missing_list())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_missing", methods=["POST"])
    def lb_missing_add() -> Response:
        """Curator-only. Add an lb_number to lb_missing.

        Body: {lb_number, confirmed_date?, notes?}
        """
        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403
            body = request.get_json(force=True) or {}
            lb = body.get("lb_number")
            if not isinstance(lb, int) or lb < 1:
                return jsonify({"error": "lb_number must be a positive integer"}), 400
            database.add_lb_missing(
                lb,
                confirmed_date=body.get("confirmed_date", ""),
                notes=body.get("notes", ""),
            )
            return jsonify({"ok": True, "lb_number": lb})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_missing/<int:lb>", methods=["DELETE"])
    def lb_missing_remove(lb: int) -> Response:
        """Curator-only. Remove an lb_number from lb_missing."""
        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403
            database.remove_lb_missing(lb)
            return jsonify({"ok": True, "lb_number": lb})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Dylan Performances API ─────────────────────────────────────────────────

    @app.route("/api/performances", methods=["GET"])
    def performances_list() -> Response:
        """Return dylan_performances rows with optional filters.

        Query params:
            date (str): ISO date (YYYY-MM-DD) — returns rows matching that date.
            lb (int): LB number — looks up the entry's date then matches performances.
            category (str): Filter by category (HOME, MCONCERT, RADIO, etc.).
            limit (int): Maximum rows to return (default 200, max 2000).
            offset (int): Pagination offset (default 0).

        Returns:
            JSON list of performance dicts. When ?lb= is used and no match is
            found returns an empty list (not 404), since not every concert is in
            the performances dataset.
        """
        try:
            conn = database.get_connection()
            date_q = request.args.get("date", "").strip()
            lb_q = request.args.get("lb", "").strip()
            cat_q = request.args.get("category", "").strip()
            limit = min(int(request.args.get("limit", 200)), 2000)
            offset = int(request.args.get("offset", 0))

            if lb_q:
                # Resolve LB → entry date → ISO date → performances lookup
                lb_num = int(lb_q)
                entry = conn.execute(
                    "SELECT date_str FROM entries WHERE lb_number=?", (lb_num,)
                ).fetchone()
                if not entry or not entry["date_str"]:
                    return jsonify([])
                from backend.geocoder import _entry_date_to_iso as _to_iso
                iso_date = _to_iso(entry["date_str"])
                if not iso_date:
                    return jsonify([])
                date_q = iso_date

            clauses: list[str] = []
            params: list = []
            if date_q:
                clauses.append("date_str = ?")
                params.append(date_q)
            if cat_q:
                clauses.append("category = ?")
                params.append(cat_q)

            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = conn.execute(
                f"SELECT event_id, date_str, category, city, state, country, venue "
                f"FROM dylan_performances {where} "
                f"ORDER BY date_str, event_id LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── lb_problems API ────────────────────────────────────────────────────────

    @app.route("/api/lb_problems", methods=["GET"])
    def lb_problems_list() -> Response:
        """List lb_problems rows, optionally filtered to a single LB.

        Query param: lb (int) — when supplied, returns only that LB's rows.

        Returns:
            JSON list of {id, lb_number, notes, added}.
        """
        try:
            lb_q = request.args.get("lb", "").strip()
            lb_num = int(lb_q) if lb_q else None
            return jsonify(database.get_lb_problems(lb_num))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_problems", methods=["POST"])
    def lb_problems_add() -> Response:
        """Curator-only. Add a problem note for an LB entry.

        Body: {lb_number (int), notes (str), added? (YYYY-MM-DD str)}

        Returns:
            JSON {ok, id, lb_number}.
        """
        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403
            body = request.get_json(force=True) or {}
            lb = body.get("lb_number")
            notes = (body.get("notes") or "").strip()
            if not isinstance(lb, int) or lb < 1:
                return jsonify({"error": "lb_number must be a positive integer"}), 400
            if not notes:
                return jsonify({"error": "notes must not be empty"}), 400
            new_id = database.add_lb_problem(lb, notes, body.get("added"))
            return jsonify({"ok": True, "id": new_id, "lb_number": lb})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_problems/<int:problem_id>", methods=["PUT"])
    def lb_problems_update(problem_id: int) -> Response:
        """Update the notes on an lb_problems row.

        Body: {notes (str)}

        Returns:
            JSON {ok, id}.
        """
        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403
            body = request.get_json(force=True) or {}
            notes = (body.get("notes") or "").strip()
            if not notes:
                return jsonify({"error": "notes must not be empty"}), 400
            database.update_lb_problem(problem_id, notes)
            return jsonify({"ok": True, "id": problem_id})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_problems/<int:problem_id>", methods=["DELETE"])
    def lb_problems_delete(problem_id: int) -> Response:
        """Curator-only. Delete an lb_problems row by id.

        Returns:
            JSON {ok, id}.
        """
        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403
            database.delete_lb_problem(problem_id)
            return jsonify({"ok": True, "id": problem_id})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/folder_naming/standard/<int:lb>", methods=["GET"])
    def folder_naming_standard(lb: int) -> Response:
        """Return the canonical folder name for an LB entry.

        Returns:
            JSON: standard_name (str), lb_status (str|null), nft (bool).
        """
        try:
            from backend.folder_naming import build_standard_name
            result = database.get_entry(lb)
            entry = (result or {}).get("entry", {})
            date_str = entry.get("date_str") or ""
            location = (entry.get("location") or "").strip()
            lb_status = database.get_lb_status(lb)
            standard_name = build_standard_name(lb, date_str, location, lb_status)
            return jsonify({
                "standard_name": standard_name,
                "lb_status": lb_status,
                "nft": lb_status == "private",
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/db/backup", methods=["POST"])
    def db_backup() -> Response:
        """Create a manual DB backup. Body: {reason} (optional)."""
        global _last_backup_at
        with _backup_lock:  # #3 — rate-limit to once per 60 s
            now = time.monotonic()
            if now - _last_backup_at < 60:
                return jsonify({"error": "rate_limited",
                                "message": "Please wait 60 s between manual backups"}), 429
            _last_backup_at = now
        try:
            body = request.get_json(silent=True) or {}
            reason = str(body.get("reason", "manual"))[:100]  # #8
            path = database.backup_database(reason=reason)
            size = path.stat().st_size
            return jsonify({"ok": True, "path": str(path), "size_bytes": size})
        except Exception:
            _log.exception("db_backup failed")  # #9
            return jsonify({"error": "internal_error"}), 500

    # ── Curator mode (local flag) ──────────────────────────────────────────────

    @app.route("/api/curator", methods=["GET"])
    def curator_get() -> Response:
        """Return whether this install is flagged as the curator."""
        try:
            return jsonify({"is_curator": database.is_curator()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/curator", methods=["POST"])
    def curator_set() -> Response:
        """Toggle the local curator flag. Body: {enabled: bool}."""
        try:
            body = request.get_json(silent=True) or {}
            enabled = bool(body.get("enabled", False))
            database.set_curator(enabled)
            return jsonify({"ok": True, "is_curator": enabled})
        except Exception as exc:
            logging.getLogger(__name__).exception("curator_set failed")
            return jsonify({"error": str(exc)}), 500

    # ── Master data publish / subscribe ────────────────────────────────────────

    @app.route("/api/master/status", methods=["GET"])
    def master_status() -> Response:
        """Return the current master snapshot version and publish timestamp.

        Returns:
            JSON dict with master_version and master_published_at from the meta table.
        """
        try:
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT key, value FROM meta WHERE key IN ('master_version', 'master_published_at')"
            ).fetchall()
            return jsonify({r["key"]: r["value"] for r in rows})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/master/export", methods=["POST"])
    def master_export() -> Response:
        """Build a master-data snapshot + manifest. Curator-only.

        Body (optional): {reason}. Returns:
        {ok, path, manifest_path, manifest: {...}}.
        """
        try:
            if not database.is_curator():
                return jsonify({
                    "error": "curator_required",
                    "message": "Master export is only available in curator mode. "
                               "Enable Curator Mode in Setup tab.",
                }), 403
            body = request.get_json(silent=True) or {}
            reason = str(body.get("reason", "publish"))[:200]  # #8
            path, manifest = database.export_master_db(reason=reason)
            return jsonify({
                "ok": True,
                "path": str(path),
                "manifest_path": str(path) + ".manifest.json",
                "manifest": manifest,
            })
        except Exception:
            _log.exception("master_export failed")  # #9
            return jsonify({"error": "internal_error"}), 500

    @app.route("/api/master/github_release", methods=["POST"])
    def master_github_release() -> Response:
        """Create a GitHub release with real upload progress. Curator-only.

        Replaces gh CLI subprocess with direct GitHub REST API calls.
        Token is obtained via ``gh auth token``.  Assets (.db and manifest)
        are uploaded in 1 MB chunks so the GUI can display byte-accurate
        progress, matching the pattern used by the download flow.

        Body: {db_path, manifest_path, version, prev_published_at (optional)}.
        Returns: text/event-stream with events:
          data: {"type": "progress", "label": "...", "pct": N_or_null}
          data: {"type": "done", "tag": "...", "url": "..."}
          data: {"type": "error", "error": "...", "message": "..."}
        """
        import json as _json
        import queue
        import subprocess
        from datetime import datetime

        import requests as _req

        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403

        body = request.get_json(silent=True) or {}
        db_path_str = body.get("db_path", "")
        manifest_path_str = body.get("manifest_path", "")
        version = body.get("version", "")
        prev_published_at = body.get("prev_published_at")

        if not db_path_str or not manifest_path_str:
            return jsonify({"error": "db_path and manifest_path are required"}), 400

        _REPO = "kuddukan42/losslessbob"
        _GH_API = "https://api.github.com"
        ev_q: queue.Queue = queue.Queue()

        def _work() -> None:
            try:
                # Obtain token via gh CLI
                tok = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, timeout=15,
                )
                if tok.returncode != 0:
                    ev_q.put({"type": "error", "error": "gh_auth_failed",
                              "message": tok.stderr.strip() or "gh auth token failed"})
                    return
                token = tok.stdout.strip()
                if not token:
                    ev_q.put({"type": "error", "error": "gh_no_token",
                              "message": "gh auth token returned empty — run `gh auth login` first."})
                    return

                gh_hdr = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                }

                # Derive date for tag
                try:
                    date_str = version[:10] if version else datetime.now(UTC).strftime("%Y-%m-%d")
                except Exception:
                    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

                # Find an unused tag: master-YYYY-MM-DD[.N]
                ev_q.put({"type": "progress", "label": "Checking for existing releases…", "pct": None})
                base_tag = f"master-{date_str}"
                tag = None
                for suffix in ["", ".2", ".3", ".4", ".5"]:
                    candidate = f"{base_tag}{suffix}" if suffix else base_tag
                    chk = _req.get(
                        f"{_GH_API}/repos/{_REPO}/releases/tags/{candidate}",
                        headers=gh_hdr, timeout=15,
                    )
                    if chk.status_code == 404:
                        tag = candidate
                        break
                if tag is None:
                    ev_q.put({"type": "error", "error": "too_many_releases",
                              "message": f"5 releases already exist for {date_str}."})
                    return

                # Build release notes
                ev_q.put({"type": "progress", "label": "Building release notes…", "pct": None})
                notes = database.generate_release_notes(since_timestamp=prev_published_at)

                # Create the GitHub release
                ev_q.put({"type": "progress", "label": f"Creating release {tag}…", "pct": None})
                cr = _req.post(
                    f"{_GH_API}/repos/{_REPO}/releases",
                    headers=gh_hdr,
                    json={"tag_name": tag, "name": f"Master Update {date_str}", "body": notes},
                    timeout=30,
                )
                if not cr.ok:
                    msg = cr.json().get("message", cr.text[:300]) if cr.content else cr.reason
                    ev_q.put({"type": "error", "error": "create_failed", "message": msg})
                    return
                release = cr.json()
                # upload_url: "https://uploads.github.com/.../assets{?name,label}" — strip template
                upload_base = release["upload_url"].split("{")[0]
                release_url = release["html_url"]

                def _upload_asset(file_path_s: str, label: str) -> None:
                    fsize = os.path.getsize(file_path_s)
                    fmb = fsize / (1 << 20)
                    fname = Path(file_path_s).name
                    sent_ref = [0]

                    # A plain generator has no __len__, so requests can't determine
                    # Content-Length and falls back to Transfer-Encoding: chunked —
                    # which uploads.github.com rejects with a 400 Bad Request. A
                    # file-like object with __len__ lets requests send a real
                    # Content-Length while still reporting progress via read().
                    class _ProgressFile:
                        def __init__(self, path: str) -> None:
                            self._fh = open(path, "rb")

                        def __len__(self) -> int:
                            return fsize

                        def read(self, _amt: int = -1) -> bytes:
                            chunk = self._fh.read(1 << 20)  # 1 MB chunks
                            if chunk:
                                sent_ref[0] += len(chunk)
                                pct = int(sent_ref[0] * 100 / fsize) if fsize else 100
                                ev_q.put({
                                    "type": "progress",
                                    "label": (
                                        f"Uploading {label}… {pct}%"
                                        f"  ({sent_ref[0] / (1<<20):.1f} / {fmb:.0f} MB)"
                                    ),
                                    "pct": pct,
                                })
                            return chunk

                        def close(self) -> None:
                            self._fh.close()

                    body = _ProgressFile(file_path_s)
                    try:
                        up = _req.post(
                            upload_base,
                            params={"name": fname},
                            data=body,
                            headers={
                                "Authorization": f"token {token}",
                                "Accept": "application/vnd.github+json",
                                "Content-Type": "application/octet-stream",
                                "Content-Length": str(fsize),
                            },
                            timeout=600,
                        )
                    finally:
                        body.close()
                    up.raise_for_status()

                db_fname = Path(db_path_str).name
                mf_fname = Path(manifest_path_str).name
                ev_q.put({"type": "progress", "label": f"Uploading {db_fname}…", "pct": 0})
                _upload_asset(db_path_str, db_fname)

                ev_q.put({"type": "progress", "label": f"Uploading {mf_fname}…", "pct": 0})
                _upload_asset(manifest_path_str, mf_fname)

                # Stamp the live DB so the GUI reflects what was just published —
                # the snapshot's meta rows only existed inside the exported .db.
                try:
                    with open(manifest_path_str, encoding="utf-8") as mf:
                        manifest_data = _json.load(mf)
                    database.set_meta(
                        "master_version", manifest_data.get("master_version", version)
                    )
                    database.set_meta(
                        "master_published_at", manifest_data.get("master_published_at", "")
                    )
                except Exception:
                    _log.exception("Failed to record published master_version/master_published_at")

                ev_q.put({"type": "done", "tag": tag, "url": release_url})

            except FileNotFoundError:
                ev_q.put({"type": "error", "error": "gh_not_found",
                          "message": "gh CLI not found — install GitHub CLI first."})
            except Exception as exc:
                ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

        def _stream():
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {"type": "error", "error": "timeout",
                          "message": "Upload timed out after 680 s."}
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

        return Response(
            stream_with_context(_stream()),
            content_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    @app.route("/api/master/import", methods=["POST"])
    def master_import() -> Response:
        """Apply a master snapshot to the local DB, preserving user data.

        Body: {path: "/abs/path/to/snapshot.db"}. Manifest sidecar must live
        alongside the snapshot at <path>.manifest.json.

        Note: intentionally not curator-gated — curators publish, anyone installs.
        """
        try:
            body = request.get_json(silent=True) or {}
            path = body.get("path")
            if not path:
                return jsonify({"error": "missing_path"}), 400
            snapshot_path = Path(path).resolve()
            if snapshot_path.suffix.lower() != ".db":
                return jsonify({"error": "path_not_allowed",
                                "message": "Snapshot must be a .db file"}), 400
            summary = database.import_master_db(str(snapshot_path))
            return jsonify({"ok": True, **summary})
        except FileNotFoundError as exc:
            return jsonify({"error": "not_found", "message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": "validation_error", "message": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": "schema_too_new", "message": str(exc)}), 400
        except sqlite3.Error as exc:
            _log.exception("master_import: SQLite error")
            return jsonify({"error": "db_error", "message": str(exc)}), 500
        except Exception as exc:
            _log.exception("master_import failed")
            return jsonify({"error": "internal_error", "message": str(exc)}), 500

    @app.route("/api/master/github_check", methods=["GET"])
    def master_github_check() -> Response:
        """Check GitHub Releases for a master snapshot newer than the local one.

        Returns:
            JSON dict with ``available`` (bool) plus ``tag``, ``remote_version``,
            ``remote_published_at``, ``local_version``, ``local_published_at``,
            ``asset_name``, ``asset_size``, ``release_url`` when a release is found.
            If no usable release exists, ``available`` is ``false`` with a
            human-readable ``message``.
        """
        import requests as _req

        _REPO = "kuddukan42/losslessbob"
        try:
            resp = _req.get(
                f"https://api.github.com/repos/{_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"}, timeout=15,
            )
            if resp.status_code == 404:
                return jsonify({"available": False, "message": "No master releases found on GitHub yet."})
            resp.raise_for_status()
            release = resp.json()
            tag = release.get("tag_name", "?")
            assets = release.get("assets", [])

            db_asset = next(
                (a for a in assets
                 if a["name"].endswith(".db") and not a["name"].endswith(".manifest.json.db")),
                None,
            )
            if not db_asset:
                return jsonify({"available": False, "message": f"No .db asset found in release {tag}."})

            manifest_name = db_asset["name"] + ".manifest.json"
            manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
            if not manifest_asset:
                return jsonify({"available": False,
                                "message": f"Manifest sidecar not found in release {tag}."})

            mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
            mresp.raise_for_status()
            manifest = mresp.json()
            remote_version = manifest.get("master_version", "")
            remote_published_at = manifest.get("master_published_at", "")

            conn = database.get_connection()
            rows = conn.execute(
                "SELECT key, value FROM meta WHERE key IN ('master_version', 'master_published_at')"
            ).fetchall()
            local = {r["key"]: r["value"] for r in rows}

            return jsonify({
                "available": bool(remote_version) and remote_version != local.get("master_version", ""),
                "tag": tag,
                "remote_version": remote_version,
                "remote_published_at": remote_published_at,
                "local_version": local.get("master_version", ""),
                "local_published_at": local.get("master_published_at", ""),
                "asset_name": db_asset["name"],
                "asset_size": db_asset.get("size", 0),
                "release_url": release.get("html_url", ""),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/master/github_install", methods=["POST"])
    def master_github_install() -> Response:
        """Download and apply the latest master snapshot from GitHub Releases.

        Streams progress via ``text/event-stream``, mirroring
        ``/api/master/github_release``'s event shape:
          data: {"type": "progress", "label": "...", "pct": N_or_null}
          data: {"type": "done", "summary": {...}}
          data: {"type": "error", "error": "...", "message": "..."}
        """
        import hashlib
        import json as _json
        import queue

        import requests as _req

        _REPO = "kuddukan42/losslessbob"
        ev_q: queue.Queue = queue.Queue()

        def _work() -> None:
            try:
                ev_q.put({"type": "progress", "label": "Checking GitHub for latest release…", "pct": None})
                resp = _req.get(
                    f"https://api.github.com/repos/{_REPO}/releases/latest",
                    headers={"Accept": "application/vnd.github+json"}, timeout=15,
                )
                if resp.status_code == 404:
                    ev_q.put({"type": "error", "error": "no_releases",
                              "message": "No master releases found on GitHub yet."})
                    return
                resp.raise_for_status()
                release = resp.json()
                tag = release.get("tag_name", "?")
                assets = release.get("assets", [])

                db_asset = next(
                    (a for a in assets
                     if a["name"].endswith(".db") and not a["name"].endswith(".manifest.json.db")),
                    None,
                )
                if not db_asset:
                    ev_q.put({"type": "error", "error": "no_db_asset",
                              "message": f"No .db asset found in release {tag}."})
                    return

                manifest_name = db_asset["name"] + ".manifest.json"
                manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
                if not manifest_asset:
                    ev_q.put({"type": "error", "error": "no_manifest",
                              "message": f"Manifest sidecar not found in release {tag}."})
                    return

                ev_q.put({"type": "progress", "label": f"Downloading manifest for {tag}…", "pct": None})
                mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
                mresp.raise_for_status()
                manifest = mresp.json()

                dest_dir = DATA_DIR / "imports"
                dest_dir.mkdir(parents=True, exist_ok=True)
                db_dest = dest_dir / db_asset["name"]
                manifest_dest = dest_dir / manifest_name

                total_bytes = db_asset.get("size", 0)
                total_mb = total_bytes / (1 << 20)
                ev_q.put({"type": "progress",
                          "label": f"Downloading {db_asset['name']} ({total_mb:.0f} MB)…", "pct": 0})
                dresp = _req.get(db_asset["browser_download_url"], stream=True, timeout=600)
                dresp.raise_for_status()

                downloaded = 0
                with open(db_dest, "wb") as fh:
                    for chunk in dresp.iter_content(chunk_size=1 << 18):
                        if chunk:
                            fh.write(chunk)
                            downloaded += len(chunk)
                            if total_bytes:
                                pct = downloaded * 100 // total_bytes
                                dl_mb = downloaded / (1 << 20)
                                ev_q.put({
                                    "type": "progress",
                                    "label": f"Downloading… {pct}%  ({dl_mb:.1f} / {total_mb:.0f} MB)",
                                    "pct": pct,
                                })

                ev_q.put({"type": "progress", "label": "Verifying checksum…", "pct": None})
                sha = hashlib.sha256()
                with open(db_dest, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        sha.update(chunk)
                expected_sha = manifest.get("sha256", "")
                if sha.hexdigest() != expected_sha:
                    db_dest.unlink(missing_ok=True)
                    ev_q.put({"type": "error", "error": "sha256_mismatch",
                              "message": "SHA256 mismatch — download may be corrupt. Please try again."})
                    return

                with open(manifest_dest, "w", encoding="utf-8") as fh:
                    _json.dump(manifest, fh, indent=2)

                ev_q.put({"type": "progress", "label": "Applying update to local database…", "pct": None})
                summary = database.import_master_db(str(db_dest))
                ev_q.put({"type": "done", "summary": summary})

            except Exception as exc:
                ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

        def _stream():
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {"type": "error", "error": "timeout", "message": "Update timed out after 680 s."}
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

        return Response(
            stream_with_context(_stream()),
            content_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    # ── lb_alias endpoints ────────────────────────────────────────────────────

    @app.route("/api/lb_alias", methods=["GET"])
    def lb_alias_list():
        """List all lb_alias rows, optionally filtered by canonical_lb.

        Query param: canonical_lb (int, optional)
        """
        try:
            canonical = request.args.get("canonical_lb", type=int)
            return jsonify(database.get_lb_aliases(canonical))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_alias", methods=["POST"])
    def lb_alias_add():
        """Add an alias mapping. Curator-only.

        Body: {alias_lb, canonical_lb, relationship, note}
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        body = request.get_json(force=True) or {}
        try:
            result = database.add_lb_alias(
                alias_lb=int(body["alias_lb"]),
                canonical_lb=int(body["canonical_lb"]),
                relationship=body.get("relationship", "duplicate"),
                note=body.get("note", ""),
            )
            return jsonify(result), 201
        except (KeyError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_alias/<int:alias_lb>", methods=["DELETE"])
    def lb_alias_delete(alias_lb):
        """Remove an alias entry. Curator-only."""
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            database.delete_lb_alias(alias_lb)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/lb_alias/resolve", methods=["GET"])
    def lb_alias_resolve():
        """Resolve a list of LB numbers through alias collapse.

        Query param: lbs=1,2,3
        """
        raw = request.args.get("lbs", "")
        try:
            lbs = [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            return jsonify({"error": "invalid lbs param"}), 400
        try:
            return jsonify({"canonical": database.resolve_aliases(lbs)})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── folder_lb_link endpoints ──────────────────────────────────────────────

    @app.route("/api/folder_link", methods=["GET"])
    def folder_link_get():
        """Get the sticky LB link for a folder path.

        Query param: path=...
        """
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path required"}), 400
        try:
            row = database.get_folder_link(path)
            return jsonify(row or {})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/folder_link", methods=["PUT"])
    def folder_link_set():
        """Set or replace a folder→LB link.

        Body: {folder_path, lb_number, note}
        """
        body = request.get_json(force=True) or {}
        path = body.get("folder_path", "")
        lb = body.get("lb_number")
        if not path or lb is None:
            return jsonify({"error": "folder_path and lb_number required"}), 400
        try:
            database.set_folder_link(path, int(lb), body.get("note", ""))
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/folder_link", methods=["DELETE"])
    def folder_link_delete():
        """Clear a folder→LB link.

        Query param: path=...
        """
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path required"}), 400
        try:
            database.delete_folder_link(path)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Map feature routes — added 2026-05-18 ──────────────────────────────────────

    @app.route("/map")
    def serve_map():
        """Serve gui/resources/map.html for both QWebEngineView and system browser."""
        resources_dir = (Path(__file__).parent.parent / "gui" / "resources").resolve()
        return send_from_directory(str(resources_dir), "map.html")

    @app.route("/leaflet/<path:filename>")
    def serve_leaflet(filename: str):
        """Serve bundled Leaflet JS/CSS assets from gui/resources/leaflet/."""
        leaflet_dir = (Path(__file__).parent.parent / "gui" / "resources" / "leaflet").resolve()
        return send_from_directory(str(leaflet_dir), filename)

    @app.route("/api/entries/by_lb_list")
    def api_entries_by_lb_list():
        """Return search-compatible entry dicts for a comma-separated list of LB numbers.

        Query params:
            lbs (str): comma-separated integer LB numbers (e.g. "1234,5678,91011").

        Returns:
            JSON list of entry dicts matching the requested LB numbers.
        """
        raw = request.args.get("lbs", "")
        try:
            lb_numbers = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            return jsonify({"error": "invalid lbs parameter — must be comma-separated integers"}), 400
        lb_numbers = lb_numbers[:500]
        try:
            results = database.get_entries_by_lb_list(lb_numbers)
        except Exception:
            _log.exception("api_entries_by_lb_list failed")
            return jsonify({"error": "internal_error"}), 500
        return jsonify(results)

    @app.route("/api/map/data")
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

    @app.route("/api/geocode/run", methods=["POST"])
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

        with _geocoder._lock:
            if _geocoder._progress.get("running"):
                return jsonify({"error": "already running"}), 409

        body = request.get_json(silent=True) or {}
        retry_failed = bool(body.get("retry_failed", False))
        limit = body.get("limit")

        t = threading.Thread(
            target=_geocoder.run_batch,
            kwargs={"limit": limit, "retry_failed": retry_failed},
            daemon=True,
        )
        t.start()
        return jsonify({"status": "started"})

    @app.route("/api/geocode/status")
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

    @app.route("/api/geocode/stats")
    def api_geocode_stats():
        """Return cache and coverage stats for the geocoder tab.

        Returns:
            JSON dict with keys: total_cached, geocoded, failed, manual,
            entries_total, entries_covered, pct_covered.
        """
        try:
            conn = database.get_connection()
            row = conn.execute("""
                SELECT
                    COUNT(*)                                          AS total_cached,
                    SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) AS geocoded,
                    SUM(CASE WHEN lat IS NULL     THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN manual_override = 1 THEN 1 ELSE 0 END) AS manual
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

    @app.route("/api/geocode/location", methods=["POST"])
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

    @app.route("/api/geocode/purge", methods=["POST"])
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

    @app.route("/api/geocode/locations")
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

    # ── Admin page ───────────────────────────────────────────────────────────

    @app.route("/admin")
    def admin_page() -> Response:
        """Serve the mobile-friendly admin control panel."""
        admin_html = Path(__file__).parent / "admin.html"
        return send_from_directory(str(admin_html.parent), admin_html.name)

    @app.route("/api/admin/status", methods=["GET"])
    def admin_status() -> Response:
        """Return combined server/DB/scraper status for the admin dashboard.

        Returns:
            JSON dict with db stats, scrape status, import status, master stats,
            and server uptime in seconds.
        """
        try:
            result: dict = {}
            result["uptime_seconds"] = round(time.monotonic() - _process_start_time)
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
                conn = database.get_connection()
                total = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
                conflicts = conn.execute(
                    "SELECT COUNT(*) FROM lb_master WHERE status='conflict'"
                ).fetchone()[0]
                result["master"] = {"total": total, "conflicts": conflicts}
            except Exception:
                result["master"] = None
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/admin/restart", methods=["POST"])
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

    @app.route("/api/checksums/reconcile_audio", methods=["POST"])
    def reconcile_audio():
        """Validate proposed audio file renames against the filesystem.

        Accepts a list of {checksum, input_filename, db_filename, folder} dicts.
        Returns each proposal annotated with status: ok | from_missing | to_exists.
        Only audio file extensions are processed; others are silently skipped.
        """
        try:
            proposals_in = (request.get_json() or {}).get("proposals", [])
            proposals_out = []
            for p in proposals_in:
                db_fn = p.get("db_filename", "")
                if Path(db_fn).suffix.lower() not in _AUDIO_EXTS:
                    continue
                folder = Path(p["folder"])
                from_path = folder / p["input_filename"]
                to_path = folder / db_fn
                if not from_path.exists():
                    status = "from_missing"
                elif to_path.exists() and to_path.resolve() != from_path.resolve():
                    status = "to_exists"
                else:
                    status = "ok"
                proposals_out.append({
                    **p,
                    "from": str(from_path),
                    "to": str(to_path),
                    "status": status,
                })
            return jsonify({"proposals": proposals_out})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/checksums/apply_reconcile_audio", methods=["POST"])
    def apply_reconcile_audio():
        """Apply a list of {from, to} file renames on disk.

        Returns {applied, errors} where applied is the count of successful renames.
        """
        try:
            renames = (request.get_json() or {}).get("renames", [])
            applied = 0
            errors = []
            for r in renames:
                try:
                    Path(r["from"]).rename(r["to"])
                    applied += 1
                except Exception as e:
                    errors.append(f"{Path(r['from']).name}: {e}")
            return jsonify({"applied": applied, "errors": errors})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Fingerprint ───────────────────────────────────────────────────────────

    @app.route("/api/fingerprint/build", methods=["POST"])
    def fp_build() -> Response:
        """Start background fingerprint DB build over the whole collection.

        Returns {ok, total} or 409 if already running.
        """
        with _fp_build_lock:
            if _fp_build_state["status"] not in ("idle", "done", "error"):
                return jsonify({"error": "Build already running"}), 409
            _fp_build_state["status"] = "running"
        try:
            data    = request.get_json(silent=True) or {}
            force   = bool(data.get("force", False))
            folders = data.get("folders")  # optional [{disk_path, lb_number}, ...]
            if folders:
                rows = [{"disk_path": f["disk_path"], "lb_number": int(f["lb_number"])}
                        for f in folders if f.get("disk_path")]
            else:
                rows = database.get_collection()
            _fp_build_stop.clear()
            threading.Thread(
                target=_do_fp_build, args=(rows, force), daemon=True
            ).start()
            return jsonify({"ok": True, "total": len(rows)})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/build/status", methods=["GET"])
    def fp_build_status() -> Response:
        """Return current state of the fingerprint build worker."""
        with _fp_build_lock:
            return jsonify(dict(_fp_build_state))

    @app.route("/api/fingerprint/build/stop", methods=["POST"])
    def fp_build_stop() -> Response:
        """Signal the fingerprint build worker to stop after the current file."""
        _fp_build_stop.set()
        with _fp_build_lock:
            _fp_build_state["stop_requested"] = True
        return jsonify({"ok": True})

    @app.route("/api/fingerprint/build/queue", methods=["GET"])
    def fp_build_queue() -> Response:
        """Return pending count and preview of upcoming files in the build queue.

        Returns {pending: N, preview: [up to 10 filenames]}.
        """
        with _fp_build_lock:
            total   = _fp_build_state["total"]
            done    = _fp_build_state["done"]
            preview = list(_fp_build_state.get("queue_preview", []))
        return jsonify({"pending": max(0, total - done), "preview": preview})

    @app.route("/api/fingerprint/lb_numbers", methods=["GET"])
    def fp_lb_numbers() -> Response:
        """Return {lb_number: n_hashes} for every lb_number that has fingerprints.

        Used by the Collection tab to display the Fingerprinted column without
        a per-row lookup.  Returns an empty dict when fingerprints.db is empty.
        """
        try:
            from backend import fingerprint as _fp
            conn = _fp._get_fp_conn()
            rows = conn.execute(
                "SELECT lb_number, SUM(n_hashes) AS n FROM audio_tracks GROUP BY lb_number"
            ).fetchall()
            return jsonify({str(r["lb_number"]): r["n"] for r in rows})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/stats", methods=["GET"])
    def fp_stats() -> Response:
        """Return {track_count, hash_count} from fingerprints.db."""
        try:
            from backend import fingerprint as _fp
            return jsonify(_fp.get_fp_stats())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/identify", methods=["POST"])
    def fp_identify() -> Response:
        """Identify an audio file against the fingerprint DB.

        Body: {file_path: "/abs/path/to/file"}
        Returns: JSON list of {track_id, lb_number, file_path, score, confident}.
        """
        try:
            from backend import fingerprint as _fp
            data = request.get_json() or {}
            file_path = data.get("file_path", "")
            if not file_path:
                return jsonify({"error": "file_path required"}), 400
            p = Path(file_path)
            if not p.exists():
                return jsonify({"error": f"File not found: {file_path}"}), 404
            results = _fp.identify_file(p)
            return jsonify(results)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/duplicates/scan", methods=["POST"])
    def fp_dup_scan() -> Response:
        """Start background duplicate-recording scan.

        Returns {ok} or 409 if already running.
        """
        with _fp_dup_lock:
            if _fp_dup_state["status"] not in ("idle", "done", "error"):
                return jsonify({"error": "Scan already running"}), 409
            _fp_dup_state["status"] = "running"
        try:
            _fp_dup_stop.clear()
            with _fp_dup_lock:
                _fp_dup_state["stop_requested"] = False
            threading.Thread(
                target=_do_fp_dup_scan, daemon=True
            ).start()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/duplicates", methods=["GET"])
    def fp_duplicates() -> Response:
        """Return current state of the duplicate scan, including results when done."""
        with _fp_dup_lock:
            return jsonify(dict(_fp_dup_state))

    @app.route("/api/fingerprint/duplicates/scan/stop", methods=["POST"])
    def fp_dup_scan_stop() -> Response:
        """Signal the duplicate scan worker to stop after the current operation."""
        _fp_dup_stop.set()
        with _fp_dup_lock:
            _fp_dup_state["stop_requested"] = True
        return jsonify({"ok": True})

    @app.route("/api/fingerprint/collection_by_date", methods=["GET"])
    def fp_collection_by_date() -> Response:
        """Return My Collection entries whose date_str matches the given date.

        Query param: date=YYYY-MM-DD
        Returns [{lb_number, folder_name, disk_path, date_str, location}].
        """
        date = request.args.get("date", "").strip()
        if not date:
            return jsonify({"error": "date required"}), 400
        try:
            all_rows = database.get_collection()
            keep = ("lb_number", "folder_name", "disk_path", "date_str", "location")
            rows = [
                {k: r.get(k) for k in keep}
                for r in all_rows
                if r.get("date_str") == date
            ]
            return jsonify(rows)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/identify_folder", methods=["POST"])
    def fp_identify_folder() -> Response:
        """Start background identification of all audio files in a folder.

        Body: {folder: "/abs/path"}
        Returns {ok} or 409 if already running.
        """
        with _fp_id_lock:
            if _fp_id_state["status"] not in ("idle", "done", "error"):
                return jsonify({"error": "Already running"}), 409
            _fp_id_state["status"] = "running"
        try:
            data = request.get_json() or {}
            folder = data.get("folder", "").strip()
            if not folder:
                return jsonify({"error": "folder required"}), 400
            p = Path(folder)
            if not p.is_dir():
                return jsonify({"error": f"Not a directory: {folder}"}), 400
            _fp_id_stop.clear()
            with _fp_id_lock:
                _fp_id_state["stop_requested"] = False
            threading.Thread(
                target=_do_fp_identify_folder, args=(folder,), daemon=True
            ).start()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/fingerprint/identify_folder/status", methods=["GET"])
    def fp_identify_folder_status() -> Response:
        """Return current state of the folder-identify worker."""
        with _fp_id_lock:
            return jsonify(dict(_fp_id_state))

    @app.route("/api/fingerprint/identify_folder/stop", methods=["POST"])
    def fp_identify_folder_stop() -> Response:
        """Signal the folder-identify worker to stop after the current file."""
        _fp_id_stop.set()
        with _fp_id_lock:
            _fp_id_state["stop_requested"] = True
        return jsonify({"ok": True})

    # ── Collection Mounts & Routes (Pipeline Step 5) ─────────────────────────

    @app.route("/api/collection/mounts", methods=["GET"])
    def collection_mounts_list() -> Response:
        """List all configured storage mounts with live online status and disk usage."""
        try:
            import concurrent.futures as _cf

            from backend.filer import _path_reachable, get_disk_usage_stats
            mounts = database.get_collection_mounts()
            if mounts:
                with _cf.ThreadPoolExecutor(max_workers=len(mounts)) as ex:
                    online_flags = list(ex.map(lambda m: _path_reachable(m["root_path"]), mounts))
                for mount, online in zip(mounts, online_flags, strict=True):
                    mount["online"] = online
                    mount.update(get_disk_usage_stats(mount["root_path"], online))
            return jsonify({"mounts": mounts})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/mounts", methods=["POST"])
    def collection_mounts_create() -> Response:
        """Create a new storage mount. Body: {label, root_path, notes?}"""
        try:
            from backend.filer import normalise_path
            data = request.get_json() or {}
            label = (data.get("label") or "").strip()
            root_path = (data.get("root_path") or "").strip()
            if not label or not root_path:
                return jsonify({"error": "label and root_path are required"}), 400
            mount_id = database.add_collection_mount(
                label, normalise_path(root_path), data.get("notes")
            )
            return jsonify({"ok": True, "id": mount_id})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/mounts/<int:mount_id>", methods=["PATCH"])
    def collection_mounts_update(mount_id: int) -> Response:
        """Update label/root_path/notes for a mount."""
        try:
            from backend.filer import normalise_path
            data = request.get_json() or {}
            if "root_path" in data and data["root_path"]:
                data["root_path"] = normalise_path(data["root_path"])
            database.update_collection_mount(mount_id, data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/mounts/<int:mount_id>", methods=["DELETE"])
    def collection_mounts_delete(mount_id: int) -> Response:
        """Delete a mount. Returns 409 if any routes reference it."""
        try:
            result = database.delete_collection_mount(mount_id)
            if not result["ok"]:
                return jsonify(result), 409
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/routes", methods=["GET"])
    def collection_routes_list() -> Response:
        """List all year routes joined with mount label and root_path."""
        try:
            return jsonify({"routes": database.get_collection_routes()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/routes/bulk", methods=["POST"])
    def collection_routes_bulk() -> Response:
        """Upsert routes for a year range. Body: {year_from, year_to, mount_id, sub_path}"""
        try:
            data = request.get_json() or {}
            year_from = data.get("year_from")
            year_to = data.get("year_to")
            mount_id = data.get("mount_id")
            sub_path = data.get("sub_path", "")
            if year_from is None or year_to is None or mount_id is None:
                return jsonify({"error": "year_from, year_to, mount_id required"}), 400
            year_from, year_to = int(year_from), int(year_to)
            if year_from > year_to:
                return jsonify({"error": "year_from must be <= year_to"}), 400
            count = database.upsert_collection_routes(
                year_from, year_to, int(mount_id), sub_path or ""
            )
            return jsonify({"ok": True, "rows_written": count})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/routes/<int:year>", methods=["DELETE"])
    def collection_routes_delete(year: int) -> Response:
        """Remove the route for a single year."""
        try:
            database.delete_collection_route(year)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/routes/preview/<int:year>", methods=["GET"])
    def collection_routes_preview(year: int) -> Response:
        """Dry-run: show what year YYYY would resolve to without filing anything."""
        try:
            from backend.filer import _path_reachable
            with database.get_connection() as conn:
                route = conn.execute(
                    """SELECT r.year, r.sub_path, m.id, m.label, m.root_path
                       FROM collection_routes r
                       JOIN collection_mounts m ON m.id = r.mount_id
                       WHERE r.year = ?""",
                    (year,),
                ).fetchone()
            if route is None:
                return jsonify({
                    "ok": False,
                    "year": year,
                    "error": f"No route configured for {year}",
                    "error_code": "no_route",
                })
            from pathlib import Path as _Path
            root = route["root_path"]
            sub = route["sub_path"] or ""
            dest_parent = str(_Path(root) / sub) if sub else root
            return jsonify({
                "ok": True,
                "year": year,
                "mount_label": route["label"],
                "mount_root": root,
                "sub_path": sub,
                "dest_parent": dest_parent,
                "mount_online": _path_reachable(root),
                "error": None,
                "error_code": None,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Collection Integrity Monitor (TODO-111) ──────────────────────────────

    @app.route("/api/collection/integrity/scan", methods=["POST"])
    def collection_integrity_scan_start() -> Response:
        """Start a background integrity scan. Body: {mount_id?: int} (omit = whole collection)."""
        try:
            from backend import integrity_monitor
            data = request.get_json(silent=True) or {}
            mount_id = data.get("mount_id")
            started = integrity_monitor.start_scan_async(
                int(mount_id) if mount_id is not None else None
            )
            if not started:
                return jsonify({"ok": False, "error": "A scan is already running"}), 409
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/integrity/scan/cancel", methods=["POST"])
    def collection_integrity_scan_cancel() -> Response:
        """Request cancellation of the running integrity scan, if any."""
        try:
            from backend import integrity_monitor
            cancelled = integrity_monitor.cancel_scan()
            return jsonify({"ok": cancelled})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/integrity/scan/status", methods=["GET"])
    def collection_integrity_scan_status() -> Response:
        """Return progress of the current/last integrity scan for GUI polling."""
        try:
            from backend import integrity_monitor
            return jsonify(integrity_monitor.get_scan_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/integrity/scan/history", methods=["GET"])
    def collection_integrity_scan_history() -> Response:
        """Return recent integrity scan history. Query param: mount_id (optional)."""
        try:
            mount_id = request.args.get("mount_id")
            history = database.get_integrity_scan_history(
                mount_id=int(mount_id) if mount_id else None
            )
            return jsonify({"history": history})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/integrity/summary", methods=["GET"])
    def collection_integrity_summary() -> Response:
        """Return per-mount integrity status counts for MountCard badges."""
        try:
            return jsonify(database.get_mount_integrity_summary())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/integrity/status", methods=["GET"])
    def collection_integrity_status() -> Response:
        """Return per-LB integrity status rows. Query params: mount_id, status (optional)."""
        try:
            mount_id = request.args.get("mount_id")
            status = request.args.get("status")
            rows = database.get_collection_integrity_status(
                mount_id=int(mount_id) if mount_id else None,
                status=status or None,
            )
            return jsonify({"status": rows})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/pipeline/file/start", methods=["POST"])
    def pipeline_file_start() -> Response:
        """Start step 5: file one folder into the collection (async, progress-tracked).

        Body: {folders: [{path: str, lb_number: int, mount_id?: int}]}
        Only the first entry is processed; mount_id, if given, overrides the
        year-routed mount (see the Collect mount picker). Returns {ok, error?,
        error_code?} immediately — poll /api/pipeline/file/status for progress
        and the final result.
        """
        try:
            from backend.filer import start_file_job
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"ok": False, "error": "folders list required", "error_code": "bad_input"}), 400
            item = folders[0]
            path = item.get("path", "")
            lb = item.get("lb_number")
            mount_id = item.get("mount_id")
            if not path or not lb:
                return jsonify({
                    "ok": False,
                    "error": "path and lb_number are required",
                    "error_code": "bad_input",
                }), 400
            file_mode = database.get_meta("pipeline_file_mode") or "move"
            result = start_file_job(
                int(lb), path, file_mode=file_mode,
                mount_id_override=int(mount_id) if mount_id is not None else None,
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/pipeline/file/status", methods=["GET"])
    def pipeline_file_status() -> Response:
        """Poll progress of the filing job started via /api/pipeline/file/start."""
        from backend.filer import get_file_job_status
        return jsonify(get_file_job_status())

    @app.route("/api/pipeline/file/preview", methods=["POST"])
    def pipeline_file_preview() -> Response:
        """Pre-flight check: resolve destinations without moving anything.

        Body: {folders: [{path: str, lb_number: int, mount_id?: int}, ...]}
        mount_id, if given, previews filing under that mount instead of the
        year-routed default.
        """
        try:
            from backend.filer import _path_reachable, resolve_destination_for_lb
            data = request.get_json() or {}
            folders = data.get("folders", [])
            results = []
            for item in folders:
                path = item.get("path", "")
                lb = item.get("lb_number")
                mount_id = item.get("mount_id")
                if not path or not lb:
                    results.append({
                        "path": path,
                        "lb_number": lb,
                        "ok": False,
                        "error": "path and lb_number required",
                        "error_code": "bad_input",
                    })
                    continue
                r = resolve_destination_for_lb(
                    int(lb), path,
                    mount_id_override=int(mount_id) if mount_id is not None else None,
                )
                r["path"] = path
                r["lb_number"] = lb
                if r["ok"]:
                    r["mount_online"] = _path_reachable(r["mount_root"])
                results.append(r)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def _file_blocked_label(error_code: str | None) -> str:
        return {
            "no_date":       "No date",
            "no_route":      "No route",
            "mount_offline": "Mount offline",
            "dest_exists":   "Already exists",
            "db_error":      "DB error",
        }.get(error_code or "", "Blocked")

    def _pipeline_process_folder(folder_path: str, steps: set) -> dict:
        """Run one or more pipeline steps on a single folder and return a PipelineRow dict."""
        from backend.folder_naming import (
            apply_nft_suffix,
            strip_nft_suffix,
        )
        from backend.folder_naming import (
            build_standard_name as _build_name,
        )

        folder = Path(folder_path)
        folder_name = folder.name

        # Rename/LBDIR/File all key off the LB# resolved by Lookup.  Force the
        # lookup step into any run that includes a downstream step so the link
        # between stages never depends on the caller sending the right combo.
        if steps & {"rename", "lbdir", "file"}:
            steps = steps | {"lookup"}

        row: dict = {
            "folder": folder_path,
            "folderName": folder_name,
            "verify":  {"status": "mute", "label": "—"},
            "lookup":  {"status": "mute", "label": "—", "lb_number": None},
            "rename":  {"status": "mute", "label": "—", "proposed": None},
            "lbdir":   {"status": "mute", "label": "—"},
            "file":    {"status": "mute", "label": "—", "error": None, "error_code": None},
            "severity": "attn",
            "errors": [],
        }

        if not folder.exists() or not folder.is_dir():
            row["errors"].append({"step": "verify", "message": "Folder not found"})
            row["verify"] = {"status": "bad", "label": "Missing"}
            return row

        lb_number: int | None = None

        # ── Step 1: Verify ────────────────────────────────────────────────────
        if "verify" in steps:
            vr = checksum_utils.verify_folder(folder_path)
            _vcounts = {
                "total":        vr.get("total", 0),
                "pass":         vr.get("pass", 0),
                "missing":      vr.get("missing", 0),
                "mismatch":     vr.get("mismatch", 0),
                "extra":        vr.get("extra", 0),
                "no_checksums": vr.get("status") == "no_checksums",
                "files":        vr.get("files", []),
            }
            if vr.get("error"):
                row["verify"] = {"status": "bad", "label": "Error", **_vcounts}
                row["errors"].append({"step": "verify", "message": vr["error"]})
            elif vr["status"] == "pass":
                row["verify"] = {"status": "ok", "label": "Pass", **_vcounts}
            elif vr["status"] in ("incomplete", "no_checksums"):
                row["verify"] = {"status": "warn", "label": "Incomplete", **_vcounts}
            elif vr["status"] == "shntool_missing":
                row["verify"] = {"status": "warn", "label": "No shntool", "shntool_missing": True, **_vcounts}
            else:
                row["verify"] = {"status": "bad", "label": "Mismatch", **_vcounts}

        # ── Step 2: Lookup ────────────────────────────────────────────────────
        if "lookup" in steps:
            chk_parts: list[str] = []
            _chk_exts = {".ffp", ".md5", ".st5"}
            for f in sorted(folder.rglob("*")):
                if f.is_file() and f.suffix.lower() in _chk_exts:
                    try:
                        chk_parts.append(f.read_text(errors="ignore"))
                    except OSError:
                        pass

            if not chk_parts:
                row["lookup"] = {"status": "warn", "label": "No checksums", "lb_number": None}
            else:
                chk_text = "\n".join(chk_parts)
                parsed = database.parse_checksum_text(chk_text)
                if not parsed:
                    row["lookup"] = {"status": "bad", "label": "Not found", "lb_number": None}
                else:
                    summary, detail = database.lookup_checksums(parsed)
                    alias_map = {
                        r["alias_lb"]: r["canonical_lb"]
                        for r in database.get_lb_aliases()
                    }
                    for d in detail:
                        d["is_alias_lb"] = d["lb_number"] in alias_map
                        d["canonical_lb"] = alias_map.get(d["lb_number"])
                    raw_lb_list: list[int] = summary.get("lb_numbers_found", [])
                    lb_list: list[int] = database.resolve_aliases(raw_lb_list)
                    alias_resolved_from: list[int] = [
                        lb for lb in raw_lb_list if lb not in set(lb_list)
                    ]

                    # A sticky folder→LB link (set via "Pin & continue") resolves
                    # ambiguity permanently — it wins over the raw checksum match set.
                    link = database.get_folder_link(folder_path)
                    pinned_lb = link["lb_number"] if link else None

                    if pinned_lb is not None:
                        lb_number = pinned_lb
                    elif len(lb_list) == 1:
                        lb_number = lb_list[0]
                    else:
                        lb_number = None

                    # A single resolved LB# is only a true "pass" when every
                    # parsed checksum (across all types — ffp/md5/st5) found a
                    # home in the DB. A 50% match (e.g. ffp matches but md5
                    # doesn't) means the files on disk diverge from the
                    # archived copy and needs human review, even though the
                    # LB# itself is correctly identified.
                    full_match = summary.get("matched") == summary.get("given")

                    if lb_number is not None and full_match:
                        row["lookup"] = {
                            "status": "ok",
                            "label": f"LB-{lb_number:05d}",
                            "lb_number": lb_number,
                            "alias_resolved_from": alias_resolved_from or None,
                            "summary": summary,
                            "detail": detail,
                        }
                    elif lb_number is not None:
                        row["lookup"] = {
                            "status": "warn",
                            "label": "Incomplete match",
                            "lb_number": lb_number,
                            "alias_resolved_from": alias_resolved_from or None,
                            "summary": summary,
                            "detail": detail,
                        }
                        row["errors"].append({
                            "step": "lookup",
                            "message": (
                                f"{summary['matched']}/{summary['given']} checksums "
                                f"matched for LB-{lb_number:05d}"
                            ),
                        })
                    elif len(lb_list) > 1:
                        row["lookup"] = {"status": "warn", "label": "Conflict", "lb_number": None,
                                         "alias_resolved_from": None,
                                         "summary": summary, "detail": detail}
                        row["errors"].append({"step": "lookup", "message": f"Multiple LBs: {lb_list}"})
                    else:
                        row["lookup"] = {"status": "bad", "label": "Not found", "lb_number": None,
                                         "alias_resolved_from": None,
                                         "summary": summary, "detail": detail}

        # ── Step 3: LBDIR retrieve + verify ──────────────────────────────────
        if "lbdir" in steps:
            if lb_number:
                lbdir_file = _find_lbdir_in_folder(folder)
                if not lbdir_file:
                    # Try to pull from attachments cache; scrape if not yet cached.
                    try:
                        lbdir_src = find_lbdir_attachment(lb_number)
                        if not lbdir_src:
                            scraper.scrape_entry(lb_number, force=False, download_files=True)
                            lbdir_src = find_lbdir_attachment(lb_number)
                        if not lbdir_src:
                            # Might be an alias — try canonical
                            canonicals = database.resolve_aliases([lb_number])
                            canonical = canonicals[0] if canonicals and canonicals[0] != lb_number else None
                            if canonical:
                                lbdir_src = find_lbdir_attachment(canonical)
                                if not lbdir_src:
                                    scraper.scrape_entry(canonical, force=False, download_files=True)
                                    lbdir_src = find_lbdir_attachment(canonical)
                        if lbdir_src:
                            shutil.copy2(str(lbdir_src), str(folder / lbdir_src.name))
                            lbdir_file = folder / lbdir_src.name
                    except Exception:
                        pass

                if lbdir_file:
                    check = checksum_utils.verify_folder_lbdir(str(folder), lbdir_file)
                    chk_status = check.get("status", "fail")
                    n_total = check.get("total", 0)
                    n_pass  = check.get("pass", 0)
                    n_miss  = check.get("missing", 0)
                    n_mm    = check.get("mismatch", 0)
                    n_extra = check.get("extra", 0)
                    detail  = {"status": chk_status, "total": n_total,
                               "pass": n_pass, "missing": n_miss, "mismatch": n_mm,
                               "extra": n_extra}
                    if chk_status == "pass":
                        row["lbdir"] = {"status": "ok",   "label": "Pass",              "check": detail}
                        # If this folder is already an owned collection item (re-check
                        # of an in-place folder), stamp lbdir_verified_at so the Collect
                        # stage's "Confirmed" date reflects this pass. No-op otherwise.
                        database.set_lbdir_verified(str(folder))
                    elif chk_status == "missing_files":
                        row["lbdir"] = {"status": "warn", "label": f"Missing {n_miss}", "check": detail}
                    elif chk_status == "extra_files":
                        row["lbdir"] = {"status": "warn", "label": f"Extra {n_extra}",  "check": detail}
                    elif chk_status == "shntool_missing":
                        row["lbdir"] = {"status": "warn", "label": "No shntool",         "check": detail}
                    else:
                        label = f"Fail {n_mm}" if n_mm else "Fail"
                        row["lbdir"] = {"status": "bad",  "label": label,               "check": detail}
                else:
                    row["lbdir"] = {"status": "warn", "label": "No LBDIR", "check": None}
            # else: stays mute

        # ── Step 4: Rename proposal ───────────────────────────────────────────
        if "rename" in steps:
            if lb_number:
                entry_data = database.get_entry(lb_number)
                entry = (entry_data or {}).get("entry", {})
                date_str = entry.get("date_str") or ""
                location = (entry.get("location") or "").strip()
                lb_status = database.get_lb_status(lb_number)
                # BUG-176: when the LB entry's location is blank, fall back to
                # bobdylan.com's location for the same date so the canonical
                # "date Location (LB-NNNNN)" order can still be built.
                if date_str and not location:
                    from backend.torrent_maker import _parse_date
                    iso_date = _parse_date(date_str)
                    with database.get_connection() as conn:
                        show = conn.execute(
                            "SELECT location FROM bobdylan_shows WHERE date_str=?", (iso_date,)
                        ).fetchone()
                    if show and show["location"]:
                        location = show["location"].strip()
                proposed = _build_name(lb_number, date_str, location, lb_status)
                # BUG-119: when DB has no date/location the standard name falls
                # back to bare LB-NNNNN[-NFT], which would silently strip any
                # date/location already in the folder name.  Use the current
                # folder name as the base and only adjust the NFT suffix and
                # (LB-NNNNN) tag — never touch the date/location portion.
                if not date_str or not location:
                    base = strip_nft_suffix(folder_name)
                    correct_tag = f"(LB-{lb_number:05d})"
                    if base.rstrip().lower().endswith(correct_tag.lower()):
                        proposed = apply_nft_suffix(base, lb_status)
                    else:
                        # BUG-176: folder is missing (or has a stale) LB# tag —
                        # strip any existing tag and append the correct one.
                        untagged = re.sub(r"\s*\(LB-\d+\)\s*$", "", base, flags=re.IGNORECASE).rstrip()
                        proposed = apply_nft_suffix(f"{untagged} {correct_tag}", lb_status)
                if folder_name == proposed:
                    row["rename"] = {"status": "ok", "label": "Correct", "proposed": None}
                else:
                    row["rename"] = {"status": "warn", "label": "Proposed", "proposed": proposed}
            # else: stays mute — lookup hasn't resolved an LB#

        # ── Step 5: File (resolve only — no filesystem action here) ─────────
        if "file" in steps and lb_number:
            from backend.filer import (
                _path_reachable,
                get_mounts_with_stats,
                resolve_destination_for_lb,
            )
            resolution = resolve_destination_for_lb(lb_number, folder_path)
            if resolution["ok"]:
                mount_online = _path_reachable(resolution["mount_root"])
                if mount_online:
                    with database.get_connection() as conn:
                        collection_count = conn.execute(
                            "SELECT COUNT(*) FROM my_collection"
                        ).fetchone()[0]
                        lb_status_row = conn.execute(
                            "SELECT lb_status FROM lb_master WHERE lb_number=?", (lb_number,)
                        ).fetchone()
                        owned_row = conn.execute(
                            "SELECT lbdir_verified_at FROM my_collection WHERE lb_number=?",
                            (lb_number,),
                        ).fetchone()
                    row["file"] = {
                        "status": "ready",
                        "label": "Ready to file",
                        "dest_parent": resolution["dest_parent"],
                        "dest": resolution["dest"],
                        "mount_label": resolution["mount_label"],
                        "year": resolution["year"],
                        "error": None,
                        "error_code": None,
                        "mounts": get_mounts_with_stats(),
                        "recommended_mount": resolution["mount_id"],
                        "routed_year": resolution["year"],
                        "collection_count": collection_count,
                        "lb_status": lb_status_row["lb_status"] if lb_status_row else None,
                        "owned": owned_row is not None,
                        "lbdir_verified_at": owned_row["lbdir_verified_at"] if owned_row else None,
                    }
                else:
                    row["file"] = {
                        "status": "blocked",
                        "label": "Mount offline",
                        "dest_parent": "",
                        "dest": "",
                        "mount_label": resolution["mount_label"],
                        "year": resolution["year"],
                        "error": f"Mount '{resolution['mount_label']}' is offline",
                        "error_code": "mount_offline",
                    }
            else:
                row["file"] = {
                    "status": "blocked",
                    "label": _file_blocked_label(resolution["error_code"]),
                    "dest_parent": "",
                    "dest": "",
                    "mount_label": "",
                    "year": resolution["year"],
                    "error": resolution["error"],
                    "error_code": resolution["error_code"],
                }
        else:
            row["file"] = {"status": "mute", "label": "—", "error": None, "error_code": None}

        # ── Severity ──────────────────────────────────────────────────────────
        # file_status "blocked" escalates to attn (route/mount misconfigured);
        # "ready" does not change severity — the File button in the row handles it.
        statuses = [row["verify"]["status"], row["lookup"]["status"],
                    row["lbdir"]["status"], row["rename"]["status"]]
        file_status = row["file"]["status"]
        if "bad" in statuses or file_status == "blocked":
            row["severity"] = "attn"
        elif row["rename"].get("label") == "Proposed":
            row["severity"] = "ready"
        elif lb_number and (row["rename"]["status"] == "mute" or row["lbdir"]["status"] == "mute"):
            # Lookup resolved but downstream steps weren't run yet — not done
            row["severity"] = "attn"
        elif all(s in ("ok", "mute") for s in statuses) and "ok" in statuses:
            row["severity"] = "done"
        else:
            row["severity"] = "attn"

        return row

    @app.route("/api/pipeline/run", methods=["POST"])
    def pipeline_run() -> Response:
        """Run pipeline steps on a list of folders.

        Body: {folders: [path, ...], steps: ["verify","lookup","lbdir","rename","file"]}
        Returns:
            JSON {results: [PipelineRow, ...]}
        """
        try:
            data = request.get_json() or {}
            folders: list[str] = data.get("folders", [])
            steps: set[str] = set(data.get("steps", ["verify", "lookup", "lbdir", "rename", "file"]))
            if not folders:
                return jsonify({"error": "folders list required"}), 400
            results = [_pipeline_process_folder(f, steps) for f in folders]
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/folder/rename", methods=["POST"])
    def folder_rename() -> Response:
        """Rename a folder on disk to a new name within the same parent directory.

        Body: {folder: "/abs/path/to/folder", new_name: "new folder name"}
        Returns:
            JSON {ok: true, new_path: "/abs/path/to/new folder name"}
        """
        try:
            from backend.rename import write_rename_log
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            new_name: str = (data.get("new_name") or "").strip()
            if not folder.exists() or not folder.is_dir():
                return jsonify({"error": "Folder not found"}), 400
            if not new_name or "/" in new_name or "\\" in new_name:
                return jsonify({"error": "Invalid new_name"}), 400
            new_path = folder.parent / new_name
            if new_path.exists():
                return jsonify({"error": f"Target already exists: {new_name}"}), 409
            write_rename_log(
                folder_path=folder,
                old_name=folder.name,
                new_name=new_name,
                source="pipeline",
            )
            folder.rename(new_path)
            return jsonify({"ok": True, "new_path": str(new_path)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/pipeline/scan-tree", methods=["POST"])
    def pipeline_scan_tree() -> Response:
        """Walk a root directory and return subdirectories containing audio files.

        Body: {root: "/abs/path", shallow: false}
        shallow=true limits results to root + immediate subdirectories only (depth 1),
        but each immediate subdirectory is checked for audio at any depth below it
        (e.g. a release folder whose audio lives in CD1/CD2/Extras subfolders still
        counts as containing audio).
        Returns:
            JSON {folders: [str, ...]} sorted alphabetically
        """
        _AUDIO = {'.flac', '.shn', '.mp3', '.wav', '.m4a', '.aiff', '.ape', '.ogg', '.wv'}
        try:
            data = request.get_json() or {}
            root = Path(data.get("root", ""))
            shallow: bool = bool(data.get("shallow", False))
            if not root.is_dir():
                return jsonify({"error": "root is not a directory"}), 400
            found: list[str] = []

            def _has_audio(d: Path) -> bool:
                return any(f.suffix.lower() in _AUDIO for f in d.iterdir() if f.is_file())

            def _has_audio_anywhere(d: Path) -> bool:
                return any(f.suffix.lower() in _AUDIO for f in d.rglob("*") if f.is_file())

            if _has_audio(root):
                found.append(str(root))
            if shallow:
                for child in root.iterdir():
                    if child.is_dir() and _has_audio_anywhere(child):
                        found.append(str(child))
            else:
                for dirpath in root.rglob("*"):
                    if dirpath.is_dir() and _has_audio(dirpath):
                        found.append(str(dirpath))
            return jsonify({"folders": sorted(found)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    _LB_RE_SCAN = re.compile(r'LB[-\s]0*(\d+)', re.IGNORECASE)

    @app.route("/api/pipeline/scan-dir", methods=["POST"])
    def pipeline_scan_dir() -> Response:
        """Walk a directory and return LB-numbered subdirectories.

        Non-recursive (depth-1) by default; pass recursive=true for a full tree walk.
        Uses folder-name LB matching, not audio-file detection.

        Body: {root: "/abs/path", recursive: false}
        Returns:
            JSON {entries: [{lb_number, folder_name, path}], skipped: int}
        """
        try:
            data = request.get_json() or {}
            root = Path(data.get("root", ""))
            recursive = bool(data.get("recursive", False))
            if not root.is_dir():
                return jsonify({"error": "root is not a directory"}), 400

            skipped = 0

            if recursive:
                by_lb: dict[int, tuple[int, str, str]] = {}
                for child in root.rglob("*"):
                    if not child.is_dir():
                        continue
                    m = _LB_RE_SCAN.search(child.name)
                    if m:
                        lb = int(m.group(1))
                        depth = len(child.relative_to(root).parts)
                        if lb not in by_lb or depth < by_lb[lb][0]:
                            by_lb[lb] = (depth, child.name, str(child))
                    else:
                        skipped += 1
                entries = [
                    {"lb_number": lb, "folder_name": name, "path": path}
                    for lb, (_, name, path) in sorted(by_lb.items())
                ]
            else:
                entries = []
                for child in sorted(root.iterdir()):
                    if not child.is_dir():
                        continue
                    m = _LB_RE_SCAN.search(child.name)
                    if m:
                        entries.append({
                            "lb_number": int(m.group(1)),
                            "folder_name": child.name,
                            "path": str(child),
                        })
                    else:
                        skipped += 1

            return jsonify({"entries": entries, "skipped": skipped})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Data Package Export ───────────────────────────────────────────────────

    @app.route("/api/package/user_data", methods=["POST"])
    def package_user_data() -> Response:
        """Bundle user data (DB + settings + gui_state) into a dated zip in data/exports/.

        Returns: {ok, path, manifest: {type, created_at, files, file_count, total_bytes}}
        """
        import hashlib
        import zipfile
        from datetime import date, datetime

        try:
            exports_dir = DATA_DIR / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)

            date_str = date.today().isoformat()
            zip_path = exports_dir / f"losslessbob_userdata_{date_str}.zip"
            counter = 2
            while zip_path.exists():
                zip_path = exports_dir / f"losslessbob_userdata_{date_str}_{counter}.zip"
                counter += 1

            candidates = [
                (DATA_DIR / "losslessbob.db", "losslessbob.db"),
                (DATA_DIR / "settings.ini", "settings.ini"),
                (DATA_DIR / "gui_state.json", "gui_state.json"),
            ]

            manifest_files = []
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for src, arc_name in candidates:
                    if src.exists():
                        zf.write(src, arc_name)
                        size = src.stat().st_size
                        sha256 = hashlib.sha256(src.read_bytes()).hexdigest()
                        manifest_files.append({"name": arc_name, "size_bytes": size, "sha256": sha256})

            manifest = {
                "type": "user_data",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "files": manifest_files,
                "file_count": len(manifest_files),
                "total_bytes": sum(f["size_bytes"] for f in manifest_files),
            }
            _log.info("package_user_data: wrote %s (%d files)", zip_path.name, len(manifest_files))
            return jsonify({"ok": True, "path": str(zip_path), "manifest": manifest})
        except Exception:
            _log.exception("package_user_data failed")
            return jsonify({"error": "internal_error"}), 500

    @app.route("/api/package/scrape_data", methods=["POST"])
    def package_scrape_data() -> Response:
        """Bundle scraped site data (data/site/) into a dated zip in data/exports/.

        Returns: {ok, path, manifest: {type, created_at, file_count, total_bytes}}
        """
        import zipfile
        from datetime import date, datetime

        try:
            if not SITE_DIR.exists():
                return jsonify({
                    "error": "no_site_data",
                    "message": "data/site/ does not exist. Run the site crawler first.",
                }), 400

            exports_dir = DATA_DIR / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)

            date_str = date.today().isoformat()
            zip_path = exports_dir / f"losslessbob_sitedata_{date_str}.zip"
            counter = 2
            while zip_path.exists():
                zip_path = exports_dir / f"losslessbob_sitedata_{date_str}_{counter}.zip"
                counter += 1

            file_count = 0
            total_bytes = 0
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for src in sorted(SITE_DIR.rglob("*")):
                    if src.is_file():
                        arc_name = "site/" + src.relative_to(SITE_DIR).as_posix()
                        zf.write(src, arc_name)
                        file_count += 1
                        total_bytes += src.stat().st_size

            manifest = {
                "type": "scrape_data",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "file_count": file_count,
                "total_bytes": total_bytes,
            }
            _log.info("package_scrape_data: wrote %s (%d files)", zip_path.name, file_count)
            return jsonify({"ok": True, "path": str(zip_path), "manifest": manifest})
        except Exception:
            _log.exception("package_scrape_data failed")
            return jsonify({"error": "internal_error"}), 500

    @app.route("/api/package/restore", methods=["POST"])
    def package_restore() -> Response:
        """Restore a zip archive produced by /api/package/user_data or /api/package/scrape_data.

        Body: {zip_path: str, dry_run: bool = false}
        Returns: {ok, type, restored: [{name, dest}], conflicts: [{name, dest}], dry_run: bool}
        """
        import zipfile

        body = request.get_json(silent=True) or {}
        zip_path_str = body.get("zip_path", "")
        dry_run = bool(body.get("dry_run", False))

        if not zip_path_str:
            return jsonify({"error": "zip_path is required"}), 400

        zip_path = Path(zip_path_str)
        if not zip_path.is_file():
            return jsonify({"error": "file_not_found", "message": f"No file at {zip_path_str}"}), 404

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                # Detect package type from manifest embedded inside zip, or from file names.
                pkg_type: str | None = None
                manifest_data: dict = {}
                if "manifest.json" in names:
                    import json as _json
                    manifest_data = _json.loads(zf.read("manifest.json"))
                    pkg_type = manifest_data.get("type")

                if pkg_type is None:
                    if any(n.startswith("site/") for n in names):
                        pkg_type = "scrape_data"
                    elif any(n in ("losslessbob.db", "settings.ini", "gui_state.json") for n in names):
                        pkg_type = "user_data"
                    else:
                        return jsonify({"error": "unrecognised_package",
                                        "message": "Cannot determine package type from zip contents."}), 400

                restored = []
                conflicts = []

                if pkg_type == "user_data":
                    user_files = [
                        ("losslessbob.db", DATA_DIR / "losslessbob.db"),
                        ("settings.ini",   DATA_DIR / "settings.ini"),
                        ("gui_state.json", DATA_DIR / "gui_state.json"),
                    ]
                    for arc_name, dest in user_files:
                        if arc_name not in names:
                            continue
                        entry = {"name": arc_name, "dest": str(dest)}
                        if dest.exists():
                            conflicts.append(entry)
                        else:
                            restored.append(entry)
                        if not dry_run:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(zf.read(arc_name))
                    if not dry_run:
                        _log.info("package_restore(user_data): restored %d files from %s",
                                  len(restored) + len(conflicts), zip_path.name)

                elif pkg_type == "scrape_data":
                    site_dest = DATA_DIR / "site"
                    for arc_name in names:
                        if not arc_name.startswith("site/") or arc_name.endswith("/"):
                            continue
                        rel = arc_name[len("site/"):]
                        dest = site_dest / rel
                        entry = {"name": arc_name, "dest": str(dest)}
                        if dest.exists():
                            conflicts.append(entry)
                        else:
                            restored.append(entry)
                        if not dry_run:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(zf.read(arc_name))
                    if not dry_run:
                        _log.info("package_restore(scrape_data): restored %d files from %s",
                                  len(restored) + len(conflicts), zip_path.name)

                return jsonify({
                    "ok": True,
                    "type": pkg_type,
                    "restored": restored,
                    "conflicts": conflicts,
                    "dry_run": dry_run,
                })
        except zipfile.BadZipFile:
            return jsonify({"error": "bad_zip", "message": "File is not a valid zip archive."}), 400
        except Exception:
            _log.exception("package_restore failed")
            return jsonify({"error": "internal_error"}), 500

    # ------------------------------------------------------------------
    # bobdylan.com setlist routes
    # ------------------------------------------------------------------

    @app.route("/api/bobdylan/update", methods=["POST"])
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
            if bobdylan_scraper.is_running():
                return jsonify({"ok": False, "error": "Already running"}), 409
            threading.Thread(
                target=bobdylan_scraper.run_update,
                kwargs={"force": force},
                daemon=True,
            ).start()
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bobdylan/discover", methods=["POST"])
    def bobdylan_discover():
        """Start background sitemap URL discovery (no page scraping).

        Returns:
            JSON: {ok: true, running: true}
        """
        try:
            if bobdylan_scraper.is_running():
                return jsonify({"ok": False, "error": "Already running"}), 409
            threading.Thread(
                target=bobdylan_scraper.run_discover,
                daemon=True,
            ).start()
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bobdylan/scrape", methods=["POST"])
    def bobdylan_scrape():
        """Start background scrape of unscraped show pages.

        Body: {force: bool}  — if true, re-scrapes all shows.

        Returns:
            JSON: {ok: true, running: true}
        """
        try:
            data = request.get_json() or {}
            force = bool(data.get("force", False))
            if bobdylan_scraper.is_running():
                return jsonify({"ok": False, "error": "Already running"}), 409
            threading.Thread(
                target=bobdylan_scraper.run_scrape,
                kwargs={"force": force},
                daemon=True,
            ).start()
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bobdylan/stop", methods=["POST"])
    def bobdylan_stop():
        """Signal the active bobdylan scrape worker to stop."""
        bobdylan_scraper.stop()
        return jsonify({"ok": True})

    @app.route("/api/bobdylan/status", methods=["GET"])
    def bobdylan_status():
        """Return the current bobdylan scraper progress state."""
        return jsonify(bobdylan_scraper.get_status())

    @app.route("/api/bobdylan/show", methods=["GET"])
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

    @app.route("/api/bobdylan/stats", methods=["GET"])
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

    @app.route("/api/setlistfm/key", methods=["POST"])
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

    @app.route("/api/setlistfm/key", methods=["GET"])
    def setlistfm_get_key():
        """Return whether an API key is configured (never returns the key itself).

        Returns:
            JSON: {configured: bool}
        """
        return jsonify({"configured": bool(setlistfm_mod.get_api_key())})

    @app.route("/api/setlistfm/update", methods=["POST"])
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
            if setlistfm_mod.is_running():
                return jsonify({"ok": False, "error": "Already running"}), 409
            threading.Thread(
                target=setlistfm_mod.run_update,
                kwargs={"force": force, "api_key": api_key},
                daemon=True,
            ).start()
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/setlistfm/stop", methods=["POST"])
    def setlistfm_stop():
        """Signal the active setlistfm worker to stop."""
        setlistfm_mod.stop()
        return jsonify({"ok": True})

    @app.route("/api/setlistfm/status", methods=["GET"])
    def setlistfm_status():
        """Return the current setlistfm worker progress state."""
        return jsonify(setlistfm_mod.get_status())

    @app.route("/api/setlistfm/show", methods=["GET"])
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

    @app.route("/api/setlistfm/stats", methods=["GET"])
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

    # ── Collection Trading ────────────────────────────────────────────────────

    @app.route("/api/trading/export", methods=["GET"])
    def trading_export():
        """Export the user's collection as a .lbcollection JSON blob.

        Returns:
            JSON: {losslessbob_collection, export_version, exported_at, entries}
        """
        try:
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT lb_number, date_str, location, lb_status FROM my_collection ORDER BY lb_number"
            ).fetchall()
            import datetime as _dt
            return jsonify({
                "losslessbob_collection": True,
                "export_version": 1,
                "exported_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "entries": [
                    {"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]}
                    for r in rows
                ],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trading/friends", methods=["GET"])
    def trading_friends_list():
        """List all stored friend collections.

        Returns:
            JSON: [{id, friend_name, imported_at, updated_at, lb_count}]
        """
        try:
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT id, friend_name, imported_at, updated_at, lb_count FROM friend_collections ORDER BY friend_name"
            ).fetchall()
            return jsonify([
                {"id": r[0], "friend_name": r[1], "imported_at": r[2], "updated_at": r[3], "lb_count": r[4]}
                for r in rows
            ])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trading/friends", methods=["POST"])
    def trading_friends_upsert():
        """Import or update a friend's collection.

        Request JSON: {friend_name: str, entries: [{lb_number, date_str?, location?, lb_status?}]}

        Returns:
            JSON: {ok, friend_id}
        """
        try:
            data = request.get_json(force=True)
            friend_name = str(data.get("friend_name", "")).strip()
            entries = data.get("entries", [])
            if not friend_name:
                return jsonify({"error": "friend_name required"}), 400

            import datetime as _dt
            conn = database.get_connection()
            now = _dt.datetime.now(_dt.UTC).isoformat()
            existing = conn.execute(
                "SELECT id FROM friend_collections WHERE friend_name = ?", (friend_name,)
            ).fetchone()

            if existing:
                friend_id = existing[0]
                conn.execute(
                    "UPDATE friend_collections SET updated_at = ?, lb_count = ? WHERE id = ?",
                    (now, len(entries), friend_id),
                )
                conn.execute("DELETE FROM friend_collection_entries WHERE friend_id = ?", (friend_id,))
            else:
                cur = conn.execute(
                    "INSERT INTO friend_collections (friend_name, lb_count) VALUES (?, ?)",
                    (friend_name, len(entries)),
                )
                friend_id = cur.lastrowid

            conn.executemany(
                "INSERT OR IGNORE INTO friend_collection_entries (friend_id, lb_number, date_str, location, lb_status) VALUES (?, ?, ?, ?, ?)",
                [
                    (friend_id, e.get("lb_number"), e.get("date_str"), e.get("location"), e.get("lb_status"))
                    for e in entries if e.get("lb_number")
                ],
            )
            conn.commit()
            return jsonify({"ok": True, "friend_id": friend_id})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trading/friends/<int:friend_id>", methods=["DELETE"])
    def trading_friends_delete(friend_id):
        """Remove a stored friend collection.

        Args:
            friend_id: Row ID in friend_collections.

        Returns:
            JSON: {ok}
        """
        try:
            conn = database.get_connection()
            conn.execute("DELETE FROM friend_collections WHERE id = ?", (friend_id,))
            conn.commit()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trading/compare/<int:friend_id>", methods=["GET"])
    def trading_compare(friend_id):
        """Diff the user's collection against a friend's.

        Args:
            friend_id: Row ID in friend_collections.

        Returns:
            JSON: {friend_name, you_have_they_dont, they_have_you_dont, both_have_count}
        """
        try:
            conn = database.get_connection()
            row = conn.execute(
                "SELECT friend_name FROM friend_collections WHERE id = ?", (friend_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "friend not found"}), 404
            friend_name = row[0]

            mine = {r[0] for r in conn.execute("SELECT lb_number FROM my_collection").fetchall()}
            theirs = {r[0] for r in conn.execute(
                "SELECT lb_number FROM friend_collection_entries WHERE friend_id = ?", (friend_id,)
            ).fetchall()}

            def _enrich(lb_numbers):
                if not lb_numbers:
                    return []
                result = []
                for lb in sorted(lb_numbers):
                    r = conn.execute(
                        "SELECT mc.lb_number, mc.date_str, mc.location, mc.lb_status "
                        "FROM my_collection mc WHERE mc.lb_number = ? "
                        "UNION SELECT fce.lb_number, fce.date_str, fce.location, fce.lb_status "
                        "FROM friend_collection_entries fce WHERE fce.friend_id = ? AND fce.lb_number = ?",
                        (lb, friend_id, lb),
                    ).fetchone()
                    if r:
                        result.append({"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]})
                    else:
                        result.append({"lb_number": lb, "date_str": None, "location": None, "lb_status": None})
                return result

            you_have = mine - theirs
            they_have = theirs - mine
            both = mine & theirs

            return jsonify({
                "friend_name": friend_name,
                "you_have_they_dont": _enrich(you_have),
                "they_have_you_dont": _enrich(they_have),
                "both_have_count": len(both),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── File Sharing ──────────────────────────────────────────────────────────

    sharing.load_persisted_shares()

    @app.route("/api/share/create", methods=["POST"])
    def share_create():
        """Create a new file share for a collection entry folder.

        Request JSON: {lb_number: int, ttl_hours?: int, use_tunnel?: bool}

        Returns:
            JSON: {token, share_url, tunnel_url?, files, expires_at}
        """
        try:
            data = request.get_json(force=True)
            lb_number = int(data.get("lb_number", 0))
            ttl_hours = int(data.get("ttl_hours", sharing.DEFAULT_TTL_HOURS))
            use_tunnel = bool(data.get("use_tunnel", False))

            conn = database.get_connection()
            row = conn.execute(
                "SELECT disk_path FROM my_collection WHERE lb_number = ?", (lb_number,)
            ).fetchone()
            if not row or not row[0]:
                return jsonify({"error": "lb_number not found in collection or no disk_path"}), 404

            folder_path = row[0]
            if not Path(folder_path).is_dir():
                return jsonify({"error": f"folder not found: {folder_path}"}), 404

            tunnel_url = None
            if use_tunnel and not sharing.is_tunnel_alive():
                tunnel_url = sharing.start_cloudflare_tunnel()
            elif sharing.is_tunnel_alive():
                tunnel_url = sharing._tunnel_url

            result = sharing.create_share(folder_path, ttl_hours=ttl_hours, lb_number=lb_number)
            token = result["token"]

            base = tunnel_url or request.host_url.rstrip("/")
            share_url = f"{base}/api/share/{token}/"

            return jsonify({
                "token": token,
                "share_url": share_url,
                "tunnel_url": tunnel_url,
                "files": result["files"],
                "expires_at": result["expires_at"],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/share/<token>/", methods=["GET"])
    def share_listing(token):
        """Serve the self-contained HTML file listing for a share.

        Args:
            token: Share token.
        """
        share = sharing.get_share(token)
        if share is None:
            abort(404)
        base_url = request.url.rstrip("/")
        html = sharing.render_listing(token, share, base_url)
        return Response(html, mimetype="text/html")

    @app.route("/api/share/<token>/file/<path:filename>", methods=["GET"])
    def share_file(token, filename):
        """Serve a single audio file from a share (supports Range / 206).

        Args:
            token: Share token.
            filename: Bare filename within the share folder.
        """
        share = sharing.get_share(token)
        if share is None:
            abort(404)
        if filename not in share["files"]:
            abort(404)
        full_path = Path(share["folder_path"]) / filename
        return send_file(full_path, conditional=True, as_attachment=True)

    @app.route("/api/share/<token>/zip", methods=["GET"])
    def share_zip(token):
        """Stream the entire share as a ZIP archive (chunked transfer).

        Args:
            token: Share token.
        """
        share = sharing.get_share(token)
        if share is None:
            abort(404)
        lb = share.get("lb_number") or "share"
        disposition = f'attachment; filename="LB-{lb:05d}.zip"' if isinstance(lb, int) else f'attachment; filename="{lb}.zip"'
        return Response(
            stream_with_context(sharing.stream_zip(share["folder_path"], share["files"])),
            mimetype="application/zip",
            headers={"Content-Disposition": disposition},
        )

    @app.route("/api/share/list", methods=["GET"])
    def share_list():
        """Return JSON list of all active shares for GUI status display.

        Returns:
            JSON: [{token, folder_path, files, expires_at, lb_number, tunnel_url}]
        """
        return jsonify(sharing.list_shares())

    @app.route("/api/share/<token>", methods=["DELETE"])
    def share_revoke(token):
        """Revoke a share and stop tunnel if no shares remain.

        Args:
            token: Share token.

        Returns:
            JSON: {ok}
        """
        sharing.revoke_share(token)
        return jsonify({"ok": True})

    @app.route("/api/share/tunnel/status", methods=["GET"])
    def share_tunnel_status():
        """Return Cloudflare Tunnel availability and current state.

        Returns:
            JSON: {cloudflared_available, tunnel_alive, tunnel_url, named_tunnel}
        """
        return jsonify({
            "cloudflared_available": sharing.cloudflared_available(),
            "tunnel_alive": sharing.is_tunnel_alive(),
            "tunnel_url": sharing._tunnel_url,
            "named_tunnel": sharing.named_tunnel_running(),
        })

    # ── Archive.org Upload ────────────────────────────────────────────────────

    @app.route("/api/archive_org/credentials", methods=["POST"])
    def archive_org_save_credentials():
        """Save archive.org S3 credentials to keyring.

        Body: {access_key, secret_key}
        Returns: {ok, label}
        """
        from backend.credentials import SERVICE_IA, save_credentials
        data = request.get_json(force=True) or {}
        access_key = data.get("access_key", "").strip()
        secret_key = data.get("secret_key", "").strip()
        if not access_key or not secret_key:
            return jsonify({"ok": False, "error": "access_key and secret_key required"}), 400
        result = save_credentials(SERVICE_IA, access_key, secret_key)
        return jsonify({"ok": result.ok, "label": result.label})

    @app.route("/api/archive_org/credentials", methods=["GET"])
    def archive_org_check_credentials():
        """Return whether archive.org credentials are stored.

        Returns: {stored: bool}
        """
        from backend.credentials import SERVICE_IA, credentials_stored
        return jsonify({"stored": credentials_stored(SERVICE_IA)})

    @app.route("/api/archive_org/credentials", methods=["DELETE"])
    def archive_org_delete_credentials():
        """Clear stored archive.org credentials.

        Returns: {ok: bool}
        """
        from backend.credentials import SERVICE_IA, delete_credentials
        delete_credentials(SERVICE_IA)
        return jsonify({"ok": True})

    @app.route("/api/archive_org/test", methods=["POST"])
    def archive_org_test():
        """Test archive.org S3 credentials.

        Body: {access_key?, secret_key?} — if omitted, uses stored credentials.
        Returns: {ok, error?}
        """
        from backend.credentials import SERVICE_IA, get_credentials
        data = request.get_json(force=True) or {}
        access_key = data.get("access_key", "").strip()
        secret_key = data.get("secret_key", "").strip()
        if not access_key or not secret_key:
            access_key, secret_key = get_credentials(SERVICE_IA)
        if not access_key or not secret_key:
            return jsonify({"ok": False, "error": "No credentials provided or stored"}), 400
        return jsonify(_archive_org.test_credentials(access_key, secret_key))

    @app.route("/api/archive_org/upload", methods=["POST"])
    def archive_org_upload():
        """Start an async archive.org upload for one LB entry.

        Body: {lb_number, folder_path, identifier?, collection?, title?, subject?,
               access_key?, secret_key?}
        Returns: {ok, error?}
        """
        from backend.credentials import SERVICE_IA, get_credentials
        data = request.get_json(force=True) or {}
        lb_number = data.get("lb_number")
        folder_path = data.get("folder_path", "").strip()
        if not lb_number or not folder_path:
            return jsonify({"ok": False, "error": "lb_number and folder_path required"}), 400

        access_key = data.get("access_key", "").strip()
        secret_key = data.get("secret_key", "").strip()
        if not access_key or not secret_key:
            access_key, secret_key = get_credentials(SERVICE_IA)
        if not access_key or not secret_key:
            return jsonify({"ok": False, "error": "No credentials provided or stored"}), 400

        result = _archive_org.upload_lb(
            lb_number=int(lb_number),
            folder_path=folder_path,
            access_key=access_key,
            secret_key=secret_key,
            identifier=data.get("identifier") or None,
            collection=data.get("collection") or _archive_org.IA_DEFAULT_COLLECTION,
            title=data.get("title") or None,
            subject=data.get("subject") or "Bob Dylan;lossless;bootleg;losslessbob",
            database=database,
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @app.route("/api/archive_org/status", methods=["GET"])
    def archive_org_status():
        """Return current archive.org upload progress.

        Returns: {running, lb_number, identifier, current_file, files_done,
                  files_total, bytes_done, bytes_total, status, error, stop_requested}
        """
        return jsonify(_archive_org.get_status())

    @app.route("/api/archive_org/stop", methods=["POST"])
    def archive_org_stop():
        """Request the running archive.org upload to stop after the current file.

        Returns: {ok}
        """
        _archive_org.stop_upload()
        return jsonify({"ok": True})

    @app.route("/api/archive_org/uploads", methods=["GET"])
    def archive_org_uploads():
        """Return archive upload history rows, newest first.

        Query params: lb=<int> to filter by LB number.
        Returns: [{id, lb_number, identifier, folder_path, files_total,
                   files_uploaded, status, started_at, finished_at, error,
                   date_str?, location?}]
        """
        lb = request.args.get("lb", type=int)
        return jsonify(database.get_archive_uploads(lb_number=lb))

    _slog.t("Flask: create_app done")
    return app


def _do_spectro_batch(folders: list[str], opts: dict) -> None:
    """Run spectrogram generation for all audio files in the given folders.

    Intended to be executed in a daemon thread. Updates _spectro_state in-place
    with progress, skipped, error counts, and final status.

    Args:
        folders: List of absolute folder paths to process.
        opts: Generation options — width, height, dyn_range (int), force (bool).
    """
    def _set(**kw):
        with _spectro_lock:
            _spectro_state.update(kw)

    try:
        from backend.sox_utils import (
            AUDIO_EXTS_ALL,
            ConversionError,
            SoxNotFoundError,
            SpectrogenError,
            generate_spectrogram,
        )
    except Exception as exc:
        _set(status="error", current=str(exc))
        return

    all_files: list[tuple[Path, Path]] = []
    for folder in folders:
        p = Path(folder)
        if not p.is_dir():
            continue
        spectro_dir = p / "spectrograms"
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS_ALL:
                png = spectro_dir / (f.stem + ".png")
                all_files.append((f, png))

    _set(status="running", done=0, total=len(all_files),
         errors=[], skipped=0, stop_requested=False, current="")

    if not all_files:
        _set(status="done", current="", done=0)
        return

    done = 0
    skipped = 0
    errors = []

    for audio_path, output_png in all_files:
        with _spectro_lock:
            if _spectro_state["stop_requested"]:
                break

        _set(current=audio_path.name)

        if output_png.exists() and not opts.get("force"):
            skipped += 1
            done += 1
            _set(done=done, skipped=skipped)
            continue

        try:
            generate_spectrogram(
                audio_path, output_png,
                width=opts["width"],
                height=opts["height"],
                dyn_range=opts["dyn_range"],
                title=audio_path.name,
            )
        except SoxNotFoundError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
            _set(status="error", errors=list(errors), done=done,
                 current="SoX not found — generation stopped.")
            return
        except ConversionError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
        except SpectrogenError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
        except Exception as e:
            errors.append({"file": audio_path.name,
                           "error": f"Unexpected: {e}"})

        done += 1
        _set(done=done, errors=list(errors), skipped=skipped)

    _set(status="done", current="", done=done,
         errors=list(errors), skipped=skipped)


def _do_fp_build(collection_rows: list[dict], force: bool = False) -> None:
    """Run fingerprint.build_fingerprint_db in a daemon thread."""
    def _set(kw: dict) -> None:
        with _fp_build_lock:
            _fp_build_state.update(kw)

    try:
        from backend import fingerprint as _fp
        _fp.build_fingerprint_db(
            collection_rows,
            force=force,
            state_setter=_set,
            stop_event=_fp_build_stop,
        )
    except Exception as exc:
        _set({"status": "error", "current": str(exc)})


def _do_fp_dup_scan() -> None:
    """Run fingerprint.find_duplicate_recordings in a daemon thread."""
    def _set(kw: dict) -> None:
        with _fp_dup_lock:
            _fp_dup_state.update(kw)

    try:
        from backend import fingerprint as _fp
        results = _fp.find_duplicate_recordings(
            state_setter=_set,
            stop_event=_fp_dup_stop,
        )
        _set({"status": "done", "results": results})
    except Exception as exc:
        _set({"status": "error", "message": str(exc)})


def _do_fp_identify_folder(folder: str) -> None:
    """Identify all audio files in folder against fingerprints.db."""
    def _set(**kw: object) -> None:
        with _fp_id_lock:
            _fp_id_state.update(kw)

    try:
        from backend import fingerprint as _fp
        folder_path = Path(folder)
        audio_files = [
            f for f in sorted(folder_path.rglob("*"))
            if f.is_file() and f.suffix.lower() in _fp.AUDIO_EXTS
        ]
        _set(status="running", done=0, total=len(audio_files),
             results=[], errors=[], current="", stop_requested=False)

        if not audio_files:
            _set(status="done", current="")
            return

        results: list[dict] = []
        errors: list[str] = []
        for i, audio_path in enumerate(audio_files):
            if _fp_id_stop.is_set():
                break
            _set(current=audio_path.name, done=i)
            try:
                candidates = _fp.identify_file(audio_path)
                results.append({
                    "user_file": audio_path.name,
                    "user_path": str(audio_path),
                    "candidates": candidates,
                })
            except Exception as exc:
                errors.append(f"{audio_path.name}: {exc}")
            _set(done=i + 1, results=list(results), errors=list(errors))

        _set(status="done", current="")
    except Exception as exc:
        _set(status="error", current=str(exc))


# Files/names _do_data_download never overwrites
_DATA_PROTECTED = frozenset({
    "losslessbob.db", "settings.ini", "scraper.log", "temp_import.db",
})
_DATA_PROTECTED_EXTS = frozenset({".db", ".ini"})


def _do_data_download(url: str) -> None:
    """Download a ZIP from url and extract safe files into DATA_DIR."""
    import shutil
    import tempfile
    import zipfile
    from pathlib import Path as _Path

    import requests as _req

    from backend.paths import DATA_DIR as _DATA_DIR
    from backend.paths import to_long_path

    def _set(status, progress, message, **kw):
        with _data_dl_lock:
            _data_dl_state.update({"status": status, "progress": progress,
                                    "message": message, **kw})

    try:
        _set("downloading", 2, "Connecting…",
             downloaded_bytes=0, total_bytes=0, files_extracted=[], files_skipped=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = _Path(tmpdir) / "data_update.zip"
            resp = _req.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 45) + 2 if total else 30
                        _set("downloading", pct,
                             f"Downloading… {downloaded // 1024:,} KB"
                             + (f" / {total // 1024:,} KB" if total else ""),
                             downloaded_bytes=downloaded, total_bytes=total)

            if not zipfile.is_zipfile(zip_path):
                _set("error", 0, "Downloaded file is not a valid ZIP archive.")
                return

            _set("extracting", 50, "Extracting…")
            extracted, skipped = [], []

            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                roots = {m.split("/")[0] for m in members if "/" in m}
                strip_prefix = (list(roots)[0] + "/") if len(roots) == 1 else ""

                for i, member in enumerate(members):
                    rel = member[len(strip_prefix):] if strip_prefix else member
                    if not rel or rel.endswith("/"):
                        continue
                    rel_path = _Path(rel)
                    name = rel_path.name
                    if name in _DATA_PROTECTED or rel_path.suffix.lower() in _DATA_PROTECTED_EXTS:
                        skipped.append(rel)
                        continue
                    dest = to_long_path(_DATA_DIR / rel_path)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(rel)
                    pct = int(i / max(len(members), 1) * 45) + 50
                    _set("extracting", min(pct, 95),
                         f"Extracting… ({i + 1}/{len(members)} files)",
                         files_extracted=extracted, files_skipped=skipped)

        _set("done", 100,
             f"Done. {len(extracted)} file(s) extracted, {len(skipped)} skipped (protected).",
             files_extracted=extracted, files_skipped=skipped)
    except Exception as e:
        _set("error", 0, f"Download failed: {e}")


# Source dirs/exts _do_update never overwrites
_UPDATE_SKIP_DIRS = frozenset({"data", ".git", "__pycache__", ".venv", "venv", "dist", "build"})
_UPDATE_SKIP_EXTS = frozenset({".db", ".ini", ".log", ".sdf"})


def _do_update(zipball_url: str) -> None:
    """Download a GitHub zipball and apply source files to APP_ROOT."""
    import shutil
    import tempfile
    import zipfile
    from pathlib import Path as _Path

    import requests as _req

    from backend.paths import APP_ROOT as _ROOT

    def _set(status, progress, message):
        with _update_lock:
            _update_state.update({"status": status, "progress": progress, "message": message})

    try:
        _set("downloading", 5, "Connecting to GitHub…")
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = _Path(tmpdir) / "update.zip"
            resp = _req.get(zipball_url, stream=True, timeout=60,
                            headers={"Accept": "application/octet-stream"})
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 40) + 5 if total else 30
                        _set("downloading", pct, f"Downloading… {downloaded // 1024:,} KB")

            _set("applying", 50, "Extracting…")
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                prefix = (members[0].split("/")[0] + "/") if members else ""
                for i, member in enumerate(members):
                    rel = member[len(prefix):]
                    if not rel or member.endswith("/"):
                        continue
                    parts = _Path(rel).parts
                    if parts and parts[0] in _UPDATE_SKIP_DIRS:
                        continue
                    if _Path(rel).suffix.lower() in _UPDATE_SKIP_EXTS:
                        continue
                    dest = _ROOT / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    pct = int(i / max(len(members), 1) * 45) + 50
                    _set("applying", min(pct, 95), f"Applying… ({i + 1} files)")

        _set("done", 100, "Update applied. Click Restart to reload the application.")
    except Exception as e:
        _set("error", 0, f"Update failed: {e}")


def _start_scrape_thread(
    lb_numbers: list[int],
    force: bool = False,
    delay_ms: int = 1500,
    download: bool = True,
    use_local_pages: bool = False,
) -> None:
    """Start a background thread to scrape the given LB numbers, if none is running.

    No-op if a scrape thread is already alive. The thread calls
    scraper.scrape_range() with the supplied options.

    Args:
        lb_numbers: Ordered list of LB numbers to scrape.
        force: Re-scrape even if an entry already has data.
        delay_ms: Milliseconds to sleep between requests.
        download: Download attachment files when True.
        use_local_pages: Read from data/site/detail/ cache instead of the network.
    """
    global _scrape_thread
    if _scrape_thread and _scrape_thread.is_alive():
        return

    def run():
        scraper.scrape_range(
            lb_numbers,
            force=force,
            download_files=download,
            use_local_pages=use_local_pages,
            delay_ms=delay_ms,
        )

    _scrape_thread = threading.Thread(target=run, daemon=True)
    _scrape_thread.start()


def _start_download_pages_thread(lb_numbers, force=False, delay_ms=1500):
    global _scrape_thread
    if _scrape_thread and _scrape_thread.is_alive():
        return

    def run():
        scraper.download_pages_range(lb_numbers, force=force, delay_ms=delay_ms)

    _scrape_thread = threading.Thread(target=run, daemon=True)
    _scrape_thread.start()


# ── Collection HTML export template ─────────────────────────────────────────
# Placeholders replaced at request time:
#   __DATA_JSON__     → JSON array of entry dicts
#   __GENERATED_AT__  → UTC timestamp string (no single-quotes, safe in JS string literal)
_COLLECTION_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LosslessBob — My Collection</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#eceff7;--surface:#fff;--s2:#f6f7fb;--bd:#dde3ef;
  --tx:#18202e;--tx2:#6a7390;
  --ac:#4878f5;--acd:#2e5cdf;--acg:rgba(72,120,245,.12);
  --pub-bg:#d1fae5;--pub:#065f46;
  --priv-bg:#dbeafe;--priv:#1e40af;
  --miss-bg:#fee2e2;--miss:#991b1b;
  --unk-bg:#f1f5f9;--unk:#475569;
  --sh1:0 1px 3px rgba(0,0,0,.07),0 2px 8px rgba(0,0,0,.05);
  --sh2:0 4px 12px rgba(0,0,0,.08),0 12px 32px rgba(0,0,0,.06);
  --r:12px
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0b0d16;--surface:#12151f;--s2:#181c28;--bd:#20253a;
  --tx:#d6ddf0;--tx2:#7a86a4;
  --ac:#6490ff;--acd:#4d78f0;--acg:rgba(100,144,255,.14);
  --pub-bg:#052e16;--pub:#4ade80;
  --priv-bg:#172554;--priv:#93c5fd;
  --miss-bg:#450a0a;--miss:#f87171;
  --unk-bg:#1a1f32;--unk:#94a3b8;
  --sh1:0 1px 3px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.2);
  --sh2:0 4px 12px rgba(0,0,0,.4),0 12px 32px rgba(0,0,0,.3)
}}
html,body{height:100%;overflow:hidden}
body{font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:var(--bg);color:var(--tx);font-size:14px;line-height:1.5;
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column}

/* header */
.hdr{flex-shrink:0;background:var(--surface);
  border-bottom:1px solid var(--bd);box-shadow:var(--sh1);padding:14px 20px 10px}
.hdr-top{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.logo{font-size:18px;font-weight:700;letter-spacing:-.4px}
.logo em{font-style:normal;color:var(--ac)}
.gen{font-size:12px;color:var(--tx2);margin-left:auto}

/* stats pills */
.stats{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:99px;font-size:12px;font-weight:500;
  background:var(--s2);border:1px solid var(--bd)}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}

/* controls */
.ctrl{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.sw{position:relative;flex:1;min-width:160px;max-width:320px}
.si{position:absolute;left:9px;top:50%;transform:translateY(-50%);
  color:var(--tx2);pointer-events:none;display:flex}
input[type=search],select,button{font:13px/1.4 inherit}
input[type=search]{width:100%;padding:6px 10px 6px 30px;border:1px solid var(--bd);
  border-radius:8px;background:var(--s2);color:var(--tx);outline:none;
  transition:border-color .15s,box-shadow .15s}
input[type=search]::-webkit-search-cancel-button{-webkit-appearance:none}
input[type=search]:focus{border-color:var(--ac);box-shadow:0 0 0 3px var(--acg)}
select{padding:6px 26px 6px 10px;border:1px solid var(--bd);border-radius:8px;
  background-color:var(--s2);color:var(--tx);outline:none;
  -webkit-appearance:none;appearance:none;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='11' height='11' viewBox='0 0 24 24'%3E%3Cpath fill='%236a7390' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
  transition:border-color .15s}
select:focus{border-color:var(--ac)}
.btn{padding:6px 12px;border-radius:8px;border:1px solid var(--bd);background:var(--s2);
  color:var(--tx);cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;
  gap:5px;font-weight:500;
  transition:background .12s,border-color .12s,color .12s,transform .08s}
.btn:hover{background:var(--acg);border-color:var(--ac);color:var(--ac)}
.btn:active{transform:scale(.96)}
.btn-p{background:var(--ac);border-color:var(--ac);color:#fff}
.btn-p:hover{background:var(--acd);border-color:var(--acd);color:#fff}
.btn:disabled{opacity:.35;cursor:default;pointer-events:none}
.cr{margin-left:auto;display:flex;align-items:center;gap:8px}
.cnt{font-size:12px;color:var(--tx2);white-space:nowrap}

/* table card */
.card{margin:8px 16px 0;border-radius:var(--r);border:1px solid var(--bd);
  box-shadow:var(--sh2);background:var(--surface);overflow:auto;flex:1;min-height:0}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{position:sticky;top:0;z-index:10;background:var(--s2);
  padding:9px 14px;text-align:left;font-size:11px;font-weight:700;
  text-transform:uppercase;letter-spacing:.55px;color:var(--tx2);
  border-bottom:1px solid var(--bd);cursor:pointer;user-select:none;
  white-space:nowrap;transition:color .1s}
thead th:hover{color:var(--tx)}
.sa{display:inline-block;margin-left:3px;font-size:9px;opacity:.3}
th.asc .sa,th.desc .sa{opacity:1;color:var(--ac)}
th.asc  .sa::after{content:'▲'}
th.desc .sa::after{content:'▼'}
th:not(.asc):not(.desc) .sa::after{content:'⇅'}
tbody tr{border-bottom:1px solid var(--bd);transition:background .08s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:var(--acg)}
tbody td{padding:7px 14px;vertical-align:middle}
.clb a{color:var(--ac);font-weight:600;text-decoration:none;font-variant-numeric:tabular-nums}
.clb a:hover{text-decoration:underline}
.cdt{white-space:nowrap;color:var(--tx2);font-variant-numeric:tabular-nums}
.cfl{font-size:12px;color:var(--tx2);max-width:280px;word-break:break-word}
.cno{font-size:12px;color:var(--tx2);font-style:italic;max-width:200px}

/* badges */
.b{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;
   font-weight:600;letter-spacing:.2px;text-transform:capitalize}
.bp{background:var(--pub-bg);color:var(--pub)}
.br{background:var(--priv-bg);color:var(--priv)}
.bm{background:var(--miss-bg);color:var(--miss)}
.bu{background:var(--unk-bg);color:var(--unk)}

/* highlight */
mark{background:#fde68a;color:#78350f;border-radius:2px;padding:0 1px;font-style:normal}
@media(prefers-color-scheme:dark){mark{background:#5c3706;color:#fcd34d}}

/* empty state */
.empty{padding:80px 20px;text-align:center;color:var(--tx2)}
.eico{font-size:36px;margin-bottom:10px;opacity:.5}

/* pagination */
.pg{flex-shrink:0;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:10px 16px}
.pg-lbl{font-size:13px;color:var(--tx2)}
.pg-sz{padding:5px 22px 5px 8px;border:1px solid var(--bd);border-radius:8px;
  background-color:var(--s2);color:var(--tx);outline:none;
  -webkit-appearance:none;appearance:none;font:12px/1.4 inherit;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='11' height='11' viewBox='0 0 24 24'%3E%3Cpath fill='%236a7390' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 6px center}
.pg-sz:focus{border-color:var(--ac)}
.pg .btn{padding:5px 10px;font-size:13px}
.ml{margin-left:auto}

/* footer */
.ftr{flex-shrink:0;margin-top:0;padding:14px 20px;text-align:center;font-size:12px;
  color:var(--tx2);border-top:1px solid var(--bd);background:var(--surface)}
.ftr a{color:var(--ac);text-decoration:none}

/* toast */
#toast{position:fixed;bottom:20px;right:20px;background:var(--surface);
  border:1px solid var(--bd);border-left:3px solid var(--ac);border-radius:10px;
  padding:9px 16px;font-size:13px;box-shadow:var(--sh2);z-index:9999;
  opacity:0;transform:translateY(10px);
  transition:opacity .2s,transform .2s;pointer-events:none}
#toast.on{opacity:1;transform:translateY(0)}

@media print{
  html,body{height:auto;overflow:visible;display:block}
  .hdr{position:static}
  .ctrl,.pg .btn{display:none!important}
  .card{flex:none;overflow:visible;height:auto;box-shadow:none;border:1px solid #ccc}
  body{background:white;color:black}
}
</style>
</head>
<body>
<header class="hdr" id="hdr">
  <div class="hdr-top">
    <div class="logo">LosslessBob <em>Collection</em></div>
    <span class="gen" id="genTs"></span>
  </div>
  <div class="stats" id="sbar"></div>
  <div class="ctrl">
    <div class="sw">
      <span class="si">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
      </span>
      <input type="search" id="qIn" placeholder="Search LB#, date, location, folder…" autocomplete="off">
    </div>
    <select id="fSt"><option value="">All statuses</option>
      <option value="public">\U0001f7e2 Public</option>
      <option value="private">\U0001f535 Private</option>
      <option value="missing">\U0001f534 Missing</option>
      <option value="unknown">⚪ Unknown</option>
    </select>
    <select id="fDec"><option value="">All decades</option></select>
    <select id="fYr"><option value="">All years</option></select>
    <button class="btn" onclick="clr()">&#x2715; Clear</button>
    <div class="cr">
      <button class="btn" onclick="dlCSV()" title="Download filtered rows as CSV">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>CSV
      </button>
      <button class="btn btn-p" onclick="cpLBs()" title="Copy visible LB numbers to clipboard">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>Copy LB#s
      </button>
      <span class="cnt" id="cntLbl"></span>
    </div>
  </div>
</header>

<div class="card">
  <table>
    <thead><tr id="thRow">
      <th data-col="lb"       onclick="srt('lb')">LB # <span class="sa"></span></th>
      <th data-col="status"   onclick="srt('status')">Status <span class="sa"></span></th>
      <th data-col="date"     onclick="srt('date')">Date <span class="sa"></span></th>
      <th data-col="location" onclick="srt('location')">Location <span class="sa"></span></th>
      <th data-col="folder"   onclick="srt('folder')">Folder <span class="sa"></span></th>
      <th data-col="notes"    onclick="srt('notes')">Notes <span class="sa"></span></th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>
  <div class="empty" id="emp" style="display:none">
    <div class="eico">\U0001f50d</div>
    <p>No recordings match your filters.</p>
  </div>
</div>

<div class="pg" id="pgBar">
  <button class="btn" id="p1"  onclick="go(1)"         title="First">&laquo;</button>
  <button class="btn" id="pp"  onclick="go(pg-1)"       title="Previous">&lsaquo;</button>
  <span class="pg-lbl" id="pLbl"></span>
  <button class="btn" id="pn"  onclick="go(pg+1)"       title="Next">&rsaquo;</button>
  <button class="btn" id="pl"  onclick="go(totPg())"    title="Last">&raquo;</button>
  <span class="ml">
    <select class="pg-sz" id="pSz" onchange="onPgSz()">
      <option value="50">50 / page</option>
      <option value="100" selected>100 / page</option>
      <option value="200">200 / page</option>
      <option value="500">500 / page</option>
    </select>
  </span>
</div>

<footer class="ftr">
  Generated <span id="ftrTs"></span> &middot;
  <a href="http://www.losslessbob.wonderingwhattochoose.com" target="_blank" rel="noopener">losslessbob.wonderingwhattochoose.com</a>
  &middot; Press <kbd>/</kbd> to search &middot; <kbd>←</kbd><kbd>→</kbd> to page
</footer>
<div id="toast"></div>

<script>
'use strict';
const DATA=__DATA_JSON__;
const GEN='__GENERATED_AT__';

const SM={public:{l:'Public',c:'#4ade80',r:0},private:{l:'Private',c:'#60a5fa',r:1},
          missing:{l:'Missing',c:'#f87171',r:2},unknown:{l:'Unknown',c:'#94a3b8',r:3}};
const BC={public:'bp',private:'br',missing:'bm'};
let sc='lb',sd=1,qr='',fSt='',fDec='',fYr='',pg=1,pz=100,fil=[];

(function boot(){
  document.getElementById('genTs').textContent=GEN;
  document.getElementById('ftrTs').textContent=GEN;
  mkDrops();mkStats();bindEvt();srt('lb');
})();

function mkDrops(){
  const yrs=[...new Set(DATA.map(r=>r.year).filter(Boolean))].sort().reverse();
  const decs=[...new Set(yrs.map(y=>String(Math.floor(+y/10)*10)))].sort().reverse();
  const yEl=document.getElementById('fYr');
  yrs.forEach(y=>{yEl.add(new Option(y,y))});
  const dEl=document.getElementById('fDec');
  decs.forEach(d=>{dEl.add(new Option(d+'s',d))});
}

function mkStats(){
  const cnt={public:0,private:0,missing:0,unknown:0};
  DATA.forEach(r=>{const k=r.status in cnt?r.status:'unknown';cnt[k]++;});
  const tot=DATA.length;
  const bits=[`<span class="pill"><strong>${tot.toLocaleString()}</strong>&thinsp;recordings</span>`];
  Object.entries(SM).filter(([k])=>cnt[k]>0).forEach(([k,m])=>{
    bits.push(`<span class="pill"><span class="dot" style="background:${m.c}"></span>${cnt[k].toLocaleString()}&thinsp;${m.l}</span>`);
  });
  document.getElementById('sbar').innerHTML=bits.join('');
}

function bindEvt(){
  let tmr;
  document.getElementById('qIn').addEventListener('input',e=>{
    clearTimeout(tmr);tmr=setTimeout(()=>{qr=e.target.value;pg=1;draw();},150);
  });
  ['fSt','fDec','fYr'].forEach(id=>{
    document.getElementById(id).addEventListener('change',e=>{
      if(id==='fSt')fSt=e.target.value;
      else if(id==='fDec')fDec=e.target.value;
      else fYr=e.target.value;
      pg=1;draw();
    });
  });
  document.addEventListener('keydown',e=>{
    const inp=document.getElementById('qIn');
    if(document.activeElement!==inp&&(e.key==='/'||(e.ctrlKey&&e.key==='k'))){
      e.preventDefault();inp.focus();inp.select();
    }
    if(document.activeElement===inp&&e.key==='Escape'){
      inp.value='';qr='';pg=1;draw();inp.blur();
    }
    if(!e.ctrlKey&&!e.altKey&&!e.metaKey&&document.activeElement!==inp){
      if(e.key==='ArrowRight'){e.preventDefault();go(pg+1);}
      if(e.key==='ArrowLeft'){e.preventDefault();go(pg-1);}
    }
  });
}

function apFil(){
  const q=qr.trim().toLowerCase();
  return DATA.filter(r=>{
    if(fSt&&r.status!==fSt)return false;
    if(fYr&&r.year!==fYr)return false;
    if(fDec&&String(Math.floor(+r.year/10)*10)!==fDec)return false;
    if(q){
      const h=`${r.lb_str} ${r.date} ${r.location} ${r.folder} ${r.notes}`.toLowerCase();
      if(!h.includes(q))return false;
    }
    return true;
  });
}

function apSort(rows){
  return rows.slice().sort((a,b)=>{
    if(sc==='lb')return(a.lb-b.lb)*sd;
    if(sc==='status'){const ra=SM[a.status]?.r??9,rb=SM[b.status]?.r??9;return(ra-rb)*sd;}
    const av=(a[sc]||'').toLowerCase(),bv=(b[sc]||'').toLowerCase();
    return av<bv?-sd:av>bv?sd:0;
  });
}

function srt(col){
  if(sc===col)sd*=-1;else{sc=col;sd=1;}
  document.querySelectorAll('thead th').forEach(th=>{
    th.classList.remove('asc','desc');
    if(th.dataset.col===col)th.classList.add(sd===1?'asc':'desc');
  });
  pg=1;draw();
}

function esc(s){
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function hl(txt,q){
  if(!q)return esc(txt);
  const s=esc(txt);
  return s.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')})`, 'gi'),'<mark>$1</mark>');
}

function totPg(){return Math.max(1,Math.ceil(fil.length/pz));}

function draw(){
  fil=apSort(apFil());
  const tb=document.getElementById('tb');
  const emp=document.getElementById('emp');
  if(!fil.length){tb.innerHTML='';emp.style.display='';document.getElementById('cntLbl').textContent='0 results';updPg();return;}
  emp.style.display='none';
  const q=qr.trim().toLowerCase();
  const st=(pg-1)*pz;
  tb.innerHTML=fil.slice(st,st+pz).map(r=>{
    const bc=BC[r.status]??'bu';
    return `<tr>
      <td class="clb"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.lb_str)}</a></td>
      <td><span class="b ${bc}">${esc(r.status)}</span></td>
      <td class="cdt">${hl(r.date,q)}</td>
      <td>${hl(r.location,q)}</td>
      <td class="cfl" title="${esc(r.folder)}">${hl(r.folder,q)}</td>
      <td class="cno">${hl(r.notes,q)}</td>
    </tr>`;
  }).join('');
  const n=fil.length,t=DATA.length;
  document.getElementById('cntLbl').textContent=n===t?`${n.toLocaleString()} recordings`:`${n.toLocaleString()} of ${t.toLocaleString()}`;
  updPg();
}

function updPg(){
  const tp=totPg();
  document.getElementById('pLbl').textContent=`Page ${pg} of ${tp}`;
  document.getElementById('p1').disabled=pg<=1;
  document.getElementById('pp').disabled=pg<=1;
  document.getElementById('pn').disabled=pg>=tp;
  document.getElementById('pl').disabled=pg>=tp;
  document.getElementById('pgBar').style.display=fil.length<=pz?'none':'';
}

function go(n){
  const tp=totPg();pg=Math.max(1,Math.min(tp,n));
  document.getElementById('tb').innerHTML='';
  draw();document.querySelector('.card').scrollTo({top:0,behavior:'smooth'});
}

function onPgSz(){pz=+document.getElementById('pSz').value;pg=1;draw();}

function clr(){
  document.getElementById('qIn').value='';
  document.getElementById('fSt').value='';
  document.getElementById('fDec').value='';
  document.getElementById('fYr').value='';
  qr='';fSt='';fDec='';fYr='';pg=1;draw();
}

function dlCSV(){
  const rows=[['LB#','Status','Date','Location','Folder','Notes'],
    ...fil.map(r=>[r.lb_str,r.status,r.date,r.location,r.folder,r.notes])];
  const csv=rows.map(r=>r.map(c=>`"${String(c??'').replace(/"/g,'""')}"`).join(',')).join('\\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,\\ufeff'+encodeURIComponent(csv);
  a.download='collection.csv';a.click();
  toast(`${fil.length.toLocaleString()} rows exported`);
}

function cpLBs(){
  navigator.clipboard.writeText(fil.map(r=>r.lb_str).join('\\n')).then(
    ()=>toast(`${fil.length.toLocaleString()} LB numbers copied`),
    ()=>toast('Clipboard access denied')
  );
}

let _tt;
function toast(msg){
  const el=document.getElementById('toast');
  el.textContent=msg;el.classList.add('on');
  clearTimeout(_tt);_tt=setTimeout(()=>el.classList.remove('on'),2800);
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    import sys

    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
