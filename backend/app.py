import base64
import gzip as gzip_module
import json
import logging
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
    stream_with_context,
)
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from backend import archive_org as _archive_org
from backend import (
    bobdylan_scraper,
    checksum_utils,
    importer,
    scheduler,
    scraper,
    sharing,
    site_crawler,
)
from backend import db as database
from backend import dossier as _dossier
from backend import gap_analysis as _gap_analysis
from backend import setlist_fingerprint as _setlist_fingerprint
from backend import setlistfm as setlistfm_mod
from backend import song_index as _song_index
from backend import timeline as _timeline
from backend.folder_lb import (
    _find_lbdir_in_folder,
)
from backend.github_upload import _github_upload_asset
from backend.lbdir_status import _lbdir_verdict
from backend.paths import (
    DATA_DIR,
    SITE_DIR,
    SITE_FILES_DIR,
    find_lbdir_attachment,
)
from backend.routes import _state as _route_state

_log = logging.getLogger(__name__)


# ── Async pipeline job (TODO-205 Phase 2 / P2) ─────────────────────────────────
_PIPELINE_JOB_LOCK = threading.Lock()
_PIPELINE_JOB: dict = {
    "running": False,
    "folders_total": 0,
    "folders_done": 0,
    "in_progress": [],   # list of folder paths currently processing
    "results": {},       # {folder_path: PipelineRow}
    "errors": [],        # [{folder, message}]
    "steps": [],         # requested steps for this run
    "started_at": None,
    "cancelled": False,
}
_PIPELINE_CANCEL_EVENT = threading.Event()


def get_pipeline_run_status() -> dict:
    """Return a snapshot of the async pipeline job status.

    Module-level helper (TODO-262) for ``backend/activity.py`` — mirrors the
    ``/api/pipeline/run/status`` route body.

    Returns:
        Dict copy of ``_PIPELINE_JOB`` with its nested containers copied too.
    """
    with _PIPELINE_JOB_LOCK:
        snapshot = dict(_PIPELINE_JOB)
        snapshot["results"] = dict(_PIPELINE_JOB["results"])
        snapshot["in_progress"] = list(_PIPELINE_JOB["in_progress"])
        snapshot["errors"] = list(_PIPELINE_JOB["errors"])
    return snapshot


# Blocked file-step codes that need human configuration (a missing recording
# date or an unroutable year) — these escalate a folder to "attn". Every other
# blocked code (mount_offline/dest_exists/db_error/unknown) is transient and
# self-heals on a live re-resolve, so it falls through to the done/shelf path
# (P8, TODO-205 Ph.6).
_TRUE_ATTN_BLOCK_CODES = {"no_date", "no_route"}


def compute_pipeline_severity(
    verify: dict,
    lookup: dict,
    lbdir: dict,
    rename: dict,
    file_status: str,
    file_error_code: "str | None",
    lb_number: "int | None",
) -> str:
    """Compute a pipeline row's severity bucket from its per-step verdicts.

    Pure function extracted from ``_pipeline_process_folder`` (TODO-211) so it is
    directly unit-testable and reusable for warm-start bucket reconstruction
    (TODO-205 Phase 7 ``/api/pipeline/state``) without re-running the pipeline.

    Args:
        verify: Verify step verdict dict (reads ``status``).
        lookup: Lookup step verdict dict (reads ``status``).
        lbdir: LBDIR step verdict dict (reads ``status`` and optional
            ``pending_fetch``).
        rename: Rename step verdict dict (reads ``status`` and optional
            ``label``).
        file_status: The file step's status (``ok``/``warn``/``blocked``/
            ``mute``/…).
        file_error_code: The file step's ``error_code`` when blocked, else None.
        lb_number: The resolved LB number, or None.

    Returns:
        One of ``"attn"``, ``"ready"``, or ``"done"``.
    """
    statuses = [verify["status"], lookup["status"], lbdir["status"], rename["status"]]
    if "bad" in statuses or (
        file_status == "blocked" and file_error_code in _TRUE_ATTN_BLOCK_CODES
    ):
        return "attn"
    if rename.get("label") == "Proposed":
        return "ready"
    if lb_number and (
        rename["status"] == "mute"
        or (lbdir["status"] == "mute" and not lbdir.get("pending_fetch"))
    ):
        # Lookup resolved but downstream steps weren't run yet — not done.
        # A pending_fetch lbdir is exempt: it's parked on a background prefetch,
        # not un-run, so it must fall through to the all-ok/mute → done rule.
        return "attn"
    # A folder is only "done" (in collection) once Lookup has actually
    # identified it: my_collection is keyed by LB#, so no resolved LB# means it
    # was never filed. Without this guard a partial run whose only non-mute step
    # is verify=ok (a re-verify or generate-missing pass, lookup/lbdir/rename all
    # still mute) reads as all-ok/mute and is wrongly promoted to "In collection".
    if lb_number and all(s in ("ok", "mute") for s in statuses) and "ok" in statuses:
        return "done"
    return "attn"


# ── P3 background LBDIR prefetch (TODO-205 Phase 5) ───────────────────────────
_LBDIR_PREFETCH_LOCK = threading.Lock()
_LBDIR_PREFETCH_INFLIGHT: set[int] = set()      # LB numbers currently being fetched
_LBDIR_PREFETCH_POOL: "ThreadPoolExecutor | None" = None   # lazy, max_workers=2


def _lbdir_prefetch_worker(lb_number: int) -> None:
    """Fetch an LB's lbdir attachment in the background (best-effort).

    Mirrors the inline lbdir retrieval in ``_pipeline_process_folder``: scrape the
    LB and, if its lbdir attachment is still missing afterwards, resolve the
    canonical alias and scrape that too. All failures are swallowed — prefetch is
    advisory; the lbdir step's synchronous fallback still covers a missed fetch.

    Args:
        lb_number: The LB number to prefetch the lbdir attachment for.
    """
    try:
        scraper.scrape_entry(lb_number, force=False, download_files=True)
        if find_lbdir_attachment(lb_number) is None:
            canonicals = database.resolve_aliases([lb_number])
            canonical = (
                canonicals[0]
                if canonicals and canonicals[0] != lb_number else None
            )
            if canonical:
                scraper.scrape_entry(canonical, force=False, download_files=True)
    except Exception as exc:
        _log.warning("lbdir prefetch for LB-%05d failed: %s", lb_number, exc)
    finally:
        with _LBDIR_PREFETCH_LOCK:
            _LBDIR_PREFETCH_INFLIGHT.discard(lb_number)


def _submit_lbdir_prefetch(lb_number: int) -> bool:
    """Kick off a best-effort background fetch of an LB's lbdir attachment.

    The lbdir stage is the slowest, least-reliable link (a live
    ``scraper.scrape_entry``). Prefetching it the moment Lookup resolves an LB
    keeps that scrape off the folder's stage chain. Dedup is by LB number, not
    folder: many folders can resolve to the same LB and only one fetch should
    run. ``max_workers=2`` bounds site concurrency; ``scrape_entry``'s own
    politeness (retry backoff, 429 sleep) is reused, so no new rate-limit logic.

    Args:
        lb_number: The canonical or alias LB number to prefetch.

    Returns:
        True if the LB is now (or already was) being fetched; False if the
        submission failed.
    """
    global _LBDIR_PREFETCH_POOL
    with _LBDIR_PREFETCH_LOCK:
        if lb_number in _LBDIR_PREFETCH_INFLIGHT:
            return True  # already inflight — dedupe concurrent folders on one LB
        _LBDIR_PREFETCH_INFLIGHT.add(lb_number)
        try:
            if _LBDIR_PREFETCH_POOL is None:
                _LBDIR_PREFETCH_POOL = ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="lbdir-fetch"
                )
            _LBDIR_PREFETCH_POOL.submit(_lbdir_prefetch_worker, lb_number)
        except Exception:
            _LBDIR_PREFETCH_INFLIGHT.discard(lb_number)
            return False
    return True


# ── Restart callback (set by run_backend.py so only the Flask server restarts) ─
_restart_callback = None


