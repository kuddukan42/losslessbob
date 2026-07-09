# tapematch — Next Steps Plan

*Generated: 2026-06-07 from full analysis of 429 dates / 455 run directories*

---

## Where We Are

### Run coverage
- **429 concert dates** have been run (latest run per date)
- **319 `analysis.md` files** generated this session (117 pre-existed)
- **6 error runs** — tapematch did not complete (broken FLAC or other crash)
- **7 no-verdict runs** — analysis.md has no usable verdict (likely empty cluster output)

### Accuracy from observations DB

| Metric | Count | Rate |
|--------|-------|------|
| LB-confirmed same-source pairs tracked | 769 | — |
| Missed by tapematch (different_family) | 500 | **65%** |
| False merges (same_family, LB says different) | 8 | ~1% |

**The 12% "miss rate" reported per date was misleading.** The DB-level rate is 65%,
driven by dates with many missed pairs each. The per-date MISS counts in analysis.md
are also slightly over-inflated by a parser false alarm (see §3.1).

### Corr distribution of missed pairs

| Primary corr bucket | Missed pairs |
|---------------------|-------------|
| 0.00–0.05 | 469 (93.8%) |
| 0.05–0.10 | 15 (3.0%) |
| 0.10–0.20 | 8 (1.6%) |
| 0.20–0.35 | 6 (1.2%) |
| 0.35+ | 2 (0.4%) |

**Conclusion: threshold tuning cannot fix this.** 93.8% of missed pairs have primary
corr near zero. These require the secondary (windowed/hiss) layer to work. It is not.

### Worst dates by miss count

| Date | Missed pairs | Known cause |
|------|-------------|-------------|
| 2001-10-30 | 13 | staircase on both sides |
| 1990-01-12 | 9 | ±15k ppm speed offsets |
| 1989-06-04 | 8 | ±15k ppm speed offsets |
| 1993-06-27 | 7 | speed offsets |
| 1996-07-21 | 6 | staircase (known from WORKFLOW.md) |
| 1989-10-31 | 6 | speed offsets |
| 1989-05-27 | 6 | speed offsets |
| 2001-10-07 | 5 | staircase on both sides |
| 1990-01-31 | 5 | speed offsets |
| 1990-01-14 | 5 | speed offsets |

---

## Root Causes (in order of impact)

### 1 — PAL/NTSC speed shift kills secondary for 1987–1990 era

Nearly all 1987–1990 recordings sit at ±8000–19000 ppm relative to each other.
The secondary `local_lag_sec` is ±10s per window. But accumulated drift at ±15000 ppm
over a 90-min show = **81 seconds**. The local lag search fails completely before
reaching the midpoint of the show.

The WORKFLOW.md critical note says "do NOT resample before secondary_corr_pair"
because resampling smears HF. But for ±15k ppm pairs the local lag approach
simply cannot track the drift at all — no resampling = no match.

**Fix direction:** For pairs where `estimate_ratio` already found a speed offset
≥ some threshold (e.g. 8000 ppm), do a pre-resampled secondary pass using
a lower-resolution 250 Hz band instead of HF residuals. The lower band is less
sensitive to smear. Or: widen `local_lag_sec` to 90+ for high-ppm pairs only.

### 2 — Staircase/staircase pairs not recovered by short-window fallback

2001 tour: many pairs have staircase on both sides. The `short_window_sec = 15s`
fallback exists but 13 pairs were missed on 2001-10-30 alone. The failure mode
is likely that 15s windows still have enough internal lag drift to suppress
per-window corr below `window_corr_threshold = 0.30`.

**Fix direction:** For staircase/staircase pairs, try `short_window_sec = 5s`
with tighter `short_hop_sec = 2s`. The lag can only drift ~0.07s in 5s at
14000 ppm — well within alignment. The cost is more windows but corr is reliable.

### 3 — gen_analysis.py MISS parser false alarm

The commentary parser fires `_same_signal` on snippets like:
> "Alternative recording to LB-0491/LB-0569 which all appear to be **same recording**"

The phrase "same recording" is referring to a different group, not the subject LB.
This causes false MISS labels. The 2001-10-30 result showing 5 missed pairs
in the analysis.md verdict may be partially or entirely parser noise (the DB
shows 13 actual misses from that date, but those include cross-family observations
that gen_analysis couldn't detect because it only sees pairs where one LB's
commentary explicitly names the other).

**Fix direction:** In `_same_signal` / `_get_snippet`, check that the subject LB
is not the object of a `_diff_signal` clause in the same sentence. A simple
heuristic: if the snippet also matches `_diff_signal`, treat as "ambiguous"
and emit a neutral `→` observation, not a MISS.

---

## Immediate Triage

### Error runs — fix FLAC and re-run

