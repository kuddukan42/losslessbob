import base64
import gzip as gzip_module
import logging
import time

from flask import (
    Flask,
    Response,
    jsonify,
    request,
)
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from backend import archive_org as _archive_org
from backend import db as database
from backend import (
    scheduler,
    sharing,
)
from backend.routes import _state as _route_state

_log = logging.getLogger(__name__)




# run_backend.py imports set_restart_callback from here.
from backend.routes.admin import set_restart_callback  # noqa: E402,F401


def create_app() -> Flask:
    """Create and configure the Flask application."""
    import backend.startup_log as _slog
    _slog.t("Flask: create_app start")
    app = Flask(__name__)
    CORS(app)

    # dossier.html (C29): segment/claim-span grouping lives in dossier_claims, not the
    # template, so it can't drift from how verdict_why()/chronicle() actually build a
    # T4 sentence -- exposed as a Jinja global rather than duplicated in Jinja logic.
    from backend.dossier_claims import claim_texts_for as _dossier_claim_texts_for
    from backend.dossier_claims import ledger_detail_text as _dossier_ledger_detail_text
    from backend.dossier_claims import sentence_segment_groups as _dossier_segment_groups
    from backend.dossier_fields import render_instrument_segments as _render_instr_segments
    app.jinja_env.globals["claim_groups"] = _dossier_segment_groups
    app.jinja_env.globals["claim_texts_for"] = _dossier_claim_texts_for
    app.jinja_env.globals["ledger_detail_text"] = _dossier_ledger_detail_text
    # TODO-347: instrument_segments() value -> display string (dossier.html stats line).
    app.jinja_env.globals["render_instrument_segments"] = _render_instr_segments

    @app.errorhandler(Exception)
    def _unhandled_exception(e):
        if isinstance(e, HTTPException):
            return e
        logging.getLogger(__name__).exception("Unhandled exception: %s %s",
                                              request.method, request.path)
        return jsonify({"error": str(e)}), 500

    # Process start time, used by /api/system/uptime and /api/admin/status to
    # show how long the backend has been running (TODO-285).
    _route_state.process_start_time = time.monotonic()

    # ── Gzip large JSON responses ─────────────────────────────────────────────
    # The bulk endpoints (/api/collection/prefetch ~36 MB, /api/search ~23 MB,
    # /api/attachments/cached ~13 MB) are dominated by werkzeug wire time
    # (~12 MB/s over loopback). Level-1 gzip cuts them ~4x for ~0.2 s of CPU;
    # Chromium's fetch() decompresses transparently, so the GUI needs no change.
    _GZIP_MIN_BYTES = 256 * 1024

    @app.after_request
    def _gzip_large_json(resp: Response) -> Response:
        if (
            resp.direct_passthrough
            or resp.status_code != 200
            or resp.mimetype != "application/json"
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
            or resp.headers.get("Content-Encoding")
            or (resp.content_length or 0) < _GZIP_MIN_BYTES
        ):
            return resp
        resp.set_data(gzip_module.compress(resp.get_data(), compresslevel=1))
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Content-Length"] = str(len(resp.get_data()))
        resp.headers.add("Vary", "Accept-Encoding")
        return resp

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
    # TODO-241: merge any user_taper_aliases overrides into the live
    # _KNOWN_TAPER_ALIASES / _TAPER_UNIVERSE tables before any request or
    # background job (file watcher, scheduler) can read them.
    database.reload_taper_aliases()
    _slog.t("Flask: start_file_watcher start")
    scheduler.start_file_watcher()
    scheduler.start_collection_watcher()
    scheduler.start_integrity_scan_scheduler()
    scheduler.start_file_verify_scheduler()
    scheduler.start_pipeline_cache_pruner()
    _slog.t("Flask: routes registering")

    from backend.routes.core import bp as _core_bp
    app.register_blueprint(_core_bp)

    from backend.routes.flat_file import bp as _flat_file_bp
    app.register_blueprint(_flat_file_bp)

    from backend.routes.entries import bp as _entries_bp
    app.register_blueprint(_entries_bp)

    from backend.routes.collection import bp as _collection_bp
    app.register_blueprint(_collection_bp)

    from backend.routes.scrape import bp as _scrape_bp
    app.register_blueprint(_scrape_bp)

    from backend.routes.bootlegs import bp as _bootlegs_bp
    app.register_blueprint(_bootlegs_bp)

    from backend.routes.crawler import bp as _crawler_bp
    app.register_blueprint(_crawler_bp)

    from backend.routes.lbdir import bp as _lbdir_bp
    app.register_blueprint(_lbdir_bp)

    from backend.routes.spectrogram import bp as _spectrogram_bp
    app.register_blueprint(_spectrogram_bp)

    from backend.routes.dbedit import bp as _dbedit_bp
    app.register_blueprint(_dbedit_bp)

    from backend.routes.torrents import bp as _torrents_bp
    app.register_blueprint(_torrents_bp)

    from backend.routes.wtrf import bp as _wtrf_bp
    app.register_blueprint(_wtrf_bp)

    from backend.routes.lb_master import bp as _lb_master_bp
    app.register_blueprint(_lb_master_bp)

    from backend.routes.lb_data import bp as _lb_data_bp
    app.register_blueprint(_lb_data_bp)

    from backend.routes.tapers import bp as _tapers_bp
    app.register_blueprint(_tapers_bp)

    from backend.routes.tapematch import bp as _tapematch_bp
    app.register_blueprint(_tapematch_bp)

    from backend.routes.ranking import bp as _ranking_bp
    app.register_blueprint(_ranking_bp)

    from backend.routes.dossier import bp as _dossier_bp
    app.register_blueprint(_dossier_bp)

    from backend.routes.aliases import bp as _aliases_bp
    app.register_blueprint(_aliases_bp)

    from backend.routes.map import bp as _map_bp
    app.register_blueprint(_map_bp)

    from backend.routes.admin import bp as _admin_bp
    app.register_blueprint(_admin_bp)

    from backend.routes.mounts import bp as _mounts_bp
    app.register_blueprint(_mounts_bp)

    from backend.routes.pipeline import bp as _pipeline_bp
    app.register_blueprint(_pipeline_bp)

    from backend.routes.export import bp as _export_bp
    app.register_blueprint(_export_bp)

    from backend.routes.setlists import bp as _setlists_bp
    app.register_blueprint(_setlists_bp)

    from backend.routes.trading import bp as _trading_bp
    app.register_blueprint(_trading_bp)

    # ── File Sharing ──────────────────────────────────────────────────────────

    sharing.load_persisted_shares()

    from backend.routes.sharing import bp as _sharing_bp
    app.register_blueprint(_sharing_bp)

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


if __name__ == "__main__":
    import sys

    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
