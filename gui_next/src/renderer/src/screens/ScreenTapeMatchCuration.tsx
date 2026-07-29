// TapeMatch Curation screen — Phases 1–6.
//
// Built per instructions/design_handoff_tapematch_curation/{README,
// WORK_PACKAGE,DESIGN_ANSWERS_B}.md. D1 is complete as of 2026-07-28: this
// screen reached parity at Phase 6 and replaced the read-only
// ScreenTapeMatch.tsx (deleted) at /tapematch, taking over its nav entry;
// /tapematch/curation redirects here. Three things came across in the swap
// because only the old screen had them: crawl start/stop (§1 top bar), the
// /library?lb= deep-link (dossier LB headings), and the raw analysis.md
// disclosure under §7.
//
// NOT internationalised — every string here is hardcoded English (TODO-275).
//
// Phase 1 scope: §1 top bar, §2 triage queue rail (incl. keybindings), §3
// date header (incl. DESIGN_ANSWERS_B §B3 verdict clamp), §4 section
// wrapper, and the three-column work grid + its two breakpoints (rail
// 272→224px at ≤1380px, dossier docked→collapsed at ≤1520px). The work
// column renders labelled empty placeholders for the matrix / speed strip /
// verdict cards (Phases 2, 4, 5).
//
// Phase 2 added §5's similarity matrix; Phase 3 the §8 dossier — verdict
// block, conflict callout, A/B player, evidence bars, LB-page claim and the
// judgment control — in both its docked and drawer forms.
//
// Phase 4 added §6's speed & lag strip — signed-√ ppm axis, A4 glyph
// vocabulary, greedy lane packing — on a new GET /api/tapematch/sources.
// Phase 5 added §7's verdict cards, parsed client-side in lib/analysisMd.ts.
//
// Phase 6 wires the write path: the judgment control's Save (POST
// /api/tapematch/pairs/judgment) with §10.7's save-status line, and §3's
// `Accept families` (POST /api/tapematch/dates/accept), which records the
// date in observations.db's additive `curation_accepts` table and gives the
// triage rail's fourth state, `curated`, its only path in (Q4).
// Phase 7 adds §11's report.md overlay — `Open report.md` in the date header
// mounts components/tapematch/ReportSheet.tsx over the workspace, off the new
// GET /api/tapematch/report. Run diff (§12) remains a placeholder.

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Pill, Chip, Button, Kbd } from '../components'
import { familyColorVar } from '../lib/tokens'
import {
  parseAnalysisMd, decodeEntities,
  type AnalysisDoc, type CardBlock, type VerdictCard as ParsedCard,
} from '../lib/analysisMd'
import { ReportSheet } from '../components/tapematch/ReportSheet'

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
  // Phase 6 — observations.db `curation_accepts`, via POST
  // /api/tapematch/dates/accept. Optional on the type because an older
  // backend (or a locked observations.db) simply omits them.
  curated?: boolean
  curated_at?: string | null
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
  log_tail?: string[]
}

interface AnalysisResponse {
  verdict?: { needs_review: boolean | null; reason: string | null }
  analysis_md?: string | null
}

interface ReportResponse {
  run_id?: string | null
  run_dir?: string | null
  report_md?: string | null
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
  // §8d secondary evidence — live-read from observations.db alongside
  // lb_says_same (they are not in the app DB's tapematch_pairs), so null
  // whenever that enrichment falls back.
  windowed_frac: number | null
  hiss_median: number | null
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
// clean.
//
// Phase 6 populates `curated`, and it wins over everything else: it is the
// curator's own terminal verdict on the date, so a date that was accepted
// while still flagged `needs_review` leaves the "needs you" queue — that is
// exactly what accepting means.
type TriageStatus = 'conflict' | 'review' | 'clean' | 'curated'

function statusOf(row: DateRow): TriageStatus {
  if (row.curated) return 'curated'
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

// §10.3 — the rail's empty state states the outcome in the *filter's own
// terms* rather than a bare "Nothing here.", because on three of the four
// filters an empty list is good news, not a dead end.
const EMPTY_FILTER_COPY: Record<FilterKey, [string, string]> = {
  needs: ['Nothing needs you.', 'Every flagged date on this page is resolved.'],
  conflict: ['No conflicts left.', 'Every disagreement on this page is resolved.'],
  curated: ['Nothing accepted yet.', 'Dates you accept with `Accept families` collect here.'],
  all: ['No dates yet.', 'TapeMatch has not synced any analysed dates into the app DB.'],
}

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

// ── §10 edge and transient states (Phase 9) ─────────────────────────────────
// The skeleton primitive is §10.1's: a faint 4.5% sweep, deliberately dimmer
// than a normal shimmer so it doesn't fight the matrix's own colour coding once
// cells populate, and dropped entirely under prefers-reduced-motion.

const SKELETON_CSS = `
@keyframes lbbSkSweep { from { transform: translateX(-100%) } to { transform: translateX(100%) } }
.lbbSk { position: relative; overflow: hidden; background: var(--lbb-surface2); border-radius: 4px; }
.lbbSk::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.045) 45%, transparent);
  animation: lbbSkSweep 1.25s cubic-bezier(.4,0,.2,1) infinite;
}
@media (prefers-reduced-motion: reduce) {
  .lbbSk::after { animation: none; background: rgba(255,255,255,.02); }
}
@keyframes lbbDrawerIn { from { transform: translateX(14px); opacity: .4 } to { transform: none; opacity: 1 } }
.lbbDrawer { animation: lbbDrawerIn 140ms cubic-bezier(.4,0,.2,1); }
@media (prefers-reduced-motion: reduce) { .lbbDrawer { animation: none; } }
`

function Skeleton({
  w, h, style,
}: { w?: number | string; h: number; style?: React.CSSProperties }) {
  return <div className="lbbSk" style={{ width: w ?? '100%', height: h, ...style }} />
}

/**
 * §10.2 / §10.4 — the generic state block: one glyph, a head, a body that names
 * both cause and recovery, an optional technical detail (this audience is
 * technical; give them the real error) and optional actions.
 */
function CurationState({
  glyph, tone, head, body, detail, actions,
}: {
  glyph: string
  tone: 'bad' | 'mute'
  head: string
  body: string
  detail?: string
  actions?: React.ReactNode
}) {
  return (
    <div style={{ maxWidth: 400, margin: '0 auto', paddingTop: 72, textAlign: 'center' }}>
      <div style={{
        fontSize: 26, color: tone === 'bad' ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)',
      }}>{glyph}</div>
      <div style={{ fontSize: 13.5, fontWeight: 700, marginTop: 8, color: 'var(--lbb-fg)' }}>
        {head}
      </div>
      <div style={{ fontSize: 11.5, marginTop: 6, lineHeight: 1.6, color: 'var(--lbb-fg3)' }}>
        {body}
      </div>
      {detail && (
        <pre style={{
          textAlign: 'left', margin: '11px 0 0', padding: '8px 11px', borderRadius: 6,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          font: '500 10.5px/1.5 var(--lbb-mono)', color: 'var(--lbb-fg3)',
          whiteSpace: 'pre-wrap',
        }}>{detail}</pre>
      )}
      {actions && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 13 }}>
          {actions}
        </div>
      )}
    </div>
  )
}

/**
 * §10.1 — the matrix skeleton renders the *real* grid, so nothing reflows when
 * the measurements arrive: same template, same `aspect-ratio:1` cells, same
 * diagonal treatment, N taken from the date's recording count (known from the
 * families query long before any pair measurement is).
 */
function MatrixSkeleton({ recordings }: { recordings: MatrixRecording[] }) {
  const n = recordings.length
  const compact = n > COMPACT_THRESHOLD
  const pairs = (n * (n - 1)) / 2
  return (
    <div style={{ overflowX: compact ? 'auto' : 'visible', maxWidth: compact ? undefined : 760 }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: compact ? `46px repeat(${n}, 22px)` : `52px repeat(${n}, minmax(0,1fr))`,
        gap: compact ? 1 : 2,
        width: compact ? 46 + n * 22 + (n + 1) : undefined,
      }}>
        <div />
        {recordings.map(r => (
          <div key={`hs${r.lb}`} style={{
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center', paddingBottom: 3,
          }}>
            <Skeleton w={compact ? 8 : 34} h={8} />
          </div>
        ))}
        {recordings.map((a, i) => (
          <React.Fragment key={`rs${a.lb}`}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
              paddingRight: compact ? 3 : 5,
            }}>
              <Skeleton w={compact ? 34 : 34} h={8} />
            </div>
            {recordings.map((b, j) => (
              i === j ? (
                <div key={`s${a.lb}-${b.lb}`} style={{
                  background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                  borderRadius: compact ? 2 : 4, aspectRatio: '1',
                }} />
              ) : (
                <div key={`s${a.lb}-${b.lb}`} className="lbbSk" style={{
                  border: '1px solid var(--lbb-border)', borderRadius: compact ? 2 : 4,
                  aspectRatio: '1',
                }} />
              )
            ))}
          </React.Fragment>
        ))}
      </div>
      {/* §10.1 asks for `measuring 45 pairs · 31 done`. The pair count is
          knowable up front (n(n−1)/2); the done count is not — the route
          answers once with the whole set, so there is no partial progress to
          report and inventing one would be a fake progress bar. */}
      <div style={{
        marginTop: 8, font: '500 10.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
      }}>
        measuring {pairs} pair{pairs === 1 ? '' : 's'}…
      </div>
    </div>
  )
}

