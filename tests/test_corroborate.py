"""Tests for backend.qc.corroborate (TODO-342 Phase 3a, R-O4).

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest


@pytest.fixture
def qc():
    """Yield (db, rules, corroborate, conn) bound to a throwaway database."""
    tmp_dir = tempfile.mkdtemp(prefix="lbqc_corroborate_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend.qc import corroborate, rules
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield db, rules, corroborate, conn
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _insert_event(conn, event_id, date_str, songs, event_type="concert"):
    """Insert one olof_events row plus its olof_songs, in order."""
    conn.execute(
        "INSERT INTO olof_events (event_id, source, page_filename, event_type, date_str,"
        " raw_text) VALUES (?, 'dsn', 'test.htm', ?, ?, '')",
        (event_id, event_type, date_str),
    )
    for i, title in enumerate(songs, start=1):
        conn.execute(
            "INSERT INTO olof_songs (event_id, position, song_title) VALUES (?, ?, ?)",
            (event_id, i, title),
        )


def _insert_setlistfm(conn, setlistfm_id, date_str, songs):
    conn.execute(
        "INSERT INTO setlistfm_shows (setlistfm_id, date_str) VALUES (?, ?)",
        (setlistfm_id, date_str),
    )
    for i, title in enumerate(songs, start=1):
        conn.execute(
            "INSERT INTO setlistfm_setlist (setlistfm_id, set_index, position, set_position,"
            " track_name) VALUES (?, 0, ?, ?, ?)",
            (setlistfm_id, i, i, title),
        )


def _insert_bobdylan(conn, url, date_str, songs):
    conn.execute(
        "INSERT INTO bobdylan_shows (bobdylan_url, date_str) VALUES (?, ?)", (url, date_str),
    )
    for i, title in enumerate(songs, start=1):
        conn.execute(
            "INSERT INTO bobdylan_setlist (bobdylan_url, position, track_name) VALUES (?, ?, ?)",
            (url, i, title),
        )


def _insert_tuit(conn, date_str, songs, show_id=1):
    for title in songs:
        conn.execute(
            "INSERT INTO tuit_song_performances (song, date_str, show_id) VALUES (?, ?, ?)",
            (title, date_str, show_id),
        )


_SETLIST = ["Song A", "Song B", "Song C", "Song D", "Song E"]


class TestSetlistQuorumVerdicts:
    def test_corroborated_when_one_source_agrees(self, qc):
        """One source matching Olof's setlist in set and order is enough."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
            _insert_bobdylan(conn, "u1", "1978-01-01", _SETLIST)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "corroborated"
        assert q["sources"]["bobdylan"]["agrees"] is True
        assert q["sources"]["setlistfm"] is None

    def test_disputed_when_two_sources_agree_against_truncated_olof(self, qc):
        """Olof only got the first two songs (a truncated parse); two independent
        sources both have the full five and agree with each other — disputed."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST[:2])
            _insert_setlistfm(conn, "s1", "1978-01-01", _SETLIST)
            _insert_bobdylan(conn, "u1", "1978-01-01", _SETLIST)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "disputed"
        assert set(q["disputed_sources"]) == {"setlistfm", "bobdylan"}
        assert q["disputed_song_count"] == 5

    def test_stated_when_no_source_has_data(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "stated"
        assert all(v is None for v in q["sources"].values())

    def test_unavailable_when_olof_and_sources_are_all_empty(self, qc):
        _db, _rules, corroborate, conn = qc
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "unavailable"

    def test_intro_and_cover_conventions_not_counted(self, qc):
        """A source's own intro/non-song filler shouldn't cost it agreement (D15)."""
        _db, _rules, corroborate, conn = qc
        with_intro = ["Intro", *_SETLIST]
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
            _insert_bobdylan(conn, "u1", "1978-01-01", with_intro)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "corroborated"
        assert q["sources"]["bobdylan"]["agrees"] is True

    def test_tuit_order_is_never_trusted(self, qc):
        """TUIT has no position column; its comparison never sets order_agrees=False."""
        _db, _rules, corroborate, conn = qc
        shuffled = list(reversed(_SETLIST))
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
            _insert_tuit(conn, "1978-01-01", shuffled)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["sources"]["tuit"]["order_agrees"] is None
        assert q["verdict"] == "corroborated"

    def test_multi_show_date_picks_the_best_aligned_group(self, qc):
        """An early/late-show date with two setlist.fm ids picks the one matching Olof."""
        _db, _rules, corroborate, conn = qc
        other_show = ["Different Song 1", "Different Song 2"]
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
            _insert_setlistfm(conn, "early", "1978-01-01", other_show)
            _insert_setlistfm(conn, "late", "1978-01-01", _SETLIST)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "corroborated"
        assert q["sources"]["setlistfm"]["agrees"] is True


class TestRuleO4:
    def test_fires_only_on_disputed(self, qc):
        _db, rules, _corroborate, conn = qc
        with conn:
            # Date 1: disputed (two sources agree against a truncated Olof).
            _insert_event(conn, 1, "1978-01-01", _SETLIST[:2])
            _insert_setlistfm(conn, "s1", "1978-01-01", _SETLIST)
            _insert_bobdylan(conn, "u1", "1978-01-01", _SETLIST)
            # Date 2: corroborated — must not fire.
            _insert_event(conn, 2, "1979-01-01", _SETLIST)
            _insert_bobdylan(conn, "u2", "1979-01-01", _SETLIST)
            # Date 3: stated (no sources) — must not fire.
            _insert_event(conn, 3, "1980-01-01", _SETLIST)

        findings = list(rules.rule_o4(conn))
        assert [f.entity_key for f in findings] == ["1"]
        assert findings[0].entity_kind == "olof_event"
        assert findings[0].severity == "error"
        assert findings[0].evidence["quorum"]["verdict"] == "disputed"

    def test_registered_in_rules_table(self, qc):
        _db, rules, _corroborate, _conn = qc
        assert rules.RULES["R-O4"].func is rules.rule_o4

    def test_order_only_dispute_is_a_warning(self, qc):
        """Same songs, two adjacent swapped in both sources: warn, not error."""
        _db, rules, corroborate, conn = qc
        swapped = [_SETLIST[1], _SETLIST[0], *_SETLIST[2:]]
        with conn:
            _insert_event(conn, 1, "1978-01-01", _SETLIST)
            _insert_setlistfm(conn, "s1", "1978-01-01", swapped)
            _insert_bobdylan(conn, "u1", "1978-01-01", swapped)
        q = corroborate.setlist_quorum(conn, "1978-01-01")
        assert q["verdict"] == "disputed"
        assert corroborate.is_order_only_dispute(q)
        [finding] = list(rules.rule_o4(conn))
        assert finding.severity == "warn"

    def test_rerun_refreshes_severity(self, qc):
        """An open finding re-graded by its rule takes the new severity on the next run."""
        _db, rules, _corroborate, conn = qc
        from backend.qc import store

        grade = {"sev": "error"}

        def stub(_conn):
            yield rules.Finding(entity_kind="olof_event", entity_key="1",
                                severity=grade["sev"], detail="d", evidence={"x": grade["sev"]})

        rule = rules.RuleDef(rule_id="R-ZZ", description="stub", severity="error", func=stub)
        store.run_rule(conn, rule)
        grade["sev"] = "warn"
        store.run_rule(conn, rule)
        sev = conn.execute("SELECT severity FROM qc_findings WHERE rule_id='R-ZZ'").fetchone()[0]
        assert sev == "warn"


def _insert_song_performances(conn, event_id, songs, event_type="concert", tour_name=""):
    """Insert ``song_performances`` rows directly (bypassing the song_index recompute)."""
    for i, title in enumerate(songs, start=1):
        conn.execute(
            "INSERT INTO song_performances (event_id, position, song_norm, song_canonical,"
            " event_type) VALUES (?, ?, ?, ?, ?)",
            (event_id, i, title.lower(), title, event_type),
        )
    conn.execute("UPDATE olof_events SET tour_name = ? WHERE event_id = ?", (tour_name, event_id))


def _insert_tuit_recording(conn, lb_number, setlist_json):
    conn.execute(
        "INSERT INTO tuit_recordings (lb_number, setlist_json) VALUES (?, ?)",
        (lb_number, setlist_json),
    )


class TestTourPremieres:
    def test_ours_flags_first_tour_performance(self, qc):
        """A song not yet performed anywhere in the tour reads as our premiere."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A", "Song B"])
            _insert_song_performances(conn, 1, ["Song A", "Song B"], tour_name="T1")
            _insert_event(conn, 2, "2010-01-02", ["Song A", "Song C"])
            _insert_song_performances(conn, 2, ["Song A", "Song C"], tour_name="T1")
        tp = corroborate.tour_premieres(conn, 2)
        by_song = {s["song"]: s for s in tp["songs"]}
        assert by_song["Song A"]["ours"] is False
        assert by_song["Song C"]["ours"] is True
        assert tp["premiere_count"] == 1

    def test_setlistfm_agreement_within_our_tour_span(self, qc):
        """setlist.fm's earlier-in-*our*-tour data confirms one non-premiere; no data for the other."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A"])
            _insert_song_performances(conn, 1, ["Song A"], tour_name="T1")
            _insert_setlistfm(conn, "s1", "2010-01-01", ["Song A"])
            # Same Olof tour (T1) continues here: Song A already played in it (both
            # sides), Song B is new and setlist.fm's row for this date doesn't list it.
            _insert_event(conn, 2, "2010-01-02", ["Song A", "Song B"])
            _insert_song_performances(conn, 2, ["Song A", "Song B"], tour_name="T1")
            _insert_setlistfm(conn, "s2", "2010-01-02", ["Song A"])
        tp = corroborate.tour_premieres(conn, 2)
        by_song = {s["song"]: s for s in tp["songs"]}
        assert by_song["Song A"]["ours"] is False
        assert by_song["Song A"]["setlistfm"] is False
        assert by_song["Song A"]["agrees"] is True
        assert by_song["Song B"]["ours"] is True
        assert by_song["Song B"]["setlistfm"] is None
        assert by_song["Song B"]["agrees"] is None

    def test_setlistfm_own_tour_name_bucket_is_ignored(self, qc):
        """C16 fix: an earlier show in a *different* Olof tour must not count as history,
        even when setlist.fm groups both shows under the same (decades-wide) tour_name —
        the 2010-03-29 "Forever Young" case.
        """
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2009-01-01", ["Song X"])
            _insert_song_performances(conn, 1, ["Song X"], tour_name="T0")
            _insert_setlistfm(conn, "s1", "2009-01-01", ["Song X"])
            conn.execute(
                "UPDATE setlistfm_shows SET tour_name = 'Never Ending Tour' WHERE setlistfm_id"
                " = 's1'",
            )
            # A new, distinct Olof tour (T1) starts here; setlist.fm buckets this show
            # under the same wide tour_name as the 2009 show, but that must not matter.
            _insert_event(conn, 2, "2010-01-01", ["Song X"])
            _insert_song_performances(conn, 2, ["Song X"], tour_name="T1")
            _insert_setlistfm(conn, "s2", "2010-01-01", ["Song X"])
            conn.execute(
                "UPDATE setlistfm_shows SET tour_name = 'Never Ending Tour' WHERE setlistfm_id"
                " = 's2'",
            )
        tp = corroborate.tour_premieres(conn, 2)
        by_song = {s["song"]: s for s in tp["songs"]}
        assert by_song["Song X"]["ours"] is True
        assert by_song["Song X"]["setlistfm"] is True
        assert by_song["Song X"]["agrees"] is True

    def test_premiere_count_matches_tour_new_count(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A", "Song B"])
            _insert_song_performances(conn, 1, ["Song A", "Song B"], tour_name="T1")
            conn.execute("UPDATE olof_events SET tour_new_count = 2 WHERE event_id = 1")
        tp = corroborate.tour_premieres(conn, 1)
        assert tp["premiere_count"] == 2
        assert tp["premiere_count_matches"] is True


class TestRotationCheck:
    def test_recompute_matches_stated_stat(self, qc):
        """rotation_new/pct = count/floor(pct) of this show's songs absent from the previous."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A", "Song B", "Song C"])
            _insert_song_performances(conn, 1, ["Song A", "Song B", "Song C"])
            _insert_event(conn, 2, "2010-01-02", ["Song A", "Song D"])
            _insert_song_performances(conn, 2, ["Song A", "Song D"])
            # 1 of 2 songs (Song D) is new vs the previous show -> floor(1/2*100) = 50.
            conn.execute(
                "UPDATE olof_events SET rotation_new = 1, rotation_pct = 50 WHERE event_id = 2",
            )
        rc = corroborate.rotation_check(conn, 2)
        assert rc["previous_event_id"] == 1
        assert (rc["ours_new"], rc["ours_pct"]) == (1, 50)
        assert rc["agrees"] is True

    def test_disagreement_with_stated_stat(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A"])
            _insert_song_performances(conn, 1, ["Song A"])
            _insert_event(conn, 2, "2010-01-02", ["Song A", "Song B"])
            _insert_song_performances(conn, 2, ["Song A", "Song B"])
            conn.execute(
                "UPDATE olof_events SET rotation_new = 2, rotation_pct = 100 WHERE event_id = 2",
            )
        rc = corroborate.rotation_check(conn, 2)
        assert (rc["ours_new"], rc["ours_pct"]) == (1, 50)
        assert rc["agrees"] is False

    def test_no_stated_stat_is_agrees_none(self, qc):
        """No previous concert (tour/corpus opener) -> nothing to compare against."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A"])
            _insert_song_performances(conn, 1, ["Song A"])
        rc = corroborate.rotation_check(conn, 1)
        assert rc["previous_event_id"] is None
        assert rc["agrees"] is None


class TestTracklistCheck:
    def test_agrees_when_sets_match(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (1, ?)",
                ("1. Song A [3:00]\n2. Song B [4:00]\n",),
            )
            _insert_tuit_recording(
                conn, 1,
                '[{"track": "1", "song": "Song A"}, {"track": "2", "song": "Song B"}]',
            )
        tc = corroborate.tracklist_check(conn, 1)
        assert tc["lb_songs"] == ["Song A", "Song B"]
        assert tc["tuit_songs"] == ["Song A", "Song B"]
        assert tc["agrees"] is True
        assert tc["lb_only"] == []
        assert tc["tuit_only"] == []

    def test_disagrees_when_songs_differ(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (2, ?)",
                ("1. Song A [3:00]\n2. Song B [4:00]\n3. Song C [2:00]\n",),
            )
            _insert_tuit_recording(conn, 2, '[{"track": "1", "song": "Song A"}]')
        tc = corroborate.tracklist_check(conn, 2)
        assert tc["agrees"] is False
        assert set(tc["lb_only"]) == {"Song B", "Song C"}

    def test_missing_track_excluded_from_lb_songs(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (3, ?)",
                ("1. Song A [3:00]\n2. Song B, missing\n",),
            )
            _insert_tuit_recording(conn, 3, '[{"track": "1", "song": "Song A"}]')
        tc = corroborate.tracklist_check(conn, 3)
        assert tc["lb_songs"] == ["Song A"]
        assert tc["agrees"] is True

    def test_no_tuit_row(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (4, ?)",
                ("1. Song A [3:00]\n",),
            )
        tc = corroborate.tracklist_check(conn, 4)
        assert tc["tuit_songs"] is None
        assert tc["agrees"] is None
        assert tc["lb_only"] == ["Song A"]


class TestSourceConventions:
    def test_talkin_spellings_fold_on_both_sides(self, qc):
        """Olof's "Talkin ' New York" and a source's "Talkin’ New York" agree."""
        _db, _rules, corroborate, conn = qc
        olof = ["Talkin ' New York", "Talking World War III Blues", *_SETLIST[:3]]
        src = ["Talkin’ New York", "Talkin' World War III Blues", *_SETLIST[:3]]
        with conn:
            _insert_event(conn, 1, "1963-01-01", olof)
            _insert_setlistfm(conn, "s1", "1963-01-01", src)
        q = corroborate.setlist_quorum(conn, "1963-01-01")
        assert q["sources"]["setlistfm"]["olof_only"] == []
        assert q["verdict"] == "corroborated"

    def test_olof_placeholders_are_not_songs(self, qc):
        """"Unidentified Instrumental" / "Harmonica Riffs" don't count against a source."""
        _db, _rules, corroborate, conn = qc
        olof = ["Unidentified Instrumental", *_SETLIST, "Harmonica Riffs", "Piano riff"]
        with conn:
            _insert_event(conn, 1, "1965-01-01", olof)
            _insert_bobdylan(conn, "u1", "1965-01-01", _SETLIST)
        q = corroborate.setlist_quorum(conn, "1965-01-01")
        assert q["sources"]["bobdylan"]["olof_only"] == []
        assert q["verdict"] == "corroborated"


class TestTuitSetlistJsonEmptyList:
    """C16 fix: '[]' (a recording with no tracklist) must read as "no TUIT data",
    not as TUIT disagreeing with everything.
    """

    def test_empty_json_list_reads_as_no_tuit_data(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (10, ?)",
                ("1. Song A [3:00]\n2. Song B [4:00]\n",),
            )
            _insert_tuit_recording(conn, 10, "[]")
        tc = corroborate.tracklist_check(conn, 10)
        assert tc["tuit_songs"] is None
        assert tc["agrees"] is None
        assert tc["lb_only"] == ["Song A", "Song B"]

    def test_later_recording_with_real_data_is_used(self, qc):
        """An earlier recording's '[]' must not shadow a later one's real tracklist."""
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (11, ?)",
                ("1. Song A [3:00]\n",),
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, setlist_json)"
                " VALUES (201, 11, '[]')",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, setlist_json) VALUES"
                " (202, 11, '[{\"track\": \"1\", \"song\": \"Song A\"}]')",
            )
        tc = corroborate.tracklist_check(conn, 11)
        assert tc["tuit_songs"] == ["Song A"]
        assert tc["agrees"] is True

    def test_corpus_agreement_excludes_empty_json(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (12, ?)",
                ("1. Song A [3:00]\n",),
            )
            _insert_tuit_recording(conn, 12, "[]")
            conn.execute(
                "INSERT INTO entries (lb_number, setlist) VALUES (13, ?)",
                ("1. Song A [3:00]\n",),
            )
            _insert_tuit_recording(conn, 13, '[{"track": "1", "song": "Song A"}]')
        result = corroborate.tracklist_corpus_agreement(conn)
        assert result["total"] == 1
        assert result["agree"] == 1


