"""Tests for the concert_ranker LB-integration layer.

These exercise the DB-integration, source-class, commentary, and
scoring-orchestration paths WITHOUT decoding audio — synthetic raw metrics are
injected directly, mirroring what a real scan would persist. The scoring brain
itself is covered by concert_ranker/test_pipeline.py.
"""

import numpy as np
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


def test_absolute_quality_grade_sbd_model():
    """SBD/FM route to QUALITY_MODEL_SBD, not the AUD model, and still discriminate."""
    from concert_ranker import quality_score
    from concert_ranker.calibrate import RATING_RANK
    from concert_ranker.config import QUALITY_MODEL_SBD

    good_sbd = {"hiss_floor_db": -14, "hf_ceiling_hz": 16000, "crest_factor_db": 20,
                "air_ratio_db": -22, "harsh_ratio_db": -4, "directness": 0.12}
    bad_sbd = {"hiss_floor_db": -1, "hf_ceiling_hz": 7000, "crest_factor_db": 12,
               "air_ratio_db": -38, "harsh_ratio_db": 8, "directness": 0.2}
    for cls in ("SBD", "FM"):
        sg, sl, _ = quality_score.grade(good_sbd, cls)
        bg, bl, _ = quality_score.grade(bad_sbd, cls)
        assert 0 <= sg <= 100 and 0 <= bg <= 100
        assert sg > bg
        assert sl in RATING_RANK and bl in RATING_RANK
    # AUD (default) and SBD models disagree on at least one weight/metric set,
    # so the same raw metrics can grade differently depending on source_class
    assert quality_score._model_for("SBD") is QUALITY_MODEL_SBD
    assert quality_score._model_for(None) is not QUALITY_MODEL_SBD
    assert quality_score._model_for("AUD") is not QUALITY_MODEL_SBD
    # missing metrics fall back to the SBD model's median (no crash)
    assert 0 <= quality_score.grade({}, "SBD")[0] <= 100


# ── dropout_count feature ─────────────────────────────────────────────────────
_SR = 22050


def _cache_for(x: np.ndarray):
    from concert_ranker.audio.cache import build_track_cache
    return build_track_cache(x.astype(np.float32), _SR, path="<test>")


def _dropout(x: np.ndarray) -> int:
    from concert_ranker.features import extract_distortion
    return extract_distortion(_cache_for(x))["dropout_count"]


def _loud_sine(dur=5.0, freq=440.0, amp=0.5) -> np.ndarray:
    t = np.arange(int(dur * _SR)) / _SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_dropout_clean_signal_is_zero():
    """Clean sine: no dropouts."""
    assert _dropout(_loud_sine()) == 0


def test_dropout_silence_gap_detected():
    """A 100ms near-silence pocket in loud audio counts as one dropout."""
    x = _loud_sine()
    gap_start = int(2.0 * _SR)
    x[gap_start: gap_start + int(0.1 * _SR)] = 0.0
    assert _dropout(x) >= 1


def test_dropout_multiple_gaps_counted():
    """Two distinct gaps are counted separately."""
    x = _loud_sine()
    for t in (1.5, 3.0):
        s = int(t * _SR)
        x[s: s + int(0.05 * _SR)] = 0.0
    assert _dropout(x) >= 2


def test_dropout_long_silence_not_counted():
    """A long silence (>500ms) is a musical pause, not a dropout."""
    x = _loud_sine()
    x[int(2.0 * _SR): int(3.0 * _SR)] = 0.0   # 1-second gap
    assert _dropout(x) == 0


def test_dropout_leading_silence_not_counted():
    """Silence at the start of a recording has no loud left flank — not counted."""
    x = _loud_sine()
    x[: int(0.1 * _SR)] = 0.0                  # 100ms of pre-roll silence
    assert _dropout(x) == 0


def test_dropout_stuck_samples_detected():
    """5+ consecutive identical PCM values in loud audio count as a dropout."""
    x = _loud_sine()
    s = int(2.5 * _SR)
    x[s: s + 10] = 0.123456                     # frozen buffer
    assert _dropout(x) >= 1


def test_dropout_vertical_digipop_detected():
    """A single bad sample (digipop) surrounded by loud audio is detected."""
    x = _loud_sine(amp=0.3)
    s = int(2.5 * _SR)
    x[s] = 0.9   # impossibly large isolated sample; creates symmetric diff pair
    assert _dropout(x) >= 1


