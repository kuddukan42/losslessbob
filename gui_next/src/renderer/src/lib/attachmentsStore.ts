import { create } from 'zustand'

export type LbStatus = 'current' | 'stale' | 'missing'

interface AttachmentsStore {
  activeLb:     number | null
  search:       string
  statusFilter: LbStatus | 'all'
  setActiveLb:     (lb: number | null) => void
  setSearch:       (v: string) => void
  setStatusFilter: (v: LbStatus | 'all') => void
}

export const useAttachmentsStore = create<AttachmentsStore>(set => ({
  activeLb:     null,
  search:       '',
  statusFilter: 'all',
  setActiveLb:     (activeLb) => set({ activeLb }),
  setSearch:       (search) => set({ search }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),
}))
