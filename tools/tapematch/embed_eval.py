#!/usr/bin/env python3
"""embed_eval.py — Task 6.2 pretrained-embedding gate + report (Tier B).

Scoring/report half of the ``instructions/CC_TAPEMATCH_ADDON.md`` Task 6 harness.
It is intentionally model-free (numpy only): it consumes the per-source window
embeddings written by ``embed_extract.py`` (``embed_cache/<date>/LB<lb>.npz``) and
the evaluation population from ``embed_eval_set.json`` (``build_embed_eval_set.py``),
computes a per-pair ``emb_score``, and prints the TP / same-show-TN / FN
distributions + the p10(TP)−p90(TN) gap — the same structure and gate as
``calibrate_triplet.py`` / ``calibrate_addon.py``.

Pair score (spec 6.1 step 3): for each 1 s window in source A, take the cosine-max
over B's windows in a ±``--tol`` aligned neighborhood (nominal perf-time, so a
source's own speed offset is removed at extraction), then ``emb_score`` = median of
those per-window maxima. Windows with no B partner in tolerance are skipped.

**Gate (spec 6.2):** ship Tier B only if p10(TP) − p90(same-show-TN) ≥ ``--min-gap``
(0.10). The triplet baseline was −0.012. A narrower/negative gap is a structural
reject — do not threshold-shop. On pass, wire ``pairs.emb_score`` + verdict Rule C
(conjunctive, never lone-merge) and run the full ``regression.py`` gate.

Read-only; never runs audio or a model.

    .venv/bin/python3 tools/tapematch/embed_eval.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
EVAL_SET_PATH = _HERE / "embed_eval_set.json"
CACHE_DIR = _HERE / "embed_cache"


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
        print(f"  {name:<8} n=0  (no scored pairs — extract embeddings first)")
        return
    print(f"  {name:<8} n={len(vals):<4} "
          f"min={min(vals):.3f} p10={_pct(vals, 10):.3f} p25={_pct(vals, 25):.3f} "
          f"median={_pct(vals, 50):.3f} p75={_pct(vals, 75):.3f} "
          f"p90={_pct(vals, 90):.3f} max={max(vals):.3f}")


def _load_source(date: str, lb: int, cache: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (L2-normalized embeddings [N,D], nominal perf-times [N]) or None if uncached."""
    p = cache / date / f"LB{lb}.npz"
    if not p.exists():
        return None
    z = np.load(p)
    emb = z["emb"].astype(np.float32)
    t = z["t"].astype(np.float32)
    if emb.size == 0:
        return None
    norm = np.linalg.norm(emb, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return emb / norm, t


def _pair_score(a: tuple[np.ndarray, np.ndarray],
                b: tuple[np.ndarray, np.ndarray], tol: float) -> float | None:
    """median over A-windows of cosine-max to B-windows.

    ``tol > 0``: restrict each A-window's max to B-windows within |t_a - t_b| <= tol
    (nominal seconds-into-performance; spec 6.1.3 speed-mapped neighbourhood).
    ``tol <= 0``: global cosine-max over all B-windows (standard fingerprint
    retrieval; robust when the two transfers sampled non-overlapping excerpts).
    """
    ea, ta = a
    eb, tb = b
    sims = ea @ eb.T  # cosine (both L2-normalized) -> [Na, Nb]
    if tol <= 0:
        return float(np.median(sims.max(axis=1)))
    maxima: list[float] = []
    for i in range(ea.shape[0]):
        mask = np.abs(tb - ta[i]) <= tol
        if not mask.any():
            continue
        maxima.append(float(sims[i, mask].max()))
    if not maxima:
        return None
    return float(np.median(maxima))


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 6.2 embedding gate + report.")
    ap.add_argument("--min-gap", type=float, default=0.10,
                    help="required p10(TP)-p90(TN) separation (spec 6.2). Below = structural reject.")
    ap.add_argument("--tol", type=float, default=2.0,
                    help="±nominal-perf-seconds window-alignment tolerance.")
    ap.add_argument("--eval-set", type=Path, default=EVAL_SET_PATH)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    args = ap.parse_args()

    if not args.eval_set.exists():
        sys.exit(f"error: {args.eval_set.name} not found — run build_embed_eval_set.py first.")
    es = json.loads(args.eval_set.read_text())

    # Cache all sources once.
    src: dict[tuple[str, int], tuple[np.ndarray, np.ndarray] | None] = {}
    for date, srcs in es["sources"].items():
        for s in srcs:
            src[(date, s["lb"])] = _load_source(date, s["lb"], args.cache)

    dist: dict[str, list[float]] = {"tp": [], "tn": [], "fn": []}
    unscored = {"tp": 0, "tn": 0, "fn": 0}
    for st in ("tp", "tn", "fn"):
        for pr in es["pairs"][st]:
            a = src.get((pr["date"], pr["lb_a"]))
            b = src.get((pr["date"], pr["lb_b"]))
            if a is None or b is None:
                unscored[st] += 1
                continue
            sc = _pair_score(a, b, args.tol)
            if sc is None:
                unscored[st] += 1
                continue
            dist[st].append(sc)

    n_cached = sum(1 for v in src.values() if v is not None)
    print("pretrained-embedding emb_score distributions (Task 6 eval set)")
    print(f"  sources cached: {n_cached}/{len(src)}   tol=±{args.tol:.1f}s")
    print(f"  scored pairs: TP={len(dist['tp'])} TN={len(dist['tn'])} FN={len(dist['fn'])}   "
          f"unscored (missing cache): TP={unscored['tp']} TN={unscored['tn']} FN={unscored['fn']}\n")
    _describe("TP", dist["tp"])
    _describe("TN(same-show)", dist["tn"])
    _describe("FN(target)", dist["fn"])

    if not dist["tp"] or not dist["tn"]:
        print("\nInsufficient TP/TN overlap — extract embeddings for more sources, then re-run.")
        return 0

    tp_low = _pct(dist["tp"], 10)
    tn_high = _pct(dist["tn"], 90)
    gap = tp_low - tn_high
    max_tn = max(dist["tn"])
    tp_above = sum(1 for v in dist["tp"] if v > max_tn)
    fn_above = sum(1 for v in dist["fn"] if v > max_tn)
    print(f"\nmax same-show-TN emb_score = {max_tn:.3f}")
    print(f"TP recoverable with 0 FP   = {tp_above}/{len(dist['tp'])}  "
          f"(FN target recovered: {fn_above}/{len(dist['fn'])})")
    print(f"gap [p90(TN)={tn_high:.3f} .. p10(TP)={tp_low:.3f}] width = {gap:+.3f}  "
          f"(triplet baseline −0.012)")
    if gap >= args.min_gap:
        midpoint = (tp_low + tn_high) / 2.0
        print(f"PASS — gap {gap:.3f} >= {args.min_gap}. Wire pairs.emb_score + verdict Rule C; "
              f"provisional T_emb = {midpoint:.3f}; then run regression.py score gate (abs fp<=9).")
    else:
        print(f"REJECT — gap {gap:.3f} < {args.min_gap} (structural). Per spec 6.2: stop Tier B, "
              f"record the negative result, carry this same-show collision into Task 7 as baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
