# FABLE spec — Unified activity center (FABLE_IDEAS, UI idea 4)

Written 2026-07-17 (Fable 5). Expands FABLE_IDEAS.md UI idea 4 into a handoff spec.
The app runs many long jobs — scrapes, scans, master installs, geocoding, recompute
chains — each with its own per-screen progress today. One persistent tray in the
status bar lists running/queued/finished jobs with progress, elapsed time, cancel
where supported, and click-through to the owning screen. Kills the "did that scan
finish?" screen-hopping; every future spec's job plugs into it for free.

**Read `instructions/SPEC_INTEGRATION_NOTES.md` first** (repo rule). No finding
amends this spec directly; the relevant contract is forward-looking — §A2's registry
is the plug-in point the idea promised future SSE endpoints ("plugs into it for
free"), so later specs must register jobs instead of inventing new progress plumbing.

**The one rule:** the activity center *observes* jobs, it never owns them. Every
existing start/stop/status flow keeps working untouched; the tray is a second reader,
so a half-shipped activity center can never break a scrape or an install.

---

## 1. Job inventory (verified against backend/app.py + AppShell.tsx, 2026-07-17)

Two progress styles exist today, and the design must unify both:

### 1a. Polled background workers (thread + module status fn + GET status route)

`GET /api/activity/busy` (app.py:612) already aggregates 11 of them into
`{busy, activity}` — the status-bar dot polls it at 5 s (`BUSY_POLL_MS`,
AppShell.tsx). Its adapter list is the seed for this spec; note the shape split it
already handles (`{"running": bool}` workers vs `{"status": "idle|running"}` workers).

| Worker (status fn) | Status route | Cancel route | Owning screen |
|---|---|---|---|
| importer import | `/api/db/import/status` | — | Setup |
| site scraper | `/api/scrape/status` | `/api/scrape/stop` | Scraper |
| bootleg scraper | `/api/bootlegs/scrape/status` | — | Bootlegs |
| integrity scan | `/api/collection/integrity/scan/status` | `…/scan/cancel` | Collection |
| filer job | `/api/pipeline/file/status` | — | Pipeline |
| site crawler | `/api/crawler/status` | `/api/crawler/stop` | Scraper |
| geocoder | `/api/geocode/status` | `/api/geocode/stop` | Map |
| bobdylan scraper | `/api/bobdylan/status` | `/api/bobdylan/stop` | Scraper |
| setlist.fm sync | `/api/setlistfm/status` | `/api/setlistfm/stop` | Scraper |
| app update | `/api/update/status` | — | Setup |
| data download | `/api/data/download/status` | — | Setup |

**Missing from `activity/busy` today** (gaps the jobs endpoint must close):
spectrogram batch (`/api/spectrogram/status` + `/stop`), tapematch crawl
(`/api/tapematch/crawl/status` + `/stop`), pipeline run (`/api/pipeline/run/status`
+ `/cancel`, `_PIPELINE_JOB`), archive.org (`/api/archive_org/status` + `/stop`),
collection-size background compute (home_stats `computing` flag — display-only,
no route of its own; fold in only if trivial).

### 1b. Request-scoped SSE streams (progress exists only inside the HTTP response)

`POST` routes streaming `text/event-stream`, read via `resp.body.getReader()` in the
initiating screen (OnboardingWizard.tsx, ScreenSetup.tsx): `/api/master/import`,
`/api/master/github_release`, `/api/master/github_install`,
`/api/sitedata/github_release`, `/api/sitedata/github_install`,
`/api/derived/recompute`, `/api/wtrf/crawl_missing`. (Implementer: re-grep
`text/event-stream` in app.py for the authoritative list — it grows.)
If the user navigates away mid-stream, progress is invisible until done. These jobs
have **no** status route and **no** cancel; the registry (§A2) gives them presence.

Existing i18n: `appShell.statusBar.activity.*` keys (en.json:69) already name the
11 polled workers — reuse them as job labels; add keys only for the new workers
and the tray chrome.

---

## 2. Target design

### A1 — Backend aggregator: one module, one normalized shape

New `backend/activity.py`. A declarative adapter table maps each 1a worker to a
normalized record — the same table `activity_busy` reads today, so busy and jobs
can never drift:

```
JOB_ADAPTERS: list of (kind, status_getter, cancel_route|None, screen_route)
```

`GET /api/activity/jobs` → snapshot, no server-side polling loop (every status fn is
a synchronous in-memory read, same as activity_busy does now):

```
{
  busy: bool,
  jobs: [{
    id,                      // kind for singleton workers; kind+start-ts for §A2
    kind,                    // i18n key suffix, e.g. 'scraping', 'geocoding'
    state,                   // 'running' | 'done' | 'error' | 'cancelled'
    progress?: {current?, total?, pct?, label?},   // whatever the worker exposes
    started_at?, finished_at?,
    cancel_route?: str,      // POST-able as-is, or absent
    screen: str              // gui_next router path, e.g. '/scraper'
  }]
}
```

Per-worker field mapping lives in the adapter (each status dict differs — that's
the point of normalizing once). `progress` is best-effort: omit fields the worker
doesn't track, never fake them.

`/api/activity/busy` is **re-implemented on top of the same adapter table** and its
response shape `{busy, activity}` is unchanged (AppShell is its only consumer —
verified). Closing the 1a gaps therefore also fixes the busy dot's blind spots (D-3).

**Finished-job history:** in-memory ring buffer (module constant, 50 entries) fed by
a state-transition check inside the snapshot call (running→idle edge = job
finished). Restart clears it — acceptable; the integrity scan keeps its own
persistent history route.

### A2 — SSE tee registry: presence for request-scoped jobs

Small thread-safe registry in the same module:
`track(kind, label) -> ctx manager`; inside the generator, `update(progress)` on
each yielded progress event; exit sets done/error. Each 1b route wraps its existing
generator — the streamed response to the initiating screen is **unchanged** (tee,
not redirect; the one rule). Registered jobs appear in `/api/activity/jobs` with
ids like `master_install-1721224512`, no cancel_route.

This is the contract future specs use: any new long job either gets a 1a adapter
row or wraps its generator in `track()`. One line either way.

### A3 — GUI tray: status-bar popover, adaptive poll

- The activity segment of `StatusBar` (AppShell.tsx) becomes a clickable trigger:
  collapsed it shows what it shows today (idle text or dot + first activity), plus
  a count when >1 job runs ("2 jobs…").
- Click → popover panel (anchored above the status bar, same layer pattern as
  existing menus): running jobs first (label, progress bar or indeterminate shimmer,
  elapsed time), then recent finished/error jobs (dimmed, with state icon).
- Row actions: **Stop** (POSTs `cancel_route`, then confirm via next poll — no
  optimistic state) and **click-through** (`useNavigate()` to `screen`, close
  popover).
- Polling: one shared store (`lib/activityStore.ts`, existing `*Store.ts` pattern)
  replaces the inline poller in StatusBar. Cadence 5 s idle → 2 s while any job is
  running, back off on idle. All consumers read the store; StatusBar stays the only
  poller.
- Completion signalling: state-change to `error` bumps a badge on the tray trigger
  (cleared on open). No toasts (D-2 default) — the tray is calm infrastructure, not
  a notification system.

### A4 — Explicitly out of scope

Queueing/scheduling (the tray shows queued state only if a worker already exposes
it), job persistence across restarts, per-job log streaming into the tray (click
through to the owning screen for logs), and touching any worker's own start/stop
logic. Also no Electron OS notifications — revisit only if tj asks.

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 tray surface** — default: popover anchored to the status-bar activity
  segment (A3). Alternative: floating bottom-corner card stack.
- **D-2 completion notifications** — default: error badge only, no toasts.
  Alternative: toast on every completion.
- **D-3 busy-dot scope widens** — re-basing `activity/busy` on the adapter table
  makes the dot see spectrogram/tapematch-crawl/pipeline/archive.org jobs it
  currently misses. Default: yes, that's a fix. Say so if the old scope mattered.
- **D-4 history depth** — default: last 50 finished jobs, memory-only.

---

## 4. Work bites (handoff units — commit each separately)

Implementation tier: sonnet per agent policy; allocate the TODO id at the first
implementation session per repo numbering rules (one TODO for the whole spec, bites
tracked in-spec). Backend restart before verifying any backend bite (repo rule).

### B1 — Aggregator module + jobs route + busy re-base (M)
`backend/activity.py` (adapter table, snapshot, ring buffer), `GET
/api/activity/jobs` in app.py, `/api/activity/busy` re-implemented on the table
(response shape byte-compatible). Include the 1a gap workers. Tests
`tests/test_activity.py` with monkeypatched status fns: (i) normalization per shape
family, (ii) busy parity with old semantics + gap workers, (iii) running→finished
edge lands in history, (iv) a worker whose status fn raises is skipped, never 500s.
**Accept:** route returns normalized jobs while a real scrape runs; tests green.

### B2 — SSE tee registry + wrap streamed routes (S) — after B1
`track()`/`update()` in activity.py; wrap every `text/event-stream` generator found
by grep (§1b list). No change to streamed payloads (verify one route's stream
byte-identical before/after). Test: tracked generator appears in jobs while
mid-stream, flips to done/error after.
**Accept:** a master github_install shows in `/api/activity/jobs` mid-run.

### B3 — GUI tray + store + i18n (M) — after B1 (B2 optional but preferred first)
`lib/activityStore.ts`, StatusBar trigger + popover in AppShell.tsx, cancel wiring,
`useNavigate` click-through. Reuse `appShell.statusBar.activity.*` labels; new keys
for gap workers + tray chrome; run `/gui-next-i18n`.
**Accept:** `/gui-check` PASS; tray lists a live job with elapsed time; Stop ends a
cancellable job; click-through lands on the owning screen. (No screenshots — repo
rule; tj verifies visuals.)

### B4 — Docs (XS) — last
PROJECT.md: new route in the API table, `backend/activity.py` in the file tree,
note on `/api/activity/busy` re-base; CHANGELOG per session-close.

Order: B1 → B2 → B3 → B4.

---

## 5. Definition of done

1. One click on the status bar answers "what is running, how far along, and did
   anything finish or fail since I last looked" — for every 1a worker (including
   today's blind spots) and every 1b stream.
2. No existing flow regressed: each screen's own progress UI, every start/stop
   route, and the `activity/busy` response shape behave exactly as before
   (busy's *coverage* widens per D-3; that is the only semantic change).
3. Cancellable jobs can be stopped from the tray; job rows navigate to their
   owning screen.
4. A worker or stream added later needs exactly one adapter row or one `track()`
   wrapper to appear in the tray — documented in a short "adding a job" note at
   the top of `backend/activity.py`.
5. Backend tests + `/gui-check` green; locales updated; PROJECT.md updated.
