# TapeMatch Recall-Recovery — Live Progress / Resume Doc

**Purpose:** orchestration state for the CC_TAPEMATCH_FIXES effort so any new session
can resume without re-deriving context. Keep this updated as runs complete.

Last updated: 2026-07-02 (session in progress)

---

## Goal & scope
- **Goal:** dramatically improve tapematch recall (baseline 38.3%) without regressing
  precision (98.2%). Precision is the asset — a new false merge on a frozen negative
  REJECTS a change.
- **Scope cap (user decision 2026-07-02):** Tasks 1–4. Defer Tasks 5–7 (estimate_ratio_v2,
  pyin, triplet fingerprint — the big Cat-1 speed work).

## Baseline numbers (the frozen set)
- Audit baseline (raw pairs, pre-dedup): tp=663 fn=1066 fp=12 tn=1422 → P0.982 R0.383.
- Frozen set (deduped via `latest_pairs`): tp=618 fn=957 fp=9 tn=1381 → P0.986 R0.392.
- Frozen file: `tools/tapematch/regression_set.json` (1575 pos + 1390 neg = 2965 labeled).

## DATA — critical
- `tools/tapematch/observations.db` = the labeled-pairs DB (8022 pairs / 885 dates).
  It had been **moved to Trash 2026-06-25**; restored from `~/.local/share/Trash/files/`.
- Backups: `observations.db.bak-precalib-*` (pre-calibration snapshot),
  `observations.db.bak-20260612_124147` (older). Trash original still present as safety.
- **Do NOT run the pytest `test_batch_queue`-family tests** — they call `run_batch`, which
  executes REAL tapematch sessions against the mounted /mnt collection and writes
  `20260702_*` runs into observations.db (contaminates the baseline). If contamination
  reappears: `DELETE FROM pairs WHERE run_id LIKE '20260702_%'` for stray dates (keep only
  the deliberate calibration runs listed below), then re-verify `score --cached`.

## What's DONE (code, no-audio)
- `tapematch/verdict.py` — single source of truth for pairwise clustering:
  `pair_links`, conditional `fp_threshold` (staircase 3.2 / curator 4.1), lo-fi
  `_effective_hiss_median` (4.2), transitive `cluster_verdicts`, `load_lineage_pairs`.
- `regression.py` — `freeze` / `score --cached` / `score --dates` / `--all-frozen-dates`.
  `score` does a clean A/B: candidate config vs an overrides-stripped baseline, BOTH
  recomputed from the same stored raw metrics on re-run dates (no delta on un-run dates).
  Exit 1 on any new FP vs a frozen negative.
- `match.cluster` gained `link_fn`; `cli.py` routes clustering through `verdict.pair_links`
  (proven byte-identical: `tests/test_verdict_equivalence.py`, 164 tests green).
- `config.yaml` new keys: `fingerprint.cluster_threshold_staircase=0.40` / `_curator=0.43`,
  `secondary_match.hiss_merge_median_lofi=0.40` / `hiss_lofi_ceiling_hz=12000`.
- `pairs` schema: added nullable `windowed_frac/hiss_frac/hiss_median/fp_score/
  nyquist_capped_a/_b` (CREATE + idempotent ALTER in `open_obs_db`); `insert_pairs`
  populates them from the run JSON's `secondary_pairs`/`sources`.
- `rerun_cat3.py` (Task 2) — Cat-3 focused re-run; `--list` works (137 pairs, not spec's 6).

## MEASUREMENT approach (how we prove a change)
1. Re-run a date via `tapematch_session.py <date>` → populates raw secondary metrics.
2. `regression.py score --cached` recomputes verdicts from those raw metrics for BOTH
   candidate (with 3/4 overrides) and baseline (overrides stripped) configs via
   `verdict.cluster_verdicts` (which applies curator + lo-fi from DB rows + entry_lineage).
   → the delta isolates the threshold change; new FP ⇒ exit 1 ⇒ reject.
   NOTE: the live `cli.py` run does NOT yet apply curator/lo-fi (lb#/hf_ceiling not threaded
   into its metrics builder), but the HARNESS does — so measurement is complete even before
   that live-wiring. Wire curator/lo-fi into `cli.py:_pair_metrics` before production deploy.

## SHOW SELECTION (data-driven, from observations.db)
### Control set — run EVERY iteration (regression sentinels)
- `1991-02-10` — 19 hard negatives, all currently correct → catches any false merge instantly.
- `1990-06-01` — 3 current FPs (worst precision date) → guard + fix target.
- `1996-07-21`, `1998-10-28` — spec-named controls, small mixed known-good.

### Calibration set — staircase recall (Task 3.2 lever)
- `1996-11-04` — 17 pos, 8 TP, **7 staircase FN** (richest).
- `1993-06-27` — 7 pos, **5 staircase FN + 9 hard negatives** (dual-purpose).
- `2001-10-30` — 4 staircase FN, mixed (spec calibration date).

### Category totals (frozen set): FN=958, FP=9, TP=618 across 827 dates.
- Cat 2 (staircase FN) is the in-scope recall lever. Cat 1 (speed, ~527) is Tasks 5–7.
- **OPEN QUESTION the runs answer:** are the staircase/curator FN pairs' `fp_score`/
  `hiss_median` actually in the recoverable band (fp 0.40–0.50)? If they cluster near 0,
  Task 3/4 can't move recall and the real lever is Cat-1 speed (Tasks 5–7).

## ⚠️ CONCURRENCY HAZARD (learned 2026-07-02 11:00 the hard way)
`regression.py score --dates <d>` does a LIVE session re-run (NOT cached) and all sessions
share the staging dir `/mnt/DATA0/examples/tapematch` (clean+copy on start). NEVER run a
live session/score --dates while another session/batch is running — the clean step killed
the batch's 1996-11-04 run (rc=1, 19s). DB verified clean after (no partial writes; failed
sessions die in copy, before analysis). Use `score --cached` for measurement; serialize all
live runs.

## BATCH STATUS
Runner: `tools/tapematch/calib_logs/run_batch.sh` → per-date logs + `progress.log`.
Timing: ~40s/source (1990-06-01 = 3 src = 125s).
Order: 1990-06-01 ✅(125s) → 1996-07-21(running) → 1998-10-28 → 1993-06-27 → 1996-11-04 → 1991-02-10.

| Date | sources | status | notes |
|------|---------|--------|-------|
| 1990-06-01 | 3 | ✅ done 125s | precision (3 FP) — FPs are fp_score-driven (0.46-0.53) |
| 1996-07-21 | 5 | ✅ done 473s | control — no regression; recoverable curator FN 4861/6985 fp0.472 |
| 1998-10-28 | 5 | ✅ done 432s | control — no regression; non-recoverable FN 3725/6168 fp0.381 |
| 1993-06-27 | 7 | ✅ done 1096s | staircase+neg — KEY DATA (see findings: bands overlap) |
| 1996-11-04 | 7 | ❌ rc=1 (collision) | KILLED by concurrent score --dates; re-run queued after 1991-02-10 |
| 1991-02-10 | 8 | ⏳ running | precision sentinel — first live run of newly wired cli.py |

**Background jobs running (survive context clear):**
- `run_batch.sh` — the 6-date session batch (detached).
- `analyze_staircase.sh` — waits for `DONE 1996-11-04`, then writes the A/B + staircase
  fp/hiss band table to `tools/tapematch/calib_logs/staircase_analysis.txt` (ends `ANALYSIS_DONE`).

