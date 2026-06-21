// TODO-150 step 8: detail-panel zones (instructions/design_handoff_unified_library/
// 02-action-system-parity.md "Redesigned detail panel — intent zones"). Replaces the
// old flat button-soup pattern with: header (title/badges) -> ActionBar (1 primary +
// Reveal + grouped "More" overflow, same registry as the right-click menu from step 7)
// -> ShareSeed (qBittorrent/torrent/forum status + a single date-sorted activity log,
// merged client-side from the already-loaded /api/collection/prefetch torrents/forum_posts
// arrays — no new backend endpoint) -> AssetStrip (attachments/spectrograms/map as
// state-bearing chips) -> an optional Setlist line for the performance lens.

import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Pill, Button, IconButton } from '../primitives'
import type { ActionRow, ActionHandlers, LibAction } from './actions'
import { buildRecordingActions, buildPerformanceActions } from './actions'
import { Icon } from '../Icon'

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
  }
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
        flex: 1, fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700,
        letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--lbb-fg3)',
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
      fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em',
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
        fontFamily: 'var(--lbb-mono)', fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
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
      fontFamily: 'var(--lbb-mono)', fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
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
      fontSize: 11, fontWeight: 650, fontVariantNumeric: 'tabular-nums',
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
      fontSize: 10, fontWeight: 700, letterSpacing: 0.02, whiteSpace: 'nowrap',
    }}>
      <Icon name={m.icon} size={10.5} />
      {m.code}{pct && <span style={{ opacity: 0.85, fontWeight: 600 }}> · {pct}</span>}
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
      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--lbb-fg)', fontVariantNumeric: 'tabular-nums', letterSpacing: -0.01 }}>
        {value}{sub && <span style={{ fontSize: 10.5, fontWeight: 500, color: 'var(--lbb-fg3)', marginLeft: 3 }}>{sub}</span>}
      </div>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginTop: 2 }}>{label}</div>
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
      <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 11, flexShrink: 0 }}>
        {isCanonical ? '●' : '└'}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11.5, fontWeight: 600, color: r.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)' }}>
            {r.lb}
          </span>
          {tag && <Pill tone={tag.tone} soft style={{ fontSize: 9, padding: '0 5px' }}>{tag.label}</Pill>}
          <div style={{ flex: 1 }} />
          {r.rating !== '—' && <Pill tone={ratingTone(r.rating)} soft style={{ fontSize: 9, padding: '0 5px' }}>{r.rating}</Pill>}
          {r.owned
            ? <Pill tone="ok" soft dot style={{ fontSize: 9, padding: '0 5px' }}>{t('library.family.owned')}</Pill>
            : r.wish ? <Pill tone="warn" soft style={{ fontSize: 9, padding: '0 5px' }}>{t('library.family.wishlist')}</Pill>
            : <Pill tone="mute" soft style={{ fontSize: 9, padding: '0 5px' }}>{t('library.family.notOwned')}</Pill>}
        </div>
        {r.src && (
          <div style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', marginTop: 3 }}>{r.src}</div>
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
        <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--lbb-fg)' }}>{fam.tmLabel ?? fam.src ?? t('library.family.recording')}</span>
        <MatchChip by={fam.by} conf={fam.conf} />
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
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
    <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', padding: '10px 0' }}>{t('library.setlist.loading')}</div>
  )
  if (!data || !data.tracks?.length) return (
    <div style={{
      padding: '14px 12px', borderRadius: 6, textAlign: 'center',
      border: '1px dashed var(--lbb-border2)', color: 'var(--lbb-fg3)', fontSize: 11.5,
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
            fontSize: 11.5, lineHeight: 1.45,
            background: ti % 2 === 1 ? 'color-mix(in srgb, var(--lbb-surface2) 40%, transparent)' : 'transparent',
          }}>
            <span style={{ width: 18, textAlign: 'right', fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: 'var(--lbb-fg3)', flexShrink: 0 }}>
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

function ShareSeedZone({ history, busy, onQbt, onTorrent, onForum, note }: {
  history: RowHistory | undefined
  busy?: boolean
  onQbt: () => void
  onTorrent: () => void
  onForum: () => void
  note?: string
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
      <ZoneLabel>{t('library.share.label')}</ZoneLabel>
      {note && <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginBottom: 6 }}>{note}</div>}
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

function AssetStripZone({ row, attachCount, onAttach, onSpectro, onMap }: {
  row: DetailRow
  attachCount: number | undefined
  onAttach: () => void
  onSpectro: () => void
  onMap: () => void
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

  return (
    <div style={{ flexShrink: 0 }}>
      <ZoneLabel>{t('library.assets.label')}</ZoneLabel>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button type="button" onClick={onAttach} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
          <Pill tone={attachCount ? 'ok' : 'mute'} soft dot={!!attachCount}>
            {attachCount ? t('library.assets.attachments', { count: attachCount }) : t('library.assets.noAttachments')}
          </Pill>
        </button>
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

// ── Recording detail panel ──────────────────────────────────────────────────

export function RecordingDetailPanel({ row, history, attachCount, actionHandlers, openMenu, onClose, open = true, onToggle, width = 380 }: {
  row: DetailRow | null
  history: RowHistory | undefined
  attachCount: number | undefined
  actionHandlers: ActionHandlers
  openMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  onClose: () => void
  open?: boolean
  onToggle?: () => void
  width?: number
}) {
  const { t } = useTranslation()
  const toggle = onToggle ?? onClose

  if (!open) return <CollapsedStub onToggle={toggle} />

  if (!row) {
    return (
      <aside style={panelAsideStyle(width)} data-panel="recording-detail">
        <PanelHeader label={t('library.panel.details')} onToggle={toggle} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lbb-fg3)', fontSize: 12 }}>
          {t('library.panel.selectRow')}
        </div>
      </aside>
    )
  }

  const actions = buildRecordingActions(row, [], actionHandlers, t)
  return (
    <aside style={panelAsideStyle(width)} data-panel="recording-detail">
      <PanelHeader
        label={t('library.panel.details')}
        lbPageLabel={t('library.panel.openLbPage')}
        onOpenLbPage={() => window.open(
          `http://www.losslessbob.wonderingwhattochoose.com/detail/${row.lb}.html`, '_blank',
        )}
        onToggle={toggle}
      />

      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {/* Status pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {row.owned
            ? <Pill tone="ok" soft dot>{t('library.panel.owned')}</Pill>
            : <Pill tone="warn" soft dot>{t('library.panel.notOwned')}</Pill>}
          <Pill tone={statusTone(row.status)} soft>{row.status}</Pill>
          {row.wish && <Pill tone="warn" soft>{t('library.panel.wishlist')}</Pill>}
          {row.dup && <Pill tone="mute" soft>{t('library.panel.dup')}</Pill>}
          {row.xref && <Pill tone="mute" soft>{t('library.panel.xref')}</Pill>}
        </div>

        {/* Identity */}
        <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 16, fontWeight: 700, color: 'var(--lbb-accent-mid)', marginBottom: 2 }}>
          {row.lb}
        </div>
        <div style={{ fontSize: 12, color: 'var(--lbb-fg2)' }}>
          {row.date} · {row.loc}
        </div>
        {row.desc && row.desc !== '—' && (
          <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 6, lineHeight: 1.5 }}>{row.desc}</div>
        )}
        {row.src && (
          <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 3 }}>
            {SRC_ABBR[row.src] ?? row.src}
          </div>
        )}

        {/* Action bar */}
        <ActionBarZone actions={actions} onMore={e => openMenu(e, row.lb, actions)} />

        {/* Owned: file metadata card */}
        {row.owned && (
          <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 6, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '86px 1fr', gap: '4px 10px', fontSize: 'var(--lbb-fs-11-5)' }}>
              {row.folder && (
                <>
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('library.panel.folder')}</span>
                  <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.folder}</span>
                </>
              )}
              {row.conf && (
                <>
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('library.panel.confirmed')}</span>
                  <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.conf}</span>
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
            fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-info-fg)',
          }}>
            {t('library.panel.catalogNote')}
          </div>
        )}

        {/* Assets (owned) */}
        {row.owned && (
          <AssetStripZone
            row={row} attachCount={attachCount}
            onAttach={() => actionHandlers.onAttach(row)}
            onSpectro={() => actionHandlers.onSpectro(row)}
            onMap={() => actionHandlers.onMap()}
          />
        )}

        {/* Share & seed (owned) */}
        {row.owned && (
          <ShareSeedZone
            history={history}
            onQbt={() => actionHandlers.onQbt([row])}
            onTorrent={() => actionHandlers.onTorrent([row])}
            onForum={() => actionHandlers.onForum([row])}
          />
        )}
      </div>
    </aside>
  )
}