/**
 * §10.5 — one recording means zero pairs, so the date collapses to a solo card
 * rather than rendering three empty components. Rows the run didn't record are
 * dropped rather than shown blank.
 */
function SoloCard({
  lb, color, source,
}: { lb: number; color: string; source: SourceRow | null }) {
  const rows: [string, string][] = []
  if (source?.folder_name) rows.push(['Folder', source.folder_name])
  if (source?.speed_kind) {
    rows.push(['Speed', source.speed_ppm != null && source.speed_kind !== 'speed-unknown'
      ? `${source.speed_ppm > 0 ? '+' : ''}${source.speed_ppm.toLocaleString()} ppm · ${source.speed_kind}`
      : source.speed_kind])
  }
  return (
    <div style={{
      maxWidth: 520, border: '1px solid var(--lbb-border)', borderRadius: 8,
      background: 'var(--lbb-surface2)', padding: '13px 15px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
        <span style={{ font: '700 13px var(--lbb-mono)', color: 'var(--lbb-fg)' }}>
          LB-{shortId(lb)}
        </span>
        <Pill tone="ok" soft>reference</Pill>
      </div>
      {rows.length > 0 && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px',
          marginTop: 11, fontSize: 11,
        }}>
          {rows.map(([k, v]) => (
            <React.Fragment key={k}>
              <span style={{ color: 'var(--lbb-fg3)' }}>{k}</span>
              <span style={{ color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>{v}</span>
            </React.Fragment>
          ))}
        </div>
      )}
      <div style={{
        borderTop: '1px solid var(--lbb-border)', paddingTop: 10, marginTop: 11,
        fontSize: 11, lineHeight: 1.6, color: 'var(--lbb-fg3)',
      }}>
        Sole recording, so it becomes its own family with no evidence needed.
        Accepting records the family without a human pair judgment.
      </div>
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

function TopBar({
  crawl, judgedCount, date,
}: {
  crawl: CrawlStatus | undefined
  judgedCount: number
  date: string | null
}) {
  const dotColor = crawl?.running ? 'var(--lbb-warn-bar)' : 'var(--lbb-ok-bar)'
  const statusWord = crawl?.running ? 'running' : 'idle'
  // Crawl start/stop, carried over from the retired ScreenTapeMatch. The
  // design's §1 shows crawl state read-only, but this was the only place in
  // the app that could start or stop the library crawl — retiring the old
  // screen without it would have removed the control outright. The scripts
  // remain the single-instance authority; 409 means one is already running.
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<'start' | 'stop' | null>(null)
  const [crawlMsg, setCrawlMsg] = useState<string | null>(null)

  async function crawlAction(action: 'start' | 'stop'): Promise<void> {
    setPending(action)
    setCrawlMsg(null)
    try {
      const res = await fetch(`${BASE}/api/tapematch/crawl/${action}`, { method: 'POST' })
      if (action === 'start' && res.status === 409) setCrawlMsg('already running')
      else if (!res.ok) setCrawlMsg(`couldn't ${action} the crawl`)
      else if (action === 'stop') setCrawlMsg('stopping…')
      queryClient.invalidateQueries({ queryKey: ['tapematch-crawl-status'] })
    } catch {
      setCrawlMsg(`couldn't ${action} the crawl`)
    } finally {
      setPending(null)
    }
  }
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
        {crawl && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Button
              variant="ghost" size="sm"
              disabled={crawl.running || pending !== null}
              onClick={() => crawlAction('start')}
              title={crawl.log_tail?.length ? crawl.log_tail.join('\n') : 'no crawl log yet'}
            >{pending === 'start' ? 'Starting…' : 'Start crawl'}</Button>
            <Button
              variant="ghost" size="sm"
              disabled={!crawl.running || pending !== null}
              onClick={() => crawlAction('stop')}
            >{pending === 'stop' ? 'Stopping…' : 'Stop'}</Button>
            {crawlMsg && (
              <span style={{ fontSize: 10.5, color: 'var(--lbb-fg3)' }}>{crawlMsg}</span>
            )}
          </div>
        )}
        {/* §3's judgment pill. The design counts judgments *queued* locally;
            D4's explicit Save means nothing is ever queued, so this counts
            what is actually on disk for the open date — the same number
            `Accept families · n judged` carries. */}
        {date && judgedCount > 0 && (
          <Pill tone="info" soft>
            {judgedCount} judged
          </Pill>
        )}
      </div>
    </div>
  )
}

// ── §2 Triage queue rail ────────────────────────────────────────────────────

function TriageRail({
  rows, narrow, selectedDate, onOpen, cursorIndexRef, familyCountByDate, loading,
}: {
  rows: DateRow[]
  narrow: boolean
  /** §10.1 — /api/tapematch/dates is slow (3,195 dates); skeleton, don't lie. */
  loading: boolean
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
        {loading && rows.length === 0 && (
          // §10.1 — the rail resolves first and is a cheap-looking query that
          // isn't: rendering the empty state while it is in flight told the
          // curator the queue was empty. Skeleton rows keep the shape.
          <div aria-hidden style={{ padding: 4 }}>
            {Array.from({ length: 9 }, (_, i) => (
              <div key={i} style={{
                display: 'flex', flexDirection: 'column', gap: 6,
                padding: '9px 8px', borderBottom: '1px solid var(--lbb-border)',
              }}>
                <Skeleton w={92} h={9} />
                <Skeleton w={narrow ? 130 : 168} h={8} />
              </div>
            ))}
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div style={{ padding: '20px 14px', textAlign: 'center' }}>
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', fontWeight: 600 }}>
              {EMPTY_FILTER_COPY[filter][0]}
            </div>
            <div style={{ fontSize: 10.5, marginTop: 6, lineHeight: 1.5, color: 'var(--lbb-fg3)' }}>
              {EMPTY_FILTER_COPY[filter][1]}
            </div>
            {filter !== 'all' && (
              <button
                type="button"
                onClick={() => setFilter('all')}
                style={{
                  marginTop: 9, background: 'transparent', border: 'none', padding: 0,
                  font: '600 11px inherit', color: 'var(--lbb-accent-mid)', cursor: 'pointer',
                }}
              >Show all dates</button>
            )}
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

// §3 `Accept families` outcome, mirroring §10.7's save-status vocabulary.
type AcceptState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'accepted'; at: string }
  | { kind: 'failed'; message: string }

function DateHeader({
  row, narrow, verdictText, families, judgedCount, soloDate, onAccept, accept,
  onOpenReport, reportButtonRef, dataState,
}: {
  /**
   * §10.2 / §10.4 — the header keeps rendering what is known (date, venue) and
   * overrides only the status pill and the verdict line: `unavailable` (bad)
   * when the date's artifacts didn't come back, `no recordings` (mute) when the
   * show is known but nothing is circulating.
   */
  dataState: 'ok' | 'error' | 'empty'
  row: DateRow | null
  narrow: boolean
  verdictText: string | null
  families: { famId: string; label: string; colorIndex: number; lbs: number[] }[]
  judgedCount: number
  soloDate: boolean
  onAccept: () => void
  accept: AcceptState
  onOpenReport: () => void
  /** Wraps the `Open report.md` button so §11 can restore focus on close. */
  reportButtonRef: React.RefObject<HTMLSpanElement>
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
  const statusTone = dataState === 'error' ? 'bad' : dataState === 'empty' ? 'mute' : STATUS_TONE[status]
  const statusLabel = dataState === 'error' ? 'unavailable'
    : dataState === 'empty' ? 'no recordings' : STATUS_LABEL[status]
  const verdictLine = dataState === 'error' ? "Couldn't load this date's analysis"
    : dataState === 'empty' ? 'Known date · nothing circulating in the library'
      : verdictText
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
          {row.run_id && dataState === 'ok' && <Pill tone="mute" soft>run {row.run_id}</Pill>}
        </div>
        <div style={{ marginTop: 7, display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
          <Pill tone={statusTone} soft>{statusLabel}</Pill>
          {verdictLine && (
            <span style={{ fontSize: 12, color: 'var(--lbb-fg2)' }}>
              <VerdictClamp text={verdictLine} />
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
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <span ref={reportButtonRef}>
              <Button
                variant="ghost" size="sm" onClick={onOpenReport}
                title="The run's generated report.md, annotated with your judgments"
              >
                Open report.md
              </Button>
            </span>
            {/* §3: disabled until at least one pair judgment exists; §10.5
                special-cases a single-recording date to enabled, because the
                rule exists to stop rubber-stamping pair decisions and there
                are no pair decisions to stamp. */}
            <Button
              variant="primary" size="sm"
              disabled={(judgedCount === 0 && !soloDate) || accept.kind === 'saving'}
              onClick={onAccept}
              title={
                judgedCount === 0 && !soloDate
                  ? 'Judge at least one pair first'
                  : "Records this date's families in the app DB · tapematch_date_curation"
              }
            >
              {judgedCount > 0 ? `Accept families · ${judgedCount} judged` : 'Accept families'}
            </Button>
          </div>
          {accept.kind !== 'idle' && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, fontSize: 10,
              color: accept.kind === 'failed' ? 'var(--lbb-bad-fg)'
                : accept.kind === 'accepted' ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)',
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: accept.kind === 'failed' ? 'var(--lbb-bad-bar)'
                  : accept.kind === 'accepted' ? 'var(--lbb-ok-bar)' : 'var(--lbb-fg3)',
              }} />
              {accept.kind === 'saving' && 'Accepting…'}
              {accept.kind === 'accepted' && `Accepted ${accept.at}`}
              {accept.kind === 'failed' && accept.message}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── §8 Dossier ──────────────────────────────────────────────────────────────
// Vertical order follows the design's own tm-parts.jsx `Dossier`, which
// (unlike AB_PLAYER_AND_NOTES.md's description of it) already carries an
// ABPlayer: header → verdict → conflict callout → A/B player → evidence bars
// → LB page says → judgment. That supersedes WORK_PACKAGE D3's provisional
// "A/B sits just above the judgment control" — D3 said to revisit if design
// answered, and the prototype answers by placement. DESIGN_ANSWERS A9 then
// fixes the A/B block's min-height at 96px so switching between eligible and
// ineligible pairs doesn't move the judgment buttons under the cursor.

const CORR_THRESHOLD = 0.45 // README §8d bar 1 — the cluster threshold
const WIN_THRESHOLD = 0.60 // bar 2 — secondary clustering gate
const FP_BAND: [number, number] = [0.15, 0.50] // bar 4 — coincidence range

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

// §8d evidence bar. `value` is null-tolerant: a null renders `n/c` with an
// empty track, which is the speed-unknown case, not a zero measurement.
function EvidenceBar({
  label, value, thresh, band, demote, note,
}: {
  label: string
  value: number | null
  thresh?: number
  band?: [number, number]
  demote?: boolean
  note: string
}): React.JSX.Element {
  const pct = value == null ? 0 : Math.min(100, value * 100)
  return (
    <div style={{ marginBottom: 11, opacity: demote ? 0.72 : 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--lbb-fg2)' }}>{label}</span>
        <span style={{ font: '600 11.5px var(--lbb-mono)', color: 'var(--lbb-fg)' }}>
          {value == null ? 'n/c' : value.toFixed(3)}
        </span>
      </div>
      <div style={{
        position: 'relative', height: 9, borderRadius: 999, marginTop: 4,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        overflow: 'visible',
      }}>
        {band && (
          <span style={{
            position: 'absolute', top: 0, bottom: 0,
            left: `${band[0] * 100}%`, width: `${(band[1] - band[0]) * 100}%`,
            background: 'repeating-linear-gradient(45deg, transparent, transparent 3px, '
              + 'var(--lbb-fg3) 3px, var(--lbb-fg3) 6px)',
            opacity: 0.35,
          }} />
        )}
        {value != null && (
          <span style={{
            position: 'absolute', top: 0, bottom: 0, left: 0, width: `${pct}%`,
            borderRadius: 999,
            background: demote ? 'var(--lbb-mute-bar)' : 'var(--lbb-accent-mid)',
          }} />
        )}
        {thresh != null && (
          <span style={{
            position: 'absolute', top: -3, bottom: -3, left: `${thresh * 100}%`,
            width: 2, borderRadius: 1, background: 'var(--lbb-warn-bar)',
          }} />
        )}
      </div>
      <div style={{
        fontSize: 10, color: 'var(--lbb-fg3)', marginTop: 4, lineHeight: 1.4,
        textWrap: 'pretty',
      }}>{note}</div>
    </div>
  )
}

// §8d bar 1's note is the pedagogical heart of the panel — it says *why* the
// algorithm did what it did, so it branches on how this pair was actually
// clustered. "Secondary link" isn't a stored flag anywhere: a pair merged on
// primary evidence has corr ≥ 0.45 by definition, so same-family with corr
// below the threshold is exactly the population the secondary path merged.
function isSecondaryLink(pair: PairRow | null): boolean {
  if (!pair || !pair.same_family) return false
  return pair.corr == null || pair.corr < CORR_THRESHOLD
}

function corrNote(pair: PairRow | null): string {
  const corr = pair?.corr ?? null
  if (corr == null) return 'not measured — speed-unknown source'
  if (corr >= CORR_THRESHOLD) return '≥ 0.45 cluster threshold — merges on primary evidence'
  if (isSecondaryLink(pair)) return "below threshold — that's why the secondary path ran"
  return 'below the 0.45 cluster threshold'
}

// ── A/B listening (carried forward from ScreenTapeMatch's AbPlayerPanel) ────
// Same mechanic: one performance-time-aligned WAV per source from POST
// /api/ab_clip, both <audio> elements started together and kept aligned, so
// the A/B switch is an instant mute swap rather than a reload/reseek.
// Restyled to the design's tmAB block and given A9's reserved 96px height.

const AB_NUMBER_INPUT_STYLE: React.CSSProperties = {
  width: 62, padding: '4px 6px', borderRadius: 5,
  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
  color: 'var(--lbb-fg)', font: '500 11.5px var(--lbb-mono)', outline: 'none',
}

const AB_FIELD_STYLE: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 3,
  font: '500 9.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
}

interface AbClipResult {
  clip_a: string
  clip_b: string
  t_sec: number
  dur_sec: number
}

function AbPlayer({
  lbA, lbB, eligible, date,
}: { lbA: number; lbB: number; eligible: boolean; date: string }): React.JSX.Element {
  const [tSec, setTSec] = useState('')
  const [durSec, setDurSec] = useState('20')
  const [clips, setClips] = useState<AbClipResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<'a' | 'b'>('a')
  const [playing, setPlaying] = useState(false)
  const audioARef = useRef<HTMLAudioElement>(null)
  const audioBRef = useRef<HTMLAudioElement>(null)

  const applyMute = (next: 'a' | 'b') => {
    if (audioARef.current) audioARef.current.muted = next !== 'a'
    if (audioBRef.current) audioBRef.current.muted = next !== 'b'
  }

  const handleLoad = async () => {
    setLoading(true)
    setError(null)
    setPlaying(false)
    setClips(null)
    try {
      const trimmed = tSec.trim()
      const resp = await fetch(`${BASE}/api/ab_clip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date, lb_a: lbA, lb_b: lbB,
          ...(trimmed === '' ? {} : { t_sec: Number(trimmed) }),
          dur_sec: Number(durSec) || 20,
        }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setError(
          body?.error === 'not_eligible' ? 'These two sources are not sample-alignable.'
            : body?.error === 't_out_of_range' ? 'That position is past the end of one of the sources.'
            : body?.error === 'folder_missing' ? "Source folder not found — the disk may not be mounted."
            : body?.error === 'locked' ? 'TapeMatch is writing right now — try again in a moment.'
            : "Couldn't build the clips."
        )
        return
      }
      setClips(body)
      if (typeof body?.t_sec === 'number') setTSec(String(Math.round(body.t_sec * 10) / 10))
      setActive('a')
    } catch {
      setError("Couldn't build the clips.")
    } finally {
      setLoading(false)
    }
  }

  const handlePlayPause = () => {
    const a = audioARef.current
    const b = audioBRef.current
    if (!a || !b) return
    if (playing) {
      a.pause(); b.pause(); setPlaying(false)
      return
    }
    a.currentTime = 0
    b.currentTime = 0
    applyMute(active)
    Promise.all([a.play(), b.play()]).catch(() => setPlaying(false))
    setPlaying(true)
  }

  const setSource = (next: 'a' | 'b') => {
    setActive(next)
    applyMute(next)
  }

  return (
    <div style={{
      marginTop: 12, padding: '12px 13px', borderRadius: 8, minHeight: 96,
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', gap: 8,
      justifyContent: 'flex-start', opacity: eligible ? 1 : 0.72,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          font: '700 11px var(--lbb-font)', letterSpacing: '0.04em',
          textTransform: 'uppercase', color: 'var(--lbb-fg3)',
        }}>A/B listening</span>
        {!eligible && <Pill tone="mute" soft>not eligible</Pill>}
      </div>
      {!eligible ? (
        // A9: one line saying *why*, inside the reserved box — "not eligible"
        // alone sends the curator hunting for a control that isn't broken.
        <div style={{
          fontSize: 11, color: 'var(--lbb-fg3)', lineHeight: 1.45, textWrap: 'pretty',
        }}>
          Not sample-alignable — the speed offset between these two makes a synced
          clip pair impossible.
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 9, flexWrap: 'wrap' }}>
            <label style={AB_FIELD_STYLE}>
              Position (s)
              <input
                type="number" min={0} step={1} value={tSec} placeholder="auto"
                onChange={e => setTSec(e.target.value)} style={AB_NUMBER_INPUT_STYLE}
              />
            </label>
            <label style={AB_FIELD_STYLE}>
              Duration (s)
              <input
                type="number" min={5} max={60} step={1} value={durSec}
                onChange={e => setDurSec(e.target.value)} style={AB_NUMBER_INPUT_STYLE}
              />
            </label>
            <Button variant="secondary" size="sm" disabled={loading} onClick={handleLoad}>
              {loading ? 'Loading…' : 'Load'}
            </Button>
          </div>
          <div style={{ fontSize: 10, color: 'var(--lbb-fg3)' }}>
            Leave position blank to auto-pick a loud aligned moment.
          </div>
          {error && (
            <div style={{ fontSize: 11, color: 'var(--lbb-bad-fg)', lineHeight: 1.45 }}>
              {error}
            </div>
          )}
          {clips && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <Button variant="primary" size="sm" onClick={handlePlayPause}>
                {playing ? 'Pause' : '▶ Play'}
              </Button>
              <Chip size="sm" active={active === 'a'} onClick={() => setSource('a')}>
                {`A · LB-${shortId(lbA)}`}
              </Chip>
              <Chip size="sm" active={active === 'b'} onClick={() => setSource('b')}>
                {`B · LB-${shortId(lbB)}`}
              </Chip>
              <audio
                ref={audioARef} src={`${BASE}${clips.clip_a}`} preload="auto"
                onEnded={() => setPlaying(false)} style={{ display: 'none' }}
              />
              <audio
                ref={audioBRef} src={`${BASE}${clips.clip_b}`} preload="auto"
                onEnded={() => setPlaying(false)} style={{ display: 'none' }}
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── §8f Judgment control ────────────────────────────────────────────────────
// Phase 6 wires the write path. WORK_PACKAGE D4 keeps the explicit
// Cancel/Save model rather than §10.7's optimistic one — the draft is only
// the curator's once they commit it, and the 409 `locked` case (a tapematch
// run holding observations.db) is a real state an optimistic button would
// have to lie about. §10.7's save-status line is built as specified.

const JUDGMENT_OPTIONS: { key: string; label: string; tone: 'ok' | 'info' | 'warn' | 'bad' }[] = [
  { key: 'confirmed_same', label: 'Same source', tone: 'ok' },
  { key: 'confirmed_different', label: 'Different', tone: 'info' },
  { key: 'uncertain', label: 'Uncertain', tone: 'warn' },
  { key: 'lb_wrong', label: 'LB wrong', tone: 'bad' },
]

type SaveState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved'; at: string; label: string }
  | { kind: 'failed'; message: string }

function JudgmentControl({
  pair, date, onSaved,
}: {
  pair: PairRow | null
  date: string | null
  onSaved: () => void
}): React.JSX.Element {
  const [judgment, setJudgment] = useState<string | null>(pair?.human_judgment ?? null)
  const [notes, setNotes] = useState(pair?.human_notes ?? '')
  const [save, setSave] = useState<SaveState>({ kind: 'idle' })
  const dirty = judgment !== (pair?.human_judgment ?? null)
    || notes !== (pair?.human_notes ?? '')

  // §10.7 — `Saved` fades back to the idle explainer after a few seconds;
  // failures persist until retried.
  useEffect(() => {
    if (save.kind !== 'saved') return
    const t = window.setTimeout(() => setSave({ kind: 'idle' }), 4000)
    return () => window.clearTimeout(t)
  }, [save])

  async function submit(): Promise<void> {
    if (!pair || !date) return
    setSave({ kind: 'saving' })
    try {
      const res = await fetch(`${BASE}/api/tapematch/pairs/judgment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date, lb_a: pair.lb_a, lb_b: pair.lb_b,
          judgment,
          notes: notes.trim() === '' ? null : notes,
        }),
      })
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        setSave({
          kind: 'failed',
          message: body?.error === 'locked'
            ? "TapeMatch is writing right now — kept locally."
            : body?.error === 'pair_not_found'
              ? "That pair isn't in the current run — kept locally."
              : "Couldn't save — kept locally.",
        })
        return
      }
      const chosen = JUDGMENT_OPTIONS.find(o => o.key === judgment)
      setSave({
        kind: 'saved',
        at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        label: chosen?.label ?? 'cleared',
      })
      onSaved()
    } catch {
      setSave({ kind: 'failed', message: "Couldn't save — kept locally." })
    }
  }

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {JUDGMENT_OPTIONS.map(o => {
          const on = judgment === o.key
          return (
            <button
              key={o.key}
              type="button"
              aria-pressed={on}
              onClick={() => setJudgment(on ? null : o.key)}
              style={{
                padding: '8px 6px', borderRadius: 6, cursor: 'pointer',
                font: '600 11.5px var(--lbb-font)',
                background: on ? `var(--lbb-${o.tone}-bg)` : 'var(--lbb-surface2)',
                border: `1px solid ${on ? `var(--lbb-${o.tone}-bar)` : 'var(--lbb-border2)'}`,
                color: on ? `var(--lbb-${o.tone}-fg)` : 'var(--lbb-fg2)',
              }}
            >{o.label}</button>
          )
        })}
      </div>
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="notes…"
        rows={3}
        style={{
          marginTop: 7, width: '100%', minHeight: 60, resize: 'vertical',
          padding: '7px 9px', borderRadius: 6, background: 'var(--lbb-surface)',
          border: '1px solid var(--lbb-border2)', color: 'var(--lbb-fg)',
          font: '400 12px var(--lbb-font)', outline: 'none',
        }}
      />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
        <Button
          variant="ghost" size="sm" disabled={!dirty}
          onClick={() => {
            setJudgment(pair?.human_judgment ?? null)
            setNotes(pair?.human_notes ?? '')
          }}
        >Cancel</Button>
        <Button
          variant="primary" size="sm"
          disabled={!dirty || save.kind === 'saving' || !pair || !date}
          onClick={submit}
        >Save</Button>
      </div>
      {/* §10.7 — the static explainer states the mechanism, the status line
          below it reports the attempt. */}
      <div style={{ fontSize: 10, color: 'var(--lbb-fg3)', marginTop: 8, lineHeight: 1.4 }}>
        Writes <span style={{ fontFamily: 'var(--lbb-mono)' }}>human_judgment</span> +{' '}
        <span style={{ fontFamily: 'var(--lbb-mono)' }}>human_notes</span> to{' '}
        <span style={{ fontFamily: 'var(--lbb-mono)' }}>observations.db · pairs</span>.
      </div>
      {save.kind !== 'idle' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 10,
          color: save.kind === 'failed' ? 'var(--lbb-bad-fg)'
            : save.kind === 'saved' ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)',
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flex: '0 0 auto',
            background: save.kind === 'failed' ? 'var(--lbb-bad-bar)'
              : save.kind === 'saved' ? 'var(--lbb-ok-bar)' : 'var(--lbb-fg3)',
            opacity: save.kind === 'saving' ? 0.5 : 1,
          }} />
          {save.kind === 'saving' && 'Saving…'}
          {save.kind === 'saved' && `Saved ${save.at} · ${save.label}`}
          {save.kind === 'failed' && (
            <>
              {save.message}
              <button
                type="button"
                onClick={submit}
                style={{
                  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                  font: '600 10px var(--lbb-font)', color: 'var(--lbb-bad-fg)',
                  textDecoration: 'underline',
                }}
              >Retry</button>
            </>
          )}
        </div>
      )}
    </>
  )
}

