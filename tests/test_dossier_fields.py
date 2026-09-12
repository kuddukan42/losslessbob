"""Tests for backend.dossier_fields (TODO-342 D-01 track matcher) and the C13
``_ENTRY_TRACK_MARKER_RE`` fix in backend.db. Pure functions — no DB needed."""
import json
import sqlite3

import pytest

from backend import db, dossier_fields
from backend.dossier_fields import (
    anchor_bobtalk,
    broadcast_set_labels,
    build_setlist_index,
    clean_track_title,
    compare_sources,
    completeness,
    family_basis,
    fits_show,
    instrument_tally,
    is_non_song,
    lineage_short,
    match_track,
    parse_band_lineup,
    parse_entry_tracklist,
    parse_runtime,
    song_instruments,
    song_writers,
    source_character,
    taper_render,
)


class TestMarkerSplit:
    def test_glued_markers_split(self):
        text = ("9. The Levee's Gonna Break, 10.When The Deal Goes Down,"
                " 11.Highway 61 Revisited, 12.Can't Wait,")
        assert db.parse_entry_setlist_titles(text) == [
            "The Levee's Gonna Break", "When The Deal Goes Down",
            "Highway 61 Revisited", "Can't Wait",
        ]

    def test_embedded_numbers_stay_intact(self):
        text = ("1. Highway 61 Revisited, 2. Positively 4th Street,"
                " 3. Rainy Day Women Nos. 12 & 35")
        assert db.parse_entry_setlist_titles(text) == [
            "Highway 61 Revisited", "Positively 4th Street", "Rainy Day Women Nos. 12 & 35",
        ]

    def test_decimal_and_time_do_not_split(self):
        assert db.parse_entry_setlist_titles("1. Song A, 12.5 minutes, 2. Song B") == [
            "Song A, 12.5 minutes", "Song B",
        ]


class TestCleanTrackTitle:
    @pytest.mark.parametrize("raw,expected", [
        ("Soon After Midnight [04:32.44]", "Soon After Midnight"),
        ("Cold Irons Bound (5:21)", "Cold Irons Bound"),
        ("Tell Me 04:03, 30:21", "Tell Me"),
        ("Cold Irons Bound 6:07", "Cold Irons Bound"),
        ("Refugee [Petty]", "Refugee"),
        ("Masters Of War (Live)", "Masters Of War"),
        ("Tangled Up In Blue*", "Tangled Up In Blue"),
        ("Tangled Up In Blue *", "Tangled Up In Blue"),
        ("Honest With Me, Disc 2:", "Honest With Me"),
        ("Highway 61 Revisited, Disc Two", "Highway 61 Revisited"),
        ("God Knows\nCD 2", "God Knows"),
        ("Love Sick, Second Show:", "Love Sick"),
        ("It Ain't Me Babe, Second Broadcast: June 19th 1965", "It Ain't Me Babe"),
        ("Ballad Of Hollis Brown, First Broadcast: June 26th 1965", "Ballad Of Hollis Brown"),
        ("Summer Days 10:01, -Encore-", "Summer Days"),
        ("It's Alright, Ma (I'm Only Bleeding) (acoustic)",
         "It's Alright, Ma (I'm Only Bleeding)"),
        ("Highway 61 Revisited", "Highway 61 Revisited"),
        ("Positively 4th Street", "Positively 4th Street"),
        ("Rainy Day Women Nos. 12 & 35", "Rainy Day Women Nos. 12 & 35"),
        ("Not Fade Away", "Not Fade Away"),
        ("Clean Cut Kid", "Clean Cut Kid"),
    ])
    def test_cleans(self, raw, expected):
        assert clean_track_title(raw) == expected

    @pytest.mark.parametrize("raw", [
        "Introduction", "intro [1:03]", "band introduction [00:41]", "Band Intros",
        "-encore break-", "(encore)", "Applause", "Tuning", "crowd noise", "audience",
        "Audience (Bob - Minasan Arigato), Intermission, 2nd Set", "Disc 2:", "", None,
    ])
    def test_non_songs_are_none(self, raw):
        assert clean_track_title(raw) is None

    def test_is_non_song_keeps_real_titles(self):
        assert not is_non_song("Intro To Highway 61")  # 'highway' is not filler
        assert not is_non_song("Not Fade Away")
        assert is_non_song("band member introductions")


