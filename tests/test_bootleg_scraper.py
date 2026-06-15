"""
Tests for the LBBCD Bootleg-CD catalog scraper (backend/bootleg_scraper.py).

Covers:
  - _parse_date()  — M/D/YY date-string parsing (pure function)
  - _parse_row()   — single <tr> -> dict (pure function over BeautifulSoup cells)
  - _diff()        — add/change/remove diff against current DB rows (pure function)
  - _apply_diff() / _record_scrape() — DB writes
  - scrape_bootlegs() — full run with mocked requests.head/get
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_bootleg_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _cells(*texts_and_html: str) -> list:
    """Build a list of BeautifulSoup <td> tags from raw cell HTML snippets."""
    html = "<tr>" + "".join(f"<td>{t}</td>" for t in texts_and_html) + "</tr>"
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("tr").find_all("td")


CATALOG_PAGE_HTML = """
<html><body>
<table><tr><td>Bob Dylan Bootleg-CD Catalog</td></tr></table>
<table>
<tr><th>Date</th><th>Title</th><th>Location</th><th>CDs</th><th>LB#</th></tr>
<tr>
  <td>08/31/69</td>
  <td>Test Show</td>
  <td>Denver, CO</td>
  <td>2</td>
  <td><a href="/detail/LB-00123.html">LB-00123</a></td>
