"""Tests for backend.qc.review (TODO-342 Phase 2b C11) — the /qc-review read
model and its GET routes.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def qc():
    """Yield (db, store, rules, review, conn, db_path) bound to a throwaway database."""
    tmp_dir = tempfile.mkdtemp(prefix="lbqc_review_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend.qc import review, rules, store
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield db, store, rules, review, conn, db_path
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


_MENTION = [{"kind": "mention", "detail": "mention"}]


# ── review.summary ───────────────────────────────────────────────────────────

class TestSummary:
    def test_counts_per_rule_and_totals(self, qc):
        _db, store, rules, review, conn, _path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
            _insert_event(conn, 1, "1. Song A\n2. Song B\n3. Song C\n")
            _insert_song(conn, 1, 1, "Song A")
            _insert_song(conn, 1, 2, "Song B")
        store.run_rule(conn, rules.RULES["R-T1"])
        store.run_rule(conn, rules.RULES["R-O1"])

        s = review.summary(db_path=_path)
        assert s["total_open_errors"] == 2
        assert s["total_open_warnings"] == 0
        assert s["rules"]["R-T1"]["counts"]["error"]["open"] == 1
        assert s["rules"]["R-T1"]["last_run"]["n_new"] == 1
        assert s["rules"]["R-E1"]["counts"] == {}  # never run
        assert s["last_run_at"] is not None

    def test_every_registered_rule_present_even_unrun(self, qc):
        _db, _store, rules, review, _conn, path = qc
        s = review.summary(db_path=path)
        assert set(s["rules"]) == set(rules.RULES)
        assert s["total_open_errors"] == 0
        assert s["last_run_at"] is None


# ── review.list_findings ─────────────────────────────────────────────────────

class TestListFindings:
    def _seed_two_rules(self, conn, store, rules):
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
            conn.execute(
                "INSERT OR REPLACE INTO entries (lb_number, date_str, timing)"
                " VALUES (7, '3/4/85', 'junk')"
            )
        store.run_rule(conn, rules.RULES["R-T1"])
        store.run_rule(conn, rules.RULES["R-E1"])

    def test_filters_by_rule_severity_status(self, qc):
        _db, store, rules, review, conn, path = qc
        self._seed_two_rules(conn, store, rules)

        all_rows = review.list_findings(db_path=path)
        assert all_rows["total"] == 2

        t1_only = review.list_findings(rule="R-T1", db_path=path)
        assert t1_only["total"] == 1
        assert t1_only["rows"][0]["rule_id"] == "R-T1"
        assert t1_only["rows"][0]["entity_key"] == "8493"
        assert "evidence_json" not in t1_only["rows"][0]

        warns = review.list_findings(severity="warn", db_path=path)
        assert warns["total"] == 1
        assert warns["rows"][0]["rule_id"] == "R-E1"

        open_only = review.list_findings(status="open", db_path=path)
        assert open_only["total"] == 2

        none_confirmed = review.list_findings(status="confirmed", db_path=path)
        assert none_confirmed["total"] == 0

    def test_q_matches_detail_and_entity_key(self, qc):
        _db, store, rules, review, conn, path = qc
        self._seed_two_rules(conn, store, rules)

        by_detail = review.list_findings(q="millard", db_path=path)
        assert by_detail["total"] == 1

        by_key = review.list_findings(q="8493", db_path=path)
        assert by_key["total"] == 1

    def test_pagination(self, qc):
        _db, store, rules, review, conn, path = qc
        self._seed_two_rules(conn, store, rules)

        page1 = review.list_findings(page=1, page_size=1, db_path=path)
        assert page1["total"] == 2
        assert len(page1["rows"]) == 1
        page2 = review.list_findings(page=2, page_size=1, db_path=path)
        assert len(page2["rows"]) == 1
        assert page1["rows"][0]["id"] != page2["rows"][0]["id"]

    def test_shows_affected_resolves_entry_date(self, qc):
        _db, store, rules, review, conn, path = qc
        self._seed_two_rules(conn, store, rules)
        t1 = review.list_findings(rule="R-T1", db_path=path)["rows"][0]
        # entry for 8493 was created with default date_str '1/1/80' by _insert_attr
        assert t1["affected_dates"] == ["1980-01-01"]
        assert t1["shows_affected"] == 1

    def test_date_filter_matches_resolved_entry_date(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96",
                         date_str="3/4/85")
        store.run_rule(conn, rules.RULES["R-T1"])

        hit = review.list_findings(date="1985-03-04", db_path=path)
        assert hit["total"] == 1
        miss = review.list_findings(date="1999-01-01", db_path=path)
        assert miss["total"] == 0


# ── review.get_finding ───────────────────────────────────────────────────────

class TestGetFinding:
    def test_missing_id_returns_none(self, qc):
        _db, _store, _rules, review, _conn, path = qc
        assert review.get_finding(999999, db_path=path) is None

    def test_taper_rule_context_and_evidence(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
        store.run_rule(conn, rules.RULES["R-T1"])

        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-T1'"
        ).fetchone()[0]
        f = review.get_finding(finding_id, db_path=path)
        assert f["rule_id"] == "R-T1"
        assert f["rule_description"]
        assert f["evidence"]["taper"] == "mike millard"
        assert f["context"]["attribution"]["taper_normalised"] == "mike millard"
        assert "MM-EBM-1" in f["context"]["entry"]["description"]
        assert f["quarantined"] is True

    def test_olof_rule_context_shows_raw_vs_parsed(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            _insert_event(conn, 1, "1. Song A\n2. Song B\n3. Song C\n")
            _insert_song(conn, 1, 1, "Song A")
            _insert_song(conn, 1, 2, "Song B")
        store.run_rule(conn, rules.RULES["R-O1"])

        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-O1'"
        ).fetchone()[0]
        f = review.get_finding(finding_id, db_path=path)
        assert f["context"]["event"]["event_id"] == 1
        assert len(f["context"]["parsed_songs"]) == 2
        assert f["affected_dates"] == ["1978-01-01"]

    def test_entry_rule_context(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO entries (lb_number, date_str, timing)"
                " VALUES (7, '3/4/85', 'junk')"
            )
        store.run_rule(conn, rules.RULES["R-E1"])

        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-E1'"
        ).fetchone()[0]
        f = review.get_finding(finding_id, db_path=path)
        assert f["context"]["entry"]["lb_number"] == 7
        assert f["affected_dates"] == ["1985-03-04"]

    def test_s1_context_is_evidence_as_is(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank,"
                " evidence_json, computed_at)"
                " VALUES ('1980-01-01', 1, 1.0, 1, '[]', '2020-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO recording_families (lb_number, fam_id, concert_date, imported_at)"
                " VALUES (1, 'F1', '1980-01-01', '2021-01-01T00:00:00')"
            )
        store.run_rule(conn, rules.RULES["R-S1"])

        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-S1'"
        ).fetchone()[0]
        f = review.get_finding(finding_id, db_path=path)
        assert f["context"] == f["evidence"]


# ── review.list_decisions ────────────────────────────────────────────────────

class TestListDecisions:
    def test_reopen_writes_a_decision_log_row(self, qc):
        _db, store, rules, review, conn, path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
        store.run_rule(conn, rules.RULES["R-T1"])
        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-T1'"
        ).fetchone()[0]
        with conn:
            conn.execute(
                "UPDATE qc_findings SET status='false_positive', decided_by='ui',"
                " decided_at='2026-01-01T00:00:00' WHERE id=?", (finding_id,)
            )
        # Evidence changes (mention detail differs) -> next run reopens it.
        with conn:
            conn.execute(
                "UPDATE taper_attributions SET evidence_json = ? WHERE lb_number = 8493",
                (json.dumps([{"kind": "mention", "detail": "a different mention"}]),),
            )
        store.run_rule(conn, rules.RULES["R-T1"])

        decisions = review.list_decisions(db_path=path)
        assert decisions["total"] == 1
        assert decisions["rows"][0]["new_status"] == "open"
        assert decisions["rows"][0]["finding_id"] == finding_id

        scoped = review.list_decisions(finding_id=finding_id, db_path=path)
        assert scoped["total"] == 1
        other = review.list_decisions(finding_id=999999, db_path=path)
        assert other["total"] == 0


# ── /qc-review routes ────────────────────────────────────────────────────────

class _AppClient:
    """Wires backend.app's create_app() to a temp DB path (mirrors
    tests/test_song_index.py's fixture)."""

    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        import backend.db as db
        import backend.paths as _paths
        self._paths = _paths
        self._db = db
        self._orig_db_path = _paths.DB_PATH
        self._orig_module_db_path = getattr(db, "DB_PATH", None)
        _paths.DB_PATH = self.db_path
        db.DB_PATH = self.db_path
        from backend.app import create_app
        app = create_app()
        return app.test_client()

    def __exit__(self, *exc):
        self._paths.DB_PATH = self._orig_db_path
        if self._orig_module_db_path is not None:
            self._db.DB_PATH = self._orig_module_db_path


