"""Tests for the Show Dossier QC rule engine (backend.qc), TODO-342 Phase 2.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def qc():
    """Yield (db, store, rules, conn) bound to a throwaway database."""
    tmp_dir = tempfile.mkdtemp(prefix="lbqc_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend.qc import rules, store
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield db, store, rules, conn, db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _insert_event(conn, event_id, raw_text, date_str="1978-01-01"):
    conn.execute(
        "INSERT INTO olof_events (event_id, source, page_filename, event_type, date_str,"
        " raw_text) VALUES (?, 'dsn', 'test.htm', 'concert', ?, ?)",
        (event_id, date_str, raw_text),
    )


def _insert_song(conn, event_id, position, title="Song", annotations=""):
    conn.execute(
        "INSERT INTO olof_songs (event_id, position, song_title, annotations)"
        " VALUES (?, ?, ?, ?)",
        (event_id, position, title, annotations),
    )


class TestInitDb:
    def test_init_twice_is_clean(self, qc):
        db, _store, _rules, _conn, db_path = qc
        db.init_db(db_path)  # should not raise, no duplicate-table errors


class TestRuleO1:
    def test_fires_on_truncated_concert(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 1, "1. Song A\n2. Song B\n3. Song C\n")
            _insert_song(conn, 1, 1, "Song A")
            _insert_song(conn, 1, 2, "Song B")
        findings = list(rules.rule_o1(conn))
        assert len(findings) == 1
        f = findings[0]
        assert f.entity_kind == "olof_event" and f.entity_key == "1"
        assert f.evidence == {"date": "1978-01-01", "parsed": 2, "numbered": 3}

    def test_does_not_fire_on_clean_concert(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 2, "1. Song A\n2. Song B\n")
            _insert_song(conn, 2, 1, "Song A")
            _insert_song(conn, 2, 2, "Song B")
        assert list(rules.rule_o1(conn)) == []


class TestRuleO3:
    def test_fires_on_date_shaped_annotation(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 3, "1. Song A\n")
            _insert_song(conn, 3, 1, "Song A", annotations="1 March 1978")
        findings = list(rules.rule_o3(conn))
        assert len(findings) == 1
        assert findings[0].entity_kind == "olof_song" and findings[0].entity_key == "3:1"

    def test_fires_on_rotation_stat_annotation(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 4, "1. Song A\n")
            _insert_song(conn, 4, 1, "Song A", annotations="compared to previous concert")
        assert len(list(rules.rule_o3(conn))) == 1

    def test_does_not_fire_on_clean_annotation(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 5, "1. Song A\n")
            _insert_song(conn, 5, 1, "Song A", annotations="acoustic w band")
        assert list(rules.rule_o3(conn)) == []


class TestLifecycle:
    def test_new_fixed_reopened(self, qc):
        _db, store, rules, conn, _path = qc
        rule = rules.RULES["R-O1"]
        with conn:
            _insert_event(conn, 6, "1. A\n2. B\n3. C\n")
            _insert_song(conn, 6, 1, "A")
            _insert_song(conn, 6, 2, "B")

        stats = store.run_rule(conn, rule)
        assert stats.n_new == 1 and stats.n_open == 1

        row = conn.execute(
            "SELECT * FROM qc_findings WHERE entity_kind='olof_event' AND entity_key='6'"
        ).fetchone()
        assert row["status"] == "open"

        with conn:
            _insert_song(conn, 6, 3, "C")  # now parsed == numbered, rule stops firing
        stats = store.run_rule(conn, rule)
        assert stats.n_fixed == 1 and stats.n_open == 0
        row = conn.execute(
            "SELECT * FROM qc_findings WHERE entity_kind='olof_event' AND entity_key='6'"
        ).fetchone()
        assert row["status"] == "fixed"

        with conn:
            conn.execute("DELETE FROM olof_songs WHERE event_id=6 AND position=3")
        stats = store.run_rule(conn, rule)
        assert stats.n_reopened == 1 and stats.n_open == 1
        row = conn.execute(
            "SELECT * FROM qc_findings WHERE entity_kind='olof_event' AND entity_key='6'"
        ).fetchone()
        assert row["status"] == "open"
        log_rows = conn.execute(
            "SELECT * FROM qc_decision_log WHERE finding_id=?", (row["id"],)
        ).fetchall()
        assert any(r["prev_status"] == "fixed" and r["new_status"] == "open" for r in log_rows)


class TestFalsePositive:
    def test_same_evidence_stays_changed_evidence_reopens(self, qc):
        _db, store, rules, conn, _path = qc
        rule = rules.RULES["R-O1"]
        with conn:
            _insert_event(conn, 7, "1. A\n2. B\n3. C\n")
            _insert_song(conn, 7, 1, "A")
        store.run_rule(conn, rule)
        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE entity_kind='olof_event' AND entity_key='7'"
        ).fetchone()["id"]
        with conn:
            conn.execute(
                "UPDATE qc_findings SET status='false_positive' WHERE id=?", (finding_id,)
            )

        # Same evidence (no data change): stays false_positive, no reopen.
        stats = store.run_rule(conn, rule)
        assert stats.n_reopened == 0
        status = conn.execute(
            "SELECT status FROM qc_findings WHERE id=?", (finding_id,)
        ).fetchone()["status"]
        assert status == "false_positive"

        # Evidence changes (numbered count drops): reopens.
        with conn:
            conn.execute(
                "UPDATE olof_events SET raw_text='1. A\n2. B\n' WHERE event_id=7"
            )
        stats = store.run_rule(conn, rule)
        assert stats.n_reopened == 1
        row = conn.execute("SELECT * FROM qc_findings WHERE id=?", (finding_id,)).fetchone()
        assert row["status"] == "open"
        log_rows = conn.execute(
            "SELECT * FROM qc_decision_log WHERE finding_id=?", (finding_id,)
        ).fetchall()
        assert any(
            r["prev_status"] == "false_positive" and r["new_status"] == "open"
            for r in log_rows
        )


class TestQuarantine:
    def test_returns_only_open_confirmed_error_rules(self, qc):
        _db, store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 8, "1. A\n2. B\n")
            _insert_song(conn, 8, 1, "A")
        store.run_rule(conn, rules.RULES["R-O1"])

        assert store.quarantined(conn, "olof_event", "8") == ["R-O1"]
        assert store.quarantined(conn, "olof_event", "999") == []

        with conn:
            conn.execute(
                "UPDATE qc_findings SET status='false_positive'"
                " WHERE entity_kind='olof_event' AND entity_key='8'"
            )
        assert store.quarantined(conn, "olof_event", "8") == []

    def test_batch_and_missing_tables_are_safe(self, qc):
        _db, store, _rules, conn, _path = qc
        assert store.quarantined_batch(conn, "olof_event", []) == {}
        assert store.quarantined_batch(conn, "olof_event", ["1", "2"]) == {}

        import sqlite3
        bare = sqlite3.connect(":memory:")  # no qc_findings, no row_factory
        assert store.quarantined(bare, "olof_event", "1") == []
        assert store.quarantined_batch(bare, "olof_event", ["1"]) == {}
