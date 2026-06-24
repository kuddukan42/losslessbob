# Concert Ranker v1 — Build Report

**Date:** 2026-06-23
**TODO:** TODO-183
**Spec:** `instructions/CC_CONCERT_RANKER.md`
**Status:** Backend + CLI complete and verified end-to-end. Calibration against the
real corpus + GUI surface remain (need the actual audio drives / curated data).

---

## What arrived vs. what I built

The v1 package delivered the **scoring brain** pre-built and synthetic-tested —
do not rebuild these:

```
config.py        # all thresholds/weights/bands (# CALIBRATE markers), externalized
scoring.py       # banding, hard disqualifiers, MAD-z sibling normalization, fusion, explain
features.py      # clarity / crowd / tonal / distortion / spatial / hf_native extractors
calibrate.py     # score_separation / fit_thresholds / validate_labels harness
audio/cache.py   # TrackCache + NativeProbe — the one-decode/one-STFT shared cache
```

I built the "real machine" parts: DB integration, source/commentary mining, real
audio decode, the scan loop, ranking, calibration orchestration, and the CLI.

---

## Placement decision

Moved `instructions/concert_ranker/` → **repo-root `concert_ranker/`** (sibling of
`backend/`). Rationale: the package writes into `losslessbob.db` and imports
`backend.db`, so it is tightly coupled to the backend (unlike the self-contained
`tools/tapematch/`). Repo-root placement makes both `import concert_ranker.*` and
`import backend.db` resolve with no `sys.path` hacks. Run as:

```
.venv/bin/python3 -m concert_ranker.cli <scan|calibrate|rerank|report> …
```

---

## Files added

