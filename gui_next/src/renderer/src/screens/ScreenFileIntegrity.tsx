// File Integrity (TODO-267) — per-file bit-rot inventory over the whole
// collection. Distinct from the Mounts screen's per-LB integrity monitor: that
// one checks lbdir-manifest files folder-by-folder; this one hashes EVERY file
// on a mount and re-reads it later to catch silent corruption that never
// touches mtime. Backend: backend/file_integrity.py + /api/file-integrity/*.

import React, { useCallback, useEffect, useState } from 'react'
import { Button, Pill, Card, Banner, SectionHead } from '../components'
import { Icon } from '../components/Icon'

const BASE = window.api.flaskBase

// ── Types (mirror backend/file_integrity.py + db.py shapes) ──────────────────

interface Mount {
  id: number
  label: string
  root_path: string
  online?: boolean
}

interface StatusCounts {
  files_seen: number
  files_hashed: number
  files_new: number
  files_ok: number
  files_rot: number
  files_changed: number
  files_missing: number
  files_unreadable: number
  bytes_hashed: number
}

interface ScanProgress {
  running: boolean
  mount_id: number
  mode?: 'index' | 'verify'
  label?: string
  current?: string | null
  counts?: StatusCounts
  total?: number | null
  elapsed?: number
  stopped_reason?: string | null
  status?: string
}

// Per-mount file counts by status, keyed by status name, plus a bytes total.
type SummaryEntry = Partial<Record<'ok' | 'rot' | 'changed' | 'missing' | 'unreadable', number>> & {
  bytes?: number
}

interface ProblemRow {
  mount_id: number
  rel_path: string
  lb_number: number | null
  size: number
  status: string
  xxh3: string
  last_hashed: string
  last_verified: string | null
}

interface ScanRun {
  id: number
  mount_id: number
  mode: string
  status: string
  started_at: string
  finished_at: string | null
  files_seen: number
  files_rot: number
  files_changed: number
  files_missing: number
  bytes_hashed: number
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`
}

function fmtDuration(sec?: number): string {
  if (!sec || sec < 1) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${s}s`
  return `${s}s`
}

function toneForStatus(status: string): 'ok' | 'warn' | 'bad' | 'mute' {
  switch (status) {
    case 'rot': return 'bad'
    case 'unreadable': return 'bad'
    case 'missing': return 'warn'
    case 'changed': return 'warn'
    default: return 'mute'
  }
}

// Health of a mount at a glance: rot/unreadable is the alarm, missing a warning.
function mountHealth(s?: SummaryEntry): { tone: 'ok' | 'warn' | 'bad' | 'mute'; label: string } {
  if (!s || !s.ok) return { tone: 'mute', label: 'not indexed' }
  const rot = (s.rot ?? 0) + (s.unreadable ?? 0)
  if (rot > 0) return { tone: 'bad', label: `${rot} corrupt` }
  if ((s.missing ?? 0) > 0) return { tone: 'warn', label: `${s.missing} missing` }
  if ((s.changed ?? 0) > 0) return { tone: 'warn', label: `${s.changed} changed` }
  return { tone: 'ok', label: 'clean' }
}

// ── Live scan progress bar ───────────────────────────────────────────────────

function ScanProgressBar({ p }: { p: ScanProgress }) {
  const c = p.counts
  const pct = p.total && p.total > 0 && c
    ? Math.min(100, Math.round((c.files_seen / p.total) * 100))
    : null
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Icon name="verify" size={13} />
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 600 }}>
          {p.mode === 'verify' ? 'Deep verify' : 'Indexing'} · {c?.files_seen ?? 0} files
          {pct !== null ? ` · ${pct}%` : ''}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
          {fmtBytes(c?.bytes_hashed ?? 0)} · {fmtDuration(p.elapsed)}
        </span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: 'var(--lbb-border2)', overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: pct !== null ? `${pct}%` : '40%',
          background: 'var(--lbb-accent)',
          borderRadius: 3,
          transition: 'width .4s ease',
          // Indeterminate shimmer when total is unknown (a full tree walk).
          animation: pct === null ? 'lbb-indeterminate 1.4s ease-in-out infinite' : undefined,
        }} />
      </div>
      {p.current && (
        <div style={{
          marginTop: 5, fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)',
          fontFamily: 'var(--lbb-mono)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }} title={p.current}>{p.current}</div>
      )}
    </div>
  )
}

