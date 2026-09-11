"""Tests for the show-dossier redesign's Olof parser work (TODO-342, plan Phase 1).

C01: the new olof_events / olof_songs columns, their idempotent migration, the
parser's upsert of them, and tools/olof_reparse_diff.py's change classifier.
"""
import sqlite3

import pytest

import backend.db as db
import backend.paths as _paths
from backend.olof_parser import (
    EventRecord,
    SongRecord,
    _is_guest_header,
    _parse_event,
    _split_title_credits,
    _split_title_parts,
    _upsert_events,
    _upsert_songs,
)
from tools import olof_reparse_diff as rd

_NEW_EVENT_COLS = {"rotation_new", "rotation_pct", "tour_new_count", "venue_history_raw"}


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "DATA_DIR", tmp_path)
    path = str(tmp_path / "test.db")
    db.init_db(path)
    yield path
    db.close_connection(path)


def _cols(path, table):
    return {r[1] for r in db.get_connection(path).execute(f"PRAGMA table_info({table})")}


def test_init_db_twice_is_clean(db_path):
    db.init_db(db_path)
    assert _NEW_EVENT_COLS <= _cols(db_path, "olof_events")
    assert "subtitle" in _cols(db_path, "olof_songs")


def test_migration_adds_columns_to_an_old_db(db_path):
    db.close_connection(db_path)
    raw = sqlite3.connect(db_path)
    for col in sorted(_NEW_EVENT_COLS):
        raw.execute(f"ALTER TABLE olof_events DROP COLUMN {col}")
    raw.execute("ALTER TABLE olof_songs DROP COLUMN subtitle")
    raw.commit()
    raw.close()
    assert not _NEW_EVENT_COLS & _cols(db_path, "olof_events")
    db.close_connection(db_path)

    db.init_db(db_path)
    assert _NEW_EVENT_COLS <= _cols(db_path, "olof_events")
    assert "subtitle" in _cols(db_path, "olof_songs")


def test_upsert_writes_the_new_columns(db_path):
    conn = db.get_connection(db_path)
    conn.execute("INSERT INTO olof_pages (filename, url, corpus) VALUES ('p1', 'http://x', 'dsn')")
    events = [
        EventRecord(event_id=1, page_filename="p1", rotation_new=13, rotation_pct=72,
                    tour_new_count=2, venue_history_raw="Other Bob Dylan shows in Tokyo:"),
        EventRecord(event_id=2, page_filename="p1", source="bobserve"),
    ]
    _upsert_events(conn, events)
    _upsert_songs(conn, events, [
        SongRecord(event_id=1, position=3, song_title="Most Likely You Go Your Way",
                   subtitle="And I'll Go Mine"),
    ])
    row = conn.execute("SELECT rotation_new, rotation_pct, tour_new_count, venue_history_raw"
                       " FROM olof_events WHERE event_id=1").fetchone()
    assert tuple(row) == (13, 72, 2, "Other Bob Dylan shows in Tokyo:")
    bob = conn.execute("SELECT rotation_new, venue_history_raw FROM olof_events"
                       " WHERE event_id=2").fetchone()
    assert tuple(bob) == (None, "")
    sub = conn.execute("SELECT subtitle FROM olof_songs WHERE event_id=1").fetchone()[0]
    assert sub == "And I'll Go Mine"


# --- tools/olof_reparse_diff.py classifier ----------------------------------------------

_STAT = "13 new songs (72%) compared to previous concert. 2 new songs for this tour."
_BLOB = "Other Bob Dylan shows in Tokyo, Japan: 1 March 1978 Nippon Budokan Hall"


def _event(**kw):
    base = {"event_id": 1, "date_str": "2010-03-29", "venue": "Zepp", "notes": "",
            "releases_raw": "", "bobtalk": "", "references_raw": "",
            "raw_text": f"Zepp\n1.\nRainy Day Women\n{_STAT}\n{_BLOB}\nreleased on X",
            "rotation_new": None, "rotation_pct": None, "tour_new_count": None,
            "venue_history_raw": ""}
    base.update(kw)
    return base


def _song(pos, **kw):
    base = {"event_id": 1, "position": pos, "song_title": f"Song {pos}", "credits": "",
            "subtitle": "", "is_encore": 0, "take_number": None, "take_status": "",
            "annotations": "", "released_on": ""}
    base.update(kw)
    return base


def _classify(before, after, b_songs, a_songs):
    return rd.classify_event(1, before, after, b_songs, a_songs)


