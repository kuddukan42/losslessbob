#!/usr/bin/env python3
"""rerun_cat3.py — Task 2 of CC_TAPEMATCH_FIXES.md: focused re-run of Cat-3 pairs.

Cat 3 = curator says same source, verdict different_family, and at least one side
was speed-aligned in the original run — i.e. a source that got speed-aligned to
the *wrong* reference when a whole date was staged together, so the true sibling
pair never actually aligned against each other.

The fix, per pair: stage ONLY the two folders together and re-run tapematch, so
each aligns against the other rather than a wrong third reference. Expected
outcome: most flip to same_family. Any that don't are genuinely a different
FN category (1/2/4) and are reported as such.

    # inspect the population (no audio):
    python tools/tapematch/rerun_cat3.py --list
    # dry-run staging plan for a few:
    python tools/tapematch/rerun_cat3.py --limit 3 --dry-run
    # actually re-run (AUDIO — copies folders + decodes):
    python tools/tapematch/rerun_cat3.py --limit 6

NOTE: the spec quotes "6 pairs"; the documented FN query actually matches ~137
under the restored observations.db (the true Cat-3 subset was narrower in Fable's
audit and can't be reproduced exactly). Use --limit / --dates to bound a run.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import tapematch_session as ts  # noqa: E402
from tapematch import verdict as V  # noqa: E402

# Documented FN characterization query (spec Task 2): an 'aligned' source on
# either side, curator says same, verdict different_family.
CAT3_QUERY = """
    SELECT concert_date, lb_a, lb_b, tapematch_verdict, corr
    FROM latest_pairs
    WHERE (speed_kind_a = 'aligned' OR speed_kind_b = 'aligned')
      AND lb_says_same = 1
      AND tapematch_verdict = 'different_family'
    ORDER BY concert_date, lb_a, lb_b
"""


def _population(dates: set[str] | None) -> list[tuple]:
    conn = sqlite3.connect(str(ts.OBS_DB_PATH))
    try:
        rows = conn.execute(CAT3_QUERY).fetchall()
    finally:
        conn.close()
    if dates:
        rows = [r for r in rows if r[0] in dates]
    return rows


def _rerun_pair(date: str, lb_a: int, lb_b: int, dry_run: bool) -> dict:
    """Stage the two folders alone and re-run tapematch. Returns a result dict."""
    year = date[:4]
    found, _excluded = ts.find_lb_folders([lb_a, lb_b], year)
    missing = [n for n in (lb_a, lb_b) if n not in found]
    if missing:
        return {"status": "missing", "missing": missing}
    if dry_run:
        return {"status": "dry_run",
                "folders": {n: str(found[n].name) for n in (lb_a, lb_b)}}

    run_id = ts.make_run_id()
    from datetime import datetime
    run_at = datetime.now().isoformat()

    ts.clean_examples()
    ts.copy_folders(found)
    json_path = ts.SESSION_DIR / "last_run.json"
    ts.run_tapematch(json_path, set_offset=None)
    import json
    results = json.loads(Path(json_path).read_text())

    # New verdict: same family iff both folders landed in one family_id.
    name_a = found[lb_a].name
    name_b = found[lb_b].name
    srcs = results.get("sources", {})
    fam_a = srcs.get(name_a, {}).get("family_id")
    fam_b = srcs.get(name_b, {}).get("family_id")
    new_verdict = (V.SAME_FAMILY if (fam_a is not None and fam_a == fam_b)
                   else V.DIFFERENT_FAMILY)

    conn = ts.open_obs_db()
    try:
        ts.insert_pairs(conn, run_id, date, results, found, run_at)
        conn.commit()
    finally:
        conn.close()

    return {"status": "ran", "new_verdict": new_verdict, "run_id": run_id}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="print the Cat-3 population and exit (no audio)")
    ap.add_argument("--dates", help="comma-separated dates to restrict to")
    ap.add_argument("--limit", type=int, default=None,
                    help="process at most N pairs")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve + report staging plan without decoding audio")
    args = ap.parse_args(argv)

    dates = {d.strip() for d in args.dates.split(",")} if args.dates else None
    pop = _population(dates)

    if args.list:
        print(f"Cat-3 population: {len(pop)} pair(s)")
        for date, a, b, tv, corr in pop:
            print(f"  {date}  LB-{a:05d}/LB-{b:05d}  corr={corr:.3f}  verdict={tv}")
        return 0

    if args.limit is not None:
        pop = pop[:args.limit]

    flipped = same_still = missing = 0
    for date, a, b, tv, corr in pop:
        res = _rerun_pair(date, a, b, args.dry_run)
        if res["status"] == "missing":
            missing += 1
            print(f"  {date}  LB-{a:05d}/LB-{b:05d}: SKIP — not on disk: "
                  f"{res['missing']}")
        elif res["status"] == "dry_run":
            print(f"  {date}  LB-{a:05d}/LB-{b:05d}: would stage {res['folders']}")
        else:
            before, after = tv, res["new_verdict"]
            change = "FLIPPED → same_family" if (before != after
                     and after == V.SAME_FAMILY) else "unchanged"
            if change.startswith("FLIP"):
                flipped += 1
            else:
                same_still += 1
            print(f"  {date}  LB-{a:05d}/LB-{b:05d}: {before} -> {after}  [{change}]")

    if not args.dry_run:
        print(f"\nSummary: {flipped} flipped to same_family, {same_still} unchanged "
              f"(reassign to Cat 1/2/4), {missing} missing on disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
