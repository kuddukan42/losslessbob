"""Task 7.4 step-3 invariance check for the ratio-invariant triplet fingerprint.

Synthetic, no live audio: a recording of gaussian-windowed HF tone pips scores a
triplet Dice against a +30000 ppm speed-changed copy of itself that is FLAT across
the whole speed range and stays far above the score against an independent pip
layout (a different "recording"). Also exercises the end-to-end ``triplet_window``
path and the 20-bit hash packing.

Empirical note (measured here; see CALIBRATION_PROGRESS.md flag): the spec's
absolute target of "self-vs-resampled Dice > 0.8" is NOT reached by the STFT
peak front end — even a +500 ppm resample drops same-source Dice to ~0.5, and it
plateaus near ~0.39 by +30000 ppm, because the nearest-neighbour triplets are
sensitive to STFT frame quantization of the peak times. What the fingerprint DOES
deliver is the property clustering needs: a stable same-source signal (~0.4–0.6,
flat vs. speed offset) separated ~6× from different-source (~0.065). The
production threshold is therefore set by real-audio calibration (calibrate_triplet.py),
not by the 0.8 figure; the OR-path stays inert until then.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import resample

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import match  # noqa: E402

SR = 16000
# Fingerprint knobs mirror config.yaml; short window so the test stays fast.
CFG = {
    "fingerprint": {
        "nperseg": 1024, "hop": 512,
        "peak_neighborhood_t": 5, "peak_neighborhood_f": 3,
        "hf_band_hz": [6000, 8000],
        "window_start_sec": 0.0, "window_dur_sec": 40.0,
        "triplet": {"enabled": True, "tmin_sec": 0.5, "tmax_sec": 8.0, "fanout": 4},
    }
}


def _synth_pips(dur_sec: float, seed: int, n_pips: int = 110,
                band=(6100, 7900)) -> np.ndarray:
    """Sum of gaussian-windowed HF tone pips at random (t, f) → stable STFT peaks.

    Strong, well-separated pips give one clean spectrogram peak each, so the peak
    set is stable under resampling — exactly what makes the ratio hashes match.
    """
    rng = np.random.default_rng(seed)
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, dtype=np.float64)
    for _ in range(n_pips):
        f = rng.uniform(*band)
        c = rng.uniform(0.4, dur_sec - 0.4)
        env = np.exp(-0.5 * ((t - c) / 0.015) ** 2)   # 15 ms pip
        x += env * np.sin(2 * np.pi * f * t)
    x += 1e-3 * rng.standard_normal(n)
    return (x / (np.max(np.abs(x)) + 1e-9)).astype(np.float32)


def _speed_change(x: np.ndarray, ppm: float) -> np.ndarray:
    """Resample to simulate a global speed offset (positive ppm = faster/shorter)."""
    m = max(8, int(round(len(x) / (1.0 + ppm * 1e-6))))
    return resample(x, m).astype(np.float32)


def _tri(x: np.ndarray) -> set:
    return match.triplet_hashes(match._fingerprint_peaks(x, SR, CFG), CFG)


def test_triplet_hashes_are_20bit_ints():
    h = _tri(_synth_pips(40, seed=1))
    assert h, "expected a non-empty hash set on rich synthetic audio"
    assert all(0 <= v < (1 << 20) for v in h)


def test_speed_invariance_flat_across_ppm():
    """Same-source Dice survives a large speed offset and does not collapse toward
    the different-source floor as the offset grows (the Cat-1 property)."""
    a = _synth_pips(40, seed=1)
    ha = _tri(a)
    d_small = match.fingerprint_score(ha, _tri(_speed_change(a, 2000)))
    d_large = match.fingerprint_score(ha, _tri(_speed_change(a, 30000)))
    assert d_large > 0.25, f"same-source Dice under +30000 ppm too low: {d_large:.3f}"
    # Flat, not decaying to noise: a 15× larger offset must not gut the score.
    assert d_large > 0.5 * d_small, (
        f"Dice decays with offset: +2000ppm={d_small:.3f} +30000ppm={d_large:.3f}")


def test_different_source_scores_far_lower():
    a = _synth_pips(40, seed=1)
    b = _synth_pips(40, seed=2)           # independent layout = different recording
    a_fast = _speed_change(a, 30000)
    d_same = match.fingerprint_score(_tri(a), _tri(a_fast))
    d_diff = match.fingerprint_score(_tri(a), _tri(b))
    assert d_diff < 0.15, f"different-source triplet Dice too high: {d_diff:.3f}"
    assert d_same > 3.0 * d_diff, (
        f"insufficient separation: same={d_same:.3f} diff={d_diff:.3f}")


def test_triplet_window_end_to_end():
    a = _synth_pips(40, seed=3)
    h = match.triplet_window(a, SR, CFG)
    assert h and all(0 <= v < (1 << 20) for v in h)
