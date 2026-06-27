"""Tests for windowed landmark-fingerprint localization (TODO-185, revised approach).

Motivation: a curator-claimed shared transient (e.g. a few seconds of shared
crowd/clapping at a track boundary) can be far shorter than the 60s grid
secondary_corr_pair uses, and can land at a different absolute offset in each
recording when the two are composite/patchwork sources with differing track
splits. windowed_fingerprints + best_window_fingerprint_match search every
window-pair (not just matching positions) for the best landmark-hash overlap,
so a localized match is found wherever it falls in either timeline.

Covers:
- a short HF landmark "marker" shared between two recordings, placed at
  different absolute offsets in each, is found by best_window_fingerprint_match
  with a high Dice score and a center time near the true marker location;
- two recordings with no shared content score low everywhere (no false match);
- fingerprint_window's fixed-window output still matches a direct
  _fingerprint_hashes() call on the same slice (refactor regression guard).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import match  # noqa: E402

SR = 16000

CFG = {
    "fingerprint": {
        "window_start_sec": 2.0,
        "window_dur_sec": 5.0,
        "nperseg": 1024,
        "hop": 512,
        "peak_neighborhood_t": 5,
        "peak_neighborhood_f": 3,
        "fanout": 5,
        "dt_bins": 100,
        "hf_band_hz": [6000, 8000],
    }
}


def _hf_background(n: int, seed: int, amp: float = 0.02) -> np.ndarray:
    """Low-amplitude, decorrelated HF-band noise -- stand-in for unrelated content."""
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(seed)
    sos = butter(6, [6000 / (SR / 2), 7999 / (SR / 2)], btype="band", output="sos")
    return (amp * sosfiltfilt(sos, rng.standard_normal(n))).astype(np.float32)


def _hf_marker(n: int) -> np.ndarray:
    """Strong, deterministic multi-tone HF burst -- same content each call."""
    t = np.arange(n) / SR
    tones = [6200.0, 6600.0, 7000.0, 7400.0, 7800.0]
    sig = sum(np.sin(2 * np.pi * f * t) for f in tones)
    return sig.astype(np.float32)


def _splice(total_sec: float, marker_center_sec: float, marker_dur_sec: float,
            seed: int) -> np.ndarray:
    n_total = int(total_sec * SR)
    out = _hf_background(n_total, seed)
    n_marker = int(marker_dur_sec * SR)
    start = int((marker_center_sec - marker_dur_sec / 2) * SR)
    out[start:start + n_marker] += _hf_marker(n_marker)
    return out


def test_shared_marker_at_different_offsets_is_localized():
    rec_a = _splice(total_sec=80.0, marker_center_sec=30.0, marker_dur_sec=6.0, seed=1)
    rec_b = _splice(total_sec=80.0, marker_center_sec=55.0, marker_dur_sec=6.0, seed=2)

    win_sec, hop_sec = 10.0, 5.0
    hashes_a = match.windowed_fingerprints(rec_a, SR, CFG, win_sec, hop_sec)
    hashes_b = match.windowed_fingerprints(rec_b, SR, CFG, win_sec, hop_sec)
    assert len(hashes_a) > 1 and len(hashes_b) > 1

    best = match.best_window_fingerprint_match(hashes_a, hashes_b, win_sec, hop_sec)
    assert best["dice"] > 0.5, f"expected a strong localized match, got {best}"
    assert abs(best["center_a_sec"] - 30.0) <= win_sec
    assert abs(best["center_b_sec"] - 55.0) <= win_sec


def test_no_shared_content_scores_low():
    rec_a = _splice(total_sec=80.0, marker_center_sec=30.0, marker_dur_sec=6.0, seed=3)
    rec_b = _hf_background(int(80.0 * SR), seed=4)  # no marker anywhere

    win_sec, hop_sec = 10.0, 5.0
    hashes_a = match.windowed_fingerprints(rec_a, SR, CFG, win_sec, hop_sec)
    hashes_b = match.windowed_fingerprints(rec_b, SR, CFG, win_sec, hop_sec)

    best = match.best_window_fingerprint_match(hashes_a, hashes_b, win_sec, hop_sec)
    assert best["dice"] < 0.3, f"expected no usable match, got {best}"


def test_windowed_fingerprints_empty_for_too_short_recording():
    short = _hf_background(int(2.0 * SR), seed=5)
    out = match.windowed_fingerprints(short, SR, CFG, win_sec=10.0, hop_sec=5.0)
    assert out == []


def test_fingerprint_window_matches_direct_hashes_call():
    """fingerprint_window's fixed-window slice should produce the same hashes
    as calling _fingerprint_hashes directly on the same slice (refactor guard)."""
    rec = _splice(total_sec=20.0, marker_center_sec=4.0, marker_dur_sec=3.0, seed=6)
    via_window = match.fingerprint_window(rec, SR, CFG)

    fp = CFG["fingerprint"]
    start = int(fp["window_start_sec"] * SR)
    dur = int(fp["window_dur_sec"] * SR)
    sliced = np.array(rec[start:start + dur], dtype=np.float32)
    direct = match._fingerprint_hashes(sliced, SR, CFG)

    assert via_window == direct