// ── Mount card with scan controls ────────────────────────────────────────────

function MountCard({ m, summary, progress, onScan, onCancel }: {
  m: Mount
  summary?: SummaryEntry
  progress?: ScanProgress
  onScan: (mount: Mount, mode: 'index' | 'verify') => void
  onCancel: (mount: Mount) => void
}) {
  const running = progress?.running ?? false
  const health = mountHealth(summary)
  const indexed = !!summary?.ok
  return (
    <div style={{
      padding: '13px 15px', borderRadius: 9,
      border: `1px solid ${m.online ? 'var(--lbb-border)' : 'var(--lbb-bad-bar)'}`,
      background: m.online ? 'var(--lbb-surface)' : 'var(--lbb-bad-bg)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Icon name="mounts" size={16} />
        <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-13)', fontFamily: 'var(--lbb-mono)' }}>{m.label}</span>
        <Pill tone={health.tone} soft dot>{health.label}</Pill>
        {!m.online && <Pill tone="bad" soft>offline</Pill>}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
          {indexed ? `${(summary!.ok ?? 0).toLocaleString()} files · ${fmtBytes(summary!.bytes ?? 0)}` : ''}
        </span>
      </div>

      {indexed && (
        <div style={{ display: 'flex', gap: 14, marginTop: 9, flexWrap: 'wrap' }}>
          {(['rot', 'unreadable', 'missing', 'changed'] as const).map(k => {
            const n = summary?.[k] ?? 0
            if (!n) return null
            return <Pill key={k} tone={toneForStatus(k)} soft>{n.toLocaleString()} {k}</Pill>
          })}
        </div>
      )}

      {running && progress && <ScanProgressBar p={progress} />}

      <div style={{ display: 'flex', gap: 7, marginTop: 11 }}>
        {running ? (
          <Button variant="danger" icon="pause" size="sm" onClick={() => onCancel(m)}>Stop</Button>
        ) : (
          <>
            <Button variant="secondary" icon="refresh" size="sm" disabled={!m.online}
              onClick={() => onScan(m, 'index')} title="Fast: hash new/changed files only">
              Index
            </Button>
            <Button variant="primary" icon="shield" size="sm" disabled={!m.online || !indexed}
              onClick={() => onScan(m, 'verify')} title="Slow: re-read every file to detect bit rot">
              Deep Verify
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

// ── Problems table ───────────────────────────────────────────────────────────

function ProblemsTable({ rows, mounts, onRebaseline, busy }: {
  rows: ProblemRow[]
  mounts: Mount[]
  onRebaseline: (mountId: number, relPath: string) => void
  busy: string | null
}) {
  const labelFor = (id: number) => mounts.find(m => m.id === id)?.label ?? `#${id}`
  if (rows.length === 0) {
    return (
      <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>
        <Icon name="check" size={20} />
        <div style={{ marginTop: 8, fontSize: 'var(--lbb-fs-12)' }}>No integrity problems detected.</div>
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map(r => (
        <div key={`${r.mount_id}:${r.rel_path}`} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '8px 11px', borderRadius: 7,
          border: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
        }}>
          <Pill tone={toneForStatus(r.status)} soft dot>{r.status}</Pill>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{
              fontSize: 'var(--lbb-fs-11-5)', fontFamily: 'var(--lbb-mono)',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }} title={r.rel_path}>{r.rel_path}</div>
            <div style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
              {labelFor(r.mount_id)} · {r.lb_number ? `LB-${String(r.lb_number).padStart(5, '0')}` : 'unlinked'} · {fmtBytes(r.size)}
              {r.last_verified ? ` · last ok ${r.last_verified.slice(0, 10)}` : ''}
            </div>
          </div>
          {(r.status === 'rot' || r.status === 'changed') && (
            <Button variant="ghost" icon="check" size="sm"
              disabled={busy === `${r.mount_id}:${r.rel_path}`}
              onClick={() => onRebaseline(r.mount_id, r.rel_path)}
              title="Accept the current content as the new known-good baseline">
              Re-baseline
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────────

export function ScreenFileIntegrity() {
  const [mounts, setMounts] = useState<Mount[]>([])
  const [summary, setSummary] = useState<Record<string, SummaryEntry>>({})
  const [progress, setProgress] = useState<Record<string, ScanProgress>>({})
  const [problems, setProblems] = useState<ProblemRow[]>([])
  const [history, setHistory] = useState<ScanRun[]>([])
  const [rollingOn, setRollingOn] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [rebaselining, setRebaselining] = useState<string | null>(null)

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 4000) }

  const loadMounts = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/mounts`)
      const d = await r.json()
      // Endpoint returns {mounts:[…]}, not a bare array.
      setMounts(Array.isArray(d) ? d : (d.mounts ?? []))
    } catch { /* silent */ }
  }, [])

  const loadSummary = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/file-integrity/summary`)
      setSummary(await r.json())
    } catch { /* silent */ }
  }, [])

  const loadProblems = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/file-integrity/problems?limit=300`)
      setProblems((await r.json()).problems ?? [])
    } catch { /* silent */ }
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/file-integrity/history?limit=8`)
      setHistory((await r.json()).history ?? [])
    } catch { /* silent */ }
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/db/settings`)
      const d = await r.json()
      setRollingOn(['1', 'true', 'yes', 'on'].includes(String(d.file_verify_enabled).toLowerCase()))
    } catch { /* silent */ }
  }, [])

  // Poll live scan progress; when a run finishes, refresh the derived views.
  const loadProgress = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/file-integrity/status`)
      const d: Record<string, ScanProgress> = await r.json()
      setProgress(prev => {
        const wasRunning = Object.values(prev).some(p => p.running)
        const nowRunning = Object.values(d).some(p => p.running)
        if (wasRunning && !nowRunning) {
          loadSummary(); loadProblems(); loadHistory()
        }
        return d
      })
    } catch { /* silent */ }
  }, [loadSummary, loadProblems, loadHistory])

  useEffect(() => {
    loadMounts(); loadSummary(); loadProblems(); loadHistory(); loadSettings(); loadProgress()
  }, [loadMounts, loadSummary, loadProblems, loadHistory, loadSettings, loadProgress])

  useEffect(() => {
    const poll = setInterval(loadProgress, 1500)
    return () => clearInterval(poll)
  }, [loadProgress])

  async function startScan(m: Mount, mode: 'index' | 'verify') {
    try {
      const r = await fetch(`${BASE}/api/file-integrity/scan`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mount_id: m.id, mode }),
      })
      if (r.status === 409) { showMsg(`${m.label}: a scan is already running`); return }
      if (!r.ok) { showMsg((await r.json()).error ?? 'Scan failed to start'); return }
      loadProgress()
    } catch (e) { showMsg((e as Error).message) }
  }

  async function cancelScan(m: Mount) {
    try {
      await fetch(`${BASE}/api/file-integrity/scan/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mount_id: m.id }),
      })
      loadProgress()
    } catch (e) { showMsg((e as Error).message) }
  }

  async function rebaseline(mountId: number, relPath: string) {
    const key = `${mountId}:${relPath}`
    setRebaselining(key)
    try {
      const r = await fetch(`${BASE}/api/file-integrity/rebaseline`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mount_id: mountId, rel_paths: [relPath] }),
      })
      if (!r.ok) { showMsg((await r.json()).error ?? 'Re-baseline failed'); return }
      loadSummary(); loadProblems()
    } catch (e) { showMsg((e as Error).message) } finally { setRebaselining(null) }
  }

  async function toggleRolling() {
    const next = !rollingOn
    setRollingOn(next)
    try {
      await fetch(`${BASE}/api/db/settings`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_verify_enabled: next ? '1' : '0' }),
      })
    } catch (e) { showMsg((e as Error).message); setRollingOn(!next) }
  }

  // Collection-wide roll-up across mounts.
  const totals = Object.values(summary).reduce(
    (acc: { files: number; bytes: number; rot: number; missing: number }, s) => {
      acc.files += s.ok ?? 0
      acc.bytes += s.bytes ?? 0
      acc.rot += (s.rot ?? 0) + (s.unreadable ?? 0)
      acc.missing += s.missing ?? 0
      return acc
    },
    { files: 0, bytes: 0, rot: 0, missing: 0 },
  )

  return (
    <div style={{ padding: '20px 24px', maxWidth: 1040, margin: '0 auto' }}>
      <style>{`@keyframes lbb-indeterminate{0%{transform:translateX(-60%)}100%{transform:translateX(300%)}}`}</style>

      <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 4 }}>
        <Icon name="shield" size={20} />
        <h2 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700 }}>File Integrity</h2>
      </div>
      <p style={{ margin: '0 0 18px', fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg3)', maxWidth: 720 }}>
        A durable xxh3 + SHA-256 hash of every file on every mount. <strong>Index</strong> is fast and
        keeps the inventory current; <strong>Deep Verify</strong> re-reads each file to catch bit rot —
        silent corruption that leaves size and mtime untouched, which nothing else here can see.
      </p>

      {msg && <Banner tone="warn" style={{ marginBottom: 14 }}>{msg}</Banner>}

      {(totals.rot > 0 || totals.missing > 0) && (
        <Banner tone={totals.rot > 0 ? 'bad' : 'warn'} icon="alert" style={{ marginBottom: 14 }}
          title={totals.rot > 0 ? `${totals.rot} corrupt file(s) detected` : `${totals.missing} file(s) missing`}>
          {totals.rot > 0
            ? 'Bit rot or unreadable files found. Re-source them, then re-baseline below.'
            : 'Inventoried files are no longer on disk. Check the drive, then re-index.'}
        </Banner>
      )}

      {/* Collection roll-up */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <Card pad={13}><div style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, fontFamily: 'var(--lbb-mono)' }}>{totals.files.toLocaleString()}</div><div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>files hashed</div></Card>
        <Card pad={13}><div style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, fontFamily: 'var(--lbb-mono)' }}>{fmtBytes(totals.bytes)}</div><div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>indexed</div></Card>
        <Card pad={13}><div style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: totals.rot ? 'var(--lbb-bad-bar)' : undefined }}>{totals.rot.toLocaleString()}</div><div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>corrupt</div></Card>
        <Card pad={13}><div style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, fontFamily: 'var(--lbb-mono)', color: totals.missing ? 'var(--lbb-warn-bar)' : undefined }}>{totals.missing.toLocaleString()}</div><div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>missing</div></Card>
      </div>

      {/* Mounts */}
      <SectionHead title="Mounts" subtitle="Scan each drive independently — they run in parallel." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 22 }}>
        {mounts.length === 0 && <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>No mounts configured. Add drives on the Mounts screen.</div>}
        {mounts.map(m => (
          <MountCard key={m.id} m={m} summary={summary[String(m.id)]} progress={progress[String(m.id)]}
            onScan={startScan} onCancel={cancelScan} />
        ))}
      </div>

      {/* Rolling verify toggle */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 22,
        padding: '12px 15px', borderRadius: 9, border: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
      }}>
        <Icon name="refresh" size={16} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 600 }}>Nightly rolling deep verify</div>
          <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            Verifies the most-overdue slice of each mount every night — the whole collection covered roughly monthly, without one long blocking run.
          </div>
        </div>
        <Button variant={rollingOn ? 'primary' : 'secondary'} icon={rollingOn ? 'check' : 'play'} size="sm" onClick={toggleRolling}>
          {rollingOn ? 'Enabled' : 'Enable'}
        </Button>
      </div>

      {/* Problems */}
      <SectionHead title={`Problems${problems.length ? ` · ${problems.length}` : ''}`}
        subtitle="Corrupt and changed files, worst first. Re-baseline accepts current content as the new good copy." />
      <div style={{ marginBottom: 22 }}>
        <ProblemsTable rows={problems} mounts={mounts} onRebaseline={rebaseline} busy={rebaselining} />
      </div>

      {/* Recent runs */}
      {history.length > 0 && (
        <>
          <SectionHead title="Recent scans" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {history.map(h => {
              const mount = mounts.find(m => m.id === h.mount_id)?.label ?? `#${h.mount_id}`
              const flagged = h.files_rot + h.files_missing
              return (
                <div key={h.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '6px 11px',
                  borderRadius: 6, fontSize: 'var(--lbb-fs-11)', fontFamily: 'var(--lbb-mono)',
                  color: 'var(--lbb-fg3)',
                }}>
                  <Pill tone={h.status === 'done' ? 'ok' : h.status === 'error' ? 'bad' : 'mute'} soft>{h.mode}</Pill>
                  <span style={{ color: 'var(--lbb-fg2)' }}>{mount}</span>
                  <span>{h.files_seen.toLocaleString()} files · {fmtBytes(h.bytes_hashed)}</span>
                  {flagged > 0 && <Pill tone="bad" soft>{flagged} flagged</Pill>}
                  <span style={{ marginLeft: 'auto' }}>{h.started_at.slice(0, 16)}</span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
