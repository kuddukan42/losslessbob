"""
Tests for the TODO-205 Phase-1 pipeline hash/state cache (backend/db.py).

Covers the Phase-1 verify column of the design doc
(instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md §9): fingerprint stability,
hash-cache round-trip with (size, mtime) validation semantics, folder-state
merge/discard semantics, and — load-bearing — that derive_tree_digest()
reproduces filer.hash_tree() byte-for-byte on a fixture containing a
lone-surrogate filename.

Never touches the real data/losslessbob.db — all tests use temp-file DBs.
"""

import os
import shutil
import tempfile


def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with the full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbpipe_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _make_folder(tmp_dir: str) -> str:
    """Create a fixture folder: nested files, cover art, surrogate filename."""
    root = os.path.join(tmp_dir, "1975-05-03 Somewhere (LB-12345)")
    os.makedirs(os.path.join(root, "artwork"))
    with open(os.path.join(root, "t01.flac"), "wb") as f:
        f.write(b"FLAC-bytes-one" * 100)
    with open(os.path.join(root, "t02.flac"), "wb") as f:
        f.write(b"FLAC-bytes-two" * 100)
    with open(os.path.join(root, "checksums.ffp"), "wb") as f:
        f.write(b"t01.flac:abc\n")
    with open(os.path.join(root, "artwork", "front.jpg"), "wb") as f:
        f.write(b"\xff\xd8jpeg")
    # Lone-surrogate filename (undecodable byte via surrogateescape) — exercises
    # the "utf-8"/"surrogatepass" encode in the tree digest (design §2c).
    surrogate_name = b"info\xff.txt".decode("utf-8", "surrogateescape")
    with open(os.path.join(root, surrogate_name), "wb") as f:
        f.write(b"weird name")
    return root


