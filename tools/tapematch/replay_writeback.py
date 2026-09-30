#!/usr/bin/env python3
"""TODO-333 follow-up — write threshold-only re-decisions back as new runs.

``calibration_eras.replay_changes`` shows which dates would re-decide under the
shipped ``config.yaml`` when their calibration differs from it *only* in
:data:`tapematch.calibration.VERDICT_ONLY_KEYS`. For those dates the stored pair
metrics are exact, so the new verdict can be written without touching audio.
This tool does that: per date it copies the run that
``backend.tapematch_sync._pick_best_run`` would sync into a new *replay run*
(``runs.replayed_from`` = the source run) carrying the shipped config, its
calibration hash, re-decided ``pairs.tapematch_verdict`` and re-clustered
``family_id`` values. The next ``python -m backend.tapematch_sync`` picks it up.

Fidelity gate: before writing, ``verdict.cluster_verdicts`` under the source
run's own ``config_json`` must reproduce every stored pair verdict AND the
stored ``sources.family_id`` partition. A date that fails is skipped
(``fidelity_mismatch``) — the offline verdict model does not explain what the
live session decided there, so re-deciding it offline would not be a replay.

Replay run_id: ``<source run_id>-r<calibration hash>``. It sorts immediately
after the source (a longer string sharing the source as a prefix) and before any
later real run (real ids are ``YYYYMMDD_HHMMSS``; any later second differs in a
digit before the suffix), so it wins ``_pick_best_run``'s ``(n_sources_ran,
run_id)`` tie-break exactly where the source did. Keeping the source's
timestamp prefix also keeps ``backend.ab_clips.is_run_eligible`` (a string
compare against ``YYYYMMDD_HHMMSS``) answering for the *source's* speed labels,
which are copied verbatim. ``-`` rather than ``_`` keeps the three-part
``<run_id>_<date>`` directory-name splitters working if a dir is ever named
after it. The id is deterministic per (source, calibration), so a re-apply
cannot collide or duplicate.

Usage:
    .venv/bin/python3 tools/tapematch/replay_writeback.py [--apply] [--db PATH]
        [--lb-db PATH] [--dates D1,D2] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

SESSION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSION_DIR.parents[1]
for _p in (str(SESSION_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibration_eras import diff_keys  # noqa: E402
from tapematch import verdict as V  # noqa: E402
from tapematch.calibration import (  # noqa: E402
    VERDICT_ONLY_KEYS,
    calibration_hash,
    calibration_view,
)

OBS_DB_PATH = SESSION_DIR / "observations.db"
CONFIG_PATH = SESSION_DIR / "config.yaml"
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
RUNS_DIR = PROJECT_ROOT / "data" / "tapematch" / "runs"
LOG_DIR = PROJECT_ROOT / "data" / "tapematch"

log = logging.getLogger("replay_writeback")

Partition = set[frozenset[int]]


@dataclass
class DateResult:
    """Outcome for one concert date."""

    concert_date: str
    source_run: str
    status: str                      # written | skipped
    reason: str = ""
    pairs_changed: int = 0
    families_before: int = 0
    families_after: int = 0
    new_run_id: str = ""
    detail: list[str] = field(default_factory=list)


def ensure_replayed_from(conn: sqlite3.Connection) -> None:
    """Idempotently add ``runs.replayed_from``."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "replayed_from" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN replayed_from TEXT")


def replay_run_id(source_run_id: str, cal_hash: str) -> str:
    """Deterministic replay id; see module docstring for the ordering argument."""
    return f"{source_run_id}-r{cal_hash}"


def pick_best_runs(conn: sqlite3.Connection) -> dict[str, str]:
    """``{concert_date: run_id}`` exactly as the app sync chooses it."""
    from backend.tapematch_sync import _pick_best_run
    return _pick_best_run(conn)


def stored_partition(sources: list[dict[str, Any]]) -> Partition:
    """Set-of-frozensets of lb_numbers grouped by stored ``family_id``."""
    groups: dict[Any, set[int]] = {}
    for s in sources:
        groups.setdefault(s["family_id"], set()).add(s["lb_number"])
    return {frozenset(g) for g in groups.values()}


def verdict_partition(pairs: list[dict[str, Any]], verdicts: dict[tuple, str],
                      lbs: set[int]) -> Partition:
    """Components implied by SAME_FAMILY pair verdicts; unpaired lbs are singletons."""
    parent = {lb: lb for lb in lbs}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), v in verdicts.items():
        if v == V.SAME_FAMILY:
            parent[find(a)] = find(b)
    comps: dict[int, set[int]] = {}
    for lb in lbs:
        comps.setdefault(find(lb), set()).add(lb)
    return {frozenset(c) for c in comps.values()}


