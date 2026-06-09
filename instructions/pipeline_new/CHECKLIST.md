# Pipeline v2 — Implementation Checklist

Track progress here. Check off each item as it is completed and committed.
Update "Last session" and "Resume from" at the end of every session.

**Last session:** —
**Resume from:** Phase 1 — Database Schema

---

## Phase 1 — Database Schema (`backend/db.py`)

- [ ] Add `collection_mounts` table (`CREATE TABLE IF NOT EXISTS`)
- [ ] Add `collection_routes` table (`CREATE TABLE IF NOT EXISTS`)
- [ ] Add index `idx_collection_routes_year` on `collection_routes(year)`
- [ ] Insert default `pipeline_file_mode = 'move'` into `meta` (`INSERT OR IGNORE`)
- [ ] Syntax check: `.venv/bin/python3 -m py_compile backend/db.py`
- [ ] Verify tables exist in live DB (SQLite shell or `/api/db/info`)

---

## Phase 2 — Backend Module (`backend/filer.py`)

- [ ] Create `backend/filer.py`
- [ ] `MOUNT_CHECK_TIMEOUT` module constant (default `2.0`)
- [ ] `normalise_path(raw: str) -> str` using `PurePosixPath.as_posix()`
- [ ] `_path_reachable(path, timeout) -> bool` (ThreadPoolExecutor + future.result — no bare `os.path.isdir`)
- [ ] `extract_year(date_str: str) -> int | None` (M/D/YY + M/D/YYYY, pivot 49)
- [ ] `resolve_route(year: int, db_path=None) -> dict | None`
- [ ] `preflight_check(folder_path, route) -> tuple[bool, str]`
- [ ] `file_folder(folder_path, route, mode='move', db_path=None) -> dict`
  - [ ] move branch (`shutil.move`)
  - [ ] copy branch (`shutil.copytree`)
  - [ ] call `write_rename_log()` on success
- [ ] Syntax check: `.venv/bin/python3 -m py_compile backend/filer.py`
- [ ] Manual smoke: file a test folder to a local path; verify move/copy + log entry

---

## Phase 3 — API Routes (`backend/app.py`)

- [ ] `GET /api/collection/mounts` — concurrent online checks (ThreadPoolExecutor, not serial)
- [ ] `POST /api/collection/mounts` — create; normalise `root_path` before insert
- [ ] `PUT /api/collection/mounts/<id>` — update; normalise `root_path` before insert
- [ ] `DELETE /api/collection/mounts/<id>` — 409 if any route references the mount
- [ ] `GET /api/collection/routes` — list joined with mount label
- [ ] `POST /api/collection/routes` — create route for a year
- [ ] `DELETE /api/collection/routes/<id>` — delete route
- [ ] `POST /api/pipeline/file` — file one folder; supports `dry_run=true`
- [ ] `POST /api/pipeline/file-all` — batch; independent error per folder
- [ ] All writes via `db_queue.execute()`
- [ ] Syntax check: `.venv/bin/python3 -m py_compile backend/app.py`
- [ ] curl smoke: `GET /api/collection/mounts` returns `{"mounts":[]}`
- [ ] curl smoke: create mount → create route → dry-run file → real file

---

## Phase 4 — Shared React Atoms (`gui_next`)

- [ ] `PipelineParts.tsx` — `StateGlyph`, `StatusTag`, `StageNode`, `StageTracker`, `StageStepper`, `QueueRow`
- [ ] `ConfirmDialog.tsx` — `useConfirm()` hook, `ConfirmDialogProvider`, danger/warn/info tones
- [ ] TypeScript compiles without errors (`npm run typecheck` in `gui_next/`)

---

## Phase 5 — Mounts & Routes Setup Card (`ScreenSetup.tsx`)

- [ ] "Collection Routing" section added to `ScreenSetup.tsx`
- [ ] Storage Mounts — list, add, edit, delete wired to API
- [ ] Year Routing — list, bulk-fill, coverage bar 1958–2026
- [ ] Filing Mode radio (move / copy) — reads/writes `pipeline_file_mode`
- [ ] Preview tester — dry-run call shows resolved destination
- [ ] TypeScript compiles without errors
- [ ] Manual test: add mount → add routes → coverage bar correct → delete route

---

## Phase 6 — Pipeline Screen Refactor (`ScreenPipeline.tsx`)

- [ ] Left queue rail (264px) — drag-drop zone + scrollable folder list
- [ ] Bucket filter bar — All / Needs you / Ready / Running / Shelf / Done
- [ ] Overview table — 5-dot `StageTracker`, LB#, row actions
- [ ] Virtual scroll retained (`@tanstack/react-virtual`)
- [ ] Bucket assignment logic (needs / ready / running / shelf / done)
- [ ] Detail panel — slide-in on row click
- [ ] `useFolderQueueStore` reused (not replaced)
- [ ] TypeScript compiles without errors
- [ ] Manual test: drag folder → queue → correct bucket assigned

---

## Phase 7 — Stage Detail Panels

- [ ] **VerifyStage** — `POST /api/pipeline/run {steps:["verify"]}`; generate checksums flow; re-verify button
- [ ] **LookupStage** — `POST /api/pipeline/run {steps:["lookup"]}`; candidate picker; mark-as-new
- [ ] **RenameStage** — dry-run then `POST /api/folder/rename`; before/after; edit mode
- [ ] **LBDIRStage** — `POST /api/pipeline/run {steps:["lbdir"]}`; reconcile + extras sections
- [ ] **CollectStage** — dry-run → RouteBox → confirm → `POST /api/pipeline/file`
  - [ ] `mute` state
  - [ ] `ready` state — RouteBox + "File into collection" button
  - [ ] `blocked` state — error card per code (`no_date`, `no_route`, `mount_offline`, `dest_exists`, `db_error`)
  - [ ] `filed` state — success card + "In collection" chip
- [ ] TypeScript compiles without errors
- [ ] Manual test: walk a real folder through all 5 stages end-to-end

---

## Phase 8 — Quick Lookup Screen

- [ ] `ScreenQuickLookup.tsx` created
- [ ] Paste input mode
- [ ] Clipboard button mode
- [ ] File drop zone (.md5 / .ffp)
- [ ] Results table: Checksum | Filename | LB# | Status
- [ ] Sidebar nav entry added (under Pipeline section)
- [ ] TypeScript compiles without errors
- [ ] Manual test: paste .md5 contents → correct LB# returned

---

## Phase 9 — Docs & Final Verification

- [ ] `CHANGELOG.md` — prepend Pipeline v2 + Step 5 entry
- [ ] `PROJECT.md` — add `collection_mounts`, `collection_routes` to schema table
- [ ] `PROJECT.md` — add 8 new routes to API route table
- [ ] `TODO.md` — close any pipeline v2 / collection TODO entries
- [ ] `tests/test_pipeline_smoke.py` passes — existing 4-step pipeline unbroken
- [ ] Full end-to-end: mount → routes → pipeline folder → all 5 steps → filed

---

## Session Log

| Date | Summary | Phases touched |
|------|---------|----------------|
| — | — | — |
