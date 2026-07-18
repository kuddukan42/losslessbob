// TODO-150 step 7 (+ step-9 follow-up): the shared Library action registry.
// One action vocabulary, rendered in the right-click context menu on both
// lenses (instructions/design_handoff_unified_library/02-action-system-parity.md)
// and the detail-panel ActionBar/More menu (step 8). Action ids without a real
// backend/UI integration to wire to (`sources`, `notify` — there is no
// "find sources" search or notification system anywhere in the app) are
// omitted rather than shipped inert, per 04-seed-data-and-punchlist.md's
// "wire it or hide it" rule.

import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Icon } from '../Icon'
import type { IconName } from '../Icon'
import { Button } from '../primitives'

export type LibActionGroup = 'open' | 'listen' | 'acquire' | 'share' | 'assets' | 'maintain'

export interface LibAction {
  id: string
  label: string
  icon: IconName
  group: LibActionGroup
  primary?: boolean
  danger?: boolean
  disabled?: boolean
  run: () => void
}

// Minimal row shape the registry needs — both RecordingRow (ScreenLibrary)
// and the performance lens's per-recording stubs satisfy this.
export interface ActionRow {
  lbNumber: number
  lb: string
  owned: boolean
  wish: boolean
  path: string
}

export interface ActionHandlers {
  onOpen: (row: ActionRow) => void
  onCopyLb: (row: ActionRow) => void
  onCopyPath: (row: ActionRow) => void
  onPlay: (row: ActionRow) => void
  onReveal: (row: ActionRow) => void
  onQbt: (rows: ActionRow[]) => void
  onTorrent: (rows: ActionRow[]) => void
  onForum: (rows: ActionRow[]) => void
  onM3u: (rows: ActionRow[]) => void
  onAttach: (row: ActionRow) => void
  onSpectro: (row: ActionRow) => void
  onMap: () => void
  onReconfirm: (row: ActionRow) => void
  onRelocate: (rows: ActionRow[]) => void
  onRemove: (rows: ActionRow[]) => void
  onWishlistToggle: (row: ActionRow) => void
  onWishlistAddMany: (rows: ActionRow[]) => void
  onDossier: (showId: string) => void
}

// entries.date_str resolves to this on olof-covered dates; only those are
// dossier-exportable (backend/dossier.py requires 'YYYY-MM-DD').
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

const GROUP_ORDER: LibActionGroup[] = ['open', 'listen', 'acquire', 'share', 'assets', 'maintain']
// i18n key per group (null = no header rendered for that group).
const GROUP_LABEL_KEY: Record<LibActionGroup, 'library.groups.acquire' | 'library.groups.share' | 'library.groups.assets' | 'library.groups.maintain' | null> = {
  open: null, listen: null,
  acquire: 'library.groups.acquire', share: 'library.groups.share',
  assets: 'library.groups.assets', maintain: 'library.groups.maintain',
}

