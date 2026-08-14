// Sidebar nav visibility — user-controlled show/hide per nav item, set from
// the About dialog's Options tab. Persists like savedViewsStore (plain JSON).
// 'home' is never hideable (it's the app's only ungrouped landing screen).

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { NavId } from './navigation'

interface NavVisibilityStore {
  hidden: NavId[]
  toggle: (id: NavId) => void
}

export const useNavVisibilityStore = create<NavVisibilityStore>()(persist((set) => ({
  hidden: [],
  toggle: (id) => set((s) => ({
    hidden: s.hidden.includes(id) ? s.hidden.filter((h) => h !== id) : [...s.hidden, id],
  })),
}), {
  name: 'lbb-nav-visibility',
}))
