#!/usr/bin/env python3
"""TODO-333 — which calibration produced each shipped family verdict.

``recording_families`` in the app DB is a patchwork: every date carries
whatever the pipeline believed on the day it happened to be run, and until
``runs.calibration_hash`` existed nothing recorded which. This script fills that
column in for historical runs (``--backfill``) and reports the result as a
staleness table — how many dates sit on each calibration era, and how far each
era is from the shipped ``config.yaml``.

Why not hash ``config_json`` directly: it splits runs that are behaviourally
identical. Over the 3,062 latest runs the raw blob takes 18 distinct values but
only nine keys ever changed VALUE; the rest of the spread is keys that did not
exist yet in an older config. ``tapematch.calibration`` normalises that away
(absent = default, a disabled block = its off switch alone), which collapses the
18 to 11 real eras. See that module for the full contract.

What the report does NOT claim: that a stale date's verdict is wrong, or that a
current-era date's verdict is right. It says only which configuration produced
each verdict, so a re-run queue can be prioritised by expected verdict change
instead of by age. Two confounds are printed alongside for that reason: the
per-era flip history (pairs whose verdict has actually moved between runs are
the ones most likely to move again) and the incomplete-set count (a date run on
fewer sources than the catalogue lists is provisional regardless of config, and
re-running it under a current config will not make it correct).

Usage:
    .venv/bin/python3 tools/tapematch/calibration_eras.py [--backfill] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

SESSION_DIR = Path(__file__).resolve().parent
if str(SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR))

from tapematch import verdict as V  # noqa: E402
from tapematch.calibration import (  # noqa: E402
    VERDICT_ONLY_KEYS,
    calibration_hash,
    calibration_view,
)

PROJECT_ROOT = SESSION_DIR.parents[1]
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"

OBS_DB_PATH = SESSION_DIR / "observations.db"
CONFIG_PATH = SESSION_DIR / "config.yaml"
DEFAULT_OUT = SESSION_DIR / "CALIBRATION_ERAS.md"

log = logging.getLogger("calibration_eras")


def backfill(conn: sqlite3.Connection, rehash: bool = False) -> tuple[int, int]:
    """Compute and store ``calibration_hash`` for runs that lack one.

    Args:
        conn: Open observations.db connection.
        rehash: Recompute every run rather than only the NULLs. Required
            whenever ``calibration.DECISION_KEYS`` changes, since that changes
            what every hash means — a mixed table would compare hashes computed
            under two different key sets.

    Returns:
        ``(written, skipped)`` — skipped counts runs with no usable config_json.
    """
    where = "" if rehash else " WHERE calibration_hash IS NULL"
    rows = conn.execute(f"SELECT run_id, config_json FROM runs{where}").fetchall()
    written = skipped = 0
    for run_id, cfg_json in rows:
        try:
            cfg = json.loads(cfg_json) if cfg_json else None
        except json.JSONDecodeError:
            cfg = None
        if not cfg:
            skipped += 1
            continue
        conn.execute("UPDATE runs SET calibration_hash = ? WHERE run_id = ?",
                     (calibration_hash(cfg), run_id))
        written += 1
    conn.commit()
    return written, skipped


def latest_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """The most recent run per concert date."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """SELECT r.* FROM runs r
           JOIN (SELECT concert_date, MAX(run_at) AS m FROM runs GROUP BY concert_date) x
             ON r.concert_date = x.concert_date AND r.run_at = x.m"""
    )
    return [dict(r) for r in cur.fetchall()]


def flip_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Per concert date, how many pairs have ever changed verdict between runs.

    A pair observed more than once whose ``tapematch_verdict`` is not constant
    is a pair the calibration has already moved. Dates carrying such pairs are
    the ones whose verdicts are most likely to move again.
    """
    cur = conn.execute(
        """SELECT concert_date, COUNT(*) FROM (
               SELECT concert_date, lb_a, lb_b
               FROM pairs
               GROUP BY concert_date, lb_a, lb_b
               HAVING COUNT(*) > 1 AND COUNT(DISTINCT tapematch_verdict) > 1
           ) GROUP BY concert_date"""
    )
    return {date: n for date, n in cur.fetchall()}


