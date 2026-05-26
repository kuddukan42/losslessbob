# LosslessBob — Claude Rules

Follow every session. No asking.

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

## Debugging

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
