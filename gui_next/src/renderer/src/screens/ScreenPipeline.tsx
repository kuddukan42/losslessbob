import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Icon } from '../components/Icon'
import { Button, IconButton, Input, Pill, Banner, Chip } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import { useFolderQueueStore } from '../lib/folderQueueStore'
import { CheckResult, ReconcileResult, ReconcileProposal, SiteProposal } from '../lib/lbdirStore'
import { FileRow } from '../lib/verifyStore'
import { useConfirm } from '../components/pipeline/ConfirmDialog'
import { VerifyDetail } from '../components/pipeline/VerifyDetail'
import { LookupDetail, categoryPill } from '../components/pipeline/LookupDetail'
import { LbdirDetail } from '../components/pipeline/LbdirDetail'
import { CollectDetail, Mount } from '../components/pipeline/CollectDetail'
import { LookupSummary, LookupDetail as LookupDetailRow } from '../lib/lookupStore'
import {
  StageTracker, QueueRow, StageStepper, StatusTag,
  DEFAULT_STAGES,
  type Bucket, type StepData, type FolderRow,
} from '../components/pipeline/PipelineParts'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type StepStatus = 'ok' | 'warn' | 'bad' | 'mute'

interface LbdirCheckSummary {
  status: string
  total: number
  pass: number
  missing: number
  mismatch: number
}

interface StepResult {
  status: StepStatus
  label: string
  lb_number?: number | null
  lb_numbers?: number[] | null
  proposed?: string | null
  alias_resolved_from?: number[] | null
  summary?: LookupSummary | null
  detail?: LookupDetailRow[] | null
  check?: LbdirCheckSummary | null
  // verify step fields
  total?: number | null
  pass?: number | null
  missing?: number | null
  mismatch?: number | null
  extra?: number | null
  no_checksums?: boolean | null
  shntool_missing?: boolean | null
  files?: FileRow[]
  // file step fields
  dest?: string | null
  dest_parent?: string | null
  mount_label?: string | null
  year?: number | null
  error?: string | null
  error_code?: string | null
  mounts?: Mount[] | null
  recommended_mount?: number | null
  routed_year?: number | null
  collection_count?: number | null
  lb_status?: string | null
  owned?: boolean | null
  existing_disk_path?: string | null
  lbdir_verified_at?: string | null
}

interface FileProgress {
  stage: string // scanning | copying | moving | verifying | removing
  files_done: number
  files_total: number
  bytes_done: number
  bytes_total: number
  current_file: string | null
}