def test_dropout_transients_not_counted():
    """Sharp musical transients (attack + decay) do not trigger the detector."""
    rng = np.random.default_rng(7)
    x = _loud_sine()
    # add 10 sharp drum-hit style attacks throughout the signal
    for hit_t in np.linspace(0.5, 4.5, 10):
        s = int(hit_t * _SR)
        env = np.exp(-np.arange(200) / 8.0).astype(np.float32)
        end = min(s + 200, len(x))
        x[s:end] += 0.9 * env[: end - s]
    assert _dropout(x) == 0


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


# ── text features (TODO-188) ──────────────────────────────────────────────────

def test_text_features_empty_description():
    from concert_ranker.text_features import TEXT_FEATURE_KEYS, extract_text_features
    result = extract_text_features(None)
    assert set(result.keys()) == set(TEXT_FEATURE_KEYS)
    assert all(v == 0.0 for v in result.values())


def test_text_features_clipping_variants():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("some clipping in places")["txt_clipping"] == 1.0
    assert extract_text_features("digitally clipped peaks")["txt_clipping"] == 1.0
    assert extract_text_features("clips on the loud sections")["txt_clipping"] == 1.0
    assert extract_text_features("great soundboard, clean")["txt_clipping"] == 0.0


def test_text_features_minidisc():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("lego parapets visible")["txt_minidisc"] == 1.0
    assert extract_text_features("ATRAC encoded mini-disc source")["txt_minidisc"] == 1.0
    assert extract_text_features("minidisc master")["txt_minidisc"] == 1.0
    assert extract_text_features("soundboard to DAT")["txt_minidisc"] == 0.0


def test_text_features_32k_dat():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("32k DAT recording")["txt_32k_dat"] == 1.0
    assert extract_text_features("nothing above 16k")["txt_32k_dat"] == 1.0
    assert extract_text_features("recorded at 32kHz")["txt_32k_dat"] == 1.0
    assert extract_text_features("48k DAT, full bandwidth")["txt_32k_dat"] == 0.0


def test_text_features_eac_match():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("close EAC match to LB1234")["txt_eac_match"] == 1.0
    assert extract_text_features("exact EAC")["txt_eac_match"] == 1.0
    assert extract_text_features("EAC match to previous")["txt_eac_match"] == 1.0
    assert extract_text_features("ripped with EAC, unique source")["txt_eac_match"] == 0.0


def test_text_features_talking_and_singing():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("some talking in row 3")["txt_talking"] == 1.0
    assert extract_text_features("crowd noise during quiet passages")["txt_talking"] == 1.0
    assert extract_text_features("audience singing along the whole set")["txt_singing"] == 1.0
    assert extract_text_features("clean, attentive audience")["txt_talking"] == 0.0
    assert extract_text_features("clean, attentive audience")["txt_singing"] == 0.0


def test_text_features_tv_band():
    from concert_ranker.text_features import extract_text_features
    assert extract_text_features("TV band visible at 15.6k")["txt_tv_band"] == 1.0
    assert extract_text_features("CRT noise band present")["txt_tv_band"] == 1.0
    assert extract_text_features("no artifacts noted")["txt_tv_band"] == 0.0


def test_extract_text_wrapper():
    """extract_text() in features.py delegates to text_features correctly."""
    from concert_ranker.features import extract_text
    result = extract_text("lego parapets, some clipping noted")
    assert result["txt_minidisc"] == 1.0
    assert result["txt_clipping"] == 1.0
    assert result["txt_dropout"] == 0.0


# ── brickwall score (TODO-191) ────────────────────────────────────────────────

def _distortion(x: np.ndarray, sr: int = _SR) -> dict:
    from concert_ranker.features import extract_distortion
    cache = _cache_for(x) if sr == _SR else __import__(
        "concert_ranker.audio.cache", fromlist=["build_track_cache"]
    ).build_track_cache(x.astype(np.float32), sr)
    return extract_distortion(cache)