class TestParseEntryTracklist:
    def test_partial_flags(self):
        tracks = parse_entry_tracklist(
            "1. London Calling (incomplete), 2. Girl Of The North Country (cut),"
            " 3. Idiot Wind (fades out), 4. She Belongs To Me (beginning cut),"
            " 5. Not Fade Away, 6. Clean Cut Kid"
        )
        assert [t["partial"] for t in tracks] == [True, True, True, True, False, False]
        assert [t["title"] for t in tracks][:2] == ["London Calling", "Girl Of The North Country"]
        assert not any(t["missing"] for t in tracks)

    def test_missing_flags_lb08855_shape(self):
        text = (
            "First Broadcast: June 26th 1965, 01. Ballad Of Hollis Brown,"
            " 02. Mr Tambourine Man, missing, 03. If You Gotta Go, Go Now, missing,"
            " 04. It Ain't Me Babe, Second Broadcast: June 19th 1965,"
            " 05. Love Minus Zero/No Limit"
        )
        tracks = parse_entry_tracklist(text)
        assert [t["title"] for t in tracks] == [
            "Ballad Of Hollis Brown", "Mr Tambourine Man", "If You Gotta Go, Go Now",
            "It Ain't Me Babe", "Love Minus Zero/No Limit",
        ]
        assert [t["missing"] for t in tracks] == [False, True, True, False, False]
        assert all(t["is_song"] for t in tracks)

    def test_paren_missing_and_missing_end(self):
        tracks = parse_entry_tracklist("1. Soon After Midnight (missing), 2. Isis (missing end)")
        assert tracks[0]["missing"] and not tracks[0]["partial"]
        assert tracks[1]["partial"] and not tracks[1]["missing"]

    def test_introduction_is_not_a_song(self):
        tracks = parse_entry_tracklist("0. Introduction, 1. Rainy Day Women #12 & 35")
        assert tracks[0] == {
            "raw": "Introduction", "title": None, "is_song": False,
            "partial": False, "missing": False,
        }
        assert tracks[1]["is_song"]

    def test_empty(self):
        assert parse_entry_tracklist("") == []
        assert parse_entry_tracklist(None) == []


class TestMatchTrack:
    def test_exact(self):
        m = match_track("Mr Tambourine Man", ["Gates Of Eden", "Mr. Tambourine Man"])
        assert m == {"candidate": "Mr. Tambourine Man", "tier": "exact"}

    def test_exact_ignores_spacing(self):
        m = match_track("My Wife's Hometown", ["My Wife's Home Town"])
        assert m == {"candidate": "My Wife's Home Town", "tier": "exact"}

    def test_exact_folds_talkin(self):
        m = match_track("T.V. Talkin' Song", ["T.V. Talking Song"])
        assert m == {"candidate": "T.V. Talking Song", "tier": "exact"}

    def test_exact_number_word(self):
        m = match_track("Rainy Day Women Nos. 12 & 35", ["Rainy Day Women # 12 & 35"])
        assert m["tier"] == "exact"

    def test_without_subtitle(self):
        m = match_track("It's Alright Ma (I'm Only Bleeding)", ["It's Alright, Ma"])
        assert m == {"candidate": "It's Alright, Ma", "tier": "base"}

    def test_alias(self):
        cmap = {"girl of the north country": "Girl From The North Country"}
        m = match_track("Girl Of The North Country", ["Girl From The North Country"], cmap)
        assert m == {"candidate": "Girl From The North Country", "tier": "alias"}
        assert match_track("Girl Of The North Country", ["Girl From The North Country"]) is None

    def test_containment(self):
        m = match_track("Most Likely You Go Your Way And I'll Go Mine",
                        ["Most Likely You Go Your Way"])
        assert m == {"candidate": "Most Likely You Go Your Way", "tier": "contains"}

    def test_no_match(self):
        assert match_track("Tombstone Blues", ["Desolation Row"]) is None
        assert match_track(None, ["Desolation Row"]) is None
        assert match_track("Desolation Row", []) is None

    def test_prebuilt_index(self):
        index = build_setlist_index(["Desolation Row", "", "Cold Irons Bound"])
        assert index.titles == ["Desolation Row", "Cold Irons Bound"]
        assert match_track("Cold Irons Bound", index)["candidate"] == "Cold Irons Bound"


class TestCleanTrackTitleC17:
    @pytest.mark.parametrize("raw,expected", [
        ("(encore break)", None),
        ("(2nd encore break)", None),
        ("Forever Young, Encore 1", "Forever Young"),
        ("All Along The Watchtower, Encore 2", "All Along The Watchtower"),
        ("Jolene / Band Intro", "Jolene"),
        ("Love Minus Zero/No Limit", "Love Minus Zero/No Limit"),
    ])
    def test_c17_gaps(self, raw, expected):
        assert clean_track_title(raw) == expected


class TestFitsShow:
    def test_misdated_compilation_does_not_fit(self):
        assert not fits_show(25, 0, 12, 0, glued=False)

    def test_short_excerpt_always_fits(self):
        assert fits_show(2, 0, 12, 0, glued=False)

    def test_share_threshold(self):
        assert fits_show(5, 1, 12, 1, glued=False)      # 20% exactly
        assert not fits_show(6, 1, 12, 1, glued=False)  # 16%

    def test_superset_of_setlist_fits(self):
        assert fits_show(40, 4, 7, 4, glued=False)

    def test_glued_fits(self):
        assert fits_show(25, 0, 12, 0, glued=True)


