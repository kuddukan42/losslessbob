"""Tests for the show dossier assembly (backend/dossier.py, TODO-257).

Fixture date has 2 tapematch families plus a singleton, an olof event with
two songs, and one private entry — covers: (i) section omission on a
fresh-install DB (derived tables empty), (ii) channel='public' blanking
private-source metadata vs channel='full' keeping it, (iii) rarity flags for
an 'only' and a 'rare' song, (iv) ambiguous two-show date requiring location.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _make_db() -> tuple[str, object, str]:
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_dossier_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _insert_entry(conn, lb_number, date_str, location="Some Hall, Some City",
                   status="ok", rating=None, timing=None, source_type=None,
                   source_chain=None):
    conn.execute(
        "INSERT INTO entries (lb_number, date_str, location, status, rating, "
        "timing, source_type, source_chain) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (lb_number, date_str, location, status, rating, timing, source_type, source_chain),
    )
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status) VALUES (?, 'public')",
        (lb_number,),
    )


def _insert_event(conn, event_id, date_str, event_type="concert", page_filename="p1"):
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
        (page_filename,),
    )
    conn.execute(
        "INSERT INTO olof_events (event_id, page_filename, event_type, date_str) "
        "VALUES (?, ?, ?, ?)",
        (event_id, page_filename, event_type, date_str),
    )


def _insert_song(conn, event_id, position, song_title, is_encore=0):
    conn.execute(
        "INSERT INTO olof_songs (event_id, position, song_title, is_encore) "
        "VALUES (?, ?, ?, ?)",
        (event_id, position, song_title, is_encore),
    )


def _insert_song_performance(
    conn, event_id, position, song_norm, concert_date_iso, song_canonical="",
):
    """Insert a ``song_performances`` row.

    *song_canonical* defaults to ``""`` (unset -- the column is NOT NULL),
    not *song_norm* -- most callers only care about rarity/history matching
    on ``song_norm``, and C4 now displays ``song_canonical`` by position
    when present, so forcing it to the lowercase norm text would silently
    override the display title in every test that doesn't care about it.
    Pass *song_canonical* explicitly to exercise that display path.
    """
    conn.execute(
        "INSERT INTO song_performances (event_id, position, song_norm, song_canonical, "
        "concert_date_iso) VALUES (?, ?, ?, ?, ?)",
        (event_id, position, song_norm, song_canonical, concert_date_iso),
    )


def _insert_family(conn, lb_number, fam_id, concert_date):
    conn.execute(
        "INSERT INTO recording_families (lb_number, fam_id, concert_date) VALUES (?, ?, ?)",
        (lb_number, fam_id, concert_date),
    )


class TestFreshInstallDegrade:
    def test_no_derived_tables_populated(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)

            assert "ambiguous" not in result
            assert result["show"]["date_iso"] == "2000-07-28"
            assert "setlist" not in result
            assert "context" not in result
            assert len(result["sources"]) == 1
            member = result["sources"][0]["members"][0]
            assert "pick" not in member
            assert "quality" not in member
            assert "taper" not in member
            assert result["provenance"]["local_analysis"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_totally_unknown_date_still_returns_a_shape(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("1975-12-04", db_path=db_path)
            assert result["show"]["date_iso"] == "1975-12-04"
            assert "sources" not in result
            assert "setlist" not in result
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestChannelGating:
    def test_public_channel_blanks_private_source(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00", status="private", rating="A",
                           timing="60:00", source_type="Soundboard")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", channel="public", db_path=db_path)
            member = result["sources"][0]["members"][0]
            assert member == {"lb": "LB-00101", "private": True}
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_full_channel_keeps_private_source_metadata(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00", status="private", rating="A",
                           timing="60:00", source_type="Soundboard")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", channel="full", db_path=db_path)
            member = result["sources"][0]["members"][0]
            assert member["lb"] == "LB-00101"
            assert member["rating"] == "A"
            assert member["timing"] == "60:00"
            assert "private" not in member
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestRarityFlags:
    def test_only_and_rare_flags(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_song(conn, 1, 1, "One Time Wonder")
            _insert_song(conn, 1, 2, "Common Song")
            _insert_song_performance(conn, 1, 1, "one time wonder", "2000-07-28")
            _insert_song_performance(conn, 1, 2, "common song", "2000-07-28")
            # "Common Song" performed a second time elsewhere, still <= RARE_THRESHOLD
            _insert_event(conn, 2, "2001-01-01")
            _insert_song(conn, 2, 1, "Common Song")
            _insert_song_performance(conn, 2, 1, "common song", "2001-01-01")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            setlist_by_title = {s["title"]: s for s in result["setlist"]}
            assert setlist_by_title["One Time Wonder"]["rarity"]["flag"] == "only"
            assert setlist_by_title["Common Song"]["rarity"]["flag"] in ("first", "rare")
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestAmbiguousDate:
    """Ambiguity is keyed off olof_events.venue (clean/normalised), never
    entries.location — real data has a dozen free-text spellings of the same
    single venue (e.g. "Foxboro, MA" / "Foxboro MA, Sullivan Stadium" /
    "Foxborough, MA, U.S.A." all for one real show), which would otherwise
    false-positive on nearly every well-documented date.
    """

    def test_messy_entries_location_spelling_is_not_ambiguous(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00", location="Venue A, City A")
            _insert_entry(conn, 102, "7/28/00", location="Venue A - City A (audience)")
            _insert_entry(conn, 103, "7/28/00", location="venue a, city a")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert "ambiguous" not in result
            assert len(result["sources"]) == 3
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_two_distinct_olof_venues_requires_disambiguation(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28", page_filename="p1")
            conn.execute("UPDATE olof_events SET venue='Venue A' WHERE event_id=1")
            _insert_event(conn, 2, "2000-07-28", page_filename="p2")
            conn.execute("UPDATE olof_events SET venue='Venue B' WHERE event_id=2")
            _insert_entry(conn, 101, "7/28/00", location="Venue A, City A")
            _insert_entry(conn, 102, "7/28/00", location="Venue B, City B")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert result["ambiguous"] is True
            locs = {c["location"] for c in result["candidates"]}
            assert locs == {"Venue A", "Venue B"}
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_location_param_resolves_ambiguity(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28", page_filename="p1")
            conn.execute("UPDATE olof_events SET venue='Venue A' WHERE event_id=1")
            _insert_event(conn, 2, "2000-07-28", page_filename="p2")
            conn.execute("UPDATE olof_events SET venue='Venue B' WHERE event_id=2")
            _insert_entry(conn, 101, "7/28/00", location="Venue A, City A")
            _insert_entry(conn, 102, "7/28/00", location="Venue B, City B")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", location="Venue A", db_path=db_path)
            assert "ambiguous" not in result
            assert result["show"]["venue"] == "Venue A"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestBBcodeDigest:
    def test_renders_show_setlist_and_sources(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            conn.execute("UPDATE olof_events SET venue='Some Hall' WHERE event_id=1")
            _insert_song(conn, 1, 1, "One Time Wonder")
            _insert_song_performance(conn, 1, 1, "one time wonder", "2000-07-28")
            _insert_entry(conn, 101, "7/28/00", rating="A")
            conn.commit()

            from backend.dossier import build_dossier, filter_dossier_sections, render_bbcode
            result = build_dossier("2000-07-28", db_path=db_path)
            text = render_bbcode(filter_dossier_sections(result))

            assert "[b]Setlist[/b]" in text
            assert "One Time Wonder" in text
            assert "(only performance)" in text
            assert "LB-00101" in text
            assert "rating A" in text
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_local_analysis_off_hides_recommendation_and_pick(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
                "evidence_json, concert_date_iso) VALUES ('7/28/00', 101, 90.0, 1, '[]', '2000-07-28')"
            )
            conn.commit()

            from backend.dossier import build_dossier, filter_dossier_sections, render_bbcode
            result = build_dossier("2000-07-28", db_path=db_path)
            assert "recommendation" in result

            view = filter_dossier_sections(result, local_analysis=False)
            assert "recommendation" not in view
            text = render_bbcode(view)
            assert "Recommended" not in text
            assert "pick #" not in text
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestFamilyGrouping:
    def test_two_families_plus_singleton(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            for lb in (101, 102, 103, 104, 105):
                _insert_entry(conn, lb, "7/28/00")
            _insert_family(conn, 101, "2000-07-28#101-102", "2000-07-28")
            _insert_family(conn, 102, "2000-07-28#101-102", "2000-07-28")
            _insert_family(conn, 103, "2000-07-28#103-104", "2000-07-28")
            _insert_family(conn, 104, "2000-07-28#103-104", "2000-07-28")
            # 105 stays a singleton — no recording_families row
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert len(result["sources"]) == 3
            fam_buckets = [b for b in result["sources"] if "fam_id" in b]
            singleton_buckets = [b for b in result["sources"] if "fam_id" not in b]
            assert len(fam_buckets) == 2
            assert len(singleton_buckets) == 1
            assert singleton_buckets[0]["members"][0]["lb"] == "LB-00105"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestXrefDeepLinks:
    """Every cross-reference card must link a page that actually resolves.

    2022+ shows are ingested from bobserve's own setlist database, and their
    olof_events.page_filename is the synthetic local name of the scraped page
    ('bobserve_event_<id>.html'). That file does not exist on the Olof mirror,
    so building an Olof deep link from it 404s — the bobserve card carries the
    deep link for those instead.
    """

    def test_dsn_page_deep_links_the_olof_mirror(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            with conn:
                _insert_entry(conn, 201, "7/28/00")
                _insert_event(conn, 1, "2000-07-28", page_filename="DSN12345 (00).htm")
                conn.commit()

            from backend.dossier import build_dossier
            xref = {c["key"]: c for c in build_dossier("2000-07-28", db_path=db_path)["xref"]}
            assert xref["olof"]["url"] == (
                "https://www.bobserve.com/olof/DSN12345%20%2800%29.htm#DSN00001")
            assert xref["olof"]["is_source"] is True
            assert xref["bobserve"]["url"] == "https://bobserve.com/eventsperiod?period=2000"
            assert xref["bobserve"]["is_source"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_bobserve_page_deep_links_bobserve_not_the_olof_mirror(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            with conn:
                _insert_entry(conn, 202, "10/16/23")
                _insert_event(conn, 9004282, "2023-10-16",
                              page_filename="bobserve_event_4282.html")
                conn.commit()

            from backend.dossier import build_dossier
            xref = {c["key"]: c for c in build_dossier("2023-10-16", db_path=db_path)["xref"]}
            assert xref["bobserve"]["url"] == "https://bobserve.com/setlist?event=4282"
            assert xref["bobserve"]["is_source"] is True
            # No fabricated mirror link — fall back to the chronicle index.
            # F7: bjorner.com is parked; the fallback is now the bobserve mirror's
            # own Olof index.
            assert xref["olof"]["url"] == "https://www.bobserve.com/olof/"
            assert xref["olof"]["is_source"] is False
            # F7: boblinks no longer guesses a MMDDYYs.html URL (unreliable -- some
            # real dates 404); it only links a date the boblinks_pages crawl found.
            # This fixture has no boblinks_pages row, so the card falls back unavailable.
            assert xref["boblinks"]["unavailable"] is True
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_bobserve_two_show_day_picks_early_or_late(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            with conn:
                _insert_entry(conn, 205, "1/6/74")
                _insert_event(conn, 2250, "1974-01-06", page_filename="DSN02230 1974 Tour.htm")
                conn.execute("UPDATE olof_events SET venue = 'The Spectrum', "
                             "date_raw = '6 January 1974 – Evening' WHERE event_id = 2250")
                conn.executemany(
                    "INSERT INTO bobserve_event_index (event_id, date_str, venue, event_type)"
                    " VALUES (?, ?, 'The Spectrum', 'Concert')",
                    [(839, "1974-01-06 Early"), (840, "1974-01-06 Late")],
                )
                conn.commit()

            from backend.dossier import build_dossier
            xref = {c["key"]: c for c in build_dossier("1974-01-06", db_path=db_path)["xref"]}
            assert xref["bobserve"]["url"] == "https://bobserve.com/setlist?event=840"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_bobdylan_card_picks_the_event_venue_page(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            with conn:
                _insert_entry(conn, 204, "3/29/10")
                _insert_event(conn, 611, "2010-03-29", page_filename="DSN00611 2010.htm")
                conn.execute("UPDATE olof_events SET venue = 'Zepp Tokyo' WHERE event_id = 611")
                conn.executemany(
                    "INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue) "
                    "VALUES (?, '2010-03-29', ?)",
                    [("https://www.bobdylan.com/date/2010-03-29-a-hall/", "A Hall"),
                     ("https://www.bobdylan.com/date/2010-03-29-zepp-tokyo/", "Zepp Tokyo")],
                )
                conn.commit()

            from backend.dossier import build_dossier
            xref = {c["key"]: c for c in build_dossier("2010-03-29", db_path=db_path)["xref"]}
            assert xref["bobdylan"]["url"] == "https://www.bobdylan.com/date/2010-03-29-zepp-tokyo/"
            assert xref["bobdylan"]["unavailable"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_pre_2022_bobserve_link_from_event_index_and_boblinks_unavailable(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            with conn:
                _insert_entry(conn, 203, "10/26/63")
                _insert_event(conn, 610, "1963-10-26", page_filename="DSN00340 1963.htm")
                conn.executemany(
                    "INSERT INTO bobserve_event_index (event_id, date_str, venue, event_type)"
                    " VALUES (?, '1963-10-26', 'Carnegie Hall', ?)",
                    [(365, "Concert"), (4578, "Soundcheck")],
                )
                conn.commit()

            from backend.dossier import build_dossier
            xref = {c["key"]: c for c in build_dossier("1963-10-26", db_path=db_path)["xref"]}
            assert xref["bobserve"]["url"] == "https://bobserve.com/setlist?event=365"
            assert xref["olof"]["url"].endswith("DSN00340%201963.htm#DSN00610")
            assert xref["boblinks"]["unavailable"] is True
            assert xref["bobdylan"]["unavailable"] is True
            assert xref["bobdylan"]["url"] == "https://www.bobdylan.com"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)



class TestTemplateAnchorCoverage:
    """C29: every ANCHORS key must be reachable from the template.

    The template renders keys through ``lbf('<key>', ...)``/``data-lb="<key>"``
    literals, so a plain quoted-string search of the template source is a
    faithful (if slightly loose) proxy for "this anchor has a rendering path" --
    it does not depend on which branches a particular fixture dossier happens to
    take at render time.
    """

    _EXCEPTIONS = {
        "show.newest_source_date": "D-12 null stub (df.newest_source_date is unbuilt); "
        "fallback_kind='suppress' -- the anchor is registered but never has a value "
        "to show, so there is nothing for the template to render a data-lb around.",
    }

    def test_every_anchor_key_referenced_in_template(self):
        import re

        from backend.dossier_anchors import ANCHORS

        template_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "templates", "dossier.html")
        src = open(template_path, encoding="utf-8").read()
        missing = [
            key for key in ANCHORS
            if key not in self._EXCEPTIONS and not re.search(rf"""['"]{re.escape(key)}['"]""", src)
        ]
        assert missing == [], f"anchors with no reference in dossier.html: {missing}"


