#!/usr/bin/env python3
"""Repost retired WTRF topics with a fresh torrent built from the collection.

Works the wtrf_reposts queue written by tools/wtrf_retire.py, one topic at a
time and only when you say so. For each topic: build a torrent from the LB's
collection folder (or reuse one already built from it), check it verifies
100% against the folder, seed it in place in qBittorrent, then reply into the
original topic with the torrent attached and print the reply's URL.

Only LBs that are public on the LB site are posted; others are held.

Usage:
    .venv/bin/python3 tools/wtrf_repost.py list                       # queue counts + next up
    .venv/bin/python3 tools/wtrf_repost.py list --status review       # weak matches to check
    .venv/bin/python3 tools/wtrf_repost.py approve 1234 https://...   # review -> queue (LB or URL)
    .venv/bin/python3 tools/wtrf_repost.py skip 1234                  # never post this one
    .venv/bin/python3 tools/wtrf_repost.py post --next 1              # preview the next post
    .venv/bin/python3 tools/wtrf_repost.py post --next 1 --apply      # post it, print the URL
    .venv/bin/python3 tools/wtrf_repost.py post --lb 1234 --apply     # post one LB's topic(s)
"""
from __future__ import annotations

import argparse
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
from backend.credentials import SERVICE_WTRF, get_credentials  # noqa: E402

LOG_PATH = _project_root / "data" / "logs" / "wtrf_repost.log"


def _all_rows() -> list[dict]:
    with database.get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM wtrf_reposts ORDER BY lb_number, id")]


def _select(keys: list[str]) -> list[dict]:
    rows = []
    for key in keys:
        if key.isdigit():
            rows += wr.repost_rows(lb_number=int(key))
        else:
            rows += wr.repost_rows(topic_url=key)
    return rows


def cmd_list(args) -> int:
    rows = _all_rows()
    print("queue: " + ", ".join(f"{k} {v}" for k, v in
                                Counter(r["status"] for r in rows).most_common()))
    shown = rows if args.status == "all" else [r for r in rows if r["status"] == args.status]
    for r in shown[: args.max or None]:
        print(f"LB-{r['lb_number']:05d}  {r['status']:12s} {r['match']:10s} "
              f"{(r['progress'] or 0):6.1%}  {r['shortfall'] or '':24s} "
              f"{r['post_url'] or r['topic_url']}"
              + (f"\n           error: {r['error']}" if r["error"] else ""))
    return 0


def cmd_move(keys: list[str], status: str, only_from: tuple[str, ...]) -> int:
    rows = _select(keys)
    moved = 0
    for r in rows:
        if r["status"] in only_from:
            wr.set_repost(r["id"], status=status, error=None)
            moved += 1
            print(f"LB-{r['lb_number']:05d} {r['status']} -> {status}  {r['topic_url']}")
        else:
            print(f"LB-{r['lb_number']:05d} left as {r['status']}  {r['topic_url']}")
    return 0 if moved else 1


def cmd_post(args) -> int:
    if args.lb is not None or args.topic:
        rows = (wr.repost_rows(lb_number=args.lb) if args.lb is not None
                else wr.repost_rows(topic_url=args.topic))
        rows = [r for r in rows if r["status"] in ("queued", "failed")]
    else:
        rows = wr.repost_rows("queued")[: args.next]
    if not rows:
        print("Nothing queued for that selection.")
        return 1
    if not args.apply:
        for r in rows:
            print(f"LB-{r['lb_number']:05d}  {r['topic_url']}\n"
                  f"  was: {r['old_name']} ({(r['progress'] or 0):.1%}, {r['shortfall']})\n"
                  f"  reply text: {wr.REPOST_BODY}\n"
                  f"  attachment: a new torrent of the LB's collection folder, seeded first")
        print("\nPreview only. Add --apply to post.")
        return 0

    user, password = get_credentials(SERVICE_WTRF)
    if not user or not password:
        print("No WTRF credentials stored (Setup → WTRF Forum).")
        return 2
    for i, r in enumerate(rows):
        if i:
            time.sleep(args.delay)
        print(f"LB-{r['lb_number']:05d}  {r['topic_url']}")
        res = wr.post(r, user, password)
        if not res["ok"]:
            print(f"  FAILED — {res['error']}\nStopping.")
            return 1
        print(f"  posted: {res['post_url']}")
    return 0


def main() -> int:
    """Entry point. Returns a process exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list", help="Show the queue.")
    pl.add_argument("--status", default="queued",
                    help="queued / review / posted / failed / held_private / skipped / all")
    pl.add_argument("--max", type=int, default=50, help="Rows to show (0 = all).")
    pa = sub.add_parser("approve", help="Move review rows into the queue.")
    pa.add_argument("keys", nargs="+", help="LB numbers or topic URLs")
    ps = sub.add_parser("skip", help="Never post these.")
    ps.add_argument("keys", nargs="+", help="LB numbers or topic URLs")
    pp = sub.add_parser("post", help="Post the next N, or one LB / topic.")
    g = pp.add_mutually_exclusive_group(required=True)
    g.add_argument("--next", type=int, help="Next N queued topics.")
    g.add_argument("--lb", type=int, help="This LB's topic(s).")
    g.add_argument("--topic", help="This topic URL.")
    pp.add_argument("--apply", action="store_true", help="Post. Without it: preview only.")
    pp.add_argument("--delay", type=float, default=60.0,
                    help="Seconds between posts (default 60).")
    args = p.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_PATH)])
    database.init_db()
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "approve":
        return cmd_move(args.keys, "queued", ("review",))
    if args.cmd == "skip":
        return cmd_move(args.keys, "skipped", ("queued", "review", "failed", "held_private"))
    return cmd_post(args)


if __name__ == "__main__":
    sys.exit(main())
