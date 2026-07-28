// TapeMatch Curation screen — Phase 1 (shell only).
//
// Built per instructions/design_handoff_tapematch_curation/{README,
// WORK_PACKAGE,DESIGN_ANSWERS_B}.md. D1: new screen, old ScreenTapeMatch.tsx
// stays untouched and keeps its nav entry until this one reaches parity
// (end of Phase 6) — this screen therefore has NO nav entry yet and is only
// reachable at /tapematch/curation.
//
// Phase 1 scope: §1 top bar, §2 triage queue rail (incl. keybindings), §3
// date header (incl. DESIGN_ANSWERS_B §B3 verdict clamp), §4 section
// wrapper, and the three-column work grid + its two breakpoints (rail
// 272→224px at ≤1380px, dossier docked→collapsed at ≤1520px). The work
// column renders labelled empty placeholders for the matrix / speed strip /
// verdict cards (Phases 2, 4, 5); the dossier renders its empty state only
// (Phase 3). No pair selection exists yet, so the dossier never becomes a
// populated drawer in this phase — that arrives with the matrix in Phase 2.

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Pill, Button, Kbd } from '../components'
import { familyColorVar } from '../lib/tokens'

const BASE = window.api.flaskBase

// ── Types (mirror backend/app.py tapematch_* route shapes — see
//    ScreenTapeMatch.tsx, which reads the same endpoints) ───────────────────

interface DateRow {
  date: string
  run_id: string | null
  n_lbs: number
  n_pairs: number
  has_analysis: boolean | null
  needs_review: boolean | null
  location: string | null
}

interface FamilyRow {
  lb_number: number
  fam_id: string
  concert_date: string
  fam_label: string | null
}

interface CrawlStatus {
  running: boolean
  runs_on_disk: number
  distinct_dates: number
}

interface AnalysisResponse {
  verdict?: { needs_review: boolean | null; reason: string | null }
  analysis_md?: string | null
}

interface PairRow {
  lb_a: number
  lb_b: number
  corr: number | null
  emb_score: number | null
  fp_score: number | null
  same_family: boolean
  similarity_pct: number | null
  human_judgment: string | null
  human_notes: string | null
  ab_eligible: boolean | null
  lb_says_same: boolean | null
  lb_relation_text: string | null
}

interface PairsResponse {
  date: string
  run_id: string | null
  pairs: PairRow[]
}

// A selected pair is identified by its two LB numbers (order-independent),
// not by matrix row/column indices — Phase 3's dossier will key off the LB
// numbers directly, and the numbers stay stable while the matrix's row/
// column order does not (family sort can change as families get curated).
interface SelectedPair {
  lbA: number
  lbB: number
}

function pairKey(a: number, b: number): string {
  return a < b ? `${a}-${b}` : `${b}-${a}`
}

function shortId(lb: number): string {
  return String(lb).padStart(5, '0')
}

// ── Status vocabulary (README §2) ───────────────────────────────────────────
// The design's four-state vocabulary (conflict/review/clean/curated) doesn't
// map 1:1 onto what /api/tapematch/dates exposes today — there is no
// "curated" concept until the Phase 6 write path lands (Accept families),
// and no separate "review" signal beyond has_analysis/needs_review. This is
// the best available approximation: needs_review true -> conflict (LB
// commentary disagreement is the review trigger the endpoint tracks);
// has_analysis false -> review (nothing parsed yet, needs a look); otherwise
// clean. `curated` is reachable in the type but unpopulated until Phase 6.
type TriageStatus = 'conflict' | 'review' | 'clean' | 'curated'

function statusOf(row: DateRow): TriageStatus {
  if (row.needs_review === true) return 'conflict'
  if (row.has_analysis === false) return 'review'
  return 'clean'
}

const STATUS_TONE: Record<TriageStatus, 'bad' | 'warn' | 'ok' | 'mute'> = {
  conflict: 'bad',
  review: 'warn',
  clean: 'ok',
  curated: 'mute',
}

const STATUS_LABEL: Record<TriageStatus, string> = {
  conflict: 'conflict',
  review: 'review',
  clean: 'clean',
  curated: 'curated',
}

type FilterKey = 'needs' | 'conflict' | 'all' | 'curated'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'needs', label: 'Needs you' },
  { key: 'conflict', label: 'Conflicts' },
  { key: 'all', label: 'All' },
  { key: 'curated', label: 'Done' },
]

