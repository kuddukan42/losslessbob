"""Data package export/restore, site-data GitHub release publish/check/install, onboarding status (TODO-369)."""

import json
import logging
import os
import threading
from datetime import UTC
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    stream_with_context,
)

from backend import db as database
from backend.github_upload import _github_upload_asset
from backend.paths import (
    DATA_DIR,
    SITE_DIR,
    SITE_FILES_DIR,
)

_log = logging.getLogger(__name__)

bp = Blueprint("export", __name__)


# ── Data Package Export ───────────────────────────────────────────────────

@bp.route("/api/package/user_data", methods=["POST"])
def package_user_data() -> Response:
    """Bundle user data (DB + settings + gui_state) into a dated zip in data/exports/.

    Returns: {ok, path, manifest: {type, created_at, files, file_count, total_bytes}}
    """
    import hashlib
    import zipfile
    from datetime import date, datetime

    try:
        exports_dir = DATA_DIR / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        date_str = date.today().isoformat()
        zip_path = exports_dir / f"losslessbob_userdata_{date_str}.zip"
        counter = 2
        while zip_path.exists():
            zip_path = exports_dir / f"losslessbob_userdata_{date_str}_{counter}.zip"
            counter += 1

        candidates = [
            (DATA_DIR / "losslessbob.db", "losslessbob.db"),
            (DATA_DIR / "settings.ini", "settings.ini"),
            (DATA_DIR / "gui_state.json", "gui_state.json"),
        ]

        manifest_files = []
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src, arc_name in candidates:
                if src.exists():
                    zf.write(src, arc_name)
                    size = src.stat().st_size
                    sha256 = hashlib.sha256(src.read_bytes()).hexdigest()
                    manifest_files.append({"name": arc_name, "size_bytes": size, "sha256": sha256})

        manifest = {
            "type": "user_data",
            "created_at": datetime.now(UTC).isoformat() + "Z",
            "files": manifest_files,
            "file_count": len(manifest_files),
            "total_bytes": sum(f["size_bytes"] for f in manifest_files),
        }
        _log.info("package_user_data: wrote %s (%d files)", zip_path.name, len(manifest_files))
        return jsonify({"ok": True, "path": str(zip_path), "manifest": manifest})
    except Exception:
        _log.exception("package_user_data failed")
        return jsonify({"error": "internal_error"}), 500


