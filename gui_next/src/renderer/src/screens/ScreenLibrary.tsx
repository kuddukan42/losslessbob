import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { create } from 'zustand'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Button, IconButton, Input, Pill, Toast, ConfirmDialog } from '../components'
import type { ToastTone } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import {
  buildRecordingActions, buildPerformanceActions, ActionMenu, useActionMenu, BulkActionBar,
} from '../components/library/actions'
import type { ActionRow, ActionHandlers, LibAction } from '../components/library/actions'
import { RecordingDetailPanel, PerformanceDetailPanel } from '../components/library/DetailPanel'
import type { RowHistory } from '../components/library/DetailPanel'
import { useAttachmentsStore } from '../lib/attachmentsStore'
import { useSpectrogramStore } from '../lib/spectrogramStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'
import { lbDetailUrl } from '../lib/lbUrl'
import { useResizableColumns } from '../lib/useResizableColumns'

// ── TODO-150 step (4): Recording lens / no-families fallback ──────────────────
// Flat, LB#-keyed table over the full catalog. Per the design contract
// (instructions/design_handoff_unified_library/03-data-contract.md) this row
// shape is also the "no-families fallback" the performance lens (step 6) will
// reuse to render recordings under a show when no TapeMatch family data
// exists.
//
// TODO-150 step (7): the shared action registry (components/library/actions.tsx)
// is wired in here — right-click context menu on both lenses, plus a
// checkbox bulk-select bar on the recording lens with batched relocate/
// remove. The detail-panel ActionBar/MoreMenu surface is step 8.

const BASE = window.api.flaskBase

function blobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Types ─────────────────────────────────────────────────────────────────────

type LibStatus  = 'Public' | 'Private' | 'Missing'
type RatingGrade = 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D+' | 'D' | 'D-' | 'F' | '—'
type Scope       = 'all' | 'owned' | 'unowned'
type SortKey     = 'lb' | 'date' | 'rating'
type SortDir     = 'asc' | 'desc'
type HealthFlag  = 'Wishlist' | 'Duplicates' | 'Unconfirmed'

interface RecordingRow {
  lb: string
  lbNumber: number
  year: number
  decade: string
  date: string
  loc: string
  desc: string
  rating: RatingGrade
  src: string | null
  taper: string
  status: LibStatus
  owned: boolean
  wish: boolean
  dup: boolean
  xref: boolean
  unconf: boolean
  folder: string
  path: string
  conf: string
  // TapeMatch family fields (performance lens only — merged in from
  // /api/tapematch/families, never set by the recording lens's adapter).
  fam?: string
  famLabel?: string
  famConf?: number | null
  famBy?: 'lb' | 'ai' | 'ai+lb'
  famNeedsReview?: boolean
  famReviewReason?: string | null
}

type FlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'row'; row: RecordingRow }

const VALID_RATINGS = new Set(['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F'])

const SRC_ABBR: Record<string, string> = {
  Soundboard: 'SBD', Audience: 'AUD', 'FM/Pre-FM': 'FM', Master: 'MST', Mixed: 'MTX', ALD: 'ALD',
}

const SOURCE_FULL: Record<string, string> = {
  Soundboard: 'Soundboard', Audience: 'Audience', 'FM/Pre-FM': 'FM / Pre-FM',
  Master: 'Master / Studio', Mixed: 'Matrix / Mixed', ALD: 'Assisted Listening Device',
}

// Generic source-type words that occasionally end up in taper_name via the
// free-text parser (backend/db.py) — not real taper handles, so the badge
// omits them rather than duplicating the Source column.
const NON_TAPER_LABELS = new Set([
  'master', 'sbd', 'bootleg', 'soundboard', 'audience', 'ald', 'mixed', 'incomplete', 'unknown', 'n/a',
])

function taperBadgeLabel(taper: string): string | null {
  const v = taper.trim()
  if (!v || NON_TAPER_LABELS.has(v.toLowerCase())) return null
  return v
}

const RATING_RANK: Record<string, number> = {
  'A+': 13, A: 12, 'A-': 11, 'B+': 10, B: 9, 'B-': 8, 'C+': 7, C: 6, 'C-': 5, 'D+': 4, D: 3, 'D-': 2, F: 1, '—': 0,
}

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

function decadeOf(year: number): string {
  if (!year) return 'Unknown'
  return `${Math.floor((year % 100) / 10) * 10}s`
}

function statusTone(s: LibStatus): 'ok' | 'warn' | 'mute' {
  if (s === 'Public')  return 'ok'
  if (s === 'Missing') return 'warn'
  return 'mute'
}

// i18n key maps (literal keys so the typed t() resolves them, vs. template strings).
const STATUS_LABEL_KEY = {
  Public: 'library.statusValue.public', Private: 'library.statusValue.private', Missing: 'library.statusValue.missing',
} as const
const VIEW_LABEL_KEY: Record<string, 'library.views.allPerformances' | 'library.views.myCollection' | 'library.views.coverageGaps' | 'library.views.wishlist' | 'library.views.duplicates'> = {
  all: 'library.views.allPerformances', owned: 'library.views.myCollection', gaps: 'library.views.coverageGaps',
  wishlist: 'library.views.wishlist', duplicates: 'library.views.duplicates',
}
const COVERAGE_LABEL_KEY: Record<string, 'library.coverageValue.covered' | 'library.coverageValue.upgrade' | 'library.coverageValue.gap' | 'library.coverageValue.undocumented'> = {
  Covered: 'library.coverageValue.covered', Upgrade: 'library.coverageValue.upgrade',
  Gap: 'library.coverageValue.gap', Undocumented: 'library.coverageValue.undocumented',
}

function ratingTone(r: RatingGrade): 'ok' | 'info' | 'warn' | 'mute' {
  if (r === 'A+' || r === 'A' || r === 'A-') return 'ok'
  if (r === 'B+' || r === 'B' || r === 'B-') return 'info'
  if (r === 'C+' || r === 'C' || r === 'C-') return 'warn'
  return 'mute'
}

// TODO-150 step 7: shared shape the action registry (components/library/actions.tsx) needs.
function toRecAction(r: RecordingRow): ActionRow {
  return { lbNumber: r.lbNumber, lb: r.lb, owned: r.owned, wish: r.wish, path: r.path }
}

function toggleSet<T>(setFn: React.Dispatch<React.SetStateAction<Set<T>>>, val: T) {
  setFn(prev => {
    const next = new Set(prev)
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  })
}

const HEALTH_CHECK: Record<HealthFlag, (r: RecordingRow) => boolean> = {
  Wishlist:     r => r.wish,
  Duplicates:   r => r.dup,
  Unconfirmed:  r => r.owned && r.unconf,
}

// ── FilterMenu — dropdown button + popover ────────────────────────────────────

