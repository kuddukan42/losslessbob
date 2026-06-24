"""Tests for the concert_ranker LB-integration layer.

These exercise the DB-integration, source-class, commentary, and
scoring-orchestration paths WITHOUT decoding audio — synthetic raw metrics are
injected directly, mirroring what a real scan would persist. The scoring brain
itself is covered by concert_ranker/test_pipeline.py.
"""

import pytest

from concert_ranker.families import rank_group, rank_scan
from concert_ranker.lb import commentary, repo, source_type


def _seed_entries(conn):
    conn.executescript("""
        CREATE TABLE entries (
            lb_number INTEGER PRIMARY KEY, description TEXT,
            source_chain TEXT, rating TEXT, source_type TEXT);
        CREATE TABLE my_collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lb_number INTEGER UNIQUE,
            folder_name TEXT, disk_path TEXT, notes TEXT);
    """)
    rows = [
        # (lb, description, source_chain, rating, curator source_type)
        (1, "great soundboard, present vocals", "SBD > DAT", "A", None),
        (2, "distant muddy audience, buried in crowd", "AUD", "C", None),
        (3, "FM broadcast, bright and airy", "pre-FM", "B", None),
    ]
    conn.executemany("INSERT INTO entries VALUES (?,?,?,?,?)", rows)
    conn.commit()


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "t.db"
    c = repo.connect(str(db))
    _seed_entries(c)
    repo.ensure_schema(c)
    yield c
    c.close()


# ── repo ─────────────────────────────────────────────────────────────────────
def test_scan_metrics_roundtrip(conn):
    sid = repo.create_scan(conn, config={"a": 1}, notes="t")
    assert repo.get_scan(conn, sid)["notes"] == "t"
    mj = repo.build_metric_json({"crowd_snr_db": 10.0, "mud_ratio_db": 3.0},
                                completeness=1.0, duration_sec=600.0)
    repo.persist_recording(conn, sid, 1, "SBD", mj, duration_sec=600.0)
    assert repo.done_lbs(conn, sid) == {1}
    loaded = repo.load_metrics(conn, sid)
    assert loaded[1]["source_class"] == "SBD"
    assert loaded[1]["metrics"]["crowd_snr_db"] == 10.0


def test_build_metric_json_sanitizes_numpy_and_nan():
    np = pytest.importorskip("numpy")
    mj = repo.build_metric_json({"a": np.float32(1.5), "b": float("nan")})
    assert mj["metrics"]["a"] == 1.5 and isinstance(mj["metrics"]["a"], float)
    assert mj["metrics"]["b"] is None  # NaN coerced to null


def test_persist_is_idempotent(conn):
    sid = repo.create_scan(conn)
    for val in (1.0, 2.0):
        repo.persist_recording(conn, sid, 1, "SBD",
                               repo.build_metric_json({"crowd_snr_db": val}))
    rows = conn.execute(
        "SELECT COUNT(*) FROM quality_recording_metrics WHERE scan_id=?", (sid,)
    ).fetchone()[0]
    assert rows == 1  # INSERT OR REPLACE, not a duplicate
    assert repo.load_metrics(conn, sid)[1]["metrics"]["crowd_snr_db"] == 2.0


# ── source_type ──────────────────────────────────────────────────────────────
def test_source_class_derivation(conn):
    classes = source_type.classify_entries(conn)
    assert classes == {1: "SBD", 2: "AUD", 3: "FM"}


def test_matrix_is_unknown():
    # A pure matrix (no SBD/AUD keyword) maps to UNKNOWN — it belongs on neither
    # pure curve, so it must not contaminate SBD or AUD calibration.
    assert source_type.derive_source_class("matrix recording", None) == "UNKNOWN"


def test_curator_source_type_wins_over_freetext():
    # The curator column is authoritative when set, even if free-text disagrees.
    assert source_type.derive_source_class(
        "sounds like a soundboard", "SBD", curator_source_type="Audience") == "AUD"
    assert source_type.derive_source_class(
        None, None, curator_source_type="Soundboard") == "SBD"
    assert source_type.derive_source_class(
        None, None, curator_source_type="Mixed") == "UNKNOWN"


# ── commentary ───────────────────────────────────────────────────────────────
def test_commentary_mining(conn):
    mined = commentary.mine_entries(conn)
    assert "buried in crowd" in mined[2]["labels"]
    assert "present vocals" in mined[1]["labels"]
    assert mined[3]["labels"] == ["bright / airy"]


def test_word_boundary_matching():
    # "bassist" must not trigger the "no bass" / bass keywords spuriously
    assert "thin / bass-light" not in commentary.mined_labels("the bassist played well")


# ── families / ranking ───────────────────────────────────────────────────────
def _metrics(crowd, mud, dur):
    return {"metrics": {"crowd_snr_db": crowd, "mud_ratio_db": mud},
            "duration_sec": dur}


def test_rank_group_orders_and_completeness():
    group = {
        10: _metrics(20.0, 1.0, 600.0),   # clean, full length
        11: _metrics(5.0, 8.0, 300.0),    # crowd-heavy, muddy, half length
    }
    rows = rank_group(group, family_id=1)
    by_lb = {r["lb_number"]: r for r in rows}
    assert by_lb[10]["rank_in_family"] == 1
    assert by_lb[11]["rank_in_family"] == 2
    # 11 is half the length of its sibling → incomplete flag in verdict
    assert "incomplete" in by_lb[11]["verdict_text"]