def _completeness_db(tuit_setlist_json=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, song_title TEXT,
                                 subtitle TEXT);
        CREATE TABLE entries (lb_number INTEGER, setlist TEXT, timing TEXT);
        CREATE TABLE tuit_recordings (rec_id INTEGER PRIMARY KEY, lb_number INTEGER,
                                      setlist_json TEXT);
    """)
    songs = ["Ballad Of Hollis Brown", "Mr. Tambourine Man", "Gates Of Eden",
             "Unidentified Instrumental", "She Belongs To Me", "Mr. Tambourine Man"]
    conn.executemany(
        "INSERT INTO olof_songs VALUES (1, ?, ?, '')", list(enumerate(songs, start=1)))
    conn.executemany("INSERT INTO entries VALUES (?, ?, ?)", [
        (10, "1. Ballad Of Hollis Brown, 2. Mr Tambourine Man, missing,"
             " 3. Gates Of Eden (incomplete), 4. She Belongs To Me", "40min"),
        (11, "1. Mr Tambourine Man, 2. Mr Tambourine Man (reprise)", "10min"),
        (12, "1. Like A Rolling Stone, 2. Tombstone Blues, 3. Desolation Row", ""),
        (13, "", "60min"),
    ])
    if tuit_setlist_json is not None:
        conn.execute(
            "INSERT INTO tuit_recordings (lb_number, setlist_json) VALUES (10, ?)",
            (tuit_setlist_json,),
        )
    return conn


class TestCompleteness:
    def test_positions_missing_partial(self):
        res = completeness(_completeness_db(), 1, [10], canonical_map={})[10]
        # Placeholder "Unidentified Instrumental" isn't a setlist song: total 5.
        assert (res["basis"], res["songs_present"], res["songs_total"]) == ("tracklist", 3, 5)
        assert [m["position"] for m in res["missing"]] == [2, 6]
        assert res["partial"] == [3]
        assert res["confidence"] == "stated" and res["fits_show"] and res["show_bar"]

    def test_repeated_song_fills_both_positions(self):
        res = completeness(_completeness_db(), 1, [11], canonical_map={})[11]
        assert res["songs_present"] == 2
        assert [m["position"] for m in res["missing"]] == [1, 3, 5]

    def test_misdated_source_leaves_verdict(self):
        res = completeness(_completeness_db(), 1, [12], canonical_map={})[12]
        assert res["songs_present"] == 0 and not res["fits_show"] and not res["show_bar"]
        assert res["extra"] == ["Like A Rolling Stone", "Tombstone Blues", "Desolation Row"]

    def test_runtime_basis_never_infers(self):
        res = completeness(_completeness_db(), 1, [13, 99], canonical_map={})
        assert 99 not in res
        assert res[13]["basis"] == "runtime" and res[13]["songs_present"] is None
        assert not res[13]["show_bar"]

    def test_tuit_agreeing_count_corroborates(self):
        tuit = json.dumps([{"song": s} for s in
                           ("Ballad Of Hollis Brown", "Gates Of Eden", "She Belongs To Me")])
        res = completeness(_completeness_db(tuit), 1, [10], canonical_map={})[10]
        assert (res["confidence"], res["tuit_present"]) == ("corroborated", 3)

    def test_tuit_different_count_is_inferred_and_hides_bar(self):
        tuit = json.dumps([{"song": "Ballad Of Hollis Brown"}])
        res = completeness(_completeness_db(tuit), 1, [10], canonical_map={})[10]
        assert (res["confidence"], res["tuit_present"], res["show_bar"]) == ("inferred", 1, False)

    def test_tuit_empty_list_is_no_tracklist(self):
        res = completeness(_completeness_db("[]"), 1, [10], canonical_map={})[10]
        assert (res["confidence"], res["tuit_present"]) == ("stated", None)


# ---------------------------------------------------------------------------
# C23 Supporting parsers
# ---------------------------------------------------------------------------

class TestBandLineup:
    def test_numbered_band_index_and_label(self):
        lineup = (
            "First concert with the first Never-Ending Tour Band: Bob Dylan"
            " (vocal & guitar), G. E. Smith (guitar), Kenny Aaronson (bass),"
            " Christopher Parker (drums).; 7-9 Bob Dylan (vocal & guitar),"
            " G.E. Smith (guitar).; 11 Bob Dylan (harmonica)."
        )
        band = parse_band_lineup(lineup)
        assert band["band_index"] == 1
        assert band["band_label"] == "First Never-Ending Tour Band"
        assert [m["name"] for m in band["members"]] == [
            "Bob Dylan", "G. E. Smith", "Kenny Aaronson", "Christopher Parker",
        ]
        assert band["members"][0]["instruments"] == "vocal & guitar"

    def test_numeric_ordinal_and_no_the(self):
        lineup = "Concert # 4 with 21st Never-Ending Tour band: Bob Dylan (vocal & guitar)."
        band = parse_band_lineup(lineup)
        assert (band["band_index"], band["band_label"]) == (21, "21st Never-Ending Tour Band")

    def test_solo_lineup(self):
        band = parse_band_lineup("Bob Dylan (solo, vocal, harmonica & acoustic guitar). .")
        assert band["band_label"] == "Solo"
        assert band["band_index"] is None
        assert band["members"] == [
            {"name": "Bob Dylan", "instruments": "solo, vocal, harmonica & acoustic guitar"},
        ]

    def test_dylan_alone_without_the_word_solo(self):
        band = parse_band_lineup("Bob Dylan (vocal & guitar).")
        assert band["band_label"] == "Solo"
        assert band["band_index"] is None

    def test_unparenthesised_band_name_is_not_solo(self):
        band = parse_band_lineup(
            "Bob Dylan (vocal & guitar) with Tom Petty & The Heartbreakers."
        )
        assert band["band_label"] is None

    def test_dylan_moved_first(self):
        lineup = "Joe Sideman (bass), Bob Dylan (vocal & guitar)."
        band = parse_band_lineup(lineup)
        assert band["members"][0]["name"] == "Bob Dylan"

    def test_unrecognised_lineup_omits(self):
        band = parse_band_lineup("Bob Dylan (vocal & guitar) with Tom Petty & The Heartbreakers")
        assert band["band_index"] is None
        assert band["band_label"] is None

    def test_blank_lineup(self):
        assert parse_band_lineup(None) == {"band_index": None, "band_label": None, "members": []}


class TestSongInstrumentsAndTally:
    _LINEUP = (
        "First concert with the first Never-Ending Tour Band: Bob Dylan"
        " (vocal & guitar), G. E. Smith (guitar), Kenny Aaronson (bass),"
        " Christopher Parker (drums).; 7-9 Bob Dylan (vocal & guitar),"
        " G.E. Smith (guitar).; 11 Bob Dylan (harmonica)."
    )

    def test_uncovered_song_omits_base_lineup(self):
        # No "otherwise" generalisation (audit M13): position 1 has no per-song
        # or range clause, so song.instruments is None, not the base personnel.
        assert song_instruments(self._LINEUP, 1) is None

    def test_range_clause_covers_its_positions(self):
        assert song_instruments(self._LINEUP, 8) == \
            "Bob Dylan (vocal & guitar), G.E. Smith (guitar)"

    def test_per_song_clause(self):
        assert song_instruments(self._LINEUP, 11) == "Bob Dylan (harmonica)"

    def test_tally_counts_songs_not_mentions(self):
        # Positions 7-9 each contribute one "guitar" tally (two names mention
        # guitar in that clause, but it's one song); position 11 contributes
        # one "harp" (canonical name for "harmonica").
        tally = instrument_tally(self._LINEUP, song_count=14)
        assert tally == {"vocal": 3, "guitar": 3, "harp": 1}

    def test_tally_never_generalises_base_lineup(self):
        # The base clause's bass/drums never appear -- only override clauses count.
        tally = instrument_tally(self._LINEUP, song_count=14)
        assert "bass" not in tally and "drums" not in tally

    def test_blank_lineup_no_instruments(self):
        assert song_instruments(None, 1) is None
        assert instrument_tally(None, song_count=5) == {}


def _corrections_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, song_title TEXT,
                                  credits TEXT);
        CREATE TABLE corrections (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_kind TEXT,
                                   entity_key TEXT, field TEXT, original TEXT, corrected TEXT);
    """)
    conn.execute(
        "INSERT INTO olof_songs VALUES (1, 1, 'Earth Angel', 'Dootsie Williams')",
    )
    conn.execute(
        "INSERT INTO olof_songs VALUES (1, 2, 'Blowin In The Wind', '')",
    )
    return conn


