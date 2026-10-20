"""Torrent generation and qBittorrent integration routes."""

import logging
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("torrents", __name__)


# ── Torrent Generation ───────────────────────────────────────────────────

@bp.route("/api/torrent/create", methods=["POST"])
def torrent_create() -> Response:
    """Generate a .torrent for one LB entry.

    Body: {lb_number, source_folder, tracker_list?}
    Returns: {ok, torrent_path, infohash, torrent_id, name, excluded_files}
    """
    try:
        from backend.torrent_maker import make_torrent
        data = request.get_json() or {}
        lb = data.get("lb_number")
        folder = data.get("source_folder", "")
        tracker_list = data.get("tracker_list") or database.get_meta("tracker_list") or "best"
        if not lb or not folder:
            return jsonify({"error": "lb_number and source_folder required"}), 400
        result = make_torrent(int(lb), folder, tracker_list=tracker_list)
        # Null out torrent_path on older sibling records that share the new file path
        # so they stop falsely reporting torrent_file_exists=True.
        database.clear_superseded_torrent_paths(
            int(lb), result["torrent_id"], result["torrent_path"]
        )
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/torrent/<int:lb>", methods=["GET"])
def torrent_list(lb: int) -> Response:
    """List all torrent records for an LB entry."""
    try:
        rows = database.get_torrents_for_lb(lb)
        # Annotate each row with source_folder_exists for the history panel
        for row in rows:
            row["source_folder_exists"] = (
                bool(row.get("source_folder"))
                and Path(row["source_folder"]).is_dir()
            )
            row["torrent_file_exists"] = (
                bool(row.get("torrent_path"))
                and Path(row["torrent_path"]).exists()
            )
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/torrent/<int:torrent_id>", methods=["PATCH"])
def torrent_update(torrent_id: int) -> Response:
    """Update a torrents row (e.g. source_folder after path relocation)."""
    try:
        fields = request.get_json() or {}
        database.update_torrent_record(torrent_id, fields)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/trackers", methods=["GET"])
def trackers_get() -> Response:
    """Return the cached tracker list.

    Query params: list_name, force_refresh (0/1).
    """
    try:
        from backend.torrent_maker import fetch_trackers
        list_name = request.args.get("list_name") or database.get_meta("tracker_list") or "best"
        force = request.args.get("force_refresh", "0") == "1"
        trackers = fetch_trackers(list_name, force_refresh=force)
        return jsonify({"list_name": list_name, "count": len(trackers), "trackers": trackers})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── qBittorrent Integration ───────────────────────────────────────────────