def _render_dossier_template(d):
    """Render dossier.html directly via Jinja (no Flask app / DB thread startup)."""
    import os

    from jinja2 import Environment, FileSystemLoader

    from backend.dossier_claims import (
        claim_texts_for,
        ledger_detail_text,
        sentence_segment_groups,
    )

    templates_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "templates")
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    env.globals["claim_groups"] = sentence_segment_groups
    env.globals["claim_texts_for"] = claim_texts_for
    env.globals["ledger_detail_text"] = ledger_detail_text
    return env.get_template("dossier.html").render(d=d)


def _build_lint_fixture_dossier(channel="full"):
    """A rendering-rich fixture: an event, 2 songs, 2 sources (pick + runner-up),
    a family, and a G7 claim -- exercises the verdict/ledger/setlist/sources
    sections enough to be a meaningful L1/L2/blank-ratio/lb-qc smoke test.
    """
    from tests.test_dossier_qc import _insert_two_source_pick

    db_path, conn, tmp_dir = _make_db()
    _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
    _insert_song(conn, 1, 1, "Rainy Day Women # 12 & 35")
    _insert_song_performance(conn, 1, 1, "rainy day women 12 35", "2010-03-29")
    conn.execute(
        "INSERT INTO recording_families (lb_number, fam_id, concert_date) VALUES"
        " (101, '2010-03-29#101-102', '2010-03-29'),"
        " (102, '2010-03-29#101-102', '2010-03-29')"
    )
    conn.commit()

    from backend.dossier import build_dossier
    result = build_dossier("2010-03-29", db_path=db_path, channel=channel)
    return result, tmp_dir


