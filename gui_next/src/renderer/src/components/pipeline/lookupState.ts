// Per FABLE_XREF_INCORPORATION.md D1: copy-level xref is a dimension
// (`matched_xref > 0`), never a status — there is no "XREF" member here.
export type LookupState = 'matched' | 'incomplete' | 'notfound' | 'duplicate'

export const STATE_TONE: Record<LookupState, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; labelKey: string; color: string }> = {
  matched:    { tone: 'ok',   labelKey: 'lookup.states.matched',    color: 'var(--lbb-ok-fg)'   },
  incomplete: { tone: 'warn', labelKey: 'lookup.states.incomplete', color: 'var(--lbb-warn-fg)' },
  notfound:   { tone: 'bad',  labelKey: 'lookup.states.notfound',  color: 'var(--lbb-bad-fg)'  },
  duplicate:  { tone: 'warn', labelKey: 'lookup.states.duplicate',  color: '#a08200'             },
}

export function apiStatusToState(status: string): LookupState {
  if (status === 'MATCHED')               return 'matched'
  if (status === 'MATCHED (INCOMPLETE)')  return 'incomplete'
  if (status === 'INCOMPLETE')            return 'incomplete'
  if (status === 'NOT FOUND')             return 'notfound'
  if (status === 'DUPLICATE')             return 'duplicate'
  return 'notfound'
}

// ── Copy-level xref (D4) ──────────────────────────────────────────────────────
// Augments the status pill above — never replaces it. Fires from `matched_xref > 0`
// (live lookup) or the persisted `my_collection.xref` (collection views).

/** Tone for the copy-level "xref fileset" pill — kept separate from STATE_TONE
 *  since it is not a lookup status. */
export const XREF_TONE = { tone: 'info' as const, color: 'var(--lbb-info-fg)' }

/** Formats a fileset id as the site's `xref-NNNNN` tag (5-digit padding, matching
 *  Jeff's site-file naming `LBF-00002-xref-00961`). */
export function formatXrefTag(xrefId: number): string {
  return `xref-${String(xrefId).padStart(5, '0')}`
}
