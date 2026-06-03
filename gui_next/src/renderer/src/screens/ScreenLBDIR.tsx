import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, Input, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useLbdirStore, LbdirState, CheckFile, CheckResult, ReconcileProposal, ReconcileResult } from '../lib/lbdirStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type Tone      = 'ok' | 'bad' | 'warn' | 'mute' | 'info'
type ToastTone = 'ok' | 'bad' | 'info'

const STATE_LABEL: Record<LbdirState, { tone: Tone; label: string; hint: string }> = {
  pass:            { tone: 'ok',   label: 'Pass',             hint: 'All files verified' },
  fail:            { tone: 'bad',  label: 'Fail',             hint: 'Checksum mismatches' },
  missing_files:   { tone: 'bad',  label: 'Missing files',    hint: 'Files listed in lbdir not found on disk' },
  no_lbdir:        { tone: 'warn', label: 'No lbdir',         hint: 'No lbdir*.txt found in folder' },
  no_lb:           { tone: 'mute', label: 'No LB#',           hint: 'Folder not linked to an LB entry' },
  shntool_missing: { tone: 'warn', label: 'Shntool missing',  hint: 'Install shntool to verify SHN files' },
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function CheckDot({ s }: { s: 'pass' | 'miss' | 'na' }): React.JSX.Element {
  if (s === 'pass') return <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
  if (s === 'miss') return <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />
  return <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>na</span>
}

function FolderSideRow({ folder, checkResult, verifiedAt, active, onClick }: {
  folder: string
  checkResult: CheckResult | undefined
  verifiedAt: string | null
  active: boolean
  onClick: () => void
}): React.JSX.Element {
  const state = checkResult?.status ?? null
  const sl = state ? STATE_LABEL[state] : null

  // Resolved verified timestamp: prefer check result, fall back to pre-loaded value
  const resolvedVerifiedAt = checkResult?.lbdir_verified_at ?? verifiedAt

  // Dot color: use check result status if available; if no check but previously verified, show faded green
  const color = sl
    ? (sl.tone === 'ok' ? 'var(--lbb-ok-bar)' : sl.tone === 'bad' ? 'var(--lbb-bad-bar)' : sl.tone === 'warn' ? 'var(--lbb-warn-bar)' : 'var(--lbb-fg3)')
    : resolvedVerifiedAt
      ? 'var(--lbb-ok-bar)'
      : 'var(--lbb-border)'

  const name = folder.split('/').pop() ?? folder
  const verifiedDate = resolvedVerifiedAt ? resolvedVerifiedAt.slice(0, 10) : null

  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 10px', marginBottom: 1, borderRadius: 6,
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      border: '1px solid ' + (active ? 'var(--lbb-accent-line)' : 'transparent'),
      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: 2, flex: '0 0 8px',
        background: color,
        opacity: !sl && resolvedVerifiedAt ? 0.55 : 1,
      }} />
      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
        <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums', display: 'flex', gap: 4, alignItems: 'center' }}>
          {checkResult ? (
            <>
              {checkResult.lb_number
                ? <span style={{ color: 'var(--lbb-accent-mid)' }}>LB-{String(checkResult.lb_number).padStart(5, '0')}</span>
                : <span>—</span>}
              {checkResult.total > 0 && <span> · {checkResult.pass}/{checkResult.total} pass</span>}
            </>
          ) : verifiedDate ? (
            <span style={{ color: 'var(--lbb-ok-fg)', opacity: 0.7 }}>✓ {verifiedDate}</span>
          ) : null}
        </span>
      </span>
    </button>
  )
}

// ── Reconcile panel ────────────────────────────────────────────────────────────

