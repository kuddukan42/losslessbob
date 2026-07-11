"""Fetcher for Olof Björner's Bob Dylan pages (bobserve.com/olof/) — mirrors
Still On The Road session pages and Yearly Chronicles verbatim (raw bytes, no
re-encoding) into data/olof/pages/ for offline parsing.

Two decoupled corpora (see instructions/FABLE_OLOF_FILES.md §1-§3):
    dsn       — DSN<nnnnn> *.htm session/event pages, linked from still.htm
                (one per tour/session block, 1956-2021).
    chronicle — per-year Yearly Chronicle pages linked from chronologies.htm:
                either a single direct page (1960-1989, some later years) or
                a TOC page (1990-2012) that itself links to body-part +
                appendix pages, discovered by fetching the TOC page and
                re-parsing its links.

Public API:
    run_fetch(corpus, limit, refresh, dry_run, db_path, pages_dir) — the crawl

CLI:
    .venv/bin/python3 -m backend.olof_fetcher [--corpus dsn|chronicle|all]
        [--limit N] [--refresh] [--dry-run]

Schema: olof_pages (see db.py). Upsert on filename.

Cloudflare fronts bobserve.com and 403s non-browser User-Agents (verified) —
_HEADERS below is required, not optional. The site updates only a few times
a year so this fetcher is meant to be run manually, never scheduled.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from backend.db import get_connection, init_db
from backend.paths import DATA_DIR

_log = logging.getLogger(__name__)

BASE_URL = "https://www.bobserve.com/olof/"
STILL_INDEX = "still.htm"
CHRON_INDEX = "chronologies.htm"
PAGES_DIR = DATA_DIR / "olof" / "pages"

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA}
_REQUEST_DELAY = 2.0   # seconds between requests (spec §7 risk: Cloudflare)
_PROGRESS_EVERY = 20   # log an INFO progress line every N fetched pages

_DSN_HREF_RE = re.compile(r"^DSN\d+.*\.htm$", re.IGNORECASE)
_YEAR4_TOC_RE = re.compile(r"^(?P<y>(?:19|20)\d{2})\s?0\.htm$", re.IGNORECASE)
_YEAR4_PAGE_RE = re.compile(r"^(?P<y>(?:19|20)\d{2})\s.+\.htm$", re.IGNORECASE)
_YEAR2_TOC_RE = re.compile(r"^(?P<y>\d{2})\s?0\.htm$", re.IGNORECASE)
_YEAR2_PAGE_RE = re.compile(r"^(?P<y>\d{2})\.htm$", re.IGNORECASE)


@dataclass
class PageTask:
    """One page to mirror: a still.htm DSN entry or a chronicle page."""

    filename: str                # decoded, original spacing/case preserved
    url: str                     # fully-qualified source URL
    corpus: str                  # 'dsn' | 'chronicle'
    segment_title: str = ""
    year: int | None = None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _page_url(filename: str) -> str:
    """Build the fully-qualified, URL-encoded source URL for *filename*."""
    return BASE_URL + urllib.parse.quote(filename)


def _fetch(url: str, retries: int = 3) -> requests.Response | None:
    """GET *url* with a browser User-Agent (Cloudflare 403s default UAs).

    Args:
        url: Fully-qualified URL to fetch.
        retries: Max attempts before giving up.

    Returns:
        Response on success (2xx/3xx), or None on 404 or exhausted retries.
    """
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 429:
                _log.warning("olof_fetcher: 429 on %s, sleeping 30s", url)
                time.sleep(30)
                continue
            if resp.status_code == 404:
                _log.warning("olof_fetcher: 404 for %s", url)
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            _log.warning("olof_fetcher: fetch attempt %d/%d failed %s: %s",
                         attempt + 1, retries, url, exc)
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    return None


def _load(filename: str, url: str, pages_dir: Path, refresh: bool, persist: bool) -> bytes | None:
    """Return raw bytes for *filename*, from disk if cached, else over the network.

    Args:
        filename: Decoded on-disk filename.
        url: Fully-qualified source URL, used only on a cache miss.
        pages_dir: Directory pages are mirrored into.
        refresh: If True, ignore any cached copy and re-fetch.
        persist: If True, a network fetch is written to disk verbatim. If
            False (--dry-run discovery), fetched bytes are used transiently
            to keep discovering links and are never written — the run stays
            side-effect free.

    Returns:
        Raw bytes, or None if a network fetch was required and failed.
    """
    path = pages_dir / filename
    if path.exists() and not refresh:
        return path.read_bytes()
    resp = _fetch(url)
    if resp is None:
        return None
    content = resp.content
    if persist:
        pages_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    time.sleep(_REQUEST_DELAY)
    return content


# ---------------------------------------------------------------------------
# Link extraction (offline-safe — operates on already-fetched bytes)
# ---------------------------------------------------------------------------

def _extract_dsn_links(html_bytes: bytes) -> list[PageTask]:
    """Extract DSN session-page links from a fetched still.htm.

    Args:
        html_bytes: Raw bytes of still.htm (windows-1252 per spec §2 — decoded
            here only for parsing; the mirrored copy on disk stays untouched).

    Returns:
        One PageTask per unique DSN<nnnnn> *.htm href, in document order,
        with segment_title taken from the link's anchor text.
    """
    text = html_bytes.decode("windows-1252", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    seen: dict[str, PageTask] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _DSN_HREF_RE.match(href):
            continue
        filename = urllib.parse.unquote(href)
        if filename in seen:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        seen[filename] = PageTask(filename, _page_url(filename), "dsn", title)
    return list(seen.values())


def _classify_year_link(filename: str) -> tuple[int, bool] | tuple[None, None]:
    """Classify a chronologies.htm-linked filename by year and TOC-ness.

    Naming conventions observed across ~25 years of Word exports (verified
    against data/olof/samples/chronologies.html):
        NN.htm            -- single direct page, 1960-1989 (e.g. '60.htm')
        NN 0.htm / NN0.htm -- TOC page, 1990-1999 ('90 0.htm', '950.htm')
        YYYY 0.htm        -- TOC page, 2000-2012 ('2002 0.htm')
        YYYY <title>.htm  -- single direct page, some later years
                             ('2016 A Wonderful Answer.htm')

    Args:
        filename: Decoded href from chronologies.htm.

    Returns:
        (year, is_toc) — is_toc True means the page must be fetched and its
        own links re-parsed for body/appendix parts (§3); False means it's a
        standalone single-page chronicle. (None, None) if *filename* isn't a
        recognizable year page (site nav/essay links — out of scope).
    """
    for rx, is_toc, offset in (
        (_YEAR4_TOC_RE, True, 0),
        (_YEAR4_PAGE_RE, False, 0),
        (_YEAR2_TOC_RE, True, 1900),
        (_YEAR2_PAGE_RE, False, 1900),
    ):
        m = rx.match(filename)
        if m:
            return int(m.group("y")) + offset, is_toc
    return None, None


def _extract_chronicle_index_links(html_bytes: bytes) -> list[tuple[str, int, bool]]:
    """Extract year-chronicle links from a fetched chronologies.htm.

    Args:
        html_bytes: Raw bytes of chronologies.htm.

    Returns:
        List of (filename, year, is_toc) tuples, in document order. Non-year
        nav/essay links (update log, index, themed essays) and non-.htm
        assets are skipped.
    """
    text = html_bytes.decode("windows-1252", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    seen: dict[str, tuple[int, bool]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#", 1)[0]
        if not href or href.lower().startswith(("http://", "https://")):
            continue
        filename = urllib.parse.unquote(href)
        if "/" in filename or not filename.lower().endswith(".htm"):
            continue
        year, is_toc = _classify_year_link(filename)
        if year is None or filename in seen:
            continue
        seen[filename] = (year, is_toc)
    return [(fn, y, toc) for fn, (y, toc) in seen.items()]


def _extract_chronicle_body_links(html_bytes: bytes, toc_filename: str) -> list[str]:
    """Extract body/appendix page links from a fetched year TOC page.

    Excludes DSN cross-references (fetched separately under the dsn corpus),
    Word support paths (*-filer/*), PDFs, external links, and the breadcrumb
    back-links to chronologies.htm / the TOC page itself.

    Args:
        html_bytes: Raw bytes of the fetched TOC page (e.g. '2002 0.htm').
        toc_filename: The TOC page's own decoded filename, excluded from
            the result if it happens to link to itself.

    Returns:
        Unique filenames (decoded, #fragment stripped), in document order.
    """
    text = html_bytes.decode("windows-1252", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#", 1)[0]
        if not href or href.lower().startswith(("http://", "https://")):
            continue
        filename = urllib.parse.unquote(href)
        if "/" in filename or "-filer" in filename.lower():
            continue
        if not filename.lower().endswith(".htm"):
            continue
        if filename.lower() == CHRON_INDEX.lower() or filename == toc_filename:
            continue
        if _DSN_HREF_RE.match(filename):
            continue
        seen.setdefault(filename, None)
    return list(seen.keys())


# ---------------------------------------------------------------------------
# Discovery — builds the full task list from the index/TOC pages
# ---------------------------------------------------------------------------

def _discover(corpus: str, pages_dir: Path, refresh: bool, persist: bool) -> list[PageTask]:
    """Walk the index pages and return the full ordered list of pages to mirror.

    Always loads still.htm and/or chronologies.htm plus, for the chronicle
    corpus, every year TOC page — this is the network footprint --dry-run is
    scoped to ("no network beyond the index pages"). Nothing beyond that is
    fetched here; the caller decides whether to actually mirror the
    discovered DSN/body/appendix pages.

    Args:
        corpus: 'dsn' | 'chronicle' | 'all'.
        pages_dir: Directory pages are mirrored into (and read cache from).
        refresh: Passed through to _load for the index/TOC pages themselves.
        persist: Passed through to _load — False under --dry-run.

    Returns:
        Ordered list of PageTask: for each corpus, its index page first,
        then discovered content pages (chronicle TOC pages are followed
        immediately by their own discovered body/appendix pages).
    """
    tasks: list[PageTask] = []

    if corpus in ("dsn", "all"):
        still_bytes = _load(STILL_INDEX, _page_url(STILL_INDEX), pages_dir, refresh, persist)
        if still_bytes is None:
            _log.error("olof_fetcher: could not fetch %s — dsn corpus skipped", STILL_INDEX)
        else:
            tasks.append(PageTask(STILL_INDEX, _page_url(STILL_INDEX), "dsn",
                                   "Still On The Road Index Page"))
            dsn_links = _extract_dsn_links(still_bytes)
            tasks.extend(dsn_links)
            _log.info("olof_fetcher: %s -> %d DSN session links", STILL_INDEX, len(dsn_links))

    if corpus in ("chronicle", "all"):
        chron_bytes = _load(CHRON_INDEX, _page_url(CHRON_INDEX), pages_dir, refresh, persist)
        if chron_bytes is None:
            _log.error("olof_fetcher: could not fetch %s — chronicle corpus skipped", CHRON_INDEX)
        else:
            tasks.append(PageTask(CHRON_INDEX, _page_url(CHRON_INDEX), "chronicle",
                                   "The Yearly Chronologies"))
            year_links = _extract_chronicle_index_links(chron_bytes)
            _log.info("olof_fetcher: %s -> %d year entries", CHRON_INDEX, len(year_links))
            for filename, year, is_toc in year_links:
                title = f"Bob Dylan {year}"
                tasks.append(PageTask(filename, _page_url(filename), "chronicle", title, year))
                if not is_toc:
                    continue
                toc_bytes = _load(filename, _page_url(filename), pages_dir, refresh, persist)
                if toc_bytes is None:
                    _log.error("olof_fetcher: could not fetch TOC %s — %d chronicle body/"
                               "appendix pages not discovered", filename, year)
                    continue
                body_links = _extract_chronicle_body_links(toc_bytes, filename)
                for body_filename in body_links:
                    tasks.append(PageTask(body_filename, _page_url(body_filename),
                                           "chronicle", title, year))

    return tasks


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _upsert_page(conn, task: PageTask, content: bytes, fetched_at: str | None) -> None:
    """Insert or replace one olof_pages row for a just-mirrored page.

    Args:
        conn: SQLite connection scoped to the target db_path (see run_fetch —
            written to directly, not via the shared write-queue singleton,
            per BUG-246: this crawler always knows its own db_path and must
            not risk a first-caller-wins queue bound elsewhere).
        task: The PageTask describing this page.
        content: Raw bytes as saved to disk (hashed here, not re-read).
        fetched_at: ISO-ish local timestamp; None reuses any existing value
            (backfill path — the file predates this crawl run).
    """
    sha256 = hashlib.sha256(content).hexdigest()
    if fetched_at is None:
        row = conn.execute(
            "SELECT fetched_at FROM olof_pages WHERE filename = ?", (task.filename,)
        ).fetchone()
        fetched_at = row[0] if row and row[0] else time.strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        """INSERT INTO olof_pages (filename, url, corpus, segment_title, year, sha256, fetched_at)
           VALUES (:filename, :url, :corpus, :segment_title, :year, :sha256, :fetched_at)
           ON CONFLICT(filename) DO UPDATE SET
               url=excluded.url, corpus=excluded.corpus,
               segment_title=excluded.segment_title, year=excluded.year,
               sha256=excluded.sha256, fetched_at=excluded.fetched_at""",
        {
            "filename": task.filename, "url": task.url, "corpus": task.corpus,
            "segment_title": task.segment_title, "year": task.year,
            "sha256": sha256, "fetched_at": fetched_at,
        },
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_fetch(
    corpus: str = "all",
    limit: int | None = None,
    refresh: bool = False,
    dry_run: bool = False,
    db_path: str | None = None,
    pages_dir: Path | None = None,
) -> dict:
    """Mirror Olof Björner's DSN session pages and/or Yearly Chronicles.

    Two-phase: discovery (see _discover) builds the full task list, then
    each discovered page is fetched and saved verbatim, skipping ones
    already on disk unless refresh=True. Sequential, >=2s between requests
    (Cloudflare — spec §7), resume-safe.

    Args:
        corpus: 'dsn' | 'chronicle' | 'all'.
        limit: Cap the number of pages actually mirrored (testing). Applied
            after discovery, in task order (each corpus's index page first).
        refresh: Re-fetch and overwrite pages already on disk.
        dry_run: Run discovery only; log the plan and return counts without
            touching disk or the database, and without fetching anything
            beyond the index/TOC pages needed to build the plan.
        db_path: Optional DB path override.
        pages_dir: Optional override of the mirror directory (tests).

    Returns:
        Summary dict: {"planned": N, "fetched": N, "skipped": N, "errors": N,
        "by_corpus": {"dsn": N, "chronicle": N}}.
    """
    if corpus not in ("dsn", "chronicle", "all"):
        raise ValueError(f"corpus must be 'dsn', 'chronicle', or 'all', got {corpus!r}")

    resolved_pages_dir = pages_dir or PAGES_DIR
    tasks = _discover(corpus, resolved_pages_dir, refresh, persist=not dry_run)

    by_corpus: dict[str, int] = {}
    for t in tasks:
        by_corpus[t.corpus] = by_corpus.get(t.corpus, 0) + 1

    if dry_run:
        for t in tasks:
            _log.debug("olof_fetcher: [dry-run] would fetch %s (%s)", t.filename, t.corpus)
        _log.info("olof_fetcher: dry-run — %d pages planned (%s)", len(tasks),
                   ", ".join(f"{k}={v}" for k, v in sorted(by_corpus.items())))
        return {"planned": len(tasks), "fetched": 0, "skipped": 0, "errors": 0,
                "by_corpus": by_corpus}

    if limit is not None:
        tasks = tasks[:limit]

    init_db(db_path)
    conn = get_connection(db_path)

    fetched = skipped = errors = 0
    for task in tasks:
        path = resolved_pages_dir / task.filename
        already_recorded = conn.execute(
            "SELECT 1 FROM olof_pages WHERE filename = ?", (task.filename,)
        ).fetchone() is not None

        if path.exists() and not refresh:
            if already_recorded:
                skipped += 1
                _log.debug("olof_fetcher: skip (already fetched) %s", task.filename)
                continue
            content = path.read_bytes()
            _upsert_page(conn, task, content, fetched_at=None)
            skipped += 1
            _log.debug("olof_fetcher: backfilled DB row for existing file %s", task.filename)
            continue

        resp = _fetch(task.url)
        if resp is None:
            errors += 1
            _log.error("olof_fetcher: failed to fetch %s", task.url)
            continue
        content = resp.content
        resolved_pages_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        _upsert_page(conn, task, content, fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        fetched += 1
        if fetched % _PROGRESS_EVERY == 0:
            _log.info("olof_fetcher: %d/%d fetched (%d skipped, %d errors)",
                       fetched, len(tasks), skipped, errors)
        time.sleep(_REQUEST_DELAY)

    _log.info("olof_fetcher: done — %d fetched, %d skipped, %d errors, %d planned (%s)",
               fetched, skipped, errors, len(tasks),
               ", ".join(f"{k}={v}" for k, v in sorted(by_corpus.items())))
    return {"planned": len(tasks), "fetched": fetched, "skipped": skipped,
            "errors": errors, "by_corpus": by_corpus}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror Olof Björner's Still On The Road + Yearly Chronicles pages."
    )
    parser.add_argument("--corpus", choices=("dsn", "chronicle", "all"), default="all",
                         help="Which corpus to fetch (default: all).")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap the number of pages mirrored (testing).")
    parser.add_argument("--refresh", action="store_true",
                         help="Re-fetch pages already on disk.")
    parser.add_argument("--dry-run", action="store_true",
                         help="List what would be fetched; no mirroring, no network "
                              "beyond the index pages.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    _args = _parse_args()
    _summary = run_fetch(
        corpus=_args.corpus, limit=_args.limit,
        refresh=_args.refresh, dry_run=_args.dry_run,
    )
    _log.info("olof_fetcher: summary %s", _summary)
