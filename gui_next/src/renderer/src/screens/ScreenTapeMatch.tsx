// TapeMatch screen v1 (LISTENING §1 / TODO-170) — read-only review surface for
// the TapeMatch acoustic-matching pipeline: pick a concert date, inspect its
// pairwise similarity matrix and inferred families, and read the crawl's
// analysis.md verdict. No run controls, no pair-correction actions — those
// stay in the tools/tapematch CLI workflow; this screen is observation only.

import React, { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Pill, Chip, Input, Button } from '../components'
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
  human_judgment?: string | null
  human_notes?: string | null
  ab_eligible?: boolean | null
}

// TODO-215 sub-feature 1 (curator match feedback) — authoritative vocabulary,
// mirrors backend/app.py's _TAPEMATCH_JUDGMENTS. tools/tapematch/regression.py
// reads confirmed_same/confirmed_different as calibration truth.
const JUDGMENT_VALUES = ['confirmed_same', 'confirmed_different', 'uncertain', 'lb_wrong'] as const
type JudgmentValue = (typeof JUDGMENT_VALUES)[number]

const JUDGMENT_TONE: Record<JudgmentValue, string> = {
  confirmed_same: 'ok',
  confirmed_different: 'bad',
  uncertain: 'warn',
  lb_wrong: 'info',
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

// TODO-215 sub-feature 3: an LB number/label rendered as a real <button> that
// deep-links into the Library DetailPanel (`/library?lb=<n>`). Styled to look
// like the plain mono label it replaces — no default button chrome, accent
// hover — used for both the SimilarityMatrix axis labels and the family pills.
function LbLinkButton({ lb, label, onOpen }: {
  lb: number
  label?: string
  onOpen: (lb: number) => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={() => onOpen(lb)}
      title={t('tapematch.matrix.openInLibrary')}
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
      {label ?? lb}
    </button>
  )
}

// ── Header crawl status strip ─────────────────────────────────────────────────

function CrawlStatusStrip({ status }: { status: CrawlStatus | undefined }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<'start' | 'stop' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const handleAction = async (action: 'start' | 'stop') => {
    setPending(action)
    setError(null)
    setMessage(null)
    try {
      const resp = await fetch(`${BASE}/api/tapematch/crawl/${action}`, { method: 'POST' })
      if (action === 'start' && resp.status === 409) {
        setError(t('tapematch.crawl.alreadyRunning'))
        return
      }
      if (!resp.ok) {
        setError(t('tapematch.crawl.startFailed'))
        return
      }
      if (action === 'stop') {
        setMessage(t('tapematch.crawl.stopped'))
      }
      queryClient.invalidateQueries({ queryKey: ['tapematch-crawl-status'] })
    } catch {
      setError(t('tapematch.crawl.startFailed'))
    } finally {
      setPending(null)
    }
  }

  if (!status) return null
  const tone = status.running ? 'ok' : 'mute'
  const label = status.running ? t('tapematch.crawl.running') : t('tapematch.crawl.idle')
  const tooltip = status.log_tail?.length
    ? status.log_tail.join('\n')
    : t('tapematch.crawl.noLog')
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
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
      <Button
        variant="secondary" size="sm"
        disabled={status.running || pending !== null}
        onClick={() => handleAction('start')}
      >
        {pending === 'start' ? t('tapematch.crawl.starting') : t('tapematch.crawl.start')}
      </Button>
      <Button
        variant="secondary" size="sm"
        disabled={!status.running || pending !== null}
        onClick={() => handleAction('stop')}
      >
        {pending === 'stop' ? t('tapematch.crawl.stopping') : t('tapematch.crawl.stop')}
      </Button>
      {error && (
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-bad-fg)' }}>{error}</span>
      )}
      {message && (
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>{message}</span>
      )}
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

function SimilarityMatrix({
  pairs, isLoading, selectedPair, onSelectPair, onOpenLb,
}: {
  pairs: PairRow[]
  isLoading: boolean
  selectedPair: { lbA: number; lbB: number } | null
  onSelectPair: (lbA: number, lbB: number) => void
  onOpenLb: (lb: number) => void
}) {
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
            {axis.map(lb => (
              <TH key={lb} align="right">
                <LbLinkButton lb={lb} onOpen={onOpenLb} />
              </TH>
            ))}
          </tr>
        </thead>
        <tbody>
          {axis.map(rowLb => (
            <TR key={rowLb}>
              <TD mono align="right">
                <LbLinkButton lb={rowLb} onOpen={onOpenLb} />
              </TD>
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
                const judgmentTone = pair.human_judgment
                  ? JUDGMENT_TONE[pair.human_judgment as JudgmentValue]
                  : null
                const isSelected = !!selectedPair && (
                  (selectedPair.lbA === rowLb && selectedPair.lbB === colLb) ||
                  (selectedPair.lbA === colLb && selectedPair.lbB === rowLb)
                )
                return (
                  <TD
                    key={colLb}
                    align="right"
                    mono
                    onClick={() => onSelectPair(rowLb, colLb)}
                    style={{
                      background: `color-mix(in srgb, var(--lbb-accent-mid) ${Math.round(pct * 0.55)}%, var(--lbb-surface))`,
                      color: pct >= 50 ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
                      fontWeight: pair.same_family ? 700 : 400,
                      cursor: 'pointer',
                      boxShadow: [
                        judgmentTone ? `inset 3px 0 0 var(--lbb-${judgmentTone}-fg)` : null,
                        isSelected ? `inset 0 0 0 2px var(--lbb-accent-mid)` : null,
                      ].filter(Boolean).join(', ') || undefined,
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

// ── Judgment editor panel (TODO-215 sub-feature 1: curator match feedback) ───
// Rendered below the matrix, not a floating popover — the matrix lives inside
// an overflow-x container so an absolutely-positioned popover would clip/scroll
// oddly. `key`'d by the pair in ScreenTapeMatch so switching pairs remounts
// this with fresh draft state instead of carrying over stale local edits.

function JudgmentPanel({
  pair, date, runId, onCancel, onSaved,
}: {
  pair: PairRow
  date: string
  runId: string | null
  onCancel: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [judgment, setJudgment] = useState<JudgmentValue | null>(
    (pair.human_judgment as JudgmentValue | null) ?? null
  )
  const [notes, setNotes] = useState(pair.human_notes ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const resp = await fetch(`${BASE}/api/tapematch/pairs/judgment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date, lb_a: pair.lb_a, lb_b: pair.lb_b, run_id: runId,
          judgment, notes: notes.trim() || null,
        }),
      })
      if (resp.status === 409) {
        setError(t('tapematch.judgment.locked'))
        return
      }
      if (!resp.ok) {
        setError(t('tapematch.judgment.saveFailed'))
        return
      }
      onSaved()
    } catch {
      setError(t('tapematch.judgment.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      marginTop: 4, padding: 14, borderRadius: 8,
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: '0.04em',
          textTransform: 'uppercase', color: 'var(--lbb-fg3)',
        }}>
          {t('tapematch.judgment.title')}
        </span>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
          {t('tapematch.judgment.pairLabel', { a: fmtLb(pair.lb_a), b: fmtLb(pair.lb_b) })}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {JUDGMENT_VALUES.map(v => (
          <Chip key={v} size="sm" active={judgment === v} onClick={() => setJudgment(v)}>
            {t(`tapematch.judgment.options.${v}`)}
          </Chip>
        ))}
        <Chip size="sm" active={judgment === null} onClick={() => setJudgment(null)}>
          {t('common.clear')}
        </Chip>
      </div>

      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder={t('tapematch.judgment.notesPlaceholder')}
        rows={3}
        style={{
          resize: 'vertical', minHeight: 60, padding: '8px 10px', borderRadius: 6,
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
          color: 'var(--lbb-fg)', fontFamily: 'inherit', fontSize: 'var(--lbb-fs-12)',
          outline: 'none',
        }}
      />

      {error && (
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-bad-fg)' }}>{error}</div>
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          {t('common.cancel')}
        </Button>
        <Button variant="primary" size="sm" onClick={handleSave} disabled={saving}>
          {saving ? t('tapematch.judgment.saving') : t('common.save')}
        </Button>
      </div>
    </div>
  )
}

// ── A/B listening player (TODO-231 part 2/2: aligned A/B listening) ──────────
// Rendered next to JudgmentPanel when a pair is selected. Loading fetches one
// performance-time-aligned WAV clip per source (POST /api/ab_clip); both
// <audio> elements are started together and stay sample-aligned for the
// clip's duration, so the A/B toggle is just an instant (un)mute swap, never
// a reload/reseek. Disabled (controls inert, notEligible pill) when the pair
// isn't cleanly aligned per `ab_eligible` from GET /api/tapematch/pairs.

const AB_NUMBER_INPUT_STYLE: React.CSSProperties = {
  width: 56, padding: '3px 6px', borderRadius: 5,
  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
  color: 'var(--lbb-fg)', fontFamily: 'inherit', fontSize: 'var(--lbb-fs-11-5)',
  outline: 'none',
}

interface AbClipResult {
  clip_a: string
  clip_b: string
  t_sec: number
  dur_sec: number
}

function AbPlayerPanel({ pair, date }: { pair: PairRow; date: string }) {
  const { t } = useTranslation()
  const eligible = pair.ab_eligible === true
  const [tSec, setTSec] = useState('')
  const [durSec, setDurSec] = useState('20')
  const [clips, setClips] = useState<AbClipResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<'a' | 'b'>('a')
  const [playing, setPlaying] = useState(false)
  const audioARef = useRef<HTMLAudioElement>(null)
  const audioBRef = useRef<HTMLAudioElement>(null)

  const applyMute = (nextActive: 'a' | 'b') => {
    if (audioARef.current) audioARef.current.muted = nextActive !== 'a'
    if (audioBRef.current) audioBRef.current.muted = nextActive !== 'b'
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
          date, lb_a: pair.lb_a, lb_b: pair.lb_b,
          ...(trimmed === '' ? {} : { t_sec: Number(trimmed) }),
          dur_sec: Number(durSec) || 20,
        }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        const key = body?.error === 'not_eligible' ? 'notEligible'
          : body?.error === 't_out_of_range' ? 'outOfRange'
          : body?.error === 'folder_missing' ? 'folderMissing'
          : body?.error === 'locked' ? 'locked'
          : 'loadFailed'
        setError(t(`tapematch.abPlayer.${key}`))
        return
      }
      setClips(body)
      if (typeof body?.t_sec === 'number') {
        setTSec(String(Math.round(body.t_sec * 10) / 10))
      }
      setActive('a')
    } catch {
      setError(t('tapematch.abPlayer.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handlePlayPause = () => {
    const a = audioARef.current
    const b = audioBRef.current
    if (!a || !b) return
    if (playing) {
      a.pause()
      b.pause()
      setPlaying(false)
      return
    }
    a.currentTime = 0
    b.currentTime = 0
    applyMute(active)
    Promise.all([a.play(), b.play()]).catch(() => setPlaying(false))
    setPlaying(true)
  }

  const handleSetActive = (next: 'a' | 'b') => {
    setActive(next)
    applyMute(next)
  }

  const handleEnded = () => setPlaying(false)

  return (
    <div style={{
      marginTop: 10, padding: 14, borderRadius: 8,
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', gap: 10,
      opacity: eligible ? 1 : 0.55,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: '0.04em',
          textTransform: 'uppercase', color: 'var(--lbb-fg3)',
        }}>
          {t('tapematch.abPlayer.title')}
        </span>
        {!eligible && (
          <Pill tone="mute" soft>{t('tapematch.abPlayer.notEligible')}</Pill>
        )}
      </div>

      <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
          {t('tapematch.abPlayer.position')}
          <input
            type="number" min={0} step={1} value={tSec}
            placeholder={t('tapematch.abPlayer.autoPlaceholder')}
            disabled={!eligible}
            onChange={e => setTSec(e.target.value)}
            style={AB_NUMBER_INPUT_STYLE}
          />
          {t('tapematch.abPlayer.seconds')}
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
          {t('tapematch.abPlayer.duration')}
          <input
            type="number" min={5} max={60} step={1} value={durSec}
            disabled={!eligible}
            onChange={e => setDurSec(e.target.value)}
            style={AB_NUMBER_INPUT_STYLE}
          />
          {t('tapematch.abPlayer.seconds')}
        </label>
        <Button variant="secondary" size="sm" disabled={!eligible || loading} onClick={handleLoad}>
          {loading ? t('tapematch.abPlayer.loading') : t('tapematch.abPlayer.load')}
        </Button>
      </div>

      <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
        {t('tapematch.abPlayer.autoPickHint')}
      </div>

      {error && (
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-bad-fg)' }}>{error}</div>
      )}

      {clips && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <Button variant="primary" size="sm" onClick={handlePlayPause}>
            {playing ? t('tapematch.abPlayer.pause') : t('tapematch.abPlayer.play')}
          </Button>
          <div style={{ display: 'flex', gap: 4 }}>
            <Chip size="sm" active={active === 'a'} onClick={() => handleSetActive('a')}>
              {t('tapematch.abPlayer.sourceLabel', { role: 'A', lb: fmtLb(pair.lb_a) })}
            </Chip>
            <Chip size="sm" active={active === 'b'} onClick={() => handleSetActive('b')}>
              {t('tapematch.abPlayer.sourceLabel', { role: 'B', lb: fmtLb(pair.lb_b) })}
            </Chip>
          </div>
          <audio
            ref={audioARef} src={`${BASE}${clips.clip_a}`} preload="auto"
            onEnded={handleEnded} style={{ display: 'none' }}
          />
          <audio
            ref={audioBRef} src={`${BASE}${clips.clip_b}`} preload="auto"
            onEnded={handleEnded} style={{ display: 'none' }}
          />
        </div>
      )}
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<ViewFilter>('all')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [analysisOpen, setAnalysisOpen] = useState(false)
  const [selectedPair, setSelectedPair] = useState<{ lbA: number; lbB: number } | null>(null)

  // TODO-215 sub-feature 3: LB deep-link into the Library DetailPanel.
  const openLb = (lb: number) => navigate(`/library?lb=${lb}`)

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
  const pairsRunId: string | null = pairsData?.run_id ?? null

  const selectedPairRow = useMemo(() => {
    if (!selectedPair) return null
    return pairs.find(p =>
      (p.lb_a === selectedPair.lbA && p.lb_b === selectedPair.lbB) ||
      (p.lb_a === selectedPair.lbB && p.lb_b === selectedPair.lbA)
    ) ?? null
  }, [pairs, selectedPair])

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
          onSelect={date => { setSelectedDate(date); setAnalysisOpen(false); setSelectedPair(null) }}
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
                      {g.label}:{' '}
                      {g.lbs.map((lb, i) => (
                        <React.Fragment key={lb}>
                          {i > 0 && ' '}
                          <LbLinkButton lb={lb} label={fmtLb(lb)} onOpen={openLb} />
                        </React.Fragment>
                      ))}
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
                <SimilarityMatrix
                  pairs={pairs}
                  isLoading={pairsLoading}
                  selectedPair={selectedPair}
                  onSelectPair={(lbA, lbB) => {
                    setSelectedPair(prev =>
                      prev && ((prev.lbA === lbA && prev.lbB === lbB) || (prev.lbA === lbB && prev.lbB === lbA))
                        ? null
                        : { lbA, lbB }
                    )
                  }}
                  onOpenLb={openLb}
                />
                {selectedPairRow && selectedDate && (
                  <JudgmentPanel
                    key={`${selectedPairRow.lb_a}-${selectedPairRow.lb_b}`}
                    pair={selectedPairRow}
                    date={selectedDate}
                    runId={pairsRunId}
                    onCancel={() => setSelectedPair(null)}
                    onSaved={() => {
                      queryClient.invalidateQueries({ queryKey: ['tapematch-pairs', selectedDate] })
                      setSelectedPair(null)
                    }}
                  />
                )}
                {selectedPairRow && selectedDate && (
                  <AbPlayerPanel
                    key={`ab-${selectedPairRow.lb_a}-${selectedPairRow.lb_b}`}
                    pair={selectedPairRow}
                    date={selectedDate}
                  />
                )}
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
