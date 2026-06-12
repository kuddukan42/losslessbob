import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, Input, Pill } from '../components'
import { FolderQueueRail } from '../components/FolderQueueRail'
import { LbdirDetail } from '../components/pipeline/LbdirDetail'
import { useLbdirStore, LbdirState, CheckResult, SiteProposal, ReconcileResult } from '../lib/lbdirStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type Tone      = 'ok' | 'bad' | 'warn' | 'mute' | 'info'
type ToastTone = 'ok' | 'bad' | 'info'

const STATE_LABEL: Record<LbdirState, { tone: Tone; label: string; hint: string }> = {
  pass:            { tone: 'ok',   label: 'Pass',             hint: 'All files verified' },
  fail:            { tone: 'bad',  label: 'Fail',             hint: 'Checksum mismatches' },
  missing_files:   { tone: 'bad',  label: 'Missing files',    hint: 'Files listed in lbdir not found on disk' },
  extra_files:     { tone: 'warn', label: 'Extra files',      hint: 'Files on disk not listed in lbdir' },
  no_lbdir:        { tone: 'warn', label: 'No lbdir',         hint: 'No lbdir*.txt found in folder' },
  no_lb:           { tone: 'mute', label: 'No LB#',           hint: 'Folder not linked to an LB entry' },
  shntool_missing: { tone: 'warn', label: 'Shntool missing',  hint: 'Install shntool to verify SHN files' },
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function FolderSideRow({ folder, checkResult, verifiedAt, active, onClick, onContextMenu }: {
  folder: string
  checkResult: CheckResult | undefined
  verifiedAt: string | null
  active: boolean
  onClick: () => void
  onContextMenu?: (e: React.MouseEvent) => void
}): React.JSX.Element {
  const state = checkResult?.status ?? null
  const sl = state ? STATE_LABEL[state] : null

  // Resolved verified timestamp: prefer check result, fall back to pre-loaded value
  const resolvedVerifiedAt = checkResult?.lbdir_verified_at ?? verifiedAt

  // Dot color: only use green after a live check that passed; stale timestamps are neutral
  const color = sl
    ? (sl.tone === 'ok' ? 'var(--lbb-ok-bar)' : sl.tone === 'bad' ? 'var(--lbb-bad-bar)' : sl.tone === 'warn' ? 'var(--lbb-warn-bar)' : 'var(--lbb-fg3)')
    : resolvedVerifiedAt
      ? 'var(--lbb-fg3)'
      : 'var(--lbb-border)'

  const name = folder.split('/').pop() ?? folder
  const verifiedDate = resolvedVerifiedAt ? resolvedVerifiedAt.slice(0, 10) : null

  return (
    <button onClick={onClick} onContextMenu={onContextMenu} style={{
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
        opacity: 1,
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
            <span style={{ color: 'var(--lbb-fg3)' }}>✓ {verifiedDate}</span>
          ) : null}
        </span>
      </span>
    </button>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenLBDIR(): React.JSX.Element {
  const navigate = useNavigate()

  const {
    activeFolder, filter, checkResults, reconcileResults, reconSelected, siteSelected,
    setActiveFolder, setFilter, setCheckResults, updateCheckResult,
    setReconcileResults, clearReconcileFor, setReconSelected, setSiteSelected,
  } = useLbdirStore()
  const { folders, addFolders, removeFolders } = useFolderQueueStore()
  const [busy,         setBusy]        = useState(false)
  const [tools,        setTools]       = useState<{ shntool_available: boolean } | null>(null)
  const [toast,        setToast]       = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [ctxMenu,      setCtxMenu]     = useState<{ x: number; y: number; folder: string } | null>(null)
  const [verifiedAt,   setVerifiedAt]  = useState<Record<string, string | null>>({})
  const [hideVerified, setHideVerified] = useState(false)

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

  const handleAddSingleFolder = useCallback(async () => {
    const path = await window.api.pickDir()
    if (path) {
      addFolders([path])
      if (!activeFolder) setActiveFolder(path)
    }
  }, [activeFolder, addFolders, setActiveFolder])

  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [ctxMenu])

  const handleAddRoot = useCallback(async () => {
    const root = await window.api.pickDir()
    if (!root) return
    try {
      const data = await post('/api/pipeline/scan-tree', { root, shallow: true }) as { folders: string[] }
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
        setSiteSelected(new Set((data.results[0].site_proposals ?? []).map((p: SiteProposal) => p.site_path)))
      }
    } catch {
      showToast('Reconcile scan failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [reconcileResults, post, showToast, setReconcileResults, setReconSelected, setSiteSelected])

  const handleApplyReconcile = useCallback(async (folder: string) => {
    const reconResult = reconcileResults.find(r => r.folder === folder)
    if (!reconResult) return
    const renames = reconResult.proposals
      .filter(p => reconSelected.has(p.disk_rel))
      .map(p => ({ from: p.disk_rel, to: p.lbdir_rel }))
    const extras = reconResult.unmatched_disk
    const siteCopies = (reconResult.site_proposals ?? [])
      .filter((p: SiteProposal) => siteSelected.has(p.site_path))
      .map((p: SiteProposal) => ({ site_path: p.site_path, lbdir_rel: p.lbdir_rel }))
    setBusy(true)
    try {
      if (renames.length || siteCopies.length) {
        await post('/api/lbdir/apply_reconcile', { folder, renames, site_copies: siteCopies })
      }
      if (extras.length) {
        await post('/api/lbdir/move_extras', { folder, files: extras })
      }
      const parts: string[] = []
      if (renames.length) parts.push(`${renames.length} rename${renames.length !== 1 ? 's' : ''}`)
      if (extras.length) parts.push(`${extras.length} extra${extras.length !== 1 ? 's' : ''} moved to /extras/`)
      if (siteCopies.length) parts.push(`${siteCopies.length} copied from site/files`)
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
  }, [reconcileResults, reconSelected, siteSelected, post, showToast, clearReconcileFor, updateCheckResult])

  const filteredFolders = folders.filter(f => {
    if (filter && !f.toLowerCase().includes(filter.toLowerCase())) return false
    if (hideVerified) {
      const resolvedVerifiedAt = checkResults.find(r => r.folder === f)?.lbdir_verified_at ?? verifiedAt[f] ?? null
      if (resolvedVerifiedAt !== null) return false
    }
    return true
  })

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
        <FolderQueueRail
          label="Folders"
          countLabel={hideVerified && filteredFolders.length !== folders.length
            ? `${filteredFolders.length}/${folders.length}`
            : String(folders.length)}
          filter={filter}
          onFilterChange={setFilter}
          width={280}
          headerExtra={
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, cursor: 'pointer', userSelect: 'none', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
              <input type="checkbox" checked={hideVerified} onChange={e => setHideVerified(e.target.checked)} style={{ accentColor: 'var(--lbb-accent-mid)' }} />
              Hide verified
            </label>
          }
          onClear={() => setActiveFolder(null)}
          footer={<>
            <Button variant="primary" size="sm" icon="lbdir" block disabled={busy || !filteredFolders.length}
              onClick={() => handleProcess(filteredFolders)}>
              {busy ? 'Processing…' : 'Process all folders'}
            </Button>
            <Button variant="ghost" size="sm" icon="folder"     block onClick={handleAddSingleFolder}>Add folder…</Button>
            <Button variant="ghost" size="sm" icon="folderPlus" block onClick={handleAddRoot}>Add root folder…</Button>
          </>}
        >
          {filteredFolders.length === 0 ? (
            <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
              {folders.length === 0 ? 'No folders added' : hideVerified ? 'All folders verified' : 'No matches'}
            </div>
          ) : filteredFolders.map(f => (
            <FolderSideRow
              key={f}
              folder={f}
              checkResult={checkResults.find(r => r.folder === f)}
              verifiedAt={verifiedAt[f] ?? null}
              active={f === activeFolderStr}
              onClick={() => setActiveFolder(f)}
              onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, folder: f }) }}
            />
          ))}
        </FolderQueueRail>

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

              {/* File table + reconcile */}
              <LbdirDetail
                checkResult={checkResult}
                reconResult={reconResult}
                reconSelected={reconSelected}
                setReconSelected={setReconSelected}
                siteSelected={siteSelected}
                setSiteSelected={setSiteSelected}
                busy={busy}
                canReconcile={canReconcile}
                onReconcile={() => handleReconcile(activeFolderStr)}
                onApplyReconcile={() => handleApplyReconcile(activeFolderStr)}
              />

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
            onClick={() => { removeFolders([ctxMenu.folder]); setCtxMenu(null) }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 12px', fontSize: 'var(--lbb-fs-12-5)', cursor: 'pointer',
              border: 'none', background: 'transparent',
              color: 'var(--lbb-bad, #e05252)', borderRadius: 5, fontFamily: 'inherit',
            }}
          >Remove from list</button>
        </div>
      )}
    </div>
  )
}
