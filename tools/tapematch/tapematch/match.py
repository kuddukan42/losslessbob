"""Matching, clustering, and lineage evidence.

Once sources are locally aligned at each anchor, we measure shared lineage:
  - residual cross-correlation: shared source locks ~0.95-1.0, independent
    captures sit ~0.1-0.3 (bimodal -> clean threshold cluster)
  - stereo transient fingerprint: pan position + reflection geometry of a clap,
    which survives EQ but differs per independent mic position
Clustering is decided automatically. Lineage DIRECTION is reported as evidence
(bandwidth ceiling, noise floor, dropouts) for you to ratify -- not auto-decided.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.signal import stft, correlate
from .audio import to_mono, resample_ratio
from .align import local_lag, local_lag_centered


def aligned_window(ref_mono, other_mono, sr, center_sec, window_sec, lag_sec):
    """Extract the same window from both, shifting `other` by lag_sec."""
    half = int(window_sec * sr / 2)
    c = int(center_sec * sr)
    a0, a1 = max(0, c - half), c + half
    shift = int(lag_sec * sr)
    b0, b1 = a0 + shift, a1 + shift
    if b0 < 0:
        a0 -= b0; b0 = 0
    ra = ref_mono[a0:a1]
    ob = other_mono[b0:b1]
    n = min(len(ra), len(ob))
    return ra[:n], ob[:n]


def residual_corr(ra, ob):
    """Correlation of the HF residual (source fine-structure, not the music)."""
    if len(ra) < 256:
        return 0.0
    ra = ra - np.mean(ra); ob = ob - np.mean(ob)
    ra = np.diff(ra); ob = np.diff(ob)
    ra = (ra - ra.mean()) / (ra.std() + 1e-9)
    ob = (ob - ob.mean()) / (ob.std() + 1e-9)
    return float(np.dot(ra, ob) / len(ra))


def polarity_aware_corr(ref_mid, ref_side, oth_mid, oth_side):
    """Best |residual_corr| across channel-polarity variants of an aligned pair.

    Pass 1 ingests the L+R "mid" mixdown only, so a same-source copy with ONE
    channel polarity-inverted reads as near-zero on mid-vs-mid: if the copy has
    its right channel flipped, copy_mid == L-R == ref_side and copy_side == L+R
    == ref_mid, so the genuine match lives in the *cross* terms. (A pure L<->R
    swap with no inversion is invariant under L+R and needs no rescue; a
    whole-signal flip is already handled by residual_corr's abs().)

    Given the four already-aligned, equal-length windows, this returns the
    strongest correlation over { mid-mid, mid-side, side-mid } — the mid-mid
    term is the normal score, the two cross terms recover a single inverted
    channel regardless of which copy carries it.

    Args:
        ref_mid: reference L+R window.
        ref_side: reference L-R window (same samples as ref_mid).
        oth_mid: other source L+R window (same length).
        oth_side: other source L-R window (same length).

    Returns:
        (best_abs_corr, pairing) where pairing is one of "mid-mid",
        "mid-side", "side-mid".
    """
    cands = (
        ("mid-mid", abs(residual_corr(ref_mid, oth_mid))),
        ("mid-side", abs(residual_corr(ref_mid, oth_side))),
        ("side-mid", abs(residual_corr(ref_side, oth_mid))),
    )
    pairing, best = max(cands, key=lambda c: c[1])
    return best, pairing


def polarity_rescue(ref_mid, ref_side, oth_mid, oth_side, sr, anchors, win, max_lag, base_med):
    """Re-score a near-zero pair across channel-polarity variants (TODO-184).

    A same-source copy with one channel polarity-inverted decorrelates on
    mid-vs-mid, so `local_lag` cannot lock the alignment there — but for a
    right-inverted copy `oth_side` == the reference's L+R, so the genuine match
    (and a strong, lockable lag) lives in the mid-side cross term. Each
    cross-pairing therefore does its OWN per-anchor lag search before the
    residual correlation.

    The mid-mid score is the caller's already-computed `base_med`; only the two
    cross terms are evaluated here. The best median across the three is returned
    — this can only RAISE a near-zero pair toward a genuine same-source match
    (independent sources have no correlated cross term), mirroring the
    keep-if-improves guard used for speed refinement.

    Args:
        ref_mid, ref_side: reference L+R and L-R memmaps/arrays.
        oth_mid, oth_side: other source L+R and L-R, speed-corrected to match the
            reference if the pair has a speed offset (caller resamples both).
        sr: sample rate.
        anchors: anchor centre times (sec).
        win: correlation window length (sec).
        max_lag: local lag search range (sec).
        base_med: the mid-mid median residual_corr already computed by the caller.

    Returns:
        (best_med, pairing) with pairing in {"mid-mid", "mid-side", "side-mid"}.
    """
    from .align import local_lag
    best_med, best_pair = float(base_med), "mid-mid"
    variants = (("mid-side", ref_mid, oth_side), ("side-mid", ref_side, oth_mid))
    for pairing, A, B in variants:
        corrs: list[float] = []
        for ctr in anchors:
            lag, _ = local_lag(A, B, sr, ctr, win, max_lag)
            if lag is None:
                continue
            ra, ob = aligned_window(A, B, sr, ctr, win, lag)
            corrs.append(abs(residual_corr(ra, ob)))
        med = float(np.median(corrs)) if corrs else 0.0
        if med > best_med:
            best_med, best_pair = med, pairing
    return best_med, best_pair


def _envelope(mono, sr, env_rate=100):
    """Low-rate energy envelope -- drift-tolerant coarse alignment feature."""
    win = int(sr / env_rate)
    n = (len(mono) // win) * win
    e = mono[:n].reshape(-1, win)
    env = np.sqrt((e ** 2).mean(axis=1) + 1e-12)
    env = np.log(env + 1e-6)
    return (env - env.mean()) / (env.std() + 1e-9), env_rate


def estimate_ratio_v1_deprecated(ref, other, sr, anchors, cfg):
    """Coarse speed-ratio search on energy envelopes. DEPRECATED.

    Superseded by `estimate_ratio_v2` (CC_TAPEMATCH_FIXES.md Task 5) — kept
    fully callable, unchanged, for A/B comparison in the regression harness
    only. Do not add new call sites; use `estimate_ratio_v2`.

    Search range/resolution come from cfg["match"] (ratio_search_min/max/steps);
    defaults reproduce the historical ±20000 ppm / 500 ppm grid. The range was
    widened to ±30000 ppm because ~18% of corpus pairs were railing at the old
    ±20000 boundary (true >2% cassette/DAT offsets clamped to the edge → wrong
    resample → false-distinct). The coarse grid is deliberately left ~500 ppm;
    `refine_speed_ratio` supplies the fine (≤~5 ppm) accuracy that the
    sample-level residual_corr actually needs (a 45s window tolerates only
    ~20 ppm residual speed error).
    """
    m = cfg.get("match", {}) if isinstance(cfg, dict) else {}
    lo = float(m.get("ratio_search_min", 0.980))
    hi = float(m.get("ratio_search_max", 1.020))
    steps = int(m.get("ratio_search_steps", 81))
    er, rate = _envelope(ref, sr)
    eo, _ = _envelope(other, sr)
    best_ratio, best_peak = 1.0, -1.0
    for ratio in np.linspace(lo, hi, steps):
        from scipy.signal import resample
        m_len = max(8, int(len(eo) * ratio))
        eo_r = resample(eo, m_len)
        eo_r = (eo_r - eo_r.mean()) / (eo_r.std() + 1e-9)
        n = min(len(er), len(eo_r))
        xc = correlate(er[:n], eo_r[:n], mode="full")
        peak = np.max(np.abs(xc)) / n
        if peak > best_peak:
            best_peak, best_ratio = peak, ratio
    return best_ratio


def duration_ratio_prior(dur_ref: float, dur_other: float,
                          diagnostics: set[str]) -> float | None:
    """Speed-ratio prior from performance durations (post-trim).

    A 5% speed offset is a 5% duration difference — trivially visible.
    CC_TAPEMATCH_FIXES.md Task 5.1.

    Args:
        dur_ref: reference source's trimmed performance duration (sec).
        dur_other: other source's trimmed performance duration (sec).
        diagnostics: diagnostic tags already known for this pair. If it
            contains "TIMING_MISMATCH" or "INCOMPLETE" the durations are not
            comparable and no prior is returned.

    Returns:
        dur_ref / dur_other, or None when trim/timing diagnostics make
        durations incomparable, `dur_other` is non-positive, or the raw
        ratio implies an implausible >80,000 ppm offset.
    """
    if {"TIMING_MISMATCH", "INCOMPLETE"} & diagnostics:
        return None
    if dur_other <= 0:
        return None
    r = dur_ref / dur_other
    if abs(r - 1.0) > 0.08:          # >80,000 ppm — durations not comparable
        return None
    return r


def estimate_ratio_v2(ref, other, sr, cfg,
                       prior: float | None = None) -> tuple[float, float]:
    """Prior-centered, confidence-reporting speed-ratio estimator.

    CC_TAPEMATCH_FIXES.md Task 5.2 — replaces the fixed-grid
    `estimate_ratio_v1_deprecated` as the primary speed-ratio search. Returns
    (ratio, confidence), where confidence is the peak prominence of the
    envelope-correlation surface: (best - median) / (mad + eps).

    Search strategy:
      prior given  -> fine grid: prior ± 3000 ppm, 100 ppm steps (61 pts)
      no prior     -> coarse grid: ±60000 ppm, 1000 ppm steps (121 pts),
                      then fine grid ±1500 ppm / 100 ppm around coarse best.

    Envelope warping uses linear interpolation of the log-envelope
    (np.interp), NOT scipy.signal.resample — FFT resampling of a
    non-periodic envelope adds edge artifacts and biases peak comparison
    across ratios.

    Args:
        ref: reference mono array (or memmap).
        other: other-source mono array (or memmap).
        sr: sample rate (Hz).
        cfg: full config dict (unused directly here — kept for signature
            symmetry with the v1 estimator and future knob additions).
        prior: optional duration-ratio prior from `duration_ratio_prior`.

    Returns:
        (ratio, confidence).
    """
    er, rate = _envelope(ref, sr)
    eo, _    = _envelope(other, sr)

    def warp(env: np.ndarray, ratio: float) -> np.ndarray:
        m = max(8, int(len(env) * ratio))
        xi = np.linspace(0, len(env) - 1, m)
        w = np.interp(xi, np.arange(len(env)), env)
        return (w - w.mean()) / (w.std() + 1e-9)

    def peak_at(ratio: float) -> float:
        eo_r = warp(eo, ratio)
        n = min(len(er), len(eo_r))
        xc = correlate(er[:n], eo_r[:n], mode="full")
        return float(np.max(np.abs(xc)) / n)

    if prior is not None:
        grid = prior + np.arange(-3000, 3001, 100) * 1e-6
    else:
        grid = 1.0 + np.arange(-60000, 60001, 1000) * 1e-6

    peaks = np.array([peak_at(r) for r in grid])
    best = grid[int(np.argmax(peaks))]

    if prior is None:  # refine around coarse best
        fine = best + np.arange(-1500, 1501, 100) * 1e-6
        fpk = np.array([peak_at(r) for r in fine])
        best = fine[int(np.argmax(fpk))]
        peaks = np.concatenate([peaks, fpk])

    med = float(np.median(peaks))
    mad = float(np.median(np.abs(peaks - med))) + 1e-9
    confidence = (float(np.max(peaks)) - med) / mad
    return float(best), confidence


def _pick_pitch_windows(mono: np.ndarray, sr: int, n: int,
                         win_sec: float) -> list[tuple[int, int]]:
    """Pick up to `n` high-energy analysis windows spread early/mid/late.

    Splits `mono` into `n` equal-length segments and, within each, centers a
    `win_sec` window on the loudest 1-second frame — the inverse of
    `align.find_quiet_segments`'s quiet-frame search, biased toward stable
    voiced/musical content rather than transient-only bursts. Used by
    `pitch_ratio_pyin` (CC_TAPEMATCH_FIXES.md Task 6.2).

    Args:
        mono: mono audio array (or memmap).
        sr: sample rate (Hz).
        n: number of windows to pick (one per segment).
        win_sec: window length in seconds.

    Returns:
        List of (start_sample, end_sample) tuples, shorter than `n` if the
        source is too short to support a full window in a given segment.
    """
    total = len(mono)
    win_samp = min(int(win_sec * sr), total)
    frame = sr  # 1-second frames
    if total < frame or win_samp < frame:
        return []
    edges = np.linspace(0, total, n + 1).astype(int)
    windows: list[tuple[int, int]] = []
    for k in range(n):
        lo, hi = int(edges[k]), int(edges[k + 1])
        if hi - lo < frame:
            continue
        chunk = np.asarray(mono[lo:hi], dtype=np.float32)
        n_frames = len(chunk) // frame
        if n_frames == 0:
            continue
        energies = (chunk[:n_frames * frame].reshape(n_frames, frame) ** 2).mean(axis=1)
        peak_frame = int(np.argmax(energies))
        center = lo + peak_frame * frame + frame // 2
        w0 = max(lo, center - win_samp // 2)
        w1 = min(hi, w0 + win_samp)
        w0 = max(lo, w1 - win_samp)
        if w1 - w0 >= frame:
            windows.append((w0, w1))
    return windows


def pitch_ratio_pyin(ref, other, sr, cfg) -> tuple[float, float]:
    """Absolute-pitch speed ratio via librosa.pyin median f0.

    CC_TAPEMATCH_FIXES.md Task 6.2 — fallback speed-ratio estimate for pairs
    where `estimate_ratio_v2` returned low confidence (speed-unknown) AND no
    duration prior was available. Gate its use behind `align.pyin_fallback`.

    Picks 3 non-quiet 60s windows per source (`_pick_pitch_windows`, spread
    early/mid/late), computes a voiced f0 track per window via
    ``librosa.pyin(y_win, fmin=65.0, fmax=1000.0, sr=sr, frame_length=4096)``,
    takes the median voiced f0 per window, and forms a per-window ratio
    med_other / med_ref. The final ratio is the median of the per-window
    ratios; confidence is derived from their spread after octave-folding.

    Ratio convention (matches `estimate_ratio_v2` / `duration_ratio_prior` /
    `audio.resample_ratio`, all resample_ratio-compatible): the returned
    ratio is the value `r` such that ``audio.resample_ratio(other, r, sr)``
    aligns `other` onto `ref` -- i.e. `r` == other's original duration
    stretched by r matches ref's duration. Since resample_ratio(x, r, sr)
    divides x's pitch by r (verified: r>1 lengthens duration AND lowers
    pitch, matching real tape/DAT speed-error physics), and a duration-
    compressed "sped up" `other` has pitch raised by the same factor its
    duration shrank, the resample-compatible ratio is med_other / med_ref
    (NOT med_ref / med_other) -- using the inverse would apply pyin's
    correction backwards and make a real speed offset worse instead of
    better, so this deliberately differs from a naive med_ref/med_other
    reading.

    Octave-fold caveat: pyin can jump octaves between sources. Any per-window
    ratio within [1.9, 2.1] or [0.48, 0.52] of the raw cross-window median is
    folded by the corresponding power of 2 before the final median is taken.
    If the folded windows still disagree by more than 2000 ppm, confidence is
    reported as 0 (caller should not trust the ratio).

    Runs at the 16 kHz analysis rate — fmax 1000 Hz is far below Nyquist.
    Callers on the tapematch entry path must set NUMBA_CACHE_DIR before the
    first call (librosa.pyin JIT-compiles via numba).

    Args:
        ref: reference mono array (or memmap).
        other: other-source mono array (or memmap).
        sr: sample rate (Hz).
        cfg: full config dict (unused directly — kept for signature symmetry
            with the other estimators and future knob additions).

    Returns:
        (ratio, confidence) with confidence in [0, 1]. Returns (1.0, 0.0)
        when no window yields a usable voiced f0 on both sides.
    """
    import librosa

    win_sec = 60.0
    n_windows = 3
    win_ref = _pick_pitch_windows(ref, sr, n_windows, win_sec)
    win_other = _pick_pitch_windows(other, sr, n_windows, win_sec)
    n = min(len(win_ref), len(win_other))
    if n == 0:
        return 1.0, 0.0

    def _med_f0(mono, w0, w1) -> float | None:
        y = np.asarray(mono[w0:w1], dtype=np.float32)
        f0, vflag, _ = librosa.pyin(y, fmin=65.0, fmax=1000.0, sr=sr,
                                    frame_length=4096)
        if f0 is None or vflag is None:
            return None
        voiced = f0[vflag.astype(bool)]
        voiced = voiced[~np.isnan(voiced)]
        if len(voiced) == 0:
            return None
        return float(np.median(voiced))

    ratios: list[float] = []
    for k in range(n):
        med_r = _med_f0(ref, *win_ref[k])
        med_o = _med_f0(other, *win_other[k])
        if med_r is None or med_o is None or med_r <= 0:
            continue
        ratios.append(med_o / med_r)

    if not ratios:
        return 1.0, 0.0

    raw_median = float(np.median(ratios))
    folded: list[float] = []
    for r in ratios:
        rel = r / raw_median if raw_median > 0 else 1.0
        if 1.9 <= rel <= 2.1:
            r = r / 2.0
        elif 0.48 <= rel <= 0.52:
            r = r * 2.0
        folded.append(r)

    med_ratio = float(np.median(folded))
    if med_ratio <= 0:
        return 1.0, 0.0
    spread = float(max(folded) - min(folded))
    spread_ppm = abs(spread / med_ratio) * 1e6
    if spread_ppm > 2000.0:
        return med_ratio, 0.0

    confidence = max(0.0, 1.0 - (spread / med_ratio))
    return med_ratio, float(confidence)


def corrected_ratio_from_lags(centers, lags, ratio):
    """Correct a speed ratio from residual per-anchor lags measured after `ratio`.

    When a residual speed error remains after a coarse resample, the per-anchor
    lag trends linearly with anchor position: slope == the residual rate. Because
    these lags come from drift-robust *music-level* cross-correlation (local_lag),
    they stay measurable even when the sample-level residual_corr has already
    collapsed to ~0 — so the slope is a far finer speed estimate than the coarse
    envelope grid. Dividing by (1 + slope) removes the residual.

    Args:
        centers: anchor center times (sec).
        lags: residual lag (sec) measured at each center after applying `ratio`.
        ratio: the speed ratio that was applied to produce those lags.

    Returns:
        (corrected_ratio, residual_ppm). With < 3 points the input is returned
        unchanged (slope under-determined).
    """
    if len(centers) < 3:
        return ratio, 0.0
    slope = float(np.polyfit(np.asarray(centers, float), np.asarray(lags, float), 1)[0])
    return ratio / (1.0 + slope), slope * 1e6


def refine_speed_ratio(ref, other, sr, anchors, cfg, coarse_ratio):
    """Iteratively refine a coarse speed ratio via the lag-curve slope.

    After resampling `other` by the current ratio, the residual per-anchor lag
    slope measures the leftover speed error directly (see
    `corrected_ratio_from_lags`); the ratio is corrected and the step repeated
    until the residual falls below ``refine.stop_ppm`` or ``refine.max_iter`` is
    reached. Only the search ratio changes — the matcher and cluster threshold
    are untouched.

    Self-limiting: for genuinely different sources the lags are noise, the fitted
    slope does not converge to a real speed, and the resulting residual_corr stays
    low — so this can recover a true same-source high-ppm pair but cannot
    manufacture a false merge. The caller keeps whichever of the coarse/refined
    ratio yields the higher median residual_corr, so refinement never regresses a
    pair.

    Returns:
        (ratio, corrs): the refined ratio and the per-anchor residual_corr list
        measured at it (median'd by the caller).
    """
    rc = cfg.get("refine", {}) if isinstance(cfg, dict) else {}
    max_iter = int(rc.get("max_iter", 2))
    stop_ppm = float(rc.get("stop_ppm", 5.0))
    win = float(cfg["anchors"]["window_sec"])
    maxlag = float(cfg["align"]["max_lag_sec"])

    ratio = float(coarse_ratio)
    corrs: list[float] = []
    for _ in range(max(1, max_iter)):
        rj = resample_ratio(other, ratio, sr)
        centers: list[float] = []
        lags: list[float] = []
        corrs = []
        for ctr in anchors:
            lag, _ = local_lag(ref, rj, sr, ctr, win, maxlag)
            if lag is None:
                continue
            centers.append(ctr)
            lags.append(lag)
            ra, ob = aligned_window(ref, rj, sr, ctr, win, lag)
            corrs.append(abs(residual_corr(ra, ob)))
        del rj
        new_ratio, resid_ppm = corrected_ratio_from_lags(centers, lags, ratio)
        if abs(resid_ppm) < stop_ppm:
            break
        ratio = new_ratio
    return ratio, corrs


def find_quiet_segments(
    mono: np.ndarray,
    sr: int,
    energy_percentile: float,
    min_sec: float,
) -> list[tuple[float, float]]:
    """Return (center_sec, dur_sec) for low-energy segments in mono.

    Reads memmap-friendly in 60-second blocks to avoid loading the full array.
    """
    frame = sr  # 1-second frames
    block_samp = 60 * sr
    energy_parts: list[np.ndarray] = []
    n_total = len(mono)
    for start in range(0, n_total, block_samp):
        chunk = np.array(mono[start:min(start + block_samp, n_total)], dtype=np.float32)
        n_frames = len(chunk) // frame
        if n_frames == 0:
            continue
        reshaped = chunk[:n_frames * frame].reshape(n_frames, frame)
        energy_parts.append((reshaped ** 2).mean(axis=1))
    if not energy_parts:
        return []
    energies = np.concatenate(energy_parts)
    threshold = float(np.percentile(energies, energy_percentile))
    is_quiet = energies < threshold

    segments: list[tuple[float, float]] = []
    run_start: int | None = None
    for i, q in enumerate(is_quiet):
        if q and run_start is None:
            run_start = i
        elif not q and run_start is not None:
            dur = float(i - run_start)
            if dur >= min_sec:
                segments.append((float(run_start) + dur / 2.0, dur))
            run_start = None
    if run_start is not None:
        dur = float(len(energies) - run_start)
        if dur >= min_sec:
            segments.append((float(run_start) + dur / 2.0, dur))
    return segments


def lowband_envelope_corr(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    band_hz: tuple[float, float] = (250, 2000),
    max_lag_sec: float = 90.0,
) -> dict:
    """Low-band (250–2000 Hz) energy-envelope cross-correlation.

    For HF-dead or noise-floor-dominated sources where `residual_corr` collapses to
    near-zero (the HF fine-structure is missing), the energy dynamics in the 250–2000 Hz
    band (audience crescendos, song starts/ends, applause patterns) may still be
    correlated between two same-source recordings. Bandpass-filters both signals (zero-
    phase, **no waveform resampling** — WORKFLOW.md prohibition), computes a low-rate
    log-RMS envelope via `_envelope`, then cross-correlates the two envelopes via a lag
    search in the envelope domain (equivalent to time-warp via search-offset shifting).

    Args:
        mono_a: first mono audio array (float32, already at analysis_sr).
        mono_b: second mono audio array.
        sr: sample rate (Hz).
        band_hz: (lo_hz, hi_hz) bandpass limits in Hz.
        max_lag_sec: maximum search lag in seconds.

    Returns:
        Dict with:
          'corr': peak normalized envelope cross-correlation in [-1, 1]
          'lag_sec': lag at which peak was found (positive = b leads a)
          'n_env_samples': envelope length used (quality indicator)
    """
    _min_samp = int(sr * 0.5)  # sosfiltfilt needs > 3*ntaps padding; 0.5s is safe
    if min(len(mono_a), len(mono_b)) < _min_samp:
        return {"corr": 0.0, "lag_sec": 0.0, "n_env_samples": 0}
    from scipy.signal import butter, sosfiltfilt
    lo_hz, hi_hz = float(band_hz[0]), float(band_hz[1])
    nyq = sr / 2.0
    sos = butter(6, [lo_hz / nyq, min(hi_hz, nyq * 0.99) / nyq],
                 btype="band", output="sos")
    fa = sosfiltfilt(sos, np.asarray(mono_a, dtype=np.float32))
    fb = sosfiltfilt(sos, np.asarray(mono_b, dtype=np.float32))
    env_a, env_rate = _envelope(fa, sr)
    env_b, _ = _envelope(fb, sr)
    n = min(len(env_a), len(env_b))
    if n < 2:
        return {"corr": 0.0, "lag_sec": 0.0, "n_env_samples": 0}
    ea, eb = env_a[:n], env_b[:n]
    from scipy.signal import correlate as _correlate
    xc = _correlate(eb, ea, mode="full")
    lags = np.arange(-(n - 1), n)
    maxl = int(max_lag_sec * env_rate)
    keep = np.abs(lags) <= maxl
    xc_k, lags_k = xc[keep], lags[keep]
    k = int(np.argmax(np.abs(xc_k)))
    corr = float(xc_k[k]) / n
    lag_sec = float(lags_k[k]) / env_rate
    return {"corr": corr, "lag_sec": lag_sec, "n_env_samples": int(n)}


def secondary_corr_pair(
    ref: np.ndarray,
    other: np.ndarray,
    sr: int,
    cfg: dict,
    predicted_lag: dict | None = None,
    return_raw: bool = False,
) -> dict:
    """Windowed coverage + quiet-segment correlation for one cross-family pair.

    Windowed coverage: dense 60s-window grid, each window does its own ±lag search
    to handle accumulated timing drift from edit points.  Reports fraction of
    windows whose residual correlation exceeds the per-window threshold.

    Quiet-segment hiss: finds low-energy sections (between songs / applause) and
    correlates them with a local lag search.  Tape hiss / crowd noise is unique to
    the recording chain and survives EQ/NR applied to the music signal.

    Args:
        ref: trimmed mono array (may be a memmap).
        other: trimmed mono array for the other source (speed-corrected if needed).
        sr: sample rate.
        cfg: full config dict (must contain secondary_match block).
        predicted_lag: optional dict with keys "ppm" (pair speed offset from
            estimate_ratio), "lag_0" (lag in seconds at anchor0_sec) and
            "anchor0_sec" (the anchor time lag_0 was measured at). When
            |ppm| >= secondary_match.high_ppm_threshold, each window's lag
            search is centered on the predicted drift
            expected_lag(t) = lag_0 + (ppm/1e6) * (t - anchor0_sec)
            instead of zero (CC_TAPEMATCH_FIXES.md Task 4).
        return_raw: if True, also include the raw per-window/per-segment
            correlation lists ("win_corrs", "hiss_corrs") for calibration.

    Returns:
        dict with keys: windowed_frac, windowed_median, n_windows,
                        hiss_frac, hiss_median, n_hiss_segs.
    """
    sec = cfg["secondary_match"]
    win_sec = float(sec["window_sec"])
    hop_sec = float(sec["hop_sec"])
    lag_sec = float(sec["local_lag_sec"])
    per_win_thr = float(sec["window_corr_threshold"])

    win_samp = int(win_sec * sr)
    hop_samp = int(hop_sec * sr)

    high_ppm_thr = float(sec.get("high_ppm_threshold", 0))
    use_predicted = (
        predicted_lag is not None
        and high_ppm_thr > 0
        and abs(predicted_lag["ppm"]) >= high_ppm_thr
    )
    if use_predicted:
        ppm_ratio = predicted_lag["ppm"] / 1e6
        lag_0 = predicted_lag["lag_0"]
        anchor0_sec = predicted_lag["anchor0_sec"]

    # --- Windowed coverage ---
    win_corrs: list[float] = []
    for s0 in range(0, len(ref) - win_samp, hop_samp):
        center_sec = (s0 + win_samp // 2) / sr
        if use_predicted:
            expected_lag = lag_0 + ppm_ratio * (center_sec - anchor0_sec)
            lag, _ = local_lag_centered(ref, other, sr, center_sec, win_sec, lag_sec, expected_lag)
        else:
            lag, _ = local_lag(ref, other, sr, center_sec, win_sec, lag_sec)
        if lag is None:
            continue
        ra, ob = aligned_window(ref, other, sr, center_sec, win_sec, lag)
        win_corrs.append(abs(residual_corr(ra, ob)))

    windowed_frac = 0.0
    windowed_median = 0.0
    if win_corrs:
        arr = np.array(win_corrs)
        windowed_frac = float((arr >= per_win_thr).mean())
        windowed_median = float(np.median(arr))

    # --- Quiet-segment hiss/crowd ---
    segs = find_quiet_segments(
        ref, sr,
        float(sec["quiet_energy_percentile"]),
        float(sec["min_quiet_sec"]),
    )
    hiss_corrs: list[float] = []
    for ctr_sec, dur_sec in segs:
        win_s = min(dur_sec, 30.0)  # cap to keep correlate call manageable
        lag, _ = local_lag(ref, other, sr, ctr_sec, win_s, float(sec["hiss_lag_sec"]))
        if lag is None:
            continue
        ra, ob = aligned_window(ref, other, sr, ctr_sec, win_s, lag)
        hiss_corrs.append(abs(residual_corr(ra, ob)))

    hiss_frac = 0.0
    hiss_median = 0.0
    if hiss_corrs:
        arr = np.array(hiss_corrs)
        hiss_frac = float((arr >= float(sec["hiss_corr_threshold"])).mean())
        hiss_median = float(np.median(arr))

    result = {
        "windowed_frac": windowed_frac,
        "windowed_median": windowed_median,
        "n_windows": len(win_corrs),
        "hiss_frac": hiss_frac,
        "hiss_median": hiss_median,
        "n_hiss_segs": len(hiss_corrs),
    }
    if return_raw:
        result["win_corrs"] = win_corrs
        result["hiss_corrs"] = hiss_corrs
    return result


def _stft_mag(window: np.ndarray, sr: int, nperseg: int, hop: int) -> np.ndarray:
    """STFT magnitude (n_freqs × n_time, float32). Complex array freed immediately."""
    from scipy.signal import stft as _stft
    _, _, Z = _stft(window, fs=sr, nperseg=nperseg, noverlap=nperseg - hop, boundary=None)
    mag = np.abs(Z).astype(np.float32)
    del Z
    return mag


def _find_peaks_2d(
    mag: np.ndarray,
    neighborhood_t: int,
    neighborhood_f: int,
) -> tuple[np.ndarray, np.ndarray]:
    """2D local maxima above mean+std threshold. Returns (t_idx, f_idx) sorted by time."""
    from scipy.ndimage import maximum_filter
    local_max = maximum_filter(
        mag,
        size=(2 * neighborhood_f + 1, 2 * neighborhood_t + 1),
        mode="constant", cval=0.0,
    )
    threshold = mag.mean() + mag.std()
    f_idx, t_idx = np.where((mag == local_max) & (mag > threshold))
    order = np.argsort(t_idx)
    return t_idx[order].astype(np.int32), f_idx[order].astype(np.int32)


def _fingerprint_hashes(window: np.ndarray, sr: int, cfg: dict) -> set:
    """Spectral-peak landmark hashes for one already-sliced window.

    Shazam-style: extract STFT local maxima, then for each peak form
    (f_anchor, f_target, Δt) hash pairs with the next `fanout` peaks within
    `dt_bins` time steps.  Hashes are packed into single ints for fast set ops.

    Offset-invariant by construction: Δt is relative within the window, so
    absolute timing differences (trim offsets, edits) do not affect matching.
    """
    fp = cfg["fingerprint"]
    mag = _stft_mag(window, sr, int(fp["nperseg"]), int(fp["hop"]))

    # Restrict peak-finding to the HF band (e.g. 6–8 kHz) when configured.
    # Musical note energy dominates below ~5 kHz and is shared by all recordings
    # of the same concert, pushing same-show different-source Dice to 0.15–0.50.
    # The 6–8 kHz band is dominated by tape hiss and room reflections that are
    # specific to the recording chain, reducing different-source same-show scores
    # to <0.10 and enabling a lower cluster_threshold (~0.30–0.35).
    if "hf_band_hz" in fp:
        lo_hz, hi_hz = fp["hf_band_hz"]
        nperseg = int(fp["nperseg"])
        lo_bin = int(lo_hz * nperseg / sr)
        hi_bin = min(int(hi_hz * nperseg / sr), mag.shape[0] - 1)
        mag = mag[lo_bin:hi_bin + 1, :]

    t_idx, f_idx = _find_peaks_2d(mag, int(fp["peak_neighborhood_t"]),
                                   int(fp["peak_neighborhood_f"]))
    del mag

    fanout = int(fp["fanout"])
    dt_max = int(fp["dt_bins"])
    hashes: set = set()
    n = len(t_idx)
    for i in range(n):
        t1 = int(t_idx[i]); f1 = int(f_idx[i])
        count = 0
        for j in range(i + 1, n):
            dt = int(t_idx[j]) - t1
            if dt > dt_max:
                break
            # Pack f1 (10 bits) | f2 (10 bits) | dt (8 bits) → 28-bit int
            hashes.add((f1 << 18) | (int(f_idx[j]) << 8) | min(dt, 255))
            count += 1
            if count >= fanout:
                break
    return hashes


def fingerprint_window(mono: np.ndarray, sr: int, cfg: dict) -> set:
    """Build a spectral-peak landmark fingerprint from a fixed reference window.

    The window skips the first few minutes (intro/tuning noise) and lands on the
    first full songs — densest unique content, unaffected by end-of-show drop-outs.
    """
    fp = cfg["fingerprint"]
    start = int(float(fp["window_start_sec"]) * sr)
    dur   = int(float(fp["window_dur_sec"]) * sr)
    if start >= len(mono):
        start = 0
    window = np.array(mono[start:min(start + dur, len(mono))], dtype=np.float32)
    return _fingerprint_hashes(window, sr, cfg)


def windowed_fingerprints(mono: np.ndarray, sr: int, cfg: dict,
                          win_sec: float, hop_sec: float) -> list[set]:
    """Landmark hash sets for a grid of windows spanning the whole recording.

    TODO-185: a curator-claimed shared transient (e.g. a few seconds of shared
    crowd/clapping at a track boundary) can be far shorter than the 60s grid
    `secondary_corr_pair` uses, so its true residual_corr signal is diluted to
    near-zero by the surrounding non-matching material within any one window —
    confirmed on the 1991-11-05 Madison network (calibrate_contig_run.py): all
    5 curator-claimed pairs scored statistically identical to a known-distinct
    control pair at both the production ±10s and a wide ±120s local-lag search.
    Landmark hashing is a different signal (sparse spectral peaks + relative
    timing, not sample-level waveform correlation) and natively offset-invariant,
    so it does not need an absolute-time correspondence between two recordings'
    differing track splits — see `best_window_fingerprint_match`.
    """
    win_samp = int(win_sec * sr)
    hop_samp = int(hop_sec * sr)
    out: list[set] = []
    n = len(mono)
    if n < win_samp:
        return out
    for s0 in range(0, n - win_samp + 1, hop_samp):
        window = np.array(mono[s0:s0 + win_samp], dtype=np.float32)
        out.append(_fingerprint_hashes(window, sr, cfg))
    return out


def best_window_fingerprint_match(hashes_a: list[set], hashes_b: list[set],
                                  win_sec: float, hop_sec: float) -> dict:
    """Best Dice score over all (window_a, window_b) pairs from `windowed_fingerprints`.

    Searches every window-pair rather than only matching positions, because a
    composite/patchwork recording's track splits (and any missing/reordered
    material) mean the same calendar moment in the show can land at different
    absolute offsets in each recording's own trimmed timeline. This localizes
    a real match wherever it falls — report as evidence for manual ratify
    (like lineage), not an automatic same-family merge.

    Returns:
        dict with "dice" (0.0 if no windows), and when a match is found,
        "center_a_sec"/"center_b_sec" (window center times) for locating it.
    """
    best = {"dice": 0.0, "i": -1, "j": -1}
    for i, ha in enumerate(hashes_a):
        for j, hb in enumerate(hashes_b):
            d = fingerprint_score(ha, hb)
            if d > best["dice"]:
                best = {"dice": d, "i": i, "j": j}
    if best["i"] >= 0:
        best["center_a_sec"] = best["i"] * hop_sec + win_sec / 2
        best["center_b_sec"] = best["j"] * hop_sec + win_sec / 2
    return best


def fingerprint_score(ha: set, hb: set) -> float:
    """Dice coefficient between two fingerprint hash sets (0 = no overlap, 1 = identical)."""
    if not ha or not hb:
        return 0.0
    return 2.0 * len(ha & hb) / (len(ha) + len(hb))


def cluster(names, M, threshold, W=None, w_threshold=0.0, F=None, f_threshold=0.0,
            H=None, h_threshold=0.0, H_med=None, h_med_threshold=0.0,
            link_fn=None):
    """Connected-components clustering: link pairs above threshold.

    Links pair (i,j) if:
      M[i,j] >= threshold          (primary residual corr), or
      W[i,j] >= w_threshold        (secondary windowed coverage), or
      H[i,j] >= h_threshold AND
        H_med[i,j] >= h_med_threshold  (hiss-only: fraction + median guard), or
      F[i,j] >= f_threshold        (spectral-peak fingerprint match).

    The H median guard blocks room-ambience false positives: modern digital
    recordings at the same venue correlate in the hiss fraction metric but
    show a low median (< ~0.40) because only a portion of quiet segments
    carry genuine tape-hiss identity.

    ``link_fn``: optional ``(i, j) -> bool`` predicate. When provided, it is the
    sole authority on whether a pair links, and the threshold arguments above
    are ignored. Used by cli.py to route the decision through
    ``verdict.pair_links`` so the clustering logic lives in exactly one place
    (Task 1.3 of CC_TAPEMATCH_FIXES.md). With the committed config and no
    staircase/curator overrides, ``verdict.pair_links`` is byte-identical to the
    built-in threshold checks (proven by tests/test_verdict_equivalence.py).
    """
    n = len(names)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    for i in range(n):
        for j in range(i + 1, n):
            if link_fn is not None:
                if link_fn(i, j):
                    union(i, j)
            elif M[i, j] >= threshold:
                union(i, j)
            elif W is not None and w_threshold > 0.0 and W[i, j] >= w_threshold:
                union(i, j)
            elif (H is not None and h_threshold > 0.0 and H[i, j] >= h_threshold
                  and H_med is not None and h_med_threshold > 0.0
                  and H_med[i, j] >= h_med_threshold):
                union(i, j)
            elif F is not None and f_threshold > 0.0 and F[i, j] >= f_threshold:
                union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(names[i])
    return list(groups.values())


def cluster_confidence(corr: float) -> str:
    """Confidence label for a same-source cluster pair based on residual corr.

    High (>=0.9): clean match, minimal processing between copies.
    Medium (0.70-0.89): same source likely but significant processing
        (resampling, level boost, EQ) has degraded the correlation.
    Low (<0.70): uncertain — verify manually.
    """
    if corr >= 0.9:
        return "high"
    if corr >= 0.70:
        return "medium"
    return "low"


def lineage_evidence(stream, sr, cfg):
    """Per-source physical evidence for generation ordering.

    Uses scipy.signal.welch (Welch's averaged periodogram) instead of a
    full STFT — welch processes the signal in internal blocks and returns only
    the 1-D PSD array, never allocating the full freq×time matrix.  For a
    2-hour show at 16 kHz the old STFT approach created ~4.3 GB of complex64
    data; welch uses ~a few MB of internal buffers.

    stream may be mono (1-D) or stereo (2-D); mono is used for the PSD.

    NOTE: for real cassette/DAT/lossy discrimination, run this on NATIVE-rate
    audio (44.1k+). At a low analysis SR the HF ceiling is capped by Nyquist.
    """
    from scipy.signal import welch
    mono = to_mono(stream)
    f, psd = welch(mono, fs=sr, nperseg=4096, noverlap=2048)
    psd_db = 10.0 * np.log10(psd + 1e-12)

    floor_db = float(np.percentile(psd_db, 20))
    nyq = sr / 2
    probes = [hz for hz in cfg["lineage"]["hf_ceiling_probe_hz"] if hz + 1000 < nyq]
    if not probes:
        probes = list(range(1000, int(nyq) - 1000, 1000))
    ceil = 0.0
    for hz in probes:
        band = (f >= hz) & (f < hz + 1000)
        if band.any() and psd_db[band].mean() > floor_db + 8:
            ceil = hz
    noise_floor_db = float(np.percentile(psd_db, 5))
    # DC asymmetry: mean sample value in full-scale units.  A value near zero is
    # balanced; a significant offset indicates recording-chain DC bias or asymmetric
    # limiting.  Reported as a taper/equipment signature — NOT a source-identity marker.
    asymmetry_dc = float(np.mean(mono))
    return {
        "hf_ceiling_hz": float(ceil),
        "noise_floor_db": noise_floor_db,
        "nyquist_capped": not [h for h in cfg["lineage"]["hf_ceiling_probe_hz"]
                                if h + 1000 < nyq],
        "asymmetry_dc": asymmetry_dc,
    }


# ── shared-flaw event fingerprint (CC_TAPEMATCH_ADDON.md Task 2, Tier A) ─────────
#
# Tape dropouts, clicks, and splice/cut edits are INHERITED: every descendant of a
# transfer carries the ancestor's flaws at the same musical position. Two
# independent audience recordings of the same show share ZERO flaws (mic-side
# noise/clipping is per-recording, not shared). Content-blind by construction —
# unlike the rejected triplet fingerprint (musical-content collision; see the
# fingerprint.triplet config comment), this measures the RECORDING CHAIN, not
# the performance, so it survives band-limiting/lossy lineage where
# residual_corr and the HF-band fingerprint both die (corr < 0.05, see
# RECALL_RECOVERY_REPORT.md). enabled: false until calibrated per the
# Calibration protocol in CC_TAPEMATCH_ADDON.md.


def _bool_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Vectorized [start, end) index pairs of contiguous True-runs in `mask`."""
    if mask.size == 0:
        return []
    d = np.diff(mask.astype(np.int8))
    starts = np.where(d == 1)[0] + 1
    ends = np.where(d == -1)[0] + 1
    if mask[0]:
        starts = np.concatenate(([0], starts))
    if mask[-1]:
        ends = np.concatenate((ends, [mask.size]))
    return list(zip(starts.tolist(), ends.tolist()))


def _flaw_frame_features(mono: np.ndarray, sr: int, frame_sec: float,
                         block_sec: float = 60.0) -> tuple[np.ndarray, np.ndarray, float]:
    """Blockwise per-frame RMS(dB) + spectral centroid(Hz); memmap-friendly.

    Reads `mono` in `block_sec` chunks (same block-read discipline as
    `find_quiet_segments`) so a full 2-hour source is never materialized as one
    dense ndarray. Frames are non-overlapping, length `frame_sec`.

    Returns:
        (rms_db, centroid_hz, frame_sec): two 1-D arrays, one value per frame.
    """
    frame_len = max(1, int(round(frame_sec * sr)))
    block_samp = int(block_sec * sr)
    block_samp -= block_samp % frame_len
    if block_samp <= 0:
        block_samp = frame_len
    n_total = len(mono)
    win = np.hanning(frame_len).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)
    rms_parts: list[np.ndarray] = []
    cen_parts: list[np.ndarray] = []
    for start in range(0, n_total, block_samp):
        chunk = np.asarray(mono[start:min(start + block_samp, n_total)], dtype=np.float32)
        n_frames = len(chunk) // frame_len
        if n_frames == 0:
            continue
        frames = chunk[:n_frames * frame_len].reshape(n_frames, frame_len)
        rms_parts.append(np.sqrt((frames ** 2).mean(axis=1) + 1e-20))
        spec = np.abs(np.fft.rfft(frames * win, axis=1))
        energy = spec.sum(axis=1) + 1e-12
        cen_parts.append((spec * freqs).sum(axis=1) / energy)
    if not rms_parts:
        return np.array([]), np.array([]), frame_sec
    rms = np.concatenate(rms_parts)
    rms_db = 20.0 * np.log10(rms + 1e-12)
    centroid = np.concatenate(cen_parts)
    return rms_db, centroid, frame_sec


