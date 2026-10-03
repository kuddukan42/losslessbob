"""TODO-346: venue -> Wikipedia link (lookup grading, cache reader, venue-card render)."""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from backend.dossier_fields import venue_wiki_link
from tests.test_dossier import _insert_entry, _insert_event, _make_db, _render_dossier_template
from tools.venue_wiki_lookup import (
    Candidate,
    _sparql_query,
    judge,
    main,
    parse_bindings,
)

SPECTRUM = "https://en.wikipedia.org/wiki/Spectrum_(arena)"


def _row(confidence="high", source="bounded_venue", lat=39.9045, lon=-75.1715,
         venue_norm="the spectrum"):
    return {"venue_norm": venue_norm, "lat": lat, "lon": lon, "source": source,
            "confidence": confidence}


def _cand(qid="Q1", names=("spectrum",), lat=39.9045, lon=-75.1720, url=SPECTRUM,
          title="Spectrum (arena)"):
    return Candidate(qid, title, url, frozenset(names), lat, lon)


class TestJudge:
    def test_name_and_venue_pin_within_2km_is_high(self):
        v = judge(_row(), [_cand()])
        assert (v.confidence, v.wiki_url) == ("high", SPECTRUM)

    def test_city_level_pin_caps_at_medium(self):
        v = judge(_row(confidence="city", source="setlistfm_city", lat=39.95, lon=-75.16),
                  [_cand()])
        assert v.confidence == "medium"

    def test_name_mismatch_is_ignored(self):
        v = judge(_row(), [_cand(names=("wells fargo center",))])
        assert v.wiki_url is None and v.confidence is None

    def test_same_name_far_away_is_low(self):
        v = judge(_row(), [_cand(lat=40.75, lon=-73.99)])
        assert v.confidence == "low"

    def test_no_coordinate_is_low(self):
        assert judge(_row(), [_cand(lat=None, lon=None)]).confidence == "low"

    def test_two_items_tied_at_best_grade_is_low(self):
        v = judge(_row(), [_cand(), _cand(qid="Q2", url="https://en.wikipedia.org/wiki/Other")])
        assert v.confidence == "low" and "ties" in v.note

    def test_alias_matches(self):
        v = judge(_row(venue_norm="the core states spectrum"),
                  [_cand(names=("spectrum", "core states spectrum"))])
        assert v.confidence == "high"


def test_parse_bindings_folds_labels_and_aliases_per_item():
    item = {"place": {"value": "http://www.wikidata.org/entity/Q7575"},
            "article": {"value": SPECTRUM}, "title": {"value": "Spectrum (arena)"}}
    cands = parse_bindings([
        {**item, "label": {"value": "Spectrum"}, "coord": {"value": "Point(-75.17 39.90)"}},
        {**item, "alt": {"value": "CoreStates Spectrum"}},
        {"place": {"value": "http://www.wikidata.org/entity/Q9"}},  # no article: dropped
    ])
    assert len(cands) == 1
    c = cands[0]
    assert c.qid == "Q7575" and (c.lat, c.lon) == (39.90, -75.17)
    assert {"spectrum", "corestates spectrum"} <= c.names


def test_query_escapes_quotes_and_backslashes():
    q = _sparql_query('Joe\'s "Pub" \\ Bar')
    assert 'mwapi:search "Joe\'s \\"Pub\\" \\\\ Bar"' in q


# ---------------------------------------------------------------------------
# Cache reader + render
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    db_path, conn, tmp_dir = _make_db()
    conn.row_factory = sqlite3.Row
    yield db_path, conn
    conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _link(conn, venue_norm, url, source="wikidata", confidence="high", city_norm="philadelphia"):
    conn.execute(
        "INSERT INTO venue_wiki_links (venue_norm, city_norm, wiki_title, wiki_url, source, "
        "confidence) VALUES (?, ?, ?, ?, ?, ?)",
        (venue_norm, city_norm, "Spectrum (arena)" if url else None, url, source, confidence))


