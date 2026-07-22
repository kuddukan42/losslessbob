---
name: verify
description: Visual verification of the gui_next GUI — screenshot all major screens, review for defects, PASS/FAIL verdict. Default Tier A (`--renderer-only`, Chromium vs the Vite server); `--electron` drives the real Electron app. Sanctioned for use on Claude's own initiative (2026-07-22).
---

# Visual Verification

Capture every major gui_next screen, review each screenshot, and give a
PASS/FAIL verdict.

The screenshot engine is sanctioned for use on Claude's own initiative
(fixed & cleared by tj 2026-07-22 — it was previously restricted to explicit
user invocation). Run it whenever a gui_next change affects layout or visuals;
`/gui-check` remains the required non-visual baseline.

## One driver, two tiers

`tools/electron_driver.mjs` is the single screenshot engine (the separate
`browser_driver.mjs` was merged into it 2026-07-22):

| | Tier A (default, `--renderer-only`) | Tier B (`--electron`) |
|---|---|---|
| Invocation | `electron_driver.mjs --renderer-only …` | `electron_driver.mjs …` (no flag) |
| Runs | headless Chromium vs the Vite server | the REAL app (`gui_next/out/main/index.js`) on Xvfb |
| PNGs | `.debug/` | `.debug/electron/` |
| Extra actions | — | `scale-matrix`, `main-eval`; `resize` is a real window resize |
| `window.api` | stubbed | real Electron preload bridge |
| Cost | seconds | slower (Xvfb + Electron boot per launch) |

Tier A is the default because it is fast and covers renderer defects. Reach for
Electron mode when the question is about the real window rather than the page:
window chrome, resize/layout at real sizes, display scale, native
`window.api`/preload flows, or main-process state. Both modes share the same
session format (`tools/debug_screens.json`), so the screen tour is identical.

Design/history for Electron mode: `instructions/complete/FABLE_VISUAL_VERIFICATION.md`.

## Steps

1. Ensure the Flask backend is running on port 5174 (the GUI needs it for live
   data). If not running, start it and confirm it responds:
   ```bash
   curl -s http://127.0.0.1:5174/api/status || echo "backend not up"
   ```
   Electron mode always sets `LB_NO_BACKEND_SPAWN=1`, so the app will not spawn
   its own backend — a manually-started one on 5174 survives the whole session,
   and the driver logs backend status before and after the run.
2. Run the full screen tour:
   ```bash
   # Tier A (default) — screenshots land in .debug/
   node tools/electron_driver.mjs --renderer-only session tools/debug_screens.json

   # Tier B (--electron) — builds first; screenshots land in .debug/electron/
   node tools/electron_driver.mjs session tools/debug_screens.json
   ```
   Tier A dev mode serves source directly (no build step); add `--no-build` to
   the Electron form only if the build already ran this session.
3. Read every screenshot with the Read tool and review for: blank/white
   screens, missing data (backend errors), broken layout or clipped text,
   untranslated i18n keys showing raw `section.key` strings, and console errors
   reported by the driver.
4. Verdict in chat: one line per screen (`screen | PASS/FAIL | issue`), then an
   overall PASS/FAIL. Say which tier ran.
5. Any new defect found → add an Open `BUG-<NNN>` entry to `BUGS.md` in the
   standard format (next free number; check `BUGS_DONE.md` too so numbers don't
   collide).

## Notes

- Single screen: `node tools/electron_driver.mjs --renderer-only navigate <route> <file.png>`
  (drop `--renderer-only` for the real app).
- Tier A stubs `window.api`, so file-picker flows can't be exercised there —
  note them as "not verifiable" rather than FAIL, or re-run that screen in
  Electron mode, where the bridge is real.
- The tour session file has settle waits (`wait-for` with `state: "detached"`
  on `text=Loading`) so heavy screens are captured loaded; a timed-out wait
  logs `ok: false` and the tour continues.
- Electron-mode extras, all `.debug/electron/`:
  ```bash
  node tools/electron_driver.mjs size-matrix   # 1280x768 / 1440x900 / 1920x1080 / 2560x1440
  node tools/electron_driver.mjs scale-matrix  # DPR 1 / 1.25 / 1.5 / 2 (relaunch per scale)
  node tools/electron_driver.mjs watch 500 15000 prog '[data-testid="done"]'
  ```
  `size-matrix` sets **content** size, so a `2560x1440.png` really is that size.
  `scale-matrix` pins a 1440x900 logical baseline per row, so rows differ only
  by DPR; its 1.25x row lands at 1800x1128 (Chromium DIP rounding, not a bug).
- Electron mode never re-probes display backends — it reads the Xvfb decision
  recorded in `tools/electron_driver.config.json`. If it errors that no backend
  is `selected`, run `node tools/electron_preflight.mjs` and own the decision;
  don't hand-edit the matrix.
- Screenshot artifacts in `.debug/` are disposable; don't commit them.
