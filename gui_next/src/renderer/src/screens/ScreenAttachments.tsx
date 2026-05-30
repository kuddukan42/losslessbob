import React, { useCallback, useEffect, useState } from 'react'
import { Icon } from '../components/Icon'
import { Button, Chip, Input, Pill } from '../components'
import { useAttachmentsStore, LbStatus } from '../lib/attachmentsStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type FileKind = 'text' | 'html' | 'image' | 'binary'
type ToastTone  = 'ok' | 'bad' | 'info'

interface LbEntry {
  lb_number:  number
  lb_status:  string
  files:      CachedFile[]
  att_status: LbStatus
}

interface CachedFile {
  filename:   string
  clean_name: string
  downloaded: number
}

interface EntryFile {
  filename:   string
  clean_name: string
  downloaded: number
}

const STATUS_COLOR: Record<LbStatus, string> = {
  current: 'var(--lbb-ok-bar)',
  stale:   'var(--lbb-warn-bar)',
  missing: 'var(--lbb-bad-bar)',
}

const STATUS_TONE: Record<LbStatus, 'ok' | 'warn' | 'bad'> = {
  current: 'ok',
  stale:   'warn',
  missing: 'bad',
}

function fileKind(filename: string): FileKind {
  const ext = filename.split('.').pop()?.toLowerCase() ?? ''
  if (['txt', 'md5', 'ffp', 'st5', 'log', 'nfo', 'md'].includes(ext)) return 'text'
  if (['html', 'htm'].includes(ext)) return 'html'
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return 'image'
  return 'binary'
}

function extIcon(kind: FileKind, ext: string): string {
  if (kind === 'image') return 'spectro'
  if (ext === 'md5' || ext === 'ffp' || ext === 'st5') return 'verify'
  return 'attachments'
}

