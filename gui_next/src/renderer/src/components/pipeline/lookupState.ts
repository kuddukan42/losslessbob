export type LookupState = 'matched' | 'incomplete' | 'notfound' | 'duplicate' | 'xref'

export const STATE_TONE: Record<LookupState, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; label: string; color: string }> = {
  matched:    { tone: 'ok',   label: 'Matched',    color: 'var(--lbb-ok-fg)'   },
  incomplete: { tone: 'warn', label: 'Incomplete', color: 'var(--lbb-warn-fg)' },
  notfound:   { tone: 'bad',  label: 'Not found',  color: 'var(--lbb-bad-fg)'  },
  duplicate:  { tone: 'warn', label: 'Duplicate',  color: '#a08200'             },
  xref:       { tone: 'info', label: 'XRef',       color: 'var(--lbb-info-fg)' },
}

export function apiStatusToState(status: string): LookupState {
  if (status === 'MATCHED')               return 'matched'
  if (status === 'MATCHED (INCOMPLETE)')  return 'incomplete'
  if (status === 'INCOMPLETE')            return 'incomplete'
  if (status === 'NOT FOUND')             return 'notfound'
  if (status === 'DUPLICATE')             return 'duplicate'
  if (status === 'XREF')                  return 'xref'
  return 'notfound'
}
