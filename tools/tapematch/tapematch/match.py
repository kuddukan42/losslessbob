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
from .audio import to_mono
from .align import local_lag


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
    # crude HF emphasis: first difference removes shared low-freq musical bulk,
    # leaving noise floor / room tone / hiss where lineage lives
    ra = np.diff(ra); ob = np.diff(ob)
    ra = (ra - ra.mean()) / (ra.std() + 1e-9)
    ob = (ob - ob.mean()) / (ob.std() + 1e-9)
    return float(np.dot(ra, ob) / len(ra))


def _envelope(mono, sr, env_rate=100):
    """Low-rate energy envelope -- drift-tolerant coarse alignment feature."""
    win = int(sr / env_rate)
    n = (len(mono) // win) * win
    e = mono[:n].reshape(-1, win)
    env = np.sqrt((e ** 2).mean(axis=1) + 1e-12)
    env = np.log(env + 1e-6)
    return (env - env.mean()) / (env.std() + 1e-9), env_rate


def estimate_ratio(ref, other, sr, anchors, cfg):
    """Coarse speed-ratio search on energy envelopes. Resampling the raw
    waveform under unknown drift smears its correlation peak to noise, so we
    align the low-rate envelope (robust to drift) over a grid of ratios and
    pick the ratio whose best lag gives the strongest envelope correlation."""
    er, rate = _envelope(ref, sr)
    eo, _ = _envelope(other, sr)
    best_ratio, best_peak = 1.0, -1.0
    for ratio in np.linspace(0.985, 1.015, 61):
        # resample `other` envelope onto ref clock and correlate
        from scipy.signal import resample
        m = max(8, int(len(eo) * ratio))
        eo_r = resample(eo, m)
        eo_r = (eo_r - eo_r.mean()) / (eo_r.std() + 1e-9)
        n = min(len(er), len(eo_r))
        xc = correlate(er[:n], eo_r[:n], mode="full")
        peak = np.max(np.abs(xc)) / n
        if peak > best_peak:
            best_peak, best_ratio = peak, ratio
    return best_ratio


def pairwise_matrix(streams_mono, sr, anchors, cfg):
    """streams_mono: dict name->mono array, already trimmed.
    For each pair: estimate speed ratio, resample to remove it, then average
    residual correlation over speed-corrected anchor windows."""
    from .audio import resample_ratio
    names = list(streams_mono.keys())
    n = len(names)
    M = np.eye(n)
    a = cfg["align"]; w = cfg["anchors"]["window_sec"]
    ppm_thr = a["ratio_flag_ppm"]
    for i in range(n):
        for j in range(i + 1, n):
            ri = streams_mono[names[i]]
            rj = streams_mono[names[j]]
            ratio = estimate_ratio(ri, rj, sr, anchors, cfg)
            if abs(ratio - 1.0) * 1e6 > ppm_thr:
                rj = resample_ratio(rj, ratio)  # stretch rj onto ri's clock
            corrs = []
            for ctr in anchors:
                lag, peak = local_lag(ri, rj, sr, ctr, w, a["max_lag_sec"])
                if lag is None:
                    continue
                ra, ob = aligned_window(ri, rj, sr, ctr, w, lag)
                corrs.append(abs(residual_corr(ra, ob)))
            val = float(np.median(corrs)) if corrs else 0.0
            M[i, j] = M[j, i] = val
    return names, M


def cluster(names, M, threshold):
    """Connected-components clustering: link pairs above threshold."""
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
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(names[i])
    return list(groups.values())


def lineage_evidence(stream, sr, cfg):
    """Per-source physical evidence for generation ordering.
    NOTE: for real cassette/DAT/lossy discrimination, run this on NATIVE-rate
    audio (44.1k+). At a low analysis SR the HF ceiling is capped by Nyquist."""
    mono = to_mono(stream)
    f, t, Z = stft(mono, fs=sr, nperseg=4096, boundary=None)
    psd = (np.abs(Z) ** 2).mean(axis=1)
    psd_db = 10 * np.log10(psd + 1e-12)
    floor_db = np.percentile(psd_db, 20)
    # highest 1 kHz band (below Nyquist) still carrying real energy
    nyq = sr / 2
    probes = [hz for hz in cfg["lineage"]["hf_ceiling_probe_hz"] if hz + 1000 < nyq]
    if not probes:  # analysis SR too low for configured probes -> scan generic grid
        probes = list(range(1000, int(nyq) - 1000, 1000))
    ceil = 0.0
    for hz in probes:
        band = (f >= hz) & (f < hz + 1000)
        if band.any() and psd_db[band].mean() > floor_db + 8:
            ceil = hz
    noise_floor_db = float(np.percentile(psd_db, 5))
    return {"hf_ceiling_hz": float(ceil), "noise_floor_db": noise_floor_db,
            "nyquist_capped": not [h for h in cfg["lineage"]["hf_ceiling_probe_hz"] if h + 1000 < nyq]}
