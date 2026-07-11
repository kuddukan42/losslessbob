import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Chip, Pill, Card, SectionHead, Toolbar, Input, Banner } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { Icon } from '../components/Icon'
import { useScraperLogStore } from '../lib/scraperLogStore'

// ── Error Boundary ─────────────────────────────────────────────────────────────

interface EBState { error: Error | null }
class ScraperErrorBoundary extends React.Component<{ children: React.ReactNode }, EBState> {
  state: EBState = { error: null }
  static getDerivedStateFromError(error: Error): EBState { return { error } }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ScreenScraper] render error:', error, info.componentStack)
  }
  render() {
    const { error } = this.state
    if (error) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100%', gap: 16,
          color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)',
        }}>
          <span style={{ fontSize: 'var(--lbb-fs-32)', opacity: 0.25 }}>⚠</span>
          <span style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 600, color: 'var(--lbb-bad-fg)' }}>
            Scraper failed to render
          </span>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', maxWidth: 480, textAlign: 'center' }}>
            {error.message}
          </span>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 8, padding: '6px 16px', borderRadius: 6,
              background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)',
              border: '1px solid var(--lbb-accent-mid)', cursor: 'pointer',
              fontSize: 'var(--lbb-fs-12)', fontFamily: 'inherit',
            }}
          >
            Try again
          </button>
          <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>
            Check the DevTools console (Ctrl+Shift+I) for the full stack trace.
          </span>
        </div>
      )
    }
    return this.props.children
  }
}

const BASE = window.api.flaskBase

// ── Types ────────────────────────────────────────────────────────────────────

interface CrawlerStatus {
  running: boolean; stage: string; current_url: string | null
  fetched: number; not_modified: number; skipped: number
  failed: number; not_found: number; queue_size: number
  session_id: number | null; message: string; stop_requested: boolean
}
interface ScrapeStatus {
  running: boolean; current_lb: number | null; last_lb: number | null
  total: number; done: number; errors: number; skipped: number
  last_action: string | null; last_source: string | null; stop_requested: boolean
}
interface BootlegStatus {
  running: boolean; stage: string; rows_total: number
  rows_added: number; rows_changed: number; rows_removed: number
  message: string; error: string | null
}
interface BobDylanStatus {
  status: string; phase: string; total: number; done: number
  errors: number; skipped: number; current_url: string | null
  stop_requested: boolean; message: string
}
interface SetlistFmStatus {
  status: string; page: number; total_pages: number
  shows_stored: number; tracks_stored: number
  errors: number; stop_requested: boolean; message: string
}
interface GeocoderStatus {
  running: boolean; done: number; total: number
  current: string; errors: number; succeeded: number; stage: string
  skipped: number; stop_requested: boolean
}
interface GeoStats {
  total_cached: number; geocoded: number | null; failed: number | null; manual: number | null
  skipped: number | null
  entries_total: number; entries_covered: number; pct_covered: number
}
interface CrawlerSession {
  id: number; started_at: string; finished_at: string | null; scope: string
  pages_fetched: number; pages_304: number; pages_failed: number; status: string
}
interface BootlegScrape {
  id: number; scraped_at: string; status: string
  rows_total: number; rows_added: number; rows_changed: number; rows_removed: number
}

type TabId = 'crawler' | 'entry' | 'bootlegs' | 'bobdylan' | 'setlistfm' | 'geocoder'

interface LogLine { ts: string; text: string; tone?: 'ok' | 'bad' | 'warn' | 'mute' }

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTs(ts: string | null): string {
  if (!ts) return '—'
  return ts.replace('T', ' ').slice(0, 16)
}

function statusTone(s: string): 'ok' | 'bad' | 'warn' | 'mute' | 'info' {
  if (s === 'running') return 'info'
  if (s === 'done' || s === 'idle' && false) return 'ok'
  if (s === 'error') return 'bad'
  if (s === 'stopped') return 'warn'
  return 'mute'
}

function dotColor(running: boolean, status: string): string {
  if (running || status === 'running') return 'var(--lbb-info-bar)'
  if (status === 'done') return 'var(--lbb-ok-bar)'
  if (status === 'error') return 'var(--lbb-bad-bar)'
  if (status === 'stopped') return 'var(--lbb-warn-bar)'
  return 'var(--lbb-border2)'
}

// ── LogPanel ─────────────────────────────────────────────────────────────────

