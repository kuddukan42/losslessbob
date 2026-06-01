import { create } from 'zustand'

export type LbdirState = 'pass' | 'fail' | 'missing_files' | 'no_lbdir' | 'no_lb' | 'shntool_missing'
export type SubTab     = 'check' | 'retrieve' | 'reconcile' | 'extras'

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
  folder:      string
  lb_number:   number | null
  lbdir_found: boolean
  lbdir_path:  string | null
  mode:        string
  status:      LbdirState
  total:       number
  pass:        number
  mismatch:    number
  missing:     number
  files:       CheckFile[]
}

export interface RetrieveResult {
  folder:    string
  lb_number: number | null
  status:    'copied' | 'scraped_and_copied' | 'not_found' | 'no_lb_number'
  msg:       string
}

export interface ReconcileProposal {
  disk_rel:  string
  lbdir_rel: string
  md5:       string
}

export interface ReconcileResult {
  folder:          string
  proposals:       ReconcileProposal[]
  unmatched_lbdir: string[]
  unmatched_disk:  string[]
  warnings:        string[]
}

export interface ExtrasResult {
  folder:    string
  extra:     string[]
  lbdir_rel: string | null
}

interface LbdirStore {
  activeFolder:     string | null
  tab:              SubTab
  filter:           string
  checkResults:     CheckResult[]
  retrieveResults:  RetrieveResult[]
  reconcileResults: ReconcileResult[]
  extrasResults:    ExtrasResult[]
  reconSelected:    Set<string>
  extrasSelected:   Set<string>
  setActiveFolder:     (folder: string | null) => void
  setTab:              (tab: SubTab) => void
  setFilter:           (v: string) => void
  setCheckResults:     (results: CheckResult[]) => void
  updateCheckResult:   (folder: string, result: CheckResult) => void
  setRetrieveResults:  (results: RetrieveResult[]) => void
  setReconcileResults: (results: ReconcileResult[]) => void
  setExtrasResults:    (results: ExtrasResult[]) => void
  setReconSelected:    (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  setExtrasSelected:   (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
}

export const useLbdirStore = create<LbdirStore>(set => ({
  activeFolder:     null,
  tab:              'check',
  filter:           '',
  checkResults:     [],
  retrieveResults:  [],
  reconcileResults: [],
  extrasResults:    [],
  reconSelected:    new Set(),
  extrasSelected:   new Set(),
  setActiveFolder: (activeFolder) => set({ activeFolder }),
  setTab:          (tab) => set({ tab }),
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
  setRetrieveResults:  (retrieveResults) => set({ retrieveResults }),
  setReconcileResults: (reconcileResults) => set({ reconcileResults }),
  setExtrasResults:    (extrasResults) => set({ extrasResults }),
  setReconSelected: (updater) => set(state => ({
    reconSelected: typeof updater === 'function' ? updater(state.reconSelected) : updater,
  })),
  setExtrasSelected: (updater) => set(state => ({
    extrasSelected: typeof updater === 'function' ? updater(state.extrasSelected) : updater,
  })),
}))
