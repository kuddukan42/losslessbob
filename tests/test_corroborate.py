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

    def test_setlistfm_agreement_and_disagreement(self, qc):
        """setlist.fm's own tour scope confirms one premiere and contradicts another."""
        _db, _rules, corroborate, conn = qc
        with conn:
            _insert_event(conn, 1, "2010-01-01", ["Song A"])
            _insert_song_performances(conn, 1, ["Song A"], tour_name="T1")
            _insert_setlistfm(conn, "s1", "2010-01-01", ["Song A"])
            conn.execute(
                "UPDATE setlistfm_shows SET tour_name = 'SFM Tour' WHERE setlistfm_id = 's1'",
            )
            # New event: our corpus says both are premieres (T1); setlist.fm's own
            # tour history (SFM Tour) already has Song A, so it disagrees on that one,
            # and has no data at all for Song B (source has no data).
            _insert_event(conn, 2, "2010-01-02", ["Song A", "Song B"])
            _insert_song_performances(conn, 2, ["Song A", "Song B"], tour_name="T2")
            _insert_setlistfm(conn, "s2", "2010-01-02", ["Song A"])
            conn.execute(
                "UPDATE setlistfm_shows SET tour_name = 'SFM Tour' WHERE setlistfm_id = 's2'",
            )
        tp = corroborate.tour_premieres(conn, 2)
        by_song = {s["song"]: s for s in tp["songs"]}
        assert by_song["Song A"]["ours"] is True
        assert by_song["Song A"]["setlistfm"] is False
        assert by_song["Song A"]["agrees"] is False
        assert by_song["Song B"]["ours"] is True
        assert by_song["Song B"]["setlistfm"] is None
        assert by_song["Song B"]["agrees"] is None

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
