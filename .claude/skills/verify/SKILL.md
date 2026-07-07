---
name: verify
description: Visual verification of the gui_next renderer via tools/browser_driver.mjs — screenshot all major screens, review for defects, PASS/FAIL verdict. Only runs when the user explicitly invokes it.
---

# Visual Verification

Drive the gui_next renderer with `tools/browser_driver.mjs` (Playwright
Chromium against the Vite build — no Electron, no Xvfb), capture every major
screen, review each screenshot, and give a PASS/FAIL verdict.

This skill is the **explicit, user-invoked exception** to the repo rule
"no screenshots to verify GUI changes". Never run it on your own initiative
after a code change — only when the user invokes `/verify`.

## Steps

1. Ensure the Flask backend is running on port 5174 (the renderer needs it for
   live data). If not running, start it and confirm it responds:
   ```bash
   curl -s http://127.0.0.1:5174/api/status || echo "backend not up"
   ```
2. Run the full screen tour (builds gui_next first, screenshots land in
   `.debug/`):
   ```bash
   node tools/browser_driver.mjs session tools/debug_screens.json
   ```
   Add `--no-build` only if the build already ran this session.
3. Read every screenshot in `.debug/` with the Read tool and review for:
   blank/white screens, missing data (backend errors), broken layout or
   clipped text, untranslated i18n keys showing raw `section.key` strings,
   and console errors reported by the driver.
4. Verdict in chat: one line per screen (`screen | PASS/FAIL | issue`), then
   an overall PASS/FAIL.
5. Any new defect found → add an Open `BUG-<NNN>` entry to `BUGS.md` in the
   standard format (next free number; check `BUGS_DONE.md` too so numbers
   don't collide).

## Notes

- For a single screen, use `node tools/browser_driver.mjs navigate <route>
  <file.png>` instead of the full session.
- The driver stubs `window.api` (Electron preload bridge), so file-picker
  flows can't be exercised here — note them as "not verifiable" rather than
  FAIL.
- Screenshot artifacts in `.debug/` are disposable; don't commit them.
