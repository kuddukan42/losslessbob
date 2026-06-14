# tapematch BASELINE — corrected reference (post Task 1)

*Generated 2026-06-12, supersedes the accuracy tables in `instructions/TAPEMATCH_PLAN.md`
per `instructions/CC_TAPEMATCH_FIXES.md` Task 1. All later validation (Tasks 4-7)
compares against this file.*

Source: `tools/tapematch/observations.db` (`pairs` table), 4318 rows, 423 distinct
concert dates, `run_at` range 2026-06-02 .. 2026-06-07. Task 1 (gen_analysis.py
parser fix) does **not** write to `observations.db` — these DB-level totals are
unchanged from `TAPEMATCH_PLAN.md` and are reproduced here verbatim as the frozen
baseline. The change from Task 1 is to the per-run `analysis.md` MISS/FALSE MERGE
annotations (see "Effect of the Task 1 parser fix" below).

---

## 1. Topline accuracy (DB-level, unchanged)

| Metric | Count | Rate |
|--------|-------|------|
| LB-confirmed same-source pairs (`lb_says_same=1`) | 769 | — |
| Missed by tapematch (`different_family`) | 500 | **65.0%** |
| False merges (`same_family`, `lb_says_same=0`) | 8 | ~1% |

## 2. Corr-bucket distribution of the 500 missed pairs

| Primary corr bucket | Missed pairs | % |
|---------------------|-------------:|------:|
| 0.00–0.05 | 469 | 93.8% |
| 0.05–0.10 | 15 | 3.0% |
| 0.10–0.20 | 8 | 1.6% |
| 0.20–0.35 | 6 | 1.2% |
| 0.35+ | 2 | 0.4% |

**Conclusion unchanged from TAPEMATCH_PLAN.md:** threshold tuning on primary
correlation cannot fix this — 93.8% of misses sit at near-zero primary corr and
require the secondary (windowed/hiss) layer to work (Tasks 4-5).

## 3. Per-date worst-miss table (top 10, DB-level)

| Date | Missed pairs | Known cause |
|------|-------------:|-------------|
| 2001-10-30 | 13 | staircase on both sides |
| 1990-01-12 | 9 | ±15k ppm speed offsets |
| 1989-06-04 | 8 | ±15k ppm speed offsets |
| 1993-06-27 | 7 | speed offsets |
| 1996-07-21 | 6 | staircase (mixed) |
| 1989-05-27 | 6 | speed offsets |
| 1989-10-31 | 6 | speed offsets |
| 2001-10-07 | 5 | staircase on both sides |
| 1989-06-07 | 5 | speed offsets |
| 1989-08-22 | 5 | speed offsets |

These are the **Task 4/5 validation baselines**: 1989-06-04=8, 1990-01-12=9,
2001-10-30=13, 2001-10-07=5, 1996-07-21=6, matching the figures already quoted
in `CC_TAPEMATCH_FIXES.md`'s validation tables.

## 4. False merges (8 raw rows)

| Date | LB pair | corr | Run |
|------|---------|-----:|-----|
| 1988-08-26 | 9900/4642 | 0.950 | 20260604_030919 |
| 1988-09-23 | 3164/267 | 0.005 | 20260604_042142 |
| 1990-06-01 | 12884/12552 | 0.002 | 20260604_222923 |
| 1990-06-01 | 12884/4200 | 0.003 | 20260604_222923 |
| 1990-06-01 | 12552/4200 | 0.002 | 20260604_222923 |
| 1993-02-17 | 7034/8677 | 0.020 | 20260606_234324 |
| 1996-07-21 | 513/4861 | 0.0015 | 20260602_182427 |
| 1996-07-21 | 513/4861 | 0.0016 | 20260603_083106 |

---

## Effect of the Task 1 parser fix

All 429 `analysis.md` files regenerated (`gen_analysis.py --overwrite --all`, 0 errors).

Post-fix totals across all regenerated `analysis.md`:
- `MISS` observations: **131**
- `possible FALSE MERGE` observations: **4**

