"""lb_master integrity + pipeline refresh Phase 2/3 routes (TODO-369)."""

import json
import logging
import threading
import time

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend import lb_coverage as _lb_coverage
from backend import refresh as _refresh

_log = logging.getLogger(__name__)

bp = Blueprint("lb_master", __name__)

_reconcile_lock = threading.Lock()  # prevents concurrent lb_master reconcile runs


# ── lb_master integrity API ────────────────────────────────────────────────

@bp.route("/api/lb_master/stats", methods=["GET"])
def lb_master_stats() -> Response:
    """Return {public, private, missing, max_lb, overrides, needs_review} counts."""
    try:
        return jsonify(database.get_lb_master_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb/coverage", methods=["GET"])
def lb_coverage_endpoint() -> Response:
    """Return the read-only LB-catalogue coverage snapshot for the award screen."""
    try:
        conn = database.get_connection()
        return jsonify(_lb_coverage.get_coverage(conn))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb/coverage/ledger", methods=["GET"])
def lb_coverage_ledger_endpoint() -> Response:
    """Return one page of the per-entry LB ledger (TODO-305).

    Query params: page, per_page, filter (all|held|missing|unmatched|review),
    q (free text over LB#/date/location), lb (deep-link — returns the page
    containing that LB number).
    """
    try:
        lb_raw = request.args.get("lb")
        conn = database.get_connection()
        return jsonify(_lb_coverage.get_ledger(
            conn,
            page=request.args.get("page", 1, type=int),
            per_page=request.args.get("per_page", 50, type=int),
            filt=request.args.get("filter", "all"),
            q=request.args.get("q", ""),
            lb=int(lb_raw) if lb_raw and lb_raw.strip().lstrip("-").isdigit() else None,
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb/snapshots", methods=["GET"])
def lb_snapshots_endpoint() -> Response:
    """Return LB-catalogue snapshot/import history, newest first (TODO-305)."""
    try:
        conn = database.get_connection()
        return jsonify(_lb_coverage.get_snapshots(
            conn, limit=request.args.get("limit", 50, type=int)
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/refresh/status", methods=["GET"])
def refresh_status_endpoint() -> Response:
    """Return the read-only pipeline freshness snapshot. Optional ?trigger=T1 filter."""
    try:
        import backend.refresh_exec as _refresh_exec

        trigger = request.args.get("trigger")
        return jsonify(_refresh_exec.annotate_buckets(_refresh.compute_plan(trigger=trigger)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/refresh/queues", methods=["GET"])
def refresh_queues_endpoint() -> Response:
    """Return the human review queue counts (Phase 4, TODO-310).

    Standalone from /api/refresh/status (which carries the same list) so
    the nav badge can poll four sub-millisecond counts without recomputing
    the whole 27-step plan every minute.
    """
    try:
        from backend import queues as _queues

        return jsonify(_queues.snapshot())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Pipeline refresh Phase 2: wrapped CLI-only steps (TODO-306) ─────────
# Fetch routes are ungated (same rationale as /api/geocode/run — decision 2);
# the GUI Run button confirms once. Ranker scan/rerank are also ungated.

@bp.route("/api/olof/fetch", methods=["POST"])
def olof_fetch_run() -> Response:
    """Start an olof (DSN + chronicle) fetch job. Body: {corpus?, limit?,
    refresh?, dry_run?}."""
    import backend.olof_fetcher as _olof_fetcher

    body = request.get_json(silent=True) or {}
    corpus = body.get("corpus", "all")
    if corpus not in ("dsn", "chronicle", "all"):
        return jsonify({"error": "bad_request",
                        "message": "corpus must be 'dsn', 'chronicle', or 'all'"}), 400
    if not _olof_fetcher.try_begin(stage="queued", corpus=corpus):
        return jsonify({"error": "already_running"}), 409
    threading.Thread(
        target=_olof_fetcher.run_fetch_claimed,
        kwargs={
            "corpus": corpus,
            "limit": body.get("limit"),
            "refresh": bool(body.get("refresh", False)),
            "dry_run": bool(body.get("dry_run", False)),
        },
        daemon=True, name="olof-fetch",
    ).start()
    return jsonify({"status": "started"})


@bp.route("/api/olof/fetch/status", methods=["GET"])
def olof_fetch_status() -> Response:
    """Return the current olof-fetch job's progress snapshot."""
    import backend.olof_fetcher as _olof_fetcher
    return jsonify(_olof_fetcher.get_status())


@bp.route("/api/olof/fetch/stop", methods=["POST"])
def olof_fetch_stop() -> Response:
    """Request that the active olof-fetch job stop as soon as possible."""
    import backend.olof_fetcher as _olof_fetcher
    _olof_fetcher.stop()
    return jsonify(_olof_fetcher.get_status())


@bp.route("/api/bobserve/fetch", methods=["POST"])
def bobserve_fetch_run() -> Response:
    """Start a bobserve.com setlist fetch job. Body: {start_year?, end_year?,
    limit?, refresh?, dry_run?}."""
    import backend.bobserve_fetcher as _bobserve_fetcher

    body = request.get_json(silent=True) or {}
    if not _bobserve_fetcher.try_begin(
        stage="queued", start_year=body.get("start_year"), end_year=body.get("end_year"),
    ):
        return jsonify({"error": "already_running"}), 409
    kwargs = {
        "limit": body.get("limit"),
        "refresh": bool(body.get("refresh", False)),
        "dry_run": bool(body.get("dry_run", False)),
    }
    if body.get("start_year") is not None:
        kwargs["start_year"] = body["start_year"]
    if body.get("end_year") is not None:
        kwargs["end_year"] = body["end_year"]
    threading.Thread(
        target=_bobserve_fetcher.run_fetch_claimed, kwargs=kwargs,
        daemon=True, name="bobserve-fetch",
    ).start()
    return jsonify({"status": "started"})


@bp.route("/api/bobserve/fetch/status", methods=["GET"])
def bobserve_fetch_status() -> Response:
    """Return the current bobserve-fetch job's progress snapshot."""
    import backend.bobserve_fetcher as _bobserve_fetcher
    return jsonify(_bobserve_fetcher.get_status())


@bp.route("/api/bobserve/fetch/stop", methods=["POST"])
def bobserve_fetch_stop() -> Response:
    """Request that the active bobserve-fetch job stop as soon as possible."""
    import backend.bobserve_fetcher as _bobserve_fetcher
    _bobserve_fetcher.stop()
    return jsonify(_bobserve_fetcher.get_status())


# ── Pipeline refresh Phase 3: parser routes (decision 2, spec §3.3) ──────
# Synchronous: a full DSN/bobserve reparse is tens of seconds and both
# run_parse() functions are already pure-DB with no network. The 409
# guard matters — parsing a half-written mirror directory (fetch still
# running) yields a coverage summary that reads as data loss.

@bp.route("/api/olof/parse", methods=["POST"])
def olof_parse_run() -> Response:
    """Synchronously reparse local DSN/chronicle pages. Body: {file?}.

    409 while the olof fetch job is running; 503 if backend.olof_parser
    isn't importable (bs4/lxml missing).
    """
    try:
        import backend.olof_fetcher as _olof_fetcher
        import backend.olof_parser as _olof_parser
    except ImportError as exc:
        return jsonify({"error": "module_unavailable", "message": str(exc)}), 503

    if _olof_fetcher.get_status()["running"]:
        return jsonify({"error": "fetch_running"}), 409

    body = request.get_json(silent=True) or {}
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        summary = _olof_parser.run_parse(file=body.get("file"))
    except Exception as exc:
        _log.exception("olof_parse route failed")
        database.record_step_run(
            "olof_parse", status="error", started_at=started_at,
            trigger_source="route",
        )
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    database.record_step_run(
        "olof_parse", status="ok", started_at=started_at,
        counters=summary, trigger_source="route",
    )
    return jsonify({"ok": True, **summary})


@bp.route("/api/olof/chronicle_parse", methods=["POST"])
def olof_chronicle_parse_run() -> Response:
    """Synchronously reparse local chronicle pages. Body: {file?}.

    Separate from /api/olof/parse because a different module owns the
    chronicle corpus (backend.olof_chronicle_parser) and olof_parse only
    selects corpus='dsn' (TODO-309). 409 while the olof fetch job is
    running; 503 if the parser isn't importable (bs4/lxml missing).
    """
    try:
        import backend.olof_chronicle_parser as _chronicle_parser
        import backend.olof_fetcher as _olof_fetcher
    except ImportError as exc:
        return jsonify({"error": "module_unavailable", "message": str(exc)}), 503

    if _olof_fetcher.get_status()["running"]:
        return jsonify({"error": "fetch_running"}), 409

    body = request.get_json(silent=True) or {}
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        summary = _chronicle_parser.run_parse(file=body.get("file"))
    except Exception as exc:
        _log.exception("olof_chronicle_parse route failed")
        database.record_step_run(
            "olof_chronicle_parse", status="error", started_at=started_at,
            trigger_source="route",
        )
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    database.record_step_run(
        "olof_chronicle_parse", status="ok", started_at=started_at,
        counters=summary, trigger_source="route",
    )
    return jsonify({"ok": True, **summary})


@bp.route("/api/bobserve/parse", methods=["POST"])
def bobserve_parse_run() -> Response:
    """Synchronously reparse local bobserve pages. Body: {file?}.

    409 while the bobserve fetch job is running; 503 if
    backend.bobserve_parser isn't importable (bs4/lxml missing).
    """
    try:
        import backend.bobserve_fetcher as _bobserve_fetcher
        import backend.bobserve_parser as _bobserve_parser
    except ImportError as exc:
        return jsonify({"error": "module_unavailable", "message": str(exc)}), 503

    if _bobserve_fetcher.get_status()["running"]:
        return jsonify({"error": "fetch_running"}), 409

    body = request.get_json(silent=True) or {}
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        summary = _bobserve_parser.run_parse(file=body.get("file"))
    except Exception as exc:
        _log.exception("bobserve_parse route failed")
        database.record_step_run(
            "bobserve_parse", status="error", started_at=started_at,
            trigger_source="route",
        )
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    database.record_step_run(
        "bobserve_parse", status="ok", started_at=started_at,
        counters=summary, trigger_source="route",
    )
    return jsonify({"ok": True, **summary})


@bp.route("/api/refresh/chain/preview", methods=["POST"])
def refresh_chain_preview() -> Response:
    """Preview the ordered chain plan_chain() would run.

    Body: {step_id?, trigger?, all?, include_expensive?}. Exactly one of
    step_id/trigger/all is required. Read-only -- claims nothing, starts
    nothing, so the GUI can call this on every keystroke of a dialog.
    """
    import backend.refresh_exec as _refresh_exec

    body = request.get_json(silent=True) or {}
    try:
        plan = _refresh_exec.plan_chain(
            step_id=body.get("step_id"), trigger=body.get("trigger"),
            all_steps=bool(body.get("all", False)),
            include_expensive=bool(body.get("include_expensive", False)),
        )
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    return jsonify(plan)


@bp.route("/api/refresh/chain/start", methods=["POST"])
def refresh_chain_start() -> Response:
    """Re-plan server-side and start the chain thread. Body: {step_id?, trigger?, all?, include_expensive?}.

    Re-plans from the posted body rather than trusting a client-side
    plan (spec Sec 3.4) -- the client's plan may be seconds stale.
    409s when the re-plan finds anything in ``blocked_by_running`` or
    the chain job is already claimed by another run; ``{"status":
    "noop"}`` when nothing is left to run.
    """
    import backend.refresh_exec as _refresh_exec

    body = request.get_json(silent=True) or {}
    try:
        plan = _refresh_exec.plan_chain(
            step_id=body.get("step_id"), trigger=body.get("trigger"),
            all_steps=bool(body.get("all", False)),
            include_expensive=bool(body.get("include_expensive", False)),
        )
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400

    if plan["blocked_by_running"]:
        return jsonify({
            "error": "blocked_by_running",
            "blocked_by_running": plan["blocked_by_running"],
        }), 409

    if not plan["runnable"]:
        return jsonify({"status": "noop"})

    if not _refresh_exec.try_begin(stage="queued"):
        return jsonify({"error": "already_running"}), 409

    threading.Thread(
        target=_refresh_exec.run_chain_claimed,
        kwargs={"plan": plan},
        daemon=True, name="refresh-chain",
    ).start()
    return jsonify({
        "status": "started",
        "steps": [item["step_id"] for item in plan["runnable"]],
    })


@bp.route("/api/refresh/chain/status", methods=["GET"])
def refresh_chain_status() -> Response:
    """Return the running chain's progress snapshot, including sub_progress."""
    import backend.refresh_exec as _refresh_exec
    return jsonify(_refresh_exec.get_status())


@bp.route("/api/refresh/chain/stop", methods=["POST"])
def refresh_chain_stop() -> Response:
    """Request that the active chain stop as soon as possible."""
    import backend.refresh_exec as _refresh_exec
    _refresh_exec.stop()
    return jsonify(_refresh_exec.get_status())


@bp.route("/api/refresh/chain/history", methods=["GET"])
def refresh_chain_history() -> Response:
    """Return refresh_chain_runs rows, newest first. Query: ?limit= (default 10)."""
    limit = request.args.get("limit", default=10, type=int)
    rows = database.get_connection().execute(
        """SELECT id, scope_kind, scope_value, started_at, finished_at, status,
                      steps_json, notes
               FROM refresh_chain_runs ORDER BY started_at DESC, id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    history = []
    for row in rows:
        entry = dict(row)
        if entry.get("steps_json"):
            try:
                entry["steps"] = json.loads(entry["steps_json"])
            except (TypeError, ValueError):
                entry["steps"] = None
        else:
            entry["steps"] = None
        del entry["steps_json"]
        history.append(entry)
    return jsonify(history)


@bp.route("/api/ranker/scan", methods=["POST"])
def ranker_scan_run() -> Response:
    """Plan + start a ranker scan. Body: {mode?, lb?, workers?, notes?}.

    mode defaults to 'backlog' (decision 1) — a full rescan needs an
    explicit {mode:'all'}. Claims the job, then calls plan_scan() (fast,
    synchronous) before starting the scan thread; an empty backlog
    finishes the claim immediately and returns 'noop' rather than
    starting a thread for nothing.
    """
    import backend.ranker_jobs as _ranker_jobs

    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "backlog")
    if mode not in ("backlog", "all"):
        return jsonify({"error": "bad_request",
                        "message": "mode must be 'backlog' or 'all'"}), 400
    lbs = body.get("lb")
    if not _ranker_jobs.try_begin(stage="queued", mode=mode):
        return jsonify({"error": "already_running"}), 409
    try:
        plan = _ranker_jobs.plan_scan(mode=mode, lbs=lbs)
    except Exception as exc:
        _ranker_jobs.finish(stage="error")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    if plan["planned"] == 0:
        _ranker_jobs.finish(stage="done")
        return jsonify({
            "status": "noop", "scan_id": plan["scan_id"], "planned": 0,
            "reused_scan": plan["reused_scan"], "config_changed": plan["config_changed"],
        })
    threading.Thread(
        target=_ranker_jobs.run_scan_claimed,
        kwargs={
            "worklist": plan["worklist"], "scan_id": plan["scan_id"],
            "workers": body.get("workers"),
        },
        daemon=True, name="ranker-scan",
    ).start()
    return jsonify({
        "status": "started", "scan_id": plan["scan_id"], "planned": plan["planned"],
        "reused_scan": plan["reused_scan"], "config_changed": plan["config_changed"],
    })


@bp.route("/api/ranker/scan/status", methods=["GET"])
def ranker_scan_status() -> Response:
    """Return the current ranker-scan job's progress snapshot."""
    import backend.ranker_jobs as _ranker_jobs
    return jsonify(_ranker_jobs.get_status())


@bp.route("/api/ranker/scan/stop", methods=["POST"])
def ranker_scan_stop() -> Response:
    """Request that the active ranker-scan job stop as soon as possible."""
    import backend.ranker_jobs as _ranker_jobs
    _ranker_jobs.stop()
    return jsonify(_ranker_jobs.get_status())


@bp.route("/api/ranker/rerank", methods=["POST"])
def ranker_rerank_run() -> Response:
    """Re-band/rank from stored metrics only. Body: {scan_id?}.

    Synchronous, pure-DB (unlike scan, this needs no thread). 409s while
    a scan is running so it doesn't race the scan's own trailing rerank.
    """
    import backend.ranker_jobs as _ranker_jobs

    if _ranker_jobs.get_status().get("running"):
        return jsonify({"error": "scan_running"}), 409
    body = request.get_json(silent=True) or {}
    try:
        result = _ranker_jobs.run_rerank(scan_id=body.get("scan_id"))
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/lb_master/<int:lb>", methods=["GET"])
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


@bp.route("/api/lb_master/<int:lb>/live", methods=["GET"])
def lb_master_live(lb: int) -> Response:
    """Check live on the LB site whether this LB has a public detail page.

    Read-only (no DB write). tools/lb_nc.py calls it before moving a folder
    that is private or sits in the private folder, and refuses the move
    unless ``exists`` is true.

    Returns:
        JSON {lb_number, url, exists: true|false|null, status}; null means
        the site could not be reached.
    """
    try:
        from backend.scraper import probe_detail_page
        return jsonify(probe_detail_page(lb))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_master", methods=["GET"])
def lb_master_list() -> Response:
    """Return paginated lb_master rows.

    Query params: status (public|private|missing|nonexistent), override=1, review=1,
                  limit (default 500), offset (default 0).
    """
    try:
        status = request.args.get("status") or None
        if status and status not in ("public", "private", "missing", "nonexistent"):  # #6
            return jsonify({"error": "invalid_status",
                            "message": "status must be public, private, missing, "
                                           "or nonexistent"}), 400
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


@bp.route("/api/lb_master/reconcile", methods=["POST"])
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


@bp.route("/api/lb_master/history/<int:lb>", methods=["GET"])
def lb_master_history(lb: int) -> Response:
    """Return transition history for an LB, newest first."""
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 500))  # #7
        rows = database.get_lb_status_history(lb, limit=limit)
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_master/<int:lb>/manual", methods=["PUT"])
def lb_master_set_manual(lb: int) -> Response:
    """Set a manual override. Body: {status, notes}."""
    try:
        body = request.get_json(silent=True) or {}
        status = body.get("status")
        notes = str(body.get("notes", ""))[:1000]  # #11
        if status not in ("public", "private", "missing", "nonexistent"):
            return jsonify({"error": "status must be public, private, missing, "
                                         "or nonexistent"}), 400
        database.set_lb_manual_override(lb, status, notes)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_master/<int:lb>/manual", methods=["DELETE"])
def lb_master_clear_manual(lb: int) -> Response:
    """Clear a manual override and immediately reconcile."""
    try:
        new_status = database.clear_lb_manual_override(lb)
        return jsonify({"ok": True, "new_status": new_status})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_master/overrides/export", methods=["GET"])
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


@bp.route("/api/lb_master/overrides/import", methods=["POST"])
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


@bp.route("/api/lb_master/<int:lb>/nft", methods=["GET"])
def lb_master_nft(lb: int) -> Response:
    """Return {nft: bool, reason: str|null} for folder naming guidance."""
    try:
        status = database.get_lb_status(lb)
        nft = status == "private"
        reason = "private" if nft else None
        return jsonify({"nft": nft, "reason": reason})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
