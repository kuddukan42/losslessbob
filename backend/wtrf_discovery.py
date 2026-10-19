"""Discover which LB entries already have a WTRF forum topic (TODO-135).

Two sources feed the ``scraped_topics`` / ``scraped_topic_lbs`` tables in the main DB:

* ``import_from_archive`` -- offline; reads the board archive DB written by
  ``tools/wtrf/wtrf_board_archive.py`` (``data/wtrf_board.db``).
* ``sync_from_board`` -- on-demand, paced live crawl of the board index pages
  (newest first, stops at the first fully-known page unless ``full``).

LB numbers are pulled from topic title, subtitle and attachment filenames.
``lookup_for_lb`` is the read path used by the Rename/post panel.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FORUM_BASE_URL = "https://www.whentherootsfail.com/forum"
SOURCE_ARCHIVE = "board_archive"
SOURCE_LIVE = "board_index"
DEFAULT_PAGE_DELAY = 5.0
DEFAULT_TOPIC_DELAY = 8.0
DEFAULT_MAX_PAGES = 10
DEFAULT_TOPIC_FETCH_LIMIT = 10
TOPICS_PER_PAGE = 20

# "LB-8", "LB 8", "LB8", "NTA-LB-9209", "(LB-09924)". Digits may not be followed by
# another digit/letter-run that makes it a different token; max 5 digits (LB range).
_LB_RE = re.compile(r"(?<![A-Za-z])LB[-_\s]?0*(\d{1,5})(?!\d)", re.IGNORECASE)
_TOPIC_ID_RE = re.compile(r"topic=(\d+)")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scraped_topics (
    topic_id            INTEGER PRIMARY KEY,
    board_id            INTEGER,
    subject             TEXT NOT NULL DEFAULT '',
    subtitle            TEXT NOT NULL DEFAULT '',
    topic_url           TEXT NOT NULL DEFAULT '',
    poster              TEXT NOT NULL DEFAULT '',
    posted_at           TEXT,
    source              TEXT NOT NULL,
    attachments_checked INTEGER NOT NULL DEFAULT 0,
    fetched_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scraped_topic_lbs (
    topic_id    INTEGER NOT NULL,
    lb_number   INTEGER NOT NULL,
    matched_in  TEXT NOT NULL,
    PRIMARY KEY (topic_id, lb_number)
);
CREATE INDEX IF NOT EXISTS idx_scraped_topic_lbs_lb ON scraped_topic_lbs(lb_number);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the scraped-topic tables (idempotent)."""
    conn.executescript(_SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(scraped_topics)").fetchall()]
    if "attachments_checked" not in cols:
        conn.execute(
            "ALTER TABLE scraped_topics ADD COLUMN attachments_checked "
            "INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def parse_lb_numbers(
    title: str = "", subtitle: str = "", attachments: Iterable[str] = ()
) -> list[tuple[int, str]]:
    """Extract LB numbers from a topic's text.

    Args:
        title: Topic subject.
        subtitle: Topic description line.
        attachments: Attachment filenames.

    Returns:
        ``[(lb_number, matched_in)]`` de-duplicated, first match wins, where
        matched_in is ``title``, ``subtitle`` or ``attachment``. Zero is ignored.
    """
    found: dict[int, str] = {}
    sources = [("title", title), ("subtitle", subtitle)]
    sources += [("attachment", a) for a in attachments]
    for where, text in sources:
        for m in _LB_RE.finditer(text or ""):
            n = int(m.group(1))
            if n > 0:
                found.setdefault(n, where)
    return list(found.items())


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def store_topic(
    conn: sqlite3.Connection,
    *,
    topic_id: int,
    board_id: int | None,
    subject: str,
    subtitle: str = "",
    topic_url: str = "",
    poster: str = "",
    posted_at: str | None = None,
    source: str,
    attachments: Iterable[str] | None = None,
) -> int:
    """Upsert one topic and its LB links; returns the number of LB links.

    Args:
        conn: Main DB connection (caller commits).
        attachments: Filenames if the topic page was inspected, else None.
    """
    atts = list(attachments) if attachments is not None else []
    conn.execute(
        """INSERT INTO scraped_topics(topic_id, board_id, subject, subtitle, topic_url,
                                      poster, posted_at, source, attachments_checked,
                                      fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(topic_id) DO UPDATE SET
             board_id=excluded.board_id, subject=excluded.subject,
             subtitle=excluded.subtitle, topic_url=excluded.topic_url,
             poster=excluded.poster,
             posted_at=COALESCE(excluded.posted_at, scraped_topics.posted_at),
             attachments_checked=MAX(scraped_topics.attachments_checked,
                                     excluded.attachments_checked),
             fetched_at=excluded.fetched_at""",
        (topic_id, board_id, subject, subtitle, topic_url, poster, posted_at, source,
         1 if attachments is not None else 0, _now()),
    )
    lbs = parse_lb_numbers(subject, subtitle, atts)
    for lb, where in lbs:
        conn.execute(
            "INSERT OR IGNORE INTO scraped_topic_lbs(topic_id, lb_number, matched_in) "
            "VALUES (?,?,?)",
            (topic_id, lb, where),
        )
    return len(lbs)


def import_from_archive(conn: sqlite3.Connection, archive_db: Path) -> dict:
    """Import topics from the board-archive DB (read-only, no network).

    Args:
        conn: Main DB connection.
        archive_db: Path to ``wtrf_board.db``.

    Returns:
        ``{"topics": n, "lb_links": n}``.
    """
    ar = sqlite3.connect(f"file:{archive_db}?mode=ro", uri=True)
    try:
        ar.row_factory = sqlite3.Row
        atts: dict[int, list[str]] = {}
        for r in ar.execute("SELECT topic_id, filename FROM wtrf_attachments"):
            atts.setdefault(r["topic_id"], []).append(r["filename"])
        topics = ar.execute(
            "SELECT topic_id, board_id, url, title, subtitle, poster, posted_at "
            "FROM wtrf_topics"
        ).fetchall()
    finally:
        ar.close()
    links = 0
    for t in topics:
        links += store_topic(
            conn, topic_id=t["topic_id"], board_id=t["board_id"], subject=t["title"],
            subtitle=t["subtitle"], topic_url=t["url"], poster=t["poster"],
            posted_at=t["posted_at"], source=SOURCE_ARCHIVE,
            attachments=atts.get(t["topic_id"], []),
        )
    conn.commit()
    logger.info("wtrf_discovery: archive import %d topics, %d LB links", len(topics), links)
    return {"topics": len(topics), "lb_links": links}


def parse_board_page(html: str, board_id: int) -> tuple[list[dict], bool]:
    """Parse a board index page into topic records.

    Returns:
        ``(records, has_rows)``; each record has topic_id, subject, subtitle, poster,
        topic_url, board_id.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[int] = set()
    for tr in soup.select("div.topic_table tr"):
        subj = tr.find("td", class_="subject")
        if not subj:
            continue
        link = subj.find("a", href=_TOPIC_ID_RE)
        if not link:
            continue
        tid = int(_TOPIC_ID_RE.search(link["href"]).group(1))
        if tid in seen:
            continue
        seen.add(tid)
        desc = subj.find("small", id=re.compile(r"^topicdesc_"))
        who = subj.find("a", href=re.compile(r"action=profile"))
        out.append({
            "topic_id": tid, "board_id": board_id,
            "subject": link.get_text(" ", strip=True),
            "subtitle": desc.get_text(" ", strip=True) if desc else "",
            "poster": who.get_text(strip=True) if who else "",
            "topic_url": f"{FORUM_BASE_URL}/index.php?topic={tid}.0",
        })
    return out, bool(out)


def parse_topic_attachments(html: str) -> list[str]:
    """Return attachment filenames (dlattach links) from a topic page."""
    soup = BeautifulSoup(html, "lxml")
    return [
        a.get_text(strip=True)
        for a in soup.find_all("a", href=lambda h: h and "dlattach" in h)
        if a.get_text(strip=True)
    ]


def sync_from_board(
    session,
    conn: sqlite3.Connection,
    board_id: int,
    *,
    full: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
    topic_fetch_limit: int = DEFAULT_TOPIC_FETCH_LIMIT,
    page_delay: float = DEFAULT_PAGE_DELAY,
    topic_delay: float = DEFAULT_TOPIC_DELAY,
    sleep: Callable[[float], None] = time.sleep,
    forum_base: str = FORUM_BASE_URL,
) -> dict:
    """Paced live crawl of the board index, newest first.

    Stops early when a whole page is already known (unless ``full``) or on the
    first empty page. Topics whose subject/subtitle carry no LB number get their
    topic page fetched (up to ``topic_fetch_limit`` per run) to read attachment
    filenames.

    Args:
        session: Authenticated ``requests.Session``.
        conn: Main DB connection.
        board_id: SMF board number.
        full: Ignore the known-page early stop.
        max_pages: Index-page cap per run.
        topic_fetch_limit: Topic-page fetch cap per run.
        page_delay: Seconds between index-page requests.
        topic_delay: Seconds between topic-page requests.
        sleep: Injectable sleeper (tests).
        forum_base: Forum base URL.

    Returns:
        Counters: pages, topics, new_topics, lb_links, topic_fetches, stopped.

    Raises:
        RuntimeError: If the session has expired.
    """
    stats = {"pages": 0, "topics": 0, "new_topics": 0, "lb_links": 0,
             "topic_fetches": 0, "stopped": "max_pages"}
    pending: list[dict] = []
    for page in range(max_pages):
        if page:
            sleep(page_delay)
        url = f"{forum_base}/index.php?board={board_id}.{page * TOPICS_PER_PAGE}"
        resp = session.get(url, timeout=20)
        if "action=login" in getattr(resp, "url", ""):
            raise RuntimeError("WTRF session expired while listing the board")
        resp.raise_for_status()
        recs, has_rows = parse_board_page(resp.text, board_id)
        stats["pages"] += 1
        if not has_rows:
            stats["stopped"] = "end_of_board"
            break
        known = {r[0] for r in conn.execute(
            f"SELECT topic_id FROM scraped_topics WHERE topic_id IN "
            f"({','.join('?' * len(recs))})", [r["topic_id"] for r in recs])}
        for rec in recs:
            is_new = rec["topic_id"] not in known
            n = store_topic(conn, source=SOURCE_LIVE, **rec)
            stats["topics"] += 1
            stats["new_topics"] += is_new
            stats["lb_links"] += n
            if n == 0:
                pending.append(rec)
        conn.commit()
        if not full and len(known) == len(recs):
            stats["stopped"] = "caught_up"
            break

    # Attachment-filename pass for subject-less-LB topics not yet inspected.
    fetched = 0
    for rec in pending:
        if fetched >= topic_fetch_limit:
            break
        row = conn.execute(
            "SELECT attachments_checked FROM scraped_topics WHERE topic_id=?",
            (rec["topic_id"],)).fetchone()
        if row and row[0]:
            continue
        if fetched:
            sleep(topic_delay)
        resp = session.get(rec["topic_url"], timeout=20)
        fetched += 1
        if resp.status_code != 200:
            continue
        stats["lb_links"] += store_topic(
            conn, source=SOURCE_LIVE, attachments=parse_topic_attachments(resp.text),
            **rec)
        conn.commit()
    stats["topic_fetches"] = fetched
    return stats


def lookup_for_lb(conn: sqlite3.Connection, lb_number: int) -> list[dict]:
    """Return scraped WTRF topics that mention an LB number, newest first."""
    rows = conn.execute(
        """SELECT t.topic_id, t.board_id, t.subject, t.topic_url, t.poster, t.posted_at,
                  t.source, l.matched_in
           FROM scraped_topic_lbs l JOIN scraped_topics t ON t.topic_id = l.topic_id
           WHERE l.lb_number = ?
           ORDER BY COALESCE(t.posted_at, '') DESC, t.topic_id DESC""",
        (lb_number,),
    ).fetchall()
    return [dict(r) for r in rows]
