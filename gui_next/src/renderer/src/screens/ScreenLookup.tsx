import React, { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useLookupStore, LookupSource, LookupSummaryRow, LookupDetail } from '../lib/lookupStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type LookupState = 'matched' | 'incomplete' | 'notfound' | 'duplicate' | 'xref'
type ToastTone   = 'ok' | 'bad' | 'info'

// ── Lookup state → tone/label/color ──────────────────────────────────────────

const STATE_TONE: Record<LookupState, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; label: string; color: string }> = {
  matched:    { tone: 'ok',   label: 'Matched',    color: 'var(--lbb-ok-fg)'   },
  incomplete: { tone: 'warn', label: 'Incomplete', color: 'var(--lbb-warn-fg)' },
  notfound:   { tone: 'bad',  label: 'Not found',  color: 'var(--lbb-bad-fg)'  },
  duplicate:  { tone: 'warn', label: 'Duplicate',  color: '#a08200'             },
  xref:       { tone: 'info', label: 'XRef',       color: 'var(--lbb-info-fg)' },
}

function apiStatusToState(status: string): LookupState {
  if (status === 'MATCHED')               return 'matched'
  if (status === 'MATCHED (INCOMPLETE)')  return 'incomplete'
  if (status === 'NOT FOUND')             return 'notfound'
  if (status === 'DUPLICATE')             return 'duplicate'
  if (status === 'XREF')                  return 'xref'
  return 'notfound'
}

const SRC_ICON: Record<LookupSource['kind'], string> = {
  folder:    'folder',
  file:      'attachments',
  listbox:   'search',
  clipboard: 'copy',
}

// ── ListboxModal ───────────────────────────────────────────────────────────────

