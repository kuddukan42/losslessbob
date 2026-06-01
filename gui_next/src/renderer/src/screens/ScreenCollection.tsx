import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { TableShell, TH, TR, TD, GroupRow } from '../components'
import { useLookupStore } from '../lib/lookupStore'
import { useSpectrogramStore } from '../lib/spectrogramStore'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

type CollectionStatus = 'Public' | 'Private' | 'New' | 'Missing'
type FilterKey = 'all' | 'missing' | 'wishlist' | 'duplicates' | 'forum' | 'torrent' | 'unconfirmed' | 'nofp' | 'not_owned' | 'forum_global' | 'torrent_global'

interface MissingLbRow {
  lb_number: number
  date_str: string
  location: string
  rating: string
  description: string
  lb_status: string
}
type HistoryTab = 'torrents' | 'forum'
type ToastTone = 'ok' | 'bad' | 'info'

interface HistoryItem {
  date: string
  filename: string
  kind: 'In qBt' | 'Local'
}

interface TorrentRecord {
  id: number
  date: string
  filename: string
  source_folder: string
  torrent_path: string
  source_folder_exists: boolean
  torrent_file_exists: boolean
  added_to_qbt: boolean
}

interface GlobalForumPost {
  id: number
  lb_number: number
  lbStr: string
  subject: string
  topic_url: string
  posted_at: string
  date_str: string
  location: string
}

interface GlobalTorrentRecord {
  id: number
  lb_number: number
  lbStr: string
  filename: string
  source_folder: string
  torrent_path: string
  created_at: string
  added_to_qbt: boolean
  source_folder_exists: boolean
  torrent_file_exists: boolean
  date_str: string
  location: string
}

interface DetailForumRecord {
  id: number
  subject: string
  topic_url: string
  posted_at: string
}

interface CollectionRow {
  lbNumber: string
  lbNumberInt: number
  status: CollectionStatus
  date: string
  location: string
  folder: string
  diskPath: string
  notes: string
  confirmed: string
  fingerprinted: boolean
  title: string
  discs: number
  size: string
  rating: string
  wishlist: boolean
  wishlistPriority: number | null
  wishlistNotes: string
  wishlistAddedAt: string
  isDuplicate: boolean
  isXref: boolean
  historyTorrents: HistoryItem[]
  historyForum: HistoryItem[]
}

interface DuplicateGroup {
  date_str: string
  location: string
  owned: { lb_number: number; rating: string; description: string }[]
  unowned: { lb_number: number; rating: string; description: string }[]
}

// ── Sample data (fallback when backend returns nothing) ───────────────────────

const SAMPLE_DATA: CollectionRow[] = [
  {
    lbNumber: 'LB-00018', lbNumberInt: 18, status: 'Public', date: '06/29/81',
    location: "Earl's Court, London, UK",
    folder: 'LB-00018 1981-06-29 Earls Court London',
    diskPath: '/media/dylan/archive/LB-00018 1981-06-29 Earls Court London',
    notes: '', confirmed: '2024-03-15', fingerprinted: true, title: "Earl's Court Night 1",
    discs: 2, size: '1.4 GB', rating: 'A', wishlist: false, wishlistPriority: null, wishlistNotes: '', wishlistAddedAt: '',
    isDuplicate: false, isXref: false,
    historyTorrents: [{ date: '2024-01-10', filename: 'LB-00018.torrent', kind: 'In qBt' }],
    historyForum: [{ date: '2024-01-12', filename: 'Post #8821', kind: 'Local' }],
  },
  {
    lbNumber: 'LB-00042', lbNumberInt: 42, status: 'Public', date: '05/26/66',
    location: 'Royal Albert Hall, London, UK',
    folder: 'LB-00042 1966-05-26 Royal Albert Hall London',
    diskPath: '/media/dylan/archive/LB-00042 1966-05-26 Royal Albert Hall London',
    notes: '', confirmed: '2024-02-01', fingerprinted: true, title: 'Royal Albert Hall 1966',
    discs: 2, size: '890 MB', rating: 'A+', wishlist: false, wishlistPriority: null, wishlistNotes: '', wishlistAddedAt: '',
    isDuplicate: false, isXref: true,
    historyTorrents: [{ date: '2023-12-01', filename: 'LB-00042.torrent', kind: 'Local' }],
    historyForum: [],
  },
  {
    lbNumber: 'LB-01001', lbNumberInt: 1001, status: 'New', date: '08/31/70',
    location: 'Isle of Wight Festival, UK',
    folder: 'LB-01001 1970-08-31 Isle of Wight',
    diskPath: '/media/dylan/imports/LB-01001 1970-08-31 Isle of Wight',
    notes: '', confirmed: '', fingerprinted: false, title: 'Isle of Wight 1970',
    discs: 1, size: '620 MB', rating: 'B+', wishlist: false, wishlistPriority: null, wishlistNotes: '', wishlistAddedAt: '',
    isDuplicate: false, isXref: false,
    historyTorrents: [], historyForum: [],
  },
  {
    lbNumber: 'LB-05421', lbNumberInt: 5421, status: 'Public', date: '01/30/74',
    location: 'Madison Square Garden, New York, NY',
    folder: 'LB-05421 1974-01-30 Madison Square Garden',
    diskPath: '/media/dylan/archive/LB-05421 1974-01-30 Madison Square Garden',
    notes: '', confirmed: '2024-01-05', fingerprinted: true, title: 'Before The Flood Night 1',
    discs: 2, size: '1.8 GB', rating: 'A', wishlist: false, wishlistPriority: null, wishlistNotes: '', wishlistAddedAt: '',
    isDuplicate: true, isXref: false,
    historyTorrents: [{ date: '2024-01-05', filename: 'LB-05421.torrent', kind: 'In qBt' }],
    historyForum: [{ date: '2024-01-06', filename: 'Post #4521', kind: 'Local' }],
  },
  {
    lbNumber: 'LB-05422', lbNumberInt: 5422, status: 'Missing', date: '02/03/74',
    location: 'Forum, Los Angeles, CA', folder: '', diskPath: '', notes: '', confirmed: '',
    fingerprinted: false, title: 'Before The Flood Night 2',
    discs: 2, size: '', rating: '', wishlist: true, wishlistPriority: 3, wishlistNotes: '', wishlistAddedAt: '2024-01-01',
    isDuplicate: false, isXref: false,
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

function extractYear(dateStr: string): number | null {
  const parts = dateStr.split('/')
  if (parts.length < 3) return null
  const y = parseInt(parts[parts.length - 1].trim(), 10)
  if (isNaN(y)) return null
  return y < 100 ? (y >= 49 ? 1900 + y : 2000 + y) : y
}

function blobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ msg, tone, onDone }: { msg: string; tone: ToastTone; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])

  const bg     = tone === 'ok'  ? 'var(--lbb-ok-bg)'   : tone === 'bad' ? 'var(--lbb-err-bg)'  : 'var(--lbb-surface2)'
  const border = tone === 'ok'  ? 'var(--lbb-ok-bar)'  : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-border2)'
  const color  = tone === 'ok'  ? 'var(--lbb-ok-fg)'   : tone === 'bad' ? 'var(--lbb-err-fg)'  : 'var(--lbb-fg)'

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 999,
      background: bg, border: `1px solid ${border}`, borderRadius: 8,
      padding: '10px 16px', color, fontSize: 'var(--lbb-fs-13)', fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.15)', maxWidth: 400,
    }}>
      {msg}
    </div>
  )
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────────

function ConfirmDialog({ title, body, onConfirm, onCancel }: {
  title: string; body: string; onConfirm: () => void; onCancel: () => void
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 440, width: '90%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 8 }}>{title}</div>
        <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', marginBottom: 20, lineHeight: 1.5 }}>{body}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onCancel}>{t('common.cancel')}</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>{t('common.confirm')}</Button>
        </div>
      </div>
    </div>
  )
}

// ── ContextMenu ───────────────────────────────────────────────────────────────

interface CtxMenuState {
  x: number
  y: number
  row: CollectionRow
}

interface CtxMenuItem {
  label: string
  disabled?: boolean
  danger?: boolean
  action: () => void
}

function ContextMenu({ state, onClose, items }: {
  state: CtxMenuState
  onClose: () => void
  items: (CtxMenuItem | 'sep')[]
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const down = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', down)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', down)
      document.removeEventListener('keydown', key)
    }
  }, [onClose])

  const menuW = 216
  const left = Math.min(state.x, window.innerWidth  - menuW - 8)
  const top  = Math.min(state.y, window.innerHeight - 320  - 8)

  return (
    <div ref={ref} style={{
      position: 'fixed', left, top, zIndex: 2000,
      background: 'var(--lbb-surface)',
      border: '1px solid var(--lbb-border)',
      borderRadius: 8, padding: '4px 0',
      minWidth: menuW,
      boxShadow: '0 8px 24px rgba(0,0,0,0.22)',
      fontSize: 'var(--lbb-fs-13)',
    }}>
      {items.map((item, i) => {
        if (item === 'sep') {
          return <div key={`sep-${i}`} style={{ height: 1, background: 'var(--lbb-border)', margin: '3px 0' }} />
        }
        return (
          <button
            key={item.label}
            disabled={item.disabled}
            onClick={() => { if (!item.disabled) { item.action(); onClose() } }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '6px 14px', fontSize: 'var(--lbb-fs-13)', border: 'none',
              cursor: item.disabled ? 'default' : 'pointer',
              background: 'transparent',
              color: item.disabled
                ? 'var(--lbb-fg3)'
                : item.danger ? 'var(--lbb-err-fg)' : 'var(--lbb-fg)',
            }}
            onMouseEnter={e => {
              if (!item.disabled) (e.currentTarget as HTMLElement).style.background = 'var(--lbb-accent-bg)'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.background = 'transparent'
            }}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

// ── PersonalInfoModal ─────────────────────────────────────────────────────────

function PersonalInfoModal({ lb, lbNumber, onClose, onSaved }: {
  lb: string
  lbNumber: number
  onClose: () => void
  onSaved: (msg: string) => void
}) {
  const { t } = useTranslation()
  const [rating, setRating] = useState<number | null>(null)
  const [tags,   setTags]   = useState('')
  const [busy,   setBusy]   = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetch(`${BASE}/api/collection/${lbNumber}/meta`)
      .then(r => r.json())
      .then(d => {
        setRating(d.personal_rating ?? null)
        setTags(d.tags ?? '')
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
  }, [lbNumber])

  const handleSave = async () => {
    setBusy(true)
    try {
      await fetch(`${BASE}/api/collection/${lbNumber}/meta`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personal_rating: rating, tags: tags.trim() || null }),
      })
      onSaved(t('collection.toast.savedPersonalInfo', { lb }))
      onClose()
    } catch {
      setBusy(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, minWidth: 340, maxWidth: 420,
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 16 }}>
          {t('collection.personalInfo.title', { lb })}
        </div>

        {!loaded ? (
          <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg3)', padding: '12px 0' }}>Loading…</div>
        ) : (
          <>
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg2)', marginBottom: 6 }}>
                {t('collection.personalInfo.rating')}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {[1, 2, 3, 4, 5].map(n => (
                  <button
                    key={n}
                    onClick={() => setRating(rating === n ? null : n)}
                    style={{
                      width: 32, height: 32, borderRadius: 6, border: '1px solid var(--lbb-border)',
                      background: rating === n ? 'var(--lbb-accent-mid)' : 'var(--lbb-surface2)',
                      color: rating === n ? '#fff' : 'var(--lbb-fg)',
                      cursor: 'pointer', fontSize: 'var(--lbb-fs-13)', fontWeight: 600,
                    }}
                  >{n}</button>
                ))}
                {rating !== null && (
                  <button
                    onClick={() => setRating(null)}
                    style={{
                      padding: '0 8px', height: 32, borderRadius: 6,
                      border: '1px solid var(--lbb-border)',
                      background: 'var(--lbb-surface2)',
                      color: 'var(--lbb-fg3)', cursor: 'pointer', fontSize: 'var(--lbb-fs-11-5)',
                    }}
                  >Clear</button>
                )}
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg2)', marginBottom: 6 }}>
                {t('collection.personalInfo.tags')}
              </div>
              <input
                type="text"
                value={tags}
                onChange={e => setTags(e.target.value)}
                placeholder={t('collection.personalInfo.tagsPlaceholder')}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '7px 10px', fontSize: 'var(--lbb-fs-13)',
                  background: 'var(--lbb-surface2)',
                  border: '1px solid var(--lbb-border)',
                  borderRadius: 6, color: 'var(--lbb-fg)',
                  outline: 'none',
                }}
              />
            </div>
          </>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" disabled={!loaded || busy} onClick={handleSave}>
            {busy ? t('collection.personalInfo.saving') : t('common.save')}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── ScanEntry type ────────────────────────────────────────────────────────────

interface ScanEntry {
  lb_number: number
  folder_name: string
  path: string
}

