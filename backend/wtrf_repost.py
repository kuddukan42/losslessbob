"""Retire WTRF seeds the swarm will never finish, and repost them from the collection.

Old WTRF topics (a month or more) are poorly seeded, so a partial overlay
stays short forever: a 98.9% seed in a dead swarm completes nobody's download
and keeps hardlinks to collection masters inside unfinished pieces. This
module

* **retires** them: the torrent is removed from qBittorrent with
  ``deleteFiles=false``, the overlay is unlinked file by file through
  :func:`backend.overlay_rehome.guard_path` (only names under ``* Seeds`` —
  a hardlinked file just loses its overlay name, the collection's data is
  never touched), and the ``wtrf_downloads`` row is marked ``retired`` so the
  board walk never seeds it again;
* **reposts** them: a fresh torrent is built from the LB's collection folder
  (named after the folder, so it seeds in place at 100%), added to
  qBittorrent, and replied into the original topic.

Every retired topic gets a ``wtrf_reposts`` row; posting is manual and paced
by the curator (``tools/wtrf_repost.py``).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from backend import qbittorrent, tracker_seed
from backend.checksum_utils import AUDIO_EXTS
from backend.overlay_rehome import (
    GuardError,
    Protected,
    _remove_tree,
    guard_path,
    is_overlay_dir,
)
from backend.torrent_verify import read_torrent, verify_folder

logger = logging.getLogger(__name__)

#: The reply posted with each replacement torrent (wording from tj, 2026-11-25).
REPOST_BODY = (
    "This is a reposted torrent, if you are looking for this show you can download "
    "it with this new torrent.  Seeded by kuddukan."
)

#: Torrents younger than this keep their chance at the swarm.
MIN_AGE_DAYS = 30

#: Share of the torrent our folder already matches above which a weak
#: (title/body) LB match counts as confirmed by content.
CONTENT_MATCH = 0.90

WTRF_TAG = "wtrf"


# ── qBittorrent reads ────────────────────────────────────────────────────────

def _session():
    """An authenticated qBittorrent WebUI session and its base URL."""
    c = tracker_seed._qbt_connection()
    base = qbittorrent._base_url(c["host"], c["port"])
    s = qbittorrent._make_session(base, c["api_key"])
    if not c["api_key"]:
        err = qbittorrent._login(s, base, c["username"], c["password"])
        if err:
            raise RuntimeError(f"qBittorrent login failed: {err}")
    return s, base


def qbt_torrents() -> list[dict]:
    """Every torrent qBittorrent holds (``/api/v2/torrents/info``)."""
    s, base = _session()
    return s.get(base + "/api/v2/torrents/info", timeout=60).json()


def shared_with(folder: Path, infohash: str, torrents: list[dict]) -> list[str]:
    """Other torrents whose files live in, above or below ``folder``.

    Two WTRF topics can post the same torrent name, so two infohashes can seed
    out of one overlay folder. Deleting it for one breaks the other.

    Args:
        folder: The overlay folder about to be deleted.
        infohash: The torrent being retired (ignored in the result).
        torrents: ``/api/v2/torrents/info`` rows.

    Returns:
        Infohashes (first 10 chars) of the other torrents using it.
    """
    f = str(folder).rstrip("/")
    out = []
    for t in torrents:
        if t.get("hash", "").lower() == infohash.lower():
            continue
        p = str(t.get("content_path") or "").rstrip("/")
        if p and (p == f or p.startswith(f + "/") or f.startswith(p + "/")):
            out.append(t["hash"][:10])
    return out


def qbt_files(infohash: str) -> list[dict]:
    """One torrent's files with per-file progress and priority."""
    s, base = _session()
    return s.get(base + "/api/v2/torrents/files", params={"hash": infohash},
                 timeout=30).json()


# ── Finding what to retire ───────────────────────────────────────────────────

