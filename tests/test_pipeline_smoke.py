"""Pipeline smoke-test: randomly sample N collection folders, run all 4 steps.

Usage:
    .venv/bin/python3 tests/test_pipeline_smoke.py            # 100 random folders
    .venv/bin/python3 tests/test_pipeline_smoke.py --n 50     # 50 random folders
    .venv/bin/python3 tests/test_pipeline_smoke.py --seed 42  # reproducible run

Output:
    - Console progress + summary table
    - tests/pipeline_smoke_results.txt  — full per-folder detail
    - pipeline_smoke_bugs.md            — BUG entries ready to paste into BUGS.md
"""

import argparse
import random
import sqlite3
import sys
import traceback
from pathlib import Path

# ── Repo root on sys.path so backend imports work ─────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import checksum_utils  # noqa: E402
from backend import db as database  # noqa: E402
from backend.folder_naming import build_standard_name  # noqa: E402
from backend.paths import DB_PATH  # noqa: E402


def _find_lbdir_in_folder(folder: Path) -> "Path | None":
    if not folder.exists():
        return None
    for f in folder.iterdir():
        if f.is_file() and 'lbdir' in f.name.lower() and f.suffix.lower() == '.txt':
            return f
    return None


def run_pipeline(folder_path: str) -> dict:
    """Mirror of app.py _pipeline_process_folder with richer exception capture."""
    folder = Path(folder_path)
    folder_name = folder.name

    row = {
        "folder": folder_path,
        "folderName": folder_name,
        "verify":  {"status": "mute", "label": "—"},
        "lookup":  {"status": "mute", "label": "—", "lb_number": None},
        "rename":  {"status": "mute", "label": "—", "proposed": None},
        "lbdir":   {"status": "mute", "label": "—"},
        "severity": "attn",
        "errors": [],
        "exceptions": [],  # unhandled Python exceptions — not visible in prod
    }

    if not folder.exists() or not folder.is_dir():
        row["errors"].append({"step": "verify", "message": "Folder not found on disk"})
        row["verify"] = {"status": "bad", "label": "Missing"}
        row["severity"] = "attn"
        return row

    lb_number: int | None = None

    # ── Step 1: Verify ────────────────────────────────────────────────────────
    try:
        vr = checksum_utils.verify_folder(folder_path)
        if vr.get("error"):
            row["verify"] = {"status": "bad", "label": "Error"}
            row["errors"].append({"step": "verify", "message": vr["error"]})
        elif vr["status"] == "pass":
            row["verify"] = {"status": "ok", "label": "Pass"}
        elif vr["status"] in ("incomplete", "no_checksums"):
            row["verify"] = {"status": "warn", "label": "Incomplete"}
        else:
            row["verify"] = {"status": "bad", "label": "Mismatch"}
            row["errors"].append({"step": "verify", "message": f"status={vr['status']}"})
    except Exception:
        tb = traceback.format_exc()
        row["verify"] = {"status": "bad", "label": "Exception"}
        row["exceptions"].append({"step": "verify", "traceback": tb})

    # ── Step 2: Lookup ────────────────────────────────────────────────────────
    try:
        chk_parts: list[str] = []
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in (".ffp", ".md5", ".st5"):
                try:
                    chk_parts.append(f.read_text(errors="ignore"))
                except OSError as e:
                    row["errors"].append({"step": "lookup", "message": f"OSError reading {f.name}: {e}"})

        if not chk_parts:
            row["lookup"] = {"status": "warn", "label": "No checksums", "lb_number": None}
        else:
            chk_text = "\n".join(chk_parts)
            parsed = database.parse_checksum_text(chk_text)
            if not parsed:
                row["lookup"] = {"status": "bad", "label": "Not found", "lb_number": None}
                row["errors"].append({"step": "lookup",
                                      "message": "parse_checksum_text returned empty — checksum files unreadable or unknown format"})
            else:
                summary, _ = database.lookup_checksums(parsed)
                lb_list: list[int] = summary.get("lb_numbers_found", [])
                if len(lb_list) == 1:
                    lb_number = lb_list[0]
                    row["lookup"] = {"status": "ok", "label": f"LB-{lb_number:05d}", "lb_number": lb_number}
                elif len(lb_list) > 1:
                    row["lookup"] = {"status": "warn", "label": "Conflict", "lb_number": None}
                    row["errors"].append({"step": "lookup", "message": f"Multiple LBs: {lb_list}"})
                else:
                    row["lookup"] = {"status": "bad", "label": "Not found", "lb_number": None}
                    row["errors"].append({"step": "lookup",
                                          "message": f"Checksums parsed ({len(parsed)} entries) but no LB match"})
    except Exception:
        tb = traceback.format_exc()
        row["lookup"] = {"status": "bad", "label": "Exception"}
        row["exceptions"].append({"step": "lookup", "traceback": tb})

    # ── Step 3: Rename proposal ───────────────────────────────────────────────
    try:
        if lb_number:
            entry_data = database.get_entry(lb_number)
            entry = (entry_data or {}).get("entry", {})
            date_str = entry.get("date_str") or ""
            location = (entry.get("location") or "").strip()
            lb_status = database.get_lb_status(lb_number)
            proposed = build_standard_name(lb_number, date_str, location, lb_status)
            if folder_name == proposed:
                row["rename"] = {"status": "ok", "label": "Correct", "proposed": None}
            else:
                row["rename"] = {"status": "warn", "label": "Proposed",
                                  "proposed": proposed}
                row["errors"].append({"step": "rename",
                                       "message": f"Current: '{folder_name}' → Proposed: '{proposed}'"})
    except Exception:
        tb = traceback.format_exc()
        row["rename"] = {"status": "bad", "label": "Exception"}
        row["exceptions"].append({"step": "rename", "traceback": tb})

    # ── Step 4: LBDIR check ───────────────────────────────────────────────────
    try:
        if lb_number:
            lbdir_file = _find_lbdir_in_folder(folder)
            if lbdir_file:
                row["lbdir"] = {"status": "ok", "label": "Pass"}
            else:
                row["lbdir"] = {"status": "warn", "label": "No LBDIR"}
                row["errors"].append({"step": "lbdir",
                                       "message": "No lbdir*.txt found in folder"})
    except Exception:
        tb = traceback.format_exc()
        row["lbdir"] = {"status": "bad", "label": "Exception"}
        row["exceptions"].append({"step": "lbdir", "traceback": tb})

    # ── Severity ──────────────────────────────────────────────────────────────
    statuses = [row["verify"]["status"], row["lookup"]["status"],
                row["rename"]["status"], row["lbdir"]["status"]]
    if any(s == "bad" for s in statuses) or row["exceptions"]:
        row["severity"] = "attn"
    elif row["rename"].get("label") == "Proposed":
        row["severity"] = "ready"
    elif all(s in ("ok", "mute") for s in statuses) and "ok" in statuses:
        row["severity"] = "done"
    else:
        row["severity"] = "attn"

    return row