def _package_site_data(part: str | None) -> "tuple[Path, Path, dict]":
    """Bundle ``data/site/`` (or a subset of it) into a dated zip + manifest.

    Mirrors :func:`backend.db.export_master_db`'s manifest convention: a
    ``<zip_name>.manifest.json`` sidecar written next to the zip with
    ``type``, ``created_at``, ``file_count``, ``total_bytes``, ``sha256``.

    Args:
        part: ``None`` to package the whole ``data/site/`` tree (legacy,
            backward-compatible behavior); ``"core"`` for everything
            except ``data/site/files/``; ``"files"`` for only
            ``data/site/files/``. See FABLE_ONBOARDING_SYNC.md §3.

    Returns:
        (zip_path, manifest_path, manifest_dict).

    Raises:
        FileNotFoundError: If ``data/site/`` does not exist yet.
    """
    import hashlib
    import zipfile
    from datetime import date, datetime

    if not SITE_DIR.exists():
        raise FileNotFoundError("data/site/ does not exist. Run the site crawler first.")

    exports_dir = DATA_DIR / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    date_str = date.today().isoformat()
    if part is None:
        base_name = f"losslessbob_sitedata_{date_str}"
        manifest_type = "scrape_data"
    else:
        base_name = f"losslessbob_sitedata_{part}_{date_str}"
        manifest_type = f"sitedata_{part}"

    zip_path = exports_dir / f"{base_name}.zip"
    counter = 2
    while zip_path.exists():
        zip_path = exports_dir / f"{base_name}_{counter}.zip"
        counter += 1

    def _include(src: Path) -> bool:
        if part is None:
            return True
        under_files = src.is_relative_to(SITE_FILES_DIR)
        return under_files if part == "files" else not under_files

    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in sorted(SITE_DIR.rglob("*")):
            if src.is_file() and _include(src):
                arc_name = "site/" + src.relative_to(SITE_DIR).as_posix()
                zf.write(src, arc_name)
                file_count += 1
                total_bytes += src.stat().st_size

    sha = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)

    manifest = {
        "type": manifest_type,
        "created_at": datetime.now(UTC).isoformat() + "Z",
        "file_count": file_count,
        "total_bytes": total_bytes,
        "sha256": sha.hexdigest(),
    }
    manifest_path = zip_path.with_name(zip_path.name + ".manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    return zip_path, manifest_path, manifest


@bp.route("/api/package/scrape_data", methods=["POST"])
def package_scrape_data() -> Response:
    """Bundle scraped site data (data/site/) into a dated zip in data/exports/.

    Query param ``part`` selects the subset to package:
      - omitted (default): the whole ``data/site/`` tree in one zip —
        backward-compatible with existing callers (ScreenSetup).
      - ``core``: everything except ``data/site/files/`` (detail pages,
        artwork, lbbcd/bynumber indexes). Recommended for all users.
      - ``files``: only ``data/site/files/`` (checksum/fingerprint text
        attachments). Optional, much larger.

    A ``<zip_name>.manifest.json`` sidecar is written next to the zip.

    Returns: {ok, path, manifest_path, manifest: {type, created_at,
    file_count, total_bytes, sha256}}
    """
    part = request.args.get("part")
    if part not in (None, "core", "files"):
        return jsonify({
            "error": "invalid_part",
            "message": "part must be 'core' or 'files'",
        }), 400

    try:
        zip_path, manifest_path, manifest = _package_site_data(part)
        _log.info("package_scrape_data: wrote %s (%d files, part=%s)",
                   zip_path.name, manifest["file_count"], part or "all")
        return jsonify({
            "ok": True,
            "path": str(zip_path),
            "manifest_path": str(manifest_path),
            "manifest": manifest,
        })
    except FileNotFoundError as exc:
        return jsonify({"error": "no_site_data", "message": str(exc)}), 400
    except Exception:
        _log.exception("package_scrape_data failed")
        return jsonify({"error": "internal_error"}), 500


def _restore_sitedata_zip(zip_path: "Path", dry_run: bool = False) -> dict:
    """Extract a ``site/``-prefixed zip (whole-tree, core, or files) into SITE_DIR.

    Shared by ``/api/package/restore`` (local zip path, legacy manifest-less
    ``scrape_data`` zips) and the ``/api/sitedata/github_install`` pipeline
    (P1's ``sitedata_core``/``sitedata_files`` zips — same ``site/``-prefixed
    entry layout, just a subset of the tree). Every entry is written to
    ``SITE_DIR / <relative path>``, overwriting any existing file, so
    re-running against the same or an updated zip is a clean overwrite —
    no doubled files.

    Args:
        zip_path: Path to the zip archive.
        dry_run: If True, compute the restored/conflicts split without
            writing anything to disk.

    Returns:
        {"restored": [{name, dest}], "conflicts": [{name, dest}]} — a
        "conflict" is an entry whose destination already existed (still
        overwritten unless dry_run).
    """
    import zipfile

    restored: list[dict] = []
    conflicts: list[dict] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for arc_name in zf.namelist():
            if not arc_name.startswith("site/") or arc_name.endswith("/"):
                continue
            rel = arc_name[len("site/"):]
            dest = SITE_DIR / rel
            entry = {"name": arc_name, "dest": str(dest)}
            if dest.exists():
                conflicts.append(entry)
            else:
                restored.append(entry)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(arc_name))
    return {"restored": restored, "conflicts": conflicts}


