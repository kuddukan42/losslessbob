#!/usr/bin/env python3
"""TODO-140 step 1 -- falsify-first pilot for low-band (250-2000 Hz) energy-envelope
cross-correlation as a fallback for HF-dead / high-noise-floor sources.

BASELINE.md Task 4 established that for 1989-06-04 (Dublin) and 1990-01-12 (New Haven),
several curator-claimed same-source pairs score near-zero on both primary residual_corr
and secondary_corr_pair windowed-median at all tested lags -- the HF fine-structure is
absent, so the standard residual_corr signal collapses. CC_TAPEMATCH_FIXES.md step 5
proposes a low-band (250-2000 Hz) *envelope* fallback: broad-band dynamics (audience
crescendos, song starts, applause patterns) may still be correlated even when the
tape-hiss HF band is dead.

match.lowband_envelope_corr() bandpass-filters both sources to 250-2000 Hz (zero-phase,
no waveform resampling per WORKFLOW.md), computes log-RMS energy envelopes, and
cross-correlates them via offset-shift lag search.

This pilot tests whether the low-band envelope provides a usable gap between:
  - lb_says_same=1, different_family "missed" pairs (the TODO's target)
  - confirmed-distinct same-show pairs (the false-positive ceiling)

Read-only: no config.yaml mutation, no DB/archive write.

Usage: .venv/bin/python3 calibrate_lowband.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from tapematch import ingest, match, trim  # noqa: E402

ROOT_1989 = Path("/mnt/DYLAN1/Concerts/1989")
SOURCES_1989 = {
    "LB-02470": ROOT_1989 / "1989-06-04 Dublin (LB-02470)",
    "LB-02478": ROOT_1989 / "1989-06-04 Dublin, Ireland, Simmonscourt, R.D.S. (LB-02478)",
    "LB-06445": ROOT_1989 / "1989-06-04 Dublin, Ireland (LB-06445)",
    "LB-07214": ROOT_1989 / "1989-06-04 Dublin, Ireland Simmonscourt, R.D.S. (LB-07214)",
    "LB-10916": ROOT_1989 / "1989-06-04 Dublin, Ireland (LB-10916)",
    "LB-14054": ROOT_1989 / "1989-06-04 Dublin, Ireland (LB-14054)",
}

# (label, lb_a, lb_b, kind)
PAIRS_1989 = [
    # lb_says_same=1, different_family — the "missed" pairs this TODO targets
    ("contradicted claim",              "LB-02470", "LB-06445", "missed"),
    ("contradicted claim",              "LB-02470", "LB-14054", "missed"),
    ("contradicted claim",              "LB-02478", "LB-14054", "missed"),
    ("contradicted claim",              "LB-06445", "LB-14054", "missed"),
    ("contradicted claim",              "LB-07214", "LB-14054", "missed"),
    # confirmed same-source positive control
    ("same-source positive",            "LB-07214", "LB-10916", "same_source"),
    # lb_says_same=None, different_family — unambiguous different-source same-show
    ("confirmed distinct (no claim)",   "LB-02470", "LB-02478", "distinct"),
]

ROOT_1990 = Path("/mnt/DYLAN1/Concerts/1990")
SOURCES_1990 = {
    "LB-01776": ROOT_1990 / "1990-01-12 Toad's Place (New Haven, CT) (LB-01776)",
    "LB-02614": ROOT_1990 / "1990-01-12 Toad's Place, New Haven, Connecticut (LB-02614)",
    "LB-06613": ROOT_1990 / "1990-01-12 Toad's Place, New Haven, Connecticut (LB-06613)",
    "LB-08421": ROOT_1990 / "1990-01-12 Toad's Place, New Haven, Ct. (LB-08421)",
}

PAIRS_1990 = [
    # lb_says_same=1, different_family — the "missed" pairs
    ("contradicted claim",              "LB-01776", "LB-02614", "missed"),
    ("contradicted claim",              "LB-01776", "LB-06613", "missed"),
    ("contradicted claim",              "LB-06611", "LB-08421", "missed"),  # note: skip if missing
    # confirmed same-source positive control (lb_says_same=1, same_family)
    # LB-02614/LB-12534 same_family but LB-12534 not in SOURCES; use LB-06613/LB-08421
    # which are different_family contradicted claims as negatives
    ("confirmed distinct same-show",    "LB-08421", "LB-01776", "distinct"),
]

BAND_HZ = (250.0, 2000.0)
MAX_LAG_SEC = 90.0


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
        if not sdir.exists():
            print(f"  {name}: NOT FOUND — skipping")
            continue
        rep = ingest.source_report(sdir, exts)
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"  {name}: {rep['n_tracks']} tracks -> trimmed "
              f"{ingest.fmt_hms(len(mono[name]) / sr)}")

    print(f"\n  --- low-band envelope corr (band={BAND_HZ} Hz, max_lag={MAX_LAG_SEC}s) ---")
    for label, lb_a, lb_b, kind in pairs:
        if lb_a not in mono or lb_b not in mono:
            print(f"  [{kind.upper():<12}] {lb_a}/{lb_b}  SKIPPED (source not available)")
            continue
        result = match.lowband_envelope_corr(
            mono[lb_a], mono[lb_b], sr,
            band_hz=BAND_HZ, max_lag_sec=MAX_LAG_SEC,
        )
        print(f"  [{kind.upper():<12}] {lb_a}/{lb_b}  "
              f"corr={result['corr']:+.3f}  lag={result['lag_sec']:+.1f}s  "
              f"n_env={result['n_env_samples']}  ({label})")


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]

    _run_date("1989-06-04 Dublin, Ireland", SOURCES_1989, PAIRS_1989, cfg, sr, exts)
    _run_date("1990-01-12 New Haven, CT", SOURCES_1990, PAIRS_1990, cfg, sr, exts)


if __name__ == "__main__":
    main()
