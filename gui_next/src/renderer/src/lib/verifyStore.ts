import { create } from 'zustand'

export type FolderState = 'pass' | 'mismatch' | 'fail' | 'incomplete' | 'shntool' | 'no_checksums'
export type CheckStatus = 'pass' | 'fail' | 'miss' | 'na'

export interface FileRow {
  filename:       string
  md5_expected:   string | null
  md5_actual:     string | null
  md5_status:     CheckStatus
  ffp_expected:   string | null
  ffp_actual:     string | null
  ffp_status:     CheckStatus
  shntool_status: CheckStatus
  st5_status:     CheckStatus
  on_disk:        boolean
  overall:        'pass' | 'fail' | 'missing' | 'extra'
}

export interface VerifyFolder {
  folder:        string
  mode:          string
  status:        FolderState
  total:         number
  pass:          number
  mismatch:      number
  missing:       number
  extra:         number
  missing_types: string[]
  files:         FileRow[]
}

interface VerifyStore {
  folders:      string[]
  results:      VerifyFolder[]
  activeIdx:    number
  showAll:      boolean
  filter:       string
  setFolders:   (updater: string[] | ((prev: string[]) => string[])) => void
  setResults:   (results: VerifyFolder[]) => void
  setActiveIdx: (idx: number) => void
  setShowAll:   (v: boolean) => void
  setFilter:    (v: string) => void
}

export const useVerifyStore = create<VerifyStore>(set => ({
  folders:    [],
  results:    [],
  activeIdx:  0,
  showAll:    false,
  filter:     '',
  setFolders: (updater) => set(state => ({
    folders: typeof updater === 'function' ? updater(state.folders) : updater,
  })),
  setResults:   (results) => set({ results }),
  setActiveIdx: (activeIdx) => set({ activeIdx }),
  setShowAll:   (showAll) => set({ showAll }),
  setFilter:    (filter) => set({ filter }),
}))