function LogPanel({ lines, onClear }: { lines: LogLine[]; onClear: () => void }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines.length])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderBottom: '1px solid var(--lbb-border)',
        background: 'var(--lbb-surface)',
      }}>
        <span style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg3)', flex: 1, textTransform: 'uppercase', letterSpacing: 0.08 }}>Live Log</span>
        <button type="button" onClick={onClear} style={{
          fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', background: 'none', border: 'none',
          cursor: 'pointer', padding: '2px 6px',
        }}>Clear</button>
        <button type="button" onClick={() => {
          const text = lines.map(l => `${l.ts}  ${l.text}`).join('\n')
          navigator.clipboard.writeText(text).catch(() => {})
        }} style={{
          fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', background: 'none', border: 'none',
          cursor: 'pointer', padding: '2px 6px',
        }}>Copy</button>
      </div>
      <div style={{
        flex: 1, overflowY: 'auto', padding: '6px 10px',
        fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11-5)',
        background: 'var(--lbb-bg)', minHeight: 0,
      }}>
        {lines.length === 0 && (
          <div style={{ color: 'var(--lbb-fg3)', padding: '8px 0' }}>No activity yet.</div>
        )}
        {lines.map((l, i) => {
          const col = l.tone === 'bad' ? 'var(--lbb-bad-fg)'
            : l.tone === 'warn' ? 'var(--lbb-warn-fg)'
            : l.tone === 'ok' ? 'var(--lbb-ok-fg)'
            : 'var(--lbb-fg2)'
          return (
            <div key={i} style={{ display: 'flex', gap: 10, lineHeight: 1.6 }}>
              <span style={{ color: 'var(--lbb-fg3)', flexShrink: 0 }}>{l.ts}</span>
              <span style={{ color: col }}>{l.text}</span>
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </div>
  )
}

// ── StatusStrip ───────────────────────────────────────────────────────────────

interface StripCardProps {
  label: string; active: boolean; running: boolean; status: string
  stat: string; lastDate: string; onClick: () => void; badge?: string
}

function StripCard({ label, active, running, status, stat, lastDate, onClick, badge }: StripCardProps) {
  const dot = dotColor(running, status)
  return (
    <button type="button" onClick={onClick} style={{
      flex: 1, textAlign: 'left', cursor: 'pointer', border: 'none', borderRadius: 8,
      padding: '10px 14px',
      background: active ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
      outline: active ? '1.5px solid var(--lbb-accent-mid)' : '1px solid var(--lbb-border)',
      transition: 'outline 0.1s',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, flexShrink: 0,
          boxShadow: running ? `0 0 5px ${dot}` : 'none' }} />
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 700, color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)' }}>
          {label}
        </span>
        <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', marginLeft: 'auto' }}>
          {badge ?? (running ? 'running' : status)}
        </span>
      </div>
      <div style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums' }}>
        {stat}
      </div>
      <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
        Last: {lastDate}
      </div>
    </button>
  )
}

// ── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ value, total, indeterminate = false }: { value: number; total: number; indeterminate?: boolean }) {
  const pct = total > 0 ? Math.min(100, (value / total) * 100) : 0
  return (
    <div style={{ height: 4, borderRadius: 2, background: 'var(--lbb-border2)', overflow: 'hidden', marginTop: 4 }}>
      <div style={{
        height: '100%', borderRadius: 2,
        background: 'var(--lbb-accent-mid)',
        width: indeterminate ? '40%' : `${pct}%`,
        transition: indeterminate ? 'none' : 'width 0.3s',
        animation: indeterminate ? 'lbb-indeterminate 1.4s ease-in-out infinite' : 'none',
      }} />
    </div>
  )
}

// ── StatGrid ─────────────────────────────────────────────────────────────────

