// First-run wizard — spec: instructions/FABLE_ONBOARDING_SYNC.md §5.
// Modal shown over ScreenHome the first time entries_count == 0. Four steps:
// 1) install the master DB, 2) install cached site pages, 3) point at a
// collection (navigation only), 4) done — fires the derived-data recompute.
// Controlled component: ScreenHome owns open/step state + the once-per-launch
// / session-dismiss logic and passes the latest onboarding status down.

import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button } from './primitives'
import { Icon } from './Icon'

const BASE = window.api.flaskBase

// ── Types ────────────────────────────────────────────────────────────────────

export interface OnboardingStatus {
  entries_count: number
  master_version: string | null
  sitedata_core_present: boolean
  sitedata_files_count: number
  mounts_configured: boolean
  collection_count: number
  complete: boolean
}

interface MasterCheckResp {
  available?: boolean
  message?: string
  tag?: string
  remote_version?: string
  remote_published_at?: string
  local_version?: string
  asset_name?: string
  asset_size?: number
  error?: string
}

interface SitedataPart { asset_name: string; asset_size: number }
interface SitedataCheckResp {
  available?: boolean
  message?: string
  tag?: string
  published_at?: string
  parts?: Record<string, SitedataPart>
  error?: string
}

interface SSEInstallEvent {
  type: 'progress' | 'done' | 'error'
  label?: string
  pct?: number | null
  error?: string
  message?: string
}

interface RecomputeEvent {
  event: 'start' | 'done' | 'skipped' | 'error' | 'chain_done'
  step?: string
  message?: string
}

type StepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error'

const RECOMPUTE_STEPS = ['parse_lineage', 'attribute_tapers', 'compute_show_picks'] as const

// ── SSE helper ───────────────────────────────────────────────────────────────

async function readSSE<T>(resp: Response, onEvent: (ev: T) => void): Promise<void> {
  if (!resp.body) return
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let nl: number
    while ((nl = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, nl)
      buf = buf.slice(nl + 2)
      if (!frame.startsWith('data: ')) continue
      try {
        onEvent(JSON.parse(frame.slice(6)) as T)
      } catch { /* ignore malformed frame */ }
    }
  }
}

function fmtBytes(n: number | undefined): string {
  if (!n) return '—'
  const mb = n / (1 << 20)
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

// ── ProgressBar ──────────────────────────────────────────────────────────────

function ProgressBar({ label, pct }: { label: string; pct: number | null }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ height: 6, borderRadius: 3, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 3, background: 'var(--lbb-accent-mid)',
          width: pct != null ? `${pct}%` : '35%',
          transition: 'width 200ms ease',
        }} />
      </div>
      <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{label}</span>
    </div>
  )
}

// ── StepDots ─────────────────────────────────────────────────────────────────

function StepDots({ step }: { step: number }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {[1, 2, 3, 4].map((n) => (
        <span key={n} style={{
          width: n === step ? 18 : 6, height: 6, borderRadius: 3,
          background: n <= step ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
          transition: 'width 150ms ease, background 150ms ease',
        }} />
      ))}
    </div>
  )
}

// ── Step 1: Get the dataset ───────────────────────────────────────────────────

