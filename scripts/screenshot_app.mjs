#!/usr/bin/env node
/**
 * Headless screenshot of the LosslessBob Electron app.
 * Requires: xvfb-run (sudo apt install xvfb)
 * Usage:  xvfb-run node scripts/screenshot_app.mjs [route] [output.png]
 *   route  — hash route without '#/', e.g. lookup, search, home (default: lookup)
 *   output — output path (default: screenshot-<route>.png)
 *
 * Example:
 *   xvfb-run node scripts/screenshot_app.mjs lookup
 *   xvfb-run node scripts/screenshot_app.mjs collection collection.png
 */

import { createRequire } from 'module'
import path from 'path'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'
import { createConnection } from 'net'

const guiRootEarly = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'gui_next')
const require = createRequire(path.join(guiRootEarly, 'package.json'))
const { _electron: electron } = require('playwright-core')

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.join(__dirname, '..')
const guiRoot     = path.join(projectRoot, 'gui_next')

const FLASK_PORT = 5174
const route   = process.argv[2] ?? 'lookup'
const outFile = process.argv[3] ?? path.join(projectRoot, `screenshot-${route}.png`)

function portOpen(port) {
  return new Promise(resolve => {
    const s = createConnection({ host: '127.0.0.1', port }, () => { s.destroy(); resolve(true) })
    s.on('error', () => resolve(false))
    s.setTimeout(300, () => { s.destroy(); resolve(false) })
  })
}

async function waitForPort(port, tries = 60, intervalMs = 500) {
  for (let i = 0; i < tries; i++) {
    if (await portOpen(port)) return true
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

async function ensureFlask() {
  if (await portOpen(FLASK_PORT)) {
    console.log('Flask already running.')
    return null
  }
  console.log('Starting Flask backend…')
  const python = path.join(projectRoot, '.venv', 'bin', 'python3')
  const proc = spawn(python, [path.join(projectRoot, 'run_backend.py')], {
    cwd: projectRoot,
    stdio: 'pipe',
    detached: false,
  })
  proc.stderr.on('data', d => process.stderr.write(`[flask] ${d}`))
  const ready = await waitForPort(FLASK_PORT)
  if (!ready) throw new Error('Flask did not start within 30 s')
  console.log('Flask ready.')
  return proc
}

;(async () => {
  const flaskProc = await ensureFlask()

  console.log(`Launching Electron — route: /${route}`)

  const app = await electron.launch({
    executablePath: path.join(guiRoot, 'node_modules', '.bin', 'electron'),
    args: [path.join(guiRoot, 'out', 'main', 'index.js')],
    env: {
      ...process.env,
      NODE_ENV: 'production',
    },
  })

  const win = await app.firstWindow()

  // Wait for the renderer to finish its initial load
  await win.waitForLoadState('domcontentloaded')

  // Navigate to the requested hash route
  if (route !== 'home' && route !== '/') {
    await win.evaluate((r) => {
      window.location.hash = `#/${r}`
    }, route)
  }

  // Wait for network to settle (API calls from the screen)
  await win.waitForLoadState('networkidle').catch(() => {})

  // Extra settle time for React renders
  await new Promise(r => setTimeout(r, 1500))

  await win.screenshot({ path: outFile, fullPage: false })
  console.log(`Screenshot saved: ${outFile}`)

  await app.close()
  if (flaskProc) flaskProc.kill()
})().catch(err => {
  console.error(err)
  process.exit(1)
})
