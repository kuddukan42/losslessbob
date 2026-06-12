# LosslessBob — Pipeline v2 Implementation Plan

Generated: 2026-06-07

---

## Overview

This document describes how to implement the Pipeline v2 workspace and the new **Step 5: File into Collection** feature. The design specs in this folder replace the current flat-table pipeline screen with a master/detail workspace and add a new backend filing system for routing finished recordings to named storage mounts.

### What changes

| Area | Current state | Target state |
|------|--------------|-------------|
| Pipeline screen | Flat table, 4 steps, severity grouping | Master/detail, 5 steps, bucket grouping |
| Folder detail | Expandable row with mini-panel | Full detail panel with per-stage sub-panels |
| Step 5 (Collect) | Does not exist | File into collection mount, log to rename_history |
| Setup | No collection config | Mounts & Routes card in ScreenSetup |
| Quick Lookup | Not implemented | Standalone checksum-to-LB screen |
| DB schema | checksums, entries, lb_master, rename_history | + collection_mounts, collection_routes |
| Backend | 4-step `_pipeline_process_folder()` | + filer.py, 8 new API routes |

---

## Source Files (this folder)

| File | Purpose |
|------|---------|
| `CC_PIPELINE_FILE.md` | Authoritative spec for Step 5: DB schema, filer.py pseudocode, 8 API routes, implementation checklist |
| `pipeline2-app.jsx` | Main workspace React layout (master/detail, bucket filter, overview table, queue rail) |
| `pipeline2-stages.jsx` | 5 stage-detail panels (Verify, Lookup, Rename, LBDIR, Collect) |
| `collect-states.jsx` | Step 5 visual states: mute / ready / blocked (5 error codes) / filed |
| `mounts-routes.jsx` | Setup UI — Storage Mounts CRUD, Year Routing table, Filing Mode radio |
| `pipeline2-parts.jsx` | Shared atoms: StateGlyph, StageTracker, StageStepper, QueueRow — **production-ready** |
| `pipeline2-confirm.jsx` | Promise-based confirmation dialog (danger/warn/info tones) — **production-ready** |
| `pipeline2-shell.jsx` | App shell & sidebar nav with collapsible advanced-tools section |
| `pipeline2-quicklookup.jsx` | Standalone paste/file checksum lookup utility |

---

## Existing Code to Reuse

| Symbol | File | Notes |
|--------|------|-------|
| `_pipeline_process_folder()` | `backend/app.py:4733` | Existing 4-step engine; Step 5 is additive |
| `write_rename_log()` | `backend/rename.py` | Use for Step 5 reversibility logging |
| `parse_checksum_text()` | `backend/db.py` | Reuse for Quick Lookup screen |
| `lookup_checksums()` | `backend/db.py` | Reuse for Quick Lookup screen |
| `build_standard_name()` | `backend/folder_naming.py` | Already used in rename step |
| `DatabaseWriteQueue` | `backend/db_queue.py` | All new DB mutations must go through this |
| `useFolderQueueStore` | `gui_next/src/renderer/src/` | Shared queue state — reuse, don't replace |
| `ScreenPipeline.tsx` | `gui_next/.../screens/ScreenPipeline.tsx` | Major refactor in-place (61 KB) |
| `ScreenSetup.tsx` | `gui_next/.../screens/ScreenSetup.tsx` | Add Collection Routing card |

---

## Implementation Phases

Work through these phases in order. Each phase is independently testable.

---

### Phase 1 — Database Schema

**File:** `backend/db.py`

Add two new tables and a meta key. Use `CREATE TABLE IF NOT EXISTS` and wrap any `ALTER TABLE` in try/except for idempotency (existing pattern in db.py).

```sql
CREATE TABLE IF NOT EXISTS collection_mounts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    label     TEXT NOT NULL UNIQUE,
    root_path TEXT NOT NULL,
    notes     TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collection_routes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    year       INTEGER NOT NULL UNIQUE,
    mount_id   INTEGER NOT NULL REFERENCES collection_mounts(id),
    sub_path   TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_collection_routes_year ON collection_routes(year);
```

Also insert default `pipeline_file_mode` into the `meta` table:
```sql
INSERT OR IGNORE INTO meta (key, value) VALUES ('pipeline_file_mode', 'move');
```

**Acceptance:** `python3 -m py_compile backend/db.py` passes; tables visible in SQLite shell.

---

### Phase 2 — Backend Module: filer.py

**File:** `backend/filer.py` (new file)

Implement the four functions described in `CC_PIPELINE_FILE.md`. Key logic:

