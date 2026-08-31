// ── Shared library action system ──────────────────────────────────────────────
// The `ActionHandlers` bag (open / play / reveal / seed / share / assets /
// maintain) plus the overlay UI those handlers drive (context menu, toast,
// confirm dialog, dossier export modal).
//
// Originally inline in ScreenLibrary.tsx; extracted so the My Collection screen
// can mount the *same* RecordingDetailPanel with the *same* behavior instead of
// keeping a parallel implementation of the same endpoints.

import React, { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Toast, ConfirmDialog } from '../components'
import type { ToastTone } from '../components'
import { ActionMenu, useActionMenu } from '../components/library/actions'
import type { ActionRow, ActionHandlers, LibAction } from '../components/library/actions'
import { DossierExportModal } from '../components/library/DossierExportModal'
import { useAttachmentsStore } from './attachmentsStore'
import { useSpectrogramStore } from './spectrogramStore'
import { useFolderQueueStore } from './folderQueueStore'
import { lbDetailUrl } from './lbUrl'

const BASE = window.api.flaskBase

function blobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export interface LibraryActions {
  /** Handler bag consumed by buildRecordingActions / the detail panels. */
  actionHandlers: ActionHandlers
  /** Context-menu opener with the signature the detail panels expect. */
  openCtxMenu: (e: React.MouseEvent, title: string | undefined, actions: LibAction[]) => void
  /** True while a multi-row action is running — drives panel button `busy`. */
  actionBusy: boolean
  showToast: (msg: string, tone: ToastTone) => void
  /** Invalidates the catalog + collection caches both screens read. */
  refreshCollection: () => void
  /** Render once per screen root: menu, toast, confirm, dossier modal. */
  overlays: React.ReactNode
}

/**
 * Build the shared library action handlers and their overlay UI.
 *
 * Returns:
 *     A `LibraryActions` bag. `overlays` must be rendered exactly once per
 *     screen root, otherwise the menus/dialogs these handlers open are invisible.
 */