def assign_family_ids(old: dict[int, int], new_part: Partition) -> dict[int, int]:
    """Map lb -> family_id, keeping an old id wherever membership is unchanged.

    Args:
        old: Stored ``{lb_number: family_id}``.
        new_part: Replayed partition.

    Returns:
        ``{lb_number: family_id}``. Changed families get ``max(old ids)+1, ...``
        in ascending order of their lowest lb_number.
    """
    old_groups: dict[frozenset[int], int] = {}
    by_fam: dict[int, set[int]] = {}
    for lb, fam in old.items():
        by_fam.setdefault(fam, set()).add(lb)
    for fam, members in by_fam.items():
        old_groups[frozenset(members)] = fam
    next_id = max(old.values(), default=0) + 1
    out: dict[int, int] = {}
    for comp in sorted(new_part, key=min):
        fam = old_groups.get(comp)
        if fam is None:
            fam = next_id
            next_id += 1
        for lb in comp:
            out[lb] = fam
    return out


def _rows(conn: sqlite3.Connection, sql: str, args: tuple) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _resolve_archive_dir(src: dict[str, Any]) -> str | None:
    """Source's archive dir, repaired to the post-relocation path when stale.

    ``tapematch_sync._resolve_run_dir`` falls back to ``<run_id>_<date>`` when
    the stored path is missing; under the replay id that fallback would miss the
    source's analysis.md, so the fallback is resolved here against the SOURCE id.
    """
    stored = src.get("archive_dir")
    if stored and Path(stored).exists():
        return stored
    fallback = RUNS_DIR / f"{src['run_id']}_{src['concert_date']}"
    if fallback.exists():
        return str(fallback)
    return stored


