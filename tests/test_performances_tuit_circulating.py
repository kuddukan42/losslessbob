"""TODO-338 part 4: get_performances() carries tuitCirculating (tracker availability)."""
from __future__ import annotations

import shutil

from tests.test_performances_uncirculated import (
    _insert_olof_event,
    _make_db,
    _seed_entry,
    db,
)


def _tuit(conn, date, venue, circ):
    conn.execute(
        "INSERT INTO tuit_shows (date_str, venue, circulating) VALUES (?, ?, ?)",
        (date, venue, circ),
    )
    conn.commit()


def test_flag_present_true_false_and_absent():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_entry(conn, 1, "6/1/00")      # TUIT circulating
        _seed_entry(conn, 2, "6/2/00")      # TUIT lists it uncirculated, LB holds a tape
        _seed_entry(conn, 3, "6/3/00")      # TUIT has no row
        _tuit(conn, "2000-06-01", "A", 0)
        _tuit(conn, "2000-06-01", "B", 1)   # any circulating row wins
        _tuit(conn, "2000-06-02", "A", 0)
        _insert_olof_event(conn, 9, "1975-12-04")
        _tuit(conn, "1975-12-04", "Massey Hall", 0)

        perfs = {p["id"]: p for p in db.get_performances(db_path=db_path)}
        assert perfs["2000-06-01"]["tuitCirculating"] is True
        assert perfs["2000-06-02"]["tuitCirculating"] is False
        assert len(perfs["2000-06-02"]["recordings"]) == 1   # tape exists regardless
        assert "tuitCirculating" not in perfs["2000-06-03"]
        assert perfs["1975-12-04"]["tuitCirculating"] is False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
