"""
Tests for the entry-metadata scraper (backend/scraper.py).

Covers:
  - _is_soft_404()                — pure function
  - _extract_setlist_from_lbbcd() — local LBBCD HTML parsing (no network)
  - scrape_entry()                — use_local_pages=True mode (no network)
  - scrape_range()                — local-pages batch run + _scrape_state updates
  - download_pages_range()        — mocked _fetch
  - get_scrape_status() / stop_scrape()
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_scraper_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _patch_site_dirs(monkeypatch, tmp_dir: str) -> tuple[Path, Path]:
    """Redirect SITE_DETAIL_DIR / SITE_FILES_DIR (in both paths and scraper modules)
    to subdirectories of tmp_dir, so local-page tests never touch data/site/.
    """
    import backend.paths as _paths
    import backend.scraper as _scraper

    detail_dir = Path(tmp_dir) / "site" / "detail"
    files_dir = Path(tmp_dir) / "site" / "files"
    detail_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_paths, "SITE_DETAIL_DIR", detail_dir)
    monkeypatch.setattr(_paths, "SITE_FILES_DIR", files_dir)
    monkeypatch.setattr(_scraper, "SITE_DETAIL_DIR", detail_dir)
    monkeypatch.setattr(_scraper, "SITE_FILES_DIR", files_dir)
    return detail_dir, files_dir


# ── Fixture HTML ─────────────────────────────────────────────────────────────

DETAIL_PAGE_HTML = """
<html><body>
<table>
<tr><th>Date</th><th>Location</th><th>CDR</th><th>Rating</th><th>Timing</th></tr>
<tr><td>7/28/00</td><td>Denver, CO</td><td>CDR1</td><td>A+</td><td>120:00</td></tr>
</table>
<p>Recorded by John Doe using a Sony ECM-MS907 to a Sony D8 DAT machine, transferred via optical.</p>
<p>1. Song One
2. Song Two
3. Song Three</p>
<a href="/files/LBF-00042-lbdir.txt">lbdir</a>
<a href="/files/LBF-00042-show.ffp">ffp</a>
</body></html>
"""

SOFT_404_HTML = """
<html><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
</body></html>
"""

LBBCD_TABLE_HTML = """
<html><body>
<table>
<tr><th>CD</th><th>TR</th><th>Song</th></tr>
<tr><td>1</td><td>1</td><td>Song A</td></tr>
<tr><td>1</td><td>2</td><td>Song B</td></tr>
<tr><td>2</td><td>1</td><td>Song C</td></tr>
</table>
</body></html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _is_soft_404()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsSoft404:
    def test_detects_soft_404_marker(self):
        from backend.scraper import _is_soft_404
        assert _is_soft_404(SOFT_404_HTML) is True

    def test_normal_page_is_not_soft_404(self):
        from backend.scraper import _is_soft_404
        assert _is_soft_404(DETAIL_PAGE_HTML) is False

    def test_empty_string_is_not_soft_404(self):
        from backend.scraper import _is_soft_404
        assert _is_soft_404("") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _extract_setlist_from_lbbcd()
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractSetlistFromLbbcd:
    def test_returns_empty_when_no_bootleg_titles_row(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.scraper import _extract_setlist_from_lbbcd
            assert _extract_setlist_from_lbbcd(99999, db_path) == ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_returns_empty_when_lbbcd_html_missing(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.paths as _paths
            lbbcd_dir = Path(tmp_dir) / "site" / "lbbcd"
            lbbcd_dir.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(_paths, "SITE_LBBCD_DIR", lbbcd_dir)

            conn.execute(
                "INSERT INTO bootleg_titles(lb_number, lbbcd_id) VALUES (?, ?)",
                (42, 275),
            )
            conn.commit()

            from backend.scraper import _extract_setlist_from_lbbcd
            assert _extract_setlist_from_lbbcd(42, db_path) == ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_parses_multi_cd_track_table(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.paths as _paths
            lbbcd_dir = Path(tmp_dir) / "site" / "lbbcd"
            lbbcd_dir.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(_paths, "SITE_LBBCD_DIR", lbbcd_dir)

            conn.execute(
                "INSERT INTO bootleg_titles(lb_number, lbbcd_id) VALUES (?, ?)",
                (42, 275),
            )
            conn.commit()
            (lbbcd_dir / "LBBCD-275.html").write_text(LBBCD_TABLE_HTML, encoding="utf-8")

            from backend.scraper import _extract_setlist_from_lbbcd
            result = _extract_setlist_from_lbbcd(42, db_path)
            assert result == "CD 1\n1. Song A\n2. Song B\nCD 2\n3. Song C"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_falls_back_to_zero_padded_filename(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.paths as _paths
            lbbcd_dir = Path(tmp_dir) / "site" / "lbbcd"
            lbbcd_dir.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(_paths, "SITE_LBBCD_DIR", lbbcd_dir)

            conn.execute(
                "INSERT INTO bootleg_titles(lb_number, lbbcd_id) VALUES (?, ?)",
                (42, 7),
            )
            conn.commit()
            # Only the zero-padded filename exists on disk.
            (lbbcd_dir / "LBBCD-007.html").write_text(LBBCD_TABLE_HTML, encoding="utf-8")

            from backend.scraper import _extract_setlist_from_lbbcd
            result = _extract_setlist_from_lbbcd(42, db_path)
            assert "1. Song A" in result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. scrape_entry() — use_local_pages=True (no network)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScrapeEntryLocalPages:
    def test_nonexistent_lb_is_skipped(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            _patch_site_dirs(monkeypatch, tmp_dir)
            # LB-00007 is one of the seeded "confirmed never existed" entries
            # (see backend.db._LB_MISSING_SEEDS) — no insert needed.
            from backend.scraper import scrape_entry
            result = scrape_entry(7, use_local_pages=True, db_path=db_path)
            assert result == {"skipped": True, "reason": "nonexistent"}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_parses_full_detail_page(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00100.html").write_text(DETAIL_PAGE_HTML, encoding="utf-8")

            from backend.scraper import scrape_entry
            result = scrape_entry(100, use_local_pages=True, download_files=False, db_path=db_path)

            assert result["ok"] is True
            assert result["local_source"] is True
            assert result["files_downloaded"] == []

            row = conn.execute("SELECT * FROM entries WHERE lb_number=100").fetchone()
            assert row["date_str"] == "7/28/00"
            assert row["location"] == "Denver, CO"
            assert row["cdr"] == "CDR1"
            assert row["rating"] == "A+"
            assert row["timing"] == "120:00"
            assert "Sony D8 DAT" in row["description"]
            assert row["setlist"] == "1. Song One\n2. Song Two\n3. Song Three"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_records_attachment_links(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00100.html").write_text(DETAIL_PAGE_HTML, encoding="utf-8")

            from backend.scraper import scrape_entry
            scrape_entry(100, use_local_pages=True, download_files=False, db_path=db_path)

            files = conn.execute(
                "SELECT filename, clean_name FROM entry_files WHERE lb_number=100 ORDER BY filename"
            ).fetchall()
            names = {(r["filename"], r["clean_name"]) for r in files}
            assert ("LBF-00042-lbdir.txt", "lbdir.txt") in names
            assert ("LBF-00042-show.ffp", "show.ffp") in names
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_soft_404_marks_entry_missing(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00099.html").write_text(SOFT_404_HTML, encoding="utf-8")

            from backend.scraper import scrape_entry
            result = scrape_entry(99, use_local_pages=True, db_path=db_path)

            assert result == {"error": "404", "missing": True}
            row = conn.execute("SELECT status FROM entries WHERE lb_number=99").fetchone()
            assert row["status"] == "missing"
            # Soft-404 local page is removed.
            assert not (detail_dir / "LB-00099.html").exists()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_skips_when_ok_entry_exists_and_download_files_false(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            _patch_site_dirs(monkeypatch, tmp_dir)
            conn.execute(
                """INSERT INTO entries(lb_number, date_str, location, cdr, rating, timing,
                       description, setlist, status)
                   VALUES (8, '1/1/01', 'Somewhere', '', '', '', '', '', 'ok')"""
            )
            conn.commit()

            from backend.scraper import scrape_entry
            result = scrape_entry(8, force=False, download_files=False, use_local_pages=True, db_path=db_path)
            assert result == {"skipped": True}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_force_reparses_existing_entry(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            conn.execute(
                """INSERT INTO entries(lb_number, date_str, location, cdr, rating, timing,
                       description, setlist, status)
                   VALUES (100, '1/1/01', 'Old Location', '', '', '', '', '', 'ok')"""
            )
            conn.commit()
            (detail_dir / "LB-00100.html").write_text(DETAIL_PAGE_HTML, encoding="utf-8")

            from backend.scraper import scrape_entry
            result = scrape_entry(100, force=True, download_files=False, use_local_pages=True, db_path=db_path)
            assert result["ok"] is True

            row = conn.execute("SELECT location FROM entries WHERE lb_number=100").fetchone()
            assert row["location"] == "Denver, CO"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_already_on_disk_file_gets_downloaded_flag(self, monkeypatch):
        """A file already on disk (e.g. fetched first by site_crawler) must still get
        entry_files.downloaded=1 set — regression test for TODO-174 (the flag update
        set previously only included freshly-network-fetched files, so pre-existing
        files stayed downloaded=0 forever).
        """
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00100.html").write_text(DETAIL_PAGE_HTML, encoding="utf-8")
            # Both attachments referenced by DETAIL_PAGE_HTML already exist on disk,
            # so the loop's "already downloaded" branch triggers for each without any
            # network fetch.
            (files_dir / "LBF-00042-lbdir.txt").write_text("dummy", encoding="utf-8")
            (files_dir / "LBF-00042-show.ffp").write_text("dummy", encoding="utf-8")

            from backend.scraper import scrape_entry
            result = scrape_entry(100, force=False, download_files=True,
                                   use_local_pages=True, db_path=db_path)
            assert result["ok"] is True
            # Not newly fetched over the network this call, so not reported as such.
            assert result["files_downloaded"] == []

            rows = conn.execute(
                "SELECT filename, downloaded FROM entry_files WHERE lb_number=100 "
                "ORDER BY filename"
            ).fetchall()
            assert len(rows) == 2
            assert all(r["downloaded"] == 1 for r in rows)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. scrape_range() — local-pages batch run
# ═══════════════════════════════════════════════════════════════════════════════

class TestScrapeRangeLocalPages:
    def test_scrape_range_updates_state_and_db(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00001.html").write_text(DETAIL_PAGE_HTML, encoding="utf-8")
            (detail_dir / "LB-00002.html").write_text(SOFT_404_HTML, encoding="utf-8")

            from backend.scraper import get_scrape_status, scrape_range
            scrape_range([1, 2], download_files=False, use_local_pages=True, db_path=db_path)

            status = get_scrape_status()
            assert status["running"] is False
            assert status["done"] == 2
            assert status["errors"] == 1  # LB 2 was a soft-404

            row1 = conn.execute("SELECT status FROM entries WHERE lb_number=1").fetchone()
            row2 = conn.execute("SELECT status FROM entries WHERE lb_number=2").fetchone()
            assert row1["status"] != "missing"
            assert row2["status"] == "missing"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_scrape_range_skips_already_ok_entries(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            _patch_site_dirs(monkeypatch, tmp_dir)
            conn.execute(
                """INSERT INTO entries(lb_number, date_str, location, cdr, rating, timing,
                       description, setlist, status)
                   VALUES (5, '1/1/01', 'Somewhere', '', '', '', '', '', 'ok')"""
            )
            conn.commit()

            from backend.scraper import get_scrape_status, scrape_range
            scrape_range([5], download_files=False, use_local_pages=True, db_path=db_path)

            status = get_scrape_status()
            assert status["skipped"] == 1
            assert status["last_action"] == "skipped"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. get_scrape_status() / stop_scrape()
# ═══════════════════════════════════════════════════════════════════════════════

class TestScrapeStatusHelpers:
    def test_get_scrape_status_returns_expected_keys(self):
        from backend.scraper import get_scrape_status
        status = get_scrape_status()
        for key in ("running", "current_lb", "last_lb", "total", "done",
                     "errors", "skipped", "last_action", "last_source", "stop_requested"):
            assert key in status

    def test_stop_scrape_sets_stop_requested(self):
        from backend import scraper
        with scraper._scrape_lock:
            scraper._scrape_state["stop_requested"] = False
        scraper.stop_scrape()
        assert scraper.get_scrape_status()["stop_requested"] is True
        with scraper._scrape_lock:
            scraper._scrape_state["stop_requested"] = False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. download_pages_range() — mocked _fetch
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class TestDownloadPagesRange:
    def test_downloads_new_page(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)

            from backend import scraper
            with patch.object(scraper, "_fetch", return_value=(_FakeResponse(DETAIL_PAGE_HTML), 200)):
                scraper.download_pages_range([1], force=False, delay_ms=0)

            assert (detail_dir / "LB-00001.html").exists()
            status = scraper.get_scrape_status()
            assert status["running"] is False
            assert status["last_action"] == "downloaded"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_skips_existing_page_without_force(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)
            (detail_dir / "LB-00001.html").write_text("cached", encoding="utf-8")

            from backend import scraper
            with patch.object(scraper, "_fetch") as mock_fetch:
                scraper.download_pages_range([1], force=False, delay_ms=0)
                mock_fetch.assert_not_called()

            status = scraper.get_scrape_status()
            assert status["skipped"] == 1
            # Cached content untouched.
            assert (detail_dir / "LB-00001.html").read_text(encoding="utf-8") == "cached"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_404_response_counted_as_skipped(self, monkeypatch):
        db_path, conn, tmp_dir = _make_db()
        try:
            detail_dir, files_dir = _patch_site_dirs(monkeypatch, tmp_dir)

            from backend import scraper
            with patch.object(scraper, "_fetch", return_value=(None, 404)):
                scraper.download_pages_range([1], force=False, delay_ms=0)

            status = scraper.get_scrape_status()
            assert status["skipped"] == 1
            assert not (detail_dir / "LB-00001.html").exists()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
