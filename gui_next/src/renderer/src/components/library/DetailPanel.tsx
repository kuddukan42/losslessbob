// TODO-150 step 8: detail-panel zones (instructions/design_handoff_unified_library/
// 02-action-system-parity.md "Redesigned detail panel — intent zones"). Replaces the
// old flat button-soup pattern with: header (title/badges) -> ActionBar (1 primary +
// Reveal + grouped "More" overflow, same registry as the right-click menu from step 7)
// -> ShareSeed (qBittorrent/torrent/forum status + a single date-sorted activity log,
// merged client-side from the already-loaded /api/collection/prefetch torrents/forum_posts
// arrays — no new backend endpoint) -> AssetStrip (attachments/spectrograms/map as
// state-bearing chips) -> an optional Setlist line for the performance lens.

import React, { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pill, Button, IconButton } from '../primitives'
import type { ActionRow, ActionHandlers, LibAction } from './actions'
import { buildRecordingActions, buildPerformanceActions } from './actions'
import { Icon } from '../Icon'
import { EvidenceList } from '../EvidenceList'
import type { EvidenceRecord } from '../EvidenceList'
import { lbDetailUrl } from '../../lib/lbUrl'
import { useSettingsStore } from '../../store'

const BASE = window.api.flaskBase

export interface HistoryEvent { d: string; f: string; tag: string }
export interface RowHistory { torrents: HistoryEvent[]; forum: HistoryEvent[] }

// Structural superset of ActionRow that the panel reads for display. RecordingRow
// (ScreenLibrary.tsx) has all of these fields plus extras, so it satisfies this
// directly — no conversion needed at call sites.
export interface DetailRow extends ActionRow {
  date: string
  loc: string
  desc: string
  rating: string
  src: string | null
  status: string
  folder: string
  conf: string
  dup: boolean
  xref: boolean
  // FABLE_UNIFIED_RANKING phase 3/4 (F4 Library payload pattern): merged in
  // from /api/library/performances via the performance lens's row merge —
  // absent when the recording lens's own /api/search-sourced row is passed
  // straight through (show_picks/curated data doesn't ride that payload).
  pickRank?: number
  absGrade?: string
  curated?: string[]
}

// Minimal recording shape used inside PerformanceDetailPanel family cards.
// RecordingRow from ScreenLibrary.tsx is a structural superset so it satisfies this.
export interface PerfRecording {
  lb: string
  lbNumber: number
  owned: boolean
  wish: boolean
  dup: boolean
  rating: string
  desc: string
  src: string | null
  famBy?: string
  famConf?: number | null
  pickRank?: number
  absGrade?: string
  curated?: string[]
}

export interface PerfFamily {
  id: string
  // TapeMatch's match-group name (e.g. "Solo" / "Family A"); null when the
  // family has no TapeMatch grouping. The source type is shown via SourceBadge,
  // so the card falls back to the source name rather than repeating a label.
  tmLabel: string | null
  src: string | null
  by: string
  conf: number | null
  total: number
  multi: boolean
  owned: boolean
  ownedCount: number
  bestRating: string
  members: PerfRecording[]
  canonical: PerfRecording | null
}

export type PerfMeta = {
  id: string
  disp: string
  dow?: string
  venue: string | null
  city: string | null
  tour?: string
  tracks?: number
  setlist?: string
  title?: string
  confirmed?: boolean
}

const SRC_ABBR: Record<string, string> = {
  Soundboard: 'SBD', Audience: 'AUD', 'FM/Pre-FM': 'FM', Master: 'MST', Mixed: 'MTX', ALD: 'ALD',
}

const SRC_HUE: Record<string, string> = {
  Soundboard:  'var(--lbb-ok-fg)',
  'FM/Pre-FM': 'var(--lbb-info-fg)',
  Audience:    'var(--lbb-fg2)',
  Master:      'var(--lbb-accent-mid)',
  Mixed:       'var(--lbb-warn-fg)',
  ALD:         'var(--lbb-bad-fg)',
}

function statusTone(s: string): 'ok' | 'warn' | 'mute' {
  if (s === 'Public') return 'ok'
  if (s === 'Missing') return 'warn'
  return 'mute'
}

function ratingTone(r: string): 'ok' | 'info' | 'warn' | 'mute' {
  if (r.startsWith('A')) return 'ok'
  if (r.startsWith('B')) return 'info'
  if (r === '—') return 'mute'
  return 'warn'
}

function coverageTone(c: string): 'ok' | 'warn' | 'mute' {
  if (c === 'Covered') return 'ok'
  if (c === 'Gap') return 'mute'
  return 'warn'
}

// Shared aside styles with --sep-detail-* token cascade (matches prototype perf-parts.jsx)
function panelAsideStyle(width: number): React.CSSProperties {
  return {
    width, flex: `0 0 ${width}px`,
    background: 'var(--sep-detail-bg, var(--lbb-surface))',
    borderLeft: '1px solid var(--lbb-border)',
    borderRadius: 'var(--sep-radius, 0px)',
    boxShadow: 'var(--sep-detail-shadow, none)',
    display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden',
    position: 'relative',
  }
}

// Drag handle on the panel's left edge — lets the user widen it when its fixed
// default width clips content (e.g. the tab strip growing past ~5 tabs).
function ResizeHandle({ onResizeStart }: { onResizeStart: (e: React.MouseEvent) => void }) {
  return (
    <div
      onMouseDown={e => { e.preventDefault(); onResizeStart(e) }}
      style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 6,
        cursor: 'col-resize', zIndex: 1,
        borderLeft: '2px solid transparent',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderLeftColor = 'var(--lbb-border2)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderLeftColor = 'transparent' }}
    />
  )
}

// Collapsed stub — 40px wide with single info icon (matches prototype collapsed state)
function CollapsedStub({ onToggle }: { onToggle: () => void }) {
  const { t } = useTranslation()
  return (
    <aside style={{
      width: 40, flex: '0 0 40px',
      background: 'var(--sep-detail-bg, var(--lbb-surface))',
      borderLeft: '1px solid var(--lbb-border)',
      borderRadius: 'var(--sep-radius, 0px)',
      boxShadow: 'var(--sep-detail-shadow, none)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 8,
    }}>
      <IconButton icon="info" title={t('library.panel.showDetails')} onClick={onToggle} />
    </aside>
  )
}

// Panel header: LABEL | optional LB-page button | chevRight collapse
function PanelHeader({
  label, lbPageLabel, onOpenLbPage, onToggle,
}: {
  label: string
  lbPageLabel?: string
  onOpenLbPage?: () => void
  onToggle: () => void
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      padding: '10px 10px 10px 16px', borderBottom: '1px solid var(--lbb-border)',
      display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
    }}>
      <span style={{
        flex: 1, fontSize: 'var(--t-label)', fontWeight: 'var(--w-bold)',
        letterSpacing: 'var(--track-eyebrow)', textTransform: 'uppercase', color: 'var(--lbb-fg3)',
      }}>{label}</span>
      {onOpenLbPage && (
        <Button size="sm" variant="ghost" icon="reveal" onClick={onOpenLbPage}>
          {lbPageLabel ?? t('library.panel.lbPage')}
        </Button>
      )}
      <IconButton icon="chevRight" size={24} title={t('library.panel.collapseDetails')} onClick={onToggle} />
    </div>
  )
}

function ZoneLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 'var(--t-label)', fontWeight: 'var(--w-bold)', letterSpacing: 'var(--track-eyebrow)',
      textTransform: 'uppercase', color: 'var(--lbb-fg3)', margin: '14px 0 8px',
    }}>
      {children}
    </div>
  )
}

// ── Source badge — compact 2–3 letter code (perf-parts.jsx SourceBadge) ────────
function SourceBadge({ src, owned }: { src: string | null; owned: boolean }) {
  if (!src) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        minWidth: 30, height: 18, padding: '0 5px', borderRadius: 4,
        fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)', letterSpacing: 0.3,
        border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)',
      }}>—</span>
    )
  }
  const code = SRC_ABBR[src] ?? src.slice(0, 3).toUpperCase()
  const hue = SRC_HUE[src] ?? 'var(--lbb-fg2)'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 30, height: 18, padding: '0 5px', borderRadius: 4,
      fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)', letterSpacing: 0.3,
      background: owned ? `color-mix(in srgb, ${hue} 18%, transparent)` : 'transparent',
      color: owned ? hue : 'var(--lbb-fg3)',
      border: `1px solid ${owned ? `color-mix(in srgb, ${hue} 45%, transparent)` : 'var(--lbb-border2)'}`,
      opacity: owned ? 1 : 0.72,
    }}>{code}</span>
  )
}

