import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

interface ActiveShare {
  token: string
  folder_path: string
  files: string[]
  expires_at: string
  lb_number: number | null
  tunnel_url: string | null
}

interface TunnelStatus {
  cloudflared_available: boolean
  tunnel_alive: boolean
  tunnel_url: string | null
  named_tunnel: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtExpiry(isoStr: string): string {
  const exp = new Date(isoStr)
  const s = Math.floor((exp.getTime() - Date.now()) / 1000)
  if (s <= 0) return 'Expired'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function Toast({ msg, tone, onDone }: { msg: string; tone: 'ok' | 'bad' | 'info'; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])
  const bg     = tone === 'ok'  ? 'var(--lbb-ok-bg)'   : tone === 'bad' ? 'var(--lbb-err-bg)'  : 'var(--lbb-surface2)'
  const border = tone === 'ok'  ? 'var(--lbb-ok-bar)'  : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-border2)'
  const color  = tone === 'ok'  ? 'var(--lbb-ok-fg)'   : tone === 'bad' ? 'var(--lbb-err-fg)'  : 'var(--lbb-fg)'
  return (
    <div style={{
      position: 'fixed', bottom: 28, right: 24, zIndex: 9999,
      padding: '10px 18px', borderRadius: 8, border: `1px solid ${border}`,
      background: bg, color, fontSize: 'var(--lbb-fs-13)', fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.22)',
    }}>
      {msg}
    </div>
  )
}

// ── Create share form ─────────────────────────────────────────────────────────

