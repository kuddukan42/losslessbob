"""Collection mounts/routes, integrity monitor, disk scanner, file-level integrity"""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("mounts", __name__)


# ── Collection Mounts & Routes (Pipeline Step 5) ─────────────────────────

@bp.route("/api/collection/mounts", methods=["GET"])
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


@bp.route("/api/collection/mounts", methods=["POST"])
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


@bp.route("/api/collection/mounts/<int:mount_id>", methods=["PATCH"])
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


@bp.route("/api/collection/mounts/<int:mount_id>", methods=["DELETE"])
def collection_mounts_delete(mount_id: int) -> Response:
    """Delete a mount. Returns 409 if any routes reference it."""
    try:
        result = database.delete_collection_mount(mount_id)
        if not result["ok"]:
            return jsonify(result), 409
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/routes", methods=["GET"])
def collection_routes_list() -> Response:
    """List all year routes joined with mount label and root_path."""
    try:
        return jsonify({"routes": database.get_collection_routes()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/routes/bulk", methods=["POST"])
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


@bp.route("/api/collection/routes/<int:year>", methods=["DELETE"])
def collection_routes_delete(year: int) -> Response:
    """Remove the route for a single year."""
    try:
        database.delete_collection_route(year)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/routes/preview/<int:year>", methods=["GET"])
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

@bp.route("/api/collection/integrity/scan", methods=["POST"])
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


@bp.route("/api/collection/integrity/scan/cancel", methods=["POST"])
def collection_integrity_scan_cancel() -> Response:
    """Request cancellation of the running integrity scan, if any."""
    try:
        from backend import integrity_monitor
        cancelled = integrity_monitor.cancel_scan()
        return jsonify({"ok": cancelled})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/integrity/scan/status", methods=["GET"])
def collection_integrity_scan_status() -> Response:
    """Return progress of the current/last integrity scan for GUI polling."""
    try:
        from backend import integrity_monitor
        return jsonify(integrity_monitor.get_scan_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/integrity/scan/history", methods=["GET"])
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


@bp.route("/api/collection/integrity/summary", methods=["GET"])
def collection_integrity_summary() -> Response:
    """Return per-mount integrity status counts for MountCard badges."""
    try:
        return jsonify(database.get_mount_integrity_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/integrity/status", methods=["GET"])
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

@bp.route("/api/scanner/scan", methods=["POST"])
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


@bp.route("/api/scanner/scan/cancel", methods=["POST"])
def scanner_scan_cancel() -> Response:
    """Request cancellation of the running disk scan, if any."""
    try:
        from backend import disk_scanner
        return jsonify({"ok": disk_scanner.cancel_scan()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/scanner/scan/status", methods=["GET"])
def scanner_scan_status() -> Response:
    """Return progress (and, once finished, results) of the disk scan."""
    try:
        from backend import disk_scanner
        return jsonify(disk_scanner.get_scan_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/scanner/add", methods=["POST"])
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

@bp.route("/api/file-integrity/scan", methods=["POST"])
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


@bp.route("/api/file-integrity/scan/cancel", methods=["POST"])
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


@bp.route("/api/file-integrity/status", methods=["GET"])
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


@bp.route("/api/file-integrity/summary", methods=["GET"])
def file_integrity_summary() -> Response:
    """Return per-mount file counts by status, for GUI badges."""
    try:
        return jsonify(database.get_file_integrity_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/file-integrity/problems", methods=["GET"])
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


@bp.route("/api/file-integrity/history", methods=["GET"])
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


@bp.route("/api/file-integrity/rebaseline", methods=["POST"])
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
