# tapematch — Performance Findings & Architecture Limits

*Written 2026-06-25. Per-task implementation details are in `BASELINE.md`.*

---

## 1. Current accuracy (latest-run per pair, `observations.db`)

| Metric | Baseline Jun-12 | Now (Jun-25) |
|--------|-----------------|--------------|
| LB-confirmed same-source pairs | 769 | 1,575 |
| Miss rate (false-distinct) | 65.0% | **60.8%** (957/1,575) |
| False merges | 8 | 9 |
| Misses with >10 000 ppm speed offset | ~50% | **49.5%** |

The ~4-point improvement is entirely from the 2026-06-21 speed-offset fix (widened coarse
search to ±30 000 ppm + `refine_speed_ratio` lag-slope iteration).  False-merge count is
stable.  Effective recall on confirmed same-source pairs is **~39%**.

---

## 2. Corr distribution of missed pairs (unchanged from baseline)

| Primary corr bucket | Missed pairs | % |
|---------------------|-------------:|------:|
| 0.00–0.05 | ~898 | **93.8%** |
| 0.05–0.10 | ~30 | 3.0% |
| 0.10–0.35 | ~22 | 2.3% |
| 0.35+ | ~7 | 0.7% |

All approaches below were directed at the 93.8% bucket.  This bucket is the hard problem.

---

## 3. Approaches tried and their outcomes

### 3a. Speed-offset: predicted-lag mode (Task 4, Jun-13)

Widened the `local_lag_sec` search by centering it on the anchor-estimated lag for
high-ppm pairs.  Mechanism activates correctly (logged `PREDICTED_LAG` lines show
plausible `lag_0`/`ppm`); zero regressions on control dates.

**Result:** zero miss reduction on target dates (1989-06-04, 1990-01-12).  At every
lag tried — including the predicted one — `windowed_median` (0.0017–0.011) and
`hiss_median` (0.0046–0.0095) sit ~100× below their thresholds.  The miss is not a
search-range problem; the signal is absent.  Code kept (correct, tested, will help
any future case where the miss genuinely is a search-range miss).

### 3b. Speed-offset: wider coarse search + ratio refinement (Jun-21)

Found that 18% of all pairs railed at the old ±2% (±20 000 ppm) grid edge.  Widened
to ±30 000 ppm; added `match.refine_speed_ratio` (lag-slope iteration to <5 ppm
residual, config-gated, self-limiting).

**Result:** miss rate dropped 65% → 60.8%.  The largest single improvement in the
project.  Still leaves 49.5% of misses at >10 000 ppm — those pairs have near-zero
residual_corr even after accurate speed correction, so the signal was never there
regardless of ratio accuracy.

### 3c. Staircase: short-window recalibration (Task 5, Jun-13)

5 s windows (`staircase_window_sec`) on known staircase/staircase pairs (2001-10-30).
Also fixed the reference-ambiguity union-flag bug in `align.union_staircase_sources`
(correctness fix to the existing 15 s fallback).

**Calibration result:** different-source-same-show pair median (0.0153) was *higher*
than same-source median (0.0118).  Distributions fully overlap at 5 s.  Not wired
into `cli.py`.  Union-flag fix kept (regression-free, correct).

### 3d. Patchwork/composites: segment overlap, three sub-approaches (Task 8, Jun-25)

Motivated by 1991-11-05 Madison — five curator-claimed same-source pairs inside
patchwork recordings (shared clapping section).

- **Contiguous corr run:** `secondary_corr_pair` at ±10 s and ±120 s lag search.
  Longest run above any threshold = 0 windows for all 6 pairs including negative
  control.

- **Windowed landmark fingerprint, 6–8 kHz HF band:** Dice 0.066–0.079 for all
  pairs; negative control 0.074 — indistinguishable.  The `best-of-all-pairs`
  statistic reaches a ~0.07 chance floor with ~1 M comparisons per pair.

- **Windowed landmark fingerprint, 200–4 000 Hz crowd/clap band:** claimed positives
  scored 0.194–0.244, but cross-validation on two other dates showed confirmed-distinct
  same-show pairs scoring 0.235–0.301 — fully overlapping.  No usable threshold.

**Conclusion:** shared musical content (same songs, same concert) dominates the
0–4 kHz band at 20 s window granularity.  Short localized transients cannot be
separated from same-show background correlation at this scale.

### 3e. Piecewise alignment for staircase pairs (Task 9, Jun-25)

`align.locate_splice_points` splits each recording at staircase-detected boundaries;
`secondary_corr_pair` run independently per segment with its own lag search.

**Pilot (2001-10-30):** same-source pair per-segment p50 = 0.004 (identical to
whole-recording baseline 0.004).  Different-source-same-show pair scored 0.005 —
*higher* than same-source.  Over-triggered staircase detection (22 boundaries, some
14–54 s micro-segments) compounded the failure.

