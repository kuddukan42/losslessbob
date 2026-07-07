#!/usr/bin/env python3
"""build_fullset_worklist.py — Tier B full frozen-set nmfp worklist builder.

Extends the Task 6.1.4 embedding harness (``build_embed_eval_set.py``, which draws
a ~180-source pilot population) to the *entire* frozen regression set
(``regression_set.json``): every frozen negative pair (same-show TN — the
population that structurally killed the triplet fingerprint) plus every frozen
positive pair the current system currently misses (FN) with corr below a
low-corr cut (the target-recovery population Tier B exists to move).

"Currently FN" is derived exactly the way ``regression.py score --cached``
derives it — imported from ``regression.py``/``tapematch.verdict``, not
reimplemented: per frozen date, ``tapematch.verdict.cluster_verdicts`` (or
stored-verdict passthrough when no secondary metrics are persisted for that
date) against the committed ``config.yaml``, the same population
``regression.py``'s ``_addon_coverage`` calls "frozen FN".

Outputs (next to this script):
  * ``fullset_pairs.json``   — flat pair list: date, lb_a, lb_b, tag
                                ("neg" | "fn_lowcorr"), corr.
  * ``fullset_sources.json`` — deduped per-source metadata, in the same
                                per-source schema ``embed_eval_set.json`` uses,
                                for every source a surviving pair references —
                                consumable directly by ``nmfp_embed.py --eval-set``.
  * with ``--pilot N --seed S``: also ``pilot_pairs.json`` / ``pilot_sources.json``,
    restricted to N random "neg"-tagged pairs (seed-fixed sample) + their sources.

A pair is dropped (and counted) if either of its sources has no ``sources``
table row on the frozen date — nmfp_embed.py would have nothing to decode.
Read-only against observations.db; never runs audio or a model.

    .venv/bin/python3 tools/tapematch/build_fullset_worklist.py
    .venv/bin/python3 tools/tapematch/build_fullset_worklist.py --pilot 40 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import regression as R  # noqa: E402  (reuse verdict/corr derivation, not reimplement)

OBS_DB_PATH = _HERE / "observations.db"
FROZEN_PATH = _HERE / "regression_set.json"
PAIRS_OUT = _HERE / "fullset_pairs.json"
SOURCES_OUT = _HERE / "fullset_sources.json"
PILOT_PAIRS_OUT = _HERE / "pilot_pairs.json"
PILOT_SOURCES_OUT = _HERE / "pilot_sources.json"


def _key(a: int, b: int) -> tuple[int, int]:
    """Canonical undirected pair key."""
    return (min(a, b), max(a, b))


def _load_frozen() -> dict:
    """Load ``regression_set.json`` or exit with a clear error."""
    if not FROZEN_PATH.exists():
        sys.exit(f"error: {FROZEN_PATH.name} not found — run `regression.py freeze` first.")
    return json.loads(FROZEN_PATH.read_text())


def _current_fn_keys(frozen: dict, conn: sqlite3.Connection) -> set[tuple[int, int]]:
    """Frozen-positive pairs the committed system currently calls different_family.

    Exactly ``regression.py score --cached``'s definition of a frozen FN (see its
    ``_addon_coverage``): candidate verdicts == committed config.yaml, no
    baseline-override stripping, computed per frozen date via
    ``_candidate_verdicts_for_date`` (stored-verdict passthrough unless secondary
    metrics are persisted, in which case ``tapematch.verdict.cluster_verdicts``
    recomputes membership from stored metrics).
    """
    cfg = yaml.safe_load(R.CONFIG_PATH.read_text())
    lineage = R.V.load_lineage_pairs(R.LB_DB_PATH) if R.LB_DB_PATH.exists() else set()
    dates = sorted(R._dates_of(frozen))
    cols = R._pair_columns(conn)

    cand_pred: dict[tuple[int, int], bool] = {}
    for date in dates:
        # baseline_cfg == cfg -> corr_changed is always False, matching the
        # default `regression.py score --cached` invocation (--config defaults
        # to the committed config.yaml on both sides).
        cp, _recomputed = R._candidate_verdicts_for_date(conn, cols, date, cfg, lineage, cfg)
        cand_pred.update(cp)

    truth_map = R._truth_map(frozen)
    return {k for k, t in truth_map.items()
            if t == 1 and k in cand_pred and not cand_pred[k]}


def _corr_by_pair(conn: sqlite3.Connection) -> dict[tuple[int, int], sqlite3.Row]:
    """Latest_pairs row per (lb_a,lb_b) key — same access pattern as
    ``build_embed_eval_set.py``'s ``pair_rows``."""
    out: dict[tuple[int, int], sqlite3.Row] = {}
    for r in conn.execute(
        "SELECT lb_a, lb_b, corr, concert_date FROM latest_pairs "
        "WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL"
    ):
        out[_key(r["lb_a"], r["lb_b"])] = r
    return out


