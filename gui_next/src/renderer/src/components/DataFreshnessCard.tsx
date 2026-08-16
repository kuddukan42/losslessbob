// "Data freshness" card — Pipeline Refresh Phase 1+2, spec §2.4
// (instructions/PIPELINE_REFRESH_PHASE1.md, instructions/PIPELINE_REFRESH_PHASE2.md).
// Reads GET /api/refresh/status and summarises stale/blocked pipeline steps
// on ScreenHome.
//
// Phase 1 is read-only (spec §6: "nothing new becomes executable"). Every
// how_to_run is rendered as copyable text; the only exception is a small,
// conservative prefix map from stable existing API namespaces to the screen
// that already owns them (e.g. /api/pipeline/* -> the Pipeline screen) — those
// render as a "Go to…" navigation button, never a route-firing button. When a
// prefix isn't recognised the value falls back to copyable text, per the task
// spec's "prefer copyable text everywhere if navigation targets aren't
// obvious" guidance.
//
// Phase 2 (TODO-306) adds real "Run" buttons for exactly the four newly
// wrapped steps (RUNNABLE below) — every other row keeps the Phase 1
// copyable-text/nav-button behaviour untouched.

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Card, Pill, Button, ConfirmDialog } from './primitives'
import type { StatusTone } from './primitives'

const BASE = window.api.flaskBase

// ── Types (mirrors backend/refresh.py's GET /api/refresh/status shape) ──────

type Trigger = 'T1' | 'T2' | 'T3' | 'T4'
type StepState = 'fresh' | 'stale' | 'blocked' | 'unknown'
type VersionState = 'ok' | 'changed' | 'unstamped' | 'n/a'

interface VersionInfo {
  key: string | null
  state: VersionState
  expected: string | null
  stored: string | null
}

interface RefreshStep {
  step_id: string
  label: string
  trigger: Trigger
  kind: 'wholesale' | 'incremental' | 'manual'
  state: StepState
  reason: string
  last_run: string | null
  last_run_source: 'run_record' | 'watermark' | null
  last_run_status: string | null
  age_days: number | null
  backlog: number | null
  blocked_by: string | null
  upstream: string[]
  how_to_run: string
  cost: 'fast' | 'slow' | 'very_slow'
  human_gate: boolean
  version: VersionInfo
}

interface RefreshStatus {
  generated_at: string
  stale_count: number
  blocked_count: number
  unknown_count: number
  by_trigger: Record<Trigger, { total: number; stale: number; blocked: number; unknown: number }>
  publish_lag: {
    published_at: string | null
    lb_status_changes_since: number
    entries_scraped_since: number
    days_since: number | null
  }
  steps: RefreshStep[]
}

const TRIGGER_ORDER: Trigger[] = ['T1', 'T2', 'T3', 'T4']

const STATE_TONE: Record<StepState, StatusTone> = {
  fresh: 'ok', stale: 'warn', blocked: 'bad', unknown: 'mute',
}

// ── Phase 3 chain types (mirrors backend/refresh_exec.py's plan_chain() /
// get_status() / refresh_chain_runs shapes) ─────────────────────────────────

type ChainScope = { step_id: string; trigger?: undefined } | { trigger: string; step_id?: undefined }

interface ChainRunnableItem {
  step_id: string
  mode: 'inproc' | 'job'
  cost: 'fast' | 'slow' | 'very_slow'
  state: StepState
  reason: string
}

interface ChainWhyItem {
  step_id: string
  why: string
}

interface ChainPlan {
  scope: { step_id: string | null; trigger: string | null; include_expensive: boolean }
  runnable: ChainRunnableItem[]
  excluded: ChainWhyItem[]
  manual: ChainWhyItem[]
  blocked_by_running: string[]
  planned_at: string
}

interface ChainStatusSnapshot {
  running: boolean
  done: number
  total: number
  current: string
  errors: number
  skipped: number
  stage: string
  stop_requested: boolean
  started_at: string | null
  sub_progress?: { done?: number; total?: number }
}

