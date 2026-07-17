import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { useSettingsStore } from '../store'

// ── Nav structure ────────────────────────────────────────────────────────────

type NavId =
  | 'home' | 'pipeline' | 'quicklookup'
  | 'library' | 'collection' | 'trading' | 'sharing' | 'search' | 'bootlegs' | 'tapematch' | 'songs' | 'gaps'
  | 'attachments' | 'spectrograms' | 'map'
  | 'scraper' | 'fingerprint' | 'setup' | 'mounts' | 'themes' | 'dbeditor'

type NavGroupLabel = 'Ingest' | 'Library' | 'Assets' | 'Curator' | 'Settings'

const NAV_GROUP_KEYS: Record<NavGroupLabel, `appShell.nav.${Lowercase<NavGroupLabel>}`> = {
  Ingest:   'appShell.nav.ingest',
  Library:  'appShell.nav.library',
  Assets:   'appShell.nav.assets',
  Curator:  'appShell.nav.curator',
  Settings: 'appShell.nav.settings',
}

interface NavItem {
  id: NavId
  label: string
  icon: string
  featured?: boolean
  count?: number
}

interface NavGroup {
  label: NavGroupLabel | null
  gatedGroup?: boolean
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ id: 'home', label: 'Home', icon: 'home' }],
  },
  {
    label: 'Ingest',
    items: [
      { id: 'pipeline', label: 'Pipeline', icon: 'pipeline' },
    ],
  },
  {
    label: 'Library',
    items: [
      { id: 'library',    label: 'Library',       icon: 'library', featured: true },
      { id: 'collection', label: 'My Collection', icon: 'collection' },
      { id: 'trading',    label: 'Trading',       icon: 'trading' },
      { id: 'sharing',    label: 'Sharing',       icon: 'share' },
      { id: 'search',     label: 'Search',        icon: 'search' },
      { id: 'bootlegs',   label: 'Bootlegs',      icon: 'bootlegs' },
      { id: 'tapematch',  label: 'TapeMatch',     icon: 'tapematch' },
      { id: 'songs',      label: 'Songs',         icon: 'songs' },
      { id: 'gaps',       label: 'Gaps',          icon: 'gaps' },
    ],
  },
  {
    label: 'Assets',
    items: [
      { id: 'attachments',  label: 'Attachments',  icon: 'attachments' },
      { id: 'spectrograms', label: 'Spectrograms', icon: 'spectro' },
      { id: 'map',          label: 'Map',          icon: 'map' },
    ],
  },
  {
    label: 'Curator',
    gatedGroup: true,
    items: [
      { id: 'scraper',     label: 'Scraper',     icon: 'scraper' },
      { id: 'fingerprint', label: 'Fingerprint', icon: 'fingerprint' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { id: 'setup',    label: 'Setup',     icon: 'setup' },
      { id: 'mounts',   label: 'Mounts',    icon: 'mounts' },
      { id: 'themes',   label: 'Themes',    icon: 'themes' },
      { id: 'dbeditor', label: 'DB Editor', icon: 'dbeditor' },
    ],
  },
]

// Derive breadcrumb trail from active screen id.
function deriveCrumbs(active: string): string[] {
  if (active === 'home') return ['LosslessBob']
  for (const group of NAV_GROUPS) {
    const item = group.items.find((i) => i.id === active)
    if (item) {
      return group.label
        ? ['LosslessBob', group.label, item.label]
        : ['LosslessBob', item.label]
    }
  }
  return ['LosslessBob']
}

const LANG_OPTIONS: { code: string; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'de', label: 'Deutsch' },
  { code: 'fr', label: 'Français' },
  { code: 'es', label: 'Español' },
  { code: 'it', label: 'Italiano' },
  { code: 'nl', label: 'Nederlands' },
]

// ── Sidebar ──────────────────────────────────────────────────────────────────

