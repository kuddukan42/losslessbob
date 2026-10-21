"""lb_alias and folder_lb_link routes (TODO-369)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("aliases", __name__)


# ── lb_alias endpoints ────────────────────────────────────────────────────

@bp.route("/api/lb_alias", methods=["GET"])
def lb_alias_list():
    """List all lb_alias rows, optionally filtered by canonical_lb.

    Query param: canonical_lb (int, optional)
    """
    try:
        canonical = request.args.get("canonical_lb", type=int)
        return jsonify(database.get_lb_aliases(canonical))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_alias", methods=["POST"])
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


@bp.route("/api/lb_alias/<int:alias_lb>", methods=["DELETE"])
def lb_alias_delete(alias_lb):
    """Remove an alias entry. Curator-only."""
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        database.delete_lb_alias(alias_lb)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_alias/resolve", methods=["GET"])
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

@bp.route("/api/folder_link", methods=["GET"])
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


@bp.route("/api/folder_link", methods=["PUT"])
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


@bp.route("/api/folder_link", methods=["DELETE"])
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
