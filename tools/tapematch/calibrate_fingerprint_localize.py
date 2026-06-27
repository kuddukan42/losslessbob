#!/usr/bin/env python3
"""TODO-185 step 2 -- falsify-first pilot for windowed landmark-fingerprint
localization, replacing the falsified "best contiguous run on 60s
residual_corr windows" approach (calibrate_contig_run.py: all 5 curator-
claimed pairs on 1991-11-05 scored statistically identical to a known-
distinct negative control, at both +-10s and +-120s lag search -- no usable
waveform-correlation signal exists at that granularity for this network).

Same sources, same claimed pairs, same negative control -- see
calibrate_contig_run.py's docstring for the full citation list. This script
instead computes match.windowed_fingerprints() (small windows, e.g. 20s/5s
hop) for each source once, then match.best_window_fingerprint_match() per
pair, searching every window-pair for the best landmark-hash overlap. Unlike
residual_corr, landmark hashing is offset-invariant by construction, so it
does not require the two recordings' claimed-shared moment to land at the
same absolute trim offset -- relevant here since LB-09174 is a patchwork
composite trimmed to a different total length than its siblings.

Read-only: no config.yaml mutation, no DB/archive write.

Usage: .venv/bin/python3 calibrate_fingerprint_localize.py
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

WIN_SEC = 20.0
HOP_SEC = 5.0

# Band configs to try in one pass (hf_band_hz key absent = full-band).
BAND_VARIANTS: list[tuple[str, dict]] = [
    ("6-8kHz HF-band (original)",   {"hf_band_hz": [6000, 8000]}),
    ("200-4kHz crowd/clap band",     {"hf_band_hz": [200, 4000]}),
    ("full-band (no restriction)",   {}),
]


def _ingest_trimmed(sdir: Path, exts: list[str], sr: int, cfg: dict) -> np.ndarray:
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)
    s0, s1 = trim.performance_envelope(stream, sr, cfg)
    a, b = int(s0 * sr), int(s1 * sr)
    return np.ascontiguousarray(stream[a:b].ravel())


def _run_variant(mono: dict[str, np.ndarray], sr: int, base_cfg: dict,
                 band_override: dict, label: str) -> None:
    """Run one band-config variant: compute windowed fingerprints + report."""
    fp_cfg = {**base_cfg["fingerprint"], **band_override}
    variant_cfg = {**base_cfg, "fingerprint": fp_cfg}
    band_desc = (f'hf_band_hz={band_override["hf_band_hz"]}'
                 if "hf_band_hz" in band_override else "no band restriction")
    print(f"\n=== {label} ({band_desc}) ===")

    fps: dict[str, list[set]] = {}
    for name, m in mono.items():
        fps[name] = match.windowed_fingerprints(m, sr, variant_cfg, WIN_SEC, HOP_SEC)

    for pair_label, lb_a, lb_b, is_positive in PAIRS:
        best = match.best_window_fingerprint_match(fps[lb_a], fps[lb_b], WIN_SEC, HOP_SEC)
        tag = "POSITIVE" if is_positive else "NEGATIVE"
        if best["i"] >= 0:
            print(f"  [{tag}] {lb_a}/{lb_b}  dice={best['dice']:.3f}  "
                  f"@ {lb_a}~{best['center_a_sec']:.0f}s / {lb_b}~{best['center_b_sec']:.0f}s"
                  f"  ({pair_label})")
        else:
            print(f"  [{tag}] {lb_a}/{lb_b}  dice=0.000 (no windows)  ({pair_label})")


def main() -> None:
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]

    print("Ingesting + trimming sources ...")
    mono: dict[str, np.ndarray] = {}
    for name, sdir in SOURCES.items():
        rep = ingest.source_report(sdir, exts)
        mono[name] = _ingest_trimmed(sdir, exts, sr, cfg)
        print(f"  {name}: {rep['n_tracks']} tracks -> trimmed "
              f"{ingest.fmt_hms(len(mono[name]) / sr)}")

    for band_label, band_override in BAND_VARIANTS:
        _run_variant(mono, sr, cfg, band_override, band_label)


if __name__ == "__main__":
    main()
