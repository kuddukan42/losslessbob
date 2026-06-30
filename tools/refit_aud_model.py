"""Refit QUALITY_MODEL (AUD) from scan-18 stored metrics.

Uses existing quality_recording_metrics rows — no audio rescan needed.
Oversamples the low-quality tail (F/D-/D/D+/C-) so the model learns to
produce grades below C-.

Run from repo root:
    .venv/bin/python3 tools/refit_aud_model.py
    .venv/bin/python3 tools/refit_aud_model.py --apply   # patch config.py in-place
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import date

import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold
from scipy.stats import spearmanr

DB_PATH = "data/losslessbob.db"
SCAN_ID = 18

PREDS = [
    "hiss_floor_db", "bass_ratio_db", "mud_ratio_db", "onset_clarity",
    "directness", "crowd_snr_db", "dff_vert_occ",
    "harsh_ratio_db", "presence_ratio_db", "hf_ceiling_hz",
]

RATING_RANK = {
    "F": 1, "D-": 2, "D": 3, "D+": 4, "C-": 5, "C": 6, "C+": 7,
    "B-": 8, "B": 9, "B+": 10, "A-": 11, "A": 12, "A+": 13,
}

# Progressive oversampling weights for the low-quality tail.
OVERSAMPLE_WEIGHTS: dict[str, float] = {
    "F": 8.0, "D-": 6.0, "D": 4.0, "D+": 2.5, "C-": 1.5,
}

# Cap per-tier sample count for tiers above C (prevents the dominant A/A-/B+
# tiers from overwhelming the loss function even after tail oversampling).
UPPER_TIER_CAP: int = 200  # max rows from any single rating >= C+

# dff_vert_occ is injected at rerank time from dff_reports, not stored in
# metric_json.  Impute with the current model training median.
DFF_FALLBACK_MEDIAN = 1.0986


def load_data(conn: sqlite3.Connection) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load scan-18 AUD rows with ratings.

    Returns:
        X: raw feature matrix (n, len(PREDS)) with NaN for missing values.
        y: rating rank vector (n,).
        w: sample weight vector (n,).
    """
    rows = conn.execute("""
        SELECT qmr.metric_json, e.rating
        FROM quality_recording_metrics qmr
        JOIN entries e ON qmr.lb_number = e.lb_number
        WHERE qmr.scan_id = ?
          AND qmr.source_class = 'AUD'
          AND e.rating IS NOT NULL AND e.rating != ''
    """, (SCAN_ID,)).fetchall()

    # Bucket rows by rating so we can cap upper tiers before building arrays
    by_rating: dict[str, list] = {}
    skipped = 0
    for metric_json, rating in rows:
        rank = RATING_RANK.get(rating)
        if rank is None:
            skipped += 1
            continue
        m = json.loads(metric_json).get("metrics", {})
        row = []
        for p in PREDS:
            v = m.get(p)
            if p == "dff_vert_occ" and (v is None or (isinstance(v, float) and math.isnan(v))):
                v = DFF_FALLBACK_MEDIAN
            elif v is None or (isinstance(v, float) and math.isnan(v)):
                v = float("nan")
            row.append(float(v))
        by_rating.setdefault(rating, []).append((row, float(rank)))

    # Apply per-tier cap on upper tiers (C+ and above) to reduce dominance
    rng = np.random.default_rng(42)
    X_rows, y_rows, w_rows = [], [], []
    cap_ratings = {r for r, rank in RATING_RANK.items() if rank >= RATING_RANK["C+"]}
    for rating, items in by_rating.items():
        if rating in cap_ratings and len(items) > UPPER_TIER_CAP:
            idx = rng.choice(len(items), UPPER_TIER_CAP, replace=False)
            items = [items[i] for i in idx]
        wt = OVERSAMPLE_WEIGHTS.get(rating, 1.0)
        for row, rank in items:
            X_rows.append(row)
            y_rows.append(rank)
            w_rows.append(wt)

    if skipped:
        print(f"[warn] skipped {skipped} rows with unrecognised rating", file=sys.stderr)

    return np.array(X_rows), np.array(y_rows), np.array(w_rows)


def impute_medians(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Column-wise median imputation. Returns (X_imputed, medians)."""
    medians = np.nanmedian(X, axis=0)
    for j in range(X.shape[1]):
        if np.isnan(medians[j]):
            medians[j] = 0.0
        X[np.isnan(X[:, j]), j] = medians[j]
    return X, medians


def standardise(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Z-score standardise. Returns (X_z, means, stds)."""
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds < 1e-9] = 1.0
    return (X - means) / stds, means, stds


