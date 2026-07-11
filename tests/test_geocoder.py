"""
Tests for the Nominatim geocoder (backend/geocoder.py).

Covers:
  - _entry_date_to_iso()                    — M/D/YY -> YYYY-MM-DD (pure function)
  - _get_performance_location_string()      — dylan_performances lookup
  - _get_bobdylan_shows_location_string()    — bobdylan_shows lookup
  - _get_olof_events_location_string()      — olof_events lookup (TODO-224)
  - _is_concert_location()                  — concert-only eligibility, olof-authoritative (TODO-224)
  - _get_setlistfm_location_string()        — setlistfm_shows lookup
  - geocode_one()                           — Nominatim lookup (mocked urllib)
  - place_manual()                          — manual pin upsert
  - run_batch()                             — batch geocoding worker, source priority
  - get_progress()
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_geocoder_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _make_urlopen_response(json_data):
    """Build a context-manager mock matching urllib.request.urlopen()'s return value."""
    cm = MagicMock()
    cm.read.return_value = json.dumps(json_data).encode("utf-8")
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cm)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _entry_date_to_iso()
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntryDateToIso:
    def test_full_date_2000s(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("7/28/00") == "2000-07-28"

    def test_full_date_4digit_year(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("1/2/1978") == "1978-01-02"

    def test_year_pivot_49_is_1900s(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("1/2/49") == "1949-01-02"

    def test_year_pivot_48_is_2000s(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("1/2/48") == "2048-01-02"

    def test_partial_date_with_xx_returns_none(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("5/xx/87") is None

    def test_empty_string_returns_none(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("") is None

    def test_wrong_part_count_returns_none(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("1/2") is None

    def test_unparseable_returns_none(self):
        from backend.geocoder import _entry_date_to_iso
        assert _entry_date_to_iso("not/a/date") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _get_performance_location_string()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPerformanceLocationString:
    def test_returns_structured_string_on_match(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_performance_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-07-28', 'Madison Square Garden', 'New York', 'NY', 'USA')"""
            )
            conn.commit()

            result = _get_performance_location_string("Raw Loc", conn)
            assert result == "Madison Square Garden, New York, NY, USA"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_drops_blank_and_question_mark_parts(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_performance_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-07-28', 'Madison Square Garden', 'New York', '?', '')"""
            )
            conn.commit()

            result = _get_performance_location_string("Raw Loc", conn)
            assert result == "Madison Square Garden, New York"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_matching_performance_returns_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_performance_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.commit()

            assert _get_performance_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_unparseable_date_str_is_skipped(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_performance_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '5/xx/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-05-01', 'Some Venue', 'Some City', 'ST', 'USA')"""
            )
            conn.commit()

            assert _get_performance_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _get_bobdylan_shows_location_string()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetBobdylanShowsLocationString:
    def test_returns_structured_string_on_match(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_bobdylan_shows_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Purple Onion', 'St. Paul, MN')"""
            )
            conn.commit()

            result = _get_bobdylan_shows_location_string("Raw Loc", conn)
            assert result == "The Purple Onion, St. Paul, MN"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_drops_blank_parts(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_bobdylan_shows_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Purple Onion', '')"""
            )
            conn.commit()

            result = _get_bobdylan_shows_location_string("Raw Loc", conn)
            assert result == "The Purple Onion"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_matching_show_returns_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_bobdylan_shows_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.commit()

            assert _get_bobdylan_shows_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _get_olof_events_location_string()  (TODO-224)
# ═══════════════════════════════════════════════════════════════════════════════

def _insert_olof_event(conn, event_id, event_type, date_str, venue, city, region, country,
                        page_filename="p1"):
    """Insert an olof_pages row (if needed) and an olof_events row for tests."""
    existing = conn.execute(
        "SELECT 1 FROM olof_pages WHERE filename=?", (page_filename,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
            (page_filename,),
        )
    conn.execute(
        """INSERT INTO olof_events
           (event_id, page_filename, event_type, date_str, venue, city, region, country)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, page_filename, event_type, date_str, venue, city, region, country),
    )


class TestGetOlofEventsLocationString:
    def test_returns_structured_string_on_match(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_olof_events_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            _insert_olof_event(conn, 1, "concert", "2000-07-28", "Massey Hall", "Toronto", "ON", "Canada")
            conn.commit()

            result = _get_olof_events_location_string("Raw Loc", conn)
            assert result == ("Massey Hall, Toronto, ON, Canada", "Toronto, ON, Canada")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_drops_blank_parts(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_olof_events_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            _insert_olof_event(conn, 1, "concert", "2000-07-28", "Massey Hall", "Toronto", "", "")
            conn.commit()

            result = _get_olof_events_location_string("Raw Loc", conn)
            assert result == ("Massey Hall, Toronto", "Toronto")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_matching_event_returns_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_olof_events_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.commit()

            assert _get_olof_events_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_prefers_concert_event_type_when_multiple_events_same_date(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_olof_events_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            _insert_olof_event(conn, 1, "interview", "2000-07-28", "TV Studio", "Toronto", "ON", "Canada")
            _insert_olof_event(conn, 2, "concert", "2000-07-28", "Massey Hall", "Toronto", "ON", "Canada")
            conn.commit()

            result = _get_olof_events_location_string("Raw Loc", conn)
            assert result == ("Massey Hall, Toronto, ON, Canada", "Toronto, ON, Canada")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_absent_table_returns_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_olof_events_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute("DROP TABLE olof_events")
            conn.commit()

            assert _get_olof_events_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. _is_concert_location()  (TODO-221, olof-authoritative TODO-224)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsConcertLocation:
    def test_olof_concert_event_is_eligible(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _is_concert_location
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            _insert_olof_event(conn, 1, "concert", "2000-07-28", "Massey Hall", "Toronto", "ON", "Canada")
            conn.commit()

            eligible, note = _is_concert_location("Raw Loc", conn)
            assert eligible is True
            assert note is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_olof_non_concert_event_is_ineligible_with_note(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _is_concert_location
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            _insert_olof_event(conn, 1, "interview", "2000-07-28", "TV Studio", "Toronto", "ON", "Canada")
            conn.commit()

            eligible, note = _is_concert_location("Raw Loc", conn)
            assert eligible is False
            assert note == "olof_events: non-concert event_type=interview"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_olof_match_is_authoritative_over_bobdylan_shows_match(self):
        # Same date has a bobdylan_shows row too, but the TODO-224 rule is
        # that an olof_events match wins outright once present.
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _is_concert_location
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Fillmore', 'San Francisco, CA')"""
            )
            _insert_olof_event(conn, 1, "rehearsal", "2000-07-28", "Rehearsal Hall", "SF", "CA", "USA")
            conn.commit()

            eligible, note = _is_concert_location("Raw Loc", conn)
            assert eligible is False
            assert note == "olof_events: non-concert event_type=rehearsal"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_absent_olof_table_falls_back_to_heuristic_eligible(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _is_concert_location
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Fillmore', 'San Francisco, CA')"""
            )
            conn.execute("DROP TABLE olof_events")
            conn.commit()

            eligible, note = _is_concert_location("Raw Loc", conn)
            assert eligible is True
            assert note is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_absent_olof_table_falls_back_to_heuristic_ineligible(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _is_concert_location
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) "
                "VALUES (1, '7/28/00', 'compilation tape', 'ok')"
            )
            conn.execute("DROP TABLE olof_events")
            conn.commit()

            eligible, note = _is_concert_location("compilation tape", conn)
            assert eligible is False
            assert note is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. _get_setlistfm_location_string()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetSetlistfmLocationString:
    def test_returns_structured_string_on_match(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_setlistfm_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city, country)
                   VALUES ('s1', '2000-07-28', 'Thalia Mara Hall', 'Jackson', 'United States')"""
            )
            conn.commit()

            result = _get_setlistfm_location_string("Raw Loc", conn)
            assert result == "Thalia Mara Hall, Jackson, United States"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_drops_blank_parts(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_setlistfm_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.execute(
                """INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city, country)
                   VALUES ('s1', '2000-07-28', 'Thalia Mara Hall', '', '')"""
            )
            conn.commit()

            result = _get_setlistfm_location_string("Raw Loc", conn)
            assert result == "Thalia Mara Hall"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_matching_show_returns_none(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend.geocoder import _get_setlistfm_location_string
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Loc', 'ok')"
            )
            conn.commit()

            assert _get_setlistfm_location_string("Raw Loc", conn) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. geocode_one()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeocodeOne:
    def test_high_confidence_result(self):
        from backend import geocoder
        nominatim_result = [{
            "lat": "39.7392", "lon": "-104.9903",
            "display_name": "Denver, Colorado, USA",
            "importance": 0.6,
        }]
        with patch.object(geocoder.urllib.request, "urlopen",
                           return_value=_make_urlopen_response(nominatim_result)):
            result = geocoder.geocode_one("Denver, CO")

        assert result["source"] == "nominatim"
        assert result["confidence"] == "high"
        assert result["lat"] == pytest.approx(39.7392)
        assert result["lon"] == pytest.approx(-104.9903)
        assert result["display_name"] == "Denver, Colorado, USA"

    def test_medium_confidence_result(self):
        from backend import geocoder
        nominatim_result = [{"lat": "1.0", "lon": "2.0", "display_name": "X", "importance": 0.35}]
        with patch.object(geocoder.urllib.request, "urlopen",
                           return_value=_make_urlopen_response(nominatim_result)):
            result = geocoder.geocode_one("X")
        assert result["confidence"] == "medium"

    def test_low_confidence_result(self):
        from backend import geocoder
        nominatim_result = [{"lat": "1.0", "lon": "2.0", "display_name": "X", "importance": 0.1}]
        with patch.object(geocoder.urllib.request, "urlopen",
                           return_value=_make_urlopen_response(nominatim_result)):
            result = geocoder.geocode_one("X")
        assert result["confidence"] == "low"

    def test_empty_result_returns_failed(self):
        from backend import geocoder
        with patch.object(geocoder.urllib.request, "urlopen",
                           return_value=_make_urlopen_response([])):
            result = geocoder.geocode_one("Nowhere")

        assert result["source"] == "failed"
        assert result["confidence"] is None
        assert result["lat"] is None

    def test_http_429_raises_rate_limit_error(self):
        from backend import geocoder
        err = urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None)
        with patch.object(geocoder.urllib.request, "urlopen", side_effect=err):
            with pytest.raises(geocoder._RateLimitError):
                geocoder.geocode_one("Denver, CO")

    def test_other_http_error_returns_failed(self):
        from backend import geocoder
        err = urllib.error.HTTPError("http://x", 500, "Server Error", {}, None)
        with patch.object(geocoder.urllib.request, "urlopen", side_effect=err):
            result = geocoder.geocode_one("Denver, CO")

        assert result["source"] == "failed"
        assert result["confidence"] is None
        assert "note" in result

    def test_generic_exception_returns_failed(self):
        from backend import geocoder
        with patch.object(geocoder.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("boom")):
            result = geocoder.geocode_one("Denver, CO")

        assert result["source"] == "failed"
        assert result["confidence"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. place_manual()
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlaceManual:
    def test_inserts_manual_row(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import geocoder
            geocoder.place_manual("Custom Venue", 10.0, 20.0, note="test note", lb_number="123")

            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Custom Venue",)
            ).fetchone()
            assert row["lat"] == 10.0
            assert row["lon"] == 20.0
            assert row["source"] == "manual"
            assert row["confidence"] == "high"
            assert row["manual_override"] == 1
            assert row["note"] == "test note"
            assert row["lb_number"] == "123"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_update_existing_row_preserves_lb_number(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import geocoder
            geocoder.place_manual("Custom Venue", 10.0, 20.0, lb_number="123")
            geocoder.place_manual("Custom Venue", 11.0, 21.0, note="updated")

            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Custom Venue",)
            ).fetchone()
            assert row["lat"] == 11.0
            assert row["lon"] == 21.0
            assert row["note"] == "updated"
            assert row["lb_number"] == "123"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. run_batch()
# ═══════════════════════════════════════════════════════════════════════════════

def _fake_geocode(loc):
    return {
        "location_text": loc, "lat": 1.0, "lon": 2.0,
        "display_name": loc, "source": "nominatim", "confidence": "high",
    }


class TestRunBatch:
    def test_geocodes_new_locations(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.executemany(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (?, ?, ?, 'ok')",
                [(1, "7/28/00", "Denver, CO"), (2, "1/1/01", "Boulder, CO")],
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one", side_effect=_fake_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            rows = conn.execute(
                "SELECT location_text, source FROM location_geocoded ORDER BY location_text"
            ).fetchall()
            assert [r["location_text"] for r in rows] == ["Boulder, CO", "Denver, CO"]
            assert all(r["source"] == "nominatim" for r in rows)

            progress = geocoder.get_progress()
            assert progress["running"] is False
            assert progress["done"] == 2
            assert progress["total"] == 2
            assert progress["errors"] == 0
            assert progress["succeeded"] == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_dry_run_does_not_write(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Denver, CO', 'ok')"
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one", side_effect=_fake_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path, dry_run=True)

            count = conn.execute("SELECT COUNT(*) FROM location_geocoded").fetchone()[0]
            assert count == 0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_limit_restricts_number_processed(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.executemany(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (?, ?, ?, 'ok')",
                [(1, "7/28/00", "Denver, CO"), (2, "1/1/01", "Boulder, CO"), (3, "2/2/02", "Aspen, CO")],
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one", side_effect=_fake_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path, limit=1)

            count = conn.execute("SELECT COUNT(*) FROM location_geocoded").fetchone()[0]
            assert count == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_manual_override_is_never_reprocessed(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Denver, CO', 'ok')"
            )
            conn.execute(
                """INSERT INTO location_geocoded (location_text, lat, lon, source, confidence, manual_override)
                   VALUES ('Denver, CO', 5.0, 6.0, 'manual', 'high', 1)"""
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one") as mock_geocode, \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path, retry_failed=True)

            mock_geocode.assert_not_called()
            row = conn.execute(
                "SELECT lat FROM location_geocoded WHERE location_text=?", ("Denver, CO",)
            ).fetchone()
            assert row["lat"] == 5.0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_retry_failed_reprocesses_failed_rows(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Denver, CO', 'ok')"
            )
            conn.execute(
                """INSERT INTO location_geocoded (location_text, lat, lon, source, confidence, manual_override)
                   VALUES ('Denver, CO', NULL, NULL, 'failed', NULL, 0)"""
            )
            conn.commit()

            from backend import geocoder

            # Without retry_failed, the failed row is left alone.
            with patch.object(geocoder, "geocode_one") as mock_geocode, \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path, retry_failed=False)
            mock_geocode.assert_not_called()

            # With retry_failed, it is re-geocoded and updated.
            with patch.object(geocoder, "geocode_one", side_effect=_fake_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path, retry_failed=True)

            row = conn.execute(
                "SELECT source FROM location_geocoded WHERE location_text=?", ("Denver, CO",)
            ).fetchone()
            assert row["source"] == "nominatim"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_uses_performances_table_for_structured_query(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-07-28', 'Madison Square Garden', 'New York', 'NY', 'USA')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "low"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "Madison Square Garden, New York, NY, USA"
            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "performances"
            assert row["confidence"] == "medium"  # promoted from 'low'
            assert row["note"].startswith("performances:")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_uses_bobdylan_shows_as_primary_source(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Fillmore', 'San Francisco, CA')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "high"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "The Fillmore, San Francisco, CA"
            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "bobdylan_shows"
            assert row["note"].startswith("bobdylan_shows:")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_uses_setlistfm_shows_when_no_bobdylan_shows_match(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                """INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city, country)
                   VALUES ('s1', '2000-07-28', 'Thalia Mara Hall', 'Jackson', 'United States')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "high"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "Thalia Mara Hall, Jackson, United States"
            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "setlistfm_shows"
            assert row["note"].startswith("setlistfm_shows:")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_uses_olof_events_when_no_bobdylan_shows_match(self):
        """TODO-224: olof_events is a structured source, hit end-to-end via run_batch."""
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                "INSERT INTO olof_pages (filename, url, corpus) VALUES ('p1', 'http://x', 'dsn')"
            )
            conn.execute(
                """INSERT INTO olof_events
                   (event_id, page_filename, event_type, date_str, venue, city, region, country)
                   VALUES (1, 'p1', 'concert', '2000-07-28', 'Massey Hall', 'Toronto', 'ON', 'Canada')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "high"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "Massey Hall, Toronto, ON, Canada"
            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "olof_events"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_olof_non_concert_event_skipped_with_event_type_note(self):
        """TODO-224: a non-concert olof_events date match is authoritative — the
        location is written skipped_not_concert with the event_type in note, and
        Nominatim is never called."""
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                "INSERT INTO olof_pages (filename, url, corpus) VALUES ('p1', 'http://x', 'dsn')"
            )
            conn.execute(
                """INSERT INTO olof_events
                   (event_id, page_filename, event_type, date_str, venue, city, region, country)
                   VALUES (1, 'p1', 'session', '2000-07-28', 'Studio A', 'New York', 'NY', 'USA')"""
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one") as mock_geocode, \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            mock_geocode.assert_not_called()
            row = conn.execute(
                "SELECT * FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "skipped_not_concert"
            assert row["note"] == "olof_events: non-concert event_type=session"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_bobdylan_shows_takes_priority_over_performances(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-07-28', 'Madison Square Garden', 'New York', 'NY', 'USA')"""
            )
            conn.execute(
                """INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)
                   VALUES ('u1', '2000-07-28', 'The Fillmore', 'San Francisco, CA')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "high"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "The Fillmore, San Francisco, CA"
            row = conn.execute(
                "SELECT source FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "bobdylan_shows"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_setlistfm_shows_takes_priority_over_performances(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Raw Location', 'ok')"
            )
            conn.execute(
                """INSERT INTO dylan_performances (event_id, date_str, venue, city, state, country)
                   VALUES ('evt1', '2000-07-28', 'Madison Square Garden', 'New York', 'NY', 'USA')"""
            )
            conn.execute(
                """INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city, country)
                   VALUES ('s1', '2000-07-28', 'Thalia Mara Hall', 'Jackson', 'United States')"""
            )
            conn.commit()

            from backend import geocoder
            captured = {}

            def _capture_geocode(loc):
                captured["query"] = loc
                return {"location_text": loc, "lat": 1.0, "lon": 2.0,
                        "display_name": loc, "source": "nominatim", "confidence": "high"}

            with patch.object(geocoder, "geocode_one", side_effect=_capture_geocode), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            assert captured["query"] == "Thalia Mara Hall, Jackson, United States"
            row = conn.execute(
                "SELECT source FROM location_geocoded WHERE location_text=?", ("Raw Location",)
            ).fetchone()
            assert row["source"] == "setlistfm_shows"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_rate_limit_retry_then_success(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Denver, CO', 'ok')"
            )
            conn.commit()

            from backend import geocoder
            good_result = {"location_text": "Denver, CO", "lat": 1.0, "lon": 2.0,
                            "display_name": "Denver", "source": "nominatim", "confidence": "high"}
            with patch.object(geocoder, "geocode_one",
                               side_effect=[geocoder._RateLimitError("Denver, CO"), good_result]), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            row = conn.execute(
                "SELECT source FROM location_geocoded WHERE location_text=?", ("Denver, CO",)
            ).fetchone()
            assert row["source"] == "nominatim"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_rate_limit_exhausted_marks_failed(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, status) VALUES (1, '7/28/00', 'Denver, CO', 'ok')"
            )
            conn.commit()

            from backend import geocoder
            with patch.object(geocoder, "geocode_one",
                               side_effect=geocoder._RateLimitError("Denver, CO")), \
                 patch.object(geocoder.time, "sleep"):
                geocoder.run_batch(db_path=db_path)

            row = conn.execute(
                "SELECT source, note FROM location_geocoded WHERE location_text=?", ("Denver, CO",)
            ).fetchone()
            assert row["source"] == "failed"
            assert "429" in row["note"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. get_progress()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetProgress:
    def test_has_expected_keys(self):
        from backend.geocoder import get_progress
        progress = get_progress()
        for key in ("running", "done", "total", "current", "errors", "stage", "succeeded"):
            assert key in progress