def test_brickwall_natural_signal_low():
    """Complex natural audio (multi-frequency mix) should score 0."""
    t = np.arange(int(5.0 * _SR)) / _SR
    x = (0.3 * np.sin(2 * np.pi * 440 * t)
         + 0.2 * np.sin(2 * np.pi * 880 * t)
         + 0.15 * np.sin(2 * np.pi * 1760 * t)
         + 0.1 * np.sin(2 * np.pi * 3520 * t)).astype(np.float32)
    score = _distortion(x)["brickwall_score"]
    assert score < 0.5, f"natural multi-harmonic signal scored {score:.3f}"


def test_brickwall_score_range():
    """brickwall_score is always in [0, 1]."""
    rng = np.random.default_rng(42)
    x = rng.standard_normal(int(3.0 * _SR)).astype(np.float32) * 0.3
    score = _distortion(x)["brickwall_score"]
    assert 0.0 <= score <= 1.0


def test_brickwall_smooth_ramps_score_higher():
    """Signal with smooth linear ramps in mid-amplitude but noisy peaks scores
    higher than one with complex content throughout."""
    rng = np.random.default_rng(7)
    n = int(5.0 * _SR)
    # 10 Hz modulation period: 2205 samples ≈ 10 frames of 220 samples each.
    # Each period: first 5 frames are a smooth linear ramp (brickwall region),
    # next 5 frames are band-limited noise at ~0.9 amplitude (the "peaks").
    period = int(_SR / 10)
    half = period // 2
    x_bw = np.zeros(n, dtype=np.float32)
    x_nat = np.zeros(n, dtype=np.float32)
    noise = (0.9 + 0.05 * rng.standard_normal(n)).clip(-1, 1).astype(np.float32)
    for start in range(0, n - period, period):
        end_ramp = min(start + half, n)
        end_loud = min(start + period, n)
        # Brickwall: smooth ramp in mid-amp, noisy in loud region
        x_bw[start:end_ramp] = np.linspace(0, 0.7, end_ramp - start)
        x_bw[end_ramp:end_loud] = noise[end_ramp:end_loud]
        # Natural: noisy throughout (similar RMS, no smoothing)
        x_nat[start:end_ramp] = 0.35 + 0.05 * rng.standard_normal(end_ramp - start)
        x_nat[end_ramp:end_loud] = noise[end_ramp:end_loud]

    score_nat = _distortion(x_nat)["brickwall_score"]
    score_bw = _distortion(x_bw)["brickwall_score"]
    assert score_bw > score_nat, (
        f"brickwall ({score_bw:.3f}) not higher than natural ({score_nat:.3f})"
    )


# ── single-channel transient count (TODO-191) ─────────────────────────────────

def _cache_stereo(L: np.ndarray, R: np.ndarray, sr: int = _SR):
    from concert_ranker.audio.cache import build_track_cache
    return build_track_cache(
        ((L + R) / 2).astype(np.float32), sr,
        left=L.astype(np.float32), right=R.astype(np.float32)
    )


def test_single_ch_transient_clean_stereo_zero():
    """Balanced stereo has no single-channel transients."""
    t = np.arange(int(5.0 * _SR)) / _SR
    L = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    R = (0.3 * np.sin(2 * np.pi * 440 * t + 0.1)).astype(np.float32)
    from concert_ranker.features import extract_distortion
    count = extract_distortion(_cache_stereo(L, R))["single_ch_transient_count"]
    assert count == 0


def test_single_ch_transient_spike_detected():
    """A large spike on one channel only (mic hit) is detected."""
    t = np.arange(int(5.0 * _SR)) / _SR
    L = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    R = L.copy()
    # Insert a large spike on L only at 2.5s
    s = int(2.5 * _SR)
    L[s: s + 50] = 0.9  # large, brief spike on L only
    from concert_ranker.features import extract_distortion
    count = extract_distortion(_cache_stereo(L, R))["single_ch_transient_count"]
    assert count >= 1


def test_single_ch_transient_mono_zero():
    """Mono recordings always return 0 (no second channel to compare)."""
    from concert_ranker.features import extract_distortion
    x = _loud_sine()
    count = extract_distortion(_cache_for(x))["single_ch_transient_count"]
    assert count == 0


# ── HF source signatures (TODO-189, TODO-190) ────────────────────────────────

def _native_probe_from_psd(freqs: np.ndarray, psd_db: np.ndarray,
                            nyquist: float = 22050.0,
                            window_psds_db: np.ndarray | None = None):
    from concert_ranker.audio.cache import NativeProbe
    return NativeProbe(
        sr=int(nyquist * 2), psd_db=psd_db.astype(np.float32),
        psd_freqs=freqs.astype(np.float32), nyquist_hz=nyquist,
        window_psds_db=window_psds_db,
    )


