#!/usr/bin/env python3
"""build_embed_eval_set.py — Task 6.1.4 evaluation-set builder (Tier B).

Selects the pretrained-embedding evaluation population defined in
``instructions/CC_TAPEMATCH_ADDON.md`` Task 6.1 step 4:

  * ~60 frozen TP pairs          (truth == same source AND currently correlating,
                                   ``corr >= --tp-corr`` — the "model should score
                                   known same-source high" control),
  * ~60 same-date different-source TN pairs (frozen negatives — the population that
                                   structurally killed the triplet fingerprint),
  * ~60 corr<``--fn-corr`` FN pairs (frozen positives the current pipeline misses,
                                   EXCLUDING Task-1 ``label_suspect`` pairs — the
                                   target-recovery population).

Selection is **date-clustered**: because scoring a pair requires embedding *both*
its sources, the set is drawn from a small number of multi-source dates so each
source is decoded/embedded exactly once and reused across every in-stratum pair on
that date. Dates are chosen greedily (deterministic, seed-free) to reach the
per-stratum quota with the fewest distinct sources — this both minimises the live
audio-extraction cost and controls for per-date acoustic conditions.

Output: ``embed_eval_set.json`` next to this script, consumed by ``embed_eval.py``
(scoring/gap harness) and by the embedding-extraction step. It records, per selected
date, every source that must be embedded (folder, trim bounds, speed) and the pair
lists per stratum. Read-only against ``observations.db``; never runs audio.

    .venv/bin/python3 tools/tapematch/build_embed_eval_set.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
OBS_DB_PATH = _HERE / "observations.db"
FROZEN_PATH = _HERE / "regression_set.json"
OUT_PATH = _HERE / "embed_eval_set.json"


def _key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _load_labels() -> dict[tuple[int, int], int]:
    if not FROZEN_PATH.exists():
        sys.exit(f"error: {FROZEN_PATH.name} not found — run `regression.py freeze` first.")
    frozen = json.loads(FROZEN_PATH.read_text())
    out: dict[tuple[int, int], int] = {}
    for a, b, _d in frozen["positives"]:
        out[_key(a, b)] = 1
    for a, b, _d in frozen["negatives"]:
        out[_key(a, b)] = 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 6.1.4 embedding eval-set builder.")
    ap.add_argument("--quota", type=int, default=60, help="target pairs per stratum.")
    ap.add_argument("--tp-corr", type=float, default=0.05,
                    help="a frozen positive counts as TP (already-matched) if corr >= this.")
    ap.add_argument("--fn-corr", type=float, default=0.05,
                    help="a frozen positive counts as target-FN if corr < this.")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    labels = _load_labels()
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row

    # latest_pairs row per frozen pair (corr / label_suspect / date / folders).
    pair_rows: dict[tuple[int, int], sqlite3.Row] = {}
    for r in conn.execute(
        "SELECT lb_a, lb_b, corr, label_suspect, concert_date, folder_a, folder_b, "
        "lb_says_same, lb_relation_text FROM latest_pairs "
        "WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL"
    ):
        pair_rows[_key(r["lb_a"], r["lb_b"])] = r

    # Classify each frozen pair into a stratum, grouped by date.
    #   stratum in {"tp","tn","fn"}
    by_date: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(
        lambda: {"tp": [], "tn": [], "fn": []})
    for k, truth in labels.items():
        r = pair_rows.get(k)
        if r is None:
            continue
        corr = r["corr"]
        date = r["concert_date"]
        if truth == 0:
            by_date[date]["tn"].append(k)
        else:  # truth == 1
            if corr is not None and corr < args.fn_corr and (r["label_suspect"] in (None, 0)):
                by_date[date]["fn"].append(k)
            elif corr is not None and corr >= args.tp_corr:
                by_date[date]["tp"].append(k)
            # positives with corr in a gap, or label_suspect, are unused.

    # Greedy date-clustered selection: prioritise dates dense in the scarcest stratum
    # (fn), tie-break by total in-stratum pairs, until every stratum meets quota.
    def date_rank(d: str) -> tuple[int, int]:
        s = by_date[d]
        return (len(s["fn"]), len(s["fn"]) + len(s["tn"]) + len(s["tp"]))

    ordered = sorted(by_date, key=date_rank, reverse=True)
    chosen: list[str] = []
    tot = {"tp": 0, "tn": 0, "fn": 0}
    for d in ordered:
        if all(tot[s] >= args.quota for s in tot):
            break
        s = by_date[d]
        if not (s["tp"] or s["tn"] or s["fn"]):
            continue
        chosen.append(d)
        for st in tot:
            tot[st] += len(s[st])

    # Trim each stratum to the quota deterministically (sorted key order) while
    # keeping only pairs whose date was chosen.
    chosen_set = set(chosen)
    strata: dict[str, list[tuple[int, int]]] = {"tp": [], "tn": [], "fn": []}
    for d in sorted(chosen_set):
        for st in strata:
            for k in sorted(by_date[d][st]):
                if len(strata[st]) < args.quota:
                    strata[st].append(k)

    # Collect the distinct sources to embed: every source on a chosen date that
    # participates in at least one selected pair.
    needed_lbs: dict[str, set[int]] = defaultdict(set)
    pairs_out: dict[str, list[dict]] = {"tp": [], "tn": [], "fn": []}
    for st, ks in strata.items():
        for a, b in ks:
            r = pair_rows[(a, b)]
            d = r["concert_date"]
            needed_lbs[d].update((a, b))
            pairs_out[st].append({
                "date": d, "lb_a": a, "lb_b": b,
                "corr": r["corr"], "truth": 1 if st != "tn" else 0,
                "lb_says_same": r["lb_says_same"],
            })

    # Source metadata (trim bounds + speed) for extraction, from the latest run per date.
    sources_out: dict[str, list[dict]] = {}
    for d in sorted(needed_lbs):
        rows = conn.execute(
            "SELECT lb_number, folder_name, run_id, trim_head_sec, trim_tail_sec, "
            "perf_dur_sec, total_dur_sec, speed_ppm, speed_kind FROM sources "
            "WHERE concert_date = ? AND lb_number IN (%s) "
            "ORDER BY id DESC" % ",".join("?" * len(needed_lbs[d])),
            (d, *sorted(needed_lbs[d])),
        ).fetchall()
        seen: set[int] = set()
        srcs = []
        for r in rows:  # latest run first; keep first occurrence per lb
            lb = r["lb_number"]
            if lb in seen or lb not in needed_lbs[d]:
                continue
            seen.add(lb)
            srcs.append({
                "lb": lb, "folder": r["folder_name"], "run_id": r["run_id"],
                "trim_head_sec": r["trim_head_sec"], "trim_tail_sec": r["trim_tail_sec"],
                "perf_dur_sec": r["perf_dur_sec"], "total_dur_sec": r["total_dur_sec"],
                "speed_ppm": r["speed_ppm"], "speed_kind": r["speed_kind"],
            })
        missing = needed_lbs[d] - seen
        if missing:
            print(f"  WARN {d}: no sources row for LB {sorted(missing)} "
                  f"(pairs referencing them will be unscorable)")
        sources_out[d] = srcs
    conn.close()

    out = {
        "spec": "CC_TAPEMATCH_ADDON Task 6.1.4",
        "params": {"quota": args.quota, "tp_corr": args.tp_corr, "fn_corr": args.fn_corr},
        "dates": sorted(chosen_set),
        "n_sources": sum(len(v) for v in sources_out.values()),
        "counts": {st: len(pairs_out[st]) for st in pairs_out},
        "sources": sources_out,
        "pairs": pairs_out,
    }
    args.out.write_text(json.dumps(out, indent=2))

    print(f"embed eval set → {args.out.name}")
    print(f"  dates: {len(chosen_set)}   distinct sources to embed: {out['n_sources']}")
    print(f"  pairs: TP={out['counts']['tp']}  TN={out['counts']['tn']}  FN={out['counts']['fn']}")
    if any(out["counts"][s] < args.quota for s in out["counts"]):
        print(f"  NOTE: a stratum is below quota={args.quota}; widen date pool or relax corr cuts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