// ── Coverage chip (perf-parts.jsx CoverageChip) ─────────────────────────────
function CoverageChip({ coverage, ownedCount, total }: { coverage: string; ownedCount: number; total: number }) {
  const { t } = useTranslation()
  const map: Record<string, { tone: string; label: string; icon: string }> = {
    Covered:      { tone: 'ok',   label: total > 1 ? t('library.coverage.ownedFull', { owned: ownedCount, total }) : t('library.coverage.owned'), icon: 'check' },
    Upgrade:      { tone: 'warn', label: t('library.coverage.upgrade', { owned: ownedCount, total }), icon: 'upload' },
    Gap:          { tone: 'mute', label: t('library.coverage.gap'), icon: 'x' },
    Undocumented: { tone: 'warn', label: t('library.coverage.noSource'), icon: 'alert' },
  }
  const m = map[coverage] ?? map.Gap
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '1px 8px 1px 6px', borderRadius: 999, whiteSpace: 'nowrap',
      background: `var(--lbb-${m.tone}-bg)`, color: `var(--lbb-${m.tone}-fg)`,
      border: `1px solid color-mix(in srgb, var(--lbb-${m.tone}-bar) 50%, transparent)`,
      fontSize: 'var(--t-micro)', fontWeight: 'var(--w-semi)', fontVariantNumeric: 'tabular-nums',
    }}>
      <Icon name={m.icon} size={11} />
      {m.label}
    </span>
  )
}

// ── TapeMatch confidence chip ─────────────────────────────────────────────────
function MatchChip({ by, conf }: { by: string; conf: number | null }) {
  const MAP: Record<string, { tone: string; icon: string; code: string }> = {
    ai:     { tone: 'info', icon: 'tapematch', code: 'AI' },
    'ai+lb': { tone: 'ok',  icon: 'tapematch', code: 'AI + LB' },
    lb:     { tone: 'mute', icon: 'link',      code: 'LB' },
  }
  const m = MAP[by] ?? MAP.lb
  const pct = conf != null ? `${Math.round(conf * 100)}%` : null
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '1px 7px 1px 5px', height: 18, borderRadius: 4,
      background: `var(--lbb-${m.tone}-bg)`, color: `var(--lbb-${m.tone}-fg)`,
      border: `1px solid color-mix(in srgb, var(--lbb-${m.tone}-bar) 55%, transparent)`,
      fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)', letterSpacing: 0.02, whiteSpace: 'nowrap',
    }}>
      <Icon name={m.icon} size={10.5} />
      {m.code}{pct && <span style={{ opacity: 0.85, fontWeight: 'var(--w-semi)' }}> · {pct}</span>}
    </span>
  )
}

// ── Family-level coverage meter ───────────────────────────────────────────────
function FamilyMeter({ families }: { families: PerfFamily[] }) {
  const { t } = useTranslation()
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {families.map(f => (
        <span key={f.id} title={`${f.tmLabel ?? f.src ?? t('library.family.recording')} · ${t('library.family.uploads', { count: f.total })}`} style={{
          flex: f.total, height: 6, borderRadius: 3,
          background: f.owned ? 'var(--lbb-ok-bar)' : 'var(--lbb-surface2)',
          border: f.owned ? 'none' : '1px solid var(--lbb-border2)',
        }} />
      ))}
    </div>
  )
}

// ── Stat fact card ─────────────────────────────────────────────────────────────
function Fact({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
      <div style={{ fontSize: 'var(--lbb-fs-18)', fontWeight: 'var(--w-bold)', color: 'var(--lbb-fg)', fontVariantNumeric: 'tabular-nums', letterSpacing: -0.01 }}>
        {value}{sub && <span style={{ fontSize: 'var(--t-micro)', fontWeight: 'var(--w-med)', color: 'var(--lbb-fg3)', marginLeft: 3 }}>{sub}</span>}
      </div>
      <div style={{ fontSize: 'var(--t-micro)', fontWeight: 'var(--w-semi)', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

// ── Member row inside a family card ──────────────────────────────────────────
function MemberRow({ r, isCanonical }: { r: PerfRecording; isCanonical: boolean }) {
  const { t } = useTranslation()
  const tag = isCanonical ? { tone: 'info' as const, label: t('library.family.bestInFamily') }
            : r.dup       ? { tone: 'mute' as const, label: t('library.family.duplicate') }
            : null
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 8, padding: '7px 10px',
      background: isCanonical ? 'color-mix(in srgb, var(--lbb-accent-soft) 60%, transparent)' : 'transparent',
      borderTop: '1px solid var(--lbb-border)',
    }}>
      <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', flexShrink: 0 }}>
        {isCanonical ? '●' : '└'}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono)', fontWeight: 'var(--w-semi)', color: r.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)' }}>
            {r.lb}
          </span>
          {r.pickRank === 1 && (
            <span title={t('library.picks.recommendedTitle')} style={{ color: 'var(--lbb-accent-mid)', fontSize: 'var(--t-meta)' }}>★</span>
          )}
          {tag && <Pill tone={tag.tone} soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{tag.label}</Pill>}
          <div style={{ flex: 1 }} />
          {r.curated?.map(name => (
            <Pill key={name} tone="info" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>
              {t('library.picks.curatedBadge', { curator: name })}
            </Pill>
          ))}
          {r.owned && r.absGrade && (
            <Pill tone="info" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{r.absGrade}</Pill>
          )}
          {r.rating !== '—' && <Pill tone={ratingTone(r.rating)} soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{r.rating}</Pill>}
          {r.owned
            ? <Pill tone="ok" soft dot style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{t('library.family.owned')}</Pill>
            : r.wish ? <Pill tone="warn" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{t('library.family.wishlist')}</Pill>
            : <Pill tone="mute" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{t('library.family.notOwned')}</Pill>}
        </div>
        {r.src && (
          <div style={{ fontSize: 'var(--t-micro)', color: 'var(--lbb-fg3)', marginTop: 3 }}>{r.src}</div>
        )}
      </div>
    </div>
  )
}

