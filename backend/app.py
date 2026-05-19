import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory, abort, Response
from flask_cors import CORS

from backend import db as database
from backend import importer, scraper, scheduler
from backend import checksum_utils
from backend import bootleg_scraper
from backend import site_crawler

from backend.paths import DATA_DIR, SITE_DIR, SITE_FILES_DIR, attachment_path, find_lbdir_attachment

_log = logging.getLogger(__name__)

# Rate-limit for /api/db/backup (#3): reject if last manual backup was < 60 s ago
_last_backup_at: float = 0.0
_backup_lock = threading.Lock()

_scrape_thread = None

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

    _slog.t("Flask: init_db start")
    database.init_db()
    _slog.t("Flask: init_db done")
    _slog.t("Flask: start_file_watcher start")
    scheduler.start_file_watcher()
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
            return jsonify({"summary": summary, "detail": detail})
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
                        "force_scrape", "search_page_size",
                        "qbt_host", "qbt_port", "qbt_category", "qbt_tags",
                        "tracker_list", "wtrf_board_id"]
                return jsonify({k: database.get_meta(k) for k in keys})
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
            delay = int(database.get_meta("scrape_delay_ms") or 1500)
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

    # ── Scraper Control ──────────────────────────────────────────────────────

    @app.route("/api/scrape/start", methods=["POST"])
    def scrape_start() -> Response:
        """Start a background scrape over a range of LB numbers.

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
                q = "SELECT DISTINCT lb_number FROM checksums WHERE lb_number >= ?"
                params = [start_lb]
                if end_lb:
                    q += " AND lb_number <= ?"
                    params.append(end_lb)
                q += " ORDER BY lb_number"
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

        Existing ``data/pages/LB-{n:05d}.html`` files are skipped unless
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
                if v == "true":  return True
                if v == "false": return False
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
            daily_cap (int):  Max requests this session.  Default 5000.

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
            daily_cap = int(data.get("daily_cap", 5000))
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

        Body: {folders: ["/path/to/folder", ...]}
        Returns:
            JSON {results: [lbdir_check_result, ...]} or 400 if folders is empty.
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not folders:
                return jsonify({"error": "folders list required"}), 400

            results = []
            for folder_path in folders:
                folder = Path(folder_path)

                # Look up LB number from collection by disk_path
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?",
                        (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None

                lbdir_path = _find_lbdir_in_folder(folder)

                if not lbdir_path:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": lb_number,
                        "lbdir_found": False,
                        "lbdir_path": None,
                        "error": "No lbdir*.txt found in folder",
                    })
                    continue

                result = checksum_utils.verify_folder_lbdir(folder_path, lbdir_path)
                result["lb_number"] = lb_number
                result["lbdir_found"] = True
                result["lbdir_path"] = str(lbdir_path)
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

            results = []
            for folder_path in folders:
                folder = Path(folder_path)

                # Look up LB number: try my_collection first, then parse folder name
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

                if lb_number is None:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": None,
                        "status": "no_lb_number",
                        "lbdir_filename": None,
                    })
                    continue
                lb_id = f"{lb_number:05d}"

                lbdir_src = find_lbdir_attachment(lb_number)
                was_scraped = False

                if not lbdir_src:
                    scraper.scrape_entry(lb_number, force=False, download_files=True)
                    lbdir_src = find_lbdir_attachment(lb_number)
                    was_scraped = True

                if not lbdir_src:
                    results.append({
                        "folder": str(folder_path),
                        "lb_number": lb_number,
                        "status": "not_found",
                        "lbdir_filename": None,
                    })
                    continue

                dest = folder / lbdir_src.name
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
        """Preview: find disk files whose MD5 matches missing lbdir entries. Does NOT move files."""
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
                result = checksum_utils.find_reconcilable_files(folder, lbdir_path)
                result["folder"] = str(folder)
                results.append(result)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/lbdir/apply_reconcile", methods=["POST"])
    def lbdir_apply_reconcile() -> Response:
        """Apply verified rename/move proposals inside a single folder. Never deletes files."""
        try:
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            renames = data.get("renames", [])  # [{"from": rel, "to": rel}, ...]
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
            return jsonify({"applied": len(applied), "errors": errors})
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
            for dirpath, dirnames, filenames in os.walk(str(folder), topdown=False):
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

    # ── Spectrogram ──────────────────────────────────────────────────────────

    @app.route("/api/spectrogram/check", methods=["GET"])
    def spectrogram_check() -> Response:
        """Return tool availability for the Setup tab indicator."""
        from backend.sox_utils import check_sox_version, get_ffmpeg
        from backend.checksum_utils import check_shntool_version
        sox_ver     = check_sox_version()
        ffmpeg      = get_ffmpeg()
        shntool_ver = check_shntool_version()
        return jsonify({
            "sox_available":      bool(sox_ver),
            "sox_version":        sox_ver,
            "ffmpeg_available":   ffmpeg is not None,
            "shntool_available":  bool(shntool_ver),
            "shntool_version":    shntool_ver,
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
            if _spectro_state["status"] == "running":
                return jsonify({"error": "Generation already running"}), 409

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

    # ── FEAT-14: DB Editor ───────────────────────────────────────────────────

    @app.route("/api/dbedit/tables", methods=["GET"])
    def dbedit_tables() -> Response:
        """List all user-visible tables and views with row counts and edit flags.

        Returns:
            JSON list of {name, row_count, readonly, audit, warn} dicts.
        """
        try:
            conn = database.get_connection()
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
                    "readonly":  name in _DBEDIT_READONLY,
                    "audit":     name in _DBEDIT_AUDIT,
                    "warn":      name in _DBEDIT_WARN,
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
            conn = database.get_connection()
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
            conn     = database.get_connection()

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
        if name in _DBEDIT_READONLY or name in _DBEDIT_AUDIT:
            return jsonify({"error": f"Table {name!r} is not editable"}), 403
        try:
            data    = request.get_json() or {}
            rowid   = data.get("rowid")
            updates = data.get("updates", {})
            if rowid is None or not updates:
                return jsonify({"error": "rowid and updates required"}), 400
            conn  = database.get_connection()
            valid = {c["name"] for c in
                     conn.execute(f"PRAGMA table_info([{name}])").fetchall()}
            bad = [k for k in updates if k not in valid]
            if bad:
                return jsonify({"error": f"Unknown columns: {bad}"}), 400
            set_clause = ", ".join(f"[{k}]=?" for k in updates)
            conn.execute(
                f"UPDATE [{name}] SET {set_clause} WHERE rowid=?",
                list(updates.values()) + [rowid]
            )
            conn.commit()
            return jsonify({"ok": True,
                            "affected": conn.execute("SELECT changes()").fetchone()[0]})
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
        if name in _DBEDIT_READONLY:
            return jsonify({"error": f"Table {name!r} cannot be modified"}), 403
        try:
            rowids = (request.get_json() or {}).get("rowids", [])
            if not rowids:
                return jsonify({"error": "rowids list required"}), 400
            conn = database.get_connection()
            ph   = ",".join("?" * len(rowids))
            conn.execute(f"DELETE FROM [{name}] WHERE rowid IN ({ph})", rowids)
            conn.commit()
            return jsonify({"ok": True,
                            "deleted": conn.execute("SELECT changes()").fetchone()[0]})
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
            import csv, io
            conn = database.get_connection()
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
            from backend.qbittorrent import test_connection
            from backend.credentials import get_credentials, SERVICE_QBT, SERVICE_QBT_KEY
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
            from backend.qbittorrent import add_torrent_from_db
            from backend.credentials import get_credentials, SERVICE_QBT, SERVICE_QBT_KEY
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

        Uses the stored infohash. Clears added_to_qbt on success.
        Body: {host?, port?, username?, password?, api_key?}
        Returns: {ok, error?}
        """
        try:
            from backend.qbittorrent import remove_torrent
            from backend.credentials import get_credentials, SERVICE_QBT, SERVICE_QBT_KEY
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
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

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

    # ── Forum Posting ─────────────────────────────────────────────────────────

    @app.route("/api/wtrf/test", methods=["POST"])
    def wtrf_test() -> Response:
        """Test WTRF forum credentials by attempting a login (no post is made).

        Body: {username?, password?} — falls back to stored keyring credentials.
        Returns: {ok, username} or {ok=False, error}.
        """
        try:
            from backend.forum_poster import _get_session
            from backend.credentials import get_credentials, SERVICE_WTRF
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
            entry = entry_data["entry"]
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

            from backend.forum_poster import post_lb_topic
            from backend.credentials import get_credentials, SERVICE_WTRF
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
            entry = entry_data["entry"]

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
        try:
            stats = database.reconcile_all_lb_master()
            return jsonify({"ok": True, "stats": stats})
        except Exception:
            _log.exception("lb_master_reconcile failed")  # #9
            return jsonify({"error": "internal_error"}), 500

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
        """Create a GitHub release for a just-exported master snapshot. Curator-only.

        Requires the ``gh`` CLI to be authenticated. Picks a tag in the form
        ``master-YYYY-MM-DD``, appending ``.2`` / ``.3`` etc. on same-day
        re-releases. Generates release notes from ``lb_status_history`` since
        the previous ``master_published_at``.

        Body: {db_path, manifest_path, version, prev_published_at (optional)}.
        Returns: {ok, tag, url} or {error}.
        """
        import subprocess
        from datetime import datetime, timezone

        try:
            if not database.is_curator():
                return jsonify({"error": "curator_required"}), 403

            body = request.get_json(silent=True) or {}
            db_path_str = body.get("db_path", "")
            manifest_path_str = body.get("manifest_path", "")
            version = body.get("version", "")
            prev_published_at = body.get("prev_published_at")

            if not db_path_str or not manifest_path_str:
                return jsonify({"error": "db_path and manifest_path are required"}), 400

            # Derive date from version (format: YYYY-MM-DDTHH:MM:SS or timestamp)
            try:
                date_str = version[:10] if version else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Find an unused tag: master-YYYY-MM-DD[.N]
            tag = f"master-{date_str}"
            for suffix in ["", ".2", ".3", ".4", ".5"]:
                candidate = f"{tag}{suffix}"
                check = subprocess.run(
                    ["gh", "release", "view", candidate, "--repo", "kuddukan42/losslessbob"],
                    capture_output=True,
                )
                if check.returncode != 0:
                    tag = candidate
                    break

            notes = database.generate_release_notes(
                since_timestamp=prev_published_at,
            )

            result = subprocess.run(
                [
                    "gh", "release", "create", tag,
                    db_path_str,
                    manifest_path_str,
                    "--title", f"Master Update {date_str}",
                    "--notes", notes,
                    "--repo", "kuddukan42/losslessbob",
                ],
                capture_output=True, text=True, timeout=120,
            )

            if result.returncode != 0:
                return jsonify({
                    "error": "gh_failed",
                    "message": result.stderr.strip() or result.stdout.strip(),
                }), 500

            url = result.stdout.strip()
            return jsonify({"ok": True, "tag": tag, "url": url})

        except FileNotFoundError:
            return jsonify({"error": "gh_not_found",
                            "message": "gh CLI not found — install GitHub CLI first."}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "timeout", "message": "gh upload timed out after 120s"}), 500
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/master/import", methods=["POST"])
    def master_import() -> Response:
        """Apply a master snapshot to the local DB, preserving user data.

        Body: {path: "/abs/path/to/snapshot.db"}. Manifest sidecar must live
        alongside the snapshot at <path>.manifest.json.
        """
        if not database.is_curator():  # #2
            return jsonify({"error": "curator_required",
                            "message": "Master import requires curator mode."}), 403
        try:
            body = request.get_json(silent=True) or {}
            path = body.get("path")
            if not path:
                return jsonify({"error": "missing_path"}), 400
            # #1 — directory containment: only allow exports/ or imports/ sub-dirs
            snapshot_path = Path(path).resolve()
            allowed_dirs = [DATA_DIR / "exports", DATA_DIR / "imports"]
            if not any(snapshot_path.is_relative_to(d) for d in allowed_dirs):
                return jsonify({"error": "path_not_allowed",
                                "message": "Snapshot must be in data/exports/ or data/imports/"}), 400
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
        except Exception:
            _log.exception("master_import failed")  # #9
            return jsonify({"error": "internal_error"}), 500

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

        if not location or lat is None or lon is None:
            return jsonify({"error": "location, lat, lon required"}), 400

        _geocoder.place_manual(location, float(lat), float(lon), note)
        return jsonify({"ok": True})

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
                "failed":         "WHERE source = 'failed'",
                "low_confidence": "WHERE confidence = 'low'",
                "manual":         "WHERE manual_override = 1",
                "all":            "",
            }
            where = where_map.get(filter_type, "")
            rows = conn.execute(
                f"SELECT * FROM location_geocoded {where} ORDER BY location_text"
            ).fetchall()
            return jsonify({"locations": [dict(r) for r in rows]})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Admin page ───────────────────────────────────────────────────────────
    import time as _time
    _admin_start_time = _time.monotonic()

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
            result["uptime_seconds"] = round(_time.monotonic() - _admin_start_time)
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
            _time.sleep(0.3)
            if _restart_callback is not None:
                _restart_callback()
            else:
                _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

        _threading.Thread(target=_do_restart, daemon=True).start()
        return jsonify({"ok": True, "message": "Restarting…"}), 202

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
    from backend.sox_utils import (
        generate_spectrogram, AUDIO_EXTS_ALL,
        SoxNotFoundError, ConversionError, SpectrogenError,
    )

    def _set(**kw):
        with _spectro_lock:
            _spectro_state.update(kw)

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
        use_local_pages: Read from data/pages/ cache instead of the network.
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


if __name__ == "__main__":
    import sys
    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