class TestSongWriters:
    def test_uncorrected_credit(self):
        w = song_writers(_corrections_db(), 1, 1)
        assert w == {"value": "Dootsie Williams", "corrected": False, "original": None}

    def test_dylan_original_omits(self):
        w = song_writers(_corrections_db(), 1, 2)
        assert w["value"] is None

    def test_correction_applied_with_original(self):
        conn = _corrections_db()
        conn.execute(
            "INSERT INTO corrections (entity_kind, entity_key, field, original, corrected)"
            " VALUES ('olof_song', '1:1', 'credits', 'Dootsie Williams', 'Curtis Williams')",
        )
        w = song_writers(conn, 1, 1)
        assert w == {"value": "Curtis Williams", "corrected": True, "original": "Dootsie Williams"}


def _broadcast_labels_db(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, annotations TEXT);"
    )
    conn.executemany(
        "INSERT INTO olof_songs VALUES (1, ?, ?)", list(enumerate(rows, start=1)),
    )
    return conn


class TestBroadcastSetLabels:
    def test_contiguous_range_becomes_band(self):
        conn = _broadcast_labels_db([
            "", "", "broadcast by BBC TV-1", "broadcast by BBC TV-1", "broadcast by BBC TV-1", "",
        ])
        labels, notes = broadcast_set_labels(conn, 1)
        assert labels == [{"kind": "band", "text": "broadcast by BBC TV-1", "positions": [3, 4, 5]}]
        assert notes == []

    def test_noncontiguous_becomes_markers(self):
        conn = _broadcast_labels_db([
            "broadcast by WMAI", "", "broadcast by WMAI", "",
        ])
        labels, notes = broadcast_set_labels(conn, 1)
        assert labels == [
            {"kind": "marker", "text": "broadcast by WMAI", "positions": [1]},
            {"kind": "marker", "text": "broadcast by WMAI", "positions": [3]},
        ]
        assert notes == []

    def test_whole_show_note_is_session_note(self):
        conn = _broadcast_labels_db(["radio broadcast", "radio broadcast", "radio broadcast"])
        labels, notes = broadcast_set_labels(conn, 1)
        assert labels == []
        assert notes == ["radio broadcast"]

    def test_no_broadcast_notes(self):
        conn = _broadcast_labels_db(["", "", ""])
        assert broadcast_set_labels(conn, 1) == ([], [])