interface PipelineRow {
  id: string                          // folderPath used as stable key
  folderName: string
  folderPath: string
  selected: boolean
  bucket: Bucket
  steps: {
    verify: StepResult
    lookup: StepResult
    lbdir:  StepResult
    rename: StepResult
    file:   StepResult
  }
  errors: { step: string; message: string }[]
  running: boolean
  shelved: boolean
  fileProgress?: FileProgress | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const MUTE: StepResult = { status: 'mute', label: '—' }

function pctOf(done: number, total: number): number {
  if (total <= 0) return 0
  return Math.min(100, Math.round((done / total) * 100))
}

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`
  return `${(n / 1073741824).toFixed(2)} GB`
}

/** Inline progress bar shown while a Collect step's copy/move is running. */
function FileProgressBar({ progress, compact = false }: { progress: FileProgress; compact?: boolean }): React.JSX.Element {
  const { t } = useTranslation()
  const percent = pctOf(progress.bytes_done, progress.bytes_total)
  const indeterminate = progress.bytes_total === 0
  const stageLabel = t(`pipeline.file.progress.${progress.stage}`, t('pipeline.file.progress.copying'))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: compact ? 100 : 160 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
        <span>
          {stageLabel}
          {progress.files_total > 0 && ` · ${progress.files_done}/${progress.files_total}`}
        </span>
        {!indeterminate && (
          <span>{compact ? `${percent}%` : `${humanBytes(progress.bytes_done)} / ${humanBytes(progress.bytes_total)} · ${percent}%`}</span>
        )}
      </div>
      <div style={{ height: 6, borderRadius: 3, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 3, background: 'var(--lbb-accent-mid)',
          width: indeterminate ? '40%' : `${percent}%`,
          transition: indeterminate ? 'none' : 'width 0.3s ease',
          animation: indeterminate ? 'lbb-indeterminate 1.4s ease-in-out infinite' : 'none',
        }} />
      </div>
      {!compact && progress.current_file && (
        <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {progress.current_file}
        </div>
      )}
    </div>
  )
}

// Module-level cache: persists step results across tab navigation within a session.
// Keyed by folder path; cleared only on explicit queue clear.
type CachedRow = { steps: PipelineRow['steps']; bucket: Bucket; errors: PipelineRow['errors'] }
const _pipelineCache = new Map<string, CachedRow>()

const BANNER_BUCKETS: { key: Exclude<Bucket, 'all'>; tone: string }[] = [
  { key: 'needs',   tone: 'bad'  },
  { key: 'ready',   tone: 'warn' },
  { key: 'running', tone: 'info' },
  { key: 'shelf',   tone: 'info' },
  { key: 'done',    tone: 'ok'   },
]

function emptyRow(folderPath: string): PipelineRow {
  const name = folderPath.split(/[/\\]/).pop() ?? folderPath
  return {
    id: folderPath,
    folderName: name,
    folderPath,
    selected: false,
    bucket: 'needs',
    steps: { verify: MUTE, lookup: MUTE, lbdir: MUTE, rename: MUTE, file: MUTE },
    errors: [],
    running: false,
    shelved: false,
  }
}

function normalizeFileStep(raw: unknown): StepResult {
  if (!raw || typeof raw !== 'object') return MUTE
  const r = raw as Record<string, unknown>
  const rawStatus = r.status as string
  const status: StepStatus =
    rawStatus === 'ready'   ? 'warn' :
    rawStatus === 'blocked' ? 'bad'  :
    (rawStatus as StepStatus) ?? 'mute'
  return {
    status,
    label:            (r.label            as string)  ?? '—',
    dest:             (r.dest             as string)  ?? null,
    dest_parent:      (r.dest_parent      as string)  ?? null,
    mount_label:      (r.mount_label      as string)  ?? null,
    year:             (r.year             as number)  ?? null,
    error:            (r.error            as string)  ?? null,
    error_code:       (r.error_code       as string)  ?? null,
    mounts:           (r.mounts           as Mount[]) ?? null,
    recommended_mount: (r.recommended_mount as number) ?? null,
    routed_year:      (r.routed_year      as number)  ?? null,
    collection_count: (r.collection_count as number)  ?? null,
    lb_status:        (r.lb_status        as string)  ?? null,
    owned:            (r.owned            as boolean) ?? null,
    existing_disk_path: (r.existing_disk_path as string) ?? null,
    lbdir_verified_at: (r.lbdir_verified_at as string) ?? null,
  }
}

function serverRowToPipeline(sr: Record<string, unknown>): Partial<PipelineRow> {
  const sev = sr.severity as string
  const file = normalizeFileStep(sr.file)
  let bucket: Bucket =
    sev === 'attn'  ? 'needs' :
    sev === 'ready' ? 'ready' :
    sev === 'done'  ? 'done'  : 'needs'
  // Backend reports "done" once verify/lookup/rename/lbdir all pass, even if
  // the folder hasn't been filed into the collection yet — reclassify those
  // as "shelf" so the status column doesn't claim "In collection" early.
  if (bucket === 'done' && file.status === 'warn') bucket = 'shelf'
  return {
    bucket,
    steps: {
      verify: (sr.verify as StepResult) ?? MUTE,
      lookup: (sr.lookup as StepResult) ?? MUTE,
      lbdir:  (sr.lbdir  as StepResult) ?? MUTE,
      rename: (sr.rename as StepResult) ?? MUTE,
      file,
    },
    errors: (sr.errors as PipelineRow['errors']) ?? [],
    running: false,
  }
}

const STATUS_TO_STATE: Record<StepStatus, StepData['state']> = {
  ok: 'pass', warn: 'action', bad: 'blocked', mute: 'mute',
}

function toFolderRow(r: PipelineRow): FolderRow {
  const rawSteps: Record<string, StepData> = {}
  for (const key of ['verify', 'lookup', 'lbdir', 'rename', 'file'] as const) {
    const s = r.steps[key]
    rawSteps[key] = { state: STATUS_TO_STATE[s.status], label: s.label }
  }
  if (r.running) {
    for (const key of ['verify', 'lookup', 'lbdir', 'rename', 'file']) {
      if (rawSteps[key].state === 'mute') {
        rawSteps[key] = { state: 'running' }
        break
      }
    }
  }
  return {
    folder: r.folderPath,
    folderName: r.folderName,
    steps: rawSteps,
    bucket: r.running ? 'running' : r.bucket,
    lb: r.steps.lookup.lb_number
      ? `LB-${String(r.steps.lookup.lb_number).padStart(5, '0')}`
      : null,
  }
}

function firstActiveStage(r: PipelineRow): string {
  for (const key of ['verify', 'lookup', 'lbdir', 'rename', 'file'] as const) {
    if (r.steps[key].status !== 'ok' && r.steps[key].status !== 'mute') return key
    if (r.steps[key].status === 'mute') return key
  }
  return 'verify'
}

type StatusInfo = { state: StepData['state']; label: string; reason: string }

function deriveFolderStatus(r: PipelineRow, t: TFunction): StatusInfo {
  if (r.running) return { state: 'running', label: t('pipeline.stepStates.running'), reason: t('pipeline.status.inProgress') }
  if (r.shelved) return { state: 'mute', label: t('pipeline.status.shelved'), reason: t('pipeline.status.deferredReason') }
  if (r.bucket === 'done') return {
    state: 'pass', label: t('pipeline.status.inCollection'),
    reason: r.steps.file.mount_label ? t('pipeline.status.filedTo', { mount: r.steps.file.mount_label }) : t('pipeline.status.filedTagged'),
  }
  if (r.bucket === 'shelf') return {
    state: 'action', label: t('pipeline.status.readyToFile'),
    reason: t('pipeline.status.archiveCleanReason'),
  }
  if (r.bucket === 'ready') return {
    state: 'action', label: t('pipeline.status.readyToApply'),
    reason: t('pipeline.status.confidentReason'),
  }
  for (const key of ['verify', 'lookup', 'lbdir', 'rename', 'file'] as const) {
    const s = r.steps[key]
    if (s.status === 'bad')  return { state: 'blocked', label: t('pipeline.stepStates.blocked'), reason: s.label }
    if (s.status === 'warn') return { state: 'action',  label: t('pipeline.buckets.needs'),      reason: s.label }
    if (s.status === 'mute') return { state: 'mute',    label: t('pipeline.stepStates.mute'),    reason: '' }
  }
  return { state: 'mute', label: t('pipeline.stepStates.mute'), reason: '' }
}

// ── Virtualizer item type ─────────────────────────────────────────────────────

type VItem =
  | { type: 'group'; label: string; count: number; bucket: Bucket }
  | { type: 'row';   row: PipelineRow }

// ── LBDIR state labels ────────────────────────────────────────────────────────

const STATE_LABEL: Record<string, { tone: 'ok'|'bad'|'warn'|'mute'|'info'; labelKey: string; fallback?: string }> = {
  pass:            { tone: 'ok',   labelKey: 'pipeline.lbdir.status.pass' },
  fail:            { tone: 'bad',  labelKey: 'pipeline.lbdir.status.fail' },
  missing_files:   { tone: 'warn', labelKey: 'pipeline.lbdir.status.missingFiles' },
  extra_files:     { tone: 'warn', labelKey: 'pipeline.lbdir.status.extraFiles' },
  no_lbdir:        { tone: 'warn', labelKey: 'pipeline.lbdir.status.noLbdir' },
  no_lb:           { tone: 'mute', labelKey: 'pipeline.lbdir.status.noLb' },
  shntool_missing: { tone: 'warn', labelKey: 'pipeline.lbdir.status.noShntool' },
}

// ── LbdirStageContent ─────────────────────────────────────────────────────────

function LbdirStageContent({ row, onRowRefresh }: {
  row: PipelineRow
  onRowRefresh: (id: string) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [checkResult, setCheckResult]   = useState<CheckResult | null>(null)
  const [reconResult, setReconResult]   = useState<ReconcileResult | null>(null)
  const [reconSel,    setReconSel]      = useState<Set<string>>(new Set())
  const [siteSel,     setSiteSel]       = useState<Set<string>>(new Set())
  const [busy,        setBusy]          = useState(false)
  const [toast,       setToast]         = useState<{ msg: string; ok: boolean } | null>(null)

  const post = useCallback(async (endpoint: string, body: object): Promise<unknown> => {
    const r = await fetch(`${BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  }, [])

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  useEffect(() => {
    if (row.steps.lbdir.status === 'mute') return
    setBusy(true)
    const lbHint = row.steps.lookup.lb_number ?? null
    fetch(`${BASE}/api/lbdir/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folders: [row.folderPath],
        ...(lbHint !== null ? { lb_number_hint: lbHint } : {}),
      }),
    })
      .then(r => r.json())
      .then((d: { results: CheckResult[] }) => { if (d.results?.[0]) setCheckResult(d.results[0]) })
      .catch(() => {})
      .finally(() => setBusy(false))
  }, [row.folderPath, row.steps.lbdir.status, row.steps.lookup.lb_number])

  const handleReconcile = useCallback(async () => {
    if (!checkResult) return
    setBusy(true)
    try {
      const lbHint = row.steps.lookup.lb_number ?? null
      const d = await post('/api/lbdir/reconcile', {
        folders: [row.folderPath],
        ...(lbHint !== null ? { lb_number_hint: lbHint } : {}),
      }) as { results: ReconcileResult[] }
      if (d.results?.[0]) {
        setReconResult(d.results[0])
        setReconSel(new Set(d.results[0].proposals.map((p: ReconcileProposal) => p.disk_rel)))
        setSiteSel(new Set((d.results[0].site_proposals ?? []).map((p: SiteProposal) => p.site_path)))
      }
    } catch { showToast(t('pipeline.lbdir.toast.reconcileFailed'), false) }
    finally { setBusy(false) }
  }, [checkResult, row.folderPath, row.steps.lookup.lb_number, post, t])

  const handleApply = useCallback(async () => {
    if (!reconResult) return
    const renames = reconResult.proposals
      .filter(p => reconSel.has(p.disk_rel))
      .map(p => ({ from: p.disk_rel, to: p.lbdir_rel }))
    const extras = reconResult.unmatched_disk
    const siteCopies = (reconResult.site_proposals ?? [])
      .filter((p: SiteProposal) => siteSel.has(p.site_path))
      .map((p: SiteProposal) => ({ site_path: p.site_path, lbdir_rel: p.lbdir_rel }))
    setBusy(true)
    try {
      if (renames.length || siteCopies.length)
        await post('/api/lbdir/apply_reconcile', { folder: row.folderPath, renames, site_copies: siteCopies })
      if (extras.length)
        await post('/api/lbdir/move_extras', { folder: row.folderPath, files: extras })
      showToast(t('pipeline.lbdir.toast.applied'), true)
      setReconResult(null)
      const d2 = await post('/api/lbdir/check', { folders: [row.folderPath] }) as { results: CheckResult[] }
      if (d2.results?.[0]) setCheckResult(d2.results[0])
      onRowRefresh(row.id)
    } catch { showToast(t('pipeline.lbdir.toast.applyFailed'), false) }
    finally { setBusy(false) }
  }, [reconResult, reconSel, siteSel, row.folderPath, row.id, post, onRowRefresh, t])

  const handleRetrieve = useCallback(async () => {
    setBusy(true)
    try {
      const lbHint = row.steps.lookup.lb_number ?? null
      await post('/api/lbdir/retrieve', {
        folders: [row.folderPath],
        ...(lbHint !== null ? { lb_number_hint: lbHint } : {}),
      })
      onRowRefresh(row.id)
    } catch { showToast(t('pipeline.lbdir.toast.retrieveFailed'), false) }
    finally { setBusy(false) }
  }, [row.folderPath, row.id, row.steps.lookup.lb_number, post, onRowRefresh, t])

  if (row.steps.lbdir.status === 'mute') {
    return (
      <Banner tone="info" icon="info" title={t('pipeline.lbdir.runsAfterTitle')}
        action={
          <Button size="sm" variant="secondary" icon="download" disabled={busy} onClick={handleRetrieve}>
            {t('pipeline.lbdir.retrieveNow')}
          </Button>
        }>
        {t('pipeline.lbdir.runsAfterBody')}
      </Banner>
    )
  }

  const cr = checkResult
  const sl = cr ? (STATE_LABEL[cr.status] ?? { tone: 'mute' as const, labelKey: '', fallback: cr.status }) : null
  const canReconcile = cr !== null && cr.lbdir_found && cr.status !== 'pass' && cr.status !== 'no_lb'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'relative' }}>
      {busy && !cr && (
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center', padding: 24 }}>
          {t('pipeline.lbdir.loading')}
        </div>
      )}

      {cr && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {cr.lb_number !== null && (
              <Pill tone="info" soft style={{ fontFamily: 'var(--lbb-mono)' }}>
                LB-{String(cr.lb_number).padStart(5, '0')}
              </Pill>
            )}
            {sl && <Pill tone={sl.tone} soft dot={cr.status !== 'pass'}>{sl.labelKey ? t(sl.labelKey as any) : sl.fallback}</Pill>}
            {cr.lbdir_path && (
              <Pill tone="mute" soft style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>
                {cr.lbdir_path.split('/').pop()}
              </Pill>
            )}
            {cr.lbdir_path && (
              <Button variant="ghost" size="sm" icon="reveal"
                onClick={() => window.api.openPath(cr.lbdir_path!)}>
                {t('pipeline.lbdir.openFile')}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => navigate('/lbdir')}>
              {t('pipeline.lbdir.fullScreen')}
            </Button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
            {[
              { l: t('pipeline.lbdir.stats.total'),    v: cr.total,    c: undefined },
              { l: t('pipeline.lbdir.stats.pass'),     v: cr.pass,     c: cr.pass     > 0 ? 'var(--lbb-ok-fg)'  : 'var(--lbb-fg3)' },
              { l: t('pipeline.lbdir.stats.missing'),  v: cr.missing,  c: cr.missing  > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
              { l: t('pipeline.lbdir.stats.mismatch'), v: cr.mismatch, c: cr.mismatch > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            ].map((st, i) => (
              <div key={i} style={{ padding: '6px 8px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{st.l}</div>
                <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: st.c ?? 'var(--lbb-fg)' }}>{st.v}</div>
              </div>
            ))}
          </div>

          {cr.status === 'no_lbdir' && (
            <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
              {t('pipeline.lbdir.noLbdirFound')}
            </div>
          )}

          <LbdirDetail
            checkResult={cr}
            reconResult={reconResult}
            reconSelected={reconSel}
            setReconSelected={setReconSel}
            siteSelected={siteSel}
            setSiteSelected={setSiteSel}
            busy={busy}
            canReconcile={canReconcile}
            onReconcile={handleReconcile}
            onApplyReconcile={handleApply}
            compact
          />

          {cr.status === 'pass' && (
            <Banner tone="ok" icon="check" title={t('pipeline.lbdir.archiveCleanTitle')}>
              {t('pipeline.lbdir.archiveCleanBody')}
            </Banner>
          )}
        </>
      )}

      {toast && (
        <div style={{
          position: 'fixed', bottom: 80, left: '50%', transform: 'translateX(-50%)',
          background: toast.ok ? 'var(--lbb-ok-bar)' : 'var(--lbb-err-bar)',
          color: '#fff', padding: '7px 16px', borderRadius: 6,
          fontSize: 'var(--lbb-fs-12)', fontWeight: 600, zIndex: 9999,
          boxShadow: '0 2px 8px rgba(0,0,0,.2)', pointerEvents: 'none',
          whiteSpace: 'nowrap',
        }}>{toast.msg}</div>
      )}
    </div>
  )
}

// ── Stage detail panels ───────────────────────────────────────────────────────

function VerifyStageContent({ step, row, onRun }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [generating, setGenerating] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const handleCopyReport = useCallback(() => {
    const lines = (step.files ?? []).map(f =>
      `${f.overall === 'pass' ? '✓' : '✗'} ${f.filename}\t[md5] ${f.md5_status}\t[ffp] ${f.ffp_status}`
    )
    navigator.clipboard.writeText(lines.join('\n')).catch(() => {})
  }, [step.files])

  const handleGenerate = useCallback(async () => {
    setGenerating(true)
    try {
      await fetch(`${BASE}/api/verify/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [row.folderPath] }),
      })
      onRun(['verify'])
    } catch { /* silent */ }
    finally { setGenerating(false) }
  }, [row.folderPath, onRun])

  if (step.status === 'mute' && row.running) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Banner tone="info" icon="info">
          <strong>{t('pipeline.verify.hashingFiles')}</strong>
          <div style={{ marginTop: 4, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
            {t('pipeline.verify.advanceAuto')}
          </div>
        </Banner>
      </div>
    )
  }

  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          {t('pipeline.verify.notRun')}
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['verify'])}>{t('pipeline.verify.run')}</Button>
      </div>
    )
  }

  if (step.shntool_missing) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Banner tone="warn" icon="alert" title={t('pipeline.verify.shnToolMissingTitle')}>
          {t('pipeline.verify.shnToolMissingBody')}
        </Banner>
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')}
          onClick={() => onRun(['verify'])}>{t('pipeline.verify.rerun')}</Button>
      </div>
    )
  }

  if (step.no_checksums) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 14, padding: '16px 18px', background: 'var(--lbb-warn-bg)', border: '1px solid var(--lbb-warn-bar)', borderRadius: 9 }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, flexShrink: 0, background: 'var(--lbb-warn-bar)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="shield" size={20} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 'var(--lbb-fs-13-5)', fontWeight: 700, marginBottom: 4 }}>{t('pipeline.verify.noChecksumsTitle')}</div>
            <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', lineHeight: 1.5, marginBottom: 10 }}>
              {t('pipeline.verify.noChecksumsBody')}
            </div>
            <Button variant="primary" size="sm" icon="shield" disabled={generating}
              onClick={handleGenerate}>
              {generating ? t('pipeline.verify.generating') : t('pipeline.verify.generate')}
            </Button>
          </div>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {t('pipeline.verify.generateInfo')}
        </div>
      </div>
    )
  }

  const total    = step.total    ?? 0
  const pass     = step.pass     ?? 0
  const missing  = step.missing  ?? 0
  const mismatch = step.mismatch ?? 0
  const extra    = step.extra    ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusTag state={STATUS_TO_STATE[step.status]}>{step.label}</StatusTag>
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')}
          onClick={() => onRun(['verify'])}>{t('pipeline.verify.rerun')}</Button>
      </div>

      {total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6 }}>
          {([
            { l: t('pipeline.verify.stats.total'),    v: total,    c: undefined },
            { l: t('pipeline.verify.stats.pass'),     v: pass,     c: pass === total && total > 0 ? 'var(--lbb-ok-fg)' : undefined },
            { l: t('pipeline.verify.stats.missing'),  v: missing,  c: missing  > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            { l: t('pipeline.verify.stats.mismatch'), v: mismatch, c: mismatch > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            { l: t('pipeline.verify.stats.extra'),    v: extra,    c: extra    > 0 ? 'var(--lbb-info-fg)' : 'var(--lbb-fg3)' },
          ] as { l: string; v: number; c: string | undefined }[]).map(({ l, v, c }) => (
            <div key={l} style={{ padding: '6px 8px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{l}</div>
              <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: c ?? 'var(--lbb-fg)' }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {(step.files?.length ?? 0) > 0 && (
        <VerifyDetail
          files={step.files!}
          showAll={showAll}
          onShowAllChange={setShowAll}
          onCopyReport={handleCopyReport}
          onOpenFinder={() => window.api.openPath(row.folderPath)}
          onGenerateMissing={handleGenerate}
          generateBusy={generating}
          compact
        />
      )}

      {step.status === 'bad' && missing > 0 && (
        <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>
          {t('pipeline.verify.missingFiles', { count: missing })}
        </div>
      )}

      {step.status === 'bad' && mismatch > 0 && (
        <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>
          {t('pipeline.verify.mismatchedFiles', { count: mismatch })}
        </div>
      )}
    </div>
  )
}

function LookupStageContent({ step, row, onRun }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [pinBusyLb, setPinBusyLb] = useState<number | null>(null)

  const handlePin = useCallback(async (lb: number) => {
    setPinBusyLb(lb)
    try {
      await fetch(`${BASE}/api/folder_link`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder_path: row.folderPath,
          lb_number: lb,
          note: 'Pinned from pipeline lookup',
        }),
      })
      onRun(['lookup', 'lbdir', 'rename', 'file'])
    } catch { /* silent */ }
    finally { setPinBusyLb(null) }
  }, [row.folderPath, onRun])

  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          {t('pipeline.lookup.runsAuto')}
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['lookup'])}>{t('pipeline.lookup.run')}</Button>
      </div>
    )
  }

  const lbFormatted = step.lb_number
    ? `LB-${String(step.lb_number).padStart(5, '0')}`
    : null
  const isMultiLb = (step.lb_numbers?.length ?? 0) > 1

  if (step.status === 'ok' && lbFormatted) {
    const summRow = step.summary?.lb_summary.find(r => r.lb_number === step.lb_number)
    const multiLabel = isMultiLb
      ? step.lb_numbers!.map(n => `LB-${String(n).padStart(5, '0')}`).join(' + ')
      : null
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)', borderRadius: 8 }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, background: 'var(--lbb-ok-bar)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Icon name="check" size={22} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-accent-mid)' }}>
                {multiLabel ?? lbFormatted}
              </span>
              {!isMultiLb && summRow && categoryPill(summRow.lb_category)}
              {!isMultiLb && step.summary && (
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
                  {t('pipeline.lookup.matchedCount', { matched: step.summary.matched, given: step.summary.given })}
                </span>
              )}
              {isMultiLb && (
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                  {t('pipeline.lookup.multiLbInfo')}
                </span>
              )}
            </div>
            {step.alias_resolved_from && step.alias_resolved_from.length > 0 && (
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
                {t('pipeline.lookup.resolvedFrom', { list: step.alias_resolved_from.map(n => `LB-${String(n).padStart(5, '0')}`).join(', ') })}
              </div>
            )}
          </div>
          <StatusTag state="pass">{isMultiLb ? t('pipeline.lookup.multiLb') : t('pipeline.lookup.matched')}</StatusTag>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {isMultiLb ? t('pipeline.lookup.multiLbMsg') : t('pipeline.lookup.flowsAuto')}
        </div>
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup'])}>{t('pipeline.lookup.rerun')}</Button>
      </div>
    )
  }

  if (step.status === 'warn' && step.lb_number == null) {
    const summaryRows = step.summary?.lb_summary ?? []
    const detailRows = step.detail ?? []
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatusTag state="action">{step.label}</StatusTag>
          <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700 }}>{t('pipeline.lookup.whichShow')}</span>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup'])}>{t('pipeline.lookup.rerun')}</Button>
        </div>
        <LookupDetail summaryRows={summaryRows} detailRows={detailRows} onPin={handlePin} pinBusyLb={pinBusyLb} />
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {t('pipeline.lookup.pinInfo')}
        </div>
      </div>
    )
  }

  if (step.status === 'warn' && step.lb_number != null) {
    const summaryRows = step.summary?.lb_summary ?? []
    const detailRows = step.detail ?? []
    const lbStr = `LB-${String(step.lb_number).padStart(5, '0')}`
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatusTag state="action">{step.label}</StatusTag>
          <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700 }}>{lbStr}</span>
          {step.summary && (
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
              {t('pipeline.lookup.matchedCount', { matched: step.summary.matched, given: step.summary.given })}
            </span>
          )}
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup'])}>{t('pipeline.lookup.rerun')}</Button>
        </div>
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
          {t('pipeline.lookup.partialMatchInfo', { lb: lbStr })}
        </div>
        <LookupDetail summaryRows={summaryRows} detailRows={detailRows} onPin={handlePin} pinBusyLb={pinBusyLb} />
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {t('pipeline.lookup.pinConfirms', { lb: lbStr })}
        </div>
      </div>
    )
  }

  const summaryRows = step.summary?.lb_summary ?? []
  const detailRows = step.detail ?? []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusTag state={STATUS_TO_STATE[step.status]}>{step.label}</StatusTag>
        <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700 }}>{t('pipeline.lookup.noMatches')}</span>
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup'])}>{t('pipeline.lookup.rerun')}</Button>
      </div>
      <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
        {t('pipeline.lookup.noMatchesInfo')}
      </div>
      <LookupDetail summaryRows={summaryRows} detailRows={detailRows} />
    </div>
  )
}

