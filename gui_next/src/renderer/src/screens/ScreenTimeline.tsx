// Timeline navigator (FABLE_IDEAS UI-2, instructions/FABLE_TIMELINE.md) — a
// zoomable Decade → Tour → Night browser of the concert archive, colored by
// the best grade held for each night. Read-only end to end; backend/timeline.py
// computes everything live per request from the same olof_events/entries
// coverage data backend/gap_analysis.py classifies for the Library's
// uncirculated/upcoming performance rows, but with no shared code (see spec
// §3 "Relationship to the Gaps view" — the standalone Gaps screen it
// originally compared against was retired once absorbed into the Library).

import React, { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { IconButton, Toast } from '../components/primitives'
import type { ToastTone } from '../components/primitives'
import { DossierExportModal } from '../components/library/DossierExportModal'

const BASE = window.api.flaskBase

// ── Types (mirror backend/timeline.py route shapes exactly) ──────────────────

interface DecadeRow {
  decade: number
  label: string
  night_count: number
  circulating_count: number
  best_grade: string | null
}

interface SummaryResponse {
  available: boolean
  generated_at: string
  decades: DecadeRow[]
}

interface TourRow {
  tour_name: string
  start_date: string
  end_date: string
  night_count: number
  circulating_count: number
  best_grade: string | null
}

interface DecadeDetailResponse {
  available: boolean
  decade: number
  label: string
  tours: TourRow[]
}

interface NightRow {
  date_iso: string
  venue: string | null
  city: string | null
  best_grade: string | null
  circulating: boolean
}

interface TourDetailResponse {
  available: boolean
  tour_name: string
  decade: number
  nights: NightRow[]
}

// ── Zoom state ─────────────────────────────────────────────────────────────

type View =
  | { level: 'decades' }
  | { level: 'tours'; decade: number; decadeLabel: string }
  | { level: 'nights'; decade: number; decadeLabel: string; tourName: string }

// ── Grade → sequential ramp step (spec §2 D3: 13-step letter grade → 6-step
// ramp, darkest = best). No shared backend/frontend ordinal exists (spec §1),
// so this mirrors backend/timeline.py::GRADE_RANK/_GRADE_ORDER as a fresh,
// frontend-local table — same duplication pattern as ScreenSongs.tsx's
// GRADE_ORDER / ScreenSearch.tsx's RATING_RANK. ──────────────────────────────

const GRADE_ORDER = [
  'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F',
] as const

/** Map a 13-step letter grade to a 1–6 `--lbb-seq-*` ramp step (6 = darkest/best). */
function seqStepForGrade(grade: string): number {
  const rank = GRADE_ORDER.indexOf(grade as (typeof GRADE_ORDER)[number])
  if (rank < 0) return 1
  return Math.max(1, Math.min(6, 6 - Math.floor((rank * 6) / GRADE_ORDER.length)))
}

function seqColorForGrade(grade: string): string {
  return `var(--lbb-seq-${seqStepForGrade(grade)})`
}

// Held-but-ungraded: a distinct, subtle neutral fill — deliberately NOT a
// ramp step (would misread as "a low grade") and NOT --lbb-mute-* (which
// means confirmed no-tape). Derived from --lbb-fg3 so it tracks the active
// theme in both light and dark (spec §4 B3 three-state model).
const HELD_FILL = 'color-mix(in srgb, var(--lbb-fg3) 30%, var(--lbb-surface))'
const HELD_BORDER = 'color-mix(in srgb, var(--lbb-fg3) 55%, var(--lbb-surface))'

function fmtDateShort(dateIso: string): string {
  const d = new Date(`${dateIso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return dateIso
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtDateLong(dateIso: string): string {
  const d = new Date(`${dateIso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return dateIso
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

// ── Breadcrumb ─────────────────────────────────────────────────────────────

function Breadcrumb({
  view, onRoot, onDecade,
}: {
  view: View
  onRoot: () => void
  onDecade: (decade: number, decadeLabel: string) => void
}) {
  const { t } = useTranslation()
  const crumbs: { label: string; onClick?: () => void }[] = [
    { label: t('timeline.breadcrumb.root'), onClick: view.level !== 'decades' ? onRoot : undefined },
  ]
  if (view.level === 'tours' || view.level === 'nights') {
    crumbs.push({
      label: view.decadeLabel,
      onClick: view.level === 'nights' ? () => onDecade(view.decade, view.decadeLabel) : undefined,
    })
  }
  if (view.level === 'nights') {
    crumbs.push({ label: view.tourName })
  }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px',
      borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      fontSize: 'var(--lbb-fs-12-5)',
    }}>
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && <Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)', flex: '0 0 auto' }} />}
          {c.onClick ? (
            <button
              type="button"
              onClick={c.onClick}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                color: 'var(--lbb-accent-mid)', fontFamily: 'inherit',
                fontSize: 'var(--lbb-fs-12-5)', fontWeight: 500,
              }}
            >
              {c.label}
            </button>
          ) : (
            <span style={{ color: 'var(--lbb-fg)', fontWeight: 600 }}>{c.label}</span>
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

// ── Grade indicator (dot + label — keeps text off colored fills so contrast
// never has to be computed per ramp step) ────────────────────────────────────

function GradeIndicator({
  color, label,
}: {
  color: string
  label: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 9, height: 9, borderRadius: 3, background: color, flex: '0 0 auto' }} />
      <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>{label}</span>
    </div>
  )
}