def _character_db(verdict_text=None, source_chain=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE quality_recording_scores (lb_number INTEGER, scan_id INTEGER,
            final_score REAL, rank_in_family INTEGER, vetoed INTEGER, verdict_text TEXT);
        CREATE TABLE entries (lb_number INTEGER, source_chain TEXT);
    """)
    if verdict_text is not None:
        conn.execute(
            "INSERT INTO quality_recording_scores VALUES (1, 1, 90.0, 1, 0, ?)", (verdict_text,),
        )
    conn.execute("INSERT INTO entries VALUES (1, ?)", (source_chain,))
    return conn


class TestSourceCharacter:
    def test_strips_prefix_and_splits_flags(self):
        text = (
            "Grade B+ (74/100). LB1: ranked #2 of 2. Sounds clean, close / direct, and"
            " present vocals. Flags: has dropouts/glitches and incomplete (missing material)."
        )
        sc = source_character(_character_db(text, "mic > recorder"), 1)
        assert sc["character"] == "clean, close / direct, and present vocals"
        assert sc["flags"] == ["has dropouts/glitches", "incomplete (missing material)"]

    def test_no_flags_keeps_trailer_sentences(self):
        text = "LB1: Sounds bright / airy, clean. Best in group for transient clarity."
        sc = source_character(_character_db(text, "mic > recorder"), 1)
        assert sc["character"] == "bright / airy, clean. Best in group for transient clarity"
        assert sc["flags"] == []

    def test_empty_source_chain_flags_no_lineage(self):
        sc = source_character(_character_db("LB1: Sounds clean.", ""), 1)
        assert "no lineage on file" in sc["flags"]

    def test_no_verdict_text(self):
        sc = source_character(_character_db(None, "mic > recorder"), 1)
        assert sc["character"] is None
        assert sc["flags"] == []


class TestLineageShort:
    def test_cuts_before_extraction_hop(self):
        chain = "CSHEB w/ bass roll-off active > M1, trade cdr > eac > wav > shn"
        assert lineage_short(chain) == "CSHEB w/ bass roll-off active > M1, trade cdr"

    def test_cuts_before_codec_hop(self):
        assert lineage_short("Neumann KM140 > Sonosax > TCD-D8 > CDR > SHN") == \
            "Neumann KM140 > Sonosax > TCD-D8 > CDR"

    def test_no_hop_returns_whole_chain(self):
        assert lineage_short("AUD DAT-2") == "AUD DAT-2"

    def test_blank_chain(self):
        assert lineage_short(None) is None
        assert lineage_short("") is None

    def test_hardware_named_wave_is_not_a_hop(self):
        # "WaveTerminal" is a soundcard, not the wav codec -- must not cut early.
        chain = "Sony TCD-D100 > Neumann KM 140 > Tascam DA-40 > WaveTerminal"
        assert lineage_short(chain) == chain


class TestParseRuntime:
    def test_split_sums_to_total(self):
        rt = parse_runtime("72min+69min+51min+41min")
        assert rt["parts"] == [72.0, 69.0, 51.0, 41.0]
        assert rt["total_minutes"] == sum(rt["parts"]) == 233.0

    def test_ignores_trailing_words(self):
        rt = parse_runtime("68min+31min+18min filler")
        assert rt["total_minutes"] == sum(rt["parts"]) == 117.0

    def test_single_segment(self):
        rt = parse_runtime("27min")
        assert rt["parts"] == [27.0]
        assert rt["total_minutes"] == sum(rt["parts"])

    def test_no_minute_token(self):
        assert parse_runtime("unknown") is None
        assert parse_runtime(None) is None
        assert parse_runtime("") is None

    @pytest.mark.parametrize("timing", [
        "72min+69min+51min+41min", "68min+31min", "45min", "70min, 37min", "78min +68min",
    ])
    def test_g5_invariant_holds_over_samples(self, timing):
        rt = parse_runtime(timing)
        assert rt["total_minutes"] == sum(rt["parts"])


def _family_db(conf=0.9, by="ai+lb", lb_numbers=(10, 11), abs_scores=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE tapematch_family_meta (fam_id TEXT PRIMARY KEY, conf REAL, by TEXT);
        CREATE TABLE recording_families (lb_number INTEGER, fam_id TEXT);
        CREATE TABLE quality_recording_scores (lb_number INTEGER, scan_id INTEGER,
            abs_score REAL, abs_grade TEXT);
    """)
    conn.execute("INSERT INTO tapematch_family_meta VALUES ('fam1', ?, ?)", (conf, by))
    conn.executemany(
        "INSERT INTO recording_families VALUES (?, 'fam1')", [(lb,) for lb in lb_numbers],
    )
    for lb, scan_id, score, grade in (abs_scores or []):
        conn.execute(
            "INSERT INTO quality_recording_scores VALUES (?, ?, ?, ?)", (lb, scan_id, score, grade),
        )
    return conn


class TestFamilyBasis:
    def test_correlation_and_lb_page_note(self):
        conn = _family_db(conf=0.87, by="ai+lb")
        fb = family_basis(conn, "fam1")
        assert fb["conf"] == 0.87
        assert fb["notes"] == ["waveform correlation mean 0.87", "LB page states same source"]

    def test_ai_only_no_lb_note(self):
        conn = _family_db(conf=0.99, by="ai")
        fb = family_basis(conn, "fam1")
        assert fb["notes"] == ["waveform correlation mean 0.99"]

    def test_quality_match_note(self):
        conn = _family_db(
            conf=0.5, by="ai", lb_numbers=(10, 11),
            abs_scores=[(10, 1, 80.0, "B+"), (11, 1, 80.2, "B+")],
        )
        fb = family_basis(conn, "fam1")
        assert "quality score match" in fb["notes"]

    def test_unknown_family(self):
        conn = _family_db()
        assert family_basis(conn, "no-such-fam") == {"fam_id": "no-such-fam", "conf": None,
                                                        "notes": []}


