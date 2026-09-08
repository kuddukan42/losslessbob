"""Tests for backend.wtrf_board — the board walk that feeds the WTRF seeder.

The listing parser is pure and covered against markup shaped like SMF's; the
crawl is driven with a stub session so a test run never touches the real forum.
"""
import pytest

from backend.forum_poster import FORUM_BASE
from backend.wtrf_board import (
    TOPICS_PER_PAGE,
    BoardTopic,
    board_page_count,
    board_page_url,
    iter_board_topics,
    parse_board_page,
)


def _row(topic_id: int, title: str, sticky: bool = False) -> str:
    """Return one board listing row, stickied or not."""
    bg = "stickybg" if sticky else "windowbg"
    icon = "normal_post_sticky.gif" if sticky else "normal_post.gif"
    return (
        f'<tr>'
        f'<td class="icon1 {bg}"><img src="/Themes/images/topic/{icon}"></td>'
        f'<td class="subject {bg}2">'
        f'<a href="{FORUM_BASE}/index.php?topic={topic_id}.0">{title}</a>'
        f'<a href="{FORUM_BASE}/index.php?topic={topic_id}.msg1#new">New</a>'
        f'</td></tr>'
    )


def _page(rows: str, board_id: int = 16, pages: int = 3) -> str:
    """Return a board page wrapping ``rows``, with a pagination strip."""
    nav = "".join(
        f'<a href="{FORUM_BASE}/index.php?board={board_id}.{n * TOPICS_PER_PAGE}">'
        f'{n + 1}</a>'
        for n in range(pages)
    )
    return f"<html><body><table>{rows}</table><div>{nav}</div></body></html>"


# ── page URLs ────────────────────────────────────────────────────────────────

def test_board_page_url_is_sorted_newest_first():
    url = board_page_url(16, 40)
    assert "board=16.40" in url
    assert "sort=first_post;desc=1" in url


# ── listing parsing ──────────────────────────────────────────────────────────

def test_parse_board_page_drops_stickies_and_dedupes():
    html = _page(
        _row(60173, "SEVEN DAYS RULE", sticky=True)
        + _row(61701, "Cleveland, OH 1998-02-14 [Travitz]")
        + _row(61700, "West Long Branch, NJ 1997-04-20")
    )
    topics = parse_board_page(html, offset=20)

    assert [t.topic_id for t in topics] == [61701, 61700]
    assert topics[0].url == f"{FORUM_BASE}/index.php?topic=61701.0"
    assert topics[0].title == "Cleveland, OH 1998-02-14 [Travitz]"
    assert all(t.offset == 20 for t in topics)


def test_parse_board_page_empty_when_past_the_end():
    assert parse_board_page(_page(""), offset=9999) == []


class _StubResponse:
    def __init__(self, text: str):
        self.text = text


class _StubSession:
    """Serves canned board pages and records what was asked for."""

    def __init__(self, pages: dict[int, str]):
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url, timeout=None):                # noqa: D102 - test stub
        self.requested.append(url)
        offset = int(url.split("board=16.")[1].split(";")[0].split("?")[0])
        return _StubResponse(self.pages.get(offset, _page("")))


def test_board_page_count_reads_the_pagination_strip():
    session = _StubSession({0: _page(_row(1, "x"), pages=5)})
    assert board_page_count(session, 16) == 5


def test_iter_board_topics_walks_pages_in_order(monkeypatch):
    monkeypatch.setattr("backend.wtrf_board.time.sleep", lambda _s: None)
    session = _StubSession({
        0: _page(_row(900, "newest") + _row(899, "next")),
        TOPICS_PER_PAGE: _page(_row(880, "older")),
    })

    topics = list(iter_board_topics(session, 16, 0, pages=2, delay=0.0))

    assert [t.topic_id for t in topics] == [900, 899, 880]
    assert [t.offset for t in topics] == [0, 0, TOPICS_PER_PAGE]


