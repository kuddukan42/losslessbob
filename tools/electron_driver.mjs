#!/usr/bin/env node
/**
 * LosslessBob Electron Driver (Tier B) — Playwright `_electron.launch()`
 * against the REAL built app (gui_next/out/main/index.js), on the display
 * backend tools/electron_preflight.mjs already selected (Xvfb, recorded in
 * tools/electron_driver.config.json `.selected`). Same session-JSON action
 * format as tools/browser_driver.mjs (Tier A, Chromium vs the Vite build) —
 * see instructions/FABLE_VISUAL_VERIFICATION.md §3, §6 (Bite 2).
 *
 * This driver does NOT re-probe display backends — it reads the committed
 * config and reuses the Xvfb lifecycle + socket-discovery helpers from
 * ./electron_display.mjs (shared with electron_preflight.mjs) and the
 * action-runner from ./driver_core.mjs (shared with browser_driver.mjs).
 *
 * Usage:
 *   node tools/electron_driver.mjs [--no-build] [--keep] <action> [args...]
 *
 * Actions:
 *   screenshot [file]              Save screenshot to .debug/electron/<file>
 *                                  (default: shot.png; absolute paths win)
 *   navigate <route> [file]        Navigate to hash route, then screenshot
 *   click <selector>               Click an element (CSS selector)
 *   fill <selector> <value>        Fill an input field
 *   eval <js>                      Evaluate JS expression, print result
 *   session <json|path>            Run a JSON action sequence (array or {actions:[...]})
 *
 * Flags:
 *   --no-build    Skip 'npm run build' in gui_next/ (assumes out/ is current)
 *   --keep        Keep the app (and Xvfb) open after actions complete
 *
 * Session action types: screenshot, navigate, click, fill, type, clear,
 *   wait, wait-for, eval, hover, scroll-to, select (see tools/driver_core.mjs)
 *
 * Hard constraints honored here (do not relax without updating the spec):
 *   - LB_NO_BACKEND_SPAWN=1 is always set — the manually-started Flask
 *     backend on :5174 must survive a full driver session.
 *   - --disable-gpu and --no-sandbox always (from the selected config).
 *   - Screenshots only via Playwright page.screenshot() — no
 *     compositor/portal/VNC/grim/scrot.
 *   - ready-to-show never fires under Playwright (index.ts:146 gates
 *     win.show() on it) — this driver always forces show() via
 *     app.evaluate() after firstWindow().
 *   - Xvfb (and the Electron app) are killed on both the success and error
 *     paths — never left running behind a driver invocation.
 */

import { _electron } from 'playwright'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { runActions, parseSessionArg, ensureDir } from './driver_core.mjs'
import { discoverX11Displays, pickFreeXvfbDisplay, startXvfb } from './electron_display.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname  = dirname(__filename)
const ROOT       = resolve(__dirname, '..')
const GUI_DIR    = join(ROOT, 'gui_next')
// Tier B gets its own output dir so a shared, tier-agnostic session file
// (tools/debug_screens.json) can't have Electron PNGs silently overwrite the
// Chromium ones — Tier A keeps writing straight to .debug/ (see
// tools/browser_driver.mjs; /verify depends on those paths). Covered by the
// existing `.debug/` .gitignore rule.
const DEBUG_DIR  = join(ROOT, '.debug', 'electron')
const MAIN_ENTRY = join(GUI_DIR, 'out/main/index.js')
const ELECTRON_BIN = join(GUI_DIR, 'node_modules/electron/dist/electron')
const CONFIG_PATH  = join(ROOT, 'tools/electron_driver.config.json')

const BACKEND_URL     = 'http://127.0.0.1:5174/api/status'
const LAUNCH_TIMEOUT_MS = 45000

function log(...args) {
  process.stderr.write('[electron-driver] ' + args.join(' ') + '\n')
}

function ensureDebugDir() {
  ensureDir(DEBUG_DIR)
}

function build() {
  log("Building gui_next ('npm run build')...")
  const result = spawnSync('npm', ['run', 'build'], { cwd: GUI_DIR, stdio: 'inherit' })
  if (result.status !== 0) throw new Error(`Build failed (exit ${result.status})`)
  log('Build complete.')
}

function curlBackendStatus() {
  const result = spawnSync('curl', ['-s', '-m', '3', BACKEND_URL], { encoding: 'utf8' })
  return {
    exitCode: result.status,
    stdout: (result.stdout || '').trim(),
    ok: result.status === 0,
  }
}

function loadSelectedConfig() {
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(
      `${CONFIG_PATH} not found — run tools/electron_preflight.mjs first (Bite 1).`,
    )
  }
  const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
  if (!config.selected) {
    throw new Error(
      `${CONFIG_PATH} has no "selected" backend recorded — the preflight matrix ` +
      'has not been reviewed/decided yet (see FABLE_VISUAL_VERIFICATION.md §4/§7).',
    )
  }
  return config.selected
}

// ── Launch + session ────────────────────────────────────────────────────────

