import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS

from backend import db as database
from backend import importer, scraper, scheduler

DATA_DIR = Path(__file__).parent.parent / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"

_scrape_thread = None


def create_app():
    app = Flask(__name__)
    CORS(app)

    database.init_db()
    scheduler.start_file_watcher()

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

    @app.route("/api/db/import", methods=["POST"])
    def db_import():
        try:
            data = request.get_json()
            file_path = data.get("file_path", "")
            path = Path(file_path)
            if not path.exists():
                return jsonify({"error": f"File not found: {file_path}"}), 404

            messages = []
            def progress_cb(msg):
                messages.append(msg)

            result = importer.run_import(path, progress_callback=progress_cb)

            if result.get("scrape_queued"):
                auto_scrape = database.get_meta("auto_scrape") != "0"
                if auto_scrape:
                    new_lbs = result.get("new_lb_numbers", [])
                    delay = int(database.get_meta("scrape_delay_ms") or 1500)
                    _start_scrape_thread(new_lbs, delay_ms=delay)

            return jsonify(result)
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
                keys = ["scrape_attachments", "scrape_delay_ms", "auto_scrape"]
                return jsonify({k: database.get_meta(k) for k in keys})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/db/reset", methods=["POST"])
    def db_reset():
        try:
            with database.get_connection() as conn:
                conn.executescript(
                    "DROP TABLE IF EXISTS checksums;"
                    "DROP TABLE IF EXISTS entries;"
                    "DROP TABLE IF EXISTS entry_files;"
                    "DROP TABLE IF EXISTS meta;"
                )
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

    @app.route("/api/entry/<int:lb_number>/scrape", methods=["POST"])
    def scrape_entry_route(lb_number):
        try:
            data = request.get_json() or {}
            force = data.get("force", False)
            delay = int(database.get_meta("scrape_delay_ms") or 1500)
            download = database.get_meta("scrape_attachments") != "0"
            result = scraper.scrape_entry(lb_number, force=force, download_files=download)
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

    # ── Scraper Control ──────────────────────────────────────────────────────

    @app.route("/api/scrape/start", methods=["POST"])
    def scrape_start():
        try:
            data = request.get_json() or {}
            start_lb = data.get("start_lb", 1)
            end_lb = data.get("end_lb", None)
            force = data.get("force", False)
            fill_gaps = data.get("fill_gaps", False)
            delay = int(database.get_meta("scrape_delay_ms") or 1500)
            download = database.get_meta("scrape_attachments") != "0"

            with database.get_connection() as conn:
                q = "SELECT DISTINCT lb_number FROM checksums WHERE lb_number >= ?"
                params = [start_lb]
                if end_lb:
                    q += " AND lb_number <= ?"
                    params.append(end_lb)
                q += " ORDER BY lb_number"
                lb_numbers = [r[0] for r in conn.execute(q, params).fetchall()]

            if fill_gaps and end_lb:
                known = set(lb_numbers)
                for n in range(start_lb, end_lb + 1):
                    if n not in known:
                        database.insert_missing_entry(n)

            _start_scrape_thread(lb_numbers, force=force, delay_ms=delay, download=download)
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

    return app


def _start_scrape_thread(lb_numbers, force=False, delay_ms=1500, download=True):
    global _scrape_thread
    if _scrape_thread and _scrape_thread.is_alive():
        return

    def run():
        scraper.scrape_range(
            lb_numbers,
            force=force,
            download_files=download,
            delay_ms=delay_ms,
        )

    _scrape_thread = threading.Thread(target=run, daemon=True)
    _scrape_thread.start()
