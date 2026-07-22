# LosslessBob — Claude Rules

Follow every session. No asking.

---

## Context Discipline

- A session briefing (branch, uncommitted count, last CHANGELOG entry, top TODOs,
  calibration tail) is auto-injected at session start by a SessionStart hook — trust
  it instead of re-deriving that state; `/session-open` re-runs it mid-session.

- For **subsystem orientation**, read the matching `docs/wiki/` page first (each
  ≤~60 lines, lists its authoritative PROJECT.md sections) — then grep PROJECT.md
  only for the specific detail needed. Same rule for subagent prompts: point them
  at the wiki page, don't restate the subsystem. Index: `docs/wiki/Home.md`.
- Do **not** read PROJECT.md, BUGS.md, or TODO.md in full (3,000+ lines combined).
  `grep -n` for the relevant section/ID first, then Read with `offset`/`limit`:
  - File structure, DB schema, Flask routes, GUI screens → matching PROJECT.md section.
  - Bug/task context → `BUG-<NNN>` / `TODO-<NNN>` or keywords in BUGS.md / TODO.md.
- Same for any large file: grep first, targeted Read after. Full reads only for
  files under ~150 lines. Never `sed`/`head`/`tail` via Bash for file inspection.
- State the files you plan to change before changing them.

---

## Environment

- Python is `.venv/bin/python3` — bare `python`/`python3` is not on PATH.
- Backend Flask port **5174**, hardcoded everywhere — change atomically + log in CHANGELOG.

## Verification

- Backend changes: restart before verifying (`/backend-restart`) — stale processes
  cause false "fix didn't work" confusion.
- gui_next changes: `/gui-check` (typecheck + production build) is always
  required. The screenshot engine is **sanctioned** (fixed & cleared by tj
  2026-07-22): when a change affects layout or visuals, also verify it with
  `/verify` — Tier A screenshots the renderer; `/verify --electron` drives the
  real Electron app on Xvfb (resize, display scale, real `window.api`). Claude
  may run it on its own initiative; pick the cheapest tier that answers the
  question.
- A PostToolUse hook (`.claude/hooks/py_compile_check.sh`) auto-runs
  `py_compile` on every `.py` edit — no manual syntax-check step needed.
- CI (`.github/workflows/ci.yml`) runs the backend suite + gui-check on every
  push; a session may cite a green run instead of re-running the full local
  suite for unrelated code. Does NOT weaken the local rules above for code the
  session actually changed — `/backend-restart` + targeted tests still apply.

---

## Code Rules

- Python 3.11+, PEP 8, 4-space indent, max 100 chars/line.
- Type hints + Google-style docstrings on all new public functions/classes.
- No `print()` — use `logging`. No hardcoded paths outside module constants.
- SQLite changes: `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` column-existence
  checks before `ALTER TABLE`, for idempotency. Never assume clean DB.
- `requirements.txt` pinned exact versions. Update it + PROJECT.md on any dep change.

---

## Bookkeeping

Every session that changes code ends with the repo's bookkeeping: CHANGELOG.md
entry, BUGS/BUGS_DONE and TODO/TODO_DONE moves. Run `/session-close` — entry
formats and numbering rules live in that skill.

User-facing feature changes also require locale updates: `/gui-next-i18n`.

CHANGELOG.md holds a rolling ~2-month window; when a month rotates out, move its
entries to the top of CHANGELOG_ARCHIVE.md (keep newest-first order).

Subdirectory rules live in `tools/tapematch/CLAUDE.md` — they load
automatically when working there; don't duplicate them here.

---

## Debugging

- First question: "is the running process the latest code?" Restart or
  version-check before deep investigation.
- Find root cause before fixing. State hypothesis, verify with logs/tests.
- Multi-symptom bug? Look for one shared root cause.
- "Still didn't work" → don't retry same fix. Re-read error, find different cause.
- Encoding/filename bugs: check BOTH Unicode normalization (curly vs straight
  apostrophes) AND Windows-1252 bytes (`\x92` etc). Legacy md5/checksum files
  may be cp1252.

---

## Commits

```
<type>(<scope>): <description>
types: feat | fix | refactor | docs | chore | test
scopes: backend | gui | db | scraper | importer | scheduler | docs
```
