import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useLookupStore, LookupDetail } from '../lib/lookupStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type RowState  = 'has_lb' | 'needs_rename' | 'wrong_lb' | 'multiple_ids' | 'no_match' | 'renamed'
type ToastTone = 'ok' | 'bad' | 'info'

interface RenameRow {
  folder:     string
  cur:        string
  prop:       string
  lbNumber:   number | null
  lbStr:      string
  state:      RowState
  hint:       string
  sel:        boolean
  candidates: number[]
}

interface DisambigState {
  loading:   boolean
  pinnedLb:  number | null
  canonical: number[]
}

// ── Static maps ────────────────────────────────────────────────────────────────

const STATES: Record<RowState, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; color: string; label: string }> = {
  has_lb:       { tone: 'ok',   color: 'var(--lbb-ok-bar)',   label: 'LB# already in name' },
  renamed:      { tone: 'ok',   color: 'var(--lbb-ok-bar)',   label: 'Renamed' },
  needs_rename: { tone: 'warn', color: 'var(--lbb-warn-bar)', label: 'Will rename' },
  wrong_lb:     { tone: 'bad',  color: '#7a3fb1',             label: 'Wrong LB · strip + rename' },
  multiple_ids: { tone: 'info', color: '#2b8b9a',             label: 'Multiple LBs · review' },
  no_match:     { tone: 'bad',  color: 'var(--lbb-bad-bar)',  label: 'No match' },
}

