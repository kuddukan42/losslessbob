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

A concert date can have several pending run dirs (re-runs after a re-ingest).
Those are emitted contiguously as one date group, and the trailing ``group``
column says which member of the group a row is.  A batch must never split a
date group across two writers: two analyses of the same date written
independently produce contradictory verdicts (seen 2026-08-19 on 2010-11-24,
where one run called a merge spurious and the other reported three families).
Use ``--newest-per-date`` to consider only each date's most recent run.

Usage:
    .venv/bin/python3 tools/tapematch/next_batch.py [N]     # default 5
    .venv/bin/python3 tools/tapematch/next_batch.py [N] --newest-per-date
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


def _iter_run_dirs() -> "list[Path]":
    """Return every run dir under ``RUNS_DIR``, sorted (chronological by name)."""
    if not RUNS_DIR.is_dir():
        return []
    return [p for p in sorted(RUNS_DIR.iterdir()) if p.is_dir()]


def _has_analysis(run_dir: Path) -> bool:
    """Return whether ``run_dir`` already has a written analysis.md."""
    return (run_dir / "analysis.md").exists()


def eligible_dirs() -> "list[tuple[Path, int]]":
    """Return ``(run_dir, db_entry_count)`` for every eligible run dir."""
    out: "list[tuple[Path, int]]" = []
    for run_dir in _iter_run_dirs():
        report = run_dir / "report.md"
        if not report.is_file() or _has_analysis(run_dir):
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


def newest_run_dir_by_date() -> "dict[str, Path]":
    """Return each concert date's most recent run dir, from ALL run dirs.

    Unlike :func:`eligible_dirs`, this does not filter on report.md,
    completeness, or analysis.md presence — it is the ground truth for "what
    is actually the latest run of this date", used to detect when a date's
    newest run has already been analysed while older, superseded runs of the
    same date are still sitting around eligible (TODO-326).
    """
    out: "dict[str, Path]" = {}
    for run_dir in _iter_run_dirs():
        concert_date = run_dir.name.split("_")[-1]
        # Run dir names are ``YYYYMMDD_HHMMSS_<date>``, which sort
        # chronologically, and _iter_run_dirs() is sorted — so the last dir
        # seen per date is the newest.
        out[concert_date] = run_dir
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


def superseded_eligible_dirs() -> "list[Path]":
    """Return eligible run dirs that are superseded re-runs (TODO-326).

    An eligible dir (no analysis.md of its own) is superseded when its
    concert date's true newest run dir is a *different* dir that already has
    an analysis.md — i.e. the date has since been re-run and analysed, but
    this older run dir predates that and would otherwise still look
    "eligible". These can never correctly be picked by any writer.
    """
    newest_by_date = newest_run_dir_by_date()
    out: "list[Path]" = []
    for run_dir, _db_entries in eligible_dirs():
        concert_date = run_dir.name.split("_")[-1]
        true_newest = newest_by_date.get(concert_date)
        if true_newest is not None and true_newest != run_dir and _has_analysis(true_newest):
            out.append(run_dir)
    return out


def ranked(newest_per_date: bool = False) -> "list[tuple[Path, int, str, int, str]]":
    """Return eligible dirs, best first, with same-date runs kept contiguous.

    Args:
        newest_per_date: Keep only each concert date's most recent run dir,
            dropping superseded earlier runs of the same date.  "Most recent"
            is judged against ALL run dirs for that date (see
            :func:`newest_run_dir_by_date`), not just the eligible ones — a
            date whose true newest run already has an analysis.md is dropped
            entirely rather than falling back to an older, superseded run
            (TODO-326).

    Returns:
        ``(dir, db_entries, verdict, n_rules, group)`` tuples, where ``group``
        is ``"i/j"`` — the row's position within its concert-date group.  Rows
        of one group are always adjacent.
    """
    triage = triage_by_date()
    by_date: "dict[str, list[tuple[Path, int, str, int]]]" = {}
    for run_dir, db_entries in eligible_dirs():
        concert_date = run_dir.name.split("_")[-1]
        verdict, n_rules = triage.get(concert_date, ("clear", 0))
        by_date.setdefault(concert_date, []).append(
            (run_dir, db_entries, verdict, n_rules)
        )

    newest_by_date = newest_run_dir_by_date() if newest_per_date else {}
    groups = []
    for concert_date, members in by_date.items():
        members.sort(key=lambda r: r[0].name)  # run dirs sort chronologically
        if newest_per_date:
            true_newest = newest_by_date.get(concert_date)
            if true_newest is not None and _has_analysis(true_newest):
                continue  # the real newest run is already analysed; skip the date
            members = [m for m in members if m[0] == true_newest]
            if not members:
                # The true newest run isn't itself eligible (missing report,
                # incomplete set, etc). Don't fall back to an older,
                # superseded run — wait for the newest to become eligible.
                continue
        # A group's priority is its most urgent / cheapest member.
        key = min((r[2] != "attention", -r[3], r[1], r[0].name) for r in members)
        groups.append((key, concert_date, members))

    groups.sort(key=lambda g: g[0])
    out: "list[tuple[Path, int, str, int, str]]" = []
    for _key, _concert_date, members in groups:
        total = len(members)
        for i, (run_dir, db_entries, verdict, n_rules) in enumerate(members, 1):
            out.append((run_dir, db_entries, verdict, n_rules, f"{i}/{total}"))
    return out


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("n", nargs="?", type=int, default=5, help="batch size (default 5)")
    ap.add_argument("--stats", action="store_true",
                    help="Print backlog counts instead of a batch.")
    ap.add_argument("--newest-per-date", action="store_true",
                    help="Consider only each concert date's most recent run dir.")
    args = ap.parse_args()

    rows = ranked(newest_per_date=args.newest_per_date)
    if args.stats:
        # Superseded runs can never correctly be picked (TODO-326), so they
        # never belong in "eligible" — strip them even without
        # --newest-per-date, which ranked() already excludes them under.
        superseded = superseded_eligible_dirs()
        if not args.newest_per_date and superseded:
            drop = {p.name for p in superseded}
            rows = [r for r in rows if r[0].name not in drop]
        att = sum(1 for r in rows if r[2] == "attention")
        dates = len({r[0].name.split("_")[-1] for r in rows})
        suffix = f" | superseded {len(superseded)} (excluded)" if superseded else ""
        print(
            f"eligible: {len(rows)} dirs / {dates} dates | "
            f"attention {att} | clear {len(rows) - att}{suffix}"
        )
        return 0

    # Never cut mid-group: a concert date's runs all go to the same writer.
    end = min(args.n, len(rows))
    while end < len(rows) and not rows[end][4].startswith("1/"):
        end += 1

    for run_dir, db_entries, verdict, n_rules, group in rows[:end]:
        rel = run_dir.relative_to(REPO_ROOT)
        print(f"{rel}\t{db_entries} entries\t{verdict}\t{n_rules} rules\t{group}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
