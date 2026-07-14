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


# ═══════════════════════════════════════════════════════════════════════════════
# 3. resolution ladder
# ═══════════════════════════════════════════════════════════════════════════════

class TestHaversine:
    def test_zero_distance(self):
        assert vg._haversine_km(40.0, -74.0, 40.0, -74.0) == pytest.approx(0.0)

    def test_known_distance(self):
        # NYC <-> LA is ~3936 km.
        d = vg._haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
        assert d == pytest.approx(3936, abs=30)


def _row(**kw):
    base = {"venue": "", "city": "", "region": "", "country": "",
            "venue_norm": "", "city_norm": ""}
    base.update(kw)
    return base


class TestCityAnchor:
    def test_prefers_setlistfm_coord(self, monkeypatch):
        monkeypatch.setattr(vg, "_setlistfm_city_coord", lambda conn, cn: (51.5, -0.1))
        called = []
        monkeypatch.setattr(vg, "_geocode_retry", lambda *a, **k: called.append(1) or {})
        cache = {}
        coord, src = vg._city_anchor(None, _row(city="London", city_norm="london"), cache)
        assert (coord, src) == ((51.5, -0.1), "setlistfm_city")
        assert called == []  # no Nominatim call when setlist.fm has the coord

    def test_falls_back_to_city_geocode_and_caches(self, monkeypatch):
        monkeypatch.setattr(vg, "_setlistfm_city_coord", lambda conn, cn: None)
        calls = []

        def fake_geo(query, viewbox=None, bounded=False):
            calls.append(query)
            return {"lat": 41.0, "lon": -73.0, "source": "nominatim", "confidence": "high"}

        monkeypatch.setattr(vg, "_geocode_retry", fake_geo)
        cache = {}
        row = _row(city="Oakland", region="California", city_norm="oakland")
        coord, src = vg._city_anchor(None, row, cache)
        assert (coord, src) == ((41.0, -73.0), "city_geocode")
        # Second venue in the same city hits the cache — no second geocode.
        vg._city_anchor(None, _row(city="Oakland", city_norm="oakland"), cache)
        assert calls == ["Oakland, California"]

    def test_empty_city_cannot_anchor(self, monkeypatch):
        monkeypatch.setattr(vg, "_setlistfm_city_coord", lambda conn, cn: None)
        monkeypatch.setattr(vg, "_geocode_retry", lambda *a, **k: pytest.fail("no geocode"))
        coord, src = vg._city_anchor(None, _row(city="", city_norm=""), {})
        assert (coord, src) == (None, "")


class TestResolveOne:
    def _anchor(self, monkeypatch, coord=(40.0, -74.0), src="city_geocode"):
        monkeypatch.setattr(vg, "_city_anchor", lambda conn, row, cache: (coord, src))

    def test_step1_bounded_venue_hit(self, monkeypatch):
        self._anchor(monkeypatch)
        monkeypatch.setattr(vg, "_geocode_retry",
                            lambda q, viewbox=None, bounded=False:
                            {"lat": 40.75, "lon": -73.99, "confidence": "high",
                             "display_name": "Beacon Theatre"})
        out = vg.resolve_one(None, _row(venue="Beacon Theatre"), {})
        assert out["source"] == "bounded_venue"
        assert (out["lat"], out["lon"], out["confidence"]) == (40.75, -73.99, "high")

    def test_step2_wikidata_when_bounded_misses(self, monkeypatch):
        self._anchor(monkeypatch)
        monkeypatch.setattr(vg, "_geocode_retry",
                            lambda *a, **k: {"lat": None, "lon": None, "source": "failed"})
        monkeypatch.setattr(vg, "_wikidata_venue_coord", lambda venue, anchor: (40.1, -74.1))
        out = vg.resolve_one(None, _row(venue="Old Boston Garden"), {})
        assert out["source"] == "wikidata"
        assert (out["lat"], out["lon"], out["confidence"]) == (40.1, -74.1, "high")

    def test_step3_city_fallback(self, monkeypatch):
        self._anchor(monkeypatch, coord=(40.0, -74.0), src="setlistfm_city")
        monkeypatch.setattr(vg, "_geocode_retry",
                            lambda *a, **k: {"lat": None, "lon": None, "source": "failed"})
        monkeypatch.setattr(vg, "_wikidata_venue_coord", lambda venue, anchor: None)
        out = vg.resolve_one(None, _row(venue="Nowhere Hall"), {})
        assert out["source"] == "setlistfm_city"
        assert (out["lat"], out["lon"], out["confidence"]) == (40.0, -74.0, "city")

    def test_failed_when_no_anchor(self, monkeypatch):
        monkeypatch.setattr(vg, "_city_anchor", lambda conn, row, cache: (None, ""))
        out = vg.resolve_one(None, _row(venue="Ghost Venue", city=""), {})
        assert out["source"] == "failed"
        assert out["lat"] is None