def _quiet_frame_mask(n_frames: int, frame_sec: float, quiet_segments,
                      trim_head_sec: float, trim_tail_sec: float | None) -> np.ndarray:
    """Boolean mask (True = exclude): trim head/tail + between-song quiet segments.

    `quiet_segments` is `find_quiet_segments`'s ``(center_sec, dur_sec)`` output —
    already in seconds (its internal frame is exactly 1 second long), so no unit
    conversion is needed here.
    """
    mask = np.zeros(n_frames, dtype=bool)
    if n_frames == 0:
        return mask
    times = np.arange(n_frames, dtype=np.float64) * frame_sec
    if trim_head_sec:
        mask |= times < trim_head_sec
    if trim_tail_sec is not None:
        mask |= times > trim_tail_sec
    for center_sec, dur_sec in quiet_segments:
        lo, hi = center_sec - dur_sec / 2.0, center_sec + dur_sec / 2.0
        mask |= (times >= lo) & (times <= hi)
    return mask


def _dropout_events(rms_db: np.ndarray, frame_sec: float, exclude_mask: np.ndarray,
                    ff: dict) -> list[tuple[float, str, float]]:
    """Short-time RMS collapse >20 dB below its local median, 40-800 ms, recovers."""
    from scipy.ndimage import median_filter
    if len(rms_db) == 0:
        return []
    local_win_sec = float(ff.get("dropout_local_window_sec", 2.0))
    win_frames = max(3, int(round(local_win_sec / frame_sec)))
    if win_frames % 2 == 0:
        win_frames += 1
    local_med = median_filter(rms_db, size=win_frames, mode="nearest")
    depth_db = float(ff.get("dropout_depth_db", 20.0))
    below = ((local_med - rms_db) > depth_db) & ~exclude_mask
    min_dur = float(ff.get("dropout_min_sec", 0.04))
    max_dur = float(ff.get("dropout_max_sec", 0.8))
    events: list[tuple[float, str, float]] = []
    for start, end in _bool_runs(below):
        dur = (end - start) * frame_sec
        if min_dur <= dur <= max_dur:      # "recovers" == the run ends (below -> False)
            depth = float((local_med[start:end] - rms_db[start:end]).max())
            t_sec = (start + (end - start) / 2.0) * frame_sec
            events.append((t_sec, "dropout", depth))
    return events