export function useLibraryActions(): LibraryActions {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setActiveAttachLb = useAttachmentsStore(s => s.setActiveLb)
  const addPendingSpectro = useSpectrogramStore(s => s.addPending)
  const addToFolderQueue = useFolderQueueStore(s => s.addFolders)

  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; body: string; onConfirm: () => void } | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [dossierShowId, setDossierShowId] = useState<string | null>(null)
  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])
  const refreshCollection = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['library-catalog'] })
    queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] })
  }, [queryClient])

  const actionHandlers = useMemo<ActionHandlers>(() => ({
    onOpen: (row) => {
      window.open(lbDetailUrl(row.lbNumber), '_blank')
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
        if (!data.ok) showToast(data.error || t('library.toast.vlcNotFound'), 'bad')
      } catch { showToast(t('library.toast.vlcFailed'), 'bad') }
    },
    onReveal: async (row) => {
      if (!row.path) { showToast(t('library.toast.noDiskPath'), 'info'); return }
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
        showToast(t('library.toast.qbtAdded', { added: data.added ?? 0, total: data.total ?? lbs.length }), data.ok ? 'ok' : 'bad')
      } catch { showToast(t('library.toast.qbtFailed'), 'bad') }
    },
    onTorrent: async (rows) => {
      const targets = rows.filter(r => r.path)
      if (!targets.length) { showToast(t('library.toast.noDiskPath'), 'info'); return }
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
      showToast(t('library.toast.torrentsCreated', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : ''), ok > 0 ? 'ok' : 'bad')
    },
    onForum: (rows) => {
      const postOne = async (r: ActionRow): Promise<{ ok: boolean; topicUrl: string }> => {
        try {
          const previewResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/preview_forum`)
          const previewData = await previewResp.json()
          const postResp = await fetch(`${BASE}/api/entry/${r.lbNumber}/post_forum`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject: previewData.subject ?? '', body: previewData.body ?? '' }),
          })
          const data = await postResp.json()
          return { ok: !!data.ok, topicUrl: data.topic_url ?? '' }
        } catch { return { ok: false, topicUrl: '' } }
      }
      const copyUrls = (urls: string[]): Promise<boolean> => {
        if (urls.length === 0) return Promise.resolve(false)
        return navigator.clipboard.writeText(urls.join('\n')).then(() => true, () => false)
      }
      if (rows.length === 1) {
        postOne(rows[0]).then(async ({ ok, topicUrl }) => {
          if (ok && topicUrl && await copyUrls([topicUrl])) {
            showToast(t('library.toast.postedForumCopied', { lb: rows[0].lb }), 'ok')
          } else {
            showToast(ok ? t('library.toast.postedForum', { lb: rows[0].lb }) : t('library.toast.forumPostFailed'), ok ? 'ok' : 'bad')
          }
        })
        return
      }
      setConfirm({
        title: t('library.ctx.postForum'),
        body: t('library.toast.confirmForumBody', { count: rows.length }),
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          const urls: string[] = []
          for (const r of rows) {
            const res = await postOne(r)
            if (res.ok) { ok++; if (res.topicUrl) urls.push(res.topicUrl) } else fail++
          }
          const copied = await copyUrls(urls)
          setActionBusy(false)
          const base = t('library.toast.postsCreated', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : '')
          showToast(ok > 0 && copied ? base + t('library.toast.linksCopiedSuffix', { count: urls.length }) : base, ok > 0 ? 'ok' : 'bad')
        },
      })
    },
    // Seeds one recording to WTRF: the backend finds the entry's forum post,
    // downloads its .torrent and runs the shared seeding gates, which never
    // point qBittorrent at an incomplete collection folder. The forum search
    // is slow (paced requests against a small hobbyist board), so the toast
    // reports rather than blocking on a progress surface.
    onSeedWtrf: async (row) => {
      if (!row.path) { showToast(t('library.toast.noDiskPath'), 'info'); return }
      setActionBusy(true)
      try {
        const resp = await fetch(`${BASE}/api/entry/${row.lbNumber}/seed_wtrf`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })
        const data = await resp.json()
        if (data.ok) {
          showToast(t('library.toast.wtrfSeeded', {
            lb: row.lb,
            where: data.overlay ? t('library.toast.wtrfViaOverlay') : t('library.toast.wtrfInPlace'),
          }), 'ok')
        } else {
          showToast(t('library.toast.wtrfSeedFailed', {
            lb: row.lb, reason: data.error || data.reason || '',
          }), 'bad')
        }
      } catch (e) {
        showToast(t('library.toast.wtrfSeedFailed', { lb: row.lb, reason: (e as Error).message }), 'bad')
      } finally {
        setActionBusy(false)
      }
    },
    onM3u: async (rows) => {
      const lbs = rows.map(r => r.lbNumber)
      if (!lbs.length) { showToast(t('library.toast.noOwnedExport'), 'info'); return }
      try {
        const resp = await fetch(`${BASE}/api/collection/export/m3u?lb_numbers=${lbs.join(',')}`)
        const blob = await resp.blob()
        blobDownload(blob, 'show.m3u')
      } catch { showToast(t('library.toast.m3uFailed'), 'bad') }
    },
    onDossier: (showId) => setDossierShowId(showId),
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
        else showToast(data.error || t('library.toast.spectroFailed'), 'bad')
      } catch { showToast(t('library.toast.spectroFailed'), 'bad') }
    },
    onMap: () => navigate('/map'),
    onReconfirm: (row) => {
      if (!row.path) return
      addToFolderQueue([row.path])
      navigate('/pipeline')
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
          showToast(t('library.toast.locationUpdated', { lb: target.lb }), 'ok')
          refreshCollection()
        } catch { showToast(t('library.toast.updateFailed'), 'bad') }
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
      showToast(t('library.toast.updated', { count: ok }) + (skip > 0 ? t('library.toast.notFoundSuffix', { count: skip }) : ''), ok > 0 ? 'ok' : 'info')
      if (ok > 0) refreshCollection()
    },
    onRemove: (rows) => {
      if (!rows.length) return
      setConfirm({
        title: t('library.ctx.removeCollection'),
        body: t('library.toast.confirmRemoveBody', { count: rows.length }),
        onConfirm: async () => {
          setConfirm(null)
          setActionBusy(true)
          let ok = 0; let fail = 0
          for (const r of rows) {
            try { await fetch(`${BASE}/api/collection/${r.lbNumber}`, { method: 'DELETE' }); ok++ } catch { fail++ }
          }
          setActionBusy(false)
          showToast(t('library.toast.removed', { count: ok }) + (fail > 0 ? t('library.toast.failedSuffix', { count: fail }) : ''), ok > 0 ? 'ok' : 'bad')
          refreshCollection()
        },
      })
    },
    onWishlistToggle: async (row) => {
      try {
        if (row.wish) {
          await fetch(`${BASE}/api/wishlist/${row.lbNumber}`, { method: 'DELETE' })
          showToast(t('library.toast.wishlistRemoved', { lb: row.lb }), 'ok')
        } else {
          await fetch(`${BASE}/api/wishlist`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lb_number: row.lbNumber }),
          })
          showToast(t('library.toast.wishlistAdded', { lb: row.lb }), 'ok')
        }
        refreshCollection()
      } catch { showToast(t('library.toast.wishlistFailed'), 'bad') }
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
      showToast(t('library.toast.wishlistAddedCount', { count: ok }), ok > 0 ? 'ok' : 'bad')
      if (ok > 0) refreshCollection()
    },
  }), [t, showToast, refreshCollection, navigate, setActiveAttachLb, addPendingSpectro, addToFolderQueue])

  const { menu: ctxMenu, openMenu: openCtxMenu, closeMenu: closeCtxMenu } = useActionMenu()

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
      {dossierShowId && (
        <DossierExportModal
          showId={dossierShowId}
          base={BASE}
          onClose={() => setDossierShowId(null)}
          showToast={showToast}
        />
      )}
    </>
  )

  return { actionHandlers, openCtxMenu, actionBusy, showToast, refreshCollection, overlays }
}
