// Coverage / "Complete against LB" award screen — route /about/coverage.
//
// Spec: instructions/design_handoff_lb_coverage_award/README.md. One component,
// three treatments of the same layout:
//   · incomplete (the state it spends most of its life in) — coverage ring, no
//     gold, warn-toned missing count, partial era bars, work strip, "Open in
//     TapeMatch" as the primary action, no export.
//   · first run / never-complete — the incomplete layout with the award
//     language suppressed (percentage headline instead of "n to chase").
//   · complete — the gold certificate treatment (§2).
//
// Deliberately NOT a sidebar destination (§1): reached from the About modal's
// "Collection progress" row, deep-linkable, restorable on reload.
//
// `?demo=complete` renders the award state from the same live data with
// entries_missing forced to 0, so the milestone can be demoed and screenshotted
// without waiting for real 100% coverage.

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Button } from '../components/primitives'

const BASE = window.api.flaskBase

// ── Types (GET /api/lb/coverage) ─────────────────────────────────────────────

interface DecadeRow { decade: number; label: string; total: number; held: number }

interface CoverageState {
  entries_total: number
  entries_held: number
  entries_missing: number
  recordings: number
  families: number
  coverage_pct: number
  complete: boolean
  by_decade: DecadeRow[]
  ledger_sha256: string
  signed_by: string
}

interface SnapshotInfo {
  // null on a fresh/partial DB — backend/lb_coverage.py deliberately omits
  // these rather than 500ing when the meta rows or my_collection are absent.
  label: string | null
  version: string | null
  published_at: string | null
  last_import: string | null
  entry_count: number
}

interface CurationStats {
  first_entry_filed_at: string | null
  days_active: number
}

interface CoveragePayload {
  snapshot: SnapshotInfo
  coverage: CoverageState
  stats: CurationStats
}

interface GithubCheck {
  available: boolean
  local_version: string
  remote_version: string
}

// ── Local helpers ────────────────────────────────────────────────────────────

const CELEBRATED_KEY = 'lbb-celebrated-snapshot-ids'

