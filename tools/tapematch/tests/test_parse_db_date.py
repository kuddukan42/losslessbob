"""Regression for BUG-280: entries.date_str parsing must not run 1961-1968

Dylan material into 2061-2068.

datetime.strptime(date_str, "%m/%d/%y") follows the POSIX pivot (00-68 ->
2000-2068, 69-99 -> 1969-1999), so plain strptime sends 1961-1968 dates into
the future. parse_db_date() re-anchors any parse landing after "now" back to
the prior century (this repo's corpus never has entries in the future).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def test_1961_stays_1961() -> None:
    d = sess.parse_db_date("1/1/61")
    assert (d.year, d.month, d.day) == (1961, 1, 1)


def test_1968_boundary_stays_1968() -> None:
    d = sess.parse_db_date("12/31/68")
    assert (d.year, d.month, d.day) == (1968, 12, 31)


def test_town_hall_1963_stays_1963() -> None:
    d = sess.parse_db_date("4/12/63")
    assert (d.year, d.month, d.day) == (1963, 4, 12)


def test_1969_still_parses_correctly() -> None:
    # 69-99 was already correct under the POSIX pivot -- must not regress.
    d = sess.parse_db_date("8/31/69")
    assert (d.year, d.month, d.day) == (1969, 8, 31)


def test_1995_unaffected() -> None:
    d = sess.parse_db_date("7/8/95")
    assert (d.year, d.month, d.day) == (1995, 7, 8)


def test_recent_2000s_date_unaffected() -> None:
    d = sess.parse_db_date("1/1/10")
    assert (d.year, d.month, d.day) == (2010, 1, 1)


def test_invalid_date_raises_value_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        sess.parse_db_date("not-a-date")
