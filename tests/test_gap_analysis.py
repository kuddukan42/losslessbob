"""
Tests for the Gaps view backend (backend/gap_analysis.py, TODO-256).

Covers:
  - classify_date()      — pure classifier (covered/partial/gap/future)
  - get_summary()        — year-by-year totals, olof_events-absent degrade
  - get_year_detail()    — per-date breakdown, two-show-date grouping
  - get_date_detail()    — drill-down: events, entries, partial entries, families
"""
from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path

TODAY = datetime.date.today()
TOMORROW_ISO = (TODAY + datetime.timedelta(days=1)).isoformat()
YESTERDAY_ISO = (TODAY - datetime.timedelta(days=1)).isoformat()


def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_gap_analysis_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _insert_olof_event(conn, event_id, date_str, event_type="concert", **kwargs):
    page_filename = f"page_{event_id}.html"
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
        (page_filename,),
    )
    fields = {
        "venue": "Some Hall",
        "city": "Some City",
        "region": "",
        "country": "USA",
        "tour_name": "",
        "recording_kind": "",
        "recording_mins": None,
        **kwargs,
    }
    conn.execute(
        """INSERT INTO olof_events
           (event_id, page_filename, event_type, date_str, venue, city, region,
            country, tour_name, recording_kind, recording_mins)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id, page_filename, event_type, date_str,
            fields["venue"], fields["city"], fields["region"], fields["country"],
            fields["tour_name"], fields["recording_kind"], fields["recording_mins"],
        ),
    )


def _insert_entry(conn, lb_number, date_str, lb_status="public", entry_status="ok"):
    conn.execute(
        "INSERT INTO entries (lb_number, date_str, status) VALUES (?, ?, ?)",
        (lb_number, date_str, entry_status),
    )
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status) VALUES (?, ?)",
        (lb_number, lb_status),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. classify_date() — pure, no DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifyDate:
    def test_covered(self):
        from backend.gap_analysis import classify_date
        assert classify_date("2000-07-28", "2026-01-01", {"2000-07-28"}, set()) == "covered"

    def test_partial(self):
        from backend.gap_analysis import classify_date
        assert classify_date("1987-05-03", "2026-01-01", set(), {"1987-05"}) == "partial"

    def test_gap(self):
        from backend.gap_analysis import classify_date
        assert classify_date("1975-12-04", "2026-01-01", set(), set()) == "gap"

    def test_future_beats_everything(self):
        from backend.gap_analysis import classify_date
        assert classify_date("2027-01-01", "2026-01-01", {"2027-01-01"}, set()) == "future"

    def test_exact_match_wins_over_partial(self):
        from backend.gap_analysis import classify_date
        assert classify_date(
            "1987-05-03", "2026-01-01", {"1987-05-03"}, {"1987-05"}
        ) == "covered"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_summary()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetSummary:
    def test_unavailable_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.gap_analysis import get_summary
            result = get_summary(db_path=db_path)
            assert result["available"] is False
            assert result["years"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_totals_and_year_classification(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "2000-07-28")   # covered
            _insert_entry(conn, 101, "7/28/00")

            _insert_olof_event(conn, 2, "1987-05-03")   # partial
            _insert_entry(conn, 102, "5/xx/87")

            _insert_olof_event(conn, 3, "1975-12-04")   # gap
            _insert_olof_event(conn, 4, TOMORROW_ISO)   # future
            conn.commit()

            from backend.gap_analysis import get_summary
            result = get_summary(db_path=db_path)

            assert result["available"] is True
            assert result["totals"] == {
                "shows": 4, "covered": 1, "partial": 1, "gap": 1, "future": 1,
            }
            years_by_year = {y["year"]: y for y in result["years"]}
            assert years_by_year[2000]["covered"] == 1
            assert years_by_year[1987]["partial"] == 1
            assert years_by_year[1975]["gap"] == 1
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_nonexistent_lb_number_on_gap_date_stays_gap(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-12-04")
            _insert_entry(conn, 101, "12/4/75", lb_status="nonexistent")
            conn.commit()

            from backend.gap_analysis import get_summary
            result = get_summary(db_path=db_path)
            years_by_year = {y["year"]: y for y in result["years"]}
            assert years_by_year[1975]["gap"] == 1
            assert years_by_year[1975]["covered"] == 0
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_private_entry_counts_as_covered(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-12-04")
            _insert_entry(conn, 101, "12/4/75", lb_status="private", entry_status="private")
            conn.commit()

            from backend.gap_analysis import get_summary
            result = get_summary(db_path=db_path)
            years_by_year = {y["year"]: y for y in result["years"]}
            assert years_by_year[1975]["covered"] == 1
            assert years_by_year[1975]["gap"] == 0
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. get_year_detail()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetYearDetail:
    def test_two_show_date_groups_into_one_cell(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1978-06-05", venue="Afternoon Hall")
            _insert_olof_event(conn, 2, "1978-06-05", venue="Evening Hall")
            conn.commit()

            from backend.gap_analysis import get_year_detail
            result = get_year_detail(1978, db_path=db_path)
            assert len(result["dates"]) == 1
            cell = result["dates"][0]
            assert cell["date_iso"] == "1978-06-05"
            assert len(cell["events"]) == 2
            assert cell["coverage"] == "gap"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_covered_date_lists_lb_numbers(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()

            from backend.gap_analysis import get_year_detail
            result = get_year_detail(2000, db_path=db_path)
            cell = result["dates"][0]
            assert cell["coverage"] == "covered"
            assert cell["lb_numbers"] == [101]
            assert cell["partial_lb_numbers"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_empty_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.gap_analysis import get_year_detail
            assert get_year_detail(2000, db_path=db_path) == {"dates": []}
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. get_date_detail()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetDateDetail:
    def test_gap_date_proves_absence(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(
                conn, 1, "1975-12-04", venue="Massey Hall", recording_kind="none known",
            )
            conn.commit()

            from backend.gap_analysis import get_date_detail
            result = get_date_detail("1975-12-04", db_path=db_path)
            assert result["available"] is True
            assert len(result["events"]) == 1
            assert result["events"][0]["venue"] == "Massey Hall"
            assert result["entries"] == []
            assert result["partial_entries"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_covered_date_lists_entries(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()

            from backend.gap_analysis import get_date_detail
            result = get_date_detail("2000-07-28", db_path=db_path)
            assert [e["lb_number"] for e in result["entries"]] == [101]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_partial_entry_surfaces_as_month_candidate(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1987-05-03")
            _insert_entry(conn, 102, "5/xx/87")
            conn.commit()

            from backend.gap_analysis import get_date_detail
            result = get_date_detail("1987-05-03", db_path=db_path)
            assert result["entries"] == []
            assert [e["lb_number"] for e in result["partial_entries"]] == [102]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_unavailable_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.gap_analysis import get_date_detail
            result = get_date_detail("2000-07-28", db_path=db_path)
            assert result["available"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