function FilterMenu({ label, count = 0, children, width = 256, align = 'left' }: {
  label: string
  count?: number
  children: React.ReactNode | ((close: () => void) => React.ReactNode)
  width?: number
  align?: 'left' | 'right'
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onEsc)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onEsc) }
  }, [open])
  const lit = count > 0 || open
  return (
    <div ref={ref} style={{ position: 'relative', flex: '0 0 auto' }}>
      <button type="button" onClick={() => setOpen(o => !o)} style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        height: 28, padding: '0 8px 0 10px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
        fontSize: 'var(--t-body)', fontWeight: count > 0 ? 'var(--w-semi)' : 'var(--w-med)', whiteSpace: 'nowrap',
        background: count > 0 ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
        color: count > 0 ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
        border: `1px solid ${lit ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
      }}>
        {label}
        {count > 0 && (
          <span style={{
            minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8,
            background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
            fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}>{count}</span>
        )}
        <Icon name={open ? 'chevUp' : 'chevDown'} size={12} style={{ opacity: 0.55 }} />
      </button>
      {open && (
        <div onClick={e => e.stopPropagation()} style={{
          position: 'absolute', top: 'calc(100% + 6px)', [align]: 0, width, zIndex: 80,
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
          borderRadius: 10, boxShadow: 'var(--lbb-shadowLg)', padding: 12,
          maxHeight: 420, overflowY: 'auto',
        }}>
          {typeof children === 'function' ? children(() => setOpen(false)) : children}
        </div>
      )}
    </div>
  )
}

function MenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8, fontSize: 'var(--t-label)', fontWeight: 'var(--w-bold)', letterSpacing: 'var(--track-eyebrow)', textTransform: 'uppercase', color: 'var(--lbb-fg3)' }}>
      {children}
    </div>
  )
}

// ── FacetOption / FacetList — single-column row filter list (matches Year menu) ─

function FacetOption({ label, count, active, onClick }: {
  label: React.ReactNode
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      width: '100%', textAlign: 'left', fontFamily: 'inherit',
      padding: '5px 8px', fontSize: 'var(--t-body)', cursor: 'pointer', border: 'none',
      background: active ? 'var(--lbb-accent-soft)' : 'transparent',
      color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
      borderRadius: 6,
    }}>
      <span>{label}</span>
      {count !== undefined && (
        <span style={{ fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg3)', fontWeight: 'var(--w-med)' }}>{count.toLocaleString()}</span>
      )}
    </button>
  )
}

function FacetList({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</div>
}

// ── ViewToggle — segmented lens switcher ──────────────────────────────────────

function ViewToggle({ value, onChange }: {
  value: 'performance' | 'recording'
  onChange: (v: 'performance' | 'recording') => void
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      display: 'flex', padding: 2, borderRadius: 8, flex: '0 0 auto',
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
    }}>
      {(['performance', 'recording'] as const).map(l => {
        const active = value === l
        return (
          <button key={l} type="button" onClick={() => onChange(l)} style={{
            display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 12px', borderRadius: 6,
            background: active ? 'var(--lbb-surface)' : 'transparent',
            color: active ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
            border: active ? '1px solid var(--lbb-border2)' : '1px solid transparent',
            boxShadow: active ? 'var(--lbb-shadow)' : 'none',
            fontSize: 'var(--t-body)', fontWeight: active ? 'var(--w-semi)' : 'var(--w-med)', cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}>
            {l === 'performance' ? t('library.lens.byPerformance') : t('library.lens.byRecording')}
          </button>
        )
      })}
    </div>
  )
}

// ── ScopeControl — segmented ownership scope ──────────────────────────────────

function ScopeControl({ value, onChange, allCount, ownedCount }: {
  value: Scope; onChange: (v: Scope) => void; allCount: number; ownedCount: number
}) {
  const { t } = useTranslation()
  const opts: [Scope, string, number][] = [
    ['all', t('library.scope.everything'), allCount],
    ['owned', t('library.scope.myCollection'), ownedCount],
    ['unowned', t('library.scope.notOwned'), allCount - ownedCount],
  ]
  return (
    <div style={{
      display: 'flex', padding: 2, borderRadius: 8, flex: '0 0 auto',
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
    }}>
      {opts.map(([opt, lbl, n]) => {
        const active = value === opt
        return (
          <button key={opt} type="button" onClick={() => onChange(opt)} style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 12px', borderRadius: 6,
            background: active ? 'var(--lbb-surface)' : 'transparent',
            color: active ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
            border: active ? '1px solid var(--lbb-border2)' : '1px solid transparent',
            boxShadow: active ? 'var(--lbb-shadow)' : 'none',
            fontSize: 'var(--t-body)', fontWeight: active ? 'var(--w-semi)' : 'var(--w-med)', cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}>
            {lbl}
            <span style={{ fontSize: 'var(--t-mono-sm)', fontVariantNumeric: 'tabular-nums', color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: 'var(--w-semi)' }}>
              {n.toLocaleString()}
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ── ActiveFilter chip (summary strip) ──────────────────────────────────────────

function ActiveFilter({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 4px 2px 8px', borderRadius: 4,
      background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)',
      fontSize: 'var(--t-meta)', fontWeight: 'var(--w-semi)', whiteSpace: 'nowrap',
    }}>
      {label}
      <button type="button" onClick={onRemove} style={{
        width: 16, height: 16, borderRadius: 3, padding: 0,
        background: 'transparent', border: 'none', color: 'currentColor',
        cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon name="x" size={10} />
      </button>
    </span>
  )
}

// ── BUG-219: search/filter state, kept alive across navigation ───────────────
// react-router unmounts ScreenLibrary on route change, so plain useState for
// the recording-lens (this screen) and performance-lens (PerformanceLensView)
// filters reset to defaults every time the user navigates away and back. A
// module-scope zustand store (no persist middleware — survives route changes
// within a session, not app restarts, matching the other ephemeral UI stores
// in lib/*Store.ts) keeps it alive. Setters mirror React's SetStateAction
// signature so existing toggleSet()/setX(new Set()) call sites need no change.
function withUpdater<T>(current: T, updater: React.SetStateAction<T>): T {
  return typeof updater === 'function' ? (updater as (prev: T) => T)(current) : updater
}

interface LibraryFilterStore {
  recScope: Scope
  setRecScope: React.Dispatch<React.SetStateAction<Scope>>
  recQuery: string
  setRecQuery: React.Dispatch<React.SetStateAction<string>>
  recActiveDecade: Set<string>
  setRecActiveDecade: React.Dispatch<React.SetStateAction<Set<string>>>
  recActiveStatus: Set<LibStatus>
  setRecActiveStatus: React.Dispatch<React.SetStateAction<Set<LibStatus>>>
  recActiveRating: Set<RatingGrade>
  setRecActiveRating: React.Dispatch<React.SetStateAction<Set<RatingGrade>>>
  recActiveSource: Set<string>
  setRecActiveSource: React.Dispatch<React.SetStateAction<Set<string>>>
  recActiveHealth: Set<HealthFlag>
  setRecActiveHealth: React.Dispatch<React.SetStateAction<Set<HealthFlag>>>

  perfQuery: string
  setPerfQuery: React.Dispatch<React.SetStateAction<string>>
  perfActiveDecade: Set<string>
  setPerfActiveDecade: React.Dispatch<React.SetStateAction<Set<string>>>
  perfActiveYear: Set<number>
  setPerfActiveYear: React.Dispatch<React.SetStateAction<Set<number>>>
  perfActiveCoverage: Set<Coverage>
  setPerfActiveCoverage: React.Dispatch<React.SetStateAction<Set<Coverage>>>
  perfActiveSource: Set<string>
  setPerfActiveSource: React.Dispatch<React.SetStateAction<Set<string>>>
  perfActiveRating: Set<RatingGrade>
  setPerfActiveRating: React.Dispatch<React.SetStateAction<Set<RatingGrade>>>
  perfView: 'all' | 'owned' | 'gaps' | 'wishlist' | 'duplicates'
  setPerfView: React.Dispatch<React.SetStateAction<'all' | 'owned' | 'gaps' | 'wishlist' | 'duplicates'>>
}

const useLibraryFilterStore = create<LibraryFilterStore>((set, get) => ({
  recScope: 'all',
  setRecScope: (u) => set({ recScope: withUpdater(get().recScope, u) }),
  recQuery: '',
  setRecQuery: (u) => set({ recQuery: withUpdater(get().recQuery, u) }),
  recActiveDecade: new Set(),
  setRecActiveDecade: (u) => set({ recActiveDecade: withUpdater(get().recActiveDecade, u) }),
  recActiveStatus: new Set(),
  setRecActiveStatus: (u) => set({ recActiveStatus: withUpdater(get().recActiveStatus, u) }),
  recActiveRating: new Set(),
  setRecActiveRating: (u) => set({ recActiveRating: withUpdater(get().recActiveRating, u) }),
  recActiveSource: new Set(),
  setRecActiveSource: (u) => set({ recActiveSource: withUpdater(get().recActiveSource, u) }),
  recActiveHealth: new Set(),
  setRecActiveHealth: (u) => set({ recActiveHealth: withUpdater(get().recActiveHealth, u) }),

  perfQuery: '',
  setPerfQuery: (u) => set({ perfQuery: withUpdater(get().perfQuery, u) }),
  perfActiveDecade: new Set(),
  setPerfActiveDecade: (u) => set({ perfActiveDecade: withUpdater(get().perfActiveDecade, u) }),
  perfActiveYear: new Set(),
  setPerfActiveYear: (u) => set({ perfActiveYear: withUpdater(get().perfActiveYear, u) }),
  perfActiveCoverage: new Set(),
  setPerfActiveCoverage: (u) => set({ perfActiveCoverage: withUpdater(get().perfActiveCoverage, u) }),
  perfActiveSource: new Set(),
  setPerfActiveSource: (u) => set({ perfActiveSource: withUpdater(get().perfActiveSource, u) }),
  perfActiveRating: new Set(),
  setPerfActiveRating: (u) => set({ perfActiveRating: withUpdater(get().perfActiveRating, u) }),
  perfView: 'all',
  setPerfView: (u) => set({ perfView: withUpdater(get().perfView, u) }),
}))

// ── Screen ───────────────────────────────────────────────────────────────────

// ── Resizable column widths (recording lens) ─────────────────────────────────
// `location` stays flex (no entry here) — it's the trailing spacer that
// absorbs leftover width, same as ScreenCollection's non-resizable columns.
type RecColKey = 'lb' | 'status' | 'date' | 'rating' | 'desc' | 'folder' | 'confirmed' | 'source' | 'own' | 'flags'
const REC_COL_DEFAULTS: Record<RecColKey, number> = {
  lb: 92, status: 88, date: 88, rating: 48,
  desc: 250, folder: 180, confirmed: 90,
  source: 60, own: 52, flags: 52,
}

export function ScreenLibrary(): React.JSX.Element {
  // ── TODO-150 step 6: lens toggle. "By performance" is the new, richer view
  // (00-overview.md "One catalogue, two lenses"); "By recording" is this
  // screen's original step-4 flat table. Both read the same merged `rows`.
  const { t } = useTranslation()
  const [lens, setLens] = useState<'performance' | 'recording'>('performance')

  // BUG-219: query/scope/active* filters below live in useLibraryFilterStore
  // (module scope) instead of useState, so they survive this screen unmounting
  // on navigation and remounting when the user comes back.
  const scope    = useLibraryFilterStore(s => s.recScope)
  const setScope = useLibraryFilterStore(s => s.setRecScope)
  const query    = useLibraryFilterStore(s => s.recQuery)
  const setQuery = useLibraryFilterStore(s => s.setRecQuery)
  const [groupByYear, setGroupByYear] = useState(true)
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())
  const [selectedLb, setSelectedLb] = useState<number | null>(null)
  const [detailPanelOpen, setDetailPanelOpen] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('lb')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  // TODO-150 step 7: checkbox multi-select for the recording lens's bulk bar.
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())

  const activeDecade    = useLibraryFilterStore(s => s.recActiveDecade)
  const setActiveDecade = useLibraryFilterStore(s => s.setRecActiveDecade)
  const activeStatus    = useLibraryFilterStore(s => s.recActiveStatus)
  const setActiveStatus = useLibraryFilterStore(s => s.setRecActiveStatus)
  const activeRating    = useLibraryFilterStore(s => s.recActiveRating)
  const setActiveRating = useLibraryFilterStore(s => s.setRecActiveRating)
  const activeSource    = useLibraryFilterStore(s => s.recActiveSource)
  const setActiveSource = useLibraryFilterStore(s => s.setRecActiveSource)
  const activeHealth    = useLibraryFilterStore(s => s.recActiveHealth)
  const setActiveHealth = useLibraryFilterStore(s => s.setRecActiveHealth)

  const tableParentRef = useRef<HTMLDivElement>(null)

  const { widths: colWidths, startResize: startColResize } = useResizableColumns('lbb_library_rec_col_widths', REC_COL_DEFAULTS)

  // ── TODO-150 step 7: shared action system ───────────────────────────────────
  // Toast/confirm UI + the ActionHandlers bag, shared by both lenses. Handlers
  // call the SAME backend endpoints ScreenCollection.tsx already uses for
  // these ids — this isn't new backend behavior, just a second surface for it.

  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setActiveAttachLb = useAttachmentsStore(s => s.setActiveLb)
  const addPendingSpectro = useSpectrogramStore(s => s.addPending)
  const addToFolderQueue = useFolderQueueStore(s => s.addFolders)

  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; body: string; onConfirm: () => void } | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])
  const refreshCollection = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['library-catalog'] })
    queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] })
  }, [queryClient])

  const actionHandlers = useMemo<ActionHandlers>(() => ({
    onOpen: (row) => {
      window.open(lbDetailUrl(row.lbNumber), '_blank')
    },
    onCopyLb: (row) => { navigator.clipboard.writeText(row.lb) },
    onCopyPath: (row) => { navigator.clipboard.writeText(row.path) },
    onPlay: async (row) => {
      if (!row.path) return
      try {
        const resp = await fetch(`${BASE}/api/open/vlc`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paths: [row.path] }),
        })
        const data = await resp.json()
        if (!data.ok) showToast(data.error || t('library.toast.vlcNotFound'), 'bad')
      } catch { showToast(t('library.toast.vlcFailed'), 'bad') }
    },
    onReveal: async (row) => {
      if (!row.path) { showToast(t('library.toast.noDiskPath'), 'info'); return }
      await window.api.openPath(row.path)
    },
    onQbt: async (rows) => {
      const lbs = rows.map(r => r.lbNumber)
      if (!lbs.length) return
      try {
        const resp = await fetch(`${BASE}/api/qbt/add`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lb_numbers: lbs }),
        })
        const data = await resp.json()
        showToast(t('library.toast.qbtAdded', { added: data.added ?? 0, total: data.total ?? lbs.length }), data.ok ? 'ok' : 'bad')
      } catch { showToast(t('library.toast.qbtFailed'), 'bad') }
    },
    onTorrent: async (rows) => {
      const targets = rows.filter(r => r.path)
      if (!targets.length) { showToast(t('library.toast.noDiskPath'), 'info'); return }
      setActionBusy(true)
      let ok = 0; let fail = 0
      for (const r of targets) {
        try {
          const resp = await fetch(`${BASE}/api/torrent/create`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: r.lbNumber, source_folder: r.path }),
          })
          const data = await resp.json()
          if (data.ok) ok++; else fail++
        } catch { fail++ }
      }
      setActionBusy(false)
      showToast(t('library.toast.torrentsCreated', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : ''), ok > 0 ? 'ok' : 'bad')
    },
    onForum: (rows) => {
      const postOne = async (r: ActionRow): Promise<{ ok: boolean; topicUrl: string }> => {
        try {
          const previewResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/preview_forum`)
          const previewData = await previewResp.json()
          const postResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/post_forum`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject: previewData.subject ?? '', body: previewData.body ?? '' }),
          })
          const data = await postResp.json()
          return { ok: !!data.ok, topicUrl: data.topic_url ?? '' }
        } catch { return { ok: false, topicUrl: '' } }
      }
      const copyUrls = (urls: string[]) => {
        if (urls.length === 0) return
        navigator.clipboard.writeText(urls.join('\n')).catch(() => {})
      }
      if (rows.length === 1) {
        postOne(rows[0]).then(({ ok, topicUrl }) => {
          if (ok && topicUrl) {
            copyUrls([topicUrl])
            showToast(t('library.toast.postedForumCopied', { lb: rows[0].lb }), 'ok')
          } else {
            showToast(ok ? t('library.toast.postedForum', { lb: rows[0].lb }) : t('library.toast.forumPostFailed'), ok ? 'ok' : 'bad')
          }
        })
        return
      }
      setConfirm({
        title: t('library.ctx.postForum'),
        body: t('library.toast.confirmForumBody', { count: rows.length }),
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          const urls: string[] = []
          for (const r of rows) {
            const res = await postOne(r)
            if (res.ok) { ok++; if (res.topicUrl) urls.push(res.topicUrl) } else fail++
          }
          copyUrls(urls)
          setActionBusy(false)
          const base = t('library.toast.postsCreated', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : '')
          showToast(ok > 0 && urls.length > 0 ? base + t('library.toast.linksCopiedSuffix', { count: urls.length }) : base, ok > 0 ? 'ok' : 'bad')
        },
      })
    },
    onM3u: async (rows) => {
      const lbs = rows.map(r => r.lbNumber)
      if (!lbs.length) { showToast(t('library.toast.noOwnedExport'), 'info'); return }
      try {
        const resp = await fetch(`${BASE}/api/collection/export/m3u?lb_numbers=${lbs.join(',')}`)
        const blob = await resp.blob()
        blobDownload(blob, 'show.m3u')
      } catch { showToast(t('library.toast.m3uFailed'), 'bad') }
    },
    onAttach: (row) => { setActiveAttachLb(row.lbNumber); navigate('/attachments') },
    onSpectro: async (row) => {
      if (!row.path) return
      try {
        const resp = await fetch(`${BASE}/api/spectrogram/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [row.path] }),
        })
        const data = await resp.json()
        if (data.ok) { addPendingSpectro([row.path]); navigate('/spectrograms') }
        else showToast(data.error || t('library.toast.spectroFailed'), 'bad')
      } catch { showToast(t('library.toast.spectroFailed'), 'bad') }
    },
    onMap: () => navigate('/map'),
    onReconfirm: (row) => {
      if (!row.path) return
      addToFolderQueue([row.path])
      navigate('/verify')
    },
    onRelocate: async (rows) => {
      if (!rows.length) return
      if (rows.length === 1) {
        const target = rows[0]
        const dir = await window.api.pickDir()
        if (!dir) return
        const folderName = dir.replace(/\/+$/, '').split('/').pop() || dir
        try {
          await fetch(`${BASE}/api/collection/${target.lbNumber}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disk_path: dir, folder_name: folderName }),
          })
          showToast(t('library.toast.locationUpdated', { lb: target.lb }), 'ok')
          refreshCollection()
        } catch { showToast(t('library.toast.updateFailed'), 'bad') }
        return
      }
      const parentDir = await window.api.pickDir()
      if (!parentDir) return
      setActionBusy(true)
      let ok = 0; let skip = 0
      try {
        const scanResp = await fetch(`${BASE}/api/pipeline/scan-dir`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root: parentDir, recursive: false }),
        })
        const scanData = await scanResp.json()
        const entries: { lb_number: number; folder: string; path: string }[] = scanData.entries ?? []
        for (const r of rows) {
          const match = entries.find(e => e.lb_number === r.lbNumber)
          if (match) {
            await fetch(`${BASE}/api/collection/${r.lbNumber}`, {
              method: 'PATCH', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ disk_path: match.path, folder_name: match.folder }),
            })
            ok++
          } else skip++
        }
      } catch { skip = rows.length }
      setActionBusy(false)
      showToast(t('library.toast.updated', { count: ok }) + (skip > 0 ? t('library.toast.notFoundSuffix', { count: skip }) : ''), ok > 0 ? 'ok' : 'info')
      if (ok > 0) refreshCollection()
    },
    onRemove: (rows) => {
      if (!rows.length) return
      setConfirm({
        title: t('library.ctx.removeCollection'),
        body: t('library.toast.confirmRemoveBody', { count: rows.length }),
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          for (const r of rows) {
            try { await fetch(`${BASE}/api/collection/${r.lbNumber}`, { method: 'DELETE' }); ok++ } catch { fail++ }
          }
          setActionBusy(false)
          showToast(t('library.toast.removed', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : ''), ok > 0 ? 'ok' : 'bad')
          refreshCollection()
        },
      })
    },
    onWishlistToggle: async (row) => {
      try {
        if (row.wish) {
          await fetch(`${BASE}/api/wishlist/${row.lbNumber}`, { method: 'DELETE' })
          showToast(t('library.toast.wishlistRemoved', { lb: row.lb }), 'ok')
        } else {
          await fetch(`${BASE}/api/wishlist`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: row.lbNumber }),
          })
          showToast(t('library.toast.wishlistAdded', { lb: row.lb }), 'ok')
        }
        refreshCollection()
      } catch { showToast(t('library.toast.wishlistFailed'), 'bad') }
    },
    onWishlistAddMany: async (rows) => {
      if (!rows.length) return
      let ok = 0
      for (const r of rows) {
        try {
          await fetch(`${BASE}/api/wishlist`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: r.lbNumber }),
          })
          ok++
        } catch { /* continue */ }
      }
      showToast(t('library.toast.wishlistAddedCount', { count: ok }), ok > 0 ? 'ok' : 'bad')
      if (ok > 0) refreshCollection()
    },
  }), [t, showToast, refreshCollection, navigate, setActiveAttachLb, addPendingSpectro, addToFolderQueue])

  const { menu: ctxMenu, openMenu: openCtxMenu, closeMenu: closeCtxMenu } = useActionMenu()

  // ── Data loading — client-side adapter over the existing catalog + collection
  // prefetch endpoints (no backend changes this step) ──────────────────────────

  const { data: catalog, isLoading: catalogLoading } = useQuery({
    queryKey: ['library-catalog'],
    queryFn: () => fetch(`${BASE}/api/search`).then(r => r.json()),
    staleTime: Infinity,
  })

  // Same query key ScreenCollection.tsx uses for this endpoint — shares the
  // react-query cache instead of double-fetching when both screens are mounted.
  const { data: prefetch } = useQuery({
    queryKey: ['collection-prefetch'],
    queryFn: () => fetch(`${BASE}/api/collection/prefetch`).then(r => r.json()),
    staleTime: Infinity,
  })

  // TODO-150 step 8: detail-panel ShareSeed zone. `prefetch.torrents`/
  // `prefetch.forum_posts` already cover every LB — no new backend endpoint,
  // just grouped by lb_number into the per-row shape the panel reads.
  const { data: attachData } = useQuery({
    queryKey: ['library-attachments-cached'],
    queryFn: () => fetch(`${BASE}/api/attachments/cached`).then(r => r.json()),
    staleTime: 60_000,
  })

  const historyMap = useMemo(() => {
    const m = new Map<number, RowHistory>()
    const get = (lb: number) => m.get(lb) ?? (m.set(lb, { torrents: [], forum: [] }), m.get(lb)!)
    if (Array.isArray(prefetch?.torrents)) {
      for (const t of prefetch.torrents) {
        get(t.lb_number).torrents.push({
          d: t.created_at ?? '',
          f: (t.torrent_path ?? '').split(/[/\\]/).pop() ?? '',
          tag: t.added_to_qbt ? 'qBittorrent' : 'Local',
        })
      }
    }
    if (Array.isArray(prefetch?.forum_posts)) {
      for (const p of prefetch.forum_posts) {
        get(p.lb_number).forum.push({ d: p.posted_at ?? '', f: p.subject ?? '', tag: 'Posted' })
      }
    }
    return m
  }, [prefetch])

  const attachCountMap = useMemo(() => {
    const m = new Map<number, number>()
    if (Array.isArray(attachData?.entries)) {
      for (const e of attachData.entries) m.set(e.lb_number, (e.files ?? []).length)
    }
    return m
  }, [attachData])

  const rows = useMemo<RecordingRow[]>(() => {
    if (!Array.isArray(catalog)) return []

    const ownedMap = new Map<number, { folder: string; path: string; conf: string }>()
    if (prefetch && Array.isArray(prefetch.collection)) {
      for (const c of prefetch.collection) {
        ownedMap.set(c.lb_number, {
          folder: c.folder_name ?? '',
          path:   c.disk_path ?? '',
          conf:   c.confirmed_at ?? '',
        })
      }
    }
    const wishSet = new Set<number>(
      prefetch && Array.isArray(prefetch.wishlist) ? prefetch.wishlist.map((w: any) => w.lb_number) : []
    )
    const dupSet = new Set<number>()
    if (prefetch && Array.isArray(prefetch.duplicates)) {
      for (const group of prefetch.duplicates) {
        if (Array.isArray(group.owned) && group.owned.length > 1) {
          for (const o of group.owned) dupSet.add(o.lb_number as number)
        }
      }
    }
    const xrefSet = new Set<number>(
      prefetch && Array.isArray(prefetch.xref_lb_numbers) ? prefetch.xref_lb_numbers : []
    )

    return (catalog as any[]).map((d): RecordingRow => {
      const lbNumber = d.lb_number as number
      const owned = ownedMap.has(lbNumber)
      const own = ownedMap.get(lbNumber)
      const year = extractYear(d.date_str ?? '')
      const raw = d.rating ?? ''
      return {
        lb:       `LB-${String(lbNumber).padStart(5, '0')}`,
        lbNumber,
        year,
        decade:   decadeOf(year),
        date:     d.date_str ?? '',
        loc:      d.location ?? '',
        desc:     d.description ?? '',
        rating:   (VALID_RATINGS.has(raw) ? raw : '—') as RatingGrade,
        src:      (d.source_type as string | null) ?? null,
        taper:    (d.taper_name as string | null) ?? '',
        status:   ({ public: 'Public', private: 'Private', missing: 'Missing' }[d.lb_status as string] ?? 'Missing') as LibStatus,
        owned,
        wish:     wishSet.has(lbNumber),
        dup:      dupSet.has(lbNumber),
        xref:     xrefSet.has(lbNumber),
        unconf:   owned && !own?.conf,
        folder:   own?.folder ?? '',
        path:     own?.path ?? '',
        conf:     own?.conf ?? '',
      }
    })
  }, [catalog, prefetch])

  const ownedCount = useMemo(() => rows.reduce((n, r) => n + (r.owned ? 1 : 0), 0), [rows])

  // ── Facet counts (from the full, unfiltered merged set — matches the
  // existing convention in ScreenSearch.tsx, not progressively narrowed) ───────

  const facetCounts = useMemo(() => {
    const decadeC: Record<string, number> = {}
    const statusC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    const sourceC: Record<string, number> = {}
    const healthC: Record<string, number> = {}
    for (const r of rows) {
      decadeC[r.decade] = (decadeC[r.decade] ?? 0) + 1
      statusC[r.status] = (statusC[r.status] ?? 0) + 1
      ratingC[r.rating] = (ratingC[r.rating] ?? 0) + 1
      const src = r.src ?? 'Unset'
      sourceC[src] = (sourceC[src] ?? 0) + 1
      for (const h of Object.keys(HEALTH_CHECK) as HealthFlag[]) {
        if (HEALTH_CHECK[h](r)) healthC[h] = (healthC[h] ?? 0) + 1
      }
    }
    return { decadeC, statusC, ratingC, sourceC, healthC }
  }, [rows])

  // ── Filtering ────────────────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter(r => {
      if (scope === 'owned'   && !r.owned) return false
      if (scope === 'unowned' &&  r.owned) return false
      if (q && !`${r.lb} ${r.loc} ${r.desc}`.toLowerCase().includes(q)) return false
      if (activeDecade.size > 0 && !activeDecade.has(r.decade)) return false
      // Default view hides Private/Missing entries; an explicit Status chip
      // (including selecting Private or Missing themselves) overrides this.
      if (activeStatus.size > 0) {
        if (!activeStatus.has(r.status)) return false
      } else if (r.status === 'Private' || r.status === 'Missing') {
        return false
      }
      if (activeRating.size > 0 && !activeRating.has(r.rating)) return false
      if (activeSource.size > 0 && !activeSource.has(r.src ?? 'Unset')) return false
      if (activeHealth.size > 0 && ![...activeHealth].some(h => HEALTH_CHECK[h](r))) return false
      return true
    })
  }, [rows, scope, query, activeDecade, activeStatus, activeRating, activeSource, activeHealth])

  // ── Sorting ──────────────────────────────────────────────────────────────

  const sortedRows = useMemo(() => {
    const arr = [...filteredRows]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      if (sortKey === 'lb')     return (a.lbNumber - b.lbNumber) * dir
      if (sortKey === 'date')   return a.date.localeCompare(b.date) * dir
      return ((RATING_RANK[a.rating] ?? 0) - (RATING_RANK[b.rating] ?? 0)) * dir
    })
    return arr
  }, [filteredRows, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); return }
    setSortKey(key)
    setSortDir('asc')
  }

  // ── Grouping by year ─────────────────────────────────────────────────────

  const groupedByYear = useMemo(() => {
    if (!groupByYear) return null
    const map = new Map<string, RecordingRow[]>()
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

  const flatItems = useMemo((): FlatItem[] => {
    if (!groupByYear || !groupedByYear) return sortedRows.map(row => ({ kind: 'row', row }) as FlatItem)
    const items: FlatItem[] = []
    for (const [year, yearRows] of groupedByYear) {
      items.push({ kind: 'group', year, count: yearRows.length })
      if (!collapsedYears.has(year)) for (const row of yearRows) items.push({ kind: 'row', row })
    }
    return items
  }, [groupedByYear, groupByYear, sortedRows, collapsedYears])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: i => flatItems[i]?.kind === 'group' ? 32 : 34,
    overscan: 12,
  })

  const colCount = 10 // edge + checkbox + LB# + Status + Date + Location + Rating + (scope-dependent cols)

  // ── TODO-150 step 7: checkbox selection + right-click target rows ──────────
  // Mirrors ScreenCollection.tsx's getCtxRows(): right-click a checked row to
  // act on the whole checked set, right-click an unchecked row to act on it alone.

  const toggleCheck = (lbNumber: number, checked: boolean) => {
    setCheckedIds(prev => {
      const next = new Set(prev)
      checked ? next.add(lbNumber) : next.delete(lbNumber)
      return next
    })
  }
  const allChecked = sortedRows.length > 0 && sortedRows.every(r => checkedIds.has(r.lbNumber))
  const toggleAllChecked = () => {
    setCheckedIds(prev => {
      if (allChecked) return new Set()
      const next = new Set(prev)
      sortedRows.forEach(r => next.add(r.lbNumber))
      return next
    })
  }
  const getCheckedRows = useCallback((): RecordingRow[] => rows.filter(r => checkedIds.has(r.lbNumber)), [rows, checkedIds])
  const getCtxBatch = useCallback((row: RecordingRow): ActionRow[] => {
    if (checkedIds.size > 0 && checkedIds.has(row.lbNumber)) return getCheckedRows().map(toRecAction)
    return []
  }, [checkedIds, getCheckedRows])

  const handleBulkCreateTorrent = () => actionHandlers.onTorrent(getCheckedRows().map(toRecAction))
  const handleBulkAddQbt = () => actionHandlers.onQbt(getCheckedRows().map(toRecAction))
  const handleBulkRelocate = () => actionHandlers.onRelocate(getCheckedRows().map(toRecAction))
  const handleBulkRemove = () => actionHandlers.onRemove(getCheckedRows().map(toRecAction))

  const hasActiveFilters = activeDecade.size > 0 || activeStatus.size > 0 || activeRating.size > 0
    || activeSource.size > 0 || activeHealth.size > 0 || scope !== 'all'
  const recActiveCount = activeDecade.size + activeStatus.size + activeRating.size + activeSource.size + activeHealth.size + (scope !== 'all' ? 1 : 0)

  const clearAll = () => {
    setActiveDecade(new Set()); setActiveStatus(new Set()); setActiveRating(new Set())
    setActiveSource(new Set()); setActiveHealth(new Set()); setScope('all'); setQuery('')
  }

  const filterChips: Array<{ label: string; onRemove: () => void }> = [
    ...[...activeDecade].map(d => ({ label: `${t('library.facets.decade')}: ${d}`, onRemove: () => toggleSet(setActiveDecade, d) })),
    ...[...activeStatus].map(s => ({ label: `${t('library.facets.status')}: ${t(STATUS_LABEL_KEY[s])}`, onRemove: () => toggleSet(setActiveStatus, s) })),
    ...[...activeRating].map(r => ({ label: `${t('library.facets.rating')}: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
    ...[...activeSource].map(s => ({ label: `${t('library.facets.source')}: ${s}`, onRemove: () => toggleSet(setActiveSource, s) })),
    ...[...activeHealth].map(h => ({ label: h, onRemove: () => toggleSet(setActiveHealth, h) })),
  ]

  const loading = catalogLoading && rows.length === 0

  // ── TODO-150 step 7: overlays shared by both lenses (context menu, toast,
  // confirm dialog) — rendered once per branch since each `return` is a
  // separate screen root. ──────────────────────────────────────────────────
  const overlays = (
    <>
      {ctxMenu && <ActionMenu state={ctxMenu} onClose={closeCtxMenu} />}
      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  )

  if (lens === 'performance') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }} data-screen-label="Library (by performance)">
        <PerformanceLensView
          lens={lens} setLens={setLens}
          rows={rows} catalogLoading={loading} actionHandlers={actionHandlers} openCtxMenu={openCtxMenu}
          historyMap={historyMap} attachCountMap={attachCountMap}
        />
        {overlays}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }} data-screen-label="Library (by recording)">

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        padding: '12px 20px', borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--sep-chrome-bg, var(--lbb-surface))', zIndex: 4,
      }}>
        <ViewToggle value={lens} onChange={setLens} />
        <span style={{ width: 1, height: 22, background: 'var(--lbb-border)', flexShrink: 0 }} />
        <ScopeControl value={scope} onChange={setScope} allCount={rows.length} ownedCount={ownedCount} />
        <Input
          icon="search" placeholder={t('library.toolbar.searchRecording')}
          value={query} onChange={e => setQuery(e.target.value)}
          style={{ flex: 1, height: 32 }}
        />
        <Button variant="secondary" size="md" onClick={() => setGroupByYear(g => !g)}>{t('library.toolbar.columns')}</Button>
        <IconButton icon="download" title={t('library.toolbar.export')} />
        <IconButton icon="more" title={t('library.toolbar.more')} />
      </div>

      {/* ── Filter bar ───────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flexShrink: 0,
        padding: '8px 20px', borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--sep-summary-bg, var(--lbb-surface))', zIndex: 3,
      }}>
        <FilterMenu label={t('library.facets.decade')} count={activeDecade.size}>
          <MenuLabel>{t('library.facets.decade')}</MenuLabel>
          <FacetList>
            {Object.entries(facetCounts.decadeC).sort(([a], [b]) => a.localeCompare(b)).map(([lbl, cnt]) => (
              <FacetOption key={lbl} label={lbl} count={cnt} active={activeDecade.has(lbl)} onClick={() => toggleSet(setActiveDecade, lbl)} />
            ))}
          </FacetList>
        </FilterMenu>
        <FilterMenu label={t('library.facets.status')} count={activeStatus.size}>
          <MenuLabel>{t('library.facets.status')}</MenuLabel>
          <FacetList>
            {(['Public', 'Private', 'Missing'] as LibStatus[]).map(s => (
              <FacetOption key={s} label={t(STATUS_LABEL_KEY[s])} count={facetCounts.statusC[s] ?? 0} active={activeStatus.has(s)} onClick={() => toggleSet(setActiveStatus, s)} />
            ))}
          </FacetList>
        </FilterMenu>
        <FilterMenu label={t('library.facets.rating')} count={activeRating.size}>
          <MenuLabel>{t('library.facets.rating')}</MenuLabel>
          <FacetList>
            {Object.entries(facetCounts.ratingC).sort(([a], [b]) => (RATING_RANK[b] ?? 0) - (RATING_RANK[a] ?? 0)).map(([lbl, cnt]) => (
              <FacetOption key={lbl} label={lbl} count={cnt} active={activeRating.has(lbl as RatingGrade)} onClick={() => toggleSet(setActiveRating, lbl as RatingGrade)} />
            ))}
          </FacetList>
        </FilterMenu>
        {Object.keys(facetCounts.sourceC).length > 0 && (
          <FilterMenu label={t('library.facets.source')} count={activeSource.size}>
            <MenuLabel>{t('library.facets.source')}</MenuLabel>
            <FacetList>
              {Object.entries(facetCounts.sourceC).map(([lbl, cnt]) => (
                <FacetOption key={lbl} label={lbl} count={cnt} active={activeSource.has(lbl)} onClick={() => toggleSet(setActiveSource, lbl)} />
              ))}
            </FacetList>
          </FilterMenu>
        )}
        {scope === 'owned' && (
          <FilterMenu label={t('library.facets.health')} count={activeHealth.size}>
            <MenuLabel>{t('library.facets.collectionHealth')}</MenuLabel>
            <FacetList>
              {(Object.keys(HEALTH_CHECK) as HealthFlag[]).map(h => (
                <FacetOption key={h} label={h} count={facetCounts.healthC[h] ?? 0} active={activeHealth.has(h)} onClick={() => toggleSet(setActiveHealth, h)} />
              ))}
            </FacetList>
          </FilterMenu>
        )}
        <div style={{ flex: 1 }} />
        {recActiveCount > 0 && (
          <button type="button" onClick={clearAll} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: '0 6px',
            fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', fontFamily: 'inherit', fontWeight: 'var(--w-med)',
          }}>
            {t('library.facets.clear', { count: recActiveCount })}
          </button>
        )}
      </div>

      {/* ── Summary strip ────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'nowrap', overflow: 'hidden', flexShrink: 0,
        padding: '8px 20px', borderBottom: '1px solid var(--lbb-border)',
        height: 40, fontSize: 'var(--t-meta)',
        background: 'var(--sep-summary-bg, var(--lbb-surface))', zIndex: 1,
      }}>
        <span style={{ fontWeight: 'var(--w-bold)', color: 'var(--lbb-fg)', whiteSpace: 'nowrap' }}>{sortedRows.length.toLocaleString()}</span>
        <span style={{ color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>{t('library.summary.ofMaster', { count: rows.length })}</span>
        {filterChips.map((f, i) => <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />)}
        <div style={{ flex: 1 }} />
        {rows.length > 0 && (
          <span style={{ color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
            <strong style={{ color: 'var(--lbb-ok-fg)', fontWeight: 'var(--w-bold)' }}>{Math.round((ownedCount / rows.length) * 100)}%</strong> {t('library.summary.owned')}
            {' · '}{t('library.summary.toGo', { count: rows.length - ownedCount })}
          </span>
        )}
        <span style={{ width: 1, height: 14, background: 'var(--lbb-border)', flexShrink: 0 }} />
        <button type="button"
          onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px', fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
        >
          {t('library.toolbar.sort')} {sortDir === 'asc' ? '↑' : '↓'}
        </button>
      </div>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div style={{
        flex: 1, display: 'flex', minHeight: 0, position: 'relative',
        background: 'var(--sep-body-bg, transparent)',
        gap: 'var(--sep-body-gap, 0px)',
        padding: 'var(--sep-body-pad, 0px)',
      }}>
        {/* Table region */}
        <div ref={tableParentRef} style={{
          flex: 1, overflow: 'auto', minHeight: 0, minWidth: 0, position: 'relative',
          background: 'var(--sep-table-bg, transparent)',
          borderRadius: 'var(--sep-radius, 0px)',
          boxShadow: 'var(--sep-table-shadow, none)',
        }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 34 }} />
              <col style={{ width: colWidths.lb }} />
              <col style={{ width: colWidths.status }} />
              <col style={{ width: colWidths.date }} />
              <col />
              <col style={{ width: colWidths.rating }} />{/* ★ rating — spec §6 (was 54) */}
              {scope === 'owned' ? <>
                <col style={{ width: colWidths.desc }} />
                <col style={{ width: colWidths.folder }} />
                <col style={{ width: colWidths.confirmed }} />
              </> : <>
                <col />
                <col style={{ width: colWidths.source }} />
                <col style={{ width: colWidths.own }} />
                <col style={{ width: colWidths.flags }} />
              </>}
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH><input type="checkbox" checked={allChecked} onChange={toggleAllChecked} /></TH>
                <TH onClick={() => handleSort('lb')} sorted={sortKey === 'lb' ? sortDir : null} onResizeStart={e => startColResize('lb', e.clientX, colWidths.lb)}>LB#</TH>
                <TH onResizeStart={e => startColResize('status', e.clientX, colWidths.status)}>{t('library.columns.status')}</TH>
                <TH onClick={() => handleSort('date')} sorted={sortKey === 'date' ? sortDir : null} onResizeStart={e => startColResize('date', e.clientX, colWidths.date)}>{t('library.columns.date')}</TH>
                <TH>{t('library.columns.location')}</TH>
                <TH align="center" onClick={() => handleSort('rating')} sorted={sortKey === 'rating' ? sortDir : null} onResizeStart={e => startColResize('rating', e.clientX, colWidths.rating)}>★</TH>
                {scope === 'owned' ? <>
                  <TH onResizeStart={e => startColResize('desc', e.clientX, colWidths.desc)}>{t('library.columns.description')}</TH>
                  <TH onResizeStart={e => startColResize('folder', e.clientX, colWidths.folder)}>{t('library.columns.folder')}</TH>
                  <TH onResizeStart={e => startColResize('confirmed', e.clientX, colWidths.confirmed)}>{t('library.columns.confirmed')}</TH>
                </> : <>
                  <TH>{t('library.columns.description')}</TH>
                  <TH onResizeStart={e => startColResize('source', e.clientX, colWidths.source)}>{t('library.columns.source')}</TH>
                  <TH align="center" onResizeStart={e => startColResize('own', e.clientX, colWidths.own)}>{t('library.columns.own')}</TH>
                  <TH align="center" onResizeStart={e => startColResize('flags', e.clientX, colWidths.flags)}>{t('library.columns.flags')}</TH>
                </>}
              </tr>
            </thead>
            <tbody>
              {(() => {
                const vItems    = virtualizer.getVirtualItems()
                const padTop    = vItems.length > 0 ? vItems[0].start : 0
                const padBottom = vItems.length > 0 ? virtualizer.getTotalSize() - vItems[vItems.length - 1].end : 0
                return (
                  <>
                    {padTop > 0 && <tr><td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} /></tr>}
                    {vItems.map(vItem => {
                      const item = flatItems[vItem.index]
                      if (!item) return null

                      if (item.kind === 'group') {
                        return (
                          <GroupRow
                            key={`g-${item.year}`}
                            label={item.year === 'Unknown' ? t('library.empty.unknownYear') : item.year}
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
                      const isChecked = checkedIds.has(r.lbNumber)
                      return (
                        <TR
                          key={r.lb}
                          edge={statusTone(r.status)}
                          selected={r.lbNumber === selectedLb}
                          onClick={() => setSelectedLb(prev => prev === r.lbNumber ? null : r.lbNumber)}
                          onContextMenu={e => openCtxMenu(e, r.lb, buildRecordingActions(toRecAction(r), getCtxBatch(r), actionHandlers, t))}
                          style={{ height: vItem.size }}
                        >
                          <TD>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onClick={e => e.stopPropagation()}
                              onChange={e => toggleCheck(r.lbNumber, e.target.checked)}
                            />
                          </TD>
                          <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 'var(--w-semi)' }}>{r.lb}</TD>
                          <TD><Pill tone={statusTone(r.status)} soft>{t(STATUS_LABEL_KEY[r.status])}</Pill></TD>
                          <TD mono>{r.date}</TD>
                          <TD>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.loc}</span>
                              {taperBadgeLabel(r.taper) && (
                                <Pill tone="mute" soft title={t('library.columns.taper')}>{taperBadgeLabel(r.taper)}</Pill>
                              )}
                            </div>
                          </TD>
                          <TD align="center">
                            {r.rating !== '—'
                              ? <Pill tone={ratingTone(r.rating)} soft>{r.rating}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                          </TD>
                          {scope === 'owned' ? <>
                            <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>{r.desc}</TD>
                            <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>{r.folder}</TD>
                            <TD mono dim style={{ fontSize: 'var(--lbb-fs-11)' }}>{r.conf ? r.conf.slice(0, 10) : '—'}</TD>
                          </> : <>
                            <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>{r.desc}</TD>
                            <TD>
                              {r.src ? <Pill tone="mute" soft>{SRC_ABBR[r.src] ?? r.src}</Pill> : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </TD>
                            <TD align="center">
                              {r.owned
                                ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)' }} />
                                : r.wish
                                  ? <Icon name="star" size={12} style={{ color: 'var(--lbb-warn-fg)' }} />
                                  : <Icon name="x" size={13} style={{ color: 'var(--lbb-bad-fg)' }} />}
                            </TD>
                            <TD align="center">
                              {r.dup
                                ? <Pill tone="warn" soft>{t('library.panel.dup')}</Pill>
                                : r.xref
                                  ? <Pill tone="info" soft>{t('library.panel.xref')}</Pill>
                                  : null}
                            </TD>
                          </>}
                        </TR>
                      )
                    })}
                    {padBottom > 0 && <tr><td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {loading && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
            }}>
              {t('library.empty.loading')}
            </div>
          )}

          {!loading && rows.length > 0 && sortedRows.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg2)' }}>{t('library.empty.nothingMatches')}</div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>{t('library.empty.tryAdjust')}</div>
              </div>
            </div>
          )}

          {/* Floating BulkActionBar */}
          {checkedIds.size > 0 && (
            <div style={{
              position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)',
              borderRadius: 10, boxShadow: 'var(--lbb-shadowLg)',
            }}>
              <BulkActionBar
                count={checkedIds.size}
                busy={actionBusy}
                onCreateTorrent={handleBulkCreateTorrent}
                onAddQbt={handleBulkAddQbt}
                onRelocate={handleBulkRelocate}
                onRemove={handleBulkRemove}
                onClear={() => setCheckedIds(new Set())}
              />
            </div>
          )}
        </div>

        {/* Detail panel — always mounted so it can collapse to 40px stub */}
        {(() => {
          const selRow = selectedLb !== null ? (rows.find(r => r.lbNumber === selectedLb) ?? null) : null
          return (
            <RecordingDetailPanel
              row={selRow}
              history={selRow ? historyMap.get(selRow.lbNumber) : undefined}
              attachCount={selRow ? attachCountMap.get(selRow.lbNumber) : undefined}
              actionHandlers={actionHandlers}
              openMenu={openCtxMenu}
              onClose={() => setSelectedLb(null)}
              open={detailPanelOpen}
              onToggle={() => setDetailPanelOpen(o => !o)}
            />
          )
        })()}
      </div>
      {overlays}
    </div>
  )
}

