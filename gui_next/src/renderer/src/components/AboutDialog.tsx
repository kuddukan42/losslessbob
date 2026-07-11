// About dialog — Variant C "Tabbed"
// Four tabs: About / Tech / Credits / Changes.

import React, { useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'

// ── Static content ────────────────────────────────────────────────────────────

const META = {
  version:    __APP_VERSION__,
  channel:    'stable',
  build:      '2026.05.29',
  db:         'LB-16630',
  checksums:  '704,624',
  tagline:    'Checksum Lookup',
  copyright:  '© 2024–2026 LosslessBob project · A community archival tool.',
}

interface StackRow { name: string; value: string; version: string; primary?: boolean }
interface StackGroup { group: string; rows: StackRow[] }

const STACK: StackGroup[] = [
  { group: 'Interface', rows: [
    { name: 'GUI (primary)',    value: 'Electron + React + TypeScript', version: 'electron-vite', primary: true },
    { name: 'GUI (legacy)',     value: 'PyQt6',                         version: '6.7.1 · frozen' },
    { name: 'Attachments view', value: 'PyQt6-WebEngine',               version: '6.7.0' },
  ]},
  { group: 'Backend', rows: [
    { name: 'REST backend',  value: 'Flask + Flask-CORS', version: '3.0.3 / 4.0.1' },
    { name: 'WSGI server',   value: 'Waitress',           version: '3.0.0' },
    { name: 'Database',      value: 'SQLite3',            version: 'stdlib' },
    { name: 'Bloom filter',  value: 'pybloom-live',       version: '4.0.0' },
  ]},
  { group: 'Ingest & web', rows: [
    { name: 'Web scraping',  value: 'BeautifulSoup4 + lxml', version: '4.12.3 / 6.1.0' },
    { name: 'HTTP client',   value: 'Requests',              version: '2.32.3' },
    { name: 'File watching', value: 'Watchdog',              version: '4.0.1' },
    { name: 'Torrent gen',   value: 'torf',                  version: '4.3.1' },
    { name: 'Credentials',   value: 'keyring',               version: '25.7.0' },
  ]},
  { group: 'Audio & DSP', rows: [
    { name: 'Numerical',       value: 'numpy',     version: '2.4.6' },
    { name: 'Audio I/O',       value: 'soundfile', version: '0.13.1' },
    { name: 'Signal proc.',    value: 'scipy',     version: '1.17.1' },
    { name: 'Language',        value: 'Python',    version: '3.11+' },
  ]},
]

const ARCH =
  'GUI and backend are separated by a local Flask REST API on port 5174. ' +
  'gui_next (Electron/React) is the active target; Flask runs as a child process. ' +
  'The PyQt6 GUI is frozen as a fallback reference.'

interface Ack { name: string; handle: string; note: string; tone?: 'memory' }

const ACKS: Ack[] = [
  {
    name: 'Losslessbob', handle: 'the original archive',
    note: 'The archive and project that inspired this tool — the source of the LB numbering this app is built around.',
  },
  {
    name: 'Rumrunners', handle: 'system author · maintainer',
    note: 'Creator of the LB system and its ongoing maintainer. The schema, conventions, and master database are his work.',
  },
  {
    name: 'Robert Cook', handle: 'r9453', tone: 'memory',
    note: 'Contributor and close friend. His work and company shaped this project. Remembered.',
  },
  {
    name: 'Olof Björner', handle: '"Still On The Road" · bobserve.com',
    note: 'Author of the definitive Dylan performance history and Yearly Chronicles — the setlist, concert-numbering, recording, and circulation-provenance data behind the app’s Olof panel.',
  },
]

const CHANGELOG = {
  version: __APP_VERSION__,
  date: 'May 29, 2026',
  entries: [
    ['new',      'Unified ingest Pipeline — verify → lookup → rename → LBDIR in one pass.'],
    ['new',      'gui_next (Electron + React) is now the primary interface.'],
    ['improved', 'Spectrogram and concert-map screens redrawn at higher fidelity.'],
    ['changed',  'PyQt6 GUI frozen — kept only as a fallback reference.'],
    ['fixed',    'Checksum-index load time on large mounts cut roughly in half.'],
  ] as Array<[string, string]>,
}

interface Link { icon: string; label: string; sub: string }

const LINKS: Link[] = [
  { icon: 'globe', label: 'losslessbob.org',           sub: 'Project home' },
  { icon: 'lbdir', label: 'Documentation & LB system',  sub: 'rumrunners guide' },
  { icon: 'link',  label: 'github · checksum-lookup',   sub: 'Source & issues' },
  { icon: 'star',  label: 'Support the archive',         sub: 'Donate / mirror' },
]

// ── Local helpers ─────────────────────────────────────────────────────────────

// Warm-white at alpha — for the double-frame strokes (works on dark surface).
const w = (a: number) => `rgba(241,236,223,${a})`

// Format a duration in seconds as HH:MM:SS (TODO-112: backend uptime clock).
function formatUptime(totalSeconds: number): string {
  const pad = (n: number): string => String(n).padStart(2, '0')
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return `${pad(h)}:${pad(m)}:${pad(s)}`
}

// Fetches backend process uptime once, then ticks it locally every second.
// Lets the user confirm whether a backend restart actually happened after a
// code change (TODO-112).
function useBackendUptime(): string | null {
  const [display, setDisplay] = useState<string | null>(null)

  useEffect(() => {
    let base: number | null = null
    let fetchedAt = 0

    const tick = (): void => {
      if (base === null) return
      const elapsed = base + Math.floor((Date.now() - fetchedAt) / 1000)
      setDisplay(formatUptime(elapsed))
    }

    fetch(`${window.api.flaskBase}/api/system/uptime`)
      .then(r => r.json())
      .then((data: { uptime_seconds?: number }) => {
        if (typeof data.uptime_seconds !== 'number') return
        base = data.uptime_seconds
        fetchedAt = Date.now()
        tick()
      })
      .catch(() => {})

    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return display
}

function BlockTitle({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12 }}>
      <h3 style={{
        margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: 1,
        textTransform: 'uppercase', color: 'var(--lbb-fg3)', whiteSpace: 'nowrap',
      }}>
        {children}
      </h3>
      <div style={{ flex: 1, height: 1, background: 'var(--lbb-border)' }} />
    </div>
  )
}

// ── Header ────────────────────────────────────────────────────────────────────

function AboutHeader({ onClose }: { onClose: () => void }): React.JSX.Element {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 18,
      padding: '20px 22px',
      borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
    }}>
      {/* Double-square frame 66 × 66 wrapping monogram 42 × 42 */}
      <div style={{ position: 'relative', width: 66, height: 66, flexShrink: 0 }}>
        <div style={{
          position: 'absolute', inset: 0,
          border: `1.5px solid ${w(0.55)}`, borderRadius: 10,
        }} />
        <div style={{
          position: 'absolute', inset: 6,
          border: `1px solid ${w(0.2)}`, borderRadius: 9,
        }} />
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            width: 42, height: 42, borderRadius: 9, flexShrink: 0,
            background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 800, fontSize: 18, letterSpacing: -0.36,
            boxShadow: '0 1px 0 rgba(255,255,255,0.18) inset, 0 2px 8px rgba(0,0,0,0.35)',
          }}>
            LB
          </div>
        </div>
      </div>

      {/* Wordmark + meta row */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{
          fontSize: 28, fontWeight: 700, letterSpacing: -0.62,
          color: 'var(--lbb-fg)', lineHeight: 1, whiteSpace: 'nowrap',
          display: 'block',
        }}>
          <span style={{ fontWeight: 500 }}>Lossless</span>Bob
        </span>
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{
            fontFamily: 'var(--lbb-mono)', fontSize: 11, fontWeight: 600,
            color: 'var(--lbb-accent-mid)', padding: '2px 8px', borderRadius: 5,
            background: 'var(--lbb-accent-soft)',
            border: '1px solid color-mix(in oklab, var(--lbb-accent-mid) 40%, transparent)',
          }}>
            v{META.version}
          </span>
          <span style={{
            fontFamily: 'var(--lbb-mono)', fontSize: 9.5, letterSpacing: 9.5 * 0.28,
            textTransform: 'uppercase', color: 'var(--lbb-fg3)',
          }}>
            {META.tagline}
          </span>
        </div>
      </div>

      {/* Close button */}
      <button
        type="button"
        onClick={onClose}
        title="Close"
        style={{
          width: 30, height: 30, borderRadius: 7, cursor: 'pointer', flexShrink: 0,
          background: 'transparent', border: '1px solid var(--lbb-border)',
          color: 'var(--lbb-fg2)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <Icon name="x" size={14} />
      </button>
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type TabId = 'about' | 'tech' | 'credits' | 'log'

const TABS: Array<{ id: TabId; label: string; icon: string }> = [
  { id: 'about',   label: 'About',   icon: 'info'   },
  { id: 'tech',    label: 'Tech',    icon: 'setup'  },
  { id: 'credits', label: 'Credits', icon: 'user'   },
  { id: 'log',     label: 'Changes', icon: 'lbdir'  },
]

function TabBar({ tab, onTab }: { tab: TabId; onTab: (t: TabId) => void }): React.JSX.Element {
  return (
    <div style={{
      display: 'flex', gap: 4, padding: '12px 22px 0',
      borderBottom: '1px solid var(--lbb-border)', flexShrink: 0,
    }}>
      {TABS.map(t => {
        const active = t.id === tab
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onTab(t.id)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '9px 14px 11px',
              background: 'transparent',
              border: 'none',
              borderBottom: active ? '2px solid var(--lbb-accent-mid)' : '2px solid transparent',
              marginBottom: -1,
              fontSize: 12.5,
              fontWeight: active ? 600 : 500,
              color: active ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            <Icon
              name={t.icon}
              size={14}
              style={{ color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)' }}
            />
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

// ── Tab: About ────────────────────────────────────────────────────────────────

function TabAbout(): React.JSX.Element {
  const uptime = useBackendUptime()
  const metaItems = [
    { key: 'version',  value: `${META.version} · ${META.channel}`, accent: true },
    { key: 'build',    value: META.build },
    { key: 'database', value: META.db },
    { key: 'index',    value: META.checksums },
    { key: 'uptime',   value: uptime ?? '—' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Blurb */}
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: 'var(--lbb-fg2)' }}>
        A local-first tool for cataloguing, verifying and renaming a lossless live-recording
        collection against the master{' '}
        <strong style={{ color: 'var(--lbb-fg)' }}>LB</strong>{' '}
        checksum database. {META.checksums} checksums indexed across 4 mounts.
      </p>

      {/* Meta grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr',
        gap: '8px 8px', rowGap: 12,
        padding: '14px 16px', borderRadius: 9,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      }}>
        {metaItems.map(item => (
          <span key={item.key} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontFamily: 'var(--lbb-mono)', fontSize: 11,
          }}>
            <span style={{ color: 'var(--lbb-fg3)' }}>{item.key}</span>
            <span style={{
              color: item.accent ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
              fontWeight: 600,
            }}>
              {item.value}
            </span>
          </span>
        ))}
      </div>

      {/* Links */}
      <div>
        <BlockTitle>Links</BlockTitle>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {LINKS.map(l => (
            <div
              key={l.label}
              style={{
                display: 'flex', alignItems: 'center', gap: 11,
                padding: '9px 11px', borderRadius: 8,
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                cursor: 'default',
              }}
            >
              <span style={{
                width: 28, height: 28, borderRadius: 7, flexShrink: 0,
                background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--lbb-accent-mid)',
              }}>
                <Icon name={l.icon} size={14} />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{
                  display: 'block', fontSize: 12.3, fontWeight: 600, color: 'var(--lbb-fg)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {l.label}
                </span>
                <span style={{ display: 'block', fontSize: 10.5, color: 'var(--lbb-fg3)' }}>
                  {l.sub}
                </span>
              </span>
              <Icon name="reveal" size={12} style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Tab: Tech ─────────────────────────────────────────────────────────────────

function TabTech(): React.JSX.Element {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {STACK.map(g => (
        <div key={g.group}>
          <div style={{
            fontFamily: 'var(--lbb-mono)', fontSize: 10, letterSpacing: 1,
            textTransform: 'uppercase', color: 'var(--lbb-accent-mid)',
            marginBottom: 4, opacity: 0.85,
          }}>
            {g.group}
          </div>
          {g.rows.map((r, i) => (
            <div key={r.name} style={{
              display: 'grid', gridTemplateColumns: '120px 1fr auto', alignItems: 'center',
              gap: 12, padding: '7px 0',
              borderTop: i > 0 ? '1px solid var(--lbb-border)' : 'none',
            }}>
              <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>{r.name}</span>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                fontSize: 12.5, color: 'var(--lbb-fg)', fontWeight: 500,
              }}>
                {r.primary && (
                  <span title="primary target" style={{
                    width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                    background: 'var(--lbb-accent-mid)',
                    boxShadow: '0 0 6px var(--lbb-accent-mid)',
                  }} />
                )}
                {r.value}
              </span>
              <span style={{
                fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg2)',
                textAlign: 'right', whiteSpace: 'nowrap',
              }}>
                {r.version}
              </span>
            </div>
          ))}
        </div>
      ))}

      {/* Architecture note */}
      <div style={{
        display: 'flex', gap: 10, alignItems: 'flex-start',
        padding: '11px 13px', borderRadius: 8,
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      }}>
        <Icon name="info" size={14} style={{ color: 'var(--lbb-fg3)', marginTop: 1, flexShrink: 0 }} />
        <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.6, color: 'var(--lbb-fg2)' }}>
          {ARCH}
        </p>
      </div>
    </div>
  )
}

// ── Tab: Credits ──────────────────────────────────────────────────────────────

function AckCard({ a }: { a: Ack }): React.JSX.Element {
  const memory = a.tone === 'memory'
  return (
    <div style={{
      display: 'flex', gap: 13, padding: '13px 15px', borderRadius: 9,
      background: memory
        ? 'color-mix(in oklab, var(--lbb-accent-mid) 7%, var(--lbb-surface2))'
        : 'var(--lbb-surface2)',
      border: '1px solid var(--lbb-border)',
      borderLeft: `2px solid ${memory ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
    }}>
      <div style={{
        width: 34, height: 34, borderRadius: 8, flexShrink: 0,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: memory ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
        border: '1px solid var(--lbb-border2)',
        color: memory ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
      }}>
        <Icon name={memory ? 'star' : 'user'} size={15} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--lbb-fg)' }}>{a.name}</span>
          {memory && (
            <span style={{
              marginLeft: 'auto',
              fontFamily: 'var(--lbb-mono)', fontSize: 9.5, letterSpacing: 0.6,
              textTransform: 'uppercase', color: 'var(--lbb-accent-mid)',
              padding: '1px 7px', borderRadius: 4,
              background: 'var(--lbb-accent-soft)',
              border: '1px solid color-mix(in oklab, var(--lbb-accent-mid) 35%, transparent)',
            }}>
              In memory
            </span>
          )}
        </div>
        <div style={{
          fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: 'var(--lbb-fg3)', marginTop: 2,
        }}>
          {a.handle}
        </div>
        <p style={{ margin: '6px 0 0', fontSize: 11.8, lineHeight: 1.55, color: 'var(--lbb-fg2)' }}>
          {a.note}
        </p>
      </div>
    </div>
  )
}

function TabCredits(): React.JSX.Element {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      {ACKS.map(a => <AckCard key={a.name} a={a} />)}
    </div>
  )
}

// ── Tab: Changes ──────────────────────────────────────────────────────────────

const TAG_COLORS: Record<string, string> = {
  new:      'var(--lbb-accent-mid)',
  improved: 'var(--lbb-ok-fg)',
  changed:  'var(--lbb-warn-fg)',
  fixed:    'var(--lbb-fg3)',
}

function TabLog(): React.JSX.Element {
  const c = CHANGELOG
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>v{c.version}</span>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg3)' }}>
          {c.date}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {c.entries.map(([tag, text], i) => (
          <div key={i} style={{
            display: 'grid', gridTemplateColumns: '74px 1fr', gap: 12, alignItems: 'baseline',
          }}>
            <span style={{
              fontFamily: 'var(--lbb-mono)', fontSize: 9.5, letterSpacing: 0.5,
              textTransform: 'uppercase', fontWeight: 600,
              color: TAG_COLORS[tag] ?? 'var(--lbb-fg3)', textAlign: 'right',
            }}>
              {tag}
            </span>
            <span style={{ fontSize: 12.3, lineHeight: 1.5, color: 'var(--lbb-fg2)' }}>
              {text}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Footer ────────────────────────────────────────────────────────────────────

function AboutFooter(): React.JSX.Element {
  return (
    <div style={{
      padding: '12px 26px', borderTop: '1px solid var(--lbb-border)', flexShrink: 0,
      display: 'flex', alignItems: 'center', gap: 14,
      fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: 'var(--lbb-fg3)',
      background: 'var(--lbb-surface)',
    }}>
      <span>{META.copyright}</span>
      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12 }}>
        <span>DB {META.db}</span>
        <span>·</span>
        <span>build {META.build}</span>
      </span>
    </div>
  )
}

// ── AboutDialog ───────────────────────────────────────────────────────────────

export interface AboutDialogProps {
  onClose: () => void
}

export function AboutDialog({ onClose }: AboutDialogProps): React.JSX.Element {
  const [tab, setTab] = useState<TabId>('about')

  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  // Close on Escape key.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onCloseRef.current() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: '#131110',
        backgroundImage:
          'radial-gradient(120% 90% at 50% 0%, color-mix(in oklab, var(--lbb-accent-mid) 10%, transparent), transparent 50%)',
        padding: 18,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Dialog card */}
      <div style={{
        width: 700,
        maxWidth: '100%',
        maxHeight: '90vh',
        background: 'var(--lbb-surface)',
        border: '1px solid var(--lbb-border2)',
        borderRadius: 12,
        boxShadow: '0 24px 70px rgba(0,0,0,0.55)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <AboutHeader onClose={onClose} />
        <TabBar tab={tab} onTab={setTab} />
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: '22px 24px 26px' }}>
          {tab === 'about'   && <TabAbout />}
          {tab === 'tech'    && <TabTech />}
          {tab === 'credits' && <TabCredits />}
          {tab === 'log'     && <TabLog />}
        </div>
        <AboutFooter />
      </div>
    </div>
  )
}