function highlightLb(name: string, lb: string, strike?: boolean): React.JSX.Element {
  const idx = name.toUpperCase().indexOf(lb.toUpperCase())
  if (idx < 0) return <>{name}</>
  return (
    <>
      {name.slice(0, idx)}
      <span style={{ fontWeight: 700, color: strike ? 'var(--lbb-bad-fg)' : 'var(--lbb-ok-fg)',
        textDecoration: strike ? 'line-through' : 'none' }}>
        {name.slice(idx, idx + lb.length)}
      </span>
      {name.slice(idx + lb.length)}
    </>
  )
}

function RenameStageContent({ step, row, onRun, onRename }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
  onRename: (customName?: string) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')

  const lb = row.steps.lookup.lb_number
  const lbTag = lb ? `LB-${String(lb).padStart(5, '0')}` : null
  const folderLbMatch = row.folderName.match(/LB-(\d+)/i)
  const folderLb = folderLbMatch ? `LB-${String(parseInt(folderLbMatch[1], 10)).padStart(5, '0')}` : null
  const hasWrongLb = !!(lbTag && folderLb && folderLb !== lbTag)

  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          {t('pipeline.rename.unlocksAfter')}
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['lookup', 'rename'])}>{t('pipeline.rename.checkRename')}</Button>
      </div>
    )
  }

  if (step.status === 'ok' && step.label === 'Renamed') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px',
          background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)', borderRadius: 8 }}>
          <Icon name="check" size={16} style={{ color: 'var(--lbb-ok-fg)', flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-ok-fg)' }}>{t('pipeline.rename.renamed')}</div>
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', marginTop: 2 }}>
              {t('pipeline.rename.loggedReady')}
            </div>
          </div>
        </div>
        <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
          padding: '8px 10px', background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
          borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.folderName}
        </div>
      </div>
    )
  }

  if (step.status === 'ok' || !step.proposed) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--lbb-ok-fg)',
          fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>
          <Icon name="check" size={14} />
          {t('pipeline.rename.alreadyCorrect')}
        </div>
        <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
          padding: '8px 10px', background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
          borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.folderName}
        </div>
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup', 'rename'])}>{t('pipeline.rename.recheck')}</Button>
      </div>
    )
  }

  const title = hasWrongLb ? t('pipeline.rename.fixWrongLb') : t('pipeline.rename.reviewProposed')

  const copyDiff = () => {
    const target = editing ? editValue : step.proposed!
    navigator.clipboard.writeText(`Current:  ${row.folderName}\nProposed: ${target}`)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 1. Stage head */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <StatusTag state="action" style={{ flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-13)', flex: 1, minWidth: 0 }}>{title}</span>
        {lbTag && <Pill tone="ok" soft dot style={{ flexShrink: 0, fontFamily: 'var(--lbb-mono)' }}>{lbTag}</Pill>}
        {editing ? (
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)} style={{ flexShrink: 0 }}>{t('pipeline.rename.cancel')}</Button>
        ) : (
          <Button variant="ghost" size="sm" icon="rename" onClick={() => { setEditValue(step.proposed!); setEditing(true) }} style={{ flexShrink: 0 }}>{t('pipeline.rename.editName')}</Button>
        )}
      </div>

      {/* 2. Wrong-LB banner */}
      {hasWrongLb && (
        <Banner tone="warn" icon="alert" title={t('pipeline.rename.mislabeledTitle', { lb: folderLb })}>
          {t('pipeline.rename.mislabeledBody', { lb: folderLb, newLb: lbTag })}
        </Banner>
      )}

      {/* 2b. Rename failure banner (e.g. duplicate folder at destination) */}
      {step.error && (
        <Banner tone="bad" icon="alert" title={t('pipeline.rename.failedTitle')}>
          {step.error}
        </Banner>
      )}

      {/* 3. Diff box */}
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--lbb-bad-bg)' }}>
          <Icon name="x" size={13} style={{ color: 'var(--lbb-bad-fg)', flexShrink: 0 }} />
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)',
            flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {hasWrongLb && folderLb ? highlightLb(row.folderName, folderLb, true) : row.folderName}
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-bad-fg)',
            textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>{t('pipeline.rename.current')}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
          background: 'var(--lbb-ok-bg)', borderTop: '1px solid var(--lbb-border)' }}>
          <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)', flexShrink: 0 }} />
          {editing ? (
            <input
              value={editValue}
              onChange={e => setEditValue(e.target.value)}
              autoFocus
              style={{ flex: 1, minWidth: 0, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
                background: 'transparent', border: 'none', outline: '1px solid var(--lbb-ok-bar)',
                borderRadius: 4, padding: '2px 6px', color: 'var(--lbb-fg)' }}
            />
          ) : (
            <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)',
              fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {lbTag ? highlightLb(step.proposed!, lbTag) : step.proposed}
            </span>
          )}
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-ok-fg)',
            textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>
            {editing ? t('pipeline.rename.editing') : t('pipeline.rename.proposed')}
          </span>
        </div>
      </div>

      {/* 4. Info banner */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 6,
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
        <Icon name="info" size={12} style={{ flexShrink: 0 }} />
        <span style={{ flex: 1 }}>{t('pipeline.rename.dryRun')}</span>
        <Button variant="ghost" size="sm" icon="copy" onClick={copyDiff} title={t('pipeline.rename.copyToClipboard')} style={{ flexShrink: 0 }}>{t('pipeline.rename.copyDiff')}</Button>
      </div>
      <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)',
        border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
        {t('pipeline.rename.loggedOnly')}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button variant="primary" size="sm" icon="check"
          onClick={() => onRename(editing ? editValue : undefined)}>{t('pipeline.rename.apply')}</Button>
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup', 'rename'])}>{t('pipeline.rename.recheck')}</Button>
      </div>
    </div>
  )
}

