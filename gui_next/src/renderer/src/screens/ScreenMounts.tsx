import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Pill, Icon, Banner, Input, IconButton } from '../components'

const BASE = window.api.flaskBase

// ── Collection Routing types ──────────────────────────────────────────────────

interface CollectionMount {
  id: number
  label: string
  root_path: string
  notes: string | null
  online?: boolean
  free?: string
  total?: string
  used_pct?: number | null
}

interface CollectionRoute {
  year: number
  mount_id: number
  sub_path: string
  mount_label?: string
  root_path?: string
}

// ── Integrity Monitor types (TODO-111) ─────────────────────────────────────────

interface IntegritySummaryEntry {
  pass: number
  content_issue: number
  tag_issue: number
  missing_files: number
  no_lbdir: number
  error: number
}

interface IntegrityStatusRow {
  lb_number: number
  mount_id: number | null
  disk_path: string
  status: string
  content_issues: number
  tag_issues: number
  missing_count: number
  total_files: number
  checked_at: string
}

interface IntegrityEvent {
  id: number
  lb_number: number | null
  disk_path: string | null
  event_type: string
  detail: string | null
  occurred_at: string
  acknowledged: number
  mount_id: number | null
}

interface ScanStatus {
  running: boolean
  mount_id: number | null
  folders_done: number
  folders_total: number
  current_folder: string | null
  result: Record<string, number> | null
}

const SCAN_INTERVAL_OPTIONS: { value: string; label: string }[] = [
  { value: '0', label: 'Off' },
  { value: '24', label: 'Daily' },
  { value: '168', label: 'Weekly' },
  { value: '720', label: 'Monthly' },
]

const INTEGRITY_STATUS_LABELS: Record<string, string> = {
  content_issue: 'Corrupted audio',
  tag_issue: 'Tags changed',
  missing_files: 'Missing files',
  no_lbdir: 'No lbdir manifest',
  error: 'Scan error',
}

const INTEGRITY_EVENT_LABELS: Record<string, string> = {
  content_changed: 'Audio content changed',
  tags_changed: 'Tags/metadata changed',
  files_missing: 'Files missing',
  restored: 'Integrity restored',
  missing: 'Folder unreachable',
}

function toneForIntegrityStatus(status: string): 'ok' | 'warn' | 'bad' | 'info' | 'mute' {
  switch (status) {
    case 'content_issue': return 'bad'
    case 'error': return 'bad'
    case 'missing_files': return 'warn'
    case 'tag_issue': return 'warn'
    default: return 'mute'
  }
}

function toneForIntegrityEvent(eventType: string): 'ok' | 'warn' | 'bad' | 'info' | 'mute' {
  switch (eventType) {
    case 'content_changed': return 'bad'
    case 'files_missing': return 'warn'
    case 'tags_changed': return 'warn'
    case 'restored': return 'ok'
    default: return 'mute'
  }
}

const YEAR_MIN = 1958
const YEAR_MAX = 2026

// Normalise a stored root_path for display: convert any backslashes (legacy Windows
// entries stored before normalise_path was fixed) and strip trailing slashes so that
// joining with '/' + sub_path never produces double slashes like "c:\/1958/".
function joinRoute(rootPath: string, subPath?: string): string {
  const root = rootPath.replace(/\\/g, '/').replace(/\/+$/, '')
  return subPath ? `${root}/${subPath}/` : `${root}/`
}

// ── Collection Routing sub-components ────────────────────────────────────────

function OnlineDot({ online }: { online?: boolean }) {
  return (
    <span
      title={online ? 'Online · reachable' : 'Offline · not mounted'}
      style={{
        width: 9, height: 9, flex: '0 0 9px', borderRadius: '50%',
        background: online ? 'var(--lbb-ok-bar)' : 'var(--lbb-bad-bar)',
        boxShadow: online ? '0 0 0 3px var(--lbb-ok-bg)' : '0 0 0 3px var(--lbb-bad-bg)',
      }}
    />
  )
}

const selectStyle: React.CSSProperties = {
  appearance: 'none', WebkitAppearance: 'none',
  height: 24, padding: '0 24px 0 10px', borderRadius: 6,
  border: '1px solid var(--lbb-border2)', background: 'var(--lbb-surface)',
  color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)', fontSize: 11.5,
  fontWeight: 600, cursor: 'pointer', outline: 'none',
}

