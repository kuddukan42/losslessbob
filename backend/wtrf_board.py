"""Walk the WTRF board post by post and seed everything already held locally.

:mod:`backend.wtrf_seed` seeds a list of links the curator pasted; this module
supplies the list instead, by paging the board itself — newest topic first and
onward backwards in time, which is how a long-dead post from 2014 gets a seeder
again. It is the WTRF counterpart of ``tools/tuit_sync.py --fetch-torrents
--seed``: a resumable crawl over an upload listing, seeding what the collection
can already supply and recording every attempt so the next run starts where the
last one stopped.

The order of work per topic matters, because the expensive parts are the ones
worth skipping:

1. **Already attempted?** ``wtrf_downloads`` is keyed by ``topic_url``, so a
   topic seen by an earlier run is skipped without a request at all.
2. **Resolve** the post — one page fetch — to its LB number and ``.torrent``
   attachment (see :func:`backend.wtrf_seed.resolve_link`).
3. **Owned?** The purpose here is seeding, not collecting: a post whose
   recording is not in the collection is dropped *before* its torrent is
   downloaded. ``--include-missing`` turns that gate off for a caller who does
   want the fetch.
4. **Seed** through the shared gates — collection folder verified in place, or
   a ``<mount>/WTRF Seeds`` overlay assembled from hardlinks plus sidecars.

Board pagination is SMF's: ``index.php?board=<id>.<offset>`` in steps of 20,
sorted by first-post date descending so the walk is stable while people post.
Stickies are announcements, not uploads, and are dropped — they carry no
``.torrent`` and would otherwise reappear on every page-1 crawl.
"""
from __future__ import annotations

import itertools
import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from backend import db as database
from backend.credentials import SERVICE_WTRF, get_credentials
from backend.forum_poster import FORUM_BASE, _board_url_sorted, _get_session
from backend.tracker_seed import SeedOptions
from backend.wtrf_seed import (
    DEFAULT_DELAY,
    LinkSpec,
    SeedTarget,
    _prepare_from_link,
    _record,
    resolve_link,
    seed_one,
)

logger = logging.getLogger(__name__)

#: Topics per board page in SMF's default listing. The offset in a board URL
#: counts non-sticky topics, so paging is exact.
TOPICS_PER_PAGE = 20

_TOPIC_ID_RE = re.compile(r"topic=(\d+)")


@dataclass
class BoardTopic:
    """One topic row read off a board listing page.

    Attributes:
        topic_id: SMF topic number.
        url: Canonical topic URL (``…index.php?topic=<id>.0``).
        title: Subject line as displayed.
        offset: The listing offset of the page it was found on.
    """

    topic_id: int
    url: str
    title: str
    offset: int


def board_page_url(board_id: int, offset: int) -> str:
    """Return the URL of one board listing page, newest first.

    Args:
        board_id: SMF board number.
        offset: Topic offset — 0, 20, 40, … (see :data:`TOPICS_PER_PAGE`).

    Returns:
        Absolute board URL sorted by first-post date descending.
    """
    return _board_url_sorted(f"{FORUM_BASE}/index.php?board={board_id}.{offset}")


def _is_sticky(row) -> bool:
    """Return True if a listing row is a stickied announcement.

    SMF paints sticky rows with the ``stickybg`` cell classes and gives them a
    ``*_post_sticky.gif`` topic icon; either is enough.

    Args:
        row: The ``<tr>`` element for one topic.

    Returns:
        Whether the row is stickied.
    """
    classes = " ".join(
        c for td in row.find_all("td") for c in (td.get("class") or [])
    )
    if "stickybg" in classes:
        return True
    return any("_sticky" in (img.get("src") or "") for img in row.find_all("img"))


def parse_board_page(html: str, offset: int = 0) -> list[BoardTopic]:
    """Parse the topic rows out of one board listing page.

    Args:
        html: The page HTML.
        offset: The offset the page was fetched at, recorded on each topic.

    Returns:
        Non-sticky topics in listing order, deduplicated by topic id.
    """
    soup = BeautifulSoup(html, "lxml")
    topics: list[BoardTopic] = []
    seen: set[int] = set()
    for row in soup.find_all("tr"):
        link = row.find("a", href=lambda h: h and "topic=" in h)
        if link is None or _is_sticky(row):
            continue
        match = _TOPIC_ID_RE.search(link["href"])
        title = link.get_text(strip=True)
        if not match or not title:
            continue
        topic_id = int(match.group(1))
        if topic_id in seen:
            continue
        seen.add(topic_id)
        topics.append(BoardTopic(
            topic_id=topic_id,
            url=f"{FORUM_BASE}/index.php?topic={topic_id}.0",
            title=title,
            offset=offset,
        ))
    return topics


