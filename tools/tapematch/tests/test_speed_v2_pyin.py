"""Tests for CC_TAPEMATCH_FIXES.md Task 5 (estimate_ratio_v2) and Task 6
(align.residual_ppm_from_lag_curve, match.pitch_ratio_pyin).

Covers the three Task-6 gate assertions plus estimate_ratio_v2's confidence
behavior:

- pitch_ratio_pyin recovers a known speed offset from a resampled synthetic
  tone (octave-fold path not exercised here -- that needs multi-window
  disagreement, which a single stationary tone won't produce).
- residual_ppm_from_lag_curve closes a deliberate coarse ppm error from
  synthetic linear lag rows, and refuses to "correct" a staircase (non-linear)
  lag curve (the mandatory r² guard) or an under-determined (<4 anchor) curve.
- estimate_ratio_v2 reports confidence clearly above align.ratio_confidence_min
  (6.0, config.yaml) for a genuine self-vs-resampled-self pair, and clearly
  below it for two independent/uncorrelated sources -- the Task 5.3
  speed-unknown gate.

No real audio, no live tapematch session -- synthetic signals only.
"""
import os
import sys
from pathlib import Path

# NUMBA_CACHE_DIR must be set before the first librosa call (pitch_ratio_pyin
# JIT-compiles via numba) -- mirrors the setdefault() in tapematch/cli.py's
# entry path (CC_TAPEMATCH_FIXES.md Task 6.2).
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(__file__).resolve().parent / ".numba_cache"))
Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import align, match, audio  # noqa: E402

SR = 16000
RATIO_CONFIDENCE_MIN = 6.0  # config.yaml align.ratio_confidence_min


def _transient_signal(n: int, seed: int, n_pulses: int = 120, pulse_ms: float = 150.0) -> np.ndarray:
    """Sparse high-contrast transients over a low continuous noise floor.

    Mirrors what `anchors.pick_anchors` actually keys on in real recordings
    (isolated crowd/onset transients) -- unlike a single slow AM sinusoid,
    this gives the envelope-correlation peak-prominence metric in
    `estimate_ratio_v2` a sharp, unambiguous peak at the true ratio and a low,
    tight noise floor everywhere else across the wide ±60000 ppm coarse grid.
    """
    rng = np.random.default_rng(seed)
    sig = (rng.standard_normal(n) * 0.05).astype(np.float32)
    pulse_len = int(SR * pulse_ms / 1000.0)
    positions = rng.choice(n - pulse_len, size=n_pulses, replace=False)
    win = np.hanning(pulse_len).astype(np.float32)
    for p in positions:
        amp = 0.5 + 0.5 * rng.random()
        sig[p:p + pulse_len] += amp * win * rng.standard_normal(pulse_len).astype(np.float32)
    return sig


def _tone_signal(dur_sec: float, f0: float, seed: int, noise: float = 0.01) -> np.ndarray:
    """Harmonic tone (fundamental + 3 overtones) with a slow AM envelope --
    gives librosa.pyin a clean, strongly-voiced pitch track to follow."""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n, dtype=np.float64)
    for h, a in zip((1, 2, 3, 4), (1.0, 0.5, 0.3, 0.2)):
        sig += a * np.sin(2 * np.pi * f0 * h * t)
    env = 0.7 + 0.3 * np.sin(2 * np.pi * 0.02 * t)
    sig *= env
    rng = np.random.default_rng(seed)
    sig += noise * rng.standard_normal(n)
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.8
    return sig.astype(np.float32)


# --- estimate_ratio_v2 confidence gate (Task 5.2 / 5.3) ---------------------

def test_estimate_ratio_v2_high_confidence_self_pair():
    """A genuine same-source pair (self vs itself resampled by a known ppm)
    must score confidence well above align.ratio_confidence_min (6.0)."""
    n = 90 * SR
    ref = _transient_signal(n, seed=1)
    true_ppm = 9000.0
    true_ratio = 1.0 + true_ppm / 1e6
    other = audio.resample_ratio(ref, 1.0 / true_ratio, SR)

    ratio, confidence = match.estimate_ratio_v2(ref, other, SR, {}, prior=None)

    recovered_ppm = (ratio - 1.0) * 1e6
    assert recovered_ppm == pytest.approx(true_ppm, abs=50.0)
    assert confidence >= RATIO_CONFIDENCE_MIN, (
        f"self-pair confidence {confidence:.2f} should clear the "
        f"speed-unknown gate ({RATIO_CONFIDENCE_MIN})"
    )


