#!/usr/bin/env node
/**
 * LosslessBob GUI Driver — Playwright-based Electron automation
 *
 * Usage:
 *   node gui_next/gui_driver.mjs [--no-build] [--keep] <action> [args...]
 *
 * Actions:
 *   screenshot [file]              Save screenshot to .debug/<file> (default: shot.png)
 *   navigate <route> [file]        Navigate to hash route, then screenshot
 *   click <selector>               Click an element (CSS selector)
 *   fill <selector> <value>        Fill an input field
 *   eval <js>                      Evaluate JS expression, print result
 *   session <json|path>            Run a JSON action sequence (array or {actions:[...]})
 *
 * Flags:
 *   --no-build   Skip npm build step (use existing out/)
 *   --keep       Keep Electron window open after actions complete
 *
 * Session action types: screenshot, navigate, click, fill, type, clear,
 *   wait, wait-for, eval, hover, scroll-to, select
 *
 * Example session JSON:
 *   [
 *     { "action": "navigate", "route": "/lookup" },
 *     { "action": "screenshot", "file": "lookup.png" },
 *     { "action": "click", "selector": "button[type=submit]" },
 *     { "action": "screenshot", "file": "lookup-result.png" }
 *   ]
 */

import { _electron as electronLauncher } from 'playwright-core'
import { spawnSync, spawn } from 'child_process'
import { existsSync, mkdirSync, readFileSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const __filename = fileURLToPath(import.meta.url)
const __dirname  = dirname(__filename)
const ROOT       = resolve(__dirname, '..')
const GUI_DIR    = __dirname
const MAIN_JS    = join(GUI_DIR, 'out', 'main', 'index.js')
const DEBUG_DIR  = join(ROOT, '.debug')

const _require    = createRequire(import.meta.url)
const ELECTRON_BIN = _require('electron')

function log(...args) {
  process.stderr.write('[gui-driver] ' + args.join(' ') + '\n')
}

function ensureDebugDir() {
  if (!existsSync(DEBUG_DIR)) mkdirSync(DEBUG_DIR, { recursive: true })
}

async function ensureDisplay() {
  if (process.env.DISPLAY) return

  // Find a free display number (skip any that have a lock file)
  let n = 2
  while (existsSync(`/tmp/.X${n}-lock`)) n++
  const display = `:${n}`

  log(`No $DISPLAY — starting Xvfb on ${display}`)
  const xvfb = spawn('Xvfb', [display, '-screen', '0', '1440x900x24', '-ac'], {
    stdio: 'ignore',
    detached: false,
  })
  await new Promise(r => setTimeout(r, 800))
  process.env.DISPLAY = display
  process.on('exit', () => xvfb.kill())
  process.on('SIGINT', () => { xvfb.kill(); process.exit(0) })
}

async function build() {
  log('Building Electron app...')
  const result = spawnSync('npm', ['run', 'build'], {
    cwd: GUI_DIR,
    stdio: 'inherit',
  })
  if (result.status !== 0) throw new Error(`Build failed (exit ${result.status})`)
  log('Build complete.')
}

async function runSession(actions, keepOpen = false) {
  if (!existsSync(MAIN_JS)) {
    throw new Error(`Built app not found at ${MAIN_JS} — run without --no-build or build first.`)
  }

  await ensureDisplay()

  // Build env after ensureDisplay() so DISPLAY is populated
  const env = { ...process.env }
  delete env.ELECTRON_RENDERER_URL  // force use of built renderer, not Vite dev server

  log('Launching Electron...')
  const electronApp = await electronLauncher.launch({
    executablePath: ELECTRON_BIN,
    args: [MAIN_JS],
    env,
  })

  log('Waiting for window...')
  const page = await electronApp.firstWindow()
  await page.waitForLoadState('domcontentloaded')

  // Wait for the splash overlay to detach from the DOM
  log('Waiting for splash to clear...')
  await page.waitForSelector('[data-testid="splash-overlay"]', { state: 'detached', timeout: 25000 })
  await page.waitForTimeout(200)

  ensureDebugDir()

  const results = []

  for (const step of actions) {
    log(`action: ${step.action}`)
    let result = { action: step.action, ok: true }

    try {
      switch (step.action) {

        case 'screenshot': {
          const file    = step.file ?? 'shot.png'
          const outPath = join(DEBUG_DIR, file)
          await page.screenshot({ path: outPath, fullPage: step.fullPage ?? false })
          log(`screenshot saved → ${outPath}`)
          result.path = outPath
          break
        }

        case 'navigate': {
          const route = step.route ?? '/'
          await page.evaluate((r) => { window.location.hash = '#' + r }, route)
          await page.waitForTimeout(step.wait ?? 600)
          break
        }

        case 'click': {
          await page.click(step.selector, { timeout: step.timeout ?? 8000 })
          await page.waitForTimeout(step.wait ?? 250)
          break
        }

        case 'fill': {
          await page.fill(step.selector, step.value ?? '', { timeout: step.timeout ?? 5000 })
          break
        }

        case 'type': {
          await page.type(step.selector, step.value ?? '', { delay: step.delay ?? 50 })
          break
        }

        case 'clear': {
          await page.fill(step.selector, '')
          break
        }

        case 'wait': {
          await page.waitForTimeout(step.ms ?? 1000)
          break
        }

        case 'wait-for': {
          await page.waitForSelector(step.selector, { timeout: step.timeout ?? 12000 })
          break
        }

        case 'hover': {
          await page.hover(step.selector, { timeout: step.timeout ?? 5000 })
          await page.waitForTimeout(step.wait ?? 200)
          break
        }

        case 'scroll-to': {
          await page.evaluate((sel) => {
            const el = document.querySelector(sel)
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' })
          }, step.selector)
          await page.waitForTimeout(300)
          break
        }

        case 'select': {
          await page.selectOption(step.selector, step.value)
          break
        }

        case 'eval': {
          const value = await page.evaluate(step.js)
          log(`eval → ${JSON.stringify(value)}`)
          result.value = value
          break
        }

        default:
          throw new Error(`Unknown action type: "${step.action}"`)
      }
    } catch (err) {
      log(`FAILED: ${err.message}`)
      result.ok    = false
      result.error = err.message
    }

    results.push(result)
  }

  if (keepOpen) {
    log('--keep: window left open. Close it manually or Ctrl+C to exit.')
    await new Promise(() => {})  // block forever
  }

  await electronApp.close()
  return results
}

// ── CLI ────────────────────────────────────────────────────────────────────────

const argv    = process.argv.slice(2)
const noBuild = argv.includes('--no-build')
const keep    = argv.includes('--keep')
const args    = argv.filter(a => !a.startsWith('--'))
const cmd     = args[0]

async function main() {
  if (!cmd) {
    process.stderr.write([
      'Usage: node gui_next/gui_driver.mjs [--no-build] [--keep] <action> [args]',
      '',
      'Actions:',
      '  screenshot [file]           Take screenshot (.debug/<file>, default shot.png)',
      '  navigate <route> [file]     Navigate to route + screenshot',
      '  click <selector>            Click element',
      '  fill <selector> <value>     Fill input',
      '  eval <js>                   Evaluate JS expression',
      '  session <json|path>         Run a JSON action sequence',
      '',
      'Flags:',
      '  --no-build    Skip npm build',
      '  --keep        Leave window open after actions',
    ].join('\n') + '\n')
    process.exit(1)
  }

  if (!noBuild) await build()

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
      let data
      if (existsSync(args[1])) {
        data = JSON.parse(readFileSync(args[1], 'utf8'))
      } else {
        data = JSON.parse(args[1])
      }
      actions = Array.isArray(data) ? data : data.actions
      break
    }

    default:
      console.error(`Unknown action: ${cmd}`)
      process.exit(1)
  }

  try {
    const results = await runSession(actions, keep)
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
