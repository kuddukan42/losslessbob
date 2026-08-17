// Full per-entry LB ledger — route /lbdir/ledger (TODO-305).
//
// Spec: instructions/design_handoff_lb_coverage_award/README.md §1 — "every LB#,
// its match state, source family, resolution note, date filed". This is the
// audit surface behind the coverage percentage on /about/coverage, so the gaps
// are rows here too, not just a number over there.
//
// Deep-linkable: ?lb=1234 lands on the page holding that entry and highlights
// it (the backend resolves the page); ?filter= and ?page= are URL state so a
// filtered view survives a reload and can be shared.

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Button, Chip, Input, Pill, TableShell, TH, TR, TD } from '../components'
import type { StatusTone } from '../components'

const BASE = window.api.flaskBase

const FILTERS = ['all', 'held', 'missing', 'unmatched', 'review'] as const
type LedgerFilter = (typeof FILTERS)[number]

type EntryState = 'verified' | 'held' | 'unmatched' | 'missing'

interface LedgerRow {
  lb_number:    number
  lb_status:    string
  date_str:     string | null
  location:     string | null
  fam_id:       string | null
  folder_name:  string | null
  filed_at:     string | null
  verified:     boolean
  needs_review: boolean
  held:         boolean
  state:        EntryState
}

interface LedgerPage {
  rows:     LedgerRow[]
  page:     number
  pages:    number
  per_page: number
  total:    number
  filter:   LedgerFilter
  q:        string
  lb:       number | null
}

const STATE_TONE: Record<EntryState, StatusTone> = {
  verified:  'ok',
  held:      'info',
  unmatched: 'warn',
  missing:   'bad',
}

const PER_PAGE = 100

function lbFolder(lb: number): string {
  return `LB-${String(lb).padStart(5, '0')}`
}

