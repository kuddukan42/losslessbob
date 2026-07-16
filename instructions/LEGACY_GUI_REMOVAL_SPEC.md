# Legacy PyQt6 GUI Removal — Spec

**Status:** DRAFT — awaiting tj sign-off on Phase 0 decisions
**Written:** 2026-07-16
**Ledger:** assign next free TODO-NNN via `tools/ledger.py` when scheduled
**Goal:** Delete the frozen legacy PyQt6 GUI (`gui/`) and every piece of code, packaging,
tooling, and documentation that exists only to support it, leaving gui_next (Electron/React)
as the sole GUI platform. Backend (Flask, port 5174) is untouched except where it reaches
into `gui/` for assets or helpers.

---

## 1. Inventory

### 1.1 Delete outright (used only by the legacy GUI)

| Item | Detail |
|---|---|
| `gui/` package | 19 modules, 18,517 LOC. Tabs, main_window, styles, widgets/, i18n.py |
| `gui/locales/` | 1.9 MB Qt `.ts`/`.qm` translation files |
| `gui/CLAUDE.md` | Legacy subdirectory rules (frozen-GUI policy, QThread rule) |
| `main.py` | Legacy entrypoint (Flask thread + PyQt6 app + splash + `-ignore_start_positions`). Backend-only entry is `run_backend.py`; Electron auto-spawns the backend itself |
| `run_next.py` | **Already dead**: imports `gui_next.main_window` (Python), which no longer exists — relic of the pre-Electron gui_next. Imports PyQt6. Safe to delete independently of everything else |
| `losslessbob.spec` | PyInstaller spec building `main.py` + PyQt6/WebEngine (Windows) |
| `losslessbob_linux.spec` | Same for Linux |
| `scripts/translate_ts.py` | DeepL translation of `gui/locales/*.ts` |
| `.claude/commands/i18n-update.md` | `/i18n-update` skill — Qt `.ts`/`.qm` pipeline, legacy-only |
| Qt test classes in `tests/test_lb_master.py` | The `qtbot` classes importing `gui.search_tab`, `gui.collection_tab`, `gui.dbedit_tab` (~5 of 27 tests, lines ~369–400). Backend tests in the same file stay |
| `requirements.txt` pins | `PyQt6==6.7.1`, `PyQt6-WebEngine==6.7.0` (lines 12–13) |
| `pytest-qt` | Installed in .venv (4.5.0, unpinned anywhere) — uninstall once Qt tests are gone |

### 1.2 Migrate before deleting (live couplings into `gui/`)

These are the only things keeping `gui/` load-bearing today:

1. **Map assets — used by gui_next.** `ScreenMap.tsx` embeds
   `${flaskBase}/map` in an iframe. Backend serves `gui/resources/map.html`
   (`backend/app.py:6211-6215`) and `gui/resources/leaflet/`
   (`backend/app.py:6217-6221`).
   → Move `gui/resources/{map.html, leaflet/}` to `backend/resources/` and update the
   two route paths + docstrings.
   → In `map.html`, remove the QWebChannel bridge block (~line 284+, the
   `qt.webChannelTransport` path used only inside QWebEngineView). **Keep** the
   `postMessage` listener — that is the path ScreenMap's iframe filter panel uses.

2. **VLC launcher — used by the backend API.** `backend/app.py:2890` imports
   `open_in_vlc` from `gui.platform_utils`.
   → Create `backend/platform_utils.py` with `open_in_vlc` and `_subprocess_flags`
   (pure subprocess/shutil, no Qt). Drop the Qt-only functions
   (`url_to_local_path` and the QDesktopServices open helpers) — nothing outside
   `gui/` uses them.

3. **Docker/noVNC container — legacy-GUI-only deployment.** `docker/entrypoint.sh`
   runs Xvfb + x11vnc + websockify/noVNC and `exec python3 main.py`; the Dockerfile
   installs the Qt6/xcb runtime for the PyQt6 wheels. Fate is a Phase 0 decision.

### 1.3 Keep untouched

- Everything under `gui_next/` and its skills: `/gui-check`, `/gui-next-i18n`, `/verify`.
- `.claude/hooks/i18n_reminder.sh` — already matches gui_next's `en.json` only.
- `.claude/hooks/py_compile_check.sh` — generic.
- `losslessbob_backend.spec` — backend-only freeze, already excludes PyQt6.
- All backend endpoints (the GUI-tab-shaped ones serve gui_next screens too).
- `run_backend.py`, `cli.py` (no gui imports).

---

## 2. Phase 0 — Decisions (tj sign-off required before work starts)

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Docker/noVNC stack fate.** (a) delete `Dockerfile`/`docker-compose.yml`/`docker/` entirely; (b) convert to a backend-only API container (`run_backend.py`, drop Qt/Xvfb/VNC layers) | (b) if the container is ever used for remote API access; otherwise (a) |
| D2 | **BUG-106** (Windows installer / Program Files) — targets the legacy PyInstaller build | Close as obsolete-by-removal |
| D3 | **BUG-249** (intermittent native pytest crash in `test_status_combobox_exists`) | Close as resolved-by-removal when the Qt tests are deleted |
| D4 | **`ui_language` settings key** (`backend/app.py:787` whitelist) — written by the legacy Setup tab; gui_next has its own locale handling | Leave the key in the DB/whitelist (harmless), just delete the GUI that wrote it. Optional later cleanup |
| D5 | **Frozen desktop builds** — is any user running the PyInstaller `losslessbob.exe`? If yes, this removal ends that distribution channel | Confirm none, then proceed |