/** Snapshot ids whose 100% milestone has already played its entrance (§5). */
function loadCelebrated(): string[] {
  try {
    const raw = localStorage.getItem(CELEBRATED_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return []
  }
}

function saveCelebrated(ids: string[]): void {
  try {
    localStorage.setItem(CELEBRATED_KEY, JSON.stringify(ids))
  } catch {
    /* storage unavailable — the entrance just replays, which is harmless */
  }
}

function fmt(n: number): string {
  return Math.round(n).toLocaleString('en-US')
}

/** "2026.07" → "July". Falls back to the raw label if it isn't YYYY.MM. */
function monthName(label: string): string {
  const m = /^(\d{4})\.(\d{2})$/.exec(label)
  if (!m) return label
  const idx = Number(m[2]) - 1
  if (idx < 0 || idx > 11) return label
  // timeZone:'UTC' is load-bearing — without it a UTC-midnight date formats in
  // the local zone and any negative offset renders the *previous* month.
  return new Date(Date.UTC(2000, idx, 1))
    .toLocaleString('en-US', { month: 'long', timeZone: 'UTC' })
}

/** "2026-08-02 22:22:28" → "2026-08-02 · 22:22". */
function fmtStamp(raw: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(raw)
  return m ? `${m[1]} · ${m[2]}` : raw
}

function dateOnly(raw: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(raw)
  return m ? m[1] : raw
}

function shortHash(sha: string): string {
  return sha.length > 8 ? `${sha.slice(0, 4)}…${sha.slice(-4)}` : sha
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Live `data-mode` off <html> — the ambient gold glow is dark-mode only (§2). */
function useDarkMode(): boolean {
  const read = (): boolean => document.documentElement.getAttribute('data-mode') === 'dark'
  const [dark, setDark] = useState(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-mode'] })
    return () => obs.disconnect()
  }, [])
  return dark
}

type Tier = 'lg' | 'md' | 'sm' | 'xs'

/** Window-width breakpoints from §9. §9's "1100–1440px" / "<1100px" thresholds
 *  are app-window widths, not the sidebar-narrowed content column — matching
 *  the `useViewportWidth` convention in ScreenTapeMatchCuration.tsx (no shared
 *  useMediaQuery hook exists in gui_next, so each screen keeps its own local
 *  version). An element-width ResizeObserver on the content column used to
 *  subtract the 224px sidebar (plus the screen's own padding) before comparing
 *  against the spec's numbers, which pushed the md/lg tiers ~300px further out
 *  than intended (BUG: 1100px window measured as sm, not md).
 *  Keeps the same `[Tier, ref-setter]` return shape as before — the ref is no
 *  longer load-bearing for the measurement, but the skeleton/loaded root divs
 *  still attach it, so it stays a harmless no-op setter rather than touching
 *  every call site. */
function useTier(): [Tier, (el: HTMLDivElement | null) => void] {
  const [tier, setTier] = useState<Tier>(() => tierForWidth(window.innerWidth))
  useEffect(() => {
    const apply = (): void => setTier(tierForWidth(window.innerWidth))
    window.addEventListener('resize', apply)
    return () => window.removeEventListener('resize', apply)
  }, [])
  const noopRef = useCallback((_el: HTMLDivElement | null): void => {}, [])
  return [tier, noopRef]
}

function tierForWidth(w: number): Tier {
  return w >= 1440 ? 'lg' : w >= 1100 ? 'md' : w >= 700 ? 'sm' : 'xs'
}

/** Shared 0→1 count-up ramp: 1400ms ease-out cubic (§5). One rAF loop drives
 *  every numeral on the screen so they stay in lockstep. Reduced motion pins it
 *  at 1 and never animates. */
function useCountProgress(replayKey: number): number {
  const reduced = prefersReducedMotion()
  const [p, setP] = useState(reduced ? 1 : 0)
  useEffect(() => {
    if (reduced) { setP(1); return }
    let raf = 0
    const t0 = performance.now()
    const step = (t: number): void => {
      const raw = Math.min(1, (t - t0) / 1400)
      setP(1 - Math.pow(1 - raw, 3))
      if (raw < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [replayKey, reduced])
  return p
}

// ── Certificate rendering (client-side, §5) ──────────────────────────────────

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#000000'
}

/** #rrggbb → rgba() at alpha. Returns the input untouched if it isn't hex. */
function hexA(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const v = parseInt(m[1], 16)
  return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${alpha})`
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  for (const word of words) {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

interface CertLabels {
  eyebrow: string
  headline: string
  subhead: string
  stats: Array<{ value: string; label: string }>
  eras: DecadeRow[]
  sigLeft: [string, string]
  sigRight: [string, string]
}

/** Draws the certificate at 2× onto an offscreen canvas and returns a PNG data
 *  URL. Hand-drawn rather than DOM-rasterised: the app has no html2canvas and
 *  the spec explicitly sanctions a client-side render. Colors are read live
 *  from the --lbb-* custom properties, so the export matches the active theme. */
function renderCertificatePng(l: CertLabels): string {
  const W = 1180
  const H = l.sigLeft[0] ? 660 : 600
  const S = 2
  const canvas = document.createElement('canvas')
  canvas.width = W * S
  canvas.height = H * S
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''
  ctx.scale(S, S)

  const bg = token('--lbb-bg')
  const surface = token('--lbb-surface')
  const surface2 = token('--lbb-surface2')
  const border = token('--lbb-border')
  const border2 = token('--lbb-border2')
  const fg = token('--lbb-fg')
  const fg2 = token('--lbb-fg2')
  const fg3 = token('--lbb-fg3')
  const gold = token('--lbb-award-mid')
  const goldLo = token('--lbb-award-lo')
  const ok = token('--lbb-ok-fg')

  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, H)

  const grad = ctx.createLinearGradient(0, 0, 0, H)
  grad.addColorStop(0, surface)
  grad.addColorStop(1, bg)
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = hexA(gold, 0.32)
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1)
  ctx.strokeStyle = hexA(gold, 0.14)
  ctx.strokeRect(7.5, 7.5, W - 15, H - 15)

  const cx = W / 2
  let y = 60

  // Seal
  ctx.beginPath()
  ctx.arc(cx, y + 44, 44, 0, Math.PI * 2)
  ctx.fillStyle = surface
  ctx.fill()
  ctx.strokeStyle = hexA(gold, 0.45)
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(cx, y + 44, 37, 0, Math.PI * 2)
  ctx.setLineDash([4, 4])
  ctx.strokeStyle = hexA(gold, 0.35)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.strokeStyle = gold
  ctx.lineWidth = 3
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()
  ctx.moveTo(cx - 12, y + 44)
  ctx.lineTo(cx - 4, y + 52)
  ctx.lineTo(cx + 13, y + 34)
  ctx.stroke()
  ctx.lineWidth = 1
  y += 88 + 22

  ctx.textAlign = 'center'
  ctx.fillStyle = fg3
  ctx.font = '700 11px Inter, sans-serif'
  ctx.fillText(l.eyebrow.toUpperCase(), cx, y)
  y += 40

  ctx.fillStyle = fg
  ctx.font = '800 42px Inter, sans-serif'
  ctx.fillText(l.headline, cx, y)
  y += 26

  ctx.fillStyle = fg2
  ctx.font = '400 14.5px Inter, sans-serif'
  for (const line of wrapText(ctx, l.subhead, 660)) {
    y += 22
    ctx.fillText(line, cx, y)
  }
  y += 34

  const pad = 56
  const inner = W - pad * 2
  const ruleGrad = ctx.createLinearGradient(pad, 0, W - pad, 0)
  ruleGrad.addColorStop(0, hexA(border2, 0))
  ruleGrad.addColorStop(0.5, border2)
  ruleGrad.addColorStop(1, hexA(border2, 0))
  ctx.fillStyle = ruleGrad
  ctx.fillRect(pad, y, inner, 1)
  y += 22

  // Stat row
  const cellW = (inner - 6) / 4
  l.stats.forEach((s, i) => {
    const x = pad + i * (cellW + 2)
    ctx.fillStyle = surface2
    ctx.fillRect(x, y, cellW, 64)
    ctx.strokeStyle = border
    ctx.strokeRect(x + 0.5, y + 0.5, cellW - 1, 63)
    ctx.fillStyle = i === 3 ? ok : fg
    ctx.font = '600 22px "JetBrains Mono", monospace'
    ctx.fillText(s.value, x + cellW / 2, y + 32)
    ctx.fillStyle = fg3
    ctx.font = '600 10px Inter, sans-serif'
    ctx.fillText(s.label.toUpperCase(), x + cellW / 2, y + 51)
  })
  y += 64 + 22

  // Era bars
  const n = Math.max(1, l.eras.length)
  const barW = (inner - 6 * (n - 1)) / n
  l.eras.forEach((d, i) => {
    const x = pad + i * (barW + 6)
    const ratio = d.total > 0 ? d.held / d.total : 0
    ctx.fillStyle = surface2
    ctx.fillRect(x, y, barW, 5)
    const bg2 = ctx.createLinearGradient(x, 0, x + barW, 0)
    bg2.addColorStop(0, goldLo)
    bg2.addColorStop(1, gold)
    ctx.fillStyle = bg2
    ctx.fillRect(x, y, barW * ratio, 5)
    ctx.fillStyle = fg3
    ctx.font = '600 9.5px "JetBrains Mono", monospace'
    ctx.fillText(d.label, x + barW / 2, y + 20)
  })
  y += 5 + 30

  if (l.sigLeft[0]) {
    y += 14
    ctx.textAlign = 'left'
    ctx.fillStyle = fg2
    ctx.font = '500 11px "JetBrains Mono", monospace'
    ctx.fillText(l.sigLeft[0], pad, y)
    ctx.fillStyle = fg3
    ctx.font = '400 11px "JetBrains Mono", monospace'
    ctx.fillText(l.sigLeft[1], pad, y + 18)
    ctx.textAlign = 'right'
    ctx.fillStyle = fg2
    ctx.font = '500 11px "JetBrains Mono", monospace'
    ctx.fillText(l.sigRight[0], W - pad, y)
    ctx.fillStyle = fg3
    ctx.font = '400 11px "JetBrains Mono", monospace'
    ctx.fillText(l.sigRight[1], W - pad, y + 18)
  }

  return canvas.toDataURL('image/png')
}

function dataUrlDownload(dataUrl: string, filename: string): void {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  a.click()
}

// ── Small presentational pieces ──────────────────────────────────────────────

function Seal({ celebrate }: { celebrate: boolean }): React.JSX.Element {
  const dark = useDarkMode()
  return (
    <div
      className={celebrate ? 'lbb-cov-celebrate-seal' : undefined}
      style={{
        width: 88, height: 88, borderRadius: '50%', position: 'relative', flex: '0 0 auto',
        display: 'grid', placeItems: 'center',
        border: '1px solid color-mix(in oklab, var(--lbb-award-mid) 45%, transparent)',
        background: dark
          ? 'radial-gradient(70% 70% at 50% 30%, var(--lbb-award-soft), var(--lbb-surface))'
          : 'radial-gradient(70% 70% at 50% 30%, var(--lbb-award-soft), var(--lbb-surface))',
      }}
    >
      <span style={{
        position: 'absolute', inset: 7, borderRadius: '50%',
        border: '1px dashed color-mix(in oklab, var(--lbb-award-mid) 35%, transparent)',
      }} />
      <Icon name="check" size={30} stroke={2.2} style={{ color: 'var(--lbb-award-mid)' }} />
    </div>
  )
}

function CoverageRing({ pct, size = 88 }: { pct: number; size?: number }): React.JSX.Element {
  const r = size / 2 - 4
  const c = 2 * Math.PI * r
  const shown = Math.max(0, Math.min(1, pct))
  return (
    <div style={{ width: size, height: size, position: 'relative', flex: '0 0 auto' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block' }}>
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="var(--lbb-surface3)" strokeWidth={3}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="var(--lbb-accent-mid)" strokeWidth={3} strokeLinecap="round"
          strokeDasharray={`${c * shown} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span style={{
        position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
        fontFamily: 'var(--lbb-mono)', fontSize: size >= 88 ? 20 : 15, fontWeight: 600,
        fontVariantNumeric: 'tabular-nums', color: 'var(--lbb-fg)',
      }}>
        {(shown * 100).toFixed(1)}%
      </span>
    </div>
  )
}

function StatCell({ value, label, tone, progress }: {
  value: number
  label: string
  tone?: string
  progress: number
}): React.JSX.Element {
  return (
    <div
      aria-label={`${label}: ${fmt(value)}`}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5,
        padding: '13px 8px', minWidth: 0,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      }}
    >
      <b aria-hidden="true" style={{
        fontFamily: 'var(--lbb-mono)', fontSize: 22, fontWeight: 600,
        fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em',
        color: tone ?? 'var(--lbb-fg)', lineHeight: 1.1,
      }}>
        {fmt(value * progress)}
      </b>
      <span aria-hidden="true" style={{
        fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase',
        color: 'var(--lbb-fg3)', textAlign: 'center', lineHeight: 1.2,
      }}>
        {label}
      </span>
    </div>
  )
}