def _click_events(mono: np.ndarray, sr: int, ff: dict) -> list[tuple[float, str, float]]:
    """Sample-domain residual spikes >6sigma of local MAD, isolated (<5 ms), capped."""
    from scipy.ndimage import median_filter
    n = len(mono)
    if n < sr:
        return []
    x = np.asarray(mono, dtype=np.float32)
    resid = np.diff(x)
    win_ms = float(ff.get("click_local_window_ms", 50.0))
    win = max(3, int(round(win_ms / 1000.0 * sr)))
    if win % 2 == 0:
        win += 1
    abs_resid = np.abs(resid)
    local_mad = median_filter(abs_resid, size=win, mode="nearest")
    sigma = 1.4826 * local_mad + 1e-9   # MAD -> sigma-equivalent (normal-consistent)
    z = abs_resid / sigma
    thr_sigma = float(ff.get("click_sigma", 6.0))
    spike = z > thr_sigma
    max_dur_ms = float(ff.get("click_max_dur_ms", 5.0))
    max_dur_samp = max(1, int(round(max_dur_ms / 1000.0 * sr)))
    events: list[tuple[float, str, float]] = []
    for start, end in _bool_runs(spike):
        if (end - start) < max_dur_samp:    # isolated
            seg = z[start:end]
            peak_off = int(np.argmax(seg))
            events.append((float(start + peak_off) / sr, "click", float(seg[peak_off])))
    cap = int(ff.get("click_cap", 200))
    if len(events) > cap:
        events.sort(key=lambda e: e[2], reverse=True)
        events = events[:cap]
        events.sort(key=lambda e: e[0])
    return events