// ── Recording (LB#) action registry ─────────────────────────────────────────
// `batch` is the right-click target set (checked rows if the clicked row is
// checked, else just the row) — matches ScreenCollection.tsx's getCtxRows().
// Batchable ids (qbt/torrent/forum/relocate/remove) act on it; everything
// else always acts on the single clicked `row`. `t` is passed in because the
// registry is a plain function, not a component.
export function buildRecordingActions(row: ActionRow, batch: ActionRow[], h: ActionHandlers, t: TFunction): LibAction[] {
  const targets = batch.length > 0 ? batch : [row]
  const n = targets.length
  const A: LibAction[] = [
    { id: 'open',   label: t('library.actions.open'),   icon: 'globe', group: 'open', run: () => h.onOpen(row) },
    { id: 'copyLb', label: t('library.actions.copyLb'), icon: 'copy',  group: 'open', run: () => h.onCopyLb(row) },
  ]
  if (row.owned) {
    A.push(
      { id: 'play',     label: t('library.actions.play'),     icon: 'play',     group: 'listen', primary: true, disabled: !row.path, run: () => h.onPlay(row) },
      { id: 'reveal',   label: t('library.actions.reveal'),   icon: 'reveal',   group: 'listen', disabled: !row.path, run: () => h.onReveal(row) },
      { id: 'copyPath', label: t('library.actions.copyPath'), icon: 'copy',     group: 'listen', disabled: !row.path, run: () => h.onCopyPath(row) },
      { id: 'qbt',      label: t('library.actions.qbtAdd', { count: n }), icon: 'upload', group: 'share', run: () => h.onQbt(targets) },
      { id: 'torrent',  label: t('library.actions.torrent'),  icon: 'copy',     group: 'share', disabled: !targets.some(r => r.path), run: () => h.onTorrent(targets) },
      { id: 'forum',    label: t('library.actions.forumPost', { count: n }), icon: 'globe', group: 'share', run: () => h.onForum(targets) },
      { id: 'attach',   label: t('library.actions.attachments'), icon: 'attachments', group: 'assets', run: () => h.onAttach(row) },
      { id: 'spectro',  label: t('library.actions.spectrograms'), icon: 'spectro',  group: 'assets', disabled: !row.path, run: () => h.onSpectro(row) },
      { id: 'map',      label: t('library.actions.showOnMap'), icon: 'map',      group: 'assets', run: () => h.onMap() },
      { id: 'reconfirm',label: t('library.actions.reconfirm'), icon: 'verify',   group: 'maintain', disabled: !row.path, run: () => h.onReconfirm(row) },
      { id: 'relocate', label: t('library.actions.relocate', { count: n }), icon: 'reveal', group: 'maintain', run: () => h.onRelocate(targets) },
      { id: 'remove',   label: t('library.actions.remove', { count: n }), icon: 'trash', group: 'maintain', danger: true, run: () => h.onRemove(targets) },
    )
  } else {
    A.push({
      id: 'wishlist',
      label: row.wish ? t('library.actions.onWishlist') : t('library.actions.addWishlist'),
      icon: row.wish ? 'starFill' : 'star',
      group: 'acquire',
      primary: !row.wish,
      run: () => h.onWishlistToggle(row),
    })
  }
  return A
}

// ── Performance (show) action registry ──────────────────────────────────────
// `canonical` is the show's best-rated recording (any owned/unowned tie-break
// already resolved by the caller — ScreenLibrary's bestOf()/rollupOf()).
export function buildPerformanceActions(recordings: ActionRow[], canonical: ActionRow | null, h: ActionHandlers, t: TFunction, showId?: string): LibAction[] {
  const owned = recordings.filter(r => r.owned)
  const gaps = recordings.filter(r => !r.owned && !r.wish)
  const A: LibAction[] = [
    { id: 'open', label: t('library.actions.open'), icon: 'globe', group: 'open', run: () => h.onOpen(canonical ?? recordings[0]) },
  ]
  if (owned.length > 0 && canonical) {
    A.push(
      { id: 'play',    label: t('library.actions.playBest'),     icon: 'play',   group: 'listen', primary: true, disabled: !canonical.path, run: () => h.onPlay(canonical) },
      { id: 'reveal',  label: t('library.actions.revealBest'),   icon: 'reveal', group: 'listen', disabled: !canonical.path, run: () => h.onReveal(canonical) },
      { id: 'm3u',     label: t('library.actions.m3u'),          icon: 'download', group: 'share', disabled: !owned.some(r => r.path), run: () => h.onM3u(owned) },
      { id: 'qbt',     label: t('library.actions.qbtAddOwned'),  icon: 'upload', group: 'share', run: () => h.onQbt(owned) },
      { id: 'torrent', label: t('library.actions.createTorrent'), icon: 'copy',   group: 'share', disabled: !canonical.path, run: () => h.onTorrent([canonical]) },
      { id: 'forum',   label: t('library.actions.forumPost', { count: 1 }), icon: 'globe',  group: 'share', run: () => h.onForum([canonical]) },
    )
  }
  if (showId !== undefined) {
    A.push({
      id: 'dossier', label: t('library.actions.dossier'), icon: 'lbdir', group: 'share',
      disabled: !ISO_DATE_RE.test(showId), run: () => h.onDossier(showId),
    })
  }
  if (gaps.length > 0) {
    A.push({ id: 'wishlistGaps', label: t('library.actions.wishlistGaps', { count: gaps.length }), icon: 'star', group: 'acquire', run: () => h.onWishlistAddMany(gaps) })
  }
  return A
}

function groupActions(actions: LibAction[]) {
  const by: Partial<Record<LibActionGroup, LibAction[]>> = {}
  for (const a of actions) (by[a.group] ??= []).push(a)
  return GROUP_ORDER.filter(g => by[g]).map(g => ({ group: g, labelKey: GROUP_LABEL_KEY[g], items: by[g]! }))
}

// ── ActionMenu — right-click context menu. Fixed-position, matching the
// convention already established by ScreenCollection.tsx's local ContextMenu. ──

