"""Adhoc Concert-Ranker quality scoring for arbitrary (non-LB) folders.

Scans each source subfolder, derives a source class from any local text
files, and grades it with the shipped Concert Ranker model. Writes NOTHING
to the app DB — results go to stdout + a JSON sidecar.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from concert_ranker.scan import scan_folder
from concert_ranker.quality_score import grade
from concert_ranker.lb.source_type import derive_source_class
from concert_ranker.audio.io import UnreadableAudioError

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("adhoc_quality.json")


def _description(folder: Path) -> str:
    """Concatenate readme/info text files to feed source-class detection."""
    txt = []
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() in (".txt", ".md", ".nfo") and p.is_file():
            try:
                txt.append(p.read_text(errors="replace"))
            except Exception:
                pass
    return "\n".join(txt)[:20000]


rows = []
for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
    name = folder.name
    desc = _description(folder)
    src_class = derive_source_class(desc, None) or "UNKNOWN"
    try:
        res = scan_folder(folder)
    except UnreadableAudioError as e:
        rows.append({"folder": name, "status": "unreadable", "error": str(e)})
        print(f"[SKIP] {name}: {e}")
        continue
    metrics = res["metrics"]
    score, letter, rank = grade(metrics, src_class)
    row = {
        "folder": name,
        "status": "ok",
        "source_class": src_class,
        "n_tracks": res["n_tracks"],
        "duration_sec": round(res["duration_sec"], 1),
        "abs_score": round(score, 1),
        "abs_grade": letter,
        "rank": round(rank, 2),
        "metrics": metrics,
    }
    rows.append(row)
    print(f"[OK]   {letter:>2} {score:5.1f}  {src_class:<7} "
          f"{res['n_tracks']:2d}trk {res['duration_sec']/60:5.1f}min  {name}")

OUT.write_text(json.dumps(rows, indent=2, default=str))
print(f"\nwrote {OUT}")
