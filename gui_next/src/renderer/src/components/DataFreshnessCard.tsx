// "Updates" card on ScreenHome — the pipeline-freshness surface (Pipeline
// Refresh phases 1–4, instructions/PIPELINE_REFRESH_PHASE{1,2,3,4}.md),
// redesigned 2026-09-21 around one question: who does the work?
//
//   Ready to update — chainable steps; ONE Update button runs them all, in
//                     dependency order (POST /api/refresh/chain/start {all}).
//   Long jobs       — chainable but hours long (cost very_slow); never part
//                     of Update, each started on purpose with its own button.
//   Needs you       — manual steps + pending gate queues; each row opens the
//                     screen where the human does it.
//
// The bucket is computed server-side (refresh_exec.step_bucket), so the
// "Ready" rows are exactly what the Update chain runs. Trigger groups (T1–T4),
// Stale/Blocked, cost pills and the include-expensive checkbox are
// deliberately not shown — they were plumbing, not decisions for the user.

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Card, Pill, Button, ConfirmDialog } from './primitives'
import { copyText } from '../lib/clipboard'

const BASE = window.api.flaskBase

// ── Types (mirror backend/refresh.py + refresh_exec.annotate_buckets) ───────

type Trigger = 'T1' | 'T2' | 'T3' | 'T4'
type StepState = 'fresh' | 'stale' | 'blocked' | 'unknown'
type Bucket = 'ready' | 'long' | 'needs_you' | 'fresh' | 'untracked'
type Cost = 'fast' | 'slow' | 'very_slow'

interface RefreshStep {
  step_id: string
  label: string
  trigger: Trigger
  state: StepState
  reason: string
  backlog: number | null
  upstream: string[]
  how_to_run: string
  cost: Cost
  bucket: Bucket
}

type QueueKind = 'gate' | 'backlog'
type QueueState = 'pending' | 'open' | 'clear' | 'unknown'

interface RefreshQueue {
  queue_id: string
  label: string
  kind: QueueKind
  count: number | null
  total: number | null
  blocks: string[]
  screen: string | null
  action: string
  state: QueueState
}

interface RefreshStatus {
  publish_lag: {
    published_at: string | null
    lb_status_changes_since: number
    days_since: number | null
  }
  steps: RefreshStep[]
  update_order: string[]
  queues?: RefreshQueue[]
}

interface ChainPlan {
  runnable: Array<{ step_id: string; cost: Cost }>
  advisories?: Array<{ queue_id: string | null; count: number; step_id: string; kind: 'queue' | 'publish' }>
}

interface ChainStatusSnapshot {
  running: boolean
  done: number
  total: number
  current: string
  stop_requested: boolean
  sub_progress?: { done?: number; total?: number }
}

interface ChainHistoryEntry {
  status: 'ok' | 'partial' | 'stopped'
  steps: {
    plan: { runnable?: unknown[] }
    ran: Array<{ step_id: string }>
    errors: Array<{ step_id: string; message: string }>
  } | null
}

interface JobSnapshot { running: boolean; done?: number; total?: number }

// ── Static maps ─────────────────────────────────────────────────────────────

// Plain-language time word per cost tier — replaces the fast/slow/very_slow pill.
const COST_TIME = {
  fast: 'seconds', slow: 'minutes', very_slow: 'hours',
} as const satisfies Record<Cost, string>

// Where each step's data comes from, shown as a muted column (was the T1–T4 group).
const TRIGGER_SOURCE = {
  T1: 'lbSite', T2: 'yourFolders', T3: 'externalSources', T4: 'publishing',
} as const satisfies Record<Trigger, string>

// Long jobs the card can start itself. `modes` = the ranker's backlog/all split.
interface LongJobConfig { start: string; status: string; stop: string; modes?: boolean }
const LONG_JOBS: Record<string, LongJobConfig> = {
  scrape_entries: { start: '/api/scrape/start', status: '/api/scrape/status', stop: '/api/scrape/stop' },
  ranker_scan: {
    start: '/api/ranker/scan', status: '/api/ranker/scan/status', stop: '/api/ranker/scan/stop', modes: true,
  },
}

// Stable API namespaces mapped to the screen that owns them — a Needs-you
// row's "Open" target. Unmapped routes fall back to a copyable command.
const ROUTE_NAV_PREFIXES: Array<[prefix: string, path: string]> = [
  ['/api/pipeline', '/pipeline'],
  ['/api/flat_file', '/setup'],
  ['/api/tapematch', '/tapematch'],
  ['/api/scrape', '/scraper'],
  ['/api/fingerprint', '/fingerprint'],
  ['/api/attachments', '/attachments'],
]