/**
 * A8 — the LB page's own words clamp to three lines with a Show more control,
 * appearing only past ~240 characters. Scrape debris (swept-up navigation,
 * track listings that ran into a file manifest) deliberately stays visible:
 * it is the only place a curator will ever notice the scrape needs fixing.
 * The one thing that is cleaned is HTML entities — nobody wrote `&amp;`.
 */
function ClaimText({ text }: { text: string }): React.JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const decoded = decodeEntities(text)
  const needsToggle = decoded.length > 240
  return (
    <div style={{
      fontSize: 11.5, color: 'var(--lbb-fg2)', lineHeight: 1.5, padding: '8px 11px',
      borderLeft: '2px solid var(--lbb-border2)', background: 'var(--lbb-surface2)',
      borderRadius: '0 6px 6px 0', textWrap: 'pretty',
    }}>
      <div style={{
        display: needsToggle && !expanded ? '-webkit-box' : 'block',
        WebkitBoxOrient: 'vertical' as React.CSSProperties['WebkitBoxOrient'],
        WebkitLineClamp: needsToggle && !expanded ? 3 : undefined,
        overflow: needsToggle && !expanded ? 'hidden' : 'visible',
      }}>{decoded}</div>
      {needsToggle && (
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          style={{
            marginTop: 4, background: 'transparent', border: 'none', padding: 0,
            cursor: 'pointer', color: 'var(--lbb-accent-mid)', font: '600 11px inherit',
          }}
        >{expanded ? 'Show less' : 'Show more'}</button>
      )}
    </div>
  )
}