def test_unchanged_event_is_not_reported():
    d = _classify(_event(), _event(), [_song(1)], [_song(1)])
    assert not d.changed


def test_gained_songs_are_p1a_and_lost_songs_unexplained():
    d = _classify(_event(), _event(), [_song(1)], [_song(1), _song(2), _song(3)])
    assert d.buckets == {"P1a"} and not d.problems
    d = _classify(_event(), _event(), [_song(1), _song(2)], [_song(1)])
    assert d.problems == ["songs lost at positions 2"]


def test_annotation_removals_by_kind():
    before = [_song(1, annotations="March 1978; harmonica; new songs for this tour")]
    d = _classify(_event(), _event(), before, [_song(1, annotations="harmonica")])
    assert d.buckets == {"P1b", "P1d"} and not d.problems
    d = _classify(_event(), _event(), [_song(1, annotations="harmonica")], [_song(1)])
    assert d.problems == ["song 1: annotation removed 'harmonica'"]
    d = _classify(_event(), _event(), [_song(1)], [_song(1, annotations="harmonica")])
    assert d.problems == ["song 1: annotation added 'harmonica'"]


def test_bobtalk_line_removed_from_annotations_is_p1g():
    ev = _event(bobtalk="Thank you! Harmonica break")
    d = _classify(ev, ev, [_song(1, annotations="Harmonica break")], [_song(1)])
    assert d.buckets == {"P1g"}


def test_venue_blob_and_stat_moved_out_of_notes():
    before = _event(notes=f"{_BLOB} {_STAT}")
    after = _event(venue_history_raw=_BLOB, rotation_new=13, rotation_pct=72, tour_new_count=2)
    d = _classify(before, after, [], [])
    assert d.buckets == {"P1c", "P1d"} and not d.problems


def test_notes_rewritten_beyond_the_fixes_is_unexplained():
    d = _classify(_event(notes=f"{_STAT} kept"), _event(notes="changed"), [], [])
    assert d.problems == ["notes changed beyond the P1c/P1d removals"]


def test_rotation_without_a_stat_on_the_page_is_unexplained():
    d = _classify(_event(raw_text="no stat"), _event(raw_text="no stat", rotation_new=1), [], [])
    assert d.problems == ["rotation stats set, but the page text has no stat line"]


def test_credits_resplit_into_subtitle_is_p1e():
    before = [_song(3, song_title="Most Likely You Go Your Way", credits="And I'll Go Mine")]
    after = [_song(3, song_title="Most Likely You Go Your Way", subtitle="And I'll Go Mine")]
    d = _classify(_event(), _event(), before, after)
    assert d.buckets == {"P1e"} and not d.problems
    d = _classify(_event(), _event(), before, [_song(3, song_title="Other Title")])
    assert d.problems == ["song 3: title/credits text changed, not just re-split"]


@pytest.mark.parametrize("line,title", [
    ("Like A Rolling St (Bob Dylan-Robert Hunter/Bob Dylan) one", "Like A Rolling Stone"),
    ("Forgetful Hear (Bob Dylan-Robert Hunter/Bob Dylan) t", "Forgetful Heart"),
])
def test_spliced_credit_is_dropped_and_word_rejoined(line, title):
    """BUG-347: the next song's credit landed mid-word on Olof's page."""
    assert _split_title_parts(line) == (title, "", "")


def test_spliced_credit_repair_needs_a_credit_marker():
    assert _split_title_parts("Song Of The Day (Early Version) live") == (
        "Song Of The Day (Early Version) live", "", "")
    assert _split_title_parts("Jolene (Bob Dylan-Robert Hunter/Bob Dylan)") == (
        "Jolene", "Bob Dylan-Robert Hunter/Bob Dylan", "")


def test_spliced_credit_repair_is_b347():
    before = [_song(15, song_title="Like A Rolling St (Bob Dylan-Robert Hunter/Bob Dylan) one")]
    d = _classify(_event(), _event(), before, [_song(15, song_title="Like A Rolling Stone")])
    assert d.buckets == {"B347"} and not d.problems


def test_release_wording_cleanup_is_p1f():
    before = [_song(4, released_on="and part of 22 released on X")]
    d = _classify(_event(), _event(), before, [_song(4, released_on="X")])
    assert d.buckets == {"P1f"} and not d.problems
    d = _classify(_event(), _event(), [_song(4)], [_song(4, released_on="Y")])
    assert d.problems == ["song 4: release 'y' is not in the page text"]