function MountForm({
  initial, onSave, onCancel,
}: { initial?: CollectionMount; onSave: (d: Partial<CollectionMount>) => void; onCancel: () => void }) {
  const [label, setLabel] = useState(initial?.label ?? '')
  const [root, setRoot] = useState(initial?.root_path ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const valid = label.trim() && root.trim()
  return (
    <div style={{ padding: '14px 16px', borderRadius: 9, border: '1px solid var(--lbb-accent-mid)', background: 'var(--lbb-accent-soft)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr auto', gap: 10, alignItems: 'end' }}>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 4 }}>Label</div>
          <Input placeholder="DYLAN5" value={label} onChange={e => setLabel(e.target.value.toUpperCase())} style={{ width: '100%', background: 'var(--lbb-surface)' }} />
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 4 }}>Root path</div>
          <Input icon="folder" placeholder="/mnt/dylan5" value={root} onChange={e => setRoot(e.target.value)} style={{ width: '100%', background: 'var(--lbb-surface)' }} />
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" icon="check" disabled={!valid} onClick={() => onSave({ label: label.trim(), root_path: root.trim(), notes: notes.trim() || null })}>
            {initial ? 'Save' : 'Add mount'}
          </Button>
        </div>
      </div>
      <div style={{ marginTop: 10 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 4 }}>
          Notes <span style={{ textTransform: 'none', fontWeight: 500 }}>· optional</span>
        </div>
        <Input placeholder="What lives on this drive…" value={notes} onChange={e => setNotes(e.target.value)} style={{ width: '100%', background: 'var(--lbb-surface)' }} />
      </div>
    </div>
  )
}

function IntegrityBadge({ summary }: { summary?: IntegritySummaryEntry }) {
  if (!summary) return null
  if (summary.content_issue > 0) {
    return <Pill tone="bad" soft dot>{summary.content_issue} corrupt</Pill>
  }
  if (summary.missing_files > 0) {
    return <Pill tone="warn" soft dot>{summary.missing_files} missing</Pill>
  }
  if (summary.tag_issue > 0) {
    return <Pill tone="warn" soft dot>{summary.tag_issue} tag-only</Pill>
  }
  if (summary.pass > 0) {
    return <Pill tone="ok" soft dot>verified</Pill>
  }
  return null
}

