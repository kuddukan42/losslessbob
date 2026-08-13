// "Data freshness" card — Pipeline Refresh Phase 1, spec §2.4
// (instructions/PIPELINE_REFRESH_PHASE1.md). Reads GET /api/refresh/status
// and summarises stale/blocked pipeline steps on ScreenHome.
//
// Phase 1 is read-only (spec §6: "nothing new becomes executable"). Every
// how_to_run is rendered as copyable text; the only exception is a small,
// conservative prefix map from stable existing API namespaces to the screen
// that already owns them (e.g. /api/pipeline/* -> the Pipeline screen) — those
// render as a "Go to…" navigation button, never a route-firing button. When a
// prefix isn't recognised the value falls back to copyable text, per the task
// spec's "prefer copyable text everywhere if navigation targets aren't
// obvious" guidance.

import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Card, Pill, Button } from './primitives'
import type { StatusTone } from './primitives'

const BASE = window.api.flaskBase

// ── Types (mirrors backend/refresh.py's GET /api/refresh/status shape) ──────

type Trigger = 'T1' | 'T2' | 'T3' | 'T4'
type StepState = 'fresh' | 'stale' | 'blocked' | 'unknown'

interface RefreshStep {
  step_id: string
  label: string
  trigger: Trigger
  kind: 'wholesale' | 'incremental' | 'manual'
  state: StepState
  reason: string
  last_run: string | null
  age_days: number | null
  backlog: number | null
  blocked_by: string | null
  upstream: string[]
  how_to_run: string
  cost: 'fast' | 'slow' | 'very_slow'
  human_gate: boolean
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

function HowToRun({ step }: { step: RefreshStep }): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
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

function StepRow({ step }: { step: RefreshStep }): React.JSX.Element {
  const { t } = useTranslation()
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '7px 4px',
      borderBottom: '1px solid var(--lbb-border)', flexWrap: 'wrap',
    }}>
      <span style={{ flex: '1 1 160px', fontSize: 'var(--lbb-fs-12-5)', minWidth: 0 }}>
        {t(`refresh.steps.${step.step_id}`, step.label)}
      </span>
      <Pill tone={STATE_TONE[step.state]} soft title={step.reason}>{t(`refresh.state.${step.state}`)}</Pill>
      <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', width: 34, textAlign: 'right' }}>
        {fmtAge(step.age_days)}
      </span>
      {step.backlog !== null && (
        <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('refresh.backlog', { count: step.backlog })}
        </span>
      )}
      <HowToRun step={step} />
    </div>
  )
}

export function DataFreshnessCard(): React.JSX.Element | null {
  const { t } = useTranslation()
  const [status, setStatus] = useState<RefreshStatus | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    fetch(`${BASE}/api/refresh/status`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((data: RefreshStatus) => setStatus(data))
      .catch(() => setFailed(true))
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

        {groups.map(g => (
          <div key={g.trig}>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', letterSpacing: 0.1, textTransform: 'uppercase',
              color: 'var(--lbb-fg3)', fontWeight: 600, margin: '6px 0 2px',
            }}>
              {t(`refresh.triggers.${g.trig}`)}
            </div>
            {g.rows.map(step => <StepRow key={step.step_id} step={step} />)}
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