def _taper_db(attribution=None, blocked_rules=(), conflict=0):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE taper_attributions (lb_number INTEGER PRIMARY KEY, taper_normalised TEXT,
            confidence TEXT, conflict INTEGER);
        CREATE TABLE qc_findings (rule_id TEXT, entity_kind TEXT, entity_key TEXT,
            status TEXT);
    """)
    if attribution is not None:
        name, confidence = attribution
        conn.execute(
            "INSERT INTO taper_attributions VALUES (1, ?, ?, ?)", (name, confidence, conflict),
        )
    for rule in blocked_rules:
        conn.execute(
            "INSERT INTO qc_findings VALUES (?, 'lb', '1', 'open')", (rule,),
        )
    return conn


class TestTaperRender:
    def test_confirmed_renders_plainly(self):
        conn = _taper_db(attribution=("cb", "confirmed"))
        tr = taper_render(conn, 1)
        assert tr["name"] == "cb" and tr["marker"] is None

    def test_propagated_gets_inferred_marker(self):
        conn = _taper_db(attribution=("cb", "propagated"))
        tr = taper_render(conn, 1)
        assert tr["name"] == "cb" and tr["marker"] == "inferred"

    def test_missing_renders_nothing_never_unknown(self):
        conn = _taper_db(attribution=None)
        tr = taper_render(conn, 1)
        assert tr["name"] is None

    def test_conflict_renders_nothing(self):
        conn = _taper_db(attribution=("cb", "confirmed"), conflict=1)
        assert taper_render(conn, 1)["name"] is None

    def test_open_rt_error_blocks_render(self):
        conn = _taper_db(attribution=("cb", "confirmed"), blocked_rules=["R-T2"])
        tr = taper_render(conn, 1)
        assert tr["name"] is None and tr["confidence"] is None

    def test_open_rt4_warn_does_not_block(self):
        # R-T4 is a warn, not an error -- it surfaces as a disputed notice
        # elsewhere (via corroborate.taper_check), never blocks rendering.
        conn = _taper_db(attribution=("cb", "confirmed"), blocked_rules=["R-T4"])
        tr = taper_render(conn, 1)
        assert tr["name"] == "cb"


# ---------------------------------------------------------------------------
# D-08 compare_sources (C24)
# ---------------------------------------------------------------------------
#
# compare_sources() orchestrates five already-tested helpers (file_meta,
# classify_generation, source_character, completeness, and
# corroborate.file_format_check). Those helpers' own parsing logic is covered
# by their dedicated test classes/files above and in
# tests/test_setlist_confidence_file_meta.py and tests/test_generation_medium.py,
# so these tests monkeypatch them to plain stand-ins and focus on
# compare_sources' own orchestration: which axes count, when they tie, when an
# alternate is the pick's runner-up vs some other visible source, and collapse.

def _compare_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE entries (lb_number INTEGER PRIMARY KEY, rating TEXT,
            source_type TEXT, timing TEXT, status TEXT);
        CREATE TABLE show_picks (lb_number INTEGER, concert_date_iso TEXT,
            pick_rank INTEGER);
        CREATE TABLE quality_recording_scores (lb_number INTEGER, scan_id INTEGER,
            abs_score REAL, abs_grade TEXT);
    """)
    return conn


def _compare_seed(conn, rows, date_iso="2020-01-01"):
    """rows: (lb, rating, source_type, timing, rank, scan_or_None)."""
    for lb, rating, source_type, timing, rank, scan in rows:
        conn.execute(
            "INSERT INTO entries VALUES (?, ?, ?, ?, 'ok')", (lb, rating, source_type, timing),
        )
        conn.execute(
            "INSERT INTO show_picks VALUES (?, ?, ?)", (lb, date_iso, rank),
        )
        if scan is not None:
            conn.execute(
                "INSERT INTO quality_recording_scores VALUES (?, 1, ?, 'A')", (lb, scan),
            )


def _stub_helpers(monkeypatch, file_res=None, generation=None, character=None, complete=None):
    """Stub compare_sources' five DB-heavy dependencies with plain lookups.

    Args:
        file_res: ``{lb: "BIT/KHZ" | None}``, default no source has a file record.
        generation: ``{lb: (generation, basis)}``, default every source "unknown".
        character: ``{lb: str | None}``, default no character text anywhere.
        complete: ``{lb: bool}``, default no source is D-01 complete.
    """
    file_res = file_res or {}
    generation = generation or {}
    character = character or {}
    complete = complete or {}
    monkeypatch.setattr(
        dossier_fields, "file_meta", lambda c, lb: {"file_res": file_res.get(lb)},
    )
    monkeypatch.setattr(
        dossier_fields, "classify_generation",
        lambda c, lb: {"generation": generation.get(lb, ("unknown", None))[0],
                        "basis": generation.get(lb, ("unknown", None))[1]},
    )
    monkeypatch.setattr(
        dossier_fields, "source_character", lambda c, lb: {"character": character.get(lb)},
    )
    monkeypatch.setattr(
        dossier_fields, "completeness",
        lambda c, event_id, lbs, canonical_map=None: {
            lb: {"basis": "tracklist", "songs_total": 1, "songs_present": 1 if complete.get(lb) else 0}
            for lb in lbs
        },
    )
    monkeypatch.setattr(
        "backend.qc.corroborate.file_format_check", lambda c, lb: {"agrees": None},
    )


