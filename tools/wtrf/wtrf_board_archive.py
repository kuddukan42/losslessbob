#!/usr/bin/env python3
"""Archive WTRF board topics into a local SQLite database for later search.

Walks a WTRF (SMF) board in descending order — newest topic first, stickies
skipped by default — fetches each topic's first post, and stores title,
subtitle (SMF topic description), poster, timestamp, body (text + HTML) and
attachment metadata in ``data/wtrf_board.db``.

Credentials come from the OS keyring entry the rest of the app already uses
(``SERVICE_WTRF``); the login session is borrowed from ``backend.forum_poster``.

Crawling is throttled: a minimum gap between every HTTP request (``--delay``)
and a longer crawl delay between topics (``--topic-delay``, default 30s), both
jittered so repeated runs don't hit the server in lockstep.

Usage:
    .venv/bin/python3 tools/wtrf/wtrf_board_archive.py fetch --limit 5
    .venv/bin/python3 tools/wtrf/wtrf_board_archive.py fetch --limit 5 --download
    .venv/bin/python3 tools/wtrf/wtrf_board_archive.py search "1988 St Louis"
    .venv/bin/python3 tools/wtrf/wtrf_board_archive.py show 61357
"""

from __future__ import annotations

import argparse
import logging
import random
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from bs4 import BeautifulSoup, Tag

from backend.credentials import SERVICE_WTRF, get_credentials
from backend.forum_poster import FORUM_BASE, _get_session
from backend.paths import DATA_DIR

logger = logging.getLogger("wtrf_board_archive")

DB_PATH = DATA_DIR / "wtrf_board.db"
ATTACH_DIR = DATA_DIR / "wtrf_attachments"

DEFAULT_BOARD = 16
DEFAULT_LIMIT = 5
DEFAULT_DELAY = 2.0          # minimum seconds between any two HTTP requests
DEFAULT_TOPIC_DELAY = 30.0   # seconds between topics — the crawl delay
DEFAULT_JITTER = 0.2         # ±fraction randomised onto every wait
TOPICS_PER_PAGE = 20         # SMF board pagination step
MESSAGES_PER_PAGE = 15       # SMF topic pagination step (fallback)
DEFAULT_MAX_REPLY_PAGES = 4  # cap on extra requests per topic for long threads
DEFAULT_BACKFILL_LIMIT = 25  # topics archived per resumable backfill run

_TOPIC_ID_RE = re.compile(r"topic=(\d+)")
_MSG_ID_RE = re.compile(r"^msg_(\d+)$")
_SIZE_RE = re.compile(r"\(([\d.]+\s*[kKmMgG]?B)\s*-\s*downloaded\s+(\d+)\s+times?", re.I)
_POSTED_RE = re.compile(r"on:\s*(.+?)\s*»", re.S)
_REPLY_NUM_RE = re.compile(r"Reply\s*#(\d+)", re.I)
_MODIFIED_RE = re.compile(
    r"Last\s+Edit:\s*(?P<when>.+?)\s+by\s+(?P<who>.+?)\s*$", re.I | re.S
)

# "<32-hex>  <filename>" (md5 manifests) and "<filename>:<32-hex>" (ffp/st5 style).
_MD5_LINE_RE = re.compile(r"^\s*([0-9a-fA-F]{32})\s+(\S.*?)\s*$")
_SHA1_LINE_RE = re.compile(r"^\s*([0-9a-fA-F]{40})\s+(\S.*?)\s*$")
_FFP_LINE_RE = re.compile(r"^\s*(\S.*?):([0-9a-fA-F]{32})\s*$")

_LB_REF_RE = re.compile(r"\bLB[-\s]?(\d{2,5})\b", re.I)
_XREF_RE = re.compile(r"\bxref-(\d{3,6})\b", re.I)


# --------------------------------------------------------------------------- #
# Live progress
# --------------------------------------------------------------------------- #

class Progress:
    """Single-line live status for a running crawl.

    On a TTY the line is rewritten in place; when output is redirected (cron,
    log files) each phase is emitted as an ordinary log line instead, so the
    log stays readable. Completed-topic messages go through :meth:`write`,
    which clears the status line first so the two never interleave.

    Attributes:
        total: Topics this run intends to archive, for the counter and ETA.
        enabled: False disables all output.
    """

    def __init__(self, total: int, enabled: bool = True) -> None:
        self.total = max(0, total)
        self.enabled = enabled
        self.tty = enabled and sys.stderr.isatty()
        self.done = 0
        self.skipped = 0
        self.board = 0
        self.offset = 0
        self.page = 0
        self.total_pages = 0
        self.phase = "starting"
        self._start = time.monotonic()
        self._last_len = 0

    def _eta(self) -> str:
        """Return an ``ETA mm:ss`` estimate from the pace so far."""
        if not self.done or not self.total:
            return "--:--"
        per = (time.monotonic() - self._start) / self.done
        left = int(per * max(0, self.total - self.done))
        return f"{left // 60:02d}:{left % 60:02d}"

    def _elapsed(self) -> str:
        """Return elapsed wall time as ``mm:ss``."""
        secs = int(time.monotonic() - self._start)
        return f"{secs // 60:02d}:{secs % 60:02d}"

    def update(self, phase: str | None = None, **fields) -> None:
        """Set state fields and redraw the status line.

        Args:
            phase: Short description of what the crawler is doing right now.
            **fields: Any of done, skipped, board, offset, page, total_pages.
        """
        if phase is not None:
            self.phase = phase
        for key, value in fields.items():
            setattr(self, key, value)
        self.render()

    def render(self) -> None:
        """Draw the status line (TTY only)."""
        if not self.tty:
            return
        pages = f"/{self.total_pages}" if self.total_pages else ""
        line = (
            f"[{self.done}/{self.total}] board {self.board} "
            f"page {self.page}{pages} off {self.offset}  "
            f"held {self.skipped}  {self._elapsed()} eta {self._eta()}  · {self.phase}"
        )
        line = line[:150]
        sys.stderr.write("\r" + line.ljust(self._last_len))
        sys.stderr.flush()
        self._last_len = len(line)

    def write(self, message: str, *args) -> None:
        """Log a message without corrupting the status line.

        Args:
            message: printf-style log message.
            *args: Arguments for the message.
        """
        if self.tty:
            sys.stderr.write("\r" + " " * self._last_len + "\r")
            sys.stderr.flush()
            self._last_len = 0
        logger.info(message, *args)
        self.render()

    def finish(self) -> None:
        """Terminate the status line so later output starts cleanly."""
        if self.tty and self._last_len:
            sys.stderr.write("\n")
            sys.stderr.flush()
            self._last_len = 0


# --------------------------------------------------------------------------- #
# Throttling
# --------------------------------------------------------------------------- #

