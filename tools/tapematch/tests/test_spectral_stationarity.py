"""Task 3.3 synthetic tests for spectral-ratio stationarity
(CC_TAPEMATCH_ADDON.md Task 3): same signal + fixed EQ -> high stationarity;
two different signals / slowly time-varying EQ -> low stationarity;
alignment-jitter robustness (+-0.5s). No live audio.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import match  # noqa: E402

SR = 16000

CFG = {"spectral_stationarity": {
    "enabled": True,
    "window_sec": 15.0, "hop_sec": 7.5, "local_lag_sec": 2.0,
    "n_mels": 16, "stft_nperseg": 512, "stft_hop": 128,
    "noise_floor_margin_db": 6.0, "min_frames_per_window": 15,
    "stationarity_norm_db": 6.0, "stationarity_min_windows": 4,
}}

DUR_SEC = 90.0
HF_CEIL = 4000.0
NOISE_FLOOR_DB = -60.0


def _make_base(seed: int, dur_sec: float = DUR_SEC, n_segments: int = 9) -> np.ndarray:
    """A "music-like" signal: `n_segments` blocks, each a random 3-tone chord.

    Content genuinely varies over time (unlike a single stationary tone bed) --
    needed so a same-signal/fixed-EQ pair's log-spectral ratio is tested for
    true time-INVARIANCE (constant transfer function) rather than trivially
    passing because neither side's spectrum ever changes.
    """
    rng = np.random.default_rng(seed)
    n = int(dur_sec * SR)
    x = np.zeros(n, dtype=np.float32)
    seg_len = n // n_segments
    for k in range(n_segments):
        i0, i1 = k * seg_len, min(n, (k + 1) * seg_len)
        t = np.arange(i1 - i0) / SR
        freqs = rng.uniform(150.0, 3500.0, size=3)
        amps = rng.uniform(0.05, 0.3, size=3)
        seg = sum(a * np.sin(2 * np.pi * f * t) for a, f in zip(amps, freqs))
        x[i0:i1] = seg
    x += 0.02 * rng.standard_normal(n)
    return x.astype(np.float32)


def _fixed_eq(x: np.ndarray, seed: int, cutoff_hz: float = 3000.0) -> np.ndarray:
    """A single, constant low-pass transfer function + noise -- the "same
    lineage, fixed copy-chain EQ/band-limit" case."""
    sos = butter(4, cutoff_hz / (SR / 2), btype="low", output="sos")
    y = sosfilt(sos, x).astype(np.float32)
    y += 0.01 * np.random.default_rng(seed).standard_normal(len(x)).astype(np.float32)
    return y


def _time_varying_eq(x: np.ndarray, seed: int, nblocks: int = 6) -> np.ndarray:
    """Low-pass cutoff sweeps block-to-block -- a transfer function that
    changes over time, e.g. levels/room response drifting through a show."""
    rng = np.random.default_rng(seed)
    n = len(x)
    blen = n // nblocks
    y = np.zeros_like(x)
    for k in range(nblocks):
        i0, i1 = k * blen, min(n, (k + 1) * blen)
        cutoff = 800.0 + 5000.0 * k / nblocks
        sos_k = butter(4, min(cutoff, SR / 2 * 0.99) / (SR / 2), btype="low", output="sos")
        y[i0:i1] = sosfilt(sos_k, x[i0:i1])
    y += 0.01 * rng.standard_normal(n).astype(np.float32)
    return y.astype(np.float32)


def _stat(a, b, hf_a=HF_CEIL, hf_b=HF_CEIL, nf_a=NOISE_FLOOR_DB, nf_b=NOISE_FLOOR_DB,
         predicted_lag=None):
    return match.spectral_ratio_stationarity(a, b, SR, CFG, hf_a, hf_b, nf_a, nf_b,
                                             predicted_lag=predicted_lag)


# ── 3.1: same-lineage fixed EQ -> high stationarity ────────────────────────

def test_same_signal_fixed_eq_stationarity_high():
    base = _make_base(seed=1)
    fixed = _fixed_eq(base, seed=2)
    score = _stat(base, fixed)
    assert score is not None
    assert score >= 0.8, f"expected high stationarity under a fixed transfer fn, got {score}"


# ── 3.1/3.3: instability cases -> low stationarity ─────────────────────────

def test_two_different_signals_stationarity_low():
    a = _make_base(seed=10)
    b = _make_base(seed=11)   # independent content
    score = _stat(a, b)
    assert score is not None
    assert score <= 0.3, f"expected low stationarity for unrelated signals, got {score}"


def test_slowly_time_varying_eq_stationarity_lower_than_fixed():
    base = _make_base(seed=20)
    fixed = _fixed_eq(base, seed=21)
    time_varying = _time_varying_eq(base, seed=22)
    score_fixed = _stat(base, fixed)
    score_tv = _stat(base, time_varying)
    assert score_fixed is not None and score_tv is not None
    assert score_tv < score_fixed - 0.1, (
        f"expected a drifting transfer function to score well below a fixed one "
        f"(fixed={score_fixed}, time_varying={score_tv})")


# ── 3.3: alignment-jitter robustness (+-0.5s) ───────────────────────────────

def test_alignment_jitter_robust_within_half_second():
    """A constant sub-second misalignment must not degrade the score: each
    window's own local-lag search (local_lag_sec=2.0 here, well over 0.5s)
    re-aligns before the ratio is measured."""
    base = _make_base(seed=30)
    fixed = _fixed_eq(base, seed=31)
    jitter_samp = int(0.4 * SR)
    shifted = np.concatenate(
        [np.zeros(jitter_samp, dtype=np.float32), fixed])[:len(fixed)]
    score_plain = _stat(base, fixed)
    score_jittered = _stat(base, shifted)
    assert score_plain is not None and score_jittered is not None
    assert abs(score_jittered - score_plain) < 0.05, (
        f"expected jitter-robust score (local_lag search absorbs +-0.5s), "
        f"got plain={score_plain} jittered={score_jittered}")


# ── None-coercion / edge-case discipline ────────────────────────────────────

def test_none_when_too_short_for_min_windows():
    short = _make_base(seed=40, dur_sec=5.0, n_segments=1)
    result = _stat(short, short)
    assert result is None
    assert not isinstance(result, float)


def test_none_when_hf_ceiling_cap_is_zero():
    base = _make_base(seed=41)
    fixed = _fixed_eq(base, seed=42)
    # hf_ceiling 0.0 on one side (e.g. a lineage_evidence probe that found
    # nothing above the floor) must yield None, not a degenerate 0-band score.
    result = _stat(base, fixed, hf_a=0.0)
    assert result is None


def test_clipped_to_unit_interval():
    base = _make_base(seed=50)
    fixed = _fixed_eq(base, seed=51)
    score = _stat(base, fixed)
    assert score is not None
    assert 0.0 <= score <= 1.0
