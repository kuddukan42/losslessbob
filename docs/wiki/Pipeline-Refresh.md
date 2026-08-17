# Pipeline Refresh

> Sources: `backend/refresh.py` · `backend/refresh_exec.py` · `backend/queues.py` ·
> `tools/refresh_status.py` · `gui_next/src/renderer/src/components/DataFreshnessCard.tsx` ·
> `PROJECT.md` §Backend routes (`/api/refresh/*`), §module reference (~line 123),
> §GUI screens (ScreenHome) · `instructions/PIPELINE_REFRESH_PHASE{1,2,3,4}.md` ·
> Status: seeded 2026-08-16

Answers *"what in the data pipeline is out of date, and how do I run it?"* — a
different subsystem from [Collection-Pipeline](Collection-Pipeline.md), which is
about filing folders. Surface: the **Data freshness** card on ScreenHome, plus
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

`refresh_step_runs` records real runs (so `last_run` is
`max(watermark, newest successful run)`), `config_version` adds a `version`
signal that beats a zero backlog, and four CLI-only steps (`olof_fetch`,
`bobserve_fetch`, `ranker_scan`, `ranker_rerank`) gained POST routes and a Run
button with progress polling.

## Phase 3 — chained execution

`refresh_exec.EXECUTORS` tiers every step into `inproc` (7), `job` (5) or
`manual` (15, each carrying a one-line reason). `plan_chain()` walks the DAG
from a step or trigger seed, pulling in stale ancestors; `run_chain_claimed()`
runs the plan in topological order under one single-flight claim, with per-step
`sub_progress` and a `refresh_chain_runs` history. The GUI previews the plan
before confirming, and `/start` always re-plans server-side.

## Phase 4 — human queues

`backend/queues.py` is a **separate registry** — a queue is not runnable and
never enters a chain plan. Four queues, counted from the app DB only (never
`tools/tapematch/observations.db`, which nightly analysis holds locked):

| Queue | Kind | Blocks | Screen |
|---|---|---|---|
| `taper_conflicts` | gate | attribute_tapers, compute_show_picks, master_publish | `/library?view=taperReview` |
| `fingerprint_suggestions` | gate | setlist_fingerprint | `/fingerprint` |
| `xref_filesets` | gate | xref_ingest, lb_master_reconcile | none — display-only |
| `tapematch_dates` | backlog | tapematch_sync | `/tapematch` |

`gate` queues drain to zero and get a badge, step `attention`, and chain
advisories. `backlog` queues are open-ended and get a ratio only — never a
badge, because one that never reaches zero teaches the user to ignore all of
them. Counts are decision units, not rows (691 suggestion rows = 242 LBs).

## Gotchas

- A pending queue **never** changes a step's `state`, and never blocks a chain —
  advisories are text above the Confirm button and nothing else. A test pins
  this: no step's state may differ when queues are unavailable.
- `refresh.py` imports `queues.py` lazily inside `compute_plan()`, guarded — the
  dependency runs one way only, same rule Phase 3 kept for `refresh_exec`.
- `xref_filesets` is a count with no local resolution path: `checksums` is
  Jeff's table, so a staged fileset is resolved by a later flat-file drop, not
  an Approve button. It is excluded from every nav badge for that reason.
- Nothing here is scheduled — every run is still started by a human.
- Still open after Phase 4: **nothing is incremental** (every wholesale step
  reprocesses the whole corpus; `ranker_scan`'s backlog mode is the lone
  counter-example), and the 15 `manual` steps stay unchained.
