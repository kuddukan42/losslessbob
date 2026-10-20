"""Verify and LBDir routes (lbdir generation, manifest scope, status)."""

import logging
import os
import re
import shutil
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import (
    checksum_utils,
    scraper,
)
from backend import db as database
from backend.folder_lb import (
    _find_lbdir_in_folder,
    _pinned_lb_for_folder,
    _resolve_lb_number_for_folder,
    _resolve_xref_for_folder,
)
from backend.paths import (
    SITE_FILES_DIR,
    find_lbdir_attachment,
)

_log = logging.getLogger(__name__)

bp = Blueprint("lbdir", __name__)


# ── Verify ───────────────────────────────────────────────────────────────

@bp.route("/api/verify", methods=["POST"])
def verify() -> Response:
    """Verify checksums for a list of local folders against the DB.

    Body: {folders: ["/path/to/folder", ...]}
    Returns:
        JSON {results: [verify_result, ...]} or 400 if folders is empty.
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400
        results = [checksum_utils.verify_folder(f) for f in folders]
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/verify/generate", methods=["POST"])
def verify_generate() -> Response:
    """Generate checksum files (_mychecksums_*) for a list of folders.

    Body: {folders: ["/path/to/folder", ...]}
    Returns:
        JSON {results: [generate_result, ...]} or 400 if folders is empty.
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400
        results = [checksum_utils.generate_checksums(f) for f in folders]
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── LBDir ────────────────────────────────────────────────────────────────

