"""Tests for FABLE_UNIFIED_RANKING phases 3-4: the Library payload extension
(pick_rank/abs_grade/curated merged onto get_performances()'s recordings),
the curated_lists CRUD routes (TODO-181 remainder), and the
GET /api/picks/for/<lb> evidence lookup used by gui_next's EvidenceList.
"""
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import concert_ranker.picks as picks


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_library_picks_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, date_str, location="Test Venue", rating=None, lb_category="concert"):
    conn.execute(
        "INSERT OR REPLACE INTO entries"
        " (lb_number, date_str, location, rating, description, status, lb_category)"
        " VALUES (?, ?, ?, ?, '', 'ok', ?)",
        (lb, date_str, location, rating, lb_category),
    )
    conn.commit()


def _seed_curated_list(conn, name, lb_numbers):
    cur = conn.execute("INSERT INTO curated_lists(name, label) VALUES (?, ?)", (name, name))
    list_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO curated_list_entries(list_id, lb_number) VALUES (?, ?)",
        [(list_id, lb) for lb in lb_numbers],
    )
    conn.commit()


def _seed_quality(conn, lb, scan_id=1, abs_score=None, abs_grade=None):
    from concert_ranker.lb import repo as cr_repo
    cr_repo.ensure_schema(conn)  # adds abs_score/abs_grade columns (later migration)
    conn.execute(
        "INSERT OR REPLACE INTO quality_recording_scores"
        " (lb_number, scan_id, abs_score, abs_grade) VALUES (?, ?, ?, ?)",
        (lb, scan_id, abs_score, abs_grade),
    )
    conn.commit()


class _AppClient:
    """Context manager wiring backend.app's create_app() to a temp DB path,
    mirroring tests/test_show_picks.py's derived-recompute test pattern.
    """

    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self._orig_db_path = _paths.DB_PATH
        self._orig_module_db_path = getattr(db, "DB_PATH", None)
        _paths.DB_PATH = self.db_path
        db.DB_PATH = self.db_path
        from backend.app import create_app
        app = create_app()
        return app.test_client()

    def __exit__(self, *exc):
        _paths.DB_PATH = self._orig_db_path
        if self._orig_module_db_path is not None:
            db.DB_PATH = self._orig_module_db_path


# ── get_performances() payload extension ─────────────────────────────────────

def test_performances_payload_carries_pick_rank_grade_and_curated():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 100, "6/1/00", rating="A")
    _seed_entry(conn, 101, "6/1/00", rating="C")
    _seed_curated_list(conn, "carbonbit", [100])
    _seed_quality(conn, 100, abs_score=88.0, abs_grade="A-")

    picks.recompute(db_path=db_path)

    perfs = db.get_performances(db_path=db_path)
    show = next(p for p in perfs if p["date"] == "2000-06-01")
    recs = {r["lbNumber"]: r for r in show["recordings"]}

    assert recs[100]["pickRank"] == 1
    assert recs[100]["absGrade"] == "A-"
    assert recs[100]["curated"] == ["carbonbit"]
    # LB 101 has no quality scan and no curated-list membership: omitted, not null-faked.
    assert "absGrade" not in recs[101]
    assert "curated" not in recs[101]
    assert recs[101]["pickRank"] == 2

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_performances_payload_omits_pick_fields_pre_recompute():
    """Before show_picks has ever been computed, the new fields are simply
    absent (spec acceptance: no UI regression when show_picks is empty)."""
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 200, "7/1/00", rating="B")

    perfs = db.get_performances(db_path=db_path)
    show = next(p for p in perfs if p["date"] == "2000-07-01")
    rec = show["recordings"][0]

    assert "pickRank" not in rec
    assert "absGrade" not in rec
    assert "curated" not in rec

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/picks/for/<lb> ───────────────────────────────────────────────────

def test_picks_for_lb_returns_evidence_and_204_when_absent():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 300, "8/1/00", rating="A+")
    db.set_curator(False, db_path)
    picks.recompute(db_path=db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/picks/for/300")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["pick_rank"] == 1
        assert body["lb_number"] == 300
        assert isinstance(body["evidence"], list)
        assert any(e["kind"] == "rating" for e in body["evidence"])

        resp_missing = client.get("/api/picks/for/999999")
        assert resp_missing.status_code == 204

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── /api/curated_lists CRUD ───────────────────────────────────────────────────

def test_curated_lists_get_is_open_and_lists_seed_data():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_curated_list(conn, "carbonbit", [1, 2])
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/curated_lists")
        assert resp.status_code == 200
        names = {row["name"] for row in resp.get_json()}
        assert "carbonbit" in names

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_curated_lists_post_delete_are_curator_gated():
    db_path, tmp_dir = _make_db()
    db.init_db(db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/curated_lists", json={"name": "wtrf"})
        assert resp.status_code == 403

        resp = client.delete("/api/curated_lists/wtrf")
        assert resp.status_code == 403

    db.set_curator(True, db_path)
    with _AppClient(db_path) as client:
        resp = client.post("/api/curated_lists", json={"name": "wtrf", "label": "WTRF thread"})
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "wtrf"

        resp = client.get("/api/curated_lists")
        assert any(row["name"] == "wtrf" for row in resp.get_json())

        resp = client.delete("/api/curated_lists/wtrf")
        assert resp.status_code == 200

        resp = client.get("/api/curated_lists")
        assert not any(row["name"] == "wtrf" for row in resp.get_json())

        resp = client.delete("/api/curated_lists/does_not_exist")
        assert resp.status_code == 404

    shutil.rmtree(tmp_dir, ignore_errors=True)