@bp.route("/api/package/restore", methods=["POST"])
def package_restore() -> Response:
    """Restore a zip archive produced by /api/package/user_data or /api/package/scrape_data.

    Body: {zip_path: str, dry_run: bool = false}
    Returns: {ok, type, restored: [{name, dest}], conflicts: [{name, dest}], dry_run: bool}
    """
    import zipfile

    body = request.get_json(silent=True) or {}
    zip_path_str = body.get("zip_path", "")
    dry_run = bool(body.get("dry_run", False))

    if not zip_path_str:
        return jsonify({"error": "zip_path is required"}), 400

    zip_path = Path(zip_path_str)
    if not zip_path.is_file():
        return jsonify({"error": "file_not_found", "message": f"No file at {zip_path_str}"}), 404

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            # Detect package type from manifest embedded inside zip, or from file names.
            pkg_type: str | None = None
            manifest_data: dict = {}
            if "manifest.json" in names:
                import json as _json
                manifest_data = _json.loads(zf.read("manifest.json"))
                pkg_type = manifest_data.get("type")

            if pkg_type is None:
                if any(n.startswith("site/") for n in names):
                    # Covers legacy whole-tree scrape_data zips as well as
                    # P1's sitedata_core/sitedata_files zips — all three
                    # share the same "site/"-prefixed entry layout and are
                    # distinguished only by the manifest.json *sidecar*
                    # (never embedded in the zip itself), so name-based
                    # detection collapses them onto the same restore path.
                    pkg_type = "scrape_data"
                elif any(n in ("losslessbob.db", "settings.ini", "gui_state.json") for n in names):
                    pkg_type = "user_data"
                else:
                    return jsonify({"error": "unrecognised_package",
                                    "message": "Cannot determine package type from zip contents."}), 400

            restored = []
            conflicts = []

            if pkg_type == "user_data":
                user_files = [
                    ("losslessbob.db", DATA_DIR / "losslessbob.db"),
                    ("settings.ini",   DATA_DIR / "settings.ini"),
                    ("gui_state.json", DATA_DIR / "gui_state.json"),
                ]
                for arc_name, dest in user_files:
                    if arc_name not in names:
                        continue
                    entry = {"name": arc_name, "dest": str(dest)}
                    if dest.exists():
                        conflicts.append(entry)
                    else:
                        restored.append(entry)
                    if not dry_run:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(arc_name))
                if not dry_run:
                    _log.info("package_restore(user_data): restored %d files from %s",
                              len(restored) + len(conflicts), zip_path.name)

            elif pkg_type in ("scrape_data", "sitedata_core", "sitedata_files"):
                extraction = _restore_sitedata_zip(zip_path, dry_run=dry_run)
                restored, conflicts = extraction["restored"], extraction["conflicts"]
                if not dry_run:
                    _log.info("package_restore(%s): restored %d files from %s",
                              pkg_type, len(restored) + len(conflicts), zip_path.name)

            return jsonify({
                "ok": True,
                "type": pkg_type,
                "restored": restored,
                "conflicts": conflicts,
                "dry_run": dry_run,
            })
    except zipfile.BadZipFile:
        return jsonify({"error": "bad_zip", "message": "File is not a valid zip archive."}), 400
    except Exception:
        _log.exception("package_restore failed")
        return jsonify({"error": "internal_error"}), 500


