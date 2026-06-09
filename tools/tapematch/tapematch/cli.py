"""tapematch CLI.

    python -m tapematch.cli /path/to/processing --config config.yaml

processing/ contains one subfolder per recording. Output: ingest report,
trim report, lag-curve diagnosis per pair, residual-corr matrix, clusters,
and lineage evidence.
"""
from __future__ import annotations
import argparse, atexit, json, shutil, sys, tempfile, time
from pathlib import Path
import numpy as np
import yaml
from . import ingest, trim, align, match
from .audio import to_mono, resample_ratio
from .ingest import fmt_hms


def _rss_mb() -> float:
    """Current process RSS in MB via /proc/self/status (Linux). Returns -1 elsewhere."""
    try:
        with open("/proc/self/status") as _f:
            for _line in _f:
                if _line.startswith("VmRSS:"):
                    return int(_line.split()[1]) / 1024.0
    except Exception:
        pass
    return -1.0


class _DebugLog:
    """Per-run debug log: elapsed time + RSS at each pass boundary."""

    def __init__(self, path: Path | None) -> None:
        self._f = open(path, "w", buffering=1) if path else None
        self._t0 = time.monotonic()

    def log(self, msg: str) -> None:
        if self._f is None:
            return
        elapsed = time.monotonic() - self._t0
        rss = _rss_mb()
        rss_str = f"{rss:.0f}MB" if rss >= 0 else "n/a"
        self._f.write(f"[{elapsed:8.2f}s  RSS={rss_str:>8}]  {msg}\n")

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tapematch")
    ap.add_argument("root", help="processing folder (one subfolder per source)")
    ap.add_argument("--config", default=str(Path(__file__).parent.parent / "config.yaml"))
    ap.add_argument("--no-trim", action="store_true", help="skip head/tail trim")
    ap.add_argument("--json-out", default=None,
                    help="write structured results JSON to this path")
    ap.add_argument("--set-offset", default=None, metavar="HH:MM:SS",
                    help="clip all sources to start at this offset (HH:MM:SS or decimal "
                         "seconds) before analysis; use when recordings include non-target "
                         "material before the show (e.g. co-headline concerts where the "
                         "target set starts mid-recording)")
    ap.add_argument("--debug-log", default=None, metavar="PATH",
                    help="write per-pass timing and RSS to this file")
    args = ap.parse_args(argv)

    def _parse_offset(s: str) -> float:
        if ":" in s:
            parts = s.split(":")
            return sum(float(p) * 60 ** (len(parts) - 1 - i) for i, p in enumerate(parts))
        return float(s)
    set_offset_sec: float | None = _parse_offset(args.set_offset) if args.set_offset else None

    cfg = yaml.safe_load(open(args.config))
    sr = cfg["audio"]["analysis_sr"]
    exts = cfg["ingest"]["audio_exts"]

    root = Path(args.root)
    sources = ingest.discover_sources(root)
    if not sources:
        print(f"no source subfolders in {root}", file=sys.stderr); return 1

    dbg = _DebugLog(Path(args.debug_log) if args.debug_log else None)
    atexit.register(dbg.close)
    dbg.log(f"START  n_sources={len(sources)}  sr={sr}  analysis_sr={sr}")

    # Temp dir for trimmed-mono memmaps — auto-deleted on normal exit.
    # Uses /mnt/DATA0/tmp to avoid filling the system tmpfs (~438 MB per source).
    _tmp_base = Path("/mnt/DATA0/tmp")
    _tmp_base.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="tapematch_", dir=_tmp_base))
    atexit.register(shutil.rmtree, tmp_dir, ignore_errors=True)

    # === Pass 1: ingest + trim + write trimmed mono to disk as memmap ===
    # Always ingests as mono (stereo never needed — all downstream phases use
    # mono memmaps).  Peak RAM per source: stream (~461 MB mono for a 2h show
    # at 16 kHz) + STFT chunk bufs (~38 MB).  performance_envelope's to_mono()
    # returns a zero-cost view when the stream is already mono, eliminating the
    # ~461 MB stereo-→-mono copy that previously pushed peak to ~1.2 GB.
    # The trimmed slice is written directly to the memmap via a view (no third
    # array); stream is freed before moving to the next source.
    print("=== INGEST / TRIM ===")
    trim_bounds: dict[str, tuple[float, float, float]] = {}
    mono_paths: dict[str, tuple[Path, int]] = {}  # name -> (path, n_samples)

    for name, sdir in sources.items():
        rep = ingest.source_report(sdir, exts)
        print(f"  {name}: {rep['n_tracks']} tracks, {fmt_hms(rep['total_sec'])}")
        stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)

        if set_offset_sec:
            off_samp = min(int(set_offset_sec * sr), max(0, len(stream) - sr))
            stream = stream[off_samp:]

        stream_dur = len(stream) / sr
        if args.no_trim:
            s0, s1 = 0.0, stream_dur
        else:
            s0, s1 = trim.performance_envelope(stream, sr, cfg)
        trim_bounds[name] = (s0, s1, stream_dur)

        # stream has shape (N, 1) from mono ingest; ravel() is a zero-copy view.
        # Write trimmed slice directly to memmap — no intermediate heap copy.
        a, b = int(s0 * sr), int(s1 * sr)
        n = b - a
        mpath = tmp_dir / f"{name}.f32"
        mm = np.memmap(str(mpath), dtype="float32", mode="w+", shape=(n,))
        mm[:] = stream[a:b].ravel()
        mm.flush()
        mono_paths[name] = (mpath, n)
        del stream, mm
        dbg.log(f"INGEST  {name}  mmap_mb={mpath.stat().st_size / 1048576:.1f}")

    dbg.log(f"PASS1_DONE  n_sources={len(mono_paths)}")

    # Persist trim metadata for re-runs / resume.
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

    # Duration outlier detection — flag recordings significantly shorter or longer
    # than the group median.  Short = missing material; long = duplicate tracks in
    # subfolders (e.g. "fixed tracks" copies) inflating the ingested stream.
    perf_durs = {n: (s1 - s0) for n, (s0, s1, _) in trim_bounds.items()}
    med_dur = float(np.median(list(perf_durs.values())))
    short_flag = {n: d for n, d in perf_durs.items() if d < med_dur * 0.95}
    long_flag  = {n: d for n, d in perf_durs.items() if d > med_dur * 1.30}
    if short_flag and not args.no_trim:
        print(f"\n  [INCOMPLETE?] — duration well below group median ({fmt_hms(med_dur)}):")
        for n, d in short_flag.items():
            pct = 100.0 * (med_dur - d) / med_dur
            print(f"    {n}: {fmt_hms(d)} ({pct:.1f}% shorter)")
    if long_flag and not args.no_trim:
        print(f"\n  [INFLATED?] — duration well above group median ({fmt_hms(med_dur)}):")
        for n, d in long_flag.items():
            pct = 100.0 * (d - med_dur) / med_dur
            print(f"    {n}: {fmt_hms(d)} ({pct:.1f}% longer) — possible duplicate tracks in subfolders")

    def _mmap(name: str) -> np.ndarray:
        """Open the trimmed-mono memmap for a source (read-only)."""
        mpath, n = mono_paths[name]
        return np.memmap(str(mpath), dtype="float32", mode="r", shape=(n,))

    # Reference starts as first source; re-selected after matrix is computed.
    ref_name = next(iter(trim_bounds))

    # === Anchors: open ref memmap; pick_anchors streams it in 1-min chunks ===
    ref_mono = _mmap(ref_name)
    anchors = align.pick_anchors(ref_mono, sr, cfg)
    print(f"\n=== ANCHORS (ref={ref_name}) ===")
    print("  " + ", ".join(fmt_hms(a) for a in anchors))
    dbg.log(f"ANCHORS  ref={ref_name}  n={len(anchors)}")

    # === Lag curves: ref_mono stays as memmap; one other source at a time ===
    print("\n=== LAG CURVES / SPEED (vs ref) ===")
    dbg.log("LAG_CURVES_START")
    ppm_thr = cfg["align"]["ratio_flag_ppm"]
    speed_info: dict[str, dict] = {ref_name: {"kind": "reference", "ppm": 0.0, "ratio": 1.0}}
    for name, (s0, s1, _) in trim_bounds.items():
        if name == ref_name:
            continue
        other_mono = _mmap(name)
        ratio = match.estimate_ratio(ref_mono, other_mono, sr, anchors, cfg)
        ppm = (ratio - 1.0) * 1e6
        rows = align.lag_curve(ref_mono, other_mono, sr, anchors, cfg)
        d = align.interpret_curve(rows, cfg)
        kind = d["kind"]
        if abs(ppm) > ppm_thr:
            kind = "constant-speed-offset"
        elif kind == "constant-speed-offset":
            kind = "aligned"
        speed_info[name] = {"kind": kind, "ppm": ppm, "ratio": ratio}
        print(f"  {ref_name}->{name}: {kind}  speed ratio={ratio:.6f} ({ppm:+.0f} ppm)")
        if kind == "staircase/splice":
            print(f"    ^ discontinuous lag curve — staircase pattern (CDR re-tracking or tape edits)")
        del other_mono

    # === Residual correlation matrix: one pair at a time ===
    # Memmaps keep process heap near zero for most pairs; only rj_c (a
    # resampled copy, ~438 MB) temporarily lands in heap when speed differs.
    print("\n=== RESIDUAL CORRELATION MATRIX ===")
    names = list(trim_bounds.keys())
    n_src = len(names)
    M = np.eye(n_src)
    a_cfg = cfg["align"]
    win = cfg["anchors"]["window_sec"]
    ref_idx = names.index(ref_name)
    pair_ratios: dict[tuple[int, int], float] = {}  # (i,j) i<j -> speed ratio
    dbg.log(f"MATRIX_START  n_src={n_src}  n_pairs={n_src*(n_src-1)//2}")

    for i in range(n_src - 1):
        ri = ref_mono if i == ref_idx else _mmap(names[i])
        for j in range(i + 1, n_src):
            rj = ref_mono if j == ref_idx else _mmap(names[j])
            ratio = match.estimate_ratio(ri, rj, sr, anchors, cfg)
            pair_ratios[(i, j)] = ratio
            ppm_val = (ratio - 1.0) * 1e6
            if abs(ppm_val) > ppm_thr:
                dbg.log(f"RESAMPLE  {names[i]}/{names[j]}  ratio={ratio:.6f}  ppm={ppm_val:+.0f}")
            rj_c = resample_ratio(rj, ratio, sr) if abs(ratio - 1.0) * 1e6 > ppm_thr else rj
            corrs = []
            for ctr in anchors:
                lag, _ = align.local_lag(ri, rj_c, sr, ctr, win, a_cfg["max_lag_sec"])
                if lag is None:
                    continue
                ra, ob = match.aligned_window(ri, rj_c, sr, ctr, win, lag)
                corrs.append(abs(match.residual_corr(ra, ob)))
            M[i, j] = M[j, i] = float(np.median(corrs)) if corrs else 0.0
            if rj_c is not rj:
                del rj_c
            if j != ref_idx:
                del rj
        if i != ref_idx:
            del ri

    dbg.log("MATRIX_DONE")

    def _label(name: str) -> str:
        """Extract 'LB-NNNNN' from folder name, or fall back to first 8 chars."""
        import re as _re
        m = _re.search(r"LB-\d+", name)
        return m.group(0) if m else name[:8]

    labels = [_label(n) for n in names]
    hdr = "          " + "  ".join(f"{lb:>8}" for lb in labels)
    print(hdr)
    for i, lb in enumerate(labels):
        row = "  ".join(f"{M[i,j]:8.3f}" for j in range(n_src))
        print(f"  {lb:>8}  {row}")

    # === Secondary match: windowed coverage + quiet-segment hiss ===
    # Only computed for cross-family pairs (primary M below threshold) to save time.
    # Catches remasters whose edits are confined to track boundaries, leaving
    # within-track audio coherent, and recordings whose music correlation is broken
    # by EQ/NR but whose tape hiss / crowd noise texture still matches.
    W = np.zeros((n_src, n_src))           # windowed coverage fractions
    H = np.zeros((n_src, n_src))           # quiet-segment hiss fractions
    H_med = np.zeros((n_src, n_src))       # quiet-segment hiss medians (guard vs room ambience)
    FP = np.zeros((n_src, n_src))          # fingerprint Dice scores
    sec_results: dict[tuple[int, int], dict] = {}

    # === Fingerprint: compute for all sources upfront (10-min window each, cheap) ===
    fp_hashes: dict[str, set] = {}
    if "fingerprint" in cfg:
        dbg.log("FINGERPRINT_START")
        for name in names:
            fp_mono = _mmap(name)
            fp_hashes[name] = match.fingerprint_window(fp_mono, sr, cfg)
            del fp_mono

    if "secondary_match" in cfg:
        m_thr = cfg["match"]["cluster_threshold"]
        cross_pairs = [
            (i, j)
            for i in range(n_src - 1)
            for j in range(i + 1, n_src)
            if M[i, j] < m_thr
        ]
        dbg.log(f"SECONDARY_START  cross_pairs={len(cross_pairs)}")
        if cross_pairs:
            print(f"\n=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===")
            print(f"  {len(cross_pairs)} cross-family pair(s) — computing secondary evidence ...")
            for i, j in cross_pairs:
                ri = ref_mono if i == ref_idx else _mmap(names[i])
                rj = ref_mono if j == ref_idx else _mmap(names[j])
                # Do NOT apply resample_ratio before secondary_corr_pair.
                # resample_poly smears the HF fine-structure that residual_corr
                # relies on, killing correlation even for same-source pairs.
                # The per-window local lag search absorbs accumulated drift.
                sec = match.secondary_corr_pair(ri, rj, sr, cfg)

                # Staircase fallback: when either recording has CDR re-tracking edits
                # and the standard 60s windows scored near-zero, retry with shorter
                # windows (default 15s) to reduce the chance of an edit-point boundary
                # landing mid-window and breaking per-window lag alignment.
                ki = speed_info.get(names[i], {}).get("kind", "")
                kj = speed_info.get(names[j], {}).get("kind", "")
                if (sec["windowed_frac"] < 0.10
                        and ("staircase" in ki or "staircase" in kj)
                        and "short_window_sec" in cfg.get("secondary_match", {})):
                    sm = cfg["secondary_match"]
                    short_cfg = {**cfg, "secondary_match": {
                        **sm,
                        "window_sec": sm["short_window_sec"],
                        "hop_sec": sm.get("short_hop_sec", sm["short_window_sec"] / 3),
                    }}
                    sec_short = match.secondary_corr_pair(ri, rj, sr, short_cfg)
                    if sec_short["windowed_frac"] > sec["windowed_frac"]:
                        sec = {**sec,
                               "windowed_frac": sec_short["windowed_frac"],
                               "windowed_median": sec_short["windowed_median"],
                               "n_windows": sec_short["n_windows"]}

                fp_score = (match.fingerprint_score(fp_hashes[names[i]], fp_hashes[names[j]])
                            if fp_hashes else 0.0)
                sec["fp_score"] = fp_score
                sec_results[(i, j)] = sec
                W[i, j] = W[j, i] = sec["windowed_frac"]
                H[i, j] = H[j, i] = sec["hiss_frac"]
                H_med[i, j] = H_med[j, i] = sec["hiss_median"]
                FP[i, j] = FP[j, i] = fp_score
                if i != ref_idx:
                    del ri
                if j != ref_idx and rj is not ref_mono:
                    del rj

            wc_thr = cfg["secondary_match"]["coverage_threshold"]
            hf_thr = cfg["secondary_match"]["hiss_frac_threshold"]
            hm_thr = cfg["secondary_match"].get("hiss_merge_frac", 1.0)
            hm_med_thr = cfg["secondary_match"].get("hiss_merge_median", 1.0)
            fp_display_thr = cfg.get("fingerprint", {}).get("match_threshold", 1.0)
            fp_cluster_thr = cfg.get("fingerprint", {}).get("cluster_threshold", 0.0)
            hits = [
                (i, j, sec_results[(i, j)])
                for i, j in cross_pairs
                if sec_results[(i, j)]["windowed_frac"] >= wc_thr
                or sec_results[(i, j)]["hiss_frac"] >= hf_thr
                or sec_results[(i, j)]["fp_score"] >= min(fp_display_thr,
                                                          fp_cluster_thr or fp_display_thr)
            ]
            if hits:
                for i, j, sec in hits:
                    a, b = names[i], names[j]
                    parts = []
                    if sec["windowed_frac"] >= wc_thr:
                        parts.append(f"windowed {sec['windowed_frac']:.2f} "
                                     f"({sec['n_windows']} win, med {sec['windowed_median']:.3f})")
                    if sec["hiss_frac"] >= hf_thr:
                        parts.append(f"hiss {sec['hiss_frac']:.2f} "
                                     f"({sec['n_hiss_segs']} segs, med {sec['hiss_median']:.3f})")
                    fp_show_thr = fp_cluster_thr if fp_cluster_thr > 0.0 else fp_display_thr
                    if sec["fp_score"] >= fp_show_thr:
                        ha = len(fp_hashes.get(names[i], set()))
                        hb = len(fp_hashes.get(names[j], set()))
                        parts.append(f"fingerprint Dice {sec['fp_score']:.3f} "
                                     f"({ha} / {hb} hashes)")
                    evidence = "; ".join(parts)
                    will_merge = (
                        sec["windowed_frac"] >= wc_thr
                        or (sec["hiss_frac"] >= hm_thr and sec["hiss_median"] >= hm_med_thr)
                        or (fp_cluster_thr > 0.0 and sec["fp_score"] >= fp_cluster_thr)
                    )
                    tag = "→ SECONDARY LINK" if will_merge else "→ hiss evidence (below merge threshold)"
                    print(f"  {_label(a)} / {_label(b)}: {evidence}  "
                          f"[primary corr {M[i,j]:.3f}] {tag}")
            else:
                print(f"  No secondary same-source evidence found.")

    # === Re-select reference as the most central source (highest row-sum in M) ===
    # The alphabetical first source may be an outlier (e.g. a bootleg CD).
    # After the full matrix is computed we know the true structure — pick the
    # source most similar to all others, excluding INCOMPLETE/INFLATED sources
    # (their duration problems mean anchors and lag curves would be misleading).
    row_sums = M.sum(axis=1)
    _eligible = {i for i, n in enumerate(names)
                 if n not in short_flag and n not in long_flag}
    if not _eligible:
        _eligible = set(range(n_src))
    central_idx = max(_eligible, key=lambda i: row_sums[i])
    central_name = names[central_idx]
    if central_name != ref_name:
        print(f"\n=== LAG CURVES / SPEED (re-run vs central ref={central_name}) ===")
        ref_mono = _mmap(central_name)
        anchors  = align.pick_anchors(ref_mono, sr, cfg)
        print("  anchors: " + ", ".join(fmt_hms(a) for a in anchors))
        speed_info = {central_name: {"kind": "reference", "ppm": 0.0, "ratio": 1.0}}
        for name in names:
            if name == central_name:
                continue
            other_mono = _mmap(name)
            ratio = match.estimate_ratio(ref_mono, other_mono, sr, anchors, cfg)
            ppm   = (ratio - 1.0) * 1e6
            rows  = align.lag_curve(ref_mono, other_mono, sr, anchors, cfg)
            d     = align.interpret_curve(rows, cfg)
            kind  = d["kind"]
            if abs(ppm) > ppm_thr:
                kind = "constant-speed-offset"
            elif kind == "constant-speed-offset":
                kind = "aligned"
            speed_info[name] = {"kind": kind, "ppm": ppm, "ratio": ratio}
            print(f"  {central_name}->{name}: {kind}  speed ratio={ratio:.6f} ({ppm:+.0f} ppm)")
            if kind == "staircase/splice":
                print(f"    ^ discontinuous lag curve — staircase pattern (CDR re-tracking or tape edits)")
            del other_mono
        ref_name = central_name

    print("\n=== CLUSTERS ===")
    m_thr = cfg["match"]["cluster_threshold"]
    wc_thr = cfg.get("secondary_match", {}).get("coverage_threshold", 0.0) if sec_results else 0.0
    hm_thr = cfg.get("secondary_match", {}).get("hiss_merge_frac", 1.0) if sec_results else 1.0
    hm_med_thr = cfg.get("secondary_match", {}).get("hiss_merge_median", 1.0) if sec_results else 1.0
    # Fingerprint clustering uses cluster_threshold (safe with hf_band_hz restriction).
    # When hf_band_hz is not configured, cluster_threshold should not be set — full-band
    # fingerprint different-source same-show pairs reach 0.15–0.50, below the safe 0.60
    # display threshold but above any clustering threshold that would be useful.
    fp_thr = cfg.get("fingerprint", {}).get("match_threshold", 0.0) if fp_hashes else 0.0
    fp_cluster_thr = cfg.get("fingerprint", {}).get("cluster_threshold", 0.0) if fp_hashes else 0.0
    groups = match.cluster(names, M, m_thr,
                           W=W if sec_results else None, w_threshold=wc_thr,
                           H=H if sec_results else None, h_threshold=hm_thr,
                           H_med=H_med if sec_results else None, h_med_threshold=hm_med_thr,
                           F=FP if fp_cluster_thr > 0.0 else None,
                           f_threshold=fp_cluster_thr)
    for gi, g in enumerate(groups, 1):
        intra_pairs = [(a, b) for a in g for b in g if a < b]
        intra_corrs = [M[names.index(a), names.index(b)] for a, b in intra_pairs]
        mc = float(np.mean(intra_corrs)) if intra_corrs else 1.0
        # fp-linked: every sub-threshold pair was bridged by fingerprint, not primary STFT.
        # "low confidence" would mislead when a Dice score of 0.55+ is the actual evidence.
        fp_linked = (
            fp_cluster_thr > 0.0
            and bool(intra_pairs)
            and mc < m_thr
            and all(
                M[names.index(a2), names.index(b2)] >= m_thr
                or FP[names.index(a2), names.index(b2)] >= fp_cluster_thr
                for a2, b2 in intra_pairs
            )
        )
        conf = (
            " [fp-linked]" if fp_linked
            else (f" [{match.cluster_confidence(mc)} confidence]" if intra_pairs else "")
        )
        # Identify any secondary-linked pairs within this family
        sec_links = []
        for a, b in intra_pairs:
            i, j = min(names.index(a), names.index(b)), max(names.index(a), names.index(b))
            if M[i, j] < m_thr and (i, j) in sec_results:
                sec = sec_results[(i, j)]
                wf = sec["windowed_frac"]
                hf = sec["hiss_frac"]
                evidence = []
                if wc_thr > 0.0 and wf >= wc_thr:
                    evidence.append(f"windowed {wf:.2f}")
                h_thr2 = cfg.get("secondary_match", {}).get("hiss_frac_threshold", 1.0)
                if h_thr2 and hf >= h_thr2:
                    evidence.append(f"hiss {hf:.2f}")
                fp_s = sec.get("fp_score", 0.0)
                if fp_cluster_thr > 0.0 and fp_s >= fp_cluster_thr:
                    evidence.append(f"fp {fp_s:.3f}")
                if evidence:
                    sec_links.append(f"{_label(a)}/{_label(b)} via {'+'.join(evidence)}")
        sec_note = f"  [secondary: {'; '.join(sec_links)}]" if sec_links else ""
        # Flag pairs in a 3+ member family that have no direct evidence (primary or
        # secondary) — they are only linked transitively through a third member.
        chain_notes = []
        if len(g) >= 3:
            for a2, b2 in intra_pairs:
                ia2, ib2 = names.index(a2), names.index(b2)
                i2, j2 = min(ia2, ib2), max(ia2, ib2)
                direct = (
                    M[i2, j2] >= m_thr
                    or (bool(sec_results) and W[i2, j2] >= wc_thr)
                    or (bool(sec_results) and H[i2, j2] >= hm_thr
                        and H_med[i2, j2] >= hm_med_thr)
                    or (fp_cluster_thr > 0.0 and FP[i2, j2] >= fp_cluster_thr)
                )
                if not direct:
                    chain_notes.append(f"{_label(a2)}/{_label(b2)}")
        chain_note = (f"  [chain-unverified: {'; '.join(chain_notes)} not directly confirmed]"
                      if chain_notes else "")
        print(f"  Family {gi}: {', '.join(g)}  (mean intra-corr {mc:.3f}{conf}){sec_note}{chain_note}")
    print(f"  Distinct source families: {len(groups)}")

    # === Lineage: mono memmap per source; welch PSD uses only a few MB ===
    print("\n=== LINEAGE EVIDENCE (interpret manually) ===")
    dbg.log(f"LINEAGE_START  n_families={len(groups)}")
    print(f"  {'source':>8}  {'HF ceiling':>11}  {'noise floor':>11}  {'DC asymmetry':>12}")
    capped = False
    lineage_results: dict[str, dict] = {}
    for name in trim_bounds:
        mono = _mmap(name)
        ev = match.lineage_evidence(mono, sr, cfg)
        lineage_results[name] = ev
        capped = capped or ev["nyquist_capped"]
        print(f"  {name:>8}  {ev['hf_ceiling_hz']/1000:8.1f}kHz  "
              f"{ev['noise_floor_db']:9.1f}dB  "
              f"{ev['asymmetry_dc']:+12.5f}")
        del mono

    if capped:
        print(f"  (HF ceiling capped by {sr//2} Hz Nyquist at analysis_sr={sr}; "
              f"run lineage at native rate for real format discrimination)")
    print(f"  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)")

    # === Diagnostics: cross-reference speed, lineage, duration, and clusters ===
    print("\n=== DIAGNOSTICS ===")
    from collections import defaultdict
    diag_lines: list[str] = []

    # 1. Incomplete / inflated recordings: duration outliers vs group median.
    for n, d in short_flag.items():
        pct = 100.0 * (med_dur - d) / med_dur
        diag_lines.append(
            f"  [INCOMPLETE] {n}: {fmt_hms(d)} vs median {fmt_hms(med_dur)} "
            f"({pct:.1f}% shorter) — likely missing material"
        )
    for n, d in long_flag.items():
        pct = 100.0 * (d - med_dur) / med_dur
        diag_lines.append(
            f"  [INFLATED] {n}: {fmt_hms(d)} vs median {fmt_hms(med_dur)} "
            f"({pct:.1f}% longer) — check for duplicate tracks in subfolders; "
            f"correlation results for this source are unreliable"
        )

    # 2. Cross-family pairs with large performance-duration mismatch.
    # When recordings differ by >8 minutes, the accumulated timing drift between
    # corresponding segments can exceed the alignment search window (max_lag_sec),
    # causing anchor lag estimates to fail silently and correlation to collapse to ~0.
    # This does NOT mean they are different tapes — it means automatic detection
    # is unreliable for this pair; manual comparison is needed.
    # 8 min threshold avoids noise from normal AUD variation (crowd intro length,
    # fade-in timing) which routinely differs by 3–6 min between independent tapers.
    # Pairs where at least one member is already flagged INCOMPLETE or INFLATED are
    # suppressed: the duration anomaly is the obvious cause and the existing flag suffices.
    TIMING_MISMATCH_MIN_SEC = 8.0 * 60
    for gi1, g1 in enumerate(groups, 1):
        for gi2, g2 in enumerate(groups, 1):
            if gi1 >= gi2:
                continue
            for a in g1:
                for b in g2:
                    if a in short_flag or b in short_flag:
                        continue  # INCOMPLETE already explains the gap
                    if a in long_flag or b in long_flag:
                        continue  # INFLATED already flagged; timing diff is expected
                    dur_a = perf_durs[a]
                    dur_b = perf_durs[b]
                    diff = abs(dur_a - dur_b)
                    if diff < TIMING_MISMATCH_MIN_SEC:
                        continue
                    i2 = min(names.index(a), names.index(b))
                    j2 = max(names.index(a), names.index(b))
                    if M[i2, j2] >= 0.05:
                        continue  # correlation is non-trivial; not a lag failure
                    diag_lines.append(
                        f"  [TIMING MISMATCH] {a} / {b}: "
                        f"performance {fmt_hms(dur_a)} vs {fmt_hms(dur_b)} "
                        f"({diff/60:.1f} min difference) — timing drift may exceed "
                        f"alignment window; correlation unreliable if same-source"
                    )

    # 3. Singleton with speed offset: distinguish remaster (moderate cross-corr + HF match)
    #    from a fully distinct source (near-zero corr to everything).
    REMASTER_MIN_CORR = 0.20   # below this the HF ceiling match is coincidental
    for g in groups:
        if len(g) != 1:
            continue
        name = g[0]
        si = speed_info.get(name, {})
        if abs(si.get("ppm", 0.0)) <= ppm_thr:
            continue
        # Best correlation to any other source
        best_any = max(
            M[names.index(name), names.index(other)]
            for other in names if other != name
        )
        if best_any < REMASTER_MIN_CORR:
            diag_lines.append(
                f"  [DISTINCT SOURCE] {name} ({si['ppm']:+.0f} ppm speed offset, "
                f"best cross-family corr {best_any:.3f}): "
                f"near-zero correlation to all other sources — entirely different recording"
            )
            continue
        my_hf = lineage_results[name]["hf_ceiling_hz"]
        for gi, og in enumerate(groups, 1):
            if name in og:
                continue
            matching = [m for m in og
                        if abs(lineage_results[m]["hf_ceiling_hz"] - my_hf) < 1000]
            if not matching:
                continue
            best_corr = max(M[names.index(name), names.index(m)] for m in og)
            diag_lines.append(
                f"  [REMASTER?] {name} ({si['ppm']:+.0f} ppm speed offset): "
                f"HF ceiling {my_hf/1000:.1f} kHz matches Family {gi} "
                f"({', '.join(matching)}); best cross-family corr {best_corr:.3f} "
                f"— EQ/processing may have broken audio correlation"
            )

    # 4. Secondary-linked same-source pairs (grouped via windowed/hiss, not primary corr).
    for gi, g in enumerate(groups, 1):
        for a in g:
            for b in g:
                if a >= b:
                    continue
                i, j = min(names.index(a), names.index(b)), max(names.index(a), names.index(b))
                if M[i, j] >= m_thr:
                    continue  # primary link, handled by confidence check below
                if (i, j) not in sec_results:
                    continue
                sec = sec_results[(i, j)]
                wf = sec["windowed_frac"]
                hf = sec["hiss_frac"]
                fps = sec.get("fp_score", 0.0)
                w_thr2 = cfg.get("secondary_match", {}).get("coverage_threshold", 1.0)
                h_thr2 = cfg.get("secondary_match", {}).get("hiss_frac_threshold", 1.0)
                f_thr2 = cfg.get("fingerprint", {}).get("cluster_threshold", 0.0) or \
                         cfg.get("fingerprint", {}).get("match_threshold", 1.0)
                if wf >= w_thr2 or hf >= h_thr2 or fps >= f_thr2:
                    parts = []
                    if wf >= w_thr2:
                        parts.append(f"windowed coverage {wf:.2f} ({sec['n_windows']} win)")
                    if hf >= h_thr2:
                        parts.append(f"hiss frac {hf:.2f} ({sec['n_hiss_segs']} segs)")
                    if fps >= f_thr2:
                        parts.append(f"fingerprint Dice {fps:.3f}")
                    # Distinguish probable NR (music windows match, quiet-segment hiss
                    # does NOT) from a remaster/edit (primary corr degraded overall).
                    hiss_med = sec.get("hiss_median", 1.0)
                    if M[i, j] < 0.05 and wf >= 0.70 and hiss_med < 0.20:
                        note = "noise reduction likely applied (music aligns, hiss does not)"
                    else:
                        note = "likely remaster or heavily edited copy of same tape"
                    diag_lines.append(
                        f"  [SECONDARY SAME-SOURCE] {a} / {b}: "
                        f"{'; '.join(parts)} — primary corr {M[i,j]:.3f} (below threshold); "
                        f"{note}"
                    )

    # 5. Medium/low-confidence family pairs: same source likely but processing degraded the corr.
    for gi, g in enumerate(groups, 1):
        pairs = [(a, b, M[names.index(a), names.index(b)])
                 for a in g for b in g if a < b]
        for a, b, c in pairs:
            i2, j2 = min(names.index(a), names.index(b)), max(names.index(a), names.index(b))
            if (i2, j2) in sec_results and M[i2, j2] < m_thr:
                continue  # already reported as [SECONDARY SAME-SOURCE]
            conf = match.cluster_confidence(c)
            if conf != "high":
                diag_lines.append(
                    f"  [{conf.upper()} CONFIDENCE] Family {gi} ({a} / {b}): "
                    f"corr {c:.3f} — same source likely but significant processing "
                    f"(resampling, level boost, EQ) may explain reduced correlation"
                )

    # 6. Shared HF ceiling spanning multiple source families: recordings share a
    #    recording chain or format even though audio correlation says different source.
    #    Only meaningful when ceilings are above 75% of Nyquist — below that the
    #    reading is capped by the analysis sample rate, not the recording chain.
    nyquist_hz = sr / 2
    hf_meaningful_min = nyquist_hz * 0.75
    hf_buckets: dict[float, list[str]] = defaultdict(list)
    for name in names:
        bucket = round(lineage_results[name]["hf_ceiling_hz"] / 1000) * 1000
        hf_buckets[float(bucket)].append(name)
    for hz, members in sorted(hf_buckets.items()):
        if len(members) < 2:
            continue
        if hz < hf_meaningful_min:
            continue   # ceiling is Nyquist-limited at this analysis_sr; not informative
        member_families = {gi for gi, og in enumerate(groups, 1)
                           if any(m in og for m in members)}
        if len(member_families) > 1:
            diag_lines.append(
                f"  [SHARED HF CEILING] {hz/1000:.1f} kHz group spans "
                f"{len(member_families)} source families: {', '.join(members)} "
                f"— same recording chain or format, but audio correlation says "
                f"different source (visual wav inspection unreliable here)"
            )

    if diag_lines:
        for line in diag_lines:
            print(line)
    else:
        print("  (no anomalies detected)")

    # === Optional structured JSON output for session logging / DB ingestion ===
    if args.json_out:
        source_family: dict[str, int] = {}
        for gi, g in enumerate(groups, 1):
            for nm in g:
                source_family[nm] = gi

        results = {
            "sources": {
                nm: {
                    "track_count": ingest.source_report(root / nm, exts)["n_tracks"],
                    "total_dur_sec": trim_bounds[nm][2],
                    "perf_dur_sec": trim_bounds[nm][1] - trim_bounds[nm][0],
                    "trim_head_sec": trim_bounds[nm][0],
                    "trim_tail_sec": trim_bounds[nm][2] - trim_bounds[nm][1],
                    "hf_ceiling_hz": lineage_results[nm]["hf_ceiling_hz"],
                    "noise_floor_db": lineage_results[nm]["noise_floor_db"],
                    "dc_asymmetry": lineage_results[nm]["asymmetry_dc"],
                    "nyquist_capped": lineage_results[nm]["nyquist_capped"],
                    "speed_ppm": speed_info[nm]["ppm"],
                    "speed_kind": speed_info[nm]["kind"],
                    "family_id": source_family[nm],
                }
                for nm in names
            },
            "correlation_matrix": {
                "names": names,
                "values": M.tolist(),
            },
            "anchors_sec": [float(a) for a in anchors],
            "n_families": len(groups),
            "secondary_matrix": {
                "names": names,
                "windowed_frac": W.tolist(),
                "hiss_frac": H.tolist(),
                "fingerprint_dice": FP.tolist(),
            } if (sec_results or fp_hashes) else None,
            "fingerprint_hash_counts": {
                name: len(fp_hashes[name]) for name in names
            } if fp_hashes else None,
            "secondary_pairs": {
                f"{names[i]}|{names[j]}": sec
                for (i, j), sec in sec_results.items()
            },
            "config": cfg,
        }
        Path(args.json_out).write_text(json.dumps(results, indent=2))

    dbg.log(f"DONE  n_families={len(groups)}")
    dbg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
