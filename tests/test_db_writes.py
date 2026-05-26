"""
Test battery for all database write functions in backend/db.py.

Covers happy-path, idempotency, constraint violations, edge cases, and
deliberate SQL errors to verify rollback and constraint enforcement.
Never touches the real data/losslessbob.db — all tests use temp-file DBs.
"""

import os
import shutil
import sqlite3
import tempfile
import threading

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with the full schema. Returns (db_path, conn, tmp_dir).

    Redirects backend.paths.DATA_DIR so backup_database() never touches
    the real data/ directory.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbwrite_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _seed_entry(conn, lb_number: int, status: str = "ok") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO entries(lb_number, status) VALUES(?,?)",
        (lb_number, status),
    )
    conn.commit()


def _seed_checksum(conn, lb_number: int, chk: str | None = None) -> None:
    chk = chk or f"a{lb_number:031d}"
    conn.execute(
        "INSERT OR IGNORE INTO checksums(checksum, filename, chk_type, lb_number)"
        " VALUES(?,?,?,?)",
        (chk, f"file{lb_number}.flac", "f", lb_number),
    )
    conn.commit()


def _seed_collection(conn, lb_number: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO my_collection(lb_number, folder_name, disk_path)"
        " VALUES(?,?,?)",
        (lb_number, f"folder-{lb_number}", f"/music/{lb_number}"),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# set_meta / get_meta
# ---------------------------------------------------------------------------

class TestSetMeta:
    def test_insert_and_retrieve(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_meta("mykey", "myvalue", db_path)
            assert db.get_meta("mykey", db_path) == "myvalue"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_overwrite_existing(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_meta("k", "v1", db_path)
            db.set_meta("k", "v2", db_path)
            assert db.get_meta("k", db_path) == "v2"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_key_returns_none(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.get_meta("nonexistent", db_path) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_string_value(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_meta("empty", "", db_path)
            assert db.get_meta("empty", db_path) == ""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_none_value(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_meta("nullkey", None, db_path)
            assert db.get_meta("nullkey", db_path) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_very_long_value(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            long_val = "x" * 100_000
            db.set_meta("bigkey", long_val, db_path)
            assert db.get_meta("bigkey", db_path) == long_val
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# my_collection writes
# ---------------------------------------------------------------------------

class TestAddToCollection:
    def test_basic_insert(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 1)
            result = db.add_to_collection(1, "folder-1", "/music/1", db_path=db_path)
            assert result == 1
            row = conn.execute(
                "SELECT folder_name FROM my_collection WHERE lb_number=1"
            ).fetchone()
            assert row is not None
            assert row[0] == "folder-1"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_duplicate_ignored(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 2)
            db.add_to_collection(2, "folder-2", "/music/2", db_path=db_path)
            result = db.add_to_collection(2, "folder-2-dup", "/music/2b", db_path=db_path)
            # OR IGNORE — second call returns 0 changes
            assert result == 0
            count = conn.execute(
                "SELECT COUNT(*) FROM my_collection WHERE lb_number=2"
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_with_notes(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 3)
            db.add_to_collection(3, "f3", "/p3", notes="great show", db_path=db_path)
            row = conn.execute(
                "SELECT notes FROM my_collection WHERE lb_number=3"
            ).fetchone()
            assert row[0] == "great show"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_null_notes(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 4)
            db.add_to_collection(4, "f4", "/p4", db_path=db_path)
            row = conn.execute(
                "SELECT notes FROM my_collection WHERE lb_number=4"
            ).fetchone()
            assert row[0] is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestUpdateCollection:
    def test_update_folder_name(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 10)
            db.add_to_collection(10, "old-name", "/old", db_path=db_path)
            db.update_collection(10, {"folder_name": "new-name"}, db_path=db_path)
            row = conn.execute(
                "SELECT folder_name FROM my_collection WHERE lb_number=10"
            ).fetchone()
            assert row[0] == "new-name"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_disk_path(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 11)
            db.add_to_collection(11, "f11", "/old/path", db_path=db_path)
            db.update_collection(11, {"disk_path": "/new/path"}, db_path=db_path)
            row = conn.execute(
                "SELECT disk_path FROM my_collection WHERE lb_number=11"
            ).fetchone()
            assert row[0] == "/new/path"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_disallowed_fields_are_no_op(self):
        """Fields not in the allowlist must never reach the database."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 12)
            db.add_to_collection(12, "f12", "/p12", db_path=db_path)
            # 'confirmed_at' and 'lb_number' are NOT in the allowed set
            db.update_collection(12, {"confirmed_at": "evil", "lb_number": 999},
                                 db_path=db_path)
            row = conn.execute(
                "SELECT lb_number, confirmed_at FROM my_collection WHERE lb_number=12"
            ).fetchone()
            # lb_number must still be 12, not 999
            assert row["lb_number"] == 12
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_empty_fields_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 13)
            db.add_to_collection(13, "f13", "/p13", db_path=db_path)
            # No exception, no change
            db.update_collection(13, {}, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_nonexistent_lb_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.update_collection(99999, {"folder_name": "ghost"}, db_path=db_path)
            count = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDeleteFromCollection:
    def test_delete_existing(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 20)
            db.add_to_collection(20, "f20", "/p20", db_path=db_path)
            db.delete_from_collection(20, db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM my_collection WHERE lb_number=20"
            ).fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_nonexistent_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.delete_from_collection(99999, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDeleteCollectionEntries:
    def test_bulk_delete(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            for lb in (30, 31, 32):
                _seed_entry(conn, lb)
                _seed_collection(conn, lb)
            deleted = db.delete_collection_entries([30, 31], db_path=db_path)
            assert deleted == 2
            remaining = conn.execute(
                "SELECT lb_number FROM my_collection"
            ).fetchall()
            assert [r[0] for r in remaining] == [32]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_list_returns_zero(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            result = db.delete_collection_entries([], db_path=db_path)
            assert result == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cascades_to_collection_meta(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 40)
            _seed_collection(conn, 40)
            db.set_collection_meta(40, {"personal_rating": 5}, db_path=db_path)
            db.delete_collection_entries([40], db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM collection_meta WHERE lb_number=40"
            ).fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cascades_to_integrity_events(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 41)
            _seed_collection(conn, 41)
            conn.execute(
                "INSERT INTO integrity_events(lb_number, event_type, detail)"
                " VALUES(41, 'deleted', 'test')"
            )
            conn.commit()
            db.delete_collection_entries([41], db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM integrity_events WHERE lb_number=41"
            ).fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# collection_meta writes
# ---------------------------------------------------------------------------

class TestSetCollectionMeta:
    def test_upsert_creates_row(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 50)
            _seed_collection(conn, 50)
            db.set_collection_meta(50, {"personal_rating": 4, "listen_count": 2},
                                   db_path=db_path)
            row = db.get_collection_meta(50, db_path)
            assert row["personal_rating"] == 4
            assert row["listen_count"] == 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upsert_updates_existing(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 51)
            _seed_collection(conn, 51)
            db.set_collection_meta(51, {"personal_rating": 3}, db_path=db_path)
            db.set_collection_meta(51, {"personal_rating": 5}, db_path=db_path)
            assert db.get_collection_meta(51, db_path)["personal_rating"] == 5
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_disallowed_fields_ignored(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 52)
            _seed_collection(conn, 52)
            # 'lb_number' is not in the allowed set — must be silently ignored
            db.set_collection_meta(52, {"lb_number": 999}, db_path=db_path)
            assert db.get_collection_meta(52, db_path)["lb_number"] == 52
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_fields_dict_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 53)
            _seed_collection(conn, 53)
            db.set_collection_meta(53, {}, db_path=db_path)
            # No row should be created
            row = conn.execute(
                "SELECT COUNT(*) FROM collection_meta WHERE lb_number=53"
            ).fetchone()[0]
            assert row == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_personal_rating_constraint_violation(self):
        """personal_rating CHECK(BETWEEN 1 AND 5) — value 6 must raise IntegrityError."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 54)
            _seed_collection(conn, 54)
            # First insert creates the row; second UPDATE enforces CHECK
            db.set_collection_meta(54, {"personal_rating": 1}, db_path=db_path)
            with pytest.raises(sqlite3.IntegrityError):
                db.set_collection_meta(54, {"personal_rating": 6}, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rating_zero_constraint_violation(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 55)
            _seed_collection(conn, 55)
            db.set_collection_meta(55, {"personal_rating": 1}, db_path=db_path)
            with pytest.raises(sqlite3.IntegrityError):
                db.set_collection_meta(55, {"personal_rating": 0}, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestIncrementListenCount:
    def test_first_increment_creates_row(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 60)
            _seed_collection(conn, 60)
            db.increment_listen_count(60, db_path=db_path)
            assert db.get_collection_meta(60, db_path)["listen_count"] == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_multiple_increments_accumulate(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 61)
            _seed_collection(conn, 61)
            for _ in range(5):
                db.increment_listen_count(61, db_path=db_path)
            assert db.get_collection_meta(61, db_path)["listen_count"] == 5
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_last_listened_is_set(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 62)
            _seed_collection(conn, 62)
            db.increment_listen_count(62, db_path=db_path)
            meta = db.get_collection_meta(62, db_path)
            assert meta["last_listened"] is not None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Wishlist writes
# ---------------------------------------------------------------------------

class TestWishlist:
    def test_add_and_retrieve(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 70)
            result = db.add_to_wishlist(70, priority=4, db_path=db_path)
            assert result == 1
            lbs = db.get_wishlist_lb_numbers(db_path)
            assert 70 in lbs
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_duplicate_ignored(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 71)
            db.add_to_wishlist(71, db_path=db_path)
            result = db.add_to_wishlist(71, db_path=db_path)
            assert result == 0
            count = conn.execute(
                "SELECT COUNT(*) FROM my_wishlist WHERE lb_number=71"
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_remove_from_wishlist(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 72)
            db.add_to_wishlist(72, db_path=db_path)
            db.remove_from_wishlist(72, db_path=db_path)
            assert 72 not in db.get_wishlist_lb_numbers(db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_remove_nonexistent_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.remove_from_wishlist(99999, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_priority_check_constraint_violation(self):
        """priority CHECK(BETWEEN 1 AND 5) — value 6 must fail."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 73)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO my_wishlist(lb_number, priority) VALUES(73, 10)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_priority_zero_constraint_violation(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 74)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO my_wishlist(lb_number, priority) VALUES(74, 0)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# record_entry_changes
# ---------------------------------------------------------------------------

class TestRecordEntryChanges:
    def test_detects_changed_fields(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries(lb_number, location, rating, status)"
                " VALUES(100, 'Old Location', 'A', 'ok')"
            )
            conn.commit()
            changed = db.record_entry_changes(
                100,
                {"location": "New Location", "rating": "A", "status": "ok"},
                db_path=db_path,
            )
            assert "location" in changed
            assert "rating" not in changed
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_changes_returns_empty(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries(lb_number, location, status) VALUES(101, 'X', 'ok')"
            )
            conn.commit()
            changed = db.record_entry_changes(
                101,
                {"location": "X", "status": "ok"},
                db_path=db_path,
            )
            assert changed == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nonexistent_lb_returns_empty(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            changed = db.record_entry_changes(
                99999, {"location": "anywhere"}, db_path=db_path
            )
            assert changed == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_change_logged_to_entry_changes_table(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries(lb_number, location, status) VALUES(102, 'A', 'ok')"
            )
            conn.commit()
            # Pass all tracked fields so only location differs
            db.record_entry_changes(
                102,
                {"location": "B", "status": "ok", "date_str": None, "cdr": None,
                 "rating": None, "timing": None, "description": None, "setlist": None},
                db_path=db_path,
            )
            log = conn.execute(
                "SELECT field, old_value, new_value FROM entry_changes WHERE lb_number=102"
            ).fetchall()
            location_rows = [r for r in log if r["field"] == "location"]
            assert len(location_rows) == 1
            assert location_rows[0]["old_value"] == "A"
            assert location_rows[0]["new_value"] == "B"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_old_none_vs_new_empty_string_is_change(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            # NULL location in DB
            conn.execute(
                "INSERT INTO entries(lb_number, location, status) VALUES(103, NULL, 'ok')"
            )
            conn.commit()
            changed = db.record_entry_changes(
                103, {"location": ""}, db_path=db_path
            )
            assert "location" in changed
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_multiple_fields_changed(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries(lb_number, location, rating, timing, status)"
                " VALUES(104, 'X', 'A', '60m', 'ok')"
            )
            conn.commit()
            changed = db.record_entry_changes(
                104,
                {"location": "Y", "rating": "B", "timing": "60m", "status": "ok"},
                db_path=db_path,
            )
            assert set(changed) == {"location", "rating"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# insert_missing_entry
# ---------------------------------------------------------------------------

class TestInsertMissingEntry:
    def test_insert_creates_row(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.insert_missing_entry(200, db_path=db_path)
            row = conn.execute(
                "SELECT status FROM entries WHERE lb_number=200"
            ).fetchone()
            assert row is not None
            assert row[0] == "missing"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_insert_idempotent(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.insert_missing_entry(201, db_path=db_path)
            db.insert_missing_entry(201, db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE lb_number=201"
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_does_not_overwrite_existing_ok(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 202, status="ok")
            db.insert_missing_entry(202, db_path=db_path)
            row = conn.execute(
                "SELECT status FROM entries WHERE lb_number=202"
            ).fetchone()
            assert row[0] == "ok"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# lb_master writes: reconcile, manual override, clear
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# lb_missing table and 'nonexistent' status (TODO-102)
# ---------------------------------------------------------------------------

class TestLbMissing:
    """lb_missing table: seeding, CRUD, reconcile integration, scraper skip."""

    def test_seeds_present_after_init(self):
        """init_db() must seed the 36 confirmed-not-existing LB numbers."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            count = conn.execute("SELECT COUNT(*) FROM lb_missing").fetchone()[0]
            assert count == 36, f"Expected 36 seed rows, got {count}"
            # Spot-check a few known entries
            for lb in (7, 36, 14215):
                row = conn.execute(
                    "SELECT lb_number FROM lb_missing WHERE lb_number=?", (lb,)
                ).fetchone()
                assert row is not None, f"LB-{lb:05d} missing from lb_missing seeds"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_is_lb_missing_true_for_seed(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.is_lb_missing(7, db_path) is True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_is_lb_missing_false_for_normal(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.is_lb_missing(1, db_path) is False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reconcile_nonexistent_status(self):
        """reconcile_lb_status must set lb_status='nonexistent' for lb_missing entries."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            status = db.reconcile_lb_status(7, db_path=db_path)
            assert status == "nonexistent"
            row = db.get_lb_master_row(7, db_path)
            assert row is not None
            assert row["lb_status"] == "nonexistent"
            assert row["has_webpage"] == 0
            assert row["has_checksums"] == 0
            assert row["public_no_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_batch_reconcile_nonexistent_status(self):
        """batch_reconcile_lb_status must give 'nonexistent' for lb_missing entries."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.batch_reconcile_lb_status([7, 36], trigger="test", db_path=db_path)
            for lb in (7, 36):
                row = db.get_lb_master_row(lb, db_path)
                assert row is not None
                assert row["lb_status"] == "nonexistent", f"LB-{lb} should be nonexistent"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_add_and_remove_lb_missing(self):
        """add_lb_missing / remove_lb_missing round-trip."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_missing(9999, confirmed_date="2026-01-01", notes="test", db_path=db_path)
            assert db.is_lb_missing(9999, db_path) is True
            row = db.get_lb_master_row(9999, db_path)
            assert row is not None and row["lb_status"] == "nonexistent"

            db.remove_lb_missing(9999, db_path=db_path)
            assert db.is_lb_missing(9999, db_path) is False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_scrape_entry_skips_lb_missing(self):
        """scrape_entry must return {skipped: True, reason: 'nonexistent'} for lb_missing LBs."""
        from backend.scraper import scrape_entry
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            result = scrape_entry(7, db_path=db_path)
            assert result.get("skipped") is True
            assert result.get("reason") == "nonexistent"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_lb_missing_list(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            rows = db.get_lb_missing_list(db_path)
            assert len(rows) == 36
            assert all("lb_number" in r for r in rows)
            # Must be ordered by lb_number
            nums = [r["lb_number"] for r in rows]
            assert nums == sorted(nums)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# public_no_checksums flag (TODO-098)
# ---------------------------------------------------------------------------

class TestPublicNoChecksums_Flag:
    """public_no_checksums column in lb_master must be set/cleared correctly."""

    def test_flag_set_for_public_no_checksums(self):
        """Entry with status='ok' and no checksums → public_no_checksums=1."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 500, "ok")
            db.reconcile_lb_status(500, db_path=db_path)
            row = db.get_lb_master_row(500, db_path)
            assert row["lb_status"] == "public"
            assert row["has_checksums"] == 0
            assert row["public_no_checksums"] == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flag_clear_for_public_with_checksums(self):
        """Entry with status='ok' AND checksums → public_no_checksums=0."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 501, "ok")
            _seed_checksum(conn, 501)
            db.reconcile_lb_status(501, db_path=db_path)
            row = db.get_lb_master_row(501, db_path)
            assert row["lb_status"] == "public"
            assert row["has_checksums"] == 1
            assert row["public_no_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flag_clear_for_private(self):
        """Checksums-only entry (private) → public_no_checksums=0."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 502)
            db.reconcile_lb_status(502, db_path=db_path)
            row = db.get_lb_master_row(502, db_path)
            assert row["lb_status"] == "private"
            assert row["public_no_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flag_clear_for_missing(self):
        """'missing' entry → public_no_checksums=0."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.insert_missing_entry(503, db_path=db_path)
            db.reconcile_lb_status(503, db_path=db_path)
            row = db.get_lb_master_row(503, db_path)
            assert row["lb_status"] == "missing"
            assert row["public_no_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flag_transitions_when_checksums_added(self):
        """Adding checksums to a public-no-checksums entry must clear the flag."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 504, "ok")
            db.reconcile_lb_status(504, db_path=db_path)
            assert db.get_lb_master_row(504, db_path)["public_no_checksums"] == 1

            _seed_checksum(conn, 504)
            db.reconcile_lb_status(504, db_path=db_path)
            assert db.get_lb_master_row(504, db_path)["public_no_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stats_returns_public_no_checksums_count(self):
        """get_lb_master_stats must include public_no_checksums count."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 505, "ok")
            _seed_entry(conn, 506, "ok")
            _seed_checksum(conn, 506)  # 505 = public+no-chk, 506 = public+chk
            db.batch_reconcile_lb_status([505, 506], trigger="test", db_path=db_path)
            stats = db.get_lb_master_stats(db_path)
            assert stats["public_no_checksums"] >= 1
            assert "nonexistent" in stats
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Public page, no checksums — regression guard for BUG-116
# ---------------------------------------------------------------------------

class TestPublicNoChecksums:
    """LB with a public webpage but zero checksums must be classified 'public', not 'missing'.

    LB-1506 is a real-world example: the archive page exists but the flat file
    contains no checksum entries for it.  All reconcile paths must agree.
    """

    def test_reconcile_single_public_no_checksums(self):
        """reconcile_lb_status: status='ok' entry with no checksums → lb_status='public'."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 1506, "ok")
            status = db.reconcile_lb_status(1506, db_path=db_path)
            assert status == "public", f"Expected 'public', got '{status}'"
            row = db.get_lb_master_row(1506, db_path)
            assert row is not None
            assert row["lb_status"] == "public"
            assert row["has_webpage"] == 1
            assert row["has_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_batch_reconcile_public_no_checksums(self):
        """batch_reconcile_lb_status: same scenario via the batch (scrape_range) path."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 1506, "ok")
            db.batch_reconcile_lb_status([1506], trigger="scrape", db_path=db_path)
            row = db.get_lb_master_row(1506, db_path)
            assert row is not None
            assert row["lb_status"] == "public"
            assert row["has_webpage"] == 1
            assert row["has_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_previously_missing_gains_webpage_no_checksums(self):
        """If lb_master starts as 'missing' then a page is scraped (still no checksums),
        reconcile must transition it to 'public'."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            # Establish a missing row first (simulates a prior 404 scrape)
            db.insert_missing_entry(1506, db_path=db_path)
            db.reconcile_lb_status(1506, db_path=db_path)
            assert db.get_lb_master_row(1506, db_path)["lb_status"] == "missing"

            # Page appears on site — entry is now ok, still no checksums
            conn.execute(
                "UPDATE entries SET status='ok' WHERE lb_number=1506"
            )
            conn.commit()
            status = db.reconcile_lb_status(1506, db_path=db_path)
            assert status == "public"
            row = db.get_lb_master_row(1506, db_path)
            assert row["lb_status"] == "public"
            assert row["has_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_public_no_checksums_absent_from_missing_list(self):
        """get_missing_lb_numbers must not return an LB whose entry has status='ok',
        even if that LB has no checksums."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 1506, "ok")
            missing = db.get_missing_lb_numbers(db_path)
            assert 1506 not in missing
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reconcile_all_no_checksums_public_entry(self):
        """reconcile_all_lb_master must not bail out when checksums table is empty.

        Regression for BUG-116: effective_max was computed from checksums and lb_master
        only, so a fresh DB with a scraped entries row (status='ok') but no checksums
        yielded effective_max=0 and returned early without reconciling anything.
        """
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 1506, "ok")
            stats = db.reconcile_all_lb_master(db_path=db_path)
            assert stats.get("public", 0) >= 1, (
                f"Expected at least one 'public' entry, got stats={stats}"
            )
            row = db.get_lb_master_row(1506, db_path)
            assert row is not None, "LB-1506 should exist in lb_master after reconcile_all"
            assert row["lb_status"] == "public"
            assert row["has_webpage"] == 1
            assert row["has_checksums"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_compute_lb_status_web_only(self):
        """Unit-test _compute_lb_status directly: (True, False, False) → 'public'."""
        from backend.db import _compute_lb_status
        status, needs_review = _compute_lb_status(has_web=True, has_chk=False, has_att=False)
        assert status == "public"
        assert needs_review == 0


class TestReconcileAndOverride:
    def test_reconcile_new_entry_inserts_lb_master(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 300)
            _seed_entry(conn, 300, "ok")
            status = db.reconcile_lb_status(300, db_path=db_path)
            assert status == "public"
            row = db.get_lb_master_row(300, db_path)
            assert row is not None
            assert row["has_webpage"] == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reconcile_transition_logged(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 301)
            db.reconcile_lb_status(301, db_path=db_path)   # private
            _seed_entry(conn, 301, "ok")
            db.reconcile_lb_status(301, db_path=db_path)   # → public
            hist = db.get_lb_status_history(301, db_path=db_path)
            transitions = [(h["old_status"], h["new_status"]) for h in hist]
            assert ("private", "public") in transitions
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manual_override_blocks_reconcile(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 302)
            _seed_entry(conn, 302, "ok")
            db.reconcile_lb_status(302, db_path=db_path)
            db.set_lb_manual_override(302, "private", "test", db_path=db_path)
            # reconcile must NOT flip back to public
            status = db.reconcile_lb_status(302, db_path=db_path)
            assert status == "private"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clear_override_restores_auto_status(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 303)
            _seed_entry(conn, 303, "ok")
            db.reconcile_lb_status(303, db_path=db_path)
            db.set_lb_manual_override(303, "private", "test", db_path=db_path)
            new_status = db.clear_lb_manual_override(303, db_path=db_path)
            assert new_status == "public"
            row = db.get_lb_master_row(303, db_path)
            assert row["manual_override"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_set_manual_override_invalid_status_raises(self):
        """lb_master.lb_status CHECK — invalid value must raise IntegrityError."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 304)
            db.reconcile_lb_status(304, db_path=db_path)
            with pytest.raises(sqlite3.IntegrityError):
                db.set_lb_manual_override(
                    304, "invalid_status", "oops", db_path=db_path
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_set_lb_manual_override_logs_history(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 305)
            db.reconcile_lb_status(305, db_path=db_path)
            db.set_lb_manual_override(305, "missing", "test", db_path=db_path)
            hist = db.get_lb_status_history(305, db_path=db_path)
            manual_rows = [h for h in hist if h["new_status"] == "missing"]
            assert len(manual_rows) >= 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manual_override_upsert_on_existing_row(self):
        """set_lb_manual_override on an already-overridden row must update, not insert."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 306)
            db.reconcile_lb_status(306, db_path=db_path)
            db.set_lb_manual_override(306, "public", "first", db_path=db_path)
            db.set_lb_manual_override(306, "private", "second", db_path=db_path)
            row = db.get_lb_master_row(306, db_path)
            assert row["lb_status"] == "private"
            assert row["manual_notes"] == "second"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_lb_master_row_missing_returns_none(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.get_lb_master_row(99999, db_path) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# export_overrides / import_overrides
# ---------------------------------------------------------------------------

class TestOverridesExportImport:
    def test_export_only_returns_overrides(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            for lb in (400, 401, 402):
                _seed_checksum(conn, lb)
                db.reconcile_lb_status(lb, db_path=db_path)
            db.set_lb_manual_override(401, "missing", "test", db_path=db_path)
            rows = db.export_overrides(db_path)
            lbs = [r["lb_number"] for r in rows]
            assert 401 in lbs
            assert 400 not in lbs
            assert 402 not in lbs
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_import_overrides_applies_valid(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            for lb in (410, 411):
                _seed_checksum(conn, lb)
                db.reconcile_lb_status(lb, db_path=db_path)
            overrides = [
                {"lb_number": 410, "manual_status": "private", "manual_notes": "nope"},
                {"lb_number": 411, "manual_status": "public", "manual_notes": "yes"},
            ]
            result = db.import_overrides(overrides, db_path=db_path)
            assert result["imported"] == 2
            assert result["skipped"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_import_overrides_skips_out_of_range_lb(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 420)
            db.reconcile_lb_status(420, db_path=db_path)
            overrides = [
                {"lb_number": 0},           # too low
                {"lb_number": -5},          # negative
                {"lb_number": 999999},      # beyond max
            ]
            result = db.import_overrides(overrides, db_path=db_path)
            assert result["skipped"] == 3
            assert result["imported"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_import_overrides_skips_non_int_lb(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_checksum(conn, 430)
            db.reconcile_lb_status(430, db_path=db_path)
            overrides = [
                {"lb_number": "not_an_int"},
                {"lb_number": None},
                {"lb_number": 1.5},
                {},                          # missing key entirely
            ]
            result = db.import_overrides(overrides, db_path=db_path)
            assert result["skipped"] == 4
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_import_empty_list_returns_zeros(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            result = db.import_overrides([], db_path=db_path)
            assert result["imported"] == 0
            assert result["skipped"] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# lb_alias writes
# ---------------------------------------------------------------------------

class TestLbAlias:
    def test_add_basic_alias(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            result = db.add_lb_alias(500, 501, db_path=db_path)
            assert result["alias_lb"] == 500
            assert result["canonical_lb"] == 501
            assert result["rewrote_chain"] is False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_self_alias_raises(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(ValueError, match="must differ"):
                db.add_lb_alias(502, 502, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cycle_detection(self):
        """Inserting a back-edge must be prevented, either by ValueError or IntegrityError.

        add_lb_alias(503, 504) stores row (alias=503, canonical=504).
        add_lb_alias(504, 503) attempts canonical=503 which itself maps to 504;
        chain-rewrite resolves canonical to 504, alias_lb==canonical_lb, triggering
        the CHECK constraint — so IntegrityError is the observed behavior here.
        """
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_alias(503, 504, db_path=db_path)
            with pytest.raises((ValueError, sqlite3.IntegrityError)):
                db.add_lb_alias(504, 503, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_chain_rewrite(self):
        """Adding X→Y when Y→Z already exists should flatten to X→Z."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_alias(510, 511, db_path=db_path)   # 510 → 511
            result = db.add_lb_alias(512, 510, db_path=db_path)  # 512 → 510 → rewrites to 511
            assert result["rewrote_chain"] is True
            assert result["canonical_lb"] == 511
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_alias(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_alias(520, 521, db_path=db_path)
            db.delete_lb_alias(520, db_path=db_path)
            aliases = db.get_lb_aliases(canonical_lb=521, db_path=db_path)
            assert all(a["alias_lb"] != 520 for a in aliases)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_nonexistent_alias_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.delete_lb_alias(99999, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolve_aliases(self):
        """resolve_aliases deduplicates canonical results (order-preserving first-seen).

        530→531 (alias). 531 is canonical. 532 is unrelated.
        [530, 531, 532] all resolve: 530→531, 531→531, 532→532.
        After dedup: [531, 532] — 531 appears only once.
        """
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_alias(530, 531, db_path=db_path)
            result = db.resolve_aliases([530, 531, 532], db_path=db_path)
            # 530 resolves to 531; 531 is already canonical; dedup → [531, 532]
            assert result[0] == 531
            assert result[1] == 532
            assert 531 not in result[1:]  # only first occurrence of 531 kept
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolve_aliases_deduplication(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_lb_alias(540, 541, db_path=db_path)
            # 540 and 541 both resolve to 541 — result should have 541 only once
            result = db.resolve_aliases([540, 541], db_path=db_path)
            assert result.count(541) == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolve_empty_list(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.resolve_aliases([], db_path=db_path) == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_alias_check_constraint_same_lb_via_sql(self):
        """The CHECK(alias_lb != canonical_lb) fires at the DB level too."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO lb_alias(alias_lb, canonical_lb, relationship)"
                    " VALUES(550, 550, 'duplicate')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# folder_lb_link writes
# ---------------------------------------------------------------------------

class TestFolderLink:
    def test_set_and_get(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_folder_link("/music/folder1", 600, note="test", db_path=db_path)
            result = db.get_folder_link("/music/folder1", db_path=db_path)
            assert result is not None
            assert result["lb_number"] == 600
            assert result["note"] == "test"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_replace_existing(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_folder_link("/music/folder2", 601, db_path=db_path)
            db.set_folder_link("/music/folder2", 602, db_path=db_path)
            result = db.get_folder_link("/music/folder2", db_path=db_path)
            assert result["lb_number"] == 602
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_existing(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_folder_link("/music/folder3", 603, db_path=db_path)
            db.delete_folder_link("/music/folder3", db_path=db_path)
            assert db.get_folder_link("/music/folder3", db_path=db_path) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_nonexistent_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.delete_folder_link("/nonexistent/path", db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_nonexistent_returns_none(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            assert db.get_folder_link("/does/not/exist", db_path=db_path) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_note(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.set_folder_link("/music/folder4", 604, note="", db_path=db_path)
            result = db.get_folder_link("/music/folder4", db_path=db_path)
            assert result["note"] == ""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Torrent writes
# ---------------------------------------------------------------------------

class TestTorrentWrites:
    def test_add_torrent_record(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 700)
            row_id = db.add_torrent_record(
                700, "/path/to.torrent", "/music/700",
                "aabbcc1122", db_path=db_path
            )
            assert isinstance(row_id, int) and row_id > 0
            rows = db.get_torrents_for_lb(700, db_path=db_path)
            assert len(rows) == 1
            assert rows[0]["infohash"] == "aabbcc1122"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_add_multiple_torrents_for_same_lb(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 701)
            db.add_torrent_record(701, "/p1.torrent", "/m/701", "hash1", db_path=db_path)
            db.add_torrent_record(701, "/p2.torrent", "/m/701", "hash2", db_path=db_path)
            assert len(db.get_torrents_for_lb(701, db_path=db_path)) == 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_add_torrent_with_excluded_files(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 702)
            row_id = db.add_torrent_record(
                702, "/t.torrent", "/m/702", "hash3",
                excluded_files=["file1.txt", "cover.jpg"],
                db_path=db_path,
            )
            import json
            row = conn.execute(
                "SELECT excluded_files FROM torrents WHERE id=?", (row_id,)
            ).fetchone()
            assert json.loads(row[0]) == ["file1.txt", "cover.jpg"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_torrent_record_allowed_field(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 703)
            row_id = db.add_torrent_record(
                703, "/t.torrent", "/m/703", "hash4", db_path=db_path
            )
            db.update_torrent_record(
                row_id, {"added_to_qbt": 1}, db_path=db_path
            )
            row = conn.execute(
                "SELECT added_to_qbt FROM torrents WHERE id=?", (row_id,)
            ).fetchone()
            assert row[0] == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_torrent_disallowed_fields_are_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 704)
            row_id = db.add_torrent_record(
                704, "/t.torrent", "/m/704", "hash5", db_path=db_path
            )
            db.update_torrent_record(row_id, {"lb_number": 9999}, db_path=db_path)
            row = conn.execute(
                "SELECT lb_number FROM torrents WHERE id=?", (row_id,)
            ).fetchone()
            assert row[0] == 704
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_torrent_empty_dict_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 705)
            row_id = db.add_torrent_record(
                705, "/t.torrent", "/m/705", "hash6", db_path=db_path
            )
            db.update_torrent_record(row_id, {}, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Forum post writes
# ---------------------------------------------------------------------------

class TestForumPostWrites:
    def test_add_forum_post_returns_id(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 800)
            post_id = db.add_forum_post(
                800, "Subject", "https://forum.example/t/1", 7, db_path=db_path
            )
            assert isinstance(post_id, int) and post_id > 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_forum_posts_for_lb(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 801)
            db.add_forum_post(801, "Post A", "https://x/1", 1, db_path=db_path)
            db.add_forum_post(801, "Post B", "https://x/2", 2, db_path=db_path)
            posts = db.get_forum_posts_for_lb(801, db_path=db_path)
            assert len(posts) == 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_forum_post(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 802)
            post_id = db.add_forum_post(802, "X", "https://x/1", None, db_path=db_path)
            db.delete_forum_post(post_id, db_path=db_path)
            posts = db.get_forum_posts_for_lb(802, db_path=db_path)
            assert posts == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_nonexistent_post_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.delete_forum_post(99999, db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_forum_post_not_null_lb_number(self):
        """lb_number NOT NULL must raise on NULL insert."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO forum_posts(lb_number, subject, topic_url,"
                    " board_id, posted_at) VALUES(NULL, 'X', 'http://x', 1,"
                    " datetime('now'))"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Rename history writes
# ---------------------------------------------------------------------------

class TestRenameHistory:
    def test_add_rename_history(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_rename_history(900, "/old/path", "/new/path", "test", db_path=db_path)
            row = conn.execute(
                "SELECT * FROM rename_history WHERE lb_number=900"
            ).fetchone()
            assert row is not None
            assert row["old_path"] == "/old/path"
            assert row["new_path"] == "/new/path"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_add_rename_history_null_lb(self):
        """lb_number can be NULL (rename with unknown LB)."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.add_rename_history(None, "/a", "/b", "auto", db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM rename_history WHERE lb_number IS NULL"
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_multiple_renames_accumulate(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            for i in range(5):
                db.add_rename_history(910, f"/old/{i}", f"/new/{i}", "test",
                                      db_path=db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM rename_history WHERE lb_number=910"
            ).fetchone()[0]
            assert count == 5
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Purge functions
# ---------------------------------------------------------------------------

class TestPurgeFunctions:
    def _seed_all_user_data(self, conn, db_path):
        """Seed data into all purgeable user tables."""
        import backend.db as db
        _seed_entry(conn, 1000)
        _seed_collection(conn, 1000)
        db.set_collection_meta(1000, {"personal_rating": 3}, db_path=db_path)
        conn.execute(
            "INSERT INTO integrity_events(lb_number, event_type, detail)"
            " VALUES(1000, 'test', 'x')"
        )
        conn.execute(
            "INSERT INTO entry_changes(lb_number, field, old_value, new_value)"
            " VALUES(1000, 'location', 'A', 'B')"
        )
        _seed_entry(conn, 1001)
        conn.execute(
            "INSERT INTO my_wishlist(lb_number, priority) VALUES(1001, 3)"
        )
        conn.commit()

    def test_purge_collection(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            self._seed_all_user_data(conn, db_path)
            db.purge_collection(db_path=db_path)
            for tbl in ("my_collection", "collection_meta", "integrity_events"):
                count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                assert count == 0, f"{tbl} should be empty after purge_collection"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_purge_wishlist(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            self._seed_all_user_data(conn, db_path)
            db.purge_wishlist(db_path=db_path)
            count = conn.execute("SELECT COUNT(*) FROM my_wishlist").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_purge_collection_meta(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            self._seed_all_user_data(conn, db_path)
            db.purge_collection_meta(db_path=db_path)
            count = conn.execute("SELECT COUNT(*) FROM collection_meta").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_purge_integrity_events(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            self._seed_all_user_data(conn, db_path)
            db.purge_integrity_events(db_path=db_path)
            count = conn.execute("SELECT COUNT(*) FROM integrity_events").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_purge_entry_changes(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            self._seed_all_user_data(conn, db_path)
            db.purge_entry_changes(db_path=db_path)
            count = conn.execute("SELECT COUNT(*) FROM entry_changes").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_purge_on_empty_tables_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.purge_collection(db_path=db_path)
            db.purge_wishlist(db_path=db_path)
            db.purge_collection_meta(db_path=db_path)
            db.purge_integrity_events(db_path=db_path)
            db.purge_entry_changes(db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scrape sessions
# ---------------------------------------------------------------------------

class TestScrapeSessions:
    def test_create_and_finish_session(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            session_id = db.create_scrape_session("incremental", "http://x", db_path=db_path)
            assert isinstance(session_id, int) and session_id > 0
            db.finish_scrape_session(
                session_id,
                status="done",
                pages_fetched=10,
                pages_304=2,
                pages_skipped=1,
                pages_failed=0,
                files_fetched=5,
                notes="all good",
                db_path=db_path,
            )
            sessions = db.get_scrape_sessions(limit=5, db_path=db_path)
            assert any(s["id"] == session_id and s["status"] == "done" for s in sessions)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_finish_nonexistent_session_is_no_op(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.finish_scrape_session(99999, status="done", db_path=db_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_multiple_sessions(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            ids = [db.create_scrape_session("full", db_path=db_path) for _ in range(3)]
            assert len(set(ids)) == 3
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_scrape_session_scope_not_null(self):
        """scope NOT NULL must raise on NULL scope."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO scrape_sessions(scope, status) VALUES(NULL, 'running')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# upsert_inventory
# ---------------------------------------------------------------------------

class TestUpsertInventory:
    def test_insert_new_url(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            db.upsert_inventory("http://example.com/page", db_path=db_path,
                                status="downloaded", http_status=200)
            stats = db.get_inventory_stats(db_path=db_path)
            assert stats.get("downloaded", 0) == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_update_existing_url(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            url = "http://example.com/page2"
            db.upsert_inventory(url, db_path=db_path, status="pending")
            db.upsert_inventory(url, db_path=db_path, status="downloaded", http_status=200)
            row = conn.execute(
                "SELECT status, http_status FROM site_inventory WHERE url=?", (url,)
            ).fetchone()
            assert row["status"] == "downloaded"
            assert row["http_status"] == 200
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upsert_no_fields_creates_stub(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            url = "http://example.com/page3"
            db.upsert_inventory(url, db_path=db_path)
            row = conn.execute(
                "SELECT status FROM site_inventory WHERE url=?", (url,)
            ).fetchone()
            assert row is not None
            assert row["status"] == "pending"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upsert_primary_key_uniqueness(self):
        """site_inventory.url is PK — inserting same URL twice must not duplicate."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            url = "http://example.com/dup"
            db.upsert_inventory(url, db_path=db_path)
            db.upsert_inventory(url, db_path=db_path, http_status=301)
            count = conn.execute(
                "SELECT COUNT(*) FROM site_inventory WHERE url=?", (url,)
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# write_connection rollback on error
# ---------------------------------------------------------------------------

class TestWriteConnectionRollback:
    def test_failed_write_is_rolled_back(self):
        """If an exception is raised inside a queue callback, no data must persist."""
        import backend.db as db
        from backend.db_queue import get_write_queue
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 2000)
            try:
                def _insert_and_fail(wconn):
                    wconn.execute(
                        "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                        " VALUES(2000, 'f', '/p')"
                    )
                    raise RuntimeError("deliberate test error")
                get_write_queue().execute(_insert_and_fail)
            except RuntimeError:
                pass
            count = conn.execute(
                "SELECT COUNT(*) FROM my_collection WHERE lb_number=2000"
            ).fetchone()[0]
            assert count == 0, "Rolled-back INSERT must not persist"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_successful_write_is_committed(self):
        import backend.db as db
        from backend.db_queue import get_write_queue
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 2001)
            get_write_queue().execute(
                lambda wconn: wconn.execute(
                    "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                    " VALUES(2001, 'f', '/p')"
                )
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM my_collection WHERE lb_number=2001"
            ).fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Deliberate SQL constraint errors (comprehensive)
# ---------------------------------------------------------------------------

class TestSQLConstraints:
    def test_checksums_unique_checksum_lb(self):
        """UNIQUE(checksum, lb_number) — duplicate must raise."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO checksums(checksum, filename, chk_type, lb_number)"
                " VALUES('abc123', 'a.flac', 'f', 1)"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO checksums(checksum, filename, chk_type, lb_number)"
                    " VALUES('abc123', 'b.flac', 'f', 1)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_checksums_not_null_checksum(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO checksums(checksum, filename, chk_type, lb_number)"
                    " VALUES(NULL, 'a.flac', 'f', 1)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_checksums_not_null_filename(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO checksums(checksum, filename, chk_type, lb_number)"
                    " VALUES('abc123', NULL, 'f', 1)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_my_collection_lb_number_unique(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            _seed_entry(conn, 3000)
            conn.execute(
                "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                " VALUES(3000, 'f1', '/p1')"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                    " VALUES(3000, 'f2', '/p2')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_lb_master_status_check_constraint(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO lb_master(lb_number, lb_status) VALUES(9999, 'bogus')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_lb_alias_self_reference_check_constraint(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO lb_alias(alias_lb, canonical_lb, relationship)"
                    " VALUES(100, 100, 'duplicate')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_my_wishlist_lb_number_not_null(self):
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO my_wishlist(lb_number, priority) VALUES(NULL, 3)"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_entry_files_primary_key(self):
        """entry_files PK is (lb_number, filename) — duplicate must raise."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO entry_files(lb_number, filename, clean_name, file_url)"
                " VALUES(1, 'LBF-00001-a.txt', 'a.txt', 'http://x')"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO entry_files(lb_number, filename, clean_name, file_url)"
                    " VALUES(1, 'LBF-00001-a.txt', 'a.txt', 'http://y')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flat_file_changelog_release_fk(self):
        """flat_file_changelog.release_id must reference flat_file_releases.id."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO flat_file_changelog"
                    "(release_id, lb_number, op, checksum, filename, chk_type)"
                    " VALUES(99999, 1, 'add', 'abc', 'f.flac', 'f')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_location_geocoded_primary_key(self):
        """location_geocoded.location_text is PK — duplicate insert must raise."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            conn.execute(
                "INSERT INTO location_geocoded(location_text, source)"
                " VALUES('New York, NY', 'nominatim')"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO location_geocoded(location_text, source)"
                    " VALUES('New York, NY', 'manual')"
                )
                conn.commit()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Thread safety: concurrent writes must not corrupt data
# ---------------------------------------------------------------------------

class TestConcurrentWrites:
    def test_write_lock_serializes_concurrent_collection_inserts(self):
        """Multiple threads inserting into my_collection must not race."""
        import backend.db as db
        db_path, conn, tmp = _make_db()
        try:
            for lb in range(4000, 4020):
                _seed_entry(conn, lb)

            errors: list[Exception] = []

            def insert(lb: int) -> None:
                try:
                    db.add_to_collection(lb, f"f{lb}", f"/p/{lb}", db_path=db_path)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=insert, args=(lb,))
                       for lb in range(4000, 4020)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert errors == [], f"Errors during concurrent inserts: {errors}"
            count = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
            assert count == 20
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
