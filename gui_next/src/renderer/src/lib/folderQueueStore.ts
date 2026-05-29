import { create } from 'zustand'

interface FolderQueueStore {
  folders:       string[]
  addFolders:    (paths: string[]) => void
  removeFolders: (paths: string[]) => void
  clearFolders:  () => void
}

export const useFolderQueueStore = create<FolderQueueStore>(set => ({
  folders: [],
  addFolders: (paths) => set(state => ({
    folders: [...new Set([...state.folders, ...paths])],
  })),
  removeFolders: (paths) => set(state => ({
    folders: state.folders.filter(f => !paths.includes(f)),
  })),
  clearFolders: () => set({ folders: [] }),
}))