@bp.route("/api/sitedata/github_release", methods=["POST"])
def sitedata_github_release() -> Response:
    """Package site data (core + files) and publish both as a GitHub release.

    Curator-only. Mirror of ``master_github_release``: builds the two
    assets locally (via ``_package_site_data``), obtains a token via
    ``gh auth token``, then uses the GitHub REST API to create a release
    tagged ``sitedata-<YYYY-MM-DD>`` and upload all 4 assets (2 zips +
    2 ``.manifest.json`` sidecars) with byte-accurate progress.

    Body: none required.
    Returns: text/event-stream with events:
      data: {"type": "progress", "label": "...", "pct": N_or_null}
      data: {"type": "done", "tag": "...", "url": "..."}
      data: {"type": "error", "error": "...", "message": "..."}
    """
    import json as _json
    import queue
    import subprocess
    from datetime import date

    import requests as _req

    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403

    _REPO = "kuddukan42/losslessbob"
    _GH_API = "https://api.github.com"
    ev_q: queue.Queue = queue.Queue()

    def _work() -> None:
        try:
            # Build both assets first so a packaging failure surfaces
            # before we ever touch the network.
            ev_q.put({"type": "progress", "label": "Packaging core site data…", "pct": None})
            try:
                core_zip, core_manifest_path, _core_manifest = _package_site_data("core")
            except FileNotFoundError as exc:
                ev_q.put({"type": "error", "error": "no_site_data", "message": str(exc)})
                return

            ev_q.put({"type": "progress", "label": "Packaging site files…", "pct": None})
            files_zip, files_manifest_path, _files_manifest = _package_site_data("files")

            # Obtain token via gh CLI
            tok = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=15,
            )
            if tok.returncode != 0:
                ev_q.put({"type": "error", "error": "gh_auth_failed",
                          "message": tok.stderr.strip() or "gh auth token failed"})
                return
            token = tok.stdout.strip()
            if not token:
                ev_q.put({"type": "error", "error": "gh_no_token",
                          "message": "gh auth token returned empty — run `gh auth login` first."})
                return

            gh_hdr = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            }

            date_str = date.today().isoformat()

            # Find an unused tag: sitedata-YYYY-MM-DD[.N]
            ev_q.put({"type": "progress", "label": "Checking for existing releases…", "pct": None})
            base_tag = f"sitedata-{date_str}"
            tag = None
            for suffix in ["", ".2", ".3", ".4", ".5"]:
                candidate = f"{base_tag}{suffix}" if suffix else base_tag
                chk = _req.get(
                    f"{_GH_API}/repos/{_REPO}/releases/tags/{candidate}",
                    headers=gh_hdr, timeout=15,
                )
                if chk.status_code == 404:
                    tag = candidate
                    break
            if tag is None:
                ev_q.put({"type": "error", "error": "too_many_releases",
                          "message": f"5 releases already exist for {date_str}."})
                return

            # Create the GitHub release
            ev_q.put({"type": "progress", "label": f"Creating release {tag}…", "pct": None})
            cr = _req.post(
                f"{_GH_API}/repos/{_REPO}/releases",
                headers=gh_hdr,
                json={
                    "tag_name": tag,
                    "name": f"Site Data {date_str}",
                    "body": "Cached LB site data (detail pages, artwork, "
                                "attachments). See manifest sidecars for contents.",
                },
                timeout=30,
            )
            if not cr.ok:
                msg = cr.json().get("message", cr.text[:300]) if cr.content else cr.reason
                ev_q.put({"type": "error", "error": "create_failed", "message": msg})
                return
            release = cr.json()
            # upload_url: "https://uploads.github.com/.../assets{?name,label}" — strip template
            upload_base = release["upload_url"].split("{")[0]
            release_url = release["html_url"]

            def _upload_asset(file_path: Path, label: str) -> None:
                _github_upload_asset(_req, upload_base, token, file_path, label, ev_q)

            for asset_path in (core_zip, core_manifest_path, files_zip, files_manifest_path):
                ev_q.put({"type": "progress", "label": f"Uploading {asset_path.name}…", "pct": 0})
                _upload_asset(asset_path, asset_path.name)

            ev_q.put({"type": "done", "tag": tag, "url": release_url})

        except FileNotFoundError:
            ev_q.put({"type": "error", "error": "gh_not_found",
                      "message": "gh CLI not found — install GitHub CLI first."})
        except Exception as exc:
            ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

    threading.Thread(target=_work, daemon=True).start()

    def _stream():
        from backend import activity as _activity

        with _activity.track("sitedata_publish", screen="/setup") as _job:
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {"type": "error", "error": "timeout",
                          "message": "Upload timed out after 680 s."}
                if ev.get("type") == "progress":
                    _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

    return Response(
        stream_with_context(_stream()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _find_sitedata_release(_req) -> "tuple[dict, dict]":
    """Search recent GitHub releases for the latest ``sitedata-*`` release.

    Mirrors ``_find_master_release`` but scoped to the ``sitedata-``
    tag prefix (the repo also carries ``master-*`` releases on the same
    endpoint) and pairs *both* core and files parts rather than a single
    asset. Real releases carry GitHub's numeric collision suffix on the
    zip name (e.g. ``losslessbob_sitedata_core_2026-07-10_2.zip`` when a
    same-day zip of that part already existed at packaging time), so
    parts are identified by substring (``_core_`` / ``_files_``) rather
    than an exact date-stamped filename, then paired with the
    ``<zip_name>.manifest.json`` sidecar asset uploaded alongside it.

    Args:
        _req: the ``requests`` module (or compatible), passed in for
            testability.

    Returns:
        (release, parts) where ``parts`` is a dict with up to
        ``"core"``/``"files"`` keys, each
        ``{"zip_asset": asset, "manifest_asset": asset}``. Only parts
        with both a zip and a matching manifest sidecar present are
        included.

    Raises:
        RuntimeError: No ``sitedata-*`` release with at least one
            complete (zip + manifest) part is found in the most recent
            5 pages of releases.
    """
    _REPO = "kuddukan42/losslessbob"
    page = 1
    while page <= 5:
        resp = _req.get(
            f"https://api.github.com/repos/{_REPO}/releases",
            headers={"Accept": "application/vnd.github+json"},
            params={"per_page": 20, "page": page},
            timeout=15,
        )
        if resp.status_code == 404 or (page == 1 and resp.json() == []):
            raise RuntimeError("No releases found on GitHub yet.")
        resp.raise_for_status()
        releases = resp.json()
        if not releases:
            break
        for release in releases:
            if not str(release.get("tag_name", "")).startswith("sitedata-"):
                continue
            assets = release.get("assets", [])
            parts: dict = {}
            for part in ("core", "files"):
                zip_asset = next(
                    (a for a in assets
                     if f"_{part}_" in a["name"] and a["name"].endswith(".zip")),
                    None,
                )
                if not zip_asset:
                    continue
                manifest_name = zip_asset["name"] + ".manifest.json"
                manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
                if not manifest_asset:
                    continue
                parts[part] = {"zip_asset": zip_asset, "manifest_asset": manifest_asset}
            if parts:
                return release, parts
        page += 1
    raise RuntimeError("No release with sitedata assets found on GitHub.")


@bp.route("/api/sitedata/github_check", methods=["GET"])
def sitedata_github_check() -> Response:
    """Check GitHub Releases for the latest ``sitedata-*`` release.

    Returns:
        JSON dict with ``available`` (bool), ``tag``, ``release_url``,
        ``published_at`` plus a ``parts`` dict keyed by whichever of
        ``core``/``files`` are present in the release, each
        ``{asset_name, asset_size, manifest}`` (manifest sidecars are a
        few hundred bytes, so fetched eagerly — cheap). If no usable
        release exists, ``available`` is ``false`` with a human-readable
        ``message``, mirroring ``master_github_check``.
    """
    import requests as _req

    try:
        try:
            release, parts = _find_sitedata_release(_req)
        except RuntimeError as exc:
            return jsonify({"available": False, "message": str(exc)})

        parts_out = {}
        for part, info in parts.items():
            zip_asset = info["zip_asset"]
            manifest_asset = info["manifest_asset"]
            mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
            mresp.raise_for_status()
            parts_out[part] = {
                "asset_name": zip_asset["name"],
                "asset_size": zip_asset.get("size", 0),
                "manifest": mresp.json(),
            }

        return jsonify({
            "available": True,
            "tag": release.get("tag_name", "?"),
            "release_url": release.get("html_url", ""),
            "published_at": release.get("published_at", ""),
            "parts": parts_out,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/sitedata/github_install", methods=["POST"])
def sitedata_github_install() -> Response:
    """Download and install site-data part(s) from the latest ``sitedata-*`` release.

    Body: ``{"parts": ["core"]}`` or ``["core", "files"]`` — default
    ``["core"]``.

    Streams progress via ``text/event-stream``, mirroring
    ``master_github_install``'s event shape:
      data: {"type": "progress", "label": "...", "pct": N_or_null}
      data: {"type": "done", "summary": {...}}
      data: {"type": "error", "error": "...", "message": "..."}

    For each selected part: downloads the zip asset to ``data/imports/``,
    fetches its manifest sidecar, and verifies the zip's SHA256 against
    the manifest *before* any extraction — a mismatch deletes the
    downloaded zip and errors out without touching ``SITE_DIR``. On
    success, extracts into ``SITE_DIR`` via ``_restore_sitedata_zip``
    (overwrite semantics — re-running is a clean overwrite, no doubled
    files) and writes a ``.sitedata_<part>_manifest.json`` marker in
    ``SITE_DIR`` so ``/api/onboarding/status`` can read part presence /
    file counts without rescanning the filesystem.
    """
    import hashlib
    import json as _json
    import queue

    import requests as _req

    body = request.get_json(silent=True) or {}
    parts = body.get("parts") or ["core"]
    invalid = [p for p in parts if p not in ("core", "files")]
    if invalid:
        return jsonify({
            "error": "invalid_part",
            "message": f"Unknown part(s): {invalid}. Must be 'core' and/or 'files'.",
        }), 400

    ev_q: queue.Queue = queue.Queue()

    def _work() -> None:
        try:
            ev_q.put({"type": "progress",
                      "label": "Checking GitHub for latest site-data release…", "pct": None})
            try:
                release, available_parts = _find_sitedata_release(_req)
            except RuntimeError as exc:
                ev_q.put({"type": "error", "error": "no_releases", "message": str(exc)})
                return

            tag = release.get("tag_name", "?")
            dest_dir = DATA_DIR / "imports"
            dest_dir.mkdir(parents=True, exist_ok=True)

            summary: dict = {"tag": tag, "parts": {}}

            for part in parts:
                part_info = available_parts.get(part)
                if part_info is None:
                    ev_q.put({"type": "error", "error": "part_not_found",
                              "message": f"No '{part}' asset found in release {tag}."})
                    return

                zip_asset = part_info["zip_asset"]
                manifest_asset = part_info["manifest_asset"]

                ev_q.put({"type": "progress",
                          "label": f"Downloading manifest for {part}…", "pct": None})
                mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
                mresp.raise_for_status()
                manifest = mresp.json()

                zip_dest = dest_dir / zip_asset["name"]
                manifest_dest = dest_dir / manifest_asset["name"]

                total_bytes = zip_asset.get("size", 0)
                total_mb = total_bytes / (1 << 20)
                ev_q.put({"type": "progress",
                          "label": f"Downloading {zip_asset['name']} ({total_mb:.0f} MB)…",
                          "pct": 0})
                dresp = _req.get(zip_asset["browser_download_url"], stream=True, timeout=600)
                dresp.raise_for_status()

                downloaded = 0
                with open(zip_dest, "wb") as fh:
                    for chunk in dresp.iter_content(chunk_size=1 << 18):
                        if chunk:
                            fh.write(chunk)
                            downloaded += len(chunk)
                            if total_bytes:
                                pct = downloaded * 100 // total_bytes
                                dl_mb = downloaded / (1 << 20)
                                ev_q.put({
                                    "type": "progress",
                                    "label": (f"Downloading {part}… {pct}%  "
                                                  f"({dl_mb:.1f} / {total_mb:.0f} MB)"),
                                    "pct": pct,
                                })

                ev_q.put({"type": "progress",
                          "label": f"Verifying {part} checksum…", "pct": None})
                sha = hashlib.sha256()
                with open(zip_dest, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        sha.update(chunk)
                expected_sha = manifest.get("sha256", "")
                if sha.hexdigest() != expected_sha:
                    zip_dest.unlink(missing_ok=True)
                    ev_q.put({"type": "error", "error": "sha256_mismatch",
                              "message": f"SHA256 mismatch for {part} — download may be "
                                             "corrupt. Please try again."})
                    return

                with open(manifest_dest, "w", encoding="utf-8") as fh:
                    _json.dump(manifest, fh, indent=2)

                ev_q.put({"type": "progress",
                          "label": f"Extracting {part} into site data…", "pct": None})
                extraction = _restore_sitedata_zip(zip_dest)

                # Cheap local signal for /api/onboarding/status — avoids an
                # os.scandir() over up to ~94k files on every status poll.
                SITE_DIR.mkdir(parents=True, exist_ok=True)
                marker_path = SITE_DIR / f".sitedata_{part}_manifest.json"
                with open(marker_path, "w", encoding="utf-8") as fh:
                    _json.dump(manifest, fh, indent=2)

                summary["parts"][part] = {
                    "restored": len(extraction["restored"]),
                    "conflicts": len(extraction["conflicts"]),
                    "manifest": manifest,
                }

            ev_q.put({"type": "done", "summary": summary})

        except Exception as exc:
            ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

    threading.Thread(target=_work, daemon=True).start()

    def _stream():
        from backend import activity as _activity

        with _activity.track("sitedata_install", screen="/setup") as _job:
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {"type": "error", "error": "timeout",
                          "message": "Install timed out after 680 s."}
                if ev.get("type") == "progress":
                    _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

    return Response(
        stream_with_context(_stream()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _sitedata_local_state() -> "tuple[bool, int]":
    """Cheap local read of installed site-data extent, for onboarding/status.

    Prefers the ``.sitedata_<part>_manifest.json`` marker written by
    ``sitedata_github_install`` (a single small JSON read) over scanning
    the filesystem. Falls back to a directory-existence check (core) and
    an ``os.scandir`` count (files — ~94k entries, ≈1s, acceptable per
    FABLE_ONBOARDING_SYNC.md §4) when a marker is missing, e.g. site data
    restored via the legacy ``/api/package/restore`` local-zip path
    rather than the GitHub installer.

    Returns:
        (sitedata_core_present, sitedata_files_count).
    """
    core_marker = SITE_DIR / ".sitedata_core_manifest.json"
    if core_marker.exists():
        core_present = True
    else:
        core_dir = SITE_DIR / "detail"
        core_present = core_dir.exists() and any(core_dir.iterdir())

    files_marker = SITE_DIR / ".sitedata_files_manifest.json"
    files_count = 0
    if files_marker.exists():
        try:
            files_count = int(
                json.loads(files_marker.read_text(encoding="utf-8")).get("file_count", 0)
            )
        except Exception:
            files_count = 0
    elif SITE_FILES_DIR.exists():
        files_count = sum(1 for _ in os.scandir(SITE_FILES_DIR))

    return core_present, files_count


@bp.route("/api/onboarding/status", methods=["GET"])
def onboarding_status() -> Response:
    """Report first-run onboarding progress for the wizard / Home checklist.

    See FABLE_ONBOARDING_SYNC.md §4. Cheap only: COUNT queries, a
    ``meta`` read, and directory existence/marker checks (see
    ``_sitedata_local_state``) — no full table scans.

    Returns:
        JSON: {entries_count, master_version, sitedata_core_present,
        sitedata_files_count, mounts_configured, collection_count,
        complete}. ``complete`` is true iff entries are present AND
        ``master_version`` is stamped AND at least one collection mount
        is configured.
    """
    try:
        with database.get_connection() as conn:
            entries_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            collection_count = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
        master_version = database.get_meta("master_version")
        sitedata_core_present, sitedata_files_count = _sitedata_local_state()
        mounts_configured = bool(database.get_collection_mounts())

        complete = bool(entries_count) and bool(master_version) and mounts_configured

        return jsonify({
            "entries_count": entries_count,
            "master_version": master_version,
            "sitedata_core_present": sitedata_core_present,
            "sitedata_files_count": sitedata_files_count,
            "mounts_configured": mounts_configured,
            "collection_count": collection_count,
            "complete": complete,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
