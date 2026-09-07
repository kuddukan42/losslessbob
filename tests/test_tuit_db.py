"""Tests for the tuit_recordings / tuit_downloads accessors in backend.db.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
import json
import os
import shutil
import tempfile

import pytest


def _make_db() -> tuple[str, str]:
    """Create a fresh temp DB with the full schema. Returns (db_path, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtuit_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    return db_path, tmp_dir


@pytest.fixture
def dbmod():
    """Yield backend.db bound to a throwaway database."""
    import backend.db as db
    db_path, tmp_dir = _make_db()
    try:
        yield db, db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _row(rec_id: int = 1837, **over) -> dict:
    row = {
        "rec_id": rec_id,
        "show_id": rec_id,
        "lb_number": 11637,
        "detail_url": f"https://tangledupintorrents.org/recordings/{rec_id}",
        "title": "Providence, Civic Center",
        "date_str": "1978-10-07",
        "venue": "Civic Center",
        "source_type": "AUD",
        "format": "FLAC 16/44",
        "quality": "Very good",
        "info_hash": "1b00b58b849e69e4b4d9601c257dbd406276f47e",
        "size_bytes": 1055307857,
        "n_files": 37,
        "seeders": 1,
        "freeleech": True,
        "lb_verified": True,
        "uploader": "tabby",
        "added_at": "2026-08-20T00:46:10+00:00",
        "lineage": "reel > dat > tlh",
        "setlist_json": json.dumps([{"track": "1", "song": "My Back Pages"}]),
    }
    row.update(over)
    return row


class TestUpsertTuitRecording:
    def test_insert_and_read_back(self, dbmod):
        db, path = dbmod
        assert db.upsert_tuit_recording(_row(), path) == 1837
        got = db.get_tuit_recording(1837, path)
        assert got["lb_number"] == 11637
        assert got["info_hash"].endswith("6276f47e")
        assert got["size_bytes"] == 1055307857
        assert got["first_seen_at"] and got["last_seen_at"]

    def test_booleans_are_stored_as_ints(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(freeleech=True, lb_verified=False), path)
        got = db.get_tuit_recording(1837, path)
        assert got["freeleech"] == 1
        assert got["lb_verified"] == 0

    def test_upsert_is_idempotent_and_updates_in_place(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(seeders=1), path)
        db.upsert_tuit_recording(_row(seeders=9, quality="Excellent"), path)
        rows = db.get_tuit_recordings(db_path=path)
        assert len(rows) == 1
        assert rows[0]["seeders"] == 9
        assert rows[0]["quality"] == "Excellent"

    def test_first_seen_at_survives_a_refresh(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(), path)
        first = db.get_tuit_recording(1837, path)["first_seen_at"]
        db.upsert_tuit_recording(_row(seeders=5), path)
        assert db.get_tuit_recording(1837, path)["first_seen_at"] == first

    def test_unknown_keys_are_ignored(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(setlist=[1, 2], files=[], nonsense="x"), path)
        assert db.get_tuit_recording(1837, path)["rec_id"] == 1837

    def test_partial_row_leaves_other_columns_null(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording({"rec_id": 55, "lb_number": 7}, path)
        got = db.get_tuit_recording(55, path)
        assert got["lb_number"] == 7
        assert got["venue"] is None

    def test_missing_rec_id_raises(self, dbmod):
        db, path = dbmod
        with pytest.raises(ValueError):
            db.upsert_tuit_recording({"lb_number": 1}, path)

    def test_get_missing_recording_returns_none(self, dbmod):
        db, path = dbmod
        assert db.get_tuit_recording(999999, path) is None


class TestGetTuitRecordings:
    def test_filter_by_lb_and_limit(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(1, lb_number=100, added_at="2026-01-01"), path)
        db.upsert_tuit_recording(_row(2, lb_number=200, added_at="2026-02-01"), path)
        db.upsert_tuit_recording(_row(3, lb_number=200, added_at="2026-03-01"), path)
        assert len(db.get_tuit_recordings(db_path=path)) == 3
        assert len(db.get_tuit_recordings(lb_number=200, db_path=path)) == 2
        assert len(db.get_tuit_recordings(limit=1, db_path=path)) == 1

    def test_ordered_newest_added_first(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_recording(_row(1, added_at="2026-01-01"), path)
        db.upsert_tuit_recording(_row(2, added_at="2026-03-01"), path)
        db.upsert_tuit_recording(_row(3, added_at="2026-02-01"), path)
        assert [r["rec_id"] for r in db.get_tuit_recordings(db_path=path)] == [2, 3, 1]

    def test_empty_table(self, dbmod):
        db, path = dbmod
        assert db.get_tuit_recordings(db_path=path) == []


class TestTuitDownloads:
    def test_add_and_list(self, dbmod):
        db, path = dbmod
        dl_id = db.add_tuit_download(1837, 11637, "/tmp/x.torrent", "downloaded",
                                     db_path=path)
        rows = db.get_tuit_downloads(db_path=path)
        assert len(rows) == 1
        assert rows[0]["id"] == dl_id
        assert rows[0]["status"] == "downloaded"
        assert rows[0]["lb_number"] == 11637
        assert rows[0]["attempted_at"]

    def test_update_status(self, dbmod):
        db, path = dbmod
        dl_id = db.add_tuit_download(1837, 11637, "/tmp/x.torrent", "downloaded",
                                     db_path=path)
        db.update_tuit_download(
            dl_id, {"status": "qbt_added", "qbt_added_at": "2026-08-20T01:00:00Z"},
            db_path=path,
        )
        row = db.get_tuit_downloads(db_path=path)[0]
        assert row["status"] == "qbt_added"
        assert row["qbt_added_at"].startswith("2026-08-20")

    def test_update_with_no_fields_is_a_noop(self, dbmod):
        db, path = dbmod
        dl_id = db.add_tuit_download(1, None, None, "pending", db_path=path)
        db.update_tuit_download(dl_id, {}, db_path=path)
        assert db.get_tuit_downloads(db_path=path)[0]["status"] == "pending"

    def test_filter_by_rec_id(self, dbmod):
        db, path = dbmod
        db.add_tuit_download(1, None, None, "pending", db_path=path)
        db.add_tuit_download(2, None, None, "pending", db_path=path)
        assert len(db.get_tuit_downloads(rec_id=2, db_path=path)) == 1

    def test_failure_row_records_reason(self, dbmod):
        db, path = dbmod
        db.add_tuit_download(1, 707, None, "no_local_files",
                             error="no collection folder linked", db_path=path)
        row = db.get_tuit_downloads(db_path=path)[0]
        assert row["status"] == "no_local_files"
        assert "no collection folder" in row["error"]

    def test_seed_folder_is_persisted(self, dbmod):
        db, path = dbmod
        db.add_tuit_download(1, 707, "/t/a.torrent", "downloaded",
                             seed_folder="/music/LB-00707", db_path=path)
        assert db.get_tuit_downloads(db_path=path)[0]["seed_folder"] == "/music/LB-00707"


class TestIsSeedableToTracker:
    def _set_status(self, db, path, lb: int, status: str) -> None:
        with db.get_connection(path) as conn:
            conn.execute("INSERT OR IGNORE INTO entries(lb_number, status) VALUES(?,?)",
                         (lb, "ok"))
            conn.execute(
                "INSERT INTO lb_master(lb_number, lb_status) VALUES(?,?)"
                " ON CONFLICT(lb_number) DO UPDATE SET lb_status=excluded.lb_status",
                (lb, status))
            conn.commit()

    def test_public_is_allowed(self, dbmod):
        db, path = dbmod
        self._set_status(db, path, 707, "public")
        assert db.is_seedable_to_tracker(707, path) == (True, None)

    @pytest.mark.parametrize("status,reason", [
        ("private", "lb_private"),
        ("missing", "lb_missing"),
        ("nonexistent", "lb_nonexistent"),
    ])
    def test_non_public_is_blocked(self, dbmod, status, reason):
        db, path = dbmod
        self._set_status(db, path, 707, status)
        assert db.is_seedable_to_tracker(707, path) == (False, reason)

    def test_unknown_lb_is_blocked(self, dbmod):
        db, path = dbmod
        assert db.is_seedable_to_tracker(424242, path) == (False, "status_unknown")


class TestGetFoldersForLb:
    def test_prefers_my_collection_then_folder_lb_link(self, dbmod):
        db, path = dbmod
        with db.get_connection(path) as conn:
            conn.execute("INSERT INTO entries(lb_number, status) VALUES(?,?)",
                         (707, "ok"))
            conn.execute(
                "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                " VALUES(?,?,?)", (707, "f", "/music/LB-00707"))
            conn.execute(
                "INSERT INTO folder_lb_link(folder_path, lb_number, linked_at)"
                " VALUES(?,?,?)", ("/downloads/LB-00707", 707, "2026-01-01"))
            conn.commit()
        assert db.get_folders_for_lb(707, path) == [
            "/music/LB-00707", "/downloads/LB-00707",
        ]

    def test_deduplicates_paths(self, dbmod):
        db, path = dbmod
        with db.get_connection(path) as conn:
            conn.execute("INSERT INTO entries(lb_number, status) VALUES(?,?)",
                         (707, "ok"))
            conn.execute(
                "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                " VALUES(?,?,?)", (707, "f", "/music/LB-00707"))
            conn.execute(
                "INSERT INTO folder_lb_link(folder_path, lb_number, linked_at)"
                " VALUES(?,?,?)", ("/music/LB-00707", 707, "2026-01-01"))
            conn.commit()
        assert db.get_folders_for_lb(707, path) == ["/music/LB-00707"]

    def test_blank_disk_path_is_skipped(self, dbmod):
        db, path = dbmod
        with db.get_connection(path) as conn:
            conn.execute("INSERT INTO entries(lb_number, status) VALUES(?,?)",
                         (707, "ok"))
            conn.execute(
                "INSERT INTO my_collection(lb_number, folder_name, disk_path)"
                " VALUES(?,?,?)", (707, "f", ""))
            conn.commit()
        assert db.get_folders_for_lb(707, path) == []

    def test_unknown_lb_returns_empty(self, dbmod):
        db, path = dbmod
        assert db.get_folders_for_lb(424242, path) == []


class TestTuitShows:
    """tuit_shows is TUIT's concert spine, keyed by (date_str, venue)."""

    def test_insert_and_read_back(self, dbmod):
        db, path = dbmod
        rows = [
            {"date_str": "1993-02-13", "venue": "Hammersmith Apollo",
             "location": "London, England", "tour": "Never Ending Tour 1993",
             "rec_id": 2589, "circulating": True, "in_collection": True,
             "has_sbd": True, "has_aud": True, "seeders": 10},
            {"date_str": "1993-04-13", "venue": "Jackson Hall",
             "tour": "Never Ending Tour 1993", "show_id": 4273,
             "circulating": False},
        ]
        assert db.upsert_tuit_shows(rows) == 2
        got = db.get_tuit_shows(db_path=path)
        assert [r["date_str"] for r in got] == ["1993-02-13", "1993-04-13"]
        assert got[0]["circulating"] == 1 and got[0]["has_sbd"] == 1
        assert got[1]["circulating"] == 0 and got[1]["show_id"] == 4273

    def test_refresh_updates_in_place(self, dbmod):
        db, path = dbmod
        row = {"date_str": "1993-02-13", "venue": "Hammersmith Apollo",
               "seeders": 10, "circulating": True}
        db.upsert_tuit_shows([row])
        db.upsert_tuit_shows([{**row, "seeders": 12}])
        got = db.get_tuit_shows(db_path=path)
        assert len(got) == 1 and got[0]["seeders"] == 12

    def test_rows_without_a_key_are_skipped(self, dbmod):
        db, path = dbmod
        assert db.upsert_tuit_shows(
            [{"date_str": "1993-02-13", "venue": ""}, {"venue": "X"}]
        ) == 0
        assert db.get_tuit_shows(db_path=path) == []

    def test_filters(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_shows([
            {"date_str": "1993-02-13", "venue": "A", "tour": "NET 1993",
             "circulating": True},
            {"date_str": "1994-02-13", "venue": "B", "tour": "NET 1994",
             "circulating": False},
        ])
        assert len(db.get_tuit_shows(tour="NET 1993", db_path=path)) == 1
        assert len(db.get_tuit_shows(circulating=False, db_path=path)) == 1
        assert len(db.get_tuit_shows(date_str="1994-02-13", db_path=path)) == 1


class TestTuitVenues:
    """tuit_venues is keyed by (venue, city, country) — names repeat."""

    def test_insert_and_order_by_show_count(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_venues([
            {"venue": "Spektrum", "city": "Oslo", "country": "Norway",
             "year_first": 1995, "year_last": 2022, "n_shows": 13},
            {"venue": "Beacon Theatre", "city": "New York, New York",
             "country": "United States", "n_shows": 46},
        ])
        got = db.get_tuit_venues(db_path=path)
        assert [r["venue"] for r in got] == ["Beacon Theatre", "Spektrum"]

    def test_same_name_in_two_cities_is_two_rows(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_venues([
            {"venue": "Palasport", "city": "Turin", "country": "Italy"},
            {"venue": "Palasport", "city": "Genoa", "country": "Italy"},
        ])
        assert len(db.get_tuit_venues(venue="Palasport", db_path=path)) == 2

    def test_missing_city_is_normalised_so_the_key_fires(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_venues([{"venue": "Unknown Hall", "n_shows": 1}])
        db.upsert_tuit_venues([{"venue": "Unknown Hall", "n_shows": 2}])
        got = db.get_tuit_venues(venue="Unknown Hall", db_path=path)
        assert len(got) == 1 and got[0]["n_shows"] == 2


class TestVenueBackfill:
    """The /venue register drops rows; tuit_shows is complete by construction."""

    def test_a_venue_only_in_shows_is_recovered(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_shows([
            {"date_str": "1995-06-01", "venue": "Adler Theatre",
             "location": "Davenport, IA, United States"},
            {"date_str": "2001-06-01", "venue": "Adler Theatre · Evening",
             "location": "Davenport, IA, United States"},
        ])
        assert db.backfill_tuit_venues_from_shows(path) == 1
        got = db.get_tuit_venues(venue="Adler Theatre", db_path=path)
        assert len(got) == 1
        assert (got[0]["city"], got[0]["country"]) == ("Davenport, IA",
                                                       "United States")
        assert (got[0]["year_first"], got[0]["year_last"]) == (1995, 2001)
        assert got[0]["n_shows"] == 2
        assert got[0]["source"] == "shows"

    def test_a_venue_already_in_the_register_is_left_alone(self, dbmod):
        db, path = dbmod
        db.upsert_tuit_venues([
            {"venue": "Beacon Theatre", "city": "New York, New York",
             "country": "United States", "n_shows": 46},
        ])
        db.upsert_tuit_shows([{"date_str": "1993-01-01",
                               "venue": "Beacon Theatre",
                               "location": "New York, USA"}])
        assert db.backfill_tuit_venues_from_shows(path) == 0
        got = db.get_tuit_venues(venue="Beacon Theatre", db_path=path)
        assert len(got) == 1 and got[0]["n_shows"] == 46
