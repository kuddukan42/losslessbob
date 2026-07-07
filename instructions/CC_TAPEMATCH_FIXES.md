# CC_TAPEMATCH_FIXES — Recall recovery: mechanical fixes + speed-invariant fingerprint

Read `PROJECT.md`, `tools/tapematch/tapematch/match.py`, `tools/tapematch/tapematch/align.py`,
`tools/tapematch/tapematch/audio.py`, `tools/tapematch/tapematch/cli.py`,
`tools/tapematch/tapematch_session.py`, `tools/tapematch/WORKFLOW.md`, and
`tools/tapematch/session/config.yaml` before starting.

---

## Context

Tapematch audit against 2,163 curator-labeled pairs: **precision 98.2%, recall 38.3%**.
FN characterization of 957 unique missed pairs:

| Cat | n | % | Cause |
|-----|-----|------|-------|
| 1 | 527 | 55.1% | Speed delta outside/beyond `estimate_ratio` grid (deltas to 56,500 ppm; grid ±20,000 ppm, 500 ppm steps) |
| 2 | 257 | 26.9% | Staircase on ONE side — short-window fallback requires staircase on BOTH sides |
| 3 | 6 | 0.6% | Sources speed-aligned to wrong reference in stale runs — need focused re-run |
| 4 | 156 | 16.3% | All four signals below threshold; ~30 fp near-misses (0.40–0.499); hiss_median guard over-blocking lo-fi pairs |

Plus 11 anomalies caused by stale cross-run data joins.

**Governing constraint: precision is the asset.** False merges poison union-find
clusters transitively. Every task below is gated by the regression harness in
Task 1. A change that raises recall but adds false positives on the frozen
negative set is REJECTED.

Ordering is strict — Task 1 must exist before any algorithm change lands, and
each subsequent task re-runs the harness before merging. Fix the measurement
instrument before touching the algorithm.

---

## Task 1 — Regression harness (`tools/tapematch/regression.py`)

New script. Freezes the current labeled pair population as a regression set and
scores any candidate configuration/code state against it.

### 1.1 Frozen set extraction

```
python tools/tapematch/regression.py freeze
```

- Reads `observations.db` `pairs` table, latest run per (lb_a, lb_b) pair only
  (dedupe on `MAX(run_at)` per unordered pair — this is the fix for the 11
  stale-data anomalies; see 1.4).
- Selects all rows with `lb_says_same IN (0, 1)` OR `human_judgment IN
  ('confirmed_same', 'confirmed_different')`. Human judgment outranks
  `lb_says_same` where both present.
- Writes `tools/tapematch/session/regression_set.json`:

```json
{
  "frozen_at": "ISO timestamp",
  "positives": [[lb_a, lb_b, "date_iso"], ...],
  "negatives": [[lb_a, lb_b, "date_iso"], ...],
  "baseline": {"tp": 663, "fn": 1066, "fp": 12, "tn": 1422,
               "precision": 0.982, "recall": 0.383}
}
```

The frozen file is committed to git. It is never regenerated except by an
explicit `freeze --force`.

### 1.2 Scoring a run

```
python tools/tapematch/regression.py score --dates 1996-07-21,1998-10-28,...
python tools/tapematch/regression.py score --all-frozen-dates
```

- For each date, runs the tapematch session (reuse `tapematch_session.py`
  machinery) and collects family verdicts for every frozen pair on that date.
- Emits per-category and aggregate confusion matrix vs. baseline:

```
           baseline   candidate   delta
recall       38.3%       xx.x%    +x.x
precision    98.2%       xx.x%    ±x.x
new FP: [LB-x/LB-y, ...]          <- listed individually, always
```

- Exit code 1 if any NEW false positive appears that was a TN in baseline.
  New FPs must be individually reviewed and either (a) reclassified by human
  judgment or (b) the change rejected.

### 1.3 Fast mode

`score --cached` re-scores from existing `pairs` rows without re-running audio,
for threshold-only changes (Tasks 3, 4). Threshold logic must therefore be
reproducible from stored per-pair metrics (corr, windowed_frac, hiss_frac,
hiss_median, fp_score, speed_kind_a/b, hf_ceiling_a/b) — implement the verdict
function as a pure function `verdict(pair_row, cfg, lineage) -> str` in a new
module `tools/tapematch/tapematch/verdict.py` so it can run against DB rows or
live results identically. Refactor `cli.py` clustering to call it.

### 1.4 Stale-data guard

Add `latest_pairs` view to the observations DB schema in
`tapematch_session.py`:

