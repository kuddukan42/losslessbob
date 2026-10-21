import base64
import gzip as gzip_module
import json
import logging
import os
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
    stream_with_context,
)
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from backend import archive_org as _archive_org
from backend import (
    bobdylan_scraper,
    scheduler,
    sharing,
)
from backend import db as database
from backend import setlist_fingerprint as _setlist_fingerprint
from backend import setlistfm as setlistfm_mod
from backend.github_upload import _github_upload_asset
from backend.paths import (
    DATA_DIR,
    SITE_DIR,
    SITE_FILES_DIR,
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
                "created_at": datetime.now(UTC).isoformat() + "Z",
                "files": manifest_files,
                "file_count": len(manifest_files),
                "total_bytes": sum(f["size_bytes"] for f in manifest_files),
            }
            _log.info("package_user_data: wrote %s (%d files)", zip_path.name, len(manifest_files))
            return jsonify({"ok": True, "path": str(zip_path), "manifest": manifest})
        except Exception:
            _log.exception("package_user_data failed")
            return jsonify({"error": "internal_error"}), 500

    def _package_site_data(part: str | None) -> "tuple[Path, Path, dict]":
        """Bundle ``data/site/`` (or a subset of it) into a dated zip + manifest.

        Mirrors :func:`backend.db.export_master_db`'s manifest convention: a
        ``<zip_name>.manifest.json`` sidecar written next to the zip with
        ``type``, ``created_at``, ``file_count``, ``total_bytes``, ``sha256``.

        Args:
            part: ``None`` to package the whole ``data/site/`` tree (legacy,
                backward-compatible behavior); ``"core"`` for everything
                except ``data/site/files/``; ``"files"`` for only
                ``data/site/files/``. See FABLE_ONBOARDING_SYNC.md §3.

        Returns:
            (zip_path, manifest_path, manifest_dict).

        Raises:
            FileNotFoundError: If ``data/site/`` does not exist yet.
        """
        import hashlib
        import zipfile
        from datetime import date, datetime

        if not SITE_DIR.exists():
            raise FileNotFoundError("data/site/ does not exist. Run the site crawler first.")

        exports_dir = DATA_DIR / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        date_str = date.today().isoformat()
        if part is None:
            base_name = f"losslessbob_sitedata_{date_str}"
            manifest_type = "scrape_data"
        else:
            base_name = f"losslessbob_sitedata_{part}_{date_str}"
            manifest_type = f"sitedata_{part}"

        zip_path = exports_dir / f"{base_name}.zip"
        counter = 2
        while zip_path.exists():
            zip_path = exports_dir / f"{base_name}_{counter}.zip"
            counter += 1

        def _include(src: Path) -> bool:
            if part is None:
                return True
            under_files = src.is_relative_to(SITE_FILES_DIR)
            return under_files if part == "files" else not under_files

        file_count = 0
        total_bytes = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in sorted(SITE_DIR.rglob("*")):
                if src.is_file() and _include(src):
                    arc_name = "site/" + src.relative_to(SITE_DIR).as_posix()
                    zf.write(src, arc_name)
                    file_count += 1
                    total_bytes += src.stat().st_size

        sha = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)

        manifest = {
            "type": manifest_type,
            "created_at": datetime.now(UTC).isoformat() + "Z",
            "file_count": file_count,
            "total_bytes": total_bytes,
            "sha256": sha.hexdigest(),
        }
        manifest_path = zip_path.with_name(zip_path.name + ".manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        return zip_path, manifest_path, manifest

    @app.route("/api/package/scrape_data", methods=["POST"])
    def package_scrape_data() -> Response:
        """Bundle scraped site data (data/site/) into a dated zip in data/exports/.

        Query param ``part`` selects the subset to package:
          - omitted (default): the whole ``data/site/`` tree in one zip —
            backward-compatible with existing callers (ScreenSetup).
          - ``core``: everything except ``data/site/files/`` (detail pages,
            artwork, lbbcd/bynumber indexes). Recommended for all users.
          - ``files``: only ``data/site/files/`` (checksum/fingerprint text
            attachments). Optional, much larger.

        A ``<zip_name>.manifest.json`` sidecar is written next to the zip.

        Returns: {ok, path, manifest_path, manifest: {type, created_at,
        file_count, total_bytes, sha256}}
        """
        part = request.args.get("part")
        if part not in (None, "core", "files"):
            return jsonify({
                "error": "invalid_part",
                "message": "part must be 'core' or 'files'",
            }), 400

        try:
            zip_path, manifest_path, manifest = _package_site_data(part)
            _log.info("package_scrape_data: wrote %s (%d files, part=%s)",
                       zip_path.name, manifest["file_count"], part or "all")
            return jsonify({
                "ok": True,
                "path": str(zip_path),
                "manifest_path": str(manifest_path),
                "manifest": manifest,
            })
        except FileNotFoundError as exc:
            return jsonify({"error": "no_site_data", "message": str(exc)}), 400
        except Exception:
            _log.exception("package_scrape_data failed")
            return jsonify({"error": "internal_error"}), 500

    def _restore_sitedata_zip(zip_path: "Path", dry_run: bool = False) -> dict:
        """Extract a ``site/``-prefixed zip (whole-tree, core, or files) into SITE_DIR.

        Shared by ``/api/package/restore`` (local zip path, legacy manifest-less
        ``scrape_data`` zips) and the ``/api/sitedata/github_install`` pipeline
        (P1's ``sitedata_core``/``sitedata_files`` zips — same ``site/``-prefixed
        entry layout, just a subset of the tree). Every entry is written to
        ``SITE_DIR / <relative path>``, overwriting any existing file, so
        re-running against the same or an updated zip is a clean overwrite —
        no doubled files.

        Args:
            zip_path: Path to the zip archive.
            dry_run: If True, compute the restored/conflicts split without
                writing anything to disk.

        Returns:
            {"restored": [{name, dest}], "conflicts": [{name, dest}]} — a
            "conflict" is an entry whose destination already existed (still
            overwritten unless dry_run).
        """
        import zipfile

        restored: list[dict] = []
        conflicts: list[dict] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for arc_name in zf.namelist():
                if not arc_name.startswith("site/") or arc_name.endswith("/"):
                    continue
                rel = arc_name[len("site/"):]
                dest = SITE_DIR / rel
                entry = {"name": arc_name, "dest": str(dest)}
                if dest.exists():
                    conflicts.append(entry)
                else:
                    restored.append(entry)
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(arc_name))
        return {"restored": restored, "conflicts": conflicts}

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
                        # Covers legacy whole-tree scrape_data zips as well as
                        # P1's sitedata_core/sitedata_files zips — all three
                        # share the same "site/"-prefixed entry layout and are
                        # distinguished only by the manifest.json *sidecar*
                        # (never embedded in the zip itself), so name-based
                        # detection collapses them onto the same restore path.
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

                elif pkg_type in ("scrape_data", "sitedata_core", "sitedata_files"):
                    extraction = _restore_sitedata_zip(zip_path, dry_run=dry_run)
                    restored, conflicts = extraction["restored"], extraction["conflicts"]
                    if not dry_run:
                        _log.info("package_restore(%s): restored %d files from %s",
                                  pkg_type, len(restored) + len(conflicts), zip_path.name)

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

    @app.route("/api/sitedata/github_release", methods=["POST"])
    def sitedata_github_release() -> Response:
        """Package site data (core + files) and publish both as a GitHub release.

        Curator-only. Mirror of ``master_github_release``: builds the two
        assets locally (via ``_package_site_data``), obtains a token via
        ``gh auth token``, then uses the GitHub REST API to create a release
        tagged ``sitedata-<YYYY-MM-DD>`` and upload all 4 assets (2 zips +
        2 ``.manifest.json`` sidecars) with byte-accurate progress.

        Body: none required.
        Returns: text/event-stream with events:
          data: {"type": "progress", "label": "...", "pct": N_or_null}
          data: {"type": "done", "tag": "...", "url": "..."}
          data: {"type": "error", "error": "...", "message": "..."}
        """
        import json as _json
        import queue
        import subprocess
        from datetime import date

        import requests as _req

        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403

        _REPO = "kuddukan42/losslessbob"
        _GH_API = "https://api.github.com"
        ev_q: queue.Queue = queue.Queue()

        def _work() -> None:
            try:
                # Build both assets first so a packaging failure surfaces
                # before we ever touch the network.
                ev_q.put({"type": "progress", "label": "Packaging core site data…", "pct": None})
                try:
                    core_zip, core_manifest_path, _core_manifest = _package_site_data("core")
                except FileNotFoundError as exc:
                    ev_q.put({"type": "error", "error": "no_site_data", "message": str(exc)})
                    return

                ev_q.put({"type": "progress", "label": "Packaging site files…", "pct": None})
                files_zip, files_manifest_path, _files_manifest = _package_site_data("files")

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

                date_str = date.today().isoformat()

                # Find an unused tag: sitedata-YYYY-MM-DD[.N]
                ev_q.put({"type": "progress", "label": "Checking for existing releases…", "pct": None})
                base_tag = f"sitedata-{date_str}"
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

                # Create the GitHub release
                ev_q.put({"type": "progress", "label": f"Creating release {tag}…", "pct": None})
                cr = _req.post(
                    f"{_GH_API}/repos/{_REPO}/releases",
                    headers=gh_hdr,
                    json={
                        "tag_name": tag,
                        "name": f"Site Data {date_str}",
                        "body": "Cached LB site data (detail pages, artwork, "
                                "attachments). See manifest sidecars for contents.",
                    },
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

                def _upload_asset(file_path: Path, label: str) -> None:
                    _github_upload_asset(_req, upload_base, token, file_path, label, ev_q)

                for asset_path in (core_zip, core_manifest_path, files_zip, files_manifest_path):
                    ev_q.put({"type": "progress", "label": f"Uploading {asset_path.name}…", "pct": 0})
                    _upload_asset(asset_path, asset_path.name)

                ev_q.put({"type": "done", "tag": tag, "url": release_url})

            except FileNotFoundError:
                ev_q.put({"type": "error", "error": "gh_not_found",
                          "message": "gh CLI not found — install GitHub CLI first."})
            except Exception as exc:
                ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

        def _stream():
            from backend import activity as _activity

            with _activity.track("sitedata_publish", screen="/setup") as _job:
                while True:
                    try:
                        ev = ev_q.get(timeout=680)
                    except queue.Empty:
                        ev = {"type": "error", "error": "timeout",
                              "message": "Upload timed out after 680 s."}
                    if ev.get("type") == "progress":
                        _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                    yield f"data: {_json.dumps(ev)}\n\n"
                    if ev.get("type") in ("done", "error"):
                        break

        return Response(
            stream_with_context(_stream()),
            content_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    def _find_sitedata_release(_req) -> "tuple[dict, dict]":
        """Search recent GitHub releases for the latest ``sitedata-*`` release.

        Mirrors ``_find_master_release`` but scoped to the ``sitedata-``
        tag prefix (the repo also carries ``master-*`` releases on the same
        endpoint) and pairs *both* core and files parts rather than a single
        asset. Real releases carry GitHub's numeric collision suffix on the
        zip name (e.g. ``losslessbob_sitedata_core_2026-07-10_2.zip`` when a
        same-day zip of that part already existed at packaging time), so
        parts are identified by substring (``_core_`` / ``_files_``) rather
        than an exact date-stamped filename, then paired with the
        ``<zip_name>.manifest.json`` sidecar asset uploaded alongside it.

        Args:
            _req: the ``requests`` module (or compatible), passed in for
                testability.

        Returns:
            (release, parts) where ``parts`` is a dict with up to
            ``"core"``/``"files"`` keys, each
            ``{"zip_asset": asset, "manifest_asset": asset}``. Only parts
            with both a zip and a matching manifest sidecar present are
            included.

        Raises:
            RuntimeError: No ``sitedata-*`` release with at least one
                complete (zip + manifest) part is found in the most recent
                5 pages of releases.
        """
        _REPO = "kuddukan42/losslessbob"
        page = 1
        while page <= 5:
            resp = _req.get(
                f"https://api.github.com/repos/{_REPO}/releases",
                headers={"Accept": "application/vnd.github+json"},
                params={"per_page": 20, "page": page},
                timeout=15,
            )
            if resp.status_code == 404 or (page == 1 and resp.json() == []):
                raise RuntimeError("No releases found on GitHub yet.")
            resp.raise_for_status()
            releases = resp.json()
            if not releases:
                break
            for release in releases:
                if not str(release.get("tag_name", "")).startswith("sitedata-"):
                    continue
                assets = release.get("assets", [])
                parts: dict = {}
                for part in ("core", "files"):
                    zip_asset = next(
                        (a for a in assets
                         if f"_{part}_" in a["name"] and a["name"].endswith(".zip")),
                        None,
                    )
                    if not zip_asset:
                        continue
                    manifest_name = zip_asset["name"] + ".manifest.json"
                    manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
                    if not manifest_asset:
                        continue
                    parts[part] = {"zip_asset": zip_asset, "manifest_asset": manifest_asset}
                if parts:
                    return release, parts
            page += 1
        raise RuntimeError("No release with sitedata assets found on GitHub.")

    @app.route("/api/sitedata/github_check", methods=["GET"])
    def sitedata_github_check() -> Response:
        """Check GitHub Releases for the latest ``sitedata-*`` release.

        Returns:
            JSON dict with ``available`` (bool), ``tag``, ``release_url``,
            ``published_at`` plus a ``parts`` dict keyed by whichever of
            ``core``/``files`` are present in the release, each
            ``{asset_name, asset_size, manifest}`` (manifest sidecars are a
            few hundred bytes, so fetched eagerly — cheap). If no usable
            release exists, ``available`` is ``false`` with a human-readable
            ``message``, mirroring ``master_github_check``.
        """
        import requests as _req

        try:
            try:
                release, parts = _find_sitedata_release(_req)
            except RuntimeError as exc:
                return jsonify({"available": False, "message": str(exc)})

            parts_out = {}
            for part, info in parts.items():
                zip_asset = info["zip_asset"]
                manifest_asset = info["manifest_asset"]
                mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
                mresp.raise_for_status()
                parts_out[part] = {
                    "asset_name": zip_asset["name"],
                    "asset_size": zip_asset.get("size", 0),
                    "manifest": mresp.json(),
                }

            return jsonify({
                "available": True,
                "tag": release.get("tag_name", "?"),
                "release_url": release.get("html_url", ""),
                "published_at": release.get("published_at", ""),
                "parts": parts_out,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/sitedata/github_install", methods=["POST"])
    def sitedata_github_install() -> Response:
        """Download and install site-data part(s) from the latest ``sitedata-*`` release.

        Body: ``{"parts": ["core"]}`` or ``["core", "files"]`` — default
        ``["core"]``.

        Streams progress via ``text/event-stream``, mirroring
        ``master_github_install``'s event shape:
          data: {"type": "progress", "label": "...", "pct": N_or_null}
          data: {"type": "done", "summary": {...}}
          data: {"type": "error", "error": "...", "message": "..."}

        For each selected part: downloads the zip asset to ``data/imports/``,
        fetches its manifest sidecar, and verifies the zip's SHA256 against
        the manifest *before* any extraction — a mismatch deletes the
        downloaded zip and errors out without touching ``SITE_DIR``. On
        success, extracts into ``SITE_DIR`` via ``_restore_sitedata_zip``
        (overwrite semantics — re-running is a clean overwrite, no doubled
        files) and writes a ``.sitedata_<part>_manifest.json`` marker in
        ``SITE_DIR`` so ``/api/onboarding/status`` can read part presence /
        file counts without rescanning the filesystem.
        """
        import hashlib
        import json as _json
        import queue

        import requests as _req

        body = request.get_json(silent=True) or {}
        parts = body.get("parts") or ["core"]
        invalid = [p for p in parts if p not in ("core", "files")]
        if invalid:
            return jsonify({
                "error": "invalid_part",
                "message": f"Unknown part(s): {invalid}. Must be 'core' and/or 'files'.",
            }), 400

        ev_q: queue.Queue = queue.Queue()

        def _work() -> None:
            try:
                ev_q.put({"type": "progress",
                          "label": "Checking GitHub for latest site-data release…", "pct": None})
                try:
                    release, available_parts = _find_sitedata_release(_req)
                except RuntimeError as exc:
                    ev_q.put({"type": "error", "error": "no_releases", "message": str(exc)})
                    return

                tag = release.get("tag_name", "?")
                dest_dir = DATA_DIR / "imports"
                dest_dir.mkdir(parents=True, exist_ok=True)

                summary: dict = {"tag": tag, "parts": {}}

                for part in parts:
                    part_info = available_parts.get(part)
                    if part_info is None:
                        ev_q.put({"type": "error", "error": "part_not_found",
                                  "message": f"No '{part}' asset found in release {tag}."})
                        return

                    zip_asset = part_info["zip_asset"]
                    manifest_asset = part_info["manifest_asset"]

                    ev_q.put({"type": "progress",
                              "label": f"Downloading manifest for {part}…", "pct": None})
                    mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
                    mresp.raise_for_status()
                    manifest = mresp.json()

                    zip_dest = dest_dir / zip_asset["name"]
                    manifest_dest = dest_dir / manifest_asset["name"]

                    total_bytes = zip_asset.get("size", 0)
                    total_mb = total_bytes / (1 << 20)
                    ev_q.put({"type": "progress",
                              "label": f"Downloading {zip_asset['name']} ({total_mb:.0f} MB)…",
                              "pct": 0})
                    dresp = _req.get(zip_asset["browser_download_url"], stream=True, timeout=600)
                    dresp.raise_for_status()

                    downloaded = 0
                    with open(zip_dest, "wb") as fh:
                        for chunk in dresp.iter_content(chunk_size=1 << 18):
                            if chunk:
                                fh.write(chunk)
                                downloaded += len(chunk)
                                if total_bytes:
                                    pct = downloaded * 100 // total_bytes
                                    dl_mb = downloaded / (1 << 20)
                                    ev_q.put({
                                        "type": "progress",
                                        "label": (f"Downloading {part}… {pct}%  "
                                                  f"({dl_mb:.1f} / {total_mb:.0f} MB)"),
                                        "pct": pct,
                                    })

                    ev_q.put({"type": "progress",
                              "label": f"Verifying {part} checksum…", "pct": None})
                    sha = hashlib.sha256()
                    with open(zip_dest, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            sha.update(chunk)
                    expected_sha = manifest.get("sha256", "")
                    if sha.hexdigest() != expected_sha:
                        zip_dest.unlink(missing_ok=True)
                        ev_q.put({"type": "error", "error": "sha256_mismatch",
                                  "message": f"SHA256 mismatch for {part} — download may be "
                                             "corrupt. Please try again."})
                        return

                    with open(manifest_dest, "w", encoding="utf-8") as fh:
                        _json.dump(manifest, fh, indent=2)

                    ev_q.put({"type": "progress",
                              "label": f"Extracting {part} into site data…", "pct": None})
                    extraction = _restore_sitedata_zip(zip_dest)

                    # Cheap local signal for /api/onboarding/status — avoids an
                    # os.scandir() over up to ~94k files on every status poll.
                    SITE_DIR.mkdir(parents=True, exist_ok=True)
                    marker_path = SITE_DIR / f".sitedata_{part}_manifest.json"
                    with open(marker_path, "w", encoding="utf-8") as fh:
                        _json.dump(manifest, fh, indent=2)

                    summary["parts"][part] = {
                        "restored": len(extraction["restored"]),
                        "conflicts": len(extraction["conflicts"]),
                        "manifest": manifest,
                    }

                ev_q.put({"type": "done", "summary": summary})

            except Exception as exc:
                ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

        def _stream():
            from backend import activity as _activity

            with _activity.track("sitedata_install", screen="/setup") as _job:
                while True:
                    try:
                        ev = ev_q.get(timeout=680)
                    except queue.Empty:
                        ev = {"type": "error", "error": "timeout",
                              "message": "Install timed out after 680 s."}
                    if ev.get("type") == "progress":
                        _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                    yield f"data: {_json.dumps(ev)}\n\n"
                    if ev.get("type") in ("done", "error"):
                        break

        return Response(
            stream_with_context(_stream()),
            content_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    def _sitedata_local_state() -> "tuple[bool, int]":
        """Cheap local read of installed site-data extent, for onboarding/status.

        Prefers the ``.sitedata_<part>_manifest.json`` marker written by
        ``sitedata_github_install`` (a single small JSON read) over scanning
        the filesystem. Falls back to a directory-existence check (core) and
        an ``os.scandir`` count (files — ~94k entries, ≈1s, acceptable per
        FABLE_ONBOARDING_SYNC.md §4) when a marker is missing, e.g. site data
        restored via the legacy ``/api/package/restore`` local-zip path
        rather than the GitHub installer.

        Returns:
            (sitedata_core_present, sitedata_files_count).
        """
        core_marker = SITE_DIR / ".sitedata_core_manifest.json"
        if core_marker.exists():
            core_present = True
        else:
            core_dir = SITE_DIR / "detail"
            core_present = core_dir.exists() and any(core_dir.iterdir())

        files_marker = SITE_DIR / ".sitedata_files_manifest.json"
        files_count = 0
        if files_marker.exists():
            try:
                files_count = int(
                    json.loads(files_marker.read_text(encoding="utf-8")).get("file_count", 0)
                )
            except Exception:
                files_count = 0
        elif SITE_FILES_DIR.exists():
            files_count = sum(1 for _ in os.scandir(SITE_FILES_DIR))

        return core_present, files_count

    @app.route("/api/onboarding/status", methods=["GET"])
    def onboarding_status() -> Response:
        """Report first-run onboarding progress for the wizard / Home checklist.

        See FABLE_ONBOARDING_SYNC.md §4. Cheap only: COUNT queries, a
        ``meta`` read, and directory existence/marker checks (see
        ``_sitedata_local_state``) — no full table scans.

        Returns:
            JSON: {entries_count, master_version, sitedata_core_present,
            sitedata_files_count, mounts_configured, collection_count,
            complete}. ``complete`` is true iff entries are present AND
            ``master_version`` is stamped AND at least one collection mount
            is configured.
        """
        try:
            with database.get_connection() as conn:
                entries_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                collection_count = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
            master_version = database.get_meta("master_version")
            sitedata_core_present, sitedata_files_count = _sitedata_local_state()
            mounts_configured = bool(database.get_collection_mounts())

            complete = bool(entries_count) and bool(master_version) and mounts_configured

            return jsonify({
                "entries_count": entries_count,
                "master_version": master_version,
                "sitedata_core_present": sitedata_core_present,
                "sitedata_files_count": sitedata_files_count,
                "mounts_configured": mounts_configured,
                "collection_count": collection_count,
                "complete": complete,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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
            if not bobdylan_scraper.start_update_async(force=force):
                return jsonify({"ok": False, "error": "Already running"}), 409
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
            if not bobdylan_scraper.start_discover_async():
                return jsonify({"ok": False, "error": "Already running"}), 409
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
            if not bobdylan_scraper.start_scrape_async(force=force):
                return jsonify({"ok": False, "error": "Already running"}), 409
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
            if not setlistfm_mod.start_update_async(force=force, api_key=api_key):
                return jsonify({"ok": False, "error": "Already running"}), 409
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

    # ── Olof Björner (Still On The Road + Yearly Chronicles) ──────────────────
    # olof_* tables are local-only (not in MASTER_TABLES); every route here
    # degrades to empty lists/counts rather than 404ing when they're empty.

    @app.route("/api/olof/date/<date_str>", methods=["GET"])
    def olof_date(date_str: str):
        """Return everything Olof's corpus knows about a show date.

        Returns:
            JSON: {date_str, events: [olof_events row + songs: [...]],
                   chronicle: [olof_chronicle rows], new_tapes: [olof_new_tapes
                   rows]}. Lists are empty (not 404) when nothing matches.
        """
        try:
            return jsonify(database.get_olof_date(date_str))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/olof/event/<int:event_id>", methods=["GET"])
    def olof_event(event_id: int):
        """Return one olof_events row (all columns) plus its ordered songs.

        Returns:
            JSON: olof_events columns + {songs: [...]}. 404 if event_id is
            unknown.
        """
        try:
            event = database.get_olof_event(event_id)
            if event is None:
                return jsonify({"error": "event not found"}), 404
            return jsonify(event)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/olof/chronicle/<int:year>", methods=["GET"])
    def olof_chronicle_year(year: int):
        """Return one chronicle year's entries in calendar order.

        Returns:
            JSON: {year, entries: [olof_chronicle rows]}. Empty list if the
            year has no chronicle page parsed.
        """
        try:
            return jsonify({"year": year, "entries": database.get_olof_chronicle_year(year)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/olof/status", methods=["GET"])
    def olof_status():
        """Return per-table Olof row counts + max DSN year, for GUI gating.

        Returns:
            JSON: {pages, events, songs, chronicle_rows, new_tapes,
                   chronicle_years, max_dsn_year}
        """
        try:
            return jsonify(database.get_olof_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/olof/bobtalk_search", methods=["GET"])
    def olof_bobtalk_search():
        """Search olof_events.bobtalk/notes for "Bob said X — which night?" lookups.

        Query params:
            q (str, required) — search text, min 2 chars after strip.
            limit (int, optional, default 50, capped at 200).

        Returns:
            JSON: {q, hits: [{event_id, date_str, venue, city, country,
                   event_type, concert_no_net, field, snippet}]}.
            400 if q is missing or shorter than 2 chars.
        """
        q = (request.args.get("q") or "").strip()
        if len(q) < 2:
            return jsonify({"error": "q must be at least 2 characters"}), 400
        try:
            limit = min(int(request.args.get("limit", 50)), 200)
        except ValueError:
            limit = 50
        try:
            hits = database.get_olof_bobtalk_search(q, limit=limit)
            return jsonify({"q": q, "hits": hits})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/olof/compare", methods=["POST"])
    def olof_compare():
        """Compare a folder's track titles against Olof's setlist for a date.

        Body JSON:
            date_str (str, required) — ISO yyyy-mm-dd.
            titles (list[str], optional) — track titles in any order.
            lb_number (int, optional) — resolves titles server-side from the
                catalog entry's stored ``entries.setlist`` tracklist text.
                Used only when ``titles`` is omitted/empty.

        Returns:
            JSON: {date_str, olof_event_id, olof_setlist: [{position,
                   song_title}], matches: [{input_title, matched_position,
                   matched_title}], olof_missing: [song_title, ...],
                   match_pct, recording_info, recording_kind, recording_mins}
            400 if neither titles nor a resolvable lb_number is given.
        """
        try:
            data = request.get_json() or {}
            date_str = (data.get("date_str") or "").strip()
            if not date_str:
                return jsonify({"error": "date_str required"}), 400
            titles = data.get("titles") or []
            if not titles and data.get("lb_number") is not None:
                titles = database.resolve_lb_number_titles(int(data["lb_number"])) or []
            if not titles:
                return jsonify({"error": "titles or a resolvable lb_number required"}), 400
            return jsonify(database.compare_olof_setlist(date_str, titles))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fingerprint/scan", methods=["POST"])
    def fingerprint_scan():
        """TODO-225: (re)scan candidate entries and rebuild the suggestion queue.

        Candidates are entries with no clean parseable date or a location in
        the TODO-221 skipped_not_concert bucket — see
        backend/setlist_fingerprint.py:_find_candidate_entries. Wholesale-
        replaces setlist_fingerprint_suggestions; not curator-gated, like
        POST /api/derived/recompute — it only rebuilds a local-only derived
        suggestion table, no master data or curator decision involved.

        Body JSON (optional): {limit: int} — cap on candidates scanned.

        Returns:
            JSON: {candidates_scanned, candidates_matched,
                   suggestions_written, skipped_no_titles}
        """
        try:
            data = request.get_json(silent=True) or {}
            limit = data.get("limit")
            stats = _setlist_fingerprint.run_fingerprint_scan(limit=int(limit) if limit else None)
            return jsonify(stats)
        except Exception as e:
            _log.exception("fingerprint_scan failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fingerprint/suggestions", methods=["GET"])
    def fingerprint_suggestions():
        """List the setlist-fingerprint curator review queue.

        Query param ``status`` (optional): 'pending' (default), 'dismissed',
        or 'all'.

        Returns:
            JSON: {suggestions: [...]} — see
            backend.setlist_fingerprint.get_suggestions for the row shape.
        """
        try:
            status = request.args.get("status", "pending")
            return jsonify({"suggestions": _setlist_fingerprint.get_suggestions(status=status)})
        except Exception as e:
            _log.exception("fingerprint_suggestions failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fingerprint/suggestions/dismiss", methods=["POST"])
    def fingerprint_dismiss():
        """Curator-only. Dismiss one suggestion; sticky across rescans.

        Body JSON: {lb_number: int, event_id: int}

        Returns:
            JSON: {ok}. 404 if no matching row existed.
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            data = request.get_json(force=True)
            lb_number = int(data["lb_number"])
            event_id = int(data["event_id"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "lb_number and event_id are required"}), 400
        try:
            found = _setlist_fingerprint.dismiss_suggestion(lb_number, event_id)
            if not found:
                return jsonify({"error": "not_found"}), 404
            return jsonify({"ok": True})
        except Exception as e:
            _log.exception("fingerprint_dismiss failed")
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
                "SELECT mc.lb_number, e.date_str, e.location, e.status "
                "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number "
                "ORDER BY mc.lb_number"
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
                        "SELECT mc.lb_number, e.date_str, e.location, e.status "
                        "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number "
                        "WHERE mc.lb_number = ? "
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

    @app.route("/api/trading/friends/<int:friend_id>/entries", methods=["GET"])
    def trading_friend_entries(friend_id):
        """Paginated raw entries of one friend's collection.

        Args:
            friend_id: Row ID in friend_collections.

        Query: q (substring of date/location/LB#), limit (default 100, max 500), offset.

        Returns:
            JSON: {friend_id, friend_name, total, offset, limit, entries}
        """
        try:
            conn = database.get_connection()
            row = conn.execute(
                "SELECT friend_name FROM friend_collections WHERE id = ?", (friend_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "friend not found"}), 404
            limit = max(1, min(request.args.get("limit", 100, type=int), 500))
            offset = max(0, request.args.get("offset", 0, type=int))
            q = (request.args.get("q") or "").strip()
            where, params = "friend_id = ?", [friend_id]
            if q:
                where += " AND (CAST(lb_number AS TEXT) LIKE ? OR date_str LIKE ? OR location LIKE ?)"
                like = f"%{q}%"
                params += [like, like, like]
            total = conn.execute(
                f"SELECT COUNT(*) FROM friend_collection_entries WHERE {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT lb_number, date_str, location, lb_status FROM friend_collection_entries "
                f"WHERE {where} ORDER BY lb_number LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return jsonify({
                "friend_id": friend_id, "friend_name": row[0], "total": total,
                "offset": offset, "limit": limit,
                "entries": [
                    {"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]}
                    for r in rows
                ],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trading/batch-compare", methods=["POST"])
    def trading_batch_compare():
        """Compare the user's collection against N friends at once (friends x shows).

        Request JSON: {friend_ids: [int], mode?: "want"|"offer"|"all" (default "all"),
        q?: str, limit?: int (default 100, max 500), offset?: int}

        A show is a "want" row when you lack it and some selected friend has it, and an
        "offer" row when you have it and some selected friend lacks it. For each row,
        best_friend_id is the candidate friend (has it / lacks it) with the largest
        two-way trade potential min(they_have_you_dont, you_have_they_dont), ties broken
        by total overlap potential then name.

        Returns:
            JSON: {friends: [{id, friend_name, they_have_you_dont, you_have_they_dont,
            both_have, potential}], total, offset, limit, rows: [{lb_number, date_str,
            location, lb_status, you_have, kind, cells: {friend_id: bool},
            best_friend_id}]}
        """
        try:
            data = request.get_json(force=True, silent=True) or {}
            ids = []
            for v in data.get("friend_ids") or []:
                try:
                    if int(v) not in ids:
                        ids.append(int(v))
                except (TypeError, ValueError):
                    return jsonify({"error": "friend_ids must be integers"}), 400
            if not ids:
                return jsonify({"error": "friend_ids required"}), 400
            if len(ids) > 50:
                return jsonify({"error": "too many friends (max 50)"}), 400
            mode = data.get("mode") or "all"
            if mode not in ("want", "offer", "all"):
                return jsonify({"error": "invalid mode"}), 400
            limit = max(1, min(int(data.get("limit") or 100), 500))
            offset = max(0, int(data.get("offset") or 0))
            q = str(data.get("q") or "").strip().lower()

            conn = database.get_connection()
            ph = ",".join("?" * len(ids))
            frows = conn.execute(
                f"SELECT id, friend_name FROM friend_collections WHERE id IN ({ph})", ids
            ).fetchall()
            names = {r[0]: r[1] for r in frows}
            ids = [i for i in ids if i in names]
            if not ids:
                return jsonify({"error": "friends not found"}), 404

            mine = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
                "SELECT mc.lb_number, e.date_str, e.location, e.status "
                "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number"
            ).fetchall()}
            theirs: dict[int, set[int]] = {i: set() for i in ids}
            meta: dict[int, tuple] = {}
            ph = ",".join("?" * len(ids))
            for fid, lb, d, loc, st in conn.execute(
                "SELECT friend_id, lb_number, date_str, location, lb_status "
                f"FROM friend_collection_entries WHERE friend_id IN ({ph})", ids
            ):
                theirs[fid].add(lb)
                meta.setdefault(lb, (d, loc, st))

            mine_set = set(mine)
            summary = {}
            for i in ids:
                want = len(theirs[i] - mine_set)
                offer = len(mine_set - theirs[i])
                summary[i] = {
                    "id": i, "friend_name": names[i], "they_have_you_dont": want,
                    "you_have_they_dont": offer, "both_have": len(mine_set & theirs[i]),
                    "potential": min(want, offer),
                }

            def rank(i: int) -> tuple:
                s = summary[i]
                return (-s["potential"], -(s["they_have_you_dont"] + s["you_have_they_dont"]),
                        names[i].lower())

            all_lbs = mine_set.union(*theirs.values())
            out = []
            for lb in sorted(all_lbs):
                have = lb in mine_set
                holders = [i for i in ids if lb in theirs[i]]
                if not have and holders:
                    kind, cands = "want", holders
                elif have and len(holders) < len(ids):
                    kind, cands = "offer", [i for i in ids if lb not in theirs[i]]
                else:
                    continue
                if mode != "all" and kind != mode:
                    continue
                d, loc, st = mine[lb] if have else meta.get(lb, (None, None, None))
                if q and q not in f"{lb} {d or ''} {loc or ''}".lower():
                    continue
                out.append({
                    "lb_number": lb, "date_str": d, "location": loc, "lb_status": st,
                    "you_have": have, "kind": kind,
                    "cells": {str(i): lb in theirs[i] for i in ids},
                    "best_friend_id": min(cands, key=rank),
                })
            return jsonify({
                "friends": [summary[i] for i in ids], "total": len(out),
                "offset": offset, "limit": limit, "rows": out[offset:offset + limit],
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


if __name__ == "__main__":
    import sys

    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
