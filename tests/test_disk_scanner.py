"""Tests for backend/disk_scanner.py — the Disk Scanner walk (TODO-250).

Never touches the real collection DB: every test builds a temp tree on disk and
a temp SQLite file, and passes ``db_path`` through explicitly.
"""

import os
import shutil
import tempfile
import threading

import pytest

from backend import disk_scanner


def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with the full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbscan_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    return db_path, db.get_connection(db_path), tmp_dir


def _touch(path: str, size: int = 16) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)


@pytest.fixture
def tree():
    """A music tree with audio folders, a non-audio folder, and prunable dirs."""
    root = tempfile.mkdtemp(prefix="lbscan_tree_")
    _touch(os.path.join(root, "1978", "1978-06-20 London (LB-06548)", "01 track.flac"))
    _touch(os.path.join(root, "1978", "1978-06-20 London (LB-06548)", "02 track.flac"))
    _touch(os.path.join(root, "1978", "1978-06-20 London (LB-06548)", "notes.txt"))
    _touch(os.path.join(root, "1966", "1966-05-17 Manchester", "d1t01.wav"))
    _touch(os.path.join(root, "artwork", "cover.jpg"))
    _touch(os.path.join(root, "node_modules", "pkg", "sample.flac"))
    _touch(os.path.join(root, ".hidden", "secret.flac"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def db():
    db_path, conn, tmp_dir = _make_db()
    yield db_path, conn
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestScanRoots:
    def test_finds_only_folders_holding_audio(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        names = {r["name"] for r in results}
        assert names == {"1978-06-20 London (LB-06548)", "1966-05-17 Manchester"}

    def test_prunes_excluded_and_hidden_dirs(self, tree, db):
        db_path, _ = db
        paths = {r["path"] for r in disk_scanner.scan_roots([tree], db_path=db_path)}
        assert not any("node_modules" in p for p in paths)
        assert not any(".hidden" in p for p in paths)

    def test_counts_only_matching_extensions(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        london = next(r for r in results if "London" in r["name"])
        assert london["file_count"] == 2          # notes.txt excluded
        assert london["extensions"] == [".flac"]
        assert london["size_bytes"] == 32

    def test_custom_extensions_narrow_the_walk(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], extensions=[".wav"], db_path=db_path)
        assert {r["name"] for r in results} == {"1966-05-17 Manchester"}

    def test_extensions_accept_bare_suffixes(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], extensions=["wav"], db_path=db_path)
        assert {r["name"] for r in results} == {"1966-05-17 Manchester"}

    def test_caller_excludes_add_to_defaults(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], excludes=["1978"], db_path=db_path)
        assert {r["name"] for r in results} == {"1966-05-17 Manchester"}

    def test_missing_root_is_skipped_not_fatal(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots(
            ["/nonexistent/path/xyz", tree], db_path=db_path,
        )
        assert len(results) == 2

    def test_results_sorted_by_path(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        assert [r["path"] for r in results] == sorted(r["path"] for r in results)

    def test_cancel_event_returns_partial(self, tree, db):
        db_path, _ = db
        cancel = threading.Event()
        cancel.set()
        assert disk_scanner.scan_roots([tree], cancel_event=cancel, db_path=db_path) == []

    def test_same_root_twice_reports_each_folder_once(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree, tree], db_path=db_path)
        assert len(results) == 2


class TestLbResolution:
    def test_lb_number_from_folder_name(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        london = next(r for r in results if "London" in r["name"])
        assert london["lb_number"] == 6548
        assert london["in_collection"] is False

    def test_unattributable_folder_has_no_lb(self, tree, db):
        db_path, _ = db
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        manchester = next(r for r in results if "Manchester" in r["name"])
        assert manchester["lb_number"] is None

    def test_existing_collection_row_wins_over_name(self, tree, db):
        db_path, conn = db
        folder = os.path.join(tree, "1978", "1978-06-20 London (LB-06548)")
        conn.execute("INSERT INTO entries(lb_number, status) VALUES(?,?)", (99, "ok"))
        conn.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path) VALUES(?,?,?)",
            (99, "London", folder.replace(os.sep, "/")),
        )
        conn.commit()
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        london = next(r for r in results if "London" in r["name"])
        assert london["lb_number"] == 99
        assert london["in_collection"] is True

    def test_folder_link_pin_resolves_unnamed_folder(self, tree, db):
        db_path, conn = db
        folder = os.path.join(tree, "1966", "1966-05-17 Manchester")
        conn.execute(
            "INSERT INTO folder_lb_link(folder_path, lb_number) VALUES(?,?)",
            (folder, 1234),
        )
        conn.commit()
        results = disk_scanner.scan_roots([tree], db_path=db_path)
        manchester = next(r for r in results if "Manchester" in r["name"])
        assert manchester["lb_number"] == 1234


class TestAddPathsToCollection:
    """The insert itself is stubbed: db.add_to_collection goes through the
    module-level write queue, which binds to the FIRST database it sees in a
    process — under a full-suite run that may not be this test's temp DB."""

    def test_unattributable_path_is_reported_not_added(self, tree, db, monkeypatch):
        db_path, _ = db
        called = []
        monkeypatch.setattr(
            disk_scanner.database, "add_to_collection",
            lambda *a, **k: called.append(a) or 1,
        )
        folder = os.path.join(tree, "1966", "1966-05-17 Manchester")
        out = disk_scanner.add_paths_to_collection([folder], db_path=db_path)
        assert out == [{"path": folder, "ok": False, "lb_number": None, "error": "no_lb"}]
        assert called == []

    def test_named_folder_is_added_with_its_lb(self, tree, db, monkeypatch):
        db_path, _ = db
        monkeypatch.setattr(disk_scanner.database, "add_to_collection", lambda *a, **k: 1)
        folder = os.path.join(tree, "1978", "1978-06-20 London (LB-06548)")
        out = disk_scanner.add_paths_to_collection([folder], db_path=db_path)
        assert out[0]["ok"] is True
        assert out[0]["lb_number"] == 6548
        assert out[0]["error"] is None

    def test_duplicate_insert_reports_already_in_collection(self, tree, db, monkeypatch):
        db_path, _ = db
        monkeypatch.setattr(disk_scanner.database, "add_to_collection", lambda *a, **k: 0)
        folder = os.path.join(tree, "1978", "1978-06-20 London (LB-06548)")
        out = disk_scanner.add_paths_to_collection([folder], db_path=db_path)
        assert out[0]["ok"] is False
        assert out[0]["error"] == "already_in_collection"

    def test_insert_failure_is_caught_per_path(self, tree, db, monkeypatch):
        db_path, _ = db

        def _boom(*a, **k):
            raise RuntimeError("FOREIGN KEY constraint failed")

        monkeypatch.setattr(disk_scanner.database, "add_to_collection", _boom)
        folder = os.path.join(tree, "1978", "1978-06-20 London (LB-06548)")
        out = disk_scanner.add_paths_to_collection([folder], db_path=db_path)
        assert out[0]["ok"] is False
        assert "FOREIGN KEY" in out[0]["error"]


class TestJobLifecycle:
    def test_status_reports_results_after_scan(self, tree, db):
        db_path, _ = db
        assert disk_scanner.start_scan_async([tree], db_path=db_path) is True
        for _ in range(200):
            if not disk_scanner.get_scan_status()["running"]:
                break
            threading.Event().wait(0.05)
        status = disk_scanner.get_scan_status()
        assert status["running"] is False
        assert status["error"] is None
        assert len(status["results"]) == 2
        assert status["dirs_scanned"] > 0

    def test_cancel_returns_false_when_idle(self):
        assert disk_scanner.cancel_scan() is False