// ── TODO-150 step 6: performance lens ───────────────────────────────────────
// Rows are shows (date + venue); each expands into its TapeMatch families,
// which expand into member recordings. Reuses the recording lens's already
// owned/wish/dup-merged `rows` by lbNumber instead of re-deriving that
// merge — the only new fetches here are /api/library/performances (the
// show grouping itself) and /api/tapematch/families (per 07 §4/§5, merged
// client-side, never joined server-side). When no recording has a `fam`,
// every family collapses to one member — the no-families fallback in
// 03-data-contract.md falls out of this for free, no separate code path.

interface PerformanceRow {
  id: string
  date: string
  disp: string
  dow?: string
  year: number
  decade: string
  venue: string | null
  city: string | null
  tour?: string
  status: LibStatus
  // Absent (true) for ordinary lb_category='concert' shows. False only for
  // rows the backend inferred from a date+location-complete 'unknown' entry
  // that didn't match bobdylan_shows/dylan_performances — real performances
  // (often guest spots at other artists' shows) with no venue/setlist/tour
  // data to back them (TODO-151 audit, 2026-06-18).
  confirmed?: boolean
  tracks?: number
  setlist?: string
  title?: string
  recordings: RecordingRow[]
}

interface FamilyGroup {
  id: string
  members: RecordingRow[]
  tmLabel: string | null
  by: 'lb' | 'ai' | 'ai+lb'
  conf: number | null
  src: string | null
  bestRating: RatingGrade
  owned: boolean
  ownedCount: number
  total: number
  multi: boolean
  canonical: RecordingRow | null
  needsReview: boolean
  reviewReason: string | null
}

