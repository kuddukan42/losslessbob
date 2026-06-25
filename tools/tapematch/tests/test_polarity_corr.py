"""Tests for single-channel polarity-inversion rescue (match.polarity_aware_corr).

Motivation (TODO-184): Pass 1 ingests the L+R "mid" mixdown only. A genuine
same-source copy with ONE channel polarity-inverted ("right channel inverted")
reads near-zero on mid-vs-mid, because copy_mid == L-R == ref_side. The match
survives only in the L-R cross term, so polarity_aware_corr scores mid-mid,
mid-side and side-mid and keeps the strongest.

Covers:
- a right-channel-inverted same-source copy is near-zero on mid-mid but rescued
  to ~1.0 via the cross term;
- a left-channel-inverted copy is rescued too (abs() handles the sign);
- an independent source is NOT rescued (no false merge);
- a clean (un-inverted) copy still scores high on mid-mid directly.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import match  # noqa: E402

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


def _mid_side(left, right):
    return (left + right).astype(np.float32), (left - right).astype(np.float32)


def _stereo_source(seed, n=SR * 30):
    """Independent left/right channels — a real stereo capture has decorrelated
    channels (different mic positions / room reflections)."""
    return _band_limited(n, seed), _band_limited(n, seed + 1000)


def test_right_channel_inverted_is_rescued():
    left, right = _stereo_source(seed=1)
    ref_mid, ref_side = _mid_side(left, right)
    # Same source, right channel polarity-flipped.
    cp_mid, cp_side = _mid_side(left, -right)

    mid_mid = abs(match.residual_corr(ref_mid, cp_mid))
    best, pairing = match.polarity_aware_corr(ref_mid, ref_side, cp_mid, cp_side)

    assert mid_mid < 0.2, f"mid-mid should collapse, got {mid_mid:.3f}"
    assert best > 0.9, f"rescue should recover the match, got {best:.3f}"
    assert pairing == "mid-side"


def test_left_channel_inverted_is_rescued():
    left, right = _stereo_source(seed=2)
    ref_mid, ref_side = _mid_side(left, right)
    cp_mid, cp_side = _mid_side(-left, right)

    mid_mid = abs(match.residual_corr(ref_mid, cp_mid))
    best, _ = match.polarity_aware_corr(ref_mid, ref_side, cp_mid, cp_side)

    assert mid_mid < 0.2
    assert best > 0.9


def test_independent_source_is_not_rescued():
    l1, r1 = _stereo_source(seed=3)
    l2, r2 = _stereo_source(seed=99)  # unrelated recording
    ref_mid, ref_side = _mid_side(l1, r1)
    oth_mid, oth_side = _mid_side(l2, r2)

    best, _ = match.polarity_aware_corr(ref_mid, ref_side, oth_mid, oth_side)
    assert best < 0.2, f"unrelated sources must not merge, got {best:.3f}"


def test_clean_copy_scores_high_on_mid_mid():
    left, right = _stereo_source(seed=4)
    ref_mid, ref_side = _mid_side(left, right)
    cp_mid, cp_side = _mid_side(left, right)  # identical, no inversion

    best, pairing = match.polarity_aware_corr(ref_mid, ref_side, cp_mid, cp_side)
    assert best > 0.9
    assert pairing == "mid-mid"


# --- driver: polarity_rescue (per-anchor own-lag search, used by the matrix loop) ---

def test_rescue_recovers_inverted_pair_with_own_lag():
    """A right-inverted copy decorrelates on mid-mid (so the caller's base_med is
    near-zero and local_lag can't lock there); polarity_rescue must still recover
    it via the mid-side cross term, which does its own lag search."""
    left, right = _stereo_source(seed=7, n=SR * 120)
    ref_mid, ref_side = _mid_side(left, right)
    cp_mid, cp_side = _mid_side(left, -right)  # right channel inverted
    anchors = [20.0, 50.0, 90.0]

    base_med = abs(match.residual_corr(ref_mid, cp_mid))  # caller's mid-mid score
    best, pairing = match.polarity_rescue(
        ref_mid, ref_side, cp_mid, cp_side, SR, anchors,
        win=45.0, max_lag=90.0, base_med=base_med)

    assert base_med < 0.2
    assert best > 0.9
    # Single-channel inversion makes BOTH cross terms match by symmetry
    # (ref_side == oth_mid up to scale, ref_mid == oth_side up to scale), so
    # either cross pairing is a valid recovery.
    assert pairing in ("mid-side", "side-mid")


def test_rescue_does_not_merge_independent_sources():
    l1, r1 = _stereo_source(seed=8, n=SR * 120)
    l2, r2 = _stereo_source(seed=808, n=SR * 120)
    ref_mid, ref_side = _mid_side(l1, r1)
    oth_mid, oth_side = _mid_side(l2, r2)
    anchors = [20.0, 50.0, 90.0]

    base_med = abs(match.residual_corr(ref_mid, oth_mid))
    best, _ = match.polarity_rescue(
        ref_mid, ref_side, oth_mid, oth_side, SR, anchors,
        win=45.0, max_lag=90.0, base_med=base_med)

    # No correlated cross term exists, so the score stays far below any cluster
    # threshold (~0.45) regardless of which pairing nominally "wins".
    assert best < 0.2, f"unrelated sources must not be rescued, got {best:.3f}"