class Throttle:
    """Rate limiter shared by every request the crawler makes.

    Enforces a minimum gap between consecutive HTTP requests and, separately,
    a longer crawl delay between topics. Both waits get a small random jitter
    so repeated runs don't hit the server in lockstep.

    Attributes:
        min_interval: Minimum seconds between any two requests.
        topic_delay: Seconds to wait before starting the next topic.
        jitter: Fraction of each wait randomised (0.2 = ±20%).
    """

    def __init__(
        self,
        min_interval: float = DEFAULT_DELAY,
        topic_delay: float = DEFAULT_TOPIC_DELAY,
        jitter: float = DEFAULT_JITTER,
    ) -> None:
        self.min_interval = max(0.0, min_interval)
        self.topic_delay = max(0.0, topic_delay)
        self.jitter = max(0.0, jitter)
        self._last_request = 0.0

    def _jittered(self, seconds: float) -> float:
        """Return ``seconds`` with the configured jitter applied."""
        if seconds <= 0 or not self.jitter:
            return max(0.0, seconds)
        return max(0.0, seconds * (1.0 + random.uniform(-self.jitter, self.jitter)))

    def wait_request(self) -> None:
        """Sleep until ``min_interval`` has elapsed since the last request."""
        gap = self._jittered(self.min_interval) - (time.monotonic() - self._last_request)
        if gap > 0 and self._last_request:
            time.sleep(gap)

    def wait_topic(self, first: bool = False, progress: "Progress | None" = None) -> None:
        """Sleep the crawl delay before the next topic.

        Args:
            first: True for the first topic of a run, which is not delayed.
            progress: Optional live status to count the wait down on.
        """
        if first or not self.topic_delay:
            return
        wait = self._jittered(self.topic_delay)
        if progress is None:
            logger.info("crawl delay: sleeping %.1fs before the next topic", wait)
            time.sleep(wait)
            return
        deadline = time.monotonic() + wait
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            progress.update(f"crawl delay {left:4.1f}s")
            time.sleep(min(0.5, left))

    def get(self, session: requests.Session, url: str, **kwargs) -> requests.Response:
        """Perform a throttled ``session.get``.

        Args:
            session: Authenticated session.
            url: URL to fetch.
            **kwargs: Passed straight to ``requests.Session.get``.

        Returns:
            The response object.
        """
        self.wait_request()
        kwargs.setdefault("headers", {"Referer": FORUM_BASE})
        kwargs.setdefault("timeout", 30)
        try:
            return session.get(url, **kwargs)
        finally:
            self._last_request = time.monotonic()


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wtrf_topics (
    topic_id      INTEGER PRIMARY KEY,
    board_id      INTEGER NOT NULL,
    url           TEXT    NOT NULL,
    title         TEXT    NOT NULL DEFAULT '',
    subtitle      TEXT    NOT NULL DEFAULT '',
    poster        TEXT    NOT NULL DEFAULT '',
    poster_id     INTEGER,
    posted_at     TEXT,
    posted_raw    TEXT    NOT NULL DEFAULT '',
    first_msg_id  INTEGER,
    replies       INTEGER,
    views         INTEGER,
    last_post_raw TEXT    NOT NULL DEFAULT '',
    is_sticky     INTEGER NOT NULL DEFAULT 0,
    body_text     TEXT    NOT NULL DEFAULT '',
    body_html     TEXT    NOT NULL DEFAULT '',
    modified_at   TEXT,
    modified_raw  TEXT    NOT NULL DEFAULT '',
    modified_by   TEXT    NOT NULL DEFAULT '',
    fetched_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS wtrf_replies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id     INTEGER NOT NULL,
    msg_id       INTEGER NOT NULL,
    reply_num    INTEGER,
    poster       TEXT    NOT NULL DEFAULT '',
    poster_id    INTEGER,
    posted_at    TEXT,
    posted_raw   TEXT    NOT NULL DEFAULT '',
    modified_at  TEXT,
    modified_raw TEXT    NOT NULL DEFAULT '',
    modified_by  TEXT    NOT NULL DEFAULT '',
    body_text    TEXT    NOT NULL DEFAULT '',
    body_html    TEXT    NOT NULL DEFAULT '',
    UNIQUE (topic_id, msg_id)
);

CREATE TABLE IF NOT EXISTS wtrf_checksums (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    msg_id   INTEGER,
    algo     TEXT    NOT NULL,
    digest   TEXT    NOT NULL,
    filename TEXT    NOT NULL DEFAULT '',
    ordinal  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (topic_id, digest, filename)
);

CREATE TABLE IF NOT EXISTS wtrf_refs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id  INTEGER NOT NULL,
    kind      TEXT    NOT NULL,          -- 'self' | 'cross' | 'xref'
    ref_raw   TEXT    NOT NULL,
    lb_number INTEGER,
    UNIQUE (topic_id, kind, ref_raw)
);

CREATE TABLE IF NOT EXISTS wtrf_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id    INTEGER NOT NULL,
    filename    TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    size_text   TEXT    NOT NULL DEFAULT '',
    downloads   INTEGER,
    local_path  TEXT,
    UNIQUE (topic_id, url)
);