function lbFolder(lb: number): string {
  return `LB-${String(lb).padStart(5, '0')}`
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenAttachments(): React.JSX.Element {
  const { activeLb, search, statusFilter, setActiveLb, setSearch, setStatusFilter } = useAttachmentsStore()
  const [entries,     setEntries]     = useState<LbEntry[]>([])
  const [total,       setTotal]       = useState(0)
  const [entryFiles,  setEntryFiles]  = useState<EntryFile[]>([])
  const [activeFile,  setActiveFile]  = useState<EntryFile | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [busy,        setBusy]        = useState(false)
  const [dataDir,     setDataDir]     = useState<string | null>(null)
  const [toast,       setToast]       = useState<{ msg: string; tone: ToastTone } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  // Load data_dir on mount for open-folder IPC
  useEffect(() => {
    fetch(`${BASE}/api/db/settings`)
      .then(r => r.json())
      .then((d: Record<string, string>) => { if (d.data_dir) setDataDir(d.data_dir) })
      .catch(() => {})
  }, [])

  const loadTree = useCallback(async () => {
    setBusy(true)
    try {
      await fetch(`${BASE}/api/attachments/reconcile`, { method: 'POST' })
      const r = await fetch(`${BASE}/api/attachments/cached`)
      const d = await r.json() as {
        entries: Array<{
          lb_number: number
          lb_status: string
          files: CachedFile[]
        }>
        total: number
      }
      setTotal(d.total)
      const mapped: LbEntry[] = (d.entries ?? []).map(e => ({
        ...e,
        att_status: e.files.length === 0 ? 'missing' : e.files.every(f => f.downloaded === 1) ? 'current' : 'stale' as LbStatus,
      }))
      setEntries(mapped)
      if (mapped.length > 0 && activeLb === null) setActiveLb(mapped[0].lb_number)
    } catch {
      showToast('Refresh failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [activeLb, showToast])

  // Load on mount
  useEffect(() => { loadTree() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load files for active LB
  useEffect(() => {
    if (activeLb === null) return
    setActiveFile(null)
    setFileContent(null)
    fetch(`${BASE}/api/entry/${activeLb}/files`)
      .then(r => r.json())
      .then((files: EntryFile[]) => {
        setEntryFiles(files ?? [])
        if (files?.length) setActiveFile(files[0])
      })
      .catch(() => setEntryFiles([]))
  }, [activeLb])

  // Load file content when active file changes
  useEffect(() => {
    if (!activeFile || !activeLb) return
    const kind = fileKind(activeFile.filename)
    if (kind !== 'text') { setFileContent(null); return }
    fetch(`${BASE}/api/attachment/${activeLb}/${encodeURIComponent(activeFile.clean_name || activeFile.filename)}`)
      .then(r => r.text())
      .then(setFileContent)
      .catch(() => setFileContent(null))
  }, [activeFile, activeLb])

  const handleRedownload = useCallback(async (lb: number) => {
    setBusy(true)
    try {
      await fetch(`${BASE}/api/entry/${lb}/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true }),
      })
      showToast(`Re-download of ${lbFolder(lb)} started`, 'info')
      setTimeout(loadTree, 2000)
    } catch {
      showToast('Re-download failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [loadTree, showToast])

  const handleOpenFolder = useCallback((lb: number) => {
    if (!dataDir) { showToast('Data directory unknown', 'info'); return }
    const path = `${dataDir}/attachments/${lbFolder(lb)}`
    window.api.openPath(path)
  }, [dataDir, showToast])

  const handleCopyContents = useCallback(() => {
    if (!fileContent) return
    navigator.clipboard.writeText(fileContent)
      .then(() => showToast('Copied', 'ok'))
      .catch(() => showToast('Copy failed', 'bad'))
  }, [fileContent, showToast])

  const handleOpenExternal = useCallback(() => {
    if (!activeFile || !activeLb) return
    const lb = lbFolder(activeLb)
    const path = dataDir
      ? `${dataDir}/attachments/${lb}/${activeFile.filename}`
      : `${BASE}/api/attachment/${activeLb}/${encodeURIComponent(activeFile.filename)}`
    window.api.openPath(path)
  }, [activeFile, activeLb, dataDir])

  const filteredEntries = entries.filter(e => {
    if (statusFilter !== 'all' && e.att_status !== statusFilter) return false
    if (search) {
      const q = search.toLowerCase()
      return lbFolder(e.lb_number).toLowerCase().includes(q)
    }
    return true
  })

  const counts = {
    current: entries.filter(e => e.att_status === 'current').length,
    stale:   entries.filter(e => e.att_status === 'stale').length,
    missing: entries.filter(e => e.att_status === 'missing').length,
  }

  const activeLbEntry = activeLb !== null ? entries.find(e => e.lb_number === activeLb) : null
  const kind     = activeFile ? fileKind(activeFile.filename) : null
  const ext      = activeFile ? (activeFile.filename.split('.').pop()?.toLowerCase() ?? '') : ''
  const fileUrl  = activeFile && activeLb
    ? `${BASE}/api/attachment/${activeLb}/${encodeURIComponent(activeFile.clean_name || activeFile.filename)}`
    : null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}><Icon name="attachments" size={18} /></div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Attachments</h1>
              <Pill tone="mute" soft>data/attachments/</Pill>
            </div>
            <div style={{ fontSize: 12, color: 'var(--lbb-fg3)', marginTop: 2 }}>
              Cached files (lbdir, ffp, md5, info, html, cover art) — {entries.length.toLocaleString()} / {total.toLocaleString()} LBs
            </div>
          </div>
          <div style={{ flex: 1 }} />
          {counts.current > 0 && <Pill tone="ok"   soft>{counts.current.toLocaleString()} current</Pill>}
          {counts.stale   > 0 && <Pill tone="warn" soft>{counts.stale} stale</Pill>}
          {counts.missing > 0 && <Pill tone="bad"  soft>{counts.missing} missing</Pill>}
          <Button variant="ghost" size="sm" icon="refresh" disabled={busy} onClick={loadTree}>
            {busy ? 'Refreshing…' : 'Refresh tree'}
          </Button>
        </div>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '260px 280px 1fr', minHeight: 0 }}>

        {/* LB rail */}
        <aside style={{
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
            <Input
              icon="search" placeholder="Jump to LB# or title…" size="sm" style={{ width: '100%' }}
              value={search} onChange={e => setSearch(e.target.value)}
            />
            <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
              <Chip active={statusFilter === 'all'}     size="sm" count={entries.length}  onClick={() => setStatusFilter('all')}>All</Chip>
              <Chip active={statusFilter === 'current'} size="sm" count={counts.current}  onClick={() => setStatusFilter('current')}>Current</Chip>
              <Chip active={statusFilter === 'stale'}   size="sm" count={counts.stale}    onClick={() => setStatusFilter('stale')}>Stale</Chip>
              <Chip active={statusFilter === 'missing'} size="sm" count={counts.missing}  onClick={() => setStatusFilter('missing')}>Missing</Chip>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {filteredEntries.length === 0 ? (
              <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 11 }}>
                {busy ? 'Loading…' : entries.length === 0 ? 'Click Refresh tree to load' : 'No matches'}
              </div>
            ) : filteredEntries.map(e => (
              <button key={e.lb_number} onClick={() => setActiveLb(e.lb_number)} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 10px', marginBottom: 1, borderRadius: 6,
                background: e.lb_number === activeLb ? 'var(--lbb-accent-soft)' : 'transparent',
                color: e.lb_number === activeLb ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                border: '1px solid ' + (e.lb_number === activeLb ? 'var(--lbb-accent-line)' : 'transparent'),
                textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: STATUS_COLOR[e.att_status], flex: '0 0 6px' }} />
                <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600, fontSize: 11.5 }}>{lbFolder(e.lb_number)}</span>
                </span>
                <span style={{ fontSize: 10, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>{e.files.length}</span>
              </button>
            ))}
          </div>
        </aside>

        {/* File list for active LB */}
        <aside style={{
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          {activeLb === null ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)', fontSize: 12 }}>
              Select an LB entry
            </div>
          ) : (
            <>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--lbb-border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 13, fontWeight: 700, color: 'var(--lbb-accent-mid)' }}>
                    {lbFolder(activeLb)}
                  </span>
                  {activeLbEntry && (
                    <Pill tone={STATUS_TONE[activeLbEntry.att_status]} soft>{activeLbEntry.att_status}</Pill>
                  )}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', marginTop: 2, fontFamily: 'var(--lbb-mono)' }}>
                  {entryFiles.length} files · attachments/{lbFolder(activeLb)}/
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
                {entryFiles.length === 0 ? (
                  <div style={{ padding: '16px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 11 }}>
                    No cached files
                  </div>
                ) : entryFiles.map((f, i) => {
                  const k = fileKind(f.filename)
                  const fext = f.filename.split('.').pop()?.toLowerCase() ?? ''
                  return (
                    <button key={i} onClick={() => setActiveFile(f)} style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                      padding: '6px 10px', marginBottom: 1, borderRadius: 6,
                      background: activeFile?.filename === f.filename ? 'var(--lbb-accent-soft)' : 'transparent',
                      color: activeFile?.filename === f.filename ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                      border: '1px solid ' + (activeFile?.filename === f.filename ? 'var(--lbb-accent-line)' : 'transparent'),
                      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
                    }}>
                      <Icon name={extIcon(k, fext)} size={11} style={{ color: 'var(--lbb-fg3)' }} />
                      <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--lbb-mono)', fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {f.clean_name || f.filename}
                      </span>
                      {f.downloaded !== 1 && <span style={{ fontSize: 9, color: 'var(--lbb-warn-fg)' }}>not cached</span>}
                    </button>
                  )
                })}
              </div>
              <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Button variant="primary" size="sm" icon="refresh" block disabled={busy}
                  onClick={() => handleRedownload(activeLb)}>
                  Re-download {lbFolder(activeLb)}
                </Button>
                <Button variant="ghost" size="sm" icon="reveal" block
                  onClick={() => handleOpenFolder(activeLb)}>
                  Open folder…
                </Button>
              </div>
            </>
          )}
        </aside>

        {/* Viewer */}
        <section style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>

          {activeFile && activeLb ? (
            <>
              {/* File meta + actions */}
              <div style={{
                padding: '10px 24px', borderBottom: '1px solid var(--lbb-border)',
                display: 'flex', alignItems: 'center', gap: 12,
                background: 'var(--lbb-surface)', fontSize: 11.5, flexShrink: 0,
              }}>
                <Icon name={extIcon(kind!, ext)} size={14} style={{ color: 'var(--lbb-fg2)' }} />
                <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600, color: 'var(--lbb-fg)' }}>
                  {activeFile.clean_name || activeFile.filename}
                </span>
                <div style={{ flex: 1 }} />
                {kind === 'text' && fileContent !== null && (
                  <Button variant="ghost" size="sm" icon="copy" onClick={handleCopyContents}>Copy contents</Button>
                )}
                <Button variant="ghost" size="sm" icon="reveal" onClick={handleOpenExternal}>Open externally</Button>
              </div>

              {/* Type-specific viewer */}
              {kind === 'text' && (
                <pre style={{
                  margin: 0, flex: 1, padding: '20px 24px',
                  fontFamily: 'var(--lbb-mono)', fontSize: 12.5, lineHeight: 1.6,
                  color: 'var(--lbb-fg)', whiteSpace: 'pre-wrap',
                  background: 'var(--lbb-bg)', overflow: 'auto',
                }}>
                  {fileContent ?? 'Loading…'}
                </pre>
              )}

              {kind === 'html' && fileUrl && (
                <iframe
                  src={fileUrl}
                  sandbox="allow-same-origin"
                  style={{ flex: 1, border: 'none', background: '#fff' }}
                  title={activeFile.filename}
                />
              )}

              {kind === 'image' && fileUrl && (
                <div style={{
                  flex: 1, padding: 24, background: 'var(--lbb-bg)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'auto',
                }}>
                  <img
                    src={fileUrl}
                    alt={activeFile.filename}
                    style={{ maxWidth: '100%', maxHeight: '100%', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,.25)' }}
                  />
                </div>
              )}

              {kind === 'binary' && (
                <div style={{
                  flex: 1, padding: 40, background: 'var(--lbb-bg)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14,
                }}>
                  <div style={{
                    width: 72, height: 72, borderRadius: 12,
                    background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'var(--lbb-fg3)',
                  }}><Icon name="attachments" size={32} /></div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 13, fontWeight: 600 }}>{activeFile.filename}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 4 }}>Binary file · no in-app preview</div>
                  </div>
                  <Button variant="primary" size="sm" icon="reveal" onClick={handleOpenExternal}>Open externally</Button>
                </div>
              )}
            </>
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="attachments" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 13 }}>Select an LB entry and file to preview</span>
            </div>
          )}
        </section>
      </div>

      {toast && (
        <div
          style={{
            position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
            background: toast.tone === 'ok' ? 'var(--lbb-ok-bar)' : toast.tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)',
            color: '#fff', padding: '9px 18px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
            pointerEvents: 'none',
          }}
          ref={(el: HTMLDivElement | null) => { if (el) setTimeout(() => setToast(null), 3500) }}
        >{toast.msg}</div>
      )}
    </div>
  )
}
