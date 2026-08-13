# Pipeline Refresh — Phase 1 spec: the freshness planner

> Companion to `PIPELINE_REFRESH_INVENTORY.md` (the 57-step inventory and the
> D1–D8 disjoints). Phase 1 of 4. Written 2026-08-12.
>
> **Phase 1 is read-only.** It adds no schema, writes no rows, and changes no
> existing code path. It answers one question — *"what is not up to date, and how
> do I run it?"* — and nothing else. Execution arrives in Phases 2–3.

---

## 1. The finding that makes this cheap

The inventory's D1 said there is no staleness ledger. That is true of *meta* —
but a live query of `data/losslessbob.db` shows the underlying signal **already
exists in the tables themselves**. Most derived tables carry a `computed_at`,
`parsed_at`, `imported_at`, `fetched_at`, or `geocoded_at` stamp that is written
today and read by nothing:

| Step | Existing signal | Live value (2026-08-12) |
|---|---|---|
| flat-file apply | `MAX(flat_file_releases.applied_at)` | 2026-08-02 |
| db import | `meta.last_import_date` | 2026-08-02 |
| scrape entries | `MAX(entries.scraped_at)` | 2026-08-03 |
| lb_master reconcile | `MAX(lb_master.last_status_at)` | 2026-08-11 |
| olof fetch | `MAX(olof_pages.fetched_at)` | 2026-07-14 |
| olof parse | `MAX(olof_pages.parsed_at)` | 2026-07-14 |
| parse_lineage | `MAX(entry_lineage.parsed_at)` | 2026-07-18 |
| attribute_tapers | `MAX(taper_attributions.computed_at)` | 2026-07-20 |
| compute_show_picks | `MAX(show_picks.computed_at)` | 2026-07-18 |
| song_index | `MAX(song_performances.computed_at)` | 2026-07-18 |
| ranker scan | `MAX(quality_scans.started_at)` | 2026-06-30 |
| tapematch family sync | `MAX(recording_families.imported_at)` | 2026-08-12 |
| tapematch pair sync | `MAX(tapematch_pairs.imported_at)` | 2026-08-12 |
| geocode | `MAX(location_geocoded.geocoded_at)` | 2026-07-22 |
| setlist fingerprint | `MAX(setlist_fingerprint_suggestions.computed_at)` | 2026-07-13 |
| pipeline state | `MAX(pipeline_folder_state.updated_at)` | 2026-08-12 |
| **master publish** | `meta.master_published_at` | **2026-07-14** |

So Phase 1 is not "build a ledger" — it is **"read the ledger that already
exists."** No `refresh_step_runs` table is needed yet. Steps that genuinely have
no signal (see §4) report `unknown` rather than blocking the build.

`master_published_at` in particular means D7 (invisible publish lag) is
measurable today with zero new schema.

### 1a. Three signal types — a date is NOT the right parameter for all steps

The timestamps in §1 are the *most available* signal, not the *best* one. The
registry must therefore be signal-agnostic: each step declares one or more
signals, and its state is the most severe result among them.

| Signal | Measures | Right for | Weakness |
|---|---|---|---|
| **`backlog`** — a count of unprocessed rows | outstanding work, **directly** | incremental steps: scrape, geocode, ranker `scan`, pipeline, xref | only where "unprocessed" is expressible in SQL |
| **`watermark`** — `MAX(ts)` vs upstream `MAX(ts)` | when it last ran, **by proxy** | wholesale steps: lineage, tapers, picks, song_index | false positives; format/clock fragility (§1b) |
| **`version`** — hash/stamp of a config input | config or code changed | steps whose inputs are not rows | no stamp exists today (§1c) |

**Rule: prefer `backlog` wherever it is computable; fall back to `watermark`; add
`version` where a config input exists.** Backlog wins on every axis — it is a
measure rather than a proxy, it is immune to §1b entirely, and it yields the
affected-row set that Phase 2 needs to make expensive steps incremental
(inventory §5 requirement 4). A step may declare both: `stale` if either fires.

Why a pure date model is not good enough:

- **Incremental steps go green while work is outstanding.** `MAX(geocoded_at)`
  says "something was geocoded recently", never "everything is geocoded".
- **False positives cause alert fatigue.** Re-scraping a single entry bumps
  `MAX(entries.scraped_at)` and marks four downstream wholesale steps stale even
  when nothing material changed. A card that cries wolf gets ignored, which
  defeats the purpose of building it.
- **Deletions move no timestamp at all.** Removing rows upstream leaves every
  `MAX()` untouched.

### 1b. Timestamp formats are not consistent — normalize before comparing

Verified against the live DB (2026-08-12), counting rows per format:

| Column | `T`-separated | space-separated | tz-aware |
|---|---|---|---|
| `olof_pages.fetched_at` / `.parsed_at` | **861** | 0 | 0 |
| `entries.scraped_at` | 0 | 16,703 | 0 |
| `entry_lineage.parsed_at` | 0 | 16,569 | 0 |
| `taper_attributions.computed_at` | 0 | 8,159 | 0 |
| `show_picks.computed_at` | 0 | 15,205 | 0 |
| every other watermark column | 0 | all | 0 |

