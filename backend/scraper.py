import re
import time
import threading
import requests
from bs4 import BeautifulSoup

from backend.db import (
    get_connection, DB_PATH, insert_missing_entry,
    record_entry_changes, reconcile_lb_status,
)
from backend.paths import ATTACHMENTS_DIR, PAGES_DIR, to_long_path

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


def get_scrape_status():
    with _scrape_lock:
        return dict(_scrape_state)


def stop_scrape():
    with _scrape_lock:
        _scrape_state["stop_requested"] = True


def _fetch(url, retries=3, delay=1.5):
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


def scrape_entry(lb_number, force=False, download_files=True, use_local_pages=False, db_path=None):
    db_path = db_path or DB_PATH
    lb_id = f"{lb_number:05d}"
    lb_dir = to_long_path(ATTACHMENTS_DIR / f"LB-{lb_id}")

    # Resolve local page path early so the skip logic can check its existence.
    local_page = to_long_path(PAGES_DIR / f"LB-{lb_id}.html")

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
                        if (lb_dir / prow["clean_name"]).exists():
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
        PAGES_DIR.mkdir(parents=True, exist_ok=True)
        local_page.write_text(html_text, encoding="utf-8")

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
        lb_dir.mkdir(parents=True, exist_ok=True)
        for filename, clean, file_url in file_links:
            local_path = lb_dir / clean
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


def scrape_range(lb_numbers, force=False, download_files=True, use_local_pages=False, delay_ms=1500, db_path=None, progress_cb=None):
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


def check_for_update(db_path=None):
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        local_max = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0

    resp, status = _fetch(BYNUMBER_URL)
    site_max = None
    if resp:
        soup = BeautifulSoup(resp.text, "lxml")
        all_links = soup.find_all("a", href=True)
        lb_nums = []
        for a in all_links:
            m = re.search(r'LB-(\d+)', a.get_text() + a["href"])
            if m:
                lb_nums.append(int(m.group(1)))
        if lb_nums:
            site_max = max(lb_nums)

    return {
        "local_latest": local_max,
        "site_latest": site_max,
        "update_available": (site_max is not None and site_max > local_max),
    }