class TestRenderedTemplateLints:
    def test_l1_and_data_lb_clean_on_a_fixture_dossier(self):
        import shutil

        from backend.dossier_qc import lint_data_lb, lint_l1

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            html = _render_dossier_template(result)
            assert lint_l1(html) == []
            assert lint_data_lb(html) == []
            assert "review" not in html.lower() or "data-claim" in html
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_always_on_review_badge(self):
        import shutil

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            html = _render_dossier_template(result)
            assert "fam-review" not in html
            assert ">review<" not in html.lower()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_blank_line_ratio_under_5_percent(self):
        import shutil

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            html = _render_dossier_template(result)
            lines = html.splitlines()
            blank = sum(1 for line in lines if not line.strip())
            assert blank / len(lines) < 0.05
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_lb_qc_json_parses_and_matches_qc(self):
        import json
        import re
        import shutil

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            html = _render_dossier_template(result)
            m = re.search(
                r'<script type="application/json" id="lb-qc">(.*?)</script>', html, re.DOTALL)
            assert m is not None
            embedded = json.loads(m.group(1))
            assert embedded["checks_run"] == result["qc"]["checks_run"]
            assert embedded["passed"] == result["qc"]["passed"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_local_analysis_off_has_no_pick_verdict_ledger_or_scan_grade(self):
        import shutil

        from backend.dossier import filter_dossier_sections

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            view = filter_dossier_sections(result, local_analysis=False)
            html = _render_dossier_template(view)
            assert "Recommended copy" not in html
            assert 'class="ledger"' not in html
            assert 'class="pick-tag"' not in html
            assert 'class="grade ' not in html
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_fresh_install_no_view_renders_minimal_page_not_500(self):
        html = _render_dossier_template({"show": {"date_iso": "2000-01-01"}})
        assert "Dossier unavailable" in html
        assert "data-lb=" not in html

    def test_no_double_escaped_entities(self):
        import shutil

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            html = _render_dossier_template(result)
            assert "&amp;middot;" not in html
            assert "&amp;times;" not in html
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_ledger_best_transfer_and_solo_render_l1_clean(self):
        import shutil

        from backend.dossier_qc import lint_l1

        result, tmp_dir = _build_lint_fixture_dossier()
        try:
            result["view"]["fields"]["ledger[]"]["value"] = [
                {"kind": "best_transfer", "detail": "best transfer in its family", "points": 5.0},
                {"kind": "solo", "detail": "only surviving circulating copy", "points": 2.0},
                {"kind": "rating", "detail": "LB rating A", "points": 91.7},
            ]
            html = _render_dossier_template(result)
            assert "preferred transfer within its tape family" in html
            assert "single circulating copy" in html
            assert "LB rating A" in html
            assert lint_l1(html) == []
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestTemplateL2Lint:
    """C29: the template SOURCE (CSS/JS/comments included) may not contain any L1
    forbidden phrase or bare word outside the ``claim`` macro's own definition --
    that macro is the only place comparative wording is allowed to reach the page,
    so its *body* (not its call sites, which pass in already-verified text) is the
    one legitimate exemption zone in the template source itself.
    """

    def test_l1_words_absent_from_template_source_outside_claim_macro(self):
        import re

        from backend.dossier_qc import _L1_BARE_WORDS, _L1_PHRASES

        template_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "templates", "dossier.html")
        src = open(template_path, encoding="utf-8").read()

        macro_match = re.search(
            r"\{%-?\s*macro claim\(.*?\{%-?\s*endmacro\s*-?%\}", src, re.DOTALL)
        assert macro_match is not None, "claim macro definition not found"
        stripped = src[:macro_match.start()] + src[macro_match.end():]

        # Jinja control/expression/comment syntax ({%...%}, {{...}}, {#...#}) is
        # template plumbing (variable names, filters, loop attributes -- "best",
        # "first", loop.last, developer comments) that can never reach the rendered
        # page as literal text; the L1/L2 rule is about words a reader could see, so
        # blank those blocks out before scanning the remaining static HTML/CSS/JS
        # (tags, attributes, inline <style>/<script> text, HTML comments).
        for pattern in (r"\{#.*?#\}", r"\{%-?.*?-?%\}", r"\{\{-?.*?-?\}\}"):
            stripped = re.sub(pattern, " ", stripped, flags=re.DOTALL)
        lower = stripped.lower()

        violations = []
        for phrase in _L1_PHRASES:
            if phrase in lower:
                violations.append(phrase)
        for word in _L1_BARE_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", lower):
                violations.append(word)
        assert violations == [], f"L1 words/phrases found in template source: {violations}"