**Year extraction** (`extract_year(date_str: str) -> int | None`):
- Parse M/D/YY and M/D/YYYY formats from the `entries.date_str` column
- Century pivot: YY ≤ 49 → 2000s, YY > 49 → 1900s
- Return `None` if unparseable

**Route resolution** (`resolve_route(year: int, db_path=None) -> dict | None`):
- Query `collection_routes JOIN collection_mounts` for the given year
- Return `{mount_id, label, root_path, sub_path, resolved_path}` or `None`

**Path normalisation** — all `root_path` values must be normalised to POSIX forward-slash strings
before writing to the DB, and resolved back via `pathlib.Path` on read. This ensures stored paths
are portable if the app ever runs on Windows (UNC paths, drive letters).

```python
from pathlib import Path, PurePosixPath

def normalise_path(raw: str) -> str:
    """Store paths as POSIX strings; pathlib resolves them correctly on any OS."""
    return PurePosixPath(Path(raw)).as_posix()
```

Apply `normalise_path()` in the POST/PUT mount routes before inserting into the DB.

**Mount online check** — use a short-timeout thread so an unreachable NAS or Windows UNC path
(`\\server\share`) cannot block the Flask thread for 20–30 seconds:

```python
import concurrent.futures

_MOUNT_TIMEOUT = 2.0  # seconds

def _path_reachable(path: str) -> bool:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(os.path.isdir, path)
        try:
            return future.result(timeout=_MOUNT_TIMEOUT)
        except concurrent.futures.TimeoutError:
            return False
```

**Pre-flight checks** (`preflight_check(folder_path, route) -> tuple[bool, str]`):
- Check mount online: `_path_reachable(route['root_path'])` (not bare `os.path.isdir`)
- Check destination free: `not os.path.exists(dest_path)`
- Return `(True, '')` or `(False, error_code)` where error_code is one of:
  `no_date | no_route | mount_offline | dest_exists | db_error`

**File folder** (`file_folder(folder_path, route, mode='move', db_path=None) -> dict`):
- Run pre-flight; abort if failed
- `mode='move'` → `shutil.move()`; `mode='copy'` → `shutil.copytree()`
- On success: call `write_rename_log()` (from `backend/rename.py`) for reversibility
- Return `{success, dest_path, mode, error_code?}`

**Acceptance:** `python3 -m py_compile backend/filer.py` passes; unit test with a temp folder.

---

### Phase 3 — API Routes

**File:** `backend/app.py` (append after existing pipeline routes, ~line 5050)

Add 8 routes as specified in `CC_PIPELINE_FILE.md` section 5:

| Method | Route | Body | Returns |
|--------|-------|------|---------|
| GET | `/api/collection/mounts` | — | `{mounts: [...]}` |
| POST | `/api/collection/mounts` | `{label, root_path, notes?}` | `{mount}` |
| PUT | `/api/collection/mounts/<id>` | `{label?, root_path?, notes?}` | `{mount}` |
| DELETE | `/api/collection/mounts/<id>` | — | 409 if routes reference it |
| GET | `/api/collection/routes` | — | `{routes: [...]}` |
| POST | `/api/collection/routes` | `{year, mount_id, sub_path?}` | `{route}` |
| DELETE | `/api/collection/routes/<id>` | — | `{ok}` |
| POST | `/api/pipeline/file` | `{folder, lb_number, dry_run?, mode?}` | `{success, dest_path, error_code?}` |
| POST | `/api/pipeline/file-all` | `{folders: [{folder, lb_number}], mode?}` | `{results: [...]}` |

All writes go through `db_queue.execute()`. The `dry_run=true` path runs pre-flight only — no filesystem changes.

`GET /api/collection/mounts` must check online status for all mounts concurrently (not serially)
using `concurrent.futures.ThreadPoolExecutor` with the `_path_reachable()` helper — never call
`os.path.isdir()` sequentially on multiple mounts in a request handler.

```python
with concurrent.futures.ThreadPoolExecutor(max_workers=len(mounts)) as ex:
    online_flags = list(ex.map(lambda m: _path_reachable(m['root_path']), mounts))
for mount, online in zip(mounts, online_flags):
    mount['online'] = online
```

**Acceptance:** `curl -s localhost:5174/api/collection/mounts` returns `{"mounts":[]}` with empty DB; adding a mount with an offline path returns `"online": false` within 3 seconds.

---

### Phase 4 — Shared React Atoms

**Target:** `gui_next/src/renderer/src/components/pipeline/`

Port these two files from JSX to TypeScript — they are already production-ready logic-wise, just need type annotations:

- `pipeline2-parts.jsx` → `PipelineParts.tsx`
  - Export: `StateGlyph`, `StatusTag`, `StageNode`, `StageTracker`, `StageStepper`, `QueueRow`
- `pipeline2-confirm.jsx` → `ConfirmDialog.tsx`
  - Export: `useConfirm()` hook + `ConfirmDialogProvider`

Use the existing CSS variable system (`--lbb-*-bar`, `--lbb-*-bg`) already in the theme.

**Acceptance:** Components render without errors in Storybook or a test page.

---

### Phase 5 — Mounts & Routes Setup Card

**File:** `gui_next/src/renderer/src/screens/ScreenSetup.tsx`

Add a new "Collection Routing" section based on `mounts-routes.jsx`. Three subsections:

1. **Storage Mounts** — fetch `GET /api/collection/mounts`, CRUD via PUT/POST/DELETE
2. **Year Routing** — fetch `GET /api/collection/routes`, bulk-fill control, coverage bar 1958–2026
3. **Filing Mode** — read/write `pipeline_file_mode` from meta (existing `/api/settings` or meta route)

The coverage bar renders a 1px-wide colored column per year — red if no route, green if routed. Implement as a simple flex row of 69 divs.

The preview tester fires `POST /api/pipeline/file` with `dry_run: true` and a typed year (construct a fake `date_str`).

**Acceptance:** Can add a mount, add routes for 1966–1970, see them in the coverage bar, and delete a route.

---

### Phase 6 — Pipeline Screen Refactor

**File:** `gui_next/src/renderer/src/screens/ScreenPipeline.tsx` (major in-place refactor)

Replace the current flat-table layout with the master/detail design from `pipeline2-app.jsx`.

**New layout:**
```
┌─────────────────────────────────────────────────────────┐
│  [Bucket filter bar: All · Needs you · Ready · Running · Shelf · Done]  │
├──────────────┬──────────────────────────────────────────┤
│ Queue Rail   │  Overview Table                          │
│ (264px)      │  folder | 1·2·3·4·5 | LB# | actions     │
│ drag-drop    │  (virtual scroll)                        │
│ folder list  │                                          │
│              │  ─────── selected folder ────────────── │
│              │  Detail Panel (slide-in from right)      │
└──────────────┴──────────────────────────────────────────┘
```

**Bucket logic** (maps folder state to filter group):
- `needs` — any step is `action` (requires user decision)
- `ready` — all prior steps pass, next step can auto-run
- `running` — a step is currently executing
- `shelf` — rename done, awaiting LBDIR reconciliation or collection filing
- `done` — all 5 steps pass

Reuse `useFolderQueueStore` for the folder list. The 5-dot stage tracker uses `StageTracker` from Phase 4.

**Acceptance:** Drag a folder onto the window; it appears in the queue rail and overview table with correct bucket assignment.

---

### Phase 7 — Stage Detail Panels

**File:** `gui_next/src/renderer/src/screens/ScreenPipeline.tsx` (or extract to `components/pipeline/stages/`)

Port the 5 panels from `pipeline2-stages.jsx` and wire real API calls:

| Stage | API call | User action |
|-------|----------|-------------|
| Verify | `POST /api/pipeline/run {steps:["verify"]}` | "Generate checksums" if missing |
| Lookup | `POST /api/pipeline/run {steps:["lookup"]}` | Candidate picker → pin LB# |
| Rename | `POST /api/pipeline/run {steps:["rename"]}` then `POST /api/folder/rename` | Confirm rename |
| LBDIR | `POST /api/pipeline/run {steps:["lbdir"]}` | "Apply moves" for reconcile section |
| Collect | `POST /api/pipeline/file {dry_run:true}` then confirm → `POST /api/pipeline/file` | "File into collection" |

The Collect stage renders states from `collect-states.jsx`:
- **mute** — prior steps not all pass
- **ready** — pre-flight passed; show RouteBox with staging → destination
- **blocked** — show error card with `error_code` from one of: `no_date`, `no_route`, `mount_offline`, `dest_exists`, `db_error`
- **filed** — show success card with mount name and "In collection" chip

**Acceptance:** Opening a fully-verified folder shows all 5 stages with correct states; clicking "File into collection" moves the folder and shows the `filed` state.

---

### Phase 8 — Quick Lookup Screen

**File:** `gui_next/src/renderer/src/screens/ScreenQuickLookup.tsx` (new file)

Port `pipeline2-quicklookup.jsx` to TypeScript. Three input modes:
- **Paste** — textarea accepts raw checksum text
- **Clipboard** — reads clipboard on button click
- **.md5/.ffp drop** — file drop zone