@dataclass
class Retiree:
    """One incomplete WTRF torrent and the topic it came from."""

    infohash: str
    name: str
    content: str
    progress: float
    added_on: int
    shortfall: str
    topic_url: str
    lb_number: int
    confidence: str
    match: str
    ambiguous: bool = False  # more than one topic recorded this seed folder


def classify(files: list[dict], content_exists: bool) -> str:
    """Name what an incomplete torrent is short of.

    Args:
        files: qBittorrent's file list (name, progress).
        content_exists: Whether the seed folder is still on disk.

    Returns:
        A short label.
    """
    if not content_exists:
        return "overlay folder missing"
    audio = [f for f in files if os.path.splitext(f["name"])[1].lower() in AUDIO_EXTS]
    short = [f for f in audio if f["progress"] < 1]
    if not audio:
        return "no audio in torrent"
    if not short:
        return "only extras short"
    if all(f["progress"] == 0 for f in short):
        return "no audio found locally" if len(short) == len(audio) else "some audio absent"
    return "audio differs from ours"


def match_kind(confidence: str, progress: float, shortfall: str) -> str:
    """How sure we are the topic really is this LB.

    Returns:
        ``definitive`` (the uploader named the LB), ``content`` (a weaker match
        confirmed by most of the bytes matching our folder) or ``suspect``.
    """
    if confidence == "definitive":
        return "definitive"
    if progress >= CONTENT_MATCH and shortfall in (
            "audio differs from ours", "only extras short", "no audio in torrent"):
        return "content"
    return "suspect"


def _norm(p: str) -> str:
    return os.path.normpath(p)


def find_retirees(min_age_days: float = MIN_AGE_DAYS, db_path=None) -> list[Retiree]:
    """Incomplete WTRF torrents older than ``min_age_days``, with their topic.

    Args:
        min_age_days: Minimum age since the torrent was added.
        db_path: Optional DB path override.

    Returns:
        Retirees, oldest LB first. Torrents with no ``wtrf_downloads`` row are
        left out (nothing to repost them to).
    """
    from backend import db

    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT lb_number, topic_url, confidence, seed_folder FROM wtrf_downloads "
            "WHERE seed_folder IS NOT NULL AND seed_folder <> '' "
            "ORDER BY attempted_at DESC, id DESC").fetchall()
    by_folder: dict[str, tuple] = {}
    n_topics: dict[str, int] = {}
    for lb, url, conf, folder in rows:
        by_folder.setdefault(_norm(folder), (lb, url, conf or ""))
        n_topics[_norm(folder)] = n_topics.get(_norm(folder), 0) + 1

    cutoff = time.time() - min_age_days * 86400
    out: list[Retiree] = []
    for t in qbt_torrents():
        tags = {x.strip() for x in (t.get("tags") or "").split(",")}
        if WTRF_TAG not in tags or t.get("progress", 1) >= 1:
            continue
        if (t.get("added_on") or 0) > cutoff:
            continue
        content = t.get("content_path") or os.path.join(t["save_path"], t["name"])
        rec = by_folder.get(_norm(content))
        if rec is None or not rec[1]:
            continue
        shortfall = classify(qbt_files(t["hash"]), os.path.isdir(content))
        ambiguous = n_topics[_norm(content)] > 1
        out.append(Retiree(
            ambiguous=ambiguous,
            infohash=t["hash"], name=t["name"], content=content,
            progress=float(t["progress"]), added_on=int(t.get("added_on") or 0),
            shortfall=shortfall, topic_url=rec[1], lb_number=int(rec[0]),
            confidence=rec[2],
            match="suspect" if ambiguous else match_kind(rec[2], float(t["progress"]), shortfall)))
    out.sort(key=lambda r: (r.lb_number, r.topic_url))
    return out


# ── Retiring ─────────────────────────────────────────────────────────────────

def _write(fn) -> None:
    from backend.db_queue import get_write_queue
    get_write_queue().execute(fn)


