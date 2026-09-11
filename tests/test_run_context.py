"""Tests for backend.dossier_fields run_context (D-07) and rotation_rank (D-04), C20.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest


@pytest.fixture
def conn():
    """Yield a connection to a throwaway database with the full schema."""
    tmp_dir = tempfile.mkdtemp(prefix="lb_run_context_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    c = db.get_connection(db_path)
    with c:
        c.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield c
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _concert(c, event_id, date_str, venue, city, tour, songs, rotation=None):
    """One concert event, its song_performances, and optionally Olof's rotation stat."""
    new, pct = rotation if rotation else (None, None)
    c.execute(
        "INSERT INTO olof_events (event_id, source, page_filename, event_type, date_str, venue,"
        " city, tour_name, rotation_new, rotation_pct, raw_text)"
        " VALUES (?, 'dsn', 'test.htm', 'concert', ?, ?, ?, ?, ?, ?, '')",
        (event_id, date_str, venue, city, tour, new, pct),
    )
    for i, title in enumerate(songs, start=1):
        c.execute(
            "INSERT INTO song_performances (event_id, position, song_norm, song_canonical,"
            " concert_date_iso, event_type) VALUES (?, ?, ?, ?, ?, 'concert')",
            (event_id, i, title.lower(), title, date_str),
        )


def _open_ro1(c, event_id):
    c.execute(
        "INSERT INTO qc_findings (rule_id, entity_kind, entity_key, severity, detail,"
        " evidence_json, evidence_hash, first_seen, last_seen, status)"
        " VALUES ('R-O1', 'olof_event', ?, 'error', '', '{}', 'h', '2026-01-01', '2026-01-01',"
        " 'open')",
        (str(event_id),),
    )


def _run_of_three(c, last_songs=("E", "F"), last_rotation=(2, 100)):
    """Tour T: W (A, B), then three nights at V, then one more night at W.

    Olof's rotation stats match the recompute unless a test overrides them.
    """
    _concert(c, 10, "2010-01-01", "W", "Osaka", "T", ["A", "B"])
    _concert(c, 11, "2010-01-02", "V", "Tokyo", "T", ["A", "C"], rotation=(1, 50))
    _concert(c, 12, "2010-01-03", "V", "Tokyo", "T", ["C", "D"], rotation=(1, 50))
    _concert(c, 13, "2010-01-04", "V", "Tokyo", "T", list(last_songs), rotation=last_rotation)
    _concert(c, 14, "2010-01-06", "W", "Seoul", "T", ["A"])


class TestRunContext:
    def test_tour_and_venue_run(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _run_of_three(conn)
        rc = run_context(conn, 13)
        assert {k: rc["tour"][k] for k in ("name", "position", "size", "is_first", "is_last")} == {
            "name": "T", "position": 4, "size": 5, "is_first": False, "is_last": False,
        }
        run = rc["venue_run"]
        assert (run["venue"], run["position"], run["size"]) == ("V", 3, 3)
        assert run["event_ids"] == [11, 12, 13] and run["claims_ok"]

    def test_run_breaks_on_another_concert_between(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _concert(conn, 1, "2010-01-01", "V", "Tokyo", "T", ["A"])
            _concert(conn, 2, "2010-01-02", "W", "Tokyo", "T", ["A"])
            _concert(conn, 3, "2010-01-03", "V", "Tokyo", "T", ["A"])
        assert run_context(conn, 3)["venue_run"]["size"] == 1

    def test_claims_guard_open_ro1_or_missing_songs(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _run_of_three(conn)
            _open_ro1(conn, 12)
        rc = run_context(conn, 13)
        assert not rc["venue_run"]["claims_ok"] and not rc["tour"]["claims_ok"]

    def test_recording_sessions_bucket_is_not_a_tour(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _concert(conn, 1, "1965-01-01", "V", "London", "1965 Recording sessions & concerts",
                     ["A"])
        assert run_context(conn, 1)["tour"] is None

    def test_city_history_rows_sum_and_exact_venues(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _concert(conn, 1, "2001-03-01", "Zepp Tokyo", "Tokyo", "T1", ["A"])
            _concert(conn, 2, "2001-03-02", "Zepp Tokyo", "Tokyo", "T1", ["A"])
            _concert(conn, 3, "2014-04-01", "Zepp DiverCity", "Tokyo", "T2", ["A"])
            _concert(conn, 4, "2014-04-05", "Zepp Osaka", "Osaka", "T2", ["A"])
        ch = run_context(conn, 3)["city_history"]
        assert (ch["city"], ch["basis"], ch["total"], ch["invariant_ok"]) == (
            "Tokyo", "olof", 3, True)
        assert ch["rows"] == [
            {"year": "2001", "venue": "Zepp Tokyo", "count": 2},
            {"year": "2014", "venue": "Zepp DiverCity", "count": 1},
        ]

    def test_city_history_prefers_setlistfm_city(self, conn):
        from backend.dossier_fields import run_context
        with conn:
            _concert(conn, 1, "1975-12-08", "Madison Square Garden", "New York City", "T", ["A"])
            _concert(conn, 2, "1978-09-29", "Madison Square Garden", "New York", "T", ["A"])
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, city, country)"
                " VALUES ('s1', '1975-12-08', 'New York', 'United States')"
            )
        ch = run_context(conn, 1)["city_history"]
        assert (ch["city"], ch["basis"], ch["total"]) == ("New York", "setlistfm", 2)

    def test_non_concert_has_no_context(self, conn):
        from backend.dossier_fields import run_context
        assert run_context(conn, 999) == {
            "event_id": 999, "tour": None, "venue_run": None, "city_history": None,
        }


class TestRotationRank:
    def test_verified_rank_one_gets_superlative_with_scope(self, conn):
        from backend.dossier_fields import rotation_rank, run_context
        with conn:
            _run_of_three(conn)
        rr = rotation_rank(conn, 13, run_context(conn, 13)["venue_run"])
        assert (rr["pct"], rr["rank_in_run"], rr["tie"], rr["superlative_ok"]) == (
            100, 1, False, True)
        assert rr["scope"] == "of the 3-night V run" and rr["run_median_pct"] == 50

    def test_tie_produces_no_superlative(self, conn):
        from backend.dossier_fields import rotation_rank, run_context
        with conn:
            _run_of_three(conn, last_songs=("C", "E"), last_rotation=(1, 50))
        rr = rotation_rank(conn, 13, run_context(conn, 13)["venue_run"])
        assert rr["rank_in_run"] == 1 and rr["tie"] and not rr["superlative_ok"]

    def test_disputed_sibling_blocks_superlative(self, conn):
        from backend.dossier_fields import rotation_rank, run_context
        with conn:
            _run_of_three(conn)
            conn.execute("UPDATE olof_events SET rotation_new = 2 WHERE event_id = 12")
        rr = rotation_rank(conn, 13, run_context(conn, 13)["venue_run"])
        sib = {s["event_id"]: s for s in rr["siblings"]}
        assert sib[12]["disputed"] and not rr["superlative_ok"]

    def test_no_stated_stat_returns_none(self, conn):
        from backend.dossier_fields import rotation_rank, run_context
        with conn:
            _run_of_three(conn)
        assert rotation_rank(conn, 10, run_context(conn, 10)["venue_run"]) is None