CREATE TABLE IF NOT EXISTS wtrf_crawl_state (
    board_id     INTEGER PRIMARY KEY,
    next_offset  INTEGER NOT NULL DEFAULT 0,
    total_pages  INTEGER,
    last_run_at  TEXT,
    started_at   TEXT,
    finished_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_topics_board  ON wtrf_topics (board_id, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_topics_poster ON wtrf_topics (poster);
CREATE INDEX IF NOT EXISTS idx_attach_topic  ON wtrf_attachments (topic_id);
CREATE INDEX IF NOT EXISTS idx_replies_topic ON wtrf_replies (topic_id, reply_num);
CREATE INDEX IF NOT EXISTS idx_sums_digest   ON wtrf_checksums (digest);
CREATE INDEX IF NOT EXISTS idx_sums_topic    ON wtrf_checksums (topic_id);
CREATE INDEX IF NOT EXISTS idx_refs_lb       ON wtrf_refs (lb_number);
CREATE INDEX IF NOT EXISTS idx_refs_topic    ON wtrf_refs (topic_id, kind);

CREATE VIRTUAL TABLE IF NOT EXISTS wtrf_topics_fts USING fts5 (
    title, subtitle, poster, body_text,
    content='wtrf_topics', content_rowid='topic_id'
);
"""

# Keeps the FTS index in step with the base table without a manual rebuild.
_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS wtrf_topics_ai AFTER INSERT ON wtrf_topics BEGIN
    INSERT INTO wtrf_topics_fts (rowid, title, subtitle, poster, body_text)
    VALUES (new.topic_id, new.title, new.subtitle, new.poster, new.body_text);
END;
CREATE TRIGGER IF NOT EXISTS wtrf_topics_ad AFTER DELETE ON wtrf_topics BEGIN
    INSERT INTO wtrf_topics_fts (wtrf_topics_fts, rowid, title, subtitle, poster, body_text)
    VALUES ('delete', old.topic_id, old.title, old.subtitle, old.poster, old.body_text);
END;
CREATE TRIGGER IF NOT EXISTS wtrf_topics_au AFTER UPDATE ON wtrf_topics BEGIN
    INSERT INTO wtrf_topics_fts (wtrf_topics_fts, rowid, title, subtitle, poster, body_text)
    VALUES ('delete', old.topic_id, old.title, old.subtitle, old.poster, old.body_text);
    INSERT INTO wtrf_topics_fts (rowid, title, subtitle, poster, body_text)
    VALUES (new.topic_id, new.title, new.subtitle, new.poster, new.body_text);
END;
"""


def open_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open (creating if needed) the archive database.

    Schema creation is idempotent: every statement is ``IF NOT EXISTS`` and
    missing columns on a pre-existing table are added via ``PRAGMA table_info``.

    Args:
        db_path: Location of the SQLite file.

    Returns:
        An open connection with ``row_factory`` set to ``sqlite3.Row``.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.executescript(_FTS_TRIGGERS)

    existing = {r["name"] for r in conn.execute("PRAGMA table_info(wtrf_topics)")}
    for col, decl in (
        ("subtitle", "TEXT NOT NULL DEFAULT ''"),
        ("body_html", "TEXT NOT NULL DEFAULT ''"),
        ("is_sticky", "INTEGER NOT NULL DEFAULT 0"),
        ("last_post_raw", "TEXT NOT NULL DEFAULT ''"),
        ("modified_at", "TEXT"),
        ("modified_raw", "TEXT NOT NULL DEFAULT ''"),
        ("modified_by", "TEXT NOT NULL DEFAULT ''"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE wtrf_topics ADD COLUMN {col} {decl}")
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #

def _resolve(href: str) -> str:
    """Return an absolute forum URL for a possibly relative ``href``."""
    if href.startswith("http"):
        return href
    return f"{FORUM_BASE}/{href.lstrip('/')}"


def _parse_timestamp(raw: str, today: date | None = None) -> str | None:
    """Parse an SMF post timestamp into an ISO-8601 string.

    Handles the three shapes SMF emits: ``Today at 11:39:36 am``,
    ``Yesterday at 09:02:11 pm`` and ``May 17, 2026, 03:56:50 pm``.

    Args:
        raw: Raw timestamp text, without the surrounding guillemets.
        today: Reference date for Today/Yesterday (defaults to the real today).

    Returns:
        ``YYYY-MM-DDTHH:MM:SS`` or None if the text could not be parsed.
    """
    text = " ".join(raw.split()).strip()
    if not text:
        return None
    ref = today or date.today()

    m = re.match(r"(Today|Yesterday)\s+at\s+(.+)$", text, re.I)
    if m:
        day = ref if m.group(1).lower() == "today" else ref - timedelta(days=1)
        for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p"):
            try:
                t = datetime.strptime(m.group(2).strip(), fmt).time()
            except ValueError:
                continue
            return datetime.combine(day, t).isoformat()
        return None

    for fmt in (
        "%B %d, %Y, %I:%M:%S %p", "%B %d, %Y, %H:%M:%S",
        "%B %d, %Y, %I:%M %p", "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    logger.debug("unparsed timestamp: %r", text)
    return None


def _parse_board_row(tr: Tag, board_id: int) -> dict | None:
    """Extract one topic-list row from a board page.

    Args:
        tr: A ``<tr>`` from ``div.topic_table``.
        board_id: Board being crawled, stored on the returned record.

    Returns:
        Dict of list-level fields, or None if the row is not a topic row.
    """
    subject = tr.find("td", class_="subject")
    if not subject:
        return None
    link = subject.find("a", href=_TOPIC_ID_RE)
    if not link:
        return None
    m = _TOPIC_ID_RE.search(link["href"])
    if not m:
        return None

    poster_tag = None
    poster_id = None
    started = subject.find("p")
    if started:
        poster_tag = started.find("a", href=re.compile(r"action=profile"))
    if poster_tag:
        pid = re.search(r"u=(\d+)", poster_tag["href"])
        poster_id = int(pid.group(1)) if pid else None

    desc = subject.find("small", id=re.compile(r"^topicdesc_"))

    stats = tr.find("td", class_="stats")
    replies = views = None
    if stats:
        stats_text = stats.get_text(" ", strip=True)
        r = re.search(r"([\d,]+)\s+Repl", stats_text, re.I)
        v = re.search(r"([\d,]+)\s+View", stats_text, re.I)
        replies = int(r.group(1).replace(",", "")) if r else None
        views = int(v.group(1).replace(",", "")) if v else None

    lastpost = tr.find("td", class_="lastpost")
    classes = " ".join(subject.get("class") or [])

    return {
        "topic_id": int(m.group(1)),
        "board_id": board_id,
        "url": f"{FORUM_BASE}/index.php?topic={m.group(1)}.0",
        "title": link.get_text(" ", strip=True),
        "subtitle": desc.get_text(" ", strip=True) if desc else "",
        "poster": poster_tag.get_text(strip=True) if poster_tag else "",
        "poster_id": poster_id,
        "replies": replies,
        "views": views,
        "last_post_raw": lastpost.get_text(" ", strip=True) if lastpost else "",
        "is_sticky": int("sticky" in classes),
    }


def _parse_post_wrapper(wrapper: Tag, today: date | None = None) -> dict | None:
    """Extract one message (first post or reply) from its ``div.post_wrapper``.

    Args:
        wrapper: The message wrapper element.
        today: Reference date passed through to timestamp parsing.

    Returns:
        Dict with msg_id, reply_num, poster, poster_id, posted_at/raw,
        modified_at/raw/by, body_text, body_html and attachments; None if the
        wrapper holds no message body.
    """
    inner = wrapper.find("div", id=_MSG_ID_RE)
    if inner is None:
        return None

    out: dict = {
        "msg_id": int(_MSG_ID_RE.match(inner["id"]).group(1)),
        "reply_num": None,
        "poster": "", "poster_id": None,
        "posted_at": None, "posted_raw": "",
        "modified_at": None, "modified_raw": "", "modified_by": "",
        "body_text": inner.get_text("\n").strip(),
        "body_html": inner.decode_contents(),
        "attachments": [],
    }

    keyinfo = wrapper.find("div", class_="keyinfo")
    if keyinfo:
        stamp = keyinfo.find("div", class_="smalltext")
        if stamp:
            raw = stamp.get_text(" ", strip=True)
            rn = _REPLY_NUM_RE.search(raw)
            out["reply_num"] = int(rn.group(1)) if rn else None
            m = _POSTED_RE.search(raw)
            cleaned = (m.group(1) if m else raw).replace("on:", "").strip(" «»")
            # "Reply #2 on: Today at ..." — drop the reply marker before parsing.
            cleaned = _REPLY_NUM_RE.sub("", cleaned).replace("on:", "").strip(" «»")
            out["posted_raw"] = cleaned
            out["posted_at"] = _parse_timestamp(cleaned, today)

    # SMF renders edits as "« Last Edit: <when> by <who> »" in a .modified span.
    mod = wrapper.find(class_="modified")
    if mod:
        mod_text = " ".join(mod.get_text(" ", strip=True).split()).strip(" «»")
        if mod_text:
            out["modified_raw"] = mod_text
            mm = _MODIFIED_RE.search(mod_text)
            if mm:
                out["modified_by"] = mm.group("who").strip(" »")
                out["modified_at"] = _parse_timestamp(mm.group("when"), today)

    poster_div = wrapper.find("div", class_="poster")
    if poster_div:
        a = poster_div.find("a", href=re.compile(r"action=profile"))
        if a:
            out["poster"] = a.get_text(strip=True)
            pid = re.search(r"u=(\d+)", a["href"])
            out["poster_id"] = int(pid.group(1)) if pid else None

    for attach_div in wrapper.find_all("div", class_="attachments"):
        for a in attach_div.find_all("a", href=lambda h: h and "dlattach" in h):
            tail = a.next_sibling
            meta = tail if isinstance(tail, str) else ""
            sm = _SIZE_RE.search(meta)
            out["attachments"].append({
                "filename": a.get_text(strip=True),
                "url": _resolve(a["href"]),
                "size_text": sm.group(1) if sm else "",
                "downloads": int(sm.group(2)) if sm else None,
            })
    return out


def _parse_topic_page(html: str, today: date | None = None) -> dict:
    """Extract first-post fields, replies and attachments from a topic page.

    Args:
        html: Raw topic-page HTML.
        today: Reference date passed through to timestamp parsing.

    Returns:
        Dict with the first post's fields (body_text, body_html, poster,
        poster_id, posted_at, posted_raw, modified_*, first_msg_id), an
        ``attachments`` list and a ``replies`` list of per-message dicts.
    """
    soup = BeautifulSoup(html, "lxml")
    out: dict = {
        "body_text": "", "body_html": "", "poster": "", "poster_id": None,
        "posted_at": None, "posted_raw": "", "first_msg_id": None,
        "modified_at": None, "modified_raw": "", "modified_by": "",
        "attachments": [], "replies": [],
    }

    wrappers = soup.find_all("div", class_="post_wrapper")
    posts = [p for p in (_parse_post_wrapper(w, today) for w in wrappers) if p]
    if not posts:
        logger.warning("topic page has no parsable messages")
        return out

    first = posts[0]
    out.update({
        "first_msg_id": first["msg_id"],
        "body_text": first["body_text"],
        "body_html": first["body_html"],
        "poster": first["poster"],
        "poster_id": first["poster_id"],
        "posted_at": first["posted_at"],
        "posted_raw": first["posted_raw"],
        "modified_at": first["modified_at"],
        "modified_raw": first["modified_raw"],
        "modified_by": first["modified_by"],
        "attachments": first["attachments"],
        "replies": posts[1:],
    })
    return out


def extract_checksums(body_text: str) -> list[dict]:
    """Pull checksum manifest lines out of a post body.

    Recognises md5/sha1 manifest lines (``<digest>  <filename>``) and ffp-style
    ``<filename>:<digest>`` lines. Bare digests with no filename are kept too,
    so a hash mentioned in prose is still searchable.

    Args:
        body_text: Plain-text post body.

    Returns:
        List of dicts with algo, digest (lower-case), filename and ordinal.
    """
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in body_text.splitlines():
        line = line.strip()
        if not line:
            continue
        algo = filename = digest = ""
        m = _MD5_LINE_RE.match(line)
        if m:
            algo, digest, filename = "md5", m.group(1), m.group(2)
        if not digest:
            m = _SHA1_LINE_RE.match(line)
            if m:
                algo, digest, filename = "sha1", m.group(1), m.group(2)
        if not digest:
            m = _FFP_LINE_RE.match(line)
            if m:
                algo, digest, filename = "md5", m.group(2), m.group(1)
        if not digest:
            bare = re.fullmatch(r"[0-9a-fA-F]{32}", line)
            if bare:
                algo, digest, filename = "md5", line, ""
        if not digest:
            continue
        key = (digest.lower(), filename)
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "algo": algo, "digest": digest.lower(),
            "filename": filename, "ordinal": len(found),
        })
    return found


def extract_refs(topic: dict, reply_bodies: list[str] | None = None) -> list[dict]:
    """Collect LB numbers and xref tokens mentioned by a topic.

    The topic's own LB number (from title, subtitle or the opening line of the
    body) is tagged ``self``; every other LB number found in the body or in
    replies is tagged ``cross``. ``xref-NNNNN`` tokens are tagged ``xref``.

    Args:
        topic: Merged topic record (needs title, subtitle, body_text).
        reply_bodies: Optional reply body texts to scan for cross-references.

    Returns:
        List of dicts with kind, ref_raw and lb_number.
    """
    title = topic.get("title") or ""
    subtitle = topic.get("subtitle") or ""
    body = topic.get("body_text") or ""
    head = "\n".join(body.splitlines()[:3])

    self_nums = {int(n) for n in _LB_REF_RE.findall(f"{title} {subtitle} {head}")}
    haystack = "\n".join([title, subtitle, body, *(reply_bodies or [])])

    refs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for match in _LB_REF_RE.finditer(haystack):
        num = int(match.group(1))
        kind = "self" if num in self_nums else "cross"
        raw = f"LB-{num:05d}"
        if (kind, raw) in seen:
            continue
        seen.add((kind, raw))
        refs.append({"kind": kind, "ref_raw": raw, "lb_number": num})
    for match in _XREF_RE.finditer(haystack):
        raw = f"xref-{int(match.group(1)):05d}"
        if ("xref", raw) in seen:
            continue
        seen.add(("xref", raw))
        refs.append({"kind": "xref", "ref_raw": raw, "lb_number": None})
    return refs


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

def _list_page(
    session: requests.Session,
    board_id: int,
    offset: int,
    throttle: Throttle,
) -> tuple[list[dict], int | None]:
    """Fetch one board page and parse its topic rows.

    Args:
        session: Authenticated session.
        board_id: Board number.
        offset: SMF page offset (0, 20, 40, …).
        throttle: Shared rate limiter.

    Returns:
        ``(records, total_pages)`` — the page's topic records in board order,
        and the page count advertised by the pager (None if not found).

    Raises:
        RuntimeError: If the session has expired.
    """
    url = f"{FORUM_BASE}/index.php?board={board_id}.{offset}"
    resp = throttle.get(session, url, timeout=20)
    if "action=login" in resp.url:
        raise RuntimeError("WTRF session expired while listing the board")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    records: list[dict] = []
    seen: set[int] = set()
    for tr in soup.select("div.topic_table tr"):
        rec = _parse_board_row(tr, board_id)
        if rec is None or rec["topic_id"] in seen:
            continue
        seen.add(rec["topic_id"])
        records.append(rec)

    total_pages = None
    pager = soup.select_one("div.pagelinks, .pagelinks")
    if pager:
        nums = [int(n) for n in re.findall(r"\b(\d+)\b", pager.get_text(" ", strip=True))]
        total_pages = max(nums) if nums else None
    return records, total_pages


def _list_topics(
    session: requests.Session,
    board_id: int,
    limit: int,
    throttle: Throttle,
    include_sticky: bool,
) -> list[dict]:
    """List the newest ``limit`` topics on a board, newest first.

    Pages the board in blocks of 20 until enough non-sticky topics are seen.

    Args:
        session: Authenticated session.
        board_id: Board number.
        limit: How many topics to return.
        throttle: Shared rate limiter.
        include_sticky: Keep pinned/announcement topics too.

    Returns:
        List of list-level topic records, newest first.
    """
    collected: list[dict] = []
    seen: set[int] = set()
    start = 0
    while len(collected) < limit:
        page, _ = _list_page(session, board_id, start, throttle)
        page_topics = 0
        for rec in page:
            if rec["topic_id"] in seen:
                continue
            seen.add(rec["topic_id"])
            page_topics += 1
            if rec["is_sticky"] and not include_sticky:
                continue
            collected.append(rec)
            if len(collected) >= limit:
                break

        if page_topics == 0:
            break                      # ran off the end of the board
        start += TOPICS_PER_PAGE
    return collected[:limit]


def _download_attachment(
    session: requests.Session,
    url: str,
    filename: str,
    dest_dir: Path,
    throttle: Throttle,
) -> Path | None:
    """Download one attachment, skipping the request if it is already on disk.

    Args:
        session: Authenticated session.
        url: ``dlattach`` URL.
        filename: Attachment filename as shown in the post.
        dest_dir: Directory to write into (created if missing).
        throttle: Shared rate limiter.

    Returns:
        Path to the saved file, or None on failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip() or "attachment.bin"
    dest = dest_dir / safe
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    try:
        resp = throttle.get(session, url, timeout=60, stream=True)
        resp.raise_for_status()
        if "text/html" in resp.headers.get("Content-Type", ""):
            logger.warning("attachment %s returned HTML (session expired?)", filename)
            return None
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(65536):
                fh.write(chunk)
    except Exception as exc:
        logger.warning("attachment download failed for %s: %s", filename, exc)
        return None
    return dest


def _store(
    conn: sqlite3.Connection,
    rec: dict,
    attachments: list[dict],
    replies: list[dict] | None = None,
    checksums: list[dict] | None = None,
    refs: list[dict] | None = None,
) -> None:
    """Upsert one topic and replace its attachment/reply/checksum/ref rows.

    Args:
        conn: Open archive connection.
        rec: Merged list-level + topic-page fields.
        attachments: Attachment dicts for this topic.
        replies: Reply message dicts (first post excluded).
        checksums: Checksum dicts extracted from the first post.
        refs: LB/xref reference dicts for this topic.
    """
    cols = (
        "topic_id", "board_id", "url", "title", "subtitle", "poster", "poster_id",
        "posted_at", "posted_raw", "first_msg_id", "replies", "views",
        "last_post_raw", "is_sticky", "body_text", "body_html",
        "modified_at", "modified_raw", "modified_by", "fetched_at",
    )
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT OR REPLACE INTO wtrf_topics ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(rec.get(c) for c in cols),
    )
    # A re-fetch without --download must not forget files already on disk.
    prior_paths = {
        r["url"]: r["local_path"]
        for r in conn.execute(
            "SELECT url, local_path FROM wtrf_attachments WHERE topic_id = ?",
            (rec["topic_id"],),
        )
    }
    conn.execute("DELETE FROM wtrf_attachments WHERE topic_id = ?", (rec["topic_id"],))
    conn.executemany(
        "INSERT OR IGNORE INTO wtrf_attachments "
        "(topic_id, filename, url, size_text, downloads, local_path) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (rec["topic_id"], a["filename"], a["url"], a["size_text"],
             a.get("downloads"), a.get("local_path") or prior_paths.get(a["url"]))
            for a in attachments
        ],
    )

    conn.execute("DELETE FROM wtrf_replies WHERE topic_id = ?", (rec["topic_id"],))
    conn.executemany(
        "INSERT OR REPLACE INTO wtrf_replies "
        "(topic_id, msg_id, reply_num, poster, poster_id, posted_at, posted_raw, "
        " modified_at, modified_raw, modified_by, body_text, body_html) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (rec["topic_id"], r["msg_id"], r["reply_num"], r["poster"], r["poster_id"],
             r["posted_at"], r["posted_raw"], r["modified_at"], r["modified_raw"],
             r["modified_by"], r["body_text"], r["body_html"])
            for r in (replies or [])
        ],
    )

    conn.execute("DELETE FROM wtrf_checksums WHERE topic_id = ?", (rec["topic_id"],))
    conn.executemany(
        "INSERT OR IGNORE INTO wtrf_checksums "
        "(topic_id, msg_id, algo, digest, filename, ordinal) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (rec["topic_id"], rec.get("first_msg_id"), c["algo"], c["digest"],
             c["filename"], c["ordinal"])
            for c in (checksums or [])
        ],
    )

    conn.execute("DELETE FROM wtrf_refs WHERE topic_id = ?", (rec["topic_id"],))
    conn.executemany(
        "INSERT OR IGNORE INTO wtrf_refs (topic_id, kind, ref_raw, lb_number) "
        "VALUES (?, ?, ?, ?)",
        [
            (rec["topic_id"], r["kind"], r["ref_raw"], r["lb_number"])
            for r in (refs or [])
        ],
    )
    conn.commit()


def get_crawl_state(conn: sqlite3.Connection, board_id: int) -> sqlite3.Row:
    """Return the resume state for a board, creating a fresh row if needed.

    Args:
        conn: Open archive connection.
        board_id: Board number.

    Returns:
        The ``wtrf_crawl_state`` row for this board.
    """
    conn.execute(
        "INSERT OR IGNORE INTO wtrf_crawl_state (board_id, next_offset, started_at) "
        "VALUES (?, 0, ?)",
        (board_id, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM wtrf_crawl_state WHERE board_id = ?", (board_id,)
    ).fetchone()


def save_crawl_state(conn: sqlite3.Connection, board_id: int, **fields) -> None:
    """Update resume-state columns for a board and commit immediately.

    Committing on every call is what makes an interrupted backfill resumable.

    Args:
        conn: Open archive connection.
        board_id: Board number.
        **fields: Column/value pairs to write.
    """
    if not fields:
        return
    fields["last_run_at"] = datetime.now().isoformat(timespec="seconds")
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE wtrf_crawl_state SET {assignments} WHERE board_id = ?",
        (*fields.values(), board_id),
    )
    conn.commit()


def _archive_topic(
    session: requests.Session,
    conn: sqlite3.Connection,
    rec: dict,
    throttle: Throttle,
    download: bool,
    max_reply_pages: int,
    progress: Progress | None = None,
) -> dict:
    """Fetch one topic (first post + replies + attachments) and store it.

    The caller is responsible for the crawl delay; this issues the topic
    request immediately.

    Args:
        session: Authenticated session.
        conn: Open archive connection.
        rec: List-level record from the board page.
        throttle: Shared rate limiter.
        download: Save attachment files to disk.
        max_reply_pages: Cap on topic pages walked for replies.
        progress: Optional live status line to narrate onto.

    Returns:
        The merged, stored topic record.

    Raises:
        RuntimeError: If the session has expired.
    """
    if progress:
        progress.update(f"topic {rec['topic_id']} · fetching")
    resp = throttle.get(session, rec["url"])
    if "action=login" in resp.url:
        raise RuntimeError("WTRF session expired while fetching topics")
    resp.raise_for_status()

    page = _parse_topic_page(resp.text)
    attachments = page.pop("attachments")
    replies = page.pop("replies")

    # Replies past the first page need extra requests (SMF pages at 15).
    expected = rec.get("replies") or 0
    page_size = len(replies) + 1 or MESSAGES_PER_PAGE
    pages_done = 1
    while len(replies) < expected and pages_done < max_reply_pages:
        start = page_size * pages_done
        if progress:
            progress.update(
                f"topic {rec['topic_id']} · replies {len(replies)}/{expected}"
            )
        nxt = throttle.get(
            session, f"{FORUM_BASE}/index.php?topic={rec['topic_id']}.{start}"
        )
        if "action=login" in nxt.url or not nxt.ok:
            break
        # On a later page every message is a reply, including the first one
        # on the page — so take the wrappers directly.
        soup = BeautifulSoup(nxt.text, "lxml")
        msgs = [
            m for m in (
                _parse_post_wrapper(w)
                for w in soup.find_all("div", class_="post_wrapper")
            ) if m
        ]
        known_ids = {r["msg_id"] for r in replies} | {page.get("first_msg_id")}
        extra = [m for m in msgs if m["msg_id"] not in known_ids]
        if not extra:
            break
        replies.extend(extra)
        pages_done += 1

    merged = {**rec, **{k: v for k, v in page.items() if v not in ("", None)}}
    merged["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    checksums = extract_checksums(merged.get("body_text", ""))
    refs = extract_refs(merged, [r["body_text"] for r in replies])

    if download:
        for att in attachments:
            if progress:
                progress.update(f"topic {rec['topic_id']} · attachment {att['filename'][:40]}")
            path = _download_attachment(
                session, att["url"], att["filename"],
                ATTACH_DIR / str(rec["topic_id"]), throttle,
            )
            att["local_path"] = str(path) if path else None

    _store(conn, merged, attachments, replies, checksums, refs)
    merged["attachments"] = attachments
    merged["replies_stored"] = replies
    merged["checksums"] = checksums
    merged["refs"] = refs
    emit = progress.write if progress else logger.info
    emit(
        "archived topic %s — %s (%d replies, %d checksums, %d refs)",
        rec["topic_id"], merged["title"][:50],
        len(replies), len(checksums), len(refs),
    )
    return merged


def fetch_board(
    board_id: int = DEFAULT_BOARD,
    limit: int = DEFAULT_LIMIT,
    delay: float = DEFAULT_DELAY,
    topic_delay: float = DEFAULT_TOPIC_DELAY,
    jitter: float = DEFAULT_JITTER,
    include_sticky: bool = False,
    download: bool = False,
    refetch: bool = False,
    max_reply_pages: int = DEFAULT_MAX_REPLY_PAGES,
    show_progress: bool = True,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Crawl the newest topics on a board and store them in the archive.

    Args:
        board_id: WTRF board number.
        limit: Number of topics to archive, newest first.
        delay: Minimum seconds between any two HTTP requests.
        topic_delay: Crawl delay — seconds to wait between topics.
        jitter: Fraction of each wait randomised (0.2 = ±20%).
        include_sticky: Also archive pinned topics.
        download: Save attachment files under ``data/wtrf_attachments/``.
        refetch: Re-fetch topics already present in the database.
        max_reply_pages: Maximum topic pages to walk per topic when collecting
            replies (1 = first page only).
        show_progress: Draw the live status line.
        db_path: Archive database path.

    Returns:
        The stored topic records, newest first.

    Raises:
        RuntimeError: If the keyring holds no WTRF credentials or login fails.
    """
    username, password = get_credentials(SERVICE_WTRF)
    if not username or not password:
        raise RuntimeError("No WTRF credentials in the keyring (service: %s)" % SERVICE_WTRF)
    session = _get_session(username, password)
    if session is None:
        raise RuntimeError("WTRF login failed — check the stored credentials")

    throttle = Throttle(min_interval=delay, topic_delay=topic_delay, jitter=jitter)
    progress = Progress(limit, enabled=show_progress)

    conn = open_db(db_path)
    try:
        progress.update("listing board", board=board_id)
        listed = _list_topics(session, board_id, limit, throttle, include_sticky)
        logger.info(
            "board %s: %d topic(s) listed (crawl delay %.0fs, request gap %.1fs, ±%.0f%%)",
            board_id, len(listed), topic_delay, delay, jitter * 100,
        )

        stored: list[dict] = []
        fetched_any = False
        skipped = 0
        for rec in listed:
            known = conn.execute(
                "SELECT 1 FROM wtrf_topics WHERE topic_id = ?", (rec["topic_id"],)
            ).fetchone()
            if known and not refetch:
                skipped += 1
                progress.write("skip topic %s (already archived)", rec["topic_id"])
                row = conn.execute(
                    "SELECT * FROM wtrf_topics WHERE topic_id = ?", (rec["topic_id"],)
                ).fetchone()
                stored.append(dict(row))
                progress.update(skipped=skipped)
                continue

            throttle.wait_topic(first=not fetched_any, progress=progress)
            fetched_any = True
            stored.append(_archive_topic(
                session, conn, rec, throttle, download, max_reply_pages, progress,
            ))
            progress.update(done=len([s for s in stored if "checksums" in s]),
                            skipped=skipped)
        return stored
    finally:
        progress.finish()
        conn.close()


def backfill_board(
    board_id: int = DEFAULT_BOARD,
    limit: int = DEFAULT_BACKFILL_LIMIT,
    delay: float = DEFAULT_DELAY,
    topic_delay: float = DEFAULT_TOPIC_DELAY,
    jitter: float = DEFAULT_JITTER,
    download: bool = False,
    max_reply_pages: int = DEFAULT_MAX_REPLY_PAGES,
    overlap_pages: int = 1,
    reset: bool = False,
    newest_first: bool = True,
    show_progress: bool = True,
    db_path: Path = DB_PATH,
) -> dict:
    """Walk a whole board page by page, resuming where the last run stopped.

    Every run starts with a *head pass* over the newest pages so anything
    posted since the last run is archived first; only then does the run spend
    its remaining budget continuing the backfill from the saved offset.

    Progress lives in ``wtrf_crawl_state`` and is committed after every topic,
    so an interrupted run (Ctrl-C, crash, session expiry) resumes without
    re-fetching what it already has. Topics already in the archive are skipped
    without a request, which also makes re-runs cheap when page offsets drift
    as new topics arrive.

    Args:
        board_id: Board number.
        limit: Maximum topics to archive in this run.
        delay: Minimum seconds between any two HTTP requests.
        topic_delay: Crawl delay between topics.
        jitter: Fraction of each wait randomised.
        download: Save attachment files to disk.
        max_reply_pages: Cap on topic pages walked for replies.
        overlap_pages: Board pages to rewind on resume, absorbing offset drift.
        reset: Restart the walk from the top of the board.
        newest_first: Archive new topics at the head of the board before
            continuing the backfill.
        show_progress: Draw the live status line.
        db_path: Archive database path.

    Returns:
        Summary dict: archived, new_at_head, skipped, pages, next_offset, finished.

    Raises:
        RuntimeError: If credentials are missing or login fails.
    """
    username, password = get_credentials(SERVICE_WTRF)
    if not username or not password:
        raise RuntimeError("No WTRF credentials in the keyring (service: %s)" % SERVICE_WTRF)
    session = _get_session(username, password)
    if session is None:
        raise RuntimeError("WTRF login failed — check the stored credentials")

    throttle = Throttle(min_interval=delay, topic_delay=topic_delay, jitter=jitter)
    conn = open_db(db_path)
    progress = Progress(limit, enabled=show_progress)
    archived = skipped = pages = head_new = 0
    finished = False
    fetched_any = False
    offset = 0

    def _walk(start_offset: int, head_pass: bool) -> bool:
        """Walk pages from ``start_offset``; return True if the board ended.

        Args:
            start_offset: SMF offset to start listing at.
            head_pass: True while catching up on newly posted topics — the walk
                stops at the first page holding nothing new, and the saved
                resume offset is left untouched.
        """
        nonlocal archived, skipped, pages, head_new, fetched_any, offset
        cursor = start_offset
        while archived < limit:
            progress.update(
                "listing page" + (" (newest)" if head_pass else ""),
                board=board_id, offset=cursor,
                page=cursor // TOPICS_PER_PAGE + 1, done=archived, skipped=skipped,
            )
            page, total_pages = _list_page(session, board_id, cursor, throttle)
            pages += 1
            if total_pages:
                progress.total_pages = total_pages
                if total_pages != state["total_pages"]:
                    save_crawl_state(conn, board_id, total_pages=total_pages)
            if not page:
                if not head_pass:
                    progress.write("board %s: no topics at offset %d — walk complete",
                                   board_id, cursor)
                    save_crawl_state(
                        conn, board_id, next_offset=cursor,
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                    )
                return True

            new_on_page = 0
            for rec in page:
                if rec["is_sticky"]:
                    continue          # pinned to every page; archive via `fetch`
                if conn.execute(
                    "SELECT 1 FROM wtrf_topics WHERE topic_id = ?", (rec["topic_id"],)
                ).fetchone():
                    skipped += 1
                    continue
                new_on_page += 1
                if archived >= limit:
                    break
                throttle.wait_topic(first=not fetched_any, progress=progress)
                fetched_any = True
                _archive_topic(session, conn, rec, throttle, download,
                               max_reply_pages, progress)
                archived += 1
                if head_pass:
                    head_new += 1
                else:
                    # Stay on this page until exhausted, so an interrupt here
                    # resumes on it and picks up the remaining topics.
                    save_crawl_state(conn, board_id, next_offset=cursor)
                progress.update(done=archived, skipped=skipped)

            if archived >= limit:
                if not head_pass:
                    save_crawl_state(conn, board_id, next_offset=cursor)
                    offset = cursor
                return False
            if head_pass and new_on_page == 0:
                return False          # caught up with the head of the board
            cursor += TOPICS_PER_PAGE
            if not head_pass:
                offset = cursor
                save_crawl_state(conn, board_id, next_offset=cursor)
        return False

    try:
        state = get_crawl_state(conn, board_id)
        resume_offset = 0 if reset else max(
            0, (state["next_offset"] or 0) - overlap_pages * TOPICS_PER_PAGE
        )
        offset = resume_offset
        if reset:
            save_crawl_state(conn, board_id, next_offset=0, finished_at=None,
                             started_at=datetime.now().isoformat(timespec="seconds"))
        logger.info(
            "backfill board %s: head pass %s, then resume at offset %d "
            "(limit %d topics, crawl delay %.0fs)",
            board_id, "on" if newest_first else "off", resume_offset, limit, topic_delay,
        )

        # Newest posts first: catch up on the head before spending the rest of
        # the budget further down the board.
        if newest_first and resume_offset > 0:
            _walk(0, head_pass=True)
            if head_new:
                progress.write("head pass: %d new topic(s) archived", head_new)
        if archived < limit:
            finished = _walk(resume_offset, head_pass=False)
    except KeyboardInterrupt:
        progress.finish()
        logger.warning("interrupted — progress saved, re-run to resume")
    finally:
        progress.finish()
        conn.close()

    logger.info(
        "backfill done: %d archived (%d new at head), %d already held, %d page(s) listed",
        archived, head_new, skipped, pages,
    )
    return {
        "archived": archived, "new_at_head": head_new, "skipped": skipped,
        "pages": pages, "next_offset": offset, "finished": finished,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_topics(conn: sqlite3.Connection, rows: list[sqlite3.Row], body_chars: int) -> None:
    """Print topic rows in the repo's one-line-per-record style.

    Args:
        conn: Open archive connection (used for attachment lookups).
        rows: Topic rows to display.
        body_chars: Body preview length; 0 prints no body.
    """
    for row in rows:
        atts = conn.execute(
            "SELECT filename, size_text, local_path FROM wtrf_attachments WHERE topic_id = ?",
            (row["topic_id"],),
        ).fetchall()
        counts = {
            name: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE topic_id = ?", (row["topic_id"],)
            ).fetchone()[0]
            for name, table in (
                ("rep", "wtrf_replies"), ("sum", "wtrf_checksums"), ("ref", "wtrf_refs")
            )
        }
        print(
            f"{row['topic_id']:>6}  {row['posted_at'] or row['posted_raw']:<19}  "
            f"{row['poster']:<14}  {row['title'][:60]:<60}  "
            f"[{row['subtitle'][:18]}]  {len(atts)} att  "
            f"{counts['rep']} rep  {counts['sum']} sum  {counts['ref']} ref"
        )
        for a in atts:
            mark = "saved" if a["local_path"] else "meta"
            print(f"        · {a['filename']} ({a['size_text']}, {mark})")
        if body_chars:
            preview = " ".join((row["body_text"] or "").split())[:body_chars]
            print(f"        {preview}")


def _cmd_fetch(args: argparse.Namespace) -> int:
    """Run the ``fetch`` subcommand."""
    try:
        stored = fetch_board(
            board_id=args.board, limit=args.limit, delay=args.delay,
            topic_delay=args.topic_delay, jitter=args.jitter,
            include_sticky=args.include_sticky, download=args.download,
            refetch=args.refetch, max_reply_pages=args.max_reply_pages,
            show_progress=args.show_progress, db_path=Path(args.db),
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    conn = open_db(Path(args.db))
    try:
        ids = [t["topic_id"] for t in stored]
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT * FROM wtrf_topics WHERE topic_id IN ({marks}) "
            "ORDER BY posted_at DESC, topic_id DESC", ids,
        ).fetchall() if ids else []
        _print_topics(conn, rows, args.body_chars)
    finally:
        conn.close()
    print(f"\n{len(stored)} topic(s) in {args.db}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Run the ``search`` subcommand (FTS5 over title/subtitle/poster/body)."""
    conn = open_db(Path(args.db))
    try:
        try:
            rows = conn.execute(
                "SELECT t.* FROM wtrf_topics_fts f JOIN wtrf_topics t ON t.topic_id = f.rowid "
                "WHERE wtrf_topics_fts MATCH ? ORDER BY rank LIMIT ?",
                (args.query, args.limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{args.query}%"
            rows = conn.execute(
                "SELECT * FROM wtrf_topics WHERE title LIKE ? OR subtitle LIKE ? "
                "OR body_text LIKE ? ORDER BY posted_at DESC LIMIT ?",
                (like, like, like, args.limit),
            ).fetchall()
        _print_topics(conn, rows, args.body_chars)
        print(f"\n{len(rows)} match(es)")
    finally:
        conn.close()
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    """Run the ``show`` subcommand — full stored record for one topic."""
    conn = open_db(Path(args.db))
    try:
        row = conn.execute(
            "SELECT * FROM wtrf_topics WHERE topic_id = ?", (args.topic_id,)
        ).fetchone()
        if row is None:
            print(f"topic {args.topic_id} not in archive", file=sys.stderr)
            return 1
        for key in ("topic_id", "title", "subtitle", "poster", "posted_at",
                    "posted_raw", "modified_at", "modified_raw", "modified_by",
                    "replies", "views", "url", "fetched_at"):
            print(f"{key:<12} {row[key]}")
        for a in conn.execute(
            "SELECT filename, size_text, downloads, local_path FROM wtrf_attachments "
            "WHERE topic_id = ?", (args.topic_id,)
        ):
            print(f"attachment   {a['filename']} ({a['size_text']}) -> {a['local_path'] or '—'}")

        refs = conn.execute(
            "SELECT kind, ref_raw FROM wtrf_refs WHERE topic_id = ? ORDER BY kind, ref_raw",
            (args.topic_id,),
        ).fetchall()
        for kind in ("self", "cross", "xref"):
            vals = [r["ref_raw"] for r in refs if r["kind"] == kind]
            if vals:
                print(f"{kind + ' refs':<12} {', '.join(vals)}")

        sums = conn.execute(
            "SELECT algo, digest, filename FROM wtrf_checksums WHERE topic_id = ? "
            "ORDER BY ordinal", (args.topic_id,),
        ).fetchall()
        print(f"{'checksums':<12} {len(sums)}")
        for s in sums:
            print(f"  {s['algo']}  {s['digest']}  {s['filename']}")

        print("-" * 70)
        print(row["body_text"])

        for r in conn.execute(
            "SELECT * FROM wtrf_replies WHERE topic_id = ? ORDER BY reply_num, msg_id",
            (args.topic_id,),
        ):
            print("-" * 70)
            edited = f"  [edited {r['modified_raw']}]" if r["modified_raw"] else ""
            print(f"Reply #{r['reply_num']} by {r['poster']} at "
                  f"{r['posted_at'] or r['posted_raw']}{edited}")
            print(r["body_text"])
    finally:
        conn.close()
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    """Run the ``list`` subcommand — newest archived topics."""
    conn = open_db(Path(args.db))
    try:
        rows = conn.execute(
            "SELECT * FROM wtrf_topics WHERE board_id = ? "
            "ORDER BY posted_at DESC, topic_id DESC LIMIT ?",
            (args.board, args.limit),
        ).fetchall()
        _print_topics(conn, rows, args.body_chars)
    finally:
        conn.close()
    return 0


def _cmd_backfill(args: argparse.Namespace) -> int:
    """Run the ``backfill`` subcommand."""
    try:
        summary = backfill_board(
            board_id=args.board, limit=args.limit, delay=args.delay,
            topic_delay=args.topic_delay, jitter=args.jitter,
            download=args.download, max_reply_pages=args.max_reply_pages,
            overlap_pages=args.overlap_pages, reset=args.reset,
            newest_first=args.newest_first, show_progress=args.show_progress,
            db_path=Path(args.db),
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"archived {summary['archived']} ({summary['new_at_head']} new at head)  "
        f"already held {summary['skipped']}  "
        f"pages {summary['pages']}  next offset {summary['next_offset']}"
        + ("  BOARD COMPLETE" if summary["finished"] else "")
    )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Run the ``status`` subcommand — coverage and resume position."""
    conn = open_db(Path(args.db))
    try:
        state = get_crawl_state(conn, args.board)
        held = conn.execute(
            "SELECT COUNT(*) FROM wtrf_topics WHERE board_id = ?", (args.board,)
        ).fetchone()[0]
        total = (state["total_pages"] or 0) * TOPICS_PER_PAGE or None
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("wtrf_replies", "wtrf_attachments", "wtrf_checksums", "wtrf_refs")
        }

        print(f"board          {args.board}")
        print(f"topics held    {held}" + (f" / ~{total} (~{held / total:.1%})" if total else ""))
        print(f"next offset    {state['next_offset']}"
              + (f" of ~{total}" if total else " (board size unknown — run backfill once)"))
        print(f"pages known    {state['total_pages'] or '—'}")
        print(f"last run       {state['last_run_at'] or '—'}")
        print(f"finished       {state['finished_at'] or 'no'}")
        for table, n in counts.items():
            print(f"{table:<14} {n}")

        if total and held < total:
            remaining = total - held
            for label, secs in (("30s", 30.0), ("10s", 10.0), ("5s", 5.0)):
                print(f"eta @ {label:<4}     {remaining * secs / 3600:.1f} h "
                      f"({remaining * secs / 86400:.1f} days)")
    finally:
        conn.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(
        description="Archive WTRF board topics into a searchable SQLite database.",
    )
    p.add_argument("--db", default=str(DB_PATH), help=f"archive DB (default: {DB_PATH})")
    p.add_argument("--body-chars", type=int, default=0,
                   help="body preview length in list output (0 = off)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="crawl the board newest-first and store topics")
    f.add_argument("--board", type=int, default=DEFAULT_BOARD)
    f.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    f.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                   help=f"minimum seconds between HTTP requests (default: {DEFAULT_DELAY})")
    f.add_argument("--topic-delay", type=float, default=DEFAULT_TOPIC_DELAY,
                   help=f"crawl delay between topics in seconds "
                        f"(default: {DEFAULT_TOPIC_DELAY:.0f}); 0 disables")
    f.add_argument("--jitter", type=float, default=DEFAULT_JITTER,
                   help=f"fraction of each wait randomised (default: {DEFAULT_JITTER})")
    f.add_argument("--include-sticky", action="store_true",
                   help="also archive pinned/announcement topics")
    f.add_argument("--download", action="store_true",
                   help=f"save attachment files under {ATTACH_DIR}")
    f.add_argument("--refetch", action="store_true",
                   help="re-fetch topics already in the archive")
    f.add_argument("--max-reply-pages", type=int, default=DEFAULT_MAX_REPLY_PAGES,
                   help="topic pages to walk per topic when collecting replies")
    f.add_argument("--no-progress", dest="show_progress", action="store_false",
                   help="suppress the live status line")
    f.set_defaults(func=_cmd_fetch)

    b = sub.add_parser("backfill", help="resumable whole-board crawl")
    b.add_argument("--board", type=int, default=DEFAULT_BOARD)
    b.add_argument("--limit", type=int, default=DEFAULT_BACKFILL_LIMIT,
                   help=f"topics to archive this run (default: {DEFAULT_BACKFILL_LIMIT})")
    b.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    b.add_argument("--topic-delay", type=float, default=DEFAULT_TOPIC_DELAY,
                   help=f"crawl delay between topics (default: {DEFAULT_TOPIC_DELAY:.0f}s)")
    b.add_argument("--jitter", type=float, default=DEFAULT_JITTER)
    b.add_argument("--download", action="store_true")
    b.add_argument("--max-reply-pages", type=int, default=DEFAULT_MAX_REPLY_PAGES)
    b.add_argument("--overlap-pages", type=int, default=1,
                   help="board pages to rewind on resume, absorbing offset drift")
    b.add_argument("--reset", action="store_true",
                   help="restart the walk from the top of the board")
    b.add_argument("--no-newest-first", dest="newest_first", action="store_false",
                   help="skip the head pass that archives newly posted topics first")
    b.add_argument("--no-progress", dest="show_progress", action="store_false",
                   help="suppress the live status line")
    b.set_defaults(func=_cmd_backfill)

    st = sub.add_parser("status", help="archive coverage and resume position")
    st.add_argument("--board", type=int, default=DEFAULT_BOARD)
    st.set_defaults(func=_cmd_status)

    s = sub.add_parser("search", help="full-text search the archive")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=_cmd_search)

    sh = sub.add_parser("show", help="print one archived topic in full")
    sh.add_argument("topic_id", type=int)
    sh.set_defaults(func=_cmd_show)

    ls = sub.add_parser("list", help="list archived topics, newest first")
    ls.add_argument("--board", type=int, default=DEFAULT_BOARD)
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=_cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
