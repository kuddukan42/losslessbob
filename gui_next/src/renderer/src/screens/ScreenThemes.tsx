import React, { useState } from 'react'
import {
  Button, Pill, Chip, Icon,
  TableShell, TH, TR, TD,
} from '../components'
import {
  applyTheme, loadTheme, saveTheme,
  type ThemeOptions, type Accent, type Density,
} from '../lib/tokens'

// ── SetupCard (local, same shape as ScreenSetup) ─────────────────────────────

function SetupCard({
  title,
  badge,
  children,
  style,
}: {
  title: string
  badge?: React.ReactNode
  children?: React.ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div
      style={{
        background: 'var(--lbb-surface)',
        border: '1px solid var(--lbb-border)',
        borderRadius: 10,
        padding: 18,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: 0.08,
            textTransform: 'uppercase',
            color: 'var(--lbb-fg)',
          }}
        >
          {title}
        </span>
        {badge}
      </div>
      {children}
    </div>
  )
}

// ── Accent swatch data ────────────────────────────────────────────────────────

const ACCENT_SWATCHES: { k: Accent; c: string }[] = [
  { k: 'indigo',  c: '#2b5fd0' },
  { k: 'plum',    c: '#7a3fb1' },
  { k: 'rust',    c: '#a8462e' },
  { k: 'forest',  c: '#2a7a4a' },
  { k: 'teal',    c: '#2b6f7c' },
  { k: 'amber',   c: '#9a6800' },
  { k: 'gray',    c: '#4a463e' },
  { k: 'crimson', c: '#a31a35' },
]

// ── Preview table rows ────────────────────────────────────────────────────────

const PREVIEW_ROWS = [
  { lb: 'LB-1',  date: '5/xx/87',  venue: 'Dead Dylan Rehearsals',  tone: 'ok'   as const, label: 'Public'  },
  { lb: 'LB-7',  date: '—',        venue: '—',                      tone: 'warn' as const, label: 'Missing' },
  { lb: 'LB-12', date: '11/11/80', venue: 'Warfield, SF',           tone: 'bad'  as const, label: 'Mismatch'},
  { lb: 'LB-18', date: '6/29/81',  venue: "Earl's Court, London",   tone: 'info' as const, label: 'Public'  },
]

const PREVIEW_BTN_VARIANTS = ['primary', 'secondary', 'ghost', 'danger'] as const

// ── ScreenThemes ──────────────────────────────────────────────────────────────

