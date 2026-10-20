"""TODO-370: GET /api/library/performances response pin + lazy bloom build.

The route itself was never slow (~0.3s on the live DB); it measured ~6s because
every init_db() call spawned a background bloom rebuild that holds the GIL for
~13s on a 708k-row checksums table, and create_app() calls init_db() twice.
The pin below freezes the route's exact JSON on a fixture DB so any later
refactor of get_performances() is caught; the bloom tests pin the lazy,
deduplicated rebuild that replaced the eager one.
"""
from __future__ import annotations

import shutil

from tests.test_library_picks_api import _AppClient, _seed_curated_list
from tests.test_performances_tuit_circulating import _tuit
from tests.test_performances_uncirculated import (
    _insert_olof_event,
    _make_db,
    _seed_entry,
    db,
)


def _seed(conn) -> None:
    _seed_entry(conn, 100, "6/1/00", location="Munich", rating="A")
    _seed_entry(conn, 101, "6/1/00", location="Munich, West Germany", rating="C")
    _seed_entry(conn, 102, "xx/xx/86", location="Somewhere")
    _seed_entry(conn, 103, "7/4/86", location="Stadium", lb_category="unknown")
    _seed_entry(conn, 104, "7/5/86", location="", lb_category="unknown")
    _seed_entry(conn, 105, "8/1/99", location="Radio", lb_category="radio")
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status) VALUES (100, 'public'), (101, 'private')"
    )
    conn.execute(
        "UPDATE entries SET source_type='Soundboard' WHERE lb_number=101"
    )
    conn.commit()
    conn.execute(
        "INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)"
        " VALUES ('u1', '2000-06-01', 'Olympiahalle', 'Munich, Germany')"
    )
    conn.executemany(
        "INSERT INTO bobdylan_setlist (bobdylan_url, position, track_name) VALUES ('u1', ?, ?)",
        [(1, "Song A"), (2, "Song B")],
    )
    conn.execute("INSERT INTO bootleg_titles (lb_number, title) VALUES (100, 'Munich Night')")
    conn.commit()
    _seed_curated_list(conn, "carbonbit", [100])
    _tuit(conn, "2000-06-01", "Munich", 1)
    _insert_olof_event(conn, 9, "1975-12-04", venue="Massey Hall", city="Toronto",
                       tour_name="Rolling Thunder")


EXPECTED: list[dict] = [   {   'city': 'Munich',
        'date': '2000-06-01',
        'disp': 'Jun 1, 2000',
        'dow': 'Thu',
        'id': '2000-06-01',
        'recordings': [   {   'curated': ['carbonbit'],
                              'lb': 'LB-00100',
                              'lbNumber': 100,
                              'rating': 'A',
                              'src': None,
                              'status': 'Public'},
                          {   'lb': 'LB-00101',
                              'lbNumber': 101,
                              'rating': 'C',
                              'src': 'Soundboard',
                              'status': 'Private'}],
        'setlist': '2000-06-01',
        'status': 'Public',
        'title': 'Munich Night',
        'tracks': 2,
        'tuitCirculating': True,
        'venue': 'Olympiahalle',
        'year': 2000},
    {   'city': 'Somewhere',
        'date': 'xx/xx/86',
        'disp': 'xx/xx/86',
        'id': 'xx/xx/86::Somewhere',
        'recordings': [   {   'lb': 'LB-00102',
                              'lbNumber': 102,
                              'rating': '',
                              'src': None,
                              'status': 'Missing'}],
        'status': 'Missing',
        'venue': None,
        'year': 1986},
    {   'city': 'Stadium',
        'confirmed': False,
        'date': '1986-07-04',
        'disp': 'Jul 4, 1986',
        'dow': 'Fri',
        'id': '1986-07-04',
        'recordings': [   {   'lb': 'LB-00103',
                              'lbNumber': 103,
                              'rating': '',
                              'src': None,
                              'status': 'Missing'}],
        'status': 'Missing',
        'venue': None,
        'year': 1986},
    {   'city': 'Toronto',
        'coverage': 'uncirculated',
        'date': '1975-12-04',
        'disp': 'Dec 4, 1975',
        'dow': 'Thu',
        'id': '1975-12-04',
        'recordings': [],
        'status': 'Missing',
        'tour': 'Rolling Thunder',
        'venue': 'Massey Hall',
        'year': 1975}]


def test_route_response_is_pinned():
    db_path, tmp_dir = _make_db()
    try:
        _seed(db.get_connection(db_path))
        with _AppClient(db_path) as client:
            resp = client.get("/api/library/performances")
        assert resp.status_code == 200
        assert resp.get_json() == EXPECTED
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
