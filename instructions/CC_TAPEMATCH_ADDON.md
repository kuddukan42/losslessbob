# CC_TAPEMATCH_ADDON — Lineage-forensic signals + learned similarity (post-42%-ceiling)

Read `tools/tapematch/RECALL_RECOVERY_REPORT.md`, `tools/tapematch/CALIBRATION_PROGRESS.md`,
`instructions/CC_TAPEMATCH_FIXES.md` (Constraints + §7.4), `tools/tapematch/tapematch/match.py`,
`tools/tapematch/tapematch/verdict.py`, `tools/tapematch/regression.py`, and
`tools/tapematch/config.yaml` before starting.

---

## Context — what the recall-recovery effort proved

CC_TAPEMATCH_FIXES Tasks 1–7 are complete. Final precision-safe state: **recall 41.6%,
precision 98.6%, fp = 9, zero new false merges** over 827 dates / 2965 frozen labeled pairs.
The in-scope ceiling was reached; three independent diagnostics established *why*:

- **93% of remaining FN (857/917) have corr < 0.05** — the waveforms do not correlate.
- Correct speed alignment does not fix it: stranded pairs re-resampled at a lowered
  confidence gate stayed at corr 0.002–0.010.
- Isolated re-alignment (Cat-3 protocol) of indisputable same-show pairs still scored
  corr ~0.005 — e.g. HF ceilings 2.0 kHz vs 3.0 kHz: independent-generation, heavily
  band-limited transfers.

These FN are **not** a speed, alignment, or threshold problem. They are pairs whose HF
fine structure (what `residual_corr` and the hf-band fingerprint measure) was destroyed
somewhere in the copy chain — lossy lineage, band-limiting, different-generation
transfers — or they are **curator label noise** (labeled same-family but actually
different recordings). No signal in the previous spec can distinguish these two cases,
and no hand-tuned threshold can recover either.

### The triplet lesson (governs every task below)

The triplet fingerprint (FIXES Task 7) was rejected with a structural finding:
**any similarity signal dominated by shared musical content collides on
same-concert-different-source negatives** (TP Dice 0.656 vs same-show TN 0.638 —
gap −0.012 → 5 false merges). Two audience recordings of the same show share the
performance's timing, pitch, and energy contour. Therefore:

> Every add-on signal must measure **recording/lineage identity** (channel, flaws,
> noise, geometry, transfer function), not performance content — or, if it is
> content-adjacent, it must be explicitly calibrated against same-date
> different-source negatives and pass the gap gate (§ Calibration protocol) before
> it can influence a verdict.

### Governing constraint (unchanged)

**Precision is the asset.** fp is frozen at 9. Any change that produces a new false
merge on a frozen negative is REJECTED. Additionally (guard-masking lesson,
2026-07-02): the per-run A/B "new FP: none" is NOT sufficient when re-run metrics were
produced by candidate code — always check the **absolute** `candidate: fp=N` against 9.

---

## Architecture: three tiers, strict ordering

| Tier | Tasks | Nature | Cost | Expected recall |
|------|-------|--------|------|-----------------|
| 0 | Task 1 | FN forensic audit + label-noise quantification | Analysis only | Sets the *honest* ceiling |
| A | Tasks 2–5 | Hand-engineered lineage-forensic signals (no ML) | Code + serialized re-runs | +5–15 pts (coverage-dependent) |
| B | Task 6 | Pretrained neural fingerprint embedding (inference only) | Model download + batch inference | Unknown; gap-gated |
| C | Task 7 | Custom contrastive embedding (train from scratch) | GPU training | The >80% path, if labels permit |

Tier 0 must complete first — if a large fraction of the corr<0.05 FN are label noise,
the true positive population shrinks and Tiers B/C targets must be re-based before any
training investment. Tier A signals are also the **verification layer** for Tier B/C
(a learned merge proposal needs at least one independent forensic confirmation).

---

## Task 1 — FN forensic audit + label-noise quantification (Tier 0)

