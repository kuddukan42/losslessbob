# LosslessBob — Claude Rules

Follow every session. No asking.

---

## Tool Usage

- When reading large files, ALWAYS use the Read tool with `offset`/`limit` parameters instead of `sed`, `head`, or `tail` via Bash. Avoid Bash for file inspection when Read can do it — it triggers unnecessary approval prompts.

---

## Before Any Task
1. Read `PROJECT.md`, `BUGS.md`, `TODO.md`.
2. State files you plan to change before changing them.

---

## After Every Code Change — Update These Files

**CHANGELOG.md** — prepend one entry per session:
```
[YYYY-MM-DD] — <summary>
Changed: <file>: <what/why>
Fixed: <file>: <bug + fix>        (if applicable)
Added: <file>: <new capability>   (if applicable)
```

**PROJECT.md** — update if any of these changed: file structure, DB schema, Flask routes, GUI tabs, dependencies. Add row to Change Log table.

**BUGS.md / BUGS_DONE.md**
```
BUG-<NNN>: <title>
Status: Open | Fixed | Wontfix
File(s): <file:line>
Reported: YYYY-MM-DD
Fixed: YYYY-MM-DD
Root cause: ...
Fix: ...
```
New bug → add Open to BUGS.md. Fixed → move to top of BUGS_DONE.md.

**TODO.md / TODO_DONE.md**
```
TODO-<NNN>: <title>
Priority: High | Medium | Low
Status: Open | In Progress | Done | Cancelled
Added: YYYY-MM-DD
Closed: YYYY-MM-DD
Description: ...
```
New task → TODO.md. Done/cancelled → move to top of TODO_DONE.md.

---

## Code Rules

- Python 3.11+, PEP 8, 4-space indent, max 100 chars/line.
- Type hints + Google-style docstrings on all new public functions/classes.
- No `print()` — use `logging`.
- No hardcoded paths outside module constants.
- GUI↔backend calls: QThread workers only, never main thread.
- SQLite changes: `ALTER TABLE` + `try/except` for idempotency. Never assume clean DB.
- Port **5174** hardcoded everywhere — change atomically + log in CHANGELOG.
- `requirements.txt` pinned exact versions. Update it + PROJECT.md on any dep change.
- Syntax check before done: `.venv/bin/python3 -m py_compile <file>`

---

## Backend Development

- After making backend code changes, ALWAYS restart the backend before verifying behavior. Stale running processes are a common source of false "fix didn't work" confusion.

---

## Workflow Conventions

When updating user-facing features, also update: (1) CHANGELOG.md, (2) locale/i18n files, and (3) any relevant TODO entries. These are part of every feature change in this repo.

---

## Known Pitfalls

- For encoding/filename bugs, check BOTH Unicode normalization (curly vs straight apostrophes) AND Windows-1252 byte encoding (`\x92` etc). The repo handles legacy md5/checksum files that may be cp1252.

---

## Debugging

- Before diagnosing a bug, ask: "is the running process the latest code?" Verify with a version check or restart before deep investigation.
- Find root cause before fixing. State hypothesis, verify with logs/tests.
- Multi-symptom bug? Look for one shared root cause.
- "Still didn't work" → don't retry same fix. Re-read error, find different cause.

---

## Commits
```
<type>(<scope>): <description>
types: feat | fix | refactor | docs | chore | test
scopes: backend | gui | db | scraper | importer | scheduler | docs
```
