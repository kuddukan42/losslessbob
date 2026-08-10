// ── Detail-panel side data ────────────────────────────────────────────────────
// The two lb_number-keyed maps RecordingDetailPanel/PerformanceDetailPanel take
// as props: seed/share history and attachment counts. Both ride existing
// endpoints (`/api/collection/prefetch`, `/api/attachments/cached`) under the
// query keys the Library and My Collection screens already share, so mounting
// these from a second screen costs no extra fetch.

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { RowHistory } from '../components/library/DetailPanel'

const BASE = window.api.flaskBase

/**
 * Seed/share history per LB number, grouped from the collection prefetch.
 *
 * Returns:
 *     Map of lb_number → {torrents, forum} event lists (empty while loading).
 */
export function useLibraryHistoryMap(): Map<number, RowHistory> {
  const { data: prefetch } = useQuery({
    queryKey: ['collection-prefetch'],
    queryFn: () => fetch(`${BASE}/api/collection/prefetch`).then(r => r.json()),
    staleTime: Infinity,
  })

  return useMemo(() => {
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
}

/**
 * Attachment file counts per LB number.
 *
 * Returns:
 *     Map of lb_number → number of attached files (empty while loading).
 */
export function useAttachCountMap(): Map<number, number> {
  const { data: attachData } = useQuery({
    queryKey: ['library-attachments-cached'],
    queryFn: () => fetch(`${BASE}/api/attachments/cached`).then(r => r.json()),
    staleTime: 60_000,
  })

  return useMemo(() => {
    const m = new Map<number, number>()
    if (Array.isArray(attachData?.entries)) {
      for (const e of attachData.entries) m.set(e.lb_number, (e.files ?? []).length)
    }
    return m
  }, [attachData])
}