On submit, call `POST /api/lookup/checksums` (existing route) with the raw text. Render results table: Checksum | Filename | LB# | Status.

Add route entry in the sidebar nav under the Pipeline section (from `pipeline2-shell.jsx`).

**Acceptance:** Paste a .md5 file's contents; matched entries show LB# and status.

---

### Phase 9 — Documentation & Verification

After all phases pass:

1. **`CHANGELOG.md`** — prepend entry:
   ```
   [2026-MM-DD] — Pipeline v2 + Step 5 (File into Collection)
   Added: backend/filer.py: year extraction, route resolution, move/copy filing
   Added: backend/app.py: 8 new /api/collection/* and /api/pipeline/file routes
   Added: backend/db.py: collection_mounts, collection_routes tables
   Changed: gui_next/.../ScreenPipeline.tsx: master/detail layout, 5-stage tracker, bucket groups
   Added: gui_next/.../ScreenSetup.tsx: Collection Routing card (Mounts, Year Routes, Filing Mode)
   Added: gui_next/.../ScreenQuickLookup.tsx: standalone checksum lookup
   ```

2. **`PROJECT.md`** — add `collection_mounts` and `collection_routes` to the DB schema table; add 8 new routes to the API route table.

3. **`TODO.md`** — close any TODO entries this satisfies (check for pipeline v2 and collection items).

4. **Smoke test** — run `tests/test_pipeline_smoke.py` to confirm existing 4-step pipeline is unbroken.

---

## File Change Summary

| Action | Path |
|--------|------|
| Create | `backend/filer.py` |
| Modify | `backend/db.py` — 2 tables + meta key |
| Modify | `backend/app.py` — 8 new routes |
| Create | `gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx` |
| Create | `gui_next/src/renderer/src/components/pipeline/ConfirmDialog.tsx` |
| Modify | `gui_next/src/renderer/src/screens/ScreenPipeline.tsx` |
| Modify | `gui_next/src/renderer/src/screens/ScreenSetup.tsx` |
| Create | `gui_next/src/renderer/src/screens/ScreenQuickLookup.tsx` |
| Update | `CHANGELOG.md`, `PROJECT.md`, `TODO.md` |

---

## Pitfalls & Notes

- **DB writes** — all new mutations must go through `DatabaseWriteQueue` (`db_queue.execute()`), not direct sqlite3 calls.
- **Idempotent migrations** — use `CREATE TABLE IF NOT EXISTS`; wrap ALTER TABLE in try/except as done elsewhere in db.py.
- **Century pivot** — year extraction uses 49 as pivot: `20XX` if YY ≤ 49, `19XX` if YY > 49. Matches the existing `folder_naming.py` behavior.
- **Move vs copy** — filing mode is stored in `meta` table and can be overridden per-request. The UI default is "move".
- **30-day reversibility** — use `write_rename_log()` from `backend/rename.py` after every successful file operation.
- **Mount delete guard** — `DELETE /api/collection/mounts/<id>` must return 409 if any route references the mount; delete routes first.
- **Port 5174** — hardcoded everywhere; do not change it.
- **Virtual scroll** — the overview table uses `@tanstack/react-virtual` (already in ScreenPipeline.tsx); keep it.
- **Restart backend** — after any `backend/` change, restart the Flask server before testing; stale process is a common false negative.

### Cross-platform mount compatibility (Windows + Linux)

These two fixes are **required** — implement them in Phase 2 and Phase 3, not as an afterthought:

**1. Path normalisation (Windows ↔ Linux portability)**
- All `root_path` values are normalised to POSIX forward-slash strings (`PurePosixPath.as_posix()`) before DB insert.
- On read, resolve via `pathlib.Path(stored_posix)` — Python translates to the host OS separator automatically.
- This means `\\NAS\archive` is stored as `//NAS/archive` and resolved correctly on both OSes.
- Apply in POST/PUT mount route handlers. Never store raw user input directly.

**2. Mount online check with timeout (prevents Flask thread hang)**
- `os.path.isdir()` on a dead Windows UNC path (`\\server\share`) can block for 20–30 seconds.
- Use `_path_reachable(path, timeout=2.0)` (ThreadPoolExecutor + `future.result(timeout=)`) everywhere mount reachability is tested — in `preflight_check()` and in `GET /api/collection/mounts`.
- For the list endpoint, fan out checks concurrently across all mounts, not serially.
- The 2-second timeout is configurable via a `MOUNT_CHECK_TIMEOUT` module constant in `filer.py`.