def _sources_for(
    conn: sqlite3.Connection, needed_lbs: dict[str, set[int]]
) -> tuple[dict[str, list[dict]], dict[str, set[int]]]:
    """Per-source metadata (embed_eval_set.json schema) + missing lbs by date.

    Mirrors ``build_embed_eval_set.py``'s source query verbatim: latest
    ``sources`` row per (date, lb_number), first occurrence wins (``id DESC``).
    """
    sources_out: dict[str, list[dict]] = {}
    missing_by_date: dict[str, set[int]] = {}
    for d in sorted(needed_lbs):
        if not needed_lbs[d]:
            continue
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
            missing_by_date[d] = missing
        sources_out[d] = srcs
    return sources_out, missing_by_date


def _write_worklist(
    pairs: list[dict], sources: dict[str, list[dict]], dates: list[str],
    params: dict, out_pairs: Path, out_sources: Path
) -> None:
    """Write the ``*_pairs.json`` / ``*_sources.json`` pair, embed_eval_set-shaped."""
    tags = sorted({p["tag"] for p in pairs})
    pairs_payload = {
        "spec": "fullset worklist (Tier B nmfp full-set extension)",
        "params": params,
        "dates": dates,
        "n_pairs": len(pairs),
        "counts": {t: sum(1 for p in pairs if p["tag"] == t) for t in tags},
        "pairs": pairs,
    }
    out_pairs.write_text(json.dumps(pairs_payload, indent=2))
    sources_payload = {
        "spec": "fullset worklist (Tier B nmfp full-set extension)",
        "dates": dates,
        "n_sources": sum(len(v) for v in sources.values()),
        "sources": sources,
    }
    out_sources.write_text(json.dumps(sources_payload, indent=2))


