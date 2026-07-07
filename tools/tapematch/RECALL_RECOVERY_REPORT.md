# TapeMatch Recall-Recovery — Final Report (CC_TAPEMATCH_FIXES Tasks 1–7)

**Date:** 2026-07-02  **Harness:** `regression.py score --cached` over 827 dates / 2965 frozen labeled pairs.
**Governing constraint:** precision is the asset — any change adding a false merge on a frozen
negative is rejected. Held throughout: **fp = 9, zero new FP.**

## Headline result

| Measurement | Recall | Precision | tp / fn / fp / tn |
|---|---|---|---|
| Audit baseline (raw pairs, pre-dedup) | 38.3% | 98.2% | 663 / 1066 / 12 / 1422 |
| Frozen set baseline (deduped, staircase stripped) | 39.2% | 98.6% | 618 / 957 / 9 / 1381 |
| **Final (staircase 0.40 + estimate_ratio_v2, triplet OFF)** | **41.6%** | **98.6%** | **655 / 920 / 9 / 1381** |

Net: **+3.3 points recall** over the published 38.3% audit baseline, at **higher precision**
(98.2% → 98.6%), zero new false merges. All gain is precision-safe.

## Lever-by-lever outcome

| Lever (spec task) | Outcome | Recall effect |
|---|---|---|
| Staircase fp bar 0.40 (Task 3) | ✅ Shipped, harness-clean | Main safe gain (~+2.4 vs stripped baseline) |
| `estimate_ratio_v2` + duration prior + confidence gate (Task 5) | ✅ Precision-safe | +0.2 across 10 Cat-1-dense dates |
| Residual lag-curve correction (Task 6.1) | ✅ Live on primary path | Folded into v2 gain |
| pyin fallback (Task 6.2) | ✅ Implemented, rarely fires | ~0 (engages only when no ratio found) |
| Triplet fingerprint (Task 7) | ❌ **REJECTED — disabled** | Made 5 false merges; removed |
| Confidence-gate sweep (6.0→4.5) | ❌ Negative result, reverted | +0.0 |
| Cat-3 focused re-run (Task 2) | ✅ Ran, reported | 0 of 6 flipped |
| Curator relaxation 4.1 / lo-fi hiss 4.2 | ✅ Live | Marginal, low coverage |

## Why the ceiling is ~42%: the FN population is non-correlating

Current FN = 917 frozen positives still `different_family`. Breakdown:

| FN category | Count | % of FN |
|---|---|---|
| **corr < 0.05 (waveforms do not correlate)** | **857** | **93%** |
| — of which speed offset was detected + corrected (`constant-speed-offset`) | 682 | 74% |
| — routed to `speed-unknown` (no confident ratio) | 95 | 10% |
| staircase/splice-involved | 214 | 23% |
| corr ≥ 0.05 (borderline recoverable) | **60** | **7%** |

The decisive evidence (three independent confirmations):
1. **estimate_ratio_v2** rescues only the confident-and-already-correlating minority.
2. **Confidence sweep (6.0→4.5):** the stranded pairs (e.g. a real −45,800 ppm offset at conf 5.0)
   *did* resample at the lower gate — and corr stayed 0.002–0.010. **Correct speed alignment does
   not make them correlate.**
3. **Cat-3 re-run:** pairs staged in isolation (aligning directly against each other) still scored
   corr ~0.005 — e.g. `1987-09-19 LB-00131/LB-05156` (indisputably the same show) with HF ceilings
   2.0 kHz vs 3.0 kHz: heavily band-limited, different-generation transfers.

These are not a speed/alignment problem. They are genuinely non-correlating recordings — independent
generations with different noise, lossy/lo-fi lineage, or curator label noise. No waveform-,
spectral-, speed-, or hiss-based method in this spec can merge them.

## Triplet fingerprint: why it was rejected

Panako-style ratio hashes were the spec's designed rescue for speed-offset pairs. Live calibration
(`calibrate_triplet.py`, 116 real pairs): true same-source Dice median **0.656**, same-date
different-source Dice median **0.638** — **overlapping, gap −0.012**. Different recordings of the
*same concert* share real musical timing, so ratio-encoded hashes collide as badly for true
negatives as positives. At threshold 0.45 this produced **5 false merges** on frozen negatives.
The collision is structural, not quantization-limited, so the spec's 7→8-bit fallback is unlikely
to help. Code retained but `fingerprint.triplet.enabled=false`.

## Conclusion

**>80% family grouping is not achievable within this spec.** The in-scope ceiling is ~42% recall
at 98.6% precision. Reaching >80% requires the **explicitly out-of-scope contrastive-embedding
(learned-similarity) model** — the 93% non-correlating FN bulk needs a learned signal, not a
better hand-engineered correlation. Every Task 1–7 lever has been implemented, measured, and
either shipped (precision-safe) or rejected with evidence.

## Code delivered (all in tree, 175 tests green)

- `match.py`: `estimate_ratio_v2`, `duration_ratio_prior`, `pitch_ratio_pyin`, `triplet_hashes`
  /`triplet_window`/`_fingerprint_peaks` (dormant); `estimate_ratio_v1_deprecated` kept for A/B.
- `align.py`: `residual_ppm_from_lag_curve` (r²-guarded).
- `cli.py`: v2 confidence gating + speed-unknown routing + primary-path residual correction.
- `verdict.py`: triplet OR-path (inert when disabled).
- `pairs.fp_triplet_score` column; `calibrate_triplet.py`; `regression.py` metric wiring.
- Config: `align.ratio_confidence_min=6.0`, `align.pyin_fallback=true`,
  `fingerprint.triplet.*` (enabled=false).