@bp.route("/api/lbdir/check", methods=["POST"])
def lbdir_check() -> Response:
    """Verify each folder's files against its lbdir*.txt checksum list.

    Body: {folders: ["/path/to/folder", ...], lb_number_hint?: int}
    Returns:
        JSON {results: [lbdir_check_result, ...]} or 400 if folders is empty.
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        # Optional single-folder hint: pipeline passes this when LB is known from
        # lookup but the folder has not yet been renamed (LBDIR now runs before
        # Rename, so neither my_collection nor the folder name has the LB# yet).
        lb_number_hint: int | None = None
        raw_hint = data.get("lb_number_hint")
        if raw_hint is not None:
            try:
                lb_number_hint = int(raw_hint)
            except (ValueError, TypeError):
                pass

        results = []
        for folder_path in folders:
            folder = Path(folder_path)

            # LB number: a single explicit pin (Override LB# / Pin & continue)
            # wins over the heuristics (BUG-257); else my_collection, then the
            # folder name, then the caller-supplied hint (pipeline lookup result).
            lb_number = _pinned_lb_for_folder(folder)
            if lb_number is None:
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?",
                        (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None

            if lb_number is None:
                m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                if m:
                    lb_number = int(m.group(1))

            if lb_number is None and lb_number_hint is not None:
                lb_number = lb_number_hint

            # LB-scoped: a manifest left behind by a previously-matched LB
            # must not be checked against this folder (BUG-315).
            lbdir_path = _find_lbdir_in_folder(folder, lb_number)

            if not lbdir_path:
                results.append({
                    "folder": str(folder_path),
                    "lb_number": lb_number,
                    "lbdir_found": False,
                    "lbdir_path": None,
                    "status": "no_lbdir",
                    "mode": "unknown",
                    "total": 0, "pass": 0, "mismatch": 0, "missing": 0,
                    "extra": 0, "missing_types": [], "files": [],
                    "error": "No lbdir*.txt found in folder",
                })
                continue

            result = checksum_utils.verify_folder_lbdir(folder_path, lbdir_path)
            result["lb_number"] = lb_number
            result["lbdir_found"] = True
            result["lbdir_path"] = str(lbdir_path)

            lbdir_verified_at = None
            if result["status"] == "pass" and lb_number is not None:
                database.set_lbdir_verified(str(folder))
                with database.get_connection() as _c:
                    _row = _c.execute(
                        "SELECT lbdir_verified_at FROM my_collection WHERE lb_number=?",
                        (lb_number,)
                    ).fetchone()
                lbdir_verified_at = _row["lbdir_verified_at"] if _row else None
            result["lbdir_verified_at"] = lbdir_verified_at

            results.append(result)

        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lbdir/retrieve", methods=["POST"])
def lbdir_retrieve() -> Response:
    """Copy the lbdir*.txt from the attachments cache into each folder.

    Scrapes the LB entry first if the attachment has not yet been downloaded.
    Body: {folders: ["/path/to/folder", ...]}
    Returns:
        JSON {results: [retrieve_result, ...]} or 400 if folders is empty.
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        # Optional single-folder hint: pipeline passes this when LB is known from
        # lookup but the folder has not yet been renamed or filed.
        lb_number_hint: int | None = None
        raw_hint = data.get("lb_number_hint")
        if raw_hint is not None:
            try:
                lb_number_hint = int(raw_hint)
            except (ValueError, TypeError):
                pass

        results = []
        for folder_path in folders:
            folder = Path(folder_path)

            # LB number: a single explicit pin (Override LB# / Pin & continue)
            # wins over the heuristics (BUG-257); else my_collection, then the
            # folder name, then the caller-supplied hint (pipeline lookup result).
            lb_number = _pinned_lb_for_folder(folder)
            if lb_number is None:
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?",
                        (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None

            if lb_number is None:
                m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                if m:
                    lb_number = int(m.group(1))

            if lb_number is None and lb_number_hint is not None:
                lb_number = lb_number_hint

            if lb_number is None:
                results.append({
                    "folder": str(folder_path),
                    "lb_number": None,
                    "status": "no_lb_number",
                    "lbdir_filename": None,
                })
                continue
            xref = _resolve_xref_for_folder(folder, lb_number)
            lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
            was_scraped = False

            if not lbdir_src:
                scraper.scrape_entry(lb_number, force=False, download_files=True)
                lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
                was_scraped = True

            if not lbdir_src and xref == 0:
                # This LB has no lbdir — try the canonical if this is an alias.
                # (Only for canonical lookups: an xref-N miss means the specific
                # fileset attachment is missing, not that lb_number is an alias.)
                canonical_list = database.resolve_aliases([lb_number])
                canonical = (
                    canonical_list[0]
                    if canonical_list and canonical_list[0] != lb_number
                    else None
                )
                if canonical:
                    lbdir_src = find_lbdir_attachment(canonical)
                    if not lbdir_src:
                        scraper.scrape_entry(canonical, force=False, download_files=True)
                        lbdir_src = find_lbdir_attachment(canonical)
                        was_scraped = True
                    if lbdir_src:
                        lb_number = canonical

            if not lbdir_src:
                results.append({
                    "folder": str(folder_path),
                    "lb_number": lb_number,
                    "status": "not_found",
                    "lbdir_filename": None,
                })
                continue

            dest = folder / lbdir_src.name
            # Only an lbdir belonging to *this* LB counts as already
            # present — after an override the folder may still hold the
            # previous LB's manifest, which must be superseded (BUG-315).
            existing = _find_lbdir_in_folder(folder, lb_number, strict=True)
            if existing:
                results.append({
                    "folder": str(folder_path),
                    "lb_number": lb_number,
                    "status": "already_present",
                    "lbdir_filename": existing.name,
                })
                continue

            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(lbdir_src), str(dest))

            results.append({
                "folder": str(folder_path),
                "lb_number": lb_number,
                "status": "scraped_and_copied" if was_scraped else "copied",
                "lbdir_filename": lbdir_src.name,
            })

        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lbdir/reconcile", methods=["POST"])
