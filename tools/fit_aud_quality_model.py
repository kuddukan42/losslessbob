#!/usr/bin/env python3
"""Fit the AUD QUALITY_MODEL ridge regression and print updated config block.

Loads AUD recordings from quality_recording_metrics for a given scan_id,
augments each row with dff_vert_occ = log1p(dff_reports.vert_occ) where
available, then runs forward selection over the candidate predictor pool and
fits a ridge regression to predict the LB rating rank (1=F .. 13=A+).

Outputs:
  - 5-fold CV Spearman / within-one-tier metrics
  - The QUALITY_MODEL dict block ready to paste into config.py

Run from the project root:
    python tools/fit_aud_quality_model.py            # scan_id=8 (full AUD corpus)
    python tools/fit_aud_quality_model.py --scan-id 17 --alpha 0.3  # validation
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from backend.paths import DB_PATH
from concert_ranker.calibrate import RATING_RANK

# ── candidate predictor pool ──────────────────────────────────────────────────
_CANDIDATE_POOL = [
    "hiss_floor_db",
    "bass_ratio_db",
    "mud_ratio_db",
    "onset_clarity",
    "directness",
    "crowd_snr_db",
    "harsh_ratio_db",
    "presence_ratio_db",
    "dff_vert_occ",          # log1p(dff_reports.vert_occ)
    "hf_ceiling_hz",
    "spectral_centroid_hz",
    "air_ratio_db",
    "crest_factor_db",
    "hum_excess_db",
    "speech_band_snr_db",    # 1-4 kHz SNR loud vs quiet (loud vs quiet frames)
    "brickwall_score",       # pre-amp saturation via mid-amp slope regularity
    "single_ch_transient_count",  # L/R asymmetric impulse events (mic hits)
]

# ── commentary labels for the Δ/σ audit ──────────────────────────────────────
_COMMENTARY_BAD  = ["muffled", "boomy", "very distant", "too distant", "muddy sound"]
_COMMENTARY_GOOD = ["upfront vocal", "vocals upfront", "excellent sound", "upfront sound",
                    "close mic", "close-mic", "dpa", "schoeps", "neumann km"]


def commentary_audit(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Print Δ/σ effect size for each metric between good/bad commentary labels.

    Good = upfront/excellent/close-mic; bad = muffled/boomy/distant.
    Uses entries.description from the DB; only AUD LBs present in ``rows``.

    "BACKWARDS" means Δ/σ sign disagrees with the univariate Spearman rho
    vs LB rating — i.e. the metric separates commentary groups in the opposite
    direction from how it tracks quality overall. "no signal" means |Δ/σ| < 0.2.
    """
    import math
    import statistics

    lbs = [r["lb"] for r in rows]
    placeholders = ",".join("?" * len(lbs))
    desc_rows = conn.execute(
        f"SELECT lb_number, description FROM entries WHERE lb_number IN ({placeholders})",
        lbs,
    ).fetchall()
    desc_map = {int(r[0]): (r[1] or "").lower() for r in desc_rows}

    good_lbs, bad_lbs = set(), set()
    for lb, desc in desc_map.items():
        if any(w in desc for w in _COMMENTARY_BAD):
            bad_lbs.add(lb)
        elif any(w in desc for w in _COMMENTARY_GOOD):
            good_lbs.add(lb)

    # Univariate Spearman rho vs rating for each metric — used to determine
    # "expected direction" so BACKWARDS means commentary disagrees with rating.
    from scipy.stats import spearmanr
    metrics_by_lb = {r["lb"]: r["metrics"] for r in rows}
    rating_ranks = {r["lb"]: r["rank"] for r in rows}
    all_metrics = sorted({k for m in metrics_by_lb.values() for k in m})
    rho_map: dict[str, float] = {}
    for k in all_metrics:
        vals, rnks = [], []
        for lb, m in metrics_by_lb.items():
            v = m.get(k)
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                vals.append(v)
                rnks.append(rating_ranks[lb])
        if len(vals) >= 10:
            rho, _ = spearmanr(vals, rnks)
            rho_map[k] = float(rho)

    print(f"\nCommentary audit  (good n={len(good_lbs)}, bad n={len(bad_lbs)}):")
    print(f"  {'Metric':<28} {'Good µ':>9} {'Bad µ':>9} {'Δ/σ':>7} {'rho':>7}  note")
    print("  " + "-" * 76)

    results = []
    for k in all_metrics:
        gv = [metrics_by_lb[lb][k] for lb in good_lbs
              if lb in metrics_by_lb and metrics_by_lb[lb].get(k) is not None
              and not (isinstance(metrics_by_lb[lb][k], float) and math.isnan(metrics_by_lb[lb][k]))]
        bv = [metrics_by_lb[lb][k] for lb in bad_lbs
              if lb in metrics_by_lb and metrics_by_lb[lb].get(k) is not None
              and not (isinstance(metrics_by_lb[lb][k], float) and math.isnan(metrics_by_lb[lb][k]))]
        if len(gv) < 5 or len(bv) < 5:
            continue
        gm, bm = statistics.mean(gv), statistics.mean(bv)
        gs = statistics.stdev(gv) if len(gv) > 1 else 1e-9
        bs = statistics.stdev(bv) if len(bv) > 1 else 1e-9
        pooled = ((gs ** 2 + bs ** 2) / 2) ** 0.5 or 1e-9
        d = (gm - bm) / pooled
        results.append((k, gm, bm, d))

    results.sort(key=lambda x: abs(x[3]), reverse=True)
    for k, gm, bm, d in results:
        rho = rho_map.get(k, float("nan"))
        note = ""
        if abs(d) < 0.2:
            note = "no signal"
        elif not math.isnan(rho) and abs(d) >= 0.2:
            # BACKWARDS: commentary Δ/σ sign contradicts rating-based rho sign
            if (d > 0) != (rho > 0):
                note = "BACKWARDS vs rating"
        print(f"  {k:<28} {gm:>9.3f} {bm:>9.3f} {d:>7.2f} {rho:>7.3f}  {note}")


