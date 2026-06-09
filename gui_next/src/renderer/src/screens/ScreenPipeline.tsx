import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import { useFolderQueueStore } from '../lib/folderQueueStore'
import { CheckResult, ReconcileResult, ReconcileProposal, SiteProposal } from '../lib/lbdirStore'
import { useConfirm } from '../components/pipeline/ConfirmDialog'
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
  proposed?: string | null
  alias_resolved_from?: number[] | null
  check?: LbdirCheckSummary | null
  // verify step fields
  total?: number | null
  pass?: number | null
  missing?: number | null
  mismatch?: number | null
  extra?: number | null
  no_checksums?: boolean | null
  // file step fields
  dest?: string | null
  dest_parent?: string | null
  mount_label?: string | null
  year?: number | null
  error?: string | null
  error_code?: string | null
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
    rename: StepResult
    lbdir:  StepResult
    file:   StepResult
  }
  errors: { step: string; message: string }[]
  running: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const MUTE: StepResult = { status: 'mute', label: '—' }

function emptyRow(folderPath: string): PipelineRow {
  const name = folderPath.split(/[/\\]/).pop() ?? folderPath
  return {
    id: folderPath,
    folderName: name,
    folderPath,
    selected: false,
    bucket: 'needs',
    steps: { verify: MUTE, lookup: MUTE, rename: MUTE, lbdir: MUTE, file: MUTE },
    errors: [],
    running: false,
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
    label:       (r.label       as string) ?? '—',
    dest:        (r.dest        as string) ?? null,
    dest_parent: (r.dest_parent as string) ?? null,
    mount_label: (r.mount_label as string) ?? null,
    year:        (r.year        as number) ?? null,
    error:       (r.error       as string) ?? null,
    error_code:  (r.error_code  as string) ?? null,
  }
}