```sql
CREATE VIEW IF NOT EXISTS latest_pairs AS
SELECT p.* FROM pairs p
JOIN (
    SELECT MIN(lb_a, lb_b) la, MAX(lb_a, lb_b) lbb, MAX(run_at) mr
    FROM pairs GROUP BY MIN(lb_a, lb_b), MAX(lb_a, lb_b)
) t ON MIN(p.lb_a, p.lb_b)=t.la AND MAX(p.lb_a, p.lb_b)=t.lbb
   AND p.run_at = t.mr;
```

All analysis/audit queries in `gen_analysis.py` and `regression.py` use
`latest_pairs`, never `pairs` directly.

**Deliverable:** harness runs, baseline numbers reproduce the audit (663/1066/12/1422
within ±5 rows — small drift from dedupe is acceptable and must be logged).

---

## Task 2 — Cat 3 focused re-run (6 pairs)

No code change. Create `tools/tapematch/rerun_cat3.py`:

- Hardcode the 6 pair list (extract from the FN characterization query:
  `latest_pairs WHERE speed_kind_a='aligned' OR speed_kind_b='aligned'` with
  `lb_says_same=1` and verdict `different_family`).
- For each pair: stage BOTH folders into the session examples dir together,
  run tapematch on just those two, write results to observations DB with a
  fresh run_id.
- Print before/after verdict per pair.

Expected outcome: most flip to same_family once aligned against each other.
Any that don't flip get reassigned to Cat 1/2/4 and noted in the report.

---

## Task 3 — Staircase: either-side fallback + conditional fp threshold

### 3.1 Short-window fallback trigger

In the secondary-match path (`cli.py` / `match.py` — locate the guard that
selects `short_window_sec`): change the condition from *both* sides
staircase-flagged to *either* side:

```python
stair = ("staircase" in speed_info[na]["kind"]) or \
        ("staircase" in speed_info[nb]["kind"])
```

Verify the current behavior first — WORKFLOW.md documents both-sides; if the
code already checks either-side, instrument it (debug-log which branch fires
for a known Cat 2 pair, e.g. from 1996-07-21) and find why windowed_frac stays
at ~0. Do not proceed on assumption.

### 3.2 Staircase-conditional fingerprint threshold

`config.yaml`:

```yaml
fingerprint:
  cluster_threshold: 0.50
  cluster_threshold_staircase: 0.40   # NEW — either side staircase-flagged
```

In `verdict.py` (from Task 1.3):

```python
def fp_threshold(pair, cfg) -> float:
    fp_cfg = cfg["fingerprint"]
    stair = ("staircase" in (pair["speed_kind_a"] or "")) or \
            ("staircase" in (pair["speed_kind_b"] or ""))
    if stair:
        return fp_cfg.get("cluster_threshold_staircase",
                          fp_cfg["cluster_threshold"])
    return fp_cfg["cluster_threshold"]
```

**Gate:** `regression.py score --cached` — Cat 2 recall must rise; zero new FP
on frozen negatives. If new FPs appear, raise the staircase threshold in 0.02
steps until clean, and report the final value.

---

## Task 4 — Conditional thresholds: curator-relaxed fp + lo-fi hiss guard

### 4.1 Curator-conditional fingerprint threshold

Requires `entry_lineage` (already built — CC_LINEAGE_PARSE). Add a lineage
loader to `verdict.py`:

```python
def load_lineage_pairs(db_path) -> set[tuple[int, int]]:
    """Return unordered (lb_lo, lb_hi) pairs where either side's same_as_lb
    lists the other."""
    import json, sqlite3
    conn = sqlite3.connect(str(db_path))
    out = set()
    for lb, same in conn.execute(
            "SELECT lb_number, same_as_lb FROM entry_lineage "
            "WHERE same_as_lb != '[]'"):
        for other in json.loads(same):
            out.add((min(lb, other), max(lb, other)))
    conn.close()
    return out
```

`config.yaml`:

```yaml
fingerprint:
  cluster_threshold_curator: 0.43   # NEW — curator text claims same-source
```

In `fp_threshold()`: if `(min(lb_a,lb_b), max(lb_a,lb_b))` in the lineage set,
use `min(current_applicable, cluster_threshold_curator)`.

Principle: text is a prior, not a label. Audio must still cross 0.43 — a text
claim with fp_score 0.10 stays `different_family` (this is how the system
learns to distrust wrong text).

### 4.2 HF-conditional hiss_merge_median