function MountCard({ m, routeCount, summary, scanning, onEdit, onDelete, onScan }: {
  m: CollectionMount; routeCount: number; summary?: IntegritySummaryEntry; scanning?: boolean
  onEdit: (m: CollectionMount) => void; onDelete: (m: CollectionMount) => void
  onScan: (m: CollectionMount) => void
}) {
  const { t } = useTranslation()
  const [hover, setHover] = useState(false)
  const hasUsage = m.online && !!m.free && !!m.total && m.free !== '—'
  return (
    <div
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ position: 'relative', padding: '12px 14px', borderRadius: 9,
        border: `1px solid ${m.online ? 'var(--lbb-border)' : 'var(--lbb-bad-bar)'}`,
        background: m.online ? 'var(--lbb-surface)' : 'var(--lbb-bad-bg)' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
        <OnlineDot online={m.online} />
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>{m.label}</span>
        <div style={{ flex: 1 }} />
        {!m.online && <Pill tone="bad" soft>offline</Pill>}
        <IntegrityBadge summary={summary} />
        <div style={{ display: 'flex', gap: 2, opacity: hover ? 1 : 0, transition: 'opacity 120ms' }}>
          <IconButton icon="verify" size={24} title="Scan integrity" active={scanning} onClick={() => onScan(m)} />
          <IconButton icon="rename" size={24} title="Edit mount" onClick={() => onEdit(m)} />
          <IconButton icon="trash" size={24} title="Delete mount" onClick={() => onDelete(m)} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--lbb-mono)', fontSize: 11.5, color: 'var(--lbb-fg2)', marginBottom: 6 }}>
        <Icon name="folder" size={12} style={{ color: 'var(--lbb-fg3)', flex: '0 0 auto' }} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.root_path}</span>
      </div>
      {hasUsage && (
        <div style={{ marginBottom: 6 }}
          title={t('mounts.usageTooltip', { free: m.free, total: m.total, pct: m.used_pct })}
        >
          <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
            {t('mounts.freeOfTotal', { free: m.free, total: m.total })}
          </span>
          {m.used_pct != null && (
            <div style={{ height: 4, borderRadius: 2, background: 'var(--lbb-border)', overflow: 'hidden', marginTop: 4 }}>
              <div style={{
                height: '100%', width: `${m.used_pct}%`,
                background: m.used_pct >= 90 ? 'var(--lbb-bad-bar)'
                  : m.used_pct >= 75 ? 'var(--lbb-warn-bar)' : 'var(--lbb-accent-mid)',
              }} />
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.notes || '—'}</span>
        <span style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums', flex: '0 0 auto' }}>
          {routeCount ? `${routeCount} ${routeCount === 1 ? 'year' : 'years'}` : 'no years'}
        </span>
      </div>
    </div>
  )
}

function BulkFill({ mounts, onApply }: {
  mounts: CollectionMount[]
  onApply: (args: { from: number; to: number; mount_id: number; mode: string; custom: string }) => void
}) {
  const [from, setFrom] = useState('1958')
  const [to, setTo] = useState('1969')
  const [mountId, setMountId] = useState<number>(mounts[0]?.id ?? 0)
  const [mode, setMode] = useState<'per-year' | 'flat' | 'custom'>('per-year')
  const [custom, setCustom] = useState('')
  const mount = mounts.find(m => m.id === mountId)
  const exampleSub = mode === 'per-year' ? '{year}' : mode === 'flat' ? '' : (custom || '…')
  const exampleDest = joinRoute(mount?.root_path ?? '', exampleSub || undefined)
  const span = Math.max(0, (parseInt(to) || 0) - (parseInt(from) || 0) + 1)

  return (
    <div style={{ padding: '13px 15px', borderRadius: 9, background: 'var(--lbb-surface2)', border: '1px dashed var(--lbb-border2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
        <Icon name="filter" size={13} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{ fontSize: 12, color: 'var(--lbb-fg2)', fontWeight: 600 }}>Route years</span>
        <Input value={from} onChange={e => setFrom(e.target.value)} size="sm" style={{ width: 60 }} />
        <span style={{ color: 'var(--lbb-fg3)' }}>–</span>
        <Input value={to} onChange={e => setTo(e.target.value)} size="sm" style={{ width: 60 }} />
        <span style={{ fontSize: 12, color: 'var(--lbb-fg2)', marginLeft: 4 }}>to</span>
        <div style={{ position: 'relative', display: 'inline-flex' }}>
          <select value={String(mountId)} onChange={e => setMountId(+e.target.value)} style={selectStyle}>
            {mounts.map(m => (
              <option key={m.id} value={String(m.id)}>{m.label}{m.online ? '' : '  (offline)'}</option>
            ))}
          </select>
          <Icon name="chevDown" size={12} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--lbb-fg3)' }} />
        </div>
        <div style={{ flex: 1 }} />
        <Button variant="primary" icon="check" disabled={!mount || !from || !to}
          onClick={() => onApply({ from: parseInt(from), to: parseInt(to), mount_id: mountId, mode, custom: custom.trim() })}>
          Apply to {span} {span === 1 ? 'year' : 'years'}
        </Button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 11, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>Sub-path</span>
        <div style={{ display: 'flex', gap: 2, padding: 2, background: 'var(--lbb-surface)', borderRadius: 7, border: '1px solid var(--lbb-border)' }}>
          {(['per-year', 'flat', 'custom'] as const).map(k => (
            <button key={k} onClick={() => setMode(k)} style={{
              padding: '4px 11px', borderRadius: 5, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11.5,
              fontWeight: mode === k ? 600 : 500, border: '1px solid transparent',
              background: mode === k ? 'var(--lbb-accent-soft)' : 'transparent',
              color: mode === k ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
              borderColor: mode === k ? 'var(--lbb-accent-mid)' : 'transparent',
            }}>
              {k === 'per-year' ? 'Per-year' : k === 'flat' ? 'Flat' : 'Custom'}
            </button>
          ))}
        </div>
        {mode === 'custom' && <Input placeholder="1960s/{year}" value={custom} onChange={e => setCustom(e.target.value)} size="sm" style={{ width: 160 }} />}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          e.g. <span style={{ color: 'var(--lbb-fg2)' }}>{exampleDest}</span><span style={{ opacity: 0.6 }}>folder/</span>
        </span>
      </div>
    </div>
  )
}

function Coverage({ routes, mounts }: { routes: CollectionRoute[]; mounts: CollectionMount[] }) {
  const mountColors = [
    'var(--lbb-ok-bar)', 'var(--lbb-info-bar)', 'var(--lbb-accent-mid)',
    'var(--lbb-warn-bar)', 'var(--lbb-fg3)',
  ]
  const mountColorMap = new Map(mounts.map((m, i) => [m.id, mountColors[i % mountColors.length]]))
  const routeMap = new Map(routes.map(r => [r.year, r.mount_id]))
  const years: number[] = []
  for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y)
  const gaps = years.filter(y => !routeMap.has(y))
  const routed = years.length - gaps.length

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>Coverage</span>
        <span style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {routed} of {years.length} years routed
        </span>
        {gaps.length > 0
          ? <Pill tone="warn" soft dot>{gaps.length} unrouted</Pill>
          : <Pill tone="ok" soft dot>complete</Pill>}
        <div style={{ flex: 1 }} />
        {gaps.length > 0 && <span style={{ fontSize: 11, color: 'var(--lbb-warn-fg)', fontFamily: 'var(--lbb-mono)' }}>gap: {gaps.join(', ')}</span>}
      </div>
      <div style={{ display: 'flex', gap: 1.5, height: 26, borderRadius: 6, overflow: 'hidden', border: '1px solid var(--lbb-border)' }}>
        {years.map(y => {
          const mid = routeMap.get(y)
          const gap = mid === undefined
          return (
            <div key={y}
              title={gap ? `${y} · no route` : `${y} · ${mounts.find(m => m.id === mid)?.label}`}
              style={{ flex: 1, background: gap ? 'var(--lbb-bad-bg)' : (mountColorMap.get(mid!) ?? 'var(--lbb-fg3)'),
                borderTop: gap ? '2px solid var(--lbb-bad-bar)' : 'none', boxSizing: 'border-box' }}
            />
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
        <span>{YEAR_MIN}</span><span>{Math.round((YEAR_MIN + YEAR_MAX) / 2)}</span><span>{YEAR_MAX}</span>
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 9, flexWrap: 'wrap' }}>
        {mounts.filter(m => routes.some(r => r.mount_id === m.id)).map((m, i) => (
          <span key={m.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--lbb-fg2)' }}>
            <span style={{ width: 11, height: 11, borderRadius: 3, background: mountColors[i % mountColors.length] }} />{m.label}
          </span>
        ))}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--lbb-fg2)' }}>
          <span style={{ width: 11, height: 11, borderRadius: 3, background: 'var(--lbb-bad-bg)', border: '2px solid var(--lbb-bad-bar)', boxSizing: 'border-box' }} />
          unrouted
        </span>
      </div>
    </div>
  )
}