async function runSession(actions, opts) {
  const { keepOpen } = opts
  const selected = loadSelectedConfig()
  log(`display backend: ${selected.name} (flags: ${selected.flags.join(' ')})`)

  if (!existsSync(MAIN_ENTRY)) {
    throw new Error(`Main entry not found: ${MAIN_ENTRY} — build gui_next first.`)
  }
  if (!existsSync(ELECTRON_BIN)) {
    throw new Error(`Electron binary not found: ${ELECTRON_BIN}`)
  }

  log('--- backend status before launch ---')
  const preStatus = curlBackendStatus()
  log(`GET ${BACKEND_URL} -> exit=${preStatus.exitCode} body=${preStatus.stdout.slice(0, 200)}`)

  const existingDisplays = discoverX11Displays()
  const displayNum = pickFreeXvfbDisplay(existingDisplays)
  const xvfbScreen = selected.xvfbScreen || '2560x1440x24'

  log(`starting Xvfb on :${displayNum} (screen ${xvfbScreen})...`)
  const xvfbProc = await startXvfb(displayNum, xvfbScreen)

  const env = { ...process.env }
  delete env.DISPLAY
  delete env.WAYLAND_DISPLAY
  Object.assign(env, selected.requiredEnv || { LB_NO_BACKEND_SPAWN: '1' })
  env.DISPLAY = `:${displayNum}`

  let app = null
  let results = []

  try {
    log('launching Electron...')
    app = await _electron.launch({
      executablePath: ELECTRON_BIN,
      args: [MAIN_ENTRY, ...selected.flags],
      cwd: GUI_DIR,
      env,
      timeout: LAUNCH_TIMEOUT_MS,
    })

    const page = await app.firstWindow({ timeout: LAUNCH_TIMEOUT_MS })
    log('firstWindow() resolved.')

    // ready-to-show never fires under Playwright's _electron.launch() (see
    // gui_next/src/main/index.ts:154 — win.on('ready-to-show', () => win.show())).
    // app.evaluate()'s callback has no `require` in scope; destructure BrowserWindow
    // off the callback's first argument instead of requiring 'electron' again.
    await app.evaluate(({ BrowserWindow }) => {
      const w = BrowserWindow.getAllWindows()[0]
      if (w) w.show()
    })
    log('forced window show() via app.evaluate().')

    await page.waitForTimeout(800) // let renderer settle/paint

    log('waiting for splash to clear...')
    try {
      await page.waitForSelector('[data-testid="splash-overlay"]', { state: 'detached', timeout: 10000 })
    } catch (err) {
      log(`splash overlay did not clear: ${err.message} — continuing anyway`)
    }

    ensureDebugDir()
    results = await runActions(page, actions, { debugDir: DEBUG_DIR, log })

    if (keepOpen) {
      log('--keep: app left open. Ctrl+C to exit.')
      await new Promise(() => {}) // block forever
    }
  } finally {
    if (app) {
      try { await app.close() } catch { /* best effort */ }
    }
    try { xvfbProc.kill('SIGTERM') } catch { /* best effort */ }
  }

  log('--- backend status after run (must survive) ---')
  const postStatus = curlBackendStatus()
  log(`GET ${BACKEND_URL} -> exit=${postStatus.exitCode} body=${postStatus.stdout.slice(0, 200)}`)
  if (postStatus.exitCode !== 0 || !postStatus.stdout) {
    log('WARNING: backend on :5174 does not appear to be responding after the run.')
  }

  return results
}

// ── CLI ────────────────────────────────────────────────────────────────────

const argv     = process.argv.slice(2)
const noBuild  = argv.includes('--no-build')
const keep     = argv.includes('--keep')
const args     = argv.filter(a => !a.startsWith('--'))
const cmd      = args[0]

async function main() {
  if (!cmd) {
    process.stderr.write([
      'Usage: node tools/electron_driver.mjs [--no-build] [--keep] <action> [args]',
      '',
      'Actions:',
      '  screenshot [file]           Take screenshot (.debug/electron/<file>, default shot.png)',
      '  navigate <route> [file]     Navigate to route + screenshot',
      '  click <selector>            Click element',
      '  fill <selector> <value>     Fill input',
      '  eval <js>                   Evaluate JS expression',
      '  session <json|path>        Run a JSON action sequence',
      '',
      'Flags:',
      '  --no-build    Skip npm run build (assumes gui_next/out is current)',
      '  --keep        Leave the app (and Xvfb) open after actions',
    ].join('\n') + '\n')
    process.exit(1)
  }

  if (!noBuild) build()

  let actions = []

  switch (cmd) {
    case 'screenshot':
      actions = [{ action: 'screenshot', file: args[1] ?? 'shot.png' }]
      break

    case 'navigate': {
      const route = args[1] ?? '/'
      const file  = args[2] ?? (route.replace(/^\//, '') || 'home') + '.png'
      actions = [
        { action: 'navigate', route },
        { action: 'screenshot', file },
      ]
      break
    }

    case 'click':
      if (!args[1]) { console.error('click requires a selector'); process.exit(1) }
      actions = [{ action: 'click', selector: args[1] }]
      break

    case 'fill':
      if (!args[1] || args[2] === undefined) {
        console.error('fill requires selector and value'); process.exit(1)
      }
      actions = [{ action: 'fill', selector: args[1], value: args[2] }]
      break

    case 'eval':
      if (!args[1]) { console.error('eval requires a JS expression'); process.exit(1) }
      actions = [{ action: 'eval', js: args[1] }]
      break

    case 'session': {
      if (!args[1]) { console.error('session requires JSON or a file path'); process.exit(1) }
      actions = parseSessionArg(args[1], existsSync, readFileSync)
      break
    }

    default:
      console.error(`Unknown action: ${cmd}`)
      process.exit(1)
  }

  try {
    const results = await runSession(actions, { keepOpen: keep })
    console.log(JSON.stringify(results, null, 2))
    const failed = results.filter(r => !r.ok)
    if (failed.length) {
      process.stderr.write(`\n${failed.length} action(s) failed.\n`)
      process.exit(1)
    }
  } catch (err) {
    console.error(`Fatal: ${err.stack || err.message}`)
    process.exit(1)
  }
}

main().catch(err => { console.error(err); process.exit(1) })