`config.yaml`:

```yaml
secondary_match:
  hiss_merge_median: 0.65
  hiss_merge_median_lofi: 0.40      # NEW — both hf_ceiling_hz < 12000
  hiss_lofi_ceiling_hz: 12000
```

In `verdict.py`: apply the lo-fi value only when BOTH sides have
`hf_ceiling_hz < hiss_lofi_ceiling_hz` AND neither is `nyquist_capped`
(a capped reading is not a real ceiling measurement — treat as unknown, keep
0.65). Rationale: cassette-generation deck noise is chain identity; the 0.65
guard was calibrated against room-ambience false positives on cleaner sources.

**Gate:** `score --cached`. 4.1 and 4.2 evaluated separately (two harness runs)
so their individual FP impact is attributable.

---

## Task 5 — `estimate_ratio` overhaul (Cat 1 primary fix)

File: `tools/tapematch/tapematch/match.py`. Replace `estimate_ratio` with a
prior-centered, confidence-reporting estimator.

### 5.1 Duration-ratio prior

```python
def duration_ratio_prior(dur_ref: float, dur_other: float,
                         diagnostics: set[str]) -> float | None:
    """Speed-ratio prior from performance durations (post-trim).
    A 5% speed offset is a 5% duration difference — trivially visible.
    Returns None when trim/timing diagnostics make durations incomparable."""
    if {"TIMING_MISMATCH", "INCOMPLETE"} & diagnostics:
        return None
    if dur_other <= 0:
        return None
    r = dur_ref / dur_other
    if abs(r - 1.0) > 0.08:          # >80,000 ppm — durations not comparable
        return None
    return r
```

Callers pass trimmed `perf_dur` values (already computed in `trim_bounds`).

### 5.2 New estimator

```python
def estimate_ratio_v2(ref, other, sr, cfg,
                      prior: float | None = None) -> tuple[float, float]:
    """Return (ratio, confidence). Confidence = peak prominence of the
    envelope-correlation surface: (best - median) / (mad + eps).

    Search strategy:
      prior given  -> fine grid: prior ± 3000 ppm, 100 ppm steps (61 pts)
      no prior     -> coarse grid: ±60000 ppm, 1000 ppm steps (121 pts),
                      then fine grid ±1500 ppm / 100 ppm around coarse best.
    Envelope warping uses linear interpolation of the log-envelope
    (np.interp), NOT scipy.signal.resample — FFT resampling of a
    non-periodic envelope adds edge artifacts and biases peak comparison
    across ratios."""
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
```

### 5.3 Confidence gating

`config.yaml`:

```yaml
align:
  ratio_flag_ppm: 200
  ratio_confidence_min: 6.0     # NEW — below this, ratio is UNKNOWN
```

When `confidence < ratio_confidence_min`:
- Do NOT resample with the returned ratio.
- Set `speed_kind = "speed-unknown"` for the pair, log it, and route the pair
  to the fingerprint path only (Task 7 makes that path speed-invariant).
This converts silent Cat 1 failures into a diagnosable population.

### 5.4 Keep `estimate_ratio` name stable

Rename old function `estimate_ratio_v1_deprecated`, wire `estimate_ratio_v2`
behind the original call sites (`pairwise_matrix`, `cli.py` lag-curve section)
with prior plumbed from trim durations. Keep v1 callable for A/B in the
harness.

**Gate:** full `regression.py score` on all frozen dates containing Cat 1
pairs. Expect the largest single recall jump of the spec. Zero new FP
tolerance stands. Also run 2–3 known-good control dates (e.g. 1998-10-28,
1996-07-21) and confirm identical family output vs. baseline.

---

## Task 6 — Lag-curve slope refinement + pyin fallback

### 6.1 Closed-form residual correction (kills the ±grid-step quantization)

The residual speed error after coarse resampling appears as the slope of the
lag-vs-position curve, which `align.lag_curve` already computes. Add to
`align.py`:

```python
def residual_ppm_from_lag_curve(rows) -> tuple[float, float]:
    """rows: [(anchor_sec, lag_sec_or_None), ...] measured AFTER coarse
    resample. lag(t) = ppm*1e-6*t + c  =>  slope*1e6 = residual ppm.
    Returns (ppm, r_squared). Robust: refuses estimate on <4 valid anchors
    or poor linear fit (staircase curves must not be 'corrected')."""
    pts = [(a, l) for a, l in rows if l is not None]
    if len(pts) < 4:
        return 0.0, 0.0
    t = np.array([p[0] for p in pts]); lag = np.array([p[1] for p in pts])
    slope, intercept = np.polyfit(t, lag, 1)
    pred = slope * t + intercept
    ss_res = float(((lag - pred) ** 2).sum())
    ss_tot = float(((lag - lag.mean()) ** 2).sum()) + 1e-12
    return float(slope * 1e6), 1.0 - ss_res / ss_tot
```

