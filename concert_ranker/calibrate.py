"""Calibration harness. Runs on YOUR machine via Claude Code, against real audio
and the existing LB ground truth. Turns the provisional # CALIBRATE thresholds
into fitted, trustworthy ones — WITHOUT which the bands and disqualifiers are
only first-principles guesses (as the synthetic test makes obvious).

Ground truth available in losslessbob.db:
  entries.rating        — A+..F  (ordinal quality label; RATING_RANK in the GUI)
  entries.source_chain  — mine -> SBD / AUD / FM / UNKNOWN (source class)
  entries.description   — mine -> human commentary keywords (validation oracle)
  my_collection.disk_path — where the audio actually is

Three jobs:
  1. fit_thresholds   — find band cutoffs that separate the rating tiers,
                        WITHIN each source class (an A-AUD != an A-SBD).
  2. validate_labels  — precision/recall of each algorithmic category label
                        against the mined commentary on the same recordings.
  3. score_separation — report which metrics actually track the human rating
                        (drop the ones that don't — they're dead weight).

This module defines the harness; Claude Code supplies the real metric values by
running the scan over the stratified sample, and the labels by mining the DB.
"""
from __future__ import annotations

import numpy as np

RATING_RANK = {'A+': 13, 'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8,
               'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3, 'D-': 2, 'F': 1}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Does a metric actually track the human rating? (Spearman within class)
# ─────────────────────────────────────────────────────────────────────────────
def score_separation(samples: list[dict]) -> dict:
    """samples: [{lb, rating, source_class, metrics:{name:value}}, ...]

    Returns per (source_class, metric) the rank correlation between the metric
    and the A-F rating. Metrics with |rho| below a floor are flagged useless —
    they add noise to fusion and should be dropped or down-weighted.
    """
    from scipy.stats import spearmanr
    by_class: dict[str, list[dict]] = {}
    for s in samples:
        by_class.setdefault(s["source_class"], []).append(s)

    report = {}
    for cls, rows in by_class.items():
        if len(rows) < 5:
            report[cls] = {"_warning": f"only {len(rows)} samples; unreliable"}
            continue
        ranks = np.array([RATING_RANK.get(r["rating"], np.nan) for r in rows],
                         dtype=float)
        metric_names = set().union(*[r["metrics"].keys() for r in rows])
        cls_report = {}
        for m in metric_names:
            # force float so stored None (NaN coerced on persist) -> np.nan rather
            # than an object-dtype array that np.isnan can't handle
            vals = np.array([r["metrics"].get(m) if r["metrics"].get(m) is not None
                             else np.nan for r in rows], dtype=float)
            ok = ~(np.isnan(vals) | np.isnan(ranks))
            if ok.sum() < 5:
                continue
            rho, p = spearmanr(vals[ok], ranks[ok])
            rho_f, p_f = float(rho), float(p)
            cls_report[m] = {"rho": rho_f, "p": p_f,
                             "useful": bool(abs(rho_f) >= 0.3 and p_f < 0.1)}
        report[cls] = cls_report
    return report


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fit band cutoffs that separate rating tiers, within a source class
# ─────────────────────────────────────────────────────────────────────────────
def fit_thresholds(samples: list[dict], metric: str, source_class: str,
                   tiers=(("A", ("A+", "A", "A-")), ("C", ("C+", "C", "C-")),
                          ("F", ("D+", "D", "D-", "F")))) -> dict:
    """Find the metric value that best splits 'good' (A) from 'bad' (D/F) for one
    source class. Returns the threshold and how cleanly it separates (AUC-like).

    Used to set the SEVERITY/QUALITY band cutoffs in config.py from real data
    instead of first-principles guesses.
    """
    rows = [s for s in samples if s["source_class"] == source_class]
    good_vals, bad_vals = [], []
    good_set = set(tiers[0][1])
    bad_set = set(tiers[-1][1])
    for r in rows:
        v = r["metrics"].get(metric)
        if v is None or np.isnan(v):
            continue
        if r["rating"] in good_set:
            good_vals.append(v)
        elif r["rating"] in bad_set:
            bad_vals.append(v)

    if len(good_vals) < 3 or len(bad_vals) < 3:
        return {"metric": metric, "source_class": source_class,
                "error": "insufficient samples in good/bad tiers"}

    good_vals, bad_vals = np.array(good_vals), np.array(bad_vals)
    # candidate thresholds across the combined range; pick max class separation
    candidates = np.percentile(np.r_[good_vals, bad_vals], np.linspace(5, 95, 37))
    best_thr, best_sep = None, -1.0
    good_high = good_vals.mean() > bad_vals.mean()  # is "good" the higher side?
    for thr in candidates:
        if good_high:
            sep = (good_vals > thr).mean() * (bad_vals <= thr).mean()
        else:
            sep = (good_vals < thr).mean() * (bad_vals >= thr).mean()
        if sep > best_sep:
            best_sep, best_thr = sep, float(thr)
    return {"metric": metric, "source_class": source_class,
            "threshold": best_thr, "separation": float(best_sep),
            "good_higher": bool(good_high),
            "n_good": len(good_vals), "n_bad": len(bad_vals)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate category labels against mined human commentary
# ─────────────────────────────────────────────────────────────────────────────
# Map algorithmic band labels -> commentary keywords that should co-occur.
LABEL_KEYWORDS = {
    "muddy":               ["muddy", "mud", "murky", "boomy low"],
    "boomy / bass-heavy":  ["boomy", "bass heavy", "bassy", "too much bass"],
    "thin / bass-light":   ["thin", "tinny", "no bass", "bass light", "lacks bass"],
    "harsh":               ["harsh", "shrill", "piercing", "fatiguing"],
    "sibilant":            ["sibilant", "essy", "sibilance"],
    "bright / airy":       ["bright", "airy", "crisp", "detailed highs"],
    "dull / closed":       ["dull", "muffled", "veiled", "closed", "no highs"],
    "buried in crowd":     ["buried", "crowd", "noisy crowd", "talkers", "distant aud"],
    "crowd-heavy":         ["crowd", "audience noise", "chatter"],
    "hissy":               ["hiss", "hissy", "tape hiss", "noisy"],
    "distant / roomy":     ["distant", "roomy", "reverberant", "back of", "far"],
    "present vocals":      ["clear vocal", "vocals up front", "present", "intimate"],
    "lossy source suspected": ["lossy", "mp3", "transcode", "upsampled", "fake flac"],
    "open dynamics":       ["dynamic", "punchy", "lively"],
    "compressed / squashed": ["compressed", "squashed", "flat", "lifeless"],
}


def validate_labels(samples: list[dict], banded: dict[int, list[str]]) -> dict:
    """samples carry mined commentary text; banded is {lb: [algorithmic labels]}.

    For each label, compute precision (when the algorithm says it, does the human
    commentary agree?) and recall (when the human says it, did the algorithm
    catch it?). A label that disagrees with humans is miscalibrated.
    """
    text_by_lb = {s["lb"]: (s.get("commentary") or "").lower() for s in samples}

    def human_says(lb, label):
        kws = LABEL_KEYWORDS.get(label, [])
        txt = text_by_lb.get(lb, "")
        return any(k in txt for k in kws)

    report = {}
    all_labels = set(LABEL_KEYWORDS)
    for label in all_labels:
        tp = fp = fn = 0
        for lb in text_by_lb:
            algo = label in banded.get(lb, [])
            human = human_says(lb, label)
            if algo and human:
                tp += 1
            elif algo and not human:
                fp += 1
            elif human and not algo:
                fn += 1
        if tp + fp + fn == 0:
            continue
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        report[label] = {"precision": precision, "recall": recall,
                         "tp": tp, "fp": fp, "fn": fn}
    return report
