"""
Tests for the site-mirror crawler subsystem (TODO-031).

Covers:
  - backend/html_utils.py   — rewrite_links()
  - backend/paths.py        — SITE_DIR hierarchy, detail_page_path(), attachment_path()
  - backend/db.py           — scrape_sessions + site_inventory tables and helpers
  - backend/site_crawler.py — pure URL utility functions (no network)
  - backend/app.py          — /api/crawler/* route smoke tests (Flask test client)
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir).

    Redirects DATA_DIR and DB_PATH so no writes touch the real data/ folder.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_crawler_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


# ── Flask test client fixture ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create a Flask test client backed by a disposable temp DB."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_flask_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    orig_data = _paths.DATA_DIR
    orig_db   = _db.DB_PATH
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    with patch("backend.scheduler.start_file_watcher"):
        from backend.app import create_app
        flask_app = create_app()

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c

    _paths.DATA_DIR = orig_data
    _db.DB_PATH = orig_db
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. html_utils.rewrite_links()
# ═══════════════════════════════════════════════════════════════════════════════

class TestRewriteLinks:
    """rewrite_links() converts server-absolute paths to relative paths."""

    BASE_DOMAIN = "www.losslessbob.wonderingwhattochoose.com"

    def _rw(self, html: str, page_url: str) -> str:
        from backend.html_utils import rewrite_links
        return rewrite_links(html, page_url, self.BASE_DOMAIN)

    def _page(self, path: str) -> str:
        return f"http://{self.BASE_DOMAIN}{path}"

    def test_same_directory_link(self):
        html = '<a href="/detail/LB-00002.html">next</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert "LB-00002.html" in result
        assert "/detail/" not in result.split('href="')[1].split('"')[0]

    def test_link_from_detail_to_root(self):
        # href="/" rewritten relative to /detail/ → ".." (browser resolves to parent dir)
        html = '<a href="/">Home</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        href = result.split('href="')[1].split('"')[0]
        assert href == ".."

    def test_link_from_root_to_detail(self):
        html = '<a href="/detail/LB-00001.html">Entry</a>'
        result = self._rw(html, self._page("/index.html"))
        href = result.split('href="')[1].split('"')[0]
        assert "detail/LB-00001.html" in href
        assert not href.startswith("/")

    def test_external_link_unchanged(self):
        html = '<a href="https://external.com/page">ext</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert 'href="https://external.com/page"' in result

    def test_mailto_unchanged(self):
        html = '<a href="mailto:foo@example.com">mail</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert 'href="mailto:foo@example.com"' in result

    def test_javascript_unchanged(self):
        html = '<a href="javascript:void(0)">js</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert 'href="javascript:void(0)"' in result

    def test_fragment_only_unchanged(self):
        html = '<a href="#section">jump</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert 'href="#section"' in result

    def test_src_attribute_rewritten(self):
        html = '<img src="/images/logo.png">'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        src = result.split('src="')[1].split('"')[0]
        assert src.endswith("logo.png")
        assert not src.startswith("/")

    def test_already_relative_path_unchanged(self):
        html = '<a href="other.html">link</a>'
        result = self._rw(html, self._page("/detail/LB-00001.html"))
        assert 'href="other.html"' in result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. paths.py — SITE_DIR hierarchy + helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaths:
    def test_site_dir_name_is_site(self):
        # DATA_DIR may be mutated by other test suites; check structural name instead.
        from backend.paths import SITE_DIR
        assert SITE_DIR.name == "site"

    def test_site_detail_dir_is_under_site_dir(self):
        from backend.paths import SITE_DETAIL_DIR, SITE_DIR
        assert SITE_DETAIL_DIR.parent == SITE_DIR

    def test_site_files_dir_is_under_site_dir(self):
        from backend.paths import SITE_DIR, SITE_FILES_DIR
        assert SITE_FILES_DIR.parent == SITE_DIR

    def test_detail_page_path_format(self):
        from backend.paths import SITE_DETAIL_DIR, detail_page_path
        p = detail_page_path("00001")
        assert p == SITE_DETAIL_DIR / "LB-00001.html"

    def test_attachment_path_format(self):
        from backend.paths import SITE_FILES_DIR, attachment_path
        fname = "LBF-00001-lbdir.txt"
        assert attachment_path(fname) == SITE_FILES_DIR / fname

    def test_ensure_data_dirs_creates_site_hierarchy(self):
        tmp_dir = tempfile.mkdtemp(prefix="lbtest_paths_")
        try:
            import backend.paths as _paths
            orig = _paths.DATA_DIR
            _paths.DATA_DIR    = Path(tmp_dir)
            _paths.SITE_DIR    = Path(tmp_dir) / "site"
            _paths.SITE_DETAIL_DIR = _paths.SITE_DIR / "detail"
            _paths.SITE_FILES_DIR  = _paths.SITE_DIR / "files"
            _paths.SITE_LBBCD_DIR  = _paths.SITE_DIR / "lbbcd"
            _paths.SITE_BN_DIR     = _paths.SITE_DIR / "bynumber"
            _paths.ensure_data_dirs()
            for sub in ("site", "site/detail", "site/files", "site/lbbcd", "site/bynumber"):
                assert (Path(tmp_dir) / sub).is_dir(), f"Missing: {sub}"
            _paths.DATA_DIR = orig
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_find_lbdir_attachment_returns_none_when_dir_missing(self):
        # SITE_FILES_DIR doesn't exist in a clean temp env → should return None, not crash
        import backend.paths as _paths
        from backend.paths import find_lbdir_attachment
        orig = _paths.SITE_FILES_DIR
        _paths.SITE_FILES_DIR = Path("/nonexistent_path_lbtest")
        result = find_lbdir_attachment(1)
        assert result is None
        _paths.SITE_FILES_DIR = orig

    def test_find_lbdir_attachment_finds_file(self):
        tmp_dir = tempfile.mkdtemp(prefix="lbtest_find_")
        try:
            import backend.paths as _paths
            from backend.paths import find_lbdir_attachment
            orig = _paths.SITE_FILES_DIR
            _paths.SITE_FILES_DIR = Path(tmp_dir)
            fname = "LBF-00001-lbdir_main.txt"
            (Path(tmp_dir) / fname).write_text("test")
            result = find_lbdir_attachment(1)
            assert result is not None
            assert result.name == fname
            _paths.SITE_FILES_DIR = orig
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. db.py — scrape_sessions + site_inventory tables and helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestDbCrawlerTables:
    def test_scrape_sessions_in_user_tables(self):
        # Local crawl-session history is per-user operational state, not master catalog data.
        import backend.db as db
        assert "scrape_sessions" in db.USER_TABLES
        assert "scrape_sessions" not in db.MASTER_TABLES

    def test_site_inventory_in_user_tables(self):
        import backend.db as db
        assert "site_inventory" in db.USER_TABLES
        assert "site_inventory" not in db.MASTER_TABLES

    def test_scrape_sessions_table_created_by_init_db(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "scrape_sessions" in tables
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_site_inventory_table_created_by_init_db(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "site_inventory" in tables
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_create_scrape_session_returns_int(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            sid = db.create_scrape_session("full", "http://example.com", db_path)
            assert isinstance(sid, int)
            assert sid > 0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_create_scrape_session_inserts_row(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            sid = db.create_scrape_session("incremental", "http://example.com", db_path)
            row = conn.execute(
                "SELECT * FROM scrape_sessions WHERE id=?", (sid,)
            ).fetchone()
            assert row is not None
            assert row["scope"] == "incremental"
            assert row["status"] == "running"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_finish_scrape_session_updates_status_and_counts(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            sid = db.create_scrape_session("full", "http://example.com", db_path)
            db.finish_scrape_session(
                sid,
                status="done",
                pages_fetched=42,
                pages_304=10,
                pages_skipped=3,
                pages_failed=1,
                db_path=db_path,
            )
            row = conn.execute(
                "SELECT * FROM scrape_sessions WHERE id=?", (sid,)
            ).fetchone()
            assert row["status"] == "done"
            assert row["pages_fetched"] == 42
            assert row["pages_304"] == 10
            assert row["finished_at"] is not None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_scrape_sessions_sorted_newest_first(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            id1 = db.create_scrape_session("full", "http://a.com", db_path)
            id2 = db.create_scrape_session("incremental", "http://b.com", db_path)
            rows = db.get_scrape_sessions(50, db_path)
            assert rows[0]["id"] == id2
            assert rows[1]["id"] == id1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_upsert_inventory_inserts_new_url(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            url = "http://example.com/detail/LB-00001.html"
            db.upsert_inventory(url, db_path, status="pending", discovered_by="start")
            row = conn.execute(
                "SELECT * FROM site_inventory WHERE url=?", (url,)
            ).fetchone()
            assert row is not None
            assert row["status"] == "pending"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_upsert_inventory_updates_existing_url(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            url = "http://example.com/detail/LB-00001.html"
            db.upsert_inventory(url, db_path, status="pending")
            db.upsert_inventory(url, db_path, status="downloaded", http_status=200)
            row = conn.execute(
                "SELECT * FROM site_inventory WHERE url=?", (url,)
            ).fetchone()
            assert row["status"] == "downloaded"
            assert row["http_status"] == 200
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_pending_urls_returns_only_pending(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            db.upsert_inventory("http://ex.com/a.html", db_path, status="pending")
            db.upsert_inventory("http://ex.com/b.html", db_path, status="downloaded")
            db.upsert_inventory("http://ex.com/c.html", db_path, status="pending")
            pending = db.get_pending_urls(db_path)
            urls = {r["url"] for r in pending}
            assert "http://ex.com/a.html" in urls
            assert "http://ex.com/c.html" in urls
            assert "http://ex.com/b.html" not in urls
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_missing_attachment_urls_returns_undownloaded_only(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            conn.execute(
                "INSERT INTO entry_files (lb_number, filename, clean_name, file_url, downloaded) "
                "VALUES (?, ?, ?, ?, ?)",
                (329, "LBF-00329-xref-02017-text.txt", "xref-02017-text.txt",
                 "http://ex.com/files/LBF-00329-xref-02017-text.txt", 0),
            )
            conn.execute(
                "INSERT INTO entry_files (lb_number, filename, clean_name, file_url, downloaded) "
                "VALUES (?, ?, ?, ?, ?)",
                (2, "LBF-00002-text.txt", "text.txt",
                 "http://ex.com/files/LBF-00002-text.txt", 1),
            )
            # Dead row (downloaded=2, BUG-255): permanently-404 URL, never re-seeded
            conn.execute(
                "INSERT INTO entry_files (lb_number, filename, clean_name, file_url, downloaded) "
                "VALUES (?, ?, ?, ?, ?)",
                (3, "LBF-00003-dead.txt", "dead.txt",
                 "http://ex.com/files/LBF-00003-dead.txt", 2),
            )
            conn.commit()
            urls = db.get_missing_attachment_urls(db_path)
            assert urls == ["http://ex.com/files/LBF-00329-xref-02017-text.txt"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_downloaded_urls_returns_set_of_downloaded(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            db.upsert_inventory("http://ex.com/a.html", db_path, status="downloaded")
            db.upsert_inventory("http://ex.com/b.html", db_path, status="pending")
            downloaded = db.get_downloaded_urls(db_path)
            assert isinstance(downloaded, set)
            assert "http://ex.com/a.html" in downloaded
            assert "http://ex.com/b.html" not in downloaded
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_inventory_page_pagination(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            for i in range(5):
                db.upsert_inventory(f"http://ex.com/p{i}.html", db_path, status="downloaded")
            rows, total = db.get_inventory_page(limit=3, offset=0, db_path=db_path)
            assert total == 5
            assert len(rows) == 3
            rows2, _ = db.get_inventory_page(limit=3, offset=3, db_path=db_path)
            assert len(rows2) == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_inventory_page_status_filter(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            db.upsert_inventory("http://ex.com/ok.html", db_path, status="downloaded")
            db.upsert_inventory("http://ex.com/fail.html", db_path, status="failed")
            rows, total = db.get_inventory_page(status="failed", db_path=db_path)
            assert total == 1
            assert rows[0]["url"] == "http://ex.com/fail.html"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_inventory_page_path_prefix_filter(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            db.upsert_inventory(
                "http://ex.com/detail/LB-00001.html", db_path,
                status="downloaded", relative_path="detail/LB-00001.html",
            )
            db.upsert_inventory(
                "http://ex.com/lbbcd/LBBCD-001.html", db_path,
                status="downloaded", relative_path="lbbcd/LBBCD-001.html",
            )
            rows, total = db.get_inventory_page(path_prefix="detail/", db_path=db_path)
            assert total == 1
            assert "LB-00001" in rows[0]["url"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_inventory_stats_groups_by_status(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.db as db
            db.upsert_inventory("http://ex.com/a.html", db_path, status="downloaded")
            db.upsert_inventory("http://ex.com/b.html", db_path, status="downloaded")
            db.upsert_inventory("http://ex.com/c.html", db_path, status="failed")
            stats = db.get_inventory_stats(db_path)
            assert isinstance(stats, dict)
            assert stats.get("downloaded") == 2
            assert stats.get("failed") == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. site_crawler.py — pure URL utility functions (no network)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawlerUrlUtils:
    BASE = "http://www.losslessbob.wonderingwhattochoose.com"
    DOMAIN = "www.losslessbob.wonderingwhattochoose.com"

    def test_normalise_strips_fragment(self):
        from backend.site_crawler import _normalise
        assert "#" not in _normalise(f"{self.BASE}/detail/LB-00001.html#section")

    def test_normalise_strips_query_string(self):
        from backend.site_crawler import _normalise
        assert "?" not in _normalise(f"{self.BASE}/search?q=foo")

    def test_normalise_empty_path_becomes_slash(self):
        from backend.site_crawler import _normalise
        result = _normalise(self.BASE)
        assert result.endswith("/") or result == self.BASE

    def test_is_same_domain_true(self):
        from backend.site_crawler import _is_same_domain
        assert _is_same_domain(f"{self.BASE}/detail/LB-00001.html")

    def test_is_same_domain_false_external(self):
        from backend.site_crawler import _is_same_domain
        assert not _is_same_domain("https://google.com/")

    def test_is_same_domain_true_for_relative_url(self):
        from backend.site_crawler import _is_same_domain
        # Relative URLs have no netloc — treated as same-domain
        assert _is_same_domain("/detail/LB-00001.html")

    def test_url_to_local_detail_page(self):
        # Check path components rather than full prefix (DATA_DIR may be patched by other suites)
        from backend.site_crawler import _url_to_local
        p = _url_to_local(f"{self.BASE}/detail/LB-00001.html")
        assert p.name == "LB-00001.html"
        assert p.parent.name == "detail"
        assert "site" in p.parts

    def test_url_to_local_files(self):
        from backend.site_crawler import _url_to_local
        p = _url_to_local(f"{self.BASE}/files/LBF-00001-lbdir.txt")
        assert p.name == "LBF-00001-lbdir.txt"
        assert p.parent.name == "files"
        assert "site" in p.parts

    def test_url_to_local_root(self):
        from backend.site_crawler import _url_to_local
        p = _url_to_local(self.BASE + "/")
        assert p.name == "index.html"
        assert "site" in p.parts

    def test_ext_returns_lowercase_suffix(self):
        from backend.site_crawler import _ext
        assert _ext(f"{self.BASE}/detail/LB-00001.html") == ".html"
        assert _ext(f"{self.BASE}/files/LBF-00001-x.FFP") == ".ffp"

    def test_should_skip_audio_extensions(self):
        from backend.site_crawler import _should_skip
        for ext in (".flac", ".mp3", ".ape", ".zip"):
            assert _should_skip(f"{self.BASE}/files/test{ext}"), f"should skip {ext}"

    def test_should_skip_allows_html(self):
        from backend.site_crawler import _should_skip
        assert not _should_skip(f"{self.BASE}/detail/LB-00001.html")

    def test_should_skip_non_http_scheme(self):
        from backend.site_crawler import _should_skip
        assert _should_skip("mailto:foo@example.com")
        assert _should_skip("javascript:void(0)")

    def test_extract_links_finds_same_domain_links(self):
        from backend.site_crawler import _extract_links
        html = """
        <html><body>
          <a href="/detail/LB-00001.html">entry 1</a>
          <a href="/detail/LB-00002.html">entry 2</a>
        </body></html>
        """
        links = _extract_links(html, self.BASE + "/")
        urls = [u for u in links if "LB-00001" in u or "LB-00002" in u]
        assert len(urls) == 2

    def test_extract_links_ignores_external(self):
        from backend.site_crawler import _extract_links
        html = '<a href="https://google.com/">ext</a>'
        links = _extract_links(html, self.BASE + "/")
        assert not any("google.com" in u for u in links)

    def test_extract_links_ignores_mailto(self):
        from backend.site_crawler import _extract_links
        html = '<a href="mailto:foo@example.com">mail</a>'
        links = _extract_links(html, self.BASE + "/")
        assert not links

    def test_extract_links_returns_all_occurrences(self):
        # _extract_links reports every found href; deduplication is the crawl loop's job.
        from backend.site_crawler import _extract_links
        html = """
        <a href="/detail/LB-00001.html">a</a>
        <a href="/detail/LB-00001.html">b</a>
        """
        links = _extract_links(html, self.BASE + "/")
        assert f"{self.BASE}/detail/LB-00001.html" in links

    def test_get_crawler_status_returns_dict_with_running_key(self):
        from backend.site_crawler import get_crawler_status
        status = get_crawler_status()
        assert isinstance(status, dict)
        assert "running" in status

    def test_stop_crawler_sets_stop_requested(self):
        from backend import site_crawler
        # Reset state before test
        with site_crawler._crawler_lock:
            site_crawler._crawler_state["stop_requested"] = False
            site_crawler._crawler_state["running"] = False
        site_crawler.stop_crawler()
        assert site_crawler.get_crawler_status()["stop_requested"] is True
        # Clean up
        with site_crawler._crawler_lock:
            site_crawler._crawler_state["stop_requested"] = False


# ═══════════════════════════════════════════════════════════════════════════════
# 4b. crawl() — skips /files/ URLs already on disk (TODO-174 guardrail)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawlSkipsFilesOnDisk:
    def test_files_url_on_disk_skips_fetch_but_updates_state(self, monkeypatch):
        """An attachment already saved by scraper.scrape_entry() (same layout as
        attachment_path()/_url_to_local()) must not be re-fetched by crawl(), but
        the crawler's own bookkeeping (site_inventory + entry_files.downloaded)
        still has to run so both subsystems agree on state.
        """
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.site_crawler as _crawler

            site_dir = Path(tmp_dir) / "site"
            files_dir = site_dir / "files"
            files_dir.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(_crawler, "SITE_DIR", site_dir)

            filename = "LBF-00042-lbdir.txt"
            (files_dir / filename).write_text("dummy contents", encoding="utf-8")

            conn.execute(
                """INSERT INTO entries(lb_number, date_str, location, cdr, rating, timing,
                       description, setlist, status)
                   VALUES (42, '1/1/01', 'Somewhere', '', '', '', '', '', 'ok')"""
            )
            files_url = _crawler.BASE_URL + "/files/" + filename
            conn.execute(
                "INSERT INTO entry_files(lb_number, filename, clean_name, file_url, downloaded) "
                "VALUES (42, ?, 'lbdir.txt', ?, 0)",
                (filename, files_url),
            )
            conn.commit()

            with patch.object(_crawler, "_load_robots"), \
                 patch.object(_crawler, "_fetch_page", return_value=(304, None, None)) as mock_fetch:
                _crawler.crawl(start_url=files_url, db_path=db_path, delay_ms=0)

            # The on-disk /files/ URL must never reach the network fetch call.
            fetched_urls = [call.args[1] for call in mock_fetch.call_args_list]
            assert files_url not in fetched_urls

            row = conn.execute(
                "SELECT downloaded FROM entry_files WHERE lb_number=42 AND filename=?",
                (filename,),
            ).fetchone()
            assert row["downloaded"] == 1

            inv = conn.execute(
                "SELECT status FROM site_inventory WHERE url=?", (files_url,)
            ).fetchone()
            assert inv is not None and inv["status"] == "downloaded"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4c. crawl() — a 404'd /files/ URL marks its entry_files row dead (BUG-255)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawl404MarksAttachmentDead:
    def test_404_files_url_sets_downloaded_2(self, monkeypatch):
        """A /files/ attachment URL that 404s is permanently dead (stale seed or
        source-mangled href): its entry_files row must flip to downloaded=2 so
        get_missing_attachment_urls() stops re-seeding it every session.
        """
        db_path, conn, tmp_dir = _make_db()
        try:
            import backend.site_crawler as _crawler

            site_dir = Path(tmp_dir) / "site"
            site_dir.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(_crawler, "SITE_DIR", site_dir)

            filename = "LBF-00042-stale-old-name.txt"
            conn.execute(
                """INSERT INTO entries(lb_number, date_str, location, cdr, rating, timing,
                       description, setlist, status)
                   VALUES (42, '1/1/01', 'Somewhere', '', '', '', '', '', 'ok')"""
            )
            files_url = _crawler.BASE_URL + "/files/" + filename
            conn.execute(
                "INSERT INTO entry_files(lb_number, filename, clean_name, file_url, downloaded) "
                "VALUES (42, ?, 'stale-old-name.txt', ?, 0)",
                (filename, files_url),
            )
            conn.commit()

            with patch.object(_crawler, "_load_robots"), \
                 patch.object(_crawler, "_fetch_page", return_value=(404, None, None)):
                _crawler.crawl(start_url=files_url, db_path=db_path, delay_ms=0)

            row = conn.execute(
                "SELECT downloaded FROM entry_files WHERE lb_number=42 AND filename=?",
                (filename,),
            ).fetchone()
            assert row["downloaded"] == 2

            inv = conn.execute(
                "SELECT status FROM site_inventory WHERE url=?", (files_url,)
            ).fetchone()
            assert inv is not None and inv["status"] == "not_found"

            # And the dead row must no longer be seeded as missing.
            import backend.db as db
            assert files_url not in db.get_missing_attachment_urls(db_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Flask /api/crawler/* route smoke tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawlerRoutes:
    def test_status_returns_200_with_running_key(self, client):
        resp = client.get("/api/crawler/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data

    def test_stop_returns_ok(self, client):
        resp = client.post("/api/crawler/stop")
        assert resp.status_code == 200
        assert resp.get_json().get("ok") is True

    def test_sessions_returns_list(self, client):
        resp = client.get("/api/crawler/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_sessions_limit_param_respected(self, client):
        resp = client.get("/api/crawler/sessions?limit=5")
        assert resp.status_code == 200

    def test_inventory_returns_rows_and_total(self, client):
        resp = client.get("/api/crawler/inventory")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rows" in data
        assert "total" in data
        assert isinstance(data["rows"], list)

    def test_inventory_stats_returns_dict(self, client):
        resp = client.get("/api/crawler/inventory/stats")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), dict)

    def test_start_while_already_running_returns_409(self, client):
        # Inject running=True into the module-level state, then try to start
        from backend import site_crawler
        with site_crawler._crawler_lock:
            orig = site_crawler._crawler_state["running"]
            site_crawler._crawler_state["running"] = True
        try:
            resp = client.post(
                "/api/crawler/start",
                json={"scope": "incremental"},
                content_type="application/json",
            )
            assert resp.status_code == 409
            assert resp.get_json().get("ok") is False
        finally:
            with site_crawler._crawler_lock:
                site_crawler._crawler_state["running"] = orig