// ── Decade grid ───────────────────────────────────────────────────────────

function DecadeCard({ row, onOpen }: { row: DecadeRow; onOpen: (row: DecadeRow) => void }) {
  const { t } = useTranslation()
  const graded = row.best_grade !== null
  const held = !graded && row.circulating_count > 0
  const barColor = graded
    ? seqColorForGrade(row.best_grade as string)
    : held ? HELD_FILL : 'var(--lbb-mute-bg)'
  const indicatorColor = graded
    ? seqColorForGrade(row.best_grade as string)
    : held ? HELD_BORDER : 'var(--lbb-mute-fg)'
  const gradeLabel = graded
    ? t('timeline.grade.best', { grade: row.best_grade })
    : held ? t('timeline.grade.circulatingUngraded') : t('timeline.grade.noTape')

  return (
    <button
      type="button"
      onClick={() => onOpen(row)}
      style={{
        width: 176, textAlign: 'left', cursor: 'pointer', padding: 0,
        borderRadius: 8, border: '1px solid var(--lbb-border)',
        background: 'var(--lbb-surface)', overflow: 'hidden', fontFamily: 'inherit',
      }}
    >
      <div style={{ height: 6, width: '100%', background: barColor }} />
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700 }}>{row.label}</div>
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('timeline.decade.nights', { count: row.night_count })}
          {' · '}
          {t('timeline.decade.circulating', { count: row.circulating_count })}
        </div>
        <GradeIndicator color={indicatorColor} label={gradeLabel} />
      </div>
    </button>
  )
}

function DecadeGrid({ decades, onOpen }: { decades: DecadeRow[]; onOpen: (row: DecadeRow) => void }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: 20 }}>
      {decades.map(row => (
        <DecadeCard key={row.decade} row={row} onOpen={onOpen} />
      ))}
    </div>
  )
}

// ── Tour grid ─────────────────────────────────────────────────────────────
//
// get_decade_detail now returns circulating_count per tour, so the tour tier
// gets the same true three-state model as the decade/night tiers: graded →
// ramp; ungraded-but-held → neutral fill; confirmed no-tape → --lbb-mute-*.

function TourCard({ row, onOpen }: { row: TourRow; onOpen: (row: TourRow) => void }) {
  const { t } = useTranslation()
  const graded = row.best_grade !== null
  const held = !graded && row.circulating_count > 0
  const barColor = graded
    ? seqColorForGrade(row.best_grade as string)
    : held ? HELD_FILL : 'var(--lbb-mute-bg)'
  const indicatorColor = graded
    ? seqColorForGrade(row.best_grade as string)
    : held ? HELD_BORDER : 'var(--lbb-mute-fg)'
  const gradeLabel = graded
    ? t('timeline.grade.best', { grade: row.best_grade })
    : held ? t('timeline.grade.circulatingUngraded') : t('timeline.grade.noTape')

  return (
    <button
      type="button"
      onClick={() => onOpen(row)}
      style={{
        width: 220, textAlign: 'left', cursor: 'pointer', padding: 0,
        borderRadius: 8, border: '1px solid var(--lbb-border)',
        background: 'var(--lbb-surface)', overflow: 'hidden', fontFamily: 'inherit',
      }}
    >
      <div style={{ height: 6, width: '100%', background: barColor }} />
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--lbb-fs-13)', fontWeight: 700, whiteSpace: 'nowrap',
          overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {row.tour_name}
        </div>
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {fmtDateShort(row.start_date)} – {fmtDateShort(row.end_date)}
        </div>
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('timeline.tour.nights', { count: row.night_count })}
          {' · '}
          {t('timeline.tour.circulating', { count: row.circulating_count })}
        </div>
        <GradeIndicator color={indicatorColor} label={gradeLabel} />
      </div>
    </button>
  )
}

