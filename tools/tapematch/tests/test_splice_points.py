"""Tests for align.locate_splice_points (TODO-144).

locate_splice_points reuses the `steps = np.abs(np.diff(y))` computation that
interpret_curve already performs but previously discarded.  It returns the
midpoint time between the two flanking anchors for each step that exceeds
step_flag_sec.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import align  # noqa: E402


def _rows(centers, lags):
    return [{"center_sec": c, "lag_sec": l, "peak": 1.0}
            for c, l in zip(centers, lags)]


def test_no_splices_when_curve_is_flat():
    rows = _rows([10, 20, 30, 40, 50], [0.1, 0.1, 0.1, 0.1, 0.1])
    assert align.locate_splice_points(rows, step_flag_sec=0.5) == []


def test_single_splice_detected():
    # step between anchor at 20s and 30s: lag jumps from 0.1 -> 2.0 (1.9s step)
    rows = _rows([10, 20, 30, 40], [0.1, 0.1, 2.0, 2.0])
    splices = align.locate_splice_points(rows, step_flag_sec=0.5)
    assert len(splices) == 1
    assert abs(splices[0] - 25.0) < 0.01  # midpoint of 20s and 30s


def test_two_splices_detected():
    rows = _rows([0, 10, 20, 30, 40], [0.0, 0.0, 1.5, 1.5, 3.0])
    splices = align.locate_splice_points(rows, step_flag_sec=0.5)
    assert len(splices) == 2
    assert abs(splices[0] - 15.0) < 0.01
    assert abs(splices[1] - 35.0) < 0.01


def test_none_lags_excluded():
    rows = [
        {"center_sec": 10.0, "lag_sec": 0.1, "peak": 1.0},
        {"center_sec": 20.0, "lag_sec": None, "peak": 0.0},  # invalid — skip
        {"center_sec": 30.0, "lag_sec": 2.0, "peak": 0.8},
        {"center_sec": 40.0, "lag_sec": 2.0, "peak": 0.8},
    ]
    splices = align.locate_splice_points(rows, step_flag_sec=0.5)
    # step is between the valid anchors at 10s and 30s (None skipped)
    assert len(splices) == 1
    assert abs(splices[0] - 20.0) < 0.01


def test_fewer_than_two_valid_returns_empty():
    rows = [{"center_sec": 10.0, "lag_sec": None, "peak": 0.0}]
    assert align.locate_splice_points(rows, step_flag_sec=0.5) == []
