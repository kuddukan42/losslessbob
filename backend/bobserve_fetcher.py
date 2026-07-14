"""Fetcher for bobserve.com's post-2021 setlist database — mirrors individual
show pages (bobserve.com/setlist?event=<id>) into data/olof/bobserve_pages/
for offline parsing by backend/bobserve_parser.py.

Background (TODO-228): the DSN corpus (backend/olof_fetcher.py) is Olof
Björner's authoritative setlist source only through 2021. TODO-228 originally
assumed 2022+ coverage would come from the Yearly Chronicle PDFs, but those
turned out to contain no per-show setlists at all (calendar diary + a bare
tour itinerary table, confirmed by extracting the 2022/2023 PDFs directly).
bobserve.com — Olof's own current site — instead publishes a full setlist
database with a page per show at /setlist?event=<id>, confirmed to carry real
per-song setlists (with cover-song credits) for 2022+ shows. This module
supersedes the PDF approach for setlist data; the itinerary-only PDF path was
not built.

Event query ids are NOT assigned chronologically (confirmed: id 4000 maps to
a 2004 show, id 3950 to a 2014 show), so individual ids can't be discovered
by walking a range or binary-searching by date. bobserve.com/eventsperiod?
period=<year> is the reliable index: it lists every show that year as an
`<a href=".../setlist?event=N">YYYY-MM-DD</a>` link, in chronological order.
Crawl is therefore two-step per year: fetch the period index, extract every
linked event id, then fetch each event page once (mirrored verbatim, skipped
on subsequent runs unless --refresh).

Public API:
    run_fetch(start_year, end_year, limit, refresh, dry_run, db_path, pages_dir)

CLI:
    .venv/bin/python3 -m backend.bobserve_fetcher [--start-year N] [--end-year N]
        [--limit N] [--refresh] [--dry-run]

Schema: olof_pages (corpus='bobserve'), shared with the DSN/chronicle
corpora. Upsert on filename.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import logging
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from backend.db import get_connection, init_db
from backend.olof_fetcher import _REQUEST_DELAY, _fetch
from backend.paths import DATA_DIR

_log = logging.getLogger(__name__)

BASE_URL = "https://bobserve.com/"
PAGES_DIR = DATA_DIR / "olof" / "bobserve_pages"

# DSN (Still On The Road) covers 1956-2021 (see module docstring) — bobserve.com's
# own setlist database is the only source consulted for 2022+ shows.
DEFAULT_START_YEAR = 2022
_PROGRESS_EVERY = 20

_EVENT_LINK_RE = re.compile(r"(?:https://bobserve\.com)?/setlist\?event=(\d+)$")


def _period_url(year: int) -> str:
    """Build the eventsperiod index URL for *year*."""
    return f"{BASE_URL}eventsperiod?period={year}"


def _event_url(event_id: int) -> str:
    """Build the fully-qualified setlist page URL for *event_id*."""
    return f"{BASE_URL}setlist?event={event_id}"


def _filename(event_id: int) -> str:
    """olof_pages.filename key for a mirrored bobserve event page."""
    return f"bobserve_event_{event_id}.html"


def _extract_year_event_ids(html_bytes: bytes) -> list[tuple[int, str]]:
    """Extract every distinct setlist event id linked from an eventsperiod page.

    Args:
        html_bytes: Raw bytes of a fetched eventsperiod?period=YYYY page
            (UTF-8, unlike the windows-1252 DSN/chronicle corpora — this is
            a current React/Flux-rendered page, not a legacy Word export).

    Returns:
        (event_id, date_str) tuples in document order (chronological), one
        per unique event id — date_str is the index page's own link text
        (e.g. '2023-11-16'), kept only as a human-readable olof_pages hint;
        the authoritative date is re-derived from each event page itself.
    """
    text = html_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    seen: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        m = _EVENT_LINK_RE.match(a["href"].strip())
        if not m:
            continue
        event_id = int(m.group(1))
        if event_id in seen:
            continue
        seen[event_id] = " ".join(a.get_text(" ", strip=True).split())
    return list(seen.items())


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _upsert_page(conn, event_id: int, filename: str, content: bytes,
                  fetched_at: str | None, year: int | None, segment_title: str) -> None:
    """Insert or replace one olof_pages row for a just-mirrored bobserve page.

    Args:
        conn: SQLite connection scoped to the target db_path — written to
            directly, not via the shared write-queue singleton, per BUG-246
            (this crawler always knows its own db_path, matching the
            existing olof_fetcher/olof_chronicle_parser convention).
        event_id: bobserve's own numeric event id (its `?event=` value).
        filename: olof_pages.filename key.
        content: Raw bytes as saved to disk (hashed here, not re-read).
        fetched_at: ISO-ish local timestamp; None reuses any existing value
            (backfill path — the file predates this crawl run).
        year: olof_pages.year — the eventsperiod year this id was
            discovered under.
        segment_title: The index page's date-string link text, for a
            human-readable olof_pages label.
    """
    sha256 = hashlib.sha256(content).hexdigest()
    if fetched_at is None:
        row = conn.execute(
            "SELECT fetched_at FROM olof_pages WHERE filename = ?", (filename,)
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
            "filename": filename, "url": _event_url(event_id), "corpus": "bobserve",
            "segment_title": segment_title, "year": year, "sha256": sha256,
            "fetched_at": fetched_at,
        },
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_fetch(
    start_year: int = DEFAULT_START_YEAR,
    end_year: int | None = None,
    limit: int | None = None,
    refresh: bool = False,
    dry_run: bool = False,
    db_path: str | None = None,
    pages_dir: Path | None = None,
) -> dict:
    """Mirror bobserve.com setlist pages for *start_year*..*end_year*.

    Two-phase per year: fetch the eventsperiod index, then mirror each
    discovered event page, skipping ones already on disk unless
    refresh=True. Sequential, >=2s between requests (same Cloudflare
    politeness rule as backend/olof_fetcher.py), resume-safe.

    Args:
        start_year: First year to crawl (default 2022, the year after DSN's
            2021 cutoff — see module docstring).
        end_year: Last year to crawl, inclusive. Defaults to the current
            calendar year.
        limit: Cap the number of event pages actually mirrored (testing).
            Applied after all years' ids are discovered, in discovery order.
        refresh: Re-fetch and overwrite pages already on disk.
        dry_run: Discover event ids per year only; no event-page fetches,
            no disk/DB writes.
        db_path: Optional DB path override.
        pages_dir: Optional override of the mirror directory (tests).

    Returns:
        Summary dict: {"years": [...], "planned": N, "fetched": N,
        "skipped": N, "errors": N}.
    """
    resolved_pages_dir = pages_dir or PAGES_DIR
    end_year = end_year if end_year is not None else datetime.date.today().year
    if end_year < start_year:
        raise ValueError(f"end_year ({end_year}) must be >= start_year ({start_year})")

    id_year: dict[int, int] = {}
    id_title: dict[int, str] = {}
    ordered_ids: list[int] = []
    years_crawled: list[int] = []

    for year in range(start_year, end_year + 1):
        resp = _fetch(_period_url(year))
        if resp is None:
            _log.error("bobserve_fetcher: could not fetch eventsperiod for %d", year)
            continue
        years_crawled.append(year)
        pairs = _extract_year_event_ids(resp.content)
        _log.info("bobserve_fetcher: eventsperiod %d -> %d event ids", year, len(pairs))
        for event_id, date_hint in pairs:
            if event_id not in id_year:
                id_year[event_id] = year
                id_title[event_id] = date_hint
                ordered_ids.append(event_id)
        time.sleep(_REQUEST_DELAY)

    if dry_run:
        _log.info("bobserve_fetcher: dry-run — %d event ids planned across years %s",
                   len(ordered_ids), years_crawled)
        return {"years": years_crawled, "planned": len(ordered_ids), "fetched": 0,
                "skipped": 0, "errors": 0}

    if limit is not None:
        ordered_ids = ordered_ids[:limit]

    init_db(db_path)
    conn = get_connection(db_path)

    fetched = skipped = errors = 0
    for event_id in ordered_ids:
        filename = _filename(event_id)
        path = resolved_pages_dir / filename
        already_recorded = conn.execute(
            "SELECT 1 FROM olof_pages WHERE filename = ?", (filename,)
        ).fetchone() is not None

        if path.exists() and not refresh:
            if already_recorded:
                skipped += 1
                _log.debug("bobserve_fetcher: skip (already fetched) event %d", event_id)
                continue
            content = path.read_bytes()
            _upsert_page(conn, event_id, filename, content, fetched_at=None,
                         year=id_year[event_id], segment_title=id_title[event_id])
            skipped += 1
            _log.debug("bobserve_fetcher: backfilled DB row for existing event %d", event_id)
            continue

        resp = _fetch(_event_url(event_id))
        if resp is None:
            errors += 1
            _log.error("bobserve_fetcher: failed to fetch event %d", event_id)
            continue
        content = resp.content
        resolved_pages_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        _upsert_page(conn, event_id, filename, content,
                     fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                     year=id_year[event_id], segment_title=id_title[event_id])
        fetched += 1
        if fetched % _PROGRESS_EVERY == 0:
            _log.info("bobserve_fetcher: %d/%d fetched (%d skipped, %d errors)",
                       fetched, len(ordered_ids), skipped, errors)
        time.sleep(_REQUEST_DELAY)

    _log.info("bobserve_fetcher: done — %d fetched, %d skipped, %d errors, %d planned "
               "(years %s)", fetched, skipped, errors, len(ordered_ids), years_crawled)
    return {"years": years_crawled, "planned": len(ordered_ids), "fetched": fetched,
            "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror bobserve.com setlist pages for shows past DSN's 2021 cutoff."
    )
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR,
                         help=f"First year to crawl (default {DEFAULT_START_YEAR}).")
    parser.add_argument("--end-year", type=int, default=None,
                         help="Last year to crawl, inclusive (default: current year).")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap the number of event pages mirrored (testing).")
    parser.add_argument("--refresh", action="store_true",
                         help="Re-fetch pages already on disk.")
    parser.add_argument("--dry-run", action="store_true",
                         help="List what would be fetched; no mirroring, no network "
                              "beyond the eventsperiod index pages.")
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
        start_year=_args.start_year, end_year=_args.end_year, limit=_args.limit,
        refresh=_args.refresh, dry_run=_args.dry_run,
    )
    _log.info("bobserve_fetcher: summary %s", _summary)