export function ScreenLbdirLedger(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()

  const filter = (FILTERS as readonly string[]).includes(params.get('filter') ?? '')
    ? (params.get('filter') as LedgerFilter)
    : 'all'
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  const q = params.get('q') ?? ''
  // Consumed once: the backend turns ?lb= into a page number, and we then drop
  // it from the URL so paging away from the deep link doesn't snap back to it.
  const deepLb = params.get('lb')

  const [draftQ, setDraftQ] = useState(q)
  useEffect(() => { setDraftQ(q) }, [q])

  const setParam = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }, [params, setParams])

  const { data, isLoading, isError } = useQuery<LedgerPage>({
    queryKey: ['lb-ledger', filter, page, q, deepLb],
    queryFn: async () => {
      const sp = new URLSearchParams({
        filter, per_page: String(PER_PAGE), page: String(page),
      })
      if (q) sp.set('q', q)
      if (deepLb) sp.set('lb', deepLb)
      const r = await fetch(`${BASE}/api/lb/coverage/ledger?${sp.toString()}`)
      if (!r.ok) throw new Error(String(r.status))
      return r.json() as Promise<LedgerPage>
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  // Once the deep link has resolved to a page, rewrite the URL to that page and
  // drop ?lb= — the row stays highlighted via `highlight` below.
  const highlight = useRef<number | null>(deepLb ? Number(deepLb) : null)
  useEffect(() => {
    if (!deepLb || !data) return
    highlight.current = Number(deepLb)
    setParam({ lb: null, page: String(data.page) })
  }, [deepLb, data, setParam])

  const rows = data?.rows ?? []
  const pages = data?.pages ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header: title + the way back to the screen that sent you here. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        padding: '14px 16px 10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 'auto' }}>
          <Icon name="lbdir" size={16} />
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('lbLedger.title')}
          </span>
          <span style={{ fontSize: 12, color: 'var(--lbb-fg3)' }}>
            {t('lbLedger.subtitle')}
          </span>
        </div>
        <Button variant="ghost" size="sm" icon="lbdir" onClick={() => navigate('/lbdir/sync')}>
          {t('lbLedger.actSync')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => navigate('/about/coverage')}>
          {t('lbLedger.actBack')}
        </Button>
      </div>

      {/* Filters + search. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        padding: '0 16px 12px', borderBottom: '1px solid var(--lbb-border)',
      }}>
        {FILTERS.map(f => (
          <Chip
            key={f}
            active={filter === f}
            onClick={() => setParam({ filter: f === 'all' ? null : f, page: null, lb: null })}
            count={filter === f ? data?.total : undefined}
          >
            {t(`lbLedger.filter.${f}`)}
          </Chip>
        ))}
        <form
          style={{ marginLeft: 'auto' }}
          onSubmit={e => { e.preventDefault(); setParam({ q: draftQ, page: null, lb: null }) }}
        >
          <Input
            icon="search"
            size="sm"
            width={240}
            placeholder={t('lbLedger.searchPlaceholder')}
            value={draftQ}
            onChange={e => setDraftQ(e.target.value)}
          />
        </form>
      </div>

      {/* Rows. */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} />
            <col style={{ width: 96 }} />
            <col style={{ width: 104 }} />
            <col />
            <col style={{ width: 120 }} />
            <col style={{ width: 132 }} />
            <col style={{ width: 108 }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ width: 3, padding: 0, background: 'var(--lbb-surface2)' }} />
              <TH>{t('lbLedger.colLb')}</TH>
              <TH>{t('lbLedger.colDate')}</TH>
              <TH>{t('lbLedger.colLocation')}</TH>
              <TH>{t('lbLedger.colFamily')}</TH>
              <TH>{t('lbLedger.colState')}</TH>
              <TH>{t('lbLedger.colFiled')}</TH>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <TR
                key={r.lb_number}
                edge={STATE_TONE[r.state]}
                selected={highlight.current === r.lb_number}
                onClick={() => navigate(`/library?lb=${r.lb_number}`)}
              >
                <TD mono style={{ color: 'var(--lbb-fg)' }}>{lbFolder(r.lb_number)}</TD>
                <TD mono>{r.date_str ?? '—'}</TD>
                <TD><span title={r.location ?? undefined}>{r.location ?? '—'}</span></TD>
                <TD mono dim><span title={r.fam_id ?? undefined}>{r.fam_id ?? '—'}</span></TD>
                <TD>
                  <Pill tone={STATE_TONE[r.state]} soft dot>
                    {t(`lbLedger.state.${r.state}`)}
                  </Pill>
                  {r.needs_review && (
                    <Pill tone="warn" soft style={{ marginLeft: 6 }}>
                      {t('lbLedger.needsReview')}
                    </Pill>
                  )}
                </TD>
                <TD mono dim>{r.filed_at ?? '—'}</TD>
              </TR>
            ))}
            {!rows.length && (
              <TR>
                <TD colSpan={6} dim align="center" style={{ padding: 28, whiteSpace: 'normal' }}>
                  {isLoading ? t('common.loading')
                    : isError ? t('lbLedger.error')
                    : t('lbLedger.empty')}
                </TD>
              </TR>
            )}
          </tbody>
        </TableShell>
      </div>

      {/* Pager. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 16px', borderTop: '1px solid var(--lbb-border)',
        fontSize: 11.5, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
      }}>
        <span>
          {t('lbLedger.countLabel', {
            count: data?.total ?? 0,
            formatted: (data?.total ?? 0).toLocaleString('en-US'),
          })}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          {t('lbLedger.pageLabel', { page: data?.page ?? 1, pages: Math.max(1, pages) })}
        </span>
        <Button
          variant="ghost" size="sm"
          disabled={(data?.page ?? 1) <= 1}
          onClick={() => setParam({ page: String((data?.page ?? 1) - 1), lb: null })}
        >
          {t('lbLedger.prev')}
        </Button>
        <Button
          variant="ghost" size="sm"
          disabled={(data?.page ?? 1) >= pages}
          onClick={() => setParam({ page: String((data?.page ?? 1) + 1), lb: null })}
        >
          {t('lbLedger.next')}
        </Button>
      </div>
    </div>
  )
}