## FINDINGS (update as runs land)
- **1990-06-01 (done):** its 3 FPs are FINGERPRINT-driven false merges — corr~0.002,
  windowed=0, but fp_score = 0.53 / 0.52 / 0.46 on different-source same-show pairs. Two
  exceed the 0.50 cluster bar directly; the third joins transitively. These are NOT
  staircase (kinds reference/const-offset), so the candidate's 0.40 staircase bar doesn't
  touch them → they persist in BOTH baseline and candidate (pre-existing, not new FPs).
  **Key risk this exposes:** different-source same-show fingerprint scores reach 0.35–0.47
  (config's own note), so LOWERING the staircase/curator fp bar to 0.40–0.43 can manufacture
  new false merges. Whether Task 3.2/4.1 nets positive depends on whether the recoverable
  staircase-FN fp band (need > new bar) separates from the staircase-negative fp band. The
  staircase dates (1993-06-27, 1996-11-04) answer this. The harness auto-rejects (exit 1) on
  any new FP, so this is safe to test empirically.
- Timing: cross-family secondary+fingerprint passes dominate; 5-src date ≫ 40s/src estimate
  (1996-07-21=473s, 1998-10-28=432s for 5 src).
- **Controls (1996-07-21, 1998-10-28) done, no regression.** Known same-source pairs still
  correct (LB-513/6986 fp0.60 wf0.99; LB-6564/12485 corr0.520). Different-source negatives
  fp = 0.32–0.38 on these dates.
- **Recoverable curator FN:** 1996-07-21 LB-4861/6985 (says_same=1) fp=0.472 → currently FN
  (below 0.50). Above the 0.43 curator bar and above the date's negatives (≤0.38) → Task 4.1
  *should* recover it with no new FP. But it did NOT flip, because…
- **Curator-keying gap (IMPORTANT):** Task 4.1 keys on `entry_lineage.same_as_lb`, which covers
  only **244/1575 = 15.5%** of frozen positives and does NOT include LB-4861/6985. So 4.1 as
  specified barely fires. Alternative: key on `lb_says_same=1` (the signal that defines
  positives) → high coverage BUT circular: all frozen negatives are lb_says_same=0, so they
  never get the relaxed bar and the frozen set CANNOT measure that keying's false-merge risk
  (real-world risk: curator says same but it's actually a different transfer). Spec chose
  entry_lineage precisely to keep the relaxation label-independent. DECISION: report both;
  treat STAIRCASE (3.2) as the primary measurable lever; do NOT ship lb_says_same-keyed
  curator relaxation as a "win" since its FP cost is unmeasurable on this frozen set.
- **Non-recoverable FN example:** 1998-10-28 LB-3725/6168 (says_same=1) fp=0.381 (< 0.43),
  corr 0.015 → fingerprint genuinely doesn't match; this is Cat-1 speed territory (Tasks 5-7).
- **DB analysis (agent, 3 done dates):** zero staircase-kind negatives ≥0.40 (the 2 on
  1998-10-28 score 0.331/0.321) — no early FP risk from the 0.40 bar. Control dates have
  ZERO staircase positives, so recall evidence must come from 1993-06-27/1996-11-04.
  Root ./observations.db is 0 bytes (irrelevant). `human_judgment` is NULL DB-wide → truth
  labels ≡ lb_says_same exactly; lb_says_same-keyed curator relaxation is tautological on
  this set (do NOT ship as measured). entry_lineage coverage 244/1575 confirmed;
  LB-4861/6985 (fp 0.472) is says_same-only, not lineage-covered.

- **1993-06-27 (done) — STAIRCASE VERDICT DATA:** all 7 says_same FN pairs have fp_score
  0.273–0.368, ALL below the 0.40 staircase bar; same-date negatives span 0.265–0.387.
  The FN and TN fp bands FULLY OVERLAP — no staircase threshold separates them. Cached A/B
  across all 827 frozen dates: zero delta (R 39.2%→39.2%, P 98.6%, no new FP). Task 3.2
  recovers nothing at 0.40 and cannot be lowered without swallowing negatives. Unless
  1996-11-04 (re-run pending) contradicts, conclusion = doc's outcome 3: the recall lever
  is Cat-1 speed (Tasks 5–7, out of scope).
- **cli.py curator/lo-fi wiring (Task 4/step 5) DONE by agent:** `_pair_metrics` now gets
  lb_a/lb_b (regex from folder name), lineage via new `--lineage-db` arg (defaults to
  data/losslessbob.db, 677 pairs, inert on failure), and hf_ceiling/nyquist from a
  lineage-evidence pre-pass moved BEFORE clustering (print section reuses it, byte-identical
  output). 164 equivalence tests green; 2 pre-existing unrelated failures in
  test_find_lb_folders_no_audio.py. Known gap: folder names embedding a foreign LB number
  can mis-key curator live (harness unaffected). 1991-02-10 is the first live run of this code.

- **1996-11-04 re-run (11:46) — DECISION DATA, STAIRCASE WINS:** full cached A/B (827 dates):
  recall 39.2%→39.6% (+5 TP, 618→623), precision 98.6% unchanged, ZERO new FP → per step-2
  decision rule: **KEEP staircase 0.40**. The +5 TP are 1996-11-04 staircase pairs at
  fp 0.433–0.447 (LB-12343/LB-14002 links) recovered by the 0.40 bar. Near-misses: LB-1062
  pairs at fp 0.397–0.400 stay FN — do NOT chase with a lower bar (1993-06-27 negatives reach
  0.387; margin gone). NOTE: `score --cached` only sees FP risk on dates with populated raw
  metrics (the 6 run today + batch2) — global negatives fp reach 0.35–0.47 per config note,
  so more staircase-date coverage = more confidence, hence batch2.
- **Batch2 (expansion, launched 12:16, detached `run_batch2.sh` → progress2.log):**
  2001-10-30, 1990-08-12, 1991-06-06, 1990-11-08 (next-densest staircase-FN dates), then
  auto `score --cached` → `calib_logs/score_after_batch2.txt`. Confirms 0.40 at scale.

- **Batch2 DONE (13:09), CONFIRMED AT SCALE:** all 4 dates rc=0; final A/B: recall
  39.2%→**40.4%** (+18 TP, 618→636), precision 98.6%, ZERO new FP
  (`calib_logs/score_after_batch2.txt`). Staircase 0.40 validated on 10 populated dates.
- **Batch3 RUNNING (launched ~13:35, detached `run_batch3.sh` → progress3.log):** top-15
  un-run staircase-FN dates (1992-06-30, 1987-09-12, 1987-09-23, 1989-06-20, 1995-03-12,
  1996-10-26, 1990-08-18, 1990-11-10, 1990-11-13, 1992-05-02, 1993-02-16, 1993-04-12,
  1993-04-19, 1995-04-09, 2001-07-18; 52 of the 79 remaining staircase FNs). Auto-guard:
  `score --cached` after EVERY date; new FP ⇒ BATCH3 ABORT in progress3.log. ~3–4 h.
  If aborted: raise `cluster_threshold_staircase` 0.40→0.42 and re-score before continuing.

- **FN sizing (agent, 939-FN live snapshot):** 875/939 FN (93%) have corr<0.05 — waveform
  correlation fails outright; Cat-1 territory. Staircase-involved FN = 254 (27%; overlaps the
  corr<0.05 core). NOTE: earlier "79 remaining staircase FN" was an undercount (LIMIT 30
  truncation) — real long tail is ~200 pairs at 1–2/date beyond batch3's 52. Staircase yield
  is BIMODAL by date (1996-11-04: 5/7 flip; 1993-06-27: 0/7). Ceilings from tp=636/1575:
  staircase fully recovered → 56.5%; realistic → ~45–50%; Cat-1 solved too → 83.9% max.
  ⇒ threshold work is nearing exhaustion; Tasks 5–7 (deferred) are the only path past ~50%.

## RESUME NOTE (2026-07-02 ~13:45 — for the next session, act as orchestrator)
- **USER DECISION: Tasks 5–7 UN-DEFERRED** (scope cap lifted; Cat-1 is the payoff per FN sizing).
- FIRST ACTION: read `instructions/CC_TAPEMATCH_FIXES.md` Tasks 5 (line ~245), 6 (~351),
  7 (~436) + Constraints (~517). Spawn sonnet implementation agents with MINIMAL context
  (task + paths + constraints; user is in token-conservation mode; no unnecessary status
  updates). Task 5 (estimate_ratio_v2) first; 6/7 depend on/integrate with it.
- **Serialize audio:** batch3 runs detached until ~17:00–17:30 (progress3.log; self-aborts
  on new FP). NO live tapematch sessions / `score --dates` until `BATCH3 END` appears
  (shared staging dir — see CONCURRENCY HAZARD above). Code + unit tests only until then.
- After BATCH3 END: check `calib_logs/score_latest.txt` (recall vs 40.4%, still 0 new FP);
  if ABORT in progress3.log → raise `cluster_threshold_staircase` to 0.42, re-score, continue.
  Then decide staircase long-tail sweep (~200 pairs @1–2/date, low ROI) vs Task 5–7 validation
  runs (must also serialize).
- Task 5–7 validation gate: `regression.py score --cached` + Task 7.4 calibration protocol
  BEFORE enabling triplet fingerprint in verdicts. Exit 1 = reject, as always.

## NEXT STEPS (resume here — FIRST ACTION)
0. **Read `tools/tapematch/calib_logs/staircase_analysis.txt`** (the armed analyzer writes it
   when 1996-11-04 finishes; look for `ANALYSIS_DONE`). Also `cat calib_logs/progress.log`.
   If the batch/analyzer died mid-way, relaunch: `bash tools/tapematch/calib_logs/run_batch.sh`
   for any un-run dates, then `bash tools/tapematch/calib_logs/analyze_staircase.sh`.
1. Interpret the staircase band table: for the staircase-FN pairs, is fp_score in [0.40,0.50)
   (recoverable by the 0.40 bar) or ~0 (not)? For staircase-NEGATIVE pairs, are any fp_score
   ≥ 0.40 (would become NEW false merges)? The `score --cached` A/B already reports net
   recall/precision delta + lists any new FP (exit 1 = reject).
2. DECISION:
   - If staircase bar nets recall↑ with zero new FP on frozen negatives → keep 0.40; expand to
     more staircase dates (see selection query below) to confirm at scale.
   - If new FPs appear → raise `cluster_threshold_staircase` in 0.02 steps (0.42, 0.44…) until
     clean; report the final value.
   - If staircase FN fp_scores are ~0 → Task 3.2 can't help; the lever is Cat-1 speed (Tasks 5-7,
     out of current scope) — report this clearly to the user.
3. Curator (4.1): report entry_lineage-keyed result (low coverage) AND the lb_says_same-keyed
   result, but flag the latter as unmeasurable-FP (circular). Do NOT ship lb_says_same keying
   as a win without an independent negative control.
4. Re-run the control set (1991-02-10, 1990-06-01, 1996-07-21, 1998-10-28) EVERY iteration.
5. Wire curator/lo-fi into `cli.py:_pair_metrics` for production once thresholds are final
   (currently only the harness applies them; live cli.py applies only staircase).

### More staircase dates to expand calibration (by FN-staircase density)
1996-11-04(7), 1993-06-27(5), 2001-10-30(4), 1990-08-12(3), 1991-06-06(3), 1990-11-08(3).

## Resume commands
```
# batch status
cat tools/tapematch/calib_logs/progress.log
# measure
.venv/bin/python3 tools/tapematch/regression.py score --cached
# re-run a date
.venv/bin/python3 tools/tapematch/tapematch_session.py 1996-11-04
# targeted tests (safe subset — NOT the batch_queue family)
.venv/bin/python3 -m pytest tools/tapematch/tests/test_verdict_equivalence.py -q
```

## PHASE 1 COMPLETE — Tasks 5–7 IMPLEMENTED (code + unit tests, no live audio) 2026-07-02 ~14:30
Scope-cap lifted (user un-deferred 5–7). All work done on the main tree while batch3
ran; NO live sessions touched. **175 tests green** (164 verdict-equivalence unchanged
+ 7 speed_v2/pyin + 4 triplet). py_compile clean on all touched files.

### Task 5+6 (sonnet agent) — `match.py`, `align.py`, `cli.py`
- `estimate_ratio` → `estimate_ratio_v1_deprecated` (kept for A/B); added `duration_ratio_prior`,
  `estimate_ratio_v2(ref,other,sr,cfg,prior=None)`, `pitch_ratio_pyin`, `_pick_pitch_windows`.
- `align.residual_ppm_from_lag_curve(rows)->(ppm,r2)` with r²>0.85 + <4-anchor guards;
  wired into the PRIMARY residual-corr matrix loop ONLY (never before secondary_corr_pair);
  guards (r²>0.85, |ppm|>50, ≤2 iters) hardcoded (not config — spec constants).
- Confidence gate at all 3 cli.py call sites: below `align.ratio_confidence_min` (=6.0) →
  `speed_kind="speed-unknown"`, not resampled, counted/logged, added to JSON `speed_confidence`.
  Duration prior plumbed from `trim_bounds` perf_durs via `_dur_prior`. NUMBA_CACHE_DIR set at import.
- **FLAG 1 (pyin direction):** agent used `ratio = med_other/med_ref` (spec prose said the
  inverse) to match `resample_ratio`'s divide-by-ratio convention. Self-limiting (pyin only
  fires for speed-unknown + no-duration-prior; can't manufacture FP) → wrong direction only
  costs recall. VERIFY vs real audio in Phase 2.
- **FLAG 2 (pyin precision):** librosa.pyin default resolution ≈5800 ppm bins can't hit the
  spec's ±300 ppm without ~100× runtime. Acceptable: pyin rarely fires (durations usually
  available) and residual-lag + triplet carry the load. Validate on real audio.

