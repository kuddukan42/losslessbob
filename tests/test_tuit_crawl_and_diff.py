"""Tests for the resumable TUIT crawl (tools/tuit_sync --crawl) and tools/tuit_lb_diff.

HTTP and DB access are mocked / in-memory; nothing contacts TUIT.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import tuit_scraper  # noqa: E402
from tools import tuit_lb_diff, tuit_sync  # noqa: E402


def _args(tmp_path, **kw):
    base = {"crawl_state": str(tmp_path / "state.json"), "max_pages": 2,
            "max_details": 100, "delay": 0.0, "dry_run": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _patch_crawl(monkeypatch, pages, stored):
    """pages: {page: (rows, total)}; stored: set of rec_ids with details."""
    calls = []

    def fake_browse(session, page=1, delay=0.0, **kw):
        rows, total = pages.get(page, ([], 100))
        calls.append(page)
        return [SimpleNamespace(rec_id=r) for r in rows], total, ""

    monkeypatch.setattr(tuit_scraper, "fetch_browse_page", fake_browse)
    monkeypatch.setattr(tuit_sync, "_needs_detail", lambda rid: rid not in stored)
    synced = []
    monkeypatch.setattr(tuit_sync, "_sync_one",
                        lambda s, rid, row, a: synced.append(rid) or "stored")
    return calls, synced


def test_state_roundtrip_and_corrupt(tmp_path):
    p = tmp_path / "sub" / "s.json"
    assert tuit_sync.load_crawl_state(p) == {"next_page": 1}
    tuit_sync.save_crawl_state(p, {"next_page": 7})
    assert tuit_sync.load_crawl_state(p)["next_page"] == 7
    p.write_text("{not json")
    assert tuit_sync.load_crawl_state(p) == {"next_page": 1}


def test_crawl_advances_cursor_and_skips_known(tmp_path, monkeypatch):
    calls, synced = _patch_crawl(monkeypatch, {1: ([10, 11], 50), 2: ([12], 50)}, {11})
    assert tuit_sync._crawl(None, _args(tmp_path)) == 0
    assert calls == [1, 2] and synced == [10, 12]
    assert tuit_sync.load_crawl_state(tmp_path / "state.json")["next_page"] == 3


def test_crawl_resumes_and_wraps_at_end(tmp_path, monkeypatch):
    tuit_sync.save_crawl_state(tmp_path / "state.json", {"next_page": 2})
    calls, _ = _patch_crawl(monkeypatch, {2: ([12], 50)}, set())
    tuit_sync._crawl(None, _args(tmp_path))
    assert calls == [2, 3]  # page 3 empty -> wrap
    st = tuit_sync.load_crawl_state(tmp_path / "state.json")
    assert st["next_page"] == 1 and "last_complete_at" in st


def test_crawl_holds_cursor_on_fetch_failure(tmp_path, monkeypatch):
    tuit_sync.save_crawl_state(tmp_path / "state.json", {"next_page": 4})
    monkeypatch.setattr(tuit_scraper, "fetch_browse_page", lambda *a, **k: ([], None, ""))
    assert tuit_sync._crawl(None, _args(tmp_path)) == 1
    assert tuit_sync.load_crawl_state(tmp_path / "state.json")["next_page"] == 4


def test_crawl_max_details_keeps_page(tmp_path, monkeypatch):
    _, synced = _patch_crawl(monkeypatch, {1: ([1, 2, 3], 9)}, set())
    tuit_sync._crawl(None, _args(tmp_path, max_details=2))
    assert synced == [1, 2]
    assert tuit_sync.load_crawl_state(tmp_path / "state.json")["next_page"] == 1


def test_crawl_dry_run_writes_nothing(tmp_path, monkeypatch):
    _, synced = _patch_crawl(monkeypatch, {1: ([1], 9)}, set())
    tuit_sync._crawl(None, _args(tmp_path, dry_run=True))
    assert synced == [] and not (tmp_path / "state.json").exists()


# ── diff ────────────────────────────────────────────────────────────────────

def _files(*names):
    return json.dumps([{"name": n, "size_bytes": 1} for n in names])


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE lb_master(lb_number INT, lb_status TEXT);
    CREATE TABLE my_collection(lb_number INT);
    CREATE TABLE checksums(lb_number INT, filename TEXT, checksum TEXT, chk_type TEXT);
    CREATE TABLE tuit_recordings(rec_id INT, lb_number INT, info_hash TEXT, date_str TEXT,
        venue TEXT, source_type TEXT, format TEXT, files_json TEXT);
    """)
    c.executemany("INSERT INTO lb_master VALUES (?,?)",
                  [(1, "public"), (2, "public"), (3, "public"), (4, "public"), (5, "public")])
    c.executemany("INSERT INTO my_collection VALUES (?)", [(1,), (3,), (4,), (5,)])
    sums = [(1, "a-01.flac"), (1, "a-02.flac"),
            (3, "x-01.shn"),
            (4, "t01.flac"), (4, "t02.flac"), (4, "t03.flac"),
            (5, "Song  One.flac")]
    c.executemany("INSERT INTO checksums VALUES (?,?, 'h','m')", sums)
    rec = [
        (10, 1, "h", "d", "v", "s", "f", _files("A-01.FLAC", "a-02.flac", "a.md5")),  # match
        (11, 2, "h", "d", "v", "s", "f", _files("b.flac")),                           # missing
        (12, None, "h", "d", "v", "s", "f", _files("c.flac")),                        # unlinked
        (13, 3, "h", "d", "v", "s", "f", _files("x-01.flac", "x-02.flac")),           # db_lacks
        (14, 4, "h", "d", "v", "s", "f", _files("t01.flac")),                         # db_extra
        (15, 5, "h", "d", "v", "s", "f", _files("song one.flac")),                    # match
    ]
    c.executemany("INSERT INTO tuit_recordings VALUES (?,?,?,?,?,?,?,?)", rec)
    return c


def test_track_stem_normalises():
    assert tuit_lb_diff.track_stem("Dir/A  B.FLAC") == "a b"
    assert tuit_lb_diff.track_stem("x.md5") == "x.md5"  # non-audio ext kept


def test_compute_diff_categories():
    d = tuit_lb_diff.compute_diff(_db())
    assert [m["lb_number"] for m in d["missing"]] == [2]
    assert [m["rec_id"] for m in d["unlinked"]] == [12]
    by = {m["rec_id"]: m["kind"] for m in d["filename"]}
    assert by == {13: "db_lacks_tracks", 14: "db_extra"}
    assert d["stats"]["tuit_recordings"] == 6


def test_render_markdown_and_cli(tmp_path):
    md = tuit_lb_diff.render_markdown(tuit_lb_diff.compute_diff(_db()), "T")
    assert "## (i)" in md and "### db_lacks_tracks (1)" in md
    path = tmp_path / "d.db"
    disk = sqlite3.connect(path)
    _db().backup(disk)
    disk.close()
    out = tmp_path / "o.md"
    assert tuit_lb_diff.main(["--db", str(path), "--out", str(out)]) == 0
    assert out.read_text().startswith("# TUIT vs collection diff")
