import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type MasterStatus  = 'Public' | 'Private' | 'Missing'
type RatingGrade   = 'A' | 'A−' | 'B+' | 'B' | 'B−' | 'C' | '—'
type OwnershipFilter = 'any' | 'owned' | 'not-owned'

interface SearchRow {
  lb: string
  lbNumber: number
  status: MasterStatus
  date: string
  year: number
  decade: string
  location: string
  rating: RatingGrade
  description: string
  xref: string | null
  owned: boolean
}

type FlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'row'; row: SearchRow }

interface SavedView { id: string; name: string }

// ── Constants ─────────────────────────────────────────────────────────────────

const SAVED_VIEWS: SavedView[] = [
  { id: 'public',  name: 'Public only'      },
  { id: 'rated',   name: 'Rated A or A−'    },
  { id: 'missing', name: 'Missing / wanted' },
]

const VALID_RATINGS = new Set(['A', 'A−', 'B+', 'B', 'B−', 'C'])

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractYear(dateStr: string): number {
  if (!dateStr) return 0
  const parts = dateStr.split('/')
  if (parts.length < 3) return 0
  const n = parseInt(parts[parts.length - 1].trim(), 10)
  if (isNaN(n)) return 0
  if (n < 100) return n >= 49 ? 1900 + n : 2000 + n
  return n
}

function ratingTone(r: RatingGrade): 'ok' | 'info' | 'warn' | 'mute' {
  if (r === 'A' || r === 'A−') return 'ok'
  if (r === 'B+' || r === 'B') return 'info'
  if (r === 'B−' || r === 'C') return 'warn'
  return 'mute'
}

function statusTone(s: MasterStatus): 'ok' | 'warn' | 'mute' {
  if (s === 'Public')  return 'ok'
  if (s === 'Missing') return 'warn'
  return 'mute'
}

function toggleSet(setFn: React.Dispatch<React.SetStateAction<Set<string>>>, val: string) {
  setFn(prev => {
    const next = new Set(prev)
    if (next.has(val)) next.delete(val)
    else next.add(val)
    return next
  })
}

// ── FacetGroup ────────────────────────────────────────────────────────────────

interface FacetGroupProps {
  title: string
  items: Array<{ label: string; count?: number }>
  active: Set<string>
  onToggle: (label: string) => void
}

function FacetGroup({ title, items, active, onToggle }: FacetGroupProps) {
  const [open, setOpen] = useState(true)
  return (
    <div style={{ borderBottom: '1px solid var(--lbb-border)' }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--lbb-fg3)',
        }}
      >
        {title}
        <Icon name={open ? 'chevDown' : 'chevRight'} size={11} />
      </button>
      {open && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '0 10px 10px' }}>
          {items.map(({ label, count }) => (
            <Chip key={label} size="sm" active={active.has(label)} onClick={() => onToggle(label)} count={count}>
              {label}
            </Chip>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ActiveFilter chip ─────────────────────────────────────────────────────────

function ActiveFilter({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 4, fontSize: 11,
      background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)',
    }}>
      {label}
      <button
        type="button" onClick={onRemove}
        style={{ display: 'flex', background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'inherit' }}
      >
        <Icon name="x" size={10} />
      </button>
    </span>
  )
}

// ── Year range slider ─────────────────────────────────────────────────────────

interface YearRangeProps {
  min: number; max: number; low: number; high: number
  onChange: (lo: number, hi: number) => void
}

