#!/usr/bin/env node
/**
 * LosslessBob Electron Preflight — probes display backends for booting the
 * real Electron app (gui_next/out/main/index.js) under Playwright
 * `_electron.launch()`, on THIS machine, and records a full result matrix.
 *
 * This does not pick a winner. It runs all four candidate backends, records
 * launched / firstWindow() / screenshot-non-blank / timing / error for each,
 * and writes the matrix to tools/electron_driver.config.json (committed) for
 * a human/orchestrator to read and choose a default from.
 *
 * The `selected` block (the human/orchestrator's backend DECISION plus its
 * rationale) and the `notes` array are hand-recorded in that config and are
 * NOT this script's output — rerunning the probe PRESERVES them verbatim and
 * refreshes only the evidence (generatedAt/versions/informational/
 * backendStatus/matrix). tools/electron_driver.mjs reads `selected`, so
 * nulling it silently would break Tier B. Use --reset-selection for the
 * deliberate "throw the decision away" case.
 *
 * See instructions/complete/FABLE_VISUAL_VERIFICATION.md §3, §4, §7 (Bite 1).
 *
 * Usage:
 *   node tools/electron_preflight.mjs [--no-build] [--rows=1,2,3,4] [--reset-selection]
 *
 * Flags:
 *   --no-build          Skip 'npm run build' in gui_next/ (assumes out/ is current)
 *   --rows=...          Comma-separated row ids to run (default: all four)
 *   --reset-selection   Deliberately discard the recorded `selected` decision
 *                       (writes selected: null) instead of preserving it
 *
 * Hard constraints honored here (do not relax without updating the spec):
 *   - LB_NO_BACKEND_SPAWN=1 is set on every launch; the manually-started
 *     Flask backend on :5174 must survive this script end to end.
 *   - --disable-gpu and --no-sandbox on every row; NVIDIA GL is never touched.
 *   - Screenshots only via Playwright page.screenshot() or
 *     webContents.capturePage() — no compositor/portal/VNC/grim/scrot.
 */

import { _electron } from 'playwright'
import { spawnSync } from 'child_process'
import {
  existsSync, mkdirSync, writeFileSync, readFileSync,
} from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import zlib from 'zlib'
import {
  sleep, xvfbRunExists, discoverWaylandSocket, discoverMutterXauthFile,
  discoverX11Displays, pickFreeXvfbDisplay, startXvfb,
} from './electron_display.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname  = dirname(__filename)
const ROOT       = resolve(__dirname, '..')
const GUI_DIR    = join(ROOT, 'gui_next')
const DEBUG_DIR  = join(ROOT, '.debug')
const MAIN_ENTRY = join(GUI_DIR, 'out/main/index.js')
const ELECTRON_BIN = join(GUI_DIR, 'node_modules/electron/dist/electron')
const CONFIG_PATH  = join(ROOT, 'tools/electron_driver.config.json')

const BACKEND_URL   = 'http://127.0.0.1:5174/api/status'
const ROW_TIMEOUT_MS = 45000

function log(...args) {
  process.stderr.write('[electron-preflight] ' + args.join(' ') + '\n')
}

function ensureDebugDir() {
  if (!existsSync(DEBUG_DIR)) mkdirSync(DEBUG_DIR, { recursive: true })
}

// eslint-disable-next-line no-control-regex
const ANSI_RE = /\x1b\[[0-9;]*m/g
function stripAnsi(s) {
  return typeof s === 'string' ? s.replace(ANSI_RE, '') : s
}

// ── Build ────────────────────────────────────────────────────────────────────

function build() {
  log("Building gui_next ('npm run build')...")
  const result = spawnSync('npm', ['run', 'build'], { cwd: GUI_DIR, stdio: 'inherit' })
  if (result.status !== 0) throw new Error(`Build failed (exit ${result.status})`)
  log('Build complete.')
}

// ── Informational probes (printed before the matrix runs) ──────────────────

function readApparmorSysctl() {
  try {
    const val = readFileSync('/proc/sys/kernel/apparmor_restrict_unprivileged_userns', 'utf8').trim()
    return val
  } catch (err) {
    if (err.code === 'ENOENT') return 'not present on this kernel'
    return `unreadable (${err.message})`
  }
}

/**
 * Read the previously written config, if any — the source of the
 * hand-recorded `selected` decision and `notes` this rerun must preserve.
 * A malformed/absent file is not fatal: the probe still has value, we just
 * have no prior decision to carry forward.
 */
function readExistingConfig() {
  if (!existsSync(CONFIG_PATH)) return null
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
  } catch (err) {
    log(`WARNING: could not parse existing ${CONFIG_PATH} (${err.message}) — treating as absent.`)
    return null
  }
}