function matchesFilter(status: TriageStatus, filter: FilterKey): boolean {
  switch (filter) {
    case 'needs': return status === 'conflict' || status === 'review'
    case 'conflict': return status === 'conflict'
    case 'curated': return status === 'curated'
    case 'all': default: return true
  }
}

// ── Small viewport-width hook — drives the two breakpoints (README "Top-level
//    layout"). No shared useMediaQuery hook exists elsewhere in gui_next, so
//    this stays local to the screen rather than inventing a new lib module. ──

function useViewportWidth(): number {
  const [w, setW] = useState(() => window.innerWidth)
  useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return w
}

// ── §4 Section wrapper — used by all three work-column blocks ──────────────

function CurationSection({
  title, hint, children,
}: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 18, maxWidth: 760 }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 9, flexWrap: 'wrap',
      }}>
        <div style={{
          fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: 'var(--lbb-fg3)',
        }}>{title}</div>
        <div style={{ fontSize: 11, color: 'var(--lbb-fg3)' }}>{hint}</div>
      </div>
      {children}
    </div>
  )
}

function SectionPlaceholder({ label }: { label: string }) {
  return (
    <div style={{
      border: '1px dashed var(--lbb-border2)', borderRadius: 8,
      padding: '26px 16px', textAlign: 'center',
      fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)',
      background: 'var(--lbb-surface)',
    }}>
      {label}
    </div>
  )
}

// ── §1 Top bar ───────────────────────────────────────────────────────────────

function TopBar({ crawl }: { crawl: CrawlStatus | undefined }) {
  const dotColor = crawl?.running ? 'var(--lbb-warn-bar)' : 'var(--lbb-ok-bar)'
  const statusWord = crawl?.running ? 'running' : 'idle'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '10px 18px',
      borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
      flex: '0 0 auto',
    }}>
      <div style={{ fontSize: 12.5, color: 'var(--lbb-fg3)' }}>
        LosslessBob <span style={{ color: 'var(--lbb-border2)' }}>/</span> Library{' '}
        <span style={{ color: 'var(--lbb-border2)' }}>/</span>{' '}
        <span style={{ color: 'var(--lbb-fg)', fontWeight: 700 }}>TapeMatch</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>
        Curation — review the algorithm's family calls, pair by pair
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        {crawl && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 11, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)',
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor }} />
            crawl {statusWord} · {crawl.runs_on_disk.toLocaleString()} runs ·{' '}
            {crawl.distinct_dates.toLocaleString()} dates
          </div>
        )}
        {/* Queued-judgments pill — only appears once the Phase 6 write path
            can actually queue something; nothing to count yet. */}
      </div>
    </div>
  )
}

// ── §2 Triage queue rail ────────────────────────────────────────────────────