export function ScreenThemes() {
  const [theme, setTheme] = useState<ThemeOptions>(loadTheme)

  function setTweak<K extends keyof ThemeOptions>(key: K, value: ThemeOptions[K]) {
    const next = { ...theme, [key]: value }
    applyTheme(next)
    saveTheme(next)
    setTheme(next)
  }

  const densityTiles: { k: Density; l: string; n: string; bars: number; barH: number; gap: number }[] = [
    { k: 'comfortable', l: 'Comfortable', n: '~25 rows', bars: 4, barH: 11, gap: 8 },
    { k: 'default',     l: 'Default',     n: '~32 rows', bars: 6, barH:  7, gap: 5 },
    { k: 'compact',     l: 'Compact',     n: '~55 rows', bars: 8, barH:  5, gap: 2 },
  ]

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <div style={{ padding: '24px 32px 40px', maxWidth: 1500, margin: '0 auto' }}>

        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: -0.02, color: 'var(--lbb-fg)' }}>
          Themes
        </h1>
        <p style={{ fontSize: 13, color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          Mode × accent × density. Status colors stay fixed for accessibility.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>

          {/* ── Mode ── */}
          <SetupCard title="Mode">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {[
                { k: 'light',  l: 'Light',  bg: '#faf8f3', side: '#e2dfd2' },
                { k: 'dark',   l: 'Dark',   bg: '#27251d', side: '#161510' },
                { k: 'system', l: 'System', bg: '#faf8f3', side: '#161510' },
              ].map((m) => (
                <button
                  key={m.k}
                  type="button"
                  onClick={() => setTweak('mode', m.k as ThemeOptions['mode'])}
                  style={{
                    padding: 10,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.mode === m.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {/* Mini preview */}
                  <div style={{ height: 80, borderRadius: 6, overflow: 'hidden', border: '1px solid var(--lbb-border2)', display: 'grid', gridTemplateColumns: '1fr 2fr' }}>
                    <div style={{ background: m.side }} />
                    <div style={{ background: m.bg, padding: 8 }}>
                      <div style={{ height: 6, background: m.side, opacity: 0.6, borderRadius: 2, marginBottom: 6 }} />
                      <div style={{ height: 4, background: m.side, opacity: 0.3, borderRadius: 2, marginBottom: 4 }} />
                      <div style={{ height: 4, background: m.side, opacity: 0.3, borderRadius: 2, width: '60%' }} />
                    </div>
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600 }}>{m.l}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Density ── */}
          <SetupCard title="Density">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {densityTiles.map((d) => (
                <button
                  key={d.k}
                  type="button"
                  onClick={() => setTweak('density', d.k)}
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.density === d.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    textAlign: 'left',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div style={{ height: 80, display: 'flex', flexDirection: 'column', gap: d.gap }}>
                    {Array.from({ length: d.bars }).map((_, i) => (
                      <div
                        key={i}
                        style={{
                          height: d.barH,
                          background: 'var(--lbb-surface2)',
                          borderRadius: 2,
                          border: '1px solid var(--lbb-border)',
                        }}
                      />
                    ))}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600 }}>{d.l}</div>
                  <div style={{ fontSize: 10.5, color: 'var(--lbb-fg3)' }}>{d.n}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Accent (span 2) ── */}
          <SetupCard title="Accent" style={{ gridColumn: 'span 2' }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {ACCENT_SWATCHES.map((a) => (
                <button
                  key={a.k}
                  type="button"
                  onClick={() => setTweak('accent', a.k)}
                  style={{
                    padding: 8,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.accent === a.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 6,
                    width: 84,
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div
                    style={{
                      width: 50,
                      height: 50,
                      borderRadius: '50%',
                      background: a.c,
                      border: '1px solid rgba(0,0,0,0.08)',
                      boxShadow: '0 1px 0 rgba(255,255,255,0.3) inset',
                    }}
                  />
                  <span style={{ fontSize: 11.5, color: 'var(--lbb-fg)', fontWeight: 600, textTransform: 'capitalize' }}>
                    {a.k}
                  </span>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Typeface ── */}
          <SetupCard title="Typeface">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { k: 'inter',    l: 'Inter',          n: 'system default · clean grotesque' },
                { k: 'ibm-plex', l: 'IBM Plex Sans',  n: 'characterful · designed for data' },
                { k: 'source',   l: 'Source Sans 3',  n: 'warmer humanist · book-text feel' },
              ].map((f, i) => (
                <button
                  key={f.k}
                  type="button"
                  style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    background: 'var(--lbb-surface)',
                    border: `1px solid ${i === 0 ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--lbb-fg)' }}>{f.l}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>{f.n}</div>
                  </div>
                  {i === 0 && <Icon name="check" size={14} style={{ color: 'var(--lbb-accent-mid)', flexShrink: 0 }} />}
                </button>
              ))}
            </div>
            <p style={{ marginTop: 12, marginBottom: 0, fontSize: 11, color: 'var(--lbb-fg3)' }}>
              Size: 12pt · 13pt · 14pt
            </p>
          </SetupCard>

          {/* ── Advanced ── */}
          <SetupCard title="Advanced">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Button variant="secondary" size="sm">Custom color tokens…</Button>
              <Button variant="ghost"     size="sm">Export theme as JSON</Button>
              <Button variant="ghost"     size="sm">Import theme…</Button>
            </div>
            <div
              style={{
                marginTop: 14,
                padding: '10px 12px',
                borderRadius: 6,
                background: 'var(--lbb-surface2)',
                fontSize: 11.5,
                color: 'var(--lbb-fg2)',
                lineHeight: 1.5,
              }}
            >
              <strong>Status colors</strong> (green / amber / red) are pinned to the
              row-status bar and pills so they never collide with your accent choice.
            </div>
          </SetupCard>

          {/* ── Live preview (span 2) ── */}
          <SetupCard
            title="Live preview"
            style={{ gridColumn: 'span 2' }}
            badge={<Pill tone="mute" soft>reflects every change above</Pill>}
          >
            <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
              {/* Mock titlebar */}
              <div
                style={{
                  padding: '10px 16px',
                  background: 'var(--lbb-accent-mid)',
                  color: 'var(--lbb-accent-onMid)',
                  fontSize: 12,
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <Icon name="collection" size={14} />
                Library / My Collection
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 11, opacity: 0.85 }}>preview · 4 of 15,967</span>
              </div>

              {/* Mock content area */}
              <div style={{ padding: 16, background: 'var(--lbb-bg)' }}>
                <TableShell stickyHeader={false}>
                  <colgroup>
                    <col style={{ width: 3 }} />
                    <col style={{ width: 90 }} />
                    <col style={{ width: 90 }} />
                    <col style={{ width: 100 }} />
                    <col />
                    <col style={{ width: 150 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <TH /><TH>LB#</TH><TH>Status</TH><TH>Date</TH><TH>Location</TH><TH align="right">Action</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {PREVIEW_ROWS.map((r, i) => (
                      <TR key={r.lb} edge={r.tone}>
                        <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{r.lb}</TD>
                        <TD><Pill tone={r.tone} soft>{r.label}</Pill></TD>
                        <TD mono dim={r.date === '—'}>{r.date}</TD>
                        <TD dim={r.venue === '—'}>{r.venue}</TD>
                        <TD align="right">
                          <Button size="sm" variant={PREVIEW_BTN_VARIANTS[i]}>
                            {['Primary', 'Secondary', 'Ghost', 'Danger'][i]}
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </tbody>
                </TableShell>

                <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Chip active count={1234}>Active chip</Chip>
                  <Chip count={88}>Filter chip</Chip>
                  <Chip count={12}>Another</Chip>
                  <Pill tone="ok"   soft>ok</Pill>
                  <Pill tone="warn" soft>warn</Pill>
                  <Pill tone="bad"  soft>bad</Pill>
                  <Pill tone="info" soft>info</Pill>
                </div>
              </div>
            </div>
          </SetupCard>

        </div>
      </div>
    </div>
  )
}
