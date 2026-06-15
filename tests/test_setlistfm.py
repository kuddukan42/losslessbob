"""
Tests for the setlist.fm API integration (backend/setlistfm.py).

Covers:
  - _parse_date()    — DD-MM-YYYY -> YYYY-MM-DD (pure function)
  - _fetch_page()    — HTTP fetch with 429/401/retry handling (mocked requests.get)
  - _parse_setlist() — API setlist object -> (show_row, track_rows)
  - save_api_key() / get_api_key()
  - run_update()     — full pagination run (mocked _fetch_page)
  - get_status() / stop() / is_running()
"""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_setlistfm_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


SETLIST_OBJ = {
    "id": "abc123",
    "eventDate": "07-06-1978",
    "tour": {"name": "1978 World Tour"},
    "venue": {
        "name": "The Forum",
        "city": {
            "name": "Los Angeles",
            "country": {"name": "USA"},
        },
    },
    "info": "Great show",
    "url": "https://www.setlist.fm/setlist/bob-dylan/1978/the-forum-abc123.html",
    "sets": {
        "set": [
            {
                "name": "",
                "song": [
                    {"name": "Mr. Tambourine Man"},
                    {"name": "Like a Rolling Stone", "info": "with band"},
                ],
            },
            {
                "name": "Encore",
                "encore": 1,
                "song": [
                    {
                        "name": "Knockin' on Heaven's Door",
                        "cover": {"name": "Bob Dylan"},
                        "tape": True,
                    },
                ],
            },
        ]
    },
}

