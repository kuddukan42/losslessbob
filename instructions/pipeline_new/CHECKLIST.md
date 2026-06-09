# Pipeline v2 — Implementation Checklist

Track progress here. Check off each item as it is completed and committed.
Update "Last session" and "Resume from" at the end of every session.

**Last session:** 2026-06-09
**Resume from:** Phase 6 — Pipeline Screen Refactor

---

## Phase 1 — Database Schema (`backend/db.py`)

- [x] Add `collection_mounts` table (`CREATE TABLE IF NOT EXISTS`)
- [x] Add `collection_routes` table (`CREATE TABLE IF NOT EXISTS`)
- [x] Add index `idx_routes_mount` on `collection_routes(mount_id)`
- [x] Insert default `pipeline_file_mode = 'move'` into `meta` (`INSERT OR IGNORE`)
- [x] Syntax check: `.venv/bin/python3 -m py_compile backend/db.py`
- [x] Add DB helper functions: get/add/update/delete collection_mounts, get/upsert/delete collection_routes

---

## Phase 2 — Backend Module (`backend/filer.py`)

- [x] Create `backend/filer.py`
- [x] `MOUNT_CHECK_TIMEOUT` module constant (default `2.0`)
- [x] `normalise_path(raw: str) -> str` using `PurePosixPath.as_posix()`
- [x] `_path_reachable(path, timeout) -> bool` (ThreadPoolExecutor + future.result — no bare `os.path.isdir`)
- [x] `year_from_date_str(date_str: str) -> int | None` (M/D/YY + M/D/YYYY, pivot 49)
- [x] `resolve_destination_for_lb(lb_number, folder_path, db_path) -> dict`
- [x] `file_folder(lb_number, folder_path, file_mode, db_path) -> dict`
  - [x] move branch (`shutil.move`)
  - [x] copy branch (`shutil.copytree`)
  - [x] registers in my_collection on success
- [x] Syntax check: `.venv/bin/python3 -m py_compile backend/filer.py`

---

## Phase 3 — API Routes (`backend/app.py`)

- [x] `GET /api/collection/mounts` — concurrent online checks (ThreadPoolExecutor, not serial)
- [x] `POST /api/collection/mounts` — create; normalise `root_path` before insert
- [x] `PATCH /api/collection/mounts/<id>` — update; normalise `root_path` before insert
- [x] `DELETE /api/collection/mounts/<id>` — 409 if any route references the mount
- [x] `GET /api/collection/routes` — list joined with mount label
- [x] `POST /api/collection/routes/bulk` — upsert year range
- [x] `DELETE /api/collection/routes/<year>` — delete route
- [x] `GET /api/collection/routes/preview/<year>` — dry-run resolve
- [x] `POST /api/pipeline/file` — file folder(s); independent per-folder errors
- [x] `POST /api/pipeline/file/preview` — pre-flight resolve
- [x] `pipeline_file_mode` added to `db_settings()` keys
- [x] Step 5 in `_pipeline_process_folder` + `_file_blocked_label` helper
- [x] Syntax check: `.venv/bin/python3 -m py_compile backend/app.py`
- [ ] curl smoke: `GET /api/collection/mounts` returns `{"mounts":[]}`
- [ ] curl smoke: create mount → create route → dry-run file → real file

---

## Phase 4 — Shared React Atoms (`gui_next`)

- [x] `PipelineParts.tsx` — `StateGlyph`, `StatusTag`, `StageNode`, `StageTracker`, `StageStepper`, `QueueRow`
- [x] `ConfirmDialog.tsx` — `useConfirm()` hook, `ConfirmDialogProvider`, danger/warn/info tones
- [x] TypeScript compiles without errors

---

## Phase 5 — Mounts & Routes Setup Card (`ScreenSetup.tsx`)

- [x] "Collection Routing" section added to `ScreenSetup.tsx` as `CollectionRoutingCard`
- [x] Storage Mounts — list, add, edit, delete wired to API
- [x] Year Routing — bulk-fill, collapsible per-mount route table, coverage bar 1958–2026
- [x] Filing Mode radio (move / copy) — reads/writes `pipeline_file_mode`
- [x] Preview tester — local resolve from loaded data
- [x] TypeScript compiles without errors
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
| 2026-06-09 | Branch created. DB schema, filer.py, all API routes, PipelineParts + ConfirmDialog, CollectionRoutingCard in ScreenSetup | 1–5 |