class TestFileFormatCheck:
    def test_file_agrees_with_lineage_final_res(self, qc):
        """LB-08485-shaped case: entries' Source: gives 24/96, TUIT lineage ends at 16/44."""
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, description) VALUES (1, ?)",
                (
                    "Taper: Hide, Source: DPA 4061's > MMA6000 > Edirol R-09HR (24bit/96kHz), "
                    "Lineage: SDHC card > PC > WAV (24bit/96kHz) > Soundforge (Edit, sampling "
                    "convert to 16bit/44.1kHz) > TLH > FLAC",
                ),
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, format, lb_verified, lineage)"
                " VALUES (1, 1, 'FLAC 16/44', 1, 'SDHC card > PC > WAV (24bit/96kHz) >"
                " Soundforge (Edit, sampling convert to 16bit/44.1kHz) > TLH > FLAC')",
            )
        fc = corroborate.file_format_check(conn, 1)
        assert fc["file_res"] == "16/44"
        assert fc["recorded_res"] == "24/96"
        assert fc["final_res"] == "16/44"
        assert fc["basis"] == "file+lineage"
        assert fc["agrees"] is True

    def test_disagreement_when_documented_conversion_differs_from_file(self, qc):
        """A real, documented conversion step that the file record doesn't match."""
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, description) VALUES (2, ?)",
                ("Lineage: DAT (24bit/96kHz) > Soundforge (convert to 16bit/44.1kHz) > FLAC",),
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, format, lb_verified)"
                " VALUES (2, 2, 'FLAC 24/96', 1)",
            )
        fc = corroborate.file_format_check(conn, 2)
        assert fc["file_res"] == "24/96"
        assert fc["recorded_res"] == "24/96"
        assert fc["final_res"] == "16/44"
        assert fc["agrees"] is False

    def test_single_mismatched_token_is_ambiguous_not_disagreement(self, qc):
        """A lineage naming only the recorder's res, differing from the file, is unknown —
        an undocumented conversion is plausible; C16 fix (see _recorded_and_final).
        """
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, description) VALUES (6, ?)",
                ("Lineage: DAT (16bit/44.1kHz) > CD > FLAC",),
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, format, lb_verified)"
                " VALUES (6, 6, 'FLAC 24/96', 1)",
            )
        fc = corroborate.file_format_check(conn, 6)
        assert fc["file_res"] == "24/96"
        assert fc["recorded_res"] == "16/44"
        assert fc["final_res"] is None
        assert fc["agrees"] is None

    def test_no_file_record_basis_is_lineage_only(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, description) VALUES (3, ?)",
                ("Lineage: DAT (16bit/44.1kHz) > CD > FLAC",),
            )
        fc = corroborate.file_format_check(conn, 3)
        assert fc["file_res"] is None
        assert fc["recorded_res"] == "16/44"
        assert fc["final_res"] is None
        assert fc["basis"] == "lineage"
        assert fc["agrees"] is None

    def test_no_data_either_side_is_basis_none(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute("INSERT INTO entries (lb_number, description) VALUES (4, '')")
        fc = corroborate.file_format_check(conn, 4)
        assert fc["basis"] == "none"
        assert fc["agrees"] is None

    def test_entries_lineage_falls_back_when_tuit_has_none(self, qc):
        """A description-only Lineage: clause still yields recorded/final res without TUIT."""
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, description) VALUES (5, ?)",
                ("Lineage: Recorder (24bit/48kHz) > PC > FLAC",),
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, format, lb_verified)"
                " VALUES (5, 5, 'FLAC 24/48', 1)",
            )
        fc = corroborate.file_format_check(conn, 5)
        assert fc["recorded_res"] == "24/48"
        assert fc["file_res"] == "24/48"
        assert fc["agrees"] is True