# Single-page response (itemsPerPage=2, total=1 -> total_pages = ceil(1/2) = 1)
PAGE_SINGLE = {
    "itemsPerPage": 2,
    "total": 1,
    "setlist": [SETLIST_OBJ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _parse_date()
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDate:
    def test_valid_date_converted_to_iso(self):
        from backend.setlistfm import _parse_date
        assert _parse_date("07-06-1978") == "1978-06-07"

    def test_invalid_date_returned_unchanged(self):
        from backend.setlistfm import _parse_date
        assert _parse_date("not-a-date") == "not-a-date"

    def test_empty_string_returned_unchanged(self):
        from backend.setlistfm import _parse_date
        assert _parse_date("") == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _fetch_page()
# ═══════════════════════════════════════════════════════════════════════════════

class TestFetchPage:
    def test_success_returns_json(self):
        from backend import setlistfm
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"total": 1}
        with patch.object(setlistfm.requests, "get", return_value=resp):
            result = setlistfm._fetch_page(1, "key")
        assert result == {"total": 1}

    def test_401_raises_value_error(self):
        from backend import setlistfm
        resp = MagicMock()
        resp.status_code = 401
        with patch.object(setlistfm.requests, "get", return_value=resp):
            with pytest.raises(ValueError):
                setlistfm._fetch_page(1, "bad-key")

    def test_429_retries_then_succeeds(self):
        from backend import setlistfm
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"total": 0}
        with patch.object(setlistfm.requests, "get", side_effect=[resp_429, resp_ok]), \
             patch.object(setlistfm.time, "sleep"):
            result = setlistfm._fetch_page(1, "key")
        assert result == {"total": 0}

    def test_request_exception_returns_none_after_retries(self):
        from backend import setlistfm
        with patch.object(setlistfm.requests, "get",
                           side_effect=requests.RequestException("boom")), \
             patch.object(setlistfm.time, "sleep"):
            result = setlistfm._fetch_page(1, "key")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _parse_setlist()
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseSetlist:
    def test_show_row_fields(self):
        from backend.setlistfm import _parse_setlist
        show_row, _ = _parse_setlist(SETLIST_OBJ)

        assert show_row == {
            "setlistfm_id": "abc123",
            "date_str": "1978-06-07",
            "tour_name": "1978 World Tour",
            "venue_name": "The Forum",
            "city": "Los Angeles",
            "country": "USA",
            "info": "Great show",
            "setlistfm_url": "https://www.setlist.fm/setlist/bob-dylan/1978/the-forum-abc123.html",
        }

    def test_track_rows_flattened_with_global_position(self):
        from backend.setlistfm import _parse_setlist
        _, track_rows = _parse_setlist(SETLIST_OBJ)

        assert len(track_rows) == 3
        assert track_rows[0]["track_name"] == "Mr. Tambourine Man"
        assert track_rows[0]["set_index"] == 0
        assert track_rows[0]["position"] == 0
        assert track_rows[0]["set_position"] == 0
        assert track_rows[0]["is_encore"] == 0
        assert track_rows[0]["is_cover"] == 0
        assert track_rows[0]["is_tape"] == 0

        assert track_rows[1]["track_name"] == "Like a Rolling Stone"
        assert track_rows[1]["info"] == "with band"
        assert track_rows[1]["position"] == 1

        encore = track_rows[2]
        assert encore["track_name"] == "Knockin' on Heaven's Door"
        assert encore["set_index"] == 1
        assert encore["set_name"] == "Encore"
        assert encore["is_encore"] == 1
        assert encore["position"] == 2
        assert encore["set_position"] == 0
        assert encore["is_cover"] == 1
        assert encore["cover_artist"] == "Bob Dylan"
        assert encore["is_tape"] == 1

    def test_missing_optional_fields_default_safely(self):
        from backend.setlistfm import _parse_setlist
        minimal = {"id": "xyz", "eventDate": "01-01-2000"}
        show_row, track_rows = _parse_setlist(minimal)

        assert show_row["setlistfm_id"] == "xyz"
        assert show_row["venue_name"] == ""
        assert show_row["city"] == ""
        assert show_row["country"] == ""
        assert show_row["tour_name"] == ""
        assert track_rows == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. API key storage
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiKey:
    def test_save_and_get_round_trip(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            setlistfm.save_api_key("  my-key-123  ", db_path=db_path)
            assert setlistfm.get_api_key(db_path=db_path) == "my-key-123"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_api_key_returns_none_if_unset(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            assert setlistfm.get_api_key(db_path=db_path) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. run_update()
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunUpdate:
    def test_stores_shows_and_tracks(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            with patch.object(setlistfm, "_fetch_page", return_value=PAGE_SINGLE), \
                 patch.object(setlistfm.time, "sleep"):
                shows = setlistfm.run_update(db_path=db_path, api_key="test-key")

            assert shows == 1
            row = conn.execute("SELECT * FROM setlistfm_shows WHERE setlistfm_id=?", ("abc123",)).fetchone()
            assert row["tour_name"] == "1978 World Tour"
            assert row["date_str"] == "1978-06-07"

            tracks = conn.execute(
                "SELECT * FROM setlistfm_setlist WHERE setlistfm_id=? ORDER BY position", ("abc123",)
            ).fetchall()
            assert len(tracks) == 3

            status = setlistfm.get_status()
            assert status["status"] == "done"
            assert status["shows_stored"] == 1
            assert status["tracks_stored"] == 3
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_without_force_does_not_overwrite_existing_show(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            with patch.object(setlistfm, "_fetch_page", return_value=PAGE_SINGLE), \
                 patch.object(setlistfm.time, "sleep"):
                setlistfm.run_update(db_path=db_path, api_key="test-key")

            modified = copy.deepcopy(PAGE_SINGLE)
            modified["setlist"][0]["tour"]["name"] = "Changed Tour"
            with patch.object(setlistfm, "_fetch_page", return_value=modified), \
                 patch.object(setlistfm.time, "sleep"):
                setlistfm.run_update(db_path=db_path, api_key="test-key", force=False)

            row = conn.execute("SELECT tour_name FROM setlistfm_shows WHERE setlistfm_id=?", ("abc123",)).fetchone()
            assert row["tour_name"] == "1978 World Tour"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_force_replaces_existing_show(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            with patch.object(setlistfm, "_fetch_page", return_value=PAGE_SINGLE), \
                 patch.object(setlistfm.time, "sleep"):
                setlistfm.run_update(db_path=db_path, api_key="test-key")

            modified = copy.deepcopy(PAGE_SINGLE)
            modified["setlist"][0]["tour"]["name"] = "Changed Tour"
            with patch.object(setlistfm, "_fetch_page", return_value=modified), \
                 patch.object(setlistfm.time, "sleep"):
                setlistfm.run_update(db_path=db_path, api_key="test-key", force=True)

            row = conn.execute("SELECT tour_name FROM setlistfm_shows WHERE setlistfm_id=?", ("abc123",)).fetchone()
            assert row["tour_name"] == "Changed Tour"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_without_api_key_returns_zero_and_errors(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            result = setlistfm.run_update(db_path=db_path, api_key=None)
            assert result == 0
            assert setlistfm.get_status()["status"] == "error"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_stop_requested_halts_pagination(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            from backend import setlistfm
            # 3 items / 1 per page -> 3 total pages
            page_multi = {"itemsPerPage": 1, "total": 3, "setlist": [SETLIST_OBJ]}

            def _fetch_side_effect(page, key):
                if page == 1:
                    setlistfm.stop()
                return page_multi

            with patch.object(setlistfm, "_fetch_page", side_effect=_fetch_side_effect), \
                 patch.object(setlistfm.time, "sleep"):
                shows = setlistfm.run_update(db_path=db_path, api_key="test-key")

            assert shows == 1  # only page 1 processed before stop halts the loop
            assert setlistfm.get_status()["status"] == "done"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Status helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusHelpers:
    def test_get_status_has_expected_keys(self):
        from backend.setlistfm import get_status
        status = get_status()
        for key in ("status", "page", "total_pages", "shows_stored",
                     "tracks_stored", "errors", "stop_requested", "message"):
            assert key in status

    def test_stop_sets_flag(self):
        from backend import setlistfm
        try:
            setlistfm.stop()
            assert setlistfm.get_status()["stop_requested"] is True
        finally:
            setlistfm._set(stop_requested=False)

    def test_is_running_reflects_status(self):
        from backend import setlistfm
        setlistfm._set(status="idle")
        assert setlistfm.is_running() is False
        setlistfm._set(status="running")
        assert setlistfm.is_running() is True
        setlistfm._set(status="idle")
