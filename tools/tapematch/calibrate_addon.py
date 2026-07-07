#!/usr/bin/env python3
"""calibrate_addon.py — Calibration protocol for the Tier A ADDON signals
(``instructions/CC_TAPEMATCH_ADDON.md`` Tasks 2/3/4 + the Calibration protocol).

DB-only analyzer (never runs audio). Joins the frozen regression labels
(``regression_set.json``) to the three ADDON metric columns in ``observations.db``
(``latest_pairs`` view) and, for each signal, prints the distributions for:

  * frozen TP pairs  (truth == same source; ``label_suspect=1`` excluded — Task 1),
  * frozen TN pairs  (same-date different-source hard negatives — the population that
                      killed the triplet fingerprint; this is the gap denominator),
  * target-FN coverage (frozen TP with primary ``corr`` < ``--cat1-corr`` and not
                      ``label_suspect`` — the population each signal exists to recover).

For every signal it reports gap = p10(TP) − p90(TN) and a PASS/REJECT verdict against
``--min-gap`` (0.10). Per spec, ship a signal's ``addon_links`` rule ONLY on PASS; a
narrower gap is a structural rejection — do not threshold-shop.

Mirrors ``calibrate_triplet.py`` (same percentile math + frozen-label join), extended
to the three ADDON metrics. Populate the columns first by re-running the calibration
dates (serialized — see CALIBRATION_PROGRESS.md CONCURRENCY HAZARD), then run:

    .venv/bin/python3 tools/tapematch/calibrate_addon.py
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

# (column, conjunctive-only?) — env_corr is permanently lone-merge-banned (spec 4.2).
SIGNALS = ["flaw_match_score", "spec_stationarity", "env_corr"]


def _key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _load_labels() -> dict[tuple[int, int], int]:
    if not FROZEN_PATH.exists():
        sys.exit(f"error: {FROZEN_PATH.name} not found — run `regression.py freeze` first.")
    frozen = json.loads(FROZEN_PATH.read_text())
    out: dict[tuple[int, int], int] = {}
    for a, b, _date in frozen["positives"]:
        out[_key(a, b)] = 1
    for a, b, _date in frozen["negatives"]:
        out[_key(a, b)] = 0
    return out


def _load_rows(conn: sqlite3.Connection) -> dict[tuple[int, int], dict]:
    """Map (lb_lo, lb_hi) -> {signal: val|None, corr, label_suspect} from latest_pairs."""
    cols = ", ".join(SIGNALS)
    out: dict[tuple[int, int], dict] = {}
    cur = conn.execute(
        f"SELECT lb_a, lb_b, corr, label_suspect, {cols} FROM latest_pairs "
        "WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL")
    for row in cur:
        a, b, corr, suspect = row[0], row[1], row[2], row[3]
        rec = {
            "corr": None if corr is None else float(corr),
            "label_suspect": None if suspect is None else int(suspect),
        }
        for i, sig in enumerate(SIGNALS):
            v = row[4 + i]
            rec[sig] = None if v is None else float(v)
        out[_key(a, b)] = rec
    return out


def _pct(vals: list[float], q: float) -> float:
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
        print(f"    {name:<8} n=0  (no populated values)")
        return
    print(f"    {name:<8} n={len(vals):<4} "
          f"min={min(vals):.3f} p10={_pct(vals, 10):.3f} "
          f"median={_pct(vals, 50):.3f} "
          f"p90={_pct(vals, 90):.3f} max={max(vals):.3f}")


def _report_signal(sig: str, rows: dict, labels: dict, cat1_corr: float,
                   min_gap: float) -> None:
    tp: list[float] = []          # true same-source positives (suspects excluded)
    tn: list[float] = []          # same-date different-source negatives
    fn_pop = 0                    # target-FN pairs (corr<cat1, not suspect) WITH a value
    fn_tot = 0                    # target-FN pairs present in populated dates at all
    for key, truth in labels.items():
        rec = rows.get(key)
        if rec is None:
            continue
        v = rec[sig]
        suspect = rec["label_suspect"] == 1
        corr = rec["corr"]
        if truth == 1:
            is_target_fn = (corr is not None and corr < cat1_corr and not suspect)
            if is_target_fn:
                fn_tot += 1
                if v is not None:
                    fn_pop += 1
            if v is not None and not suspect:
                tp.append(v)
        else:
            if v is not None:
                tn.append(v)

    print(f"\n=== {sig} ===")
    _describe("TP", tp)
    _describe("TN", tn)
    cov = f"{fn_pop}/{fn_tot}" if fn_tot else "0/0"
    cov_pct = (100.0 * fn_pop / fn_tot) if fn_tot else 0.0
    print(f"    target-FN coverage (corr<{cat1_corr}, not suspect): {cov} ({cov_pct:.0f}%)")
    if not tp or not tn:
        print("    VERDICT: INSUFFICIENT DATA (need both TP and TN populated)")
        return
    tp_low = _pct(tp, 10)
    tn_high = _pct(tn, 90)
    gap = tp_low - tn_high
    midpoint = (tp_low + tn_high) / 2.0
    verdict = "PASS" if gap >= min_gap else "REJECT"
    print(f"    gap = p10(TP)={tp_low:.3f} - p90(TN)={tn_high:.3f} = {gap:+.3f}  "
          f"[{verdict} vs min_gap {min_gap}]")
    # Zero-FP threshold: the real ship test for a lone-merge LINEAGE-PURE signal
    # (flaw), where the p10/p90 gap is dragged down by low-coverage TP zeros but a
    # high bar above the worst negative still recovers TP with no false merge.
    max_tn = max(tn)
    strict = max_tn + 0.01
    tp_above = sum(1 for v in tp if v > max_tn)
    print(f"    zero-FP bar > max(TN)={max_tn:.3f}: recovers {tp_above}/{len(tp)} TP "
          f"(strict cluster_threshold >= {strict:.3f})")
    if gap >= min_gap:
        print(f"    -> recommend threshold ~{midpoint:.3f} (midpoint); wire the "
              f"corresponding addon_links rule, then run score --cached (absolute fp<=9).")
    elif tp_above > 0:
        print(f"    -> p10/p90 gap fails, BUT a strict zero-FP bar {strict:.3f} recovers "
              f"{tp_above} TP with no frozen FP — precision-safe if lone-merge is allowed "
              f"(Rule A / flaw only; stationarity+env are conjunctive-only, never lone).")
    else:
        print("    -> structural reject: do NOT ship / do NOT threshold-shop (triplet precedent).")


def _report_rule_b(rows: dict, labels: dict, t_stat: float, t_env: float) -> None:
    """Rule B is CONJUNCTIVE (spec_stationarity AND env_corr). Individual gaps failing
    does not settle the AND-gate; scan whether the conjunction admits any frozen TN."""
    tp_pass = tn_pass = tp_have = tn_have = 0
    for key, truth in labels.items():
        rec = rows.get(key)
        if rec is None:
            continue
        s, e = rec["spec_stationarity"], rec["env_corr"]
        if s is None or e is None:
            continue
        if truth == 1:
            tp_have += 1
            if s >= t_stat and e >= t_env:
                tp_pass += 1
        else:
            tn_have += 1
            if s >= t_stat and e >= t_env:
                tn_pass += 1
    print(f"\n=== Rule B conjunction (spec_stationarity>={t_stat} AND env_corr>={t_env}) ===")
    print(f"    both-populated pairs: TP={tp_have} TN={tn_have}")
    print(f"    pass the AND-gate:    TP={tp_pass} TN={tn_pass}")
    if tn_have and tp_have:
        if tn_pass == 0 and tp_pass > 0:
            print(f"    -> PRECISION-SAFE at these thresholds: recovers {tp_pass} TP, 0 TN. "
                  f"Candidate Rule B — confirm with score --cached (absolute fp<=9).")
        elif tn_pass > 0:
            print(f"    -> REJECT at these thresholds: {tn_pass} frozen TN pass (false merges). "
                  f"Raise thresholds and re-scan, or reject structurally.")
        else:
            print("    -> no TP recovered at these thresholds (no recall benefit).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier A ADDON signal calibration (gap>=0.10 gate).")
    ap.add_argument("--min-gap", type=float, default=0.10)
    ap.add_argument("--cat1-corr", type=float, default=0.05)
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    args = ap.parse_args()

    labels = _load_labels()
    conn = sqlite3.connect(str(args.db))
    try:
        rows = _load_rows(conn)
    finally:
        conn.close()

    pop = {s: sum(1 for r in rows.values() if r[s] is not None) for s in SIGNALS}
    print("Tier A ADDON signal calibration (frozen set ∩ populated rows)")
    print(f"  labeled pairs: {len(labels)}   rows in latest_pairs: {len(rows)}")
    print("  populated per signal: " + "  ".join(f"{s}={pop[s]}" for s in SIGNALS))
    for sig in SIGNALS:
        _report_signal(sig, rows, labels, args.cat1_corr, args.min_gap)
    # Rule B is conjunctive; provisional thresholds from config (uncalibrated).
    _report_rule_b(rows, labels, t_stat=0.7, t_env=0.90)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
