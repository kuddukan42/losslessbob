import os
import re
import shutil
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS

from backend import db as database
from backend import importer, scraper, scheduler
from backend import checksum_utils

from backend.paths import ATTACHMENTS_DIR

_scrape_thread = None

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


def create_app():
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
    def lookup():
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

    @app.route("/api/db/stats", methods=["GET"])
    def db_stats():
        try:
            return jsonify(database.get_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/missing_lb_numbers", methods=["GET"])
    def db_missing_lb_numbers():
        try:
            return jsonify(database.get_missing_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/import", methods=["POST"])
    def db_import():
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
                        _start_scrape_thread(new_lbs, delay_ms=delay)

            importer.start_import_async(path, on_complete=on_complete)
            return jsonify({"ok": True, "running": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/import/status", methods=["GET"])
    def db_import_status():
        try:
            return jsonify(importer.get_import_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/settings", methods=["GET", "POST"])
    def db_settings():
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
    def db_reset():
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

    @app.route("/api/db/check_update", methods=["GET"])
    def check_update():
        try:
            result = scraper.check_for_update()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Entry Detail & Attachments ───────────────────────────────────────────

    @app.route("/api/entry/<int:lb_number>", methods=["GET"])
    def get_entry(lb_number):
        try:
            data = database.get_entry(lb_number)
            if not data:
                return jsonify({"error": "Entry not found"}), 404
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entry/<int:lb_number>/files", methods=["GET"])
    def get_entry_files(lb_number):
        try:
            with database.get_connection() as conn:
                files = conn.execute(
                    "SELECT * FROM entry_files WHERE lb_number=?", (lb_number,)
                ).fetchall()
            return jsonify([dict(f) for f in files])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/attachment/<int:lb_number>/<path:filename>", methods=["GET"])
    def get_attachment(lb_number, filename):
        file_path = ATTACHMENTS_DIR / f"LB-{lb_number}" / filename
        if not file_path.exists():
            abort(404)
        return send_file(str(file_path))

    @app.route("/api/entry/<int:lb_number>/changes", methods=["GET"])
    def entry_changes(lb_number):
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
    def scrape_entry_route(lb_number):
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
    def search():
        try:
            q = request.args.get("q", "")
            field = request.args.get("field", "all")
            year_str = request.args.get("year")
            year = int(year_str) if year_str else None
            results = database.search_entries(q, field, year=year)
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/search/years", methods=["GET"])
    def search_years():
        try:
            return jsonify(database.get_distinct_years())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/checksums/xref_lb_numbers", methods=["GET"])
    def xref_lb_numbers():
        try:
            return jsonify(database.get_xref_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/checksums/xref_map", methods=["GET"])
    def xref_map():
        try:
            return jsonify(database.get_xref_map())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entries/year/<year>", methods=["GET"])
    def entries_by_year(year):
        try:
            results = database.get_entries_by_year(year)
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── My Collection ────────────────────────────────────────────────────────

    @app.route("/api/collection", methods=["GET"])
    def collection_list():
        try:
            return jsonify(database.get_collection())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection", methods=["POST"])
    def collection_add():
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
    def collection_update(lb):
        try:
            data = request.get_json() or {}
            database.update_collection(lb, data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>", methods=["DELETE"])
    def collection_delete(lb):
        try:
            database.delete_from_collection(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/missing", methods=["GET"])
    def collection_missing():
        try:
            return jsonify(database.get_missing_from_collection())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/search", methods=["GET"])
    def collection_search():
        try:
            q = request.args.get("q", "")
            return jsonify(database.search_collection(q))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/lb_numbers", methods=["GET"])
    def collection_lb_numbers():
        try:
            return jsonify(database.get_owned_lb_numbers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-03: Personal Metadata ───────────────────────────────────────────

    @app.route("/api/collection/<int:lb>/meta", methods=["GET"])
    def get_coll_meta(lb):
        try:
            return jsonify(database.get_collection_meta(lb))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>/meta", methods=["POST"])
    def set_coll_meta(lb):
        try:
            database.set_collection_meta(lb, request.get_json() or {})
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/<int:lb>/listen", methods=["POST"])
    def log_listen(lb):
        try:
            database.increment_listen_count(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-04: Wishlist ────────────────────────────────────────────────────

    @app.route("/api/wishlist", methods=["GET"])
    def wishlist_list():
        try:
            return jsonify(database.get_wishlist())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/wishlist", methods=["POST"])
    def wishlist_add():
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
    def wishlist_remove(lb):
        try:
            database.remove_from_wishlist(lb)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-05: Duplicate Detector ──────────────────────────────────────────

    @app.route("/api/collection/duplicates", methods=["GET"])
    def collection_duplicates():
        try:
            return jsonify(database.get_collection_duplicates())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── FEAT-13: Granular Collection Data Management ─────────────────────────

    @app.route("/api/collection/purge", methods=["POST"])
    def collection_purge():
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
    def collection_delete_bulk():
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
    def scrape_start():
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
    def scrape_status():
        return jsonify(scraper.get_scrape_status())

    @app.route("/api/scrape/stop", methods=["POST"])
    def scrape_stop():
        scraper.stop_scrape()
        return jsonify({"ok": True})

    # ── Verify ───────────────────────────────────────────────────────────────

    @app.route("/api/verify", methods=["POST"])
    def verify():
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
    def verify_generate():
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
    def lbdir_check():
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
    def lbdir_retrieve():
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
                attach_dir = ATTACHMENTS_DIR / f"LB-{lb_id}"

                lbdir_src = _find_lbdir_in_folder(attach_dir)
                was_scraped = False

                if not lbdir_src:
                    scraper.scrape_entry(lb_number, force=False, download_files=True)
                    lbdir_src = _find_lbdir_in_folder(attach_dir)
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
    def lbdir_reconcile():
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
    def lbdir_apply_reconcile():
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
    def lbdir_find_extra():
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
    def lbdir_delete_extra():
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
    def spectrogram_check():
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
    def spectrogram_generate():
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
    def spectrogram_status():
        with _spectro_lock:
            return jsonify(dict(_spectro_state))

    @app.route("/api/spectrogram/stop", methods=["POST"])
    def spectrogram_stop():
        with _spectro_lock:
            _spectro_state["stop_requested"] = True
        return jsonify({"ok": True})

    @app.route("/api/spectrogram/list", methods=["POST"])
    def spectrogram_list():
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
    def dbedit_tables():
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
    def dbedit_schema(name):
        try:
            conn = database.get_connection()
            cols = conn.execute(
                f"PRAGMA table_info([{name}])"
            ).fetchall()
            return jsonify([dict(c) for c in cols])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/rows", methods=["GET"])
    def dbedit_rows(name):
        try:
            page     = int(request.args.get("page", 0))
            limit    = min(int(request.args.get("limit", 100)), 500)
            search   = request.args.get("search", "").strip()
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
            conn     = database.get_connection()

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
    def dbedit_update_row(name):
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
    def dbedit_delete_rows(name):
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
    def dbedit_export(name):
        try:
            import csv, io
            conn = database.get_connection()
            rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
            buf  = io.StringIO()
            if rows:
                writer = csv.writer(buf)
                writer.writerow(rows[0].keys())
                writer.writerows(rows)
            from flask import Response
            return Response(
                buf.getvalue(), mimetype="text/csv",
                headers={"Content-Disposition":
                         f"attachment; filename={name}.csv"}
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Torrent Generation ───────────────────────────────────────────────────

    @app.route("/api/torrent/create", methods=["POST"])
    def torrent_create():
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
    def torrent_list(lb):
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
    def torrent_update(torrent_id):
        """Update a torrents row (e.g. source_folder after path relocation)."""
        try:
            fields = request.get_json() or {}
            database.update_torrent_record(torrent_id, fields)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/trackers", methods=["GET"])
    def trackers_get():
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
    def qbt_test():
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
    def qbt_add():
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
    def qbt_remove(torrent_id):
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
    def torrent_file_delete(torrent_id):
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
    def wtrf_test():
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
    def preview_forum(lb):
        """Return the forum post subject and body for an LB entry without posting.

        Returns: {subject, body}.
        """
        try:
            from backend.forum_poster import preview_lb_topic
            from backend.paths import ATTACHMENTS_DIR
            entry_data = database.get_entry(lb)
            if not entry_data:
                return jsonify({"ok": False, "error": f"Entry LB-{lb} not found"}), 404
            entry = entry_data["entry"]
            attach_dir = ATTACHMENTS_DIR / f"LB-{lb:05d}"
            result = preview_lb_topic(lb_number=lb, entry=entry, attachments_dir=attach_dir)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/entry/<int:lb>/post_forum", methods=["POST"])
    def post_forum(lb):
        """Post a topic to the WTRF forum for one LB entry.

        Body: {username?, password?, torrent_id?}
        Requires a torrents record for the entry to exist.
        Returns: {ok, topic_url} or {ok=False, error}.
        """
        try:
            from backend.forum_poster import post_lb_topic
            from backend.credentials import get_credentials, SERVICE_WTRF
            from backend.paths import ATTACHMENTS_DIR
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

            attach_dir = ATTACHMENTS_DIR / f"LB-{lb:05d}"
            result = post_lb_topic(
                lb_number=lb,
                torrent_path=torrent_path,
                username=username,
                password=password,
                entry=entry,
                board_id=board_id,
                attachments_dir=attach_dir,
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
    def forum_posts_list(lb):
        """Return all logged forum posts for an LB entry, newest first."""
        try:
            return jsonify(database.get_forum_posts_for_lb(lb))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/forum_post/<int:post_id>", methods=["DELETE"])
    def forum_post_delete(post_id):
        """Delete a forum post log record by id."""
        try:
            database.delete_forum_post(post_id)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/forum_posts", methods=["GET"])
    def all_forum_posts():
        """Return all logged forum posts across every LB entry, newest first."""
        try:
            return jsonify(database.get_all_forum_posts())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/torrents", methods=["GET"])
    def all_torrents():
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

    _slog.t("Flask: create_app done")
    return app


def _do_spectro_batch(folders: list[str], opts: dict) -> None:
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


def _start_scrape_thread(lb_numbers, force=False, delay_ms=1500, download=True, use_local_pages=False):
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
