"""
Tests for TODO-205 Phase-4 (hash-cache consultation).

Covers:
  - checksum_utils.verify_folder() consulting the P1 pipeline_file_hash cache
    via _cached_file_hashes(): cold/warm identical results, stale-stat
    detection (R1) on an edited file, a poisoned/stale cache row being
    ignored, and silent no-cache degradation on a cache-layer failure.
  - filer._source_tree_digest() reproducing filer.hash_tree() byte-for-byte
    from the cache, cold and warm, and falling back to hash_tree() on a
    derive_tree_digest() failure.
  - filer.start_file_job()'s stale-verify guard: a stored pipeline_folder_state
    fingerprint that no longer matches disk blocks with error_code
    "stale_verify"; a matching fingerprint or no stored state at all lets the
    call proceed past the guard (it then fails later for an unrelated reason
    since no mounts/routes/entries are configured in the test DB).

Never touches the real data/losslessbob.db — all tests use temp-file DBs.
"""

import hashlib
import os
import shutil
import tempfile


def _make_db():
    """Create a fresh temp DB with the full schema; rebind default DB_PATH globals.

    Mirrors tests/test_pipeline_cache.py's fixture, plus also rebinds
    backend.paths.DB_PATH / backend.db.DB_PATH — the code under test here
    (verify_folder, _source_tree_digest, start_file_job's stale-verify guard)
    calls several db.py cache helpers WITHOUT an explicit db_path, so those
    calls fall back to the module-level default; it must point at the temp DB.

    Returns:
        (db_path, conn, tmp_dir, restore) — call restore() in a finally block.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbhashcache_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)

    orig_paths_db_path = _paths.DB_PATH
    orig_db_db_path = db.DB_PATH
    _paths.DB_PATH = db_path
    db.DB_PATH = db_path

    def _restore():
        _paths.DB_PATH = orig_paths_db_path
        db.DB_PATH = orig_db_db_path

    return db_path, conn, tmp_dir, _restore


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _make_verify_folder(tmp_dir: str) -> str:
    """Fixture: 2 .flac files + a real checksums.md5 covering both."""
    root = os.path.join(tmp_dir, "1975-05-03 Somewhere (LB-99999)")
    os.makedirs(root)
    data1 = b"audio-bytes-track-one" * 200
    data2 = b"audio-bytes-track-two" * 200
    with open(os.path.join(root, "t01.flac"), "wb") as f:
        f.write(data1)
    with open(os.path.join(root, "t02.flac"), "wb") as f:
        f.write(data2)
    lines = [
        f"{_md5_hex(data1)}  t01.flac",
        f"{_md5_hex(data2)}  t02.flac",
    ]
    with open(os.path.join(root, "checksums.md5"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return root


def _make_tree_folder(tmp_dir: str) -> str:
    """Fixture for tree-digest tests: files at root + in a subfolder."""
    root = os.path.join(tmp_dir, "1977-06-01 Elsewhere (LB-88888)")
    os.makedirs(os.path.join(root, "disc2"))
    with open(os.path.join(root, "t01.flac"), "wb") as f:
        f.write(b"root-track-bytes" * 150)
    with open(os.path.join(root, "disc2", "t02.flac"), "wb") as f:
        f.write(b"disc2-track-bytes" * 150)
    return root


class TestVerifyFolderCache:
    def test_cold_and_warm_identical(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.checksum_utils as cu
            import backend.db as db
            root = _make_verify_folder(tmp)

            result1 = cu.verify_folder(root)
            assert result1["status"] == "pass"

            result2 = cu.verify_folder(root)
            assert result2 == result1

            rows = db.get_folder_hashes(root, db_path=db_path)
            assert set(rows) == {"t01.flac", "t02.flac"}
            for rel in ("t01.flac", "t02.flac"):
                assert rows[rel]["md5"]
                assert rows[rel]["sha256"]
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_edit_detected_not_stale(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.checksum_utils as cu
            import backend.db as db
            root = _make_verify_folder(tmp)

            first = cu.verify_folder(root)
            assert first["status"] == "pass"

            target = os.path.join(root, "t01.flac")
            new_data = b"totally-different-content" * 50
            with open(target, "wb") as f:
                f.write(new_data)
            os.utime(target, (2000000000, 2000000000))
            new_md5 = _md5_hex(new_data)

            second = cu.verify_folder(root)
            assert second["status"] == "fail"
            assert second["mismatch"] == 1
            file_entry = next(f for f in second["files"] if f["filename"] == "t01.flac")
            assert file_entry["overall"] == "fail"
            assert file_entry["md5_actual"] == new_md5
            assert file_entry["md5_status"] == "fail"

            rows = db.get_folder_hashes(root, db_path=db_path)
            assert rows["t01.flac"]["md5"] == new_md5
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_poisoned_cache_with_stale_stats_ignored(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.checksum_utils as cu
            import backend.db as db
            root = _make_verify_folder(tmp)

            # Poison the cache for t01.flac with a wrong md5 under (size, mtime)
            # that do not match the real file's current stat — a stale row.
            db.upsert_file_hash(
                root, "t01.flac", size=999999, mtime=123456789.0,
                md5="deadbeef" * 4, db_path=db_path,
            )

            result = cu.verify_folder(root)
            assert result["status"] == "pass"
            assert result["mismatch"] == 0
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cache_layer_failure_degrades(self, monkeypatch):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.checksum_utils as cu
            import backend.db as db
            root = _make_verify_folder(tmp)

            def _raise(*args, **kwargs):
                raise RuntimeError("cache layer unavailable")

            monkeypatch.setattr(db, "get_folder_hashes", _raise)

            result = cu.verify_folder(root)
            assert result["status"] == "pass"
            assert result["mismatch"] == 0
            assert result["pass"] == 2
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestSourceTreeDigest:
    def test_equals_hash_tree_cold_and_warm(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            from pathlib import Path

            import backend.filer as filer
            root = _make_tree_folder(tmp)

            expected = filer.hash_tree(Path(root))

            cold = filer._source_tree_digest(Path(root))
            assert cold == expected

            warm = filer._source_tree_digest(Path(root))
            assert warm == expected
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fallback_on_cache_error(self, monkeypatch):
        db_path, conn, tmp, restore = _make_db()
        try:
            from pathlib import Path

            import backend.db as db
            import backend.filer as filer
            root = _make_tree_folder(tmp)

            expected = filer.hash_tree(Path(root))

            def _raise(*args, **kwargs):
                raise RuntimeError("derive_tree_digest unavailable")

            monkeypatch.setattr(db, "derive_tree_digest", _raise)

            assert filer._source_tree_digest(Path(root)) == expected
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestStaleVerifyGuard:
    def test_stale_fingerprint_blocks(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.db as db
            import backend.filer as filer
            root = _make_tree_folder(tmp)

            db.put_folder_state(
                root, "WRONG-FINGERPRINT", {"verify": {"status": "ok"}}, db_path=db_path,
            )

            result = filer.start_file_job(99999, root, db_path=db_path)
            assert result == {
                "ok": False,
                "error": (
                    "Folder contents changed since the last pipeline check — "
                    "re-run the pipeline for this folder"
                ),
                "error_code": "stale_verify",
            }
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_matching_fingerprint_proceeds(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.db as db
            import backend.filer as filer
            root = _make_tree_folder(tmp)

            real_fp = db.folder_fingerprint(root)
            db.put_folder_state(
                root, real_fp, {"verify": {"status": "ok"}}, db_path=db_path,
            )

            result = filer.start_file_job(99999, root, db_path=db_path)
            assert result["ok"] is False
            assert result["error_code"] != "stale_verify"
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_state_proceeds(self):
        db_path, conn, tmp, restore = _make_db()
        try:
            import backend.filer as filer
            root = _make_tree_folder(tmp)

            result = filer.start_file_job(99999, root, db_path=db_path)
            assert result["ok"] is False
            assert result["error_code"] != "stale_verify"
        finally:
            restore()
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)