function navTargetForRoute(route: string): string | null {
  if (!route.startsWith('POST ') && !route.startsWith('GET ')) return null
  const path = route.replace(/^(POST|GET)\s+/, '').trim()
  const hit = ROUTE_NAV_PREFIXES.find(([prefix]) => path.startsWith(prefix))
  return hit ? hit[1] : null
}

const stepName = (t: TFunction, id: string, fallback?: string): string =>
  t(`refresh.steps.${id}`, fallback ?? id)

// ── Shared row / section chrome ─────────────────────────────────────────────

const ROW: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px',
  borderBottom: '1px solid var(--lbb-border)', flexWrap: 'wrap',
}
const MUTED: React.CSSProperties = { fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }

function NameCell({ name, why }: { name: string; why?: string }): React.JSX.Element {
  return (
    <div style={{ flex: '1 1 220px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 500 }}>{name}</span>
      {why && <span style={MUTED}>{why}</span>}
    </div>
  )
}

function Section({ title, hint, children }: {
  title: string; hint: string; children: React.ReactNode
}): React.JSX.Element {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{
          margin: 0, fontSize: 'var(--lbb-fs-11)', fontWeight: 600, textTransform: 'uppercase',
          letterSpacing: 0.5, color: 'var(--lbb-fg)',
        }}>{title}</h3>
        <span style={MUTED}>{hint}</span>
      </div>
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
        {/* -1px swallows the last row's bottom border into the frame's own. */}
        <div style={{ marginBottom: -1 }}>{children}</div>
      </div>
    </section>
  )
}

function Modal({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div role="dialog" style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', borderRadius: 10,
        padding: 24, maxWidth: 520, width: '92%', maxHeight: '80vh', overflowY: 'auto',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)', display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        {children}
      </div>
    </div>
  )
}

// ── Update confirm dialog ───────────────────────────────────────────────────
// Fed by /api/refresh/chain/preview {all}; confirm re-plans server-side via
// /api/refresh/chain/start (spec §3.4 — never trust a client-side plan).