/**
 * Loudly flag a recorded decision the fresh matrix now contradicts (selected
 * row missing, failed to launch, or produced a blank screenshot). Never nulls
 * the decision — that is the user's call (--reset-selection).
 */
function checkSelectionAgainstMatrix(selected, results) {
  if (!selected) return
  const row = results.find((r) => r.id === selected.id)
  if (!row) {
    log(`NOTE: selected backend (row ${selected.id}, ${selected.name}) was not re-probed in this run — decision left untouched.`)
    return
  }
  const healthy = row.launched && row.firstWindowResolved && row.screenshotNonBlank
  if (healthy) {
    log(`Selected backend (row ${selected.id}, ${selected.name}) re-probed OK — decision still valid.`)
    return
  }
  const banner = '='.repeat(78)
  log(banner)
  log(`WARNING: the RECORDED DECISION no longer matches the probe results.`)
  log(`  selected: row ${selected.id} (${selected.name})`)
  log(`  this run: launched=${row.launched} firstWindow=${row.firstWindowResolved} nonBlank=${row.screenshotNonBlank}`)
  log(`  error:    ${row.error || 'none'}`)
  log('')
  log('The `selected` block has been PRESERVED (this script never silently')
  log('discards a decision), so tools/electron_driver.mjs will keep launching')
  log('the backend above even though it just failed here. Review the refreshed')
  log('matrix and re-decide; use --reset-selection to clear the decision.')
  log(banner)
}

function readVersions() {
  const electronVersion = JSON.parse(
    readFileSync(join(GUI_DIR, 'node_modules/electron/package.json'), 'utf8'),
  ).version
  const playwrightVersion = JSON.parse(
    readFileSync(join(ROOT, 'node_modules/playwright/package.json'), 'utf8'),
  ).version
  return { electronVersion, playwrightVersion, nodeVersion: process.version }
}

// Display socket discovery (§4 amendment: discover, don't inherit) lives in
// ./electron_display.mjs (shared with electron_driver.mjs).

// ── Minimal PNG decoder (no deps) — used only to prove non-blank ───────────
// Supports bit depth 8, non-interlaced, color types 0/2/3/4/6. That covers
// what Chromium's Page.captureScreenshot / nativeImage.toPNG() actually emit.

function paethPredictor(a, b, c) {
  const p = a + b - c
  const pa = Math.abs(p - a)
  const pb = Math.abs(p - b)
  const pc = Math.abs(p - c)
  if (pa <= pb && pa <= pc) return a
  if (pb <= pc) return b
  return c
}