`olof_pages` is the lone ISO-`T` writer; everything else uses
`YYYY-MM-DD HH:MM:SS`. Since `'T'` (0x54) sorts **after** `' '` (0x20), naive
string comparison inverts within the same day:

```
'2026-07-14T00:00:01' > '2026-07-14 23:59:59'   ->  True   # wrong
```

`olof parse → song_index` is precisely a cross-format comparison, so this is a
live bug, not a hypothetical. All timestamps must go through one
`_parse_ts(value) -> datetime | None` helper that accepts both separators and
optional tz, before any comparison. Never compare these columns as strings, and
never compare them in SQL. Values are naive local time; do not mix in
`datetime.now(timezone.utc)`.

### 1c. Config inputs have no signal at all

Some steps' inputs are **code or config, not rows**, so no timestamp anywhere
moves when they change:

- `_KNOWN_TAPER_ALIASES` in `backend/db.py` — edit it and `taper_attributions`
  is wrong, therefore `show_picks` is wrong. Zero timestamps move.
- `concert_ranker/config.py` bands/thresholds — change them and every
  `quality_recording_scores` verdict is stale without a rescan.
- TapeMatch thresholds, tracked by hand in `CALIBRATION_PROGRESS.md`.

Phase 1 reports these steps' config dimension as `unknown` and says so in the
reason string — it does **not** invent a stamp. Adding a `version` signal (a hash
of the alias tuple / config constants, stored in `meta`) is a small, well-defined
follow-up, but it is a *write*, so it belongs to Phase 2 where writes are already
on the table. Recording the gap explicitly here is what keeps it from being
rediscovered later as a mystery.

---

## 2. Deliverables

### 2.1 `backend/refresh.py` (new, ~300 lines)

The registry and the planner. Modeled deliberately on `backend/activity.py`'s
declarative `JOB_ADAPTERS` table — same shape, same "observe, never own" rule.

```python
class RefreshStep(NamedTuple):
    step_id: str            # 'attribute_tapers'
    label: str              # i18n key suffix
    trigger: str            # 'T1' | 'T2' | 'T3' | 'T4'
    kind: str               # 'wholesale' | 'incremental' | 'manual'
    # --- signals (§1a). At least one required; backlog preferred. ---
    backlog_sql: str | None     # -> one int: rows still unprocessed
    last_run_sql: str | None    # -> one timestamp (naive local, either separator)
    version_key: str | None     # meta key holding a config hash; None in Phase 1
    upstream: tuple[str, ...]   # step_ids this depends on (the §3 DAG edges)
    how_to_run: str             # route or exact CLI command, for display
    cost: str                   # 'fast' | 'slow' | 'very_slow'
    human_gate: bool
```

Public API — all read-only, all synchronous:

- `compute_plan(db_path=None) -> dict` — the whole snapshot:
  `{steps: [...], stale_count, by_trigger: {...}, generated_at}`.
  Per step: `last_run`, `age_days`, `state`, `reason`, `backlog`, `blocked_by`,
  `how_to_run`.
- `_step_state(step, last_run, upstream_runs, backlog) -> str` — the one
  staleness rule, isolated so it is unit-testable without a DB. Evaluates every
  declared signal and returns the most severe:
  - `unknown` — no signal available (or all signals unavailable)
  - `blocked` — an upstream step is itself stale (report the culprit, don't
    double-report the symptom)
  - `stale` — **`backlog > 0`** (checked first — it is the direct measure), or,
    for wholesale steps with no backlog signal, any upstream `last_run` is newer
    than mine after `_parse_ts()` normalization
  - `fresh` — otherwise

  Each step's `reason` string names *which* signal fired and which are missing,
  so a `fresh` verdict backed only by a proxy is never mistaken for a `fresh`
  verdict backed by a zero backlog.

- `_parse_ts(value) -> datetime | None` — the §1b normalizer. Accepts both
  separators and optional tz; returns naive local. **Every** timestamp comparison
  in the module goes through it; none happen in SQL.

Every `last_run_sql` / `backlog_sql` runs inside a **read-only connection**
(`file:...?mode=ro`) with a defensive `_table_exists()` guard, matching the
existing pattern in `gap_analysis.py` / `lb_coverage.py` / `song_index.py`. A step
whose table is missing reports `unknown`, never raises — same degradation rule as
the `/api/derived/recompute` chain's per-step skip.

The `upstream` tuples encode the §3 DAG from the inventory. This is the one place
the ordering knowledge gets written down (fixes D3 for read purposes; Phase 3
reuses the same tuples for execution order).

### 2.2 `GET /api/refresh/status` (in `backend/app.py`)

Thin wrapper over `compute_plan()`. Returns JSON. No curator gate (read-only,
local-only, same rationale as `/api/lb/coverage`). Optional `?trigger=T1` filter.

Register it near `/api/lb/coverage` (`app.py:4787`) — same read-only-snapshot
family.

### 2.3 `tools/refresh_status.py` (new)

