// Verify-step shared types. The standalone Verify screen (and its zustand
// store) was removed — verify now runs only as a Pipeline stage — but these
// types are still shared between the Pipeline stage content and the
// VerifyDetail table component.

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
