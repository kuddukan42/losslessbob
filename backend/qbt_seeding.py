"""Paced bulk seeding into qBittorrent (TODO-330).

Bulk adds used to hit the tracker with every announce at once.  This adds
torrents paused, then resumes them in batches with a delay between batches,
caps adds per run, and preflights qBittorrent's ``max_concurrent_http_announces``.
Pacing is a mitigation only: TUIT timeouts were server-side SYN drops.
Per-torrent tracker status is returned so silent announce failures show up.
"""
import logging
import time
from collections.abc import Callable

import requests

from backend import qbittorrent as qbt

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5
DEFAULT_INTERVAL_S = 60
DEFAULT_MAX_ADDS = 50
DEFAULT_MAX_ANNOUNCES = 20

_TRACKER_STATUS = {
    0: "disabled", 1: "not_contacted", 2: "working", 3: "updating", 4: "not_working",
}


def _open(host: str, port: int, username: str, password: str, api_key: str):
    """Return (session, base, error_dict_or_None) with auth done."""
    base = qbt._base_url(host, port)
    session = qbt._make_session(base, api_key)
    if not api_key:
        err = qbt._login(session, base, username, password)
        if err:
            return session, base, err
    return session, base, None


def preflight(
    host: str, port: int, username: str = "", password: str = "", api_key: str = "",
    max_announces: int = DEFAULT_MAX_ANNOUNCES,
) -> dict:
    """Read max_concurrent_http_announces and decide whether to proceed.

    Returns:
        Dict: ok (bool, False = refuse), value (int|None), warning (str|None),
        error (str if ok=False).
    """
    try:
        session, base, err = _open(host, port, username, password, api_key)
        if err:
            return {**err, "value": None}
        r = session.get(base + "/api/v2/app/preferences", timeout=10)
        value = int(r.json().get("max_concurrent_http_announces"))
    except requests.exceptions.ConnectionError:
        return {"ok": False, "value": None, "error": "Cannot connect to qBittorrent"}
    except Exception as exc:
        # Prefs unreadable: don't block seeding, but say so.
        return {"ok": True, "value": None,
                "warning": f"Could not read max_concurrent_http_announces: {exc}"}
    if value > max_announces:
        return {"ok": False, "value": value,
                "error": f"max_concurrent_http_announces={value} exceeds limit "
                         f"{max_announces}; lower it in qBittorrent (Advanced)"}
    return {"ok": True, "value": value, "warning": None}


def tracker_status(
    infohashes: list[str], host: str, port: int,
    username: str = "", password: str = "", api_key: str = "",
) -> dict[str, dict]:
    """Per-torrent tracker status from /api/v2/torrents/trackers.

    Returns:
        {infohash: {"state": working|not_working|..., "trackers": [{url, status,
        msg}], "error": str|None}}.  state is "working" if any real tracker works,
        else not_working if any failed, else the first tracker's state.
    """
    try:
        session, base, err = _open(host, port, username, password, api_key)
    except Exception as exc:
        return {h: {"state": "unknown", "trackers": [], "error": str(exc)} for h in infohashes}
    out: dict[str, dict] = {}
    for h in infohashes:
        if err:
            out[h] = {"state": "unknown", "trackers": [], "error": err["error"]}
            continue
        try:
            r = session.get(base + "/api/v2/torrents/trackers", params={"hash": h}, timeout=10)
            rows = [t for t in r.json() if not str(t.get("url", "")).startswith("** [")]
            trackers = [{"url": t.get("url", ""),
                         "status": _TRACKER_STATUS.get(t.get("status"), "unknown"),
                         "msg": t.get("msg", "")} for t in rows]
            states = [t["status"] for t in trackers]
            if "working" in states:
                state = "working"
            elif "not_working" in states:
                state = "not_working"
            else:
                state = states[0] if states else "no_trackers"
            out[h] = {"state": state, "trackers": trackers, "error": None}
        except Exception as exc:
            out[h] = {"state": "unknown", "trackers": [], "error": str(exc)}
    return out


def _resume(session, base: str, hashes: list[str]) -> bool:
    """Resume torrents; qBittorrent 5 renamed resume -> start."""
    data = {"hashes": "|".join(hashes)}
    r = session.post(base + "/api/v2/torrents/resume", data=data, timeout=15)
    if r.status_code == 404:
        r = session.post(base + "/api/v2/torrents/start", data=data, timeout=15)
    return r.status_code == 200


def add_paused(
    torrent_ids: list[int], host: str, port: int, username: str = "", password: str = "",
    category: str = "", tags: str = "", api_key: str = "", db_path=None,
    max_adds: int = DEFAULT_MAX_ADDS, max_announces: int = DEFAULT_MAX_ANNOUNCES,
) -> dict:
    """Preflight, then add up to max_adds torrents paused.

    Returns:
        Dict: ok, error?, warning?, results (per-torrent add dicts with
        torrent_id/infohash), skipped (ids over the cap).
    """
    pf = preflight(host, port, username, password, api_key, max_announces)
    if not pf["ok"]:
        return {"ok": False, "error": pf["error"], "results": [], "skipped": []}
    todo, skipped = torrent_ids[:max_adds], torrent_ids[max_adds:]
    results = []
    for tid in todo:
        r = qbt.add_torrent_from_db(tid, host, port, username, password, category, tags,
                                    api_key=api_key, db_path=db_path, paused=True)
        results.append({**r, "torrent_id": tid})
    return {"ok": True, "warning": pf.get("warning"), "results": results, "skipped": skipped}


def release_paced(
    infohashes: list[str], host: str, port: int, username: str = "", password: str = "",
    api_key: str = "", batch_size: int = DEFAULT_BATCH_SIZE,
    interval_s: float = DEFAULT_INTERVAL_S, sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Resume torrents in batches, sleeping interval_s between batches.

    Returns:
        Dict: released (list), failed (list), tracker (tracker_status of released).
    """
    batch_size = max(1, int(batch_size))
    released: list[str] = []
    failed: list[str] = []
    session, base, err = _open(host, port, username, password, api_key)
    if err:
        return {"released": [], "failed": list(infohashes), "error": err["error"], "tracker": {}}
    for i in range(0, len(infohashes), batch_size):
        if i:
            sleep(interval_s)
        batch = infohashes[i:i + batch_size]
        try:
            ok = _resume(session, base, batch)
        except Exception:
            logger.exception("qBittorrent resume failed")
            ok = False
        (released if ok else failed).extend(batch)
        logger.info("qbt release batch %d: %d torrents ok=%s", i // batch_size + 1, len(batch), ok)
    return {"released": released, "failed": failed,
            "tracker": tracker_status(released, host, port, username, password, api_key)}
