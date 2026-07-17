"""Tests for align.fit_lag_segments (TODO-235).

fit_lag_segments turns an anchor lag curve into a piecewise-linear per-segment
model (offset + rate between splice points) so a staircase source's
perf->source time map can be persisted by the run instead of discarded.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import align  # noqa: E402


def _rows(centers, lags):
    return [{"center_sec": c, "lag_sec": l, "peak": 1.0}
            for c, l in zip(centers, lags)]


def test_flat_curve_yields_single_zero_rate_segment():
    rows = _rows([10, 20, 30, 40, 50], [0.1, 0.1, 0.1, 0.1, 0.1])
    segs = align.fit_lag_segments(rows, step_flag_sec=0.5)
    assert len(segs) == 1
    s = segs[0]
    assert s["t_start"] == 0.0
    assert s["t_end"] == 50.0
    assert s["offset_sec"] == pytest.approx(0.1)
    assert s["rate_ppm"] == pytest.approx(0.0, abs=1e-6)
    assert s["n_anchors"] == 5


def test_staircase_splits_at_step():
    # lag jumps 0.1 -> 2.0 between anchors at 200s and 300s
    rows = _rows([100, 200, 300, 400], [0.1, 0.1, 2.0, 2.0])
    segs = align.fit_lag_segments(rows, step_flag_sec=0.5)
    assert len(segs) == 2
    a, b = segs
    assert a["t_start"] == 0.0
    assert a["t_end"] == pytest.approx(250.0)   # midpoint, same as locate_splice_points
    assert b["t_start"] == pytest.approx(250.0)
    assert b["t_end"] == 400.0
    assert a["offset_sec"] == pytest.approx(0.1)
    assert b["offset_sec"] == pytest.approx(2.0)
    assert a["n_anchors"] == 2 and b["n_anchors"] == 2


def test_constant_slope_recovers_rate_ppm():
    # lag(t) = 0.5 + 1000ppm * t
    centers = [600, 1200, 1800, 2400, 3000]
    rows = _rows(centers, [0.5 + 1e-3 * c for c in centers])
    segs = align.fit_lag_segments(rows, step_flag_sec=10.0)
    assert len(segs) == 1
    assert segs[0]["rate_ppm"] == pytest.approx(1000.0, rel=1e-3)
    assert segs[0]["offset_sec"] == pytest.approx(0.5, abs=1e-6)
    assert segs[0]["r2"] == pytest.approx(1.0)


def test_single_anchor_segment_after_late_splice():
    # splice right before the last anchor -> 1-anchor tail segment
    rows = _rows([100, 200, 300], [0.0, 0.0, 5.0])
    segs = align.fit_lag_segments(rows, step_flag_sec=0.5)
    assert len(segs) == 2
    tail = segs[1]
    assert tail["n_anchors"] == 1
    assert tail["offset_sec"] == pytest.approx(5.0)
    assert tail["rate_ppm"] == 0.0
    assert tail["r2"] == 1.0


def test_none_lags_are_ignored():
    rows = _rows([10, 20, 30, 40], [0.1, None, 0.1, 0.1])
    segs = align.fit_lag_segments(rows, step_flag_sec=0.5)
    assert len(segs) == 1
    assert segs[0]["n_anchors"] == 3


def test_fewer_than_two_valid_anchors_returns_empty():
    assert align.fit_lag_segments(_rows([10], [0.1]), 0.5) == []
    assert align.fit_lag_segments(_rows([10, 20], [None, None]), 0.5) == []
    assert align.fit_lag_segments([], 0.5) == []
