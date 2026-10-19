"""WTRF fetch review surface (TODO-193).

Lists the latest wtrf_downloads row per LB entry with parsed signals and tied
candidates, and applies curator confirm / reject decisions:

  * confirm a paused-added row  -> resume the torrent in qBittorrent
  * confirm a skipped / downloaded row -> (download the .torrent from the chosen
    topic if needed, then) add it to qBittorrent, started
  * reject -> status='rejected', the row stays as history

All network access (WTRF, qBittorrent) happens only inside ``confirm_row`` and is
injectable for tests.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from backend import db as database

logger = logging.getLogger(__name__)

REVIEW_FILTERS = ("review", "added", "not_found", "rejected", "all")

# filter -> SQL predicate on the latest-per-LB row (alias w)
_FILTER_SQL = {
    "review": "w.status = 'skipped' AND w.confidence IN ('needs_review', 'ambiguous')",
    "added": "w.status IN ('qbt_added', 'downloaded')",
    "not_found": "w.status IN ('skipped', 'failed') AND w.confidence = 'not_found'",
    "rejected": "w.status = 'rejected'",
    "all": "1=1",
}


def _row_view(row: dict) -> dict:
    """Expand a raw wtrf_downloads row with parsed signals and candidate URLs."""
    try:
        signals = json.loads(row.get("signals_json") or "{}")
    except (TypeError, ValueError):
        signals = {}
    if not isinstance(signals, dict):
        signals = {}
    tied = [u for u in (signals.get("tied_candidates") or []) if isinstance(u, str)]
    if row.get("topic_url") and row["topic_url"] not in tied and tied:
        tied.insert(0, row["topic_url"])
    return {**row, "signals": signals, "candidates": tied or (
        [row["topic_url"]] if row.get("topic_url") else []
    )}


def list_review_rows(
    flt: str = "review", limit: int = 200, offset: int = 0, db_path=None,
) -> dict:
    """Return the latest wtrf_downloads row per LB for a review filter.

    Args:
        flt: One of REVIEW_FILTERS.
        limit: Max rows.
        offset: Rows to skip.
        db_path: Optional DB path override.

    Returns:
        Dict with rows (list), total (int) and counts (filter -> int).
    """
    if flt not in REVIEW_FILTERS:
        flt = "review"
    latest = (
        "FROM wtrf_downloads w WHERE w.id = "
        "(SELECT MAX(id) FROM wtrf_downloads x WHERE x.lb_number = w.lb_number)"
    )
    with database.get_connection(db_path) as conn:
        counts = {
            k: conn.execute(f"SELECT COUNT(*) {latest} AND {sql}").fetchone()[0]
            for k, sql in _FILTER_SQL.items()
        }
        rows = conn.execute(
            f"SELECT w.* {latest} AND {_FILTER_SQL[flt]} "
            "ORDER BY w.lb_number DESC LIMIT ? OFFSET ?",
            (max(1, min(limit, 1000)), max(0, offset)),
        ).fetchall()
    return {"rows": [_row_view(dict(r)) for r in rows], "total": counts[flt],
            "counts": counts}


def get_row(download_id: int, db_path=None) -> dict | None:
    """Fetch one wtrf_downloads row by id (raw dict) or None."""
    with database.get_connection(db_path) as conn:
        r = conn.execute("SELECT * FROM wtrf_downloads WHERE id=?", (download_id,)).fetchone()
    return dict(r) if r else None


def _merge_signals(row: dict, extra: dict) -> str:
    try:
        sig = json.loads(row.get("signals_json") or "{}")
    except (TypeError, ValueError):
        sig = {}
    if not isinstance(sig, dict):
        sig = {}
    sig.update(extra)
    return json.dumps(sig)


def reject_row(download_id: int, db_path=None) -> dict:
    """Mark a row rejected (kept as history; no qBittorrent action).

    Args:
        download_id: wtrf_downloads id.
        db_path: Optional DB path override.

    Returns:
        Dict with ok (bool) and error (str) on failure.
    """
    row = get_row(download_id, db_path)
    if not row:
        return {"ok": False, "error": "No such row"}
    database.update_wtrf_download(download_id, {
        "status": "rejected",
        "signals_json": _merge_signals(row, {
            "review": "rejected", "reviewed_at": datetime.now(UTC).isoformat(),
        }),
    })
    return {"ok": True}


def _qbt_conn() -> dict:
    from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
    user, pw = get_credentials(SERVICE_QBT)
    _, key = get_credentials(SERVICE_QBT_KEY)
    return {
        "host": database.get_meta("qbt_host") or "localhost",
        "port": int(database.get_meta("qbt_port") or 8080),
        "username": user, "password": pw, "api_key": key,
    }


def confirm_row(
    download_id: int,
    topic_url: str | None = None,
    save_path: str | None = None,
    delay: float = 2.0,
    db_path=None,
) -> dict:
    """Confirm a row: resume its paused torrent, or fetch + add it to qBittorrent.

    Args:
        download_id: wtrf_downloads id.
        topic_url: Candidate the curator picked (ambiguous rows); defaults to the
            row's topic_url. Must be one of the row's known candidates.
        save_path: qBittorrent download directory / .torrent folder.
        delay: Seconds between WTRF requests.
        db_path: Optional DB path override.

    Returns:
        Dict with ok (bool), action ('resumed'|'added') and error on failure.
    """
    from backend import qbittorrent as qbt
    from backend.paths import DATA_DIR
    from backend.wtrf_scraper import download_torrent_from_topic

    row = get_row(download_id, db_path)
    if not row:
        return {"ok": False, "error": "No such row"}
    view = _row_view(row)
    save = save_path or str(DATA_DIR / "downloads" / "wtrf")
    conn = _qbt_conn()
    stamp = {"review": "confirmed", "reviewed_at": datetime.now(UTC).isoformat()}

    # Paused-added (or already-added) torrent: just start it.
    if row["status"] == "qbt_added" and row.get("torrent_path"):
        ih = qbt.torrent_file_infohash(row["torrent_path"])
        res = qbt.resume_torrent(ih or "", **conn)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "Resume failed"}
        database.update_wtrf_download(
            download_id, {"signals_json": _merge_signals(row, stamp)})
        return {"ok": True, "action": "resumed"}

    chosen = topic_url or row.get("topic_url")
    torrent_path = row.get("torrent_path")
    if not (torrent_path and Path(torrent_path).exists()):
        if not chosen:
            return {"ok": False, "error": "No topic URL to fetch from"}
        if chosen not in view["candidates"]:
            return {"ok": False, "error": "topic_url is not a known candidate for this row"}
        dl = download_torrent_from_topic(row["lb_number"], chosen, save, delay)
        if not dl.get("ok"):
            return {"ok": False, "error": dl.get("error") or "Download failed"}
        torrent_path = dl["torrent_path"]

    add = qbt.add_torrent_for_download(
        torrent_path=torrent_path, save_path=save,
        category=database.get_meta("qbt_category") or "",
        tags=database.get_meta("qbt_tags") or "", paused=False, **conn,
    )
    if not add.get("ok"):
        return {"ok": False, "error": add.get("error") or "qBittorrent add failed"}
    database.update_wtrf_download(download_id, {
        "status": "qbt_added", "topic_url": chosen, "torrent_path": torrent_path,
        "qbt_added_at": datetime.now(UTC).isoformat(),
        "signals_json": _merge_signals(row, stamp),
    })
    return {"ok": True, "action": "added"}