def replay_changes(conn: sqlite3.Connection, runs: list[dict[str, Any]],
                   cfg: dict[str, Any], views: dict[str, dict[str, Any]],
                   cur_view: dict[str, Any],
                   lineage: set[tuple[int, int]]) -> dict[str, int]:
    """Count, per date, the pairs whose verdict moves under the current config.

    Only dates whose calibration differs from the current one *purely* in
    :data:`~tapematch.calibration.VERDICT_ONLY_KEYS` are replayable: their pair
    metrics were produced by the same signal chain, so re-deciding the stored
    rows under today's thresholds is exact. A date whose era also differs on a
    signal-generation key cannot be answered this way at all — its metrics would
    themselves come out differently — and is omitted rather than guessed at.

    Args:
        conn: Open observations.db connection.
        runs: Latest run per date.
        cfg: The shipped config.
        views: Calibration view per era hash.
        cur_view: Calibration view of the shipped config.
        lineage: Curator lineage pairs, for the curator-relaxed fp bar.

    Returns:
        ``{concert_date: n_pairs_changed}`` for replayable dates only. A date
        that replays to an identical verdict set maps to 0.
    """
    out: dict[str, int] = {}
    conn.row_factory = sqlite3.Row
    for r in runs:
        h = r["calibration_hash"]
        if not h or h not in views:
            continue
        diffs = diff_keys(cur_view, views[h])
        if not diffs or any(k not in VERDICT_ONLY_KEYS for k in diffs):
            continue
        pairs = [dict(x) for x in conn.execute(
            "SELECT * FROM pairs WHERE run_id = ?", (r["run_id"],)).fetchall()]
        if not pairs:
            continue
        era_cfg = json.loads(r["config_json"])
        before = V.cluster_verdicts(pairs, era_cfg, lineage)
        after = V.cluster_verdicts(pairs, cfg, lineage)
        out[r["concert_date"]] = sum(1 for k in before if before[k] != after.get(k))
    return out


def diff_keys(current: dict[str, Any], other: dict[str, Any]) -> list[str]:
    """Decision keys where two calibration views disagree."""
    keys = sorted(set(current) | set(other))
    return [k for k in keys if current.get(k, "<absent>") != other.get(k, "<absent>")]


