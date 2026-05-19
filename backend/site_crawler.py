"""Full-domain site crawler for losslessbob.wonderingwhattochoose.com.

Produces a complete offline mirror under ``data/site/`` whose relative links
work in a regular browser via ``file://``.  Uses ``If-Modified-Since`` for
efficient incremental updates — unchanged pages return HTTP 304 and cost only
one small request each.

Entry point: :func:`crawl`.
Status polling: :func:`get_crawler_status`.
Stop request: :func:`stop_crawler`.
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

from backend.db import (
    DB_PATH,
    upsert_inventory,
    get_downloaded_urls,
    get_pending_urls,
    create_scrape_session,
    finish_scrape_session,
)
from backend.html_utils import rewrite_links
from backend.paths import SITE_DIR

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL    = "http://www.losslessbob.wonderingwhattochoose.com"
BASE_DOMAIN = "www.losslessbob.wonderingwhattochoose.com"

# Real site entry point.  The domain root (/) serves a DreamHost placeholder.
SITE_HOME_URL = BASE_URL + "/LosslessBob.html"

# Extra seeds queued on every crawl as a safety net in case the home page
# restructures or doesn't link directly to the index pages.
SEED_URLS = [
    BASE_URL + "/bynumber/LBMbynumber.html",       # master LB index (~13 000 entries)
    BASE_URL + "/detail/LB-bootleg-by-title.html", # bootleg title index
]

_HEADERS = {"User-Agent": "LosslessBob-Archiver/1.0 (offline mirror)"}

# File extensions that are cached as raw bytes (no link rewriting)
_RAW_EXTS = {".txt", ".ffp", ".md5", ".st5", ".sha1", ".sha256",
             ".jpg", ".jpeg", ".png", ".gif", ".ico", ".css", ".js"}

# Extensions that are definitely not worth downloading
_SKIP_EXTS = {".mp3", ".flac", ".ape", ".wav", ".shn", ".m4a",
              ".zip", ".gz", ".tar", ".rar", ".exe", ".dmg",
              ".pdf", ".doc", ".docx", ".xls"}

# ── Shared crawler state ──────────────────────────────────────────────────────

_crawler_lock = threading.Lock()
_crawler_state: dict = {
    "running":       False,
    "stage":         "idle",     # idle | loading | crawling | done | stopped | error
    "current_url":   None,
    "queue_size":    0,
    "fetched":       0,
    "not_modified":  0,
    "skipped":       0,
    "failed":        0,
    "not_found":     0,
    "session_id":    None,
    "message":       "",
    "stop_requested": False,
}


def get_crawler_status() -> dict:
    """Return a snapshot of the current crawler state."""
    with _crawler_lock:
        return dict(_crawler_state)


def stop_crawler() -> None:
    """Request the crawler to stop after the current URL."""
    with _crawler_lock:
        _crawler_state["stop_requested"] = True


def _set(**kwargs) -> None:
    with _crawler_lock:
        _crawler_state.update(kwargs)


def _stopped() -> bool:
    with _crawler_lock:
        return _crawler_state["stop_requested"]


# ── URL helpers ───────────────────────────────────────────────────────────────

def _normalise(url: str) -> str:
    """Strip fragments and trailing slashes; return canonical URL string."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(path=path, query="").geturl()


def _is_same_domain(url: str) -> bool:
    host = urlparse(url).netloc
    return host == BASE_DOMAIN or host == ""


def _url_to_local(url: str) -> Path:
    """Map a site URL to its local mirror path under SITE_DIR.

    Examples::

        /detail/LB-00001.html   → data/site/detail/LB-00001.html
        /files/LBF-01234-x.txt  → data/site/files/LBF-01234-x.txt
        /                       → data/site/index.html
    """
    path = urlparse(url).path.lstrip("/") or "index.html"
    # If the path has no extension, treat as a directory index
    p = Path(path)
    if not p.suffix:
        path = path.rstrip("/") + "/index.html"
    return SITE_DIR / path


