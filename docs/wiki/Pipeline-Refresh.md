# Pipeline Refresh

> Sources: `backend/refresh.py` · `backend/refresh_exec.py` · `backend/queues.py` ·
> `tools/refresh_status.py` · `gui_next/src/renderer/src/components/DataFreshnessCard.tsx` ·
> `PROJECT.md` `/api/refresh/*` routes, `refresh.py` module entry, ScreenHome row · `archive/specs/PIPELINE_REFRESH_PHASE{1,2,3,4}.md` ·
> Status: fresh 2026-10-18

Answers *"what in the data pipeline is out of date, and how do I run it?"* — a
different subsystem from [Collection-Pipeline](Collection-Pipeline.md), which is
about filing folders. Surface: the **Updates** card on ScreenHome (was "Data freshness";
redesigned 2026-09-21 into Ready / Long jobs / Needs you buckets from
`refresh_exec.step_bucket`, one whole-pipeline Update button), plus
`tools/refresh_status.py` for the same picture from a terminal. Four phases,
all shipped 2026-08.

## Phase 1 — the planner (read-only)

`refresh.STEPS` is a 28-node registry + DAG. Each step declares a `backlog_sql`
(rows still unprocessed — the direct measure), a `last_run_sql` watermark (a
proxy, only consulted when no backlog signal exists), upstream edges, cost, and
whether it is human-gated. `compute_plan()` reads only existing `computed_at`/
`parsed_at`/`imported_at`-style columns, issues zero writes, and reports each
step as `fresh` / `stale` / `blocked` / `unknown`. **A step with no signal is
`unknown`, never assumed fresh** — that honesty rule runs through all four
phases. Also computes `publish_lag`.

## Phase 2 — steps become buttons

`refresh_step_runs` records real runs (`last_run` = max(watermark, newest successful
run)); `config_version` adds a `version` signal that beats a zero backlog. Four CLI-only
steps (`olof_fetch`, `bobserve_fetch`, `ranker_scan`, `ranker_rerank`) have POST routes
(`/api/olof/fetch`, `/api/bobserve/fetch`, `/api/ranker/{scan,rerank}`) with polling.

## Phase 3 — chained execution

`refresh_exec.EXECUTORS` tiers every step into `inproc` (8), `job` (5) or
`manual` (15, each carrying a one-line reason). `plan_chain()` walks the DAG
from a step or trigger seed, pulling in stale ancestors; `run_chain_claimed()`
runs the plan in topological order under one single-flight claim, with per-step
`sub_progress` and a `refresh_chain_runs` history. The GUI previews the plan
before confirming, and `/start` always re-plans server-side.

## Phase 4 — human queues

`backend/queues.py` is a **separate registry** — never runnable, never in a chain plan.
Six queues, counted from the app DB only (never `tools/tapematch/observations.db`):

| Queue | Kind | Blocks | Screen |
|---|---|---|---|
| `taper_conflicts` | gate | attribute_tapers, compute_show_picks, master_publish | `/library?view=taperReview` |
| `fingerprint_suggestions` | gate | setlist_fingerprint | `/fingerprint` |
| `xref_filesets` | gate | xref_ingest, lb_master_reconcile | none — display-only |
| `tapematch_dates` | backlog | tapematch_sync | `/tapematch` |
| `qc_errors` / `qc_warnings` | gate / backlog | nothing | `/qc-review` |

`gate` queues drain to zero and get a badge, step `attention`, and chain advisories.
`backlog` queues are open-ended: a ratio only, never a badge. Counts are decision
units, not rows.

## Gotchas

- A pending queue **never** changes a step's `state`, and never blocks a chain —
  advisories are text above the Confirm button and nothing else. A test pins
  this: no step's state may differ when queues are unavailable.
- `refresh.py` imports `queues.py` lazily inside `compute_plan()`, guarded (one-way dep).
- `xref_filesets` has no local resolution path (a later flat-file drop resolves it),
  so it gets no nav badge.
- Still open: nothing is incremental (`ranker_scan`'s backlog mode excepted); the 15
  `manual` steps stay unchained.
