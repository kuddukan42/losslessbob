#!/usr/bin/env python3
"""Print the pipeline freshness table (backend.refresh.compute_plan).

Usage:
    .venv/bin/python3 tools/refresh_status.py
    .venv/bin/python3 tools/refresh_status.py --trigger T1
    .venv/bin/python3 tools/refresh_status.py --stale-only
    .venv/bin/python3 tools/refresh_status.py --json
    .venv/bin/python3 tools/refresh_status.py --exit-nonzero-if-stale

This is a terminal/cron wrapper over the same `compute_plan()` the
`GET /api/refresh/status` route serves -- read-only, no writes, safe to run
against the live DB at any time. Exit code is 0 unless
`--exit-nonzero-if-stale` is passed and at least one step is stale or blocked.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import refresh as _refresh  # noqa: E402
from backend import refresh_exec as _refresh_exec  # noqa: E402

logger = logging.getLogger(__name__)

_HEADER = (
    f"{'STEP':<22}{'TRIGGER':<9}{'STATE':<9}{'VER':<5}"
    f"{'LAST RUN':<13}{'AGE':<7}{'BACKLOG':<9}HOW TO RUN"
)

# version.state -> single-glance column value (TODO-306 Phase 2).
_VER_DISPLAY = {"ok": "ok", "changed": "chg", "unstamped": "-", "n/a": "-"}


def _fmt_row(step: dict) -> str:
    """Format one step dict as a single-line table row."""
    last_run = (step["last_run"] or "-")[:10]
    age = f"{step['age_days']}d" if step["age_days"] is not None else "-"
    backlog = str(step["backlog"]) if step["backlog"] is not None else "-"
    ver_state = (step.get("version") or {}).get("state", "n/a")
    ver = _VER_DISPLAY.get(ver_state, "-")
    return (
        f"{step['step_id']:<22}{step['trigger']:<9}{step['state']:<9}{ver:<5}"
        f"{last_run:<13}{age:<7}{backlog:<9}{step['how_to_run']}"
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", choices=("T1", "T2", "T3", "T4"), default=None)
    parser.add_argument("--stale-only", action="store_true", help="Only show stale/blocked rows")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON payload")
    parser.add_argument(
        "--exit-nonzero-if-stale", action="store_true",
        help="Exit 1 if any step is stale or blocked (default: always exit 0)",
    )
    parser.add_argument("--db", default=None, help="Override the DB path")
    parser.add_argument(
        "--chain", metavar="STEP_ID|T1..T4", default=None,
        help="Print the plan_chain() dry-run for this step_id or trigger and exit "
        "without running anything",
    )
    parser.add_argument(
        "--include-expensive", action="store_true",
        help="With --chain: include very_slow/human_gate steps in runnable",
    )
    return parser


_CHAIN_HEADER = f"{'STEP':<22}{'MODE':<8}{'COST':<10}{'STATE':<9}REASON"


def _print_chain(chain_arg: str, *, include_expensive: bool, db_path: str | None) -> int:
    """Print the ``plan_chain()`` dry-run and return the process exit code."""
    kwargs = {"include_expensive": include_expensive, "db_path": db_path}
    if chain_arg in ("T1", "T2", "T3", "T4"):
        plan = _refresh_exec.plan_chain(trigger=chain_arg, **kwargs)
    else:
        plan = _refresh_exec.plan_chain(step_id=chain_arg, **kwargs)

    lines = [f"scope: {plan['scope']}", "", "RUNNABLE", _CHAIN_HEADER]
    for step in plan["runnable"]:
        lines.append(
            f"{step['step_id']:<22}{step['mode']:<8}{step['cost']:<10}"
            f"{step['state']:<9}{step['reason']}"
        )
    lines.append("")
    lines.append("EXCLUDED")
    for step in plan["excluded"]:
        lines.append(f"{step['step_id']:<22}{step['why']}")
    lines.append("")
    lines.append("MANUAL")
    for step in plan["manual"]:
        lines.append(f"{step['step_id']:<22}{step['why']}")
    if plan["blocked_by_running"]:
        lines.append("")
        lines.append(f"blocked_by_running: {', '.join(plan['blocked_by_running'])}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point: print the freshness table and return the exit code."""
    logging.basicConfig(level=logging.WARNING)
    args = build_parser().parse_args(argv)

    if args.chain:
        return _print_chain(
            args.chain, include_expensive=args.include_expensive, db_path=args.db,
        )

    plan = _refresh.compute_plan(db_path=args.db, trigger=args.trigger)

    if args.json:
        sys.stdout.write(json.dumps(plan, indent=2) + "\n")
    else:
        lines = [_HEADER]
        for step in plan["steps"]:
            if args.stale_only and step["state"] not in ("stale", "blocked"):
                continue
            lines.append(_fmt_row(step))
        lag = plan["publish_lag"]
        lines.append("")
        lines.append(
            f"publish_lag: published_at={lag['published_at'] or '-'} "
            f"days_since={lag['days_since'] if lag['days_since'] is not None else '-'} "
            f"lb_status_changes_since={lag['lb_status_changes_since']} "
            f"entries_scraped_since={lag['entries_scraped_since']}"
        )
        lines.append(
            f"stale={plan['stale_count']} blocked={plan['blocked_count']} "
            f"unknown={plan['unknown_count']}"
        )
        sys.stdout.write("\n".join(lines) + "\n")

    if args.exit_nonzero_if_stale and (plan["stale_count"] or plan["blocked_count"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
