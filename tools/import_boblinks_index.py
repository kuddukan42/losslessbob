#!/usr/bin/env python3
"""CLI tool to crawl boblinks.com's tour-guide index into the ``boblinks_pages``
table (F7, GOLDEN_DOSSIER_FIX_PLAN.md).

``backend.dossier._boblinks_url`` links a show's Bob Links setlist page only when
this table has a row for that date -- probing during the plan's review showed the
old "guess a ``MMDDYYs.html`` URL" approach 404s for some real dates (031695s) and
hits for others that don't otherwise look special (050397s), so a crawled, verified
index is the only reliable source.

Crawl shape:
  1. ``guide.html`` lists the older per-tour index pages (``dates1.html`` ..
     ``dates37c.html``); ``dates.html`` itself is the current tour's index.
  2. Each index page lists per-show links, ``MMDDYYs.html`` (e.g.
     ``032910s.html`` = 2010-03-29).
  3. ``pre1995s.html`` is a dead end for this table -- it links out to
     bjorner.com pages, not boblinks per-show pages. Bob Links per-show
     coverage starts in fall 1995 (matches ``backend.dossier._BOBLINKS_FIRST_YEAR``),
     so a pre-1995 date is expected to have no row.
  4. Every per-show link is verified with its own GET (politely: sequential,
     one request at a time, ``--delay`` seconds apart, a real browser
     User-Agent) before being stored, since a listed link can still 404.

Usage::

    .venv/bin/python3 tools/import_boblinks_index.py --db /mnt/DATA0/tmp/boblinks/test.db
    .venv/bin/python3 tools/import_boblinks_index.py --db /mnt/DATA0/tmp/boblinks/test.db --limit 3

Never point ``--db`` at the live ``data/losslessbob.db`` -- this writes rows
while crawling and the tool refuses that path outright (see ``_refuse_live_db``).
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

log = logging.getLogger("import_boblinks_index")

_BASE = "https://boblinks.com/"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 LosslessBob-index-crawl/1.0")
_GUIDE_INDEX_RE = re.compile(r'HREF="(dates\d+c?\.html)"', re.IGNORECASE)
_SHOW_LINK_RE = re.compile(r'HREF="(\d{6}s\.html)"', re.IGNORECASE)
_TIMEOUT = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS boblinks_pages (
    date_iso  TEXT PRIMARY KEY,
    url       TEXT NOT NULL,
    found_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _fetch(url: str) -> str | None:
    """GET *url* with a browser UA; ``None`` on any non-2xx status or error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return resp.read().decode("utf-8", errors="replace")
            log.warning("GET %s -> HTTP %s", url, resp.status)
            return None
    except urllib.error.HTTPError as e:
        log.info("GET %s -> HTTP %s", url, e.code)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("GET %s -> %s", url, e)
        return None


def _date_iso_from_slug(slug: str) -> str | None:
    """``"032910s.html"`` -> ``"2010-03-29"``, or ``None`` for an invalid date.

    Bob Links' per-show slug is ``MMDDYY``. Coverage starts fall 1995 and runs
    to the present, so ``YY >= 95`` is 19YY and everything else is 20YY -- no
    date in that range collides the other way for a Dylan tour date.
    """
    m = re.match(r"^(\d{2})(\d{2})(\d{2})s\.html$", slug, re.IGNORECASE)
    if not m:
        return None
    mm, dd, yy = (int(g) for g in m.groups())
    year = 1900 + yy if yy >= 95 else 2000 + yy
    try:
        import datetime

        return datetime.date(year, mm, dd).isoformat()
    except ValueError:
        return None


def discover_index_pages(delay: float) -> list[str]:
    """Every tour-guide index page: ``dates.html`` (current) + ``guide.html``'s list."""
    pages = ["dates.html"]
    guide_html = _fetch(_BASE + "guide.html")
    time.sleep(delay)
    if guide_html:
        found = sorted(set(_GUIDE_INDEX_RE.findall(guide_html)))
        pages.extend(p for p in found if p not in pages)
    else:
        log.warning("guide.html fetch failed -- only crawling the current dates.html")
    return pages


def crawl(delay: float, limit: int | None = None) -> list[tuple[str, str]]:
    """Crawl every index page's show links, verify each, return ``(date_iso, url)`` rows.

    Args:
        delay: Seconds between each sequential HTTP request (politeness).
        limit: Cap on the number of *index* pages crawled, for a quick smoke test.

    Returns:
        One ``(date_iso, url)`` tuple per show link that both parses to a valid
        date and returns 200 on a direct GET.
    """
    index_pages = discover_index_pages(delay)
    if limit is not None:
        index_pages = index_pages[:limit]
    log.info("crawling %d index page(s): %s", len(index_pages), ", ".join(index_pages))

    slugs: dict[str, str] = {}  # slug -> index page it was found on (first wins)
    for page in index_pages:
        html = _fetch(_BASE + page)
        time.sleep(delay)
        if not html:
            continue
        for slug in _SHOW_LINK_RE.findall(html):
            slugs.setdefault(slug.lower(), page)

    log.info("%d distinct show link(s) found across index pages", len(slugs))

    rows: list[tuple[str, str]] = []
    for slug in sorted(slugs):
        date_iso = _date_iso_from_slug(slug)
        if date_iso is None:
            log.warning("skip %s: doesn't parse as a date", slug)
            continue
        url = _BASE + slug
        html = _fetch(url)
        time.sleep(delay)
        if html is None:
            log.info("skip %s (%s): page did not resolve", slug, date_iso)
            continue
        rows.append((date_iso, url))
    return rows


def _refuse_live_db(db_path: Path) -> None:
    """Hard stop if *db_path* looks like the live database (project rule, never write it)."""
    resolved = db_path.resolve()
    live = (_project_root / "data" / "losslessbob.db").resolve()
    if resolved == live:
        raise SystemExit(
            f"refusing to write {resolved} -- this tool never touches the live DB; "
            "point --db at a scratch copy (e.g. /mnt/DATA0/tmp/boblinks/test.db)"
        )


def store(db_path: Path, rows: list[tuple[str, str]]) -> None:
    """Write *rows* into ``boblinks_pages`` at *db_path* (creating the table if needed)."""
    _refuse_live_db(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO boblinks_pages (date_iso, url) VALUES (?, ?) "
            "ON CONFLICT(date_iso) DO UPDATE SET url = excluded.url",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=Path,
                     help="SQLite DB to write boblinks_pages into (never the live DB)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    ap.add_argument("--limit", type=int, default=None,
                     help="only crawl the first N index pages (smoke test)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                         format="%(levelname)s %(name)s: %(message)s")

    _refuse_live_db(args.db)
    rows = crawl(args.delay, args.limit)
    store(args.db, rows)
    print(f"boblinks_pages: {len(rows)} row(s) written to {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
