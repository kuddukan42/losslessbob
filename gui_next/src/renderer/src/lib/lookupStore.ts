import { create } from 'zustand'

export interface LookupDetail {
  checksum:       string
  filename:       string
  type:           string
  lb_number:      number | null
  xref:           number
  status:         string
  source_file:    string | null
  db_filename:    string | null
  lb_status:      string | null
  lb_category:    string | null
  owned:          boolean
  lbdir_verified: boolean
  is_alias_lb:    boolean
  canonical_lb:   number | null
}

/** One `(lb, xref)` fileset group touched by the lookup input (FABLE_XREF_INCORPORATION.md D1). */
export interface LookupXrefGroup {
  xref:    number
  given:   number
  matched: number
  missing: number
}

export interface LookupSummaryRow {
  lb_number:          number
  given:              number
  matched:            number
  not_found:          number
  missing_from_set:   number
  duplicates:         number
  xrefs:              number
  status:             string
  lb_status:          string | null
  lb_category:        string | null
  owned:              boolean
  lbdir_verified:     boolean
  /** Winning fileset id for this copy — 0 = canonical fileset (D1). */
  matched_xref:       number
  /** Every `(lb, xref)` group the input touched; `matched_xref` is the group with fewest missing. */
  xref_groups:        LookupXrefGroup[]
}

export interface LookupSummary {
  lb_summary:       LookupSummaryRow[]
  matched:          number
  given:            number
  lb_numbers_found: number[]
}

export interface LookupSource {
  kind:    'folder' | 'file' | 'listbox' | 'clipboard'
  name:    string
  content: string
  active:  boolean
  path?:   string  // full filesystem path, set for folder/file sources
}

export type LookupFilterState = 'matched' | 'incomplete' | 'notfound' | 'duplicate' | 'xref'

interface LookupStoreState {
  sources:      LookupSource[]
  summary:      LookupSummary | null
  detail:       LookupDetail[]
  folderList:   string[]
  filter:       LookupFilterState | 'all'
  filterMy:     boolean
  activeSource: number | null
  setResult:     (summary: LookupSummary, detail: LookupDetail[]) => void
  addSource:     (src: LookupSource) => void
  removeSource:  (idx: number) => void
  clearSources:  () => void
  setFolderList: (folders: string[]) => void
  setFilter:     (v: LookupFilterState | 'all') => void
  setFilterMy:   (v: boolean) => void
  setActiveSource: (idx: number | null) => void
}

export const useLookupStore = create<LookupStoreState>(set => ({
  sources:      [],
  summary:      null,
  detail:       [],
  folderList:   [],
  filter:       'all',
  filterMy:     true,
  activeSource: null,
  setResult:    (summary, detail) => set({ summary, detail }),
  addSource:    src => set(state => ({
    sources: [...state.sources, src],
  })),
  removeSource: idx => set(state => ({
    sources: state.sources.filter((_, i) => i !== idx),
    activeSource: state.activeSource === idx ? null
      : state.activeSource !== null && state.activeSource > idx ? state.activeSource - 1
      : state.activeSource,
  })),
  clearSources: () => set({ sources: [], summary: null, detail: [], folderList: [] }),
  setFolderList: folders => set({ folderList: folders }),
  setFilter:     (filter) => set({ filter }),
  setFilterMy:   (filterMy) => set({ filterMy }),
  setActiveSource: (activeSource) => set({ activeSource }),
}))
