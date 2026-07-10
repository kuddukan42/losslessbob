"""Tests for ONBOARDING spec Phase P1: site-data packaging (backend/app.py).

Covers (see instructions/FABLE_ONBOARDING_SYNC.md §3):
  - POST /api/package/scrape_data with part=core|files|omitted selects the
    right files from data/site/ into each zip, with omitted staying
    backward-compatible with existing callers (whole-tree zip).
  - The <zip_name>.manifest.json sidecar shape (type, created_at, file_count,
    total_bytes, sha256) and correctness (sha256 matches zip bytes, counts
    match the files actually written).
  - POST /api/sitedata/github_release is curator-gated (smoke only — no
    network/gh CLI calls happen before the 403).

All tests build a throwaway data/ dir (temp) with a fake site/ tree and
redirect backend.app's module-level path constants + backend.paths.DB_PATH
so nothing touches the real data/ directory or a real DB.
"""

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


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
