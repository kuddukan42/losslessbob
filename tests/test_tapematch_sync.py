"""Tests for backend/tapematch_sync.py's analysis.md verdict parsing.

Covers the regex-based ``_parse_verdict`` helper that extracts the
tapematch-batch skill's "needs review" flag + reason from each run's
analysis.md, since it's the one piece of free-text parsing this module does.
"""

from backend.tapematch_sync import _parse_verdict


def test_parse_verdict_clean_looks_correct():
    text = "## Verdict: 3 recordings — 2 families — result looks correct\n"
    assert _parse_verdict(text) == (False, None)


def test_parse_verdict_clean_all_confirmed_different():
    text = "## Verdict: 2 recordings — 2 families — all sources confirmed different\n"
    assert _parse_verdict(text) == (False, None)


def test_parse_verdict_needs_review_with_reason():
    text = (
        "## Verdict: 2 recordings — 2 families — result needs review — "
        "LB-04776's claimed same-source identity with LB-04053 is contradicted "
        "by near-zero correlation\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == (
        "LB-04776's claimed same-source identity with LB-04053 is contradicted "
        "by near-zero correlation"
    )


def test_parse_verdict_needs_review_reason_contains_em_dash():
    # The reason clause can itself contain "—"-joined sub-clauses; the parser
    # must rejoin everything after "needs review" rather than truncating at
    # the first dash.
    text = (
        "## Verdict: 7 recordings — 7 families — result needs review — "
        "LB-10613's claimed identity with LB-807/LB-1940 is contradicted — "
        "and LB-4210's claim is also unresolved\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == (
        "LB-10613's claimed identity with LB-807/LB-1940 is contradicted — "
        "and LB-4210's claim is also unresolved"
    )


def test_parse_verdict_needs_review_no_reason():
    text = "## Verdict: 3 recordings — 3 families — result needs review\n"
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason is None


def test_parse_verdict_no_verdict_line():
    assert _parse_verdict("# Analysis — 1991-01-01 — Nowhere\n\nNo verdict here.\n") == (False, None)


def test_parse_verdict_finds_line_anywhere_in_document():
    text = (
        "# Analysis — 1991-01-01 — Nowhere\n"
        "*Claude claude-sonnet-4-6 — 2026-06-22*\n\n"
        "## Verdict: 4 recordings — 4 families — result needs review — reason text\n\n"
        "| LB | Rating |\n|----|----|\n"
    )
    flagged, reason = _parse_verdict(text)
    assert flagged is True
    assert reason == "reason text"
