"""tapematch CLI.

    python -m tapematch.cli /path/to/processing --config config.yaml

processing/ contains one subfolder per recording. Output: ingest report,
trim report, lag-curve diagnosis per pair, residual-corr matrix, clusters,
and lineage evidence.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import yaml
from . import ingest, trim, align, match
from .audio import to_mono, resample_ratio
from .ingest import fmt_hms


def _load_trimmed_mono(sdir, exts, sr, mono_mix, s0, s1, no_trim):
    """Load one source, apply trim bounds, return mono; stream freed before return."""
    stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=mono_mix)
    if not no_trim:
        stream = trim.apply_trim(stream, sr, s0, s1)
    mono = to_mono(stream)
    del stream
    return mono


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

    # === Pass 1: load each source once, compute trim bounds, discard immediately ===
    # trim_bounds holds only seconds — stays tiny regardless of source count.
    print("=== INGEST ===")
    trim_bounds: dict[str, tuple[float, float, float]] = {}  # name -> (s0, s1, total_sec)
    for name, sdir in sources.items():
        rep = ingest.source_report(sdir, exts)
        print(f"  {name}: {rep['n_tracks']} tracks, {fmt_hms(rep['total_sec'])}")
        stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=mono_mix)
        if args.no_trim:
            s0, s1 = 0.0, rep["total_sec"]
        else:
            s0, s1 = trim.performance_envelope(stream, sr, cfg)
        trim_bounds[name] = (s0, s1, rep["total_sec"])
        del stream

    # Persist trim metadata — short JSON, survives re-runs and resume
    (root / ".tapematch_meta.json").write_text(json.dumps(
        {"trim": {n: {"s0": s0, "s1": s1} for n, (s0, s1, _) in trim_bounds.items()}},
        indent=2,
    ))

    print("\n=== TRIM (performance envelope) ===")
    for name, (s0, s1, total_sec) in trim_bounds.items():
        if args.no_trim:
            continue
        print(f"  {name}: trimmed {fmt_hms(s0)} head, {fmt_hms(total_sec - s1)} tail "
              f"-> performance {fmt_hms(s1 - s0)}")

    # === Anchors: load reference once; keep ref_mono in RAM for lag + matrix ===
    ref_name = next(iter(trim_bounds))
    ref_s0, ref_s1, _ = trim_bounds[ref_name]
    ref_mono = _load_trimmed_mono(
        sources[ref_name], exts, sr, mono_mix, ref_s0, ref_s1, args.no_trim
    )
    anchors = align.pick_anchors(ref_mono, sr, cfg)
    print(f"\n=== ANCHORS (ref={ref_name}) ===")
    print("  " + ", ".join(fmt_hms(a) for a in anchors))

    # === Lag curves: ref_mono stays in RAM; one other source loaded at a time ===
    print("\n=== LAG CURVES / SPEED (vs ref) ===")
    ppm_thr = cfg["align"]["ratio_flag_ppm"]
    for name, (s0, s1, _) in trim_bounds.items():
        if name == ref_name:
            continue
        other_mono = _load_trimmed_mono(
            sources[name], exts, sr, mono_mix, s0, s1, args.no_trim
        )
        ratio = match.estimate_ratio(ref_mono, other_mono, sr, anchors, cfg)
        ppm = (ratio - 1.0) * 1e6
        rows = align.lag_curve(ref_mono, other_mono, sr, anchors, cfg)
        d = align.interpret_curve(rows, cfg)
        kind = d["kind"]
        if abs(ppm) > ppm_thr:
            kind = "constant-speed-offset"
        elif kind == "constant-speed-offset":
            kind = "aligned"
        print(f"  {ref_name}->{name}: {kind}  speed ratio={ratio:.6f} ({ppm:+.0f} ppm)")
        del other_mono

    # === Residual correlation matrix: one pair at a time ===
    # ref_mono is kept in RAM so ref-column pairs skip a reload.
    # All other sources are loaded, used for one pair, then freed.
    print("\n=== RESIDUAL CORRELATION MATRIX ===")
    names = list(trim_bounds.keys())
    n_src = len(names)
    M = np.eye(n_src)
    a_cfg = cfg["align"]
    win = cfg["anchors"]["window_sec"]
    ref_idx = names.index(ref_name)

    for i in range(n_src - 1):  # last source is never the outer member of a new pair
        si0, si1, _ = trim_bounds[names[i]]
        ri = ref_mono if i == ref_idx else _load_trimmed_mono(
            sources[names[i]], exts, sr, mono_mix, si0, si1, args.no_trim
        )
        for j in range(i + 1, n_src):
            sj0, sj1, _ = trim_bounds[names[j]]
            rj = ref_mono if j == ref_idx else _load_trimmed_mono(
                sources[names[j]], exts, sr, mono_mix, sj0, sj1, args.no_trim
            )
            ratio = match.estimate_ratio(ri, rj, sr, anchors, cfg)
            rj_c = resample_ratio(rj, ratio) if abs(ratio - 1.0) * 1e6 > ppm_thr else rj
            corrs = []
            for ctr in anchors:
                lag, _ = align.local_lag(ri, rj_c, sr, ctr, win, a_cfg["max_lag_sec"])
                if lag is None:
                    continue
                ra, ob = match.aligned_window(ri, rj_c, sr, ctr, win, lag)
                corrs.append(abs(match.residual_corr(ra, ob)))
            M[i, j] = M[j, i] = float(np.median(corrs)) if corrs else 0.0
            if j != ref_idx:
                del rj
        if i != ref_idx:
            del ri

    hdr = "        " + "  ".join(f"{n[:6]:>6}" for n in names)
    print(hdr)
    for i, nm in enumerate(names):
        row = "  ".join(f"{M[i,j]:6.3f}" for j in range(n_src))
        print(f"  {nm[:6]:>6}  {row}")

    print("\n=== CLUSTERS ===")
    groups = match.cluster(names, M, cfg["match"]["cluster_threshold"])
    for gi, g in enumerate(groups, 1):
        intra = [M[names.index(a), names.index(b)]
                 for a in g for b in g if a != b]
        mc = np.mean(intra) if intra else 1.0
        print(f"  Family {gi}: {', '.join(g)}  (mean intra-corr {mc:.3f})")
    print(f"  Distinct source families: {len(groups)}")

    # === Lineage: load full stereo stream per source, free after each ===
    print("\n=== LINEAGE EVIDENCE (interpret manually) ===")
    print(f"  {'source':>8}  {'HF ceiling':>11}  {'noise floor':>11}")
    capped = False
    for name, (s0, s1, _) in trim_bounds.items():
        stream, _, _ = ingest.concat_source(sources[name], exts, sr, mono=mono_mix)
        if not args.no_trim:
            stream = trim.apply_trim(stream, sr, s0, s1)
        ev = match.lineage_evidence(stream, sr, cfg)
        capped = capped or ev["nyquist_capped"]
        print(f"  {name:>8}  {ev['hf_ceiling_hz']/1000:8.1f}kHz  "
              f"{ev['noise_floor_db']:9.1f}dB")
        del stream

    if capped:
        print(f"  (HF ceiling capped by {sr//2} Hz Nyquist at analysis_sr={sr}; "
              f"run lineage at native rate for real format discrimination)")
    del ref_mono
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
