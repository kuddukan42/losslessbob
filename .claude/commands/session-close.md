---
description: End-of-session bookkeeping — CHANGELOG entry, BUGS/TODO moves via tools/ledger.py, PROJECT.md reference-section updates, consistency check
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

All bug ledger moves go through `tools/ledger.py` — it handles numbering,
formatting, and moving entries between the open/done files. Do not hand-edit
BUGS.md / BUGS_DONE.md or hand-compute the next number.

- New bug discovered:
  ```bash
  .venv/bin/python3 tools/ledger.py bug-open "title" [--files file:line,...] [--desc "..."]
  ```
- Bug fixed this session:
  ```bash
  .venv/bin/python3 tools/ledger.py bug-close NNN --root-cause "..." --fix "..."
  ```
- Check the next free id without writing anything: `next-id bug`.
- Every subcommand accepts `--dry-run` to preview without touching files.

Background (formatting the CLI already enforces): entries carry
`Status: Open | Fixed | Wontfix`, `File(s)`, `Reported`/`Fixed` dates, and
`Root cause`/`Fix` text; numbering is `BUG-<NNN>` unique across both files.

## Step 4 — TODO.md / TODO_DONE.md

Same rule: use `tools/ledger.py`, not manual edits.

- New task:
  ```bash
  .venv/bin/python3 tools/ledger.py todo-open "title" [--priority High|Medium|Low] [--desc "..."]
  ```
- Done or cancelled:
  ```bash
  .venv/bin/python3 tools/ledger.py todo-close NNN [--resolution "..."]
  ```
- Check the next free id: `next-id todo`. All subcommands accept `--dry-run`.

Background: entries carry `Priority`, `Status: Open | In Progress | Done |
Cancelled`, `Added`/`Closed` dates, `Description`; numbering is `TODO-<NNN>`
unique across both files.

## Step 5 — PROJECT.md (only if applicable)

Update the relevant section if any of these changed: file structure, DB
schema, Flask routes, GUI screens/tabs, dependencies. The `## Change Log`
table is **frozen** (see its header note) — do not add rows there.
CHANGELOG.md is the only narrative change log.

## Step 6 — Cross-cutting reminders

- User-facing GUI strings changed → locale files must be updated
  (`/gui-next-i18n` for gui_next, `/i18n-update` for legacy gui/). Flag it if
  not yet done.
- Dependency changed → `requirements.txt` (pinned exact version) + PROJECT.md.
- If this session finished a spec/plan in `instructions/` (or its remainder
  moved to a TODO), `git mv` it to `instructions/complete/` and update
  `instructions/README.md`.

## Step 7 — Consistency check + report

Verify before finishing:
- No BUG/TODO number used twice across the four files.
- Every `Fixed`/`Done` item this session appears in a `*_DONE.md`, not the
  open file.
- All dates are today's actual date.

Report as a single table: `File | Action taken` (or "no change needed"), plus
the BUG/TODO numbers assigned this session.
