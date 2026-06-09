"""Scraper for https://www.bobdylan.com — discovers show URLs from WordPress
sitemaps and scrapes full setlist data for each show page.

Public API:
    run_discover(db_path)      — fetch 3 sitemaps, upsert bobdylan_shows rows (URL + date only)
    run_scrape(db_path, force) — fetch each unscraped show page, populate venue/setlist
    run_update(db_path, force) — discover then scrape; idempotent, resumes after interruption
    get_status()               — current progress snapshot
    stop()                     — signal worker to stop after its current page
"""
from __future__ import annotations

import logging
import re
import threading
import time
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from backend.db import DB_PATH, get_connection
from backend.db_queue import get_write_queue, init_write_queue

_log = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA}
_SITEMAP_URLS = [
    "https://www.bobdylan.com/wp-sitemap-posts-date-1.xml",
    "https://www.bobdylan.com/wp-sitemap-posts-date-2.xml",
    "https://www.bobdylan.com/wp-sitemap-posts-date-3.xml",
]
_DATE_RE = re.compile(r"/date/(\d{4}-\d{2}-\d{2})-")
_PAGE_DELAY = 0.35  # seconds between show-page requests

_state: dict = {
    "status": "idle",   # idle | running | done | error
    "phase": "",        # discover | scrape
    "total": 0,
    "done": 0,
    "errors": 0,
    "skipped": 0,
    "current_url": None,
    "stop_requested": False,
    "message": "",
}
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """Return a snapshot of the current worker state."""
    with _state_lock:
        return dict(_state)


def stop() -> None:
    """Signal the active worker to stop after its current page."""
    with _state_lock:
        _state["stop_requested"] = True


def is_running() -> bool:
    with _state_lock:
        return _state["status"] == "running"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def _is_stop_requested() -> bool:
    with _state_lock:
        return _state["stop_requested"]


def _fetch(url: str, retries: int = 3, delay: float = 1.5) -> requests.Response | None:
    """GET *url* with browser UA, retry logic, and 429 back-off.

    Args:
        url: Full URL to fetch.
        retries: Max attempts before giving up.
        delay: Base seconds between retries (multiplied by attempt index).

    Returns:
        Response on success; None on 404 or exhausted retries.
    """
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 429:
                _log.warning("bobdylan_scraper: 429 on %s, sleeping 60s", url)
                time.sleep(60)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            _log.warning("bobdylan_scraper: fetch attempt %d/%d failed %s: %s",
                         attempt + 1, retries, url, exc)
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def fetch_sitemap_urls() -> list[tuple[str, str]]:
    """Fetch all date sitemaps and return a list of (date_str, bobdylan_url).

    date_str is YYYY-MM-DD extracted from the URL slug.  Requires 3 HTTP
    requests (one per sitemap).

    Returns:
        List of (date_str, url) pairs for every show page listed in the sitemaps.
    """
    results: list[tuple[str, str]] = []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for sitemap_url in _SITEMAP_URLS:
        time.sleep(3.0)  # polite gap between sitemap requests
        resp = _fetch(sitemap_url, retries=5, delay=3.0)
        if not resp:
            _log.error("bobdylan_scraper: failed to fetch sitemap %s", sitemap_url)
            continue
        try:
            root = ElementTree.fromstring(resp.content)
            for loc in root.findall(".//sm:loc", ns):
                url = (loc.text or "").strip()
                m = _DATE_RE.search(url)
                if m:
                    results.append((m.group(1), url))
        except ElementTree.ParseError as exc:
            _log.error("bobdylan_scraper: sitemap parse error %s: %s", sitemap_url, exc)
    return results


def parse_show_page(html: str) -> dict:
    """Parse a bobdylan.com /date/ page into structured setlist data.

    Args:
        html: Raw HTML content of a show page.

    Returns:
        Dict with keys: location (str), venue (str), notes (str),
        tracks (list of {name: str, song_url: str}).
        Returns empty dict if the setlist-detail block is absent.
    """
    soup = BeautifulSoup(html, "lxml")
    detail = soup.find(class_="setlist-detail")
    if not detail:
        return {}

    location_el = detail.find(class_="headline")
    venue_el = detail.find(class_="venue")
    notes_el = detail.find(class_="notes")

    tracks: list[dict] = []
    set_list = detail.find(class_="set-list")
    if set_list:
        for li in set_list.find_all("li"):
            a = li.find("a", class_="title")
            if a:
                tracks.append({
                    "name": a.get_text(strip=True),
                    "song_url": a.get("href", ""),
                })

    return {
        "location": location_el.get_text(strip=True) if location_el else "",
        "venue": venue_el.get_text(strip=True) if venue_el else "",
        "notes": notes_el.get_text(strip=True) if notes_el else "",
        "tracks": tracks,
    }


# ---------------------------------------------------------------------------
# Worker functions
# ---------------------------------------------------------------------------