---

## 3. Work plan (one usage chunk per phase; commit at each phase boundary)

### Phase 1 — Migrations (no deletions; repo stays fully working)
- `git mv gui/resources/map.html gui/resources/leaflet backend/resources/`;
  update the two routes in `backend/app.py` (~6211–6221) + docstrings.
- Strip the QWebChannel block from `map.html`; keep postMessage handling.
- New `backend/platform_utils.py` (`open_in_vlc`, `_subprocess_flags`);
  point `backend/app.py:2890` at it.
- Delete the Qt test classes from `tests/test_lb_master.py`.
- Docstring sweep in `backend/app.py` for `gui/` mentions (6213, 7966, 2890 area).
- **Verify:** `/backend-restart`; load ScreenMap in gui_next and confirm the map
  renders and filters apply (tj visual check per no-screenshot rule); full pytest.
- Commit: `refactor(backend): migrate map assets + VLC helper out of gui/, drop Qt tests`

### Phase 2 — Deletion
- `git rm -r gui/`; `git rm main.py run_next.py losslessbob.spec losslessbob_linux.spec scripts/translate_ts.py .claude/commands/i18n-update.md`
- **Verify:** grep sweep is clean (Section 4); `/backend-restart`; pytest.
- Commit: `chore(gui): remove legacy PyQt6 GUI`

### Phase 3 — Dependencies, packaging, Docker (per D1)
- `requirements.txt`: drop the two PyQt6 pins; `pip uninstall PyQt6 PyQt6-WebEngine pytest-qt` from .venv.
- Dockerfile/entrypoint: apply D1 — either delete the docker stack or rebase the image
  on `run_backend.py` with Qt/Xvfb/x11vnc/websockify layers removed.
- **Verify:** fresh `pip install -r requirements.txt` into a temp venv imports
  `backend.app` cleanly; if D1=(b), `docker build` succeeds.
- Commit: `chore(backend): drop PyQt6 deps and legacy packaging`

### Phase 4 — Docs, rules, ledger
- **PROJECT.md:** header stack table (lines ~13, 26–27, 42), file tree (~52, 121),
  all `## GUI: * Tab (gui/*.py)` sections (~1868–2300), scattered references
  (~1217, 2283, 2332, 2469, 2488). Replace tab sections with a one-paragraph
  "legacy GUI removed <date>, see CHANGELOG" note or delete outright.
- **Root `.claude/CLAUDE.md`:** remove `/i18n-update` from Bookkeeping, remove the
  `gui/CLAUDE.md` line from subdirectory rules, remove legacy-GUI wording in Verification.
- **Wiki:** `/wiki-update` for `GUI.md` (retire or rewrite as gui_next-only),
  then `Architecture.md`, `Home.md`, `Dev-Workflow.md` (one page per run).
- **Ledger:** close BUG-106 + BUG-249 per D2/D3 via `tools/ledger.py`; CHANGELOG entry;
  `/session-close`.
- Commit: `docs: purge legacy GUI from PROJECT.md, CLAUDE.md, wiki`

### Phase 5 — Final verification
- Grep sweep (Section 4) returns nothing.
- Full pytest green; `/gui-check` green; `/backend-restart` + status OK.
- gui_next launch + ScreenMap check by tj.

---

## 4. Residual-reference grep sweep (run after Phases 2 and 4)

```bash
grep -rn "PyQt6\|pyqt\|QWebEngine\|qtbot\|from gui\.\|from gui import\|import gui\b\|gui/" \
  --include="*.py" --include="*.md" --include="*.txt" --include="*.toml" \
  --include="*.sh" --include="*.spec" . \
  | grep -v "gui_next\|\.venv\|node_modules\|__pycache__\|\.claude/worktrees\|CHANGELOG\|TODO_DONE\|BUGS_DONE\|instructions/complete\|LEGACY_GUI_REMOVAL"
```

Historical files (CHANGELOG*, *_DONE, instructions/complete/) keep their references —
they are records, not live docs.

---

## 5. Risks

- **ScreenMap regression** is the only user-visible risk: the map iframe depends on the
  moved `/map` + `/leaflet` assets and the postMessage filter path surviving the
  QWebChannel strip. Phase 1 verifies this before anything is deleted.
- **`.venv` drift:** PyQt6 stays importable in the venv until Phase 3's uninstall —
  fine, but the grep sweep excludes `.venv` for this reason.
- **Old worktrees** under `.claude/worktrees/` still contain legacy files; they are
  disposable agent artifacts, not part of the removal.

## 6. Resume state

- [ ] Phase 0 — decisions D1–D5 signed off
- [ ] Phase 1 — migrations committed + map verified
- [ ] Phase 2 — deletion committed
- [ ] Phase 3 — deps/packaging committed
- [ ] Phase 4 — docs/ledger committed
- [ ] Phase 5 — final sweep green → move spec to `instructions/complete/`