def _cut_events(mono: np.ndarray, sr: int, exclude_mask_fn, ff: dict,
                ) -> list[tuple[float, str, float]]:
    """Joint 100ms spectral-centroid + RMS discontinuity >4sigma (splice/seam signature).

    Extends the jump-vs-sigma technique `align.locate_splice_points` uses on a
    pairwise lag curve (a large step relative to the curve's own noise floor
    flags a splice) to a per-source curve instead: here the "curve" is this
    single recording's own 100ms RMS + spectral-centroid series, so the
    detector needs no reference/second source. A joint jump on both series is
    required so a single loud musical accent (which only moves RMS) does not
    register as a splice.
    """
    rms_db, centroid, frame_sec = _flaw_frame_features(mono, sr, float(ff.get("cut_frame_sec", 0.1)))
    n = len(rms_db)
    if n < 3:
        return []
    exclude = exclude_mask_fn(n, frame_sec)
    d_rms = np.diff(rms_db)
    d_cen = np.diff(centroid)

    def _robust_sigma(v: np.ndarray) -> float:
        med = np.median(v)
        mad = np.median(np.abs(v - med))
        return 1.4826 * mad + 1e-9

    z_rms = np.abs(d_rms) / _robust_sigma(d_rms)
    z_cen = np.abs(d_cen) / _robust_sigma(d_cen)
    thr = float(ff.get("cut_sigma", 4.0))
    joint = (z_rms > thr) & (z_cen > thr) & ~(exclude[:-1] | exclude[1:])
    events: list[tuple[float, str, float]] = []
    for i in np.where(joint)[0]:
        t_sec = (int(i) + 1) * frame_sec   # boundary between frame i and i+1
        events.append((t_sec, "cut", float(min(z_rms[i], z_cen[i]))))
    return events


