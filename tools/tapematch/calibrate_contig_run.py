#!/usr/bin/env python3
"""TODO-185 step 1 — audit whether a localized same-source overlap exists in
the 1991-11-05 Madison patchwork-composite network that the whole-recording
median (and existing windowed-coverage fraction) misses.

Curator claims on this date (analysis.md, run 20260617_044647_1991-11-05):
  - LB-10660 / LB-09174: "same crowd and clapping at end of d1t1" (+ claimed
    channel-swap/inversion — out of scope here, see TODO-184)
  - LB-10660 / LB-06828: "same clapping wavs at end of d1t10"
  - LB-12544 / LB-10660: "same clapping wavs at end of d1t8"
  - LB-12544 / LB-06828, LB-12544 / LB-09174: broader "probably same
    recording as" claims
All five whole-recording corr values are 0.003-0.007 (near-zero / distinct).
LB-00873 / LB-06828 is a confirmed-DISTINCT pair on the same date (explicit
uploader README disclaiming a match, corr 0.002) -- used here as the
negative control.

Re-ingests the real sources and runs match.secondary_corr_pair(...,
return_raw=True) for each claimed-positive pair plus the negative control,
reporting the per-window residual_corr distribution AND the longest
contiguous run of windows above a few candidate thresholds. Also re-runs
each claimed-positive pair with a much wider per-window local lag search
(120s instead of the production 10s), since LB-09174 is a patchwork
composite trimmed to ~4934s vs ~6100s for its siblings -- if material is
missing/reordered earlier in the show, the standard +-10s search can never
reach the true alignment for windows after that point even when the
"end of d1tN" clapping region is genuinely shared.

Read-only: no config.yaml mutation, no DB/archive write.

Usage: .venv/bin/python3 calibrate_contig_run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from tapematch import ingest, match, trim  # noqa: E402

ROOT = Path("/mnt/DYLAN1/Concerts/1991")
SOURCES = {
    "LB-00873": ROOT / "1991-11-05 Madison, Wisconsin (LB-00873)",
    "LB-06828": ROOT / "1991-11-05 Madison, Wisconsin (LB-06828)",
    "LB-09174": ROOT / "1991-11-05 Madison, Wisconsin (LB-09174)",
    "LB-10660": ROOT / "1991-11-05 Madison, Wisconsin (LB-10660)",
    "LB-12544": ROOT / "1991-11-05 Madison, WI (LB-12544)",
}

# (label, lb_a, lb_b, is_positive_claim)
PAIRS = [
    ("claimed same-source (end of d1t1)",  "LB-10660", "LB-09174", True),
    ("claimed same-source (end of d1t10)", "LB-10660", "LB-06828", True),
    ("claimed same-source (end of d1t8)",  "LB-12544", "LB-10660", True),
    ("claimed same-source (broad)",        "LB-12544", "LB-06828", True),
    ("claimed same-source (broad)",        "LB-12544", "LB-09174", True),
    ("NEGATIVE CONTROL — confirmed distinct", "LB-00873", "LB-06828", False),
]


def _ingest_trimmed(sdir: Path, exts: list[str], sr: int, cfg: dict) -> np.ndarray:
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)
    s0, s1 = trim.performance_envelope(stream, sr, cfg)
    a, b = int(s0 * sr), int(s1 * sr)
    return np.ascontiguousarray(stream[a:b].ravel())


def _percentiles(arr: np.ndarray) -> dict[str, float]:
    pcts = [0, 5, 25, 50, 75, 90, 95, 100]
    return {f"p{p}": float(np.percentile(arr, p)) for p in pcts}


def _longest_run(win_corrs: np.ndarray, threshold: float) -> tuple[int, int]:
    """(run_len, start_idx) of the longest consecutive stretch >= threshold."""
    above = win_corrs >= threshold
    best_len, best_start = 0, -1
    cur_len, cur_start = 0, -1
    for i, ok in enumerate(above):
        if ok:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
        else:
            cur_len = 0
    return best_len, best_start


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]
    sm = cfg["secondary_match"]
    hop_sec = float(sm["hop_sec"])

    print("Ingesting + trimming sources ...")
    mono: dict[str, np.ndarray] = {}
    for name, sdir in SOURCES.items():
        rep = ingest.source_report(sdir, exts)
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"  {name}: {rep['n_tracks']} tracks -> trimmed "
              f"{ingest.fmt_hms(len(mono[name]) / sr)}")

    wide_cfg = {**cfg, "secondary_match": {**sm, "local_lag_sec": 120.0}}

    for label, lb_a, lb_b, is_positive in PAIRS:
        print(f"\n=== {label}: {lb_a} / {lb_b} ===")
        for pass_label, pass_cfg in (("standard (10s lag)", cfg),
                                      ("wide (120s lag)", wide_cfg)):
            sec = match.secondary_corr_pair(
                mono[lb_a], mono[lb_b], sr, pass_cfg, return_raw=True,
            )
            win_corrs = np.array(sec["win_corrs"])
            if len(win_corrs) == 0:
                print(f"  [{pass_label}] no windows produced")
                continue
            pcts = _percentiles(win_corrs)
            print(f"  [{pass_label}] n_windows={len(win_corrs)}  " +
                  ", ".join(f"{k}={v:.4f}" for k, v in pcts.items()))
            for thr in (0.20, 0.25, 0.30, 0.40):
                run_len, start_idx = _longest_run(win_corrs, thr)
                run_sec = run_len * hop_sec
                marker = f"  @ window {start_idx} (~{start_idx * hop_sec:.0f}s)" if run_len else ""
                print(f"    longest run >= {thr:.2f}: {run_len} windows "
                      f"(~{run_sec:.0f}s){marker}")


if __name__ == "__main__":
    main()
