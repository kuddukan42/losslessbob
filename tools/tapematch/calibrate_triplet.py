#!/usr/bin/env python3
"""calibrate_triplet.py — Task 7.4 calibration for the ratio-invariant triplet
fingerprint (``instructions/CC_TAPEMATCH_FIXES.md`` Task 7).

Reads the frozen regression labels (``regression_set.json``) and joins them to
the ``fp_triplet_score`` column in ``observations.db`` (``latest_pairs`` view),
then prints the triplet-Dice distributions for:

  * frozen TP pairs  (curator/human truth == same source)
  * frozen TN pairs  (same-date hard negatives — truth == different source)
  * Cat-1 subset      (frozen TP pairs whose primary ``corr`` < ``--cat1-corr``,
                       i.e. the speed failures the triplet path exists to rescue)

and recommends ``fingerprint.triplet.cluster_threshold`` at the midpoint of the
TP/TN gap. Per Task 7.4 the gap must be >= ``--min-gap`` (default 0.10); if it is
narrower, raise the freq-ratio quantization bits (7 -> 8) in
``match.triplet_hashes`` and repeat.

This is a DB-only analyzer: it consumes the ``fp_triplet_score`` values that the
live session (cli.py) computes and ``insert_pairs`` persists, so it reflects the
exact production code path. Populate the column first by re-running the relevant
dates (serialized — see CALIBRATION_PROGRESS.md CONCURRENCY HAZARD), then run:

    .venv/bin/python3 tools/tapematch/calibrate_triplet.py

Read-only; never runs audio.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
OBS_DB_PATH = _HERE / "observations.db"
FROZEN_PATH = _HERE / "regression_set.json"


def _key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _load_labels() -> dict[tuple[int, int], int]:
    """Map normalized (lb_lo, lb_hi) -> truth (1 same / 0 different) from the frozen set."""
    if not FROZEN_PATH.exists():
        sys.exit(f"error: {FROZEN_PATH.name} not found — run `regression.py freeze` first.")
    frozen = json.loads(FROZEN_PATH.read_text())
    out: dict[tuple[int, int], int] = {}
    for a, b, _date in frozen["positives"]:
        out[_key(a, b)] = 1
    for a, b, _date in frozen["negatives"]:
        out[_key(a, b)] = 0
    return out


def _load_scores(conn: sqlite3.Connection) -> dict[tuple[int, int], tuple[float, float | None]]:
    """Map normalized (lb_lo, lb_hi) -> (fp_triplet_score, corr) for rows that carry a triplet score."""
    out: dict[tuple[int, int], tuple[float, float | None]] = {}
    cur = conn.execute(
        "SELECT lb_a, lb_b, fp_triplet_score, corr FROM latest_pairs "
        "WHERE fp_triplet_score IS NOT NULL AND lb_a IS NOT NULL AND lb_b IS NOT NULL")
    for a, b, tri, corr in cur:
        out[_key(a, b)] = (float(tri), None if corr is None else float(corr))
    return out


def _pct(vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0,100]) of a non-empty sorted-able list."""
    if not vals:
        return float("nan")
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _describe(name: str, vals: list[float]) -> None:
    if not vals:
        print(f"  {name:<10} n=0  (no populated triplet scores — re-run dates first)")
        return
    print(f"  {name:<10} n={len(vals):<4} "
          f"min={min(vals):.3f} p10={_pct(vals, 10):.3f} p25={_pct(vals, 25):.3f} "
          f"median={_pct(vals, 50):.3f} p75={_pct(vals, 75):.3f} "
          f"p90={_pct(vals, 90):.3f} max={max(vals):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 7.4 triplet-fingerprint threshold calibration.")
    ap.add_argument("--min-gap", type=float, default=0.10,
                    help="required TP/TN separation (Task 7.4); below this, raise quant bits.")
    ap.add_argument("--cat1-corr", type=float, default=0.05,
                    help="corr below this marks a Cat-1 speed-failure pair.")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    args = ap.parse_args()

    labels = _load_labels()
    conn = sqlite3.connect(str(args.db))
    try:
        scores = _load_scores(conn)
    finally:
        conn.close()

    tp: list[float] = []
    tn: list[float] = []
    cat1: list[float] = []
    for key, truth in labels.items():
        if key not in scores:
            continue
        tri, corr = scores[key]
        if truth == 1:
            tp.append(tri)
            if corr is not None and corr < args.cat1_corr:
                cat1.append(tri)
        else:
            tn.append(tri)

    print("triplet-fingerprint Dice distributions (frozen set ∩ populated rows)")
    print(f"  labeled pairs: {len(labels)}   populated triplet scores: {len(scores)}")
    print(f"  overlap: TP={len(tp)}  TN={len(tn)}  Cat-1(TP,corr<{args.cat1_corr})={len(cat1)}\n")
    _describe("TP", tp)
    _describe("TN", tn)
    _describe("Cat-1", cat1)

    if not tp or not tn:
        print("\nInsufficient overlap to recommend a threshold — populate more dates "
              "(re-run frozen Cat-1 dates), then re-run this script.")
        return 0

    # Zero-FP threshold: the smallest bar that admits no frozen negative.
    max_tn = max(tn)
    tp_above = [v for v in tp if v > max_tn]
    print(f"\nmax TN triplet-Dice        = {max_tn:.3f}")
    print(f"TP recoverable with 0 FP    = {len(tp_above)}/{len(tp)} "
          f"(triplet-Dice > max TN)")

    # Gap between the negative upper edge and the positive lower body (Task 7.4).
    tp_low = _pct(tp, 10)          # ignore a few TP outliers dragging into the noise
    tn_high = _pct(tn, 90)
    gap = tp_low - tn_high
    midpoint = (tp_low + tn_high) / 2.0
    print(f"\ngap [p90(TN)={tn_high:.3f} .. p10(TP)={tp_low:.3f}] width = {gap:+.3f}")
    if gap >= args.min_gap:
        print(f"RECOMMEND fingerprint.triplet.cluster_threshold = {midpoint:.3f}  "
              f"(gap {gap:.3f} >= {args.min_gap})")
    else:
        # Conservative fallback: a strict zero-FP bar above the worst negative.
        strict = max_tn + 0.01
        print(f"GAP TOO NARROW ({gap:.3f} < {args.min_gap}). Task 7.4: raise freq-ratio "
              f"quant bits (7->8) in match.triplet_hashes and re-run.")
        print(f"  Until then, only a strict zero-FP bar is safe: "
              f"cluster_threshold >= {strict:.3f} (recovers {len(tp_above)} TP).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