function TriageRail({
  rows, narrow, selectedDate, onOpen, cursorIndexRef, familyCountByDate,
}: {
  rows: DateRow[]
  narrow: boolean
  selectedDate: string | null
  onOpen: (date: string) => void
  cursorIndexRef: React.MutableRefObject<number>
  familyCountByDate: Map<string, number>
}) {
  const [filter, setFilter] = useState<FilterKey>('needs')
  const [cursor, setCursor] = useState(0)
  const listRef = useRef<HTMLDivElement | null>(null)
  const rowRefs = useRef<Map<number, HTMLButtonElement>>(new Map())

  const filtered = useMemo(
    () => rows.filter(r => matchesFilter(statusOf(r), filter)),
    [rows, filter],
  )
  const needsCount = useMemo(
    () => rows.filter(r => matchesFilter(statusOf(r), 'needs')).length,
    [rows],
  )

  // Cursor reconciliation (README §2): snap to the open date's row if it's
  // in the filtered list, otherwise clamp into range. Deliberately does not
  // re-run when only the cursor moves (cursor is local state, not a dep).
  useEffect(() => {
    if (selectedDate) {
      const idx = filtered.findIndex(r => r.date === selectedDate)
      if (idx >= 0) { setCursor(idx); return }
    }
    setCursor(c => Math.max(0, Math.min(c, filtered.length - 1)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, selectedDate])

  useEffect(() => { cursorIndexRef.current = cursor }, [cursor, cursorIndexRef])

  // Keep the cursor row visible — manual scrollTop math, not scrollIntoView
  // (README §2: scrollIntoView drags ancestor containers around too).
  useEffect(() => {
    const box = listRef.current
    const row = rowRefs.current.get(cursor)
    if (!box || !row) return
    const margin = 6
    const rowTop = row.offsetTop - box.offsetTop
    const rowBottom = rowTop + row.offsetHeight
    if (rowTop - margin < box.scrollTop) box.scrollTop = rowTop - margin
    else if (rowBottom + margin > box.scrollTop + box.clientHeight) {
      box.scrollTop = rowBottom + margin - box.clientHeight
    }
  }, [cursor])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor(c => Math.min(c + 1, filtered.length - 1))
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor(c => Math.max(c - 1, 0))
      } else if (e.key === 'Enter') {
        const row = filtered[cursor]
        if (row) { e.preventDefault(); onOpen(row.date) }
      } else if (e.key === 'Escape') {
        // Phase 1 has no pair selection yet to clear — no-op, kept for parity
        // with the documented model once Phase 2/3 add one.
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [filtered, cursor, onOpen])

  return (
    <div style={{
      // minWidth/maxWidth pin the rail to its flex-basis: a flex item's default
      // min-width:auto lets min-content win, and real location strings ("Seattle
      // Center Key Area, 10/6/01, …") pushed the rail to ~745px, squeezing the
      // matrix. The basis alone is not enough.
      flex: `0 0 ${narrow ? 224 : 272}px`, minWidth: 0, maxWidth: narrow ? 224 : 272,
      background: 'var(--lbb-surface)',
      borderRight: '1px solid var(--lbb-border)', display: 'flex', flexDirection: 'column',
      minHeight: 0,
    }}>
      <div style={{ padding: '12px 12px 10px', borderBottom: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: 'var(--lbb-fg3)',
          }}>TRIAGE QUEUE</span>
          <span style={{ fontSize: 10.5, color: 'var(--lbb-warn-fg)' }}>{needsCount} need you</span>
        </div>
        <div style={{ display: 'flex', gap: 5, marginTop: 9, flexWrap: 'wrap' }}>
          {FILTERS.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              style={{
                background: filter === f.key ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface2)',
                border: `1px solid ${filter === f.key ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                color: filter === f.key ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                borderRadius: 999, padding: '3px 10px', font: '600 11px inherit', cursor: 'pointer',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 6, minHeight: 0 }}>
        {filtered.length === 0 && (
          <div style={{ padding: 20, textAlign: 'center', fontSize: 11.5, color: 'var(--lbb-fg3)' }}>
            Nothing here.
          </div>
        )}
        {filtered.map((row, i) => {
          const status = statusOf(row)
          const tone = STATUS_TONE[status]
          const isCursor = i === cursor
          const isOpen = row.date === selectedDate
          return (
            <button
              key={row.date}
              ref={el => { if (el) rowRefs.current.set(i, el); else rowRefs.current.delete(i) }}
              type="button"
              onClick={() => { setCursor(i); onOpen(row.date) }}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 9,
                padding: '8px 9px', borderRadius: 6, textAlign: 'left', cursor: 'pointer',
                fontFamily: 'inherit',
                background: isOpen ? 'var(--lbb-accent-soft)' : 'transparent',
                border: `1px solid ${isOpen ? 'var(--lbb-accent-mid)' : 'transparent'}`,
                boxShadow: isCursor
                  ? `inset 2px 0 0 ${isOpen ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)'}`
                  : 'none',
              }}
              onMouseEnter={e => { if (!isOpen) e.currentTarget.style.background = 'var(--lbb-surface2)' }}
              onMouseLeave={e => { if (!isOpen) e.currentTarget.style.background = 'transparent' }}
            >
              <span style={{
                flex: '0 0 7px', width: 7, height: 7, borderRadius: '50%',
                background: `var(--lbb-${tone}-bar)`,
              }} />
              <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span style={{
                  fontSize: 11.5, fontWeight: 600, fontFamily: 'var(--lbb-mono)',
                  color: isOpen ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
                }}>{row.date}</span>
                <span style={{
                  fontSize: narrow ? 10.5 : 11.5, color: 'var(--lbb-fg3)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>{row.location ?? '—'}</span>
              </span>
              <span style={{ fontSize: 11, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)' }}>
                {row.n_lbs}<span style={{ color: 'var(--lbb-fg3)' }}>&rarr;</span>
                <span style={{ color: 'var(--lbb-fg2)', fontWeight: 700 }}>
                  {familyCountByDate.get(row.date) ?? '—'}
                </span>
              </span>
            </button>
          )
        })}
      </div>

      <div style={{
        padding: '8px 12px', borderTop: '1px solid var(--lbb-border)',
        fontSize: 10.5, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)',
        display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap',
      }}>
        <Kbd>j</Kbd> / <Kbd>k</Kbd> to move · <Kbd>enter</Kbd> to open · <Kbd>esc</Kbd> to close
      </div>
    </div>
  )
}