function TourGrid({ tours, onOpen }: { tours: TourRow[]; onOpen: (row: TourRow) => void }) {
  const { t } = useTranslation()
  if (tours.length === 0) {
    return (
      <div style={{ padding: 20, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12-5)' }}>
        {t('timeline.empty.tours')}
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: 20 }}>
      {tours.map(row => (
        <TourCard key={row.tour_name} row={row} onOpen={onOpen} />
      ))}
    </div>
  )
}

// ── Night strip ────────────────────────────────────────────────────────────

function NightCell({ night, onOpen }: { night: NightRow; onOpen: (dateIso: string) => void }) {
  const { t } = useTranslation()
  const graded = night.best_grade !== null
  const clickable = graded || night.circulating

  const background = graded
    ? seqColorForGrade(night.best_grade as string)
    : night.circulating ? HELD_FILL : 'var(--lbb-mute-bg)'
  const border = graded
    ? seqColorForGrade(night.best_grade as string)
    : night.circulating ? HELD_BORDER : 'var(--lbb-mute-fg)'

  const venue = night.venue || night.city || t('timeline.night.unknownVenue')
  const title = graded
    ? t('timeline.night.tooltipGraded', { date: fmtDateLong(night.date_iso), venue, grade: night.best_grade })
    : night.circulating
      ? t('timeline.night.tooltipCirculating', { date: fmtDateLong(night.date_iso), venue })
      : t('timeline.night.tooltipNoTape', { date: fmtDateLong(night.date_iso), venue })

  return (
    <button
      type="button"
      title={title}
      disabled={!clickable}
      onClick={() => onOpen(night.date_iso)}
      style={{
        width: 16, height: 16, borderRadius: 3, padding: 0,
        cursor: clickable ? 'pointer' : 'default',
        background, border: `1px solid ${border}`,
        opacity: clickable ? 1 : 0.6,
        boxSizing: 'border-box', flex: '0 0 auto',
      }}
    />
  )
}

function NightStrip({
  nights, onOpen,
}: {
  nights: NightRow[]
  onOpen: (dateIso: string) => void
}) {
  const { t } = useTranslation()
  if (nights.length === 0) {
    return (
      <div style={{ padding: 20, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12-5)' }}>
        {t('timeline.empty.nights')}
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: 20, alignContent: 'flex-start' }}>
      {nights.map(n => (
        <NightCell key={n.date_iso} night={n} onOpen={onOpen} />
      ))}
    </div>
  )
}

// ── Dossier viewer modal (spec D4) ──────────────────────────────────────────
//
// A minimal, read-only iframe onto the same HTML the backend already renders
// for the export flow (`/api/dossier/html`, public channel). Closing this
// modal only clears local `viewerDate` state in ScreenTimeline — it never
// touches the `useQuery` calls that back the decade/tour/night grids, so the
// night strip underneath is untouched (no remount, no refetch). "Open full
// export…" hands off to the existing `DossierExportModal` for anyone who
// wants PDF/BBcode/format options instead of just looking; that modal is not
// retrofitted, just mounted on top with the same date as `showId`.

function DossierViewerModal({
  dateIso, base, onClose, onOpenExport,
}: {
  dateIso: string
  base: string
  onClose: () => void
  onOpenExport: () => void
}) {
  const { t } = useTranslation()
  const title = t('timeline.viewer.title', { date: fmtDateLong(dateIso) })

  return (
    <div
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 900,
        background: 'color-mix(in oklab, var(--lbb-fg) 38%, transparent)',
        backdropFilter: 'blur(1.5px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div style={{
        width: '90%', maxWidth: 960, height: '86%',
        background: 'var(--lbb-bg)', borderRadius: 12,
        border: '1px solid var(--lbb-border)',
        boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
        }}>
          <div style={{
            flex: 1, minWidth: 0, fontSize: 'var(--lbb-fs-14)', fontWeight: 700,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {title}
          </div>
          <button
            type="button"
            onClick={onOpenExport}
            style={{
              background: 'none', border: '1px solid var(--lbb-border)', borderRadius: 6,
              padding: '5px 10px', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-accent-mid)', flex: '0 0 auto',
            }}
          >
            {t('timeline.viewer.openExport')}
          </button>
          <IconButton icon="x" onClick={onClose} title={t('timeline.viewer.close')} />
        </div>
        <iframe
          src={`${base}/api/dossier/html?date=${encodeURIComponent(dateIso)}&channel=public&inline=1`}
          title={title}
          style={{ flex: 1, width: '100%', border: 'none', background: 'var(--lbb-bg)' }}
        />
      </div>
    </div>
  )
}

