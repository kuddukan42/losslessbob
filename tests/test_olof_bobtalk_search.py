"""Tests for TODO-226 Part A remainder: BobTalk/notes full-text search —
``backend.db.get_olof_bobtalk_search`` and ``GET /api/olof/bobtalk_search``.
Follows tests/test_song_index.py's ``_make_db``/``_seed_event``/``_AppClient``
patterns (temp DB via ``db.init_db``, app wired via ``create_app()``).
"""
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_olof_bobtalk_search_test_")
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
                 venue="Massey Hall", city="Toronto", country="Canada",
                 concert_no_net=None, bobtalk="", notes="", page_filename="p1"):
    _seed_page(conn, page_filename)
    conn.execute(
        "INSERT OR REPLACE INTO olof_events"
        " (event_id, page_filename, event_type, date_str, venue, city, country,"
        "  concert_no_net, bobtalk, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, page_filename, event_type, date_str, venue, city, country,
         concert_no_net, bobtalk, notes),
    )


class _AppClient:
    """Context manager wiring backend.app's create_app() to a temp DB path."""

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


# ── db.get_olof_bobtalk_search ──────────────────────────────────────────────


def test_match_in_bobtalk():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_event(
            conn, 1, date_str="2000-07-28",
            bobtalk="Bob said something about Elvis Presley tonight.",
        )
        conn.commit()

        hits = db.get_olof_bobtalk_search("Elvis", db_path=db_path)
        assert len(hits) == 1
        assert hits[0]["event_id"] == 1
        assert hits[0]["field"] == "bobtalk"
        assert "Elvis" in hits[0]["snippet"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_match_in_notes():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_event(
            conn, 1, date_str="2000-07-28",
            notes="An unusually short show, cut short by a curfew.",
        )
        conn.commit()

        hits = db.get_olof_bobtalk_search("curfew", db_path=db_path)
        assert len(hits) == 1
        assert hits[0]["field"] == "notes"
        assert "curfew" in hits[0]["snippet"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_match_in_both_fields_dedupes_to_bobtalk_only():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_event(
            conn, 1, date_str="2000-07-28",
            bobtalk="Bob mentioned the harmonica again.",
            notes="The harmonica solo ran long tonight.",
        )
        conn.commit()

        hits = db.get_olof_bobtalk_search("harmonica", db_path=db_path)
        assert len(hits) == 1
        assert hits[0]["field"] == "bobtalk"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_like_wildcards_are_escaped_and_match_literally():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        # If '_' were left as a SQL LIKE single-char wildcard, "j_ke" would
        # also match "joke" here — it must not, once escaped.
        _seed_event(
            conn, 1, date_str="2000-07-28",
            bobtalk="He told a joke about deja vu tonight.",
        )
        # Contains the literal substring "j_ke" — this is the only row that
        # should match once the underscore is treated literally.
        _seed_event(
            conn, 2, date_str="2000-07-29",
            bobtalk="A literal j_ke placeholder shows up in this transcript.",
        )
        conn.commit()

        hits = db.get_olof_bobtalk_search("j_ke", db_path=db_path)
        assert [h["event_id"] for h in hits] == [2]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ordering_bobtalk_before_notes_then_date_ascending():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        # notes hit, earlier date
        _seed_event(conn, 1, date_str="1999-01-01", notes="mumbled a joke to the band")
        # bobtalk hit, later date
        _seed_event(conn, 2, date_str="2001-01-01", bobtalk="told a joke about the band")
        # bobtalk hit, earlier date
        _seed_event(conn, 3, date_str="1998-01-01", bobtalk="another joke here")
        conn.commit()

        hits = db.get_olof_bobtalk_search("joke", db_path=db_path)
        assert [h["event_id"] for h in hits] == [3, 2, 1]
        assert [h["field"] for h in hits] == ["bobtalk", "bobtalk", "notes"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_limit_caps_results():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        for i in range(5):
            _seed_event(
                conn, i + 1, date_str=f"2000-01-0{i + 1}",
                bobtalk="repeated phrase every night",
            )
        conn.commit()

        hits = db.get_olof_bobtalk_search("repeated", limit=3, db_path=db_path)
        assert len(hits) == 3
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_blank_query_returns_empty_list():
    db_path, tmp_dir = _make_db()
    try:
        assert db.get_olof_bobtalk_search("  ", db_path=db_path) == []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/olof/bobtalk_search ────────────────────────────────────────────


def test_route_returns_hits():
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        _seed_event(
            conn, 1, date_str="2000-07-28", venue="Massey Hall",
            bobtalk="Bob said something about Elvis Presley tonight.",
        )
        conn.commit()

        with _AppClient(db_path) as client:
            resp = client.get("/api/olof/bobtalk_search?q=Elvis")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["q"] == "Elvis"
            assert len(body["hits"]) == 1
            assert body["hits"][0]["venue"] == "Massey Hall"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_route_400_on_missing_or_short_q():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/olof/bobtalk_search")
            assert resp.status_code == 400

            resp = client.get("/api/olof/bobtalk_search?q=a")
            assert resp.status_code == 400

            resp = client.get("/api/olof/bobtalk_search?q=  a ")
            assert resp.status_code == 400
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_route_caps_limit_at_200():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.get("/api/olof/bobtalk_search?q=xy&limit=9999")
            assert resp.status_code == 200
            assert resp.get_json()["hits"] == []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