CLI table for terminal use and for cron/scripted checks. Single-line-per-row
output per the repo's CLI convention:

```
STEP                  TRIGGER  STATE    LAST RUN     AGE   BACKLOG  HOW TO RUN
attribute_tapers      T1       stale    2026-07-20   23d   -        POST /api/derived/recompute
ranker_scan           T2       stale    2026-06-30   43d   118      concert_ranker/cli.py scan --lb …
```

Exit code 0 always (it is a report, not a gate) unless `--exit-nonzero-if-stale`
is passed, so it can be dropped into cron later.

### 2.4 GUI: "Data freshness" card on `ScreenHome`

**Not a new screen.** ScreenGaps was retired into Library rows (TODO-270); this
follows that precedent rather than proliferating screens.

A card on `ScreenHome.tsx` showing:
- A one-line headline: *"6 steps out of date"* / *"Everything up to date"*.
- Rows for stale steps only, grouped by trigger, each showing label, age, backlog,
  and the `how_to_run` string (copyable for the CLI-only ones).
- Publish lag called out separately when `master_published_at` is behind — the
  D7 fix, and the reason this card earns its place on Home rather than hiding
  behind a tab.

Steps whose `how_to_run` is an existing route get a button that hits that route
directly (they already exist and are already activity-tracked). CLI-only steps
show the command as copyable text — Phase 2 turns those into buttons.

### 2.5 Tests: `tests/test_refresh.py`

- `_step_state()` truth table — pure function, no DB, covers all four states,
  the `blocked` precedence over `stale`, and backlog-beats-watermark precedence
  (a step with `backlog=0` but a newer upstream watermark must **not** be
  reported stale — that is the false-positive case from §1a).
- `_parse_ts()` — both separators, tz-suffixed input, `None`, and garbage. Plus
  an explicit regression test for the §1b inversion: the ISO-`T` olof value and
  a same-day space-separated value must order correctly, which they do not as
  raw strings.
- Every `last_run_sql` and `backlog_sql` in the registry **parses and executes**
  against the fixture DB (`tools/make_fixture_db.py`) and returns the right
  arity. This is the regression guard that matters: it catches a renamed column
  the day it is renamed, rather than silently reporting `unknown` forever.
- Registry integrity: every `upstream` id resolves to a real `step_id`; no cycles.
- A missing-table case reports `unknown` and does not raise.

---

## 3. Files touched

| File | Change |
|---|---|
| `backend/refresh.py` | **new** — registry + planner |
| `backend/app.py` | +1 route, `GET /api/refresh/status`, near line 4787 |
| `tools/refresh_status.py` | **new** — CLI report |
| `gui_next/src/renderer/src/screens/ScreenHome.tsx` | + freshness card |
| `gui_next/src/renderer/src/locales/en.json` | + strings (then `/gui-next-i18n` for de/fr/es/it/nl) |
| `tests/test_refresh.py` | **new** |
| `PROJECT.md` | + §Refresh planner (routes + module reference sections) |
| `CHANGELOG.md`, `TODO.md` | via `/session-close` |

No existing backend module is modified. No schema change. Nothing that runs today
runs differently.

---

## 4. Known gaps Phase 1 will report as `unknown`

Honest limits, to be closed in Phase 2 when those steps get run-records:

- **bobserve fetch** — shares `olof_pages` with Olof; needs a `source='bobserve'`
  filter to separate the two watermarks. Doable in SQL; verify the column name
  during implementation.
- **ranker rerank** — `quality_recording_scores` has no timestamp column. Infer
  from `quality_scans.started_at` (the scan it derives from) and mark the
  inference explicitly in the reason string, or report `unknown`. Do **not** add
  a column in Phase 1.
- **xref ingest, attachments reconcile, mirror crawl, WTRF, bootlegs, site-data
  publish, preservation, archive.org** — no queryable local signal. `unknown`.
- **Human queues** (taper conflicts, fingerprint suggestions, TapeMatch
  judgments) — counts are queryable and worth showing as backlog, but they are
  D5 blockers rather than staleness; Phase 4 gives them proper treatment.

---

## 5. Verification

- `pytest tests/test_refresh.py -v`, plus the targeted backend suite.
- `/backend-restart`, then `curl localhost:5174/api/refresh/status | jq` and
  sanity-check the numbers against §1's table (they should broadly match, since
  §1 was computed by hand from the same DB).
- `.venv/bin/python3 tools/refresh_status.py` — visually compare to the route.
- `/gui-check` (mandatory for gui_next), then `/verify` Tier A for the Home card
  since it changes layout.
- `/gui-next-i18n` for the new locale strings.
- `/session-close`.

---

## 6. What Phase 1 deliberately does not do

- Does not run anything. Every button on the card triggers a route that already
  exists today; nothing new becomes executable.
- Does not wrap the four CLI-only orphans (Phase 2).
- Does not chain steps (Phase 3).
- Does not add `refresh_step_runs`, because §1 showed it isn't needed yet. When
  Phase 2 wraps the orphans, *those* steps will need run-records — that is the
  right moment to add the table, with real requirements rather than guessed ones.
