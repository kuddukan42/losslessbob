"""Taper attribution read/curator API, curation console + workbench, QC review console, master taper vocabulary and known-taper alias admin routes (TODO-369)."""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend import taper_attribution as _taper_attribution
from backend import taper_curation as _taper_curation
from backend.qc import decisions as _qc_decisions
from backend.qc import jobs as _qc_jobs
from backend.qc import review as _qc_review

_log = logging.getLogger(__name__)

bp = Blueprint("tapers", __name__)


# ── Taper attribution read API (FABLE_TAPER_ATTRIBUTION phase 2 §5) ─────────
# Read-only, no curator gate — confirm/reject below are the only gated actions.

@bp.route("/api/tapers/attributions/<int:lb>", methods=["GET"])
def taper_attribution_for_lb(lb: int) -> Response:
    """Return this LB's taper attribution for the DetailPanel's lazy fetch.

    Mirrors ``GET /api/picks/for/<lb>``'s response/error style (F3). Unlike
    the picks route, absence is a normal 200 with ``attribution: null``
    rather than 204, since the caller needs the ``lb_number`` echoed back
    either way for cache bookkeeping.
    """
    try:
        row = _taper_attribution.get_attribution_for_lb(lb)
        return jsonify({"lb_number": lb, "attribution": row})
    except Exception as exc:
        _log.exception("taper_attribution_for_lb failed for LB-%s", lb)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/attributions", methods=["GET"])
def taper_attributions_list() -> Response:
    """Filtered list of taper attributions with parsed evidence (spec §5).

    Read-only, no curator gate. Query params (all optional):
        confidence: restrict to 'confirmed' / 'propagated' / 'inferred'.
        taper: restrict to one taper (raw or canonical; normalised here).
        conflict: '1' (or 'true') restricts to conflict=1 rows only.
        kind: sub-classify conflicts — 'mention' drops series-vs-series
            (the /taper-review hand queue), 'series' keeps only them
            (TODO-234 family-split leads).
    """
    try:
        conflict_arg = request.args.get("conflict")
        conflict = conflict_arg.lower() in ("1", "true") if conflict_arg else None
        kind_arg = (request.args.get("kind") or "").lower() or None
        if kind_arg not in (None, "mention", "series"):
            return jsonify({"error": "bad_request",
                            "message": "kind must be 'mention' or 'series'"}), 400
        rows = _taper_attribution.list_attributions(
            confidence=request.args.get("confidence") or None,
            taper=request.args.get("taper") or None,
            conflict=conflict,
            conflict_kind=kind_arg,
        )
        return jsonify({"attributions": rows})
    except Exception as exc:
        _log.exception("taper_attributions_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── Taper attribution curator API (FABLE_TAPER_ATTRIBUTION phase 2, F2) ─────

@bp.route("/api/tapers/attributions/<int:lb>/confirm", methods=["POST"])
def taper_attribution_confirm(lb: int) -> Response:
    """Curator-only. Confirm this LB's taper attribution immediately.

    Body: {taper?} — raw or canonical taper name. If omitted, taken from
    the entry's existing taper_attributions row. Writes a sticky
    'confirm' row to the MASTER-tier taper_confirmations table
    (overwriting any prior decision for this lb) and applies it to
    taper_attributions right away, without waiting for a full
    /api/derived/recompute run.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        body = request.get_json(silent=True) or {}
        row = _taper_attribution.confirm(lb, taper=body.get("taper"))
        return jsonify({"lb_number": lb, "attribution": row})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_attribution_confirm failed for LB-%s", lb)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/attributions/<int:lb>/reject", methods=["POST"])
def taper_attribution_reject(lb: int) -> Response:
    """Curator-only. Reject this LB's taper attribution immediately.

    Body: {taper?} — raw or canonical taper name being rejected. If
    omitted, taken from the entry's existing taper_attributions row.
    Writes a sticky 'reject' row to the MASTER-tier taper_confirmations
    table (overwriting any prior decision for this lb) and, if the
    current taper_attributions row matches, deletes it right away —
    future /api/derived/recompute runs stay suppressed via
    taper_confirmations regardless.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        body = request.get_json(silent=True) or {}
        row = _taper_attribution.reject(lb, taper=body.get("taper"))
        return jsonify({"lb_number": lb, "attribution": row})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_attribution_reject failed for LB-%s", lb)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/attributions/<int:lb>/unresolved", methods=["POST"])