def extract_flaw_events(mono: np.ndarray, sr: int, cfg: dict,
                        trim_head_sec: float = 0.0,
                        trim_tail_sec: float | None = None,
                        ) -> list[tuple[float, str, float]]:
    """Per-source flaw timeline (Task 2.1): dropout / click / cut events.

    Reads `cfg["flaw_fingerprint"]` for all thresholds (see config.yaml). The
    trim head/tail and any between-song quiet segment (reusing
    `find_quiet_segments`, the hiss-detector's own quiet mask) are excluded
    from dropout/cut detection so a between-song gap is never counted as a flaw.

    Args:
        mono: mono audio at analysis_sr (memmap-friendly; read in blocks).
        sr: sample rate (Hz).
        cfg: full config dict; reads ``flaw_fingerprint``.
        trim_head_sec: seconds of head padding to exclude (0.0 = none).
        trim_tail_sec: seconds marking the end of the performance region to
            keep; ``None`` = no tail exclusion (whole array length).

    Returns:
        List of ``(t_sec, kind, strength)`` sorted by time, ``kind`` in
        ``{"dropout", "click", "cut"}``.
    """
    ff = cfg.get("flaw_fingerprint", {}) or {}
    quiet_pct = float(ff.get("quiet_energy_percentile", 25))
    quiet_min_sec = float(ff.get("min_quiet_sec", 3.0))
    quiet_segments = find_quiet_segments(mono, sr, quiet_pct, quiet_min_sec)

    total_dur_sec = len(mono) / float(sr)
    tail = trim_tail_sec if trim_tail_sec is not None else total_dur_sec

    rms_db, _centroid_unused, frame_sec = _flaw_frame_features(
        mono, sr, float(ff.get("dropout_frame_sec", 0.02)))
    exclude = _quiet_frame_mask(len(rms_db), frame_sec, quiet_segments, trim_head_sec, tail)
    dropouts = _dropout_events(rms_db, frame_sec, exclude, ff)

    clicks = _click_events(mono, sr, ff)

    def _cut_exclude(n_frames: int, cframe_sec: float) -> np.ndarray:
        return _quiet_frame_mask(n_frames, cframe_sec, quiet_segments, trim_head_sec, tail)

    cuts = _cut_events(mono, sr, _cut_exclude, ff)

    events = dropouts + clicks + cuts
    events.sort(key=lambda e: e[0])
    return events


