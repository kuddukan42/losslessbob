"""Tests for the Library performance-lens phase 1 union (TODO phase 1):
`backend.db.get_performances()` appends recording-less rows for olof_events
concert dates with zero `entries` coverage (`backend.gap_analysis.
uncirculated_dates`), so the 259 known Dylan concerts with no circulating
recording — and the small number of not-yet-happened dates — become
first-class Library rows instead of only existing on the standalone Gaps
screen. See BUG/TODO tracker phase-1 spec.
"""
from __future__ import annotations

import datetime
import os
import tempfile

import backend.db as db
import backend.paths as _paths

TOMORROW_ISO = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_perf_uncirc_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, date_str, location="Test Venue", rating=None, lb_category="concert"):
    conn.execute(
        "INSERT OR REPLACE INTO entries"
        " (lb_number, date_str, location, rating, description, status, lb_category)"
        " VALUES (?, ?, ?, ?, '', 'ok', ?)",
        (lb, date_str, location, rating, lb_category),
    )
    conn.commit()


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
    conn.commit()


def test_uncirculated_olof_date_appears_as_recordingless_row():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _insert_olof_event(
            conn, 1, "1975-12-04", venue="Massey Hall", city="Toronto",
            tour_name="Rolling Thunder Revue",
        )

        perfs = db.get_performances(db_path=db_path)
        row = next(p for p in perfs if p["id"] == "1975-12-04")

        assert row["recordings"] == []
        assert row["coverage"] == "uncirculated"
        assert row["status"] == "Missing"
        assert row["venue"] == "Massey Hall"
        assert row["city"] == "Toronto"
        assert row["tour"] == "Rolling Thunder Revue"
        assert row["year"] == 1975
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_future_olof_date_appears_with_upcoming_coverage():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _insert_olof_event(conn, 1, TOMORROW_ISO)

        perfs = db.get_performances(db_path=db_path)
        row = next(p for p in perfs if p["id"] == TOMORROW_ISO)

        assert row["recordings"] == []
        assert row["coverage"] == "upcoming"
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_entry_derived_rows_never_carry_coverage_key():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry(conn, 100, "6/1/00", rating="A")

        perfs = db.get_performances(db_path=db_path)
        row = next(p for p in perfs if p["date"] == "2000-06-01")

        assert "coverage" not in row
        assert len(row["recordings"]) == 1
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_covered_olof_date_does_not_duplicate_entry_row():
    """A date with both an olof concert event AND an entries row (covered) must
    produce exactly one performance row — the ordinary entry-derived one, not
    a second appended uncirculated/upcoming row (they'd collide on `id`).
    """
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _insert_olof_event(conn, 1, "2000-06-01")
        _seed_entry(conn, 100, "6/1/00", rating="A")

        perfs = db.get_performances(db_path=db_path)
        matches = [p for p in perfs if p["id"] == "2000-06-01"]

        assert len(matches) == 1
        assert "coverage" not in matches[0]
        assert len(matches[0]["recordings"]) == 1
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