// ── Family card — one TapeMatch family with its members ──────────────────────
function FamilyCard({ fam }: { fam: PerfFamily }) {
  const { t } = useTranslation()
  return (
    <div style={{
      borderRadius: 8, overflow: 'hidden',
      border: `1px solid ${fam.owned ? 'color-mix(in srgb, var(--lbb-accent-mid) 40%, transparent)' : 'var(--lbb-border)'}`,
      background: fam.owned ? 'var(--lbb-surface2)' : 'transparent',
    }}>
      <div style={{ padding: '9px 10px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <SourceBadge src={fam.src} owned={fam.owned} />
        <span style={{ fontSize: 'var(--t-title)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg)' }}>{fam.tmLabel ?? fam.src ?? t('library.family.recording')}</span>
        <MatchChip by={fam.by} conf={fam.conf} />
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 'var(--t-micro)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
          {t('library.family.uploads', { count: fam.total })}
        </span>
      </div>
      <div>
        {fam.members.map((r) => (
          <MemberRow
            key={r.lb}
            r={r}
            isCanonical={fam.multi && r.lb === fam.canonical?.lb}
          />
        ))}
      </div>
    </div>
  )
}

// ── Setlist — lazy-fetched from /api/bobdylan/show?date=YYYY-MM-DD ───────────
function Setlist({ date }: { date: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['bobdylan-setlist', date],
    queryFn: () => fetch(`${BASE}/api/bobdylan/show?date=${encodeURIComponent(date)}`).then(r => r.status === 204 ? null : r.json()),
    staleTime: 300_000,
    enabled: !!date,
  })

  if (isLoading) return (
    <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', padding: '10px 0' }}>{t('library.setlist.loading')}</div>
  )
  if (!data || !data.tracks?.length) return (
    <div style={{
      padding: '14px 12px', borderRadius: 6, textAlign: 'center',
      border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 'var(--t-meta)',
    }}>
      {t('library.setlist.notScraped')}
    </div>
  )

  return (
    <div>
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 6, overflow: 'hidden' }}>
        {(data.tracks as { name: string }[]).map((t, ti) => (
          <div key={ti} style={{
            display: 'flex', alignItems: 'baseline', gap: 8, padding: '3.5px 10px',
            fontSize: 'var(--t-meta)', lineHeight: 1.45,
            background: ti % 2 === 1 ? 'color-mix(in srgb, var(--lbb-surface2) 40%, transparent)' : 'transparent',
          }}>
            <span style={{ width: 18, textAlign: 'right', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg3)', flexShrink: 0 }}>
              {ti + 1}
            </span>
            <span style={{ flex: 1, color: 'var(--lbb-fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {t.name}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── ChecksumsZone — the entry's documented checksums grouped by fileset
// (FABLE_XREF_INCORPORATION.md D5): canonical block first, then one block per
// xref id, mirroring the site's own per-fileset breakdown. This is catalog
// data about the entry (checksums.xref), never a statement about which
// fileset this row's own copy is — that's the copy-level pill above. ────────

interface EntryChecksumRow { filename: string; xref: number | null }

function ChecksumsZone({ lbNumber }: { lbNumber: number }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['library-entry-checksums', lbNumber],
    queryFn: () => fetch(`${BASE}/api/entry/${lbNumber}`).then(r => (r.status === 404 ? null : r.json())),
    staleTime: 300_000,
  })

  const checksums: EntryChecksumRow[] = Array.isArray(data?.checksums) ? data.checksums : []
  if (isLoading || checksums.length === 0) return null

  const groups = new Map<number, string[]>()
  for (const c of checksums) {
    const key = c.xref ?? 0
    const arr = groups.get(key)
    if (arr) { if (!arr.includes(c.filename)) arr.push(c.filename) }
    else groups.set(key, [c.filename])
  }
  const sortedKeys = [...groups.keys()].sort((a, b) => a - b) // canonical (0) first

  return (
    <div style={{ marginTop: 14 }}>
      <ZoneLabel>{t('library.panel.checksumsLabel')}</ZoneLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sortedKeys.map(key => {
          const files = groups.get(key)!
          return (
            <div key={key} style={{ border: '1px solid var(--lbb-border)', borderRadius: 6, overflow: 'hidden' }}>
              <div style={{
                padding: '5px 10px', fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)',
                letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--lbb-fg3)',
                background: 'var(--lbb-surface2)', borderBottom: '1px solid var(--lbb-border)',
              }}>
                {key === 0
                  ? t('library.panel.checksumsCanonical', { count: files.length })
                  : t('library.panel.checksumsXrefGroup', { id: String(key).padStart(5, '0'), count: files.length })}
              </div>
              <div style={{ padding: '3px 0' }}>
                {files.map(f => (
                  <div key={f} title={f} style={{
                    padding: '2.5px 10px', fontSize: 'var(--t-mono-sm)', fontFamily: 'var(--lbb-mono)',
                    color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {f}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── ActionBar — one primary + Reveal inline; everything else lives in the
// "More" overflow, which renders the identical grouped list as the right-click
// menu (same `openMenu` the context menu already uses). ───────────────────────

function ActionBarZone({ actions, onMore }: { actions: LibAction[]; onMore: (e: React.MouseEvent) => void }) {
  const { t } = useTranslation()
  const primary = actions.find(a => a.primary)
  const reveal = actions.find(a => a.id === 'reveal')
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10, flexShrink: 0 }}>
      {primary && (
        <Button variant="primary" icon={primary.icon} disabled={primary.disabled} onClick={primary.run}>
          {primary.label}
        </Button>
      )}
      {reveal && (
        <Button variant="secondary" icon={reveal.icon} disabled={reveal.disabled} onClick={reveal.run}>
          {reveal.label}
        </Button>
      )}
      <div style={{ flex: 1 }} />
      <Button variant="ghost" icon="more" onClick={onMore}>{t('library.panel.more')}</Button>
    </div>
  )
}

// ── ShareSeed — status line + the three distribution actions + a unified,
// filterable activity log built from the torrents/forum_posts already bundled
// in /api/collection/prefetch (per row.lbNumber). Absent history = "Not shared
// yet" empty state, never a fake log (03-data-contract.md Entity 4). ──────────

function ShareSeedZone({ history, busy, onQbt, onTorrent, onForum, note, hideLabel }: {
  history: RowHistory | undefined
  busy?: boolean
  onQbt: () => void
  onTorrent: () => void
  onForum: () => void
  note?: string
  hideLabel?: boolean
}) {
  const { t } = useTranslation()
  const [filter, setFilter] = useState<'all' | 'torrents' | 'forum'>('all')
  const torrents = history?.torrents ?? []
  const forum = history?.forum ?? []
  const seeding = torrents.filter(e => e.tag === 'qBittorrent').length
  const lastForum = forum[0]?.d

  const parts: string[] = []
  if (seeding > 0) parts.push(t('library.share.seeding', { count: seeding }))
  if (lastForum) parts.push(t('library.share.lastForumPost', { date: lastForum }))
  const status = parts.length > 0 ? parts.join(' · ') : t('library.share.notSharedYet')

  const filterLabels: Record<'all' | 'torrents' | 'forum', string> = {
    all: t('library.share.filterAll'),
    torrents: t('library.share.filterTorrents'),
    forum: t('library.share.filterForum'),
  }

  const log = [
    ...torrents.map(t => ({ ...t, kind: 'torrent' as const })),
    ...forum.map(f => ({ ...f, kind: 'forum' as const })),
  ]
    .filter(e => filter === 'all' || (filter === 'torrents' ? e.kind === 'torrent' : e.kind === 'forum'))
    .sort((a, b) => b.d.localeCompare(a.d))

  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.share.label')}</ZoneLabel>}
      {note && <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', marginBottom: 6 }}>{note}</div>}
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginBottom: 8 }}>{status}</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
        <Button variant="secondary" size="sm" icon="upload" disabled={busy} onClick={onQbt}>{t('library.share.addQbt')}</Button>
        <Button variant="secondary" size="sm" icon="copy" disabled={busy} onClick={onTorrent}>{t('library.share.regenerate')}</Button>
        <Button variant="secondary" size="sm" icon="globe" disabled={busy} onClick={onForum}>{t('library.share.post')}</Button>
      </div>
      {(torrents.length > 0 || forum.length > 0) && (
        <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
          {(['all', 'torrents', 'forum'] as const).map(f => (
            <button
              key={f} type="button" onClick={() => setFilter(f)}
              style={{
                padding: '2px 8px', borderRadius: 999, fontSize: 'var(--lbb-fs-10-5)',
                border: '1px solid var(--lbb-border2)', cursor: 'pointer',
                background: filter === f ? 'var(--lbb-accent-soft)' : 'transparent',
                color: filter === f ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
              }}
            >
              {filterLabels[f]}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 160, overflowY: 'auto' }}>
        {log.length === 0 ? (
          <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '4px 0' }}>{t('library.share.notSharedYet')}</div>
        ) : log.map((e, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontSize: 'var(--lbb-fs-11-5)' }}>
            <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', flexShrink: 0 }}>{e.d}</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--lbb-fg2)' }}>{e.f}</span>
            <Pill tone={e.kind === 'torrent' ? 'info' : 'mute'} soft>{e.tag}</Pill>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── AssetStrip — attachments count, spectrogram readiness, map availability
// as state-bearing chips (not three identical buttons). Spectrogram readiness
// is checked lazily (only while this zone is mounted) via the existing
// /api/spectrogram/list endpoint, scoped to this row's folder. ───────────────

interface AttachmentFile { filename: string; clean_name: string }

function AssetStripZone({ row, attachCount, onAttach, onSpectro, onMap, hideLabel }: {
  row: DetailRow
  attachCount: number | undefined
  onAttach: () => void
  onSpectro: () => void
  onMap: () => void
  hideLabel?: boolean
}) {
  const { t } = useTranslation()
  const { data: specData, isLoading: specLoading } = useQuery({
    queryKey: ['library-spectro-check', row.path],
    queryFn: () => fetch(`${BASE}/api/spectrogram/list`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: [row.path] }),
    }).then(r => r.json()),
    enabled: row.owned && !!row.path,
    staleTime: 30_000,
  })
  const entries: Array<{ has_png: boolean }> = specData?.[row.path] ?? []
  const ready = entries.filter(e => e.has_png).length

  let specLabel = t('library.assets.spectrograms')
  let specTone: 'ok' | 'warn' | 'mute' = 'mute'
  if (specLoading) specLabel = t('library.assets.spectrogramsChecking')
  else if (entries.length === 0) specLabel = t('library.assets.spectrogramsNone')
  else { specLabel = t('library.assets.spectrogramsReady', { ready, total: entries.length }); specTone = ready === entries.length ? 'ok' : 'warn' }

  // TODO-163: reuses ScreenLibrary's already-fetched attachments-cached query
  // (same key -> same cache entry, no extra request) to list actual filenames
  // inline instead of just the count.
  const { data: attachData } = useQuery({
    queryKey: ['library-attachments-cached'],
    queryFn: () => fetch(`${BASE}/api/attachments/cached`).then(r => r.json()),
    staleTime: 60_000,
  })
  const files: AttachmentFile[] = attachData?.entries?.find(
    (e: { lb_number: number }) => e.lb_number === row.lbNumber
  )?.files ?? []

  const { data: dbSettings } = useQuery({
    queryKey: ['db-settings-data-dir'],
    queryFn: () => fetch(`${BASE}/api/db/settings`).then(r => r.json()),
    staleTime: Infinity,
  })
  const dataDir: string | undefined = dbSettings?.data_dir

  const [filesOpen, setFilesOpen] = useState(false)
  const filesRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!filesOpen) return
    function onClickOut(e: MouseEvent) {
      if (filesRef.current && !filesRef.current.contains(e.target as Node)) setFilesOpen(false)
    }
    document.addEventListener('mousedown', onClickOut)
    return () => document.removeEventListener('mousedown', onClickOut)
  }, [filesOpen])

  const openFile = (f: AttachmentFile) => {
    if (!dataDir) return
    window.api.openPath(`${dataDir}/attachments/LB-${String(row.lbNumber).padStart(5, '0')}/${f.filename}`)
  }

  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.assets.label')}</ZoneLabel>}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <div ref={filesRef} style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setFilesOpen(o => !o)}
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
          >
            <Pill tone={attachCount ? 'ok' : 'mute'} soft dot={!!attachCount}>
              {attachCount ? t('library.assets.attachments', { count: attachCount }) : t('library.assets.noAttachments')}
            </Pill>
          </button>
          {filesOpen && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 20,
              minWidth: 220, maxWidth: 320, maxHeight: 220, overflowY: 'auto',
              background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
              borderRadius: 6, boxShadow: '0 4px 16px rgba(0,0,0,0.2)', padding: 4,
            }}>
              {files.length === 0 ? (
                <div style={{ padding: '6px 8px', fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                  {t('library.assets.noAttachments')}
                </div>
              ) : files.map(f => (
                <button
                  key={f.filename}
                  type="button"
                  onClick={() => openFile(f)}
                  disabled={!dataDir}
                  title={f.filename}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    background: 'none', border: 'none', textAlign: 'left', padding: '5px 8px',
                    borderRadius: 4, cursor: dataDir ? 'pointer' : 'default',
                    fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
                  }}
                  onMouseEnter={e => { if (dataDir) e.currentTarget.style.background = 'var(--lbb-surface2)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                >
                  <Icon name="attachments" size={12} style={{ flexShrink: 0, color: 'var(--lbb-fg3)' }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.clean_name || f.filename}
                  </span>
                </button>
              ))}
              <button
                type="button"
                onClick={() => { setFilesOpen(false); onAttach() }}
                style={{
                  display: 'block', width: '100%', marginTop: 4, padding: '5px 8px',
                  borderTop: '1px solid var(--lbb-border)', background: 'none', border: 'none',
                  borderTopWidth: 1, textAlign: 'left', cursor: 'pointer',
                  fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-accent-mid)',
                }}
              >
                {t('library.assets.viewAll')}
              </button>
            </div>
          )}
        </div>
        {row.owned && (
          <button type="button" onClick={onSpectro} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
            <Pill tone={specTone} soft>{specLabel}</Pill>
          </button>
        )}
        <button type="button" onClick={onMap} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
          <Pill tone="info" soft>{t('library.assets.showOnMap')}</Pill>
        </button>
      </div>
    </div>
  )
}

// ── QualityZone — LB Rating (catalog) side by side with the AI Quality Index
// (Concert Ranker's abs_grade/abs_score, latest scan), lazy-fetched per row
// via /api/quality/<lb>. ────────────────────────────────────────────────────

interface QualityMetrics {
  mono: boolean
  stereo_width: number | null
  stereo_width_label: string | null
  clip_fraction: number | null
  crowd_snr_db: number | null
  crowd_snr_label: string | null
  bass_ratio_db: number | null
  bass_label: string | null
  mud_ratio_db: number | null
  mud_label: string | null
  harsh_ratio_db: number | null
  harsh_label: string | null
  source_flags: string[]
}

interface QualityScore {
  abs_grade: string | null
  abs_score: number | null
  final_score: number | null
  rank_in_family: number | null
  vetoed: number
  verdict_text: string | null
  metrics: QualityMetrics | null
}

// ── Metric magnitude bar — thin track + rounded fill, tone-colored, for the
// Quality tab's stereo width / clipping / tonal-balance visualizations.
// `pct` is 0-100, pre-clamped by the caller (each metric has its own domain).
function MetricBar({ label, valueLabel, pct, tone, note }: {
  label: string; valueLabel: string; pct: number; tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; note?: string
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
        <span style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)' }}>{label}</span>
        <span style={{ fontSize: 'var(--t-meta)', fontWeight: 'var(--w-semi)', color: `var(--lbb-${tone}-fg)`, fontVariantNumeric: 'tabular-nums' }}>
          {valueLabel}{note && <span style={{ color: 'var(--lbb-fg3)', fontWeight: 'var(--w-med)' }}> · {note}</span>}
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)', overflow: 'hidden' }}>
        <div style={{
          width: `${Math.max(2, Math.min(100, pct))}%`, height: '100%', borderRadius: 3,
          background: `var(--lbb-${tone}-bar)`,
        }} />
      </div>
    </div>
  )
}