function ListboxModal({ onDone }: { onDone: (text: string) => void }): React.JSX.Element {
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
        <div style={{ fontWeight: 700, fontSize: 15 }}>Paste checksum text</div>
        <textarea
          autoFocus
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Paste .ffp / .md5 / .st5 lines here…"
          style={{
            width: '100%', height: 220, resize: 'vertical',
            fontFamily: 'var(--lbb-mono)', fontSize: 12, lineHeight: 1.5,
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            borderRadius: 6, padding: 10, color: 'var(--lbb-fg)',
          }}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={() => onDone('')}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={!text.trim()} onClick={() => onDone(text)}>Lookup</Button>
        </div>
      </div>
    </div>
  )
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function SourceRow({ src, active, onClick }: { src: LookupSource; active: boolean; onClick: () => void }): React.JSX.Element {
  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 10px', marginBottom: 1, borderRadius: 6,
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      border: '1px solid ' + (active ? 'var(--lbb-accent-line)' : 'transparent'),
      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
    }}>
      <Icon name={SRC_ICON[src.kind]} size={12} style={{ color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)' }} />
      <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>
        {src.name}
      </span>
    </button>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenLookup(): React.JSX.Element {
  const navigate = useNavigate()
  const { sources, summary, detail, filter, filterMy, activeSource, addSource, clearSources, setResult, setFolderList, setFilter, setFilterMy, setActiveSource } = useLookupStore()

  const [busy,       setBusy]       = useState(false)
  const [showListbox,setShowListbox] = useState(false)
  const [toast,      setToast]      = useState<{ msg: string; tone: ToastTone } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  const runLookup = useCallback(async (text: string, sourceName: string) => {
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await fetch(`${BASE}/api/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const d = await r.json() as { summary: { lb_summary: LookupSummaryRow[]; matched: number; given: number; lb_numbers_found: number[] }; detail: LookupDetail[] }
      setResult(d.summary, d.detail)
      const folders = [...new Set(
        (d.detail ?? [])
          .filter(row => row.source_file)
          .map(row => {
            const parts = (row.source_file ?? '').split('/')
            parts.pop()
            return parts.join('/')
          })
          .filter(Boolean)
      )]
      setFolderList(folders)
    } catch {
      showToast('Lookup failed', 'bad')
    } finally {
      setBusy(false)
    }
  }, [setResult, setFolderList, showToast])

  const handleClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) { showToast('Clipboard is empty', 'info'); return }
      const src: LookupSource = { kind: 'clipboard', name: `Clipboard · ${text.split('\n').filter(Boolean).length} lines`, content: text, active: true }
      addSource(src)
      await runLookup(text, src.name)
    } catch {
      showToast('Could not read clipboard', 'bad')
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
    for (const folder of picked) {
      const name = folder.split('/').pop() ?? folder
      try {
        const r = await fetch(`${BASE}/api/lookup/scan_folders`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [folder] }),
        })
        const d = await r.json() as { content: string; files: string[] }
        addSource({ kind: 'folder', name, content: d.content ?? '', active: true })
        if (!d.content?.trim()) showToast(`No checksum files found in ${name}`, 'info')
      } catch {
        addSource({ kind: 'folder', name, content: '', active: true })
        showToast('Folder scan failed', 'bad')
      }
    }
  }, [addSource, showToast])

  const handleLookupAll = useCallback(async () => {
    if (!sources.length) { showToast('Add sources first', 'info'); return }
    const combined = sources.filter(s => s.content).map(s => s.content).join('\n')
    if (!combined.trim()) {
      showToast('No text content in sources — try picking files or pasting text', 'info')
      return
    }
    await runLookup(combined, 'all sources')
  }, [sources, runLookup, showToast])

  const handleGenerate = useCallback(async () => {
    const folders = sources.filter(s => s.kind === 'folder').map(s => s.name)
    if (!folders.length) { showToast('Add folder sources first', 'info'); return }
    showToast('Use the Verify screen to generate checksums for folders', 'info')
  }, [sources, showToast])

  const handleCopySummary = useCallback(() => {
    if (!summary?.lb_summary.length) return
    const lines = summary.lb_summary.map(r =>
      [r.lb_number, r.given, r.matched, r.not_found, r.missing_from_set, r.duplicates, r.xrefs, r.status].join('\t')
    )
    navigator.clipboard.writeText(lines.join('\n'))
      .then(() => showToast('Summary copied', 'ok'))
      .catch(() => showToast('Copy failed', 'bad'))
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
      showToast(`Added LB-${lbNumber} to wishlist`, 'ok')
    } catch {
      showToast('Wishlist add failed', 'bad')
    }
  }, [showToast])

  const summaryRows = summary?.lb_summary ?? []
  const detailRows  = detail ?? []

  const filteredSummary = summaryRows.filter(r => {
    if (filter === 'all') return true
    return apiStatusToState(r.status) === filter
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

  const totalSums = summary?.given ?? 0

  const statusBars: Array<{ k: LookupState; l: string }> = [
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
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Lookup</h1>
            <Pill tone="mute" soft>checksums → master DB</Pill>
          </div>
          <div style={{ fontSize: 12, color: 'var(--lbb-fg3)', marginTop: 2 }}>
            Identifies LB numbers for any set of checksums. Per-LB summary + per-checksum detail.
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {summary && (
          <span style={{ fontSize: 12, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
            {totalSums.toLocaleString()} checksums · {summaryRows.length} LBs
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
            <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 8 }}>
              Sources
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 8 }}>
              <Button variant="secondary" size="sm" icon="copy"        block disabled={busy} onClick={handleClipboard}>Clipboard</Button>
              <Button variant="secondary" size="sm" icon="search"      block disabled={busy} onClick={() => setShowListbox(true)}>Listbox…</Button>
              <Button variant="secondary" size="sm" icon="attachments" block disabled={busy} onClick={handleFiles}>Files…</Button>
              <Button variant="secondary" size="sm" icon="folderPlus"  block disabled={busy} onClick={handleFolders}>Folders…</Button>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
              <input type="checkbox" checked={filterMy} onChange={() => setFilterMy(!filterMy)} />
              Hide <span style={{ fontFamily: 'var(--lbb-mono)' }}>_mychecksums</span> files
            </label>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {sources.length === 0 ? (
              <div style={{ padding: '16px 10px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 11 }}>
                No sources yet
              </div>
            ) : sources.map((s, i) => (
              <SourceRow key={i} src={s} active={i === activeSource} onClick={() => setActiveSource(i)} />
            ))}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary"   size="sm" icon="lookup" block disabled={busy || !sources.length} onClick={handleLookupAll}>
              {busy ? 'Looking up…' : 'Lookup all sources'}
            </Button>
            <Button variant="secondary" size="sm" icon="plus"   block disabled={busy} onClick={handleGenerate}>Generate missing</Button>
            <Button variant="ghost"     size="sm" icon="trash"  block disabled={busy} onClick={clearSources}>Clear sources</Button>
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
                const t      = STATE_TONE[c.k]
                const n      = counts[c.k] || 0
                const active = filter === c.k
                return (
                  <button key={c.k} onClick={() => setFilter(active ? 'all' : c.k)} style={{
                    flex: 1, padding: '8px 12px', borderRadius: 6,
                    background: active ? `var(--lbb-${t.tone}-bg)` : 'var(--lbb-surface)',
                    border: `1px solid ${active ? t.color : 'var(--lbb-border)'}`,
                    cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                    display: 'flex', flexDirection: 'column', gap: 2,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.color }} />
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: t.color, letterSpacing: 0.06, textTransform: 'uppercase' }}>
                        {c.l}
                      </span>
                    </div>
                    <span style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg)', lineHeight: 1.1 }}>
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
              color: 'var(--lbb-fg3)', fontSize: 12,
            }}>
              {busy ? 'Running lookup…' : 'Add sources, then click Lookup all sources'}
            </div>
          )}

          {/* Scrollable body */}
          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>

            {summary && (
              <>
                {/* Summary table */}
                <div style={{ padding: '16px 24px 6px', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                    Match summary
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--lbb-fg3)' }}>per LB number · double-click to open on LB.com</span>
                  <div style={{ flex: 1 }} />
                  <Button variant="ghost" size="sm" icon="copy" onClick={handleCopySummary}>Copy summary</Button>
                  <Button variant="ghost" size="sm" icon="download" onClick={handleExportCsv}>Export CSV…</Button>
                </div>
                <div style={{ padding: '0 24px' }}>
                  <TableShell>
                    <colgroup>
                      <col style={{ width: 3 }} />
                      <col style={{ width: 110 }} />
                      <col style={{ width: 70 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} />
                      <col style={{ width: 80 }} /><col style={{ width: 70 }} /><col style={{ width: 70 }} />
                      <col /><col style={{ width: 130 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <TH> </TH>
                        <TH>LB#</TH>
                        <TH align="right">Given</TH><TH align="right">Matched</TH><TH align="right">Not found</TH>
                        <TH align="right">Missing</TH><TH align="right">Dups</TH><TH align="right">Xrefs</TH>
                        <TH>Status</TH><TH align="right"> </TH>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSummary.map((r, i) => {
                        const state = apiStatusToState(r.status)
                        const t = STATE_TONE[state]
                        const lbStr = `LB-${String(r.lb_number).padStart(5, '0')}`
                        return (
                          <TR key={i} edge={t.tone === 'mute' ? undefined : t.tone}>
                            <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{lbStr}</TD>
                            <TD align="right" mono>{r.given}</TD>
                            <TD align="right" mono style={{ color: r.matched      > 0 ? 'var(--lbb-ok-fg)'   : 'var(--lbb-fg3)' }}>{r.matched      || '—'}</TD>
                            <TD align="right" mono style={{ color: r.not_found    > 0 ? 'var(--lbb-bad-fg)'  : 'var(--lbb-fg3)' }}>{r.not_found    || '—'}</TD>
                            <TD align="right" mono style={{ color: r.missing_from_set > 0 ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)' }}>{r.missing_from_set || '—'}</TD>
                            <TD align="right" mono style={{ color: r.duplicates   > 0 ? '#a08200'            : 'var(--lbb-fg3)' }}>{r.duplicates   || '—'}</TD>
                            <TD align="right" mono style={{ color: r.xrefs        > 0 ? 'var(--lbb-info-fg)' : 'var(--lbb-fg3)' }}>{r.xrefs        || '—'}</TD>
                            <TD><Pill tone={t.tone} soft dot={state !== 'matched'}>{t.label}</Pill></TD>
                            <TD align="right" style={{ display: 'flex', gap: 4 }}>
                              <Button size="sm" variant="ghost" icon="reveal"
                                onClick={() => window.open(`http://www.losslessbob.wonderingwhattochoose.com/detail/LB-${String(r.lb_number).padStart(5, '0')}.html`)}>
                                Open
                              </Button>
                              <Button size="sm" variant="ghost"
                                onClick={() => handleAddToWishlist(r.lb_number)}>
                                +WL
                              </Button>
                            </TD>
                          </TR>
                        )
                      })}
                    </tbody>
                  </TableShell>
                </div>

                {/* Checksum detail */}
                <div style={{ padding: '20px 24px 6px', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
                    Checksum detail
                  </span>
                  <span style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
                    {filteredDetail.length} rows
                  </span>
                  <div style={{ flex: 1 }} />
                </div>
                <div style={{ padding: '0 24px 24px' }}>
                  <TableShell>
                    <colgroup>
                      <col style={{ width: 3 }} />
                      <col style={{ width: 170 }} /><col />
                      <col style={{ width: 50 }} /><col style={{ width: 100 }} />
                      <col style={{ width: 60 }} /><col style={{ width: 110 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <TH> </TH>
                        <TH>Checksum</TH><TH>Filename</TH>
                        <TH align="center">Type</TH><TH>LB#</TH>
                        <TH align="center">Xref</TH><TH>Status</TH>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDetail.map((r, i) => {
                        const state = apiStatusToState(r.status)
                        const t = STATE_TONE[state]
                        const lbStr = r.lb_number !== null ? `LB-${String(r.lb_number).padStart(5, '0')}` : '—'
                        return (
                          <TR key={i} edge={t.tone === 'mute' ? undefined : t.tone}>
                            <TD mono dim>{r.checksum.slice(0, 12)}…</TD>
                            <TD mono style={{ color: 'var(--lbb-fg)' }}>{r.filename}</TD>
                            <TD align="center" mono style={{ color: 'var(--lbb-fg3)' }}>{r.type}</TD>
                            <TD mono style={{ color: r.lb_number !== null ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: r.lb_number !== null ? 600 : 400 }}>
                              {lbStr}
                            </TD>
                            <TD align="center">
                              {r.xref > 0
                                ? <Icon name="check" size={11} style={{ color: 'var(--lbb-info-fg)' }} />
                                : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </TD>
                            <TD><Pill tone={t.tone} soft>{t.label}</Pill></TD>
                          </TR>
                        )
                      })}
                    </tbody>
                  </TableShell>

                  {filteredDetail.length === 0 && (
                    <div style={{
                      marginTop: 14, padding: '10px 14px', borderRadius: 6,
                      background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
                      fontSize: 11.5, color: 'var(--lbb-fg2)',
                      display: 'flex', alignItems: 'flex-start', gap: 10,
                    }}>
                      <Icon name="info" size={14} style={{ color: 'var(--lbb-info-fg)', marginTop: 1 }} />
                      <span>
                        <strong style={{ color: 'var(--lbb-info-fg)' }}>Not found?</strong>{' '}
                        Either this is a new entry the master DB doesn't know about yet, or the checksums don't match what's on file.
                      </span>
                    </div>
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
            <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>
              Results auto-populate the <strong style={{ color: 'var(--lbb-fg2)' }}>Rename</strong> tab
            </span>
            <div style={{ flex: 1 }} />
            <Button variant="ghost"     size="sm" disabled={busy || !sources.length} onClick={handleLookupAll}>Re-lookup all</Button>
            <Button variant="secondary" size="sm" icon="rename" onClick={() => navigate('/rename')}>Go to Rename →</Button>
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
            fontSize: 13, fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
            pointerEvents: 'none',
          }}
          ref={(el: HTMLDivElement | null) => { if (el) setTimeout(() => setToast(null), 3500) }}
        >{toast.msg}</div>
      )}
    </div>
  )
}