| Date | Run dir | Action |
|------|---------|--------|
| 1987-10-05 | `20260604_135334_1987-10-05` | Check FLAC integrity; re-run after fix |
| 1989-08-26 | `20260603_174944_1989-08-26` | Check FLAC integrity; re-run after fix |
| 1989-09-01 | `20260603_175017_1989-09-01` | Check FLAC integrity; re-run after fix |
| 1989-09-03 | `20260603_175022_1989-09-03` | Check FLAC integrity; re-run after fix |
| 1993-04-23 | `20260607_090855_1993-04-23` | Check FLAC integrity; re-run after fix |
| 2001-07-07 | `20260603_063606_2001-07-07` | Check FLAC integrity; re-run after fix |

Each error run has `report.md` with the raw traceback. Check with
`flac -t` on the flagged folder before re-running.

### No-verdict runs — investigate cluster output

| Date | Likely cause |
|------|-------------|
| 1978-11-29 | Empty clusters section (≤1 recording on disk?) |
| 1991-02-13 | Same |
| 1992-11-12 | Same |
| 1994-10-01 | Same |
| 2003-11-25 | Same |
| 2018-08-26 | Same |
| 2026-06-05 | Likely a test/calibration run, not a real concert date |

For each: read the `report.md` and `tapematch.log` in its run dir to confirm.
If only 1 recording on disk, no clustering is possible — these dates can be
skipped or marked "insufficient coverage."

### 4 — Memory exhaustion with N ≥ 5 sources per date

When a date has 5 or more sources, tapematch crashes or is killed by the OOM
killer before completing. The failure mode is silent — the run dir exists but
`report.md` / `analysis.md` may be absent or truncated.

**Root cause (likely):** Feature arrays (downsampled waveforms, FFT bins, or
cross-correlation scratch buffers) for all sources are allocated simultaneously.
The number of pairs is O(N²/2) and each pair's comparison may keep both sources
in memory concurrently.

**Important:** The machine has ~32 GB free RAM. The previous estimates of
~2 GB peak at N=5 are far too low to explain OOM crashes — the process must be
consuming significantly more than that. Prior estimates (200 MB/source at 96 kHz
stereo float32) were underestimates; scratch buffers for cross-correlation,
FFT intermediates, or retained intermediate arrays likely multiply the footprint
by 10–50×. Do not assume the fix is "lazy loading two sources at a time" — with
32 GB free, even 10 full sources shouldn't crash. The real leak is likely an
intermediate array that is never freed, a correlation scratch buffer sized to the
full track length squared, or an explicit memory cap/limit being hit rather than
physical RAM exhaustion. Instrument with `tracemalloc` or `memory_profiler`
before assuming the fix direction.

**Known affected pattern:** Dates with multiple circulating bootlegs from the
same era (e.g. multi-source 2001 tour nights, heavily-traded 1990 tapes) easily
reach 6–8 sources on disk.

**Case study — 1994-02-20:** This date OOM-crashed and has no run directory.
Use it as the primary validation target for the lazy-load fix (Priority 3):
confirm it was OOM-killed, count sources on disk, then verify the fix allows
it to complete.

**Fix directions (in order of complexity):**

1. **Pair-at-a-time loading (simplest):** Load each source's audio lazily — only
   when it appears in the current pair — then release it immediately after.
   Requires changing the pipeline from "load all → compare all" to iterating
   pairs one at a time. Cost: some re-reads from disk if a source appears in
   many pairs; mitigated by LRU cache keyed on source path with size=2.

2. **Memory-mapped source arrays:** Use `numpy.memmap` for downsampled waveform
   arrays instead of in-memory `ndarray`. OS pages out unused regions. Works
   well for sequential access patterns (cross-correlation, short-window sweep).
   Requires writing intermediate arrays to a temp dir per run.

3. **Pair batching with configurable concurrency:** Add a `max_sources_in_ram`
   config knob (default 3). When N exceeds it, process pairs in batches where
   each batch holds at most `max_sources_in_ram` sources simultaneously.

4. **Downsample representation earlier:** If the comparison representation is
   already at 500 Hz mono, memory footprint is ~3.6 MB / hr. At 96 kHz stereo
   it is ~2.8 GB / hr. Confirm which representation is kept in RAM during
   pair-wise comparison and push the downsample step earlier in the pipeline.

**Recommended path:** Start with option 1 (lazy load + LRU-2 cache). If that
is insufficient for very large dates, add option 3 as a config gate.

---

## Algorithm Fix Priorities

### Priority 1 — Speed-offset secondary (impact: ~300+ missed pairs)

**Files:** `tools/tapematch/tapematch/match.py` (secondary_corr_pair),
`tools/tapematch/config.yaml`

