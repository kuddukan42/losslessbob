import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '../store'
import { Button, Pill, Icon, Banner } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

interface DbStats {
  total_checksums: number
  total_lb_numbers: number
  latest_lb: number
  last_import: string | null
}

interface HelperStatus {
  sox_available: boolean
  sox_version: string | null
  ffmpeg_available: boolean
  shntool_available: boolean
  flac_available: boolean
  ffmpeg_install_hint: string | null
  sox_install_hint: string | null
  flac_install_hint: string | null
  shntool_install_hint: string | null
}

interface AppSettings {
  auto_scrape: string | null
  search_page_size: string | null
  qbt_host: string | null
  qbt_port: string | null
  qbt_category: string | null
  qbt_tags: string | null
  wtrf_board_id: string | null
  tracker_list: string | null
  web_password: string | null
  data_dir: string
}

interface MasterStatus {
  master_version: string | null
  master_published_at: string | null
}

interface FlatRelease {
  id: number
  detected_at: string
  applied_at: string | null
  zip_filename: string
  zip_size_bytes: number | null
  rows_added: number | null
  rows_changed: number | null
  status: string
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ msg, tone, onDone }: { msg: string; tone: 'ok' | 'bad' | 'info'; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])

  const bg = tone === 'ok' ? 'var(--lbb-ok-bg)' : tone === 'bad' ? 'var(--lbb-err-bg)' : 'var(--lbb-surface2)'
  const border = tone === 'ok' ? 'var(--lbb-ok-bar)' : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-border2)'
  const color = tone === 'ok' ? 'var(--lbb-ok-fg)' : tone === 'bad' ? 'var(--lbb-err-fg)' : 'var(--lbb-fg)'

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 999,
      background: bg, border: `1px solid ${border}`, borderRadius: 8,
      padding: '10px 16px', color, fontSize: 'var(--lbb-fs-13)', fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.15)', maxWidth: 360,
    }}>
      {msg}
    </div>
  )
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────────

function ConfirmDialog({ title, body, onConfirm, onCancel }: {
  title: string; body: string; onConfirm: () => void; onCancel: () => void
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 440, width: '90%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 8 }}>{title}</div>
        <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', marginBottom: 20, lineHeight: 1.5 }}>{body}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>Confirm</Button>
        </div>
      </div>
    </div>
  )
}

// ── SetupCard ─────────────────────────────────────────────────────────────────

function SetupCard({
  title, badge, children, style,
}: {
  title: string; badge?: React.ReactNode; children?: React.ReactNode; style?: React.CSSProperties
}) {
  return (
    <div style={{
      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
      borderRadius: 10, padding: 18, ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span style={{
          fontSize: 'var(--lbb-fs-12)', fontWeight: 700, letterSpacing: 0.08,
          textTransform: 'uppercase', color: 'var(--lbb-fg)',
        }}>
          {title}
        </span>
        {badge}
      </div>
      {children}
    </div>
  )
}

// ── PurgeRow ──────────────────────────────────────────────────────────────────

function PurgeRow({
  item, count, barPct, onPurge, isLast,
}: {
  item: { label: string; desc: string; unit: string }
  count: number
  barPct: number
  onPurge: () => void
  isLast?: boolean
}) {
  const [hov, setHov] = React.useState(false)
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '9px minmax(140px, 1fr) 140px auto',
      alignItems: 'center',
      columnGap: 14,
      padding: '10px 6px',
      borderBottom: isLast ? 'none' : '1px solid var(--lbb-border)',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--lbb-border2)', display: 'inline-block', flexShrink: 0 }} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg)' }}>{item.label}</span>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>{item.desc}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
          {count.toLocaleString()}
          <em style={{ fontStyle: 'normal', color: 'var(--lbb-fg3)', fontWeight: 500, fontSize: 'var(--lbb-fs-11)', marginLeft: 4 }}>{item.unit}</em>
        </span>
        <span style={{ height: 4, borderRadius: 2, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
          <i style={{ display: 'block', height: '100%', borderRadius: 2, background: 'var(--lbb-border2)', width: `${barPct}%` }} />
        </span>
      </span>
      <button
        onClick={onPurge}
        onMouseEnter={() => setHov(true)}
        onMouseLeave={() => setHov(false)}
        style={{
          justifySelf: 'end',
          fontFamily: 'inherit',
          cursor: 'pointer',
          border: `1px solid ${hov ? '#e3a99b' : 'var(--lbb-border)'}`,
          background: hov ? '#fbe6df' : 'var(--lbb-surface)',
          color: hov ? '#b03f30' : 'var(--lbb-fg2)',
          fontSize: 'var(--lbb-fs-12)',
          fontWeight: 500,
          padding: '5px 12px',
          borderRadius: 7,
          transition: 'all 0.12s',
        }}
      >
        Purge
      </button>
    </div>
  )
}

// ── PurgeDangerZone ───────────────────────────────────────────────────────────

function PurgeDangerZone({
  item, count, onPurge, purgeAllLabel,
}: {
  item: { label: string; desc: string }
  count: number
  onPurge: () => void
  purgeAllLabel: string
}) {
  const [hov, setHov] = React.useState(false)
  return (
    <div style={{
      marginTop: 12,
      padding: '12px 12px 12px 14px',
      border: '1px solid #efd6cd',
      borderRadius: 10,
      background: 'rgba(208, 96, 79, 0.06)',
      display: 'grid',
      gridTemplateColumns: '4px 1fr auto',
      alignItems: 'center',
      columnGap: 12,
    }}>
      <span style={{ width: 4, alignSelf: 'stretch', borderRadius: 2, background: '#d8604f', display: 'block' }} />
      <span>
        <span style={{ display: 'block', fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: '#8f3526' }}>{item.label}</span>
        <span style={{ display: 'block', fontSize: 'var(--lbb-fs-11-5)', color: '#a86b5e', marginTop: 2, lineHeight: 1.4 }}>
          Collection, wishlist, ratings, alerts &amp; logs —{' '}
          <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600, color: '#8f3526' }}>{count.toLocaleString()}</span>
          {' '}records, not reversible.
        </span>
      </span>
      <button
        onClick={onPurge}
        onMouseEnter={() => setHov(true)}
        onMouseLeave={() => setHov(false)}
        style={{
          fontFamily: 'inherit',
          cursor: 'pointer',
          border: '1px solid #d8604f',
          background: hov ? '#b03f30' : 'var(--lbb-surface)',
          color: hov ? '#fff' : '#b03f30',
          fontSize: 'var(--lbb-fs-12)',
          fontWeight: 600,
          padding: '6px 14px',
          borderRadius: 7,
          transition: 'all 0.12s',
          whiteSpace: 'nowrap',
        }}
      >
        {purgeAllLabel}
      </button>
    </div>
  )
}

// ── MetaGrid ──────────────────────────────────────────────────────────────────

function MetaGrid({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '6px 16px', fontSize: 'var(--lbb-fs-12-5)' }}>
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <span style={{ color: 'var(--lbb-fg3)' }}>{label}</span>
          <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600, color: 'var(--lbb-fg)' }}>{value}</span>
        </React.Fragment>
      ))}
    </div>
  )
}

// ── CuratorToggle ─────────────────────────────────────────────────────────────