// ── §3 Date header (incl. B3 verdict clamp) ─────────────────────────────────

function VerdictClamp({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const needsToggle = text.length > 160
  return (
    <span style={{ display: 'inline' }}>
      <span
        style={{
          display: needsToggle && !expanded ? '-webkit-box' : 'inline',
          WebkitBoxOrient: 'vertical' as React.CSSProperties['WebkitBoxOrient'],
          WebkitLineClamp: needsToggle && !expanded ? 2 : undefined,
          overflow: needsToggle && !expanded ? 'hidden' : 'visible',
          maxWidth: 640,
        }}
      >
        {text}
      </span>
      {needsToggle && (
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          style={{
            marginLeft: 6, background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--lbb-accent-mid)', font: '600 12px inherit', padding: 0,
          }}
        >
          {expanded ? 'less' : 'more'}
        </button>
      )}
    </span>
  )
}

function DateHeader({
  row, narrow, verdictText, families,
}: {
  row: DateRow | null
  narrow: boolean
  verdictText: string | null
  families: { famId: string; label: string; colorIndex: number; lbs: number[] }[]
}) {
  if (!row) {
    return (
      <div style={{
        padding: narrow ? '14px 16px 12px' : '16px 22px 14px',
        borderBottom: '1px solid var(--lbb-border)', color: 'var(--lbb-fg3)', fontSize: 12,
      }}>
        Select a date from the triage queue.
      </div>
    )
  }
  const status = statusOf(row)
  return (
    <div style={{
      display: 'flex', gap: 18, alignItems: 'flex-start', justifyContent: 'space-between',
      flexWrap: 'wrap', padding: narrow ? '14px 16px 12px' : '16px 22px 14px',
      borderBottom: '1px solid var(--lbb-border)', flex: '0 0 auto',
    }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: 19, fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg)',
          }}>{row.date}</span>
          {row.location && (
            <span style={{ fontSize: 13, color: 'var(--lbb-fg2)' }}>{row.location}</span>
          )}
          {row.run_id && <Pill tone="mute" soft>run {row.run_id}</Pill>}
        </div>
        <div style={{ marginTop: 7, display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
          <Pill tone={STATUS_TONE[status]} soft>{STATUS_LABEL[status]}</Pill>
          {verdictText && (
            <span style={{ fontSize: 12, color: 'var(--lbb-fg2)' }}>
              <VerdictClamp text={verdictText} />
            </span>
          )}
          {/* Provenance (model · run date) — dropped when unknown per README
              §10 "renders whatever is known"; the dates endpoint carries no
              model/ranAt field today. */}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 9 }}>
        {families.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {families.map(f => (
              <div key={f.famId} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 999, padding: '2px 8px', fontSize: 10.5, fontWeight: 600,
                color: 'var(--lbb-fg2)',
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: 2, background: familyColorVar(f.colorIndex),
                }} />
                {f.label}
                <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 9.5, fontWeight: 500, color: 'var(--lbb-fg3)' }}>
                  {f.lbs.map(lb => String(lb).padStart(5, '0')).join(' ')}
                </span>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="ghost" size="sm" disabled title="report.md view ships in Phase 7">
            Open report.md
          </Button>
          <Button variant="primary" size="sm" disabled title="Judgment write path ships in Phase 6">
            Accept families
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── §8 Dossier — empty state only (Phase 1 has no pair selection) ──────────

function DossierEmpty() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100%', minHeight: 0,
    }}>
      <div style={{ textAlign: 'center', maxWidth: 260 }}>
        <div style={{ fontSize: 26, color: 'var(--lbb-fg3)' }}>&#8862;</div>
        <div style={{ fontSize: 13.5, fontWeight: 700, marginTop: 8, color: 'var(--lbb-fg)' }}>
          Select a pair
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', lineHeight: 1.5, marginTop: 5 }}>
          Click any matrix cell to open the evidence dossier — every signal TapeMatch
          measured for that pair, against its threshold.
        </div>
      </div>
    </div>
  )
}