function lbStr(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

function applyNftSuffix(name: string, lbStatus: string | undefined): string {
  if (lbStatus !== 'private') return name
  if (name.toUpperCase().endsWith('-NFT')) return name.slice(0, -4) + '-NFT'
  return name + '-NFT'
}

function buildProposals(detail: LookupDetail[], folderList: string[]): RenameRow[] {
  const byFolder = new Map<string, Set<number>>()
  for (const row of detail) {
    if (!row.source_file) continue
    const parts = row.source_file.split('/')
    parts.pop()
    const folder = parts.join('/')
    if (!folder) continue
    if (row.lb_number !== null && (row.status === 'MATCHED' || row.status === 'MATCHED (INCOMPLETE)')) {
      if (!byFolder.has(folder)) byFolder.set(folder, new Set())
      byFolder.get(folder)!.add(row.lb_number)
    } else if (!byFolder.has(folder)) {
      byFolder.set(folder, new Set())
    }
  }

  const rows: RenameRow[] = []
  const folders = folderList.length > 0 ? folderList : Array.from(byFolder.keys())
  for (const folder of folders) {
    const cur = folder.split('/').pop() ?? folder
    const lbs = byFolder.get(folder) ?? new Set<number>()
    const lbArray = Array.from(lbs)

    if (lbArray.length === 0) {
      rows.push({
        folder, cur, prop: '(no change)',
        lbNumber: null, lbStr: '—',
        state: 'no_match', hint: 'No checksums matched',
        sel: false, candidates: [],
      })
      continue
    }

    const alreadyHasLb = /LB-\d{4,5}/i.test(cur)
    if (alreadyHasLb) {
      rows.push({
        folder, cur, prop: '(no change)',
        lbNumber: lbArray[0], lbStr: lbStr(lbArray[0]),
        state: 'has_lb', hint: 'LB# already in folder name',
        sel: false, candidates: lbArray,
      })
      continue
    }

    if (lbArray.length === 1) {
      const lb = lbArray[0]
      const lbStatus = detail.find(d => d.lb_number === lb)?.lb_status
      const proposed = applyNftSuffix(`${cur} (${lbStr(lb)})`, lbStatus)
      rows.push({
        folder, cur, prop: proposed,
        lbNumber: lb, lbStr: lbStr(lb),
        state: 'needs_rename', hint: 'Single complete match in master DB',
        sel: true, candidates: [lb],
      })
    } else {
      rows.push({
        folder, cur, prop: '(select LB# to populate)',
        lbNumber: lbArray[0], lbStr: `${lbStr(lbArray[0])}?`,
        state: 'multiple_ids', hint: `${lbArray.length} candidate LBs · resolve below`,
        sel: false, candidates: lbArray,
      })
    }
  }
  return rows
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function StateChip({ state, count, active, onClick }: {
  state: RowState; count: number; active: boolean; onClick: () => void
}): React.JSX.Element {
  const { t } = useTranslation()
  const s = STATES[state]
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 999,
      border: `1px solid ${active ? s.color : 'var(--lbb-border2)'}`,
      background: active ? `var(--lbb-${s.tone}-bg)` : 'var(--lbb-surface)',
      color: active ? `var(--lbb-${s.tone}-fg)` : 'var(--lbb-fg2)',
      fontFamily: 'inherit', fontSize: 11.5, fontWeight: active ? 600 : 500, cursor: 'pointer',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.color }} />
      {t(`rename.states.${state}` as const)}
      <span style={{ fontSize: 10, opacity: 0.65, marginLeft: 2 }}>{count}</span>
    </button>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenRename(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { summary, detail, folderList } = useLookupStore()

  const [rows,         setRows]         = useState<RenameRow[]>([])
  const [filter,       setFilter]       = useState<RowState | null>(null)
  const [expandedRow,  setExpandedRow]  = useState<number | null>(null)
  const [busy,         setBusy]         = useState(false)
  const [toast,        setToast]        = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [disambig,     setDisambig]     = useState<DisambigState | null>(null)
  const [disambigLbSel, setDisambigLbSel] = useState<number | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  // Rebuild proposals whenever lookup store changes
  useEffect(() => {
    if (detail.length > 0 || folderList.length > 0) {
      setRows(buildProposals(detail, folderList))
    }
  }, [detail, folderList])

  const handleToggleRow = useCallback((i: number) => {
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, sel: !r.sel } : r))
  }, [])

  const handleSelectAll = useCallback(() => {
    setRows(prev => prev.map(r => ({ ...r, sel: r.state !== 'no_match' && r.state !== 'has_lb' })))
  }, [])

  const handleClear = useCallback(() => {
    setRows(prev => prev.map(r => ({ ...r, sel: false })))
  }, [])

  const handleApply = useCallback(async () => {
    const selected = rows.filter(r => r.sel && r.state === 'needs_rename' && r.prop !== '(no change)' && r.prop !== '(select LB# to populate)')
    if (!selected.length) { showToast(t('rename.toast.noValidRenames'), 'info'); return }
    setBusy(true)
    try {
      const renames = selected.map(r => ({
        old_path: r.folder,
        new_path: r.folder.replace(/[^/]+$/, r.prop),
        lb_number: r.lbNumber,
      }))
      const resp = await fetch(`${BASE}/api/rename/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ renames }),
      })
      const data = await resp.json() as { applied: number; errors: string[] }
      showToast(t('rename.toast.applied', { count: data.applied, errors: data.errors.length > 0 ? ` · ${data.errors.length} errors` : '' }), data.errors.length > 0 ? 'info' : 'ok')
      setRows(prev => prev.map(r => {
        if (!r.sel) return r
        const found = renames.find(ren => ren.old_path === r.folder)
        if (found && data.errors.every(e => !e.includes(r.folder))) {
          return { ...r, state: 'renamed', sel: false }
        }
        return r
      }))
    } catch {
      showToast(t('rename.toast.applyFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }, [rows, showToast, t])

  const handleCopyDiff = useCallback(() => {
    const lines = rows
      .filter(r => r.state === 'needs_rename' || r.state === 'renamed')
      .map(r => `${r.cur} → ${r.prop}`)
    navigator.clipboard.writeText(lines.join('\n'))
      .then(() => showToast(t('rename.toast.diffCopied'), 'ok'))
      .catch(() => showToast(t('rename.toast.copyFailed'), 'bad'))
  }, [rows, showToast])

  const handleExport = useCallback(async () => {
    const lines = rows.map(r => `${r.cur}\t→\t${r.prop}\t${r.lbStr}\t${STATES[r.state].label}`)
    await window.api.saveFile(lines.join('\n'), 'rename_plan.txt')
  }, [rows])

  const handleExpand = useCallback((i: number, row: RenameRow) => {
    if (expandedRow === i) {
      setExpandedRow(null)
      setDisambig(null)
      setDisambigLbSel(null)
      return
    }
    setExpandedRow(i)
    setDisambig(null)
    setDisambigLbSel(null)
    if (row.state !== 'multiple_ids' || !row.candidates.length) return
    setDisambig({ loading: true, pinnedLb: null, canonical: row.candidates })
    Promise.all([
      fetch(`${BASE}/api/folder_link?path=${encodeURIComponent(row.folder)}`).then(r => r.json()),
      fetch(`${BASE}/api/lb_alias/resolve?lbs=${row.candidates.join(',')}`).then(r => r.json()),
    ]).then(([linkData, aliasData]: [any, any]) => {
      const pinnedLb: number | null = typeof linkData.lb_number === 'number' ? linkData.lb_number : null
      const canonical: number[] = Array.isArray(aliasData.canonical) && aliasData.canonical.length
        ? aliasData.canonical : row.candidates
      setDisambig({ loading: false, pinnedLb, canonical })
      if (pinnedLb) setDisambigLbSel(pinnedLb)
    }).catch(() => {
      setDisambig({ loading: false, pinnedLb: null, canonical: row.candidates })
    })
  }, [expandedRow])

  const handlePin = useCallback(async (row: RenameRow, lb: number) => {
    try {
      const resp = await fetch(`${BASE}/api/folder_link`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: row.folder, lb_number: lb }),
      })
      const data = await resp.json() as { ok?: boolean; error?: string }
      if (!data.ok) throw new Error(data.error)
      setDisambig(prev => prev ? { ...prev, pinnedLb: lb } : prev)
      const lbStatus = detail.find(d => d.lb_number === lb)?.lb_status
      const proposed = applyNftSuffix(`${row.cur} (${lbStr(lb)})`, lbStatus)
      setRows(prev => prev.map(r => r.folder === row.folder
        ? { ...r, lbNumber: lb, lbStr: lbStr(lb), prop: proposed, state: 'needs_rename', sel: true }
        : r
      ))
      setExpandedRow(null)
      setDisambig(null)
      showToast(`${t('rename.toast.pinned', { lb: lbStr(lb) })}`, 'ok')
    } catch {
      showToast(t('rename.toast.pinFailed'), 'bad')
    }
  }, [detail, showToast, t])

  const handleUnpin = useCallback(async (folder: string) => {
    try {
      const resp = await fetch(`${BASE}/api/folder_link?path=${encodeURIComponent(folder)}`, { method: 'DELETE' })
      const data = await resp.json() as { ok?: boolean }
      if (!data.ok) throw new Error()
      setDisambig(prev => prev ? { ...prev, pinnedLb: null } : prev)
      setDisambigLbSel(null)
      showToast(t('rename.toast.unpinned'), 'ok')
    } catch {
      showToast(t('rename.toast.unpinFailed'), 'bad')
    }
  }, [showToast, t])

  const handleStandardize = useCallback(async (folder: string, lb: number) => {
    try {
      const resp = await fetch(`${BASE}/api/folder_naming/standard/${lb}`)
      const data = await resp.json() as { standard_name?: string; error?: string }
      if (!data.standard_name) throw new Error(data.error)
      setRows(prev => prev.map(r => r.folder === folder
        ? { ...r, prop: data.standard_name!, state: 'needs_rename', sel: true }
        : r
      ))
      setExpandedRow(null)
      setDisambig(null)
      showToast(t('rename.toast.standardized'), 'ok')
    } catch {
      showToast(t('rename.toast.standardizeFailed'), 'bad')
    }
  }, [showToast, t])

  const counts  = rows.reduce<Partial<Record<RowState, number>>>((a, r) => { a[r.state] = (a[r.state] ?? 0) + 1; return a }, {})
  const selected = rows.filter(r => r.sel).length
  const visible  = filter ? rows.filter(r => r.state === filter) : rows

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
          <Icon name="rename" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>{t('rename.title')}</h1>
            <Pill tone="mute" soft>{t('rename.subtitle', { count: rows.length })}</Pill>
          </div>
          <div style={{ fontSize: 12, color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('rename.desc')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" icon="refresh" onClick={() => navigate('/lookup')}>{t('rename.goToLookup')}</Button>
      </div>

      {rows.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 14, color: 'var(--lbb-fg3)' }}>
          <Icon name="rename" size={40} style={{ opacity: 0.15 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--lbb-fg2)' }}>{t('rename.noResults')}</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>{t('rename.noResultsDesc')}</div>
          </div>
          <Button variant="primary" size="md" icon="lookup" onClick={() => navigate('/lookup')}>{t('rename.goToLookup')}</Button>
        </div>
      ) : (
        <>
          {/* State filter chips */}
          <div style={{
            padding: '10px 24px', borderBottom: '1px solid var(--lbb-border)',
            display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
          }}>
            <button onClick={() => setFilter(null)} style={{
              padding: '3px 10px', borderRadius: 999,
              border: `1px solid ${!filter ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
              background: !filter ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
              color: !filter ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
              fontFamily: 'inherit', fontSize: 11.5, fontWeight: !filter ? 600 : 500, cursor: 'pointer',
            }}>
              {t('rename.filterAll')} <span style={{ fontSize: 10, opacity: 0.65, marginLeft: 4 }}>{rows.length}</span>
            </button>
            {(Object.keys(STATES) as RowState[]).filter(k => k !== 'renamed' && counts[k]).map(k => (
              <StateChip key={k} state={k} count={counts[k] ?? 0}
                active={filter === k} onClick={() => setFilter(filter === k ? null : k)} />
            ))}
          </div>

          {/* Bulk action bar */}
          <div style={{
            padding: '10px 24px', borderBottom: '1px solid var(--lbb-border)',
            background: selected > 0 ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <span style={{ fontSize: 12, color: selected > 0 ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)', fontWeight: 600 }}>
              {t('rename.bulk.selectedOf', { selected, total: rows.length })}
            </span>
            <div style={{ flex: 1 }} />
            <Button variant="ghost"     size="sm" onClick={handleClear}>{t('common.clear')}</Button>
            <Button variant="secondary" size="sm" onClick={handleSelectAll}>{t('rename.bulk.selectAllConfident')}</Button>
            <Button variant="primary"   size="sm" icon="check" disabled={busy || selected === 0} onClick={handleApply}>
              {busy ? t('rename.bulk.applying') : t('rename.bulk.apply', { count: selected })}
            </Button>
          </div>

          {/* Table */}
          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            <div style={{ padding: '16px 24px' }}>
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 32 }} />
                  <col /><col style={{ width: 24 }} /><col />
                  <col style={{ width: 130 }} /><col style={{ width: 220 }} />
                  <col style={{ width: 36 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH> </TH>
                    <TH><input type="checkbox" onChange={e => e.target.checked ? handleSelectAll() : handleClear()} /></TH>
                    <TH>{t('rename.table.currentName')}</TH>
                    <TH> </TH>
                    <TH>{t('rename.table.proposedName')}</TH>
                    <TH>{t('rename.table.lb')}</TH>
                    <TH>{t('rename.table.state')}</TH>
                    <TH> </TH>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r, i) => {
                    const s       = STATES[r.state]
                    const expanded = expandedRow === i
                    const propColor =
                      r.state === 'no_match'  ? 'var(--lbb-fg3)'    :
                      r.state === 'has_lb'    ? 'var(--lbb-fg3)'    :
                      r.state === 'wrong_lb'  ? 'var(--lbb-bad-fg)' :
                      r.state === 'renamed'   ? 'var(--lbb-ok-fg)'  :
                      'var(--lbb-ok-fg)'
                    return (
                      <React.Fragment key={i}>
                        <TR edge={s.tone === 'mute' ? undefined : s.tone} selected={r.sel}>
                          <TD>
                            <input
                              type="checkbox"
                              checked={r.sel}
                              disabled={r.state === 'no_match' || r.state === 'has_lb' || r.state === 'renamed'}
                              onChange={() => handleToggleRow(i)}
                            />
                          </TD>
                          <TD mono style={{ color: 'var(--lbb-fg)' }}>{r.cur}</TD>
                          <TD align="center">
                            <Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} />
                          </TD>
                          <TD mono style={{ color: propColor, fontStyle: r.prop.startsWith('(') ? 'italic' : 'normal' }}>
                            {r.prop}
                          </TD>
                          <TD mono style={{ color: r.lbNumber !== null ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: 600 }}>
                            {r.lbStr}
                          </TD>
                          <TD>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <Pill tone={s.tone} soft dot={r.state !== 'has_lb' && r.state !== 'renamed'}>{t(`rename.states.${r.state}` as const)}</Pill>
                            </div>
                            <div style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', marginTop: 3 }}>
                              {r.state === 'multiple_ids'
                                ? t('rename.hints.multiple_ids', { count: (r.hint.match(/\d+/) ?? [''])[0] })
                                : r.state === 'has_lb'
                                  ? t('rename.hints.has_lb')
                                  : r.state === 'needs_rename'
                                    ? t('rename.hints.needs_rename')
                                    : r.hint}
                            </div>
                          </TD>
                          <TD>
                            {r.state === 'multiple_ids' && (
                              <button
                                title="Disambiguate"
                                onClick={() => handleExpand(i, r)}
                                style={{
                                  background: 'none', border: '1px solid var(--lbb-border2)',
                                  borderRadius: 4, padding: '2px 4px', cursor: 'pointer',
                                  display: 'inline-flex', alignItems: 'center',
                                }}
                              >
                                <Icon name={expanded ? 'chevDown' : 'chevRight'} size={12} />
                              </button>
                            )}
                          </TD>
                        </TR>

                        {expanded && r.state === 'multiple_ids' && (
                          <tr>
                            <td colSpan={8} style={{ padding: 0 }}>
                              <div style={{
                                padding: '14px 16px 16px 56px',
                                background: 'var(--lbb-info-bg)', borderBottom: '1px solid var(--lbb-border)',
                              }}>
                                <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-info-fg)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 8 }}>
                                  {t('rename.disambiguate.title')}
                                </div>

                                {(!disambig || disambig.loading) ? (
                                  <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', fontStyle: 'italic' }}>
                                    {t('rename.disambiguate.loading')}
                                  </div>
                                ) : (
                                  <>
                                    {disambig.pinnedLb && (
                                      <div style={{ fontSize: 11.5, color: 'var(--lbb-ok-fg)', marginBottom: 8 }}>
                                        {t('rename.disambiguate.pinned', { lb: lbStr(disambig.pinnedLb) })}
                                      </div>
                                    )}
                                    <div style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', marginBottom: 10 }}>
                                      {t('rename.disambiguate.desc')}
                                    </div>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                                      {disambig.canonical.map(lb => (
                                        <button key={lb} onClick={() => setDisambigLbSel(lb)} style={{
                                          padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontFamily: 'var(--lbb-mono)',
                                          fontSize: 12, fontWeight: disambigLbSel === lb ? 700 : 500,
                                          border: `1px solid ${disambigLbSel === lb ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
                                          background: disambigLbSel === lb ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                                          color: disambigLbSel === lb ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                                        }}>
                                          {lbStr(lb)}
                                        </button>
                                      ))}
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                      <Button size="sm" variant="primary" disabled={!disambigLbSel} onClick={() => disambigLbSel && handlePin(r, disambigLbSel)}>
                                        {t('rename.disambiguate.pin')}
                                      </Button>
                                      <Button size="sm" variant="secondary" disabled={!disambigLbSel} onClick={() => disambigLbSel && handleStandardize(r.folder, disambigLbSel)}>
                                        {t('rename.disambiguate.standardize')}
                                      </Button>
                                      {disambig.pinnedLb && (
                                        <Button size="sm" variant="ghost" onClick={() => handleUnpin(r.folder)}>
                                          {t('rename.disambiguate.unpin')}
                                        </Button>
                                      )}
                                      <Button size="sm" variant="ghost" onClick={() => { setExpandedRow(null); setDisambig(null) }}>
                                        {t('rename.disambiguate.skip')}
                                      </Button>
                                    </div>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </TableShell>

              {/* Dry-run banner */}
              <div style={{
                marginTop: 16, padding: '12px 16px', borderRadius: 6,
                background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
                fontSize: 12, color: 'var(--lbb-fg2)',
                display: 'flex', alignItems: 'flex-start', gap: 12,
              }}>
                <Icon name="info" size={14} style={{ color: 'var(--lbb-info-fg)', marginTop: 1 }} />
                <div style={{ flex: 1 }}>
                  <strong style={{ color: 'var(--lbb-info-fg)' }}>{t('rename.dryrun.title')}</strong> — {t('rename.dryrun.desc')}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Button size="sm" variant="ghost"     icon="copy"     onClick={handleCopyDiff}>{t('rename.dryrun.copyDiff')}</Button>
                  <Button size="sm" variant="secondary" icon="download" onClick={handleExport}>{t('rename.dryrun.exportPlan')}</Button>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

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