// ── Small tone-colored chip for source-type flags ──────────────────────────
function FlagChip({ text, tone }: { text: string; tone: 'warn' | 'bad' }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap',
      background: `var(--lbb-${tone}-bg)`, color: `var(--lbb-${tone}-fg)`,
      border: `1px solid color-mix(in srgb, var(--lbb-${tone}-bar) 50%, transparent)`,
      fontSize: 'var(--t-micro)', fontWeight: 'var(--w-semi)',
    }}>
      <Icon name="alert" size={10} />
      {text}
    </span>
  )
}

const _CROWD_TONE: Record<string, 'bad' | 'warn' | 'mute' | 'ok'> = {
  'buried in crowd': 'bad', 'crowd-heavy': 'warn', 'some crowd': 'mute', clean: 'ok',
}
const _SEVERITY_TONE: Record<string, 'bad' | 'warn'> = {
  muddy: 'bad', 'slightly muddy': 'warn', harsh: 'bad', 'a little forward': 'warn',
}

// ── QualityMetricsPanel — Concert Ranker raw-signal visualizations (stereo
// width, clipping, crowd separation, tonal balance, source-type flags) below
// the LB Rating / AI Quality Index tiles. ───────────────────────────────────
function QualityMetricsPanel({ metrics }: { metrics: QualityMetrics }) {
  const { t } = useTranslation()

  const widthPct = metrics.mono ? 0 : Math.min(100, ((metrics.stereo_width ?? 0) / 1.0) * 100)
  const widthTone: 'info' | 'warn' | 'mute' = metrics.mono ? 'mute'
    : metrics.stereo_width_label === 'effectively mono' ? 'warn'
    : metrics.stereo_width_label === 'very wide' ? 'info' : 'mute'

  const clipPct = Math.min(100, ((metrics.clip_fraction ?? 0) / 0.05) * 100)
  const clipTone: 'ok' | 'warn' | 'bad' = (metrics.clip_fraction ?? 0) > 0.02 ? 'bad'
    : (metrics.clip_fraction ?? 0) > 0 ? 'warn' : 'ok'

  const crowdTone = (metrics.crowd_snr_label && _CROWD_TONE[metrics.crowd_snr_label]) || 'mute'
  const crowdPct = metrics.crowd_snr_db == null ? 0 : Math.max(0, Math.min(100, (metrics.crowd_snr_db / 24) * 100))

  const bassPct = metrics.bass_ratio_db == null ? 0 : Math.max(0, Math.min(100, (metrics.bass_ratio_db / 33) * 100))
  const bassTone: 'info' | 'mute' = metrics.bass_label ? 'info' : 'mute'
  const mudPct = metrics.mud_ratio_db == null ? 0 : Math.max(0, Math.min(100, (metrics.mud_ratio_db / 40) * 100))
  const mudTone = (metrics.mud_label && _SEVERITY_TONE[metrics.mud_label]) || 'ok'
  const harshPct = metrics.harsh_ratio_db == null ? 0 : Math.max(0, Math.min(100, ((metrics.harsh_ratio_db + 3) / 15) * 100))
  const harshTone = (metrics.harsh_label && _SEVERITY_TONE[metrics.harsh_label]) || 'ok'

  return (
    <div style={{ marginTop: 4 }}>
      <ZoneLabel>{t('library.quality.metrics.label')}</ZoneLabel>

      <MetricBar
        label={t('library.quality.metrics.channels')}
        valueLabel={metrics.mono ? t('library.quality.metrics.mono') : t('library.quality.metrics.stereo')}
        note={!metrics.mono ? (metrics.stereo_width_label ?? undefined) : undefined}
        pct={widthPct} tone={widthTone}
      />
      <MetricBar
        label={t('library.quality.metrics.clipping')}
        valueLabel={`${((metrics.clip_fraction ?? 0) * 100).toFixed(2)}%`}
        pct={clipPct} tone={clipTone}
      />
      <MetricBar
        label={t('library.quality.metrics.crowdSeparation')}
        valueLabel={metrics.crowd_snr_db != null ? `${metrics.crowd_snr_db.toFixed(1)} dB` : '—'}
        note={metrics.crowd_snr_label ?? undefined}
        pct={crowdPct} tone={crowdTone}
      />

      <div style={{ fontSize: 'var(--t-micro)', fontWeight: 'var(--w-semi)', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', margin: '12px 0 8px' }}>
        {t('library.quality.metrics.tonalBalance')}
      </div>
      <MetricBar
        label={t('library.quality.metrics.bass')}
        valueLabel={metrics.bass_ratio_db != null ? `${metrics.bass_ratio_db.toFixed(1)} dB` : '—'}
        note={metrics.bass_label ?? t('library.quality.metrics.balanced')}
        pct={bassPct} tone={bassTone}
      />
      <MetricBar
        label={t('library.quality.metrics.mud')}
        valueLabel={metrics.mud_ratio_db != null ? `${metrics.mud_ratio_db.toFixed(1)} dB` : '—'}
        note={metrics.mud_label ?? t('library.quality.metrics.balanced')}
        pct={mudPct} tone={mudTone}
      />
      <MetricBar
        label={t('library.quality.metrics.harsh')}
        valueLabel={metrics.harsh_ratio_db != null ? `${metrics.harsh_ratio_db.toFixed(1)} dB` : '—'}
        note={metrics.harsh_label ?? t('library.quality.metrics.balanced')}
        pct={harshPct} tone={harshTone}
      />

      <div style={{ fontSize: 'var(--t-micro)', fontWeight: 'var(--w-semi)', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', margin: '12px 0 8px' }}>
        {t('library.quality.metrics.sourceFlags')}
      </div>
      {metrics.source_flags.length > 0 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {metrics.source_flags.map(f => (
            <FlagChip key={f} text={f} tone={f.includes('lossy') ? 'bad' : 'warn'} />
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)' }}>{t('library.quality.metrics.noFlags')}</div>
      )}
    </div>
  )
}

function QualityZone({ row, hideLabel }: { row: DetailRow; hideLabel?: boolean }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery<QualityScore | null>({
    queryKey: ['library-quality', row.lbNumber],
    queryFn: () => fetch(`${BASE}/api/quality/${row.lbNumber}`).then(r => (r.status === 204 ? null : r.json())),
    enabled: row.owned,
    staleTime: 60_000,
  })

  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.quality.label')}</ZoneLabel>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
        <Fact
          label={t('library.quality.lbRating')}
          value={row.rating && row.rating !== '—' ? row.rating : '—'}
        />
        <Fact
          label={t('library.quality.aiIndex')}
          value={isLoading ? '…' : data?.abs_grade ? data.abs_grade : '—'}
          sub={data?.abs_score != null ? `${Math.round(data.abs_score)}/100` : undefined}
        />
      </div>
      {data?.verdict_text && (
        <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', lineHeight: 1.5 }}>{data.verdict_text}</div>
      )}
      {data?.metrics && <QualityMetricsPanel metrics={data.metrics} />}
      {!isLoading && !data && (
        <div style={{
          padding: '14px 12px', borderRadius: 6, textAlign: 'center',
          border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 'var(--t-meta)',
        }}>
          {t('library.quality.notScannedNote')}
        </div>
      )}
    </div>
  )
}

// ── PicksZone — FABLE_UNIFIED_RANKING §6/§4: why this recording ranked where
// it did for its date, via the shared EvidenceList (F3). Lazily fetched per
// row (evidence_json is deliberately NOT in the bulk /api/library/performances
// payload, to keep that payload flat — only pickRank/absGrade/curated ride
// it, per F4). 204 means show_picks has no row yet (pre-recompute or no
// usable date), not an error. ─────────────────────────────────────────────
interface ShowPick {
  concert_date: string
  lb_number: number
  pick_score: number
  pick_rank: number
  evidence: EvidenceRecord[]
}

function PicksZone({ row, hideLabel }: { row: DetailRow; hideLabel?: boolean }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery<ShowPick | null>({
    queryKey: ['library-picks-for', row.lbNumber],
    queryFn: () => fetch(`${BASE}/api/picks/for/${row.lbNumber}`).then(r => (r.status === 204 ? null : r.json())),
    staleTime: 60_000,
  })

  if (isLoading) {
    return <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)' }}>{t('library.empty.loading')}</div>
  }
  if (!data) {
    return (
      <div style={{
        padding: '14px 12px', borderRadius: 6, textAlign: 'center',
        border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 'var(--t-meta)',
      }}>
        {t('library.picks.notComputedNote')}
      </div>
    )
  }
  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.picks.label')}</ZoneLabel>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
        <Fact
          label={t('library.picks.rankLabel')}
          value={data.pick_rank === 1 ? t('library.picks.recommended') : `#${data.pick_rank}`}
        />
        <Fact label={t('library.picks.scoreLabel')} value={Math.round(data.pick_score)} />
      </div>
      <EvidenceList evidence={data.evidence} />
    </div>
  )
}

// ── TaperZone — FABLE_TAPER_ATTRIBUTION §5: tier + taper + conflict flag +
// evidence for ANY attribution (confirmed/propagated/inferred), via the shared
// EvidenceList (F3). Lazily fetched per row like PicksZone, from the read-only
// GET /api/tapers/attributions/<lb>. Confirm/Reject only render in curator mode
// (TODO-160 convention: useSettingsStore's curatorMode, same gate ScreenSetup's
// publish button uses) and POST to the existing curator-gated confirm/reject
// routes, pushing the response straight into the query cache so the tab
// reflects the decision without a second round-trip. ───────────────────────
interface TaperAttribution {
  lb_number: number
  taper_normalised: string
  confidence: 'confirmed' | 'propagated' | 'inferred'
  evidence: EvidenceRecord[]
  conflict: number
  confirmed_at: string | null
  computed_at: string
}
interface TaperAttributionResponse {
  lb_number: number
  attribution: TaperAttribution | null
}

function TaperZone({ row, hideLabel }: { row: DetailRow; hideLabel?: boolean }) {
  const { t } = useTranslation()
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  const queryClient = useQueryClient()
  const queryKey = ['library-taper-for', row.lbNumber]
  const { data, isLoading } = useQuery<TaperAttributionResponse>({
    queryKey,
    queryFn: () => fetch(`${BASE}/api/tapers/attributions/${row.lbNumber}`).then(r => r.json()),
    staleTime: 60_000,
  })
  const [busy, setBusy] = useState(false)

  const decide = async (action: 'confirm' | 'reject') => {
    setBusy(true)
    try {
      const resp = await fetch(`${BASE}/api/tapers/attributions/${row.lbNumber}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (resp.ok) {
        const body: TaperAttributionResponse = await resp.json()
        queryClient.setQueryData(queryKey, body)
      }
    } finally {
      setBusy(false)
    }
  }

  if (isLoading) {
    return <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)' }}>{t('library.empty.loading')}</div>
  }
  const attribution = data?.attribution ?? null
  if (!attribution) {
    return (
      <div style={{
        padding: '14px 12px', borderRadius: 6, textAlign: 'center',
        border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 'var(--t-meta)',
      }}>
        {t('library.taper.emptyNote')}
      </div>
    )
  }
  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.taper.label')}</ZoneLabel>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
        <Pill tone={attribution.confidence === 'confirmed' ? 'ok' : 'mute'} soft>
          {t(`library.taper.tier.${attribution.confidence}`)}
        </Pill>
        {attribution.conflict === 1 && (
          <Pill tone="warn" soft>{t('library.taper.conflict')}</Pill>
        )}
      </div>
      <div style={{ marginBottom: 14 }}>
        <Fact label={t('library.taper.taperLabel')} value={attribution.taper_normalised} />
      </div>
      <EvidenceList evidence={attribution.evidence} />
      {curatorMode && (
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <Button variant="primary" size="sm" disabled={busy} onClick={() => decide('confirm')}>
            {t('library.taper.confirm')}
          </Button>
          <Button variant="danger" size="sm" disabled={busy} onClick={() => decide('reject')}>
            {t('library.taper.reject')}
          </Button>
        </div>
      )}
    </div>
  )
}

// ── OlofZone — FABLE_OLOF_FILES §5 items 1/2/7, §6 P5b: Olof Björner's "Still
// On The Road" + Yearly Chronicles corpus for this show date — setlist
// (position, encore, cover credits, per-song annotations, studio take
// numbers/statuses), NET/year concert numbering, tour name, recording info,
// notes, BobTalk, chronicle diary entries, and new-tapes circulation
// provenance — plus a setlist-vs-folder comparison against this recording's
// own tracklist via POST /api/olof/compare. olof_* tables are local-only;
// callers gate rendering entirely on useOlofStatus().events > 0 rather than
// showing an empty/broken panel on most installs. ──────────────────────────

interface OlofSong {
  position: number
  song_title: string
  credits: string | null
  is_encore: number
  take_number: number | null
  take_status: string | null
  annotations: string | null
  released_on: string | null
}

interface OlofEventRow {
  event_id: number
  event_type: string
  date_str: string
  venue: string | null
  city: string | null
  tour_name: string | null
  session_title: string | null
  concert_no_net: number | null
  concert_no_year: number | null
  recording_info: string | null
  recording_kind: string | null
  recording_mins: number | null
  notes: string | null
  bobtalk: string | null
  songs: OlofSong[]
}

interface OlofChronicleEntry { year: number; seq: number; date_str: string; date_raw: string; entry_text: string }
interface OlofNewTapeEntry { year: number; seq: number; title: string; date_str: string; body_text: string }

interface OlofDateResponse {
  date_str: string
  events: OlofEventRow[]
  chronicle: OlofChronicleEntry[]
  new_tapes: OlofNewTapeEntry[]
}

export interface OlofStatus {
  pages: number
  events: number
  songs: number
  chronicle_rows: number
  new_tapes: number
  chronicle_years: number
  max_dsn_year: number | null
}

interface OlofCompareResponse {
  date_str: string
  olof_event_id: number | null
  olof_setlist: { position: number; song_title: string }[]
  matches: { input_title: string; matched_position: number | null; matched_title: string | null }[]
  olof_missing: string[]
  match_pct: number
  recording_info: string
  recording_kind: string
  recording_mins: number | null
}

export const OLOF_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

// Fetches /api/olof/status once per app session (staleTime: Infinity, same
// convention as the db-settings-data-dir query above) — react-query dedupes
// on the shared queryKey, so every caller (tab-visibility checks + the zone
// itself) reads the same cached result instead of refetching per row.
export function useOlofStatus() {
  return useQuery<OlofStatus>({
    queryKey: ['olof-status'],
    queryFn: () => fetch(`${BASE}/api/olof/status`).then(r => r.json()),
    staleTime: Infinity,
  })
}

function OlofSongRow({ s, i, showTakes }: { s: OlofSong; i: number; showTakes: boolean }) {
  const { t } = useTranslation()
  const note = [
    s.credits ? t('library.olof.coverCredit', { credits: s.credits }) : null,
    s.annotations || null,
    s.released_on ? t('library.olof.releasedOn', { where: s.released_on }) : null,
  ].filter(Boolean).join(' · ')
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 2, padding: '5px 10px',
      fontSize: 'var(--t-meta)', lineHeight: 1.4,
      background: i % 2 === 1 ? 'color-mix(in srgb, var(--lbb-surface2) 40%, transparent)' : 'transparent',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ width: 18, textAlign: 'right', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg3)', flexShrink: 0 }}>
          {s.position}
        </span>
        <span style={{ flex: 1, color: 'var(--lbb-fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {s.song_title}
        </span>
        {!!s.is_encore && (
          <Pill tone="info" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>{t('library.olof.encore')}</Pill>
        )}
        {showTakes && s.take_number != null && (
          <Pill tone="mute" soft style={{ fontSize: 'var(--t-micro)', padding: '0 5px' }}>
            {t('library.olof.take', { n: s.take_number })}{s.take_status ? ` · ${s.take_status}` : ''}
          </Pill>
        )}
      </div>
      {note && (
        <div style={{ paddingLeft: 26, fontSize: 'var(--t-micro)', color: 'var(--lbb-fg3)' }}>{note}</div>
      )}
    </div>
  )
}

function OlofEventCard({ ev }: { ev: OlofEventRow }) {
  const { t } = useTranslation()
  const isStudio = ev.event_type !== 'concert'
  const recLine = [
    ev.recording_kind || null,
    ev.recording_info || null,
    ev.recording_mins != null ? t('library.olof.recordingMinutes', { count: ev.recording_mins }) : null,
  ].filter(Boolean).join(' · ')

  return (
    <div style={{ marginBottom: 18 }}>
      {(ev.concert_no_net != null || ev.concert_no_year != null) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
          {ev.concert_no_net != null && <Fact label={t('library.olof.concertNoNet')} value={ev.concert_no_net} />}
          {ev.concert_no_year != null && <Fact label={t('library.olof.concertNoYear')} value={ev.concert_no_year} />}
        </div>
      )}
      {(ev.tour_name || ev.session_title) && (
        <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', marginBottom: 8 }}>
          {ev.tour_name || ev.session_title}
        </div>
      )}

      {ev.songs.length > 0 && (
        <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 6, overflow: 'hidden', marginBottom: 10 }}>
          {ev.songs.map((s, i) => (
            <OlofSongRow key={`${ev.event_id}-${s.position}`} s={s} i={i} showTakes={isStudio} />
          ))}
        </div>
      )}

      {recLine && (
        <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', marginBottom: 8 }}>{recLine}</div>
      )}

      {ev.notes && (
        <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', lineHeight: 1.5, marginBottom: 8 }}>{ev.notes}</div>
      )}

      {ev.bobtalk && (
        <div style={{
          borderLeft: '2px solid var(--lbb-accent-mid)', paddingLeft: 10, margin: '8px 0',
          fontSize: 'var(--t-meta)', fontStyle: 'italic', color: 'var(--lbb-fg2)', lineHeight: 1.5,
        }}>
          “{ev.bobtalk}”
        </div>
      )}
    </div>
  )
}

function OlofChronicleList({ entries }: { entries: OlofChronicleEntry[] }) {
  const { t } = useTranslation()
  if (entries.length === 0) return null
  return (
    <div style={{ marginBottom: 14 }}>
      <ZoneLabel>{t('library.olof.chronicleLabel')}</ZoneLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {entries.map(e => (
          <div key={`${e.year}-${e.seq}`} style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', lineHeight: 1.5 }}>
            {e.entry_text}
          </div>
        ))}
      </div>
    </div>
  )
}

function OlofNewTapesList({ entries }: { entries: OlofNewTapeEntry[] }) {
  const { t } = useTranslation()
  if (entries.length === 0) return null
  return (
    <div style={{ marginBottom: 14 }}>
      <ZoneLabel>{t('library.olof.newTapesLabel')}</ZoneLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {entries.map(e => (
          <div key={`${e.year}-${e.seq}`} style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)' }}>
            <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', marginRight: 6 }}>{e.year}</span>
            {t('library.olof.circulatedAs', { title: e.title })}
          </div>
        ))}
      </div>
    </div>
  )
}

// Setlist-vs-folder comparison (spec §5 item 2) — silently renders nothing
// while loading, on fetch failure, or when Olof has no event for this date
// (olof_event_id null), rather than showing a broken/empty comparison block.
function OlofCompareNote({ date, lbNumber }: { date: string; lbNumber: number }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery<OlofCompareResponse>({
    queryKey: ['olof-compare', date, lbNumber],
    queryFn: () => fetch(`${BASE}/api/olof/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date_str: date, lb_number: lbNumber }),
    }).then(r => r.json()),
    staleTime: 60_000,
  })

  if (isLoading || !data || data.olof_event_id == null) return null

  return (
    <div style={{ marginBottom: 14, padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 'var(--t-meta)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg)' }}>
          {t('library.olof.matchPct', { pct: data.match_pct })}
        </span>
        {data.recording_mins != null && (
          <span style={{ fontSize: 'var(--t-micro)', color: 'var(--lbb-fg3)' }}>
            {t('library.olof.expectedMinutes', { count: data.recording_mins })}
          </span>
        )}
      </div>
      {data.olof_missing.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 'var(--t-meta)', color: 'var(--lbb-warn-fg)' }}>
          {t('library.olof.missingFromCopy', { titles: data.olof_missing.join(', ') })}
        </div>
      )}
    </div>
  )
}

