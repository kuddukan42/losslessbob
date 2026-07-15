# Visual Verification Driver — Design Spec (attempt 3)

Spec author: Fable 5, 2026-07-14. Execution target: Sonnet session(s), one bite per session.
Goal: Claude can drive the real gui_next app — open screens, click, resize the window, vary
display scale, and watch progress meters over time — and *see* the results as PNGs, reliably,
on this machine (Debian, Wayland, NVIDIA).

---

## 1. Problem and history

Two prior attempts at screenshot verification failed or fell short:

1. **`gui_next/gui_driver.mjs`** (2026-06-04, removed 2026-06-10): Playwright + real Electron
   + auto-started Xvfb. "Consistently failed in this sandbox — Electron CDP target never
   connects / GTK aborts under headless ozone" (CHANGELOG 2026-06-10).
2. **Docker Xvfb + x11vnc + noVNC** (CHANGELOG_ARCHIVE, docker/): screenshots via a virtual
   display captured from *outside* the app. Heavyweight, brittle, abandoned.

What survives is `tools/browser_driver.mjs`: Playwright **Chromium** (not Electron) against the
Vite renderer build, `window.api` stubbed. It works — `/verify` uses it — but it cannot answer
the questions tj actually has: real window chrome, real `window.api`/IPC behavior, real window
resizing (not just viewport), OS-level display scaling, main-process behavior (backend spawn,
file associations), and anything behind the preload bridge.

## 2. Root-cause analysis — why attempts 1–2 failed, and why Wayland/NVIDIA is a red herring

**The losing pattern is capturing pixels from outside the app** (compositor grab, VNC, screen
capture). On Wayland that path is deliberately locked down (portal permission prompts, no
`grim` on GNOME/Mutter) and NVIDIA adds GL/EGL flakiness on top (see BUG-053, BUG-090 history
in CHANGELOG_ARCHIVE: EGL_BAD_NATIVE_WINDOW crashes, black-screen flickers).

**The winning pattern captures from inside the render pipeline.** Playwright's
`page.screenshot()` and Electron's `webContents.capturePage()` go through CDP
`Page.captureScreenshot` — Chromium renders the frame itself and hands back a PNG. The Wayland
compositor and the NVIDIA driver are never involved, and with `--disable-gpu` (SwiftShader
software raster) the NVIDIA stack is out of the loop entirely. `browser_driver.mjs` already
proves this works here. The only unsolved part is getting *Electron itself* to boot and accept
a CDP connection on this machine — which is a launch/environment problem, not a capture problem.

Likely culprits for attempt 1's launch failures (each gets a preflight check in §4):

- **Debian AppArmor userns restriction**: Debian 13+ sets
  `kernel.apparmor_restrict_unprivileged_userns=1`; unprofiled Electron binaries abort at the
  Chromium SUID/userns sandbox step. Fix for a dev-only driver: launch with `--no-sandbox`
  (acceptable — it renders only our local app content).
- **Claude Code bash sandbox**: can block X11/Wayland sockets and the CDP pipe. The 06-10
  failure note says "in this sandbox" explicitly. Probe both sandboxed and
  sandbox-disabled; whichever works becomes a documented pre-approved rule.
- **GTK needs a display**: Electron on Linux initialises GTK before honoring ozone flags, so
  "headless ozone" still aborted without any display. Xvfb or the real Wayland session must
  back whichever ozone platform is chosen.
- **NVIDIA GLX on a virtual display**: Xvfb has no GPU; Chromium must be told
  `--disable-gpu` or it can hang probing GL. Attempt 1 did not force this.

## 3. Architecture — two tiers, one session format

| Tier | Tool | Boots | Use for |
|---|---|---|---|
| A (exists) | `tools/browser_driver.mjs` | Chromium headless vs Vite build | fast layout/screen checks — keep as `/verify` default |
| B (new) | `tools/electron_driver.mjs` | real Electron app via Playwright `_electron.launch()` | window resize, scale, preload/IPC, main-process behavior, progress watching |

Both tiers accept the same session-JSON action format (`tools/debug_screens.json` stays
reusable), the same `data-testid` selector discipline (see CLAUDE.md "verification gotchas"
history, CHANGELOG 2026-06-10), and both write PNGs to `.debug/` for review with the Read tool.
If action-runner code is shared, extract it to `tools/driver_core.mjs`; don't fork two copies.

Playwright's Electron support lives in `playwright-core` (already a gui_next devDependency,
^1.60 — verify it supports Electron 42's bundled Chromium; bump the pin if launch errors
mention protocol mismatch). Launch shape:

```js
const app = await _electron.launch({
  args: [join(GUI_DIR, 'out/main/index.js'), ...displayFlags],  // build first
  cwd: GUI_DIR,
  env: { ...process.env, LB_NO_BACKEND_SPAWN: '1', ...displayEnv },
})
const page = await app.firstWindow()
```

