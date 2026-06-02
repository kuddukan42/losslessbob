"""tapematch CLI.

    python -m tapematch.cli /path/to/processing --config config.yaml

processing/ contains one subfolder per recording. Output: ingest report,
trim report, lag-curve diagnosis per pair, residual-corr matrix, clusters,
and lineage evidence.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
import yaml
from . import ingest, trim, align, match
from .audio import to_mono
from .ingest import fmt_hms


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tapematch")
    ap.add_argument("root", help="processing folder (one subfolder per source)")
    ap.add_argument("--config", default=str(Path(__file__).parent.parent / "config.yaml"))
    ap.add_argument("--no-trim", action="store_true", help="skip head/tail trim")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(open(args.config))
    sr = cfg["audio"]["analysis_sr"]
    mono_mix = cfg["audio"]["mono_mix"]
    exts = cfg["ingest"]["audio_exts"]

    root = Path(args.root)
    sources = ingest.discover_sources(root)
    if not sources:
        print(f"no source subfolders in {root}", file=sys.stderr); return 1

    print("=== INGEST ===")
    streams = {}
    for name, sdir in sources.items():
        rep = ingest.source_report(sdir, exts)
        print(f"  {name}: {rep['n_tracks']} tracks, {fmt_hms(rep['total_sec'])}")
        stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=mono_mix)
        streams[name] = stream

    print("\n=== TRIM (performance envelope) ===")
    trimmed = {}
    for name, stream in streams.items():
        if args.no_trim:
            trimmed[name] = stream; continue
        s0, s1 = trim.performance_envelope(stream, sr, cfg)
        head = s0; tail = len(to_mono(stream)) / sr - s1
        trimmed[name] = trim.apply_trim(stream, sr, s0, s1)
        print(f"  {name}: trimmed {fmt_hms(head)} head, {fmt_hms(tail)} tail "
              f"-> performance {fmt_hms(s1 - s0)}")

    # anchors from the (trimmed) reference = first source
    ref_name = next(iter(trimmed))
    ref_mono = to_mono(trimmed[ref_name])
    anchors = align.pick_anchors(ref_mono, sr, cfg)
    print(f"\n=== ANCHORS (ref={ref_name}) ===")
    print("  " + ", ".join(fmt_hms(a) for a in anchors))

    print("\n=== LAG CURVES / SPEED (vs ref) ===")
    monos = {n: to_mono(s) for n, s in trimmed.items()}
    ppm_thr = cfg["align"]["ratio_flag_ppm"]
    for name, m in monos.items():
        if name == ref_name:
            continue
        ratio = match.estimate_ratio(ref_mono, m, sr, anchors, cfg)
        ppm = (ratio - 1.0) * 1e6
        rows = align.lag_curve(ref_mono, m, sr, anchors, cfg)
        d = align.interpret_curve(rows, cfg)
        kind = d["kind"]
        if abs(ppm) > ppm_thr:
            kind = "constant-speed-offset"        # clean envelope ratio wins
        elif kind == "constant-speed-offset":
            kind = "aligned"
        print(f"  {ref_name}->{name}: {kind}  speed ratio={ratio:.6f} "
              f"({ppm:+.0f} ppm)")

    print("\n=== RESIDUAL CORRELATION MATRIX ===")
    names, M = match.pairwise_matrix(monos, sr, anchors, cfg)
    hdr = "        " + "  ".join(f"{n[:6]:>6}" for n in names)
    print(hdr)
    for i, n in enumerate(names):
        row = "  ".join(f"{M[i,j]:6.3f}" for j in range(len(names)))
        print(f"  {n[:6]:>6}  {row}")

    print("\n=== CLUSTERS ===")
    groups = match.cluster(names, M, cfg["match"]["cluster_threshold"])
    for gi, g in enumerate(groups, 1):
        intra = [M[names.index(a), names.index(b)]
                 for a in g for b in g if a != b]
        mc = np.mean(intra) if intra else 1.0
        print(f"  Family {gi}: {', '.join(g)}  (mean intra-corr {mc:.3f})")
    print(f"  Distinct source families: {len(groups)}")

    print("\n=== LINEAGE EVIDENCE (interpret manually) ===")
    print(f"  {'source':>8}  {'HF ceiling':>11}  {'noise floor':>11}")
    capped = False
    for name, s in trimmed.items():
        ev = match.lineage_evidence(s, sr, cfg)
        capped = capped or ev["nyquist_capped"]
        print(f"  {name:>8}  {ev['hf_ceiling_hz']/1000:8.1f}kHz  "
              f"{ev['noise_floor_db']:9.1f}dB")
    if capped:
        print(f"  (HF ceiling capped by {sr//2} Hz Nyquist at analysis_sr={sr}; "
              f"run lineage at native rate for real format discrimination)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