**Why:** the 857 corr<0.05 FN conflate two populations with opposite implications:
(a) true same-lineage pairs degraded past waveform correlation → recoverable by
Tiers A–C; (b) curator mislabels (different recordings marked same family) →
*unrecoverable by definition*, and poisonous as training positives for Task 7.
Nobody has measured the mix.

### 1.1 Stratified sample

New script `tools/tapematch/audit_fn.py`. From `regression_set.json` positives still
verdicted `different_family`, draw a stratified sample of **60 pairs**:
20 with detected-and-corrected speed offset, 20 `speed-unknown`, 20 staircase-involved.
Stratify secondarily on |hf_ceiling_a − hf_ceiling_b| (>1 kHz vs ≤1 kHz).

### 1.2 Per-pair evidence dossier

For each sampled pair, emit (markdown, one section per pair):
- `lb_source_text` for both sides (taper/equipment/lineage strings from `sources`),
  plus `lb_relation_text` from `pairs`.
- hf_ceiling, noise_floor_db, dc_asymmetry, perf_dur ratio, track counts.
- A 4-band envelope-correlation quick check (see Task 4 math, throwaway inline
  version is fine) at the best available speed ratio.
- Verdict field `label_assessment: plausible-same-lineage | suspect-label |
  indeterminate` with one-line reasoning (e.g. source_texts name different tapers →
  suspect; identical lineage strings + one side "MP3 sourced" → plausible).

### 1.3 Deliverable

`tools/tapematch/FN_AUDIT_REPORT.md`: the dossier + a headline table — estimated
label-noise rate with a binomial 95% CI extrapolated to the 857-pair population, and
the re-based recall ceiling (e.g. if 25% are suspect labels, max achievable recall is
~(1575 − 0.25·857)/1575 ≈ 86% even with a perfect matcher). **This number re-scopes
Tiers B/C.** Flag every `suspect-label` pair in a new nullable column
`pairs.label_suspect` (INTEGER, 1 = suspect, via idempotent ALTER) so Tier C can
exclude them from training/eval.

No audio re-runs needed if raw metrics are already populated; where the envelope check
needs audio, serialize per the concurrency hazard (shared staging dir).

---

## Task 2 — Shared-flaw event fingerprint (Tier A, highest priority)

**Why:** tape dropouts, clicks, splices, and cut-ins are *inherited*: every descendant
of a transfer carries the ancestor's flaws at the same musical positions. Two
independent audience recordings of the same show share **zero** flaws (mic-side
artifacts are per-recording). This is the cleanest lineage-only signal available —
content-blind by construction — and it survives band-limiting (dropouts are
broadband energy events).

### 2.1 Per-source flaw timeline — `match.py: extract_flaw_events`

Input: mono 16 kHz memmap (existing analysis rate). Output: list of
`(t_sec, kind, strength)` with kinds:
- `dropout`: short-time RMS (20 ms hop) falls >20 dB below its 2 s local median for
  40–800 ms, then recovers. Exclude the trim head/tail and detected between-song
  quiet segments (reuse the hiss-segment detector's quiet mask — a between-song gap
  is not a dropout).
- `click`: sample-domain residual spike >6σ of local (50 ms) MAD, isolated (<5 ms).
  Cap at the 200 strongest per source.
- `cut`: instantaneous discontinuity in the 100-ms spectral centroid + RMS jointly
  jumping >4σ (splice/track-seam signature). Reuse/extend the existing CDR
  re-tracking (staircase) edit detector rather than duplicating it.

Config block `flaw_fingerprint:` with all thresholds; `enabled: false` by default.
Persist per-source event count + serialized timeline into the run JSON (`sources`
section), not the DB (variable-length).

### 2.2 Pair scoring — `match.py: flaw_match_score`