function PreviewTester({ routes, mounts }: { routes: CollectionRoute[]; mounts: CollectionMount[] }) {
  const [year, setYear] = useState('1966')
  const y = parseInt(year)
  const r = routes.find(x => x.year === y)
  const m = r ? mounts.find(x => x.id === r.mount_id) : undefined

  let out: { tone: 'ok' | 'bad' | 'warn' | 'mute'; dest?: string; label?: string; online?: boolean; text?: string }
  if (!y) out = { tone: 'mute', text: 'Enter a year to test the route' }
  else if (!r || !m) out = { tone: 'bad', text: `No route configured for ${year}` }
  else {
    const dest = joinRoute(m.root_path, r.sub_path || undefined)
    out = { tone: m.online ? 'ok' : 'warn', dest, label: m.label, online: m.online }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px', borderRadius: 8, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)' }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>Test a year</span>
      <Input value={year} onChange={e => setYear(e.target.value)} size="sm" style={{ width: 76 }} />
      <Icon name="chevRight" size={14} style={{ color: 'var(--lbb-fg3)' }} />
      {out.dest ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 12.5, color: 'var(--lbb-fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{out.dest}</span>
          <Pill tone={out.online ? 'ok' : 'warn'} soft dot style={{ flex: '0 0 auto' }}>{out.label} · {out.online ? 'online' : 'offline'}</Pill>
        </div>
      ) : (
        <Pill tone={out.tone} soft dot={out.tone !== 'mute'}>{out.text}</Pill>
      )}
    </div>
  )
}

// ── CollectionRoutingCard ─────────────────────────────────────────────────────

