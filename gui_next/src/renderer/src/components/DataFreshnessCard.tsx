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

function HowToRun({ step, onRefresh }: { step: RefreshStep; onRefresh: () => void }): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()

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

function StepRow({ step, onRefresh }: { step: RefreshStep; onRefresh: () => void }): React.JSX.Element {
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
      <HowToRun step={step} onRefresh={onRefresh} />
    </div>
  )
}

export function DataFreshnessCard(): React.JSX.Element | null {
  const { t } = useTranslation()
  const [status, setStatus] = useState<RefreshStatus | null>(null)
  const [failed, setFailed] = useState(false)

  const fetchStatus = useCallback(() => {
    fetch(`${BASE}/api/refresh/status`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('refresh status'))))
      .then((data: RefreshStatus) => setStatus(data))
      .catch(() => setFailed(true))
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

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

        {groups.map(g => (
          <div key={g.trig}>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', letterSpacing: 0.1, textTransform: 'uppercase',
              color: 'var(--lbb-fg3)', fontWeight: 600, margin: '6px 0 2px',
            }}>
              {t(`refresh.triggers.${g.trig}`)}
            </div>
            {g.rows.map(step => <StepRow key={step.step_id} step={step} onRefresh={fetchStatus} />)}
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
