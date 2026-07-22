# TapeMatch

> Sources: `tools/tapematch/CLAUDE.md` · `tools/tapematch/WORKFLOW.md` ·
> `tools/tapematch/CALIBRATION_PROGRESS.md` · `PROJECT.md` §recording_families,
> §tapematch_pairs · Status: fresh 2026-07-22

Audio-matching pipeline that clusters LB entries into **recording families**
(same source tape → one family). Lives in `tools/tapematch/`; results sync into
the app DB (`recording_families`, `tapematch_family_meta` — MASTER tables;
`tapematch_pairs` per-date pairwise similarity — USER).

## Layout & data

- Code: `tools/tapematch/tapematch/` (`align.py`, `match.py`, `trim.py`, `cli.py`)
  + `tapematch_session.py`, `config.yaml`.
- Run artifacts: `data/tapematch/runs/` (moved there 2026-06-04).
- `observations.db` and `last_run_report.md` at `tools/tapematch/` root.
- Calibration state: `tools/tapematch/CALIBRATION_PROGRESS.md` — the single
  source of truth for threshold/parameter history.

## Calibration status (2026-07-21)

- Staircase 0.40 shipped; t_emb 0.75 / 5× cache kept.
- **Frozen-set gating** (TODO-255, closed 07-21): blocks staircase relaxed-bar
  merges corroborated only by noise-level hiss — strict precision gain, zero
  recall cost. Tests: `tests/test_staircase_gating.py`.
- **Corpus rescore complete** (07-20): 561/561 drained, TODO-254/235 closed;
  gate validated with no fp-only leaks.
- Full-library crawl in progress since 07-20 (detached, ~3–4 day ETA).

## Workflow rules

- **Never run live tapematch sessions concurrently** — single-instance; no live
  session/batch while the library crawl runs.
- Batch analysis: `/tapematch-batch` writes missing `analysis.md` files for
  **complete sets only** (DB entries == files found on disk), batch size 5, then
  syncs families to the app DB. `/analyze-runs` is the read-only rollup.
- Subdirectory rules auto-load from `tools/tapematch/CLAUDE.md` when working there.

## Open threads

TODO-234 (family over-merge review — series-vs-series taper conflicts, 14
remaining after rescore refresh; picks await tj) · TODO-204 (emb-gated MrMsDTW
confirmation probe) · TODO-201 (curator review of census-flagged frozen-set
labels, 265 pairs).
