#!/usr/bin/env python3
"""emb_fullset_eval.py — read-only threshold/variant sweep for the Tier B
pretrained-embedding signal (``emb_tol2`` / ``emb_tol0``, Task 6) against the
frozen regression set.

Measures, WITHOUT touching ``config.yaml``, ``verdict.py``, or observations.db:
for a grid of candidate thresholds and three candidate OR-in rules, what would
happen to recall/precision if the embedding score were wired into
``tapematch.verdict.pair_links`` as an extra OR-leg. No existing file is
edited and no verdict is written back to the DB — the injection is done
in-process by temporarily swapping ``tapematch.verdict.pair_links`` for a
thin wrapper that calls the real predicate and ORs in the candidate:

    def wrapped(pair, cfg, lineage=None):
        return _ORIG_PAIR_LINKS(pair, cfg, lineage) or candidate(pair)

``tapematch.verdict.cluster_verdicts`` looks up ``pair_links`` as a bare name
in its own module globals on every call, so reassigning ``verdict.pair_links``
(this module's ``V.pair_links``) takes effect on the next ``cluster_verdicts``
call and is restored in a ``finally`` block immediately after.

Variants (per CC_TAPEMATCH_ADDON.md Task 6 threshold sweep):
    lone       emb_tol2 >= T
    both_tol   emb_tol2 >= T AND emb_tol0 >= T
    dur        emb_tol2 >= T AND speed-corrected performance-duration ratio
               within 15% of unity (reuses ``audit_fn._duration_mismatch`` so
               the ratio math never drifts from the production heuristic)

Only dates carrying at least one non-null ``emb_tol2`` score need to be
re-clustered per (variant, T); every other frozen date reuses the
committed-config verdict (``regression.py``'s ``_candidate_verdicts_for_date``)
computed once. Emb-scored dates honour the same PASSTHROUGH branch that
``score --cached`` uses (regression.py:218-231): when a date's rows carry no
populated ``_SECONDARY_METRIC_COLS`` and the corr threshold is unchanged, the
baseline is the STORED ``tapematch_verdict`` values (a corr-only re-cluster
would lose stored merges), and injection unions {stored SAME_FAMILY pairs}
with {candidate fires} — strictly additive on the stored system. FP counts are
the absolute post-transitive-clustering count on frozen negatives (never a
per-pair-only guard) — the per-date recompute always includes every pair
observed on that date, not just the emb-scored ones, so a new link's
transitive fallout is captured exactly like a live regression run. An
acceptance check printed at startup verifies the no-injection baseline equals
``regression.py score --cached`` with ``addon_links.rule_d`` disabled — the
sweep evaluates every (variant, T) candidate as a REPLACEMENT for the shipped
Rule D (same emb signal, new cache/threshold), so the baseline is the
pre-Rule-D system and flip counts stay comparable with the shipped +25
(see :func:`_acceptance_check`).

Usage:
    .venv/bin/python3 tools/tapematch/emb_fullset_eval.py
    .venv/bin/python3 tools/tapematch/emb_fullset_eval.py \
        --scores fullset_pairs_scores.json --set regression_set_v2.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Callable

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import audit_fn as AF  # noqa: E402  (reuse _duration_mismatch — no reimplementation)
import regression as R  # noqa: E402
from tapematch import verdict as V  # noqa: E402

DEFAULT_SCORES = _HERE / "fullset_pairs_scores.json"
DEFAULT_SET = R.FROZEN_PATH
CONFIG_PATH = R.CONFIG_PATH
OBS_DB_PATH = R.OBS_DB_PATH
LB_DB_PATH = R.LB_DB_PATH

VARIANTS = ("lone", "both_tol", "dur")
DEFAULT_MIN_T = 0.55
DEFAULT_MAX_T = 0.90
DEFAULT_STEP = 0.025
DUR_RATIO_TOL = 0.15  # +/-15% of unity, matches audit_fn._duration_mismatch

# Duration/speed columns needed by the "dur" variant; not in verdict.METRIC_KEYS
# (that tuple is scoped to pair_links' own signals) so fetched separately.
_DUR_COLS = ("perf_dur_sec_a", "perf_dur_sec_b", "speed_ppm_a", "speed_ppm_b")

# A frozen (lb_lo, lb_hi) pair is globally unique across the whole labeled
# corpus (verified: 2965 labeled pairs -> 2965 unique (a,b) keys, no repeats
# across dates), which is exactly the convention regression.py's truth_map /
# cluster_verdicts already use (no date in the key). This module follows suit
# for every pred/truth/score lookup keyed on a pair; ``date`` is carried only
# as a display field inside the scores-by-key value, never as part of the key.
PairKey = tuple[int, int]

# Saved once at import time so the wrapper always calls the *real* predicate,
# even after ``V.pair_links`` has been (temporarily) reassigned below.
_ORIG_PAIR_LINKS = V.pair_links


def _t_grid(min_t: float, max_t: float, step: float) -> list[float]:
    """Inclusive threshold grid from ``min_t`` to ``max_t`` (rounded to 1e-6)."""
    n = round((max_t - min_t) / step)
    return [round(min_t + i * step, 6) for i in range(n + 1)]


def _pair_key(a: int, b: int) -> PairKey:
    return (min(a, b), max(a, b))


def _load_scores(path: Path) -> tuple[list[dict], dict[PairKey, dict]]:
    """Return (raw list, lookup by normalized (lb_lo, lb_hi)); ``date`` stays
    on each value dict for display, out of the key (see PairKey note above)."""
    if not path.exists():
        sys.exit(f"error: scores file not found: {path}")
    raw = json.loads(path.read_text())
    by_key = {_pair_key(r["lb_a"], r["lb_b"]): r for r in raw}
    return raw, by_key


def _load_date_rows(conn: sqlite3.Connection, cols: set[str], date: str) -> list[dict]:
    """Every ``latest_pairs`` row for one date, as dicts with pair_links' own
    metric columns plus the duration/speed columns the "dur" variant needs and
    the stored ``tapematch_verdict`` (for the passthrough edge set below).

    Includes every observed pair for the date (not just emb-scored ones) so a
    full re-cluster captures the real transitive fallout of the injected link.
    """
    metric_cols = [c for c in V.METRIC_KEYS if c in cols]
    extra = [c for c in _DUR_COLS if c in cols]
    sel = ("concert_date, lb_a, lb_b, tapematch_verdict, "
           + ", ".join(metric_cols + extra))
    cur = conn.execute(f"SELECT {sel} FROM latest_pairs WHERE concert_date = ?", (date,))
    names = [d[0] for d in cur.description]
    rows = [dict(zip(names, r)) for r in cur.fetchall()]
    return [r for r in rows if r["lb_a"] is not None and r["lb_b"] is not None]


def _metrics_with_extras(row: dict) -> dict:
    """``regression._row_to_metrics`` conversion (exact metric-key mapping the
    cached-score path uses) plus the ``dur``-variant duration/speed fields."""
    m = R._row_to_metrics(row)
    for c in _DUR_COLS:
        m[c] = row.get(c)
    return m


def _duration_ok(row: dict) -> bool:
    """True iff the speed-corrected perf-duration ratio is within 15% of unity.

    Delegates to ``audit_fn._duration_mismatch`` (Task 1 FN audit) rather than
    re-deriving the ratio, per the task's "same way audit_fn.py does" ask.
    Abstains (False) when duration data is unavailable for either side.
    """
    mismatch, ratio = AF._duration_mismatch(row)
    return ratio is not None and not mismatch


def _make_candidate(variant: str, t: float, scores: dict[PairKey, dict]
                    ) -> Callable[[dict], bool]:
    """Per-pair candidate-link predicate for one (variant, threshold)."""
    def candidate(pair: dict) -> bool:
        if pair["lb_a"] == pair["lb_b"]:
            # Self-pair (two versions of one LB#, e.g. frozen negative
            # LB-3164/LB-3164): the embed cache is keyed by LB number only,
            # so emb_score is trivially 1.0 — unmeasurable, always abstain.
            return False
        key = _pair_key(pair["lb_a"], pair["lb_b"])
        s = scores.get(key)
        if s is None:
            return False
        tol2 = s.get("emb_tol2")
        if tol2 is None or tol2 < t:
            return False
        if variant == "lone":
            return True
        if variant == "both_tol":
            tol0 = s.get("emb_tol0")
            return tol0 is not None and tol0 >= t
        if variant == "dur":
            return _duration_ok(pair)
        raise ValueError(f"unknown variant: {variant}")
    return candidate


def _wrapped_pair_links(candidate: Callable[[dict], bool]):
    """OR-in ``candidate`` alongside the real predicate; no verdict.py edits."""
    def wrapped(pair, cfg, lineage=None):
        return _ORIG_PAIR_LINKS(pair, cfg, lineage) or candidate(pair)
    return wrapped


def _cluster_with_injection(rows: list[dict], cfg: dict, lineage,
                            candidate: Callable[[dict], bool]) -> dict[tuple, bool]:
    """Run ``verdict.cluster_verdicts`` with ``candidate`` OR'd into the link
    predicate, restoring the original predicate immediately afterward."""
    V.pair_links = _wrapped_pair_links(candidate)
    try:
        verdicts = V.cluster_verdicts(rows, cfg, lineage)
    finally:
        V.pair_links = _ORIG_PAIR_LINKS
    return {k: v == V.SAME_FAMILY for k, v in verdicts.items()}


def _cluster_edges(rows: list[dict], link_fn: Callable[[dict], bool]) -> dict[tuple, bool]:
    """Union-find over one date's rows with an arbitrary edge predicate.

    Mirrors ``verdict.cluster_verdicts``'s transitive-component structure but
    takes the link decision from ``link_fn`` directly — used on passthrough
    dates, where the edge set is {stored SAME_FAMILY pairs} OR {candidate
    fires}, so the injected link is strictly additive on top of the stored
    system verdicts and every stored merge is preserved exactly.
    """
    nodes: dict[int, int] = {}

    def node(x: int) -> int:
        if x not in nodes:
            nodes[x] = len(nodes)
        return nodes[x]

    for r in rows:
        node(r["lb_a"])
        node(r["lb_b"])
    parent = list(range(len(nodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rows:
        if link_fn(r):
            ra, rb = find(node(r["lb_a"])), find(node(r["lb_b"]))
            parent[ra] = rb

    out: dict[tuple, bool] = {}
    for r in rows:
        a, b = r["lb_a"], r["lb_b"]
        out[(min(a, b), max(a, b))] = find(node(a)) == find(node(b))
    return out


def _label_suspect_keys(conn: sqlite3.Connection, cols: set[str]) -> set[tuple[int, int]]:
    """Frozen pairs flagged ``label_suspect=1`` (Task 1 FN audit), for
    excluding curator-label-noise pairs from the genuine-negative embedding
    distribution. Reads ``latest_pairs`` (never ``pairs`` directly, per
    regression.py's stale-data guard)."""
    if "label_suspect" not in cols:
        return set()
    out = set()
    for a, b in conn.execute(
            "SELECT lb_a, lb_b FROM latest_pairs WHERE label_suspect = 1"):
        if a is not None and b is not None:
            out.add((min(a, b), max(a, b)))
    return out


def _build_predictions(
    conn: sqlite3.Connection, cols: set[str], frozen_dates: list[str],
    raw_scores: list[dict], cfg: dict, baseline_cfg: dict, lineage,
) -> tuple[dict[tuple, bool], dict[str, list[dict]], set[str], set[str]]:
    """Return (current_pred, date_rows, recompute_dates, passthrough_dates).

    ``current_pred`` is the committed-config (no injection) prediction for
    every frozen pair, computed EXACTLY the way ``regression.py score
    --cached`` computes it — including its passthrough branch
    (``_candidate_verdicts_for_date``): a date whose rows carry no populated
    ``_SECONDARY_METRIC_COLS`` (historical rows) and whose corr threshold is
    unchanged uses the STORED ``tapematch_verdict`` values, never a
    re-cluster (a re-cluster from corr-only rows would lose stored merges).

    For emb-scored dates the same test decides the later injection strategy:
      * passthrough date -> stored verdicts here; injection later unions
        {stored SAME_FAMILY pairs} with {candidate fires} via
        :func:`_cluster_edges` (strictly additive on the stored system);
      * non-passthrough date -> ``cluster_verdicts`` over
        ``regression._row_to_metrics`` rows (dur fields attached), matching
        the cached-score recompute branch key-for-key.
    """
    recompute_dates = {r["date"] for r in raw_scores if r.get("emb_tol2") is not None}
    recompute_dates &= set(frozen_dates)
    corr_changed = ((cfg.get("match", {}) or {}).get("cluster_threshold")
                    != (baseline_cfg.get("match", {}) or {}).get("cluster_threshold"))
    have_secondary_cols = any(c in cols for c in R._SECONDARY_METRIC_COLS)

    current_pred: dict[tuple, bool] = {}
    date_rows: dict[str, list[dict]] = {}
    passthrough_dates: set[str] = set()
    for date in frozen_dates:
        if date not in recompute_dates:
            cp, _recomputed = R._candidate_verdicts_for_date(
                conn, cols, date, cfg, lineage, baseline_cfg)
            current_pred.update(cp)
            continue
        rows = _load_date_rows(conn, cols, date)
        have_secondary = have_secondary_cols and any(
            any(r.get(c) is not None for c in R._SECONDARY_METRIC_COLS) for r in rows)
        if not have_secondary and not corr_changed:
            # Same passthrough branch as regression.py:_candidate_verdicts_for_date.
            passthrough_dates.add(date)
            date_rows[date] = rows
            for r in rows:
                a, b = r["lb_a"], r["lb_b"]
                current_pred[(min(a, b), max(a, b))] = \
                    r["tapematch_verdict"] == V.SAME_FAMILY
        else:
            metrics_rows = [_metrics_with_extras(r) for r in rows]
            date_rows[date] = metrics_rows
            verdicts = V.cluster_verdicts(metrics_rows, cfg, lineage)
            for k, v in verdicts.items():
                current_pred[k] = v == V.SAME_FAMILY
    return current_pred, date_rows, recompute_dates, passthrough_dates


def _score_variant(
    pred_map: dict[tuple, bool], truth_map: dict[tuple, int], current_pred: dict[tuple, bool],
) -> tuple[dict, list[tuple], list[tuple]]:
    """Confusion dict + (new_fp keys, fn_flip keys) for one (variant, T)."""
    tp = fn = fp = tn = 0
    new_fps: list[tuple] = []
    fn_flips: list[tuple] = []
    for key, truth in truth_map.items():
        if key not in pred_map:
            continue
        pred_same = pred_map[key]
        was_same = current_pred.get(key, False)
        if key[0] == key[1]:
            # Self-pair (two versions of one LB#): union-find marks it
            # same-family trivially and the LB-keyed embed cache scores it
            # 1.0 against itself — unmeasurable, so inherit the baseline.
            pred_same = was_same
        if truth == 1 and pred_same:
            tp += 1
            if not was_same:
                fn_flips.append(key)
        elif truth == 1 and not pred_same:
            fn += 1
        elif truth == 0 and pred_same:
            fp += 1
            if not was_same:
                new_fps.append(key)
        else:
            tn += 1
    n = tp + fn + fp + tn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    conf = {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "n": n, "precision": prec, "recall": rec}
    return conf, new_fps, fn_flips


def _committed_confusion(current_pred: dict[tuple, bool], truth_map: dict[tuple, int]) -> dict:
    """Confusion of the plain committed config (no injection at all)."""
    conf, _new, _flip = _score_variant(current_pred, truth_map, current_pred)
    return conf


def _acceptance_check(
    conn: sqlite3.Connection, cols: set[str], frozen_dates: list[str],
    cfg: dict, baseline_cfg: dict, lineage,
    truth_map: dict[tuple, int], current_pred: dict[tuple, bool],
) -> bool:
    """Startup gate: with no injection, this script's baseline confusion must
    equal ``regression.py score --cached`` with ``addon_links.rule_d`` disabled.

    The sweep evaluates each (variant, T) candidate as a REPLACEMENT for the
    shipped Rule D (the candidate re-scores the same emb signal from a new
    cache/threshold), so its no-injection baseline is deliberately the
    pre-Rule-D system — flip counts stay comparable with the shipped +25.
    ``score --cached`` itself grew a passthrough∪rule_d union when Rule D
    shipped (2026-07-04, ``_passthrough_with_rule_d``), so the reference here
    strips rule_d before reproducing it; the committed-config confusion
    (rule_d on) is printed alongside so the shipped delta stays visible.
    Returns True on match; prints a loud warning and returns False on any
    mismatch.
    """
    import copy
    stripped_cfg = copy.deepcopy(cfg)
    rule_d = (stripped_cfg.get("addon_links") or {}).get("rule_d")
    if rule_d:
        rule_d["enabled"] = False
    ref_pred: dict[tuple, bool] = {}
    committed_pred: dict[tuple, bool] = {}
    for date in frozen_dates:
        cp, _recomputed = R._candidate_verdicts_for_date(
            conn, cols, date, stripped_cfg, lineage, baseline_cfg)
        ref_pred.update(cp)
        cp_full, _recomputed_full = R._candidate_verdicts_for_date(
            conn, cols, date, cfg, lineage, baseline_cfg)
        committed_pred.update(cp_full)
    ref_conf, _n, _f = _score_variant(ref_pred, truth_map, ref_pred)
    full_conf, _n3, _f3 = _score_variant(committed_pred, truth_map, committed_pred)
    our_conf, _n2, _f2 = _score_variant(current_pred, truth_map, current_pred)
    fields = ("tp", "fn", "fp", "tn")
    ok = all(ref_conf[f] == our_conf[f] for f in fields)
    print("Acceptance check (baseline must equal `score --cached` with rule_d OFF —")
    print("the sweep replaces Rule D, so flips are counted from the pre-Rule-D system):")
    print(f"  score --cached, rule_d off : tp={ref_conf['tp']} fn={ref_conf['fn']} "
          f"fp={ref_conf['fp']} tn={ref_conf['tn']}")
    print(f"  this script                : tp={our_conf['tp']} fn={our_conf['fn']} "
          f"fp={our_conf['fp']} tn={our_conf['tn']}")
    print(f"  (shipped system, rule_d on : tp={full_conf['tp']} fn={full_conf['fn']} "
          f"fp={full_conf['fp']} tn={full_conf['tn']} — candidate must beat "
          f"tp by > {full_conf['tp'] - ref_conf['tp']} flips to ship)")
    if ok:
        print("  -> MATCH\n")
    else:
        print("  -> *** MISMATCH — baseline reproduction is broken; every number "
              "below is untrustworthy. Fix before reading the sweep. ***\n")
    return ok


def _genuine_negative_emb_stats(
    truth_map: dict[tuple, int], scores_by_key: dict[PairKey, dict],
    suspect: set[tuple[int, int]],
) -> tuple[int, float | None, float | None]:
    """(n, median, max) of ``emb_tol2`` over frozen negatives, excluding pairs
    flagged ``label_suspect=1`` and pairs with no emb score at all."""
    vals = []
    for key, truth in truth_map.items():
        if truth != 0 or key in suspect:
            continue
        s = scores_by_key.get(key)
        if s is None or s.get("emb_tol2") is None:
            continue
        vals.append(s["emb_tol2"])
    if not vals:
        return 0, None, None
    return len(vals), statistics.median(vals), max(vals)


def _fmt_key(key: PairKey, scores_by_key: dict[PairKey, dict]) -> str:
    a, b = key
    date = scores_by_key.get(key, {}).get("date", "????-??-??")
    return f"{date}  LB-{a:05d}/LB-{b:05d}"


def _detail_lines(keys: list[PairKey], scores_by_key: dict[PairKey, dict]) -> list[str]:
    lines = []
    for key in sorted(keys):
        s = scores_by_key.get(key, {})
        lines.append(
            f"  - {_fmt_key(key, scores_by_key)}  tag={s.get('tag', '?')}  "
            f"corr={s.get('corr')!s}  emb_tol2={s.get('emb_tol2')!s}  "
            f"emb_tol0={s.get('emb_tol0')!s}"
        )
    return lines


def _print_report(
    grid: list[float], results: dict[tuple[str, float], dict], scores_by_key: dict[PairKey, dict],
    baseline_conf: dict, genuine_neg_stats: tuple[int, float | None, float | None],
    set_path: Path, scores_path: Path,
) -> None:
    n_neg, med_neg, max_neg = genuine_neg_stats
    print(f"# emb_fullset_eval — {scores_path.name} vs {set_path.name}\n")
    print(f"Grid: {grid[0]:.3f} .. {grid[-1]:.3f} step "
          f"{(grid[1] - grid[0]) if len(grid) > 1 else 0:.3f}  "
          f"({len(grid)} thresholds x {len(VARIANTS)} variants)\n")
    print(f"Baseline (committed config, no injection): "
          f"tp={baseline_conf['tp']} fn={baseline_conf['fn']} fp={baseline_conf['fp']} "
          f"tn={baseline_conf['tn']}  P={baseline_conf['precision']:.3f} "
          f"R={baseline_conf['recall']:.3f}\n")
    if n_neg:
        print(f"Genuine negatives (label_suspect != 1), emb_tol2 available: n={n_neg}  "
              f"median={med_neg:.3f}  max={max_neg:.3f}\n")
    else:
        print("Genuine negatives: no emb_tol2 coverage yet.\n")

    header = "| T     |"
    sep = "|-------|"
    for v in VARIANTS:
        header += f" {v} abs_fp | {v} fn_flips |"
        sep += "---------|-------------|"
    print(header)
    print(sep)
    for t in grid:
        row = f"| {t:.3f} |"
        for v in VARIANTS:
            r = results[(v, t)]
            row += f" {r['conf']['fp']:>7d} | {len(r['fn_flips']):>11d} |"
        print(row)

    print("\n## New FP detail\n")
    any_new_fp = False
    for v in VARIANTS:
        for t in grid:
            r = results[(v, t)]
            if r["new_fps"]:
                any_new_fp = True
                print(f"### {v}  T={t:.3f}  ({len(r['new_fps'])} new FP)")
                print("\n".join(_detail_lines(r["new_fps"], scores_by_key)))
                print()
    if not any_new_fp:
        print("(none across the grid)\n")

    print("## FN flip detail\n")
    any_flip = False
    for v in VARIANTS:
        for t in grid:
            r = results[(v, t)]
            if r["fn_flips"]:
                any_flip = True
                print(f"### {v}  T={t:.3f}  ({len(r['fn_flips'])} FN -> TP)")
                print("\n".join(_detail_lines(r["fn_flips"], scores_by_key)))
                print()
    if not any_flip:
        print("(none across the grid)\n")


def main(argv=None) -> int:
    """Sweep the emb_tol2/emb_tol0 threshold grid across three candidate OR
    rules and report absolute FP + FN-flip counts against a frozen label set.
    See module docstring for the injection mechanism and methodology."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", type=Path, default=DEFAULT_SCORES,
                    help="pair scores JSON from emb_score_pairs.py")
    ap.add_argument("--set", type=Path, default=DEFAULT_SET,
                    help="frozen regression set to score against")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH,
                    help="config.yaml to run unchanged (default: committed)")
    ap.add_argument("--min-t", type=float, default=DEFAULT_MIN_T)
    ap.add_argument("--max-t", type=float, default=DEFAULT_MAX_T)
    ap.add_argument("--step", type=float, default=DEFAULT_STEP)
    args = ap.parse_args(argv)

    frozen = R._load_frozen(args.set)
    truth_map = R._truth_map(frozen)
    frozen_dates = sorted(R._dates_of(frozen))
    cfg = yaml.safe_load(args.config.read_text())
    baseline_cfg = yaml.safe_load(CONFIG_PATH.read_text())
    lineage = V.load_lineage_pairs(LB_DB_PATH) if LB_DB_PATH.exists() else set()
    raw_scores, scores_by_key = _load_scores(args.scores)

    conn = R._connect(OBS_DB_PATH)
    try:
        cols = R._pair_columns(conn)
        current_pred, date_rows, recompute_dates, passthrough_dates = _build_predictions(
            conn, cols, frozen_dates, raw_scores, cfg, baseline_cfg, lineage)
        _acceptance_check(conn, cols, frozen_dates, cfg, baseline_cfg, lineage,
                         truth_map, current_pred)
        suspect = _label_suspect_keys(conn, cols)
    finally:
        conn.close()

    baseline_conf = _committed_confusion(current_pred, truth_map)
    genuine_neg_stats = _genuine_negative_emb_stats(truth_map, scores_by_key, suspect)

    grid = _t_grid(args.min_t, args.max_t, args.step)
    results: dict[tuple[str, float], dict] = {}
    for variant in VARIANTS:
        for t in grid:
            candidate = _make_candidate(variant, t, scores_by_key)
            pred_map = dict(current_pred)
            for date in recompute_dates:
                if date in passthrough_dates:
                    # Additive on stored system: edges = stored SAME ∪ candidate.
                    def link_fn(r, _c=candidate):
                        return r["tapematch_verdict"] == V.SAME_FAMILY or _c(r)
                    pred_map.update(_cluster_edges(date_rows[date], link_fn))
                else:
                    pred_map.update(_cluster_with_injection(
                        date_rows[date], cfg, lineage, candidate))
            conf, new_fps, fn_flips = _score_variant(pred_map, truth_map, current_pred)
            results[(variant, t)] = {"conf": conf, "new_fps": new_fps, "fn_flips": fn_flips}

    _print_report(grid, results, scores_by_key, baseline_conf, genuine_neg_stats,
                 args.set, args.scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