const SR_ONLY: React.CSSProperties = {
  position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
  overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
}

// ── Screen ───────────────────────────────────────────────────────────────────

type SyncState =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'uptodate'; version: string }
  | { kind: 'newer'; version: string }
  | { kind: 'error' }

export function ScreenCoverage(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const demoComplete = params.get('demo') === 'complete'

  const [tier, rootRef] = useTier()
  const dark = useDarkMode()

  const [countKey, setCountKey] = useState(0)
  const progress = useCountProgress(countKey)
  const [sync, setSync] = useState<SyncState>({ kind: 'idle' })
  const [lastSyncOk, setLastSyncOk] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [celebrate, setCelebrate] = useState(false)

  const { data, isLoading, isError } = useQuery<CoveragePayload>({
    queryKey: ['lb-coverage'],
    queryFn: async () => {
      const r = await fetch(`${BASE}/api/lb/coverage`)
      if (!r.ok) throw new Error(String(r.status))
      return r.json() as Promise<CoveragePayload>
    },
    staleTime: 60_000,
  })

  // `?demo=complete` — the award state, driven by the same live payload with
  // nothing missing. Never mutates anything server-side.
  const view = useMemo<CoveragePayload | undefined>(() => {
    if (!data) return undefined
    if (!demoComplete) return data
    return {
      ...data,
      coverage: {
        ...data.coverage,
        entries_held: data.coverage.entries_total,
        entries_missing: 0,
        coverage_pct: 1,
        complete: true,
        by_decade: data.coverage.by_decade.map(d => ({ ...d, held: d.total })),
      },
    }
  }, [data, demoComplete])

  const complete = view?.coverage.complete ?? false
  const snapshotId = view ? `${view.snapshot.version}${demoComplete ? '+demo' : ''}` : null

  // Award language is suppressed until 100% has been reached at least once
  // (§3, third state). "Never celebrated anything" is our stand-in for that.
  const everComplete = useMemo(() => loadCelebrated().length > 0, [])

  // First-time celebration, once per snapshot (§5).
  useEffect(() => {
    if (!complete || !snapshotId) return
    if (prefersReducedMotion()) return
    const seen = loadCelebrated()
    if (seen.includes(snapshotId)) return
    saveCelebrated([...seen, snapshotId])
    setCelebrate(true)
    const id = setTimeout(() => setCelebrate(false), 1400)
    return () => clearTimeout(id)
  }, [complete, snapshotId])

  const replay = useCallback(() => {
    if (prefersReducedMotion()) return
    setCountKey(k => k + 1)
  }, [])

  const runSync = useCallback(async () => {
    setSync({ kind: 'busy' })
    try {
      const r = await fetch(`${BASE}/api/master/github_check`)
      if (!r.ok) throw new Error(String(r.status))
      const j = (await r.json()) as GithubCheck
      setLastSyncOk(new Date().toISOString().slice(0, 16).replace('T', ' · '))
      setSync(j.available
        ? { kind: 'newer', version: j.remote_version }
        : { kind: 'uptodate', version: j.local_version })
    } catch {
      setSync({ kind: 'error' })
    }
  }, [])

  // ── Loading / error ────────────────────────────────────────────────────────
  if (isLoading || (!view && !isError)) return <CoverageSkeleton tier={tier} rootRef={rootRef} />
  if (isError || !view) {
    return (
      <div ref={rootRef} style={{ padding: 56, display: 'grid', placeItems: 'center', minHeight: '100%' }}>
        <div style={{
          maxWidth: 420, textAlign: 'center', padding: '22px 26px', borderRadius: 8,
          border: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('screenCoverage.errorTitle')}
          </div>
          <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--lbb-fg2)', lineHeight: 1.6 }}>
            {t('screenCoverage.errorBody')}
          </p>
        </div>
      </div>
    )
  }

  const cov = view.coverage
  const snap = view.snapshot
  const stats = view.stats
  const missing = cov.entries_missing
  // Once a manual check has run, report *that* time — the snapshot's import
  // stamp is only the fallback, and on a fresh DB neither may exist yet.
  const lastCheckedWhen = lastSyncOk ?? (snap.last_import ? fmtStamp(snap.last_import) : null)

  // ── Responsive dials (§9) ──────────────────────────────────────────────────
  const narrow = tier === 'sm' || tier === 'xs'
  const headlineSize = tier === 'lg' ? 42 : tier === 'md' ? 36 : tier === 'sm' ? 32 : 28
  const cardPad = narrow ? (tier === 'xs' ? '24px 18px 20px' : '30px 26px 24px') : '38px 56px 30px'
  const statCols = narrow ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)'
  const eraCols = narrow ? 'repeat(4, 1fr)' : `repeat(${Math.max(1, cov.by_decade.length)}, 1fr)`
  const cardWrap: React.CSSProperties = tier === 'lg'
    ? { maxWidth: 1180, margin: '0 auto', width: '100%' }
    : tier === 'md'
      ? { margin: '0 32px' }
      : { margin: 0 }

  // ── Copy ───────────────────────────────────────────────────────────────────
  // `snap.label` is null on a fresh/partial DB (no master meta yet) — fall
  // back to label-less copy rather than printing the literal "null".
  const eyebrow = complete
    ? (snap.label
        ? t('screenCoverage.eyebrowComplete', { label: snap.label })
        : t('screenCoverage.eyebrowCompleteNoLabel'))
    : (snap.label
        ? t('screenCoverage.eyebrowIncomplete', { label: snap.label, count: missing })
        : t('screenCoverage.eyebrowIncompleteNoLabel', { count: missing }))

  const headline = complete
    ? t('screenCoverage.headlineComplete')
    : everComplete
      ? t('screenCoverage.headlineChase', { count: missing })
      : t('screenCoverage.headlineFirstRun', { pct: (cov.coverage_pct * 100).toFixed(1) })

  const subhead = complete
    ? (snap.label
        ? t('screenCoverage.subheadComplete', { month: monthName(snap.label) })
        : t('screenCoverage.subheadCompleteNoMonth'))
    : t('screenCoverage.subheadIncomplete', { count: missing, total: fmt(cov.entries_total) })

  const goldBorder = 'color-mix(in oklab, var(--lbb-award-mid) 32%, transparent)'

  return (
    <div
      ref={rootRef}
      style={{
        position: 'relative', minHeight: '100%', height: '100%', overflowY: 'auto',
        display: 'flex', flexDirection: 'column',
        padding: narrow ? '24px 16px 20px' : '56px 0 20px',
        background: 'var(--lbb-bg)',
      }}
    >
      {/* Ambient gold glow — dark mode + complete only (§2). */}
      {complete && dark && (
        <div
          aria-hidden="true"
          className={celebrate ? 'lbb-cov-celebrate-glow' : undefined}
          style={{
            position: 'absolute', inset: '-30% 20% 50%', pointerEvents: 'none',
            background: 'radial-gradient(50% 50% at 50% 50%, color-mix(in oklab, var(--lbb-award-mid) 13%, transparent), transparent 70%)',
          }}
        />
      )}

      {demoComplete && (
        <div style={{
          ...cardWrap, marginBottom: 12,
          padding: '7px 12px', borderRadius: 6, fontSize: 11.5, textAlign: 'center',
          background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
          color: 'var(--lbb-info-fg)',
        }}>
          {t('screenCoverage.demoBanner')}
        </div>
      )}

      {/* Certificate / progress card. Click anywhere on it replays the
          count-up (§5) — it is not focusable and carries no role, so it stays
          a nicety rather than a control (§8). */}
      <div
        onClick={replay}
        className={celebrate ? 'lbb-cov-celebrate' : undefined}
        style={{
          ...cardWrap,
          // Sized to content, not stretched: at the 1000px content height a
          // flexed card left ~130px of dead space above the signature row,
          // which the 800px design reference does not have.
          position: 'relative', flex: '0 0 auto',
          display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
          padding: cardPad, borderRadius: 6,
          border: `1px solid ${complete ? goldBorder : 'var(--lbb-border)'}`,
          background: 'linear-gradient(180deg, var(--lbb-surface), var(--lbb-bg))',
          boxShadow: complete && !dark ? 'var(--lbb-shadowLg)' : 'none',
        }}
      >
        {complete && (
          <span aria-hidden="true" style={{
            position: 'absolute', inset: 7, borderRadius: 3, pointerEvents: 'none',
            border: '1px solid color-mix(in oklab, var(--lbb-award-mid) 14%, transparent)',
          }} />
        )}

        {complete
          ? <Seal celebrate={celebrate} />
          : (
            <>
              <CoverageRing pct={cov.coverage_pct} size={tier === 'xs' ? 64 : 88} />
              <span style={SR_ONLY}>
                {t('screenCoverage.ringAria', { pct: (cov.coverage_pct * 100).toFixed(1) })}
              </span>
            </>
          )}

        <div style={{
          marginTop: 16, fontSize: 10.5, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--lbb-fg3)',
        }}>
          {eyebrow}
        </div>

        <h1 style={{
          margin: '20px 0 0', fontSize: headlineSize, fontWeight: 800, lineHeight: 1.05,
          letterSpacing: '-0.025em', color: 'var(--lbb-fg)',
        }}>
          {headline}
        </h1>

        <p style={{
          margin: '11px 0 0', maxWidth: 660, fontSize: 14.5, lineHeight: 1.55,
          color: 'var(--lbb-fg2)', textWrap: 'pretty',
        } as React.CSSProperties}>
          {subhead}
        </p>

        <div aria-hidden="true" style={{
          width: '100%', height: 1, margin: '26px 0 20px',
          background: 'linear-gradient(90deg, transparent, var(--lbb-border2), transparent)',
        }} />

        {/* Stat row — live region so coverage changes are announced (§8). */}
        <div
          aria-live="polite"
          style={{ display: 'grid', gridTemplateColumns: statCols, gap: 2, width: '100%' }}
        >
          <StatCell value={cov.entries_held} label={t('screenCoverage.statHeld')} progress={progress} />
          <StatCell value={cov.recordings}   label={t('screenCoverage.statRecordings')} progress={progress} />
          <StatCell value={cov.families}     label={t('screenCoverage.statFamilies')} progress={progress} />
          <StatCell
            value={missing}
            label={t('screenCoverage.statMissing')}
            progress={progress}
            tone={missing === 0 ? 'var(--lbb-ok-fg)' : 'var(--lbb-warn-fg)'}
          />
        </div>

        {/* Era bars — one column per decade the API returns, each filled to
            that decade's held/total over a --lbb-surface2 track (§2 row 7). */}
        <div style={{
          width: '100%', marginTop: 18,
          display: 'grid', gridTemplateColumns: eraCols, gap: 6,
        }}>
          {cov.by_decade.map(d => {
            const ratio = d.total > 0 ? d.held / d.total : 0
            return (
              <div key={d.decade} style={{
                display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', minWidth: 0,
              }}>
                <i aria-hidden="true" style={{
                  display: 'block', width: '100%', height: 5, borderRadius: 3,
                  background: 'var(--lbb-surface2)', overflow: 'hidden',
                }}>
                  <span style={{
                    display: 'block', height: '100%', width: `${ratio * 100}%`, borderRadius: 3,
                    background: complete
                      ? 'linear-gradient(90deg, var(--lbb-award-lo), var(--lbb-award-mid))'
                      : 'linear-gradient(90deg, var(--lbb-accent-lo), var(--lbb-accent-mid))',
                  }} />
                </i>
                <span aria-hidden="true" style={{
                  fontFamily: 'var(--lbb-mono)', fontSize: 9.5, fontWeight: 600,
                  color: 'var(--lbb-fg3)',
                }}>
                  {d.label}
                </span>
                <span style={SR_ONLY}>
                  {t('screenCoverage.eraAria', {
                    decade: d.decade, pct: Math.round(ratio * 100),
                    held: fmt(d.held), total: fmt(d.total),
                  })}
                </span>
              </div>
            )
          })}
        </div>

        {/* Live strip / work strip / sync result / failure strip (§2 row 8, §5). */}
        <div style={{
          marginTop: 22, width: '100%',
          display: 'flex', flexDirection: narrow ? 'column' : 'row',
          alignItems: narrow ? 'flex-start' : 'center', gap: narrow ? 8 : 14,
          padding: '12px 16px', borderRadius: 7, textAlign: 'left',
          border: `1px solid ${sync.kind === 'error' ? 'var(--lbb-bad-bar)' : 'var(--lbb-border)'}`,
          background: sync.kind === 'error' ? 'var(--lbb-bad-bg)' : 'var(--lbb-surface)',
        }}>
          {sync.kind === 'error' ? (
            <>
              <Icon name="alert" size={14} style={{ color: 'var(--lbb-bad-fg)', flex: '0 0 auto' }} />
              <p style={{ margin: 0, fontSize: 13, color: 'var(--lbb-bad-fg)' }}>
                <b style={{ fontWeight: 600 }}>{t('screenCoverage.syncFailedTitle')}</b>{' '}
                <span style={{ color: 'var(--lbb-fg2)' }}>{t('screenCoverage.syncFailedBody')}</span>
              </p>
              <span style={{ marginLeft: narrow ? 0 : 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg3)' }}>
                  {lastSyncOk
                    ? t('screenCoverage.syncLastOk', { when: lastSyncOk })
                    : lastCheckedWhen && t('screenCoverage.lastChecked', { when: lastCheckedWhen })}
                </span>
                <Button
                  size="sm" variant="secondary"
                  onClick={e => { e.stopPropagation(); void runSync() }}
                >
                  {t('screenCoverage.syncRetry')}
                </Button>
              </span>
            </>
          ) : (
            <>
              <span
                aria-hidden="true"
                className={sync.kind === 'busy' ? undefined : 'lbb-cov-dot'}
                style={{
                  position: 'relative', width: 8, height: 8, borderRadius: '50%', flex: '0 0 auto',
                  background: sync.kind === 'newer'
                    ? 'var(--lbb-warn-fg)'
                    : complete ? 'var(--lbb-ok-fg)' : 'var(--lbb-accent-mid)',
                }}
              />
              <p style={{ margin: 0, fontSize: 13, color: 'var(--lbb-fg2)', lineHeight: 1.5 }}>
                {sync.kind === 'busy' && t('screenCoverage.syncChecking')}
                {sync.kind === 'uptodate' && (
                  <b style={{ color: 'var(--lbb-fg)', fontWeight: 600 }}>
                    {t('screenCoverage.syncUpToDate', { version: sync.version })}
                  </b>
                )}
                {sync.kind === 'newer' && (
                  <>
                    <b style={{ color: 'var(--lbb-fg)', fontWeight: 600 }}>
                      {t('screenCoverage.syncNewer', { version: sync.version })}
                    </b>{' '}
                    <a
                      href="#/setup"
                      onClick={e => { e.stopPropagation(); e.preventDefault(); navigate('/setup') }}
                      style={{ color: 'var(--lbb-accent-mid)', cursor: 'pointer' }}
                    >
                      {t('screenCoverage.syncOpenSetup')}
                    </a>
                  </>
                )}
                {sync.kind === 'idle' && (
                  <>
                    <b style={{ color: 'var(--lbb-fg)', fontWeight: 600 }}>
                      {complete ? t('screenCoverage.liveTitle') : t('screenCoverage.workTitle')}
                    </b>{' '}
                    {complete ? t('screenCoverage.liveBody') : t('screenCoverage.workBody')}
                    {!complete && (
                      <>
                        {' '}
                        <a
                          href="#/tapematch"
                          onClick={e => { e.stopPropagation(); e.preventDefault(); navigate('/tapematch') }}
                          style={{ color: 'var(--lbb-accent-mid)', cursor: 'pointer' }}
                        >
                          {t('screenCoverage.workLink')}
                        </a>
                      </>
                    )}
                  </>
                )}
              </p>
              <span style={{
                marginLeft: narrow ? 0 : 'auto', textAlign: narrow ? 'left' : 'right',
                fontFamily: 'var(--lbb-mono)', fontSize: 11, lineHeight: 1.6,
                color: 'var(--lbb-fg3)', whiteSpace: 'nowrap',
              }}>
                {lastCheckedWhen && (
                  <>
                    {t('screenCoverage.lastChecked', { when: lastCheckedWhen })}
                    <br />
                  </>
                )}
                {t('screenCoverage.cadence')}
              </span>
            </>
          )}
        </div>

        {/* Signature row. The prototype's "· 412 sessions" clause is dropped —
            this app keeps no session log, and §4 forbids invented numbers. */}
        <div style={{
          marginTop: 'auto', paddingTop: 22, width: '100%',
          display: 'flex', flexDirection: narrow ? 'column' : 'row',
          alignItems: narrow ? 'flex-start' : 'flex-end',
          justifyContent: 'space-between', gap: narrow ? 10 : 30, textAlign: 'left',
        }}>
          <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11, lineHeight: 1.6, color: 'var(--lbb-fg3)' }}>
            <strong style={{ display: 'block', color: 'var(--lbb-fg2)', fontWeight: 500 }}>
              {snap.last_import && (complete
                ? t('screenCoverage.sigCaughtUp', { date: dateOnly(snap.last_import) })
                : t('screenCoverage.sigLastImport', { date: dateOnly(snap.last_import) }))}
            </strong>
            {stats.first_entry_filed_at && t('screenCoverage.sigFiled', {
              date: stats.first_entry_filed_at, days: stats.days_active,
            })}
          </div>
          <div style={{
            fontFamily: 'var(--lbb-mono)', fontSize: 11, lineHeight: 1.6,
            color: 'var(--lbb-fg3)', textAlign: narrow ? 'left' : 'right',
          }}>
            <strong style={{ display: 'block', color: 'var(--lbb-fg2)', fontWeight: 500 }}>
              {t('screenCoverage.sigLedger')}
            </strong>
            {t('screenCoverage.sigSigned', {
              hash: shortHash(cov.ledger_sha256), signer: cov.signed_by,
            })}
          </div>
        </div>
      </div>

      {/* Action row — outside the card, so it can never be swallowed by
          click-to-replay (§8). */}
      <div style={{
        ...cardWrap,
        display: 'flex', flexDirection: narrow ? 'column' : 'row',
        justifyContent: 'center', alignItems: 'center', gap: 10, padding: '24px 0 20px',
      }}>
        {complete ? (
          <Button
            variant="primary" icon="download" block={narrow}
            onClick={() => setExportOpen(true)}
            style={{
              background: 'var(--lbb-award-mid)', borderColor: 'var(--lbb-award-mid)',
              color: 'var(--lbb-award-on)',
            }}
            // Button's own hover handler repaints with --lbb-accent-hi, which
            // would drop the gold on hover. These land in its {...rest} spread,
            // which is applied last, so they win. §2 "Button specs": gold →
            // gold-hi on hover, gold-lo while pressed.
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--lbb-award-hi)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--lbb-award-mid)' }}
            onMouseDown={e => { e.currentTarget.style.background = 'var(--lbb-award-lo)' }}
            onMouseUp={e => { e.currentTarget.style.background = 'var(--lbb-award-hi)' }}
          >
            {t('screenCoverage.actExport')}
          </Button>
        ) : (
          <Button variant="primary" icon="tapematch" block={narrow} onClick={() => navigate('/tapematch')}>
            {t('screenCoverage.actTapeMatch')}
          </Button>
        )}
        <Button
          variant="secondary" block={narrow}
          disabled={sync.kind === 'busy'} aria-busy={sync.kind === 'busy'}
          onClick={() => void runSync()}
        >
          {sync.kind === 'busy'
            ? <Icon name="refresh" size={13} className="p2-spin" />
            : t('screenCoverage.actSync')}
        </Button>
        <Button variant="ghost" block={narrow} onClick={() => navigate('/lbdir/ledger')}>
          {t('screenCoverage.actLedger')}
        </Button>
        <Button variant="ghost" block={narrow} onClick={() => navigate('/lbdir/sync')}>
          {t('screenCoverage.actSyncHistory')}
        </Button>
      </div>

      {exportOpen && view && (
        <CertificateModal view={view} onClose={() => setExportOpen(false)} />
      )}
    </div>
  )
}