def flaw_match_score(events_a: list[tuple[float, str, float]],
                     events_b: list[tuple[float, str, float]],
                     speed_ratio: float, offset_sec: float, cfg: dict,
                     ) -> float | None:
    """Pair score (Task 2.2): fraction of A's flaw events found in B, kind + time.

    Maps A's clock onto B's clock via ``t_mapped = offset_sec + speed_ratio *
    t_a`` (the pair's already-estimated speed ratio / coarse alignment offset —
    same convention as the rest of the pipeline: `speed_ratio` resamples/maps
    the "other" source's clock onto the "reference" source's clock; pass
    ``events_a`` as the "other" side and ``events_b`` as the "reference" side,
    or 1.0/0.0 for an untested pair).

    Args:
        events_a: `extract_flaw_events` output for source A.
        events_b: `extract_flaw_events` output for source B.
        speed_ratio: multiplies A's timestamps to map onto B's clock.
        offset_sec: additive offset after scaling.
        cfg: full config; reads ``flaw_fingerprint.flaw_min_events`` (default 5)
            and ``flaw_fingerprint.tol_sec`` (default 0.5).

    Returns:
        ``matched / min(|A|, |B|)`` in [0, 1], or ``None`` when
        ``min(|A|, |B|) < flaw_min_events`` — absence of flaws is absence of
        evidence, not evidence of difference, so ``None`` must never be
        coerced to 0.0 by any caller.
    """
    import bisect
    ff = cfg.get("flaw_fingerprint", {}) or {}
    min_events = int(ff.get("flaw_min_events", 5))
    tol = float(ff.get("tol_sec", 0.5))
    n_min = min(len(events_a), len(events_b))
    if n_min < min_events:
        return None

    by_kind: dict[str, list[float]] = {}
    for t_b, kind_b, _s in events_b:
        by_kind.setdefault(kind_b, []).append(t_b)
    for times in by_kind.values():
        times.sort()

    matched = 0
    for t_a, kind_a, _s in events_a:
        times = by_kind.get(kind_a)
        if not times:
            continue
        t_map = offset_sec + speed_ratio * t_a
        idx = bisect.bisect_left(times, t_map)
        hit = (idx < len(times) and abs(times[idx] - t_map) < tol) or \
              (idx > 0 and abs(times[idx - 1] - t_map) < tol)
        if hit:
            matched += 1
    return matched / n_min


# ── spectral-ratio stationarity (CC_TAPEMATCH_ADDON.md Task 3) ───────────────────
#
# If A and B descend from the same recording, B(t) ~= H(A(t)) for a FIXED transfer
# function H (the copy chain's EQ/band-limit): the frame-wise log-spectral ratio
# between time-aligned A and B is constant over time (up to noise). Two different
# recordings of the same show have time-varying ratios (mic/room response differs
# as the source moves/levels change). Phase-blind and magnitude-only, so it works
# exactly where residual_corr dies (corr ~0.005). Conjunctive-only signal per spec
# -- never a lone-merge OR-path; combination rules are Task 5.