def test_fixed_event_field_change_is_unexplained():
    d = _classify(_event(), _event(venue="Zepp DiverCity"), [], [])
    assert d.problems == ["event.venue changed"]


def test_snapshot_and_diff_round_trip(db_path, tmp_path):
    conn = db.get_connection(db_path)
    conn.execute("INSERT INTO olof_pages (filename, url, corpus) VALUES ('p1', 'http://x', 'dsn')")
    ev = EventRecord(event_id=1, page_filename="p1", date_str="2010-03-29", raw_text="1.\nA")
    _upsert_events(conn, [ev])
    _upsert_songs(conn, [ev], [SongRecord(event_id=1, position=1, song_title="A")])
    snap = tmp_path / "before.db"
    assert rd.snapshot(db_path, snap) == {"olof_events": 1, "olof_songs": 1}
    with pytest.raises(FileExistsError):
        rd.snapshot(db_path, snap)

    _upsert_songs(conn, [ev], [SongRecord(event_id=1, position=1, song_title="A"),
                               SongRecord(event_id=1, position=2, song_title="B")])
    diffs, meta = rd.diff(db_path, snap)
    assert "taken_at" in meta
    assert [(x.event_id, x.buckets, x.problems) for x in diffs] == [(1, {"P1a"}, [])]
    assert "| UNEXPLAINED | 0 |" in rd.render_report(diffs, db_path, snap, meta)


# --- C02: P1a guest/interlude blocks, P1g section guard ------------------------------------

def _numbered(titles: list[str], start: int = 1) -> list[str]:
    out: list[str] = []
    for n, title in enumerate(titles, start):
        out += [f"{n}.", title]
    return out


# Modelled on DSN02910 / 1975-12-08: a session-title line, then guest sets before song 1
# and between 13 and 14, one header spaced "Rob Stoner :", and "Official release"
# (singular) inside the References section.
_RTR_1975 = (
    ["Madison Square Garden", "New York City , New York", "8 December 1975",
     "Night of The Hurricane 1",
     "Bob Neuwirth:", "Good Love Is Hard To Find (Ned Albright)",
     "Rob Stoner :", "Too Good To Be Wasted (Rob Stoner)",
     "Bob Neuwirth:", "Cindy (When I Get Home) (trad.)", "Mercedes Benz (Janis Joplin)"]
    + _numbered([f"Dylan song {n}" for n in range(1, 8)])
    + ["—"]
    + _numbered([f"Dylan song {n}" for n in range(8, 14)], 8)
    + ["Joan Baez:", "Diamonds And Rust (Joan Baez)",
       "Roger McGuinn:", "Eight Miles High (Gene Clark, Roger McGuinn, David Crosby)"]
    + _numbered([f"Dylan song {n}" for n in range(14, 23)], 14)
    + ["Rolling Thunder Revue concert # 31.",
       "14, 15 Bob Dylan solo (vocal, guitar & harmonica).",
       "BobTalk", "14 years ago I wrote this one.",
       "Bootlegs", "Knight of the Hurricane . Razor's Edge GWW 001/002.",
       "References", "Larry Sloman: On The Road With Bob Dylan . Bantam Books 1978.",
       "Official release", "5 released on BOB DYLAN. The Rolling Thunder Revue.",
       "Notes", "2 available on Wolfgang's Vault March 2006.",
       "Mono audience recording, 105 minutes."]
)

# Modelled on DSN07660 / 1986-02-24: Tom Petty interludes after 7 and 16, encore dash at 23.
_TP_1986 = (
    ["Entertainment Centre", "Sydney, New South Wales, Australia", "24 February 1986"]
    + _numbered([f"Dylan song {n}" for n in range(1, 8)])
    + ["Tom Petty & The Heartbreakers:", "Straight Into Darkness (Tom Petty)",
       "Bye Bye Johnny (Chuck Berry)"]
    + _numbered([f"Dylan song {n}" for n in range(8, 17)], 8)
    + ["Tom Petty & The Heartbreakers:", "Refugee (Tom Petty & Mike Campbell)"]
    + _numbered([f"Dylan song {n}" for n in range(17, 23)], 17)
    + ["—"]
    + _numbered([f"Dylan song {n}" for n in range(23, 26)], 23)
    + ["Concert #13 of the 1986 True Confessions Far East Tour.",
       "Bob Dylan (vocal & guitar) with Tom Petty & The Heartbreakers:",
       "Tom Petty (guitar), Mike Campbell (guitar)",
       "8-10 Bob Dylan solo acoustic.",
       "Stereo PA audience recording, 120 minutes."]
)


