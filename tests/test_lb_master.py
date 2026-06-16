"""
Tests for the lb_master integrity system (ITEM-1 through ITEM-7).

All backend tests use an in-memory (or temp-file) SQLite database so they
never touch the real data/losslessbob.db.

GUI tests are skipped when no DISPLAY is available (headless CI).
"""

import os
import sqlite3
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> tuple[str, object]:
    """Create a fresh temp database with the full schema and return (path, conn).

    Redirects DATA_DIR to a throwaway temp folder so backup_database never
    touches the real data/ directory during tests.
    """
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")

    # Redirect DATA_DIR so backup_database writes backups to tmp_dir
    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return db_path, conn


def _seed_entries(conn, records: list[tuple]) -> None:
    """Insert rows into entries: (lb_number, status)."""
    conn.executemany(
        "INSERT OR IGNORE INTO entries(lb_number, status) VALUES(?,?)",
        records,
    )
    conn.commit()


def _seed_checksums(conn, lb_numbers: list[int]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO checksums(checksum, filename, chk_type, lb_number) "
        "VALUES(?,?,?,?)",
        [(f"abc{n:032d}", f"file{n}.flac", "f", n) for n in lb_numbers],
    )
    conn.commit()


def _seed_entry_files(conn, lb_numbers: list[int]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO entry_files(lb_number, filename, clean_name, file_url) "
        "VALUES(?,?,?,?)",
        [(n, f"LBF-{n:05d}-a.txt", "a.txt", f"http://x/{n}") for n in lb_numbers],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# ITEM-1: lb_master schema and DB functions
# ---------------------------------------------------------------------------

class TestLbMasterSchema:
    def test_tables_created(self):
        db_path, conn = _make_db()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "lb_master" in tables
        assert "lb_status_history" in tables

    def test_lb_master_columns(self):
        db_path, conn = _make_db()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(lb_master)").fetchall()}
        for expected in (
            "lb_number", "lb_status", "has_webpage", "has_checksums",
            "has_attachments", "manual_override", "needs_review",
        ):
            assert expected in cols, f"Missing column: {expected}"

    def test_lb_master_status_constraint(self):
        db_path, conn = _make_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO lb_master(lb_number, lb_status) VALUES(1, 'invalid')"
            )


class TestMigrateLbMaster:
    def test_migrate_populates_rows(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1, 2, 3])
        _seed_entries(conn, [(1, "ok"), (2, "ok")])
        # migrate_lb_master is called by init_db in a background thread;
        # call it directly with our conn/db_path
        result = db.migrate_lb_master(db_path)
        assert result == 3  # rows 1, 2, 3

    def test_migrate_status_precedence(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1, 2, 3])
        _seed_entries(conn, [(1, "ok")])  # LB-1 public
        # LB-2 has checksums but no entry → private
        # LB-3 has no data → missing (has checksum so it's private actually)
        # Actually LB-3 has checksum so it's private too; let me use 4 for missing
        _seed_checksums(conn, [4])
        # Remove LB-4 checksum so it's missing
        conn.execute("DELETE FROM checksums WHERE lb_number=4")
        conn.commit()
        db.migrate_lb_master(db_path)
        row1 = conn.execute(
            "SELECT lb_status FROM lb_master WHERE lb_number=1"
        ).fetchone()[0]
        row2 = conn.execute(
            "SELECT lb_status FROM lb_master WHERE lb_number=2"
        ).fetchone()[0]
        assert row1 == "public"
        assert row2 == "private"

    def test_migrate_idempotent(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1, 2])
        _seed_entries(conn, [(1, "ok")])
        db.migrate_lb_master(db_path)
        # Second call should return 0 (already populated)
        result2 = db.migrate_lb_master(db_path)
        assert result2 == 0

    def test_migrate_deletes_tombstones(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1])
        _seed_entries(conn, [(1, "ok"), (99, "missing")])
        db.migrate_lb_master(db_path)
        missing_rows = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE status='missing'"
        ).fetchone()[0]
        assert missing_rows == 0


