"""Tests for the aligned A/B listening clip service (LISTENING §2, TODO-231):
backend/ab_clips.py pure math + the POST /api/ab_clip / GET /api/ab_clip
routes and the GET /api/tapematch/pairs ``ab_eligible`` enrichment.

No real ffmpeg/ffprobe is ever invoked: ffprobe durations are monkeypatched
and ffmpeg extraction is replaced with a stub that writes a placeholder file.
The offset/track-locate math is exercised via the pure functions directly.
Follows tests/test_tapematch_routes.py's _AppClient + synthetic-observations.db
fixture pattern.
"""
import os
import shutil
import sqlite3
import tempfile

import backend.ab_clips as ab_clips
import backend.db as db
import backend.paths as _paths
import backend.tapematch_sync as tapematch_sync


# ── _AppClient (mirrors tests/test_tapematch_routes.py) ──────────────────────
def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_clips_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


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


def _make_obs_db(tmp_dir, rows, run_id="20260101_000000", concert_date="1991-01-01"):
    """Create a synthetic observations.db with a ``sources`` table.

    Args:
        tmp_dir: Directory to create observations.db in.
        rows: Iterable of ``(lb_number, folder_name, trim_head_sec,
            perf_dur_sec, speed_kind)`` tuples.
        run_id: Run id seeded on every row.
        concert_date: Concert date seeded on every row.

    Returns:
        Path to the created observations.db.
    """
    obs_path = os.path.join(tmp_dir, "observations.db")
    conn = sqlite3.connect(obs_path)
    conn.execute(
        "CREATE TABLE sources (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, "
        "concert_date TEXT, lb_number INTEGER, folder_name TEXT, "
        "trim_head_sec REAL, perf_dur_sec REAL, total_dur_sec REAL, speed_kind TEXT)"
    )
    # The real observations.db also has a ``pairs`` table (used by the pairs
    # route's human-feedback enrichment); create an empty one so that query
    # doesn't abort the shared best-effort enrichment block.
    conn.execute(
        "CREATE TABLE pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, "
        "concert_date TEXT, lb_a INTEGER, lb_b INTEGER, "
        "human_judgment TEXT, human_notes TEXT)"
    )
    for lb, folder, trim, perf, kind in rows:
        conn.execute(
            "INSERT INTO sources (run_id, concert_date, lb_number, folder_name, "
            "trim_head_sec, perf_dur_sec, total_dur_sec, speed_kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, concert_date, lb, folder, trim, perf, (perf or 0) + (trim or 0), kind),
        )
    conn.commit()
    conn.close()
    return obs_path


def _seed_collection_folder(tmp_dir, lb_number, n_tracks=3):
    """Create a fake LB folder with n empty .flac files, register in my_collection."""
    folder = os.path.join(tmp_dir, f"LB-{lb_number:05d}")
    os.makedirs(folder, exist_ok=True)
    for i in range(n_tracks):
        open(os.path.join(folder, f"{i + 1:02d}-track.flac"), "wb").close()
    return folder


# ── Pure math ────────────────────────────────────────────────────────────────
def test_clamp_dur_defaults_and_bounds():
    assert ab_clips.clamp_dur(None) == ab_clips.DEFAULT_DUR_SEC
    assert ab_clips.clamp_dur(20) == 20
    assert ab_clips.clamp_dur(2) == ab_clips.MIN_DUR_SEC
    assert ab_clips.clamp_dur(999) == ab_clips.MAX_DUR_SEC
    assert ab_clips.clamp_dur("garbage") == ab_clips.DEFAULT_DUR_SEC


def test_source_offset_adds_trim_head():
    # Performance time t=10 maps to source-local t + trim_head.
    assert ab_clips.source_offset(10.0, 35.5) == 45.5
    assert ab_clips.source_offset(10.0, None) == 10.0
    # Two differently-trimmed sources land at different local offsets for same t.
    assert ab_clips.source_offset(100.0, 8.0) != ab_clips.source_offset(100.0, 116.5)


def test_plan_extraction_within_single_file():
    durations = [300.0, 300.0, 300.0]
    segs = ab_clips.plan_extraction(durations, offset_sec=50.0, dur_sec=20.0)
    assert segs == [(0, 50.0, 20.0)]


