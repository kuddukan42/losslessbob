"""Tests for backend.dossier_fields (TODO-342 D-01 track matcher) and the C13
``_ENTRY_TRACK_MARKER_RE`` fix in backend.db. Pure functions — no DB needed."""
import pytest

from backend import db
from backend.dossier_fields import (
    build_setlist_index,
    clean_track_title,
    is_non_song,
    match_track,
    parse_entry_tracklist,
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
