"""
Tests for backend/gap_analysis.py — concert-date coverage classification
(originally TODO-256's Gaps view; the standalone screen was retired once its
coverage grid became a Library performance-lens view, see module docstring).

Covers:
  - classify_date()      — pure classifier (covered/partial/gap/future)
  - get_date_detail()    — drill-down: events, entries, partial entries, families
  - uncirculated_dates() — Library performance-lens recording-less rows
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
# 2. get_date_detail()
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


# ═══════════════════════════════════════════════════════════════════════════════
# 3. uncirculated_dates() — Library performance-lens phase 1 (recording-less rows)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUncirculatedDates:
    def test_only_gap_and_future_dates_returned(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "2000-07-28")   # covered
            _insert_entry(conn, 101, "7/28/00")

            _insert_olof_event(conn, 2, "1987-05-03")   # partial
            _insert_entry(conn, 102, "5/xx/87")

            _insert_olof_event(conn, 3, "1975-12-04")   # gap
            _insert_olof_event(conn, 4, TOMORROW_ISO)   # future
            conn.commit()

            from backend.gap_analysis import uncirculated_dates
            result = uncirculated_dates(db_path=db_path)
            by_date = {r["date_iso"]: r for r in result}

            assert set(by_date) == {"1975-12-04", TOMORROW_ISO}
            assert by_date["1975-12-04"]["coverage"] == "uncirculated"
            assert by_date[TOMORROW_ISO]["coverage"] == "upcoming"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_carries_venue_city_tour_from_first_event(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(
                conn, 1, "1975-12-04", venue="Massey Hall", city="Toronto",
                tour_name="Rolling Thunder Revue",
            )
            conn.commit()

            from backend.gap_analysis import uncirculated_dates
            result = uncirculated_dates(db_path=db_path)
            assert len(result) == 1
            row = result[0]
            assert row["venue"] == "Massey Hall"
            assert row["city"] == "Toronto"
            assert row["tour"] == "Rolling Thunder Revue"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_blank_venue_city_tour_become_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-12-04", venue="", city="", tour_name="")
            conn.commit()

            from backend.gap_analysis import uncirculated_dates
            result = uncirculated_dates(db_path=db_path)
            row = result[0]
            assert row["venue"] is None
            assert row["city"] is None
            assert row["tour"] is None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_covered_and_partial_dates_excluded(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00")

            _insert_olof_event(conn, 2, "1987-05-03")
            _insert_entry(conn, 102, "5/xx/87")
            conn.commit()

            from backend.gap_analysis import uncirculated_dates
            assert uncirculated_dates(db_path=db_path) == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_empty_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.gap_analysis import uncirculated_dates
            assert uncirculated_dates(db_path=db_path) == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
