# LosslessBob — Claude Rules

Follow every session. No asking.

---

## Tool Usage

- When reading large files, ALWAYS use the Read tool with `offset`/`limit` parameters instead of `sed`, `head`, or `tail` via Bash. Avoid Bash for file inspection when Read can do it — it triggers unnecessary approval prompts.

## Screenshots / GUI Verification

**Only use `tools/browser_driver.mjs`** for all screenshots and UI automation. The old
`gui_next/gui_driver.mjs` (Electron+Playwright via Xvfb) and `scripts/screenshot_app.mjs`
are both unreliable in this sandbox (Electron CDP never connects / GTK aborts) — do not
use them.

`tools/browser_driver.mjs` drives the renderer with headless Chromium against the Vite
dev server, with `window.api` (the Electron preload bridge) stubbed via `addInitScript`.
No Electron, no Xvfb, no display manipulation.

**Start the Flask backend first** (port 5174) so the splash overlay clears quickly
(~2.4s) instead of timing out (~11s):
```
nohup .venv/bin/python3 run_backend.py > /tmp/flask_backend.log 2>&1 & disown
```

```
# Single screen
node tools/browser_driver.mjs navigate /attachments attachments.png

# All screens
node tools/browser_driver.mjs session tools/debug_screens.json
```

- Screenshots land in `.debug/`
- Spawns `npm run dev` (port 5173) automatically — pass `--no-server` if one is already running
- `--preview` uses `npm run preview` (port 4173) and builds first unless `--no-build`
- Waits for the splash overlay to detach before acting

### Verification gotchas (read before writing a session JSON)

- **Prefer API checks over screenshots for data-shape changes.** If you only need to confirm
  a backend field/shape change (e.g. a new key in an API response), `curl` the endpoint
  directly. Reserve `browser_driver.mjs` sessions for layout/interaction checks that actually
  need a render.
- **Use `data-testid` selectors, not `:has-text()`.** `:has-text()` is a case-insensitive
  *substring* match — `"Lookup"` matches both the "Lookup" stage tab and the "Quick lookup"
  sidebar button, and clicking the wrong one silently navigates away. Stable testids exist:
  `[data-testid="stage-tab-verify|lookup|rename|lbdir|file"]` (pipeline DetailPanel tabs),
  `[data-testid="nav-<id>"]` (main sidebar nav), `[data-testid="nav-adv-<id>"]` (Advanced
  tools sub-nav: verify/lookup/rename/lbdir), `[data-testid="sidebar-quick-lookup"]`.
- **Button labels use the Unicode ellipsis `…` (U+2026)**, not three periods (`...`) —
  e.g. `"Add folders…"`. A selector with `...` will never match.
- **Use `wait-for` on a real condition, not a fixed `wait` ms.** Fixed waits are either too
  short (verify+lookup on a real folder can take >10s) or wastefully long. Wait for the
  status pill/text that indicates completion instead of guessing a duration.
- **Kill stray dev-server processes before starting a new session** — a previous
  `browser_driver.mjs` run that didn't exit cleanly leaves `electron-vite dev`/esbuild
  processes that hold port 5173 and can hang unrelated commands (e.g. `tsc`):
  `pkill -9 -f "electron-vite dev"; pkill -9 -f esbuild`
- **Always use absolute/repo-relative paths** for `node tools/browser_driver.mjs ...` —
  don't rely on a prior `cd` having persisted.

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