function CollectionRoutingCard() {
  const [mounts, setMounts] = useState<CollectionMount[]>([])
  const [routes, setRoutes] = useState<CollectionRoute[]>([])
  const [fileMode, setFileMode] = useState<'move' | 'copy'>('move')
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [toast, setToast] = useState<string | null>(null)

  // Integrity monitor (TODO-111)
  const [integritySummary, setIntegritySummary] = useState<Record<string, IntegritySummaryEntry>>({})
  const [integrityStatus, setIntegrityStatus] = useState<IntegrityStatusRow[]>([])
  const [integrityEvents, setIntegrityEvents] = useState<IntegrityEvent[]>([])
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null)
  const [scanInterval, setScanInterval] = useState('0')

  function showMsg(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  const loadMounts = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/mounts`)
      const d = await r.json()
      setMounts(d.mounts ?? [])
    } catch { /* silent */ }
  }, [])

  const loadRoutes = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/routes`)
      const d = await r.json()
      setRoutes(d.routes ?? [])
    } catch { /* silent */ }
  }, [])

  const loadFileMode = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/db/settings`)
      const d = await r.json()
      if (d.pipeline_file_mode) setFileMode(d.pipeline_file_mode)
      if (d.integrity_scan_interval_hours) setScanInterval(String(d.integrity_scan_interval_hours))
    } catch { /* silent */ }
  }, [])

  const loadIntegritySummary = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/integrity/summary`)
      const d = await r.json()
      setIntegritySummary(d ?? {})
    } catch { /* silent */ }
  }, [])

  const loadIntegrityStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/integrity/status`)
      const d = await r.json()
      setIntegrityStatus(((d.status ?? []) as IntegrityStatusRow[]).filter(row => row.status !== 'pass'))
    } catch { /* silent */ }
  }, [])

  const loadIntegrityEvents = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/integrity/events`)
      const d = await r.json()
      setIntegrityEvents(Array.isArray(d) ? d : [])
    } catch { /* silent */ }
  }, [])

  const loadScanStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/collection/integrity/scan/status`)
      const d = await r.json()
      setScanStatus(prev => {
        if (prev?.running && !d.running) {
          loadIntegritySummary()
          loadIntegrityStatus()
          loadIntegrityEvents()
        }
        return d
      })
    } catch { /* silent */ }
  }, [loadIntegritySummary, loadIntegrityStatus, loadIntegrityEvents])

  useEffect(() => {
    loadMounts()
    loadRoutes()
    loadFileMode()
    loadIntegritySummary()
    loadIntegrityStatus()
    loadIntegrityEvents()
    loadScanStatus()
  }, [loadMounts, loadRoutes, loadFileMode, loadIntegritySummary, loadIntegrityStatus, loadIntegrityEvents, loadScanStatus])

  useEffect(() => {
    const poll = setInterval(loadScanStatus, 1500)
    return () => clearInterval(poll)
  }, [loadScanStatus])

  async function saveMount(data: Partial<CollectionMount>) {
    try {
      if (editId !== null) {
        await fetch(`${BASE}/api/collection/mounts/${editId}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        setEditId(null)
      } else {
        await fetch(`${BASE}/api/collection/mounts`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        setAdding(false)
      }
      loadMounts()
    } catch (e) { showMsg((e as Error).message) }
  }

  async function deleteMount(m: CollectionMount) {
    const r = await fetch(`${BASE}/api/collection/mounts/${m.id}`, { method: 'DELETE' })
    if (r.status === 409) { showMsg(`${m.label} has routes — delete routes first`); return }
    loadMounts()
  }

  async function applyBulk({ from, to, mount_id, mode, custom }: {
    from: number; to: number; mount_id: number; mode: string; custom: string
  }) {
    if (!from || !to || from > to) return
    if (mode === 'per-year') {
      for (let y = from; y <= to; y++) {
        await fetch(`${BASE}/api/collection/routes/bulk`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ year_from: y, year_to: y, mount_id, sub_path: String(y) }),
        })
      }
    } else {
      const sub_path = mode === 'flat' ? '' : custom
      await fetch(`${BASE}/api/collection/routes/bulk`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year_from: from, year_to: to, mount_id, sub_path }),
      })
    }
    setExpanded(s => new Set([...s, mount_id]))
    loadRoutes()
  }

  async function deleteRoute(year: number) {
    await fetch(`${BASE}/api/collection/routes/${year}`, { method: 'DELETE' })
    loadRoutes()
  }

  async function saveFileMode(m: 'move' | 'copy') {
    setFileMode(m)
    await fetch(`${BASE}/api/db/settings`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_file_mode: m }),
    })
  }

  async function startScan(mountId?: number) {
    try {
      const r = await fetch(`${BASE}/api/collection/integrity/scan`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mountId !== undefined ? { mount_id: mountId } : {}),
      })
      const d = await r.json()
      if (!d.ok) showMsg(d.error || 'A scan is already running')
      else loadScanStatus()
    } catch (e) { showMsg((e as Error).message) }
  }

  async function cancelScan() {
    await fetch(`${BASE}/api/collection/integrity/scan/cancel`, { method: 'POST' })
  }

  async function saveScanInterval(hours: string) {
    setScanInterval(hours)
    await fetch(`${BASE}/api/db/settings`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ integrity_scan_interval_hours: hours }),
    })
  }

  async function ackEvents(ids: number[]) {
    if (!ids.length) return
    await fetch(`${BASE}/api/integrity/ack`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    })
    loadIntegrityEvents()
  }

  const routeCountFor = (id: number) => routes.filter(r => r.mount_id === id).length
  const toggleExpand = (id: number) => setExpanded(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const offlineCount = mounts.filter(m => !m.online).length

  return (
    <div style={{ background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)', borderRadius: 10, padding: 18 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 700, letterSpacing: 0.08, textTransform: 'uppercase', color: 'var(--lbb-fg)' }}>
          Mounts &amp; Routes
        </span>
        <Pill tone="info" soft dot>{mounts.length} mounts · {routes.length} routed years</Pill>
        {toast && <span style={{ fontSize: 11.5, color: 'var(--lbb-warn-fg)', marginLeft: 'auto' }}>{toast}</span>}
      </div>

      <Banner tone="info" icon="info">
        When a folder reaches the <strong>File</strong> step, its show year picks a storage drive and sub-folder
        from the table below, then the folder is moved (or copied) there and registered in My Collection.
        Set up your drives once — routing then runs automatically for every filing.
      </Banner>

      {/* 1 · Storage Mounts */}
      <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
          <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 5, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>1</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>Storage mounts</div>
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 2, lineHeight: 1.4 }}>Named drives or NAS shares. Online status updates live.</div>
          </div>
          {!adding && editId === null && (
            <Button variant="secondary" size="sm" icon="plus" onClick={() => { setAdding(true); setEditId(null) }}>Add mount</Button>
          )}
        </div>
        {offlineCount > 0 && (
          <div style={{ marginBottom: 10 }}>
            <Banner tone="warn" icon="alert">
              <strong>{offlineCount} mount{offlineCount === 1 ? ' is' : 's are'} offline.</strong> Folders routed to an offline drive can't be filed until it's reconnected.
            </Banner>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
          {mounts.map(m => editId === m.id ? (
            <div key={m.id} style={{ gridColumn: 'span 3' }}>
              <MountForm initial={m} onSave={saveMount} onCancel={() => setEditId(null)} />
            </div>
          ) : (
            <MountCard key={m.id} m={m} routeCount={routeCountFor(m.id)}
              summary={integritySummary[String(m.id)]}
              scanning={!!scanStatus?.running && scanStatus.mount_id === m.id}
              onEdit={mm => { setEditId(mm.id); setAdding(false) }}
              onDelete={deleteMount}
              onScan={mm => startScan(mm.id)} />
          ))}
        </div>
        {adding && (
          <div style={{ marginTop: 10 }}>
            <MountForm onSave={saveMount} onCancel={() => setAdding(false)} />
          </div>
        )}
      </div>

      {/* 2 · Year Routing */}
      <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
          <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 5, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>2</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>Year routing</div>
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 2, lineHeight: 1.4 }}>Each concert year maps to one mount + sub-path. Use the range filler for whole decades.</div>
          </div>
          <button
            onClick={() => {
              const allIds = mounts.map(m => m.id)
              const allOpen = allIds.every(id => !routeCountFor(id) || expanded.has(id))
              setExpanded(allOpen ? new Set() : new Set(allIds))
            }}
            style={{ background: 'none', border: 'none', color: 'var(--lbb-accent-mid)', font: 'inherit', fontSize: 11.5, fontWeight: 600, cursor: 'pointer' }}
          >
            {mounts.every(m => !routeCountFor(m.id) || expanded.has(m.id)) ? 'Collapse all' : 'Expand all years'}
          </button>
        </div>
        {mounts.length === 0 ? (
          <div style={{ padding: '14px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 12 }}>
            Add a storage mount above to start configuring routes.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <BulkFill mounts={mounts} onApply={applyBulk} />
            {/* Routes table */}
            {routes.length > 0 && (
              <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
                {mounts.filter(m => routeCountFor(m.id) > 0).map(m => {
                  const rows = routes.filter(r => r.mount_id === m.id).sort((a, b) => a.year - b.year)
                  if (rows.length === 0) return null
                  const open = expanded.has(m.id)
                  const span = `${rows[0].year}–${rows[rows.length - 1].year}`
                  return (
                    <React.Fragment key={m.id}>
                      <div onClick={() => toggleExpand(m.id)} style={{
                        display: 'flex', alignItems: 'center', gap: 9, padding: '7px 12px',
                        background: 'var(--lbb-surface2)', cursor: 'pointer',
                        borderBottom: '1px solid var(--lbb-border)', borderTop: '1px solid var(--lbb-border)',
                      }}>
                        <div style={{ width: 3, height: 16, borderRadius: 2, background: m.online ? 'var(--lbb-ok-bar)' : 'var(--lbb-bad-bar)', flex: '0 0 3px' }} />
                        <Icon name={open ? 'chevDown' : 'chevRight'} size={12} style={{ color: 'var(--lbb-fg3)' }} />
                        <OnlineDot online={m.online} />
                        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 12, fontWeight: 700, color: 'var(--lbb-fg)' }}>{m.label}</span>
                        <span style={{ fontSize: 11, color: 'var(--lbb-fg3)' }}>· {span}</span>
                        <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>· {rows.length} {rows.length === 1 ? 'year' : 'years'}</span>
                        <span style={{ marginLeft: 'auto', fontFamily: 'var(--lbb-mono)', fontSize: 11, color: 'var(--lbb-fg3)' }}>{joinRoute(m.root_path)}</span>
                      </div>
                      {open && rows.map(r => (
                        <div key={r.year} style={{ display: 'grid', gridTemplateColumns: '80px 140px 140px 1fr 40px', alignItems: 'center', gap: 0, padding: '5px 12px', borderBottom: '1px solid var(--lbb-border)', fontSize: 12 }}>
                          <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600 }}>{r.year}</span>
                          <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{m.label}</span>
                          <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)' }}>{r.sub_path || '(flat)'}</span>
                          <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {joinRoute(m.root_path, r.sub_path || undefined)}
                          </span>
                          <IconButton icon="x" size={22} title={`Remove ${r.year}`} onClick={() => deleteRoute(r.year)} />
                        </div>
                      ))}
                    </React.Fragment>
                  )
                })}
              </div>
            )}
            <Coverage routes={routes} mounts={mounts} />
            <PreviewTester routes={routes} mounts={mounts} />
          </div>
        )}
      </div>

      {/* 3 · Filing Mode */}
      <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
          <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 5, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>3</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>Filing mode</div>
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 2 }}>What happens to the staging folder once it's written to the collection mount.</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {(['move', 'copy'] as const).map(k => {
            const on = fileMode === k
            const desc = k === 'move'
              ? 'Source folder is relocated — nothing left behind. Recommended.'
              : 'Source is duplicated and left in place. Clean up staging yourself.'
            return (
              <label key={k} style={{ flex: 1, display: 'flex', gap: 11, padding: '12px 14px', borderRadius: 9, cursor: 'pointer',
                background: on ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                border: `1px solid ${on ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}` }}>
                <input type="radio" name="filemode" checked={on} onChange={() => saveFileMode(k)} style={{ marginTop: 2 }} />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <Icon name={k === 'move' ? 'drop' : 'copy'} size={14} style={{ color: on ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)' }} />
                    <span style={{ fontSize: 13, fontWeight: 700, color: on ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)' }}>
                      {k === 'move' ? 'Move' : 'Copy'}
                    </span>
                    {k === 'move' && <Pill tone="mute" soft>default</Pill>}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', marginTop: 4, lineHeight: 1.45 }}>{desc}</div>
                </div>
              </label>
            )
          })}
        </div>
        {fileMode === 'copy' && (
          <div style={{ marginTop: 10 }}>
            <Banner tone="warn" icon="alert" title="Copy mode leaves originals in place">
              Filed folders are duplicated to the collection mount; the staging copy is <strong>not removed</strong>. Reclaim space by clearing staging manually once you've confirmed the copy.
            </Banner>
          </div>
        )}
      </div>

      {/* 4 · Integrity Monitor */}
      <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
          <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 5, background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>4</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--lbb-fg)' }}>Integrity monitor</div>
            <div style={{ fontSize: 11.5, color: 'var(--lbb-fg3)', marginTop: 2, lineHeight: 1.4 }}>
              Verifies collection folders against their lbdir manifests — catches bitrot/corruption, missing or moved files, and tag-only edits.
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--lbb-fg3)' }}>Auto-scan</span>
            <div style={{ position: 'relative', display: 'inline-flex' }}>
              <select value={scanInterval} onChange={e => saveScanInterval(e.target.value)} style={selectStyle}>
                {SCAN_INTERVAL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <Icon name="chevDown" size={12} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--lbb-fg3)' }} />
            </div>
            {scanStatus?.running ? (
              <Button variant="danger" size="sm" icon="x" onClick={cancelScan}>Cancel scan</Button>
            ) : (
              <Button variant="secondary" size="sm" icon="verify" onClick={() => startScan()}>Scan now</Button>
            )}
          </div>
        </div>

        {scanStatus?.running && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--lbb-fg3)', marginBottom: 4 }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--lbb-mono)' }}>
                Scanning{scanStatus.current_folder ? `: ${scanStatus.current_folder}` : '…'}
              </span>
              <span style={{ fontVariantNumeric: 'tabular-nums', flex: '0 0 auto', marginLeft: 8 }}>{scanStatus.folders_done} / {scanStatus.folders_total}</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: 'var(--lbb-surface2)', overflow: 'hidden', border: '1px solid var(--lbb-border)' }}>
              <div style={{
                height: '100%',
                width: `${scanStatus.folders_total ? Math.round((scanStatus.folders_done / scanStatus.folders_total) * 100) : 0}%`,
                background: 'var(--lbb-accent-mid)', transition: 'width 200ms ease',
              }} />
            </div>
          </div>
        )}

        {integrityStatus.length > 0 ? (
          <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '70px 110px 130px 1fr 150px', gap: 0, padding: '6px 12px', background: 'var(--lbb-surface2)', borderBottom: '1px solid var(--lbb-border)', fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.06, textTransform: 'uppercase' }}>
              <span>LB#</span><span>Mount</span><span>Issue</span><span>Folder</span><span>Checked</span>
            </div>
            {integrityStatus.map(row => (
              <div key={row.lb_number} style={{ display: 'grid', gridTemplateColumns: '70px 110px 130px 1fr 150px', gap: 0, padding: '6px 12px', borderBottom: '1px solid var(--lbb-border)', fontSize: 12, alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600 }}>{row.lb_number}</span>
                <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{mounts.find(m => m.id === row.mount_id)?.label ?? '—'}</span>
                <Pill tone={toneForIntegrityStatus(row.status)} soft dot>{INTEGRITY_STATUS_LABELS[row.status] ?? row.status}</Pill>
                <span style={{ fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)', fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row.disk_path}>
                  {row.disk_path}
                  {row.content_issues > 0 && ` · ${row.content_issues} corrupt`}
                  {row.tag_issues > 0 && ` · ${row.tag_issues} tag-only`}
                  {row.missing_count > 0 && ` · ${row.missing_count} missing`}
                </span>
                <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>{row.checked_at}</span>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '14px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 12 }}>
            No integrity issues found. Run a scan to check your collection against its lbdir manifests.
          </div>
        )}

        {integrityEvents.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>Recent changes</span>
              <Pill tone="info" soft dot>{integrityEvents.length} unacknowledged</Pill>
              <div style={{ flex: 1 }} />
              <Button variant="ghost" size="sm" onClick={() => ackEvents(integrityEvents.map(e => e.id))}>Acknowledge all</Button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {integrityEvents.map(ev => (
                <div key={ev.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 7, border: '1px solid var(--lbb-border)', background: 'var(--lbb-surface2)' }}>
                  <Pill tone={toneForIntegrityEvent(ev.event_type)} soft dot>{INTEGRITY_EVENT_LABELS[ev.event_type] ?? ev.event_type}</Pill>
                  {ev.lb_number != null && <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 12, fontWeight: 600 }}>LB-{ev.lb_number}</span>}
                  <span style={{ fontSize: 11.5, color: 'var(--lbb-fg2)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.detail}</span>
                  <span style={{ fontSize: 11, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', flex: '0 0 auto' }}>{ev.occurred_at}</span>
                  <IconButton icon="check" size={24} title="Acknowledge" onClick={() => ackEvents([ev.id])} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── ScreenMounts ──────────────────────────────────────────────────────────────

export function ScreenMounts() {
  const { t } = useTranslation()
  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <div style={{ padding: '24px 32px 40px', maxWidth: 1100, margin: '0 auto' }}>
        <h1 style={{ fontSize: 'var(--lbb-fs-22)', fontWeight: 700, letterSpacing: -0.02, color: 'var(--lbb-fg)', margin: 0 }}>
          {t('mounts.title')}
        </h1>
        <p style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          {t('mounts.subtitle')}
        </p>

        <div style={{ marginTop: 24 }}>
          <CollectionRoutingCard />
        </div>
      </div>
    </div>
  )
}