The fix (`_build_observations`: skip `_same_signal(snip)` when `_diff_signal(snip)`
also matches) directly affects the 3 snippets matching the
"alternative recording to X/Y ... which all appear to be same recording" pattern
(2001-10-30, two run dirs, and 1993-06-27 — 9 cross-reference observations total).
All 9 are now emitted as neutral `→` observations instead of false `MISS`.

**2001-10-30 concrete result:** the latest run dir
(`20260603_085731_2001-10-30`) analysis.md MISS count went from **5** (pre-fix,
all parser noise from this pattern) to **0** (post-fix). This confirms
TAPEMATCH_PLAN.md's suspicion that the "5 missed" figure for this date was
"partially or entirely parser noise" — it was entirely parser noise. The DB-level
**13 missed pairs** for 2001-10-30 (table 3 above) is the real Task 5 target;
the analysis.md cross-reference count is a separate, much narrower metric (see
caveat below) and is not a substitute for it.

---

## Known measurement caveat — `lb_says_same` (do not "fix")

`lb_says_same` (and the DB-level totals in sections 1-4) is populated by
`tapematch_session.py`'s `extract_lb_relationship()`, a **separate** parser from
`gen_analysis.py`'s `_same_signal`/`_diff_signal` (which Task 1 fixed). It only
fires where LB commentary **explicitly names the other LB** in the pair. True
recall is unknowable from this metric — it is a biased subsample. tapematch links
on pairs with **no commentary cross-reference are potential discoveries, not
errors**, and should not be treated as false positives.

---

## Live example of the Task 2 problem (conflicting verdicts across runs)

While computing this baseline, a concrete instance of the problem Task 2 must
solve was found in **1996-07-21** (6 runs in `observations.db`, 2026-06-02 to
2026-06-03):

- Pairs (6985,4861) and (6986,513) are `lb_says_same=1` (commentary confirms
  same-source) and were correctly `different_family` in early runs, but flip to
  `same_family` in later runs.
- Pair (513,4861) is `lb_says_same=0` (commentary says **different** recording,
  near-zero corr ~0.0015-0.0016) but is also `same_family` in 2 of the later runs
  — a textbook **transitive false merge**: once both (6985,4861) and (6986,513)
  are unioned into one family, (513,4861) inherits `same_family` despite its own
  corr being ~0.0015.
- The **latest** run (`20260603_083106`) is the worst of the six: 0 DB-level
  misses but 1 false merge (the transitive one above).

**Implication for Tasks 4-7:** "latest run per pair" is not automatically a clean
baseline — some existing runs already reflect experimental/regressed states. When
Task 2's `latest_pairs` view is built, 1996-07-21 and 2001-10-07 (whose later runs
also show 0 DB-misses, vs. the 5-6 baseline in table 3) should be **re-run fresh**
with the current `config.yaml` before being used as Task 4/5 control or validation
dates, rather than trusting the existing `observations.db` rows for those two
dates.

---

## Task 4 results — predicted-lag mode (2026-06-13)

**Implementation:** `align.local_lag_centered` + `secondary_match.high_ppm_threshold`
(config.yaml) + `match.secondary_corr_pair(..., predicted_lag=...)`, wired from
per-pair `pair_ratios`/`anchors[0]` in `cli.py`. Unit-tested
(`tests/test_predicted_lag.py`, 3/3 pass): correctly recovers a lag beyond
`±local_lag_sec` when centered on the true predicted value, and leaves
zero-centered search unchanged below `high_ppm_threshold`.

**Validation — target dates:**

| Date | Baseline misses | After Task 4 | Target | Predicted-lag activations |
|------|-----------------|--------------|--------|----------------------------|
| 1989-06-04 | 8 | 8 | ≤2 | 11/14 cross-pairs |
| 1990-01-12 | 9 | 9 | ≤3 | 54/65 cross-pairs |

**Validation — control dates:** 1987-09-28, 1987-10-07, 1988-07-28 (high-ppm,
predicted-lag activates on both pairs and correctly stays `different_family`).
All family assignments **unchanged** from baseline on all 3 — zero regressions.

