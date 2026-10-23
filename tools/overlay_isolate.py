#!/usr/bin/env python3
"""Lock every torrent in qBittorrent so it can never write into the collection.

Runs :func:`backend.tracker_seed.make_resume_safe` on each torrent (BUG-386/387):

* every file the client already holds in full is set to "do not download" —
  the priority survives rechecks and restarts, so a piece that later fails its
  hash is never fetched again, not even through a manual Force recheck + Start;
* an overlay (``<mount>/<Tracker> Seeds``) still downloading has each hardlink
  that shares a piece with an unfinished file replaced by a private copy — the
  collection's file is only ever read;
* an unfinished torrent seeding *in place* from a collection folder has no
  link to break and is reported for the curator; it must stay stopped.

A torrent holding no piece at all has never been checked; it is reported and
skipped, or with ``--recheck`` hashed while it stays stopped and then locked.
Nothing is ever started or stopped. Dry-run by default.

Usage::

    .venv/bin/python3 tools/overlay_isolate.py 2>&1 | tee data/logs/overlay_isolate.log
    .venv/bin/python3 tools/overlay_isolate.py --apply 2>&1 | tee data/logs/overlay_isolate.log
    .venv/bin/python3 tools/overlay_isolate.py --apply --recheck 2>&1 \
        | tee -a data/logs/overlay_isolate.log

Must be run from the project root directory.
"""
import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import qbittorrent  # noqa: E402
from backend.tracker_seed import _qbt_connection, make_resume_safe  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _all_torrents() -> list[dict]:
    """Every torrent in qBittorrent."""
    conn = _qbt_connection()
    base = qbittorrent._base_url(conn["host"], conn["port"])
    s = qbittorrent._make_session(base, conn["api_key"])
    if not conn["api_key"]:
        err = qbittorrent._login(s, base, conn["username"], conn["password"])
        if err:
            raise SystemExit(f"qBittorrent login failed: {err.get('error')}")
    return s.get(base + "/api/v2/torrents/info", timeout=120).json()


def main() -> int:
    """Lock every torrent; return an exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="set priorities, copy files out")
    ap.add_argument("--recheck", action="store_true",
                    help="recheck (while stopped) and lock never-checked torrents")
    args = ap.parse_args()
    verb = "" if args.apply else "would "

    torrents = _all_torrents()
    logger.info("%d torrent(s) in qBittorrent", len(torrents))
    frozen = locked = files = total = 0
    in_place: list[str] = []
    unchecked: list[str] = []
    failed: list[str] = []
    for n, t in enumerate(torrents, 1):
        res = make_resume_safe(t["hash"], dry_run=not args.apply, recheck=args.recheck)
        if res["in_place"]:
            in_place.append(f"{t['name']}  ({t['save_path']}, {t['state']})")
            continue
        if not res["ok"]:
            (unchecked if res["error"].startswith("never checked") else failed).append(
                f"{t['name']}: {res['error']}")
            continue
        if res["frozen"]:
            locked += 1
            frozen += res["frozen"]
        if res["isolated"]:
            files += len(res["isolated"])
            total += res["bytes"]
            logger.info("%scopy %3d file(s) %8.1f MB  %s", verb, len(res["isolated"]),
                        res["bytes"] / 1e6, t["name"])
        if n % 500 == 0:
            logger.info("… %d/%d", n, len(torrents))

    logger.info("%slock %d file(s) in %d torrent(s); %scopy %d file(s), %.1f GB",
                verb, frozen, locked, verb, files, total / 1e9)
    for line in in_place:
        logger.warning("IN-PLACE unfinished — keep stopped: %s", line)
    for line in unchecked:
        logger.warning("NEVER CHECKED — skipped: %s", line)
    for line in failed:
        logger.error("FAILED  %s", line)
    if failed:
        logger.error("%d torrent(s) could not be locked", len(failed))
    if not args.apply:
        logger.info("dry run — re-run with --apply to lock")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