def _songs_of(lines: list[str]) -> list[SongRecord]:
    return _parse_event(lines, 1, "p1", "")[1]


def test_guest_blocks_are_skipped_1975_12_08():
    songs = _songs_of(_RTR_1975)
    assert [s.position for s in songs] == list(range(1, 23))
    assert all(s.song_title.startswith("Dylan song") for s in songs)
    assert [s.position for s in songs if s.is_encore] == list(range(8, 23))
    by_pos = {s.position: s for s in songs}
    assert by_pos[14].annotations == "Bob Dylan solo (vocal, guitar & harmonica)"
    assert by_pos[5].released_on == "BOB DYLAN. The Rolling Thunder Revue"
    assert by_pos[2].released_on == "Wolfgang's Vault March 2006"


def test_interludes_are_skipped_1986_02_24():
    songs = _songs_of(_TP_1986)
    assert [s.position for s in songs] == list(range(1, 26))
    assert [s.position for s in songs if s.is_encore] == [23, 24, 25]
    assert {s.position: s.annotations for s in songs}[9] == "Bob Dylan solo acoustic"


def test_guest_header_right_after_the_date():
    lines = ["Venue", "City, Sweden", "1 May 1990", "Opening Act:", "Their Song",
             "1.", "First", "2.", "Second"]
    assert [s.song_title for s in _songs_of(lines)] == ["First", "Second"]


def test_header_not_followed_by_the_next_song_stops_the_walk():
    lines = ["Venue", "City, Sweden", "1 May 1990", "1.", "First", "2.", "Second",
             "Other Bob Dylan shows in Stockholm, Sweden:", "1 March 1978 Hall",
             "2 released on X.", "Stereo PA recording, 90 minutes."]
    songs = _songs_of(lines)
    assert [s.position for s in songs] == [1, 2]
    assert songs[1].released_on == "X"  # the trailer scan still starts at the header
    out_of_sequence = ["Venue", "City, Sweden", "1 May 1990", "1.", "First",
                       "Guest:", "Their Song", "5.", "Fifth"]
    assert [s.position for s in _songs_of(out_of_sequence)] == [1]


def test_lineup_and_section_labels_are_not_guest_headers():
    assert _is_guest_header("Tom Petty & The Heartbreakers:")
    assert _is_guest_header("Rob Stoner :")
    assert not _is_guest_header("Bob Dylan (vocal & guitar) with Tom Petty & The Heartbreakers:")
    assert not _is_guest_header("BobTalk:")
    assert not _is_guest_header("x" * 61 + ":")


def test_bobtalk_and_references_lines_are_not_position_lists():
    lines = ["Venue", "City, Sweden", "1 May 1990", "1.", "First", "2.", "Second",
             "BobTalk", "2 years ago I wrote this.", "References",
             "1 day in the life. Book 1990.", "Official releases", "1 released on X."]
    songs = _songs_of(lines)
    assert songs[0].annotations == "" and songs[1].annotations == ""
    assert songs[0].released_on == "X"


def test_release_lines_after_bobtalk_survive_the_section_guard():
    # Modelled on DSN00100 / 1961-11-04: "Unauthorized releases" isn't a section label,
    # and DSN12490 puts per-song recording ranges straight after BobTalk.
    lines = ["Venue", "City, Sweden", "1 May 1990", "1.", "First", "2.", "Second",
             "BobTalk", "Thank you.", "Unauthorized releases",
             "1 released on Y.", "Notes", "2 is also called Omie Wise.",
             "BobTalk:", "Thanks.", "1- 2 stereo PA recording."]
    songs = _songs_of(lines)
    assert songs[0].released_on == "Y"
    assert songs[1].annotations == "is also called Omie Wise; stereo PA recording"


# --- C03: P1b date lines, P1c venue-history lists, P1d rotation stat ----------------------

_HEAD = ["Zepp Tokyo", "Tokyo, Japan", "29 March 2010"]


def _event_of(trailer: list[str], n_songs: int = 28) -> tuple[EventRecord, list[SongRecord]]:
    lines = _HEAD + _numbered([f"Song {n}" for n in range(1, n_songs + 1)]) + trailer
    return _parse_event(lines, 1, "p1", "")


