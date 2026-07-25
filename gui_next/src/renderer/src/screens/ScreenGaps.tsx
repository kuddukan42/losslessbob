// Gaps view (PLATFORM_ROADMAP §3, TODO-256) — Les Kokay's uncirculated-shows
// list as a self-updating grid: every known Dylan concert date becomes a
// cell, colored by whether a recording circulates. Read-only end to end —
// no writes, no derived table; backend/gap_analysis.py computes coverage
// live per request. See instructions/FABLE_GAPS_VIEW.md.

import React, { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Chip, Pill } from '../components'

const BASE = window.api.flaskBase

/**
 * Fetch JSON from the backend, failing loudly on non-2xx.
 *
 * `fetch().then(r => r.json())` swallows two distinct failures: a 5xx that
 * returns an HTML error page (json() throws a parse error) and a 4xx that
 * returns a JSON body (parsed as if it were data). Both must reject so the
 * caller's error branch renders instead of an endless loading state.
 *
 * @param path Backend path, e.g. `/api/gaps/summary`.
 * @returns Parsed JSON body typed as `T`.
 * @throws Error when the response status is not ok.
 */
async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

// ── Types (mirror backend/gap_analysis.py route shapes) ──────────────────────

type Coverage = 'covered' | 'partial' | 'gap' | 'future'

interface YearStats {
  year: number
  shows: number
  covered: number
  partial: number
  gap: number
  future: number
}

interface SummaryResponse {
  available: boolean
  generated_at: string
  totals: Partial<Record<'shows' | 'covered' | 'partial' | 'gap' | 'future', number>>
  years: YearStats[]
}

interface OlofEventRow {
  event_id: number
  venue: string
  city: string
  region: string
  country: string
  tour_name: string
  event_type: string
  recording_kind: string
  recording_mins: number | null
}

interface DateCell {
  date_iso: string
  coverage: Coverage
  events: OlofEventRow[]
  lb_numbers: number[]
  partial_lb_numbers: number[]
}

interface YearDetailResponse {
  dates: DateCell[]
}

interface FullOlofEventRow extends OlofEventRow {
  session_title?: string
  lineup?: string
  recording_info?: string
  notes?: string
  bobtalk?: string
}

interface EntryRow {
  lb_number: number
  date_str: string
  rating: string | null
  status: string
  taper_name: string | null
}

interface FamilyRow {
  lb_number: number
  fam_id: string
  run_id: string | null
}

interface DateDetailResponse {
  available: boolean
  date_iso: string
  events: FullOlofEventRow[]
  entries: EntryRow[]
  partial_entries: EntryRow[]
  recording_families: FamilyRow[]
}

// ── Coverage -> visual tone (spec §D3: covered/dim, partial/mid, gap/warm-alert) ──

const COVERAGE_TONE: Record<Coverage, 'mute' | 'info' | 'warn'> = {
  covered: 'mute',
  partial: 'info',
  gap: 'warn',
  future: 'mute',
}

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