function decodePNG(buf) {
  if (buf.length < 8 || buf.readUInt32BE(0) !== 0x89504e47) {
    throw new Error('not a PNG (bad signature)')
  }
  let offset = 8
  let ihdr = null
  const idatChunks = []
  while (offset < buf.length) {
    const length = buf.readUInt32BE(offset); offset += 4
    const type   = buf.toString('ascii', offset, offset + 4); offset += 4
    const data   = buf.subarray(offset, offset + length); offset += length
    offset += 4 // CRC, not verified
    if (type === 'IHDR') {
      ihdr = {
        width: data.readUInt32BE(0),
        height: data.readUInt32BE(4),
        bitDepth: data[8],
        colorType: data[9],
        interlace: data[12],
      }
    } else if (type === 'IDAT') {
      idatChunks.push(data)
    } else if (type === 'IEND') {
      break
    }
  }
  if (!ihdr) throw new Error('no IHDR chunk found')
  if (ihdr.bitDepth !== 8) throw new Error(`unsupported bit depth ${ihdr.bitDepth}`)
  if (ihdr.interlace !== 0) throw new Error('interlaced PNG not supported')

  const channelsByColorType = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }
  const channels = channelsByColorType[ihdr.colorType]
  if (!channels) throw new Error(`unsupported color type ${ihdr.colorType}`)

  const raw = zlib.inflateSync(Buffer.concat(idatChunks))
  const { width, height } = ihdr
  const bpp = channels // bitDepth 8 => 1 byte per channel
  const stride = width * bpp
  const out = Buffer.alloc(stride * height)
  let rawOffset = 0

  for (let y = 0; y < height; y += 1) {
    const filterType = raw[rawOffset]; rawOffset += 1
    const rowStart = y * stride
    for (let x = 0; x < stride; x += 1) {
      const rawByte = raw[rawOffset + x]
      const a = x >= bpp ? out[rowStart + x - bpp] : 0
      const b = y > 0 ? out[rowStart - stride + x] : 0
      const c = (x >= bpp && y > 0) ? out[rowStart - stride + x - bpp] : 0
      let value
      switch (filterType) {
        case 0: value = rawByte; break
        case 1: value = rawByte + a; break
        case 2: value = rawByte + b; break
        case 3: value = rawByte + Math.floor((a + b) / 2); break
        case 4: value = rawByte + paethPredictor(a, b, c); break
        default: throw new Error(`unsupported PNG filter type ${filterType}`)
      }
      out[rowStart + x] = value & 0xff
    }
    rawOffset += stride
  }

  return { width, height, channels, colorType: ihdr.colorType, pixels: out }
}

/**
 * Decides whether a PNG buffer shows real, varied content vs a single flat
 * color (blank/unpainted window). Decodes the PNG, samples pixels across the
 * image, and checks both distinct-quantized-color count and luminance range.
 */
function analyzeScreenshot(buf) {
  const { width, height, channels, colorType, pixels } = decodePNG(buf)
  const totalPixels = width * height
  const stride = Math.max(1, Math.floor(totalPixels / 5000))
  let minLum = Infinity
  let maxLum = -Infinity
  const seen = new Set()

  for (let i = 0; i < totalPixels; i += stride) {
    const off = i * channels
    const r = pixels[off]
    const g = channels > 1 ? pixels[off + 1] : r
    const b = channels > 2 ? pixels[off + 2] : r
    const lum = 0.299 * r + 0.587 * g + 0.114 * b
    if (lum < minLum) minLum = lum
    if (lum > maxLum) maxLum = lum
    seen.add(`${r >> 3},${g >> 3},${b >> 3}`)
  }

  const lumRange = maxLum - minLum
  const nonBlank = seen.size > 2 && lumRange > 4
  return { width, height, colorType, uniqueColors: seen.size, lumRange, nonBlank }
}

// ── Backend health check (curl, per hard constraint) ───────────────────────

function curlBackendStatus() {
  const result = spawnSync('curl', ['-s', '-m', '3', BACKEND_URL], { encoding: 'utf8' })
  return {
    exitCode: result.status,
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
    ok: result.status === 0,
  }
}

// Xvfb lifecycle (row 3) lives in ./electron_display.mjs — startXvfb() is
// called below with the historical 1280x800x24 default screen size (the
// probe matrix result already committed in electron_driver.config.json
// recorded that geometry; electron_driver.mjs requests 2560x1440x24 instead).

// ── Row execution ───────────────────────────────────────────────────────

function withTimeout(promise, ms, label) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

function buildEnv(row) {
  const env = { ...process.env }
  delete env.DISPLAY
  delete env.WAYLAND_DISPLAY
  env.LB_NO_BACKEND_SPAWN = '1'
  Object.assign(env, row.env || {})
  return env
}