function UpdateDialog({ notIncluded, onClose, onStarted }: {
  notIncluded: { long: number; needs: number }
  onClose: () => void
  onStarted: (steps: string[]) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [plan, setPlan] = useState<ChainPlan | null>(null)
  const [starting, setStarting] = useState(false)
  const [warn, setWarn] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${BASE}/api/refresh/chain/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: true }),
    })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('preview'))))
      .then((data: ChainPlan) => setPlan(data))
      .catch(() => setWarn(t('refresh.runFailed')))
  }, [t])

  const confirm = useCallback(() => {
    setWarn(null)
    setStarting(true)
    fetch(`${BASE}/api/refresh/chain/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: true }),
    })
      .then(async r => {
        const body = await r.json().catch(() => ({}))
        setStarting(false)
        if (r.status === 409) {
          setWarn(body.error === 'blocked_by_running' && Array.isArray(body.blocked_by_running)
            ? t('refresh.update.busyStep', {
              steps: body.blocked_by_running.map((id: string) => stepName(t, id)).join(', '),
            })
            : t('refresh.update.alreadyRunning'))
          return
        }
        if (!r.ok) { setWarn(t('refresh.runFailed')); return }
        onStarted(Array.isArray(body.steps) ? body.steps : [])
        onClose()
      })
      .catch(() => { setStarting(false); setWarn(t('refresh.runFailed')) })
  }, [onStarted, onClose, t])

  const runnable = plan?.runnable ?? []
  const advisories = plan?.advisories ?? []

  return (
    <Modal>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700 }}>
          {plan ? t('refresh.update.confirmTitle', { count: runnable.length }) : t('common.loading', 'Loading…')}
        </div>
        <div style={MUTED}>{t('refresh.update.confirmBody')}</div>
      </div>

      {plan && (
        <ol style={{ margin: 0, padding: 0, listStyle: 'none', border: '1px solid var(--lbb-border)', borderRadius: 8 }}>
          {runnable.map((item, i) => (
            <li key={item.step_id} style={{ ...ROW, padding: '7px 12px' }}>
              <span style={{ width: 16, textAlign: 'right', fontFamily: 'var(--lbb-mono)', ...MUTED }}>{i + 1}</span>
              <span style={{ flex: 1, fontSize: 'var(--lbb-fs-12-5)' }}>{stepName(t, item.step_id)}</span>
              <span style={MUTED}>{t(`refresh.time.${COST_TIME[item.cost]}`)}</span>
            </li>
          ))}
        </ol>
      )}

      {/* Phase 4 §3.5: advisories are text, never a gate — Update stays enabled. */}
      {advisories.length > 0 && (
        <div style={{
          padding: '10px 12px', borderRadius: 8, background: 'var(--lbb-warn-bg)',
          fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg)', lineHeight: 1.5,
        }}>
          {advisories.map((adv, i) => (
            <div key={`${adv.kind}-${adv.queue_id ?? 'all'}-${i}`}>
              {adv.kind === 'publish'
                ? t('refresh.queues.advisoryPublish', { count: adv.count })
                : t('refresh.queues.advisoryQueue', {
                  step: stepName(t, adv.step_id), count: adv.count,
                  queue: t(`refresh.queues.labels.${adv.queue_id}`, adv.queue_id ?? ''),
                })}
            </div>
          ))}
          <div style={{ color: 'var(--lbb-fg2)' }}>{t('refresh.update.advisoryOk')}</div>
        </div>
      )}

      {(notIncluded.long > 0 || notIncluded.needs > 0) && (
        <div style={MUTED}>
          {t('refresh.update.notIncluded', {
            needs: notIncluded.needs, long: t('refresh.longJobs', { count: notIncluded.long }),
          })}
        </div>
      )}

      {warn && <Pill tone="bad" soft title={warn}>{warn}</Pill>}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
        <Button variant="primary" disabled={!plan || starting || runnable.length === 0} onClick={confirm}>
          {t('refresh.update.confirm')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Long-job row ────────────────────────────────────────────────────────────

function LongJobRow({ step, onDone }: { step: RefreshStep; onDone: () => void }): React.JSX.Element {
  const { t } = useTranslation()
  const config = LONG_JOBS[step.step_id]
  const [snap, setSnap] = useState<JobSnapshot | null>(null)
  const [confirming, setConfirming] = useState<'start' | 'all' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const wasRunning = useRef(false)

  const poll = useCallback(() => {
    if (!config) return
    fetch(`${BASE}${config.status}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('status'))))
      .then((s: JobSnapshot) => {
        setSnap(s)
        if (s.running) {
          wasRunning.current = true
          if (pollRef.current === null) pollRef.current = window.setInterval(poll, 2000)
        } else {
          if (pollRef.current !== null) { window.clearInterval(pollRef.current); pollRef.current = null }
          if (wasRunning.current) { wasRunning.current = false; onDone() }
        }
      })
      .catch(() => {})
  }, [config, onDone])

  // A job started elsewhere (Scraper screen, another window) shows as running here too.
  useEffect(() => {
    poll()
    return () => { if (pollRef.current !== null) window.clearInterval(pollRef.current) }
  }, [poll])

  const start = useCallback((body: Record<string, unknown>) => {
    if (!config) return
    setConfirming(null)
    setError(null)
    fetch(`${BASE}${config.start}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
      .then(r => {
        if (r.status === 409) setError(t('refresh.alreadyRunning'))
        else if (!r.ok) setError(t('refresh.runFailed'))
        else { wasRunning.current = true; poll() }
      })
      .catch(() => setError(t('refresh.runFailed')))
  }, [config, poll, t])

  const stop = useCallback(() => {
    if (config) fetch(`${BASE}${config.stop}`, { method: 'POST' }).catch(() => {})
  }, [config])

  const name = stepName(t, step.step_id, step.label)
  const why = step.backlog !== null
    ? t(`refresh.long.backlog.${step.step_id}`, { count: step.backlog, defaultValue: step.reason })
    : step.reason

  let controls: React.JSX.Element
  if (!config) {
    controls = <FallbackAction route={step.how_to_run} />
  } else if (snap?.running) {
    controls = (
      <>
        <span style={MUTED}>
          {snap.total ? t('refresh.long.progress', { done: snap.done ?? 0, total: snap.total }) : t('refresh.running')}
        </span>
        <Button variant="ghost" onClick={stop}>{t('refresh.stop')}</Button>
      </>
    )
  } else if (config.modes) {
    controls = (
      <>
        <Button variant="secondary" disabled={!step.backlog} onClick={() => start({ mode: 'backlog' })}>
          {t('refresh.long.scanNew', { count: step.backlog ?? 0 })}
        </Button>
        <Button variant="ghost" onClick={() => setConfirming('all')}>{t('refresh.long.rescanAll')}</Button>
      </>
    )
  } else {
    controls = <Button variant="secondary" onClick={() => setConfirming('start')}>{t('refresh.long.start')}</Button>
  }

  return (
    <div style={ROW}>
      <NameCell name={name} why={why} />
      <span style={{ ...MUTED, flex: '0 0 auto' }}>{t('refresh.time.hours')}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
        {error && <Pill tone="bad" soft>{error}</Pill>}
        {controls}
      </div>
      {confirming === 'start' && (
        <ConfirmDialog
          title={t('refresh.long.confirmStart', { step: name })}
          body={t('refresh.long.confirmStartBody')}
          confirmLabel={t('refresh.long.start')} cancelLabel={t('common.cancel', 'Cancel')}
          onConfirm={() => start({})} onCancel={() => setConfirming(null)}
        />
      )}
      {confirming === 'all' && (
        <ConfirmDialog
          title={t('refresh.long.confirmRescan')}
          body={t('refresh.long.confirmRescanBody')}
          confirmLabel={t('refresh.long.rescanAllConfirm')} cancelLabel={t('common.cancel', 'Cancel')}
          onConfirm={() => start({ mode: 'all' })} onCancel={() => setConfirming(null)}
        />
      )}
    </div>
  )
}

// ── Needs-you row ───────────────────────────────────────────────────────────

function FallbackAction({ route }: { route: string }): React.JSX.Element {
  const { t } = useTranslation()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <code style={{
        fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)', background: 'var(--lbb-surface2)',
        border: '1px solid var(--lbb-border)', borderRadius: 5, padding: '2px 6px',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240,
      }} title={route}>{route}</code>
      <Button variant="ghost" size="sm" icon="copy" onClick={() => { void copyText(route) }}>
        {t('common.copy')}
      </Button>
    </div>
  )
}

function NeedsYouRow({ name, why, screen, route }: {
  name: string; why: string; screen: string | null; route?: string
}): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <div style={ROW}>
      <NameCell name={name} why={why} />
      <div style={{ marginLeft: 'auto' }}>
        {screen ? (
          <Button variant="ghost" iconRight="chevRight" onClick={() => navigate(screen)}
            style={{ color: 'var(--lbb-accent-mid)' }}>
            {t('refresh.needs.open')}
          </Button>
        ) : route ? (
          <FallbackAction route={route} />
        ) : null /* no screen resolves it (xref_filesets, decision 7): the why text says how */}
      </div>
    </div>
  )
}

// ── The card ────────────────────────────────────────────────────────────────

export function DataFreshnessCard(): React.JSX.Element | null {
  const { t } = useTranslation()
  const [status, setStatus] = useState<RefreshStatus | null>(null)
  const [failed, setFailed] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)

  // One global chain job; its live status lives at card level.
  const [chain, setChain] = useState<ChainStatusSnapshot | null>(null)
  const [chainSteps, setChainSteps] = useState<string[]>([])
  const [outcome, setOutcome] = useState<string | null>(null)
  const chainPollRef = useRef<number | null>(null)
  const chainWasRunningRef = useRef(false)

  const fetchStatus = useCallback(() => {
    fetch(`${BASE}/api/refresh/status`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('refresh status'))))
      .then((data: RefreshStatus) => setStatus(data))
      .catch(() => setFailed(true))
  }, [])

  const handleChainComplete = useCallback(() => {
    fetch(`${BASE}/api/refresh/chain/history?limit=1`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain history'))))
      .then((rows: ChainHistoryEntry[]) => {
        const entry = rows[0]
        if (!entry?.steps) return
        const ran = entry.steps.ran.length
        const total = entry.steps.plan?.runnable?.length ?? ran
        const firstError = entry.steps.errors[0]
        if (entry.status === 'ok') setOutcome(t('refresh.update.outcomeOk', { ran, total }))
        else if (entry.status === 'stopped') setOutcome(t('refresh.update.outcomeStopped', { ran, total }))
        else setOutcome(t('refresh.update.outcomePartial', {
          ran, total, step: firstError ? stepName(t, firstError.step_id) : '',
        }))
      })
      .catch(() => {})
      .finally(() => { setChainSteps([]); fetchStatus() })
  }, [fetchStatus, t])

  const pollChain = useCallback(() => {
    fetch(`${BASE}/api/refresh/chain/status`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain status'))))
      .then((snap: ChainStatusSnapshot) => {
        setChain(snap)
        if (snap.running) {
          chainWasRunningRef.current = true
          if (chainPollRef.current === null) chainPollRef.current = window.setInterval(pollChain, 2000)
        } else {
          if (chainPollRef.current !== null) { window.clearInterval(chainPollRef.current); chainPollRef.current = null }
          if (chainWasRunningRef.current) { chainWasRunningRef.current = false; handleChainComplete() }
        }
      })
      .catch(() => {})
  }, [handleChainComplete])

  const onChainStarted = useCallback((steps: string[]) => {
    setOutcome(null)
    setChainSteps(steps)
    chainWasRunningRef.current = true
    pollChain()
  }, [pollChain])

  const stopChain = useCallback(() => {
    fetch(`${BASE}/api/refresh/chain/stop`, { method: 'POST' })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain stop'))))
      .then((snap: ChainStatusSnapshot) => setChain(snap))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchStatus()
    pollChain()   // a chain started from another window should surface here
    return () => { if (chainPollRef.current !== null) window.clearInterval(chainPollRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (failed || !status) return null

  const byId = new Map(status.steps.map(s => [s.step_id, s]))
  const ready = status.update_order.map(id => byId.get(id)).filter((s): s is RefreshStep => !!s)
  const long = status.steps.filter(s => s.bucket === 'long')
  const manual = status.steps.filter(s => s.bucket === 'needs_you')
  const untracked = status.steps.filter(s => s.bucket === 'untracked')
  const freshCount = status.steps.filter(s => s.bucket === 'fresh').length
  const queues = status.queues ?? []
  const gateQueues = queues.filter(q => q.kind === 'gate' && q.state === 'pending')
  const backlogQueues = queues.filter(q => q.kind === 'backlog' && (q.total ?? 0) > 0)
  const needsCount = manual.length + gateQueues.length
  const behind = ready.length + long.length + needsCount
  const running = !!chain?.running

  const pl = status.publish_lag
  const publishLag = !!pl.published_at
    && ((pl.days_since !== null && pl.days_since >= 7) || pl.lb_status_changes_since > 0)

  // "After step N" for a row whose upstream is also in this Update run.
  const readyIndex = new Map(ready.map((s, i) => [s.step_id, i + 1]))
  const readyWhy = (s: RefreshStep): string => {
    const after = s.upstream.map(u => readyIndex.get(u)).filter((n): n is number => n !== undefined)
    if (s.state === 'blocked' && after.length > 0) {
      return t('refresh.ready.after', { count: after.length, steps: after.join(', ') })
    }
    return s.reason
  }

  const subtitle = behind === 0
    ? t('refresh.allUpToDate')
    : t('refresh.summary', {
      total: behind, ready: ready.length, needs: needsCount,
      long: t('refresh.longJobs', { count: long.length }),
    })

  const action = running ? (
    <Button variant="secondary" disabled={chain?.stop_requested} onClick={stopChain}>
      {chain?.stop_requested ? t('refresh.update.stopping') : t('refresh.update.stop')}
    </Button>
  ) : (
    <Button variant="primary" icon="refresh" disabled={ready.length === 0} onClick={() => setDialogOpen(true)}>
      {t('refresh.update.button', { count: ready.length })}
    </Button>
  )

  return (
    <Card title={t('refresh.title')} subtitle={subtitle} action={action} pad={14} style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

        {running && chain && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={MUTED}>
              {t('refresh.update.progress', {
                n: Math.min(chain.done + 1, chain.total), total: chain.total,
                step: stepName(t, chain.current || '—'),
              })}
              {chain.sub_progress?.total ? ` (${chain.sub_progress.done ?? 0}/${chain.sub_progress.total})` : ''}
            </div>
            <div style={{ height: 5, borderRadius: 3, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
              <div style={{
                width: `${chain.total ? Math.round((chain.done / chain.total) * 100) : 0}%`,
                height: '100%', background: 'var(--lbb-accent-mid)', transition: 'width 0.4s',
              }} />
            </div>
            {chainSteps.length > 0 && (
              <ol style={{
                margin: 0, padding: 0, listStyle: 'none', display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '2px 24px',
              }}>
                {chainSteps.map((id, i) => {
                  const done = i < chain.done
                  const current = id === chain.current
                  return (
                    <li key={id} style={{
                      display: 'flex', gap: 8, fontSize: 'var(--lbb-fs-12)',
                      color: current ? 'var(--lbb-fg)' : 'var(--lbb-fg2)', fontWeight: current ? 600 : 400,
                    }}>
                      <span style={{ width: 12, fontFamily: 'var(--lbb-mono)' }}>{done ? '✓' : current ? '›' : '·'}</span>
                      {stepName(t, id)}
                    </li>
                  )
                })}
              </ol>
            )}
          </div>
        )}

        {!running && outcome && <Pill tone="mute" soft>{outcome}</Pill>}

        {!running && ready.length > 0 && (
          <Section title={t('refresh.ready.title')} hint={t('refresh.ready.hint')}>
            {ready.map((s, i) => (
              <div key={s.step_id} style={ROW}>
                <span style={{ width: 16, textAlign: 'right', fontFamily: 'var(--lbb-mono)', ...MUTED }}>{i + 1}</span>
                <NameCell name={stepName(t, s.step_id, s.label)} why={readyWhy(s)} />
                <span style={{ ...MUTED, width: 130 }}>{t(`refresh.source.${TRIGGER_SOURCE[s.trigger]}`)}</span>
                <span style={{ ...MUTED, width: 64, textAlign: 'right' }}>{t(`refresh.time.${COST_TIME[s.cost]}`)}</span>
              </div>
            ))}
          </Section>
        )}

        {long.length > 0 && (
          <Section title={t('refresh.long.title')} hint={t('refresh.long.hint')}>
            {long.map(s => <LongJobRow key={s.step_id} step={s} onDone={fetchStatus} />)}
          </Section>
        )}

        {(needsCount > 0 || publishLag) && (
          <Section title={t('refresh.needs.title')} hint={t('refresh.needs.hint')}>
            {gateQueues.map(q => (
              <NeedsYouRow
                key={q.queue_id}
                name={t(`refresh.queues.labels.${q.queue_id}`, q.label)}
                why={`${t('refresh.queues.pending', { count: q.count ?? 0 })} · ${t(`refresh.queues.actions.${q.queue_id}`, q.action)}`}
                screen={q.screen}
              />
            ))}
            {manual.map(s => (
              <NeedsYouRow
                key={s.step_id}
                name={stepName(t, s.step_id, s.label)}
                why={s.step_id === 'master_publish' && publishLag
                  ? t('refresh.publishLag', { days: pl.days_since ?? 0, changes: pl.lb_status_changes_since })
                  : s.reason}
                screen={navTargetForRoute(s.how_to_run)}
                route={s.how_to_run}
              />
            ))}
            {publishLag && !manual.some(s => s.step_id === 'master_publish') && (
              <NeedsYouRow
                name={stepName(t, 'master_publish')}
                why={t('refresh.publishLag', { days: pl.days_since ?? 0, changes: pl.lb_status_changes_since })}
                screen={null}
                route={byId.get('master_publish')?.how_to_run}
              />
            )}
          </Section>
        )}

        <div style={{
          display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 12,
          borderTop: '1px solid var(--lbb-border)',
        }}>
          {backlogQueues.map(q => {
            const total = q.total ?? 0
            const done = Math.max(0, total - (q.count ?? 0))
            return (
              <div key={q.queue_id} style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                <span style={{ ...MUTED, flex: '1 1 200px' }}>
                  {t(`refresh.queues.labels.${q.queue_id}`, q.label)} · {t('refresh.queues.ratio', { done, total })}
                </span>
                <div style={{ width: 200, height: 4, borderRadius: 2, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round((done / total) * 100)}%`, height: '100%', background: 'var(--lbb-fg3)' }} />
                </div>
              </div>
            )
          })}
          <details style={MUTED}>
            <summary style={{ cursor: 'pointer' }}>
              {t('refresh.footer', { fresh: freshCount, untracked: untracked.length })}
            </summary>
            {untracked.length > 0 && (
              <div style={{ padding: '6px 0 0 14px', lineHeight: 1.6 }}>
                {t('refresh.untrackedList', {
                  steps: untracked.map(s => stepName(t, s.step_id, s.label)).join(', '),
                })}
              </div>
            )}
          </details>
        </div>
      </div>

      {dialogOpen && (
        <UpdateDialog
          notIncluded={{ long: long.length, needs: needsCount }}
          onClose={() => setDialogOpen(false)}
          onStarted={onChainStarted}
        />
      )}
    </Card>
  )
}
