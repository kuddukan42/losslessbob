// Saved smart views (UI5 / FABLE_IDEAS UI#5).
//
// A saved view is a named snapshot of the Library recording-lens filter set,
// pinned in the sidebar with a live count badge. RecordingFilters stores its
// selections as arrays (not Sets), so this store persists as plain JSON — no
// custom replacer needed.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { RecordingFilters } from './libraryRows'

export interface SavedView {
  id: string
  name: string
  filters: RecordingFilters
}

interface SavedViewsStore {
  views: SavedView[]
  addView: (name: string, filters: RecordingFilters) => void
  renameView: (id: string, name: string) => void
  removeView: (id: string) => void
}

function makeId(): string {
  return `sv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

export const useSavedViewsStore = create<SavedViewsStore>()(persist((set) => ({
  views: [],
  addView: (name, filters) => set((s) => ({
    views: [...s.views, { id: makeId(), name: name.trim() || 'Untitled view', filters }],
  })),
  renameView: (id, name) => set((s) => ({
    views: s.views.map(v => v.id === id ? { ...v, name: name.trim() || v.name } : v),
  })),
  removeView: (id) => set((s) => ({ views: s.views.filter(v => v.id !== id) })),
}), {
  name: 'lbb-saved-views',
}))