async function runRow(row) {
  const start = Date.now()
  const result = {
    id: row.id,
    name: row.name,
    flags: row.flags,
    env: row.env || {},
    skipped: false,
    launched: false,
    firstWindowResolved: false,
    readyToShowFired: null,
    forcedShow: false,
    usedCapturePage: false,
    screenshotPath: null,
    screenshotNonBlank: null,
    screenshotDetail: null,
    ms: null,
    error: null,
  }

  if (row.skip) {
    result.skipped = true
    result.error = row.skip
    result.ms = 0
    return result
  }

  let xvfbProc = null
  let app = null

  try {
    if (row.needsXvfb) {
      log(`row ${row.id} (${row.name}): starting Xvfb on :${row.xvfbDisplayNum}...`)
      xvfbProc = await startXvfb(row.xvfbDisplayNum)
    }

    const env = buildEnv(row)
    log(`row ${row.id} (${row.name}): launching Electron...`)

    const rowBody = (async () => {
      app = await _electron.launch({
        executablePath: ELECTRON_BIN,
        args: [MAIN_ENTRY, ...row.flags],
        cwd: GUI_DIR,
        env,
        timeout: ROW_TIMEOUT_MS,
      })
      result.launched = true

      const page = await app.firstWindow({ timeout: ROW_TIMEOUT_MS })
      result.firstWindowResolved = true

      // Note: electronApp.evaluate()'s callback receives the `electron` main
      // module itself as its first argument (Playwright convention — see
      // playwright docs' `({ app }) => app.isPackaged` example). There is no
      // `require` in scope inside the evaluated function, so destructure off
      // that argument rather than requiring 'electron' again.
      const visible = await app.evaluate(({ BrowserWindow }) => {
        const w = BrowserWindow.getAllWindows()[0]
        return w ? w.isVisible() : false
      })
      result.readyToShowFired = visible

      if (!visible) {
        log(`row ${row.id}: window not visible (ready-to-show likely didn't fire) — forcing show()`)
        await app.evaluate(({ BrowserWindow }) => {
          const w = BrowserWindow.getAllWindows()[0]
          if (w) w.show()
        })
        result.forcedShow = true
      }

      await page.waitForTimeout(800) // let renderer settle/paint

      ensureDebugDir()
      const shotPath = join(DEBUG_DIR, `preflight-row${row.id}-${row.slug}.png`)

      let buf = null
      try {
        buf = await page.screenshot({ path: shotPath })
      } catch (err) {
        log(`row ${row.id}: page.screenshot() threw: ${err.message}`)
      }

      let analysis = buf ? safeAnalyze(buf) : { nonBlank: false, error: 'no screenshot buffer' }

      if (!analysis.nonBlank) {
        log(`row ${row.id}: page.screenshot() non-blank check failed — falling back to webContents.capturePage()`)
        const b64 = await app.evaluate(async ({ BrowserWindow }) => {
          const w = BrowserWindow.getAllWindows()[0]
          if (!w) return null
          const img = await w.webContents.capturePage()
          return img.toPNG().toString('base64')
        })
        if (b64) {
          const buf2 = Buffer.from(b64, 'base64')
          writeFileSync(shotPath, buf2)
          analysis = safeAnalyze(buf2)
          result.usedCapturePage = true
        }
      }

      result.screenshotPath = shotPath.slice(ROOT.length + 1)
      result.screenshotNonBlank = !!analysis.nonBlank
      result.screenshotDetail = analysis

      await app.close()
      app = null
    })()

    await withTimeout(rowBody, ROW_TIMEOUT_MS + 5000, `row ${row.id} (${row.name})`)
  } catch (err) {
    result.error = stripAnsi(err.message)
    log(`row ${row.id} (${row.name}): FAILED — ${result.error}`)
    if (app) {
      try { await app.close() } catch { /* best effort */ }
    }
  } finally {
    if (xvfbProc) {
      try { xvfbProc.kill('SIGTERM') } catch { /* best effort */ }
    }
    result.ms = Date.now() - start
  }

  return result
}