def cv_metrics(X_z: np.ndarray, y: np.ndarray,
               w: np.ndarray) -> tuple[float, float]:
    """5-fold CV Spearman rho and within-1-tier accuracy (weighted fit, unweighted eval)."""
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    rhos, w1s = [], []
    for train_idx, val_idx in kf.split(X_z):
        m = RidgeCV(alphas=[0.1, 0.5, 1.0, 5.0, 10.0, 50.0])
        m.fit(X_z[train_idx], y[train_idx], sample_weight=w[train_idx])
        pred = np.clip(m.predict(X_z[val_idx]), 1, 13)
        rho, _ = spearmanr(pred, y[val_idx])
        w1s.append(float(np.mean(np.abs(pred - y[val_idx]) <= 1)))
        rhos.append(float(rho))
    return float(np.mean(rhos)), float(np.mean(w1s))


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="patch concert_ranker/config.py in-place")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    X_raw, y, w = load_data(conn)
    n = len(y)

    from collections import Counter
    rank_to_letter = {v: k for k, v in RATING_RANK.items()}
    rank_counts = Counter(int(r) for r in y)
    print(f"Training set: n={n} AUD recordings with ratings (scan {SCAN_ID})")
    print("Rating distribution:")
    for rank in range(1, 14):
        letter = rank_to_letter[rank]
        cnt = rank_counts.get(rank, 0)
        wt = OVERSAMPLE_WEIGHTS.get(letter, 1.0)
        if cnt:
            print(f"  {letter:3s}  n={cnt:4d}  weight={wt:.1f}  eff_n={int(cnt * wt):4d}")

    # Impute + standardise
    X, medians = impute_medians(X_raw.copy())
    X_z, means, stds = standardise(X.copy())

    # Fit on full set
    model = RidgeCV(alphas=[0.1, 0.5, 1.0, 5.0, 10.0, 50.0])
    model.fit(X_z, y, sample_weight=w)

    print(f"\nRidgeCV alpha: {model.alpha_:.1f}")
    print(f"Intercept:     {model.intercept_:.5f}")
    print("\nWeights (standardised):")
    for p, coef in zip(PREDS, model.coef_):
        print(f"  {p:25s}  {coef:+.4f}")

    rho_cv, w1_cv = cv_metrics(X_z, y, w)
    print(f"\nCV (5-fold, weighted fit / unweighted eval):")
    print(f"  Spearman rho = {rho_cv:.4f},  within-1 = {w1_cv:.1%}")

    # Low-quality tail preview
    low_mask = y <= 4
    if low_mask.sum():
        preds_low = np.clip(model.predict(X_z[low_mask]), 1, 13)
        actual_low = y[low_mask]
        print(f"\nLow-quality tail (LB ≤ D+, n={low_mask.sum()}):")
        print(f"  Actual mean rank:    {actual_low.mean():.2f}")
        print(f"  Predicted mean rank: {preds_low.mean():.2f}")
        print(f"  % predicted ≤ D+ (rank 4): {(preds_low <= 4).mean():.1%}")
        print(f"  % predicted ≤ C- (rank 5): {(preds_low <= 5).mean():.1%}")

    config_block = (
        f"QUALITY_MODEL = {{\n"
        f"    # REFIT {date.today()}: scan-{SCAN_ID} full library ({n} AUD recordings).\n"
        f"    # Tail-weighted (F=8x D-=6x D=4x D+=2.5x C-=1.5x). Ridge alpha={model.alpha_:.1f}.\n"
        f"    # CV Spearman rho={rho_cv:.4f} (weighted fit / unweighted eval),"
        f" within-1={w1_cv:.1%}.\n"
        f'    "predictors": {json.dumps(PREDS)},\n'
        f'    "median": {json.dumps([round(float(v), 4) for v in medians])},\n'
        f'    "mean":   {json.dumps([round(float(v), 4) for v in means])},\n'
        f'    "std":    {json.dumps([round(float(v), 4) for v in stds])},\n'
        f'    "intercept": {model.intercept_:.5f},\n'
        f'    "weights":   {json.dumps([round(float(v), 4) for v in model.coef_])},\n'
        f"}}"
    )

    print(f"\n{'=' * 70}")
    print("New QUALITY_MODEL block:")
    print(config_block)

    if args.apply:
        import re
        cfg_path = "concert_ranker/config.py"
        with open(cfg_path) as f:
            src = f.read()
        # Match from QUALITY_MODEL = { through the closing }
        pattern = r"QUALITY_MODEL = \{[^}]*(?:\"[^\"]*\"[^}]*)?\}"
        new_src = re.sub(pattern, config_block, src, count=1)
        if new_src == src:
            print("\n[error] regex did not match QUALITY_MODEL block — not applied",
                  file=sys.stderr)
            sys.exit(1)
        with open(cfg_path, "w") as f:
            f.write(new_src)
        print(f"\n[ok] Patched {cfg_path}")


if __name__ == "__main__":
    main()