function YearRangeSlider({ min, max, low, high, onChange }: YearRangeProps) {
  return (
    <div style={{ padding: '4px 12px 10px', display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: 'var(--lbb-fg3)', width: 18, flexShrink: 0 }}>From</span>
        <input
          type="range" min={min} max={max} value={low}
          onChange={e => onChange(Math.min(+e.target.value, high - 1), high)}
          style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--lbb-accent-mid)' }}
        />
        <span style={{ fontSize: 10.5, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', width: 34, textAlign: 'right' }}>
          {low}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: 'var(--lbb-fg3)', width: 18, flexShrink: 0 }}>To</span>
        <input
          type="range" min={min} max={max} value={high}
          onChange={e => onChange(low, Math.max(+e.target.value, low + 1))}
          style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--lbb-accent-mid)' }}
        />
        <span style={{ fontSize: 10.5, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', width: 34, textAlign: 'right' }}>
          {high}
        </span>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenSearch(): React.JSX.Element {
  const [rows, setRows]               = useState<SearchRow[]>([])
  const [loading, setLoading]         = useState(false)
  const [search, setSearch]           = useState('')
  const [searchField, setSearchField] = useState('all')
  const [dataYearRange, setDataYearRange] = useState<[number, number]>([1961, 2030])
  const [yearRange, setYearRange]     = useState<[number, number]>([1961, 2030])
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())

  const [activeDec,    setActiveDec]    = useState<Set<string>>(new Set())
  const [activeStatus, setActiveStatus] = useState<Set<string>>(new Set())
  const [activeRating, setActiveRating] = useState<Set<string>>(new Set())
  const [ownership,    setOwnership]    = useState<OwnershipFilter>('any')

  const tableParentRef = useRef<HTMLDivElement>(null)

  // ── Fetch years for range bounds ───────────────────────────────────────────

  useEffect(() => {
    fetch(`${BASE}/api/search/years`)
      .then(r => r.json())
      .then((years: number[]) => {
        if (!Array.isArray(years) || years.length === 0) return
        const lo = Math.min(...years)
        const hi = Math.max(...years)
        setDataYearRange([lo, hi])
        setYearRange([lo, hi])
      })
      .catch(() => {})
  }, [])

  // ── Fetch search results (debounced 200ms) ─────────────────────────────────

  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true)
      const url = `${BASE}/api/search?q=${encodeURIComponent(search)}&field=${encodeURIComponent(searchField)}`
      fetch(url)
        .then(r => r.json())
        .then((data: any[]) => {
          if (!Array.isArray(data)) { setRows([]); return }
          const mapped: SearchRow[] = data.map((d: any) => {
            const yr  = extractYear(d.date_str ?? '')
            const dec = yr > 0 ? `${Math.floor(yr / 10) * 10}s` : '?'
            const raw = d.rating ?? ''
            return {
              lb:          `LB-${String(d.lb_number).padStart(5, '0')}`,
              lbNumber:    d.lb_number as number,
              status:      ({ public: 'Public', private: 'Private', missing: 'Missing' }[
                              d.lb_status as string
                           ] ?? 'Missing') as MasterStatus,
              date:        d.date_str ?? '',
              year:        yr,
              decade:      dec,
              location:    d.location ?? '',
              rating:      (VALID_RATINGS.has(raw) ? raw : '—') as RatingGrade,
              description: d.description ?? '',
              xref:        null,
              owned:       true,
            }
          })
          setRows(mapped)
        })
        .catch(() => setRows([]))
        .finally(() => setLoading(false))
    }, 200)
    return () => clearTimeout(timer)
  }, [search, searchField])

  // ── Facet counts (computed from unfiltered rows) ───────────────────────────

  const facetCounts = useMemo(() => {
    const statusC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    const decadeC: Record<string, number> = {}
    for (const r of rows) {
      statusC[r.status] = (statusC[r.status] ?? 0) + 1
      ratingC[r.rating] = (ratingC[r.rating] ?? 0) + 1
      decadeC[r.decade] = (decadeC[r.decade] ?? 0) + 1
    }
    return { statusC, ratingC, decadeC }
  }, [rows])

  // ── Client-side filtering ──────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    return rows.filter(r => {
      if (activeStatus.size > 0 && !activeStatus.has(r.status)) return false
      if (activeRating.size > 0 && !activeRating.has(r.rating)) return false
      if (activeDec.size > 0    && !activeDec.has(r.decade))    return false
      if (ownership === 'owned'     && !r.owned) return false
      if (ownership === 'not-owned' &&  r.owned) return false
      if (r.year > 0 && (r.year < yearRange[0] || r.year > yearRange[1])) return false
      return true
    })
  }, [rows, activeStatus, activeRating, activeDec, ownership, yearRange])

  // ── Group by year ──────────────────────────────────────────────────────────

  const groupedByYear = useMemo(() => {
    const map = new Map<string, SearchRow[]>()
    for (const r of filteredRows) {
      const key = r.year > 0 ? String(r.year) : 'Unknown'
      const arr = map.get(key)
      if (arr) arr.push(r)
      else map.set(key, [r])
    }
    return [...map.entries()].sort(([a], [b]) => {
      const an = a === 'Unknown' ? -1 : parseInt(a, 10)
      const bn = b === 'Unknown' ? -1 : parseInt(b, 10)
      return an - bn
    })
  }, [filteredRows])

  // ── Flat list for virtualizer ──────────────────────────────────────────────

  const flatItems = useMemo((): FlatItem[] => {
    const items: FlatItem[] = []
    for (const [year, yearRows] of groupedByYear) {
      items.push({ kind: 'group', year, count: yearRows.length })
      if (!collapsedYears.has(year)) {
        for (const row of yearRows) items.push({ kind: 'row', row })
      }
    }
    return items
  }, [groupedByYear, collapsedYears])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: (i) => flatItems[i]?.kind === 'group' ? 32 : 34,
    overscan: 12,
  })

  // ── Facet/filter helpers ───────────────────────────────────────────────────

  const clearAll = () => {
    setActiveDec(new Set())
    setActiveStatus(new Set())
    setActiveRating(new Set())
    setOwnership('any')
    setYearRange(dataYearRange)
  }

  const hasActiveFilters =
    activeDec.size > 0 || activeStatus.size > 0 || activeRating.size > 0 || ownership !== 'any'

  const activeFilterChips: Array<{ label: string; onRemove: () => void }> = [
    ...[...activeStatus].map(s => ({ label: `Status: ${s}`, onRemove: () => toggleSet(setActiveStatus, s) })),
    ...[...activeRating].map(r => ({ label: `Rating: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
    ...[...activeDec].map(d   => ({ label: `Decade: ${d}`,  onRemove: () => toggleSet(setActiveDec,    d) })),
    ...(ownership !== 'any'
      ? [{ label: ownership === 'owned' ? 'Owned' : 'Not owned', onRemove: () => setOwnership('any') }]
      : []),
  ]

  // ── Facet item lists ───────────────────────────────────────────────────────

  const decadeItems = ['1960s','1970s','1980s','1990s','2000s','2010s','2020s'].map(d => ({
    label: d, count: facetCounts.decadeC[d],
  }))
  const statusItems = (['Public','Private','Missing'] as MasterStatus[]).map(s => ({
    label: s, count: facetCounts.statusC[s],
  }))
  const ratingItems = (['A','A−','B+','B','B−','C'] as RatingGrade[]).map(r => ({
    label: r, count: facetCounts.ratingC[r],
  }))

  const sep = (
    <span style={{ width: 1, height: 16, background: 'var(--lbb-border)', margin: '0 4px', flexShrink: 0 }} />
  )

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 0 }}>

      {/* ── Facet rail ──────────────────────────────────────────────────── */}
      <aside style={{
        width: 260, flexShrink: 0,
        borderRight: '1px solid var(--lbb-border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--lbb-surface2)',
        overflowY: 'auto',
      }}>

        {/* Saved views */}
        <div style={{ borderBottom: '1px solid var(--lbb-border)', paddingBottom: 4 }}>
          <div style={{
            fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--lbb-fg3)', padding: '10px 12px 6px',
          }}>
            Saved views
          </div>
          {SAVED_VIEWS.map(v => (
            <div
              key={v.id}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                padding: '5px 12px', cursor: 'pointer', fontSize: 12,
                color: 'var(--lbb-fg2)',
              }}
            >
              <Icon name="star" size={12} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{v.name}</span>
            </div>
          ))}
          <button
            type="button"
            style={{
              width: '100%', textAlign: 'left', display: 'block',
              padding: '6px 12px', fontSize: 11.5, marginTop: 4,
              background: 'none', cursor: 'pointer', color: 'var(--lbb-fg3)',
              border: 'none', borderTop: '1px dashed var(--lbb-border2)',
            }}
          >
            + Save current filter as view
          </button>
        </div>

        {/* Facet groups */}
        <FacetGroup
          title="Decade"
          items={decadeItems}
          active={activeDec}
          onToggle={v => toggleSet(setActiveDec, v)}
        />
        <FacetGroup
          title="Status"
          items={statusItems}
          active={activeStatus}
          onToggle={v => toggleSet(setActiveStatus, v)}
        />
        <FacetGroup
          title="Rating"
          items={ratingItems}
          active={activeRating}
          onToggle={v => toggleSet(setActiveRating, v)}
        />

        {/* Ownership segmented control */}
        <div style={{ borderBottom: '1px solid var(--lbb-border)', padding: '8px 12px' }}>
          <div style={{
            fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--lbb-fg3)', marginBottom: 8,
          }}>
            Ownership
          </div>
          <div style={{
            display: 'flex',
            border: '1px solid var(--lbb-border2)', borderRadius: 6, overflow: 'hidden',
          }}>
            {(['any', 'owned', 'not-owned'] as OwnershipFilter[]).map((opt, i) => (
              <button
                key={opt}
                type="button"
                onClick={() => setOwnership(opt)}
                style={{
                  flex: 1, padding: '4px 0', fontSize: 11, cursor: 'pointer',
                  background: ownership === opt ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                  color: ownership === opt ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                  fontWeight: ownership === opt ? 600 : 400,
                  border: 'none',
                  borderLeft: i > 0 ? '1px solid var(--lbb-border2)' : 'none',
                }}
              >
                {opt === 'any' ? 'Any' : opt === 'owned' ? 'Owned' : 'Not owned'}
              </button>
            ))}
          </div>
        </div>

        {/* Year range */}
        <div style={{ borderBottom: '1px solid var(--lbb-border)' }}>
          <div style={{
            fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--lbb-fg3)', padding: '8px 12px 4px',
          }}>
            Year range
          </div>
          <YearRangeSlider
            min={dataYearRange[0]} max={dataYearRange[1]}
            low={yearRange[0]}    high={yearRange[1]}
            onChange={(lo, hi) => setYearRange([lo, hi])}
          />
        </div>

        {/* Clear all */}
        <div style={{ padding: '10px 12px', marginTop: 'auto' }}>
          <Button
            variant="ghost" size="sm"
            onClick={clearAll}
            disabled={!hasActiveFilters}
            style={{ width: '100%' }}
          >
            Clear all filters
          </Button>
        </div>
      </aside>

      {/* ── Main pane ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>

        {/* Search toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '10px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
        }}>
          <Input
            icon="search"
            placeholder="Search title, location, description, LB# …"
            size="lg"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1 }}
          />
          <Button variant="ghost" size="sm" iconRight="chevDown" onClick={() => setSearchField(f => f === 'all' ? 'location' : 'all')}>
            {searchField === 'all' ? 'All Fields' : searchField === 'location' ? 'Location' : 'Date'}
          </Button>
          {sep}
          <Button variant="ghost" size="sm" icon="filter" iconRight="chevDown">Group by year</Button>
          <Button variant="ghost" size="sm" iconRight="chevDown">Columns</Button>
          {sep}
          <IconButton icon="download" size={16} title="Export CSV" />
          <IconButton icon="more"     size={16} title="More options" />
        </div>

        {/* Result summary strip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
          padding: '5px 14px', borderBottom: '1px solid var(--lbb-border)',
          flexShrink: 0, minHeight: 38,
        }}>
          <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--lbb-fg)' }}>
            {filteredRows.length.toLocaleString()} results
          </span>
          <span style={{ fontSize: 12, color: 'var(--lbb-fg3)' }}>
            of {rows.length.toLocaleString()}
          </span>
          {activeFilterChips.length > 0 && (
            <>
              {sep}
              {activeFilterChips.map((f, i) => (
                <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />
              ))}
            </>
          )}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>Sort:</span>
          <Button variant="ghost" size="sm" iconRight="chevDown">LB# ↑</Button>
        </div>

        {/* Results table */}
        <div ref={tableParentRef} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 180 }} />
              <col style={{ width: 50 }} />
              <col />
              <col style={{ width: 80 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 28 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH>LB#</TH>
                <TH>Status</TH>
                <TH>Date</TH>
                <TH>Location</TH>
                <TH align="center">★</TH>
                <TH>Description</TH>
                <TH align="right">Xref</TH>
                <TH align="center">Own</TH>
                <TH />
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
                      <tr><td colSpan={10} style={{ height: padTop, padding: 0, border: 0 }} /></tr>
                    )}
                    {vItems.map(vItem => {
                      const item = flatItems[vItem.index]
                      if (!item) return null

                      if (item.kind === 'group') {
                        return (
                          <GroupRow
                            key={`g-${item.year}`}
                            label={item.year}
                            count={item.count}
                            expanded={!collapsedYears.has(item.year)}
                            onToggle={() => setCollapsedYears(prev => {
                              const next = new Set(prev)
                              if (next.has(item.year)) next.delete(item.year)
                              else next.add(item.year)
                              return next
                            })}
                            colSpan={9}
                          />
                        )
                      }

                      const r = item.row
                      return (
                        <TR key={r.lb} edge={statusTone(r.status)} style={{ height: vItem.size }}>
                          <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>
                            {r.lb}
                          </TD>
                          <TD>
                            <Pill tone={statusTone(r.status)} soft>{r.status}</Pill>
                          </TD>
                          <TD mono>{r.date}</TD>
                          <TD>{r.location}</TD>
                          <TD align="center">
                            {r.rating !== '—'
                              ? <Pill tone={ratingTone(r.rating)} soft>{r.rating}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>
                            }
                          </TD>
                          <TD dim>{r.description}</TD>
                          <TD mono dim align="right">{r.xref ?? ''}</TD>
                          <TD align="center">
                            {r.owned
                              ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)' }} />
                              : <Icon name="x"     size={13} style={{ color: 'var(--lbb-bad-fg)' }} />
                            }
                          </TD>
                          <TD align="center">
                            <Icon name="more" size={13} style={{ color: 'var(--lbb-fg3)' }} />
                          </TD>
                        </TR>
                      )
                    })}
                    {padBottom > 0 && (
                      <tr><td colSpan={10} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>
                    )}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {/* Loading state */}
          {loading && rows.length === 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 12,
            }}>
              Loading…
            </div>
          )}

          {/* Empty state */}
          {!loading && rows.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                  No results
                </div>
                <div style={{ fontSize: 11.5, marginTop: 4 }}>
                  Try adjusting your search or filters
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