function CreateShareForm({ tunnelStatus, onCreated }: { tunnelStatus: TunnelStatus | null; onCreated: () => void }) {
  const [lbNumber, setLbNumber] = useState('')
  const [ttlHours, setTtlHours] = useState('24')
  const [useTunnel, setUseTunnel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ share_url: string; tunnel_url: string | null; files: string[]; expires_at: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canTunnel = tunnelStatus?.cloudflared_available ?? false

  const handleCreate = async () => {
    if (!lbNumber.trim()) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetch(`${BASE}/api/share/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: parseInt(lbNumber), ttl_hours: parseInt(ttlHours), use_tunnel: useTunnel }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error ?? 'Share creation failed')
      setResult(data)
      onCreated()
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    height: 32, padding: '0 10px', borderRadius: 6,
    border: '1px solid var(--lbb-border2)', background: 'var(--lbb-bg)',
    color: 'var(--lbb-fg)', fontSize: 'var(--lbb-fs-13)', fontFamily: 'inherit',
  }

  return (
    <div style={{
      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
      borderRadius: 10, padding: 20, display: 'flex', flexDirection: 'column', gap: 14,
    }}>
      <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-fg)' }}>Create New Share</div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>LB Number</label>
          <input
            style={{ ...inputStyle, width: 110 }}
            placeholder="e.g. 1234"
            value={lbNumber}
            onChange={e => setLbNumber(e.target.value)}
            type="number"
            min={1}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Expires after</label>
          <select
            style={{ ...inputStyle, width: 130 }}
            value={ttlHours}
            onChange={e => setTtlHours(e.target.value)}
          >
            {[['4', '4 hours'], ['12', '12 hours'], ['24', '24 hours'], ['48', '48 hours'], ['168', '1 week']].map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 4 }}>
          <input
            id="use-tunnel"
            type="checkbox"
            checked={useTunnel}
            onChange={e => setUseTunnel(e.target.checked)}
            disabled={!canTunnel}
          />
          <label
            htmlFor="use-tunnel"
            style={{ fontSize: 'var(--lbb-fs-12-5)', color: canTunnel ? 'var(--lbb-fg)' : 'var(--lbb-fg3)', cursor: canTunnel ? 'pointer' : 'default' }}
          >
            Share over internet
            {!canTunnel && <span style={{ marginLeft: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-err-fg)' }}>(cloudflared not found)</span>}
          </label>
        </div>

        <button
          onClick={handleCreate}
          disabled={busy || !lbNumber.trim()}
          style={{
            height: 32, padding: '0 18px', borderRadius: 6,
            background: 'var(--lbb-accent-mid)', color: '#fff',
            border: 'none', fontSize: 'var(--lbb-fs-13)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            opacity: busy || !lbNumber.trim() ? 0.6 : 1,
          }}
        >
          {busy ? 'Creating…' : 'Create Share Link'}
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-err-fg)', padding: '8px 12px', background: 'var(--lbb-err-bg)', borderRadius: 6, border: '1px solid var(--lbb-err-bar)' }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
            Share link (expires {fmtExpiry(result.expires_at)} · {result.files.length} files):
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              readOnly
              value={result.share_url}
              style={{ ...inputStyle, flex: 1, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-accent-mid)' }}
              onClick={e => (e.target as HTMLInputElement).select()}
            />
            <button
              onClick={() => { navigator.clipboard.writeText(result.share_url) }}
              style={{
                height: 32, padding: '0 12px', borderRadius: 6,
                background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
                color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              <Icon name="copy" size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              Copy
            </button>
          </div>
          {result.tunnel_url && (
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-ok-fg)' }}>
              <Icon name="globe" size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              Cloudflare Tunnel active — your home IP is hidden.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Active shares list ────────────────────────────────────────────────────────

function ActiveSharesList({ shares, onRevoke }: { shares: ActiveShare[]; onRevoke: (token: string) => void }) {
  if (shares.length === 0) {
    return (
      <div style={{ padding: '24px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center' }}>
        No active shares. Create one above to share a folder with a friend.
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {shares.map(s => (
        <div key={s.token} style={{
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
          borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg)' }}>
              {s.lb_number ? `LB-${String(s.lb_number).padStart(5, '0')}` : 'Unknown'}
              <span style={{ marginLeft: 8, fontSize: 'var(--lbb-fs-11)', fontWeight: 400, color: 'var(--lbb-fg3)' }}>
                {s.files.length} files
              </span>
            </div>
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {s.folder_path}
            </div>
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
              Expires in {fmtExpiry(s.expires_at)}
              {s.tunnel_url && (
                <span style={{ marginLeft: 8, color: 'var(--lbb-ok-fg)' }}>
                  <Icon name="globe" size={11} style={{ marginRight: 3, verticalAlign: 'middle' }} />
                  Tunnel active
                </span>
              )}
            </div>
          </div>
          <button
            onClick={() => onRevoke(s.token)}
            style={{
              height: 28, padding: '0 10px', borderRadius: 6,
              background: 'transparent', border: '1px solid var(--lbb-err-bar)',
              color: 'var(--lbb-err-fg)', fontSize: 'var(--lbb-fs-12)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            Stop Sharing
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Tunnel status banner ──────────────────────────────────────────────────────

function TunnelBanner({ status }: { status: TunnelStatus | null }) {
  if (!status) return null
  if (status.named_tunnel) {
    return (
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-ok-fg)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Icon name="globe" size={13} />
        Named tunnel active — permanent URL via own domain
      </div>
    )
  }
  if (status.tunnel_alive) {
    return (
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-ok-fg)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Icon name="globe" size={13} />
        Quick tunnel active: {status.tunnel_url}
      </div>
    )
  }
  if (status.cloudflared_available) {
    return (
      <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Icon name="globe" size={13} />
        cloudflared available — enable "Share over internet" to start a tunnel
      </div>
    )
  }
  return (
    <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', display: 'flex', alignItems: 'center', gap: 6 }}>
      <Icon name="alert" size={13} />
      cloudflared not found — shares are LAN-only.
      Install from <a href="https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" style={{ color: 'var(--lbb-accent-mid)' }} target="_blank" rel="noreferrer">cloudflare.com</a> for internet sharing.
    </div>
  )
}

// ── Archive.org upload ────────────────────────────────────────────────────────

interface ArchiveUploadStatus {
  running: boolean
  lb_number: number | null
  identifier: string | null
  current_file: string | null
  files_done: number
  files_total: number
  bytes_done: number
  bytes_total: number
  status: 'idle' | 'running' | 'done' | 'failed' | 'stopped'
  error: string | null
  stop_requested: boolean
}

interface ArchiveUploadRow {
  id: number
  lb_number: number
  identifier: string
  folder_path: string
  files_total: number
  files_uploaded: number
  status: string
  started_at: string
  finished_at: string | null
  error: string | null
  date_str?: string
  location?: string
}

function pct(done: number, total: number): number {
  if (total <= 0) return 0
  return Math.min(100, Math.round((done / total) * 100))
}

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`
  return `${(n / 1073741824).toFixed(2)} GB`
}

function ArchiveOrgSection({ showToast }: { showToast: (msg: string, tone: 'ok' | 'bad' | 'info') => void }) {
  const [accessKey, setAccessKey]   = useState('')
  const [secretKey, setSecretKey]   = useState('')
  const [credStored, setCredStored] = useState(false)
  const [credBusy, setCredBusy]     = useState(false)

  const [lbNumber, setLbNumber]       = useState('')
  const [folderPath, setFolderPath]   = useState('')
  const [identifier, setIdentifier]   = useState('')
  const [collection, setCollection]   = useState('opensource_audio')
  const [itemTitle, setItemTitle]     = useState('')
  const [uploadBusy, setUploadBusy]   = useState(false)

  const [uploadStatus, setUploadStatus] = useState<ArchiveUploadStatus | null>(null)
  const [history, setHistory]           = useState<ArchiveUploadRow[]>([])
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadCredCheck = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/archive_org/credentials`)
      if (r.ok) {
        const d = await r.json()
        setCredStored(d.stored)
      }
    } catch { /* ignore */ }
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/archive_org/uploads`)
      if (r.ok) setHistory(await r.json())
    } catch { /* ignore */ }
  }, [])

  const pollStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/archive_org/status`)
      if (!r.ok) return
      const s: ArchiveUploadStatus = await r.json()
      setUploadStatus(s)
      if (!s.running && (s.status === 'done' || s.status === 'failed' || s.status === 'stopped')) {
        setUploadBusy(false)
        loadHistory()
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
      }
    } catch { /* ignore */ }
  }, [loadHistory])

  useEffect(() => {
    loadCredCheck()
    loadHistory()
    pollStatus()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [loadCredCheck, loadHistory, pollStatus])

  const handleSaveCred = async () => {
    if (!accessKey.trim() || !secretKey.trim()) return
    setCredBusy(true)
    try {
      const r = await fetch(`${BASE}/api/archive_org/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_key: accessKey.trim(), secret_key: secretKey.trim() }),
      })
      const d = await r.json()
      if (d.ok) { showToast(`Saved — ${d.label}`, 'ok'); setCredStored(true) }
      else showToast(d.error ?? 'Save failed', 'bad')
    } catch (e) { showToast(String(e), 'bad') }
    setCredBusy(false)
  }

  const handleTestCred = async () => {
    setCredBusy(true)
    try {
      const body: Record<string, string> = {}
      if (accessKey.trim()) body.access_key = accessKey.trim()
      if (secretKey.trim()) body.secret_key = secretKey.trim()
      const r = await fetch(`${BASE}/api/archive_org/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (d.ok) showToast('Credentials valid.', 'ok')
      else showToast(d.error ?? 'Invalid credentials', 'bad')
    } catch (e) { showToast(String(e), 'bad') }
    setCredBusy(false)
  }

  const handleClearCred = async () => {
    await fetch(`${BASE}/api/archive_org/credentials`, { method: 'DELETE' })
    setCredStored(false)
    setAccessKey('')
    setSecretKey('')
    showToast('Credentials cleared.', 'info')
  }

  const handleUpload = async () => {
    if (!lbNumber.trim() || !folderPath.trim()) return
    setUploadBusy(true)
    try {
      const body: Record<string, string | number> = {
        lb_number: parseInt(lbNumber),
        folder_path: folderPath.trim(),
      }
      if (identifier.trim()) body.identifier = identifier.trim()
      if (collection.trim()) body.collection = collection.trim()
      if (itemTitle.trim()) body.title = itemTitle.trim()
      if (accessKey.trim()) body.access_key = accessKey.trim()
      if (secretKey.trim()) body.secret_key = secretKey.trim()

      const r = await fetch(`${BASE}/api/archive_org/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (d.ok) {
        showToast('Upload started.', 'ok')
        pollRef.current = setInterval(pollStatus, 1500)
      } else {
        showToast(d.error ?? 'Upload failed to start', 'bad')
        setUploadBusy(false)
      }
    } catch (e) {
      showToast(String(e), 'bad')
      setUploadBusy(false)
    }
  }

  const handleStop = async () => {
    await fetch(`${BASE}/api/archive_org/stop`, { method: 'POST' })
    showToast('Stop requested.', 'info')
  }

  const inputStyle: React.CSSProperties = {
    height: 32, padding: '0 10px', borderRadius: 6,
    border: '1px solid var(--lbb-border2)', background: 'var(--lbb-bg)',
    color: 'var(--lbb-fg)', fontSize: 'var(--lbb-fs-13)', fontFamily: 'inherit',
  }
  const btnStyle: React.CSSProperties = {
    height: 32, padding: '0 14px', borderRadius: 6, border: 'none',
    background: 'var(--lbb-accent-mid)', color: '#fff',
    fontSize: 'var(--lbb-fs-13)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
  }
  const secBtnStyle: React.CSSProperties = {
    ...btnStyle, background: 'var(--lbb-surface2)',
    border: '1px solid var(--lbb-border2)', color: 'var(--lbb-fg2)',
  }

  const isRunning = uploadStatus?.running ?? false

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Credentials */}
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
          Credentials
          {credStored && (
            <span style={{ marginLeft: 10, fontSize: 'var(--lbb-fs-11)', fontWeight: 400, color: 'var(--lbb-ok-fg)' }}>
              <Icon name="check" size={11} style={{ marginRight: 3, verticalAlign: 'middle' }} />
              stored
            </span>
          )}
        </div>
        <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          Get S3 keys at{' '}
          <a href="https://archive.org/account/s3.php" target="_blank" rel="noreferrer"
            style={{ color: 'var(--lbb-accent-mid)' }}>
            archive.org/account/s3.php
          </a>{' '}
          (free account required).
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Access Key</label>
            <input
              style={{ ...inputStyle, width: 200, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)' }}
              placeholder="Access key…"
              value={accessKey}
              onChange={e => setAccessKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Secret Key</label>
            <input
              style={{ ...inputStyle, width: 200, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)' }}
              placeholder="Secret key…"
              value={secretKey}
              onChange={e => setSecretKey(e.target.value)}
              type="password"
              autoComplete="off"
            />
          </div>
          <button onClick={handleSaveCred} disabled={credBusy || !accessKey.trim() || !secretKey.trim()} style={{ ...btnStyle, opacity: credBusy ? 0.6 : 1 }}>
            Save
          </button>
          <button onClick={handleTestCred} disabled={credBusy} style={{ ...secBtnStyle, opacity: credBusy ? 0.6 : 1 }}>
            Test
          </button>
          {credStored && (
            <button onClick={handleClearCred} style={{ ...secBtnStyle, color: 'var(--lbb-err-fg)', borderColor: 'var(--lbb-err-bar)' }}>
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Upload form */}
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-fg)' }}>Upload</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>LB Number</label>
            <input style={{ ...inputStyle, width: 110 }} placeholder="e.g. 1234" type="number" min={1}
              value={lbNumber} onChange={e => setLbNumber(e.target.value)} disabled={isRunning} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 220 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Folder Path</label>
            <input style={{ ...inputStyle, width: '100%' }} placeholder="/path/to/audio/folder"
              value={folderPath} onChange={e => setFolderPath(e.target.value)} disabled={isRunning} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>IA Identifier (optional)</label>
            <input style={{ ...inputStyle, width: '100%', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)' }}
              placeholder="losslessbob-lb-01234 (auto)"
              value={identifier} onChange={e => setIdentifier(e.target.value)} disabled={isRunning} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 160 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Collection (optional)</label>
            <input style={{ ...inputStyle, width: '100%' }}
              placeholder="opensource_audio"
              value={collection} onChange={e => setCollection(e.target.value)} disabled={isRunning} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 160 }}>
            <label style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>Item Title (optional)</label>
            <input style={{ ...inputStyle, width: '100%' }}
              placeholder="Bob Dylan – LB-01234 (auto)"
              value={itemTitle} onChange={e => setItemTitle(e.target.value)} disabled={isRunning} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={isRunning ? handleStop : handleUpload}
            disabled={uploadBusy && !isRunning}
            style={{
              ...btnStyle,
              background: isRunning ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)',
              opacity: (uploadBusy && !isRunning) ? 0.6 : 1,
            }}
          >
            {isRunning
              ? 'Stop'
              : uploadBusy
              ? 'Starting…'
              : 'Upload to Archive.org'}
          </button>
          {isRunning && uploadStatus && (
            <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
              {uploadStatus.current_file ?? '…'}
              {' — '}
              {uploadStatus.files_done}/{uploadStatus.files_total} files
              {uploadStatus.bytes_total > 0 && ` (${humanBytes(uploadStatus.bytes_done)} / ${humanBytes(uploadStatus.bytes_total)})`}
            </span>
          )}
          {!isRunning && uploadStatus && uploadStatus.status !== 'idle' && (
            <span style={{
              fontSize: 'var(--lbb-fs-12)',
              color: uploadStatus.status === 'done' ? 'var(--lbb-ok-fg)'
                : uploadStatus.status === 'failed' ? 'var(--lbb-err-fg)'
                : 'var(--lbb-fg3)',
            }}>
              {uploadStatus.status === 'done' && 'Upload complete.'}
              {uploadStatus.status === 'failed' && `Failed: ${uploadStatus.error}`}
              {uploadStatus.status === 'stopped' && 'Stopped.'}
            </span>
          )}
        </div>
        {isRunning && uploadStatus && uploadStatus.bytes_total > 0 && (
          <div style={{ height: 6, background: 'var(--lbb-border2)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 3,
              background: 'var(--lbb-accent-mid)',
              width: `${pct(uploadStatus.bytes_done, uploadStatus.bytes_total)}%`,
              transition: 'width 0.5s ease',
            }} />
          </div>
        )}
      </div>

      {/* History */}
      <div>
        <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 700, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
          Upload History ({history.length})
        </div>
        {history.length === 0 ? (
          <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', textAlign: 'center', padding: '16px 0' }}>
            No uploads yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {history.map(row => (
              <div key={row.id} style={{
                background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                borderRadius: 8, padding: '10px 14px',
                display: 'grid', gridTemplateColumns: '80px 1fr 80px 70px 130px', gap: 10, alignItems: 'center',
              }}>
                <span style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 600, color: 'var(--lbb-fg)' }}>
                  LB-{String(row.lb_number).padStart(5, '0')}
                </span>
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--lbb-mono)' }}>
                  {row.identifier}
                </span>
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', textAlign: 'center' }}>
                  {row.files_uploaded ?? 0}/{row.files_total}
                </span>
                <span style={{
                  fontSize: 'var(--lbb-fs-11)', fontWeight: 600, textAlign: 'center', borderRadius: 4, padding: '2px 6px',
                  background: row.status === 'done' ? 'var(--lbb-ok-bg)'
                    : row.status === 'failed' ? 'var(--lbb-err-bg)'
                    : 'var(--lbb-surface2)',
                  color: row.status === 'done' ? 'var(--lbb-ok-fg)'
                    : row.status === 'failed' ? 'var(--lbb-err-fg)'
                    : 'var(--lbb-fg3)',
                }}>
                  {row.status}
                </span>
                <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
                  {row.started_at ? new Date(row.started_at).toLocaleString() : '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function ScreenSharing() {
  const [shares, setShares] = useState<ActiveShare[]>([])
  const [tunnelStatus, setTunnelStatus] = useState<TunnelStatus | null>(null)
  const [toast, setToast] = useState<{ msg: string; tone: 'ok' | 'bad' | 'info' } | null>(null)

  const showToast = useCallback((msg: string, tone: 'ok' | 'bad' | 'info' = 'info') => {
    setToast({ msg, tone })
  }, [])

  const loadShares = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/share/list`)
      if (r.ok) setShares(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadTunnelStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/share/tunnel/status`)
      if (r.ok) setTunnelStatus(await r.json())
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    loadShares()
    loadTunnelStatus()
  }, [loadShares, loadTunnelStatus])

  const handleRevoke = async (token: string) => {
    const r = await fetch(`${BASE}/api/share/${token}`, { method: 'DELETE' })
    if (r.ok) {
      showToast('Share stopped', 'info')
      await loadShares()
      await loadTunnelStatus()
    }
  }

  return (
    <>
      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}

      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 800 }}>
        {/* Header */}
        <div>
          <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 4 }}>
            File Sharing
          </div>
          <TunnelBanner status={tunnelStatus} />
        </div>

        {/* Create share form */}
        <CreateShareForm tunnelStatus={tunnelStatus} onCreated={loadShares} />

        {/* Active shares */}
        <div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 700, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
            Active Shares ({shares.length})
          </div>
          <ActiveSharesList shares={shares} onRevoke={handleRevoke} />
        </div>

        {/* How it works note */}
        <div style={{
          fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', lineHeight: 1.6,
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
          borderRadius: 8, padding: '12px 16px',
        }}>
          <strong style={{ color: 'var(--lbb-fg2)' }}>How it works:</strong>{' '}
          Shares are served from the local Flask backend. Without cloudflared, the link only works on your local network.
          With cloudflared installed, selecting "Share over internet" opens a Cloudflare Tunnel so your friend can download
          without needing access to your network — and your home IP stays hidden.
          Shares expire automatically and can be stopped at any time.
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: 'var(--lbb-border)', margin: '4px 0' }} />

        {/* Archive.org section */}
        <div>
          <div style={{ fontSize: 'var(--lbb-fs-16)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 4 }}>
            Archive.org Upload
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginBottom: 14 }}>
            Upload audio files for an LB entry to the Internet Archive (archive.org). Requires a free account and S3-like API keys.
          </div>
          <ArchiveOrgSection showToast={showToast} />
        </div>
      </div>
    </>
  )
}
