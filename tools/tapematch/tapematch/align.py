"""Anchor detection + alignment.

Anchors are sharp crowd transients (claps/whistles/yells) located by onset
strength, preferably in low-energy gaps. They serve as both alignment locks and
source-identity fingerprints. Alignment is content-anchored, never file-position
based: we cross-correlate a window around each anchor to find the local lag, then
read the lag-vs-position curve:
    flat line      -> aligned, same playback speed
    constant slope -> fixed speed ratio (resample to fix)
    staircase      -> gap edits / splices
    single jump    -> missing or extra material
"""
from __future__ import annotations
import numpy as np
from scipy.signal import stft, correlate
from .audio import to_mono


def onset_strength(mono, sr, hop_sec=0.02):
    """Spectral-flux onset strength, computed in 1-minute chunks.

    The full-signal STFT for a 2-hour show at 16 kHz with nperseg=640 creates a
    ~924 MB complex64 Z matrix.  Processing 60-second blocks caps each Z at
    ~7.7 MB; Z and mag are freed before the next iteration.
    """
    nper = int(0.04 * sr)
    hop = int(hop_sec * sr)
    chunk_samp = 60 * sr  # 1-minute blocks

    t_parts: list[np.ndarray] = []
    flux_parts: list[np.ndarray] = []

    for start in range(0, len(mono), chunk_samp):
        chunk = mono[start:start + chunk_samp]
        if len(chunk) < nper:
            break
        _, t_c, Z = stft(chunk, fs=sr, nperseg=nper, noverlap=nper - hop, boundary=None)
        mag = np.abs(Z)
        del Z
        flux = np.maximum(0, np.diff(mag, axis=1)).sum(axis=0)
        del mag
        flux = np.concatenate([[0.0], flux])
        t_parts.append(t_c + start / sr)
        flux_parts.append(flux)

    if not t_parts:
        return np.array([]), np.array([])
    return np.concatenate(t_parts), np.concatenate(flux_parts)


def pick_anchors(mono, sr, cfg):
    """Return anchor center times (sec), spread early->late across the body."""
    c = cfg["anchors"]
    t, flux = onset_strength(mono, sr)
    thr = np.percentile(flux, c["onset_percentile"])
    cand = t[flux >= thr]
    if len(cand) == 0:
        cand = t[np.argsort(flux)[-c["n_anchors"]:]]
    dur = len(mono) / sr
    edges = np.linspace(0, dur, c["n_anchors"] + 1)
    anchors = []
    for i in range(c["n_anchors"]):
        lo, hi = edges[i], edges[i + 1]
        in_bin = (t >= lo) & (t < hi)
        if not in_bin.any():
            continue
        idx = np.where(in_bin)[0]
        best = idx[np.argmax(flux[idx])]
        anchors.append(float(t[best]))
    return anchors


def local_lag(ref_mono, other_mono, sr, center_sec, window_sec, max_lag_sec):
    """Cross-correlate a window of `other` against `ref` near center_sec.
    Returns (lag_sec, peak_corr). lag is how much `other` is delayed vs ref."""
    half = int(window_sec * sr / 2)
    c = int(center_sec * sr)
    a0, a1 = max(0, c - half), min(len(ref_mono), c + half)
    b0, b1 = max(0, c - half), min(len(other_mono), c + half)
    ra = ref_mono[a0:a1]
    ob = other_mono[b0:b1]
    n = min(len(ra), len(ob))
    if n < sr:
        return None, 0.0
    ra, ob = ra[:n], ob[:n]
    ra = (ra - ra.mean()) / (ra.std() + 1e-9)
    ob = (ob - ob.mean()) / (ob.std() + 1e-9)
    xc = correlate(ob, ra, mode="full")
    lags = np.arange(-n + 1, n)
    maxl = int(max_lag_sec * sr)
    keep = np.abs(lags) <= maxl
    xc, lags = xc[keep], lags[keep]
    k = np.argmax(np.abs(xc))
    peak = xc[k] / n
    return lags[k] / sr, float(peak)


