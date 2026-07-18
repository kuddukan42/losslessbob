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


def _insert_song_performance(conn, event_id, position, song_norm, concert_date_iso):
    conn.execute(
        "INSERT INTO song_performances (event_id, position, song_norm, song_canonical, "
        "concert_date_iso) VALUES (?, ?, ?, ?, ?)",
        (event_id, position, song_norm, song_norm, concert_date_iso),
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
