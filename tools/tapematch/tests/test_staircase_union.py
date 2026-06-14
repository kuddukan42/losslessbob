"""Tests for align.union_staircase_sources (CC_TAPEMATCH_FIXES.md Task 5).

Covers the reference-ambiguity fix: a source's lag-curve "kind" is always
"reference" relative to itself, so a single speed_info pass can never flag
the current reference source as staircase. union_staircase_sources takes the
union across both lag-curve passes (vs the initial ref, and vs the
re-selected central ref) so each source's staircase status is picked up from
whichever pass it isn't the reference in.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import align  # noqa: E402


def test_union_resolves_reference_ambiguity():
    # 2001-10-30 case: LB-08413 is "reference" in pass 1 (vs initial ref) but
    # "staircase/splice" in pass 2 (vs central ref LB-00569). LB-07888 is
    # "staircase/splice" in pass 1 but "aligned" in pass 2.
    speed_info = {
        "LB-08413": {"kind": "reference", "ppm": 0.0, "ratio": 1.0},
        "LB-07888": {"kind": "staircase/splice", "ppm": 0.0, "ratio": 1.0},
        "LB-10594": {"kind": "constant-speed-offset", "ppm": -500.0, "ratio": 0.9995},
    }
    speed_info_central = {
        "LB-00569": {"kind": "reference", "ppm": 0.0, "ratio": 1.0},
        "LB-08413": {"kind": "staircase/splice", "ppm": 0.0, "ratio": 1.0},
        "LB-07888": {"kind": "aligned", "ppm": 0.0, "ratio": 1.0},
    }

    result = align.union_staircase_sources(speed_info, speed_info_central)

    assert result == {"LB-08413", "LB-07888"}


def test_union_with_empty_second_pass():
    # central_name == ref_name -> speed_info_central is {} (no second pass run).
    speed_info = {
        "A": {"kind": "reference", "ppm": 0.0, "ratio": 1.0},
        "B": {"kind": "staircase/splice", "ppm": 0.0, "ratio": 1.0},
        "C": {"kind": "aligned", "ppm": 0.0, "ratio": 1.0},
    }
    assert align.union_staircase_sources(speed_info, {}) == {"B"}


def test_union_no_staircase_sources():
    speed_info = {"A": {"kind": "reference"}, "B": {"kind": "aligned"}}
    speed_info_central = {"B": {"kind": "reference"}, "A": {"kind": "aligned"}}
    assert align.union_staircase_sources(speed_info, speed_info_central) == set()
