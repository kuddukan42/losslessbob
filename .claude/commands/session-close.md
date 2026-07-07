---
description: End-of-session bookkeeping — CHANGELOG entry, BUGS/TODO moves with correct numbering, PROJECT.md change-log row, consistency check
---

# session-close — Mandatory bookkeeping, done consistently

Perform the repo's required end-of-session file updates for everything changed
this session. This skill is the single source of truth for entry formats and
numbering; apply them completely and consistently.

## Step 1 — Inventory what actually changed

- `git status --short` and `git diff --stat` for files touched.
- From the session itself: bugs found/fixed, TODOs completed/created,
  schema/route/structure changes, user-facing string changes.
- Anything already logged earlier in the session (check the top of
  CHANGELOG.md) must not be double-logged — extend the existing entry instead.

## Step 2 — CHANGELOG.md

Prepend one entry (skip if this session's entry already exists — then extend it):

```
[YYYY-MM-DD] — <summary>
Changed: <file>: <what/why>
Fixed: <file>: <bug + fix>        (if applicable)
Added: <file>: <new capability>   (if applicable)
```

## Step 3 — BUGS.md / BUGS_DONE.md

- **Next free number** = max `BUG-<NNN>` across **both** files + 1. Verify with:
  ```bash
  grep -ho "BUG-[0-9]*" BUGS.md BUGS_DONE.md | sort -t- -k2 -n | tail -1
  ```
- Entry format:
  ```
  BUG-<NNN>: <title>
  Status: Open | Fixed | Wontfix
  File(s): <file:line>
  Reported: YYYY-MM-DD
  Fixed: YYYY-MM-DD
  Root cause: ...
  Fix: ...
  ```
- New bug discovered → add as `Status: Open` to BUGS.md.
- Bug fixed this session → fill `Fixed:` date, `Root cause:`, `Fix:`, and
  **move the whole entry to the top of BUGS_DONE.md** (remove from BUGS.md).

## Step 4 — TODO.md / TODO_DONE.md

- Same numbering rule across TODO.md + TODO_DONE.md (`TODO-<NNN>`).
- Entry format:
  ```
  TODO-<NNN>: <title>
  Priority: High | Medium | Low
  Status: Open | In Progress | Done | Cancelled
  Added: YYYY-MM-DD
  Closed: YYYY-MM-DD
  Description: ...
  ```
- New task → TODO.md with Priority/Status/Added/Description.
- Done or cancelled → set `Closed:` date and move to top of TODO_DONE.md.

## Step 5 — PROJECT.md (only if applicable)

Update the relevant section if any of these changed: file structure, DB
schema, Flask routes, GUI screens/tabs, dependencies. Then add a row to the
`## Change Log` table (newest first):

```
| YYYY-MM-DD | <one-row summary, dense prose, backtick file/route/table names> |
```

## Step 6 — Cross-cutting reminders

- User-facing GUI strings changed → locale files must be updated
  (`/gui-next-i18n` for gui_next, `/i18n-update` for legacy gui/). Flag it if
  not yet done.
- Dependency changed → `requirements.txt` (pinned exact version) + PROJECT.md.

## Step 7 — Consistency check + report

Verify before finishing:
- No BUG/TODO number used twice across the four files.
- Every `Fixed`/`Done` item this session appears in a `*_DONE.md`, not the
  open file.
- All dates are today's actual date.

Report as a single table: `File | Action taken` (or "no change needed"), plus
the BUG/TODO numbers assigned this session.