Integration in `pairwise_matrix` / `cli.py`:

```
ratio, conf = estimate_ratio_v2(...)
resample if needed
rows = lag_curve(ref, other_corrected, ...)
ppm_res, r2 = residual_ppm_from_lag_curve(rows)
if r2 > 0.85 and abs(ppm_res) > 50:
    apply corrective resample: ratio *= (1 + ppm_res * 1e-6); recompute lag curve
    (max 2 correction iterations)
```

The r² guard is mandatory — a staircase lag curve fits a line badly and must
fall through to the staircase path untouched.

MEMORY-CRITICAL: corrective resample creates a second full-length float32
array. Follow the existing memmap discipline in `cli.py` — resample into a new
memmap under the run tmp dir, delete the intermediate, never hold two
resampled copies in heap.

### 6.2 pyin absolute-pitch fallback

Only for pairs where `estimate_ratio_v2` returned `speed-unknown` AND duration
prior was unavailable. New function in `match.py`:

```python
def pitch_ratio_pyin(ref, other, sr, cfg) -> tuple[float, float]:
    """Absolute-pitch speed ratio via librosa.pyin median f0.

    Windows: pick 3 non-quiet 60 s windows per source (reuse
    find_quiet_segments logic inverted — highest-energy stable segments,
    spread early/mid/late). For each window compute voiced f0 track:

        f0, vflag, _ = librosa.pyin(y_win, fmin=65.0, fmax=1000.0,
                                    sr=sr, frame_length=4096)
        med = np.nanmedian(f0[vflag])

    Per-window ratio = med_ref / med_other. Take the median of the 3 window
    ratios; confidence = 1 - (max-min spread of window ratios / median).
    Returns (ratio, confidence in [0,1]).

    CAVEAT — octave errors: pyin can jump octaves between sources. After
    computing per-window ratios, fold any ratio in [1.9, 2.1] or
    [0.48, 0.52] * another window's ratio by the appropriate power of 2
    before taking the median. If windows disagree by >2000 ppm after
    folding, return confidence 0."""
```

Gate its use behind `align.pyin_fallback: true` config flag (default true).
Runs at the 16 kHz analysis rate — fmax 1000 Hz is far below Nyquist. numba
JIT: `NUMBA_CACHE_DIR` must already be set per existing project convention;
verify it is set in the tapematch entry path before first librosa call.

**Gate:** full harness run. Also add a synthetic unit test: take one real
track, resample by known ppm (e.g. +17,000), assert `pitch_ratio_pyin`
recovers within ±300 ppm and `residual_ppm_from_lag_curve` closes a deliberate
+400 ppm coarse error to <100 ppm.

---

## Task 7 — Ratio-invariant triplet fingerprint (Panako-style)

File: extend `tools/tapematch/tapematch/fingerprint.py` (or wherever the
constellation hashing lives — locate the Shazam-style hash builder first and
mirror its structure).

### 7.1 Why

Current hashes encode (f1, f2, Δt) with absolute quantization — a 1.5% speed
change shifts both frequency and Δt, breaking every hash. Cat 1 pairs
therefore fail the fingerprint fallback too. Triplet-ratio hashes are
invariant to time-scaling and pitch shift because they encode only ratios.

### 7.2 Algorithm

Keep the existing peak-picking front end (same STFT, same `hf_band_hz`
[6000, 8000] restriction — this preserves the same-show rejection property).
Replace the pairing stage:

```python
def triplet_hashes(peaks: list[tuple[float, float]], cfg: dict) -> set[int]:
    """peaks: [(t_sec, f_hz), ...] sorted by t, from the existing peak picker.

    For each anchor peak p0, take up to `fanout` peaks p1 in
    (t0 + tmin, t0 + tmax], and for each p1 up to `fanout` peaks p2 in
    (t1, t1 + tmax]. Hash the RATIOS only:

        r_t = (t2 - t1) / (t1 - t0)          # time-scale invariant
        r_f1 = f1 / f0                       # pitch-shift invariant
        r_f2 = f2 / f0

    Quantize: r_t to 6-bit log scale over [0.25, 4.0];
              r_f1, r_f2 to 7-bit log scale over [0.5, 2.0].
    hash = (q_rt << 14) | (q_rf1 << 7) | q_rf2   -> 20-bit int.

    Speed change scales all t deltas by the same factor and all f by the
    same factor -> every ratio is unchanged -> hash set is unchanged."""
```

