# TapeMatch

> Sources: `tools/tapematch/CLAUDE.md` · `tools/tapematch/WORKFLOW.md` ·
> `tools/tapematch/CALIBRATION_PROGRESS.md` · `PROJECT.md` §recording_families ·
> Status: seeded 2026-07-06

Audio-matching pipeline that clusters LB entries into **recording families**
(same source tape → one family). Lives in `tools/tapematch/`; results sync into
the app DB (`recording_families`, `tapematch_family_meta` — MASTER tables).

## Layout & data

- Code: `tools/tapematch/tapematch/` (`align.py`, `match.py`, `trim.py`, `cli.py`)
  + `tapematch_session.py`, `config.yaml`.
- Run artifacts: `data/tapematch/runs/` (moved there 2026-06-04).
- `observations.db` and `last_run_report.md` at `tools/tapematch/` root.
- Calibration state: `tools/tapematch/CALIBRATION_PROGRESS.md` — the single source
  of truth for threshold/parameter history. Current: staircase 0.40 shipped,
  t_emb 0.75 / 5× cache kept.

## Workflow rules

- **Never run live tapematch sessions concurrently.**
- Batch analysis: `/tapematch-batch` writes missing `analysis.md` files for
  **complete sets only** (DB entries == files found on disk), batch size 5, then
  syncs families to the app DB. `/analyze-runs` is the read-only rollup.
- Open threads: TODO-204 (emb-gated MrMsDTW confirmation probe), TODO-203
  (Tier C retrain with family-aware hard negatives), TODO-201 (curator review of
  census-flagged frozen-set labels).