function safeAnalyze(buf) {
  try {
    return analyzeScreenshot(buf)
  } catch (err) {
    return { nonBlank: false, error: err.message }
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  const argv = process.argv.slice(2)
  const noBuild = argv.includes('--no-build')
  const resetSelection = argv.includes('--reset-selection')
  const rowsArg = argv.find((a) => a.startsWith('--rows='))
  const rowFilter = rowsArg
    ? rowsArg.slice('--rows='.length).split(',').map((s) => parseInt(s, 10))
    : null

  if (argv.includes('--help') || argv.includes('-h')) {
    process.stderr.write([
      'Usage: node tools/electron_preflight.mjs [--no-build] [--rows=1,2,3,4] [--reset-selection]',
      '',
      'Probes 4 display backends for booting the real Electron app under',
      'Playwright _electron.launch(), records launched/firstWindow/screenshot',
      'results for all four (no early stop), and writes',
      'tools/electron_driver.config.json.',
      '',
      'The hand-recorded `selected` decision + `notes` in that config are',
      'PRESERVED across reruns (only the evidence is refreshed). Pass',
      '--reset-selection to deliberately discard the decision.',
    ].join('\n') + '\n')
    process.exit(0)
  }

  log(`Repo root: ${ROOT}`)
  // Read the prior config up front: the `selected` decision + `notes` it
  // holds must survive this rerun (see readExistingConfig).
  const existingConfig = readExistingConfig()
  const versions = readVersions()
  log(`Electron ${versions.electronVersion}, playwright ${versions.playwrightVersion}, node ${versions.nodeVersion}`)

  if (!existsSync(MAIN_ENTRY) && !noBuild) {
    build()
  } else if (!noBuild) {
    build()
  } else {
    log('--no-build: skipping npm run build, assuming out/ is current')
  }

  if (!existsSync(MAIN_ENTRY)) {
    throw new Error(`Main entry not found after build: ${MAIN_ENTRY}`)
  }
  if (!existsSync(ELECTRON_BIN)) {
    throw new Error(`Electron binary not found: ${ELECTRON_BIN}`)
  }

  // Informational block (printed before the matrix runs, per §4)
  const apparmor = readApparmorSysctl()
  const xvfbAvailable = xvfbRunExists()
  const initialEnv = {
    DISPLAY: process.env.DISPLAY || '(empty)',
    WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY || '(empty)',
    XDG_SESSION_TYPE: process.env.XDG_SESSION_TYPE || '(unset)',
  }
  const wayland = discoverWaylandSocket()
  const x11Displays = discoverX11Displays()
  const runtimeDir = process.env.XDG_RUNTIME_DIR || `/run/user/${process.getuid()}`
  const mutterXauth = discoverMutterXauthFile(runtimeDir)

  log('--- informational (pre-matrix) ---')
  log(`apparmor_restrict_unprivileged_userns: ${apparmor}`)
  log(`xvfb-run + Xvfb present: ${xvfbAvailable}`)
  log(`inherited env: DISPLAY=${initialEnv.DISPLAY} WAYLAND_DISPLAY=${initialEnv.WAYLAND_DISPLAY} XDG_SESSION_TYPE=${initialEnv.XDG_SESSION_TYPE}`)
  log(`discovered Wayland socket: ${wayland.socket ? `${wayland.socket} (in ${wayland.dir})` : 'none found'}`)
  log(`discovered X11 displays: ${x11Displays.length ? x11Displays.map((n) => `:${n}`).join(', ') : 'none found'}`)
  log(`discovered XWayland Xauthority file: ${mutterXauth || 'none found'}`)
  log('--- backend status before probes ---')
  const preStatus = curlBackendStatus()
  log(`GET ${BACKEND_URL} -> exit=${preStatus.exitCode} body=${preStatus.stdout.slice(0, 200)}`)

  const primaryX11Display = x11Displays.length ? x11Displays[0] : null
  const xvfbDisplayNum = pickFreeXvfbDisplay(x11Displays)

  const allRows = [
    {
      id: 1,
      slug: 'wayland-native',
      name: 'native Wayland',
      flags: ['--ozone-platform=wayland', '--disable-gpu', '--no-sandbox'],
      env: wayland.socket
        ? { WAYLAND_DISPLAY: wayland.socket, XDG_RUNTIME_DIR: wayland.dir }
        : {},
      skip: wayland.socket ? null : 'no wayland-* socket discovered under XDG_RUNTIME_DIR',
    },
    {
      id: 2,
      slug: 'xwayland',
      name: 'XWayland',
      flags: ['--ozone-platform=x11', '--disable-gpu', '--no-sandbox'],
      env: primaryX11Display !== null
        ? {
            DISPLAY: `:${primaryX11Display}`,
            ...(mutterXauth ? { XAUTHORITY: mutterXauth } : {}),
          }
        : {},
      skip: primaryX11Display !== null ? null : 'no /tmp/.X11-unix/X* socket discovered',
    },
    {
      id: 3,
      slug: 'xvfb',
      name: 'Xvfb',
      flags: ['--ozone-platform=x11', '--disable-gpu', '--no-sandbox'],
      env: { DISPLAY: `:${xvfbDisplayNum}` },
      needsXvfb: true,
      xvfbDisplayNum,
      skip: xvfbAvailable ? null : 'xvfb-run/Xvfb not found at /usr/bin',
    },
    {
      id: 4,
      slug: 'ozone-headless',
      name: 'ozone headless',
      flags: ['--ozone-platform=headless', '--disable-gpu', '--no-sandbox'],
      env: {},
      skip: null,
    },
  ]

  const rows = rowFilter ? allRows.filter((r) => rowFilter.includes(r.id)) : allRows

  log(`--- running ${rows.length} row(s) (~${ROW_TIMEOUT_MS / 1000}s cap each) ---`)
  const results = []
  for (const row of rows) {
    const result = await runRow(row)
    results.push(result)
    log(`row ${row.id} (${row.name}): launched=${result.launched} firstWindow=${result.firstWindowResolved} nonBlank=${result.screenshotNonBlank} ms=${result.ms} error=${result.error || 'none'}`)
    await sleep(300)
  }

  log('--- backend status after probes (must survive) ---')
  const postStatus = curlBackendStatus()
  log(`GET ${BACKEND_URL} -> exit=${postStatus.exitCode} body=${postStatus.stdout.slice(0, 200)}`)
  if (postStatus.exitCode !== 0 || !postStatus.stdout) {
    log('WARNING: backend on :5174 does not appear to be responding after the run.')
  }

  // The `selected` decision and `notes` are hand-recorded by the reviewing
  // human/orchestrator (§4/§7) — they are NOT this script's output, and
  // tools/electron_driver.mjs launches whatever `selected` says. So a rerun
  // carries them forward verbatim instead of nulling them; --reset-selection
  // is the explicit opt-out.
  let selected = existingConfig?.selected ?? null
  const notes = existingConfig?.notes ?? undefined

  if (resetSelection) {
    if (selected) {
      log(`--reset-selection: discarding the recorded decision (was row ${selected.id}, ${selected.name}).`)
    } else {
      log('--reset-selection: no recorded decision to discard.')
    }
    selected = null
  } else if (selected) {
    log(`Preserving recorded decision: row ${selected.id} (${selected.name}), decided by ${selected.decidedBy || 'unknown'}.`)
    checkSelectionAgainstMatrix(selected, results)
  } else {
    log('No recorded decision in the existing config — review the matrix below and record a `selected` block (see FABLE_VISUAL_VERIFICATION.md §4/§7).')
  }

  const config = {
    generatedAt: new Date().toISOString(),
    versions,
    informational: {
      apparmorRestrictUnprivilegedUserns: apparmor,
      xvfbAvailable,
      inheritedDisplayEnv: initialEnv,
      discoveredSockets: {
        wayland: wayland.socket ? { socket: wayland.socket, dir: wayland.dir } : null,
        x11Displays,
        xwaylandXauthFile: mutterXauth,
        xvfbDisplayNumUsed: xvfbDisplayNum,
      },
    },
    backendStatus: {
      before: preStatus,
      after: postStatus,
    },
    matrix: results,
    // This preflight records EVIDENCE only — it never picks a winner. The
    // default display backend is chosen by reviewing the matrix above (see
    // FABLE_VISUAL_VERIFICATION.md §4/§7); `selected` and `notes` below are
    // preserved from the previous config, not generated here.
    selected,
    ...(notes !== undefined ? { notes } : {}),
  }

  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2) + '\n')
  log(`Wrote ${CONFIG_PATH}`)

  console.log(JSON.stringify(config, null, 2))
}

main().catch((err) => {
  console.error(`Fatal: ${err.stack || err.message}`)
  process.exit(1)
})
