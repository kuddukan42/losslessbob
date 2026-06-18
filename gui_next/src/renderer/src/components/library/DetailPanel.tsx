// TODO-150 step 8: detail-panel zones (instructions/design_handoff_unified_library/
// 02-action-system-parity.md "Redesigned detail panel — intent zones"). Replaces the
// old flat button-soup pattern with: header (title/badges) -> ActionBar (1 primary +
// Reveal + grouped "More" overflow, same registry as the right-click menu from step 7)
// -> ShareSeed (qBittorrent/torrent/forum status + a single date-sorted activity log,
// merged client-side from the already-loaded /api/collection/prefetch torrents/forum_posts
// arrays — no new backend endpoint) -> AssetStrip (attachments/spectrograms/map as
// state-bearing chips) -> an optional Setlist line for the performance lens.

import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pill, Button, IconButton } from '../primitives'
import type { ActionRow, ActionHandlers, LibAction } from './actions'
import { buildRecordingActions, buildPerformanceActions } from './actions'

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
  fp: boolean
  dup: boolean
  xref: boolean
}

const SRC_ABBR: Record<string, string> = {
  Soundboard: 'SBD', Audience: 'AUD', 'FM/Pre-FM': 'FM', Master: 'MST', Mixed: 'MTX',
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

const panelStyle: React.CSSProperties = {
  width: 320, flexShrink: 0, borderLeft: '1px solid var(--lbb-border)',
  background: 'var(--lbb-surface2)', padding: '10px 16px 20px', overflowY: 'auto',
  display: 'flex', flexDirection: 'column', gap: 0,
}

const chipBtnStyle: React.CSSProperties = { background: 'none', border: 'none', padding: 0, cursor: 'pointer' }

function PanelHeader({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', flexShrink: 0 }}>
      <IconButton icon="x" size={22} title="Close" onClick={onClose} />
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

// ── ActionBar — one primary + Reveal inline; everything else lives in the
// "More" overflow, which renders the identical grouped list as the right-click
// menu (same `openMenu` the context menu already uses). ───────────────────────

function ActionBarZone({ actions, onMore }: { actions: LibAction[]; onMore: (e: React.MouseEvent) => void }) {
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
      <Button variant="ghost" icon="more" onClick={onMore}>More</Button>
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
  const [filter, setFilter] = useState<'all' | 'torrents' | 'forum'>('all')
  const torrents = history?.torrents ?? []
  const forum = history?.forum ?? []
  const seeding = torrents.filter(t => t.tag === 'qBittorrent').length
  const lastForum = forum[0]?.d

  const parts: string[] = []
  if (seeding > 0) parts.push(`Seeding ${seeding} torrent${seeding !== 1 ? 's' : ''}`)
  if (lastForum) parts.push(`last forum post ${lastForum}`)
  const status = parts.length > 0 ? parts.join(' · ') : 'Not shared yet'

  const log = [
    ...torrents.map(t => ({ ...t, kind: 'torrent' as const })),
    ...forum.map(f => ({ ...f, kind: 'forum' as const })),
  ]
    .filter(e => filter === 'all' || (filter === 'torrents' ? e.kind === 'torrent' : e.kind === 'forum'))
    .sort((a, b) => b.d.localeCompare(a.d))

  return (
    <div style={{ flexShrink: 0 }}>
      <ZoneLabel>Share &amp; seed</ZoneLabel>
      {note && <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginBottom: 6 }}>{note}</div>}
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginBottom: 8 }}>{status}</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
        <Button variant="secondary" size="sm" icon="upload" disabled={busy} onClick={onQbt}>Add to qBittorrent</Button>
        <Button variant="secondary" size="sm" icon="copy" disabled={busy} onClick={onTorrent}>Regenerate</Button>
        <Button variant="secondary" size="sm" icon="globe" disabled={busy} onClick={onForum}>Post…</Button>
      </div>
      {(torrents.length > 0 || forum.length > 0) && (
        <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
          {(['all', 'torrents', 'forum'] as const).map(f => (
            <button
              key={f} type="button" onClick={() => setFilter(f)}
              style={{
                padding: '2px 8px', borderRadius: 999, fontSize: 'var(--lbb-fs-10-5)',
                border: '1px solid var(--lbb-border2)', textTransform: 'capitalize', cursor: 'pointer',
                background: filter === f ? 'var(--lbb-accent-soft)' : 'transparent',
                color: filter === f ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
              }}
            >
              {f}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 160, overflowY: 'auto' }}>
        {log.length === 0 ? (
          <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '4px 0' }}>Not shared yet</div>
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

  let specLabel = 'Spectrograms'
  let specTone: 'ok' | 'warn' | 'mute' = 'mute'
  if (specLoading) specLabel = 'Spectrograms — checking…'
  else if (entries.length === 0) specLabel = 'Spectrograms — none'
  else { specLabel = `Spectrograms ${ready}/${entries.length}`; specTone = ready === entries.length ? 'ok' : 'warn' }

  return (
    <div style={{ flexShrink: 0 }}>
      <ZoneLabel>Assets</ZoneLabel>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button type="button" onClick={onAttach} style={chipBtnStyle}>
          <Pill tone={attachCount ? 'ok' : 'mute'} soft dot={!!attachCount}>
            {attachCount ? `Attachments ${attachCount}` : 'No attachments'}
          </Pill>
        </button>
        {row.owned && (
          <button type="button" onClick={onSpectro} style={chipBtnStyle}>
            <Pill tone={specTone} soft>{specLabel}</Pill>
          </button>
        )}
        <button type="button" onClick={onMap} style={chipBtnStyle}>
          <Pill tone="info" soft>Show on map</Pill>
        </button>
      </div>
    </div>
  )
}

// ── Recording detail panel ──────────────────────────────────────────────────

export function RecordingDetailPanel({ row, history, attachCount, actionHandlers, openMenu, onClose }: {
  row: DetailRow
  history: RowHistory | undefined
  attachCount: number | undefined
  actionHandlers: ActionHandlers
  openMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  onClose: () => void
}) {
  const actions = buildRecordingActions(row, [], actionHandlers)
  return (
    <aside style={panelStyle} data-panel="recording-detail">
      <PanelHeader onClose={onClose} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 700, fontSize: 'var(--lbb-fs-15)', color: 'var(--lbb-fg)' }}>
          {row.lb}
        </span>
        {row.rating !== '—' && <Pill tone={ratingTone(row.rating)} soft>{row.rating}</Pill>}
        <Pill tone={statusTone(row.status)} soft>{row.status}</Pill>
        {row.src && <Pill tone="mute" soft>{SRC_ABBR[row.src] ?? row.src}</Pill>}
        {row.dup && <Pill tone="mute" soft>dup</Pill>}
        {row.xref && <Pill tone="mute" soft>xref</Pill>}
      </div>
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginTop: 4 }}>
        {row.date} · {row.loc}
      </div>
      {row.desc && (
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 2 }}>{row.desc}</div>
      )}
      {row.owned && row.folder && (
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 6, fontFamily: 'var(--lbb-mono)' }}>
          {row.folder}{row.conf ? ` · confirmed ${row.conf}` : ''}{row.fp ? ' · fingerprinted' : ''}
        </div>
      )}
      <ActionBarZone actions={actions} onMore={e => openMenu(e, row.lb, actions)} />
      {row.owned && (
        <ShareSeedZone
          history={history}
          onQbt={() => actionHandlers.onQbt([row])}
          onTorrent={() => actionHandlers.onTorrent([row])}
          onForum={() => actionHandlers.onForum([row])}
        />
      )}
      {row.owned && (
        <AssetStripZone
          row={row} attachCount={attachCount}
          onAttach={() => actionHandlers.onAttach(row)}
          onSpectro={() => actionHandlers.onSpectro(row)}
          onMap={() => actionHandlers.onMap()}
        />
      )}
    </aside>
  )
}