class TestParseResolutionTokens:
    def test_bit_khz_form(self, qc):
        _db, _rules, corroborate, _conn = qc
        assert corroborate.parse_resolution_tokens("WAV (24bit/96kHz)") == ["24/96"]

    def test_bare_slash_form_truncates_fraction(self, qc):
        _db, _rules, corroborate, _conn = qc
        assert corroborate.parse_resolution_tokens("FLAC 16/44") == ["16/44"]

    def test_multiple_hops_in_order(self, qc):
        _db, _rules, corroborate, _conn = qc
        text = "Recorder (24bit/96kHz) > Soundforge (16bit/44.1kHz) > FLAC"
        assert corroborate.parse_resolution_tokens(text) == ["24/96", "16/44"]

    def test_no_match_returns_empty(self, qc):
        _db, _rules, corroborate, _conn = qc
        assert corroborate.parse_resolution_tokens("SDHC card > PC > FLAC") == []


class TestTaperCheck:
    def test_corroborated_when_canonical_matches(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES (1, 'spot', 'confirmed', '[]', 0)",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES (1, 1, 'SPOT')",
            )
        tc = corroborate.taper_check(conn, 1)
        assert tc["verdict"] == "corroborated"
        assert tc["ours"] == "spot"

    def test_disputed_when_no_canonical_matches(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES (2, 'spot', 'confirmed', '[]', 0)",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES (2, 2, 'Bach')",
            )
        tc = corroborate.taper_check(conn, 2)
        assert tc["verdict"] == "disputed"

    def test_unavailable_when_tuit_has_no_taper(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES (3, 'spot', 'confirmed', '[]', 0)",
            )
        tc = corroborate.taper_check(conn, 3)
        assert tc["verdict"] == "unavailable"

    def test_conflict_row_is_unavailable(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES (4, 'spot', 'confirmed', '[]', 1)",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES (4, 4, 'Bach')",
            )
        tc = corroborate.taper_check(conn, 4)
        assert tc["verdict"] == "unavailable"

    def test_matches_rule_t4_verdict(self, qc):
        """taper_check and rule_t4 must agree — both go through taper_agreement."""
        _db, rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES (5, '', '', '')",
            )
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES (5, 'spot', 'confirmed', '[]', 0)",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES (5, 5, 'Bach')",
            )
        tc = corroborate.taper_check(conn, 5)
        finding_keys = {f.entity_key for f in rules.rule_t4(conn)}
        assert (tc["verdict"] == "disputed") == ("5" in finding_keys)


