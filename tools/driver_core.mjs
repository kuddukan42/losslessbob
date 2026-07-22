/**
 * LosslessBob driver action-runner — shared between tools/browser_driver.mjs
 * (Playwright Chromium vs the Vite renderer) and tools/electron_driver.mjs
 * (Playwright `_electron.launch()` vs the real Electron app).
 *
 * Both drivers hand this module a live Playwright `Page` plus a parsed
 * session-JSON action array; the action semantics (screenshot/navigate/
 * click/fill/type/clear/wait/wait-for/hover/scroll-to/select/eval/resize/
 * size-matrix/watch/main-eval) must be identical regardless of which tier
 * produced the page, so the step loop lives here once instead of being
 * forked.
 *
 * See instructions/complete/FABLE_VISUAL_VERIFICATION.md §3 (Bite 2): "If
 * action-runner code is shared between the two drivers, extract it to
 * tools/driver_core.mjs — do not fork two copies of the action runner."
 *
 * Bite 3 (§6/§8) adds `resize`, `size-matrix`, `watch`, and `main-eval`.
 * These need driver-specific capabilities (real window resize, main-process
 * eval) that a Playwright `Page` alone cannot provide, so each driver passes
 * an optional `caps` object into `runActions()`:
 *   { resize?: async (w, h) => void, mainEval?: async (jsString) => any }
 * A driver that can't support a capability simply omits it — the action
 * then fails that one step (ok:false, clear error) without stopping the
 * sequence. `scale-matrix` is NOT here: it needs a fresh Electron launch per
 * scale (`--force-device-scale-factor` is a launch flag), so it lives as a
 * CLI-level command in tools/electron_driver.mjs only.
 */

import { existsSync, mkdirSync } from 'fs'
import { join, isAbsolute, dirname } from 'path'

/**
 * Ensure a directory exists (recursive mkdir if missing).
 * @param {string} dir Absolute path to ensure.
 */
export function ensureDir(dir) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

/**
 * Run a session-JSON action sequence against a live Playwright page.
 *
 * @param {import('playwright').Page} page Live page (Chromium tab or
 *   Electron BrowserWindow's page) to drive.
 * @param {Array<object>} actions Parsed session actions (same shape as
 *   tools/debug_screens.json entries).
 * @param {{ debugDir: string, log: (...args: string[]) => void,
 *   caps?: { resize?: (w: number, h: number) => Promise<void>,
 *   mainEval?: (js: string) => Promise<any> } }} opts
 *   `debugDir` — absolute dir RELATIVE screenshot paths resolve against
 *   (created if missing). This is the per-tier output dir: `.debug/` for
 *   Tier A, `.debug/electron/` for Tier B — so a tier-agnostic session file
 *   (tools/debug_screens.json) never has one tier silently overwriting the
 *   other's PNGs. An ABSOLUTE `file` wins over `debugDir` (explicit CLI
 *   path). `log` — driver-specific logger (keeps each driver's own
 *   `[browser-driver]` / `[electron-driver]` prefix). `caps` — optional
 *   per-driver capability object for actions a bare Playwright `Page` can't
 *   do itself (real window resize, main-process eval); a driver that omits
 *   a capability makes any action requiring it fail cleanly (see below).
 * @returns {Promise<Array<{action: string, ok: boolean, [key: string]: any}>>}
 *   One result per action, in order; failed actions get `ok: false` and an
 *   `error` message but do not stop the sequence.
 */