class TestWikidataVenueCoord:
    def _resp(self, monkeypatch, bindings):
        import io
        import json as _json

        class _Ctx:
            def __enter__(self_): return io.BytesIO(
                _json.dumps({"results": {"bindings": bindings}}).encode())
            def __exit__(self_, *a): return False

        monkeypatch.setattr(vg.time, "sleep", lambda *a: None)
        monkeypatch.setattr(vg.urllib.request, "urlopen", lambda *a, **k: _Ctx())

    def test_accepts_coord_within_radius(self, monkeypatch):
        self._resp(monkeypatch, [{"coord": {"value": "Point(-74.01 40.71)"}}])
        assert vg._wikidata_venue_coord("Madison Square Garden", (40.75, -73.99)) \
            == (40.71, -74.01)

    def test_rejects_coord_outside_radius(self, monkeypatch):
        # A same-name venue on the other side of the world must be rejected.
        self._resp(monkeypatch, [{"coord": {"value": "Point(151.2 -33.8)"}}])
        assert vg._wikidata_venue_coord("Fox Theatre", (40.75, -73.99)) is None

    def test_network_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(vg.time, "sleep", lambda *a: None)

        def boom(*a, **k):
            raise vg.urllib.error.URLError("down")

        monkeypatch.setattr(vg.urllib.request, "urlopen", boom)
        assert vg._wikidata_venue_coord("Any", (0.0, 0.0)) is None


class TestResolveVenues:
    def test_updates_seeded_skips_manual_and_honors_limit(self, tmp_path, monkeypatch):
        _db, c = _make_db(tmp_path, monkeypatch)
        c.executemany(
            """INSERT INTO venue_geocoded (venue_norm, city_norm, venue, city, source,
                   manual_override) VALUES (?,?,?,?,?,?)""",
            [
                ("a hall", "oakland", "A Hall", "Oakland", "seeded", 0),
                ("b hall", "oakland", "B Hall", "Oakland", "seeded", 0),
                ("m hall", "oakland", "M Hall", "Oakland", "manual", 1),
            ],
        )
        c.commit()
        monkeypatch.setattr(vg, "_city_anchor",
                            lambda conn, row, cache: ((37.8, -122.3), "city_geocode"))
        monkeypatch.setattr(vg, "_geocode_retry",
                            lambda q, viewbox=None, bounded=False:
                            {"lat": 37.81, "lon": -122.27, "confidence": "high",
                             "display_name": q})
        monkeypatch.setattr(vg, "_wikidata_venue_coord", lambda venue, anchor: None)

        summary = vg.resolve_venues(limit=1)
        assert summary["processed"] == 1  # limit honored

        vg.resolve_venues()  # process the rest
        rows = {r["venue_norm"]: r for r in c.execute("SELECT * FROM venue_geocoded")}
        assert rows["a hall"]["source"] == "bounded_venue"
        assert rows["b hall"]["source"] == "bounded_venue"
        assert rows["a hall"]["lat"] == 37.81
        # manual row untouched.
        assert rows["m hall"]["source"] == "manual"
        assert rows["m hall"]["lat"] is None