def test_iter_board_topics_stops_at_the_end_of_the_board(monkeypatch):
    monkeypatch.setattr("backend.wtrf_board.time.sleep", lambda _s: None)
    session = _StubSession({0: _page(_row(900, "only page"))})

    topics = list(iter_board_topics(session, 16, 0, pages=5, delay=0.0))

    assert [t.topic_id for t in topics] == [900]
    # The walk stopped as soon as a page came back empty, rather than fetching
    # all five requested pages.
    assert len(session.requested) == 2


def test_iter_board_topics_survives_a_dead_page(monkeypatch):
    monkeypatch.setattr("backend.wtrf_board.time.sleep", lambda _s: None)

    class _Broken(_StubSession):
        def get(self, url, timeout=None):
            import requests
            raise requests.RequestException("connection reset")

    assert list(iter_board_topics(_Broken({}), 16, 0, 2, 0.0)) == []


# ── the ownership gate ───────────────────────────────────────────────────────

def _stub_resolution(monkeypatch, info: dict):
    """Point seed_board's resolver at a canned result."""
    monkeypatch.setattr("backend.wtrf_board.resolve_link", lambda *a, **k: dict(info))


@pytest.fixture
def one_topic(monkeypatch):
    """A board with exactly one topic on it, and no sleeping."""
    monkeypatch.setattr("backend.wtrf_board.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "backend.wtrf_board.iter_board_topics",
        lambda *a, **k: iter([BoardTopic(
            topic_id=61701,
            url=f"{FORUM_BASE}/index.php?topic=61701.0",
            title="Cleveland, OH 1998-02-14",
            offset=0,
        )]),
    )
    monkeypatch.setattr("backend.wtrf_board.database.get_wtrf_attempted_topics",
                        lambda: {})
    monkeypatch.setattr("backend.wtrf_board.database.get_meta", lambda _k: "16")
    recorded: list[tuple] = []
    monkeypatch.setattr("backend.wtrf_board._record",
                        lambda *a, **k: recorded.append(a) or 1)
    return recorded


def _run(tmp_path, **kwargs):
    from backend.tracker_seed import SeedOptions
    from backend.wtrf_board import seed_board
    return list(seed_board(
        opts=SeedOptions(tracker="wtrf"), dest_dir=tmp_path,
        session=object(), **kwargs,
    ))


def test_seed_board_skips_a_recording_not_in_the_collection(one_topic, monkeypatch,
                                                            tmp_path):
    _stub_resolution(monkeypatch, {
        "lb_number": 4154, "lb_candidates": [4154], "lb_source": "attachment",
        "confidence": "definitive", "needs_content_check": False,
        "torrent_url": "http://x/t.torrent", "title": "Cleveland", "error": "",
    })
    monkeypatch.setattr("backend.wtrf_board._owned_candidates", lambda _c: [])

    events = _run(tmp_path)
    topic = next(e for e in events if e["event"] == "topic")

    assert topic["status"] == "skipped"
    assert "not in the collection" in topic["reason"]
    # Recorded, so the next run does not fetch the post again.
    assert one_topic and one_topic[0][3] == "not_seeded"


def test_seed_board_reports_an_unresolved_post(one_topic, monkeypatch, tmp_path):
    _stub_resolution(monkeypatch, {
        "lb_number": None, "lb_candidates": [], "lb_source": "",
        "confidence": "not_found", "needs_content_check": False,
        "torrent_url": None, "title": "Chat thread",
        "error": "no LB number in the post's title, body or attachment",
    })

    topic = next(e for e in _run(tmp_path) if e["event"] == "topic")

    assert topic["status"] == "skipped"
    assert "no LB number" in topic["reason"]


def test_seed_board_dry_run_downloads_nothing(one_topic, monkeypatch, tmp_path):
    _stub_resolution(monkeypatch, {
        "lb_number": 4154, "lb_candidates": [4154], "lb_source": "attachment",
        "confidence": "definitive", "needs_content_check": False,
        "torrent_url": "http://x/t.torrent", "title": "Cleveland", "error": "",
    })
    monkeypatch.setattr("backend.wtrf_board._owned_candidates", lambda c: list(c))

    def _boom(*_a, **_k):
        raise AssertionError("a dry run must not download")

    monkeypatch.setattr("backend.wtrf_board._prepare_from_link", _boom)

    events = _run(tmp_path, dry_run=True)
    topic = next(e for e in events if e["event"] == "topic")

    assert topic["status"] == "resolved"
    assert "would seed from" in topic["reason"]
    assert not one_topic          # a dry run records nothing