| File | Task | Purpose |
|------|------|---------|
| `lb/repo.py` | 1 | USER-table persistence. Standalone WAL connections, one-transaction-per-recording, scan create, raw-metric + score upsert, restart-skip (`done_lbs`), rerank reads (`load_metrics`). `_jsonable()` coerces numpy `float32`/NaN → JSON-safe. |
| `lb/source_type.py` | 2 | SBD/AUD/FM/UNKNOWN derivation, reusing `backend.db.classify_source_type`. Matrix/ALD → UNKNOWN (don't contaminate a pure source-class curve). |
| `lb/commentary.py` | 3 | Word-boundary mines `entries.description` into `calibrate.LABEL_KEYWORDS` — the validation oracle. |
| `audio/io.py` | 4 | ffmpeg decode: one bulk pass at 22.05 kHz → `build_track_cache`; 8×20 s windows at 44.1 kHz → `build_native_probe`. Mirrors `tools/tapematch/tapematch/audio.py`. |
| `scan.py` | 5 | Per-folder decode→extract→median-aggregate → one RAW metric dict. |
| `runner.py` | 5 | Direct process-pool driver (`scan_folders`) + producer/consumer staging loop (`run_staged`). Crash=scrap, skip done LBs on restart. |
| `families.py` | 7 | Rank within `recording_families` (MAD-z normalize → fuse → `rank_in_family`); standalone fallback (absolute bands only). Sibling-relative completeness injected at rank time. |
| `calibration.py` | 6 | Stratified rating×source_class sample → scan → `score_separation`/`fit_thresholds`/`validate_labels`. Returns a **report**; does NOT auto-rewrite `config.py`. |
| `cli.py` | — | `scan` / `calibrate` / `rerank` / `report` subcommands. |
| `tests/test_concert_ranker.py` (in repo `tests/`) | — | 11 tests, no audio decode needed. |

## Files changed

- `backend/db.py` — 3 USER tables (`quality_scans`, `quality_recording_metrics`,
  `quality_recording_scores`) added to `SCHEMA_SQL` + `USER_TABLES`; created by
  `init_db()`. (+51 lines, confined to these tables.)
- `CHANGELOG.md`, `PROJECT.md` (schema + file structure + change-log row),
  `TODO.md` (TODO-183).

---

## Architectural decisions honored

1. **One decode + one STFT per track** — every feature rides `TrackCache`; `audio/io.py` decodes once for the bulk cache, samples cheap native windows separately.
2. **Two-rate** — bulk metrics at 22.05 kHz, HF metrics from the 8×20 s `NativeProbe` at 44.1 kHz (not a second full decode).
3. **Scan once, store RAW** — `quality_recording_metrics.metric_json` holds raw aggregated values; `rerank` re-bands/ranks from them with zero rescans.
4. **Two-stage scoring** — hard disqualifiers veto/demote before fusion (`families.rank_group`).
5. **Within-source-class calibration** — sample stratified by rating × source_class; `fit_thresholds` per class.
6. **Crash = scrap** — consumer computes the whole folder in memory, commits ONE transaction; job status is just pending→done; restart skips done LBs.
7. **Families optional** — ungrouped recordings score standalone; family grouping is never a hard dependency.

---

## Verification

- `py_compile` clean across the package and `backend/db.py`.
- Synthetic `test_pipeline.py` still passes (`python -m concert_ranker.test_pipeline`).
- `tests/test_concert_ranker.py` — **11 passed** (repo roundtrip/idempotency/sanitize,
  source-class, commentary, family ranking, standalone, rerank-from-stored-metrics).
- **End-to-end on real generated FLACs**: `scan --all` → ranking (a 2-member family
  ranked #1/#2, a singleton scored standalone with absolute bands only) → `rerank`
  (rewrote scores from stored metrics, no audio) → `report` in text/json/csv.
- Bug found & fixed during e2e: `intrusion_rate`/`handling_rate` leaked numpy
  `float32` (from float32 frame times) → JSON serialization failure. Fixed by
  sanitizing in `repo.build_metric_json` (also maps NaN → null).

### Note on the pre-existing test failure
`tests/test_db_writes.py::TestFolderLink::test_replace_existing` fails, but it is
**pre-existing** — `backend/db.py` was already modified at session start, and the
failure is in `folder_lb_link` replace logic (the composite-PK migration made
folder links multi-LB), unrelated to the quality tables.

---

## Remaining work (needs the real machine / curated data)

- Run `concert_ranker calibrate` against the real corpus and **review** the fitted
  thresholds — calibration returns a report and intentionally does not mutate
  `config.py`.
- Validate the lossy-brickwall (25 dB) + `crowd_snr` (3.0 dB) disqualifiers against
  real known-lossy / buried-in-crowd files (synthetic test under-fired lossy).
- True 5–9 kHz sibilance from the `NativeProbe` (currently HF-capped at BULK_SR;
  omitted from the v1 scan — scoring tolerates its absence).
- Polish band-label phrasing for fluent verdict sentences.
- GUI surface for quality scores/verdicts (backend + CLI only so far).

---

## Next steps (as of 2026-06-24)

State: 6 calibration rounds done; metrics de-confounded (harsh/hiss/hum/dropout);
bands fitted per-decade + per-class (hybrid, crowd held absolute); absolute quality
score live (config.QUALITY_MODEL, held-out CV Spearman 0.65 vs LB rating, 94% within
one letter tier). Scans on record: 3/4/5 (117 each), 6 (697 decade), 7 (256 middle,
C-rich). Branch `concert-ranker`: package + dropout + ratings + abs-score commits.

Open items, roughly in priority order:

1. **Mono/stereo flag (ready — no rescan).** `stereo_width` already separates it:
   width < ~0.05 (and `lr_corr` ≈ 1.0) = mono/dual-mono (~133 of 873), width ≥ 0.05
   = stereo (740). Surface as a derived `channels`/`is_stereo` field in the metrics
   and/or report. Cheap, deterministic from stored data.
2. **SBD quality-score model.** QUALITY_MODEL is AUD-fit, applied to all classes —
   SBD/FM grades are approximate. Fit + validate a separate SBD model.
3. **Re-scan scan 6 with the current dropout detector** for a fully clean combined
   training set (dropout isn't a score predictor, so it doesn't change grades — just
   tidies the data), then refit QUALITY_MODEL + per-decade bands off the unified set.
4. **dropout disqualifier threshold** is provisional (150) — refit from a current scan.
5. **lossy_flag** never fires — needs labeled known-lossy files to tune the brick-wall.
6. **True 5-9 kHz sibilance + dynamic_range_dr** (not yet produced by the scan).
7. **Per-decade SBD bands** and **per-decade disqualifiers** (currently global).
8. **GUI surface** for grades/verdicts (backend + CLI only so far).

---

## CLI quick reference

```
concert_ranker scan      --all | --lb N... | --family FAM_ID   [--workers 16] [--staging-dir DIR]
concert_ranker calibrate [--by-decade] [--ratings C+ C C-] [--per-cell N] [--classes AUD SBD] [--staging-dir DIR]
concert_ranker rerank    --scan-id N          # re-band/rank/grade from stored metrics, no audio
concert_ranker report    --scan-id N [--lb N... | --family INT] [--format text|json|csv]
```
