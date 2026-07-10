"""Tests for ONBOARDING spec Phases P1 + P2 (backend/app.py).

Covers P1 (see instructions/FABLE_ONBOARDING_SYNC.md §3):
  - POST /api/package/scrape_data with part=core|files|omitted selects the
    right files from data/site/ into each zip, with omitted staying
    backward-compatible with existing callers (whole-tree zip).
  - The <zip_name>.manifest.json sidecar shape (type, created_at, file_count,
    total_bytes, sha256) and correctness (sha256 matches zip bytes, counts
    match the files actually written).
  - POST /api/sitedata/github_release is curator-gated (smoke only — no
    network/gh CLI calls happen before the 403).

Covers P2 (§3 item 3 + §4):
  - GET /api/sitedata/github_check pairs collision-suffixed asset names
    (e.g. losslessbob_sitedata_core_2026-07-10_2.zip) with their
    .manifest.json sidecars, per part.
  - POST /api/sitedata/github_install verifies SHA256 before extraction —
    a mismatch errors out and leaves SITE_DIR untouched.
  - /api/package/restore's site-extraction path accepts the new
    sitedata_core/sitedata_files manifest types.
  - GET /api/onboarding/status shape + complete logic, empty vs populated DB.

All tests build a throwaway data/ dir (temp) with a fake site/ tree and
redirect backend.app's module-level path constants + backend.paths.DB_PATH
so nothing touches the real data/ directory or a real DB. P2's GitHub calls
are mocked via unittest.mock.patch("requests.get", ...) — no network reached.
"""

import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_site_tree() -> Path:
    """Build a fake data/ dir with a data/site/ tree of known contents.

    Returns:
        Path to the temp dir standing in for DATA_DIR (contains a site/ subdir).
    """
    tmp = Path(tempfile.mkdtemp(prefix="lbtest_sitedata_"))
    site_dir = tmp / "site"
    (site_dir / "detail").mkdir(parents=True)
    (site_dir / "lbbcd").mkdir(parents=True)
    (site_dir / "files").mkdir(parents=True)

    (site_dir / "detail" / "12345.html").write_text("<html>detail</html>")
    (site_dir / "lbbcd" / "index.html").write_text("<html>lbbcd</html>")
    (site_dir / "files" / "a.md5").write_text("deadbeef  file.flac\n")
    (site_dir / "files" / "b.st5").write_text("checksum data\n")

    return tmp


def _app_client(data_dir: Path, db_path: str):
    """Build a Flask test client with app.py's path/DB constants redirected.

    Args:
        data_dir: temp dir standing in for DATA_DIR (must contain site/).
        db_path: temp sqlite file already migrated via backend.db.init_db.

    Returns:
        (test_client, restore_fn) — call restore_fn() in a finally block.
    """
    import backend.app as app_module
    import backend.db as db
    import backend.paths as _paths

    orig = {
        "app_DATA_DIR": app_module.DATA_DIR,
        "app_SITE_DIR": app_module.SITE_DIR,
        "app_SITE_FILES_DIR": app_module.SITE_FILES_DIR,
        "paths_DB_PATH": _paths.DB_PATH,
        "db_DB_PATH": db.DB_PATH,
    }

    site_dir = data_dir / "site"
    app_module.DATA_DIR = data_dir
    app_module.SITE_DIR = site_dir
    app_module.SITE_FILES_DIR = site_dir / "files"
    _paths.DB_PATH = db_path
    db.DB_PATH = db_path

    def _restore() -> None:
        app_module.DATA_DIR = orig["app_DATA_DIR"]
        app_module.SITE_DIR = orig["app_SITE_DIR"]
        app_module.SITE_FILES_DIR = orig["app_SITE_FILES_DIR"]
        _paths.DB_PATH = orig["paths_DB_PATH"]
        db.DB_PATH = orig["db_DB_PATH"]

    app = app_module.create_app()
    return app.test_client(), _restore


