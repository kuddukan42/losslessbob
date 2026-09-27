#!/usr/bin/env python3
"""Undo the WTRF overlays a full drive left half-built, so the walk redoes them.

The seed walk of 2026-09-26/27 kept going after ``/mnt/DYLAN1`` filled
(BUG-364): overlays hit ``[Errno 28]`` mid-build and were still handed to
qBittorrent short, which then set out to download most of each folder onto the
full drive. This finds those torrents — overlay names the walk log shows
failing with ENOSPC, still under 100% in qBittorrent, saved under a
``WTRF Seeds`` folder — and for each one:

1. removes it from qBittorrent (``deleteFiles=false``);
2. deletes the overlay folder — hardlinks and copies only; unlinking a
   hardlink leaves the collection's copy untouched, and any folder not directly
   inside a ``WTRF Seeds`` directory is refused;
3. writes a ``disk_full`` ``wtrf_downloads`` row for its topic, which the walk
   treats as untried.

Once space is free, re-run the walk over the affected pages (the script prints
the command). The DB is backed up to ``data/backups/`` before any write.
Dry-run by default.

Usage::

    .venv/bin/python3 tools/wtrf_requeue_disk_full.py \\
        data/logs/wtrf_seed_20260926_184240.log            # preview
    .venv/bin/python3 tools/wtrf_requeue_disk_full.py \\
        data/logs/wtrf_seed_20260926_184240.log --apply    # do it

Must be run from the project root directory.
"""
import argparse
import json
import logging
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials  # noqa: E402
from backend.qbittorrent import _base_url, _login, _make_session  # noqa: E402
from backend.wtrf_board import STATUS_DISK_FULL, TOPICS_PER_PAGE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OVERLAY_DIRNAME = "WTRF Seeds"
BACKUP_DIR = _project_root / "data" / "backups"

# "  overlay: <name>/<file>: [Errno 28] …" and
# "hardlink failed for <name>/<file> ([Errno 28] …"
_ENOSPC_RE = re.compile(r"(?:overlay: |hardlink failed for )([^/]+)/.*\[Errno 28\]")
_OFFSET_RE = re.compile(r"board=\d+\.(\d+)")


def enospc_overlays(log: Path) -> tuple[set[str], int | None]:
    """Return the overlay names that hit ENOSPC, and the board offset of the first.

    Args:
        log: A ``wtrf_seed_*.log`` from the walk.

    Returns:
        (overlay folder names, listing offset the first failure was on, or None).
    """
    names: set[str] = set()
    offset = first_offset = None
    with log.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if m := _OFFSET_RE.search(line):
                offset = int(m.group(1))
            if m := _ENOSPC_RE.search(line):
                names.add(m.group(1))
                if first_offset is None:
                    first_offset = offset
    return names, first_offset


def latest_row(con: sqlite3.Connection, folder: str) -> sqlite3.Row | None:
    """Return the newest ``wtrf_downloads`` row seeded from ``folder``.

    Args:
        con: Open DB connection with ``row_factory = sqlite3.Row``.
        folder: The overlay directory.

    Returns:
        The row, or None.
    """
    return con.execute(
        "SELECT * FROM wtrf_downloads WHERE seed_folder = ? "
        "ORDER BY attempted_at DESC, id DESC LIMIT 1", (folder.rstrip("/"),),
    ).fetchone()


def backup_db() -> Path:
    """Snapshot the live DB with sqlite's online backup and quick_check it.

    Returns:
        The backup file's path.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"losslessbob_{datetime.now():%Y%m%d_%H%M%S}_pre_requeue.db"
    src = sqlite3.connect(database.DB_PATH)
    out = sqlite3.connect(dest)
    try:
        src.backup(out)
        ok = out.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        out.close()
        src.close()
    if ok != "ok":
        raise SystemExit(f"backup quick_check failed: {ok}")
    return dest


def main() -> int:
    """Requeue every ENOSPC overlay; return an exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", type=Path, help="the walk's wtrf_seed_*.log")
    ap.add_argument("--apply", action="store_true",
                    help="remove torrents, delete overlays, write DB rows")
    args = ap.parse_args()

    names, first_offset = enospc_overlays(args.log)
    logger.info("%d overlay(s) hit ENOSPC in %s", len(names), args.log.name)
    if not names:
        return 0

    base = _base_url(database.get_meta("qbt_host") or "localhost",
                     int(database.get_meta("qbt_port") or 8080))
    user, pw = get_credentials(SERVICE_QBT)
    _, key = get_credentials(SERVICE_QBT_KEY)
    s = _make_session(base, key or "")
    if not key and (err := _login(s, base, user or "", pw or "")):
        logger.error(err["error"])
        return 1

    torrents = [
        t for t in s.get(base + "/api/v2/torrents/info",
                         params={"category": "losslessbob"}, timeout=60).json()
        if Path(t["content_path"]).name in names
        and Path(t["content_path"]).parent.name == OVERLAY_DIRNAME
        and t["progress"] < 1
    ]
    logger.info("%d of them are in qBittorrent short of 100%%", len(torrents))

    con = sqlite3.connect(database.DB_PATH)
    con.row_factory = sqlite3.Row
    plan = []
    for t in torrents:
        row = latest_row(con, t["content_path"])
        if row is None or not row["topic_url"]:
            logger.warning("skip (no wtrf_downloads topic): %s", t["name"][:60])
            continue
        plan.append((t, row))
        logger.info("%6.2f%%  %7.0f MB left  LB-%05d  %s", t["progress"] * 100,
                    t["amount_left"] / 1e6, row["lb_number"], t["content_path"])
    con.close()

    page = first_offset // TOPICS_PER_PAGE + 1 if first_offset is not None else None
    rerun = (f"tools/wtrf.sh --start-page {page}" if page
             else "tools/wtrf_resume.sh")
    if not args.apply:
        logger.info("dry run — %d torrent(s) would be requeued; re-run with --apply",
                    len(plan))
        logger.info("afterwards, once the drive has space: %s", rerun)
        return 0

    logger.info("DB backed up to %s", backup_db())
    done = 0
    for t, row in plan:
        overlay = Path(t["content_path"])
        r = s.post(base + "/api/v2/torrents/delete",
                   data={"hashes": t["hash"], "deleteFiles": "false"}, timeout=30)
        if r.status_code not in (200, 204):
            logger.warning("qBittorrent refused removing %s: HTTP %d", t["name"][:60],
                           r.status_code)
            continue
        if overlay.parent.name == OVERLAY_DIRNAME and overlay.is_dir():
            shutil.rmtree(overlay)
        database.add_wtrf_download(
            lb_number=row["lb_number"], topic_url=row["topic_url"],
            torrent_path=row["torrent_path"], confidence=row["confidence"],
            signals_json=json.dumps({**json.loads(row["signals_json"] or "{}"),
                                     "via": "board_walk"}),
            status=STATUS_DISK_FULL,
            error="requeued: overlay half-built on a full drive (BUG-364)",
            seed_folder="",
        )
        done += 1
        logger.info("requeued LB-%05d  %s", row["lb_number"], overlay.name)

    logger.info("requeued %d of %d; once the drive has space: %s", done, len(plan), rerun)
    return 0


if __name__ == "__main__":
    sys.exit(main())
