"""Tests for BUG-330: the [DISTINCT SOURCE] diagnostic must not cite an
untrusted speed ratio.

When ``estimate_ratio_v2`` returns a confidence below
``align.ratio_confidence_min``, the matrix pass marks the pair speed-unknown,
forces the ratio to 1.0 and skips resampling. The stored ppm is therefore the
rejected estimate, and the correlations computed against it ran unresampled --
a same-source copy a few percent off speed cannot correlate under those
conditions. ``_speed_offset_trusted`` is the guard that keeps both numbers out
of a "entirely different recording" claim.

No audio and no tapematch session -- the helper is pure dict logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch.cli import _speed_offset_trusted  # noqa: E402

TRUSTED = {"kind": "constant-speed-offset", "ppm": 36200.0, "ratio_confidence": 11.4}
UNTRUSTED = {"kind": "speed-unknown", "ppm": 36200.0, "ratio_confidence": 2.4}
STAIRCASE = {"kind": "staircase/splice", "ppm": 120.0, "ratio_confidence": 1.1}


def test_trusted_offset_is_quotable():
    assert _speed_offset_trusted("LB-1", {"LB-1": TRUSTED}, {}) is True


def test_speed_unknown_in_initial_pass_withholds_the_claim():
    assert _speed_offset_trusted("LB-1", {"LB-1": UNTRUSTED}, {}) is False


def test_speed_unknown_in_central_pass_alone_withholds_the_claim():
    """The re-selected central reference is a second, independent opinion.

    Mirrors align.union_staircase_sources: either pass objecting is enough.
    """
    assert _speed_offset_trusted("LB-1", {"LB-1": TRUSTED}, {"LB-1": UNTRUSTED}) is False


def test_both_passes_trusted_is_quotable():
    assert _speed_offset_trusted("LB-1", {"LB-1": TRUSTED}, {"LB-1": TRUSTED}) is True


def test_staircase_keeps_its_offset_quotable():
    """Staircase classification comes from the lag-curve shape, not the ratio
    search, so its low ratio confidence must not be read as speed-unknown."""
    assert _speed_offset_trusted("LB-1", {"LB-1": STAIRCASE}, {}) is True


def test_missing_source_defaults_to_trusted():
    """A name absent from both dicts has no objection recorded against it."""
    assert _speed_offset_trusted("LB-9", {"LB-1": TRUSTED}, {}) is True