def _make_db(tmp: Path) -> str:
    """Init a fresh migrated sqlite DB inside tmp and return its path."""
    import backend.db as db

    db_path = str(tmp / "test.db")
    db.init_db(db_path)
    return db_path


# ---------------------------------------------------------------------------
# part=core / part=files / omitted (backward compat) file selection
# ---------------------------------------------------------------------------

def test_part_core_excludes_files_subtree():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data?part=core")
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"] is True
            manifest = data["manifest"]
            assert manifest["type"] == "sitedata_core"
            assert manifest["file_count"] == 2  # detail/ + lbbcd/, no files/

            zip_path = Path(data["path"])
            assert zip_path.name.startswith("losslessbob_sitedata_core_")
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
            assert "site/detail/12345.html" in names
            assert "site/lbbcd/index.html" in names
            assert not any(n.startswith("site/files/") for n in names)
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_part_files_includes_only_files_subtree():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data?part=files")
            assert r.status_code == 200
            data = r.get_json()
            manifest = data["manifest"]
            assert manifest["type"] == "sitedata_files"
            assert manifest["file_count"] == 2  # a.md5 + b.st5

            zip_path = Path(data["path"])
            assert zip_path.name.startswith("losslessbob_sitedata_files_")
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
            assert len(names) == 2
            assert all(n.startswith("site/files/") for n in names)
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_default_part_packages_whole_tree_backward_compat():
    """Omitting `part` must keep working exactly like before (existing callers)."""
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data")
            assert r.status_code == 200
            data = r.get_json()
            manifest = data["manifest"]
            assert manifest["type"] == "scrape_data"
            assert manifest["file_count"] == 4  # all 4 fixture files

            zip_path = Path(data["path"])
            # Legacy filename convention preserved (no part suffix).
            assert zip_path.name.startswith("losslessbob_sitedata_")
            assert "_core_" not in zip_path.name
            assert "_files_" not in zip_path.name
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_invalid_part_returns_400():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data?part=bogus")
            assert r.status_code == 400
            assert r.get_json()["error"] == "invalid_part"
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_site_data_returns_400():
    tmp = Path(tempfile.mkdtemp(prefix="lbtest_sitedata_empty_"))
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data?part=core")
            assert r.status_code == 400
            assert r.get_json()["error"] == "no_site_data"
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Manifest sidecar shape + correctness
# ---------------------------------------------------------------------------

