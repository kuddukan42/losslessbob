import React, { useCallback, useState } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { applyTheme, loadTheme, saveTheme, getSystemMode } from './lib/tokens'
import type { ThemeOptions, Mode, Accent, Density } from './lib/tokens'
import { AppShell } from './components'
import {
  Pill, Chip, Button, IconButton, Input, Kbd,
  Card, Toolbar, Banner, Stat, SectionHead,
  TableShell, TH, TR, TD, GroupRow,
} from './components'
import { useSettingsStore } from './store'
import { ScreenHome } from './screens/ScreenHome'
import { ScreenPipeline } from './screens/ScreenPipeline'
import { ScreenSetup } from './screens/ScreenSetup'
import { ScreenCollection } from './screens/ScreenCollection'
import { ScreenSearch } from './screens/ScreenSearch'
import { ScreenBootlegs } from './screens/ScreenBootlegs'
import { ScreenThemes } from './screens/ScreenThemes'
import { ScreenMap } from './screens/ScreenMap'
import { ScreenAttachments } from './screens/ScreenAttachments'
import { ScreenVerify } from './screens/ScreenVerify'

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
      <span style={{ fontSize: 32, opacity: 0.2 }}>◻</span>
      <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--lbb-fg2)' }}>{name}</span>
      <span style={{ fontSize: 11.5 }}>Screen not yet implemented</span>
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
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--lbb-fg3)', marginRight: 4 }}>Mode</span>
        {(['light','dark'] as Mode[]).map(m => (
          <Chip key={m} active={theme.mode === m} size="sm" onClick={() => update({ mode: m })}>{m}</Chip>
        ))}
        <Chip size="sm" onClick={() => update({ mode: getSystemMode() })}>system</Chip>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--lbb-fg3)' }}>Density</span>
        {DENSITIES.map(d => (
          <Chip key={d} active={theme.density === d} size="sm" onClick={() => update({ density: d })}>{d}</Chip>
        ))}
      </Toolbar>

      {/* Accent row */}
      <Toolbar bordered pad="6px 16px" style={{ gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--lbb-fg3)', marginRight: 4 }}>Accent</span>
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
            <span style={{ fontSize: 12, color: 'var(--lbb-fg2)' }}>Global search</span>
            <Kbd>⌘</Kbd><Kbd>K</Kbd>
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
              fontSize: 11.5, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
              Selected: {selected}
            </div>
          )}
        </Card>

        <div style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', textAlign: 'center', paddingBottom: 8 }}>
          gui_next · Phase 2 complete — app shell + routing · active screen shown in sidebar
        </div>
      </div>
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App(): React.JSX.Element {
  return (
    <HashRouter>
      <AppShell>
        <Routes>
          <Route path="/"            element={<ScreenHome />} />
          <Route path="/pipeline"    element={<ScreenPipeline />} />
          <Route path="/verify"      element={<ScreenVerify />} />
          <Route path="/lookup"      element={<PlaceholderScreen name="Lookup" />} />
          <Route path="/rename"      element={<PlaceholderScreen name="Rename" />} />
          <Route path="/lbdir"       element={<PlaceholderScreen name="LBDIR" />} />
          <Route path="/collection"  element={<ScreenCollection />} />
          <Route path="/search"      element={<ScreenSearch />} />
          <Route path="/bootlegs"    element={<ScreenBootlegs />} />
          <Route path="/attachments" element={<ScreenAttachments />} />
          <Route path="/spectrograms"element={<PlaceholderScreen name="Spectrograms" />} />
          <Route path="/map"         element={<ScreenMap />} />
          <Route path="/dbeditor"    element={<CuratorRoute element={<PlaceholderScreen name="DB Editor" />} />} />
          <Route path="/scraper"     element={<CuratorRoute element={<PlaceholderScreen name="Scraper" />} />} />
          <Route path="/setup"       element={<ScreenSetup />} />
          <Route path="/themes"      element={<ScreenThemes />} />
        </Routes>
      </AppShell>
    </HashRouter>
  )
}
