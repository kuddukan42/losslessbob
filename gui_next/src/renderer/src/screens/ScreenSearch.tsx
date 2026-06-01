import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type MasterStatus    = 'Public' | 'Private' | 'Missing'
type RatingGrade     = 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D+' | 'D' | 'D-' | 'F' | '—'
type OwnershipFilter = 'any' | 'owned' | 'not-owned'
type ToastTone       = 'ok' | 'bad' | 'info'
type SortKey         = 'lb_asc' | 'lb_desc' | 'date_asc' | 'date_desc' | 'loc_asc' | 'loc_desc'
type ColKey          = 'status' | 'date' | 'location' | 'rating' | 'description' | 'taper' | 'source' | 'xref' | 'own'

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
  taperName: string
  sourceChain: string
  xref: string | null
  owned: boolean
}

type FlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'row'; row: SearchRow }

interface FilterState {
  activeStatus: string[]
  activeRating: string[]
  activeDec: string[]
  ownership: OwnershipFilter
  yearRange: [number, number]
}

interface StoredView {
  id: string
  name: string
  state: FilterState
}

interface EntryDetail {
  entry: {
    lb_number: number
    date_str?: string
    location?: string
    description?: string
    setlist?: string
    rating?: string
    timing?: string
    cdr?: string
    status?: string
    scraped_at?: string
    taper_name?: string
    source_chain?: string
  }
  files: Array<{ filename: string; clean_name: string; downloaded: number }>
}

// ── Constants ─────────────────────────────────────────────────────────────────

const RATING_RANK: Record<string, number> = { 'A+': 13, 'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8, 'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3, 'D-': 2, 'F': 1, '—': 0 }

const SORT_OPTS: { key: SortKey; label: string }[] = [
  { key: 'lb_asc',   label: 'LB# ↑'       },
  { key: 'lb_desc',  label: 'LB# ↓'       },
  { key: 'date_asc', label: 'Date ↑'       },
  { key: 'date_desc', label: 'Date ↓'     },
  { key: 'loc_asc',  label: 'Location A–Z' },
  { key: 'loc_desc', label: 'Location Z–A' },
]

const ALL_COLS: ColKey[] = ['status', 'date', 'location', 'rating', 'description', 'taper', 'source', 'xref', 'own']
const COL_LABELS: Record<ColKey, string> = {
  status: 'Status', date: 'Date', location: 'Location',
  rating: '★ Rating', description: 'Description',
  taper: 'Taper', source: 'Source', xref: 'Xref', own: 'Owned',
}

const LS_COLS_KEY  = 'lbb_search_cols'
const LS_VIEWS_KEY = 'lbb_search_views'

const BUILT_IN_VIEWS: { id: string; name: string; state: FilterState }[] = [
  {
    id: 'public',  name: 'Public only',
    state: { activeStatus: ['Public'],   activeRating: [],       activeDec: [], ownership: 'any', yearRange: [1961, 2030] },
  },
  {
    id: 'rated',   name: 'Rated A or A-',
    state: { activeStatus: [],           activeRating: ['A+','A','A-'], activeDec: [], ownership: 'any', yearRange: [1961, 2030] },
  },
  {
    id: 'missing', name: 'Missing / wanted',
    state: { activeStatus: ['Missing'],  activeRating: [],       activeDec: [], ownership: 'any', yearRange: [1961, 2030] },
  },
]

const VALID_RATINGS = new Set(['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F'])

// ── Helpers ───────────────────────────────────────────────────────────────────

type SetlistItem =
  | { kind: 'track'; num: string; title: string }
  | { kind: 'header'; text: string }