def _status_char(status: str) -> str:
    return {"ok": "✓", "warn": "~", "bad": "✗", "mute": "·"}.get(status, "?")


def load_collection_paths(n: int, seed: int) -> list[tuple[int, str]]:
    """Return up to n random (lb_number, disk_path) rows from my_collection."""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT lb_number, disk_path FROM my_collection ORDER BY lb_number").fetchall()
    conn.close()
    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))
    return sample


def classify_errors(rows: list[dict]) -> dict[str, list[dict]]:
    """Group rows into buckets by root problem type."""
    buckets: dict[str, list[dict]] = {
        "missing_folder": [],
        "exception": [],
        "verify_mismatch": [],
        "verify_error": [],
        "no_checksums": [],
        "lookup_not_found": [],
        "lookup_conflict": [],
        "rename_mismatch": [],
        "no_lbdir": [],
        "clean": [],
    }
    for row in rows:
        if row["exceptions"]:
            buckets["exception"].append(row)
            continue
        vl = row["verify"]["label"]
        ll = row["lookup"]["label"]
        missing = any(e["message"] == "Folder not found on disk" for e in row["errors"])
        if missing:
            buckets["missing_folder"].append(row)
        elif vl == "Mismatch":
            buckets["verify_mismatch"].append(row)
        elif vl == "Error":
            buckets["verify_error"].append(row)
        elif ll in ("No checksums",):
            buckets["no_checksums"].append(row)
        elif ll == "Not found":
            buckets["lookup_not_found"].append(row)
        elif ll == "Conflict":
            buckets["lookup_conflict"].append(row)
        elif row["severity"] == "done":
            buckets["clean"].append(row)
        else:
            if row["rename"]["label"] == "Proposed":
                buckets["rename_mismatch"].append(row)
            if row["lbdir"]["label"] == "No LBDIR":
                buckets["no_lbdir"].append(row)
            if row["rename"]["label"] != "Proposed" and row["lbdir"]["label"] != "No LBDIR":
                buckets["clean"].append(row)

    return buckets


def write_detail_report(rows: list[dict], path: Path) -> None:
    lines = []
    lines.append("=" * 80)
    lines.append("PIPELINE SMOKE TEST — FULL DETAIL REPORT")
    lines.append(f"Tested {len(rows)} folders")
    lines.append("=" * 80)
    for row in rows:
        v = _status_char(row["verify"]["status"])
        lk = _status_char(row["lookup"]["status"])
        r = _status_char(row["rename"]["status"])
        d = _status_char(row["lbdir"]["status"])
        lines.append(f"\n[V:{v} L:{lk} R:{r} D:{d}] {row['folderName']}")
        lines.append(f"  Path  : {row['folder']}")
        for err in row["errors"]:
            lines.append(f"  ERROR [{err['step']}]: {err['message']}")
        for exc in row["exceptions"]:
            lines.append(f"  EXCEPTION [{exc['step']}]:")
            for tb_line in exc["traceback"].splitlines():
                lines.append(f"    {tb_line}")
    path.write_text("\n".join(lines))


