#!/usr/bin/env python3
"""regression.py — tapematch recall/precision regression harness.

Implements Task 1 of ``instructions/CC_TAPEMATCH_FIXES.md``. Freezes the current
curator-labeled pair population as a regression set and scores any candidate
configuration/code state against it.

Governing constraint: **precision is the asset.** A change that raises recall
but adds a false positive on the frozen negative set is REJECTED — ``score``
exits non-zero and lists each new FP individually for human review.

Subcommands
-----------
    freeze [--force]
        Extract the labeled pairs from observations.db (deduped via the
        ``latest_pairs`` view) and write ``regression_set.json``. Committed to
        git; only regenerated with --force.

    score --dates D1,D2,...   |   --all-frozen-dates    [--config PATH]
        Re-run the tapematch session for each date (AUDIO — expensive) and
        score the resulting family verdicts against the frozen set.

    score --cached            [--config PATH]
        Re-score from the stored ``latest_pairs`` rows without re-running audio.
        Faithful only for changes reproducible from persisted per-pair metrics
        (corr, and — once added + repopulated — windowed_frac / hiss_frac /
        hiss_median / fp_score). With the committed config it reproduces the
        stored verdicts exactly (baseline reproduction).

All analysis queries read the ``latest_pairs`` view, never ``pairs`` directly
(Task 1.4 stale-data guard).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# tapematch package is a sibling dir; make it importable when run as a script.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from tapematch import verdict as V  # noqa: E402

PROJECT_ROOT = _HERE.parent.parent
OBS_DB_PATH = _HERE / "observations.db"
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
CONFIG_PATH = _HERE / "config.yaml"
FROZEN_PATH = _HERE / "regression_set.json"
SESSION_SCRIPT = _HERE / "tapematch_session.py"

# The published audit baseline (raw pairs, pre-dedup) from the spec Context table.
# The frozen set is deduped via latest_pairs; the small drift is logged at freeze.
AUDIT_BASELINE = {
    "tp": 663, "fn": 1066, "fp": 12, "tn": 1422,
    "precision": 0.982, "recall": 0.383,
}

# Metric columns the cached recompute needs beyond corr. Absent historically.
_SECONDARY_METRIC_COLS = ("windowed_frac", "hiss_frac", "hiss_median", "fp_score",
                          "fp_triplet_score", "flaw_match_score",
                          "flaw_n_events_a", "flaw_n_events_b", "spec_stationarity",
                          "env_corr")

# CC_TAPEMATCH_ADDON.md Task 5.3 — the Tier A/B addon_links signals whose FN
# coverage bounds their max recall contribution. emb_score has no persisted
# column yet (Task 6); it is only reported once/if `pairs.emb_score` exists.
_ADDON_METRIC_COLS = ("flaw_match_score", "spec_stationarity", "env_corr", "emb_score")


# ── shared helpers ──────────────────────────────────────────────────────────
def _connect(db_path: Path):
    import sqlite3
    if not db_path.exists():
        sys.exit(f"error: DB not found: {db_path}")
    return sqlite3.connect(str(db_path))


def _pair_columns(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(pairs)")}


def _truth(lb_says_same, human_judgment) -> int | None:
    """Ground-truth label for a pair: human judgment outranks lb_says_same."""
    if human_judgment == "confirmed_same":
        return 1
    if human_judgment == "confirmed_different":
        return 0
    if lb_says_same in (0, 1):
        return lb_says_same
    return None


def _confusion(items) -> dict:
    """items: iterable of (truth:int, pred_same:bool). Returns confusion dict."""
    tp = fn = fp = tn = 0
    for truth, pred_same in items:
        if truth == 1 and pred_same:
            tp += 1
        elif truth == 1 and not pred_same:
            fn += 1
        elif truth == 0 and pred_same:
            fp += 1
        else:
            tn += 1
    n = tp + fn + fp + tn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "n": n,
            "precision": prec, "recall": rec}


# ── freeze ──────────────────────────────────────────────────────────────────
def _labeled_rows(conn):
    """All labeled latest_pairs rows with the columns freeze/score need."""
    return conn.execute(
        """SELECT concert_date, lb_a, lb_b, lb_says_same, human_judgment,
                  tapematch_verdict
           FROM latest_pairs
           WHERE lb_says_same IN (0, 1)
              OR human_judgment IN ('confirmed_same', 'confirmed_different')"""
    ).fetchall()


def cmd_freeze(args) -> int:
    if FROZEN_PATH.exists() and not args.force:
        sys.exit(f"error: {FROZEN_PATH.name} exists; pass --force to regenerate.")
    conn = _connect(OBS_DB_PATH)
    try:
        rows = _labeled_rows(conn)
    finally:
        conn.close()

    positives, negatives = [], []
    frozen_conf = []  # (truth, pred_same) using stored verdict — for drift log
    for date, a, b, ss, hj, tv in rows:
        truth = _truth(ss, hj)
        if truth is None:
            continue
        entry = [a, b, date]
        (positives if truth == 1 else negatives).append(entry)
        frozen_conf.append((truth, tv == V.SAME_FAMILY))

    frozen_actual = _confusion(frozen_conf)
    payload = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(OBS_DB_PATH.relative_to(PROJECT_ROOT)),
        "positives": positives,
        "negatives": negatives,
        "baseline": AUDIT_BASELINE,
        "frozen_set_actual": frozen_actual,  # deduped-set reproduction of baseline
    }
    FROZEN_PATH.write_text(json.dumps(payload, indent=2))

    print(f"froze {len(positives)} positives + {len(negatives)} negatives "
          f"= {len(positives) + len(negatives)} labeled pairs -> {FROZEN_PATH.name}")
    print("\naudit baseline (raw pairs, pre-dedup):")
    print(f"  tp={AUDIT_BASELINE['tp']} fn={AUDIT_BASELINE['fn']} "
          f"fp={AUDIT_BASELINE['fp']} tn={AUDIT_BASELINE['tn']}  "
          f"P={AUDIT_BASELINE['precision']:.3f} R={AUDIT_BASELINE['recall']:.3f}")
    print("frozen set actual (deduped via latest_pairs):")
    print(f"  tp={frozen_actual['tp']} fn={frozen_actual['fn']} "
          f"fp={frozen_actual['fp']} tn={frozen_actual['tn']}  "
          f"P={frozen_actual['precision']:.3f} R={frozen_actual['recall']:.3f}")
    dtp = frozen_actual['tp'] - AUDIT_BASELINE['tp']
    dfp = frozen_actual['fp'] - AUDIT_BASELINE['fp']
    print(f"dedup drift vs audit: tp {dtp:+d}, fp {dfp:+d} "
          f"(expected — dedup removed stale duplicate rows; logged per spec 1.1)")
    return 0


# ── scoring ─────────────────────────────────────────────────────────────────
def _load_frozen(path: Path = FROZEN_PATH) -> dict:
    if not path.exists():
        sys.exit(f"error: {path.name} not found — run `freeze` first.")
    return json.loads(path.read_text())


def _truth_map(frozen) -> dict[tuple, int]:
    out = {}
    for a, b, _date in frozen["positives"]:
        out[(min(a, b), max(a, b))] = 1
    for a, b, _date in frozen["negatives"]:
        out[(min(a, b), max(a, b))] = 0
    return out


def _dates_of(frozen) -> set[str]:
    return {d for _a, _b, d in frozen["positives"] + frozen["negatives"]}


def _row_to_metrics(row: dict) -> dict:
    """Build a verdict metrics dict from a latest_pairs row dict."""
    return {k: row.get(k) for k in V.METRIC_KEYS}


def _passthrough_with_rule_d(raw: list[dict], cfg: dict) -> dict[tuple, bool]:
    """Passthrough-branch verdicts, additively unioned with addon_links.rule_d.

    Stored ``tapematch_verdict`` values are authoritative for historical
    rows: a full metric replay of every pair on a passthrough date loses
    ~147 stored merges that upstream signals (curator lineage, retired
    live-session metrics, etc.) established but that are not reproducible
    from the columns available here (this is exactly why the passthrough
    branch exists at all). Rule D must therefore be strictly ADDITIVE on top
    of that stored system, never a replacement for it: the edge set is
    {rows whose stored verdict is SAME_FAMILY} UNION {rows where
    ``verdict._rule_d_emb_both`` fires}, and each pair's verdict is derived
    from the resulting connected components — mirroring
    ``emb_fullset_eval.py:_cluster_edges``'s additive union semantics.

    Self-pairs (``lb_a == lb_b``, two versions of the same recording) keep
    their stored verdict verbatim and never participate in the union-find:
    they must never inherit the component identity of an unrelated LB pair
    through incidental transitive linking, and rule_d itself never fires on
    a self-pair (see ``verdict._rule_d_emb_both``).
    """
    valid = [r for r in raw if r.get("lb_a") is not None and r.get("lb_b") is not None]
    al_cfg = cfg.get("addon_links", {}) or {}

    nodes: dict[int, int] = {}

    def node(x: int) -> int:
        if x not in nodes:
            nodes[x] = len(nodes)
        return nodes[x]

    cross_rows = [r for r in valid if r["lb_a"] != r["lb_b"]]
    for r in cross_rows:
        node(r["lb_a"])
        node(r["lb_b"])
    parent = list(range(len(nodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in cross_rows:
        stored_same = r.get("tapematch_verdict") == V.SAME_FAMILY
        if stored_same or V._rule_d_emb_both(r, al_cfg):
            ra, rb = find(node(r["lb_a"])), find(node(r["lb_b"]))
            parent[ra] = rb

    out: dict[tuple, bool] = {}
    for r in valid:
        a, b = r["lb_a"], r["lb_b"]
        key = (min(a, b), max(a, b))
        if a == b:
            out[key] = r.get("tapematch_verdict") == V.SAME_FAMILY
        else:
            out[key] = find(node(a)) == find(node(b))
    return out


def _candidate_verdicts_for_date(conn, cols, date, cfg, lineage,
                                 baseline_cfg) -> tuple[dict, bool]:
    """Return ({(lb_lo,lb_hi): pred_same_bool}, recomputed?) for one date.

    If the secondary/fp metric columns are unavailable (historical rows), and
    the candidate corr threshold equals the committed baseline threshold, pass
    the stored verdicts through unchanged (exact reproduction). Otherwise
    recompute family membership from stored metrics via verdict.cluster_verdicts.

    ``emb_score``/``emb_score_global`` are deliberately excluded from
    ``_SECONDARY_METRIC_COLS`` (they must never flip the ``have_secondary``
    test — routing a passthrough date through a full metric replay loses its
    stored merges, corrupting the tp 659->512 baseline). Instead, when
    ``addon_links.rule_d.enabled`` and at least one row on this date carries a
    non-NULL ``emb_score``, the passthrough result is additively unioned with
    rule_d via :func:`_passthrough_with_rule_d` rather than returned raw. With
    rule_d disabled, or no ``emb_score`` populated yet on this date, this is
    byte-identical to the plain passthrough below.
    """
    sel = "concert_date, lb_a, lb_b, tapematch_verdict, " + ", ".join(
        c for c in V.METRIC_KEYS if c in cols)
    q = f"SELECT {sel} FROM latest_pairs WHERE concert_date = ?"
    raw = [dict(zip([d[0] for d in cur.description], r))
           for cur in [conn.execute(q, (date,))] for r in cur.fetchall()]

    have_secondary = any(c in cols for c in _SECONDARY_METRIC_COLS) and any(
        any(r.get(c) is not None for c in _SECONDARY_METRIC_COLS) for r in raw)
    corr_changed = ((cfg.get("match", {}) or {}).get("cluster_threshold")
                    != (baseline_cfg.get("match", {}) or {}).get("cluster_threshold"))

    if not have_secondary and not corr_changed:
        rule_d_enabled = ((cfg.get("addon_links", {}) or {})
                          .get("rule_d", {}) or {}).get("enabled")
        has_emb = any(r.get("emb_score") is not None for r in raw)
        if rule_d_enabled and has_emb:
            return _passthrough_with_rule_d(raw, cfg), True
        # Passthrough: candidate == stored system verdict.
        out = {}
        for r in raw:
            a, b = r["lb_a"], r["lb_b"]
            if a is None or b is None:
                continue
            out[(min(a, b), max(a, b))] = r["tapematch_verdict"] == V.SAME_FAMILY
        return out, False

    metrics = [_row_to_metrics(r) for r in raw
               if r["lb_a"] is not None and r["lb_b"] is not None]
    verdicts = V.cluster_verdicts(metrics, cfg, lineage)
    return {k: v == V.SAME_FAMILY for k, v in verdicts.items()}, True


def _strip_overrides(cfg: dict) -> dict:
    """Return a deep-ish copy of cfg with the Task 3/4 conditional-threshold
    override keys removed, reconstructing pre-change (baseline) behaviour."""
    import copy
    c = copy.deepcopy(cfg)
    for key in ("cluster_threshold_staircase", "cluster_threshold_curator"):
        c.get("fingerprint", {}).pop(key, None)
    for key in ("hiss_merge_median_lofi", "hiss_lofi_ceiling_hz"):
        c.get("secondary_match", {}).pop(key, None)
    return c


def _baseline_pred_map(conn, dates) -> dict[tuple, bool]:
    """Stored-verdict prediction per pair across the given dates (the baseline)."""
    out = {}
    qmarks = ",".join("?" * len(dates))
    for date, a, b, tv in conn.execute(
            f"SELECT concert_date, lb_a, lb_b, tapematch_verdict "
            f"FROM latest_pairs WHERE concert_date IN ({qmarks})", tuple(dates)):
        if a is None or b is None:
            continue
        out[(min(a, b), max(a, b))] = tv == V.SAME_FAMILY
    return out


def cmd_score(args) -> int:
    frozen = _load_frozen(Path(args.set))
    truth_map = _truth_map(frozen)
    cfg = yaml.safe_load(Path(args.config).read_text())
    baseline_cfg = yaml.safe_load(CONFIG_PATH.read_text())
    lineage = V.load_lineage_pairs(LB_DB_PATH) if LB_DB_PATH.exists() else set()

    frozen_dates = _dates_of(frozen)
    if args.cached:
        dates = sorted(frozen_dates)
    elif args.all_frozen_dates:
        dates = sorted(frozen_dates)
    elif args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        sys.exit("error: score needs --cached, --dates, or --all-frozen-dates.")

    if not args.cached:
        _run_sessions_live(dates)

    # Baseline = current production behaviour = candidate config with the Task 3/4
    # conditional-threshold overrides stripped. On dates re-run with the new schema
    # (raw secondary metrics present) BOTH sides recompute from the same metrics, so
    # the delta isolates exactly the threshold change. On un-re-run dates both fall
    # back to the stored verdict, yielding no delta (honest: unmeasurable without a run).
    base_cfg = _strip_overrides(cfg)

    conn = _connect(OBS_DB_PATH)
    try:
        cols = _pair_columns(conn)
        cand_pred: dict[tuple, bool] = {}
        base_pred: dict[tuple, bool] = {}
        any_recompute = False
        for date in dates:
            cp, recomputed = _candidate_verdicts_for_date(
                conn, cols, date, cfg, lineage, baseline_cfg)
            bp, _ = _candidate_verdicts_for_date(
                conn, cols, date, base_cfg, lineage, baseline_cfg)
            cand_pred.update(cp)
            base_pred.update(bp)
            any_recompute = any_recompute or recomputed
    finally:
        conn.close()

    # Restrict to frozen pairs that fall on the scored dates.
    scored_keys = [k for k in truth_map if k in cand_pred]
    cand_conf = _confusion((truth_map[k], cand_pred[k]) for k in scored_keys)
    base_conf = _confusion((truth_map[k], base_pred.get(k, False))
                           for k in scored_keys)

    # New FPs: candidate FP where the pair was a baseline TN (truth 0).
    new_fps = [k for k in scored_keys
               if truth_map[k] == 0 and cand_pred[k] and not base_pred.get(k, False)]

    _print_score(cand_conf, base_conf, new_fps, dates, any_recompute, args)

    if args.cached:
        conn = _connect(OBS_DB_PATH)
        try:
            cols = _pair_columns(conn)
            coverage = _addon_coverage(conn, cols, dates, truth_map, cand_pred)
        finally:
            conn.close()
        _print_addon_coverage(coverage)

    return 1 if new_fps else 0


def _run_sessions_live(dates) -> None:
    print(f"[live] re-running tapematch for {len(dates)} date(s) — this decodes "
          f"audio and may take a long time.\n", flush=True)
    for i, date in enumerate(dates, 1):
        print(f"[live {i}/{len(dates)}] {date}", flush=True)
        r = subprocess.run(
            [sys.executable, str(SESSION_SCRIPT), date],
            cwd=str(_HERE))
        if r.returncode != 0:
            print(f"  warning: session for {date} exited {r.returncode}",
                  file=sys.stderr)


def _addon_coverage(conn, cols, dates, truth_map, cand_pred) -> list[tuple[str, int, int]]:
    """Task 5.3 — per-signal coverage over frozen FN pairs.

    A frozen FN is a positive (truth == 1) that the candidate verdicts as
    ``different_family`` on the scored dates. For each addon-links metric
    that exists as a column in ``pairs``, count how many of those FN pairs
    carry a non-NULL value. This bounds the signal's max possible recall
    contribution — a signal that "works" but covers only a handful of the
    FN population cannot move the needle much.

    Returns a list of ``(metric, non_null_count, fn_total)``; empty if none
    of ``_ADDON_METRIC_COLS`` exist yet.
    """
    metrics = [c for c in _ADDON_METRIC_COLS if c in cols]
    fn_keys = {k for k, t in truth_map.items()
              if t == 1 and k in cand_pred and not cand_pred[k]}
    fn_total = len(fn_keys)
    if not metrics or fn_total == 0:
        return [(m, 0, fn_total) for m in metrics]

    sel = ", ".join(["lb_a", "lb_b"] + metrics)
    qmarks = ",".join("?" * len(dates))
    rows = conn.execute(
        f"SELECT {sel} FROM latest_pairs WHERE concert_date IN ({qmarks})",
        tuple(dates)).fetchall()

    counts = {m: 0 for m in metrics}
    for row in rows:
        a, b = row[0], row[1]
        if a is None or b is None:
            continue
        key = (min(a, b), max(a, b))
        if key not in fn_keys:
            continue
        for m, val in zip(metrics, row[2:]):
            if val is not None:
                counts[m] += 1
    return [(m, counts[m], fn_total) for m in metrics]


def _print_addon_coverage(coverage: list[tuple[str, int, int]]) -> None:
    if not coverage:
        return
    fn_total = coverage[0][2]
    print(f"\naddon-links signal coverage (frozen FN, n={fn_total}) — "
          f"bounds each signal's max recall contribution:")
    for metric, non_null, total in coverage:
        pct = (non_null / total * 100) if total else 0.0
        print(f"  {metric:20s}: {non_null:>5d} / {total:<5d}  ({pct:5.1f}%)")


def _print_score(cand, base, new_fps, dates, recomputed, args) -> None:
    mode = "cached" if args.cached else "live"
    print(f"\n=== regression score ({mode}"
          f"{'; recomputed' if recomputed else '; passthrough'}) "
          f"— {len(dates)} date(s), {cand['n']} frozen pairs ===\n")
    print(f"{'':11s}{'baseline':>10s}{'candidate':>12s}{'delta':>9s}")
    dr = (cand['recall'] - base['recall']) * 100
    dp = (cand['precision'] - base['precision']) * 100
    print(f"{'recall':11s}{base['recall']*100:>9.1f}%{cand['recall']*100:>11.1f}%"
          f"{dr:>+8.1f}")
    print(f"{'precision':11s}{base['precision']*100:>9.1f}%"
          f"{cand['precision']*100:>11.1f}%{dp:>+8.1f}")
    print(f"\nconfusion  baseline: tp={base['tp']} fn={base['fn']} "
          f"fp={base['fp']} tn={base['tn']}")
    print(f"           candidate: tp={cand['tp']} fn={cand['fn']} "
          f"fp={cand['fp']} tn={cand['tn']}")
    if new_fps:
        print(f"\nNEW FALSE POSITIVES ({len(new_fps)}) — each must be reviewed "
              f"or the change REJECTED:")
        for a, b in new_fps:
            print(f"  LB-{a:05d} / LB-{b:05d}")
    else:
        print("\nnew FP: none  (precision preserved on frozen negatives)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    fp = sub.add_parser("freeze", help="freeze the current labeled pair set")
    fp.add_argument("--force", action="store_true",
                    help="overwrite an existing regression_set.json")
    fp.set_defaults(func=cmd_freeze)

    sp = sub.add_parser("score", help="score a candidate against the frozen set")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--dates", help="comma-separated dates to re-run live")
    g.add_argument("--all-frozen-dates", action="store_true",
                   help="re-run every frozen date live (very expensive)")
    g.add_argument("--cached", action="store_true",
                   help="re-score from stored pairs rows, no audio")
    sp.add_argument("--config", default=str(CONFIG_PATH),
                    help="candidate config.yaml (default: committed config)")
    sp.add_argument("--set", default=str(FROZEN_PATH),
                    help="frozen regression set to score against (default: "
                         "regression_set.json)")
    sp.set_defaults(func=cmd_score)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
