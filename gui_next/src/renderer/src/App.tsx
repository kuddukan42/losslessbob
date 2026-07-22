import React, { useCallback, useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient } from '@tanstack/react-query'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import type { PersistedClient, Persister } from '@tanstack/react-query-persist-client'
import { get as idbGet, set as idbSet, del as idbDel } from 'idb-keyval'
import { applyTheme, loadTheme, saveTheme, getSystemMode } from './lib/tokens'
import type { ThemeOptions, Mode, Accent, Density } from './lib/tokens'
import { AppShell, SplashOverlay, AboutDialog } from './components'
import {
  Pill, Chip, Button, IconButton, Input,
  Card, Toolbar, Banner, Stat, SectionHead,
  TableShell, TH, TR, TD, GroupRow,
} from './components'
import { useSettingsStore } from './store'
import i18n from './i18n'
import { ScreenHome } from './screens/ScreenHome'
import { ScreenPipeline } from './screens/ScreenPipeline'
import { ScreenSetup } from './screens/ScreenSetup'
import { ScreenMounts } from './screens/ScreenMounts'
import { ScreenCollection } from './screens/ScreenCollection'
import { ScreenSearch } from './screens/ScreenSearch'
import { ScreenBootlegs } from './screens/ScreenBootlegs'
import { ScreenThemes } from './screens/ScreenThemes'
import { ScreenMap } from './screens/ScreenMap'
import { ScreenAttachments } from './screens/ScreenAttachments'
import { ScreenSpectrograms } from './screens/ScreenSpectrograms'
import { ScreenDbEditor } from './screens/ScreenDbEditor'
import { ScreenScraper } from './screens/ScreenScraper'
import { ScreenTrading } from './screens/ScreenTrading'
import { ScreenSharing } from './screens/ScreenSharing'
import { ScreenQuickLookup } from './screens/ScreenQuickLookup'
import { ScreenLibrary } from './screens/ScreenLibrary'
import { ScreenTapeMatch } from './screens/ScreenTapeMatch'
import { ScreenSongs } from './screens/ScreenSongs'
import { ScreenGaps } from './screens/ScreenGaps'
import { ScreenFingerprint } from './screens/ScreenFingerprint'

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
      queryFn: () => fetch(`${window.api.flaskBase}${path}`).then(r => r.json()),
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

// ── Curator-only route guard ──────────────────────────────────────────────────

function CuratorRoute({ element }: { element: React.ReactNode }) {
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  return curatorMode ? <>{element}</> : <Navigate to="/" replace />
}

// ── Placeholder screen ────────────────────────────────────────────────────────

function PlaceholderScreen({ name }: { name: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      height: '100%', gap: 12,
      color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
    }}>
      <span style={{ fontSize: 'var(--lbb-fs-32)', opacity: 0.2 }}>◻</span>
      <span style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>{name}</span>
      <span style={{ fontSize: 'var(--lbb-fs-11-5)' }}>Screen not yet implemented</span>
    </div>
  )
}

// ── Primitives dev screen (moved from Phase 1 smoke test) ─────────────────────

const ACCENTS: Accent[] = ['indigo', 'plum', 'rust', 'forest', 'teal', 'amber', 'gray', 'crimson']
const DENSITIES: Density[] = ['compact', 'default', 'comfortable']
const SAMPLE_ROWS = [
  { lb: 'LB-5421', title: 'Madison Square Garden, New York, NY', date: '1974-01-30', files: 12, status: 'ok'   as const },
  { lb: 'LB-5422', title: 'Forum, Los Angeles, CA',              date: '1974-02-03', files:  9, status: 'warn' as const },
  { lb: 'LB-1001', title: 'Isle of Wight Festival, England',     date: '1970-08-31', files:  6, status: 'bad'  as const },
  { lb: 'LB-0042', title: 'Royal Albert Hall, London',           date: '1966-05-26', files: 11, status: 'info' as const },
]