class TestCompareSources:
    def test_no_visible_sources_collapses(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[])
        assert cs == {"pick": None, "runner_up": None, "diffs": [], "alternates": [],
                      "collapsed": True}

    def test_single_visible_source_has_no_runner_up(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [(1, "A", None, "60min", 1, None)])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1])
        assert cs["pick"] == 1 and cs["runner_up"] is None and cs["collapsed"]

    def test_best_scan_alternate_need_not_be_the_runner_up(self, monkeypatch):
        # Mirrors the 2010-03-29 accept case: LB-08637 (pick_rank 3) beats the
        # pick's scan score, not LB-08476 (pick_rank 2, the runner-up).
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, 84.0),  # pick
            (2, "A", None, "59min", 2, 79.0),  # runner-up
            (3, "A", None, "58min", 3, 90.0),  # scan leader, not the runner-up
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2, 3])
        assert cs["pick"] == 1 and cs["runner_up"] == 2
        assert cs["alternates"] == [
            {"axis": "scan", "lb_number": 3, "pick_value": 84.0, "alt_value": 90.0},
        ]
        assert any(d["field"] == "scan" and d["leader"] == "pick" for d in cs["diffs"])
        assert not cs["collapsed"]

    def test_tied_scan_is_no_alternate(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, 84.0),
            (2, "A", None, "60min", 2, 84.0),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert cs["alternates"] == [] and cs["diffs"] == [] and cs["collapsed"]

    def test_resolution_needs_the_same_basis(self, monkeypatch):
        # Audit M17 (LB-08493 vs LB-08485/08476): a lineage-only figure never
        # competes against a file-record figure, even a higher one.
        _stub_helpers(monkeypatch, file_res={1: "16/44", 2: "16/44"})
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),  # pick: file record 16/44
            (2, "A", None, "60min", 2, None),  # ties the pick's file record
            (3, "A", None, "60min", 3, None),  # no file_meta entry -> no comparable basis
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2, 3])
        assert not any(a["axis"] == "resolution" for a in cs["alternates"])

    def test_higher_resolution_file_record_is_an_alternate(self, monkeypatch):
        _stub_helpers(monkeypatch, file_res={1: "16/44", 2: "16/44", 3: "24/96"})
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", None, "60min", 2, None),
            (3, "A", None, "60min", 3, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2, 3])
        assert {"axis": "resolution", "lb_number": 3, "pick_value": "16/44",
                "alt_value": "24/96"} in cs["alternates"]

    def test_small_runtime_gap_is_not_meaningful(self, monkeypatch):
        # A 1-minute gap between two minute-rounded timings can be the same length:
        # must not produce a diff or an alternate.
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "66min", 1, None),
            (2, "A", None, "67min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert cs["diffs"] == [] and cs["alternates"] == [] and cs["collapsed"]

    def test_two_minute_runtime_gap_is_an_alternate(self, monkeypatch):
        # The rounding floor (tj, 2026-09-12): 2 minutes can't be rounding alone.
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "66min", 1, None),
            (2, "A", None, "68min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert {"axis": "runtime", "lb_number": 2, "pick_value": 66.0,
                "alt_value": 68.0} in cs["alternates"]

    def test_large_runtime_gap_is_an_alternate(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", None, "70min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert cs["alternates"] == [
            {"axis": "runtime", "lb_number": 2, "pick_value": 60.0, "alt_value": 70.0},
        ]

    def test_only_soundboard_needs_a_single_source(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", "Soundboard", "60min", 2, None),
            (3, "A", "Soundboard", "60min", 3, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2, 3])
        # Two soundboards, so "only soundboard" doesn't hold for either.
        assert not any(a["axis"] == "soundboard" for a in cs["alternates"])

    def test_only_soundboard_alternate_when_unique(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", "Soundboard", "60min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert {"axis": "soundboard", "lb_number": 2, "pick_value": False,
                "alt_value": True} in cs["alternates"]

    def test_only_complete_alternate_when_unique(self, monkeypatch):
        _stub_helpers(monkeypatch, complete={2: True})
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", None, "60min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert {"axis": "complete", "lb_number": 2, "pick_value": False,
                "alt_value": True} in cs["alternates"]

    def test_unknown_generation_is_treated_as_null(self, monkeypatch):
        # classify_generation's "unknown" (basis None) never guesses -- it must
        # not surface as a real generation diff between pick and runner-up.
        _stub_helpers(monkeypatch, generation={1: ("unknown", None), 2: ("silver", "stated")})
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", None, "60min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert not any(d["field"] == "generation" for d in cs["diffs"])

    def test_differing_generation_is_reported_not_ranked(self, monkeypatch):
        _stub_helpers(monkeypatch, generation={1: ("master", "stated"), 2: ("low_gen", "stated")})
        conn = _compare_db()
        _compare_seed(conn, [
            (1, "A", None, "60min", 1, None),
            (2, "A", None, "60min", 2, None),
        ])
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        diff = next(d for d in cs["diffs"] if d["field"] == "generation")
        assert diff == {"field": "generation", "pick_value": "master",
                        "runner_value": "low_gen", "leader": None}

    def test_status_not_ok_is_excluded(self, monkeypatch):
        _stub_helpers(monkeypatch)
        conn = _compare_db()
        _compare_seed(conn, [(1, "A", None, "60min", 1, None)])
        conn.execute("INSERT INTO entries VALUES (2, 'A', NULL, '60min', 'private')")
        conn.execute("INSERT INTO show_picks VALUES (2, '2020-01-01', 2)")
        cs = compare_sources(conn, event_id=1, date_iso="2020-01-01", visible_lbs=[1, 2])
        assert cs["pick"] == 1 and cs["runner_up"] is None


# ---------------------------------------------------------------------------
# D-10 anchor_bobtalk (C24)
# ---------------------------------------------------------------------------

def _bobtalk_db(bobtalk_text, titles, event_id=1):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE olof_events (event_id INTEGER PRIMARY KEY, bobtalk TEXT);
        CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, song_title TEXT,
            subtitle TEXT);
    """)
    conn.execute("INSERT INTO olof_events VALUES (?, ?)", (event_id, bobtalk_text))
    conn.executemany(
        "INSERT INTO olof_songs VALUES (?, ?, ?, '')",
        [(event_id, i, t) for i, t in enumerate(titles, start=1)],
    )
    return conn


class TestAnchorBobtalk:
    def test_no_bobtalk_text_is_empty_both_ways(self):
        conn = _bobtalk_db("", [])
        bt = anchor_bobtalk(conn, 1)
        assert bt == {"event_id": 1, "anchored": [], "context": []}

    def test_simple_cue_resolves(self):
        line = (
            "How are you? Sometimes it's hard to find people who understand"
            " me. (before Trust Yourself)"
        )
        conn = _bobtalk_db(line, ["Trust Yourself"])
        bt = anchor_bobtalk(conn, 1)
        assert len(bt["anchored"]) == 1
        anchor = bt["anchored"][0]
        assert (anchor["position"], anchor["cue"], anchor["title"]) == \
            (1, "before", "Trust Yourself")
        assert bt["context"] == []

    def test_nested_parens_title_stays_whole(self):
        line = (
            "I don't know how to. If I did, I would. (before It's Alright, Ma"
            " (I'm Only Bleeding))"
        )
        conn = _bobtalk_db(line, ["It's Alright, Ma (I'm Only Bleeding)"])
        bt = anchor_bobtalk(conn, 1)
        assert len(bt["anchored"]) == 1
        assert bt["anchored"][0]["position"] == 1

    def test_hyphen_and_space_insensitive(self):
        line = "Thank you! The Queens of Rhythm! (after Clean-Cut Kid)"
        conn = _bobtalk_db(line, ["Clean Cut Kid"])
        bt = anchor_bobtalk(conn, 1)
        assert len(bt["anchored"]) == 1

    def test_unresolved_cue_stays_in_context(self):
        line = "Thank you. This next one you all know pretty well by now. (before Some Song)"
        conn = _bobtalk_db(line, ["Trust Yourself"])
        bt = anchor_bobtalk(conn, 1)
        assert bt["anchored"] == [] and bt["context"] == [line]

    def test_no_cue_stays_in_context(self):
        line = "Thank you very much everybody, we appreciate you all coming out tonight."
        conn = _bobtalk_db(line, ["Trust Yourself"])
        bt = anchor_bobtalk(conn, 1)
        assert bt["anchored"] == [] and bt["context"] == [line]

    def test_multiple_cues_in_one_line_resolve_independently(self):
        # One cue ("plays guitar") never resolves to a song; the other
        # ("after Masters of War") does -- the line still ends up anchored,
        # not duplicated into context.
        line = 'He says that aint being a hero. [plays guitar] (after "Masters of War")'
        conn = _bobtalk_db(line, ["Masters Of War"])
        bt = anchor_bobtalk(conn, 1)
        assert len(bt["anchored"]) == 1
        assert bt["anchored"][0]["cue"] == "after"
        assert bt["context"] == []

    def test_repeated_song_claims_cues_in_order(self):
        conn = _bobtalk_db(
            "Here's one you know. (before Highway 61 Revisited)\n"
            "That's always fun to play live for you all. (before Highway 61 Revisited)",
            ["Highway 61 Revisited", "Highway 61 Revisited"],
        )
        bt = anchor_bobtalk(conn, 1)
        assert [a["position"] for a in bt["anchored"]] == [1, 2]

    def test_metadata_and_short_lines_never_become_context(self):
        # parse_bobtalk() already drops catalogue/short lines -- they must not
        # leak into context either.
        conn = _bobtalk_db("Bootlegs\nDuelling Banjos . Papillon 016.", [])
        bt = anchor_bobtalk(conn, 1)
        assert bt == {"event_id": 1, "anchored": [], "context": []}
