# Dev Workflow

> Sources: `.claude/CLAUDE.md` · `.claude/commands/` · `.claude/skills/` ·
> Status: seeded 2026-07-06

## Session lifecycle

- **Open**: a SessionStart hook auto-injects a briefing (branch, uncommitted count,
  last CHANGELOG entry, top TODOs, calibration tail). `/session-open` re-runs it.
- **Close**: `/session-close` does the mandatory bookkeeping — CHANGELOG.md entry,
  BUGS→BUGS_DONE / TODO→TODO_DONE moves with numbering, PROJECT.md change-log row.
  CHANGELOG keeps a rolling ~2-month window; older months rotate to
  CHANGELOG_ARCHIVE.md.

## Verification rules

| Change | Verify with |
|---|---|
| Backend | `/backend-restart` first, then test against :5174 |
| gui_next | `/gui-check` (typecheck + prod build) — no screenshots |
| Python file | `.venv/bin/python3 -m py_compile <file>` |
| User-facing gui_next feature | `/gui-next-i18n` locale update |
| Legacy gui/ feature | `/i18n-update` |

## Key commands & skills

`/backend-restart` · `/gui-check` · `/session-open` · `/session-close` ·
`/tapematch-batch` · `/analyze-runs` · `/find-bugs` · `/gui-next-i18n` ·
`/i18n-update` · `/verify` (explicit-only visual check) · `/wiki-update` (this wiki).

## Working conventions

- Grep-first context discipline: never full-read PROJECT.md/BUGS.md/TODO.md —
  `grep -n` for the section/ID, then Read with offset/limit.
- Commits: `<type>(<scope>): <description>` — types feat|fix|refactor|docs|chore|test,
  scopes backend|gui|db|scraper|importer|scheduler|docs.
- Debugging first question: "is the running process the latest code?"
- Bug/task tracking: BUGS.md / TODO.md with BUG-NNN / TODO-NNN IDs.
