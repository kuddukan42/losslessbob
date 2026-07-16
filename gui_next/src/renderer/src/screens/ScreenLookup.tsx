import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Chip, Pill } from '../components'
import { useLookupStore, LookupSource, LookupSummaryRow, LookupDetail, type LookupFilterState } from '../lib/lookupStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'
import {
  LookupSummaryTable, LookupChecksumTable, LookupNotFoundHint,
} from '../components/pipeline/LookupDetail'
import { STATE_TONE, apiStatusToState, XREF_TONE } from '../components/pipeline/lookupState'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type ToastTone   = 'ok' | 'bad' | 'info'

const SRC_ICON: Record<LookupSource['kind'], string> = {
  folder:    'folder',
  file:      'attachments',
  listbox:   'search',
  clipboard: 'copy',
}

// ── ListboxModal ───────────────────────────────────────────────────────────────

function ListboxModal({ onDone }: { onDone: (text: string) => void }): React.JSX.Element {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={() => onDone('')}
    >
      <div
        style={{
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
          borderRadius: 12, padding: 20, width: 560, maxWidth: '94vw',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-15)' }}>{t('lookup.listbox.title')}</div>
        <textarea
          autoFocus
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={t('lookup.listbox.placeholder')}
          style={{
            width: '100%', height: 220, resize: 'vertical',
            fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', lineHeight: 1.5,
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            borderRadius: 6, padding: 10, color: 'var(--lbb-fg)',
          }}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={() => onDone('')}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" disabled={!text.trim()} onClick={() => onDone(text)}>{t('lookup.listbox.lookup')}</Button>
        </div>
      </div>
    </div>
  )
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function SourceRow({ src, active, onClick, onContextMenu }: { src: LookupSource; active: boolean; onClick: () => void; onContextMenu?: (e: React.MouseEvent) => void }): React.JSX.Element {
  return (
    <button onClick={onClick} onContextMenu={onContextMenu} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 10px', marginBottom: 1, borderRadius: 6,
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      border: '1px solid ' + (active ? 'var(--lbb-accent-line)' : 'transparent'),
      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
    }}>
      <Icon name={SRC_ICON[src.kind]} size={12} style={{ color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)' }} />
      <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)' }}>
        {src.name}
      </span>
    </button>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenLookup(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { sources, summary, detail, filter, filterMy, activeSource, addSource, removeSource, clearSources, setResult, setFolderList, setFilter, setFilterMy, setActiveSource } = useLookupStore()
  const { folders: queueFolders } = useFolderQueueStore()

  // Sync shared folder queue into sources so folders added on other tabs appear here too
  useEffect(() => {
    if (!queueFolders.length) return
    const { sources: cur, addSource: add, folderList: curFL, setFolderList: setFL } = useLookupStore.getState()
    const existingNames = new Set(cur.filter(s => s.kind === 'folder').map(s => s.name))
    const toAdd = queueFolders.filter(f => !existingNames.has(f.split('/').pop() ?? f))
    if (!toAdd.length) return
    for (const folder of toAdd) {
      const name = folder.split('/').pop() ?? folder
      fetch(`${BASE}/api/lookup/scan_folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [folder] }),
      })
        .then(r => r.json() as Promise<{ content: string }>)
        .then(d => {
          if (useLookupStore.getState().sources.some(s => s.path === folder)) return
          add({ kind: 'folder', name, content: d.content ?? '', active: true, path: folder })
        })
        .catch(() => {
          if (useLookupStore.getState().sources.some(s => s.path === folder)) return
          add({ kind: 'folder', name, content: '', active: true, path: folder })
        })
    }
    setFL([...new Set([...curFL, ...toAdd])])
  }, [queueFolders])

  const [busy,           setBusy]           = useState(false)
  const [showListbox,    setShowListbox]     = useState(false)
  const [toast,          setToast]          = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<Set<string>>(new Set())
  const [ctxMenu,        setCtxMenu]        = useState<{ x: number; y: number; idx: number } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [ctxMenu])

  const runLookup = useCallback(async (text: string, sourceName: string, checksumToFolder?: Map<string, string>) => {
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await fetch(`${BASE}/api/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const d = await r.json() as { summary: { lb_summary: LookupSummaryRow[]; matched: number; given: number; lb_numbers_found: number[] }; detail: LookupDetail[] }
      // Tag each detail row with source_file (full path) so ScreenRename can map checksums → folders
      const taggedDetail = (checksumToFolder && checksumToFolder.size > 0)
        ? (d.detail ?? []).map(row => {
            const folderPath = checksumToFolder.get(row.checksum.toLowerCase())
            return folderPath ? { ...row, source_file: `${folderPath}/${row.filename}` } : row
          })
        : (d.detail ?? [])
      setResult(d.summary, taggedDetail)
      const folders = [...new Set(
        taggedDetail
          .filter(row => row.source_file)
          .map(row => {
            const parts = (row.source_file ?? '').split('/')
            parts.pop()
            return parts.join('/')
          })
          .filter(Boolean)
      )]
      if (folders.length) setFolderList(folders)
    } catch {
      showToast(t('lookup.toast.lookupFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }, [setResult, setFolderList, showToast])

  const handleClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) { showToast(t('lookup.toast.clipboardEmpty'), 'info'); return }
      const src: LookupSource = { kind: 'clipboard', name: `Clipboard · ${text.split('\n').filter(Boolean).length} lines`, content: text, active: true }
      addSource(src)
      await runLookup(text, src.name)
    } catch {
      showToast(t('lookup.toast.clipboardFailed'), 'bad')
    }
  }, [addSource, runLookup, showToast])

  const handleListbox = useCallback((text: string) => {
    setShowListbox(false)
    if (!text.trim()) return
    const src: LookupSource = { kind: 'listbox', name: `Pasted listbox · ${text.split('\n').filter(Boolean).length} lines`, content: text, active: true }
    addSource(src)
    runLookup(text, src.name)
  }, [addSource, runLookup])

  const handleFiles = useCallback(async () => {
    const files = await window.api.pickAndReadFiles({
      title: 'Select checksum files',
      filters: [
        { name: 'Checksum files', extensions: ['ffp', 'md5', 'st5', 'txt', 'sha1'] },
        { name: 'All files', extensions: ['*'] },
      ],
    })
    if (!files.length) return
    const filteredFiles = filterMy
      ? files.filter(f => !f.path.toLowerCase().includes('_mychecksums'))
      : files
    const content = (filteredFiles.length ? filteredFiles : files).map(f => f.content).join('\n')
    const names = files.map(f => f.path.split('/').pop() ?? f.path)
    for (const f of files) {
      addSource({ kind: 'file', name: f.path.split('/').pop() ?? f.path, content: f.content, active: true })
    }
    await runLookup(content, names.join(', '))
  }, [filterMy, addSource, runLookup])

  const handleFolders = useCallback(async () => {
    const picked = await window.api.pickFolders()
    if (!picked.length) return
    const scanned: string[] = []
    for (const folder of picked) {
      if (useLookupStore.getState().sources.some(s => s.path === folder)) continue
      const name = folder.split('/').pop() ?? folder
      try {
        const r = await fetch(`${BASE}/api/lookup/scan_folders`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [folder] }),
        })
        const d = await r.json() as { content: string; files: string[] }
        addSource({ kind: 'folder', name, content: d.content ?? '', active: true, path: folder })
        scanned.push(folder)
        if (!d.content?.trim()) showToast(t('lookup.toast.noChecksumsInFolder', { name }), 'info')
      } catch {
        addSource({ kind: 'folder', name, content: '', active: true, path: folder })
        showToast(t('lookup.toast.folderScanFailed'), 'bad')
      }
    }
    if (scanned.length) {
      const existing = useLookupStore.getState().folderList
      setFolderList([...new Set([...existing, ...scanned])])
    }
  }, [addSource, showToast, setFolderList])

  const handleSingleFolder = useCallback(async () => {
    const folder = await window.api.pickDir()
    if (!folder) return
    if (useLookupStore.getState().sources.some(s => s.path === folder)) return
    const name = folder.split('/').pop() ?? folder
    try {
      const r = await fetch(`${BASE}/api/lookup/scan_folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [folder] }),
      })
      const d = await r.json() as { content: string; files: string[] }
      addSource({ kind: 'folder', name, content: d.content ?? '', active: true, path: folder })
      const existing = useLookupStore.getState().folderList
      setFolderList([...new Set([...existing, folder])])
      if (!d.content?.trim()) showToast(t('lookup.toast.noChecksumsInFolder', { name }), 'info')
    } catch {
      addSource({ kind: 'folder', name, content: '', active: true, path: folder })
      showToast(t('lookup.toast.folderScanFailed'), 'bad')
    }
  }, [addSource, showToast, setFolderList, t])

  const handleLookupAll = useCallback(async () => {
    if (!sources.length) { showToast(t('lookup.toast.addSourcesFirst'), 'info'); return }
    const activeSources = sources.filter(s => s.content)
    const combined = activeSources.map(s => s.content).join('\n')
    if (!combined.trim()) {
      showToast(t('lookup.toast.noTextContent'), 'info')
      return
    }
    // Build checksum → folder path map so Rename can link detail rows to real folder paths
    const checksumToFolder = new Map<string, string>()
    for (const src of activeSources) {
      if (!src.path) continue
      const hexMatches = src.content.match(/[0-9a-f]{32,64}/gi) ?? []
      for (const chk of hexMatches) {
        const lc = chk.toLowerCase()
        if (!checksumToFolder.has(lc)) checksumToFolder.set(lc, src.path)
      }
    }
    await runLookup(combined, 'all sources', checksumToFolder)
  }, [sources, runLookup, showToast])

  const handleGenerate = useCallback(async () => {
    const folders = sources.filter(s => s.kind === 'folder').map(s => s.name)
    if (!folders.length) { showToast(t('lookup.toast.addSourcesFirst'), 'info'); return }
    showToast(t('lookup.toast.useVerify'), 'info')
  }, [sources, showToast])

  const handleCopySummary = useCallback(() => {
    if (!summary?.lb_summary.length) return
    const lines = summary.lb_summary.map(r =>
      [r.lb_number, r.given, r.matched, r.not_found, r.missing_from_set, r.duplicates, r.xrefs, r.status].join('\t')
    )
    navigator.clipboard.writeText(lines.join('\n'))
      .then(() => showToast(t('lookup.toast.summaryCopied'), 'ok'))
      .catch(() => showToast(t('lookup.toast.copyFailed'), 'bad'))
  }, [summary, showToast])

  const handleExportCsv = useCallback(() => {
    if (!summary?.lb_summary.length) return
    const header = 'LB#\tGiven\tMatched\tNot Found\tMissing\tDups\tXrefs\tStatus'
    const rows = summary.lb_summary.map(r =>
      [r.lb_number, r.given, r.matched, r.not_found, r.missing_from_set, r.duplicates, r.xrefs, r.status].join('\t')
    )
    const content = [header, ...rows].join('\n')
    const blob = new Blob([content], { type: 'text/tab-separated-values' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'lookup_results.tsv'
    a.click()
    URL.revokeObjectURL(a.href)
  }, [summary])

  const handleAddToWishlist = useCallback(async (lbNumber: number) => {
    try {
      await fetch(`${BASE}/api/wishlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: lbNumber }),
      })
      showToast(t('lookup.toast.addedToWishlist', { lb: lbNumber }), 'ok')
    } catch {
      showToast(t('lookup.toast.wishlistFailed'), 'bad')
    }
  }, [showToast])

  const summaryRows = summary?.lb_summary ?? []
  const detailRows  = detail ?? []

  const filteredSummary = summaryRows.filter(r => {
    // "Cross-refs" (A12) counts/filters on the copy-level matched_xref dimension,
    // not a lookup status — handled separately from apiStatusToState (D1).
    if (filter === 'xref') {
      if (!(r.matched_xref > 0)) return false
    } else if (filter !== 'all' && apiStatusToState(r.status) !== filter) {
      return false
    }
    if (categoryFilter.size > 0 && !categoryFilter.has(r.lb_category ?? '')) return false
    return true
  })

  const filteredDetail = filterMy
    ? detailRows.filter(r => {
        const fn = r.source_file ?? r.filename ?? ''
        return !fn.toLowerCase().includes('_mychecksums')
      })
    : detailRows

  const counts = summaryRows.reduce<Record<string, number>>((a, r) => {
    const s = apiStatusToState(r.status)
    a[s] = (a[s] || 0) + 1
    a.total = (a.total || 0) + 1
    return a
  }, {})
  // A12: "Cross-refs" counts rows with matched_xref > 0 — a copy-level dimension,
  // not a status, so it's tallied separately from the apiStatusToState reduce above.
  counts.xref = summaryRows.filter(r => r.matched_xref > 0).length

  const totalSums = summary?.given ?? 0

  const ownedVerifiedCount   = summaryRows.filter(r => r.owned && r.lbdir_verified).length
  const ownedUnverifiedCount = summaryRows.filter(r => r.owned && !r.lbdir_verified).length

  const statusBars: Array<{ k: LookupFilterState; l: string }> = [
    { k: 'matched',    l: 'Matched'    },
    { k: 'incomplete', l: 'Incomplete' },
    { k: 'notfound',   l: 'Not found'  },
    { k: 'duplicate',  l: 'Duplicates' },
    { k: 'xref',       l: 'Cross-refs' },
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
          background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="lookup" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>{t('lookup.title')}</h1>
            <Pill tone="mute" soft>{t('lookup.subtitle')}</Pill>
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('lookup.desc')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {summary && (
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
            {t('lookup.countLabel', { count: totalSums.toLocaleString(), lbs: summaryRows.length })}
          </span>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Sources rail */}
        <aside style={{
          width: 280, flex: '0 0 280px',
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
            <div style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 8 }}>
              {t('lookup.sources.label')}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 8 }}>
              <Button variant="secondary" size="sm" icon="copy"        block disabled={busy} onClick={handleClipboard}>{t('lookup.sources.clipboard')}</Button>
              <Button variant="secondary" size="sm" icon="search"      block disabled={busy} onClick={() => setShowListbox(true)}>{t('lookup.sources.listbox')}</Button>
              <Button variant="secondary" size="sm" icon="attachments" block disabled={busy} onClick={handleFiles}>{t('lookup.sources.files')}</Button>
              <Button variant="secondary" size="sm" icon="folderPlus"  block disabled={busy} onClick={handleFolders}>{t('lookup.sources.folders')}</Button>
              <Button variant="secondary" size="sm" icon="folder"      block disabled={busy} onClick={handleSingleFolder} style={{ gridColumn: 'span 2' }}>{t('common.addFolder')}</Button>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
              <input type="checkbox" checked={filterMy} onChange={() => setFilterMy(!filterMy)} />
              {t('lookup.sources.filterMy')}
            </label>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {sources.length === 0 ? (
              <div style={{ padding: '16px 10px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
                {t('lookup.sources.noSources')}
              </div>
            ) : sources.map((s, i) => (
              <SourceRow key={i} src={s} active={i === activeSource} onClick={() => setActiveSource(i)} onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, idx: i }) }} />
            ))}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary"   size="sm" icon="lookup" block disabled={busy || !sources.length} onClick={handleLookupAll}>
              {busy ? t('lookup.sources.lookingUp') : t('lookup.sources.lookupAll')}
            </Button>
            <Button variant="secondary" size="sm" icon="plus"   block disabled={busy} onClick={handleGenerate}>{t('lookup.sources.generate')}</Button>
            <Button variant="ghost"     size="sm" icon="trash"  block disabled={busy} onClick={clearSources}>{t('lookup.sources.clearSources')}</Button>
          </div>
        </aside>

        {/* Main pane */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>

          {/* Status counters */}
          {summary ? (
            <div style={{
              padding: '12px 24px', borderBottom: '1px solid var(--lbb-border)',
              background: 'var(--lbb-surface)',
              display: 'flex', alignItems: 'stretch', gap: 8,
            }}>
              {statusBars.map(c => {
                const tone   = c.k === 'xref' ? XREF_TONE : STATE_TONE[c.k]
                const n      = counts[c.k] || 0
                const active = filter === c.k
                return (
                  <button key={c.k} onClick={() => setFilter(active ? 'all' : c.k)} style={{
                    flex: 1, padding: '8px 12px', borderRadius: 6,
                    background: active ? `var(--lbb-${tone.tone}-bg)` : 'var(--lbb-surface)',
                    border: `1px solid ${active ? tone.color : 'var(--lbb-border)'}`,
                    cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                    display: 'flex', flexDirection: 'column', gap: 2,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: tone.color }} />
                      <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: tone.color, letterSpacing: 0.06, textTransform: 'uppercase' }}>
                        {c.l}
                      </span>
                    </div>
                    <span style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg)', lineHeight: 1.1 }}>
                      {n}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div style={{
              padding: '12px 24px', borderBottom: '1px solid var(--lbb-border)',
              background: 'var(--lbb-surface)', display: 'flex', alignItems: 'center',
              color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)',
            }}>
              {busy ? t('lookup.status.running') : t('lookup.status.addSourcesFirst')}
            </div>
          )}

          {/* Type filter chips — only when results are present */}
          {summary && (
            <div style={{
              padding: '6px 24px', borderBottom: '1px solid var(--lbb-border)',
              background: 'var(--lbb-surface)', display: 'flex', gap: 6, flexWrap: 'wrap',
            }}>
              {(['concert','interview'] as const).map(cat => {
                const n = summaryRows.filter(r => r.lb_category === cat).length
                return (
                  <Chip key={cat} size="sm"
                    active={categoryFilter.has(cat)}
                    count={n}
                    onClick={() => setCategoryFilter(prev => {
                      const next = new Set(prev)
                      next.has(cat) ? next.delete(cat) : next.add(cat)
                      return next
                    })}
                  >
                    {cat.charAt(0).toUpperCase() + cat.slice(1)}
                  </Chip>
                )
              })}
            </div>
          )}

          {/* Scrollable body */}
          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>

            {summary && (
              <>
                {/* Owned banner */}
                {(ownedVerifiedCount + ownedUnverifiedCount) > 0 && (
                  <div style={{
                    margin: '12px 24px 0', padding: '10px 14px', borderRadius: 6,
                    background: 'var(--lbb-warn-bg)', border: '1px solid var(--lbb-warn-bar)',
                    fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                  }}>
                    <Icon name="info" size={14} style={{ color: 'var(--lbb-warn-fg)', marginTop: 1 }} />
                    <span>
                      {ownedVerifiedCount > 0 && (
                        <span>
                          <strong style={{ color: 'var(--lbb-ok-fg)' }}>
                            {t('lookup.owned.verifiedBanner', { count: ownedVerifiedCount })}
                          </strong>
                          {' — '}{t('lookup.owned.verifiedNote')}{ownedUnverifiedCount > 0 ? '  ' : ''}
                        </span>
                      )}
                      {ownedUnverifiedCount > 0 && (
                        <span>
                          <strong style={{ color: 'var(--lbb-warn-fg)' }}>
                            {t('lookup.owned.unverifiedBanner', { count: ownedUnverifiedCount })}
                          </strong>
                          {' — '}{t('lookup.owned.unverifiedNote')}
                        </span>
                      )}
                    </span>
                  </div>
                )}

                {/* Summary table */}
                <div style={{ padding: '16px 24px 6px', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                    {t('lookup.status.matchSummary')}
                  </span>
                  <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{t('lookup.status.matchSummarySub')}</span>
                  <div style={{ flex: 1 }} />
                  <Button variant="ghost" size="sm" icon="copy" onClick={handleCopySummary}>{t('lookup.status.copySummary')}</Button>
                  <Button variant="ghost" size="sm" icon="download" onClick={handleExportCsv}>{t('lookup.status.exportCsv')}</Button>
                </div>
                <div style={{ padding: '0 24px' }}>
                  <LookupSummaryTable summaryRows={filteredSummary} detail={detail} onAddToWishlist={handleAddToWishlist} />
                </div>

                {/* Checksum detail */}
                <div style={{ padding: '20px 24px 6px', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                    {t('lookup.status.checksumDetail')}
                  </span>
                  <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
                    {t('lookup.status.rows', { count: filteredDetail.length })}
                  </span>
                  <div style={{ flex: 1 }} />
                </div>
                <div style={{ padding: '0 24px 24px' }}>
                  <LookupChecksumTable summaryRows={summaryRows} detailRows={filteredDetail} />

                  {filteredDetail.length === 0 && (
                    <LookupNotFoundHint style={{ marginTop: 14 }} />
                  )}
                </div>
              </>
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: '10px 24px', borderTop: '1px solid var(--lbb-border)',
            display: 'flex', alignItems: 'center', gap: 8, background: 'var(--lbb-surface)',
          }}>
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
              {t('lookup.footer.autoPopulate')}
            </span>
            <div style={{ flex: 1 }} />
            <Button variant="ghost"     size="sm" disabled={busy || !sources.length} onClick={handleLookupAll}>{t('lookup.footer.relookupAll')}</Button>
            <Button variant="secondary" size="sm" icon="rename" onClick={() => navigate('/rename')}>{t('lookup.footer.goToRename')}</Button>
          </div>
        </section>
      </div>

      {showListbox && <ListboxModal onDone={handleListbox} />}

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
            onClick={() => { removeSource(ctxMenu.idx); setCtxMenu(null) }}
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
