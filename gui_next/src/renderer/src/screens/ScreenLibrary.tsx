import React, { useCallback, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Chip, IconButton, Input, Pill, Toast, ConfirmDialog } from '../components'
import type { ToastTone } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import {
  buildRecordingActions, buildPerformanceActions, ActionMenu, useActionMenu, BulkActionBar,
} from '../components/library/actions'
import type { ActionRow, ActionHandlers, LibAction } from '../components/library/actions'
import { RecordingDetailPanel, PerformanceDetailPanel } from '../components/library/DetailPanel'
import type { RowHistory } from '../components/library/DetailPanel'
import { useAttachmentsStore } from '../lib/attachmentsStore'
import { useSpectrogramStore } from '../lib/spectrogramStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

// ── TODO-150 step (4): Recording lens / no-families fallback ──────────────────
// Flat, LB#-keyed table over the full catalog. Per the design contract
// (instructions/design_handoff_unified_library/03-data-contract.md) this row
// shape is also the "no-families fallback" the performance lens (step 6) will
// reuse to render recordings under a show when no TapeMatch family data
// exists.
//
// TODO-150 step (7): the shared action registry (components/library/actions.tsx)
// is wired in here — right-click context menu on both lenses, plus a
// checkbox bulk-select bar on the recording lens with batched relocate/
// remove. The detail-panel ActionBar/MoreMenu surface is step 8.

const BASE = window.api.flaskBase

function blobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Types ─────────────────────────────────────────────────────────────────────

type LibStatus  = 'Public' | 'Private' | 'Missing'
type RatingGrade = 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D+' | 'D' | 'D-' | 'F' | '—'
type Scope       = 'all' | 'owned' | 'unowned'
type SortKey     = 'lb' | 'date' | 'rating'
type SortDir     = 'asc' | 'desc'
type HealthFlag  = 'Wishlist' | 'Duplicates' | 'Unconfirmed' | 'No FP'

interface RecordingRow {
  lb: string
  lbNumber: number
  year: number
  decade: string
  date: string
  loc: string
  desc: string
  rating: RatingGrade
  src: string | null
  status: LibStatus
  owned: boolean
  wish: boolean
  dup: boolean
  xref: boolean
  fp: boolean
  unconf: boolean
  folder: string
  path: string
  conf: string
  // TapeMatch family fields (performance lens only — merged in from
  // /api/tapematch/families, never set by the recording lens's adapter).
  fam?: string
  famLabel?: string
  famConf?: number | null
  famBy?: 'lb' | 'ai' | 'ai+lb'
}

type FlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'row'; row: RecordingRow }

const VALID_RATINGS = new Set(['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F'])

const SRC_ABBR: Record<string, string> = {
  Soundboard: 'SBD', Audience: 'AUD', 'FM/Pre-FM': 'FM', Master: 'MST', Mixed: 'MTX',
}

const SOURCE_FULL: Record<string, string> = {
  Soundboard: 'Soundboard', Audience: 'Audience', 'FM/Pre-FM': 'FM / Pre-FM',
  Master: 'Master / Studio', Mixed: 'Matrix / Mixed',
}

const RATING_RANK: Record<string, number> = {
  'A+': 13, A: 12, 'A-': 11, 'B+': 10, B: 9, 'B-': 8, 'C+': 7, C: 6, 'C-': 5, 'D+': 4, D: 3, 'D-': 2, F: 1, '—': 0,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractYear(dateStr: string): number {
  if (!dateStr) return 0
  const parts = dateStr.split('/')
  if (parts.length < 3) return 0
  const n = parseInt(parts[parts.length - 1].trim(), 10)
  if (isNaN(n)) return 0
  if (n < 100) return n >= 49 ? 1900 + n : 2000 + n
  return n
}

function decadeOf(year: number): string {
  if (!year) return 'Unknown'
  return `${Math.floor((year % 100) / 10) * 10}s`
}

function statusTone(s: LibStatus): 'ok' | 'warn' | 'mute' {
  if (s === 'Public')  return 'ok'
  if (s === 'Missing') return 'warn'
  return 'mute'
}

function ratingTone(r: RatingGrade): 'ok' | 'info' | 'warn' | 'mute' {
  if (r === 'A+' || r === 'A' || r === 'A-') return 'ok'
  if (r === 'B+' || r === 'B' || r === 'B-') return 'info'
  if (r === 'C+' || r === 'C' || r === 'C-') return 'warn'
  return 'mute'
}

// TODO-150 step 7: shared shape the action registry (components/library/actions.tsx) needs.
function toRecAction(r: RecordingRow): ActionRow {
  return { lbNumber: r.lbNumber, lb: r.lb, owned: r.owned, wish: r.wish, path: r.path }
}

function toggleSet<T>(setFn: React.Dispatch<React.SetStateAction<Set<T>>>, val: T) {
  setFn(prev => {
    const next = new Set(prev)
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  })
}

const HEALTH_CHECK: Record<HealthFlag, (r: RecordingRow) => boolean> = {
  Wishlist:     r => r.wish,
  Duplicates:   r => r.dup,
  Unconfirmed:  r => r.owned && r.unconf,
  'No FP':      r => r.owned && !r.fp,
}

// ── FacetGroup (mirrors ScreenSearch.tsx's left-rail facet pattern) ───────────

interface FacetGroupProps<T extends string> {
  title: string
  items: Array<{ label: T; count: number }>
  active: Set<T>
  onToggle: (label: T) => void
}

function FacetGroup<T extends string>({ title, items, active, onToggle }: FacetGroupProps<T>) {
  const [open, setOpen] = useState(true)
  if (items.length === 0) return null
  return (
    <div style={{ borderBottom: '1px solid var(--lbb-border)' }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--lbb-fg3)',
        }}
      >
        {title}
        <Icon name={open ? 'chevDown' : 'chevRight'} size={11} />
      </button>
      {open && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '0 10px 10px' }}>
          {items.map(({ label, count }) => (
            <Chip key={label} size="sm" active={active.has(label)} onClick={() => onToggle(label)} count={count}>
              {label}
            </Chip>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ActiveFilter chip (summary strip) ──────────────────────────────────────────

function ActiveFilter({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 4, fontSize: 'var(--lbb-fs-11)',
      background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)', fontWeight: 600, whiteSpace: 'nowrap',
    }}>
      {label}
      <button
        type="button" onClick={onRemove}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'currentColor', padding: 0, display: 'flex' }}
      >
        <Icon name="x" size={10} />
      </button>
    </span>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────────

