import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import { useFolderQueueStore } from '../lib/folderQueueStore'
import { CheckResult, ReconcileResult, ReconcileProposal, SiteProposal } from '../lib/lbdirStore'

const BASE = window.api.flaskBase

// ── Types ────────────────────────────────────────────────────────────────────

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
  check?: LbdirCheckSummary | null  // only populated for lbdir step
}

interface PipelineRow {
  id: string                          // folderPath used as stable key
  folderName: string
  folderPath: string
  selected: boolean
  severity: 'attn' | 'ready' | 'done'
  steps: {
    verify: StepResult
    lookup: StepResult
    rename: StepResult
    lbdir:  StepResult
  }
  errors: { step: string; message: string }[]
  running: boolean
}

type FilterKey = 'all' | 'attn' | 'ready' | 'done'

// ── StepPill ─────────────────────────────────────────────────────────────────

function StepPill({ step, running = false }: { step: StepResult; running?: boolean }): React.JSX.Element {
  if (running && step.status === 'mute') {
    return (
      <Pill tone="mute" soft style={{ minWidth: 64, justifyContent: 'center', opacity: 0.5, letterSpacing: 3 }}>···</Pill>
    )
  }
  if (step.status === 'mute') {
    return (
      <Pill tone="mute" soft style={{ minWidth: 64, justifyContent: 'center' }}>—</Pill>
    )
  }
  return (
    <Pill tone={step.status} soft dot style={{ minWidth: 64, justifyContent: 'center' }}>
      {step.label}
    </Pill>
  )
}

// ── Numbered step header ──────────────────────────────────────────────────────

function StepTH({ n, label }: { n: number; label: string }): React.JSX.Element {
  return (
    <TH align="center">
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <span style={{
          width: 14, height: 14, borderRadius: '50%',
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 'var(--lbb-fs-9)', fontWeight: 700, color: 'var(--lbb-fg2)',
        }}>{n}</span>
        {label}
      </span>
    </TH>
  )
}

// ── Virtualizer item type ─────────────────────────────────────────────────────

type VItem =
  | { type: 'group'; label: string; count: number; severity: string }
  | { type: 'row';   row: PipelineRow }

// ── Helpers ───────────────────────────────────────────────────────────────────

const MUTE: StepResult = { status: 'mute', label: '—' }

function emptyRow(folderPath: string): PipelineRow {
  const name = folderPath.split(/[/\\]/).pop() ?? folderPath
  return {
    id: folderPath,
    folderName: name,
    folderPath,
    selected: false,
    severity: 'attn',
    steps: { verify: MUTE, lookup: MUTE, rename: MUTE, lbdir: MUTE },
    errors: [],
    running: false,
  }
}

function serverRowToPipeline(sr: Record<string, unknown>): Partial<PipelineRow> {
  return {
    severity: sr.severity as PipelineRow['severity'],
    steps: {
      verify: (sr.verify as StepResult) ?? MUTE,
      lookup: (sr.lookup as StepResult) ?? MUTE,
      rename: (sr.rename as StepResult) ?? MUTE,
      lbdir:  (sr.lbdir  as StepResult) ?? MUTE,
    },
    errors: (sr.errors as PipelineRow['errors']) ?? [],
    running: false,
  }
}

// ── LBDIR Mini Panel ─────────────────────────────────────────────────────────

const STATE_LABEL: Record<string, { tone: 'ok'|'bad'|'warn'|'mute'|'info'; label: string }> = {
  pass:            { tone: 'ok',   label: 'Pass' },
  fail:            { tone: 'bad',  label: 'Fail' },
  missing_files:   { tone: 'warn', label: 'Missing files' },
  no_lbdir:        { tone: 'warn', label: 'No lbdir' },
  no_lb:           { tone: 'mute', label: 'No LB#' },
  shntool_missing: { tone: 'warn', label: 'No shntool' },
}

