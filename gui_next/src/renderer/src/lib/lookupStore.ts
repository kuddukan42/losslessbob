// Lookup-step shared types. The standalone Lookup and Rename screens (and
// the zustand store that fed them — sources, folderList, filter, etc.) were
// removed — lookup now runs only as a Pipeline stage, and quick one-off
// lookups go through Quick Lookup — but these types are still shared
// between the Pipeline stage content, the LookupDetail table component, and
// Quick Lookup.

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
