import React, { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient } from '@tanstack/react-query'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import type { PersistedClient, Persister } from '@tanstack/react-query-persist-client'
import { get as idbGet, set as idbSet, del as idbDel } from 'idb-keyval'
import { AppShell, SplashOverlay, AboutDialog } from './components'
import { useSettingsStore } from './store'
import { useFolderQueueStore } from './lib/folderQueueStore'
import i18n from './i18n'
import { ScreenHome } from './screens/ScreenHome'
import { ScreenPipeline } from './screens/ScreenPipeline'
import { ScreenScanner } from './screens/ScreenScanner'
import { ScreenSetup } from './screens/ScreenSetup'
import { ScreenMounts } from './screens/ScreenMounts'
import { ScreenFileIntegrity } from './screens/ScreenFileIntegrity'
import { ScreenCollection } from './screens/ScreenCollection'
import { ScreenSearch } from './screens/ScreenSearch'
import { ScreenBootlegs } from './screens/ScreenBootlegs'
import { ScreenThemes } from './screens/ScreenThemes'
import { ScreenCoverage } from './screens/ScreenCoverage'
import { ScreenLbdirLedger } from './screens/ScreenLbdirLedger'
import { ScreenLbdirSync } from './screens/ScreenLbdirSync'
import { ScreenMap } from './screens/ScreenMap'
import { ScreenAttachments } from './screens/ScreenAttachments'
import { ScreenSpectrograms } from './screens/ScreenSpectrograms'
import { ScreenDbEditor } from './screens/ScreenDbEditor'
import { ScreenScraper } from './screens/ScreenScraper'
import { ScreenTrading } from './screens/ScreenTrading'
import { ScreenSharing } from './screens/ScreenSharing'
import { ScreenQuickLookup } from './screens/ScreenQuickLookup'
import { ScreenLibrary } from './screens/ScreenLibrary'
import { ScreenTapeMatchCuration } from './screens/ScreenTapeMatchCuration'
import { ScreenSongs } from './screens/ScreenSongs'
import { ScreenTimeline } from './screens/ScreenTimeline'
import { ScreenFingerprint } from './screens/ScreenFingerprint'
import { ScreenChecksumDisputes } from './screens/ScreenChecksumDisputes'
import { getJson } from './lib/api'

// ── React Query client — persisted to IndexedDB (BUG-271) ────────────────────
// The bulk datasets (collection prefetch, library catalog/performances/badges)
// are written to IndexedDB and restored on launch, so Library/Collection render
// instantly from last session's data while a background refetch reconciles.
// localStorage is not an option — the payloads are 20-36 MB each.

const PERSIST_MAX_AGE = 7 * 24 * 60 * 60 * 1000  // 7 days

const queryClient = new QueryClient({
  // gcTime must outlive maxAge, or restored-but-unmounted queries get
  // garbage-collected out of the next persisted snapshot.
  defaultOptions: { queries: { gcTime: PERSIST_MAX_AGE } },
})

// idb-keyval persister — stores the dehydrated client via structured clone
// (no JSON.stringify of a ~60 MB string on the main thread).
const IDB_CACHE_KEY = 'lbb-query-cache'
const idbPersister: Persister = {
  persistClient: (client: PersistedClient) => idbSet(IDB_CACHE_KEY, client),
  restoreClient: () => idbGet<PersistedClient>(IDB_CACHE_KEY),
  removeClient: () => idbDel(IDB_CACHE_KEY),
}

// Only the bulk datasets are worth the disk round-trip; everything else
// refetches in well under a second.
const PERSISTED_KEYS = new Set([
  'collection-prefetch', 'library-catalog', 'library-performances', 'library-badges',
])

const BULK_QUERIES = [
  ['collection-prefetch',   '/api/collection/prefetch'],
  ['library-catalog',       '/api/search'],
  ['library-performances',  '/api/library/performances'],
  ['library-badges',        '/api/library/badges'],
] as const

const appStartedAt = Date.now()

// Runs once the IndexedDB restore has finished (PersistQueryClientProvider
// onSuccess). First run / empty cache: prefetch fills it (no-op when restored
// data is present, staleTime Infinity). Then, staggered off the first paint,
// background-refetch anything that came from a previous session's snapshot.
function warmBulkQueries(): void {
  for (const [key, path] of BULK_QUERIES) {
    queryClient.prefetchQuery({
      queryKey: [key],
      queryFn: () => getJson(path),
      staleTime: Infinity,
    })
  }
  setTimeout(() => {
    for (const [key] of BULK_QUERIES) {
      const state = queryClient.getQueryState([key])
      if (state && state.fetchStatus === 'idle' && state.dataUpdatedAt < appStartedAt) {
        queryClient.invalidateQueries({ queryKey: [key], refetchType: 'all' })
      }
    }
  }, 3000)
}

// ── Last-route restore — reopen the app on the screen it was closed on ───────

const LAST_ROUTE_KEY = 'lbb-last-route'
// Captured at module load, before RouteRestorer's save-effect can overwrite it.
const savedRoute = localStorage.getItem(LAST_ROUTE_KEY)