def write_bugs_report(buckets: dict[str, list[dict]], path: Path, start_bug: int) -> None:
    lines = []
    bug_n = start_bug

    def section(title: str, items: list[dict], step: str, desc_fn):
        nonlocal bug_n
        if not items:
            return
        lines.append(f"BUG-{bug_n:03d}: Pipeline smoke — {title} ({len(items)} folders)")
        lines.append("Status: Open")
        lines.append("File(s): backend/app.py:4547, backend/checksum_utils.py:439")
        lines.append("Reported: 2026-05-31")
        lines.append("Root cause: (TBD — see samples below)")
        lines.append("Fix: (TBD)")
        lines.append("Samples:")
        for row in items[:10]:
            lines.append(f"  • {desc_fn(row)}")
        if len(items) > 10:
            lines.append(f"  … and {len(items) - 10} more (see pipeline_smoke_results.txt)")
        lines.append("")
        bug_n += 1

    section(
        "Missing folders (DB has record but disk path gone)",
        buckets["missing_folder"], "verify",
        lambda r: r["folder"]
    )
    section(
        "Python exceptions during pipeline",
        buckets["exception"], "mixed",
        lambda r: f"{r['folder']} — {r['exceptions'][0]['step']}: {r['exceptions'][0]['traceback'].splitlines()[-1]}"
    )
    section(
        "Checksum verify mismatch (audio files differ from .ffp/.md5/.st5)",
        buckets["verify_mismatch"], "verify",
        lambda r: r["folder"]
    )
    section(
        "Verify error (unreadable or corrupt checksum file)",
        buckets["verify_error"], "verify",
        lambda r: f"{r['folder']} — {next((e['message'] for e in r['errors'] if e['step']=='verify'), '')}"
    )
    section(
        "No checksum files found (.ffp/.md5/.st5 absent)",
        buckets["no_checksums"], "lookup",
        lambda r: r["folder"]
    )
    section(
        "Lookup not found (checksums parsed but no LB match)",
        buckets["lookup_not_found"], "lookup",
        lambda r: r["folder"]
    )
    section(
        "Lookup conflict (multiple LB matches)",
        buckets["lookup_conflict"], "lookup",
        lambda r: f"{r['folder']} — {next((e['message'] for e in r['errors'] if e['step']=='lookup'), '')}"
    )
    section(
        "Rename mismatch (folder name doesn't match LB standard)",
        buckets["rename_mismatch"], "rename",
        lambda r: f"{r['folder']} → {r['rename'].get('proposed','?')}"
    )
    section(
        "No LBDIR file found in folder",
        buckets["no_lbdir"], "lbdir",
        lambda r: r["folder"]
    )

    path.write_text("\n".join(lines) if lines else "No bugs found — all folders passed.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline smoke test over random collection folders")
    parser.add_argument("--n",    type=int, default=100, help="Number of folders to test")
    parser.add_argument("--seed", type=int, default=1,   help="Random seed for reproducibility")
    parser.add_argument("--bugs-start", type=int, default=200,
                        help="Starting BUG number for generated BUGS entries")
    args = parser.parse_args()

    print(f"Loading {args.n} random folders (seed={args.seed}) from my_collection …")
    sample = load_collection_paths(args.n, args.seed)
    print(f"  → Got {len(sample)} folders\n")

    results: list[dict] = []
    width = len(str(len(sample)))
    for i, (lb_number, disk_path) in enumerate(sample, 1):
        row = run_pipeline(disk_path)
        v = _status_char(row["verify"]["status"])
        lk = _status_char(row["lookup"]["status"])
        r = _status_char(row["rename"]["status"])
        d = _status_char(row["lbdir"]["status"])
        exc_flag = " [EXC]" if row["exceptions"] else ""
        print(f"  [{i:>{width}}/{len(sample)}] V:{v} L:{lk} R:{r} D:{d}{exc_flag}  {row['folderName'][:70]}")
        results.append(row)

    buckets = classify_errors(results)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(results)
    clean = len(buckets["clean"])
    print(f"  Clean (all ok/mute+ok):   {clean:>4} / {total}")
    print(f"  Missing folders:          {len(buckets['missing_folder']):>4}")
    print(f"  Exceptions:               {len(buckets['exception']):>4}")
    print(f"  Verify mismatch:          {len(buckets['verify_mismatch']):>4}")
    print(f"  Verify error:             {len(buckets['verify_error']):>4}")
    print(f"  No checksums:             {len(buckets['no_checksums']):>4}")
    print(f"  Lookup not found:         {len(buckets['lookup_not_found']):>4}")
    print(f"  Lookup conflict:          {len(buckets['lookup_conflict']):>4}")
    print(f"  Rename mismatch:          {len(buckets['rename_mismatch']):>4}")
    print(f"  No LBDIR:                 {len(buckets['no_lbdir']):>4}")

    out_dir = Path(__file__).parent
    detail_path = out_dir / "pipeline_smoke_results.txt"
    bugs_path   = out_dir / "pipeline_smoke_bugs.md"

    write_detail_report(results, detail_path)
    write_bugs_report(buckets, bugs_path, args.bugs_start)

    print(f"\nDetail report → {detail_path}")
    print(f"Bug report    → {bugs_path}")


if __name__ == "__main__":
    main()
