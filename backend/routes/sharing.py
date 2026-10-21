"""File-sharing routes: create/list/revoke shares, file/zip downloads, tunnel status (TODO-369)."""

import logging
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    request,
    send_file,
    stream_with_context,
)

from backend import db as database
from backend import sharing

_log = logging.getLogger(__name__)

bp = Blueprint("sharing", __name__)


@bp.route("/api/share/create", methods=["POST"])
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


@bp.route("/api/share/<token>/", methods=["GET"])
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


@bp.route("/api/share/<token>/file/<path:filename>", methods=["GET"])
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


@bp.route("/api/share/<token>/zip", methods=["GET"])
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


@bp.route("/api/share/list", methods=["GET"])
def share_list():
    """Return JSON list of all active shares for GUI status display.

    Returns:
        JSON: [{token, folder_path, files, expires_at, lb_number, tunnel_url}]
    """
    return jsonify(sharing.list_shares())


@bp.route("/api/share/<token>", methods=["DELETE"])
def share_revoke(token):
    """Revoke a share and stop tunnel if no shares remain.

    Args:
        token: Share token.

    Returns:
        JSON: {ok}
    """
    sharing.revoke_share(token)
    return jsonify({"ok": True})


@bp.route("/api/share/tunnel/status", methods=["GET"])
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