// ── Empty state (olof_events absent) ──────────────────────────────────────

function TimelineUnavailable() {
  const { t } = useTranslation()
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 12, color: 'var(--lbb-fg3)', padding: 40, textAlign: 'center',
    }}>
      <Icon name="timeline" size={36} style={{ opacity: 0.15 }} />
      <span style={{ fontSize: 'var(--lbb-fs-13)', maxWidth: 420 }}>{t('timeline.unavailable')}</span>
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────

export function ScreenTimeline(): React.JSX.Element {
  const { t } = useTranslation()
  const [view, setView] = useState<View>({ level: 'decades' })

  // Dossier viewer (spec D4) — deliberately separate from `view`/the
  // `useQuery` calls below: opening/closing it must never touch the
  // decade/tour/night queries backing the night strip underneath.
  const [viewerDate, setViewerDate] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)
  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  const { data: summary, isLoading } = useQuery<SummaryResponse>({
    queryKey: ['timeline-summary'],
    queryFn: () => fetch(`${BASE}/api/timeline/summary`).then(r => r.json()),
    staleTime: 60_000,
  })

  const decade = view.level !== 'decades' ? view.decade : null
  const { data: decadeDetail, isLoading: decadeLoading } = useQuery<DecadeDetailResponse>({
    queryKey: ['timeline-decade', decade],
    queryFn: () => fetch(`${BASE}/api/timeline/decade/${decade}`).then(r => r.json()),
    enabled: decade !== null,
    staleTime: 60_000,
  })

  const tourName = view.level === 'nights' ? view.tourName : null
  const { data: tourDetail, isLoading: tourLoading } = useQuery<TourDetailResponse>({
    queryKey: ['timeline-tour', tourName, decade],
    queryFn: () => fetch(
      `${BASE}/api/timeline/tour?name=${encodeURIComponent(tourName as string)}&decade=${decade}`,
    ).then(r => r.json()),
    enabled: view.level === 'nights',
    staleTime: 60_000,
  })

  const openDecade = (row: DecadeRow) => setView({ level: 'tours', decade: row.decade, decadeLabel: row.label })
  const openTour = (row: TourRow) => {
    if (view.level === 'decades') return
    setView({ level: 'nights', decade: view.decade, decadeLabel: view.decadeLabel, tourName: row.tour_name })
  }
  const goRoot = () => setView({ level: 'decades' })
  const goDecade = (d: number, decadeLabel: string) => setView({ level: 'tours', decade: d, decadeLabel })

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
          <Icon name="timeline" size={18} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('timeline.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('timeline.subtitle')}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)' }}>
          {t('common.loading')}
        </div>
      ) : !summary?.available ? (
        <TimelineUnavailable />
      ) : (
        <>
          <Breadcrumb view={view} onRoot={goRoot} onDecade={goDecade} />
          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {view.level === 'decades' && (
              <DecadeGrid decades={summary.decades} onOpen={openDecade} />
            )}
            {view.level === 'tours' && (
              decadeLoading || !decadeDetail ? (
                <div style={{ padding: 20, color: 'var(--lbb-fg3)' }}>{t('common.loading')}</div>
              ) : (
                <TourGrid tours={decadeDetail.tours} onOpen={openTour} />
              )
            )}
            {view.level === 'nights' && (
              tourLoading || !tourDetail ? (
                <div style={{ padding: 20, color: 'var(--lbb-fg3)' }}>{t('common.loading')}</div>
              ) : (
                <NightStrip nights={tourDetail.nights} onOpen={setViewerDate} />
              )
            )}
          </div>
        </>
      )}

      {viewerDate && (
        <DossierViewerModal
          dateIso={viewerDate}
          base={BASE}
          onClose={() => setViewerDate(null)}
          onOpenExport={() => setExportOpen(true)}
        />
      )}
      {exportOpen && viewerDate && (
        <DossierExportModal
          showId={viewerDate}
          base={BASE}
          onClose={() => setExportOpen(false)}
          showToast={showToast}
        />
      )}
      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
    </div>
  )
}
