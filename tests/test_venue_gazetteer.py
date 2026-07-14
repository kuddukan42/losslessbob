"""Tests for the venue-level gazetteer seeding (backend/venue_gazetteer.py, TODO-223).

Covers the first slice: normalization keys and ``seed_venues()`` enumerating
distinct concert venues into ``venue_geocoded`` unresolved, richest-source-wins
dedup, re-run idempotency, and never disturbing resolved / manual rows.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend import venue_gazetteer as vg

# ═══════════════════════════════════════════════════════════════════════════════
# 1. normalization
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalize:
    @pytest.mark.parametrize("raw, expected", [
        ("Fox Theater", "fox theater"),
        ("  Massey   Hall  ", "massey hall"),
        ("St. James Theatre", "st james theatre"),
        ("O2 Arena", "o2 arena"),
        ("Café de Paris", "café de paris"),   # unicode letters preserved
        ("", ""),
        ("---", ""),
        (None, ""),
    ])
    def test_normalize_key_form(self, raw, expected):
        assert vg._normalize(raw) == expected

    def test_theater_and_theatre_stay_distinct(self):
        # Conservative: we do NOT canonicalize spelling variants.
        assert vg._norm_venue("Fox Theater") != vg._norm_venue("Fox Theatre")

    def test_city_key_drops_embedded_state_country(self):
        # City-string variants across sources must collapse to one key.
        assert vg._norm_city("Birmingham") == vg._norm_city("Birmingham, AL") \
            == vg._norm_city("Birmingham, Alabama") == "birmingham"

    def test_venue_key_keeps_commas(self):
        # Venue names can legitimately contain commas — do not truncate them.
        assert vg._norm_venue("Tucson Music Hall, Tucson Convention Center") \
            == "tucson music hall tucson convention center"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. seed_venues()
# ═══════════════════════════════════════════════════════════════════════════════

def _make_db(tmp_path, monkeypatch):
    """Build a temp DB with the venue_geocoded schema + source tables and point
    venue_gazetteer's connection helpers at it."""
    db_file = str(tmp_path / "t.db")

    # venue_gazetteer calls init_db()+get_connection(); stub both to our file so
    # we control the schema without the full app init.
    def _conn(_db_path=None):
        c = sqlite3.connect(db_file)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(vg, "init_db", lambda _db_path=None: None)
    monkeypatch.setattr(vg, "get_connection", _conn)

    c = _conn()
    c.executescript(
        """
        CREATE TABLE venue_geocoded (
            venue_norm TEXT NOT NULL, city_norm TEXT NOT NULL,
            venue TEXT, city TEXT, region TEXT, country TEXT,
            lat REAL, lon REAL, source TEXT NOT NULL, confidence TEXT,
            manual_override INTEGER NOT NULL DEFAULT 0, note TEXT,
            geocoded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (venue_norm, city_norm)
        );
        CREATE TABLE olof_events (
            event_id INTEGER, source TEXT, event_type TEXT,
            venue TEXT, city TEXT, region TEXT, country TEXT
        );
        CREATE TABLE setlistfm_shows (
            setlistfm_id TEXT, venue_name TEXT, city TEXT,
            city_state TEXT, country TEXT
        );
        CREATE TABLE bobdylan_shows (
            bobdylan_url TEXT, venue TEXT, location TEXT
        );
        """
    )
    return db_file, c


def test_seed_enumerates_and_dedups(tmp_path, monkeypatch):
    _db, c = _make_db(tmp_path, monkeypatch)
    c.executemany(
        "INSERT INTO olof_events (event_type, venue, city, region, country) VALUES (?,?,?,?,?)",
        [
            ("concert", "Fox Theater", "Oakland", "California", ""),
            ("concert", "Fox Theater", "Oakland", "California", ""),   # dup key
            ("interview", "Radio Studio", "New York", "New York", ""),  # non-concert
            ("concert", "", "Nowhere", "", ""),                          # no venue -> skip
        ],
    )
    c.execute(
        "INSERT INTO setlistfm_shows (venue_name, city, city_state, country) VALUES (?,?,?,?)",
        ("Massey Hall", "Toronto", "ON", "Canada"),
    )
    c.execute("INSERT INTO bobdylan_shows (venue, location) VALUES (?,?)",
              ("Beacon Theatre", "New York"))
    c.commit()

    summary = vg.seed_venues()

    # per_source counts rows returned by each (already-filtered) SELECT: the
    # non-concert interview and the empty-venue concert are filtered in SQL, so
    # olof_events yields just the 2 Fox Theater concert rows.
    assert summary["per_source"] == {
        "olof_events": 2, "setlistfm_shows": 1, "bobdylan_shows": 1,
    }
    # Fox Theater dedups to one; interview + empty-venue rows never appear.
    assert summary["distinct_candidates"] == 3
    assert summary["inserted"] == 3
    assert summary["total_rows"] == 3

    rows = {r["venue_norm"]: r for r in c.execute("SELECT * FROM venue_geocoded")}
    assert set(rows) == {"fox theater", "massey hall", "beacon theatre"}
    fox = rows["fox theater"]
    assert (fox["source"], fox["lat"], fox["lon"], fox["confidence"]) == ("seeded", None, None, None)
    assert fox["region"] == "California"


def test_seed_is_idempotent_and_preserves_resolved_rows(tmp_path, monkeypatch):
    _db, c = _make_db(tmp_path, monkeypatch)
    c.execute(
        "INSERT INTO olof_events (event_type, venue, city, region, country) VALUES (?,?,?,?,?)",
        ("concert", "Fox Theater", "Oakland", "California", ""),
    )
    # A pre-existing manually-fixed row for the same venue must survive re-seed.
    c.execute(
        """INSERT INTO venue_geocoded
               (venue_norm, city_norm, venue, city, lat, lon, source,
                confidence, manual_override)
           VALUES ('fox theater','oakland','Fox Theater','Oakland',
                   37.8080, -122.2680, 'manual', 'high', 1)""",
    )
    c.commit()

    first = vg.seed_venues()
    assert first["inserted"] == 0            # already present
    assert first["already_present"] == 1

    second = vg.seed_venues()
    assert second["total_rows"] == 1         # no growth on re-run

    fox = c.execute("SELECT * FROM venue_geocoded WHERE venue_norm='fox theater'").fetchone()
    assert (fox["source"], fox["manual_override"], fox["lat"]) == ("manual", 1, 37.8080)


def test_seed_tolerates_missing_optional_source_tables(tmp_path, monkeypatch):
    _db, c = _make_db(tmp_path, monkeypatch)
    c.execute("DROP TABLE setlistfm_shows")
    c.execute("DROP TABLE bobdylan_shows")
    c.execute(
        "INSERT INTO olof_events (event_type, venue, city, region, country) VALUES (?,?,?,?,?)",
        ("concert", "Fox Theater", "Oakland", "California", ""),
    )
    c.commit()

    summary = vg.seed_venues()
    assert summary["per_source"]["setlistfm_shows"] == 0
    assert summary["per_source"]["bobdylan_shows"] == 0
    assert summary["inserted"] == 1
