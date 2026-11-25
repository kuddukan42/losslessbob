#!/usr/bin/env python3
"""Move TUIT/WTRF seed overlays to the drive their LB now lives on (TODO-376).

A cross-drive move leaves a seed overlay behind on the old drive holding its own
copy of the audio. This rebuilds it next to the collection folder (audio
hardlinked to the collection, overlay-only files copied), points qBittorrent at
it, and deletes the old overlay. The collection folder is never written to; see
backend/overlay_rehome.py for the safety rules.

Dry run by default: prints every planned link, copy and delete with full paths
and changes nothing. --apply works one overlay at a time and stops at the first
error.

Usage:
    .venv/bin/python3 tools/overlay_rehome.py                 # dry run, all LBs
    .venv/bin/python3 tools/overlay_rehome.py --lb 16054      # dry run, one LB
    .venv/bin/python3 tools/overlay_rehome.py --lb 16054 --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend import overlay_rehome as rh  # noqa: E402

LOG_PATH = _project_root / "data" / "logs" / "overlay_rehome.log"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--lb", type=int, action="append", default=None,
                   help="Only this LB number (repeatable). Default: every recorded seed.")
    p.add_argument("--apply", action="store_true",
                   help="Do it. Without this nothing is changed.")
    p.add_argument("--limit", type=int, default=0,
                   help="With --apply, stop after this many overlays (0 = no limit).")
    p.add_argument("--brief", action="store_true",
                   help="One line per overlay instead of every file.")
    return p


def _print_plan(plan: rh.RehomePlan, brief: bool) -> None:
    rec = plan.record
    head = f"LB-{rec.lb_number:05d} {rec.tracker.upper()}"
    if plan.skip:
        print(f"{head}  SKIP  {plan.skip}  [{rec.overlay}]")
        return
    print(f"{head}  {rec.overlay}  ->  {plan.new_overlay}  "
          f"link {len(plan.links)}, copy {len(plan.copies)} "
          f"({plan.copy_bytes / 1e6:.1f} MB), frees {plan.freed_bytes / 1e9:.2f} GB")
    if brief:
        return
    for rel in sorted(plan.sizes):
        if rel in plan.links:
            print(f"    link   {plan.new_overlay / rel}  =  {plan.links[rel]}")
        else:
            print(f"    copy   {plan.new_overlay / rel}  <-  {rec.overlay / rel}")
    for rel in sorted(plan.sizes):
        print(f"    delete {rec.overlay / rel}")


def main() -> int:
    """Entry point. Returns a process exit code."""
    args = _build_parser().parse_args()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])
    database.init_db()

    disabled = database.get_meta(rh.DISABLED_META)
    if disabled:
        print(f"REFUSED: overlay re-homing is disabled — {disabled}\n"
              f"Investigate, then clear meta '{rh.DISABLED_META}'.")
        return 2

    plans = rh.find_candidates(args.lb)
    if not plans:
        print("No overlays sit on a different drive from their collection folder.")
        return 0
    for plan in plans:
        _print_plan(plan, args.brief)
    todo = [p for p in plans if not p.skip]
    print(f"\n{len(todo)} to re-home, {len(plans) - len(todo)} skipped, "
          f"{sum(p.freed_bytes for p in todo) / 1e9:.2f} GB to free, "
          f"{sum(p.copy_bytes for p in todo) / 1e9:.2f} GB to copy.")
    if not args.apply:
        print("Dry run — nothing changed. Add --apply to do it.")
        return 0

    protected = rh.load_protected()
    done = 0
    for plan in todo:
        if args.limit and done >= args.limit:
            break
        rec = plan.record
        print(f"\nLB-{rec.lb_number:05d} {rec.tracker.upper()}: re-homing {rec.overlay}")
        try:
            res = rh.rehome(plan, protected)
        except rh.RehomeError as exc:
            print(f"STOPPED — {exc}")
            return 2
        if not res["ok"]:
            print(f"FAILED — {res['error']}\nStopping at the first error.")
            return 1
        print(f"  ok: {res['new_overlay']} ({res['linked']} linked, {res['copied']} copied), "
              f"freed {res['freed'] / 1e9:.2f} GB")
        for left in res["leftover"]:
            print(f"  left in place: {left}")
        done += 1
    print(f"\n{done} overlay(s) re-homed. Log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
