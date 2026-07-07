"""Throwaway miner (2026-07-03): find candidate dates for a small, high-confidence
Tier-C calibration set, sourced from entry_lineage (parsed same_as_lb) and a direct
text scan for explicit "different recording" curator language -- both restricted to
locally-available (my_collection) pairs on the same show date.

Not part of the shipped pipeline. Run with .venv/bin/python3 (stdlib sqlite3 + re only).
"""
import json
import re
import sqlite3

DB = "data/losslessbob.db"

_DIFF_RECORDING_RE = re.compile(
    r"(?:this|it)\s+is\s+a\s+different\s+recording"
    r"|not\s+the\s+same\s+recording"
    r"|different\s+recording\s+(?:than|from)"
    r"|different\s+source\s+(?:than|from)"
    r"|not\s+the\s+same\s+show",
    re.IGNORECASE,
)
_LB_REF_RE = re.compile(r"\bLB-0*(\d+)\b", re.IGNORECASE)


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    local = {r[0] for r in cur.execute("SELECT lb_number FROM my_collection").fetchall()}
    entries = {r[0]: (r[1], r[2]) for r in
               cur.execute("SELECT lb_number, date_str, location FROM entries").fetchall()}

    print("=" * 70)
    print("SAME-SOURCE candidates (entry_lineage.same_as_lb, parse_confidence=high)")
    print("=" * 70)
    rows = cur.execute(
        "SELECT lb_number, same_as_lb FROM entry_lineage "
        "WHERE same_as_lb != '[]' AND parse_confidence = 'high'"
    ).fetchall()
    seen = set()
    n_same = 0
    for lb, same_json in rows:
        if lb not in local or lb not in entries:
            continue
        targets = json.loads(same_json)
        for t in targets:
            if t not in local or t not in entries:
                continue
            date_a, loc_a = entries[lb]
            date_b, loc_b = entries[t]
            if date_a != date_b:
                continue  # sanity: must be the same show
            key = tuple(sorted((lb, t)))
            if key in seen:
                continue
            seen.add(key)
            n_same += 1
            print(f"  {date_a}  {loc_a}:  LB-{lb} <-> LB-{t}")
    print(f"  ({n_same} candidate same-source pairs, both sides local)")

    print()
    print("=" * 70)
    print('DISTINCT-SOURCE candidates (explicit "different recording" text,')
    print("cross-referencing an LB- mention in the same description)")
    print("=" * 70)
    n_diff = 0
    desc_rows = cur.execute(
        "SELECT lb_number, date_str, location, description FROM entries WHERE description IS NOT NULL"
    ).fetchall()
    for lb, date_str, loc, desc in desc_rows:
        if lb not in local:
            continue
        for m in _DIFF_RECORDING_RE.finditer(desc):
            window = desc[max(0, m.start() - 150):min(len(desc), m.end() + 150)]
            for ref in _LB_REF_RE.finditer(window):
                other = int(ref.group(1))
                if other == lb or other not in local or other not in entries:
                    continue
                other_date, other_loc = entries[other]
                if other_date != date_str:
                    continue  # only same-show references are useful here
                n_diff += 1
                snippet = window.strip().replace("\n", " ")
                print(f"  {date_str}  {loc}:  LB-{lb} vs LB-{other}")
                print(f"    ...{snippet[:180]}...")
    print(f"  ({n_diff} candidate distinct-source references, both sides local)")


if __name__ == "__main__":
    main()
