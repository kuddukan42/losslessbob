import { create } from 'zustand'

export interface SpectroTrack {
  audio_file: string
  audio_name: string
  png_path:   string | null
  has_png:    boolean
}

interface SpectrogramStore {
  // Screen state — persists across navigation
  folders:       string[]
  activeFolder:  string | null
  inventory:     Record<string, SpectroTrack[]>
  activeTrack:   SpectroTrack | null
  filter:        string
  width:         string
  height:        string
  dynRange:      string
  forceRerender: boolean
  zoom:          number
  // Cross-screen queuing (Verify → Spectrograms)
  pendingFolders: string[]
  // Actions
  setFolders:       (updater: string[] | ((prev: string[]) => string[])) => void
  setActiveFolder:  (folder: string | null) => void
  setInventory:     (inv: Record<string, SpectroTrack[]>) => void
  setActiveTrack:   (track: SpectroTrack | null) => void
  setFilter:        (v: string) => void
  setWidth:         (v: string) => void
  setHeight:        (v: string) => void
  setDynRange:      (v: string) => void
  setForceRerender: (v: boolean) => void
  setZoom:          (updater: number | ((prev: number) => number)) => void
  addPending:       (folders: string[]) => void
  takePending:      () => string[]
}

export const useSpectrogramStore = create<SpectrogramStore>((set, get) => ({
  folders:        [],
  activeFolder:   null,
  inventory:      {},
  activeTrack:    null,
  filter:         '',
  width:          '1500',
  height:         '400',
  dynRange:       '-120',
  forceRerender:  false,
  zoom:           100,
  pendingFolders: [],
  setFolders: (updater) => set(state => ({
    folders: typeof updater === 'function' ? updater(state.folders) : updater,
  })),
  setActiveFolder:  (activeFolder) => set({ activeFolder }),
  setInventory:     (inventory) => set({ inventory }),
  setActiveTrack:   (activeTrack) => set({ activeTrack }),
  setFilter:        (filter) => set({ filter }),
  setWidth:         (width) => set({ width }),
  setHeight:        (height) => set({ height }),
  setDynRange:      (dynRange) => set({ dynRange }),
  setForceRerender: (forceRerender) => set({ forceRerender }),
  setZoom: (updater) => set(state => ({
    zoom: typeof updater === 'function' ? updater(state.zoom) : updater,
  })),
  addPending: folders => set(state => ({
    pendingFolders: [...new Set([...state.pendingFolders, ...folders])],
  })),
  takePending: () => {
    const folders = get().pendingFolders
    set({ pendingFolders: [] })
    return folders
  },
}))