Given the pair's speed ratio (from the existing estimate; if `speed-unknown`, fall
back to `duration_ratio_prior`) and coarse offset (from the existing alignment; if
none, best-offset search over event sets is cheap — they're sparse), map timeline A
onto B's clock and score:

```
matched = |{a ∈ A : ∃ b ∈ B, |map(t_a) − t_b| < tol ∧ kind_a = kind_b}|
flaw_match_score = matched / min(|A|, |B|)     (None if min(|A|,|B|) < flaw_min_events)
```

`tol = 0.5 s` (generous — residual ppm error over 2 h ≈ 0.3 s at 40 ppm),
`flaw_min_events = 5`. A score of None must stay None end-to-end (no 0.0 coercion —
absence of flaws is absence of evidence, not evidence of difference).

### 2.3 Persistence + verdict

- `pairs.flaw_match_score` REAL nullable (CREATE + idempotent ALTER in `open_obs_db`),
  populated by `insert_pairs`, auto-picked-up by `regression.py` METRIC_KEYS and
  `_SECONDARY_METRIC_COLS`.
- `verdict.py`: OR-path `flaw_match_score ≥ flaw_fingerprint.merge_threshold`
  (provisional 0.6 — calibrate per protocol) **AND** `min_events` both sides ≥ 8.
  Gated on `flaw_fingerprint.enabled`; inert on NULL rows (same pattern as the
  dormant triplet path — copy it).

### 2.4 Unit tests

Synthetic: inject dropouts/clicks at known times into noise + tone, verify extraction;
verify inherited-flaw pair scores ~1.0 under ±5000 ppm speed warp; verify two
independently-flawed signals score ~0. Byte-identical equivalence on historical rows
(extend `test_verdict_equivalence.py`).

---

## Task 3 — Spectral-ratio stationarity (Tier A)

**Why:** if A and B descend from the same recording, B(t) ≈ H(A(t)) for a *fixed*
transfer function H (the copy chain's EQ/band-limit) — the frame-wise log-spectral
ratio between time-aligned A and B is **constant over time** (up to noise). Two
different recordings of the same show have time-varying ratios (different mic/room
positions respond differently as the source moves/levels change). This is phase-blind
and magnitude-only, so it works exactly where `residual_corr` dies (corr ~0.005), and
it was pre-identified in FIXES as a promising out-of-scope feature.

### 3.1 Metric — `match.py: spectral_ratio_stationarity`

On time-aligned 60 s windows (reuse the windowed-coverage grid + speed mapping):
1. Log-mel spectra (32 bands, cap top band at `min(hf_ceiling_a, hf_ceiling_b, 0.45·sr)`
   — never compare above the narrower side's ceiling).
2. Per window w: `R_w[band] = median_t(logmel_A − logmel_B)` over frames where both
   sides are above the noise floor (skip quiet frames).
3. Stationarity = `1 − mean_band(std_w(R_w)) / stationarity_norm_db` clipped to [0,1],
   computed only over windows with sufficient energy; `None` if <
   `stationarity_min_windows` (default 6) usable windows.

`stationarity_norm_db` provisional 6.0 (a 6 dB per-band wobble across the show → 0).
Config block `spectral_stationarity:`; `enabled: false` default.

### 3.2 Persistence + verdict

`pairs.spec_stationarity` REAL nullable, same plumbing as 2.3. Verdict use is
**conjunctive only**: stationarity never merges alone — it is one leg of the Task 5
combination rules (it is content-adjacent at the "did they align at all" level, so a
lone-merger path is banned until calibration proves a gap; expected TP band ≥0.7,
same-show TN expected lower but MUST be measured).

### 3.3 Unit tests

Synthetic: same signal + fixed EQ + noise → stationarity high; two different signals
(or same signal with slowly time-varying EQ) → low. Alignment-jitter robustness
(±0.5 s) test.

---

## Task 4 — Band-limited envelope correlation (Tier A, high collision risk — handle like triplet)

**Why:** corr<0.05 reflects destroyed HF *fine structure*; the coarse energy envelope
in the surviving band (say 200 Hz–2 kHz at 20 Hz frame rate) survives lossy/band-limited
generations. Same-lineage pairs should envelope-correlate near 1.0.

**⚠️ Explicit risk:** envelope is music-dominated — two audience recordings of the same
show WILL correlate substantially. This is the triplet failure mode. The signal is
included because, unlike triplet Dice, envelope corr of the *same* recording should
approach 1.0 while different recordings saturate lower (audience/room differences),
so a usable gap MAY exist near the top (e.g. 0.97 vs 0.90). If calibration shows
gap < 0.10, **reject it without appeal** (do not iterate thresholds; the population
answer is structural, per the triplet precedent).

### 4.1 Metric — `match.py: envelope_corr`

Band-limit both sides to `[200 Hz, min(hf_ceiling_a, hf_ceiling_b, 2000 Hz)]`,
RMS envelope at 20 Hz frame rate, speed-map, Pearson over the aligned overlap
(≥10 min required, else None). Column `pairs.env_corr`. Config `envelope_corr:`,
`enabled: false`.

### 4.2 Verdict use

Conjunctive only, and only ever paired with a lineage-pure signal (flaw or
stationarity). Never a lone merge path, even if calibrated — this is a hard spec rule.

---

## Task 5 — Evidence combination + verdict integration (Tier A close-out)

### 5.1 Combination rules (all in `config.yaml`, all `enabled: false` until calibrated)

`verdict.py` gains an `addon_links` section evaluated alongside existing paths:

- **Rule A (lone lineage):** `flaw_match_score ≥ T_flaw` (≥8 events both sides).
- **Rule B (two-leg):** `spec_stationarity ≥ T_stat` AND `env_corr ≥ T_env`.
- **Rule C (belt-and-braces, for Tier B/C later):** `emb_score ≥ T_emb` AND
  (`flaw_match_score ≥ T_flaw_weak` OR `spec_stationarity ≥ T_stat`).

Every rule independently gated + thresholded in config; NULL on any leg → rule
abstains. No rule may reference `lb_says_same` or `entry_lineage` (keeps the frozen
set a valid negative control — the curator-keying circularity finding stands).

### 5.2 Calibration + rollout (per signal, in order 2 → 3 → 4)

Follow the **Calibration protocol** below; ship each signal's `enabled: true` only
after it passes. Re-run the four control dates (1991-02-10, 1990-06-01, 1996-07-21,
1998-10-28) every iteration. Serialize all live sessions (shared staging dir).

### 5.3 Coverage instrumentation

`regression.py score --cached` extension: per-signal coverage line — how many frozen
FN pairs have a non-NULL value for each new metric. Tier A's recall contribution is
bounded by coverage; report it explicitly so a "signal works but only 40 pairs have
flaws" outcome is visible immediately.

---

## Task 6 — Pretrained neural fingerprint embedding (Tier B)

**Why before training from scratch:** robust audio fingerprinting models (e.g.
neural audio fingerprinting à la Chang et al. 2021 / "Now Playing"-style embeddings)
are trained for exactly this transformation class — same recording under severe
channel degradation (noise, reverb, EQ, codec). Inference is CPU-feasible in batch.
This measures whether *any* learned representation separates the population before
committing to Tier C training.

### 6.1 Harness — `tools/tapematch/embed_eval.py` (offline, no verdict wiring yet)

1. Pick one open-weights fingerprint/embedding model; pin the exact checkpoint +
   version in the script and `requirements.txt`. Justify the choice in the report
   (input sr, window, training augmentations).
2. For each source on the evaluation dates: embed 1 s windows with 0.5 s hop over
   5 evenly-spaced 60 s excerpts (reuse trim bounds; memmap discipline).
3. Pair score = for each window in A, cosine-max over B's windows in a ±tol aligned
   neighborhood (speed-mapped); `emb_score` = median of per-window maxima.
4. Evaluation set: ~60 frozen TP, ~60 same-date different-source TN (**mandatory** —
   this is the population that killed triplet), ~60 corr<0.05 FN excluding
   Task-1 `label_suspect` pairs.

### 6.2 Gate + wiring

Report TP / same-show-TN / FN distributions exactly like `calibrate_triplet.py`
(reuse its structure). **Gap ≥ 0.10 between TP p10 and same-show-TN p90 required.**
- Pass → `pairs.emb_score` column (same plumbing as 2.3), verdict Rule C only
  (never lone-merge), full regression gate.
- Fail → write the negative result into the report (distributions + gap), stop
  Tier B, and carry the same-show collision measurement into Task 7 as its baseline.

---

## Task 7 — Contrastive lineage embedding (Tier C — the >80% path)

Only start after Tasks 1–6 are reported. This is the explicitly out-of-scope model
from CC_TAPEMATCH_FIXES, now in scope. Spec here covers the protocol; implementation
details (architecture depth, LR schedules) are left to the implementer within these
rails.

### 7.1 Training data — self-supervised, zero curator labels

**Positives are synthetic** — two augmented views of the same audio window, with the
augmentation menu modeled on the *observed* transfer chains (this is the crucial
domain knowledge; encode each as a config-listed probability):
- speed warp ±6% (covers the observed −56,500…+45,800 ppm with margin),
- low-pass at 1.5–8 kHz (observed hf_ceilings go down to 2.0 kHz),
- lossy codec round-trip (MP3 96–192 kbps — lossy lineage is named in the FN evidence),
- additive tape hiss + level rides, mild EQ tilt, wow/flutter (slow ±0.3% LFO warp),
- generation stacking: compose 2–3 of the above (a 3rd-gen tape is a *composition*
  of degradations).

**Hard negatives are the triplet killer, weaponized:** time-aligned windows from
*different sources of the same concert* — mined from observations.db same-date
different-family pairs (~1390 frozen negatives + unlabeled same-date pairs). The loss
must explicitly push these apart. This single design choice is what separates Tier C
from every failed content-based signal. Easy negatives: random windows from other
shows.

Curator labels (minus `label_suspect`) are used ONLY for evaluation, never training →
no circularity; the frozen set remains a valid measuring instrument.

### 7.2 Model + features

Input: log-mel (e.g. 64 bands, 16 kHz, 1–3 s windows) — same front end family the
pipeline already computes. Model: small conv encoder (≤10 M params), embedding
dim 128, InfoNCE/NT-Xent with the same-show hard negatives in-batch at a fixed
minimum rate (e.g. ≥25% of negatives per batch). Training needs a GPU; document
the environment. Inference must run CPU-batch on the archive (that's the production
constraint; measure throughput).

### 7.3 Evaluation gates (in order; each is a hard stop)

1. **Augmentation sanity:** self vs augmented-self score ≥ 0.8 across the full
   augmentation menu (the invariance triplet never had).
2. **Same-show gap:** TP p10 − same-show-TN p90 ≥ 0.10 on the Task 6 evaluation set.
   (Triplet baseline: −0.012. This is the make-or-break number.)
3. **Frozen-set regression:** wire as `pairs.emb_score` + Rule C (conjunctive with a
   forensic leg), `regression.py score --cached` + live `--dates` on re-run dates,
   absolute fp ≤ 9. Zero new FP or reject.
4. **Recall accounting:** per-category FN-flip table (speed-corrected / speed-unknown /
   staircase), so the final report states exactly which population the model recovers.

### 7.4 Deliverables

`tools/tapematch/embedding/` package (train script, augmentation module with its own
unit tests, inference CLI), model checkpoint path in config
(`embedding.checkpoint`, `embedding.enabled=false` default), evaluation report, and
the Rule-C verdict wiring.

---

## Calibration protocol (applies to EVERY new signal — generalizes FIXES §7.4)

1. Populate the metric on real audio for ≥100 pairs spanning: frozen TP, **same-date
   different-source TN** (mandatory; never rely on synthetic negatives — the triplet
   synthetic test under-estimated same-show collision by 10×), and target FN.
2. Print distributions (median, p10/p90) per population + the zero-FP threshold +
   gap. **Ship only if gap ≥ 0.10**; if narrower, the signal is rejected structurally
   — do not threshold-shop.
3. Wire to verdict behind `enabled: false`; prove byte-identical historical behavior
   (extend `test_verdict_equivalence.py`).
4. Enable → `regression.py score --cached`, then `--dates` on re-run dates. Check
   **absolute** `candidate: fp` ≤ 9 (not just "new FP: none" — guard-masking lesson).
5. Control dates every iteration: 1991-02-10, 1990-06-01, 1996-07-21, 1998-10-28.

## Constraints (all tasks)

- Precision is the asset: absolute fp ≤ 9 on the frozen set; any new FP rejects.
- Strictly additive DB schema: nullable columns, CREATE + idempotent ALTER in
  `open_obs_db`, no destructive migrations. NULL means "not measured", never 0.
- `verdict.py` stays the single source of truth for clustering; no threshold logic in
  `cli.py`/`gen_analysis.py`. All thresholds in `config.yaml`, every new signal
  `enabled: false` by default.
- No verdict rule may key on `lb_says_same` or `entry_lineage` (frozen-set validity).
- Memory: full-length arrays via the memmap tmp-dir pattern; assume 2-hour sources.
- Do NOT resample before `secondary_corr_pair` (standing WORKFLOW.md rule).
- **Serialize all live audio sessions** — shared staging dir `/mnt/DATA0/examples/
  tapematch`; a concurrent run kills the other (learned 2026-07-02).
- Never run the pytest `test_batch_queue` family (contaminates observations.db).
- Python via `.venv/bin/python3`; `py_compile` every touched file; logging not print.
- After each task: harness run, CHANGELOG.md prepend, WORKFLOW.md knob/failure tables.
- No screenshot/visual verification — human sign-off happens outside this spec.

## Explicitly out of scope

- htdemucs stem analysis (cost/benefit unproven; revisit only if Tier C fails).
- Any change to primary residual_corr math or anchor selection.
- Re-enabling the triplet fingerprint (rejected structurally; re-armable only via a
  demonstrated ≥0.10 gap, which Task 6/7 measurement would surface anyway).
- Changing frozen-set labels in place (Task 1 *flags* suspects; it never edits labels).

## Completion checklist

- [x] Task 1: FN_AUDIT_REPORT.md — label-noise rate 36.7% (CI 25.6–49.3%), re-based recall ceiling ~80.0% (CI 73.1–86.0%); 22/60 pairs `label_suspect` flagged (2026-07-02)
- [x] Task 2: flaw extraction + `flaw_match_score` implemented (code + synthetic unit tests,
  `enabled: false`) — NOT yet calibrated on real audio; do not enable before the Calibration
  protocol (2026-07-02)
- [x] Task 3: `spectral_ratio_stationarity` + `pairs.spec_stationarity` implemented (code +
  synthetic unit tests, `enabled: false`, no OR-path — conjunctive-only per spec) — NOT yet
  calibrated on real audio; do not enable / wire into Task 5 `addon_links` before the Calibration
  protocol (2026-07-02)
- [x] Task 4: `envelope_corr`/`env_corr` implemented (code + synthetic unit tests, `enabled: false`,
  no OR-path — conjunctive-only per spec, and permanently banned from a lone-merge path even
  post-calibration per 4.2) — NOT yet calibrated on real audio; do not enable / wire into Task 5
  `addon_links` before the Calibration protocol (2026-07-02)
- [x] Task 5: `addon_links` (Rule A/B/C) in verdict.py, all `enabled: false`; Task 2.3's standalone
  flaw OR-path folded into Rule A (single canonical flaw path); per-signal FN coverage line added
  to `score --cached` — flaw_match_score/spec_stationarity 0/920 (0.0%), env_corr/emb_score columns
  not yet present in this DB so omitted — NOT yet calibrated; do not enable any rule before the
  Calibration protocol (2026-07-02)
- [ ] Task 6: pretrained-embedding eval report — gap number vs triplet's −0.012; wired or stopped
- [ ] Task 7: contrastive model trained per protocol; gates 1–4 passed or negative result reported
- [ ] Final report: recall/precision vs 41.6%/98.6%, per-tier + per-FN-category recovery table
- [ ] CHANGELOG.md, WORKFLOW.md, PROJECT.md updated
