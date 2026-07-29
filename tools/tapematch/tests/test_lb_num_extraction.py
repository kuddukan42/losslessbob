"""Regression for BUG-277: an embedded cross-referenced LB tag in a folder

name must not shadow the folder's own (trailing) LB number.

tapematch.ingest.extract_own_lb_number() strips bracketed `[...]` segments
(cross-reference annotations) and then takes the LAST remaining LB-NNNNN
match, since the folder's own tag is conventionally trailing. This replaces
the old "first LB-\\d+ match wins" regex in both tapematch/cli.py's _lb_num()
and tapematch_session.py's _lb_num_from_folder() regex fallback.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402
from tapematch.ingest import extract_own_lb_number  # noqa: E402


def test_docstring_example() -> None:
    # The bug report's own example: an embedded "fixed LB-2204" cross-reference
    # ahead of the folder's own trailing LB-10437 tag.
    name = "1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v"
    assert extract_own_lb_number(name) == 10437


def test_no_lb_tag_returns_none() -> None:
    assert extract_own_lb_number("random_folder_no_tag") is None


def test_single_tag_no_bracket() -> None:
    assert extract_own_lb_number("1988-06-07 Concord Pavilion, Concord, CA (LB-02564)") == 2564


@pytest.mark.parametrize(
    "folder_a,folder_b,expected_a,expected_b",
    [
        # 1989-07-16 -- the bug report's own collision.
        ("1989-07-16 Bristol (LB-02204)",
         "1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v",
         2204, 10437),
        # 1988-06-07
        ("1988-06-07 Concord (drop-outs patched) best copy (xref LB-2564)-LB-14661",
         "1988-06-07 Concord Pavilion, Concord, CA (LB-02564)",
         14661, 2564),
        # 1988-06-25
        ("1988-06-25 Holmdel 25 June 1988 LTE xref-LB-6295 Upgrade-LB-14665",
         "1988-06-25 Holmdel, New Jersey (LB-06295)",
         14665, 6295),
        # 1988-07-20
        ("1988-07-20  Columbia Merriweather 20 July 1988 (best xref-LB-1475)-LB-14672",
         "1988-07-20 Marjorie Merriweather Post Pavilion, Columbia, Maryland (LB-01475)",
         14672, 1475),
        # 1988-09-11
        ("1988-09-11 Fairfax (LB-02585)",
         "1988-09-11 Fairfax (LB-2585 Fixed) LB-10934-v",
         2585, 10934),
        # 1988-09-23
        ("1988-09-23 MAMI ARENA, MIAMI, FLORIDA (LB-03164)",
         "1988-09-23 Miami, Florida (xref LB-3164) Upgrade-LB-14683",
         3164, 14683),
    ],
)
def test_known_collision_folders_now_resolve_distinctly(
    folder_a: str, folder_b: str, expected_a: int, expected_b: int
) -> None:
    """6 of the 7 live BUG-277 collisions resolve to distinct LB numbers now."""
    got_a = extract_own_lb_number(folder_a)
    got_b = extract_own_lb_number(folder_b)
    assert (got_a, got_b) == (expected_a, expected_b)
    assert got_a != got_b


def test_1993_06_19_collision_is_not_regex_resolvable() -> None:
    """1993-06-19 (LB-1929/LB-2072) is the one collision the folder-name

    regex alone cannot disambiguate -- both LB numbers appear unbracketed
    (one embedded mid-name, the other trailing-but-bracketed), so this case
    genuinely needs the session's DB-resolved name_to_lb map, not a filename
    heuristic. Documented here so a future "smarter" filename regex doesn't
    silently regress on the 6 cases above while chasing this one.
    """
    folder_a = "1993-06-19 Beersheva, Israel (LB-01929)"
    folder_b = "1993-06-19-LB-1929.flacf [LB-02072]-v"
    assert extract_own_lb_number(folder_a) == 1929
    # Known ambiguous case: regex-only resolution collides here.
    assert extract_own_lb_number(folder_b) == 1929


def test_assert_no_self_pair_raises_on_collision() -> None:
    with pytest.raises(AssertionError, match="BUG-277 guard"):
        sess._assert_no_self_pair(1929, 1929, "folder_a", "folder_b", "run123", "1993-06-19")


def test_assert_no_self_pair_allows_distinct() -> None:
    sess._assert_no_self_pair(1929, 2072, "folder_a", "folder_b", "run123", "1993-06-19")


def test_assert_no_self_pair_allows_unresolved() -> None:
    # Neither side resolved -- nothing to compare, must not raise.
    sess._assert_no_self_pair(None, None, "folder_a", "folder_b", "run123", "1993-06-19")


def test_lb_num_from_folder_prefers_db_map_over_regex() -> None:
    name = "1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v"
    name_to_lb = {name: 10437}
    assert sess._lb_num_from_folder(name, name_to_lb) == 10437


def test_lb_num_from_folder_falls_back_to_regex_when_no_db_map() -> None:
    name = "1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v"
    assert sess._lb_num_from_folder(name, None) == 10437


def test_lb_num_from_folder_logs_on_db_map_miss(caplog) -> None:
    name = "some_unmapped_folder LB-999"
    name_to_lb: dict[str, int] = {"a_different_folder": 1}
    with caplog.at_level("WARNING"):
        result = sess._lb_num_from_folder(name, name_to_lb)
    assert result == 999
    assert any("falling back to folder-name regex" in r.message for r in caplog.records)
