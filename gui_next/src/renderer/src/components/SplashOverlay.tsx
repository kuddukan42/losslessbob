// Startup splash — Variant A "Launch card"
// Plays the real boot sequence at measured speed (~2.4 s), polls Flask to
// detect the real "done" signal, then fades out.  If Flask is slower than
// the animation the bar goes indeterminate until the backend responds.

import React, { useEffect, useRef, useState } from 'react'

// Warm-white helper: matches dark-splash fg #f1ecdf at varying alpha.
const w = (a: number) => `rgba(241,236,223,${a})`

// ── Boot sequence (timings measured from real cold start) ─────────────────────
const BOOT_STEPS = [
  { label: 'Starting backend',  detail: 'Flask · Waitress',              atMs: 120  },
  { label: 'Opening database',  detail: 'checksum_lookup.db · LB-16630', atMs: 510  },
  { label: 'Loading interface', detail: 'electron-vite · renderer',      atMs: 792  },
  { label: 'Backend ready',     detail: 'localhost:5174',                 atMs: 1679 },
  { label: 'Building views',    detail: '14 panels',                      atMs: 1712 },
  { label: 'Restoring session', detail: 'geometry · shadows',             atMs: 2381 },
] as const

const BOOT_READY_MS = 2407

// ── Mock boot hook — replays phases at true speed ─────────────────────────────
function useMockBoot() {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    startRef.current = performance.now()
    const tick = (now: number) => {
      const e = now - (startRef.current ?? now)
      if (e >= BOOT_READY_MS) {
        setElapsed(BOOT_READY_MS)
        return
      }
      setElapsed(e)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  const animDone = elapsed >= BOOT_READY_MS

  let idx = 0
  for (let i = 0; i < BOOT_STEPS.length; i++) {
    if (elapsed >= BOOT_STEPS[i].atMs) idx = i
  }
  if (animDone) idx = BOOT_STEPS.length - 1

  const pct = animDone ? 100 : Math.min(96, Math.round((elapsed / BOOT_READY_MS) * 100))

  return { pct, label: BOOT_STEPS[idx].label, detail: BOOT_STEPS[idx].detail, animDone }
}

// ── SplashOverlay ─────────────────────────────────────────────────────────────

export interface SplashOverlayProps {
  onDone: () => void
}

export function SplashOverlay({ onDone }: SplashOverlayProps): React.JSX.Element {
  const boot = useMockBoot()
  const [backendReady, setBackendReady] = useState(false)
  const [dismissing, setDismissing] = useState(false)

  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  // Poll Flask until it responds (or 10-second fallback).
  useEffect(() => {
    let cancelled = false
    const poll = setInterval(async () => {
      try {
        const r = await fetch(`${window.api.flaskBase}/api/db/stats`, {
          signal: AbortSignal.timeout(400),
        })
        if (r.ok && !cancelled) {
          setBackendReady(true)
          clearInterval(poll)
        }
      } catch { /* not yet ready */ }
    }, 400)
    // Initial attempt immediately
    fetch(`${window.api.flaskBase}/api/db/stats`, { signal: AbortSignal.timeout(400) })
      .then(r => { if (r.ok && !cancelled) { setBackendReady(true); clearInterval(poll) } })
      .catch(() => {})
    const timeout = setTimeout(() => {
      if (!cancelled) setBackendReady(true)
    }, 10_000)
    return () => { cancelled = true; clearInterval(poll); clearTimeout(timeout) }
  }, [])

  // When animation done + backend ready: dwell 500 ms then start fade.
  useEffect(() => {
    if (!boot.animDone || !backendReady || dismissing) return
    const dwell = setTimeout(() => setDismissing(true), 500)
    return () => clearTimeout(dwell)
  }, [boot.animDone, backendReady, dismissing])

  // Call onDone after the 600 ms CSS fade completes.
  useEffect(() => {
    if (!dismissing) return
    const fade = setTimeout(() => onDoneRef.current(), 650)
    return () => clearTimeout(fade)
  }, [dismissing])

  const overrun = boot.animDone && !backendReady
  const showReady = boot.animDone && backendReady
  const isIndeterminate = overrun
  const displayPct = showReady ? 100 : boot.pct

  return (
    <div
      data-testid="splash-overlay"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        backgroundColor: '#131110',
        backgroundImage:
          'radial-gradient(120% 90% at 50% 42%, color-mix(in oklab, var(--lbb-accent-mid) 16%, transparent), transparent 55%)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        opacity: dismissing ? 0 : 1,
        transition: dismissing ? 'opacity 600ms ease' : 'none',
      }}
    >
      {/* Hairline inner frame */}
      <div style={{
        position: 'absolute', inset: 16,
        border: `1px solid ${w(0.05)}`, borderRadius: 4,
        pointerEvents: 'none',
      }} />

      {/* Brand frame — double square 440 × 232 */}
      <div style={{ position: 'relative', width: 440, height: 232, flexShrink: 0 }}>
        <div style={{
          position: 'absolute', inset: 0,
          border: `1.5px solid ${w(0.85)}`, borderRadius: 3,
        }} />
        <div style={{
          position: 'absolute', inset: 8,
          border: `1px solid ${w(0.28)}`, borderRadius: 2,
        }} />
        {/* Contents: monogram · wordmark · tagline */}
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 18, padding: '0 40px',
        }}>
          {/* Monogram 52 × 52 */}
          <div style={{
            width: 52, height: 52, borderRadius: 13, flexShrink: 0,
            background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 800, fontSize: 22, letterSpacing: -0.44,
            boxShadow: '0 1px 0 rgba(255,255,255,0.18) inset, 0 2px 8px rgba(0,0,0,0.35)',
          }}>
            LB
          </div>

          {/* Wordmark 38 px */}
          <span style={{
            fontSize: 38, fontWeight: 700, letterSpacing: -0.84,
            color: w(0.96), lineHeight: 1, whiteSpace: 'nowrap',
          }}>
            <span style={{ fontWeight: 500, color: w(0.62) }}>Lossless</span>
            <span>Bob</span>
          </span>

          {/* Tagline */}
          <span style={{
            fontFamily: 'var(--lbb-mono)', fontSize: 11, letterSpacing: 3.1,
            textTransform: 'uppercase', color: w(0.4),
          }}>
            Checksum Lookup
          </span>
        </div>
      </div>

      {/* Progress block */}
      <div style={{ width: 440, marginTop: 30 }}>
        {/* 3 px progress bar */}
        <div style={{ height: 3, background: w(0.1), borderRadius: 999, overflow: 'hidden' }}>
          {isIndeterminate ? (
            <div style={{
              height: '100%', width: '40%', borderRadius: 999,
              background: 'var(--lbb-accent-mid)',
              boxShadow: '0 0 10px var(--lbb-accent-mid)',
              animation: 'lbbIndet 1.15s cubic-bezier(.5,0,.5,1) infinite',
            }} />
          ) : (
            <div style={{
              height: '100%', width: `${displayPct}%`,
              background: 'var(--lbb-accent-mid)',
              boxShadow: '0 0 10px var(--lbb-accent-mid)',
              transition: 'width 120ms linear',
            }} />
          )}
        </div>

        {/* Status row */}
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginTop: 12,
          fontFamily: 'var(--lbb-mono)', fontSize: 11.5,
        }}>
          {showReady ? (
            <span style={{ color: 'var(--lbb-ok-fg)' }}>Ready · 704,624 checksums</span>
          ) : (
            <span>
              <span style={{ color: w(0.55) }}>{boot.label}</span>
              <span style={{ color: w(0.32) }}>{' · '}{boot.detail}</span>
            </span>
          )}
          <span style={{ color: w(0.4), fontVariantNumeric: 'tabular-nums' }}>
            {isIndeterminate ? '…' : showReady ? '100%' : `${displayPct}%`}
          </span>
        </div>
      </div>

      {/* Version footers */}
      <div style={{
        position: 'absolute', bottom: 26, left: 30,
        fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: w(0.3),
      }}>
        v{__APP_VERSION__} · stable
      </div>
      <div style={{
        position: 'absolute', bottom: 26, right: 30,
        fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: w(0.3),
      }}>
        build 2026.05.29
      </div>
    </div>
  )
}
