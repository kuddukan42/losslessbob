"""CLI for the Show Dossier QC rule engine (TODO-342 Phase 2).

Usage::

    .venv/bin/python3 -m backend.qc run
    .venv/bin/python3 -m backend.qc run --rule R-O1
    .venv/bin/python3 -m backend.qc run --db path/to/other.db

Prints one line per rule run: id, severity, open count, new, fixed, reopened.
"""
from __future__ import annotations

import argparse
import logging

from backend import db
from backend.paths import DB_PATH
from backend.qc.rules import RULES
from backend.qc.store import run_all

_log = logging.getLogger(__name__)


def _cmd_run(args: argparse.Namespace) -> int:
    if args.rule and args.rule not in RULES:
        _log.error("unknown rule: %s (known: %s)", args.rule, ", ".join(sorted(RULES)))
        return 1
    db_path = args.db or DB_PATH
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    rule_ids = [args.rule] if args.rule else None
    for stats in run_all(conn, rule_ids):
        _log.info(
            "%-6s %-5s open=%-6d new=%-6d fixed=%-6d reopened=%d", stats.rule_id,
            RULES[stats.rule_id].severity, stats.n_open, stats.n_new, stats.n_fixed,
            stats.n_reopened,
        )
    return 0


def main() -> int:
    """Parse argv and run the requested QC subcommand. Returns process exit status."""
    parser = argparse.ArgumentParser(prog="backend.qc")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run QC rules and reconcile qc_findings")
    run_p.add_argument("--rule", help="Run only this rule ID (default: all rules)")
    run_p.add_argument("--db", help="DB path (default: backend.paths.DB_PATH)")
    run_p.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
