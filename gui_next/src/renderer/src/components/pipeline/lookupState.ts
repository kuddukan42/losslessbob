export type LookupState = 'matched' | 'incomplete' | 'notfound' | 'duplicate' | 'xref'

export const STATE_TONE: Record<LookupState, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; labelKey: string; color: string }> = {
  matched:    { tone: 'ok',   labelKey: 'lookup.states.matched',    color: 'var(--lbb-ok-fg)'   },
  incomplete: { tone: 'warn', labelKey: 'lookup.states.incomplete', color: 'var(--lbb-warn-fg)' },
  notfound:   { tone: 'bad',  labelKey: 'lookup.states.notfound',  color: 'var(--lbb-bad-fg)'  },
  duplicate:  { tone: 'warn', labelKey: 'lookup.states.duplicate',  color: '#a08200'             },
  xref:       { tone: 'info', labelKey: 'lookup.states.xref',       color: 'var(--lbb-info-fg)' },
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
