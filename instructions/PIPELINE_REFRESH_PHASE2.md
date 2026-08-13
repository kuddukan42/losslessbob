# Pipeline Refresh — Phase 2 spec: make the CLI-only steps runnable

> Companion to `PIPELINE_REFRESH_INVENTORY.md` (57-step inventory, D1–D8) and
> `PIPELINE_REFRESH_PHASE1.md` (the read-only freshness planner). Phase 2 of 4.
> Written 2026-08-12. Tracks TODO-306.
>
> **Phase 2 is the first phase that writes.** It adds one table, three `meta`
> keys, eight routes, and turns four copyable CLI strings on the Home card into
> buttons.

---

## 1. Context — why this phase exists

Phase 1 shipped a planner that can *see* the whole pipeline but cannot *touch*
it. The inventory's §3 graph has four roots-of-record living entirely outside the
application: `olof fetch`, `bobserve fetch`, `concert_ranker scan`, and
`tapematch run`. Three of those four (TapeMatch stays a machine-local cron, by
decision) plus `concert_ranker rerank` are what Phase 2 wraps.

Two consequences follow from wrapping them, and they are the rest of this phase:

- Wrapped steps are the first ones that genuinely need **run-records** — the
  Phase 1 argument for skipping `refresh_step_runs` ("read the ledger that
  already exists") holds only for steps whose output tables carry a timestamp.
  `ranker_rerank` writes `quality_recording_scores`, which has no timestamp
  column at all, so it currently reports `last_run: null` forever.
- Two of the four steps are driven by **config, not rows** (inventory §1c): the
  taper alias table and `concert_ranker/config.py`. Edit either and every
  downstream verdict is wrong while every timestamp stays put. That is the
  `version` signal Phase 1 deliberately deferred.

Intended outcome: the Home freshness card's four CLI-only rows become
"Run" buttons with live progress in the status bar and a stop control, config
changes stop being invisible, and every step run leaves a durable record that
survives a backend restart (fixes D8 for these steps).

**Out of scope:** chaining steps in dependency order (Phase 3) and first-class
human-queue blockers (Phase 4).

---

## 2. Binding decisions (tj, 2026-08-12)

| # | Decision |
|---|---|
| 1 | `POST /api/ranker/scan` defaults to **backlog-only**; a full rescan needs an explicit `{mode:"all"}` plus a GUI confirm. |
| 2 | Fetch routes are **ungated** (same rationale as `/api/geocode/run`); the GUI Run button confirms once. |
| 3 | Only the **four newly wrapped steps** get live Run buttons; every other card row keeps Phase 1 behaviour. |
| 4 | Packaging: add `multiprocessing.freeze_support()` to `run_backend.py` **and** force `workers=1` when `sys.frozen`. |
| 5 | `ranker_scan.backlog_sql` is **rescoped to the latest scan_id**, so the card's number equals the route's `planned`. |
| 6 | A `version_key` with no stored hash is **benign** — annotate the reason, never change the state. |

---

## 3. Deliverables

### 3.1 `backend/job_progress.py` (new, ~90 lines)

One shared primitive for the three new background workers, modelled on
`backend/geocoder.py`'s `_progress`/`_lock`/`stop()` contract.
**`geocoder.py` is not refactored onto it** — working code, no reason to churn.

```python
class JobStopped(Exception): ...

class JobState:
    """Thread-safe progress, atomic claim, and cooperative stop for one job."""
    def __init__(self, name: str) -> None
    def try_begin(self, **fields) -> bool   # atomic claim; False if already running
    def update(self, **fields) -> None
    def bump(self, key: str, n: int = 1) -> None
    def check_stop(self) -> None            # raises JobStopped
    def sleep(self, seconds: float, slice_s: float = 0.5) -> None  # raises JobStopped
    def stop(self) -> None
    def finish(self, **fields) -> None      # running=False, stop_requested=False
    def snapshot(self) -> dict
```

Field set matches `activity._PROGRESS_FIELDS` expectations: `running, done,
total, current, errors, skipped, stage, stop_requested, started_at`.

`try_begin()` is an atomic claim, which also closes the check-then-set race
`/api/geocode/run` has today (two rapid POSTs both pass its `if running` check).
Routes claim first, then start the thread.

### 3.2 Fetcher retrofit — `backend/olof_fetcher.py`, `backend/bobserve_fetcher.py`

Identical in both. **Public `run_fetch()` signature is unchanged** so the CLI and
existing tests keep working.

Split: `_run_fetch_inner()` (current body, progress-aware, assumes claimed) ·
`run_fetch()` (claims, then inner, `finally` finish + run-record) ·
`run_fetch_claimed()` (thread target for the route; job already claimed).
Module surface adds `_JOB = JobState(...)`, `get_status()`, `stop()`,
`try_begin()`.

Progress points: `stage="discovering"` during index/TOC fetch (it does network
I/O with sleeps, so it must be cancellable too), then `total=len(tasks)` and
`stage="fetching"`; per task `current=<filename>` and a `fetched`/`skipped`/
`errors` bump. Keep the existing `_PROGRESS_EVERY = 20` log lines.

**Interruptible waits** — every `time.sleep` becomes `_JOB.sleep(...)`:

| Site | Current | New |
|---|---|---|
| main loop politeness | `time.sleep(_REQUEST_DELAY)` 2.0 s | `_JOB.sleep(2.0, slice_s=0.25)` |
| `_fetch` HTTP-429 backoff | `time.sleep(30)` | `_JOB.sleep(30, slice_s=0.5)` |
| `_fetch` retry backoff | `time.sleep(3*(attempt+1))` | `_JOB.sleep(…, slice_s=0.5)` |
| bobserve year-index loop | `time.sleep(_REQUEST_DELAY)` | `_JOB.sleep(2.0, slice_s=0.25)` |

`JobStopped` propagates cleanly out of `_fetch` — its only `except` is
`requests.RequestException`. `_run_fetch_inner` catches `JobStopped` around the
main loop and returns the partial summary plus `{"stopped": True}`. Nothing is
left half-written: each page is `write_bytes` + `_upsert_page` + `commit` per
item already.

`requests.get(timeout=30)` is **not** interruptible — worst-case stop latency is
~30 s during an in-flight request. Document it; do not try to kill the request.

### 3.3 `backend/ranker_jobs.py` (new)

Backend-side wrapper so `concert_ranker/` stays standalone. Never call
`cli.main()` (it calls `logging.basicConfig`).

```python
def plan_scan(mode: str = "backlog", lbs: list[int] | None = None,
              db_path: str | None = None) -> dict
    # -> {"scan_id", "worklist", "planned", "reused_scan", "config_changed"}
def run_scan_claimed(worklist, scan_id, workers, db_path=None) -> dict
def run_rerank(scan_id: int | None = None, db_path: str | None = None) -> dict
```

**`plan_scan`** (decision 1) — `repo.connect` + `ensure_schema`, then reuse
`concert_ranker.cli`'s worklist builder (it encodes the non-concert/non-public
exclusions; duplicating it would drift). Promote `_collection_worklist` →
`collection_worklist` and `_rerank` → `rerank` in `cli.py`, keeping the private
names as aliases, so `backend/` is not reaching into underscore names.