// ── ScanPreviewModal ──────────────────────────────────────────────────────────

type ScanRowState = 'idle' | 'adding' | 'done' | 'error'

function ScanPreviewModal({ entries, skipped, onClose, onAdded }: {
  entries: ScanEntry[]
  skipped: number
  onClose: () => void
  onAdded: () => void
}) {
  const { t } = useTranslation()
  const [ownedSet, setOwnedSet]     = useState<Set<number>>(new Set())
  const [ownedLoaded, setOwnedLoaded] = useState(false)
  const [rowState, setRowState]     = useState<Record<number, ScanRowState>>({})
  const [busy, setBusy]             = useState(false)

  useEffect(() => {
    fetch(`${BASE}/api/collection/lb_numbers`)
      .then(r => r.json())
      .then((data: number[]) => { setOwnedSet(new Set(data)); setOwnedLoaded(true) })
      .catch(() => setOwnedLoaded(true))
  }, [])

  const addEntry = async (e: ScanEntry) => {
    setRowState(prev => ({ ...prev, [e.lb_number]: 'adding' }))
    try {
      const resp = await fetch(`${BASE}/api/collection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: e.lb_number, folder_name: e.folder_name, disk_path: e.path }),
      })
      const data = await resp.json()
      setRowState(prev => ({ ...prev, [e.lb_number]: data.ok ? 'done' : 'error' }))
      if (data.ok) onAdded()
    } catch {
      setRowState(prev => ({ ...prev, [e.lb_number]: 'error' }))
    }
  }

  const pendingEntries = entries.filter(e =>
    !ownedSet.has(e.lb_number) && (rowState[e.lb_number] ?? 'idle') === 'idle'
  )

  const addAll = async () => {
    setBusy(true)
    for (const e of pendingEntries) await addEntry(e)
    setBusy(false)
  }

  const lbStr = (n: number) => `LB-${String(n).padStart(5, '0')}`

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, width: 860, maxWidth: '96vw',
        maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexShrink: 0 }}>
          <span style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('collection.scanPreview.title', { count: entries.length })}
            {skipped > 0 && <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 400, color: 'var(--lbb-fg3)', marginLeft: 8 }}>{t('collection.scanPreview.skipped', { count: skipped })}</span>}
          </span>
          <IconButton icon="x" size={14} title="Close" onClick={onClose} />
        </div>

        <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 260 }} />
              <col />
              <col style={{ width: 110 }} />
              <col style={{ width: 80 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH>LB#</TH>
                <TH>Folder</TH>
                <TH>Path</TH>
                <TH align="center">{t('collection.scanPreview.alreadyOwned')}</TH>
                <TH />
              </tr>
            </thead>
            <tbody>
              {entries.map(e => {
                const isOwned = ownedLoaded && ownedSet.has(e.lb_number)
                const state   = rowState[e.lb_number] ?? 'idle'
                return (
                  <TR key={e.lb_number}>
                    <TD />
                    <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{lbStr(e.lb_number)}</TD>
                    <TD mono>{e.folder_name}</TD>
                    <TD mono dim style={{ fontSize: 'var(--lbb-fs-10)' }}>{e.path}</TD>
                    <TD align="center">
                      {!ownedLoaded
                        ? <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>…</span>
                        : isOwned
                          ? <Pill tone="ok" soft>Yes</Pill>
                          : <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11-5)' }}>No</span>
                      }
                    </TD>
                    <TD>
                      <Button
                        variant={state === 'done' ? 'ghost' : 'secondary'} size="sm"
                        disabled={isOwned || state === 'done' || state === 'adding'}
                        onClick={() => addEntry(e)}
                      >
                        {state === 'done' ? '✓' : state === 'adding' ? '…' : state === 'error' ? 'Retry' : 'Add'}
                      </Button>
                    </TD>
                  </TR>
                )
              })}
            </tbody>
          </TableShell>
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14, flexShrink: 0 }}>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.close')}</Button>
          <Button
            variant="primary" size="sm"
            disabled={!ownedLoaded || busy || pendingEntries.length === 0}
            onClick={addAll}
          >
            {busy ? t('collection.scanPreview.adding') : t('collection.scanPreview.addAll', { count: pendingEntries.length })}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── AddFolderModal ─────────────────────────────────────────────────────────────

interface FolderEntry {
  path: string
  lbInput: string
  folderNameInput: string
  notesInput: string
  status: 'idle' | 'adding' | 'done' | 'error'
  errorMsg?: string
}

function AddFolderModal({ paths, onClose, onAdded }: {
  paths: string[]
  onClose: () => void
  onAdded: () => void
}) {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<FolderEntry[]>(
    () => paths.map(p => ({
      path: p,
      lbInput: '',
      folderNameInput: p.replace(/\/+$/, '').split('/').pop() || p,
      notesInput: '',
      status: 'idle' as const,
    }))
  )

  const updateLb = (idx: number, val: string) =>
    setEntries(prev => prev.map((e, i) => i === idx ? { ...e, lbInput: val } : e))

  const updateFolderName = (idx: number, val: string) =>
    setEntries(prev => prev.map((e, i) => i === idx ? { ...e, folderNameInput: val } : e))

  const updateNotes = (idx: number, val: string) =>
    setEntries(prev => prev.map((e, i) => i === idx ? { ...e, notesInput: val } : e))

  const addOne = async (idx: number) => {
    // Read current lbInput/path before marking 'adding'
    const snap = entries[idx]
    const lb = parseInt(snap.lbInput, 10)
    if (isNaN(lb) || lb <= 0 || snap.status !== 'idle') return

    const folderName = snap.folderNameInput.trim() || snap.path.replace(/\/+$/, '').split('/').pop() || snap.path
    setEntries(prev => prev.map((r, i) => i === idx ? { ...r, status: 'adding' } : r))

    try {
      const resp = await fetch(`${BASE}/api/collection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lb_number: lb, folder_name: folderName, disk_path: snap.path,
          ...(snap.notesInput.trim() ? { notes: snap.notesInput.trim() } : {}),
        }),
      })
      const data = await resp.json()
      setEntries(prev => prev.map((r, i) =>
        i === idx ? { ...r, status: data.ok ? 'done' : 'error', errorMsg: data.error } : r
      ))
      if (data.ok) onAdded()
    } catch (err) {
      setEntries(prev => prev.map((r, i) =>
        i === idx ? { ...r, status: 'error', errorMsg: String(err) } : r
      ))
    }
  }

  const pendingCount = entries.filter(e => e.status === 'idle' && /^\d+$/.test(e.lbInput)).length

  const addAll = async () => {
    for (let i = 0; i < entries.length; i++) {
      const e = entries[i]
      if (e.status === 'idle' && /^\d+$/.test(e.lbInput)) {
        const lb = parseInt(e.lbInput, 10)
        if (lb <= 0) continue
        const folderName = e.folderNameInput.trim() || e.path.replace(/\/+$/, '').split('/').pop() || e.path
        setEntries(prev => prev.map((r, j) => j === i ? { ...r, status: 'adding' } : r))
        try {
          const resp = await fetch(`${BASE}/api/collection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              lb_number: lb, folder_name: folderName, disk_path: e.path,
              ...(e.notesInput.trim() ? { notes: e.notesInput.trim() } : {}),
            }),
          })
          const data = await resp.json()
          setEntries(prev => prev.map((r, j) =>
            j === i ? { ...r, status: data.ok ? 'done' : 'error', errorMsg: data.error } : r
          ))
          if (data.ok) onAdded()
        } catch (err) {
          setEntries(prev => prev.map((r, j) =>
            j === i ? { ...r, status: 'error', errorMsg: String(err) } : r
          ))
        }
      }
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, width: 700, maxWidth: '95vw',
        maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('collection.addFolder.title', { count: entries.length })}
          </span>
          <IconButton icon="x" size={14} title="Close" onClick={onClose} />
        </div>

        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginBottom: 10 }}>
          {t('collection.addFolder.instruction')}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 5, paddingRight: 2 }}>
          {entries.map((e, idx) => {
            const isDone = e.status === 'done'
            const isErr  = e.status === 'error'
            const isBusy = e.status === 'adding'
            const inputStyle = {
              height: 28, padding: '0 8px',
              fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
              borderRadius: 5, color: 'var(--lbb-fg)', outline: 'none',
            }
            return (
              <div key={idx} style={{
                display: 'flex', flexDirection: 'column', gap: 5,
                padding: '8px 10px',
                background: isDone ? 'var(--lbb-ok-bg)' : isErr ? 'var(--lbb-err-bg)' : 'var(--lbb-surface2)',
                border: `1px solid ${isDone ? 'var(--lbb-ok-bar)' : isErr ? 'var(--lbb-err-bar)' : 'var(--lbb-border)'}`,
                borderRadius: 6,
              }}>
                {/* disk path display */}
                <div style={{
                  fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {e.path}
                </div>
                {/* row: folder name input | LB# | Add */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    placeholder={t('collection.addFolder.folderName')}
                    value={e.folderNameInput}
                    disabled={isDone || isBusy}
                    onChange={ev => updateFolderName(idx, ev.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <input
                    type="number"
                    placeholder={t('collection.addFolder.lbNumber')}
                    value={e.lbInput}
                    disabled={isDone || isBusy}
                    onChange={ev => updateLb(idx, ev.target.value)}
                    style={{ ...inputStyle, width: 80 }}
                  />
                  <Button
                    variant={isDone ? 'ghost' : 'secondary'} size="sm"
                    disabled={isDone || isBusy || !/^\d+$/.test(e.lbInput)}
                    onClick={() => addOne(idx)}
                  >
                    {isDone ? t('collection.addFolder.added') : isBusy ? '…' : t('common.add')}
                  </Button>
                </div>
                {/* notes input */}
                <input
                  placeholder={t('collection.addFolder.notes')}
                  value={e.notesInput}
                  disabled={isDone || isBusy}
                  onChange={ev => updateNotes(idx, ev.target.value)}
                  style={{ ...inputStyle, width: '100%' }}
                />
                {isErr && (
                  <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-err-fg)' }}>
                    {e.errorMsg || 'Failed to add'}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14, flexShrink: 0 }}>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.close')}</Button>
          <Button
            variant="primary" size="sm"
            disabled={pendingCount === 0}
            onClick={addAll}
          >
            {t('collection.addFolder.addAll', { count: pendingCount })}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── ForumModal ─────────────────────────────────────────────────────────────────

function ForumModal({ lb, subject: initSubject, body: initBody, onClose, onPosted }: {
  lb: number
  subject: string
  body: string
  onClose: () => void
  onPosted: (topicUrl: string) => void
}) {
  const { t } = useTranslation()
  const [subject, setSubject] = useState(initSubject)
  const [body, setBody]       = useState(initBody)
  const [busy, setBusy]       = useState(false)
  const [err, setErr]         = useState<string | null>(null)

  const handlePost = async () => {
    setBusy(true); setErr(null)
    try {
      const resp = await fetch(`${BASE}/api/entry/${lb}/post_forum`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, body }),
      })
      const data = await resp.json()
      if (data.ok) {
        onPosted(data.topic_url ?? '')
        onClose()
      } else {
        setErr(data.error || 'Post failed')
      }
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, width: 640, maxWidth: '95vw',
        maxHeight: '85vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)' }}>{t('collection.forum.modalTitle')}</span>
          <IconButton icon="x" size={14} title="Close" onClick={onClose} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <div>
            <label style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', display: 'block', marginBottom: 4 }}>
              {t('collection.forum.subject')}
            </label>
            <input
              value={subject}
              onChange={e => setSubject(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                height: 30, padding: '0 10px', fontSize: 'var(--lbb-fs-12-5)',
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
                borderRadius: 6, color: 'var(--lbb-fg)', outline: 'none',
              }}
            />
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <label style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--lbb-fg3)', display: 'block', marginBottom: 4 }}>
              {t('collection.forum.body')}
            </label>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              style={{
                flex: 1, minHeight: 200, resize: 'vertical',
                padding: '8px 10px', fontSize: 'var(--lbb-fs-11-5)',
                fontFamily: 'var(--lbb-mono)',
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
                borderRadius: 6, color: 'var(--lbb-fg)', outline: 'none',
                lineHeight: 1.5,
              }}
            />
          </div>
          {err && (
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-err-fg)', background: 'var(--lbb-err-bg)', padding: '6px 10px', borderRadius: 5 }}>
              {err}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14, flexShrink: 0 }}>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" disabled={busy} onClick={handlePost}>
            {busy ? t('collection.forum.posting') : t('collection.forum.postTopic')}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Detail panel ──────────────────────────────────────────────────────────────

interface PersonalMeta {
  personal_rating: number | null
  listen_count: number
  last_listened: string | null
}

interface DetailPanelProps {
  row: CollectionRow
  historyTab: HistoryTab
  onHistoryTab: (t: HistoryTab) => void
  onClose: () => void
  onReveal: (path: string) => void
  onRegenTorrent: (lb: number, path: string) => void
  onPostForum: (lb: number) => void
  onWishlistToggle: (lb: number, currentlyOn: boolean) => void
  onPersonalInfo: (lb: string, lbNumber: number) => void
  personalMetaVersion: number
  onToast: (msg: string, tone: ToastTone) => void
  onRefetch: () => void
  onSpectrograms: (row: CollectionRow) => void
  onNavigate: (path: string) => void
}

interface AudioInfo {
  format: string | null
  bit_depth: number | null
  sample_rate: number | null
  mixed: boolean
  files_probed: number
  offline?: boolean
}

function DetailPanel({ row, historyTab, onHistoryTab, onClose, onReveal, onRegenTorrent, onPostForum, onWishlistToggle, onPersonalInfo, personalMetaVersion, onToast, onRefetch, onSpectrograms, onNavigate }: DetailPanelProps): React.JSX.Element {
  const { t } = useTranslation()
  const edge = edgeFor(row.status)

  const [personalMeta, setPersonalMeta] = useState<PersonalMeta | null>(null)
  const [logListenBusy, setLogListenBusy] = useState(false)
  const [torrentRecords, setTorrentRecords] = useState<TorrentRecord[]>([])
  const [torrentBusy, setTorrentBusy] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [forumRecords, setForumRecords] = useState<DetailForumRecord[]>([])
  const [forumBusy, setForumBusy] = useState(true)
  const [forumError, setForumError] = useState(false)
  const [forumDeleteConfirm, setForumDeleteConfirm] = useState<number | null>(null)
  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null)

  const fetchTorrentRecords = useCallback(() => {
    setTorrentBusy(true)
    fetch(`${BASE}/api/torrent/${row.lbNumberInt}`)
      .then(r => r.json())
      .then((data: any) => {
        if (Array.isArray(data)) {
          const records = data.map((t: any) => ({
            id: t.id,
            date: (t.created_at ?? '').slice(0, 10),
            filename: t.torrent_path ? (t.torrent_path as string).split('/').pop() ?? '' : '',
            source_folder: t.source_folder ?? '',
            torrent_path: t.torrent_path ?? '',
            source_folder_exists: !!t.source_folder_exists,
            torrent_file_exists: !!t.torrent_file_exists,
            added_to_qbt: !!t.added_to_qbt,
          }))
          setTorrentRecords(records)
          // Silently sync DB flag for records the DB thinks are in qBittorrent
          const qbtRecords = records.filter(r => r.added_to_qbt)
          if (qbtRecords.length > 0) {
            Promise.all(
              qbtRecords.map(r =>
                fetch(`${BASE}/api/torrent/${r.id}/qbt_check`)
                  .then(res => res.json())
                  .catch(() => null)
              )
            ).then(results => {
              const syncedIds = new Set(
                qbtRecords
                  .filter((_, i) => results[i]?.synced)
                  .map(r => r.id)
              )
              if (syncedIds.size > 0) {
                setTorrentRecords(prev =>
                  prev.map(r => syncedIds.has(r.id) ? { ...r, added_to_qbt: false } : r)
                )
              }
            })
          }
        }
      })
      .catch(() => {})
      .finally(() => setTorrentBusy(false))
  }, [row.lbNumberInt])

  useEffect(() => {
    setTorrentRecords([])
    fetchTorrentRecords()
  }, [fetchTorrentRecords])

  const fetchForumRecords = useCallback(() => {
    setForumBusy(true)
    setForumError(false)
    fetch(`${BASE}/api/entry/${row.lbNumberInt}/forum_posts`)
      .then(r => r.json())
      .then((data: any) => {
        if (Array.isArray(data)) {
          setForumRecords(data.map((p: any) => ({
            id: p.id,
            subject: p.subject ?? '',
            topic_url: p.topic_url ?? '',
            posted_at: (p.posted_at ?? '').slice(0, 10),
          })))
        } else {
          setForumError(true)
        }
      })
      .catch(() => setForumError(true))
      .finally(() => setForumBusy(false))
  }, [row.lbNumberInt])

  useEffect(() => {
    setForumRecords([])
    fetchForumRecords()
  }, [fetchForumRecords])

  const handleTorrentAddQbt = async (rec: TorrentRecord) => {
    try {
      const resp = await fetch(`${BASE}/api/qbt/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ torrent_id: rec.id }),
      })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.addedToQbt') : (data.error || t('collection.toast.qbtAddFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) { fetchTorrentRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.qbtRequestFailed'), 'bad') }
  }

  const handleTorrentQbtRemove = async (rec: TorrentRecord) => {
    try {
      const resp = await fetch(`${BASE}/api/torrent/${rec.id}/qbt_remove`, { method: 'POST' })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.removedFromQbt') : (data.error || t('collection.toast.qbtRemoveFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) { fetchTorrentRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.qbtRequestFailed'), 'bad') }
  }

  const handleTorrentRegen = async (rec: TorrentRecord) => {
    if (!rec.source_folder) { onToast(t('collection.toast.noSourceFolder'), 'info'); return }
    try {
      const resp = await fetch(`${BASE}/api/torrent/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: row.lbNumberInt, source_folder: rec.source_folder }),
      })
      const data = await resp.json()
      onToast(
        data.ok ? t('collection.toast.torrentRegenerated', { name: data.name ?? '' }) : (data.error || t('collection.toast.torrentFailed')),
        data.ok ? 'ok' : 'bad',
      )
      if (data.ok) { fetchTorrentRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.torrentCreationFailed'), 'bad') }
  }

  const handleForumOpen = (rec: DetailForumRecord) => {
    if (!rec.topic_url) { onToast(t('collection.toast.noUrlStored'), 'info'); return }
    window.open(rec.topic_url, '_blank')
  }

  const handleForumRecordDelete = async (postId: number) => {
    setForumDeleteConfirm(null)
    try {
      const resp = await fetch(`${BASE}/api/forum_post/${postId}`, { method: 'DELETE' })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.recordRemoved') : (data.error || t('collection.toast.deleteFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) { fetchForumRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.deleteFailed'), 'bad') }
  }

  const handleTorrentRelocate = async (rec: TorrentRecord) => {
    const dir = await window.api.pickDir()
    if (!dir) return
    try {
      const resp = await fetch(`${BASE}/api/torrent/${rec.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_folder: dir }),
      })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.sourceFolderUpdated') : (data.error || t('collection.toast.updateFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) fetchTorrentRecords()
    } catch { onToast(t('collection.toast.updateFailed'), 'bad') }
  }

  const handleTorrentFileDelete = async (torrentId: number) => {
    setDeleteConfirm(null)
    try {
      const resp = await fetch(`${BASE}/api/torrent/${torrentId}/file`, { method: 'DELETE' })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.torrentFileDeleted') : (data.error || t('collection.toast.deleteFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) { fetchTorrentRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.deleteFailed'), 'bad') }
  }

  const [deleteRecordConfirm, setDeleteRecordConfirm] = useState<number | null>(null)

  const handleTorrentRecordDelete = async (torrentId: number) => {
    setDeleteRecordConfirm(null)
    try {
      const resp = await fetch(`${BASE}/api/torrent/${torrentId}`, { method: 'DELETE' })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.torrentRecordDeleted') : (data.error || t('collection.toast.deleteFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) { fetchTorrentRecords(); onRefetch() }
    } catch { onToast(t('collection.toast.deleteFailed'), 'bad') }
  }

  const fetchPersonalMeta = useCallback(() => {
    fetch(`${BASE}/api/collection/${row.lbNumberInt}/meta`)
      .then(r => r.json())
      .then(d => setPersonalMeta({ personal_rating: d.personal_rating ?? null, listen_count: d.listen_count ?? 0, last_listened: d.last_listened ?? null }))
      .catch(() => {})
  }, [row.lbNumberInt])

  useEffect(() => {
    setPersonalMeta(null)
    fetchPersonalMeta()
  }, [fetchPersonalMeta, personalMetaVersion])

  useEffect(() => {
    if (!row.diskPath) return
    setAudioInfo(null)
    fetch(`${BASE}/api/collection/${row.lbNumberInt}/audioinfo`)
      .then(r => r.json())
      .then((d: AudioInfo) => setAudioInfo(d))
      .catch(() => {})
  }, [row.lbNumberInt, row.diskPath])

  const handleLogListen = async () => {
    setLogListenBusy(true)
    try {
      await fetch(`${BASE}/api/collection/${row.lbNumberInt}/listen`, { method: 'POST' })
      fetchPersonalMeta()
      onToast(t('collection.toast.listenLogged', { lb: row.lbNumber }), 'ok')
    } catch {
      onToast(t('collection.toast.failedLogListen'), 'warn')
    } finally {
      setLogListenBusy(false)
    }
  }

  const META_ROWS: [string, React.ReactNode][] = [
    [t('collection.detail.folder'),        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)' }}>{row.folder || '—'}</span>],
    [t('collection.detail.diskPath'),     <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{row.diskPath || '—'}</span>],
    [t('collection.detail.size'),          <span style={{ fontFamily: 'var(--lbb-mono)' }}>{row.size || '—'}</span>],
    [t('collection.detail.confirmed'),     <span style={{ fontFamily: 'var(--lbb-mono)' }}>{row.confirmed || '—'}</span>],
    [t('collection.detail.fingerprinted'), row.fingerprinted
      ? <Pill tone="ok" soft>{t('collection.detail.fingerprintedYes')}</Pill>
      : <Pill tone="mute" soft>{t('collection.detail.fingerprintedNo')}</Pill>],
    [t('collection.detail.archRating'),  row.rating
      ? <Pill tone="ok" soft>{row.rating}</Pill>
      : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>],
    [t('collection.detail.myRating'),     personalMeta?.personal_rating != null
      ? <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{personalMeta.personal_rating} {t('collection.detail.perFive')}</span>
      : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>],
    [t('collection.detail.listens'),       personalMeta
      ? <span style={{ fontFamily: 'var(--lbb-mono)' }}>
          {personalMeta.listen_count}
          {personalMeta.last_listened && (
            <span style={{ color: 'var(--lbb-fg3)', marginLeft: 6 }}>· {personalMeta.last_listened.slice(0, 10)}</span>
          )}
        </span>
      : <span style={{ color: 'var(--lbb-fg3)' }}>…</span>],
  ]

  return (
    <>
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
          <Pill tone="ok" soft dot>{t('collection.detail.owned')}</Pill>
          <Pill tone={edge} soft>{row.status}</Pill>
          {row.isXref && <Pill tone="info" soft>{t('collection.detail.xref')}</Pill>}
          {audioInfo && audioInfo.format && !audioInfo.offline && (
            <Pill tone={audioInfo.mixed ? 'info' : 'mute'} soft>
              {audioInfo.format}
              {audioInfo.bit_depth  != null ? ` · ${audioInfo.bit_depth}`  : ''}
              {audioInfo.sample_rate != null ? `/${audioInfo.sample_rate}` : ''}
              {audioInfo.mixed ? ' (mixed)' : ''}
            </Pill>
          )}
        </div>

        {/* 2. ID + title block */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{
            fontSize: 'var(--lbb-fs-16)', fontWeight: 700,
            fontFamily: 'var(--lbb-mono)',
            color: 'var(--lbb-accent-mid)',
          }}>
            {row.lbNumber}
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {row.title || row.folder || '—'}
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
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
          fontSize: 'var(--lbb-fs-11-5)',
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
          <Button
            variant="secondary" size="sm" icon="reveal"
            disabled={!row.diskPath}
            onClick={() => onReveal(row.diskPath)}
          >
            {t('collection.detail.revealOnDisk')}
          </Button>
          <Button
            variant={row.wishlist ? 'primary' : 'ghost'} size="sm" icon="star"
            onClick={() => onWishlistToggle(row.lbNumberInt, row.wishlist)}
            title={row.wishlist ? 'Remove from wishlist' : 'Add to wishlist'}
          >
            {row.wishlist ? t('collection.detail.onWishlist') : t('collection.detail.wishlist')}
          </Button>
          <Button variant="ghost" size="sm" disabled={logListenBusy} onClick={handleLogListen}>
            {t('collection.detail.logListen')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onPersonalInfo(row.lbNumber, row.lbNumberInt)}>
            {t('collection.detail.editPersonalInfo')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onNavigate('/attachments')}>
            {t('collection.detail.attachments')}
          </Button>
          <Button variant="ghost" size="sm" disabled={!row.diskPath} onClick={() => onSpectrograms(row)}>
            {t('collection.detail.spectrograms')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onNavigate('/map')}>
            {t('collection.detail.onMap')}
          </Button>
        </div>

        {/* 5. History */}
        <div>
          <div style={{
            fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg3)',
            letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
          }}>
            {t('collection.detail.history')}
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <Chip
              active={historyTab === 'torrents'} size="sm"
              onClick={() => onHistoryTab('torrents')}
              count={torrentRecords.length || row.historyTorrents.length}
            >{t('collection.detail.torrents')}</Chip>
            <Chip
              active={historyTab === 'forum'} size="sm"
              onClick={() => onHistoryTab('forum')}
              count={forumRecords.length || row.historyForum.length}
            >{t('collection.detail.forumPosts')}</Chip>
          </div>

          {/* Torrents tab — per-record management */}
          {historyTab === 'torrents' && (
            torrentBusy ? (
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '6px 0' }}>{t('collection.detail.loadingTorrents')}</div>
            ) : torrentRecords.length === 0 ? (
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '6px 0' }}>{t('collection.detail.noTorrents')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {torrentRecords.map(rec => (
                  <div key={rec.id} style={{
                    border: '1px solid var(--lbb-border)',
                    borderRadius: 5, padding: '6px 8px',
                    display: 'flex', flexDirection: 'column', gap: 5,
                  }}>
                    {/* info row */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', flexShrink: 0 }}>
                        {rec.date || '—'}
                      </span>
                      <span style={{
                        fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg)',
                        flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {rec.filename || '—'}
                      </span>
                      {/* source folder dot */}
                      <span
                        title={`Source folder: ${rec.source_folder_exists ? rec.source_folder || 'exists' : 'missing'}`}
                        style={{
                          width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                          background: rec.source_folder_exists ? 'var(--lbb-ok-fg)' : rec.source_folder ? 'var(--lbb-err-fg)' : 'var(--lbb-border2)',
                        }}
                      />
                      {/* torrent file dot */}
                      <span
                        title={`Torrent file: ${rec.torrent_file_exists ? 'exists' : rec.torrent_path ? 'missing' : 'no path'}`}
                        style={{
                          width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                          background: rec.torrent_file_exists ? 'var(--lbb-ok-fg)' : rec.torrent_path ? 'var(--lbb-err-fg)' : 'var(--lbb-border2)',
                        }}
                      />
                      <Pill tone={rec.added_to_qbt ? 'info' : 'mute'} soft>
                        {rec.added_to_qbt ? t('collection.detail.inQbt') : t('collection.detail.local')}
                      </Pill>
                    </div>
                    {/* action row */}
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {rec.added_to_qbt ? (
                        <Button variant="ghost" size="sm" onClick={() => handleTorrentQbtRemove(rec)}>
                          {t('collection.detail.removeQbt')}
                        </Button>
                      ) : (
                        <Button variant="ghost" size="sm" onClick={() => handleTorrentAddQbt(rec)}>
                          {t('collection.detail.addQbt')}
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" disabled={!rec.source_folder} onClick={() => handleTorrentRegen(rec)}>
                        {t('collection.detail.regen')}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleTorrentRelocate(rec)}>
                        {t('collection.detail.relocate')}
                      </Button>
                      <Button variant="danger" size="sm" disabled={!rec.torrent_file_exists} onClick={() => setDeleteConfirm(rec.id)}>
                        {t('collection.detail.delFile')}
                      </Button>
                      <Button variant="danger" size="sm" disabled={rec.added_to_qbt} onClick={() => setDeleteRecordConfirm(rec.id)}>
                        {t('collection.detail.delRecord')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          {/* Forum tab — actionable */}
          {historyTab === 'forum' && (
            forumBusy ? (
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '6px 0' }}>{t('collection.detail.loadingForum')}</div>
            ) : forumError ? (
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-danger)', padding: '6px 0' }}>{t('collection.detail.forumLoadError')}</div>
            ) : forumRecords.length === 0 ? (
              <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', padding: '6px 0' }}>{t('collection.detail.noForumHistory')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {forumRecords.map(rec => (
                  <div key={rec.id} style={{
                    border: '1px solid var(--lbb-border)',
                    borderRadius: 5, padding: '6px 8px',
                    display: 'flex', flexDirection: 'column', gap: 5,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', flexShrink: 0 }}>
                        {rec.posted_at || '—'}
                      </span>
                      <span style={{
                        fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg)',
                        flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {rec.subject || '—'}
                      </span>
                      <Pill tone={rec.topic_url ? 'info' : 'mute'} soft>
                        {rec.topic_url ? 'Posted' : 'Local'}
                      </Pill>
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      <Button
                        variant="ghost" size="sm"
                        disabled={!rec.topic_url}
                        onClick={() => handleForumOpen(rec)}
                      >
                        {t('collection.detail.openInBrowser')}
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => setForumDeleteConfirm(rec.id)}>
                        {t('common.remove')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <Button
              variant="ghost" size="sm"
              disabled={!row.diskPath}
              onClick={() => onRegenTorrent(row.lbNumberInt, row.diskPath)}
            >
              {t('collection.detail.createTorrent')}
            </Button>
            <Button
              variant="ghost" size="sm"
              onClick={() => onPostForum(row.lbNumberInt)}
            >
              {t('collection.detail.postToForum')}
            </Button>
          </div>
        </div>

      </div>
    </div>

    {deleteConfirm !== null && (
      <ConfirmDialog
        title={t('collection.confirmDelete.torrentTitle')}
        body={t('collection.confirmDelete.torrentBody')}
        onConfirm={() => handleTorrentFileDelete(deleteConfirm)}
        onCancel={() => setDeleteConfirm(null)}
      />
    )}

    {deleteRecordConfirm !== null && (
      <ConfirmDialog
        title={t('collection.confirmDelete.recordTitle')}
        body={t('collection.confirmDelete.recordBody')}
        onConfirm={() => handleTorrentRecordDelete(deleteRecordConfirm)}
        onCancel={() => setDeleteRecordConfirm(null)}
      />
    )}

    {forumDeleteConfirm !== null && (
      <ConfirmDialog
        title={t('collection.confirmDelete.forumTitle')}
        body={t('collection.confirmDelete.forumBody')}
        onConfirm={() => handleForumRecordDelete(forumDeleteConfirm)}
        onCancel={() => setForumDeleteConfirm(null)}
      />
    )}
    </>
  )
}

// ── GlobalForumPanel ─────────────────────────────────────────────────────────

function GlobalForumPanel({ posts, search, onSearch, onOpen, onDelete, onGoToLb }: {
  posts: GlobalForumPost[]
  search: string
  onSearch: (s: string) => void
  onOpen: (url: string) => void
  onDelete: (postId: number) => void
  onGoToLb: (lb: number, lbStr: string) => void
}) {
  const { t } = useTranslation()
  const [deleteConfirm, setDeleteConfirm] = useState<GlobalForumPost | null>(null)

  const filtered = posts.filter(p => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      p.lbStr.toLowerCase().includes(q) ||
      p.subject.toLowerCase().includes(q) ||
      p.location.toLowerCase().includes(q) ||
      p.date_str.toLowerCase().includes(q)
    )
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', fontWeight: 600 }}>
          {t('collection.globalForum.postsCount', { count: filtered.length })}
        </span>
        <div style={{ flex: 1 }} />
        <Input
          icon="filter"
          placeholder={t('collection.globalForum.filter')}
          size="sm"
          value={search}
          onChange={e => onSearch(e.target.value)}
          style={{ width: 220 }}
        />
      </div>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <TableShell stickyHeader>
          <colgroup>
            <col style={{ width: 3 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 220 }} />
            <col />
            <col style={{ width: 240 }} />
          </colgroup>
          <thead>
            <tr>
              <TH />
              <TH>{t('collection.globalForum.colPosted')}</TH>
              <TH>LB#</TH>
              <TH>{t('collection.globalForum.colShowDate')}</TH>
              <TH>Subject</TH>
              <TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {filtered.map(p => (
              <TR key={p.id}>
                <TD />
                <TD mono dim>{p.posted_at || '—'}</TD>
                <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{p.lbStr}</TD>
                <TD dim>{[p.date_str, p.location].filter(Boolean).join(' · ') || '—'}</TD>
                <TD>{p.subject || '—'}</TD>
                <TD>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <Button
                      variant="ghost" size="sm"
                      disabled={!p.topic_url}
                      onClick={() => onOpen(p.topic_url)}
                    >
                      {t('collection.globalForum.openInBrowser')}
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => setDeleteConfirm(p)}>
                      {t('common.remove')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onGoToLb(p.lb_number, p.lbStr)}>
                      {t('collection.globalForum.goToLb')}
                    </Button>
                  </div>
                </TD>
              </TR>
            ))}
          </tbody>
        </TableShell>
        {filtered.length === 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            height: '60%', fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)',
          }}>
            {posts.length === 0 ? t('collection.globalForum.noPostsRecorded') : t('collection.globalForum.noResultsMatch')}
          </div>
        )}
      </div>
      {deleteConfirm && (
        <ConfirmDialog
          title={t('collection.confirmDelete.forumTitle')}
          body={t('collection.confirmDelete.forumBody')}
          onConfirm={() => { onDelete(deleteConfirm.id); setDeleteConfirm(null) }}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  )
}

// ── GlobalTorrentPanel ────────────────────────────────────────────────────────

function GlobalTorrentPanel({ records, search, onSearch, onGoToLb, onToast, onRefetch }: {
  records: GlobalTorrentRecord[]
  search: string
  onSearch: (s: string) => void
  onGoToLb: (lb: number, lbStr: string) => void
  onToast: (msg: string, tone: ToastTone) => void
  onRefetch: () => void
}) {
  const { t } = useTranslation()
  const filtered = records.filter(r => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      r.lbStr.toLowerCase().includes(q) ||
      r.filename.toLowerCase().includes(q) ||
      r.location.toLowerCase().includes(q) ||
      r.date_str.toLowerCase().includes(q)
    )
  })

  const [deleteRecordConfirm, setDeleteRecordConfirm] = useState<GlobalTorrentRecord | null>(null)

  const handleAddQbt = async (rec: GlobalTorrentRecord) => {
    try {
      const resp = await fetch(`${BASE}/api/qbt/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ torrent_id: rec.id }),
      })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.addedToQbt') : (data.error || t('collection.toast.qbtAddFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) onRefetch()
    } catch { onToast(t('collection.toast.qbtRequestFailed'), 'bad') }
  }

  const handleDeleteRecord = async (rec: GlobalTorrentRecord) => {
    setDeleteRecordConfirm(null)
    try {
      const resp = await fetch(`${BASE}/api/torrent/${rec.id}`, { method: 'DELETE' })
      const data = await resp.json()
      onToast(data.ok ? t('collection.toast.torrentRecordDeleted') : (data.error || t('collection.toast.deleteFailed')), data.ok ? 'ok' : 'bad')
      if (data.ok) onRefetch()
    } catch { onToast(t('collection.toast.deleteFailed'), 'bad') }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', fontWeight: 600 }}>
          {t('collection.globalTorrent.count', { count: filtered.length })}
        </span>
        <div style={{ flex: 1 }} />
        <Input
          icon="filter"
          placeholder={t('collection.globalTorrent.filter')}
          size="sm"
          value={search}
          onChange={e => onSearch(e.target.value)}
          style={{ width: 220 }}
        />
      </div>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <TableShell stickyHeader>
          <colgroup>
            <col style={{ width: 3 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 220 }} />
            <col />
            <col style={{ width: 110 }} />
            <col style={{ width: 160 }} />
          </colgroup>
          <thead>
            <tr>
              <TH />
              <TH>{t('collection.globalTorrent.colCreated')}</TH>
              <TH>LB#</TH>
              <TH>{t('collection.globalForum.colShowDate')}</TH>
              <TH>Filename</TH>
              <TH align="center">{t('collection.globalTorrent.colStatus')}</TH>
              <TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <TR key={r.id}>
                <TD />
                <TD mono dim>{r.created_at || '—'}</TD>
                <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{r.lbStr}</TD>
                <TD dim>{[r.date_str, r.location].filter(Boolean).join(' · ') || '—'}</TD>
                <TD mono>{r.filename || '—'}</TD>
                <TD align="center">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                    <span
                      title={`Source folder: ${r.source_folder_exists ? 'exists' : r.source_folder ? 'missing' : 'none'}`}
                      style={{
                        width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                        background: r.source_folder_exists ? 'var(--lbb-ok-fg)' : r.source_folder ? 'var(--lbb-err-fg)' : 'var(--lbb-border2)',
                      }}
                    />
                    <span
                      title={`Torrent file: ${r.torrent_file_exists ? 'exists' : r.torrent_path ? 'missing' : 'none'}`}
                      style={{
                        width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                        background: r.torrent_file_exists ? 'var(--lbb-ok-fg)' : r.torrent_path ? 'var(--lbb-err-fg)' : 'var(--lbb-border2)',
                      }}
                    />
                    <Pill tone={r.added_to_qbt ? 'info' : 'mute'} soft>
                      {r.added_to_qbt ? t('collection.detail.inQbt') : t('collection.detail.local')}
                    </Pill>
                  </div>
                </TD>
                <TD>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {!r.added_to_qbt && (
                      <Button variant="ghost" size="sm" onClick={() => handleAddQbt(r)}>
                        {t('collection.globalTorrent.addQbt')}
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => onGoToLb(r.lb_number, r.lbStr)}>
                      {t('collection.globalTorrent.goToLb')}
                    </Button>
                    <Button variant="danger" size="sm" disabled={r.added_to_qbt} onClick={() => setDeleteRecordConfirm(r)}>
                      {t('collection.detail.delRecord')}
                    </Button>
                  </div>
                </TD>
              </TR>
            ))}
          </tbody>
        </TableShell>
        {filtered.length === 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            height: '60%', fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)',
          }}>
            {records.length === 0 ? t('collection.detail.noTorrents') : t('collection.globalForum.noResultsMatch')}
          </div>
        )}
      </div>
      {deleteRecordConfirm && (
        <ConfirmDialog
          title={t('collection.confirmDelete.recordTitle')}
          body={t('collection.confirmDelete.recordBody')}
          onConfirm={() => handleDeleteRecord(deleteRecordConfirm)}
          onCancel={() => setDeleteRecordConfirm(null)}
        />
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenCollection(): React.JSX.Element {
  const { t } = useTranslation()
  const [rows, setRows]               = useState<CollectionRow[]>([])
  const [filter, setFilter]           = useState<FilterKey>('all')
  const [search, setSearch]           = useState('')
  const [selectedId, setSelectedId]   = useState<string | null>(null)
  const [checkedIds, setCheckedIds]   = useState<Set<string>>(new Set())
  const [historyTab, setHistoryTab]   = useState<HistoryTab>('torrents')
  const [years, setYears]             = useState<number[]>([])
  const [yearFilter, setYearFilter]   = useState<string | null>(null)
  const [yearsOpen, setYearsOpen]     = useState(false)
  const [xrefOnly, setXrefOnly]       = useState(false)
  const [toast, setToast]             = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [confirm, setConfirm]         = useState<{ title: string; body: string; onConfirm: () => void } | null>(null)
  const [addModal, setAddModal]       = useState<{ paths: string[] } | null>(null)
  const [forumModal, setForumModal]   = useState<{ lb: number; subject: string; body: string } | null>(null)
  const [removeProgress, setRemoveProgress]   = useState<{ done: number; total: number } | null>(null)
  const [torrentProgress, setTorrentProgress] = useState<{ done: number; total: number; label: string } | null>(null)
  const [ctxMenu, setCtxMenu]               = useState<CtxMenuState | null>(null)
  const [personalModal, setPersonalModal]   = useState<{ lb: string; lbNumber: number } | null>(null)
  const [personalSaveVer, setPersonalSaveVer] = useState(0)
  const [scanPreviewModal, setScanPreviewModal] = useState<{ entries: ScanEntry[]; skipped: number } | null>(null)
  const [missingLbRows, setMissingLbRows]   = useState<MissingLbRow[]>([])
  const [rawForumPosts,   setRawForumPosts]   = useState<GlobalForumPost[]>([])
  const [rawTorrentRecs,  setRawTorrentRecs]  = useState<GlobalTorrentRecord[]>([])
  const [duplicateGroups,  setDuplicateGroups]  = useState<DuplicateGroup[]>([])
  const [dupExpanded,      setDupExpanded]      = useState<Set<string>>(new Set())
  const [wishEditId,       setWishEditId]       = useState<string | null>(null)
  const [wishEditPriority, setWishEditPriority] = useState<number>(3)
  const [wishEditNotes,    setWishEditNotes]    = useState<string>('')
  const [globalForumSearch,   setGlobalForumSearch]   = useState('')
  const [globalTorrentSearch, setGlobalTorrentSearch] = useState('')
  const [sortCol, setSortCol]   = useState<string | null>(null)
  const [sortDir, setSortDir]   = useState<'asc' | 'desc'>('asc')

  const tableParentRef = useRef<HTMLDivElement>(null)
  const yearsDropRef   = useRef<HTMLDivElement>(null)

  const navigate                    = useNavigate()
  const { clearSources, addSource } = useLookupStore()
  const addPendingSpectro            = useSpectrogramStore(s => s.addPending)
  const queryClient = useQueryClient()
  const refetch    = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] }),
    [queryClient]
  )
  const showToast  = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  // ── Data loading ───────────────────────────────────────────────────────────

  const { data: prefetch } = useQuery({
    queryKey: ['collection-prefetch'],
    queryFn: () => fetch(`${BASE}/api/collection/prefetch`).then(r => r.json()),
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!prefetch) return

    const STATUS_MAP: Record<string, CollectionStatus> = {
      public: 'Public', private: 'Private', missing: 'Missing',
    }

    if (Array.isArray(prefetch.years)) {
      setYears((prefetch.years as number[]).sort((a, b) => b - a))
    }

    const xrefSetLocal = new Set<number>(
      Array.isArray(prefetch.xref_lb_numbers) ? (prefetch.xref_lb_numbers as number[]) : []
    )

    if (!Array.isArray(prefetch.collection)) {
      setRows(SAMPLE_DATA)
      return
    }

    const fpMap: Record<string, number> =
      prefetch.fingerprints && !prefetch.fingerprints.error ? prefetch.fingerprints : {}

    const wishlistMap = new Map<number, { priority: number | null; notes: string; added_at: string }>(
      Array.isArray(prefetch.wishlist)
        ? prefetch.wishlist.map((w: any) => [
            w.lb_number as number,
            { priority: w.priority ?? null, notes: w.notes ?? '', added_at: (w.added_at ?? '').slice(0, 10) },
          ])
        : []
    )
    const wishlistSet = new Set<number>(wishlistMap.keys())

    const dupSet = new Set<number>()
    if (Array.isArray(prefetch.duplicates)) {
      for (const group of prefetch.duplicates) {
        if (Array.isArray(group.owned) && group.owned.length > 1) {
          for (const o of group.owned) dupSet.add(o.lb_number as number)
        }
      }
    }

    const forumByLb: Record<number, any[]> = {}
    if (Array.isArray(prefetch.forum_posts)) {
      for (const p of prefetch.forum_posts) {
        ;(forumByLb[p.lb_number] ??= []).push(p)
      }
    }

    const torrentByLb: Record<number, any[]> = {}
    if (Array.isArray(prefetch.torrents)) {
      for (const t of prefetch.torrents) {
        ;(torrentByLb[t.lb_number] ??= []).push(t)
      }
      setRawTorrentRecs((prefetch.torrents as any[]).map((t: any) => ({
        id: t.id,
        lb_number: t.lb_number,
        lbStr: `LB-${String(t.lb_number).padStart(5, '0')}`,
        filename: t.torrent_path ? (t.torrent_path as string).split('/').pop() ?? '' : '',
        source_folder: t.source_folder ?? '',
        torrent_path: t.torrent_path ?? '',
        created_at: (t.created_at ?? '').slice(0, 10),
        added_to_qbt: !!t.added_to_qbt,
        source_folder_exists: !!t.source_folder_exists,
        torrent_file_exists: !!t.torrent_file_exists,
        date_str: t.date_str ?? '',
        location: t.location ?? '',
      })))
    }

    if (Array.isArray(prefetch.forum_posts)) {
      setRawForumPosts((prefetch.forum_posts as any[]).map((p: any) => ({
        id: p.id,
        lb_number: p.lb_number,
        lbStr: `LB-${String(p.lb_number).padStart(5, '0')}`,
        subject: p.subject ?? '',
        topic_url: p.topic_url ?? '',
        posted_at: (p.posted_at ?? '').slice(0, 10),
        date_str: p.date_str ?? '',
        location: p.location ?? '',
      })))
    }

    const merged: CollectionRow[] = (prefetch.collection as any[]).map((c: any) => {
      const lb: number = c.lb_number
      return {
        lbNumber:    `LB-${String(lb).padStart(5, '0')}`,
        lbNumberInt: lb,
        status:      STATUS_MAP[c.lb_status] ?? 'New',
        date:        c.date_str ?? '',
        location:    c.location ?? '',
        folder:      c.folder_name ?? '',
        diskPath:    c.disk_path ?? '',
        notes:       c.notes ?? '',
        confirmed:   c.confirmed_at ?? '',
        fingerprinted: (fpMap[String(lb)] ?? 0) > 0,
        title:       c.description ?? '',
        discs:       parseInt(c.cdr ?? '0') || 0,
        size:        '',
        rating:           c.rating ?? '',
        wishlist:         wishlistSet.has(lb),
        wishlistPriority: wishlistMap.get(lb)?.priority ?? null,
        wishlistNotes:    wishlistMap.get(lb)?.notes ?? '',
        wishlistAddedAt:  wishlistMap.get(lb)?.added_at ?? '',
        isDuplicate: dupSet.has(lb),
        isXref:      xrefSetLocal.has(lb),
        historyTorrents: (torrentByLb[lb] ?? []).map((t: any) => ({
          date:     (t.created_at ?? '').slice(0, 10),
          filename: t.torrent_path ? (t.torrent_path as string).split('/').pop() ?? '' : '',
          kind:     t.added_to_qbt ? 'In qBt' : 'Local',
        })),
        historyForum: (forumByLb[lb] ?? []).map((p: any) => ({
          date:     (p.posted_at ?? '').slice(0, 10),
          filename: p.subject ?? '',
          kind:     'Local',
        })),
      }
    })

    setRows(merged)
    setMissingLbRows(Array.isArray(prefetch.missing) ? prefetch.missing : [])
    setDuplicateGroups(Array.isArray(prefetch.duplicates) ? prefetch.duplicates : [])
  }, [prefetch])

  // ── Close year dropdown on outside click ───────────────────────────────────

  useEffect(() => {
    if (!yearsOpen) return
    const handler = (e: MouseEvent) => {
      if (yearsDropRef.current && !yearsDropRef.current.contains(e.target as Node)) {
        setYearsOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [yearsOpen])

  // ── Derived state ──────────────────────────────────────────────────────────

  const counts = {
    all:         rows.length,
    missing:     rows.filter(r => r.status === 'Missing').length,
    wishlist:    rows.filter(r => r.wishlist).length,
    duplicates:  rows.filter(r => r.isDuplicate).length,
    forum:       rows.filter(r => r.historyForum.length > 0).length,
    torrent:     rows.filter(r => r.historyTorrents.length > 0).length,
    unconfirmed: rows.filter(r => !r.confirmed).length,
    nofp:        rows.filter(r => !r.fingerprinted).length,
    not_owned:      missingLbRows.length,
    forum_global:   rawForumPosts.length,
    torrent_global: rawTorrentRecs.length,
  }

  const confirmedCount     = rows.filter(r => r.confirmed).length
  const fingerprintedCount = rows.filter(r => r.fingerprinted).length

  const filteredRows = rows.filter(r => {
    switch (filter) {
      case 'missing':     if (r.status !== 'Missing') return false; break
      case 'wishlist':    if (!r.wishlist) return false; break
      case 'duplicates':  if (!r.isDuplicate) return false; break
      case 'forum':       if (r.historyForum.length === 0) return false; break
      case 'torrent':     if (r.historyTorrents.length === 0) return false; break
      case 'unconfirmed': if (r.confirmed) return false; break
      case 'nofp':        if (r.fingerprinted) return false; break
    }
    if (yearFilter !== null) {
      const y = extractYear(r.date)
      if (y === null || String(y) !== yearFilter) return false
    }
    if (xrefOnly && !r.isXref) return false
    if (search) {
      const q = search.toLowerCase()
      if (
        !r.lbNumber.toLowerCase().includes(q) &&
        !r.location.toLowerCase().includes(q) &&
        !r.folder.toLowerCase().includes(q) &&
        !r.date.includes(q)
      ) return false
    }
    return true
  })

  const selectedRow = selectedId ? (filteredRows.find(r => r.lbNumber === selectedId) ?? null) : null

  const handleSort = useCallback((col: string) => {
    setSortCol(prev => {
      if (prev === col) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); return col }
      setSortDir('asc')
      return col
    })
  }, [])

  const sortedFilteredRows = React.useMemo(() => {
    if (!sortCol) return filteredRows
    return [...filteredRows].sort((a, b) => {
      let va: string | number = ''
      let vb: string | number = ''
      if (sortCol === 'lb')        { va = a.lbNumberInt;  vb = b.lbNumberInt }
      else if (sortCol === 'status')    { va = a.status;       vb = b.status }
      else if (sortCol === 'date')      { va = a.date;         vb = b.date }
      else if (sortCol === 'location')  { va = a.location;     vb = b.location }
      else if (sortCol === 'folder')    { va = a.folder;       vb = b.folder }
      else if (sortCol === 'diskPath')  { va = a.diskPath;     vb = b.diskPath }
      else if (sortCol === 'confirmed') { va = a.confirmed;    vb = b.confirmed }
      else if (sortCol === 'fp')        { va = a.fingerprinted ? 1 : 0; vb = b.fingerprinted ? 1 : 0 }
      const cmp = typeof va === 'number'
        ? va - (vb as number)
        : String(va).localeCompare(String(vb))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filteredRows, sortCol, sortDir])

  const virtualizer = useVirtualizer({
    count: sortedFilteredRows.length,
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

  // ── Action helpers ─────────────────────────────────────────────────────────

  // Rows targeted by bulk actions: checked rows first, fall back to selected row
  const getTargetRows = useCallback((): CollectionRow[] => {
    if (checkedIds.size > 0) return rows.filter(r => checkedIds.has(r.lbNumber))
    const sel = rows.find(r => r.lbNumber === selectedId)
    return sel ? [sel] : []
  }, [rows, checkedIds, selectedId])

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleExportHtml = async () => {
    try {
      const resp = await fetch(`${BASE}/api/collection/export/html`)
      const blob = await resp.blob()
      blobDownload(blob, 'collection.html')
    } catch { showToast('HTML export failed', 'bad') }
  }

  const handleExportM3u = async () => {
    try {
      const resp = await fetch(`${BASE}/api/collection/export/m3u`)
      const blob = await resp.blob()
      blobDownload(blob, 'collection.m3u')
    } catch { showToast('M3U export failed', 'bad') }
  }

  const handleBatchCreateTorrent = async () => {
    const targets = getTargetRows().filter(r => r.diskPath)
    if (!targets.length) { showToast('Select rows with a disk path first', 'info'); return }
    let ok = 0; let fail = 0
    setTorrentProgress({ done: 0, total: targets.length, label: 'Creating torrents' })
    for (let i = 0; i < targets.length; i++) {
      const r = targets[i]
      try {
        const resp = await fetch(`${BASE}/api/torrent/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lb_number: r.lbNumberInt, source_folder: r.diskPath }),
        })
        const data = await resp.json()
        if (data.ok) ok++; else fail++
      } catch { fail++ }
      setTorrentProgress({ done: i + 1, total: targets.length, label: 'Creating torrents' })
    }
    setTorrentProgress(null)
    showToast(
      `${ok} torrent${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`,
      ok > 0 ? 'ok' : 'bad'
    )
    refetch()
  }

  const handleBatchAddToQbt = async () => {
    const lbs = getTargetRows().map(r => r.lbNumberInt)
    if (!lbs.length) { showToast('Select rows first', 'info'); return }
    setTorrentProgress({ done: 0, total: lbs.length, label: 'Sending to qBittorrent' })
    try {
      const resp = await fetch(`${BASE}/api/qbt/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_numbers: lbs }),
      })
      const data = await resp.json()
      setTorrentProgress({ done: lbs.length, total: lbs.length, label: 'Sending to qBittorrent' })
      showToast(
        `Added ${data.added ?? 0}/${data.total ?? lbs.length} to qBittorrent`,
        data.ok ? 'ok' : 'bad'
      )
    } catch {
      showToast('qBittorrent request failed', 'bad')
    } finally {
      setTorrentProgress(null)
    }
  }

  const handleReveal = useCallback(async (diskPath: string) => {
    if (!diskPath) { showToast('No disk path for this entry', 'info'); return }
    await window.api.openPath(diskPath)
  }, [showToast])

  const handleRemoveChecked = () => {
    const targets = getTargetRows()
    if (!targets.length) { showToast('Select rows first', 'info'); return }
    setConfirm({
      title: 'Remove from collection',
      body: `Remove ${targets.length} item${targets.length !== 1 ? 's' : ''} from your collection? Files on disk will not be deleted.`,
      onConfirm: async () => {
        setConfirm(null)
        setRemoveProgress({ done: 0, total: targets.length })
        let ok = 0; let fail = 0
        for (let i = 0; i < targets.length; i++) {
          try {
            await fetch(`${BASE}/api/collection/${targets[i].lbNumberInt}`, { method: 'DELETE' })
            ok++
          } catch { fail++ }
          setRemoveProgress({ done: i + 1, total: targets.length })
        }
        setRemoveProgress(null)
        showToast(
          `Removed ${ok}${fail > 0 ? `, ${fail} failed` : ''}`,
          ok > 0 ? 'ok' : 'bad'
        )
        setCheckedIds(new Set())
        setSelectedId(null)
        refetch()
      },
    })
  }

  const handleAddSingleFolder = async () => {
    const paths = await window.api.pickFolders()
    if (!paths.length) return
    setAddModal({ paths })
  }

  const _runScanLb = async (recursive: boolean) => {
    const dir = await window.api.pickDir()
    if (!dir) return
    try {
      const resp = await fetch(`${BASE}/api/pipeline/scan-dir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ root: dir, recursive }),
      })
      const data = await resp.json() as { entries?: ScanEntry[]; skipped?: number; error?: string }
      if (data.entries?.length) {
        setScanPreviewModal({ entries: data.entries, skipped: data.skipped ?? 0 })
      } else {
        const skippedMsg = (data.skipped ?? 0) > 0 ? ` (${data.skipped} folders skipped — no LB#)` : ''
        showToast(`No LB-numbered folders found${skippedMsg}`, 'info')
      }
    } catch { showToast('Scan failed', 'bad') }
  }

  const handleScanDir  = () => _runScanLb(false)
  const handleScanTree = () => _runScanLb(true)

  const handleUpdateLocation = async () => {
    const targets = getTargetRows()
    if (!targets.length) { showToast('Select rows first', 'info'); return }

    if (targets.length === 1) {
      // Single-row: pick the exact folder, validate name
      const target = targets[0]
      const dir = await window.api.pickDir()
      if (!dir) return
      const folderName = dir.replace(/\/+$/, '').split('/').pop() || dir
      // Cross-check folder name against standard
      try {
        const stdResp = await fetch(`${BASE}/api/folder_naming/standard/${target.lbNumberInt}`)
        if (stdResp.ok) {
          const stdData = await stdResp.json()
          const stdName: string = stdData.standard_name ?? ''
          if (stdName && folderName !== stdName) {
            showToast(`Name mismatch — expected: ${stdName}`, 'info')
          }
        }
      } catch { /* non-blocking */ }
      try {
        await fetch(`${BASE}/api/collection/${target.lbNumberInt}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ disk_path: dir, folder_name: folderName }),
        })
        showToast(`Updated location for ${target.lbNumber}`, 'ok')
        refetch()
      } catch { showToast('Update failed', 'bad') }
    } else {
      // Multi-row: pick a parent dir and scan for LB-XXXXX subfolders
      const parentDir = await window.api.pickDir()
      if (!parentDir) return
      let ok = 0; let skip = 0
      setTorrentProgress({ done: 0, total: targets.length, label: 'Updating locations' })
      for (let i = 0; i < targets.length; i++) {
        const t = targets[i]
        // Ask backend to find matching subfolder
        try {
          const scanResp = await fetch(`${BASE}/api/pipeline/scan-dir`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ root: parentDir, recursive: false }),
          })
          const scanData = await scanResp.json()
          const entries: { lb_number: number; folder: string; path: string }[] = scanData.entries ?? []
          const match = entries.find(e => e.lb_number === t.lbNumberInt)
          if (match) {
            // Validate folder name
            try {
              const stdResp = await fetch(`${BASE}/api/folder_naming/standard/${t.lbNumberInt}`)
              if (stdResp.ok) {
                const stdData = await stdResp.json()
                const stdName: string = stdData.standard_name ?? ''
                const actualName = match.folder
                if (stdName && actualName !== stdName) {
                  showToast(`${t.lbNumber}: name mismatch — expected ${stdName}`, 'info')
                }
              }
            } catch { /* non-blocking */ }
            await fetch(`${BASE}/api/collection/${t.lbNumberInt}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ disk_path: match.path, folder_name: match.folder }),
            })
            ok++
          } else {
            skip++
          }
        } catch { skip++ }
        setTorrentProgress({ done: i + 1, total: targets.length, label: 'Updating locations' })
      }
      setTorrentProgress(null)
      showToast(
        `Updated ${ok}${skip > 0 ? `, ${skip} not found` : ''}`,
        ok > 0 ? 'ok' : 'info'
      )
      if (ok > 0) refetch()
    }
  }

  const handleRegenTorrent = useCallback(async (lb: number, diskPath: string) => {
    if (!diskPath) { showToast('No disk path for this entry', 'info'); return }
    try {
      const resp = await fetch(`${BASE}/api/torrent/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: lb, source_folder: diskPath }),
      })
      const data = await resp.json()
      showToast(
        data.ok ? `Torrent regenerated: ${data.name ?? ''}` : (data.error || 'Torrent failed'),
        data.ok ? 'ok' : 'bad'
      )
      if (data.ok) refetch()
    } catch { showToast('Torrent creation failed', 'bad') }
  }, [showToast, refetch])

  const handlePostForum = useCallback(async (lb: number) => {
    try {
      const resp = await fetch(`${BASE}/api/entry/${lb}/preview_forum`)
      const data = await resp.json()
      setForumModal({ lb, subject: data.subject ?? '', body: data.body ?? '' })
    } catch { showToast(t('collection.toast.couldNotLoadForumPreview'), 'bad') }
  }, [showToast])

  const handleForumPosted = useCallback((topicUrl: string) => {
    showToast(topicUrl ? t('collection.toast.postedWithUrl', { url: topicUrl }) : t('collection.toast.postedToForum'), 'ok')
    refetch()
  }, [showToast, refetch])

  const handleWishlistToggle = useCallback(async (lb: number, currentlyOn: boolean) => {
    try {
      if (currentlyOn) {
        await fetch(`${BASE}/api/wishlist/${lb}`, { method: 'DELETE' })
        showToast(t('collection.toast.removedFromWishlist', { lb }), 'ok')
      } else {
        await fetch(`${BASE}/api/wishlist`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lb_number: lb }),
        })
        showToast(t('collection.toast.addedToWishlist', { lb }), 'ok')
      }
      refetch()
    } catch {
      showToast(t('collection.toast.wishlistUpdateFailed'), 'bad')
    }
  }, [showToast, refetch])

  const handleWishlistUpdate = useCallback(async (lb: number, priority: number, notes: string) => {
    try {
      await fetch(`${BASE}/api/wishlist/${lb}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority, notes }),
      })
      refetch()
      setWishEditId(null)
    } catch { showToast('Wishlist update failed', 'bad') }
  }, [refetch, showToast])

  // ── Context menu handlers ──────────────────────────────────────────────────

  const handleCtxOpenFolder = useCallback(async (row: CollectionRow) => {
    if (!row.diskPath) return
    await window.api.openPath(row.diskPath)
  }, [])

  const handleCtxViewLookup = useCallback((row: CollectionRow) => {
    if (!row.diskPath) return
    clearSources()
    addSource({ kind: 'folder', name: row.folder || row.lbNumber, content: row.diskPath, active: true })
    navigate('/lookup')
  }, [clearSources, addSource, navigate])

  const handleCtxScrape = useCallback(async (row: CollectionRow) => {
    try {
      const resp = await fetch(`${BASE}/api/entry/${row.lbNumberInt}/scrape`, { method: 'POST' })
      const data = await resp.json()
      showToast(
        data.ok !== false ? t('collection.toast.queuedScrape', { lb: row.lbNumber }) : (data.error || t('collection.toast.scrapeFailed')),
        data.ok !== false ? 'ok' : 'bad',
      )
    } catch { showToast(t('collection.toast.scrapeRequestFailed'), 'bad') }
  }, [showToast])

  const handleCtxFingerprint = useCallback(async (row: CollectionRow) => {
    if (!row.diskPath) return
    try {
      const resp = await fetch(`${BASE}/api/fingerprint/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [{ disk_path: row.diskPath, lb_number: row.lbNumberInt }] }),
      })
      const data = await resp.json()
      showToast(
        data.ok ? t('collection.toast.fingerprinting', { lb: row.lbNumber }) : (data.error || t('collection.toast.fingerprintFailed')),
        data.ok ? 'ok' : 'bad',
      )
    } catch { showToast(t('collection.toast.fingerprintRequestFailed'), 'bad') }
  }, [showToast])

  const handleCtxVlc = useCallback(async (row: CollectionRow) => {
    if (!row.diskPath) return
    try {
      const resp = await fetch(`${BASE}/api/open/vlc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: [row.diskPath] }),
      })
      const data = await resp.json()
      if (!data.ok) showToast(data.error || t('collection.toast.vlcNotFound'), 'bad')
    } catch { showToast(t('collection.toast.vlcRequestFailed'), 'bad') }
  }, [showToast])

  const handleCtxSpectrograms = useCallback(async (row: CollectionRow) => {
    if (!row.diskPath) return
    try {
      const resp = await fetch(`${BASE}/api/spectrogram/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: [row.diskPath] }),
      })
      const data = await resp.json()
      if (data.ok) {
        addPendingSpectro([row.diskPath])
        navigate('/spectrograms')
      } else {
        showToast(data.error || t('collection.toast.spectrogramFailed'), 'bad')
      }
    } catch { showToast(t('collection.toast.spectrogramRequestFailed'), 'bad') }
  }, [showToast, addPendingSpectro, navigate])

  // Returns rows to act on from a right-click: all checked rows if the clicked row is checked, else just that row.
  const getCtxRows = useCallback((row: CollectionRow): CollectionRow[] => {
    if (checkedIds.size > 0 && checkedIds.has(row.lbNumber)) {
      return rows.filter(r => checkedIds.has(r.lbNumber))
    }
    return [row]
  }, [checkedIds, rows])

  const handleCtxCreateTorrent = useCallback(async (row: CollectionRow) => {
    const targets = getCtxRows(row).filter(r => r.diskPath)
    if (!targets.length) { showToast('No disk path for this entry', 'info'); return }
    let ok = 0; let fail = 0
    setTorrentProgress({ done: 0, total: targets.length, label: 'Creating torrents' })
    for (let i = 0; i < targets.length; i++) {
      const r = targets[i]
      try {
        const resp = await fetch(`${BASE}/api/torrent/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lb_number: r.lbNumberInt, source_folder: r.diskPath }),
        })
        const data = await resp.json()
        if (data.ok) ok++; else fail++
      } catch { fail++ }
      setTorrentProgress({ done: i + 1, total: targets.length, label: 'Creating torrents' })
    }
    setTorrentProgress(null)
    showToast(
      `${ok} torrent${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`,
      ok > 0 ? 'ok' : 'bad'
    )
    refetch()
  }, [getCtxRows, showToast, refetch])

  const handleCtxAddToQbt = useCallback(async (row: CollectionRow) => {
    const lbs = getCtxRows(row).map(r => r.lbNumberInt)
    if (!lbs.length) return
    try {
      const resp = await fetch(`${BASE}/api/qbt/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_numbers: lbs }),
      })
      const data = await resp.json()
      showToast(
        `Added ${data.added ?? 0}/${data.total ?? lbs.length} to qBittorrent`,
        data.ok ? 'ok' : 'bad'
      )
    } catch { showToast('qBittorrent request failed', 'bad') }
  }, [getCtxRows, showToast])

  const handleCtxPostForum = useCallback(async (row: CollectionRow) => {
    const targets = getCtxRows(row)
    if (targets.length === 1) {
      await handlePostForum(targets[0].lbNumberInt)
      return
    }
    setConfirm({
      title: 'Post to forum',
      body: `Post ${targets.length} entries to the forum? Each will be posted using its auto-generated subject and body.`,
      onConfirm: async () => {
        setConfirm(null)
        let ok = 0; let fail = 0
        for (const r of targets) {
          try {
            const previewResp = await fetch(`${BASE}/api/entry/${r.lbNumberInt}/preview_forum`)
            const previewData = await previewResp.json()
            const postResp = await fetch(`${BASE}/api/entry/${r.lbNumberInt}/post_forum`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ subject: previewData.subject ?? '', body: previewData.body ?? '' }),
            })
            const postData = await postResp.json()
            if (postData.ok) ok++; else fail++
          } catch { fail++ }
        }
        showToast(
          `${ok} post${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`,
          ok > 0 ? 'ok' : 'bad'
        )
        refetch()
      },
    })
  }, [getCtxRows, handlePostForum, showToast, refetch])

  const handleBatchPostForum = useCallback(async () => {
    const targets = getTargetRows()
    if (!targets.length) { showToast('Select rows first', 'info'); return }
    if (targets.length === 1) {
      await handlePostForum(targets[0].lbNumberInt)
      return
    }
    setConfirm({
      title: 'Post to forum',
      body: `Post ${targets.length} entries to the forum? Each will be posted using its auto-generated subject and body.`,
      onConfirm: async () => {
        setConfirm(null)
        let ok = 0; let fail = 0
        for (const r of targets) {
          try {
            const previewResp = await fetch(`${BASE}/api/entry/${r.lbNumberInt}/preview_forum`)
            const previewData = await previewResp.json()
            const postResp = await fetch(`${BASE}/api/entry/${r.lbNumberInt}/post_forum`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ subject: previewData.subject ?? '', body: previewData.body ?? '' }),
            })
            const postData = await postResp.json()
            if (postData.ok) ok++; else fail++
          } catch { fail++ }
        }
        showToast(
          `${ok} post${ok !== 1 ? 's' : ''} created${fail > 0 ? `, ${fail} failed` : ''}`,
          ok > 0 ? 'ok' : 'bad'
        )
        refetch()
      },
    })
  }, [getTargetRows, handlePostForum, showToast, refetch])


  // ── Missing LB (not-owned) handlers ───────────────────────────────────────

  const handleMissingExportCsv = useCallback(() => {
    const headers = ['LB#', 'LB Status', 'Date', 'Location', 'Rating', 'Description']
    const escape  = (v: string) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines   = [
      headers.join(','),
      ...missingLbRows.map(r => [
        `LB-${String(r.lb_number).padStart(5, '0')}`,
        r.lb_status ?? '',
        r.date_str   ?? '',
        r.location   ?? '',
        r.rating     ?? '',
        r.description ?? '',
      ].map(escape).join(',')),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'missing_lbs.csv'
    a.click()
    URL.revokeObjectURL(url)
  }, [missingLbRows])

  const handleMissingRowDblClick = useCallback((row: MissingLbRow) => {
    const lb = `LB-${String(row.lb_number).padStart(5, '0')}`
    clearSources()
    addSource({ label: lb, lbNumber: row.lb_number })
    navigate('/lookup')
  }, [clearSources, addSource, navigate])

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
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-20)', fontWeight: 700, color: 'var(--lbb-fg)', lineHeight: 1.2 }}>
            My Collection
          </h1>
          <span style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)' }}>
            {rows.length.toLocaleString()} items
          </span>
        </div>
        <div style={{ flex: 1 }} />
        {filter === 'not_owned' ? (
          <Button variant="ghost" size="sm" icon="download" onClick={handleMissingExportCsv}>Export CSV</Button>
        ) : (
          <>
            <Button variant="ghost"     size="sm" icon="download" onClick={handleExportHtml}>Export HTML</Button>
            <Button variant="ghost"     size="sm" icon="download" onClick={handleExportM3u}>Export M3U</Button>
            <Button variant="secondary" size="sm" onClick={handleBatchPostForum}>Post to forum</Button>
            <Button variant="secondary" size="sm" onClick={handleBatchCreateTorrent}>Create torrent</Button>
            <Button variant="primary"   size="sm" icon="plus" onClick={handleBatchAddToQbt}>Add to qBittorrent</Button>
          </>
        )}
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
        <Chip active={filter === 'forum_global'}   onClick={() => setFilter('forum_global')}   count={counts.forum_global}>All forum posts</Chip>
        <Chip active={filter === 'torrent_global'} onClick={() => setFilter('torrent_global')} count={counts.torrent_global}>All torrents</Chip>
        {sep}
        <Chip active={filter === 'not_owned'}   onClick={() => setFilter('not_owned')}   count={counts.not_owned}>Not in collection</Chip>
        <div style={{ flex: 1 }} />
        <Input
          icon="filter"
          placeholder="Filter collection…"
          size="sm"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 240 }}
        />

        {/* Year dropdown */}
        <div ref={yearsDropRef} style={{ position: 'relative' }}>
          <Button
            variant="ghost" size="sm" iconRight="chevDown"
            onClick={() => setYearsOpen(v => !v)}
          >
            {yearFilter ?? 'All years'}
          </Button>
          {yearsOpen && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 4px)', right: 0, zIndex: 100,
              background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
              borderRadius: 8, padding: 4,
              minWidth: 110, maxHeight: 280, overflowY: 'auto',
              boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
            }}>
              {[null, ...years].map(y => (
                <button
                  key={y ?? 'all'}
                  onClick={() => { setYearFilter(y !== null ? String(y) : null); setYearsOpen(false) }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '5px 10px', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', border: 'none',
                    background: (y !== null ? String(y) : null) === yearFilter
                      ? 'var(--lbb-accent-bg)' : 'transparent',
                    color: 'var(--lbb-fg)', borderRadius: 5,
                  }}
                >
                  {y ?? 'All years'}
                </button>
              ))}
            </div>
          )}
        </div>

        <label style={{
          fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
          display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            style={{ margin: 0 }}
            checked={xrefOnly}
            onChange={e => setXrefOnly(e.target.checked)}
          />
          Xref only
        </label>
      </div>

      {/* ── Inline action toolbar ─────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 16px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
      }}>
        <Button variant="secondary" size="sm" icon="folderPlus" onClick={handleAddSingleFolder}>
          Add single folder
        </Button>
        <Button variant="secondary" size="sm" icon="search" onClick={handleScanDir}>
          Scan directory
        </Button>
        <Button variant="secondary" size="sm" icon="folder" onClick={handleScanTree}>
          Scan tree…
        </Button>
        {sep}
        <Button variant="ghost"  size="sm" onClick={handleUpdateLocation}>Update location</Button>
        <Button variant="danger" size="sm" icon="trash" onClick={handleRemoveChecked}>Remove</Button>
        <div style={{ flex: 1 }} />
        <span style={{
          fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)',
          fontFamily: 'var(--lbb-mono)',
        }}>
          {confirmedCount.toLocaleString()} confirmed
        </span>
      </div>

      {/* ── Batch-remove progress bar ─────────────────────────────────────────── */}
      {removeProgress && (
        <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
            <span>Removing {removeProgress.done} / {removeProgress.total}…</span>
            <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--lbb-border)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2,
                background: 'var(--lbb-accent-mid)',
                width: `${Math.round((removeProgress.done / removeProgress.total) * 100)}%`,
                transition: 'width 0.15s',
              }} />
            </div>
          </div>
        </div>
      )}

      {/* ── Batch-torrent progress bar ────────────────────────────────────────── */}
      {torrentProgress && (
        <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
            <span>{torrentProgress.label}: {torrentProgress.done} / {torrentProgress.total}…</span>
            <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--lbb-border)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2,
                background: 'var(--lbb-ok-bar)',
                width: `${Math.round((torrentProgress.done / torrentProgress.total) * 100)}%`,
                transition: 'width 0.15s',
              }} />
            </div>
          </div>
        </div>
      )}

      {/* ── Main content: table + detail panel ───────────────────────────────── */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'grid',
        gridTemplateColumns: (filter === 'not_owned' || filter === 'forum_global' || filter === 'torrent_global') ? '1fr' : (selectedRow ? '1fr 360px' : '1fr'),
      }}>

        {/* Not-in-collection table */}
        {filter === 'not_owned' && (
          <div style={{ overflow: 'auto', minHeight: 0 }}>
            <TableShell stickyHeader>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 100 }} />
                <col />
                <col style={{ width: 60 }} />
                <col style={{ width: 300 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH />
                  <TH>LB#</TH>
                  <TH>LB Status</TH>
                  <TH>Date</TH>
                  <TH>Location</TH>
                  <TH>Rating</TH>
                  <TH>Description</TH>
                </tr>
              </thead>
              <tbody>
                {missingLbRows.map(r => {
                  const lb = `LB-${String(r.lb_number).padStart(5, '0')}`
                  return (
                    <TR
                      key={r.lb_number}
                      onDoubleClick={() => handleMissingRowDblClick(r)}
                      style={{ cursor: 'pointer' }}
                    >
                      <TD />
                      <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{lb}</TD>
                      <TD><Pill tone="mute" soft dot>{r.lb_status || '—'}</Pill></TD>
                      <TD mono>{r.date_str || '—'}</TD>
                      <TD>{r.location || '—'}</TD>
                      <TD mono>{r.rating || '—'}</TD>
                      <TD dim>{r.description || '—'}</TD>
                    </TR>
                  )
                })}
              </tbody>
            </TableShell>
            {missingLbRows.length === 0 && (
              <div style={{
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                height: '60%', gap: 12,
                color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
              }}>
                <Icon name="check" size={40} style={{ opacity: 0.2 }} />
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                  You own everything in the archive
                </div>
              </div>
            )}
          </div>
        )}

        {/* Global Forum History */}
        {filter === 'forum_global' && (
          <GlobalForumPanel
            posts={rawForumPosts}
            search={globalForumSearch}
            onSearch={setGlobalForumSearch}
            onOpen={url => window.open(url, '_blank')}
            onDelete={async postId => {
              try {
                const resp = await fetch(`${BASE}/api/forum_post/${postId}`, { method: 'DELETE' })
                const data = await resp.json()
                showToast(data.ok ? t('collection.toast.recordRemoved') : (data.error || t('collection.toast.deleteFailed')), data.ok ? 'ok' : 'bad')
                if (data.ok) refetch()
              } catch { showToast(t('collection.toast.deleteFailed'), 'bad') }
            }}
            onGoToLb={(lb, lbStr) => {
              setFilter('all')
              setSearch(lbStr)
              setSelectedId(lbStr)
            }}
          />
        )}

        {/* Global Torrent History */}
        {filter === 'torrent_global' && (
          <GlobalTorrentPanel
            records={rawTorrentRecs}
            search={globalTorrentSearch}
            onSearch={setGlobalTorrentSearch}
            onGoToLb={(lb, lbStr) => {
              setFilter('all')
              setSearch(lbStr)
              setSelectedId(lbStr)
            }}
            onToast={showToast}
            onRefetch={refetch}
          />
        )}

        {/* Wishlist table — extra columns + inline edit */}
        {filter === 'wishlist' && (
        <div style={{ overflow: 'auto', minHeight: 0 }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 60 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 200 }} />
              <col style={{ width: 80 }} />
            </colgroup>
            <thead>
              <tr>
                <TH />
                <TH onClick={() => handleSort('lb')}       sorted={sortCol === 'lb'       ? sortDir : null}>LB#</TH>
                <TH onClick={() => handleSort('date')}     sorted={sortCol === 'date'     ? sortDir : null}>Date</TH>
                <TH onClick={() => handleSort('location')} sorted={sortCol === 'location' ? sortDir : null}>Location</TH>
                <TH>Description</TH>
                <TH align="center">Rating</TH>
                <TH>Added</TH>
                <TH>Notes</TH>
                <TH align="center">Priority</TH>
              </tr>
            </thead>
            <tbody>
              {sortedFilteredRows.map(r => {
                const isEditing = wishEditId === r.lbNumber
                return (
                  <TR
                    key={r.lbNumber}
                    selected={selectedId === r.lbNumber}
                    onClick={() => setSelectedId(selectedId === r.lbNumber ? null : r.lbNumber)}
                    onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, row: r }) }}
                  >
                    <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{r.lbNumber}</TD>
                    <TD mono>{r.date || '—'}</TD>
                    <TD>{r.location || '—'}</TD>
                    <TD dim>{r.title || '—'}</TD>
                    <TD align="center" mono>{r.rating || '—'}</TD>
                    <TD mono dim>{r.wishlistAddedAt || '—'}</TD>
                    <TD>
                      {isEditing ? (
                        <input
                          autoFocus
                          value={wishEditNotes}
                          onChange={e => setWishEditNotes(e.target.value)}
                          onBlur={() => handleWishlistUpdate(r.lbNumberInt, wishEditPriority, wishEditNotes)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleWishlistUpdate(r.lbNumberInt, wishEditPriority, wishEditNotes)
                            if (e.key === 'Escape') setWishEditId(null)
                          }}
                          style={{
                            width: '100%', background: 'var(--lbb-input-bg)', color: 'var(--lbb-fg)',
                            border: '1px solid var(--lbb-accent-mid)', borderRadius: 3, fontSize: 'var(--lbb-fs-12)',
                            padding: '2px 6px', fontFamily: 'inherit',
                          }}
                        />
                      ) : (
                        <span
                          title="Click to edit"
                          style={{ cursor: 'text', color: r.wishlistNotes ? 'var(--lbb-fg2)' : 'var(--lbb-fg3)' }}
                          onClick={e => {
                            e.stopPropagation()
                            setWishEditId(r.lbNumber)
                            setWishEditPriority(r.wishlistPriority ?? 3)
                            setWishEditNotes(r.wishlistNotes)
                          }}
                        >
                          {r.wishlistNotes || '—'}
                        </span>
                      )}
                    </TD>
                    <TD align="center">
                      {isEditing ? (
                        <select
                          value={wishEditPriority}
                          onChange={e => setWishEditPriority(Number(e.target.value))}
                          style={{
                            background: 'var(--lbb-input-bg)', color: 'var(--lbb-fg)',
                            border: '1px solid var(--lbb-border)', borderRadius: 3, fontSize: 'var(--lbb-fs-12)',
                          }}
                        >
                          {[1,2,3,4,5].map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                      ) : (
                        <span
                          style={{ cursor: 'pointer' }}
                          onClick={e => {
                            e.stopPropagation()
                            setWishEditId(r.lbNumber)
                            setWishEditPriority(r.wishlistPriority ?? 3)
                            setWishEditNotes(r.wishlistNotes)
                          }}
                        >
                          <Pill
                            tone={r.wishlistPriority != null && r.wishlistPriority >= 4 ? 'ok' : r.wishlistPriority === 1 ? 'mute' : 'info'}
                            soft
                          >
                            {r.wishlistPriority ?? 3}
                          </Pill>
                        </span>
                      )}
                    </TD>
                  </TR>
                )
              })}
            </tbody>
          </TableShell>
          {sortedFilteredRows.length === 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60%', fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)' }}>
              No wishlist entries.
            </div>
          )}
        </div>
        )}

        {/* Duplicates grouped tree */}
        {filter === 'duplicates' && (
        <div style={{ overflow: 'auto', minHeight: 0 }}>
          {duplicateGroups.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60%', fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)' }}>
              No duplicate entries.
            </div>
          ) : (
            <TableShell stickyHeader>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 50 }} />
                <col />
                <col style={{ width: 160 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH />
                  <TH>LB#</TH>
                  <TH>Owned</TH>
                  <TH align="center">Rating</TH>
                  <TH>Description</TH>
                  <TH>Actions</TH>
                </tr>
              </thead>
              <tbody>
                {duplicateGroups.map(g => {
                  const key = `${g.date_str}::${g.location}`
                  const isOpen = !dupExpanded.has(key)
                  return (
                    <React.Fragment key={key}>
                      <GroupRow
                        label={`${g.date_str} · ${g.location}`}
                        count={g.owned.length}
                        expanded={isOpen}
                        onToggle={() => setDupExpanded(prev => {
                          const next = new Set(prev)
                          if (next.has(key)) next.delete(key); else next.add(key)
                          return next
                        })}
                        colSpan={5}
                      />
                      {isOpen && g.owned.map(o => {
                        const lbStr = `LB-${String(o.lb_number).padStart(5, '0')}`
                        const collRow = rows.find(r => r.lbNumberInt === o.lb_number)
                        return (
                          <TR
                            key={o.lb_number}
                            selected={selectedId === lbStr}
                            onClick={() => setSelectedId(selectedId === lbStr ? null : lbStr)}
                          >
                            <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{lbStr}</TD>
                            <TD>
                              <Pill tone="ok" soft dot>Owned</Pill>
                            </TD>
                            <TD align="center" mono>{o.rating || '—'}</TD>
                            <TD dim>{o.description || '—'}</TD>
                            <TD>
                              <div style={{ display: 'flex', gap: 4 }}>
                                <Button variant="ghost" size="sm" onClick={() => {
                                  clearSources(); addSource({ label: lbStr, lbNumber: o.lb_number }); navigate('/lookup')
                                }}>
                                  LosslessBob
                                </Button>
                                {collRow?.diskPath && (
                                  <Button variant="ghost" size="sm" onClick={() => window.api.openPath(collRow.diskPath)}>
                                    Open
                                  </Button>
                                )}
                                <Button variant="danger" size="sm" onClick={() => {
                                  setConfirm({
                                    title: `Remove ${lbStr}?`,
                                    body: 'Remove from your collection? Files on disk will not be deleted.',
                                    onConfirm: async () => {
                                      setConfirm(null)
                                      await fetch(`${BASE}/api/collection/${o.lb_number}`, { method: 'DELETE' })
                                      showToast(`Removed ${lbStr}`, 'ok')
                                      refetch()
                                    },
                                  })
                                }}>
                                  Remove
                                </Button>
                              </div>
                            </TD>
                          </TR>
                        )
                      })}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </TableShell>
          )}
        </div>
        )}

        {/* Owned-collection Table */}
        {filter !== 'not_owned' && filter !== 'forum_global' && filter !== 'torrent_global' && filter !== 'wishlist' && filter !== 'duplicates' && (
        <div ref={tableParentRef} style={{ overflow: 'auto', minHeight: 0, position: 'relative' }}>
          <TableShell stickyHeader>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 220 }} />
              <col style={{ width: 180 }} />
              <col style={{ width: 160 }} />
              <col style={{ width: 120 }} />
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
                <TH onClick={() => handleSort('lb')}        sorted={sortCol === 'lb'        ? sortDir : null}>{t('collection.table.lb')}</TH>
                <TH onClick={() => handleSort('status')}    sorted={sortCol === 'status'    ? sortDir : null}>{t('collection.table.status')}</TH>
                <TH onClick={() => handleSort('date')}      sorted={sortCol === 'date'      ? sortDir : null}>{t('collection.table.date')}</TH>
                <TH onClick={() => handleSort('location')}  sorted={sortCol === 'location'  ? sortDir : null}>{t('collection.table.location')}</TH>
                <TH onClick={() => handleSort('folder')}    sorted={sortCol === 'folder'    ? sortDir : null}>{t('collection.table.folder')}</TH>
                <TH onClick={() => handleSort('diskPath')}  sorted={sortCol === 'diskPath'  ? sortDir : null}>{t('collection.detail.diskPath')}</TH>
                <TH>Notes</TH>
                <TH onClick={() => handleSort('confirmed')} sorted={sortCol === 'confirmed' ? sortDir : null}>{t('collection.detail.confirmed')}</TH>
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
                      const r = sortedFilteredRows[vItem.index]
                      if (!r) return null
                      const isSelected = selectedId === r.lbNumber
                      const isChecked  = checkedIds.has(r.lbNumber)
                      return (
                        <TR
                          key={r.lbNumber}
                          edge={edgeFor(r.status)}
                          selected={isSelected}
                          onClick={() => setSelectedId(isSelected ? null : r.lbNumber)}
                          onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, row: r }) }}
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
                          <TD dim>{r.notes || '—'}</TD>
                          <TD mono dim>{r.confirmed || '—'}</TD>
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
                <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                  No recordings in your collection
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', marginTop: 4 }}>
                  Use "Add single folder" to get started
                </div>
              </div>
            </div>
          )}
        </div>
        )}

        {/* Detail panel */}
        {filter !== 'not_owned' && filter !== 'forum_global' && filter !== 'torrent_global' && selectedRow && (
          <DetailPanel
            row={selectedRow}
            historyTab={historyTab}
            onHistoryTab={setHistoryTab}
            onClose={() => setSelectedId(null)}
            onReveal={handleReveal}
            onRegenTorrent={handleRegenTorrent}
            onPostForum={handlePostForum}
            onWishlistToggle={handleWishlistToggle}
            onPersonalInfo={(lb, lbNumber) => setPersonalModal({ lb, lbNumber })}
            personalMetaVersion={personalSaveVer}
            onToast={showToast}
            onRefetch={refetch}
            onSpectrograms={handleCtxSpectrograms}
            onNavigate={navigate}
          />
        )}
      </div>

      {/* ── Overlays ──────────────────────────────────────────────────────────── */}

      {toast && (
        <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />
      )}

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}

      {scanPreviewModal && (
        <ScanPreviewModal
          entries={scanPreviewModal.entries}
          skipped={scanPreviewModal.skipped}
          onClose={() => setScanPreviewModal(null)}
          onAdded={refetch}
        />
      )}

      {addModal && (
        <AddFolderModal
          paths={addModal.paths}
          onClose={() => setAddModal(null)}
          onAdded={refetch}
        />
      )}

      {forumModal && (
        <ForumModal
          lb={forumModal.lb}
          subject={forumModal.subject}
          body={forumModal.body}
          onClose={() => setForumModal(null)}
          onPosted={handleForumPosted}
        />
      )}

      {ctxMenu && (
        <ContextMenu
          state={ctxMenu}
          onClose={() => setCtxMenu(null)}
          items={[
            {
              label: 'Open Folder',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxOpenFolder(ctxMenu.row),
            },
            {
              label: 'View LB Entry',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxViewLookup(ctxMenu.row),
            },
            'sep',
            {
              label: 'Post to forum',
              action: () => handleCtxPostForum(ctxMenu.row),
            },
            {
              label: 'Create torrent',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxCreateTorrent(ctxMenu.row),
            },
            {
              label: 'Add to qBittorrent',
              action: () => handleCtxAddToQbt(ctxMenu.row),
            },
            'sep',
            {
              label: 'Scrape Entry',
              action: () => handleCtxScrape(ctxMenu.row),
            },
            {
              label: 'Fingerprint Folder',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxFingerprint(ctxMenu.row),
            },
            {
              label: 'Play in VLC',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxVlc(ctxMenu.row),
            },
            {
              label: 'Generate Spectrograms',
              disabled: !ctxMenu.row.diskPath,
              action: () => handleCtxSpectrograms(ctxMenu.row),
            },
            'sep',
            {
              label: 'Edit Personal Info…',
              action: () => setPersonalModal({ lb: ctxMenu.row.lbNumber, lbNumber: ctxMenu.row.lbNumberInt }),
            },
          ]}
        />
      )}

      {personalModal && (
        <PersonalInfoModal
          lb={personalModal.lb}
          lbNumber={personalModal.lbNumber}
          onClose={() => setPersonalModal(null)}
          onSaved={msg => { showToast(msg, 'ok'); setPersonalSaveVer(v => v + 1) }}
        />
      )}

    </div>
  )
}
