"""Tests for backend.qc.decisions and backend.qc.jobs (TODO-342 Phase 2b C12)
and the curator-gated write routes they back.

All tests use a temp-file DB -- the real data/losslessbob.db is never touched.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time

import pytest


@pytest.fixture
def qc():
    """Yield (db, store, rules, decisions, conn, db_path) on a throwaway database."""
    tmp_dir = tempfile.mkdtemp(prefix="lbqc_decisions_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend.qc import decisions, rules, store
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute("INSERT INTO olof_pages (filename) VALUES ('test.htm')")
    try:
        yield db, store, rules, decisions, conn, db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _insert_finding(conn, rule_id="R-G1", entity_kind="venue", entity_key="v:c",
                     severity="error", status="open", evidence_hash="h1"):
    conn.execute(
        "INSERT INTO qc_findings (rule_id, entity_kind, entity_key, severity, detail,"
        " evidence_json, evidence_hash, first_seen, last_seen, status) VALUES"
        " (?, ?, ?, ?, 'detail', '{}', ?, '2026-01-01T00:00:00', '2026-01-01T00:00:00', ?)",
        (rule_id, entity_kind, entity_key, severity, evidence_hash, status),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ── backend.qc.decisions.decide ─────────────────────────────────────────────

class TestDecide:
    def test_confirms_from_open_and_logs(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
        updated = decisions.decide(conn, fid, "confirmed", note="looks real")
        assert updated["status"] == "confirmed"
        assert updated["decided_by"] == "ui"
        assert updated["note"] == "looks real"

        log = conn.execute(
            "SELECT * FROM qc_decision_log WHERE finding_id=?", (fid,)
        ).fetchone()
        assert log["prev_status"] == "open"
        assert log["new_status"] == "confirmed"

    def test_false_positive_from_confirmed(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="confirmed")
        updated = decisions.decide(conn, fid, "false_positive")
        assert updated["status"] == "false_positive"

    def test_re_decide_false_positive_to_confirmed(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="false_positive")
        updated = decisions.decide(conn, fid, "confirmed")
        assert updated["status"] == "confirmed"

    def test_fixed_raises_value_error(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="fixed")
        with pytest.raises(ValueError):
            decisions.decide(conn, fid, "confirmed")

    def test_corrected_raises_value_error(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="corrected")
        with pytest.raises(ValueError):
            decisions.decide(conn, fid, "confirmed")

    def test_missing_finding_raises_value_error(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with pytest.raises(ValueError):
            decisions.decide(conn, 999999, "confirmed")

    def test_bad_status_raises_value_error(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
        with pytest.raises(ValueError):
            decisions.decide(conn, fid, "fixed")


# ── backend.qc.decisions.bulk_decide ────────────────────────────────────────

class TestBulkDecide:
    def test_bulk_confirms_same_rule(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            a = _insert_finding(conn, rule_id="R-G1", entity_key="a", status="open")
            b = _insert_finding(conn, rule_id="R-G1", entity_key="b", status="open")
        results = decisions.bulk_decide(conn, [a, b], "confirmed")
        assert {r["status"] for r in results} == {"confirmed"}
        assert conn.execute(
            "SELECT COUNT(*) FROM qc_decision_log"
        ).fetchone()[0] == 2

    def test_mixed_rule_raises_and_writes_nothing(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            a = _insert_finding(conn, rule_id="R-G1", entity_key="a", status="open")
            b = _insert_finding(conn, rule_id="R-E1", entity_key="b", status="open")
        with pytest.raises(ValueError):
            decisions.bulk_decide(conn, [a, b], "confirmed")
        row_a = conn.execute("SELECT status FROM qc_findings WHERE id=?", (a,)).fetchone()
        row_b = conn.execute("SELECT status FROM qc_findings WHERE id=?", (b,)).fetchone()
        assert row_a["status"] == "open"
        assert row_b["status"] == "open"
        assert conn.execute("SELECT COUNT(*) FROM qc_decision_log").fetchone()[0] == 0

    def test_illegal_transition_writes_nothing(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            a = _insert_finding(conn, rule_id="R-G1", entity_key="a", status="open")
            b = _insert_finding(conn, rule_id="R-G1", entity_key="b", status="fixed")
        with pytest.raises(ValueError):
            decisions.bulk_decide(conn, [a, b], "confirmed")
        row_a = conn.execute("SELECT status FROM qc_findings WHERE id=?", (a,)).fetchone()
        assert row_a["status"] == "open"
        assert conn.execute("SELECT COUNT(*) FROM qc_decision_log").fetchone()[0] == 0

    def test_empty_ids_raises(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with pytest.raises(ValueError):
            decisions.bulk_decide(conn, [], "confirmed")


# ── backend.qc.decisions.add_correction ─────────────────────────────────────

class TestAddCorrection:
    def test_writes_row_and_marks_corrected(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, entity_kind="venue", entity_key="v:c", status="open")
        result = decisions.add_correction(
            conn, fid, "venue", "Willie Dixon", reason="misspelling", original="Wille Dixon",
        )
        assert result["correction"]["field"] == "venue"
        assert result["correction"]["original"] == "Wille Dixon"
        assert result["correction"]["corrected"] == "Willie Dixon"
        assert result["correction"]["entity_kind"] == "venue"
        assert result["correction"]["entity_key"] == "v:c"
        assert result["finding"]["status"] == "corrected"

        log = conn.execute(
            "SELECT * FROM qc_decision_log WHERE finding_id=?", (fid,)
        ).fetchone()
        assert log["new_status"] == "corrected"

    def test_fixed_finding_raises(self, qc):
        _db, _store, _rules, decisions, conn, _path = qc
        with conn:
            fid = _insert_finding(conn, status="fixed")
        with pytest.raises(ValueError):
            decisions.add_correction(conn, fid, "venue", "x")


# ── false_positive lifts quarantine, evidence change reopens it ────────────

class TestReopenOnEvidenceChange:
    def test_false_positive_then_changed_evidence_reopens(self, qc):
        _db, store, rules, decisions, conn, path = qc
        calls = {"n": 0}

        def stub_rule(conn):
            # Runs 1-2: identical evidence (the geocode row hasn't changed).
            # Run 3: the evidence text differs, as if the geocode row was
            # edited -- the hash changes underneath a sticky false_positive
            # decision and the finding should reopen.
            calls["n"] += 1
            confidence = 0.1 if calls["n"] < 3 else 0.9
            yield rules.Finding(
                entity_kind="venue", entity_key="v:c", severity="error",
                detail="low confidence", evidence={"confidence": confidence},
            )

        rule = rules.RuleDef(rule_id="R-STUB", description="stub", severity="error",
                             func=stub_rule)

        store.run_rule(conn, rule)
        fid = conn.execute(
            "SELECT id FROM qc_findings WHERE rule_id='R-STUB'"
        ).fetchone()["id"]
        assert store.quarantined(conn, "venue", "v:c") == ["R-STUB"]

        decisions.decide(conn, fid, "false_positive")
        assert store.quarantined(conn, "venue", "v:c") == []

        # Same evidence again: stays false_positive, still lifted.
        store.run_rule(conn, rule)
        row = conn.execute("SELECT status FROM qc_findings WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "false_positive"
        assert store.quarantined(conn, "venue", "v:c") == []

        # Evidence changes: reopens.
        store.run_rule(conn, rule)
        row = conn.execute("SELECT status FROM qc_findings WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "open"
        assert store.quarantined(conn, "venue", "v:c") == ["R-STUB"]


# ── routes ───────────────────────────────────────────────────────────────────

class _AppClient:
    """Point backend.app at a temp DB path and hand back a Flask test client."""

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


class TestDecisionRoute:
    def test_403_when_curator_off(self, qc):
        _db, _store, _rules, _decisions, conn, path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
        with _AppClient(path) as client:
            resp = client.post(f"/api/qc/findings/{fid}/decision",
                                json={"status": "confirmed"})
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "curator_required"

    def test_confirm_then_404_then_409(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
            fixed_id = _insert_finding(conn, entity_key="z", status="fixed")
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.post(f"/api/qc/findings/{fid}/decision",
                                json={"status": "confirmed"})
            assert resp.status_code == 200
            assert resp.get_json()["finding"]["status"] == "confirmed"

            resp = client.post("/api/qc/findings/999999/decision",
                                json={"status": "confirmed"})
            assert resp.status_code == 404

            resp = client.post(f"/api/qc/findings/{fixed_id}/decision",
                                json={"status": "confirmed"})
            assert resp.status_code == 409

    def test_bad_body_400(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.post(f"/api/qc/findings/{fid}/decision", json={"status": "nope"})
            assert resp.status_code == 400


class TestBulkRoute:
    def test_403_when_curator_off(self, qc):
        _db, _store, _rules, _decisions, conn, path = qc
        with _AppClient(path) as client:
            resp = client.post("/api/qc/findings/bulk", json={"ids": [1], "status": "confirmed"})
            assert resp.status_code == 403

    def test_mixed_rule_400(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        with conn:
            a = _insert_finding(conn, rule_id="R-G1", entity_key="a", status="open")
            b = _insert_finding(conn, rule_id="R-E1", entity_key="b", status="open")
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.post("/api/qc/findings/bulk",
                                json={"ids": [a, b], "status": "confirmed"})
            assert resp.status_code == 400


class TestCorrectionsRoute:
    def test_403_when_curator_off(self, qc):
        _db, _store, _rules, _decisions, conn, path = qc
        with _AppClient(path) as client:
            resp = client.post("/api/qc/corrections",
                                json={"finding_id": 1, "field": "venue", "corrected": "x"})
            assert resp.status_code == 403

    def test_success(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        with conn:
            fid = _insert_finding(conn, status="open")
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.post("/api/qc/corrections", json={
                "finding_id": fid, "field": "venue", "corrected": "Willie Dixon",
                "reason": "typo",
            })
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["finding"]["status"] == "corrected"


class TestRunRoute:
    def test_403_when_curator_off(self, qc):
        _db, _store, _rules, _decisions, conn, path = qc
        with _AppClient(path) as client:
            resp = client.post("/api/qc/run", json={})
            assert resp.status_code == 403

    def test_start_poll_and_409_while_running(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.get("/api/qc/run")
            assert resp.status_code == 200
            assert resp.get_json()["running"] is False

            resp = client.post("/api/qc/run", json={})
            assert resp.status_code == 200

            # A second start while the first may still be running (or has
            # already finished, since the rule set here is tiny/fast) must
            # never 500; assert on the documented contract instead of timing.
            resp2 = client.post("/api/qc/run", json={})
            assert resp2.status_code in (200, 409)

            deadline = time.time() + 5
            while time.time() < deadline:
                status = client.get("/api/qc/run").get_json()
                if not status["running"]:
                    break
                time.sleep(0.05)
            assert status["running"] is False
            assert status.get("stage") == "done"

    def test_unknown_rule_400(self, qc):
        db, _store, _rules, _decisions, conn, path = qc
        db.set_curator(True, path)
        with _AppClient(path) as client:
            resp = client.post("/api/qc/run", json={"rule_id": "R-NOPE"})
            assert resp.status_code == 400
