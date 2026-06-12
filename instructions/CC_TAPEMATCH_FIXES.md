# CC_TAPEMATCH_FIXES.md — tapematch reliability fixes for recording_families

*Supersedes the priority ordering in `instructions/TAPEMATCH_PLAN.md`. The diagnosis
in that file stands; the implementation sequence and two fix designs are revised here.*

---

## Context for Claude Code

Read first:
```
tools/tapematch/WORKFLOW.md
tools/tapematch/config.yaml
instructions/TAPEMATCH_PLAN.md     # background diagnosis — sequence below overrides it
```

**Purpose shift:** tapematch output is the acoustic-evidence feed for a future
`recording_families` table (same recording, different transfer/remaster/tracking —
distinct from `xref`, which is same files modified/retracked). This changes the
optimization target:

> **False merges are catastrophic; misses are cheap.**
> A false merge propagates transitively through union-find clustering and fuses two
> genuinely distinct recording families. A miss is backfilled later by text mining
> or a re-run. Never trade false-merge risk for recall.

Standing rules (from `.claude/CLAUDE.md`, restated):
- Strictly additive. No destructive operations on `observations.db` or any run dir.
- Dry-run mode on anything that writes.
- All schema changes guarded by version checks.
- Validate every fix against the named regression dates AND the control dates before
  moving to the next task.

---

## Task sequence (do in this order)

| # | Task | Why this order |
|---|------|----------------|
| 1 | gen_analysis.py parser fix + re-baseline | Fixes the measurement instrument before algorithm work |
| 2 | observations.db run versioning + latest-verdict view | Blocks everything downstream; cheap |
| 3 | OOM: dtype/rate audit → downsample-at-ingest | Likely a 5-minute root cause; unblocks N≥5 dates |
| 4 | Speed-offset secondary via **predicted lag** | ~300+ missed pairs (1987–1990 era) |
| 5 | Staircase short-window with **recalibrated thresholds** | ~100+ missed pairs (2001 tour) |
| 6 | Re-run queue generator | Targeted re-runs, not blind 429-date sweep |
| 7 | Error/no-verdict triage | Cleanup |

---

## Task 1 — gen_analysis.py parser fix + re-baseline

**File:** `tools/tapematch/gen_analysis.py`

### Problem
`_same_signal` fires on snippets where "same recording" refers to a *different* group
of LBs, not the subject LB. Example false positive:

> "Alternative recording to LB-0491/LB-0569 which all appear to be same recording"

This inflates MISS counts and corrupts the baseline used to validate Tasks 4–5.

### Implementation
1. In `_build_observations`, after obtaining `snip`:
   - If `_diff_signal(snip)` also matches, do **not** call `_same_signal(snip)`.
   - Emit the neutral `→` (ambiguous) observation branch instead.
2. Add a unit test in `tools/tapematch/tests/` with the exact snippet above plus
   2–3 clean positive and negative snippets pulled from real analysis.md files.

### Re-baseline (required before Task 4)
3. Regenerate all analysis.md: `gen_analysis.py --overwrite` across all run dirs.
4. Recompute and record the corrected miss numbers in a new file
   `tools/tapematch/BASELINE.md`:
   - total LB-confirmed same-source pairs
   - missed (different_family)
   - false merges (same_family where lb_says_same=0... see Task 2 note on this field)
   - corr-bucket distribution of misses (reproduce the table from TAPEMATCH_PLAN.md
     with corrected numbers)
   - per-date worst-miss table

   All later validation compares against BASELINE.md, not TAPEMATCH_PLAN.md.

### Known measurement caveat (document in BASELINE.md, do not "fix")
`lb_says_same` only exists where commentary explicitly names the other LB. True
recall is unknowable from this metric; it is a biased subsample. tapematch links
on pairs with NO commentary cross-reference are potential discoveries, not errors.

---

## Task 2 — observations.db run versioning + latest-verdict view

**File:** new `tools/tapematch/migrate_observations.py` (one-shot, idempotent)

### Problem
After Tasks 4–5, most dates get re-run. `observations.db` will then hold conflicting
verdicts per pair across runs. The future family builder must consume only the
latest verdict per pair.

### Implementation
1. Inspect the current `pairs` schema first (`PRAGMA table_info(pairs)`).
2. If `run_id` / `run_timestamp` columns are absent, add them
   (`ALTER TABLE ... ADD COLUMN`, nullable, no rewrite).
   Backfill from run-dir names where derivable (`YYYYMMDD_HHMMSS_DATE` pattern in
   `tools/tapematch/runs/`); leave NULL where not derivable.
3. Modify the session script's pair-logging code so every new row carries
   `run_id` (the run dir name) and `run_timestamp` (ISO 8601).
4. Create view:
```sql
CREATE VIEW IF NOT EXISTS latest_pairs AS
SELECT p.*
FROM pairs p
JOIN (
    SELECT lb_a, lb_b, MAX(COALESCE(run_timestamp, '')) AS max_ts
    FROM pairs
    GROUP BY lb_a, lb_b
) m ON m.lb_a = p.lb_a AND m.lb_b = p.lb_b
   AND COALESCE(p.run_timestamp, '') = m.max_ts;
```
   Note: pairs with NULL timestamps from un-backfillable legacy rows sort lowest —
   any re-run supersedes them, which is the desired behavior.