def build_report(runs: list[dict[str, Any]], cur_hash: str, cur_view: dict[str, Any],
                 views: dict[str, dict[str, Any]], flips: dict[str, int],
                 replay: dict[str, int]) -> str:
    """Render the staleness report."""
    total = len(runs)
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_hash[r["calibration_hash"] or "(unhashed)"].append(r)

    out: list[str] = []
    out.append("# Calibration eras of the shipped family verdicts (TODO-333)\n")
    out.append(
        f"Latest run per date: **{total} dates**. Shipped `config.yaml` hashes to "
        f"**`{cur_hash}`**, which covers **{len(by_hash.get(cur_hash, []))} dates "
        f"({100.0 * len(by_hash.get(cur_hash, [])) / total:.1f}%)**; the rest were "
        "computed under an earlier calibration.\n"
    )
    out.append(
        "Regenerate with `.venv/bin/python3 tools/tapematch/calibration_eras.py`. "
        "Staleness is a provenance fact, not a verdict on correctness — see the "
        "module docstring before using this to schedule re-runs.\n"
    )

    out.append("\n## Eras, newest activity first\n")
    out.append("| Calibration | Dates | Share | Last run | Months | Flipped pairs | "
               "Δ keys vs current | Replayable |")
    out.append("|---|---:|---:|---|---|---:|---:|---|")
    ordered = sorted(by_hash.items(), key=lambda kv: max(r["run_at"] or "" for r in kv[1]),
                     reverse=True)
    for h, rs in ordered:
        months = sorted({(r["run_at"] or "")[:7] for r in rs})
        last = max(r["run_at"] or "" for r in rs)[:10]
        flipped = sum(flips.get(r["concert_date"], 0) for r in rs)
        nd = "—" if h == cur_hash else (
            str(len(diff_keys(cur_view, views[h]))) if h in views else "?")
        mark = " **(current)**" if h == cur_hash else ""
        if h == cur_hash:
            replayable = "—"
        elif h in views and all(k in VERDICT_ONLY_KEYS for k in diff_keys(cur_view, views[h])):
            moved = sum(1 for r in rs if replay.get(r["concert_date"], 0) > 0)
            replayable = f"yes — {moved} date(s) move"
        else:
            replayable = "no (signal keys differ)"
        out.append(f"| `{h}`{mark} | {len(rs)} | {100.0 * len(rs) / total:.1f}% | {last} | "
                   f"{', '.join(months)} | {flipped} | {nd} | {replayable} |")

    out.append("\n## What each era differs on\n")
    out.append(
        "Only keys whose VALUE differs from the shipped config are listed — a key "
        "absent from an older config but equal to today's default is not a "
        "difference and does not appear.\n"
    )
    for h, rs in ordered:
        if h == cur_hash or h not in views:
            continue
        keys = diff_keys(cur_view, views[h])
        out.append(f"\n### `{h}` — {len(rs)} dates\n")
        out.append("| Key | This era | Current |")
        out.append("|---|---|---|")
        for k in keys:
            out.append(f"| `{k}` | `{views[h].get(k, '(absent)')}` | "
                       f"`{cur_view.get(k, '(absent)')}` |")

    moved = {d: n for d, n in replay.items() if n}
    out.append("\n## Replay: dates whose verdict actually moves under the current config\n")
    out.append(
        f"{len(replay)} stale dates differ from the shipped config ONLY in threshold "
        "keys, so their stored pair metrics can be re-decided exactly without "
        f"touching audio. Of those, **{len(moved)} change verdict** and "
        f"{len(replay) - len(moved)} are identical — i.e. most of the staleness in "
        "those eras is bookkeeping, not disagreement. A re-run for a date in the "
        "identical set buys a fresher `calibration_hash` and nothing else.\n"
    )
    if moved:
        out.append("| Date | Calibration | Pairs that move | Flipped before | Sources ran / catalogued |")
        out.append("|---|---|---:|---:|---|")
        by_date = {r["concert_date"]: r for r in runs}
        for d, n in sorted(moved.items(), key=lambda kv: (-kv[1], kv[0])):
            r = by_date[d]
            incomplete = (r["n_sources_ran"] or 0) < (r["n_sources_db"] or 0)
            counts = f"{r['n_sources_ran']}/{r['n_sources_db']}" + (" ⚠" if incomplete else "")
            out.append(f"| {d} | `{r['calibration_hash']}` | {n} | "
                       f"{flips.get(d, 0)} | {counts} |")
    else:
        out.append("_No replayable date changes verdict._\n")

    out.append("\n## Re-run priority (highest expected change first)\n")
    out.append(
        "Dates on a non-current calibration, ordered by how many of their pairs "
        "have already flipped verdict between runs. A date with flips has "
        "demonstrated that its verdicts turn on the config; a date with none may "
        "well be stable across the difference. Incomplete-set dates are marked: "
        "re-running one under a current config does not make it correct, because "
        "it is still missing sources.\n"
    )
    stale = [r for r in runs if r["calibration_hash"] != cur_hash]
    stale.sort(key=lambda r: (-flips.get(r["concert_date"], 0), r["concert_date"]))
    out.append("| Date | Calibration | Flipped pairs | Sources ran / catalogued | Last run |")
    out.append("|---|---|---:|---|---|")
    for r in stale[:60]:
        incomplete = (r["n_sources_ran"] or 0) < (r["n_sources_db"] or 0)
        counts = f"{r['n_sources_ran']}/{r['n_sources_db']}" + (" ⚠ incomplete" if incomplete else "")
        out.append(f"| {r['concert_date']} | `{r['calibration_hash']}` | "
                   f"{flips.get(r['concert_date'], 0)} | {counts} | {(r['run_at'] or '')[:10]} |")
    out.append(f"\n_{len(stale)} stale dates in total; the {len(stale) - 60} beyond the top 60 "
               "carry no recorded flips._\n" if len(stale) > 60 else "")

    n_incomplete = sum(1 for r in stale if (r["n_sources_ran"] or 0) < (r["n_sources_db"] or 0))
    out.append(f"\nOf the {len(stale)} stale dates, {n_incomplete} also ran on an incomplete "
               "set (TODO-334), so their family counts are provisional for a second, "
               "independent reason.\n")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill", action="store_true",
                    help="compute calibration_hash for runs that lack one, then report")
    ap.add_argument("--rehash", action="store_true",
                    help="recompute EVERY run's calibration_hash (use after "
                         "calibration.DECISION_KEYS changes), then report")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = sqlite3.connect(args.db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "calibration_hash" not in cols:
        log.error("runs.calibration_hash missing — open the DB once through "
                  "tapematch_session.open_obs_db() to apply the migration")
        return 1

    if args.backfill or args.rehash:
        written, skipped = backfill(conn, rehash=args.rehash)
        log.info("backfill: %d run(s) hashed, %d skipped (no config_json)", written, skipped)

    cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    cur_hash, cur_view = calibration_hash(cfg), calibration_view(cfg)

    runs = latest_runs(conn)
    views: dict[str, dict[str, Any]] = {}
    for r in runs:
        h = r["calibration_hash"]
        if h and h not in views and r["config_json"]:
            views[h] = calibration_view(json.loads(r["config_json"]))
    flips = flip_counts(conn)
    lineage = V.load_lineage_pairs(LB_DB_PATH) if LB_DB_PATH.exists() else set()
    replay = replay_changes(conn, runs, cfg, views, cur_view, lineage)
    conn.close()

    args.out.write_text(build_report(runs, cur_hash, cur_view, views, flips, replay))
    log.info("replayable stale dates: %d, of which %d change verdict",
             len(replay), sum(1 for n in replay.values() if n))
    log.info("report -> %s", args.out)
    counts = Counter(r["calibration_hash"] for r in runs)
    log.info("current calibration %s covers %d/%d dates", cur_hash,
             counts.get(cur_hash, 0), len(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
