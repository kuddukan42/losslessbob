"""Tests for the Show Dossier QC rule engine (backend.qc), TODO-342 Phase 2.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
import json
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


def _insert_attr(conn, lb, taper, confidence, evidence, description="",
                 date_str="1/1/80", conflict=0):
    conn.execute(
        "INSERT OR REPLACE INTO entries (lb_number, description, date_str) VALUES (?, ?, ?)",
        (lb, description, date_str),
    )
    conn.execute(
        "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
        " evidence_json, conflict) VALUES (?, ?, ?, ?, ?)",
        (lb, taper, confidence, json.dumps(evidence), conflict),
    )


def _insert_family_meta(conn, fam_id, conf, review_flag=0):
    conn.execute(
        "INSERT INTO tapematch_family_meta (fam_id, concert_date, member_count, conf,"
        " review_flag) VALUES (?, '1980-01-01', 2, ?, ?)",
        (fam_id, conf, review_flag),
    )


_MENTION = [{"kind": "mention", "detail": "mention"}]


class TestRuleT1:
    def test_fires_on_gear_name_mention(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
        findings = list(rules.rule_t1(conn))
        assert [f.entity_key for f in findings] == ["8493"]
        assert findings[0].evidence["taper"] == "mike millard"

    def test_quiet_on_context_mention_and_confirmed(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_attr(conn, 1, "spot", "propagated", _MENTION,
                         "Audience, recorded by spot on a Sony D5")
            _insert_attr(conn, 2, "spot", "confirmed",
                         [{"kind": "confirmation", "detail": "curator confirmed"}],
                         "thanks to spot")
        assert list(rules.rule_t1(conn)) == []


class TestRuleT2:
    def test_fires_on_weak_and_flagged_families(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_family_meta(conn, "F-low", 0.3)
            _insert_family_meta(conn, "F-flag", 0.9, review_flag=1)
            _insert_family_meta(conn, "F-ok", 0.8)
            for lb, fam in ((1, "F-low"), (2, "F-flag"), (3, "F-ok")):
                _insert_attr(conn, lb, "spot", "propagated",
                             [{"kind": "family", "detail": "d", "fam_id": fam, "via_lb": 9}])
        findings = {f.entity_key: f for f in rules.rule_t2(conn)}
        assert set(findings) == {"1", "2"}
        assert findings["1"].evidence["fam_id"] == "F-low"
        assert "review-flagged" in findings["2"].detail


class TestRuleT3:
    def test_fires_outside_confirmed_years(self, qc):
        _db, _store, rules, conn, _path = qc
        confirmed = [{"kind": "explicit", "detail": "d"}]
        with conn:
            _insert_attr(conn, 1, "spot", "confirmed", confirmed, date_str="1/1/80")
            _insert_attr(conn, 2, "spot", "confirmed", confirmed, date_str="6/5/85")
            _insert_attr(conn, 3, "spot", "propagated", _MENTION, date_str="1/1/95")
            _insert_attr(conn, 4, "spot", "propagated", _MENTION, date_str="5/xx/89")
            _insert_attr(conn, 5, "spot", "propagated", _MENTION, date_str="1/1/05",
                         conflict=1)
            _insert_attr(conn, 6, "hide", "propagated", _MENTION, date_str="1/1/05")
        findings = list(rules.rule_t3(conn))
        assert [f.entity_key for f in findings] == ["3"]
        assert findings[0].evidence == {"taper": "spot", "year": 1995,
                                        "confirmed_from": 1980, "confirmed_to": 1985}


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


class TestRuleO2:
    def test_fires_on_embedded_country_and_empty_city(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            # A baseline row establishes 'England' in the corpus's known-country set.
            _insert_event(conn, 19, "1. Song A\n", date_str="1976-01-01")
            conn.execute("UPDATE olof_events SET city='Manchester', country='England' WHERE event_id=19")
            _insert_event(conn, 20, "1. Song A\n", date_str="1978-01-01")
            conn.execute(
                "UPDATE olof_events SET city='London England', country='' WHERE event_id=20"
            )
            _insert_event(conn, 21, "1. Song A\n", date_str="1978-01-02")
            conn.execute("UPDATE olof_events SET city='', country='' WHERE event_id=21")
        findings = list(rules.rule_o2(conn))
        keys = {f.entity_key: f.detail for f in findings}
        assert "20" in keys and "embeds a country name" in keys["20"]
        assert "21" in keys and "empty city" in keys["21"]

    def test_fires_on_ambiguous_city_country_pairing(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 22, "1. Song A\n", date_str="1977-01-01")
            conn.execute("UPDATE olof_events SET city='London', country='England' WHERE event_id=22")
            _insert_event(conn, 23, "1. Song A\n", date_str="1997-01-01")
            conn.execute("UPDATE olof_events SET city='London', country='Canada' WHERE event_id=23")
        findings = list(rules.rule_o2(conn))
        keys = {f.entity_key for f in findings}
        assert {"22", "23"} <= keys

    def test_does_not_fire_on_empty_country_alone(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 24, "1. Song A\n", date_str="1978-01-01")
            conn.execute("UPDATE olof_events SET city='Paris', country='' WHERE event_id=24")
        assert list(rules.rule_o2(conn)) == []


class TestRuleG1:
    def test_fires_on_zepp_tokyo(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO venue_geocoded (venue_norm, city_norm, venue, city, country,"
                " source, confidence, note) VALUES ('zepp tokyo', 'tokyo', 'Zepp Tokyo',"
                " 'Tokyo', 'Japan', 'bounded_venue', 'low',"
                " 'Zepp DiverCity, Aomi, Koto, Tokyo, Japan')"
            )
        findings = list(rules.rule_g1(conn))
        assert len(findings) == 1
        assert findings[0].entity_key == "zepp tokyo:tokyo"
        assert "tokyo" in findings[0].evidence["missing"]

    def test_does_not_fire_on_matching_venue(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO venue_geocoded (venue_norm, city_norm, venue, city, country,"
                " source, confidence, note) VALUES ('symphony hall', 'boston', 'Symphony Hall',"
                " 'Boston', 'USA', 'bounded_venue', 'low',"
                " 'Symphony Hall, 301, Massachusetts Avenue, Boston, USA')"
            )
        assert list(rules.rule_g1(conn)) == []

    def test_ignores_city_level_pins(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO venue_geocoded (venue_norm, city_norm, venue, city, country,"
                " source, confidence, note) VALUES ('some club', 'nowhere', 'Some Club',"
                " 'Nowhere', 'USA', 'setlistfm_city', 'city', 'city-level pin (setlistfm_city)')"
            )
        assert list(rules.rule_g1(conn)) == []


class TestRuleE1:
    def test_fires_on_bad_fields(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (100, 'Heinrich', '2', 'A')"
            )
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (101, '60min', '26', 'A')"
            )
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (102, '60min', '2', 'Z')"
            )
        findings = {f.entity_key: f.detail for f in rules.rule_e1(conn)}
        assert "no 'min' unit" in findings["100"]
        assert "out of range" in findings["101"]
        assert "not a known grade" in findings["102"]

    def test_does_not_fire_on_clean_entry(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (103, '60min', '2', 'A-')"
            )
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES (104, '', '', '')"
            )
        assert list(rules.rule_e1(conn)) == []


class TestRuleF1:
    def test_fires_on_weak_or_flagged_family(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO tapematch_family_meta (fam_id, concert_date, conf, member_count,"
                " review_flag) VALUES ('fam-weak', '1978-01-01', 0.05, 2, 0)"
            )
            conn.execute(
                "INSERT INTO tapematch_family_meta (fam_id, concert_date, conf, member_count,"
                " review_flag) VALUES ('fam-flagged', '1978-01-01', 0.9, 2, 1)"
            )
        keys = {f.entity_key for f in rules.rule_f1(conn)}
        assert keys == {"fam-weak", "fam-flagged"}

    def test_does_not_fire_on_healthy_family(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO tapematch_family_meta (fam_id, concert_date, conf, member_count,"
                " review_flag) VALUES ('fam-good', '1978-01-01', 0.9, 2, 0)"
            )
        assert list(rules.rule_f1(conn)) == []


class TestRuleS1:
    def test_fires_when_picks_older_than_families(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank,"
                " evidence_json, computed_at) VALUES ('1978-01-01', 1, 1.0, 1, '[]',"
                " '2026-01-01 00:00:00')"
            )
            conn.execute(
                "INSERT INTO recording_families (lb_number, fam_id, concert_date, imported_at)"
                " VALUES (1, 'fam-1', '1978-01-01', '2026-02-01 00:00:00')"
            )
        keys = {f.entity_key for f in rules.rule_s1(conn)}
        assert "show_picks" in keys

    def test_fires_on_lb_measured_after_last_rerank(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (200, '', '', ''), (201, '', '', ''), (202, '', '', '')"
            )
            conn.execute(
                "INSERT INTO quality_scans (scan_id, started_at) VALUES"
                " (1, '2026-01-01'), (2, '2026-02-01')"
            )
            # Scan 1 was reranked (201 scored, 202 seen but unscorable); scan 2 never was.
            conn.execute(
                "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json)"
                " VALUES (200, 2, '{}'), (201, 1, '{}'), (202, 1, '{}')"
            )
            conn.execute(
                "INSERT INTO quality_recording_scores (lb_number, scan_id, final_score)"
                " VALUES (201, 1, 5.0)"
            )
        keys = {f.entity_key for f in rules.rule_s1(conn)}
        assert "200" in keys
        assert "201" not in keys
        assert "202" not in keys  # unscored by the last rerank is not stale

    def test_does_not_fire_when_everything_fresh(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO recording_families (lb_number, fam_id, concert_date, imported_at)"
                " VALUES (1, 'fam-1', '1978-01-01', '2026-01-01 00:00:00')"
            )
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank,"
                " evidence_json, computed_at) VALUES ('1978-01-01', 1, 1.0, 1, '[]',"
                " '2026-02-01 00:00:00')"
            )
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES (200, '', '', '')"
            )
            conn.execute(
                "INSERT INTO quality_scans (scan_id, started_at) VALUES (1, '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json)"
                " VALUES (200, 1, '{}')"
            )
            conn.execute(
                "INSERT INTO quality_recording_scores (lb_number, scan_id, final_score)"
                " VALUES (200, 1, 5.0)"
            )
            conn.execute(
                "INSERT INTO olof_pages (filename, parsed_at) VALUES"
                " ('other.htm', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "UPDATE olof_pages SET parsed_at='2026-01-01T00:00:00' WHERE filename='test.htm'"
            )
            conn.execute(
                "INSERT INTO song_performances (event_id, position, song_norm, song_canonical,"
                " computed_at) VALUES (1, 1, 'song a', 'Song A', '2026-02-01 00:00:00')"
            )
        assert list(rules.rule_s1(conn)) == []


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