- `mode="backlog"` (default): `scan_id = repo.latest_scan_id()` or create one;
  **config-drift guard** — if `quality_scans.config_json` for that scan differs
  from `json.dumps(vars(default_config()), sort_keys=True)`, create a *new* scan
  instead of appending (mixing two extraction configs inside one `scan_id`
  silently corrupts rankings) and return `config_changed=True`; filter the
  worklist by `repo.done_lbs(conn, scan_id)`. Empty → `planned=0`.
- `mode="all"`: always create a scan, full worklist.
- explicit `lbs`: filter to those, reuse the latest scan_id, `skip_done=False`.

**`run_scan_claimed`** — plain `threading.Thread(daemon=True,
name="ranker-scan")`; a plain thread is mandatory because `runner.scan_folders`
uses `mp.get_context("spawn")`. `scan_folders` has no cancel hook and reports
nothing until it returns, so slice the worklist into chunks of `4 * workers` and
call it per chunk with `skip_done=False` (already filtered in `plan_scan`),
checking `_JOB.check_stop()` between chunks. One Pool teardown per chunk (~1–2 s)
against chunks that take minutes of audio decode — negligible. *Rejected for this
phase:* adding a `should_stop` callable to `runner.scan_folders` — better
granularity, but it changes `concert_ranker` and needs its own tests.