export interface ActionMenuState {
  x: number
  y: number
  title?: string
  actions: LibAction[]
}

export function ActionMenu({ state, onClose }: { state: ActionMenuState; onClose: () => void }) {
  const { t } = useTranslation()
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    const key  = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', down)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', down)
      document.removeEventListener('keydown', key)
    }
  }, [onClose])

  const menuW = 232
  const left = Math.min(state.x, window.innerWidth - menuW - 8)
  const top  = Math.min(state.y, window.innerHeight - 380 - 8)
  const groups = groupActions(state.actions)

  return (
    <div ref={ref} style={{
      position: 'fixed', left, top, zIndex: 2000,
      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
      borderRadius: 8, padding: '4px 0', minWidth: menuW, maxHeight: '80vh', overflowY: 'auto',
      boxShadow: '0 8px 24px rgba(0,0,0,0.22)', fontSize: 'var(--lbb-fs-13)',
    }}>
      {state.title && (
        <div style={{
          padding: '4px 14px 7px', marginBottom: 3, borderBottom: '1px solid var(--lbb-border)',
          fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg2)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{state.title}</div>
      )}
      {groups.map((grp, gi) => (
        <React.Fragment key={grp.group}>
          {gi > 0 && <div style={{ height: 1, background: 'var(--lbb-border)', margin: '3px 0' }} />}
          {grp.labelKey && (
            <div style={{
              fontSize: 9.5, fontWeight: 700, letterSpacing: 0.1, textTransform: 'uppercase',
              color: 'var(--lbb-fg3)', padding: '5px 14px 3px',
            }}>{t(grp.labelKey)}</div>
          )}
          {grp.items.map(a => (
            <button
              key={a.id}
              type="button"
              disabled={a.disabled}
              onClick={() => { if (!a.disabled) { a.run(); onClose() } }}
              style={{
                display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left',
                padding: '6px 14px', fontSize: 'var(--lbb-fs-13)', fontFamily: 'inherit',
                border: 'none', background: 'transparent',
                cursor: a.disabled ? 'default' : 'pointer',
                color: a.disabled ? 'var(--lbb-fg3)' : a.danger ? 'var(--lbb-err-fg)' : 'var(--lbb-fg)',
              }}
              onMouseEnter={e => { if (!a.disabled) (e.currentTarget as HTMLElement).style.background = 'var(--lbb-accent-bg)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
            >
              <Icon name={a.icon} size={14} style={{ flexShrink: 0, opacity: a.disabled ? 0.5 : 1 }} />
              <span style={{ flex: 1 }}>{a.label}</span>
            </button>
          ))}
        </React.Fragment>
      ))}
    </div>
  )
}

export function useActionMenu() {
  const [menu, setMenu] = useState<ActionMenuState | null>(null)
  const openMenu = useCallback((e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => {
    e.preventDefault()
    e.stopPropagation()
    setMenu({ x: e.clientX, y: e.clientY, title, actions })
  }, [])
  const closeMenu = useCallback(() => setMenu(null), [])
  return { menu, openMenu, closeMenu }
}

// ── BulkActionBar — multi-select bar for the recording lens. Parity with
// Collection's inline toolbar (Create torrent / Add to qBittorrent / Update
// location / Remove), shown only once something is checked. ──────────────

export function BulkActionBar({
  count, busy, onCreateTorrent, onAddQbt, onRelocate, onRemove, onClear,
}: {
  count: number
  busy?: boolean
  onCreateTorrent: () => void
  onAddQbt: () => void
  onRelocate: () => void
  onRemove: () => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      background: 'var(--lbb-accent-soft)',
    }}>
      <span style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-accent-mid)' }}>
        {t('library.bulk.selected', { count })}
      </span>
      <Button variant="secondary" size="sm" icon="copy" disabled={busy} onClick={onCreateTorrent}>{t('library.bulk.createTorrent')}</Button>
      <Button variant="secondary" size="sm" icon="upload" disabled={busy} onClick={onAddQbt}>{t('library.bulk.addQbt')}</Button>
      <Button variant="ghost" size="sm" disabled={busy} onClick={onRelocate}>{t('library.bulk.updateLocation')}</Button>
      <Button variant="danger" size="sm" icon="trash" disabled={busy} onClick={onRemove}>{t('library.bulk.remove')}</Button>
      <div style={{ flex: 1 }} />
      <Button variant="ghost" size="sm" onClick={onClear}>{t('library.bulk.clearSelection')}</Button>
    </div>
  )
}
