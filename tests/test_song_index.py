"""Tests for backend.song_index (LISTENING spec §3, TODO-230): the
normalisation function, song_canonical seeding + curator-row preservation,
song_performances recompute idempotency, and the three /api/songs routes
(incl. 404 + curator gating).
"""
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import backend.song_index as song_index


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_song_index_test_")
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


def _seed_song(conn, event_id, position, song_title, is_encore=0, take_status=""):
    conn.execute(
        "INSERT OR REPLACE INTO olof_songs"
        " (event_id, position, song_title, is_encore, take_status)"
        " VALUES (?, ?, ?, ?, ?)",
        (event_id, position, song_title, is_encore, take_status),
    )


def _seed_entry(conn, lb, date_str, rating=None):
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, date_str, rating, description, status)"
        " VALUES (?, ?, ?, '', 'ok')",
        (lb, date_str, rating),
    )


class _AppClient:
    """Wires backend.app's create_app() to a temp DB path (mirrors
    tests/test_library_picks_api.py's fixture)."""

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


# ── normalize_song_title ──────────────────────────────────────────────────────

def test_normalize_unifies_curly_and_straight_apostrophes():
    assert song_index.normalize_song_title("Don't Think Twice") == \
        song_index.normalize_song_title("Don’t Think Twice")


def test_normalize_casefolds():
    assert song_index.normalize_song_title("VISIONS OF JOHANNA") == "visions of johanna"
    assert song_index.normalize_song_title("Visions Of Johanna") == "visions of johanna"


def test_normalize_strips_punctuation_to_spaces_and_collapses_whitespace():
    assert song_index.normalize_song_title("Rainy Day Women #12 & 35") == \
        "rainy day women 12 35"
    assert song_index.normalize_song_title("Mr.   Tambourine   Man!") == "mr tambourine man"


def test_normalize_blank_and_none():
    assert song_index.normalize_song_title("") == ""
    assert song_index.normalize_song_title("   ") == ""
    assert song_index.normalize_song_title(None) == ""


# ── song_canonical seeding + curator-row preservation ─────────────────────────

def test_seeding_picks_most_frequent_spelling_deterministically():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1)
    _seed_event(conn, 2, date_str="2000-07-29")
    _seed_event(conn, 3, date_str="2000-07-30")
    # "Visions of Johanna" appears twice, "VISIONS OF JOHANNA" once -> the
    # lowercase-title spelling should win as canonical.
    _seed_song(conn, 1, 1, "Visions of Johanna")
    _seed_song(conn, 2, 1, "Visions of Johanna")
    _seed_song(conn, 3, 1, "VISIONS OF JOHANNA")
    conn.commit()

    stats = song_index.run(db_path=db_path)
    assert stats["performances_written"] == 3
    assert stats["distinct_songs"] == 1

    norm = song_index.normalize_song_title("Visions of Johanna")
    row = conn.execute(
        "SELECT canonical, source FROM song_canonical WHERE alias_norm=?", (norm,)
    ).fetchone()
    assert row["canonical"] == "Visions of Johanna"
    assert row["source"] == "auto"

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_seeding_never_overwrites_curator_row():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1)
    _seed_song(conn, 1, 1, "visions of johanna")  # lowercase would normally win the tie-break
    conn.commit()

    song_index.run(db_path=db_path)
    norm = song_index.normalize_song_title("Visions of Johanna")

    # Curator hand-edits the display spelling.
    song_index.upsert_alias("Visions of Johanna", "Visions Of Johanna (curator spelling)",
                             db_path=db_path)
    row = conn.execute(
        "SELECT canonical, source FROM song_canonical WHERE alias_norm=?", (norm,)
    ).fetchone()
    assert row["canonical"] == "Visions Of Johanna (curator spelling)"
    assert row["source"] == "curator"

    # Add more auto-frequent spellings and re-run — curator row must survive.
    _seed_event(conn, 2, date_str="2000-07-29")
    _seed_event(conn, 3, date_str="2000-07-30")
    _seed_song(conn, 2, 1, "visions of johanna")
    _seed_song(conn, 3, 1, "visions of johanna")
    conn.commit()
    song_index.run(db_path=db_path)

    row = conn.execute(
        "SELECT canonical, source FROM song_canonical WHERE alias_norm=?", (norm,)
    ).fetchone()
    assert row["canonical"] == "Visions Of Johanna (curator spelling)"
    assert row["source"] == "curator"

    # The performance rows pick up the curator spelling too.
    perf_rows = conn.execute(
        "SELECT DISTINCT song_canonical FROM song_performances WHERE song_norm=?", (norm,)
    ).fetchall()
    assert [r["song_canonical"] for r in perf_rows] == ["Visions Of Johanna (curator spelling)"]

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── song_performances recompute ────────────────────────────────────────────────