// ── Performance (show) detail panel ─────────────────────────────────────────

export function PerformanceDetailPanel({ perf, recordings, families, canonical, history, attachCount, actionHandlers, openMenu, onClose, open = true, onToggle, width = 400 }: {
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
}) {
  const { t } = useTranslation()
  const toggle = onToggle ?? onClose

  if (!open) return <CollapsedStub onToggle={toggle} />

  const actions = perf ? buildPerformanceActions(recordings, canonical, actionHandlers, t) : []
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

  return (
    <aside style={panelAsideStyle(width)} data-panel="performance-detail">
      <PanelHeader
        label={t('library.panel.performance')}
        onOpenLbPage={perf ? () => {} : undefined}
        lbPageLabel={t('library.panel.lbPage')}
        onToggle={toggle}
      />

      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {!perf ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--lbb-fg3)', fontSize: 12 }}>
            {t('library.panel.selectPerformance')}
          </div>
        ) : (
          <>
            {/* DOW + Coverage chip */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              {perf.dow && (
                <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  {perf.dow}
                </span>
              )}
              <CoverageChip coverage={coverage} ownedCount={owned.length} total={recordings.length} />
            </div>

            {/* Large date */}
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--lbb-fg)', letterSpacing: -0.02, lineHeight: 1.05 }}>
              {perf.disp}
              {perf.confirmed === false && (
                <Pill tone="mute" soft style={{ marginLeft: 8, fontSize: 'var(--lbb-fs-9-5)', verticalAlign: 'middle' }}>
                  {t('library.panel.unconfirmed')}
                </Pill>
              )}
            </div>

            {/* Venue */}
            {perf.venue && (
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--lbb-fg)', marginTop: 4 }}>{perf.venue}</div>
            )}

            {/* City */}
            {perf.city && (
              <div style={{ fontSize: 12.5, color: 'var(--lbb-fg2)' }}>{perf.city}</div>
            )}

            {/* Tour */}
            {perf.tour && (
              <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 6 }}>{perf.tour}</div>
            )}

            {/* Title */}
            {perf.title && (
              <div style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--lbb-fg2)', marginTop: 6 }}>
                {t('library.panel.releasedAs', { title: perf.title })}
              </div>
            )}

            {/* Action bar */}
            <ActionBarZone actions={actions} onMore={e => openMenu(e, perf.disp, actions)} />

            {/* Coverage summary card */}
            {recordings.length > 0 && (
              <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 8, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--lbb-fg)' }}>
                    {owned.length === 0
                      ? t('library.panel.noRecording')
                      : t('library.panel.youHold', { owned: ownedFams.length, count: families.length })}
                  </span>
                  <div style={{ flex: 1 }} />
                  {bestOwnedRating && (
                    <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>
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
                  <div style={{ marginTop: 8, fontSize: 11, color: 'var(--lbb-fg3)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Icon name="copy" size={12} />
                    {t('library.panel.foldedNote', {
                      uploads: recordings.length,
                      families: t('library.panel.familyCount', { count: families.length }),
                      dupes: t('library.panel.dupeCount', { count: dupeCount }),
                    })}
                  </div>
                )}
                {coverage === 'Upgrade' && (
                  <div style={{ marginTop: 8, fontSize: 11, color: 'var(--lbb-warn-fg)', display: 'flex', alignItems: 'center', gap: 6 }}>
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

            {/* Recording families section */}
            {families.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--lbb-fg3)' }}>
                    {t('library.panel.recordingFamilies', { count: families.length })}
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--lbb-fg3)' }}>
                    <Icon name="tapematch" size={11} style={{ color: 'var(--lbb-info-fg)' }} /> {t('library.panel.groupedByTapeMatch')}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {families.map(f => <FamilyCard key={f.id} fam={f} />)}
                </div>
              </div>
            )}

            {/* Setlist */}
            {perf.setlist && (
              <div style={{ marginTop: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--lbb-fg3)' }}>
                    {t('library.setlist.title')}
                  </span>
                  {perf.tracks != null && (
                    <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
                      {t('library.setlist.tracksCount', { count: perf.tracks })}
                    </span>
                  )}
                </div>
                <Setlist date={perf.setlist} />
              </div>
            )}

            {/* Assets + distribution — scoped to the best owned source */}
            {canonical && (
              <AssetStripZone
                row={canonical} attachCount={attachCount}
                onAttach={() => actionHandlers.onAttach(canonical)}
                onSpectro={() => actionHandlers.onSpectro(canonical)}
                onMap={() => actionHandlers.onMap()}
              />
            )}
            {owned.length > 0 && canonical && (
              <ShareSeedZone
                history={history}
                note={t('library.share.note', { lb: canonical.lb })}
                onQbt={() => actionHandlers.onQbt(owned)}
                onTorrent={() => actionHandlers.onTorrent([canonical])}
                onForum={() => actionHandlers.onForum([canonical])}
              />
            )}
          </>
        )}
      </div>
    </aside>
  )
}