def lbdir_reconcile() -> Response:
    """Preview: find disk/site files whose MD5 matches missing lbdir entries. Does NOT move files.

    Body: {folders: ["/path/to/folder", ...], lb_number_hint?: int}
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        # Optional single-folder hint: pipeline passes this when LB is known from
        # lookup but the folder has not yet been renamed (LBDIR now runs before
        # Rename, so neither my_collection nor the folder name has the LB# yet).
        lb_number_hint: int | None = None
        raw_hint = data.get("lb_number_hint")
        if raw_hint is not None:
            try:
                lb_number_hint = int(raw_hint)
            except (ValueError, TypeError):
                pass

        results = []
        for folder_path in folders:
            folder = Path(folder_path)
            lbdir_path = _find_lbdir_in_folder(
                folder, _resolve_lb_number_for_folder(folder) or lb_number_hint
            )
            if not lbdir_path:
                results.append({"folder": str(folder), "error": "No lbdir*.txt found"})
                continue
            result = checksum_utils.find_reconcilable_files(folder, lbdir_path)
            result["folder"] = str(folder)

            # Look up lb_number to scan site/files for still-missing entries.
            # A single explicit pin wins over the heuristics (BUG-257).
            lb_number = _pinned_lb_for_folder(folder)
            if lb_number is None:
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT lb_number FROM my_collection WHERE disk_path=?", (str(folder),)
                    ).fetchone()
                lb_number = row["lb_number"] if row else None
            if lb_number is None:
                m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
                if m:
                    lb_number = int(m.group(1))

            if lb_number is None and lb_number_hint is not None:
                lb_number = lb_number_hint

            if lb_number is not None:
                site_result = checksum_utils.find_site_recoverable_files(
                    folder, lbdir_path, SITE_FILES_DIR, lb_number
                )
                result["site_proposals"] = site_result.get("site_proposals", [])
            else:
                result["site_proposals"] = []

            results.append(result)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lbdir/apply_reconcile", methods=["POST"])
def lbdir_apply_reconcile() -> Response:
    """Apply verified rename/move/copy proposals inside a single folder. Never deletes files.

    If folder is qBittorrent-tracked, best-effort syncs the new file paths
    (see backend.filer._sync_qbt_file_renames) so applied renames don't
    break seeding for that torrent (BUG-228).
    """
    try:
        from backend.filer import _sync_qbt_file_renames
        data = request.get_json() or {}
        folder = Path(data.get("folder", ""))
        renames = data.get("renames", [])      # [{"from": rel, "to": rel}, ...]
        site_copies = data.get("site_copies", [])  # [{"site_path": abs, "lbdir_rel": rel}, ...]
        applied, errors = [], []

        for r in renames:
            src = folder / r["from"]
            dst = folder / r["to"]
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                applied.append(r)
            except Exception as e:
                errors.append({"rename": r, "error": str(e)})

        if applied:
            lb_number = _resolve_lb_number_for_folder(folder)
            if lb_number is not None:
                _sync_qbt_file_renames(
                    lb_number, folder, [(r["from"], r["to"]) for r in applied]
                )

        site_copied = []
        for sc in site_copies:
            src = Path(sc["site_path"])
            dst = folder / sc["lbdir_rel"]
            # Security: only allow copies from within SITE_FILES_DIR
            try:
                src.relative_to(SITE_FILES_DIR)
            except ValueError:
                errors.append({"site_copy": sc, "error": "site_path outside SITE_FILES_DIR"})
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                site_copied.append(sc["lbdir_rel"])
            except Exception as e:
                errors.append({"site_copy": sc, "error": str(e)})

        return jsonify({"applied": len(applied), "site_copied": len(site_copied), "errors": errors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lbdir/find_extra", methods=["POST"])
def lbdir_find_extra() -> Response:
    """List files in each folder that are not referenced in the lbdir MD5 section."""
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        results = []
        for folder_path in folders:
            folder = Path(folder_path)
            lbdir_path = _find_lbdir_in_folder(
                folder, _resolve_lb_number_for_folder(folder)
            )
            if not lbdir_path:
                results.append({"folder": str(folder), "error": "No lbdir*.txt found"})
                continue
            result = checksum_utils.find_extra_files(folder, lbdir_path)
            result["folder"] = str(folder)
            results.append(result)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lbdir/move_extras", methods=["POST"])
def lbdir_move_extras() -> Response:
    """Move extra files (not in lbdir) to <folder>/extras/, preserving relative path structure.

    If folder is qBittorrent-tracked, best-effort syncs the new file paths
    (see backend.filer._sync_qbt_file_renames) so the move doesn't break
    seeding for that torrent (BUG-228).
    """
    try:
        from backend.filer import _sync_qbt_file_renames
        data = request.get_json() or {}
        folder = Path(data.get("folder", ""))
        files = data.get("files", [])  # list of relative paths
        extras_dir = folder / "extras"
        extras_dir.mkdir(parents=True, exist_ok=True)
        moved, errors = [], []
        for rel in files:
            src = folder / rel
            dst = extras_dir / rel
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(rel)
            except Exception as e:
                errors.append({"file": rel, "error": str(e)})

        if moved:
            lb_number = _resolve_lb_number_for_folder(folder)
            if lb_number is not None:
                _sync_qbt_file_renames(
                    lb_number, folder, [(rel, f"extras/{rel}") for rel in moved]
                )
        # Prune empty subdirectories (never touch folder root or extras_dir)
        for dirpath, _dirs, _files in os.walk(str(folder), topdown=False):
            d = Path(dirpath)
            if d == folder or d == extras_dir or str(d).startswith(str(extras_dir)):
                continue
            try:
                if not any(d.iterdir()):
                    d.rmdir()
            except Exception:
                pass
        return jsonify({"moved": len(moved), "errors": errors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