type Coverage = 'Covered' | 'Upgrade' | 'Gap' | 'Undocumented'

function bestOf(recs: RecordingRow[]): RecordingRow | null {
  return recs.reduce<RecordingRow | null>((b, r) =>
    (RATING_RANK[r.rating] ?? 0) > (RATING_RANK[b ? b.rating : '—'] ?? -1) ? r : b, null)
}

function familiesOf(recordings: RecordingRow[]): FamilyGroup[] {
  const groups = new Map<string, RecordingRow[]>()
  for (const r of recordings) {
    const key = r.fam || r.lb
    const arr = groups.get(key)
    if (arr) arr.push(r); else groups.set(key, [r])
  }
  const out: FamilyGroup[] = []
  for (const [key, members] of groups) {
    const best = bestOf(members)
    const owned = members.filter(r => r.owned)
    const bestOwned = bestOf(owned)
    const canonical = bestOwned || best
    const src = canonical ? canonical.src : (members[0]?.src ?? null)
    out.push({
      id: key, members,
      // TapeMatch's match-group name (Solo / Family A / Family B...); the source
      // type itself is already shown via the AUD/SBD/etc. pill, so it isn't repeated here.
      tmLabel: members[0]?.famLabel ?? null,
      by: members[0]?.famBy ?? 'lb',
      conf: members[0]?.famConf ?? null,
      src,
      bestRating: (best?.rating ?? '—') as RatingGrade,
      owned: owned.length > 0, ownedCount: owned.length, total: members.length,
      multi: members.length > 1,
      canonical,
      needsReview: !!members[0]?.famNeedsReview,
      reviewReason: members[0]?.famReviewReason ?? null,
    })
  }
  out.sort((a, b) =>
    (Number(b.owned) - Number(a.owned)) ||
    ((RATING_RANK[b.bestRating] ?? 0) - (RATING_RANK[a.bestRating] ?? 0)) ||
    (b.total - a.total))
  return out
}