// ── Performance (show) detail panel ─────────────────────────────────────────

export function PerformanceDetailPanel({ perf, recordings, canonical, history, attachCount, actionHandlers, openMenu, onClose }: {
  perf: { id: string; disp: string; venue: string | null; city: string | null; tour?: string; tracks?: number; title?: string; confirmed?: boolean }
  recordings: DetailRow[]
  canonical: DetailRow | null
  history: RowHistory | undefined
  attachCount: number | undefined
  actionHandlers: ActionHandlers
  openMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  onClose: () => void
}) {
  const actions = buildPerformanceActions(recordings, canonical, actionHandlers)
  const owned = recordings.filter(r => r.owned)
  return (
    <aside style={panelStyle} data-panel="performance-detail">
      <PanelHeader onClose={onClose} />
      <div style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 700, fontSize: 'var(--lbb-fs-15)', color: 'var(--lbb-fg)' }}>
        {perf.disp}
        {perf.confirmed === false && (
          <span title="Inferred from the recording's own date/location — not matched to a known Dylan show date">
            <Pill tone="mute" soft style={{ marginLeft: 8, fontSize: 'var(--lbb-fs-9-5)' }}>Unconfirmed</Pill>
          </span>
        )}
      </div>
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginTop: 2 }}>
        {perf.venue || perf.city || '—'}{perf.tour ? ` · ${perf.tour}` : ''}
      </div>
      {perf.title && (
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-accent-mid)', fontStyle: 'italic', marginTop: 2 }}>
          "{perf.title}"
        </div>
      )}
      <ActionBarZone actions={actions} onMore={e => openMenu(e, perf.disp, actions)} />
      {owned.length > 0 && canonical && (
        <ShareSeedZone
          history={history}
          note={`Distribution for best owned source · ${canonical.lb}`}
          onQbt={() => actionHandlers.onQbt(owned)}
          onTorrent={() => actionHandlers.onTorrent([canonical])}
          onForum={() => actionHandlers.onForum([canonical])}
        />
      )}
      {canonical && (
        <AssetStripZone
          row={canonical} attachCount={attachCount}
          onAttach={() => actionHandlers.onAttach(canonical)}
          onSpectro={() => actionHandlers.onSpectro(canonical)}
          onMap={() => actionHandlers.onMap()}
        />
      )}
      {perf.tracks != null && (
        <div style={{ flexShrink: 0 }}>
          <ZoneLabel>Setlist</ZoneLabel>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>{perf.tracks} tracks documented</div>
        </div>
      )}
    </aside>
  )
}