function parseSetlist(raw: string): SetlistItem[] {
  // Normalise num: strip leading zero ("01" → "1")
  const normNum = (n: string) => String(parseInt(n, 10))

  let parts: string[]
  if (/\n/.test(raw)) {
    parts = raw.split('\n').map(l => l.trim()).filter(Boolean)
  } else if (/,\s*0?\d{1,2}[.)]\s/.test(raw)) {
    // Comma-separated dot/paren: "1. Song, 2. Song" or "01. Song, 02. Song"
    parts = raw.split(/,\s*(?=0?\d{1,2}[.)]\s)/).map(p => p.trim()).filter(Boolean)
  } else if (/,\s*\d{1,2}\s+[A-Z*"]/.test(raw)) {
    // Comma-separated num-only: "1 Song, 2 Song"
    parts = raw.split(/,\s*(?=\d{1,2}\s+[A-Z*"])/).map(p => p.trim()).filter(Boolean)
  } else if (/\s+(?=0?\d{1,2}[.)]\s)/.test(raw)) {
    // Space-separated dot/paren: "1. Song 2. Song"
    parts = raw.split(/\s+(?=0?\d{1,2}[.)]\s)/).map(p => p.trim()).filter(Boolean)
  } else {
    // Space-separated num-only: "1 Song 2 Song"
    parts = raw.split(/\s+(?=\d{1,2}\s+[A-Z*"])/).map(p => p.trim()).filter(Boolean)
  }

  return parts.map(line => {
    // Dot / paren: "1. Title" / "01. Title" / "1) Title"
    let m = line.match(/^(0?\d{1,2})[.)]\s+(.+)$/)
    if (m) return { kind: 'track' as const, num: normNum(m[1]), title: m[2] }
    // Num-only: "1 Title" (title starts with capital, *, or quote)
    m = line.match(/^(0?\d{1,2})\s+([A-Z*"].+)$/)
    if (m) return { kind: 'track' as const, num: normNum(m[1]), title: m[2] }
    return { kind: 'header' as const, text: line }
  })
}

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
  if (r === 'A+' || r === 'A' || r === 'A-') return 'ok'
  if (r === 'B+' || r === 'B' || r === 'B-') return 'info'
  if (r === 'C+' || r === 'C' || r === 'C-') return 'warn'
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
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  })
}

function loadColsFromLS(): Set<ColKey> {
  try {
    const raw = localStorage.getItem(LS_COLS_KEY)
    if (raw) {
      const arr = JSON.parse(raw) as ColKey[]
      if (Array.isArray(arr) && arr.length > 0) return new Set(arr)
    }
  } catch {}
  return new Set(ALL_COLS)
}

function loadStoredViews(): StoredView[] {
  try {
    const raw = localStorage.getItem(LS_VIEWS_KEY)
    if (raw) return JSON.parse(raw) as StoredView[]
  } catch {}
  return []
}

function exportToCsv(rows: SearchRow[]) {
  const header = 'LB#,Status,Date,Location,Rating,Taper,Source,Description\n'
  const lines = rows.map(r =>
    [r.lb, r.status, r.date, r.location, r.rating, r.taperName, r.sourceChain, r.description]
      .map(v => `"${(v ?? '').replace(/"/g, '""')}"`)
      .join(',')
  )
  const blob = new Blob([header + lines.join('\n')], { type: 'text/csv' })
  const url  = URL.createObjectURL(blob)
  const a    = Object.assign(document.createElement('a'), { href: url, download: 'losslessbob_search.csv' })
  a.click()
  URL.revokeObjectURL(url)
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ msg, tone, onDone }: { msg: string; tone: ToastTone; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])

  const bg     = tone === 'ok'  ? 'var(--lbb-ok-bg)'   : tone === 'bad' ? 'var(--lbb-err-bg)'  : 'var(--lbb-surface2)'
  const border = tone === 'ok'  ? 'var(--lbb-ok-bar)'  : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-border2)'
  const color  = tone === 'ok'  ? 'var(--lbb-ok-fg)'   : tone === 'bad' ? 'var(--lbb-err-fg)'  : 'var(--lbb-fg)'

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 999,
      background: bg, border: `1px solid ${border}`, borderRadius: 8,
      padding: '10px 16px', color, fontSize: 'var(--lbb-fs-13)', fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.15)', maxWidth: 400,
    }}>{msg}</div>
  )
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
          fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
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
      padding: '2px 8px', borderRadius: 4, fontSize: 'var(--lbb-fs-11)',
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
        <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', width: 18, flexShrink: 0 }}>From</span>
        <input
          type="range" min={min} max={max} value={low}
          onChange={e => onChange(Math.min(+e.target.value, high - 1), high)}
          style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--lbb-accent-mid)' }}
        />
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', width: 34, textAlign: 'right' }}>
          {low}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', width: 18, flexShrink: 0 }}>To</span>
        <input
          type="range" min={min} max={max} value={high}
          onChange={e => onChange(low, Math.max(+e.target.value, low + 1))}
          style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--lbb-accent-mid)' }}
        />
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', width: 34, textAlign: 'right' }}>
          {high}
        </span>
      </div>
    </div>
  )
}

// ── SaveViewDialog ────────────────────────────────────────────────────────────

function SaveViewDialog({ onSave, onCancel }: {
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 340, width: '90%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 12 }}>
          Save current filter
        </div>
        <input
          autoFocus
          type="text"
          placeholder="View name…"
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && name.trim()) onSave(name.trim()) }}
          style={{
            width: '100%', padding: '6px 10px', borderRadius: 6, fontSize: 'var(--lbb-fs-13)',
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
            color: 'var(--lbb-fg)', outline: 'none', boxSizing: 'border-box',
          }}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
          <Button variant="ghost"   size="sm" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={!name.trim()} onClick={() => onSave(name.trim())}>Save</Button>
        </div>
      </div>
    </div>
  )
}

// ── EntryDetailPanel ──────────────────────────────────────────────────────────