function rollupOf(recordings: RecordingRow[]) {
  const owned = recordings.filter(r => r.owned)
  const best = bestOf(recordings)
  const fams = familiesOf(recordings)
  let coverage: Coverage
  if (recordings.length === 0) coverage = 'Undocumented'
  else if (owned.length === 0) coverage = 'Gap'
  else if (owned.length < recordings.length && best && !best.owned) coverage = 'Upgrade'
  else coverage = 'Covered'
  return {
    total: recordings.length, ownedCount: owned.length,
    famTotal: fams.length, famOwned: fams.filter(f => f.owned).length,
    bestRating: (best?.rating ?? '—') as RatingGrade,
    coverage, fams,
  }
}

function coverageTone(c: Coverage): 'ok' | 'warn' | 'mute' {
  if (c === 'Covered') return 'ok'
  if (c === 'Gap') return 'mute'
  return 'warn'
}

function coverageLabel(c: Coverage, ownedCount: number, total: number, t: TFunction): string {
  if (c === 'Covered') return total > 1 ? t('library.coverage.ownedFull', { owned: ownedCount, total }) : t('library.coverage.owned')
  if (c === 'Upgrade') return t('library.coverage.upgrade', { owned: ownedCount, total })
  if (c === 'Gap') return t('library.coverage.gap')
  return t('library.coverage.noSource')
}

type PerfFlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'show'; perf: PerformanceRow }
  | { kind: 'fam'; perf: PerformanceRow; fam: FamilyGroup }
  | { kind: 'member'; perf: PerformanceRow; fam: FamilyGroup; rec: RecordingRow; isLast: boolean; isCanonical: boolean }

// ── Resizable column widths (performance lens) ───────────────────────────────
// The trailing column stays flex (no entry here) — it absorbs leftover width
// per the spec §5 column model (see colgroup comment below).
type PerfColKey = 'date' | 'show' | 'tour' | 'families' | 'recs' | 'rating' | 'coverage'
const PERF_COL_DEFAULTS: Record<PerfColKey, number> = {
  date: 104, show: 345, tour: 155, families: 116, recs: 52, rating: 46, coverage: 112,
}

