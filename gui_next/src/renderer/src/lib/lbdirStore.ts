// LBDIR-step shared types. The standalone LBDIR screen (and its zustand
// store) was removed — lbdir check/reconcile now runs only as a Pipeline
// stage — but these types are still shared between the Pipeline stage
// content and the LbdirDetail table component.

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
  /** What this folder's lbdir requires — differs from md5 on name matches (BUG-252). */
  expected_md5?: string
  matched_by?:   'md5' | 'name'
}

export interface SiteProposal {
  site_path:    string
  lbdir_rel:    string
  md5:          string
  expected_md5: string
  matched_by:   'md5' | 'name'
}

export interface ReconcileResult {
  folder:          string
  proposals:       ReconcileProposal[]
  unmatched_lbdir: string[]
  unmatched_disk:  string[]
  warnings:        string[]
  site_proposals:  SiteProposal[]
}
