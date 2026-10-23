#!/usr/bin/env python3
"""Copy out every overlay hardlink qBittorrent could still write through (BUG-386).

Walks every incomplete torrent in qBittorrent. For one seeding from an overlay
root (``<mount>/<Tracker> Seeds``), each file with more than one link that
overlaps a piece the client does not hold is replaced by a private copy, via
:func:`backend.tracker_seed.make_resume_safe` — the collection's file is only
ever read. An incomplete torrent seeding *in place* from a collection folder
has no link to break and is reported for the curator; it must stay stopped.

Torrent state is not changed: nothing is started, stopped or rechecked.
Dry-run by default.

Usage::

    .venv/bin/python3 tools/overlay_isolate.py 2>&1 | tee data/logs/overlay_isolate.log
    .venv/bin/python3 tools/overlay_isolate.py --apply 2>&1 | tee data/logs/overlay_isolate.log

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
from backend.tracker_seed import (  # noqa: E402
    _qbt_connection,
    is_overlay_root,
    make_resume_safe,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _incomplete_torrents() -> list[dict]:
    """Every torrent qBittorrent still has bytes left to download for."""
    conn = _qbt_connection()
    base = qbittorrent._base_url(conn["host"], conn["port"])
    s = qbittorrent._make_session(base, conn["api_key"])
    if not conn["api_key"]:
        err = qbittorrent._login(s, base, conn["username"], conn["password"])
        if err:
            raise SystemExit(f"qBittorrent login failed: {err.get('error')}")
    rows = s.get(base + "/api/v2/torrents/info", timeout=60).json()
    return [t for t in rows if int(t.get("amount_left") or 0) > 0]


def main() -> int:
    """Isolate every exposed overlay; return an exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="copy files out")
    args = ap.parse_args()

    torrents = _incomplete_torrents()
    logger.info("%d incomplete torrent(s) in qBittorrent", len(torrents))
    files = total = interior = 0
    exposed: list[str] = []
    in_place: list[str] = []
    failed: list[str] = []
    for t in torrents:
        if not is_overlay_root(t["save_path"]):
            in_place.append(f"{t['name']}  ({t['save_path']}, {t['state']}, "
                            f"{t['progress']:.2%})")
            continue
        res = make_resume_safe(t["hash"], dry_run=not args.apply)
        if not res["ok"]:
            failed.append(f"{t['name']}: {res['error']}")
            logger.error("FAILED  %s: %s", t["name"], res["error"])
            continue
        if not res["isolated"]:
            continue
        exposed.append(t["name"])
        files += len(res["isolated"])
        total += res["bytes"]
        interior += len(res["interior"])
        logger.info("%s  %3d file(s) %8.1f MB%s  %s",
                    "copied" if args.apply else "would copy",
                    len(res["isolated"]), res["bytes"] / 1e6,
                    f" ({len(res['interior'])} interior)" if res["interior"] else "",
                    t["name"])

    logger.info("%s %d file(s), %.1f GB, in %d overlay(s); %d with interior gaps",
                "copied" if args.apply else "would copy", files, total / 1e9,
                len(exposed), interior)
    for line in in_place:
        logger.warning("IN-PLACE incomplete — keep stopped: %s", line)
    if failed:
        logger.error("%d overlay(s) could not be isolated — still exposed", len(failed))
    if not args.apply:
        logger.info("dry run — re-run with --apply to copy files out")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