`npm run build` must precede launch (same as browser_driver's default; honor `--no-build`).

## 4. Phase 0 — display preflight probe (the anti-third-failure device)

Do **not** pick a display backend on paper. Ship `tools/electron_preflight.mjs` first: it
tries each backend on the actual machine, in order, and records the first one where Electron
launches, `firstWindow()` resolves, and a screenshot PNG comes back non-blank. Result is
written to `tools/electron_driver.config.json` (committed) and `electron_driver.mjs` just
reads it — no per-run guessing.

Probe matrix (each row also tried with `--no-sandbox` appended; record which was needed):

| # | Backend | Flags / env | Notes |
|---|---|---|---|
| 1 | native Wayland | `--ozone-platform=wayland --disable-gpu`; inherit `WAYLAND_DISPLAY` | window appears on tj's desktop — fine, even useful |
| 2 | XWayland | `--ozone-platform=x11 --disable-gpu`; inherit `DISPLAY` | app history shows xcb is stable here when GPU quirks are avoided |
| 3 | Xvfb | `xvfb-run -a` wrapper + `--ozone-platform=x11 --disable-gpu` | needs `xvfb` apt package; fully invisible |
| 4 | ozone headless | `--ozone-platform=headless --disable-gpu` | may still hit the GTK abort; try last |

Preflight also reports (informational, printed before the matrix runs):
`sysctl kernel.apparmor_restrict_unprivileged_userns`, whether `xvfb-run` exists, and
`$WAYLAND_DISPLAY`/`$DISPLAY`. If all sandboxed probes fail, rerun with the Claude bash
sandbox disabled and note that requirement in the config + `.claude/settings.json` rule.

Gotcha to verify per backend: `index.ts:146` shows the window only on `ready-to-show`. If that
event doesn't fire on a backend, screenshots may be blank — fall back to forcing
`win.show()` via `app.evaluate()` and/or `webContents.capturePage()` (works unmapped).

## 5. App-side changes (small, dev-only)

- **`LB_NO_BACKEND_SPAWN=1`**: `ensureBackend()` (gui_next/src/main/index.ts:88) currently
  kills whatever owns port 5174 and spawns its own backend. A driver run must not murder the
  manually-started backend mid-session. Gate: if the env var is set (and `!app.isPackaged`),
  skip `ensureBackend()` entirely and assume 5174 is up. Driver sets it always; `/verify`
  keeps the existing "backend up first" step.
- **Progress fixture**: a dev-gated Flask route (suggest `/api/debug/progress_job`, enabled
  only when `LB_DEBUG_ENDPOINTS=1`) that starts a fake job advancing 0→100% over N seconds
  (param). It must ride the **same** job/progress transport the pipeline screen already polls
  — inspect ScreenPipeline.tsx's data source and feed that path; a parallel fake channel
  verifies nothing. This makes progress-meter rendering deterministic and repeatable without
  staging real folders. (Real-folder runs remain possible; the fixture is for UI verification.)

## 6. Driver command surface (Tier B)

Same CLI/session shape as browser_driver, plus:

| Action | Args | Behavior |
|---|---|---|
| `resize` | `w h [file]` | `BrowserWindow.setSize` via `app.evaluate`, settle ~300ms, optional screenshot |
| `size-matrix` | `[prefix]` | screenshots at 1280×768 (app min — index.ts:133), 1440×900 (default), 1920×1080, 2560×1440 |
| `scale-matrix` | `[prefix]` | relaunch per `--force-device-scale-factor` ∈ {1, 1.25, 1.5, 2}, same route each time |
| `watch` | `interval_ms max_ms prefix [until-selector]` | screenshot every interval until selector appears/timeout → `prefix-000.png…`; for progress meters |
| `main-eval` | `js` | evaluate in the main process (`app.evaluate`) — window state, IPC pokes |

Notes: don't test below 1280×768 — the app enforces its min size by design. `resize` on
Wayland: `setSize` works; `setPosition` is a Wayland no-op — never rely on window position.
Review discipline for `watch` frames: Read every frame, report first-frame %, last-frame %,
and whether intermediate frames are monotonic — that's the "watch the meter fill" deliverable.

## 7. Integration & bookkeeping

- `/verify` skill: add a `--electron` mode (Tier B full tour) while keeping the Chromium tour
  as the default fast path. The rule stands: screenshot verification is **user-invoked only**
  (memory + CLAUDE.md); this spec expands capability, not initiative.
- `.claude/settings.json`: pre-approve `node tools/electron_driver.mjs …` and
  `node tools/electron_preflight.mjs …` Bash rules (mirroring the existing browser_driver
  rule), with whatever sandbox setting Phase 0 proved necessary.
- Docs: PROJECT.md tooling section + CLAUDE.md GUI-verification note (one line each);
  CHANGELOG entries per bite; assign a TODO (next free at time of writing: TODO-240).
- `.debug/` artifacts stay disposable and uncommitted; `electron_driver.config.json` is the
  one committed output of Phase 0.

## 8. Execution plan — 4 bites (one usage chunk each)

| Bite | Deliverable | Done when |
|---|---|---|
| 1 | `electron_preflight.mjs` + probe run on this machine + committed config + settings rules | a real screenshot PNG of the booted app exists in `.debug/` and the winning backend is recorded |
| 2 | `electron_driver.mjs` MVP (launch/screenshot/navigate/click/fill/eval/session via shared core) + `LB_NO_BACKEND_SPAWN` | full `debug_screens.json` tour passes on Tier B |
| 3 | `resize`, `size-matrix`, `scale-matrix`, `watch` + progress fixture endpoint | size matrix PNGs reviewed; watch captures a fixture job filling 0→100% |
| 4 | `/verify --electron`, docs, CHANGELOG/TODO bookkeeping, move this spec to complete/ | `/verify --electron` produces a full PASS/FAIL verdict end-to-end |

Resume tracking (update in place, per usage-pacing convention):

```
[x] Bite 1 — preflight        (DONE 2026-07-15 — backend decided: Xvfb)
[x] Bite 2 — driver MVP       (DONE 2026-07-15 — full tour passes on Tier B)
[ ] Bite 3 — resize/scale/watch (not started)
[ ] Bite 4 — skill + docs     (not started — incl. CHANGELOG/TODO bookkeeping)
```

### Findings from bites 1–2 (amend §4/§6 — read before Bite 3)

1. **Display env is never inherited.** §4 says rows 1/2 inherit `WAYLAND_DISPLAY`/`DISPLAY`;
   in reality the shell has both empty with `XDG_SESSION_TYPE=tty`. The sockets exist and are
   reachable (`/run/user/1000/wayland-0`, `/tmp/.X11-unix/X0`) but must be **discovered and set
   explicitly**. This is a likely contributor to the 2026-06-04 attempt's failure — the backend
   was never the problem, the missing env was.
2. **`ready-to-show` never fires under Playwright**, on any backend (not backend-specific).
   `index.ts:146` gates `win.show()` on it, so every driver must force show via `app.evaluate()`.
   The §4 gotcha was real and is now handled in `electron_driver.mjs`.
3. **`app.evaluate()` has no `require` in scope** — destructure the electron module off the
   callback's first arg: `app.evaluate(({ BrowserWindow }) => …)`.
4. **XWayland (row 2) needs an Xauthority cookie**, `/run/user/1000/.mutter-Xwaylandauth.<rand>`,
   random per session — one reason it lost to Xvfb.
5. **Xvfb chosen over the working Wayland/XWayland rows** (all three booted fine, ~1.6s each).
   Decisive reason: a window cannot exceed its screen — row 3 was clamped to 1280×771 by a
   1280×800 virtual screen. §6's `size-matrix` needs 2560×1440, which no real display here can
   satisfy, so the Xvfb screen is created at **2560×1440×24**. Xvfb is also deterministic
   (rows 1/2 disagreed on window height, 835 vs 871, from decoration variance) and
   session-independent. Full rationale in `electron_driver.config.json`'s `selected` block.
6. **Ozone headless (row 4) is dead** as §4 predicted: main process starts and CDP attaches,
   but no window is ever created — 45s timeout.
7. Tier B writes PNGs to **`.debug/electron/`**, Tier A keeps `.debug/` — the two tiers share
   `debug_screens.json` and would otherwise silently overwrite each other.
8. `electron_preflight.mjs` preserves the `selected` decision on re-run (`--reset-selection` to
   discard deliberately). Don't hand-edit the matrix; do hand-own the decision.

## 9. Acceptance criteria

1. From a cold shell: one command boots the real Electron app and saves a non-blank PNG of the
   Lookup screen, with no manual display setup and no compositor/portal interaction.
2. Window resized to each size-matrix entry with a PNG per size; layout differences visible.
3. `scale-matrix` produces visibly re-scaled UI at 1.25/1.5/2 DPR.
4. `watch` on the progress fixture yields ≥5 frames showing monotonic meter progress.
5. A manually-started backend on 5174 survives a full driver session (`LB_NO_BACKEND_SPAWN`).
6. All of the above run without touching NVIDIA GL (`--disable-gpu` in every probe row) and
   without any screen-capture API.

## 10. Out of scope

- **Legacy PyQt6 `gui/`**: same philosophy applies if ever needed — `QWidget.grab()` renders
  widget→QPixmap compositor-free, driven via a debug command socket + QTest. Not built now;
  gui_next is the active UI.
- OS-level/compositor screen capture, video recording, and pixel-diff regression baselines
  (a possible later layer on top of `.debug/` output).
- Windows/AppImage packaged-app driving (`app.isPackaged` paths).
