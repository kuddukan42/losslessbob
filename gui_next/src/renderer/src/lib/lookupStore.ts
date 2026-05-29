import { create } from 'zustand'

export interface LookupDetail {
  checksum:    string
  filename:    string
  type:        string
  lb_number:   number | null
  xref:        number
  status:      string
  source_file: string | null
  db_filename: string | null
  lb_status:   string | null
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
  clearSources: () => set({ sources: [], summary: null, detail: [], folderList: [] }),
  setFolderList: folders => set({ folderList: folders }),
  setFilter:     (filter) => set({ filter }),
  setFilterMy:   (filterMy) => set({ filterMy }),
  setActiveSource: (activeSource) => set({ activeSource }),
}))