function DossierSubhead({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
      color: 'var(--lbb-fg3)', margin: '16px 0 7px',
    }}>{children}</div>
  )
}

function Dossier({
  selected, pair, date, colorOf, onClose, drawer, onJudgmentSaved, onOpenLb,
}: {
  selected: SelectedPair
  pair: PairRow | null
  date: string
  colorOf: (lb: number) => string
  onClose: () => void
  drawer: boolean
  onJudgmentSaved: () => void
  onOpenLb: (lb: number) => void
}): React.JSX.Element {
  const { lbA, lbB } = selected
  const sim = pair?.similarity_pct ?? null
  const conflict = !!pair && pair.lb_says_same === true && pair.same_family === false
  const secondary = isSecondaryLink(pair)
  const verdict: { text: string; tone: 'ok' | 'warn' | 'mute' | 'info' } =
    pair?.same_family
      ? (secondary
        ? { text: 'same family · secondary link', tone: 'warn' }
        : { text: 'same family', tone: 'ok' })
      : sim == null
        ? { text: 'not comparable', tone: 'mute' }
        : { text: 'different family', tone: 'info' }
  const claim = pair?.lb_relation_text ?? null
  const hasClaim = !!claim && claim.trim() !== '' && claim.trim() !== '—'

  // Both LB headings deep-link into the Library detail panel — carried over
  // from the retired ScreenTapeMatch's LbLinkButton (TODO-215 sub-feature 3),
  // which ScreenLibrary consumes one-shot from `?lb=`. It reads as the plain
  // mono label it replaces; only the hover colour marks it as a target.
  const lbLabel = (lb: number) => (
    <button
      type="button"
      onClick={() => onOpenLb(lb)}
      title={`Open LB-${shortId(lb)} in the Library`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: 0,
        background: 'none', border: 'none', cursor: 'pointer',
        font: '700 13px var(--lbb-mono)', color: 'var(--lbb-fg)',
      }}
      onMouseEnter={e => { e.currentTarget.style.color = 'var(--lbb-accent-mid)' }}
      onMouseLeave={e => { e.currentTarget.style.color = 'var(--lbb-fg)' }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: 2, background: colorOf(lb), flex: '0 0 8px',
      }} />
      LB-{shortId(lb)}
    </button>
  )

  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {lbLabel(lbA)}
          <span style={{ color: 'var(--lbb-fg3)' }}>×</span>
          {lbLabel(lbB)}
        </div>
        {drawer && (
          <button
            type="button" onClick={onClose} aria-label="Close dossier"
            style={{
              background: 'none', border: 'none', color: 'var(--lbb-fg3)',
              cursor: 'pointer', fontSize: 14, padding: 4,
            }}
          >&#10005;</button>
        )}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        marginTop: 12, padding: '10px 12px', borderRadius: 7,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      }}>
        <div>
          <span style={{ font: '800 24px var(--lbb-mono)', lineHeight: 1, color: 'var(--lbb-fg)' }}>
            {sim == null ? 'n/c' : `${sim}%`}
          </span>
          <span style={{
            display: 'block', fontSize: 9.5, color: 'var(--lbb-fg3)', marginTop: 3, maxWidth: 170,
          }}>
            {sim == null
              ? 'similarity — speed ratio unconfident, correlation not comparable'
              : 'similarity · banded blend of corr + embedding'}
          </span>
        </div>
        <Pill tone={verdict.tone}>{verdict.text}</Pill>
      </div>

      {conflict && (
        <div style={{
          marginTop: 10, padding: '9px 11px', borderRadius: 7,
          background: 'var(--lbb-bad-bg)',
          border: '1px solid color-mix(in oklab, var(--lbb-bad-bar) 50%, transparent)',
          fontSize: 11.5, color: 'var(--lbb-bad-fg)', lineHeight: 1.45,
        }}>
          <strong>Conflict.</strong> LB page says same source; TapeMatch found no
          acoustic link. This pair is why this date is in the queue.
        </div>
      )}

      <AbPlayer lbA={lbA} lbB={lbB} eligible={pair?.ab_eligible === true} date={date} />

      <DossierSubhead>Primary evidence</DossierSubhead>
      <EvidenceBar
        label="Residual correlation" value={pair?.corr ?? null}
        thresh={CORR_THRESHOLD} note={corrNote(pair)}
      />
      <DossierSubhead>Secondary evidence</DossierSubhead>
      <EvidenceBar
        label="Windowed coverage" value={pair?.windowed_frac ?? null} thresh={WIN_THRESHOLD}
        note="fraction of dense 60 s windows correlating — drives secondary clustering"
      />
      <EvidenceBar
        label="Quiet-segment hiss corr" value={pair?.hiss_median ?? null}
        note="tape hiss survives EQ/NR applied to the music"
      />
      <EvidenceBar
        label="Fingerprint dice" value={pair?.fp_score ?? null} band={FP_BAND} demote
        note={'confirmatory only — never groups. Shaded band = 0.15–0.50 coincidence '
          + 'range for two tapers at the same show.'}
      />

      <DossierSubhead>LB page says</DossierSubhead>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, alignItems: 'flex-start' }}>
        {hasClaim ? (
          <>
            <Pill tone={conflict ? 'bad' : pair?.lb_says_same ? 'ok' : 'mute'} soft>
              {conflict ? 'disagrees' : pair?.lb_says_same ? 'agrees · same source' : 'no claim'}
            </Pill>
            <ClaimText text={claim as string} />
          </>
        ) : (
          <div style={{
            fontSize: 11.5, color: 'var(--lbb-fg3)', lineHeight: 1.5, padding: '8px 11px',
            borderLeft: '2px solid var(--lbb-border)', background: 'var(--lbb-surface2)',
            borderRadius: '0 6px 6px 0', textWrap: 'pretty',
          }}>
            No relation claim between these LB numbers on either page.
          </div>
        )}
      </div>

      <DossierSubhead>Your judgment</DossierSubhead>
      {/* keyed by the pair so switching cells remounts with that pair's stored
          judgment/notes instead of carrying over the previous draft */}
      <JudgmentControl
        key={pairKey(lbA, lbB)} pair={pair} date={date} onSaved={onJudgmentSaved}
      />
    </>
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