**Outcome:** the mechanism activates exactly as specified (`PREDICTED_LAG` log
lines show plausible `lag_0`/`ppm` per pair) and is regression-free, but does
**not** reduce misses on either target date. For every missed pair on both dates,
`windowed_median` (0.0017-0.011) and `hiss_median` (0.0046-0.0095) sit ~100x below
their thresholds (0.30 / 0.20) **at every lag tried**, including the predicted one
— fingerprint scores 0.36-0.50 are consistent with "different source, same show".
Task 4's premise (accumulated drift pushes the true lag outside `±local_lag_sec`)
does not explain these misses: there is no lag at which HF-residual or hiss
correlation rises above noise. The spec's own fallback (low-band 250-2000 Hz
envelope comparison with time-warped *features*, Task 4 step 5) is the relevant
path for these pairs and is tracked as a follow-up (TODO-140), not part of Task 4.

**Decision:** keep the predicted-lag code — it is correct, tested, and will help
any pair where the miss *is* a search-range problem (none of the two validation
dates happen to be such a case, but the mechanism is now available for Task 5/6
re-runs across the other ~300 high-ppm-era pairs). Proceeding to Task 5.

---

## Task 5 results — staircase short-window recalibration (2026-06-13)

**Implementation:**
- `align.union_staircase_sources(*speed_infos)` — a source counts as "staircase"
  if classified `"staircase/splice"` in *either* lag-curve pass (vs the initial
  `ref_name`, or vs the re-selected central ref). Fixes a reference-ambiguity
  bug: `speed_info[ref_name]["kind"]` is always `"reference"` under a single
  pass, so a pair involving the current reference source could never be flagged
  staircase on that source from that pass alone. Unit-tested
  (`tests/test_staircase_union.py`, 3/3 pass).
- `cli.py` now computes the central-ref lag-curve pass (`speed_info_central`)
  *before* the secondary-match loop (previously computed after), so
  `staircase_sources = union_staircase_sources(speed_info, speed_info_central)`
  can drive the existing 15s short-window OR-fallback. Output section order is
  unchanged (the central-ref pass is still printed in its original later
  position).
- `match.secondary_corr_pair(..., return_raw=True)` — optional, adds
  `win_corrs`/`hiss_corrs` (raw per-window correlations) to the returned dict,
  used by the calibration tool below.
- New `calibrate_staircase.py` — one-off tool computing the per-window
  `residual_corr` distribution at a short window size for known
  same-source / different-source-same-show staircase pairs.
- New `config.yaml` knobs `staircase_window_sec`/`staircase_hop_sec` (5.0/2.0)
  and `staircase_window_corr_threshold`/`staircase_coverage_threshold` (both
  `null`) — added per spec step 2 but **left disabled** (see calibration result
  below). No code path in `cli.py` reads these four knobs; they exist only as
  documented config for a mechanism that calibration showed has no usable
  signal.

**Calibration (step 3) — 2001-10-30, `staircase_window_sec=5.0`,
`staircase_hop_sec=2.0`, `local_lag_sec=10.0`:**

| Pair | n_windows | p25 | p50 (median) | p75 | p95 | frac≥0.10 | frac≥0.15 | frac≥0.20 |
|------|----------:|----:|-------------:|----:|----:|----------:|----------:|----------:|
| Same-source (LB-07888/LB-08413, both staircase) | 3815 | 0.0077 | **0.0118** | 0.0171 | 0.0296 | 0.000 | 0.000 | 0.000 |
| Different-source, same show (LB-08413/LB-13258, both staircase) | 3958 | 0.0101 | **0.0153** | 0.0219 | 0.0373 | 0.002 | 0.001 | 0.000 |

**No usable gap exists at 5s windows** — the different-source pair's median
(0.0153) is *higher* than the same-source pair's median (0.0118); the
distributions fully overlap. No fixed `residual_corr` threshold at this window
size can separate same-source from different-source-same-show for staircase
pairs. This mirrors Task 4's finding for 1989-06-04/1990-01-12: these
CDR-sourced, HF-capped recordings carry essentially no discriminating
HF-residual signal, regardless of window size.

