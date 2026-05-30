import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  curatorMode: boolean
  setCuratorMode: (v: boolean) => void
  language: string
  setLanguage: (lang: string) => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      curatorMode: false,
      setCuratorMode: (v) => set({ curatorMode: v }),
      language: 'en',
      setLanguage: (lang) => set({ language: lang }),
    }),
    { name: 'lbb-settings' }
  )
)
