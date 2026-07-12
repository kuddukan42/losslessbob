// Song browser screen (LISTENING §3 / TODO-230) — inverts the catalog to browse
// by song instead of by recording: search the song_canonical spine, pick a
// song, and read every performance (date, venue, event type, encore/take
// status) with its circulating recordings deep-linking into the Library
// DetailPanel. Read-mostly like ScreenTapeMatch — the only write path is the
// curator-gated canonical-spelling rename.

import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Pill, Chip, Input, Button } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useSettingsStore } from '../store'

const BASE = window.api.flaskBase

// ── Types (mirror backend/song_index.py route shapes) ────────────────────────

interface SongRow {
  song_norm: string
  canonical: string
  n_performances: number
  n_concerts: number
  n_dates_with_recordings: number
  first_date: string | null
  last_date: string | null
}

interface RecordingRow {
  lb_number: number
  pick_rank: number
  abs_grade: string | null
}

interface PerformanceRow {
  date_iso: string | null
  event_id: number
  event_type: string | null
  venue: string | null
  city: string | null
  is_encore: boolean
  take_status: string | null
  recordings: RecordingRow[]
}

interface PerformancesResponse {
  song_norm: string
  canonical: string
  performances: PerformanceRow[]
}

type SortMode = 'date' | 'best'

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

// Concert Ranker's A+..F letter scale (concert_ranker/calibrate.py RATING_RANK),
// best to worst. Used only to order the "best first" performance sort below —
// unknown/ungraded recordings rank worst (0).
const GRADE_ORDER = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']
const GRADE_RANK: Record<string, number> = Object.fromEntries(
  GRADE_ORDER.map((g, i) => [g, GRADE_ORDER.length - i])
)

function eventTypeTone(eventType: string | null): 'ok' | 'info' | 'mute' {
  if (eventType === 'concert') return 'ok'
  if (eventType) return 'info'
  return 'mute'
}

// "Best first" heuristic: a performance's rank is the abs_grade of its
// rank-1 (top pick) recording, if any — performances with a graded top pick
// sort before those without, best grade first. Performances tied on grade
// (or with no graded top pick at all) fall back to chronological order,
// which is the array's incoming order since the API already returns
// performances date-ascending.
function bestFirstRank(perf: PerformanceRow): number {
  const top = perf.recordings.find(r => r.pick_rank === 1)
  if (!top || !top.abs_grade) return -1
  return GRADE_RANK[top.abs_grade] ?? 0
}

function sortPerformances(performances: PerformanceRow[], mode: SortMode): PerformanceRow[] {
  if (mode === 'date') return performances
  return performances
    .map((perf, index) => ({ perf, index }))
    .sort((a, b) => {
      const rankDiff = bestFirstRank(b.perf) - bestFirstRank(a.perf)
      if (rankDiff !== 0) return rankDiff
      return a.index - b.index // stable fallback to original (chronological) order
    })
    .map(({ perf }) => perf)
}

// LB number/label rendered as a real <button> that deep-links into the
// Library DetailPanel (`/library?lb=<n>`). Mirrors ScreenTapeMatch's
// LbLinkButton — no default button chrome, accent hover.
function LbLinkButton({ lb, onOpen }: { lb: number; onOpen: (lb: number) => void }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={() => onOpen(lb)}
      title={t('songs.table.openInLibrary')}
      style={{
        fontFamily: 'var(--lbb-mono)',
        fontSize: 'inherit',
        fontWeight: 'inherit',
        color: 'inherit',
        background: 'none',
        border: 'none',
        padding: 0,
        margin: 0,
        cursor: 'pointer',
      }}
      onMouseEnter={e => { e.currentTarget.style.color = 'var(--lbb-accent-mid)' }}
      onMouseLeave={e => { e.currentTarget.style.color = 'inherit' }}
    >
      {fmtLb(lb)}
    </button>
  )
}

// ── Left rail — song search + list ────────────────────────────────────────────

