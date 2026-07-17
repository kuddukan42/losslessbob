"""tapematch CLI.

    python -m tapematch.cli /path/to/processing --config config.yaml

processing/ contains one subfolder per recording. Output: ingest report,
trim report, lag-curve diagnosis per pair, residual-corr matrix, clusters,
and lineage evidence.
"""
from __future__ import annotations
import argparse, atexit, json, os, shutil, sys, tempfile, time
from pathlib import Path
import numpy as np
import yaml
from . import ingest, trim, align, match, verdict
from .audio import to_mono, resample_ratio
from .ingest import fmt_hms

# NUMBA_CACHE_DIR must be set before the first librosa call (match.pitch_ratio_pyin
# JIT-compiles via numba) -- default numba cache location can be a read-only
# site-packages path. Set once, here, on the tapematch entry path, before any
# pair processing (and therefore before any possible pitch_ratio_pyin call) --
# CC_TAPEMATCH_FIXES.md Task 6.2. setdefault() respects an operator-supplied env var.
os.environ.setdefault("NUMBA_CACHE_DIR", "/mnt/DATA0/tmp/numba_cache")
Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)


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
    ap.add_argument("--lineage-db", default=None, metavar="PATH",
                    help="path to the LosslessBob main DB (entry_lineage table) used for "
                         "the curator-conditional fingerprint threshold (CC_TAPEMATCH_FIXES "
                         "Task 4.1); default auto-detects data/losslessbob.db relative to "
                         "the repo root. Absent/unreadable -> curator conditional stays "
                         "inert (empty lineage set), all other clustering unaffected")
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

    # Curator lineage (Task 4.1): load once, read-only, from the LosslessBob main
    # DB's entry_lineage table via verdict.load_lineage_pairs — the same helper
    # regression.py's cached harness uses, so a live run and a harness re-score of
    # the same date apply the identical curator-relaxed fingerprint bar. Absent or
    # unreadable DB -> empty set -> fp_threshold() falls through to the staircase/
    # base threshold for every pair (inert, never crashes the run).
    lineage_db_path = (Path(args.lineage_db) if args.lineage_db
                       else Path(__file__).parent.parent.parent.parent / "data" / "losslessbob.db")
    lineage_pairs: set[tuple[int, int]] = set()
    if lineage_db_path.exists():
        try:
            lineage_pairs = verdict.load_lineage_pairs(lineage_db_path)
        except Exception as exc:  # noqa: BLE001 - any DB hiccup must not abort the run
            print(f"  [lineage] could not read {lineage_db_path}: {exc} "
                  f"-- curator conditional threshold inert this run", file=sys.stderr)
    print(f"  curator lineage pairs loaded: {len(lineage_pairs)} "
          f"({'from ' + str(lineage_db_path) if lineage_pairs else 'none -- inert'})")

    root = Path(args.root)
    sources = ingest.discover_sources(root)
    if not sources:
        print(f"no source subfolders in {root}", file=sys.stderr); return 1

    # Drop sources with an undecodable track up front so one corrupt/placeholder
    # file doesn't abort the whole run -- the remaining sources can still be
    # ingested and compared.
    good_sources = {}
    for name, sdir in sources.items():
        try:
            ingest.source_report(sdir, exts)
        except ingest.UnreadableSourceError as e:
            print(f"  [SKIP] source excluded: unreadable file {e.track}", file=sys.stderr)
            continue
        good_sources[name] = sdir
    sources = good_sources
    if len(sources) < 2:
        print(f"Need >=2 readable source subfolders in {root} "
              f"(after excluding unreadable sources)", file=sys.stderr)
        return 1

    dbg = _DebugLog(Path(args.debug_log) if args.debug_log else None)
    atexit.register(dbg.close)

    # Pre-run RAM estimate from probed durations (header reads only, no decode).
    # Each source's mono float32 stream is sr*4 bytes/sec. This is a rough
    # order-of-magnitude lower bound (2x the largest source + fixed STFT/
    # secondary chunk-buffer overhead), not a hard cap: actual peak RSS also
    # grows with source count, since memmap pages touched during the n^2
    # matrix/secondary passes accumulate in the page cache. Calibration runs:
    # 3 sources/3 pairs (1993-04-16) -> est 1.3 GB, actual peak 2.3 GB;
    # 8 sources/28 pairs (1994-02-20) -> est 1.4 GB, actual peak 2.6 GB.
    # Both are far below typical available RAM (30+ GB) and complete normally.
    _durs_sec = [ingest.source_report(sdir, exts)["total_sec"] for sdir in sources.values()]
    _max_src_mb = max(_durs_sec) * sr * 4 / 1e6
    _est_peak_mb = 2 * _max_src_mb + 300
    print(f"  est. peak RAM ~{_est_peak_mb / 1024:.1f} GB "
          f"({len(sources)} sources, largest {fmt_hms(max(_durs_sec))})")
    dbg.log(f"START  n_sources={len(sources)}  sr={sr}  analysis_sr={sr}  "
            f"est_peak_mb={_est_peak_mb:.0f}")

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
    # Polarity rescue (TODO-184): when enabled, also decode stereo and persist an
    # L-R "side" memmap per source so the residual matrix can recover a same-source
    # copy whose one channel is polarity-inverted (collapses the L+R mid mixdown).
    # Default OFF; the stereo decode roughly doubles the Pass-1 working set.
    polarity_cfg = cfg.get("polarity", {}) if isinstance(cfg, dict) else {}
    polarity_on = bool(polarity_cfg.get("enabled", False))

    print("=== INGEST / TRIM ===")
    trim_bounds: dict[str, tuple[float, float, float]] = {}
    mono_paths: dict[str, tuple[Path, int]] = {}  # name -> (path, n_samples)
    side_paths: dict[str, tuple[Path, int]] = {}  # name -> (path, n) — stereo only

    for name, sdir in sources.items():
        rep = ingest.source_report(sdir, exts)
        print(f"  {name}: {rep['n_tracks']} tracks, {fmt_hms(rep['total_sec'])}")
        side = None
        if polarity_on:
            # Decode stereo once: mid = channel mean (scale-equivalent to the mono
            # downmix for the scale-invariant residual_corr); side = L-R (None for
            # mono sources, which have no inter-channel difference to invert).
            st, _, _ = ingest.concat_source(sdir, exts, sr, mono=False)
            if st.ndim == 1:
                st = st.reshape(-1, 1)
            stream = st.mean(axis=1, keepdims=True).astype("float32")
            if st.shape[1] >= 2:
                side = (st[:, 0] - st[:, 1]).astype("float32")
            del st
        else:
            stream, _, _ = ingest.concat_source(sdir, exts, sr, mono=True)

        if set_offset_sec:
            off_samp = min(int(set_offset_sec * sr), max(0, len(stream) - sr))
            stream = stream[off_samp:]
            if side is not None:
                side = side[off_samp:]

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
        # Side channel uses the IDENTICAL trim bounds so mid/side stay sample-aligned.
        if side is not None:
            spath = tmp_dir / f"{name}.side.f32"
            sm = np.memmap(str(spath), dtype="float32", mode="w+", shape=(n,))
            sm[:] = side[a:b]
            sm.flush()
            side_paths[name] = (spath, n)
            del sm
        del stream, side, mm
        dbg.log(f"INGEST  {name}  mmap_mb={mpath.stat().st_size / 1048576:.1f}"
                f"{'  +side' if name in side_paths else ''}")

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

    def _mmap_side(name: str):
        """Open the trimmed L-R side memmap for a source, or None (mono/disabled)."""
        if name not in side_paths:
            return None
        spath, n = side_paths[name]
        return np.memmap(str(spath), dtype="float32", mode="r", shape=(n,))

    # CC_TAPEMATCH_FIXES.md Task 5: estimate_ratio_v2 confidence gate + pyin
    # fallback gate, both read from config (orchestrator-added keys; do not
    # hardcode, do not edit config.yaml here).
    ratio_conf_min = float(cfg["align"].get("ratio_confidence_min", 6.0))
    pyin_fallback_on = bool(cfg["align"].get("pyin_fallback", True))
    speed_unknown_count = 0

    def _dur_prior(name_a: str, name_b: str) -> float | None:
        """Duration-ratio prior for estimate_ratio_v2 (Task 5.1).

        Gated off (returns None) when either source's trimmed duration is
        already flagged as an outlier (short_flag = likely missing material,
        long_flag = likely duplicate tracks inflating the stream) -- both
        break the "duration ratio == speed ratio" assumption the same way
        TIMING_MISMATCH/INCOMPLETE do in duration_ratio_prior's own guard.
        """
        diagnostics: set[str] = set()
        if name_a in short_flag or name_b in short_flag:
            diagnostics.add("INCOMPLETE")
        if name_a in long_flag or name_b in long_flag:
            diagnostics.add("INCOMPLETE")
        return match.duration_ratio_prior(perf_durs[name_a], perf_durs[name_b], diagnostics)

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
    # TODO-235: keep each source's anchor lag curve instead of discarding it, so
    # the run output can persist per-segment offset/rate (backend piecewise maps).
    lag_rows_pass1: dict[str, list[dict]] = {}
    for name, (s0, s1, _) in trim_bounds.items():
        if name == ref_name:
            continue
        other_mono = _mmap(name)
        prior = _dur_prior(ref_name, name)
        ratio, ratio_conf = match.estimate_ratio_v2(ref_mono, other_mono, sr, cfg, prior=prior)
        ppm = (ratio - 1.0) * 1e6
        rows = align.lag_curve(ref_mono, other_mono, sr, anchors, cfg)
        lag_rows_pass1[name] = rows
        d = align.interpret_curve(rows, cfg)
        kind = d["kind"]
        if abs(ppm) > ppm_thr:
            kind = "constant-speed-offset"
        elif kind == "constant-speed-offset":
            kind = "aligned"
        # Task 5.3 confidence gate. Staircase classification (from the lag-curve
        # shape, not the ratio search) takes precedence: a staircase pair
        # legitimately has no single global speed ratio, so low v2 confidence
        # there is expected and must not erase the (independently derived,
        # already-validated) staircase diagnosis that drives the short-window
        # secondary fallback.
        if kind != "staircase/splice" and ratio_conf < ratio_conf_min:
            kind = "speed-unknown"
            speed_unknown_count += 1
            dbg.log(f"SPEED_UNKNOWN  {ref_name}/{name}  v2_conf={ratio_conf:.2f} "
                    f"(<{ratio_conf_min})  prior={prior}")
        speed_info[name] = {"kind": kind, "ppm": ppm, "ratio": ratio, "ratio_confidence": ratio_conf}
        conf_note = f"  [conf={ratio_conf:.1f}]" if kind == "speed-unknown" else ""
        print(f"  {ref_name}->{name}: {kind}  speed ratio={ratio:.6f} ({ppm:+.0f} ppm){conf_note}")
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

    refine_cfg = cfg.get("refine", {}) if isinstance(cfg, dict) else {}
    refine_on = bool(refine_cfg.get("enabled", True))
    refine_min_ppm = float(refine_cfg.get("trigger_min_ppm", 2000.0))
    refine_corr_ceiling = float(refine_cfg.get("trigger_corr_ceiling", 0.60))

    polarity_ceiling = float(polarity_cfg.get("rescue_corr_ceiling", 0.60))

    # CC_TAPEMATCH_FIXES.md Task 6.1: closed-form residual correction guards.
    # These are spec-mandated constants (the r² guard is mandatory so staircase
    # lag curves are never "corrected"), not tunable knobs -- config.yaml was
    # not extended with new keys for this task.
    RESIDUAL_R2_MIN = 0.85
    RESIDUAL_PPM_MIN = 50.0
    RESIDUAL_MAX_ITER = 2

    for i in range(n_src - 1):
        ri = ref_mono if i == ref_idx else _mmap(names[i])
        for j in range(i + 1, n_src):
            rj = ref_mono if j == ref_idx else _mmap(names[j])

            # Task 5: prior-centered v2 ratio estimate + confidence gate. Below
            # ratio_confidence_min the ratio is untrusted -- do NOT resample with
            # it; mark the pair speed-unknown (routes to fingerprint via the
            # normal cross_pairs/secondary-match path below, since M[i,j] will
            # stay low) and, only when no duration prior was available either,
            # try the pyin absolute-pitch fallback (Task 6.2).
            prior = _dur_prior(names[i], names[j])
            ratio, ratio_conf = match.estimate_ratio_v2(ri, rj, sr, cfg, prior=prior)
            speed_unknown = ratio_conf < ratio_conf_min

            if speed_unknown:
                speed_unknown_count += 1
                dbg.log(f"SPEED_UNKNOWN  {names[i]}/{names[j]}  v2_conf={ratio_conf:.2f} "
                        f"(<{ratio_conf_min})  prior={prior}")
                ratio = 1.0  # do not resample with the untrusted v2 ratio
                if prior is None and pyin_fallback_on:
                    ratio_pyin, conf_pyin = match.pitch_ratio_pyin(ri, rj, sr, cfg)
                    if conf_pyin > 0.0:
                        dbg.log(f"PYIN_FALLBACK  {names[i]}/{names[j]}  "
                                f"ratio={ratio_pyin:.6f}  conf={conf_pyin:.2f}")
                        ratio = ratio_pyin

            pair_ratios[(i, j)] = ratio
            ppm_val = (ratio - 1.0) * 1e6
            if abs(ppm_val) > ppm_thr:
                dbg.log(f"RESAMPLE  {names[i]}/{names[j]}  ratio={ratio:.6f}  ppm={ppm_val:+.0f}")
            rj_c = resample_ratio(rj, ratio, sr) if abs(ppm_val) > ppm_thr else rj

            # Task 6.1 closed-form residual correction -- PRIMARY path only
            # (never applied before secondary_corr_pair, per WORKFLOW.md), and
            # never for speed-unknown pairs (ratio above is identity/untrusted,
            # so a lag-curve fit against it is meaningless). Memory discipline:
            # only one resampled copy of `rj` is ever heap-resident -- the
            # previous rj_c is deleted before the next corrective resample is
            # created, mirroring the existing single-rj_c-at-a-time pattern.
            if not speed_unknown:
                for _ in range(RESIDUAL_MAX_ITER):
                    rows6 = align.lag_curve(ri, rj_c, sr, anchors, cfg)
                    ppm_res, r2 = align.residual_ppm_from_lag_curve(
                        [(r["center_sec"], r["lag_sec"]) for r in rows6])
                    if not (r2 > RESIDUAL_R2_MIN and abs(ppm_res) > RESIDUAL_PPM_MIN):
                        break
                    new_ratio = ratio * (1.0 + ppm_res * 1e-6)
                    new_rj_c = resample_ratio(rj, new_ratio, sr)
                    if rj_c is not rj:
                        del rj_c
                    rj_c = new_rj_c
                    ratio = new_ratio
                    dbg.log(f"RESIDUAL_CORRECT  {names[i]}/{names[j]}  "
                            f"ppm_res={ppm_res:+.1f}  r2={r2:.3f}  ratio={ratio:.6f}")
                pair_ratios[(i, j)] = ratio
                ppm_val = (ratio - 1.0) * 1e6

            corrs = []
            for ctr in anchors:
                lag, _ = align.local_lag(ri, rj_c, sr, ctr, win, a_cfg["max_lag_sec"])
                if lag is None:
                    continue
                ra, ob = match.aligned_window(ri, rj_c, sr, ctr, win, lag)
                corrs.append(abs(match.residual_corr(ra, ob)))
            med = float(np.median(corrs)) if corrs else 0.0
            if rj_c is not rj:
                del rj_c

            # Lag-slope speed refinement (pre-existing mechanism, untouched):
            # a further safety net on top of Task 6.1 for cases its r² guard
            # rejected (e.g. genuinely staircase pairs) where the raw ppm
            # offset is still large. Self-limiting: only kept if it improves
            # median residual_corr, so it cannot manufacture a false merge and
            # never regresses a pair that Task 6.1 already fixed.
            if (refine_on and abs(ppm_val) >= refine_min_ppm
                    and med < refine_corr_ceiling and len(corrs) >= 3):
                refined_ratio, refined_corrs = match.refine_speed_ratio(
                    ri, rj, sr, anchors, cfg, ratio)
                refined_med = float(np.median(refined_corrs)) if refined_corrs else 0.0
                if refined_med > med:
                    dbg.log(f"REFINE  {names[i]}/{names[j]}  "
                            f"coarse_ppm={ppm_val:+.0f} -> refined_ppm="
                            f"{(refined_ratio - 1.0) * 1e6:+.0f}  "
                            f"corr {med:.3f}->{refined_med:.3f}")
                    med = refined_med
                    pair_ratios[(i, j)] = refined_ratio

            # Channel-polarity rescue (TODO-184): a same-source copy with one
            # channel polarity-inverted collapses on mid-vs-mid; for such a
            # near-zero pair, re-score across the L-R cross terms (each with its
            # own lag lock) and keep it only if it improves — independent sources
            # have no correlated cross term, so this cannot manufacture a merge.
            if polarity_on and med < polarity_ceiling:
                si = _mmap_side(names[i])
                sj = _mmap_side(names[j])
                if si is not None and sj is not None:
                    pratio = pair_ratios[(i, j)]
                    if abs(pratio - 1.0) * 1e6 > ppm_thr:
                        rj_mid_c = resample_ratio(rj, pratio, sr)
                        sj_c = resample_ratio(sj, pratio, sr)
                    else:
                        rj_mid_c, sj_c = rj, sj
                    resc_med, pairing = match.polarity_rescue(
                        ri, si, rj_mid_c, sj_c, sr, anchors, win,
                        a_cfg["max_lag_sec"], med)
                    if resc_med > med:
                        dbg.log(f"POLARITY_RESCUE  {names[i]}/{names[j]}  "
                                f"{pairing}  corr {med:.3f}->{resc_med:.3f}")
                        med = resc_med
                    if rj_mid_c is not rj:
                        del rj_mid_c
                    if sj_c is not sj:
                        del sj_c
                    del si, sj

            M[i, j] = M[j, i] = med
            if j != ref_idx:
                del rj
        if i != ref_idx:
            del ri

    if speed_unknown_count:
        print(f"  {speed_unknown_count} pair(s)/source(s) speed-unknown "
              f"(v2 confidence < {ratio_conf_min}) — routed to fingerprint path only")
    dbg.log(f"MATRIX_DONE  speed_unknown_count={speed_unknown_count}")

    def _label(name: str) -> str:
        """Extract 'LB-NNNNN' from folder name, or fall back to first 8 chars."""
        import re as _re
        m = _re.search(r"LB-\d+", name)
        return m.group(0) if m else name[:8]

    def _lb_num(name: str) -> int | None:
        """Extract the integer LB number from a staged folder name, or None.

        cli.py sees only the folder name staged on disk -- it has no access to
        tapematch_session.py's DB-resolved name->LB mapping (which additionally
        disambiguates folder names that embed a *different* cross-referenced LB
        number, e.g. "... [fixed LB-2204]-LB-10437-v"). This is the same regex
        fallback tapematch_session.py's own `_lb_num_from_folder` uses when its
        DB lookup misses, so it agrees with the harness in the common case; a
        folder whose own number is shadowed by an earlier cross-reference is a
        known, rare gap (curator conditional simply won't key on it live).
        """
        import re as _re
        m = _re.search(r"LB-(\d+)", name)
        return int(m.group(1)) if m else None

    lb_numbers: dict[str, int | None] = {n: _lb_num(n) for n in names}
    labels = [_label(n) for n in names]
    hdr = "          " + "  ".join(f"{lb:>8}" for lb in labels)
    print(hdr)
    for i, lb in enumerate(labels):
        row = "  ".join(f"{M[i,j]:8.3f}" for j in range(n_src))
        print(f"  {lb:>8}  {row}")

    # === Re-select reference as the most central source (highest row-sum in M) ===
    # Computed here (before the secondary match loop) so its lag-curve pass can
    # inform the both-staircase union flags below. Printed later, in its
    # original position, to keep output section order unchanged.
    row_sums = M.sum(axis=1)
    _eligible = {i for i, n in enumerate(names)
                 if n not in short_flag and n not in long_flag}
    if not _eligible:
        _eligible = set(range(n_src))
    central_idx = max(_eligible, key=lambda i: row_sums[i])
    central_name = names[central_idx]

    # Second lag-curve pass vs the central ref (only if different from ref_name).
    speed_info_central: dict[str, dict] = {}
    lag_rows_central: dict[str, list[dict]] = {}
    central_mono = ref_mono
    anchors_central = anchors
    if central_name != ref_name:
        central_mono = _mmap(central_name)
        anchors_central = align.pick_anchors(central_mono, sr, cfg)
        speed_info_central[central_name] = {"kind": "reference", "ppm": 0.0, "ratio": 1.0}
        for name in names:
            if name == central_name:
                continue
            other_mono = _mmap(name)
            prior = _dur_prior(central_name, name)
            ratio, ratio_conf = match.estimate_ratio_v2(central_mono, other_mono, sr, cfg, prior=prior)
            ppm = (ratio - 1.0) * 1e6
            rows = align.lag_curve(central_mono, other_mono, sr, anchors_central, cfg)
            lag_rows_central[name] = rows
            d = align.interpret_curve(rows, cfg)
            kind = d["kind"]
            if abs(ppm) > ppm_thr:
                kind = "constant-speed-offset"
            elif kind == "constant-speed-offset":
                kind = "aligned"
            # Task 5.3 confidence gate (see the initial-ref pass above for why
            # staircase classification takes precedence over "speed-unknown").
            if kind != "staircase/splice" and ratio_conf < ratio_conf_min:
                kind = "speed-unknown"
                speed_unknown_count += 1
                dbg.log(f"SPEED_UNKNOWN  {central_name}/{name}  v2_conf={ratio_conf:.2f} "
                        f"(<{ratio_conf_min})  prior={prior}")
            speed_info_central[name] = {"kind": kind, "ppm": ppm, "ratio": ratio,
                                        "ratio_confidence": ratio_conf}
            del other_mono

    # Both-staircase union flags (CC_TAPEMATCH_FIXES.md Task 5): a source counts
    # as "staircase" if EITHER lag-curve pass (vs the initial ref, or vs the
    # re-selected central ref) classifies it as "staircase/splice". Fixes a
    # reference-ambiguity bug: speed_info[ref_name]["kind"] is always
    # "reference" under a single pass, so a pair involving the current
    # reference source could never be flagged as staircase on that source.
    staircase_sources = align.union_staircase_sources(speed_info, speed_info_central)

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
    # Ratio-invariant triplet fingerprint (Task 7) — same window, computed only
    # when enabled. Populated alongside fp_hashes so each source is mmap'd once.
    tri_hashes: dict[str, set] = {}
    tri_enabled = bool(cfg.get("fingerprint", {}).get("triplet", {}).get("enabled"))
    if "fingerprint" in cfg:
        dbg.log("FINGERPRINT_START")
        for name in names:
            fp_mono = _mmap(name)
            fp_hashes[name] = match.fingerprint_window(fp_mono, sr, cfg)
            if tri_enabled:
                tri_hashes[name] = match.triplet_window(fp_mono, sr, cfg)
            del fp_mono

    # === Lineage pre-pass (moved ahead of clustering AND the secondary-match
    # cross_pairs loop below) ===
    # HF-ceiling / noise-floor / nyquist-capped readings historically weren't
    # computed until the "LINEAGE EVIDENCE" section, well after clustering ran --
    # too late for the lo-fi hiss conditional (Task 4.2) and for spectral-ratio
    # stationarity (CC_TAPEMATCH_ADDON.md Task 3), both of which need per-pair
    # hf_ceiling_hz/noise_floor_db before the cross_pairs loop. Compute once here
    # (same match.lineage_evidence call, same cost, unconditional either way) and
    # have every later section reuse this dict instead of recomputing. Purely a
    # reordering -- no gating change, so behaviour is unaffected.
    dbg.log("LINEAGE_PREPASS_START")
    lineage_results: dict[str, dict] = {}
    for name in trim_bounds:
        mono = _mmap(name)
        lineage_results[name] = match.lineage_evidence(mono, sr, cfg)
        del mono
    dbg.log("LINEAGE_PREPASS_DONE")

    # === Shared-flaw event fingerprint (CC_TAPEMATCH_ADDON.md Task 2) — computed
    # for all sources upfront, full-length (flaws can occur anywhere in a 2h
    # show, unlike the fixed-window landmark fingerprint above). Gated on
    # flaw_fingerprint.enabled so it costs nothing while dormant (config default).
    flaw_events: dict[str, list[tuple[float, str, float]]] = {}
    ff_enabled = bool(cfg.get("flaw_fingerprint", {}).get("enabled"))
    # Spectral-ratio stationarity (CC_TAPEMATCH_ADDON.md Task 3) master switch --
    # checked once here, used inside the cross_pairs loop below. Costs nothing
    # while dormant: the metric call is skipped entirely (None, NULL column).
    stat_enabled = bool(cfg.get("spectral_stationarity", {}).get("enabled"))
    # Band-limited envelope correlation (CC_TAPEMATCH_ADDON.md Task 4) master
    # switch -- same dormant-while-disabled pattern as stat_enabled above.
    env_enabled = bool(cfg.get("envelope_corr", {}).get("enabled"))
    if ff_enabled:
        dbg.log("FLAW_FINGERPRINT_START")
        for name in names:
            fl_mono = _mmap(name)
            th, tt, _tot = trim_bounds[name]
            flaw_events[name] = match.extract_flaw_events(
                fl_mono, sr, cfg, trim_head_sec=th, trim_tail_sec=tt)
            del fl_mono
        dbg.log("FLAW_FINGERPRINT_DONE")

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
            high_ppm_thr = cfg["secondary_match"].get("high_ppm_threshold", 0)
            for i, j in cross_pairs:
                ri = ref_mono if i == ref_idx else _mmap(names[i])
                rj = ref_mono if j == ref_idx else _mmap(names[j])

                # Predicted-lag mode (Task 4): under a large constant speed offset,
                # accumulated drift can exceed local_lag_sec's residual search.
                # lag_0 is the lag at the first anchor; expected_lag(t) extrapolates
                # from there using the pair's speed ratio (pair_ratios, from
                # estimate_ratio above). Only computed when the offset is large
                # enough to matter.
                predicted_lag = None
                pair_ppm = (pair_ratios[(i, j)] - 1.0) * 1e6
                if high_ppm_thr and abs(pair_ppm) >= high_ppm_thr:
                    lag_0, _ = align.local_lag(ri, rj, sr, anchors[0], win, a_cfg["max_lag_sec"])
                    if lag_0 is not None:
                        predicted_lag = {"ppm": pair_ppm, "lag_0": lag_0, "anchor0_sec": anchors[0]}
                        dbg.log(f"PREDICTED_LAG  {names[i]}/{names[j]}  ppm={pair_ppm:+.0f}  "
                                f"lag_0={lag_0:+.2f}s @ anchor0={anchors[0]:.1f}s")

                # Do NOT apply resample_ratio before secondary_corr_pair.
                # resample_poly smears the HF fine-structure that residual_corr
                # relies on, killing correlation even for same-source pairs.
                # The per-window local lag search absorbs accumulated drift.
                sec = match.secondary_corr_pair(ri, rj, sr, cfg, predicted_lag=predicted_lag)

                # Staircase fallback: when either recording has CDR re-tracking edits
                # and the standard 60s windows scored near-zero, retry with shorter
                # windows (default 15s) to reduce the chance of an edit-point boundary
                # landing mid-window and breaking per-window lag alignment.
                # staircase_sources (Task 5) is the union over both lag-curve passes,
                # so a pair involving the current reference source is still correctly
                # flagged when that source is staircase relative to the central ref.
                if (sec["windowed_frac"] < 0.10
                        and (names[i] in staircase_sources or names[j] in staircase_sources)
                        and "short_window_sec" in cfg.get("secondary_match", {})):
                    sm = cfg["secondary_match"]
                    short_cfg = {**cfg, "secondary_match": {
                        **sm,
                        "window_sec": sm["short_window_sec"],
                        "hop_sec": sm.get("short_hop_sec", sm["short_window_sec"] / 3),
                    }}
                    sec_short = match.secondary_corr_pair(ri, rj, sr, short_cfg, predicted_lag=predicted_lag)
                    if sec_short["windowed_frac"] > sec["windowed_frac"]:
                        sec = {**sec,
                               "windowed_frac": sec_short["windowed_frac"],
                               "windowed_median": sec_short["windowed_median"],
                               "n_windows": sec_short["n_windows"]}

                fp_score = (match.fingerprint_score(fp_hashes[names[i]], fp_hashes[names[j]])
                            if fp_hashes else 0.0)
                sec["fp_score"] = fp_score
                # Ratio-invariant triplet Dice (Task 7): None when disabled so the
                # DB column stays NULL and the verdict OR-path is inert.
                sec["fp_triplet_score"] = (
                    match.fingerprint_score(tri_hashes[names[i]], tri_hashes[names[j]])
                    if tri_enabled and tri_hashes else None)

                # Shared-flaw event fingerprint (Task 2.2/2.3): None when disabled
                # so the DB column stays NULL and the verdict OR-path is inert
                # (same dormant pattern as fp_triplet_score above). Coarse offset
                # reuses the predicted-lag anchor-0 lag when already computed
                # (Task 4 high-ppm path); otherwise a single fresh local_lag call
                # -- flaw event sets are sparse, so this is cheap.
                flaw_score_val = flaw_na = flaw_nb = None
                if ff_enabled:
                    ev_i = flaw_events.get(names[i], [])
                    ev_j = flaw_events.get(names[j], [])
                    flaw_na, flaw_nb = len(ev_i), len(ev_j)
                    if predicted_lag is not None:
                        flaw_offset = predicted_lag["lag_0"]
                    else:
                        flaw_lag0, _ = align.local_lag(ri, rj, sr, anchors[0], win,
                                                       a_cfg["max_lag_sec"])
                        flaw_offset = flaw_lag0 if flaw_lag0 is not None else 0.0
                    flaw_score_val = match.flaw_match_score(
                        ev_i, ev_j, pair_ratios[(i, j)], flaw_offset, cfg)
                sec["flaw_match_score"] = flaw_score_val
                sec["flaw_n_events_a"] = flaw_na
                sec["flaw_n_events_b"] = flaw_nb

                # Spectral-ratio stationarity (CC_TAPEMATCH_ADDON.md Task 3): None
                # when disabled so the DB column stays NULL (same dormant pattern
                # as flaw_match_score above). Conjunctive-only signal -- no
                # verdict OR-path; this just persists the metric for Task 5.
                stat_val = None
                if stat_enabled:
                    stat_val = match.spectral_ratio_stationarity(
                        ri, rj, sr, cfg,
                        lineage_results[names[i]]["hf_ceiling_hz"],
                        lineage_results[names[j]]["hf_ceiling_hz"],
                        lineage_results[names[i]]["noise_floor_db"],
                        lineage_results[names[j]]["noise_floor_db"],
                        predicted_lag=predicted_lag)
                sec["spec_stationarity"] = stat_val

                # Band-limited envelope correlation (CC_TAPEMATCH_ADDON.md Task 4):
                # None when disabled so the DB column stays NULL (same dormant
                # pattern as flaw_match_score/spec_stationarity above). Coarse
                # offset reuses the predicted-lag anchor-0 lag when already
                # computed (Task 4 high-ppm path); otherwise a single fresh
                # local_lag call, same cost discipline as the flaw block.
                # Conjunctive-only signal per spec 4.2 -- never a lone-merge
                # OR-path even after calibration; this just persists the metric
                # for Task 5's addon_links.
                env_val = None
                if env_enabled:
                    if predicted_lag is not None:
                        env_offset = predicted_lag["lag_0"]
                    else:
                        env_lag0, _ = align.local_lag(ri, rj, sr, anchors[0], win,
                                                       a_cfg["max_lag_sec"])
                        env_offset = env_lag0 if env_lag0 is not None else 0.0
                    env_val = match.envelope_corr(
                        ri, rj, sr, cfg,
                        lineage_results[names[i]]["hf_ceiling_hz"],
                        lineage_results[names[j]]["hf_ceiling_hz"],
                        pair_ratios[(i, j)], env_offset)
                sec["env_corr"] = env_val

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
    # central_name/speed_info_central were already computed above (before the
    # secondary match loop, so the both-staircase union flags could use them);
    # this just prints the section in its original position and switches the
    # active reference for the downstream CLUSTERS/lineage sections.
    if central_name != ref_name:
        print(f"\n=== LAG CURVES / SPEED (re-run vs central ref={central_name}) ===")
        print("  anchors: " + ", ".join(fmt_hms(a) for a in anchors_central))
        for name, d in speed_info_central.items():
            if name == central_name:
                continue
            print(f"  {central_name}->{name}: {d['kind']}  "
                  f"speed ratio={d['ratio']:.6f} ({d['ppm']:+.0f} ppm)")
            if d["kind"] == "staircase/splice":
                print(f"    ^ discontinuous lag curve — staircase pattern (CDR re-tracking or tape edits)")
        speed_info = speed_info_central
        ref_mono = central_mono
        anchors = anchors_central
        ref_name = central_name
        lag_rows_final = lag_rows_central
    else:
        lag_rows_final = lag_rows_pass1

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
    # Route the link decision through verdict.pair_links so the clustering logic
    # lives in exactly one place (Task 1.3). A None signal (no secondary pass, or
    # fingerprint disabled) is skipped by the predicate, reproducing the built-in
    # threshold checks.
    #   - speed_kind_a/b: staircase flag (Task 3.2), from staircase_sources.
    #   - hf_ceiling_hz_a/b, nyquist_capped_a/b: lo-fi hiss conditional (Task 4.2),
    #     from the lineage pre-pass above -- same match.lineage_evidence values
    #     tapematch_session.py persists to pairs.hf_ceiling_hz_a/b and the harness
    #     (verdict.cluster_verdicts) reads back from the DB.
    #   - lb_a/lb_b: curator conditional key (Task 4.1), regex-extracted from the
    #     staged folder name (_lb_num); paired with lineage_pairs loaded above via
    #     verdict.load_lineage_pairs, the same helper the harness uses.
    def _pair_metrics(i, j):
        na, nb = names[i], names[j]
        return {
            "corr": float(M[i, j]),
            "windowed_frac": float(W[i, j]) if sec_results else None,
            "hiss_frac": float(H[i, j]) if sec_results else None,
            "hiss_median": float(H_med[i, j]) if sec_results else None,
            "fp_score": float(FP[i, j]) if fp_cluster_thr > 0.0 else None,
            "speed_kind_a": "staircase/splice" if na in staircase_sources else None,
            "speed_kind_b": "staircase/splice" if nb in staircase_sources else None,
            "hf_ceiling_hz_a": lineage_results[na]["hf_ceiling_hz"],
            "hf_ceiling_hz_b": lineage_results[nb]["hf_ceiling_hz"],
            "nyquist_capped_a": lineage_results[na]["nyquist_capped"],
            "nyquist_capped_b": lineage_results[nb]["nyquist_capped"],
            "lb_a": lb_numbers.get(na),
            "lb_b": lb_numbers.get(nb),
        }

    groups = match.cluster(names, M, m_thr,
                           link_fn=lambda i, j: verdict.pair_links(
                               _pair_metrics(i, j), cfg, lineage=lineage_pairs))
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

    # === Lineage: values computed in the pre-pass above (before clustering, so
    # the lo-fi hiss conditional had them); this section just reports them ===
    print("\n=== LINEAGE EVIDENCE (interpret manually) ===")
    dbg.log(f"LINEAGE_START  n_families={len(groups)}")
    print(f"  {'source':>8}  {'HF ceiling':>11}  {'noise floor':>11}  {'DC asymmetry':>12}")
    capped = False
    for name in trim_bounds:
        ev = lineage_results[name]
        capped = capped or ev["nyquist_capped"]
        print(f"  {name:>8}  {ev['hf_ceiling_hz']/1000:8.1f}kHz  "
              f"{ev['noise_floor_db']:9.1f}dB  "
              f"{ev['asymmetry_dc']:+12.5f}")

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

        # TODO-235: per-source piecewise lag model vs the final reference, so a
        # staircase source's perf->source time map survives the run (backend
        # ab_clips, TODO-233 pt2). The reference source itself has no curve —
        # it IS the clock (lag identically 0).
        step_thr = cfg["align"]["step_flag_sec"]
        lag_segments_out = {
            nm: align.fit_lag_segments(lag_rows_final.get(nm, []), step_thr)
            for nm in names
        }

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
                    "speed_confidence": speed_info[nm].get("ratio_confidence"),
                    "family_id": source_family[nm],
                    # TODO-235: piecewise lag model vs lag_ref (final reference
                    # source). Empty for the reference itself and for sources
                    # with <2 valid anchors. Raw anchor rows kept alongside so
                    # consumers can re-derive with different step thresholds.
                    "lag_ref": ref_name,
                    "lag_segments": lag_segments_out[nm],
                    "lag_curve": [
                        {"center_sec": r["center_sec"], "lag_sec": r["lag_sec"],
                         "peak": r["peak"]}
                        for r in lag_rows_final.get(nm, [])
                    ],
                    # Shared-flaw event fingerprint (Task 2.1): per-source count +
                    # serialized timeline. Variable-length -> run JSON only, not
                    # the DB (pairs.flaw_n_events_a/b carries the scalar counts).
                    # Empty/absent when flaw_fingerprint.enabled is false.
                    "flaw_event_count": len(flaw_events.get(nm, [])),
                    "flaw_events": [[t, kind, s] for t, kind, s in flaw_events.get(nm, [])],
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
