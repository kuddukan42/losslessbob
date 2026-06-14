"""Tests for gen_analysis.py's commentary cross-reference parser.

Covers the fix for the _same_signal false-positive on snippets where
"same recording" describes a *different* group of LBs than the subject,
e.g.:

    "Alternative recording to LB-0491/LB-0569 which all appear to be
    same recording"

Such a snippet matches both _DIFF_PATS ("alternative recording to") and
_SAME_PATS ("same recording"). The fix: if _diff_signal(snip) matches,
do not treat the snippet as a same-source signal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gen_analysis  # noqa: E402

LB_A = "LB-10594"
LB_B = "LB-0491"

# Real snippet from data/tapematch/runs/20260603_085731_2001-10-30/report.md —
# "same recording" here refers to the LB-0491/LB-0569/.../LB-8413 group's
# relationship to *each other*, not to LB-10594.
AMBIGUOUS_TEXT = (
    'version "e", Alternative recording to LB-0491/LB-0569/LB-4885/LB-7888 '
    "which all appear to be same recording & LB-8413., "
    "Trade cd-r's > eac > flac 5 > dime"
)

# Clean same-source signal: subject explicitly says it is the same recording
# as the other LB, with no diff signal in the snippet.
SAME_TEXT = "4 (64-bit), same recording as LB-0491"

# Clean different-source signal: "alternative recording to" with no
# "same recording" anywhere in the snippet.
DIFF_TEXT = (
    'version "c"; audience recording, alternative recording to LB-0491 '
    "& LB-4793 - excellent sound"
)


def _make_case(commentary_text: str, fa: int, fb: int):
    r = {
        "sources": [{"lb": LB_A}, {"lb": LB_B}],
        "family_map": {LB_A: fa, LB_B: fb},
        "secondary_pairs": [],
        "diagnostics": [],
    }
    rows = [
        {"lb": LB_A, "on_disk": True, "commentary": commentary_text,
         "speed_ppm": 0, "speed_kind": "aligned", "incomplete": False},
        {"lb": LB_B, "on_disk": True, "commentary": "",
         "speed_ppm": 0, "speed_kind": "aligned", "incomplete": False},
    ]
    return r, rows


# ── snippet-level signal checks ─────────────────────────────────────────────

def test_ambiguous_snippet_matches_both_signal_patterns():
    snip = gen_analysis._get_snippet(AMBIGUOUS_TEXT, LB_B)
    assert gen_analysis._diff_signal(snip)
    assert gen_analysis._same_signal(snip)


def test_same_snippet_matches_only_same_signal():
    snip = gen_analysis._get_snippet(SAME_TEXT, LB_B)
    assert gen_analysis._same_signal(snip)
    assert not gen_analysis._diff_signal(snip)


def test_diff_snippet_matches_only_diff_signal():
    snip = gen_analysis._get_snippet(DIFF_TEXT, LB_B)
    assert gen_analysis._diff_signal(snip)
    assert not gen_analysis._same_signal(snip)


# ── _build_observations: ambiguous "alternative ... same recording" ────────

def test_ambiguous_snippet_different_families_is_not_a_miss():
    r, rows = _make_case(AMBIGUOUS_TEXT, fa=1, fb=2)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "MISS" not in text
    assert f"{LB_A} → {LB_B}" in text


def test_ambiguous_snippet_same_family_is_false_merge():
    r, rows = _make_case(AMBIGUOUS_TEXT, fa=1, fb=1)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "FALSE MERGE" in text
    assert "same-source confirmed" not in text


# ── _build_observations: regression — clean signals still classified ───────

def test_clean_same_signal_different_families_is_miss():
    r, rows = _make_case(SAME_TEXT, fa=1, fb=2)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "MISS" in text


def test_clean_same_signal_same_family_is_confirmed():
    r, rows = _make_case(SAME_TEXT, fa=1, fb=1)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "same-source confirmed" in text


def test_clean_diff_signal_same_family_is_false_merge():
    r, rows = _make_case(DIFF_TEXT, fa=1, fb=1)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "FALSE MERGE" in text


def test_clean_diff_signal_different_families_is_neutral():
    r, rows = _make_case(DIFF_TEXT, fa=1, fb=2)
    obs = gen_analysis._build_observations(r, rows)
    text = "\n".join(obs)
    assert "MISS" not in text
    assert "FALSE MERGE" not in text
    assert f"{LB_A} → {LB_B}" in text
