import { create } from 'zustand'

export type LbdirState = 'pass' | 'fail' | 'missing_files' | 'extra_files' | 'no_lbdir' | 'no_lb' | 'shntool_missing'

export interface CheckFile {
  filename:       string
  md5_status:     'pass' | 'miss' | 'na'
  on_disk:        boolean
  overall:        'pass' | 'fail' | 'missing' | 'extra'
  length?:        string
  expanded_size?: string
  cdr?:           boolean | null
  wave_problems?: string
  fmt?:           string
  ratio?:         string
}

export interface CheckResult {
  folder:            string
  lb_number:         number | null
  lbdir_found:       boolean
  lbdir_path:        string | null
  mode:              string
  status:            LbdirState
  total:             number
  pass:              number
  mismatch:          number
  missing:           number
  extra:             number
  files:             CheckFile[]
  lbdir_verified_at: string | null
}

export interface ReconcileProposal {
  disk_rel:  string
  lbdir_rel: string
  md5:       string
}

export interface SiteProposal {
  site_path: string
  lbdir_rel: string
  md5:       string
}

export interface ReconcileResult {
  folder:          string
  proposals:       ReconcileProposal[]
  unmatched_lbdir: string[]
  unmatched_disk:  string[]
  warnings:        string[]
  site_proposals:  SiteProposal[]
}

interface LbdirStore {
  activeFolder:     string | null
  filter:           string
  checkResults:     CheckResult[]
  reconcileResults: ReconcileResult[]
  reconSelected:    Set<string>
  siteSelected:     Set<string>
  setActiveFolder:     (folder: string | null) => void
  setFilter:           (v: string) => void
  setCheckResults:     (results: CheckResult[]) => void
  updateCheckResult:   (folder: string, result: CheckResult) => void
  setReconcileResults: (results: ReconcileResult[]) => void
  clearReconcileFor:   (folder: string) => void
  setReconSelected:    (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  setSiteSelected:     (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
}

export const useLbdirStore = create<LbdirStore>(set => ({
  activeFolder:     null,
  filter:           '',
  checkResults:     [],
  reconcileResults: [],
  reconSelected:    new Set(),
  siteSelected:     new Set(),
  setActiveFolder: (activeFolder) => set({ activeFolder }),
  setFilter:       (filter) => set({ filter }),
  setCheckResults: (checkResults) => set({ checkResults }),
  updateCheckResult: (folder, result) => set(state => {
    const idx = state.checkResults.findIndex(r => r.folder === folder)
    if (idx >= 0) {
      const next = [...state.checkResults]
      next[idx] = result
      return { checkResults: next }
    }
    return { checkResults: [...state.checkResults, result] }
  }),
  setReconcileResults: (reconcileResults) => set({ reconcileResults }),
  clearReconcileFor: (folder) => set(state => ({
    reconcileResults: state.reconcileResults.filter(r => r.folder !== folder),
  })),
  setReconSelected: (updater) => set(state => ({
    reconSelected: typeof updater === 'function' ? updater(state.reconSelected) : updater,
  })),
  setSiteSelected: (updater) => set(state => ({
    siteSelected: typeof updater === 'function' ? updater(state.siteSelected) : updater,
  })),
}))