def process_date(conn: sqlite3.Connection, concert_date: str, run_id: str,
                 cfg: dict[str, Any], cfg_json: str, cur_hash: str,
                 cur_view: dict[str, Any], lineage: set[tuple[int, int]],
                 now_iso: str) -> DateResult:
    """Evaluate and (inside the caller's transaction) write one date."""
    src = dict(conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone())
    res = DateResult(concert_date, run_id, "skipped")
    try:
        era_cfg = json.loads(src["config_json"]) if src["config_json"] else None
    except json.JSONDecodeError:
        era_cfg = None
    if not era_cfg:
        res.reason = "no_config"
        return res
    diffs = diff_keys(cur_view, calibration_view(era_cfg))
    if not diffs:
        res.reason = "current_calibration"
        return res
    if any(k not in VERDICT_ONLY_KEYS for k in diffs):
        res.reason = "signal_keys_differ"
        return res
    new_id = replay_run_id(run_id, cur_hash)
    if conn.execute(
        "SELECT 1 FROM runs WHERE run_id = ? OR (replayed_from = ? AND calibration_hash = ?)",
        (new_id, run_id, cur_hash),
    ).fetchone():
        res.reason = "already_replayed"
        return res

    sources = _rows(conn, "SELECT * FROM sources WHERE run_id = ? ORDER BY id", (run_id,))
    pairs = _rows(conn, "SELECT * FROM pairs WHERE run_id = ? ORDER BY id", (run_id,))
    if not pairs:
        res.reason = "no_pairs"
        return res
    if any(s["lb_number"] is None for s in sources) or any(
            p["lb_a"] is None or p["lb_b"] is None for p in pairs):
        res.reason = "null_lb"
        return res

    old_fam = {s["lb_number"]: s["family_id"] for s in sources}
    lbs = set(old_fam) | {p["lb_a"] for p in pairs} | {p["lb_b"] for p in pairs}
    before = V.cluster_verdicts(pairs, era_cfg, lineage)
    bad_pairs = sum(
        1 for p in pairs
        if before[(min(p["lb_a"], p["lb_b"]), max(p["lb_a"], p["lb_b"]))]
        != p["tapematch_verdict"])
    part_before = stored_partition(sources)
    part_model = verdict_partition(pairs, before, lbs)
    if bad_pairs or part_model != part_before:
        res.reason = "fidelity_mismatch"
        res.detail.append(f"{bad_pairs} pair verdict(s) not reproduced"
                          + ("" if part_model == part_before else "; partition differs"))
        return res

    after = V.cluster_verdicts(pairs, cfg, lineage)
    res.pairs_changed = sum(1 for k in before if before[k] != after.get(k))
    if not res.pairs_changed:
        res.reason = "no_change"
        return res
    part_after = verdict_partition(pairs, after, lbs)
    new_fam = assign_family_ids(old_fam, part_after)
    res.families_before = len(part_before)
    res.families_after = len(part_after)
    res.new_run_id = new_id
    for comp in sorted(part_after - part_before, key=min):
        res.detail.append("new family {" + ", ".join(f"LB-{lb:05d}" for lb in sorted(comp))
                          + "}")

    # ── write ────────────────────────────────────────────────────────────────
    run_row = dict(src)
    run_row.update(run_id=new_id, config_json=cfg_json, calibration_hash=cur_hash,
                   run_at=now_iso, archive_dir=_resolve_archive_dir(src),
                   n_families=len(set(new_fam.values())), duration_sec=None,
                   replayed_from=run_id)
    cols = list(run_row)
    conn.execute(f"INSERT INTO runs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                 [run_row[c] for c in cols])
    for s in sources:
        s = dict(s)
        s.pop("id")
        s.update(run_id=new_id, family_id=new_fam[s["lb_number"]])
        cols = list(s)
        conn.execute(
            f"INSERT INTO sources ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [s[c] for c in cols])
    for p in pairs:
        p = dict(p)
        p.pop("id")
        key = (min(p["lb_a"], p["lb_b"]), max(p["lb_a"], p["lb_b"]))
        p.update(run_id=new_id, run_at=now_iso, tapematch_verdict=after[key],
                 family_id_a=new_fam[p["lb_a"]], family_id_b=new_fam[p["lb_b"]])
        cols = list(p)
        conn.execute(
            f"INSERT INTO pairs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [p[c] for c in cols])
    res.status = "written"
    return res


def run(db_path: Path, lb_db_path: Path, config_path: Path, apply: bool,
        dates: set[str] | None = None, limit: int | None = None) -> list[DateResult]:
    """Replay every eligible date; commit only when ``apply``.

    Args:
        db_path: observations.db to read and (with ``apply``) write.
        lb_db_path: LosslessBob DB for curator lineage pairs.
        config_path: Shipped config.yaml.
        apply: Commit each date's transaction; otherwise roll back.
        dates: Restrict to these concert dates.
        limit: Stop after this many dates are written (or would be).

    Returns:
        One :class:`DateResult` per date considered.
    """
    cfg = yaml.safe_load(config_path.read_text()) or {}
    cfg_json = json.dumps(cfg)
    cur_hash, cur_view = calibration_hash(cfg), calibration_view(cfg)
    lineage = V.load_lineage_pairs(lb_db_path) if lb_db_path.exists() else set()
    now_iso = datetime.now().isoformat()

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    results: list[DateResult] = []
    try:
        if apply:
            conn.execute("BEGIN IMMEDIATE")
            ensure_replayed_from(conn)
            conn.execute("COMMIT")
        # A dry-run adds the column inside each rolled-back date transaction
        # below instead, so the idempotency query parses without persisting it.
        best = pick_best_runs(conn)
        n_written = 0
        for concert_date in sorted(best):
            if dates and concert_date not in dates:
                continue
            if limit is not None and n_written >= limit:
                break
            conn.execute("BEGIN IMMEDIATE")
            try:
                ensure_replayed_from(conn)
                r = process_date(conn, concert_date, best[concert_date], cfg, cfg_json,
                                 cur_hash, cur_view, lineage, now_iso)
                conn.execute("COMMIT" if (apply and r.status == "written") else "ROLLBACK")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            results.append(r)
            if r.status == "written":
                n_written += 1
    finally:
        conn.close()
    return results


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    ap.add_argument("--lb-db", type=Path, default=LB_DB_PATH,
                    help="LosslessBob DB for curator lineage (read-only)")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--dates", help="comma-separated concert dates")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--log", type=Path,
                    default=LOG_DIR / f"replay_writeback_{datetime.now():%Y%m%d_%H%M%S}.log")
    args = ap.parse_args(argv)

    args.log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(args.log)])
    dates = {d.strip() for d in args.dates.split(",")} if args.dates else None
    mode = "APPLY" if args.apply else "DRY-RUN"
    log.info("%s db=%s", mode, args.db)
    results = run(args.db, args.lb_db, args.config, args.apply, dates, args.limit)

    skips: dict[str, int] = {}
    for r in results:
        if r.status == "written":
            log.info("%s  %s -> %s  pairs changed %d  families %d -> %d  %s",
                     r.concert_date, r.source_run, r.new_run_id, r.pairs_changed,
                     r.families_before, r.families_after, "; ".join(r.detail))
        else:
            skips[r.reason] = skips.get(r.reason, 0) + 1
            if r.reason == "fidelity_mismatch" or (dates and r.reason != "current_calibration"):
                log.info("%s  %s  skipped: %s %s", r.concert_date, r.source_run, r.reason,
                         "; ".join(r.detail))
    written = [r for r in results if r.status == "written"]
    log.info("%s: %d date(s) %s, %d pair verdicts changed, families %d -> %d; skipped %s; "
             "log %s", mode, len(written), "written" if args.apply else "would be written",
             sum(r.pairs_changed for r in written), sum(r.families_before for r in written),
             sum(r.families_after for r in written),
             ", ".join(f"{k}={v}" for k, v in sorted(skips.items())) or "none", args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
