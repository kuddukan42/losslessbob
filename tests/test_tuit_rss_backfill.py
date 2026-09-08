"""Tests for the /browse backfill that covers a rolled RSS window.

The feed is a rolling window of the newest ``RSS_WINDOW`` uploads. These tests
pin the trigger condition (a full window with no overlap) and the paging that
recovers the uploads the window dropped.
"""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import tuit_scraper  # noqa: E402
from tools import tuit_sync  # noqa: E402


def _args(**overrides) -> argparse.Namespace:
    """Return CLI args with the fields the backfill helpers read."""
    base = {"rss_backfill_pages": 10, "rescan": False, "delay": 0.0}
    base.update(overrides)
    return argparse.Namespace(**base)


def _items(count: int) -> list:
    """Return ``count`` stand-in feed items."""
    return [SimpleNamespace(rec_id=i) for i in range(1, count + 1)]


def _row(rec_id: int) -> SimpleNamespace:
    """Return a stand-in browse row."""
    return SimpleNamespace(rec_id=rec_id)


# ── trigger condition ────────────────────────────────────────────────────────

def test_full_window_without_overlap_triggers_backfill():
    known = {900, 901}
    assert tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW), 0, known, _args()
    )


def test_any_overlap_means_nothing_rolled_off():
    known = {900}
    assert not tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW), 1, known, _args()
    )


def test_partial_window_does_not_trigger():
    known = {900}
    assert not tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW - 1), 0, known, _args()
    )


def test_first_run_with_empty_db_does_not_trigger():
    assert not tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW), 0, set(), _args()
    )


def test_rescan_does_not_trigger():
    assert not tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW), 0, {900}, _args(rescan=True)
    )


def test_zero_pages_disables_backfill():
    assert not tuit_sync._rss_window_may_have_rolled(
        _items(tuit_scraper.RSS_WINDOW), 0, {900}, _args(rss_backfill_pages=0)
    )


# ── paging ───────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_browse(monkeypatch):
    """Serve canned /browse pages and record which pages were fetched."""
    fetched: list[int] = []
    pages: dict[int, list] = {}

    def _fetch(session, page=1, delay=0.0):
        fetched.append(page)
        return pages.get(page, []), None, ""

    monkeypatch.setattr(tuit_scraper, "fetch_browse_page", _fetch)
    return SimpleNamespace(pages=pages, fetched=fetched)


def test_backfill_stops_at_the_first_known_recording(fake_browse):
    fake_browse.pages[1] = [_row(60), _row(59)]
    fake_browse.pages[2] = [_row(58), _row(500)]   # 500 is known → overlap
    fake_browse.pages[3] = [_row(57)]              # must never be fetched
    rows_by_id: dict = {}
    queue: list = []

    skipped = tuit_sync._rss_backfill(
        object(), _args(), {500}, rows_by_id, queue
    )

    assert queue == [60, 59, 58]
    assert skipped == 1
    assert fake_browse.fetched == [1, 2]


def test_backfill_respects_the_page_cap(fake_browse):
    for page in range(1, 6):
        fake_browse.pages[page] = [_row(100 + page)]
    rows_by_id: dict = {}
    queue: list = []

    tuit_sync._rss_backfill(
        object(), _args(rss_backfill_pages=3), {500}, rows_by_id, queue
    )

    assert fake_browse.fetched == [1, 2, 3]
    assert queue == [101, 102, 103]


def test_backfill_does_not_requeue_ids_the_feed_already_supplied(fake_browse):
    fake_browse.pages[1] = [_row(60), _row(59)]
    fake_browse.pages[2] = [_row(500)]
    rows_by_id: dict = {60: None}      # 60 came from the feed
    queue: list = [60]

    tuit_sync._rss_backfill(object(), _args(), {500}, rows_by_id, queue)

    assert queue == [60, 59]
    assert rows_by_id[60] is None      # feed entry not clobbered by a row


def test_backfill_stops_on_an_empty_page(fake_browse):
    fake_browse.pages[1] = [_row(60)]
    queue: list = []

    tuit_sync._rss_backfill(object(), _args(), {500}, {}, queue)

    assert fake_browse.fetched == [1, 2]
    assert queue == [60]