function LbdirMiniPanel({ row, onClose, onRowRefresh }: {
  row: PipelineRow
  onClose: () => void
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

  // Fetch check result when panel opens
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
      // Re-check after apply
      const d2 = await post('/api/lbdir/check', { folders: [row.folderPath] }) as { results: CheckResult[] }
      if (d2.results?.[0]) setCheckResult(d2.results[0])
      // Tell pipeline to re-run lbdir step on this row so the pill updates
      onRowRefresh(row.id)
    } catch { showToast('Apply failed', false) }
    finally { setBusy(false) }
  }, [reconResult, reconSel, siteSel, row.folderPath, row.id, post, onRowRefresh])

  const cr = checkResult
  const sl = cr ? (STATE_LABEL[cr.status] ?? { tone: 'mute' as const, label: cr.status }) : null
  const canReconcile = cr !== null && cr.lbdir_found && cr.status !== 'pass' && cr.status !== 'no_lb'

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, bottom: 0, width: 420,
      background: 'var(--lbb-bg)', borderLeft: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', zIndex: 50,
      boxShadow: '-4px 0 20px rgba(0,0,0,0.12)',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
      }}>
        <Icon name="lbdir" size={15} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{ fontWeight: 600, fontSize: 'var(--lbb-fs-11)', flex: 1, minWidth: 0,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'var(--lbb-mono)' }}>
          {row.folderName}
        </span>
        <Button variant="ghost" size="sm" onClick={() => { navigate('/lbdir') }}>Open full LBDIR →</Button>
        <IconButton icon="x" title="Close" onClick={onClose} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {busy && !cr && (
          <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center', padding: 24 }}>
            Loading…
          </div>
        )}

        {cr && (
          <>
            {/* Status + LB# */}
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
            </div>

            {/* Stats */}
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

            {/* no_lbdir hint */}
            {cr.status === 'no_lbdir' && (
              <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
                No <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> found. The retrieve step ran but
                no cached file was available — try scraping the entry from the LBDIR screen.
              </div>
            )}

            {/* File list (truncated) */}
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

            {/* Reconcile section */}
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
      </div>

      {toast && (
        <div style={{
          position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
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

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenPipeline(): React.JSX.Element {
  const { t } = useTranslation()
  const { folders: queueFolders, addFolders: addToQueue, removeFolders, clearFolders } = useFolderQueueStore()

  const [rows, setRows] = useState<PipelineRow[]>([])
  const [filter, setFilter] = useState<FilterKey>('all')
  const [tableSearch, setTableSearch] = useState('')
  const [queueSearch, setQueueSearch] = useState('')
  const [activeQueue, setActiveQueue] = useState<string | null>(null)
  const [lastShiftAnchor, setLastShiftAnchor] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [shallowScan, setShallowScan] = useState(false)
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; id: string } | null>(null)
  const [lbdirPanelId, setLbdirPanelId] = useState<string | null>(null)

  // Sync shared folder queue into local rows — handles both additions and removals
  // (so clearing on Verify/LBDIR/Spectrograms also clears Pipeline's rows)
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
  const flatListRef = useRef<VItem[]>([])
  const stopRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const bulkMenuRef = useRef<HTMLDivElement>(null)
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false)

  // ── Derived counts ──────────────────────────────────────────────────────────
  const counts = {
    all:   rows.length,
    attn:  rows.filter(r => r.severity === 'attn').length,
    ready: rows.filter(r => r.severity === 'ready').length,
    done:  rows.filter(r => r.severity === 'done').length,
  }

  const isRunning  = rows.some(r => r.running)
  const readyRows  = rows.filter(r => r.severity === 'ready')
  const selectedRows = rows.filter(r => r.selected)
  const selectedReady = selectedRows.filter(r => r.severity === 'ready')

  // ── Filtered + grouped rows for the table ───────────────────────────────────
  const visibleRows = rows.filter(r => {
    if (filter !== 'all' && r.severity !== filter) return false
    if (tableSearch) {
      const q = tableSearch.toLowerCase()
      if (!r.folderName.toLowerCase().includes(q)) return false
    }
    return true
  })

  const attnRows  = visibleRows.filter(r => r.severity === 'attn')
  const renaRows  = visibleRows.filter(r => r.severity === 'ready')
  const doneRows  = visibleRows.filter(r => r.severity === 'done')

  // ── Virtualizer flat list: group headers + data rows ────────────────────────
  const flatList: VItem[] = []
  if (attnRows.length > 0) {
    flatList.push({ type: 'group', label: 'Need attention', count: counts.attn, severity: 'attn' })
    attnRows.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (renaRows.length > 0) {
    flatList.push({ type: 'group', label: 'Ready to rename', count: counts.ready, severity: 'ready' })
    renaRows.forEach(r => flatList.push({ type: 'row', row: r }))
  }
  if (doneRows.length > 0) {
    flatList.push({ type: 'group', label: 'Done', count: counts.done, severity: 'done' })
    doneRows.forEach(r => flatList.push({ type: 'row', row: r }))
  }

  // Keep ref in sync so callbacks can look up indices without stale closure issues
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

  // ── Row mutation helpers ────────────────────────────────────────────────────
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

  // ── Backend: run steps (sequential, one folder at a time) ──────────────────
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

  // ── Stop an in-progress run ─────────────────────────────────────────────────
  const stopRun = useCallback(() => {
    stopRef.current = true
    abortRef.current?.abort()
    abortRef.current = null
    setRows(prev => prev.map(r => r.running ? { ...r, running: false } : r))
  }, [])

  // ── Refresh just the lbdir step for one row (called after reconcile apply) ──
  const refreshLbdirRow = useCallback(async (id: string) => {
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

  // ── Backend: apply a single rename ─────────────────────────────────────────
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
        // Update local rows first so the sync effect sees the new id when the store change propagates
        setRows(prev => prev.map(r =>
          r.id === row.id ? {
            ...r,
            folderPath: data.new_path!,
            folderName: newName,
            id: data.new_path!,
            severity: 'done',
            steps: { ...r.steps, rename: { status: 'ok', label: 'Renamed' } },
          } : r
        ))
        // Keep queue store in sync: swap old path for new path
        useFolderQueueStore.getState().removeFolders([row.folderPath])
        useFolderQueueStore.getState().addFolders([data.new_path])
      }
    } catch { /* silent */ }
  }, [])

  // ── Bulk apply all ready rows ───────────────────────────────────────────────
  const applyAllReady = useCallback(async () => {
    for (const row of readyRows) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [readyRows, applyRename])

  // ── Bulk apply selected ready rows ─────────────────────────────────────────
  const applySelected = useCallback(async () => {
    for (const row of selectedReady) {
      if (row.steps.rename.proposed) await applyRename(row)
    }
  }, [selectedReady, applyRename])

  // ── Folder picking (Electron IPC) ──────────────────────────────────────────
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
  }, [removeFolders])

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

  // ── Selection ───────────────────────────────────────────────────────────────
  const toggleSelect = useCallback((id: string, shiftKey: boolean) => {
    setRows(prev => {
      if (shiftKey && lastShiftAnchor) {
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

  // ── Close bulk-actions menu on outside click ────────────────────────────────
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

  // ── Drag-and-drop folder ingestion ──────────────────────────────────────────
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
            {counts.all === 0
              ? t('pipeline.emptyHint')
              : t('pipeline.runHint')}
          </div>
        </div>

        {counts.all > 0 && (
          <div style={{ display: 'flex', gap: 8, marginLeft: 12 }}>
            <Pill tone="ok"   soft dot>{t('pipeline.done', { count: counts.done })}</Pill>
            <Pill tone="warn" soft dot>{t('pipeline.readyToRename', { count: counts.ready })}</Pill>
            <Pill tone="bad"  soft dot>{t('pipeline.needAttention', { count: counts.attn })}</Pill>
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
                  <button
                    onClick={() => { selectAll(); setBulkMenuOpen(false) }}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                      border: 'none', background: 'transparent',
                      color: 'var(--lbb-fg)', borderRadius: 5,
                    }}
                  >{t('pipeline.selectAllVisible')}</button>
                  {selectedRows.length > 0 && (
                    <button
                      onClick={() => { clearSelection(); setBulkMenuOpen(false) }}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left',
                        padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
                        border: 'none', background: 'transparent',
                        color: 'var(--lbb-fg)', borderRadius: 5,
                      }}
                    >{t('pipeline.clearSelection', { count: selectedRows.length })}</button>
                  )}
                  <div style={{ height: 1, background: 'var(--lbb-border)', margin: '4px 0' }} />
                  <button
                    onClick={() => { setRows([]); setActiveQueue(null); clearFolders(); setBulkMenuOpen(false) }}
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
            {queueRows.map(r => {
              const active = activeQueue === r.id
              const dotColor = r.severity === 'done'  ? 'var(--lbb-ok-bar)'
                             : r.severity === 'ready' ? 'var(--lbb-warn-bar)'
                             : 'var(--lbb-bad-bar)'
              return (
                <button
                  key={r.id}
                  onClick={() => scrollToRow(r.id)}
                  onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, id: r.id }) }}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 8px', marginBottom: 1, borderRadius: 6,
                    background: active ? 'var(--lbb-accent-soft)' : 'transparent',
                    color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                    border: '1px solid transparent', textAlign: 'left',
                    fontFamily: 'inherit', fontSize: 'var(--lbb-fs-11-5)', cursor: 'pointer',
                  }}
                >
                  <span style={{
                    width: 8, height: 8, borderRadius: 2,
                    background: dotColor, flexShrink: 0,
                  }} />
                  <span style={{
                    flex: 1, minWidth: 0, whiteSpace: 'nowrap',
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)',
                  }}>{r.folderName}</span>
                  {r.running && (
                    <span style={{ fontSize: 'var(--lbb-fs-9)', color: 'var(--lbb-accent-mid)', letterSpacing: 1 }}>···</span>
                  )}
                </button>
              )
            })}
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
              onClick={() => { setRows([]); setActiveQueue(null); clearFolders() }}
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
                  onClick={() => runSteps(rows.map(r => r.id), ['verify', 'lookup', 'rename', 'lbdir'])}
                >{t('pipeline.queue.runAll')}</Button>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['verify'])}>{t('pipeline.queue.verify')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['lookup'])}>{t('pipeline.queue.lookup')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['rename'])}>{t('pipeline.queue.rename')}</Button>
                  <Button variant="secondary" size="sm" onClick={() => runSteps(rows.map(r => r.id), ['lbdir'])}>{t('pipeline.queue.lbdir')}</Button>
                </div>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main table area ─────────────────────────────────────────────────── */}
        <section style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, position: 'relative' }}>

          {/* Filter chips bar */}
          <div style={{
            padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 6,
            borderBottom: '1px solid var(--lbb-border)', flexWrap: 'wrap', flexShrink: 0,
          }}>
            <Chip active={filter === 'all'}   onClick={() => setFilter('all')}   count={counts.all}>{t('pipeline.filter.all')}</Chip>
            <Chip active={filter === 'attn'}  onClick={() => setFilter('attn')}  count={counts.attn}>{t('pipeline.filter.needAttention')}</Chip>
            <Chip active={filter === 'ready'} onClick={() => setFilter('ready')} count={counts.ready}>{t('pipeline.filter.readyToRename')}</Chip>
            <Chip active={filter === 'done'}  onClick={() => setFilter('done')}  count={counts.done}>{t('pipeline.filter.done')}</Chip>
            <span style={{ width: 1, height: 16, background: 'var(--lbb-border)', margin: '0 4px' }} />
            <Chip count={rows.filter(r => r.steps.lookup.label === 'Not found').length}>{t('pipeline.filter.notFound')}</Chip>
            <Chip count={rows.filter(r => r.steps.verify.label === 'Mismatch').length}>{t('pipeline.filter.mismatch')}</Chip>
            <Chip count={rows.filter(r => r.steps.verify.label === 'Incomplete').length}>{t('pipeline.filter.incomplete')}</Chip>
            <div style={{ flex: 1 }} />
            <Input
              icon="filter"
              placeholder={t('pipeline.filter.filterFolders')}
              size="sm"
              value={tableSearch}
              onChange={e => setTableSearch(e.target.value)}
              style={{ width: 240 }}
            />
            <IconButton icon="more" title="Density" />
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
              <span style={{ color: 'var(--lbb-fg2)' }}>
                {t('pipeline.selection.hint')}
              </span>
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
                  <col style={{ width: 36 }} />
                  <col />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 140 }} />
                  <col style={{ width: 172 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH> </TH>
                    <TH>
                      <input
                        type="checkbox"
                        checked={selectedRows.length === visibleRows.length && visibleRows.length > 0}
                        onChange={e => e.target.checked ? selectAll() : clearSelection()}
                      />
                    </TH>
                    <TH>{t('pipeline.table.folder')}</TH>
                    <StepTH n={1} label={t('pipeline.table.verify')} />
                    <StepTH n={2} label={t('pipeline.table.lookup')} />
                    <StepTH n={3} label={t('pipeline.table.rename')} />
                    <StepTH n={4} label={t('pipeline.table.lbdir')} />
                    <TH>{t('pipeline.table.lb')}</TH>
                    <TH align="right"> </TH>
                  </tr>
                </thead>
                <tbody>
                  {/* top spacer — keeps real rows in normal table flow so colgroup widths apply */}
                  {virtualizer.getVirtualItems().length > 0 && (
                    <tr aria-hidden="true">
                      <td colSpan={9} style={{ height: virtualizer.getVirtualItems()[0].start, padding: 0, border: 'none' }} />
                    </tr>
                  )}
                  {virtualizer.getVirtualItems().map(vItem => {
                    const item = flatList[vItem.index]
                    if (!item) return null

                    if (item.type === 'group') {
                      return (
                        <GroupRow
                          key={`group-${item.label}`}
                          label={item.label}
                          count={item.count}
                          colSpan={8}
                        />
                      )
                    }

                    const r = item.row
                    const edge = r.severity === 'attn' ? 'bad'
                               : r.severity === 'ready' ? 'warn'
                               : 'ok'
                    const lb = r.steps.lookup.lb_number
                    const lbLabel = lb ? `LB-${String(lb).padStart(5, '0')}` : '—'
                    const aliasFrom = r.steps.lookup.alias_resolved_from

                    return (
                      <TR
                        key={r.id}
                        edge={edge}
                        selected={r.selected}
                        onClick={(e: React.MouseEvent) => toggleSelect(r.id, e.shiftKey)}
                      >
                        <TD>
                          <input
                            type="checkbox"
                            checked={r.selected}
                            onChange={() => {/* handled by TR click */}}
                            onClick={e => e.stopPropagation()}
                          />
                        </TD>
                        <TD mono style={{ color: r.severity === 'done' ? 'var(--lbb-fg2)' : 'var(--lbb-fg)' }}>
                          {r.folderName}
                        </TD>
                        <TD align="center"><StepPill step={r.steps.verify} running={r.running} /></TD>
                        <TD align="center"><StepPill step={r.steps.lookup} running={r.running} /></TD>
                        <TD align="center"><StepPill step={r.steps.rename} running={r.running} /></TD>
                        <TD align="center"><StepPill step={r.steps.lbdir} running={r.running} /></TD>
                        <TD mono style={{
                          color: r.severity === 'ready' ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                          fontWeight: r.severity === 'ready' ? 600 : undefined,
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
                            {r.steps.lbdir.status !== 'mute' && r.steps.lbdir.status !== 'ok' && (
                              <Button
                                size="sm"
                                variant={lbdirPanelId === r.id ? 'primary' : 'ghost'}
                                icon="lbdir"
                                onClick={() => setLbdirPanelId(prev => prev === r.id ? null : r.id)}
                              >LBDIR</Button>
                            )}
                            {r.severity === 'attn' && (
                              <Button size="sm" variant="secondary" icon="reveal" onClick={() => window.api.openPath(r.folderPath)}>Open</Button>
                            )}
                            {r.severity === 'ready' && (
                              <Button size="sm" variant="primary" icon="check" onClick={() => applyRename(r)}>Apply</Button>
                            )}
                            {r.severity === 'done' && r.steps.lbdir.status === 'ok' && (
                              <Pill tone="ok" soft>Done</Pill>
                            )}
                          </div>
                        </TD>
                      </TR>
                    )
                  })}
                  {/* bottom spacer */}
                  {virtualizer.getVirtualItems().length > 0 && (() => {
                    const last = virtualizer.getVirtualItems()[virtualizer.getVirtualItems().length - 1]
                    const remaining = virtualizer.getTotalSize() - last.end
                    return remaining > 0 ? (
                      <tr aria-hidden="true">
                        <td colSpan={9} style={{ height: remaining, padding: 0, border: 'none' }} />
                      </tr>
                    ) : null
                  })()}
                </tbody>
              </TableShell>
            </div>
          )}

          {/* ── LBDIR mini panel ─────────────────────────────────────────────── */}
          {lbdirPanelId && (() => {
            const panelRow = rows.find(r => r.id === lbdirPanelId)
            return panelRow ? (
              <LbdirMiniPanel
                key={lbdirPanelId}
                row={panelRow}
                onClose={() => setLbdirPanelId(null)}
                onRowRefresh={refreshLbdirRow}
              />
            ) : null
          })()}
        </section>
      </div>

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
