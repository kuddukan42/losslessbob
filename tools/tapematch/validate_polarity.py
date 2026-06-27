"""TODO-184 step 3 — validate channel-polarity rescue across the contradicted-
claim corpus before considering ``polarity.enabled: true`` the default.

For every concert date in observations.db where LB curator commentary asserts
a same-source pair (``lb_says_same=1``) but the latest tapematch run called it
``different_family``, this stages a non-destructive run with
``polarity.enabled: true`` and diffs the result against the existing
baseline. No DB write, no archive write, no mutation of the real
config.yaml — symlinks are staged into a scratch root and the package CLI is
invoked directly (bypassing tapematch_session.py's archiving entirely), the
same "staged symlinks, package CLI direct" pattern used for the original
1991-11-05 dry run.

Resumable: each date's result is appended to validate_polarity_results.jsonl
as soon as it's done, so a long batch can be interrupted and re-run without
redoing finished dates.

Usage:
    .venv/bin/python3 tools/tapematch/validate_polarity.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tapematch_session import (  # noqa: E402
    SESSION_DIR,
    VENV_PYTHON,
    find_lb_folders,
    query_db,
)

OBS_DB_PATH = SESSION_DIR / "observations.db"
SCRATCH_BASE = Path("/mnt/DATA0/tmp/validate_polarity")
RESULTS_PATH = SESSION_DIR / "validate_polarity_results.jsonl"

POLARITY_RESCUE_RE = re.compile(
    r"POLARITY_RESCUE\s+(\S+)/(\S+)\s+(\S+)\s+corr ([\d.]+)->([\d.]+)"
)


def contradicted_dates() -> list[str]:
    """Dates with an explicit curator same-source claim tapematch currently
    contradicts (lb_says_same=1 AND verdict=different_family in the latest
    run per pair)."""
    conn = sqlite3.connect(OBS_DB_PATH)
    cur = conn.execute(
        """SELECT DISTINCT concert_date FROM latest_pairs
           WHERE lb_says_same = 1 AND tapematch_verdict = 'different_family'
           ORDER BY concert_date"""
    )
    return [r[0] for r in cur.fetchall()]


def baseline_for_date(date_iso: str) -> dict[tuple[int, int], dict]:
    conn = sqlite3.connect(OBS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """SELECT lb_a, lb_b, corr, tapematch_verdict, lb_says_same
           FROM latest_pairs WHERE concert_date = ?""",
        (date_iso,),
    )
    return {(r["lb_a"], r["lb_b"]): dict(r) for r in cur.fetchall()}


def already_done() -> set[str]:
    if not RESULTS_PATH.exists():
        return set()
    done = set()
    for line in RESULTS_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            done.add(json.loads(line)["date"])
    return done


def stage_symlinks(found_folders: dict[int, Path], root: Path) -> dict[str, int]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    name_to_lb: dict[str, int] = {}
    for lb_num, src in found_folders.items():
        dest = root / src.name
        dest.symlink_to(src)
        name_to_lb[src.name] = lb_num
    return name_to_lb


def parse_polarity_rescues(debug_log_text: str) -> list[dict]:
    rescues = []
    for m in POLARITY_RESCUE_RE.finditer(debug_log_text):
        name_a, name_b, pairing, old_corr, new_corr = m.groups()
        rescues.append({
            "name_a": name_a, "name_b": name_b, "pairing": pairing,
            "old_corr": float(old_corr), "new_corr": float(new_corr),
        })
    return rescues


def run_one(date_iso: str) -> dict:
    location, lb_numbers = query_db(date_iso)
    if not lb_numbers:
        return {"date": date_iso, "status": "no_db_entries"}

    found_folders, excluded = find_lb_folders(lb_numbers, date_iso[:4])
    if len(found_folders) < 2:
        return {"date": date_iso, "status": "insufficient_sources",
                "n_found": len(found_folders), "n_db": len(lb_numbers)}

    scratch_root = SCRATCH_BASE / date_iso
    name_to_lb = stage_symlinks(found_folders, scratch_root)

    cfg = yaml.safe_load((SESSION_DIR / "config.yaml").read_text())
    cfg.setdefault("polarity", {})["enabled"] = True
    tmp_cfg_path = SCRATCH_BASE / f"{date_iso}.config.yaml"
    tmp_cfg_path.write_text(yaml.safe_dump(cfg))

    json_out = SCRATCH_BASE / f"{date_iso}.results.json"
    debug_log = SCRATCH_BASE / f"{date_iso}.debug.log"
    json_out.unlink(missing_ok=True)
    debug_log.unlink(missing_ok=True)

    cmd = [
        str(VENV_PYTHON), "-m", "tapematch.cli", str(scratch_root),
        "--config", str(tmp_cfg_path),
        "--json-out", str(json_out),
        "--debug-log", str(debug_log),
    ]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=str(SESSION_DIR), capture_output=True, text=True, timeout=1800,
        )
        rc, stdout_tail = proc.returncode, (proc.stdout + proc.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        rc, stdout_tail = -1, "[TIMEOUT after 1800s]"
    duration = time.monotonic() - t0

    debug_text = debug_log.read_text() if debug_log.exists() else ""
    shutil.rmtree(scratch_root, ignore_errors=True)
    tmp_cfg_path.unlink(missing_ok=True)
    debug_log.unlink(missing_ok=True)

    if rc != 0 or not json_out.exists():
        json_out.unlink(missing_ok=True)
        return {"date": date_iso, "status": "run_failed", "rc": rc,
                "duration": duration, "log_tail": stdout_tail}

    results = json.loads(json_out.read_text())
    json_out.unlink(missing_ok=True)

    names = results["correlation_matrix"]["names"]
    matrix = results["correlation_matrix"]["values"]
    srcs = results["sources"]
    name_idx = {n: i for i, n in enumerate(names)}
    lb_to_name = {v: k for k, v in name_to_lb.items()}
    rescues = parse_polarity_rescues(debug_text)
    rescued_pairs = {frozenset((r["name_a"], r["name_b"])) for r in rescues}

    baseline = baseline_for_date(date_iso)
    rescued, regressed, new_merges = [], [], []
    for (lb_a, lb_b), base in baseline.items():
        na, nb = lb_to_name.get(lb_a), lb_to_name.get(lb_b)
        if na not in name_idx or nb not in name_idx:
            continue
        i, j = name_idx[na], name_idx[nb]
        new_corr = matrix[i][j]
        new_same = srcs[na]["family_id"] == srcs[nb]["family_id"]
        was_same = base["tapematch_verdict"] == "same_family"
        row = {
            "lb_a": lb_a, "lb_b": lb_b, "lb_says_same": base["lb_says_same"],
            "old_corr": base["corr"], "new_corr": new_corr,
            "old_verdict": base["tapematch_verdict"],
            "new_verdict": "same_family" if new_same else "different_family",
            "polarity_rescue_fired": frozenset((na, nb)) in rescued_pairs,
        }
        if base["lb_says_same"] == 1 and not was_same and new_same:
            rescued.append(row)
        elif was_same and not new_same:
            regressed.append(row)
        elif base["lb_says_same"] == 0 and not was_same and new_same:
            new_merges.append(row)

    return {
        "date": date_iso, "status": "ok", "duration": duration,
        "n_sources": len(names), "n_pairs_checked": len(baseline),
        "rescued": rescued, "regressed": regressed, "new_merges": new_merges,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                     help="process at most N remaining dates this invocation")
    args = ap.parse_args(argv)

    SCRATCH_BASE.mkdir(parents=True, exist_ok=True)
    dates = contradicted_dates()
    done = already_done()
    todo = [d for d in dates if d not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(dates)} contradicted-claim dates total, {len(done)} already "
          f"done, processing {len(todo)} now", flush=True)

    with open(RESULTS_PATH, "a") as out:
        for n, date_iso in enumerate(todo, 1):
            print(f"[{n}/{len(todo)}] {date_iso} ...", flush=True)
            try:
                result = run_one(date_iso)
            except Exception as e:  # noqa: BLE001 -- keep the batch alive
                result = {"date": date_iso, "status": "error", "error": repr(e)}
            out.write(json.dumps(result) + "\n")
            out.flush()
            summary = result["status"]
            if result["status"] == "ok":
                summary += (f"  rescued={len(result['rescued'])} "
                            f"new_merges={len(result['new_merges'])} "
                            f"regressed={len(result['regressed'])}")
            print(f"  -> {summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
