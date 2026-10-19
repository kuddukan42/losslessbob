#!/usr/bin/env python3
"""TODO-319 — measure the ``family_guard`` against stored pair metrics (read-only).

Replays every date's synced run (``backend.tapematch_sync._pick_best_run``)
through ``verdict.cluster_verdicts`` twice — shipped ``config.yaml`` as is, and
the same config with a ``family_guard`` variant enabled — and reports what the
guard changes. Dates whose stored verdicts the offline model cannot reproduce
under their own run config (the ``replay_writeback.py`` fidelity gate) are
counted but not measured. Nothing is written to any DB.

Usage:
    .venv/bin/python3 tools/tapematch/chain_overmerge_replay.py [--db PATH]
        [--density 0.5] [--strong primary,rule_d] [--json OUT]
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

SESSION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSION_DIR.parents[1]
for _p in (str(SESSION_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tapematch import verdict as V  # noqa: E402

OBS_DB_PATH = SESSION_DIR / "observations.db"
CONFIG_PATH = SESSION_DIR / "config.yaml"
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
FROZEN_PATH = SESSION_DIR / "regression_set.json"
QUEUE_PATH = PROJECT_ROOT / "data" / "tapematch" / "false_merge_queue.json"

# Dates TODO-319 names as suspected chain over-merges.
NAMED_DATES = (
    "2010-03-23", "2010-03-24", "2010-03-28", "2010-03-29", "2007-04-08",
    "2007-04-04", "2011-10-21", "2008-06-11", "2002-04-28", "2004-03-05",
    "2009-10-10", "1997-12-10", "2024-04-06", "2003-10-17", "1997-12-08",
    "1997-12-18", "2009-07-05", "2012-07-03", "2011-06-26", "2003-04-19",
    "2004-11-13", "2004-03-01", "2004-06-08", "2000-09-20", "2002-10-11",
    "2001-10-12",
)

log = logging.getLogger("chain_overmerge_replay")


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_lineage(path: Path) -> set[tuple[int, int]]:
    """Curator lineage pairs, read-only (``verdict.load_lineage_pairs`` opens rw)."""
    out: set[tuple[int, int]] = set()
    if not path.exists():
        return out
    conn = _ro(path)
    try:
        for lb, same in conn.execute(
                "SELECT lb_number, same_as_lb FROM entry_lineage "
                "WHERE same_as_lb IS NOT NULL AND same_as_lb != '[]'"):
            for other in json.loads(same) if same else []:
                if isinstance(other, int):
                    out.add((min(lb, other), max(lb, other)))
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return out


def partition(verdicts: dict[tuple, str], lbs: set[int]) -> set[frozenset[int]]:
    """Families implied by SAME_FAMILY verdicts; unpaired lbs are singletons."""
    fam = {lb: {lb} for lb in lbs}
    for (a, b), v in verdicts.items():
        if v == V.SAME_FAMILY and fam[a] is not fam[b]:
            merged = fam[a] | fam[b]
            for m in merged:
                fam[m] = merged
    return {frozenset(s) for s in fam.values()}


def guard_cfg(cfg: dict[str, Any], density: float, strong: list[str]) -> dict[str, Any]:
    """``cfg`` with the family guard switched on at the given knobs."""
    out = copy.deepcopy(cfg)
    out["family_guard"] = {"enabled": True, "strong_legs": strong,
                           "min_link_density": density}
    return out


def measure(db_path: Path, cfg: dict[str, Any], gcfg: dict[str, Any],
            lineage: set[tuple[int, int]], truth: dict[tuple, int],
            queue: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay every synced run under ``cfg`` and ``gcfg``; collect the deltas."""
    from backend.tapematch_sync import _pick_best_run
    conn = _ro(db_path)
    stats: Counter = Counter()
    per_date: dict[str, dict[str, Any]] = {}
    frozen = {"base": Counter(), "guard": Counter()}
    tp_lost: list[tuple] = []
    fp_cleared: list[tuple] = []
    base_pred: dict[tuple, bool] = {}
    guard_pred: dict[tuple, bool] = {}
    direct: dict[tuple, str | None] = {}
    try:
        for date, run_id in sorted(_pick_best_run(conn).items()):
            run = conn.execute("SELECT config_json FROM runs WHERE run_id = ?",
                               (run_id,)).fetchone()
            era = json.loads(run["config_json"]) if run["config_json"] else None
            pairs = [dict(r) for r in conn.execute(
                "SELECT * FROM pairs WHERE run_id = ?", (run_id,))]
            pairs = [p for p in pairs if p["lb_a"] is not None and p["lb_b"] is not None]
            if not era or not pairs:
                stats["dates_unmeasurable"] += 1
                continue
            stored = V.cluster_verdicts(pairs, era, lineage)
            if any(stored[(min(p["lb_a"], p["lb_b"]), max(p["lb_a"], p["lb_b"]))]
                   != p["tapematch_verdict"] for p in pairs):
                stats["dates_fidelity_mismatch"] += 1
                per_date[date] = {"status": "fidelity_mismatch", "run_id": run_id}
                continue
            stats["dates_measured"] += 1
            lbs = {p["lb_a"] for p in pairs} | {p["lb_b"] for p in pairs}
            base = V.cluster_verdicts(pairs, cfg, lineage)
            guard = V.cluster_verdicts(pairs, gcfg, lineage)
            for p in pairs:
                k = (min(p["lb_a"], p["lb_b"]), max(p["lb_a"], p["lb_b"]))
                direct[(date, *k)] = V.link_mechanism(p, cfg, lineage)
                base_pred[(date, *k)] = base[k] == V.SAME_FAMILY
                guard_pred[(date, *k)] = guard[k] == V.SAME_FAMILY
                if base[k] == V.SAME_FAMILY:
                    stats["base_same_pairs"] += 1
                    if direct[(date, *k)] is None:
                        stats["base_same_pairs_chained"] += 1
            pb, pg = partition(base, lbs), partition(guard, lbs)
            per_date[date] = {
                "status": "changed" if pb != pg else "unchanged", "run_id": run_id,
                "n_sources": len(lbs), "families_stored": len(partition(stored, lbs)),
                "families_base": len(pb), "families_guard": len(pg),
                "base": sorted(sorted(f) for f in pb), "guard": sorted(sorted(f) for f in pg),
            }
            if pb != pg:
                stats["dates_changed"] += 1
                stats["families_added"] += len(pg) - len(pb)
                stats["base_families_split"] += len(pb - pg)
    finally:
        conn.close()

    # Frozen regression set — truth keyed (lo, hi) without date, as regression.py does.
    for (date, a, b), same in base_pred.items():
        t = truth.get((a, b))
        if t is None:
            continue
        g = guard_pred[(date, a, b)]
        for tag, pred in (("base", same), ("guard", g)):
            frozen[tag]["tp" if t and pred else "fn" if t else "fp" if pred else "tn"] += 1
        chained = direct[(date, a, b)] is None
        if same:
            frozen["base"][("pos" if t else "neg") + ("_chained" if chained else "_direct")] += 1
        if t == 1 and same and not g:
            tp_lost.append((date, a, b, direct[(date, a, b)]))
        if t == 0 and same and not g:
            fp_cleared.append((date, a, b, direct[(date, a, b)]))

    q_out = Counter()
    for row in queue:
        k = (row["concert_date"], min(row["lb_a"], row["lb_b"]), max(row["lb_a"], row["lb_b"]))
        if k not in base_pred:
            q_out["not_measured"] += 1
            continue
        q_out["base_same" if base_pred[k] else "base_split"] += 1
        q_out["guard_same" if guard_pred[k] else "guard_split"] += 1
    return {"stats": dict(stats), "frozen": {k: dict(v) for k, v in frozen.items()},
            "tp_lost": tp_lost, "fp_cleared": fp_cleared, "queue": dict(q_out),
            "per_date": per_date}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    ap.add_argument("--lb-db", type=Path, default=LB_DB_PATH)
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--queue", type=Path, default=QUEUE_PATH)
    ap.add_argument("--density", type=float, default=0.5)
    ap.add_argument("--strong", default="primary")
    ap.add_argument("--json", type=Path, default=None, help="write full result here")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(args.config.read_text()) or {}
    gcfg = guard_cfg(cfg, args.density, [s for s in args.strong.split(",") if s])
    fz = json.loads(FROZEN_PATH.read_text())
    truth = {(min(a, b), max(a, b)): 1 for a, b, _ in fz["positives"]}
    truth.update({(min(a, b), max(a, b)): 0 for a, b, _ in fz["negatives"]})
    queue = []
    if args.queue.exists():
        queue = json.loads(args.queue.read_text())["queues"].get("chained", [])
    res = measure(args.db, cfg, gcfg, load_lineage(args.lb_db), truth, queue)

    log.info("density=%s strong=%s", args.density, args.strong)
    log.info("stats  %s", res["stats"])
    log.info("frozen %s", res["frozen"])
    log.info("queue  %s", res["queue"])
    log.info("tp_lost %d  fp_cleared %d", len(res["tp_lost"]), len(res["fp_cleared"]))
    for date in NAMED_DATES:
        d = res["per_date"].get(date)
        if d is None:
            log.info("  %s  not in corpus", date)
        elif d["status"] == "fidelity_mismatch":
            log.info("  %s  fidelity_mismatch", date)
        else:
            log.info("  %s  n=%d families stored %d / shipped %d / guard %d", date,
                     d["n_sources"], d["families_stored"], d["families_base"],
                     d["families_guard"])
    if args.json:
        args.json.write_text(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
