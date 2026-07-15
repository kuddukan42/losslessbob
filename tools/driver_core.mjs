/**
 * LosslessBob driver action-runner — shared between tools/browser_driver.mjs
 * (Playwright Chromium vs the Vite renderer) and tools/electron_driver.mjs
 * (Playwright `_electron.launch()` vs the real Electron app).
 *
 * Both drivers hand this module a live Playwright `Page` plus a parsed
 * session-JSON action array; the action semantics (screenshot/navigate/
 * click/fill/type/clear/wait/wait-for/hover/scroll-to/select/eval) must be
 * identical regardless of which tier produced the page, so the step loop
 * lives here once instead of being forked.
 *
 * See instructions/FABLE_VISUAL_VERIFICATION.md §3 (Bite 2): "If
 * action-runner code is shared between the two drivers, extract it to
 * tools/driver_core.mjs — do not fork two copies of the action runner."
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
 * @param {{ debugDir: string, log: (...args: string[]) => void }} opts
 *   `debugDir` — absolute dir RELATIVE screenshot paths resolve against
 *   (created if missing). This is the per-tier output dir: `.debug/` for
 *   Tier A, `.debug/electron/` for Tier B — so a tier-agnostic session file
 *   (tools/debug_screens.json) never has one tier silently overwriting the
 *   other's PNGs. An ABSOLUTE `file` wins over `debugDir` (explicit CLI
 *   path). `log` — driver-specific logger (keeps each driver's own
 *   `[browser-driver]` / `[electron-driver]` prefix).
 * @returns {Promise<Array<{action: string, ok: boolean, [key: string]: any}>>}
 *   One result per action, in order; failed actions get `ok: false` and an
 *   `error` message but do not stop the sequence.
 */
export async function runActions(page, actions, { debugDir, log }) {
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