def taper_attribution_unresolved(lb: int) -> Response:
    """Curator-only. Mark this LB's taper conflict as undecidable.

    For a genuine historical conflict (the same recording documented with
    two different tapers, no ground truth to pick), records a sticky
    'unresolved' decision in taper_confirmations and drops the current
    taper_attributions row — the entry leaves the review queue and shows no
    taper, rather than a guessed one. Reversible via a later confirm/reject.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        row = _taper_attribution.mark_unresolved(lb)
        return jsonify({"lb_number": lb, "attribution": row})
    except Exception as exc:
        _log.exception("taper_attribution_unresolved failed for LB-%s", lb)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── Taper curation console (TODO-312) ───────────────────────────────────────
# Backs the three tabs of /taper-review. Reads are open (matching the
# attribution read routes above); the bulk and revert writes are curator-gated
# exactly like the single-LB confirm/reject/unresolved routes.

def _review_args() -> dict:
    """Parse the filter query params shared by the two review read routes.

    Returns:
        Kwargs for taper_attribution.list_review_rows / taper_rollup.

    Raises:
        ValueError: A param has an unusable value (surfaced as a 400).
    """
    conflict_arg = request.args.get("conflict")
    attributed_arg = request.args.get("attributed")
    return {
        "state": request.args.get("state") or None,
        "confidence": request.args.get("confidence") or None,
        "conflict": (conflict_arg.lower() in ("1", "true")) if conflict_arg else None,
        "taper": request.args.get("taper") or None,
        "q": request.args.get("q") or None,
        "attributed": ((attributed_arg.lower() in ("1", "true"))
                       if attributed_arg else None),
    }


@bp.route("/api/tapers/review", methods=["GET"])
def taper_review_rows() -> Response:
    """One page of the curation console's entry view, with facet counts.

    Query params (all optional): state (any/undecided/confirm/reject/
    unresolved), confidence, conflict, kind (mention/series), taper, q,
    attributed (1/0 — 0 surfaces entries with no attribution at all),
    limit (default 100, max 500), offset, sort (lb/date/taper/confidence,
    '-' prefix to descend).
    """
    try:
        args = _review_args()
        result = _taper_attribution.list_review_rows(
            conflict_kind=(request.args.get("kind") or "").lower() or None,
            limit=request.args.get("limit", type=int, default=100),
            offset=request.args.get("offset", type=int, default=0),
            sort=request.args.get("sort") or "lb",
            **args,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_review_rows failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/review/tapers", methods=["GET"])
def taper_review_rollup() -> Response:
    """Per-taper rollup for the console's grouped view (same filters, no taper)."""
    try:
        args = _review_args()
        args.pop("taper", None)
        args.pop("attributed", None)
        return jsonify({"tapers": _taper_attribution.taper_rollup(**args)})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_review_rollup failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── Taper curation workbench (/taper-curation) ────────────────────────────
# A wider read model than /api/tapers/review: every source that has an
# opinion about a recording's taper (LB text, parser, attribution engine,
# TUIT, TapeMatch family) in one row. Read-only — the workbench posts its
# decisions to the curator-gated attribution/vocabulary routes above.