class TestReconcileLbStatus:
    def test_reconcile_new_public(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1])
        _seed_entries(conn, [(1, "ok")])
        status = db.reconcile_lb_status(1, db_path=db_path)
        assert status == "public"
        row = conn.execute(
            "SELECT lb_status, has_webpage FROM lb_master WHERE lb_number=1"
        ).fetchone()
        assert row["lb_status"] == "public"
        assert row["has_webpage"] == 1

    def test_reconcile_private(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [5])
        # No entry row → private
        status = db.reconcile_lb_status(5, db_path=db_path)
        assert status == "private"

    def test_reconcile_missing(self):
        import backend.db as db
        db_path, conn = _make_db()
        status = db.reconcile_lb_status(999, db_path=db_path)
        assert status == "missing"

    def test_reconcile_respects_manual_override(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [10])
        _seed_entries(conn, [(10, "ok")])
        # First reconcile sets public
        db.reconcile_lb_status(10, db_path=db_path)
        # Set manual override to private
        db.set_lb_manual_override(10, "private", "test override", db_path=db_path)
        # Reconcile again — should NOT change lb_status
        db.reconcile_lb_status(10, db_path=db_path)
        row = conn.execute(
            "SELECT lb_status, manual_override FROM lb_master WHERE lb_number=10"
        ).fetchone()
        assert row["lb_status"] == "private"
        assert row["manual_override"] == 1

    def test_reconcile_logs_transition(self):
        import backend.db as db
        db_path, conn = _make_db()
        # Use LB 11 — not in _LB_MISSING_SEEDS (7 is seeded as nonexistent)
        _seed_checksums(conn, [11])
        # Start as private (no entry)
        db.reconcile_lb_status(11, db_path=db_path)
        # Add entry row → now public
        _seed_entries(conn, [(11, "ok")])
        db.reconcile_lb_status(11, db_path=db_path)
        hist = conn.execute(
            "SELECT old_status, new_status FROM lb_status_history "
            "WHERE lb_number=11 ORDER BY changed_at"
        ).fetchall()
        statuses = [(r["old_status"], r["new_status"]) for r in hist]
        assert (None, "private") in statuses or ("private", "public") in statuses


class TestGetLbMasterStats:
    def test_stats_structure(self):
        import backend.db as db
        db_path, conn = _make_db()
        stats = db.get_lb_master_stats(db_path)
        for key in ("public", "private", "missing", "max_lb", "overrides", "needs_review"):
            assert key in stats

    def test_stats_counts(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1, 2, 3])
        _seed_entries(conn, [(1, "ok"), (2, "ok")])
        db.migrate_lb_master(db_path)
        stats = db.get_lb_master_stats(db_path)
        assert stats["public"] == 2
        assert stats["private"] == 1
        assert stats["max_lb"] == 3


# ---------------------------------------------------------------------------
# ITEM-3: reconcile_lb_status wired into importer
# ---------------------------------------------------------------------------

class TestImporterIntegration:
    def test_run_import_updates_lb_master(self, tmp_path):
        """After importing a flat file, lb_master should be populated."""
        import backend.db as db
        import backend.paths as _p

        db_path = str(tmp_path / "test.db")
        # Redirect DATA_DIR so temp_import.db and backups stay in tmp_path
        _p.DATA_DIR = tmp_path
        db.init_db(db_path)

        flat = tmp_path / "data.txt"
        flat.write_text(
            "abc123def456abc123def456abc123de\tfile1.flac\tf\t42\t0\n"
            "abc123def456abc123def456abc123df\tfile2.flac\tf\t42\t0\n",
            encoding="utf-8",
        )

        from backend.importer import run_import
        run_import(str(flat), db_path=db_path)

        conn = db.get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
        assert count >= 1, "lb_master should be populated after import"


# ---------------------------------------------------------------------------
# ITEM-7: is_postable_to_forum
# ---------------------------------------------------------------------------