def local_lag_centered(ref_mono, other_mono, sr, center_sec, window_sec, max_lag_sec, lag_center_sec):
    """Like `local_lag`, but centers the +-max_lag_sec residual search on
    `lag_center_sec` instead of zero.

    Used for predicted-lag mode (CC_TAPEMATCH_FIXES.md Task 4): under a constant
    speed offset, accumulated drift at a given window can exceed max_lag_sec, so
    the search is re-centered on the drift predicted from the pair's speed ratio.
    Only the search offset changes -- no waveform resampling.

    Returns (lag_sec, peak_corr) where lag_sec is the absolute lag (i.e.
    lag_center_sec plus whatever residual offset the search finds), in the same
    sign convention as `local_lag`.
    """
    half = int(window_sec * sr / 2)
    c = int(center_sec * sr)
    a0, a1 = max(0, c - half), min(len(ref_mono), c + half)
    ra = ref_mono[a0:a1]
    n_ref = len(ra)
    if n_ref < sr:
        return None, 0.0

    center_shift = int(round(lag_center_sec * sr))
    maxl = int(max_lag_sec * sr)
    b0 = max(0, a0 + center_shift - maxl)
    b1 = min(len(other_mono), a1 + center_shift + maxl)
    ob = other_mono[b0:b1]
    if len(ob) < n_ref:
        return None, 0.0

    ra_n = (ra - ra.mean()) / (ra.std() + 1e-9)
    ob_n = (ob - ob.mean()) / (ob.std() + 1e-9)

    xc = correlate(ob_n, ra_n, mode="valid")
    k = np.argmax(np.abs(xc))
    peak = xc[k] / n_ref
    lag_sec = (b0 + k - a0) / sr
    return lag_sec, float(peak)


def lag_curve(ref_mono, other_mono, sr, anchors, cfg):
    """Lag and peak-corr at each anchor -> the diagnostic curve."""
    a = cfg["align"]
    w = cfg["anchors"]["window_sec"]
    rows = []
    for ctr in anchors:
        lag, peak = local_lag(ref_mono, other_mono, sr, ctr,
                              w, a["max_lag_sec"])
        rows.append({"center_sec": ctr, "lag_sec": lag, "peak": peak})
    return rows


def interpret_curve(rows, cfg):
    """Classify the lag-vs-position curve and estimate speed ratio."""
    a = cfg["align"]
    valid = [r for r in rows if r["lag_sec"] is not None]
    if len(valid) < 2:
        return {"kind": "insufficient", "ratio": 1.0}
    x = np.array([r["center_sec"] for r in valid])
    y = np.array([r["lag_sec"] for r in valid])
    slope, intercept = np.polyfit(x, y, 1)
    ratio = 1.0 + slope
    resid = y - (slope * x + intercept)
    steps = np.abs(np.diff(y))
    kind = "aligned"
    if np.max(steps) > a["step_flag_sec"] and np.std(resid) > a["step_flag_sec"]:
        kind = "staircase/splice"
    elif abs(ratio - 1.0) * 1e6 > a["ratio_flag_ppm"]:
        kind = "constant-speed-offset"
    return {"kind": kind, "ratio": float(ratio),
            "ppm": float((ratio - 1.0) * 1e6),
            "max_step_sec": float(steps.max() if len(steps) else 0.0)}


def union_staircase_sources(*speed_infos: dict[str, dict]) -> set[str]:
    """Sources classified "staircase/splice" in ANY of the given speed_info dicts.

    A source's lag-curve "kind" is always "reference" relative to itself, so a
    single speed_info pass can never flag the current reference source as
    staircase. Each lag-curve pass uses a different reference (initial ref,
    then re-selected central ref), so taking the union across passes lets a
    source's staircase status be detected from whichever pass it isn't the
    reference in (CC_TAPEMATCH_FIXES.md Task 5).

    Args:
        *speed_infos: one or more {source_name: {"kind": ..., ...}} dicts,
            one per lag-curve pass.

    Returns:
        Set of source names classified "staircase/splice" in at least one pass.
    """
    return {
        name
        for info in speed_infos
        for name, d in info.items()
        if d.get("kind") == "staircase/splice"
    }