@bp.route("/api/tapers/curation", methods=["GET"])
def taper_curation_rows() -> Response:
    """One page of the curation workbench.

    Query params (all optional): state, confidence ('none' = unattributed),
    conflict, taper, q, attributed, tuit (scraped/not_scraped/has_taper/
    taper_only), family (has/none/review), agreement, limit (max 500),
    offset, sort (lb/date/taper/confidence/similarity, '-' to descend).
    """
    try:
        conflict_arg = request.args.get("conflict")
        attributed_arg = request.args.get("attributed")
        return jsonify(_taper_curation.list_rows(
            state=request.args.get("state") or None,
            confidence=request.args.get("confidence") or None,
            conflict=((conflict_arg.lower() in ("1", "true"))
                      if conflict_arg else None),
            taper=request.args.get("taper") or None,
            q=request.args.get("q") or None,
            attributed=((attributed_arg.lower() in ("1", "true"))
                        if attributed_arg else None),
            tuit=request.args.get("tuit") or None,
            family=request.args.get("family") or None,
            agreement_filter=request.args.get("agreement") or None,
            limit=request.args.get("limit", type=int, default=50),
            offset=request.args.get("offset", type=int, default=0),
            sort=request.args.get("sort") or "lb",
        ))
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_curation_rows failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/curation/tuit_candidates", methods=["GET"])
def taper_curation_tuit_candidates() -> Response:
    """Recordings where TUIT names a taper and entries names none (TODO-339).

    Read-only candidate evidence with TUIT provenance. Query params:
    include_decided (1/true), limit, offset.
    """
    try:
        inc = (request.args.get("include_decided") or "").lower() in ("1", "true")
        return jsonify(_taper_curation.tuit_candidates(
            include_decided=inc,
            limit=request.args.get("limit", type=int, default=1000),
            offset=request.args.get("offset", type=int, default=0),
        ))
    except Exception as exc:
        _log.exception("taper_curation_tuit_candidates failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/curation/isolated", methods=["GET"])
def taper_curation_isolated() -> Response:
    """Texts that never became a taper credit, grouped by canonical.

    Query params: kind (excluded/unknown), q, limit (default 200),
    refresh=1 to rebuild the cached description scan.
    """
    try:
        return jsonify(_taper_curation.isolated_texts(
            kind=request.args.get("kind") or None,
            q=request.args.get("q") or None,
            limit=request.args.get("limit", type=int, default=200),
            refresh=request.args.get("refresh") in ("1", "true"),
        ))
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_curation_isolated failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/curation/tapers", methods=["GET"])
def taper_curation_rollup() -> Response:
    """Per-canonical rollup across attribution, curator decisions and TUIT."""
    try:
        return jsonify({"tapers": _taper_curation.taper_rollup()})
    except Exception as exc:
        _log.exception("taper_curation_rollup failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── QC review console (/qc-review, TODO-342 Phase 2b, experimental) ───────
# Reads (C11) are open — no curator guard. Writes (C12, below) — decisions,
# bulk decisions, corrections, and starting a rules run — are curator-only,
# the same `database.is_curator()` -> 403 `curator_required` guard as
# /api/tapers/attributions/<lb>/confirm.

@bp.route("/api/qc/summary", methods=["GET"])
def qc_summary() -> Response:
    """Per-rule counts by severity x status, last run per rule, open totals."""
    try:
        return jsonify(_qc_review.summary())
    except Exception as exc:
        _log.exception("qc_summary failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/findings", methods=["GET"])
def qc_findings_list() -> Response:
    """Paged QC findings list.

    Query params (all optional): rule, severity, status, entity_kind,
    date (ISO, matches an affected dossier date), q, page, page_size
    (max 200).
    """
    try:
        return jsonify(_qc_review.list_findings(
            rule=request.args.get("rule") or None,
            severity=request.args.get("severity") or None,
            status=request.args.get("status") or None,
            entity_kind=request.args.get("entity_kind") or None,
            date=request.args.get("date") or None,
            q=request.args.get("q") or None,
            page=request.args.get("page", type=int, default=1),
            page_size=request.args.get("page_size", type=int, default=50),
        ))
    except Exception as exc:
        _log.exception("qc_findings_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/findings/<int:finding_id>", methods=["GET"])
def qc_finding_detail(finding_id: int) -> Response:
    """One finding: its evidence, rule-family context panel, affected dates."""
    try:
        finding = _qc_review.get_finding(finding_id)
    except Exception as exc:
        _log.exception("qc_finding_detail failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    if finding is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(finding)


@bp.route("/api/qc/decisions", methods=["GET"])
def qc_decisions_list() -> Response:
    """Paged qc_decision_log, newest first.

    Query params: page, page_size (max 200), finding_id (restrict to one
    finding's history).
    """
    try:
        return jsonify(_qc_review.list_decisions(
            page=request.args.get("page", type=int, default=1),
            page_size=request.args.get("page_size", type=int, default=50),
            finding_id=request.args.get("finding_id", type=int),
        ))
    except Exception as exc:
        _log.exception("qc_decisions_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/findings/<int:finding_id>/decision", methods=["POST"])
def qc_finding_decision(finding_id: int) -> Response:
    """Curator-only. Decide one finding: confirmed or false_positive.

    Body: {status: 'confirmed'|'false_positive', note?}.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in ("confirmed", "false_positive"):
        return jsonify({"error": "bad_request",
                         "message": "status must be confirmed or false_positive"}), 400
    try:
        conn = database.get_connection()
        finding = _qc_decisions.decide(conn, finding_id, status, note=body.get("note"))
        return jsonify({"finding": finding})
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("no such finding"):
            return jsonify({"error": "not_found", "message": msg}), 404
        return jsonify({"error": "illegal_transition", "message": msg}), 409
    except Exception as exc:
        _log.exception("qc_finding_decision failed for finding %s", finding_id)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/findings/bulk", methods=["POST"])
def qc_findings_bulk() -> Response:
    """Curator-only. Decide many findings at once, one rule per batch.

    Body: {ids: [int, ...], status: 'confirmed'|'false_positive', note?}.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    status = body.get("status")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "bad_request", "message": "ids must be a non-empty list"
                             " of integers"}), 400
    if status not in ("confirmed", "false_positive"):
        return jsonify({"error": "bad_request",
                         "message": "status must be confirmed or false_positive"}), 400
    try:
        conn = database.get_connection()
        findings = _qc_decisions.bulk_decide(conn, ids, status, note=body.get("note"))
        return jsonify({"findings": findings})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("qc_findings_bulk failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/corrections", methods=["POST"])
