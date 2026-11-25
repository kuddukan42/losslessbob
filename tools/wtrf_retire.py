#!/usr/bin/env python3
"""Retire old WTRF seeds that will never complete, and queue them for reposting.

Picks every qBittorrent torrent tagged ``wtrf`` that is below 100% and was added
at least --min-age-days ago, then (with --apply) removes it from qBittorrent
(files kept), unlinks its overlay through the collection-safety guard, marks
the wtrf_downloads row 'retired', and queues a wtrf_reposts row. Topics whose
LB match is weak and not confirmed by content go to 'review' instead of the
queue. The full list is always written to a CSV.

Dry run by default.

Usage:
    .venv/bin/python3 tools/wtrf_retire.py                 # list, change nothing
    .venv/bin/python3 tools/wtrf_retire.py --apply         # retire them all
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from collections import Counter
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend import wtrf_repost as wr  # noqa: E402
from backend.overlay_rehome import load_protected  # noqa: E402

LOG_DIR = _project_root / "data" / "logs"


def main() -> int:
    """Entry point. Returns a process exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--apply", action="store_true", help="Retire. Without it nothing changes.")
    p.add_argument("--min-age-days", type=float, default=wr.MIN_AGE_DAYS,
                   help=f"Only torrents added at least this long ago (default {wr.MIN_AGE_DAYS}).")
    p.add_argument("--limit", type=int, default=0, help="With --apply, stop after N.")
    args = p.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "wtrf_retire.log"),
                                  logging.StreamHandler()])
    database.init_db()

    retirees = wr.find_retirees(args.min_age_days)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = LOG_DIR / f"wtrf_retire_{stamp}.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["lb", "match", "confidence", "progress", "shortfall", "topic_url",
                    "torrent", "seed_folder"])
        for r in retirees:
            w.writerow([r.lb_number, r.match, r.confidence, f"{r.progress:.4f}", r.shortfall,
                        r.topic_url, r.name, r.content])
    for r in retirees:
        print(f"LB-{r.lb_number:05d}  {r.match:10s} {r.progress:6.1%}  {r.shortfall:24s} "
              f"{r.topic_url}")
    print(f"\n{len(retirees)} to retire — " + ", ".join(
        f"{k} {v}" for k, v in Counter(r.match for r in retirees).most_common()))
    print("by shortfall: " + ", ".join(
        f"{k} {v}" for k, v in Counter(r.shortfall for r in retirees).most_common()))
    print(f"List: {csv_path}")
    if not args.apply:
        print("Dry run — nothing changed. Add --apply to retire.")
        return 0

    protected = load_protected()
    done = 0
    for r in retirees:
        if args.limit and done >= args.limit:
            break
        res = wr.retire(r, protected)
        if not res["ok"]:
            print(f"FAILED LB-{r.lb_number:05d} {r.name}: {res['error']}\nStopping.")
            return 1
        for left in res["leftover"]:
            print(f"  left in place: {left}")
        done += 1
    print(f"\n{done} retired. Queue: tools/wtrf_repost.py list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