// ── §6 Speed & lag strip ────────────────────────────────────────────────────
// A one-dimensional plot of every recording's playback-speed offset against
// the date's reference, on a signed square-root axis (ppm spans four orders of
// magnitude, so a linear axis piles every dot on top of the origin).

interface SourceRow {
  lb_number: number
  speed_kind: string | null
  speed_ppm: number | null
  family_id: number | string | null
  folder_name: string | null
  lag_ref_lb: number | null
}

interface SourcesResponse {
  date: string
  run_id: string | null
  sources: SourceRow[]
}

// DESIGN_ANSWERS A4: ▤ survives the staircase/splice merge (observations.db
// stores them as the single value `staircase/splice`), and `insufficient`
// folds into speed-unknown's `?` rather than earning a sixth symbol for the
// two rows in the corpus that have it.
const SPEED_GLYPH: Record<string, string> = {
  'reference': '◆',
  'aligned': '●',
  'constant-speed-offset': '●',
  'staircase/splice': '▤',
  'staircase': '▤',
  'splice': '▤',
  'speed-unknown': '?',
  'insufficient': '?',
}

function speedGlyph(kind: string | null): string {
  return (kind && SPEED_GLYPH[kind]) || '?'
}

function speedKindLabel(kind: string | null): string {
  if (kind === 'insufficient') return 'speed-unknown (insufficient)' // A4
  return kind ?? 'speed unmeasured'
}

/** Signed square-root: keeps sign, compresses magnitude (README §6 `sym`). */
function symPpm(ppm: number): number {
  return Math.sign(ppm) * Math.sqrt(Math.abs(ppm))
}

/** Tick/label form: 0 is the reference, others get a true minus + separators. */
function formatPpm(ppm: number): string {
  const n = Math.round(ppm)
  if (n === 0) return '0'
  const abs = Math.abs(n).toLocaleString('en-US')
  return n < 0 ? `−${abs}` : `+${abs}`
}

// A `speed-unknown` row's ratio confidence fell below the 6.0 minimum, so its
// stored ppm is an estimate the pipeline itself doesn't trust — but it is what
// exists on disk, and the design plots every recording on the axis. Say so in
// the tooltip rather than silently positioning a dot by an untrusted number.
function speedTooltip(src: SourceRow): string {
  const parts = [`LB-${shortId(src.lb_number)}`, speedKindLabel(src.speed_kind)]
  if (src.speed_ppm == null) {
    parts.push('no ppm recorded')
  } else {
    const untrusted = src.speed_kind === 'speed-unknown' || src.speed_kind === 'insufficient'
    parts.push(`${formatPpm(src.speed_ppm)} ppm${untrusted ? ' (unconfident estimate)' : ''}`)
  }
  return parts.join(' · ')
}

const LABEL_WIDTH_PCT = 4.8 // README §6 lane packing — a short id's footprint
const LANE_HEIGHT = 34
const TICK_GUTTER = 22

function SpeedLegend(): React.JSX.Element {
  const entry: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 5 }
  return (
    <div style={{
      display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8,
      fontSize: 10, color: 'var(--lbb-fg3)', maxWidth: 760,
    }}>
      <span style={entry}>◆ reference</span>
      <span style={entry}>● aligned / constant offset</span>
      <span style={entry}>▤ lag steps — re-tracking or a splice</span>
      <span style={{ ...entry, color: 'var(--lbb-warn-fg)' }}>
        ? speed-unknown → fingerprint path only
      </span>
      <span style={{
        marginLeft: 'auto', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)',
      }}>ppm vs reference · √ scale</span>
    </div>
  )
}

