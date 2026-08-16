# Pipeline Refresh — Phase 3 spec: chained execution in dependency order

> Companion to `PIPELINE_REFRESH_INVENTORY.md` (57-step inventory, D1–D8),
> `PIPELINE_REFRESH_PHASE1.md` (read-only freshness planner) and
> `PIPELINE_REFRESH_PHASE2.md` (four CLI-only steps become buttons).
> Phase 3 of 4. Written 2026-08-16. Tracks TODO-308.
>
> **Phase 3 is the first phase that runs more than one step.** It adds one
> module, one table, six routes, two parser routes, and turns the freshness
> card's `blocked` rows into a "Run chain" affordance.

---

## 1. Context — why this phase exists

Phase 1 encoded the §3 graph as data (`RefreshStep.upstream`) and Phase 2 made
four of its roots executable, but the `upstream` tuples are still read-only
reasoning: they colour a row `blocked` and name the culprit, and then the user
walks the chain by hand. That is inventory D3 (*"ordering is tribal knowledge"*)
half-fixed — ordering is *data*, but nothing *executes* along it.

The gap is most visible in exactly the place Phase 2 opened up. Pressing "Run"
on `olof_fetch` now succeeds and immediately makes `olof_parse` stale, which
makes `song_index` blocked, which makes `setlist_fingerprint` blocked. The
button that Phase 2 shipped creates three new rows of work whose only
instruction is a `<code>` string to copy into a terminal — and one of those
strings (`.venv/bin/python3 -m backend.olof_parser`) is not even a route.

Intended outcome: from the freshness card, one action runs a *chain* — the
selected step plus everything it is blocked on (or every stale step in one
trigger) — strictly in topological order, with per-step run records, one live
progress surface, a stop that takes effect between steps, and an explicit,
honest report of the steps a chain could not run for you.

**Out of scope:** first-class human-queue blockers (Phase 4), parallel branch
execution, and any scheduling/automatic triggering. Chains are always started by
a human (inventory §5 requirement 8).

---

## 2. Binding decisions (tj, 2026-08-16)

