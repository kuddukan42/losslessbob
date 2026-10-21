// Paced bulk qBittorrent add (TODO-330): result reporting + tracker-status panel.
// POST /api/qbt/add with several LBs adds paused and releases in the background;
// the panel polls POST /api/qbt/tracker_status for the hashes of the last bulk add.

import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { create } from 'zustand'

import { BASE } from './api'
import { Button } from '../components'

interface QbtBulkState {
  hashes: string[]
  open: boolean
  setHashes: (h: string[]) => void
  setOpen: (o: boolean) => void
}

export const useQbtBulkStore = create<QbtBulkState>((set) => ({
  hashes: [],
  open: false,
  setHashes: (hashes) => set({ hashes }),
  setOpen: (open) => set({ open }),
}))

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TFn = (key: any, opts?: any) => string

/** Build the toast for a /api/qbt/add response and remember paced hashes. */
export function qbtAddSummary(
  data: Record<string, any>, fallbackTotal: number, t: TFn,
): { msg: string; tone: 'ok' | 'bad' | 'info' } {
  if (!data.ok) return { msg: data.error || t('qbtBulk.failed'), tone: 'bad' }
  let msg = t('library.toast.qbtAdded', { added: data.added ?? 0, total: data.total ?? fallbackTotal })
  if (data.paced) {
    const hashes = (data.results ?? [])
      .filter((r: any) => r.ok && r.infohash).map((r: any) => r.infohash as string)
    useQbtBulkStore.getState().setHashes(hashes)
    msg += ' ' + t('qbtBulk.pacedRelease', {
      pending: data.release?.pending ?? 0,
      batch: data.release?.batch_size ?? 0,
      interval: data.release?.interval_s ?? 0,
    })
  }
  const skipped = (data.skipped ?? []).length
  if (skipped) msg += ' ' + t('qbtBulk.skipped', { count: skipped })
  if (data.warning) msg += ' ' + data.warning
  return { msg, tone: skipped || data.warning ? 'info' : 'ok' }
}

function stateLabel(t: TFn, s: string): string {
  switch (s) {
    case 'working': return t('qbtBulk.state.working')
    case 'not_working': return t('qbtBulk.state.not_working')
    case 'not_contacted': return t('qbtBulk.state.not_contacted')
    case 'updating': return t('qbtBulk.state.updating')
    case 'disabled': return t('qbtBulk.state.disabled')
    case 'no_trackers': return t('qbtBulk.state.no_trackers')
    case 'pending': return t('qbtBulk.state.pending')
    default: return t('qbtBulk.state.unknown')
  }
}

interface TrackerRow{ state: string; trackers: { url: string; status: string; msg: string }[]; error: string | null }

/** Modal listing per-torrent tracker state for the last paced bulk add. */
export function QbtTrackerPanel(): React.ReactElement | null {
  const { t } = useTranslation()
  const { hashes, open, setOpen } = useQbtBulkStore()
  const [status, setStatus] = useState<Record<string, TrackerRow>>({})
  const [err, setErr] = useState('')

  const poll = useCallback(async () => {
    try {
      const resp = await fetch(`${BASE}/api/qbt/tracker_status`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hashes }),
      })
      const data = await resp.json()
      if (data.ok) { setStatus(data.status); setErr('') } else setErr(data.error || '')
    } catch { setErr(t('qbtBulk.failed')) }
  }, [hashes, t])

  useEffect(() => {
    if (!open || !hashes.length) return
    void poll()
    const id = setInterval(() => { void poll() }, 15000)
    return () => clearInterval(id)
  }, [open, hashes, poll])

  if (!hashes.length) return null
  if (!open) {
    return (
      <div style={{ position: 'fixed', right: 16, bottom: 40, zIndex: 50 }}>
        <Button size="sm" icon="info" onClick={() => setOpen(true)}>
          {t('qbtBulk.showStatus', { count: hashes.length })}
        </Button>
      </div>
    )
  }
  return (
    <div role="dialog" style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--lbb-surface)', color: 'var(--lbb-fg)',
        border: '1px solid var(--lbb-border)', borderRadius: 10, padding: 20,
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)', fontSize: 'var(--lbb-fs-12)',
        width: 'min(720px, 92vw)', maxHeight: '80vh', overflow: 'auto' }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 600, marginBottom: 10 }}>
          {t('qbtBulk.title')}
        </div>
        {err && <div style={{ color: 'var(--lbb-bad-fg)' }}>{err}</div>}
        {hashes.map((h) => {
          const row = status[h]
          const bad = row?.state === 'not_working'
          return (
            <div key={h} data-state={row?.state ?? 'pending'}
              style={{ padding: '4px 0', color: bad ? 'var(--lbb-bad-fg)' : undefined,
                fontWeight: bad ? 600 : undefined }}>
              <code style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)' }}>
                {h.slice(0, 10)}
              </code>{' '}
              {stateLabel(t, row?.state ?? 'pending')}
              {row?.trackers?.map((tr, i) => tr.msg
                ? <div key={i} style={{ paddingLeft: 12, fontWeight: 400 }}>{tr.msg}</div> : null)}
              {row?.error && <div style={{ paddingLeft: 12, fontWeight: 400 }}>{row.error}</div>}
            </div>
          )
        })}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
          <Button size="sm" onClick={() => setOpen(false)}>{t('qbtBulk.close')}</Button>
        </div>
      </div>
    </div>
  )
}
