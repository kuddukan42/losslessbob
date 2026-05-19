from __future__ import annotations

import re
import time
import threading
from typing import Callable

import requests
from bs4 import BeautifulSoup

from backend.db import (
    get_connection, DB_PATH, insert_missing_entry,
    record_entry_changes, reconcile_lb_status,
)
from backend.paths import (
    SITE_DETAIL_DIR, SITE_FILES_DIR, to_long_path,
    detail_page_path, attachment_path,
)
from backend.html_utils import rewrite_links

BASE_URL = "http://www.losslessbob.wonderingwhattochoose.com"
DETAIL_URL = BASE_URL + "/detail/LB-{n}.html"
FILE_URL = BASE_URL + "/files/{filename}"
BYNUMBER_URL = BASE_URL + "/bynumber/LBMbynumber.html"

HEADERS = {"User-Agent": "LosslessBob-Archiver/1.0 (personal research tool)"}

_scrape_state = {
    "running": False,
    "current_lb": None,
    "last_lb": None,
    "total": 0,
    "done": 0,
    "errors": 0,
    "skipped": 0,
    "last_action": None,
    "last_source": None,
    "stop_requested": False,
}
_scrape_lock = threading.Lock()


def get_scrape_status() -> dict:
    """Return a snapshot of the current scrape state.

    Returns:
        Dict with keys: running (bool), current_lb (int|None), last_lb (int|None),
        total (int), done (int), errors (int), skipped (int),
        last_action (str|None), last_source (str|None), stop_requested (bool).
    """
    with _scrape_lock:
        return dict(_scrape_state)


def stop_scrape() -> None:
    """Signal the active scrape_range call to stop after its current entry."""
    with _scrape_lock:
        _scrape_state["stop_requested"] = True


def _fetch(url: str, retries: int = 3, delay: float = 1.5) -> tuple[requests.Response | None, int]:
    """GET *url* with retry logic and 429 back-off.

    Args:
        url: Full URL to fetch.
        retries: Maximum number of attempts before giving up.
        delay: Base sleep in seconds between retries (multiplied by attempt number).

    Returns:
        (response, status_code) on success; (None, 404) on 404; (None, 0) after
        all retries are exhausted.
    """
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 429:
                time.sleep(60)
                continue
            if resp.status_code == 404:
                return None, 404
            resp.raise_for_status()
            return resp, resp.status_code
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None, 0


