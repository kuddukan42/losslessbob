"""Tests for the file-level collection integrity system (TODO-267).

Covers the behaviour that distinguishes this from the existing stat-keyed
``pipeline_file_hash`` cache and the manifest-driven integrity monitor:

  - ``index`` mode baselines every file, then skips unchanged files on a second
    run (no re-read).
  - ``verify`` mode detects **bit rot** — content changed while size and mtime
    stayed identical — and preserves the known-good baseline hash rather than
    overwriting it.
  - A legitimate edit (content *and* mtime moved) is classified ``changed`` and
    re-baselined, not reported as rot.
  - An inventoried file removed from disk is classified ``missing``, and only on
    a complete pass — a cancelled run must not declare the remainder missing.
  - ``verify_batch`` draws in oldest-``last_verified`` order so successive runs
    advance through the collection instead of re-checking the same head.

Never touches the real data/losslessbob.db — all tests use temp-file DBs.
"""

import os
import tempfile
import threading

import pytest


def _make_db():
    """Create a fresh temp DB with the full schema; rebind default DB_PATH globals.

    Returns:
        (db_path, conn, tmp_dir, restore) — call restore() in a finally block.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbfileintegrity_test_")
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


def _make_mount(tmp_dir: str, n_files: int = 4) -> tuple[int, str]:
    """Create a collection mount on disk plus its collection_mounts row.

    Args:
        tmp_dir: Temp directory to build under.
        n_files: Number of .flac files to create in the LB folder.

    Returns:
        (mount_id, mount_root).
    """
    import backend.db as db

    root = os.path.join(tmp_dir, "MOUNT")
    folder = os.path.join(root, "1975-05-03 Somewhere (LB-99999)")
    os.makedirs(folder)
    for i in range(n_files):
        with open(os.path.join(folder, f"t{i:02d}.flac"), "wb") as f:
            f.write(f"audio-track-{i}-".encode() * 300)

    mount_id = db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_mounts(label, root_path) VALUES('TEST', ?)",
            (root,),
        ).lastrowid
    )
    # my_collection.lb_number is FK-bound to entries, so the entry must exist.
    db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO entries(lb_number, date_str) VALUES(99999, '1975-05-03')"
        )
    )
    db.get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path) "
            "VALUES(99999, ?, ?)",
            (os.path.basename(folder), folder),
        )
    )
    return mount_id, root


def _rot_file(path: str) -> None:
    """Corrupt a file in place, preserving its size and mtime exactly.

    This is what bit rot looks like to the filesystem: the bytes moved but
    nothing in the stat did. Any stat-keyed cache is blind to it.

    Args:
        path: File to corrupt.
    """
    st = os.stat(path)
    with open(path, "r+b") as f:
        f.seek(0)
        first = f.read(1)
        f.seek(0)
        f.write(b"\x00" if first != b"\x00" else b"\xff")
    os.utime(path, (st.st_atime, st.st_mtime))
    after = os.stat(path)
    assert after.st_size == st.st_size
    assert after.st_mtime == st.st_mtime


def test_index_baselines_then_skips_unchanged():
    """First index hashes everything; second index re-reads nothing."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, _root = _make_mount(tmp_dir, n_files=4)

        first = fi.scan_mount(mount_id, "index")
        assert first["files_seen"] == 4
        assert first["files_hashed"] == 4
        assert first["files_new"] == 4

        rows = conn.execute(
            "SELECT * FROM file_inventory WHERE mount_id=?", (mount_id,)
        ).fetchall()
        assert len(rows) == 4
        assert all(r["xxh3"] and r["sha256"] for r in rows)
        assert all(r["lb_number"] == 99999 for r in rows), "LB ownership resolved"
        assert all(r["status"] == "ok" for r in rows)

        second = fi.scan_mount(mount_id, "index")
        assert second["files_seen"] == 4
        assert second["files_hashed"] == 0, "unchanged files must not be re-read"
    finally:
        restore()


def test_verify_detects_bit_rot_and_keeps_baseline():
    """Content changed with identical size+mtime is rot, and the baseline survives."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, root = _make_mount(tmp_dir, n_files=3)
        fi.scan_mount(mount_id, "index")

        victim = os.path.join(root, "1975-05-03 Somewhere (LB-99999)", "t01.flac")
        baseline = conn.execute(
            "SELECT xxh3 FROM file_inventory WHERE rel_path LIKE '%t01.flac'"
        ).fetchone()["xxh3"]

        _rot_file(victim)

        # An index scan is blind to it — that is exactly why this table exists.
        blind = fi.scan_mount(mount_id, "index")
        assert blind["files_hashed"] == 0
        assert blind["files_rot"] == 0

        # A deep verify catches it.
        result = fi.scan_mount(mount_id, "verify")
        assert result["files_hashed"] == 3
        assert result["files_rot"] == 1
        assert result["files_ok"] == 2

        row = conn.execute(
            "SELECT * FROM file_inventory WHERE rel_path LIKE '%t01.flac'"
        ).fetchone()
        assert row["status"] == "rot"
        assert row["xxh3"] == baseline, "known-good baseline must be preserved"

        event = conn.execute(
            "SELECT * FROM integrity_events WHERE event_type='file_rot'"
        ).fetchone()
        assert event is not None
        assert event["lb_number"] == 99999
    finally:
        restore()


def test_legitimate_edit_is_changed_not_rot():
    """A real edit moves mtime too, so it re-baselines instead of alarming."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, root = _make_mount(tmp_dir, n_files=2)
        fi.scan_mount(mount_id, "index")

        target = os.path.join(root, "1975-05-03 Somewhere (LB-99999)", "t00.flac")
        old = conn.execute(
            "SELECT xxh3 FROM file_inventory WHERE rel_path LIKE '%t00.flac'"
        ).fetchone()["xxh3"]

        with open(target, "ab") as f:
            f.write(b"retagged-metadata")
        os.utime(target, None)

        result = fi.scan_mount(mount_id, "verify")
        assert result["files_rot"] == 0
        assert result["files_changed"] == 1

        row = conn.execute(
            "SELECT * FROM file_inventory WHERE rel_path LIKE '%t00.flac'"
        ).fetchone()
        assert row["status"] == "ok"
        assert row["xxh3"] != old, "edited file must be re-baselined"
    finally:
        restore()


