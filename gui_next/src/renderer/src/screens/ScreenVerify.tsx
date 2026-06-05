import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Chip, Input, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useVerifyStore, VerifyFolder, FolderState, CheckStatus } from '../lib/verifyStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type ToastTone = 'ok' | 'bad' | 'info' | 'warn'

interface ToolStatus {
  sox_available:     boolean
  ffmpeg_available:  boolean
  shntool_available: boolean
  flac_available:    boolean
}


// ── Atoms ──────────────────────────────────────────────────────────────────────

function StatusDot({ s }: { s: CheckStatus }): React.JSX.Element {
  if (s === 'pass') return <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-bar)' }} />
  if (s === 'fail') return <Icon name="x"     size={13} style={{ color: 'var(--lbb-bad-fg)' }} />
  if (s === 'miss') return <Icon name="x"     size={13} style={{ color: 'var(--lbb-warn-fg)' }} />
  return <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>na</span>
}

function ToolDot({ ok, label }: { ok: boolean; label: string }): React.JSX.Element {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: ok ? 'var(--lbb-ok-bar)' : 'var(--lbb-bad-fg)' }} />
      {label}
    </span>
  )
}

function FolderRow({ row, active, onClick, onContextMenu }: { row: VerifyFolder; active: boolean; onClick: () => void; onContextMenu?: (e: React.MouseEvent) => void }): React.JSX.Element {
  const tone = row.status === 'pass' ? 'ok' : row.status === 'mismatch' || row.status === 'fail' ? 'bad' : 'warn'
  const dotColor = tone === 'ok' ? 'var(--lbb-ok-bar)' : tone === 'bad' ? 'var(--lbb-bad-bar)' : 'var(--lbb-warn-bar)'
  const name = row.folder.split('/').pop() ?? row.folder
  return (
    <button onClick={onClick} onContextMenu={onContextMenu} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 10px', marginBottom: 1, borderRadius: 6,
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      border: '1px solid ' + (active ? 'var(--lbb-accent-line)' : 'transparent'),
      textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: dotColor, flex: '0 0 8px' }} />
      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
        <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
          {row.mode.toUpperCase()} · {row.pass}/{row.total} pass
          {row.missing > 0 && <> · <span style={{ color: 'var(--lbb-warn-fg)' }}>{row.missing} miss</span></>}
          {row.mismatch > 0 && <> · <span style={{ color: 'var(--lbb-bad-fg)' }}>{row.mismatch} mismatch</span></>}
        </span>
      </span>
    </button>
  )
}

