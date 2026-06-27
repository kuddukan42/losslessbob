"""Tests for match.lowband_envelope_corr (TODO-140).

lowband_envelope_corr bandpass-filters two mono arrays to a low-frequency band
(default 250-2000 Hz), computes log-RMS energy envelopes, and cross-correlates
them via a lag search -- no waveform resampling (WORKFLOW.md prohibition).

Covers:
- same signal (offset copy) yields near-1.0 correlation at the right lag;
- independent signals yield near-zero correlation;
- lag is recovered correctly when b leads a;
- very short input returns a safe zero result.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import match  # noqa: E402

SR = 16000


def _pure_lowband(n: int, seed: int) -> np.ndarray:
    """Pure bandpass noise (250-2000 Hz) — no shared amplitude envelope across seeds."""
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(seed)
    sos = butter(4, [250 / (SR / 2), 2000 / (SR / 2)], btype="band", output="sos")
    return sosfiltfilt(sos, rng.standard_normal(n)).astype(np.float32)


def _am_lowband(n: int, seed: int, mod_hz: float = 0.05) -> np.ndarray:
    """AM-modulated lowband signal — has a slow dynamic envelope for lag recovery."""
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(seed)
    sos = butter(4, [250 / (SR / 2), 2000 / (SR / 2)], btype="band", output="sos")
    carrier = sosfiltfilt(sos, rng.standard_normal(n)).astype(np.float32)
    t = np.arange(n) / SR
    # Use a non-round modulation frequency to avoid periodicity aliasing.
    env = (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * mod_hz * t))).astype(np.float32)
    return (env * carrier).astype(np.float32)


def test_same_signal_scores_high():
    sig = _am_lowband(SR * 120, seed=1)
    result = match.lowband_envelope_corr(sig, sig, SR)
    assert result["corr"] > 0.90
    assert abs(result["lag_sec"]) < 1.0


def test_independent_signals_score_low():
    # Pure noise, no shared deterministic amplitude envelope between seeds.
    a = _pure_lowband(SR * 120, seed=2)
    b = _pure_lowband(SR * 120, seed=99)
    result = match.lowband_envelope_corr(a, b, SR)
    assert abs(result["corr"]) < 0.30


def test_lag_recovered_for_offset_copy():
    # a = sig[0:N-L], b = sig[L:N] → b leads a by offset_sec → lag_sec ≈ -offset_sec
    sig = _am_lowband(SR * 180, seed=3)
    offset_sec = 5.0
    offset_samp = int(offset_sec * SR)
    a = sig[:-offset_samp]
    b = sig[offset_samp:]
    result = match.lowband_envelope_corr(a, b, SR, max_lag_sec=20.0)
    assert result["corr"] > 0.85
    assert abs(abs(result["lag_sec"]) - offset_sec) < 1.5  # magnitude within 1.5s


def test_short_input_returns_zero():
    short = np.zeros(10, dtype=np.float32)
    result = match.lowband_envelope_corr(short, short, SR)
    assert result["corr"] == 0.0
    assert result["n_env_samples"] == 0
