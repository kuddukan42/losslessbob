// TapeMatch screen v1 (LISTENING §1 / TODO-170) — read-only review surface for
// the TapeMatch acoustic-matching pipeline: pick a concert date, inspect its
// pairwise similarity matrix and inferred families, and read the crawl's
// analysis.md verdict. No run controls, no pair-correction actions — those
// stay in the tools/tapematch CLI workflow; this screen is observation only.

import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Pill, Chip, Input } from '../components'
import { TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

// ── Types (mirror backend/app.py tapematch_* route shapes) ───────────────────

interface DateRow {
  date: string
  run_id: string | null
  n_lbs: number
  n_pairs: number
  has_analysis: boolean | null
  needs_review: boolean | null
  location: string | null
}

interface PairRow {
  lb_a: number
  lb_b: number
  corr: number | null
  emb_score: number | null
  fp_score: number | null
  same_family: boolean
  similarity_pct: number | null
}

interface FamilyRow {
  lb_number: number
  fam_id: string // deterministic '<date>#<n>' from tapematch_sync, not numeric
  concert_date: string
  fam_label: string | null
}

interface CrawlStatus {
  running: boolean
  pid: number | null
  runs_on_disk: number
  distinct_dates: number
  log_tail: string[]
}

type ViewFilter = 'all' | 'conflicts' | 'no_analysis'

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

// ── Header crawl status strip ─────────────────────────────────────────────────

function CrawlStatusStrip({ status }: { status: CrawlStatus | undefined }) {
  const { t } = useTranslation()
  if (!status) return null
  const tone = status.running ? 'ok' : 'mute'
  const label = status.running ? t('tapematch.crawl.running') : t('tapematch.crawl.idle')
  const tooltip = status.log_tail?.length
    ? status.log_tail.join('\n')
    : t('tapematch.crawl.noLog')
  return (
    <span
      title={tooltip}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}
    >
      <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
        {t('tapematch.crawl.label')}
      </span>
      <Pill tone={tone} soft dot>{label}</Pill>
      <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
        {t('tapematch.crawl.counts', {
          runs: status.runs_on_disk.toLocaleString(),
          dates: status.distinct_dates.toLocaleString(),
        })}
      </span>
    </span>
  )
}

// ── Left rail — dates list ────────────────────────────────────────────────────

function DateRail({
  dates, view, onViewChange, selectedDate, onSelect, isLoading,
}: {
  dates: DateRow[]
  view: ViewFilter
  onViewChange: (v: ViewFilter) => void
  selectedDate: string | null
  onSelect: (date: string) => void
  isLoading: boolean
}) {
  const { t } = useTranslation()
  return (
    <aside style={{
      width: 260, flex: '0 0 260px',
      background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', minHeight: 0,
    }}>
      <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <Icon name="tapematch" size={13} style={{ color: 'var(--lbb-fg3)' }} />
          <span style={{
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
            letterSpacing: 0.1, textTransform: 'uppercase',
          }}>{t('tapematch.rail.dates')}</span>
          <span style={{
            marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600,
            color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums',
          }}>{dates.length}</span>
        </div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          <Chip size="sm" active={view === 'all'} onClick={() => onViewChange('all')}>
            {t('tapematch.rail.viewAll')}
          </Chip>
          <Chip size="sm" active={view === 'conflicts'} onClick={() => onViewChange('conflicts')}>
            {t('tapematch.rail.viewConflicts')}
          </Chip>
          <Chip size="sm" active={view === 'no_analysis'} onClick={() => onViewChange('no_analysis')}>
            {t('tapematch.rail.viewNoAnalysis')}
          </Chip>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
        {isLoading ? (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
            {t('common.loading')}
          </div>
        ) : dates.length === 0 ? (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
            {t('tapematch.rail.noMatches')}
          </div>
        ) : dates.map(d => {
          const active = d.date === selectedDate
          return (
            <button
              key={d.date}
              type="button"
              onClick={() => onSelect(d.date)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 10px', marginBottom: 1,
                border: '1px solid transparent', borderRadius: 6,
                background: active ? 'var(--lbb-accent-soft)' : 'transparent',
                color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--lbb-surface2)' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600, flex: '0 0 auto' }}>
                {d.date}
              </span>
              <span style={{
                fontSize: 'var(--lbb-fs-10-5)', color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
                fontVariantNumeric: 'tabular-nums', flex: '0 0 auto',
              }}>
                {d.n_lbs}
              </span>
              {d.needs_review === true && (
                <Icon name="alert" size={11} style={{ color: 'var(--lbb-warn-fg)', flex: '0 0 auto' }} />
              )}
              {d.has_analysis === true && (
                <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-fg)', flex: '0 0 auto', marginLeft: 'auto' }} />
              )}
            </button>
          )
        })}
      </div>
    </aside>
  )
}

// ── Similarity matrix ─────────────────────────────────────────────────────────