def test_seed_board_drops_candidates_the_collection_lacks(one_topic, monkeypatch,
                                                          tmp_path):
    """A post naming two LBs is decided when only one of them is held."""
    _stub_resolution(monkeypatch, {
        "lb_number": 14777, "lb_candidates": [14777, 14778],
        "lb_source": "attachment", "confidence": "ambiguous",
        "needs_content_check": True, "torrent_url": "http://x/t.torrent",
        "title": "84 Revisited", "error": "",
    })
    monkeypatch.setattr("backend.wtrf_board._owned_candidates", lambda _c: [14778])

    topic = next(e for e in _run(tmp_path, dry_run=True) if e["event"] == "topic")

    assert topic["lb_number"] == 14778
    # One survivor means no content check is needed to settle the post.
    assert topic["reason"].startswith("would seed from")


def test_seed_board_skips_topics_already_attempted(one_topic, monkeypatch, tmp_path):
    url = f"{FORUM_BASE}/index.php?topic=61701.0"
    monkeypatch.setattr("backend.wtrf_board.database.get_wtrf_attempted_topics",
                        lambda: {url: "qbt_added"})

    def _boom(*_a, **_k):
        raise AssertionError("a seen topic must not be fetched")

    monkeypatch.setattr("backend.wtrf_board.resolve_link", _boom)

    events = _run(tmp_path)
    topic = next(e for e in events if e["event"] == "topic")
    done = events[-1]

    assert topic["status"] == "seen"
    assert "qbt_added" in topic["reason"]
    assert done["attempted"] == 0 and done["skipped"] == 1


def test_seed_board_rescan_ignores_the_attempt_log(one_topic, monkeypatch, tmp_path):
    url = f"{FORUM_BASE}/index.php?topic=61701.0"
    monkeypatch.setattr("backend.wtrf_board.database.get_wtrf_attempted_topics",
                        lambda: {url: "qbt_added"})
    _stub_resolution(monkeypatch, {
        "lb_number": 4154, "lb_candidates": [4154], "lb_source": "attachment",
        "confidence": "definitive", "needs_content_check": False,
        "torrent_url": "http://x/t.torrent", "title": "Cleveland", "error": "",
    })
    monkeypatch.setattr("backend.wtrf_board._owned_candidates", lambda c: list(c))

    topic = next(e for e in _run(tmp_path, dry_run=True, rescan=True)
                 if e["event"] == "topic")

    assert topic["status"] == "resolved"


def test_seed_board_limit_counts_attempts_only(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.wtrf_board.time.sleep", lambda _s: None)
    monkeypatch.setattr("backend.wtrf_board.database.get_meta", lambda _k: "16")
    monkeypatch.setattr("backend.wtrf_board.database.get_wtrf_attempted_topics",
                        lambda: {})
    monkeypatch.setattr("backend.wtrf_board._record", lambda *a, **k: 1)
    monkeypatch.setattr(
        "backend.wtrf_board.iter_board_topics",
        lambda *a, **k: iter([
            BoardTopic(n, f"{FORUM_BASE}/index.php?topic={n}.0", f"t{n}", 0)
            for n in (900, 899, 898)
        ]),
    )
    _stub_resolution(monkeypatch, {
        "lb_number": None, "lb_candidates": [], "lb_source": "",
        "confidence": "not_found", "needs_content_check": False,
        "torrent_url": None, "title": "", "error": "no LB number",
    })

    events = _run(tmp_path, limit=2)
    topics = [e for e in events if e["event"] == "topic"]

    assert len(topics) == 2
    assert events[-1]["attempted"] == 2
