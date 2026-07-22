# Visual Verification

> Sources: `tools/electron_driver.mjs` · `tools/driver_core.mjs` · `tools/electron_display.mjs` · `tools/electron_preflight.mjs` · `tools/electron_driver.config.json` · `tools/debug_screens.json` · `.claude/skills/verify/SKILL.md` · `instructions/complete/FABLE_VISUAL_VERIFICATION.md` · Status: fresh 2026-07-22

The screenshot engine that lets an agent see the gui_next GUI. Since
2026-07-22 it is **one driver, two modes** (`tools/browser_driver.mjs` was
retired into `--renderer-only`), and it is **sanctioned for agent-initiative
use** after visual changes — the old "user-invoked only" rule is gone.
`/gui-check` (typecheck + build) remains the required non-visual baseline.

## The two modes

| | Tier A `--renderer-only` | Tier B (default) |
|---|---|---|
| Runs | headless Chromium vs the Vite server | the real built app (`gui_next/out/main/index.js`) on Xvfb |
| `window.api` | stubbed shim | real preload bridge |
| PNGs | `.debug/` | `.debug/electron/` |
| Cost | seconds | Xvfb + Electron boot per launch |
| Extras | — | real window `resize`, `scale-matrix` (DPR 1–2), `main-eval` |

```bash
node tools/electron_driver.mjs --renderer-only session tools/debug_screens.json  # fast tour
node tools/electron_driver.mjs session tools/debug_screens.json                  # real app
```

## How it fits together

- **`driver_core.mjs`** — shared action runner (screenshot/navigate/click/
  fill/wait-for/eval/resize/size-matrix/watch/…). Failed steps report
  `ok: false` but never abort the sequence. `wait-for` takes a `state`
  option; the tour uses `state: "detached"` on `text=Loading` so heavy
  screens are captured settled, not mid-spinner.
- **`debug_screens.json`** — the 20-screen tour, mode-agnostic; must track
  `gui_next/src/renderer/src/lib/navigation.ts` when screens change
  (BUG-268 was this file going stale).
- **`electron_preflight.mjs` + `electron_driver.config.json`** — the display
  backend was probed once and committed: Xvfb, screen `2920x1860x24`, flags
  `--ozone-platform=x11 --disable-gpu --no-sandbox`. The driver reads the
  decision and never re-probes.
- **`/verify` skill** — the workflow wrapper: backend on :5174 first, run the
  tour, Read every PNG, per-screen PASS/FAIL verdict, new defects → BUGS.md.

## Hard rules (from the design record)

- Electron mode always sets `LB_NO_BACKEND_SPAWN=1` — the manually started
  Flask backend on :5174 must survive a session.
- Screenshots only via Playwright `page.screenshot()`; Xvfb and the app are
  killed on success *and* error paths.
- Tier B `resize` uses `setContentSize` (not `setSize`) so both modes produce
  honestly-sized PNGs; `scale-matrix` 1.25x lands at 1800x1128 (DIP
  rounding — not a bug).
- Screenshots show collection data — keep them local, never publish.

Full design history and findings: `instructions/complete/FABLE_VISUAL_VERIFICATION.md`.
Related: [GUI](GUI.md) · [Dev-Workflow](Dev-Workflow.md).
