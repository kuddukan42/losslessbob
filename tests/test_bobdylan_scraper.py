"""
Tests for the bobdylan.com setlist scraper (backend/bobdylan_scraper.py).

Covers:
  - fetch_sitemap_urls()  — sitemap XML parsing (mocked _fetch)
  - parse_show_page()     — show-page HTML parsing (pure function)
  - run_discover()        — sitemap discovery -> bobdylan_shows upsert
  - run_scrape()          — show-page scraping -> bobdylan_shows/bobdylan_setlist
  - run_update()          — discover + scrape combined
  - get_status() / stop() / is_running()
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_bobdylan_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.bobdylan.com/date/1978-06-07-los-angeles-ca/</loc></url>
  <url><loc>https://www.bobdylan.com/about/</loc></url>
</urlset>"""

SHOW_PAGE_HTML = """
<html><body>
<div class="setlist-detail">
  <div class="headline">Los Angeles, CA</div>
  <div class="venue">The Forum</div>
  <div class="notes">Some notes about the show</div>
  <ul class="set-list">
    <li><a class="title" href="/song/like-a-rolling-stone/">Like a Rolling Stone</a></li>
    <li><a class="title" href="/song/blowin-in-the-wind/">Blowin' in the Wind</a></li>
  </ul>
</div>
</body></html>
"""

NO_SETLIST_HTML = "<html><body><div class='not-a-setlist'>nothing here</div></body></html>"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. fetch_sitemap_urls()
# ═══════════════════════════════════════════════════════════════════════════════

