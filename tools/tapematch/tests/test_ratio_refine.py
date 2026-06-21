"""Tests for lag-curve-slope speed-ratio refinement (match.refine_speed_ratio).

Motivation: the coarse envelope estimate_ratio resolves speed to ~500 ppm, but a
45s residual_corr window decorrelates above ~20 ppm residual speed error, so
high-ppm same-source pairs were being called "distinct". The refinement reads the
residual speed off the per-anchor lag slope (drift-robust music correlation) and
corrects the ratio.

Covers:
- corrected_ratio_from_lags: the pure slope->ratio math, including sign.
- refine_speed_ratio: recovers a known speed offset (in range, and beyond the old
  +-20000 ppm rail) to within a tight ppm tolerance.
- different-source control: refinement does not manufacture a high residual_corr
  (cannot create a false merge).
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import match, audio  # noqa: E402

SR = 16000


def _band_limited(n, seed, cutoff_hz=4000.0):
    """Music-like band-limited carrier with a slow amplitude envelope."""
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(seed)
    sos = butter(6, cutoff_hz / (SR / 2), btype="low", output="sos")
    carrier = sosfiltfilt(sos, rng.standard_normal(n)).astype(np.float32)
    t = np.arange(n) / SR
    env = (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 0.05 * t))).astype(np.float32)
    return (env * carrier).astype(np.float32)


def _cfg():
    return {
        "anchors": {"window_sec": 45.0},
        "align": {"max_lag_sec": 90.0},
        "match": {"cluster_threshold": 0.45},
        "refine": {"max_iter": 3, "stop_ppm": 5.0},
    }


def test_corrected_ratio_from_lags_math_and_sign():
    centers = [10.0, 60.0, 110.0, 160.0]
    # A residual +300 ppm speed error shows up as a +300e-6 lag slope.
    slope = 300e-6
    lags = [slope * c for c in centers]
    corrected, ppm = match.corrected_ratio_from_lags(centers, lags, ratio=1.012)
    assert ppm == pytest.approx(300.0, abs=1.0)
    # ratio is corrected downward: 1.012 / (1 + 300e-6)
    assert corrected == pytest.approx(1.012 / (1 + slope), rel=1e-9)


def test_corrected_ratio_from_lags_underdetermined_is_noop():
    assert match.corrected_ratio_from_lags([1.0, 2.0], [0.0, 0.0], 1.005) == (1.005, 0.0)


@pytest.mark.parametrize("true_ppm", [8000, -12000, 25000])
def test_refine_recovers_speed_offset(true_ppm):
    """Refinement recovers the true ratio from a coarse-grid / railed start,
    including +25000 ppm (beyond the old +-20000 ppm search rail)."""
    dur = 180
    n = dur * SR
    ref = _band_limited(n, seed=1)
    true_ratio = 1.0 + true_ppm / 1e6
    other = audio.resample_ratio(ref, 1.0 / true_ratio, SR)

    # Coarse start: quantize to the 500 ppm grid and clamp to the old +-20000 rail,
    # reproducing the failure conditions.
    coarse = round(true_ratio / 5e-4) * 5e-4
    coarse = float(np.clip(coarse, 0.980, 1.020))

    anchors = list(np.linspace(20, dur - 20, 10))
    refined, _ = match.refine_speed_ratio(ref, other, SR, anchors, _cfg(), coarse)

    residual_ppm = abs(refined - true_ratio) / true_ratio * 1e6
    assert residual_ppm < 60.0, f"residual {residual_ppm:.0f} ppm too large"


def test_refine_does_not_merge_different_sources():
    """Two independent recordings: refinement must not produce a high
    residual_corr (no false merge), regardless of the ratio it lands on."""
    dur = 150
    n = dur * SR
    ref = _band_limited(n, seed=2)
    other = _band_limited(n, seed=99)  # independent source, same envelope family

    anchors = list(np.linspace(20, dur - 20, 10))
    _, corrs = match.refine_speed_ratio(ref, other, SR, anchors, _cfg(), 1.012)
    med = float(np.median(corrs)) if corrs else 0.0
    assert med < _cfg()["match"]["cluster_threshold"], (
        f"different-source median corr {med:.3f} would falsely merge"
    )