def test_plan_extraction_locates_later_file():
    durations = [300.0, 300.0, 300.0]
    # offset 350 -> 50s into file index 1.
    segs = ab_clips.plan_extraction(durations, offset_sec=350.0, dur_sec=20.0)
    assert segs == [(1, 50.0, 20.0)]


def test_plan_extraction_spans_track_boundary():
    durations = [300.0, 300.0, 300.0]
    # Window [290, 310) straddles the file0/file1 boundary.
    segs = ab_clips.plan_extraction(durations, offset_sec=290.0, dur_sec=20.0)
    assert len(segs) == 2
    assert segs[0] == (0, 290.0, 10.0)
    assert segs[1][0] == 1 and segs[1][1] == 0.0
    assert abs(segs[1][2] - 10.0) < 1e-6
    assert abs(sum(s[2] for s in segs) - 20.0) < 1e-6


def test_plan_extraction_offset_beyond_end_is_empty():
    assert ab_clips.plan_extraction([100.0, 100.0], offset_sec=500.0, dur_sec=10.0) == []


def test_plan_extraction_truncates_past_end():
    # Window runs past the sequence end -> best-effort short clip.
    segs = ab_clips.plan_extraction([100.0], offset_sec=95.0, dur_sec=20.0)
    assert segs == [(0, 95.0, 5.0)]


def test_cache_filename_is_deterministic_and_scoped():
    a = ab_clips.cache_filename(6162, 100.0, 20)
    b = ab_clips.cache_filename(6162, 100.0, 20)
    assert a == b and a.startswith("ab_6162_") and a.endswith(".wav")
    # Different lb / offset / dur -> different names. Keying on the post-trim
    # offset (not raw performance time) means a rerun that changes a source's
    # trim yields a new cache file instead of serving a stale clip.
    assert a != ab_clips.cache_filename(5953, 100.0, 20)
    assert a != ab_clips.cache_filename(6162, 101.0, 20)
    assert a != ab_clips.cache_filename(6162, 100.0, 30)