@bp.route("/api/qbt/test", methods=["POST"])
def qbt_test() -> Response:
    """Test qBittorrent WebUI connectivity.

    Body: {host, port, username?, password?, api_key?} — credentials optional (uses keyring).
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import test_connection
        data = request.get_json() or {}
        host = data.get("host") or database.get_meta("qbt_host") or "localhost"
        port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
        api_key = data.get("api_key") or ""
        if not api_key:
            _, api_key = get_credentials(SERVICE_QBT_KEY)
        username = data.get("username") or ""
        password = data.get("password") or ""
        if not api_key and not username:
            username, password = get_credentials(SERVICE_QBT)
        return jsonify(test_connection(host, port, username, password, api_key))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/qbt/add", methods=["POST"])
def qbt_add() -> Response:
    """Add one or more torrents to qBittorrent.

    Body: {torrent_id?, lb_numbers?, host?, port?, username?, password?,
           api_key?, category?, tags?}
    Use torrent_id for a single known record, or lb_numbers to add all
    torrents for those entries (latest record per LB).
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import add_torrent_from_db
        data = request.get_json() or {}
        host = data.get("host") or database.get_meta("qbt_host") or "localhost"
        port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
        category = data.get("category") or database.get_meta("qbt_category") or ""
        tags = data.get("tags") or database.get_meta("qbt_tags") or ""
        api_key = data.get("api_key") or ""
        if not api_key:
            _, api_key = get_credentials(SERVICE_QBT_KEY)
        username = data.get("username") or ""
        password = data.get("password") or ""
        if not api_key and not username:
            username, password = get_credentials(SERVICE_QBT)

        results = []
        if data.get("torrent_id"):
            r = add_torrent_from_db(
                int(data["torrent_id"]), host, port, username, password, category, tags,
                api_key=api_key,
            )
            results.append(r)
        elif data.get("lb_numbers") and len(data["lb_numbers"]) > 1:
            # Bulk: add paused, release in paced background batches (TODO-330).
            from backend import qbt_seeding as qs

            def _cfg(key: str, default: float) -> float:
                return float(data.get(key) or database.get_meta("qbt_" + key) or default)

            ids = []
            for lb in data["lb_numbers"]:
                rows = database.get_torrents_for_lb(int(lb))
                if rows:
                    ids.append(rows[0]["id"])
            res = qs.add_paused(
                ids, host, port, username, password, category, tags, api_key=api_key,
                max_adds=int(_cfg("max_adds", qs.DEFAULT_MAX_ADDS)),
                max_announces=int(_cfg("max_announces", qs.DEFAULT_MAX_ANNOUNCES)),
            )
            if not res["ok"]:
                return jsonify({"ok": False, "error": res["error"]}), 409
            hashes = [r["infohash"] for r in res["results"] if r.get("ok") and r.get("infohash")]
            batch = int(_cfg("batch_size", qs.DEFAULT_BATCH_SIZE))
            interval = _cfg("interval_s", qs.DEFAULT_INTERVAL_S)
            import threading
            threading.Thread(
                target=qs.release_paced,
                args=(hashes, host, port, username, password, api_key, batch, interval),
                daemon=True,
            ).start()
            ok_count = sum(1 for r in res["results"] if r.get("ok"))
            return jsonify({
                "ok": True, "added": ok_count, "total": len(res["results"]),
                "results": res["results"], "skipped": res["skipped"],
                "warning": res.get("warning"), "paced": True,
                "release": {"batch_size": batch, "interval_s": interval,
                            "pending": len(hashes)},
            })
        elif data.get("lb_numbers"):
            for lb in data["lb_numbers"]:
                rows = database.get_torrents_for_lb(int(lb))
                if rows:
                    r = add_torrent_from_db(
                        rows[0]["id"], host, port, username, password, category, tags,
                        api_key=api_key,
                    )
                    results.append({**r, "lb_number": lb})
        else:
            return jsonify({"error": "torrent_id or lb_numbers required"}), 400

        ok_count = sum(1 for r in results if r.get("ok"))
        return jsonify({"ok": True, "added": ok_count, "total": len(results), "results": results})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/qbt/tracker_status", methods=["POST"])