**Decision (per spec step 3's own branch: "if no gap, the new 5s pass is not
implemented; consider piecewise alignment"):** the new 5s pass is **not wired
into `cli.py`** — `staircase_window_corr_threshold`/`staircase_coverage_threshold`
remain `null`/disabled. The reference-ambiguity union-flag fix is kept (it is a
correctness fix to the *existing* 15s fallback, independent of the calibration
outcome). Piecewise alignment (spec step 4) is deferred — tracked as TODO-144.

**Validation — control dates** (1987-09-28, 1987-10-07, 1988-07-28): CLUSTERS /
LINEAGE / DIAGNOSTICS sections byte-identical to the pre-fix re-runs — zero
regressions.

**Validation — target date (2001-10-30):** re-ran with the union-flag fix
applied. CLUSTERS / LINEAGE / DIAGNOSTICS output is **byte-identical** to the
pre-fix fresh re-run (`20260613_130913_2001-10-30`) — same 5 families, same
INCOMPLETE/DISTINCT SOURCE diagnostics. DB-level miss count unchanged: **6/6
`lb_says_same=1` pairs remain `different_family`**, with identical `corr` values
in both runs:

| LB pair | corr |
|---------|-----:|
| 491/10594  | 0.0018 |
| 569/10594  | 0.0032 |
| 4885/10594 | 0.0036 |
| 7888/8413  | 0.0045 |
| 7888/10594 | 0.0028 |
| 8413/10594 | 0.0345 |

**Outcome:** the union-flag fix is correct and regression-free, but produces
**zero observable change** for 2001-10-30 — every cross-family pair already had
at least one side flagged staircase under the single-pass `speed_info` (the
only pair the fix newly flags is (LB-10594, LB-08413), via LB-08413's
central-ref-pass classification), and the 15s fallback already has no usable
signal for any of these pairs (consistent with the 5s calibration above — more
signal does not appear at 15s either, per the prior session's "no signal at 60s
or 15s for all 21 cross-pairs" finding). Target (≤3 misses) **not met** — same
result as Task 4, the limiting factor is signal content, not the alignment/
search mechanism. Proceeding to Task 6 (re-run queue generator).

---

## Task 7 results — error & no-verdict triage (2026-06-13)

**Implementation:**
- `tapematch/ingest.list_tracks` now requires `p.is_file()` in addition to
  suffix matching — fixes BUG-180 (a *directory* named
  `1987-10-05locarno+asm.flac` was matched as a track, crashing
  `audio.duration_sec()` with `LibsndfileError`).
- `tapematch_session.find_lb_folders` now drops collection folders with no
  audio files (via the existing `_has_audio()` helper), printing
  `Excluded (no audio found): LB-XXXXX` — fixes BUG-181 (a no-audio folder
  included as a source made `ingest.concat_source` raise
  `ValueError("no audio in ...")` for the *whole date*).
- `tapematch_session.resolve_from_collection` now catches `OSError` from
  `p.is_dir()` and treats an unreachable collection path as "missing" — fixes
  BUG-182 (found during validation: `/mnt/DYLAN2` was intermittently offline
  and crashed the session with `OSError: [Errno 5] Input/output error` before
  reaching any exclusion logic).
- `tapematch_session.run_date` now writes an explicit `insufficient_sources`
  report + archives the run when fewer than 2 sources remain after exclusion,
  instead of returning early with nothing written.
- `gen_analysis.py` (`parse_report`/`build_analysis`/`main`) recognizes the
  `**insufficient_sources**` marker and renders a clean "insufficient sources"
  status section instead of `ERROR`.
- 3 new test files (`test_ingest_list_tracks.py`,
  `test_find_lb_folders_no_audio.py`, `test_insufficient_sources.py`,
  6 new tests). Full suite: **33/33 pass**.

**Validation — error dates (6):**

| Date | Pre-fix error | Result after fix |
|------|---------------|-------------------|
| 1987-10-05 | `LibsndfileError: Format not recognised` (directory-as-track, BUG-180) | Full run completes: 5/7 sources, **2 families**, 10 pairs logged (`20260613_201610_1987-10-05`) |
| 1989-08-26 | `ValueError: no audio in ... LB-01430` (BUG-181) | Full run completes: 2/5 sources (LB-01430 excluded, LB-13291/LB-16623 not found), **2 families**, 1 pair logged (`20260613_202211_1989-08-26`) |
| 1989-09-01 | `ValueError: no audio in ... LB-01588` (BUG-181) | LB-01588 excluded; only LB-08627 (1/3) remains → **`insufficient_sources`** report written + archived (`20260613_200759_1989-09-01`), no crash |
| 1989-09-03 | `ValueError: no audio in ... LB-02245` (BUG-181) | Full run completes: 8/11 sources (LB-02245 excluded; LB-13296/LB-16624 not found — DYLAN2 offline), **8 distinct families**, 28 pairs logged (`20260613_214035_1989-09-03`) |
| 1993-04-23 | `ValueError: array is too big` (`soundfile.info()` returns `frames=INT64_MAX` sentinel for a truncated file) | **Genuinely corrupted source file** — not a code bug. Reported to user, not modified (see below). |
| 2001-07-07 | `LibsndfileError: Format not recognised` (0-byte file) | **Genuinely corrupted (empty) source file** — not a code bug. Reported to user, not modified (see below). |

Note: `1989-09-01`'s re-run hit `/mnt/DYLAN2` while it was offline (LB-13295's
`my_collection` path) — BUG-182's fix correctly treated it as "missing"
without crashing; the run still completed and produced the expected
`insufficient_sources` report. `1989-08-26`/`1989-09-03` each have one
private/no-torrent entry on `/mnt/DYLAN2` (LB-13291, LB-13296) that were
likewise correctly resolved as "not found" with DYLAN2 offline.

**Corrupted source files (reported to user per spec — collection files are
never modified):**
- `/mnt/DYLAN1/Concerts/1993/1993-04-23 New Orleans, Louisiana, New Orleans
  Jazz Heritage Festival, WWL-Ray-Ban Stage, The Fairgrounds Racetrack
  (LB-04994)/d1/bd1993-04-23d1t01.flac` — 4186 bytes (truncated; `ffprobe`
  duration `N/A`, `soundfile.info()` returns the `frames=INT64_MAX` sentinel)
- `/mnt/DYLAN1/Concerts/2001/2001-07-07 Schwabisch, Germany
  (LB-14942)/d1/bd2001-07-07.d1t01.flac` — 0 bytes

`flac -t` was unavailable in this environment (`flac: command not found`);
`ffprobe`/`soundfile.info()` output (file size + duration sentinel values) is
equally conclusive evidence of corruption for both files.

**Validation — no-verdict dates (7):**

`1978-11-29`, `1991-02-13`, `1992-11-12`, `1994-10-01`, `2003-11-25`,
`2018-08-26` — re-examined and found **NOT currently anomalous**: each
already has a valid `## Verdict:` section in its latest run dir (regenerated
2026-06-02, predating this session). The original "empty cluster output"
hypothesis from the pre-Task-1 plan does not hold for any of these as the run
dirs now stand — no fix needed.

`2026-06-05` — confirmed **test/calibration artifact**: both run dirs
(`20260605_214549_2026-06-05`, `20260605_215513_2026-06-05`) actually analyze
2000-03-14 Visalia, California sources (LB-04117, LB-06898, + a manual no-LB
"Dolphinsmile Archive" folder) under a fake "2026-06-05" date label. Marked
both with a `SKIP_REASON` file (not deleted) per spec.

**Outcome:** all 6 error dates triaged — 2 root-cause code bugs (BUG-180,
BUG-181) fixed and validated with real full re-runs producing correct
clusters/families; 1 incidental crash (BUG-182, `/mnt/DYLAN2` OSError) found
during validation and fixed; 2 dates are genuinely corrupted source files,
reported not touched. The session script now emits `insufficient_sources`
instead of crashing or silently skipping `<2`-source dates. All 7 no-verdict
dates resolved (6 already valid, 1 marked as calibration artifact via
`SKIP_REASON`). This completes the TODO-139 / CC_TAPEMATCH_FIXES.md task
sequence (Tasks 2-7); see TODO.md for the final summary and follow-ups
(TODO-140, TODO-144).