def set_restart_callback(cb) -> None:
    """Register a function the backend launcher calls to restart the Flask server in-process.

    When set, admin_restart invokes this instead of os.execv so the GUI is not affected.
    If not set (standalone/Windows), os.execv restarts the whole process as before.
    """
    global _restart_callback
    _restart_callback = cb




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

    # ── Curated "best of" lists (TODO-181 remainder + FABLE_UNIFIED_RANKING §6) ──

    @app.route("/api/curated_lists", methods=["GET"])
    def curated_lists_list() -> Response:
        """List curated lists with entry counts (carbonbit, 10haaf, ...)."""
        try:
            return jsonify(database.get_curated_lists())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/curated_lists", methods=["POST"])
    def curated_lists_create() -> Response:
        """Curator-only. Create (or fetch, if it already exists) a curated list.

        Body: {name, label?, source?}
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            body = request.get_json(force=True) or {}
            name = body.get("name")
            if not isinstance(name, str) or not name.strip():
                return jsonify({"error": "name is required"}), 400
            list_id = database.get_or_create_curated_list(
                name.strip(), body.get("label", ""), body.get("source", "")
            )
            return jsonify({"ok": True, "id": list_id, "name": name.strip()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/curated_lists/<string:name>", methods=["DELETE"])
    def curated_lists_delete(name: str) -> Response:
        """Curator-only. Delete a curated list and all its entries."""
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            deleted = database.delete_curated_list(name)
            if not deleted:
                return jsonify({"error": "not_found"}), 404
            return jsonify({"ok": True, "name": name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Show picks lookup (FABLE_UNIFIED_RANKING §6) ─────────────────────────────

    @app.route("/api/picks/for/<int:lb_number>", methods=["GET"])
    def picks_for_lb(lb_number: int) -> Response:
        """Return this LB's show-pick rank/score/evidence, for DetailPanel's
        EvidenceList (per SPEC_INTEGRATION_NOTES.md F3). 204 when show_picks
        has no row for this LB yet (pre-recompute, or no usable date).
        """
        try:
            pick = database.get_show_pick_for_lb(lb_number)
            if pick is None:
                return "", 204
            return jsonify(pick)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/picks", methods=["GET"])
    def picks_for_date() -> Response:
        """Return all show picks for one ISO concert date, rank-ordered.

        Query param ``date`` (``YYYY-MM-DD``) is required; missing or
        malformed values are a 400. No computed picks for that date is a
        normal 200 with an empty list.
        """
        date_param = request.args.get("date", "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_param):
            return jsonify({"error": "date query param (YYYY-MM-DD) is required"}), 400
        from datetime import date as _date
        try:
            _date.fromisoformat(date_param)
        except ValueError:
            return jsonify({"error": "invalid date"}), 400
        try:
            picks = database.get_picks_for_date(date_param)
            return jsonify(picks)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/picks/tonight", methods=["GET"])
    def picks_tonight() -> Response:
        """"This night in Dylan history" (LISTENING spec §9): rank-1 show
        picks whose concert date falls on today's calendar day (MM-DD)
        across all years, best-scored first. Accepts ``?mmdd=MM-DD`` to
        override "today" for testing. No matches is a normal 200 with an
        empty candidates list.
        """
        mmdd = request.args.get("mmdd", "")
        if mmdd and not re.match(r"^\d{2}-\d{2}$", mmdd):
            return jsonify({"error": "mmdd must be MM-DD"}), 400
        if not mmdd:
            from datetime import date as _date
            mmdd = _date.today().strftime("%m-%d")
        try:
            candidates = database.get_tonight_picks(mmdd)
            return jsonify({"mmdd": mmdd, "candidates": candidates})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Song index (LISTENING spec §3, TODO-230 — song-centric catalog view) ────

    @app.route("/api/songs", methods=["GET"])
    def songs_list() -> Response:
        """List distinct songs from song_performances, most-performed first.

        Query param ``q`` (optional): substring filter against the canonical
        display spelling or the normalised key. No ``q`` returns every song.
        """
        try:
            songs = _song_index.get_songs(q=request.args.get("q") or None)
            return jsonify({"songs": songs})
        except Exception as e:
            _log.exception("songs_list failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/songs/performances", methods=["GET"])
    def song_performances() -> Response:
        """Every performance of one song, joined to venue + circulating recordings.

        Query param ``song`` (required, the normalised ``song_norm`` key
        from ``GET /api/songs``). 404 if unknown.
        """
        song_norm = request.args.get("song", "")
        if not song_norm:
            return jsonify({"error": "song query param is required"}), 400
        try:
            result = _song_index.get_song_performances(song_norm)
            if result is None:
                return jsonify({"error": "not_found"}), 404
            return jsonify(result)
        except Exception as e:
            _log.exception("song_performances failed for song_norm=%r", song_norm)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/songs/alias", methods=["POST"])
    def songs_alias() -> Response:
        """Curator-only. Map an alias spelling to a canonical display spelling.

        Body: {alias, canonical}. Normalises the alias, upserts song_canonical
        with source='curator' (sticky against future auto-seeding), then
        re-runs the song_performances recompute so the new spelling is live
        immediately. Returns the recompute stats dict.
        """
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        try:
            body = request.get_json(silent=True) or {}
            stats = _song_index.upsert_alias(body.get("alias", ""), body.get("canonical", ""))
            return jsonify({"ok": True, "stats": stats})
        except ValueError as exc:
            return jsonify({"error": "bad_request", "message": str(exc)}), 400
        except Exception as e:
            _log.exception("songs_alias failed")
            return jsonify({"error": str(e)}), 500

    # ── Show detail (Library performance lens — backend/gap_analysis.py) ───────
    # Read-only: no writes, no derived table. Degrades to an empty/
    # available:false response when olof_events is absent. This route is a
    # rename/survivor of the standalone Gaps screen's four routes, retired
    # once its coverage grid/detail became a Library performance-lens view
    # (uncirculated/upcoming rows, Coverage facet) — this drill-down is what
    # DetailPanel.tsx now calls for those rows.

    @app.route("/api/shows/<date_iso>/olof", methods=["GET"])
    def show_olof_detail(date_iso: str) -> Response:
        """Drill-down: olof event rows, entries, and family data for one date."""
        try:
            return jsonify(_gap_analysis.get_date_detail(date_iso))
        except Exception as e:
            _log.exception("show_olof_detail failed for date_iso=%r", date_iso)
            return jsonify({"error": str(e)}), 500

    # ── Timeline navigator (instructions/FABLE_TIMELINE.md) ─────────────────────
    # Read-only: no writes, no derived table. All three routes degrade to an
    # empty/available:false response when olof_events is absent.

    @app.route("/api/timeline/summary", methods=["GET"])
    def timeline_summary() -> Response:
        """Decade-by-decade summary (night/circulating counts, best grade)."""
        try:
            return jsonify(_timeline.get_summary())
        except Exception as e:
            _log.exception("timeline_summary failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/timeline/decade/<int:decade>", methods=["GET"])
    def timeline_decade(decade: int) -> Response:
        """Tour-by-tour breakdown for one decade."""
        try:
            return jsonify(_timeline.get_decade_detail(decade))
        except Exception as e:
            _log.exception("timeline_decade failed for decade=%r", decade)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/timeline/tour", methods=["GET"])
    def timeline_tour() -> Response:
        """Night-by-night breakdown for one tour, scoped by decade.

        Query params: name (required, exact olof_events.tour_name), decade
        (required, int -- the decade of the tour's earliest show).
        """
        try:
            name = request.args.get("name", "")
            decade = request.args.get("decade", type=int)
            return jsonify(_timeline.get_tour_detail(name, decade))
        except Exception as e:
            _log.exception(
                "timeline_tour failed for name=%r decade=%r",
                request.args.get("name"), request.args.get("decade"),
            )
            return jsonify({"error": str(e)}), 500

    # ── Show dossier (TODO-257, instructions/FABLE_SHOW_DOSSIER.md) ────────────

    @app.route("/api/dossier", methods=["GET"])
    def dossier_json() -> Response:
        """Assemble the show dossier for one date (spec D1).

        Query params: date (required, YYYY-MM-DD), location (disambiguates a
        multi-venue date), show (picks one show of a same-venue two-show day,
        e.g. 'afternoon'/'evening' -- TODO-345), channel ('public' default / 'full').
        Returns the dossier JSON, or HTTP 300 with {ambiguous, candidates}
        when location or show is required but not given.
        """
        try:
            date_iso = request.args.get("date", "")
            location = request.args.get("location") or None
            show = request.args.get("show") or None
            channel = request.args.get("channel", "public")
            result = _dossier.build_dossier(date_iso, location=location, channel=channel,
                                            show=show)
            if result.get("ambiguous"):
                return jsonify(result), 300
            return jsonify(result)
        except Exception as e:
            _log.exception("dossier_json failed for date=%r", request.args.get("date"))
            return jsonify({"error": str(e)}), 500

    def _dossier_pick_href(pick: dict) -> str:
        """Same-route query string that re-requests the dossier for one candidate show."""
        from urllib.parse import urlencode

        q = {k: v for k, v in request.args.items() if k not in ("location", "show")}
        if pick.get("location"):
            q["location"] = pick["location"]
        if pick.get("show"):
            q["show"] = pick["show"]
        return "?" + urlencode(q)

    @app.route("/api/dossier/html", methods=["GET"])
    def dossier_html() -> Response:
        """Render the dossier as a self-contained, print-first HTML document (spec D3).

        Query params: date, location?, show?, channel? (as /api/dossier), plus
        sections= (comma list of 'context'/'setlist' to include, default both)
        and local_analysis= ('0' hides pick/quality/curated/family-confidence
        and the recommendation, default shown). chooser=1 (the in-app viewer)
        answers an ambiguous date with an HTML page linking each candidate show
        instead of JSON.
        Returns an HTML attachment, or HTTP 300 JSON (or chooser HTML) when
        location or show is required.
        """
        try:
            date_iso = request.args.get("date", "")
            location = request.args.get("location") or None
            show = request.args.get("show") or None
            channel = request.args.get("channel", "public")
            # F8: the in-app viewer (timeline screen, embedded iframe) passes inline=1
            # (Content-Disposition, unrelated to run-links) and, by default, also gets
            # same-route ?date= sibling-run links since it's the only current inline=1
            # caller. tools.dossier_golden.export_html sends inline=1 too (so the test
            # client doesn't get an attachment back) but sets link_mode=none explicitly
            # -- it has no filesystem for /api/dossier/html?date= links to resolve to,
            # and does its own rewrite pass for the dates it actually exports.
            inline = request.args.get("inline") in ("1", "true", "True")
            link_mode = request.args.get("link_mode") or ("inline" if inline else "none")
            result = _dossier.build_dossier(date_iso, location=location, channel=channel,
                                            show=show, link_mode=link_mode)
            if result.get("ambiguous"):
                if request.args.get("chooser") in ("1", "true", "True"):
                    picks = [dict(c, href=_dossier_pick_href(c),
                                  label=c.get("label") or c.get("location") or "")
                             for c in result.get("candidates") or []]
                    html = render_template("dossier_chooser.html", date_iso=date_iso,
                                           picks=picks)
                    return Response(html, status=300, mimetype="text/html")
                return jsonify(result), 300
            qc = result.get("qc") or {}
            if qc.get("refused"):
                return jsonify({"refused": True, "reasons": qc.get("reasons", [])}), 422

            sections_param = request.args.get("sections")
            sections = (
                {s.strip() for s in sections_param.split(",") if s.strip()}
                if sections_param else None
            )
            local_analysis_on = request.args.get("local_analysis", "1") not in ("0", "false", "False")
            view = _dossier.filter_dossier_sections(
                result, sections=sections, local_analysis=local_analysis_on
            )
            if result.get("show_options"):
                view["show_links"] = [dict(o, href=_dossier_pick_href(o))
                                      for o in result["show_options"]]
            # C33: the exact identity this export was built with (echoed back, not
            # re-derived), so tools.dossier_verify_export can rebuild an identical
            # dossier from the exported file alone and diff it against the live DB.
            identity = {"date_iso": date_iso, "location": location, "show": show,
                       "channel": channel}
            html = render_template("dossier.html", d=view, identity=identity)
            from backend.dossier_qc import lint_data_lb, lint_l1

            for violation in lint_l1(html) + lint_data_lb(html):
                _log.warning("dossier_html lint violation for date=%s: %s",
                             date_iso, violation)
            # Default: download as an attachment (the export flow). The in-app
            # dossier viewer (timeline screen) embeds this route in an iframe,
            # where an attachment disposition renders blank -- it passes
            # inline=1 to be served inline instead. The HTML export flow reads
            # the body via fetch()+blob and never depends on this header, so the
            # opt-in is backward-compatible.
            inline = request.args.get("inline") in ("1", "true", "True")
            headers = (
                {}
                if inline
                else {"Content-Disposition": f"attachment; filename=dossier-{date_iso}.html"}
            )
            return Response(html, mimetype="text/html", headers=headers)
        except Exception as e:
            _log.exception("dossier_html failed for date=%r", request.args.get("date"))
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dossier/bbcode", methods=["GET"])
    def dossier_bbcode() -> Response:
        """Compact BBcode digest of the dossier for forum posts (spec D5).

        Same query params as /api/dossier/html. Returns {text} — shares B1's
        JSON via the same filtered view, so it can't drift from the HTML twin.
        """
        try:
            date_iso = request.args.get("date", "")
            location = request.args.get("location") or None
            show = request.args.get("show") or None
            channel = request.args.get("channel", "public")
            result = _dossier.build_dossier(date_iso, location=location, channel=channel,
                                            show=show)
            if result.get("ambiguous"):
                return jsonify(result), 300
            qc = result.get("qc") or {}
            if qc.get("refused"):
                return jsonify({"refused": True, "reasons": qc.get("reasons", [])}), 422

            sections_param = request.args.get("sections")
            sections = (
                {s.strip() for s in sections_param.split(",") if s.strip()}
                if sections_param else None
            )
            local_analysis_on = request.args.get("local_analysis", "1") not in ("0", "false", "False")
            view = _dossier.filter_dossier_sections(
                result, sections=sections, local_analysis=local_analysis_on
            )
            return jsonify({"text": _dossier.render_bbcode(view)})
        except Exception as e:
            _log.exception("dossier_bbcode failed for date=%r", request.args.get("date"))
            return jsonify({"error": str(e)}), 500

    def _find_master_release(_req):
        """Search recent GitHub releases for the latest one containing a .db master asset.

        Returns (release, db_asset, manifest_asset) or raises RuntimeError with a
        human-readable message when nothing usable is found.
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
                assets = release.get("assets", [])
                db_asset = next(
                    (a for a in assets
                     if a["name"].endswith(".db") and not a["name"].endswith(".manifest.json.db")),
                    None,
                )
                if not db_asset:
                    continue
                manifest_name = db_asset["name"] + ".manifest.json"
                manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
                if not manifest_asset:
                    continue
                return release, db_asset, manifest_asset
            page += 1
        raise RuntimeError("No release with a master .db asset found on GitHub.")

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

        try:
            try:
                release, db_asset, manifest_asset = _find_master_release(_req)
            except RuntimeError as exc:
                return jsonify({"available": False, "message": str(exc)})

            tag = release.get("tag_name", "?")
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

        ev_q: queue.Queue = queue.Queue()

        def _work() -> None:
            try:
                ev_q.put({"type": "progress", "label": "Checking GitHub for latest release…", "pct": None})
                try:
                    release, db_asset, manifest_asset = _find_master_release(_req)
                except RuntimeError as exc:
                    ev_q.put({"type": "error", "error": "no_releases", "message": str(exc)})
                    return

                tag = release.get("tag_name", "?")

                ev_q.put({"type": "progress", "label": f"Downloading manifest for {tag}…", "pct": None})
                mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
                mresp.raise_for_status()
                manifest = mresp.json()

                dest_dir = DATA_DIR / "imports"
                dest_dir.mkdir(parents=True, exist_ok=True)
                db_dest = dest_dir / db_asset["name"]
                manifest_dest = dest_dir / manifest_asset["name"]

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
                summary = database.import_master_db(str(db_dest), source="github")
                ev_q.put({"type": "done", "summary": summary})

            except Exception as exc:
                ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

        def _stream():
            from backend import activity as _activity

            with _activity.track("master_install", screen="/setup") as _job:
                while True:
                    try:
                        ev = ev_q.get(timeout=680)
                    except queue.Empty:
                        ev = {
                            "type": "error", "error": "timeout",
                            "message": "Update timed out after 680 s.",
                        }
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
            database.replace_folder_link(path, int(lb), body.get("note", ""))
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
        """Serve backend/resources/map.html for the gui_next map iframe and system browser."""
        resources_dir = (Path(__file__).parent / "resources").resolve()
        return send_from_directory(str(resources_dir), "map.html")

    @app.route("/leaflet/<path:filename>")
    def serve_leaflet(filename: str):
        """Serve bundled Leaflet JS/CSS assets from backend/resources/leaflet/."""
        leaflet_dir = (Path(__file__).parent / "resources" / "leaflet").resolve()
        return send_from_directory(str(leaflet_dir), filename)

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

        body = request.get_json(silent=True) or {}
        retry_failed = bool(body.get("retry_failed", False))
        limit = body.get("limit")

        if not _geocoder.start_batch_async(limit=limit, retry_failed=retry_failed):
            return jsonify({"error": "already running"}), 409
        return jsonify({"status": "started"})

    @app.route("/api/geocode/stop", methods=["POST"])
    def api_geocode_stop():
        """Signal the active geocode batch to stop; mirrors /api/bobdylan/stop.

        Returns:
            The current _geocoder._progress dict (with stop_requested=True
            once the flag is set) or 503 if the geocoder module is
            unavailable.
        """
        try:
            import backend.geocoder as _geocoder
        except ImportError:
            return jsonify({"error": "geocoder module not available"}), 503

        _geocoder.stop()
        return jsonify(_geocoder.get_progress())

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
            skipped (TODO-221 source='skipped_not_concert', excluded from
            failed), entries_total, entries_covered, pct_covered.
        """
        try:
            conn = database.get_connection()
            row = conn.execute("""
                SELECT
                    COUNT(*)                                                   AS total_cached,
                    COALESCE(SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END), 0) AS geocoded,
                    COALESCE(SUM(CASE WHEN lat IS NULL
                                       AND source != 'skipped_not_concert'
                                  THEN 1 ELSE 0 END), 0)                       AS failed,
                    COALESCE(SUM(CASE WHEN manual_override = 1 THEN 1 ELSE 0 END), 0) AS manual,
                    COALESCE(SUM(CASE WHEN source = 'skipped_not_concert'
                                  THEN 1 ELSE 0 END), 0)                       AS skipped
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

    @app.route("/taper-review")
    def taper_review_page() -> Response:
        """Serve the mobile-friendly taper conflict curation queue.

        One-card-at-a-time review of ``taper_attributions`` rows with
        ``conflict=1``, backed entirely by the existing curator confirm/reject
        API (TAPER phase 2) — each decision persists immediately server-side,
        so the queue can be worked in short sessions across page reloads.
        """
        review_html = Path(__file__).parent / "taper_review.html"
        return send_from_directory(str(review_html.parent), review_html.name)

    @app.route("/taper-curation")
    def taper_curation_page() -> Response:
        """Serve the taper curation workbench (TODO-327).

        A wide, keyboard-driven grid over all 16.7k entries: every source's
        taper opinion side by side with the raw LB description text, plus the
        isolated-text views for vocabulary work. Decisions post to the same
        curator-gated routes /taper-review uses.
        """
        page_html = Path(__file__).parent / "taper_curation.html"
        return send_from_directory(str(page_html.parent), page_html.name)

    @app.route("/qc-review")
    def qc_review_page() -> Response:
        """Serve the QC review console (TODO-342 Phase 2b, experimental).

        v1: Queue (one card at a time) and Findings (workbench table) tabs,
        both curator-gated for writes via the /api/qc/* routes above.
        """
        page_html = Path(__file__).parent / "qc_review.html"
        return send_from_directory(str(page_html.parent), page_html.name)

    @app.route("/api/admin/status", methods=["GET"])
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

    # ── Collection Integrity Monitor (TODO-284) ──────────────────────────────

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

    # ── Disk Scanner (TODO-250) ───────────────────────────────────────────────
    # One-shot discovery of audio folders anywhere on disk — no index is kept.
    # Unlike the integrity routes above, this looks *outside* the collection.

    @app.route("/api/scanner/scan", methods=["POST"])
    def scanner_scan_start() -> Response:
        """Start a background disk scan.

        Body: {roots: [str, ...], extensions?: [str, ...], excludes?: [str, ...]}
        Returns:
            JSON {ok: true}, 400 if roots is empty, or 409 if a scan is running.
        """
        try:
            from backend import disk_scanner
            data = request.get_json(silent=True) or {}
            roots = [r for r in (data.get("roots") or []) if str(r).strip()]
            if not roots:
                return jsonify({"error": "roots required"}), 400
            started = disk_scanner.start_scan_async(
                roots, data.get("extensions"), data.get("excludes"),
            )
            if not started:
                return jsonify({"ok": False, "error": "A scan is already running"}), 409
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scanner/scan/cancel", methods=["POST"])
    def scanner_scan_cancel() -> Response:
        """Request cancellation of the running disk scan, if any."""
        try:
            from backend import disk_scanner
            return jsonify({"ok": disk_scanner.cancel_scan()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scanner/scan/status", methods=["GET"])
    def scanner_scan_status() -> Response:
        """Return progress (and, once finished, results) of the disk scan."""
        try:
            from backend import disk_scanner
            return jsonify(disk_scanner.get_scan_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scanner/add", methods=["POST"])
    def scanner_add_to_collection() -> Response:
        """Add scanned folders to my_collection.

        Body: {paths: [str, ...]}
        Returns:
            JSON {results: [{path, ok, lb_number, error}, ...], added: int}.
        """
        try:
            from backend import disk_scanner
            data = request.get_json(silent=True) or {}
            paths = [p for p in (data.get("paths") or []) if str(p).strip()]
            if not paths:
                return jsonify({"error": "paths required"}), 400
            results = disk_scanner.add_paths_to_collection(paths)
            return jsonify({
                "results": results,
                "added": sum(1 for r in results if r["ok"]),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── File-level integrity / bit-rot inventory (TODO-267) ───────────────────
    # Distinct from /api/collection/integrity/* above: that one is per-LB and
    # lbdir-manifest-driven, this one is per-file across every file on a mount.

    @app.route("/api/file-integrity/scan", methods=["POST"])
    def file_integrity_scan_start() -> Response:
        """Start a background file-integrity scan on one mount.

        Body: {mount_id: int, mode: "index"|"verify"|"rolling",
               max_seconds?: number, limit?: int}

        One scan per mount; different mounts may scan concurrently since they
        are separate spindles. Returns 409 if that mount is already scanning.
        """
        try:
            from backend import file_integrity
            data = request.get_json(silent=True) or {}
            mount_id = data.get("mount_id")
            if mount_id is None:
                return jsonify({"error": "mount_id is required"}), 400
            mode = data.get("mode", "index")
            if mode not in ("index", "verify", "rolling"):
                return jsonify({"error": f"invalid mode {mode!r}"}), 400
            max_seconds = data.get("max_seconds")
            limit = data.get("limit")
            started = file_integrity.start_scan(
                int(mount_id), mode,
                max_seconds=float(max_seconds) if max_seconds else None,
                limit=int(limit) if limit else None,
            )
            if not started:
                return jsonify({
                    "ok": False, "error": "A scan is already running on this mount",
                }), 409
            return jsonify({"ok": True})
        except (ValueError, FileNotFoundError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/scan/cancel", methods=["POST"])
    def file_integrity_scan_cancel() -> Response:
        """Request cancellation of a running scan.

        Accepts ``mount_id`` in the JSON body (the screen's Stop button) or as
        a query param (the activity tray's Stop button, which POSTs no body).
        """
        try:
            from backend import file_integrity
            data = request.get_json(silent=True) or {}
            mount_id = data.get("mount_id", request.args.get("mount_id"))
            if mount_id is None:
                return jsonify({"error": "mount_id is required"}), 400
            return jsonify({"ok": file_integrity.cancel_scan(int(mount_id))})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/status", methods=["GET"])
    def file_integrity_status() -> Response:
        """Return live scan progress. Query param: mount_id (optional, else all)."""
        try:
            from backend import file_integrity
            mount_id = request.args.get("mount_id")
            return jsonify(file_integrity.get_status(
                int(mount_id) if mount_id else None
            ))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/summary", methods=["GET"])
    def file_integrity_summary() -> Response:
        """Return per-mount file counts by status, for GUI badges."""
        try:
            return jsonify(database.get_file_integrity_summary())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/problems", methods=["GET"])
    def file_integrity_problems() -> Response:
        """Return files flagged as anything but ok, rot first.

        Query params: limit (default 200), status (optional filter).
        """
        try:
            limit = int(request.args.get("limit", 200))
            status = request.args.get("status")
            return jsonify({
                "problems": database.get_file_integrity_problems(
                    limit=limit, status=status or None
                )
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/history", methods=["GET"])
    def file_integrity_history() -> Response:
        """Return recent scan runs. Query params: mount_id (optional), limit."""
        try:
            mount_id = request.args.get("mount_id")
            limit = int(request.args.get("limit", 20))
            return jsonify({
                "history": database.get_file_scan_history(
                    mount_id=int(mount_id) if mount_id else None, limit=limit
                )
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/file-integrity/rebaseline", methods=["POST"])
    def file_integrity_rebaseline() -> Response:
        """Accept current content as the new baseline for specific files.

        Body: {mount_id: int, rel_paths: [str]}

        Only ever operator-driven: a rot flag is sticky precisely so it cannot
        launder itself into a new baseline during a scan. Use after re-sourcing
        a corrupt file, or when the change was known-good.
        """
        try:
            from backend import file_integrity
            data = request.get_json(silent=True) or {}
            mount_id = data.get("mount_id")
            rel_paths = data.get("rel_paths") or []
            if mount_id is None or not rel_paths:
                return jsonify({"error": "mount_id and rel_paths are required"}), 400
            return jsonify(file_integrity.rebaseline(int(mount_id), list(rel_paths)))
        except (ValueError, FileNotFoundError) as e:
            return jsonify({"error": str(e)}), 400
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

        ``xref`` (optional, default 0) is the copy-level fileset id the
        pipeline's lookup step resolved (row.file.xref) — persisted to
        my_collection.xref (FABLE_XREF_INCORPORATION.md D3).

        ``file_mode`` (optional, "move" | "copy") overrides the
        pipeline_file_mode setting for this one job — tools/lb_nc.py sends
        "move" when shuffling a collection folder between mounts, which a
        global "copy" setting must never turn into a duplicate.
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
            xref = item.get("xref")
            if not path or not lb:
                return jsonify({
                    "ok": False,
                    "error": "path and lb_number are required",
                    "error_code": "bad_input",
                }), 400
            file_mode = data.get("file_mode") or database.get_meta("pipeline_file_mode") or "move"
            if file_mode not in ("move", "copy"):
                return jsonify({
                    "ok": False,
                    "error": "file_mode must be move or copy",
                    "error_code": "bad_input",
                }), 400
            result = start_file_job(
                int(lb), path, file_mode=file_mode,
                mount_id_override=int(mount_id) if mount_id is not None else None,
                xref=int(xref) if xref is not None else 0,
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

    # TODO-195: stable label_key enums for every pipeline step's `label` text.
    # `_FILE_BLOCKED_LABELS` doubles as the error_code -> (label, label_key) map
    # for the file step's "blocked" branch, since those error codes are already
    # stable enums.
    _FILE_BLOCKED_LABELS: dict[str, str] = {
        "no_date":       "No date",
        "no_route":      "No route",
        "mount_offline": "Mount offline",
        "dest_exists":   "Already exists",
        "db_error":      "DB error",
    }

    def _file_blocked_label(error_code: str | None) -> str:
        return _FILE_BLOCKED_LABELS.get(error_code or "", "Blocked")

    def _file_blocked_label_key(error_code: str | None) -> str:
        return error_code if error_code in _FILE_BLOCKED_LABELS else "blocked"

    def _pipeline_process_folder(folder_path: str, steps: set, force: bool = False) -> dict:
        """Run one or more pipeline steps on a single folder and return a PipelineRow dict.

        When ``force`` is False the two expensive hash steps (verify, lbdir) may be
        served from the P7 folder-state cache if the folder fingerprint is unchanged;
        ``force=True`` bypasses the cache and recomputes every requested step.
        """
        from backend.folder_naming import (
            apply_nft_suffix,
            lb_tag,
            strip_lb_tag,
            strip_nft_suffix,
        )
        from backend.folder_naming import (
            build_multi_lb_name as _build_multi_name,
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

        _mute = {"label_key": "mute", "label_params": {}}
        row: dict = {
            "folder": folder_path,
            "folderName": folder_name,
            "verify":  {"status": "mute", "label": "—", **_mute},
            "lookup":  {"status": "mute", "label": "—", "lb_number": None, **_mute},
            "rename":  {"status": "mute", "label": "—", "proposed": None, **_mute},
            "lbdir":   {"status": "mute", "label": "—", **_mute},
            "file":    {"status": "mute", "label": "—", "error": None, "error_code": None, **_mute},
            "severity": "attn",
            "errors": [],
        }

        if not folder.exists() or not folder.is_dir():
            row["errors"].append({"step": "verify", "message": "Folder not found"})
            row["verify"] = {
                "status": "bad", "label": "Missing",
                "label_key": "missing_folder", "label_params": {},
            }
            return row

        # ── P7 folder-state cache read (design §2b, §3) ──────────────────────
        # The fingerprint comparison below IS the design's R3 revalidation sweep:
        # a per-file os.stat aggregate that changes on any add/remove/rename/
        # in-place edit. Only the two expensive hash steps (verify, lbdir) are
        # ever served from cache; the cheap DB-dependent steps (lookup, rename,
        # file) always run fresh.
        fp_now = database.folder_fingerprint(folder_path)
        state = database.get_folder_state(folder_path)
        cache_valid = (
            (not force)
            and state is not None
            and fp_now is not None
            and state["fingerprint"] == fp_now
        )

        lb_number: int | None = None
        lb_numbers: list[int] = []
        # Copy-level xref (FABLE_XREF_INCORPORATION.md D1/D2/D3): per-LB
        # matched_xref from the lookup summary, populated in Step 2. Read via
        # _xref_for() in the rename/file steps so a re-lookup that resolves a
        # different fileset (e.g. after a DB update) always re-derives it
        # fresh rather than reusing a stale value from an earlier run.
        _lb_xref_map: dict[int, int] = {}

        def _xref_for(lb: int | None) -> int:
            return _lb_xref_map.get(lb, 0) if lb is not None else 0

        # ── Step 1: Verify ────────────────────────────────────────────────────
        if "verify" in steps and cache_valid and "verify" in state["steps"]:
            row["verify"] = {**state["steps"]["verify"], "cached": True}
        elif "verify" in steps:
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
                row["verify"] = {
                    "status": "bad", "label": "Error",
                    "label_key": "error", "label_params": {}, **_vcounts,
                }
                row["errors"].append({"step": "verify", "message": vr["error"]})
            elif vr["status"] == "pass":
                row["verify"] = {
                    "status": "ok", "label": "Pass",
                    "label_key": "pass", "label_params": {}, **_vcounts,
                }
            elif vr["status"] in ("incomplete", "no_checksums"):
                row["verify"] = {
                    "status": "warn", "label": "Incomplete",
                    "label_key": "incomplete", "label_params": {}, **_vcounts,
                }
            elif vr["status"] == "shntool_missing":
                row["verify"] = {
                    "status": "warn", "label": "No shntool", "shntool_missing": True,
                    "label_key": "no_shntool", "label_params": {}, **_vcounts,
                }
            else:
                row["verify"] = {
                    "status": "bad", "label": "Mismatch",
                    "label_key": "mismatch", "label_params": {}, **_vcounts,
                }

        # ── Step 2: Lookup ────────────────────────────────────────────────────
        if "lookup" in steps:
            from backend.checksum_utils import _is_reconciled_extra
            chk_parts: list[str] = []
            _chk_exts = {".ffp", ".md5", ".st5"}
            for f in sorted(folder.rglob("*")):
                if not (f.is_file() and f.suffix.lower() in _chk_exts):
                    continue
                # Never ingest sidecars that were deliberately set aside under
                # extras/ (move_extras). Those are superseded or alternate-version
                # checksums; parsing them merges a *different* fileset's hashes
                # into the input and makes the lookup falsely report a multi-LB
                # "perfect match" (e.g. a folder holding one transfer whose extras/
                # still carries the other transfer's .ffp/.md5). See BUG-257.
                if _is_reconciled_extra(f.relative_to(folder).as_posix()):
                    continue
                try:
                    chk_parts.append(f.read_text(errors="ignore"))
                except OSError:
                    pass

            if not chk_parts:
                row["lookup"] = {
                    "status": "warn", "label": "No checksums", "lb_number": None,
                    "label_key": "no_checksums", "label_params": {},
                }
            else:
                chk_text = "\n".join(chk_parts)
                parsed = database.parse_checksum_text(chk_text)
                if not parsed:
                    row["lookup"] = {
                        "status": "bad", "label": "Not found", "lb_number": None,
                        "label_key": "not_found", "label_params": {},
                    }
                else:
                    summary, detail = database.lookup_checksums(parsed)
                    _lb_xref_map = {
                        s["lb_number"]: s.get("matched_xref", 0)
                        for s in summary.get("lb_summary", [])
                    }
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

                    # Sticky folder→LB links (set via "Pin & continue", or
                    # auto-written for multi-LB perfect matches) win over the
                    # raw checksum match set.
                    pinned_links = database.get_folder_links(folder_path)
                    pinned_lbs = sorted(r["lb_number"] for r in pinned_links)

                    if pinned_lbs:
                        lb_numbers = pinned_lbs
                        lb_number = pinned_lbs[0]
                    elif len(lb_list) == 1:
                        lb_numbers = lb_list
                        lb_number = lb_list[0]
                    else:
                        lb_numbers = []
                        lb_number = None

                    # When multiple LBs all have perfect (MATCHED) status in the
                    # summary, the recording is genuinely archived under both
                    # entries — auto-link all and proceed rather than blocking.
                    if lb_number is None and len(lb_list) > 1 and not pinned_lbs:
                        _lb_summary_map = {
                            s["lb_number"]: s
                            for s in summary.get("lb_summary", [])
                        }
                        _all_perfect = all(
                            _lb_summary_map.get(lb, {}).get("status") == "MATCHED"
                            for lb in lb_list
                        )
                        if _all_perfect:
                            lb_numbers = sorted(lb_list)
                            lb_number = lb_numbers[0]
                            for _lb in lb_numbers:
                                database.set_folder_link(
                                    folder_path, _lb,
                                    "Auto-linked (multi-LB perfect match)",
                                    xref=_xref_for(_lb),
                                )

                    # For the single-pin incomplete-match guard below.
                    pinned_lb = pinned_lbs[0] if len(pinned_lbs) == 1 else (
                        lb_number if pinned_lbs else None
                    )

                    # A single resolved LB# is only a true "pass" when every
                    # parsed checksum (across all types — ffp/md5/st5) found a
                    # home in the DB. A 50% match (e.g. ffp matches but md5
                    # doesn't) means the files on disk diverge from the
                    # archived copy and needs human review, even though the
                    # LB# itself is correctly identified.
                    #
                    # Test on *distinct unmatched* checksums, not
                    # summary["matched"]: when the identical fileset is archived
                    # under more than one LB (duplicate entries — even when they
                    # collapse to one canonical after alias resolution), every
                    # checksum matches N times so summary["matched"] == given*N.
                    # A naive matched==given check then never holds and wedges a
                    # genuinely-complete folder in "Incomplete match" forever —
                    # pinning either LB can't clear it because the guard sees the
                    # inflated global count, not the pinned LB's own totals.
                    full_match = summary.get("unmatched", 1) == 0
                    is_multi_lb = len(lb_numbers) > 1

                    if lb_number is not None and (full_match or is_multi_lb):
                        label = (
                            "+".join(f"LB-{lb:05d}" for lb in lb_numbers)
                            if is_multi_lb else f"LB-{lb_number:05d}"
                        )
                        row["lookup"] = {
                            "status": "ok",
                            "label": label,
                            # The matched LB tag(s) are locale-invariant data, not a
                            # translatable sentence — no label_key means the frontend
                            # falls back to this raw label unchanged.
                            "label_key": None,
                            "label_params": {},
                            "lb_number": lb_number,
                            "lb_numbers": lb_numbers,
                            "alias_resolved_from": alias_resolved_from or None,
                            "summary": summary,
                            "detail": detail,
                        }
                    elif lb_number is not None:
                        row["lookup"] = {
                            "status": "warn",
                            "label": "Incomplete match",
                            "label_key": "incomplete_match",
                            "label_params": {},
                            "lb_number": lb_number,
                            "lb_numbers": lb_numbers,
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
                        # Downstream steps (lbdir/rename/file) must stay mute for an
                        # incomplete match — the files on disk haven't been confirmed
                        # against the archive.  Only allow them through if the user
                        # has explicitly pinned this folder (they've reviewed and
                        # accepted the partial match).
                        if pinned_lb is None:
                            lb_number = None
                    elif len(lb_list) > 1:
                        row["lookup"] = {"status": "warn", "label": "Conflict",
                                         "label_key": "conflict", "label_params": {},
                                         "lb_number": None, "lb_numbers": [],
                                         "alias_resolved_from": None,
                                         "summary": summary, "detail": detail}
                        row["errors"].append({"step": "lookup", "message": f"Multiple LBs: {lb_list}"})
                    else:
                        row["lookup"] = {"status": "bad", "label": "Not found",
                                         "label_key": "not_found", "label_params": {},
                                         "lb_number": None, "lb_numbers": [],
                                         "alias_resolved_from": None,
                                         "summary": summary, "detail": detail}

        # ── P3 prefetch trigger (TODO-205 Phase 5) ───────────────────────────
        # Once Lookup has settled on an LB, warm its lbdir attachment off the
        # stage chain — but only if the folder has no lbdir file and none is
        # cached (both cheap fs/cache checks). Best-effort: a prefetch failure
        # must never break the lookup step.
        if lb_number and "lbdir" in steps:
            try:
                if (_find_lbdir_in_folder(folder, lb_number) is None
                        and find_lbdir_attachment(lb_number, xref=_xref_for(lb_number)) is None):
                    _submit_lbdir_prefetch(lb_number)
            except Exception as exc:
                _log.warning("lbdir prefetch trigger failed for LB-%05d: %s",
                             lb_number, exc)

        # ── Step 3: LBDIR retrieve + verify ──────────────────────────────────
        if ("lbdir" in steps and cache_valid and "lbdir" in state["steps"]
                and state["steps"]["lbdir"].get("lb_number") == lb_number
                and not state["steps"]["lbdir"].get("pending_fetch")):
            # Serve the cached manifest verdict only when it was verified against
            # the same LB the lookup just resolved (lookup always runs fresh). A
            # re-pin to a different LB changes lb_number and forces a fresh check.
            # No set_lbdir_verified() here: nothing was re-verified this run, so
            # the collection's "Confirmed" date must not be re-stamped.
            row["lbdir"] = {**state["steps"]["lbdir"], "cached": True}
        elif "lbdir" in steps:
            if lb_number:
                # Scoped to the LB the lookup just resolved: after an override
                # the folder still holds the previous LB's manifest, and
                # verifying against it reports the wrong archive entry until
                # the file is manually removed (BUG-315).
                lbdir_file = _find_lbdir_in_folder(folder, lb_number, strict=True)
                pending_fetch = False
                if not lbdir_file:
                    # Try the attachments cache; if uncached, either park on an
                    # inflight P3 prefetch or (fallback) scrape synchronously.
                    try:
                        xref = _xref_for(lb_number)
                        lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
                        if not lbdir_src:
                            # Resolve canonical alias once — needed both for the
                            # inflight check and the synchronous fallback. Alias
                            # resolution only applies to canonical (xref=0) lookups:
                            # an xref-N miss means the specific fileset attachment
                            # is missing, not that lb_number is an alias (BUG-310).
                            canonicals = database.resolve_aliases([lb_number]) if xref == 0 else []
                            canonical = canonicals[0] if canonicals and canonicals[0] != lb_number else None
                            with _LBDIR_PREFETCH_LOCK:
                                inflight = (
                                    lb_number in _LBDIR_PREFETCH_INFLIGHT
                                    or (canonical is not None
                                        and canonical in _LBDIR_PREFETCH_INFLIGHT)
                                )
                            if inflight:
                                # A P3 prefetch is running for this LB — don't block
                                # on a live scrape. Park the row instead.
                                pending_fetch = True
                            else:
                                # Safety-net: no prefetch inflight (submission
                                # failed or never fired) — original synchronous
                                # scrape path, unchanged.
                                scraper.scrape_entry(lb_number, force=False, download_files=True)
                                lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
                                if not lbdir_src and canonical:
                                    lbdir_src = find_lbdir_attachment(canonical)
                                    if not lbdir_src:
                                        scraper.scrape_entry(canonical, force=False, download_files=True)
                                        lbdir_src = find_lbdir_attachment(canonical)
                        if lbdir_src:
                            shutil.copy2(str(lbdir_src), str(folder / lbdir_src.name))
                            lbdir_file = folder / lbdir_src.name
                    except Exception:
                        pass

                if not lbdir_file:
                    # This LB has no manifest of its own to pull in (common for
                    # double-LB pairs — only one entry carries the lbdir). Fall
                    # back to whatever manifest the folder already holds rather
                    # than reporting nothing, and don't park on a prefetch that
                    # has something to verify against meanwhile (BUG-315).
                    lbdir_file = _find_lbdir_in_folder(folder, lb_number)
                    if lbdir_file:
                        pending_fetch = False

                if pending_fetch:
                    # Wire status stays "mute" because the GUI StepStatus type is a
                    # closed union; the pending_fetch marker carries the "fetching,
                    # don't escalate" semantics for severity + auto-complete.
                    row["lbdir"] = {"status": "mute", "label": "Fetching LBDIR…",
                                    "label_key": "fetching", "label_params": {},
                                    "pending_fetch": True, "check": None}
                elif lbdir_file:
                    check = checksum_utils.verify_folder_lbdir(str(folder), lbdir_file)
                    row["lbdir"] = _lbdir_verdict(check)
                    if check.get("status") == "pass":
                        # If this folder is already an owned collection item (re-check
                        # of an in-place folder), stamp lbdir_verified_at so the Collect
                        # stage's "Confirmed" date reflects this pass. No-op otherwise.
                        database.set_lbdir_verified(str(folder))
                else:
                    row["lbdir"] = _lbdir_verdict(None)
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
                # Copy-level xref (D2): each LB tag carries the fileset id this
                # folder's checksums matched, re-derived fresh every run so a
                # changed matched_xref (e.g. after a master re-import) always
                # produces a new proposal — see _xref_for() above.
                matched_xrefs = [_xref_for(lb) for lb in lb_numbers]
                if len(lb_numbers) > 1:
                    proposed = _build_multi_name(
                        lb_numbers, date_str, location, lb_status, matched_xrefs,
                    )
                    if not date_str or not location:
                        base = strip_nft_suffix(folder_name)
                        multi_tag = "(" + "+".join(
                            lb_tag(lb, xr)
                            for lb, xr in zip(lb_numbers, matched_xrefs, strict=True)
                        ) + ")"
                        if not base.rstrip().upper().endswith(multi_tag.upper()):
                            untagged = strip_lb_tag(base)
                            proposed = apply_nft_suffix(f"{untagged} {multi_tag}", lb_status)
                else:
                    matched_xref = _xref_for(lb_number)
                    proposed = _build_name(lb_number, date_str, location, lb_status, matched_xref)
                # BUG-119: when DB has no date/location the standard name falls
                # back to bare LB-NNNNN[-NFT], which would silently strip any
                # date/location already in the folder name.  Use the current
                # folder name as the base and only adjust the NFT suffix and
                # (LB-NNNNN[-xrefYYYYY]) tag — never touch the date/location portion.
                if len(lb_numbers) <= 1 and (not date_str or not location):
                    base = strip_nft_suffix(folder_name)
                    correct_tag = f"({lb_tag(lb_number, _xref_for(lb_number))})"
                    if base.rstrip().lower().endswith(correct_tag.lower()):
                        proposed = apply_nft_suffix(base, lb_status)
                    else:
                        # BUG-176: folder is missing (or has a stale) LB# tag —
                        # strip any existing tag (incl. a stale/wild xref suffix)
                        # and append the correct one.
                        untagged = strip_lb_tag(base)
                        proposed = apply_nft_suffix(f"{untagged} {correct_tag}", lb_status)
                if folder_name == proposed:
                    row["rename"] = {
                        "status": "ok", "label": "Correct", "proposed": None,
                        "label_key": "correct", "label_params": {},
                    }
                else:
                    row["rename"] = {
                        "status": "warn", "label": "Proposed", "proposed": proposed,
                        "label_key": "proposed", "label_params": {},
                    }
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
                            "SELECT disk_path, lbdir_verified_at FROM my_collection WHERE lb_number=?",
                            (lb_number,),
                        ).fetchone()
                    row["file"] = {
                        "status": "ready",
                        "label": "Ready to file",
                        "label_key": "ready_to_file",
                        "label_params": {},
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
                        "existing_disk_path": owned_row["disk_path"] if owned_row else None,
                        "lbdir_verified_at": owned_row["lbdir_verified_at"] if owned_row else None,
                        # Copy-level xref (D3): carried by the GUI into
                        # /api/pipeline/file/start so filing persists it to
                        # my_collection.xref.
                        "xref": _xref_for(lb_number),
                    }
                else:
                    row["file"] = {
                        "status": "blocked",
                        "label": "Mount offline",
                        "label_key": "mount_offline",
                        "label_params": {},
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
                    "label_key": _file_blocked_label_key(resolution["error_code"]),
                    "label_params": {},
                    "dest_parent": "",
                    "dest": "",
                    "mount_label": "",
                    "year": resolution["year"],
                    "error": resolution["error"],
                    "error_code": resolution["error_code"],
                }
        else:
            row["file"] = {
                "status": "mute", "label": "—", "error": None, "error_code": None,
                "label_key": "mute", "label_params": {},
            }

        # ── Severity (pure fn extracted for testability/warm-start, TODO-211) ──
        # On a partial run the steps that weren't requested stay "mute" in `row`.
        # Fold in the last-known verdicts from the validated folder-state cache so
        # severity reflects the whole folder, not just the step(s) that ran this
        # call — a re-verify of an already-filed folder keeps its "done" state
        # instead of being demoted, and a lone verify pass on an unidentified
        # folder is not promoted to "done".
        def _sev_step(name: str) -> dict:
            cur = row[name]
            if name in steps or cur.get("status", "mute") != "mute":
                return cur
            if cache_valid and name in state["steps"]:
                return state["steps"][name]
            return cur

        _sev_lookup = _sev_step("lookup")
        _sev_lb = lb_number if lb_number is not None else _sev_lookup.get("lb_number")
        row["severity"] = compute_pipeline_severity(
            _sev_step("verify"), _sev_lookup, _sev_step("lbdir"), _sev_step("rename"),
            row["file"]["status"], row["file"].get("error_code"), _sev_lb,
        )

        # ── P7 folder-state cache write (design §4d) ─────────────────────────
        # Recompute the fingerprint here instead of reusing fp_now: the lbdir step
        # may have copied a manifest file into the folder mid-run, which changes
        # the per-file stat aggregate — persisting under the stale entry
        # fingerprint would make the row look invalid on the very next request.
        try:
            fp_post = database.folder_fingerprint(folder_path)
            if fp_post is not None:
                step_results: dict = {}
                for name in steps:
                    if name == "lbdir" and row["lbdir"].get("pending_fetch"):
                        # Never persist a pending verdict: the folder fingerprint
                        # doesn't change until the lbdir file is copied in, so a
                        # stored pending verdict would be served cached:true forever
                        # even after the prefetch completes.
                        continue
                    verdict = dict(row[name])
                    verdict.pop("cached", None)  # transport annotation, never stored
                    if name == "lbdir":
                        # Record the LB this manifest check ran against so the
                        # rule-3 guard can reject the verdict after a re-pin.
                        verdict["lb_number"] = lb_number
                    step_results[name] = verdict
                database.put_folder_state(folder_path, fp_post, step_results)
        except Exception as exc:
            _log.warning("pipeline: folder-state cache write failed for %s: %s",
                         folder_path, exc)

        return row

    @app.route("/api/pipeline/run", methods=["POST"])
    def pipeline_run() -> Response:
        """Run pipeline steps on a list of folders.

        Body: {folders: [path, ...], steps: ["verify","lookup","lbdir","rename","file"],
        force?: bool}. ``force=true`` bypasses the P7 folder-state cache and
        recomputes every requested step.
        Returns:
            JSON {results: [PipelineRow, ...]}
        """
        try:
            data = request.get_json() or {}
            folders: list[str] = data.get("folders", [])
            steps: set[str] = set(data.get("steps", ["verify", "lookup", "lbdir", "rename", "file"]))
            force: bool = bool(data.get("force", False))
            if not folders:
                return jsonify({"error": "folders list required"}), 400
            results = [_pipeline_process_folder(f, steps, force) for f in folders]
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    def _pipeline_run_async_coordinator(folders: list[str], steps: list[str], workers: int,
                                        force: bool = False) -> None:
        """Drain ``folders`` through ``_pipeline_process_folder`` across worker threads.

        Folders are grouped by source device (``os.stat().st_dev``); a folder whose
        stat fails is still processed, in a ``None`` group of its own (it yields the
        "Folder not found" row from ``_pipeline_process_folder``). One daemon thread
        drains each device group serially (FIFO within the group), while a global
        ``threading.Semaphore(workers)`` caps how many folders are in flight across
        *different* groups at once — at most one worker per device, at most
        ``workers`` folders total, per design doc §4c (parallel hashing on one
        spindle seek-thrashes).

        Cancellation (`_PIPELINE_CANCEL_EVENT`) is cooperative and checked only
        between folders (once before a group's next folder, once more right after
        the semaphore is acquired) — never mid-folder.

        Args:
            folders: Absolute folder paths to process, in caller-supplied order.
            steps: Pipeline step names to run per folder (pre-validated by the
                caller route).
            workers: Global concurrency cap, already clamped to 1-4.
            force: When True, bypass the P7 folder-state cache and recompute
                every requested step for every folder.
        """
        groups: dict[object, list[str]] = {}
        for folder in folders:
            try:
                dev = os.stat(folder).st_dev
            except OSError:
                dev = None
            groups.setdefault(dev, []).append(folder)

        semaphore = threading.Semaphore(workers)
        step_set = set(steps)

        def _process_one(folder: str) -> None:
            with _PIPELINE_JOB_LOCK:
                _PIPELINE_JOB["in_progress"].append(folder)
            try:
                row = _pipeline_process_folder(folder, step_set, force)
            except Exception as exc:
                _log.exception("pipeline async: folder failed: %s", folder)
                with _PIPELINE_JOB_LOCK:
                    _PIPELINE_JOB["errors"].append({"folder": folder, "message": str(exc)})
            else:
                with _PIPELINE_JOB_LOCK:
                    _PIPELINE_JOB["results"][folder] = row
            finally:
                with _PIPELINE_JOB_LOCK:
                    if folder in _PIPELINE_JOB["in_progress"]:
                        _PIPELINE_JOB["in_progress"].remove(folder)
                    _PIPELINE_JOB["folders_done"] += 1

        def _drain(group_folders: list[str]) -> None:
            for folder in group_folders:
                if _PIPELINE_CANCEL_EVENT.is_set():
                    return
                semaphore.acquire()
                try:
                    if _PIPELINE_CANCEL_EVENT.is_set():
                        return
                    _process_one(folder)
                finally:
                    semaphore.release()

        drain_threads = [
            threading.Thread(target=_drain, args=(group_folders,), daemon=True,
                              name=f"pipeline-drain-{dev}")
            for dev, group_folders in groups.items()
        ]
        for t in drain_threads:
            t.start()
        for t in drain_threads:
            t.join()

        with _PIPELINE_JOB_LOCK:
            _PIPELINE_JOB["running"] = False
            _PIPELINE_JOB["cancelled"] = _PIPELINE_CANCEL_EVENT.is_set()

    @app.route("/api/pipeline/run/start", methods=["POST"])
    def pipeline_run_start() -> Response:
        """Start an async pipeline run across multiple folders (TODO-205 Phase 2).

        Body: {folders: [path, ...], steps?: ["verify","lookup","lbdir","rename","file"],
        workers?: int, force?: bool}. ``force=true`` bypasses the P7 folder-state
        cache and recomputes every requested step. Returns immediately with
        {ok: true, started: N} or {ok: false, error, error_code}. Poll
        /api/pipeline/run/status for progress
        and cancel via /api/pipeline/run/cancel. The synchronous /api/pipeline/run
        route is unaffected and keeps working standalone.
        """
        try:
            data = request.get_json() or {}
            folders: list[str] = data.get("folders", [])
            if not folders:
                return jsonify({
                    "ok": False,
                    "error": "folders list required",
                    "error_code": "bad_input",
                }), 400

            allowed_steps = {"verify", "lookup", "lbdir", "rename", "file"}
            steps = data.get("steps", ["verify", "lookup", "lbdir", "rename", "file"])
            if not isinstance(steps, list) or not set(steps).issubset(allowed_steps):
                return jsonify({
                    "ok": False,
                    "error": "steps must be a subset of verify, lookup, lbdir, rename, file",
                    "error_code": "bad_input",
                }), 400

            try:
                workers = int(data.get("workers", 2))
            except (TypeError, ValueError):
                workers = 2
            workers = max(1, min(4, workers))
            force: bool = bool(data.get("force", False))

            with _PIPELINE_JOB_LOCK:
                if _PIPELINE_JOB["running"]:
                    return jsonify({
                        "ok": False,
                        "error": "A pipeline job is already in progress",
                        "error_code": "busy",
                    })
                _PIPELINE_CANCEL_EVENT.clear()
                _PIPELINE_JOB["running"] = True
                _PIPELINE_JOB["folders_total"] = len(folders)
                _PIPELINE_JOB["folders_done"] = 0
                _PIPELINE_JOB["in_progress"] = []
                _PIPELINE_JOB["results"] = {}
                _PIPELINE_JOB["errors"] = []
                _PIPELINE_JOB["steps"] = list(steps)
                _PIPELINE_JOB["started_at"] = time.time()
                _PIPELINE_JOB["cancelled"] = False

            thread = threading.Thread(
                target=_pipeline_run_async_coordinator,
                args=(folders, list(steps), workers, force),
                daemon=True,
                name="pipeline-run-coordinator",
            )
            thread.start()
            return jsonify({"ok": True, "started": len(folders)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/pipeline/run/status", methods=["GET"])
    def pipeline_run_status() -> Response:
        """Poll progress of the async pipeline job started via /api/pipeline/run/start."""
        return jsonify(get_pipeline_run_status())

    @app.route("/api/pipeline/run/cancel", methods=["POST"])
    def pipeline_run_cancel() -> Response:
        """Request cancellation of the running async pipeline job, if any.

        Cancellation is cooperative (see `_pipeline_run_async_coordinator`):
        in-flight folders finish, no new folder starts.
        """
        with _PIPELINE_JOB_LOCK:
            was_running = _PIPELINE_JOB["running"]
        _PIPELINE_CANCEL_EVENT.set()
        return jsonify({"ok": True, "was_running": was_running})

    @app.route("/api/pipeline/state", methods=["POST"])
    def pipeline_state() -> Response:
        """Return last-known cached verdicts for a set of folders (warm-start).

        TODO-205 Phase 7: lets the GUI paint pipeline buckets immediately after an
        app restart, before any re-run. For each folder whose stored fingerprint
        still matches the folder on disk (design R3 revalidation), the persisted
        per-step verdicts are returned with a freshly computed severity. Folders
        with no cache, an invalidated fingerprint, or an unreadable path are
        omitted — the GUI leaves those rows empty and runs them normally. The file
        step is returned for appearance only and is never trusted (P8); the GUI
        re-resolves it live on the next run.

        Body: {folders: [path, ...]}
        Returns: {ok: true, results: {path: row}} where each row mirrors a
        /api/pipeline/run result (verify/lookup/lbdir/rename/file/severity/errors).
        """
        try:
            data = request.get_json() or {}
            folders = data.get("folders", [])
            if not isinstance(folders, list):
                return jsonify({
                    "ok": False,
                    "error": "folders must be a list",
                    "error_code": "bad_input",
                }), 400

            results: dict[str, dict] = {}
            for folder_path in folders:
                try:
                    state = database.get_folder_state(folder_path)
                    if state is None:
                        continue
                    fp_now = database.folder_fingerprint(folder_path)
                    if fp_now is None or state["fingerprint"] != fp_now:
                        continue
                    steps = state["steps"]
                    mute = {"status": "mute", "label": "—"}
                    verify = steps.get("verify", dict(mute))
                    lookup = steps.get("lookup", dict(mute))
                    lbdir = steps.get("lbdir", dict(mute))
                    rename = steps.get("rename", dict(mute))
                    file_step = steps.get("file", {
                        "status": "mute", "label": "—",
                        "error": None, "error_code": None,
                    })
                    lb_number = lookup.get("lb_number") or lbdir.get("lb_number")
                    results[folder_path] = {
                        "folder": folder_path,
                        "verify": verify,
                        "lookup": lookup,
                        "lbdir": lbdir,
                        "rename": rename,
                        "file": file_step,
                        "errors": [],
                        "severity": compute_pipeline_severity(
                            verify, lookup, lbdir, rename,
                            file_step.get("status", "mute"),
                            file_step.get("error_code"), lb_number,
                        ),
                    }
                except Exception as exc:
                    _log.warning("pipeline: warm-start state read failed for %s: %s",
                                 folder_path, exc)
            return jsonify({"ok": True, "results": results})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/folder/rename", methods=["POST"])
    def folder_rename() -> Response:
        """Rename a folder on disk to a new name within the same parent directory.

        Also best-effort syncs qBittorrent (see backend.filer._sync_qbt_location)
        if the folder is already tracked in qBittorrent for a known lb_number,
        resolved from the request body's ``lb_number`` (the pipeline's lookup
        match — set for the typical single-LB-match rename candidate, which has
        not been filed into my_collection yet at rename time, BUG-309), else
        my_collection, else a "Pin & continue" folder link — so an already-added
        torrent keeps seeding under the new name.

        Body: {folder: "/abs/path/to/folder", new_name: "new folder name",
               lb_number?: int}
        Returns:
            JSON {ok: true, new_path: "...", qbt_synced: bool, qbt_error: str|None}
        """
        try:
            from backend.filer import _sync_qbt_location
            from backend.rename import write_rename_log
            data = request.get_json() or {}
            folder = Path(data.get("folder", ""))
            new_name: str = (data.get("new_name") or "").strip()
            lb_number_hint = data.get("lb_number")
            if lb_number_hint is not None:
                try:
                    lb_number_hint = int(lb_number_hint)
                except (ValueError, TypeError):
                    lb_number_hint = None
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
            try:
                folder.rename(new_path)
            except (FileExistsError, OSError):
                if new_path.exists():
                    return jsonify({"error": f"Target already exists: {new_name}"}), 409
                raise
            # BUG-206: sync my_collection if this folder was already filed
            old_disk_path = str(folder)
            with database.get_connection() as conn:
                row = conn.execute(
                    "SELECT lb_number FROM my_collection WHERE disk_path=?",
                    (old_disk_path,),
                ).fetchone()
            if row:
                database.update_collection(
                    row["lb_number"],
                    {"folder_name": new_name, "disk_path": str(new_path)},
                )
            # BUG-212: a "Pin & continue" link is keyed on the exact folder
            # path — move it forward so the pinned LB# survives the rename
            # instead of being silently lost on the next pipeline run.
            database.rekey_folder_link(old_disk_path, str(new_path))
            # Best-effort qBittorrent sync so a torrent already tracked under
            # the old name keeps seeding instead of erroring on missing files.
            # lb_number: prefer the my_collection row just synced above, else
            # the caller-supplied lookup hint (BUG-309 — the typical single-LB
            # rename candidate has no my_collection row yet, since it isn't
            # filed until later), else a "Pin & continue" folder link.
            lb_number = row["lb_number"] if row else None
            if lb_number is None:
                lb_number = lb_number_hint
            if lb_number is None:
                link = database.get_folder_link(old_disk_path)
                lb_number = link["lb_number"] if link else None
            qbt_synced = False
            qbt_error = None
            if lb_number is not None:
                qbt_synced, qbt_error = _sync_qbt_location(int(lb_number), folder, new_path)
            return jsonify({
                "ok": True, "new_path": str(new_path),
                "qbt_synced": qbt_synced, "qbt_error": qbt_error,
            })
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

            root_has_audio = _has_audio(root)
            if root_has_audio:
                found.append(str(root))
            if shallow:
                if not root_has_audio:
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