def retire(r: Retiree, protected: Protected) -> dict:
    """Remove one torrent from qBittorrent, delete its overlay, queue the repost.

    Args:
        r: The torrent to retire.
        protected: Collection folders and mount roots (see overlay_rehome).

    Returns:
        Dict with ``ok``, ``leftover`` (overlay paths refused) and ``error``.
    """
    out = {"ok": False, "leftover": [], "error": ""}
    content = Path(r.content)
    try:
        sharers = shared_with(content, r.infohash, qbt_torrents())
    except Exception as exc:  # noqa: BLE001 — unknown sharing means do not delete
        out["error"] = f"could not list qBittorrent torrents: {exc}"
        return out
    removed = qbittorrent.remove_torrent(r.infohash, **tracker_seed._qbt_connection())
    if not removed.get("ok"):
        out["error"] = f"qBittorrent remove failed: {removed.get('error')}"
        return out

    if sharers:
        out["leftover"] = [f"{content}: kept, also used by torrent(s) {', '.join(sharers)}"]
    elif content.is_dir() and is_overlay_dir(content):
        try:
            guard_path(content, protected)
            out["leftover"] = _remove_tree(content, protected, allow_shared=True)
        except GuardError as exc:
            out["leftover"] = [str(exc)]

    status = "queued" if r.match != "suspect" else "review"
    reason = f"retired {time.strftime('%Y-%m-%d')}: {r.shortfall} at {r.progress:.1%}"

    def run(c):
        c.execute(
            "INSERT OR IGNORE INTO wtrf_reposts(topic_url, lb_number, old_infohash, old_name,"
            " old_folder, progress, shortfall, match, status) VALUES(?,?,?,?,?,?,?,?,?)",
            (r.topic_url, r.lb_number, r.infohash, r.name, r.content, r.progress,
             r.shortfall, r.match, status))
        if not r.ambiguous:  # several topics share the folder: can't tell whose row
            c.execute("UPDATE wtrf_downloads SET status='retired', error=? "
                      "WHERE seed_folder=? AND topic_url=?", (reason, r.content, r.topic_url))
    _write(run)
    out["ok"] = True
    return out


# ── Reposting ────────────────────────────────────────────────────────────────

def repost_rows(status: str = "queued", lb_number: int | None = None,
                topic_url: str | None = None, db_path=None) -> list[dict]:
    """``wtrf_reposts`` rows to work on, lowest LB first."""
    from backend import db

    sql, args = "SELECT * FROM wtrf_reposts WHERE 1=1", []
    if topic_url:
        sql += " AND topic_url=?"
        args.append(topic_url)
    elif lb_number is not None:
        sql += " AND lb_number=?"
        args.append(lb_number)
    else:
        sql += " AND status=?"
        args.append(status)
    with db.get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql + " ORDER BY lb_number, id", args)]


def set_repost(row_id: int, **fields) -> None:
    """Update columns of one ``wtrf_reposts`` row."""
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [row_id]
    _write(lambda c: c.execute(f"UPDATE wtrf_reposts SET {cols} WHERE id=?", vals))  # noqa: S608


def _collection(lb_number: int, db_path=None) -> tuple[Path | None, str]:
    from backend import db

    with db.get_connection(db_path) as conn:
        row = conn.execute("SELECT disk_path FROM my_collection WHERE lb_number=?",
                           (lb_number,)).fetchone()
        st = conn.execute("SELECT lb_status FROM lb_master WHERE lb_number=?",
                          (lb_number,)).fetchone()
    return (Path(row[0]) if row and row[0] else None), (st[0] if st else "")


def _existing_torrent(lb_number: int, folder: Path, db_path=None) -> dict | None:
    """A torrent already built from this exact folder and named after it."""
    from backend import db

    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT torrent_path, infohash FROM torrents WHERE lb_number=? AND source_folder=? "
            "ORDER BY id DESC", (lb_number, str(folder))).fetchall()
    for path, infohash in rows:
        if path and Path(path).is_file():
            try:
                if read_torrent(path).name == folder.name:
                    return {"torrent_path": path, "infohash": (infohash or "").lower()}
            except Exception:  # noqa: BLE001 — unreadable: build a new one
                continue
    return None