function PerformanceLensView({ lens, setLens, rows, catalogLoading, actionHandlers, openCtxMenu, historyMap, attachCountMap }: {
  lens: 'performance' | 'recording'
  setLens: (v: 'performance' | 'recording') => void
  rows: RecordingRow[]
  catalogLoading: boolean
  actionHandlers: ActionHandlers
  openCtxMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  historyMap: Map<number, RowHistory>
  attachCountMap: Map<number, number>
}) {
  const { t } = useTranslation()
  // BUG-219: query/active*/perfView filters below live in useLibraryFilterStore
  // (module scope) instead of useState, so they survive this screen unmounting
  // on navigation and remounting when the user comes back.
  const query    = useLibraryFilterStore(s => s.perfQuery)
  const setQuery = useLibraryFilterStore(s => s.setPerfQuery)
  const [groupByYear, setGroupByYear] = useState(true)
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())
  const [expandedShows, setExpandedShows] = useState<Set<string>>(new Set())
  const [collapsedFams, setCollapsedFams] = useState<Set<string>>(new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedMemberLb, setSelectedMemberLb] = useState<number | null>(null)
  const [detailPanelOpen, setDetailPanelOpen] = useState(true)
  const autoExpandedRef = useRef(false)

  const { widths: colWidths, startResize: startColResize } = useResizableColumns('lbb_library_perf_col_widths', PERF_COL_DEFAULTS)

  const activeDecade      = useLibraryFilterStore(s => s.perfActiveDecade)
  const setActiveDecade   = useLibraryFilterStore(s => s.setPerfActiveDecade)
  const activeYear        = useLibraryFilterStore(s => s.perfActiveYear)
  const setActiveYear     = useLibraryFilterStore(s => s.setPerfActiveYear)
  const activeCoverage    = useLibraryFilterStore(s => s.perfActiveCoverage)
  const setActiveCoverage = useLibraryFilterStore(s => s.setPerfActiveCoverage)
  const activeSource      = useLibraryFilterStore(s => s.perfActiveSource)
  const setActiveSource   = useLibraryFilterStore(s => s.setPerfActiveSource)
  const activeRating      = useLibraryFilterStore(s => s.perfActiveRating)
  const setActiveRating   = useLibraryFilterStore(s => s.setPerfActiveRating)
  const perfView    = useLibraryFilterStore(s => s.perfView)
  const setPerfView = useLibraryFilterStore(s => s.setPerfView)

  const tableParentRef = useRef<HTMLDivElement>(null)

  const { data: perfData, isLoading: perfLoading } = useQuery({
    queryKey: ['library-performances'],
    queryFn: () => fetch(`${BASE}/api/library/performances`).then(r => r.json()),
    staleTime: Infinity,
  })
  // Same query key the performance adapter will keep reusing once family
  // confirmation UI exists — shares the cache rather than re-fetching.
  const { data: famData } = useQuery({
    queryKey: ['tapematch-families'],
    queryFn: () => fetch(`${BASE}/api/tapematch/families`).then(r => r.json()),
    staleTime: Infinity,
  })

  const rowsByLb = useMemo(() => {
    const m = new Map<number, RecordingRow>()
    for (const r of rows) m.set(r.lbNumber, r)
    return m
  }, [rows])

  const famMap = useMemo(() => {
    const m = new Map<number, {
      fam_id: string; fam_label: string; fam_conf: number | null; fam_by: string
      fam_needs_review?: number | boolean; fam_review_reason?: string | null
    }>()
    if (Array.isArray(famData)) for (const f of famData as any[]) m.set(f.lb_number, f)
    return m
  }, [famData])

  const performances = useMemo<PerformanceRow[]>(() => {
    if (!Array.isArray(perfData)) return []
    return (perfData as any[]).map((p): PerformanceRow => {
      const recordings: RecordingRow[] = (p.recordings as any[])
        .map((stub): RecordingRow => {
          const base = rowsByLb.get(stub.lbNumber)
          const fam = famMap.get(stub.lbNumber)
          const row: RecordingRow = base ? { ...base } : {
            lb: stub.lb, lbNumber: stub.lbNumber, year: p.year ?? 0, decade: decadeOf(p.year ?? 0),
            date: p.date ?? '', loc: p.city ?? '', desc: '',
            rating: (VALID_RATINGS.has(stub.rating) ? stub.rating : '—') as RatingGrade,
            src: stub.src ?? null, taper: '', status: (stub.status ?? 'Missing') as LibStatus,
            owned: false, wish: false, dup: false, xref: false, unconf: false,
            folder: '', path: '', conf: '',
          }
          if (fam) {
            row.fam = fam.fam_id; row.famLabel = fam.fam_label
            row.famConf = fam.fam_conf; row.famBy = fam.fam_by as RecordingRow['famBy']
            row.famNeedsReview = !!fam.fam_needs_review; row.famReviewReason = fam.fam_review_reason ?? null
          }
          return row
        })
        // Performance lens has no per-recording Status filter (unlike the
        // recording lens), so Private/Missing entries are hidden from
        // counts/families unconditionally rather than just from a default —
        // matches the recording lens's default-hidden behavior.
        .filter(r => r.status !== 'Private' && r.status !== 'Missing')
      return {
        id: p.id, date: p.date ?? '', disp: p.disp ?? p.date ?? '', dow: p.dow,
        year: p.year ?? 0, decade: decadeOf(p.year ?? 0),
        venue: p.venue ?? null, city: p.city ?? null, tour: p.tour,
        status: (p.status ?? 'Missing') as LibStatus,
        confirmed: p.confirmed,
        tracks: p.tracks, setlist: p.setlist, title: p.title,
        recordings,
      }
    })
  }, [perfData, rowsByLb, famMap])

  // Auto-expand the first multi-recording show when data loads — mirrors the
  // prototype which starts with one show pre-expanded so family groups are
  // visible on first render without needing a click.
  useEffect(() => {
    if (autoExpandedRef.current || performances.length === 0) return
    const first = performances.find(p => p.recordings.length > 1)
    if (first) {
      setExpandedShows(new Set([first.id]))
      autoExpandedRef.current = true
    }
  }, [performances])

  const facetCounts = useMemo(() => {
    const decadeC: Record<string, number> = {}
    const yearC: Record<number, number> = {}
    const coverageC: Record<string, number> = {}
    const sourceC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    for (const p of performances) {
      const ru = rollupOf(p.recordings)
      decadeC[p.decade] = (decadeC[p.decade] ?? 0) + 1
      if (p.year > 0) yearC[p.year] = (yearC[p.year] ?? 0) + 1
      coverageC[ru.coverage] = (coverageC[ru.coverage] ?? 0) + 1
      ratingC[ru.bestRating] = (ratingC[ru.bestRating] ?? 0) + 1
      const seen = new Set<string>()
      for (const r of p.recordings) {
        if (r.src && !seen.has(r.src)) { seen.add(r.src); sourceC[r.src] = (sourceC[r.src] ?? 0) + 1 }
      }
    }
    return { decadeC, yearC, coverageC, sourceC, ratingC }
  }, [performances])

  const filteredPerfs = useMemo(() => {
    const q = query.trim().toLowerCase()
    return performances.filter(p => {
      const ru = rollupOf(p.recordings)
      if (q) {
        const hay = `${p.disp} ${p.venue ?? ''} ${p.city ?? ''} ${p.tour ?? ''} ${p.title ?? ''} ${
          p.recordings.map(r => `${r.lb} ${r.desc}`).join(' ')}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (activeDecade.size > 0 && !activeDecade.has(p.decade)) return false
      if (activeYear.size > 0 && !activeYear.has(p.year)) return false
      if (activeCoverage.size > 0 && !activeCoverage.has(ru.coverage)) return false
      if (activeRating.size > 0 && !activeRating.has(ru.bestRating)) return false
      if (activeSource.size > 0 && !p.recordings.some(r => r.src && activeSource.has(r.src))) return false
      if (perfView === 'owned')     return ru.ownedCount > 0
      if (perfView === 'gaps')      return ru.coverage === 'Gap'
      if (perfView === 'wishlist')  return p.recordings.some(r => r.wish)
      if (perfView === 'duplicates') return p.recordings.some(r => r.dup)
      return true
    })
  }, [performances, query, activeDecade, activeYear, activeCoverage, activeSource, activeRating, perfView])

  const sortedPerfs = useMemo(
    () => [...filteredPerfs].sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id)),
    [filteredPerfs],
  )

  const groupedByYear = useMemo(() => {
    if (!groupByYear) return null
    const map = new Map<string, PerformanceRow[]>()
    for (const p of sortedPerfs) {
      const key = p.year > 0 ? String(p.year) : 'Unknown'
      const arr = map.get(key)
      if (arr) arr.push(p); else map.set(key, [p])
    }
    return [...map.entries()].sort(([a], [b]) => {
      const an = a === 'Unknown' ? -1 : parseInt(a, 10)
      const bn = b === 'Unknown' ? -1 : parseInt(b, 10)
      return an - bn
    })
  }, [sortedPerfs, groupByYear])

  const flatItems = useMemo((): PerfFlatItem[] => {
    const items: PerfFlatItem[] = []
    const pushShow = (p: PerformanceRow) => {
      items.push({ kind: 'show', perf: p })
      if (!expandedShows.has(p.id)) return
      // A "Best rating" facet filter passes a show if any of its recordings
      // match, but the expanded family/member rows should still only surface
      // the matching recordings — otherwise off-rating siblings (eg. a C or D
      // alt source) stay visible under a show that only matched on its best.
      const visibleRecs = activeRating.size > 0
        ? p.recordings.filter(r => activeRating.has(r.rating))
        : p.recordings
      for (const fam of familiesOf(visibleRecs)) {
        items.push({ kind: 'fam', perf: p, fam })
        if (fam.multi && !collapsedFams.has(`${p.id}::${fam.id}`)) {
          fam.members.forEach((rec, i) => {
            items.push({
              kind: 'member', perf: p, fam, rec,
              isLast: i === fam.members.length - 1, isCanonical: rec === fam.canonical,
            })
          })
        }
      }
    }
    if (groupByYear && groupedByYear) {
      for (const [year, perfs] of groupedByYear) {
        items.push({ kind: 'group', year, count: perfs.length })
        if (!collapsedYears.has(year)) for (const p of perfs) pushShow(p)
      }
    } else {
      for (const p of sortedPerfs) pushShow(p)
    }
    return items
  }, [groupByYear, groupedByYear, sortedPerfs, collapsedYears, expandedShows, collapsedFams])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: i => {
      const it = flatItems[i]
      if (!it) return 34
      if (it.kind === 'group') return 32
      if (it.kind === 'show') return 38
      if (it.kind === 'fam') return 30
      return 28
    },
    overscan: 12,
  })

  const colCount = 10 // edge + expand + checkbox + date + show + tour + families + recs + ★ + coverage
  const perfActiveCount = activeDecade.size + activeYear.size + activeCoverage.size + activeSource.size + activeRating.size

  const expandableShowIds = useMemo(
    () => performances.filter(p => p.recordings.length > 0).map(p => p.id),
    [performances],
  )
  const allShowsExpanded = expandableShowIds.length > 0
    && expandableShowIds.every(id => expandedShows.has(id))
    && collapsedFams.size === 0
  const toggleExpandAll = () => {
    if (allShowsExpanded) {
      setExpandedShows(new Set())
    } else {
      setExpandedShows(new Set(expandableShowIds))
      setCollapsedFams(new Set())
    }
  }

  const totalRecs = useMemo(() => filteredPerfs.reduce((n, p) => n + p.recordings.length, 0), [filteredPerfs])
  const totalFams = useMemo(() => filteredPerfs.reduce((n, p) => n + rollupOf(p.recordings).famTotal, 0), [filteredPerfs])
  const gapsShown = useMemo(() => filteredPerfs.filter(p => rollupOf(p.recordings).coverage === 'Gap').length, [filteredPerfs])

  const viewCounts = useMemo(() => ({
    owned:     performances.filter(p => rollupOf(p.recordings).ownedCount > 0).length,
    gaps:      performances.filter(p => rollupOf(p.recordings).coverage === 'Gap').length,
    wishlist:  performances.filter(p => p.recordings.some(r => r.wish)).length,
    duplicates: performances.filter(p => p.recordings.some(r => r.dup)).length,
  }), [performances])

  const hasActiveFilters = activeDecade.size > 0 || activeYear.size > 0 || activeCoverage.size > 0 || activeSource.size > 0 || activeRating.size > 0 || perfView !== 'all'
  const clearAll = () => {
    setActiveDecade(new Set()); setActiveYear(new Set()); setActiveCoverage(new Set()); setActiveSource(new Set()); setActiveRating(new Set())
    setPerfView('all'); setQuery('')
  }
  const viewName = (v: string): string => t(VIEW_LABEL_KEY[v] ?? 'library.views.allPerformances')
  const coverageName = (c: string): string => t(COVERAGE_LABEL_KEY[c] ?? 'library.coverageValue.gap')

  const filterChips: Array<{ label: string; onRemove: () => void }> = [
    ...(perfView !== 'all' ? [{ label: `${t('library.facets.views')}: ${viewName(perfView)}`, onRemove: () => setPerfView('all') }] : []),
    ...[...activeDecade].map(d => ({ label: `${t('library.facets.decade')}: ${d}`, onRemove: () => toggleSet(setActiveDecade, d) })),
    ...[...activeYear].map(y => ({ label: `${t('library.facets.year')}: ${y}`, onRemove: () => toggleSet(setActiveYear, y) })),
    ...[...activeCoverage].map(c => ({ label: `${t('library.facets.coverageLabel')}: ${coverageName(c)}`, onRemove: () => toggleSet(setActiveCoverage, c) })),
    ...[...activeSource].map(s => ({ label: `${t('library.facets.source')}: ${s}`, onRemove: () => toggleSet(setActiveSource, s) })),
    ...[...activeRating].map(r => ({ label: `${t('library.facets.bestRating')}: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
  ]

  const loading = (catalogLoading || perfLoading) && performances.length === 0

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        padding: '12px 20px', borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--sep-chrome-bg, var(--lbb-surface))', zIndex: 4,
      }}>
        <ViewToggle value={lens} onChange={setLens} />
        <span style={{ width: 1, height: 22, background: 'var(--lbb-border)', flexShrink: 0 }} />
        <Input
          icon="search" placeholder={t('library.toolbar.searchPerformance')}
          value={query} onChange={e => setQuery(e.target.value)}
          style={{ flex: 1, height: 32 }}
        />
        <IconButton icon="download" title={t('library.toolbar.export')} />
        <IconButton icon="more" title={t('library.toolbar.more')} />
      </div>

      {/* ── Filter bar ───────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flexShrink: 0,
        padding: '8px 20px', borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--sep-summary-bg, var(--lbb-surface))', zIndex: 3,
        position: 'relative',
      }}>
        {/* Views preset menu */}
        <FilterMenu label={perfView === 'all' ? t('library.facets.views') : viewName(perfView)} count={perfView !== 'all' ? 1 : 0} width={220}>
          {close => {
            const opt = (id: typeof perfView, label: string, count?: number) => (
              <button key={id} type="button" onClick={() => { setPerfView(id); close() }} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                width: '100%', padding: '6px 8px', borderRadius: 6, cursor: 'pointer',
                background: perfView === id ? 'var(--lbb-accent-soft)' : 'transparent',
                color: perfView === id ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
                border: 'none', fontFamily: 'inherit', fontSize: 'var(--t-body)', fontWeight: perfView === id ? 'var(--w-semi)' : 'var(--w-reg)',
                textAlign: 'left',
              }}>
                <span>{label}</span>
                {count !== undefined && <span style={{ fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg3)', fontWeight: 'var(--w-med)' }}>{count.toLocaleString()}</span>}
              </button>
            )
            return <>
              {opt('all', t('library.views.allPerformances'), performances.length)}
              <div style={{ height: 1, background: 'var(--lbb-border)', margin: '4px 0' }} />
              {opt('owned', t('library.views.myCollection'), viewCounts.owned)}
              {opt('gaps', t('library.views.coverageGaps'), viewCounts.gaps)}
              {opt('wishlist', t('library.views.wishlist'), viewCounts.wishlist)}
              {opt('duplicates', t('library.views.duplicates'), viewCounts.duplicates)}
            </>
          }}
        </FilterMenu>
        <span style={{ width: 1, height: 20, background: 'var(--lbb-border)', flexShrink: 0 }} />
        <FilterMenu label={t('library.facets.decade')} count={activeDecade.size}>
          <MenuLabel>{t('library.facets.decade')}</MenuLabel>
          <FacetList>
            {Object.entries(facetCounts.decadeC).sort(([a], [b]) => a.localeCompare(b)).map(([lbl, cnt]) => (
              <FacetOption key={lbl} label={lbl} count={cnt} active={activeDecade.has(lbl)} onClick={() => toggleSet(setActiveDecade, lbl)} />
            ))}
          </FacetList>
        </FilterMenu>
        <FilterMenu label={t('library.facets.year')} count={activeYear.size}>
          <MenuLabel>{t('library.facets.year')}</MenuLabel>
          <button
            type="button"
            onClick={() => setActiveYear(new Set())}
            style={{
              display: 'block', width: '100%', textAlign: 'left', fontFamily: 'inherit',
              padding: '5px 8px', fontSize: 'var(--t-body)', cursor: 'pointer', border: 'none',
              background: activeYear.size === 0 ? 'var(--lbb-accent-soft)' : 'transparent',
              color: activeYear.size === 0 ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
              borderRadius: 6, marginBottom: 4,
            }}
          >
            {t('library.facets.allYears')}
          </button>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 2 }}>
            {Object.keys(facetCounts.yearC).sort((a, b) => Number(b) - Number(a)).map(lbl => (
              <button
                key={lbl}
                type="button"
                onClick={() => toggleSet(setActiveYear, Number(lbl))}
                style={{
                  textAlign: 'center', fontFamily: 'inherit',
                  padding: '5px 4px', fontSize: 'var(--t-body)', cursor: 'pointer', border: 'none',
                  background: activeYear.has(Number(lbl)) ? 'var(--lbb-accent-soft)' : 'transparent',
                  color: activeYear.has(Number(lbl)) ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
                  borderRadius: 6,
                }}
              >
                {lbl}
              </button>
            ))}
          </div>
        </FilterMenu>
        <FilterMenu label={t('library.facets.coverageLabel')} count={activeCoverage.size}>
          <MenuLabel>{t('library.facets.coverageLabel')}</MenuLabel>
          <FacetList>
            {(['Covered', 'Upgrade', 'Gap', 'Undocumented'] as Coverage[]).map(c => (
              <FacetOption key={c} label={coverageName(c)} count={facetCounts.coverageC[c] ?? 0} active={activeCoverage.has(c)} onClick={() => toggleSet(setActiveCoverage, c)} />
            ))}
          </FacetList>
        </FilterMenu>
        {Object.keys(facetCounts.sourceC).length > 0 && (
          <FilterMenu label={t('library.facets.source')} count={activeSource.size}>
            <MenuLabel>{t('library.facets.source')}</MenuLabel>
            <FacetList>
              {Object.entries(facetCounts.sourceC).map(([lbl, cnt]) => (
                <FacetOption key={lbl} label={lbl} count={cnt} active={activeSource.has(lbl)} onClick={() => toggleSet(setActiveSource, lbl)} />
              ))}
            </FacetList>
          </FilterMenu>
        )}
        <FilterMenu label={t('library.facets.bestRatingPerShow')} count={activeRating.size}>
          <MenuLabel>{t('library.facets.bestRating')}</MenuLabel>
          <FacetList>
            {Object.entries(facetCounts.ratingC).sort(([a], [b]) => (RATING_RANK[b] ?? 0) - (RATING_RANK[a] ?? 0)).map(([lbl, cnt]) => (
              <FacetOption key={lbl} label={lbl} count={cnt} active={activeRating.has(lbl as RatingGrade)} onClick={() => toggleSet(setActiveRating, lbl as RatingGrade)} />
            ))}
          </FacetList>
        </FilterMenu>
        <span style={{ width: 1, height: 20, background: 'var(--lbb-border)', flexShrink: 0 }} />
        <button
          type="button" onClick={toggleExpandAll} disabled={expandableShowIds.length === 0}
          title={allShowsExpanded ? t('library.toolbar.collapseAllShows') : t('library.toolbar.expandAllShows')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            height: 28, padding: '0 10px', borderRadius: 6, fontFamily: 'inherit',
            fontSize: 'var(--t-body)', fontWeight: 'var(--w-med)', whiteSpace: 'nowrap',
            cursor: expandableShowIds.length === 0 ? 'not-allowed' : 'pointer',
            opacity: expandableShowIds.length === 0 ? 0.5 : 1,
            background: 'var(--lbb-surface)', color: 'var(--lbb-fg2)',
            border: '1px solid var(--lbb-border2)',
          }}
        >
          <Icon name={allShowsExpanded ? 'chevUp' : 'chevDown'} size={12} style={{ opacity: 0.7 }} />
          {allShowsExpanded ? t('library.toolbar.collapseAll') : t('library.toolbar.expandAll')}
        </button>
        <div style={{ flex: 1 }} />
        {hasActiveFilters && (
          <button type="button" onClick={clearAll} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: '0 6px',
            fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', fontFamily: 'inherit', fontWeight: 'var(--w-med)',
          }}>
            {t('library.facets.clear', { count: perfActiveCount + (perfView !== 'all' ? 1 : 0) })}
          </button>
        )}
      </div>

      {/* ── Summary strip ────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'nowrap', overflow: 'hidden', flexShrink: 0,
        padding: '8px 20px', borderBottom: '1px solid var(--lbb-border)',
        height: 40, fontSize: 'var(--t-meta)',
        background: 'var(--sep-summary-bg, var(--lbb-surface))', zIndex: 1,
      }}>
        <span style={{ fontWeight: 'var(--w-bold)', color: 'var(--lbb-fg)', whiteSpace: 'nowrap' }}>
          {t('library.summary.shows', { count: filteredPerfs.length })}
        </span>
        <span style={{ color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>· {t('library.summary.recordings', { count: totalRecs })}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--lbb-info-fg)', fontWeight: 'var(--w-semi)', whiteSpace: 'nowrap' }}>
          <Icon name="tapematch" size={12} /> {t('library.summary.familyCount', { count: totalFams })}
        </span>
        {gapsShown > 0 && (
          <span style={{ color: 'var(--lbb-warn-fg)', fontWeight: 'var(--w-semi)', whiteSpace: 'nowrap' }}>
            · {t('library.summary.gaps', { count: gapsShown })}
          </span>
        )}
        {filterChips.map((f, i) => <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />)}
      </div>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div style={{
        flex: 1, display: 'flex', minHeight: 0, position: 'relative',
        background: 'var(--sep-body-bg, transparent)',
        gap: 'var(--sep-body-gap, 0px)',
        padding: 'var(--sep-body-pad, 0px)',
      }}>
        {/* Table region */}
        <div ref={tableParentRef} style={{
          flex: 1, overflow: 'auto', minHeight: 0, minWidth: 0, position: 'relative',
          background: 'var(--sep-table-bg, transparent)',
          borderRadius: 'var(--sep-radius, 0px)',
          boxShadow: 'var(--sep-table-shadow, none)',
        }}>
          <TableShell stickyHeader>
            {/* Column model (spec §5): every data column fixed to its longest
                content, dead 32px spacer removed, single trailing flex spacer
                absorbs leftover width at the table's natural end. */}
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 30 }} />
              <col style={{ width: colWidths.date }} />
              <col style={{ width: colWidths.show }} />
              <col style={{ width: colWidths.tour }} />
              <col style={{ width: colWidths.families }} />
              <col style={{ width: colWidths.recs }} />
              <col style={{ width: colWidths.rating }} />
              <col style={{ width: colWidths.coverage }} />
              <col />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH />
                <TH onResizeStart={e => startColResize('date', e.clientX, colWidths.date)}>{t('library.columns.date')}</TH>
                <TH onResizeStart={e => startColResize('show', e.clientX, colWidths.show)}>{t('library.columns.show')}</TH>
                <TH onResizeStart={e => startColResize('tour', e.clientX, colWidths.tour)}>{t('library.columns.tour')}</TH>
                <TH onResizeStart={e => startColResize('families', e.clientX, colWidths.families)}>{t('library.columns.families')}</TH>
                <TH align="center" onResizeStart={e => startColResize('recs', e.clientX, colWidths.recs)}>{t('library.columns.recs')}</TH>
                <TH align="center" onResizeStart={e => startColResize('rating', e.clientX, colWidths.rating)}>★</TH>
                <TH onResizeStart={e => startColResize('coverage', e.clientX, colWidths.coverage)}>{t('library.columns.coverage')}</TH>
                <TH />
              </tr>
            </thead>
            <tbody>
              {(() => {
                const vItems    = virtualizer.getVirtualItems()
                const padTop    = vItems.length > 0 ? vItems[0].start : 0
                const padBottom = vItems.length > 0 ? virtualizer.getTotalSize() - vItems[vItems.length - 1].end : 0
                return (
                  <>
                    {padTop > 0 && <tr><td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} /></tr>}
                    {vItems.map(vItem => {
                      const item = flatItems[vItem.index]
                      if (!item) return null

                      if (item.kind === 'group') {
                        return (
                          <GroupRow
                            key={`g-${item.year}`}
                            label={item.year === 'Unknown' ? t('library.empty.unknownYear') : item.year}
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

                      if (item.kind === 'show') {
                        const p = item.perf
                        const ru = rollupOf(p.recordings)
                        const multi = p.recordings.length > 1
                        const expandable = p.recordings.length > 0
                        const expanded = expandedShows.has(p.id)
                        const canonical = bestOf(p.recordings)
                        return (
                          <TR
                            key={p.id}
                            edge={p.status === 'Missing' ? 'warn' : statusTone(p.status)}
                            selected={selectedId === p.id && selectedMemberLb === null}
                            onClick={() => {
                              setSelectedId(p.id)
                              setSelectedMemberLb(null)
                              if (expandable) setExpandedShows(s => {
                                const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n
                              })
                            }}
                            onContextMenu={e => openCtxMenu(
                              e, p.disp,
                              buildPerformanceActions(p.recordings.map(toRecAction), canonical ? toRecAction(canonical) : null, actionHandlers, t),
                            )}
                            style={{ height: vItem.size }}
                          >
                            <TD
                              onClick={e => {
                                e.stopPropagation()
                                if (!expandable) return
                                setExpandedShows(s => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })
                              }}
                              style={{ overflow: 'visible', cursor: expandable ? 'pointer' : 'default' }}
                            >
                              {expandable && <Icon name={expanded ? 'chevDown' : 'chevRight'} size={13} style={{ color: 'var(--lbb-fg3)' }} />}
                            </TD>
                            <TD mono style={{ color: 'var(--lbb-fg)', fontWeight: 'var(--w-semi)' }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.2 }}>
                                <span>{p.disp}</span>
                                {p.dow && (
                                  <span style={{ fontSize: 'var(--lbb-fs-9-5)', color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                    {p.dow}
                                  </span>
                                )}
                              </span>
                            </TD>
                            <TD style={{ color: 'var(--lbb-fg)' }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.25, minWidth: 0 }}>
                                <span style={{ fontWeight: 'var(--w-semi)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {p.venue || p.city || '—'}
                                  {p.title && (
                                    <span style={{ marginLeft: 6, fontWeight: 'var(--w-med)', fontStyle: 'italic', color: 'var(--lbb-accent-mid)', fontSize: 'var(--lbb-fs-11-5)' }}>
                                      "{p.title}"
                                    </span>
                                  )}
                                  {p.confirmed === false && (
                                    <span title={t('library.tooltip.inferred')}>
                                      <Pill tone="mute" soft style={{ marginLeft: 6, fontSize: 'var(--lbb-fs-9-5)' }}>
                                        {t('library.panel.unconfirmed')}
                                      </Pill>
                                    </span>
                                  )}
                                </span>
                                {p.venue && p.city && (
                                  <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {p.city}
                                  </span>
                                )}
                              </span>
                            </TD>
                            <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>{p.tour ?? ''}</TD>
                            <TD style={{ overflow: 'visible' }}>
                              <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
                                {ru.fams.map(fam => (
                                  <Pill key={fam.id} tone={fam.owned ? 'ok' : 'mute'} soft>
                                    {fam.src ? (SRC_ABBR[fam.src] ?? fam.src) : '—'}{fam.multi ? ` ×${fam.total}` : ''}
                                  </Pill>
                                ))}
                              </span>
                            </TD>
                            <TD align="center" mono style={{ color: multi ? 'var(--lbb-fg)' : 'var(--lbb-fg3)', fontWeight: multi ? 'var(--w-bold)' : 'var(--w-med)' }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.1, alignItems: 'center' }}>
                                <span>{ru.famTotal}</span>
                                <span style={{ fontSize: 'var(--lbb-fs-9)', fontWeight: 'var(--w-med)', color: 'var(--lbb-fg3)' }}>{t('library.summary.recShort', { count: ru.total })}</span>
                              </span>
                            </TD>
                            <TD align="center">
                              {ru.bestRating !== '—'
                                ? <Pill tone={ratingTone(ru.bestRating)} soft>{ru.bestRating}</Pill>
                                : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </TD>
                            <TD style={{ overflow: 'visible' }}>
                              <Pill tone={coverageTone(ru.coverage)} soft dot={ru.coverage === 'Covered'}>
                                {coverageLabel(ru.coverage, ru.ownedCount, ru.total, t)}
                              </Pill>
                            </TD>
                            <TD />
                          </TR>
                        )
                      }

                      if (item.kind === 'fam') {
                        const { fam } = item
                        const single = !fam.multi
                        const lone = fam.members[0]
                        return (
                          <tr
                            key={`f-${item.perf.id}-${fam.id}`}
                            onClick={() => {
                              if (single && lone) { setSelectedMemberLb(lone.lbNumber); setSelectedId(null) }
                              else { setSelectedId(item.perf.id); setSelectedMemberLb(null) }
                            }}
                            onContextMenu={single && lone
                              ? e => openCtxMenu(e, lone.lb, buildRecordingActions(toRecAction(lone), [], actionHandlers, t))
                              : undefined}
                            style={{
                              height: vItem.size, cursor: 'pointer',
                              background: single && selectedMemberLb === lone?.lbNumber
                                ? 'var(--lbb-accent-soft)'
                                : fam.owned
                                  ? 'color-mix(in srgb, var(--lbb-ok-bg) 26%, transparent)'
                                  : 'color-mix(in srgb, var(--lbb-surface2) 55%, transparent)',
                            }}
                          >
                            <td style={{ width: 3, padding: 0, background: fam.owned ? 'var(--lbb-ok-bar)' : 'var(--lbb-border2)', borderBottom: '1px solid var(--lbb-border)' }} />
                            <td
                              onClick={e => { e.stopPropagation(); if (fam.multi) setCollapsedFams(s => { const n = new Set(s); const k = `${item.perf.id}::${fam.id}`; n.has(k) ? n.delete(k) : n.add(k); return n }) }}
                              style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center', cursor: fam.multi ? 'pointer' : 'default' }}
                            >
                              {fam.multi && (
                                <Icon
                                  name={collapsedFams.has(`${item.perf.id}::${fam.id}`) ? 'chevRight' : 'chevDown'}
                                  size={12} style={{ color: 'var(--lbb-fg3)' }}
                                />
                              )}
                            </td>
                            <td colSpan={4} style={{ borderBottom: '1px solid var(--lbb-border)', padding: '4px 10px', overflow: 'hidden' }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, maxWidth: '100%' }}>
                                <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', flex: '0 0 auto' }}>
                                  {fam.multi ? '├' : '└'}
                                </span>
                                <Pill tone={fam.owned ? 'ok' : 'mute'} soft>{fam.src ? (SRC_ABBR[fam.src] ?? fam.src) : '—'}</Pill>
                                {fam.tmLabel && (
                                  <span title={t('library.tooltip.tapematchGroup')}>
                                    <Pill tone="info" soft>{fam.tmLabel}</Pill>
                                  </span>
                                )}
                                {fam.needsReview && (
                                  <span title={fam.reviewReason || t('library.tooltip.tapematchReview')}>
                                    <Pill tone="warn" soft>{t('library.panel.needsReview')}</Pill>
                                  </span>
                                )}
                                {single && (
                                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', fontWeight: 'var(--w-semi)', color: fam.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                                    {lone?.lb}
                                  </span>
                                )}
                                {single && lone?.desc && (
                                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-11-5)', minWidth: 0 }}>
                                    {lone.desc}
                                  </span>
                                )}
                              </span>
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
                              {fam.multi ? `×${fam.total}` : ''}
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center' }}>
                              {fam.bestRating !== '—'
                                ? <Pill tone={ratingTone(fam.bestRating)} soft>{fam.bestRating}</Pill>
                                : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', padding: '0 var(--lbb-d-pad)', overflow: 'visible' }}>
                              {fam.owned
                                ? (fam.ownedCount < fam.total
                                    ? <Pill tone="ok" soft dot>{t('library.family.ownCount', { owned: fam.ownedCount, total: fam.total })}</Pill>
                                    : <Pill tone="ok" soft dot>{t('library.family.owned')}</Pill>)
                                : (lone?.wish ? <Pill tone="warn" soft>{t('library.family.wishlist')}</Pill> : <Pill tone="mute" soft>{t('library.family.notOwned')}</Pill>)}
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                          </tr>
                        )
                      }

                      // member
                      const { rec, isLast, isCanonical } = item
                      return (
                        <tr
                          key={`m-${item.perf.id}-${item.fam.id}-${rec.lb}`}
                          onClick={() => { setSelectedMemberLb(rec.lbNumber); setSelectedId(null) }}
                          onContextMenu={e => openCtxMenu(e, rec.lb, buildRecordingActions(toRecAction(rec), [], actionHandlers, t))}
                          style={{
                            height: vItem.size, cursor: 'pointer',
                            background: selectedMemberLb === rec.lbNumber
                              ? 'var(--lbb-accent-soft)'
                              : 'color-mix(in srgb, var(--lbb-surface2) 35%, transparent)',
                          }}
                        >
                          <td style={{ width: 3, padding: 0, background: rec.owned ? 'var(--lbb-ok-bar)' : 'transparent', borderBottom: '1px solid var(--lbb-border)' }} />
                          <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                          <TD mono dim style={{ paddingLeft: 22 }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ color: 'var(--lbb-fg3)' }}>{isLast ? '└' : '├'}</span>
                              <span style={{ color: rec.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: 'var(--w-semi)' }}>{rec.lb}</span>
                            </span>
                          </TD>
                          <TD dim colSpan={3} style={{ fontSize: 'var(--lbb-fs-11-5)' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                              {isCanonical && <Pill tone="info" soft>{t('library.family.best')}</Pill>}
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rec.desc}</span>
                              <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>{rec.src ? (SOURCE_FULL[rec.src] ?? rec.src) : '—'}</span>
                            </span>
                          </TD>
                          <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                          <TD align="center">
                            {rec.rating !== '—'
                              ? <Pill tone={ratingTone(rec.rating)} soft>{rec.rating}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                          </TD>
                          <TD style={{ overflow: 'visible' }}>
                            {rec.owned ? <Pill tone="ok" soft dot>{t('library.family.owned')}</Pill>
                              : rec.wish ? <Pill tone="warn" soft>{t('library.family.wishlist')}</Pill> : <Pill tone="mute" soft>{t('library.family.notOwned')}</Pill>}
                          </TD>
                          <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                        </tr>
                      )
                    })}
                    {padBottom > 0 && <tr><td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {loading && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
            }}>
              {t('library.empty.loading')}
            </div>
          )}

          {!loading && performances.length > 0 && filteredPerfs.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg2)' }}>{t('library.empty.nothingMatches')}</div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>{t('library.empty.tryAdjust')}</div>
              </div>
            </div>
          )}
        </div>

        {/* Detail panel — always mounted; collapses to 40px stub */}
        {(() => {
          const toggle = () => setDetailPanelOpen(o => !o)
          if (selectedMemberLb !== null) {
            const rec = rowsByLb.get(selectedMemberLb) ?? null
            return (
              <RecordingDetailPanel
                row={rec}
                history={rec ? historyMap.get(rec.lbNumber) : undefined}
                attachCount={rec ? attachCountMap.get(rec.lbNumber) : undefined}
                actionHandlers={actionHandlers}
                openMenu={openCtxMenu}
                onClose={() => setSelectedMemberLb(null)}
                open={detailPanelOpen}
                onToggle={toggle}
              />
            )
          }
          const perf = selectedId !== null ? (performances.find(p => p.id === selectedId) ?? null) : null
          const canonical = perf ? bestOf(perf.recordings) : null
          const perfFamilies = perf ? familiesOf(perf.recordings) : []
          return (
            <PerformanceDetailPanel
              perf={perf}
              recordings={(perf?.recordings ?? []) as any}
              families={perfFamilies}
              canonical={canonical as any}
              history={canonical ? historyMap.get(canonical.lbNumber) : undefined}
              attachCount={canonical ? attachCountMap.get(canonical.lbNumber) : undefined}
              actionHandlers={actionHandlers}
              openMenu={openCtxMenu}
              onClose={() => setSelectedId(null)}
              open={detailPanelOpen}
              onToggle={toggle}
            />
          )
        })()}
      </div>
    </div>
  )
}