def test_recompute_idempotent_rerun():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1)
    _seed_song(conn, 1, 1, "Visions of Johanna")
    _seed_song(conn, 1, 2, "Like a Rolling Stone", is_encore=1)
    conn.commit()

    stats1 = song_index.run(db_path=db_path)
    rows1 = conn.execute(
        "SELECT event_id, position, song_norm, song_canonical, concert_date_iso,"
        " is_encore, take_status, event_type FROM song_performances ORDER BY position"
    ).fetchall()

    stats2 = song_index.run(db_path=db_path)
    rows2 = conn.execute(
        "SELECT event_id, position, song_norm, song_canonical, concert_date_iso,"
        " is_encore, take_status, event_type FROM song_performances ORDER BY position"
    ).fetchall()

    assert stats1 == stats2
    assert [dict(r) for r in rows1] == [dict(r) for r in rows2]
    assert stats1["performances_written"] == 2

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_recompute_skips_blank_titles_and_sets_null_date_for_unparsed():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1, date_str="")  # unparsed date
    _seed_song(conn, 1, 1, "Visions of Johanna")
    _seed_song(conn, 1, 2, "")  # blank title -> skipped
    conn.commit()

    stats = song_index.run(db_path=db_path)
    assert stats["performances_written"] == 1
    assert stats["skipped_blank_title"] == 1

    row = conn.execute("SELECT concert_date_iso FROM song_performances").fetchone()
    assert row["concert_date_iso"] is None

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dry_run_does_not_write():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1)
    _seed_song(conn, 1, 1, "Visions of Johanna")
    conn.commit()

    stats = song_index.run(dry_run=True, db_path=db_path)
    assert stats["performances_written"] == 1

    count = conn.execute("SELECT COUNT(*) AS c FROM song_performances").fetchone()["c"]
    canonical_count = conn.execute("SELECT COUNT(*) AS c FROM song_canonical").fetchone()["c"]
    assert count == 0
    assert canonical_count == 0

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/songs ─────────────────────────────────────────────────────────────

def test_songs_list_orders_by_performance_count_and_filters_by_q():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1, date_str="2000-07-28")
    _seed_event(conn, 2, date_str="2000-07-29")
    _seed_song(conn, 1, 1, "Visions of Johanna")
    _seed_song(conn, 2, 1, "Visions of Johanna")
    _seed_song(conn, 2, 2, "Like a Rolling Stone")
    conn.commit()
    song_index.run(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/songs")
        assert resp.status_code == 200
        songs = resp.get_json()["songs"]
        assert songs[0]["canonical"] == "Visions of Johanna"
        assert songs[0]["n_performances"] == 2
        assert songs[0]["n_concerts"] == 2

        resp = client.get("/api/songs?q=rolling")
        songs = resp.get_json()["songs"]
        assert len(songs) == 1
        assert songs[0]["canonical"] == "Like a Rolling Stone"

        resp = client.get("/api/songs?q=nonexistentsong")
        assert resp.get_json()["songs"] == []

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_songs_list_n_dates_with_recordings_via_show_picks():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1, date_str="2000-07-28")
    _seed_event(conn, 2, date_str="2000-07-29")
    _seed_song(conn, 1, 1, "Visions of Johanna")
    _seed_song(conn, 2, 1, "Visions of Johanna")
    _seed_entry(conn, 100, "7/28/00", rating="A")
    conn.commit()
    song_index.run(db_path=db_path)

    import concert_ranker.picks as picks
    picks.recompute(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/songs")
        songs = resp.get_json()["songs"]
        assert songs[0]["n_performances"] == 2
        assert songs[0]["n_dates_with_recordings"] == 1

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── GET /api/songs/performances ────────────────────────────────────────────────

def test_song_performances_route_returns_recordings_and_404_when_unknown():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1, date_str="2000-07-28", venue="Massey Hall", city="Toronto")
    _seed_song(conn, 1, 1, "Visions of Johanna", is_encore=0, take_status="complete")
    _seed_entry(conn, 100, "7/28/00", rating="A")
    _seed_entry(conn, 101, "7/28/00", rating="C")
    conn.commit()
    song_index.run(db_path=db_path)

    from concert_ranker.lb import repo as cr_repo
    cr_repo.ensure_schema(conn)
    conn.execute(
        "INSERT OR REPLACE INTO quality_recording_scores"
        " (lb_number, scan_id, abs_score, abs_grade) VALUES (100, 1, 88.0, 'A-')"
    )
    conn.commit()

    import concert_ranker.picks as picks
    picks.recompute(db_path=db_path)
    db.set_curator(False, db_path)

    norm = song_index.normalize_song_title("Visions of Johanna")
    with _AppClient(db_path) as client:
        resp = client.get(f"/api/songs/performances?song={norm}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["canonical"] == "Visions of Johanna"
        assert len(body["performances"]) == 1
        perf = body["performances"][0]
        assert perf["date_iso"] == "2000-07-28"
        assert perf["venue"] == "Massey Hall"
        assert perf["city"] == "Toronto"
        assert perf["take_status"] == "complete"
        recs = {r["lb_number"]: r for r in perf["recordings"]}
        assert recs[100]["pick_rank"] == 1
        assert recs[100]["abs_grade"] == "A-"
        assert recs[101]["abs_grade"] is None

        resp_missing = client.get("/api/songs/performances?song=not-a-real-song")
        assert resp_missing.status_code == 404

        resp_no_param = client.get("/api/songs/performances")
        assert resp_no_param.status_code == 400

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── POST /api/songs/alias ──────────────────────────────────────────────────────

def test_songs_alias_is_curator_gated_and_recomputes():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1)
    _seed_song(conn, 1, 1, "visions of johanna")
    conn.commit()
    song_index.run(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post(
            "/api/songs/alias",
            json={"alias": "Visions of Johanna", "canonical": "Visions Of Johanna"},
        )
        assert resp.status_code == 403

    db.set_curator(True, db_path)
    with _AppClient(db_path) as client:
        resp = client.post(
            "/api/songs/alias",
            json={"alias": "Visions of Johanna", "canonical": "Visions Of Johanna"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["stats"]["performances_written"] == 1

        resp = client.get("/api/songs")
        songs = resp.get_json()["songs"]
        assert songs[0]["canonical"] == "Visions Of Johanna"

        resp = client.post("/api/songs/alias", json={"alias": "", "canonical": "x"})
        assert resp.status_code == 400

    shutil.rmtree(tmp_dir, ignore_errors=True)
