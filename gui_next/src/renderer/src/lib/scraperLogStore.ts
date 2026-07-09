import { create } from 'zustand'

export type ScraperTabId = 'crawler' | 'entry' | 'bootlegs' | 'bobdylan' | 'setlistfm' | 'geocoder'

export interface ScraperLogLine { ts: string; text: string; tone?: 'ok' | 'bad' | 'warn' | 'mute' }

const MAX_LINES = 500

interface ScraperLogStore {
  logs: Record<ScraperTabId, ScraperLogLine[]>
  pushLog: (tab: ScraperTabId, text: string, tone?: ScraperLogLine['tone']) => void
  clearLog: (tab: ScraperTabId) => void
}

// Module-level store (not React state) so the live log survives ScreenScraper
// unmounting when the user navigates to another top-level tab and back —
// TODO-148. Intentionally not persisted to localStorage: this is a run-session
// buffer, not durable state.
export const useScraperLogStore = create<ScraperLogStore>()((set) => ({
  logs: { crawler: [], entry: [], bootlegs: [], bobdylan: [], setlistfm: [], geocoder: [] },
  pushLog: (tab, text, tone) => set(state => ({
    logs: { ...state.logs, [tab]: [...state.logs[tab], { ts: new Date().toTimeString().slice(0, 8), text, tone }].slice(-MAX_LINES) },
  })),
  clearLog: (tab) => set(state => ({ logs: { ...state.logs, [tab]: [] } })),
}))
