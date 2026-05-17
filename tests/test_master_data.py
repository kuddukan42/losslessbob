"""
Tests for the master-data publish/subscribe system (TODO-020).

Covers:
  - Table classification constants (MASTER_TABLES, USER_TABLES, MASTER_META_KEYS).
  - export_master_db() strips every user table, filters meta, stamps version,
    verifies the snapshot, and writes a manifest with a matching SHA256.
  - import_master_db() validates the manifest SHA256, refuses newer schema
    versions, takes a pre-import backup, preserves user-table rows, replaces
    master-table rows, and only overwrites whitelisted meta keys.
  - is_curator() / set_curator() round-trip.

All tests use temp-file SQLite DBs and redirect DATA_DIR so backups and
exports never touch the real data/ directory.
"""

import json
import os
import shutil
import sqlite3
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir).

    Redirects backend.paths.DATA_DIR so backup_database() and export_master_db()
    write into the temp dir instead of the real data/ directory.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _seed_master_and_user_data(conn, db_path: str) -> None:
    """Populate enough rows to make export/import diffs meaningful.

    db_path must be passed explicitly because migrate_lb_master/reconcile
    default to the production DB path otherwise.
    """
    # Master: entries + checksums + lb_master
    conn.executemany(
        "INSERT INTO entries(lb_number, status, location, date_str) VALUES(?,?,?,?)",
        [
            (1, "ok", "Forest Hills, NY", "1965-08-28"),
            (2, "ok", "Carnegie Hall, NY", "1961-11-04"),
            (3, "missing", None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO checksums(checksum, filename, chk_type, lb_number) VALUES(?,?,?,?)",
        [(f"abc{n:032d}", f"f{n}.flac", "f", n) for n in (1, 2)],
    )
    # User-only tables (must NOT ship)
    conn.execute(
        "INSERT INTO my_collection(lb_number, folder_name, disk_path) VALUES(?,?,?)",
        (1, "1965-08-28 Forest Hills (LB-00001)", "/music/1965-08-28"),
    )
    conn.execute(
        "INSERT INTO my_wishlist(lb_number, priority) VALUES(?, ?)", (2, 3)
    )
    conn.execute(
        "INSERT INTO collection_meta(lb_number, personal_rating, listen_count) "
        "VALUES(?, ?, ?)", (1, 5, 12),
    )
    conn.execute(
        "INSERT INTO forum_posts(lb_number, subject, topic_url, board_id) "
        "VALUES(?, ?, ?, ?)", (1, "Test post", "https://example/x", 7),
    )
    # Meta: a mix of master and user keys
    conn.executemany(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        [
            # Master keys (should ship)
            ("import_hash", "deadbeef"),
            ("last_import_date", "2026-05-17T00:00:00"),
            ("last_lb_number", "3"),
            # User keys (must NOT ship)
            ("search_page_size", "100"),
            ("qbt_host", "secret.example.com"),
            ("qbt_password", "shouldnotleak"),
            ("wtrf_board_id", "42"),
            ("is_curator", "1"),
            ("auto_scrape", "1"),
        ],
    )
    conn.commit()
    # Build lb_master from the seeded data on THIS test DB (not the default)
    import backend.db as db
    db.migrate_lb_master(db_path=db_path)
    for n in (1, 2, 3):
        db.reconcile_lb_status(n, trigger="reconcile", db_path=db_path)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_master_tables_constant_contains_expected_tables():
    import backend.db as db
    assert "checksums" in db.MASTER_TABLES
    assert "entries" in db.MASTER_TABLES
    assert "entry_files" in db.MASTER_TABLES
    assert "lb_master" in db.MASTER_TABLES
    assert "lb_status_history" in db.MASTER_TABLES
    assert "entry_changes" in db.MASTER_TABLES


def test_user_tables_constant_contains_expected_tables():
    import backend.db as db
    assert "my_collection" in db.USER_TABLES
    assert "collection_meta" in db.USER_TABLES
    assert "my_wishlist" in db.USER_TABLES
    assert "integrity_events" in db.USER_TABLES
    assert "torrents" in db.USER_TABLES
    assert "rename_history" in db.USER_TABLES
    assert "forum_posts" in db.USER_TABLES


def test_master_and_user_tables_are_disjoint():
    import backend.db as db
    assert set(db.MASTER_TABLES).isdisjoint(set(db.USER_TABLES))


def test_master_meta_keys_whitelist_excludes_user_keys():
    import backend.db as db
    assert "import_hash" in db.MASTER_META_KEYS
    assert "last_import_date" in db.MASTER_META_KEYS
    assert "master_version" in db.MASTER_META_KEYS
    assert "master_schema_version" in db.MASTER_META_KEYS
    # user keys must NOT be in the master whitelist
    assert "qbt_host" not in db.MASTER_META_KEYS
    assert "qbt_password" not in db.MASTER_META_KEYS
    assert "wtrf_board_id" not in db.MASTER_META_KEYS
    assert "search_page_size" not in db.MASTER_META_KEYS
    assert "is_curator" not in db.MASTER_META_KEYS


# ---------------------------------------------------------------------------
# Curator helpers
# ---------------------------------------------------------------------------

def test_curator_flag_roundtrip():
    db_path, _conn, tmp = _make_db()
    try:
        import backend.db as db
        assert db.is_curator(db_path) is False
        db.set_curator(True, db_path)
        assert db.is_curator(db_path) is True
        db.set_curator(False, db_path)
        assert db.is_curator(db_path) is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_excludes_user_tables_and_keys():
    db_path, conn, tmp = _make_db()
    try:
        _seed_master_and_user_data(conn, db_path)
        import backend.db as db
        out_path, manifest = db.export_master_db(reason="test", db_path=db_path)

        # Open the export with a plain sqlite3 connection (NOT the project pool)
        snap = sqlite3.connect(str(out_path))
        try:
            tables = {r[0] for r in snap.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            # No user tables present
            for t in db.USER_TABLES:
                assert t not in tables, f"user table {t} leaked into export"
            # Master tables present
            for t in db.MASTER_TABLES:
                assert t in tables, f"master table {t} missing from export"
            # Meta filtered: master keys present, user keys absent
            meta_keys = {r[0] for r in snap.execute(
                "SELECT key FROM meta"
            ).fetchall()}
            assert "import_hash" in meta_keys
            assert "master_version" in meta_keys
            assert "master_schema_version" in meta_keys
            assert "qbt_host" not in meta_keys
            assert "qbt_password" not in meta_keys
            assert "search_page_size" not in meta_keys
            assert "is_curator" not in meta_keys
            assert "wtrf_board_id" not in meta_keys
        finally:
            snap.close()

        # Manifest sanity
        assert manifest["filename"] == out_path.name
        assert manifest["sha256"]
        assert manifest["master_schema_version"] == db.MASTER_SCHEMA_VERSION
        assert manifest["row_counts"]["lb_master"] >= 1
        # Sidecar file written
        sidecar = out_path.parent / (out_path.name + ".manifest.json")
        assert sidecar.exists()
        with open(sidecar) as f:
            assert json.load(f)["sha256"] == manifest["sha256"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_export_sha256_matches_file_contents():
    import hashlib
    db_path, conn, tmp = _make_db()
    try:
        _seed_master_and_user_data(conn, db_path)
        import backend.db as db
        out_path, manifest = db.export_master_db(reason="hashtest", db_path=db_path)

        sha = hashlib.sha256()
        with open(out_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
        assert sha.hexdigest() == manifest["sha256"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_export_stamps_version_and_published_at():
    db_path, conn, tmp = _make_db()
    try:
        _seed_master_and_user_data(conn, db_path)
        import backend.db as db
        _out, manifest = db.export_master_db(reason="stamp", db_path=db_path)
        assert manifest["master_version"]
        assert manifest["master_published_at"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import_preserves_user_data_and_user_meta():
    """Curator exports a snapshot. End user (different DB) imports.
    Collection/wishlist/meta keys on the end user side survive intact."""
    # Step 1: curator builds an export. Stash a copy outside the tmp dir so
    # it survives curator cleanup, then end user imports from the stashed copy.
    curator_path, curator_conn, curator_tmp = _make_db()
    stash_dir = tempfile.mkdtemp(prefix="lbexport_")
    try:
        _seed_master_and_user_data(curator_conn, curator_path)
        import backend.db as db
        export_path, _ = db.export_master_db(
            reason="for_user", db_path=curator_path
        )
        # Stash both the .db and the .manifest.json
        stashed_db = shutil.copy2(
            str(export_path), os.path.join(stash_dir, export_path.name)
        )
        shutil.copy2(
            str(export_path) + ".manifest.json",
            os.path.join(stash_dir, export_path.name + ".manifest.json"),
        )
        export_path = type(export_path)(stashed_db)  # Path of the stashed copy
    finally:
        shutil.rmtree(curator_tmp, ignore_errors=True)

    # Step 2: end user has their own DB with their own user data + user meta
    user_path, user_conn, user_tmp = _make_db()
    try:
        # User-side data that must SURVIVE the master import.
        # my_collection has a FK on entries(lb_number), so seed an entry first.
        user_conn.execute(
            "INSERT INTO entries(lb_number, status, location) VALUES(?,?,?)",
            (99, "ok", "User-only venue"),
        )
        user_conn.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path) "
            "VALUES(?,?,?)", (99, "user-folder", "/music/user-only")
        )
        user_conn.executemany(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            [
                ("qbt_host", "user-qbt.local"),
                ("qbt_password", "user-secret"),
                ("search_page_size", "75"),
                ("is_curator", "0"),
            ],
        )
        user_conn.commit()

        # Step 3: apply the master
        import backend.db as db
        summary = db.import_master_db(export_path, db_path=user_path)

        # User-only rows preserved
        coll = user_conn.execute(
            "SELECT folder_name FROM my_collection WHERE lb_number=99"
        ).fetchone()
        assert coll is not None and coll[0] == "user-folder"

        # User meta preserved (untouched by import)
        get = lambda k: user_conn.execute(
            "SELECT value FROM meta WHERE key=?", (k,)
        ).fetchone()
        assert get("qbt_host")[0] == "user-qbt.local"
        assert get("qbt_password")[0] == "user-secret"
        assert get("search_page_size")[0] == "75"
        assert get("is_curator")[0] == "0"

        # Master meta overwritten from incoming
        assert get("import_hash")[0] == "deadbeef"
        assert get("master_version") is not None

        # Master tables populated with curator's content.
        # NOTE: migrate_lb_master deletes status='missing' tombstones, so
        # entries holds 2 rows (LB-1, LB-2) while lb_master holds 3 (LB-1..3).
        assert summary["row_counts"]["lb_master"] >= 3
        assert summary["row_counts"]["entries"] >= 2
        assert summary["row_counts"]["checksums"] >= 2
        assert summary["backup_path"]
    finally:
        shutil.rmtree(user_tmp, ignore_errors=True)
        shutil.rmtree(stash_dir, ignore_errors=True)


def test_import_rejects_sha256_mismatch():
    # Build a valid export
    curator_path, curator_conn, curator_tmp = _make_db()
    try:
        _seed_master_and_user_data(curator_conn, curator_path)
        import backend.db as db
        export_path, _ = db.export_master_db(
            reason="tampered", db_path=curator_path
        )
        # Tamper with the .db (append a byte → SHA changes)
        with open(export_path, "ab") as f:
            f.write(b"\x00")
        # Import side
        user_path, _uc, user_tmp = _make_db()
        try:
            with pytest.raises(ValueError, match="SHA256"):
                db.import_master_db(export_path, db_path=user_path)
        finally:
            shutil.rmtree(user_tmp, ignore_errors=True)
    finally:
        shutil.rmtree(curator_tmp, ignore_errors=True)


def test_import_rejects_newer_schema_version():
    curator_path, curator_conn, curator_tmp = _make_db()
    try:
        _seed_master_and_user_data(curator_conn, curator_path)
        import backend.db as db
        export_path, _ = db.export_master_db(
            reason="future", db_path=curator_path
        )
        # Hack the manifest to claim a higher schema version
        manifest_path = export_path.parent / (export_path.name + ".manifest.json")
        with open(manifest_path, "r") as f:
            m = json.load(f)
        m["master_schema_version"] = db.MASTER_SCHEMA_VERSION + 1
        with open(manifest_path, "w") as f:
            json.dump(m, f)
        # Also re-stamp SHA to match (otherwise we'd fail with SHA mismatch first)
        import hashlib
        sha = hashlib.sha256()
        with open(export_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
        m["sha256"] = sha.hexdigest()
        with open(manifest_path, "w") as f:
            json.dump(m, f)

        user_path, _uc, user_tmp = _make_db()
        try:
            with pytest.raises(RuntimeError, match="schema version"):
                db.import_master_db(export_path, db_path=user_path)
        finally:
            shutil.rmtree(user_tmp, ignore_errors=True)
    finally:
        shutil.rmtree(curator_tmp, ignore_errors=True)


def test_import_writes_pre_import_backup():
    """Backup must be created on the import side before the destructive copy."""
    curator_path, curator_conn, curator_tmp = _make_db()
    try:
        _seed_master_and_user_data(curator_conn, curator_path)
        import backend.db as db
        export_path, _ = db.export_master_db(
            reason="bktest", db_path=curator_path
        )

        user_path, _uc, user_tmp = _make_db()
        try:
            summary = db.import_master_db(export_path, db_path=user_path)
            from pathlib import Path
            backup = Path(summary["backup_path"])
            assert backup.exists()
            assert "pre_master_import" in backup.name
        finally:
            shutil.rmtree(user_tmp, ignore_errors=True)
    finally:
        shutil.rmtree(curator_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Flask endpoint guards (smoke)
# ---------------------------------------------------------------------------

def test_master_export_endpoint_requires_curator():
    """POST /api/master/export should 403 when curator flag is off."""
    db_path, conn, tmp = _make_db()
    try:
        _seed_master_and_user_data(conn, db_path)
        import backend.db as db
        db.set_curator(False, db_path)
        from backend.app import create_app
        # The Flask app uses the default DB_PATH; redirect it for the test.
        import backend.paths as _paths
        _orig = _paths.DB_PATH
        _paths.DB_PATH = db_path
        # backend.db uses module-level DB_PATH for some calls; also rebind it
        db.DB_PATH = db_path
        try:
            app = create_app()
            client = app.test_client()
            r = client.post("/api/master/export", json={"reason": "test"})
            assert r.status_code == 403
            assert r.get_json().get("error") == "curator_required"
        finally:
            _paths.DB_PATH = _orig
            db.DB_PATH = _orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
