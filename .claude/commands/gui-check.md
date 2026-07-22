---
description: Non-visual verification for gui_next changes — typecheck main + renderer, then production build. Baseline check; pair with /verify screenshots for visual changes.
---

# gui-check — Typecheck + build gui_next

Runs the non-visual code checks for gui_next. Run after any change under
`gui_next/src/`. For changes that affect layout or visuals, follow up with
`/verify` — the screenshot engine is sanctioned for use on Claude's own
initiative (2026-07-22).

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
   **Known baseline:** 0 errors as of 2026-07-15 (the old 14-error
   `ScreenScraper.tsx` baseline was cleared). Any error = FAIL; report the
   total so drift is visible.
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
- Screenshots/UI automation are not part of this skill — that is `/verify`,
  which may be run separately (on Claude's initiative for visual changes).