export async function runActions(page, actions, { debugDir, log, caps = {} }) {
  ensureDir(debugDir)

  const results = []

  for (const step of actions) {
    log(`action: ${step.action}`)
    let result = { action: step.action, ok: true }

    try {
      switch (step.action) {

        case 'screenshot': {
          const file    = step.file ?? 'shot.png'
          // Absolute paths are taken verbatim (an explicit CLI/session path
          // beats the tier's output dir); relative ones resolve against it.
          const outPath = isAbsolute(file) ? file : join(debugDir, file)
          ensureDir(dirname(outPath))
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
          // `state` passthrough ('visible' | 'attached' | 'detached' | 'hidden')
          // lets sessions wait for loading placeholders to DISAPPEAR
          // (state: 'detached'), not just for elements to appear.
          await page.waitForSelector(step.selector, {
            timeout: step.timeout ?? 12000,
            state: step.state ?? 'visible',
          })
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

        case 'resize': {
          if (!caps.resize) {
            throw new Error(`action 'resize' requires a driver that supports it`)
          }
          const { w, h, file } = step
          await caps.resize(w, h)
          await page.waitForTimeout(300) // let layout settle
          result.w = w
          result.h = h
          if (file) {
            const outPath = isAbsolute(file) ? file : join(debugDir, file)
            ensureDir(dirname(outPath))
            await page.screenshot({ path: outPath })
            log(`resize ${w}x${h} → screenshot ${outPath}`)
            result.path = outPath
          } else {
            log(`resize → ${w}x${h}`)
          }
          break
        }

        case 'size-matrix': {
          if (!caps.resize) {
            throw new Error(`action 'size-matrix' requires a driver that supports it`)
          }
          // Never go below 1280x768 — the app enforces that as its minimum
          // window size by design (see FABLE_VISUAL_VERIFICATION.md §6).
          const prefix = step.prefix ?? 'size'
          const sizes  = [[1280, 768], [1440, 900], [1920, 1080], [2560, 1440]]
          const shots  = []
          for (const [w, h] of sizes) {
            await caps.resize(w, h)
            await page.waitForTimeout(300) // let layout settle
            const file    = `${prefix}-${w}x${h}.png`
            const outPath = join(debugDir, file)
            ensureDir(dirname(outPath))
            await page.screenshot({ path: outPath })
            log(`size-matrix ${w}x${h} → ${outPath}`)
            shots.push({ w, h, path: outPath })
          }
          result.sizes = shots
          break
        }

        case 'watch': {
          const intervalMs = step.interval_ms ?? 500
          const maxMs      = step.max_ms ?? 10000
          const prefix     = step.prefix ?? 'watch'
          const until      = step.until ?? null
          const deadline   = Date.now() + maxMs
          const frames     = []
          let frameIdx     = 0
          let stoppedBy    = 'timeout'

          // Always capture at least one frame before checking any stop
          // condition, so a max_ms of 0 or an already-present selector
          // still yields one screenshot.
          // eslint-disable-next-line no-constant-condition
          while (true) {
            const file    = `${prefix}-${String(frameIdx).padStart(3, '0')}.png`
            const outPath = join(debugDir, file)
            ensureDir(dirname(outPath))
            await page.screenshot({ path: outPath })
            frames.push(outPath)
            log(`watch frame ${frameIdx} → ${outPath}`)
            frameIdx += 1

            if (until && (await page.$(until))) {
              stoppedBy = 'selector'
              break
            }
            if (Date.now() >= deadline) {
              stoppedBy = 'timeout'
              break
            }
            await page.waitForTimeout(intervalMs)
          }

          result.frameCount = frames.length
          result.frames     = frames
          result.stoppedBy  = stoppedBy
          log(`watch stopped (${stoppedBy}) after ${frames.length} frame(s)`)
          break
        }

        case 'main-eval': {
          if (!caps.mainEval) {
            throw new Error(`action 'main-eval' requires a driver that supports it`)
          }
          const value = await caps.mainEval(step.js)
          log(`main-eval → ${JSON.stringify(value)}`)
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

  return results
}

/**
 * Parse a `session <json|path>` CLI argument into an action array — shared
 * so both drivers accept either an inline JSON string or a file path the
 * same way.
 * @param {string} arg Raw CLI argument (inline JSON or a filesystem path).
 * @param {(p: string) => boolean} existsFn `existsSync`-shaped check
 *   (injected so this stays dependency-free of `fs` path assumptions).
 * @param {(p: string, enc: string) => string} readFn `readFileSync`-shaped
 *   reader.
 * @returns {Array<object>}
 */
export function parseSessionArg(arg, existsFn, readFn) {
  const data = existsFn(arg)
    ? JSON.parse(readFn(arg, 'utf8'))
    : JSON.parse(arg)
  return Array.isArray(data) ? data : data.actions
}