function fmtDateLong(dateIso: string): string {
  const d = new Date(`${dateIso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return dateIso
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

// ── Decade strip ───────────────────────────────────────────────────────────────

function DecadeStrip({
  years, selectedDecade, onSelect,
}: {
  years: YearStats[]
  selectedDecade: number | null
  onSelect: (decade: number | null) => void
}) {
  const { t } = useTranslation()
  const decades = useMemo(() => {
    const byDecade = new Map<number, number>()
    for (const y of years) {
      const decade = Math.floor(y.year / 10) * 10
      byDecade.set(decade, (byDecade.get(decade) ?? 0) + y.gap)
    }
    return [...byDecade.entries()].sort((a, b) => a[0] - b[0])
  }, [years])

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', gap: 6, padding: '10px 20px',
      borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
    }}>
      <Chip size="sm" active={selectedDecade === null} onClick={() => onSelect(null)}>
        {t('gaps.decades.all')}
      </Chip>
      {decades.map(([decade, gapCount]) => (
        <Chip
          key={decade}
          size="sm"
          active={selectedDecade === decade}
          onClick={() => onSelect(decade)}
        >
          {decade}s
          {gapCount > 0 && (
            <span style={{ marginLeft: 4, opacity: 0.65 }}>({gapCount})</span>
          )}
        </Chip>
      ))}
    </div>
  )
}

// ── One date cell ──────────────────────────────────────────────────────────────

function DateCellButton({
  cell, selected, onSelect,
}: {
  cell: DateCell
  selected: boolean
  onSelect: (dateIso: string) => void
}) {
  const tone = COVERAGE_TONE[cell.coverage]
  const isFuture = cell.coverage === 'future'
  const label = cell.events.map(e => e.venue || e.city).filter(Boolean).join(' / ')
  return (
    <button
      type="button"
      title={`${cell.date_iso}${label ? ` — ${label}` : ''}`}
      onClick={() => onSelect(cell.date_iso)}
      style={{
        width: 14, height: 14, borderRadius: 3, padding: 0, cursor: 'pointer',
        background: isFuture ? 'transparent' : `var(--lbb-${tone}-bg)`,
        border: selected
          ? '2px solid var(--lbb-accent-mid)'
          : `1px solid ${isFuture ? 'var(--lbb-border2)' : `var(--lbb-${tone}-fg)`}`,
        opacity: isFuture ? 0.5 : 1,
        boxSizing: 'border-box', flex: '0 0 auto',
      }}
    />
  )
}

// ── One year row ─────────────────────────────────────────────────────────────

function YearRow({
  year, stats, selectedDate, onSelectDate,
}: {
  year: number
  stats: YearStats
  selectedDate: string | null
  onSelectDate: (dateIso: string) => void
}) {
  const { t } = useTranslation()
  const { data, isError } = useQuery<YearDetailResponse>({
    queryKey: ['gaps-year', year],
    queryFn: () => fetchJson<YearDetailResponse>(`/api/gaps/year/${year}`),
    staleTime: 60_000,
  })
  const dates = data?.dates ?? []

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '5px 20px' }}>
      <div style={{
        width: 44, flex: '0 0 44px', fontFamily: 'var(--lbb-mono)',
        fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg3)',
        paddingTop: 1,
      }}>
        {year}
      </div>
      <div style={{
        flex: 1, minWidth: 0, display: 'flex', flexWrap: 'wrap', gap: 3,
      }}>
        {dates.length === 0 ? (
          <span style={{
            fontSize: 'var(--lbb-fs-10-5)',
            color: isError ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)',
          }}>
            {t(isError ? 'gaps.grid.error' : 'gaps.grid.loading')}
          </span>
        ) : dates.map(cell => (
          <DateCellButton
            key={cell.date_iso}
            cell={cell}
            selected={cell.date_iso === selectedDate}
            onSelect={onSelectDate}
          />
        ))}
      </div>
      <div style={{
        flex: '0 0 auto', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)',
        fontVariantNumeric: 'tabular-nums', paddingTop: 1,
      }}>
        {t('gaps.grid.yearGap', { count: stats.gap })}
      </div>
    </div>
  )
}

// ── Detail pane (tab group — §6 will add a "Family tree" tab) ────────────────

type DetailTab = 'event'

function EntryList({ entries, onOpenLb }: { entries: EntryRow[]; onOpenLb: (lb: number) => void }) {
  const { t } = useTranslation()
  if (entries.length === 0) {
    return <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11-5)' }}>{t('gaps.detail.none')}</span>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {entries.map(e => (
        <div key={e.lb_number} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-11-5)' }}>
          <button
            type="button"
            onClick={() => onOpenLb(e.lb_number)}
            style={{
              fontFamily: 'var(--lbb-mono)', background: 'none', border: 'none',
              padding: 0, color: 'var(--lbb-accent-mid)', cursor: 'pointer',
            }}
          >
            {fmtLb(e.lb_number)}
          </button>
          {e.rating && <Pill tone="mute" soft>{e.rating}</Pill>}
          {e.status !== 'ok' && <Pill tone="warn" soft>{e.status}</Pill>}
          {e.taper_name && <span style={{ color: 'var(--lbb-fg3)' }}>{e.taper_name}</span>}
        </div>
      ))}
    </div>
  )
}

function DetailPane({
  dateIso, onOpenLb,
}: {
  dateIso: string | null
  onOpenLb: (lb: number) => void
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<DetailTab>('event')

  const { data, isLoading, isError, refetch } = useQuery<DateDetailResponse>({
    queryKey: ['gaps-date', dateIso],
    queryFn: () => fetchJson<DateDetailResponse>(`/api/gaps/date/${dateIso}`),
    enabled: !!dateIso,
  })

  return (
    <aside style={{
      width: 360, flex: '0 0 360px', borderLeft: '1px solid var(--lbb-border)',
      background: 'var(--lbb-surface)', display: 'flex', flexDirection: 'column', minHeight: 0,
    }}>
      {!dateIso ? (
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', gap: 10, color: 'var(--lbb-fg3)', padding: 20, textAlign: 'center',
        }}>
          <Icon name="lookup" size={28} style={{ opacity: 0.15 }} />
          <span style={{ fontSize: 'var(--lbb-fs-12-5)' }}>{t('gaps.detail.noSelection')}</span>
        </div>
      ) : (
        <>
          <div style={{
            display: 'flex', gap: 4, padding: '10px 16px 0',
            borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
          }}>
            <button
              type="button"
              onClick={() => setTab('event')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 10px 10px', background: 'transparent', border: 'none',
                borderBottom: '2px solid var(--lbb-accent-mid)', marginBottom: -1,
                fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg)',
                cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              {t('gaps.detail.tabEvent')}
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700 }}>
              {fmtDateLong(dateIso)}
            </div>

            {isError ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ color: 'var(--lbb-warn-fg)', fontSize: 'var(--lbb-fs-11-5)' }}>
                  {t('gaps.detail.error')}
                </span>
                <RetryButton onClick={() => { void refetch() }} />
              </div>
            ) : isLoading || !data ? (
              <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11-5)' }}>{t('common.loading')}</span>
            ) : (
              <>
                <div>
                  <div style={{
                    fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.04em',
                    textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                  }}>
                    {t('gaps.detail.eventsHeading')}
                  </div>
                  {data.events.length === 0 ? (
                    <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11-5)' }}>{t('gaps.detail.none')}</span>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {data.events.map(ev => (
                        <div key={ev.event_id} style={{
                          border: '1px solid var(--lbb-border)', borderRadius: 6, padding: 10,
                          fontSize: 'var(--lbb-fs-11-5)', display: 'flex', flexDirection: 'column', gap: 4,
                        }}>
                          <div style={{ fontWeight: 600 }}>
                            {ev.venue || t('gaps.detail.unknownVenue')}
                          </div>
                          <div style={{ color: 'var(--lbb-fg3)' }}>
                            {[ev.city, ev.region, ev.country].filter(Boolean).join(', ')}
                          </div>
                          {ev.tour_name && <div style={{ color: 'var(--lbb-fg3)' }}>{ev.tour_name}</div>}
                          {ev.recording_kind && (
                            <div style={{ color: 'var(--lbb-fg3)' }}>
                              {t('gaps.detail.recording', {
                                kind: ev.recording_kind,
                                mins: ev.recording_mins ?? '?',
                              })}
                            </div>
                          )}
                          {ev.notes && <div style={{ color: 'var(--lbb-fg2)' }}>{ev.notes}</div>}
                          {ev.bobtalk && (
                            <div style={{ color: 'var(--lbb-fg3)', fontStyle: 'italic' }}>{ev.bobtalk}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div style={{
                    fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.04em',
                    textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                  }}>
                    {t('gaps.detail.entriesHeading')}
                  </div>
                  <EntryList entries={data.entries} onOpenLb={onOpenLb} />
                </div>

                {data.partial_entries.length > 0 && (
                  <div>
                    <div style={{
                      fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.04em',
                      textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                    }}>
                      {t('gaps.detail.partialEntriesHeading')}
                    </div>
                    <EntryList entries={data.partial_entries} onOpenLb={onOpenLb} />
                  </div>
                )}

                {data.recording_families.length > 0 && (
                  <div>
                    <div style={{
                      fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.04em',
                      textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                    }}>
                      {t('gaps.detail.familiesHeading')}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {data.recording_families.map(f => (
                        <Pill key={f.lb_number} tone="mute" soft title={fmtLb(f.lb_number)}>
                          {f.fam_id}
                        </Pill>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </aside>
  )
}

// ── Empty state (olof_events absent) ──────────────────────────────────────────

function RetryButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '5px 12px', borderRadius: 6,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg)',
        cursor: 'pointer', fontFamily: 'inherit',
      }}
    >
      {t('gaps.error.retry')}
    </button>
  )
}

/**
 * Terminal error state for the whole screen — the summary request failed, so
 * there is no year list to render. Kept visually distinct from
 * `GapsUnavailable`, which means the chronology genuinely isn't installed;
 * conflating the two told users their data was missing when the backend was
 * merely unreachable.
 */
function GapsError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 12, padding: 40, textAlign: 'center',
    }}>
      <Icon name="x" size={36} style={{ opacity: 0.2, color: 'var(--lbb-warn-fg)' }} />
      <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, maxWidth: 420 }}>
        {t('gaps.error.title')}
      </span>
      <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', maxWidth: 420 }}>
        {t('gaps.error.detail')}
      </span>
      <RetryButton onClick={onRetry} />
    </div>
  )
}

function GapsUnavailable() {
  const { t } = useTranslation()
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 12, color: 'var(--lbb-fg3)', padding: 40, textAlign: 'center',
    }}>
      <Icon name="lookup" size={36} style={{ opacity: 0.15 }} />
      <span style={{ fontSize: 'var(--lbb-fs-13)', maxWidth: 420 }}>{t('gaps.unavailable')}</span>
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenGaps(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [selectedDecade, setSelectedDecade] = useState<number | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const { data: summary, isLoading, isError, refetch } = useQuery<SummaryResponse>({
    queryKey: ['gaps-summary'],
    queryFn: () => fetchJson<SummaryResponse>('/api/gaps/summary'),
    staleTime: 60_000,
  })
  const years = summary?.years ?? []
  const visibleYears = selectedDecade === null
    ? years
    : years.filter(y => Math.floor(y.year / 10) * 10 === selectedDecade)

  const openLb = (lb: number) => navigate(`/library?lb=${lb}`)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="gaps" size={18} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('gaps.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('gaps.subtitle')}
          </div>
        </div>
        {summary?.available && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Pill tone="mute" soft>{t('gaps.header.totalShows', { count: summary.totals.shows ?? 0 })}</Pill>
            <Pill tone="warn" soft>{t('gaps.header.totalGaps', { count: summary.totals.gap ?? 0 })}</Pill>
          </div>
        )}
      </div>

      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)' }}>
          {t('common.loading')}
        </div>
      ) : isError ? (
        <GapsError onRetry={() => { void refetch() }} />
      ) : !summary?.available ? (
        <GapsUnavailable />
      ) : (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
            <DecadeStrip years={years} selectedDecade={selectedDecade} onSelect={setSelectedDecade} />
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
              {visibleYears.map(y => (
                <YearRow
                  key={y.year}
                  year={y.year}
                  stats={y}
                  selectedDate={selectedDate}
                  onSelectDate={setSelectedDate}
                />
              ))}
            </div>
            <div style={{
              padding: '8px 20px', borderTop: '1px solid var(--lbb-border)',
              fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', flexShrink: 0,
            }}>
              {t('gaps.credit')}
            </div>
          </section>

          <DetailPane dateIso={selectedDate} onOpenLb={openLb} />
        </div>
      )}
    </div>
  )
}