### Task 7 (orchestrator) — triplet fingerprint
- `match.py`: `_fingerprint_peaks` (absolute Hz — needed so f-ratios are true pitch ratios,
  undistorted by hf_band lo_bin offset), `triplet_hashes` (6-bit r_t log[0.25,4] | 7-bit
  r_f1/r_f2 log[0.5,2] → 20-bit int), `triplet_window`, `_quant_log`. Reuses existing STFT +
  `_find_peaks_2d` front end (same hf_band → same-show rejection preserved).
- `cli.py`: `tri_hashes` built in the fingerprint loop (source mmap'd once); per-pair
  `sec["fp_triplet_score"]` = Dice, or None when `fingerprint.triplet.enabled` is false.
- Schema: `pairs.fp_triplet_score` REAL (CREATE + idempotent ALTER in `open_obs_db`);
  persisted by `insert_pairs` (38 non-id cols verified). `regression.py` auto-selects it
  (METRIC_KEYS) + added to `_SECONDARY_METRIC_COLS`.
- `verdict.py`: triplet OR-path, gated on `fingerprint.triplet.enabled` + threshold, **inert
  on historical rows** (column NULL) → equivalence tests byte-identical (proven, 164 green).
- `calibrate_triplet.py` (Task 7.4, DB-only): reads `fp_triplet_score` for frozen TP/TN/Cat-1
  from observations.db, prints distributions + zero-FP bar + gap-midpoint threshold recommendation.
- **FLAG 3 (triplet absolute Dice vs separation):** synthetic invariance shows the spec's
  "self-vs-resampled Dice >0.8" is NOT reached by the STFT peak front end — even +500 ppm drops
  same-source to ~0.5, plateauing ~0.39 by +30000 ppm (STFT frame-quantization of nearest-
  neighbour triplets). What IS delivered: same-source ~0.4–0.6 FLAT across the whole speed
  range, ~6× above different-source (~0.065). So clustering works via SEPARATION; the provisional
  `fingerprint.triplet.cluster_threshold=0.45` is likely TOO HIGH (would miss ~0.4 same-source) —
  **do NOT trust it; calibrate_triplet.py sets the real value from Phase-2 audio.** 0.45 is safe
  (no FP), just under-recovers; precision (the asset) is preserved either way.

## PHASE 2 — LIVE VALIDATION (pending BATCH3 END, ~16:00–17:30) — SERIALIZE ALL LIVE RUNS
Config keys already staged (align.ratio_confidence_min, align.pyin_fallback, fingerprint.triplet.*).
After `BATCH3 END` (watch progress3.log; if `BATCH3 ABORT` → raise staircase 0.40→0.42, re-score):
1. Re-run a spread of frozen Cat-1 dates (corr<0.05 dense) live to populate `fp_triplet_score` +
   the new speed metrics. Serialize (shared staging /mnt/DATA0/examples/tapematch).
2. `calibrate_triplet.py` → set `fingerprint.triplet.cluster_threshold` at the TP/TN gap
   (require ≥0.10 width; if narrower, raise freq-ratio quant 7→8 bits in `triplet_hashes`).
3. `regression.py score --cached` (then `--dates` on re-run dates): zero-new-FP gate stands
   (exit 1 = reject). Confirm estimate_ratio_v2 nets the Cat-1 recall jump; verify FLAG-1 pyin
   direction on a real speed-offset pair.
4. Control set every iteration: 1991-02-10, 1990-06-01, 1996-07-21, 1998-10-28.
5. Then consolidate docs (CHANGELOG/PROJECT/WORKFLOW) + move Task-6.1 guard constants to config
   if desired. Target: family grouping >80% (Cat-1 ceiling ~84%).

## PHASE 2 LIVE RESULTS (2026-07-02 ~16:00) — TRIPLET REJECTED, precision-safe baseline set
**BATCH3 END** at 42.9% candidate — BUT that number was INFLATED by false merges (see below).

### ⚠️ Guard-masking lesson (important)
batch3 sessions launched AFTER ~14:01 ran the NEW code (Agent-1 v2, and after ~14:29 my triplet
path with `fingerprint.triplet.enabled=true`, threshold 0.45). The per-date batch guard compares
candidate-vs-baseline from the SAME stored metrics, so FALSE MERGES baked into the re-run metrics
appear in BOTH configs and slip past "new FP: none". The REAL guard is ABSOLUTE fp vs the frozen
count (9). It had climbed to 14 (precision 98.6%→97.9%). ALWAYS check absolute `candidate: fp=N`.

### TRIPLET FINGERPRINT (Task 7) = NEGATIVE RESULT — DISABLED
`calibrate_triplet.py` on real populated data (116 pairs): TP triplet-Dice median 0.656
(0.606–0.731), TN (same-date diff-source) median 0.638 (0.626–0.649) — **OVERLAP, gap −0.012**.
Same-concert recordings share real temporal/spectral structure, so ratio hashes collide even in
the hf_band. At 0.45 this made **5 false merges** on frozen negatives (1990-08-18 LB4930/7375;
1990-11-10 LB419/1201, LB419/10381, LB8282/10381; 1993-02-16 LB6019/8668) — all triplet=0.63–0.65.
The synthetic invariance test used INDEPENDENT layouts (Dice 0.065) and badly underestimated
same-show collision. Spec's 7→8-bit-quant fallback unlikely to help (collision is structural).
→ `fingerprint.triplet.enabled=false` in config.yaml. Code kept (dormant); OR-path inert when off.

### PRECISION-SAFE RESULT after disabling triplet (score --cached, 827 dates)
recall 39.4%→**41.5%** (+2.0), precision **98.6%**, fp=9 (== frozen), ZERO new FP. estimate_ratio_v2
caused NONE of the FPs (the 5 were all triplet; v2 pairs had corr~0.002). So v2 is precision-safe
so far, but was only exercised on staircase-focused batch3 dates — NOT yet on Cat-1-dense dates.

### NEXT: validate estimate_ratio_v2 on Cat-1-dense dates (the sole remaining >80% lever)
Re-run (serialized, absolute-fp≤9 guard) old-code Cat-1-dense dates and measure FN(corr<0.05)→TP
flips: 1990-01-12(9), 1994-04-28(9), 1989-06-04(8), 1994-07-04(8), 1990-10-26(7), 1991-06-11(6),
1991-11-05(6). If v2 raises corr on true Cat-1 same-source pairs → safe merges via PRIMARY corr path.
This is the make-or-break for family-grouping >80% now that triplet is out.

## PHASE 2 FINAL CONCLUSION (2026-07-02 ~17:30) — in-scope ceiling reached, >80% NOT achievable
Every in-scope recall lever was exercised and measured against the frozen set (score --cached,
absolute-fp≤9 guard). Final precision-safe state: recall **41.7%**, precision **98.6%**, fp=9,
zero new FP (config: `fingerprint.triplet.enabled=false`, `align.ratio_confidence_min=6.0`).

Lever-by-lever result:
- **Staircase 0.40** (Task 3): shipped, the main safe gain (~+2.3 over stripped baseline).
- **estimate_ratio_v2** (Task 5): precision-safe but recovers only ~+0.2 across 10 Cat-1-dense
  dates — it rescues only the "confident + already-correlating" minority.
- **Triplet fingerprint** (Task 7): REJECTED — same-show pairs collide (Dice 0.63–0.65 vs TP 0.66,
  gap −0.012); made 5 false merges at 0.45. Disabled.
- **Confidence-gate sweep** (ratio_confidence_min 6.0→4.5): +0.0. DEFINITIVE diagnostic — the
  stranded conf~5 pairs (e.g. a real −45800 ppm offset) DID resample at 4.5 but corr stayed
  0.002–0.010. **Waveforms do not correlate even when correctly speed-aligned.** Reverted to 6.0.
- Curator 4.1 (entry_lineage): live, low coverage. Lo-fi hiss 4.2: live (406 candidate pairs),
  folded into the aggregate.

ROOT FINDING: the corr<0.05 FN bulk (93% of all FN) is NOT a speed problem — those recordings
are genuinely non-correlating (independent-generation transfers / different noise, or curator
label noise). No speed/fingerprint/hiss method in this spec can merge them. **>80% requires the
explicitly OUT-OF-SCOPE contrastive-embedding (learned-similarity) model** — waveform/spectral/
speed methods have hit their ceiling at ~42% recall / 98.6% precision.

STILL OPEN (spec deliverables, NOT recall levers): gen_analysis.py → latest_pairs migration
(Task 1.4, verified NOT done — still reads `pairs`); confirm Cat-3 rerun (Task 2) logged+reported;
final harness report vs 38.3%/98.2% + per-category table; CHANGELOG/WORKFLOW/PROJECT updates.
CODE STATE: all Task 5/6/7 code committed to the working tree, 175 tests green; triplet code is
dormant (enabled=false) not deleted — re-armable only if a >=0.10 TP/TN gap is ever demonstrated.

## CC_TAPEMATCH_ADDON Task 1 (Tier 0) COMPLETE (2026-07-02) — honest ceiling re-based to ~80%

`tools/tapematch/audit_fn.py` recomputed the live corr<0.05 FN population (**859** pairs,
via the same `verdict.cluster_verdicts` path `regression.py score --cached` uses — close to
the "857/917" figure above, small drift expected), drew a stratified 60-pair sample (20
speed-corrected / 20 speed-unknown / 20 staircase x hf_ceiling-gap secondary strata), and
scored each pair with a transparent heuristic (priority order: explicit "different recording"
text in `lb_relation_text`/`lb_source_text` > taper-name conflict > speed-corrected duration-ratio
mismatch >15% > explanatory lossy/band-limited lineage > throwaway 4-band envelope-corr quick
check >=0.30 > indeterminate). Full dossier + methodology: `tools/tapematch/FN_AUDIT_REPORT.md`.

**Result: 22/60 (36.7%, Wilson 95% CI 25.6–49.3%) are curator label noise**, not recoverable by
any waveform/spectral method — extrapolated to ~315 of the 859-pair population (CI 220–424).
**Re-based recall ceiling: ~80.0% (CI 73.1–86.0%)**, down from the naive 100%-implies-perfect-
matcher framing. This re-scopes Tiers B/C: even a perfect learned-similarity model tops out
near 80% recall on this frozen set, not >95%. Flagged pairs: `pairs.label_suspect=1` (22 rows;
nullable INTEGER, idempotent ALTER in `tapematch_session.open_obs_db`, NULL=not-assessed).
Frozen-set labels in `regression_set.json` were NOT edited — Tier C training/eval should filter
`label_suspect IS NULL OR label_suspect=0` (currently only NULL/1 exist; 0 is never written).

NEXT: Tier A (Tasks 2–5) — flaw-fingerprint / spectral-stationarity / envelope-corr signals —
should now target closing the gap to ~80%, not 100%. Tier B/C evaluation sets (Task 6.1's
"~60 corr<0.05 FN" sample) must exclude `label_suspect=1` pairs.

## CC_TAPEMATCH_ADDON Tier A (Tasks 2–5) CODE COMPLETE (2026-07-02 evening)

All three lineage-forensic signals + the combination layer are implemented, unit-tested,
byte-identical on historical rows, and shipped `enabled:false`. ~269 tests green (only the 2
long-standing `test_find_lb_folders_no_audio.py` failures remain, unrelated). Schema migrated:
`pairs` now has `flaw_match_score`, `flaw_n_events_a/b`, `spec_stationarity`, `env_corr`,
`label_suspect` (45 cols total; idempotent ALTERs in `tapematch_session.open_obs_db`).

- **Task 2 flaw fingerprint** (`match.extract_flaw_events` / `flaw_match_score`): dropout/click/cut
  events, inherited-flaw scoring under speed warp. LINEAGE-PURE (content-blind).
- **Task 3 spectral stationarity** (`match.spectral_ratio_stationarity` → `spec_stationarity`):
  time-constant log-spectral ratio. CONJUNCTIVE-ONLY (no lone OR-path).
- **Task 4 envelope correlation** (`match.envelope_corr` → `env_corr`): band-limited RMS envelope
  Pearson. CONJUNCTIVE-ONLY, **permanently lone-merge-banned** (spec 4.2; music-dominated).
- **Task 5 combination** (`verdict.py addon_links`): Rule A (lone flaw, ≥8 events), Rule B
  (`spec_stationarity` AND `env_corr`), Rule C (`emb_score` AND a forensic leg — Tier B/C, abstains
  when `emb_score` absent). Rule A is now the SOLE flaw merge path; `flaw_fingerprint.enabled` only
  gates COMPUTATION. All rules `enabled:false`. `regression.py score --cached` gained a per-signal
  frozen-FN coverage line. Measurement script: `tools/tapematch/calibrate_addon.py` (gap≥0.10 gate
  + zero-FP bar + Rule B conjunction scan; mirrors `calibrate_triplet.py`).

## ADDON Phase 2 live calibration — IN PROGRESS (detached, survives session limits)

**Config right now:** `flaw_fingerprint.enabled`/`spectral_stationarity.enabled`/`envelope_corr.enabled`
= **true** (metric COMPUTATION only). ALL `addon_links.rule_*.enabled` = **false**, `fingerprint.triplet.enabled`
= false. So population is precision-safe — no merge is armed, verdicts unchanged, no guard-masking risk.

**11 calibration dates** (≥100 pairs across frozen TP / same-date-diff-source TN / target-FN), selected
data-driven, logged in `calib_logs/addon_calib_progress.log`. As of ~23:35: **8 done** (1990-06-01,
1996-07-21, 1998-10-28, 1991-02-10, 1993-06-27, 1994-07-04, 1996-11-04, 1990-11-08); **1994-04-28 running**;
**2001-10-30, 1989-06-04 queued**.

**Two detached OS processes (PPID→init; survive Claude session limits — the calibration agent died on
a session limit at ~23:xx, resets 11:30pm America/Chicago):**
1. `calib_logs/run_addon_calib.sh` (pid was 1165487) — population batch, reparented to init, finishing
   the last 3 dates on its own (rc=0 on all 8 so far, ~600–1700s/date).
2. `calib_logs/run_addon_measure.sh` (launched via nohup) — measurement watcher: waits for #1 + any live
   session to clear, re-runs any date that failed to populate (idempotent safety), then runs
   `calibrate_addon.py` + `regression.py score --cached`, appends a `## RESULTS` block, and writes a
   final literal `ADDON_CALIB_DONE` line to `addon_calib_progress.log`.

### PRELIMINARY calibration (8 of 11 dates; the watcher will overwrite with the full 11-date RESULTS)
p10(TP)−p90(TN) gap gate (ship iff ≥0.10) — all three currently **REJECT** on that gate, BUT:
- **`flaw_match_score` (Rule A, lineage-pure) — PROMISING.** TN maxes at **0.133**, TP fans to **0.900**;
  a strict zero-FP bar (~0.14) recovers **16/42 TP with 0 in-sample FP**. This is the spec's designed
  behavior (flaws are inherited & content-blind → same-show negatives don't share them). Unlike the
  triplet (flat collision, gap −0.012), flaw separates cleanly at the top. **Caveat:** in-sample TN=40;
  the real gate is `score --cached` vs all 1390 frozen negatives (absolute fp≤9). Coverage low (~3% of
  target-FN) → modest recall, but precision-safe.
- **`spec_stationarity` / `env_corr` (Rule B, conjunctive):** individual gaps fail; Rule B recovers 0 at
  provisional thresholds because `t_env=0.90` is unreachable (env TP max=0.609). Need Rule-B threshold
  calibration; content-adjacent → collision-prone → must prove 0 FP on the full negative set. Lower priority.

### MORNING RESUME — do this
1. `cat tools/tapematch/calib_logs/addon_calib_progress.log` → look for `ADDON_CALIB_DONE` + the `## RESULTS`
   block (full 11-date calibrate_addon.py + score --cached). If absent, check both procs still alive:
   `pgrep -af 'run_addon_calib|run_addon_measure|tapematch_session'`. If a proc died and dates are unpopulated,
   relaunch: `nohup bash tools/tapematch/calib_logs/run_addon_measure.sh >> tools/tapematch/calib_logs/addon_measure_nohup.out 2>&1 &`
   (it's idempotent + self-guarding — safe to re-run).
2. Read the full-set RESULTS. **Decision — flaw (Rule A):** if `calibrate_addon.py` still shows a clean
   zero-FP bar AND `score --cached` (with Rule A enabled at that bar) keeps absolute `candidate: fp` ≤ 9 →
   ship: set `addon_links.rule_a.t_flaw` to the calibrated bar (NOT the provisional 0.6 if that under-recovers),
   `addon_links.rule_a.enabled: true`, re-run `score --cached` (must stay fp≤9; exit 1 = reject), then the
   control dates. Prove byte-identical elsewhere via `test_verdict_equivalence.py`.
3. **Rule B (stationarity+env):** re-scan `_report_rule_b` at candidate thresholds (t_env must be <0.609,
   e.g. try t_stat 0.7 / t_env 0.35) for a 0-TN conjunction; only ship if the AND-gate admits 0 frozen TN
   at scale via `score --cached`. If none clears, reject (content-adjacent, triplet precedent).
4. Then Tier B (Task 6 `embed_eval.py`) — pretrained fingerprint embedding, eval set excludes
   `label_suspect=1`; gap≥0.10 vs same-show TN required. Then Tier C (Task 7). Then final report vs 41.6%/98.6%.

**HARD REMINDERS:** never run two live sessions at once (shared staging dir `/mnt/DATA0/examples/tapematch`
kills both). Precision is the asset — check ABSOLUTE `candidate: fp` ≤ 9, not just "new FP: none". Never run
`test_batch_queue`-family tests (contaminate observations.db). `.venv/bin/python3` for everything.

## ADDON Phase 2 CALIBRATION COMPLETE (2026-07-03) — Tier A verdict: flaw precision-safe but marginal; left dormant

Full 11-date calibration (`calibrate_addon.py`, 178 flaw / 160 stat+env populated pairs) + score --cached:

| signal | p10(TP)−p90(TN) gap | zero-FP bar | precision-safe recall gain | verdict |
|---|---|---|---|---|
| flaw_match_score | −0.044 (fails) | >0.133 (TN max) | +1 TP @0.45, +2 @0.20 (abs fp=9) | **precision-SAFE, marginal** |
| spec_stationarity | −0.464 (fails) | 0.685 (10 TP) but conjunctive-only | Rule B recovers 0 | REJECT |
| env_corr | −0.377 (fails) | 0.671 (0 TP) | Rule B recovers 0 | REJECT |

- **flaw is the ONE clean Tier A signal**: TN caps at 0.133 while TP fans to 0.900 — no triplet-style
  same-show collision (flaws are inherited & content-blind). BUT the aggressive zero-FP bar 0.143 gave
  **abs fp=10** via TRANSITIVE clustering while the per-run guard reported "new FP: none" — the
  guard-masking trap; absolute fp is the real gate. Precision-safe threshold t_flaw≥0.20 nets only
  +1..+2 TP (coverage ~6% of FN: most FN are too degraded to share ≥8 detectable flaws).
- **Decision: left DORMANT** (`addon_links.rule_a.enabled=false`, computation flags false). +0.1 recall pt
  is not worth a production merge path on a 43-pair TN sample. Re-enable at `t_flaw≥0.45` if the marginal
  precision-safe gain is wanted. Config back at the shipped 41.6%/fp=9 baseline (byte-identical).
- **Rule B (stationarity AND env): rejected** — individual gaps fail hard and the AND-gate recovers 0 TP
  (content-adjacent signals collide on same-show negatives, as the spec warned).

**CONCLUSION: Tier A hand-engineered forensic signals have hit their ceiling — flaw works but its
coverage caps recall at ~+0.1 pt.** This confirms the ADDON premise: the 93%-non-correlating FN bulk needs
LEARNED similarity. NEXT = Tier B (Task 6 `embed_eval.py`, pretrained fingerprint embedding; eval set
excludes `label_suspect=1`; gap≥0.10 vs same-show TN required) → Tier C (Task 7 contrastive) → final report.

## ADDON Tier B (Task 6) — MEASUREMENT HARNESS BUILT + PROVEN, gated on model install (2026-07-03)

Three scripts landed + verified end-to-end with a synthetic backend on the REAL 60/60/60 eval set.
The heavy/outward-facing part (install a ~2 GB model, download weights, run live extraction) is the
ONLY remaining step and is gated on the user's model choice (asked; no answer yet — user away).

- `build_embed_eval_set.py` → `embed_eval_set.json`: 60 TP (frozen pos, corr≥0.05) / 60 same-date
  different-source TN / 60 target-FN (frozen pos corr<0.05, `label_suspect` excluded). Date-clustered
  (67 dates, 184 distinct sources) so each source is embedded ONCE and reused across in-stratum pairs.
- `embed_extract.py` (Task 6.1): pluggable `--backend`. `synthetic` = audio/model-free plumbing
  (PROVEN: 184/184 sources, all 180 pairs scored). `nmfp`/`muq` real paths written but raise
  NotImplementedError until a model env exists. Embeds 1s/0.5s windows over 5×60s excerpts; caches
  per-source npz to `embed_cache/<date>/LB<lb>.npz` (gitignored). Nominal time = seconds-INTO-perf
  (from trim_head, speed-corrected) so both transfers of a show share an origin (fixed an early bug
  where absolute-time excerpt grids of differently-trimmed transfers never overlapped → unscored pairs).
- `embed_eval.py` (Task 6.2): numpy-only gate + report. emb_score = median A-window cosine-max to B
  (±`--tol` aligned neighbourhood, or GLOBAL max when tol≤0). Prints TP/same-show-TN/FN dists +
  p10(TP)−p90(TN) gap; PASS iff gap≥0.10 (triplet baseline −0.012), else structural REJECT. Synthetic
  gap ≈0 (noise floor — different-LB synthetic pairs share no lineage signal; confirms harness unbiased).

### MODEL = nmfp — ENV BUILT (2026-07-03, user confirmed nmfp)
- **Model:** raraz15/neural-music-fp (ISMIR 2025), `nmfp-triplet` checkpoint (ckpt-100) — the
  spec-named degradation-robust neural fingerprint WITH a discriminative head → should separate
  same-show different-source captures (the population that killed triplet/env_corr). Input 8 kHz, 1 s
  segments, 256-mel (essentia), 128-d L2-normalized fingerprints at 0.5 s hop.
- **Isolated env (built):** `tools/tapematch/.venv-nmfp` (py3.11.15 via uv) with
  tensorflow-cpu==2.13.0 / numpy==1.24.3 / essentia==2.1b6.dev1110 / pandas==2.1.4 / h5py / pyyaml /
  soundfile. CPU-only (no CUDA); RTX 3080 unused (inference is CPU-feasible). Repo + checkpoint under
  `tools/tapematch/vendor/neural-music-fp/` (gitignored — 200 MB). Main `.venv` untouched (uv is a
  build tool installed there; not an app runtime dep).
- **Real extractor:** `tools/tapematch/nmfp_embed.py` (self-contained; runs under `.venv-nmfp`).
  Reproduces the authors' essentia mel + FingerPrinter on exactly-8000-sample segments → faithful by
  construction. Writes the SAME `embed_cache/<date>/LB<lb>.npz` that `embed_eval.py` reads. Smoke-tested
  OK (ckpt-100 restored, probe fingerprints L2-norm=1.0). `embed_extract.py --backend nmfp` intentionally
  errors and points here (the real path needs TF, which the py3.13 embed_extract cannot import).
- **Fallback (unused) = muq** (torch foundation, no fingerprint head → weaker probe). Only if nmfp fails.
- On a real result: add the model+checkpoint version note to requirements/PROJECT + justify sr/window
  in the report (spec 6.1.1). NOTE: nmfp deps live ONLY in `.venv-nmfp`, NOT in the pinned requirements.txt.

### RESUME COMMANDS (Tier B)
```
.venv/bin/python3 tools/tapematch/build_embed_eval_set.py          # (re)build eval set (deterministic)
tools/tapematch/.venv-nmfp/bin/python tools/tapematch/nmfp_embed.py   # REAL extraction (→ embed_cache/)
.venv/bin/python3 tools/tapematch/embed_eval.py --tol 2     # aligned neighbourhood
.venv/bin/python3 tools/tapematch/embed_eval.py --tol 0     # global cosine-max (robust)
```

## ADDON Tier B (Task 6) RESULT (2026-07-03) — REJECT on gate, but STRONG separation → Tier C green light
Full report: `tools/tapematch/TIER_B_EMBED_REPORT.md`. Model = neural-music-fp `nmfp-triplet`/ckpt-100
(isolated `.venv-nmfp`, TF2.13/essentia/CPU); real extractor `nmfp_embed.py`; 184/184 sources embedded.

| population | median | p10 | p90 | max | (aligned ±2s) |
|---|---|---|---|---|---|
| TP | **0.912** | 0.401 | 0.993 | 1.000 | frozen pos, corr≥0.05 |
| TN same-show | **0.150** | 0.058 | 0.435 | 0.961 | frozen neg |
| FN target | 0.215 | 0.099 | 0.494 | 0.944 | frozen pos, corr<0.05 |

- **Gap p10(TP)−p90(TN) = −0.034 (aligned) / +0.007 (global) → REJECT** (spec 6.2 needs ≥0.10).
  BUT unlike triplet's collapse (median Δ≈0), nmfp separates HUGELY at the median (TP 0.91 vs TN 0.15,
  Δ≈0.76). The strict gate fails only on TAIL overlap; the p10/p90 gate governs LONE-merge safety and
  nmfp is Rule-C-only anyway. **Learned similarity WORKS** — this is the evidence Tier C is built on.
- **Killer TN tail = LABEL NOISE:** max TN 0.961 (LB4642/LB9900) has waveform corr=0.950 + same family
  (4/4) — a frozen "negative" that IS the same recording. Full-set scan found **3** such waveform-
  contradicted negatives (LB4642/9900, LB6825/9180, LB3431/3455); all flagged `label_suspect=1` in
  observations.db (poison as Tier C hard negatives). Excluding them, genuine same-show collisions cap
  at **0.605**; a Rule-C bar ≈0.65 recovers 8/60 FN with 0 clean-neg FP (precision-safe but marginal,
  and only validated over 59 negs — NOT shipped; would need full-1390-neg emb_score + score --cached).
- **NOT shipped** (`pairs.emb_score`/Rule C not wired) per spec 6.2 "fail the gap → stop Tier B, carry
  the same-show collision measurement into Task 7 as baseline." Baseline for Tier C: same-show median
  ≈0.15–0.34, genuine-collision max ≈0.605, TP median ≈0.91–0.96.

### NEXT = Tier C (Task 7, the >80% path) — RESUME HERE
Contrastive lineage embedding trained from scratch (spec §7). Self-supervised positives (augmented
views: speed±6%, low-pass 1.5–8k, MP3 round-trip, tape hiss/EQ/wow-flutter, gen-stacking); HARD
NEGATIVES = time-aligned windows from same-concert different-source pairs (observations.db same-date
different-family), the triplet-killer weaponized — EXCLUDE `label_suspect=1` (the 3 mislabeled negs +
22 Task-1 FN). Curator labels EVAL-only (frozen set stays valid). Gates 7.3 in order: (1) aug-sanity
self-vs-aug ≥0.8; (2) same-show gap p10(TP)−p90(TN) ≥0.10 on THIS eval set (Tier B baseline −0.034);
(3) frozen regression `emb_score`+Rule C, abs fp≤9; (4) per-category FN-flip table. GPU (RTX 3080)
available — torch installs cleanly on py3.13 (build a `.venv-emb` torch env; don't touch pinned .venv).
Deliverables `tools/tapematch/embedding/` (train + augmentation module w/ unit tests + inference CLI),
`embedding.checkpoint`/`embedding.enabled=false` config, eval report, Rule-C wiring. Then FINAL report
vs 41.6%/98.6%.

## ADDON Tier C (Task 7) — IN PROGRESS (2026-07-03) — package built, cache building, training next
Isolated torch env `tools/tapematch/.venv-emb` (torch 2.6.0+cu124, RTX 3080; py3.13 via uv). Package
`tools/tapematch/embedding/`:
- `config.yaml` — all hyperparams (audio 16 kHz/1 s, mel 64-band, model EMB=128/WIDTH=64, augment probs,
  train batch 256/temp 0.07/hard-neg≥0.25, CHECKPOINT + ENABLED=false).
- `melspec.py` — shared torchaudio log-mel (train+infer parity). DONE.
- `augment.py` (sonnet agent) — AugmentChain: speed±6%, lowpass 1.5-8k, MP3 round-trip (real ffmpeg +
  FFT-xcorr realignment for the ~69 ms LAME delay), tape hiss, level ride, EQ tilt, wow/flutter,
  GEN_STACK 2-3 ops. 21 tests pass. DONE.
- `model.py` (sonnet agent) — ConvEncoder (587,712 params, <10 M) + symmetric NT-Xent. 5 tests. DONE.
- `data.py` — hard-neg mining from observations.db (same-date different-family, EXCL label_suspect + 67
  eval dates), time-aligned window cache on a (date, slot) grid so same-slot windows across sources are
  same-show hard negatives. RESUMABLE shard build (audio_cache/shards/*.npz → windows.npy). DONE.
- `train.py` — GPU NT-Xent loop, cosine LR + warmup, checkpoint → config CHECKPOINT. DONE.
- `infer.py` — CPU/GPU batch inference → embed_cache_tierc/ (Tier-B format) for embed_eval.py. DONE.
Full loop smoke-validated end-to-end (cache→train→infer→gate) on a 2-date cache; batches carry
42/64 same-show hard negatives; mel→encoder→NT-Xent→backward OK; 587K params.

STATE (2026-07-03, PAUSED for user review BEFORE training): training cache BUILT + verified.
`audio_cache/windows.npy` = **61,253** windows (float16, 1s@16k), `index.json`, from **1,278**
sources / **200** dates. **9,600 (date,slot) groups, ALL multi-source** (every group has same-show
hard negatives — the Tier C signal). No NaNs, sane amplitudes. Shards kept under `audio_cache/shards/`
(1.8 GB, enable resume/extension; redundant with windows.npy). Cleaned up: removed the throwaway
20-step smoke checkpoint + smoke embed_cache_tierc + __pycache__.
BUILD NOTE: tool-`run_in_background` shells kept getting SIGKILLed (harness reaps long ones) — use
setsid+nohup+disown for long jobs; the build is resumable so relaunch = resume.

NEXT (resume here — NOT yet started, awaiting go-ahead):
1. Measure steady-state train throughput (`train.py --max-steps 100 --device cuda`, time it) → pick
   epoch count so total ≲ 1-2 h. MP3 P=0.3 + NUM_WORKERS=24 (tiny encoder is CPU-augmentation-bound).
2. Full training: `tools/tapematch/.venv-emb/bin/python tools/tapematch/embedding/train.py --device cuda`
   → checkpoint `tools/tapematch/embedding/ckpt/tierc.pt`.
3. Gate 7.3.1 aug-sanity (self-vs-aug cosine ≥0.8) — quick script w/ model+augment.
4. `infer.py --device cuda` → all 184 eval sources → `embed_cache_tierc/`.
5. DECISIVE gate 7.3.2: `.venv/bin/python3 tools/tapematch/embed_eval.py --cache
   tools/tapematch/embed_cache_tierc --tol 0` (and `--tol 2`) → p10(TP)-p90(TN) vs Tier B −0.034 / 0.10 bar.
6. If ≥0.10: gate 7.3.3 (emb_score + Rule C, full frozen set, abs fp≤9) → Tier C report + FINAL report
   vs 41.6%/98.6%. If <0.10: negative result, report, done.
RESUME CACHE (if ever needed): `setsid nohup tools/tapematch/.venv-emb/bin/python
tools/tapematch/embedding/data.py --max-dates 200 --slots 48 --workers 16 &` (skips existing shards).
On PASS (gap≥0.10): wire `pairs.emb_score` (strictly-additive nullable col + idempotent ALTER) +
verdict Rule C (conjunctive, never lone-merge), then `regression.py score --cached` (abs fp≤9 or reject).
On REJECT: record the gap vs −0.012 in the report, STOP Tier B, carry the same-show collision number
into Task 7 (Tier C) as its baseline.

## ADDON Tier C (Task 7) — TRAINING LAUNCHED (2026-07-03)
Step 1 (throughput): `train.py --max-steps 100 --device cuda` → steady-state (step50→100)
= 50 steps / 29.8 s = **1.678 steps/sec**. Dataset: 239 batches/epoch. Config default
EPOCHS=30 → 7170 steps → **~71 min (1.19 h)**, within the 1-2 h target — no config change
needed. Config verified: MP3 P=0.3, NUM_WORKERS=24 already set as intended. Removed the
100-step debug checkpoint before the real run.

Step 2 (full training) launched detached: `setsid nohup .venv-emb/bin/python
embedding/train.py --device cuda > tools/tapematch/calib_logs/train_full_run.log 2>&1
< /dev/null &` + `disown`. Main PID **3505211** (PPID=1, confirmed reparented to init;
24 DataLoader worker subprocesses spawned as children). Log:
`tools/tapematch/calib_logs/train_full_run.log`. Expected checkpoint:
`tools/tapematch/embedding/ckpt/tierc.pt`.

**Training COMPLETE** (2026-07-03 17:50): 30 epochs, 7170 steps, wall time **69.8 min**
(matches the ~71 min throughput projection). Final loss ~0.029 (last 50-step avg:
step7100=0.0286, step7150=0.0291), LR decayed to ~0 per cosine schedule. No crash/NaN/OOM.
Checkpoint `tools/tapematch/embedding/ckpt/tierc.pt` (2.37 MB).

**Gate 7.3.1 (aug-sanity)** — new script `tools/tapematch/embedding/aug_sanity.py`
(loads checkpoint, samples 200 cached windows, compares each window's clean embedding
vs one `AugmentChain`-augmented view's embedding via cosine sim): **n=200, mean=0.9638,
median=0.9767, min=0.7921, p10=0.9147**. Bar is ≥0.80 mean/median → **PASS**.

**Step 4 (inference)**: `embedding/infer.py --device cuda` over all 184 Task-6 eval
sources → `tools/tapematch/embed_cache_tierc/`: `extracted=184 skip=0 fail=0`, 184 files
across 46 dates confirmed on disk (matches the full eval set, same sources Tier B used).

**Gate 7.3.2 (decisive)** — `embed_eval.py --cache embed_cache_tierc`:

`--tol 0`: TP n=60 (min=0.424 p10=0.475 median=0.520 p90=0.632 max=1.000); TN(same-show)
n=60 (min=0.332 p10=0.377 median=0.441 p90=0.492 max=0.538); FN(target) n=60
(min=0.385 p10=0.404 median=0.481 p90=0.546 max=0.695). max same-show-TN=0.538.
TP recoverable with 0 FP = 22/60 (FN target recovered 9/60).
**gap [p90(TN)=0.492 .. p10(TP)=0.475] = -0.017** (triplet baseline -0.012; Tier B/nmfp
was -0.034 aligned).

`--tol 2`: TP n=60 (min=0.207 p10=0.267 median=0.393 p90=0.671 max=1.000); TN(same-show)
n=60 (min=0.091 p10=0.176 median=0.230 p90=0.341 max=0.459); FN(target) n=60
(min=0.132 p10=0.195 median=0.282 p90=0.413 max=0.646). max same-show-TN=0.459.
TP recoverable with 0 FP = 20/60 (FN target recovered 3/60).
**gap [p90(TN)=0.341 .. p10(TP)=0.267] = -0.074**.

Both gaps are negative and below the ≥0.10 bar (worse than the Tier B/nmfp -0.034
baseline at tol=2). The `embed_eval.py` script's own printed diagnostic says "REJECT"
against its hardcoded 0.10 bar — that is the script's threshold check, not a ship/reject
call made by this run. Per the task's explicit scope, **the pass/reject DECISION is left
PENDING for user review**; gates 7.3.3 (Rule-C wiring, frozen-set regression) and 7.3.4
(FN-flip accounting) were NOT started, and `pairs.emb_score`/Rule C/verdict logic/
regression.py scoring were not touched.

## DECISION (confirmed with user, 2026-07-03 evening): Tier C REJECTED

Per the pre-agreed protocol ("if gap <0.10 → valid negative result, do not threshold-shop,
write the report, stop"), gate 7.3.2's result stands as a clean reject: **no Rule-C wiring,
no `pairs.emb_score` column, no verdict changes, no `regression.py` re-scoring** — the
shipped config is untouched. Notably Tier C (from-scratch, 587K-param encoder, 69.8 min
training, trained specifically on same-show hard negatives) underperformed Tier B's
off-the-shelf pretrained nmfp model even at the median-separation level (TP/TN medians
0.520/0.441, barely separated at all, vs nmfp's 0.912/0.150) — the extra training did not
buy discriminative power on this task.

## CC_TAPEMATCH_ADDON — EFFORT CONCLUDED (2026-07-03)

All three tiers are now closed:
- **Tier 0** (Task 1, FN audit): DONE — re-based recall ceiling to ~80% (36.7% curator label
  noise in the corr<0.05 FN sample); `label_suspect` flag added (25 rows total across the
  whole effort: 22 from the Task-1 FN audit + 3 waveform-contradicted negatives found in Tier B).
- **Tier A** (Tasks 2–5, hand-engineered forensic signals): flaw-match precision-safe but
  marginal (+0.1 recall pt), left dormant; spectral-stationarity/envelope-corr rejected.
- **Tier B** (Task 6, pretrained nmfp embedding): REJECTED on the gap gate (−0.034/+0.007)
  despite strong median separation.
- **Tier C** (Task 7, from-scratch contrastive embedding): REJECTED on the gap gate
  (−0.017/−0.074), performing *worse* than the pretrained model above.

**FINAL STATE: recall 41.6%, precision 98.6%, fp=9** (unchanged from the CC_TAPEMATCH_FIXES
conclusion) — the ceiling for waveform/spectral/speed/lineage-forensic signals and both
attempted learned-similarity approaches on this frozen set. Genuinely reaching further would
need either (a) a proper hyperparameter search on a bigger/longer-trained embedding model
(not attempted — this effort trained one config once), or (b) cleaning the label set before
re-measuring, since a meaningful slice of "truth" here (`lb_says_same`) is itself wrong (see
the calibration audit tool below).

## Calibration audit tool (2026-07-03) — for manually sanity-checking the truth labels

Built `tools/tapematch/dump_calibration_audit.py` (reuses `regression.py`'s exact
`score --cached` internals, so the TP/FN/FP/TN split matches the shipped numbers exactly —
not a reimplementation) + `tools/tapematch/build_calibration_audit_html.py`, producing:
- `tools/tapematch/calibration_audit.json` — all 2965 frozen pairs (3157 unique LB#s) with
  date, both LB numbers, truth (`lb_says_same`), current verdict category,
  `corr`/`fp_score`/`hiss_median`, `label_suspect` flag, and the LB catalog's
  `lb_relation_text` the truth label was derived from.
- `tools/tapematch/calibration_audit.html` — self-contained interactive table
  (search/filter/sort, category chips, suspect-only toggle) built from the JSON above, for
  manually auditing whether individual `lb_says_same` labels hold up against the actual
  curator note text. Published as a Claude Code artifact for browsing. Rerun both scripts
  any time the frozen set or shipped config changes to refresh the audit view.

## RE-OPENED: Tier B full-set re-measurement → Rule D SHIPPED (2026-07-04)

The 2026-07-03 "EFFORT CONCLUDED" stands corrected on one point: the Tier B reject was made
by the lone-merge gap gate; the deferred decisive measurement (full-1390-neg emb_score +
absolute-fp curve through transitive clustering) was run 2026-07-04 and PASSED for the
both-convention variant. Full narrative: `TIER_B_FULLSET_REPORT.md`. Shipped state:
- `addon_links.rule_d` ENABLED (t_emb 0.75, emb_score AND emb_score_global): score --cached
  tp=684 fn=891 fp=9 (recall 43.4%, zero new FP); v2 labels tp=687 fp=6 (43.5%/99.1%).
- `regression_set_v2.json` = v1 with the 3 waveform-contradicted negatives flipped (real
  frozen FP count is 6). v1 stays the continuity gate; v2 is the honesty gate.
- Lone/aligned-only variant REJECTED (abs fp floor 10 incl. a transitive guard-masking FP).
- Standing rule for future signals: `emb_score`/`emb_score_global` must NEVER be added to
  regression.py `_SECONDARY_METRIC_COLS` — metric replay is not authoritative on historical
  dates (force-recompute probe collapsed baseline tp 659→512); Rule D applies additively over
  stored SAME_FAMILY edges there (`_passthrough_with_rule_d`).
- Follow-ups: TODO-200 (live-session emb integration), TODO-201 (curator census review,
  265 flagged labels), TODO-202 (densification probe).

## TODO-202 densification probe → 12× REJECTED, 5× kept (2026-07-05)

Full-population 12×60s re-embed (embed_cache_12x/: 1942 extracted + 523 pilot-cached, ~8.5h;
LB14682 + LB2147 absent from my_collection) + fullset_pairs_12x_scores.json + v1/v2 sweeps.
- Both_tol at margin-respecting thresholds (0.750–0.825): exactly 25 flips = shipped 5×, no
  improvement. Gate (flips > 25 at abs fp ≤9 v1 / ≤6 v2) met ONLY at the 0.725 plateau edge:
  26 flips, one step from the 0.700 cliff (v1 fp 12 / v2 fp 9) — the margin position the 5×
  calibration explicitly refused when choosing 0.75.
- Churn at 0.725: −3 shipped recoveries regress (LB-859/2281 global 0.7096; LB-4428/7275
  aligned 1.000→0.510 — the 5× near-1.0 was itself a sampling artifact; LB-4428/7302
  transitive), +4 gains (LB-576/9116 +2 transitive; LB-4351/6518 at 0.7401). Net +1.
- Verdict: sparse-excerpt TP-tail hypothesis falsified as a broad effect; densification moves
  pairs in both directions. Kept t_emb 0.75 / 5× cache; 12× artifacts retained for TODO-204.
- BUG-237 fixed en route: emb_fullset_eval.py acceptance check was stale post-Rule-D ship
  (false 25-TP MISMATCH); reference now strips rule_d, identity re-proven exactly.

## TODO-201 label flips APPLIED → regression_set_v3.json (2026-07-09)

- tj approved the 83 batch-1+2 FLIPs from FN_LABEL_REVIEW.md (census-flagged frozen-set
  positives whose curator/info text explicitly asserts, pair-scoped, "different recording").
- Applied via make_regression_set_v3.py (parses the ledger's FLIP rows, count pinned to 83;
  v4 for any batch 3). regression_set_v3.json: positives 1578→1495, negatives 1387→1470,
  total 2,965 conserved; flip list embedded as v3_flips. regression_set.json / _v2.json
  untouched per frozen-set rules.
- NOT rescored: honest-recall re-basing against v3 (est. corr<0.05 FN population 830→~747)
  deferred — calibration FROZEN for the 7/09–7/12 window. Note consumers (regression.py,
  calibrate_*.py, audit_fn.py) still read regression_set.json (v1) by default; pointing the
  harness at v3 is part of the future rescore, not this apply step.
- Remaining TODO-201 scope: 136 duration-only pairs (partial/incomplete-set judgment method)
  + 8 UNSURE. TODO-201 stays open.

## EDGE CASE OBSERVED IN THE WILD (2026-07-11) — staircase relaxation × same-show fp floor false-merge

Confirms the risk flagged abstractly in FINDINGS (1990-06-01 note, "LOWERING the
staircase/curator fp bar to 0.40–0.43 can manufacture new false merges") with a concrete
real-world instance from an adhoc run (1997-11-11 Lisle IL, 7 audience sources, run
`20260711_142949`; NOT in the frozen set — no regression-harness signal, logged adhoc only).

- **Symptom:** LB-01126 merged into a same-source family (LB-13287/LB-09042/LB-04854,
  intra-corr 0.91–0.99) despite primary corr 0.003–0.018, windowed_frac 0.0, hiss_frac 0.0,
  hiss_median ~0.006 to every member. Pipeline self-flagged it `chain-unverified`.
- **Sole linking signal = fingerprint at the relaxed bar.** LB-01126's fp Dice is a flat
  **~0.40–0.43 to ALL SIX other sources** (DAT 0.416 · LB-13287 0.409 · LB-04283 0.398 ·
  LB-09042 0.407 · LB-9394 0.432 · LB-04854 0.410) — i.e. the *same-show musical-content
  floor*, source-agnostic, exactly the 0.35–0.47 band the config warns about. It is NOT a
  source-specific match.
- **Why it landed in THIS family and not the others:** the genuine same-source pair
  LB-04854↔LB-09042 has a staircase/splice lag curve (CD-R re-tracking) → those sources carry
  `speed_kind='staircase/splice'`. `verdict.fp_threshold` drops the fp cluster bar 0.50→0.40
  for **any pair touching a staircase-flagged source** (not just the staircase pair itself).
  LB-01126↔LB-04854 fp=0.410 ≥ 0.40 → single-linkage merge. Reproduced: with the flag
  `pair_links→True` (thr 0.40); without it `→False` (thr 0.50). Families 1/3/4 kept the 0.50
  bar (no staircase member), so 01126's identical ~0.41 fp to them did not merge — the
  asymmetry is purely which family happened to contain a staircase pair.
- **Generalised hazard (beyond the 1990-06-01 note):** the staircase relaxation is
  *source-scoped, not pair-scoped* — one staircase pair inside an otherwise-clean family
  lowers the fp bar for that family's edges to **every unrelated source on the date**, so any
  same-show fingerprint floor (~0.40) can cross. Precision cost scales with family size × #
  other sources, and is invisible to the frozen harness whenever the date isn't in the set.
- **No config change made** (calibration FROZEN 7/09–7/12; single adhoc anecdote, not a
  frozen-set FP). Candidate mitigations if this recurs on measured dates: (a) require a
  corroborating non-fingerprint signal (windowed/hiss > floor) before a staircase-relaxed fp
  merge — fingerprint is confirmatory-only per WORKFLOW; (b) gate the 0.40 bar to the
  staircase *pair* rather than either source globally; (c) raise `cluster_threshold_staircase`
  toward the 0.47 same-show ceiling. Left for the post-7/12 rescore.
