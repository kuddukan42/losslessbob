import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, Input, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useLbdirStore, LbdirState, SubTab, CheckFile, CheckResult, RetrieveResult, ReconcileProposal, ReconcileResult, ExtrasResult } from '../lib/lbdirStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type Tone      = 'ok' | 'bad' | 'warn' | 'mute' | 'info'
type ToastTone = 'ok' | 'bad' | 'info'


const STATE_LABEL: Record<LbdirState, { tone: Tone; label: string }> = {
  pass:            { tone: 'ok',   label: 'Pass' },
  fail:            { tone: 'bad',  label: 'Fail · mismatches' },
  missing_files:   { tone: 'bad',  label: 'Missing files' },
  no_lbdir:        { tone: 'warn', label: 'No lbdir · retrievable' },
  no_lb:           { tone: 'mute', label: 'No LB#' },
  shntool_missing: { tone: 'warn', label: 'Shntool not installed' },
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function CheckDot({ s }: { s: 'pass' | 'miss' | 'na' }): React.JSX.Element {
  if (s === 'pass') return <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
  if (s === 'miss') return <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />
  return <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>na</span>
}

function FolderSideRow({ folder, checkResult, active, onClick }: {
  folder: string
  checkResult: CheckResult | undefined
  active: boolean
  onClick: () => void
}): React.JSX.Element {
  const state = checkResult?.status ?? null
  const sl = state ? STATE_LABEL[state] : null
  const color = sl
    ? (sl.tone === 'ok' ? 'var(--lbb-ok-bar)' : sl.tone === 'bad' ? 'var(--lbb-bad-bar)' : sl.tone === 'warn' ? 'var(--lbb-warn-bar)' : 'var(--lbb-fg3)')
    : 'var(--lbb-border)'
  const name = folder.split('/').pop() ?? folder
  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 10px', marginBottom: 1, borderRadius: 6,
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      border: '1px solid ' + (active ? 'var(--lbb-accent-line)' : 'transparent'),
      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flex: '0 0 8px' }} />
      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
        {checkResult && (
          <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
            {checkResult.lb_number
              ? <span style={{ color: 'var(--lbb-accent-mid)' }}>LB-{String(checkResult.lb_number).padStart(5, '0')}</span>
              : <span>—</span>}
            {checkResult.total > 0 && <> · {checkResult.pass}/{checkResult.total} pass</>}
          </span>
        )}
      </span>
    </button>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenLBDIR(): React.JSX.Element {
  const navigate = useNavigate()

  const {
    activeFolder, tab, filter, checkResults, retrieveResults, reconcileResults, extrasResults,
    reconSelected, extrasSelected,
    setActiveFolder, setTab, setFilter, setCheckResults, updateCheckResult,
    setRetrieveResults, setReconcileResults, setExtrasResults, setReconSelected, setExtrasSelected,
  } = useLbdirStore()
  const { folders, addFolders } = useFolderQueueStore()
  const [busy,  setBusy]  = useState(false)
  const [tools, setTools] = useState<{ shntool_available: boolean } | null>(null)
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  useEffect(() => {
    fetch(`${BASE}/api/spectrogram/check`)
      .then(r => r.json())
      .then((d: { shntool_available: boolean }) => setTools(d))
      .catch(() => {})
  }, [])

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

  const handleCheckAll = useCallback(async () => {
    if (!folders.length) { showToast('Add folders first', 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/lbdir/check', { folders }) as { results: CheckResult[] }
      setCheckResults(data.results ?? [])
      setTab('check')
      if (activeFolder === null && data.results?.length) {
        setActiveFolder(data.results[0].folder)
      }
    } catch {
      showToast('Check failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, activeFolder, post, showToast])

  const handleRecheck = useCallback(async (folder: string) => {
    setBusy(true)
    try {
      const data = await post('/api/lbdir/check', { folders: [folder] }) as { results: CheckResult[] }
      if (data.results?.length) {
        updateCheckResult(folder, data.results[0])
      }
    } catch {
      showToast('Re-check failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [post, showToast, updateCheckResult])

  const handleRetrieve = useCallback(async () => {
    if (!folders.length) { showToast('Add folders first', 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/lbdir/retrieve', { folders }) as { results: RetrieveResult[] }
      setRetrieveResults(data.results ?? [])
      setTab('retrieve')
    } catch {
      showToast('Retrieve failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, post, showToast])

  const handleRescan = useCallback(async (folder: string) => {
    setBusy(true)
    try {
      const data = await post('/api/lbdir/reconcile', { folders: [folder] }) as { results: ReconcileResult[] }
      if (data.results?.length) {
        setReconcileResults(data.results)
        setReconSelected(new Set(data.results[0].proposals.map(p => p.disk_rel)))
      }
    } catch {
      showToast('Re-scan failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [post, showToast])

  const handleApplyRecon = useCallback(async (folder: string, proposals: ReconcileProposal[]) => {
    const renames = proposals
      .filter(p => reconSelected.has(p.disk_rel))
      .map(p => ({ from: p.disk_rel, to: p.lbdir_rel }))
    if (!renames.length) { showToast('No renames selected', 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/lbdir/apply_reconcile', { folder, renames }) as { applied: number; errors: string[] }
      showToast(`Applied ${data.applied} renames`, 'ok')
      handleRecheck(folder)
    } catch {
      showToast('Apply failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [reconSelected, post, showToast, handleRecheck])

  const handleFindExtras = useCallback(async (folder: string) => {
    setBusy(true)
    try {
      const data = await post('/api/lbdir/find_extra', { folders: [folder] }) as { results: ExtrasResult[] }
      setExtrasResults(data.results ?? [])
      if (data.results?.[0]) {
        setExtrasSelected(new Set())
      }
    } catch {
      showToast('Find extras failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [post, showToast])

  const handleDeleteExtras = useCallback(async (folder: string, extra: string[]) => {
    const files = extra.filter(f => extrasSelected.has(f))
    if (!files.length) { showToast('No files selected', 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/lbdir/delete_extra', { folder, files }) as { deleted: number; errors: string[] }
      showToast(`Deleted ${data.deleted} files`, 'ok')
      handleFindExtras(folder)
    } catch {
      showToast('Delete failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [extrasSelected, post, showToast, handleFindExtras])

  const filteredFolders = filter
    ? folders.filter(f => f.toLowerCase().includes(filter.toLowerCase()))
    : folders

  const activeFolderStr = activeFolder ?? folders[0] ?? null
  const checkResult  = activeFolderStr ? checkResults.find(r => r.folder === activeFolderStr) ?? null : null
  const reconResult  = activeFolderStr ? reconcileResults.find(r => r.folder === activeFolderStr) ?? null : null
  const extrasResult = activeFolderStr ? extrasResults.find(r => r.folder === activeFolderStr) ?? null : null

  const SUB_TABS: { k: SubTab; l: string; icon: string; hint: string }[] = [
    { k: 'check',     l: 'Check',     icon: 'verify',   hint: 'verify lbdir vs disk' },
    { k: 'retrieve',  l: 'Retrieve',  icon: 'download', hint: 'copy lbdir from cache' },
    { k: 'reconcile', l: 'Reconcile', icon: 'rename',   hint: 'find moved files' },
    { k: 'extras',    l: 'Extras',    icon: 'trash',    hint: 'files not in lbdir' },
  ]

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
            Check, retrieve, and reconcile the <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> file from the LosslessBob archive.
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

      {/* Sub-flow tabs */}
      <div style={{
        padding: '0 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'stretch', gap: 0, background: 'var(--lbb-surface)',
      }}>
        {SUB_TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{
            padding: '10px 16px 12px',
            borderBottomWidth: 2, borderBottomStyle: 'solid',
            borderBottomColor: tab === t.k ? 'var(--lbb-accent-mid)' : 'transparent',
            background: 'transparent', border: 'none',
            color: tab === t.k ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
            fontFamily: 'inherit', fontSize: 'var(--lbb-fs-12-5)', fontWeight: tab === t.k ? 600 : 500,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <Icon name={t.icon} size={13} />
            {t.l}
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 500 }}>{t.hint}</span>
          </button>
        ))}
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
                active={f === activeFolderStr}
                onClick={() => setActiveFolder(f)}
              />
            ))}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary"   size="sm" icon="lbdir"      block disabled={busy || !folders.length} onClick={handleCheckAll}>
              {busy ? 'Running…' : 'Check all folders'}
            </Button>
            <Button variant="secondary" size="sm" icon="download"   block disabled={busy || !folders.length} onClick={handleRetrieve}>Retrieve missing lbdir</Button>
            <Button variant="ghost"     size="sm" icon="folderPlus" block onClick={handleAddRoot}>Add root folder…</Button>
          </div>
        </aside>

        {/* Active sub-flow */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'auto' }}>

          {!activeFolderStr ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
              <Icon name="lbdir" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>Add folders, then click Check all folders</span>
            </div>
          ) : (
            <>
              {/* ── CHECK ────────────────────────────────────────────────────── */}
              {tab === 'check' && (
                checkResult ? (
                  <>
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
                          <Button variant="secondary" size="sm" icon="reveal"
                            onClick={() => window.api.openPath(checkResult.lbdir_path!)}>
                            Open lbdir.txt
                          </Button>
                        )}
                        <Button variant="primary" size="sm" icon="lbdir" disabled={busy}
                          onClick={() => handleRecheck(activeFolderStr)}>
                          Re-check this folder
                        </Button>
                      </div>

                      <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
                        {[
                          { l: 'Total',    v: checkResult.total,    c: undefined },
                          { l: 'Pass',     v: checkResult.pass,     c: checkResult.pass  > 0 ? 'var(--lbb-ok-fg)'  : 'var(--lbb-fg3)' },
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

                    <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
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
                  </>
                ) : (
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
                    <Icon name="lbdir" size={36} style={{ opacity: 0.15 }} />
                    <span style={{ fontSize: 'var(--lbb-fs-13)' }}>Click Check all folders to run</span>
                  </div>
                )
              )}

              {/* ── RETRIEVE ─────────────────────────────────────────────────── */}
              {tab === 'retrieve' && (
                <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                      Retrieve lbdir from cache
                    </span>
                    {retrieveResults.length > 0 && (
                      <>
                        {retrieveResults.filter(r => r.status === 'copied').length > 0 &&
                          <Pill tone="ok"   soft>{retrieveResults.filter(r => r.status === 'copied').length} copied</Pill>}
                        {retrieveResults.filter(r => r.status === 'scraped_and_copied').length > 0 &&
                          <Pill tone="warn" soft>{retrieveResults.filter(r => r.status === 'scraped_and_copied').length} scraped</Pill>}
                        {retrieveResults.filter(r => r.status === 'not_found').length > 0 &&
                          <Pill tone="bad"  soft>{retrieveResults.filter(r => r.status === 'not_found').length} not found</Pill>}
                        {retrieveResults.filter(r => r.status === 'no_lb_number').length > 0 &&
                          <Pill tone="mute" soft>{retrieveResults.filter(r => r.status === 'no_lb_number').length} no LB#</Pill>}
                      </>
                    )}
                    <div style={{ flex: 1 }} />
                    <Button variant="secondary" size="sm" icon="download" disabled={busy || !folders.length} onClick={handleRetrieve}>
                      {busy ? 'Retrieving…' : 'Re-run retrieve'}
                    </Button>
                  </div>

                  {retrieveResults.length === 0 ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
                      Click "Retrieve missing lbdir" in the sidebar to run
                    </div>
                  ) : (
                    <TableShell>
                      <colgroup>
                        <col style={{ width: 3 }} /><col /><col style={{ width: 100 }} />
                        <col style={{ width: 160 }} /><col /><col style={{ width: 100 }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <TH> </TH><TH>Folder</TH><TH>LB#</TH><TH>Result</TH><TH>Message</TH><TH align="right"> </TH>
                        </tr>
                      </thead>
                      <tbody>
                        {retrieveResults.map((r, i) => {
                          const tone: Tone = r.status === 'copied' || r.status === 'scraped_and_copied' ? 'ok' : r.status === 'not_found' ? 'bad' : 'mute'
                          const label = r.status === 'copied' ? 'Copied' : r.status === 'scraped_and_copied' ? 'Scraped + copied' : r.status === 'not_found' ? 'Not on LB.com' : 'No LB# known'
                          return (
                            <TR key={i} edge={tone === 'mute' ? undefined : tone}>
                              <TD mono style={{ color: 'var(--lbb-fg)' }}>{r.folder.split('/').pop()}</TD>
                              <TD mono style={{ color: r.lb_number ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: 600 }}>
                                {r.lb_number ? `LB-${String(r.lb_number).padStart(5, '0')}` : '—'}
                              </TD>
                              <TD><Pill tone={tone} soft dot={tone !== 'ok'}>{label}</Pill></TD>
                              <TD style={{ color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-11-5)' }}>{r.msg}</TD>
                              <TD align="right">
                                {r.status === 'no_lb_number' && (
                                  <Button size="sm" variant="secondary" icon="lookup" onClick={() => navigate('/lookup')}>Run Lookup</Button>
                                )}
                                {(r.status === 'copied' || r.status === 'scraped_and_copied') && (
                                  <Button size="sm" variant="ghost" icon="reveal" onClick={() => window.api.openPath(r.folder)}>Open</Button>
                                )}
                              </TD>
                            </TR>
                          )
                        })}
                      </tbody>
                    </TableShell>
                  )}

                  <div style={{
                    marginTop: 16, padding: '10px 14px', borderRadius: 6,
                    background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
                    fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', display: 'flex', alignItems: 'flex-start', gap: 10,
                  }}>
                    <Icon name="info" size={13} style={{ color: 'var(--lbb-info-fg)', marginTop: 1 }} />
                    <div>
                      Cached <span style={{ fontFamily: 'var(--lbb-mono)' }}>lbdir*.txt</span> files live in{' '}
                      <span style={{ fontFamily: 'var(--lbb-mono)' }}>data/attachments/LB-XXXXX/</span>. Retrieve copies the file to the audio folder. If no cache hit, the Scraper auto-fetches from LB.com.
                    </div>
                  </div>
                </div>
              )}

              {/* ── RECONCILE ────────────────────────────────────────────────── */}
              {tab === 'reconcile' && (
                <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                      Reconcile · find moved files
                    </span>
                    {reconResult && (
                      <Pill tone="info" soft>
                        {reconResult.proposals.length} proposals · {reconResult.unmatched_lbdir.length} unmatched
                      </Pill>
                    )}
                    <div style={{ flex: 1 }} />
                    <Button variant="ghost" size="sm" disabled={busy || !activeFolderStr} onClick={() => activeFolderStr && handleRescan(activeFolderStr)}>
                      Re-scan disk
                    </Button>
                    {reconResult && reconResult.proposals.length > 0 && (
                      <Button variant="primary" size="sm" icon="check" disabled={busy}
                        onClick={() => handleApplyRecon(reconResult.folder, reconResult.proposals)}>
                        Apply {Array.from(reconSelected).filter(k => reconResult.proposals.some(p => p.disk_rel === k)).length} renames
                      </Button>
                    )}
                  </div>

                  {!reconResult ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
                      Click "Re-scan disk" to find moved files
                    </div>
                  ) : reconResult.proposals.length === 0 ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
                      No proposals — files match or none could be matched by MD5
                    </div>
                  ) : (
                    <TableShell>
                      <colgroup>
                        <col style={{ width: 3 }} /><col style={{ width: 32 }} />
                        <col /><col style={{ width: 24 }} /><col /><col style={{ width: 140 }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <TH> </TH>
                          <TH><input type="checkbox"
                            checked={reconResult.proposals.every(p => reconSelected.has(p.disk_rel))}
                            onChange={e => setReconSelected(e.target.checked ? new Set(reconResult.proposals.map(p => p.disk_rel)) : new Set())}
                          /></TH>
                          <TH>Disk file (current path)</TH><TH> </TH>
                          <TH>Will move to</TH><TH>MD5</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {reconResult.proposals.map((p, i) => (
                          <TR key={i} edge="info">
                            <TD><input type="checkbox"
                              checked={reconSelected.has(p.disk_rel)}
                              onChange={e => {
                                setReconSelected(prev => {
                                  const next = new Set(prev)
                                  e.target.checked ? next.add(p.disk_rel) : next.delete(p.disk_rel)
                                  return next
                                })
                              }}
                            /></TD>
                            <TD mono style={{ color: 'var(--lbb-fg2)' }}>{p.disk_rel}</TD>
                            <TD align="center"><Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} /></TD>
                            <TD mono style={{ color: 'var(--lbb-ok-fg)' }}>{p.lbdir_rel}</TD>
                            <TD mono dim>{p.md5.slice(0, 12)}…</TD>
                          </TR>
                        ))}
                      </tbody>
                    </TableShell>
                  )}

                  <div style={{
                    marginTop: 16, padding: '12px 16px', borderRadius: 6,
                    background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
                    fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', display: 'flex', alignItems: 'flex-start', gap: 10,
                  }}>
                    <Icon name="info" size={14} style={{ color: 'var(--lbb-info-fg)', marginTop: 1 }} />
                    <div>
                      For each missing lbdir file, we MD5 every file in the folder tree and propose moves where MD5 matches.{' '}
                      <strong>Files are moved, never deleted.</strong>
                    </div>
                  </div>
                </div>
              )}

              {/* ── EXTRAS ───────────────────────────────────────────────────── */}
              {tab === 'extras' && (
                <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                      Extra files · not in lbdir
                    </span>
                    {extrasResult && <Pill tone="warn" soft>{extrasResult.extra.length} files</Pill>}
                    <div style={{ flex: 1 }} />
                    <Button variant="ghost" size="sm" disabled={busy || !activeFolderStr}
                      onClick={() => activeFolderStr && handleFindExtras(activeFolderStr)}>
                      {busy ? 'Scanning…' : 'Find extras'}
                    </Button>
                    {extrasResult && extrasResult.extra.length > 0 && (
                      <Button variant="ghost" size="sm"
                        onClick={() => setExtrasSelected(new Set(
                          extrasResult.extra.filter(f => f === '.DS_Store' || f === 'Thumbs.db')
                        ))}>
                        Select system files
                      </Button>
                    )}
                    {extrasResult && extrasResult.extra.length > 0 && (
                      <Button size="sm" icon="trash" disabled={busy || extrasSelected.size === 0}
                        onClick={() => extrasResult && handleDeleteExtras(extrasResult.folder, extrasResult.extra)}>
                        Delete {extrasSelected.size > 0 ? `${extrasSelected.size}` : ''}
                      </Button>
                    )}
                  </div>

                  {!extrasResult ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
                      Click "Find extras" to scan for files not in lbdir
                    </div>
                  ) : extrasResult.extra.length === 0 ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
                      No extra files found
                    </div>
                  ) : (
                    <TableShell>
                      <colgroup>
                        <col style={{ width: 3 }} /><col style={{ width: 32 }} />
                        <col /><col style={{ width: 110 }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <TH> </TH>
                          <TH><input type="checkbox"
                            checked={extrasResult.extra.length > 0 && extrasResult.extra.every(f => extrasSelected.has(f))}
                            onChange={e => setExtrasSelected(e.target.checked ? new Set(extrasResult.extra) : new Set())}
                          /></TH>
                          <TH>Path</TH><TH>Hint</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {extrasResult.extra.map((f, i) => {
                          const isSystem = f === '.DS_Store' || f === 'Thumbs.db'
                          return (
                            <TR key={i} edge={extrasSelected.has(f) ? 'warn' : undefined}>
                              <TD><input type="checkbox"
                                checked={extrasSelected.has(f)}
                                onChange={e => {
                                  setExtrasSelected(prev => {
                                    const next = new Set(prev)
                                    e.target.checked ? next.add(f) : next.delete(f)
                                    return next
                                  })
                                }}
                              /></TD>
                              <TD mono style={{ color: 'var(--lbb-fg)' }}>{f}</TD>
                              <TD>{isSystem ? <Pill tone="mute" soft>System</Pill> : <Pill tone="info" soft>User file</Pill>}</TD>
                            </TR>
                          )
                        })}
                      </tbody>
                    </TableShell>
                  )}

                  {extrasResult && extrasResult.extra.length > 0 && (
                    <div style={{
                      marginTop: 16, padding: '12px 16px', borderRadius: 6,
                      background: 'var(--lbb-bad-bg)', border: '1px solid var(--lbb-bad-fg)',
                      fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', display: 'flex', alignItems: 'flex-start', gap: 10,
                    }}>
                      <Icon name="info" size={14} style={{ color: 'var(--lbb-bad-fg)', marginTop: 1 }} />
                      <div>
                        <strong style={{ color: 'var(--lbb-bad-fg)' }}>Permanent deletion.</strong>
                        {' '}Selected files are removed from disk. Review carefully before confirming.
                      </div>
                    </div>
                  )}
                </div>
              )}
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