| # | Decision |
|---|---|
| 1 | Two entry points, one planner: **per-step unblock** ("run this and everything it's blocked on") and **per-trigger** ("refresh every stale step in T1"). |
| 2 | Steps with no callable entry point are **skipped, not fatal** — the chain continues and reports them. The two CLI-only parsers are the exception: they get routes this phase, because they are the direct downstream of Phase 2's fetch buttons. |
| 3 | **Sequential, one chain at a time.** One `JobState` claim covers the whole chain; steps run strictly in topological order. No parallel branches (Phase 2's write-contention risk is already at its margin). |
| 4 | `cost='very_slow'` and `human_gate=True` steps are **excluded by default** and included only via an explicit opt-in on the preview. |
| 5 | A chain **re-plans nothing mid-flight**: the step list is frozen at preview time, so what the user approved is what runs. Freshness is re-evaluated per step only to *skip* steps that became fresh. |
| 6 | The chain never starts a step whose own worker is already running — it **fails the preview**, rather than queueing behind it. |

---

## 3. Deliverables

### 3.1 `backend/refresh_exec.py` (new, ~260 lines)

The executor registry and the chain planner. Imports `backend.refresh` for the
DAG; `refresh.py` does **not** import this module (the planner stays read-only,
which is the property Phase 1 was built around).

```python
class StepExecutor(NamedTuple):
    step_id: str
    mode: str                      # 'inproc' | 'job' | 'manual'
    run: Callable[..., dict] | None       # inproc: returns a counters dict
    start: Callable[..., bool] | None     # job: claims + starts, False if busy
    status: Callable[[], dict] | None     # job: JobState-shaped progress dict
    stop: Callable[[], None] | None
    reason: str | None             # manual only: why this cannot be chained

EXECUTORS: dict[str, StepExecutor]

def plan_chain(*, step_id=None, trigger=None, include_expensive=False,
               db_path=None) -> dict
def run_chain_claimed(plan: dict, db_path=None) -> dict
```

All callables are resolved **lazily inside the executor**, never at import time —
`concert_ranker`/`numpy` and `bs4`/`lxml` must not be pulled into backend startup
(the constraint `activity.py` already documents for the Phase 2 wrappers).

**Executor coverage.** Three tiers, and the tiering is the honest part of this
phase — it is written down rather than discovered at runtime:

| Tier | Steps | How the chain runs them |
|---|---|---|
| `inproc` | `olof_parse`, `bobserve_parse`, `parse_lineage`, `attribute_tapers`, `compute_show_picks`, `song_index`, `ranker_rerank` | Call the function, await the dict, record the run. |
| `job` | `olof_fetch`, `bobserve_fetch`, `ranker_scan`, `geocode`, `scrape_entries` | Claim + start the worker, then poll its status until `running` goes false. |
| `manual` | everything else — `flat_file_apply`, `db_import`, `lb_master_reconcile`, `setlist_fingerprint`, `pipeline_run`, `tapematch_sync`, `xref_ingest`, `attachments_reconcile`, `mirror_crawl`, `wtrf_crawl`, `bootleg_scrape`, `master_publish`, `sitedata_publish`, `preservation`, `archive_org` | Never executed. Listed in the plan with `reason` and skipped at run time. |

`manual` is not a permanent verdict — it is "not wired in Phase 3". Each one
carries a one-line `reason` (`"needs a chosen release file"`, `"human gate"`,
`"no completion signal"`, `"machine-local cron"`) which the GUI shows verbatim.
A test asserts every `STEPS` entry appears in `EXECUTORS` exactly once, so a new
registry step cannot silently become invisible to the chain.

**`plan_chain`** calls `refresh.compute_plan()` once, then:

- `step_id=` — walk `upstream` transitively from that step, keep the target plus
  any ancestor whose state is `stale` (a `blocked` ancestor contributes its own
  ancestors, not itself-as-work). Order by `refresh._topological_order()`.
- `trigger=` — every step of that trigger whose state is `stale` or `blocked`,
  **plus** the stale ancestors those blocked steps depend on even when the
  ancestor belongs to a different trigger (this is the whole point; a T3 chain
  that cannot run its T1 prerequisite is theatre).
- Exactly one of `step_id`/`trigger` is required; both or neither → `ValueError`
  → 400.

Then partition into `runnable` / `excluded` / `manual`:

```python
{"scope": {"step_id": …, "trigger": …, "include_expensive": bool},
 "runnable": [{"step_id", "mode", "cost", "state", "reason"}],
 "excluded": [{"step_id", "why": "very_slow"|"human_gate"}],
 "manual":   [{"step_id", "why": <StepExecutor.reason>}],
 "blocked_by_running": ["ranker_scan"],   # decision 6
 "planned_at": "…"}
```

`blocked_by_running` is non-empty ⇒ `POST /api/refresh/chain/start` 409s. The
preview route still returns 200 with the field populated, so the GUI can explain
*why* the button is disabled instead of only failing on press.

**`run_chain_claimed`** — the thread target; `_CHAIN` is already claimed by the
route (Phase 2's race-free start sequence, unchanged). Per step, in order:

1. `check_stop()`. A stop between steps is the granularity contract — an
   in-flight `job` step is *also* asked to stop via its own `stop()`, so a stop
   during a fetch behaves as it does today.
2. Re-evaluate that one step's freshness (decision 5): `refresh.compute_plan()`
   is too heavy per step, so `refresh_exec` calls the two cheap primitives
   directly — `refresh._run_scalar(conn, step.backlog_sql)` and
   `refresh._version_signal(conn, step)`. Backlog 0 **and** version not
   `changed` ⇒ record `status='noop'` and continue. This is what makes a T1
   chain cheap the second time it is run.
3. Run it. `inproc`: call, capture the dict. `job`: `start()`, then poll
   `status()` every 1.0 s via `_CHAIN.sleep(1.0)` (so a chain stop is
   responsive) until `running` is false; mirror the worker's `done`/`total`
   into the chain's own progress under a `sub_progress` key.
4. `database.record_step_run(step_id, status=…, started_at=…, counters=…,
   trigger_source='chain')` + `config_version.stamp_for_step(step_id)` on
   success. **`trigger_source='chain'` is new** and is the only schema-visible
   change to `refresh_step_runs`.
5. On exception: record `status='error'`, append to the result's `errors`, and
   **halt the chain** — downstream steps in a dependency chain consume the
   output of the step that just failed, so continuing produces garbage with a
   green tick. Halting mid-chain is not an error state for the *chain*; it
   returns `status='partial'`.

Returns `{"status": "ok"|"partial"|"stopped", "ran": [...], "skipped": [...],
"errors": [{"step_id", "message"}], "started_at", "finished_at"}` and writes
one `refresh_chain_runs` row.

### 3.2 `refresh_chain_runs` + `record_chain_run()` (`backend/db.py`)

DDL beside `refresh_step_runs` (Phase 2, `db.py`), same column style and the
same `time.strftime("%Y-%m-%d %H:%M:%S")` naive-local format:

```sql
CREATE TABLE IF NOT EXISTS refresh_chain_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_kind   TEXT NOT NULL,          -- 'step' | 'trigger'
    scope_value  TEXT NOT NULL,          -- step_id or 'T1'
    started_at   TIMESTAMP NOT NULL,
    finished_at  TIMESTAMP,
    status       TEXT NOT NULL,          -- ok|partial|stopped|error
    steps_json   TEXT,                   -- the frozen plan + per-step outcome
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_chain_runs_started
    ON refresh_chain_runs(started_at);
```

One insert at completion, written through `_run_queued_write` (the helper Phase 2
generalised). The per-step rows in `refresh_step_runs` remain the authoritative
freshness signal — this table exists so "what did that chain actually do?"
survives the restart that D8 otherwise eats, and so the GUI can show a last-run
summary without keeping it in renderer state.

Nothing here is exported: no new `USER_META_KEYS` (this is history, not config),
and the table is install-local like `refresh_step_runs`.

### 3.3 Parser routes (decision 2)

Two thin routes in `backend/app.py`, immediately after the Phase 2 fetch block.
Both are **synchronous** — a full DSN reparse is tens of seconds, not minutes,
and both `run_parse()` functions are already pure-DB with no network:

| Route | Body | Response |
|---|---|---|
| `POST /api/olof/parse` | `{file?}` | `{"ok":true, …coverage summary}` · 409 while `olof_fetch` runs · 503 if `bs4` missing |
| `POST /api/bobserve/parse` | `{file?}` | same shape |

Each records its own `refresh_step_runs` row (`trigger_source='route'` when
called directly, `'chain'` from the executor — the executor calls
`olof_parser.run_parse` directly, not over HTTP). Registry `how_to_run` for
`olof_parse`/`bobserve_parse` changes from the `-m backend.olof_parser` string
to the route, which is the visible payoff on the card.

The 409-while-fetching guard matters: a parse that runs against a half-written
mirror directory produces a coverage summary that looks like data loss.

### 3.4 Routes (`backend/app.py`)

One block after the parser routes. Ungated, same `{"error": …}, <code>` idiom.

| Route | Body | Response |
|---|---|---|
| `POST /api/refresh/chain/preview` | `{step_id?, trigger?, include_expensive?}` | the `plan_chain` dict · 400 bad scope |
| `POST /api/refresh/chain/start` | same body | `{"status":"started","steps":[…]}` · `{"status":"noop"}` when `runnable` is empty · 409 already running / `blocked_by_running` |
| `GET /api/refresh/chain/status` | — | chain progress dict + `sub_progress` |
| `POST /api/refresh/chain/stop` | — | progress dict |
| `GET /api/refresh/chain/history` | `?limit=` (default 10) | `refresh_chain_runs` rows, newest first |

`start` re-plans server-side from the same body rather than trusting a plan
posted by the client — the client's plan may be seconds stale and it is not a
trust boundary worth inventing.

### 3.5 `backend/activity.py`

One lazy wrapper, one `JobAdapter` **appended** (order is precedence for the
legacy `busy_snapshot()`), one `_PROGRESS_FIELDS` entry:

```python
JobAdapter("refresh_chain", _get_refresh_chain_status, "/api/refresh/chain/stop", "/"),
```

`current` carries the running step_id, so the status bar reads "Refreshing —
attribute_tapers (3/7)". The chained worker's *own* adapter row stays where it
is; both appear while a chain runs a `job`-mode step, which is correct — they
are two true facts, and `activity.py` observes rather than owns.

### 3.6 GUI — `DataFreshnessCard.tsx`

The Phase 2 `RUNNABLE` map and its `RunControl` are untouched. New, alongside:

- **Per-trigger header button** — each trigger group's header gains "Refresh
  T*n*" when that group has any `stale`/`blocked` step.
- **Per-row chain button** — a `blocked` row's `HowToRun` renders "Run chain"
  instead of the culprit's `<code>` string. `stale` rows keep Phase 2 behaviour
  (a direct Run button when wrapped, the copy fallback otherwise).
- **Preview dialog** — both buttons open one dialog fed by
  `/api/refresh/chain/preview`: the ordered runnable list with per-step cost
  pills, a collapsed "won't run" section listing `manual` steps with their
  `reason`, and — when `excluded` is non-empty — a checkbox "Include slow and
  publish steps (N)" that re-previews with `include_expensive: true`. Confirm
  runs `start`.
- **Live state** — poll `/api/refresh/chain/status` every 2 s while running;
  render `done/total` plus the current step label and the nested `sub_progress`
  bar for `job`-mode steps; Stop replaces Run. On completion re-fetch
  `/api/refresh/status` so the card self-updates, and surface a one-line
  outcome ("5 of 7 steps ran; parse_lineage failed") that links nowhere and
  disappears on the next refresh.

New `en.json` keys: `refresh.chain.{runTrigger,runChain,previewTitle,willRun,
wontRun,excluded,includeExpensive,confirm,running,stopping,outcomeOk,
outcomePartial,outcomeStopped,alreadyRunning,busyStep}` plus
`appShell.statusBar.activity.refresh_chain`. Then `/gui-next-i18n`.

### 3.7 `tools/refresh_status.py`

`--chain <step_id|T1>` prints the plan `plan_chain` would produce (runnable /
excluded / manual, in order) and exits without running anything. The dry-run
surface the GUI dialog is built on, usable from a terminal for debugging a
chain that "did nothing".

---

## 4. Files touched

| File | Change |
|---|---|
| `backend/refresh_exec.py` | **new** — `StepExecutor`, `EXECUTORS`, `plan_chain`, `run_chain_claimed` |
| `backend/db.py` | `refresh_chain_runs` DDL, `record_chain_run()` |
| `backend/refresh.py` | `how_to_run` for `olof_parse`/`bobserve_parse` → routes. No other change |
| `backend/scraper.py` | extract the `/api/scrape/start` worklist builder into `plan_range()` so `scrape_entries` is chainable (mirrors Phase 2's `collection_worklist` promotion) |
| `backend/app.py` | +2 parser routes, +5 chain routes, `scrape_start` calls `scraper.plan_range()` |
| `backend/activity.py` | 1 wrapper, 1 `JobAdapter`, 1 `_PROGRESS_FIELDS` |
| `gui_next/.../components/DataFreshnessCard.tsx` | chain buttons, preview dialog, chain polling |
| `gui_next/.../locales/en.json` | new keys (+ `/gui-next-i18n`) |
| `tests/test_refresh_exec.py` | **new** |
| `tests/test_refresh.py`, `tests/test_pipeline_jobs.py` | registry↔executor integrity, parser-route tests |
| `PROJECT.md`, `CHANGELOG.md`, `TODO.md` | reference sections + `/session-close` |

Build order: `db` schema/helper → `refresh_exec` registry → `plan_chain` +
`tools/refresh_status.py --chain` (fully testable with zero execution) →
parser routes → `scraper.plan_range` → `run_chain_claimed` → chain routes →
activity → GUI.

The planner half is worth landing and committing on its own: it is the half with
the subtle logic, it is verifiable from the CLI, and it ships no way to start
anything.

---

## 5. Tests

**`tests/test_refresh_exec.py` (new).** No network, no audio, every executor
monkeypatched.

- **Registry integrity, both directions**: every `refresh.STEPS` step_id has
  exactly one `EXECUTORS` entry; every `EXECUTORS` key is a real step_id; every
  `mode='manual'` entry has a non-empty `reason`; every `mode='inproc'|'job'`
  entry resolves its callables without raising (import check only, no call).
- **`plan_chain` ordering** is a prefix-consistent subsequence of
  `refresh._topological_order()` on a synthetic DB, for both scopes.
- **Per-step scope** pulls in stale ancestors and *not* fresh ones; a `blocked`
  ancestor contributes its ancestors rather than itself.
- **Trigger scope crosses trigger boundaries** for prerequisites (the T3-needs-T1
  case named in §3.1).
- **`include_expensive=False`** keeps `very_slow`/`human_gate` out of `runnable`
  and in `excluded`; `True` moves them.
- **`blocked_by_running`** is populated when a `job`-mode step's `status()` says
  running, and `start` 409s on it.
- **Both/neither scope arg** → `ValueError`.
- **`run_chain_claimed`** over three fake steps: order preserved, three
  `refresh_step_runs` rows with `trigger_source='chain'`, one
  `refresh_chain_runs` row with `status='ok'`.
- **Failure halts**: middle step raises → `status='partial'`, one `error` row,
  the third step never called and recorded nowhere.
- **Stop between steps**: stop flag set after the first → `status='stopped'`,
  second never runs, and the flag is cleared by `finish()`.
- **Re-evaluation skip** (decision 5): a step whose backlog is 0 at run time is
  recorded `noop` and its callable is never invoked; a `version_state='changed'`
  step at backlog 0 *is* invoked.
- **`job`-mode wait loop** terminates when the fake status flips `running` false,
  and mirrors `done`/`total` into `sub_progress`.

**`tests/test_refresh.py` (additions).** `how_to_run` route-existence (the Phase 2
test already enforces it) now covers the two parser routes — that test is the
reason this phase cannot ship a typo'd route string on the card.

**`tests/test_pipeline_jobs.py` (additions).** `POST /api/olof/parse` with a
monkeypatched `run_parse` writes one `refresh_step_runs` row; 409s while
`olof_fetch` is claimed.

---

## 6. Verification

1. `.venv/bin/python3 -m pytest tests/test_refresh_exec.py tests/test_refresh.py tests/test_pipeline_jobs.py -v`, then the targeted backend suite.
2. `/backend-restart`.
3. `.venv/bin/python3 tools/refresh_status.py --chain olof_parse` — plan lists `olof_fetch` then `olof_parse`, nothing else.
4. `.venv/bin/python3 tools/refresh_status.py --chain T3` — reconcile by hand against the card's T3 group; prerequisites from other triggers must appear.
5. `POST /api/refresh/chain/preview {"trigger":"T2"}` — `excluded` contains `ranker_scan` (very_slow); re-preview with `include_expensive:true` moves it to `runnable`.
6. `POST /api/refresh/chain/start {"step_id":"song_index"}` → `GET /api/refresh/chain/status` shows the running step; `/api/activity` shows `refresh_chain`; `/api/stats` stays responsive.
7. Start a chain containing a `job` step, `POST /api/refresh/chain/stop` mid-step — the worker's own stop fires, `refresh_chain_runs` gets a `stopped` row, and the chain does not advance.
8. Run the same chain twice — the second run records `noop` for every step whose backlog is 0 and finishes in seconds.
9. `POST /api/olof/parse` directly, then `GET /api/refresh/status` → `olof_parse` fresh, `last_run_source='run_record'`.
10. `/gui-check` (mandatory), then `/verify` Tier A on Home (the card gains a dialog and per-group buttons).
11. `/gui-next-i18n`.
12. `PROJECT.md`: routes section (+7), schema section (`refresh_chain_runs`), module reference (`refresh_exec`). Wiki touch-up to `Collection-Pipeline.md` via `/wiki-update`.
13. `/session-close`.

---

## 7. Residual risks

- **`manual` is most of the registry.** 15 of 27 steps cannot be chained in
  Phase 3, so a T4 chain is nearly empty and a T1 chain still needs a human for
  `db_import`. The preview dialog's "won't run" section is therefore not a
  footnote — it is the honest headline, and it must not be collapsed by default
  when it is longer than the runnable list.
- **Sequential means slow.** A T2 chain that includes `ranker_scan` is an
  hours-long single-threaded walk. Decision 4 keeps it opt-in; decision 3 keeps
  it from being made worse by contention.
- **Halt-on-error strands the tail.** A failure at step 2 of 7 leaves five steps
  untouched with no queue to resume from — the user re-previews and starts
  again. Acceptable because a re-run is now cheap (decision 5's noop skip), but
  it is why the outcome line names the failing step.
- **`scraper.plan_range()` extraction** touches a long-lived route body
  (`/api/scrape/start`) that predates all of this. The route's behaviour must be
  byte-identical afterwards; it is the one refactor in this phase that can break
  something a user does daily.
- **Two progress surfaces during `job` steps.** The chain and the worker both
  report running. Intended, but the status bar must not read as two independent
  jobs — the chain row's label carries the step name for exactly that reason.

---

## 8. What Phase 3 deliberately does not do

- Does not give human queues (taper conflicts, fingerprint suggestions,
  TapeMatch judgments, xref approvals) blocker treatment with counts — Phase 4,
  and inventory D5 stays open until then.
- Does not run independent branches in parallel (decision 3).
- Does not schedule, poll, or auto-start anything: no timer, no startup hook, no
  "run on new arrivals" (inventory open question 3 stays unanswered).
- Does not wire the 15 `manual` steps; each keeps its Phase 1/2 behaviour and its
  `reason` string.
- Does not make any step incremental — inventory requirement 4 (accept an
  affected-LB set) is untouched, and `ranker_scan`'s backlog mode remains the
  only example in the system.
