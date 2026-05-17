# Claude Code — Project Instructions: LosslessBob Checksum Lookup

## Role
You are the primary developer assistant for this project. Follow all rules below on every session without being asked.

---

## Debugging Approach

- Before making speculative fixes, identify and confirm the root cause first. State your hypothesis and verify it with logs/tests before editing.
- For multi-symptom bugs, check for shared root causes (e.g., import-time binding, date format swaps, platform checks) rather than patching each symptom.

---

## Mandatory on Every Code Change

### 1. Update CHANGELOG.md
After every code change (bugfix, feature, refactor, config), prepend an entry:
[YYYY-MM-DD] — <one-line summary>
Changed

<file>: <what changed and why>

Fixed (if applicable)

<file>: <bug description and fix>

Added (if applicable)

<file>: <new capability>


Do not batch multiple sessions into one entry. One entry per session that produces a diff.

### 2. Update PROJECT.md
- **Tech Stack table**: If any dependency is added, removed, or version-bumped, update the table immediately. Pull the exact version from `requirements.txt` or the installed package.
- **File Structure**: If a file is created, moved, or deleted, update the tree.
- **Database Schema**: If any table or column changes, update the schema section.
- **API routes**: If any Flask route is added, changed, or removed, update the Backend section.
- **Change Log table** at the bottom of PROJECT.md: Append a one-liner for any structural change.

### 3. Update BUGS.md
Format:
BUG-<NNN>: <short title>
Status: Open | Fixed | Wontfix
File(s): <file:line if known>
Reported: YYYY-MM-DD
Fixed: YYYY-MM-DD (if resolved)
Description: <what goes wrong>
Root cause: <once known>
Fix: <what was done>

- When you identify a bug (even while doing unrelated work), add it as Open.
- When you fix a bug, update its status and fill in Root cause + Fix.
- Never delete bug entries — only update status.

### 4. Update TODO.md
Format:
TODO-<NNN>: <task title>
Priority: High | Medium | Low
Status: Open | In Progress | Done | Cancelled
Added: YYYY-MM-DD
Closed: YYYY-MM-DD (if done)
Description: <what needs doing>

- Add a TODO for any known improvement, tech debt, or deferred work discovered during a session.
- Mark Done when completed; never delete entries.

---

## Code Standards

- **Python 3.11+**, PEP 8, 4-space indent, max line length 100.
- **Type hints** on all new functions.
- **Docstrings** (Google style) on all new public functions and classes.
- **No breaking changes to the Flask API** without adding a migration note in CHANGELOG.md and a comment in `backend/app.py`.
- **SQLite schema changes**: always use `ALTER TABLE` or migration SQL with a fallback `try/except` for idempotency — never assume a clean DB.
- **Threading**: all GUI↔backend calls must be in QThread workers, never on the main thread.
- **Port 5174** is hardcoded in multiple files — if it ever needs to change, update all occurrences atomically and log in CHANGELOG.

---

## Dependency Management

- Keep `requirements.txt` pinned to exact versions.
- After any `pip install` or version bump, update both `requirements.txt` and the Tech Stack table in `PROJECT.md`.
- If a dependency is removed, remove it from both.

---

## Before Starting Any Task

1. Read `PROJECT.md` for architecture context.
2. Read `BUGS.md` for any open bugs relevant to the area you're touching.
3. Read `TODO.md` for relevant open tasks.
4. State which files you plan to modify before modifying them.

---

## Commit Message Format (if using git)
<type>(<scope>): <short description>
Types: feat | fix | refactor | docs | chore | test
Scope: backend | gui | db | scraper | importer | scheduler | docs
Example: fix(scraper): handle HTTP 429 rate limit with exponential backoff

---

## Project Conventions

- This is a PyQt application; after any GUI change, verify Qt repaint/viewport behavior and avoid initialization-order issues.
- After implementing any feature or fix, update CHANGELOG.md and BUGS.md as appropriate.
- Run a syntax check (`python -m py_compile`) on modified files before declaring done.

---

## Testing & Verification

- For bugs reported with 'still didn't work', do not re-apply similar fixes — re-read the original error and consider alternative root causes (off-by-one, format swaps, platform differences, library quirks).
- Verify fixes end-to-end where possible (run the code, check actual output) rather than relying on code inspection alone.

---

## What NOT to Do

- Do not silently change behavior — document every behavioral change in CHANGELOG.md.
- Do not leave debug `print()` statements in committed code; use Python `logging`.
- Do not hardcode paths outside of the designated constants in each module.
- Do not modify `data/losslessbob.db` schema without updating PROJECT.md and adding a migration path.
- Do not create new files without adding them to the File Structure in PROJECT.md.