function EntryDetailPanel({ lbNumber, status, rating, owned, detail, loading, onClose, onToast }: {
  lbNumber: number
  status: MasterStatus
  rating: RatingGrade
  owned: boolean
  detail: EntryDetail | null
  loading: boolean
  onClose: () => void
  onToast: (msg: string, tone: ToastTone) => void
}) {
  const [descExpanded, setDescExpanded] = useState(false)
  const [slExpanded,   setSlExpanded]   = useState(false)

  useEffect(() => { setDescExpanded(false); setSlExpanded(false) }, [lbNumber])

  const lb = `LB-${String(lbNumber).padStart(5, '0')}`
  const e  = detail?.entry

  return (
    <div style={{
      borderLeft: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column',
      overflowY: 'auto', minHeight: 0,
      background: 'var(--lbb-surface)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '6px 10px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-accent-mid)' }}>
          {lb}
        </span>
        <IconButton icon="x" size={14} title="Close" onClick={onClose} />
      </div>

      {loading ? (
        <div style={{ padding: 20, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', fontFamily: 'var(--lbb-mono)' }}>
          Loading…
        </div>
      ) : (
        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Status pills */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Pill tone={statusTone(status)} soft>{status}</Pill>
            {rating !== '—' && <Pill tone={ratingTone(rating)} soft>{rating}</Pill>}
            {owned && <Pill tone="ok" soft dot>Owned</Pill>}
          </div>

          {/* Date + location */}
          {e && (
            <div>
              <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg)' }}>{e.date_str || '—'}</div>
              <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', marginTop: 2 }}>{e.location || '—'}</div>
              {e.timing && (
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 2 }}>{e.timing}</div>
              )}
            </div>
          )}

          {/* Meta grid */}
          {e && (e.taper_name || e.source_chain || e.cdr || e.scraped_at) && (
            <div style={{
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              borderRadius: 6, padding: '8px 12px',
              display: 'grid', gridTemplateColumns: '72px 1fr',
              rowGap: 6, columnGap: 8, fontSize: 'var(--lbb-fs-11-5)',
            }}>
              {e.taper_name && (
                <React.Fragment>
                  <span style={{ color: 'var(--lbb-fg3)', fontWeight: 600, alignSelf: 'center' }}>Taper</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.taper_name}</span>
                </React.Fragment>
              )}
              {e.source_chain && (
                <React.Fragment>
                  <span style={{ color: 'var(--lbb-fg3)', fontWeight: 600, alignSelf: 'center' }}>Source</span>
                  <span style={{ wordBreak: 'break-word', lineHeight: 1.4 }}>{e.source_chain}</span>
                </React.Fragment>
              )}
              {e.cdr && (
                <React.Fragment>
                  <span style={{ color: 'var(--lbb-fg3)', fontWeight: 600, alignSelf: 'center' }}>CDR</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.cdr}</span>
                </React.Fragment>
              )}
              {e.scraped_at && (
                <React.Fragment>
                  <span style={{ color: 'var(--lbb-fg3)', fontWeight: 600, alignSelf: 'center' }}>Scraped</span>
                  <span>{e.scraped_at.slice(0, 10)}</span>
                </React.Fragment>
              )}
            </div>
          )}

          {/* Description */}
          {e?.description && (
            <div>
              <div style={{
                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                color: 'var(--lbb-fg3)', marginBottom: 4,
              }}>
                Description
              </div>
              <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', lineHeight: 1.5 }}>
                {descExpanded ? e.description : e.description.slice(0, 240) + (e.description.length > 240 ? '…' : '')}
              </div>
              {e.description.length > 240 && (
                <button
                  type="button"
                  onClick={() => setDescExpanded(v => !v)}
                  style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-accent-mid)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 3, padding: 0 }}
                >
                  {descExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* Setlist — or file-name fallback when no setlist is available */}
          {(() => {
            const SL_LIMIT   = 12
            const hasSetlist = !!(e?.setlist && e.setlist.trim().length > 0)
            const files      = detail?.files ?? []

            if (!hasSetlist && files.length === 0) return null

            if (hasSetlist) {
              const items   = parseSetlist(e!.setlist!)
              const trackCt = items.filter(t => t.kind === 'track').length
              const visible = slExpanded ? items : items.slice(0, SL_LIMIT)
              const hasNums = items.some(t => t.kind === 'track' && t.num !== '')
              return (
                <div>
                  <div style={{
                    fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: 'var(--lbb-fg3)', marginBottom: 4,
                  }}>
                    Setlist{trackCt > 0 ? ` (${trackCt})` : ''}
                  </div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <tbody>
                      {visible.map((item, i) =>
                        item.kind === 'header' ? (
                          <tr key={i}>
                            <td
                              colSpan={hasNums ? 2 : 1}
                              style={{
                                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
                                padding: i === 0 ? '0 4px 2px' : '8px 4px 2px',
                                letterSpacing: '0.04em', textTransform: 'uppercase',
                              }}
                            >
                              {item.text}
                            </td>
                          </tr>
                        ) : (
                          <tr key={i} style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                            {hasNums && (
                              <td style={{
                                color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
                                padding: '3px 6px 3px 0', width: 22, textAlign: 'right',
                                fontSize: 'var(--lbb-fs-10-5)', verticalAlign: 'top', userSelect: 'none',
                              }}>
                                {item.num}
                              </td>
                            )}
                            <td style={{ padding: '3px 0 3px 4px', color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-11-5)', lineHeight: 1.4 }}>
                              {item.title}
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                  {items.length > SL_LIMIT && (
                    <button
                      type="button"
                      onClick={() => setSlExpanded(v => !v)}
                      style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-accent-mid)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 4, padding: 0 }}
                    >
                      {slExpanded ? 'Show less' : `Show ${items.length - SL_LIMIT} more…`}
                    </button>
                  )}
                </div>
              )
            }

            // Fallback: no setlist — show file names so there's always a track listing
            const visible = slExpanded ? files : files.slice(0, SL_LIMIT)
            return (
              <div>
                <div style={{
                  fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                  color: 'var(--lbb-fg3)', marginBottom: 4,
                }}>
                  Files ({files.length})
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <tbody>
                    {visible.map((f, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                        <td style={{
                          color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
                          padding: '3px 6px 3px 0', width: 22, textAlign: 'right',
                          fontSize: 'var(--lbb-fs-10-5)', verticalAlign: 'top', userSelect: 'none',
                        }}>
                          {i + 1}
                        </td>
                        <td style={{ padding: '3px 0 3px 4px', color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-11-5)', lineHeight: 1.4 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Icon
                              name={f.downloaded ? 'check' : 'x'} size={10}
                              style={{ color: f.downloaded ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)', flexShrink: 0 }}
                            />
                            <span style={{ fontFamily: 'var(--lbb-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {f.clean_name || f.filename}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {files.length > SL_LIMIT && (
                  <button
                    type="button"
                    onClick={() => setSlExpanded(v => !v)}
                    style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-accent-mid)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 4, padding: 0 }}
                  >
                    {slExpanded ? 'Show less' : `Show ${files.length - SL_LIMIT} more…`}
                  </button>
                )}
              </div>
            )
          })()}

          {/* Files — only when a setlist is also shown; suppressed when files are the fallback */}
          {detail && detail.files.length > 0 && !!(e?.setlist && e.setlist.trim().length > 0) && (
            <div>
              <div style={{
                fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                color: 'var(--lbb-fg3)', marginBottom: 4,
              }}>
                Files ({detail.files.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {detail.files.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11-5)' }}>
                    <Icon
                      name={f.downloaded ? 'check' : 'x'} size={10}
                      style={{ color: f.downloaded ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)', flexShrink: 0 }}
                    />
                    <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.clean_name || f.filename}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No metadata yet */}
          {!e && (
            <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
              No metadata. Scrape this entry to populate details.
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', borderTop: '1px solid var(--lbb-border)', paddingTop: 10 }}>
            <Button
              variant="ghost" size="sm" icon="refresh"
              onClick={() => {
                fetch(`${BASE}/api/entry/${lbNumber}/scrape`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ force: false }),
                })
                  .then(() => onToast('Scrape queued', 'info'))
                  .catch(() => onToast('Scrape failed', 'bad'))
              }}
            >
              Scrape entry
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenSearch(): React.JSX.Element {
  // ── Data ─────────────────────────────────────────────────────────────────
  const [rows, setRows]           = useState<SearchRow[]>([])
  const [loading, setLoading]     = useState(false)
  const [ownedLbs, setOwnedLbs]   = useState<Set<number>>(new Set())

  // ── Filter ───────────────────────────────────────────────────────────────
  const [search, setSearch]           = useState('')
  const [searchField, setSearchField] = useState('all')
  const [dataYearRange, setDataYearRange] = useState<[number, number]>([1961, 2030])
  const [yearRange, setYearRange]     = useState<[number, number]>([1961, 2030])
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())
  const [activeDec,    setActiveDec]    = useState<Set<string>>(new Set())
  const [activeStatus, setActiveStatus] = useState<Set<string>>(new Set())
  const [activeRating, setActiveRating] = useState<Set<string>>(new Set())
  const [ownership,    setOwnership]    = useState<OwnershipFilter>('any')
  const [bestPerDate,  setBestPerDate]  = useState(false)

  // ── UI ───────────────────────────────────────────────────────────────────
  const [sortKey,      setSortKey]      = useState<SortKey>('lb_asc')
  const [sortOpen,     setSortOpen]     = useState(false)
  const [groupByYear,  setGroupByYear]  = useState(true)
  const [visibleCols,  setVisibleCols]  = useState<Set<ColKey>>(loadColsFromLS)
  const [colsOpen,     setColsOpen]     = useState(false)
  const [storedViews,  setStoredViews]  = useState<StoredView[]>(loadStoredViews)
  const [saveViewOpen, setSaveViewOpen] = useState(false)
  const [toast,        setToast]        = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [rowMenu,      setRowMenu]      = useState<{ lb: number; x: number; y: number } | null>(null)

  // ── Detail panel ─────────────────────────────────────────────────────────
  const [selectedLb,   setSelectedLb]   = useState<number | null>(null)
  const [entryDetail,  setEntryDetail]  = useState<EntryDetail | null>(null)
  const [entryLoading, setEntryLoading] = useState(false)

  const tableParentRef = useRef<HTMLDivElement>(null)
  const sortDropRef    = useRef<HTMLDivElement>(null)
  const colsDropRef    = useRef<HTMLDivElement>(null)
  const rowMenuRef     = useRef<HTMLDivElement>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  // ── Fetch owned LB numbers ────────────────────────────────────────────────

  const refreshOwned = useCallback(() => {
    fetch(`${BASE}/api/collection/lb_numbers`)
      .then(r => r.json())
      .then((nums: number[]) => { if (Array.isArray(nums)) setOwnedLbs(new Set(nums)) })
      .catch(() => {})
  }, [])

  useEffect(() => { refreshOwned() }, [refreshOwned])

  // ── Fetch year range bounds ───────────────────────────────────────────────

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

  // ── Fetch search results (debounced 200 ms) ───────────────────────────────

  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true)
      const url = `${BASE}/api/search?q=${encodeURIComponent(search)}&field=${encodeURIComponent(searchField)}`
      fetch(url)
        .then(r => r.json())
        .then((data: any[]) => {
          if (!Array.isArray(data)) { setRows([]); return }
          setRows(data.map((d: any) => {
            const yr  = extractYear(d.date_str ?? '')
            const dec = yr > 0 ? `${Math.floor(yr / 10) * 10}s` : '?'
            const raw = d.rating ?? ''
            return {
              lb:          `LB-${String(d.lb_number).padStart(5, '0')}`,
              lbNumber:    d.lb_number as number,
              status:      ({ public: 'Public', private: 'Private', missing: 'Missing' }[
                              d.lb_status as string] ?? 'Missing') as MasterStatus,
              date:        d.date_str ?? '',
              year:        yr,
              decade:      dec,
              location:    d.location ?? '',
              rating:      (VALID_RATINGS.has(raw) ? raw : '—') as RatingGrade,
              description: d.description ?? '',
              taperName:   d.taper_name ?? '',
              sourceChain: d.source_chain ?? '',
              xref:        null,
              owned:       false,  // set in ownedRows memo
            }
          }))
        })
        .catch(() => setRows([]))
        .finally(() => setLoading(false))
    }, 200)
    return () => clearTimeout(timer)
  }, [search, searchField])

  // ── Fetch entry detail when selection changes ─────────────────────────────

  useEffect(() => {
    if (selectedLb === null) { setEntryDetail(null); return }
    setEntryLoading(true)
    fetch(`${BASE}/api/entry/${selectedLb}`)
      .then(r => r.json())
      .then((data: EntryDetail) => setEntryDetail(data))
      .catch(() => setEntryDetail(null))
      .finally(() => setEntryLoading(false))
  }, [selectedLb])

  // ── Persist visible cols to localStorage ─────────────────────────────────

  useEffect(() => {
    try { localStorage.setItem(LS_COLS_KEY, JSON.stringify([...visibleCols])) } catch {}
  }, [visibleCols])

  // ── Close popovers on outside click ──────────────────────────────────────

  useEffect(() => {
    if (!sortOpen) return
    const h = (e: MouseEvent) => { if (!sortDropRef.current?.contains(e.target as Node)) setSortOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [sortOpen])

  useEffect(() => {
    if (!colsOpen) return
    const h = (e: MouseEvent) => { if (!colsDropRef.current?.contains(e.target as Node)) setColsOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [colsOpen])

  useEffect(() => {
    if (!rowMenu) return
    const h = (e: MouseEvent) => { if (!rowMenuRef.current?.contains(e.target as Node)) setRowMenu(null) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [rowMenu])

  // ── Derived: rows with correct owned field ────────────────────────────────

  const ownedRows = useMemo(() =>
    rows.map(r => ({ ...r, owned: ownedLbs.has(r.lbNumber) })),
    [rows, ownedLbs]
  )

  // ── Facet counts (from all unfiltered results) ────────────────────────────

  const facetCounts = useMemo(() => {
    const statusC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    const decadeC: Record<string, number> = {}
    for (const r of ownedRows) {
      statusC[r.status] = (statusC[r.status] ?? 0) + 1
      ratingC[r.rating] = (ratingC[r.rating] ?? 0) + 1
      decadeC[r.decade] = (decadeC[r.decade] ?? 0) + 1
    }
    return { statusC, ratingC, decadeC }
  }, [ownedRows])

  // ── Filtering ────────────────────────────────────────────────────────────

  const filteredRows = useMemo(() =>
    ownedRows.filter(r => {
      if (activeStatus.size > 0 && !activeStatus.has(r.status)) return false
      if (activeRating.size > 0 && !activeRating.has(r.rating)) return false
      if (activeDec.size > 0    && !activeDec.has(r.decade))    return false
      if (ownership === 'owned'     && !r.owned) return false
      if (ownership === 'not-owned' &&  r.owned) return false
      if (r.year > 0 && (r.year < yearRange[0] || r.year > yearRange[1])) return false
      return true
    }),
    [ownedRows, activeStatus, activeRating, activeDec, ownership, yearRange]
  )

  // ── Best-per-date filter ─────────────────────────────────────────────────

  const bestPerDateRows = useMemo(() => {
    if (!bestPerDate) return filteredRows
    // For each unique non-empty date keep only the entry/entries with the max rating.
    // Undated entries (empty string) are always included as-is.
    const byDate = new Map<string, SearchRow[]>()
    const undated: SearchRow[] = []
    for (const r of filteredRows) {
      if (!r.date) { undated.push(r); continue }
      const bucket = byDate.get(r.date)
      if (bucket) bucket.push(r)
      else byDate.set(r.date, [r])
    }
    const result: SearchRow[] = [...undated]
    for (const bucket of byDate.values()) {
      const maxRank = Math.max(...bucket.map(r => RATING_RANK[r.rating] ?? 0))
      for (const r of bucket) {
        if ((RATING_RANK[r.rating] ?? 0) === maxRank) result.push(r)
      }
    }
    return result
  }, [filteredRows, bestPerDate])

  // ── Sorting ──────────────────────────────────────────────────────────────

  const sortedRows = useMemo(() => {
    const arr = [...bestPerDateRows]
    switch (sortKey) {
      case 'lb_asc':    return arr.sort((a, b) => a.lbNumber - b.lbNumber)
      case 'lb_desc':   return arr.sort((a, b) => b.lbNumber - a.lbNumber)
      case 'date_asc':  return arr.sort((a, b) => a.date.localeCompare(b.date))
      case 'date_desc': return arr.sort((a, b) => b.date.localeCompare(a.date))
      case 'loc_asc':   return arr.sort((a, b) => a.location.localeCompare(b.location))
      case 'loc_desc':  return arr.sort((a, b) => b.location.localeCompare(a.location))
      default:          return arr
    }
  }, [bestPerDateRows, sortKey])

  // ── Grouping ─────────────────────────────────────────────────────────────

  const groupedByYear = useMemo(() => {
    if (!groupByYear) return null
    const map = new Map<string, SearchRow[]>()
    for (const r of sortedRows) {
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
  }, [sortedRows, groupByYear])

  // ── Flat list for virtualizer ─────────────────────────────────────────────

  const flatItems = useMemo((): FlatItem[] => {
    if (!groupByYear || !groupedByYear)
      return sortedRows.map(row => ({ kind: 'row', row }) as FlatItem)
    const items: FlatItem[] = []
    for (const [year, yearRows] of groupedByYear) {
      items.push({ kind: 'group', year, count: yearRows.length })
      if (!collapsedYears.has(year))
        for (const row of yearRows) items.push({ kind: 'row', row })
    }
    return items
  }, [groupedByYear, groupByYear, sortedRows, collapsedYears])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: (i) => flatItems[i]?.kind === 'group' ? 32 : 34,
    overscan: 12,
  })

  // ── Column helpers ────────────────────────────────────────────────────────

  const toggleCol = (col: ColKey) =>
    setVisibleCols(prev => { const n = new Set(prev); n.has(col) ? n.delete(col) : n.add(col); return n })

  // edge(1) + LB#(1) + visible cols + more-btn(1)
  const colCount  = 3 + visibleCols.size
  const sortLabel = SORT_OPTS.find(o => o.key === sortKey)?.label ?? 'LB# ↑'

  // ── Filter helpers ────────────────────────────────────────────────────────

  const clearAll = () => {
    setActiveDec(new Set()); setActiveStatus(new Set()); setActiveRating(new Set())
    setOwnership('any'); setYearRange(dataYearRange); setBestPerDate(false)
  }

  const hasActiveFilters = activeDec.size > 0 || activeStatus.size > 0 || activeRating.size > 0 || ownership !== 'any' || bestPerDate

  const filterChips: Array<{ label: string; onRemove: () => void }> = [
    ...[...activeStatus].map(s => ({ label: `Status: ${s}`, onRemove: () => toggleSet(setActiveStatus, s) })),
    ...[...activeRating].map(r => ({ label: `Rating: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
    ...[...activeDec   ].map(d => ({ label: `Decade: ${d}`, onRemove: () => toggleSet(setActiveDec, d) })),
    ...(ownership !== 'any'
      ? [{ label: ownership === 'owned' ? 'Owned' : 'Not owned', onRemove: () => setOwnership('any') }]
      : []),
    ...(bestPerDate ? [{ label: 'Best per date', onRemove: () => setBestPerDate(false) }] : []),
  ]

  // ── Saved views ───────────────────────────────────────────────────────────

  const applyView = (state: FilterState) => {
    setActiveStatus(new Set(state.activeStatus))
    setActiveRating(new Set(state.activeRating))
    setActiveDec(new Set(state.activeDec))
    setOwnership(state.ownership)
    setYearRange(
      state.yearRange[0] === 1961 && state.yearRange[1] === 2030
        ? dataYearRange
        : state.yearRange
    )
  }

  const saveView = (name: string) => {
    const view: StoredView = {
      id: Date.now().toString(),
      name,
      state: { activeStatus: [...activeStatus], activeRating: [...activeRating], activeDec: [...activeDec], ownership, yearRange },
    }
    const updated = [...storedViews, view]
    setStoredViews(updated)
    try { localStorage.setItem(LS_VIEWS_KEY, JSON.stringify(updated)) } catch {}
    setSaveViewOpen(false)
    showToast(`Saved view "${name}"`, 'ok')
  }

  const deleteView = (id: string) => {
    const updated = storedViews.filter(v => v.id !== id)
    setStoredViews(updated)
    try { localStorage.setItem(LS_VIEWS_KEY, JSON.stringify(updated)) } catch {}
  }

  // ── Selected row ──────────────────────────────────────────────────────────

  const selectedRow = selectedLb !== null
    ? (ownedRows.find(r => r.lbNumber === selectedLb) ?? null)
    : null

  // ── Facet items ───────────────────────────────────────────────────────────

  const decadeItems = ['1960s','1970s','1980s','1990s','2000s','2010s','2020s'].map(d => ({ label: d, count: facetCounts.decadeC[d] }))
  const statusItems = (['Public','Private','Missing'] as MasterStatus[]).map(s  => ({ label: s, count: facetCounts.statusC[s] }))
  const ratingItems = (['A+','A','A-','B+','B','B-','C+','C','C-','D+','D','D-','F'] as RatingGrade[]).map(r => ({ label: r, count: facetCounts.ratingC[r] }))

  const sep = <span style={{ width: 1, height: 16, background: 'var(--lbb-border)', margin: '0 4px', flexShrink: 0 }} />

  // ── Render ────────────────────────────────────────────────────────────────

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
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--lbb-fg3)', padding: '10px 12px 6px',
          }}>
            Saved views
          </div>
          {BUILT_IN_VIEWS.map(v => (
            <div
              key={v.id}
              onClick={() => applyView(v.state)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                padding: '5px 12px', cursor: 'pointer', fontSize: 'var(--lbb-fs-12)',
                color: 'var(--lbb-fg2)',
              }}
            >
              <Icon name="star" size={12} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
              <span>{v.name}</span>
            </div>
          ))}
          {storedViews.map(v => (
            <div
              key={v.id}
              onClick={() => applyView(v.state)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                padding: '5px 12px', cursor: 'pointer', fontSize: 'var(--lbb-fs-12)',
                color: 'var(--lbb-fg2)',
              }}
            >
              <Icon name="starFill" size={12} style={{ color: 'var(--lbb-accent-mid)', flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{v.name}</span>
              <button
                type="button"
                onClick={e => { e.stopPropagation(); deleteView(v.id) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--lbb-fg3)', padding: 0, display: 'flex' }}
              >
                <Icon name="x" size={10} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setSaveViewOpen(true)}
            style={{
              width: '100%', textAlign: 'left', display: 'block',
              padding: '6px 12px', fontSize: 'var(--lbb-fs-11-5)', marginTop: 4,
              background: 'none', cursor: 'pointer', color: 'var(--lbb-fg3)',
              border: 'none', borderTop: '1px dashed var(--lbb-border2)',
            }}
          >
            + Save current filter as view
          </button>
        </div>

        {/* Facet groups */}
        <FacetGroup title="Decade" items={decadeItems} active={activeDec} onToggle={v => toggleSet(setActiveDec, v)} />
        <FacetGroup title="Status" items={statusItems} active={activeStatus} onToggle={v => toggleSet(setActiveStatus, v)} />
        <FacetGroup title="Rating" items={ratingItems} active={activeRating} onToggle={v => toggleSet(setActiveRating, v)} />

        {/* Ownership segmented control */}
        <div style={{ borderBottom: '1px solid var(--lbb-border)', padding: '8px 12px' }}>
          <div style={{
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--lbb-fg3)', marginBottom: 8,
          }}>
            Ownership
          </div>
          <div style={{ display: 'flex', border: '1px solid var(--lbb-border2)', borderRadius: 6, overflow: 'hidden' }}>
            {(['any', 'owned', 'not-owned'] as OwnershipFilter[]).map((opt, i) => (
              <button
                key={opt} type="button" onClick={() => setOwnership(opt)}
                style={{
                  flex: 1, padding: '4px 0', fontSize: 'var(--lbb-fs-11)', cursor: 'pointer',
                  background: ownership === opt ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                  color: ownership === opt ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                  fontWeight: ownership === opt ? 600 : 400,
                  border: 'none', borderLeft: i > 0 ? '1px solid var(--lbb-border2)' : 'none',
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
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
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

        {/* Best per date */}
        <div style={{ borderBottom: '1px solid var(--lbb-border)', padding: '8px 12px' }}>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8,
            cursor: 'pointer', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)',
          }}>
            <input
              type="checkbox"
              checked={bestPerDate}
              onChange={e => setBestPerDate(e.target.checked)}
              style={{ accentColor: 'var(--lbb-accent-mid)', flexShrink: 0 }}
            />
            <span>Best per date</span>
          </label>
          <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 4, paddingLeft: 20 }}>
            Show only the highest-rated entry for each concert date
          </div>
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
      <div style={{
        flex: 1, display: 'grid', minHeight: 0, minWidth: 0,
        gridTemplateColumns: selectedLb !== null ? '1fr 340px' : '1fr',
      }}>

        {/* Table area */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>

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
            <Button
              variant="ghost" size="sm" iconRight="chevDown"
              onClick={() => setSearchField(f => f === 'all' ? 'location' : f === 'location' ? 'date' : 'all')}
            >
              {searchField === 'all' ? 'All Fields' : searchField === 'location' ? 'Location' : 'Date'}
            </Button>
            {sep}

            {/* Group by year toggle */}
            <Button
              variant="ghost" size="sm" icon="filter" iconRight="chevDown"
              style={groupByYear ? { background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)' } : undefined}
              onClick={() => setGroupByYear(g => !g)}
            >
              Group by year
            </Button>

            {/* Columns popover */}
            <div ref={colsDropRef} style={{ position: 'relative' }}>
              <Button variant="ghost" size="sm" iconRight="chevDown" onClick={() => { setColsOpen(o => !o); setSortOpen(false) }}>
                Columns
              </Button>
              {colsOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 4px)', right: 0, zIndex: 200,
                  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                  borderRadius: 8, padding: '8px 0', minWidth: 160,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                }}>
                  {ALL_COLS.map(col => (
                    <label key={col} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '5px 14px', cursor: 'pointer', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)',
                    }}>
                      <input
                        type="checkbox"
                        checked={visibleCols.has(col)}
                        onChange={() => toggleCol(col)}
                        style={{ accentColor: 'var(--lbb-accent-mid)' }}
                      />
                      {COL_LABELS[col]}
                    </label>
                  ))}
                </div>
              )}
            </div>

            {sep}
            <IconButton icon="download" size={16} title="Export CSV" onClick={() => exportToCsv(sortedRows)} />
            <IconButton
              icon="more" size={16} title="More options"
              onClick={() => showToast('Additional options coming in a future update', 'info')}
            />
          </div>

          {/* Result summary strip */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
            padding: '5px 14px', borderBottom: '1px solid var(--lbb-border)',
            flexShrink: 0, minHeight: 38,
          }}>
            <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)' }}>
              {sortedRows.length.toLocaleString()} results
            </span>
            <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
              of {rows.length.toLocaleString()}
            </span>
            {filterChips.length > 0 && (
              <>
                {sep}
                {filterChips.map((f, i) => <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />)}
              </>
            )}
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>Sort:</span>

            {/* Sort popover */}
            <div ref={sortDropRef} style={{ position: 'relative' }}>
              <Button variant="ghost" size="sm" iconRight="chevDown" onClick={() => { setSortOpen(o => !o); setColsOpen(false) }}>
                {sortLabel}
              </Button>
              {sortOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 4px)', right: 0, zIndex: 200,
                  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                  borderRadius: 8, padding: '4px 0', minWidth: 160,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                }}>
                  {SORT_OPTS.map(opt => (
                    <button
                      key={opt.key} type="button"
                      onClick={() => { setSortKey(opt.key); setSortOpen(false) }}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left',
                        padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 'var(--lbb-fs-12)',
                        background: sortKey === opt.key ? 'var(--lbb-accent-soft)' : 'none',
                        color: sortKey === opt.key ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                        fontWeight: sortKey === opt.key ? 600 : 400,
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Results table */}
          <div ref={tableParentRef} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            <TableShell stickyHeader>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 100 }} />
                {visibleCols.has('status')      && <col style={{ width: 80  }} />}
                {visibleCols.has('date')        && <col style={{ width: 90  }} />}
                {visibleCols.has('location')    && <col style={{ width: 180 }} />}
                {visibleCols.has('rating')      && <col style={{ width: 50  }} />}
                {visibleCols.has('description') && <col />}
                {visibleCols.has('taper')       && <col style={{ width: 140 }} />}
                {visibleCols.has('source')      && <col style={{ width: 200 }} />}
                {visibleCols.has('xref')        && <col style={{ width: 80  }} />}
                {visibleCols.has('own')         && <col style={{ width: 36  }} />}
                <col style={{ width: 28 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH /><TH>LB#</TH>
                  {visibleCols.has('status')      && <TH>Status</TH>}
                  {visibleCols.has('date')        && <TH>Date</TH>}
                  {visibleCols.has('location')    && <TH>Location</TH>}
                  {visibleCols.has('rating')      && <TH align="center">★</TH>}
                  {visibleCols.has('description') && <TH>Description</TH>}
                  {visibleCols.has('taper')       && <TH>Taper</TH>}
                  {visibleCols.has('source')      && <TH>Source</TH>}
                  {visibleCols.has('xref')        && <TH align="right">Xref</TH>}
                  {visibleCols.has('own')         && <TH align="center">Own</TH>}
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
                        <tr><td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} /></tr>
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
                                const n = new Set(prev)
                                n.has(item.year) ? n.delete(item.year) : n.add(item.year)
                                return n
                              })}
                              colSpan={colCount - 1}
                            />
                          )
                        }

                        const r = item.row
                        return (
                          <TR
                            key={r.lb}
                            edge={statusTone(r.status)}
                            selected={r.lbNumber === selectedLb}
                            onClick={() => setSelectedLb(prev => prev === r.lbNumber ? null : r.lbNumber)}
                            style={{ height: vItem.size }}
                          >
                            <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>
                              {r.lb}
                            </TD>
                            {visibleCols.has('status') && (
                              <TD><Pill tone={statusTone(r.status)} soft>{r.status}</Pill></TD>
                            )}
                            {visibleCols.has('date') && <TD mono>{r.date}</TD>}
                            {visibleCols.has('location') && <TD>{r.location}</TD>}
                            {visibleCols.has('rating') && (
                              <TD align="center">
                                {r.rating !== '—'
                                  ? <Pill tone={ratingTone(r.rating)} soft>{r.rating}</Pill>
                                  : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                              </TD>
                            )}
                            {visibleCols.has('description') && <TD dim>{r.description}</TD>}
                            {visibleCols.has('taper')       && <TD dim>{r.taperName}</TD>}
                            {visibleCols.has('source')      && <TD dim>{r.sourceChain}</TD>}
                            {visibleCols.has('xref')        && <TD mono dim align="right">{r.xref ?? ''}</TD>}
                            {visibleCols.has('own') && (
                              <TD align="center">
                                {r.owned
                                  ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)' }} />
                                  : <Icon name="x"     size={13} style={{ color: 'var(--lbb-bad-fg)' }} />}
                              </TD>
                            )}
                            <TD
                              align="center"
                              onClick={e => {
                                e.stopPropagation()
                                const rect = e.currentTarget.getBoundingClientRect()
                                setRowMenu(prev =>
                                  prev?.lb === r.lbNumber ? null : { lb: r.lbNumber, x: rect.left - 140, y: rect.bottom + 2 }
                                )
                              }}
                            >
                              <Icon name="more" size={13} style={{ color: 'var(--lbb-fg3)' }} />
                            </TD>
                          </TR>
                        )
                      })}
                      {padBottom > 0 && (
                        <tr><td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>
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
                height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
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
                  <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>No results</div>
                  <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>Try adjusting your search or filters</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Detail panel */}
        {selectedLb !== null && (
          <EntryDetailPanel
            lbNumber={selectedLb}
            status={selectedRow?.status ?? 'Missing'}
            rating={selectedRow?.rating ?? '—'}
            owned={selectedRow?.owned ?? false}
            detail={entryDetail}
            loading={entryLoading}
            onClose={() => setSelectedLb(null)}
            onToast={showToast}
          />
        )}
      </div>

      {/* ── Overlays ────────────────────────────────────────────────────── */}
      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}

      {saveViewOpen && (
        <SaveViewDialog onSave={saveView} onCancel={() => setSaveViewOpen(false)} />
      )}

      {rowMenu && (
        <div
          ref={rowMenuRef}
          style={{
            position: 'fixed', left: rowMenu.x, top: rowMenu.y, zIndex: 300,
            background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
            borderRadius: 8, padding: '4px 0', minWidth: 150,
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
          }}
        >
          <button
            type="button"
            onClick={() => {
              const lb = rowMenu.lb
              setRowMenu(null)
              fetch(`${BASE}/api/entry/${lb}/scrape`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: false }),
              })
                .then(() => showToast(`LB-${String(lb).padStart(5, '0')} queued for scrape`, 'info'))
                .catch(() => showToast('Scrape failed', 'bad'))
            }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 'var(--lbb-fs-12)',
              background: 'none', color: 'var(--lbb-fg2)',
            }}
          >
            Scrape entry
          </button>
        </div>
      )}
    </div>
  )
}
