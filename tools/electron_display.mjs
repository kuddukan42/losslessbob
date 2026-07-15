/**
 * LosslessBob Electron display helpers — Xvfb lifecycle + X11/Wayland socket
 * discovery, shared between tools/electron_preflight.mjs (which probed all
 * four candidate backends, see FABLE_VISUAL_VERIFICATION.md §4) and
 * tools/electron_driver.mjs (which only ever launches the backend the
 * preflight matrix selected — Xvfb, see electron_driver.config.json
 * `.selected`).
 *
 * Extracted per FABLE_VISUAL_VERIFICATION.md §3 (Bite 2): "Reuse the Xvfb
 * lifecycle + socket-discovery helpers already written in
 * electron_preflight.mjs (extract/share rather than copy-paste)."
 */

import { spawn } from 'child_process'
import { existsSync, readdirSync, statSync } from 'fs'
import { join } from 'path'

/** @param {number} ms */
export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

/** Whether the `xvfb-run` wrapper + `Xvfb` binary are both installed. */
export function xvfbRunExists() {
  return existsSync('/usr/bin/xvfb-run') && existsSync('/usr/bin/Xvfb')
}

/** Find a live `wayland-N` socket under `$XDG_RUNTIME_DIR` (or `/run/user/<uid>`). */
export function discoverWaylandSocket() {
  const dir = process.env.XDG_RUNTIME_DIR || `/run/user/${process.getuid()}`
  try {
    const matches = readdirSync(dir)
      .filter((e) => /^wayland-\d+$/.test(e))
      .filter((e) => {
        try { return statSync(join(dir, e)).isSocket() } catch { return false }
      })
      .sort()
    return { dir, socket: matches[0] || null }
  } catch (err) {
    return { dir, socket: null, error: err.message }
  }
}

/**
 * XWayland (Mutter) requires an Xauthority cookie to accept connections on
 * :0/:1 — the file name has a random per-session suffix
 * (`.mutter-Xwaylandauth.XXXXXX`), so it must be discovered, not hardcoded.
 * @param {string} runtimeDir
 */
export function discoverMutterXauthFile(runtimeDir) {
  try {
    const match = readdirSync(runtimeDir).find((e) => /^\.mutter-Xwaylandauth\./.test(e))
    return match ? join(runtimeDir, match) : null
  } catch {
    return null
  }
}

/** Live X11 display numbers with a socket under `/tmp/.X11-unix`. */
export function discoverX11Displays() {
  const dir = '/tmp/.X11-unix'
  try {
    const nums = readdirSync(dir)
      .filter((e) => /^X\d+$/.test(e))
      .filter((e) => {
        try { return statSync(join(dir, e)).isSocket() } catch { return false }
      })
      .map((e) => parseInt(e.slice(1), 10))
      .sort((a, b) => a - b)
    return nums
  } catch {
    return []
  }
}

/**
 * First display number >= 90 with no existing socket and not in `existing`.
 * @param {number[]} existing Display numbers already known to be live.
 */
export function pickFreeXvfbDisplay(existing) {
  let n = 90
  while (existing.includes(n) || existsSync(`/tmp/.X11-unix/X${n}`)) n += 1
  return n
}

/**
 * Start Xvfb on `:displayNum` and wait for its socket to appear.
 * @param {number} displayNum
 * @param {string} screen Xvfb `-screen 0 <geometry>` value, e.g. `2560x1440x24`.
 * @returns {Promise<import('child_process').ChildProcess>}
 */
export async function startXvfb(displayNum, screen = '1280x800x24') {
  const proc = spawn(
    'Xvfb',
    [`:${displayNum}`, '-screen', '0', screen, '-nolisten', 'tcp'],
    { stdio: 'ignore' },
  )
  const sockPath = `/tmp/.X11-unix/X${displayNum}`
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (existsSync(sockPath)) return proc
    await sleep(100)
  }
  proc.kill('SIGTERM')
  throw new Error(`Xvfb did not create ${sockPath} within 5s`)
}