function SongRail({
  songs, isLoading, search, onSearchChange, selectedSongNorm, onSelect,
}: {
  songs: SongRow[]
  isLoading: boolean
  search: string
  onSearchChange: (v: string) => void
  selectedSongNorm: string | null
  onSelect: (songNorm: string) => void
}) {
  const { t } = useTranslation()
  return (
    <aside style={{
      width: 280, flex: '0 0 280px',
      background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', minHeight: 0,
    }}>
      <div style={{ padding: '12px 12px 10px', borderBottom: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <Icon name="songs" size={13} style={{ color: 'var(--lbb-fg3)' }} />
          <span style={{
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
            letterSpacing: 0.1, textTransform: 'uppercase',
          }}>{t('songs.title')}</span>
          <span style={{
            marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600,
            color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums',
          }}>{songs.length}</span>
        </div>
        <Input
          icon="search"
          placeholder={t('songs.rail.searchPlaceholder')}
          size="sm"
          width="100%"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
        />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
        {isLoading ? (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
            {t('songs.rail.loading')}
          </div>
        ) : songs.length === 0 ? (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
            {t('songs.rail.empty')}
          </div>
        ) : songs.map(s => {
          const active = s.song_norm === selectedSongNorm
          return (
            <button
              key={s.song_norm}
              type="button"
              onClick={() => onSelect(s.song_norm)}
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
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 'var(--lbb-fs-12-5)', fontWeight: active ? 600 : 500,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {s.canonical}
                </div>
                <div style={{
                  fontSize: 'var(--lbb-fs-10-5)', marginTop: 2,
                  color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
                }}>
                  {t('songs.rail.meta', { recDates: s.n_dates_with_recordings })}
                </div>
              </div>
              <span style={{
                fontSize: 'var(--lbb-fs-11)', fontWeight: 600, flex: '0 0 auto',
                fontVariantNumeric: 'tabular-nums',
                color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
              }}>
                {s.n_performances}
              </span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}

// ── Header — canonical name + curator rename affordance + stats ──────────────

function SongHeader({
  song, songNorm, onRenamed,
}: {
  song: SongRow | undefined
  songNorm: string
  onRenamed: () => void
}) {
  const { t } = useTranslation()
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canonical = song?.canonical ?? songNorm

  const startEdit = () => {
    setValue(canonical)
    setError(null)
    setEditing(true)
  }

  const save = async () => {
    const trimmed = value.trim()
    if (!trimmed) return
    setSaving(true)
    setError(null)
    try {
      const resp = await fetch(`${BASE}/api/songs/alias`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: songNorm, canonical: trimmed }),
      })
      if (resp.status === 403) {
        setError(t('songs.edit.curatorRequired'))
        return
      }
      if (!resp.ok) {
        setError(t('songs.edit.saveFailed'))
        return
      }
      setEditing(false)
      onRenamed()
    } catch {
      setError(t('songs.edit.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const statsLine = song
    ? t('songs.header.stats', {
        performances: song.n_performances,
        concerts: song.n_concerts,
        first: song.first_date ?? t('songs.header.unknownDate'),
        last: song.last_date ?? t('songs.header.unknownDate'),
      })
    : null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {editing ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Input
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder={t('songs.edit.placeholder')}
              size="sm"
              width={260}
            />
            <Button variant="primary" size="sm" disabled={saving || !value.trim()} onClick={save}>
              {saving ? t('songs.edit.saving') : t('common.save')}
            </Button>
            <Button variant="ghost" size="sm" disabled={saving} onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        ) : (
          <>
            <span style={{ fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01, color: 'var(--lbb-fg)' }}>
              {canonical}
            </span>
            {curatorMode && (
              <button
                type="button"
                title={t('songs.edit.title')}
                onClick={startEdit}
                style={{
                  width: 24, height: 24, borderRadius: 6, flexShrink: 0,
                  background: 'transparent', border: '1px solid var(--lbb-border2)',
                  color: 'var(--lbb-fg3)', cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--lbb-surface2)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
              >
                <Icon name="rename" size={12} />
              </button>
            )}
          </>
        )}
      </div>
      {error && (
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-bad-fg)', marginTop: 6 }}>{error}</div>
      )}
      {statsLine && !editing && (
        <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 4, fontFamily: 'var(--lbb-mono)' }}>
          {statsLine}
        </div>
      )}
    </div>
  )
}

// ── Performance table ─────────────────────────────────────────────────────────

function PerformanceTable({
  performances, isLoading, onOpenLb,
}: {
  performances: PerformanceRow[]
  isLoading: boolean
  onOpenLb: (lb: number) => void
}) {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div style={{ padding: '16px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
        {t('common.loading')}
      </div>
    )
  }
  if (performances.length === 0) {
    return (
      <div style={{ padding: '16px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
        {t('songs.table.empty')}
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <TableShell stickyHeader={false}>
        <colgroup>
          <col style={{ width: 3 }} />
          <col style={{ width: 96 }} />
          <col />
          <col style={{ width: 130 }} />
          <col style={{ width: 96 }} />
          <col style={{ width: 110 }} />
          <col style={{ width: 76 }} />
          <col style={{ width: 200 }} />
        </colgroup>
        <thead>
          <tr>
            <TH />
            <TH>{t('songs.table.date')}</TH>
            <TH>{t('songs.table.venue')}</TH>
            <TH>{t('songs.table.city')}</TH>
            <TH>{t('songs.table.type')}</TH>
            <TH>{t('songs.table.take')}</TH>
            <TH align="center">{t('songs.table.encore')}</TH>
            <TH>{t('songs.table.recordings')}</TH>
          </tr>
        </thead>
        <tbody>
          {performances.map(p => (
            <TR key={`${p.event_id}-${p.date_iso ?? 'nodate'}`}>
              <TD mono>{p.date_iso ?? t('songs.table.none')}</TD>
              <TD>{p.venue ?? t('songs.table.none')}</TD>
              <TD>{p.city ?? t('songs.table.none')}</TD>
              <TD>
                <Pill tone={eventTypeTone(p.event_type)} soft>
                  {p.event_type ?? t('songs.table.none')}
                </Pill>
              </TD>
              <TD>
                {p.take_status ? (
                  <Pill tone="mute" soft>{p.take_status}</Pill>
                ) : (
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('songs.table.none')}</span>
                )}
              </TD>
              <TD align="center">
                {p.is_encore ? (
                  <span title={t('songs.table.encoreYes')}>
                    <Icon name="starFill" size={13} style={{ color: 'var(--lbb-warn-fg)' }} />
                  </span>
                ) : (
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('songs.table.none')}</span>
                )}
              </TD>
              <TD>
                {p.recordings.length === 0 ? (
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('songs.table.none')}</span>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                    {p.recordings.map(r => (
                      <span key={r.lb_number} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <LbLinkButton lb={r.lb_number} onOpen={onOpenLb} />
                        {r.pick_rank === 1 && (
                          <Pill tone="ok" soft>{t('songs.table.pick')}</Pill>
                        )}
                        {r.abs_grade && (
                          <span style={{
                            fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)',
                            color: 'var(--lbb-fg3)',
                          }}>
                            {r.abs_grade}
                          </span>
                        )}
                      </span>
                    ))}
                  </div>
                )}
              </TD>
            </TR>
          ))}
        </tbody>
      </TableShell>
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenSongs(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [selectedSongNorm, setSelectedSongNorm] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('date')

  // Debounce the song search 200ms before it drives the ?q= backend query
  // (mirrors ScreenBootlegs's search debounce).
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 200)
    return () => clearTimeout(timer)
  }, [search])

  const openLb = (lb: number) => navigate(`/library?lb=${lb}`)

  const { data: songsData, isLoading: songsLoading } = useQuery({
    queryKey: ['songs', debouncedSearch],
    queryFn: () => fetch(
      `${BASE}/api/songs${debouncedSearch.trim() ? `?q=${encodeURIComponent(debouncedSearch.trim())}` : ''}`
    ).then(r => r.json()),
    staleTime: 30_000,
  })
  const songs: SongRow[] = songsData?.songs ?? []

  const selectedSong = selectedSongNorm
    ? songs.find(s => s.song_norm === selectedSongNorm)
    : undefined

  const { data: perfData, isLoading: perfLoading } = useQuery<PerformancesResponse>({
    queryKey: ['song-performances', selectedSongNorm],
    queryFn: () => fetch(
      `${BASE}/api/songs/performances?song=${encodeURIComponent(selectedSongNorm as string)}`
    ).then(r => r.json()),
    enabled: !!selectedSongNorm,
  })
  const performances: PerformanceRow[] = perfData?.performances ?? []
  const sortedPerformances = useMemo(
    () => sortPerformances(performances, sortMode),
    [performances, sortMode]
  )

  const handleRenamed = () => {
    if (!selectedSongNorm) return
    queryClient.invalidateQueries({ queryKey: ['songs'] })
    queryClient.invalidateQueries({ queryKey: ['song-performances', selectedSongNorm] })
  }

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
          <Icon name="songs" size={18} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('songs.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('songs.subtitle')}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        <SongRail
          songs={songs}
          isLoading={songsLoading}
          search={search}
          onSearchChange={setSearch}
          selectedSongNorm={selectedSongNorm}
          onSelect={songNorm => { setSelectedSongNorm(songNorm); setSortMode('date') }}
        />

        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'auto' }}>
          {!selectedSongNorm ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
              <Icon name="songs" size={36} style={{ opacity: 0.15 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)' }}>{t('songs.noSelection')}</span>
            </div>
          ) : (
            <div style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

              <SongHeader song={selectedSong} songNorm={selectedSongNorm} onRenamed={handleRenamed} />

              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{
                    fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: '0.04em',
                    textTransform: 'uppercase', color: 'var(--lbb-fg3)',
                  }}>
                    {t('songs.sort.label')}
                  </span>
                  <Chip size="sm" active={sortMode === 'date'} onClick={() => setSortMode('date')}>
                    {t('songs.sort.date')}
                  </Chip>
                  <Chip size="sm" active={sortMode === 'best'} onClick={() => setSortMode('best')}>
                    {t('songs.sort.best')}
                  </Chip>
                </div>
                <PerformanceTable
                  performances={sortedPerformances}
                  isLoading={perfLoading}
                  onOpenLb={openLb}
                />
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
