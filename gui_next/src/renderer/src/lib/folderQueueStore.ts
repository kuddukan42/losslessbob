import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface FolderQueueStore {
  folders:       string[]
  addFolders:    (paths: string[]) => void
  removeFolders: (paths: string[]) => void
  clearFolders:  () => void
}

// TODO-205 Phase 7: persist the queued paths client-side (localStorage) so the
// work queue survives an app restart. Verdicts are NOT stored here — they live
// server-side in pipeline_folder_state and are re-served from the P7 cache on
// the next run. Two-part by design: cheap path list local, expensive verdicts
// in SQLite. Mirrors useSettingsStore's 'lbb-settings' persist.
export const useFolderQueueStore = create<FolderQueueStore>()(
  persist(
    (set) => ({
      folders: [],
      addFolders: (paths) => set(state => ({
        folders: [...new Set([...state.folders, ...paths])],
      })),
      removeFolders: (paths) => set(state => ({
        folders: state.folders.filter(f => !paths.includes(f)),
      })),
      clearFolders: () => set({ folders: [] }),
    }),
    { name: 'lbb-pipeline-queue' }
  )
)