def _ext(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower()


def _should_skip(url: str) -> bool:
    """Return True if this URL should never be downloaded."""
    e = _ext(url)
    if e in _SKIP_EXTS:
        return True
    parsed = urlparse(url)
    # Skip mailto:, javascript:, tel: etc.
    if parsed.scheme and parsed.scheme not in ("http", "https", ""):
        return True
    return False


# ── Link extraction ───────────────────────────────────────────────────────────

def _extract_links(html: str, page_url: str) -> list[str]:
    """Return normalised same-domain URLs found in *html*."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for tag in soup.find_all(["a", "link"], href=True):
        href = tag["href"].strip()
        abs_url = urljoin(page_url, href)
        abs_url = _normalise(abs_url)
        if not _is_same_domain(abs_url):
            continue
        if _should_skip(abs_url):
            continue
        found.append(abs_url)
    return found


# ── robots.txt ────────────────────────────────────────────────────────────────

_robots_disallowed: set[str] = set()
_robots_loaded = False


def _load_robots(session: requests.Session) -> None:
    global _robots_loaded
    if _robots_loaded:
        return
    try:
        resp = session.get(BASE_URL + "/robots.txt", timeout=10)
        if resp.status_code == 200:
            ua_block = False
            for line in resp.text.splitlines():
                line = line.strip()
                if line.lower().startswith("user-agent"):
                    ua_block = "*" in line or "archiver" in line.lower()
                elif ua_block and line.lower().startswith("disallow"):
                    path = line.split(":", 1)[-1].strip()
                    if path:
                        _robots_disallowed.add(path)
    except Exception:
        pass
    _robots_loaded = True


def _robots_allowed(url: str) -> bool:
    path = urlparse(url).path
    for disallowed in _robots_disallowed:
        if path.startswith(disallowed):
            return False
    return True


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _sleep(base_ms: int, jitter: bool = True) -> None:
    """Sleep for base_ms milliseconds ± 20% jitter."""
    ms = base_ms
    if jitter:
        ms = int(ms * random.uniform(0.8, 1.2))
    time.sleep(ms / 1000.0)


# ── Fetch with If-Modified-Since ──────────────────────────────────────────────

def _fetch_page(
    session: requests.Session,
    url: str,
    last_modified: str | None,
    delay_ms: int,
) -> tuple[int, bytes | None, str | None]:
    """Fetch *url* with conditional GET.

    Args:
        session:       Requests session (connection pooling).
        url:           Absolute URL to fetch.
        last_modified: Stored ``Last-Modified`` header from previous fetch.
        delay_ms:      Base delay in ms before the request.

    Returns:
        ``(http_status, body_bytes_or_None, new_last_modified_or_None)``
        Status 304 means unchanged — body is None.
    """
    _sleep(delay_ms)
    hdrs = dict(_HEADERS)
    if last_modified:
        hdrs["If-Modified-Since"] = last_modified

    for attempt in range(3):
        try:
            resp = session.get(url, headers=hdrs, timeout=30)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                logger.warning("Crawler: 429 — sleeping %ds", retry_after)
                time.sleep(retry_after)
                continue
            new_lm = resp.headers.get("Last-Modified")
            if resp.status_code == 304:
                return 304, None, last_modified
            return resp.status_code, resp.content, new_lm
        except requests.RequestException as e:
            wait = 5 * (2 ** attempt)
            logger.warning("Crawler: fetch error %s (attempt %d) — waiting %ds", e, attempt + 1, wait)
            time.sleep(wait)

    return 0, None, None


# ── Save page ─────────────────────────────────────────────────────────────────

def _save(url: str, content: bytes) -> Path:
    """Write *content* to the mirror path for *url*, rewriting links if HTML."""
    local = _url_to_local(url)
    local.parent.mkdir(parents=True, exist_ok=True)
    ext = _ext(url)
    if ext == ".html" or ext == "" or not ext:
        html = content.decode("utf-8", errors="replace")
        html = rewrite_links(html, url, BASE_DOMAIN)
        local.write_text(html, encoding="utf-8")
    else:
        local.write_bytes(content)
    return local


# ── Main crawl loop ───────────────────────────────────────────────────────────

def crawl(
    start_url: str = SITE_HOME_URL,
    scope: str = "full",
    force: bool = False,
    delay_ms: int = 1500,
    daily_cap: int = 5000,
    db_path=None,
) -> dict:
    """Crawl the LosslessBob site and cache all pages under data/site/.

    Args:
        start_url:  Entry point URL.  Defaults to the site root.
        scope:      Label stored on the scrape_session row (``'full'`` or
                    ``'incremental'``).
        force:      When True, re-fetch pages that already exist on disk and
                    ignore ``If-Modified-Since``.
        delay_ms:   Base milliseconds between page requests.
        daily_cap:  Maximum requests in this session (safety limit).
        db_path:    Override DB path (tests).

    Returns:
        Dict with final counts.
    """
    db_path = db_path or DB_PATH

    _set(running=True, stage="loading", fetched=0, not_modified=0,
         skipped=0, failed=0, not_found=0, stop_requested=False,
         current_url=None, message="Loading inventory…")

    session_id = create_scrape_session(scope, start_url, db_path)
    _set(session_id=session_id)

    # Build visited set and pending queue from the inventory table + disk
    _set(stage="loading", message="Building queue from inventory…")
    visited: set[str] = set() if force else get_downloaded_urls(db_path)
    pending_db = get_pending_urls(db_path)   # [{url, last_modified}]
    lm_map: dict[str, str | None] = {r["url"]: r["last_modified"] for r in pending_db}

    queue: deque[str] = deque()

    def _seed(url: str, discovered_by: str = "start") -> None:
        norm = _normalise(url)
        if norm not in visited and norm not in queue:
            queue.append(norm)
            if norm not in lm_map:
                upsert_inventory(norm, db_path, status="pending",
                                 discovered_by=discovered_by, session_id=session_id)

    _seed(start_url)
    # Always seed known index pages — the root URL is a placeholder with no links.
    for seed in SEED_URLS:
        _seed(seed)

    # Re-queue anything marked pending in the DB
    for row in pending_db:
        url = row["url"]
        if url not in visited and url not in queue:
            queue.append(url)

    counts = {"fetched": 0, "not_modified": 0, "skipped": 0,
              "failed": 0, "not_found": 0}

    http_session = requests.Session()
    _load_robots(http_session)

    _set(stage="crawling", queue_size=len(queue),
         message=f"Starting crawl — {len(queue)} URLs queued")

    while queue and not _stopped() and counts["fetched"] + counts["not_modified"] < daily_cap:
        url = queue.popleft()

        if url in visited:
            continue
        if not _robots_allowed(url):
            visited.add(url)
            upsert_inventory(url, db_path, status="skipped", session_id=session_id)
            counts["skipped"] += 1
            continue

        stored_lm = lm_map.get(url) if not force else None

        _set(current_url=url, queue_size=len(queue),
             **{k: counts[k] for k in counts},
             message=f"{'↺' if stored_lm else '↓'} {url}")

        status, body, new_lm = _fetch_page(http_session, url, stored_lm, delay_ms)

        if status == 304:
            visited.add(url)
            counts["not_modified"] += 1
            upsert_inventory(url, db_path, status="downloaded",
                             last_checked_at="CURRENT_TIMESTAMP",
                             session_id=session_id)
            _set(not_modified=counts["not_modified"])
            continue

        if status == 404:
            visited.add(url)
            counts["not_found"] += 1
            upsert_inventory(url, db_path, status="not_found",
                             http_status=404, session_id=session_id)
            _set(not_found=counts["not_found"])
            continue

        if status == 0 or body is None:
            counts["failed"] += 1
            upsert_inventory(url, db_path, status="failed",
                             http_status=status, session_id=session_id)
            _set(failed=counts["failed"])
            continue

        # Save to disk
        sha = hashlib.sha256(body).hexdigest()
        saved_path = _save(url, body)
        visited.add(url)
        counts["fetched"] += 1

        upsert_inventory(
            url, db_path,
            status="downloaded",
            relative_path=str(saved_path.relative_to(SITE_DIR)),
            content_type="text/html" if _ext(url) in (".html", "") else "application/octet-stream",
            last_fetched_at="CURRENT_TIMESTAMP",
            last_checked_at="CURRENT_TIMESTAMP",
            last_modified=new_lm,
            body_sha256=sha,
            size_bytes=len(body),
            http_status=status,
            session_id=session_id,
        )
        _set(fetched=counts["fetched"])

        # Discover new links from HTML pages
        if _ext(url) in (".html", ""):
            html = body.decode("utf-8", errors="replace")
            for link in _extract_links(html, url):
                if link not in visited and link not in queue:
                    queue.append(link)
                    if link not in lm_map:
                        upsert_inventory(link, db_path, status="pending",
                                         discovered_by=url, session_id=session_id)
                        lm_map[link] = None

        _set(queue_size=len(queue))

    final_status = "stopped" if _stopped() else "done"
    finish_scrape_session(
        session_id,
        status=final_status,
        pages_fetched=counts["fetched"],
        pages_304=counts["not_modified"],
        pages_skipped=counts["skipped"],
        pages_failed=counts["failed"],
        db_path=db_path,
    )

    _set(running=False, stage=final_status, current_url=None,
         message=f"Done — {counts['fetched']} fetched, "
                 f"{counts['not_modified']} unchanged (304), "
                 f"{counts['failed']} failed.")

    return {"status": final_status, **counts}