def run_discover(db_path: str | None = None) -> int:
    """Fetch the 3 WordPress sitemaps and upsert bobdylan_shows (URL + date).

    This is fast — only 3 HTTP requests total.  Show pages are not fetched.
    Safe to re-run; existing rows are left unchanged (INSERT OR IGNORE).

    Args:
        db_path: Optional override for the SQLite database path.

    Returns:
        Number of new URL rows inserted (existing rows are skipped).
    """
    _set(
        status="running", phase="discover",
        total=0, done=0, errors=0, skipped=0,
        current_url=None, stop_requested=False,
        message="Fetching sitemaps…",
    )
    try:
        pairs = fetch_sitemap_urls()
        _set(total=len(pairs))
        _log.info("bobdylan_scraper: discovered %d show URLs from sitemaps", len(pairs))

        init_write_queue(str(db_path or DB_PATH))
        wq = get_write_queue()
        inserted = 0

        def _upsert(conn):
            nonlocal inserted
            for date_str, url in pairs:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO bobdylan_shows(bobdylan_url, date_str) VALUES (?, ?)",
                    (url, date_str),
                )
                inserted += cur.rowcount

        wq.execute(_upsert)
        _set(done=len(pairs), status="done", phase="discover",
             message=f"Discovered {len(pairs)} URLs, {inserted} new", current_url=None)
        return inserted

    except Exception as exc:
        _log.exception("bobdylan_scraper: discover failed")
        _set(status="error", message=str(exc))
        return 0


def run_scrape(db_path: str | None = None, force: bool = False) -> int:
    """Scrape individual show pages and populate venue/location/setlist data.

    By default skips shows where scraped_at IS NOT NULL.  With force=True,
    re-scrapes every show page and replaces stored data.

    Resumes safely after interruption: only unscraped rows are fetched.

    Args:
        db_path: Optional override for the SQLite database path.
        force: If True, re-scrape shows that already have data.

    Returns:
        Number of show pages successfully scraped.
    """
    _set(
        status="running", phase="scrape",
        total=0, done=0, errors=0, skipped=0,
        current_url=None, stop_requested=False,
        message="Loading pending shows…",
    )
    try:
        conn = get_connection(db_path)
        if force:
            rows = conn.execute(
                "SELECT bobdylan_url FROM bobdylan_shows ORDER BY date_str"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT bobdylan_url FROM bobdylan_shows WHERE scraped_at IS NULL ORDER BY date_str"
            ).fetchall()
        urls = [r[0] for r in rows]
        _set(total=len(urls))
        _log.info("bobdylan_scraper: %d show pages to scrape (force=%s)", len(urls), force)

        init_write_queue(str(db_path or DB_PATH))
        wq = get_write_queue()
        scraped = 0
        errors = 0

        for url in urls:
            if _is_stop_requested():
                _log.info("bobdylan_scraper: stop requested, halting at %s", url)
                break

            _set(current_url=url)
            resp = _fetch(url)
            if not resp:
                _log.warning("bobdylan_scraper: fetch failed for %s", url)
                errors += 1
                _set(errors=errors)
                continue

            data = parse_show_page(resp.text)
            if not data:
                _log.warning("bobdylan_scraper: no setlist-detail at %s", url)
                errors += 1
                _set(errors=errors)
                continue

            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            _url = url  # capture for lambda

            def _write(conn, _u=_url, _d=data, _n=now):
                conn.execute(
                    """UPDATE bobdylan_shows
                       SET venue=?, location=?, notes=?, scraped_at=?
                       WHERE bobdylan_url=?""",
                    (_d["venue"], _d["location"], _d["notes"], _n, _u),
                )
                conn.execute(
                    "DELETE FROM bobdylan_setlist WHERE bobdylan_url=?", (_u,)
                )
                conn.executemany(
                    """INSERT INTO bobdylan_setlist(bobdylan_url, position, track_name, song_url)
                       VALUES (?, ?, ?, ?)""",
                    [(_u, pos, t["name"], t["song_url"]) for pos, t in enumerate(_d["tracks"])],
                )

            wq.execute(_write)
            scraped += 1
            _set(done=scraped, errors=errors)
            time.sleep(_PAGE_DELAY)

        _set(
            status="done", phase="scrape",
            message=f"Scraped {scraped} shows ({errors} errors)",
            current_url=None,
        )
        return scraped

    except Exception as exc:
        _log.exception("bobdylan_scraper: scrape failed")
        _set(status="error", message=str(exc))
        return 0


def run_update(db_path: str | None = None, force: bool = False) -> None:
    """Discover show URLs then scrape unscraped pages.  Idempotent.

    Running this repeatedly is safe:
    - discover inserts only new URLs (INSERT OR IGNORE)
    - scrape only fetches pages where scraped_at IS NULL (unless force=True)

    Args:
        db_path: Optional override for the SQLite database path.
        force: If True, re-scrape all shows even if already scraped.
    """
    _log.info("bobdylan_scraper: run_update start (force=%s)", force)
    run_discover(db_path=db_path)
    if _is_stop_requested():
        _log.info("bobdylan_scraper: stop requested after discover phase")
        return
    run_scrape(db_path=db_path, force=force)
    _log.info("bobdylan_scraper: run_update complete")