def main() -> int:
    """Build the full-frozen-set (and optional pilot) nmfp worklist. See module docstring."""
    ap = argparse.ArgumentParser(description="Tier B full frozen-set nmfp worklist builder.")
    ap.add_argument("--fn-corr", type=float, default=0.05,
                    help="frozen positive is 'fn_lowcorr' if corr < this AND currently FN.")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    ap.add_argument("--out-pairs", type=Path, default=PAIRS_OUT)
    ap.add_argument("--out-sources", type=Path, default=SOURCES_OUT)
    ap.add_argument("--pilot", type=int, default=0,
                    help="also write pilot_pairs.json/pilot_sources.json restricted "
                         "to N random negative ('neg') pairs.")
    ap.add_argument("--seed", type=int, default=42, help="pilot sample seed.")
    ap.add_argument("--pilot-out-pairs", type=Path, default=PILOT_PAIRS_OUT)
    ap.add_argument("--pilot-out-sources", type=Path, default=PILOT_SOURCES_OUT)
    args = ap.parse_args()

    frozen = _load_frozen()
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row

    fn_keys = _current_fn_keys(frozen, conn)
    corr_by_pair = _corr_by_pair(conn)

    neg_keys = {_key(a, b) for a, b, _d in frozen["negatives"]}

    candidates: list[dict] = []
    for k in neg_keys:
        r = corr_by_pair.get(k)
        if r is None:
            continue  # no latest_pairs row at all — unscorable, same as a metadata miss.
        candidates.append({"date": r["concert_date"], "lb_a": k[0], "lb_b": k[1],
                           "tag": "neg", "corr": r["corr"]})

    n_fn_precorr = 0
    for k in fn_keys:
        r = corr_by_pair.get(k)
        if r is None or r["corr"] is None:
            continue
        n_fn_precorr += 1
        if r["corr"] >= args.fn_corr:
            continue
        candidates.append({"date": r["concert_date"], "lb_a": k[0], "lb_b": k[1],
                           "tag": "fn_lowcorr", "corr": r["corr"]})

    # Collect sources needed, then drop pairs with unresolvable metadata.
    needed_lbs: dict[str, set[int]] = defaultdict(set)
    for p in candidates:
        needed_lbs[p["date"]].update((p["lb_a"], p["lb_b"]))
    sources_out, missing_by_date = _sources_for(conn, needed_lbs)
    conn.close()

    def resolvable(p: dict) -> bool:
        missing = missing_by_date.get(p["date"], set())
        return p["lb_a"] not in missing and p["lb_b"] not in missing

    kept = [p for p in candidates if resolvable(p)]
    n_skipped = len(candidates) - len(kept)

    # Trim the source list to exactly what the kept pairs reference.
    kept_lbs: dict[str, set[int]] = defaultdict(set)
    for p in kept:
        kept_lbs[p["date"]].update((p["lb_a"], p["lb_b"]))
    sources_out = {d: [s for s in srcs if s["lb"] in kept_lbs.get(d, set())]
                  for d, srcs in sources_out.items() if d in kept_lbs}

    dates = sorted(kept_lbs)
    params = {"fn_corr": args.fn_corr}
    _write_worklist(kept, sources_out, dates, params, args.out_pairs, args.out_sources)

    n_neg = sum(1 for p in kept if p["tag"] == "neg")
    n_fn = sum(1 for p in kept if p["tag"] == "fn_lowcorr")
    n_sources = sum(len(v) for v in sources_out.values())
    print(f"fullset worklist -> {args.out_pairs.name} / {args.out_sources.name}")
    print(f"  frozen: neg={len(neg_keys)}  currently-FN positives={len(fn_keys)} "
         f"(with corr recorded: {n_fn_precorr})")
    print(f"  kept: neg={n_neg} fn_lowcorr={n_fn}  "
         f"skipped (missing sources metadata / no latest_pairs row): {n_skipped}")
    print(f"  dates: {len(dates)}   distinct sources: {n_sources}")
    print(f"TOTAL kept={len(kept)} skipped={n_skipped} sources={n_sources} dates={len(dates)}")

    if args.pilot:
        neg_pool = [p for p in kept if p["tag"] == "neg"]
        rng = random.Random(args.seed)
        n = min(args.pilot, len(neg_pool))
        pilot_pairs = rng.sample(neg_pool, n)
        pilot_lbs: dict[str, set[int]] = defaultdict(set)
        for p in pilot_pairs:
            pilot_lbs[p["date"]].update((p["lb_a"], p["lb_b"]))
        pilot_sources = {d: [s for s in sources_out.get(d, []) if s["lb"] in pilot_lbs[d]]
                         for d in pilot_lbs}
        pilot_dates = sorted(pilot_lbs)
        _write_worklist(pilot_pairs, pilot_sources, pilot_dates,
                        {**params, "pilot": args.pilot, "seed": args.seed},
                        args.pilot_out_pairs, args.pilot_out_sources)
        n_pilot_sources = sum(len(v) for v in pilot_sources.values())
        print(f"\npilot worklist (seed={args.seed}) -> {args.pilot_out_pairs.name} / "
             f"{args.pilot_out_sources.name}")
        print(f"  pairs: {len(pilot_pairs)}/{args.pilot} requested   "
             f"dates: {len(pilot_dates)}   sources: {n_pilot_sources}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