// ── §5 Similarity matrix ────────────────────────────────────────────────────
// Ported from the design's tm-parts.jsx `Matrix` (README §5 + §10.6) — logic
// only, not the raw hexes (WORK_PACKAGE D2): semantic colours come from the
// `--lbb-*` token system so the heatmap survives light mode, family colours
// come from `familyColorVar`.

const COMPACT_THRESHOLD = 20 // README §10.6: "past ~20 recordings" fitting beats filling

interface MatrixRecording {
  lb: number
  colorIndex: number
}

function cellVisual(
  sim: number | null, sameFamily: boolean, familyColor: string,
): { background: string; color: string; fontWeight: number } {
  if (sim == null) {
    return {
      background: 'repeating-linear-gradient(45deg, var(--lbb-surface2), '
        + 'var(--lbb-surface2) 4px, var(--lbb-surface) 4px, var(--lbb-surface) 8px)',
      color: 'var(--lbb-fg3)', fontWeight: 500,
    }
  }
  if (sameFamily) {
    const pct = 30 + sim * 0.55
    return {
      background: `color-mix(in oklab, ${familyColor} ${pct}%, var(--lbb-surface))`,
      color: 'var(--lbb-fg)', fontWeight: 700,
    }
  }
  const t = Math.pow(sim / 100, 0.8) * 72
  return {
    background: `color-mix(in oklab, var(--lbb-accent-mid) ${t.toFixed(0)}%, var(--lbb-surface))`,
    color: sim >= 45 ? 'var(--lbb-fg)' : 'var(--lbb-fg3)', fontWeight: 500,
  }
}

function MatrixLegend({ densityNote }: { densityNote: string | null }): React.JSX.Element {
  const swatch: React.CSSProperties = {
    display: 'inline-block', width: 13, height: 11, borderRadius: 3,
    border: '1px solid var(--lbb-border)', marginLeft: 8, verticalAlign: 'middle',
  }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap',
      marginTop: 10, fontSize: 10.5, color: 'var(--lbb-fg3)',
    }}>
      <span style={{
        ...swatch, marginLeft: 0,
        background: 'color-mix(in oklab, var(--lbb-accent-mid) 12%, var(--lbb-surface))',
      }} /> unrelated 0–40
      <span style={{
        ...swatch,
        background: 'color-mix(in oklab, var(--lbb-accent-mid) 55%, var(--lbb-surface))',
      }} /> check 40–85
      <span style={{ ...swatch, background: familyColorVar(0) }} /> same family 85–100 · tinted by family
      <span style={{
        ...swatch,
        background: 'repeating-linear-gradient(45deg, var(--lbb-surface2), '
          + 'var(--lbb-surface2) 3px, var(--lbb-surface) 3px, var(--lbb-surface) 6px)',
      }} /> n/c not comparable
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginLeft: 8 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%', background: 'var(--lbb-bad-bar)',
          border: '1px solid var(--lbb-bg)', display: 'inline-block',
        }} /> LB-page conflict
      </span>
      {densityNote && (
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)',
        }}>{densityNote}</span>
      )}
    </div>
  )
}

