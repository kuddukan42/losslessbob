"""setlist.fm API integration — fetches all Bob Dylan setlists and stores
tour names, set structure (Set 1 / Encore splits), song notes, and cover info.

Public API:
    run_update(db_path, api_key, force) — paginate artist setlists, upsert all data
    get_status()                        — current progress snapshot
    stop()                              — signal worker to stop after current page
    is_running()                        — True while worker is active

Schema: setlistfm_shows + setlistfm_setlist (see db.py).
Link to entries / bobdylan_shows via date_str (YYYY-MM-DD).

API key:  stored in meta table under key 'setlistfm_api_key'.
Rate limit: 0.5 s between requests (API allows ~2/s for free tier).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import requests

from backend.db import DB_PATH, get_meta, set_meta
from backend.db_queue import get_write_queue, init_write_queue

_log = logging.getLogger(__name__)

_ARTIST_MBID = "72c536dc-7137-4477-a521-567eeb840fa8"
_BASE_URL = "https://api.setlist.fm/rest/1.0"
_PAGE_DELAY = 0.55   # seconds between API requests
_META_KEY = "setlistfm_api_key"

_state: dict = {
    "status": "idle",   # idle | running | done | error
    "page": 0,
    "total_pages": 0,
    "shows_stored": 0,
    "tracks_stored": 0,
    "errors": 0,
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
    """Signal the active worker to stop after its current API page."""
    with _state_lock:
        _state["stop_requested"] = True


def is_running() -> bool:
    with _state_lock:
        return _state["status"] == "running"


def save_api_key(key: str, db_path: str | None = None) -> None:
    """Persist the setlist.fm API key to the meta table."""
    set_meta(_META_KEY, key.strip(), db_path=db_path)


def get_api_key(db_path: str | None = None) -> str | None:
    """Retrieve the stored API key, or None if not set."""
    return get_meta(_META_KEY, db_path=db_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def _is_stop_requested() -> bool:
    with _state_lock:
        return _state["stop_requested"]


def _parse_date(event_date: str) -> str:
    """Convert setlist.fm DD-MM-YYYY to YYYY-MM-DD.

    Args:
        event_date: Date string in DD-MM-YYYY format from the API.

    Returns:
        ISO date string YYYY-MM-DD, or the original string on parse failure.
    """
    try:
        return datetime.strptime(event_date, "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return event_date


def _fetch_page(page: int, api_key: str) -> dict | None:
    """Fetch one page of Bob Dylan setlists from the API.

    Args:
        page: 1-based page number.
        api_key: setlist.fm API key.

    Returns:
        Parsed JSON dict on success; None on error.
    """
    url = f"{_BASE_URL}/artist/{_ARTIST_MBID}/setlists"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params={"p": page}, timeout=30)
            if resp.status_code == 429:
                _log.warning("setlistfm: 429 rate-limited, sleeping 30s")
                time.sleep(30)
                continue
            if resp.status_code == 401:
                raise ValueError("setlist.fm API key is invalid or missing")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            _log.warning("setlistfm: page %d attempt %d failed: %s", page, attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_setlist(sl: dict) -> tuple[dict, list[dict]]:
    """Extract show metadata and flattened song list from a setlist API object.

    Args:
        sl: One setlist object from the API response.

    Returns:
        (show_row, track_rows) where show_row is a dict for setlistfm_shows
        and track_rows is a list of dicts for setlistfm_setlist.
    """
    venue = sl.get("venue") or {}
    city_obj = venue.get("city") or {}
    country = (city_obj.get("country") or {}).get("name", "")
    tour = (sl.get("tour") or {}).get("name", "")

    show_row = {
        "setlistfm_id": sl.get("id", ""),
        "date_str": _parse_date(sl.get("eventDate", "")),
        "tour_name": tour,
        "venue_name": venue.get("name", ""),
        "city": city_obj.get("name", ""),
        "country": country,
        "info": sl.get("info", "") or "",
        "setlistfm_url": sl.get("url", ""),
    }

    track_rows: list[dict] = []
    sets = (sl.get("sets") or {}).get("set") or []
    global_pos = 0
    for set_idx, s in enumerate(sets):
        set_name = s.get("name") or ""
        is_encore = int(bool(s.get("encore", 0)))
        for set_pos, song in enumerate(s.get("song") or []):
            cover_artist = ""
            cover_obj = song.get("cover")
            if cover_obj:
                cover_artist = cover_obj.get("name", "")
            track_rows.append({
                "setlistfm_id": show_row["setlistfm_id"],
                "set_index": set_idx,
                "set_name": set_name,
                "is_encore": is_encore,
                "position": global_pos,
                "set_position": set_pos,
                "track_name": song.get("name", ""),
                "info": song.get("info", "") or "",
                "is_cover": 1 if cover_obj else 0,
                "cover_artist": cover_artist,
                "is_tape": 1 if song.get("tape") else 0,
            })
            global_pos += 1

    return show_row, track_rows


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def run_update(
    db_path: str | None = None,
    api_key: str | None = None,
    force: bool = False,
) -> int:
    """Fetch all Bob Dylan setlists from setlist.fm and upsert into the DB.

    Paginates through /artist/{mbid}/setlists (20 per page).  With force=False
    uses INSERT OR IGNORE so existing rows are not overwritten.  With
    force=True replaces all rows.

    Args:
        db_path: Optional DB path override.
        api_key: API key; if None, loaded from meta table.
        force: If True, replace existing show/track data.

    Returns:
        Number of shows stored.
    """
    _set(
        status="running", page=0, total_pages=0,
        shows_stored=0, tracks_stored=0, errors=0,
        stop_requested=False, message="Starting…",
    )
    try:
        resolved_key = api_key or get_api_key(db_path=db_path)
        if not resolved_key:
            raise ValueError("No setlist.fm API key configured. "
                             "POST to /api/setlistfm/key first.")

        init_write_queue(str(db_path or DB_PATH))
        wq = get_write_queue()

        # Fetch page 1 to get total count
        _set(message="Fetching page 1…")
        data = _fetch_page(1, resolved_key)
        if not data:
            raise RuntimeError("Failed to fetch page 1 from setlist.fm")

        items_per_page = data.get("itemsPerPage", 20)
        total = data.get("total", 0)
        total_pages = max(1, -(-total // items_per_page))  # ceiling division
        _set(total_pages=total_pages, message=f"~{total} setlists across {total_pages} pages")
        _log.info("setlistfm: %d setlists, %d pages", total, total_pages)

        shows_stored = 0
        tracks_stored = 0

        def _write_page(conn, show_rows, track_rows, _force):
            nonlocal shows_stored, tracks_stored
            if _force:
                for sr in show_rows:
                    conn.execute(
                        """INSERT OR REPLACE INTO setlistfm_shows
                           (setlistfm_id, date_str, tour_name, venue_name,
                            city, country, info, setlistfm_url)
                           VALUES (:setlistfm_id,:date_str,:tour_name,:venue_name,
                                   :city,:country,:info,:setlistfm_url)""",
                        sr,
                    )
                    conn.execute(
                        "DELETE FROM setlistfm_setlist WHERE setlistfm_id=?",
                        (sr["setlistfm_id"],),
                    )
            else:
                for sr in show_rows:
                    conn.execute(
                        """INSERT OR IGNORE INTO setlistfm_shows
                           (setlistfm_id, date_str, tour_name, venue_name,
                            city, country, info, setlistfm_url)
                           VALUES (:setlistfm_id,:date_str,:tour_name,:venue_name,
                                   :city,:country,:info,:setlistfm_url)""",
                        sr,
                    )
            conn.executemany(
                """INSERT OR IGNORE INTO setlistfm_setlist
                   (setlistfm_id, set_index, set_name, is_encore,
                    position, set_position, track_name, info,
                    is_cover, cover_artist, is_tape)
                   VALUES (:setlistfm_id,:set_index,:set_name,:is_encore,
                           :position,:set_position,:track_name,:info,
                           :is_cover,:cover_artist,:is_tape)""",
                track_rows,
            )
            shows_stored += len(show_rows)
            tracks_stored += len(track_rows)

        # Process page 1 results
        page_setlists = data.get("setlist") or []
        show_rows, track_rows_flat = [], []
        for sl in page_setlists:
            sr, tr = _parse_setlist(sl)
            if sr["setlistfm_id"]:
                show_rows.append(sr)
                track_rows_flat.extend(tr)
        if show_rows:
            wq.execute(lambda c, _s=show_rows, _t=track_rows_flat, _f=force:
                       _write_page(c, _s, _t, _f))
        _set(page=1, shows_stored=shows_stored, tracks_stored=tracks_stored)

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            if _is_stop_requested():
                _log.info("setlistfm: stop requested at page %d", page)
                break
            _set(page=page, message=f"Page {page}/{total_pages}")
            time.sleep(_PAGE_DELAY)

            data = _fetch_page(page, resolved_key)
            if not data:
                _log.error("setlistfm: failed page %d", page)
                with _state_lock:
                    _state["errors"] += 1
                continue

            page_setlists = data.get("setlist") or []
            show_rows, track_rows_flat = [], []
            for sl in page_setlists:
                sr, tr = _parse_setlist(sl)
                if sr["setlistfm_id"]:
                    show_rows.append(sr)
                    track_rows_flat.extend(tr)
            if show_rows:
                wq.execute(lambda c, _s=show_rows, _t=track_rows_flat, _f=force:
                           _write_page(c, _s, _t, _f))
            _set(shows_stored=shows_stored, tracks_stored=tracks_stored)

        _set(
            status="done",
            message=f"Stored {shows_stored} shows, {tracks_stored} tracks",
        )
        _log.info("setlistfm: done — %d shows, %d tracks", shows_stored, tracks_stored)
        return shows_stored

    except Exception as exc:
        _log.exception("setlistfm: run_update failed")
        _set(status="error", message=str(exc))
        return 0