// ── Loading skeleton (§6 — never a bare spinner) ─────────────────────────────

function ShimmerBlock({ h, w, r = 4 }: { h: number; w?: number | string; r?: number }): React.JSX.Element {
  return (
    <div className="lbb-cov-shimmer" style={{
      position: 'relative', overflow: 'hidden',
      height: h, width: w ?? '100%', borderRadius: r,
      background: 'var(--lbb-surface2)',
    }} />
  )
}

function CoverageSkeleton({ tier, rootRef }: {
  tier: Tier
  rootRef: (el: HTMLDivElement | null) => void
}): React.JSX.Element {
  const narrow = tier === 'sm' || tier === 'xs'
  return (
    <div
      ref={rootRef}
      aria-busy="true"
      style={{
        minHeight: '100%', display: 'flex', flexDirection: 'column',
        padding: narrow ? '24px 16px 20px' : '56px 0 20px', background: 'var(--lbb-bg)',
      }}
    >
      <div style={{
        maxWidth: 1180, width: '100%', margin: '0 auto', flex: 1,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18,
        padding: narrow ? '30px 26px 24px' : '38px 56px 30px', borderRadius: 6,
        border: '1px solid var(--lbb-border)',
        background: 'linear-gradient(180deg, var(--lbb-surface), var(--lbb-bg))',
      }}>
        <ShimmerBlock h={88} w={88} r={44} />
        <ShimmerBlock h={11} w={200} />
        <ShimmerBlock h={40} w={460} />
        <ShimmerBlock h={44} w={620} />
        <div style={{
          width: '100%', marginTop: 8,
          display: 'grid', gridTemplateColumns: narrow ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)', gap: 2,
        }}>
          {[0, 1, 2, 3].map(i => <ShimmerBlock key={i} h={64} r={0} />)}
        </div>
        <div style={{ width: '100%', display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 6 }}>
          {[0, 1, 2, 3, 4, 5, 6, 7].map(i => <ShimmerBlock key={i} h={17} r={3} />)}
        </div>
        <ShimmerBlock h={46} r={7} />
      </div>
    </div>
  )
}