def qc_corrections_create() -> Response:
    """Curator-only. Record a field correction and mark its finding corrected.

    Body: {finding_id: int, field: str, corrected: str, reason?, original?}.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    finding_id = body.get("finding_id")
    field = body.get("field")
    corrected = body.get("corrected")
    if not isinstance(finding_id, int) or not field or corrected is None:
        return jsonify({"error": "bad_request",
                         "message": "finding_id, field and corrected are required"}), 400
    try:
        conn = database.get_connection()
        result = _qc_decisions.add_correction(
            conn, finding_id, field, corrected,
            reason=body.get("reason"), original=body.get("original"),
        )
        return jsonify(result)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("no such finding"):
            return jsonify({"error": "not_found", "message": msg}), 404
        return jsonify({"error": "illegal_transition", "message": msg}), 409
    except Exception as exc:
        _log.exception("qc_corrections_create failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/releases/<title_key>", methods=["POST"])
def qc_release_classify(title_key: str) -> Response:
    """Curator-only. Classify one release title (D-03 R-R1). Body: {official: bool, note?}."""
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    official = body.get("official")
    if not isinstance(official, bool):
        return jsonify({"error": "bad_request", "message": "official must be a bool"}), 400
    try:
        conn = database.get_connection()
        result = _qc_decisions.classify_release(
            conn, title_key, official, note=body.get("note"),
        )
        return jsonify(result)
    except Exception as exc:
        _log.exception("qc_release_classify failed for %s", title_key)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/qc/run", methods=["POST"])
def qc_run_start() -> Response:
    """Curator-only. Start a rules run (all rules, or one via body {rule_id?})."""
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    rule_id = body.get("rule_id") or None
    try:
        started = _qc_jobs.start(rule_id=rule_id)
    except KeyError:
        return jsonify({"error": "bad_request",
                         "message": f"no such rule: {rule_id}"}), 400
    except Exception as exc:
        _log.exception("qc_run_start failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
    if not started:
        return jsonify({"error": "run_active", "message": "a rules run is already active"}
                        ), 409
    return jsonify(_qc_jobs.get_status())


@bp.route("/api/qc/run", methods=["GET"])
def qc_run_status() -> Response:
    """Poll the active/last rules run's progress."""
    return jsonify(_qc_jobs.get_status())


