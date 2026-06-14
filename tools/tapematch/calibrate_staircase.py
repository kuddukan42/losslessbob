#!/usr/bin/env python3
"""TODO-139 Task 5 step 3 — calibrate staircase short-window thresholds.

Re-ingests specific sources from `my_collection` and computes the per-window
residual_corr distribution at `staircase_window_sec`/`staircase_hop_sec` for
known same-source and known different-source-same-show pairs (both sides
classified "staircase/splice" in the 2001-10-30 run). Used to set
`staircase_window_corr_threshold` / `staircase_coverage_threshold` in
config.yaml — see tools/tapematch/BASELINE.md "Task 5 results".

Usage: .venv/bin/python3 calibrate_staircase.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from tapematch import align, ingest, match, trim  # noqa: E402

ROOT = Path("/mnt/DYLAN1/Concerts/2001")
SOURCES = {
    "LB-08413": ROOT / "2001-10-30 Green Bay, (LB-08413)",
    "LB-07888": ROOT / "2001-10-30 Green Bay, WI (LB-07888)",
    "LB-13258": ROOT / "2001-10-30 Memorial Arena, Green Bay, WI (LB-13258)",
}

# (label, lb_a, lb_b) — both sides classified "staircase/splice" in the
# 2001-10-30 run (via union of both lag-curve passes; see BASELINE.md).
PAIRS = [
    ("same-source", "LB-07888", "LB-08413"),
    ("different-source, same show", "LB-08413", "LB-13258"),
]


def _ingest_trimmed(sdir: Path, exts: list[str], sr: int, cfg: dict) -> np.ndarray:
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)
    s0, s1 = trim.performance_envelope(stream, sr, cfg)
    a, b = int(s0 * sr), int(s1 * sr)
    return np.ascontiguousarray(stream[a:b].ravel())


def _percentiles(arr: np.ndarray) -> dict[str, float]:
    pcts = [0, 5, 25, 50, 75, 95, 100]
    return {f"p{p}": float(np.percentile(arr, p)) for p in pcts}


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]

    print("Ingesting + trimming sources ...")
    mono: dict[str, np.ndarray] = {}
    for name, sdir in SOURCES.items():
        rep = ingest.source_report(sdir, exts)
        print(f"  {name}: {rep['n_tracks']} tracks, {ingest.fmt_hms(rep['total_sec'])}")
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"    -> trimmed {ingest.fmt_hms(len(mono[name]) / sr)}")

    sm = cfg["secondary_match"]
    stair_cfg = {
        **cfg,
        "secondary_match": {
            **sm,
            "window_sec": sm["staircase_window_sec"],
            "hop_sec": sm["staircase_hop_sec"],
            "window_corr_threshold": 0.0,  # permissive — we want the full distribution
        },
    }

    print(f"\nCalibration windows: {sm['staircase_window_sec']}s / "
          f"hop {sm['staircase_hop_sec']}s, local_lag_sec={sm['local_lag_sec']}\n")

    for label, lb_a, lb_b in PAIRS:
        sec = match.secondary_corr_pair(
            mono[lb_a], mono[lb_b], sr, stair_cfg, return_raw=True,
        )
        win_corrs = np.array(sec["win_corrs"])
        pcts = _percentiles(win_corrs)
        print(f"=== {label}: {lb_a} / {lb_b} ===")
        print(f"  n_windows={len(win_corrs)}")
        print("  residual_corr percentiles: " +
              ", ".join(f"{k}={v:.4f}" for k, v in pcts.items()))
        for thr in (0.10, 0.15, 0.20, 0.25, 0.30):
            frac = float((win_corrs >= thr).mean())
            print(f"  frac >= {thr:.2f}: {frac:.3f}")
        print()


if __name__ == "__main__":
    main()
