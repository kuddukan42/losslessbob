#!/usr/bin/env python3
"""Print the next N eligible tapematch run dirs, ordered by triage priority.

Eligibility is the /tapematch-batch rule: has report.md, no analysis.md, the
run actually produced clusters, and the set is complete (DB entries == found on
disk).  Ordering adds backend.tapematch_autoflag's machine triage on top:

    auto_triage='attention' first, most rules fired first, then fewest DB
    entries first.

Rationale: an 'attention' date is where a written analysis is most likely to
say something, and among equally-suspicious dates the cheap ones (2-3 sources)
should clear before the expensive ones.  'clear' dates stay eligible, just last.

Usage:
    .venv/bin/python3 tools/tapematch/next_batch.py [N]     # default 5
    .venv/bin/python3 tools/tapematch/next_batch.py --stats
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "data" / "tapematch" / "runs"
APP_DB = REPO_ROOT / "data" / "losslessbob.db"

_COVERAGE_RE = re.compile(
    r"DB entries:\s*\*\*(\d+)\*\*.*?Found on disk:\s*\*\*(\d+)\*\*"
)


def eligible_dirs() -> "list[tuple[Path, int]]":
    """Return ``(run_dir, db_entry_count)`` for every eligible run dir."""
    out: "list[tuple[Path, int]]" = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        report = run_dir / "report.md"
        if not report.is_file() or (run_dir / "analysis.md").exists():
            continue
        text = report.read_text(errors="replace")
        if "=== CLUSTERS ===" not in text:
            continue
        m = _COVERAGE_RE.search(text)
        if not m:
            continue
        db_entries, found_disk = int(m.group(1)), int(m.group(2))
        if db_entries != found_disk:
            continue
        out.append((run_dir, db_entries))
    return out


def triage_by_date() -> "dict[str, tuple[str, int]]":
    """Return ``{concert_date: (verdict, n_rules_fired)}`` from the app DB."""
    if not APP_DB.exists():
        return {}
    conn = sqlite3.connect(f"file:{APP_DB}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT concert_date, auto_triage, auto_triage_reasons "
            "FROM tapematch_family_meta WHERE auto_triage IS NOT NULL "
            "GROUP BY concert_date"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}  # migration not applied yet — fall back to plain ordering
    finally:
        conn.close()
    out: "dict[str, tuple[str, int]]" = {}
    for concert_date, verdict, reasons in rows:
        try:
            n = len(json.loads(reasons or "[]"))
        except (TypeError, ValueError):
            n = 0
        out[concert_date] = (verdict, n)
    return out


def ranked() -> "list[tuple[Path, int, str, int]]":
    """Return eligible dirs as ``(dir, db_entries, verdict, n_rules)``, best first."""
    triage = triage_by_date()
    rows = []
    for run_dir, db_entries in eligible_dirs():
        concert_date = run_dir.name.split("_")[-1]
        verdict, n_rules = triage.get(concert_date, ("clear", 0))
        rows.append((run_dir, db_entries, verdict, n_rules))
    rows.sort(key=lambda r: (r[2] != "attention", -r[3], r[1], r[0].name))
    return rows


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("n", nargs="?", type=int, default=5, help="batch size (default 5)")
    ap.add_argument("--stats", action="store_true",
                    help="Print backlog counts instead of a batch.")
    args = ap.parse_args()

    rows = ranked()
    if args.stats:
        att = sum(1 for r in rows if r[2] == "attention")
        print(f"eligible: {len(rows)} | attention {att} | clear {len(rows) - att}")
        return 0

    for run_dir, db_entries, verdict, n_rules in rows[: args.n]:
        rel = run_dir.relative_to(REPO_ROOT)
        print(f"{rel}\t{db_entries} entries\t{verdict}\t{n_rules} rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
