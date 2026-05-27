import React, { useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type CollectionStatus = 'Public' | 'Private' | 'New' | 'Missing'
type FilterKey = 'all' | 'missing' | 'wishlist' | 'duplicates' | 'forum' | 'torrent' | 'unconfirmed' | 'nofp'
type HistoryTab = 'torrents' | 'forum'

interface HistoryItem {
  date: string
  filename: string
  kind: 'In qBt' | 'Local'
}

interface CollectionRow {
  lbNumber: string
  status: CollectionStatus
  date: string
  location: string
  folder: string
  diskPath: string
  confirmed: string
  fingerprinted: boolean
  title: string
  discs: number
  size: string
  rating: string
  wishlist: boolean
  isDuplicate: boolean
  historyTorrents: HistoryItem[]
  historyForum: HistoryItem[]
}

// ── Sample data ───────────────────────────────────────────────────────────────

const SAMPLE_DATA: CollectionRow[] = [
  {
    lbNumber: 'LB-00018', status: 'Public', date: '06/29/81',
    location: "Earl's Court, London, UK",
    folder: 'LB-00018 1981-06-29 Earls Court London',
    diskPath: '/media/dylan/archive', confirmed: '2024-03-15',
    fingerprinted: true, title: "Earl's Court Night 1", discs: 2,
    size: '1.4 GB', rating: 'A', wishlist: false, isDuplicate: false,
    historyTorrents: [{ date: '2024-01-10', filename: 'LB-00018.torrent', kind: 'In qBt' }],
    historyForum: [{ date: '2024-01-12', filename: 'Post #8821', kind: 'Local' }],
  },
  {
    lbNumber: 'LB-00042', status: 'Public', date: '05/26/66',
    location: 'Royal Albert Hall, London, UK',
    folder: 'LB-00042 1966-05-26 Royal Albert Hall London',
    diskPath: '/media/dylan/archive', confirmed: '2024-02-01',
    fingerprinted: true, title: 'Royal Albert Hall 1966', discs: 2,
    size: '890 MB', rating: 'A+', wishlist: false, isDuplicate: false,
    historyTorrents: [{ date: '2023-12-01', filename: 'LB-00042.torrent', kind: 'Local' }],
    historyForum: [],
  },
  {
    lbNumber: 'LB-01001', status: 'New', date: '08/31/70',
    location: 'Isle of Wight Festival, UK',
    folder: 'LB-01001 1970-08-31 Isle of Wight',
    diskPath: '/media/dylan/imports', confirmed: '',
    fingerprinted: false, title: 'Isle of Wight 1970', discs: 1,
    size: '620 MB', rating: 'B+', wishlist: false, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-05421', status: 'Public', date: '01/30/74',
    location: 'Madison Square Garden, New York, NY',
    folder: 'LB-05421 1974-01-30 Madison Square Garden',
    diskPath: '/media/dylan/archive', confirmed: '2024-01-05',
    fingerprinted: true, title: 'Before The Flood Night 1', discs: 2,
    size: '1.8 GB', rating: 'A', wishlist: false, isDuplicate: true,
    historyTorrents: [{ date: '2024-01-05', filename: 'LB-05421.torrent', kind: 'In qBt' }],
    historyForum: [{ date: '2024-01-06', filename: 'Post #4521', kind: 'Local' }],
  },
  {
    lbNumber: 'LB-05422', status: 'Missing', date: '02/03/74',
    location: 'Forum, Los Angeles, CA',
    folder: '', diskPath: '', confirmed: '',
    fingerprinted: false, title: 'Before The Flood Night 2', discs: 2,
    size: '', rating: '', wishlist: true, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-07800', status: 'Public', date: '09/22/87',
    location: 'Beacon Theatre, New York, NY',
    folder: 'LB-07800 1987-09-22 Beacon Theatre New York',
    diskPath: '/media/dylan/archive', confirmed: '2023-11-30',
    fingerprinted: true, title: 'Temples In Flames', discs: 2,
    size: '1.2 GB', rating: 'A−', wishlist: false, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-09100', status: 'New', date: '10/16/92',
    location: 'Supper Club, New York, NY',
    folder: 'LB-09100 1992-10-16 Supper Club New York',
    diskPath: '/media/dylan/imports', confirmed: '',
    fingerprinted: false, title: 'Supper Club Sessions', discs: 1,
    size: '780 MB', rating: '', wishlist: false, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-11234', status: 'Public', date: '08/05/65',
    location: 'Forest Hills Stadium, New York, NY',
    folder: 'LB-11234 1965-08-05 Forest Hills Stadium New York',
    diskPath: '/media/dylan/archive', confirmed: '2024-03-01',
    fingerprinted: true, title: 'Forest Hills Electric Set', discs: 1,
    size: '450 MB', rating: 'A', wishlist: false, isDuplicate: false,
    historyTorrents: [{ date: '2024-03-01', filename: 'LB-11234.torrent', kind: 'Local' }],
    historyForum: [],
  },
  {
    lbNumber: 'LB-13005', status: 'Missing', date: '07/xx/66',
    location: 'unknown', folder: '', diskPath: '', confirmed: '',
    fingerprinted: false, title: 'Unknown 1966 Show', discs: 1,
    size: '', rating: '', wishlist: true, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-15967', status: 'Public', date: '04/12/19',
    location: 'Paramount Theatre, Oakland, CA',
    folder: 'LB-15967 2019-04-12 Paramount Theatre Oakland',
    diskPath: '/media/dylan/archive', confirmed: 'yesterday',
    fingerprinted: true, title: 'Paramount Theatre 2019', discs: 2,
    size: '2.1 GB', rating: 'B+', wishlist: false, isDuplicate: false,
    historyTorrents: [], historyForum: [],
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function edgeFor(status: CollectionStatus): 'ok' | 'info' | 'warn' | 'mute' {
  if (status === 'Public')  return 'ok'
  if (status === 'New')     return 'info'
  if (status === 'Missing') return 'warn'
  return 'mute'
}

// ── Detail panel ──────────────────────────────────────────────────────────────

interface DetailPanelProps {
  row: CollectionRow
  historyTab: HistoryTab
  onHistoryTab: (t: HistoryTab) => void
  onClose: () => void
}

function DetailPanel({ row, historyTab, onHistoryTab, onClose }: DetailPanelProps): React.JSX.Element {
  const historyItems = historyTab === 'torrents' ? row.historyTorrents : row.historyForum
  const edge = edgeFor(row.status)

  const META_ROWS: [string, React.ReactNode][] = [
    ['Folder',        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>{row.folder || '—'}</span>],
    ['Disk path',     <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg3)' }}>{row.diskPath || '—'}</span>],
    ['Size',          <span style={{ fontFamily: 'var(--lbb-mono)' }}>{row.size || '—'}</span>],
    ['Confirmed',     <span style={{ fontFamily: 'var(--lbb-mono)' }}>{row.confirmed || '—'}</span>],
    ['Fingerprinted', row.fingerprinted
      ? <Pill tone="ok" soft>Yes · acoustid</Pill>
      : <Pill tone="mute" soft>No</Pill>],
    ['Rating',        row.rating
      ? <Pill tone="ok" soft>{row.rating}</Pill>
      : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>],
  ]

  return (
    <div style={{
      borderLeft: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column',
      overflowY: 'auto', minHeight: 0,
      background: 'var(--lbb-surface)',
    }}>
      {/* close button */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        padding: '6px 10px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <IconButton icon="x" size={14} title="Close detail" onClick={onClose} />
      </div>

      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* 1. Pill row */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Pill tone="ok" soft dot>Owned</Pill>
          <Pill tone={edge} soft>{row.status}</Pill>
          <Pill tone="mute" soft>FLAC · 16/44</Pill>
        </div>

        {/* 2. ID + title block */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{
            fontSize: 16, fontWeight: 700,
            fontFamily: 'var(--lbb-mono)',
            color: 'var(--lbb-accent-mid)',
          }}>
            {row.lbNumber}
          </span>
          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {row.title || row.folder || '—'}
          </span>
          <span style={{ fontSize: 12, color: 'var(--lbb-fg2)' }}>
            {row.date} · {row.location}
            {row.discs > 0 ? ` · ${row.discs} CD${row.discs !== 1 ? 's' : ''}` : ''}
          </span>
        </div>

        {/* 3. Meta grid */}
        <div style={{
          background: 'var(--lbb-surface2)',
          border: '1px solid var(--lbb-border)',
          borderRadius: 6, padding: '10px 12px',
          display: 'grid',
          gridTemplateColumns: '80px 1fr',
          rowGap: 7, columnGap: 8,
          fontSize: 11.5,
        }}>
          {META_ROWS.map(([label, value]) => (
            <React.Fragment key={label}>
              <span style={{ color: 'var(--lbb-fg3)', fontWeight: 600, alignSelf: 'center' }}>
                {label}
              </span>
              <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', alignSelf: 'center' }}>
                {value}
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* 4. Action buttons */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Button variant="secondary" size="sm" icon="reveal">Reveal on disk</Button>
          <Button variant="ghost" size="sm">Attachments</Button>
          <Button variant="ghost" size="sm">Spectrograms</Button>
          <Button variant="ghost" size="sm">On map</Button>
        </div>

        {/* 5. History */}
        <div>
          <div style={{
            fontSize: 11, fontWeight: 700, color: 'var(--lbb-fg3)',
            letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
          }}>
            History
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <Chip
              active={historyTab === 'torrents'} size="sm"
              onClick={() => onHistoryTab('torrents')}
              count={row.historyTorrents.length}
            >Torrents</Chip>
            <Chip
              active={historyTab === 'forum'} size="sm"
              onClick={() => onHistoryTab('forum')}
              count={row.historyForum.length}
            >Forum posts</Chip>
          </div>
          {historyItems.length === 0 ? (
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', padding: '6px 0' }}>
              No {historyTab === 'torrents' ? 'torrent' : 'forum'} history.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {historyItems.map((item, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 8px',
                  border: '1px solid var(--lbb-border)',
                  borderRadius: 4, fontSize: 11.5,
                }}>
                  <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', flexShrink: 0, fontSize: 11 }}>
                    {item.date}
                  </span>
                  <span style={{
                    fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg)',
                    flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11,
                  }}>
                    {item.filename}
                  </span>
                  <Pill tone={item.kind === 'In qBt' ? 'info' : 'mute'} soft>
                    {item.kind}
                  </Pill>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <Button variant="ghost" size="sm">Regenerate</Button>
            <Button variant="ghost" size="sm">Post to forum</Button>
          </div>
        </div>

      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenCollection(): React.JSX.Element {
  const [rows, setRows] = useState<CollectionRow[]>([])
  const [filter, setFilter] = useState<FilterKey>('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [historyTab, setHistoryTab] = useState<HistoryTab>('torrents')

  const tableParentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const STATUS_MAP: Record<string, CollectionStatus> = {
      public: 'Public', private: 'Private', missing: 'Missing',
    }

    Promise.allSettled([
      fetch(`${BASE}/api/collection`).then(r => r.json()),
      fetch(`${BASE}/api/fingerprint/lb_numbers`).then(r => r.json()),
      fetch(`${BASE}/api/wishlist`).then(r => r.json()),
      fetch(`${BASE}/api/collection/duplicates`).then(r => r.json()),
      fetch(`${BASE}/api/forum_posts`).then(r => r.json()),
      fetch(`${BASE}/api/torrents`).then(r => r.json()),
    ]).then(([collRes, fpRes, wlRes, dupRes, forumRes, torrentRes]) => {
      if (collRes.status === 'rejected' || !Array.isArray(collRes.value)) {
        setRows(SAMPLE_DATA)
        return
      }

      const fpMap: Record<string, number> =
        fpRes.status === 'fulfilled' && fpRes.value && !fpRes.value.error
          ? fpRes.value : {}

      const wishlistSet = new Set<number>(
        wlRes.status === 'fulfilled' && Array.isArray(wlRes.value)
          ? wlRes.value.map((w: any) => w.lb_number as number)
          : []
      )

      const dupSet = new Set<number>()
      if (dupRes.status === 'fulfilled' && Array.isArray(dupRes.value)) {
        for (const group of dupRes.value) {
          if (Array.isArray(group.owned) && group.owned.length > 1) {
            for (const o of group.owned) dupSet.add(o.lb_number as number)
          }
        }
      }

      const forumByLb: Record<number, any[]> = {}
      if (forumRes.status === 'fulfilled' && Array.isArray(forumRes.value)) {
        for (const p of forumRes.value) {
          ;(forumByLb[p.lb_number] ??= []).push(p)
        }
      }

      const torrentByLb: Record<number, any[]> = {}
      if (torrentRes.status === 'fulfilled' && Array.isArray(torrentRes.value)) {
        for (const t of torrentRes.value) {
          ;(torrentByLb[t.lb_number] ??= []).push(t)
        }
      }

      const merged: CollectionRow[] = (collRes.value as any[]).map((c: any) => {
        const lb: number = c.lb_number
        return {
          lbNumber: `LB-${String(lb).padStart(5, '0')}`,
          status: STATUS_MAP[c.lb_status] ?? 'New',
          date: c.date_str ?? '',
          location: c.location ?? '',
          folder: c.folder_name ?? '',
          diskPath: c.disk_path ?? '',
          confirmed: c.confirmed_at ?? '',
          fingerprinted: (fpMap[String(lb)] ?? 0) > 0,
          title: c.description ?? '',
          discs: parseInt(c.cdr ?? '0') || 0,
          size: '',
          rating: c.rating ?? '',
          wishlist: wishlistSet.has(lb),
          isDuplicate: dupSet.has(lb),
          historyTorrents: (torrentByLb[lb] ?? []).map((t: any) => ({
            date: (t.created_at ?? '').slice(0, 10),
            filename: t.torrent_path ? (t.torrent_path as string).split('/').pop() ?? '' : '',
            kind: t.added_to_qbt ? 'In qBt' : 'Local',
          })),
          historyForum: (forumByLb[lb] ?? []).map((p: any) => ({
            date: (p.posted_at ?? '').slice(0, 10),
            filename: p.subject ?? '',
            kind: 'Local',
          })),
        }
      })

      setRows(merged)
    }).catch(() => setRows(SAMPLE_DATA))
  }, [])

  // ── Derived ────────────────────────────────────────────────────────────────

  const counts = {
    all:         rows.length,
    missing:     rows.filter(r => r.status === 'Missing').length,
    wishlist:    rows.filter(r => r.wishlist).length,
    duplicates:  rows.filter(r => r.isDuplicate).length,
    forum:       rows.filter(r => r.historyForum.length > 0).length,
    torrent:     rows.filter(r => r.historyTorrents.length > 0).length,
    unconfirmed: rows.filter(r => !r.confirmed).length,
    nofp:        rows.filter(r => !r.fingerprinted).length,
  }

  const confirmedCount     = rows.filter(r => r.confirmed).length
  const fingerprintedCount = rows.filter(r => r.fingerprinted).length

  const filteredRows = rows.filter(r => {
    switch (filter) {
      case 'missing':     return r.status === 'Missing'
      case 'wishlist':    return r.wishlist
      case 'duplicates':  return r.isDuplicate
      case 'forum':       return r.historyForum.length > 0
      case 'torrent':     return r.historyTorrents.length > 0
      case 'unconfirmed': return !r.confirmed
      case 'nofp':        return !r.fingerprinted
      default:            return true
    }
  }).filter(r => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      r.lbNumber.toLowerCase().includes(q) ||
      r.location.toLowerCase().includes(q) ||
      r.folder.toLowerCase().includes(q) ||
      r.date.includes(q)
    )
  })

  const selectedRow = selectedId ? (filteredRows.find(r => r.lbNumber === selectedId) ?? null) : null

  const virtualizer = useVirtualizer({
    count: filteredRows.length,
    getScrollElement: () => tableParentRef.current,
    estimateSize: () => 36,
    overscan: 12,
  })

  // ── Checkbox helpers ───────────────────────────────────────────────────────

  const toggleCheck = (id: string, checked: boolean) => {
    setCheckedIds(prev => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const allChecked = filteredRows.length > 0 && filteredRows.every(r => checkedIds.has(r.lbNumber))
  const toggleAll = () => {
    if (allChecked) {
      setCheckedIds(prev => {
        const next = new Set(prev)
        filteredRows.forEach(r => next.delete(r.lbNumber))
        return next
      })
    } else {
      setCheckedIds(prev => {
        const next = new Set(prev)
        filteredRows.forEach(r => next.add(r.lbNumber))
        return next
      })
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const sep = (
    <span style={{ width: 1, height: 16, background: 'var(--lbb-border)', margin: '0 4px', flexShrink: 0 }} />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* ── Heading row ───────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 20px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--lbb-fg)', lineHeight: 1.2 }}>
            My Collection
          </h1>
          <span style={{ fontSize: 13, color: 'var(--lbb-fg3)' }}>
            {rows.length.toLocaleString()} items · across 4 mounts
          </span>
        </div>
        <div style={{ flex: 1 }} />
        <Button variant="ghost"     size="sm" icon="download">Export HTML</Button>
        <Button variant="ghost"     size="sm" icon="download">Export M3U</Button>
        <Button variant="secondary" size="sm">Create torrent</Button>
        <Button variant="primary"   size="sm" icon="plus">Add to qBittorrent</Button>
      </div>

      {/* ── Filter chips row ──────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '8px 16px', borderBottom: '1px solid var(--lbb-border)',
        flexWrap: 'wrap', flexShrink: 0,
      }}>
        <Chip active={filter === 'all'}        onClick={() => setFilter('all')}        count={counts.all}>All</Chip>
        <Chip active={filter === 'missing'}    onClick={() => setFilter('missing')}    count={counts.missing}>Missing</Chip>
        <Chip active={filter === 'wishlist'}   onClick={() => setFilter('wishlist')}   count={counts.wishlist}>Wishlist</Chip>
        <Chip active={filter === 'duplicates'} onClick={() => setFilter('duplicates')} count={counts.duplicates}>Duplicates</Chip>
        <Chip active={filter === 'forum'}      onClick={() => setFilter('forum')}      count={counts.forum}>Forum history</Chip>
        <Chip active={filter === 'torrent'}    onClick={() => setFilter('torrent')}    count={counts.torrent}>Torrent history</Chip>
        {sep}
        <Chip active={filter === 'unconfirmed'} onClick={() => setFilter('unconfirmed')} count={counts.unconfirmed}>Unconfirmed</Chip>
        <Chip active={filter === 'nofp'}        onClick={() => setFilter('nofp')}        count={counts.nofp}>No fingerprint</Chip>
        <div style={{ flex: 1 }} />
        <Input
          icon="filter"
          placeholder="Filter collection…"
          size="sm"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 240 }}
        />
        <Button variant="ghost" size="sm" iconRight="chevDown">All years</Button>
        <label style={{
          fontSize: 11.5, color: 'var(--lbb-fg2)',
          display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer',
        }}>
          <input type="checkbox" style={{ margin: 0 }} />
          Xref only
        </label>
      </div>

      {/* ── Inline action toolbar ─────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 16px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <Button variant="secondary" size="sm" icon="folderPlus">Add single folder</Button>
        <Button variant="secondary" size="sm" icon="search">Scan directory</Button>
        <Button variant="secondary" size="sm" icon="folder">Scan tree…</Button>
        {sep}
        <Button variant="ghost"  size="sm">Update location</Button>
        <Button variant="danger" size="sm" icon="trash">Remove</Button>
        <div style={{ flex: 1 }} />
        <span style={{
          fontSize: 11.5, color: 'var(--lbb-fg3)',
          fontFamily: 'var(--lbb-mono)',
        }}>
          {confirmedCount.toLocaleString()} confirmed · {fingerprintedCount.toLocaleString()} fingerprinted
        </span>
      </div>

      {/* ── Main content: table + detail panel ───────────────────────────────── */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'grid',
        gridTemplateColumns: selectedRow ? '1fr 360px' : '1fr',
      }}>

        {/* Table */}
        <div ref={tableParentRef} style={{ overflow: 'auto', minHeight: 0, position: 'relative' }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 240 }} />
              <col style={{ width: 200 }} />
              <col style={{ width: 160 }} />
              <col style={{ width: 40 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH>
                  <input
                    type="checkbox"
                    checked={allChecked}
                    onChange={toggleAll}
                  />
                </TH>
                <TH>LB#</TH>
                <TH>Status</TH>
                <TH>Date</TH>
                <TH>Location</TH>
                <TH>Folder</TH>
                <TH>Disk path</TH>
                <TH>Confirmed</TH>
                <TH align="center">FP</TH>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const items = virtualizer.getVirtualItems()
                const padTop    = items.length > 0 ? items[0].start : 0
                const padBottom = items.length > 0
                  ? virtualizer.getTotalSize() - items[items.length - 1].end
                  : 0
                return (
                  <>
                    {padTop > 0 && (
                      <tr><td colSpan={10} style={{ height: padTop, padding: 0, border: 0 }} /></tr>
                    )}
                    {items.map(vItem => {
                      const r = filteredRows[vItem.index]
                      if (!r) return null
                      const isSelected = selectedId === r.lbNumber
                      const isChecked  = checkedIds.has(r.lbNumber)
                      return (
                        <TR
                          key={r.lbNumber}
                          edge={edgeFor(r.status)}
                          selected={isSelected}
                          onClick={() => setSelectedId(isSelected ? null : r.lbNumber)}
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
                          <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>
                            {r.lbNumber}
                          </TD>
                          <TD>
                            <Pill tone={edgeFor(r.status)} soft dot>{r.status}</Pill>
                          </TD>
                          <TD mono>{r.date}</TD>
                          <TD>{r.location}</TD>
                          <TD mono>{r.folder || '—'}</TD>
                          <TD mono dim>{r.diskPath || '—'}</TD>
                          <TD mono dim>{r.confirmed || '—'}</TD>
                          <TD align="center">
                            {r.fingerprinted
                              ? <Icon name="check" size={14} style={{ color: 'var(--lbb-ok-fg)' }} />
                              : <Icon name="x"     size={14} style={{ color: 'var(--lbb-bad-fg)' }} />
                            }
                          </TD>
                        </TR>
                      )
                    })}
                    {padBottom > 0 && (
                      <tr><td colSpan={10} style={{ height: padBottom, padding: 0, border: 0 }} /></tr>
                    )}
                  </>
                )
              })()}
            </tbody>
          </TableShell>

          {/* Empty state */}
          {rows.length === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              height: '60%', gap: 12,
              color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
            }}>
              <Icon name="collection" size={40} style={{ opacity: 0.2 }} />
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                  No recordings in your collection
                </div>
                <div style={{ fontSize: 11.5, marginTop: 4 }}>
                  Use "Add single folder" to get started
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selectedRow && (
          <DetailPanel
            row={selectedRow}
            historyTab={historyTab}
            onHistoryTab={setHistoryTab}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>

    </div>
  )
}
