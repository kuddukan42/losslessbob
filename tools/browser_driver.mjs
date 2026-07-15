#!/usr/bin/env node
/**
 * LosslessBob Browser Driver — Playwright Chromium automation against the
 * Vite renderer (no Electron, no Xvfb, no display manipulation).
 *
 * Usage:
 *   node tools/browser_driver.mjs [--no-build] [--keep] [--preview] [--no-server] <action> [args...]
 *
 * Actions:
 *   screenshot [file]              Save screenshot to .debug/<file> (default: shot.png)
 *   navigate <route> [file]        Navigate to hash route, then screenshot
 *   click <selector>               Click an element (CSS selector)
 *   fill <selector> <value>        Fill an input field
 *   eval <js>                      Evaluate JS expression, print result
 *   resize <w> <h> [file]          Resize the viewport, optional screenshot
 *   size-matrix [prefix]           Screenshot at 1280x768/1440x900/1920x1080/2560x1440
 *   watch <interval_ms> <max_ms> <prefix> [until-selector]
 *                                  Screenshot every interval_ms until the
 *                                  selector appears or max_ms elapses
 *   session <json|path>            Run a JSON action sequence (array or {actions:[...]})
 *
 * Flags:
 *   --no-build    Skip 'npm run build' (dev server mode always skips the build)
 *   --keep        Keep the browser open after actions complete
 *   --preview     Use 'npm run preview' (port 4173) instead of 'npm run dev' (port 5173)
 *   --no-server   Don't spawn a server — assume one is already running on the target port
 *
 * Session action types: screenshot, navigate, click, fill, type, clear,
 *   wait, wait-for, eval, hover, scroll-to, select, resize, size-matrix, watch
 *   (see tools/driver_core.mjs). `main-eval` is also a shared action type but
 *   always fails cleanly here — this tier has no Electron main process (no
 *   `caps.mainEval`); use tools/electron_driver.mjs for that. `scale-matrix`
 *   is not offered here either — it relaunches Electron per scale, which has
 *   no equivalent for a persistent Chromium `page.setViewportSize()` tab.
 */

import { chromium } from 'playwright'
import { spawnSync, spawn } from 'child_process'
import { existsSync, mkdirSync, readFileSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { runActions, parseSessionArg } from './driver_core.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname  = dirname(__filename)
const ROOT       = resolve(__dirname, '..')
const GUI_DIR    = join(ROOT, 'gui_next')
const DEBUG_DIR  = join(ROOT, '.debug')

const DEV_PORT     = 5173
const PREVIEW_PORT = 4173

// Stub for window.api (the Electron preload bridge) — see
// gui_next/src/renderer/src/env.d.ts for the real shape.
const API_SHIM = `
  window.api = {
    flaskPort: 5174,
    flaskBase: 'http://127.0.0.1:5174',
    pickFolders: async () => [],
    pickDir: async () => null,
    pickFile: async () => null,
    openPath: async () => '',
    saveFile: async () => false,
    pickAndReadFile: async () => null,
    pickAndReadFiles: async () => [],
  }
`

function log(...args) {
  process.stderr.write('[browser-driver] ' + args.join(' ') + '\n')
}

function ensureDebugDir() {
  if (!existsSync(DEBUG_DIR)) mkdirSync(DEBUG_DIR, { recursive: true })
}

async function build() {
  log('Building renderer...')
  const result = spawnSync('npm', ['run', 'build'], {
    cwd: GUI_DIR,
    stdio: 'inherit',
  })
  if (result.status !== 0) throw new Error(`Build failed (exit ${result.status})`)
  log('Build complete.')
}

async function waitForServer(url, maxMs = 15000, intervalMs = 200) {
  const deadline = Date.now() + maxMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(intervalMs) })
      if (res.ok || res.status < 500) return true
    } catch { /* not ready yet */ }
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

function startServer(preview) {
  const script = preview ? 'preview' : 'dev'
  log(`Starting 'npm run ${script}'...`)
  const proc = spawn('npm', ['run', script], {
    cwd: GUI_DIR,
    stdio: 'pipe',
  })
  proc.stdout?.on('data', (d) => process.stderr.write(`[${script}] ${d}`))
  proc.stderr?.on('data', (d) => process.stderr.write(`[${script}] ${d}`))
  return proc
}

