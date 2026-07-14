"""Tests for backend.setlist_fingerprint (TODO-225): candidate-entry
selection (no clean date / skipped_not_concert bucket only — not bulk
re-dating), event scoring (coverage + order + containment-tolerant title
matching), the wholesale-recompute scan with dismissed-status preservation,
and the three /api/fingerprint/* routes (incl. curator gating on dismiss).
"""
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import backend.setlist_fingerprint as sf


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_fingerprint_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_page(conn, filename="p1"):
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
        (filename,),
    )


def _seed_event(conn, event_id, date_str="2000-07-28", event_type="concert",
                 venue="Massey Hall", city="Toronto", page_filename="p1"):
    _seed_page(conn, page_filename)
    conn.execute(
        "INSERT OR REPLACE INTO olof_events"
        " (event_id, page_filename, event_type, date_str, venue, city)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, page_filename, event_type, date_str, venue, city),
    )


def _seed_song(conn, event_id, position, song_title):
    conn.execute(
        "INSERT OR REPLACE INTO olof_songs (event_id, position, song_title) VALUES (?, ?, ?)",
        (event_id, position, song_title),
    )


def _seed_entry(conn, lb, date_str, location="", setlist=""):
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, date_str, location, setlist, status)"
        " VALUES (?, ?, ?, ?, 'ok')",
        (lb, date_str, location, setlist),
    )


def _seed_skipped_location(conn, location_text):
    conn.execute(
        "INSERT OR REPLACE INTO location_geocoded (location_text, source) VALUES (?, 'skipped_not_concert')",
        (location_text,),
    )


class _AppClient:
    """Wires backend.app's create_app() to a temp DB path (mirrors
    tests/test_song_index.py's fixture)."""

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


_SETLIST = "1. Tangled Up In Blue, 2. Simple Twist Of Fate, 3. Blowin' In The Wind (acoustic)"


# ── _find_candidate_entries ───────────────────────────────────────────────────

def test_candidate_entries_include_no_date_and_skipped_location_only():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, date_str="", location="various", setlist=_SETLIST)
    _seed_entry(conn, 2, date_str="various 98-99", location="Chicago", setlist=_SETLIST)
    _seed_entry(conn, 3, date_str="7/28/00", location="Chicago", setlist=_SETLIST)
    _seed_skipped_location(conn, "various")
    conn.commit()

    candidates = {r["lb_number"] for r in sf._find_candidate_entries(conn)}
    assert candidates == {1, 2}  # 3 has a clean date and a non-skipped location

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_candidate_entries_skips_blank_setlist():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, date_str="", location="various", setlist="")
    conn.commit()

    assert sf._find_candidate_entries(conn) == []

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── _score_event ──────────────────────────────────────────────────────────────

def test_score_event_matches_containment_and_preserves_order():
    from backend.db import normalize_title_for_match

    olof = [
        (1, "Tangled Up In Blue", normalize_title_for_match("Tangled Up In Blue")),
        (2, "Simple Twist Of Fate", normalize_title_for_match("Simple Twist Of Fate")),
        (3, "Blowin' in the Wind", normalize_title_for_match("Blowin' in the Wind")),
        (4, "Like A Rolling Stone", normalize_title_for_match("Like A Rolling Stone")),
    ]
    entry_norms = [
        normalize_title_for_match(t) for t in
        ["Tangled Up in Blue", "Simple Twist of Fate", "Blowin' In The Wind (acoustic)"]
    ]

    result = sf._score_event(entry_norms, olof)
    assert result["matched_count"] == 3
    assert result["entry_coverage"] == 1.0
    assert result["order_score"] == 1.0  # matched positions 1,2,3 strictly increasing
    assert result["olof_coverage"] == 0.75  # 3 of 4 olof songs covered
    assert result["missing"] == ["Like A Rolling Stone"]
    assert 0 < result["score"] <= 1


def test_score_event_shuffled_order_scores_lower_than_in_order():
    from backend.db import normalize_title_for_match

    olof = [
        (1, "A", normalize_title_for_match("A")),
        (2, "B", normalize_title_for_match("B")),
        (3, "C", normalize_title_for_match("C")),
    ]
    in_order = sf._score_event([normalize_title_for_match(t) for t in ["A", "B", "C"]], olof)
    shuffled = sf._score_event([normalize_title_for_match(t) for t in ["C", "A", "B"]], olof)
    assert in_order["order_score"] == 1.0
    assert shuffled["order_score"] < 1.0
    assert in_order["score"] > shuffled["score"]