@bp.route("/api/tapers/decisions", methods=["GET"])
def taper_decisions_list() -> Response:
    """Decision history from taper_decision_log, newest first.

    Query params: lb (restrict to one entry), limit (default 200, max 1000).
    """
    try:
        return jsonify({"decisions": _taper_attribution.list_decisions(
            lb=request.args.get("lb", type=int),
            limit=request.args.get("limit", type=int, default=200),
        )})
    except Exception as exc:
        _log.exception("taper_decisions_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/attributions/bulk", methods=["POST"])
def taper_attribution_bulk() -> Response:
    """Curator-only. Apply one decision to many LBs (console multi-select).

    Body: {action: 'confirm'|'reject'|'unresolved', lbs: [int, ...],
    taper?, note?}. Each LB is applied independently and its outcome
    reported, so one bad row (e.g. a taper outside the known-taper
    universe) does not sink the rest of the batch.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").lower()
    if action not in ("confirm", "reject", "unresolved"):
        return jsonify({"error": "bad_request",
                        "message": "action must be confirm/reject/unresolved"}), 400
    lbs = body.get("lbs")
    if not isinstance(lbs, list) or not lbs:
        return jsonify({"error": "bad_request", "message": "lbs must be a non-empty list"}), 400
    cap = _taper_attribution.REVIEW_MAX_LIMIT
    if len(lbs) > cap:
        return jsonify({"error": "bad_request",
                        "message": f"at most {cap} lbs per batch"}), 400
    taper, note = body.get("taper"), body.get("note")
    results, ok_count = [], 0
    for raw in lbs:
        try:
            lb = int(raw)
        except (TypeError, ValueError):
            results.append({"lb": raw, "ok": False, "error": "not an LB number"})
            continue
        try:
            if action == "confirm":
                _taper_attribution.confirm(lb, taper=taper, source="bulk", note=note)
            elif action == "reject":
                _taper_attribution.reject(lb, taper=taper, source="bulk", note=note)
            else:
                _taper_attribution.mark_unresolved(lb, source="bulk", note=note)
            results.append({"lb": lb, "ok": True})
            ok_count += 1
        except ValueError as exc:
            results.append({"lb": lb, "ok": False, "error": str(exc)})
        except Exception as exc:
            _log.exception("bulk %s failed for LB-%s", action, lb)
            results.append({"lb": lb, "ok": False, "error": str(exc)})
    return jsonify({"results": results, "ok_count": ok_count,
                    "fail_count": len(results) - ok_count})


@bp.route("/api/tapers/decisions/<int:log_id>/revert", methods=["POST"])
def taper_decision_revert(log_id: int) -> Response:
    """Curator-only. Undo one logged decision, restoring its recorded prior state."""
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        return jsonify(_taper_attribution.revert_decision(log_id))
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_decision_revert failed for log #%s", log_id)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── Master taper vocabulary curation (TODO-313) ─────────────────────────────
# Canonical-keyed counterpart to the alias-keyed admin below: the unit here is
# "is this person a taper" / "are these two names the same person", which the
# flat alias table cannot express. Read open, writes curator-gated, matching
# the rest of the taper API. Every write reloads the merged alias tables, so
# `_TAPER_UNIVERSE` is live immediately; attributions only catch up on the
# next /api/derived/recompute, which the responses flag.

@bp.route("/api/tapers/vocabulary", methods=["GET"])
def taper_vocabulary_list() -> Response:
    """The canonical-centric master taper list with aliases and usage counts."""
    try:
        return jsonify(database.list_taper_vocabulary())
    except Exception as exc:
        _log.exception("taper_vocabulary_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/vocabulary", methods=["POST"])
def taper_vocabulary_create() -> Response:
    """Curator-only. Register a brand-new canonical taper.

    Body: {name, note?}. A new taper is just an alias whose canonical is
    itself, so this delegates to add_taper_alias rather than inventing a
    second way for a name to enter the vocabulary.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "bad_request", "message": "name is required"}), 400
    try:
        row = database.add_taper_alias(name, name, note=body.get("note"))
        _taper_attribution._rebuild_alias_index()
        return jsonify({"created": row})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_vocabulary_create failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/vocabulary/<path:canonical>/flag", methods=["POST"])