async function runSession(actions, opts) {
  const { preview, noServer, keepOpen } = opts
  const port    = preview ? PREVIEW_PORT : DEV_PORT
  const baseUrl = `http://localhost:${port}`

  let serverProc = null
  if (!noServer) {
    serverProc = startServer(preview)
  }

  log(`Waiting for server at ${baseUrl}...`)
  const ready = await waitForServer(baseUrl)
  if (!ready) {
    serverProc?.kill('SIGTERM')
    throw new Error(`Server did not respond at ${baseUrl} within timeout.`)
  }

  log('Launching Chromium...')
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await context.addInitScript({ content: API_SHIM })
  const page = await context.newPage()

  log(`Navigating to ${baseUrl}...`)
  await page.goto(baseUrl)
  await page.waitForLoadState('domcontentloaded')

  // Wait for the splash overlay to detach from the DOM (skip if Flask isn't running).
  log('Waiting for splash to clear...')
  try {
    await page.waitForSelector('[data-testid="splash-overlay"]', { state: 'detached', timeout: 10000 })
  } catch (err) {
    log(`splash overlay did not clear: ${err.message} — continuing anyway`)
  }

  // Tier A capability for driver_core's shared action runner (§6): resize
  // maps to a Playwright viewport resize (not a real OS window — there is
  // no window here). No `mainEval` — Chromium tier has no main process, so
  // that key is left undefined and the action fails cleanly per-step.
  const caps = {
    resize: async (w, h) => {
      await page.setViewportSize({ width: w, height: h })
    },
  }

  const results = await runActions(page, actions, { debugDir: DEBUG_DIR, log, caps })

  if (keepOpen) {
    log('--keep: browser left open. Ctrl+C to exit.')
    await new Promise(() => {})  // block forever
  }

  await browser.close()
  if (serverProc) serverProc.kill('SIGTERM')
  return results
}

// ── CLI ────────────────────────────────────────────────────────────────────────

const argv      = process.argv.slice(2)
const noBuild   = argv.includes('--no-build')
const keep      = argv.includes('--keep')
const preview   = argv.includes('--preview')
const noServer  = argv.includes('--no-server')
const args      = argv.filter(a => !a.startsWith('--'))
const cmd       = args[0]

async function main() {
  if (!cmd) {
    process.stderr.write([
      'Usage: node tools/browser_driver.mjs [--no-build] [--keep] [--preview] [--no-server] <action> [args]',
      '',
      'Actions:',
      '  screenshot [file]           Take screenshot (.debug/<file>, default shot.png)',
      '  navigate <route> [file]     Navigate to route + screenshot',
      '  click <selector>            Click element',
      '  fill <selector> <value>     Fill input',
      '  eval <js>                   Evaluate JS expression',
      '  resize <w> <h> [file]       Resize viewport, optional screenshot',
      '  size-matrix [prefix]        Screenshot at 1280x768/1440x900/1920x1080/2560x1440',
      '  watch <interval_ms> <max_ms> <prefix> [until-selector]',
      '                              Screenshot every interval until selector/timeout',
      '  session <json|path>         Run a JSON action sequence',
      '',
      'Flags:',
      '  --no-build    Skip npm run build (dev mode always skips)',
      '  --keep        Leave browser open after actions',
      '  --preview     Use npm run preview (port 4173) instead of npm run dev (port 5173)',
      '  --no-server   Assume a server is already running on the target port',
    ].join('\n') + '\n')
    process.exit(1)
  }

  if (preview && !noBuild) await build()

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

    case 'resize': {
      if (!args[1] || !args[2]) { console.error('resize requires w and h'); process.exit(1) }
      actions = [{
        action: 'resize', w: parseInt(args[1], 10), h: parseInt(args[2], 10), file: args[3],
      }]
      break
    }

    case 'size-matrix':
      actions = [{ action: 'size-matrix', prefix: args[1] ?? 'size' }]
      break

    case 'watch': {
      if (!args[1] || !args[2] || !args[3]) {
        console.error('watch requires interval_ms, max_ms, and prefix'); process.exit(1)
      }
      actions = [{
        action: 'watch',
        interval_ms: parseInt(args[1], 10),
        max_ms: parseInt(args[2], 10),
        prefix: args[3],
        until: args[4],
      }]
      break
    }

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
    const results = await runSession(actions, { preview, noServer, keepOpen: keep })
    console.log(JSON.stringify(results, null, 2))
    const failed = results.filter(r => !r.ok)
    if (failed.length) {
      process.stderr.write(`\n${failed.length} action(s) failed.\n`)
      process.exit(1)
    }
  } catch (err) {
    console.error(`Fatal: ${err.message}`)
    process.exit(1)
  }
}

main().catch(err => { console.error(err); process.exit(1) })