function serverRowToPipeline(sr: Record<string, unknown>): Partial<PipelineRow> {
  const sev = sr.severity as string
  const bucket: Bucket =
    sev === 'attn'  ? 'needs' :
    sev === 'ready' ? 'ready' :
    sev === 'done'  ? 'done'  : 'needs'
  return {
    bucket,
    steps: {
      verify: (sr.verify as StepResult) ?? MUTE,
      lookup: (sr.lookup as StepResult) ?? MUTE,
      rename: (sr.rename as StepResult) ?? MUTE,
      lbdir:  (sr.lbdir  as StepResult) ?? MUTE,
      file:   normalizeFileStep(sr.file),
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
  for (const key of ['verify', 'lookup', 'rename', 'lbdir', 'file'] as const) {
    const s = r.steps[key]
    rawSteps[key] = { state: STATUS_TO_STATE[s.status], label: s.label }
  }
  if (r.running) {
    for (const key of ['verify', 'lookup', 'rename', 'lbdir', 'file']) {
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
  for (const key of ['verify', 'lookup', 'rename', 'lbdir', 'file'] as const) {
    if (r.steps[key].status !== 'ok' && r.steps[key].status !== 'mute') return key
    if (r.steps[key].status === 'mute') return key
  }
  return 'verify'
}

// ── Virtualizer item type ─────────────────────────────────────────────────────

type VItem =
  | { type: 'group'; label: string; count: number; bucket: Bucket }
  | { type: 'row';   row: PipelineRow }

// ── LBDIR state labels ────────────────────────────────────────────────────────

const STATE_LABEL: Record<string, { tone: 'ok'|'bad'|'warn'|'mute'|'info'; label: string }> = {
  pass:            { tone: 'ok',   label: 'Pass' },
  fail:            { tone: 'bad',  label: 'Fail' },
  missing_files:   { tone: 'warn', label: 'Missing files' },
  no_lbdir:        { tone: 'warn', label: 'No lbdir' },
  no_lb:           { tone: 'mute', label: 'No LB#' },
  shntool_missing: { tone: 'warn', label: 'No shntool' },
}

// ── LbdirStageContent ─────────────────────────────────────────────────────────

function LbdirStageContent({ row, onRowRefresh }: {
  row: PipelineRow
  onRowRefresh: (id: string) => void
}): React.JSX.Element {
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
    setBusy(true)
    fetch(`${BASE}/api/lbdir/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: [row.folderPath] }),
    })
      .then(r => r.json())
      .then((d: { results: CheckResult[] }) => { if (d.results?.[0]) setCheckResult(d.results[0]) })
      .catch(() => {})
      .finally(() => setBusy(false))
  }, [row.folderPath])

  const handleReconcile = useCallback(async () => {
    if (!checkResult) return
    setBusy(true)
    try {
      const d = await post('/api/lbdir/reconcile', { folders: [row.folderPath] }) as { results: ReconcileResult[] }
      if (d.results?.[0]) {
        setReconResult(d.results[0])
        setReconSel(new Set(d.results[0].proposals.map((p: ReconcileProposal) => p.disk_rel)))
        setSiteSel(new Set((d.results[0].site_proposals ?? []).map((p: SiteProposal) => p.site_path)))
      }
    } catch { showToast('Reconcile scan failed', false) }
    finally { setBusy(false) }
  }, [checkResult, row.folderPath, post])

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
      showToast('Applied', true)
      setReconResult(null)
      const d2 = await post('/api/lbdir/check', { folders: [row.folderPath] }) as { results: CheckResult[] }
      if (d2.results?.[0]) setCheckResult(d2.results[0])
      onRowRefresh(row.id)
    } catch { showToast('Apply failed', false) }
    finally { setBusy(false) }
  }, [reconResult, reconSel, siteSel, row.folderPath, row.id, post, onRowRefresh])

  const cr = checkResult
  const sl = cr ? (STATE_LABEL[cr.status] ?? { tone: 'mute' as const, label: cr.status }) : null
  const canReconcile = cr !== null && cr.lbdir_found && cr.status !== 'pass' && cr.status !== 'no_lb'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'relative' }}>
      {busy && !cr && (
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center', padding: 24 }}>
          Loading…
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
            {sl && <Pill tone={sl.tone} soft dot={cr.status !== 'pass'}>{sl.label}</Pill>}
            {cr.lbdir_path && (
              <Pill tone="mute" soft style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>
                {cr.lbdir_path.split('/').pop()}
              </Pill>
            )}
            {cr.lbdir_path && (
              <Button variant="ghost" size="sm" icon="reveal"
                onClick={() => window.api.openPath(cr.lbdir_path!)}>
                Open file
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => navigate('/lbdir')}>
              Full LBDIR screen →
            </Button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
            {[
              { l: 'Total',    v: cr.total,    c: undefined },
              { l: 'Pass',     v: cr.pass,     c: cr.pass     > 0 ? 'var(--lbb-ok-fg)'  : 'var(--lbb-fg3)' },
              { l: 'Missing',  v: cr.missing,  c: cr.missing  > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
              { l: 'Mismatch', v: cr.mismatch, c: cr.mismatch > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            ].map((st, i) => (
              <div key={i} style={{ padding: '6px 8px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{st.l}</div>
                <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: st.c ?? 'var(--lbb-fg)' }}>{st.v}</div>
              </div>
            ))}
          </div>

          {cr.status === 'no_lbdir' && (
            <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
              No <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> found. Try scraping the entry from the LBDIR screen.
            </div>
          )}

          {cr.files.length > 0 && (
            <div style={{ borderRadius: 6, border: '1px solid var(--lbb-border)', overflow: 'hidden' }}>
              <div style={{ padding: '6px 10px', background: 'var(--lbb-surface2)', borderBottom: '1px solid var(--lbb-border)',
                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                Files
              </div>
              {cr.files.slice(0, 12).map((f, i) => {
                const edge = f.overall === 'pass' ? 'var(--lbb-ok-bar)' : f.overall === 'missing' ? 'var(--lbb-warn-bar)' : 'var(--lbb-bad-bar)'
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
                    borderTop: i > 0 ? '1px solid var(--lbb-border)' : undefined,
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: 1, background: edge, flexShrink: 0 }} />
                    <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      color: f.overall === 'pass' ? 'var(--lbb-fg2)' : 'var(--lbb-bad-fg)' }}>
                      {f.filename}
                    </span>
                    <Pill tone={f.overall === 'pass' ? 'ok' : f.overall === 'missing' ? 'warn' : 'bad'} soft>
                      {f.overall === 'pass' ? 'Pass' : f.overall === 'missing' ? 'Missing' : 'Fail'}
                    </Pill>
                  </div>
                )
              })}
              {cr.files.length > 12 && (
                <div style={{ padding: '5px 10px', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', borderTop: '1px solid var(--lbb-border)' }}>
                  +{cr.files.length - 12} more — open full LBDIR view for details
                </div>
              )}
            </div>
          )}

          {canReconcile && !reconResult && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Button variant="secondary" size="sm" icon="rename" disabled={busy} onClick={handleReconcile}>
                {busy ? 'Scanning…' : 'Reconcile files…'}
              </Button>
              <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                Match missing files by MD5
              </span>
            </div>
          )}

          {reconResult && (
            <div style={{ borderRadius: 6, border: '1px solid var(--lbb-border)', overflow: 'hidden' }}>
              <div style={{ padding: '8px 12px', background: 'var(--lbb-surface2)', borderBottom: '1px solid var(--lbb-border)',
                display: 'flex', alignItems: 'center', gap: 8 }}>
                <Icon name="rename" size={12} style={{ color: 'var(--lbb-fg3)' }} />
                <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', flex: 1 }}>
                  Reconcile
                </span>
                {reconResult.proposals.length > 0 && (
                  <Pill tone="info" soft>{reconResult.proposals.length} rename{reconResult.proposals.length !== 1 ? 's' : ''}</Pill>
                )}
                {reconResult.unmatched_disk.length > 0 && (
                  <Pill tone="warn" soft>{reconResult.unmatched_disk.length} extras</Pill>
                )}
                <Button variant="ghost" size="sm" disabled={busy} onClick={handleReconcile}>Re-scan</Button>
                <Button variant="primary" size="sm" icon="check" disabled={busy} onClick={handleApply}>Apply</Button>
              </div>

              {reconResult.proposals.length > 0 ? (
                <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <input type="checkbox"
                      checked={reconResult.proposals.every(p => reconSel.has(p.disk_rel))}
                      onChange={e => setReconSel(e.target.checked ? new Set(reconResult.proposals.map(p => p.disk_rel)) : new Set())}
                    />
                    <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>Proposed renames</span>
                  </div>
                  {reconResult.proposals.map((p, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input type="checkbox"
                        checked={reconSel.has(p.disk_rel)}
                        onChange={e => setReconSel(prev => { const n = new Set(prev); e.target.checked ? n.add(p.disk_rel) : n.delete(p.disk_rel); return n })}
                      />
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg2)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.disk_rel}</span>
                      <Icon name="chevRight" size={10} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-ok-fg)', flexShrink: 0, maxWidth: '45%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.lbdir_rel}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ padding: '8px 12px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
                  No rename proposals — missing files could not be matched by MD5.
                </div>
              )}

              {reconResult.unmatched_disk.length > 0 && (
                <div style={{ borderTop: '1px solid var(--lbb-border)', padding: '6px 12px' }}>
                  <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600, marginBottom: 4 }}>
                    Extras → will move to <span style={{ fontFamily: 'var(--lbb-mono)' }}>/extras/</span>
                  </div>
                  {reconResult.unmatched_disk.map((f, i) => (
                    <div key={i} style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-warn-fg)' }}>{f}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {cr.status === 'pass' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--lbb-ok-fg)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>
              <Icon name="check" size={14} />
              All files verified against lbdir
            </div>
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
  const [generating, setGenerating] = useState(false)

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

  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          Verify hasn't run yet.
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['verify'])}>Run verify</Button>
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
            <div style={{ fontSize: 'var(--lbb-fs-13-5)', fontWeight: 700, marginBottom: 4 }}>No checksum sidecar found</div>
            <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', lineHeight: 1.5, marginBottom: 10 }}>
              Audio files are present but there's no <span style={{ fontFamily: 'var(--lbb-mono)' }}>.ffp</span> or <span style={{ fontFamily: 'var(--lbb-mono)' }}>.md5</span> sidecar. Generate checksums to unblock the pipeline.
            </div>
            <Button variant="primary" size="sm" icon="shield" disabled={generating}
              onClick={handleGenerate}>
              {generating ? 'Generating…' : 'Generate FFP + MD5'}
            </Button>
          </div>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          Writes <span style={{ fontFamily: 'var(--lbb-mono)' }}>_mychecksums.ffp</span> and <span style={{ fontFamily: 'var(--lbb-mono)' }}>.md5</span> into the folder — audio files are not modified.
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
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['verify'])}>Re-verify</Button>
      </div>

      {total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6 }}>
          {([
            { l: 'Total',    v: total,    c: undefined },
            { l: 'Pass',     v: pass,     c: pass === total && total > 0 ? 'var(--lbb-ok-fg)' : undefined },
            { l: 'Missing',  v: missing,  c: missing  > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            { l: 'Mismatch', v: mismatch, c: mismatch > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
            { l: 'Extra',    v: extra,    c: extra    > 0 ? 'var(--lbb-info-fg)' : 'var(--lbb-fg3)' },
          ] as { l: string; v: number; c: string | undefined }[]).map(({ l, v, c }) => (
            <div key={l} style={{ padding: '6px 8px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{l}</div>
              <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: c ?? 'var(--lbb-fg)' }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {step.status === 'ok' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--lbb-ok-fg)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>
          <Icon name="check" size={14} />
          All {total} files verified
        </div>
      )}

      {step.status === 'bad' && missing > 0 && (
        <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>
          {missing} file{missing !== 1 ? 's' : ''} in the checksum list are not on disk. Restore the missing files, then re-verify.
        </div>
      )}

      {step.status === 'bad' && mismatch > 0 && (
        <div style={{ padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-bad-fg)' }}>
          {mismatch} file{mismatch !== 1 ? 's' : ''} have mismatched checksums — the audio may be corrupted or modified.
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
  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          Lookup runs automatically after verify passes.
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['lookup'])}>Run lookup</Button>
      </div>
    )
  }

  const lbFormatted = step.lb_number
    ? `LB-${String(step.lb_number).padStart(5, '0')}`
    : null

  if (step.status === 'ok' && lbFormatted) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)', borderRadius: 8 }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, background: 'var(--lbb-ok-bar)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Icon name="check" size={22} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-accent-mid)' }}>{lbFormatted}</div>
            {step.alias_resolved_from && step.alias_resolved_from.length > 0 && (
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
                ↩ resolved from {step.alias_resolved_from.map(n => `LB-${String(n).padStart(5, '0')}`).join(', ')}
              </div>
            )}
          </div>
          <StatusTag state="pass">Matched</StatusTag>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          The match flows into <strong>Rename</strong> automatically — no extra step needed.
        </div>
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['lookup'])}>Re-run lookup</Button>
      </div>
    )
  }

  if (step.status === 'warn') {
    const conflicts = row.errors.filter(e => e.step === 'lookup')
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <StatusTag state="action">{step.label}</StatusTag>
        {conflicts.length > 0 && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--lbb-warn-bg)', border: '1px solid var(--lbb-warn-bar)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-warn-fg)' }}>
            {conflicts[0].message}
          </div>
        )}
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['lookup'])}>Re-run lookup</Button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-bar)', borderRadius: 8 }}>
        <Icon name="alert" size={15} style={{ color: 'var(--lbb-bad-fg)', flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-bad-fg)' }}>Not in the archive</div>
          <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', marginTop: 2 }}>
            None of these checksums match any archive entry. This may be a new or unknown source.
          </div>
        </div>
      </div>
      <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['lookup'])}>Re-run lookup</Button>
    </div>
  )
}

function RenameStageContent({ step, row, onRun, onRename }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
  onRename: () => void
}): React.JSX.Element {
  if (step.status === 'mute') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
          Rename unlocks after lookup resolves an LB#.
        </div>
        <Button variant="secondary" size="sm" icon="play" onClick={() => onRun(['rename'])}>Check rename</Button>
      </div>
    )
  }

  if (step.status === 'ok' || !step.proposed) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--lbb-ok-fg)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>
          <Icon name="check" size={14} />
          Folder name is already correct
        </div>
        <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', padding: '8px 10px', background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.folderName}
        </div>
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['rename'])}>Re-check</Button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--lbb-bad-bg)' }}>
          <Icon name="x" size={13} style={{ color: 'var(--lbb-bad-fg)', flexShrink: 0 }} />
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.folderName}</span>
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-bad-fg)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>current</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--lbb-ok-bg)', borderTop: '1px solid var(--lbb-border)' }}>
          <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)', flexShrink: 0 }} />
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)', fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{step.proposed}</span>
          <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-ok-fg)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>proposed</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button variant="primary" size="sm" icon="check" onClick={onRename}>Apply rename</Button>
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['rename'])}>Re-check</Button>
      </div>
      <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
        Logged to <span style={{ fontFamily: 'var(--lbb-mono)' }}>rename_history</span> — reversible for 30 days.
      </div>
    </div>
  )
}

function CollectStageContent({ step, row, onRun, onFile }: {
  step: StepResult
  row: PipelineRow
  onRun: (steps: string[]) => void
  onFile?: () => void
}): React.JSX.Element {
  const ERROR_MSG: Record<string, string> = {
    no_date:       "This entry has no concert date — can't determine the year for routing.",
    no_route:      'No collection route is configured for this year. Add one in Setup → Collection Routing.',
    mount_offline: 'The storage mount is offline or unreachable.',
    dest_exists:   'A folder with this name already exists at the destination.',
    db_error:      'A database error occurred while resolving the route.',
  }

  if (step.status === 'ok') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--lbb-ok-bg)', border: '1px solid var(--lbb-ok-bar)', borderRadius: 9 }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, flexShrink: 0, background: 'var(--lbb-ok-bar)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="check" size={22} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700 }}>Added to collection</div>
            {step.dest && (
              <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{step.dest}</div>
            )}
          </div>
          {step.mount_label && <Pill tone="ok" soft dot>{step.mount_label}</Pill>}
        </div>
        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          Logged to <span style={{ fontFamily: 'var(--lbb-mono)' }}>rename_history</span> — reversible for 30 days.
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
            <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-bad-fg)' }}>Can't file</span>
            {step.error_code && (
              <Pill tone="bad" soft style={{ fontFamily: 'var(--lbb-mono)', marginLeft: 'auto' }}>{step.error_code}</Pill>
            )}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>{msg ?? 'Unknown error'}</div>
        </div>
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['file'])}>Re-check route</Button>
      </div>
    )
  }

  if (step.status === 'warn') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 9, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--lbb-surface)' }}>
            <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.folderPath}</span>
            <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>staging</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '3px 0', background: 'var(--lbb-surface)' }}>
            <Icon name="drop" size={13} style={{ color: 'var(--lbb-accent-mid)' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'var(--lbb-accent-soft)', borderTop: '1px solid var(--lbb-border)' }}>
            <Icon name="folder" size={13} style={{ color: 'var(--lbb-accent-mid)', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {step.mount_label && (
                <mark style={{ background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)', borderRadius: 3, padding: '1px 4px', marginRight: 4 }}>{step.mount_label}</mark>
              )}
              {step.dest ?? '—'}
            </span>
            <span style={{ fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-accent-mid)', textTransform: 'uppercase', letterSpacing: 0.06, flexShrink: 0 }}>final storage</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="primary" size="sm" icon="folder" onClick={onFile}>File into collection</Button>
          <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['file'])}>Re-check route</Button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontStyle: 'italic' }}>
        Filing is the last step. Complete verify, lookup, rename, and LBDIR first.
      </div>
      <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun(['file'])}>Check route now</Button>
    </div>
  )
}

function StageContent({ step, stageKey, row, onRun, onRename, onFile }: {
  step: StepResult
  stageKey: string
  row: PipelineRow
  onRun: (steps: string[]) => void
  onRename: () => void
  onFile?: () => void
}): React.JSX.Element {
  if (stageKey === 'verify')  return <VerifyStageContent  step={step} row={row} onRun={onRun} />
  if (stageKey === 'lookup')  return <LookupStageContent  step={step} row={row} onRun={onRun} />
  if (stageKey === 'rename')  return <RenameStageContent  step={step} row={row} onRun={onRun} onRename={onRename} />
  if (stageKey === 'file')    return <CollectStageContent step={step} row={row} onRun={onRun} onFile={onFile} />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <StatusTag state={STATUS_TO_STATE[step.status]}>{step.label}</StatusTag>
      <Button variant="ghost" size="sm" icon="refresh" onClick={() => onRun([stageKey])}>Re-run</Button>
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
  onRename: () => void
  onFile?: () => void
}): React.JSX.Element {
  const [activeStage, setActiveStage] = useState(initialStage)
  const folderRow = toFolderRow(row)

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, bottom: 0, width: 460,
      background: 'var(--lbb-bg)', borderLeft: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', zIndex: 50,
      boxShadow: '-4px 0 20px rgba(0,0,0,0.12)',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
      }}>
        <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{
          fontWeight: 600, fontSize: 'var(--lbb-fs-12)', flex: 1, minWidth: 0,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'var(--lbb-mono)',
        }}>
          {row.folderName}
        </span>
        <Button variant="ghost" size="sm" icon="reveal"
          onClick={() => window.api.openPath(row.folderPath)}>
          Open
        </Button>
        <IconButton icon="x" title="Close" onClick={onClose} />
      </div>

      {/* Stage stepper */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <StageStepper
          folder={folderRow}
          stages={DEFAULT_STAGES}
          activeKey={activeStage}
          onPick={setActiveStage}
        />
      </div>

      {/* Stage content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px' }}>
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
  const { folders: queueFolders, addFolders: addToQueue, removeFolders, clearFolders } = useFolderQueueStore()

  const [rows, setRows]                     = useState<PipelineRow[]>([])
  const [filter, setFilter]                 = useState<Bucket>('all')
  const [tableSearch, setTableSearch]       = useState('')
  const [queueSearch, setQueueSearch]       = useState('')
  const [activeQueue, setActiveQueue]       = useState<string | null>(null)
  const [lastShiftAnchor, setLastShiftAnchor] = useState<string | null>(null)
  const [dragOver, setDragOver]             = useState(false)
  const [shallowScan, setShallowScan]       = useState(false)
  const [ctxMenu, setCtxMenu]               = useState<{ x: number; y: number; id: string } | null>(null)
  const [detailId, setDetailId]             = useState<string | null>(null)
  const [detailStage, setDetailStage]       = useState<string>('verify')
  const [confirm, ConfirmHost]              = useConfirm()

  // Sync shared folder queue → local rows
  useEffect(() => {
    setRows(prev => {
      const queueSet = new Set(queueFolders)
      const kept = prev.filter(r => queueSet.has(r.id))
      const existingIds = new Set(kept.map(r => r.id))
      const added = queueFolders.filter(p => !existingIds.has(p)).map(emptyRow)
      if (kept.length === prev.length && !added.length) return prev
      return [...kept, ...added]
    })
  }, [queueFolders])

  const tableParentRef = useRef<HTMLDivElement>(null)
  const flatListRef    = useRef<VItem[]>([])
  const stopRef        = useRef(false)
  const abortRef       = useRef<AbortController | null>(null)
  const bulkMenuRef    = useRef<HTMLDivElement>(null)
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false)

  // ── Derived counts ───────────────────────────────────────────────────────────
  const counts = {
    all:     rows.length,
    needs:   rows.filter(r => !r.running && r.bucket === 'needs').length,
    ready:   rows.filter(r => !r.running && r.bucket === 'ready').length,
    running: rows.filter(r => r.running).length,
    shelf:   rows.filter(r => r.bucket === 'shelf').length,
    done:    rows.filter(r => !r.running && r.bucket === 'done').length,
  }

  const isRunning       = rows.some(r => r.running)
  const selectedRows    = rows.filter(r => r.selected)
  const selectedReady   = selectedRows.filter(r => r.bucket === 'ready')
  const fileableRows    = rows.filter(r => r.steps.file.status === 'warn' && !!r.steps.file.dest)
  const selectedFileable = selectedRows.filter(r => r.steps.file.status === 'warn' && !!r.steps.file.dest)

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
  const shelfVis   = visibleRows.filter(r => r.bucket === 'shelf')
  const doneVis    = visibleRows.filter(r => !r.running && r.bucket === 'done')

  // ── Virtualizer flat list ────────────────────────────────────────────────────
  const flatList: VItem[] = []
  if (needsVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.needs'), count: counts.needs, bucket: 'needs' })
    needsVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (runningVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.running'), count: counts.running, bucket: 'running' })
    runningVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (readyVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.ready'), count: counts.ready, bucket: 'ready' })
    readyVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (shelfVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.shelf'), count: counts.shelf, bucket: 'shelf' })
    shelfVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (doneVis.length > 0) {
    flatList.push({ type: 'group', label: t('pipeline.filter.done'), count: counts.done, bucket: 'done' })
    doneVis.forEach(r => flatList.push({ type: 'row', row: r }))
  }

  flatListRef.current = flatList

  const virtualizer = useVirtualizer({
    count: flatList.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: () => 38,
    overscan: 12,
  })

  // ── Queue rail filtered list ─────────────────────────────────────────────────
  const queueRows = queueSearch
    ? rows.filter(r => r.folderName.toLowerCase().includes(queueSearch.toLowerCase()))
    : rows

  // ── Row mutation helpers ─────────────────────────────────────────────────────
  const updateRow = useCallback((id: string, patch: Partial<PipelineRow>) => {
    setRows(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r))
  }, [])

  const addFolders = useCallback((paths: string[]) => {
    addToQueue(paths)
    setRows(prev => {
      const existing = new Set(prev.map(r => r.id))
      const newRows = paths.filter(p => !existing.has(p)).map(emptyRow)
      return [...prev, ...newRows]
    })
  }, [addToQueue])

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
          if (data.results[0]) updateRow(target.id, serverRowToPipeline(data.results[0]))
          else updateRow(target.id, { running: false })
        } else {
          updateRow(target.id, { running: false })
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') updateRow(target.id, { running: false })
      }
    }
    abortRef.current = null
  }, [rows, updateRow])

  const stopRun = useCallback(() => {
    stopRef.current = true
    abortRef.current?.abort()
    abortRef.current = null
    setRows(prev => prev.map(r => r.running ? { ...r, running: false } : r))
  }, [])

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
        if (data.results[0]) updateRow(id, serverRowToPipeline(data.results[0]))
      }
    } catch { /* silent */ }
  }, [rows, updateRow])

  // ── Apply a single rename ────────────────────────────────────────────────────
  const applyRename = useCallback(async (row: PipelineRow) => {
    const proposed = row.steps.rename.proposed
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
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            folderPath: data.new_path!,
            folderName: newName,
            id: data.new_path!,
            bucket: 'done',
            steps: { ...r.steps, rename: { status: 'ok', label: 'Renamed' } },
          } : r
        ))
        useFolderQueueStore.getState().removeFolders([row.folderPath])
        useFolderQueueStore.getState().addFolders([data.new_path])
      }
    } catch { /* silent */ }
  }, [detailId])

  const applyAllReady = useCallback(async () => {
    const readyRows = rows.filter(r => r.bucket === 'ready')
    for (const row of readyRows) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [rows, applyRename])

  const applySelected = useCallback(async () => {
    for (const row of selectedReady) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [selectedReady, applyRename])

  // ── File a folder into the collection ────────────────────────────────────────
  const applyFile = useCallback(async (row: PipelineRow) => {
    const lb = row.steps.lookup.lb_number
    const dest = row.steps.file.dest
    if (!lb || !dest) return

    const mountLabel = row.steps.file.mount_label ?? 'collection mount'
    const destName = dest.split(/[/\\]/).pop() ?? dest

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

    setRows(prev => prev.map(r => r.id === row.id ? { ...r, running: true } : r))
    try {
      const resp = await fetch(`${BASE}/api/pipeline/file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [{ path: row.folderPath, lb_number: lb }] }),
      })
      const data = await resp.json() as { results: Array<{ ok: boolean; dest?: string; filed_to?: string; error?: string }> }
      const result = data.results?.[0]
      if (result?.ok) {
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            running: false,
            bucket: 'done',
            steps: { ...r.steps, file: { status: 'ok', label: 'Filed', dest: result.dest ?? null, mount_label: result.filed_to ?? null, error: null, error_code: null } },
          } : r
        ))
      } else {
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            running: false,
            steps: { ...r.steps, file: { ...r.steps.file, status: 'bad', label: (result?.error ?? 'Failed').slice(0, 24), error: result?.error ?? null } },
          } : r
        ))
      }
    } catch {
      setRows(prev => prev.map(r => r.id === row.id ? { ...r, running: false } : r))
    }
  }, [confirm, t])

  const applyAllFileable = useCallback(async () => {
    for (const row of fileableRows) await applyFile(row)
  }, [fileableRows, applyFile])

  const applySelectedFileable = useCallback(async () => {
    for (const row of selectedFileable) await applyFile(row)
  }, [selectedFileable, applyFile])

  // ── Folder picking ───────────────────────────────────────────────────────────
  const handlePickFolders = useCallback(async () => {
    const paths = await window.api.pickFolders()
    if (paths.length) addFolders(paths)
  }, [addFolders])

  const handleAddSingleFolder = useCallback(async () => {
    const path = await window.api.pickDir()
    if (path) addFolders([path])
  }, [addFolders])

  const handleRemoveRow = useCallback((id: string) => {
    setRows(prev => prev.filter(r => r.id !== id))
    removeFolders([id])
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
        body: JSON.stringify({ root: dir, shallow: shallowScan }),
      })
      const data = await resp.json() as { folders?: string[]; error?: string }
      if (data.folders?.length) addFolders(data.folders)
    } catch { /* silent */ }
  }, [addFolders, shallowScan])

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

  // ── Bulk-actions menu close on outside click ─────────────────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (bulkMenuRef.current && !bulkMenuRef.current.contains(e.target as Node))
        setBulkMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

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
        display: 'flex', alignItems: 'center', gap: 18, flexShrink: 0,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 9,
          background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 1px 0 rgba(255,255,255,0.18) inset', flexShrink: 0,
        }}>
          <Icon name="pipeline" size={18} />
        </div>

        <div style={{ minWidth: 260 }}>
          <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('pipeline.title')}{counts.all > 0 ? ` ${t('pipeline.folderQueued', { count: counts.all })}` : ''}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginTop: 2 }}>
            {counts.all === 0 ? t('pipeline.emptyHint') : t('pipeline.runHint')}
          </div>
        </div>

        {counts.all > 0 && (
          <div style={{ display: 'flex', gap: 8, marginLeft: 12 }}>
            <Pill tone="ok"   soft dot>{t('pipeline.done',          { count: counts.done })}</Pill>
            <Pill tone="warn" soft dot>{t('pipeline.readyToRename', { count: counts.ready })}</Pill>
            <Pill tone="bad"  soft dot>{t('pipeline.needAttention', { count: counts.needs })}</Pill>
          </div>
        )}

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isRunning ? (
            <Button variant="secondary" size="md" icon="x" onClick={stopRun}>{t('pipeline.stop')}</Button>
          ) : (
            <div ref={bulkMenuRef} style={{ position: 'relative' }}>
              <Button variant="ghost" size="md" icon="more" onClick={() => setBulkMenuOpen(v => !v)}>
                {t('pipeline.bulkActions')}
              </Button>
              {bulkMenuOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 4px)', right: 0, zIndex: 100,
                  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                  borderRadius: 8, padding: 4, minWidth: 180,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
                }}>
                  {([
                    { label: t('pipeline.selectAllVisible'), action: () => { selectAll(); setBulkMenuOpen(false) }, color: undefined },
                    ...(selectedRows.length > 0 ? [{ label: t('pipeline.clearSelection', { count: selectedRows.length }), action: () => { clearSelection(); setBulkMenuOpen(false) }, color: undefined }] : []),
                  ]).map((item, i) => (
                    <button key={i} onClick={item.action} style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                      border: 'none', background: 'transparent',
                      color: item.color ?? 'var(--lbb-fg)', borderRadius: 5,
                    }}>{item.label}</button>
                  ))}
                  <div style={{ height: 1, background: 'var(--lbb-border)', margin: '4px 0' }} />
                  <button
                    onClick={() => { setRows([]); setActiveQueue(null); setDetailId(null); clearFolders(); setBulkMenuOpen(false) }}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                      border: 'none', background: 'transparent',
                      color: 'var(--lbb-bad, #e05252)', borderRadius: 5,
                    }}
                  >{t('pipeline.clearQueue')}</button>
                </div>
              )}
            </div>
          )}
          {counts.ready > 0 && !isRunning && (
            <Button variant="primary" size="md" icon="check" onClick={applyAllReady}>
              {t('pipeline.applyRenames', { count: counts.ready })}
            </Button>
          )}
          {fileableRows.length > 0 && !isRunning && (
            <Button variant="primary" size="md" icon="folder" onClick={applyAllFileable}>
              {t('pipeline.fileAllReady', { count: fileableRows.length })}
            </Button>
          )}
        </div>
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
                  scrollToRow(r.id)
                  openDetail(r.id)
                }}
              />
            ))}
          </div>

          <div style={{
            padding: 12, borderTop: '1px solid var(--lbb-border)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}>
            <Button variant="primary" size="sm" icon="folderPlus" block onClick={handlePickFolders}>{t('pipeline.queue.addFolders')}</Button>
            <Button variant="secondary" size="sm" icon="folder" block onClick={handleAddSingleFolder}>{t('common.addFolder')}</Button>
            <Button variant="secondary" size="sm" icon="search" block onClick={handleScanTree}>{t('pipeline.queue.scanTree')}</Button>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', cursor: 'pointer', paddingLeft: 2 }}>
              <input type="checkbox" checked={shallowScan} onChange={e => setShallowScan(e.target.checked)} style={{ accentColor: 'var(--lbb-accent)' }} />
              {t('common.shallowScan')}
            </label>
            <Button
              variant="ghost" size="sm" icon="trash" block
              onClick={() => { setRows([]); setActiveQueue(null); setDetailId(null); clearFolders() }}
            >{t('common.clearList')}</Button>

            <div style={{
              marginTop: 10, padding: '8px 10px',
              background: 'var(--lbb-surface2)', borderRadius: 6,
              border: '1px solid var(--lbb-border)',
            }}>
              <div style={{
                fontSize: 'var(--lbb-fs-10)', fontWeight: 700, color: 'var(--lbb-fg3)',
                letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 6,
              }}>
                {t('pipeline.queue.runOnSelected', { count: counts.all })}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <Button
                  variant="primary" size="sm" icon="play" block
                  onClick={() => runSteps(rows.map(r => r.id), ['verify', 'lookup', 'rename', 'lbdir', 'file'])}
                >{t('pipeline.queue.runAll')}</Button>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['verify'])}>{t('pipeline.queue.verify')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['lookup'])}>{t('pipeline.queue.lookup')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['rename'])}>{t('pipeline.queue.rename')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['lbdir'])}>{t('pipeline.queue.lbdir')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['file'])}>{t('pipeline.queue.collect')}</Button>
                </div>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main table area ─────────────────────────────────────────────────── */}
        <section style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, position: 'relative' }}>

          {/* Bucket filter bar */}
          <div style={{
            padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 6,
            borderBottom: '1px solid var(--lbb-border)', flexWrap: 'wrap', flexShrink: 0,
          }}>
            <Chip active={filter === 'all'}     onClick={() => setFilter('all')}     count={counts.all}>{t('pipeline.filter.all')}</Chip>
            <Chip active={filter === 'needs'}   onClick={() => setFilter('needs')}   count={counts.needs}>{t('pipeline.filter.needs')}</Chip>
            <Chip active={filter === 'ready'}   onClick={() => setFilter('ready')}   count={counts.ready}>{t('pipeline.filter.ready')}</Chip>
            {counts.running > 0 && (
              <Chip active={filter === 'running'} onClick={() => setFilter('running')} count={counts.running}>{t('pipeline.filter.running')}</Chip>
            )}
            {counts.shelf > 0 && (
              <Chip active={filter === 'shelf'}   onClick={() => setFilter('shelf')}   count={counts.shelf}>{t('pipeline.filter.shelf')}</Chip>
            )}
            <Chip active={filter === 'done'}    onClick={() => setFilter('done')}    count={counts.done}>{t('pipeline.filter.done')}</Chip>
            <div style={{ flex: 1 }} />
            <Input
              icon="filter"
              placeholder={t('pipeline.filter.filterFolders')}
              size="sm"
              value={tableSearch}
              onChange={e => setTableSearch(e.target.value)}
              style={{ width: 240 }}
            />
            <IconButton icon="reveal" title="Open queue location"
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
            <div ref={tableParentRef} style={{ flex: 1, overflow: 'auto', minHeight: 0, position: 'relative' }}>
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 32 }} />
                  <col />
                  <col style={{ width: 220 }} />
                  <col style={{ width: 120 }} />
                  <col style={{ width: 120 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH>
                      <input
                        type="checkbox"
                        checked={selectedRows.length === visibleRows.length && visibleRows.length > 0}
                        onChange={e => e.target.checked ? selectAll() : clearSelection()}
                      />
                    </TH>
                    <TH>{t('pipeline.table.folder')}</TH>
                    <TH>Stages</TH>
                    <TH>{t('pipeline.table.lb')}</TH>
                    <TH align="right"> </TH>
                  </tr>
                </thead>
                <tbody>
                  {virtualizer.getVirtualItems().length > 0 && (
                    <tr aria-hidden="true">
                      <td colSpan={6} style={{ height: virtualizer.getVirtualItems()[0].start, padding: 0, border: 'none' }} />
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
                          key={`group-${item.label}`}
                          label={item.label}
                          count={item.count}
                          colSpan={5}
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
                        key={r.id}
                        edge={edge}
                        selected={r.selected || isDetailOpen}
                        onClick={() => openDetail(r.id)}
                        onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, id: r.id }) }}
                      >
                        <TD onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={r.selected}
                            onChange={e => toggleSelect(r.id, e.shiftKey)}
                          />
                        </TD>
                        <TD mono style={{ color: r.bucket === 'done' ? 'var(--lbb-fg2)' : 'var(--lbb-fg)' }}>
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
                        <TD mono style={{
                          color: r.bucket === 'ready' ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                          fontWeight: r.bucket === 'ready' ? 600 : undefined,
                        }}>
                          {lbLabel}
                          {aliasFrom && aliasFrom.length > 0 && (
                            <span style={{ fontSize: 'var(--lbb-fs-9)', color: 'var(--lbb-fg3)', marginLeft: 4 }}
                              title={`Resolved from alias: ${aliasFrom.map(n => `LB-${String(n).padStart(5, '0')}`).join(', ')}`}>
                              ↩ alias
                            </span>
                          )}
                        </TD>
                        <TD align="right" onClick={e => e.stopPropagation()}>
                          <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', alignItems: 'center' }}>
                            {r.bucket === 'ready' && (
                              <Button size="sm" variant="primary" icon="check" onClick={() => applyRename(r)}>Apply</Button>
                            )}
                            {r.steps.file.status === 'warn' && !!r.steps.file.dest && (
                              <Button size="sm" variant="primary" icon="folder" onClick={() => applyFile(r)}>
                                {t('pipeline.file.action')}
                              </Button>
                            )}
                            {r.bucket === 'done' && r.steps.file.status === 'ok' && (
                              <Pill tone="ok" soft>Done</Pill>
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
                        <td colSpan={6} style={{ height: remaining, padding: 0, border: 'none' }} />
                      </tr>
                    ) : null
                  })()}
                </tbody>
              </TableShell>
            </div>
          )}

          {/* ── Detail panel (slide-in on row click) ──────────────────────────── */}
          {detailRow && (
            <DetailPanel
              key={detailRow.id}
              row={detailRow}
              initialStage={detailStage}
              onClose={() => setDetailId(null)}
              onRowRefresh={refreshDetailRow}
              onRun={(id, steps) => runSteps([id], steps)}
              onRename={() => applyRename(detailRow)}
              onFile={() => applyFile(detailRow)}
            />
          )}
        </section>
      </div>

      <ConfirmHost />

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
              setRows(prev => prev.map(r => r.id === ctxMenu.id ? { ...r, bucket: 'shelf' } : r))
              setCtxMenu(null)
            }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
              border: 'none', background: 'transparent',
              color: 'var(--lbb-fg)', borderRadius: 5, fontFamily: 'inherit',
            }}
          >Shelve (skip for now)</button>
          {rows.find(r => r.id === ctxMenu.id)?.bucket === 'shelf' && (
            <button
              onClick={() => {
                setRows(prev => prev.map(r => r.id === ctxMenu.id ? { ...r, bucket: 'needs' } : r))
                setCtxMenu(null)
              }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                border: 'none', background: 'transparent',
                color: 'var(--lbb-fg)', borderRadius: 5, fontFamily: 'inherit',
              }}
            >Unshelve</button>
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