class TestFetchSitemapUrls:
    def test_extracts_date_urls_from_each_sitemap(self):
        from backend import bobdylan_scraper
        fake_resp = MagicMock()
        fake_resp.content = SITEMAP_XML.encode("utf-8")
        with patch.object(bobdylan_scraper, "_fetch", return_value=fake_resp), \
             patch.object(bobdylan_scraper.time, "sleep"):
            results = bobdylan_scraper.fetch_sitemap_urls()

        # Same fixture returned for all 3 sitemaps -> 1 dated URL each.
        assert len(results) == 3
        assert results[0] == (
            "1978-06-07", "https://www.bobdylan.com/date/1978-06-07-los-angeles-ca/"
        )

    def test_failed_sitemap_fetch_is_skipped(self):
        from backend import bobdylan_scraper
        with patch.object(bobdylan_scraper, "_fetch", return_value=None), \
             patch.object(bobdylan_scraper.time, "sleep"):
            results = bobdylan_scraper.fetch_sitemap_urls()

        assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. parse_show_page()
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseShowPage:
    def test_parses_full_setlist_detail(self):
        from backend.bobdylan_scraper import parse_show_page
        data = parse_show_page(SHOW_PAGE_HTML)

        assert data["location"] == "Los Angeles, CA"
        assert data["venue"] == "The Forum"
        assert data["notes"] == "Some notes about the show"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0] == {
            "name": "Like a Rolling Stone", "song_url": "/song/like-a-rolling-stone/"
        }

    def test_returns_empty_dict_without_setlist_detail(self):
        from backend.bobdylan_scraper import parse_show_page
        assert parse_show_page(NO_SETLIST_HTML) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. run_discover()
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunDiscover:
    PAIRS = [
        ("1978-06-07", "https://www.bobdylan.com/date/1978-06-07-los-angeles-ca/"),
        ("1978-06-08", "https://www.bobdylan.com/date/1978-06-08-san-diego-ca/"),
    ]

    def test_inserts_new_rows(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import bobdylan_scraper
            with patch.object(bobdylan_scraper, "fetch_sitemap_urls", return_value=self.PAIRS):
                inserted = bobdylan_scraper.run_discover(db_path=db_path)

            assert inserted == 2
            rows = conn.execute(
                "SELECT bobdylan_url, date_str FROM bobdylan_shows ORDER BY date_str"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["date_str"] == "1978-06-07"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_is_idempotent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import bobdylan_scraper
            with patch.object(bobdylan_scraper, "fetch_sitemap_urls", return_value=self.PAIRS):
                bobdylan_scraper.run_discover(db_path=db_path)
                inserted_second = bobdylan_scraper.run_discover(db_path=db_path)

            assert inserted_second == 0
            count = conn.execute("SELECT COUNT(*) FROM bobdylan_shows").fetchone()[0]
            assert count == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. run_scrape()
# ═══════════════════════════════════════════════════════════════════════════════

SHOW_URL = "https://www.bobdylan.com/date/1978-06-07-los-angeles-ca/"


class TestRunScrape:
    def test_populates_show_and_setlist(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO bobdylan_shows(bobdylan_url, date_str) VALUES (?, ?)",
                (SHOW_URL, "1978-06-07"),
            )
            conn.commit()

            from backend import bobdylan_scraper
            fake_resp = MagicMock()
            fake_resp.text = SHOW_PAGE_HTML
            with patch.object(bobdylan_scraper, "_fetch", return_value=fake_resp), \
                 patch.object(bobdylan_scraper.time, "sleep"):
                scraped = bobdylan_scraper.run_scrape(db_path=db_path)

            assert scraped == 1
            row = conn.execute(
                "SELECT * FROM bobdylan_shows WHERE bobdylan_url=?", (SHOW_URL,)
            ).fetchone()
            assert row["venue"] == "The Forum"
            assert row["location"] == "Los Angeles, CA"
            assert row["scraped_at"] is not None

            tracks = conn.execute(
                "SELECT * FROM bobdylan_setlist WHERE bobdylan_url=? ORDER BY position", (SHOW_URL,)
            ).fetchall()
            assert len(tracks) == 2
            assert tracks[0]["track_name"] == "Like a Rolling Stone"
            assert tracks[1]["track_name"] == "Blowin' in the Wind"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_skips_already_scraped_without_force(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO bobdylan_shows(bobdylan_url, date_str, scraped_at) VALUES (?, ?, ?)",
                (SHOW_URL, "1978-06-07", "2024-01-01T00:00:00"),
            )
            conn.commit()

            from backend import bobdylan_scraper
            with patch.object(bobdylan_scraper, "_fetch") as mock_fetch, \
                 patch.object(bobdylan_scraper.time, "sleep"):
                scraped = bobdylan_scraper.run_scrape(db_path=db_path, force=False)

            assert scraped == 0
            mock_fetch.assert_not_called()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_force_rescrapes_existing_show(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO bobdylan_shows(bobdylan_url, date_str, scraped_at) VALUES (?, ?, ?)",
                (SHOW_URL, "1978-06-07", "2024-01-01T00:00:00"),
            )
            conn.commit()

            from backend import bobdylan_scraper
            fake_resp = MagicMock()
            fake_resp.text = SHOW_PAGE_HTML
            with patch.object(bobdylan_scraper, "_fetch", return_value=fake_resp), \
                 patch.object(bobdylan_scraper.time, "sleep"):
                scraped = bobdylan_scraper.run_scrape(db_path=db_path, force=True)

            assert scraped == 1
            row = conn.execute(
                "SELECT venue FROM bobdylan_shows WHERE bobdylan_url=?", (SHOW_URL,)
            ).fetchone()
            assert row["venue"] == "The Forum"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_fetch_failure_counts_as_error(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO bobdylan_shows(bobdylan_url, date_str) VALUES (?, ?)",
                (SHOW_URL, "1978-06-07"),
            )
            conn.commit()

            from backend import bobdylan_scraper
            with patch.object(bobdylan_scraper, "_fetch", return_value=None), \
                 patch.object(bobdylan_scraper.time, "sleep"):
                scraped = bobdylan_scraper.run_scrape(db_path=db_path)

            assert scraped == 0
            assert bobdylan_scraper.get_status()["errors"] == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_missing_setlist_detail_counts_as_error(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO bobdylan_shows(bobdylan_url, date_str) VALUES (?, ?)",
                (SHOW_URL, "1978-06-07"),
            )
            conn.commit()

            from backend import bobdylan_scraper
            fake_resp = MagicMock()
            fake_resp.text = NO_SETLIST_HTML
            with patch.object(bobdylan_scraper, "_fetch", return_value=fake_resp), \
                 patch.object(bobdylan_scraper.time, "sleep"):
                scraped = bobdylan_scraper.run_scrape(db_path=db_path)

            assert scraped == 0
            assert bobdylan_scraper.get_status()["errors"] == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. run_update()
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunUpdate:
    def test_discovers_then_scrapes(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import bobdylan_scraper
            pairs = [("1978-06-07", SHOW_URL)]
            fake_resp = MagicMock()
            fake_resp.text = SHOW_PAGE_HTML
            with patch.object(bobdylan_scraper, "fetch_sitemap_urls", return_value=pairs), \
                 patch.object(bobdylan_scraper, "_fetch", return_value=fake_resp), \
                 patch.object(bobdylan_scraper.time, "sleep"):
                bobdylan_scraper.run_update(db_path=db_path)

            row = conn.execute("SELECT * FROM bobdylan_shows WHERE bobdylan_url=?", (SHOW_URL,)).fetchone()
            assert row is not None
            assert row["venue"] == "The Forum"
            assert row["scraped_at"] is not None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Status helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusHelpers:
    def test_get_status_has_expected_keys(self):
        from backend.bobdylan_scraper import get_status
        status = get_status()
        for key in ("status", "phase", "total", "done", "errors", "skipped",
                     "current_url", "stop_requested", "message"):
            assert key in status

    def test_stop_sets_flag(self):
        from backend import bobdylan_scraper
        try:
            bobdylan_scraper.stop()
            assert bobdylan_scraper.get_status()["stop_requested"] is True
        finally:
            bobdylan_scraper._set(stop_requested=False)

    def test_is_running_reflects_status(self):
        from backend import bobdylan_scraper
        bobdylan_scraper._set(status="idle")
        assert bobdylan_scraper.is_running() is False
        bobdylan_scraper._set(status="running")
        assert bobdylan_scraper.is_running() is True
        bobdylan_scraper._set(status="idle")
