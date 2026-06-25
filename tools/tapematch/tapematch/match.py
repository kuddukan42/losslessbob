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


def estimate_ratio(ref, other, sr, anchors, cfg):
    """Coarse speed-ratio search on energy envelopes.

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


def fingerprint_window(mono: np.ndarray, sr: int, cfg: dict) -> set:
    """Build a spectral-peak landmark fingerprint from a fixed reference window.

    Shazam-style: extract STFT local maxima, then for each peak form
    (f_anchor, f_target, Δt) hash pairs with the next `fanout` peaks within
    `dt_bins` time steps.  Hashes are packed into single ints for fast set ops.

    The window skips the first few minutes (intro/tuning noise) and lands on the
    first full songs — densest unique content, unaffected by end-of-show drop-outs.

    Offset-invariant by construction: Δt is relative within each recording, so
    absolute timing differences (trim offsets, edits) do not affect matching.
    """
    fp = cfg["fingerprint"]
    start = int(float(fp["window_start_sec"]) * sr)
    dur   = int(float(fp["window_dur_sec"]) * sr)
    if start >= len(mono):
        start = 0
    window = np.array(mono[start:min(start + dur, len(mono))], dtype=np.float32)

    mag = _stft_mag(window, sr, int(fp["nperseg"]), int(fp["hop"]))
    del window

    # Restrict peak-finding to the HF band (e.g. 6–8 kHz) when configured.
    # Musical note energy dominates below ~5 kHz and is shared by all recordings
    # of the same concert, pushing same-show different-source Dice to 0.15–0.50.
    # The 6–8 kHz band is dominated by tape hiss and room reflections that are
    # specific to the recording chain, reducing different-source same-show scores
    # to <0.10 and enabling a lower cluster_threshold (~0.30–0.35).
    f_offset = 0
    if "hf_band_hz" in fp:
        lo_hz, hi_hz = fp["hf_band_hz"]
        nperseg = int(fp["nperseg"])
        lo_bin = int(lo_hz * nperseg / sr)
        hi_bin = min(int(hi_hz * nperseg / sr), mag.shape[0] - 1)
        mag = mag[lo_bin:hi_bin + 1, :]
        f_offset = lo_bin  # unused in hashing but kept for clarity

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


def fingerprint_score(ha: set, hb: set) -> float:
    """Dice coefficient between two fingerprint hash sets (0 = no overlap, 1 = identical)."""
    if not ha or not hb:
        return 0.0
    return 2.0 * len(ha & hb) / (len(ha) + len(hb))


def cluster(names, M, threshold, W=None, w_threshold=0.0, F=None, f_threshold=0.0,
            H=None, h_threshold=0.0, H_med=None, h_med_threshold=0.0):
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
            if M[i, j] >= threshold:
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