class TestRoutes:
    def test_page_serves(self, qc):
        _db, _store, _rules, _review, _conn, path = qc
        with _AppClient(path) as client:
            resp = client.get("/qc-review")
            assert resp.status_code == 200
            assert b"QC Review Console" in resp.data

    def test_summary_route(self, qc):
        _db, _store, _rules, _review, _conn, path = qc
        with _AppClient(path) as client:
            resp = client.get("/api/qc/summary")
            assert resp.status_code == 200
            body = resp.get_json()
            assert "total_open_errors" in body
            assert "rules" in body

    def test_findings_route_and_detail_and_404(self, qc):
        _db, store, rules, _review, conn, path = qc
        with conn:
            _insert_attr(conn, 8493, "mike millard", "propagated", _MENTION,
                         "Source: SP-CMC-8 > MM-EBM-1(Power Supply) > MicroTrack 24/96")
        store.run_rule(conn, rules.RULES["R-T1"])
        finding_id = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-T1'"
        ).fetchone()[0]

        with _AppClient(path) as client:
            resp = client.get("/api/qc/findings?rule=R-T1")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["total"] == 1

            resp = client.get(f"/api/qc/findings/{finding_id}")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["id"] == finding_id
            assert body["context"]["attribution"]["taper_normalised"] == "mike millard"

            resp = client.get("/api/qc/findings/999999")
            assert resp.status_code == 404
            assert resp.get_json()["error"] == "not_found"

    def test_decisions_route(self, qc):
        _db, _store, _rules, _review, _conn, path = qc
        with _AppClient(path) as client:
            resp = client.get("/api/qc/decisions")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["rows"] == []
            assert body["total"] == 0
