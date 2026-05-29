import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  curatorMode: boolean
  setCuratorMode: (v: boolean) => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      curatorMode: false,
      setCuratorMode: (v) => set({ curatorMode: v }),
    }),
    { name: 'lbb-settings' }
  )
)
