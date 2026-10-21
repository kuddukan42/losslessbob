"""Platform helper, spectrogram and rename-apply routes."""

import logging
import shutil
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    request,
    send_file,
)

from backend.spectro_worker import (
    _do_spectro_batch,
    _spectro_lock,
    _spectro_state,
    get_spectrogram_status,
)

_log = logging.getLogger(__name__)

bp = Blueprint("spectrogram", __name__)


# ── Platform helpers ─────────────────────────────────────────────────────

@bp.route("/api/open/vlc", methods=["POST"])
def open_vlc_route() -> Response:
    """Launch VLC with a list of paths.

    Body: {paths: ["/absolute/path", ...]}
    Returns:
        JSON {ok: true} or {ok: false, error: "..."}.
    """
    try:
        paths = (request.get_json(silent=True) or {}).get("paths", [])
        if not paths:
            return jsonify({"ok": False, "error": "No paths provided"}), 400
        from backend.platform_utils import open_in_vlc
        ok, err = open_in_vlc(paths)
        return jsonify({"ok": ok, "error": err if not ok else None})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Spectrogram ──────────────────────────────────────────────────────────

@bp.route("/api/spectrogram/check", methods=["GET"])
def spectrogram_check() -> Response:
    """Return tool availability for the Setup tab indicator."""
    from backend.checksum_utils import check_shntool_version
    from backend.sox_utils import check_sox_version, get_ffmpeg, get_flac, get_install_hints
    sox_ver     = check_sox_version()
    ffmpeg      = get_ffmpeg()
    shntool_ver = check_shntool_version()
    flac_cmd    = get_flac()
    hints       = get_install_hints()
    return jsonify({
        "sox_available":        bool(sox_ver),
        "sox_version":          sox_ver,
        "ffmpeg_available":     ffmpeg is not None,
        "shntool_available":    bool(shntool_ver),
        "shntool_version":      shntool_ver,
        "flac_available":       flac_cmd is not None,
        "ffmpeg_install_hint":  hints.get("ffmpeg"),
        "sox_install_hint":     hints.get("sox"),
        "flac_install_hint":    hints.get("flac"),
        "shntool_install_hint": hints.get("shntool"),
    })


@bp.route("/api/spectrogram/generate", methods=["POST"])
def spectrogram_generate() -> Response:
    """
    Start batch spectrogram generation for a list of folders.
    Body: {
        folders:    ["/path/to/folder", ...],
        width:      1500,
        height:     513,
        dyn_range:  120,
        force:      false,
    }
    """
    with _spectro_lock:
        if _spectro_state["status"] not in ("idle", "done", "error"):
            return jsonify({"error": "Generation already running"}), 409
        _spectro_state["status"] = "running"

    data    = request.get_json() or {}
    folders = data.get("folders", [])
    if not folders:
        return jsonify({"error": "folders list required"}), 400

    opts = {
        "width":     int(data.get("width",    1500)),
        "height":    int(data.get("height",    513)),
        "dyn_range": int(data.get("dyn_range", 120)),
        "force":     bool(data.get("force",  False)),
    }
    import threading as _t
    _t.Thread(target=_do_spectro_batch,
              args=([str(f) for f in folders], opts),
              daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/spectrogram/status", methods=["GET"])
def spectrogram_status() -> Response:
    """Return current status of the spectrogram batch generation worker.

    Returns:
        JSON copy of the _spectro_state dict.
    """
    return jsonify(get_spectrogram_status())


@bp.route("/api/spectrogram/stop", methods=["POST"])
def spectrogram_stop() -> Response:
    """Request the spectrogram batch worker to stop after the current file.

    Returns:
        JSON {ok: true}.
    """
    with _spectro_lock:
        _spectro_state["stop_requested"] = True
    return jsonify({"ok": True})


@bp.route("/api/spectrogram/list", methods=["POST"])
def spectrogram_list() -> Response:
    """
    Return a dict of {folder -> [entry, ...]} for the viewer.
    Body: {folders: [...]}
    """
    from backend.sox_utils import AUDIO_EXTS_ALL
    folders = (request.get_json() or {}).get("folders", [])
    result  = {}
    for folder in folders:
        p = Path(folder)
        if not p.is_dir():
            continue
        spectro_dir = p / "spectrograms"
        audio_files = sorted(
            f for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS_ALL
        )
        pngs = {
            png.stem: str(png)
            for png in (spectro_dir.iterdir() if spectro_dir.is_dir() else [])
            if png.suffix.lower() == ".png"
        }
        entries = []
        for af in audio_files:
            png_path = pngs.get(af.stem, None)
            entries.append({
                "audio_file": str(af),
                "audio_name": af.name,
                "png_path":   png_path,
                "has_png":    png_path is not None,
            })
        if entries:
            result[folder] = entries
    return jsonify(result)


@bp.route("/api/spectrogram/png", methods=["GET"])
def spectrogram_png() -> Response:
    """Serve a spectrogram PNG from an arbitrary absolute path on disk.

    Query param: path (absolute path to the PNG file)
    Returns:
        The PNG file bytes with image/png content-type, or 404.
    """
    path_str = request.args.get("path", "")
    if not path_str:
        abort(400)
    p = Path(path_str)
    if not p.exists() or not p.is_file() or p.suffix.lower() != ".png":
        abort(404)
    return send_file(str(p), mimetype="image/png")


@bp.route("/api/rename/apply", methods=["POST"])
def rename_apply() -> Response:
    """Apply a list of folder/file renames on disk and log each to rename_history.

    When an item carries lb_number, also best-effort syncs qBittorrent's
    save path/root folder name (see backend.filer._sync_qbt_location) so a
    torrent already tracked in qBittorrent keeps seeding under the new name.

    Body: {renames: [{old_path, new_path, lb_number?}]}
    Returns:
        JSON {applied: N, errors: [...string]}
    """

    from backend.filer import _sync_qbt_location
    from backend.rename import write_rename_log
    data = request.get_json() or {}
    renames = data.get("renames", [])
    applied = 0
    errors: list[str] = []
    for item in renames:
        old_path = item.get("old_path", "")
        new_path = item.get("new_path", "")
        lb_number = item.get("lb_number")
        if not old_path or not new_path:
            errors.append(f"Missing old_path or new_path in item: {item}")
            continue
        try:
            src = Path(old_path)
            dst = Path(new_path)
            if not src.exists():
                errors.append(f"Source not found: {old_path}")
                continue
            if dst.exists():
                errors.append(f"Destination already exists: {new_path}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            write_rename_log(
                folder_path=str(dst.parent),
                old_name=src.name,
                new_name=dst.name,
                source="rename_tab",
                lb_number=lb_number,
            )
            if lb_number:
                _sync_qbt_location(int(lb_number), src, dst)
            applied += 1
        except Exception as exc:
            errors.append(f"{old_path}: {exc}")
    return jsonify({"applied": applied, "errors": errors})
