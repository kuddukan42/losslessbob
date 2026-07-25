import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Banner, Icon, Input, Pill, IconButton, TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

// ── Types (mirror backend/disk_scanner.py) ───────────────────────────────────

interface ScanResult {
  path: string
  name: string
  file_count: number
  extensions: string[]
  size_bytes: number
  in_collection: boolean
  lb_number: number | null
}

interface ScanStatus {
  running: boolean
  roots: string[]
  dirs_scanned: number
  found: number
  current_dir: string | null
  results: ScanResult[] | null
  error: string | null
  cancelled: boolean
}

interface AddResult {
  path: string
  ok: boolean
  lb_number: number | null
  error: string | null
}

/** Settings keys this screen persists through /api/db/settings. */
interface ScannerSettings {
  scanner_roots: string | null
  scanner_excludes: string | null
}

function fmtSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/**
 * Parse the persisted `scanner_roots` meta value into a path list.
 *
 * The value is JSON, but a hand-edited or pre-TODO-250 meta row could be
 * anything; a bad parse must not blank the screen, so it degrades to an empty
 * list rather than throwing during render.
 */
function parseRoots(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((p): p is string => typeof p === 'string') : []
  } catch {
    return []
  }
}

// ── Root list editor ─────────────────────────────────────────────────────────

function RootList({ roots, onChange }: {
  roots: string[]
  onChange: (next: string[]) => void
}) {
  const { t } = useTranslation()

  const addRoots = useCallback(async () => {
    const picked = await window.api.pickFolders()
    if (!picked?.length) return
    onChange([...roots, ...picked.filter(p => !roots.includes(p))])
  }, [roots, onChange])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {roots.length === 0 ? (
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          {t('scanner.roots.empty')}
        </span>
      ) : roots.map(root => (
        <div key={root} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 8px', borderRadius: 6,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        }}>
          <Icon name="folder" size={13} style={{ flexShrink: 0, opacity: 0.6 }} />
          <span
            title={root}
            style={{
              flex: 1, minWidth: 0, fontFamily: 'var(--lbb-mono)',
              fontSize: 'var(--lbb-fs-10-5)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              direction: 'rtl', textAlign: 'left',
            }}
          >
            {root}
          </span>
          <IconButton
            icon="x"
            title={t('scanner.roots.remove')}
            onClick={() => onChange(roots.filter(r => r !== root))}
          />
        </div>
      ))}
      <Button icon="folderPlus" size="sm" variant="ghost" onClick={() => { void addRoots() }}>
        {t('scanner.roots.add')}
      </Button>
    </div>
  )
}

// ── Results table ────────────────────────────────────────────────────────────