interface ChainHistoryEntry {
  id: number
  scope_kind: 'step' | 'trigger'
  scope_value: string
  started_at: string
  finished_at: string | null
  status: 'ok' | 'partial' | 'stopped'
  steps: {
    plan: ChainPlan
    ran: Array<{ step_id: string; status: string }>
    skipped: Array<{ step_id: string; reason?: string; status?: string }>
    errors: Array<{ step_id: string; message: string }>
  } | null
  notes: string | null
}

const COST_TONE: Record<'fast' | 'slow' | 'very_slow', StatusTone> = {
  fast: 'mute', slow: 'warn', very_slow: 'bad',
}

// Stable existing API namespaces mapped to the screen that already owns them.
// Conservative on purpose — see file header. Add entries only when a step's
// how_to_run route is unambiguously owned by one existing screen.
const ROUTE_NAV_PREFIXES: Array<[prefix: string, path: string]> = [
  ['/api/pipeline', '/pipeline'],
  ['/api/flat_file', '/setup'],
  ['/api/tapematch', '/tapematch'],
  ['/api/scrape', '/scraper'],
  ['/api/fingerprint', '/fingerprint'],
  ['/api/attachments', '/attachments'],
]

function navTargetForRoute(route: string): string | null {
  const path = route.replace(/^(POST|GET)\s+/, '').trim()
  const hit = ROUTE_NAV_PREFIXES.find(([prefix]) => path.startsWith(prefix))
  return hit ? hit[1] : null
}

function fmtAge(ageDays: number | null): string {
  if (ageDays === null) return '—'
  return `${Math.max(0, ageDays)}d`
}

// TODO-306 Phase 2: the four wrapped CLI-only steps get a real Run button.
// { start } is always a POST route; { status, stop } are omitted for
// ranker_rerank, which is synchronous/pure-DB (no background job to poll).
interface RunnableConfig {
  start: string
  status?: string
  stop?: string
}

const RUNNABLE: Record<string, RunnableConfig> = {
  olof_fetch: {
    start: '/api/olof/fetch', status: '/api/olof/fetch/status', stop: '/api/olof/fetch/stop',
  },
  bobserve_fetch: {
    start: '/api/bobserve/fetch', status: '/api/bobserve/fetch/status',
    stop: '/api/bobserve/fetch/stop',
  },
  ranker_scan: {
    start: '/api/ranker/scan', status: '/api/ranker/scan/status', stop: '/api/ranker/scan/stop',
  },
  ranker_rerank: { start: '/api/ranker/rerank' },
}

interface JobStatusSnapshot {
  running: boolean
  done?: number
  total?: number
}

