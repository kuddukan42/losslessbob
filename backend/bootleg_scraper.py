"""Scraper for the LosslessBob Bootleg-CD catalog index page.

Single entry point: :func:`scrape_bootlegs`.  Manual trigger only — no
auto-scrape on startup.  Mirrors the flat-file diff-then-apply pattern so
each run produces a meaningful change log rather than a blind wipe-and-reload.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any

import requests
from bs4 import BeautifulSoup

from backend.db import (
    _BOOTLEG_SOURCE_URL,
    DB_PATH,
    backup_database,
    get_connection,
)

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "LosslessBob-Archiver/1.0 (personal research tool)"}

# 2-digit year pivot: Y >= 30 → 19YY, Y < 30 → 20YY.
# Dylan's career started ~1960.  Revisit ~2030.
_YEAR_PIVOT = 30

_scrape_lock = threading.Lock()
_scrape_state: dict[str, Any] = {
    "running": False,
    "stage":   "idle",   # idle | fetching | parsing | diffing | applying | done | error
    "rows_total":   0,
    "rows_added":   0,
    "rows_changed": 0,
    "rows_removed": 0,
    "message": "",
    "error":   None,
}


def get_scrape_status() -> dict:
    """Return a snapshot of the current bootleg-scrape progress state."""
    with _scrape_lock:
        return dict(_scrape_state)


def _set(**kwargs) -> None:
    with _scrape_lock:
        _scrape_state.update(kwargs)


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> tuple[str | None, int | None]:
    """Parse a M/D/YY date string (with 'xx' for unknown parts).

    Args:
        raw: Date string as it appears on the page, e.g. ``"xx/xx/67"``,
             ``"08/31/69"``, ``"11/xx/68"``.

    Returns:
        ``(date_iso, year)`` where *date_iso* is the best-effort ISO string
        (``YYYY-MM-DD``, ``YYYY-MM``, or ``YYYY``) and *year* is the 4-digit
        integer, or ``(None, None)`` if the input is wholly unparseable.
    """
    raw = raw.strip()
    if not raw:
        return None, None
    parts = raw.split("/")
    if len(parts) != 3:
        return None, None

    m_raw, d_raw, y_raw = parts
    m_raw = m_raw.strip().lower()
    d_raw = d_raw.strip().lower()
    y_raw = y_raw.strip().lower()

    # Year
    try:
        y2 = int(y_raw)
        year = (1900 + y2) if y2 >= _YEAR_PIVOT else (2000 + y2)
    except ValueError:
        return None, None  # year unknown → can't produce anything useful

    m_known = m_raw not in ("xx", "x", "") and m_raw.isdigit()
    d_known = d_raw not in ("xx", "x", "") and d_raw.isdigit()

    if m_known and d_known:
        try:
            date_iso = f"{year:04d}-{int(m_raw):02d}-{int(d_raw):02d}"
        except ValueError:
            date_iso = f"{year:04d}"
    elif m_known:
        date_iso = f"{year:04d}-{int(m_raw):02d}"
    else:
        date_iso = f"{year:04d}"

    return date_iso, year


# ── Row parsing ───────────────────────────────────────────────────────────────

def _parse_row(cells: list) -> dict | None:
    """Extract one bootleg row from a list of BeautifulSoup <td> elements.

    Returns a dict ready to compare/insert, or None if the row is malformed
    (e.g. a header row or a row with fewer than 5 cells).
    """
    if len(cells) < 5:
        return None

    date_raw  = cells[0].get_text(" ", strip=True)
    title_raw = cells[1].get_text(" ", strip=True)
    location  = cells[2].get_text(" ", strip=True)
    cd_raw    = cells[3].get_text(" ", strip=True)
    lb_cell   = cells[4]

    # LB number from the link text or plain text
    lb_link = lb_cell.find("a")
    lb_text = (lb_link.get_text(strip=True) if lb_link
               else lb_cell.get_text(strip=True))
    lb_text = lb_text.strip()
    if not lb_text.upper().startswith("LB-"):
        return None
    try:
        lb_number = int(lb_text[3:])
    except ValueError:
        return None

    # LBBCD link (may be inside the title cell)
    lbbcd_id: int | None = None
    lbbcd_url: str | None = None
    title_link = cells[1].find("a", href=True)
    if title_link:
        href = title_link["href"].strip()
        if "LBBCD-" in href.upper():
            lbbcd_url = href
            try:
                # e.g. "lbbcd/LBBCD-275.html" → 275
                lbbcd_id = int(href.upper().split("LBBCD-")[1].split(".")[0])
            except (IndexError, ValueError):
                pass

    # CD count
    try:
        cd_count = int(cd_raw.strip())
    except ValueError:
        cd_count = 0

    date_iso, year = _parse_date(date_raw)

    return {
        "lb_number": lb_number,
        "title":     title_raw,
        "date_str":  date_raw,
        "date_iso":  date_iso,
        "year":      year,
        "location":  location,
        "cd_count":  cd_count,
        "lbbcd_id":  lbbcd_id,
        "lbbcd_url": lbbcd_url,
    }


# ── Diff + apply ──────────────────────────────────────────────────────────────

_NATURAL_KEY = ("lb_number", "title", "date_str")
_MUTABLE_COLS = ("location", "cd_count", "lbbcd_id", "lbbcd_url", "date_iso", "year")


def _diff(incoming: list[dict], current: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    """Compute adds, changes, and removals.

    Natural key: (lb_number, title, date_str).

    Returns:
        (to_add, to_change, ids_to_remove) where *to_change* rows include
        the ``id`` field of the current row to update.
    """
    def nk(row: dict) -> tuple:
        return tuple(row[k] for k in _NATURAL_KEY)

    current_by_nk = {nk(r): r for r in current}
    to_add: list[dict] = []
    to_change: list[dict] = []
    ids_to_remove: list[int] = []

    # Duplicates on the page (same natural key twice) → keep first, warn
    seen_incoming: set[tuple] = set()
    deduplicated: list[dict] = []
    for row in incoming:
        k = nk(row)
        if k in seen_incoming:
            logger.warning("Bootleg catalog: duplicate natural key skipped: %s", k)
            continue
        seen_incoming.add(k)
        deduplicated.append(row)

    for row in deduplicated:
        k = nk(row)
        if k not in current_by_nk:
            to_add.append(row)
        else:
            cur = current_by_nk[k]
            if any(row.get(c) != cur.get(c) for c in _MUTABLE_COLS):
                changed = dict(row)
                changed["id"] = cur["id"]
                to_change.append(changed)

    for k, cur in current_by_nk.items():
        if k not in seen_incoming:
            ids_to_remove.append(cur["id"])

    return to_add, to_change, ids_to_remove


def _apply_diff(
    to_add: list[dict],
    to_change: list[dict],
    ids_to_remove: list[int],
    db_path,
) -> None:
    conn = get_connection(db_path)
    if to_add:
        conn.executemany(
            "INSERT INTO bootleg_titles"
            "(lb_number, title, date_str, date_iso, year, location, cd_count, lbbcd_id, lbbcd_url)"
            " VALUES(:lb_number,:title,:date_str,:date_iso,:year,:location,:cd_count,:lbbcd_id,:lbbcd_url)",
            to_add,
        )
    for row in to_change:
        conn.execute(
            "UPDATE bootleg_titles SET location=?, cd_count=?, lbbcd_id=?, lbbcd_url=?, "
            "date_iso=?, year=? WHERE id=?",
            (row["location"], row["cd_count"], row["lbbcd_id"], row["lbbcd_url"],
             row["date_iso"], row["year"], row["id"]),
        )
    if ids_to_remove:
        ph = ",".join("?" * len(ids_to_remove))
        conn.execute(f"DELETE FROM bootleg_titles WHERE id IN ({ph})", ids_to_remove)
    conn.commit()


# ── Public entry point ────────────────────────────────────────────────────────

def scrape_bootlegs(force: bool = False, db_path=None) -> dict:
    """Fetch and diff-apply the LosslessBob Bootleg-CD catalog index.

    Args:
        force: When True, fetch and apply even if ETag / Last-Modified
               indicate no change since the last successful scrape.
        db_path: Override DB path (used in tests).

    Returns:
        Dict with keys: status, rows_total, rows_added, rows_changed,
        rows_removed, error (str or None).
    """
    db_path = db_path or DB_PATH
    _set(running=True, stage="fetching", rows_total=0, rows_added=0,
         rows_changed=0, rows_removed=0, message="Checking for changes…", error=None)

    url = _BOOTLEG_SOURCE_URL

    # Step 1 — HEAD to read caching headers
    prev_etag: str | None = None
    prev_lm: str | None = None
    conn = get_connection(db_path)
    last = conn.execute(
        "SELECT http_etag, http_last_modified FROM bootleg_scrapes "
        "WHERE status='success' ORDER BY scraped_at DESC LIMIT 1"
    ).fetchone()
    if last:
        prev_etag = last["http_etag"]
        prev_lm   = last["http_last_modified"]

    try:
        head_resp = requests.head(url, headers=HEADERS, timeout=30)
        etag = head_resp.headers.get("ETag")
        last_modified = head_resp.headers.get("Last-Modified")
    except requests.RequestException as e:
        _set(running=False, stage="error", error=str(e),
             message=f"HEAD request failed: {e}")
        _record_scrape(db_path, url, None, None, None, 0, 0, 0, 0, "failed")
        return {"status": "failed", "error": str(e),
                "rows_total": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0}

    if not force and prev_etag and etag and etag == prev_etag:
        _set(running=False, stage="done", message="No change detected (ETag match).")
        _record_scrape(db_path, url, etag, last_modified, None, 0, 0, 0, 0, "no_change")
        return {"status": "no_change", "error": None,
                "rows_total": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0}

    # Step 2 — GET full page
    _set(stage="fetching", message="Downloading catalog page…")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        _set(running=False, stage="error", error=str(e),
             message=f"GET failed: {e}")
        _record_scrape(db_path, url, etag, last_modified, None, 0, 0, 0, 0, "failed")
        return {"status": "failed", "error": str(e),
                "rows_total": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0}

    body = resp.text
    body_sha = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()

    if not force and prev_lm and last_modified and last_modified == prev_lm:
        _set(running=False, stage="done", message="No change detected (Last-Modified match).")
        _record_scrape(db_path, url, etag, last_modified, body_sha, 0, 0, 0, 0, "no_change")
        return {"status": "no_change", "error": None,
                "rows_total": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0}

    # Step 3 — Parse
    _set(stage="parsing", message="Parsing catalog table…")
    soup = BeautifulSoup(body, "lxml")
    incoming: list[dict] = []
    # The page has two tables: a 1-row title banner and the data table.
    # Pick the table that has <th> header cells (the data table).
    all_tables = soup.find_all("table")
    table = next((t for t in all_tables if t.find("th")), None) or (all_tables[-1] if all_tables else None)
    if table:
        rows = table.find_all("tr")
        for tr in rows[1:]:  # skip header
            cells = tr.find_all("td")
            parsed = _parse_row(cells)
            if parsed:
                incoming.append(parsed)

    rows_total = len(incoming)
    _set(rows_total=rows_total, message=f"Parsed {rows_total} rows. Computing diff…")

    # Step 4 — Diff against current DB state
    _set(stage="diffing")
    current_rows = conn.execute("SELECT * FROM bootleg_titles").fetchall()
    current = [dict(r) for r in current_rows]
    to_add, to_change, ids_to_remove = _diff(incoming, current)

    _set(stage="applying",
         message=f"Applying diff: +{len(to_add)} ~{len(to_change)} -{len(ids_to_remove)}…")

    # Step 5 — Backup + apply
    try:
        backup_database(reason="pre_bootleg_scrape", db_path=db_path)
    except Exception as e:
        logger.warning("Bootleg scrape: DB backup failed (continuing): %s", e)

    try:
        _apply_diff(to_add, to_change, ids_to_remove, db_path)
    except Exception as e:
        _set(running=False, stage="error", error=str(e),
             message=f"Apply failed: {e}")
        _record_scrape(db_path, url, etag, last_modified, body_sha,
                       rows_total, 0, 0, 0, "failed")
        return {"status": "failed", "error": str(e),
                "rows_total": rows_total, "rows_added": 0,
                "rows_changed": 0, "rows_removed": 0}

    rows_added   = len(to_add)
    rows_changed = len(to_change)
    rows_removed = len(ids_to_remove)
    _record_scrape(db_path, url, etag, last_modified, body_sha,
                   rows_total, rows_added, rows_changed, rows_removed, "success")

    _set(running=False, stage="done",
         rows_added=rows_added, rows_changed=rows_changed, rows_removed=rows_removed,
         message=(f"Done. {rows_total} rows total, "
                  f"+{rows_added} added, ~{rows_changed} changed, -{rows_removed} removed."))

    return {
        "status": "success",
        "error": None,
        "rows_total":   rows_total,
        "rows_added":   rows_added,
        "rows_changed": rows_changed,
        "rows_removed": rows_removed,
    }


def _record_scrape(db_path, url, etag, last_modified, body_sha,
                   rows_total, rows_added, rows_changed, rows_removed, status) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO bootleg_scrapes"
        "(source_url, http_etag, http_last_modified, body_sha256,"
        " rows_total, rows_added, rows_changed, rows_removed, status)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (url, etag, last_modified, body_sha,
         rows_total, rows_added, rows_changed, rows_removed, status),
    )
    conn.commit()