def qbt_tracker_status() -> Response:
    """Per-torrent tracker status. Body: {hashes: [...], host?, port?}."""
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbt_seeding import tracker_status
        data = request.get_json() or {}
        host = data.get("host") or database.get_meta("qbt_host") or "localhost"
        port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
        _, api_key = get_credentials(SERVICE_QBT_KEY)
        username, password = ("", "") if api_key else get_credentials(SERVICE_QBT)
        hashes = [str(h).lower() for h in data.get("hashes") or []]
        return jsonify({"ok": True, "status": tracker_status(
            hashes, host, port, username, password, api_key or "")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/torrent/<int:torrent_id>/qbt_remove", methods=["POST"])
def qbt_remove(torrent_id: int) -> Response:
    """Remove a torrent from qBittorrent (content files are NOT deleted).

    Uses the stored infohash. Clears added_to_qbt on success, and also
    when qBittorrent confirms the torrent is already gone (manual removal).
    Body: {host?, port?, username?, password?, api_key?}
    Returns: {ok, error?}
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import check_torrent_presence, remove_torrent
        data = request.get_json(silent=True) or {}
        host = data.get("host") or database.get_meta("qbt_host") or "localhost"
        port = int(data.get("port") or database.get_meta("qbt_port") or 8080)
        api_key = data.get("api_key") or ""
        if not api_key:
            _, api_key = get_credentials(SERVICE_QBT_KEY)
        username = data.get("username") or ""
        password = data.get("password") or ""
        if not api_key and not username:
            username, password = get_credentials(SERVICE_QBT)

        conn = database.get_connection()
        row = conn.execute(
            "SELECT infohash FROM torrents WHERE id=?", (torrent_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404

        result = remove_torrent(
            infohash=row["infohash"] or "",
            host=host, port=port,
            username=username, password=password, api_key=api_key,
        )
        if result["ok"]:
            database.update_torrent_record(
                torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
            )
        else:
            # Remove failed — check if the torrent is simply already gone from qBittorrent
            # (e.g. user removed it manually). If absent, still clear the DB flag.
            check = check_torrent_presence(
                infohash=row["infohash"] or "",
                host=host, port=port,
                username=username, password=password, api_key=api_key,
            )
            if check.get("ok") and not check.get("present"):
                database.update_torrent_record(
                    torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
                )
                result = {"ok": True}
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/torrent/<int:torrent_id>/qbt_check", methods=["GET"])
def qbt_check(torrent_id: int) -> Response:
    """Check whether a torrent is present in qBittorrent and sync the DB flag.

    Returns: {ok, present, synced, error?}
    synced=True means added_to_qbt was cleared because the torrent was gone.
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
        from backend.qbittorrent import check_torrent_presence
        host = database.get_meta("qbt_host") or "localhost"
        port = int(database.get_meta("qbt_port") or 8080)
        _, api_key = get_credentials(SERVICE_QBT_KEY)
        username, password = "", ""
        if not api_key:
            username, password = get_credentials(SERVICE_QBT)

        conn = database.get_connection()
        row = conn.execute(
            "SELECT infohash, added_to_qbt FROM torrents WHERE id=?", (torrent_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "present": False, "synced": False,
                            "error": f"No torrent record id={torrent_id}"}), 404

        result = check_torrent_presence(
            infohash=row["infohash"] or "",
            host=host, port=port,
            username=username, password=password, api_key=api_key,
        )

        synced = False
        if result.get("ok") and not result.get("present") and row["added_to_qbt"]:
            database.update_torrent_record(
                torrent_id, {"added_to_qbt": 0, "added_to_qbt_at": None}
            )
            synced = True

        return jsonify({**result, "synced": synced})
    except Exception as exc:
        return jsonify({"ok": False, "present": False, "synced": False,
                        "error": str(exc)}), 500


@bp.route("/api/torrent/<int:torrent_id>/file", methods=["DELETE"])
def torrent_file_delete(torrent_id: int) -> Response:
    """Delete the .torrent file from disk and clear torrent_path in the DB.

    Does not remove from qBittorrent.
    Returns: {ok, error?}
    """
    try:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT torrent_path FROM torrents WHERE id=?", (torrent_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404

        torrent_path = row["torrent_path"]
        if torrent_path:
            p = Path(torrent_path)
            if p.exists():
                p.unlink()
        database.update_torrent_record(torrent_id, {"torrent_path": None})
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/torrent/<int:torrent_id>", methods=["DELETE"])
def torrent_record_delete(torrent_id: int) -> Response:
    """Delete a torrent DB record and its .torrent file if present.

    Blocked when added_to_qbt=1 — remove from qBittorrent first.
    Returns: {ok, error?}
    """
    try:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT torrent_path, added_to_qbt FROM torrents WHERE id=?", (torrent_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": f"No torrent record id={torrent_id}"}), 404
        if row["added_to_qbt"]:
            return jsonify({
                "ok": False,
                "error": "Remove from qBittorrent before deleting this record.",
            }), 400

        torrent_path = row["torrent_path"]
        if torrent_path:
            p = Path(torrent_path)
            if p.exists():
                p.unlink()
        database.delete_torrent_record(torrent_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