function PrimitivesScreen() {
  const [theme, setTheme]       = useState<ThemeOptions>(loadTheme)
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery]       = useState('')

  const update = useCallback((patch: Partial<ThemeOptions>) => {
    const next = { ...theme, ...patch }
    applyTheme(next)
    saveTheme(next)
    setTheme(next)
  }, [theme])

  return (
    <div style={{ padding: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Theme bar */}
      <Toolbar bordered pad="8px 16px" style={{ gap: 12, flexShrink: 0 }}>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg3)', marginRight: 4 }}>Mode</span>
        {(['light','dark'] as Mode[]).map(m => (
          <Chip key={m} active={theme.mode === m} size="sm" onClick={() => update({ mode: m })}>{m}</Chip>
        ))}
        <Chip size="sm" onClick={() => update({ mode: getSystemMode() })}>system</Chip>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg3)' }}>Density</span>
        {DENSITIES.map(d => (
          <Chip key={d} active={theme.density === d} size="sm" onClick={() => update({ density: d })}>{d}</Chip>
        ))}
      </Toolbar>

      {/* Accent row */}
      <Toolbar bordered pad="6px 16px" style={{ gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600, color: 'var(--lbb-fg3)', marginRight: 4 }}>Accent</span>
        {ACCENTS.map(a => (
          <Chip key={a} active={theme.accent === a} size="sm" onClick={() => update({ accent: a })}>{a}</Chip>
        ))}
      </Toolbar>

      {/* Content */}
      <div style={{ flex: 1, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20, minHeight: 0 }}>

        <div style={{ display: 'flex', gap: 16 }}>
          {[
            { value: '15,967', label: 'in My Collection',  delta: '+12', tone: 'ok'   as const },
            { value:  '8,341', label: 'fully verified',    delta: '+3',  tone: 'ok'   as const },
            { value:    '124', label: 'need attention',    delta: '-2',  tone: 'warn' as const },
            { value:     '18', label: 'missing files'                                          },
          ].map(s => (
            <Card key={s.label} style={{ flex: 1 }}>
              <Stat value={s.value} label={s.label} delta={s.delta} tone={s.tone} />
            </Card>
          ))}
        </div>

        <Banner tone="info" icon="info" title="Phase 1 primitives — smoke test">
          All components render via CSS custom properties. Switch mode/accent/density above to verify live-update.
        </Banner>

        <Card title="Status Pills">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {(['ok','warn','bad','info','mute'] as const).flatMap(t => [
              <Pill key={`${t}-outline`} tone={t}>{t}</Pill>,
              <Pill key={`${t}-soft`}    tone={t} soft>{t} soft</Pill>,
              <Pill key={`${t}-dot`}     tone={t} soft dot>{t} dot</Pill>,
            ])}
          </div>
        </Card>

        <Card title="Buttons">
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <Button variant="primary"   icon="plus">Primary</Button>
            <Button variant="secondary" icon="folder">Secondary</Button>
            <Button variant="ghost"     icon="refresh">Ghost</Button>
            <Button variant="danger"    icon="trash">Danger</Button>
            <Button variant="primary" size="sm" icon="plus">Sm</Button>
            <Button variant="primary" size="lg" icon="plus">Lg</Button>
            <Button variant="secondary" disabled>Disabled</Button>
            <IconButton icon="more" title="More" />
            <IconButton icon="bell" active title="Bell (active)" />
          </div>
        </Card>

        <Card title="Inputs &amp; Keyboard Hints">
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <Input icon="search" placeholder="Search recordings…" value={query}
              onChange={e => setQuery(e.target.value)} width={240} />
            <Input placeholder="No icon" size="sm" width={140} />
            <Input placeholder="Large" size="lg" width={160} />
          </div>
        </Card>

        <Card title="Table (edge bars + density)" style={{ padding: 0, overflow: 'hidden' }}>
          <Toolbar pad="8px 12px">
            <SectionHead title="Recent Matches" subtitle="last import"
              style={{ flex: 1, marginBottom: 0 }} />
            <Button size="sm" icon="download" variant="ghost">Export</Button>
          </Toolbar>
          <div style={{ overflowX: 'auto' }}>
            <TableShell stickyHeader>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 90 }} />
                <col />
                <col style={{ width: 110 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 100 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH /><TH>LB#</TH><TH>Title / Venue</TH>
                  <TH>Date</TH><TH align="right">Files</TH><TH>Status</TH>
                </tr>
              </thead>
              <tbody>
                <GroupRow label="1970s · 2 results" count={2} colSpan={5} />
                {SAMPLE_ROWS.slice(0, 2).map(r => (
                  <TR key={r.lb} edge={r.status} selected={selected === r.lb}
                    onClick={() => setSelected(r.lb === selected ? null : r.lb)}>
                    <TD mono>{r.lb}</TD>
                    <TD>{r.title}</TD>
                    <TD mono dim>{r.date}</TD>
                    <TD align="right" mono>{r.files}</TD>
                    <TD><Pill tone={r.status} soft dot>{r.status}</Pill></TD>
                  </TR>
                ))}
                <GroupRow label="1960s · 2 results" count={2} colSpan={5} />
                {SAMPLE_ROWS.slice(2).map(r => (
                  <TR key={r.lb} edge={r.status} selected={selected === r.lb}
                    onClick={() => setSelected(r.lb === selected ? null : r.lb)}>
                    <TD mono>{r.lb}</TD>
                    <TD>{r.title}</TD>
                    <TD mono dim>{r.date}</TD>
                    <TD align="right" mono>{r.files}</TD>
                    <TD><Pill tone={r.status} soft dot>{r.status}</Pill></TD>
                  </TR>
                ))}
              </tbody>
            </TableShell>
          </div>
          {selected && (
            <div style={{ padding: '8px 14px', borderTop: '1px solid var(--lbb-border)',
              fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
              Selected: {selected}
            </div>
          )}
        </Card>

        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', textAlign: 'center', paddingBottom: 8 }}>
          gui_next · Phase 2 complete — app shell + routing · active screen shown in sidebar
        </div>
      </div>
    </div>
  )
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
      {!splashDone && <SplashOverlay onDone={() => setSplashDone(true)} />}
      {showAbout && <AboutDialog onClose={() => setShowAbout(false)} />}
      <AppShell onAbout={() => setShowAbout(true)}>
        <KeepAlivePipeline />
        <Routes>
          <Route path="/"            element={<ScreenHome />} />
          <Route path="/quicklookup" element={<ScreenQuickLookup />} />
          <Route path="/library"     element={<ScreenLibrary />} />
          <Route path="/tapematch"   element={<ScreenTapeMatch />} />
          <Route path="/songs"       element={<ScreenSongs />} />
          <Route path="/gaps"        element={<ScreenGaps />} />
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
          <Route path="/setup"       element={<ScreenSetup />} />
          <Route path="/mounts"      element={<ScreenMounts />} />
          <Route path="/themes"      element={<ScreenThemes />} />
        </Routes>
      </AppShell>
    </HashRouter>
    </PersistQueryClientProvider>
  )
}