Config:

```yaml
fingerprint:
  triplet:
    enabled: true
    tmin_sec: 0.5
    tmax_sec: 8.0
    fanout: 4
    cluster_threshold: 0.45     # Dice on triplet hash sets — CALIBRATE, see 7.4
```

### 7.3 Scoring and integration

Dice coefficient over triplet-hash sets, exactly parallel to the existing
fp_score. Store as new column `fp_triplet_score` in the observations `pairs`
table (schema migration in `tapematch_session.py` — `ALTER TABLE ADD COLUMN`,
nullable). Verdict logic in `verdict.py`: triplet score is an OR-path with its
own threshold, applied to ALL pairs but especially the sole surviving signal
for `speed-unknown` pairs from Task 5.3.

Note: quantized ratios have far fewer distinct values than Shazam hashes —
expect a higher random-collision baseline. That is why calibration (7.4) is
mandatory before the threshold goes live.

### 7.4 Calibration protocol (do this BEFORE enabling in verdicts)

1. Compute triplet Dice on 30 frozen TP pairs and 30 frozen TN pairs
   (same-date TNs only — the hard negatives), plus the 527 Cat 1 pairs.
2. Plot/print the two distributions. Set `cluster_threshold` at the midpoint
   of the gap, require gap width ≥ 0.10; if the gap is narrower, raise
   quantization bits (7→8 for freq ratios) and repeat.
3. Synthetic invariance test: one recording vs. itself resampled +30,000 ppm
   must score Dice > 0.8; vs. a different-family same-date recording must
   stay below threshold.

**Gate:** full harness. This task has the highest FP risk in the spec —
if any new FP appears on frozen same-date negatives, do not lower quality
bars to keep recall; tighten quantization or raise the threshold.

---

## Constraints (all tasks)

- Strictly additive to observations DB: new columns nullable, no row deletion,
  no destructive migrations.
- `verdict.py` is the single source of truth for clustering decisions after
  Task 1 — no threshold logic duplicated in `cli.py` or `gen_analysis.py`.
- All new thresholds live in `config.yaml`, none hardcoded.
- Memory discipline: any new full-length array goes through the memmap tmp-dir
  pattern; assume 2-hour sources.
- Do NOT resample before `secondary_corr_pair` (existing critical note in
  WORKFLOW.md stands — resampling smears the HF fine-structure that
  residual_corr needs). Task 6.1's corrective resample applies only to the
  PRIMARY path.
- After each task: run the harness, prepend CHANGELOG.md, update WORKFLOW.md
  knob tables and the failure-mode table.
- No screenshot/visual verification steps in any task — human sign-off happens
  outside this spec.

## Explicitly out of scope

- Contrastive embedding model (separate spec, separate conversation).
- Dropout event fingerprint, stereo M/S geometry, crowd-event matching,
  spectral-ratio stationarity (Phase-1 feature extraction spec).
- htdemucs stem analysis.
- Any change to the primary residual_corr math or anchor selection.

## Completion checklist

- [ ] `regression.py` freeze/score/score --cached working; baseline reproduced
- [ ] `latest_pairs` view; `gen_analysis.py` migrated to it
- [ ] `verdict.py` extracted; cli.py clustering calls it; identical output on 2 control dates
- [ ] Cat 3: 6 pairs re-run, results logged, report written
- [ ] Either-side staircase fallback verified/fixed with instrumented evidence
- [ ] `cluster_threshold_staircase` live, harness-clean
- [ ] Curator-conditional fp threshold live, harness-clean
- [ ] Lo-fi hiss_merge_median live, harness-clean
- [ ] `estimate_ratio_v2` with duration prior + confidence gating; v1 kept for A/B
- [ ] `speed-unknown` routing implemented and counted
- [ ] `residual_ppm_from_lag_curve` with r² guard + synthetic unit test
- [ ] `pitch_ratio_pyin` with octave folding + synthetic unit test
- [ ] Triplet fingerprint implemented, calibrated per 7.4, `fp_triplet_score` column added
- [ ] Final harness run: report recall/precision vs. 38.3%/98.2% baseline, per-category recovery table
- [ ] CHANGELOG.md, WORKFLOW.md, PROJECT.md updated
