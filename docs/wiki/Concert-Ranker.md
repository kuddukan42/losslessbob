# Concert Ranker

> Sources: `concert_ranker/` (incl. `LB_KNOWLEDGE.md`) · `PROJECT.md`
> §quality_scans tables (~line 415) · branch `concert-ranker` commits ·
> Status: seeded 2026-07-06

Ranks recordings of the same concert by audio quality, so the user can pick the
best circulating source per show. Active development branch: `concert-ranker`.

## Data model (USER tables)

- `quality_scans` — scan run records.
- `quality_recording_metrics` — per-recording measured audio metrics.
- `quality_recording_scores` — derived quality scores used for ranking.
- Related: `entry_lineage` (per-LB parsed lineage signals), `curated_lists`
  (curator "best of" picks, TODO-181).

## UI

Pipeline visualization in gui_next: `components/pipeline/PipelineIcon.tsx`,
`PipelineParts.tsx` (recent work: pipeline UI improvements + i18n, commit d0744c66).

## Notes

- Domain knowledge collected in `concert_ranker/LB_KNOWLEDGE.md`.
- Interacts with TapeMatch families: ranking compares recordings *within* a
  performance/family grouping (Library performance/show grouping API).
- Future direction: `instructions/FABLE_UNIFIED_RANKING.md` spec (read
  `SPEC_INTEGRATION_NOTES.md` first).