def taper_vocabulary_flag(canonical: str) -> Response:
    """Curator-only. Set or clear the not-a-taper judgement on a canonical.

    Body: {is_taper: bool, note?} to set, or {clear: true} to drop a local
    override and fall back to the shipped `_NOT_TAPER` default.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    try:
        if body.get("clear"):
            result = database.clear_taper_flag(canonical)
        else:
            if "is_taper" not in body:
                return jsonify({"error": "bad_request",
                                "message": "is_taper (bool) or clear:true required"}), 400
            result = database.set_taper_flag(
                canonical, bool(body["is_taper"]), note=body.get("note"))
        _taper_attribution._rebuild_alias_index()
        # Excluding a taper does not retract attributions already computed
        # under it; only a recompute does.
        result["needs_recompute"] = True
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_vocabulary_flag failed for %s", canonical)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/vocabulary/merge", methods=["POST"])
def taper_vocabulary_merge() -> Response:
    """Curator-only. Merge one canonical into another (or rename it).

    Body: {source, target}. Repoints every alias of source at target and
    carries `taper_confirmations` across; derived attributions catch up on
    the next recompute (see `attributions_pending` in the response).
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    try:
        result = database.merge_tapers(body.get("source"), body.get("target"))
        _taper_attribution._rebuild_alias_index()
        result["needs_recompute"] = result["attributions_pending"] > 0
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_vocabulary_merge failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


# ── Known-taper alias admin (TODO-241) ──────────────────────────────────────
# UI/CLI conduit to add/remove known-taper handles without a code edit. See
# backend.db.{list,add,remove}_taper_alias / reload_taper_aliases and the
# "Taper aliases" section on /taper-review. Read is open (matches the
# attributions list route above); add/remove are curator-gated, matching
# confirm/reject/unresolved above — both redefine the shared known-taper
# vocabulary, not just one LB's attribution.

@bp.route("/api/tapers/aliases", methods=["GET"])
def taper_aliases_list() -> Response:
    """Merged known-taper alias table: builtin + approved user overrides.

    Returns entries (each tagged ``origin: "builtin"|"user"``), the list
    of builtin keys currently suppressed by a user 'remove' row, and
    counts. Powers the /taper-review "Taper aliases" admin section.
    """
    try:
        return jsonify(database.list_taper_aliases())
    except Exception as exc:
        _log.exception("taper_aliases_list failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/aliases", methods=["POST"])
def taper_aliases_add() -> Response:
    """Curator-only. Add or override one known-taper alias.

    Body: {alias, canonical, note?}. Upserts a 'add' row in
    user_taper_aliases, reloads backend.db's merged alias tables, and
    rebuilds taper_attribution's alias reverse index so both take effect
    immediately (a later /api/derived/recompute is what actually re-scores
    existing entries against the new alias).
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    body = request.get_json(silent=True) or {}
    alias = body.get("alias")
    canonical = body.get("canonical")
    if not alias or not str(alias).strip() or not canonical or not str(canonical).strip():
        return jsonify({"error": "bad_request",
                         "message": "alias and canonical are required"}), 400
    try:
        row = database.add_taper_alias(alias, canonical, note=body.get("note"))
        _taper_attribution._rebuild_alias_index()
        return jsonify({"alias": row})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("taper_aliases_add failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapers/aliases/<path:alias>", methods=["DELETE"])
def taper_aliases_remove(alias: str) -> Response:
    """Curator-only. Remove a user alias, or suppress a builtin one.

    If *alias* is a user 'add' row, deletes it outright. If *alias* is a
    builtin key, upserts a 'remove' row to suppress it locally (the
    builtin table is code, never edited). 404 if *alias* is neither.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        result = database.remove_taper_alias(alias)
        _taper_attribution._rebuild_alias_index()
        return jsonify({"alias": alias, "result": result})
    except KeyError:
        return jsonify({"error": "not_found",
                         "message": f"{alias!r} is not a known alias"}), 404
    except Exception as exc:
        _log.exception("taper_aliases_remove failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500
