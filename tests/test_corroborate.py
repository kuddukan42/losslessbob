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