Steps:
1. Add a `high_ppm_threshold` config knob (suggested: 8000 ppm).
2. In `secondary_corr_pair`, detect if the pair's estimated ppm exceeds threshold.
3. For high-ppm pairs: widen `local_lag_sec` proportionally, or add a dedicated
   low-band (250–2000 Hz) resampled pass as fallback.
4. Validate on 1989-06-04 (8 missed) and 1990-01-12 (9 missed).

### Priority 2 — Staircase/staircase short-window fix (impact: ~100+ missed pairs)

**Files:** `tools/tapematch/tapematch/match.py`, `tools/tapematch/config.yaml`

Steps:
1. Add `short_window_sec_staircase = 5.0` and `short_hop_sec_staircase = 2.0`
   config knobs.
2. When both sides of a pair are flagged staircase, use these narrower windows.
3. Validate on 2001-10-30 (13 missed) and 2001-10-07 (5 missed).

### Priority 3 — Memory: lazy source loading for N ≥ 5 dates (impact: unblocks multi-source dates)

**Files:** `tools/tapematch/tapematch/match.py` (or wherever sources are bulk-loaded),
`tools/tapematch/config.yaml`

Steps:
1. Audit where source audio arrays are allocated — find the "load all sources"
   loop and the lifetime of those arrays through the pair-comparison stage.
2. Refactor to a lazy-load pattern: open/close each source's audio per pair,
   keeping at most 2 sources in RAM at once (LRU-2 keyed on source path).
3. Add `max_sources_in_ram = 2` to `config.yaml` as a tunable.
4. Add a pre-run memory estimate log line: `N sources, ~X GB peak RAM`.
5. Validate on **1994-02-20** (OOM case study — no run dir exists). Confirm
   run completes and produces a verdict.

If lazy-load alone is insufficient (very long recordings), add numpy.memmap
for downsampled waveform scratch arrays as a follow-up.

### Priority 4 — gen_analysis.py parser fix (correctness, not algorithm)

**File:** `tools/tapematch/gen_analysis.py`

Steps:
1. In `_build_observations`, after getting `snip`, check: if `_diff_signal(snip)`,
   do NOT call `_same_signal(snip)` — treat as ambiguous.
2. Emit the neutral `→` branch for ambiguous snippets.
3. Regenerate all analysis.md with `--overwrite` after fix.

Note: this was previously "Priority 3" before the memory fix was inserted above it.

---

## Regression Test Targets

Use these dates to validate each fix before moving on:

| Date | Missed pairs | What to fix | Expected after fix |
|------|-------------|-------------|-------------------|
| 1989-06-04 | 8 | Speed-offset secondary | ≤2 missed |
| 1990-01-12 | 9 | Speed-offset secondary | ≤3 missed |
| 2001-10-30 | 13 | Staircase short-window | ≤3 missed |
| 2001-10-07 | 5 | Staircase short-window | ≤1 missed |
| 1996-07-21 | 6 | Both (mixed) | ≤2 missed |

For each regression test: run `tapematch_session.py YYYY-MM-DD`, compare
`last_run_report.md` family assignments against LB commentary.

---

## Dates Not Yet Run

The 429 dates above cover **all runs that exist** in `data/tapematch/runs/`.
To continue expanding coverage, use:

```bash
.venv/bin/python3 tools/tapematch/tapematch_session.py --suggest
```

This shows dates with 3–5 collected entries not yet analysed. The algorithm
fixes above should be done before running many new dates — otherwise the
observations DB accumulates misses that will need re-runs.

---

## Session Workflow Going Forward

1. **Fix gen_analysis.py parser** (30 min) → regenerate all analysis.md.
2. **Fix Priority 1** (speed-offset secondary) → validate on 1989-06-04, 1990-01-12.
3. **Fix Priority 2** (staircase short-window) → validate on 2001-10-30, 2001-10-07.
4. **Fix Priority 3** (lazy source loading) → identify an OOM-crashed N≥5 date,
   audit the load-all loop, refactor to LRU-2 lazy load, validate run completes.
5. **Triage errors** (check FLACs, re-run the 6 broken dates).
6. **Investigate no-verdict dates** (read logs, mark insufficient coverage if needed).
7. **Expand to new dates** using `--suggest` once miss rate improves.
   Priority 3 should be done before expanding to new multi-source dates — many
   high-source dates are currently silently skipped or OOM-killed mid-run.

Each fix iteration: follow the WORKFLOW.md loop (edit config/code → re-run date →
compare against LB commentary → commit).

---

## Files to Read at Session Start

```
tools/tapematch/WORKFLOW.md          # always
tools/tapematch/config.yaml          # current knob values
tools/tapematch/last_run_report.md   # last run's output
instructions/TAPEMATCH_PLAN.md       # this file
```
