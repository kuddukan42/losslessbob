"""Tests for predicted-lag mode (CC_TAPEMATCH_FIXES.md Task 4).

Covers:
- align.local_lag_centered: finds a lag well beyond +-max_lag_sec when the
  search is centered on the correct predicted value, and does not find it
  when centered on zero with the same +-max_lag_sec.
- match.secondary_corr_pair: predicted-lag mode recovers high windowed
  coverage for a pair whose constant offset exceeds local_lag_sec, while
  the same call without predicted_lag (or with ppm below
  high_ppm_threshold) leaves the zero-centered search unchanged.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import align, match  # noqa: E402

SR = 1000


def _white_noise(n, seed):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n).astype(np.float32)


def _delayed(sig, delay_samples, pad_seed):
    pad = _white_noise(delay_samples, pad_seed)
    return np.concatenate([pad, sig[:-delay_samples]]).astype(np.float32)


def test_local_lag_centered_finds_true_lag_beyond_max_lag_sec():
    n = 60 * SR
    sig = _white_noise(n, seed=10)
    true_lag_sec = 8.2
    delay_samples = int(round(true_lag_sec * SR))
    other = _delayed(sig, delay_samples, pad_seed=11)

    center_sec = 30.0
    window_sec = 10.0
    max_lag_sec = 2.0

    # Centered on the true lag: +-2s residual search finds it exactly.
    lag, peak = align.local_lag_centered(
        sig, other, SR, center_sec, window_sec, max_lag_sec, true_lag_sec
    )
    assert lag is not None
    assert abs(lag - true_lag_sec) < 1e-6
    assert peak > 0.9

    # Centered on zero with the same +-2s: the true lag (8.2s) is outside
    # the search window, so the result cannot be the true lag.
    lag0, _ = align.local_lag_centered(sig, other, SR, center_sec, window_sec, max_lag_sec, 0.0)
    assert lag0 is None or abs(lag0 - true_lag_sec) > max_lag_sec


def _base_cfg():
    return {
        "secondary_match": {
            "window_sec": 10.0,
            "hop_sec": 10.0,
            "local_lag_sec": 2.0,
            "window_corr_threshold": 0.5,
            "quiet_energy_percentile": 25,
            "min_quiet_sec": 3.0,
            "hiss_lag_sec": 2.0,
            "hiss_corr_threshold": 0.9,
            "high_ppm_threshold": 5000,
        }
    }


def test_secondary_corr_pair_predicted_lag_recovers_high_offset_pair():
    n = 120 * SR
    delay_sec = 8.2
    delay_samples = int(round(delay_sec * SR))

    sig = _white_noise(n, seed=42)
    other = _delayed(sig, delay_samples, pad_seed=43)

    cfg = _base_cfg()
    predicted_lag = {"ppm": 5000.0, "lag_0": delay_sec, "anchor0_sec": 0.0}

    with_pred = match.secondary_corr_pair(sig, other, SR, cfg, predicted_lag=predicted_lag)
    without_pred = match.secondary_corr_pair(sig, other, SR, cfg, predicted_lag=None)

    assert with_pred["windowed_frac"] > 0.9
    assert without_pred["windowed_frac"] < 0.5


def test_secondary_corr_pair_below_threshold_unchanged():
    """ppm below high_ppm_threshold leaves the zero-centered search unchanged,
    even if lag_0 is supplied."""
    n = 120 * SR
    sig = _white_noise(n, seed=1)
    other = sig.copy()  # zero-lag, perfectly aligned pair

    cfg = _base_cfg()
    # ppm below threshold -> predicted-lag mode must not activate, despite a
    # wildly wrong lag_0.
    predicted_lag = {"ppm": 100.0, "lag_0": 50.0, "anchor0_sec": 0.0}
    result = match.secondary_corr_pair(sig, other, SR, cfg, predicted_lag=predicted_lag)
    assert result["windowed_frac"] > 0.9