def test_missing_file_flagged_on_complete_pass_only():
    """A deleted file is 'missing'; a cancelled run must not mass-flag."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, root = _make_mount(tmp_dir, n_files=3)
        fi.scan_mount(mount_id, "index")

        os.remove(os.path.join(root, "1975-05-03 Somewhere (LB-99999)", "t02.flac"))

        # A cancelled run stops before the sweep and flags nothing.
        cancelled = threading.Event()
        cancelled.set()
        stopped = fi.scan_mount(mount_id, "index", cancel_event=cancelled)
        assert stopped["files_missing"] == 0
        assert conn.execute(
            "SELECT COUNT(*) c FROM file_inventory WHERE status='missing'"
        ).fetchone()["c"] == 0

        result = fi.scan_mount(mount_id, "index")
        assert result["files_missing"] == 1
        row = conn.execute(
            "SELECT * FROM file_inventory WHERE rel_path LIKE '%t02.flac'"
        ).fetchone()
        assert row["status"] == "missing"
    finally:
        restore()


def test_rolling_verify_advances_through_the_collection():
    """Successive batches pick different files rather than re-checking the head."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, _root = _make_mount(tmp_dir, n_files=6)
        fi.scan_mount(mount_id, "index")

        # Nothing has been verified yet, so all six are equally overdue.
        assert conn.execute(
            "SELECT COUNT(*) c FROM file_inventory WHERE last_verified IS NULL"
        ).fetchone()["c"] == 6

        first = fi.verify_batch(mount_id, limit=3)
        assert first["files_seen"] == 3
        assert first["files_ok"] == 3
        done_after_first = {
            r["rel_path"] for r in conn.execute(
                "SELECT rel_path FROM file_inventory WHERE last_verified IS NOT NULL"
            ).fetchall()
        }
        assert len(done_after_first) == 3

        second = fi.verify_batch(mount_id, limit=3)
        assert second["files_seen"] == 3
        assert conn.execute(
            "SELECT COUNT(*) c FROM file_inventory WHERE last_verified IS NULL"
        ).fetchone()["c"] == 0, "second batch must cover the remaining files"
    finally:
        restore()


def test_rolling_verify_detects_rot():
    """The nightly path finds rot too, not just the full sweep."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        from backend import file_integrity as fi

        mount_id, root = _make_mount(tmp_dir, n_files=2)
        fi.scan_mount(mount_id, "index")
        _rot_file(os.path.join(root, "1975-05-03 Somewhere (LB-99999)", "t00.flac"))

        result = fi.verify_batch(mount_id, limit=10)
        assert result["files_rot"] == 1
        assert result["files_ok"] == 1
    finally:
        restore()


def test_hash_file_matches_reference_digests():
    """Both digests from the single read pass match hashlib/xxhash directly."""
    import hashlib
    from pathlib import Path

    import xxhash

    from backend.file_integrity import hash_file

    tmp_dir = tempfile.mkdtemp(prefix="lbfileintegrity_hash_")
    path = Path(tmp_dir) / "sample.bin"
    payload = os.urandom(9_000_000)  # spans several 4 MB chunks
    path.write_bytes(payload)

    result = hash_file(path)
    assert result["xxh3"] == xxhash.xxh3_128(payload).hexdigest()
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["size"] == len(payload)
    assert result["bytes_read"] == len(payload)


def test_scan_rejects_bad_mode_and_offline_mount():
    """Guard rails: unknown mode and an absent mount root both raise."""
    db_path, conn, tmp_dir, restore = _make_db()
    try:
        import backend.db as db
        from backend import file_integrity as fi

        mount_id, root = _make_mount(tmp_dir, n_files=1)
        with pytest.raises(ValueError):
            fi.scan_mount(mount_id, "bogus")

        offline_id = db.get_write_queue().execute(
            lambda c: c.execute(
                "INSERT INTO collection_mounts(label, root_path) VALUES('GONE', ?)",
                (os.path.join(tmp_dir, "does-not-exist"),),
            ).lastrowid
        )
        with pytest.raises(FileNotFoundError):
            fi.scan_mount(offline_id, "index")
    finally:
        restore()