def test_standalone_has_no_relative_rank():
    rows = rank_group({10: _metrics(20.0, 1.0, 600.0)}, family_id=None)
    assert len(rows) == 1
    # single recording → absolute bands only, no "#1 of N" phrasing
    assert "of " not in rows[0]["verdict_text"]


def test_rank_scan_groups_families_and_standalone():
    metrics = {
        10: _metrics(20.0, 1.0, 600.0),
        11: _metrics(5.0, 8.0, 600.0),
        12: _metrics(15.0, 2.0, 600.0),
    }
    family_map = {10: "fam#A", 11: "fam#A"}  # 12 ungrouped
    rows = rank_scan(metrics, family_map)
    by_lb = {r["lb_number"]: r for r in rows}
    assert by_lb[10]["family_id"] == by_lb[11]["family_id"] is not None
    assert by_lb[12]["family_id"] is None  # standalone


def test_decade_bands_are_era_relative():
    """The same hiss value bands differently against each era's norms."""
    from concert_ranker import scoring as S
    from concert_ranker.config import DECADE_BANDS, decade_of

    raw = {"hiss_floor_db": -0.3}
    # -0.3 is way above the 2000s 'hissy' cut (digital era is clean) but normal
    # for the 1960s tape era.
    assert "hissy" in S.all_bands(raw, decade=2000)
    assert "hissy" not in S.all_bands(raw, decade=1960)
    # unknown / unrepresented decade falls back to the global bands
    assert S.all_bands(raw, decade=1234) == S.all_bands(raw)
    assert set(DECADE_BANDS) >= {1960, 1970, 1980, 1990, 2000, 2010}
    assert decade_of(1987) == 1980 and decade_of(None) is None


def test_hybrid_crowd_global_hiss_per_class():
    """Hybrid bands: crowd stays absolute across classes; hiss is class-relative."""
    from concert_ranker.config import SEVERITY_BANDS, resolve_band_set
    sbd = resolve_band_set(None, "SBD")
    aud = resolve_band_set(1990, "AUD")
    # crowd_snr held on the global band for everyone (a soundboard reads "clean",
    # not "crowd-heavy" — crowd level is meaningful absolutely)
    assert sbd["SEVERITY"]["crowd_snr_db"] == SEVERITY_BANDS["crowd_snr_db"]
    assert aud["SEVERITY"]["crowd_snr_db"] == SEVERITY_BANDS["crowd_snr_db"]
    # but hiss IS class-specific (soundboard floor is lower)
    assert sbd["SEVERITY"]["hiss_floor_db"] != SEVERITY_BANDS["hiss_floor_db"]
    # FM piggybacks on the SBD set
    assert resolve_band_set(None, "FM") is sbd


def test_absolute_quality_grade():
    """grade() returns a 0-100 score + valid letter, and tracks metric quality."""
    from concert_ranker import quality_score
    from concert_ranker.calibrate import RATING_RANK

    good = {"hiss_floor_db": -10, "hf_ceiling_hz": 15000, "spectral_centroid_hz": 2000,
            "crest_factor_db": 20, "crowd_snr_db": 12, "air_ratio_db": -15,
            "mud_ratio_db": 10, "presence_ratio_db": -2}
    bad = {"hiss_floor_db": 0, "hf_ceiling_hz": 6000, "spectral_centroid_hz": 1100,
           "crest_factor_db": 12, "crowd_snr_db": 2, "air_ratio_db": -40,
           "mud_ratio_db": 22, "presence_ratio_db": -10}
    sg, sl, _ = quality_score.grade(good)
    bg, bl, _ = quality_score.grade(bad)
    assert 0 <= sg <= 100 and 0 <= bg <= 100
    assert sg > bg  # clean metrics grade higher than degraded ones
    assert sl in RATING_RANK and bl in RATING_RANK
    # missing metrics fall back to the model median (no crash)
    assert 0 <= quality_score.grade({})[0] <= 100


def test_rerank_from_stored_metrics_no_audio(conn):
    """The scan-once guarantee: ranking works purely from stored metric_json."""
    sid = repo.create_scan(conn)
    repo.persist_recording(conn, sid, 1, "SBD",
                           repo.build_metric_json({"crowd_snr_db": 20.0},
                                                  duration_sec=600.0),
                           duration_sec=600.0)
    repo.persist_recording(conn, sid, 2, "AUD",
                           repo.build_metric_json({"crowd_snr_db": 2.0},
                                                  duration_sec=600.0),
                           duration_sec=600.0)
    metrics = repo.load_metrics(conn, sid)
    rows = rank_scan(metrics, {1: "x", 2: "x"})
    repo.clear_scores(conn, sid)
    repo.write_scores(conn, sid, rows)
    scores = {s["lb_number"]: s for s in repo.load_scores(conn, sid)}
    # LB2 trips "buried in crowd" (crowd_snr 2.0 < 3.0) → demoted below LB1
    assert scores[1]["rank_in_family"] == 1