export function ScreenLibrary(): React.JSX.Element {
  // ── TODO-150 step 6: lens toggle. "By performance" is the new, richer view
  // (00-overview.md "One catalogue, two lenses"); "By recording" is this
  // screen's original step-4 flat table. Both read the same merged `rows`.
  const [lens, setLens] = useState<'performance' | 'recording'>('performance')

  const [filterPaneOpen, setFilterPaneOpen] = useState(true)
  const [scope,    setScope]    = useState<Scope>('all')
  const [query,    setQuery]    = useState('')
  const [groupByYear, setGroupByYear] = useState(true)
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())
  const [selectedLb, setSelectedLb] = useState<number | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('lb')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  // TODO-150 step 7: checkbox multi-select for the recording lens's bulk bar.
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())

  const [activeDecade, setActiveDecade] = useState<Set<string>>(new Set())
  const [activeStatus, setActiveStatus] = useState<Set<LibStatus>>(new Set())
  const [activeRating, setActiveRating] = useState<Set<RatingGrade>>(new Set())
  const [activeSource, setActiveSource] = useState<Set<string>>(new Set())
  const [activeHealth, setActiveHealth] = useState<Set<HealthFlag>>(new Set())

  const tableParentRef = useRef<HTMLDivElement>(null)

  // ── TODO-150 step 7: shared action system ───────────────────────────────────
  // Toast/confirm UI + the ActionHandlers bag, shared by both lenses. Handlers
  // call the SAME backend endpoints ScreenCollection.tsx already uses for
  // these ids — this isn't new backend behavior, just a second surface for it.

  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setActiveAttachLb = useAttachmentsStore(s => s.setActiveLb)
  const addPendingSpectro = useSpectrogramStore(s => s.addPending)
  const addToFolderQueue = useFolderQueueStore(s => s.addFolders)

  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; body: string; onConfirm: () => void } | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])
  const refreshCollection = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['library-catalog'] })
    queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] })
  }, [queryClient])

  const actionHandlers = useMemo<ActionHandlers>(() => ({
    onOpen: (row) => {
      window.open(`http://www.losslessbob.wonderingwhattochoose.com/detail/${row.lb}.html`, '_blank')
    },
    onCopyLb: (row) => { navigator.clipboard.writeText(row.lb) },
    onCopyPath: (row) => { navigator.clipboard.writeText(row.path) },
    onPlay: async (row) => {
      if (!row.path) return
      try {
        const resp = await fetch(`${BASE}/api/open/vlc`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paths: [row.path] }),
        })
        const data = await resp.json()
        if (!data.ok) showToast(data.error || 'VLC not found', 'bad')
      } catch { showToast('VLC request failed', 'bad') }
    },
    onReveal: async (row) => {
      if (!row.path) { showToast('No disk path for this entry', 'info'); return }
      await window.api.openPath(row.path)
    },
    onQbt: async (rows) => {
      const lbs = rows.map(r => r.lbNumber)
      if (!lbs.length) return
      try {
        const resp = await fetch(`${BASE}/api/qbt/add`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lb_numbers: lbs }),
        })
        const data = await resp.json()
        showToast(`Added ${data.added ?? 0}/${data.total ?? lbs.length} to qBittorrent`, data.ok ? 'ok' : 'bad')
      } catch { showToast('qBittorrent request failed', 'bad') }
    },
    onTorrent: async (rows) => {
      const targets = rows.filter(r => r.path)
      if (!targets.length) { showToast('No disk path for this entry', 'info'); return }
      setActionBusy(true)
      let ok = 0; let fail = 0
      for (const r of targets) {
        try {
          const resp = await fetch(`${BASE}/api/torrent/create`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: r.lbNumber, source_folder: r.path }),
          })
          const data = await resp.json()
          if (data.ok) ok++; else fail++
        } catch { fail++ }
      }
      setActionBusy(false)
      showToast(`${ok} torrent${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`, ok > 0 ? 'ok' : 'bad')
    },
    onForum: (rows) => {
      const postOne = async (r: ActionRow) => {
        try {
          const previewResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/preview_forum`)
          const previewData = await previewResp.json()
          const postResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/post_forum`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject: previewData.subject ?? '', body: previewData.body ?? '' }),
          })
          return (await postResp.json()).ok as boolean
        } catch { return false }
      }
      if (rows.length === 1) {
        postOne(rows[0]).then(ok => showToast(ok ? `Posted ${rows[0].lb} to forum` : 'Forum post failed', ok ? 'ok' : 'bad'))
        return
      }
      setConfirm({
        title: 'Post to forum',
        body: `Post ${rows.length} entries to the forum? Each will be posted using its auto-generated subject and body.`,
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          for (const r of rows) { if (await postOne(r)) ok++; else fail++ }
          setActionBusy(false)
          showToast(`${ok} post${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`, ok > 0 ? 'ok' : 'bad')
        },
      })
    },
    onM3u: async (rows) => {
      const lbs = rows.map(r => r.lbNumber)
      if (!lbs.length) { showToast('No owned recordings to export', 'info'); return }
      try {
        const resp = await fetch(`${BASE}/api/collection/export/m3u?lb_numbers=${lbs.join(',')}`)
        const blob = await resp.blob()
        blobDownload(blob, 'show.m3u')
      } catch { showToast('M3U export failed', 'bad') }
    },
    onAttach: (row) => { setActiveAttachLb(row.lbNumber); navigate('/attachments') },
    onSpectro: async (row) => {
      if (!row.path) return
      try {
        const resp = await fetch(`${BASE}/api/spectrogram/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [row.path] }),
        })
        const data = await resp.json()
        if (data.ok) { addPendingSpectro([row.path]); navigate('/spectrograms') }
        else showToast(data.error || 'Spectrogram request failed', 'bad')
      } catch { showToast('Spectrogram request failed', 'bad') }
    },
    onMap: () => navigate('/map'),
    onReconfirm: (row) => {
      if (!row.path) return
      addToFolderQueue([row.path])
      navigate('/verify')
    },
    onRefp: async (row) => {
      if (!row.path) return
      try {
        const resp = await fetch(`${BASE}/api/fingerprint/build`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folders: [{ disk_path: row.path, lb_number: row.lbNumber }] }),
        })
        const data = await resp.json()
        showToast(data.ok ? `Fingerprinting ${row.lb}` : (data.error || 'Fingerprint failed'), data.ok ? 'ok' : 'bad')
      } catch { showToast('Fingerprint request failed', 'bad') }
    },
    onRelocate: async (rows) => {
      if (!rows.length) return
      if (rows.length === 1) {
        const target = rows[0]
        const dir = await window.api.pickDir()
        if (!dir) return
        const folderName = dir.replace(/\/+$/, '').split('/').pop() || dir
        try {
          await fetch(`${BASE}/api/collection/${target.lbNumber}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disk_path: dir, folder_name: folderName }),
          })
          showToast(`Updated location for ${target.lb}`, 'ok')
          refreshCollection()
        } catch { showToast('Update failed', 'bad') }
        return
      }
      const parentDir = await window.api.pickDir()
      if (!parentDir) return
      setActionBusy(true)
      let ok = 0; let skip = 0
      try {
        const scanResp = await fetch(`${BASE}/api/pipeline/scan-dir`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root: parentDir, recursive: false }),
        })
        const scanData = await scanResp.json()
        const entries: { lb_number: number; folder: string; path: string }[] = scanData.entries ?? []
        for (const r of rows) {
          const match = entries.find(e => e.lb_number === r.lbNumber)
          if (match) {
            await fetch(`${BASE}/api/collection/${r.lbNumber}`, {
              method: 'PATCH', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ disk_path: match.path, folder_name: match.folder }),
            })
            ok++
          } else skip++
        }
      } catch { skip = rows.length }
      setActionBusy(false)
      showToast(`Updated ${ok}${skip > 0 ? `, ${skip} not found` : ''}`, ok > 0 ? 'ok' : 'info')
      if (ok > 0) refreshCollection()
    },
    onRemove: (rows) => {
      if (!rows.length) return
      setConfirm({
        title: 'Remove from collection',
        body: `Remove ${rows.length} item${rows.length !== 1 ? 's' : ''} from your collection? Files on disk will not be deleted.`,
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          for (const r of rows) {
            try { await fetch(`${BASE}/api/collection/${r.lbNumber}`, { method: 'DELETE' }); ok++ } catch { fail++ }
          }
          setActionBusy(false)
          showToast(`Removed ${ok}${fail > 0 ? `, ${fail} failed` : ''}`, ok > 0 ? 'ok' : 'bad')
          refreshCollection()
        },
      })
    },
    onWishlistToggle: async (row) => {
      try {
        if (row.wish) {
          await fetch(`${BASE}/api/wishlist/${row.lbNumber}`, { method: 'DELETE' })
          showToast(`Removed ${row.lb} from wishlist`, 'ok')
        } else {
          await fetch(`${BASE}/api/wishlist`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: row.lbNumber }),
          })
          showToast(`Added ${row.lb} to wishlist`, 'ok')
        }
        refreshCollection()
      } catch { showToast('Wishlist update failed', 'bad') }
    },
    onWishlistAddMany: async (rows) => {
      if (!rows.length) return
      let ok = 0
      for (const r of rows) {
        try {
          await fetch(`${BASE}/api/wishlist`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: r.lbNumber }),
          })
          ok++
        } catch { /* continue */ }
      }
      showToast(`Added ${ok} to wishlist`, ok > 0 ? 'ok' : 'bad')
      if (ok > 0) refreshCollection()
    },
  }), [showToast, refreshCollection, navigate, setActiveAttachLb, addPendingSpectro, addToFolderQueue])

  const { menu: ctxMenu, openMenu: openCtxMenu, closeMenu: closeCtxMenu } = useActionMenu()

  // ── Data loading — client-side adapter over the existing catalog + collection
  // prefetch endpoints (no backend changes this step) ──────────────────────────

  const { data: catalog, isLoading: catalogLoading } = useQuery({
    queryKey: ['library-catalog'],
    queryFn: () => fetch(`${BASE}/api/search`).then(r => r.json()),
    staleTime: Infinity,
  })

  // Same query key ScreenCollection.tsx uses for this endpoint — shares the
  // react-query cache instead of double-fetching when both screens are mounted.
  const { data: prefetch } = useQuery({
    queryKey: ['collection-prefetch'],
    queryFn: () => fetch(`${BASE}/api/collection/prefetch`).then(r => r.json()),
    staleTime: Infinity,
  })

  // TODO-150 step 8: detail-panel ShareSeed zone. `prefetch.torrents`/
  // `prefetch.forum_posts` already cover every LB — no new backend endpoint,
  // just grouped by lb_number into the per-row shape the panel reads.
  const { data: attachData } = useQuery({
    queryKey: ['library-attachments-cached'],
    queryFn: () => fetch(`${BASE}/api/attachments/cached`).then(r => r.json()),
    staleTime: 60_000,
  })

  const historyMap = useMemo(() => {
    const m = new Map<number, RowHistory>()
    const get = (lb: number) => m.get(lb) ?? (m.set(lb, { torrents: [], forum: [] }), m.get(lb)!)
    if (Array.isArray(prefetch?.torrents)) {
      for (const t of prefetch.torrents) {
        get(t.lb_number).torrents.push({
          d: t.created_at ?? '',
          f: (t.torrent_path ?? '').split(/[/\\]/).pop() ?? '',
          tag: t.added_to_qbt ? 'qBittorrent' : 'Local',
        })
      }
    }
    if (Array.isArray(prefetch?.forum_posts)) {
      for (const p of prefetch.forum_posts) {
        get(p.lb_number).forum.push({ d: p.posted_at ?? '', f: p.subject ?? '', tag: 'Posted' })
      }
    }
    return m
  }, [prefetch])

  const attachCountMap = useMemo(() => {
    const m = new Map<number, number>()
    if (Array.isArray(attachData?.entries)) {
      for (const e of attachData.entries) m.set(e.lb_number, (e.files ?? []).length)
    }
    return m
  }, [attachData])

  const rows = useMemo<RecordingRow[]>(() => {
    if (!Array.isArray(catalog)) return []

    const ownedMap = new Map<number, { folder: string; path: string; conf: string }>()
    if (prefetch && Array.isArray(prefetch.collection)) {
      for (const c of prefetch.collection) {
        ownedMap.set(c.lb_number, {
          folder: c.folder_name ?? '',
          path:   c.disk_path ?? '',
          conf:   c.confirmed_at ?? '',
        })
      }
    }
    const fpMap: Record<string, number> =
      prefetch && prefetch.fingerprints && !prefetch.fingerprints.error ? prefetch.fingerprints : {}
    const wishSet = new Set<number>(
      prefetch && Array.isArray(prefetch.wishlist) ? prefetch.wishlist.map((w: any) => w.lb_number) : []
    )
    const dupSet = new Set<number>()
    if (prefetch && Array.isArray(prefetch.duplicates)) {
      for (const group of prefetch.duplicates) {
        if (Array.isArray(group.owned) && group.owned.length > 1) {
          for (const o of group.owned) dupSet.add(o.lb_number as number)
        }
      }
    }
    const xrefSet = new Set<number>(
      prefetch && Array.isArray(prefetch.xref_lb_numbers) ? prefetch.xref_lb_numbers : []
    )

    return (catalog as any[]).map((d): RecordingRow => {
      const lbNumber = d.lb_number as number
      const owned = ownedMap.has(lbNumber)
      const own = ownedMap.get(lbNumber)
      const year = extractYear(d.date_str ?? '')
      const raw = d.rating ?? ''
      return {
        lb:       `LB-${String(lbNumber).padStart(5, '0')}`,
        lbNumber,
        year,
        decade:   decadeOf(year),
        date:     d.date_str ?? '',
        loc:      d.location ?? '',
        desc:     d.description ?? '',
        rating:   (VALID_RATINGS.has(raw) ? raw : '—') as RatingGrade,
        src:      (d.source_type as string | null) ?? null,
        status:   ({ public: 'Public', private: 'Private', missing: 'Missing' }[d.lb_status as string] ?? 'Missing') as LibStatus,
        owned,
        wish:     wishSet.has(lbNumber),
        dup:      dupSet.has(lbNumber),
        xref:     xrefSet.has(lbNumber),
        fp:       (fpMap[String(lbNumber)] ?? 0) > 0,
        unconf:   owned && !own?.conf,
        folder:   own?.folder ?? '',
        path:     own?.path ?? '',
        conf:     own?.conf ?? '',
      }
    })
  }, [catalog, prefetch])

  const ownedCount = useMemo(() => rows.reduce((n, r) => n + (r.owned ? 1 : 0), 0), [rows])

  // ── Facet counts (from the full, unfiltered merged set — matches the
  // existing convention in ScreenSearch.tsx, not progressively narrowed) ───────

  const facetCounts = useMemo(() => {
    const decadeC: Record<string, number> = {}
    const statusC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    const sourceC: Record<string, number> = {}
    const healthC: Record<string, number> = {}
    for (const r of rows) {
      decadeC[r.decade] = (decadeC[r.decade] ?? 0) + 1
      statusC[r.status] = (statusC[r.status] ?? 0) + 1
      ratingC[r.rating] = (ratingC[r.rating] ?? 0) + 1
      const src = r.src ?? 'Unset'
      sourceC[src] = (sourceC[src] ?? 0) + 1
      for (const h of Object.keys(HEALTH_CHECK) as HealthFlag[]) {
        if (HEALTH_CHECK[h](r)) healthC[h] = (healthC[h] ?? 0) + 1
      }
    }
    return { decadeC, statusC, ratingC, sourceC, healthC }
  }, [rows])

  // ── Filtering ────────────────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter(r => {
      if (scope === 'owned'   && !r.owned) return false
      if (scope === 'unowned' &&  r.owned) return false
      if (q && !`${r.lb} ${r.loc} ${r.desc}`.toLowerCase().includes(q)) return false
      if (activeDecade.size > 0 && !activeDecade.has(r.decade)) return false
      if (activeStatus.size > 0 && !activeStatus.has(r.status)) return false
      if (activeRating.size > 0 && !activeRating.has(r.rating)) return false
      if (activeSource.size > 0 && !activeSource.has(r.src ?? 'Unset')) return false
      if (activeHealth.size > 0 && ![...activeHealth].some(h => HEALTH_CHECK[h](r))) return false
      return true
    })
  }, [rows, scope, query, activeDecade, activeStatus, activeRating, activeSource, activeHealth])

  // ── Sorting ──────────────────────────────────────────────────────────────

  const sortedRows = useMemo(() => {
    const arr = [...filteredRows]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      if (sortKey === 'lb')     return (a.lbNumber - b.lbNumber) * dir
      if (sortKey === 'date')   return a.date.localeCompare(b.date) * dir
      return ((RATING_RANK[a.rating] ?? 0) - (RATING_RANK[b.rating] ?? 0)) * dir
    })
    return arr
  }, [filteredRows, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); return }
    setSortKey(key)
    setSortDir('asc')
  }

  // ── Grouping by year ─────────────────────────────────────────────────────

  const groupedByYear = useMemo(() => {
    if (!groupByYear) return null
    const map = new Map<string, RecordingRow[]>()
    for (const r of sortedRows) {
      const key = r.year > 0 ? String(r.year) : 'Unknown'
      const arr = map.get(key)
      if (arr) arr.push(r)
      else map.set(key, [r])
    }
    return [...map.entries()].sort(([a], [b]) => {
      const an = a === 'Unknown' ? -1 : parseInt(a, 10)
      const bn = b === 'Unknown' ? -1 : parseInt(b, 10)
      return an - bn
    })
  }, [sortedRows, groupByYear])

  const flatItems = useMemo((): FlatItem[] => {
    if (!groupByYear || !groupedByYear) return sortedRows.map(row => ({ kind: 'row', row }) as FlatItem)
    const items: FlatItem[] = []
    for (const [year, yearRows] of groupedByYear) {
      items.push({ kind: 'group', year, count: yearRows.length })
      if (!collapsedYears.has(year)) for (const row of yearRows) items.push({ kind: 'row', row })
    }
    return items
  }, [groupedByYear, groupByYear, sortedRows, collapsedYears])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: i => flatItems[i]?.kind === 'group' ? 32 : 34,
    overscan: 12,
  })

  const colCount = 9 // edge + checkbox + LB# + Status + Date + Location + Rating + Source + Own

  // ── TODO-150 step 7: checkbox selection + right-click target rows ──────────
  // Mirrors ScreenCollection.tsx's getCtxRows(): right-click a checked row to
  // act on the whole checked set, right-click an unchecked row to act on it alone.

  const toggleCheck = (lbNumber: number, checked: boolean) => {
    setCheckedIds(prev => {
      const next = new Set(prev)
      checked ? next.add(lbNumber) : next.delete(lbNumber)
      return next
    })
  }
  const allChecked = sortedRows.length > 0 && sortedRows.every(r => checkedIds.has(r.lbNumber))
  const toggleAllChecked = () => {
    setCheckedIds(prev => {
      if (allChecked) return new Set()
      const next = new Set(prev)
      sortedRows.forEach(r => next.add(r.lbNumber))
      return next
    })
  }
  const getCheckedRows = useCallback((): RecordingRow[] => rows.filter(r => checkedIds.has(r.lbNumber)), [rows, checkedIds])
  const getCtxBatch = useCallback((row: RecordingRow): ActionRow[] => {
    if (checkedIds.size > 0 && checkedIds.has(row.lbNumber)) return getCheckedRows().map(toRecAction)
    return []
  }, [checkedIds, getCheckedRows])

  const handleBulkCreateTorrent = () => actionHandlers.onTorrent(getCheckedRows().map(toRecAction))
  const handleBulkAddQbt = () => actionHandlers.onQbt(getCheckedRows().map(toRecAction))
  const handleBulkRelocate = () => actionHandlers.onRelocate(getCheckedRows().map(toRecAction))
  const handleBulkRemove = () => actionHandlers.onRemove(getCheckedRows().map(toRecAction))

  const hasActiveFilters = activeDecade.size > 0 || activeStatus.size > 0 || activeRating.size > 0
    || activeSource.size > 0 || activeHealth.size > 0 || scope !== 'all'

  const clearAll = () => {
    setActiveDecade(new Set()); setActiveStatus(new Set()); setActiveRating(new Set())
    setActiveSource(new Set()); setActiveHealth(new Set()); setScope('all'); setQuery('')
  }

  const filterChips: Array<{ label: string; onRemove: () => void }> = [
    ...[...activeDecade].map(d => ({ label: `Decade: ${d}`, onRemove: () => toggleSet(setActiveDecade, d) })),
    ...[...activeStatus].map(s => ({ label: `Status: ${s}`, onRemove: () => toggleSet(setActiveStatus, s) })),
    ...[...activeRating].map(r => ({ label: `Rating: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
    ...[...activeSource].map(s => ({ label: `Source: ${s}`, onRemove: () => toggleSet(setActiveSource, s) })),
    ...[...activeHealth].map(h => ({ label: h, onRemove: () => toggleSet(setActiveHealth, h) })),
  ]

  const loading = catalogLoading && rows.length === 0

  const lensToggle = (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '8px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
    }}>
      <div style={{ display: 'inline-flex', border: '1px solid var(--lbb-border2)', borderRadius: 6, overflow: 'hidden' }}>
        {(['performance', 'recording'] as const).map(l => (
          <button
            key={l} type="button" onClick={() => setLens(l)}
            style={{
              padding: '5px 12px', fontSize: 'var(--lbb-fs-12)', fontWeight: lens === l ? 650 : 500,
              background: lens === l ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
              color: lens === l ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
              border: 'none', cursor: 'pointer',
            }}
          >
            {l === 'performance' ? 'By performance' : 'By recording'}
          </button>
        ))}
      </div>
    </div>
  )

  // ── TODO-150 step 7: overlays shared by both lenses (context menu, toast,
  // confirm dialog) — rendered once per branch since each `return` is a
  // separate screen root. ──────────────────────────────────────────────────
  const overlays = (
    <>
      {ctxMenu && <ActionMenu state={ctxMenu} onClose={closeCtxMenu} />}
      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  )

  if (lens === 'performance') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }} data-screen-label="Library (by performance)">
        {lensToggle}
        <PerformanceLensView
          rows={rows} catalogLoading={loading} actionHandlers={actionHandlers} openCtxMenu={openCtxMenu}
          historyMap={historyMap} attachCountMap={attachCountMap}
        />
        {overlays}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }} data-screen-label="Library (by recording)">
      {lensToggle}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

      {/* ── Facet rail ──────────────────────────────────────────────────── */}
      <aside style={{
        width: filterPaneOpen ? 220 : 32, flexShrink: 0,
        borderRight: '1px solid var(--lbb-border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--lbb-surface2)',
        overflowY: filterPaneOpen ? 'auto' : 'hidden',
        overflowX: 'hidden',
        transition: 'width 180ms ease',
      }}>
        {!filterPaneOpen ? (
          <button type="button" title="Show filters" onClick={() => setFilterPaneOpen(true)} style={{
            margin: '8px auto', display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 24, height: 24, borderRadius: 4, flexShrink: 0,
            background: 'none', border: '1px solid var(--lbb-border2)', cursor: 'pointer', color: 'var(--lbb-fg3)',
          }}>
            <Icon name="chevRight" size={13} />
          </button>
        ) : (
          <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '6px 8px 0', flexShrink: 0 }}>
            <button type="button" title="Hide filters" onClick={() => setFilterPaneOpen(false)} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 22, height: 22, borderRadius: 4,
              background: 'none', border: '1px solid var(--lbb-border2)', cursor: 'pointer', color: 'var(--lbb-fg3)',
            }}>
              <Icon name="chevLeft" size={13} />
            </button>
          </div>
        )}

        {filterPaneOpen && <>
          {/* Scope */}
          <div style={{ borderBottom: '1px solid var(--lbb-border)', padding: '8px 12px' }}>
            <div style={{
              fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'var(--lbb-fg3)', marginBottom: 8,
            }}>
              Scope
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid var(--lbb-border2)', borderRadius: 6, overflow: 'hidden' }}>
              {([
                ['all', 'Everything', rows.length],
                ['owned', 'My collection', ownedCount],
                ['unowned', 'Not owned', rows.length - ownedCount],
              ] as [Scope, string, number][]).map(([opt, label, n], i) => (
                <button
                  key={opt} type="button" onClick={() => setScope(opt)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '5px 10px', fontSize: 'var(--lbb-fs-11)', cursor: 'pointer',
                    background: scope === opt ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                    color: scope === opt ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                    fontWeight: scope === opt ? 600 : 400,
                    border: 'none', borderTop: i > 0 ? '1px solid var(--lbb-border2)' : 'none',
                  }}
                >
                  <span>{label}</span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--lbb-fg3)' }}>{n.toLocaleString()}</span>
                </button>
              ))}
            </div>
          </div>

          <FacetGroup
            title="Decade"
            items={Object.entries(facetCounts.decadeC).sort(([a], [b]) => a.localeCompare(b)).map(([label, count]) => ({ label, count }))}
            active={activeDecade}
            onToggle={v => toggleSet(setActiveDecade, v)}
          />
          <FacetGroup
            title="Status"
            items={(['Public', 'Private', 'Missing'] as LibStatus[]).map(label => ({ label, count: facetCounts.statusC[label] ?? 0 }))}
            active={activeStatus}
            onToggle={v => toggleSet(setActiveStatus, v)}
          />
          <FacetGroup
            title="Rating"
            items={Object.entries(facetCounts.ratingC).map(([label, count]) => ({ label: label as RatingGrade, count }))}
            active={activeRating}
            onToggle={v => toggleSet(setActiveRating, v)}
          />
          <FacetGroup
            title="Source"
            items={Object.entries(facetCounts.sourceC).map(([label, count]) => ({ label, count }))}
            active={activeSource}
            onToggle={v => toggleSet(setActiveSource, v)}
          />
          <FacetGroup
            title="Health"
            items={(Object.keys(HEALTH_CHECK) as HealthFlag[]).map(label => ({ label, count: facetCounts.healthC[label] ?? 0 }))}
            active={activeHealth}
            onToggle={v => toggleSet(setActiveHealth, v)}
          />

          <div style={{ padding: '10px 12px', marginTop: 'auto' }}>
            <button
              type="button" onClick={clearAll} disabled={!hasActiveFilters}
              style={{
                width: '100%', padding: '6px 0', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
                background: 'none', border: '1px solid var(--lbb-border2)', cursor: hasActiveFilters ? 'pointer' : 'default',
                color: hasActiveFilters ? 'var(--lbb-fg2)' : 'var(--lbb-fg3)', opacity: hasActiveFilters ? 1 : 0.5,
              }}
            >
              Clear all filters
            </button>
          </div>
        </>}
      </aside>

      {/* ── Main pane ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>

        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '10px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
        }}>
          <Input
            icon="search"
            placeholder="Search LB#, location, description…"
            size="lg"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <IconButton
            icon="filter"
            title="Group by year"
            active={groupByYear}
            onClick={() => setGroupByYear(g => !g)}
          />
        </div>

        {/* Summary strip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
          padding: '5px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0, minHeight: 38,
        }}>
          <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)' }}>
            {sortedRows.length.toLocaleString()} results
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
            of {rows.length.toLocaleString()} in master DB
          </span>
          {filterChips.length > 0 && (
            <>
              <span style={{ width: 1, height: 14, background: 'var(--lbb-border)' }} />
              {filterChips.map((f, i) => <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />)}
            </>
          )}
          <div style={{ flex: 1 }} />
          {rows.length > 0 && (
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
              You own <strong style={{ color: 'var(--lbb-ok-fg)' }}>{Math.round((ownedCount / rows.length) * 100)}%</strong>
              {' · '}{(rows.length - ownedCount).toLocaleString()} to go
            </span>
          )}
        </div>

        {/* TODO-150 step 7: bulk action bar — checkbox multi-select parity with
            Collection's inline toolbar (Create torrent / Add to qBittorrent /
            Update location / Remove), batched over the checked rows. */}
        {checkedIds.size > 0 && (
          <BulkActionBar
            count={checkedIds.size}
            busy={actionBusy}
            onCreateTorrent={handleBulkCreateTorrent}
            onAddQbt={handleBulkAddQbt}
            onRelocate={handleBulkRelocate}
            onRemove={handleBulkRemove}
            onClear={() => setCheckedIds(new Set())}
          />
        )}

        {/* Table */}
        <div ref={tableParentRef} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 32 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 56 }} />
              <col style={{ width: 60 }} />
              <col style={{ width: 44 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH><input type="checkbox" checked={allChecked} onChange={toggleAllChecked} /></TH>
                <TH onClick={() => handleSort('lb')} sorted={sortKey === 'lb' ? sortDir : null}>LB#</TH>
                <TH>Status</TH>
                <TH onClick={() => handleSort('date')} sorted={sortKey === 'date' ? sortDir : null}>Date</TH>
                <TH>Location</TH>
                <TH align="center" onClick={() => handleSort('rating')} sorted={sortKey === 'rating' ? sortDir : null}>★</TH>
                <TH>Source</TH>
                <TH align="center">Own</TH>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const vItems    = virtualizer.getVirtualItems()
                const padTop    = vItems.length > 0 ? vItems[0].start : 0
                const padBottom = vItems.length > 0 ? virtualizer.getTotalSize() - vItems[vItems.length - 1].end : 0
                return (
                  <>
                    {padTop > 0 && <tr><td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} /></tr>}
                    {vItems.map(vItem => {
                      const item = flatItems[vItem.index]
                      if (!item) return null

                      if (item.kind === 'group') {
                        return (
                          <GroupRow
                            key={`g-${item.year}`}
                            label={item.year}
                            count={item.count}
                            expanded={!collapsedYears.has(item.year)}
                            onToggle={() => setCollapsedYears(prev => {
                              const n = new Set(prev)
                              n.has(item.year) ? n.delete(item.year) : n.add(item.year)
                              return n
                            })}
                            colSpan={colCount - 1}
                          />
                        )
                      }

                      const r = item.row
                      const isChecked = checkedIds.has(r.lbNumber)
                      return (
                        <TR
                          key={r.lb}
                          edge={statusTone(r.status)}
                          selected={r.lbNumber === selectedLb}
                          onClick={() => setSelectedLb(prev => prev === r.lbNumber ? null : r.lbNumber)}
                          onContextMenu={e => openCtxMenu(e, r.lb, buildRecordingActions(toRecAction(r), getCtxBatch(r), actionHandlers))}
                          style={{ height: vItem.size }}
                        >
                          <TD>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onClick={e => e.stopPropagation()}
                              onChange={e => toggleCheck(r.lbNumber, e.target.checked)}
                            />
                          </TD>
                          <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{r.lb}</TD>
                          <TD><Pill tone={statusTone(r.status)} soft>{r.status}</Pill></TD>
                          <TD mono>{r.date}</TD>
                          <TD>{r.loc}</TD>
                          <TD align="center">
                            {r.rating !== '—'
                              ? <Pill tone={ratingTone(r.rating)} soft>{r.rating}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                          </TD>
                          <TD>
                            {r.src
                              ? <Pill tone="mute" soft>{SRC_ABBR[r.src] ?? r.src}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                          </TD>
                          <TD align="center">
                            {r.owned
                              ? <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-fg)' }} />
                              : r.wish
                                ? <Icon name="star" size={12} style={{ color: 'var(--lbb-warn-fg)' }} />
                                : <Icon name="x" size={13} style={{ color: 'var(--lbb-bad-fg)' }} />}
                          </TD>
                        </TR>
                      )
                    })}
                    {padBottom > 0 && <tr><td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {loading && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
            }}>
              Loading…
            </div>
          )}

          {!loading && rows.length > 0 && sortedRows.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>Nothing matches</div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>Try adjusting your search or filters</div>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* TODO-150 step 8: detail panel — third column, only one row selected at a time. */}
      {selectedLb !== null && (() => {
        const selRow = rows.find(r => r.lbNumber === selectedLb)
        if (!selRow) return null
        return (
          <RecordingDetailPanel
            row={selRow}
            history={historyMap.get(selRow.lbNumber)}
            attachCount={attachCountMap.get(selRow.lbNumber)}
            actionHandlers={actionHandlers}
            openMenu={openCtxMenu}
            onClose={() => setSelectedLb(null)}
          />
        )
      })()}
      </div>
      {overlays}
    </div>
  )
}

// ── TODO-150 step 6: performance lens ───────────────────────────────────────
// Rows are shows (date + venue); each expands into its TapeMatch families,
// which expand into member recordings. Reuses the recording lens's already
// owned/wish/dup/fp-merged `rows` by lbNumber instead of re-deriving that
// merge — the only new fetches here are /api/library/performances (the
// show grouping itself) and /api/tapematch/families (per 07 §4/§5, merged
// client-side, never joined server-side). When no recording has a `fam`,
// every family collapses to one member — the no-families fallback in
// 03-data-contract.md falls out of this for free, no separate code path.

interface PerformanceRow {
  id: string
  date: string
  disp: string
  dow?: string
  year: number
  decade: string
  venue: string | null
  city: string | null
  tour?: string
  status: LibStatus
  // Absent (true) for ordinary lb_category='concert' shows. False only for
  // rows the backend inferred from a date+location-complete 'unknown' entry
  // that didn't match bobdylan_shows/dylan_performances — real performances
  // (often guest spots at other artists' shows) with no venue/setlist/tour
  // data to back them (TODO-151 audit, 2026-06-18).
  confirmed?: boolean
  tracks?: number
  setlist?: string
  title?: string
  recordings: RecordingRow[]
}

interface FamilyGroup {
  id: string
  members: RecordingRow[]
  label: string
  by: 'lb' | 'ai' | 'ai+lb'
  conf: number | null
  src: string | null
  bestRating: RatingGrade
  owned: boolean
  ownedCount: number
  total: number
  multi: boolean
  dupes: number
  canonical: RecordingRow | null
}

type Coverage = 'Covered' | 'Upgrade' | 'Gap' | 'Undocumented'

function bestOf(recs: RecordingRow[]): RecordingRow | null {
  return recs.reduce<RecordingRow | null>((b, r) =>
    (RATING_RANK[r.rating] ?? 0) > (RATING_RANK[b ? b.rating : '—'] ?? -1) ? r : b, null)
}

function familiesOf(recordings: RecordingRow[]): FamilyGroup[] {
  const groups = new Map<string, RecordingRow[]>()
  for (const r of recordings) {
    const key = r.fam || r.lb
    const arr = groups.get(key)
    if (arr) arr.push(r); else groups.set(key, [r])
  }
  const out: FamilyGroup[] = []
  for (const [key, members] of groups) {
    const best = bestOf(members)
    const owned = members.filter(r => r.owned)
    const bestOwned = bestOf(owned)
    const canonical = bestOwned || best
    const src = canonical ? canonical.src : (members[0]?.src ?? null)
    out.push({
      id: key, members,
      label: members[0]?.famLabel || (src ? (SOURCE_FULL[src] ?? src) : 'Recording'),
      by: members[0]?.famBy ?? 'lb',
      conf: members[0]?.famConf ?? null,
      src,
      bestRating: (best?.rating ?? '—') as RatingGrade,
      owned: owned.length > 0, ownedCount: owned.length, total: members.length,
      multi: members.length > 1,
      dupes: members.filter(r => r.dup).length,
      canonical,
    })
  }
  out.sort((a, b) =>
    (Number(b.owned) - Number(a.owned)) ||
    ((RATING_RANK[b.bestRating] ?? 0) - (RATING_RANK[a.bestRating] ?? 0)) ||
    (b.total - a.total))
  return out
}

function rollupOf(recordings: RecordingRow[]) {
  const owned = recordings.filter(r => r.owned)
  const best = bestOf(recordings)
  const fams = familiesOf(recordings)
  let coverage: Coverage
  if (recordings.length === 0) coverage = 'Undocumented'
  else if (owned.length === 0) coverage = 'Gap'
  else if (owned.length < recordings.length && best && !best.owned) coverage = 'Upgrade'
  else coverage = 'Covered'
  return {
    total: recordings.length, ownedCount: owned.length,
    famTotal: fams.length, famOwned: fams.filter(f => f.owned).length,
    bestRating: (best?.rating ?? '—') as RatingGrade,
    coverage, fams,
  }
}

function coverageTone(c: Coverage): 'ok' | 'warn' | 'mute' {
  if (c === 'Covered') return 'ok'
  if (c === 'Gap') return 'mute'
  return 'warn'
}

function coverageLabel(c: Coverage, ownedCount: number, total: number): string {
  if (c === 'Covered') return total > 1 ? `Owned ${ownedCount}/${total}` : 'Owned'
  if (c === 'Upgrade') return `Upgrade ${ownedCount}/${total}`
  if (c === 'Gap') return 'Gap'
  return 'No source'
}

type PerfFlatItem =
  | { kind: 'group'; year: string; count: number }
  | { kind: 'show'; perf: PerformanceRow }
  | { kind: 'fam'; perf: PerformanceRow; fam: FamilyGroup }
  | { kind: 'member'; perf: PerformanceRow; fam: FamilyGroup; rec: RecordingRow; isLast: boolean; isCanonical: boolean }

function PerformanceLensView({ rows, catalogLoading, actionHandlers, openCtxMenu, historyMap, attachCountMap }: {
  rows: RecordingRow[]
  catalogLoading: boolean
  actionHandlers: ActionHandlers
  openCtxMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  historyMap: Map<number, RowHistory>
  attachCountMap: Map<number, number>
}) {
  const [filterPaneOpen, setFilterPaneOpen] = useState(true)
  const [query, setQuery] = useState('')
  const [groupByYear, setGroupByYear] = useState(true)
  const [collapsedYears, setCollapsedYears] = useState<Set<string>>(new Set())
  const [expandedShows, setExpandedShows] = useState<Set<string>>(new Set())
  const [collapsedFams, setCollapsedFams] = useState<Set<string>>(new Set())
  // TODO-150 step 8: detail-panel selection. A show row opens the performance
  // panel; a member row opens that single recording's panel instead — mutually
  // exclusive, so selecting one clears the other.
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedMemberLb, setSelectedMemberLb] = useState<number | null>(null)

  const [activeDecade,   setActiveDecade]   = useState<Set<string>>(new Set())
  const [activeCoverage, setActiveCoverage] = useState<Set<Coverage>>(new Set())
  const [activeSource,   setActiveSource]   = useState<Set<string>>(new Set())
  const [activeRating,   setActiveRating]   = useState<Set<RatingGrade>>(new Set())

  const tableParentRef = useRef<HTMLDivElement>(null)

  const { data: perfData, isLoading: perfLoading } = useQuery({
    queryKey: ['library-performances'],
    queryFn: () => fetch(`${BASE}/api/library/performances`).then(r => r.json()),
    staleTime: Infinity,
  })
  // Same query key the performance adapter will keep reusing once family
  // confirmation UI exists — shares the cache rather than re-fetching.
  const { data: famData } = useQuery({
    queryKey: ['tapematch-families'],
    queryFn: () => fetch(`${BASE}/api/tapematch/families`).then(r => r.json()),
    staleTime: Infinity,
  })

  const rowsByLb = useMemo(() => {
    const m = new Map<number, RecordingRow>()
    for (const r of rows) m.set(r.lbNumber, r)
    return m
  }, [rows])

  const famMap = useMemo(() => {
    const m = new Map<number, { fam_id: string; fam_label: string; fam_conf: number | null; fam_by: string }>()
    if (Array.isArray(famData)) for (const f of famData as any[]) m.set(f.lb_number, f)
    return m
  }, [famData])

  const performances = useMemo<PerformanceRow[]>(() => {
    if (!Array.isArray(perfData)) return []
    return (perfData as any[]).map((p): PerformanceRow => {
      const recordings: RecordingRow[] = (p.recordings as any[]).map((stub): RecordingRow => {
        const base = rowsByLb.get(stub.lbNumber)
        const fam = famMap.get(stub.lbNumber)
        const row: RecordingRow = base ? { ...base } : {
          lb: stub.lb, lbNumber: stub.lbNumber, year: p.year ?? 0, decade: decadeOf(p.year ?? 0),
          date: p.date ?? '', loc: p.city ?? '', desc: '',
          rating: (VALID_RATINGS.has(stub.rating) ? stub.rating : '—') as RatingGrade,
          src: stub.src ?? null, status: (stub.status ?? 'Missing') as LibStatus,
          owned: false, wish: false, dup: false, xref: false, fp: false, unconf: false,
          folder: '', path: '', conf: '',
        }
        if (fam) {
          row.fam = fam.fam_id; row.famLabel = fam.fam_label
          row.famConf = fam.fam_conf; row.famBy = fam.fam_by as RecordingRow['famBy']
        }
        return row
      })
      return {
        id: p.id, date: p.date ?? '', disp: p.disp ?? p.date ?? '', dow: p.dow,
        year: p.year ?? 0, decade: decadeOf(p.year ?? 0),
        venue: p.venue ?? null, city: p.city ?? null, tour: p.tour,
        status: (p.status ?? 'Missing') as LibStatus,
        confirmed: p.confirmed,
        tracks: p.tracks, setlist: p.setlist, title: p.title,
        recordings,
      }
    })
  }, [perfData, rowsByLb, famMap])

  const facetCounts = useMemo(() => {
    const decadeC: Record<string, number> = {}
    const coverageC: Record<string, number> = {}
    const sourceC: Record<string, number> = {}
    const ratingC: Record<string, number> = {}
    for (const p of performances) {
      const ru = rollupOf(p.recordings)
      decadeC[p.decade] = (decadeC[p.decade] ?? 0) + 1
      coverageC[ru.coverage] = (coverageC[ru.coverage] ?? 0) + 1
      ratingC[ru.bestRating] = (ratingC[ru.bestRating] ?? 0) + 1
      const seen = new Set<string>()
      for (const r of p.recordings) {
        if (r.src && !seen.has(r.src)) { seen.add(r.src); sourceC[r.src] = (sourceC[r.src] ?? 0) + 1 }
      }
    }
    return { decadeC, coverageC, sourceC, ratingC }
  }, [performances])

  const filteredPerfs = useMemo(() => {
    const q = query.trim().toLowerCase()
    return performances.filter(p => {
      const ru = rollupOf(p.recordings)
      if (q) {
        const hay = `${p.disp} ${p.venue ?? ''} ${p.city ?? ''} ${p.tour ?? ''} ${p.title ?? ''} ${
          p.recordings.map(r => `${r.lb} ${r.desc}`).join(' ')}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (activeDecade.size > 0 && !activeDecade.has(p.decade)) return false
      if (activeCoverage.size > 0 && !activeCoverage.has(ru.coverage)) return false
      if (activeRating.size > 0 && !activeRating.has(ru.bestRating)) return false
      if (activeSource.size > 0 && !p.recordings.some(r => r.src && activeSource.has(r.src))) return false
      return true
    })
  }, [performances, query, activeDecade, activeCoverage, activeSource, activeRating])

  const sortedPerfs = useMemo(
    () => [...filteredPerfs].sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id)),
    [filteredPerfs],
  )

  const groupedByYear = useMemo(() => {
    if (!groupByYear) return null
    const map = new Map<string, PerformanceRow[]>()
    for (const p of sortedPerfs) {
      const key = p.year > 0 ? String(p.year) : 'Unknown'
      const arr = map.get(key)
      if (arr) arr.push(p); else map.set(key, [p])
    }
    return [...map.entries()].sort(([a], [b]) => {
      const an = a === 'Unknown' ? -1 : parseInt(a, 10)
      const bn = b === 'Unknown' ? -1 : parseInt(b, 10)
      return an - bn
    })
  }, [sortedPerfs, groupByYear])

  const flatItems = useMemo((): PerfFlatItem[] => {
    const items: PerfFlatItem[] = []
    const pushShow = (p: PerformanceRow) => {
      items.push({ kind: 'show', perf: p })
      if (!expandedShows.has(p.id)) return
      for (const fam of familiesOf(p.recordings)) {
        items.push({ kind: 'fam', perf: p, fam })
        if (fam.multi && !collapsedFams.has(`${p.id}::${fam.id}`)) {
          fam.members.forEach((rec, i) => {
            items.push({
              kind: 'member', perf: p, fam, rec,
              isLast: i === fam.members.length - 1, isCanonical: rec === fam.canonical,
            })
          })
        }
      }
    }
    if (groupByYear && groupedByYear) {
      for (const [year, perfs] of groupedByYear) {
        items.push({ kind: 'group', year, count: perfs.length })
        if (!collapsedYears.has(year)) for (const p of perfs) pushShow(p)
      }
    } else {
      for (const p of sortedPerfs) pushShow(p)
    }
    return items
  }, [groupByYear, groupedByYear, sortedPerfs, collapsedYears, expandedShows, collapsedFams])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: i => {
      const it = flatItems[i]
      if (!it) return 34
      if (it.kind === 'group') return 32
      if (it.kind === 'show') return 38
      if (it.kind === 'fam') return 30
      return 28
    },
    overscan: 12,
  })

  const colCount = 8 // edge + date + show + tour + families + recs + ★ + coverage

  const totalRecs = useMemo(() => filteredPerfs.reduce((n, p) => n + p.recordings.length, 0), [filteredPerfs])
  const totalFams = useMemo(() => filteredPerfs.reduce((n, p) => n + rollupOf(p.recordings).famTotal, 0), [filteredPerfs])
  const gapsShown = useMemo(() => filteredPerfs.filter(p => rollupOf(p.recordings).coverage === 'Gap').length, [filteredPerfs])

  const hasActiveFilters = activeDecade.size > 0 || activeCoverage.size > 0 || activeSource.size > 0 || activeRating.size > 0
  const clearAll = () => {
    setActiveDecade(new Set()); setActiveCoverage(new Set()); setActiveSource(new Set()); setActiveRating(new Set()); setQuery('')
  }
  const filterChips: Array<{ label: string; onRemove: () => void }> = [
    ...[...activeDecade].map(d => ({ label: `Decade: ${d}`, onRemove: () => toggleSet(setActiveDecade, d) })),
    ...[...activeCoverage].map(c => ({ label: `Coverage: ${c}`, onRemove: () => toggleSet(setActiveCoverage, c) })),
    ...[...activeSource].map(s => ({ label: `Source: ${s}`, onRemove: () => toggleSet(setActiveSource, s) })),
    ...[...activeRating].map(r => ({ label: `Rating: ${r}`, onRemove: () => toggleSet(setActiveRating, r) })),
  ]

  const loading = (catalogLoading || perfLoading) && performances.length === 0

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

      {/* ── Facet rail ──────────────────────────────────────────────────── */}
      <aside style={{
        width: filterPaneOpen ? 220 : 32, flexShrink: 0,
        borderRight: '1px solid var(--lbb-border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--lbb-surface2)',
        overflowY: filterPaneOpen ? 'auto' : 'hidden',
        overflowX: 'hidden',
        transition: 'width 180ms ease',
      }}>
        {!filterPaneOpen ? (
          <button type="button" title="Show filters" onClick={() => setFilterPaneOpen(true)} style={{
            margin: '8px auto', display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 24, height: 24, borderRadius: 4, flexShrink: 0,
            background: 'none', border: '1px solid var(--lbb-border2)', cursor: 'pointer', color: 'var(--lbb-fg3)',
          }}>
            <Icon name="chevRight" size={13} />
          </button>
        ) : (
          <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '6px 8px 0', flexShrink: 0 }}>
            <button type="button" title="Hide filters" onClick={() => setFilterPaneOpen(false)} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 22, height: 22, borderRadius: 4,
              background: 'none', border: '1px solid var(--lbb-border2)', cursor: 'pointer', color: 'var(--lbb-fg3)',
            }}>
              <Icon name="chevLeft" size={13} />
            </button>
          </div>
        )}

        {filterPaneOpen && <>
          <FacetGroup
            title="Decade"
            items={Object.entries(facetCounts.decadeC).sort(([a], [b]) => a.localeCompare(b)).map(([label, count]) => ({ label, count }))}
            active={activeDecade}
            onToggle={v => toggleSet(setActiveDecade, v)}
          />
          <FacetGroup
            title="Coverage"
            items={(['Covered', 'Upgrade', 'Gap', 'Undocumented'] as Coverage[]).map(label => ({ label, count: facetCounts.coverageC[label] ?? 0 }))}
            active={activeCoverage}
            onToggle={v => toggleSet(setActiveCoverage, v)}
          />
          <FacetGroup
            title="Source available"
            items={Object.entries(facetCounts.sourceC).map(([label, count]) => ({ label, count }))}
            active={activeSource}
            onToggle={v => toggleSet(setActiveSource, v)}
          />
          <FacetGroup
            title="Best rating"
            items={Object.entries(facetCounts.ratingC).map(([label, count]) => ({ label: label as RatingGrade, count }))}
            active={activeRating}
            onToggle={v => toggleSet(setActiveRating, v)}
          />

          <div style={{ padding: '10px 12px', marginTop: 'auto' }}>
            <button
              type="button" onClick={clearAll} disabled={!hasActiveFilters && !query}
              style={{
                width: '100%', padding: '6px 0', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
                background: 'none', border: '1px solid var(--lbb-border2)',
                cursor: (hasActiveFilters || query) ? 'pointer' : 'default',
                color: (hasActiveFilters || query) ? 'var(--lbb-fg2)' : 'var(--lbb-fg3)', opacity: (hasActiveFilters || query) ? 1 : 0.5,
              }}
            >
              Clear all filters
            </button>
          </div>
        </>}
      </aside>

      {/* ── Main pane ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>

        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '10px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
        }}>
          <Input
            icon="search"
            placeholder="Search date, venue, city, tour, LB#…"
            size="lg"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <IconButton icon="filter" title="Group by year" active={groupByYear} onClick={() => setGroupByYear(g => !g)} />
        </div>

        {/* Summary strip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
          padding: '5px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0, minHeight: 38,
        }}>
          <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg)' }}>
            {filteredPerfs.length.toLocaleString()} show{filteredPerfs.length === 1 ? '' : 's'}
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
            · {totalRecs.toLocaleString()} recordings
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--lbb-info-fg)', fontWeight: 600, fontSize: 'var(--lbb-fs-12)' }}>
            <Icon name="tapematch" size={12} /> {totalFams.toLocaleString()} {totalFams === 1 ? 'family' : 'families'}
          </span>
          {gapsShown > 0 && (
            <span style={{ color: 'var(--lbb-warn-fg)', fontWeight: 600, fontSize: 'var(--lbb-fs-12)' }}>
              · {gapsShown.toLocaleString()} gap{gapsShown === 1 ? '' : 's'}
            </span>
          )}
          {filterChips.length > 0 && (
            <>
              <span style={{ width: 1, height: 14, background: 'var(--lbb-border)' }} />
              {filterChips.map((f, i) => <ActiveFilter key={i} label={f.label} onRemove={f.onRemove} />)}
            </>
          )}
        </div>

        {/* Table */}
        <div ref={tableParentRef} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 96 }} />
              <col />
              <col style={{ width: 150 }} />
              <col style={{ width: 200 }} />
              <col style={{ width: 56 }} />
              <col style={{ width: 56 }} />
              <col style={{ width: 140 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH>Date</TH>
                <TH>Show</TH>
                <TH>Tour</TH>
                <TH>Families</TH>
                <TH align="center">Recs</TH>
                <TH align="center">★</TH>
                <TH>Coverage</TH>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const vItems    = virtualizer.getVirtualItems()
                const padTop    = vItems.length > 0 ? vItems[0].start : 0
                const padBottom = vItems.length > 0 ? virtualizer.getTotalSize() - vItems[vItems.length - 1].end : 0
                return (
                  <>
                    {padTop > 0 && <tr><td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} /></tr>}
                    {vItems.map(vItem => {
                      const item = flatItems[vItem.index]
                      if (!item) return null

                      if (item.kind === 'group') {
                        return (
                          <GroupRow
                            key={`g-${item.year}`}
                            label={item.year}
                            count={item.count}
                            expanded={!collapsedYears.has(item.year)}
                            onToggle={() => setCollapsedYears(prev => {
                              const n = new Set(prev)
                              n.has(item.year) ? n.delete(item.year) : n.add(item.year)
                              return n
                            })}
                            colSpan={colCount - 1}
                          />
                        )
                      }

                      if (item.kind === 'show') {
                        const p = item.perf
                        const ru = rollupOf(p.recordings)
                        const multi = p.recordings.length > 1
                        const expanded = expandedShows.has(p.id)
                        const canonical = bestOf(p.recordings)
                        return (
                          <TR
                            key={p.id}
                            edge={p.status === 'Missing' ? 'warn' : statusTone(p.status)}
                            selected={selectedId === p.id && selectedMemberLb === null}
                            onClick={() => {
                              setSelectedId(p.id)
                              setSelectedMemberLb(null)
                              if (multi) setExpandedShows(s => {
                                const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n
                              })
                            }}
                            onContextMenu={e => openCtxMenu(
                              e, p.disp,
                              buildPerformanceActions(p.recordings.map(toRecAction), canonical ? toRecAction(canonical) : null, actionHandlers),
                            )}
                            style={{ height: vItem.size }}
                          >
                            <TD
                              onClick={e => {
                                e.stopPropagation()
                                if (!multi) return
                                setExpandedShows(s => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })
                              }}
                              style={{ overflow: 'visible', cursor: multi ? 'pointer' : 'default' }}
                            >
                              {multi && <Icon name={expanded ? 'chevDown' : 'chevRight'} size={13} style={{ color: 'var(--lbb-fg3)' }} />}
                            </TD>
                            <TD mono style={{ color: 'var(--lbb-fg)', fontWeight: 600 }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.2 }}>
                                <span>{p.disp}</span>
                                {p.dow && (
                                  <span style={{ fontSize: 'var(--lbb-fs-9-5)', color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                    {p.dow}
                                  </span>
                                )}
                              </span>
                            </TD>
                            <TD style={{ color: 'var(--lbb-fg)' }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.25, minWidth: 0 }}>
                                <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {p.venue || p.city || '—'}
                                  {p.title && (
                                    <span style={{ marginLeft: 6, fontWeight: 500, fontStyle: 'italic', color: 'var(--lbb-accent-mid)', fontSize: 'var(--lbb-fs-11-5)' }}>
                                      "{p.title}"
                                    </span>
                                  )}
                                  {p.confirmed === false && (
                                    <span title="Inferred from the recording's own date/location — not matched to a known Dylan show date">
                                      <Pill tone="mute" soft style={{ marginLeft: 6, fontSize: 'var(--lbb-fs-9-5)' }}>
                                        Unconfirmed
                                      </Pill>
                                    </span>
                                  )}
                                </span>
                                {p.venue && p.city && (
                                  <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {p.city}
                                  </span>
                                )}
                              </span>
                            </TD>
                            <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>{p.tour ?? ''}</TD>
                            <TD style={{ overflow: 'visible' }}>
                              <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
                                {ru.fams.map(fam => (
                                  <Pill key={fam.id} tone={fam.owned ? 'ok' : 'mute'} soft>
                                    {fam.src ? (SRC_ABBR[fam.src] ?? fam.src) : '—'}{fam.multi ? ` ×${fam.total}` : ''}
                                  </Pill>
                                ))}
                              </span>
                            </TD>
                            <TD align="center" mono style={{ color: multi ? 'var(--lbb-fg)' : 'var(--lbb-fg3)', fontWeight: multi ? 700 : 500 }}>
                              <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.1, alignItems: 'center' }}>
                                <span>{ru.famTotal}</span>
                                <span style={{ fontSize: 'var(--lbb-fs-9)', fontWeight: 500, color: 'var(--lbb-fg3)' }}>{ru.total} rec</span>
                              </span>
                            </TD>
                            <TD align="center">
                              {ru.bestRating !== '—'
                                ? <Pill tone={ratingTone(ru.bestRating)} soft>{ru.bestRating}</Pill>
                                : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </TD>
                            <TD style={{ overflow: 'visible' }}>
                              <Pill tone={coverageTone(ru.coverage)} soft dot={ru.coverage === 'Covered'}>
                                {coverageLabel(ru.coverage, ru.ownedCount, ru.total)}
                              </Pill>
                            </TD>
                          </TR>
                        )
                      }

                      if (item.kind === 'fam') {
                        const { fam } = item
                        const single = !fam.multi
                        const lone = fam.members[0]
                        return (
                          <tr
                            key={`f-${item.perf.id}-${fam.id}`}
                            onClick={() => { setSelectedId(item.perf.id); setSelectedMemberLb(null) }}
                            style={{
                              height: vItem.size, cursor: 'pointer',
                              background: fam.owned
                                ? 'color-mix(in srgb, var(--lbb-ok-bg) 26%, transparent)'
                                : 'color-mix(in srgb, var(--lbb-surface2) 55%, transparent)',
                            }}
                          >
                            <td style={{ width: 3, padding: 0, background: fam.owned ? 'var(--lbb-ok-bar)' : 'var(--lbb-border2)', borderBottom: '1px solid var(--lbb-border)' }} />
                            <td
                              onClick={e => { e.stopPropagation(); if (fam.multi) setCollapsedFams(s => { const n = new Set(s); const k = `${item.perf.id}::${fam.id}`; n.has(k) ? n.delete(k) : n.add(k); return n }) }}
                              style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center', cursor: fam.multi ? 'pointer' : 'default' }}
                            >
                              {fam.multi && (
                                <Icon
                                  name={collapsedFams.has(`${item.perf.id}::${fam.id}`) ? 'chevRight' : 'chevDown'}
                                  size={12} style={{ color: 'var(--lbb-fg3)' }}
                                />
                              )}
                            </td>
                            <td colSpan={3} style={{ borderBottom: '1px solid var(--lbb-border)', padding: '4px 10px', overflow: 'hidden' }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, maxWidth: '100%' }}>
                                <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', flex: '0 0 auto' }}>
                                  {fam.multi ? '├' : '└'}
                                </span>
                                <Pill tone={fam.owned ? 'ok' : 'mute'} soft>{fam.src ? (SRC_ABBR[fam.src] ?? fam.src) : '—'}</Pill>
                                <span style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 700, color: 'var(--lbb-fg)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: '0 1 auto', minWidth: 0 }}>
                                  {fam.label}
                                </span>
                                {single && (
                                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', fontWeight: 600, color: fam.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>
                                    {lone?.lb}
                                  </span>
                                )}
                                {fam.dupes > 0 && <Pill tone="mute" soft>{fam.dupes} dup</Pill>}
                              </span>
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
                              {fam.multi ? `×${fam.total}` : ''}
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', textAlign: 'center' }}>
                              {fam.bestRating !== '—'
                                ? <Pill tone={ratingTone(fam.bestRating)} soft>{fam.bestRating}</Pill>
                                : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                            </td>
                            <td style={{ borderBottom: '1px solid var(--lbb-border)', padding: '0 var(--lbb-d-pad)', overflow: 'visible' }}>
                              {fam.owned
                                ? (fam.ownedCount < fam.total
                                    ? <Pill tone="ok" soft dot>Own {fam.ownedCount}/{fam.total}</Pill>
                                    : <Pill tone="ok" soft dot>Owned</Pill>)
                                : (lone?.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>)}
                            </td>
                          </tr>
                        )
                      }

                      // member
                      const { rec, isLast, isCanonical } = item
                      return (
                        <tr
                          key={`m-${item.perf.id}-${item.fam.id}-${rec.lb}`}
                          onClick={() => { setSelectedMemberLb(rec.lbNumber); setSelectedId(null) }}
                          onContextMenu={e => openCtxMenu(e, rec.lb, buildRecordingActions(toRecAction(rec), [], actionHandlers))}
                          style={{
                            height: vItem.size, cursor: 'pointer',
                            background: selectedMemberLb === rec.lbNumber
                              ? 'var(--lbb-accent-soft)'
                              : 'color-mix(in srgb, var(--lbb-surface2) 35%, transparent)',
                          }}
                        >
                          <td style={{ width: 3, padding: 0, background: rec.owned ? 'var(--lbb-ok-bar)' : 'transparent', borderBottom: '1px solid var(--lbb-border)' }} />
                          <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                          <TD mono dim style={{ paddingLeft: 22 }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ color: 'var(--lbb-fg3)' }}>{isLast ? '└' : '├'}</span>
                              <span style={{ color: rec.owned ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)', fontWeight: 600 }}>{rec.lb}</span>
                            </span>
                          </TD>
                          <TD dim style={{ fontSize: 'var(--lbb-fs-11-5)' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                              {isCanonical && <Pill tone="info" soft>Best</Pill>}
                              {rec.dup && <Pill tone="mute" soft>dup</Pill>}
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rec.desc}</span>
                            </span>
                          </TD>
                          <TD dim style={{ fontSize: 'var(--lbb-fs-11)' }}>{rec.src ? (SOURCE_FULL[rec.src] ?? rec.src) : '—'}</TD>
                          <td style={{ borderBottom: '1px solid var(--lbb-border)' }} />
                          <TD align="center">
                            {rec.rating !== '—'
                              ? <Pill tone={ratingTone(rec.rating)} soft>{rec.rating}</Pill>
                              : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
                          </TD>
                          <TD style={{ overflow: 'visible' }}>
                            {rec.owned ? <Pill tone="ok" soft dot>Owned</Pill>
                              : rec.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>}
                          </TD>
                        </tr>
                      )
                    })}
                    {padBottom > 0 && <tr><td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {loading && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '50%', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
            }}>
              Loading…
            </div>
          )}

          {!loading && performances.length > 0 && filteredPerfs.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              height: '50%', gap: 12, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="search" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>Nothing matches</div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>Try adjusting your search or filters</div>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* TODO-150 step 8: detail panel — member-row selection wins over show
          selection (mutually exclusive, enforced where each is set above). */}
      {selectedMemberLb !== null ? (() => {
        const rec = rowsByLb.get(selectedMemberLb)
        if (!rec) return null
        return (
          <RecordingDetailPanel
            row={rec}
            history={historyMap.get(rec.lbNumber)}
            attachCount={attachCountMap.get(rec.lbNumber)}
            actionHandlers={actionHandlers}
            openMenu={openCtxMenu}
            onClose={() => setSelectedMemberLb(null)}
          />
        )
      })() : selectedId !== null ? (() => {
        const perf = performances.find(p => p.id === selectedId)
        if (!perf) return null
        const canonical = bestOf(perf.recordings)
        return (
          <PerformanceDetailPanel
            perf={perf}
            recordings={perf.recordings}
            canonical={canonical}
            history={canonical ? historyMap.get(canonical.lbNumber) : undefined}
            attachCount={canonical ? attachCountMap.get(canonical.lbNumber) : undefined}
            actionHandlers={actionHandlers}
            openMenu={openCtxMenu}
            onClose={() => setSelectedId(null)}
          />
        )
      })() : null}
    </div>
  )
}
