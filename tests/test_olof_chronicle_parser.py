"""Tests for backend/olof_chronicle_parser.py's calendar date-heading detection.

Golden-dossier review: cross-month range headings ('11 April - 17 May') and
bare season headings ('Summer') were not recognized as headings at all, so
their text glued onto the *previous* date's entry_text instead of opening a
new olof_chronicle row (confirmed live: olof_chronicle 1983-02-16 entry_text
ends '...\\n11 April - 17 May\\nThe Infidels recording sessions ...').
"""
import pytest

from backend.olof_chronicle_parser import _parse_date_heading


@pytest.mark.parametrize("heading,want_date", [
    ("11 April – 17 May", "1983-04-11"),
    ("24 April - 6 May", "1983-04-24"),
    ("29 July – 4 August", "1983-07-29"),
    ("28 June - 1 July", "1983-06-28"),
])
def test_cross_month_range_heading_resolves_to_first_day(heading, want_date):
    result = _parse_date_heading(heading, 1983)
    assert result is not None
    date_str, date_raw = result
    assert date_str == want_date
    assert date_raw == heading


@pytest.mark.parametrize("heading", [
    "Spring", "Summer", "Autumn", "Fall", "Winter",
    "Early Summer", "Late Autumn", "early winter",
])
def test_bare_season_heading_is_recognized_with_no_date(heading):
    result = _parse_date_heading(heading, 1983)
    assert result is not None
    date_str, date_raw = result
    assert date_str == ""
    assert date_raw == heading


def test_ordinary_prose_is_still_not_a_heading():
    assert _parse_date_heading("The Infidels recording sessions continued.", 1983) is None
    # A season word inside a longer sentence must not false-positive.
    assert _parse_date_heading("Summer was a busy time for Bob.", 1983) is None


def test_same_month_range_and_plain_day_still_work():
    assert _parse_date_heading("19 -24 February", 1983) == ("1983-02-19", "19 -24 February")
    assert _parse_date_heading("31 January", 1983) == ("1983-01-31", "31 January")
    assert _parse_date_heading("January", 1983) == ("", "January")