5. Normalize pair key ordering: assert/enforce `lb_a < lb_b` on insert so
   (A,B) and (B,A) never coexist. If legacy rows violate this, normalize them in
   the migration (swap columns, keep all other fields).
6. Dry-run mode: print intended changes without writing. Back up `observations.db`
   (file copy with timestamp suffix) before the real migration.

---

## Task 3 — OOM root cause: dtype/rate audit before any refactor

**Files:** `tools/tapematch/tapematch/ingest.py`, `match.py`, possibly `align.py`

### Hypothesis to verify FIRST (5-minute audit)
2 hr stereo @ 96 kHz in float64 ≈ 11 GB per source. Three resident sources ≈ 33 GB
≈ available RAM. Also: `scipy.signal.correlate(method='fft')` promotes inputs to
float64 and allocates several full-length scratch copies.

### Audit steps
1. Trace what `ingest.py` returns per source: sample rate, channels, dtype.
2. Trace where (or whether) downsampling to the comparison representation happens,
   and whether the native-rate array is freed afterward (look for retained
   references — module-level lists, dataclass fields, closure captures).
3. Check dtype at every correlation call site. Log findings in the commit message.

### Fix (expected form — adjust to what the audit finds)
4. Downsample + mono + `float32` **at ingest**; `del` the native-rate array
   immediately and ensure nothing retains a reference.
5. If HF residual comparison genuinely needs higher-rate data, keep only the HF
   band representation, also float32, and only for the two sources in the current
   pair.
6. Add a pre-run estimate log line: `N sources, est. peak RAM ~X GB` computed from
   the actual representation sizes.

### Only if the above is insufficient
7. LRU-2 lazy loading per pair (`max_sources_in_ram = 2` config knob). Do NOT build
   this preemptively.

### Validation
- **1994-02-20** (OOM case study, no run dir exists): run must complete and produce
  a verdict.
- One previously-successful 3-source date must produce identical family assignments
  (float32 must not change verdicts — if it does, stop and report).

---

## Task 4 — Speed-offset secondary: predicted lag, NOT widened search

**Files:** `tools/tapematch/tapematch/match.py` (`secondary_corr_pair`),
`tools/tapematch/tapematch/align.py`, `config.yaml`

### Design decision (overrides TAPEMATCH_PLAN.md option list)
Do NOT widen `local_lag_sec` to 90+. A ±90s search per window is expensive and
raises false-lock risk — a window can find spurious correlation at a wrong lag in
a 180s range, and false locks feed false merges (see context note).

Instead: drift under a constant speed offset is **deterministic**:

```
expected_lag(t) = lag_0 + ppm_ratio * t
```

`estimate_ratio` already produces the ppm. Apply the predicted lag as the per-window
search **center**, keep the residual search window at the existing ±10s (it now only
absorbs ppm-estimate error, not accumulated drift).

### Pre-check (do before implementing)
1. Verify the `estimate_ratio` search grid extends to at least ±19,000 ppm. The
   worst 1989–1990 pairs sit at ±15–19k ppm; if the grid caps lower, those pairs
   get no usable ppm and predicted-lag silently degrades. Widen the grid if needed
   (config knob `align.ratio_grid_max_ppm`, suggested 20000).

### Implementation
2. New config knob: `secondary_match.high_ppm_threshold: 5000` (ppm above which
   predicted-lag mode activates; below it, existing behavior is unchanged).
3. In `secondary_corr_pair`, when `abs(pair_ppm) >= high_ppm_threshold`:
   - Compute `expected_lag(t)` for each window center from `lag_0` (the lag at the
     first aligned anchor) and the ppm ratio.
   - Center each window's local lag search on `expected_lag(t)`; keep search
     half-width at `local_lag_sec` (10s).
4. Critical constraint preserved: **no waveform resampling before
   `secondary_corr_pair`** (WORKFLOW.md prohibition — resampling smears HF
   fine-structure). Predicted-lag centering touches only search offsets, not audio.
5. Fallback (only if predicted-lag underperforms on regression dates): low-band
   (250–2000 Hz) envelope comparison with time-warped *features* — never resample
   waveforms. Treat as a follow-up, not part of this task.

### Validation
| Date | Baseline misses (verify against BASELINE.md) | Target |
|------|----------------------------------------------|--------|
| 1989-06-04 | 8 | ≤2 |
| 1990-01-12 | 9 | ≤3 |

Plus control dates (Task 4 and 5 shared): pick 3 dates from BASELINE.md with
0 misses and 0 false merges. After the fix, their family assignments must be
**unchanged**. Any new same_family link on a control date is a probable false
merge — stop and report before proceeding.

---

## Task 5 — Staircase/staircase: recalibrate thresholds for short windows

**Files:** `tools/tapematch/tapematch/match.py`, `config.yaml`

### Statistical caveat (overrides the plan's bare "use 5s windows")
Correlation variance grows as window length shrinks. `window_corr_threshold: 0.30`
was calibrated for 60s windows and is NOT valid at 5s — applying it unchanged
trades staircase misses for noise-driven false windows (→ false merges).