function Matrix({
  recordings, pairsByKey, selected, onSelect, familyCount,
}: {
  recordings: MatrixRecording[]
  pairsByKey: Map<string, PairRow>
  selected: SelectedPair | null
  onSelect: (pair: SelectedPair | null) => void
  familyCount: number
}): React.JSX.Element {
  const n = recordings.length
  const compact = n > COMPACT_THRESHOLD
  const cellRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const [focusPos, setFocusPos] = useState<[number, number]>(() => [0, n > 1 ? 1 : 0])

  // Keep the roving-tabindex position in range if the recording list changes
  // (e.g. switching dates without unmounting the screen).
  useEffect(() => {
    setFocusPos(([i, j]) => [Math.min(i, n - 1), Math.min(j, n - 1)])
  }, [n])

  const move = (i: number, j: number, di: number, dj: number, e: React.KeyboardEvent) => {
    e.preventDefault()
    e.stopPropagation() // don't let the triage rail's j/k/arrow handler also fire
    let ni = i, nj = j
    for (let step = 0; step < n; step++) {
      ni = (ni + di + n) % n
      nj = (nj + dj + n) % n
      if (ni !== nj) break
    }
    setFocusPos([ni, nj])
    cellRefs.current.get(`${ni}-${nj}`)?.focus()
  }

  return (
    // 760px cap on the normal wrap — §10.6 describes compact mode as the state
    // that "drops the 760px cap", so the default carries it. Without it a
    // 6-recording date stretches cells to ~118px and pushes the legend and the
    // speed strip below the fold.
    <div style={{ overflowX: compact ? 'auto' : 'visible', maxWidth: compact ? undefined : 760 }}>
      <div
        role="grid"
        aria-label="Recording similarity matrix"
        style={{
          display: 'grid',
          gridTemplateColumns: compact
            ? `46px repeat(${n}, 22px)`
            : `52px repeat(${n}, minmax(0,1fr))`,
          gap: compact ? 1 : 2,
          width: compact ? 46 + n * 22 + (n + 1) : undefined,
        }}
      >
        <div role="presentation" />
        {recordings.map(r => (
          <div
            key={`h${r.lb}`}
            role="columnheader"
            title={`LB-${shortId(r.lb)}`}
            style={compact ? {
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'flex-end', gap: 2, paddingBottom: 3, minWidth: 0,
              writingMode: 'vertical-rl', transform: 'rotate(180deg)',
              font: '600 8.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
              letterSpacing: '-0.02em',
            } : {
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'flex-end', gap: 2, paddingBottom: 3, minWidth: 0,
              font: '600 10px var(--lbb-mono)', color: 'var(--lbb-fg3)',
            }}
          >
            <span style={{
              width: 8, height: 8, borderRadius: 2, background: familyColorVar(r.colorIndex),
              flex: '0 0 auto',
            }} />
            <span>{shortId(r.lb)}</span>
          </div>
        ))}
        {recordings.map((a, i) => (
          <React.Fragment key={`r${a.lb}`}>
            <div
              role="rowheader"
              title={`LB-${shortId(a.lb)}`}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                gap: compact ? 3 : 5, paddingRight: compact ? 3 : 5,
                font: `600 ${compact ? '8.5px' : '10px'} var(--lbb-mono)`,
                color: 'var(--lbb-fg3)', minWidth: 0,
              }}
            >
              <span>{shortId(a.lb)}</span>
              <span style={{
                width: 8, height: 8, borderRadius: 2, background: familyColorVar(a.colorIndex),
                flex: '0 0 auto',
              }} />
            </div>
            {recordings.map((b, j) => {
              if (i === j) {
                return (
                  <div
                    key={`${a.lb}-${b.lb}`}
                    role="gridcell"
                    style={{
                      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                      borderRadius: compact ? 2 : 4, aspectRatio: '1',
                    }}
                  />
                )
              }
              const p = pairsByKey.get(pairKey(a.lb, b.lb)) ?? null
              const sim = p?.similarity_pct ?? null
              const sameFamily = a.colorIndex === b.colorIndex
              const conflict = !!p && p.lb_says_same === true && p.same_family === false
              const isSel = !!selected
                && ((selected.lbA === a.lb && selected.lbB === b.lb)
                  || (selected.lbA === b.lb && selected.lbB === a.lb))
              const dim = !!selected && !isSel
                && selected.lbA !== a.lb && selected.lbB !== a.lb
                && selected.lbA !== b.lb && selected.lbB !== b.lb
              const visual = cellVisual(sim, sameFamily, familyColorVar(a.colorIndex))
              const isFocus = focusPos[0] === i && focusPos[1] === j
              const simLabel = sim == null ? 'not comparable' : `${sim} percent similar`
              const famLabel = sameFamily ? 'same family' : 'different family'
              let title = `LB-${shortId(a.lb)} × LB-${shortId(b.lb)}`
                + (sim == null ? ' — not comparable' : ` — ${sim}%`)
              if (conflict && p?.lb_relation_text) title += ` · LB page: ${p.lb_relation_text}`
              return (
                <button
                  key={`${a.lb}-${b.lb}`}
                  ref={el => {
                    const key = `${i}-${j}`
                    if (el) cellRefs.current.set(key, el); else cellRefs.current.delete(key)
                  }}
                  type="button"
                  role="gridcell"
                  tabIndex={isFocus ? 0 : -1}
                  aria-label={`LB-${shortId(a.lb)} by LB-${shortId(b.lb)}, ${simLabel}, ${famLabel}`
                    + (conflict ? ', LB page conflict' : '')}
                  aria-selected={isSel}
                  title={title}
                  onFocus={() => setFocusPos([i, j])}
                  onKeyDown={e => {
                    if (e.key === 'ArrowRight') move(i, j, 0, 1, e)
                    else if (e.key === 'ArrowLeft') move(i, j, 0, -1, e)
                    else if (e.key === 'ArrowDown') move(i, j, 1, 0, e)
                    else if (e.key === 'ArrowUp') move(i, j, -1, 0, e)
                  }}
                  onClick={() => onSelect(isSel ? null : { lbA: a.lb, lbB: b.lb })}
                  style={{
                    position: 'relative', aspectRatio: '1', minWidth: 0, padding: 0,
                    cursor: 'pointer', borderRadius: compact ? 2 : 4,
                    border: isSel ? '2px solid var(--lbb-fg)' : '1px solid var(--lbb-border)',
                    zIndex: isSel ? 1 : undefined,
                    font: compact ? '500 0 var(--lbb-mono)'
                      : '500 clamp(9px,1vw,11.5px) var(--lbb-mono)',
                    transition: 'opacity .12s',
                    opacity: dim ? 0.3 : 1,
                    background: visual.background, color: visual.color, fontWeight: visual.fontWeight,
                  }}
                >
                  {sim == null
                    ? <span style={{ fontSize: compact ? 9 : '0.85em' }}>n/c</span>
                    : sim}
                  {conflict && (
                    <span style={{
                      position: 'absolute', top: 2, right: 2, width: 7, height: 7,
                      borderRadius: '50%', background: 'var(--lbb-bad-bar)',
                      border: '1px solid var(--lbb-bg)',
                    }} />
                  )}
                </button>
              )
            })}
          </React.Fragment>
        ))}
      </div>
      <MatrixLegend densityNote={compact
        ? `${n} recordings · ${familyCount} families · ${(n * (n - 1)) / 2} pairs`
          + ' · values in tooltip below 28px'
        : null}
      />
    </div>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────────