class TestIsPostableToForum:
    def test_public_is_allowed(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [1])
        _seed_entries(conn, [(1, "ok")])
        db.reconcile_lb_status(1, db_path=db_path)
        allowed, reason = db.is_postable_to_forum(1, db_path)
        assert allowed is True
        assert reason is None

    def test_private_is_blocked(self):
        import backend.db as db
        db_path, conn = _make_db()
        _seed_checksums(conn, [2])
        db.reconcile_lb_status(2, db_path=db_path)
        allowed, reason = db.is_postable_to_forum(2, db_path)
        assert allowed is False
        assert reason == "lb_private"

    def test_missing_is_blocked(self):
        import backend.db as db
        db_path, conn = _make_db()
        db.reconcile_lb_status(999, db_path=db_path)
        allowed, reason = db.is_postable_to_forum(999, db_path)
        assert allowed is False
        assert reason == "lb_missing"

    def test_unknown_is_blocked(self):
        import backend.db as db
        db_path, conn = _make_db()
        allowed, reason = db.is_postable_to_forum(77777, db_path)
        assert allowed is False
        assert reason == "status_unknown"


# ---------------------------------------------------------------------------
# ITEM-7: Flask forum endpoint guard (integration test)
# ---------------------------------------------------------------------------

class TestForumEndpointGuard:
    @pytest.fixture
    def flask_client(self, tmp_path):
        """Spin up a Flask test client with a seeded temp DB."""
        import backend.db as db
        import backend.paths as _p

        db_path = str(tmp_path / "test.db")
        _p.DATA_DIR = tmp_path
        (tmp_path / "attachments").mkdir(exist_ok=True)
        (tmp_path / "backups").mkdir(exist_ok=True)

        db.init_db(db_path)
        conn = db.get_connection(db_path)
        _seed_checksums(conn, [1, 2])
        _seed_entries(conn, [(1, "ok")])
        db.reconcile_lb_status(1, db_path=db_path)  # public
        db.reconcile_lb_status(2, db_path=db_path)  # private

        # Patch so the app module's DB_PATH references our temp DB
        _orig_dbpath = db.DB_PATH
        db.DB_PATH = db_path

        from backend.app import create_app
        app = create_app()
        app.config["TESTING"] = True

        yield app.test_client()

        db.DB_PATH = _orig_dbpath

    def test_preview_forum_blocked_for_private(self, flask_client):
        resp = flask_client.get("/api/entry/2/preview_forum")
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "lb_private"

    def test_preview_forum_passes_for_public(self, flask_client):
        # public LB — should pass the guard (may still fail for other reasons
        # such as no forum creds, but must not return 403 from our guard)
        resp = flask_client.get("/api/entry/1/preview_forum")
        assert resp.status_code != 403 or resp.get_json().get("error") not in (
            "lb_private", "lb_missing", "status_unknown"
        )

    def test_post_forum_blocked_for_private(self, flask_client):
        resp = flask_client.post("/api/entry/2/post_forum", json={})
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "lb_private"


# ---------------------------------------------------------------------------
# GUI tests (skipped without a display)
# ---------------------------------------------------------------------------

_HAVE_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.mark.skipif(not _HAVE_DISPLAY, reason="No display available")
class TestSearchTabStatusColumn:
    def test_status_column_in_headers(self, qtbot):
        from gui.search_tab import HEADERS
        assert "Status" in HEADERS

    def test_status_combobox_exists(self, qtbot):
        from gui.search_tab import SearchTab
        tab = SearchTab(flask_port=15174)
        qtbot.addWidget(tab)
        # The status combo should exist and have items
        assert tab._status_combo.count() >= 4

    def test_missing_only_checkbox_removed(self, qtbot):
        from gui.search_tab import SearchTab
        tab = SearchTab(flask_port=15174)
        qtbot.addWidget(tab)
        assert not hasattr(tab, "_missing_only_cb")


@pytest.mark.skipif(not _HAVE_DISPLAY, reason="No display available")
class TestCollectionTabStatusColumn:
    def test_coll_headers_has_status(self):
        from gui.collection_tab import COLL_HEADERS, MISS_HEADERS
        assert "Status" in COLL_HEADERS
        assert "Status" in MISS_HEADERS


@pytest.mark.skipif(not _HAVE_DISPLAY, reason="No display available")
class TestDbEditorIntegrityPanel:
    def test_integrity_label_exists(self, qtbot):
        from gui.dbedit_tab import DbEditTab
        tab = DbEditTab(flask_port=15174)
        qtbot.addWidget(tab)
        assert hasattr(tab, "_integrity_label")