def test_score_event_returns_none_when_nothing_matches():
    from backend.db import normalize_title_for_match

    olof = [(1, "A", normalize_title_for_match("A"))]
    entry_norms = [normalize_title_for_match("Totally Unrelated Title")]
    assert sf._score_event(entry_norms, olof) is None


# ── run_fingerprint_scan ───────────────────────────────────────────────────────

def test_run_fingerprint_scan_writes_top_match_and_ignores_dated_entries():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 100, date_str="1975-01-14")
    _seed_song(conn, 100, 1, "Tangled Up In Blue")
    _seed_song(conn, 100, 2, "Simple Twist Of Fate")
    _seed_song(conn, 100, 3, "Blowin' in the Wind")
    # unrelated event sharing zero songs — must not appear as a match
    _seed_event(conn, 200, date_str="1990-06-01", venue="Other Hall")
    _seed_song(conn, 200, 1, "Highway 61 Revisited")

    _seed_entry(conn, 1, date_str="", location="various", setlist=_SETLIST)
    conn.commit()

    stats = sf.run_fingerprint_scan(db_path=db_path)
    assert stats["candidates_scanned"] == 1
    assert stats["candidates_matched"] == 1
    assert stats["suggestions_written"] == 1

    suggestions = sf.get_suggestions(status="all", db_path=db_path)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["lb_number"] == 1
    assert s["event_id"] == 100
    assert s["rank"] == 1
    assert s["status"] == "pending"
    assert s["matched_count"] == 3
    assert len(s["matched"]) == 3
    assert s["missing"] == []

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_run_fingerprint_scan_preserves_dismissed_status_across_rescan():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 100, date_str="1975-01-14")
    _seed_song(conn, 100, 1, "Tangled Up In Blue")
    _seed_song(conn, 100, 2, "Simple Twist Of Fate")
    _seed_entry(conn, 1, date_str="", location="various", setlist=_SETLIST)
    conn.commit()

    sf.run_fingerprint_scan(db_path=db_path)
    ok = sf.dismiss_suggestion(1, 100, db_path=db_path)
    assert ok is True

    # Rescan with unchanged input must not resurrect the dismissed row.
    sf.run_fingerprint_scan(db_path=db_path)
    suggestions = sf.get_suggestions(status="all", db_path=db_path)
    assert suggestions[0]["status"] == "dismissed"

    pending = sf.get_suggestions(status="pending", db_path=db_path)
    assert pending == []

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dismiss_suggestion_returns_false_when_no_match():
    db_path, tmp_dir = _make_db()
    assert sf.dismiss_suggestion(999, 999, db_path=db_path) is False
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Routes ──────────────────────────────────────────────────────────────────

def test_scan_and_list_routes():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 100, date_str="1975-01-14")
    _seed_song(conn, 100, 1, "Tangled Up In Blue")
    _seed_song(conn, 100, 2, "Simple Twist Of Fate")
    _seed_entry(conn, 1, date_str="", location="various", setlist=_SETLIST)
    conn.commit()
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/fingerprint/scan", json={})
        assert resp.status_code == 200
        assert resp.get_json()["suggestions_written"] == 1

        resp = client.get("/api/fingerprint/suggestions")
        assert resp.status_code == 200
        suggestions = resp.get_json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["lb_number"] == 1
        assert suggestions[0]["venue"] == "Massey Hall"

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dismiss_route_is_curator_gated():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 100, date_str="1975-01-14")
    _seed_song(conn, 100, 1, "Tangled Up In Blue")
    _seed_song(conn, 100, 2, "Simple Twist Of Fate")
    _seed_entry(conn, 1, date_str="", location="various", setlist=_SETLIST)
    conn.commit()
    sf.run_fingerprint_scan(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/fingerprint/suggestions/dismiss", json={"lb_number": 1, "event_id": 100})
        assert resp.status_code == 403

    db.set_curator(True, db_path)
    with _AppClient(db_path) as client:
        resp = client.post("/api/fingerprint/suggestions/dismiss", json={"lb_number": 1, "event_id": 100})
        assert resp.status_code == 200

        resp = client.post("/api/fingerprint/suggestions/dismiss", json={"lb_number": 999, "event_id": 999})
        assert resp.status_code == 404

    shutil.rmtree(tmp_dir, ignore_errors=True)
