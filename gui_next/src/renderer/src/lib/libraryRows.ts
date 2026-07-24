// Shared Library recording-lens data layer.
//
// Extracted from ScreenLibrary.tsx so the same row-building and filter predicate
// power both the Library table AND the Saved Views count badges (lib/savedViewsStore
// + components/SavedViews). Keeping one source of truth means a saved view's badge
// count can never drift from what the Library would actually show for that filter set.
//
// The three underlying queries (`library-catalog`, `collection-prefetch`,
// `library-badges`) all use `staleTime: Infinity`, so calling useLibraryRows() from
// both ScreenLibrary and the sidebar shares one react-query cache — no double fetch.

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

const BASE = window.api.flaskBase

// ── Types (single source of truth; ScreenLibrary imports these) ──────────────
export type LibStatus  = 'Public' | 'Private' | 'Missing'
export type RatingGrade = 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D+' | 'D' | 'D-' | 'F' | '—'
export type Scope       = 'all' | 'owned' | 'unowned'
export type SortKey     = 'lb' | 'date' | 'rating'
export type SortDir     = 'asc' | 'desc'
export type HealthFlag  = 'Wishlist' | 'Duplicates' | 'Unconfirmed'

export interface RecordingRow {
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
  taperKnown: boolean
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
  // FABLE_UNIFIED_RANKING phase 3 (F4 Library payload pattern) — merged in
  // from /api/library/performances, same as the TapeMatch fields above:
  // never set by the recording lens's /api/search-sourced adapter.
  pickRank?: number
  absGrade?: string
  curated?: string[]
  // FABLE_TAPER_ATTRIBUTION phase 2 (F4 Library payload pattern, §5) — merged
  // in from /api/library/performances alongside the ranking fields above.
  taperConfirmed?: string
  taperPropagated?: string
  taperReview?: boolean
}

export const VALID_RATINGS = new Set(['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F'])

export const RATING_RANK: Record<string, number> = {
  'A+': 13, A: 12, 'A-': 11, 'B+': 10, B: 9, 'B-': 8, 'C+': 7, C: 6, 'C-': 5, 'D+': 4, D: 3, 'D-': 2, F: 1, '—': 0,
}

// ── Helpers ──────────────────────────────────────────────────────────────────
export function extractYear(dateStr: string): number {
  if (!dateStr) return 0
  const parts = dateStr.split('/')
  if (parts.length < 3) return 0
  const n = parseInt(parts[parts.length - 1].trim(), 10)
  if (isNaN(n)) return 0
  if (n < 100) return n >= 49 ? 1900 + n : 2000 + n
  return n
}

export function decadeOf(year: number): string {
  if (!year) return 'Unknown'
  return `${Math.floor((year % 100) / 10) * 10}s`
}

export const HEALTH_CHECK: Record<HealthFlag, (r: RecordingRow) => boolean> = {
  Wishlist:     r => r.wish,
  Duplicates:   r => r.dup,
  Unconfirmed:  r => r.owned && r.unconf,
}

