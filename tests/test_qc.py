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


_BBC_1965 = [
    "Ballad Of Hollis Brown", "Mr. Tambourine Man", "Gates Of Eden", "If You Gotta Go, Go Now",
    "It Ain't Me, Babe", "Love Minus Zero/No Limit", "One Too Many Mornings",
    "Boots Of Spanish Leather", "She Belongs To Me", "It's All Over Now, Baby Blue",
]


def _seed_1965(conn):
    _insert_event(conn, 1, "raw", date_str="1965-06-01")
    for pos, title in enumerate(_BBC_1965, start=1):
        _insert_song(conn, 1, pos, title)
    _insert_song(conn, 1, 11, "It's Alright, Ma")
    conn.execute(
        "UPDATE olof_songs SET subtitle=\"I'm Only Bleeding\" WHERE song_title=\"It's Alright, Ma\""
    )


def _insert_entry(conn, lb, setlist, date_str="6/1/65"):
    conn.execute(
        "INSERT INTO entries (lb_number, date_str, setlist) VALUES (?, ?, ?)",
        (lb, date_str, setlist),
    )


class TestRuleE2:
    def test_fires_on_misdated_compilation(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _seed_1965(conn)
            _insert_entry(conn, 6654, (
                "CD 1\n1. Like A Rolling Stone\n2. Tombstone Blues\n3. From A Buick 6\n"
                "4. Desolation Row\n5. Positively 4th Street\nCD 2\n"
                "6. Rainy Day Women Nos. 12 & 35\n7. Visions Of Johanna\n8. I Want You"
            ))
        findings = list(rules.rule_e2(conn))
        assert [f.entity_key for f in findings] == ["6654"]
        f = findings[0]
        assert f.entity_kind == "entry" and f.severity == "error"
        assert f.evidence["date"] == "1965-06-01"
        assert f.evidence["song_tracks"] == 8 and f.evidence["matched"] == 0
        assert f.evidence["share"] == 0.0
        assert len(f.evidence["unmatched"]) == 8
        assert f.evidence["unmatched"][0] == "Like A Rolling Stone"

    def test_short_excerpt_and_good_fit_do_not_fire(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _seed_1965(conn)
            _insert_entry(conn, 10364, "01. If You Gotta Go, Go Now")  # 1/1 matched
            _insert_entry(conn, 8855, (
                "First Broadcast: June 26th 1965, 01. Ballad Of Hollis Brown,"
                " 02. Mr Tambourine Man, missing, 03. If You Gotta Go, Go Now, missing,"
                " 04. It Ain't Me Babe, Second Broadcast: June 19th 1965,"
                " 05. Love Minus Zero/No Limit, 06. It's Alright Ma (I'm Only Bleeding)"
            ))
            # Two unlisted songs: below the minimum song-track count, so skipped.
            _insert_entry(conn, 20001, "1. Like A Rolling Stone, 2. Tombstone Blues")
        assert list(rules.rule_e2(conn)) == []
        fits = {f["lb_number"]: f for f in rules.entry_setlist_fit(conn)}
        assert (fits[10364]["song_tracks"], fits[10364]["matched"]) == (1, 1)
        # The two 'missing' tracks don't count; the rest all match.
        assert (fits[8855]["song_tracks"], fits[8855]["matched"]) == (4, 4)

    def test_intro_is_not_a_song_track(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _seed_1965(conn)
            _insert_entry(conn, 30001, (
                "0. Introduction, 1. Gates Of Eden, 2. Tombstone Blues, 3. Desolation Row,"
                " 4. I Want You, 5. Visions Of Johanna"
            ))
        fit = next(iter(rules.entry_setlist_fit(conn)))
        assert (fit["song_tracks"], fit["matched"]) == (5, 1)
        assert list(rules.rule_e2(conn)) == []  # 1/5 = 20%, not below

    def test_skips_undated_and_dates_without_olof_songs(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _seed_1965(conn)
            _insert_entry(conn, 40001, "1. A, 2. B, 3. C, 4. D", date_str="6/xx/65")
            _insert_entry(conn, 40002, "1. A Song, 2. B Song, 3. C Song", date_str="7/1/65")
        assert list(rules.entry_setlist_fit(conn)) == []
        assert list(rules.rule_e2(conn)) == []

    def test_superset_of_short_olof_listing_does_not_fire(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _insert_event(conn, 2, "raw", date_str="1976-05-16")
            _insert_song(conn, 2, 1, "Isis")
            _insert_song(conn, 2, 2, "Mozambique")
            # Full show: both of Olof's 2 songs plus 10 guest-set songs (2/12 < 20%).
            guests = ", ".join(f"{i}. Guest Song {chr(64 + i)}" for i in range(3, 13))
            _insert_entry(conn, 567, f"1. Isis, 2. Mozambique, {guests}", date_str="5/16/76")
        fit = next(iter(rules.entry_setlist_fit(conn)))
        assert (fit["matched"], fit["song_tracks"], fit["olof_matched"]) == (2, 12, 2)
        assert list(rules.rule_e2(conn)) == []

    def test_glued_tracklist_does_not_fire(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            _seed_1965(conn)
            _insert_entry(conn, 46, (
                "1. Somebody Touched Me 2. Long Black Veil 3. Masters Of War,"
                " 4. Tombstone Blues, 5. Visions Of Johanna"
            ))
        fit = next(iter(rules.entry_setlist_fit(conn)))
        assert fit["glued"] and fit["matched"] == 0
        assert list(rules.rule_e2(conn)) == []

    def test_registered(self, qc):
        _db, _store, rules, _conn, _path = qc
        assert rules.RULES["R-E2"].severity == "error"


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
            # Scan 1 is the main scan: 200 measured after the rerank, 201 scored,
            # 202 seen but unscorable. Scan 2 is a calibration re-measure of 201.
            conn.execute(
                "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json,"
                " scored_at) VALUES (200, 1, '{}', '2026-03-01 00:00:00'),"
                " (201, 1, '{}', '2026-01-15 00:00:00'), (202, 1, '{}', '2026-01-15 00:00:00'),"
                " (201, 2, '{}', '2026-03-01 00:00:00')"
            )
            conn.execute(
                "INSERT INTO quality_recording_scores (lb_number, scan_id, final_score)"
                " VALUES (201, 1, 5.0)"
            )
            conn.execute(
                "INSERT INTO refresh_step_runs (step_id, started_at, finished_at, status,"
                " trigger_source) VALUES ('ranker_rerank', '2026-02-01 00:00:00',"
                " '2026-02-01 00:01:00', 'ok', 'route')"
            )
        keys = {f.entity_key for f in rules.rule_s1(conn)}
        assert "200" in keys
        assert "201" not in keys  # calibration scan metrics are not staleness
        assert "202" not in keys  # unscored by the last rerank is not stale

    def test_fires_on_never_reranked_main_scan(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES (300, '', '', '')"
            )
            conn.execute("INSERT INTO quality_scans (scan_id, started_at) VALUES (1, '2026-01-01')")
            conn.execute(
                "INSERT INTO quality_recording_metrics (lb_number, scan_id, metric_json)"
                " VALUES (300, 1, '{}')"
            )
        assert "300" in {f.entity_key for f in rules.rule_s1(conn)}

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


def _tuit(conn, rec_id, lb, taper):
    conn.execute(
        "INSERT INTO tuit_recordings (rec_id, lb_number, taper) VALUES (?, ?, ?)",
        (rec_id, lb, taper),
    )


def _attr(conn, lb, taper, conflict=0):
    conn.execute(
        "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
        " evidence_json, conflict) VALUES (?, ?, 'confirmed', '[]', ?)",
        (lb, taper, conflict),
    )


class TestRuleT4:
    def test_fires_on_real_disagreement_only(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute(
                "INSERT INTO entries (lb_number, timing, cdr, rating) VALUES"
                " (1, '', '', ''), (2, '', '', ''), (3, '', '', ''), (4, '', '', ''),"
                " (5, '', '', '')"
            )
            _attr(conn, 1, "spot")
            _tuit(conn, 101, 1, "Bach")             # disagrees
            _attr(conn, 2, "spot")
            _tuit(conn, 102, 2, "SPOT")             # same after normalising
            _attr(conn, 3, "bach")
            _tuit(conn, 103, 3, "Spot & Bach")      # one part agrees
            _attr(conn, 4, "spot")
            _tuit(conn, 104, 4, "Unknown")          # placeholder
            _attr(conn, 5, "spot", conflict=1)
            _tuit(conn, 105, 5, "Bach")             # conflict rows skipped
        keys = {f.entity_key for f in rules.rule_t4(conn)}
        assert keys == {"1"}

    def test_ignores_not_a_taper_handles(self, qc):
        _db, _store, rules, conn, _path = qc
        with conn:
            conn.execute("INSERT INTO entries (lb_number, timing, cdr, rating)"
                         " VALUES (7, '', '', '')")
            _attr(conn, 7, "spot")
            _tuit(conn, 107, 7, "Dolphinsmile")     # uploader, not a taper
        assert list(rules.rule_t4(conn)) == []


class TestTuitTaperHelpers:
    def test_parts_split_gloss_and_drop_placeholders(self, qc):
        from backend import taper_curation
        assert taper_curation.tuit_taper_parts("Unknown") == []
        assert "bach" in taper_curation.tuit_taper_parts("Spot (Bach)")

    def test_alias_candidates_are_mechanical(self, qc):
        db, _store, _rules, conn, path = qc
        from backend import taper_curation
        with conn:
            conn.execute("INSERT INTO entries (lb_number, timing, cdr, rating)"
                         " VALUES (1, '', '', '')")
            for i, raw in enumerate(["WalkinDude", "Legendary Taper: Z", "Unknown"]):
                _tuit(conn, 200 + i, 1, raw)
        db.add_taper_alias("walkin dude", "walkin dude", db_path=path)
        cands = taper_curation.tuit_alias_candidates(conn)
        assert cands.get("walkindude") == "walkin dude"
        assert "legendary taper z" not in cands  # builtin alias already
        assert "unknown" not in cands