### Implementation
1. New config knobs:
```yaml
secondary_match:
  staircase_window_sec: 5.0
  staircase_hop_sec: 2.0
  staircase_window_corr_threshold: null   # set after calibration step below
  staircase_coverage_threshold: null      # set after calibration step below
```
2. Activate only when BOTH sides of a pair carry the staircase flag.
3. **Calibration step (required before setting thresholds):** on 2001-10-30, run
   the 5s-window pass on (a) the known same-source pairs and (b) known
   different-source same-show pairs. Record both per-window corr distributions.
   Set `staircase_window_corr_threshold` and `staircase_coverage_threshold` to
   sit in the gap, biased toward the false-positive-safe side (higher). Document
   the observed distributions as a table in a comment block in config.yaml,
   mirroring the existing fingerprint calibration notes in WORKFLOW.md.
4. Alternative if calibration shows no usable gap at 5s: piecewise alignment.
   The staircase lag curve already locates the step edges — align segment-by-
   segment between detected steps with piecewise-constant lag, using the existing
   60s window machinery within each segment. Implement only if 3 fails.

### Validation
| Date | Baseline misses | Target |
|------|-----------------|--------|
| 2001-10-30 | 13 (partially parser noise — use post-Task-1 number) | ≤3 |
| 2001-10-07 | 5 | ≤1 |
| 1996-07-21 | 6 (mixed mode, exercises Task 4 + 5 together) | ≤2 |

Same 3 control dates as Task 4: family assignments unchanged.

---

## Task 6 — Re-run queue generator

**File:** new `tools/tapematch/build_rerun_queue.py`

After Tasks 4–5 validate, generate a targeted re-run list instead of blindly
re-running all 429 dates.

1. Query `latest_pairs` (Task 2 view) for dates with ≥1
   `lb_says_same=1 AND verdict='different_family'` pair, ordered by miss count desc.
2. Exclude dates already re-run after the fix commit timestamp.
3. Output `tools/tapematch/rerun_queue.txt`, one date per line, with miss count as
   a trailing comment.
4. Add `--batch FILE` mode to `tapematch_session.py`: consume the queue file,
   run sequentially, skip lines starting with `#`, append `# done <timestamp>` to
   completed lines so the queue is resumable after interruption.
5. Dates with 0 misses and no errors are NOT re-run.

---

## Task 7 — Error and no-verdict triage

### Error runs (6 dates)
For each of: 1987-10-05, 1989-08-26, 1989-09-01, 1989-09-03, 1993-04-23, 2001-07-07
1. Read `report.md` traceback in the run dir.
2. `flac -t` on every file in the flagged source folder.
3. If FLAC corruption: report the file paths to the user — do NOT attempt repair
   or replacement (collection files are never modified).
4. If the crash is the Task-3 OOM signature, re-run after Task 3 lands.

### No-verdict runs (7 dates)
1978-11-29, 1991-02-13, 1992-11-12, 1994-10-01, 2003-11-25, 2018-08-26, 2026-06-05
1. Read `report.md` + `tapematch.log` per run dir.
2. Expected cause: ≥2 DB entries but only 1 locally analyzable source (private LBs
   excluded by the session script).
3. Fix the session script to emit an explicit `insufficient_sources` status into
   the run report instead of an empty clusters section, so these stop surfacing
   as anomalies.
4. 2026-06-05 is likely a test/calibration artifact — confirm and mark the run dir
   with a `SKIP_REASON` file rather than deleting it.

---

## Forward-looking constraint (informational — no implementation in this spec)

A `recording_families` build will later consume `latest_pairs`. Its edge-acceptance
rules will be:
- union-find edges require primary corr ≥ cluster threshold OR multi-signal
  secondary agreement (windowed AND hiss)
- fingerprint-only links and single-signal secondary links go to a quarantine
  table for human ratification, never directly into clustering

Nothing in Tasks 1–7 should make single-signal links easier to mistake for
multi-signal ones. Where the report/observations rows record which layer produced
a link, keep that attribution intact and machine-readable — it is the input to
the quarantine logic.

---

## Definition of done

- [ ] Parser unit test passes; all analysis.md regenerated; BASELINE.md written
- [ ] observations.db migrated (backed up first); `latest_pairs` view returns one
      row per normalized pair; session script writes run_id/run_timestamp
- [ ] 1994-02-20 completes; one prior 3-source date reproduces identical verdicts
- [ ] 1989-06-04 ≤2 misses; 1990-01-12 ≤3 misses; control dates unchanged
- [ ] 2001-10-30 ≤3; 2001-10-07 ≤1; 1996-07-21 ≤2; control dates unchanged;
      staircase calibration table documented in config.yaml
- [ ] rerun_queue.txt generated; `--batch` mode works and is resumable
- [ ] 6 error dates triaged (corrupt FLACs reported, not touched); session script
      emits `insufficient_sources`; no-verdict dates resolved or marked
- [ ] CHANGELOG.md entries added per task (FEAT/BUG IDs per existing convention)