def scrape_entry(
    lb_number: int,
    force: bool = False,
    download_files: bool = True,
    use_local_pages: bool = False,
    db_path: str | None = None,
) -> dict:
    """Scrape a single LB entry page and persist the result to the database.

    Fetches the detail page for *lb_number* (from the live site or a local
    cache), parses metadata and attachment links, upserts the ``entries`` and
    ``entry_files`` rows, optionally downloads attachment files, and calls
    ``reconcile_lb_status`` to keep ``lb_master`` in sync.

    Args:
        lb_number: The LB number to scrape (e.g. 12345).
        force: When True, re-scrape and re-download even if the entry already
            exists and all files are present.
        download_files: When True, fetch attachment files that are not yet
            cached locally.
        use_local_pages: When True, read the detail page from
            ``data/site/detail/`` instead of making a network request.
        db_path: Override the default database path (used in tests).

    Returns:
        On skip: ``{"skipped": True}``.
        On 404: ``{"error": "404", "missing": True}``.
        On network failure: ``{"error": "fetch_failed"}``.
        On success: ``{"ok": True, "files_downloaded": list[str], "local_source": bool}``.
    """
    db_path = db_path or DB_PATH
    lb_id = f"{lb_number:05d}"

    # Resolve local page path early so the skip logic can check its existence.
    local_page = to_long_path(detail_page_path(lb_id))

    if not force:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM entries WHERE lb_number=?", (lb_number,)
            ).fetchone()
            if row is not None:
                if row["status"] == "missing":
                    # If a local page is available we can recover real metadata;
                    # only skip if there is nothing local to work with.
                    if not (use_local_pages and local_page.exists()):
                        return {"skipped": True}
                elif not download_files:
                    return {"skipped": True}
                else:
                    for prow in conn.execute(
                        "SELECT filename, clean_name FROM entry_files WHERE lb_number=? AND downloaded=0",
                        (lb_number,)
                    ).fetchall():
                        if attachment_path(prow["filename"]).exists():
                            conn.execute(
                                "UPDATE entry_files SET downloaded=1 WHERE lb_number=? AND filename=?",
                                (lb_number, prow["filename"])
                            )
                    pending = conn.execute(
                        "SELECT COUNT(*) FROM entry_files WHERE lb_number=? AND downloaded=0",
                        (lb_number,)
                    ).fetchone()[0]
                    if pending == 0:
                        return {"skipped": True}

    if use_local_pages and local_page.exists():
        html_text = local_page.read_text(encoding="utf-8", errors="replace")
        used_local = True
    else:
        url = DETAIL_URL.format(n=lb_id)
        resp, status = _fetch(url)
        if status == 404:
            insert_missing_entry(lb_number, db_path)
            reconcile_lb_status(lb_number, trigger="scrape", db_path=db_path)
            return {"error": "404", "missing": True}
        if resp is None:
            return {"error": "fetch_failed"}
        html_text = resp.text
        used_local = False
        SITE_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
        rewritten = rewrite_links(html_text, url, BASE_URL.split("//")[-1])
        local_page.write_text(rewritten, encoding="utf-8")

    soup = BeautifulSoup(html_text, "lxml")
    entry_data = {"lb_number": lb_number}

    # Parse the detail table — find the one with known header columns
    for table in soup.find_all("table"):
        headers_row = table.find("tr")
        if not headers_row:
            continue
        headers = [th.get_text(strip=True).lower() for th in headers_row.find_all(["th", "td"])]
        if not any(h in headers for h in ("date", "location", "rating")):
            continue
        data_row = headers_row.find_next_sibling("tr")
        if data_row:
            values = [td.get_text(strip=True) for td in data_row.find_all("td")]
            row_dict = dict(zip(headers, values))
            entry_data["date_str"] = row_dict.get("date", row_dict.get("date_str", ""))
            entry_data["location"] = row_dict.get("location", "")
            entry_data["cdr"] = row_dict.get("cdr", "")
            entry_data["rating"] = row_dict.get("rating", "")
            entry_data["timing"] = row_dict.get("timing", "")
        break

    # Collect text content — <p> tags are description; bare text nodes between <hr/>
    # separators may be notes (description) or track listings (setlist)
    from bs4 import NavigableString
    track_pattern = re.compile(r'^\d{1,2}[.)]\s')
    desc_parts = []
    setlist_parts = []

    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            desc_parts.append(text)

    body = soup.find("body")
    if body:
        for node in body.children:
            if not isinstance(node, NavigableString):
                continue
            text = str(node).strip()
            if not text:
                continue
            if track_pattern.search(text):
                setlist_parts.append(text)
            else:
                desc_parts.append(text)

    entry_data["description"] = "\n\n".join(desc_parts)
    entry_data["setlist"] = "\n\n".join(setlist_parts)

    # Collect attachment links
    file_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/files/LBF-" in href:
            filename = href.split("/files/")[-1].strip()
            clean = re.sub(r'^LBF-\d+-', '', filename)
            full_url = BASE_URL + "/files/" + filename
            file_links.append((filename, clean, full_url))

    record_entry_changes(lb_number, entry_data, db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO entries(lb_number, date_str, location, cdr, rating, timing, description, setlist)
               VALUES(:lb_number,:date_str,:location,:cdr,:rating,:timing,:description,:setlist)""",
            {
                "lb_number": lb_number,
                "date_str": entry_data.get("date_str", ""),
                "location": entry_data.get("location", ""),
                "cdr": entry_data.get("cdr", ""),
                "rating": entry_data.get("rating", ""),
                "timing": entry_data.get("timing", ""),
                "description": entry_data.get("description", ""),
                "setlist": entry_data.get("setlist", ""),
            }
        )
        for filename, clean, file_url in file_links:
            conn.execute(
                "INSERT OR IGNORE INTO entry_files(lb_number, filename, clean_name, file_url) VALUES(?,?,?,?)",
                (lb_number, filename, clean, file_url)
            )

    downloaded = []
    if download_files and file_links:
        SITE_FILES_DIR.mkdir(parents=True, exist_ok=True)
        for filename, clean, file_url in file_links:
            local_path = attachment_path(filename)   # data/site/files/LBF-XXXXX-name.ext
            if local_path.exists() and (not force or use_local_pages):
                continue
            file_resp, fstatus = _fetch(file_url)
            if file_resp and fstatus == 200:
                local_path.write_bytes(file_resp.content)
                with get_connection(db_path) as conn:
                    conn.execute(
                        "UPDATE entry_files SET downloaded=1 WHERE lb_number=? AND filename=?",
                        (lb_number, filename)
                    )
                downloaded.append(clean)
            time.sleep(0.5)

    reconcile_lb_status(lb_number, trigger="scrape", db_path=db_path)
    return {"ok": True, "files_downloaded": downloaded, "local_source": used_local}


def scrape_range(
    lb_numbers: list[int],
    force: bool = False,
    download_files: bool = True,
    use_local_pages: bool = False,
    delay_ms: int = 1500,
    db_path: str | None = None,
    progress_cb: Callable[[int, int, int], None] | None = None,
) -> None:
    """Scrape a sequence of LB entries, updating shared state for GUI progress.

    Iterates over *lb_numbers* calling :func:`scrape_entry` for each one.
    Updates ``_scrape_state`` so the Setup tab progress bar and Stop button
    work without extra wiring.  Respects ``stop_requested`` between entries.
    Runs ``PRAGMA optimize`` on the connection when done.

    Args:
        lb_numbers: Ordered list of LB numbers to scrape.
        force: Passed through to :func:`scrape_entry`.
        download_files: Passed through to :func:`scrape_entry`.
        use_local_pages: Passed through to :func:`scrape_entry`.
        delay_ms: Milliseconds to sleep between live web requests.  Skipped
            entries and local-page reads do not incur the delay.
        db_path: Override the default database path (used in tests).
        progress_cb: Optional callback invoked after each entry as
            ``progress_cb(done, total, lb_number)``.
    """
    db_path = db_path or DB_PATH
    total = len(lb_numbers)

    with _scrape_lock:
        _scrape_state.update({
            "running": True,
            "total": total,
            "done": 0,
            "errors": 0,
            "skipped": 0,
            "last_action": None,
            "last_source": None,
            "stop_requested": False,
        })

    for i, lb in enumerate(lb_numbers):
        with _scrape_lock:
            if _scrape_state["stop_requested"]:
                break
            _scrape_state["current_lb"] = lb

        result = scrape_entry(lb, force=force, download_files=download_files, use_local_pages=use_local_pages, db_path=db_path)
        was_skipped = result.get("skipped", False)

        with _scrape_lock:
            _scrape_state["done"] = i + 1
            _scrape_state["last_lb"] = lb
            if "error" in result:
                _scrape_state["errors"] += 1
                _scrape_state["last_action"] = "error"
                _scrape_state["last_source"] = None
            elif was_skipped:
                _scrape_state["skipped"] += 1
                _scrape_state["last_action"] = "skipped"
                _scrape_state["last_source"] = None
            else:
                _scrape_state["last_action"] = "scraped"
                _scrape_state["last_source"] = "local" if result.get("local_source") else "web"

        if progress_cb:
            progress_cb(i + 1, total, lb)

        if not was_skipped and not result.get("local_source") and i < total - 1:
            time.sleep(delay_ms / 1000.0)

    with _scrape_lock:
        _scrape_state.update({"running": False, "done": total, "current_lb": None})

    conn = get_connection(db_path)
    conn.execute("PRAGMA optimize")
    conn.commit()


def download_pages_range(lb_numbers: list[int], force: bool = False, delay_ms: int = 1500) -> None:
    """Fetch and cache HTML detail pages for *lb_numbers* without parsing metadata.

    Saves each page to ``data/pages/LB-{n:05d}.html``.  Does not write to the
    database, parse entry fields, or download attachment files.  Existing pages
    are skipped unless *force* is True.

    Uses the same ``_scrape_state`` as :func:`scrape_range` so the Setup-tab
    progress bar and Stop button work without any extra wiring.

    Args:
        lb_numbers: Ordered list of LB numbers to download.
        force: When True, re-download pages that already exist on disk.
        delay_ms: Milliseconds to sleep between successful web fetches.
    """
    total = len(lb_numbers)
    SITE_DETAIL_DIR.mkdir(parents=True, exist_ok=True)

    with _scrape_lock:
        _scrape_state.update({
            "running": True,
            "total": total,
            "done": 0,
            "errors": 0,
            "skipped": 0,
            "last_action": None,
            "last_source": None,
            "stop_requested": False,
            "current_lb": None,
            "last_lb": None,
        })

    for i, lb in enumerate(lb_numbers):
        with _scrape_lock:
            if _scrape_state["stop_requested"]:
                break
            _scrape_state["current_lb"] = lb

        lb_id = f"{lb:05d}"
        local_page = to_long_path(detail_page_path(lb_id))

        if not force and local_page.exists():
            with _scrape_lock:
                _scrape_state["done"] = i + 1
                _scrape_state["last_lb"] = lb
                _scrape_state["skipped"] += 1
                _scrape_state["last_action"] = "skipped"
                _scrape_state["last_source"] = None
            continue

        url = DETAIL_URL.format(n=lb_id)
        resp, status = _fetch(url)

        with _scrape_lock:
            _scrape_state["done"] = i + 1
            _scrape_state["last_lb"] = lb

        if resp is None or status in (0, 404):
            with _scrape_lock:
                if status == 404:
                    _scrape_state["skipped"] += 1
                    _scrape_state["last_action"] = "skipped"
                else:
                    _scrape_state["errors"] += 1
                    _scrape_state["last_action"] = "error"
                _scrape_state["last_source"] = None
            continue

        url = DETAIL_URL.format(n=lb_id)
        rewritten = rewrite_links(resp.text, url, BASE_URL.split("//")[-1])
        local_page.write_text(rewritten, encoding="utf-8")

        with _scrape_lock:
            _scrape_state["last_action"] = "downloaded"
            _scrape_state["last_source"] = "web"

        if i < total - 1:
            time.sleep(delay_ms / 1000.0)

    with _scrape_lock:
        _scrape_state.update({"running": False, "current_lb": None})


# check_for_update() was removed — it scraped the bynumber page to count LB links
# which missed corrections and checksum additions that didn't extend the max LB number.
# Use backend.flat_file.discover_flat_file_release() and the /api/flat_file/* routes instead.