function CuratorToggle({
  masterStatus,
  busy,
  onPublish,
  onCheckGithub,
  onInstall,
}: {
  masterStatus: MasterStatus | null
  busy: string | null
  onPublish: () => void
  onCheckGithub: () => void
  onInstall: () => void
}) {
  const { t } = useTranslation()
  const curatorMode = useSettingsStore((s) => s.curatorMode)
  const setCuratorMode = useSettingsStore((s) => s.setCuratorMode)

  const version = masterStatus?.master_version ?? '—'
  const publishedAt = masterStatus?.master_published_at
    ? masterStatus.master_published_at.slice(0, 10)
    : '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{
        background: 'var(--lbb-surface2)', borderRadius: 8,
        border: '1px solid var(--lbb-border)', padding: 14,
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 38, height: 38, borderRadius: 8, flexShrink: 0,
          background: curatorMode ? 'var(--lbb-warn-bg)' : 'var(--lbb-surface)',
          border: `1px solid ${curatorMode ? 'var(--lbb-warn-bar)' : 'var(--lbb-border2)'}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'background 0.2s, border-color 0.2s',
          color: curatorMode ? 'var(--lbb-warn-fg)' : 'var(--lbb-fg3)',
        }}>
          <Icon name="dbeditor" size={18} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, lineHeight: 1.2, color: 'var(--lbb-fg)' }}>
            {t('setup.masterData.curatorMode')}
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 3, lineHeight: 1.4 }}>
            {t('setup.masterData.curatorDesc')}
          </div>
        </div>
        <button
          type="button"
          aria-checked={curatorMode}
          role="switch"
          onClick={() => setCuratorMode(!curatorMode)}
          style={{
            width: 44, height: 24, borderRadius: 12, flexShrink: 0,
            background: curatorMode ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
            border: 'none', cursor: 'pointer', padding: 0, position: 'relative',
            transition: 'background 0.2s',
          }}
        >
          <span style={{
            position: 'absolute', top: 2, left: curatorMode ? 22 : 2,
            width: 20, height: 20, borderRadius: '50%', background: '#fff',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)', transition: 'left 0.2s', display: 'block',
          }} />
        </button>
      </div>

      <MetaGrid rows={[
        [t('setup.masterData.masterVersion'), version],
        [t('setup.masterData.lastPublished'), publishedAt],
      ]} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button variant="secondary" icon="upload" disabled={!curatorMode} onClick={onPublish}>
          {t('setup.masterData.publishUpdate')}
        </Button>
        <Button variant="secondary" icon="download" disabled={busy === 'checkGithub' || busy === 'githubInstall'} onClick={onCheckGithub}>
          {busy === 'checkGithub' || busy === 'githubInstall'
            ? t('setup.masterData.checkingUpdate')
            : t('setup.masterData.checkUpdate')}
        </Button>
        <Button variant="ghost" icon="download" onClick={onInstall}>
          {t('setup.masterData.installUpdate')}
        </Button>
      </div>
    </div>
  )
}

// ── IntegCard ─────────────────────────────────────────────────────────────────

function IntegCard({
  title, tone, rows, onTest, onSave, onClear, editFields,
}: {
  title: string
  tone: 'ok' | 'warn' | 'mute'
  rows: [string, string][]
  onTest: () => void
  onSave?: (values: Record<string, string>) => void
  onClear?: () => void
  editFields?: { key: string; label: string; type?: string; placeholder?: string }[]
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [testTone, setTestTone] = useState<'ok' | 'bad' | null>(null)
  const [testMsg, setTestMsg] = useState('')

  const handleTest = async () => {
    setTestTone(null)
    setTestMsg(t('setup.integrations.testing'))
    await onTest()
  }

  const handleSave = () => {
    onSave?.(values)
    setEditing(false)
  }

  const handleClearConfirmed = () => {
    setConfirming(false)
    onClear?.()
  }

  return (
    <div style={{
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
      borderRadius: 8, padding: 14, display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)' }}>{title}</span>
        <Pill tone={tone} soft dot>
          {tone === 'ok' ? t('setup.integrations.connected') : tone === 'warn' ? t('setup.integrations.degraded') : t('setup.integrations.disabled')}
        </Pill>
      </div>

      {!editing && (
        <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '4px 8px', fontSize: 'var(--lbb-fs-11-5)' }}>
          {rows.map(([label, value]) => (
            <React.Fragment key={label}>
              <span style={{ color: 'var(--lbb-fg3)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{value}</span>
            </React.Fragment>
          ))}
        </div>
      )}

      {editing && editFields && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {editFields.map((f) => (
            <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <label style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', width: 80, flexShrink: 0 }}>
                {f.label}
              </label>
              <input
                type={f.type ?? 'text'}
                placeholder={f.placeholder}
                value={values[f.key] ?? ''}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                style={{
                  flex: 1, height: 24, padding: '0 8px', fontSize: 'var(--lbb-fs-11-5)',
                  background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
                  borderRadius: 5, color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)',
                  outline: 'none',
                }}
              />
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
        <Button variant="ghost" size="sm" onClick={handleTest}>{t('setup.integrations.test')}</Button>
        {editFields && !editing && (
          <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>{t('setup.integrations.edit')}</Button>
        )}
        {onClear && !editing && !confirming && (
          <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>{t('setup.integrations.clearCreds')}</Button>
        )}
        {confirming && (
          <>
            <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', alignSelf: 'center' }}>{t('setup.integrations.sure')}</span>
            <Button variant="danger" size="sm" onClick={handleClearConfirmed}>{t('setup.integrations.yesClear')}</Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>{t('common.cancel')}</Button>
          </>
        )}
        {editing && (
          <>
            <Button variant="secondary" size="sm" onClick={handleSave}>{t('common.save')}</Button>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>{t('common.cancel')}</Button>
          </>
        )}
      </div>
      {testMsg && (
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: testTone === 'bad' ? 'var(--lbb-err-fg)' : 'var(--lbb-fg3)' }}>
          {testMsg}
        </div>
      )}
    </div>
  )
}

// ── HelpersStrip ──────────────────────────────────────────────────────────────

function HelpersStrip({
  helpers,
  onRecheck,
}: {
  helpers: HelperStatus | null
  onRecheck: () => void
}) {
  const items = [
    { name: 'shntool', ok: helpers?.shntool_available ?? false, hint: helpers?.shntool_install_hint ?? null },
    { name: 'flac',    ok: helpers?.flac_available    ?? false, hint: helpers?.flac_install_hint    ?? null },
    { name: 'ffmpeg',  ok: helpers?.ffmpeg_available  ?? false, hint: helpers?.ffmpeg_install_hint  ?? null },
    { name: 'sox',     ok: helpers?.sox_available     ?? false, hint: helpers?.sox_install_hint     ?? null },
  ]
  const missingWithHints = items.filter(h => !h.ok && h.hint)

  return (
    <div style={{
      background: 'var(--lbb-surface2)', borderRadius: 6, padding: '8px 12px',
      marginTop: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', flex: 1, display: 'flex', gap: 14 }}>
          {items.map((h) => (
            <span key={h.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                background: helpers == null
                  ? 'var(--lbb-border2)'
                  : h.ok ? 'var(--lbb-ok-bar)' : 'var(--lbb-warn-bar)',
              }} />
              {h.name}
            </span>
          ))}
        </span>
        <Button variant="ghost" size="sm" icon="refresh" onClick={onRecheck}>Re-check</Button>
      </div>
      {missingWithHints.length > 0 && (
        <div style={{ marginTop: 7, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {missingWithHints.map((h) => (
            <div key={h.name} style={{
              fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)',
              fontFamily: 'var(--lbb-mono)',
            }}>
              <span style={{ color: 'var(--lbb-warn-bar)' }}>↳</span> {h.name}: {h.hint}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ScreenSetup ───────────────────────────────────────────────────────────────

export function ScreenSetup() {
  const { t } = useTranslation()
  const { language, setLanguage } = useSettingsStore()
const [dbStats, setDbStats] = useState<DbStats | null>(null)
  const [helpers, setHelpers] = useState<HelperStatus | null>(null)
  const [settings, setSettings] = useState<AppSettings>({
    auto_scrape: null, search_page_size: null,
    qbt_host: null, qbt_port: null, qbt_category: null, qbt_tags: null,
    wtrf_board_id: null, tracker_list: null, web_password: null, data_dir: '',
  })
  const [masterStatus, setMasterStatus] = useState<MasterStatus | null>(null)
  const [flatReleases, setFlatReleases] = useState<FlatRelease[]>([])
  const [flatBusyId, setFlatBusyId] = useState<number | null>(null)
  const [toast, setToast] = useState<{ msg: string; tone: 'ok' | 'bad' | 'info' } | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; body: string; onConfirm: () => void } | null>(null)
  const [pageSize, setPageSize] = useState('100')
  const [autoScrape, setAutoScrape] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [qbtTone, setQbtTone] = useState<'ok' | 'warn' | 'mute'>('mute')
  const [wtrfTone, setWtrfTone] = useState<'ok' | 'warn' | 'mute'>('mute')
  const [webUiTone, setWebUiTone] = useState<'ok' | 'warn' | 'mute'>('ok')
  const [trackerCount, setTrackerCount] = useState<number | null>(null)
  const [trackerBusy, setTrackerBusy] = useState(false)
  const [pkgBusy, setPkgBusy] = useState<'user' | 'scrape' | 'restore' | null>(null)
  const [pkgUserResult, setPkgUserResult] = useState<{ path: string; count: number; size: number } | null>(null)
  const [pkgScrapeResult, setPkgScrapeResult] = useState<{ path: string; count: number; size: number } | null>(null)
  const [purgeStats, setPurgeStats] = useState<Record<string, number>>({})
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((msg: string, tone: 'ok' | 'bad' | 'info' = 'info') => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, tone })
    toastTimer.current = setTimeout(() => setToast(null), 3500)
  }, [])

  // ── Load on mount ───────────────────────────────────────────────────────────

  const loadSettings = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/db/settings`)
      if (r.ok) {
        const s = await r.json() as AppSettings
        setSettings(s)
        setPageSize(s.search_page_size ?? '100')
        setAutoScrape(s.auto_scrape !== '0')
      }
    } catch { /* silently skip if backend not ready */ }
  }, [])  // tracker_list and web_password are read from settings state directly

  const loadDbStats = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/db/stats`)
      if (r.ok) setDbStats(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadHelpers = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/spectrogram/check`)
      if (r.ok) setHelpers(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadMasterStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/master/status`)
      if (r.ok) setMasterStatus(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadFlatReleases = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/flat_file/releases`)
      if (r.ok) setFlatReleases(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadPurgeStats = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/purge/stats`)
      if (r.ok) setPurgeStats(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadQbtStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/qbt/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean }
      setQbtTone(d.ok ? 'ok' : 'warn')
    } catch { /* ignore — service unavailable */ }
  }, [])

  const loadWtrfStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/wtrf/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean }
      setWtrfTone(d.ok ? 'ok' : 'warn')
    } catch { /* ignore — service unavailable */ }
  }, [])

  useEffect(() => {
    loadSettings()
    loadDbStats()
    loadHelpers()
    loadMasterStatus()
    loadFlatReleases()
    loadQbtStatus()
    loadWtrfStatus()
    loadPurgeStats()
  }, [loadSettings, loadDbStats, loadHelpers, loadMasterStatus, loadFlatReleases, loadQbtStatus, loadWtrfStatus, loadPurgeStats])

  // ── Settings save helper ─────────────────────────────────────────────────────

  const saveSetting = useCallback(async (key: string, value: string) => {
    try {
      const r = await fetch(`${BASE}/api/db/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) throw new Error((await r.json()).error ?? 'Save failed')
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, t])

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const handleCheckUpdate = useCallback(async () => {
    setBusy('update')
    try {
      const r = await fetch(`${BASE}/api/flat_file/discover`)
      const data = await r.json() as {
        available?: boolean | null
        current_release?: { zip_filename?: string } | null
        error?: string
      }
      if (data.error) { showToast(t('setup.toast.error', { error: data.error }), 'bad'); return }
      if (data.available) {
        showToast(t('setup.toast.newRelease', { filename: data.current_release?.zip_filename ?? '' }), 'ok')
        loadFlatReleases()
      } else {
        showToast(t('setup.toast.upToDate'), 'info')
      }
    } catch (e) {
      showToast(t('setup.toast.checkFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setBusy(null)
    }
  }, [showToast, loadFlatReleases, t])

  // ── Flat-file release: download + review/apply ───────────────────────────────

  const handleDownloadRelease = useCallback(async (id: number) => {
    setFlatBusyId(id)
    try {
      const r = await fetch(`${BASE}/api/flat_file/download/${id}`, { method: 'POST' })
      const d = await r.json() as { error?: string }
      if (d.error) { showToast(t('setup.toast.error', { error: d.error }), 'bad'); return }
      showToast(t('setup.flatFile.downloadDone'), 'ok')
      loadFlatReleases()
    } catch (e) {
      showToast(t('setup.toast.checkFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setFlatBusyId(null)
    }
  }, [showToast, loadFlatReleases, t])

  const handleApplyRelease = useCallback((id: number) => {
    setConfirm(null)
    setFlatBusyId(id)
    fetch(`${BASE}/api/flat_file/apply/${id}`, { method: 'POST' })
      .then((r) => r.json())
      .then((d: { error?: string; rows_added?: number; rows_changed?: number; rows_removed?: number }) => {
        if (d.error) { showToast(t('setup.toast.error', { error: d.error }), 'bad'); return }
        showToast(t('setup.flatFile.applyDone', {
          added: d.rows_added ?? 0, changed: d.rows_changed ?? 0, removed: d.rows_removed ?? 0,
        }), 'ok')
        loadFlatReleases()
        loadDbStats()
      })
      .catch((e: Error) => showToast(t('setup.toast.checkFailed', { message: e.message }), 'bad'))
      .finally(() => setFlatBusyId(null))
  }, [showToast, loadFlatReleases, loadDbStats, t])

  const handleReviewRelease = useCallback(async (rel: FlatRelease) => {
    setFlatBusyId(rel.id)
    try {
      const r = await fetch(`${BASE}/api/flat_file/diff/${rel.id}`)
      const d = await r.json() as {
        error?: string
        rows_added?: number; rows_changed?: number; rows_removed?: number
        new_lb_min?: number | null; new_lb_max?: number | null
      }
      if (d.error) { showToast(t('setup.toast.error', { error: d.error }), 'bad'); return }
      setConfirm({
        title: t('setup.flatFile.applyConfirmTitle'),
        body: t('setup.flatFile.applyConfirmBody', {
          filename: rel.zip_filename,
          added: d.rows_added ?? 0,
          changed: d.rows_changed ?? 0,
          removed: d.rows_removed ?? 0,
        }),
        onConfirm: () => handleApplyRelease(rel.id),
      })
    } catch (e) {
      showToast(t('setup.toast.checkFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setFlatBusyId(null)
    }
  }, [showToast, handleApplyRelease, t])

  const handleImportDb = useCallback(async () => {
    const path = await window.api.pickFile({
      title: 'Select DB file to import',
      filters: [{ name: 'Database', extensions: ['db', 'zip', 'txt'] }],
    })
    if (!path) return
    setBusy('import')
    showToast(t('setup.toast.startingImport'), 'info')
    try {
      const r = await fetch(`${BASE}/api/db/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: path }),
      })
      if (!r.ok) {
        const err = (await r.json()).error ?? 'Import failed'
        showToast(t('setup.toast.importError', { error: err }), 'bad')
        setBusy(null)
        return
      }
      // Poll status
      const poll = setInterval(async () => {
        try {
          const sr = await fetch(`${BASE}/api/db/import/status`)
          const st = await sr.json() as { running?: boolean; done?: boolean; error?: string; rows_added?: number }
          if (!st.running) {
            clearInterval(poll)
            setBusy(null)
            if (st.error) { showToast(t('setup.toast.importFailed', { error: st.error }), 'bad') }
            else {
              showToast(t('setup.toast.importComplete', { count: st.rows_added ?? 0 }), 'ok')
              loadDbStats()
              loadFlatReleases()
            }
          }
        } catch { clearInterval(poll); setBusy(null) }
      }, 800)
    } catch (e) {
      showToast(t('setup.toast.importError', { error: (e as Error).message }), 'bad')
      setBusy(null)
    }
  }, [showToast, loadDbStats, loadFlatReleases, t])

  const handleOpenDataFolder = useCallback(async () => {
    const dir = settings.data_dir
    if (!dir) { showToast(t('setup.toast.dataFolderUnavailable'), 'bad'); return }
    await window.api.openPath(dir)
  }, [settings.data_dir, showToast, t])

  const handleResetDb = useCallback(() => {
    setConfirm({
      title: 'Reset Database?',
      body: 'This drops all checksum and entry tables and reinitialises the schema. Your collection, wishlist, and personal settings are preserved. This cannot be undone.',
      onConfirm: async () => {
        setConfirm(null)
        setBusy('reset')
        try {
          const r = await fetch(`${BASE}/api/db/reset`, { method: 'POST' })
          if (r.ok) { showToast(t('setup.toast.dbReset'), 'ok'); loadDbStats() }
          else showToast(t('setup.toast.resetFailed', { error: (await r.json()).error }), 'bad')
        } catch (e) {
          showToast(t('setup.toast.resetFailed', { error: (e as Error).message }), 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, loadDbStats, t])

  const handleRecheckHelpers = useCallback(async () => {
    setHelpers(null)
    await loadHelpers()
  }, [loadHelpers])

  // ── Curator: Publish master ──────────────────────────────────────────────────

  const handlePublishMaster = useCallback(() => {
    setConfirm({
      title: 'Publish Master Update?',
      body: 'Build a master-only snapshot and upload it to GitHub releases? This writes a .db and .manifest.json to data/exports/, then calls the gh CLI to create a new release.',
      onConfirm: async () => {
        setConfirm(null)
        setBusy('publish')
        showToast(t('setup.toast.exportingMaster'), 'info')
        try {
          // Step 1: export
          const er = await fetch(`${BASE}/api/master/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: 'publish' }),
          })
          const ed = await er.json() as {
            ok?: boolean; error?: string; message?: string;
            path?: string; manifest_path?: string; manifest?: { master_version?: string }
          }
          if (!ed.ok || ed.error) {
            showToast(t('setup.toast.exportFailed', { message: ed.message ?? ed.error }), 'bad')
            setBusy(null)
            return
          }

          showToast(t('setup.toast.uploadingGithub'), 'info')

          // Step 2: GitHub release — server responds with text/event-stream progress
          const gr = await fetch(`${BASE}/api/master/github_release`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              db_path: ed.path,
              manifest_path: ed.manifest_path,
              version: ed.manifest?.master_version ?? '',
              prev_published_at: masterStatus?.master_published_at,
            }),
          })
          if (!gr.ok || !gr.body) {
            const errBody = await gr.json().catch(() => ({})) as { error?: string; message?: string }
            showToast(t('setup.toast.githubFailed', { message: errBody.message ?? errBody.error ?? gr.statusText }), 'bad')
            return
          }
          const reader = gr.body.getReader()
          const decoder = new TextDecoder()
          let buf = ''
          for (;;) {
            const { done, value } = await reader.read()
            if (done) break
            buf += decoder.decode(value, { stream: true })
            let nl: number
            while ((nl = buf.indexOf('\n\n')) >= 0) {
              const frame = buf.slice(0, nl)
              buf = buf.slice(nl + 2)
              if (!frame.startsWith('data: ')) continue
              const ev = JSON.parse(frame.slice(6)) as {
                type: string; label?: string; tag?: string; url?: string; error?: string; message?: string
              }
              if (ev.type === 'progress' && ev.label) {
                showToast(ev.label, 'info')
              } else if (ev.type === 'done') {
                showToast(t('setup.toast.released', { tag: ev.tag ?? '' }), 'ok')
                loadMasterStatus()
              } else if (ev.type === 'error') {
                showToast(t('setup.toast.githubFailed', { message: ev.message ?? ev.error }), 'bad')
              }
            }
          }
        } catch (e) {
          showToast(t('setup.toast.publishFailed', { message: (e as Error).message }), 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, masterStatus, loadMasterStatus, t])

  // ── Install master ──────────────────────────────────────────────────────────

  const handleInstallMaster = useCallback(async () => {
    const path = await window.api.pickFile({
      title: 'Select Master Snapshot',
      filters: [{ name: 'Master DB', extensions: ['db'] }],
    })
    if (!path) return
    setConfirm({
      title: 'Install Master Update?',
      body: `Apply this master snapshot to your local database?\n\n${path}\n\nYour collection, wishlist, and personal settings are preserved.`,
      onConfirm: async () => {
        setConfirm(null)
        setBusy('install')
        try {
          const r = await fetch(`${BASE}/api/master/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
          })
          const d = await r.json() as { ok?: boolean; error?: string; message?: string }
          if (d.ok) {
            showToast(t('setup.toast.masterInstalled'), 'ok')
            loadDbStats()
            loadMasterStatus()
          } else {
            showToast(t('setup.toast.installFailed', { message: d.message ?? d.error }), 'bad')
          }
        } catch (e) {
          showToast(t('setup.toast.installFailed', { message: (e as Error).message }), 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, loadDbStats, loadMasterStatus, t])

  // ── Check GitHub for master update ───────────────────────────────────────────

  const runGithubInstall = useCallback(async () => {
    setBusy('githubInstall')
    try {
      const gr = await fetch(`${BASE}/api/master/github_install`, { method: 'POST' })
      if (!gr.ok || !gr.body) {
        const errBody = await gr.json().catch(() => ({})) as { error?: string; message?: string }
        showToast(t('setup.toast.installFailed', { message: errBody.message ?? errBody.error ?? gr.statusText }), 'bad')
        return
      }
      const reader = gr.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let nl: number
        while ((nl = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, nl)
          buf = buf.slice(nl + 2)
          if (!frame.startsWith('data: ')) continue
          const ev = JSON.parse(frame.slice(6)) as { type: string; label?: string; error?: string; message?: string }
          if (ev.type === 'progress' && ev.label) {
            showToast(ev.label, 'info')
          } else if (ev.type === 'done') {
            showToast(t('setup.toast.masterInstalled'), 'ok')
            loadDbStats()
            loadMasterStatus()
          } else if (ev.type === 'error') {
            showToast(t('setup.toast.installFailed', { message: ev.message ?? ev.error }), 'bad')
          }
        }
      }
    } catch (e) {
      showToast(t('setup.toast.installFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setBusy(null)
    }
  }, [showToast, loadDbStats, loadMasterStatus, t])

  const handleCheckGithubMaster = useCallback(async () => {
    setBusy('checkGithub')
    try {
      const r = await fetch(`${BASE}/api/master/github_check`)
      const d = await r.json() as {
        available?: boolean; error?: string; message?: string; tag?: string
      }
      if (d.error) {
        showToast(t('setup.toast.githubCheckFailed', { message: d.message ?? d.error }), 'bad')
        return
      }
      if (!d.available) {
        showToast(d.message ?? t('setup.toast.masterUpToDate'), 'info')
        return
      }
      setConfirm({
        title: 'Install Master Update?',
        body: t('setup.masterData.githubUpdateBody', { tag: d.tag ?? '' }),
        onConfirm: () => {
          setConfirm(null)
          void runGithubInstall()
        },
      })
    } catch (e) {
      showToast(t('setup.toast.githubCheckFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setBusy(null)
    }
  }, [showToast, t, runGithubInstall])

  // ── qBt ─────────────────────────────────────────────────────────────────────

  const handleQbtTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/qbt/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean; version?: string; error?: string }
      if (d.ok) { showToast(t('setup.toast.qbtOk', { version: d.version ?? '' }), 'ok'); setQbtTone('ok') }
      else { showToast(t('setup.toast.qbtError', { error: d.error ?? 'connection failed' }), 'bad'); setQbtTone('warn') }
    } catch (e) {
      showToast(t('setup.toast.qbtTestError', { error: (e as Error).message }), 'bad')
      setQbtTone('mute')
    }
  }, [showToast, t])

  const handleQbtSave = useCallback(async (values: Record<string, string>) => {
    try {
      const metaKeys = ['qbt_host', 'qbt_port', 'qbt_category', 'qbt_tags']
      const metaBody: Record<string, string> = {}
      metaKeys.forEach((k) => { if (values[k] !== undefined) metaBody[k] = values[k] })
      if (Object.keys(metaBody).length) {
        await fetch(`${BASE}/api/db/settings`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(metaBody),
        })
      }
      if (values.qbt_username || values.qbt_password || values.qbt_api_key) {
        await fetch(`${BASE}/api/credentials/qbt`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: values.qbt_username, password: values.qbt_password, api_key: values.qbt_api_key }),
        })
      }
      showToast(t('setup.toast.qbtSaved'), 'ok')
      loadSettings()
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, loadSettings, t])

  const handleQbtClear = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/credentials/qbt`, { method: 'DELETE' })
      showToast(t('setup.toast.qbtCleared'), 'ok')
      setQbtTone('mute')
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, t])

  // ── WTRF ─────────────────────────────────────────────────────────────────────

  const handleWtrfTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/wtrf/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean; username?: string; error?: string }
      if (d.ok) { showToast(t('setup.toast.wtrfOk', { username: d.username ?? '' }), 'ok'); setWtrfTone('ok') }
      else { showToast(t('setup.toast.wtrfError', { error: d.error ?? 'login failed' }), 'bad'); setWtrfTone('warn') }
    } catch (e) {
      showToast(t('setup.toast.wtrfTestError', { message: (e as Error).message }), 'bad')
      setWtrfTone('mute')
    }
  }, [showToast, t])

  const handleWtrfSave = useCallback(async (values: Record<string, string>) => {
    try {
      if (values.wtrf_username) {
        const r = await fetch(`${BASE}/api/credentials/wtrf`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: values.wtrf_username, password: values.wtrf_password }),
        })
        const d = await r.json() as { ok?: boolean; error?: string }
        if (!d.ok) { showToast(t('setup.toast.saveFailed', { error: d.error }), 'bad'); return }
      }
      showToast(t('setup.toast.forumSaved'), 'ok')
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, t])

  const handleWtrfClear = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/credentials/wtrf`, { method: 'DELETE' })
      showToast(t('setup.toast.forumCleared'), 'ok')
      setWtrfTone('mute')
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, t])

  // ── Admin web UI ─────────────────────────────────────────────────────────────

  const handleWebUiTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/admin/status`)
      if (r.ok) {
        setWebUiTone('ok')
        showToast(t('setup.toast.adminReachable'), 'ok')
      } else {
        setWebUiTone('warn')
        showToast(t('setup.toast.adminHttpError', { status: r.status }), 'bad')
      }
    } catch (e) {
      setWebUiTone('warn')
      showToast(t('setup.toast.adminUnreachable', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, t])

  const handleWebUiSave = useCallback(async (values: Record<string, string>) => {
    try {
      await fetch(`${BASE}/api/db/settings`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ web_password: values.web_password ?? '' }),
      })
      const msg = values.web_password
        ? t('setup.toast.passwordSet')
        : t('setup.toast.passwordCleared')
      showToast(msg, 'ok')
      loadSettings()
    } catch (e) {
      showToast(t('setup.toast.saveFailed', { error: (e as Error).message }), 'bad')
    }
  }, [showToast, loadSettings, t])

  // ── Tracker settings ─────────────────────────────────────────────────────────

  const handleTrackerListChange = useCallback(async (name: string) => {
    setSettings((s) => ({ ...s, tracker_list: name }))
    await saveSetting('tracker_list', name)
  }, [saveSetting])

  const handleRefreshTrackers = useCallback(async () => {
    setTrackerBusy(true)
    try {
      const list = settings.tracker_list ?? 'best'
      const r = await fetch(`${BASE}/api/trackers?list_name=${encodeURIComponent(list)}&force_refresh=1`)
      const d = await r.json() as { count?: number; error?: string }
      if (d.error) { showToast(t('setup.toast.trackerFetchError', { error: d.error }), 'bad'); return }
      setTrackerCount(d.count ?? 0)
      showToast(t('setup.toast.trackersLoaded', { count: d.count ?? 0 }), d.count ? 'ok' : 'bad')
    } catch (e) {
      showToast(t('setup.toast.trackerFetchFailed', { error: (e as Error).message }), 'bad')
    } finally {
      setTrackerBusy(false)
    }
  }, [showToast, settings.tracker_list, t])

  // ── Preferences ─────────────────────────────────────────────────────────────

  const handlePageSize = useCallback(async (v: string) => {
    setPageSize(v)
    await saveSetting('search_page_size', v === 'All' ? '0' : v)
  }, [saveSetting])

  const handleAutoScrape = useCallback(async (checked: boolean) => {
    setAutoScrape(checked)
    await saveSetting('auto_scrape', checked ? '1' : '0')
  }, [saveSetting])

  // ── Data purges ──────────────────────────────────────────────────────────────

  type PurgeItem = { label: string; desc: string; unit: string; endpoint: string | string[]; statKey: string }

  const SCOPE_ITEMS: PurgeItem[] = [
    { label: t('setup.purges.lookupHistory'),    desc: t('setup.purges.lookupHistoryDesc'),    unit: t('setup.purges.lookupHistoryUnit'),    endpoint: '/api/rename_history/purge', statKey: 'lookup_history' },
    { label: t('setup.purges.importLog'),        desc: t('setup.purges.importLogDesc'),        unit: t('setup.purges.importLogUnit'),        endpoint: '/api/flat_file/purge',      statKey: 'import_log' },
    { label: t('setup.purges.scraperCache'),     desc: t('setup.purges.scraperCacheDesc'),     unit: t('setup.purges.scraperCacheUnit'),     endpoint: '/api/scraper/purge',        statKey: 'scraper_cache' },
    { label: t('setup.purges.fingerprintCache'), desc: t('setup.purges.fingerprintCacheDesc'), unit: t('setup.purges.fingerprintCacheUnit'), endpoint: '/api/fingerprint/purge',    statKey: 'fingerprint_cache' },
  ]

  const ALL_USER_DATA_ITEM: PurgeItem = {
    label: t('setup.purges.allUserData'),
    desc: t('setup.purges.allUserDataDesc'),
    unit: 'records',
    statKey: 'all_user_data',
    endpoint: [
      '/api/rename_history/purge', '/api/flat_file/purge',
      '/api/scraper/purge', '/api/fingerprint/purge',
      '/api/collection/purge?scope=collection',
      '/api/collection/purge?scope=wishlist',
      '/api/collection/purge?scope=personal_meta',
      '/api/collection/purge?scope=integrity_events',
      '/api/collection/purge?scope=entry_changes',
    ],
  }

  const handlePurge = useCallback((item: PurgeItem) => {
    setConfirm({
      title: `Purge ${item.label}?`,
      body: `This will permanently delete all ${item.label.toLowerCase()} data. This cannot be undone.`,
      onConfirm: async () => {
        setConfirm(null)
        const endpoints = Array.isArray(item.endpoint) ? item.endpoint : [item.endpoint]
        try {
          for (const ep of endpoints) {
            const [path, qs] = ep.split('?')
            const scope = qs ? new URLSearchParams(qs).get('scope') ?? undefined : undefined
            await fetch(`${BASE}${path}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: scope ? JSON.stringify({ scope }) : '{}',
            })
          }
          showToast(t('setup.toast.purged', { label: item.label }), 'ok')
          if (endpoints.some((e) => e.includes('flat_file'))) loadFlatReleases()
          loadPurgeStats()
        } catch (e) {
          showToast(t('setup.toast.purgeFailed', { error: (e as Error).message }), 'bad')
        }
      },
    })
  }, [showToast, loadFlatReleases, loadPurgeStats, t])

  // ── Flat file Reveal ─────────────────────────────────────────────────────────

  const handleReveal = useCallback(async (rel: FlatRelease) => {
    const dir = settings.data_dir
    if (!dir) { showToast(t('setup.toast.dataFolderUnknown'), 'bad'); return }
    await window.api.openPath(`${dir}/downloads/${rel.zip_filename}`)
  }, [settings.data_dir, showToast, t])

  // ── Data package export ──────────────────────────────────────────────────────

  const handleExportUserData = useCallback(async () => {
    setPkgBusy('user')
    try {
      const r = await fetch(`${BASE}/api/package/user_data`, { method: 'POST' })
      const d = await r.json() as {
        ok?: boolean; path?: string; error?: string; message?: string
        manifest?: { file_count?: number; total_bytes?: number }
      }
      if (!d.ok || d.error) {
        showToast(t('setup.toast.packageExportFailed', { error: d.message ?? d.error }), 'bad')
      } else {
        const count = d.manifest?.file_count ?? 0
        const size = d.manifest?.total_bytes ?? 0
        setPkgUserResult({ path: d.path ?? '', count, size })
        showToast(`User data exported — ${count} files, ${(size / 1024).toFixed(0)} KB`, 'ok')
      }
    } catch (e) {
      showToast(t('setup.toast.packageExportFailed', { error: (e as Error).message }), 'bad')
    } finally {
      setPkgBusy(null)
    }
  }, [showToast, t])

  const handleExportScrapeData = useCallback(async () => {
    setPkgBusy('scrape')
    showToast(t('setup.toast.buildingArchive'), 'info')
    try {
      const r = await fetch(`${BASE}/api/package/scrape_data`, { method: 'POST' })
      const d = await r.json() as {
        ok?: boolean; path?: string; error?: string; message?: string
        manifest?: { file_count?: number; total_bytes?: number }
      }
      if (!d.ok || d.error) {
        showToast(t('setup.toast.packageExportFailed', { error: d.message ?? d.error }), 'bad')
      } else {
        const count = d.manifest?.file_count ?? 0
        const size = d.manifest?.total_bytes ?? 0
        setPkgScrapeResult({ path: d.path ?? '', count, size })
        showToast(t('setup.toast.scrapedExported', { count, size: (size / 1024 / 1024).toFixed(1) }), 'ok')
      }
    } catch (e) {
      showToast(t('setup.toast.packageExportFailed', { error: (e as Error).message }), 'bad')
    } finally {
      setPkgBusy(null)
    }
  }, [showToast, t])

  const handleRestorePackage = useCallback(async () => {
    const zipPath = await window.api.pickFile({
      title: 'Select Package Zip to Restore',
      filters: [{ name: 'Zip archives', extensions: ['zip'] }],
    })
    if (!zipPath) return

    // Dry-run first to detect conflicts.
    setPkgBusy('restore')
    try {
      const dr = await fetch(`${BASE}/api/package/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zip_path: zipPath, dry_run: true }),
      })
      const dd = await dr.json() as {
        ok?: boolean; type?: string; error?: string; message?: string
        restored?: { name: string; dest: string }[]
        conflicts?: { name: string; dest: string }[]
      }
      if (!dd.ok || dd.error) {
        showToast(t('setup.toast.packageExportFailed', { error: dd.message ?? dd.error }), 'bad')
        setPkgBusy(null)
        return
      }

      const allFiles = [...(dd.restored ?? []), ...(dd.conflicts ?? [])]
      if (allFiles.length === 0) {
        showToast(t('setup.toast.noRecognisableFiles'), 'bad')
        setPkgBusy(null)
        return
      }

      const conflictNames = (dd.conflicts ?? []).map(f => f.name)
      const overwriteNote = conflictNames.length > 0
        ? `\n\nThe following files will be overwritten:\n${conflictNames.join('\n')}`
        : ''

      setPkgBusy(null)
      setConfirm({
        title: 'Confirm Restore',
        body: `Package type: ${dd.type}\nFiles to restore: ${allFiles.length}${overwriteNote}\n\nProceed?`,
        onConfirm: async () => {
          setConfirm(null)
          setPkgBusy('restore')
          try {
            const r = await fetch(`${BASE}/api/package/restore`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ zip_path: zipPath, dry_run: false }),
            })
            const d = await r.json() as {
              ok?: boolean; type?: string; error?: string; message?: string
              restored?: unknown[]; conflicts?: unknown[]
            }
            if (!d.ok || d.error) {
              showToast(t('setup.toast.packageExportFailed', { error: d.message ?? d.error }), 'bad')
            } else {
              const n = (d.restored?.length ?? 0) + (d.conflicts?.length ?? 0)
              showToast(t('setup.toast.restored', { n, type: d.type }), 'ok')
            }
          } catch (e) {
            showToast(t('setup.toast.packageExportFailed', { error: (e as Error).message }), 'bad')
          } finally {
            setPkgBusy(null)
          }
        },
      })
    } catch (e) {
      showToast(t('setup.toast.packageExportFailed', { error: (e as Error).message }), 'bad')
      setPkgBusy(null)
    }
  }, [showToast, t])

  // ── Render ───────────────────────────────────────────────────────────────────

  const fmtNum = (n: number | null | undefined) =>
    n != null ? n.toLocaleString() : '—'

  const displayPageSize = settings.search_page_size === '0' ? 'All' : (settings.search_page_size ?? '100')

  const qbtRows: [string, string][] = [
    [t('setup.integrations.host'), `${settings.qbt_host ?? '—'}:${settings.qbt_port ?? '—'}`],
    [t('setup.integrations.category'), settings.qbt_category ?? '—'],
    [t('setup.integrations.tags'), settings.qbt_tags || '—'],
  ]

  const wtrfRows: [string, string][] = [
    ['Board ID', settings.wtrf_board_id ?? '—'],
    ['Status', wtrfTone === 'ok' ? t('setup.integrations.connected') : wtrfTone === 'warn' ? 'error' : 'not tested'],
  ]

  const webUiPasswordStatus = settings.web_password === 'set' ? 'set' : 'not configured'
  const webUiRows: [string, string][] = [
    ['URL', `${BASE}/admin`],
    ['Auth', webUiPasswordStatus],
    ['Status', settings.web_password === 'set' ? 'password protected' : 'open access'],
  ]

  const TRACKER_LISTS = ['best', 'all', 'all_udp', 'all_http', 'all_https']
  const currentTrackerList = settings.tracker_list ?? 'best'

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      {toast && (
        <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />
      )}
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}

      <div style={{ padding: '24px 32px 40px', maxWidth: 1500, margin: '0 auto' }}>
        <h1 style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, letterSpacing: -0.02, color: 'var(--lbb-fg)', margin: 0 }}>
          {t('setup.title')}
        </h1>
        <p style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          {t('setup.subtitle')}
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>

          {/* ── Database ── */}
          <SetupCard
            title={t('setup.database.title')}
            badge={<Pill tone={dbStats ? 'ok' : 'mute'} soft dot>{dbStats ? t('setup.database.connected') : t('setup.database.loading')}</Pill>}
          >
            <MetaGrid rows={[
              [t('setup.database.active'), 'LosslessBob'],
              [t('setup.database.checksums'), fmtNum(dbStats?.total_checksums)],
              [t('setup.database.lbEntries'), fmtNum(dbStats?.total_lb_numbers)],
              [t('setup.database.lastImport'), dbStats?.last_import ?? '—'],
            ]} />
            <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
              <Button
                variant="secondary" icon="download" size="sm"
                disabled={busy === 'import'}
                onClick={handleImportDb}
              >
                {busy === 'import' ? t('setup.database.importing') : t('setup.database.importDb')}
              </Button>
              <Button
                variant="secondary" icon="refresh" size="sm"
                disabled={busy === 'update'}
                onClick={handleCheckUpdate}
              >
                {busy === 'update' ? t('setup.database.checking') : t('setup.database.checkUpdate')}
              </Button>
              <Button variant="ghost" icon="folder" size="sm" onClick={handleOpenDataFolder}>
                {t('setup.database.openDataFolder')}
              </Button>
              <Button variant="danger" icon="trash" size="sm" disabled={busy === 'reset'} onClick={handleResetDb}>
                {t('setup.database.resetDb')}
              </Button>
            </div>
            <HelpersStrip helpers={helpers} onRecheck={handleRecheckHelpers} />
          </SetupCard>

          {/* ── Master Data ── */}
          <SetupCard title={t('setup.masterData.title')}>
            <CuratorToggle
              masterStatus={masterStatus}
              busy={busy}
              onPublish={handlePublishMaster}
              onCheckGithub={handleCheckGithubMaster}
              onInstall={handleInstallMaster}
            />
          </SetupCard>

          {/* ── Integrations ── */}
          <SetupCard title={t('setup.integrations.title')} style={{ gridColumn: 'span 2' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
              <IntegCard
                title={t('setup.integrations.qbt')}
                tone={qbtTone}
                rows={qbtRows}
                onTest={handleQbtTest}
                onSave={handleQbtSave}
                onClear={handleQbtClear}
                editFields={[
                  { key: 'qbt_host', label: t('setup.integrations.host'), placeholder: 'localhost' },
                  { key: 'qbt_port', label: t('setup.integrations.port'), placeholder: '8080' },
                  { key: 'qbt_category', label: t('setup.integrations.category'), placeholder: 'losslessbob' },
                  { key: 'qbt_tags', label: t('setup.integrations.tags'), placeholder: 'optional' },
                  { key: 'qbt_username', label: t('setup.integrations.username'), placeholder: 'optional' },
                  { key: 'qbt_password', label: t('setup.integrations.password'), type: 'password', placeholder: 'optional' },
                  { key: 'qbt_api_key', label: t('setup.integrations.apiKey'), type: 'password', placeholder: 'optional' },
                ]}
              />
              <IntegCard
                title={t('setup.integrations.wtrf')}
                tone={wtrfTone}
                rows={wtrfRows}
                onTest={handleWtrfTest}
                onSave={handleWtrfSave}
                onClear={handleWtrfClear}
                editFields={[
                  { key: 'wtrf_username', label: t('setup.integrations.username') },
                  { key: 'wtrf_password', label: t('setup.integrations.password'), type: 'password' },
                ]}
              />
              <IntegCard
                title={t('setup.integrations.adminUi')}
                tone={webUiTone}
                rows={webUiRows}
                onTest={handleWebUiTest}
                onSave={handleWebUiSave}
                editFields={[
                  { key: 'web_password', label: t('setup.integrations.password'), type: 'password', placeholder: 'leave empty to disable auth' },
                ]}
              />
              {/* ── Torrent Settings ── */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 14, display: 'flex', flexDirection: 'column', gap: 10,
              }}>
                <span style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)' }}>{t('setup.torrent.title')}</span>
                <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: '6px 8px', fontSize: 'var(--lbb-fs-11-5)', alignItems: 'center' }}>
                  <span style={{ color: 'var(--lbb-fg3)' }}>{t('setup.torrent.trackerList')}</span>
                  <select
                    value={currentTrackerList}
                    onChange={(e) => handleTrackerListChange(e.target.value)}
                    style={{
                      height: 24, padding: '0 6px', fontSize: 'var(--lbb-fs-11-5)',
                      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
                      borderRadius: 5, color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)',
                      outline: 'none', cursor: 'pointer',
                    }}
                  >
                    {TRACKER_LISTS.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                  {trackerCount !== null && (
                    <>
                      <span style={{ color: 'var(--lbb-fg3)' }}>{t('setup.torrent.trackers')}</span>
                      <span style={{ fontFamily: 'var(--lbb-mono)', color: trackerCount > 0 ? 'var(--lbb-ok-bar)' : 'var(--lbb-err-bar)' }}>
                        {trackerCount} loaded
                      </span>
                    </>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
                  <Button variant="ghost" size="sm" onClick={handleRefreshTrackers} disabled={trackerBusy}>
                    {trackerBusy ? t('setup.torrent.fetching') : t('setup.torrent.refresh')}
                  </Button>
                </div>
              </div>
            </div>
          </SetupCard>

          {/* ── Preferences ── */}
          <SetupCard title={t('setup.preferences.title')}>
            <div style={{
              display: 'grid', gridTemplateColumns: '140px 1fr',
              gap: '8px 16px', fontSize: 'var(--lbb-fs-12-5)', alignItems: 'center',
            }}>
              <span style={{ color: 'var(--lbb-fg3)' }}>{t('setup.preferences.resultsPerPage')}</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {['50', '100', '250', 'All'].map((v) => {
                  const active = v === displayPageSize
                  return (
                    <button
                      key={v}
                      type="button"
                      onClick={() => handlePageSize(v)}
                      style={{
                        height: 24, padding: '0 9px', fontSize: 'var(--lbb-fs-11-5)',
                        fontWeight: active ? 700 : 500, borderRadius: 5,
                        background: active ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface2)',
                        color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                        border: `1px solid ${active ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                        cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >
                      {v}
                    </button>
                  )
                })}
              </div>

              <span style={{ color: 'var(--lbb-fg3)' }}>{t('setup.preferences.autoScrape')}</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={autoScrape}
                  onChange={(e) => handleAutoScrape(e.target.checked)}
                  style={{ accentColor: 'var(--lbb-accent-mid)' }}
                />
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                  {autoScrape ? t('setup.preferences.enabled') : t('setup.preferences.disabled')}
                </span>
              </label>

              <span style={{ color: 'var(--lbb-fg3)' }}>{t('setup.preferences.language')}</span>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value)}
                style={{
                  height: 28, padding: '0 8px', fontSize: 'var(--lbb-fs-12-5)',
                  background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
                  borderRadius: 5, color: 'var(--lbb-fg)', cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                {(['en','de','fr','es','it','nl'] as const).map(code => (
                  <option key={code} value={code}>{t(`setup.languages.${code}`)}</option>
                ))}
              </select>

            </div>
          </SetupCard>

          {/* ── Data purges ── */}
          <SetupCard
            title={t('setup.purges.title')}
            badge={
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, flex: 1 }}>
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                  {t('setup.purges.subtitle')}
                </span>
                {purgeStats['recoverable_bytes'] != null && purgeStats['recoverable_bytes'] > 0 && (
                  <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
                    <span style={{ fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                      {purgeStats['recoverable_bytes'] >= 1073741824
                        ? `≈ ${(purgeStats['recoverable_bytes'] / 1073741824).toFixed(1)} GB`
                        : `≈ ${(purgeStats['recoverable_bytes'] / 1048576).toFixed(0)} MB`}
                    </span>
                    {' '}{t('setup.purges.recoverable')}
                  </span>
                )}
              </span>
            }
          >
            {/* Scope rows */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {(() => {
                const maxCount = Math.max(...SCOPE_ITEMS.map(i => purgeStats[i.statKey] ?? 0), 1)
                return SCOPE_ITEMS.map((item, idx) => {
                  const n = purgeStats[item.statKey] ?? 0
                  const barPct = Math.round((n / maxCount) * 100)
                  return (
                    <PurgeRow
                      key={item.statKey}
                      item={item}
                      count={n}
                      barPct={barPct}
                      onPurge={() => handlePurge(item)}
                      isLast={idx === SCOPE_ITEMS.length - 1}
                    />
                  )
                })
              })()}
            </div>

            {/* Danger zone — all user data */}
            <PurgeDangerZone
              item={ALL_USER_DATA_ITEM}
              count={purgeStats['all_user_data'] ?? 0}
              onPurge={() => handlePurge(ALL_USER_DATA_ITEM)}
              purgeAllLabel={t('setup.purges.purgeAll')}
            />

            {/* Protected archive callout */}
            <div style={{
              marginTop: 12, paddingTop: 12,
              borderTop: '1px solid var(--lbb-border)',
              display: 'flex', alignItems: 'center', gap: 8,
              fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
            }}>
              <span style={{ flex: '0 0 auto', width: 8, height: 8, borderRadius: '50%', background: '#39a360', display: 'inline-block' }} />
              <span>
                {t('setup.purges.archiveProtected')}
              </span>
            </div>
          </SetupCard>

          {/* ── Data Packages ── */}
          <SetupCard title={t('setup.packages.title')}>
            <p style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', margin: '0 0 14px', lineHeight: 1.5 }}>
              {t('setup.packages.desc')}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* User data */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  {t('setup.packages.userData')}
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  {t('setup.packages.userDataDesc')}
                </div>
                {pkgUserResult && (
                  <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginBottom: 8, fontFamily: 'var(--lbb-mono)' }}>
                    ✓ {pkgUserResult.count} files · {(pkgUserResult.size / 1024).toFixed(0)} KB
                    <br />
                    <span
                      style={{ color: 'var(--lbb-accent-mid)', cursor: 'pointer', textDecoration: 'underline' }}
                      onClick={() => window.api.openPath(pkgUserResult.path)}
                    >
                      {pkgUserResult.path}
                    </span>
                  </div>
                )}
                <Button
                  variant="secondary" icon="download" size="sm"
                  disabled={pkgBusy !== null}
                  onClick={handleExportUserData}
                >
                  {pkgBusy === 'user' ? t('setup.packages.exporting') : t('setup.packages.exportUserData')}
                </Button>
              </div>

              {/* Scraped site data */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  {t('setup.packages.scrapedData')}
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  {t('setup.packages.scrapedDataDesc')}
                </div>
                {pkgScrapeResult && (
                  <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginBottom: 8, fontFamily: 'var(--lbb-mono)' }}>
                    ✓ {pkgScrapeResult.count} files · {(pkgScrapeResult.size / 1024 / 1024).toFixed(1)} MB
                    <br />
                    <span
                      style={{ color: 'var(--lbb-accent-mid)', cursor: 'pointer', textDecoration: 'underline' }}
                      onClick={() => window.api.openPath(pkgScrapeResult.path)}
                    >
                      {pkgScrapeResult.path}
                    </span>
                  </div>
                )}
                <Button
                  variant="secondary" icon="download" size="sm"
                  disabled={pkgBusy !== null}
                  onClick={handleExportScrapeData}
                >
                  {pkgBusy === 'scrape' ? t('setup.packages.exporting') : t('setup.packages.exportScraped')}
                </Button>
              </div>

              {/* Restore */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  {t('setup.packages.restore')}
                </div>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  {t('setup.packages.restoreDesc')}
                </div>
                <Button
                  variant="secondary" icon="upload" size="sm"
                  disabled={pkgBusy !== null}
                  onClick={handleRestorePackage}
                >
                  {pkgBusy === 'restore' ? t('setup.database.checking') : t('setup.packages.restoreBtn')}
                </Button>
              </div>
            </div>
          </SetupCard>

          {/* ── Flat file history ── */}
          <SetupCard title={t('setup.flatFile.title')} style={{ gridColumn: 'span 2' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--lbb-fs-12)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                    {[t('setup.flatFile.colDetected'), t('setup.flatFile.colFilename'), t('setup.flatFile.colStatus'), t('setup.flatFile.colApplied'), t('setup.flatFile.colAdded'), t('setup.flatFile.colChanged'), ''].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '6px 10px', textAlign: 'left', fontSize: 'var(--lbb-fs-10-5)',
                          fontWeight: 700, letterSpacing: 0.05, textTransform: 'uppercase',
                          color: 'var(--lbb-fg3)',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {flatReleases.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: '16px 10px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center' }}>
                        {t('setup.flatFile.noHistory')}
                      </td>
                    </tr>
                  )}
                  {flatReleases.map((rel) => {
                    const isActive = rel.status === 'applied'
                    return (
                      <tr key={rel.id} style={{ borderBottom: '1px solid var(--lbb-border)', color: 'var(--lbb-fg2)' }}>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)' }}>
                          {rel.detected_at?.slice(0, 16) ?? '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)' }}>{rel.zip_filename}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <Pill tone={isActive ? 'ok' : 'mute'} soft dot>
                            {isActive ? t('setup.flatFile.active') : rel.status}
                          </Pill>
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)' }}>
                          {rel.applied_at?.slice(0, 10) ?? '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)' }}>
                          {rel.rows_added != null ? `+${rel.rows_added}` : '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)' }}>
                          {rel.rows_changed != null ? `~${rel.rows_changed}` : '—'}
                        </td>
                        <td style={{ padding: '8px 10px', display: 'flex', gap: 6 }}>
                          {(rel.status === 'detected' || rel.status === 'failed' || rel.status === 'deferred') && (
                            <Button
                              variant="secondary" size="sm" icon="download"
                              disabled={flatBusyId === rel.id}
                              onClick={() => handleDownloadRelease(rel.id)}
                            >
                              {flatBusyId === rel.id ? t('setup.flatFile.downloading') : t('setup.flatFile.download')}
                            </Button>
                          )}
                          {rel.status === 'downloaded' && (
                            <Button
                              variant="secondary" size="sm" icon="check"
                              disabled={flatBusyId === rel.id}
                              onClick={() => handleReviewRelease(rel)}
                            >
                              {flatBusyId === rel.id ? t('setup.flatFile.applying') : t('setup.flatFile.reviewApply')}
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" onClick={() => handleReveal(rel)}>{t('setup.flatFile.reveal')}</Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </SetupCard>

        </div>
      </div>
    </div>
  )
}
