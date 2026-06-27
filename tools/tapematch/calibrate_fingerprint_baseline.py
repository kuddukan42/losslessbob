#!/usr/bin/env python3
"""TODO-185 step 3 -- baseline calibration for 200-4kHz windowed fingerprinting.

calibrate_fingerprint_localize.py found that the 200-4kHz band separates 3 of 5
curator-claimed same-source pairs on 1991-11-05 (0.19-0.24 Dice) from the single
negative control on that date (0.103). But one negative control is not enough to
set a threshold safely -- the 200-4kHz band picks up shared musical content across
same-show different-source pairs, and we need to know how high that ceiling sits
across other dates before we can set a floor.

This script runs the same 200-4kHz windowed fingerprinting on:
  - 2001-10-30 Green Bay, WI: LB-07888/LB-08413 (confirmed same-source positive),
    LB-08413/LB-13258 (confirmed distinct, from BASELINE.md Task 5), plus other
    same-show pairs.
  - 1989-06-04 Dublin, Ireland: confirmed-distinct same-show pairs (lb_says_same=None
    in observations.db -- nobody claimed same source -- as unambiguous negatives).

Positive controls (LB-07888/LB-08413) validate that same-source pairs score high
in the 200-4kHz band too.  Negative controls (same show, confirmed different source)
measure the musical-content false-positive ceiling to calibrate the threshold.

Read-only: no config.yaml mutation, no DB/archive write.

Usage: .venv/bin/python3 calibrate_fingerprint_baseline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from tapematch import ingest, match, trim  # noqa: E402

SOURCES_2001 = {
    "LB-07888": Path("/mnt/DYLAN1/Concerts/2001/2001-10-30 Green Bay, WI (LB-07888)"),
    "LB-08413": Path("/mnt/DYLAN1/Concerts/2001/2001-10-30 Green Bay, (LB-08413)"),
    "LB-13258": Path("/mnt/DYLAN1/Concerts/2001/2001-10-30 Memorial Arena, Green Bay, WI (LB-13258)"),
}

# (label, lb_a, lb_b, kind)  kind: "same_source" | "different_source_same_show"
PAIRS_2001 = [
    ("same-source positive",            "LB-07888", "LB-08413", "same_source"),
    ("confirmed distinct (no claim)",   "LB-08413", "LB-13258", "different_source_same_show"),
    ("confirmed distinct (no claim)",   "LB-07888", "LB-13258", "different_source_same_show"),
]

ROOT_1989 = Path("/mnt/DYLAN1/Concerts/1989")
SOURCES_1989 = {
    "LB-02470": ROOT_1989 / "1989-06-04 Dublin (LB-02470)",
    "LB-02478": ROOT_1989 / "1989-06-04 Dublin, Ireland, Simmonscourt, R.D.S. (LB-02478)",
    "LB-06445": ROOT_1989 / "1989-06-04 Dublin, Ireland (LB-06445)",
    "LB-07214": ROOT_1989 / "1989-06-04 Dublin, Ireland Simmonscourt, R.D.S. (LB-07214)",
    "LB-10916": ROOT_1989 / "1989-06-04 Dublin, Ireland (LB-10916)",
}

PAIRS_1989 = [
    # lb_says_same=None in observations.db -- nobody claimed these are the same source;
    # confirmed different_family by tapematch; used here as unambiguous negatives.
    ("confirmed distinct (no claim)", "LB-02470", "LB-02478", "different_source_same_show"),
    ("confirmed distinct (no claim)", "LB-02470", "LB-07214", "different_source_same_show"),
    ("confirmed distinct (no claim)", "LB-02470", "LB-10916", "different_source_same_show"),
    # LB-07214/LB-10916 are same_family (confirmed same source) -- positive cross-check
    ("same-source positive", "LB-07214", "LB-10916", "same_source"),
    # contradicted claims -- curators said same source, tapematch says different
    ("contradicted claim",   "LB-02478", "LB-06445", "different_source_same_show"),
    ("contradicted claim",   "LB-06445", "LB-10916", "different_source_same_show"),
]

WIN_SEC = 20.0
HOP_SEC = 5.0
BAND_200_4K = {"hf_band_hz": [200, 4000]}


def _ingest_trimmed(sdir: Path, exts: list[str], sr: int, cfg: dict) -> np.ndarray:
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)
    s0, s1 = trim.performance_envelope(stream, sr, cfg)
    a, b = int(s0 * sr), int(s1 * sr)
    return np.ascontiguousarray(stream[a:b].ravel())


def _run_date(date_label: str, sources: dict[str, Path], pairs: list[tuple],
              cfg: dict, sr: int, exts: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"DATE: {date_label}")
    print(f"{'='*60}")
    mono: dict[str, np.ndarray] = {}
    for name, sdir in sources.items():
        rep = ingest.source_report(sdir, exts)
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"  {name}: {rep['n_tracks']} tracks -> trimmed "
              f"{ingest.fmt_hms(len(mono[name]) / sr)}")

    fp_cfg = {**cfg["fingerprint"], **BAND_200_4K}
    variant_cfg = {**cfg, "fingerprint": fp_cfg}

    fps: dict[str, list[set]] = {}
    for name, m in mono.items():
        fps[name] = match.windowed_fingerprints(m, sr, variant_cfg, WIN_SEC, HOP_SEC)
        print(f"    {name}: {len(fps[name])} windows")

    print(f"\n  --- Results (200-4kHz band, win={WIN_SEC}s hop={HOP_SEC}s) ---")
    for label, lb_a, lb_b, kind in pairs:
        best = match.best_window_fingerprint_match(fps[lb_a], fps[lb_b], WIN_SEC, HOP_SEC)
        if best["i"] >= 0:
            print(f"  [{kind.upper():<30}] {lb_a}/{lb_b}  dice={best['dice']:.3f}"
                  f"  @ {lb_a}~{best['center_a_sec']:.0f}s / {lb_b}~{best['center_b_sec']:.0f}s"
                  f"  ({label})")
        else:
            print(f"  [{kind.upper():<30}] {lb_a}/{lb_b}  dice=0.000  ({label})")


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]

    _run_date("2001-10-30 Green Bay, WI", SOURCES_2001, PAIRS_2001, cfg, sr, exts)
    _run_date("1989-06-04 Dublin, Ireland", SOURCES_1989, PAIRS_1989, cfg, sr, exts)


if __name__ == "__main__":
    main()