function ReconcilePanel({ result, reconSelected, setReconSelected, busy, onRescan, onApply }: {
  result: ReconcileResult
  reconSelected: Set<string>
  setReconSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  busy: boolean
  onRescan: () => void
  onApply: () => void
}): React.JSX.Element {
  const selectedCount = result.proposals.filter(p => reconSelected.has(p.disk_rel)).length
  const extrasCount = result.unmatched_disk.length

  return (
    <div style={{
      margin: '0 24px 20px',
      borderRadius: 8,
      border: '1px solid var(--lbb-border)',
      background: 'var(--lbb-surface)',
      overflow: 'hidden',
    }}>
      {/* Panel header */}
      <div style={{
        padding: '10px 16px', background: 'var(--lbb-surface2)',
        borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <Icon name="rename" size={13} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
          Reconcile
        </span>
        {result.proposals.length > 0 && (
          <Pill tone="info" soft>{result.proposals.length} rename{result.proposals.length !== 1 ? 's' : ''}</Pill>
        )}
        {extrasCount > 0 && (
          <Pill tone="warn" soft>{extrasCount} extra{extrasCount !== 1 ? 's' : ''} → /extras/</Pill>
        )}
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" disabled={busy} onClick={onRescan}>Re-scan</Button>
        <Button variant="primary" size="sm" icon="check" disabled={busy || (selectedCount === 0 && extrasCount === 0)} onClick={onApply}>
          Apply{selectedCount > 0 ? ` ${selectedCount} rename${selectedCount !== 1 ? 's' : ''}` : ''}
          {extrasCount > 0 ? ` + move ${extrasCount} extra${extrasCount !== 1 ? 's' : ''}` : ''}
        </Button>
      </div>

      {/* Proposals */}
      {result.proposals.length > 0 ? (
        <div style={{ borderBottom: extrasCount > 0 ? '1px solid var(--lbb-border)' : undefined }}>
          <div style={{ padding: '8px 16px 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox"
              checked={result.proposals.length > 0 && result.proposals.every(p => reconSelected.has(p.disk_rel))}
              onChange={e => setReconSelected(e.target.checked
                ? new Set(result.proposals.map(p => p.disk_rel))
                : new Set()
              )}
            />
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
              Proposed renames — files found by MD5 match
            </span>
          </div>
          <TableShell style={{ margin: 0, borderRadius: 0, border: 'none' }}>
            <colgroup>
              <col style={{ width: 3 }} /><col style={{ width: 32 }} />
              <col /><col style={{ width: 24 }} /><col /><col style={{ width: 140 }} />
            </colgroup>
            <thead>
              <tr>
                <TH> </TH><TH> </TH>
                <TH>Current path on disk</TH><TH> </TH>
                <TH>Will rename to</TH><TH>MD5</TH>
              </tr>
            </thead>
            <tbody>
              {result.proposals.map((p, i) => (
                <TR key={i} edge="info">
                  <TD> </TD>
                  <TD>
                    <input type="checkbox"
                      checked={reconSelected.has(p.disk_rel)}
                      onChange={e => setReconSelected(prev => {
                        const next = new Set(prev)
                        e.target.checked ? next.add(p.disk_rel) : next.delete(p.disk_rel)
                        return next
                      })}
                    />
                  </TD>
                  <TD mono style={{ color: 'var(--lbb-fg2)' }}>{p.disk_rel}</TD>
                  <TD align="center"><Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} /></TD>
                  <TD mono style={{ color: 'var(--lbb-ok-fg)' }}>{p.lbdir_rel}</TD>
                  <TD mono dim>{p.md5.slice(0, 12)}…</TD>
                </TR>
              ))}
            </tbody>
          </TableShell>
        </div>
      ) : (
        <div style={{ padding: '12px 16px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', borderBottom: extrasCount > 0 ? '1px solid var(--lbb-border)' : undefined }}>
          No rename proposals — missing files could not be matched by MD5.
        </div>
      )}

      {/* Extras */}
      {extrasCount > 0 && (
        <div>
          <div style={{ padding: '8px 16px 4px' }}>
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
              Extra files — not in lbdir, will be moved to <span style={{ fontFamily: 'var(--lbb-mono)' }}>/extras/</span>
            </span>
          </div>
          <div style={{ padding: '4px 16px 12px', display: 'flex', flexDirection: 'column', gap: 3 }}>
            {result.unmatched_disk.map((f, i) => (
              <span key={i} style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-warn-fg)' }}>{f}</span>
            ))}
          </div>
        </div>
      )}

      {result.proposals.length === 0 && extrasCount === 0 && (
        <div style={{ padding: '12px 16px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
          Nothing to reconcile for this folder.
        </div>
      )}
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenLBDIR(): React.JSX.Element {
  const navigate = useNavigate()

  const {
    activeFolder, filter, checkResults, reconcileResults, reconSelected,
    setActiveFolder, setFilter, setCheckResults, updateCheckResult,
    setReconcileResults, clearReconcileFor, setReconSelected,
  } = useLbdirStore()
  const { folders, addFolders } = useFolderQueueStore()
  const [busy,      setBusy]      = useState(false)
  const [tools,     setTools]     = useState<{ shntool_available: boolean } | null>(null)
  const [toast,     setToast]     = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [verifiedAt, setVerifiedAt] = useState<Record<string, string | null>>({})

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  useEffect(() => {
    fetch(`${BASE}/api/spectrogram/check`)
      .then(r => r.json())
      .then((d: { shntool_available: boolean }) => setTools(d))
      .catch(() => {})
  }, [])

  // Load lbdir_verified_at from collection whenever the folder list changes
  useEffect(() => {
    if (!folders.length) return
    fetch(`${BASE}/api/lbdir/verified_status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders }),
    })
      .then(r => r.json())
      .then((d: Record<string, string | null>) => setVerifiedAt(d))
      .catch(() => {})
  }, [folders])

  const post = useCallback(async (endpoint: string, body: object): Promise<unknown> => {
    const r = await fetch(`${BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  }, [])

  const handleAddFolders = useCallback(async () => {
    const picked = await window.api.pickFolders()
    if (picked.length) {
      addFolders(picked)
      if (!activeFolder) setActiveFolder(picked[0])
    }
  }, [activeFolder, addFolders, setActiveFolder])

  const handleAddRoot = useCallback(async () => {
    const root = await window.api.pickDir()
    if (!root) return
    try {
      const data = await post('/api/pipeline/scan-tree', { root }) as { folders: string[] }
      if (data.folders?.length) {
        addFolders(data.folders)
        if (!activeFolder) setActiveFolder(data.folders[0])
        showToast(`Found ${data.folders.length} folders`, 'ok')
      } else {
        showToast('No audio folders found', 'info')
      }
    } catch {
      showToast('Scan failed', 'bad')
    }
  }, [activeFolder, post, showToast])

  // Process: retrieve lbdir for all folders, then check all
  const handleProcess = useCallback(async (targetFolders: string[]) => {
    if (!targetFolders.length) { showToast('Add folders first', 'info'); return }
    setBusy(true)
    try {
      // Auto-retrieve lbdir files from cache/LB.com where missing
      await post('/api/lbdir/retrieve', { folders: targetFolders }).catch(() => {})
      // Check all folders against their lbdir files
      const data = await post('/api/lbdir/check', { folders: targetFolders }) as { results: CheckResult[] }
      const results = data.results ?? []
      if (targetFolders.length === folders.length) {
        setCheckResults(results)
      } else {
        results.forEach(r => updateCheckResult(r.folder, r))
      }
      if (!activeFolder && results.length) setActiveFolder(results[0].folder)
      // Clear any stale reconcile data for re-processed folders
      results.forEach(r => clearReconcileFor(r.folder))
      // Refresh local verifiedAt map from the fresh check results
      setVerifiedAt(prev => {
        const next = { ...prev }
        results.forEach(r => { next[r.folder] = r.lbdir_verified_at })
        return next
      })
    } catch {
      showToast('Process failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, activeFolder, post, showToast, setCheckResults, updateCheckResult, setActiveFolder, clearReconcileFor])

  const handleReconcile = useCallback(async (folder: string) => {
    setBusy(true)
    try {
      const data = await post('/api/lbdir/reconcile', { folders: [folder] }) as { results: ReconcileResult[] }
      if (data.results?.length) {
        setReconcileResults([...reconcileResults.filter(r => r.folder !== folder), data.results[0]])
        setReconSelected(new Set(data.results[0].proposals.map(p => p.disk_rel)))
      }
    } catch {
      showToast('Reconcile scan failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [reconcileResults, post, showToast, setReconcileResults, setReconSelected])

  const handleApplyReconcile = useCallback(async (folder: string) => {
    const reconResult = reconcileResults.find(r => r.folder === folder)
    if (!reconResult) return
    const renames = reconResult.proposals
      .filter(p => reconSelected.has(p.disk_rel))
      .map(p => ({ from: p.disk_rel, to: p.lbdir_rel }))
    const extras = reconResult.unmatched_disk
    setBusy(true)
    try {
      if (renames.length) {
        await post('/api/lbdir/apply_reconcile', { folder, renames })
      }
      if (extras.length) {
        await post('/api/lbdir/move_extras', { folder, files: extras })
      }
      const parts: string[] = []
      if (renames.length) parts.push(`${renames.length} rename${renames.length !== 1 ? 's' : ''}`)
      if (extras.length) parts.push(`${extras.length} extra${extras.length !== 1 ? 's' : ''} moved to /extras/`)
      showToast(parts.length ? parts.join(', ') : 'Nothing to apply', 'ok')
      clearReconcileFor(folder)
      // Re-check this folder
      const data = await post('/api/lbdir/check', { folders: [folder] }) as { results: CheckResult[] }
      if (data.results?.length) updateCheckResult(folder, data.results[0])
    } catch {
      showToast('Apply failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [reconcileResults, reconSelected, post, showToast, clearReconcileFor, updateCheckResult])

  const filteredFolders = filter
    ? folders.filter(f => f.toLowerCase().includes(filter.toLowerCase()))
    : folders

  const activeFolderStr = activeFolder ?? folders[0] ?? null
  const checkResult  = activeFolderStr ? checkResults.find(r => r.folder === activeFolderStr) ?? null : null
  const reconResult  = activeFolderStr ? reconcileResults.find(r => r.folder === activeFolderStr) ?? null : null

  const canReconcile = checkResult !== null
    && checkResult.lbdir_found
    && checkResult.status !== 'pass'
    && checkResult.status !== 'no_lb'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="lbdir" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>LBDIR</h1>
            <Pill tone="mute" soft>official sidecar reconciliation</Pill>
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            Retrieve, verify, and reconcile the <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> archive sidecar for each folder.
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 14, padding: '0 12px', borderRight: '1px solid var(--lbb-border)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: tools?.shntool_available ? 'var(--lbb-ok-bar)' : 'var(--lbb-warn-bar)' }} /> shntool
          </span>
        </div>
        <Button variant="ghost" size="sm" icon="folderPlus" onClick={handleAddFolders}>Add folders…</Button>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Queue rail */}
        <aside style={{
          width: 280, flex: '0 0 280px',
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
              <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.1, textTransform: 'uppercase' }}>Folders</span>
              <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>{folders.length}</span>
            </div>
            <Input
              icon="search" placeholder="Filter…" size="sm" style={{ width: '100%' }}
              value={filter} onChange={e => setFilter(e.target.value)}
            />
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {filteredFolders.length === 0 ? (
              <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
                {folders.length === 0 ? 'No folders added' : 'No matches'}
              </div>
            ) : filteredFolders.map(f => (
              <FolderSideRow
                key={f}
                folder={f}
                checkResult={checkResults.find(r => r.folder === f)}
                verifiedAt={verifiedAt[f] ?? null}
                active={f === activeFolderStr}
                onClick={() => setActiveFolder(f)}
              />
            ))}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary"   size="sm" icon="lbdir"      block disabled={busy || !folders.length}
              onClick={() => handleProcess(folders)}>
              {busy ? 'Processing…' : 'Process all folders'}
            </Button>
            <Button variant="ghost"     size="sm" icon="folderPlus" block onClick={handleAddRoot}>Add root folder…</Button>
          </div>
        </aside>

        {/* Detail panel */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'auto' }}>

          {!activeFolderStr ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
              <Icon name="lbdir" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>Add folders, then click Process all folders</span>
            </div>
          ) : !checkResult ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
              <Icon name="lbdir" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>Click Process all folders to retrieve and verify</span>
              <Button variant="secondary" size="sm" icon="lbdir" disabled={busy}
                onClick={() => handleProcess([activeFolderStr])}>
                Process this folder
              </Button>
            </div>
          ) : (
            <>
              {/* Folder header */}
              <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-13)', fontWeight: 600 }}>
                    {activeFolderStr.split('/').pop()}
                  </span>
                  {checkResult.lb_number !== null && (
                    <Pill tone="info" soft style={{ fontFamily: 'var(--lbb-mono)' }}>
                      LB-{String(checkResult.lb_number).padStart(5, '0')}
                    </Pill>
                  )}
                  {checkResult.lbdir_path && (
                    <Pill tone="mute" soft style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>
                      {checkResult.lbdir_path.split('/').pop()}
                    </Pill>
                  )}
                  <Pill tone="mute" soft>{checkResult.mode.toUpperCase()}</Pill>
                  <Pill tone={STATE_LABEL[checkResult.status].tone} soft dot={checkResult.status !== 'pass'}>
                    {STATE_LABEL[checkResult.status].label}
                  </Pill>
                  <div style={{ flex: 1 }} />
                  {checkResult.lbdir_path && (
                    <Button variant="ghost" size="sm" icon="reveal"
                      onClick={() => window.api.openPath(checkResult.lbdir_path!)}>
                      Open lbdir.txt
                    </Button>
                  )}
                  <Button variant="secondary" size="sm" icon="lbdir" disabled={busy}
                    onClick={() => handleProcess([activeFolderStr])}>
                    Re-process
                  </Button>
                </div>

                {/* Stats row */}
                <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                  {[
                    { l: 'Total',    v: checkResult.total,    c: undefined },
                    { l: 'Pass',     v: checkResult.pass,     c: checkResult.pass     > 0 ? 'var(--lbb-ok-fg)'  : 'var(--lbb-fg3)' },
                    { l: 'Mismatch', v: checkResult.mismatch, c: checkResult.mismatch > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
                    { l: 'Missing',  v: checkResult.missing,  c: checkResult.missing  > 0 ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)' },
                  ].map((st, i) => (
                    <div key={i} style={{ padding: '6px 10px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)' }}>
                      <div style={{ fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{st.l}</div>
                      <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: st.c ?? 'var(--lbb-fg)' }}>{st.v}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Special-state messages */}
              {checkResult.status === 'no_lb' && (
                <div style={{ margin: '16px 24px 0', padding: '10px 14px', borderRadius: 6, background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name="info" size={13} style={{ color: 'var(--lbb-fg3)' }} />
                  <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
                    No LB number linked to this folder. Run Lookup to identify it, then link it in My Collection.
                  </span>
                  <div style={{ flex: 1 }} />
                  <Button size="sm" variant="secondary" icon="lookup" onClick={() => navigate('/lookup')}>Run Lookup</Button>
                </div>
              )}
              {checkResult.status === 'no_lbdir' && (
                <div style={{ margin: '16px 24px 0', padding: '10px 14px', borderRadius: 6, background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name="info" size={13} style={{ color: 'var(--lbb-info-fg)' }} />
                  <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
                    No <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> found. The retrieve step ran but no cached file was available — scrape the entry to fetch it from LB.com.
                  </span>
                </div>
              )}

              {/* File table */}
              {checkResult.files.length > 0 && (
                <div style={{ padding: '16px 24px 0' }}>
                  <TableShell>
                    <colgroup>
                      <col style={{ width: 3 }} /><col />
                      <col style={{ width: 50 }} /><col style={{ width: 60 }} /><col style={{ width: 70 }} />
                      <col style={{ width: 80 }} /><col style={{ width: 60 }} /><col style={{ width: 70 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <TH> </TH><TH>Filename</TH>
                        <TH align="center">MD5</TH><TH align="center">Disk</TH><TH>Overall</TH>
                        <TH align="right">Length</TH><TH>Fmt</TH><TH align="right">Ratio</TH>
                      </tr>
                    </thead>
                    <tbody>
                      {checkResult.files.map((f, i) => {
                        const edge: 'ok' | 'warn' | 'bad' = f.overall === 'pass' ? 'ok' : f.overall === 'missing' ? 'warn' : 'bad'
                        return (
                          <TR key={i} edge={edge}>
                            <TD mono style={{ color: f.overall === 'pass' ? 'var(--lbb-fg)' : 'var(--lbb-bad-fg)' }}>{f.filename}</TD>
                            <TD align="center"><CheckDot s={f.md5_status} /></TD>
                            <TD align="center">
                              {f.on_disk
                                ? <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
                                : <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />}
                            </TD>
                            <TD><Pill tone={edge} soft>{f.overall === 'pass' ? 'Pass' : f.overall === 'missing' ? 'Missing' : 'Fail'}</Pill></TD>
                            <TD align="right" mono dim>{f.length ?? '—'}</TD>
                            <TD mono dim>{f.fmt ?? '—'}</TD>
                            <TD align="right" mono dim>{f.ratio ?? '—'}</TD>
                          </TR>
                        )
                      })}
                    </tbody>
                  </TableShell>
                </div>
              )}

              {/* Reconcile trigger / panel */}
              {canReconcile && (
                <div style={{ padding: '16px 0 0' }}>
                  {!reconResult ? (
                    <div style={{ padding: '0 24px' }}>
                      <Button variant="secondary" size="sm" icon="rename" disabled={busy}
                        onClick={() => handleReconcile(activeFolderStr)}>
                        {busy ? 'Scanning…' : 'Reconcile files…'}
                      </Button>
                      <span style={{ marginLeft: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                        Match missing files by MD5 and move extras to <span style={{ fontFamily: 'var(--lbb-mono)' }}>/extras/</span>
                      </span>
                    </div>
                  ) : (
                    <ReconcilePanel
                      result={reconResult}
                      reconSelected={reconSelected}
                      setReconSelected={setReconSelected}
                      busy={busy}
                      onRescan={() => handleReconcile(activeFolderStr)}
                      onApply={() => handleApplyReconcile(activeFolderStr)}
                    />
                  )}
                </div>
              )}

              <div style={{ height: 24 }} />
            </>
          )}
        </section>
      </div>

      {toast && (
        <div
          style={{
            position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
            background: toast.tone === 'ok' ? 'var(--lbb-ok-bar)' : toast.tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)',
            color: '#fff', padding: '9px 18px', borderRadius: 8,
            fontSize: 'var(--lbb-fs-13)', fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
            pointerEvents: 'none',
          }}
          ref={(el: HTMLDivElement | null) => { if (el) setTimeout(() => setToast(null), 3500) }}
        >{toast.msg}</div>
      )}
    </div>
  )
}
