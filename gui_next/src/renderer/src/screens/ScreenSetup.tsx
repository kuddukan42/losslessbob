import React from 'react'
import { useSettingsStore } from '../store'
import { Button, Pill, Icon } from '../components'

// ── SetupCard ─────────────────────────────────────────────────────────────────

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
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 14,
        }}
      >
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

// ── Meta grid (2-col label/value) ─────────────────────────────────────────────

function MetaGrid({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '140px 1fr',
        gap: '6px 16px',
        fontSize: 12.5,
      }}
    >
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <span style={{ color: 'var(--lbb-fg3)' }}>{label}</span>
          <span
            style={{
              fontFamily: 'var(--lbb-mono)',
              fontWeight: 600,
              color: 'var(--lbb-fg)',
            }}
          >
            {value}
          </span>
        </React.Fragment>
      ))}
    </div>
  )
}

// ── CuratorToggle ─────────────────────────────────────────────────────────────

function CuratorToggle() {
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  const setCuratorMode = useSettingsStore((s) => s.setCuratorMode)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Big inset block */}
      <div
        style={{
          background: 'var(--lbb-surface2)',
          borderRadius: 8,
          border: '1px solid var(--lbb-border)',
          padding: 14,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
        }}
      >
        {/* Icon square — warn-tinted when on */}
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: 8,
            flexShrink: 0,
            background: curatorMode ? 'var(--lbb-warn-bg)' : 'var(--lbb-surface)',
            border: `1px solid ${curatorMode ? 'var(--lbb-warn-bar)' : 'var(--lbb-border2)'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'background 0.2s, border-color 0.2s',
            color: curatorMode ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)',
          }}
        >
          <Icon name="dbeditor" size={18} />
        </div>

        {/* Label + description */}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2, color: 'var(--lbb-fg)' }}>
            Curator Mode
          </div>
          <div
            style={{
              fontSize: 11.5,
              color: 'var(--lbb-fg3)',
              marginTop: 3,
              lineHeight: 1.4,
            }}
          >
            Enable direct DB editing, scraping, and master data publishing.
          </div>
        </div>

        {/* Toggle switch — 44×24, animated knob */}
        <button
          type="button"
          aria-checked={curatorMode}
          role="switch"
          onClick={() => setCuratorMode(!curatorMode)}
          style={{
            width: 44,
            height: 24,
            borderRadius: 12,
            flexShrink: 0,
            background: curatorMode ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            position: 'relative',
            transition: 'background 0.2s',
          }}
        >
          <span
            style={{
              position: 'absolute',
              top: 2,
              left: curatorMode ? 22 : 2,
              width: 20,
              height: 20,
              borderRadius: '50%',
              background: '#fff',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              transition: 'left 0.2s',
              display: 'block',
            }}
          />
        </button>
      </div>

      {/* Master version meta */}
      <MetaGrid
        rows={[
          ['Master version', 'v16630 · 2026-05-21'],
          ['Source', 'losslessbob.wonderingwhattochoose.com'],
        ]}
      />

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button variant="secondary" icon="upload" disabled={!curatorMode}>
          Publish master update…
        </Button>
        <Button variant="ghost" icon="download">
          Install master update…
        </Button>
      </div>
    </div>
  )
}

// ── IntegCard ─────────────────────────────────────────────────────────────────

function IntegCard({
  title,
  tone,
  rows,
}: {
  title: string
  tone: 'ok' | 'warn' | 'mute'
  rows: [string, string][]
}) {
  return (
    <div
      style={{
        background: 'var(--lbb-surface2)',
        border: '1px solid var(--lbb-border)',
        borderRadius: 8,
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)' }}>{title}</span>
        <Pill tone={tone} soft dot>
          {tone === 'ok' ? 'connected' : tone === 'warn' ? 'degraded' : 'disabled'}
        </Pill>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '100px 1fr',
          gap: '4px 8px',
          fontSize: 11.5,
        }}
      >
        {rows.map(([label, value]) => (
          <React.Fragment key={label}>
            <span style={{ color: 'var(--lbb-fg3)' }}>{label}</span>
            <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{value}</span>
          </React.Fragment>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
        <Button variant="ghost" size="sm">Test</Button>
        <Button variant="secondary" size="sm">Edit…</Button>
      </div>
    </div>
  )
}

// ── HelperDot ─────────────────────────────────────────────────────────────────

function HelpersStrip() {
  const helpers = [
    { name: 'shntool', color: 'var(--lbb-ok-bar)' },
    { name: 'flac', color: 'var(--lbb-ok-bar)' },
    { name: 'ffmpeg', color: 'var(--lbb-ok-bar)' },
    { name: 'sox', color: 'var(--lbb-warn-bar)' },
  ]
  return (
    <div
      style={{
        background: 'var(--lbb-surface2)',
        borderRadius: 6,
        padding: '8px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        marginTop: 14,
      }}
    >
      <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', flex: 1, display: 'flex', gap: 14 }}>
        {helpers.map((h) => (
          <span key={h.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: h.color,
                flexShrink: 0,
              }}
            />
            {h.name}
          </span>
        ))}
      </span>
      <Button variant="ghost" size="sm" icon="refresh">Re-check</Button>
    </div>
  )
}

// ── ScreenSetup ───────────────────────────────────────────────────────────────

export function ScreenSetup() {
  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <div
        style={{
          padding: '24px 32px 40px',
          maxWidth: 1500,
          margin: '0 auto',
        }}
      >
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: -0.02,
            color: 'var(--lbb-fg)',
            margin: 0,
          }}
        >
          Setup
        </h1>
        <p style={{ fontSize: 13, color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          Database management, integrations, and preferences.
        </p>

        {/* 2-column card grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
            marginTop: 24,
          }}
        >
          {/* ── Database ── */}
          <SetupCard
            title="Database"
            badge={
              <Pill tone="ok" soft dot>
                connected
              </Pill>
            }
          >
            <MetaGrid
              rows={[
                ['Active', 'LossLessBob'],
                ['Checksums', '704,624'],
                ['LB entries', '16,630'],
                ['Last import', '2026-05-21'],
                ['DB size', '312 MB'],
              ]}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
              <Button variant="secondary" icon="download" size="sm">Import DB file…</Button>
              <Button variant="secondary" icon="refresh" size="sm">Check for update</Button>
              <Button variant="ghost" icon="folder" size="sm">Open data folder</Button>
              <Button variant="danger" icon="trash" size="sm">Reset DB…</Button>
            </div>
            <HelpersStrip />
          </SetupCard>

          {/* ── Master Data (curator toggle) ── */}
          <SetupCard title="Master Data">
            <CuratorToggle />
          </SetupCard>

          {/* ── Integrations (full width) ── */}
          <SetupCard title="Integrations" style={{ gridColumn: 'span 2' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <IntegCard
                title="qBittorrent"
                tone="ok"
                rows={[
                  ['Host', 'localhost:8080'],
                  ['Version', '5.0.3'],
                  ['Category', 'losslessbob'],
                ]}
              />
              <IntegCard
                title="Watching the River Flow"
                tone="warn"
                rows={[
                  ['Forum', 'wtrf.example.org'],
                  ['User', 'rolling.thunder'],
                  ['Last check', '2026-05-21'],
                ]}
              />
              <IntegCard
                title="Torrent web UI"
                tone="mute"
                rows={[
                  ['URL', '—'],
                  ['Auth', 'not configured'],
                  ['Status', 'disabled'],
                ]}
              />
            </div>
          </SetupCard>

          {/* ── Preferences ── */}
          <SetupCard title="Preferences">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '140px 1fr',
                gap: '8px 16px',
                fontSize: 12.5,
                alignItems: 'center',
              }}
            >
              <span style={{ color: 'var(--lbb-fg3)' }}>Interface language</span>
              <span style={{ color: 'var(--lbb-fg)' }}>English (en)</span>

              <span style={{ color: 'var(--lbb-fg3)' }}>Results per page</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {['50', '100', '250', 'All'].map((v, i) => (
                  <button
                    key={v}
                    type="button"
                    style={{
                      height: 24,
                      padding: '0 9px',
                      fontSize: 11.5,
                      fontWeight: i === 1 ? 700 : 500,
                      borderRadius: 5,
                      background: i === 1 ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface2)',
                      color: i === 1 ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                      border: `1px solid ${i === 1 ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                  >
                    {v}
                  </button>
                ))}
              </div>

              <span style={{ color: 'var(--lbb-fg3)' }}>Column widths</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {['Narrow', 'Default', 'Wide'].map((v) => (
                  <button
                    key={v}
                    type="button"
                    style={{
                      height: 24,
                      padding: '0 9px',
                      fontSize: 11.5,
                      borderRadius: 5,
                      background: 'var(--lbb-surface2)',
                      color: 'var(--lbb-fg2)',
                      border: '1px solid var(--lbb-border)',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                  >
                    {v}
                  </button>
                ))}
              </div>

              <span style={{ color: 'var(--lbb-fg3)' }}>Auto-scrape on import</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input type="checkbox" defaultChecked style={{ accentColor: 'var(--lbb-accent-mid)' }} />
                <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>enabled</span>
              </label>

              <span style={{ color: 'var(--lbb-fg3)' }}>Send anon. usage</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input type="checkbox" style={{ accentColor: 'var(--lbb-accent-mid)' }} />
                <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>disabled</span>
              </label>
            </div>
          </SetupCard>

          {/* ── Data purges ── */}
          <SetupCard title="Data purges">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                'Lookup history',
                'Import log',
                'Scraper cache',
                'Fingerprint cache',
                'All user data',
              ].map((label) => (
                <div
                  key={label}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: 12.5,
                    color: 'var(--lbb-fg2)',
                  }}
                >
                  <span>{label}</span>
                  <Button variant="ghost" size="sm">Purge…</Button>
                </div>
              ))}
            </div>
            <p
              style={{
                fontSize: 11,
                color: 'var(--lbb-fg3)',
                marginTop: 14,
                marginBottom: 0,
                lineHeight: 1.4,
              }}
            >
              User data only. The checksum archive is never affected.
            </p>
          </SetupCard>

          {/* ── Flat file history (full width) ── */}
          <SetupCard title="Flat file history" style={{ gridColumn: 'span 2' }}>
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: 12,
                }}
              >
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                    {['Detected', 'Filename', 'Status', 'Added', 'Changed', ''].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '6px 10px',
                          textAlign: 'left',
                          fontSize: 10.5,
                          fontWeight: 700,
                          letterSpacing: 0.05,
                          textTransform: 'uppercase',
                          color: 'var(--lbb-fg3)',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    { ts: '2026-05-21 14:32', name: 'losslessbob_v16630.db', status: 'ok' as const,  added: '2026-05-21', changed: '—' },
                    { ts: '2026-05-14 09:11', name: 'losslessbob_v16580.db', status: 'mute' as const, added: '2026-05-14', changed: '2026-05-21' },
                  ].map((row, i) => (
                    <tr
                      key={i}
                      style={{
                        borderBottom: '1px solid var(--lbb-border)',
                        color: 'var(--lbb-fg2)',
                      }}
                    >
                      <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>{row.ts}</td>
                      <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)' }}>{row.name}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <Pill tone={row.status} soft dot>
                          {row.status === 'ok' ? 'active' : 'archived'}
                        </Pill>
                      </td>
                      <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>{row.added}</td>
                      <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>{row.changed}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <Button variant="ghost" size="sm">Reveal</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SetupCard>
        </div>
      </div>
    </div>
  )
}
