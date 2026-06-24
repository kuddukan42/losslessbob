"""Scoring brain: turns stored RAW metrics into (a) human-readable categories,
(b) hard-disqualifier verdicts, (c) MAD-z sibling-relative scores, and (d)
a readable per-recording explanation. All of this reads stored raw values —
no audio — so re-tuning thresholds re-categorizes the corpus with zero rescans.

Two axes are kept deliberately separate, per the design requirement:
  ABSOLUTE band  — "muddy", "boomy", "buried in crowd"  (from raw value)
  RELATIVE rank  — "best of 6", "worst bass of the group" (from MAD-z vs siblings)
A recording can be the best of its siblings and still absolutely muddy; the
explanation says both.
"""
from __future__ import annotations

import numpy as np

from .config import (
    DISQUALIFIERS,
    FAMILY_WEIGHTS,
    POLARITY,
    QUALITY_BANDS,
    SEVERITY_BANDS,
    SIGNED_BANDS,
    resolve_band_set,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ABSOLUTE banding: raw metric value -> human label (or None if "fine")
# ─────────────────────────────────────────────────────────────────────────────
def band_metric(metric: str, value: float, signed: dict | None = None,
                severity: dict | None = None, quality: dict | None = None) -> str | None:
    """Band one raw value to a label using the given band sets (global by default).

    Passing per-decade band dicts (see :data:`config.DECADE_BANDS`) lets a
    recording be judged against the norms of its own era.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    signed = SIGNED_BANDS if signed is None else signed
    severity = SEVERITY_BANDS if severity is None else severity
    quality = QUALITY_BANDS if quality is None else quality

    if metric in signed:
        low_cut, low_label, high_cut, high_label = signed[metric]
        if value <= low_cut:
            return low_label
        if value >= high_cut:
            return high_label
        return None  # neutral / balanced

    if metric in severity:
        for cutoff, label in severity[metric]:
            if value <= cutoff:
                return label
        return severity[metric][-1][1]

    if metric in quality:
        for cutoff, label in quality[metric]:
            if value <= cutoff:
                return label
        return quality[metric][-1][1]

    return None


def all_bands(raw: dict, decade: int | None = None,
              source_class: str | None = None) -> list[str]:
    """All non-None absolute category labels for one recording's raw metrics.

    The recording is banded against the norms of its own source class and era:
    SBD/FM use the class-global SBD bands, AUD/UNKNOWN use per-decade bands, and
    everything falls back to the global bands (see ``config.resolve_band_set``).
    """
    bset = resolve_band_set(decade, source_class)
    signed, severity, quality = bset["SIGNED"], bset["SEVERITY"], bset["QUALITY"]
    out = []
    for metric, value in raw.items():
        label = band_metric(metric, value, signed, severity, quality)
        if label:
            out.append(label)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 2. HARD DISQUALIFIERS: veto / demote before any ranking
# ─────────────────────────────────────────────────────────────────────────────
def check_disqualifiers(raw: dict) -> tuple[list[str], bool]:
    """Return (labels, vetoed). vetoed=True means exclude from ranking entirely."""
    labels, vetoed = [], False
    for dq in DISQUALIFIERS:
        v = raw.get(dq.metric)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        tripped = (v > dq.threshold) if dq.direction == "above" else (v < dq.threshold)
        if tripped:
            labels.append(dq.label)
            if dq.veto:
                vetoed = True
    return labels, vetoed


# ─────────────────────────────────────────────────────────────────────────────
# 3. MAD-z normalization across the sibling set (robust; good for small N)
# ─────────────────────────────────────────────────────────────────────────────
def mad_z(values: np.ndarray) -> np.ndarray:
    """Robust z-score: (x - median) / (1.4826 * MAD). Falls back to std."""
    v = np.asarray(values, dtype=float)
    med = np.nanmedian(v)
    mad = np.nanmedian(np.abs(v - med))
    scale = 1.4826 * mad
    if scale < 1e-9:
        sd = np.nanstd(v)
        scale = sd if sd > 1e-9 else 1.0
    return (v - med) / scale


def normalize_siblings(sibling_raw: dict[int, dict]) -> dict[int, dict]:
    """sibling_raw: {lb_number: {metric: raw_value}}. Returns per-LB signed
    z-scores already oriented so +z = better (polarity applied)."""
    lbs = list(sibling_raw.keys())
    metrics = set().union(*[d.keys() for d in sibling_raw.values()])
    z = {lb: {} for lb in lbs}
    for m in metrics:
        pol = POLARITY.get(m, 0)
        if pol == 0:
            continue  # signed/banded metrics are not linearly fused
        col = np.array([sibling_raw[lb].get(m, np.nan) for lb in lbs], dtype=float)
        zc = mad_z(col) * pol
        for lb, val in zip(lbs, zc, strict=False):
            z[lb][m] = float(val)
    return z


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fusion: family scores -> track score -> recording score
# ─────────────────────────────────────────────────────────────────────────────
FAMILY_METRICS = {
    "clarity":    ["presence_ratio_db", "directness", "onset_clarity"],
    "crowd":      ["crowd_snr_db", "intrusion_rate", "handling_rate"],
    "tonal":      ["mud_ratio_db", "harsh_ratio_db", "sibilance_ratio_db"],
    "distortion": ["clip_fraction", "crest_factor_db", "hiss_floor_db", "hum_excess_db"],
    "spatial":    ["channel_balance_db", "azimuth_lag_us"],
}


def family_scores(z: dict) -> dict:
    out = {}
    for fam, metrics in FAMILY_METRICS.items():
        vals = [z[m] for m in metrics if m in z and not np.isnan(z[m])]
        out[fam] = float(np.mean(vals)) if vals else 0.0
    return out


def track_score(fam: dict) -> float:
    num = sum(FAMILY_WEIGHTS[f] * fam.get(f, 0.0) for f in FAMILY_WEIGHTS)
    den = sum(FAMILY_WEIGHTS.values())
    return num / den


def recording_score(track_scores: list[float]) -> dict:
    """Aggregate track scores with consistency + worst-track protection."""
    ts = np.asarray(track_scores, dtype=float)
    ts = ts[~np.isnan(ts)]
    if ts.size == 0:
        return {"mean_track_quality": 0.0, "consistency": 0.0,
                "worst_track": 0.0, "final": 0.0}
    mean_q = float(ts.mean())
    consistency = -float(ts.std())          # lower variance = better (negated)
    worst = float(ts.min())                 # protect against one bad/spliced track
    final = mean_q + 0.5 * consistency + 0.5 * worst
    return {"mean_track_quality": mean_q, "consistency": consistency,
            "worst_track": worst, "final": final}


# ─────────────────────────────────────────────────────────────────────────────
# 5. EXPLAIN: combine absolute bands + relative rank into a readable verdict
# ─────────────────────────────────────────────────────────────────────────────
def explain_recording(lb, raw, z, rank, n_siblings, dq_labels, vetoed,
                      decade=None, source_class=None) -> str:
    parts = []

    if vetoed:
        parts.append(f"LB{lb}: EXCLUDED — {', '.join(dq_labels)}.")
        return " ".join(parts)

    # rank line
    if n_siblings > 1:
        ordinal = f"#{rank} of {n_siblings}"
        if rank == 1:
            parts.append(f"LB{lb}: recommended ({ordinal}).")
        else:
            parts.append(f"LB{lb}: ranked {ordinal}.")
    else:
        parts.append(f"LB{lb}:")

    # absolute character (what it sounds like, regardless of siblings) — banded
    # against the recording's own source class + era
    bands = all_bands(raw, decade, source_class)
    if bands:
        parts.append("Sounds " + _join(bands) + ".")

    # demerits that don't veto but matter
    if dq_labels:
        parts.append("Flags: " + _join(dq_labels) + ".")

    # relative strengths/weaknesses (where it beats / trails siblings most)
    if n_siblings > 1 and z:
        ranked = sorted(z.items(), key=lambda kv: kv[1])
        worst_m, worst_v = ranked[0]
        best_m, best_v = ranked[-1]
        if best_v > 0.8:
            parts.append(f"Best in group for {_pretty(best_m)}.")
        if worst_v < -0.8:
            parts.append(f"Weakest in group for {_pretty(worst_m)}.")

    return " ".join(parts)


def _join(items):
    items = list(dict.fromkeys(items))  # dedupe, preserve order
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


_PRETTY = {
    "crowd_snr_db": "crowd separation", "presence_ratio_db": "vocal presence",
    "directness": "directness", "onset_clarity": "transient clarity",
    "mud_ratio_db": "low-mid clarity", "harsh_ratio_db": "smoothness",
    "hiss_floor_db": "noise floor", "hum_excess_db": "freedom from hum",
    "crest_factor_db": "dynamics", "channel_balance_db": "channel balance",
    "azimuth_lag_us": "channel alignment",
}


def _pretty(metric):
    return _PRETTY.get(metric, metric)
