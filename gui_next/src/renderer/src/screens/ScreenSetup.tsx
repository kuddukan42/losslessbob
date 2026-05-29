import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useSettingsStore } from '../store'
import { Button, Pill, Icon } from '../components'

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
      padding: '10px 16px', color, fontSize: 13, fontWeight: 500,
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
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 8 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--lbb-fg2)', marginBottom: 20, lineHeight: 1.5 }}>{body}</div>
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
          fontSize: 12, fontWeight: 700, letterSpacing: 0.08,
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

// ── MetaGrid ──────────────────────────────────────────────────────────────────

function MetaGrid({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '6px 16px', fontSize: 12.5 }}>
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
  onPublish,
  onInstall,
}: {
  masterStatus: MasterStatus | null
  onPublish: () => void
  onInstall: () => void
}) {
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
          <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2, color: 'var(--lbb-fg)' }}>
            Curator Mode
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 3, lineHeight: 1.4 }}>
            Enable direct DB editing, scraping, and master data publishing.
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
        ['Master version', version],
        ['Last published', publishedAt],
      ]} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button variant="secondary" icon="upload" disabled={!curatorMode} onClick={onPublish}>
          Publish master update…
        </Button>
        <Button variant="ghost" icon="download" onClick={onInstall}>
          Install master update…
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
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [testTone, setTestTone] = useState<'ok' | 'bad' | null>(null)
  const [testMsg, setTestMsg] = useState('')

  const handleTest = async () => {
    setTestTone(null)
    setTestMsg('Testing…')
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
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)' }}>{title}</span>
        <Pill tone={tone} soft dot>
          {tone === 'ok' ? 'connected' : tone === 'warn' ? 'degraded' : 'disabled'}
        </Pill>
      </div>

      {!editing && (
        <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '4px 8px', fontSize: 11.5 }}>
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
              <label style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', width: 80, flexShrink: 0 }}>
                {f.label}
              </label>
              <input
                type={f.type ?? 'text'}
                placeholder={f.placeholder}
                value={values[f.key] ?? ''}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                style={{
                  flex: 1, height: 24, padding: '0 8px', fontSize: 11.5,
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
        <Button variant="ghost" size="sm" onClick={handleTest}>Test</Button>
        {editFields && !editing && (
          <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>Edit…</Button>
        )}
        {onClear && !editing && !confirming && (
          <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>Clear creds</Button>
        )}
        {confirming && (
          <>
            <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', alignSelf: 'center' }}>Sure?</span>
            <Button variant="danger" size="sm" onClick={handleClearConfirmed}>Yes, clear</Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>Cancel</Button>
          </>
        )}
        {editing && (
          <>
            <Button variant="secondary" size="sm" onClick={handleSave}>Save</Button>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
          </>
        )}
      </div>
      {testMsg && (
        <div style={{ fontSize: 11, color: testTone === 'bad' ? 'var(--lbb-err-fg)' : 'var(--lbb-fg3)' }}>
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
    { name: 'shntool', ok: helpers?.shntool_available ?? false },
    { name: 'flac',    ok: helpers?.flac_available    ?? false },
    { name: 'ffmpeg',  ok: helpers?.ffmpeg_available  ?? false },
    { name: 'sox',     ok: helpers?.sox_available     ?? false },
  ]

  return (
    <div style={{
      background: 'var(--lbb-surface2)', borderRadius: 6, padding: '8px 12px',
      display: 'flex', alignItems: 'center', gap: 16, marginTop: 14,
    }}>
      <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', flex: 1, display: 'flex', gap: 14 }}>
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
  )
}

// ── ScreenSetup ───────────────────────────────────────────────────────────────

export function ScreenSetup() {
  const [dbStats, setDbStats] = useState<DbStats | null>(null)
  const [helpers, setHelpers] = useState<HelperStatus | null>(null)
  const [settings, setSettings] = useState<AppSettings>({
    auto_scrape: null, search_page_size: null,
    qbt_host: null, qbt_port: null, qbt_category: null, qbt_tags: null,
    wtrf_board_id: null, tracker_list: null, web_password: null, data_dir: '',
  })
  const [masterStatus, setMasterStatus] = useState<MasterStatus | null>(null)
  const [flatReleases, setFlatReleases] = useState<FlatRelease[]>([])
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

  useEffect(() => {
    loadSettings()
    loadDbStats()
    loadHelpers()
    loadMasterStatus()
    loadFlatReleases()
  }, [loadSettings, loadDbStats, loadHelpers, loadMasterStatus, loadFlatReleases])

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
      showToast(`Save failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast])

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const handleCheckUpdate = useCallback(async () => {
    setBusy('update')
    try {
      const r = await fetch(`${BASE}/api/flat_file/discover`)
      const data = await r.json() as { new_release?: boolean; zip_filename?: string; error?: string }
      if (data.error) { showToast(`Error: ${data.error}`, 'bad'); return }
      if (data.new_release) {
        showToast(`New release available: ${data.zip_filename ?? ''}`, 'ok')
        loadFlatReleases()
      } else {
        showToast('Already up to date.', 'info')
      }
    } catch (e) {
      showToast(`Check failed: ${(e as Error).message}`, 'bad')
    } finally {
      setBusy(null)
    }
  }, [showToast, loadFlatReleases])

  const handleImportDb = useCallback(async () => {
    const path = await window.api.pickFile({
      title: 'Select DB file to import',
      filters: [{ name: 'Database', extensions: ['db', 'zip', 'txt'] }],
    })
    if (!path) return
    setBusy('import')
    showToast('Starting import…', 'info')
    try {
      const r = await fetch(`${BASE}/api/db/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: path }),
      })
      if (!r.ok) {
        const err = (await r.json()).error ?? 'Import failed'
        showToast(`Import error: ${err}`, 'bad')
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
            if (st.error) { showToast(`Import failed: ${st.error}`, 'bad') }
            else {
              showToast(`Import complete — ${st.rows_added ?? 0} rows added`, 'ok')
              loadDbStats()
              loadFlatReleases()
            }
          }
        } catch { clearInterval(poll); setBusy(null) }
      }, 800)
    } catch (e) {
      showToast(`Import error: ${(e as Error).message}`, 'bad')
      setBusy(null)
    }
  }, [showToast, loadDbStats, loadFlatReleases])

  const handleOpenDataFolder = useCallback(async () => {
    const dir = settings.data_dir
    if (!dir) { showToast('Data folder path not available', 'bad'); return }
    await window.api.openPath(dir)
  }, [settings.data_dir, showToast])

  const handleResetDb = useCallback(() => {
    setConfirm({
      title: 'Reset Database?',
      body: 'This drops all checksum and entry tables and reinitialises the schema. Your collection, wishlist, and personal settings are preserved. This cannot be undone.',
      onConfirm: async () => {
        setConfirm(null)
        setBusy('reset')
        try {
          const r = await fetch(`${BASE}/api/db/reset`, { method: 'POST' })
          if (r.ok) { showToast('Database reset.', 'ok'); loadDbStats() }
          else showToast(`Reset failed: ${(await r.json()).error}`, 'bad')
        } catch (e) {
          showToast(`Reset failed: ${(e as Error).message}`, 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, loadDbStats])

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
        showToast('Exporting master snapshot…', 'info')
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
            showToast(`Export failed: ${ed.message ?? ed.error}`, 'bad')
            setBusy(null)
            return
          }

          showToast('Uploading to GitHub…', 'info')

          // Step 2: GitHub release
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
          const gd = await gr.json() as { ok?: boolean; tag?: string; url?: string; error?: string; message?: string }
          if (gd.ok) {
            showToast(`Released ${gd.tag ?? ''}`, 'ok')
            loadMasterStatus()
          } else {
            showToast(`GitHub upload failed: ${gd.message ?? gd.error}`, 'bad')
          }
        } catch (e) {
          showToast(`Publish failed: ${(e as Error).message}`, 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, masterStatus, loadMasterStatus])

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
            showToast('Master update installed.', 'ok')
            loadDbStats()
            loadMasterStatus()
          } else {
            showToast(`Install failed: ${d.message ?? d.error}`, 'bad')
          }
        } catch (e) {
          showToast(`Install failed: ${(e as Error).message}`, 'bad')
        } finally {
          setBusy(null)
        }
      },
    })
  }, [showToast, loadDbStats, loadMasterStatus])

  // ── qBt ─────────────────────────────────────────────────────────────────────

  const handleQbtTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/qbt/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean; version?: string; error?: string }
      if (d.ok) { showToast(`qBittorrent OK${d.version ? ` — v${d.version}` : ''}`, 'ok'); setQbtTone('ok') }
      else { showToast(`qBittorrent: ${d.error ?? 'connection failed'}`, 'bad'); setQbtTone('warn') }
    } catch (e) {
      showToast(`qBt test error: ${(e as Error).message}`, 'bad')
      setQbtTone('mute')
    }
  }, [showToast])

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
      showToast('qBittorrent settings saved.', 'ok')
      loadSettings()
    } catch (e) {
      showToast(`Save failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast, loadSettings])

  const handleQbtClear = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/credentials/qbt`, { method: 'DELETE' })
      showToast('qBittorrent credentials cleared.', 'ok')
      setQbtTone('mute')
    } catch (e) {
      showToast(`Clear failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast])

  // ── WTRF ─────────────────────────────────────────────────────────────────────

  const handleWtrfTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/wtrf/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json() as { ok?: boolean; username?: string; error?: string }
      if (d.ok) { showToast(`WTRF OK — logged in as ${d.username ?? ''}`, 'ok'); setWtrfTone('ok') }
      else { showToast(`WTRF: ${d.error ?? 'login failed'}`, 'bad'); setWtrfTone('warn') }
    } catch (e) {
      showToast(`WTRF test error: ${(e as Error).message}`, 'bad')
      setWtrfTone('mute')
    }
  }, [showToast])

  const handleWtrfSave = useCallback(async (values: Record<string, string>) => {
    try {
      if (values.wtrf_username) {
        const r = await fetch(`${BASE}/api/credentials/wtrf`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: values.wtrf_username, password: values.wtrf_password }),
        })
        const d = await r.json() as { ok?: boolean; error?: string }
        if (!d.ok) { showToast(`Save failed: ${d.error}`, 'bad'); return }
      }
      showToast('Forum credentials saved.', 'ok')
    } catch (e) {
      showToast(`Save failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast])

  const handleWtrfClear = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/credentials/wtrf`, { method: 'DELETE' })
      showToast('Forum credentials cleared.', 'ok')
      setWtrfTone('mute')
    } catch (e) {
      showToast(`Clear failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast])

  // ── Admin web UI ─────────────────────────────────────────────────────────────

  const handleWebUiTest = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/admin/status`)
      if (r.ok) {
        setWebUiTone('ok')
        showToast('Admin web UI is reachable.', 'ok')
      } else {
        setWebUiTone('warn')
        showToast(`Admin web UI error: HTTP ${r.status}`, 'bad')
      }
    } catch (e) {
      setWebUiTone('warn')
      showToast(`Admin web UI unreachable: ${(e as Error).message}`, 'bad')
    }
  }, [showToast])

  const handleWebUiSave = useCallback(async (values: Record<string, string>) => {
    try {
      await fetch(`${BASE}/api/db/settings`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ web_password: values.web_password ?? '' }),
      })
      const msg = values.web_password
        ? 'Password set — admin UI requires login.'
        : 'Password cleared — admin UI is open access.'
      showToast(msg, 'ok')
      loadSettings()
    } catch (e) {
      showToast(`Save failed: ${(e as Error).message}`, 'bad')
    }
  }, [showToast, loadSettings])

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
      if (d.error) { showToast(`Tracker fetch error: ${d.error}`, 'bad'); return }
      setTrackerCount(d.count ?? 0)
      showToast(`${d.count ?? 0} trackers loaded.`, d.count ? 'ok' : 'bad')
    } catch (e) {
      showToast(`Tracker fetch failed: ${(e as Error).message}`, 'bad')
    } finally {
      setTrackerBusy(false)
    }
  }, [showToast, settings.tracker_list])

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

  const PURGE_ITEMS: { label: string; endpoint: string | string[] }[] = [
    { label: 'Lookup history',    endpoint: '/api/rename_history/purge' },
    { label: 'Import log',        endpoint: '/api/flat_file/purge' },
    { label: 'Scraper cache',     endpoint: '/api/scraper/purge' },
    { label: 'Fingerprint cache', endpoint: '/api/fingerprint/purge' },
    {
      label: 'All user data',
      endpoint: [
        '/api/rename_history/purge', '/api/flat_file/purge',
        '/api/scraper/purge', '/api/fingerprint/purge',
        '/api/collection/purge?scope=collection',
        '/api/collection/purge?scope=wishlist',
        '/api/collection/purge?scope=personal_meta',
        '/api/collection/purge?scope=integrity_events',
        '/api/collection/purge?scope=entry_changes',
      ],
    },
  ]

  const handlePurge = useCallback((item: typeof PURGE_ITEMS[number]) => {
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
          showToast(`${item.label} purged.`, 'ok')
          if (endpoints.some((e) => e.includes('flat_file'))) loadFlatReleases()
        } catch (e) {
          showToast(`Purge failed: ${(e as Error).message}`, 'bad')
        }
      },
    })
  }, [showToast, loadFlatReleases])

  // ── Flat file Reveal ─────────────────────────────────────────────────────────

  const handleReveal = useCallback(async (rel: FlatRelease) => {
    const dir = settings.data_dir
    if (!dir) { showToast('Data folder unknown', 'bad'); return }
    await window.api.openPath(`${dir}/downloads/${rel.zip_filename}`)
  }, [settings.data_dir, showToast])

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
        showToast(`Export failed: ${d.message ?? d.error}`, 'bad')
      } else {
        const count = d.manifest?.file_count ?? 0
        const size = d.manifest?.total_bytes ?? 0
        setPkgUserResult({ path: d.path ?? '', count, size })
        showToast(`User data exported — ${count} files, ${(size / 1024).toFixed(0)} KB`, 'ok')
      }
    } catch (e) {
      showToast(`Export failed: ${(e as Error).message}`, 'bad')
    } finally {
      setPkgBusy(null)
    }
  }, [showToast])

  const handleExportScrapeData = useCallback(async () => {
    setPkgBusy('scrape')
    showToast('Building scraped site archive — this may take a moment…', 'info')
    try {
      const r = await fetch(`${BASE}/api/package/scrape_data`, { method: 'POST' })
      const d = await r.json() as {
        ok?: boolean; path?: string; error?: string; message?: string
        manifest?: { file_count?: number; total_bytes?: number }
      }
      if (!d.ok || d.error) {
        showToast(`Export failed: ${d.message ?? d.error}`, 'bad')
      } else {
        const count = d.manifest?.file_count ?? 0
        const size = d.manifest?.total_bytes ?? 0
        setPkgScrapeResult({ path: d.path ?? '', count, size })
        showToast(`Scraped data exported — ${count} files, ${(size / 1024 / 1024).toFixed(1)} MB`, 'ok')
      }
    } catch (e) {
      showToast(`Export failed: ${(e as Error).message}`, 'bad')
    } finally {
      setPkgBusy(null)
    }
  }, [showToast])

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
        showToast(`Restore failed: ${dd.message ?? dd.error}`, 'bad')
        setPkgBusy(null)
        return
      }

      const allFiles = [...(dd.restored ?? []), ...(dd.conflicts ?? [])]
      if (allFiles.length === 0) {
        showToast('Zip contains no recognisable files to restore.', 'bad')
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
              showToast(`Restore failed: ${d.message ?? d.error}`, 'bad')
            } else {
              const n = (d.restored?.length ?? 0) + (d.conflicts?.length ?? 0)
              showToast(`Restored ${n} file(s) from ${d.type} package.`, 'ok')
            }
          } catch (e) {
            showToast(`Restore failed: ${(e as Error).message}`, 'bad')
          } finally {
            setPkgBusy(null)
          }
        },
      })
    } catch (e) {
      showToast(`Restore failed: ${(e as Error).message}`, 'bad')
      setPkgBusy(null)
    }
  }, [showToast])

  // ── Render ───────────────────────────────────────────────────────────────────

  const fmtNum = (n: number | null | undefined) =>
    n != null ? n.toLocaleString() : '—'

  const displayPageSize = settings.search_page_size === '0' ? 'All' : (settings.search_page_size ?? '100')

  const qbtRows: [string, string][] = [
    ['Host', `${settings.qbt_host ?? '—'}:${settings.qbt_port ?? '—'}`],
    ['Category', settings.qbt_category ?? '—'],
    ['Tags', settings.qbt_tags || '—'],
  ]

  const wtrfRows: [string, string][] = [
    ['Board ID', settings.wtrf_board_id ?? '—'],
    ['Status', wtrfTone === 'ok' ? 'connected' : 'not tested'],
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
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.02, color: 'var(--lbb-fg)', margin: 0 }}>
          Setup
        </h1>
        <p style={{ fontSize: 13, color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          Database management, integrations, and preferences.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>

          {/* ── Database ── */}
          <SetupCard
            title="Database"
            badge={<Pill tone={dbStats ? 'ok' : 'mute'} soft dot>{dbStats ? 'connected' : 'loading'}</Pill>}
          >
            <MetaGrid rows={[
              ['Active', 'LosslessBob'],
              ['Checksums', fmtNum(dbStats?.total_checksums)],
              ['LB entries', fmtNum(dbStats?.total_lb_numbers)],
              ['Last import', dbStats?.last_import ?? '—'],
            ]} />
            <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
              <Button
                variant="secondary" icon="download" size="sm"
                disabled={busy === 'import'}
                onClick={handleImportDb}
              >
                {busy === 'import' ? 'Importing…' : 'Import DB file…'}
              </Button>
              <Button
                variant="secondary" icon="refresh" size="sm"
                disabled={busy === 'update'}
                onClick={handleCheckUpdate}
              >
                {busy === 'update' ? 'Checking…' : 'Check for update'}
              </Button>
              <Button variant="ghost" icon="folder" size="sm" onClick={handleOpenDataFolder}>
                Open data folder
              </Button>
              <Button variant="danger" icon="trash" size="sm" disabled={busy === 'reset'} onClick={handleResetDb}>
                Reset DB…
              </Button>
            </div>
            <HelpersStrip helpers={helpers} onRecheck={handleRecheckHelpers} />
          </SetupCard>

          {/* ── Master Data ── */}
          <SetupCard title="Master Data">
            <CuratorToggle
              masterStatus={masterStatus}
              onPublish={handlePublishMaster}
              onInstall={handleInstallMaster}
            />
          </SetupCard>

          {/* ── Integrations ── */}
          <SetupCard title="Integrations" style={{ gridColumn: 'span 2' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
              <IntegCard
                title="qBittorrent"
                tone={qbtTone}
                rows={qbtRows}
                onTest={handleQbtTest}
                onSave={handleQbtSave}
                onClear={handleQbtClear}
                editFields={[
                  { key: 'qbt_host', label: 'Host', placeholder: 'localhost' },
                  { key: 'qbt_port', label: 'Port', placeholder: '8080' },
                  { key: 'qbt_category', label: 'Category', placeholder: 'losslessbob' },
                  { key: 'qbt_tags', label: 'Tags', placeholder: 'optional' },
                  { key: 'qbt_username', label: 'Username', placeholder: 'optional' },
                  { key: 'qbt_password', label: 'Password', type: 'password', placeholder: 'optional' },
                  { key: 'qbt_api_key', label: 'API Key', type: 'password', placeholder: 'optional' },
                ]}
              />
              <IntegCard
                title="Watching the River Flow"
                tone={wtrfTone}
                rows={wtrfRows}
                onTest={handleWtrfTest}
                onSave={handleWtrfSave}
                onClear={handleWtrfClear}
                editFields={[
                  { key: 'wtrf_username', label: 'Username' },
                  { key: 'wtrf_password', label: 'Password', type: 'password' },
                ]}
              />
              <IntegCard
                title="Admin web UI"
                tone={webUiTone}
                rows={webUiRows}
                onTest={handleWebUiTest}
                onSave={handleWebUiSave}
                editFields={[
                  { key: 'web_password', label: 'Password', type: 'password', placeholder: 'leave empty to disable auth' },
                ]}
              />
              {/* ── Torrent Settings ── */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 14, display: 'flex', flexDirection: 'column', gap: 10,
              }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)' }}>Torrent Settings</span>
                <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: '6px 8px', fontSize: 11.5, alignItems: 'center' }}>
                  <span style={{ color: 'var(--lbb-fg3)' }}>Tracker list</span>
                  <select
                    value={currentTrackerList}
                    onChange={(e) => handleTrackerListChange(e.target.value)}
                    style={{
                      height: 24, padding: '0 6px', fontSize: 11.5,
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
                      <span style={{ color: 'var(--lbb-fg3)' }}>Trackers</span>
                      <span style={{ fontFamily: 'var(--lbb-mono)', color: trackerCount > 0 ? 'var(--lbb-ok-bar)' : 'var(--lbb-err-bar)' }}>
                        {trackerCount} loaded
                      </span>
                    </>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
                  <Button variant="ghost" size="sm" onClick={handleRefreshTrackers} disabled={trackerBusy}>
                    {trackerBusy ? 'Fetching…' : 'Refresh Trackers'}
                  </Button>
                </div>
              </div>
            </div>
          </SetupCard>

          {/* ── Preferences ── */}
          <SetupCard title="Preferences">
            <div style={{
              display: 'grid', gridTemplateColumns: '140px 1fr',
              gap: '8px 16px', fontSize: 12.5, alignItems: 'center',
            }}>
              <span style={{ color: 'var(--lbb-fg3)' }}>Results per page</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {['50', '100', '250', 'All'].map((v) => {
                  const active = v === displayPageSize
                  return (
                    <button
                      key={v}
                      type="button"
                      onClick={() => handlePageSize(v)}
                      style={{
                        height: 24, padding: '0 9px', fontSize: 11.5,
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

              <span style={{ color: 'var(--lbb-fg3)' }}>Auto-scrape on import</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={autoScrape}
                  onChange={(e) => handleAutoScrape(e.target.checked)}
                  style={{ accentColor: 'var(--lbb-accent-mid)' }}
                />
                <span style={{ fontSize: 11.5, color: 'var(--lbb-fg3)' }}>
                  {autoScrape ? 'enabled' : 'disabled'}
                </span>
              </label>
            </div>
          </SetupCard>

          {/* ── Data purges ── */}
          <SetupCard title="Data purges">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {PURGE_ITEMS.map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    fontSize: 12.5, color: 'var(--lbb-fg2)',
                  }}
                >
                  <span>{item.label}</span>
                  <Button variant="ghost" size="sm" onClick={() => handlePurge(item)}>Purge…</Button>
                </div>
              ))}
            </div>
            <p style={{ fontSize: 11, color: 'var(--lbb-fg3)', marginTop: 14, marginBottom: 0, lineHeight: 1.4 }}>
              User data only. The checksum archive is never affected.
            </p>
          </SetupCard>

          {/* ── Data Packages ── */}
          <SetupCard title="Data Packages">
            <p style={{ fontSize: 12, color: 'var(--lbb-fg3)', margin: '0 0 14px', lineHeight: 1.5 }}>
              Export your data as portable zip archives saved to <code style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>data/exports/</code>.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* User data */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  User data
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  Bundles <code style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>losslessbob.db</code>,{' '}
                  <code style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>settings.ini</code>, and{' '}
                  <code style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>gui_state.json</code>.
                </div>
                {pkgUserResult && (
                  <div style={{ fontSize: 11, color: 'var(--lbb-fg3)', marginBottom: 8, fontFamily: 'var(--lbb-mono)' }}>
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
                  {pkgBusy === 'user' ? 'Exporting…' : 'Export user data…'}
                </Button>
              </div>

              {/* Scraped site data */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  Scraped site data
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  Bundles all HTML pages and attachment files from{' '}
                  <code style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>data/site/</code>.
                  Useful for seeding another install without re-crawling.
                </div>
                {pkgScrapeResult && (
                  <div style={{ fontSize: 11, color: 'var(--lbb-fg3)', marginBottom: 8, fontFamily: 'var(--lbb-mono)' }}>
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
                  {pkgBusy === 'scrape' ? 'Exporting…' : 'Export scraped site data…'}
                </Button>
              </div>

              {/* Restore */}
              <div style={{
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: 12,
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--lbb-fg)', marginBottom: 4 }}>
                  Restore from zip
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginBottom: 10, lineHeight: 1.4 }}>
                  Import a zip archive exported by this app. Auto-detects package type (user data or
                  scraped site). Shows a conflict preview before writing anything.
                </div>
                <Button
                  variant="secondary" icon="upload" size="sm"
                  disabled={pkgBusy !== null}
                  onClick={handleRestorePackage}
                >
                  {pkgBusy === 'restore' ? 'Checking…' : 'Restore from zip…'}
                </Button>
              </div>
            </div>
          </SetupCard>

          {/* ── Flat file history ── */}
          <SetupCard title="Flat file history" style={{ gridColumn: 'span 2' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                    {['Detected', 'Filename', 'Status', 'Applied', 'Added', 'Changed', ''].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '6px 10px', textAlign: 'left', fontSize: 10.5,
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
                      <td colSpan={7} style={{ padding: '16px 10px', color: 'var(--lbb-fg3)', fontSize: 12, textAlign: 'center' }}>
                        No import history yet.
                      </td>
                    </tr>
                  )}
                  {flatReleases.map((rel) => {
                    const isActive = rel.status === 'applied'
                    return (
                      <tr key={rel.id} style={{ borderBottom: '1px solid var(--lbb-border)', color: 'var(--lbb-fg2)' }}>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>
                          {rel.detected_at?.slice(0, 16) ?? '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)' }}>{rel.zip_filename}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <Pill tone={isActive ? 'ok' : 'mute'} soft dot>
                            {isActive ? 'active' : rel.status}
                          </Pill>
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>
                          {rel.applied_at?.slice(0, 10) ?? '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>
                          {rel.rows_added != null ? `+${rel.rows_added}` : '—'}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--lbb-mono)', fontSize: 11.5 }}>
                          {rel.rows_changed != null ? `~${rel.rows_changed}` : '—'}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <Button variant="ghost" size="sm" onClick={() => handleReveal(rel)}>Reveal</Button>
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