def board_page_count(session: requests.Session, board_id: int) -> int:
    """Return how many listing pages the board has, or 0 if unreadable.

    Args:
        session: Authenticated WTRF session.
        board_id: SMF board number.

    Returns:
        The highest page number in the board's pagination strip.
    """
    try:
        resp = session.get(board_page_url(board_id, 0), timeout=30)
    except requests.RequestException as exc:
        logger.warning("board page count: %s", exc)
        return 0
    soup = BeautifulSoup(resp.text, "lxml")
    pages = [
        int(a.get_text(strip=True))
        for a in soup.find_all("a", href=lambda h: h and f"board={board_id}." in h)
        if a.get_text(strip=True).isdigit()
    ]
    return max(pages) if pages else 0


def iter_board_topics(session: requests.Session, board_id: int,
                      start_offset: int = 0, pages: int | None = 1,
                      delay: float = DEFAULT_DELAY) -> Iterator[BoardTopic]:
    """Yield topics from consecutive board pages, newest first.

    Args:
        session: Authenticated WTRF session.
        board_id: SMF board number.
        start_offset: Topic offset to start at — a multiple of
            :data:`TOPICS_PER_PAGE`.
        pages: How many pages to walk, or ``None`` to keep walking until the
            board runs out (the caller is expected to stop it another way).
        delay: Seconds to sleep between page fetches.

    Yields:
        :class:`BoardTopic` rows in listing order.
    """
    for page in itertools.count() if pages is None else range(pages):
        offset = start_offset + page * TOPICS_PER_PAGE
        if page or start_offset:
            time.sleep(delay)
        try:
            resp = session.get(board_page_url(board_id, offset), timeout=30)
        except requests.RequestException as exc:
            logger.warning("board offset %d: %s", offset, exc)
            return
        rows = parse_board_page(resp.text, offset)
        if not rows:
            logger.info("board offset %d: no topics — end of board", offset)
            return
        yield from rows


def _owned_candidates(candidates: list[int]) -> list[int]:
    """Return the nominated LB numbers whose folders exist on disk.

    Args:
        candidates: LB numbers nominated by a post.

    Returns:
        The subset the collection can actually supply files for.
    """
    owned = []
    for lb_number in candidates:
        if any(Path(f).is_dir() for f in database.get_folders_for_lb(lb_number)):
            owned.append(lb_number)
    return owned