function SpeedStrip({
  sources, colorOf, selected, pending, onDotClick,
}: {
  sources: SourceRow[]
  colorOf: (lb: number) => string
  selected: SelectedPair | null
  pending: number | null
  onDotClick: (lb: number) => void
}): React.JSX.Element {
  const { x, ticks, lanes, maxLane } = useMemo(() => {
    const values = sources.map(s => symPpm(s.speed_ppm ?? 0))
    const lo = Math.min(...values, 0)
    const hi = Math.max(...values, 0)
    const span = hi - lo
    // The plot inhabits 4%–96% of the width, leaving room for the outermost
    // labels. A degenerate domain (every recording at 0 ppm — common: a date
    // whose sources are all reference/aligned) centres instead of dividing
    // by zero.
    const xOf = (ppm: number | null): number =>
      span === 0 ? 50 : 4 + ((symPpm(ppm ?? 0) - lo) / span) * 92

    const rawTicks = [Math.min(...sources.map(s => s.speed_ppm ?? 0), 0), 0,
      Math.max(...sources.map(s => s.speed_ppm ?? 0), 0)]
    const seen = new Set<number>()
    const tickList = rawTicks
      .map(t => Math.round(t))
      .filter(t => (seen.has(t) ? false : (seen.add(t), true)))

    // Greedy lane packing, in list order: lowest lane with no already-placed
    // dot within a label width. The strip grows taller as needed rather than
    // clipping (README §6).
    const placed: { x: number; lane: number }[] = []
    const laneOf = sources.map(s => {
      const px = xOf(s.speed_ppm)
      let lane = 0
      while (placed.some(p => p.lane === lane && Math.abs(p.x - px) < LABEL_WIDTH_PCT)) lane++
      placed.push({ x: px, lane })
      return lane
    })
    return {
      x: xOf, ticks: tickList, lanes: laneOf,
      maxLane: laneOf.length ? Math.max(...laneOf) : 0,
    }
  }, [sources])

  return (
    <div style={{
      border: '1px solid var(--lbb-border)', borderRadius: 8,
      background: 'var(--lbb-surface)', padding: '12px 14px 10px', maxWidth: 760,
    }}>
      <div style={{ position: 'relative', height: (maxLane + 1) * LANE_HEIGHT + TICK_GUTTER }}>
        {ticks.map(t => (
          <div
            key={`tick-${t}`}
            style={{
              position: 'absolute', top: 0, bottom: TICK_GUTTER - 6, left: `${x(t)}%`,
            }}
          >
            <div style={{
              position: 'absolute', top: 0, bottom: 0, width: 1,
              background: 'var(--lbb-border2)', left: 0,
            }} />
            <div style={{
              position: 'absolute', bottom: -15, left: 0, transform: 'translateX(-50%)',
              font: '500 9.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
              whiteSpace: 'nowrap',
            }}>{t === 0 ? 'ref' : formatPpm(t)}</div>
          </div>
        ))}
        {sources.map((s, i) => {
          const inPair = !!selected
            && (selected.lbA === s.lb_number || selected.lbB === s.lb_number)
          const isPending = pending === s.lb_number
          return (
            <button
              key={s.lb_number}
              type="button"
              title={speedTooltip(s)}
              aria-pressed={inPair || isPending}
              aria-label={speedTooltip(s)}
              onClick={() => onDotClick(s.lb_number)}
              style={{
                position: 'absolute', left: `${x(s.speed_ppm)}%`, top: lanes[i] * LANE_HEIGHT + 4,
                transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column',
                alignItems: 'center', gap: 1, background: 'none', border: 'none',
                padding: 0, cursor: 'pointer', zIndex: 1,
              }}
            >
              <span style={{
                width: 18, height: 18, borderRadius: '50%', background: colorOf(s.lb_number),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                // The family colours are theme-independent mid-tones (tokens.ts),
                // so the glyph's dark ink is too — it is not --lbb-fg.
                font: '700 9px var(--lbb-font)', color: '#0b1020',
                outline: inPair ? '2px solid var(--lbb-fg)'
                  : isPending ? '2px dashed var(--lbb-accent-mid)' : 'none',
                outlineOffset: 1,
              }}>{speedGlyph(s.speed_kind)}</span>
              <span style={{
                font: '600 9px var(--lbb-mono)',
                color: inPair || isPending ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
              }}>{shortId(s.lb_number)}</span>
            </button>
          )
        })}
      </div>
      <SpeedLegend />
    </div>
  )
}

// ── §7 Analysis verdict cards ───────────────────────────────────────────────
// Parsing lives in `lib/analysisMd.ts` (B1/B1.1/B1.2/B2 rules); this is the
// rendering only. Ported from the design's `tm-parts.jsx` VerdictCards +
// `tm.css` .tmNote* block, with the raw hexes mapped onto `--lbb-*` (D2).

function CardBody({ blocks }: { blocks: CardBlock[] }): React.JSX.Element | null {
  if (!blocks.length) return null
  return (
    <div style={{
      fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', lineHeight: 1.5,
      display: 'flex', flexDirection: 'column', gap: 5, textWrap: 'pretty',
    }}>
      {blocks.map((b, i) => b.kind === 'ul' ? (
        <ul key={i} style={{ margin: 0, paddingLeft: 16, display: 'grid', gap: 3 }}>
          {b.items.map((it, j) => <li key={j}>{it}</li>)}
        </ul>
      ) : b.kind === 'kv' ? (
        // B1.1 — `label: value` becomes a two-column row. Every card's keys are
        // identical, so in an eleven-card stack the eye lands on what differs.
        <div key={i} style={{
          display: 'grid', gridTemplateColumns: '104px minmax(0,1fr)', gap: 9,
          alignItems: 'baseline',
        }}>
          <span style={{
            fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em',
            textTransform: 'uppercase', color: 'var(--lbb-fg3)', paddingTop: 1,
          }}>{b.k}</span>
          {b.quote ? (
            <span style={{
              display: 'block', minWidth: 0, color: 'var(--lbb-fg2)',
              borderLeft: '2px solid var(--lbb-border2)', background: 'var(--lbb-surface2)',
              borderRadius: '0 5px 5px 0', padding: '4px 9px', textWrap: 'pretty',
            }}>{b.v}</span>
          ) : (
            <span style={{ minWidth: 0, color: 'var(--lbb-fg2)' }}>{b.v}</span>
          )}
        </div>
      ) : (
        <p key={i} style={{ margin: 0 }}>{b.text}</p>
      ))}
    </div>
  )
}

function VerdictCard({
  card, famColor, onOpenRef,
}: {
  card: ParsedCard
  famColor: string | null
  onOpenRef: ((refs: number[]) => void) | null
}): React.JSX.Element {
  // B1.2 — a heading with no subject is a statement about the run, not a
  // finding about a recording, so it takes A6's dashed treatment: no chip, no
  // tone bar, and only its key is tinted. It never competes with a card.
  if (card.kind === 'statement') {
    return (
      <div style={{
        padding: '9px 12px', borderRadius: 7, border: '1px dashed var(--lbb-border2)',
        background: 'var(--lbb-surface)',
      }}>
        <div style={{
          fontSize: 9.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase',
          color: `var(--lbb-${card.tone}-fg)`, marginBottom: 4,
        }}>{card.title}</div>
        {card.lead && (
          <div style={{
            fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4,
            textWrap: 'pretty',
          }}>{card.lead}</div>
        )}
        <CardBody blocks={card.blocks} />
      </div>
    )
  }
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 7,
      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
    }}>
      <span style={{
        width: 3, flex: '0 0 3px', borderRadius: 2, background: `var(--lbb-${card.tone}-bar)`,
      }} />
      <div style={{ minWidth: 0, flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'baseline',
          gap: 6, flexWrap: 'wrap',
        }}>
          {card.kind === 'family' ? (
            // The swatch is tinted from the document's own table (LB → Family
            // column), because `fam_id` in the app DB is member-derived
            // (`1996-07-13#5812-6362-6368`) and carries no run family number.
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              font: '700 11px var(--lbb-mono)', color: 'var(--lbb-fg)',
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: 2, flex: '0 0 8px',
                background: famColor ?? 'var(--lbb-mute-bar)',
              }} />
              {card.ref}
            </span>
          ) : onOpenRef ? (
            // A7 — display follows the document (slash, its own ordering);
            // navigation normalises through the lb_a < lb_b pair key.
            <button
              type="button"
              onClick={() => onOpenRef(card.refs)}
              title={`Open ${card.ref}`}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                font: '700 11px var(--lbb-mono)', color: 'var(--lbb-fg)',
                borderBottom: '1px dashed var(--lbb-border2)',
              }}
            >{card.ref}</button>
          ) : (
            <span style={{ font: '700 11px var(--lbb-mono)', color: 'var(--lbb-fg)' }}>
              {card.ref}
            </span>
          )}
          {/* B1.1 — no headline in the document means no headline here, and no
              dangling em-dash. Nothing is promoted into the empty slot. */}
          {card.head && (
            <>
              <span style={{ color: 'var(--lbb-fg3)' }}>—</span>
              <span style={{ color: `var(--lbb-${card.tone}-fg)` }}>{card.head}</span>
            </>
          )}
        </div>
        <CardBody blocks={card.blocks} />
      </div>
    </div>
  )
}

function VerdictCards({
  doc, colorOf, pairsByKey, onOpenPair,
}: {
  doc: AnalysisDoc
  colorOf: (lb: number) => string
  pairsByKey: Map<string, PairRow>
  onOpenPair: (lbA: number, lbB: number) => void
}): React.JSX.Element {
  // A6 — a clean date keeps the section and states the absence in one line.
  // A card means "here is a finding to review"; dressing the absence of
  // findings as a card devalues the card after fifty clean dates.
  const clean = doc.cards.length === 0 ? doc.epilogue.join(' ') : ''
  const famColor = (fam: number | null): string | null => {
    if (fam == null) return null
    for (const [lb, n] of doc.famByLb) if (n === fam) return colorOf(lb)
    return null
  }
  // A ref is a click target only when it resolves to a pair this date actually
  // has — a single-recording card (`LB-00776`) has no dossier to open, and a
  // three-way heading has no one pair to mean.
  const openerFor = (refs: number[]): ((refs: number[]) => void) | null => {
    if (refs.length !== 2) return null
    if (!pairsByKey.has(pairKey(refs[0], refs[1]))) return null
    return r => onOpenPair(r[0], r[1])
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7, maxWidth: 760 }}>
      {clean && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 9, fontSize: 12,
          color: 'var(--lbb-fg2)', lineHeight: 1.5, padding: '2px 0', textWrap: 'pretty',
        }}>
          <span style={{
            width: 7, height: 7, flex: '0 0 7px', borderRadius: '50%',
            background: 'var(--lbb-ok-bar)', marginTop: 6,
          }} />
          <span>{clean}</span>
        </div>
      )}
      {doc.cards.map((card, i) => (
        <VerdictCard
          key={i}
          card={card}
          famColor={famColor(card.fam)}
          onOpenRef={openerFor(card.refs)}
        />
      ))}
      {doc.notOnDisk.length > 0 && (
        <div style={{
          fontSize: 11, color: 'var(--lbb-fg3)', lineHeight: 1.5, paddingTop: 2,
        }}>
          Not on disk:{' '}
          <span style={{ fontFamily: 'var(--lbb-mono)' }}>{doc.notOnDisk.join(', ')}</span>
          {' '}— known to the DB, no audio found by the crawl.
        </div>
      )}
      {doc.algoNote && (
        <div style={{
          marginTop: 4, padding: '8px 11px', borderRadius: 6,
          border: '1px dashed var(--lbb-border2)', background: 'var(--lbb-surface)',
          fontSize: 11, color: 'var(--lbb-fg3)', lineHeight: 1.5,
        }}>
          <span style={{
            display: 'block', fontSize: 9.5, fontWeight: 700, letterSpacing: '0.07em',
            textTransform: 'uppercase', marginBottom: 3,
          }}>Algorithm note</span>
          {doc.algoNote}
        </div>
      )}
    </div>
  )
}

