"""Tests for LISTENING spec §9 "this night in Dylan history": the
concert_date_iso population on show_picks (concert_ranker/picks.py),
GET /api/picks?date=, and GET /api/picks/tonight.
"""
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import concert_ranker.picks as picks
from concert_ranker.picks import _parse_concert_date_iso


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_picks_tonight_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, date_str, location="Test Venue", rating=None,
                 description="", lb_category="concert"):
    conn.execute(
        "INSERT OR REPLACE INTO entries"
        " (lb_number, date_str, location, rating, description, status, lb_category)"
        " VALUES (?, ?, ?, ?, ?, 'ok', ?)",
        (lb, date_str, location, rating, description, lb_category),
    )
    conn.commit()


class _AppClient:
    """Context manager wiring backend.app's create_app() to a temp DB path,
    mirroring tests/test_library_picks_api.py's pattern.
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


# ── _parse_concert_date_iso ───────────────────────────────────────────────────

def test_parse_concert_date_iso_full_date():
    assert _parse_concert_date_iso("7/28/00") == "2000-07-28"
    assert _parse_concert_date_iso("2/11/74") == "1974-02-11"


def test_parse_concert_date_iso_century_pivot():
    # pivot at 30, matching backend/bootleg_scraper.py's _YEAR_PIVOT:
    # >=30 -> 19xx, <30 -> 20xx
    assert _parse_concert_date_iso("1/1/29") == "2029-01-01"
    assert _parse_concert_date_iso("1/1/30") == "1930-01-01"
    assert _parse_concert_date_iso("1/1/99") == "1999-01-01"
    assert _parse_concert_date_iso("1/1/00") == "2000-01-01"


def test_parse_concert_date_iso_xx_placeholders_are_none():
    assert _parse_concert_date_iso("5/xx/87") is None
    assert _parse_concert_date_iso("xx/xx/87") is None
    assert _parse_concert_date_iso("xx/28/00") is None


def test_parse_concert_date_iso_unparseable_is_none():
    assert _parse_concert_date_iso("") is None
    assert _parse_concert_date_iso("not a date") is None
    assert _parse_concert_date_iso("13/40/00") is None  # invalid calendar date


# ── recompute() populates concert_date_iso ────────────────────────────────────

def test_recompute_populates_concert_date_iso_and_nulls_xx():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 100, "7/28/00", rating="A")
    _seed_entry(conn, 101, "5/xx/87", rating="B")

    picks.recompute(db_path=db_path)

    row100 = conn.execute(
        "SELECT concert_date_iso FROM show_picks WHERE lb_number=100"
    ).fetchone()
    row101 = conn.execute(
        "SELECT concert_date_iso FROM show_picks WHERE lb_number=101"
    ).fetchone()
    assert row100["concert_date_iso"] == "2000-07-28"
    assert row101["concert_date_iso"] is None

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/picks?date= ───────────────────────────────────────────────────────

def test_picks_for_date_happy_and_400():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 200, "6/1/00", rating="A")
    _seed_entry(conn, 201, "6/1/00", rating="C")
    picks.recompute(db_path=db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/picks?date=2000-06-01")
        assert resp.status_code == 200
        body = resp.get_json()
        assert [row["pick_rank"] for row in body] == [1, 2]
        assert body[0]["lb_number"] == 200

        resp_empty = client.get("/api/picks?date=1975-01-01")
        assert resp_empty.status_code == 200
        assert resp_empty.get_json() == []

        resp_missing = client.get("/api/picks")
        assert resp_missing.status_code == 400

        resp_bad = client.get("/api/picks?date=not-a-date")
        assert resp_bad.status_code == 400

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/picks/tonight ─────────────────────────────────────────────────────

def test_picks_tonight_mmdd_override_and_empty():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 300, "7/28/00", rating="A+", location="Portland, OR",
                description="a great show")
    _seed_entry(conn, 301, "7/28/95", rating="B", location="Boston, MA")
    _seed_entry(conn, 302, "3/1/00", rating="A")  # different day, should be excluded
    picks.recompute(db_path=db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/picks/tonight?mmdd=07-28")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["mmdd"] == "07-28"
        lb_numbers = {c["lb_number"] for c in body["candidates"]}
        assert lb_numbers == {300, 301}
        c300 = next(c for c in body["candidates"] if c["lb_number"] == 300)
        assert c300["year"] == 2000
        assert c300["location"] == "Portland, OR"
        assert c300["rating"] == "A+"
        assert c300["description"] == "a great show"
        assert "pick_score" in c300

        resp_empty = client.get("/api/picks/tonight?mmdd=12-25")
        assert resp_empty.status_code == 200
        assert resp_empty.get_json()["candidates"] == []

        resp_bad = client.get("/api/picks/tonight?mmdd=bogus")
        assert resp_bad.status_code == 400

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_picks_tonight_defaults_to_server_today():
    db_path, tmp_dir = _make_db()
    with _AppClient(db_path) as client:
        resp = client.get("/api/picks/tonight")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["mmdd"]) == 5 and body["mmdd"][2] == "-"
        assert body["candidates"] == []

    shutil.rmtree(tmp_dir, ignore_errors=True)