def load_rows(conn: sqlite3.Connection, scan_id: int) -> list[dict]:
    """Load AUD metric rows from a scan, augmented with dff_vert_occ."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT m.lb_number, m.metric_json, e.rating,
               d.vert_occ AS dff_vert_raw
        FROM quality_recording_metrics m
        JOIN entries e ON m.lb_number = e.lb_number
        LEFT JOIN dff_reports d ON m.lb_number = d.lb_number
        WHERE m.scan_id = ?
          AND e.rating IS NOT NULL AND e.rating != ''
          AND m.source_class = 'AUD'
        ORDER BY m.lb_number
    """, (scan_id,)).fetchall()

    out = []
    for r in rows:
        rank = RATING_RANK.get(r["rating"])
        if rank is None:
            continue
        envelope = json.loads(r["metric_json"])
        metrics = envelope.get("metrics", {})
        # Inject DFF feature: log1p(vert_occ), None if no DFF data
        raw_vert = r["dff_vert_raw"]
        if raw_vert is not None:
            metrics["dff_vert_occ"] = float(np.log1p(raw_vert))
        else:
            metrics["dff_vert_occ"] = None
        out.append({"lb": r["lb_number"], "rating": r["rating"],
                    "rank": rank, "metrics": metrics})
    return out


def build_matrix(rows: list[dict], predictors: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build (X, y, nan_mask) from rows for the given predictor list.

    NaN/None values are median-imputed per column.
    Returns X (n, p), y (n,), medians (p,).
    """
    n = len(rows)
    p = len(predictors)
    X_raw = np.full((n, p), np.nan)
    y = np.array([r["rank"] for r in rows], dtype=float)

    for j, name in enumerate(predictors):
        for i, r in enumerate(rows):
            v = r["metrics"].get(name)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X_raw[i, j] = float(v)

    medians = np.nanmedian(X_raw, axis=0)
    for j in range(p):
        mask = np.isnan(X_raw[:, j])
        X_raw[mask, j] = medians[j]

    return X_raw, y, medians


def cv_spearman(X: np.ndarray, y: np.ndarray, alpha: float = 0.3,
                n_splits: int = 5, n_seeds: int = 3) -> tuple[float, float]:
    """5-fold CV Spearman and within-one-tier accuracy, averaged over seeds."""
    rhos, within1s = [], []
    for seed in range(n_seeds):
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
        pred_all = np.zeros(len(y))
        for train_idx, val_idx in kf.split(X):
            Xm = X[train_idx].mean(axis=0)
            Xs = X[train_idx].std(axis=0) + 1e-9
            Xtr = (X[train_idx] - Xm) / Xs
            Xv = (X[val_idx] - Xm) / Xs
            m = Ridge(alpha=alpha)
            m.fit(Xtr, y[train_idx])
            pred_all[val_idx] = m.predict(Xv)
        rho, _ = spearmanr(y, pred_all)
        within1 = np.mean(np.abs(np.round(pred_all) - y) <= 1)
        rhos.append(rho)
        within1s.append(within1)
    return float(np.mean(rhos)), float(np.mean(within1s))


def forward_select(rows: list[dict], pool: list[str], alpha: float = 0.3,
                   min_improve: float = 0.002) -> list[str]:
    """Greedy forward selection maximising CV Spearman.

    Stops when adding any remaining candidate improves Spearman by less than
    ``min_improve``.
    """
    selected: list[str] = []
    best_rho = -1.0

    while True:
        best_cand, best_cand_rho = None, best_rho
        for cand in pool:
            if cand in selected:
                continue
            trial = selected + [cand]
            X, y, _ = build_matrix(rows, trial)
            rho, _ = cv_spearman(X, y, alpha=alpha)
            if rho > best_cand_rho:
                best_cand_rho, best_cand = rho, cand

        if best_cand is None or best_cand_rho - best_rho < min_improve:
            break
        selected.append(best_cand)
        best_rho = best_cand_rho
        print(f"  +{best_cand:30s}  CV rho={best_cand_rho:.4f}")

    return selected


def fit_model(rows: list[dict], predictors: list[str], alpha: float = 0.3) -> dict:
    """Fit final Ridge on all data with the chosen predictors."""
    X, y, medians = build_matrix(rows, predictors)
    means = X.mean(axis=0)
    stds = X.std(axis=0) + 1e-9
    Xz = (X - means) / stds
    m = Ridge(alpha=alpha)
    m.fit(Xz, y)

    # Check weight signs vs univariate Spearman
    print("\nWeight sign check (univariate rho vs model weight):")
    for j, name in enumerate(predictors):
        rho, _ = spearmanr(X[:, j], y)
        sign_ok = (rho > 0) == (m.coef_[j] > 0)
        print(f"  {name:30s} rho={rho:+.3f}  weight={m.coef_[j]:+.4f}  "
              f"{'OK' if sign_ok else 'SIGN FLIP ⚠'}")

    return {
        "predictors": predictors,
        "median": [round(float(v), 4) for v in medians],
        "mean":   [round(float(v), 4) for v in means],
        "std":    [round(float(v), 4) for v in stds],
        "intercept": round(float(m.intercept_), 5),
        "weights":   [round(float(w), 4) for w in m.coef_],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--scan-id", type=int, default=8)
    ap.add_argument("--alpha", type=float, default=0.3)
    ap.add_argument("--no-forward-select", action="store_true",
                    help="Skip forward selection; use the full candidate pool")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    print(f"Loading scan_id={args.scan_id} AUD rows …")
    rows = load_rows(conn, args.scan_id)
    print(f"Loaded {len(rows)} rows  "
          f"({sum(1 for r in rows if r['metrics'].get('dff_vert_occ') is not None)} with DFF)")

    commentary_audit(conn, rows)
    conn.close()

    available_pool = [p for p in _CANDIDATE_POOL
                      if any(r["metrics"].get(p) is not None for r in rows)]
    missing = [p for p in _CANDIDATE_POOL if p not in available_pool]
    if missing:
        print(f"\nSkipping candidates with no scan data: {missing}")

    if args.no_forward_select:
        predictors = available_pool
    else:
        print(f"\nForward selection over {len(available_pool)}-candidate pool (alpha={args.alpha}):")
        predictors = forward_select(rows, available_pool, alpha=args.alpha)
        print(f"\nSelected {len(predictors)} predictors: {predictors}")

    # Final model fit
    model = fit_model(rows, predictors, alpha=args.alpha)

    # Full-sample in-sample validation (for reference)
    X, y, _ = build_matrix(rows, predictors)
    means = np.array(model["mean"])
    stds = np.array(model["std"])
    Xz = (X - means) / stds
    from sklearn.linear_model import Ridge as _Ridge
    m_full = _Ridge(alpha=args.alpha)
    m_full.fit(Xz, y)
    pred = m_full.predict(Xz)
    rho_in, _ = spearmanr(y, pred)
    within1_in = np.mean(np.abs(np.round(pred) - y) <= 1)

    # Held-out CV
    rho_cv, within1_cv = cv_spearman(X, y, alpha=args.alpha)

    print(f"\nIn-sample : Spearman={rho_in:.3f}, within-1-tier={within1_in:.1%}")
    print(f"5-fold CV : Spearman={rho_cv:.3f}, within-1-tier={within1_cv:.1%}")

    # Print model dict for config.py
    print("\n# ── paste into concert_ranker/config.py ──────────────────────────────────")
    print(f"QUALITY_MODEL = {{")
    print(f"    \"predictors\": {model['predictors']!r},")
    print(f"    \"median\": {model['median']!r},")
    print(f"    \"mean\":   {model['mean']!r},")
    print(f"    \"std\":    {model['std']!r},")
    print(f"    \"intercept\": {model['intercept']},")
    print(f"    \"weights\":   {model['weights']!r},")
    print(f"}}")
    print(f"# CV Spearman={rho_cv:.3f}, within-1={within1_cv:.1%}, "
          f"n={len(rows)}, alpha={args.alpha}, scan_id={args.scan_id}")


if __name__ == "__main__":
    main()