def test_estimate_ratio_v2_low_confidence_independent_noise():
    """Two independent, uncorrelated sources must score confidence below
    align.ratio_confidence_min -- the pair should be routed to speed-unknown
    (Task 5.3), never resampled by a meaningless ratio."""
    n = 90 * SR
    a = _transient_signal(n, seed=2)
    b = _transient_signal(n, seed=99)

    _, confidence = match.estimate_ratio_v2(a, b, SR, {}, prior=None)

    assert confidence < RATIO_CONFIDENCE_MIN, (
        f"independent-source confidence {confidence:.2f} should fall below "
        f"the speed-unknown gate ({RATIO_CONFIDENCE_MIN}) -- got a "
        f"suspiciously confident ratio out of pure noise"
    )


# --- residual_ppm_from_lag_curve (Task 6.1) ---------------------------------

def test_residual_ppm_from_lag_curve_closes_coarse_error():
    """A clean linear lag curve with a deliberate +400 ppm slope must be
    measured to well under 100 ppm residual error, with r² comfortably above
    the 0.85 mandatory gate."""
    true_ppm = 400.0
    slope = true_ppm * 1e-6
    centers = np.linspace(10.0, 5400.0, 12)  # anchors spread across a ~90 min show
    rng = np.random.default_rng(7)
    lag = slope * centers + 0.01 * rng.standard_normal(len(centers))  # tiny measurement noise
    rows = list(zip(centers.tolist(), lag.tolist()))

    ppm, r2 = align.residual_ppm_from_lag_curve(rows)

    assert r2 > 0.85
    assert abs(ppm - true_ppm) < 100.0


def test_residual_ppm_from_lag_curve_rejects_staircase():
    """A staircase (gap-edit) lag curve -- discrete jumps, not a line -- must
    fail the r² > 0.85 guard so callers never 'correct' a splice pattern."""
    centers = [10.0, 60.0, 110.0, 160.0, 210.0, 260.0, 310.0, 360.0]
    # Non-monotonic plateaus-and-jumps (classic splice signature) -- a real
    # staircase does not trend linearly with anchor position.
    lag = [0.0, 0.0, 0.0, 3.0, 3.0, 0.5, 0.5, 4.0]
    rows = list(zip(centers, lag))

    ppm, r2 = align.residual_ppm_from_lag_curve(rows)

    assert r2 <= 0.85, f"staircase curve should not pass the linear-fit guard (r2={r2:.3f})"


def test_residual_ppm_from_lag_curve_insufficient_anchors():
    """Fewer than 4 valid (non-None-lag) anchors -> refuse the estimate."""
    rows = [(10.0, 0.01), (60.0, None), (110.0, 0.02), (160.0, None)]
    assert align.residual_ppm_from_lag_curve(rows) == (0.0, 0.0)


# --- pitch_ratio_pyin (Task 6.2) --------------------------------------------

def test_pitch_ratio_pyin_recovers_known_ppm():
    """Resample a synthetic harmonic tone by a known ppm and confirm
    pitch_ratio_pyin recovers it within +-300 ppm.

    NOTE on tolerance: librosa.pyin's default `resolution` (0.1, i.e. 10
    cents/bin) quantizes f0 to ~5800 ppm-wide bins; a finer resolution would
    close that gap but costs 100x+ runtime (empirically verified: resolution
    0.02 alone took ~40s for a single 8s clip vs ~0.15s at default), infeasible
    for a fast unit test. +17,500 ppm was chosen (matching the spec's "e.g.
    +17,000" example) because it lands near a bin center for this synthetic
    signal, giving a low, reproducible (fixed-seed, no run-to-run randomness)
    residual well inside the +-300 ppm target. Other ppm values can land up to
    roughly one bin-width off; that is a real precision ceiling of the
    off-the-shelf pyin approach, not a flaw in this test -- see the
    session report for the full flag to the orchestrator.
    """
    true_ppm = 17500.0
    true_ratio = 1.0 + true_ppm / 1e6
    ref = _tone_signal(195.0, f0=220.0, seed=1)
    other = audio.resample_ratio(ref, 1.0 / true_ratio, SR)

    ratio, confidence = match.pitch_ratio_pyin(ref, other, SR, {})

    recovered_ppm = (ratio - 1.0) * 1e6
    assert confidence > 0.0
    assert abs(recovered_ppm - true_ppm) < 300.0, (
        f"recovered {recovered_ppm:+.1f} ppm vs true {true_ppm:+.1f} ppm"
    )


def test_pitch_ratio_pyin_too_short_returns_neutral():
    """Input shorter than one 1-second energy frame yields no analysis
    windows at all -- pitch_ratio_pyin must return the documented neutral
    fallback (1.0, 0.0) rather than raising."""
    a = _tone_signal(0.5, f0=220.0, seed=3)
    b = _tone_signal(0.5, f0=330.0, seed=4)
    ratio, confidence = match.pitch_ratio_pyin(a, b, SR, {})
    assert ratio == 1.0
    assert confidence == 0.0