def spectral_ratio_stationarity(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    cfg: dict,
    hf_ceiling_hz_a: float,
    hf_ceiling_hz_b: float,
    noise_floor_db_a: float,
    noise_floor_db_b: float,
    predicted_lag: dict | None = None,
) -> float | None:
    """Pair score (Task 3.1): time-stationarity of the frame-wise log-spectral ratio.

    Reuses the windowed-coverage grid + speed mapping from `secondary_corr_pair`
    (dense 60s windows, each with its own local-lag search, or a predicted-lag
    centered search under a large constant speed offset -- see
    `secondary_corr_pair`'s docstring). Per window, both sides are converted to
    log-mel spectra (band count from ``spectral_stationarity.n_mels``) capped at
    ``min(hf_ceiling_hz_a, hf_ceiling_hz_b, 0.45*sr)`` -- never compare above the
    narrower side's HF ceiling, since a band neither side reliably carries would
    only inject noise into the ratio. Quiet frames (either side's per-frame level
    below its own ``noise_floor_db`` + margin) are excluded before the per-window
    median ratio is taken, so silence/near-silence can't dominate ``R_w``.

    Args:
        mono_a: trimmed mono array for source A (memmap-friendly).
        mono_b: trimmed mono array for source B.
        sr: sample rate (Hz).
        cfg: full config dict; reads ``spectral_stationarity`` (see config.yaml).
        hf_ceiling_hz_a: `lineage_evidence(...)["hf_ceiling_hz"]` for A.
        hf_ceiling_hz_b: same, for B.
        noise_floor_db_a: `lineage_evidence(...)["noise_floor_db"]` for A.
        noise_floor_db_b: same, for B.
        predicted_lag: optional dict with keys "ppm", "lag_0", "anchor0_sec" --
            same predicted-lag-mode convention as `secondary_corr_pair` (Task 4);
            when given, each window's lag search is centered on the drift
            predicted from the pair's speed ratio instead of zero.

    Returns:
        ``1 - mean_band(std_w(R_w)) / stationarity_norm_db`` clipped to [0, 1],
        or ``None`` when fewer than ``stationarity_min_windows`` windows yield a
        usable ``R_w`` -- absence of usable windows is absence of evidence, not
        evidence of instability, so ``None`` must never be coerced to 0.0 by any
        caller (same discipline as `flaw_match_score`).
    """
    ss = cfg.get("spectral_stationarity", {}) or {}
    win_sec = float(ss.get("window_sec", 60.0))
    hop_sec = float(ss.get("hop_sec", 30.0))
    lag_sec = float(ss.get("local_lag_sec", 10.0))
    n_mels = int(ss.get("n_mels", 32))
    nperseg = int(ss.get("stft_nperseg", 1024))
    stft_hop = int(ss.get("stft_hop", 256))
    margin_db = float(ss.get("noise_floor_margin_db", 6.0))
    min_frames_per_window = int(ss.get("min_frames_per_window", 20))
    norm_db = float(ss.get("stationarity_norm_db", 6.0))
    min_windows = int(ss.get("stationarity_min_windows", 6))

    cap_hz = min(hf_ceiling_hz_a, hf_ceiling_hz_b, 0.45 * sr)
    win_samp = int(win_sec * sr)
    hop_samp = int(hop_sec * sr)
    if cap_hz <= 0 or win_samp <= 0 or hop_samp <= 0:
        return None
    if len(mono_a) <= win_samp or len(mono_b) <= win_samp:
        return None

    import librosa  # lazy import -- same convention as pitch_ratio_pyin above
    mel_fb = librosa.filters.mel(sr=sr, n_fft=nperseg, n_mels=n_mels, fmax=cap_hz)

    use_predicted = predicted_lag is not None
    if use_predicted:
        ppm_ratio = predicted_lag["ppm"] / 1e6
        lag_0 = predicted_lag["lag_0"]
        anchor0_sec = predicted_lag["anchor0_sec"]

    r_windows: list[np.ndarray] = []
    for s0 in range(0, len(mono_a) - win_samp, hop_samp):
        center_sec = (s0 + win_samp // 2) / sr
        if use_predicted:
            expected_lag = lag_0 + ppm_ratio * (center_sec - anchor0_sec)
            lag, _ = local_lag_centered(mono_a, mono_b, sr, center_sec, win_sec,
                                        lag_sec, expected_lag)
        else:
            lag, _ = local_lag(mono_a, mono_b, sr, center_sec, win_sec, lag_sec)
        if lag is None:
            continue
        ra, rb = aligned_window(mono_a, mono_b, sr, center_sec, win_sec, lag)
        n = min(len(ra), len(rb))
        if n < nperseg:
            continue
        ra, rb = np.asarray(ra[:n], dtype=np.float32), np.asarray(rb[:n], dtype=np.float32)

        mag_a = _stft_mag(ra, sr, nperseg, stft_hop)
        mag_b = _stft_mag(rb, sr, nperseg, stft_hop)
        nt = min(mag_a.shape[1], mag_b.shape[1])
        if nt < min_frames_per_window:
            continue
        power_a = mag_a[:, :nt].astype(np.float64) ** 2
        power_b = mag_b[:, :nt].astype(np.float64) ** 2
        del mag_a, mag_b

        # Per-frame overall level (dB) gates quiet frames against each source's
        # OWN noise floor -- an absolute-scale mismatch between this STFT-power
        # convention and lineage_evidence's Welch-PSD dB is immaterial as long as
        # the comparison is self-consistent per side; `noise_floor_margin_db` is
        # the tunable slack (calibrated alongside the rest of this signal).
        frame_level_a = 10.0 * np.log10(power_a.mean(axis=0) + 1e-12)
        frame_level_b = 10.0 * np.log10(power_b.mean(axis=0) + 1e-12)
        keep = ((frame_level_a > noise_floor_db_a + margin_db)
                & (frame_level_b > noise_floor_db_b + margin_db))
        if int(keep.sum()) < min_frames_per_window:
            continue

        logmel_a = 10.0 * np.log10(mel_fb @ power_a[:, keep] + 1e-12)
        logmel_b = 10.0 * np.log10(mel_fb @ power_b[:, keep] + 1e-12)
        r_w = np.median(logmel_a - logmel_b, axis=1)   # (n_mels,)
        r_windows.append(r_w)

    if len(r_windows) < min_windows:
        return None

    R = np.stack(r_windows, axis=0)          # (n_windows, n_mels)
    std_w = np.std(R, axis=0)                # per-band std across windows
    stationarity = 1.0 - float(np.mean(std_w)) / norm_db
    return float(np.clip(stationarity, 0.0, 1.0))


# ── band-limited envelope correlation (CC_TAPEMATCH_ADDON.md Task 4) ─────────────
#
# corr<0.05 FN reflect destroyed HF *fine structure*; the coarse energy envelope
# in the surviving low/mid band (200 Hz-2 kHz by default) can still survive
# lossy/band-limited generations. Same-lineage pairs should envelope-correlate
# near 1.0.
#
# WARNING (triplet failure mode -- handle like the rejected triplet fingerprint):
# envelope is music-dominated, so two INDEPENDENT audience recordings of the same
# show will also correlate substantially here. The signal is included on the
# hypothesis that same-source pairs saturate near 1.0 while different-source
# pairs saturate lower (room/audience differences) -- that gap is UNPROVEN until
# real-audio calibration (CC_TAPEMATCH_ADDON.md Calibration protocol: gap >= 0.10
# between TP p10 and same-show-TN p90, or reject without appeal). Conjunctive-only
# per spec 4.2 -- NEVER a lone-merge OR-path, even after calibration passes;
# combination rules are Task 5's addon_links (AND'd with a lineage-pure signal).

def envelope_corr(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    cfg: dict,
    hf_ceiling_hz_a: float,
    hf_ceiling_hz_b: float,
    speed_ratio: float,
    offset_sec: float,
) -> float | None:
    """Pair score (Task 4.1): Pearson correlation of band-limited RMS envelopes.

    Both sides are zero-phase bandpass-filtered to ``[band_lo_hz,
    min(hf_ceiling_hz_a, hf_ceiling_hz_b, band_hi_cap_hz)]`` -- never above the
    narrower side's HF ceiling, same discipline as
    `spectral_ratio_stationarity`'s mel cap. A low-rate RMS envelope
    (``frame_rate_hz``, default 20 Hz) is computed for each filtered side. A's
    envelope clock is affine-mapped onto B's via ``t_mapped = offset_sec +
    speed_ratio * t_a`` -- the identical convention `flaw_match_score` uses:
    pass the "other" side as `mono_a`/`hf_ceiling_hz_a` and the "reference"
    side as `mono_b`/`hf_ceiling_hz_b`. B's envelope is linearly interpolated
    onto that mapped grid and Pearson correlation is computed over the
    overlapping region only.

    Args:
        mono_a: trimmed mono array, "other" side (memmap-friendly).
        mono_b: trimmed mono array, "reference" side.
        sr: sample rate (Hz).
        cfg: full config dict; reads ``envelope_corr`` (see config.yaml).
        hf_ceiling_hz_a: `lineage_evidence(...)["hf_ceiling_hz"]` for A.
        hf_ceiling_hz_b: same, for B.
        speed_ratio: multiplies A's envelope timestamps to map onto B's clock
            (the pair's already-estimated speed ratio).
        offset_sec: additive offset after scaling (coarse alignment offset).

    Returns:
        Pearson correlation in [-1, 1], or ``None`` when the band is
        degenerate (narrower HF ceiling at/below ``band_lo_hz``) or the mapped
        overlap is shorter than ``min_overlap_min`` minutes -- absence of a
        usable overlap is absence of evidence, not evidence of difference, so
        ``None`` must never be coerced to 0.0 by any caller (same discipline
        as `flaw_match_score` / `spectral_ratio_stationarity`).
    """
    ec = cfg.get("envelope_corr", {}) or {}
    lo_hz = float(ec.get("band_lo_hz", 200.0))
    hi_cap_hz = float(ec.get("band_hi_cap_hz", 2000.0))
    frame_rate = float(ec.get("frame_rate_hz", 20.0))
    min_overlap_sec = float(ec.get("min_overlap_min", 10.0)) * 60.0
    filt_order = int(ec.get("filter_order", 6))

    nyq = sr / 2.0
    hi_hz = min(hf_ceiling_hz_a, hf_ceiling_hz_b, hi_cap_hz, nyq * 0.99)
    if hi_hz <= lo_hz or frame_rate <= 0:
        return None

    # sosfiltfilt needs > 3*ntaps of padding; 0.5s is a safe floor (same guard
    # as lowband_envelope_corr above).
    _min_samp = int(sr * 0.5)
    if min(len(mono_a), len(mono_b)) < _min_samp:
        return None

    from scipy.signal import butter, sosfiltfilt
    sos = butter(filt_order, [lo_hz / nyq, hi_hz / nyq], btype="band", output="sos")
    fa = sosfiltfilt(sos, np.asarray(mono_a, dtype=np.float32))
    fb = sosfiltfilt(sos, np.asarray(mono_b, dtype=np.float32))

    win_samp = int(round(sr / frame_rate))
    if win_samp <= 0:
        return None
    env_a = _rms_envelope(fa, win_samp)
    env_b = _rms_envelope(fb, win_samp)
    del fa, fb
    if len(env_a) == 0 or len(env_b) == 0:
        return None

    t_a = np.arange(len(env_a), dtype=np.float64) / frame_rate
    t_mapped = offset_sec + speed_ratio * t_a
    t_b_max = (len(env_b) - 1) / frame_rate
    valid = (t_mapped >= 0.0) & (t_mapped <= t_b_max)
    n_valid = int(valid.sum())
    if n_valid == 0 or (n_valid / frame_rate) < min_overlap_sec:
        return None

    t_b = np.arange(len(env_b), dtype=np.float64) / frame_rate
    env_b_interp = np.interp(t_mapped[valid], t_b, env_b)
    env_a_valid = env_a[valid]

    if env_a_valid.std() < 1e-12 or env_b_interp.std() < 1e-12:
        return None
    corr = float(np.corrcoef(env_a_valid, env_b_interp)[0, 1])
    return corr if np.isfinite(corr) else None


def _rms_envelope(x: np.ndarray, win_samp: int) -> np.ndarray:
    """Non-overlapping-block RMS envelope, ``win_samp`` samples per frame."""
    n = (len(x) // win_samp) * win_samp
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    blocks = np.asarray(x[:n], dtype=np.float64).reshape(-1, win_samp)
    return np.sqrt((blocks ** 2).mean(axis=1) + 1e-18)


# ── ratio-invariant triplet fingerprint (CC_TAPEMATCH_FIXES.md Task 7) ───────────
#
# The Shazam-style landmark hashes above encode (f1, f2, Δt) with absolute
# quantization, so a 1.5% speed change shifts both frequency and Δt and breaks
# every hash — Cat-1 (speed-offset) pairs fail the fingerprint fallback too.
# Triplet-ratio hashes encode only RATIOS between three peaks, which are
# invariant to time-scaling and pitch shift, so a same-source pair survives a
# global speed change. This is the sole surviving signal for the Task 5.3
# "speed-unknown" pairs. Dice on triplet-hash sets scores exactly like fp_score.


def _fingerprint_peaks(window: np.ndarray, sr: int, cfg: dict) -> list[tuple[float, float]]:
    """STFT peaks as absolute ``(t_sec, f_hz)``, sorted by time.

    Shares the exact front end of :func:`_fingerprint_hashes` — same STFT and the
    same ``hf_band_hz`` restriction that gives the fingerprint its same-show
    rejection property — but returns absolute time/frequency instead of packed,
    band-relative bin hashes. Triplet ratios (Task 7.2) need absolute Hz so that
    ``f1 / f0`` is a true pitch ratio, undistorted by the band's additive
    ``lo_bin`` offset.
    """
    fp = cfg["fingerprint"]
    nperseg = int(fp["nperseg"])
    hop = int(fp["hop"])
    mag = _stft_mag(window, sr, nperseg, hop)
    lo_bin = 0
    if "hf_band_hz" in fp:
        lo_hz, hi_hz = fp["hf_band_hz"]
        lo_bin = int(lo_hz * nperseg / sr)
        hi_bin = min(int(hi_hz * nperseg / sr), mag.shape[0] - 1)
        mag = mag[lo_bin:hi_bin + 1, :]
    t_idx, f_idx = _find_peaks_2d(mag, int(fp["peak_neighborhood_t"]),
                                   int(fp["peak_neighborhood_f"]))
    del mag
    t_scale = hop / float(sr)
    f_scale = float(sr) / nperseg
    return [(int(t) * t_scale, (lo_bin + int(f)) * f_scale)
            for t, f in zip(t_idx, f_idx)]


def _quant_log(x: float, lo: float, hi: float, bits: int) -> int:
    """Quantize a positive ratio ``x`` to ``bits`` bits on a log scale over [lo, hi].

    Clamps out-of-range ratios to the end buckets so an extreme (likely spurious)
    ratio still hashes deterministically rather than raising.
    """
    if x <= 0.0:
        return 0
    n = (1 << bits) - 1
    v = (math.log(x) - math.log(lo)) / (math.log(hi) - math.log(lo))
    q = int(round(v * n))
    return 0 if q < 0 else (n if q > n else q)


def triplet_hashes(peaks: list[tuple[float, float]], cfg: dict) -> set:
    """Ratio-invariant Panako-style triplet hashes (Task 7.2).

    Args:
        peaks: ``[(t_sec, f_hz), ...]`` sorted by ``t`` (from
            :func:`_fingerprint_peaks`).
        cfg: full config; reads ``fingerprint.triplet`` (tmin_sec, tmax_sec, fanout).

    For each anchor peak ``p0``, take up to ``fanout`` peaks ``p1`` in
    ``(t0 + tmin, t0 + tmax]``, and for each ``p1`` up to ``fanout`` peaks ``p2``
    in ``(t1, t1 + tmax]``. Hash the RATIOS only::

        r_t  = (t2 - t1) / (t1 - t0)      # time-scale invariant
        r_f1 = f1 / f0                    # pitch-shift invariant
        r_f2 = f2 / f0

    Quantize ``r_t`` to 6-bit log over [0.25, 4.0]; ``r_f1``, ``r_f2`` to 7-bit
    log over [0.5, 2.0]; pack ``(q_rt << 14) | (q_rf1 << 7) | q_rf2`` into a
    20-bit int. A speed change scales every Δt by one factor and every f by one
    factor, so all three ratios — and thus the whole hash set — are unchanged.

    Note: quantized ratios have far fewer distinct values than Shazam hashes, so
    the random-collision baseline is higher — the threshold MUST be calibrated
    (Task 7.4, ``calibrate_triplet.py``) before it drives clustering.
    """
    tri = cfg.get("fingerprint", {}).get("triplet", {}) or {}
    tmin = float(tri.get("tmin_sec", 0.5))
    tmax = float(tri.get("tmax_sec", 8.0))
    fanout = int(tri.get("fanout", 4))
    hashes: set = set()
    n = len(peaks)
    for i in range(n):
        t0, f0 = peaks[i]
        if f0 <= 0.0:
            continue
        c1 = 0
        for j in range(i + 1, n):
            t1, f1 = peaks[j]
            dt1 = t1 - t0
            if dt1 <= tmin:
                continue
            if dt1 > tmax:
                break
            if f1 <= 0.0:
                continue
            c2 = 0
            for k in range(j + 1, n):
                t2, f2 = peaks[k]
                dt2 = t2 - t1
                if dt2 <= 0.0:
                    continue
                if dt2 > tmax:
                    break
                if f2 <= 0.0:
                    continue
                q_rt = _quant_log(dt2 / dt1, 0.25, 4.0, 6)
                q_rf1 = _quant_log(f1 / f0, 0.5, 2.0, 7)
                q_rf2 = _quant_log(f2 / f0, 0.5, 2.0, 7)
                hashes.add((q_rt << 14) | (q_rf1 << 7) | q_rf2)
                c2 += 1
                if c2 >= fanout:
                    break
            c1 += 1
            if c1 >= fanout:
                break
    return hashes


def triplet_window(mono: np.ndarray, sr: int, cfg: dict) -> set:
    """Ratio-invariant triplet fingerprint from the fixed reference window.

    Uses the same window as :func:`fingerprint_window` (skips the intro, lands on
    the densest first songs) and the same peak front end, so the triplet and
    landmark fingerprints describe the same audio — but the triplet set also
    survives a global speed/pitch change (Task 5.3 speed-unknown pairs).
    """
    fp = cfg["fingerprint"]
    start = int(float(fp["window_start_sec"]) * sr)
    dur = int(float(fp["window_dur_sec"]) * sr)
    if start >= len(mono):
        start = 0
    window = np.array(mono[start:min(start + dur, len(mono))], dtype=np.float32)
    return triplet_hashes(_fingerprint_peaks(window, sr, cfg), cfg)
