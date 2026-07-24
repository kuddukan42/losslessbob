// Library filter/view state — module-scope so it survives ScreenLibrary
// unmounting on navigation (BUG-219), persisted to localStorage so the whole
// view (lens, filters, sort, grouping, collapsed years) also survives app
// restarts. Moved out of ScreenLibrary.tsx (2026-07-24, UI5 Saved Views) so the
// sidebar can APPLY a saved view by writing this store directly.

import React from 'react'
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type {
  Scope, LibStatus, RatingGrade, HealthFlag, SortKey, SortDir, RecordingFilters,
} from './libraryRows'

type PerfView = 'all' | 'owned' | 'gaps' | 'wishlist' | 'duplicates'
  | 'recommended' | 'superseded' | 'carbonbit' | 'tenhaaf' | 'curatedAny'
  | 'taperConfirmed' | 'taperReview'
type Coverage = 'Covered' | 'Upgrade' | 'Gap' | 'Undocumented'

// Setters mirror React's SetStateAction signature so existing
// toggleSet()/setX(new Set()) call sites need no change.
function withUpdater<T>(current: T, updater: React.SetStateAction<T>): T {
  return typeof updater === 'function' ? (updater as (prev: T) => T)(current) : updater
}

// Set-aware JSON round-trip for the persist storage below — the store keeps
// filter selections as Set objects, which JSON.stringify would silently
// flatten to {}.
const SET_TAG = '__lbbSet'
function setReplacer(_key: string, value: unknown): unknown {
  return value instanceof Set ? { [SET_TAG]: Array.from(value) } : value
}
function setReviver(_key: string, value: unknown): unknown {
  if (value && typeof value === 'object' && SET_TAG in (value as object)) {
    return new Set((value as Record<string, unknown[]>)[SET_TAG])
  }
  return value
}

export interface LibraryFilterStore {
  lens: 'performance' | 'recording'
  setLens: React.Dispatch<React.SetStateAction<'performance' | 'recording'>>

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
  recGroupByYear: boolean
  setRecGroupByYear: React.Dispatch<React.SetStateAction<boolean>>
  recCollapsedYears: Set<string>
  setRecCollapsedYears: React.Dispatch<React.SetStateAction<Set<string>>>
  recDetailPanelOpen: boolean
  setRecDetailPanelOpen: React.Dispatch<React.SetStateAction<boolean>>
  recSortKey: SortKey
  setRecSortKey: React.Dispatch<React.SetStateAction<SortKey>>
  recSortDir: SortDir
  setRecSortDir: React.Dispatch<React.SetStateAction<SortDir>>

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
  perfView: PerfView
  setPerfView: React.Dispatch<React.SetStateAction<PerfView>>
  perfGroupByYear: boolean
  setPerfGroupByYear: React.Dispatch<React.SetStateAction<boolean>>
  perfCollapsedYears: Set<string>
  setPerfCollapsedYears: React.Dispatch<React.SetStateAction<Set<string>>>
  perfExpandedShows: Set<string>
  setPerfExpandedShows: React.Dispatch<React.SetStateAction<Set<string>>>
  perfCollapsedFams: Set<string>
  setPerfCollapsedFams: React.Dispatch<React.SetStateAction<Set<string>>>
  perfDetailPanelOpen: boolean
  setPerfDetailPanelOpen: React.Dispatch<React.SetStateAction<boolean>>
}

export const useLibraryFilterStore = create<LibraryFilterStore>()(persist((set, get) => ({
  lens: 'performance' as const,
  setLens: (u) => set({ lens: withUpdater(get().lens, u) }),

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
  recGroupByYear: true,
  setRecGroupByYear: (u) => set({ recGroupByYear: withUpdater(get().recGroupByYear, u) }),
  recCollapsedYears: new Set(),
  setRecCollapsedYears: (u) => set({ recCollapsedYears: withUpdater(get().recCollapsedYears, u) }),
  recDetailPanelOpen: true,
  setRecDetailPanelOpen: (u) => set({ recDetailPanelOpen: withUpdater(get().recDetailPanelOpen, u) }),
  recSortKey: 'lb' as const,
  setRecSortKey: (u) => set({ recSortKey: withUpdater(get().recSortKey, u) }),
  recSortDir: 'asc' as const,
  setRecSortDir: (u) => set({ recSortDir: withUpdater(get().recSortDir, u) }),

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
  perfGroupByYear: true,
  setPerfGroupByYear: (u) => set({ perfGroupByYear: withUpdater(get().perfGroupByYear, u) }),
  perfCollapsedYears: new Set(),
  setPerfCollapsedYears: (u) => set({ perfCollapsedYears: withUpdater(get().perfCollapsedYears, u) }),
  perfExpandedShows: new Set(),
  setPerfExpandedShows: (u) => set({ perfExpandedShows: withUpdater(get().perfExpandedShows, u) }),
  perfCollapsedFams: new Set(),
  setPerfCollapsedFams: (u) => set({ perfCollapsedFams: withUpdater(get().perfCollapsedFams, u) }),
  perfDetailPanelOpen: true,
  setPerfDetailPanelOpen: (u) => set({ perfDetailPanelOpen: withUpdater(get().perfDetailPanelOpen, u) }),
}), {
  name: 'lbb-library-filters',
  storage: createJSONStorage(() => localStorage, { replacer: setReplacer, reviver: setReviver }),
}))

// ── Saved-view bridge (UI5) ────────────────────────────────────────────────────

/** Snapshot the current recording-lens filters into a serializable view. */
export function snapshotRecordingFilters(): RecordingFilters {
  const s = useLibraryFilterStore.getState()
  return {
    scope:       s.recScope,
    query:       s.recQuery,
    decade:      [...s.recActiveDecade],
    status:      [...s.recActiveStatus],
    rating:      [...s.recActiveRating],
    source:      [...s.recActiveSource],
    health:      [...s.recActiveHealth],
    sortKey:     s.recSortKey,
    sortDir:     s.recSortDir,
    groupByYear: s.recGroupByYear,
  }
}

/** Apply a saved view: switch to the recording lens and restore its filter set. */
export function applyRecordingFilters(f: RecordingFilters): void {
  useLibraryFilterStore.setState({
    lens:            'recording',
    recScope:        f.scope,
    recQuery:        f.query,
    recActiveDecade: new Set(f.decade),
    recActiveStatus: new Set(f.status),
    recActiveRating: new Set(f.rating),
    recActiveSource: new Set(f.source),
    recActiveHealth: new Set(f.health),
    recSortKey:      f.sortKey,
    recSortDir:      f.sortDir,
    recGroupByYear:  f.groupByYear,
  })
}

/** True when the recording lens currently has any non-default filter worth saving. */
export function hasRecordingFilters(): boolean {
  const s = useLibraryFilterStore.getState()
  return s.recScope !== 'all' || s.recQuery.trim() !== ''
    || s.recActiveDecade.size > 0 || s.recActiveStatus.size > 0 || s.recActiveRating.size > 0
    || s.recActiveSource.size > 0 || s.recActiveHealth.size > 0
}
