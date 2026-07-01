import React from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../Icon'
import { Button, Pill, Banner, TableShell, TH, TR, TD } from '../index'
import { LookupSummaryRow, LookupDetail as LookupDetailRow } from '../../lib/lookupStore'
import { lbDetailUrl } from '../../lib/lbUrl'
import { LookupState, STATE_TONE, apiStatusToState } from './lookupState'

export function categoryPill(cat: string | null | undefined): React.JSX.Element | null {
  if (!cat || cat === 'unknown') return null
  const tone = cat === 'concert' ? 'info' : cat === 'interview' ? 'warn' : 'mute'
  const label = cat.charAt(0).toUpperCase() + cat.slice(1)
  return <Pill tone={tone} soft>{label}</Pill>
}

export interface LookupSummaryTableProps {
  summaryRows: LookupSummaryRow[]
  /** Full (unfiltered) detail rows — used to find the alias→canonical pill for a group. */
  detail: LookupDetailRow[]
  onAddToWishlist?: (lb: number) => void
  /** When set, replaces the Open/Wishlist column with a "Pin {lb} & continue" button per row. */
  onPin?: (lb: number) => void
  pinBusyLb?: number | null
}

/** LB summary table — harvested from ScreenLookup L580-646. See design doc 14 §1. */
export function LookupSummaryTable({
  summaryRows, detail, onAddToWishlist, onPin, pinBusyLb,
}: LookupSummaryTableProps): React.JSX.Element | null {
  const { t } = useTranslation()
  if (summaryRows.length === 0) return null
  return (
    <TableShell>
      <colgroup>
        <col style={{ width: 3 }} />
        <col style={{ width: 110 }} />
        <col style={{ width: 80 }} />
        <col style={{ width: 70 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} />
        <col style={{ width: 80 }} /><col style={{ width: 70 }} /><col style={{ width: 70 }} />
        <col /><col style={{ width: onPin ? 360 : 180 }} />
      </colgroup>
      <thead>
        <tr>
          <TH> </TH>
          <TH>{t('lookup.table.lb')}</TH>
          <TH>{t('lookup.table.type')}</TH>
          <TH align="right">{t('lookup.table.given')}</TH><TH align="right">{t('lookup.table.matched')}</TH><TH align="right">{t('lookup.table.notFound')}</TH>
          <TH align="right">{t('lookup.table.missing')}</TH><TH align="right">{t('lookup.table.dups')}</TH><TH align="right">{t('lookup.table.xrefs')}</TH>
          <TH>{t('lookup.table.status')}</TH><TH align="right"> </TH>
        </tr>
      </thead>
      <tbody>
        {summaryRows.map((r, i) => {
          const state = apiStatusToState(r.status)
          const tone  = STATE_TONE[state]
          const lbStr = `LB-${String(r.lb_number).padStart(5, '0')}`
          const aliasDetail = detail.find(d => d.lb_number === r.lb_number && d.is_alias_lb)
          return (
            <TR key={i} edge={tone.tone === 'mute' ? undefined : tone.tone}>
              <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>
                {lbStr}
                {aliasDetail && aliasDetail.canonical_lb != null && (
                  <Pill tone="warn" soft style={{ marginLeft: 6 }}
                    title={`Duplicate LB — canonical: LB-${String(aliasDetail.canonical_lb).padStart(5, '0')}`}>
                    ≡ LB-{String(aliasDetail.canonical_lb).padStart(5, '0')}
                  </Pill>
                )}
              </TD>
              <TD>{categoryPill(r.lb_category)}</TD>
              <TD align="right" mono>{r.given}</TD>
              <TD align="right" mono style={{ color: r.matched      > 0 ? 'var(--lbb-ok-fg)'   : 'var(--lbb-fg3)' }}>{r.matched      || '—'}</TD>
              <TD align="right" mono style={{ color: r.not_found    > 0 ? 'var(--lbb-bad-fg)'  : 'var(--lbb-fg3)' }}>{r.not_found    || '—'}</TD>
              <TD align="right" mono style={{ color: r.missing_from_set > 0 ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)' }}>{r.missing_from_set || '—'}</TD>
              <TD align="right" mono style={{ color: r.duplicates   > 0 ? '#a08200'            : 'var(--lbb-fg3)' }}>{r.duplicates   || '—'}</TD>
              <TD align="right" mono style={{ color: r.xrefs        > 0 ? 'var(--lbb-info-fg)' : 'var(--lbb-fg3)' }}>{r.xrefs        || '—'}</TD>
              <TD><Pill tone={tone.tone} soft dot={state !== 'matched'}>{t(tone.labelKey as any)}</Pill></TD>
              <TD align="right" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <Button size="sm" variant="ghost" icon="reveal"
                  onClick={() => window.open(lbDetailUrl(r.lb_number))}
                  title={t('lookup.table.openTitle')}>
                  {t('lookup.table.open')}
                </Button>
                {onPin ? (
                  <Button size="sm" variant="primary" disabled={pinBusyLb != null}
                    onClick={() => onPin(r.lb_number)}>
                    {pinBusyLb === r.lb_number ? '…' : t('lookup.table.pinAndContinue', { lb: lbStr })}
                  </Button>
                ) : r.owned ? (
                  <Pill tone={r.lbdir_verified ? 'ok' : 'warn'} soft>
                    {r.lbdir_verified ? t('lookup.owned.badgeVerified') : t('lookup.owned.badgeOwned')}
                  </Pill>
                ) : onAddToWishlist && (
                  <Button size="sm" variant="ghost"
                    onClick={() => onAddToWishlist(r.lb_number)}>
                    {t('lookup.table.addWishlist')}
                  </Button>
                )}
              </TD>
            </TR>
          )
        })}
      </tbody>
    </TableShell>
  )
}

export interface LookupChecksumTableProps {
  summaryRows: LookupSummaryRow[]
  detailRows: LookupDetailRow[]
}

/** Grouped per-checksum detail table with xref column — harvested from ScreenLookup L658-737. */
export function LookupChecksumTable({ summaryRows, detailRows }: LookupChecksumTableProps): React.JSX.Element | null {
  const { t } = useTranslation()
  if (detailRows.length === 0) return null
  return (
    <TableShell>
      <colgroup>
        <col style={{ width: 3 }} />
        <col style={{ width: 170 }} /><col />
        <col style={{ width: 50 }} /><col style={{ width: 100 }} />
        <col style={{ width: 60 }} /><col style={{ width: 110 }} />
      </colgroup>
      <thead>
        <tr>
          <TH> </TH>
          <TH>{t('lookup.table.checksum')}</TH><TH>{t('lookup.table.filename')}</TH>
          <TH align="center">{t('lookup.table.type')}</TH><TH>{t('lookup.table.lb')}</TH>
          <TH align="center">{t('lookup.table.xref')}</TH><TH>{t('lookup.table.status')}</TH>
        </tr>
      </thead>
      <tbody>
        {(() => {
          const groupMap = new Map<string, { lbNumber: number | null; rows: LookupDetailRow[] }>()
          for (const row of detailRows) {
            const key = row.lb_number === null ? '__null__' : String(row.lb_number)
            if (!groupMap.has(key)) groupMap.set(key, { lbNumber: row.lb_number, rows: [] })
            groupMap.get(key)!.rows.push(row)
          }
          const groups = Array.from(groupMap.values())
          const multiGroup = groups.length > 1
          return groups.map((group, gi) => {
            const summRow = summaryRows.find(r => r.lb_number === group.lbNumber)
            const groupLbStr = group.lbNumber !== null ? `LB-${String(group.lbNumber).padStart(5, '0')}` : '—'
            const groupState = summRow ? apiStatusToState(summRow.status) : 'notfound'
            const groupTone = STATE_TONE[groupState]
            return (
              <React.Fragment key={group.lbNumber ?? '__null__'}>
                {multiGroup && (
                  <tr>
                    <td colSpan={7} style={{
                      padding: '10px 8px 6px',
                      background: 'var(--lbb-surface2)',
                      borderTop: gi > 0 ? '2px solid var(--lbb-border)' : undefined,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 700, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-accent-mid)' }}>
                          {groupLbStr}
                        </span>
                        {summRow && categoryPill(summRow.lb_category)}
                        <Pill tone={groupTone.tone} soft dot={groupState !== 'matched'}>{t(groupTone.labelKey as any)}</Pill>
                        <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
                          {t('lookup.status.rows', { count: group.rows.length })}
                        </span>
                      </div>
                    </td>
                  </tr>
                )}
                {group.rows.map((r, i) => {
                  const rowState = apiStatusToState(r.status)
                  const rowTone = STATE_TONE[rowState]
                  const rowLbStr = r.lb_number !== null ? `LB-${String(r.lb_number).padStart(5, '0')}` : '—'
                  return (
                    <TR key={`${gi}-${i}`} edge={rowTone.tone === 'mute' ? undefined : rowTone.tone}>
                      <TD mono dim>{r.checksum.slice(0, 12)}…</TD>
                      <TD mono style={{ color: 'var(--lbb-fg)' }}>{r.filename}</TD>
                      <TD align="center" mono style={{ color: 'var(--lbb-fg3)' }}>{r.type}</TD>
                      <TD mono style={{ color: r.lb_number !== null ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: r.lb_number !== null ? 600 : 400 }}>
                        {rowLbStr}
                      </TD>
                      <TD align="center">
                        {r.xref > 0
                          ? <Icon name="check" size={11} style={{ color: 'var(--lbb-info-fg)' }} />
                          : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                      </TD>
                      <TD><Pill tone={rowTone.tone} soft>{t(rowTone.labelKey as any)}</Pill></TD>
                    </TR>
                  )
                })}
              </React.Fragment>
            )
          })
        })()}
      </tbody>
    </TableShell>
  )
}

/** "New entry or checksum mismatch?" hint banner — harvested from ScreenLookup L739-752. */
export function LookupNotFoundHint({ style }: { style?: React.CSSProperties }): React.JSX.Element {
  const { t } = useTranslation()
  return (
    <Banner tone="info" icon="info" title={`${t('lookup.states.notfound')}?`} style={style}>
      {t('lookup.notFoundHint')}
    </Banner>
  )
}

export interface LookupDetailProps {
  summaryRows: LookupSummaryRow[]
  detailRows: LookupDetailRow[]
  onPin?: (lb: number) => void
  pinBusyLb?: number | null
}

/**
 * Combined summary + checksum tables + not-found hint, with no section headers —
 * used by the pipeline Lookup stage panel. See design doc 14 §2.2.
 */
export function LookupDetail({ summaryRows, detailRows, onPin, pinBusyLb }: LookupDetailProps): React.JSX.Element {
  return (
    <>
      <LookupSummaryTable summaryRows={summaryRows} detail={detailRows} onPin={onPin} pinBusyLb={pinBusyLb} />
      {summaryRows.length > 0 && detailRows.length > 0 && <div style={{ height: 14 }} />}
      <LookupChecksumTable summaryRows={summaryRows} detailRows={detailRows} />
      {(detailRows.length === 0 || summaryRows.length === 0) && (
        <LookupNotFoundHint style={{ marginTop: 14 }} />
      )}
    </>
  )
}