function RunControl({ step, onRefresh }: { step: RefreshStep; onRefresh: () => void }): React.JSX.Element {
  const { t } = useTranslation()
  const config = RUNNABLE[step.step_id]
  const [confirming, setConfirming] = useState<'fetch' | 'scan' | null>(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ done?: number; total?: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => () => { if (pollRef.current !== null) window.clearInterval(pollRef.current) }, [])

  const pollStatus = useCallback(() => {
    if (!config.status) return
    pollRef.current = window.setInterval(() => {
      fetch(`${BASE}${config.status}`)
        .then(r => (r.ok ? r.json() : Promise.reject(new Error('status'))))
        .then((snap: JobStatusSnapshot) => {
          setProgress({ done: snap.done, total: snap.total })
          if (!snap.running) {
            if (pollRef.current !== null) window.clearInterval(pollRef.current)
            pollRef.current = null
            setRunning(false)
            setProgress(null)
            onRefresh()
          }
        })
        .catch(() => {})
    }, 2000)
  }, [config.status, onRefresh])

  const startRun = useCallback((body: Record<string, unknown> = {}) => {
    setError(null)
    setConfirming(null)
    setRunning(true)
    fetch(`${BASE}${config.start}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async r => {
        if (r.status === 409) {
          setError(t('refresh.alreadyRunning'))
          setRunning(false)
          return
        }
        if (!r.ok) {
          setError(t('refresh.runFailed'))
          setRunning(false)
          return
        }
        const data = await r.json().catch(() => ({}))
        if (data.status === 'noop') {
          setRunning(false)
          onRefresh()
          return
        }
        if (config.status) {
          pollStatus()
        } else {
          // Synchronous route (ranker_rerank) — the POST already awaited completion.
          setRunning(false)
          onRefresh()
        }
      })
      .catch(() => {
        setError(t('refresh.runFailed'))
        setRunning(false)
      })
  }, [config.start, config.status, onRefresh, pollStatus, t])

  const stop = useCallback(() => {
    if (!config.stop) return
    fetch(`${BASE}${config.stop}`, { method: 'POST' }).catch(() => {})
  }, [config.stop])

  const label = progress?.total
    ? `${t('refresh.running')} ${progress.done ?? 0}/${progress.total}`
    : t('refresh.running')

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      {error && (
        <Pill tone="bad" soft title={error}>{error}</Pill>
      )}
      {running ? (
        <>
          <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{label}</span>
          {config.stop && (
            <Button variant="ghost" size="sm" onClick={stop}>{t('refresh.stop')}</Button>
          )}
        </>
      ) : (
        <Button
          variant="primary" size="sm"
          onClick={() => {
            if (step.step_id === 'ranker_scan') setConfirming('scan')
            else if (config.status) setConfirming('fetch')
            else startRun()
          }}
        >
          {t('refresh.run')}
        </Button>
      )}

      {confirming === 'fetch' && (
        <ConfirmDialog
          title={t('refresh.confirmFetch')}
          body={t('refresh.confirmFetchBody')}
          confirmLabel={t('refresh.run')}
          cancelLabel={t('common.cancel', 'Cancel')}
          onConfirm={() => startRun()}
          onCancel={() => setConfirming(null)}
        />
      )}

      {confirming === 'scan' && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
            borderRadius: 10, padding: 24, maxWidth: 440, width: '90%',
            boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
          }}>
            <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 8 }}>
              {t('refresh.confirmScanTitle')}
            </div>
            <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-bad-fg)', marginBottom: 20, lineHeight: 1.5 }}>
              {t('refresh.scanAllWarning')}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>
                {t('common.cancel', 'Cancel')}
              </Button>
              <Button variant="danger" size="sm" onClick={() => startRun({ mode: 'all' })}>
                {t('refresh.scanAll')}
              </Button>
              <Button variant="primary" size="sm" onClick={() => startRun({ mode: 'backlog' })}>
                {t('refresh.scanBacklog', { count: step.backlog ?? 0 })}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Phase 3: chain preview dialog + buttons ─────────────────────────────────
// Fed by /api/refresh/chain/preview; Confirm re-plans server-side via
// /api/refresh/chain/start (spec §3.4 — never trust a client-side plan).
// Modeled on RunControl's own hand-rolled dialog markup above (ConfirmDialog's
// `body: string` prop can't carry the runnable/won't-run lists this needs).

function ChainPreviewDialog({
  scope, scopeLabel, onClose, onStarted,
}: {
  scope: ChainScope
  scopeLabel: string
  onClose: () => void
  onStarted: () => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [plan, setPlan] = useState<ChainPlan | null>(null)
  const [includeExpensive, setIncludeExpensive] = useState(false)
  const [starting, setStarting] = useState(false)
  const [warn, setWarn] = useState<string | null>(null)

  const fetchPreview = useCallback((expensive: boolean) => {
    fetch(`${BASE}/api/refresh/chain/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...scope, include_expensive: expensive }),
    })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('preview'))))
      .then((data: ChainPlan) => setPlan(data))
      .catch(() => {})
    // scope is a stable prop for the dialog's lifetime (one scope per open).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { fetchPreview(includeExpensive) }, [fetchPreview, includeExpensive])

  const confirm = useCallback(() => {
    setWarn(null)
    setStarting(true)
    fetch(`${BASE}/api/refresh/chain/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...scope, include_expensive: includeExpensive }),
    })
      .then(async r => {
        if (r.status === 409) {
          const body = await r.json().catch(() => ({}))
          if (body.error === 'blocked_by_running' && Array.isArray(body.blocked_by_running)) {
            setWarn(t('refresh.chain.busyStep', { steps: body.blocked_by_running.join(', ') }))
          } else {
            setWarn(t('refresh.chain.alreadyRunning'))
          }
          setStarting(false)
          return
        }
        if (!r.ok) {
          setWarn(t('refresh.runFailed'))
          setStarting(false)
          return
        }
        setStarting(false)
        onStarted()
        onClose()
      })
      .catch(() => {
        setWarn(t('refresh.runFailed'))
        setStarting(false)
      })
  }, [scope, includeExpensive, onStarted, onClose, t])

  const runnable = plan?.runnable ?? []
  const manual = plan?.manual ?? []
  const excluded = plan?.excluded ?? []
  const wontRunOpen = manual.length > runnable.length

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 520, width: '92%', maxHeight: '80vh',
        overflowY: 'auto', boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 12 }}>
          {t('refresh.chain.previewTitle', { scope: scopeLabel })}
        </div>

        {!plan ? (
          <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg3)' }}>{t('common.loading', 'Loading…')}</div>
        ) : (
          <>
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg2)', marginBottom: 6 }}>
              {t('refresh.chain.willRun', { count: runnable.length })}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 14 }}>
              {runnable.map((item, i) => (
                <div key={item.step_id} style={{
                  display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-12)',
                }}>
                  <span style={{ color: 'var(--lbb-fg3)', width: 18, textAlign: 'right' }}>{i + 1}.</span>
                  <span style={{ flex: 1, minWidth: 0 }}>{t(`refresh.steps.${item.step_id}`, item.step_id)}</span>
                  <Pill tone={COST_TONE[item.cost]} soft>{item.cost}</Pill>
                </div>
              ))}
              {runnable.length === 0 && (
                <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>—</div>
              )}
            </div>

            {manual.length > 0 && (
              <details open={wontRunOpen} style={{ marginBottom: 14 }}>
                <summary style={{
                  cursor: 'pointer', fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg2)',
                }}>
                  {t('refresh.chain.wontRun', { count: manual.length })}
                </summary>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                  {manual.map(item => (
                    <div key={item.step_id} style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                      <strong style={{ color: 'var(--lbb-fg2)' }}>
                        {t(`refresh.steps.${item.step_id}`, item.step_id)}
                      </strong>
                      {' — '}{item.why}
                    </div>
                  ))}
                </div>
              </details>
            )}

            {excluded.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-12)', cursor: 'pointer',
                }}>
                  <input
                    type="checkbox" checked={includeExpensive}
                    onChange={e => setIncludeExpensive(e.target.checked)}
                  />
                  {t('refresh.chain.includeExpensive', { count: excluded.length })}
                </label>
                {!includeExpensive && (
                  <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 4, marginLeft: 24 }}>
                    {t('refresh.chain.excluded', { count: excluded.length })}:{' '}
                    {excluded.map(item => t(`refresh.steps.${item.step_id}`, item.step_id)).join(', ')}
                  </div>
                )}
              </div>
            )}

            {warn && <Pill tone="bad" soft title={warn} style={{ marginBottom: 12 }}>{warn}</Pill>}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
              <Button
                variant="primary" size="sm" disabled={starting || runnable.length === 0}
                onClick={confirm}
              >
                {t('refresh.chain.confirm')}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function ChainButton({
  label, scope, scopeLabel, onStarted,
}: {
  label: string
  scope: ChainScope
  scopeLabel: string
  onStarted: () => void
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>{label}</Button>
      {open && (
        <ChainPreviewDialog
          scope={scope} scopeLabel={scopeLabel}
          onClose={() => setOpen(false)}
          onStarted={onStarted}
        />
      )}
    </>
  )
}

function HowToRun({
  step, onRefresh, onChainStarted,
}: { step: RefreshStep; onRefresh: () => void; onChainStarted: () => void }): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Phase 3 §3.6: a blocked row can't be fixed by running itself (its
  // upstream is what's stale) — replace the copy-fallback with a chain
  // button regardless of whether the step also happens to be RUNNABLE.
  if (step.state === 'blocked') {
    return (
      <ChainButton
        label={t('refresh.chain.runChain')}
        scope={{ step_id: step.step_id }}
        scopeLabel={t(`refresh.steps.${step.step_id}`, step.label)}
        onStarted={onChainStarted}
      />
    )
  }

  if (RUNNABLE[step.step_id]) {
    return <RunControl step={step} onRefresh={onRefresh} />
  }

  const route = step.how_to_run
  const isRoute = route.startsWith('POST ') || route.startsWith('GET ')
  const navTarget = isRoute ? navTargetForRoute(route) : null

  if (navTarget) {
    return (
      <Button variant="ghost" size="sm" iconRight="chevRight" onClick={() => navigate(navTarget)}>
        {t('refresh.goTo')}
      </Button>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <code style={{
        fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', background: 'var(--lbb-surface2)',
        border: '1px solid var(--lbb-border)', borderRadius: 5, padding: '2px 6px',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 260,
      }}>{route}</code>
      <Button
        variant="ghost" size="sm" icon="copy"
        title={t('common.copy')}
        onClick={() => { void navigator.clipboard.writeText(route) }}
      >{t('common.copy')}</Button>
    </div>
  )
}

function StepRow({
  step, onRefresh, onChainStarted,
}: { step: RefreshStep; onRefresh: () => void; onChainStarted: () => void }): React.JSX.Element {
  const { t } = useTranslation()
  const tooltip = step.version?.state === 'changed'
    ? `${step.reason} — ${t('refresh.versionChanged')}`
    : step.reason
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '7px 4px',
      borderBottom: '1px solid var(--lbb-border)', flexWrap: 'wrap',
    }}>
      <span style={{ flex: '1 1 160px', fontSize: 'var(--lbb-fs-12-5)', minWidth: 0 }}>
        {t(`refresh.steps.${step.step_id}`, step.label)}
      </span>
      <Pill tone={STATE_TONE[step.state]} soft title={tooltip}>{t(`refresh.state.${step.state}`)}</Pill>
      <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', width: 34, textAlign: 'right' }}>
        {fmtAge(step.age_days)}
      </span>
      {step.backlog !== null && (
        <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('refresh.backlog', { count: step.backlog })}
        </span>
      )}
      <HowToRun step={step} onRefresh={onRefresh} onChainStarted={onChainStarted} />
    </div>
  )
}

export function DataFreshnessCard(): React.JSX.Element | null {
  const { t } = useTranslation()
  const [status, setStatus] = useState<RefreshStatus | null>(null)
  const [failed, setFailed] = useState(false)

  // Phase 3 §3.6: one global chain job, so its live status lives at card
  // level (not per-row) — every "Refresh T<n>"/"Run chain" button funnels
  // into the same poll loop and outcome line.
  const [chainStatus, setChainStatus] = useState<ChainStatusSnapshot | null>(null)
  const [chainOutcome, setChainOutcome] = useState<string | null>(null)
  const chainPollRef = useRef<number | null>(null)
  const chainWasRunningRef = useRef(false)

  const fetchStatus = useCallback((opts?: { keepOutcome?: boolean }) => {
    if (!opts?.keepOutcome) setChainOutcome(null)
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
        if (entry?.steps) {
          const ran = entry.steps.ran.length
          const total = entry.steps.plan?.runnable?.length ?? ran
          const firstError = entry.steps.errors[0]
          const step = firstError ? t(`refresh.steps.${firstError.step_id}`, firstError.step_id) : ''
          if (entry.status === 'ok') {
            setChainOutcome(t('refresh.chain.outcomeOk', { ran, total }))
          } else if (entry.status === 'stopped') {
            setChainOutcome(t('refresh.chain.outcomeStopped', { ran, total }))
          } else {
            setChainOutcome(t('refresh.chain.outcomePartial', { ran, total, step }))
          }
        }
      })
      .catch(() => {})
      .finally(() => fetchStatus({ keepOutcome: true }))
  }, [fetchStatus, t])

  const pollChainStatus = useCallback(() => {
    fetch(`${BASE}/api/refresh/chain/status`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain status'))))
      .then((snap: ChainStatusSnapshot) => {
        setChainStatus(snap)
        if (snap.running) {
          chainWasRunningRef.current = true
        } else if (chainWasRunningRef.current) {
          chainWasRunningRef.current = false
          if (chainPollRef.current !== null) {
            window.clearInterval(chainPollRef.current)
            chainPollRef.current = null
          }
          handleChainComplete()
        }
      })
      .catch(() => {})
  }, [handleChainComplete])

  const startChainPolling = useCallback(() => {
    chainWasRunningRef.current = true
    pollChainStatus()
    if (chainPollRef.current === null) {
      chainPollRef.current = window.setInterval(pollChainStatus, 2000)
    }
  }, [pollChainStatus])

  const stopChain = useCallback(() => {
    fetch(`${BASE}/api/refresh/chain/stop`, { method: 'POST' })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain stop'))))
      .then((snap: ChainStatusSnapshot) => setChainStatus(snap))
      .catch(() => {})
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  // A chain started from another window/session should still surface here.
  useEffect(() => {
    fetch(`${BASE}/api/refresh/chain/status`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chain status'))))
      .then((snap: ChainStatusSnapshot) => {
        setChainStatus(snap)
        if (snap.running) startChainPolling()
      })
      .catch(() => {})
    return () => {
      if (chainPollRef.current !== null) window.clearInterval(chainPollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (failed || !status) return null

  const notFresh = status.steps.filter(s => s.state === 'stale' || s.state === 'blocked')
  const unknownSteps = status.steps.filter(s => s.state === 'unknown')
  const outOfDate = status.stale_count + status.blocked_count

  const groups = TRIGGER_ORDER
    .map(trig => ({ trig, rows: notFresh.filter(s => s.trigger === trig) }))
    .filter(g => g.rows.length > 0)

  const pl = status.publish_lag
  const showPublishLag = !!pl.published_at
    && ((pl.days_since !== null && pl.days_since >= 7) || pl.lb_status_changes_since > 0)

  return (
    <Card title={t('refresh.title')} subtitle={t('refresh.subtitle')} pad={14} style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700 }}>
          {outOfDate === 0 ? t('refresh.allUpToDate') : t('refresh.nOutOfDate', { count: outOfDate })}
        </div>

        {showPublishLag && (
          <div style={{
            padding: '9px 11px', borderRadius: 8,
            background: 'var(--lbb-warn-bg)', border: '1px solid var(--lbb-warn-fg)',
            fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg)',
          }}>
            {t('refresh.publishLag', {
              days: pl.days_since ?? 0,
              changes: pl.lb_status_changes_since,
            })}
          </div>
        )}

        {chainStatus?.running && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            padding: '8px 11px', borderRadius: 8,
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
          }}>
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg)', flex: '1 1 auto', minWidth: 0 }}>
              {t('refresh.chain.running', {
                step: t(`refresh.steps.${chainStatus.current}`, chainStatus.current || '—'),
                done: chainStatus.done, total: chainStatus.total,
              })}
              {chainStatus.sub_progress?.total ? (
                <span style={{ color: 'var(--lbb-fg3)' }}>
                  {' '}({chainStatus.sub_progress.done ?? 0}/{chainStatus.sub_progress.total})
                </span>
              ) : null}
            </span>
            <Button
              variant="ghost" size="sm" disabled={chainStatus.stop_requested}
              onClick={stopChain}
            >
              {chainStatus.stop_requested ? t('refresh.chain.stopping') : t('refresh.stop')}
            </Button>
          </div>
        )}

        {!chainStatus?.running && chainOutcome && (
          <Pill tone="mute" soft>{chainOutcome}</Pill>
        )}

        {groups.map(g => (
          <div key={g.trig}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              margin: '6px 0 2px',
            }}>
              <div style={{
                flex: 1, fontSize: 'var(--lbb-fs-10-5)', letterSpacing: 0.1, textTransform: 'uppercase',
                color: 'var(--lbb-fg3)', fontWeight: 600,
              }}>
                {t(`refresh.triggers.${g.trig}`)}
              </div>
              <ChainButton
                label={t('refresh.chain.runTrigger', { trigger: g.trig })}
                scope={{ trigger: g.trig }}
                scopeLabel={t(`refresh.triggers.${g.trig}`)}
                onStarted={startChainPolling}
              />
            </div>
            {g.rows.map(step => (
              <StepRow key={step.step_id} step={step} onRefresh={fetchStatus} onChainStarted={startChainPolling} />
            ))}
          </div>
        ))}

        {unknownSteps.length > 0 && (
          <div
            title={unknownSteps.map(s => t(`refresh.steps.${s.step_id}`, s.label)).join(', ')}
            style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 4 }}
          >
            {t('refresh.unknownFootnote', { count: unknownSteps.length })}
          </div>
        )}
      </div>
    </Card>
  )
}