# Modelled on DSN32000 / 2010-03-29: the Tokyo list and the stat inside Notes.
_TOKYO = ["Other Bob Dylan shows in Tokyo, Japan:",
          "20 February 1978", "Nippon Budokan Hall",
          "1 March 1978", "Nippon Budokan Hall",
          "9 February 1997", 'Hall "A", Tokyo International Forum',
          "21 March 2010", "Zepp Tokyo"]
_STAT_2010 = "13 new songs (72%) compared to previous concert. 2 new songs for this tour."


def test_tokyo_list_and_stat_leave_notes_2010_03_29():
    rec, songs = _event_of(["Notes.", *_TOKYO, _STAT_2010,
                            "Stereo audience recording, 125 minutes."])
    assert (rec.rotation_new, rec.rotation_pct, rec.tour_new_count) == (13, 72, 2)
    assert rec.venue_history_raw == "\n".join(_TOKYO)
    assert rec.notes == ""
    assert all(s.annotations == "" for s in songs)  # no "March 1978" on songs 1, 9, 13, 20, 21
    assert rec.recording_mins == 125


def test_venue_list_entry_shapes():
    blob = ["Other Bob Dylan concerts in Birmingham, England:",
            "12-13 May 1995", "The Joint",
            "Late September 1961", "Gerde's Folk City",
            "8 maj 1984", "St Andrews",
            "3 May 1976 (2 shows)", "The Warehouse",
            "23 May 1992 Civic Centre",
            "4 April 2016 - Afternoon", "Orchard Hall"]
    rec, songs = _event_of(["Notes.", "First performance of Song 2.", *blob,
                            "Same setlist as previous concert."])
    assert rec.venue_history_raw == "\n".join(blob)
    assert rec.notes == "First performance of Song 2.\nSame setlist as previous concert."
    assert all(s.annotations == "" for s in songs)


def test_stat_and_list_header_on_one_line():
    # DSN37540: the stat and the next list's header share a paragraph.
    rec, _ = _event_of(["Notes.", "No new songs compared to previous concert. No new songs for"
                        " this tour. Previous Bob Dylan concerts in San Diego, California:",
                        "12 June 1990", "Open Air Theatre"])
    assert (rec.rotation_new, rec.rotation_pct, rec.tour_new_count) == (0, 0, 0)
    assert rec.venue_history_raw == (
        "Previous Bob Dylan concerts in San Diego, California:\n12 June 1990\nOpen Air Theatre")
    assert rec.notes == ""


def test_pointer_header_without_a_list_stays_in_notes():
    rec, _ = _event_of(["Notes.", "Bob Dylan concerts in London, England .",
                        "First Bob Dylan concert in Taormina, Italy."])
    assert rec.venue_history_raw == ""
    assert rec.notes == ("Bob Dylan concerts in London, England .\n"
                         "First Bob Dylan concert in Taormina, Italy.")


@pytest.mark.parametrize("stat, want, rest", [
    ("No new songs compared to previous concert. No new songs for this tour. Same setlist as"
     " 21 June.", (0, 0, 0), "Same setlist as 21 June."),
    ("1 new song (3%) compared to previous conc ert. 1 new song for this tour.", (1, 3, 1), ""),
    ("1 new song (3%) compared to previous concert. Probably 1 new song for this tour.",
     (1, 3, None), ""),
    ("4 new songs (13%) compared to previous concert. 2 possible new songs for this tour.",
     (4, 13, None), ""),
    ("Only 2 new songs (10%) compared to previous concert!! No new songs (0%) for this tour.",
     (2, 10, 0), ""),
    ("new songs (50%) compared to previous concert. 1 new song for this tour.", (None, 50, 1), ""),
    ("No new songs compared to previous concert! Exactly the same set list as last concert!",
     (0, 0, None), "Exactly the same set list as last concert!"),
])
def test_rotation_stat_variants(stat, want, rest):
    rec, songs = _event_of(["Notes.", stat])
    assert (rec.rotation_new, rec.rotation_pct, rec.tour_new_count) == want
    assert rec.notes == rest
    assert all(s.annotations == "" for s in songs)


def test_stat_halves_on_separate_lines_outside_any_section():
    # DSN4100: no Notes label, so the lines used to become annotations on songs 3 and 10.
    rec, songs = _event_of(["3 new songs (10%) compared to previous concert.",
                            "3 new songs for this tour.", "5 harmonica."])
    assert (rec.rotation_new, rec.rotation_pct, rec.tour_new_count) == (3, 10, 3)
    assert {s.position: s.annotations for s in songs if s.annotations} == {5: "harmonica"}