def prepare(row: dict, db_path=None) -> dict:
    """Make sure the replacement torrent exists and seeds at 100% in place.

    Args:
        row: A ``wtrf_reposts`` row.
        db_path: Optional DB path override.

    Returns:
        Dict with ``ok``, ``torrent_path``, ``infohash``, ``held`` (the LB is not
        public) and ``error``.
    """
    from backend import db
    from backend.torrent_maker import make_torrent

    out = {"ok": False, "torrent_path": "", "infohash": "", "held": False, "error": ""}
    folder, status = _collection(row["lb_number"], db_path)
    if status != "public":
        out.update(held=True, error=f"LB-{row['lb_number']:05d} is {status or 'unknown'} "
                                    "on the LB site — not reposted")
        return out
    if folder is None or not folder.is_dir():
        out["error"] = f"collection folder missing: {folder}"
        return out

    made = _existing_torrent(row["lb_number"], folder, db_path)
    if made is None:
        try:
            made = make_torrent(row["lb_number"], folder,
                                tracker_list=db.get_meta("tracker_list") or "best",
                                name=folder.name)
        except RuntimeError as exc:
            out["error"] = f"torrent build failed: {exc}"
            return out
    out["torrent_path"] = made["torrent_path"]
    info = read_torrent(made["torrent_path"])
    check = verify_folder(info, folder)
    if not check.complete:
        out["error"] = f"new torrent does not verify against {folder}: {check.summary()}"
        return out
    infohash = (made.get("infohash") or qbittorrent.torrent_file_infohash(
        made["torrent_path"]) or "").lower()
    out["infohash"] = infohash

    added = tracker_seed.qbt_seed(made["torrent_path"], str(folder),
                                  tracker_seed.SeedOptions(tracker=WTRF_TAG))
    if not added.get("ok"):
        out["error"] = f"qBittorrent: {added.get('error')}"
        return out
    lay = qbittorrent.get_torrent_layout(infohash, **tracker_seed._qbt_connection())
    states = lay.get("piece_states") or []
    if not (lay.get("ok") and lay.get("present") and states and all(s == 2 for s in states)):
        out["error"] = (f"qBittorrent does not report it complete "
                        f"({lay.get('state') or lay.get('error')})")
        return out
    out["ok"] = True
    return out


def post(row: dict, username: str, password: str, db_path=None) -> dict:
    """Prepare the torrent and reply it into the topic.

    Args:
        row: A ``wtrf_reposts`` row in status ``queued``.
        username: WTRF username.
        password: WTRF password.
        db_path: Optional DB path override.

    Returns:
        Dict with ``ok``, ``post_url`` and ``error``; the row is updated.
    """
    from backend.forum_poster import post_reply

    prep = prepare(row, db_path)
    if not prep["ok"]:
        set_repost(row["id"], status="held_private" if prep["held"] else "failed",
                   error=prep["error"], torrent_path=prep["torrent_path"] or None)
        return {"ok": False, "post_url": "", "error": prep["error"]}
    res = post_reply(row["topic_url"], prep["torrent_path"], REPOST_BODY, username, password)
    if not res.get("ok"):
        # 'unverified' may already be on the forum: never retried automatically.
        set_repost(row["id"], status="unverified" if res.get("unverified") else "failed",
                   error=res.get("error"),
                   torrent_path=prep["torrent_path"], new_infohash=prep["infohash"])
        return {"ok": False, "post_url": "", "error": res.get("error")}
    set_repost(row["id"], status="posted", post_url=res["post_url"], error=None,
               torrent_path=prep["torrent_path"], new_infohash=prep["infohash"],
               posted_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    return {"ok": True, "post_url": res["post_url"], "error": ""}