function StateBadge({ s }: { s: FolderState }): React.JSX.Element {
  const { t } = useTranslation()
  if (s === 'pass')         return <Pill tone="ok"   soft>{t('verify.states.pass')}</Pill>
  if (s === 'mismatch')     return <Pill tone="bad"  soft dot>{t('verify.states.mismatch')}</Pill>
  if (s === 'fail')         return <Pill tone="bad"  soft dot>{t('verify.states.fail')}</Pill>
  if (s === 'incomplete')   return <Pill tone="warn" soft>{t('verify.states.incomplete')}</Pill>
  if (s === 'shntool')      return <Pill tone="warn" soft dot>{t('verify.states.shntool')}</Pill>
  if (s === 'no_checksums') return <Pill tone="warn" soft>{t('verify.states.noChecksums')}</Pill>
  return <Pill tone="mute" soft>—</Pill>
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenVerify(): React.JSX.Element {
  const { t } = useTranslation()
  const { results, activeIdx, showAll, filter, setResults, setActiveIdx, setShowAll, setFilter } = useVerifyStore()
  const { folders, addFolders, removeFolders, clearFolders } = useFolderQueueStore()
  const [busy,        setBusy]       = useState(false)
  const [tools,       setTools]      = useState<ToolStatus | null>(null)
  const [toast,       setToast]      = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [shallowScan, setShallowScan] = useState(false)
  const [ctxMenu,     setCtxMenu]    = useState<{ x: number; y: number; folder: string } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  // Load tool status on mount
  useEffect(() => {
    fetch(`${BASE}/api/spectrogram/check`)
      .then(r => r.json())
      .then((d: ToolStatus) => setTools(d))
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
    if (picked.length) addFolders(picked)
  }, [addFolders])

  const handleAddSingleFolder = useCallback(async () => {
    const path = await window.api.pickDir()
    if (path) addFolders([path])
  }, [addFolders])

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
      const data = await post('/api/pipeline/scan-tree', { root, shallow: shallowScan }) as { folders: string[] }
      if (data.folders?.length) {
        addFolders(data.folders)
        showToast(t('verify.toast.foundFolders', { count: data.folders.length }), 'ok')
      } else {
        showToast(t('verify.toast.noAudioFolders'), 'info')
      }
    } catch {
      showToast(t('verify.toast.scanFailed'), 'bad')
    }
  }, [post, showToast, addFolders, t, shallowScan])

  const handleVerify = useCallback(async () => {
    if (!folders.length) { showToast(t('verify.toast.addFoldersFirst'), 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/verify', { folders }) as { results: VerifyFolder[] }
      setResults(data.results ?? [])
      setActiveIdx(0)
    } catch {
      showToast(t('verify.toast.verifyFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, post, showToast, t])

  const handleGenerate = useCallback(async () => {
    if (!folders.length) { showToast(t('verify.toast.addFoldersFirst'), 'info'); return }
    setBusy(true)
    try {
      await post('/api/verify/generate', { folders })
      showToast(t('verify.toast.checksumsGenerated'), 'info')
      const data = await post('/api/verify', { folders }) as { results: VerifyFolder[] }
      setResults(data.results ?? [])
      setActiveIdx(0)
    } catch {
      showToast(t('verify.toast.generateFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, post, showToast, t])

  const handleRetrieve = useCallback(async () => {
    if (!folders.length) { showToast(t('verify.toast.addFoldersFirst'), 'info'); return }
    setBusy(true)
    try {
      const data = await post('/api/lbdir/retrieve', { folders }) as { results: { status: string }[] }
      const copied = data.results?.filter(r => r.status === 'copied' || r.status === 'scraped_and_copied').length ?? 0
      showToast(copied > 0 ? t('verify.toast.retrieved', { count: copied }) : t('verify.toast.nothingRetrieved'), copied > 0 ? 'ok' : 'info')
      if (copied > 0) {
        const vdata = await post('/api/verify', { folders }) as { results: VerifyFolder[] }
        setResults(vdata.results ?? [])
        setActiveIdx(0)
      }
    } catch {
      showToast(t('verify.toast.retrieveFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }, [folders, post, showToast, t])

  const handleCopyReport = useCallback(() => {
    if (!results[activeIdx]) return
    const row = results[activeIdx]
    const lines = row.files.map(f =>
      `${f.overall === 'pass' ? '✓' : '✗'} ${f.filename}\t[md5] ${f.md5_status}\t[ffp] ${f.ffp_status}`
    )
    navigator.clipboard.writeText(lines.join('\n'))
      .then(() => showToast(t('verify.toast.reportCopied'), 'ok'))
      .catch(() => showToast(t('verify.toast.copyFailed'), 'bad'))
  }, [results, activeIdx, showToast])

  const row = results[activeIdx] ?? null
  const filteredFolders = filter
    ? folders.filter(f => f.toLowerCase().includes(filter.toLowerCase()))
    : folders

  const visible = row
    ? (showAll ? row.files : row.files.filter(f => f.overall !== 'pass'))
    : []

  const STAT_LABEL: React.CSSProperties = {
    fontSize: 'var(--lbb-fs-9-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
    letterSpacing: 0.08, textTransform: 'uppercase',
  }

  const stats = row ? [
    { l: t('verify.stats.total'),    v: row.total,    color: 'var(--lbb-fg)' },
    { l: t('verify.stats.pass'),     v: row.pass,     color: row.pass === row.total ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg)' },
    { l: t('verify.stats.mismatch'), v: row.mismatch, color: row.mismatch > 0 ? 'var(--lbb-bad-fg)'  : 'var(--lbb-fg3)' },
    { l: t('verify.stats.missing'),  v: row.missing,  color: row.missing  > 0 ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)' },
    { l: t('verify.stats.extra'),    v: row.extra,    color: row.extra    > 0 ? 'var(--lbb-info-fg)' : 'var(--lbb-fg3)' },
    {
      l: t('verify.stats.ffp'),
      v: row.missing_types?.includes('ffp') ? '—' : '✓',
      color: row.missing_types?.includes('ffp') ? 'var(--lbb-warn-fg)' : 'var(--lbb-ok-fg)',
    },
    {
      l: t('verify.stats.md5'),
      v: row.missing_types?.includes('md5') ? '—' : '✓',
      color: row.missing_types?.includes('md5') ? 'var(--lbb-warn-fg)' : 'var(--lbb-ok-fg)',
    },
  ] : []

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
          <Icon name="verify" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>{t('verify.title')}</h1>
            <Pill tone="mute" soft>{t('verify.subtitle')}</Pill>
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('verify.desc')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 14, padding: '0 12px', borderRight: '1px solid var(--lbb-border)' }}>
          <ToolDot ok={!!tools?.flac_available}    label="FFP" />
          <ToolDot ok                              label="MD5" />
          <ToolDot ok={!!tools?.shntool_available} label="shntool" />
        </div>
        <Button variant="ghost" size="sm" icon="folderPlus" onClick={handleAddFolders}>{t('verify.addFolders')}</Button>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Queue rail */}
        <aside style={{
          width: 300, flex: '0 0 300px',
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
              <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.1, textTransform: 'uppercase' }}>{t('verify.rail.foldersLabel')}</span>
              <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600, color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums' }}>{folders.length}</span>
            </div>
            <Input
              icon="search" placeholder={t('verify.rail.filterPlaceholder')} size="sm" style={{ width: '100%' }}
              value={filter} onChange={e => setFilter(e.target.value)}
            />
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {filteredFolders.length === 0 ? (
              <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
                {folders.length === 0 ? t('verify.rail.noFolders') : t('verify.rail.noMatches')}
              </div>
            ) : filteredFolders.map((f, i) => {
              const res = results.find(r => r.folder === f)
              if (res) {
                return <FolderRow key={f} row={res} active={results.indexOf(res) === activeIdx} onClick={() => { setActiveIdx(results.indexOf(res)); setShowAll(false) }} onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, folder: f }) }} />
              }
              const name = f.split('/').pop() ?? f
              return (
                <button key={f} onClick={() => {}} onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, folder: f }) }} style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '7px 10px', marginBottom: 1, borderRadius: 6,
                  background: 'transparent', color: 'var(--lbb-fg2)',
                  border: '1px solid transparent',
                  textAlign: 'left', fontFamily: 'inherit', cursor: 'default',
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--lbb-border)', flex: '0 0 8px' }} />
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
                </button>
              )
            })}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary"   size="sm" icon="verify"     block disabled={busy || !folders.length} onClick={handleVerify}>
              {busy ? t('verify.rail.running') : t('verify.rail.verifyAll')}
            </Button>
            <Button variant="secondary" size="sm" icon="plus"       block disabled={busy || !folders.length} onClick={handleGenerate}>{t('verify.rail.generate')}</Button>
            <Button variant="ghost"     size="sm" icon="download"   block disabled={busy || !folders.length} onClick={handleRetrieve}>{t('verify.rail.retrieve')}</Button>
            <Button variant="ghost"     size="sm" icon="folder"    block onClick={handleAddSingleFolder}>{t('common.addFolder')}</Button>
            <Button variant="ghost"     size="sm" icon="folderPlus" block onClick={handleAddRoot}>{t('verify.rail.addRoot')}</Button>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', cursor: 'pointer', paddingLeft: 2 }}>
              <input type="checkbox" checked={shallowScan} onChange={e => setShallowScan(e.target.checked)} style={{ accentColor: 'var(--lbb-accent)' }} />
              {t('common.shallowScan')}
            </label>
            <Button variant="ghost"     size="sm" icon="trash"     block disabled={!folders.length} onClick={() => clearFolders()}>{t('common.clearList')}</Button>
          </div>
        </aside>

        {/* Main pane */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>

          {!row ? (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="verify" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>
                {folders.length === 0 ? t('verify.emptyFolders') : t('verify.clickToRun')}
              </span>
            </div>
          ) : (
            <>
              {/* Folder summary */}
              <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--lbb-border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                  <Icon name="folder" size={14} style={{ color: 'var(--lbb-fg3)' }} />
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg)' }}>
                    {row.folder.split('/').pop()}
                  </span>
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{row.folder}</span>
                  <div style={{ flex: 1 }} />
                  <StateBadge s={row.status} />
                  <Pill tone="mute" soft>{row.mode.toUpperCase()}</Pill>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8 }}>
                  {stats.map((s, idx) => (
                    <div key={idx} style={{
                      padding: '8px 12px', borderRadius: 6,
                      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                    }}>
                      <div style={STAT_LABEL}>{s.l}</div>
                      <div style={{ fontSize: 'var(--lbb-fs-18)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', fontVariantNumeric: 'tabular-nums', color: s.color, marginTop: 2 }}>
                        {s.v}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Toolbar */}
              <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--lbb-border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>{t('verify.toolbar.files')}</span>
                <Chip active={!showAll} onClick={() => setShowAll(false)} size="sm" count={row.files.filter(f => f.overall !== 'pass').length}>{t('verify.toolbar.problems')}</Chip>
                <Chip active={showAll}  onClick={() => setShowAll(true)}  size="sm" count={row.files.length}>{t('verify.toolbar.showAll')}</Chip>
                <div style={{ flex: 1 }} />
                <Button variant="ghost"     size="sm" icon="reveal"   onClick={() => window.api.openPath(row.folder)}>{t('verify.toolbar.openFinder')}</Button>
                <Button variant="ghost"     size="sm" icon="copy"     onClick={handleCopyReport}>{t('verify.toolbar.copyReport')}</Button>
                <Button variant="secondary" size="sm" icon="plus"     disabled={busy} onClick={handleGenerate}>{t('verify.toolbar.generateMissing')}</Button>
              </div>

              {/* Detail area */}
              <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                {row.status === 'shntool' ? (
                  <div style={{ padding: '32px 24px' }}>
                    <div style={{
                      padding: '16px 18px', borderRadius: 8,
                      background: 'var(--lbb-warn-bg)', border: '1px solid var(--lbb-warn-bar)',
                      display: 'flex', gap: 12, alignItems: 'flex-start',
                    }}>
                      <Icon name="info" size={18} style={{ color: 'var(--lbb-warn-fg)', flex: '0 0 18px', marginTop: 2 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-warn-fg)' }}>{t('verify.shntoolWarning')}</div>
                        <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginTop: 4 }}>
                          {t('verify.shntoolDesc')}
                        </div>
                        <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                          <Button variant="ghost" size="sm" disabled={busy} onClick={handleVerify}>{t('verify.verifyWithoutShntool')}</Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '0 24px 24px' }}>
                    <TableShell>
                      <colgroup>
                        <col style={{ width: 3 }} />
                        <col />
                        <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
                        <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
                        <col style={{ width: 60 }} /><col style={{ width: 60 }} /><col style={{ width: 90 }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <TH> </TH><TH>{t('verify.table.filename')}</TH>
                          <TH align="right">{t('verify.table.md5Expected')}</TH><TH align="right">{t('verify.table.md5Actual')}</TH><TH align="center">{t('verify.table.md5')}</TH>
                          <TH align="right">{t('verify.table.ffpExpected')}</TH><TH align="right">{t('verify.table.ffpActual')}</TH><TH align="center">{t('verify.table.ffp')}</TH>
                          <TH align="center">{t('verify.table.st5')}</TH><TH align="center">{t('verify.table.disk')}</TH><TH>{t('verify.table.overall')}</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((f, i) => {
                          const edge: 'ok' | 'warn' | 'bad' = f.overall === 'pass' ? 'ok' : f.overall === 'missing' ? 'warn' : 'bad'
                          const md5e = f.md5_expected ? f.md5_expected.slice(0, 12) + '…' : '—'
                          const md5a = f.md5_actual   ? f.md5_actual.slice(0, 12)   + '…' : '—'
                          const ffpe = f.ffp_expected ? f.ffp_expected.slice(0, 12) + '…' : '—'
                          const ffpa = f.ffp_actual   ? f.ffp_actual.slice(0, 12)   + '…' : '—'
                          return (
                            <TR key={i} edge={edge}>
                              <TD mono style={{ color: f.overall === 'pass' ? 'var(--lbb-fg)' : f.overall === 'missing' ? 'var(--lbb-warn-fg)' : 'var(--lbb-bad-fg)' }}>
                                {f.filename}
                              </TD>
                              <TD align="right" mono dim>{md5e}</TD>
                              <TD align="right" mono style={{ color: f.md5_status === 'fail' ? 'var(--lbb-bad-fg)' : f.md5_status === 'miss' ? 'var(--lbb-fg3)' : 'var(--lbb-fg2)' }}>
                                {md5a}
                              </TD>
                              <TD align="center"><StatusDot s={f.md5_status} /></TD>
                              <TD align="right" mono dim>{ffpe}</TD>
                              <TD align="right" mono style={{ color: f.ffp_status === 'fail' ? 'var(--lbb-bad-fg)' : f.ffp_status === 'miss' ? 'var(--lbb-fg3)' : 'var(--lbb-fg2)' }}>
                                {ffpa}
                              </TD>
                              <TD align="center"><StatusDot s={f.ffp_status} /></TD>
                              <TD align="center"><StatusDot s={f.shntool_status} /></TD>
                              <TD align="center">
                                {f.on_disk
                                  ? <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
                                  : <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />}
                              </TD>
                              <TD>
                                <Pill tone={edge} soft>
                                  {f.overall === 'pass' ? t('verify.fileStates.pass') : f.overall === 'missing' ? t('verify.fileStates.missing') : f.overall === 'extra' ? t('verify.fileStates.extra') : t('verify.fileStates.fail')}
                                </Pill>
                              </TD>
                            </TR>
                          )
                        })}
                      </tbody>
                    </TableShell>

                    {!showAll && (
                      <div style={{ marginTop: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontStyle: 'italic', textAlign: 'center' }}>
                        {t('verify.showingProblems', { count: visible.length })}{' '}
                        <button
                          onClick={() => setShowAll(true)}
                          style={{
                            background: 'none', border: 'none', color: 'var(--lbb-accent-mid)',
                            cursor: 'pointer', textDecoration: 'underline', fontStyle: 'italic',
                            padding: 0, font: 'inherit',
                          }}
                        >
                          {t('verify.showAllCount', { count: row.files.length })}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
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
          >{t('common.removeFromList')}</button>
        </div>
      )}
    </div>
  )
}