function SimilarityMatrix({ pairs, isLoading }: { pairs: PairRow[]; isLoading: boolean }) {
  const { t } = useTranslation()

  const axis = useMemo(() => {
    const s = new Set<number>()
    pairs.forEach(p => { s.add(p.lb_a); s.add(p.lb_b) })
    return Array.from(s).sort((a, b) => a - b)
  }, [pairs])

  const pairMap = useMemo(() => {
    const m = new Map<string, PairRow>()
    pairs.forEach(p => {
      m.set(`${p.lb_a}:${p.lb_b}`, p)
      m.set(`${p.lb_b}:${p.lb_a}`, p)
    })
    return m
  }, [pairs])

  if (isLoading) {
    return (
      <div style={{ padding: '16px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
        {t('common.loading')}
      </div>
    )
  }
  if (axis.length === 0) {
    return (
      <div style={{ padding: '16px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
        {t('tapematch.matrix.empty')}
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <TableShell stickyHeader={false}>
        <colgroup>
          <col style={{ width: 3 }} />
          <col style={{ width: 100 }} />
          {axis.map(lb => <col key={lb} style={{ width: 64 }} />)}
        </colgroup>
        <thead>
          <tr>
            <TH />
            <TH align="right">{t('tapematch.matrix.header')}</TH>
            {axis.map(lb => <TH key={lb} align="right">{lb}</TH>)}
          </tr>
        </thead>
        <tbody>
          {axis.map(rowLb => (
            <TR key={rowLb}>
              <TD mono align="right">{rowLb}</TD>
              {axis.map(colLb => {
                if (colLb === rowLb) {
                  return (
                    <TD key={colLb} align="right" mono dim>—</TD>
                  )
                }
                const pair = pairMap.get(`${rowLb}:${colLb}`)
                if (!pair || pair.similarity_pct == null) {
                  return (
                    <TD key={colLb} align="right" mono dim>{t('tapematch.matrix.noContact')}</TD>
                  )
                }
                const pct = pair.similarity_pct
                const tooltip = t('tapematch.matrix.cellTooltip', {
                  corr: pair.corr != null ? pair.corr.toFixed(2) : '—',
                  emb: pair.emb_score != null ? pair.emb_score.toFixed(2) : '—',
                  fp: pair.fp_score != null ? pair.fp_score.toFixed(2) : '—',
                  sameFamily: pair.same_family ? t('common.yes') : t('common.no'),
                })
                return (
                  <TD
                    key={colLb}
                    align="right"
                    mono
                    style={{
                      background: `color-mix(in srgb, var(--lbb-accent-mid) ${Math.round(pct * 0.55)}%, var(--lbb-surface))`,
                      color: pct >= 50 ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
                      fontWeight: pair.same_family ? 700 : 400,
                    }}
                  >
                    <span title={tooltip}>{pct}</span>
                  </TD>
                )
              })}
            </TR>
          ))}
        </tbody>
      </TableShell>
    </div>
  )
}

// ── Analysis collapsible section ──────────────────────────────────────────────

function AnalysisSection({ date, open, onToggle }: { date: string; open: boolean; onToggle: () => void }) {
  const { t } = useTranslation()
  const { data, isFetching } = useQuery({
    queryKey: ['tapematch-analysis', date],
    queryFn: () => fetch(`${BASE}/api/tapematch/analysis?date=${encodeURIComponent(date)}`).then(r => r.json()),
    enabled: open,
    staleTime: 30_000,
  })

  return (
    <div style={{ marginTop: 4 }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 0', border: 'none', borderTop: '1px solid var(--lbb-border)',
          background: 'transparent', color: 'var(--lbb-fg2)', cursor: 'pointer',
          fontFamily: 'inherit', fontSize: 'var(--lbb-fs-12-5)', fontWeight: 600,
          textAlign: 'left',
        }}
      >
        <Icon name={open ? 'chevDown' : 'chevRight'} size={12} style={{ flexShrink: 0 }} />
        <span>{t('tapematch.analysis.title')}</span>
        {data?.verdict?.needs_review && (
          <Pill tone="warn" soft>{t('tapematch.analysis.flagged')}</Pill>
        )}
      </button>
      {open && (
        <div style={{ paddingBottom: 12 }}>
          {isFetching ? (
            <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', padding: '4px 0' }}>
              {t('common.loading')}
            </div>
          ) : !data?.analysis_md ? (
            <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', padding: '4px 0' }}>
              {t('tapematch.analysis.none')}
            </div>
          ) : (
            <pre style={{
              margin: 0, padding: 12, borderRadius: 6,
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)',
              lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxHeight: 420, overflowY: 'auto',
            }}>
              {data.analysis_md}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenTapeMatch(): React.JSX.Element {
  const { t } = useTranslation()
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<ViewFilter>('all')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [analysisOpen, setAnalysisOpen] = useState(false)

  const { data: datesData, isLoading: datesLoading } = useQuery({
    queryKey: ['tapematch-dates'],
    queryFn: () => fetch(`${BASE}/api/tapematch/dates`).then(r => r.json()),
    staleTime: 30_000,
  })
  const allDates: DateRow[] = datesData?.dates ?? []

  const { data: statusData } = useQuery({
    queryKey: ['tapematch-crawl-status'],
    queryFn: () => fetch(`${BASE}/api/tapematch/crawl/status`).then(r => r.json()),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })

  const filteredDates = useMemo(() => {
    let rows = allDates
    if (view === 'conflicts') rows = rows.filter(d => d.needs_review === true)
    else if (view === 'no_analysis') rows = rows.filter(d => d.has_analysis === false)
    const q = filter.trim().toLowerCase()
    if (q) {
      rows = rows.filter(d =>
        d.date.toLowerCase().includes(q) || (d.location ?? '').toLowerCase().includes(q)
      )
    }
    return rows
  }, [allDates, view, filter])

  const selectedRow = selectedDate ? allDates.find(d => d.date === selectedDate) ?? null : null

  const { data: pairsData, isLoading: pairsLoading } = useQuery({
    queryKey: ['tapematch-pairs', selectedDate],
    queryFn: () => fetch(`${BASE}/api/tapematch/pairs?date=${encodeURIComponent(selectedDate as string)}`).then(r => r.json()),
    enabled: !!selectedDate,
  })
  const pairs: PairRow[] = pairsData?.pairs ?? []

  // Families endpoint is a flat, ungrouped list across every synced date
  // (each row already carries concert_date + fam_id), so per-date grouping
  // is a filter + group-by — no client-side union-find over same_family
  // pairs needed.
  const { data: familiesData } = useQuery({
    queryKey: ['tapematch-families-all'],
    queryFn: () => fetch(`${BASE}/api/tapematch/families`).then(r => r.json()),
    staleTime: 60_000,
  })
  const allFamilies: FamilyRow[] = familiesData ?? []

  const familyGroups = useMemo(() => {
    if (!selectedDate) return [] as { label: string; lbs: number[] }[]
    const byFam = new Map<string, number[]>()
    allFamilies
      .filter(f => f.concert_date === selectedDate)
      .forEach(f => {
        const arr = byFam.get(f.fam_id) ?? []
        arr.push(f.lb_number)
        byFam.set(f.fam_id, arr)
      })
    const groups = Array.from(byFam.values()).map(lbs => lbs.slice().sort((a, b) => a - b))
    groups.sort((a, b) => a[0] - b[0])
    return groups.map((lbs, i) => ({ label: `F${i + 1}`, lbs }))
  }, [allFamilies, selectedDate])

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
          <Icon name="tapematch" size={18} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('tapematch.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('tapematch.subtitle')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <Input
          icon="search"
          placeholder={t('tapematch.filterPlaceholder')}
          size="sm"
          width={220}
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <CrawlStatusStrip status={statusData} />
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        <DateRail
          dates={filteredDates}
          view={view}
          onViewChange={setView}
          selectedDate={selectedDate}
          onSelect={date => { setSelectedDate(date); setAnalysisOpen(false) }}
          isLoading={datesLoading}
        />

        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'auto' }}>
          {!selectedDate || !selectedRow ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
              <Icon name="tapematch" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>{t('tapematch.noSelection')}</span>
            </div>
          ) : (
            <div style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Date + location + run id */}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-16)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
                  {selectedRow.date}
                </span>
                {selectedRow.location && (
                  <span style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg2)' }}>
                    {selectedRow.location}
                  </span>
                )}
                <div style={{ flex: 1 }} />
                {selectedRow.run_id && (
                  <Pill tone="mute" soft>{t('tapematch.runId', { runId: selectedRow.run_id })}</Pill>
                )}
              </div>

              {/* Families */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: '0.04em',
                    textTransform: 'uppercase', color: 'var(--lbb-fg3)', flex: '0 0 auto',
                  }}>
                    {t('tapematch.families.label')}
                  </span>
                  {familyGroups.length === 0 ? (
                    <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
                      {t('tapematch.families.none')}
                    </span>
                  ) : familyGroups.map(g => (
                    <Pill key={g.label} tone="info" soft>
                      {g.label}: {g.lbs.map(fmtLb).join(' ')}
                    </Pill>
                  ))}
                </div>
              </div>

              {/* Matrix */}
              <div>
                <div style={{
                  fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: '0.04em',
                  textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                }}>
                  {t('tapematch.matrix.label')}
                </div>
                <SimilarityMatrix pairs={pairs} isLoading={pairsLoading} />
              </div>

              {/* Analysis */}
              <AnalysisSection date={selectedRow.date} open={analysisOpen} onToggle={() => setAnalysisOpen(o => !o)} />
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