function Sidebar({
  active,
  onNav,
  curatorMode,
  onAbout,
}: {
  active: string
  onNav: (id: string) => void
  curatorMode: boolean
  onAbout?: () => void
}) {
  const { t } = useTranslation()
  const setCuratorMode = useSettingsStore((s) => s.setCuratorMode)
  const language = useSettingsStore((s) => s.language)
  const setLanguage = useSettingsStore((s) => s.setLanguage)
  const [collectionCount, setCollectionCount] = useState<number | undefined>(undefined)
  const [wtrfUsername, setWtrfUsername] = useState<string>('')
  const [langOpen, setLangOpen] = useState(false)
  const langRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!langOpen) return
    function onClickOut(e: MouseEvent) {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setLangOpen(false)
    }
    document.addEventListener('mousedown', onClickOut)
    return () => document.removeEventListener('mousedown', onClickOut)
  }, [langOpen])

  useEffect(() => {
    fetch(`${window.api.flaskBase}/api/home/stats`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((d: { collection_count?: number }) => {
        if (typeof d.collection_count === 'number') setCollectionCount(d.collection_count)
      })
      .catch(() => {})
    fetch(`${window.api.flaskBase}/api/credentials/wtrf`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((d: { username?: string }) => setWtrfUsername(d.username ?? ''))
      .catch(() => {})
  }, [])

  return (
    <aside
      style={{
        width: 224,
        flex: '0 0 224px',
        background: 'var(--lbb-surface)',
        borderRight: '1px solid var(--lbb-border)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
      }}
    >
      {/* Brand */}
      <div
        style={{
          padding: '16px 18px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          borderBottom: '1px solid var(--lbb-border)',
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: 'var(--lbb-accent-mid)',
            color: 'var(--lbb-accent-onMid)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: 'var(--lbb-fs-14)',
            letterSpacing: -0.02,
            boxShadow:
              '0 1px 0 rgba(255,255,255,0.18) inset, 0 1px 2px rgba(0,0,0,0.12)',
          }}
        >
          LB
        </div>
        <div>
          <div
            style={{
              fontSize: 'var(--lbb-fs-14)',
              fontWeight: 700,
              letterSpacing: -0.01,
              lineHeight: 1.1,
            }}
          >
            {t('appShell.brand')}
          </div>
          <div
            style={{
              fontSize: 'var(--lbb-fs-10-5)',
              color: 'var(--lbb-fg3)',
              marginTop: 2,
              letterSpacing: 0.04,
            }}
          >
            {t('appShell.version', { version: __APP_VERSION__ })}
          </div>
        </div>
      </div>

      {/* Nav */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 8px 16px' }}>
        {NAV_GROUPS.map((group, gi) => {
          if (group.gatedGroup && !curatorMode) return null
          return (
            <div key={gi} style={{ marginTop: gi === 0 ? 0 : 14 }}>
              {group.label && (
                <div
                  style={{
                    fontSize: 'var(--lbb-fs-10)',
                    fontWeight: 700,
                    color: 'var(--lbb-fg3)',
                    letterSpacing: 0.12,
                    textTransform: 'uppercase',
                    padding: '6px 10px 6px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>{group.label ? t(NAV_GROUP_KEYS[group.label]) : null}</span>
                  {group.gatedGroup && (
                    <span
                      style={{
                        fontSize: 'var(--lbb-fs-8-5)',
                        fontWeight: 700,
                        letterSpacing: 0.1,
                        padding: '1px 5px',
                        borderRadius: 3,
                        background: 'var(--lbb-warn-bg)',
                        color: 'var(--lbb-warn-fg)',
                        border: '1px solid var(--lbb-warn-bar)',
                      }}
                    >
                      {t('appShell.nav.curatorBadge')}
                    </span>
                  )}
                </div>
              )}
              {group.items.map((item) => {
                const isActive = item.id === active
                const dynamicCount = item.id === 'collection' ? collectionCount : item.count
                return (
                  <button
                    key={item.id}
                    type="button"
                    data-testid={`nav-${item.id}`}
                    onClick={() => onNav(item.id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '7px 10px',
                      marginBottom: 1,
                      border: '1px solid transparent',
                      borderRadius: 6,
                      background: isActive
                        ? 'var(--lbb-accent-soft)'
                        : 'transparent',
                      color: isActive
                        ? 'var(--lbb-accent-mid)'
                        : 'var(--lbb-fg2)',
                      fontSize: 'var(--lbb-fs-12-5)',
                      fontWeight: isActive ? 600 : 500,
                      textAlign: 'left',
                      cursor: 'pointer',
                      lineHeight: 1.2,
                      fontFamily: 'inherit',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive)
                        e.currentTarget.style.background =
                          'var(--lbb-surface2)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive)
                        e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <Icon name={item.icon} size={15} />
                    <span style={{ flex: 1 }}>{t(`appShell.nav.${item.id}`)}</span>
                    {item.featured && !isActive && (
                      <span
                        style={{
                          fontSize: 'var(--lbb-fs-8-5)',
                          fontWeight: 700,
                          padding: '0 5px',
                          borderRadius: 3,
                          background: 'var(--lbb-accent-soft)',
                          color: 'var(--lbb-accent-mid)',
                          letterSpacing: 0.06,
                        }}
                      >
                        NEW
                      </span>
                    )}
                    {dynamicCount !== undefined && (
                      <span
                        style={{
                          fontSize: 'var(--lbb-fs-10-5)',
                          color: isActive
                            ? 'var(--lbb-accent-mid)'
                            : 'var(--lbb-fg3)',
                          fontVariantNumeric: 'tabular-nums',
                          fontWeight: 500,
                        }}
                      >
                        {dynamicCount.toLocaleString()}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )
        })}

        {!curatorMode && (
          <div
            style={{
              margin: '16px 6px 0',
              padding: '10px 12px',
              background: 'var(--lbb-surface2)',
              borderRadius: 8,
              border: '1px dashed var(--lbb-border2)',
              fontSize: 'var(--lbb-fs-11)',
              color: 'var(--lbb-fg3)',
              lineHeight: 1.4,
            }}
          >
            {t('appShell.curatorHint')}
            <div style={{ marginTop: 6 }}>
              <span
                style={{
                  color: 'var(--lbb-accent-mid)',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                onClick={() => setCuratorMode(true)}
              >
                {t('appShell.curatorEnable')}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* User chip */}
      <div
        style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--lbb-border)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: 'var(--lbb-surface2)',
            border: '1px solid var(--lbb-border2)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 'var(--lbb-fs-11)',
            fontWeight: 700,
            color: 'var(--lbb-fg2)',
          }}
        >
          {wtrfUsername ? wtrfUsername.slice(0, 2).toUpperCase() : '—'}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, lineHeight: 1.1 }}>
            {wtrfUsername || t('appShell.noWtrfAccount')}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>
            Local · 4 mounts
          </div>
        </div>

        {/* Language picker */}
        <div ref={langRef} style={{ position: 'relative' }}>
          <button
            type="button"
            title={t('setup.preferences.language')}
            onClick={() => setLangOpen(o => !o)}
            style={{
              height: 24,
              padding: '0 6px',
              borderRadius: 5,
              background: langOpen ? 'var(--lbb-surface2)' : 'transparent',
              border: `1px solid ${langOpen ? 'var(--lbb-border2)' : 'transparent'}`,
              color: 'var(--lbb-fg3)',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 'var(--lbb-fs-10-5)',
              fontWeight: 600,
              fontFamily: 'var(--lbb-mono)',
              letterSpacing: 0.04,
            }}
          >
            <Icon name="globe" size={12} />
            {language.toUpperCase()}
          </button>
          {langOpen && (
            <div
              style={{
                position: 'absolute',
                bottom: '100%',
                right: 0,
                marginBottom: 4,
                background: 'var(--lbb-surface)',
                border: '1px solid var(--lbb-border2)',
                borderRadius: 8,
                boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
                minWidth: 130,
                padding: '4px 0',
                zIndex: 200,
              }}
            >
              {LANG_OPTIONS.map(({ code, label }) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => { setLanguage(code); setLangOpen(false) }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '5px 12px',
                    background: code === language ? 'var(--lbb-accent-soft)' : 'transparent',
                    border: 'none',
                    color: code === language ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                    fontSize: 'var(--lbb-fs-12-5)',
                    fontWeight: code === language ? 600 : 400,
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span style={{ fontSize: 'var(--lbb-fs-10)', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', minWidth: 18 }}>
                    {code.toUpperCase()}
                  </span>
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          title="About LosslessBob"
          onClick={onAbout}
          style={{
            width: 24,
            height: 24,
            borderRadius: 5,
            background: 'transparent',
            border: '1px solid transparent',
            color: 'var(--lbb-fg3)',
            cursor: onAbout ? 'pointer' : 'default',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="more" size={14} />
        </button>
      </div>
    </aside>
  )
}

// ── Topbar ───────────────────────────────────────────────────────────────────

function Topbar({
  crumbs,
  actions,
  hasNotification = true,
}: {
  crumbs: string[]
  actions?: React.ReactNode
  hasNotification?: boolean
}) {
  const { t } = useTranslation()
  return (
    <header
      style={{
        height: 52,
        flex: '0 0 52px',
        padding: '0 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--lbb-surface)',
      }}
    >
      {/* Breadcrumbs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          minWidth: 0,
        }}
      >
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && (
              <span style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>/</span>
            )}
            <span
              style={{
                fontSize: 'var(--lbb-fs-13)',
                fontWeight: i === crumbs.length - 1 ? 600 : 500,
                color:
                  i === crumbs.length - 1
                    ? 'var(--lbb-fg)'
                    : 'var(--lbb-fg2)',
                letterSpacing: -0.005,
              }}
            >
              {c}
            </span>
          </React.Fragment>
        ))}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Per-screen actions */}
      {actions}

      {/* Global search */}
      <button
        type="button"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
          height: 32,
          padding: '0 10px 0 12px',
          background: 'var(--lbb-surface2)',
          border: '1px solid var(--lbb-border)',
          borderRadius: 8,
          color: 'var(--lbb-fg3)',
          fontSize: 'var(--lbb-fs-12-5)',
          cursor: 'pointer',
          minWidth: 280,
          fontFamily: 'inherit',
        }}
      >
        <Icon name="search" size={14} />
        <span style={{ flex: 1, textAlign: 'left' }}>
          {t('appShell.search')}
        </span>
      </button>

      {/* Bell */}
      <button
        type="button"
        style={{
          width: 34,
          height: 34,
          borderRadius: 8,
          background: 'transparent',
          border: '1px solid transparent',
          color: 'var(--lbb-fg2)',
          cursor: 'pointer',
          position: 'relative',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon name="bell" size={16} />
        {hasNotification && (
          <span
            style={{
              position: 'absolute',
              top: 7,
              right: 8,
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: 'var(--lbb-bad-bar)',
              border: '1.5px solid var(--lbb-surface)',
            }}
          />
        )}
      </button>
    </header>
  )
}

// ── StatusBar ────────────────────────────────────────────────────────────────

interface FooterStats {
  checksum_count: number
  latest_lb: number
  last_import: string | null
  bootleg_count: number
  collection_size?: { bytes: number | null; human: string | null; computing: boolean }
}

function fmtNum(n: number): string {
  return n.toLocaleString()
}

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

function fmtLastImport(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return 'today'
  if (diffDays === 1) return 'yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return d.toISOString().slice(0, 10)
}

interface MasterSyncStatus {
  available: boolean
}

interface BusyStatus {
  busy: boolean
  activity: string | null
}

const BUSY_POLL_MS = 5000

function StatusBar({ extra }: { extra?: React.ReactNode }) {
  const { t } = useTranslation()
  const [stats, setStats] = useState<FooterStats | null>(null)
  const [masterSync, setMasterSync] = useState<MasterSyncStatus | null>(null)
  const [activity, setActivity] = useState<BusyStatus | null>(null)

  useEffect(() => {
    fetch(`${window.api.flaskBase}/api/home/stats`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setStats)
      .catch(() => { /* stats stay null, footer shows placeholders */ })
  }, [])

  useEffect(() => {
    fetch(`${window.api.flaskBase}/api/master/github_check`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: { available?: boolean }) => {
        if (typeof d.available === 'boolean') setMasterSync({ available: d.available })
      })
      .catch(() => { /* masterSync stays null, footer falls back to "Synced" */ })
  }, [])

  useEffect(() => {
    let cancelled = false
    function poll() {
      fetch(`${window.api.flaskBase}/api/activity/busy`)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d: BusyStatus) => { if (!cancelled) setActivity(d) })
        .catch(() => { /* activity stays as last-known value */ })
    }
    poll()
    const id = setInterval(poll, BUSY_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const sep = (
    <span style={{ color: 'var(--lbb-border2)', margin: '0 2px' }}>·</span>
  )

  function item(
    label: string,
    value: string,
    tone?: string
  ): React.ReactNode {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        {tone && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: `var(--lbb-${tone}-bar)`,
            }}
          />
        )}
        <span style={{ color: 'var(--lbb-fg3)' }}>{label}</span>
        <span
          style={{
            color: 'var(--lbb-fg2)',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {value}
        </span>
      </span>
    )
  }

  return (
    <footer
      style={{
        height: 28,
        flex: '0 0 28px',
        padding: '0 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        borderTop: '1px solid var(--lbb-border)',
        background: 'var(--lbb-surface)',
        fontSize: 'var(--lbb-fs-11)',
        fontFamily: 'var(--lbb-mono)',
      }}
    >
      {item(t('appShell.statusBar.db'), stats ? fmtLb(stats.latest_lb) : '…', 'ok')}
      {sep}
      {item(t('appShell.statusBar.checksums'), stats ? fmtNum(stats.checksum_count) : '…')}
      {sep}
      {item(t('appShell.statusBar.lastImport'), stats ? fmtLastImport(stats.last_import) : '…')}
      {sep}
      {item(t('appShell.statusBar.bootlegs'), stats ? fmtNum(stats.bootleg_count) : '…')}
      {sep}
      {item(
        t('appShell.statusBar.collectionSize'),
        stats?.collection_size?.human
          ?? (stats?.collection_size?.computing ? t('appShell.statusBar.computing') : '…')
      )}
      {extra && (
        <>
          {sep}
          {extra}
        </>
      )}
      <div style={{ flex: 1 }} />
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          color: 'var(--lbb-fg3)',
        }}
      >
        <Icon name="shield" size={11} />
        {masterSync?.available
          ? t('appShell.statusBar.updateAvailable')
          : t('appShell.statusBar.synced')}
        {masterSync?.available && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--lbb-warn-bar)',
            }}
          />
        )}
      </span>
      {sep}
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          color: 'var(--lbb-fg3)',
        }}
      >
        {activity?.busy && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--lbb-info-bar)',
            }}
          />
        )}
        {activity?.busy && activity.activity
          ? t(`appShell.statusBar.activity.${activity.activity}` as any)
          : t('appShell.statusBar.idle')}
      </span>
    </footer>
  )
}

// ── AppShell ─────────────────────────────────────────────────────────────────

export interface AppShellProps {
  crumbs?: string[]
  topActions?: React.ReactNode
  statusExtra?: React.ReactNode
  onAbout?: () => void
  children: React.ReactNode
}

export function AppShell({
  crumbs,
  topActions,
  statusExtra,
  onAbout,
  children,
}: AppShellProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const curatorMode = useSettingsStore((s) => s.curatorMode)

  const active =
    location.pathname === '/' ? 'home' : location.pathname.slice(1)

  function onNav(id: string) {
    navigate(id === 'home' ? '/' : `/${id}`)
  }

  const resolvedCrumbs = crumbs ?? deriveCrumbs(active)

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--lbb-bg)',
        color: 'var(--lbb-fg)',
        overflow: 'hidden',
      }}
    >
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Sidebar active={active} onNav={onNav} curatorMode={curatorMode} onAbout={onAbout} />
        <main
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
          }}
        >
          <Topbar crumbs={resolvedCrumbs} actions={topActions} />
          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            {children}
          </div>
        </main>
      </div>
      <StatusBar extra={statusExtra} />
    </div>
  )
}