function ResultsTable({ rows, selected, onToggle, onToggleAll }: {
  rows: ScanResult[]
  selected: Set<string>
  onToggle: (path: string) => void
  onToggleAll: () => void
}) {
  const { t } = useTranslation()
  const selectable = rows.filter(r => !r.in_collection && r.lb_number !== null)
  const allSelected = selectable.length > 0 && selectable.every(r => selected.has(r.path))

  return (
    <TableShell>
      <colgroup>
        <col style={{ width: 3 }} />
        <col style={{ width: 34 }} />
        <col />
        <col style={{ width: 90 }} />
        <col style={{ width: 90 }} />
        <col style={{ width: 130 }} />
        <col style={{ width: 90 }} />
        <col style={{ width: 130 }} />
      </colgroup>
      <thead>
        <tr>
          <th style={{ width: 3, padding: 0, background: 'var(--lbb-surface2)' }} />
          <TH align="center">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={onToggleAll}
              disabled={selectable.length === 0}
              title={t('scanner.table.selectAll')}
            />
          </TH>
          <TH>{t('scanner.table.folder')}</TH>
          <TH align="right">{t('scanner.table.files')}</TH>
          <TH align="right">{t('scanner.table.size')}</TH>
          <TH>{t('scanner.table.formats')}</TH>
          <TH align="right">{t('scanner.table.lb')}</TH>
          <TH>{t('scanner.table.status')}</TH>
        </tr>
      </thead>
      <tbody>
        {rows.map(row => {
          const addable = !row.in_collection && row.lb_number !== null
          return (
            <TR
              key={row.path}
              edge={row.in_collection ? 'mute' : addable ? 'ok' : 'warn'}
              selected={selected.has(row.path)}
              onClick={addable ? () => onToggle(row.path) : undefined}
              style={row.in_collection ? { opacity: 0.5 } : undefined}
            >
              <TD align="center">
                <input
                  type="checkbox"
                  checked={selected.has(row.path)}
                  disabled={!addable}
                  onChange={() => onToggle(row.path)}
                  onClick={e => e.stopPropagation()}
                />
              </TD>
              <TD>
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.name}</div>
                <div title={row.path} style={{
                  fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)',
                  color: 'var(--lbb-fg3)', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {row.path}
                </div>
              </TD>
              <TD align="right" mono>{row.file_count}</TD>
              <TD align="right" mono dim>{fmtSize(row.size_bytes)}</TD>
              <TD dim>{row.extensions.join(' ')}</TD>
              <TD align="right" mono>{row.lb_number ?? '—'}</TD>
              <TD>
                {row.in_collection ? (
                  <Pill tone="mute" soft>{t('scanner.status.inCollection')}</Pill>
                ) : row.lb_number === null ? (
                  <Pill tone="warn" soft>{t('scanner.status.noLb')}</Pill>
                ) : (
                  <Pill tone="ok" soft>{t('scanner.status.new')}</Pill>
                )}
              </TD>
            </TR>
          )
        })}
      </tbody>
    </TableShell>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────────

export function ScreenScanner(): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [roots, setRoots] = useState<string[]>([])
  const [excludes, setExcludes] = useState('')
  const [settingsLoaded, setSettingsLoaded] = useState(false)
  const [rows, setRows] = useState<ScanResult[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [addSummary, setAddSummary] = useState<{ added: number; failed: number } | null>(null)
  const [startError, setStartError] = useState<string | null>(null)

  const { data: settings } = useQuery<ScannerSettings>({
    queryKey: ['db-settings'],
    queryFn: () => fetch(`${BASE}/api/db/settings`).then(r => r.json()),
    staleTime: 300_000,
  })

  // Hydrate the editors once, then leave them alone — a later refetch of the
  // shared ['db-settings'] query must not stomp on paths the user is editing.
  useEffect(() => {
    if (!settings || settingsLoaded) return
    setRoots(parseRoots(settings.scanner_roots))
    setExcludes(settings.scanner_excludes ?? '')
    setSettingsLoaded(true)
  }, [settings, settingsLoaded])

  const persist = useCallback((nextRoots: string[], nextExcludes: string) => {
    void fetch(`${BASE}/api/db/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scanner_roots: JSON.stringify(nextRoots),
        scanner_excludes: nextExcludes,
      }),
    })
  }, [])

  const { data: status } = useQuery<ScanStatus>({
    queryKey: ['scanner-status'],
    queryFn: () => fetch(`${BASE}/api/scanner/scan/status`).then(r => r.json()),
    refetchInterval: q => (q.state.data?.running ? 700 : false),
  })
  const running = status?.running ?? false

  // The job dict holds the last scan's results even after a restart of this
  // screen, so adopt them whenever they change identity — that also repopulates
  // the table when the user navigates back mid-scan.
  useEffect(() => {
    if (status?.results) {
      setRows(status.results)
      setSelected(new Set())
    }
  }, [status?.results])

  const startScan = useCallback(async () => {
    setStartError(null)
    setAddSummary(null)
    const res = await fetch(`${BASE}/api/scanner/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        roots,
        excludes: excludes.split(',').map(s => s.trim()).filter(Boolean),
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setStartError(body.error || `HTTP ${res.status}`)
      return
    }
    setRows([])
    setSelected(new Set())
    persist(roots, excludes)
    void qc.invalidateQueries({ queryKey: ['scanner-status'] })
  }, [roots, excludes, persist, qc])

  const cancelScan = useCallback(() => {
    void fetch(`${BASE}/api/scanner/scan/cancel`, { method: 'POST' })
  }, [])

  const addSelected = useCallback(async () => {
    const paths = [...selected]
    if (!paths.length) return
    const res = await fetch(`${BASE}/api/scanner/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths }),
    })
    const body: { results?: AddResult[]; added?: number } = await res.json().catch(() => ({}))
    const results = body.results ?? []
    const addedPaths = new Set(results.filter(r => r.ok).map(r => r.path))
    setRows(prev => prev.map(r => (
      addedPaths.has(r.path) ? { ...r, in_collection: true } : r
    )))
    setSelected(new Set())
    setAddSummary({
      added: addedPaths.size,
      failed: results.length - addedPaths.size,
    })
    void qc.invalidateQueries({ queryKey: ['collection'] })
  }, [selected, qc])

  const toggle = useCallback((path: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setSelected(prev => {
      const selectable = rows.filter(r => !r.in_collection && r.lb_number !== null)
      const allOn = selectable.length > 0 && selectable.every(r => prev.has(r.path))
      return allOn ? new Set() : new Set(selectable.map(r => r.path))
    })
  }, [rows])

  const counts = useMemo(() => ({
    total: rows.length,
    addable: rows.filter(r => !r.in_collection && r.lb_number !== null).length,
    known: rows.filter(r => r.in_collection).length,
  }), [rows])

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
          <Icon name="folderPlus" size={18} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('scanner.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('scanner.subtitle')}
          </div>
        </div>
        {rows.length > 0 && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Pill tone="mute" soft>{t('scanner.header.found', { count: counts.total })}</Pill>
            <Pill tone="ok" soft>{t('scanner.header.addable', { count: counts.addable })}</Pill>
          </div>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Left: scan configuration */}
        <aside style={{
          width: 320, flexShrink: 0, borderRight: '1px solid var(--lbb-border)',
          padding: 16, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto',
        }}>
          <div>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', fontWeight: 600, letterSpacing: '0.04em',
              textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 8,
            }}>
              {t('scanner.roots.heading')}
            </div>
            <RootList roots={roots} onChange={next => { setRoots(next); persist(next, excludes) }} />
          </div>

          <div>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', fontWeight: 600, letterSpacing: '0.04em',
              textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 8,
            }}>
              {t('scanner.excludes.heading')}
            </div>
            <Input
              value={excludes}
              placeholder={t('scanner.excludes.placeholder')}
              onChange={e => setExcludes(e.target.value)}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 6 }}>
              {t('scanner.excludes.hint')}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              icon="search"
              variant="primary"
              disabled={running || roots.length === 0}
              onClick={() => { void startScan() }}
            >
              {t('scanner.actions.scan')}
            </Button>
            {running && (
              <Button icon="x" variant="ghost" onClick={cancelScan}>
                {t('scanner.actions.cancel')}
              </Button>
            )}
          </div>

          {running && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 'var(--lbb-fs-11-5)' }}>
                {t('scanner.progress.scanning', {
                  dirs: status?.dirs_scanned ?? 0,
                  found: status?.found ?? 0,
                })}
              </span>
              <span title={status?.current_dir ?? ''} style={{
                fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)',
                color: 'var(--lbb-fg3)', overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap', direction: 'rtl',
              }}>
                {status?.current_dir ?? ''}
              </span>
            </div>
          )}

          {startError && <Banner tone="bad" icon="alert">{startError}</Banner>}
          {status?.error && !running && <Banner tone="bad" icon="alert">{status.error}</Banner>}
          {status?.cancelled && !running && (
            <Banner tone="warn" icon="alert">{t('scanner.progress.cancelled')}</Banner>
          )}
        </aside>

        {/* Right: results */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
          {rows.length > 0 && (
            <div style={{
              padding: '10px 16px', borderBottom: '1px solid var(--lbb-border)',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <Button
                icon="plus"
                variant="primary"
                size="sm"
                disabled={selected.size === 0}
                onClick={() => { void addSelected() }}
              >
                {selected.size === 0
                  ? t('scanner.actions.add')
                  : t('scanner.actions.addSelected', { count: selected.size })}
              </Button>
              {counts.known > 0 && (
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                  {t('scanner.header.known', { count: counts.known })}
                </span>
              )}
              {addSummary && (
                <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11-5)' }}>
                  {t('scanner.added.summary', addSummary)}
                </span>
              )}
            </div>
          )}

          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            {rows.length === 0 ? (
              <div style={{
                height: '100%', display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 10,
                padding: 40, textAlign: 'center',
              }}>
                <Icon name="folder" size={36} style={{ opacity: 0.2 }} />
                <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600 }}>
                  {running ? t('scanner.empty.running') : t('scanner.empty.title')}
                </span>
                <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', maxWidth: 420 }}>
                  {t('scanner.empty.detail')}
                </span>
              </div>
            ) : (
              <ResultsTable
                rows={rows}
                selected={selected}
                onToggle={toggle}
                onToggleAll={toggleAll}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