function Step1Master({
  status, installed, onInstalled,
}: {
  status: OnboardingStatus | null
  installed: boolean
  onInstalled: () => void
}) {
  const { t } = useTranslation()
  const [check, setCheck] = useState<MasterCheckResp | null>(null)
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [progress, setProgress] = useState<{ label: string; pct: number | null } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runCheck = useCallback(async () => {
    setChecking(true)
    setError(null)
    try {
      const r = await fetch(`${BASE}/api/master/github_check`)
      const d = await r.json() as MasterCheckResp
      setCheck(d)
      if (d.error) setError(d.message ?? d.error)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => { void runCheck() }, [runCheck])

  const runInstall = useCallback(async () => {
    setInstalling(true)
    setError(null)
    setProgress({ label: t('onboarding.step1.installing'), pct: null })
    try {
      const r = await fetch(`${BASE}/api/master/github_install`, { method: 'POST' })
      if (!r.ok || !r.body) {
        const errBody = await r.json().catch(() => ({})) as { error?: string; message?: string }
        setError(errBody.message ?? errBody.error ?? r.statusText)
        return
      }
      await readSSE<SSEInstallEvent>(r, (ev) => {
        if (ev.type === 'progress') setProgress({ label: ev.label ?? '', pct: ev.pct ?? null })
        else if (ev.type === 'done') { setProgress(null); onInstalled() }
        else if (ev.type === 'error') setError(ev.message ?? ev.error ?? 'error')
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setInstalling(false)
    }
  }, [onInstalled, t])

  const already = installed || (status?.entries_count ?? 0) > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <p style={{ margin: 0, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg2)', lineHeight: 1.6 }}>
        {t('onboarding.step1.desc')}
      </p>

      {already && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
          borderRadius: 8, background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)',
        }}>
          <Icon name="check" size={14} style={{ color: 'var(--lbb-ok-fg)' }} />
          <span style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-ok-fg)' }}>
            {t('onboarding.step1.installed')}
          </span>
        </div>
      )}

      {!already && checking && (
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('onboarding.step1.checking')}</span>
      )}

      {!already && !checking && check && !check.error && check.remote_version && (
        <div style={{
          display: 'grid', gridTemplateColumns: '110px 1fr', gap: '6px 12px',
          fontSize: 'var(--lbb-fs-12-5)', padding: '12px 14px',
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)', borderRadius: 8,
        }}>
          <span style={{ color: 'var(--lbb-fg3)' }}>{t('onboarding.step1.version')}</span>
          <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600 }}>{check.remote_version}</span>
          <span style={{ color: 'var(--lbb-fg3)' }}>{t('onboarding.step1.published')}</span>
          <span style={{ fontFamily: 'var(--lbb-mono)' }}>{fmtDate(check.remote_published_at)}</span>
          <span style={{ color: 'var(--lbb-fg3)' }}>{t('onboarding.step1.size')}</span>
          <span style={{ fontFamily: 'var(--lbb-mono)' }}>{fmtBytes(check.asset_size)}</span>
        </div>
      )}

      {!already && !checking && check?.error && (
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>
          {check.message ?? check.error}
        </span>
      )}

      {!already && !checking && check && !check.error && !check.remote_version && (
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
          {check.message ?? t('onboarding.step1.noRelease')}
        </span>
      )}

      {progress && <ProgressBar label={progress.label} pct={progress.pct} />}
      {error && <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>{error}</span>}

      {!already && (
        <Button
          variant="primary" icon="download" disabled={installing || checking}
          onClick={() => void runInstall()}
        >
          {installing ? t('onboarding.step1.installing') : t('onboarding.step1.install')}
        </Button>
      )}
    </div>
  )
}

// ── Step 2: Cached site pages ─────────────────────────────────────────────────