def test_stat_in_a_bobtalk_section_is_lifted_too():
    rec, _ = _event_of(["BobTalk", "Thank you.", _STAT_2010])
    assert rec.rotation_new == 13 and rec.bobtalk == "Thank you."


@pytest.mark.parametrize("text, want", [
    # 1965-06-01 and 2010-03-29: Olof's alternate titles are subtitles, not credits.
    ("It's Alright, Ma (I'm Only Bleeding)", ("It's Alright, Ma", "", "I'm Only Bleeding")),
    ("Most Likely You Go Your Way (And I’ll Go Mine)",
     ("Most Likely You Go Your Way", "", "And I’ll Go Mine")),
    ("High Water (For Charley Patton)", ("High Water", "", "For Charley Patton")),
    # A composer marker makes a credit whatever its length.
    ("Melancholy Mood (Walter Schumann & Vick R. Knight Sr.)",
     ("Melancholy Mood", "Walter Schumann & Vick R. Knight Sr.", "")),
    ("My Wife's Home Town (Bob Dylan-Robert Hunter/Wille Dixon & Bob Dylan)",
     ("My Wife's Home Town", "Bob Dylan-Robert Hunter/Wille Dixon & Bob Dylan", "")),
    ("Dink's Song (trad. arr. by John & Alan Lomax)",
     ("Dink's Song", "trad. arr. by John & Alan Lomax", "")),
    # Single-writer credits have no marker and stay credits (C01 caution).
    ("I'm Moving On (Hank Snow)", ("I'm Moving On", "Hank Snow", "")),
    ("Uranium Rock (Warren Smith)", ("Uranium Rock", "Warren Smith", "")),
    # A long parenthetical with no marker is part of the title.
    ("I Don't Believe You (She Acts Like We Never Have Met)",
     ("I Don't Believe You (She Acts Like We Never Have Met)", "", "")),
    ("Forever Young", ("Forever Young", "", "")),
])
def test_title_credits_and_subtitle(text, want):
    assert _split_title_parts(text) == want


def test_bobserve_and_chronicle_split_is_unchanged():
    assert _split_title_credits("Melancholy Mood (Walter Schumann & Vick R. Knight Sr.)") == (
        "Melancholy Mood (Walter Schumann & Vick R. Knight Sr.)", "")


def _releases(trailer: list[str], n_songs: int = 25) -> dict[int, str]:
    return {s.position: s.released_on for s in _event_of(trailer, n_songs)[1] if s.released_on}


def test_and_part_of_marks_a_partial_release_1986_02_24():
    got = _releases(["4, 9, 12, 15, 16 and part of 22 released on the commercial video HARD TO"
                     " HANDLE, CBS/FOX 3502 , October 1986."])
    video = "the commercial video HARD TO HANDLE, CBS/FOX 3502 , October 1986"
    assert got == {4: video, 9: video, 12: video, 15: video, 16: video, 22: "(part) " + video}


def test_or_marks_only_its_neighbours_uncertain():
    got = _releases(["1 or 2, 10 or 11, 12 and 15 released on X."])
    assert got == {1: "(uncertain) X", 2: "(uncertain) X", 10: "(uncertain) X",
                   11: "(uncertain) X", 12: "X", 15: "X"}


def test_release_wording_variants():
    got = _releases(["5 released in remastered version on Y.", "6 partly released on W.",
                     "3 digitally released on Z.", "7 available as a download from V.",
                     "20 released on 3 CD box set DYLAN."])
    assert got == {5: "released in remastered version on Y", 6: "(part) W",
                   3: "digitally released on Z", 7: "available as a download from V",
                   20: "3 CD box set DYLAN"}
    assert all(s.annotations == "" for s in _event_of(["5 released in mono on Y."])[1])


def test_date_lines_are_not_position_lists():
    rec, songs = _event_of(["Notes.", "1 March 1978", "12-13 May 1995",
                            "1-7 circulated 1986.", "4 Bob Dylan harmonica."])
    by_pos = {s.position: s.annotations for s in songs if s.annotations}
    assert by_pos == {1: "circulated 1986", 2: "circulated 1986", 3: "circulated 1986",
                      4: "circulated 1986; Bob Dylan harmonica", 5: "circulated 1986",
                      6: "circulated 1986", 7: "circulated 1986"}