export function ScreenTapeMatchCuration(): React.JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedDate = searchParams.get('date')
  const cursorIndexRef = useRef(0)

  const width = useViewportWidth()
  const narrowRail = width <= 1380
  const narrowDossier = width <= 1520

  const { data: datesData } = useQuery({
    queryKey: ['tapematch-dates'],
    queryFn: () => fetch(`${BASE}/api/tapematch/dates`).then(r => r.json()),
    staleTime: 30_000,
  })
  const allDates: DateRow[] = datesData?.dates ?? []

  const { data: crawlData } = useQuery({
    queryKey: ['tapematch-crawl-status'],
    queryFn: () => fetch(`${BASE}/api/tapematch/crawl/status`).then(r => r.json()),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })
  const crawl: CrawlStatus | undefined = crawlData

  const selectedRow = selectedDate ? allDates.find(d => d.date === selectedDate) ?? null : null

  const { data: analysisData } = useQuery({
    queryKey: ['tapematch-curation-analysis', selectedDate],
    queryFn: () => fetch(`${BASE}/api/tapematch/analysis?date=${encodeURIComponent(selectedDate as string)}`).then(r => r.json()),
    enabled: !!selectedDate,
    staleTime: 30_000,
  })
  const verdictText: string | null = (analysisData as AnalysisResponse | undefined)?.verdict?.reason ?? null

  const { data: familiesData } = useQuery({
    queryKey: ['tapematch-families-all'],
    queryFn: () => fetch(`${BASE}/api/tapematch/families`).then(r => r.json()),
    staleTime: 60_000,
  })
  const allFamilies: FamilyRow[] = familiesData ?? []

  const familyCountByDate = useMemo(() => {
    const byDate = new Map<string, Set<string>>()
    for (const f of allFamilies) {
      const set = byDate.get(f.concert_date) ?? new Set<string>()
      set.add(f.fam_id)
      byDate.set(f.concert_date, set)
    }
    return new Map(Array.from(byDate, ([date, set]) => [date, set.size]))
  }, [allFamilies])

  const dateFamilies = useMemo(() => {
    if (!selectedDate) return []
    const byFam = new Map<string, { famId: string; label: string; lbs: number[] }>()
    for (const f of allFamilies) {
      if (f.concert_date !== selectedDate) continue
      const entry = byFam.get(f.fam_id) ?? { famId: f.fam_id, label: f.fam_label ?? f.fam_id, lbs: [] }
      entry.lbs.push(f.lb_number)
      byFam.set(f.fam_id, entry)
    }
    return Array.from(byFam.values())
      .sort((a, b) => a.famId.localeCompare(b.famId))
      .map((f, i) => ({ ...f, colorIndex: i, lbs: f.lbs.sort((a, b) => a - b) }))
  }, [allFamilies, selectedDate])

  // §5 matrix data. Family-ordered recording list is the existing
  // `dateFamilies` memo, flattened — families are already sorted by famId
  // with each family's lbs sorted ascending, so this preserves adjacency.
  const recordings: MatrixRecording[] = useMemo(
    () => dateFamilies.flatMap(f => f.lbs.map(lb => ({ lb, colorIndex: f.colorIndex }))),
    [dateFamilies],
  )

  const {
    data: pairsData, isLoading: pairsLoading, isError: pairsError,
  } = useQuery({
    queryKey: ['tapematch-curation-pairs', selectedDate],
    queryFn: () => fetch(`${BASE}/api/tapematch/pairs?date=${encodeURIComponent(selectedDate as string)}`)
      .then(r => r.json()),
    enabled: !!selectedDate,
    staleTime: 15_000,
  })
  const pairsByKey = useMemo(() => {
    const map = new Map<string, PairRow>()
    const pairs = (pairsData as PairsResponse | undefined)?.pairs ?? []
    for (const p of pairs) map.set(pairKey(p.lb_a, p.lb_b), p)
    return map
  }, [pairsData])

  // Lifted here (not local to Matrix) because Phase 3's dossier will read it
  // too — the dossier rendering itself stays untouched (empty state only)
  // until that phase lands.
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)
  useEffect(() => { setSelectedPair(null) }, [selectedDate])

  const openDate = (date: string) => setSearchParams({ date })

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <TopBar crawl={crawl} />
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <TriageRail
          rows={allDates}
          narrow={narrowRail}
          selectedDate={selectedDate}
          onOpen={openDate}
          cursorIndexRef={cursorIndexRef}
          familyCountByDate={familyCountByDate}
        />
        <div style={{
          flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column',
          minHeight: 0, overflowY: 'auto', position: 'relative',
        }}>
          <DateHeader row={selectedRow} narrow={narrowRail} verdictText={verdictText} families={dateFamilies} />
          <div style={{
            display: 'grid',
            gridTemplateColumns: narrowDossier ? 'minmax(0,1fr)' : 'minmax(0,1fr) 350px',
            flex: 1, minHeight: 0,
          }}>
            <div style={{ padding: narrowRail ? '6px 16px 22px' : '6px 22px 26px', minHeight: 0 }}>
              <CurationSection
                title="Similarity matrix"
                hint="family-ordered · % is the banded corr+embedding blend · click a cell for the dossier"
              >
                {!selectedRow ? (
                  <SectionPlaceholder label="Select a date from the triage queue." />
                ) : recordings.length === 0 ? (
                  // README §10.4 — known date, nothing circulating; not an error.
                  <SectionPlaceholder label={
                    'No recordings for this date — nothing to compare yet.'
                  } />
                ) : recordings.length === 1 ? (
                  // README §10.5 — one recording means zero pairs. The full
                  // .tmSolo write-path card is Phase 6 scope; here we just
                  // name the threshold so the state doesn't read as a bug.
                  <SectionPlaceholder label={
                    `Only one recording (LB-${shortId(recordings[0].lb)}) on this date — `
                    + 'pair views only appear from two recordings up.'
                  } />
                ) : pairsLoading ? (
                  <SectionPlaceholder label="Loading pairs…" />
                ) : pairsError ? (
                  <SectionPlaceholder label="Couldn't load this date's pairs." />
                ) : (
                  <Matrix
                    recordings={recordings}
                    pairsByKey={pairsByKey}
                    selected={selectedPair}
                    onSelect={setSelectedPair}
                    familyCount={dateFamilies.length}
                  />
                )}
              </CurationSection>
              <CurationSection
                title="Speed & lag"
                hint="why a pair's correlation looks the way it does"
              >
                <SectionPlaceholder label="Speed & lag strip — Phase 4" />
              </CurationSection>
              <CurationSection
                title="Analysis verdict"
                hint="parsed from analysis.md — the human/AI review layer"
              >
                <SectionPlaceholder label="Analysis verdict cards — Phase 5" />
              </CurationSection>
            </div>
            {!narrowDossier && (
              <div style={{
                borderLeft: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
                padding: 16, overflowY: 'auto', minHeight: 0,
              }}>
                <DossierEmpty />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