class TestTaperCorpusAgreement:
    def test_counts_match_population(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            conn.execute(
                "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                " evidence_json, conflict) VALUES"
                " (1, 'spot', 'confirmed', '[]', 0), (2, 'spot', 'confirmed', '[]', 0),"
                " (3, 'spot', 'confirmed', '[]', 1)",
            )
            conn.execute(
                "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES"
                " (1, 1, 'SPOT'), (2, 2, 'Bach'), (3, 3, 'Bach')",
            )
        result = corroborate.taper_corpus_agreement(conn)
        assert result["total"] == 2
        assert result["corroborated"] == 1
        assert result["disputed"] == 1


class TestVenueCheck:
    def test_corroborated_when_setlistfm_venue_matches(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-01-01", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'The Fillmore', city = 'San Francisco'"
                " WHERE event_id = 1",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city)"
                " VALUES ('s1', '1990-01-01', 'Fillmore', 'San Francisco')",
            )
        vc = corroborate.venue_check(conn, "1990-01-01")
        assert vc["verdict"] == "corroborated"
        assert vc["sources"]["setlistfm"]["venue_agrees"] is True

    def test_disputed_when_venues_differ(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-01-02", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'Zepp Tokyo', city = 'Tokyo' WHERE event_id = 1",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city)"
                " VALUES ('s2', '1990-01-02', 'Zepp DiverCity', 'Tokyo')",
            )
            conn.execute(
                "INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location)"
                " VALUES ('u2', '1990-01-02', 'Zepp DiverCity', 'Tokyo, Japan')",
            )
        vc = corroborate.venue_check(conn, "1990-01-02")
        assert vc["verdict"] == "disputed"
        assert vc["sources"]["setlistfm"]["venue_agrees"] is False
        assert vc["sources"]["bobdylan"]["city_agrees"] is True

    def test_unavailable_when_no_source_has_a_row(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-01-03", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'Zepp Tokyo', city = 'Tokyo' WHERE event_id = 1",
            )
        vc = corroborate.venue_check(conn, "1990-01-03")
        assert vc["verdict"] == "unavailable"

    def test_city_fold_new_york_city_vs_new_york(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-01-04", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'MSG', city = 'New York City'"
                " WHERE event_id = 1",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city)"
                " VALUES ('s4', '1990-01-04', 'MSG', 'New York')",
            )
        vc = corroborate.venue_check(conn, "1990-01-04")
        assert vc["sources"]["setlistfm"]["city_agrees"] is True

    def test_leading_the_and_accents_fold(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-01-05", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'The Café Royal', city = ''"
                " WHERE event_id = 1",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city)"
                " VALUES ('s5', '1990-01-05', 'Cafe Royal', '')",
            )
        vc = corroborate.venue_check(conn, "1990-01-05")
        assert vc["sources"]["setlistfm"]["venue_agrees"] is True
        assert vc["verdict"] == "corroborated"


class TestVenueCorpusAgreement:
    def test_counts_match_population(self, qc):
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "1990-02-01", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'Fillmore' WHERE event_id = 1",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name)"
                " VALUES ('s1', '1990-02-01', 'Fillmore')",
            )
            _insert_event(conn, 2, "1990-02-02", [])
            conn.execute(
                "UPDATE olof_events SET venue = 'Zepp Tokyo' WHERE event_id = 2",
            )
            conn.execute(
                "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name)"
                " VALUES ('s2', '1990-02-02', 'Zepp DiverCity')",
            )
        result = corroborate.venue_corpus_agreement(conn)
        assert result["total"] == 2
        assert result["corroborated"] == 1
        assert result["disputed"] == 1
