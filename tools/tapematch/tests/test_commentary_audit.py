"""Tests for the commentary-audit clause scoping fix (TODO-322).

The commentary audit in tapematch_session.py's `_build_commentary_audit`
raises AGREES/DISAGREES by keyword-matching an LB info-file's prose (via
`extract_lb_relationship` / `_relationship_from_text`) against the tapematch
family assignment. Confirmed false positives from the 2026-08-21 batch:

  - 1984-06-04: LB-03917's own text reads "alternate recording to LB-0680 &
    LB-1785 ...; this is a sort of close eac match to sm LB-3914 ..." -- a
    +/-250-char window around the "LB-0680" mention used to pick up the
    unrelated "close eac match to sm LB-3914" clause and wrongly report
    LB-03917 as claiming to be the SAME recording as LB-0680.
  - 1995-03-31: LB-10825's own text reads "... this has very similar wav and
    spectral view and levels to LB-1884 ; this has more digital flaws; for
    the 3/29 portion of this in 5-way comparison this is a different
    recording based on different crowd ..." -- the window around "LB-1884"
    used to pick up the unrelated "different recording" clause, which is
    actually about a bonus/filler portion, not the LB-1884 comparison.

Both are reproduced here with inline sample prose (not the real HTML pages)
so the fix is verified against `_relationship_from_text` directly, plus one
genuine true-positive case (LB-03917 explicitly claiming a "close eac match"
to LB-03914) that must keep firing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def test_cross_clause_same_keyword_does_not_leak_to_unrelated_lb() -> None:
    """1984-06-04 false positive: LB-03917 text, checked against LB-0680.

    The clause naming LB-0680 says "alternate recording to" (no same/
    different keyword match at all); the "close eac match" a few clauses
    later is about LB-3914, not LB-0680, and must not bleed in.
    """
    text = (
        'version "a"; alternate recording to LB-0680 & LB-1785, from 1st gen '
        "tapes, except for tape flip breaks, seamless.; this is a sort of "
        "close eac match to sm LB-3914 but tracked differently and not TAO; "
        "very good sound"
    )
    same, _ = sess._relationship_from_text(text, 680)
    assert same is None


def test_cross_clause_diff_keyword_does_not_leak_to_unrelated_lb() -> None:
    """1995-03-31 false positive: LB-10825 text, checked against LB-1884.

    The clause naming LB-1884 says "very similar wav and spectral view"
    (no same/different keyword match); the "different recording" clause a
    few clauses later is about the 3/29 bonus-filler portion, not LB-1884.
    """
    text = (
        "d2t6-d210 filler is from 3/29 and companion to 3/30 which together "
        "are missing several songs from 3/29 this has very similar wav and "
        "spectral view and levels to LB-1884 ; this has more digital flaws; "
        "for the 3/29 portion of this in 5-way comparison this is a "
        "different recording based on different crowd at end of she "
        "belongs to me"
    )
    same, _ = sess._relationship_from_text(text, 1884)
    assert same is None


def test_same_clause_eac_match_still_fires() -> None:
    """True positive: LB-03917's own clause claims a close eac match to

    LB-03914 -- the keyword and the LB reference are in the same clause, so
    this must still be flagged.
    """
    text = (
        'version "a"; alternate recording to LB-0680 & LB-1785; this is a '
        "sort of close eac match to sm LB-3914 but tracked differently and "
        "not TAO; very good sound"
    )
    same, ctx = sess._relationship_from_text(text, 3914)
    assert same == 1
    assert "LB-3914" in ctx


def test_same_clause_different_recording_still_fires() -> None:
    """True negative: a clause that both names the target LB and says

    "different recording" (with a lineage term in scope) must still resolve
    to says_same=0.
    """
    text = (
        "same recording as fendert LB-1785 based on same clapping wavs; "
        "different recording than JvV LB-7416 and LB-3914 based on "
        "different crowd at end of d2t10"
    )
    same, _ = sess._relationship_from_text(text, 3914)
    assert same == 0


def test_no_mention_returns_none() -> None:
    same, ctx = sess._relationship_from_text("nothing relevant here at all", 12345)
    assert same is None
    assert ctx == ""


def test_boilerplate_header_repeat_without_lineage_term_does_not_fire() -> None:
    """A bare page-header repeat naming the LB with no lineage vocabulary in

    its clause must not trigger a same/different verdict even if a same/
    different keyword happens to appear far away in a later clause.
    """
    text = (
        "LosslessBob LB-5503 LosslessBob LB-5503 Date Location CDR Rating "
        "Timing 9/26/87 Stockholm, Sweden.; unrelated later note says this "
        "is a different recording of something else entirely"
    )
    same, _ = sess._relationship_from_text(text, 5503)
    assert same is None
