---
description: Non-visual verification for gui_next changes — typecheck main + renderer, then production build. The sanctioned alternative to screenshots.
---

# gui-check — Typecheck + build gui_next

Runs the code checks that stand in for visual verification (per the repo rule:
no screenshots/UI automation after GUI changes — the user verifies visuals).
Run after any change under `gui_next/src/`.

## Steps

Run all from `gui_next/`:

1. Typecheck the main process (Electron side):
   ```bash
   ./node_modules/.bin/tsc --noEmit -p tsconfig.node.json
   ```
2. Typecheck the renderer (React side):
   ```bash
   ./node_modules/.bin/tsc --noEmit -p tsconfig.web.json
   ```
   **Known baseline:** the renderer has pre-existing errors (14 in
   `ScreenScraper.tsx` as of 2026-07-04, tracked in BUGS.md). Compare against
   the files you touched: new errors in changed files = FAIL; the untouched
   baseline is not your failure, but report the current total so drift is
   visible.
3. Production build:
   ```bash
   npm run build
   ```
   Vite build errors (bad imports, missing assets) surface here even when
   types pass.
4. If locale strings were added/changed (`t()` calls or `en.json` keys),
   remind the user to run `/gui-next-i18n` — or run it if they asked for the
   full feature workflow.

## Report

One line per check (`node types | renderer types | build — PASS/FAIL`), then
any new errors with file:line. FAIL on any new error in files changed this
session.

## Notes

- There is no lint script in `gui_next/package.json` — typecheck + build is
  the full check suite.
- Do not launch the app, take screenshots, or run `tools/browser_driver.mjs`
  here; that is `/verify`, which only the user invokes.
