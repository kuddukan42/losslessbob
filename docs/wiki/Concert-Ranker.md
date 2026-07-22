# Concert Ranker

> Sources: `concert_ranker/` (incl. `LB_KNOWLEDGE.md`) · `PROJECT.md`
> §quality tables (~line 684), §show_picks (~line 762), §Derived-Data Recompute
> (~line 1321) · Status: fresh 2026-07-22

Ranks recordings of the same concert by audio quality so the user can pick the
best circulating source per show. Merged into `main` (the old `concert-ranker`
branch is gone). Package: `concert_ranker/` — `scan.py`, `features.py`,
`scoring.py`, `quality_score.py`, `families.py`, `picks.py`, `calibrate.py`,
`cli.py`; domain knowledge in `LB_KNOWLEDGE.md`.

## Data model (USER tables)

- `quality_scans` — scan run records (config snapshot for reproducibility).
- `quality_recording_metrics` — RAW aggregated per-recording metrics, stored
  **separately** from scores: the "scan once, store RAW metrics" guarantee —
  `concert_ranker rerank` re-bands/re-ranks without any audio rescan.
- `quality_recording_scores` — fused `final_score`, `rank_in_family`
  (1 = best transfer of the show), `vetoed` hard-disqualifications, and a
  human-readable `verdict_text`. Rewritten wholesale on every rerank.
- Grouping compares recordings *within* a TapeMatch family
  ([TapeMatch](TapeMatch.md)) — `family_id` maps to `recording_families`.

## Show picks (unified ranking)

`show_picks` — per-date "best of" ranking recomputed wholesale by
`tools/compute_show_picks.py` (scoring in `concert_ranker/picks.py`) from
`entries.rating`, `curated_lists`, `entry_lineage`, `quality_recording_scores`,
and `taper_attributions`. `pick_rank = 1` = recommended for the date; every
score carries ordered `evidence_json`. Model: `instructions/FABLE_UNIFIED_RANKING.md`
§3/§4. Runs as step 3 of the `/api/derived/recompute` SSE chain
(lineage → tapers → picks → song index).

## Surfaces

- Library DetailPanel ([GUI](GUI.md)): **Quality tab** (LB Rating vs AI Quality
  Index side by side), **Picks tab** (rank/score + `EvidenceList`), `absGrade`
  and ★ recommended badges in the recording lens.
- [Show-Dossier](Show-Dossier.md): pick ranking + quality verdicts +
  rank-1 `recommendation` section.
- Aux tooling: `tools/fit_aud_quality_model.py`, `tools/adhoc_quality/`.
