"""Tests for backend.venue_xref — the TUIT <-> Olof venue cross-reference (TODO-338).

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def xdb():
    """Yield (venue_xref module, conn) bound to a throwaway database."""
    tmp_dir = tempfile.mkdtemp(prefix="lbvx_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    saved = _paths.DATA_DIR
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend import venue_xref
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield venue_xref, conn
    finally:
        db.close_connection(db_path)
        _paths.DATA_DIR = saved
        shutil.rmtree(tmp_dir, ignore_errors=True)


_EID = iter(range(1000, 9999))


def _olof(conn, date, venue, city, event_type="concert"):
    conn.execute(
        "INSERT INTO olof_events (event_id, source, page_filename, event_type, date_str,"
        " venue, city) VALUES (?, 'dsn', 'test.htm', ?, ?, ?, ?)",
        (next(_EID), event_type, date, venue, city))


def _tuit(conn, date, venue, location):
    conn.execute("INSERT INTO tuit_shows (date_str, venue, location) VALUES (?, ?, ?)",
                 (date, venue, location))


def test_shared_dates_link_pairwise_and_count(xdb):
    vx, conn = xdb
    with conn:
        for d in ("1963-12-14", "1964-03-01"):
            _olof(conn, d, "Lisner Auditorium", "Washington")
            _tuit(conn, d, "Lisner Auditorium, George Washington University", "Washington, DC")
    rows, stats = vx.build(conn)
    assert stats["date_links"] == 1
    (row,) = rows
    assert (row.method, row.n_dates, row.relation) == ("date", 2, "tuit_longer")
    assert row.olof_venue == "Lisner Auditorium"


def test_name_rule_links_only_a_unique_candidate(xdb):
    vx, conn = xdb
    with conn:
        _olof(conn, "1990-01-01", "Civic Auditorium", "Portland")
        _tuit(conn, "1991-05-05", "Portland Civic Auditorium", "Portland, Oregon")
        # Two Olof candidates in one city -> ambiguous, left unlinked.
        _olof(conn, "1990-02-01", "Arena", "Springfield")
        _olof(conn, "1990-02-02", "Arena North", "Springfield")
        _tuit(conn, "1991-06-06", "Arena", "Springfield")
    rows, stats = vx.build(conn)
    assert [(r.tuit_venue, r.olof_venue, r.method) for r in rows] == [
        ("Portland Civic Auditorium", "Civic Auditorium", "name")]
    assert stats["name_ambiguous"] == 1


def test_no_transitive_merge(xdb):
    vx, conn = xdb
    with conn:
        # Chapter Hall shares a date with Carnegie Hall once; Carnegie Hall's own
        # TUIT entity must not inherit a link to Chapter Hall through it.
        _olof(conn, "1961-11-04", "Carnegie Chapter Hall", "New York")
        _tuit(conn, "1961-11-04", "Carnegie Hall", "New York, New York")
        _olof(conn, "1963-10-26", "Carnegie Hall", "New York")
        _tuit(conn, "1963-10-26", "Carnegie Hall", "New York, New York")
    rows, _ = vx.build(conn)
    pairs = sorted((r.tuit_venue, r.olof_venue, r.n_dates) for r in rows)
    assert pairs == [("Carnegie Hall", "Carnegie Chapter Hall", 1),
                     ("Carnegie Hall", "Carnegie Hall", 1)]


def test_refresh_rewrites_the_table(xdb):
    vx, conn = xdb
    with conn:
        _olof(conn, "1963-12-14", "Lisner Auditorium", "Washington")
        _tuit(conn, "1963-12-14", "Lisner Auditorium", "Washington, DC")
    assert vx.refresh(conn)["written"] == 1
    assert vx.refresh(conn)["written"] == 1  # idempotent: rebuilt, not appended


def test_tuit_longer_venue(xdb):
    vx, conn = xdb
    with conn:
        _tuit(conn, "1963-12-14", "Lisner Auditorium, George Washington University · Evening",
              "Washington, DC")
        _tuit(conn, "1965-01-01", "Lisner Auditorium", "Washington, DC")
        _tuit(conn, "1966-01-01", "Hall A", "X")
        _tuit(conn, "1966-01-01", "Hall B", "X")
    longer = vx.tuit_longer_venue
    assert longer(conn, "1963-12-14", "Lisner Auditorium") == \
        "Lisner Auditorium, George Washington University"
    assert longer(conn, "1965-01-01", "Lisner Auditorium") is None  # equal, not longer
    assert longer(conn, "1966-01-01", "Hall") is None  # two TUIT venues on the date
    assert longer(conn, "1999-01-01", "Anywhere") is None
