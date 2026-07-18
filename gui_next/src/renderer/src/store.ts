import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type DossierChannel = 'public' | 'full'
export type DossierFormat = 'html' | 'pdf'

interface SettingsStore {
  curatorMode: boolean
  setCuratorMode: (v: boolean) => void
  language: string
  setLanguage: (lang: string) => void
  rowHighlight: boolean
  setRowHighlight: (v: boolean) => void
  // Show dossier export (FABLE_SHOW_DOSSIER.md D4) — remembers the curator's
  // last choices across exports, same pattern as the other persisted prefs.
  dossierChannel: DossierChannel
  setDossierChannel: (v: DossierChannel) => void
  dossierIncludeContext: boolean
  setDossierIncludeContext: (v: boolean) => void
  dossierIncludeSetlist: boolean
  setDossierIncludeSetlist: (v: boolean) => void
  dossierIncludeLocalAnalysis: boolean
  setDossierIncludeLocalAnalysis: (v: boolean) => void
  dossierFormat: DossierFormat
  setDossierFormat: (v: DossierFormat) => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      curatorMode: false,
      setCuratorMode: (v) => set({ curatorMode: v }),
      language: 'en',
      setLanguage: (lang) => set({ language: lang }),
      rowHighlight: true,
      setRowHighlight: (v) => set({ rowHighlight: v }),
      dossierChannel: 'public',
      setDossierChannel: (v) => set({ dossierChannel: v }),
      dossierIncludeContext: true,
      setDossierIncludeContext: (v) => set({ dossierIncludeContext: v }),
      dossierIncludeSetlist: true,
      setDossierIncludeSetlist: (v) => set({ dossierIncludeSetlist: v }),
      dossierIncludeLocalAnalysis: true,
      setDossierIncludeLocalAnalysis: (v) => set({ dossierIncludeLocalAnalysis: v }),
      dossierFormat: 'html',
      setDossierFormat: (v) => set({ dossierFormat: v }),
    }),
    { name: 'lbb-settings' }
  )
)