`locate_splice_points` retained with unit tests for potential future use; not wired
into `cli.py`.

### 3f. Low-band (250–2 000 Hz) envelope fallback (Task 10, Jun-25)

Zero-phase butterworth bandpass + log-RMS envelope cross-correlation (±90 s lag
search).  Motivated by the idea that audience-dynamics patterns survive even when
HF is dead.

**Pilot (1989-06-04, 1990-01-12):** confirmed-distinct no-claim pair
(LB-02470/LB-02478) scored +0.357 — higher than every missed claimed-same pair
(max +0.201).  Same-show dynamics inflate same-show scores regardless of source
identity.  The LB-14054 pairs scored −0.11 to −0.13, suggesting polarity inversion
or genuinely different sources.

`match.lowband_envelope_corr` retained with unit tests; not wired into `cli.py`.

### 3g. Channel-polarity rescue (TODO-184, Jun-24–Jun-25)

Implemented stereo ingest (Pass 1 now decodes stereo when `polarity.enabled`);
`match.polarity_rescue` re-scores near-zero pairs via mid-side and side-mid
cross-terms with per-anchor lag lock.

**Batch validation (93/474 dates):** 0 polarity-rescue wins, 0 regressions,
1 new false merge.  Batch stalled at 93/474 (6 consecutive `run_failed`).
Memory profile: RSS ~2.7 GB peak vs ~1.1 GB mono (stereo resample spike).

**Finding from 1991-11-05 dry-run:** the actual unhandled case in the curator notes
("channels swapped and wavs inverted") is segment-level patchwork, not a
whole-recording single-channel inversion.  Polarity rescue is solving the right
problem in principle but the actual contradicted-claim corpus is dominated by
patchwork composites and speed-offset recordings, not clean whole-recording polarity
flips.

---

## 4. Root cause

The discriminating signal is genuinely absent in the majority of missed pairs.
These recordings are:

- **CDR-sourced / HF-capped** — tape hiss fine structure above ~8 kHz (the primary
  discriminating signal) is attenuated or absent.
- **High ppm** — speed offsets decorrelate whole-recording correlation even when ratio
  estimation is accurate, because the residual_corr grid tolerance is ~250 ppm after
  coarse resampling (~0.015 corr vs 1.0 for a perfect match).
- **Same show** — shared musical content (same songs, same concert hall) inflates
  low-frequency and mid-band correlation between all pairs, regardless of source
  identity.  No frequency band or window size tested escapes this floor.
- **Patchwork/composite** — shared material is localised to a short segment; whole-
  recording correlation averages over mostly non-matching material and collapses.

The correlation-based architecture (primary residual + windowed/hiss secondary) is
fundamentally constrained by these properties of the source material.

---

## 5. What works

tapematch is reliable for pairs where at least one of the following holds:

- Clean HF response (reel-to-reel source, no CDR ceiling) — primary residual
  correlation scores 0.7–0.95 for same-source pairs.
- Moderate speed offset (<10 000 ppm) with usable HF — secondary windowed coverage
  catches most of these.
- Quiet-segment hiss texture distinguishable from musical content — hiss layer adds
  marginal coverage.

This covers roughly **39%** of curator-confirmed same-source pairs.

---

## 6. Approaches not yet tried (potential future angles)

These are open research directions, not currently planned work.  None are guaranteed.

| Approach | Rationale | Risk |
|----------|-----------|------|
| Sub-second percussive onset fingerprinting | Snare/kick transients have sharp HF spikes regardless of tape ceiling; onset-aligned matching within a 1–2 s window could survive patchwork offsets | Same-show onset patterns may still collide; high engineering cost |
| Polarity fix on clean whole-recording flip dates | The mechanism is correct; find dates with an unambiguous single-channel inversion note in curator commentary | Batch validation already shows 0 wins in 93 dates; may be a rare case |
| Waveform-level DTW on short same-show segments | Find locally coherent lag using dynamic time warping on a known same-recording segment anchor | Requires manual seed; not automatable without a different discovery step |

---

## 7. Recommendation

**Accept ~39% recall as the practical ceiling for this architecture.**

- tapematch results are useful for the pairs it does link.  False-merge rate is low (9
  out of 7 528 total pairs, 0.12%).
- Do not invest further in signal-level improvements (threshold tuning, new frequency
  bands, window sizes) — each calibration study has produced the same finding.
- The polarity-rescue batch can run to completion to confirm the 0-rescue pattern, but
  do not expect meaningful improvement from it.
- Any future improvement would require a fundamentally different approach (onset-based
  fingerprinting, human-assisted segment seeding, or exploiting metadata rather than
  audio signal).
