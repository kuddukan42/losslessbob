#!/usr/bin/env python3
"""One-shot background runner: re-fetch the 85 LB entries that didn't
download on the first WTRF batch pass, then write a markdown report.

Launched detached (nohup/setsid) from an interactive session that is
expected to end before this finishes. Not part of the normal toolset —
delete after the report has been reviewed.
"""
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path("/home/tjenkins/Documents/losslessbob")
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
LOG_PATH = PROJECT_ROOT / "wtrf_batch_85_run.log"
REPORT_PATH = PROJECT_ROOT / "wtrf_batch_85_report.md"

LB_NUMBERS = [
    16064, 16096, 16098, 16101, 16107, 16125, 16147, 16156, 16191, 16219,
    16226, 16253, 16260, 16268, 16278, 16289, 16308, 16310, 16340, 16362,
    16369, 16389, 16392, 16393, 16404, 16405, 16406, 16420, 16426, 16427,
    16434, 16439, 16440, 16453, 16456, 16458, 16459, 16463, 16464, 16465,
    16473, 16476, 16477, 16480, 16489, 16492, 16511, 16512, 16513, 16514,
    16516, 16518, 16519, 16520, 16521, 16524, 16528, 16532, 16533, 16535,
    16547, 16548, 16551, 16565, 16566, 16567, 16568, 16586, 16588, 16596,
    16612, 16613, 16614, 16621, 16622, 16623, 16624, 16626, 16628, 16632,
    16633, 16634, 16635, 16644, 16649,
]


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend import db as database

    start_iso = datetime.now(UTC).isoformat()
    start_sql = start_iso[:19].replace("T", " ")
    lbs_arg = ",".join(str(n) for n in LB_NUMBERS)

    cmd = [
        PYTHON, str(PROJECT_ROOT / "tools" / "wtrf_fetch_missing.py"),
        "--lbs", lbs_arg,
        "--delay", "2.0",
        "--add-to-qbt", "--paused",
    ]

    with LOG_PATH.open("w", encoding="utf-8") as log_fh:
        log_fh.write(f"# wtrf batch-85 rerun started {start_iso}\n")
        log_fh.write(f"$ {' '.join(cmd)}\n\n")
        log_fh.flush()
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), stdout=log_fh, stderr=subprocess.STDOUT,
        )
    end_iso = datetime.now(UTC).isoformat()

    # ── Pull the latest wtrf_downloads row per LB number from this run ─────────
    database.init_db()
    rows_by_lb: dict[int, dict] = {}
    for lb in LB_NUMBERS:
        for row in database.get_wtrf_downloads(lb_number=lb):
            if row.get("attempted_at", "") >= start_sql:
                if lb not in rows_by_lb or row["attempted_at"] > rows_by_lb[lb]["attempted_at"]:
                    rows_by_lb[lb] = row

    counts = {"downloaded": 0, "qbt_added": 0, "skipped": 0, "failed": 0, "missing": 0}
    lines = [
        f"# WTRF batch-85 rerun — {start_iso} to {end_iso}",
        "",
        f"Command exit code: {proc.returncode}",
        "",
        "| LB | Status | Confidence | Error / candidate link(s) |",
        "|---|---|---|---|",
    ]

    for lb in LB_NUMBERS:
        row = rows_by_lb.get(lb)
        if not row:
            counts["missing"] += 1
            lines.append(f"| LB-{lb:05d} | *(no row recorded)* | — | — |")
            continue
        status = row.get("status", "?")
        counts[status] = counts.get(status, 0) + 1
        conf = row.get("confidence", "?")
        topic_url = row.get("topic_url") or ""
        error = row.get("error") or ""
        detail = topic_url if status in ("downloaded", "qbt_added") else (error or topic_url)
        lines.append(f"| LB-{lb:05d} | {status} | {conf} | {detail} |")

    lines += [
        "",
        "## Summary",
        "",
        f"- Total entries: {len(LB_NUMBERS)}",
    ]
    for k in ("downloaded", "qbt_added", "skipped", "failed", "missing"):
        lines.append(f"- {k}: {counts.get(k, 0)}")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"counts": counts, "report": str(REPORT_PATH)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