Workers: `max(1, min(requested, 16))`, default
`max(1, min(8, (os.cpu_count() or 4) - 1))` — the CLI's 16 is right for a
dedicated terminal run, wrong for a process also serving the GUI and holding a
write queue. **`workers = 1` when `sys.frozen`** (decision 4), which takes
`scan_folders`' in-process branch and spawns no Pool at all.

After the scan — **including after a stop**, a partial scan is worth scoring —
`stage="reranking"` then `cli.rerank(conn, scan_id)`. Records **two** run rows
(`ranker_scan`, `ranker_rerank`) and stamps both version hashes on success.

`run_rerank` is synchronous and pure-DB; the route calls it inline and 409s while
a scan is running (it would otherwise race the scan's trailing rerank).

### 3.4 Routes (`backend/app.py`)

One block immediately after `GET /api/refresh/status` (`app.py:4797`). All
ungated (decision 2); errors use the local `{"error": …}, <code>` idiom.

| Route | Body | Response |
|---|---|---|
| `POST /api/olof/fetch` | `{corpus?, limit?, refresh?, dry_run?}` | `{"status":"started"}` · 409 already running · 400 bad corpus |
| `GET /api/olof/fetch/status` · `POST /api/olof/fetch/stop` | — | progress dict |
| `POST /api/bobserve/fetch` | `{start_year?, end_year?, limit?, refresh?, dry_run?}` | same shape |
| `GET /api/bobserve/fetch/status` · `POST /api/bobserve/fetch/stop` | — | progress dict |
| `POST /api/ranker/scan` | `{mode?, lb?, workers?, notes?}` | `{"status":"started","scan_id","planned","reused_scan","config_changed"}` · `{"status":"noop"}` · 409 |
| `GET /api/ranker/scan/status` · `POST /api/ranker/scan/stop` | — | progress dict |
| `POST /api/ranker/rerank` | `{scan_id?}` | `{"ok":true,"scan_id","rows"}` · 409 during a scan · 404 no scans |

Namespaces are free. Note the near-collision with the existing read-only
`/api/olof/status` — that is why the new one nests under `/fetch/`. Do **not**
name it `/api/olof/fetch_status`.

Race-free start sequence:

```python
if not _olof_fetcher.try_begin(stage="queued", corpus=corpus):
    return jsonify({"error": "already running"}), 409
threading.Thread(target=_olof_fetcher.run_fetch_claimed, kwargs={...},
                 daemon=True, name="olof-fetch").start()
return jsonify({"status": "started"})
```

`/api/ranker/scan` claims, calls `plan_scan()` (fast), and `finish()`es +
returns `noop` when `planned == 0`.

**`POST /api/derived/recompute`** (`app.py:5606`): inside `_stream()`, per step
capture `started_at`, then on success `database.record_step_run(name,
status="ok", …)` + `config_version.stamp_for_step(name)`; on exception
`status="error"`; record nothing on the `skipped` branch. The four `name` values
already equal registry `step_id`s — assert that in a test rather than trusting it.

**`run_backend.py`**: `multiprocessing.freeze_support()` as the first statement
of `main()` (decision 4).

### 3.5 `refresh_step_runs` + `record_step_run()`

DDL in `backend/db.py` next to `scrape_sessions` (`db.py:502`), same column style:

```sql
CREATE TABLE IF NOT EXISTS refresh_step_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id        TEXT NOT NULL,          -- refresh.STEPS step_id
    started_at     TIMESTAMP NOT NULL,     -- 'YYYY-MM-DD HH:MM:SS', naive local
    finished_at    TIMESTAMP,
    status         TEXT NOT NULL DEFAULT 'running',  -- running|ok|noop|stopped|error
    trigger_source TEXT,                   -- 'route' | 'cli' | 'cron'
    counters_json  TEXT,                   -- worker summary dict, verbatim
    notes          TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_step_runs_step
    ON refresh_step_runs(step_id, finished_at);
```

`CREATE TABLE IF NOT EXISTS` is idempotent and no `ALTER` is needed this phase —
but any later column addition uses the `PRAGMA table_info` pattern at
`db.py:2477`. Timestamps via `time.strftime("%Y-%m-%d %H:%M:%S")` — space-
separated naive local, matching every other watermark column and `_parse_ts`
(Phase 1 §1b).

```python
def record_step_run(step_id: str, *, status: str = "ok",
                    started_at: str | None = None, finished_at: str | None = None,
                    counters: dict | None = None, notes: str | None = None,
                    trigger_source: str = "route", db_path: str | None = None) -> int:
```

**One insert at completion**, not a start/finish pair: "currently running" is
already fully covered by `activity.snapshot()`, and a single insert avoids
carrying a rowid across a thread boundary and avoids orphan `running` rows after
a crash. Written through `get_write_queue()`; generalise `_run_alias_write`
(`db.py:1925`) into `_run_queued_write(fn, db_path)` — the BUG-246 db_path guard
is now needed in a second place, which is the moment to lift it.

Call sites: both fetch workers, the ranker worker (two rows), the rerank route,
the four `/api/derived/recompute` steps, and both fetchers' `__main__` blocks
with `trigger_source="cli"`.

**Deliberate gap:** `concert_ranker/cli.py` is left untouched — it must not
import `backend.db`. CLI scans produce no run record but still move
`quality_scans.started_at`, which the existing watermark catches. Say so in the
module docstring.

### 3.6 `backend/config_version.py` (new)

```python
def taper_config_hash(db_path: str | None = None) -> str
def ranker_scan_config_hash() -> str
def ranker_rank_config_hash() -> str

STEP_VERSION_SOURCES: dict[str, tuple[str, Callable[[], str]]] = {
    "attribute_tapers": ("refresh_version_taper_aliases", taper_config_hash),
    "ranker_scan":      ("refresh_version_ranker_scan_config", ranker_scan_config_hash),
    "ranker_rerank":    ("refresh_version_ranker_rank_config", ranker_rank_config_hash),
}

def stamp_for_step(step_id: str, db_path: str | None = None) -> str | None
def version_state(step_id: str, stored: str | None) -> str  # ok|changed|unstamped|n/a
```

**Taper hash** covers the *effective merged* config, not the source file:
`{"aliases": dict(db._KNOWN_TAPER_ALIASES), "not_taper": sorted(db._NOT_TAPER)}`.
Access as **module attributes** on `backend.db` (never
`from backend.db import _KNOWN_TAPER_ALIASES`) — `reload_taper_aliases()`
rebuilds the dict in place but reassigns the derived names. Call
`db.reload_taper_aliases(db_path)` first when `user_taper_aliases` exists; it is
a rebuild, not a write.

**Two ranker hashes**, from explicit name lists (not "all uppercase globals", so
an unrelated new constant does not spuriously invalidate every stored metric):

- scan/extraction: `BULK_SR, NATIVE_SR, NATIVE_WINDOW_SEC, NATIVE_N_WINDOWS,
  STFT_N_FFT, STFT_HOP, BANDS, POLARITY, DISQUALIFIERS`
- rank/banding: `SIGNED_BANDS, SEVERITY_BANDS, QUALITY_BANDS, _DECADE_CUTS,
  _SBD_CUTS, QUALITY_MODEL, QUALITY_MODEL_SBD, FAMILY_WEIGHTS, RECORDING_SCORE`

`DECADE_BANDS`/`CLASS_BANDS` are *derived* from the cuts — hashing the cuts is
sufficient and stabler. The canonical-JSON encoder maps dataclass instances
(`DISQUALIFIERS`) through `dataclasses.asdict` and sets through `sorted()`.

Meta keys `refresh_version_taper_aliases`,
`refresh_version_ranker_scan_config`, `refresh_version_ranker_rank_config`
**must be added to `USER_META_KEYS` (`db.py:125`)** or they ship in a master
export and one install's run history overwrites another's. Test it.

Stamped only on a *successful* run of the consuming step, colocated with the
`record_step_run` call so the two cannot drift.

### 3.7 `backend/refresh.py` — consuming both new signals

**Run records.** New guarded helper (no new `RefreshStep` field — the key is
`step_id`):

```python
def _last_run_record(conn, step_id: str) -> tuple[datetime | None, str | None]:
    """Return (newest successful finished_at, status of the newest row overall)."""
```

`compute_plan` takes `last_run = max(watermark, run_record)` and adds
`last_run_source` (`'run_record' | 'watermark' | None`) to the JSON and the
reason string. This alone closes the Phase 1 §4 gap for `ranker_rerank`, whose
`last_run_sql` is `None`, while the watermark keeps CLI/cron runs honest.

`_step_state` gains keyword-only args so every Phase 1 positional call and test
stays green:

```python
def _step_state(step, last_run, upstream_runs, backlog, *,
                version_state: str = "n/a", last_run_status: str | None = None,
                last_run_source: str | None = None) -> tuple[str, str]:
```

New precedence:

1. `version_state == "changed"` → **stale** — a config change invalidates output
   even at backlog 0, so it is checked first.
2. `backlog > 0` → stale *(unchanged)*.
3. newest row `status == "error"` with no later success → **stale**,
   "last run failed".
4. upstream stale/blocked → blocked *(unchanged)*.
5. watermark comparison, only when `backlog is None` *(unchanged)*.
6. unknown / fresh *(unchanged)*; `version_state == "unstamped"` is appended to
   the reason and **never** changes the state (decision 6).

**Registry edits:**

| step_id | change |
|---|---|
| `olof_fetch` | `how_to_run` → `POST /api/olof/fetch` |
| `bobserve_fetch` | `how_to_run` → `POST /api/bobserve/fetch` |
| `ranker_scan` | `how_to_run` → `POST /api/ranker/scan`; `version_key="refresh_version_ranker_scan_config"`; **`backlog_sql` rescoped to the latest scan** (decision 5) — `… WHERE m.scan_id = (SELECT MAX(scan_id) FROM quality_scans)`, so the card's number equals the route's `planned` |
| `ranker_rerank` | `how_to_run` → `POST /api/ranker/rerank`; `version_key="refresh_version_ranker_rank_config"`; `last_run_sql` stays `None` (the run record supplies it) |
| `attribute_tapers` | `version_key="refresh_version_taper_aliases"` |

**`upstream` edges: no changes.** `compute_show_picks` already lists
`attribute_tapers`, so an alias change propagates as `blocked` — correct, and it
avoids double-reporting one root cause.

New per-step JSON: `last_run_source`, `last_run_status`,
`version: {key, state, expected, stored}`.

### 3.8 Activity + GUI

**`backend/activity.py`** — three *lazy* status wrappers (so `bs4`/`lxml`/
`concert_ranker` are not pulled into backend startup), three `JobAdapter` rows
**appended** to `JOB_ADAPTERS` (order is precedence for the legacy
`busy_snapshot`, so appending preserves existing behaviour), three
`_PROGRESS_FIELDS` entries `{"current":"done","total":"total","label":"current"}`:

```python
JobAdapter("olof_fetching",     _get_olof_fetch_status,     "/api/olof/fetch/stop",     "/"),
JobAdapter("bobserve_fetching", _get_bobserve_fetch_status, "/api/bobserve/fetch/stop", "/"),
JobAdapter("ranker_scanning",   _get_ranker_scan_status,    "/api/ranker/scan/stop",    "/"),
```

`screen_route="/"` (ScreenHome) because the freshness card is these jobs' only
UI. StatusBar consumes `/api/activity` generically, so the only other
requirement is the `appShell.statusBar.activity.<kind>` locale keys.

**`DataFreshnessCard.tsx`** (decision 3) — a `RUNNABLE` map keyed by `step_id`
holding `{start, status?, stop?}` for the four steps. `HowToRun` gains a first
branch rendering a primary "Run" button; the existing `ROUTE_NAV_PREFIXES` ghost
button and the `<code>` + copy fallback are untouched.

- Confirm via the existing `ConfirmDialog` in `primitives.tsx`. Fetchers get one
  dialog naming the ~2 s/request politeness delay and expected duration.
  `ranker_scan` gets two options: default **"Scan backlog (N)"** →
  `{mode:'backlog'}`, secondary **"Full rescan"** → `{mode:'all'}` with a
  danger-toned warning. When the plan returns `config_changed`, the dialog must
  say the backlog run has become a full rescan.
- After a 2xx start: poll that step's status route every 2 s, show `done/total`
  and a Stop button in place of Run; when `running` flips false, re-fetch
  `/api/refresh/status` so the card self-updates. `ranker_rerank` is synchronous
  — await the POST, then re-fetch.
- 409 → inline warn pill; other non-2xx → an error string. The Phase 1
  render-null-on-initial-failure behaviour is unchanged.
- `version.state === 'changed'` appends a hint to the row's tooltip.

New `en.json` keys: `refresh.{run,stop,running,alreadyRunning,runFailed,
confirmFetch,confirmScanTitle,scanBacklog,scanAll,scanAllWarning,scanNoBacklog,
versionChanged}` plus the three `appShell.statusBar.activity.*`. Then
`/gui-next-i18n` for de/fr/es/it/nl.

**`tools/refresh_status.py`** — add a `VER` column (`ok`/`chg`/`—`); `how_to_run`
now prints routes for the four steps, which is the point.

---

## 4. Files touched

| File | Change |
|---|---|
| `backend/job_progress.py` | **new** — `JobState`, `JobStopped` |
| `backend/ranker_jobs.py` | **new** — scan thread, chunked cancel, rerank |
| `backend/config_version.py` | **new** — hashes, `STEP_VERSION_SOURCES`, stamping |
| `backend/olof_fetcher.py`, `backend/bobserve_fetcher.py` | progress/stop retrofit, interruptible sleeps, run-record |
| `backend/db.py` | `refresh_step_runs` DDL, `record_step_run()`, `_run_queued_write`, 3 `USER_META_KEYS` |
| `backend/refresh.py` | run-record + version signals, `_step_state` args, 5 registry edits |
| `backend/activity.py` | 3 wrappers, 3 `JobAdapter` rows, 3 `_PROGRESS_FIELDS` |
| `backend/app.py` | +8 routes, `record_step_run` in `/api/derived/recompute` |
| `run_backend.py` | `multiprocessing.freeze_support()` |
| `concert_ranker/cli.py` | promote `_collection_worklist`/`_rerank` to public names (private aliases kept) |
| `tools/refresh_status.py` | `VER` column |
| `gui_next/.../components/DataFreshnessCard.tsx` | Run/Stop, confirms, polling |
| `gui_next/.../locales/en.json` | new keys (+ `/gui-next-i18n`) |
| `tests/test_refresh.py` | run-record, version, route-existence tests; fixture cleanup |
| `tests/test_config_version.py`, `tests/test_pipeline_jobs.py` | **new** |
| `PROJECT.md`, `CHANGELOG.md`, `TODO.md` | reference sections + `/session-close` |

Build order: `job_progress` → `db` schema/helper → `config_version` → fetcher
retrofit → `ranker_jobs` → routes → `refresh.py` signals → activity → GUI.

---

## 5. Tests

**`tests/test_refresh.py` (additions).** Convert `_make_conn()` (`:35`) to a
`tmp_path` fixture with teardown — it leaks a `mkdtemp` per test today and this
phase roughly doubles the DB-touching tests in the file. Then: a run record newer
than the watermark wins and sets `last_run_source='run_record'`; an older one
loses; `ranker_rerank` gets a `last_run` purely from a record; a newest
`status='error'` row → stale "last run failed", cleared by a later `ok`;
`_step_state` truth table over `version_state ∈ {ok,changed,unstamped,n/a}`
(`changed` → stale at `backlog=0`; `unstamped` never downgrades); bidirectional
registry↔`STEP_VERSION_SOURCES` integrity; **route existence** — every
`how_to_run` starting `POST `/`GET ` resolves in `create_app().url_map` (catches
a typo'd route string on the card the day it is written); `record_step_run` then
`init_db()` again → one row, no error.

**`tests/test_config_version.py` (new).** Hash stability across calls and dict
insertion order; monkeypatching `db._KNOWN_TAPER_ALIASES` or a `_NOT_TAPER`
member changes the taper hash; changing `QUALITY_BANDS` changes the *rank* hash
and not the scan hash, and `BULK_SR` vice-versa (the whole justification for two
hashes); every name in both constant lists still exists in
`concert_ranker.config` (rename guard); `DISQUALIFIERS` serialises;
`version_state()` returns `unstamped` for a missing key.

**`tests/test_pipeline_jobs.py` (new)** — Flask `test_client`, everything
monkeypatched, zero network and zero audio. `JobState.try_begin` twice → False;
`sleep()` with the stop flag set returns in <0.5 s (the interruptible-wait
regression test); fetch routes 200 then 409, `/status` shows running, `/stop`
sets the flag; `_run_fetch_inner` with a `tmp_path` pages dir and a monkeypatched
`_fetch`, stopped after one page → partial summary with `stopped: True` and
exactly one `refresh_step_runs` row with `status='stopped'`; `plan_scan` backlog
reuse / `mode='all'` new scan / `config_json` mismatch forces a new scan / empty
backlog → `noop` with no thread; `/api/ranker/rerank` 409s during a scan;
`/api/derived/recompute` with trivial monkeypatched steps writes four rows with
the exact registry `step_id`s and stamps the taper version.

---

## 6. Verification

1. `.venv/bin/python3 -m pytest tests/test_refresh.py tests/test_config_version.py tests/test_pipeline_jobs.py -v`, then the targeted backend suite.
2. `/backend-restart`.
3. `POST /api/olof/fetch {"dry_run":true}` → `GET /api/olof/fetch/status` shows `running`/`total`/`stage`.
4. `POST /api/bobserve/fetch {"limit":2}` then immediately `/stop` — stops within ~3 s, not 30 s; `SELECT * FROM refresh_step_runs ORDER BY id DESC LIMIT 3` shows a `stopped` row.
5. `POST /api/ranker/scan {"mode":"backlog","workers":2}` — `planned` matches the card's backlog number; `/api/activity` shows `ranker_scanning`; `/stop` works; `/api/stats` stays responsive throughout (the non-blocking requirement).
6. `POST /api/ranker/rerank`, then `SELECT key,value FROM meta WHERE key LIKE 'refresh_version_%'` → three keys stamped.
7. Version signal end-to-end: run `/api/derived/recompute` once, add a `user_taper_aliases` row, re-`GET /api/refresh/status` → `attribute_tapers` is `stale` and the reason names the config change.
8. `.venv/bin/python3 tools/refresh_status.py` — reconcile with the route.
9. `/gui-check` (mandatory), then `/verify` Tier A on Home (the card gains buttons).
10. `/gui-next-i18n`.
11. `PROJECT.md`: routes section (+8), schema section (`refresh_step_runs`), module reference (3 new modules). Wiki touch-ups to `Collection-Pipeline.md` / `Concert-Ranker.md` via `/wiki-update`.
12. `/session-close`.

---

## 7. Residual risks

- **Write contention.** A scan opens up to 8 direct `repo.connect()` writers that
  bypass the backend write queue, concurrently with the fetchers' direct commits.
  Both sides are WAL with 30–60 s busy timeouts; keeping the server-side worker
  default at ≤8 (not the CLI's 16) is part of that margin.
- **Stop granularity.** Chunked cancel means up to `4 × workers` recordings keep
  scanning after Stop, and an in-flight `requests.get` gives up to 30 s of
  latency in the fetchers. Both go in the docstrings, and the GUI shows
  "stopping…" rather than implying instant.
- **Packaged builds are the untested path.** Decision 4 makes them safe
  (`freeze_support` + `workers=1`, no Pool), but nothing in CI exercises a frozen
  build. If a frozen scan ever misbehaves, the fallback is a 503.
- **`concert_ranker` name promotion.** Two private names become public with
  aliases. Small, but it is a `concert_ranker` change and the subdirectory has
  its own rules.

---

## 8. What Phase 2 deliberately does not do

- Does not chain steps in dependency order — Phase 3 reuses the `upstream`
  tuples for execution.
- Does not give human queues (taper conflicts, fingerprint suggestions, TapeMatch
  judgments) blocker treatment — Phase 4.
- Does not move the TapeMatch cron into the app (inventory open question 2 stays
  answered "cron, app reads its state").
- Does not add Run buttons for any step outside the four wrapped ones, and adds
  no button for a destructive or very expensive step without an explicit confirm
  (inventory §5 requirement 8).