class TestVenueWikiLink:
    def test_high_wikidata_row_renders(self, db):
        _, conn = db
        _link(conn, "the spectrum", SPECTRUM)
        got = venue_wiki_link(conn, ["The Spectrum"], "Philadelphia, PA")
        assert got["url"] == SPECTRUM and got["title"] == "Spectrum (arena)"

    def test_low_row_does_not_render(self, db):
        _, conn = db
        _link(conn, "the spectrum", SPECTRUM, confidence="low")
        assert venue_wiki_link(conn, ["The Spectrum"], "Philadelphia") is None

    def test_no_link_override_beats_another_spelling(self, db):
        _, conn = db
        _link(conn, "spectrum", SPECTRUM)
        _link(conn, "the spectrum", None, source="override", confidence=None)
        assert venue_wiki_link(conn, ["Spectrum", "The Spectrum"], "Philadelphia") is None

    def test_malformed_url_refused(self, db):
        _, conn = db
        _link(conn, "the spectrum", "javascript:alert(1)", source="override", confidence=None)
        assert venue_wiki_link(conn, ["The Spectrum"], "Philadelphia") is None

    def test_country_keyed_row_found(self, db):
        _, conn = db
        _link(conn, "the spectrum", SPECTRUM, city_norm="philadelphia|united states")
        assert venue_wiki_link(conn, ["The Spectrum"], "Philadelphia", "United States")

    def test_missing_table_is_none(self, db):
        _, conn = db
        conn.execute("DROP TABLE venue_wiki_links")
        assert venue_wiki_link(conn, ["The Spectrum"], "Philadelphia") is None


def _spectrum_show(conn):
    _insert_entry(conn, 101, "10/4/76", location="The Spectrum")
    _insert_event(conn, 1, "1976-10-04", page_filename="p1")
    conn.execute("UPDATE olof_events SET venue='The Spectrum', city='Philadelphia', "
                 "country='United States' WHERE event_id=1")


def test_venue_card_links_the_article(db):
    from backend.dossier import build_dossier
    from backend.dossier_qc import lint_data_lb

    db_path, conn = db
    _spectrum_show(conn)
    _link(conn, "the spectrum", SPECTRUM, city_norm="philadelphia|united states")
    conn.commit()
    result = build_dossier("1976-10-04", db_path=db_path)
    assert result["view"]["fields"]["venue.wiki"]["value"]["url"] == SPECTRUM
    html = _render_dossier_template(result)
    assert f'href="{SPECTRUM}"' in html and 'data-lb="venue.wiki"' in html
    assert lint_data_lb(html) == []


def test_venue_card_without_a_row_has_no_link(db):
    from backend.dossier import build_dossier

    db_path, conn = db
    _spectrum_show(conn)
    conn.commit()
    result = build_dossier("1976-10-04", db_path=db_path)
    assert result["view"]["fields"]["venue.wiki"]["value"] is None  # omit fallback
    assert 'data-lb="venue.wiki"' not in _render_dossier_template(result)


class TestOverrideCli:
    def test_set_override_writes_row(self, db):
        db_path, conn = db
        assert main(["--db", db_path, "--set-override", "The Spectrum", "Philadelphia",
                     SPECTRUM, "--apply"]) == 0
        row = conn.execute("SELECT * FROM venue_wiki_links").fetchone()
        assert (row["venue_norm"], row["source"], row["wiki_title"]) == (
            "the spectrum", "override", "Spectrum (arena)")

    def test_non_wikipedia_url_refused(self, db):
        db_path, conn = db
        assert main(["--db", db_path, "--set-override", "The Spectrum", "Philadelphia",
                     "https://example.com/x", "--apply"]) == 2
        assert conn.execute("SELECT COUNT(*) FROM venue_wiki_links").fetchone()[0] == 0

    def test_dry_run_writes_nothing(self, db):
        db_path, conn = db
        assert main(["--db", db_path, "--no-link", "The Spectrum", "Philadelphia"]) == 0
        assert conn.execute("SELECT COUNT(*) FROM venue_wiki_links").fetchone()[0] == 0