function OlofZone({ date, lbNumber, hideLabel }: { date: string; lbNumber?: number; hideLabel?: boolean }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery<OlofDateResponse>({
    queryKey: ['olof-date', date],
    queryFn: () => fetch(`${BASE}/api/olof/date/${encodeURIComponent(date)}`).then(r => r.json()),
    staleTime: 300_000,
    enabled: !!date,
  })

  if (isLoading) {
    return <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)' }}>{t('library.empty.loading')}</div>
  }
  const hasContent = !!data && (data.events.length > 0 || data.chronicle.length > 0 || data.new_tapes.length > 0)
  if (!hasContent) {
    return (
      <div style={{
        padding: '14px 12px', borderRadius: 6, textAlign: 'center',
        border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 'var(--t-meta)',
      }}>
        {t('library.olof.emptyNote')}
      </div>
    )
  }

  return (
    <div style={{ flexShrink: 0 }}>
      {!hideLabel && <ZoneLabel>{t('library.olof.label')}</ZoneLabel>}
      {lbNumber != null && <OlofCompareNote date={date} lbNumber={lbNumber} />}
      {data!.events.map(ev => <OlofEventCard key={ev.event_id} ev={ev} />)}
      <OlofChronicleList entries={data!.chronicle} />
      <OlofNewTapesList entries={data!.new_tapes} />
    </div>
  )
}

