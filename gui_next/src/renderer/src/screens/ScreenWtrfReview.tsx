// WTRF fetch review — route /wtrfreview (curator-gated, TODO-193).
//
// Lists the latest wtrf_downloads row per LB with confidence, signals, topic
// URL(s) and tied candidates. Confirm resumes a paused-added torrent or fetches
// + adds it to qBittorrent; reject marks the row. Backend: /api/wtrf/review*.

import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Banner, Button, Pill, TableShell, TH, TR, TD } from '../components'
import { getJson, postJson } from '../lib/api'

type Filter = 'review' | 'added' | 'not_found' | 'rejected' | 'all'
const FILTERS: Filter[] = ['review', 'added', 'not_found', 'rejected', 'all']
const FILTER_KEY = {
  review: 'wtrfReview.filter.review', added: 'wtrfReview.filter.added',
  not_found: 'wtrfReview.filter.not_found', rejected: 'wtrfReview.filter.rejected',
  all: 'wtrfReview.filter.all',
} as const

interface ReviewRow {
  id: number
  lb_number: number
  topic_url: string | null
  confidence: string | null
  status: string
  error: string | null
  signals: Record<string, unknown>
  candidates: string[]
}

interface ReviewPayload {
  rows: ReviewRow[]
  total: number
  counts: Record<Filter, number>
}

interface ActionResult {
  ok: boolean
  action?: 'resumed' | 'added'
  error?: string
}

function confTone(c: string | null): 'ok' | 'info' | 'warn' | 'bad' | 'mute' {
  if (c === 'definitive' || c === 'high') return 'ok'
  if (c === 'medium') return 'info'
  if (c === 'needs_review' || c === 'ambiguous') return 'warn'
  if (c === 'not_found') return 'bad'
  return 'mute'
}

/** Compact "key=value" signal summary, minus keys shown elsewhere. */
function signalSummary(s: Record<string, unknown>): string {
  const hide = new Set(['has_torrent', 'tied_candidates', 'tied_with', 'tiebreak',
    'review', 'reviewed_at'])
  return Object.entries(s)
    .filter(([k]) => !hide.has(k))
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join('  ')
}

export function ScreenWtrfReview(): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<Filter>('review')
  const [busy, setBusy] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)

  const { data, isLoading, isError } = useQuery<ReviewPayload>({
    queryKey: ['wtrf-review', filter],
    queryFn: () => getJson<ReviewPayload>(`/api/wtrf/review?filter=${filter}&limit=500`),
  })

  const run = async (row: ReviewRow, verb: 'confirm' | 'reject', topicUrl?: string) => {
    setBusy(row.id)
    setNotice(null)
    try {
      const res = await postJson<ActionResult>(
        `/api/wtrf/review/${row.id}/${verb}`,
        verb === 'confirm' && topicUrl ? { topic_url: topicUrl } : undefined,
      )
      if (res.ok) {
        setNotice({ tone: 'ok', text: res.action === 'resumed' ? t('wtrfReview.resumed')
          : res.action === 'added' ? t('wtrfReview.added') : '' })
        await qc.invalidateQueries({ queryKey: ['wtrf-review'] })
      } else {
        setNotice({ tone: 'bad', text: `${t('wtrfReview.actionFailed')}: ${res.error ?? ''}` })
      }
    } catch (e) {
      setNotice({ tone: 'bad', text: `${t('wtrfReview.actionFailed')}: ${String(e)}` })
    } finally {
      setBusy(null)
    }
  }

  const rows = data?.rows ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        padding: '14px 16px 12px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 'auto' }}>
          <Icon name="scraper" size={16} />
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('wtrfReview.title')}
          </span>
          <span style={{ fontSize: 12, color: 'var(--lbb-fg3)' }}>{t('wtrfReview.subtitle')}</span>
        </div>
        {FILTERS.map((f) => (
          <Button
            key={f} size="sm" variant={f === filter ? 'primary' : 'ghost'}
            onClick={() => setFilter(f)}
          >
            {t(FILTER_KEY[f])}
            {data ? ` (${data.counts[f] ?? 0})` : ''}
          </Button>
        ))}
      </div>

      {notice && notice.text && (
        <div style={{ padding: '0 16px 10px' }}>
          <Banner tone={notice.tone} icon={notice.tone === 'ok' ? 'check' : 'alert'}
            title={notice.text} />
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', borderTop: '1px solid var(--lbb-border)' }}>
        <TableShell>
          <thead>
            <tr>
              <th style={{ width: 3, padding: 0, background: 'var(--lbb-surface2)' }} />
              <TH>{t('wtrfReview.colLb')}</TH>
              <TH>{t('wtrfReview.colConfidence')}</TH>
              <TH>{t('wtrfReview.colSignals')}</TH>
              <TH>{t('wtrfReview.colTopics')}</TH>
              <TH>{t('wtrfReview.colStatus')}</TH>
              <TH>{t('wtrfReview.colActions')}</TH>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pending = r.status === 'skipped' && r.candidates.length > 0
              const canConfirm = r.status === 'qbt_added' || pending
              const isBusy = busy === r.id
              return (
                <TR key={r.id} edge={confTone(r.confidence)}>
                  <TD mono style={{ color: 'var(--lbb-fg)' }}>
                    {`LB-${String(r.lb_number).padStart(5, '0')}`}
                  </TD>
                  <TD>
                    <Pill tone={confTone(r.confidence)} soft>{r.confidence ?? '—'}</Pill>
                  </TD>
                  <TD dim style={{ whiteSpace: 'normal' }}>
                    {signalSummary(r.signals) || '—'}
                    {r.signals.tiebreak ? ` · ${t('wtrfReview.tiebreak')}` : ''}
                  </TD>
                  <TD style={{ whiteSpace: 'normal' }}>
                    {r.candidates.map((u, i) => (
                      <div key={u} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <a href={u} target="_blank" rel="noreferrer"
                          title={t('wtrfReview.openTopic')}
                          style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>
                          {u.replace(/^https?:\/\/[^/]+\//, '')}
                        </a>
                        {r.candidates.length > 1 && (
                          <>
                            <span style={{ fontSize: 10, color: 'var(--lbb-fg3)' }}>
                              {t('wtrfReview.tied')} {i + 1}
                            </span>
                            {pending && (
                              <Button size="sm" variant="secondary" disabled={isBusy}
                                onClick={() => void run(r, 'confirm', u)}>
                                {t('wtrfReview.confirmAdd')}
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </TD>
                  <TD dim>{r.status}</TD>
                  <TD>
                    {canConfirm && r.status !== 'rejected' && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        {!(pending && r.candidates.length > 1) && (
                          <Button size="sm" variant="primary" disabled={isBusy}
                            onClick={() => void run(r, 'confirm', r.candidates[0])}>
                            {isBusy ? t('wtrfReview.working')
                              : r.status === 'qbt_added' ? t('wtrfReview.confirmResume')
                              : t('wtrfReview.confirmAdd')}
                          </Button>
                        )}
                        <Button size="sm" variant="danger" disabled={isBusy}
                          onClick={() => void run(r, 'reject')}>
                          {t('wtrfReview.reject')}
                        </Button>
                      </div>
                    )}
                  </TD>
                </TR>
              )
            })}
            {!rows.length && (
              <TR>
                <TD colSpan={7} dim align="center" style={{ padding: 28, whiteSpace: 'normal' }}>
                  {isLoading ? t('common.loading')
                    : isError ? t('wtrfReview.error')
                    : t('wtrfReview.empty')}
                </TD>
              </TR>
            )}
          </tbody>
        </TableShell>
      </div>
    </div>
  )
}
