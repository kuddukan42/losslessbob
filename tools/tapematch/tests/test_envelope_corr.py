"""Task 4.3 synthetic tests for band-limited envelope correlation
(CC_TAPEMATCH_ADDON.md Task 4): same recording + fixed band-limit/EQ + noise ->
near 1.0; two independent signals -> low; <10 min overlap -> None; speed-warp
robustness (+-5000ppm). No live audio.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import match  # noqa: E402
from tapematch.audio import resample_ratio  # noqa: E402

SR = 16000
HF_CEIL = 4000.0   # well above band_hi_cap_hz (2000) -- exercises the band cap,
                   # not the HF-ceiling cap.

# min_overlap_min scaled down to 1.0 (60s) so synthetic signals stay short --
# same convention as test_spectral_stationarity.py's scaled-down window/hop
# knobs. test_none_below_min_overlap below restores the real 10-minute spec
# default to prove the None-below-threshold behaviour.
CFG = {"envelope_corr": {
    "enabled": True, "band_lo_hz": 200.0, "band_hi_cap_hz": 2000.0,
    "frame_rate_hz": 20.0, "filter_order": 6, "min_overlap_min": 1.0,
}}


def _make_base(seed: int, dur_sec: float, n_segments: int = 9) -> np.ndarray:
    """A "music-like" signal: n_segments blocks, each a random 3-tone chord
    within the envelope-corr band, so RMS-envelope dynamics genuinely vary
    block-to-block (not a single stationary tone bed)."""
    rng = np.random.default_rng(seed)
    n = int(dur_sec * SR)
    x = np.zeros(n, dtype=np.float32)
    seg_len = n // n_segments
    for k in range(n_segments):
        i0, i1 = k * seg_len, min(n, (k + 1) * seg_len)
        t = np.arange(i1 - i0) / SR
        freqs = rng.uniform(250.0, 1800.0, size=3)
        amps = rng.uniform(0.05, 0.3, size=3)
        seg = sum(a * np.sin(2 * np.pi * f * t) for a, f in zip(amps, freqs))
        x[i0:i1] = seg
    x += 0.02 * rng.standard_normal(n)
    return x.astype(np.float32)


def _fixed_bandlimit_eq(x: np.ndarray, seed: int, cutoff_hz: float = 1500.0) -> np.ndarray:
    """A single, constant low-pass transfer fn + noise -- "same lineage,
    fixed copy-chain EQ/band-limit"."""
    sos = butter(4, cutoff_hz / (SR / 2), btype="low", output="sos")
    y = sosfilt(sos, x).astype(np.float32)
    y += 0.01 * np.random.default_rng(seed).standard_normal(len(x)).astype(np.float32)
    return y


def _env(a, b, ratio=1.0, offset=0.0, hf_a=HF_CEIL, hf_b=HF_CEIL, cfg=CFG):
    return match.envelope_corr(a, b, SR, cfg, hf_a, hf_b, ratio, offset)


# ── 4.1: same recording, fixed band-limit/EQ + noise -> near 1.0 ───────────

def test_same_recording_fixed_eq_near_one():
    base = _make_base(seed=1, dur_sec=90.0)
    degraded = _fixed_bandlimit_eq(base, seed=2)
    score = _env(base, degraded)
    assert score is not None
    assert score >= 0.9, f"expected near-1.0 envelope corr for same recording, got {score}"


# ── two independent signals -> low ──────────────────────────────────────────

def test_independent_signals_low():
    a = _make_base(seed=10, dur_sec=90.0)
    b = _make_base(seed=11, dur_sec=90.0)   # independent content
    score = _env(a, b)
    assert score is not None
    assert score <= 0.5, f"expected low envelope corr for independent signals, got {score}"


# ── <10 min overlap -> None ─────────────────────────────────────────────────

def test_none_below_min_overlap():
    """Real spec threshold (10 min): a 90s pair must yield None, not a
    degenerate score over a handful of frames."""
    spec_cfg = {"envelope_corr": {**CFG["envelope_corr"], "min_overlap_min": 10.0}}
    base = _make_base(seed=20, dur_sec=90.0)
    degraded = _fixed_bandlimit_eq(base, seed=21)
    result = _env(base, degraded, cfg=spec_cfg)
    assert result is None
    assert not isinstance(result, float)


def test_none_when_offset_pushes_overlap_out_of_range():
    base = _make_base(seed=22, dur_sec=90.0)
    degraded = _fixed_bandlimit_eq(base, seed=23)
    # Offset larger than the signal duration -> zero overlap regardless of ratio.
    result = _env(base, degraded, offset=500.0)
    assert result is None


# ── speed-warp robustness (+-5000 ppm) ──────────────────────────────────────

def test_speed_warp_positive_ppm_still_correlates():
    base = _make_base(seed=30, dur_sec=120.0)
    degraded = _fixed_bandlimit_eq(base, seed=31)
    ppm = 5000.0
    ratio = 1.0 + ppm * 1e-6
    # `warped` is what a genuine tape-speed error produces: degraded's clock
    # stretched by `ratio`, i.e. t_warped = ratio * t_degraded -- exactly the
    # mapping envelope_corr expects when called with speed_ratio=ratio.
    warped = resample_ratio(degraded, ratio, SR)
    score = _env(base, warped, ratio=ratio, offset=0.0)
    assert score is not None
    assert score >= 0.85, f"expected speed-map to recover near-1.0 corr, got {score}"


def test_speed_warp_negative_ppm_still_correlates():
    base = _make_base(seed=32, dur_sec=120.0)
    degraded = _fixed_bandlimit_eq(base, seed=33)
    ppm = -5000.0
    ratio = 1.0 + ppm * 1e-6
    warped = resample_ratio(degraded, ratio, SR)
    score = _env(base, warped, ratio=ratio, offset=0.0)
    assert score is not None
    assert score >= 0.85, f"expected speed-map to recover near-1.0 corr, got {score}"


# ── None-coercion / edge-case discipline ────────────────────────────────────

def test_none_when_hf_ceiling_below_band_lo():
    base = _make_base(seed=40, dur_sec=90.0)
    degraded = _fixed_bandlimit_eq(base, seed=41)
    # hf_ceiling below band_lo_hz (200) -> degenerate band, must be None not 0.0.
    result = _env(base, degraded, hf_a=100.0)
    assert result is None
    assert not isinstance(result, float)