// ── Tab strip (spec §8) — pinned below the identity block; routes the pane
// body. Idle tabs are --t-body/500 fg3; the active tab is accent-mid with a
// 2px inset underline. Count pills sit inline. ──────────────────────────────
export interface PanelTab { id: string; label: string; count?: number }

function TabStrip({ tabs, active, onChange }: { tabs: PanelTab[]; active: string; onChange: (id: string) => void }) {
  return (
    <div style={{
      display: 'flex', gap: 2, padding: '6px 10px 0',
      borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      overflowX: 'auto', overflowY: 'hidden',
    }}>
      {tabs.map(tab => {
        const on = tab.id === active
        return (
          <button
            key={tab.id} type="button" onClick={() => onChange(tab.id)}
            style={{
              position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '7px 11px 9px', border: 'none', background: 'none', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: 'var(--t-body)',
              fontWeight: on ? 'var(--w-semi)' : 'var(--w-med)',
              color: on ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => { if (!on) e.currentTarget.style.color = 'var(--lbb-fg2)' }}
            onMouseLeave={e => { if (!on) e.currentTarget.style.color = 'var(--lbb-fg3)' }}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span style={{
                minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 'var(--t-micro)', fontWeight: 'var(--w-bold)', lineHeight: 1,
                background: on ? 'var(--lbb-accent-mid)' : 'var(--lbb-surface3)',
                color: on ? 'var(--lbb-accent-onMid)' : 'var(--lbb-fg3)',
              }}>{tab.count}</span>
            )}
            {on && (
              <span style={{
                position: 'absolute', left: 8, right: 8, bottom: -1, height: 2,
                background: 'var(--lbb-accent-mid)', borderRadius: 1,
              }} />
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Recording detail panel ──────────────────────────────────────────────────

export function RecordingDetailPanel({ row, history, attachCount, actionHandlers, openMenu, onClose, open = true, onToggle, width = 380, onResizeStart }: {
  row: DetailRow | null
  history: RowHistory | undefined
  attachCount: number | undefined
  actionHandlers: ActionHandlers
  openMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  onClose: () => void
  open?: boolean
  onToggle?: () => void
  width?: number
  onResizeStart?: (e: React.MouseEvent) => void
}) {
  const { t } = useTranslation()
  const toggle = onToggle ?? onClose
  // Tab state + scroll-reset on tab/row change (spec §8/§11). Hooks run before
  // any early return to satisfy the rules of hooks.
  const [tab, setTab] = useState('overview')
  const paneRef = useRef<HTMLDivElement>(null)
  useEffect(() => { if (paneRef.current) paneRef.current.scrollTop = 0 }, [tab, row?.lb])
  // FABLE_OLOF_FILES §6 P5b: shared once-per-session status fetch — decides
  // whether the Olof tab appears at all (most installs have olof_events == 0).
  const { data: olofStatus } = useOlofStatus()

  if (!open) return <CollapsedStub onToggle={toggle} />

  if (!row) {
    return (
      <aside style={panelAsideStyle(width)} data-panel="recording-detail">
        {onResizeStart && <ResizeHandle onResizeStart={onResizeStart} />}
        <PanelHeader label={t('library.panel.details')} onToggle={toggle} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--t-body)' }}>
          {t('library.panel.selectRow')}
        </div>
      </aside>
    )
  }

  const actions = buildRecordingActions(row, [], actionHandlers, t)
  // Overview is always present; Assets and Seed & Share only when the recording
  // is owned (nothing local to act on otherwise — spec §10 unowned note).
  // Picks is always present (unlike Quality, which needs an owned scan) —
  // show_picks scores every dated candidate regardless of ownership, so an
  // unowned recording's rank/evidence can still help decide whether to get it.
  // FABLE_OLOF_FILES §6 P5b: Olof tab only when the local corpus has events
  // (status gate) and this row's date is a usable ISO date (Olof keys on
  // date_str, same as the bobdylan setlist fetch).
  const olofDate = OLOF_DATE_RE.test(row.date) ? row.date : null
  const showOlof = (olofStatus?.events ?? 0) > 0 && !!olofDate

  const tabs: PanelTab[] = [
    { id: 'overview', label: t('library.panel.tabOverview') },
    { id: 'picks', label: t('library.panel.tabPicks') },
    { id: 'taper', label: t('library.panel.tabTaper') },
  ]
  if (showOlof) tabs.push({ id: 'olof', label: t('library.panel.tabOlof') })
  if (row.owned) {
    tabs.push({ id: 'assets', label: t('library.panel.tabAssets') })
    tabs.push({ id: 'share', label: t('library.panel.tabShare') })
    tabs.push({ id: 'quality', label: t('library.panel.tabQuality') })
  }
  const activeTab = tabs.some(x => x.id === tab) ? tab : 'overview'

  return (
    <aside style={panelAsideStyle(width)} data-panel="recording-detail">
      {onResizeStart && <ResizeHandle onResizeStart={onResizeStart} />}
      <PanelHeader
        label={t('library.panel.details')}
        lbPageLabel={t('library.panel.openLbPage')}
        onOpenLbPage={() => window.open(lbDetailUrl(row.lbNumber), '_blank')}
        onToggle={toggle}
      />

      {/* Identity block — pinned (does not scroll) */}
      <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {row.owned
            ? <Pill tone="ok" soft dot>{t('library.panel.owned')}</Pill>
            : <Pill tone="warn" soft dot>{t('library.panel.notOwned')}</Pill>}
          <Pill tone={statusTone(row.status)} soft>{row.status}</Pill>
          {row.wish && <Pill tone="warn" soft>{t('library.panel.wishlist')}</Pill>}
          {row.dup && <Pill tone="mute" soft>{t('library.panel.dup')}</Pill>}
          {/* Entry-level (A15/D4): this LB has alternate filesets documented —
              distinct from a copy-level "your copy is xref-N" statement, which
              this screen never makes. */}
          {row.xref && <Pill tone="mute" soft>{t('library.panel.altFilesets')}</Pill>}
          {row.pickRank === 1 && (
            <Pill tone="ok" soft title={t('library.picks.recommendedTitle')}>★ {t('library.picks.recommended')}</Pill>
          )}
          {row.owned && row.absGrade && <Pill tone="info" soft>{t('library.picks.gradeBadge', { grade: row.absGrade })}</Pill>}
          {row.curated?.map(name => (
            <Pill key={name} tone="info" soft>{t('library.picks.curatedBadge', { curator: name })}</Pill>
          ))}
        </div>
        <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-display)', fontWeight: 'var(--w-bold)', color: 'var(--lbb-accent-mid)', marginBottom: 2 }}>
          {row.lb}
        </div>
        <div style={{ fontSize: 'var(--t-body)', color: 'var(--lbb-fg2)' }}>
          {row.date} · {row.loc}
        </div>
      </div>

      <TabStrip tabs={tabs} active={activeTab} onChange={setTab} />

      <div ref={paneRef} style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {activeTab === 'overview' && (
          <>
            {row.desc && row.desc !== '—' && (
              <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', lineHeight: 1.5 }}>{row.desc}</div>
            )}
            {row.src && (
              <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', marginTop: 3 }}>
                {SRC_ABBR[row.src] ?? row.src}
              </div>
            )}
            <ActionBarZone actions={actions} onMore={e => openMenu(e, row.lb, actions)} />

            {/* Owned: file & location card */}
            {row.owned && (
              <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: '6px 10px', fontSize: 'var(--t-meta)' }}>
                  {row.folder && (
                    <>
                      <span style={{ color: 'var(--lbb-fg3)' }}>{t('library.panel.folder')}</span>
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.folder}</span>
                    </>
                  )}
                  {row.conf && (
                    <>
                      <span style={{ color: 'var(--lbb-fg3)' }}>{t('library.panel.confirmed')}</span>
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.conf}</span>
                    </>
                  )}
                  {row.rating && row.rating !== '—' && (
                    <>
                      <span style={{ color: 'var(--lbb-fg3)' }}>{t('library.panel.rating')}</span>
                      <span><Pill tone={ratingTone(row.rating)} soft>{row.rating}</Pill></span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Unowned: catalog note */}
            {!row.owned && (
              <div style={{
                marginTop: 14, padding: '10px 12px', borderRadius: 6,
                background: 'color-mix(in srgb, var(--lbb-info-bg) 40%, transparent)',
                border: '1px solid color-mix(in srgb, var(--lbb-info-bar) 30%, transparent)',
                fontSize: 'var(--t-meta)', color: 'var(--lbb-info-fg)',
              }}>
                {t('library.panel.catalogNote')}
              </div>
            )}

            {/* D5: checksums grouped by fileset — catalog data, shown for
                owned and unowned rows alike. */}
            <ChecksumsZone lbNumber={row.lbNumber} />
          </>
        )}

        {activeTab === 'picks' && (
          <PicksZone row={row} hideLabel />
        )}

        {activeTab === 'taper' && (
          <TaperZone row={row} hideLabel />
        )}

        {activeTab === 'olof' && olofDate && (
          <OlofZone date={olofDate} lbNumber={row.lbNumber} hideLabel />
        )}

        {activeTab === 'assets' && row.owned && (
          <AssetStripZone
            row={row} attachCount={attachCount} hideLabel
            onAttach={() => actionHandlers.onAttach(row)}
            onSpectro={() => actionHandlers.onSpectro(row)}
            onMap={() => actionHandlers.onMap()}
          />
        )}

        {activeTab === 'share' && row.owned && (
          <ShareSeedZone
            history={history} hideLabel
            onQbt={() => actionHandlers.onQbt([row])}
            onTorrent={() => actionHandlers.onTorrent([row])}
            onForum={() => actionHandlers.onForum([row])}
          />
        )}

        {activeTab === 'quality' && row.owned && (
          <QualityZone row={row} hideLabel />
        )}
      </div>
    </aside>
  )
}

// ── Performance (show) detail panel ─────────────────────────────────────────

export function PerformanceDetailPanel({ perf, recordings, families, canonical, history, attachCount, actionHandlers, openMenu, onClose, open = true, onToggle, width = 400, onResizeStart }: {
  perf: PerfMeta | null
  recordings: DetailRow[]
  families: PerfFamily[]
  canonical: DetailRow | null
  history: RowHistory | undefined
  attachCount: number | undefined
  actionHandlers: ActionHandlers
  openMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  onClose: () => void
  open?: boolean
  onToggle?: () => void
  width?: number
  onResizeStart?: (e: React.MouseEvent) => void
}) {
  const { t } = useTranslation()
  const toggle = onToggle ?? onClose
  // Tab state + scroll-reset on tab/performance change (spec §8/§11).
  const [tab, setTab] = useState('overview')
  const paneRef = useRef<HTMLDivElement>(null)
  useEffect(() => { if (paneRef.current) paneRef.current.scrollTop = 0 }, [tab, perf?.id])
  // FABLE_OLOF_FILES §6 P5b: shared once-per-session status fetch — decides
  // whether the Olof tab appears at all (most installs have olof_events == 0).
  const { data: olofStatus } = useOlofStatus()

  if (!open) return <CollapsedStub onToggle={toggle} />

  if (!perf) {
    return (
      <aside style={panelAsideStyle(width)} data-panel="performance-detail">
        {onResizeStart && <ResizeHandle onResizeStart={onResizeStart} />}
        <PanelHeader label={t('library.panel.performance')} lbPageLabel={t('library.panel.lbPage')} onToggle={toggle} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--t-body)' }}>
          {t('library.panel.selectPerformance')}
        </div>
      </aside>
    )
  }

  const actions = buildPerformanceActions(recordings, canonical, actionHandlers, t)
  const owned = recordings.filter(r => r.owned)
  const ownedFams = families.filter(f => f.owned)
  const coverage = recordings.length === 0 ? 'Undocumented'
    : owned.length === 0 ? 'Gap'
    : owned.length < recordings.length && canonical && !canonical.owned ? 'Upgrade'
    : 'Covered'
  const bestOwnedRating = ownedFams.length > 0
    ? ownedFams.map(f => f.bestRating).sort((a, b) => {
        const RANK: Record<string, number> = { 'A+': 13, 'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8, 'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3, 'D-': 2, 'F': 1 }
        return (RANK[b] ?? 0) - (RANK[a] ?? 0)
      })[0]
    : null
  const dupeCount = recordings.filter(r => r.dup).length

  // FABLE_OLOF_FILES §6 P5b: Olof tab only when the local corpus has events
  // (status gate) and the performance has a usable ISO date — reuses
  // perf.setlist, the same bobdylan_shows-backed ISO date the Setlist tab
  // fetches against, rather than perf.date (which can fall back to raw,
  // non-ISO scraped text when there's no bobdylan_shows match).
  const olofDate = perf.setlist && OLOF_DATE_RE.test(perf.setlist) ? perf.setlist : null
  const showOlof = (olofStatus?.events ?? 0) > 0 && !!olofDate

  // Overview always; Recordings/Setlist/Seed & Share only when they have content
  // (spec §9). Each focus item is a peer tab, not a footer in a long scroll.
  const tabs: PanelTab[] = [{ id: 'overview', label: t('library.panel.tabOverview') }]
  if (families.length > 0) tabs.push({ id: 'recordings', label: t('library.panel.tabRecordings'), count: families.length })
  if (perf.setlist) tabs.push({ id: 'setlist', label: t('library.panel.tabSetlist') })
  if (showOlof) tabs.push({ id: 'olof', label: t('library.panel.tabOlof') })
  if (owned.length > 0 && canonical) tabs.push({ id: 'share', label: t('library.panel.tabShare') })
  const activeTab = tabs.some(x => x.id === tab) ? tab : 'overview'

  return (
    <aside style={panelAsideStyle(width)} data-panel="performance-detail">
      {onResizeStart && <ResizeHandle onResizeStart={onResizeStart} />}
      <PanelHeader
        label={t('library.panel.performance')}
        onOpenLbPage={() => {}}
        lbPageLabel={t('library.panel.lbPage')}
        onToggle={toggle}
      />

      {/* Identity block — pinned (does not scroll) */}
      <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          {perf.dow && (
            <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {perf.dow}
            </span>
          )}
          <CoverageChip coverage={coverage} ownedCount={owned.length} total={recordings.length} />
        </div>
        <div style={{ fontSize: 'var(--t-display)', fontWeight: 'var(--w-bold)', color: 'var(--lbb-fg)', letterSpacing: -0.02, lineHeight: 1.05 }}>
          {perf.disp}
          {perf.confirmed === false && (
            <Pill tone="mute" soft style={{ marginLeft: 8, fontSize: 'var(--t-micro)', verticalAlign: 'middle' }}>
              {t('library.panel.unconfirmed')}
            </Pill>
          )}
        </div>
        {perf.venue && (
          <div style={{ fontSize: 'var(--t-title)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg)', marginTop: 4 }}>{perf.venue}</div>
        )}
        {perf.city && (
          <div style={{ fontSize: 'var(--t-body)', color: 'var(--lbb-fg2)' }}>{perf.city}</div>
        )}
        {perf.tour && (
          <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', marginTop: 6 }}>{perf.tour}</div>
        )}
        {perf.title && (
          <div style={{ fontSize: 'var(--t-body)', fontStyle: 'italic', color: 'var(--lbb-fg2)', marginTop: 6 }}>
            {t('library.panel.releasedAs', { title: perf.title })}
          </div>
        )}
      </div>

      <TabStrip tabs={tabs} active={activeTab} onChange={setTab} />

      <div ref={paneRef} style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {activeTab === 'overview' && (
          <>
            {/* Action bar */}
            <ActionBarZone actions={actions} onMore={e => openMenu(e, perf.disp, actions)} />

            {/* Coverage summary card */}
            {recordings.length > 0 && (
              <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 8, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 'var(--t-strong)', fontWeight: 'var(--w-semi)', color: 'var(--lbb-fg)' }}>
                    {owned.length === 0
                      ? t('library.panel.noRecording')
                      : t('library.panel.youHold', { owned: ownedFams.length, count: families.length })}
                  </span>
                  <div style={{ flex: 1 }} />
                  {bestOwnedRating && (
                    <span style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>
                      {t('library.panel.bestOwned')} <strong style={{ color: 'var(--lbb-fg2)' }}>{bestOwnedRating}</strong>
                    </span>
                  )}
                </div>
                {families.length > 0
                  ? <FamilyMeter families={families} />
                  : (
                    <div style={{ display: 'flex', gap: 3 }}>
                      {recordings.map((r, i) => (
                        <span key={i} style={{ flex: 1, height: 6, borderRadius: 3, background: r.owned ? 'var(--lbb-ok-bar)' : 'var(--lbb-surface2)', border: r.owned ? 'none' : '1px solid var(--lbb-border2)' }} />
                      ))}
                    </div>
                  )}
                {dupeCount > 0 && (
                  <div style={{ marginTop: 8, fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Icon name="copy" size={12} />
                    {t('library.panel.foldedNote', {
                      uploads: recordings.length,
                      families: t('library.panel.familyCount', { count: families.length }),
                      dupes: t('library.panel.dupeCount', { count: dupeCount }),
                    })}
                  </div>
                )}
                {coverage === 'Upgrade' && (
                  <div style={{ marginTop: 8, fontSize: 'var(--t-meta)', color: 'var(--lbb-warn-fg)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Icon name="upload" size={12} />
                    {t('library.panel.upgradeNote')}
                  </div>
                )}
              </div>
            )}

            {/* Fact cards */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 14 }}>
              <Fact
                label={t('library.panel.factFamilies')}
                value={families.length > 0 ? families.length : recordings.length}
                sub={families.length > 0 ? t('library.panel.ofRec', { count: recordings.length }) : ''}
              />
              <Fact label={t('library.panel.factSetlist')} value={perf.tracks != null ? perf.tracks : '—'} sub={perf.tracks != null ? t('library.panel.tracksUnit') : ''} />
              <Fact label={t('library.panel.factLength')} value="—" />
            </div>

            {/* Assets chips — part of Overview (spec §9), scoped to best owned source */}
            {canonical && (
              <AssetStripZone
                row={canonical} attachCount={attachCount}
                onAttach={() => actionHandlers.onAttach(canonical)}
                onSpectro={() => actionHandlers.onSpectro(canonical)}
                onMap={() => actionHandlers.onMap()}
              />
            )}
          </>
        )}

        {/* Recordings tab — TapeMatch family cards */}
        {activeTab === 'recordings' && families.length > 0 && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 'var(--t-label)', fontWeight: 'var(--w-bold)', letterSpacing: 'var(--track-eyebrow)', textTransform: 'uppercase', color: 'var(--lbb-fg3)' }}>
                {t('library.panel.recordingFamilies', { count: families.length })}
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 'var(--t-micro)', color: 'var(--lbb-fg3)' }}>
                <Icon name="tapematch" size={11} style={{ color: 'var(--lbb-info-fg)' }} /> {t('library.panel.groupedByTapeMatch')}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {families.map(f => <FamilyCard key={f.id} fam={f} />)}
            </div>
          </div>
        )}

        {/* Setlist tab */}
        {activeTab === 'setlist' && perf.setlist && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 'var(--t-label)', fontWeight: 'var(--w-bold)', letterSpacing: 'var(--track-eyebrow)', textTransform: 'uppercase', color: 'var(--lbb-fg3)' }}>
                {t('library.setlist.title')}
              </span>
              {perf.tracks != null && (
                <span style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
                  {t('library.setlist.tracksCount', { count: perf.tracks })}
                </span>
              )}
            </div>
            <Setlist date={perf.setlist} />
          </div>
        )}

        {/* Olof tab — Still On The Road / Yearly Chronicles for this date */}
        {activeTab === 'olof' && olofDate && (
          <OlofZone date={olofDate} lbNumber={canonical?.lbNumber} hideLabel />
        )}

        {/* Seed & Share tab — scoped to the best owned source */}
        {activeTab === 'share' && owned.length > 0 && canonical && (
          <ShareSeedZone
            history={history} hideLabel
            note={t('library.share.note', { lb: canonical.lb })}
            onQbt={() => actionHandlers.onQbt(owned)}
            onTorrent={() => actionHandlers.onTorrent([canonical])}
            onForum={() => actionHandlers.onForum([canonical])}
          />
        )}
      </div>
    </aside>
  )
}