/** Mount picker preview — refetches dest/mount_label when the user overrides the suggested mount. */
function CollectReadyDetail({ step, row, onRun, onFile }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
  onFile?: (mountId?: number | null, dest?: string | null, mountLabel?: string | null) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [selectedMount, setSelectedMount] = useState<number | null>(step.recommended_mount ?? null)
  const [preview, setPreview] = useState<{ dest: string | null; mount_label: string | null } | null>(null)

  useEffect(() => {
    setSelectedMount(step.recommended_mount ?? null)
    setPreview(null)
  }, [step.recommended_mount, row.folderPath])

  useEffect(() => {
    const lb = row.steps.lookup.lb_number
    if (selectedMount == null || selectedMount === step.recommended_mount || !lb) {
      setPreview(null)
      return
    }
    let cancelled = false
    fetch(`${BASE}/api/pipeline/file/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: [{ path: row.folderPath, lb_number: lb, mount_id: selectedMount }] }),
    })
      .then(r => r.json())
      .then((data: { results?: Array<{ ok: boolean; dest?: string; mount_label?: string }> }) => {
        if (cancelled) return
        const result = data.results?.[0]
        if (result?.ok) setPreview({ dest: result.dest ?? null, mount_label: result.mount_label ?? null })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedMount, step.recommended_mount, row.folderPath, row.steps.lookup.lb_number])

  const overrideSelected = selectedMount != null && selectedMount !== step.recommended_mount
  const previewPending = overrideSelected && preview == null
  const dest = preview?.dest ?? step.dest
  const mountLabel = preview?.mount_label ?? step.mount_label
  const lb = row.steps.lookup.lb_number
  const lbLabel = lb ? `LB-${String(lb).padStart(5, '0')}` : null
  const renamePending = row.steps.rename.status === 'warn' && !!row.steps.rename.proposed

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 9, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--lbb-surface)' }}>
          <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.folderPath}</span>
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>{t('pipeline.collect.staging')}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '3px 0', background: 'var(--lbb-surface)' }}>
          <Icon name="drop" size={13} style={{ color: 'var(--lbb-accent-mid)' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'var(--lbb-accent-soft)', borderTop: '1px solid var(--lbb-border)' }}>
          <Icon name="folder" size={13} style={{ color: 'var(--lbb-accent-mid)', flexShrink: 0 }} />
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {mountLabel && (
              <mark style={{ background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)', borderRadius: 3, padding: '1px 4px', marginRight: 4 }}>{mountLabel}</mark>
            )}
            {dest ?? '—'}
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-accent-mid)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>{t('pipeline.collect.finalStorage')}</span>
        </div>
      </div>
      {step.mounts && step.mounts.length > 0 && (
        <CollectDetail
          mounts={step.mounts}
          selectedMount={selectedMount}
          recommendedMount={step.recommended_mount ?? null}
          routedYear={step.routed_year}
          lbLabel={lbLabel}
          collectionCount={step.collection_count}
          lbStatus={step.lb_status ?? null}
          owned={step.owned ?? false}
          confirmedAt={step.lbdir_verified_at ?? null}
          onSelectMount={setSelectedMount}
        />
      )}
      {renamePending && (
        <Banner tone="warn" icon="alert" title={t('pipeline.collect.renamePendingTitle')}>
          {t('pipeline.collect.renamePendingBody')}
        </Banner>
      )}
      {step.owned && step.existing_disk_path && (
        <Banner tone="warn" icon="warn" title={t('pipeline.collect.alreadyInCollectionTitle')}>
          {t('pipeline.collect.alreadyInCollectionBody', { path: step.existing_disk_path })}
        </Banner>
      )}
      <Banner tone="info" icon="info" title={t('pipeline.collect.whatFilingTitle')}
        action={
          row.running && row.fileProgress ? (
            <FileProgressBar progress={row.fileProgress} />
          ) : (
            <Button variant="primary" size="sm" icon="folder" disabled={previewPending || renamePending}
              onClick={() => onFile?.(selectedMount, dest, mountLabel)}>
              {t('pipeline.collect.fileAction')}
            </Button>
          )
        }>
        {t('pipeline.collect.filingBody', { dest: dest ?? '—' })}
        {previewPending && (
          <div style={{ marginTop: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
            {t('pipeline.collect.resolvingDest', { reset: t('pipeline.collect.resetToSuggested') })}
          </div>
        )}
      </Banner>
      <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')}
      onClick={() => onRun(['lookup', 'file'])} style={{ alignSelf: 'flex-start' }}>{t('pipeline.collect.recheckRoute')}</Button>
    </div>
  )
}

function CollectStageContent({ step, row, onRun, onFile }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
  onFile?: (mountId?: number | null, dest?: string | null, mountLabel?: string | null) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const ERROR_MSG: Record<string, string> = {
    no_date:       t('pipeline.collect.errors.noDate'),
    no_route:      t('pipeline.collect.errors.noRoute'),
    mount_offline: t('pipeline.collect.errors.mountOffline'),
    dest_exists:   t('pipeline.collect.errors.destExists'),
    db_error:      t('pipeline.collect.errors.dbError'),
  }

  if (step.status === 'ok') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)', borderRadius: 9 }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, flexShrink: 0, background: 'var(--lbb-ok-bar)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="check" size={22} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700 }}>{t('pipeline.collect.addedTitle')}</div>
            {step.dest && (
              <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{step.dest}</div>
            )}
          </div>
          {step.mount_label && <Pill tone="ok" soft dot>{step.mount_label}</Pill>}
        </div>
        {(step.lb_number || step.mount_label) && (
          <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
            {step.lb_number && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
                background: 'var(--lbb-surface)', borderBottom: step.mount_label ? '1px solid var(--lbb-border)' : 'none' }}>
                <span style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg3)',
                  textTransform: 'uppercase', letterSpacing: 0.04, width: 80, flexShrink: 0 }}>{t('pipeline.collect.lbLabel')}</span>
                <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 700, color: 'var(--lbb-accent-mid)' }}>
                  {`LB-${String(step.lb_number).padStart(5, '0')}`}
                </span>
              </div>
            )}
            {step.mount_label && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
                background: 'var(--lbb-surface2)' }}>
                <span style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg3)',
                  textTransform: 'uppercase', letterSpacing: 0.04, width: 80, flexShrink: 0 }}>{t('pipeline.collect.mountLabelText')}</span>
                <span style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg)' }}>{step.mount_label}</span>
              </div>
            )}
          </div>
        )}
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {t('pipeline.rename.loggedOnly')}
        </div>
      </div>
    )
  }

  if (step.status === 'bad') {
    const msg = step.error_code ? (ERROR_MSG[step.error_code] ?? step.error) : step.error
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ padding: '12px 14px', borderRadius: 8, background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <Icon name="alert" size={14} style={{ color: 'var(--lbb-bad-fg)', flexShrink: 0 }} />
            <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-bad-fg)' }}>{t('pipeline.collect.cantFile')}</span>
            {step.error_code && (
              <Pill tone="bad" soft style={{ fontFamily: 'var(--lbb-mono)', marginLeft: 'auto' }}>{step.error_code}</Pill>
            )}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>{msg ?? t('pipeline.collect.unknownError')}</div>
        </div>
        <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup', 'file'])}>{t('pipeline.collect.recheckRoute')}</Button>
      </div>
    )
  }

  if (step.status === 'warn') {
    return <CollectReadyDetail step={step} row={row} onRun={onRun} onFile={onFile} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Banner tone="info" icon="info">
        {t('pipeline.collect.lastStepInfo')}
      </Banner>
      <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')}
          onClick={() => onRun(['lookup', 'file'])} style={{ alignSelf: 'flex-start' }}>{t('pipeline.collect.checkRouteNow')}</Button>
    </div>
  )
}

function StageContent({ step, stageKey, row, onRun, onRename, onFile }: {
  step: StepResult
  stageKey: string
  row: PipelineRow
  onRun: (steps: string[]) => void
  onRename: (customName?: string) => void
  onFile?: (mountId?: number | null, dest?: string | null, mountLabel?: string | null) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  if (stageKey === 'verify')  return <VerifyStageContent  step={step} row={row} onRun={onRun} />
  if (stageKey === 'lookup')  return <LookupStageContent  step={step} row={row} onRun={onRun} />
  if (stageKey === 'rename')  return <RenameStageContent  step={step} row={row} onRun={onRun} onRename={onRename} />
  if (stageKey === 'file')    return <CollectStageContent step={step} row={row} onRun={onRun} onFile={onFile} />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <StatusTag state={STATUS_TO_STATE[step.status]}>{step.label}</StatusTag>
      <Button variant="ghost" size="sm" icon="refresh" title={t('pipeline.rerunStage')} onClick={() => onRun(['lookup', stageKey])}>{t('pipeline.rerunGeneric')}</Button>
    </div>
  )
}

// ── DetailPanel ───────────────────────────────────────────────────────────────

function DetailPanel({ row, initialStage, onClose, onRowRefresh, onRun, onRename, onFile }: {
  row: PipelineRow
  initialStage: string
  onClose: () => void
  onRowRefresh: (id: string) => void
  onRun: (id: string, steps: string[]) => void
  onRename: (customName?: string) => void
  onFile?: (mountId?: number | null, dest?: string | null, mountLabel?: string | null) => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const [activeStage, setActiveStage] = useState(initialStage)
  const folderRow = toFolderRow(row)

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0,
      background: 'var(--lbb-bg)',
    }}>
      {/* Header: ← Batch breadcrumb + folder name */}
      <div style={{
        padding: '12px 20px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
      }}>
        <button
          onClick={onClose}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            background: 'none', border: '1px solid var(--lbb-border2)',
            borderRadius: 6, padding: '4px 10px', color: 'var(--lbb-fg2)',
            fontFamily: 'inherit', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer',
          }}
        >
          <Icon name="chevLeft" size={13} /> {t('pipeline.detail.batch')}
        </button>
        <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{
          fontWeight: 600, fontSize: 'var(--lbb-fs-13)', flex: 1, minWidth: 0,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'var(--lbb-mono)',
        }}>
          {row.folderName}
        </span>
        <Button variant="ghost" size="sm" icon="reveal" title={t('pipeline.detail.revealTitle')}
          onClick={() => window.api.openPath(row.folderPath)}>
          {t('pipeline.detail.open')}
        </Button>
      </div>

      {/* Stage stepper — full width, all 5 stages */}
      <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <StageStepper
          folder={folderRow}
          stages={DEFAULT_STAGES}
          activeKey={activeStage}
          onPick={setActiveStage}
        />
      </div>

      {/* Stage panel (scrollable) */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {activeStage === 'lbdir' ? (
          <LbdirStageContent row={row} onRowRefresh={onRowRefresh} />
        ) : (
          <StageContent
            step={row.steps[activeStage as keyof typeof row.steps] ?? MUTE}
            stageKey={activeStage}
            row={row}
            onRun={(steps) => onRun(row.id, steps)}
            onRename={onRename}
            onFile={activeStage === 'file' ? onFile : undefined}
          />
        )}
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenPipeline(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { folders: queueFolders, addFolders: addToQueue, removeFolders, clearFolders } = useFolderQueueStore()

  const [rows, setRows]                     = useState<PipelineRow[]>([])
  const [filter, setFilter]                 = useState<Bucket>('all')
  const [autorun, setAutorun]               = useState(true)
  const [autoRename, setAutoRename]         = useState(false)
  const [tableSearch, setTableSearch]       = useState('')
  const [queueSearch, setQueueSearch]       = useState('')
  const [activeQueue, setActiveQueue]       = useState<string | null>(null)
  const [lastShiftAnchor, setLastShiftAnchor] = useState<string | null>(null)
  const [dragOver, setDragOver]             = useState(false)
  const [ctxMenu, setCtxMenu]               = useState<{ x: number; y: number; id: string } | null>(null)
  const [detailId, setDetailId]             = useState<string | null>(null)
  const [detailStage, setDetailStage]       = useState<string>('verify')
  const [confirm, ConfirmHost]              = useConfirm()
  const [collapsedBuckets, setCollapsedBuckets] = useState<Set<Bucket>>(new Set())
  const [filingActive, setFilingActive]     = useState(false)
  const [toast, setToast]                   = useState<{ msg: string; ok: boolean } | null>(null)

  const showToast = useCallback((msg: string, ok: boolean) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }, [])

  const toggleBucket = useCallback((bucket: Bucket) => {
    setCollapsedBuckets(prev => {
      const next = new Set(prev)
      if (next.has(bucket)) next.delete(bucket)
      else next.add(bucket)
      return next
    })
  }, [])

  // Sync shared folder queue → local rows
  useEffect(() => {
    setRows(prev => {
      const queueSet = new Set(queueFolders)
      const kept = prev.filter(r => queueSet.has(r.id))
      const existingIds = new Set(kept.map(r => r.id))
      const added = queueFolders.filter(p => !existingIds.has(p)).map(p => {
        const cached = _pipelineCache.get(p)
        return cached ? { ...emptyRow(p), ...cached } : emptyRow(p)
      })
      if (kept.length === prev.length && !added.length) return prev
      if (autorun && added.length) {
        // Only auto-run rows with no prior results (verify still mute = never processed)
        const toRun = added.filter(r => r.steps.verify.status === 'mute').map(r => r.id)
        if (toRun.length) autorunPendingRef.current = [...autorunPendingRef.current, ...toRun]
      }
      return [...kept, ...added]
    })
  }, [queueFolders, autorun])

  const tableParentRef    = useRef<HTMLDivElement>(null)
  const flatListRef       = useRef<VItem[]>([])
  const stopRef              = useRef(false)
  const abortRef             = useRef<AbortController | null>(null)
  const autorunPendingRef    = useRef<string[]>([])
  const autocompleteStarted  = useRef<Set<string>>(new Set())
  const autoRenamedRef       = useRef<Set<string>>(new Set())
  const filingRef            = useRef(false)

  // ── Derived counts ───────────────────────────────────────────────────────────
  const counts = {
    all:     rows.length,
    needs:   rows.filter(r => !r.running && r.bucket === 'needs').length,
    ready:   rows.filter(r => !r.running && r.bucket === 'ready').length,
    running: rows.filter(r => r.running).length,
    shelf:   rows.filter(r => !r.running && r.bucket === 'shelf' && !r.shelved).length,
    done:    rows.filter(r => !r.running && r.bucket === 'done').length,
  }

  const isRunning       = rows.some(r => r.running)
  const selectedRows    = rows.filter(r => r.selected)
  const selectedReady   = selectedRows.filter(r => r.bucket === 'ready')
  const fileableRows    = rows.filter(r => !r.running && r.steps.file.status === 'warn' && !!r.steps.file.dest && !r.shelved && !(r.steps.rename.status === 'warn' && !!r.steps.rename.proposed))
  const selectedFileable = selectedRows.filter(r => !r.running && r.steps.file.status === 'warn' && !!r.steps.file.dest && !r.shelved && !(r.steps.rename.status === 'warn' && !!r.steps.rename.proposed))

  // ── Filtered rows ────────────────────────────────────────────────────────────
  const visibleRows = rows.filter(r => {
    const effectiveBucket: Bucket = r.running ? 'running' : r.bucket
    if (filter !== 'all' && effectiveBucket !== filter) return false
    if (tableSearch) {
      const q = tableSearch.toLowerCase()
      if (!r.folderName.toLowerCase().includes(q)) return false
    }
    return true
  })

  const needsVis   = visibleRows.filter(r => !r.running && r.bucket === 'needs')
  const runningVis = visibleRows.filter(r => r.running)
  const readyVis   = visibleRows.filter(r => !r.running && r.bucket === 'ready')
  const shelfVis   = visibleRows.filter(r => !r.running && r.bucket === 'shelf')
  const doneVis    = visibleRows.filter(r => !r.running && r.bucket === 'done')

  // ── Virtualizer flat list ────────────────────────────────────────────────────
  const flatList: VItem[] = []
  if (needsVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.needs'), count: counts.needs, bucket: 'needs' })
    if (!collapsedBuckets.has('needs')) needsVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (runningVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.running'), count: counts.running, bucket: 'running' })
    if (!collapsedBuckets.has('running')) runningVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (readyVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.ready'), count: counts.ready, bucket: 'ready' })
    if (!collapsedBuckets.has('ready')) readyVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (shelfVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.shelf'), count: counts.shelf, bucket: 'shelf' })
    if (!collapsedBuckets.has('shelf')) shelfVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (doneVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.done'), count: counts.done, bucket: 'done' })
    if (!collapsedBuckets.has('done')) doneVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }

  flatListRef.current = flatList

  const virtualizer = useVirtualizer({
    count: flatList.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: () => 38,
    overscan: 12,
    measureElement: (el) => el?.getBoundingClientRect().height ?? 38,
  })

  // ── Queue rail filtered list ─────────────────────────────────────────────────
  const queueRows = queueSearch
    ? rows.filter(r => r.folderName.toLowerCase().includes(queueSearch.toLowerCase()))
    : rows

  // ── Row mutation helpers ─────────────────────────────────────────────────────
  const updateRow = useCallback((id: string, patch: Partial<PipelineRow>) => {
    setRows(prev => prev.map(r => {
      if (r.id !== id) return r
      const updated = { ...r, ...patch }
      if (patch.steps !== undefined || patch.bucket !== undefined || patch.errors !== undefined) {
        _pipelineCache.set(id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
      }
      return updated
    }))
  }, [])

  // Merge a server result into the current row. Requested steps always take the
  // fresh value; unrequested steps keep their current result unless the server
  // ran them anyway (the backend auto-includes lookup with rename/lbdir/file so
  // the LB# link survives partial runs). Merging against the live row (not a
  // snapshot captured when the run started) prevents wiping results that landed
  // while the request was in flight.
  const mergeServerRow = useCallback((id: string, fresh: Partial<PipelineRow>, stepSet: Set<string>) => {
    setRows(prev => prev.map(r => {
      if (r.id !== id) return r
      const steps = { ...fresh.steps! }
      for (const key of ['verify', 'lookup', 'lbdir', 'rename', 'file'] as const) {
        if (!stepSet.has(key) && steps[key].status === 'mute') steps[key] = r.steps[key]
      }
      const updated = { ...r, ...fresh, steps }
      _pipelineCache.set(id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
      return updated
    }))
  }, [])

  const addFolders = useCallback((paths: string[]) => {
    addToQueue(paths)
    setRows(prev => {
      const existing = new Set(prev.map(r => r.id))
      const newRows = paths.filter(p => !existing.has(p)).map(emptyRow)
      if (autorun && newRows.length) {
        autorunPendingRef.current = [...autorunPendingRef.current, ...newRows.map(r => r.id)]
      }
      return [...prev, ...newRows]
    })
  }, [addToQueue, autorun])

  // ── Backend: run steps ───────────────────────────────────────────────────────
  const runSteps = useCallback(async (targetIds: string[], steps: string[]) => {
    const targets = rows.filter(r => targetIds.includes(r.id))
    if (!targets.length) return

    stopRef.current = false

    for (const target of targets) {
      if (stopRef.current) break

      updateRow(target.id, { running: true })
      const ctrl = new AbortController()
      abortRef.current = ctrl

      try {
        const resp = await fetch(`${BASE}/api/pipeline/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [target.folderPath], steps }),
          signal: ctrl.signal,
        })
        if (resp.ok) {
          const data = await resp.json() as { results: Record<string, unknown>[] }
          if (data.results[0]) {
            const fresh = serverRowToPipeline(data.results[0])
            mergeServerRow(target.id, fresh, new Set(steps))
          } else updateRow(target.id, { running: false })
        } else {
          updateRow(target.id, { running: false })
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') updateRow(target.id, { running: false })
      }
    }
    abortRef.current = null
  }, [rows, updateRow, mergeServerRow])

  const stopRun = useCallback(() => {
    stopRef.current = true
    abortRef.current?.abort()
    abortRef.current = null
    setRows(prev => prev.map(r => r.running ? { ...r, running: false } : r))
  }, [])

  // ── Auto-run: drain pending queue after state settles ────────────────────────
  useEffect(() => {
    const pending = autorunPendingRef.current
    if (!pending.length) return
    const ready = pending.filter(id => rows.some(r => r.id === id))
    if (!ready.length) return
    autorunPendingRef.current = pending.filter(id => !ready.includes(id))
    runSteps(ready, ['verify', 'lookup', 'lbdir', 'rename', 'file'])
  }, [rows, runSteps])

  // ── Auto-complete: resume folders where lookup resolved but lbdir/rename weren't run ──
  useEffect(() => {
    const stale = rows.filter(r =>
      !r.running &&
      r.steps.lookup.status === 'ok' &&
      r.steps.lbdir.status === 'mute' &&
      !autocompleteStarted.current.has(r.id)
    )
    if (!stale.length) return
    stale.forEach(r => autocompleteStarted.current.add(r.id))
    runSteps(stale.map(r => r.id), ['lookup', 'lbdir', 'rename', 'file'])
  }, [rows, runSteps])

  // Refresh one row's lbdir step (called after reconcile apply in detail panel)
  const refreshDetailRow = useCallback(async (id: string) => {
    const target = rows.find(r => r.id === id)
    if (!target) return
    try {
      const resp = await fetch(`${BASE}/api/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [target.folderPath], steps: ['lbdir'] }),
      })
      if (resp.ok) {
        const data = await resp.json() as { results: Record<string, unknown>[] }
        if (data.results[0]) {
          const fresh = serverRowToPipeline(data.results[0])
          mergeServerRow(id, fresh, new Set(['lbdir']))
        }
      }
    } catch { /* silent */ }
  }, [rows, mergeServerRow])

  // ── Apply a single rename ────────────────────────────────────────────────────
  const applyRename = useCallback(async (row: PipelineRow, customName?: string) => {
    const proposed = customName ?? row.steps.rename.proposed
    if (!proposed) return
    try {
      const resp = await fetch(`${BASE}/api/folder/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: row.folderPath, new_name: proposed }),
      })
      const data = await resp.json() as { ok?: boolean; new_path?: string; error?: string }
      if (data.ok && data.new_path) {
        const newName = data.new_path.split(/[/\\]/).pop() ?? proposed
        // If the detail panel was open for this row, update its id
        if (detailId === row.id) setDetailId(data.new_path)
        setRows(prev => prev.map(r => {
          if (r.id !== row.id) return r
          const updated = {
            ...r,
            folderPath: data.new_path!,
            folderName: newName,
            id: data.new_path!,
            bucket: (r.steps.file.status === 'warn' ? 'shelf' : 'done') as Bucket,
            steps: { ...r.steps, rename: { status: 'ok' as const, label: 'Renamed' } },
          }
          _pipelineCache.delete(row.id)
          _pipelineCache.set(data.new_path!, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
          return updated
        }))
        useFolderQueueStore.getState().removeFolders([row.folderPath])
        useFolderQueueStore.getState().addFolders([data.new_path])

        // The "file" step's destination was resolved against the pre-rename
        // folder name — refresh it now that the rename has been applied on disk.
        try {
          const fresp = await fetch(`${BASE}/api/pipeline/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folders: [data.new_path], steps: ['file'] }),
          })
          if (fresp.ok) {
            const fdata = await fresp.json() as { results: Record<string, unknown>[] }
            const file = fdata.results[0] ? normalizeFileStep(fdata.results[0].file) : null
            if (file) {
              setRows(prev => prev.map(r => {
                if (r.id !== data.new_path) return r
                const updated = { ...r, steps: { ...r.steps, file } }
                _pipelineCache.set(r.id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
                return updated
              }))
            }
          }
        } catch { /* silent */ }
      } else {
        const message = data.error || 'Rename failed'
        setRows(prev => prev.map(r => {
          if (r.id !== row.id) return r
          const updated = { ...r, steps: { ...r.steps, rename: { ...r.steps.rename, status: 'warn' as const, error: message } } }
          _pipelineCache.set(r.id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
          return updated
        }))
      }
    } catch {
      setRows(prev => prev.map(r => {
        if (r.id !== row.id) return r
        const updated = { ...r, steps: { ...r.steps, rename: { ...r.steps.rename, status: 'warn' as const, error: 'Rename failed — could not reach backend' } } }
        _pipelineCache.set(r.id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
        return updated
      }))
    }
  }, [detailId])

  const applyAllReady = useCallback(async () => {
    const readyRows = rows.filter(r => r.bucket === 'ready')
    for (const row of readyRows) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [rows, applyRename])

  // ── Auto-rename: when verify/lookup/lbdir all pass with a single confident LB
  // match and rename has a proposal queued, apply it automatically and advance
  // straight to the collect stage — no "Apply rename" click needed.
  useEffect(() => {
    if (!autoRename) return
    const candidates = rows.filter(r =>
      !r.running &&
      r.steps.verify.status === 'ok' &&
      r.steps.lookup.status === 'ok' &&
      r.steps.lbdir.status === 'ok' &&
      r.steps.rename.status === 'warn' &&
      !!r.steps.rename.proposed &&
      !autoRenamedRef.current.has(r.id)
    )
    if (!candidates.length) return
    ;(async () => {
      for (const r of candidates) {
        autoRenamedRef.current.add(r.id)
        await applyRename(r)
      }
    })()
  }, [rows, autoRename, applyRename])

  const applySelected = useCallback(async () => {
    for (const row of selectedReady) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [selectedReady, applyRename])

  // ── File a folder into the collection ────────────────────────────────────────
  const applyFile = useCallback(async (
    row: PipelineRow, mountId?: number | null, overrideDest?: string | null, overrideMountLabel?: string | null,
    skipConfirm?: boolean,
  ) => {
    if (row.steps.rename.status === 'warn' && row.steps.rename.proposed) {
      showToast(t('pipeline.file.renamePending'), false)
      return
    }

    const lb = row.steps.lookup.lb_number
    const dest = overrideDest ?? row.steps.file.dest
    if (!lb || !dest) return

    const mountLabel = overrideMountLabel ?? row.steps.file.mount_label ?? 'collection mount'
    const destName = dest.split(/[/\\]/).pop() ?? dest

    if (!skipConfirm) {
      const ok = await confirm({
        tone: 'info',
        title: t('pipeline.file.confirmTitle'),
        body: t('pipeline.file.confirmBody', { folder: row.folderName, mount: mountLabel }),
        items: [{ label: destName, icon: 'folder', meta: mountLabel }],
        note: t('pipeline.file.confirmNote'),
        confirmLabel: t('pipeline.file.confirmAction'),
        confirmIcon: 'check',
        icon: 'folder',
      })
      if (!ok) return
    }

    if (filingRef.current) {
      showToast(t('pipeline.file.busy'), false)
      return
    }
    filingRef.current = true
    setFilingActive(true)

    setRows(prev => prev.map(r => r.id === row.id ? { ...r, running: true, fileProgress: { stage: 'scanning', files_done: 0, files_total: 0, bytes_done: 0, bytes_total: 0, current_file: null } } : r))
    try {
      const startResp = await fetch(`${BASE}/api/pipeline/file/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folders: [{
            path: row.folderPath, lb_number: lb,
            ...(mountId != null && mountId !== row.steps.file.recommended_mount ? { mount_id: mountId } : {}),
          }],
        }),
      })
      const started = await startResp.json() as { ok: boolean; error?: string; error_code?: string }
      if (!started.ok) {
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            running: false,
            fileProgress: null,
            steps: { ...r.steps, file: { ...r.steps.file, status: 'bad', label: (started.error ?? 'Failed').slice(0, 24), error: started.error ?? null, error_code: started.error_code ?? null } },
          } : r
        ))
        return
      }

      // Poll until the background copy/move finishes, updating the progress bar.
      let result: { ok: boolean; dest?: string; filed_to?: string; error?: string; qbt_synced?: boolean; qbt_error?: string | null } | null = null
      while (!result) {
        await new Promise(r => setTimeout(r, 400))
        const statusResp = await fetch(`${BASE}/api/pipeline/file/status`)
        const status = await statusResp.json() as {
          running: boolean; stage: string; path: string | null
          files_done: number; files_total: number; bytes_done: number; bytes_total: number
          current_file: string | null
          result: { ok: boolean; dest?: string; filed_to?: string; error?: string; qbt_synced?: boolean; qbt_error?: string | null } | null
        }
        if (status.path !== null && status.path !== row.folderPath) {
          // _FILE_JOB now belongs to a different job — ours is no longer trackable here.
          result = { ok: false, error: t('pipeline.file.jobMismatch') }
        } else if (status.running) {
          setRows(prev => prev.map(r =>
            r.id === row.id ? {
              ...r,
              fileProgress: {
                stage: status.stage, files_done: status.files_done, files_total: status.files_total,
                bytes_done: status.bytes_done, bytes_total: status.bytes_total, current_file: status.current_file,
              },
            } : r
          ))
        } else {
          result = status.result
        }
      }

      if (result.ok) {
        const filedStep = { status: 'ok' as const, label: 'Filed', dest: result!.dest ?? null, mount_label: result!.filed_to ?? null, error: null, error_code: null }
        setRows(prev => prev.map(r => {
          if (r.id !== row.id) return r
          const updated = { ...r, running: false, fileProgress: null, bucket: 'done' as const, steps: { ...r.steps, file: filedStep } }
          _pipelineCache.set(r.id, { steps: updated.steps, bucket: updated.bucket, errors: updated.errors })
          return updated
        }))
        queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] })
        if (result.qbt_synced) {
          showToast(t('pipeline.file.qbtSynced'), true)
        } else if (result.qbt_error) {
          showToast(t('pipeline.file.qbtSyncFailed', { error: result.qbt_error }), false)
        }
      } else {
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            running: false,
            fileProgress: null,
            steps: { ...r.steps, file: { ...r.steps.file, status: 'bad', label: (result!.error ?? 'Failed').slice(0, 24), error: result!.error ?? null } },
          } : r
        ))
      }
    } catch {
      setRows(prev => prev.map(r => r.id === row.id ? { ...r, running: false, fileProgress: null } : r))
    } finally {
      filingRef.current = false
      setFilingActive(false)
    }
  }, [confirm, t, showToast])

  const applyAllFileable = useCallback(async () => {
    for (const row of fileableRows) await applyFile(row, undefined, undefined, undefined, true)
  }, [fileableRows, applyFile])

  const applySelectedFileable = useCallback(async () => {
    for (const row of selectedFileable) await applyFile(row, undefined, undefined, undefined, true)
  }, [selectedFileable, applyFile])

  // ── Folder picking ───────────────────────────────────────────────────────────
  const handlePickFolders = useCallback(async () => {
    const paths = await window.api.pickFolders()
    if (paths.length) addFolders(paths)
  }, [addFolders])

  const handleRemoveRow = useCallback((id: string) => {
    setRows(prev => prev.filter(r => r.id !== id))
    removeFolders([id])
    _pipelineCache.delete(id)
    setActiveQueue(prev => prev === id ? null : prev)
    if (detailId === id) setDetailId(null)
  }, [removeFolders, detailId])

  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [ctxMenu])

  const handleScanTree = useCallback(async () => {
    const dir = await window.api.pickDir()
    if (!dir) return
    try {
      const resp = await fetch(`${BASE}/api/pipeline/scan-tree`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ root: dir, shallow: true }),
      })
      const data = await resp.json() as { folders?: string[]; error?: string }
      if (data.folders?.length) addFolders(data.folders)
    } catch { /* silent */ }
  }, [addFolders])

  // ── Selection ────────────────────────────────────────────────────────────────
  const toggleSelect = useCallback((id: string, shift: boolean) => {
    setRows(prev => {
      if (shift && lastShiftAnchor) {
        const ids = prev.map(r => r.id)
        const a = ids.indexOf(lastShiftAnchor)
        const b = ids.indexOf(id)
        const lo = Math.min(a, b), hi = Math.max(a, b)
        return prev.map((r, i) => i >= lo && i <= hi ? { ...r, selected: true } : r)
      }
      return prev.map(r => r.id === id ? { ...r, selected: !r.selected } : r)
    })
    setLastShiftAnchor(id)
  }, [lastShiftAnchor])

  const selectAll = useCallback(() => {
    setRows(prev => {
      const visible = new Set(visibleRows.map(r => r.id))
      return prev.map(r => visible.has(r.id) ? { ...r, selected: true } : r)
    })
  }, [visibleRows])

  const clearSelection = useCallback(() => {
    setRows(prev => prev.map(r => ({ ...r, selected: false })))
  }, [])

  // ── Detail panel open/close ──────────────────────────────────────────────────
  const openDetail = useCallback((id: string, stage?: string) => {
    if (detailId === id && !stage) {
      setDetailId(null)
      return
    }
    const row = rows.find(r => r.id === id)
    setDetailId(id)
    setDetailStage(stage ?? (row ? firstActiveStage(row) : 'verify'))
  }, [detailId, rows])

  // ── ⌘A keyboard shortcut ────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'a') {
        e.preventDefault()
        selectAll()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectAll])

  // ── Drag-and-drop ────────────────────────────────────────────────────────────
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true) }
  const onDragLeave = () => setDragOver(false)
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const paths: string[] = []
    for (let i = 0; i < e.dataTransfer.items.length; i++) {
      const item = e.dataTransfer.items[i]
      if (item.kind === 'file') {
        const file = item.getAsFile()
        const ef = file as (File & { path?: string }) | null
        if (ef?.path) paths.push(ef.path)
      }
    }
    if (paths.length) addFolders(paths)
  }, [addFolders])

  // ── Scroll-to when queue rail item clicked ───────────────────────────────────
  const scrollToRow = (id: string) => {
    setActiveQueue(id)
    const idx = flatListRef.current.findIndex(item => item.type === 'row' && item.row.id === id)
    if (idx >= 0) virtualizer.scrollToIndex(idx, { align: 'center' })
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  const hasSelection = selectedRows.length > 0
  const detailRow = detailId ? rows.find(r => r.id === detailId) ?? null : null

  return (
    <div
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* ── Top progress banner ──────────────────────────────────────────────── */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--lbb-border)',
        background: 'linear-gradient(180deg, var(--lbb-accent-soft) 0%, transparent 140%)',
        display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0,
      }}>
        {/* Icon square */}
        <div style={{
          width: 36, height: 36, borderRadius: 9,
          background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 1px 0 rgba(255,255,255,0.18) inset', flex: '0 0 36px',
        }}>
          <Icon name="pipeline" size={18} />
        </div>

        {/* Title block */}
        <div style={{ minWidth: 230 }}>
          <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('pipeline.titleFolders', { count: counts.all })}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginTop: 2 }}>
            {t('pipeline.runHint')}
          </div>
        </div>

        {/* Bucket filter pills — one per non-zero bucket, clicking toggles table filter */}
        <div style={{ display: 'flex', gap: 7, marginLeft: 8 }}>
          {BANNER_BUCKETS.map(({ key, tone }) => counts[key] > 0 && (
            <button
              key={key}
              onClick={() => setFilter(filter === key ? 'all' : key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '3px 10px', borderRadius: 999,
                cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
                background: filter === key ? `var(--lbb-${tone}-bg)` : 'var(--lbb-surface)',
                border: `1px solid ${filter === key ? `var(--lbb-${tone}-bar)` : 'var(--lbb-border2)'}`,
                color: `var(--lbb-${tone}-fg)`,
                fontSize: 11.5, fontWeight: 600,
              }}
            >
              <span style={{
                width: 7, height: 7, borderRadius: '50%',
                background: `var(--lbb-${tone}-bar)`,
              }} />
              {counts[key]} {t(`pipeline.filter.${key}`).toLowerCase()}
            </button>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        {/* Auto-run toggle */}
        <button
          onClick={() => setAutorun(a => !a)}
          title={t('pipeline.autoRunHint')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '5px 10px', borderRadius: 8,
            cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
            background: autorun ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
            border: `1px solid ${autorun ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
            color: autorun ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
            fontSize: 12, fontWeight: 600,
          }}
        >
          <span style={{
            width: 26, height: 15, borderRadius: 999,
            background: autorun ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
            position: 'relative', transition: 'background 120ms',
          }}>
            <span style={{
              position: 'absolute', top: 2,
              left: autorun ? 13 : 2,
              width: 11, height: 11, borderRadius: '50%',
              background: '#fff', transition: 'left 120ms',
            }} />
          </span>
          {t('pipeline.autoRun')}
        </button>

        {/* Auto-rename toggle */}
        <button
          onClick={() => setAutoRename(a => !a)}
          title={t('pipeline.autoRenameHint')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '5px 10px', borderRadius: 8,
            cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
            background: autoRename ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
            border: `1px solid ${autoRename ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
            color: autoRename ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
            fontSize: 12, fontWeight: 600,
          }}
        >
          <span style={{
            width: 26, height: 15, borderRadius: 999,
            background: autoRename ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
            position: 'relative', transition: 'background 120ms',
          }}>
            <span style={{
              position: 'absolute', top: 2,
              left: autoRename ? 13 : 2,
              width: 11, height: 11, borderRadius: '50%',
              background: '#fff', transition: 'left 120ms',
            }} />
          </span>
          {t('pipeline.autoRename')}
        </button>

        {/* Apply all N ready — always visible, disabled when 0 */}
        <Button
          variant="primary"
          size="md"
          icon="check"
          disabled={counts.ready === 0}
          onClick={applyAllReady}
        >
          {t('pipeline.applyAllReady', { count: counts.ready })}
        </Button>

        {/* File all N into collection — only when shelf > 0 */}
        {counts.shelf > 0 && (
          <Button
            variant="primary"
            size="md"
            icon="collection"
            disabled={filingActive}
            onClick={applyAllFileable}
          >
            {t('pipeline.fileAllCollection', { count: counts.shelf })}
          </Button>
        )}
      </div>

      {/* ── Two-pane body ────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '264px 1fr', minHeight: 0 }}>

        {/* ── Folder queue rail ───────────────────────────────────────────────── */}
        <aside style={{
          background: 'var(--lbb-surface)',
          borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid var(--lbb-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
              <span style={{
                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
                letterSpacing: 0.1, textTransform: 'uppercase',
              }}>{t('pipeline.queue.label')}</span>
              <span style={{
                marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600,
                color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums',
              }}>{counts.all}</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <Input
                icon="search"
                placeholder={t('pipeline.queue.filterPlaceholder')}
                size="sm"
                value={queueSearch}
                onChange={e => setQueueSearch(e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px' }}>
            {queueRows.length === 0 && (
              <div style={{
                padding: '16px 8px', textAlign: 'center',
                fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontStyle: 'italic',
              }}>
                {counts.all === 0
                  ? t('pipeline.queue.emptyNoFolders')
                  : t('pipeline.queue.emptyFiltered')}
              </div>
            )}
            {queueRows.map(r => (
              <QueueRow
                key={r.id}
                folder={toFolderRow(r)}
                active={activeQueue === r.id || detailId === r.id}
                onClick={() => {
                  if (!detailRow) scrollToRow(r.id)
                  openDetail(r.id)
                }}
              />
            ))}
          </div>

          <div style={{
            padding: 12, borderTop: '1px solid var(--lbb-border)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}>
            <Button variant="primary" size="sm" icon="folderPlus" block onClick={handlePickFolders}>
              {t('pipeline.queue.addFolders')}
            </Button>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              <Button variant="secondary" size="sm" icon="search" onClick={handleScanTree}>
                {t('pipeline.queue.scanTree')}
              </Button>
              <Button variant="ghost" size="sm" icon="trash"
                onClick={() => { setRows([]); setActiveQueue(null); setDetailId(null); clearFolders(); _pipelineCache.clear() }}>
                {t('common.clear')}
              </Button>
            </div>
            <button
              data-testid="sidebar-quick-lookup"
              onClick={() => navigate('/quicklookup')}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                padding: '8px 10px', borderRadius: 7, cursor: 'pointer',
                fontFamily: 'inherit', textAlign: 'left',
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
                color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600,
              }}
            >
              <Icon name="lookup" size={14} />
              <span style={{ flex: 1 }}>{t('pipeline.queue.quickLookup')}</span>
              <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', fontWeight: 500 }}>{t('pipeline.queue.noFolder')}</span>
            </button>
            <div style={{
              padding: '9px 11px', background: 'var(--lbb-surface2)', borderRadius: 7,
              border: '1px dashed var(--lbb-border2)', fontSize: 'var(--lbb-fs-10-5)',
              color: 'var(--lbb-fg3)', lineHeight: 1.45, display: 'flex', gap: 8, alignItems: 'flex-start',
            }}>
              <Icon name="drop" size={13} style={{ marginTop: 1, flex: '0 0 auto' }} />
              <span>{t('pipeline.queue.dragInfo')}</span>
            </div>
          </div>
        </aside>

        {/* ── Main content area ──────────────────────────────────────────────── */}
        <section style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, position: 'relative' }}>

          {/* Detail view replaces batch table when a folder is open */}
          {detailRow && (
            <DetailPanel
              key={detailRow.id}
              row={detailRow}
              initialStage={detailStage}
              onClose={() => setDetailId(null)}
              onRowRefresh={refreshDetailRow}
              onRun={(id, steps) => runSteps([id], steps)}
              onRename={(customName) => applyRename(detailRow, customName)}
              onFile={(mountId, dest, mountLabel) => applyFile(detailRow, mountId, dest, mountLabel)}
            />
          )}

          {!detailRow && (<>

          {/* Filter bar */}
          <div style={{
            padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 6,
            borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
          }}>
            <div style={{ flex: 1 }} />
            <Input
              icon="filter"
              placeholder={t('pipeline.filter.filterFolders')}
              size="sm"
              value={tableSearch}
              onChange={e => setTableSearch(e.target.value)}
              style={{ width: 240 }}
            />
            <IconButton icon="reveal" title={t('pipeline.queue.openLocation')}
              disabled={!rows.length}
              onClick={() => {
                const first = rows[0]?.folderPath
                if (!first) return
                const parent = first.replace(/[/\\][^/\\]+$/, '')
                window.api.openPath(parent || first)
              }}
            />
          </div>

          {/* Selection bar */}
          {hasSelection && (
            <div style={{
              padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 12,
              borderBottom: '1px solid var(--lbb-border)',
              background: 'var(--lbb-accent-soft)', fontSize: 'var(--lbb-fs-12)', flexShrink: 0,
            }}>
              <span style={{ fontWeight: 600, color: 'var(--lbb-accent-mid)' }}>
                {t('pipeline.selection.selected', { count: selectedRows.length })}
              </span>
              <span style={{ color: 'var(--lbb-fg2)' }}>{t('pipeline.selection.hint')}</span>
              <div style={{ flex: 1 }} />
              <Button size="sm" variant="ghost" onClick={clearSelection}>{t('common.clear')}</Button>
              <Button
                size="sm" variant="secondary" icon="verify"
                onClick={() => runSteps(selectedRows.map(r => r.id), ['verify'])}
              >{t('pipeline.selection.verifySelected')}</Button>
              <Button
                size="sm" variant="secondary" icon="lookup"
                onClick={() => runSteps(selectedRows.map(r => r.id), ['lookup'])}
              >{t('pipeline.selection.lookupSelected')}</Button>
              {selectedReady.length > 0 && (
                <Button size="sm" variant="primary" icon="check" onClick={applySelected}>
                  {t('pipeline.selection.applySelected', { count: selectedReady.length })}
                </Button>
              )}
              {selectedFileable.length > 0 && (
                <Button size="sm" variant="primary" icon="folder" onClick={applySelectedFileable}>
                  {t('pipeline.selection.fileSelected', { count: selectedFileable.length })}
                </Button>
              )}
            </div>
          )}

          {/* Empty state */}
          {rows.length === 0 && (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 14,
              border: dragOver ? '2px dashed var(--lbb-accent-mid)' : '2px dashed transparent',
              borderRadius: 10, margin: 20, transition: 'border-color 0.15s',
            }}>
              <Icon name="folderPlus" size={40} style={{ color: 'var(--lbb-fg3)' }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg)' }}>
                  {t('pipeline.empty.title')}
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
                  {t('pipeline.empty.desc')}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="primary" size="md" icon="folderPlus" onClick={handlePickFolders}>{t('pipeline.queue.addFolders')}</Button>
                <Button variant="secondary" size="md" icon="search" onClick={handleScanTree}>{t('pipeline.queue.scanTree')}</Button>
              </div>
            </div>
          )}

          {/* Virtualized table */}
          {rows.length > 0 && (
            <div ref={tableParentRef} className="pipe-queue-table" style={{ flex: 1, overflow: 'auto', minHeight: 0, position: 'relative' }}>
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 32 }} />
                  <col />
                  <col style={{ width: 340 }} />
                  <col style={{ width: 420 }} />
                  <col style={{ width: 104 }} />
                  <col style={{ width: 160 }} />
                </colgroup>
                <thead>
                  <tr>
                    <th style={{ width: 3, padding: 0 }} />
                    <TH align="center">
                      <input
                        type="checkbox"
                        checked={selectedRows.length === visibleRows.length && visibleRows.length > 0}
                        onChange={e => e.target.checked ? selectAll() : clearSelection()}
                      />
                    </TH>
                    <TH>{t('pipeline.table.folder')}</TH>
                    <TH align="center">{t('pipeline.table.stages')}</TH>
                    <TH align="center">{t('pipeline.table.status')}</TH>
                    <TH align="center">{t('pipeline.table.lb')}</TH>
                    <TH align="right"> </TH>
                  </tr>
                </thead>
                <tbody>
                  {virtualizer.getVirtualItems().length > 0 && (
                    <tr aria-hidden="true">
                      <td colSpan={7} style={{ height: virtualizer.getVirtualItems()[0].start, padding: 0, border: 'none' }} />
                    </tr>
                  )}
                  {virtualizer.getVirtualItems().map(vItem => {
                    const item = flatList[vItem.index]
                    if (!item) return null

                    if (item.type === 'group') {
                      const edgeMap: Record<Bucket, string> = {
                        needs: 'bad', ready: 'warn', running: 'info', shelf: 'mute', done: 'ok', all: 'mute',
                      }
                      return (
                        <GroupRow
                          ref={node => { if (node) node.dataset.index = String(vItem.index); virtualizer.measureElement(node) }}
                          key={`group-${item.label}`}
                          label={item.label}
                          count={item.count}
                          colSpan={6}
                          expanded={!collapsedBuckets.has(item.bucket)}
                          onToggle={() => toggleBucket(item.bucket)}
                          style={{ color: `var(--lbb-${edgeMap[item.bucket] ?? 'mute'}-fg)` }}
                        />
                      )
                    }

                    const r = item.row
                    const edgeMap: Record<Bucket, 'ok'|'warn'|'bad'|'info'|'mute'> = {
                      needs: 'bad', ready: 'warn', running: 'info', shelf: 'mute', done: 'ok', all: 'mute',
                    }
                    const edge = r.running ? 'info' : edgeMap[r.bucket]
                    const lb = r.steps.lookup.lb_number
                    const lbLabel = lb ? `LB-${String(lb).padStart(5, '0')}` : '—'
                    const aliasFrom = r.steps.lookup.alias_resolved_from
                    const isDetailOpen = detailId === r.id

                    return (
                      <TR
                        ref={node => { if (node) node.dataset.index = String(vItem.index); virtualizer.measureElement(node) }}
                        key={r.id}
                        edge={edge}
                        selected={r.selected || isDetailOpen}
                        onClick={() => openDetail(r.id)}
                        onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, id: r.id }) }}
                      >
                        <TD align="center" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={r.selected}
                            onChange={e => toggleSelect(r.id, e.shiftKey)}
                          />
                        </TD>
                        <TD mono style={{
                          color: r.bucket === 'done' ? 'var(--lbb-fg2)' : 'var(--lbb-fg)',
                          whiteSpace: 'normal', overflowWrap: 'anywhere',
                        }}>
                          {r.folderName}
                          {r.running && (
                            <span style={{ marginLeft: 6, fontSize: 'var(--lbb-fs-9)', color: 'var(--lbb-info-fg)', letterSpacing: 1 }}>···</span>
                          )}
                        </TD>
                        <TD onClick={e => e.stopPropagation()}>
                          <StageTracker
                            folder={toFolderRow(r)}
                            stages={DEFAULT_STAGES}
                            currentKey={isDetailOpen ? detailStage : null}
                            onPick={key => openDetail(r.id, key)}
                          />
                        </TD>
                        <TD style={{ whiteSpace: 'normal' }}>
                          {(() => {
                            const st = deriveFolderStatus(r, t)
                            return (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'center' }}>
                                <StatusTag state={st.state} style={{ width: '50%', justifyContent: 'center' }}>{st.label}</StatusTag>
                                {st.reason && (
                                  <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', lineHeight: 1.35 }}>
                                    {st.reason}
                                  </span>
                                )}
                              </div>
                            )
                          })()}
                        </TD>
                        <TD mono align="center" style={{
                          color: r.bucket === 'ready' ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                          fontWeight: r.bucket === 'ready' ? 600 : undefined,
                        }}>
                          {lbLabel}
                          {aliasFrom && aliasFrom.length > 0 && (
                            <span style={{ fontSize: 'var(--lbb-fs-9)', color: 'var(--lbb-fg3)', marginLeft: 4 }}
                              title={t('pipeline.table.resolvedFromAlias', { list: aliasFrom.map(n => `LB-${String(n).padStart(5, '0')}`).join(', ') })}>
                              {t('pipeline.table.aliasBadge')}
                            </span>
                          )}
                        </TD>
                        <TD align="right" onClick={e => e.stopPropagation()}>
                          <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', alignItems: 'center' }}>
                            {r.bucket === 'ready' && (
                              <Button size="sm" variant="primary" icon="check" onClick={() => applyRename(r)}>{t('pipeline.table.apply')}</Button>
                            )}
                            {r.steps.file.status === 'warn' && !!r.steps.file.dest && !r.shelved &&
                             !(['verify', 'lookup', 'lbdir', 'rename'] as const).some(k => r.steps[k].status === 'bad') && (
                              r.running && r.fileProgress ? (
                                <FileProgressBar progress={r.fileProgress} compact />
                              ) : (
                                <Button size="sm" variant="primary" icon="folder" onClick={() => applyFile(r)}>
                                  {t('pipeline.file.action')}
                                </Button>
                              )
                            )}
                            {r.bucket === 'done' && r.steps.file.status === 'ok' && (
                              <Pill tone="ok" soft>{t('pipeline.table.done')}</Pill>
                            )}
                          </div>
                        </TD>
                      </TR>
                    )
                  })}
                  {virtualizer.getVirtualItems().length > 0 && (() => {
                    const last = virtualizer.getVirtualItems()[virtualizer.getVirtualItems().length - 1]
                    const remaining = virtualizer.getTotalSize() - last.end
                    return remaining > 0 ? (
                      <tr aria-hidden="true">
                        <td colSpan={7} style={{ height: remaining, padding: 0, border: 'none' }} />
                      </tr>
                    ) : null
                  })()}
                </tbody>
              </TableShell>
            </div>
          )}

          </>)}
        </section>
      </div>

      <ConfirmHost />

      {toast && (
        <div style={{
          position: 'fixed', bottom: 80, left: '50%', transform: 'translateX(-50%)',
          background: toast.ok ? 'var(--lbb-ok-bar)' : 'var(--lbb-err-bar)',
          color: '#fff', padding: '7px 16px', borderRadius: 6,
          fontSize: 'var(--lbb-fs-12)', fontWeight: 600, zIndex: 9999,
          boxShadow: '0 2px 8px rgba(0,0,0,.2)', pointerEvents: 'none',
          whiteSpace: 'nowrap',
        }}>{toast.msg}</div>
      )}

      {/* ── Right-click context menu ──────────────────────────────────────────── */}
      {ctxMenu && (
        <div
          onMouseDown={e => e.stopPropagation()}
          style={{
            position: 'fixed', top: ctxMenu.y, left: ctxMenu.x, zIndex: 1000,
            background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
            borderRadius: 8, padding: 4, minWidth: 160,
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
          }}
        >
          <button
            onClick={() => {
              setRows(prev => prev.map(r => r.id === ctxMenu.id ? { ...r, bucket: 'shelf', shelved: true } : r))
              setCtxMenu(null)
            }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
              border: 'none', background: 'transparent',
              color: 'var(--lbb-fg)', borderRadius: 5, fontFamily: 'inherit',
            }}
          >{t('pipeline.contextMenu.shelve')}</button>
          {rows.find(r => r.id === ctxMenu.id)?.shelved && (
            <button
              onClick={() => {
                setRows(prev => prev.map(r => {
                  if (r.id !== ctxMenu.id) return r
                  const preFileOk = (['verify', 'lookup', 'lbdir', 'rename'] as const)
                    .every(k => r.steps[k].status === 'ok')
                  const restoredBucket: Bucket = (preFileOk && r.steps.file.status === 'warn') ? 'shelf' : 'needs'
                  return { ...r, shelved: false, bucket: restoredBucket }
                }))
                setCtxMenu(null)
              }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                border: 'none', background: 'transparent',
                color: 'var(--lbb-fg)', borderRadius: 5, fontFamily: 'inherit',
              }}
            >{t('pipeline.contextMenu.unshelve')}</button>
          )}
          <div style={{ height: 1, background: 'var(--lbb-border)', margin: '4px 0' }} />
          <button
            onClick={() => { handleRemoveRow(ctxMenu.id); setCtxMenu(null) }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
              border: 'none', background: 'transparent',
              color: 'var(--lbb-bad, #e05252)', borderRadius: 5, fontFamily: 'inherit',
            }}
          >{t('common.removeFromList')}</button>
        </div>
      )}
    </div>
  )
}