</tr>
</table>
</body></html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _parse_date()
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDate:
    def test_empty_string(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("") == (None, None)

    def test_full_date_19xx(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("08/31/69") == ("1969-08-31", 1969)

    def test_full_date_20xx(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("01/02/05") == ("2005-01-02", 2005)

    def test_year_pivot_boundary_29_is_2000s(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("01/01/29") == ("2029-01-01", 2029)

    def test_year_pivot_boundary_30_is_1900s(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("01/01/30") == ("1930-01-01", 1930)

    def test_unknown_month_and_day(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("xx/xx/67") == ("1967", 1967)

    def test_unknown_day_only(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("11/xx/68") == ("1968-11", 1968)

    def test_unknown_month_only_falls_back_to_year(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("xx/15/05") == ("2005", 2005)

    def test_unparseable_year(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("xx/xx/xx") == (None, None)

    def test_wrong_number_of_parts(self):
        from backend.bootleg_scraper import _parse_date
        assert _parse_date("1/2") == (None, None)
        assert _parse_date("1/2/3/4") == (None, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _parse_row()
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseRow:
    def test_valid_row(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells(
            "08/31/69", "Test Show", "Denver, CO", "2",
            '<a href="/detail/LB-00123.html">LB-00123</a>',
        )
        row = _parse_row(cells)
        assert row is not None
        assert row["lb_number"] == 123
        assert row["title"] == "Test Show"
        assert row["date_str"] == "08/31/69"
        assert row["date_iso"] == "1969-08-31"
        assert row["year"] == 1969
        assert row["location"] == "Denver, CO"
        assert row["cd_count"] == 2
        assert row["lbbcd_id"] is None
        assert row["lbbcd_url"] is None

    def test_too_few_cells_returns_none(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells("08/31/69", "Test Show", "Denver, CO", "2")
        assert _parse_row(cells) is None

    def test_lb_cell_without_lb_prefix_returns_none(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells("08/31/69", "Test Show", "Denver, CO", "2", "N/A")
        assert _parse_row(cells) is None

    def test_lb_cell_non_numeric_returns_none(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells("08/31/69", "Test Show", "Denver, CO", "2", "LB-XXXXX")
        assert _parse_row(cells) is None

    def test_non_numeric_cd_count_defaults_to_zero(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells(
            "08/31/69", "Test Show", "Denver, CO", "?",
            '<a href="/detail/LB-00123.html">LB-00123</a>',
        )
        row = _parse_row(cells)
        assert row["cd_count"] == 0

    def test_lbbcd_link_parsed(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells(
            "08/31/69",
            '<a href="lbbcd/LBBCD-275.html">Test Show</a>',
            "Denver, CO", "2",
            '<a href="/detail/LB-00123.html">LB-00123</a>',
        )
        row = _parse_row(cells)
        assert row["lbbcd_id"] == 275
        assert row["lbbcd_url"] == "lbbcd/LBBCD-275.html"

    def test_lb_number_from_plain_text_cell(self):
        from backend.bootleg_scraper import _parse_row
        cells = _cells("08/31/69", "Test Show", "Denver, CO", "2", "LB-00456")
        row = _parse_row(cells)
        assert row["lb_number"] == 456


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _diff()
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiff:
    NATURAL_ROW = {
        "lb_number": 1, "title": "Show A", "date_str": "08/31/69",
        "date_iso": "1969-08-31", "year": 1969,
        "location": "Denver, CO", "cd_count": 2,
        "lbbcd_id": None, "lbbcd_url": None,
    }

    def test_new_row_is_added(self):
        from backend.bootleg_scraper import _diff
        to_add, to_change, ids_to_remove = _diff([self.NATURAL_ROW], [])
        assert to_add == [self.NATURAL_ROW]
        assert to_change == []
        assert ids_to_remove == []

    def test_unchanged_row_is_neither_added_nor_changed(self):
        from backend.bootleg_scraper import _diff
        current = [{**self.NATURAL_ROW, "id": 1}]
        to_add, to_change, ids_to_remove = _diff([self.NATURAL_ROW], current)
        assert to_add == []
        assert to_change == []
        assert ids_to_remove == []

    def test_changed_mutable_column_is_flagged(self):
        from backend.bootleg_scraper import _diff
        current = [{**self.NATURAL_ROW, "id": 7, "location": "Old Location"}]
        to_add, to_change, ids_to_remove = _diff([self.NATURAL_ROW], current)
        assert to_add == []
        assert len(to_change) == 1
        assert to_change[0]["id"] == 7
        assert to_change[0]["location"] == "Denver, CO"

    def test_row_missing_from_incoming_is_removed(self):
        from backend.bootleg_scraper import _diff
        current = [{**self.NATURAL_ROW, "id": 7}]
        to_add, to_change, ids_to_remove = _diff([], current)
        assert ids_to_remove == [7]

    def test_duplicate_natural_keys_are_deduplicated(self):
        from backend.bootleg_scraper import _diff
        to_add, to_change, ids_to_remove = _diff([self.NATURAL_ROW, dict(self.NATURAL_ROW)], [])
        assert to_add == [self.NATURAL_ROW]

    def test_change_in_non_mutable_column_is_ignored(self):
        # natural-key columns differing would mean a different key entirely,
        # so test that an extraneous column (not in _MUTABLE_COLS) is ignored.
        from backend.bootleg_scraper import _diff
        current = [{**self.NATURAL_ROW, "id": 1, "scraped_at": "old"}]
        incoming = {**self.NATURAL_ROW, "scraped_at": "new"}
        to_add, to_change, ids_to_remove = _diff([incoming], current)
        assert to_add == []
        assert to_change == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _apply_diff() / _record_scrape() — DB writes
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyDiffAndRecordScrape:
    def test_apply_diff_inserts_changes_and_removes(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.bootleg_scraper import _apply_diff

            to_add = [{
                "lb_number": 1, "title": "Show A", "date_str": "08/31/69",
                "date_iso": "1969-08-31", "year": 1969,
                "location": "Denver, CO", "cd_count": 2,
                "lbbcd_id": None, "lbbcd_url": None,
            }]
            _apply_diff(to_add, [], [], db_path)

            row = conn.execute("SELECT * FROM bootleg_titles WHERE lb_number=1").fetchone()
            assert row is not None
            assert row["title"] == "Show A"

            # Now change location and remove via id.
            _apply_diff(
                [],
                [{"id": row["id"], "location": "New York, NY", "cd_count": 3,
                  "lbbcd_id": None, "lbbcd_url": None, "date_iso": "1969-08-31", "year": 1969}],
                [],
                db_path,
            )
            updated = conn.execute("SELECT * FROM bootleg_titles WHERE id=?", (row["id"],)).fetchone()
            assert updated["location"] == "New York, NY"
            assert updated["cd_count"] == 3

            _apply_diff([], [], [row["id"]], db_path)
            assert conn.execute(
                "SELECT * FROM bootleg_titles WHERE id=?", (row["id"],)
            ).fetchone() is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_record_scrape_inserts_row(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.bootleg_scraper import _record_scrape

            _record_scrape(db_path, "http://example.com", "etag1", "lastmod1",
                            "sha", 5, 1, 2, 0, "success")

            row = conn.execute("SELECT * FROM bootleg_scrapes ORDER BY id DESC LIMIT 1").fetchone()
            assert row["source_url"] == "http://example.com"
            assert row["http_etag"] == "etag1"
            assert row["status"] == "success"
            assert row["rows_total"] == 5
            assert row["rows_added"] == 1
            assert row["rows_changed"] == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. scrape_bootlegs() — mocked requests.head/get
# ═══════════════════════════════════════════════════════════════════════════════

def _fake_head(headers: dict) -> MagicMock:
    resp = MagicMock()
    resp.headers = headers
    return resp


def _fake_get(text: str, raise_exc: Exception | None = None) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    if raise_exc:
        resp.raise_for_status.side_effect = raise_exc
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestScrapeBootlegs:
    def test_etag_match_returns_no_change(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                """INSERT INTO bootleg_scrapes
                   (source_url, http_etag, http_last_modified, body_sha256,
                    rows_total, rows_added, rows_changed, rows_removed, status)
                   VALUES ('http://x', 'etag-abc', NULL, NULL, 0, 0, 0, 0, 'success')"""
            )
            conn.commit()

            from backend import bootleg_scraper
            with patch.object(bootleg_scraper.requests, "head",
                               return_value=_fake_head({"ETag": "etag-abc"})) as mock_head, \
                 patch.object(bootleg_scraper.requests, "get") as mock_get:
                result = bootleg_scraper.scrape_bootlegs(force=False, db_path=db_path)

            assert result["status"] == "no_change"
            mock_get.assert_not_called()

            scrape_row = conn.execute(
                "SELECT * FROM bootleg_scrapes ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert scrape_row["status"] == "no_change"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_successful_scrape_inserts_new_title(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import bootleg_scraper
            with patch.object(bootleg_scraper.requests, "head",
                               return_value=_fake_head({"ETag": "etag-new",
                                                         "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"})), \
                 patch.object(bootleg_scraper.requests, "get",
                               return_value=_fake_get(CATALOG_PAGE_HTML)):
                result = bootleg_scraper.scrape_bootlegs(force=True, db_path=db_path)

            assert result["status"] == "success"
            assert result["rows_total"] == 1
            assert result["rows_added"] == 1
            assert result["rows_changed"] == 0
            assert result["rows_removed"] == 0

            row = conn.execute("SELECT * FROM bootleg_titles WHERE lb_number=123").fetchone()
            assert row is not None
            assert row["title"] == "Test Show"
            assert row["cd_count"] == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_head_request_failure_returns_failed(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import requests as _requests

            from backend import bootleg_scraper
            with patch.object(bootleg_scraper.requests, "head",
                               side_effect=_requests.RequestException("boom")):
                result = bootleg_scraper.scrape_bootlegs(force=False, db_path=db_path)

            assert result["status"] == "failed"
            assert "boom" in result["error"]

            scrape_row = conn.execute(
                "SELECT * FROM bootleg_scrapes ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert scrape_row["status"] == "failed"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_request_failure_returns_failed(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            import requests as _requests

            from backend import bootleg_scraper
            with patch.object(bootleg_scraper.requests, "head",
                               return_value=_fake_head({"ETag": "etag-new"})), \
                 patch.object(bootleg_scraper.requests, "get",
                               side_effect=_requests.RequestException("get boom")):
                result = bootleg_scraper.scrape_bootlegs(force=True, db_path=db_path)

            assert result["status"] == "failed"
            assert "get boom" in result["error"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_scrape_status_returns_dict(self):
        from backend.bootleg_scraper import get_scrape_status
        status = get_scrape_status()
        assert "running" in status
        assert "stage" in status
