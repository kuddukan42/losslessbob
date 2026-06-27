#!/usr/bin/env python3
"""TODO-144 step 1 -- falsify-first pilot for piecewise alignment of staircase pairs.

Per BASELINE.md Task 5, the 5 s short-window recalibration found no usable gap
between same-source and different-source-same-show pairs on 2001-10-30.  Task 5
concluded: "limiting factor is signal content, not the alignment/search mechanism."
TODO-144 proposes a different fix: use the staircase lag-curve to LOCATE splice
points, then run secondary_corr_pair independently per segment with its own per-
segment local-lag search.  The hypothesis: the whole-recording lag curve diverges
after a splice, but within each piecewise segment the lag is well-defined, so
the per-segment correlation can be recovered.

This pilot runs on 2001-10-30 (the same date Task 5 used):
  - LB-07888 / LB-08413: same-source positive (staircase-flagged, corr ~0.52 before
    splice confusion -- see BASELINE.md Task 5)
  - LB-08413 / LB-13258: different-source same-show negative control

For each pair:
  1. Compute the lag curve (same as cli.py Pass 1) to locate splice points via
     align.locate_splice_points().
  2. Split each mono array at the splice times and run secondary_corr_pair()
     independently per segment, with the standard config local_lag_sec.
  3. Report per-segment windowed_median corr + n_windows for both pairs.
  4. Compare same-source vs different-source distribution -- is there a gap?

Read-only: no config.yaml mutation, no DB/archive write.

Usage: .venv/bin/python3 calibrate_piecewise.py
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
    "LB-07888": ROOT / "2001-10-30 Green Bay, WI (LB-07888)",
    "LB-08413": ROOT / "2001-10-30 Green Bay, (LB-08413)",
    "LB-13258": ROOT / "2001-10-30 Memorial Arena, Green Bay, WI (LB-13258)",
}

PAIRS = [
    ("same-source (staircase-flagged)", "LB-07888", "LB-08413"),
    ("different-source same-show",      "LB-08413", "LB-13258"),
]


def _ingest_trimmed(sdir: Path, exts: list[str], sr: int, cfg: dict) -> np.ndarray:
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)
    s0, s1 = trim.performance_envelope(stream, sr, cfg)
    a, b = int(s0 * sr), int(s1 * sr)
    return np.ascontiguousarray(stream[a:b].ravel())


def _split_at_splices(mono: np.ndarray, sr: int,
                      splice_secs: list[float]) -> list[np.ndarray]:
    """Split mono array into segments at the given splice times."""
    n = len(mono)
    boundaries = [0] + [int(s * sr) for s in sorted(splice_secs)] + [n]
    segments = []
    for i in range(len(boundaries) - 1):
        s0, s1 = boundaries[i], boundaries[i + 1]
        if s1 > s0:
            segments.append(np.ascontiguousarray(mono[s0:s1]))
    return segments


def _percentiles(arr: list[float]) -> str:
    if not arr:
        return "(no data)"
    a = np.array(arr)
    return (f"p0={a.min():.3f} p25={np.percentile(a,25):.3f} "
            f"p50={np.median(a):.3f} p75={np.percentile(a,75):.3f} "
            f"p100={a.max():.3f}")


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]
    step_flag = cfg["align"]["step_flag_sec"]

    print("Ingesting + trimming sources ...")
    mono: dict[str, np.ndarray] = {}
    for name, sdir in SOURCES.items():
        rep = ingest.source_report(sdir, exts)
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"  {name}: {rep['n_tracks']} tracks -> trimmed "
              f"{ingest.fmt_hms(len(mono[name]) / sr)}")

    print("\nComputing lag curves + locating splice points ...")
    anchors: dict[str, list[float]] = {}
    for name, m in mono.items():
        anchors[name] = align.pick_anchors(m, sr, cfg)
        print(f"  {name}: {len(anchors[name])} anchors")

    for label, lb_ref, lb_other in PAIRS:
        print(f"\n{'='*60}")
        print(f"PAIR: {label}  ({lb_ref} / {lb_other})")
        print(f"{'='*60}")

        rows = align.lag_curve(mono[lb_ref], mono[lb_other], sr,
                               anchors[lb_ref], cfg)
        interp = align.interpret_curve(rows, cfg)
        print(f"  lag-curve kind: {interp['kind']}  "
              f"max_step={interp['max_step_sec']:.2f}s  ppm={interp['ppm']:.0f}")

        splices = align.locate_splice_points(rows, step_flag)
        print(f"  splice points detected: {len(splices)}  "
              f"@ {[f'{s:.0f}s' for s in splices]}")

        if not splices:
            print("  (no splices — running whole-recording secondary_corr_pair as baseline)")
            result = match.secondary_corr_pair(mono[lb_ref], mono[lb_other], sr, cfg)
            print(f"  whole-recording: windowed_median={result['windowed_median']:.4f}  "
                  f"n_windows={result['n_windows']}")
            continue

        # Split ref at its own splice points and other at its own lag-curve splices.
        rows_other = align.lag_curve(mono[lb_other], mono[lb_ref], sr,
                                     anchors[lb_other], cfg)
        splices_other = align.locate_splice_points(rows_other, step_flag)
        print(f"  splice points in {lb_other} (other-side): {len(splices_other)}  "
              f"@ {[f'{s:.0f}s' for s in splices_other]}")

        # Use the union of both sides' detected splices so each segment is
        # coherent within both recordings.
        all_splices = sorted(set(splices + splices_other))
        segs_ref   = _split_at_splices(mono[lb_ref],   sr, all_splices)
        segs_other = _split_at_splices(mono[lb_other], sr, all_splices)
        n_segs = min(len(segs_ref), len(segs_other))
        print(f"  piecewise segments: {n_segs}  "
              f"(union of {len(all_splices)} splice points)")

        seg_medians: list[float] = []
        for i in range(n_segs):
            seg_r = segs_ref[i]
            seg_o = segs_other[i]
            dur_r = len(seg_r) / sr
            dur_o = len(seg_o) / sr
            if min(dur_r, dur_o) < cfg["secondary_match"]["window_sec"]:
                print(f"  seg {i}: too short ({dur_r:.0f}s / {dur_o:.0f}s) — skip")
                continue
            result = match.secondary_corr_pair(seg_r, seg_o, sr, cfg)
            med = result["windowed_median"]
            n_w = result["n_windows"]
            seg_medians.append(med)
            print(f"  seg {i}: dur={dur_r:.0f}s/{dur_o:.0f}s  "
                  f"windowed_median={med:.4f}  n_windows={n_w}")

        print(f"  per-segment medians: {_percentiles(seg_medians)}")

        # Compare against whole-recording baseline.
        wr = match.secondary_corr_pair(mono[lb_ref], mono[lb_other], sr, cfg)
        print(f"  whole-recording baseline: windowed_median={wr['windowed_median']:.4f}  "
              f"n_windows={wr['n_windows']}")


if __name__ == "__main__":
    main()
