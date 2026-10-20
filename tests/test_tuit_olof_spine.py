"""tools/tuit_olof_spine.py — TUIT show spine vs olof_events (TODO-338) on a fixture DB."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tuit_olof_spine as sp  # noqa: E402

_SCHEMA = """
CREATE TABLE tuit_shows (id INTEGER PRIMARY KEY AUTOINCREMENT, date_str TEXT, venue TEXT,
    location TEXT, tour TEXT, circulating INTEGER DEFAULT 0, last_seen_at TEXT);
CREATE TABLE tuit_venues (id INTEGER PRIMARY KEY AUTOINCREMENT, venue TEXT, city TEXT,
    country TEXT, n_shows INTEGER);
CREATE TABLE olof_events (event_id INTEGER PRIMARY KEY, event_type TEXT, date_str TEXT,
    date_raw TEXT DEFAULT '', venue TEXT, city TEXT, region TEXT DEFAULT '',
    country TEXT DEFAULT '', source TEXT DEFAULT 'dsn');
CREATE TABLE setlistfm_shows (setlistfm_id TEXT, date_str TEXT, city TEXT,
    city_lat REAL, city_lon REAL);
CREATE TABLE bobdylan_shows (bobdylan_url TEXT, date_str TEXT);
CREATE TABLE venue_geocoded (venue_norm TEXT, city_norm TEXT, city TEXT, lat REAL, lon REAL);
"""

_CRAWL = "2026-09-07 21:38:51"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def _tuit(conn, date, venue, location, circ=1):
    conn.execute("INSERT INTO tuit_shows (date_str, venue, location, circulating, last_seen_at) "
                 "VALUES (?,?,?,?,?)", (date, venue, location, circ, _CRAWL))


def _olof(conn, eid, date, venue, city, etype="concert", raw=""):
    conn.execute("INSERT INTO olof_events (event_id, event_type, date_str, date_raw, venue, city) "
                 "VALUES (?,?,?,?,?,?)", (eid, etype, date, raw or date, venue, city))


# --- normalisation ---------------------------------------------------------

def test_norm_venue_strips_session_suffix_and_folds_spelling():
    assert sp.norm_venue("Civic Center · Afternoon") == "civic center"
    assert sp.norm_venue("The Palace Theatre") == "palace theater"
    assert sp.norm_venue("Procter & Gamble Hall") == "procter gamble hall"
    assert sp.norm_venue("Universitätspark") == "universitatspark"


def test_norm_city_first_segment_and_alias():
    assert sp.norm_city("New York, New York") == "new york"
    assert sp.norm_city("New York City") == "new york"
    assert sp.norm_city("St. Louis, Missouri") == "saint louis"


@pytest.mark.parametrize("a,b,want", [
    ("Lisner Auditorium, George Washington University", "Lisner Auditorium", True),
    ("St. Jacobshalle", "St. Jakobshalle", True),
    ("Salzburgarena", "Salzburg Arena", True),
    ("Fox Warfield Theatre", "Fox Warfield Theater", True),
    ("Beacon Theatre", "Madison Square Garden", False),
    # Known false positive: two rooms in one building. Documented, not fixed.
    ("Carnegie Chapter Hall", "Carnegie Hall", True),
])
def test_fuzzy_name(a, b, want):
    assert sp.fuzzy_name(sp.norm_venue(a), sp.norm_venue(b)) is want


def test_relation():
    assert sp.relation("lisner auditorium george washington university",
                       "lisner auditorium") == "tuit_longer"
    assert sp.relation("filene center", "filene center") == "equal"
    assert sp.relation("mullins center", "university massachusetts mullins center") == \
        "olof_longer"
    assert sp.relation("ahoy", "sportpaleis") == "different"


def test_haversine():
    assert sp.haversine_km((0.0, 0.0), (0.0, 1.0)) == pytest.approx(111.2, abs=0.5)


# --- part 1 ----------------------------------------------------------------

def test_tuit_only_classes():
    c = _db()
    c.execute("INSERT INTO setlistfm_shows (date_str, city) VALUES ('2014-11-25', 'Washington')")
    c.execute("INSERT INTO bobdylan_shows (date_str) VALUES ('2014-11-25')")
    _tuit(c, "1986-02-17", "Perth Entertainment Center", "Perth, Australia")
    _olof(c, 1, "1986-02-17", "Perth Entertainment Center", "Perth", etype="other")
    _tuit(c, "1980-06-02", "Civic Center", "Springfield, MA")        # olof says 06-03
    _olof(c, 2, "1980-06-03", "Civic Center", "Springfield")
    _tuit(c, "1987-10-15", "Wembley Arena", "London")                # both have 10-16
    _tuit(c, "1987-10-16", "Wembley Arena", "London")
    _olof(c, 3, "1987-10-16", "Wembley Arena", "London")
    _tuit(c, "1961-09-01", "Gaslight Café", "New York, New York")
    _tuit(c, "2014-11-25", "DAR Constitution Hall", "Washington, D.C.")
    _tuit(c, "2001-01-01", "Nowhere Hall", "Nowhere")
    rows = {r["date"]: r for r in sp.classify_tuit_only(
        sp.load_tuit(c), sp.load_olof(c), *sp.load_other_dates(c))}
    assert rows["1986-02-17"]["class"] == "olof_nonconcert"
    assert rows["1980-06-02"]["class"] == "date_offset"
    assert rows["1987-10-15"]["class"] == "multi_night"
    assert rows["1961-09-01"]["class"] == "circa"
    assert rows["2014-11-25"]["class"] == "corroborated"
    assert "parser gap" in rows["2014-11-25"]["note"]
    assert rows["2001-01-01"]["class"] == "unverified"
    assert "1987-10-16" not in rows


def test_olof_only_classes():
    c = _db()
    c.execute("INSERT INTO bobdylan_shows (date_str) VALUES ('1971-08-01')")
    c.execute("INSERT INTO setlistfm_shows (date_str, city) VALUES ('1980-02-27', 'LA')")
    _tuit(c, "2026-01-01", "Somewhere", "Somewhere")
    _olof(c, 1, "1971-08-01", "Madison Square Garden", "New York City")
    _olof(c, 2, "1980-02-27", "Shrine Auditorium", "Los Angeles")
    _olof(c, 3, "1979-10-08", "Rundown Studios", "Santa Monica")
    _olof(c, 4, "1992-01-18", "Radio City Music Hall", "New York City")
    _olof(c, 5, "2026-10-17", "Spektrum", "Oslo")
    _olof(c, 6, "1965-04-26", "Arrival Area", "London")
    _olof(c, 7, "1963-05-01", "Gerde's", "New York City", raw="circa May 1963")
    _olof(c, 8, "1979-10-08", "Rundown Studios", "Santa Monica")    # same date, one row out
    rows = {r["date"]: r for r in sp.classify_olof_only(
        sp.load_tuit(c), sp.load_olof(c), *sp.load_other_dates(c), "2026-09-07")}
    assert rows["1971-08-01"]["class"] == "corroborated"
    assert rows["1980-02-27"]["class"] == "corroborated_sfm"
    assert rows["1979-10-08"]["class"] == "non_show"
    assert rows["1992-01-18"]["class"] == "unverified"   # 'radio city' is not a radio studio
    assert rows["2026-10-17"]["class"] == "after_crawl"
    assert rows["1965-04-26"]["class"] == "non_show"
    assert rows["1963-05-01"]["class"] == "circa"
    assert len(rows) == 7


# --- part 2 ----------------------------------------------------------------

def _key_fixture() -> sqlite3.Connection:
    c = _db()
    c.execute("INSERT INTO tuit_venues (venue, city, country, n_shows) VALUES "
              "('Beacon Theatre', 'New York, New York', 'United States', 3)")
    # exact on two dates, TUIT-longer on one, and a cross-city pair geo must bridge.
    for i, d in enumerate(("1989-10-10", "1989-10-11")):
        _tuit(c, d, "Beacon Theatre", "New York, New York, United States")
        _olof(c, 10 + i, d, "Beacon Theatre", "New York City")
    _tuit(c, "1963-12-14", "Lisner Auditorium, George Washington University",
          "Washington, District Of Columbia")
    _olof(c, 20, "1963-12-14", "Lisner Auditorium", "Washington")
    _tuit(c, "2013-07-31", "Fiddler's Green Amphitheatre", "Greenwood Village")
    _olof(c, 30, "2013-07-31", "Fiddler's Green Amphitheatre", "Denver")
    for i, d in enumerate(("1993-02-11", "1993-02-12")):           # only crosswalk links
        _tuit(c, d, "Ahoy", "Rotterdam, Netherlands")
        _olof(c, 40 + i, d, "Rotterdam Sportpaleis", "Rotterdam")
    c.execute("INSERT INTO setlistfm_shows (date_str, city, city_lat, city_lon) VALUES "
              "('x', 'Denver', 39.74, -104.99), ('y', 'Greenwood Village', 39.62, -104.95)")
    return c


def test_evaluate_keys_rates():
    c = _key_fixture()
    res = sp.evaluate_keys(sp.load_tuit(c), sp.load_olof(c), sp.load_city_coords(c))
    k = res["keys"]
    assert res["n_pairs"] == 6
    assert k["exact"]["matched"] == 2
    assert k["fuzzy"]["matched"] == 3          # + Lisner containment
    assert k["geo25"]["matched"] == 4          # + Fiddler's Green across Denver/Greenwood
    assert k["geo10"]["matched"] == 3          # 13 km apart: outside 10 km
    # Leave-one-out crosswalk: each Beacon/Ahoy date is predicted from its sibling date.
    assert k["crosswalk"]["matched"] == 4
    assert k["geo25+crosswalk"]["matched"] == 6
    assert res["relation"]["tuit_longer"] == 1


def test_contradicted_link_is_counted():
    c = _db()
    # TUIT says Chapter Hall, olof agrees on that date; TUIT says Carnegie Hall another
    # date and olof agrees — fuzzy still links the cross pair, evidence contradicts it.
    _tuit(c, "1961-11-04", "Carnegie Chapter Hall", "New York, New York")
    _olof(c, 1, "1961-11-04", "Carnegie Chapter Hall", "New York City")
    _tuit(c, "1963-10-26", "Carnegie Hall", "New York, New York")
    _olof(c, 2, "1963-10-26", "Carnegie Hall", "New York City")
    res = sp.evaluate_keys(sp.load_tuit(c), sp.load_olof(c), {})
    assert res["keys"]["exact"]["false"] == 0
    assert res["keys"]["fuzzy"]["false"] == 2


# --- report / CLI ----------------------------------------------------------

def test_write_block_preserves_prose(tmp_path):
    out = tmp_path / "doc.md"
    out.write_text(f"# Title\n\nintro\n\n{sp.GEN_START}\nold\n{sp.GEN_END}\n\n## Tail\n")
    sp.write_block(out, f"{sp.GEN_START}\nnew\n{sp.GEN_END}\n")
    text = out.read_text()
    assert "intro" in text and "## Tail" in text and "new" in text and "old" not in text


def test_main_is_read_only(tmp_path):
    db = tmp_path / "t.db"
    disk = sqlite3.connect(db)
    src = _key_fixture()
    src.commit()
    src.backup(disk)
    disk.close()
    before = db.read_bytes()
    out = tmp_path / "spine.md"
    assert sp.main(["--db", str(db), "--out", str(out)]) == 0
    assert db.read_bytes() == before
    text = out.read_text()
    assert "Part 1a" in text and "geo25+crosswalk" in text