// ── Certificate export modal (§5) ────────────────────────────────────────────

function CertificateModal({ view, onClose }: {
  view: CoveragePayload
  onClose: () => void
}): React.JSX.Element {
  const { t } = useTranslation()
  // PDF rides the existing dossier bridge (a hidden BrowserWindow prints a URL
  // to PDF). Outside Electron that bridge is absent, so the option is omitted
  // rather than pulling in a PDF dependency (scope decision 3).
  const pdfAvailable = typeof window.api?.printDossierPdf === 'function'
  const [format, setFormat] = useState<'png' | 'pdf'>('png')
  const [withSignature, setWithSignature] = useState(true)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const cov = view.coverage
  const snap = view.snapshot

  const build = (): string => renderCertificatePng({
    eyebrow: snap.label
      ? t('screenCoverage.eyebrowComplete', { label: snap.label })
      : t('screenCoverage.eyebrowCompleteNoLabel'),
    headline: t('screenCoverage.headlineComplete'),
    subhead: snap.label
      ? t('screenCoverage.subheadComplete', { month: monthName(snap.label) })
      : t('screenCoverage.subheadCompleteNoMonth'),
    stats: [
      { value: fmt(cov.entries_held), label: t('screenCoverage.statHeld') },
      { value: fmt(cov.recordings),   label: t('screenCoverage.statRecordings') },
      { value: fmt(cov.families),     label: t('screenCoverage.statFamilies') },
      { value: fmt(cov.entries_missing), label: t('screenCoverage.statMissing') },
    ],
    eras: cov.by_decade,
    sigLeft: withSignature
      ? [
        snap.last_import ? t('screenCoverage.sigCaughtUp', { date: dateOnly(snap.last_import) }) : '',
        view.stats.first_entry_filed_at
          ? t('screenCoverage.sigFiled', {
              date: view.stats.first_entry_filed_at, days: view.stats.days_active,
            })
          : '',
      ]
      : ['', ''],
    sigRight: withSignature
      ? [
        t('screenCoverage.sigLedger'),
        t('screenCoverage.sigSigned', {
          hash: shortHash(cov.ledger_sha256), signer: cov.signed_by,
        }),
      ]
      : ['', ''],
  })

  const handleExport = async (): Promise<void> => {
    setBusy(true)
    setFailed(false)
    try {
      const png = build()
      if (!png) throw new Error('canvas')
      const stem = snap.label ? `losslessbob-complete-LB-${snap.label}` : 'losslessbob-complete-LB'
      if (format === 'pdf' && pdfAvailable) {
        const html = `<!doctype html><meta charset="utf-8"><style>@page{margin:0}`
          + `html,body{margin:0;padding:0;background:#fff}`
          + `img{display:block;width:100%}</style><img src="${png}">`
        const ok = await window.api.printDossierPdf(
          `data:text/html;base64,${btoa(unescape(encodeURIComponent(html)))}`,
          `${stem}.pdf`,
        )
        if (!ok) { setBusy(false); return }
      } else {
        dataUrlDownload(png, `${stem}.png`)
      }
      onClose()
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('screenCoverage.cert.title')}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 18,
      }}
    >
      <div style={{
        width: 420, maxWidth: '100%', padding: 24, borderRadius: 10,
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.35)',
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 4 }}>
          {t('screenCoverage.cert.title')}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--lbb-fg2)', marginBottom: 18 }}>
          {snap.label
            ? t('screenCoverage.eyebrowComplete', { label: snap.label })
            : t('screenCoverage.eyebrowCompleteNoLabel')}
        </div>

        {pdfAvailable && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.05,
              color: 'var(--lbb-fg3)', marginBottom: 6,
            }}>
              {t('screenCoverage.cert.format')}
            </div>
            <div style={{ display: 'flex', gap: 14 }}>
              {(['png', 'pdf'] as const).map(f => (
                <label key={f} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 13, color: 'var(--lbb-fg)', cursor: 'pointer',
                }}>
                  <input
                    type="radio" name="cert-format" checked={format === f}
                    onChange={() => setFormat(f)}
                  />
                  {f.toUpperCase()}
                </label>
              ))}
            </div>
          </div>
        )}

        <label style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 22,
          fontSize: 13, color: 'var(--lbb-fg)', cursor: 'pointer',
        }}>
          <input
            type="checkbox" checked={withSignature}
            onChange={e => setWithSignature(e.target.checked)}
          />
          {t('screenCoverage.cert.includeSignature')}
        </label>

        {failed && (
          <div style={{ marginBottom: 14, fontSize: 12, color: 'var(--lbb-bad-fg)' }}>
            {t('screenCoverage.cert.failed')}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            {t('screenCoverage.cert.cancel')}
          </Button>
          <Button variant="primary" size="sm" onClick={() => void handleExport()} disabled={busy}>
            {busy ? t('screenCoverage.cert.exporting') : t('screenCoverage.cert.export')}
          </Button>
        </div>
      </div>
    </div>
  )
}