def test_pair_source_info_uses_latest_common_run():
    """Trims must come from ONE run: latest run containing BOTH sources.

    Seeds run R1 with both LBs (eligible, known trims) and a newer run R2
    containing only LB 6162 with a different trim and an ineligible
    speed_kind. Per-source-latest selection would mix R2's row in; the
    common-run rule must return both rows from R1.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_ab_")
    try:
        obs_path = _make_obs_db(
            tmp_dir,
            [(6162, "A", 10.0, 3600.0, "reference"), (5953, "B", 4.0, 3600.0, "aligned")],
            run_id="20260101_000000",
        )
        conn = sqlite3.connect(obs_path)
        conn.execute(
            "INSERT INTO sources (run_id, concert_date, lb_number, folder_name, "
            "trim_head_sec, perf_dur_sec, total_dur_sec, speed_kind) "
            "VALUES ('20260202_000000', '1991-01-01', 6162, 'A', 99.0, 3600.0, 3699.0, "
            "'staircase/splice')",
        )
        conn.commit()
        conn.close()
        ro = sqlite3.connect(f"file:{obs_path}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        try:
            pair = ab_clips.get_pair_source_info(ro, "1991-01-01", 6162, 5953)
            assert pair is not None
            info_a, info_b = pair
            assert info_a["run_id"] == info_b["run_id"] == "20260101_000000"
            assert info_a["trim_head_sec"] == 10.0
            assert info_a["speed_kind"] == "reference"
        finally:
            ro.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_is_eligible_speed():
    assert ab_clips.is_eligible_speed("reference")
    assert ab_clips.is_eligible_speed("aligned")
    assert not ab_clips.is_eligible_speed("staircase/splice")
    assert not ab_clips.is_eligible_speed("speed-unknown")
    assert not ab_clips.is_eligible_speed(None)


# ── eligible_lb_set ──────────────────────────────────────────────────────────
def test_eligible_lb_set_filters_by_speed_kind():
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_eligset_")
    try:
        obs_path = _make_obs_db(tmp_dir, [
            (10, "f10", 5.0, 100.0, "reference"),
            (20, "f20", 5.0, 100.0, "aligned"),
            (30, "f30", 5.0, 100.0, "staircase/splice"),
        ])
        conn = ab_clips._open_obs_ro(obs_path)
        try:
            elig = ab_clips.eligible_lb_set(conn, "1991-01-01", "20260101_000000")
        finally:
            conn.close()
        assert elig == {10, 20}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── prune_cache ──────────────────────────────────────────────────────────────
def test_prune_cache_keeps_newest(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_prune_")
    try:
        monkeypatch.setattr(ab_clips, "AB_CLIPS_DIR", ab_clips.Path(tmp_dir))
        # 45 clips with increasing mtimes.
        for i in range(45):
            p = os.path.join(tmp_dir, f"ab_{i}.wav")
            open(p, "wb").close()
            os.utime(p, (1000 + i, 1000 + i))
        ab_clips.prune_cache(limit=40)
        remaining = sorted(os.listdir(tmp_dir))
        assert len(remaining) == 40
        # The 5 oldest (0..4) should be gone.
        assert "ab_0.wav" not in remaining and "ab_44.wav" in remaining
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── generate_ab_clips (with stubbed ffprobe/ffmpeg) ──────────────────────────
def _patch_audio(monkeypatch, per_file_dur=300.0):
    """Stub ffprobe (fixed durations) and ffmpeg extraction (touch output)."""
    ab_clips.clear_duration_cache()
    monkeypatch.setattr(ab_clips, "_ffprobe_duration", lambda p: per_file_dur)

    def _fake_extract(files, segments, out_path):
        with open(out_path, "wb") as fh:
            fh.write(b"RIFFfake")

    monkeypatch.setattr(ab_clips, "_extract_clip", _fake_extract)


def test_generate_ab_clips_happy_path(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_gen_")
    try:
        clips_dir = os.path.join(tmp_dir, "ab_clips")
        monkeypatch.setattr(ab_clips, "AB_CLIPS_DIR", ab_clips.Path(clips_dir))
        _patch_audio(monkeypatch)

        folder_a = _seed_collection_folder(tmp_dir, 6162)
        folder_b = _seed_collection_folder(tmp_dir, 5953)
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 35.5, 8434.0, "aligned"),
        ])

        main = sqlite3.connect(":memory:")
        main.row_factory = sqlite3.Row
        main.execute(
            "CREATE TABLE my_collection (lb_number INTEGER, disk_path TEXT)"
        )
        main.execute(
            "INSERT INTO my_collection VALUES (6162, ?)", (folder_a,)
        )
        main.execute(
            "INSERT INTO my_collection VALUES (5953, ?)", (folder_b,)
        )
        main.commit()

        result = ab_clips.generate_ab_clips(
            main, obs_path, "1991-01-01", 6162, 5953, t_sec=100.0, dur_sec=20,
        )
        assert result["clip_a"].startswith("/api/ab_clip/ab_6162_")
        assert result["clip_b"].startswith("/api/ab_clip/ab_5953_")
        # Both files were written into the cache.
        assert len(os.listdir(clips_dir)) == 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_generate_ab_clips_not_eligible_raises_409(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_409_")
    try:
        _patch_audio(monkeypatch)
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 35.5, 8434.0, "staircase/splice"),
        ])
        main = sqlite3.connect(":memory:")
        main.execute("CREATE TABLE my_collection (lb_number INTEGER, disk_path TEXT)")
        try:
            ab_clips.generate_ab_clips(
                main, obs_path, "1991-01-01", 6162, 5953, t_sec=10.0, dur_sec=20,
            )
            assert False, "expected NotEligibleError"
        except ab_clips.NotEligibleError as exc:
            assert exc.status == 409
            assert exc.payload["error"] == "not_eligible"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_generate_ab_clips_missing_folder_raises_404(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_404_")
    try:
        _patch_audio(monkeypatch)
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 35.5, 8434.0, "aligned"),
        ])
        main = sqlite3.connect(":memory:")
        main.row_factory = sqlite3.Row
        main.execute("CREATE TABLE my_collection (lb_number INTEGER, disk_path TEXT)")
        # Point at a path that does not exist (unmounted drive scenario).
        main.execute(
            "INSERT INTO my_collection VALUES (6162, ?)",
            (os.path.join(tmp_dir, "not_mounted"),),
        )
        main.commit()
        try:
            ab_clips.generate_ab_clips(
                main, obs_path, "1991-01-01", 6162, 5953, t_sec=10.0, dur_sec=20,
            )
            assert False, "expected FolderMissingError"
        except ab_clips.FolderMissingError as exc:
            assert exc.status == 404
            assert exc.payload["error"] == "folder_missing"
            assert exc.payload["lb_number"] == 6162
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_generate_ab_clips_unknown_pair_raises_404(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_np_")
    try:
        _patch_audio(monkeypatch)
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
        ])
        main = sqlite3.connect(":memory:")
        main.execute("CREATE TABLE my_collection (lb_number INTEGER, disk_path TEXT)")
        try:
            ab_clips.generate_ab_clips(
                main, obs_path, "1991-01-01", 6162, 9999, t_sec=10.0, dur_sec=20,
            )
            assert False, "expected PairNotFoundError"
        except ab_clips.PairNotFoundError as exc:
            assert exc.status == 404
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_generate_ab_clips_t_beyond_perf_dur_raises_400(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_toob_")
    try:
        _patch_audio(monkeypatch)
        folder_a = _seed_collection_folder(tmp_dir, 6162)
        folder_b = _seed_collection_folder(tmp_dir, 5953)
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 100.0, "reference"),
            (5953, "f_b", 8.0, 100.0, "aligned"),
        ])
        main = sqlite3.connect(":memory:")
        main.row_factory = sqlite3.Row
        main.execute("CREATE TABLE my_collection (lb_number INTEGER, disk_path TEXT)")
        main.execute("INSERT INTO my_collection VALUES (6162, ?)", (folder_a,))
        main.execute("INSERT INTO my_collection VALUES (5953, ?)", (folder_b,))
        main.commit()
        try:
            ab_clips.generate_ab_clips(
                main, obs_path, "1991-01-01", 6162, 5953, t_sec=999.0, dur_sec=20,
            )
            assert False, "expected BadRequestError"
        except ab_clips.BadRequestError as exc:
            assert exc.status == 400
            assert exc.payload["error"] == "t_out_of_range"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_build_clip_uses_trim_head_offset(monkeypatch):
    """Offset passed to extraction = t + trim_head, and lands in the right file."""
    tmp_dir = tempfile.mkdtemp(prefix="lb_ab_off_")
    try:
        clips_dir = os.path.join(tmp_dir, "ab_clips")
        monkeypatch.setattr(ab_clips, "AB_CLIPS_DIR", ab_clips.Path(clips_dir))
        ab_clips.clear_duration_cache()
        monkeypatch.setattr(ab_clips, "_ffprobe_duration", lambda p: 300.0)

        captured = {}

        def _fake_extract(files, segments, out_path):
            captured["segments"] = segments
            open(out_path, "wb").close()

        monkeypatch.setattr(ab_clips, "_extract_clip", _fake_extract)

        folder = _seed_collection_folder(tmp_dir, 6162, n_tracks=3)
        # t=350, trim_head=8 -> offset 358 -> 58s into file index 1.
        offset = ab_clips.source_offset(350.0, 8.0)
        ab_clips.build_clip(folder, offset, 20, "ab_test.wav")
        segs = captured["segments"]
        assert segs[0][0] == 1
        assert abs(segs[0][1] - 58.0) < 1e-6
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Route: POST /api/ab_clip ─────────────────────────────────────────────────
def test_post_ab_clip_route_missing_fields_is_400():
    db_path, tmp_dir = _make_db()
    try:
        with _AppClient(db_path) as client:
            resp = client.post("/api/ab_clip", json={"date": "1991-01-01"})
            assert resp.status_code == 400
            assert resp.get_json()["error"] == "missing_fields"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_post_ab_clip_route_not_eligible_is_409(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 8.0, 8434.0, "speed-unknown"),
        ])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        _patch_audio(monkeypatch)

        with _AppClient(db_path) as client:
            resp = client.post("/api/ab_clip", json={
                "date": "1991-01-01", "lb_a": 6162, "lb_b": 5953,
                "t_sec": 10.0, "dur_sec": 20,
            })
            assert resp.status_code == 409
            assert resp.get_json()["error"] == "not_eligible"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_post_ab_clip_route_folder_missing_is_404(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 8.0, 8434.0, "aligned"),
        ])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        _patch_audio(monkeypatch)

        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, status) VALUES (6162, '1/1/91', 'ok')"
        )
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, status) VALUES (5953, '1/1/91', 'ok')"
        )
        conn.execute(
            "INSERT INTO my_collection (lb_number, folder_name, disk_path) "
            "VALUES (6162, 'f_a', ?)", (os.path.join(tmp_dir, "gone"),)
        )
        conn.execute(
            "INSERT INTO my_collection (lb_number, folder_name, disk_path) "
            "VALUES (5953, 'f_b', ?)", (os.path.join(tmp_dir, "gone2"),)
        )
        conn.commit()

        with _AppClient(db_path) as client:
            resp = client.post("/api/ab_clip", json={
                "date": "1991-01-01", "lb_a": 6162, "lb_b": 5953,
                "t_sec": 10.0, "dur_sec": 20,
            })
            assert resp.status_code == 404
            assert resp.get_json()["error"] == "folder_missing"
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_post_ab_clip_route_happy_path_and_serve(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        clips_dir = os.path.join(tmp_dir, "ab_clips")
        monkeypatch.setattr(ab_clips, "AB_CLIPS_DIR", ab_clips.Path(clips_dir))
        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 35.5, 8434.0, "aligned"),
        ])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)
        _patch_audio(monkeypatch)

        folder_a = _seed_collection_folder(tmp_dir, 6162)
        folder_b = _seed_collection_folder(tmp_dir, 5953)
        conn = db.get_connection(db_path)
        for lb, folder in ((6162, folder_a), (5953, folder_b)):
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, status) VALUES (?, '1/1/91', 'ok')",
                (lb,),
            )
            conn.execute(
                "INSERT INTO my_collection (lb_number, folder_name, disk_path) "
                "VALUES (?, 'f', ?)", (lb, folder),
            )
        conn.commit()

        with _AppClient(db_path) as client:
            resp = client.post("/api/ab_clip", json={
                "date": "1991-01-01", "lb_a": 6162, "lb_b": 5953,
                "t_sec": 100.0,
            })
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["dur_sec"] == ab_clips.DEFAULT_DUR_SEC
            name = body["clip_a"].split("/")[-1]

            # Serve it back.
            serve = client.get(f"/api/ab_clip/{name}")
            assert serve.status_code == 200
            assert serve.mimetype == "audio/wav"

            # Unknown clip -> 404.
            missing = client.get("/api/ab_clip/does_not_exist.wav")
            assert missing.status_code == 404
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Route: GET /api/tapematch/pairs ab_eligible enrichment ───────────────────
def test_pairs_route_enriches_ab_eligible(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        # Two pairs on the same date/run.
        for lb_a, lb_b in ((6162, 5953), (6162, 3030)):
            conn.execute(
                "INSERT INTO tapematch_pairs "
                "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
                " similarity_pct, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("1991-01-01", lb_a, lb_b, 0.9, 0.9, 0.9, 1, 90, "20260101_000000"),
            )
        conn.commit()

        obs_path = _make_obs_db(tmp_dir, [
            (6162, "f_a", 8.0, 7230.0, "reference"),
            (5953, "f_b", 8.0, 8434.0, "aligned"),
            (3030, "f_c", 8.0, 8000.0, "staircase/splice"),
        ])
        monkeypatch.setattr(tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH", obs_path)

        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1991-01-01")
            assert resp.status_code == 200
            pairs = {(p["lb_a"], p["lb_b"]): p for p in resp.get_json()["pairs"]}
            # both eligible speed_kinds -> True
            assert pairs[(6162, 5953)]["ab_eligible"] is True
            # one staircase -> False
            assert pairs[(6162, 3030)]["ab_eligible"] is False
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pairs_route_ab_eligible_null_when_no_observations(monkeypatch):
    db_path, tmp_dir = _make_db()
    try:
        conn = db.get_connection(db_path)
        conn.execute(
            "INSERT INTO tapematch_pairs "
            "(concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family, "
            " similarity_pct, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("1991-01-01", 6162, 5953, 0.9, 0.9, 0.9, 1, 90, "20260101_000000"),
        )
        conn.commit()
        monkeypatch.setattr(
            tapematch_sync, "DEFAULT_OBSERVATIONS_DB_PATH",
            os.path.join(tmp_dir, "nope.db"),
        )
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/pairs?date=1991-01-01")
            assert resp.status_code == 200
            assert resp.get_json()["pairs"][0]["ab_eligible"] is None
    finally:
        db.close_connection(db_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
