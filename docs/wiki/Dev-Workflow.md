# Dev Workflow

> Sources: `.claude/CLAUDE.md` · `.claude/commands/` · `.claude/skills/` ·
> `.claude/hooks/` · Status: fresh 2026-10-18

## Session lifecycle

- **Open**: a SessionStart hook (`hooks/session_brief.sh`) auto-injects a briefing
  (branch, uncommitted count, last CHANGELOG entry, top TODOs, calibration tail,
  wiki staleness via `tools/wiki_staleness.py`). `/session-open` re-runs it
  mid-session.
- **Close**: `/session-close` does the mandatory bookkeeping — CHANGELOG.md entry,
  BUGS→BUGS_DONE / TODO→TODO_DONE moves via `tools/ledger.py`, PROJECT.md
  reference updates. CHANGELOG keeps a rolling ~2-month window; older months
  rotate to CHANGELOG_ARCHIVE.md.

## Verification rules

| Change | Verify with |
|---|---|
| Backend | `/backend-restart` first, then test against :5174 |
| gui_next | `/gui-check` (typecheck + prod build) — always required |
| gui_next layout/visuals | also `/verify` — Tier A screenshots the renderer; `/verify --electron` drives the real app on Xvfb (sanctioned 2026-07-22, Claude may run on own initiative; pick the cheapest tier) |
| Python file | automatic — PostToolUse hook runs `py_compile` on every `.py` edit |
| User-facing gui_next feature | `/gui-next-i18n` locale update |

CI (`.github/workflows/ci.yml`) runs the backend suite + gui-check on every
push; a green run can stand in for re-running the full local suite for
*unrelated* code — never for code the session actually changed.

## Hooks (`.claude/hooks/`)

`session_brief.sh` (briefing) · `py_compile_check.sh` (syntax on .py edits) ·
`changelog_check.sh` + `session_end_check.sh` (bookkeeping nags) ·
`i18n_reminder.sh` (locale nag) · an inline PreToolUse guard in `settings.json` (blocks Read/Write/Edit outside
the project; `hooks/path_guard.py` is not wired in `settings.json`) · plus an async wrangler deploy of `docs/schema.html` to
Cloudflare Pages.

## Key commands & skills

`/backend-restart` · `/gui-check` · `/verify` · `/session-open` ·
`/session-close` · `/tapematch-batch` · `/analyze-runs` · `/find-bugs` ·
`/gui-next-i18n` · `/wiki-update` (this wiki). `/verify` and `/analyze-runs`
are skills (`.claude/skills/`); the rest are commands (`.claude/commands/`).

## Working conventions

- Grep-first context discipline: never full-read PROJECT.md/BUGS.md/TODO.md —
  `grep -n` for the section/ID, then Read with offset/limit.
- Python is `.venv/bin/python3` — bare `python`/`python3` not on PATH.
- Commits: `<type>(<scope>): <description>` — types feat|fix|refactor|docs|chore|test,
  scopes backend|gui|db|scraper|importer|scheduler|docs|tapematch|bookkeeping.
- Temp files: never the harness scratchpad (hook aborts the turn) — use `.debug/`
  or `tools/_<name>.<ext>`. Bulk audio never in `/tmp` (2.7 GB): backend uses
  `backend.tmp_utils.audio_tmp_dir()`; ad-hoc decodes go to `/mnt/DATA0/tmp/<name>/`,
  deleted same session.
- Replies stay short (CLAUDE.md Response length): answer first, no preamble.
- Debugging first question: "is the running process the latest code?"
- Bug/task tracking: BUGS.md / TODO.md with BUG-NNN / TODO-NNN IDs.
