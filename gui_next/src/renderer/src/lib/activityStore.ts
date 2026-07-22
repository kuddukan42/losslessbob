import { create } from 'zustand'

// Shared activity-tray store (TODO-262 / FABLE_ACTIVITY_CENTER.md §A3, B3).
// Polls `GET /api/activity/jobs` — the same normalized shape backend/activity.py
// serves for both the status-bar dot and the tray popover. This module owns the
// only poll loop in the app for that route; StatusBar starts/stops it via
// `startActivityPolling()` in a mount effect (spec: "StatusBar stays the only
// poller"). Cadence is adaptive — 5s idle, 2s while any job is running — so the
// tray feels live during a run without hammering the backend at rest.

export interface ActivityProgress {
  current?: number
  total?: number
  pct?: number
  label?: string
}

export type ActivityJobState = 'running' | 'done' | 'error' | 'cancelled'

export interface ActivityJob {
  id: string
  kind: string
  state: ActivityJobState
  progress?: ActivityProgress
  started_at?: number
  finished_at?: number
  cancel_route?: string
  screen: string
}

interface ActivityJobsResponse {
  busy: boolean
  jobs: ActivityJob[]
}

interface ActivityStore {
  jobs: ActivityJob[]
  busy: boolean
  runningCount: number
  /** D-2: bumped on a running->error transition, cleared when the tray opens. */
  hasError: boolean
  clearError: () => void
  _applySnapshot: (data: ActivityJobsResponse) => void
}

export const useActivityStore = create<ActivityStore>((set, get) => ({
  jobs: [],
  busy: false,
  runningCount: 0,
  hasError: false,
  clearError: () => set({ hasError: false }),
  _applySnapshot: (data) => {
    const prevRunningIds = new Set(
      get().jobs.filter((j) => j.state === 'running').map((j) => j.id)
    )
    const newlyErrored = data.jobs.some(
      (j) => j.state === 'error' && prevRunningIds.has(j.id)
    )
    set((state) => ({
      jobs: data.jobs,
      busy: data.busy,
      runningCount: data.jobs.filter((j) => j.state === 'running').length,
      hasError: state.hasError || newlyErrored,
    }))
  },
}))

const IDLE_POLL_MS = 5000
const BUSY_POLL_MS = 2000

let pollTimer: ReturnType<typeof setTimeout> | null = null
let activePollers = 0

async function pollOnce(): Promise<void> {
  try {
    const r = await fetch(`${window.api.flaskBase}/api/activity/jobs`)
    if (!r.ok) return
    const data: ActivityJobsResponse = await r.json()
    useActivityStore.getState()._applySnapshot(data)
  } catch {
    // jobs/busy stay at last-known value — same fallback as every other poller here
  }
}

function scheduleNext(): void {
  if (activePollers <= 0) return
  const delay = useActivityStore.getState().runningCount > 0 ? BUSY_POLL_MS : IDLE_POLL_MS
  pollTimer = setTimeout(() => {
    pollOnce().then(scheduleNext)
  }, delay)
}

/**
 * Start the shared activity poller. Idempotent across concurrent mount
 * points — only the first caller actually starts the interval, so StatusBar
 * can be the sole intended caller without the store needing to know that.
 *
 * Returns a teardown function; call it on unmount. The interval stops once
 * the last caller tears down.
 */
export function startActivityPolling(): () => void {
  activePollers += 1
  if (activePollers === 1) {
    pollOnce().then(scheduleNext)
  }
  return () => {
    activePollers = Math.max(0, activePollers - 1)
    if (activePollers === 0 && pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }
}
