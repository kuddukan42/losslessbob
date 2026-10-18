# TapeMatch

> Sources: `tools/tapematch/CLAUDE.md` · `tools/tapematch/WORKFLOW.md` ·
> `tools/tapematch/CALIBRATION_PROGRESS.md` · `tools/tapematch/config.yaml` ·
> `backend/tapematch_sync.py` · `backend/tapematch_autoflag.py` ·
> `PROJECT.md` §recording_families, §tapematch_pairs · Status: fresh 2026-10-18

Audio-matching pipeline that clusters LB entries into **recording families**
(same source tape -> one family). Lives in `tools/tapematch/`; results sync into
the app DB (`recording_families`, `tapematch_family_meta` -- MASTER tables;
`tapematch_pairs` per-date pairwise similarity -- USER) via `backend/tapematch_sync.py`
(`POST /api/tapematch/sync`).

## Layout & data

- Code: `tools/tapematch/tapematch/` (`align.py`, `match.py`, `trim.py`, `verdict.py`,
  `calibration.py`, `asr.py`, `ingest.py`, `audio.py`, `cli.py`) +
  `tapematch_session.py`, `config.yaml`.
- Run artifacts: `data/tapematch/runs/`. `observations.db` and `last_run_report.md`
  at `tools/tapematch/` root. The embed cache, run logs and junk were **untracked**
  (git history purged) in TODO-358/359 -- they are local-only.
- Calibration state: `CALIBRATION_PROGRESS.md` (threshold/parameter history, newest
  entries at the bottom) -- read first, update after any calibration work.

## Calibration status (2026-09-30)

- Staircase 0.40, t_emb 0.75 / 5x embedding cache; 12x rejected. Frozen-set
  gating (TODO-255) keeps hiss-only staircase merges out
  (`tools/tapematch/tests/test_staircase_gating.py`).
- **`match.fingerprint_primary_floor: 0.05` ENABLED** (TODO-325, 09-30): a
  fingerprint/secondary link also needs primary correlation >= 0.05. Closed
  BUG-331; frozen set -41 tp / -4 fp vs a 0.10 floor (0.05 chosen).
- **Calibration identity per run** (TODO-333): `tapematch/calibration.py` hashes the
  config; `calibration_eras.py` reports stale dates. `replay_writeback.py` re-decides
  threshold-only stale dates **without audio** as replay runs
  (`runs.replayed_from`, id `<run>-r<hash>`), gated by a fidelity check; the next
  `tapematch_sync` picks them up. Dates needing real re-runs go through the queue.
- **Banter/ASR transcript matching** (`asr.py`, `pairs.banter_score`) is built but
  **dark** (config `asr:`; uncalibrated, no rule reads it).
- Link-mechanism false-merge census (TODO-336); [DISTINCT SOURCE] verdicts on
  untrusted speed ratios are classified/re-checked (BUG-330, TODO-324).

## Auto-triage & review flags

`backend/tapematch_autoflag.py` derives a machine `clear`/`attention` verdict per date
from `observations.db` (~0.19 precision, but ~97% of no-fire dates were human-clean):
it means "analyse first", never "broken", and stays out of `review_flag` (human prose).
At sync, a multi-member family whose members state 2+ mic brands or 2+ confirmed tapers
gets `attention` + `R8_stated_rig` (TODO-356; helpers in `backend/dossier_fields.py`;
QC rule R-F2). Nothing is split -- flagged for review only.

## Workflow rules

- **Never run live tapematch sessions concurrently** -- shared caches and DB.
- Library crawl (`crawl_start.sh`/`crawl_stop.sh`/`crawl_status.sh`) finished
  2026-07-26. A crontab (not /loop) runs `/tapematch-batch` nightly 11pm-7am CT.
- Before `/tapematch-batch`: `triage_analysis.py --apply` auto-writes trivially clean
  `analysis.md`. Batch = **complete sets only** (DB entries == files on disk), size 5,
  then syncs families. `/analyze-runs` is the read-only rollup.
- API: `/api/tapematch/{sync,families,pairs,sources,runs,dates,analysis,report,
  pairs/judgment,dates/accept,crawl/*}` in `backend/app.py`.

## Open threads

TODO-333 (re-decide remaining stale dates), TODO-336 (false-merge queue), TODO-324
(distinct-source re-check queue), TODO-234 (series-vs-series taper over-merge review),
TODO-204 (emb-gated MrMsDTW probe), TODO-201 (frozen-set label review).
