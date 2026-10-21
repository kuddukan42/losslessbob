"""Archive.org upload routes: credentials, test, upload/status/stop, upload history (TODO-369)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import archive_org as _archive_org
from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("archive_org", __name__)


# ── Archive.org Upload ────────────────────────────────────────────────────

@bp.route("/api/archive_org/credentials", methods=["POST"])
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


@bp.route("/api/archive_org/credentials", methods=["GET"])
def archive_org_check_credentials():
    """Return whether archive.org credentials are stored.

    Returns: {stored: bool}
    """
    from backend.credentials import SERVICE_IA, credentials_stored
    return jsonify({"stored": credentials_stored(SERVICE_IA)})


@bp.route("/api/archive_org/credentials", methods=["DELETE"])
def archive_org_delete_credentials():
    """Clear stored archive.org credentials.

    Returns: {ok: bool}
    """
    from backend.credentials import SERVICE_IA, delete_credentials
    delete_credentials(SERVICE_IA)
    return jsonify({"ok": True})


@bp.route("/api/archive_org/test", methods=["POST"])
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


@bp.route("/api/archive_org/upload", methods=["POST"])
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


@bp.route("/api/archive_org/status", methods=["GET"])
def archive_org_status():
    """Return current archive.org upload progress.

    Returns: {running, lb_number, identifier, current_file, files_done,
              files_total, bytes_done, bytes_total, status, error, stop_requested}
    """
    return jsonify(_archive_org.get_status())


@bp.route("/api/archive_org/stop", methods=["POST"])
def archive_org_stop():
    """Request the running archive.org upload to stop after the current file.

    Returns: {ok}
    """
    _archive_org.stop_upload()
    return jsonify({"ok": True})


@bp.route("/api/archive_org/uploads", methods=["GET"])
def archive_org_uploads():
    """Return archive upload history rows, newest first.

    Query params: lb=<int> to filter by LB number.
    Returns: [{id, lb_number, identifier, folder_path, files_total,
               files_uploaded, status, started_at, finished_at, error,
               date_str?, location?}]
    """
    lb = request.args.get("lb", type=int)
    return jsonify(database.get_archive_uploads(lb_number=lb))