function RouteRestorer(): null {
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    localStorage.setItem(LAST_ROUTE_KEY, location.pathname)
  }, [location.pathname])
  useEffect(() => {
    if (savedRoute && savedRoute !== '/' && location.pathname === '/') {
      navigate(savedRoute, { replace: true })
    }
    // mount-only: restoring once at launch, not on later navigations
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}

// ── "Send to LosslessBob pipeline" from the file manager ─────────────────────
//
// tools/nemo drops folder paths for the main process (see PIPELINE_INBOX there);
// they arrive here as a batch, join the pipeline queue and pull the app to the
// Pipeline screen. Also runs when the drop is what launched the app, via the
// pending batch the main process buffered until this mounted.

function PipelineInbox(): null {
  const navigate = useNavigate()
  const addFolders = useFolderQueueStore((s) => s.addFolders)

  useEffect(() => {
    if (!window.api?.onPipelineFolders) return // renderer-only dev/screenshot mode
    const accept = (paths: string[]): void => {
      if (!paths.length) return
      addFolders(paths)
      navigate('/pipeline')
    }
    const off = window.api.onPipelineFolders(accept)
    window.api.consumePipelineFolders().then(accept).catch(() => {})
    return off
  }, [addFolders, navigate])

  return null
}

// ── Curator-only route guard ──────────────────────────────────────────────────

function CuratorRoute({ element }: { element: React.ReactNode }) {
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  return curatorMode ? <>{element}</> : <Navigate to="/" replace />
}

// The curation screen reached parity with the old read-only ScreenTapeMatch at
// Phase 6 (the write path) and took over /tapematch. This keeps links made
// while it was being built working, `?date=` and all.
function RedirectToTapeMatch(): React.JSX.Element {
  const { search } = useLocation()
  return <Navigate to={{ pathname: '/tapematch', search }} replace />
}

// ── Keep Pipeline screen mounted so its state survives navigation ─────────────

function KeepAlivePipeline() {
  const { pathname } = useLocation()
  return (
    <div style={{ display: pathname === '/pipeline' ? 'contents' : 'none' }}>
      <ScreenPipeline />
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App(): React.JSX.Element {
  const language = useSettingsStore((s) => s.language)
  useEffect(() => { i18n.changeLanguage(language) }, [language])

  const [splashDone, setSplashDone] = useState(true) // TODO: re-enable splash screen
  const [showAbout, setShowAbout] = useState(false)

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: idbPersister,
        maxAge: PERSIST_MAX_AGE,
        buster: 'lbb-cache-v1',
        dehydrateOptions: {
          shouldDehydrateQuery: (q) =>
            q.state.status === 'success' && PERSISTED_KEYS.has(String(q.queryKey[0])),
        },
      }}
      onSuccess={warmBulkQueries}
    >
    <HashRouter>
      <RouteRestorer />
      <PipelineInbox />
      {!splashDone && <SplashOverlay onDone={() => setSplashDone(true)} />}
      {showAbout && <AboutDialog onClose={() => setShowAbout(false)} />}
      <AppShell onAbout={() => setShowAbout(true)}>
        <KeepAlivePipeline />
        <Routes>
          <Route path="/"            element={<ScreenHome />} />
          <Route path="/quicklookup" element={<ScreenQuickLookup />} />
          <Route path="/scanner"     element={<ScreenScanner />} />
          <Route path="/library"     element={<ScreenLibrary />} />
          <Route path="/tapematch"   element={<ScreenTapeMatchCuration />} />
          {/* The curation screen reached parity with the old read-only
              ScreenTapeMatch at Phase 6 (write path) and replaced it at
              /tapematch. This alias keeps links made while it was being
              built — including the ?date= ones — working. */}
          <Route path="/tapematch/curation" element={<RedirectToTapeMatch />} />
          <Route path="/songs"       element={<ScreenSongs />} />
          <Route path="/timeline"    element={<ScreenTimeline />} />
          <Route path="/collection"  element={<ScreenCollection />} />
          <Route path="/trading"     element={<ScreenTrading />} />
          <Route path="/sharing"     element={<ScreenSharing />} />
          <Route path="/search"      element={<ScreenSearch />} />
          <Route path="/bootlegs"    element={<ScreenBootlegs />} />
          <Route path="/attachments" element={<ScreenAttachments />} />
          <Route path="/spectrograms"element={<ScreenSpectrograms />} />
          <Route path="/map"         element={<ScreenMap />} />
          <Route path="/dbeditor"    element={<ScreenDbEditor />} />
          <Route path="/scraper"     element={<CuratorRoute element={<ScreenScraper />} />} />
          <Route path="/fingerprint" element={<CuratorRoute element={<ScreenFingerprint />} />} />
          <Route path="/checksumdisputes" element={<CuratorRoute element={<ScreenChecksumDisputes />} />} />
          <Route path="/setup"       element={<ScreenSetup />} />
          <Route path="/mounts"      element={<ScreenMounts />} />
          <Route path="/fileintegrity" element={<ScreenFileIntegrity />} />
          <Route path="/themes"      element={<ScreenThemes />} />
          {/* Coverage / "Complete against LB" award screen. Deliberately not a
              sidebar destination — reached from the About modal's "Collection
              progress" row, but a real deep-linkable route so the milestone
              survives a reload and can be shared. */}
          <Route path="/about/coverage" element={<ScreenCoverage />} />
          {/* Ledger + sync (TODO-305): the two surfaces the coverage screen's
              "View full ledger" / "Sync with LB now" actions point at. Also not
              sidebar destinations — reached from /about/coverage, or by URL. */}
          <Route path="/lbdir/ledger" element={<ScreenLbdirLedger />} />
          <Route path="/lbdir/sync"   element={<ScreenLbdirSync />} />
        </Routes>
      </AppShell>
    </HashRouter>
    </PersistQueryClientProvider>
  )
}
