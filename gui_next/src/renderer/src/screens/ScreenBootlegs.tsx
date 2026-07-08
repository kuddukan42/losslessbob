import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, Chip, Input, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type BootlegStatus = 'Public' | 'Private' | 'Unknown'
type OwnedFilter   = 'any' | 'owned' | 'unowned'

interface BootlegRow {
  id:       number
  lb:       string
  lbNumber: number
  title:    string
  dateStr:  string
  year:     number | null
  location: string
  cdCount:  number
  lbbcdId:  number | null
  lbbcdUrl: string | null
  status:   BootlegStatus
  owned:    boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function mapRow(d: any): BootlegRow {
  const raw = (d.lb_status ?? '').toLowerCase()
  return {
    id:       d.id as number,
    lb:       `LB-${String(d.lb_number).padStart(5, '0')}`,
    lbNumber: d.lb_number as number,
    title:    d.title    ?? '',
    dateStr:  d.date_str ?? '',
    year:     d.year     ?? null,
    location: d.location ?? '',
    cdCount:  d.cd_count ?? 0,
    lbbcdId:  d.lbbcd_id  ?? null,
    lbbcdUrl: d.lbbcd_url ?? null,
    status:   raw === 'public' ? 'Public' : raw === 'private' ? 'Private' : 'Unknown',
    owned:    Boolean(d.owned),
  }
}

function statusTone(s: BootlegStatus): 'ok' | 'info' | 'mute' {
  return s === 'Public' ? 'ok' : s === 'Private' ? 'info' : 'mute'
}

function lbbcdLabel(id: number): string {
  return `LBBCD-${String(id).padStart(5, '0')}`
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenBootlegs(): React.JSX.Element {
  const navigate = useNavigate()

  const [rows, setRows]                   = useState<BootlegRow[]>([])
  const [total, setTotal]                 = useState(0)
  const [loading, setLoading]             = useState(false)
  const [search, setSearch]               = useState('')
  const [debouncedSearch, setDebouncedQ]  = useState('')
  const [statusFilter, setStatusFilter]   = useState<string>('')
  const [ownedFilter, setOwnedFilter]     = useState<OwnedFilter>('any')
  const [selected, setSelected]           = useState<BootlegRow | null>(null)
  const [yearFilter, setYearFilter]       = useState<string | null>(null)
  const [cdFilter, setCdFilter]           = useState<'all' | '1' | '2' | '3+'>('all')
  const [yearsOpen, setYearsOpen]         = useState(false)
  const [cdsOpen, setCdsOpen]             = useState(false)
  const [toast, setToast]                 = useState<{ msg: string; tone: 'ok' | 'bad' | 'info' } | null>(null)

  const showToast = useCallback((msg: string, tone: 'ok' | 'bad' | 'info') => setToast({ msg, tone }), [])

  const tableParentRef = useRef<HTMLDivElement>(null)
  const yearsDropRef   = useRef<HTMLDivElement>(null)
  const cdsDropRef     = useRef<HTMLDivElement>(null)

  // Debounce search input 200ms
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(search), 200)
    return () => clearTimeout(t)
  }, [search])

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (yearsDropRef.current && !yearsDropRef.current.contains(e.target as Node)) setYearsOpen(false)
      if (cdsDropRef.current   && !cdsDropRef.current.contains(e.target as Node))   setCdsOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Load all bootleg rows on mount; fetch a second page if total > 1000
  useEffect(() => {
    setLoading(true)
    fetch(`${BASE}/api/bootlegs?limit=1000&offset=0`)
      .then(r => r.json())
      .then(async (data: { rows: any[]; total: number }) => {
        const first      = data.rows ?? []
        const serverTotal = data.total ?? first.length
        setTotal(serverTotal)
        if (serverTotal > 1000) {
          const d2 = await fetch(`${BASE}/api/bootlegs?limit=1000&offset=1000`).then(r => r.json())
          setRows([...first, ...(d2.rows ?? [])].map(mapRow))
        } else {
          setRows(first.map(mapRow))
        }
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [])

  // ── Derived counts for chips ───────────────────────────────────────────────

  const ownedCount   = useMemo(() => rows.filter(r =>  r.owned).length,              [rows])
  const unownedCount = useMemo(() => rows.filter(r => !r.owned).length,              [rows])
  const privateCount = useMemo(() => rows.filter(r => r.status === 'Private').length, [rows])

  const yearList = useMemo(() => {
    const s = new Set<number>()
    rows.forEach(r => { if (r.year !== null) s.add(r.year) })
    return Array.from(s).sort((a, b) => b - a)
  }, [rows])

  // ── Client-side filtering ──────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    const q = debouncedSearch.toLowerCase()
    return rows.filter(r => {
      if (q && !r.title.toLowerCase().includes(q) && !r.location.toLowerCase().includes(q)) return false
      if (statusFilter && r.status !== statusFilter) return false
      if (ownedFilter === 'owned'   && !r.owned) return false
      if (ownedFilter === 'unowned' &&  r.owned) return false
      if (yearFilter !== null && (r.year === null || String(r.year) !== yearFilter)) return false
      if (cdFilter === '1'  && r.cdCount !== 1) return false
      if (cdFilter === '2'  && r.cdCount !== 2) return false
      if (cdFilter === '3+' && r.cdCount < 3)   return false
      return true
    })
  }, [rows, debouncedSearch, statusFilter, ownedFilter, yearFilter, cdFilter])

  // Other bootleg titles that share the same LB number as the selected row
  const detailOthers = useMemo(() => {
    if (!selected) return []
    return rows.filter(r => r.lbNumber === selected.lbNumber && r.id !== selected.id)
  }, [rows, selected])

  // ── Virtualizer ───────────────────────────────────────────────────────────

  const virtualizer = useVirtualizer({
    count:           filteredRows.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize:    () => 34,
    overscan:        12,
  })

  // ── Filter helpers ────────────────────────────────────────────────────────

  const hasFilters = search !== '' || statusFilter !== '' || ownedFilter !== 'any' || yearFilter !== null || cdFilter !== 'all'

  const clearFilters = () => {
    setSearch('')
    setStatusFilter('')
    setOwnedFilter('any')
    setYearFilter(null)
    setCdFilter('all')
  }

  const exportCsv = () => {
    const header = 'LB#,Title,Date,Year,Location,CDs,Status,Owned\n'
    const lines = filteredRows.map(r =>
      [r.lb, r.title, r.dateStr, r.year ?? '', r.location, r.cdCount, r.status, r.owned ? 'Yes' : 'No']
        .map(v => `"${String(v ?? '').replace(/"/g, '""')}"`)
        .join(',')
    )
    const blob = new Blob([header + lines.join('\n')], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = Object.assign(document.createElement('a'), { href: url, download: 'losslessbob_bootlegs.csv' })
    a.click()
    URL.revokeObjectURL(url)
  }

  const toggleStatus = (val: string) =>
    setStatusFilter(f => (f === val ? '' : val))

  const toggleOwned = (val: OwnedFilter) =>
    setOwnedFilter(f => (f === val ? 'any' : val))

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div style={{ padding: '18px 24px 12px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-20)', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Bootleg titles
          </h1>
          <span style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
            {total > 0 ? `${total.toLocaleString()} titles · ` : ''}LBBCD catalog
          </span>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" icon="download" onClick={exportCsv}>Export CSV</Button>
          <Button
            variant="secondary"
            size="sm"
            icon="refresh"
            onClick={() =>
              fetch(`${BASE}/api/bootlegs/scrape`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: false }),
              })
                .then(r => r.json())
                .then((d: { ok?: boolean; running?: boolean; error?: string }) =>
                  showToast(d.ok ? 'Scrape started' : (d.error ?? 'Scrape failed'), d.ok ? 'info' : 'bad')
                )
                .catch(() => showToast('Scrape request failed', 'bad'))
            }
          >
            Refresh LBBCD
          </Button>
        </div>

        {/* Filter row */}
        <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Input
            icon="search"
            placeholder="Search title or location…"
            size="sm"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: 360 }}
          />
          {/* Year filter popover */}
          <div ref={yearsDropRef} style={{ position: 'relative' }}>
            <Button
              variant={yearFilter !== null ? 'secondary' : 'ghost'}
              size="sm"
              iconRight="chevDown"
              onClick={() => setYearsOpen(v => !v)}
            >
              {yearFilter ?? 'Year'}
            </Button>
            {yearsOpen && (
              <div style={{
                position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 100,
                background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 4,
                minWidth: 240, maxHeight: 320, overflowY: 'auto',
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
              }}>
                <button
                  onClick={() => { setYearFilter(null); setYearsOpen(false) }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '5px 10px', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', border: 'none',
                    background: yearFilter === null ? 'var(--lbb-accent-bg)' : 'transparent',
                    color: 'var(--lbb-fg)', borderRadius: 5, marginBottom: 4,
                  }}
                >
                  All years
                </button>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 2 }}>
                  {yearList.map(y => (
                    <button
                      key={y}
                      onClick={() => { setYearFilter(String(y)); setYearsOpen(false) }}
                      style={{
                        textAlign: 'center',
                        padding: '5px 4px', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', border: 'none',
                        background: String(y) === yearFilter ? 'var(--lbb-accent-bg)' : 'transparent',
                        color: 'var(--lbb-fg)', borderRadius: 5,
                      }}
                    >
                      {y}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* CDs filter popover */}
          <div ref={cdsDropRef} style={{ position: 'relative' }}>
            <Button
              variant={cdFilter !== 'all' ? 'secondary' : 'ghost'}
              size="sm"
              iconRight="chevDown"
              onClick={() => setCdsOpen(v => !v)}
            >
              {cdFilter === 'all' ? 'CDs' : cdFilter === '3+' ? '3+ CDs' : `${cdFilter} CD`}
            </Button>
            {cdsOpen && (
              <div style={{
                position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 100,
                background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 4,
                minWidth: 120,
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
              }}>
                {(['all', '1', '2', '3+'] as const).map(opt => (
                  <button
                    key={opt}
                    onClick={() => { setCdFilter(opt); setCdsOpen(false) }}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '5px 10px', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', border: 'none',
                      background: opt === cdFilter ? 'var(--lbb-accent-bg)' : 'transparent',
                      color: 'var(--lbb-fg)', borderRadius: 5,
                    }}
                  >
                    {opt === 'all' ? 'All' : opt === '3+' ? '3+ CDs' : `${opt} CD`}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Button
            variant={statusFilter ? 'secondary' : 'ghost'}
            size="sm"
            iconRight="chevDown"
            onClick={() => toggleStatus('Private')}
          >
            {statusFilter || 'All statuses'}
          </Button>
          <Chip count={ownedCount}   active={ownedFilter === 'owned'}   onClick={() => toggleOwned('owned')}>
            Owned
          </Chip>
          <Chip count={unownedCount} active={ownedFilter === 'unowned'} onClick={() => toggleOwned('unowned')}>
            Unowned
          </Chip>
          <Chip count={privateCount} active={statusFilter === 'Private'} onClick={() => toggleStatus('Private')}>
            Private
          </Chip>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" onClick={clearFilters} disabled={!hasFilters}>
            Clear
          </Button>
        </div>
      </div>

      {/* ── Two-pane body ────────────────────────────────────────────────── */}
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: selected ? '1fr 380px' : '1fr',
        minHeight: 0,
      }}>

        {/* ── Main table ─────────────────────────────────────────────── */}
        <div ref={tableParentRef} style={{ overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 90 }} />
              <col style={{ width: 55 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 50 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 60 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH>LB#</TH>
                <TH>Title</TH>
                <TH>Date</TH>
                <TH>Year</TH>
                <TH>Location</TH>
                <TH align="center">CDs</TH>
                <TH>Status</TH>
                <TH align="center">Owned</TH>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const vItems    = virtualizer.getVirtualItems()
                const padTop    = vItems.length > 0 ? vItems[0].start : 0
                const padBottom = vItems.length > 0
                  ? virtualizer.getTotalSize() - vItems[vItems.length - 1].end
                  : 0
                return (
                  <>
                    {padTop > 0 && (
                      <tr><td colSpan={9} style={{ height: padTop, padding: 0, border: 0 }} /></tr>
                    )}
                    {vItems.map(vItem => {
                      const r = filteredRows[vItem.index]
                      if (!r) return null
                      const isSel = selected?.id === r.id
                      return (
                        <TR
                          key={r.id}
                          edge={statusTone(r.status)}
                          selected={isSel}
                          onClick={() => setSelected(isSel ? null : r)}
                          style={{ height: vItem.size }}
                        >
                          <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>
                            {r.lb}
                          </TD>
                          <TD style={{ fontWeight: isSel ? 600 : 500 }}>
                            {r.title}
                          </TD>
                          <TD mono>{r.dateStr}</TD>
                          <TD mono>{r.year ?? ''}</TD>
                          <TD>{r.location}</TD>
                          <TD align="center" mono>{r.cdCount || ''}</TD>
                          <TD>
                            <Pill tone={statusTone(r.status)} soft>{r.status}</Pill>
                          </TD>
                          <TD align="center">
                            {r.owned
                              ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-bar)' }} />
                              : <Icon name="x"     size={12} style={{ color: 'var(--lbb-fg3)'  }} />
                            }
                          </TD>
                        </TR>
                      )
                    })}
                    {padBottom > 0 && (
                      <tr><td colSpan={9} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>
                    )}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {loading && rows.length === 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
            }}>
              Loading…
            </div>
          )}

          {!loading && rows.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                  No bootleg titles
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>
                  Try "Refresh LBBCD" to fetch the catalog
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Detail panel ────────────────────────────────────────────── */}
        {selected && (
          <aside style={{
            borderLeft: '1px solid var(--lbb-border)',
            background: 'var(--lbb-surface)',
            overflowY: 'auto',
            padding: 18,
            flexShrink: 0,
          }}>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
              letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
            }}>
              Bootleg detail
            </div>

            <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-14)', color: 'var(--lbb-accent-mid)', fontWeight: 700 }}>
              {selected.lb}
            </div>
            <h2 style={{ margin: '4px 0 4px', fontSize: 'var(--lbb-fs-20)', fontWeight: 700, letterSpacing: '-0.01em' }}>
              {selected.title}
            </h2>
            <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
              {[
                selected.year,
                selected.location || null,
                selected.cdCount > 0 ? `${selected.cdCount} CD${selected.cdCount !== 1 ? 's' : ''}` : null,
                selected.lbbcdId != null ? lbbcdLabel(selected.lbbcdId) : null,
              ].filter(Boolean).join(' · ')}
            </div>

            {/* Cover art placeholder */}
            <div style={{
              marginTop: 14, height: 200, borderRadius: 8,
              background: 'linear-gradient(135deg, #1c1a17 0%, var(--lbb-accent-lo) 100%)',
              color: '#fff', padding: 18,
              display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
              position: 'relative', overflow: 'hidden',
            }}>
              <div style={{
                position: 'absolute', inset: 0, opacity: 0.25,
                background: 'repeating-linear-gradient(45deg, transparent 0 12px, rgba(255,255,255,0.08) 12px 13px)',
              }} />
              <div style={{ position: 'relative', fontSize: 'var(--lbb-fs-10-5)', letterSpacing: '0.14em', textTransform: 'uppercase', opacity: 0.7 }}>
                {selected.lbbcdId != null ? lbbcdLabel(selected.lbbcdId) : 'Bootleg'}{selected.year ? ` · ${selected.year}` : ''}
              </div>
              <div style={{ position: 'relative', fontSize: 'var(--lbb-fs-17)', fontWeight: 700, marginTop: 2 }}>
                {selected.title}
              </div>
              <div style={{ position: 'relative', fontSize: 'var(--lbb-fs-11-5)', opacity: 0.8, marginTop: 2 }}>
                {[
                  selected.cdCount > 0 ? `${selected.cdCount}-CD set` : null,
                  selected.location || null,
                ].filter(Boolean).join(' · ')}
              </div>
            </div>

            {/* Meta grid */}
            <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '90px 1fr', gap: '5px 12px', fontSize: 'var(--lbb-fs-12)' }}>
              <span style={{ color: 'var(--lbb-fg3)' }}>LB#</span>
              <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{selected.lb}</span>

              {selected.cdCount > 0 && (
                <>
                  <span style={{ color: 'var(--lbb-fg3)' }}>CDs</span>
                  <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{selected.cdCount}</span>
                </>
              )}

              {selected.lbbcdId != null && (
                <>
                  <span style={{ color: 'var(--lbb-fg3)' }}>LBBCD #</span>
                  <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>
                    {lbbcdLabel(selected.lbbcdId)}
                  </span>
                </>
              )}

              <span style={{ color: 'var(--lbb-fg3)' }}>Status</span>
              <span>
                <Pill tone={statusTone(selected.status)} soft>{selected.status}</Pill>
              </span>

              <span style={{ color: 'var(--lbb-fg3)' }}>Owned</span>
              <span style={{ display: 'flex', alignItems: 'center' }}>
                {selected.owned
                  ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-bar)' }} />
                  : <Icon name="x"     size={12} style={{ color: 'var(--lbb-fg3)'  }} />
                }
              </span>
            </div>

            {/* CTAs */}
            <div style={{ marginTop: 14, display: 'flex', gap: 6 }}>
              <Button
                size="sm"
                variant="primary"
                icon="search"
                onClick={() => navigate(`/search?lb=${encodeURIComponent(selected.lb)}`)}
              >
                Open in search
              </Button>
              {selected.lbbcdUrl && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => window.open(selected.lbbcdUrl!, '_blank')}
                >
                  Open LBBCD
                </Button>
              )}
            </div>

            {/* Other titles for same LB */}
            <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--lbb-border)' }}>
              <div style={{
                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
                letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6,
              }}>
                Other titles for this LB
              </div>
              {detailOthers.length === 0 ? (
                <div style={{
                  fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)',
                  padding: '10px 12px',
                  border: '1px dashed var(--lbb-border2)', borderRadius: 6,
                }}>
                  Only bootleg title issued for {selected.lb}.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {detailOthers.map(other => (
                    <div
                      key={other.id}
                      onClick={() => setSelected(other)}
                      style={{
                        padding: '8px 10px', borderRadius: 6, cursor: 'pointer',
                        border: '1px solid var(--lbb-border)',
                        background: 'var(--lbb-surface2)',
                      }}
                    >
                      <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>{other.title}</div>
                      <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2, fontFamily: 'var(--lbb-mono)' }}>
                        {other.lbbcdId != null ? lbbcdLabel(other.lbbcdId) : '—'}
                        {other.cdCount > 0 ? ` · ${other.cdCount} CDs` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
      {toast && (
        <div style={{
          position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
          background: toast.tone === 'ok' ? 'var(--lbb-ok-bar)' : toast.tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)',
          color: '#fff', padding: '9px 18px', borderRadius: 8,
          fontSize: 'var(--lbb-fs-13)', fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
          pointerEvents: 'none',
        }}
          ref={el => { if (el) setTimeout(() => setToast(null), 3500) }}
        >{toast.msg}</div>
      )}
    </div>
  )
}