function Step2Sitedata({ onInstalled }: { onInstalled: (parts: string[]) => void }) {
  const { t } = useTranslation()
  const [check, setCheck] = useState<SitedataCheckResp | null>(null)
  const [checking, setChecking] = useState(false)
  const [coreChecked, setCoreChecked] = useState(true)
  const [filesChecked, setFilesChecked] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [progress, setProgress] = useState<{ label: string; pct: number | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [installedParts, setInstalledParts] = useState<string[]>([])

  useEffect(() => {
    setChecking(true)
    fetch(`${BASE}/api/sitedata/github_check`)
      .then((r) => r.json())
      .then((d: SitedataCheckResp) => setCheck(d))
      .catch((e: Error) => setError(e.message))
      .finally(() => setChecking(false))
  }, [])

  const runInstall = useCallback(async () => {
    const parts = [...(coreChecked ? ['core'] : []), ...(filesChecked ? ['files'] : [])]
    if (parts.length === 0) return
    setInstalling(true)
    setError(null)
    setProgress({ label: t('onboarding.step2.installing'), pct: null })
    try {
      const r = await fetch(`${BASE}/api/sitedata/github_install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parts }),
      })
      if (!r.ok || !r.body) {
        const errBody = await r.json().catch(() => ({})) as { error?: string; message?: string }
        setError(errBody.message ?? errBody.error ?? r.statusText)
        return
      }
      await readSSE<SSEInstallEvent>(r, (ev) => {
        if (ev.type === 'progress') setProgress({ label: ev.label ?? '', pct: ev.pct ?? null })
        else if (ev.type === 'done') { setProgress(null); setInstalledParts(parts); onInstalled(parts) }
        else if (ev.type === 'error') setError(ev.message ?? ev.error ?? 'error')
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setInstalling(false)
    }
  }, [coreChecked, filesChecked, onInstalled, t])

  const filesSize = check?.parts?.files?.asset_size

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <p style={{ margin: 0, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg2)', lineHeight: 1.6 }}>
        {t('onboarding.step2.desc')}
      </p>

      {checking && <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('onboarding.step2.checking')}</span>}
      {!checking && check?.error && (
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>{check.message ?? check.error}</span>
      )}
      {!checking && check && !check.available && !check.error && (
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
          {check.message ?? t('onboarding.step2.noRelease')}
        </span>
      )}

      {!checking && check?.available && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--lbb-fs-12-5)' }}>
            <input type="checkbox" checked={coreChecked} onChange={(e) => setCoreChecked(e.target.checked)} />
            <span style={{ flex: 1 }}>
              <strong style={{ color: 'var(--lbb-fg)' }}>{t('onboarding.step2.core')}</strong>
              {' — '}
              <span style={{ color: 'var(--lbb-fg3)' }}>{t('onboarding.step2.coreDesc')}</span>
            </span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--lbb-fs-12-5)' }}>
            <input
              type="checkbox" checked={filesChecked}
              disabled={!check.parts?.files}
              onChange={(e) => setFilesChecked(e.target.checked)}
            />
            <span style={{ flex: 1 }}>
              <strong style={{ color: 'var(--lbb-fg)' }}>{t('onboarding.step2.files')}</strong>
              {' — '}
              <span style={{ color: 'var(--lbb-fg3)' }}>
                {t('onboarding.step2.filesDesc', { size: fmtBytes(filesSize) })}
              </span>
            </span>
          </label>
        </div>
      )}

      {progress && <ProgressBar label={progress.label} pct={progress.pct} />}
      {error && <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>{error}</span>}
      {installedParts.length > 0 && !installing && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
          borderRadius: 8, background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)',
        }}>
          <Icon name="check" size={14} style={{ color: 'var(--lbb-ok-fg)' }} />
          <span style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-ok-fg)' }}>
            {t('onboarding.step2.installed')}
          </span>
        </div>
      )}

      {check?.available && (
        <Button
          variant="primary" icon="download"
          disabled={installing || checking || (!coreChecked && !filesChecked)}
          onClick={() => void runInstall()}
        >
          {installing ? t('onboarding.step2.installing') : t('onboarding.step2.install')}
        </Button>
      )}
    </div>
  )
}

// ── Step 3: Your collection ───────────────────────────────────────────────────

function Step3Collection({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { t } = useTranslation()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ margin: 0, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg2)', lineHeight: 1.6 }}>
        {t('onboarding.step3.desc')}
      </p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Button variant="secondary" icon="mounts" onClick={() => onNavigate('/mounts')}>
          {t('onboarding.step3.addMount')}
        </Button>
        <Button variant="secondary" icon="pipeline" onClick={() => onNavigate('/pipeline')}>
          {t('onboarding.step3.goPipeline')}
        </Button>
      </div>
    </div>
  )
}

// ── Step 4: Done ───────────────────────────────────────────────────────────────

function Step4Done({
  status, masterInstalled, sitedataParts,
}: {
  status: OnboardingStatus | null
  masterInstalled: boolean
  sitedataParts: string[]
}) {
  const { t } = useTranslation()
  const [steps, setSteps] = useState<Record<string, StepStatus>>(
    () => Object.fromEntries(RECOMPUTE_STEPS.map((s) => [s, 'pending'])) as Record<string, StepStatus>,
  )
  const [chainDone, setChainDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState(false)

  useEffect(() => {
    if (started) return
    setStarted(true)
    void (async () => {
      try {
        const r = await fetch(`${BASE}/api/derived/recompute`, { method: 'POST' })
        if (!r.ok || !r.body) {
          const errBody = await r.json().catch(() => ({})) as { message?: string; error?: string }
          setError(errBody.message ?? errBody.error ?? r.statusText)
          return
        }
        await readSSE<RecomputeEvent>(r, (ev) => {
          if (ev.event === 'chain_done') { setChainDone(true); return }
          if (!ev.step) return
          if (ev.event === 'start') setSteps((s) => ({ ...s, [ev.step as string]: 'running' }))
          else if (ev.event === 'done') setSteps((s) => ({ ...s, [ev.step as string]: 'done' }))
          else if (ev.event === 'skipped') setSteps((s) => ({ ...s, [ev.step as string]: 'skipped' }))
          else if (ev.event === 'error') { setSteps((s) => ({ ...s, [ev.step as string]: 'error' })); setError(ev.message ?? null) }
        })
      } catch (e) {
        setError((e as Error).message)
      }
    })()
  }, [started])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ margin: 0, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg2)', lineHeight: 1.6 }}>
        {t('onboarding.step4.desc')}
      </p>

      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6, padding: '12px 14px',
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)', borderRadius: 8,
        fontSize: 'var(--lbb-fs-12-5)',
      }}>
        <SummaryRow label={t('onboarding.step4.summaryMaster')} ok={masterInstalled || (status?.entries_count ?? 0) > 0} />
        <SummaryRow label={t('onboarding.step4.summarySitedataCore')} ok={sitedataParts.includes('core') || !!status?.sitedata_core_present} />
        <SummaryRow label={t('onboarding.step4.summaryMounts')} ok={!!status?.mounts_configured} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
          {chainDone ? t('onboarding.step4.recomputeDone') : t('onboarding.step4.recomputing')}
        </span>
        {RECOMPUTE_STEPS.map((s) => (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-11-5)' }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background:
                steps[s] === 'done' ? 'var(--lbb-ok-bar)'
                  : steps[s] === 'error' ? 'var(--lbb-bad-fg)'
                    : steps[s] === 'running' ? 'var(--lbb-accent-mid)'
                      : 'var(--lbb-border2)',
            }} />
            <span style={{ color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>{s}</span>
            <span style={{ color: 'var(--lbb-fg3)' }}>{steps[s]}</span>
          </div>
        ))}
        {error && <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>{error}</span>}
      </div>
    </div>
  )
}

function SummaryRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Icon name={ok ? 'check' : 'x'} size={13} style={{ color: ok ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)' }} />
      <span style={{ color: 'var(--lbb-fg2)' }}>{label}</span>
    </div>
  )
}

// ── OnboardingWizard ─────────────────────────────────────────────────────────

export interface OnboardingWizardProps {
  open: boolean
  initialStep?: number
  status: OnboardingStatus | null
  onClose: () => void
  onStatusRefresh: () => void
}

export function OnboardingWizard({
  open, initialStep, status, onClose, onStatusRefresh,
}: OnboardingWizardProps): React.JSX.Element | null {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [step, setStep] = useState(initialStep ?? 1)
  const [masterInstalled, setMasterInstalled] = useState(false)
  const [sitedataParts, setSitedataParts] = useState<string[]>([])

  useEffect(() => {
    if (open) setStep(initialStep ?? 1)
  }, [open, initialStep])

  const handleMasterInstalled = useCallback(() => {
    setMasterInstalled(true)
    onStatusRefresh()
  }, [onStatusRefresh])

  const handleSitedataInstalled = useCallback((parts: string[]) => {
    setSitedataParts((prev) => Array.from(new Set([...prev, ...parts])))
    onStatusRefresh()
  }, [onStatusRefresh])

  const handleNavigate = useCallback((path: string) => {
    navigate(path)
  }, [navigate])

  if (!open) return null

  const canProceedStep1 = masterInstalled || (status?.entries_count ?? 0) > 0
  const titles = [
    t('onboarding.step1.title'),
    t('onboarding.step2.title'),
    t('onboarding.step3.title'),
    t('onboarding.step4.title'),
  ]

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 18,
      }}
    >
      <div style={{
        width: 560, maxWidth: '100%', maxHeight: '88vh',
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
        borderRadius: 12, boxShadow: '0 24px 70px rgba(0,0,0,0.5)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 22px 14px', borderBottom: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', gap: 10, flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 'var(--lbb-fs-11)', letterSpacing: 0.1, textTransform: 'uppercase', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
                {t('onboarding.stepLabel', { n: step })}
              </div>
              <div style={{ fontSize: 'var(--lbb-fs-18)', fontWeight: 700, marginTop: 2 }}>
                {titles[step - 1]}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              title={t('common.close')}
              style={{
                width: 30, height: 30, borderRadius: 7, cursor: 'pointer', flexShrink: 0,
                background: 'transparent', border: '1px solid var(--lbb-border)', color: 'var(--lbb-fg2)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Icon name="x" size={14} />
            </button>
          </div>
          <StepDots step={step} />
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: '20px 22px' }}>
          {step === 1 && <Step1Master status={status} installed={masterInstalled} onInstalled={handleMasterInstalled} />}
          {step === 2 && <Step2Sitedata onInstalled={handleSitedataInstalled} />}
          {step === 3 && <Step3Collection onNavigate={handleNavigate} />}
          {step === 4 && <Step4Done status={status} masterInstalled={masterInstalled} sitedataParts={sitedataParts} />}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 22px', borderTop: '1px solid var(--lbb-border)',
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <Button variant="ghost" onClick={onClose}>{t('onboarding.skip')}</Button>
          <div style={{ flex: 1 }} />
          {step > 1 && (
            <Button variant="secondary" onClick={() => setStep((s) => s - 1)}>{t('onboarding.back')}</Button>
          )}
          {step < 4 && (
            <Button
              variant="primary"
              disabled={step === 1 && !canProceedStep1}
              onClick={() => setStep((s) => s + 1)}
            >
              {t('onboarding.next')}
            </Button>
          )}
          {step === 4 && (
            <Button variant="primary" onClick={onClose}>{t('onboarding.finish')}</Button>
          )}
        </div>
      </div>
    </div>
  )
}