class TestFingerprint:
    def test_stable_and_sensitive(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            root = _make_folder(tmp)

            fp1 = db.folder_fingerprint(root)
            fp2 = db.folder_fingerprint(root)
            assert fp1 is not None and fp1 == fp2

            # In-place content edit: directory mtime unchanged, file mtime moves.
            target = os.path.join(root, "t01.flac")
            with open(target, "r+b") as f:
                f.write(b"X")
            os.utime(target, (1234567890, 1234567890))
            assert db.folder_fingerprint(root) != fp1

            assert db.folder_fingerprint(os.path.join(tmp, "missing")) is None
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rename_changes_fingerprint(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            root = _make_folder(tmp)
            fp1 = db.folder_fingerprint(root)
            os.rename(os.path.join(root, "t02.flac"), os.path.join(root, "t03.flac"))
            assert db.folder_fingerprint(root) != fp1
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestFileHashCache:
    def test_round_trip_and_merge(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            db.upsert_file_hash("/x/folder", "t01.flac", 100, 1.5, md5="aa", db_path=db_path)
            row = db.get_file_hash("/x/folder", "t01.flac", db_path=db_path)
            assert row["md5"] == "aa" and row["sha256"] is None

            # Same (size, mtime): NULL args preserve stored values (merge).
            db.upsert_file_hash("/x/folder", "t01.flac", 100, 1.5, sha256="bb", db_path=db_path)
            row = db.get_file_hash("/x/folder", "t01.flac", db_path=db_path)
            assert row["md5"] == "aa" and row["sha256"] == "bb"

            # Changed (size, mtime): whole row replaced — old hashes must die.
            db.upsert_file_hash("/x/folder", "t01.flac", 101, 2.5, sha256="cc", db_path=db_path)
            row = db.get_file_hash("/x/folder", "t01.flac", db_path=db_path)
            assert row["md5"] is None and row["sha256"] == "cc"
            assert row["size"] == 101 and row["mtime"] == 2.5
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_folder_hashes_keyed_by_rel_path(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            db.upsert_file_hash("/x/f", "a.flac", 1, 1.0, sha256="aa", db_path=db_path)
            db.upsert_file_hash("/x/f", "sub/b.flac", 2, 2.0, sha256="bb", db_path=db_path)
            db.upsert_file_hash("/x/other", "c.flac", 3, 3.0, sha256="cc", db_path=db_path)
            rows = db.get_folder_hashes("/x/f", db_path=db_path)
            assert set(rows) == {"a.flac", "sub/b.flac"}
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestFolderState:
    def test_round_trip_merge_and_discard(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            db.put_folder_state("/x/f", "fp1", {"verify": {"status": "ok"}}, db_path=db_path)
            state = db.get_folder_state("/x/f", db_path=db_path)
            assert state["fingerprint"] == "fp1"
            assert state["steps"]["verify"]["status"] == "ok"
            assert state["steps_run"] == ["verify"]

            # Same fingerprint: partial update merges, verify survives.
            db.put_folder_state("/x/f", "fp1", {"lookup": {"lb_number": 5}}, db_path=db_path)
            state = db.get_folder_state("/x/f", db_path=db_path)
            assert state["steps"]["verify"]["status"] == "ok"
            assert state["steps"]["lookup"]["lb_number"] == 5
            assert state["steps_run"] == ["lookup", "verify"]

            # New fingerprint: previous verdicts described different bytes — gone.
            db.put_folder_state("/x/f", "fp2", {"verify": {"status": "warn"}}, db_path=db_path)
            state = db.get_folder_state("/x/f", db_path=db_path)
            assert state["fingerprint"] == "fp2"
            assert "lookup" not in state["steps"]
            assert state["steps"]["verify"]["status"] == "warn"
            assert state["steps_run"] == ["verify"]
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_step_rejected(self):
        db_path, conn, tmp = _make_db()
        try:
            import pytest

            import backend.db as db
            with pytest.raises(ValueError):
                db.put_folder_state("/x/f", "fp", {"evil; DROP": {}}, db_path=db_path)
            assert db.get_folder_state("/x/f", db_path=db_path) is None
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestDeriveTreeDigest:
    def test_matches_hash_tree_cold_and_warm(self):
        db_path, conn, tmp = _make_db()
        try:
            from pathlib import Path

            import backend.db as db
            from backend.filer import hash_tree, normalise_path
            root = _make_folder(tmp)

            expected = hash_tree(Path(root))
            # Cold cache: every file read fresh, written through — except the
            # surrogate-named file, which is uncacheable (SQLite TEXT cannot
            # bind lone surrogates) and is always hashed fresh instead.
            assert db.derive_tree_digest(root, db_path=db_path) == expected
            rows = db.get_folder_hashes(root, db_path=db_path)
            assert len(rows) == 4 and all(r["sha256"] for r in rows.values())
            assert not any("info" in k for k in rows)
            # Warm cache: every file served from cache — still identical.
            assert db.derive_tree_digest(root, db_path=db_path) == expected
            # Cache keys use the same normalised folder path filing will use.
            assert db.get_folder_hashes(normalise_path(root), db_path=db_path) == rows
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stale_cache_row_falls_back_to_fresh_read(self):
        db_path, conn, tmp = _make_db()
        try:
            from pathlib import Path

            import backend.db as db
            from backend.filer import hash_tree
            root = _make_folder(tmp)
            expected = hash_tree(Path(root))

            # Poison the cache with a wrong sha256 under STALE stats (R1: a
            # (size, mtime) mismatch is a miss, so the poison is never used).
            db.upsert_file_hash(root, "t01.flac", 1, 1.0, sha256="00" * 32, db_path=db_path)
            assert db.derive_tree_digest(root, db_path=db_path) == expected
            # The stale row was overwritten by the fresh write-through.
            st = os.stat(os.path.join(root, "t01.flac"))
            row = db.get_file_hash(root, "t01.flac", db_path=db_path)
            assert row["size"] == st.st_size and row["mtime"] == st.st_mtime
            assert row["sha256"] != "00" * 32
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TestPruneAndExportSafety:
    def test_tables_registered_as_user_tables(self):
        import backend.db as db
        assert "pipeline_file_hash" in db.USER_TABLES
        assert "pipeline_folder_state" in db.USER_TABLES

    def test_prune_missing_folder_and_age(self):
        db_path, conn, tmp = _make_db()
        try:
            import backend.db as db
            root = _make_folder(tmp)  # exists
            db.upsert_file_hash(root, "t01.flac", 1, 1.0, sha256="aa", db_path=db_path)
            db.put_folder_state(root, "fp", {"verify": {}}, db_path=db_path)
            db.upsert_file_hash("/gone/folder", "x.flac", 1, 1.0, sha256="bb", db_path=db_path)
            db.put_folder_state("/gone/folder", "fp", {"verify": {}}, db_path=db_path)

            res = db.prune_pipeline_cache(db_path=db_path)
            assert res == {"file_hash_deleted": 1, "folder_state_deleted": 1}
            assert db.get_file_hash(root, "t01.flac", db_path=db_path) is not None
            assert db.get_file_hash("/gone/folder", "x.flac", db_path=db_path) is None

            # Age cap: backdate the surviving rows, then prune with a 0-day cap
            # would delete everything — use an explicit old timestamp instead.
            conn.execute("UPDATE pipeline_file_hash SET hashed_at=datetime('now','-400 days')")
            conn.execute("UPDATE pipeline_folder_state SET updated_at=datetime('now','-400 days')")
            conn.commit()
            res = db.prune_pipeline_cache(max_age_days=365, db_path=db_path)
            assert res == {"file_hash_deleted": 1, "folder_state_deleted": 1}
            assert db.get_folder_state(root, db_path=db_path) is None
        finally:
            conn.close()
            shutil.rmtree(tmp, ignore_errors=True)
