#!/usr/bin/env python3
"""build_rerun_queue.py — generate a targeted tapematch re-run queue.

Implements Task 6 of instructions/CC_TAPEMATCH_FIXES.md.

Queries observations.db's ``latest_pairs`` view (see migrate_observations.py,
Task 2) for concert dates with at least one
``lb_says_same=1 AND tapematch_verdict='different_family'`` pair — a miss
against LB commentary — ordered by miss count descending. Writes
``tools/tapematch/rerun_queue.txt``, one date per line with the miss count as
a trailing comment, for use with ``tapematch_session.py --batch``.

Dates with zero such misses are never queued (per spec step 5 — they don't
need re-running).

Usage:
    .venv/bin/python3 tools/tapematch/build_rerun_queue.py
    .venv/bin/python3 tools/tapematch/build_rerun_queue.py --since 2026-06-13T18:00:00
    .venv/bin/python3 tools/tapematch/build_rerun_queue.py --since <git-ref>
    .venv/bin/python3 tools/tapematch/build_rerun_queue.py --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

OBS_DB_PATH   = Path(__file__).parent / "observations.db"
QUEUE_PATH    = Path(__file__).parent / "rerun_queue.txt"
PROJECT_ROOT  = Path(__file__).parent.parent.parent

QUERY = """
SELECT concert_date, COUNT(*) AS misses, MAX(run_at) AS last_run
FROM latest_pairs
WHERE lb_says_same = 1 AND tapematch_verdict = 'different_family'
GROUP BY concert_date
ORDER BY misses DESC, concert_date ASC
"""


def resolve_since(value: str | None) -> str | None:
    """Resolve --since to an ISO 8601 timestamp.

    Accepts either an ISO 8601 timestamp directly, or a git ref (commit,
    branch, tag) whose author date is used — e.g. the Task 4/5 fix commit
    once it lands.
    """
    if value is None:
        return None
    try:
        datetime.fromisoformat(value)
        return value
    except ValueError:
        pass
    result = subprocess.run(
        ["git", "show", "-s", "--format=%aI", value],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(
            f"--since value is not an ISO timestamp or a valid git ref: {value!r}"
        )
    return result.stdout.strip()


def build_queue(
    conn: sqlite3.Connection, since: str | None = None
) -> tuple[list[tuple[str, int]], list[tuple[str, int, str]]]:
    """Return (queue, excluded) from latest_pairs.

    queue:    [(concert_date, miss_count), ...] ordered by miss_count desc
    excluded: [(concert_date, miss_count, last_run), ...] — dates whose most
              recent run (last_run) is at/after `since`, i.e. already
              re-validated post-fix and not re-queued.
    """
    queue: list[tuple[str, int]] = []
    excluded: list[tuple[str, int, str]] = []
    for date, misses, last_run in conn.execute(QUERY).fetchall():
        if since is not None and last_run is not None and last_run >= since:
            excluded.append((date, misses, last_run))
            continue
        queue.append((date, misses))
    return queue, excluded


def format_line(date: str, misses: int) -> str:
    unit = "miss" if misses == 1 else "misses"
    return f"{date}  # {misses} {unit}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--since", default=None, metavar="TIMESTAMP|REF",
        help="Exclude dates whose most recent run is at/after this ISO "
             "timestamp or git ref (e.g. the Task 4/5 fix commit) — they're "
             "already re-validated post-fix",
    )
    ap.add_argument(
        "--out", type=Path, default=QUEUE_PATH,
        help=f"Output path (default: {QUEUE_PATH})",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print the queue without writing the output file",
    )
    args = ap.parse_args(argv)

    since = resolve_since(args.since)

    conn = sqlite3.connect(str(OBS_DB_PATH))
    try:
        queue, excluded = build_queue(conn, since)
    finally:
        conn.close()

    total = len(queue) + len(excluded)
    print(f"Dates with >=1 lb_says_same=1/different_family miss: {total}")
    if since is not None:
        print(f"Excluding {len(excluded)} date(s) already re-run at/after {since}")
    print(f"Queue: {len(queue)} date(s)")

    lines = [format_line(date, misses) for date, misses in queue]

    if args.dry_run:
        for line in lines[:20]:
            print(f"  {line}")
        if len(lines) > 20:
            print(f"  … and {len(lines) - 20} more")
        print("\n[DRY RUN] — output file not written.")
        return 0

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} date(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