def seed_board(
    opts: SeedOptions,
    dest_dir: str | Path,
    board_id: int | None = None,
    start_offset: int = 0,
    pages: int | None = 1,
    limit: int | None = None,
    delay: float = DEFAULT_DELAY,
    dry_run: bool = False,
    rescan: bool = False,
    include_missing: bool = False,
    session: requests.Session | None = None,
) -> Iterator[dict]:
    """Crawl the board and seed every post the collection can already supply.

    Yields one event dict per topic as it completes, so a caller can stream
    progress; a final ``{"event": "done", …}`` carries the tallies. Every
    decision is written to ``wtrf_downloads``, which is also the resume state:
    a topic with an attempt on record is skipped on the next run.

    Args:
        opts: Seeding policy (overlay, tolerances, qBittorrent tag).
        dest_dir: Directory to write downloaded ``.torrent`` files into.
        board_id: SMF board to walk; defaults to the configured
            ``wtrf_board_id``.
        start_offset: Topic offset to start at, for resuming a deep walk.
        pages: How many listing pages to walk this run, or ``None`` to walk
            back through the board until ``limit`` is filled or the board ends.
        limit: Stop after this many topics have been *attempted* (skips of
            already-seen topics do not count).
        delay: Seconds between HTTP requests.
        dry_run: Resolve and report, but download nothing and seed nothing.
        rescan: Re-attempt topics that already have a ``wtrf_downloads`` row.
        include_missing: Also seed posts whose recording is not in the
            collection — the fetch behaviour of ``wtrf_fetch_missing.py``.
            Off by default: the point of the walk is seeding what is held.
        session: An authenticated session to reuse; one is opened if omitted.

    Yields:
        Event dicts. Per-topic events carry ``event="topic"``, ``topic_id``,
        ``url``, ``title``, ``lb_number``, ``status`` (one of
        seen/skipped/resolved/qbt_added/not_seeded/failed), ``reason`` and
        ``error``.
    """
    dest = Path(dest_dir)
    if board_id is None:
        board_id = int(database.get_meta("wtrf_board_id") or 16)

    if session is None:
        username, password = get_credentials(SERVICE_WTRF)
        if not username or not password:
            yield {"event": "done", "error": "WTRF credentials not configured",
                   "attempted": 0, "seeded": 0, "skipped": 0, "refused": 0,
                   "failed": 0}
            return
        session = _get_session(username, password)
        if session is None:
            yield {"event": "done", "error": "WTRF login failed — check the "
                                             "stored credentials",
                   "attempted": 0, "seeded": 0, "skipped": 0, "refused": 0,
                   "failed": 0}
            return

    attempted_topics = {} if rescan else database.get_wtrf_attempted_topics()
    counts = {"attempted": 0, "seeded": 0, "skipped": 0, "refused": 0,
              "failed": 0}
    yield {"event": "start", "board_id": board_id, "start_offset": start_offset,
           "pages": pages, "known": len(attempted_topics)}

    for topic in iter_board_topics(session, board_id, start_offset, pages, delay):
        if limit is not None and counts["attempted"] >= limit:
            break
        event = {"event": "topic", "topic_id": topic.topic_id, "url": topic.url,
                 "title": topic.title, "offset": topic.offset, "lb_number": None,
                 "status": "failed", "reason": "", "error": "",
                 "confidence": "not_found", "folder": "", "overlay": False}
        if topic.url in attempted_topics:
            counts["skipped"] += 1
            event.update({"status": "seen",
                          "reason": f"attempted before ({attempted_topics[topic.url]})"})
            yield event
            continue

        counts["attempted"] += 1
        target = SeedTarget(url=topic.url, lb_number=None, raw=topic.url)
        try:
            info = resolve_link(session, LinkSpec(topic.url, None, topic.url), delay)
            event.update({"lb_number": info["lb_number"], "title": info["title"]
                          or topic.title, "confidence": info["confidence"]})

            if info["error"] or info["lb_number"] is None:
                counts["skipped"] += 1
                event.update({"status": "skipped",
                              "reason": info["error"] or "unresolved"})
                _record(info, target, None, "skipped", event["reason"], "",
                        via="board_walk")
                yield event
                continue

            if not include_missing:
                owned = _owned_candidates(info["lb_candidates"] or [info["lb_number"]])
                if not owned:
                    counts["skipped"] += 1
                    event.update({"status": "skipped", "reason": (
                        f"LB-{info['lb_number']:05d} is not in the collection — "
                        f"nothing local to seed from")})
                    _record(info, target, None, "not_seeded", event["reason"], "",
                            via="board_walk")
                    yield event
                    continue
                if len(owned) < len(info["lb_candidates"]):
                    # Candidates the collection cannot supply cannot win the
                    # content check either, and dropping them here often turns
                    # an ambiguous post into a decided one.
                    info["lb_candidates"] = owned
                    info["lb_number"] = owned[0]
                    info["needs_content_check"] = len(owned) > 1
                    event["lb_number"] = owned[0]

            if dry_run:
                counts["skipped"] += 1
                nominated = ", ".join(f"LB-{n:05d}" for n in info["lb_candidates"][:4])
                event.update({"status": "resolved", "reason": (
                    f"nominates {nominated}; the seed run downloads the torrent "
                    f"and lets its contents pick" if info["needs_content_check"]
                    else f"would seed from {info['torrent_url']}")})
                yield event
                continue

            outcome = _prepare_from_link(session, target, dest, delay, False,
                                         event, info=info)
            if outcome is None:
                counts["failed"] += 1
                event["status"] = "failed"
                yield event
                continue

            resolved, path, link_dirs = outcome
            result = seed_one(resolved["lb_number"], str(path), opts, link_dirs)
            event.update({"reason": result["reason"], "folder": result["folder"],
                          "overlay": result["overlay"],
                          "torrent_path": str(path)})
            if event.get("picked"):
                event["reason"] = f"{event['picked']}; {event['reason']}"

            if result["ok"]:
                counts["seeded"] += 1
                event["status"] = "qbt_added"
                download_id = _record(resolved, target, str(path), "downloaded",
                                      "", result["folder"], via="board_walk")
                database.update_wtrf_download(download_id, {
                    "status": "qbt_added",
                    "qbt_added_at": datetime.now(UTC).isoformat(),
                })
            elif result["error"]:
                counts["failed"] += 1
                event.update({"status": "failed", "error": result["error"]})
                _record(resolved, target, str(path), "failed", result["error"],
                        result["folder"], via="board_walk")
            else:
                counts["refused"] += 1
                event["status"] = "not_seeded"
                _record(resolved, target, str(path), "not_seeded",
                        result["reason"], result["folder"], via="board_walk")
        except Exception as exc:              # one bad topic must not kill the
            logger.exception("wtrf_board: %s", topic.url)   # rest of the walk
            counts["failed"] += 1
            event.update({"status": "failed", "error": str(exc)})
        yield event

    yield {"event": "done", "error": "", **counts}