function StatGrid({ rows }: { rows: [string, string | number][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 12px', marginTop: 8 }}>
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{k}</span>
          <span style={{ fontSize: 'var(--lbb-fs-12)', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--lbb-fg2)' }}>
            {typeof v === 'number' ? v.toLocaleString() : v}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Section heading row ───────────────────────────────────────────────────────

function CtrlLabel({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', textTransform: 'uppercase', letterSpacing: 0.08, marginTop: 12, marginBottom: 4 }}>{children}</div>
}

// ── Tab: LB Site Crawler ──────────────────────────────────────────────────────

function CrawlerTab({ status, logs, onClearLog }: {
  status: CrawlerStatus | null; logs: LogLine[]; onClearLog: () => void
}) {
  const [scope, setScope] = useState('incremental')
  const [force, setForce] = useState(false)
  const [delay, setDelay] = useState('1500')
  const [cap, setCap] = useState('5000')
  const [sessions, setSessions] = useState<CrawlerSession[]>([])
  const [histOpen, setHistOpen] = useState(true)
  const running = status?.running ?? false

  useEffect(() => {
    fetch(`${BASE}/api/crawler/sessions?limit=15`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setSessions)
      .catch(() => {})
  }, [running])

  const start = async () => {
    await fetch(`${BASE}/api/crawler/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope, force, delay_ms: parseInt(delay), daily_cap: parseInt(cap) }),
    })
  }
  const stop = async () => { await fetch(`${BASE}/api/crawler/stop`, { method: 'POST' }) }

  const sessionTone = (s: string): 'ok' | 'warn' | 'bad' | 'mute' =>
    s === 'done' ? 'ok' : s === 'stopped' ? 'warn' : s === 'error' ? 'bad' : 'mute'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* Controls */}
        <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 0 }}>
          <CtrlLabel>Scope</CtrlLabel>
          <div style={{ display: 'flex', gap: 6 }}>
            {['incremental', 'full'].map(s => (
              <Chip key={s} size="sm" active={scope === s} onClick={() => setScope(s)}>{s}</Chip>
            ))}
          </div>
          <CtrlLabel>Options</CtrlLabel>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
            <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
            Force re-fetch cached pages
          </label>
          <CtrlLabel>Delay (ms)</CtrlLabel>
          <Input value={delay} onChange={e => setDelay(e.target.value)} size="sm" width={100} />
          <CtrlLabel>Daily cap</CtrlLabel>
          <Input value={cap} onChange={e => setCap(e.target.value)} size="sm" width={100} />

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <Button variant="primary" size="sm" icon="play" onClick={start} disabled={running}>Start Crawl</Button>
            <Button variant="danger" size="sm" icon="stop" onClick={stop} disabled={!running}>Stop</Button>
          </div>

          {status && (
            <>
              <div style={{ marginTop: 12 }}>
                <ProgressBar value={status.fetched} total={parseInt(cap)} indeterminate={running && parseInt(cap) === 0} />
              </div>
              {running && status.current_url && (
                <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 6, fontFamily: 'var(--lbb-mono)', wordBreak: 'break-all' }}>
                  {status.current_url.replace('http://www.losslessbob.wonderingwhattochoose.com', '')}
                </div>
              )}
              <StatGrid rows={[
                ['Fetched', status.fetched],
                ['304 (cached)', status.not_modified],
                ['Not found', status.not_found],
                ['Skipped', status.skipped],
                ['Failed', status.failed],
                ['Queue', status.queue_size],
              ]} />
            </>
          )}
        </div>
        {/* Log */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <LogPanel lines={logs} onClear={onClearLog} />
        </div>
      </div>

      {/* Session history */}
      <div style={{ borderTop: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <Toolbar pad="6px 14px">
          <SectionHead title="Session History" style={{ flex: 1, marginBottom: 0 }} />
          <button type="button" onClick={() => setHistOpen(o => !o)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
            {histOpen ? '▾' : '▸'}
          </button>
        </Toolbar>
        {histOpen && (
          <div style={{ maxHeight: 180, overflowY: 'auto' }}>
            <TableShell stickyHeader>
              <colgroup><col style={{ width: 160 }} /><col style={{ width: 160 }} /><col style={{ width: 100 }} /><col style={{ width: 100 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /><col style={{ width: 70 }} /></colgroup>
              <thead><tr><TH>Started</TH><TH>Finished</TH><TH>Scope</TH><TH>Status</TH><TH align="right">Fetched</TH><TH align="right">304</TH><TH align="right">Failed</TH></tr></thead>
              <tbody>
                {sessions.map(s => (
                  <TR key={s.id}>
                    <TD mono dim>{fmtTs(s.started_at)}</TD>
                    <TD mono dim>{fmtTs(s.finished_at)}</TD>
                    <TD>{s.scope}</TD>
                    <TD><Pill tone={sessionTone(s.status)} soft dot>{s.status}</Pill></TD>
                    <TD align="right" mono>{s.pages_fetched.toLocaleString()}</TD>
                    <TD align="right" mono>{s.pages_304.toLocaleString()}</TD>
                    <TD align="right" mono>{s.pages_failed.toLocaleString()}</TD>
                  </TR>
                ))}
                {sessions.length === 0 && <TR><TD colSpan={7} style={{ textAlign: 'center', color: 'var(--lbb-fg3)' }}>No sessions yet</TD></TR>}
              </tbody>
            </TableShell>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab: Entry Metadata Scraper ───────────────────────────────────────────────

function EntryTab({ status, logs, onClearLog, onLog }: {
  status: ScrapeStatus | null; logs: LogLine[]; onClearLog: () => void
  onLog: (text: string, tone?: LogLine['tone']) => void
}) {
  const [force, setForce] = useState(false)
  const [dlFiles, setDlFiles] = useState(false)
  const [localPages, setLocalPages] = useState(true)
  const [delay, setDelay] = useState('500')
  const [startLb, setStartLb] = useState('')
  const [endLb, setEndLb] = useState('')
  const [singleLb, setSingleLb] = useState('')
  const [singleBusy, setSingleBusy] = useState(false)
  const running = status?.running ?? false

  const post = async (path: string, body: object) => {
    await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  }

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto' }}>
        <CtrlLabel>Options</CtrlLabel>
        {[
          ['Force re-scrape', force, setForce],
          ['Download attachments', dlFiles, setDlFiles],
          ['Use local cached pages', localPages, setLocalPages],
        ].map(([label, val, setter]) => (
          <label key={label as string} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', cursor: 'pointer', marginBottom: 6 }}>
            <input type="checkbox" checked={val as boolean} onChange={e => (setter as (v: boolean) => void)(e.target.checked)} />
            {label as string}
          </label>
        ))}
        <CtrlLabel>Delay (ms)</CtrlLabel>
        <Input value={delay} onChange={e => setDelay(e.target.value)} size="sm" width={100} />

        <CtrlLabel>Actions</CtrlLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Button variant="primary" size="sm" icon="play" disabled={running}
            onClick={() => post('/api/scrape/start', { force, download_files: dlFiles, delay_ms: parseInt(delay) })}>
            Scrape All Missing
          </Button>
          <Button variant="secondary" size="sm" disabled={running}
            onClick={() => post('/api/scrape/private_rescrape', {})}>
            Re-scrape Private LBs
          </Button>
          <Button variant="secondary" size="sm" disabled={running}
            onClick={() => post('/api/scrape/download_pages', { force })}>
            Download Missing Pages
          </Button>
        </div>

        <CtrlLabel>Range Scrape</CtrlLabel>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <Input placeholder="Start LB" value={startLb} onChange={e => setStartLb(e.target.value)} size="sm" width={90} />
          <span style={{ color: 'var(--lbb-fg3)' }}>–</span>
          <Input placeholder="End LB" value={endLb} onChange={e => setEndLb(e.target.value)} size="sm" width={90} />
        </div>
        <Button variant="secondary" size="sm" style={{ marginTop: 6 }} disabled={running || !startLb || !endLb}
          onClick={() => post('/api/scrape/start', { start_lb: parseInt(startLb), end_lb: parseInt(endLb), force, download_files: dlFiles, delay_ms: parseInt(delay) })}>
          Scrape Range
        </Button>

        <CtrlLabel>Single Entry</CtrlLabel>
        <div style={{ display: 'flex', gap: 6 }}>
          <Input placeholder="LB number" value={singleLb} onChange={e => setSingleLb(e.target.value)} size="sm" width={110} />
          <Button variant="secondary" size="sm" disabled={running || singleBusy || !singleLb}
            onClick={async () => {
              const lbId = String(parseInt(singleLb)).padStart(5, '0')
              setSingleBusy(true)
              onLog(`scraping  LB-${lbId}...`)
              try {
                const res = await fetch(`${BASE}/api/entry/${singleLb}/scrape`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ force }),
                })
                const data = await res.json().catch(() => ({}))
                if (!res.ok || data.error) {
                  onLog(`LB-${lbId} error: ${data.error ?? res.status}`, 'bad')
                } else if (data.skipped) {
                  onLog(`LB-${lbId} skipped${data.reason ? ` (${data.reason})` : ' — already up to date'}`, 'warn')
                } else {
                  const n = data.files_downloaded?.length ?? 0
                  onLog(`LB-${lbId} done — ${n} file${n === 1 ? '' : 's'} downloaded`, 'ok')
                }
              } catch (e) {
                onLog(`LB-${lbId} request failed: ${e}`, 'bad')
              } finally {
                setSingleBusy(false)
              }
            }}>
            {singleBusy ? 'Working…' : 'Go'}
          </Button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <Button variant="danger" size="sm" icon="stop" onClick={() => post('/api/scrape/stop', {})} disabled={!running}>Stop</Button>
        </div>

        {status && (
          <>
            <div style={{ marginTop: 12 }}>
              <ProgressBar value={status.done} total={status.total} />
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
                {status.done.toLocaleString()} / {status.total.toLocaleString()}
              </div>
            </div>
            <StatGrid rows={[
              ['Errors', status.errors],
              ['Skipped', status.skipped],
              ['Current LB', status.current_lb ?? '—'],
            ]} />
          </>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <LogPanel lines={logs} onClear={onClearLog} />
      </div>
    </div>
  )
}

// ── Tab: Bootleg Catalog ──────────────────────────────────────────────────────

function BootlegTab({ status, logs, onClearLog }: {
  status: BootlegStatus | null; logs: LogLine[]; onClearLog: () => void
}) {
  const [force, setForce] = useState(false)
  const [history, setHistory] = useState<BootlegScrape[]>([])
  const running = status?.running ?? false

  useEffect(() => {
    fetch(`${BASE}/api/bootlegs/scrapes?limit=10`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setHistory)
      .catch(() => {})
  }, [running])

  const start = () => fetch(`${BASE}/api/bootlegs/scrape`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force }) })
  const stop = () => fetch(`${BASE}/api/bootlegs/stop`, { method: 'POST' })

  const histTone = (s: string): 'ok' | 'warn' | 'bad' | 'mute' =>
    s === 'success' ? 'ok' : s === 'no_change' ? 'mute' : 'bad'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto' }}>
          <CtrlLabel>Options</CtrlLabel>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
            <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
            Force re-scrape
          </label>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <Button variant="primary" size="sm" icon="play" onClick={start} disabled={running}>Scrape Catalog</Button>
            <Button variant="danger" size="sm" icon="stop" onClick={stop} disabled={!running}>Stop</Button>
          </div>
          {status && (
            <>
              <div style={{ marginTop: 12 }}>
                <ProgressBar value={0} total={0} indeterminate={running} />
                <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 4 }}>{status.stage}</div>
              </div>
              <StatGrid rows={[
                ['Total rows', status.rows_total],
                ['Added', status.rows_added],
                ['Changed', status.rows_changed],
                ['Removed', status.rows_removed],
              ]} />
              {status.error && <div style={{ marginTop: 8, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-bad-fg)' }}>{status.error}</div>}
            </>
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <LogPanel lines={logs} onClear={onClearLog} />
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--lbb-border)', flexShrink: 0 }}>
        <Toolbar pad="6px 14px">
          <SectionHead title="Scrape History" style={{ flex: 1, marginBottom: 0 }} />
        </Toolbar>
        <div style={{ maxHeight: 180, overflowY: 'auto' }}>
          <TableShell stickyHeader>
            <colgroup><col style={{ width: 160 }} /><col style={{ width: 110 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /></colgroup>
            <thead><tr><TH>Scraped at</TH><TH>Status</TH><TH align="right">Total</TH><TH align="right">Added</TH><TH align="right">Changed</TH><TH align="right">Removed</TH></tr></thead>
            <tbody>
              {history.map(h => (
                <TR key={h.id}>
                  <TD mono dim>{fmtTs(h.scraped_at)}</TD>
                  <TD><Pill tone={histTone(h.status)} soft dot>{h.status}</Pill></TD>
                  <TD align="right" mono>{h.rows_total.toLocaleString()}</TD>
                  <TD align="right" mono>{h.rows_added.toLocaleString()}</TD>
                  <TD align="right" mono>{h.rows_changed.toLocaleString()}</TD>
                  <TD align="right" mono>{h.rows_removed.toLocaleString()}</TD>
                </TR>
              ))}
              {history.length === 0 && <TR><TD colSpan={6} style={{ textAlign: 'center', color: 'var(--lbb-fg3)' }}>No history yet</TD></TR>}
            </tbody>
          </TableShell>
        </div>
      </div>
    </div>
  )
}

// ── Tab: bobdylan.com ─────────────────────────────────────────────────────────

function BobDylanTab({ status, logs, onClearLog }: {
  status: BobDylanStatus | null; logs: LogLine[]; onClearLog: () => void
}) {
  const [force, setForce] = useState(false)
  const [stats, setStats] = useState<{ total: number; scraped: number; pending: number } | null>(null)
  const running = status?.status === 'running'

  useEffect(() => {
    fetch(`${BASE}/api/bobdylan/stats`).then(r => r.ok ? r.json() : Promise.reject()).then(setStats).catch(() => {})
  }, [running])

  const post = (path: string, body: object = {}) =>
    fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto' }}>
        <CtrlLabel>Options</CtrlLabel>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
          <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
          Force re-scrape all shows
        </label>

        <CtrlLabel>Actions</CtrlLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Button variant="primary" size="sm" icon="play" disabled={running}
            onClick={() => post('/api/bobdylan/update', { force })}>
            Discover + Scrape (full update)
          </Button>
          <Button variant="secondary" size="sm" disabled={running}
            onClick={() => post('/api/bobdylan/discover')}>
            Discover only (sitemap)
          </Button>
          <Button variant="secondary" size="sm" disabled={running}
            onClick={() => post('/api/bobdylan/scrape', { force })}>
            Scrape show pages only
          </Button>
          <Button variant="danger" size="sm" icon="stop" disabled={!running}
            onClick={() => post('/api/bobdylan/stop')}>
            Stop
          </Button>
        </div>

        {status && (
          <>
            <div style={{ marginTop: 12 }}>
              <ProgressBar value={status.done} total={status.total} indeterminate={running && status.total === 0} />
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
                Phase: {status.phase || '—'} · {status.done}/{status.total}
              </div>
            </div>
            <StatGrid rows={[
              ['Errors', status.errors],
              ['Skipped', status.skipped],
            ]} />
          </>
        )}

        {stats && (
          <>
            <CtrlLabel>Database</CtrlLabel>
            <StatGrid rows={[
              ['Total shows', stats.total],
              ['Scraped', stats.scraped],
              ['Pending', stats.pending],
            ]} />
          </>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <LogPanel lines={logs} onClear={onClearLog} />
      </div>
    </div>
  )
}

// ── Tab: setlist.fm ───────────────────────────────────────────────────────────

function SetlistFmTab({ status, logs, onClearLog }: {
  status: SetlistFmStatus | null; logs: LogLine[]; onClearLog: () => void
}) {
  const [apiKey, setApiKey] = useState('')
  const [keyConfigured, setKeyConfigured] = useState(false)
  const [force, setForce] = useState(false)
  const [stats, setStats] = useState<{ shows: number; tracks: number; tours: number } | null>(null)
  const [keyMsg, setKeyMsg] = useState('')
  const running = status?.status === 'running'

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}/api/setlistfm/key`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/setlistfm/stats`).then(r => r.ok ? r.json() : null),
    ]).then(([key, s]) => {
      if (key) setKeyConfigured(key.configured)
      if (s) setStats(s)
    }).catch(() => {})
  }, [running])

  const saveKey = async () => {
    const r = await fetch(`${BASE}/api/setlistfm/key`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    })
    if (r.ok) { setKeyConfigured(true); setKeyMsg('Saved'); setApiKey('') }
    else setKeyMsg('Failed to save')
    setTimeout(() => setKeyMsg(''), 2500)
  }

  const post = (path: string, body: object = {}) =>
    fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto' }}>
        <CtrlLabel>API Key</CtrlLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: keyConfigured ? 'var(--lbb-ok-bar)' : 'var(--lbb-warn-bar)', flexShrink: 0 }} />
          <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{keyConfigured ? 'Configured' : 'Not set'}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <Input type="password" placeholder="setlist.fm API key" value={apiKey}
            onChange={e => setApiKey(e.target.value)} size="sm" width={160} />
          <Button variant="secondary" size="sm" onClick={saveKey} disabled={!apiKey}>Save</Button>
        </div>
        {keyMsg && <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-ok-fg)', marginTop: 4 }}>{keyMsg}</div>}

        <CtrlLabel>Options</CtrlLabel>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', cursor: 'pointer' }}>
          <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
          Force re-fetch all setlists
        </label>

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <Button variant="primary" size="sm" icon="play" disabled={running || !keyConfigured}
            onClick={() => post('/api/setlistfm/update', { force })}>
            Update All Setlists
          </Button>
          <Button variant="danger" size="sm" icon="stop" disabled={!running}
            onClick={() => post('/api/setlistfm/stop')}>
            Stop
          </Button>
        </div>
        {!keyConfigured && (
          <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-warn-fg)', marginTop: 6 }}>
            An API key is required. Get one at setlist.fm/settings/api.
          </div>
        )}

        {status && running && (
          <>
            <div style={{ marginTop: 12 }}>
              <ProgressBar value={status.page} total={status.total_pages} indeterminate={status.total_pages === 0} />
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
                Page {status.page} / {status.total_pages || '?'}
              </div>
            </div>
            <StatGrid rows={[
              ['Shows stored', status.shows_stored],
              ['Tracks stored', status.tracks_stored],
              ['Errors', status.errors],
            ]} />
          </>
        )}

        {stats && (
          <>
            <CtrlLabel>Database</CtrlLabel>
            <StatGrid rows={[
              ['Shows', stats.shows],
              ['Tracks', stats.tracks],
              ['Tours', stats.tours],
            ]} />
          </>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <LogPanel lines={logs} onClear={onClearLog} />
      </div>
    </div>
  )
}

// ── Tab: Geocoder ─────────────────────────────────────────────────────────────

function GeocoderTab({ status, geoStats, logs, onClearLog }: {
  status: GeocoderStatus | null; geoStats: GeoStats | null; logs: LogLine[]; onClearLog: () => void
}) {
  const { t } = useTranslation()
  const [manualLoc, setManualLoc] = useState('')
  const [manualLat, setManualLat] = useState('')
  const [manualLon, setManualLon] = useState('')
  const [manualMsg, setManualMsg] = useState('')
  const running = status?.running ?? false

  const post = (path: string, body: object = {}) =>
    fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

  const placeManual = async () => {
    const r = await post('/api/geocode/location', { location: manualLoc, lat: parseFloat(manualLat), lon: parseFloat(manualLon) })
    if (r.ok) { setManualMsg('Saved'); setManualLoc(''); setManualLat(''); setManualLon('') }
    else setManualMsg('Failed')
    setTimeout(() => setManualMsg(''), 2500)
  }

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      <div style={{ width: 300, flexShrink: 0, padding: '14px 16px', borderRight: '1px solid var(--lbb-border)', overflowY: 'auto' }}>
        <CtrlLabel>Batch Geocode</CtrlLabel>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="primary" size="sm" icon="play" disabled={running}
            onClick={() => post('/api/geocode/run')}>
            Run Batch
          </Button>
          <Button variant="danger" size="sm" icon="stop" disabled={!running}
            onClick={() => post('/api/geocode/stop')}>
            Stop
          </Button>
        </div>

        {status && (
          <>
            <div style={{ marginTop: 12 }}>
              <ProgressBar value={status.done} total={status.total} />
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 4 }}>
                {status.done.toLocaleString()} / {status.total.toLocaleString()} · stage: {status.stage}
              </div>
            </div>
            <StatGrid rows={[
              ['Succeeded', status.succeeded],
              ['Errors', status.errors],
            ]} />
            {status.current && (
              <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 6, fontFamily: 'var(--lbb-mono)', wordBreak: 'break-all' }}>
                {status.current}
              </div>
            )}
          </>
        )}

        {geoStats && (
          <>
            <CtrlLabel>Cache Stats</CtrlLabel>
            <StatGrid rows={[
              ['Cached', geoStats.total_cached],
              ['Geocoded', geoStats.geocoded ?? 0],
              ['Failed', geoStats.failed ?? 0],
              ['Manual pins', geoStats.manual ?? 0],
              [t('scraper.geocoder.skippedLabel'), geoStats.skipped ?? 0],
            ]} />
            <CtrlLabel>Coverage</CtrlLabel>
            <StatGrid rows={[
              ['Unique locations', geoStats.entries_total],
              ['With coordinates', geoStats.entries_covered],
              ['Coverage', `${geoStats.pct_covered}%`],
            ]} />
          </>
        )}

        <CtrlLabel>Purge Cache</CtrlLabel>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" size="sm" disabled={running}
            onClick={() => post('/api/geocode/purge', { scope: 'failed' })}>
            Purge Failed
          </Button>
          <Button variant="danger" size="sm" disabled={running}
            onClick={() => post('/api/geocode/purge', { scope: 'all' })}>
            Purge All
          </Button>
        </div>

        <CtrlLabel>Manual Pin</CtrlLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Input placeholder="Location text (exact match)" value={manualLoc} onChange={e => setManualLoc(e.target.value)} size="sm" />
          <div style={{ display: 'flex', gap: 6 }}>
            <Input placeholder="Lat" value={manualLat} onChange={e => setManualLat(e.target.value)} size="sm" width={110} />
            <Input placeholder="Lon" value={manualLon} onChange={e => setManualLon(e.target.value)} size="sm" width={110} />
          </div>
          <Button variant="secondary" size="sm" disabled={!manualLoc || !manualLat || !manualLon} onClick={placeManual}>
            Place Pin
          </Button>
          {manualMsg && <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-ok-fg)' }}>{manualMsg}</div>}
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <LogPanel lines={logs} onClear={onClearLog} />
      </div>
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

const TABS: { id: TabId; label: string }[] = [
  { id: 'crawler',   label: 'LB Crawler' },
  { id: 'entry',     label: 'Entry Metadata' },
  { id: 'bootlegs',  label: 'Bootleg Catalog' },
  { id: 'bobdylan',  label: 'Dylan.com' },
  { id: 'setlistfm', label: 'Setlist.fm' },
  { id: 'geocoder',  label: 'Geocoder' },
]

function ScreenScraperInner() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabId>('crawler')

  // All statuses
  const [crawlerStatus,   setCrawlerStatus]   = useState<CrawlerStatus | null>(null)
  const [scrapeStatus,    setScrapeStatus]     = useState<ScrapeStatus | null>(null)
  const [bootlegStatus,   setBootlegStatus]    = useState<BootlegStatus | null>(null)
  const [bobdylanStatus,  setBobdylanStatus]   = useState<BobDylanStatus | null>(null)
  const [setlistFmStatus, setSetlistFmStatus]  = useState<SetlistFmStatus | null>(null)
  const [geocoderStatus,  setGeocoderStatus]   = useState<GeocoderStatus | null>(null)

  // Strip stats
  const [crawlerStats,   setCrawlerStats]   = useState<{ last: string; fetched: number } | null>(null)
  const [scrapeStats,    setScrapeStats]    = useState<{ done: number; total: number } | null>(null)
  const [bootlegStats,   setBootlegStats]   = useState<{ total: number; last: string } | null>(null)
  const [bobdylanStats,  setBobdylanStats]  = useState<{ total: number; scraped: number; last: string } | null>(null)
  const [setlistFmStats, setSetlistFmStats] = useState<{ shows: number; tracks: number } | null>(null)
  const [geocoderStats,  setGeocoderStats]  = useState<{ done: number; total: number } | null>(null)
  const [geoStats,       setGeoStats]       = useState<GeoStats | null>(null)
  const [invStats,       setInvStats]       = useState<{ total: number } | null>(null)
  const [entryDbStats,   setEntryDbStats]   = useState<{ ok: number } | null>(null)

  // Logs per tab (max 500 lines each) — held in a module-level store so they
  // survive this screen unmounting on tab navigation (TODO-148).
  const logs = useScraperLogStore(s => s.logs)
  const pushLogToStore = useScraperLogStore(s => s.pushLog)
  const clearLogInStore = useScraperLogStore(s => s.clearLog)

  // Previous status refs for log diffing
  const prevRef = useRef<{
    crawlerUrl: string | null; crawlerFetched: number
    scrapeLb: number | null; scrapeAction: string | null
    bootlegMsg: string; bdUrl: string | null; bdMsg: string
    sfPage: number; sfMsg: string
    geoLoc: string; geoStage: string
  }>({
    crawlerUrl: null, crawlerFetched: 0,
    scrapeLb: null, scrapeAction: null,
    bootlegMsg: '', bdUrl: null, bdMsg: '',
    sfPage: 0, sfMsg: '',
    geoLoc: '', geoStage: '',
  })

  const pushLog = useCallback((tab: TabId, text: string, tone?: LogLine['tone']) => {
    pushLogToStore(tab, text, tone)
  }, [pushLogToStore])

  const clearLog = useCallback((tab: TabId) => {
    clearLogInStore(tab)
  }, [clearLogInStore])

  // Fetch all statuses
  const pollAll = useCallback(async () => {
    const results = await Promise.allSettled([
      fetch(`${BASE}/api/crawler/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/scrape/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/bootlegs/scrape/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/bobdylan/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/setlistfm/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/geocode/status`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/geocode/stats`).then(r => r.ok ? r.json() : null),
      // Strip extras
      fetch(`${BASE}/api/crawler/sessions?limit=1`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/bootlegs/stats`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/bobdylan/stats`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/setlistfm/stats`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/db/stats`).then(r => r.ok ? r.json() : null),
      fetch(`${BASE}/api/crawler/inventory/stats`).then(r => r.ok ? r.json() : null),
    ])

    const v = results.map(r => r.status === 'fulfilled' ? r.value : null)
    const [crawler, scrape, bootleg, bd, slFm, geo, geoSt, crawlerSess, bootlegSt, bdSt, slFmSt, dbSt, invSt] = v

    const p = prevRef.current

    if (crawler) {
      setCrawlerStatus(crawler)
      if (crawler.running) {
        if (crawler.current_url && crawler.current_url !== p.crawlerUrl) {
          const action = crawler.stage === 'crawling' ? 'fetched' : crawler.stage
          const shortUrl = (crawler.current_url as string).replace('http://www.losslessbob.wonderingwhattochoose.com', '')
          pushLog('crawler', `${action.padEnd(8)} ${shortUrl}`)
          p.crawlerUrl = crawler.current_url
        }
        if (crawler.failed > p.crawlerFetched && crawler.failed > 0) {
          pushLog('crawler', `failed   ${crawler.current_url}`, 'bad')
        }
        p.crawlerFetched = crawler.failed
      } else if (crawler.stage === 'done' && p.crawlerUrl !== null) {
        pushLog('crawler', `Crawl complete — ${crawler.fetched} fetched, ${crawler.failed} failed`, 'ok')
        p.crawlerUrl = null
      }
      if (crawlerSess && Array.isArray(crawlerSess) && crawlerSess.length > 0) {
        setCrawlerStats({ last: fmtTs(crawlerSess[0].started_at), fetched: crawlerSess[0].pages_fetched })
      }
    }

    if (scrape) {
      setScrapeStatus(scrape)
      if (scrape.running && scrape.current_lb !== p.scrapeLb) {
        const action = scrape.last_action ?? 'scraping'
        const src = scrape.last_source ? ` [${scrape.last_source}]` : ''
        pushLog('entry', `${action.padEnd(8)} LB-${String(scrape.current_lb).padStart(5, '0')}${src}`)
        p.scrapeLb = scrape.current_lb
      }
      setScrapeStats({ done: scrape.done, total: scrape.total })
    }

    if (bootleg) {
      setBootlegStatus(bootleg)
      if (bootleg.message && bootleg.message !== p.bootlegMsg) {
        pushLog('bootlegs', bootleg.message, bootleg.error ? 'bad' : undefined)
        p.bootlegMsg = bootleg.message
      }
    }
    if (bootlegSt) {
      setBootlegStats({ total: bootlegSt.total ?? 0, last: bootlegSt.last_scraped_at ? fmtTs(bootlegSt.last_scraped_at) : '—' })
    }

    if (bd) {
      setBobdylanStatus(bd)
      if (bd.status === 'running' && bd.current_url && bd.current_url !== p.bdUrl) {
        const shortUrl = (bd.current_url as string).replace('https://www.bobdylan.com', '')
        pushLog('bobdylan', `${(bd.phase || 'scraping').padEnd(10)} ${shortUrl}`)
        p.bdUrl = bd.current_url
      } else if (bd.message && bd.message !== p.bdMsg) {
        pushLog('bobdylan', bd.message, bd.status === 'error' ? 'bad' : undefined)
        p.bdMsg = bd.message
      }
    }
    if (bdSt) setBobdylanStats({ total: bdSt.total, scraped: bdSt.scraped, last: '—' })

    if (slFm) {
      setSetlistFmStatus(slFm)
      if (slFm.status === 'running' && slFm.page !== p.sfPage) {
        pushLog('setlistfm', `Page ${slFm.page}/${slFm.total_pages || '?'} · ${slFm.shows_stored} shows stored`)
        p.sfPage = slFm.page
      } else if (slFm.message && slFm.message !== p.sfMsg) {
        pushLog('setlistfm', slFm.message, slFm.status === 'error' ? 'bad' : undefined)
        p.sfMsg = slFm.message
      }
    }
    if (slFmSt) setSetlistFmStats({ shows: slFmSt.shows, tracks: slFmSt.tracks })

    if (geo) {
      setGeocoderStatus(geo)
      if (geo.running) {
        if (geo.current && geo.current !== p.geoLoc) {
          pushLog('geocoder', `geocoding  ${geo.current}`)
          p.geoLoc = geo.current
        } else if (geo.stage !== p.geoStage) {
          pushLog('geocoder', `stage: ${geo.stage}`, geo.stage === 'rate_limited' ? 'warn' : undefined)
          p.geoStage = geo.stage
        }
      }
      setGeocoderStats({ done: geo.done, total: geo.total })
    }
    if (geoSt && !geoSt.error) setGeoStats(geoSt)

    if (dbSt) {
      setEntryDbStats({ ok: dbSt.ok_entries ?? 0 })
    }
    if (invSt) {
      setInvStats({ total: invSt.total ?? 0 })
    }
  }, [pushLog])

  useEffect(() => {
    pollAll()
    const id = setInterval(pollAll, 2000)
    return () => clearInterval(id)
  }, [pollAll])

  // Strip card data
  const stripCards: { id: TabId; label: string; running: boolean; status: string; stat: string; lastDate: string; badge?: string }[] = [
    {
      id: 'crawler', label: 'LB Crawler',
      running: crawlerStatus?.running ?? false,
      status: crawlerStatus?.stage ?? 'idle',
      stat: invStats ? `${invStats.total.toLocaleString()} URLs indexed` : '—',
      lastDate: crawlerStats?.last ?? '—',
    },
    {
      id: 'entry', label: 'Entry Metadata',
      running: scrapeStatus?.running ?? false,
      status: scrapeStatus?.running ? 'running' : 'idle',
      stat: scrapeStatus?.running && scrapeStats
        ? `${scrapeStats.done.toLocaleString()} / ${scrapeStats.total.toLocaleString()}`
        : entryDbStats ? `${entryDbStats.ok.toLocaleString()} entries` : '—',
      lastDate: '—',
    },
    {
      id: 'bootlegs', label: 'Bootleg Catalog',
      running: bootlegStatus?.running ?? false,
      status: bootlegStatus?.stage ?? 'idle',
      stat: bootlegStats ? `${bootlegStats.total.toLocaleString()} titles` : '—',
      lastDate: bootlegStats?.last ?? '—',
    },
    {
      id: 'bobdylan', label: 'Dylan.com',
      running: bobdylanStatus?.status === 'running',
      status: bobdylanStatus?.status ?? 'idle',
      stat: bobdylanStats ? `${bobdylanStats.scraped.toLocaleString()} / ${bobdylanStats.total.toLocaleString()} shows` : '—',
      lastDate: '—',
    },
    {
      id: 'setlistfm', label: 'Setlist.fm',
      running: setlistFmStatus?.status === 'running',
      status: setlistFmStatus?.status ?? 'idle',
      stat: setlistFmStats ? `${setlistFmStats.shows.toLocaleString()} shows` : '—',
      lastDate: '—',
    },
    {
      id: 'geocoder', label: 'Geocoder',
      running: geocoderStatus?.running ?? false,
      status: geocoderStatus?.running ? 'running' : 'idle',
      stat: geoStats ? `${geoStats.pct_covered}% covered` : '—',
      lastDate: geoStats ? `${(geoStats.geocoded ?? 0).toLocaleString()} cached` : '—',
      badge: geocoderStatus?.running && geocoderStatus?.stop_requested
        ? t('scraper.geocoder.stoppingBadge')
        : undefined,
    },
  ]

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

        {/* Curator-only note (spec §6: end users get scraped data via master + site-data releases) */}
        <div style={{ padding: '10px 16px 0', flexShrink: 0 }}>
          <Banner tone="info" icon="info">{t('scraper.curatorNote')}</Banner>
        </div>

        {/* Status Strip */}
        <div style={{
          padding: '10px 16px', borderBottom: '1px solid var(--lbb-border)',
          background: 'var(--lbb-surface)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', gap: 10 }}>
            {stripCards.map(c => (
              <StripCard key={c.id} {...c} active={activeTab === c.id} onClick={() => setActiveTab(c.id)} />
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'crawler'   && <CrawlerTab   status={crawlerStatus}   logs={logs.crawler}   onClearLog={() => clearLog('crawler')} />}
          {activeTab === 'entry'     && <EntryTab      status={scrapeStatus}    logs={logs.entry}     onClearLog={() => clearLog('entry')} onLog={(text, tone) => pushLog('entry', text, tone)} />}
          {activeTab === 'bootlegs'  && <BootlegTab    status={bootlegStatus}   logs={logs.bootlegs}  onClearLog={() => clearLog('bootlegs')} />}
          {activeTab === 'bobdylan'  && <BobDylanTab   status={bobdylanStatus}  logs={logs.bobdylan}  onClearLog={() => clearLog('bobdylan')} />}
          {activeTab === 'setlistfm' && <SetlistFmTab  status={setlistFmStatus} logs={logs.setlistfm} onClearLog={() => clearLog('setlistfm')} />}
          {activeTab === 'geocoder'  && <GeocoderTab   status={geocoderStatus}  geoStats={geoStats}  logs={logs.geocoder}  onClearLog={() => clearLog('geocoder')} />}
        </div>
      </div>
    </>
  )
}

export function ScreenScraper() {
  return (
    <ScraperErrorBoundary>
      <ScreenScraperInner />
    </ScraperErrorBoundary>
  )
}