def _flat_psd(nyquist=22050.0, level_db=-30.0):
    """Flat PSD up to nyquist (like a full-bandwidth source)."""
    freqs = np.linspace(0, nyquist, 2049)
    psd_db = np.full_like(freqs, level_db)
    return freqs, psd_db


def test_32k_dat_flag_clean_wall():
    """A clean 16 kHz wall (32k DAT) is flagged."""
    freqs = np.linspace(0, 22050.0, 2049)
    psd_db = np.where(freqs < 16000, -20.0, -80.0).astype(np.float32)
    p = _native_probe_from_psd(freqs, psd_db, nyquist=22050.0)
    from concert_ranker.features import _32k_dat_flag
    assert _32k_dat_flag(p) == 1.0


def test_32k_dat_flag_full_bandwidth_not_flagged():
    """A full-bandwidth signal (no ceiling) does not trigger the 32k DAT flag."""
    freqs, psd_db = _flat_psd(-20.0)
    p = _native_probe_from_psd(freqs, psd_db, nyquist=22050.0)
    from concert_ranker.features import _32k_dat_flag
    assert _32k_dat_flag(p) == 0.0


def test_cassette_rolloff_gradual_slope():
    """A gradual HF rolloff (cassette-like) is detected."""
    freqs = np.linspace(0, 22050.0, 2049)
    # Build a descending slope: -20 dB up to 15k, then gradual rolloff to -50 dB
    psd_db = np.where(freqs <= 15000, -20.0,
               np.where(freqs <= 17000, -20.0 - (freqs - 15000) / 100,
               np.where(freqs <= 18000, -40.0 - (freqs - 17000) / 50,
                        -60.0))).astype(np.float32)
    p = _native_probe_from_psd(freqs, psd_db, nyquist=22050.0)
    from concert_ranker.features import _cassette_rolloff_flag
    assert _cassette_rolloff_flag(p) == 1.0


def test_cassette_rolloff_full_bandwidth_not_flagged():
    """Full-bandwidth (no rolloff above 17k) does not trigger cassette flag."""
    freqs, psd_db = _flat_psd(-20.0)
    p = _native_probe_from_psd(freqs, psd_db, nyquist=22050.0)
    from concert_ranker.features import _cassette_rolloff_flag
    assert _cassette_rolloff_flag(p) == 0.0


def test_tv_band_elevated_with_variance():
    """An elevated, pulsing band at 15.6 kHz triggers the TV band flag."""
    freqs = np.linspace(0, 22050.0, 2049)
    psd_db = np.full_like(freqs, -30.0)
    # Narrow elevated peak at 15.5–15.8 kHz
    tv_mask = (freqs >= 15500) & (freqs < 15800)
    psd_db[tv_mask] = -15.0   # 15 dB above neighbors
    p_db = psd_db.astype(np.float32)

    # Per-window PSDs that show the band pulsing in and out
    n_win = 6
    win_db = np.tile(np.full_like(freqs, -30.0, dtype=np.float32), (n_win, 1))
    for i in range(n_win):
        # Alternate: even windows have the TV band, odd don't
        if i % 2 == 0:
            win_db[i, tv_mask] = -15.0

    p = _native_probe_from_psd(freqs, p_db, nyquist=22050.0, window_psds_db=win_db)
    from concert_ranker.features import _tv_band_flag
    assert _tv_band_flag(p) == 1.0


def test_tv_band_steady_not_flagged():
    """A steady elevated band (no variance across windows) is not flagged."""
    freqs = np.linspace(0, 22050.0, 2049)
    psd_db = np.full_like(freqs, -30.0)
    tv_mask = (freqs >= 15500) & (freqs < 15800)
    psd_db[tv_mask] = -15.0
    p_db = psd_db.astype(np.float32)

    # All windows identical → no pulsing
    n_win = 6
    win_db = np.tile(p_db, (n_win, 1))

    p = _native_probe_from_psd(freqs, p_db, nyquist=22050.0, window_psds_db=win_db)
    from concert_ranker.features import _tv_band_flag
    assert _tv_band_flag(p) == 0.0   # no variance → not a TV band