/**
 * The raw `analysis.md` behind the §7 cards, collapsed by default.
 *
 * Carried over from the retired ScreenTapeMatch's `AnalysisSection`. §7's cards
 * are a reading of the document, and this audience works in the filesystem too
 * — when a card looks wrong, the next question is always "what does the file
 * actually say". Not §11: that overlay renders `report.md`, a different file.
 */
function RawAnalysis({ md }: { md: string | null }): React.JSX.Element | null {
  const [open, setOpen] = useState(false)
  if (!md) return null
  return (
    <div style={{ marginTop: 12 }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 7, padding: '7px 0',
          border: 'none', borderTop: '1px solid var(--lbb-border)', width: '100%',
          background: 'transparent', color: 'var(--lbb-fg3)', cursor: 'pointer',
          font: '600 11px var(--lbb-font)', textAlign: 'left',
        }}
      >
        <Icon name={open ? 'chevDown' : 'chevRight'} size={11} />
        <span style={{ fontFamily: 'var(--lbb-mono)' }}>analysis.md</span>
        <span style={{ fontWeight: 500 }}>— the document these cards were read from</span>
      </button>
      {open && (
        <pre style={{
          margin: 0, padding: 12, borderRadius: 6,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          color: 'var(--lbb-fg2)', font: '400 11.5px/1.5 var(--lbb-mono)',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 420, overflowY: 'auto',
        }}>{md}</pre>
      )}
    </div>
  )
}