def test_manifest_sidecar_shape_and_sha256():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/scrape_data?part=core")
            data = r.get_json()
            manifest = data["manifest"]

            for key in ("type", "created_at", "file_count", "total_bytes", "sha256"):
                assert key in manifest, f"manifest missing {key}"

            zip_path = Path(data["path"])
            manifest_path = Path(data["manifest_path"])
            assert manifest_path.exists()
            assert manifest_path.name == zip_path.name + ".manifest.json"

            with open(manifest_path) as f:
                sidecar = json.load(f)
            assert sidecar == manifest

            # sha256 matches the zip's actual bytes
            sha = hashlib.sha256()
            with open(zip_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    sha.update(chunk)
            assert sha.hexdigest() == manifest["sha256"]

            # total_bytes matches the sum of the two source files' sizes
            expected_bytes = (
                (tmp / "site" / "detail" / "12345.html").stat().st_size
                + (tmp / "site" / "lbbcd" / "index.html").stat().st_size
            )
            assert manifest["total_bytes"] == expected_bytes
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manifest_type_distinguishes_core_and_files():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r_core = client.post("/api/package/scrape_data?part=core")
            r_files = client.post("/api/package/scrape_data?part=files")
            core_type = r_core.get_json()["manifest"]["type"]
            files_type = r_files.get_json()["manifest"]["type"]
            assert core_type == "sitedata_core"
            assert files_type == "sitedata_files"
            assert core_type != files_type
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# /api/sitedata/github_release curator gate (smoke — no network reached)
# ---------------------------------------------------------------------------

def test_sitedata_github_release_requires_curator():
    """POST /api/sitedata/github_release should 403 before any packaging/network work."""
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        import backend.db as db
        db.set_curator(False, db_path)

        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/sitedata/github_release")
            assert r.status_code == 403
            assert r.get_json().get("error") == "curator_required"
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# P2: /api/sitedata/github_check + github_install (mocked GitHub)
# ---------------------------------------------------------------------------

_CORE_ZIP_NAME = "losslessbob_sitedata_core_2026-07-10_2.zip"
_CORE_ZIP_URL = "https://dl.example/core.zip"
_CORE_MANIFEST_URL = "https://dl.example/core.zip.manifest.json"


def _make_sitedata_zip_bytes(entries: dict[str, str]) -> bytes:
    """Build an in-memory site/-prefixed zip from {relative_path: text}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, text in entries.items():
            zf.writestr(f"site/{rel}", text)
    return buf.getvalue()


def _core_release_assets(zip_bytes: bytes) -> list[dict]:
    return [
        {"name": _CORE_ZIP_NAME, "size": len(zip_bytes),
         "browser_download_url": _CORE_ZIP_URL},
        {"name": _CORE_ZIP_NAME + ".manifest.json", "size": 200,
         "browser_download_url": _CORE_MANIFEST_URL},
    ]


def _mock_github_get(assets: list[dict], downloads: dict):
    """Build a requests.get side_effect serving a fake GitHub Releases API.

    Args:
        assets: asset dicts for a single sitedata-2026-07-10 release.
        downloads: browser_download_url -> dict (JSON body) or bytes
            (streamed zip content).
    """
    release = {
        "tag_name": "sitedata-2026-07-10",
        "html_url": "https://github.com/x/y/releases/tag/sitedata-2026-07-10",
        "published_at": "2026-07-10T00:00:00Z",
        "assets": assets,
    }

    def _get(url, **_kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        if "api.github.com" in url:
            resp.json.return_value = [release]
            return resp
        payload = downloads[url]
        if isinstance(payload, bytes):
            resp.iter_content = lambda chunk_size: iter(
                payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)
            )
        else:
            resp.json.return_value = payload
        return resp

    return _get


def _sse_events(raw: str) -> list[dict]:
    """Parse 'data: {...}' lines out of an SSE response body."""
    return [json.loads(line[len("data: "):])
            for line in raw.splitlines() if line.startswith("data: ")]


def test_github_check_pairs_collision_suffixed_assets():
    """github_check must match _core_/_files_ zips by substring (GitHub adds
    a numeric collision suffix), pair each with its .manifest.json sidecar,
    and omit parts whose sidecar is missing."""
    zip_bytes = _make_sitedata_zip_bytes({"detail/1.html": "x"})
    manifest = {"type": "sitedata_core",
                "sha256": hashlib.sha256(zip_bytes).hexdigest(), "file_count": 1}
    # files part zip present but WITHOUT a manifest sidecar → must be omitted.
    assets = _core_release_assets(zip_bytes) + [
        {"name": "losslessbob_sitedata_files_2026-07-10.zip", "size": 10,
         "browser_download_url": "https://dl.example/files.zip"},
    ]
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            with patch("requests.get",
                       side_effect=_mock_github_get(assets, {_CORE_MANIFEST_URL: manifest})):
                r = client.get("/api/sitedata/github_check")
            assert r.status_code == 200
            data = r.get_json()
            assert data["available"] is True
            assert data["tag"] == "sitedata-2026-07-10"
            core = data["parts"]["core"]
            assert core["asset_name"] == _CORE_ZIP_NAME
            assert core["asset_size"] == len(zip_bytes)
            assert core["manifest"] == manifest
            assert "files" not in data["parts"]
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_github_install_sha_mismatch_leaves_site_untouched():
    """A manifest/zip SHA256 mismatch must error out before extraction and
    delete the downloaded zip."""
    zip_bytes = _make_sitedata_zip_bytes({"detail/999.html": "new"})
    manifest = {"type": "sitedata_core", "sha256": "0" * 64, "file_count": 1}
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            with patch("requests.get", side_effect=_mock_github_get(
                    _core_release_assets(zip_bytes),
                    {_CORE_MANIFEST_URL: manifest, _CORE_ZIP_URL: zip_bytes})):
                r = client.post("/api/sitedata/github_install", json={"parts": ["core"]})
                events = _sse_events(r.get_data(as_text=True))
            assert events[-1]["type"] == "error"
            assert events[-1]["error"] == "sha256_mismatch"
            assert not (tmp / "site" / "detail" / "999.html").exists()
            assert not (tmp / "imports" / _CORE_ZIP_NAME).exists()
            assert not (tmp / "site" / ".sitedata_core_manifest.json").exists()
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_github_install_success_extracts_and_writes_marker():
    zip_bytes = _make_sitedata_zip_bytes({"detail/999.html": "new",
                                          "detail/12345.html": "overwrite"})
    manifest = {"type": "sitedata_core",
                "sha256": hashlib.sha256(zip_bytes).hexdigest(), "file_count": 2}
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            with patch("requests.get", side_effect=_mock_github_get(
                    _core_release_assets(zip_bytes),
                    {_CORE_MANIFEST_URL: manifest, _CORE_ZIP_URL: zip_bytes})):
                r = client.post("/api/sitedata/github_install", json={"parts": ["core"]})
                events = _sse_events(r.get_data(as_text=True))
            assert events[-1]["type"] == "done"
            part = events[-1]["summary"]["parts"]["core"]
            # detail/999.html is new; detail/12345.html pre-exists in the fixture.
            assert part["restored"] == 1
            assert part["conflicts"] == 1
            assert (tmp / "site" / "detail" / "999.html").read_text() == "new"
            assert (tmp / "site" / "detail" / "12345.html").read_text() == "overwrite"
            marker = tmp / "site" / ".sitedata_core_manifest.json"
            assert json.loads(marker.read_text()) == manifest
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_github_install_invalid_part_400():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/sitedata/github_install", json={"parts": ["bogus"]})
            assert r.status_code == 400
            assert r.get_json()["error"] == "invalid_part"
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# P2: /api/package/restore accepts sitedata_core/sitedata_files manifest types
# ---------------------------------------------------------------------------

def test_restore_accepts_sitedata_manifest_types():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        zp = tmp / "core_pkg.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"type": "sitedata_core"}))
            zf.writestr("site/detail/777.html", "restored")
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.post("/api/package/restore", json={"zip_path": str(zp)})
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"] is True
            assert data["type"] == "sitedata_core"
            assert (tmp / "site" / "detail" / "777.html").read_text() == "restored"
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# P2: /api/onboarding/status
# ---------------------------------------------------------------------------

def test_onboarding_status_empty_db():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.get("/api/onboarding/status")
            assert r.status_code == 200
            data = r.get_json()
            assert data["entries_count"] == 0
            assert data["master_version"] is None
            # fixture tree has site/detail/ + 2 files in site/files/
            assert data["sitedata_core_present"] is True
            assert data["sitedata_files_count"] == 2
            assert data["mounts_configured"] is False
            assert data["collection_count"] == 0
            assert data["complete"] is False
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_onboarding_status_complete_when_populated():
    tmp = _make_site_tree()
    try:
        db_path = _make_db(tmp)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO entries(lb_number) VALUES (1)")
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('master_version', '1.2.0')")
        conn.execute("INSERT INTO collection_mounts(label, root_path) VALUES ('main', '/mnt/x')")
        conn.commit()
        conn.close()
        client, restore = _app_client(tmp, db_path)
        try:
            r = client.get("/api/onboarding/status")
            assert r.status_code == 200
            data = r.get_json()
            assert data["entries_count"] == 1
            assert data["master_version"] == "1.2.0"
            assert data["mounts_configured"] is True
            assert data["complete"] is True
        finally:
            restore()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
