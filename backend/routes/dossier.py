"""Show dossier routes (TODO-369)."""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
)

from backend import dossier as _dossier

_log = logging.getLogger(__name__)

bp = Blueprint("dossier", __name__)


# ── Show dossier (TODO-257, instructions/FABLE_SHOW_DOSSIER.md) ────────────

@bp.route("/api/dossier", methods=["GET"])
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


@bp.route("/api/dossier/html", methods=["GET"])
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


@bp.route("/api/dossier/bbcode", methods=["GET"])
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