// ── Row building ───────────────────────────────────────────────────────────────
// Client-side adapter merging the catalog (/api/search via library-catalog),
// the collection prefetch (ownership / wishlist / duplicates / xref), and the
// pick/quality/curated/taper badge map. Identical to the builder ScreenLibrary
// used inline before the extraction.
export function buildRecordingRows(
  catalog: unknown,
  prefetch: any,
  badgeData: any,
): RecordingRow[] {
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

  const badges = (badgeData ?? {}) as Record<string, {
    pickRank?: number; absGrade?: string; curated?: string[]
    taperConfirmed?: string; taperPropagated?: string; taperReview?: boolean
  }>

  return (catalog as any[]).map((d): RecordingRow => {
    const lbNumber = d.lb_number as number
    const owned = ownedMap.has(lbNumber)
    const own = ownedMap.get(lbNumber)
    const year = extractYear(d.date_str ?? '')
    const raw = d.rating ?? ''
    const row: RecordingRow = {
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
      taperKnown: Boolean(d.taper_known),
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
    const b = badges[lbNumber]
    if (b) {
      if (b.pickRank != null) row.pickRank = b.pickRank
      if (b.absGrade) row.absGrade = b.absGrade
      if (b.curated) row.curated = b.curated
      if (b.taperConfirmed) row.taperConfirmed = b.taperConfirmed
      if (b.taperPropagated) row.taperPropagated = b.taperPropagated
      if (b.taperReview) row.taperReview = b.taperReview
    }
    return row
  })
}

/**
 * The full merged recording-lens row set. Runs the three cached queries and the
 * builder; safe to call from any component (shared react-query cache).
 *
 * @param enabled Gate the underlying fetches. Pass `false` where the rows are
 *   only needed conditionally (e.g. the sidebar with no saved views) so new
 *   installs never pay for the catalog fetch until a view exists.
 */
export function useLibraryRows(enabled = true): RecordingRow[] {
  const { data: catalog } = useQuery({
    queryKey: ['library-catalog'],
    queryFn: () => fetch(`${BASE}/api/search`).then(r => r.json()),
    staleTime: Infinity,
    enabled,
  })
  const { data: prefetch } = useQuery({
    queryKey: ['collection-prefetch'],
    queryFn: () => fetch(`${BASE}/api/collection/prefetch`).then(r => r.json()),
    staleTime: Infinity,
    enabled,
  })
  const { data: badgeData } = useQuery({
    queryKey: ['library-badges'],
    queryFn: () => fetch(`${BASE}/api/library/badges`).then(r => r.json()),
    staleTime: Infinity,
    enabled,
  })
  return useMemo(() => buildRecordingRows(catalog, prefetch, badgeData), [catalog, prefetch, badgeData])
}

// ── Filtering ──────────────────────────────────────────────────────────────────

// The live filter shape ScreenLibrary already holds (Set-based) — the recording
// table passes its zustand store selections straight through, no per-render
// conversion on the hot path.
export interface RecordingFilterSets {
  scope: Scope
  query: string
  decade: Set<string>
  status: Set<LibStatus>
  rating: Set<RatingGrade>
  source: Set<string>
  health: Set<HealthFlag>
}

// The serializable filter set a Saved View persists. Sets become arrays so the
// view survives JSON; sortKey/sortDir/groupByYear are kept for view RESTORE
// (they do not affect the count).
export interface RecordingFilters {
  scope: Scope
  query: string
  decade: string[]
  status: LibStatus[]
  rating: RatingGrade[]
  source: string[]
  health: HealthFlag[]
  sortKey: SortKey
  sortDir: SortDir
  groupByYear: boolean
}

/** The one filter predicate — used by the Library table AND the saved-view
 *  counts, so a view's badge always matches what its table would show. */
export function filterRecordingRows(rows: RecordingRow[], f: RecordingFilterSets): RecordingRow[] {
  const q = f.query.trim().toLowerCase()
  return rows.filter(r => {
    if (f.scope === 'owned'   && !r.owned) return false
    if (f.scope === 'unowned' &&  r.owned) return false
    if (q && !`${r.lb} ${r.loc} ${r.desc}`.toLowerCase().includes(q)) return false
    if (f.decade.size > 0 && !f.decade.has(r.decade)) return false
    // Default view hides Private/Missing entries; an explicit Status selection
    // (including Private or Missing themselves) overrides this.
    if (f.status.size > 0) {
      if (!f.status.has(r.status)) return false
    } else if (r.status === 'Private' || r.status === 'Missing') {
      return false
    }
    if (f.rating.size > 0 && !f.rating.has(r.rating)) return false
    if (f.source.size > 0 && !f.source.has(r.src ?? 'Unset')) return false
    if (f.health.size > 0 && ![...f.health].some(h => HEALTH_CHECK[h](r))) return false
    return true
  })
}

/** Rehydrate a persisted (array-based) saved view into the Set-based predicate shape. */
export function filtersToSets(f: RecordingFilters): RecordingFilterSets {
  return {
    scope:  f.scope,
    query:  f.query,
    decade: new Set(f.decade),
    status: new Set(f.status),
    rating: new Set(f.rating),
    source: new Set(f.source),
    health: new Set(f.health),
  }
}

/** Live count of rows matching a saved view's filter set. */
export function countForView(rows: RecordingRow[], f: RecordingFilters): number {
  return filterRecordingRows(rows, filtersToSets(f)).length
}