export function ScreenTapeMatchCuration(): React.JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const selectedDate = searchParams.get('date')
  const cursorIndexRef = useRef(0)

  const width = useViewportWidth()
  const narrowRail = width <= 1380
  const narrowDossier = width <= 1520

  const {
    data: datesData, isPending: datesPending, isError: datesError,
  } = useQuery({
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
  const analysisMd: string | null = (analysisData as AnalysisResponse | undefined)?.analysis_md ?? null
  // §7 — parsed client-side rather than server-side: the route already serves
  // the whole document (it has to, for §11's raw view), and the parse rules are
  // rendering rules, so they belong next to the thing that renders them.
  const analysisDoc = useMemo(() => analysisMd ? parseAnalysisMd(analysisMd) : null, [analysisMd])

  const { data: familiesData, isPending: familiesLoading } = useQuery({
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
    data: pairsData, isPending: pairsLoading, isError: pairsError,
    error: pairsErrorObj, failureCount: pairsFailureCount, refetch: refetchPairsQuery,
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

  // §6 speed strip data — source-shaped, so its own route rather than a field
  // on /api/tapematch/pairs. Kept separate from `recordings` (which comes from
  // the synced family assignment) because a date can have sources with no
  // synced pairs at all.
  const {
    data: sourcesData, isPending: sourcesLoading, isError: sourcesError,
  } = useQuery({
    queryKey: ['tapematch-curation-sources', selectedDate],
    queryFn: () => fetch(`${BASE}/api/tapematch/sources?date=${encodeURIComponent(selectedDate as string)}`)
      .then(r => r.json()),
    enabled: !!selectedDate,
    staleTime: 15_000,
  })
  const speedSources = (sourcesData as SourcesResponse | undefined)?.sources ?? []

  // Lifted here (not local to Matrix) because Phase 3's dossier will read it
  // too — the dossier rendering itself stays untouched (empty state only)
  // until that phase lands.
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)
  useEffect(() => { setSelectedPair(null) }, [selectedDate])

  // §6 dot interaction. The design calls its prototype's logic "blunt" and
  // recommends the two-click form instead (click a dot to select a recording,
  // click a second to form the pair and open its dossier) — built as
  // recommended, minus the "highlight the whole matrix row/column" half, which
  // would need a second highlight state threaded through Matrix on top of its
  // existing selection dimming. WORK_PACKAGE D7.
  const [pendingLb, setPendingLb] = useState<number | null>(null)
  useEffect(() => { setPendingLb(null) }, [selectedDate])
  const onSpeedDotClick = (lb: number) => {
    if (pendingLb === lb) { setPendingLb(null); return }
    if (pendingLb == null) { setPendingLb(lb); setSelectedPair(null); return }
    setSelectedPair({ lbA: pendingLb, lbB: lb })
    setPendingLb(null)
  }
  // A pair chosen anywhere else (matrix cell, drawer close) ends any half-made
  // selection in the strip, so the dashed outline never outlives its meaning.
  useEffect(() => { if (selectedPair) setPendingLb(null) }, [selectedPair])

  const selectedPairRow = selectedPair
    ? pairsByKey.get(pairKey(selectedPair.lbA, selectedPair.lbB)) ?? null
    : null

  const colorByLb = useMemo(() => {
    const m = new Map<number, number>()
    for (const r of recordings) m.set(r.lb, r.colorIndex)
    return m
  }, [recordings])
  const colorOf = (lb: number) => familyColorVar(colorByLb.get(lb) ?? 0)

  // ── §11 report.md overlay (Phase 7) ───────────────────────────────────────
  // Fetched only while the sheet is open: report.md is up to ~250 lines of
  // fixed-width ASCII per run, and a curator opens it on a minority of dates.
  const [reportOpen, setReportOpen] = useState(false)
  const reportButtonRef = useRef<HTMLSpanElement>(null)
  useEffect(() => { setReportOpen(false) }, [selectedDate])

  const {
    data: reportData, isPending: reportLoading, isError: reportError,
  } = useQuery({
    queryKey: ['tapematch-report', selectedDate],
    queryFn: () => fetch(`${BASE}/api/tapematch/report?date=${encodeURIComponent(selectedDate as string)}`)
      .then(r => r.json()),
    enabled: reportOpen && !!selectedDate,
    staleTime: 60_000,
  })
  const report = reportData as ReportResponse | undefined

  // §8 production note — the drawer takes focus on open and hands it back to
  // whatever opened it (a matrix cell or a speed dot) on close.
  const drawerRef = useRef<HTMLDivElement>(null)
  const drawerOpenerRef = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (!narrowDossier || !selectedPair) return
    drawerOpenerRef.current = document.activeElement as HTMLElement | null
    drawerRef.current?.focus()
    return () => { drawerOpenerRef.current?.focus?.() }
  }, [narrowDossier, selectedPair])

  const closeReport = () => {
    setReportOpen(false)
    // §11 — focus returns to `Open report.md`. The Button primitive doesn't
    // forward refs, so the ref sits on its wrapper.
    reportButtonRef.current?.querySelector('button')?.focus()
  }

  // Esc closes the drawer. Only bound in drawer mode — docked, the dossier is
  // part of the layout and Esc belongs to the triage rail. Focus-trap and
  // focus-restore-to-cell are Phase 9 (README §8's production note).
  // Not bound while the report is open: §11 says Esc closes the report first,
  // and both handlers listen in the capture phase.
  useEffect(() => {
    if (!narrowDossier || !selectedPair || reportOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); setSelectedPair(null) }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [narrowDossier, selectedPair])

  // ── Phase 6 write path ────────────────────────────────────────────────────
  // Judged count is server truth (the pairs query), not a local queue: D4's
  // explicit Save writes before the count can move, and refetching the pairs
  // after a save is what keeps the dossier, the header count and the top-bar
  // pill from drifting apart.
  const judgedCount = useMemo(() => {
    const pairs = (pairsData as PairsResponse | undefined)?.pairs ?? []
    return pairs.filter(p => p.human_judgment != null).length
  }, [pairsData])

  const queryClient = useQueryClient()
  const refetchPairs = () => {
    queryClient.invalidateQueries({ queryKey: ['tapematch-curation-pairs', selectedDate] })
  }

  // TODO-215 sub-feature 3, carried over from ScreenTapeMatch: ScreenLibrary
  // consumes `?lb=` one-shot and opens that recording's detail panel.
  const openLb = (lb: number) => navigate(`/library?lb=${lb}`)

  const [accept, setAccept] = useState<AcceptState>({ kind: 'idle' })
  useEffect(() => { setAccept({ kind: 'idle' }) }, [selectedDate])
  useEffect(() => {
    if (accept.kind !== 'accepted') return
    const t = window.setTimeout(() => setAccept({ kind: 'idle' }), 4000)
    return () => window.clearTimeout(t)
  }, [accept])

  async function acceptFamilies(): Promise<void> {
    if (!selectedDate) return
    setAccept({ kind: 'saving' })
    try {
      const res = await fetch(`${BASE}/api/tapematch/dates/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: selectedDate }),
      })
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        setAccept({
          kind: 'failed',
          message: body?.error === 'locked'
            ? 'TapeMatch is writing right now — try again in a moment.'
            : body?.error === 'no_run'
              ? "No analysed run for this date — nothing to accept."
              : "Couldn't accept — nothing was recorded.",
        })
        return
      }
      setAccept({
        kind: 'accepted',
        at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      })
      // The rail's `curated` state comes from /api/tapematch/dates, so the
      // status pill and the "Done" filter only move once that refetches.
      queryClient.invalidateQueries({ queryKey: ['tapematch-dates'] })
    } catch {
      setAccept({ kind: 'failed', message: "Couldn't accept — nothing was recorded." })
    }
  }

  const dossierBody = selectedPair && selectedDate ? (
    <Dossier
      selected={selectedPair}
      pair={selectedPairRow}
      date={selectedDate}
      colorOf={colorOf}
      onClose={() => setSelectedPair(null)}
      drawer={narrowDossier}
      onJudgmentSaved={refetchPairs}
      onOpenLb={openLb}
    />
  ) : <DossierEmpty />

  const openDate = (date: string) => setSearchParams({ date })

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* §10.1's skeleton sweep and §8's drawer transition — keyframes can't be
          expressed as inline styles, and this screen owns both. */}
      <style>{SKELETON_CSS}</style>
      <TopBar crawl={crawl} judgedCount={judgedCount} date={selectedDate} />
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <TriageRail
          rows={allDates}
          loading={datesPending && !datesError}
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
          <DateHeader
            row={selectedRow}
            narrow={narrowRail}
            verdictText={verdictText}
            families={dateFamilies}
            judgedCount={judgedCount}
            soloDate={recordings.length <= 1}
            onAccept={acceptFamilies}
            accept={accept}
            onOpenReport={() => setReportOpen(true)}
            reportButtonRef={reportButtonRef}
            dataState={
              pairsError ? 'error'
                : (!familiesLoading && !pairsLoading && recordings.length === 0) ? 'empty' : 'ok'
            }
          />
          <div style={{
            display: 'grid',
            gridTemplateColumns: narrowDossier ? 'minmax(0,1fr)' : 'minmax(0,1fr) 350px',
            flex: 1, minHeight: 0,
          }}>
            <div style={{ padding: narrowRail ? '6px 16px 22px' : '6px 22px 26px', minHeight: 0 }}>
              <CurationSection
                // §10.5 — on a solo date the section is a Recording, not a
                // matrix, and the hint names the threshold so the state
                // doesn't read as a bug.
                title={recordings.length === 1 ? 'Recording' : 'Similarity matrix'}
                hint={recordings.length === 1
                  ? 'nothing to compare — pair views only appear from two recordings up'
                  : 'family-ordered · % is the banded corr+embedding blend · click a cell for the dossier'}
              >
                {!selectedRow ? (
                  <SectionPlaceholder label="Select a date from the triage queue." />
                ) : pairsError ? (
                  // §10.2 — the real error, not "something went wrong": this
                  // audience is technical, and the reassurance about saved
                  // judgments is required copy for a curator mid-session.
                  <CurationState
                    glyph="&#9888;"
                    tone="bad"
                    head="Couldn't load this date"
                    body={
                      "The run's artifacts didn't come back. Nothing has been changed — "
                      + 'judgments you already saved are safe in observations.db.'
                    }
                    detail={
                      `GET /api/tapematch/pairs?date=${selectedDate}\n`
                      + `error   ${(pairsErrorObj as Error | null)?.message ?? 'request failed'}\n`
                      + `run     ${selectedRow.run_id ?? '—'}\n`
                      + `attempt ${pairsFailureCount}`
                    }
                    actions={
                      <Button variant="primary" size="sm" onClick={() => { void refetchPairsQuery() }}>
                        Retry
                      </Button>
                    }
                  />
                ) : familiesLoading || (pairsLoading && recordings.length === 0) ? (
                  // §10.1 — N isn't known yet either, so this is the one
                  // loading state that can't render the real grid.
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 760 }}>
                    <Skeleton w={220} h={10} />
                    <Skeleton h={180} />
                  </div>
                ) : recordings.length === 0 ? (
                  // §10.4 — a known show with nothing circulating. Mute, not
                  // bad: nothing is wrong, and it re-enters the queue on its
                  // own when a recording appears.
                  <CurationState
                    glyph="&#8709;"
                    tone="mute"
                    head="No recordings for this date"
                    body={
                      'The show is in the library but no audience recordings have been '
                      + 'indexed, so TapeMatch has nothing to compare. It will re-enter the '
                      + 'queue automatically when a recording appears.'
                    }
                  />
                ) : recordings.length === 1 ? (
                  // §10.5 — one recording means zero pairs, so the date
                  // collapses to a solo card instead of three empty components.
                  <SoloCard
                    lb={recordings[0].lb}
                    color={colorOf(recordings[0].lb)}
                    source={speedSources.find(s => s.lb_number === recordings[0].lb) ?? null}
                  />
                ) : pairsLoading ? (
                  <MatrixSkeleton recordings={recordings} />
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
                hint="why a pair's correlation looks the way it does · click two dots to open their pair"
              >
                {!selectedRow ? (
                  <SectionPlaceholder label="Select a date from the triage queue." />
                ) : sourcesLoading ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 760 }}>
                    <Skeleton h={54} />
                    <Skeleton w={280} h={9} />
                  </div>
                ) : sourcesError ? (
                  <SectionPlaceholder label="Couldn't load this date's speed measurements." />
                ) : speedSources.length === 0 ? (
                  // No analysed run for the date (or observations.db locked
                  // mid-run — the route degrades to an empty list either way).
                  <SectionPlaceholder label={
                    'No speed measurements for this date — nothing has been analysed yet.'
                  } />
                ) : (
                  <SpeedStrip
                    sources={speedSources}
                    colorOf={colorOf}
                    selected={selectedPair}
                    pending={pendingLb}
                    onDotClick={onSpeedDotClick}
                  />
                )}
              </CurationSection>
              <CurationSection
                title="Analysis verdict"
                hint="parsed from analysis.md — the human/AI review layer"
              >
                {!selectedRow ? (
                  <SectionPlaceholder label="Select a date from the triage queue." />
                ) : !analysisDoc ? (
                  // The run exists but has no analysis.md yet (or the date has
                  // no run at all) — the route returns analysis_md null for
                  // both, and neither is an error worth alarming about.
                  <SectionPlaceholder label={
                    'No analysis.md for this date yet — the review layer runs after the '
                    + 'match pass.'
                  } />
                ) : (
                  <>
                    <VerdictCards
                      doc={analysisDoc}
                      colorOf={colorOf}
                      pairsByKey={pairsByKey}
                      onOpenPair={(lbA, lbB) => setSelectedPair({ lbA, lbB })}
                    />
                    <RawAnalysis md={analysisMd} />
                  </>
                )}
              </CurationSection>
            </div>
            {!narrowDossier && (
              <div style={{
                borderLeft: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
                padding: 16, overflowY: 'auto', minHeight: 0,
              }}>
                {dossierBody}
              </div>
            )}
          </div>
        </div>
      </div>
      {/* §8 drawer mode (≤1520px): the dossier leaves the grid and overlays
          the work column on a scrim. Only mounted when a pair is selected —
          an empty-state drawer would cover the matrix for nothing. The
          slide-in transition and focus trap are Phase 9. */}
      {narrowDossier && selectedPair && (
        <>
          <div
            onClick={() => setSelectedPair(null)}
            style={{
              position: 'fixed', inset: 0, background: 'var(--lbb-scrim, rgba(5,8,14,.5))',
              zIndex: 25,
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Pair dossier"
            className="lbbDrawer"
            ref={drawerRef}
            tabIndex={-1}
            onKeyDown={e => {
              if (e.key !== 'Tab') return
              const root = e.currentTarget
              const f = root.querySelectorAll<HTMLElement>(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
              )
              if (!f.length) return
              const first = f[0]
              const last = f[f.length - 1]
              if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
              if (e.shiftKey && (document.activeElement === first || document.activeElement === root)) {
                e.preventDefault(); last.focus()
              }
            }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(380px, 92vw)',
              zIndex: 30, background: 'var(--lbb-surface)', padding: 16,
              overflowY: 'auto', borderLeft: '1px solid var(--lbb-border2)',
              boxShadow: '-18px 0 40px rgba(0,0,0,.45)',
            }}
          >
            {dossierBody}
          </div>
        </>
      )}
      {/* §11 — reference material consulted *during* review, so it overlays the
          workspace rather than routing away from it. Portalled to the body,
          which is also what scopes §11.1's print block. */}
      {reportOpen && selectedDate && (
        <ReportSheet
          date={selectedDate}
          runId={report?.run_id ?? selectedRow?.run_id ?? null}
          runDir={report?.run_dir ?? null}
          md={report?.report_md ?? null}
          loading={reportLoading}
          error={reportError}
          judgedCount={judgedCount}
          judgmentFor={(a, b) => pairsByKey.get(pairKey(a, b))?.human_judgment ?? null}
          pairExists={(a, b) => pairsByKey.has(pairKey(a, b))}
          colorOf={colorOf}
          onClose={closeReport}
          onOpenPair={(a, b) => { setSelectedPair({ lbA: a, lbB: b }); closeReport() }}
          onSelectLb={lb => { setPendingLb(lb); setSelectedPair(null); closeReport() }}
        />
      )}
    </div>
  )
}
