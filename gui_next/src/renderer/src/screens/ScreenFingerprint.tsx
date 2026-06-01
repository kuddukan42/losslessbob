import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Button, Card, Pill, SectionHead, TableShell, TH, TR, TD, Toolbar,
} from '../components'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type Phase = 'idle' | 'loading' | 'building' | 'identifying' | 'done'
type ToastTone = 'ok' | 'bad' | 'info'

interface LbEntry {
  lb_number: number
  folder_name: string
  disk_path: string
  date_str: string
  location: string
}

interface BuildStatus {
  status: string
  current: string
  done: number
  total: number
  stop_requested: boolean
}

interface Candidate {
  lb_number: number
  file_path: string
  score: number
  confident: boolean
}

interface MatchResult {
  user_file: string
  candidates: Candidate[]
}

interface IdentifyStatus {
  status: string
  current: string
  done: number
  total: number
  results: MatchResult[]
  errors: string[]
  stop_requested: boolean
}

// ── Progress bar sub-component ─────────────────────────────────────────────────

function ProgressBar({ done, total, current }: { done: number; total: number; current: string }) {
  const { t } = useTranslation()
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
          {t('fingerprint.progress.files', { done, total })}
        </span>
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{pct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: 'var(--lbb-surface2)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 3, background: 'var(--lbb-accent-mid)',
          width: `${pct}%`, transition: 'width 0.3s ease',
        }} />
      </div>
      {current && (
        <div style={{
          fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {t('fingerprint.progress.current', { name: current })}
        </div>
      )}
    </div>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenFingerprint(): React.JSX.Element {
  const { t } = useTranslation()

  const [date, setDate]               = useState('')
  const [userFolder, setUserFolder]   = useState('')
  const [lbEntries, setLbEntries]     = useState<LbEntry[]>([])
  const [phase, setPhase]             = useState<Phase>('idle')
  const [buildStatus, setBuildStatus] = useState<BuildStatus | null>(null)
  const [idStatus, setIdStatus]       = useState<IdentifyStatus | null>(null)
  const [toast, setToast]             = useState<{ msg: string; tone: ToastTone } | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => {
    setToast({ msg, tone })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  useEffect(() => () => stopPoll(), [stopPoll])

  // ── Load collection entries for the selected date ──────────────────────────

  async function findEntries() {
    if (!date) return
    setPhase('loading')
    setLbEntries([])
    try {
      const r = await fetch(`${BASE}/api/fingerprint/collection_by_date?date=${encodeURIComponent(date)}`)
      const rows: LbEntry[] = await r.json()
      setLbEntries(rows)
      if (rows.length === 0) showToast(t('fingerprint.toast.noEntries', { date }), 'info')
    } catch {
      showToast(t('fingerprint.toast.loadFailed'), 'bad')
    } finally {
      setPhase('idle')
    }
  }

  // ── Folder picker ──────────────────────────────────────────────────────────

  async function pickFolder() {
    try {
      const chosen = await window.api.pickDir()
      if (chosen) setUserFolder(chosen)
    } catch {
      showToast(t('fingerprint.toast.pickFailed'), 'bad')
    }
  }

  // ── Phase 1: build LB fingerprints ────────────────────────────────────────

  async function runMatch() {
    const withPath = lbEntries.filter(e => e.disk_path)
    if (withPath.length === 0) {
      showToast(t('fingerprint.toast.noPath'), 'bad')
      return
    }

    setPhase('building')
    setBuildStatus(null)

    try {
      const r = await fetch(`${BASE}/api/fingerprint/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folders: withPath.map(e => ({ disk_path: e.disk_path, lb_number: e.lb_number })),
        }),
      })
      if (!r.ok) {
        showToast(t('fingerprint.toast.buildFailed'), 'bad')
        setPhase('idle')
        return
      }
    } catch {
      showToast(t('fingerprint.toast.buildFailed'), 'bad')
      setPhase('idle')
      return
    }

    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${BASE}/api/fingerprint/build/status`)
        const s: BuildStatus = await r.json()
        setBuildStatus(s)
        if (s.status === 'done') { stopPoll(); await startIdentify() }
        else if (s.stop_requested && s.status !== 'running') {
          stopPoll(); setPhase('idle'); showToast(t('fingerprint.toast.stopped'), 'info')
        }
      } catch { /* ignore */ }
    }, 800)
  }

  // ── Phase 2: identify user files ──────────────────────────────────────────

  async function startIdentify() {
    setPhase('identifying')
    setIdStatus(null)

    try {
      const r = await fetch(`${BASE}/api/fingerprint/identify_folder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: userFolder }),
      })
      if (!r.ok) {
        showToast(t('fingerprint.toast.identifyFailed'), 'bad')
        setPhase('idle')
        return
      }
    } catch {
      showToast(t('fingerprint.toast.identifyFailed'), 'bad')
      setPhase('idle')
      return
    }

    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${BASE}/api/fingerprint/identify_folder/status`)
        const s: IdentifyStatus = await r.json()
        setIdStatus(s)
        if (s.status === 'done') {
          stopPoll()
          setPhase('done')
          showToast(t('fingerprint.toast.done'), 'ok')
        }
      } catch { /* ignore */ }
    }, 800)
  }

  // ── Stop ──────────────────────────────────────────────────────────────────

  async function handleStop() {
    stopPoll()
    if (phase === 'building') {
      await fetch(`${BASE}/api/fingerprint/build/stop`, { method: 'POST' })
      setPhase('idle')
    } else if (phase === 'identifying') {
      await fetch(`${BASE}/api/fingerprint/identify_folder/stop`, { method: 'POST' })
      setPhase('done')
    }
    showToast(t('fingerprint.toast.stopped'), 'info')
  }

  // ── Cleanup ───────────────────────────────────────────────────────────────

  async function cleanup() {
    try {
      await fetch(`${BASE}/api/fingerprint/purge`, { method: 'POST' })
      showToast(t('fingerprint.toast.cleanupDone'), 'ok')
      setPhase('idle')
      setBuildStatus(null)
      setIdStatus(null)
    } catch {
      showToast(t('fingerprint.toast.cleanupFailed'), 'bad')
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────

  const withPath = lbEntries.filter(e => e.disk_path)
  const canMatch = withPath.length > 0 && !!userFolder && phase === 'idle'
  const isRunning = phase === 'building' || phase === 'identifying'
  const lbLocationMap = Object.fromEntries(lbEntries.map(e => [e.lb_number, e.location]))

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%', overflow: 'auto' }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 16, right: 20, zIndex: 1000,
          padding: '10px 16px', borderRadius: 8,
          background: `var(--lbb-${toast.tone}-bg)`,
          border: `1px solid var(--lbb-${toast.tone}-bar)`,
          color: `var(--lbb-${toast.tone}-fg)`,
          fontSize: 'var(--lbb-fs-12-5)', fontWeight: 500,
          boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
        }}>
          {toast.msg}
        </div>
      )}

      <div style={{ flex: 1, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* ── Configure ────────────────────────────────────────────────────── */}
        <Card>
          <SectionHead
            title={t('fingerprint.configure.title')}
            subtitle={t('fingerprint.configure.subtitle')}
          />

          {/* Date row */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginTop: 14 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
                {t('fingerprint.configure.date')}
              </label>
              <input
                type="date"
                value={date}
                onChange={e => { setDate(e.target.value); setLbEntries([]) }}
                style={{
                  height: 32, padding: '0 10px', borderRadius: 6,
                  border: '1px solid var(--lbb-border2)',
                  background: 'var(--lbb-bg)', color: 'var(--lbb-fg)',
                  fontSize: 'var(--lbb-fs-13)', fontFamily: 'var(--lbb-mono)',
                  cursor: 'pointer',
                }}
              />
            </div>
            <Button
              variant="secondary"
              icon={phase === 'loading' ? 'refresh' : 'search'}
              onClick={findEntries}
              disabled={!date || isRunning || phase === 'loading'}
            >
              {phase === 'loading' ? t('fingerprint.configure.finding') : t('fingerprint.configure.findEntries')}
            </Button>
          </div>

          {/* LB entries table */}
          {lbEntries.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', marginBottom: 8 }}>
                {t('fingerprint.configure.found', { count: lbEntries.length, withPath: withPath.length })}
              </div>
              <div style={{
                borderRadius: 6, border: '1px solid var(--lbb-border)',
                overflow: 'hidden', maxHeight: 200, overflowY: 'auto',
              }}>
                <TableShell>
                  <thead>
                    <tr>
                      <TH>{t('fingerprint.entries.lb')}</TH>
                      <TH>{t('fingerprint.entries.location')}</TH>
                      <TH>{t('fingerprint.entries.folder')}</TH>
                      <TH>{t('fingerprint.entries.onDisk')}</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {lbEntries.map(e => (
                      <TR key={e.lb_number}>
                        <TD mono>{`LB-${String(e.lb_number).padStart(5, '0')}`}</TD>
                        <TD>{e.location || '—'}</TD>
                        <TD dim>{e.folder_name}</TD>
                        <TD>
                          <Pill tone={e.disk_path ? 'ok' : 'mute'} soft dot>
                            {e.disk_path ? t('fingerprint.entries.yes') : t('fingerprint.entries.no')}
                          </Pill>
                        </TD>
                      </TR>
                    ))}
                  </tbody>
                </TableShell>
              </div>
            </div>
          )}

          {/* Mystery folder */}
          <div style={{ marginTop: 16, display: 'flex', gap: 10, alignItems: 'flex-end' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 0 }}>
              <label style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
                {t('fingerprint.configure.userFolder')}
              </label>
              <div style={{
                height: 32, padding: '0 10px', borderRadius: 6,
                border: '1px solid var(--lbb-border2)',
                background: 'var(--lbb-surface2)',
                fontSize: 'var(--lbb-fs-12)', fontFamily: 'var(--lbb-mono)',
                display: 'flex', alignItems: 'center',
                color: userFolder ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {userFolder || t('fingerprint.configure.noFolderSelected')}
              </div>
            </div>
            <Button variant="secondary" icon="folder" onClick={pickFolder} disabled={isRunning}>
              {t('fingerprint.configure.browse')}
            </Button>
          </div>

          {/* Match button */}
          <div style={{ marginTop: 16, display: 'flex', gap: 10, alignItems: 'center' }}>
            <Button variant="primary" icon="fingerprint" onClick={runMatch} disabled={!canMatch}>
              {t('fingerprint.configure.match')}
            </Button>
            {!canMatch && phase === 'idle' && (
              <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                {t('fingerprint.configure.matchHint')}
              </span>
            )}
          </div>
        </Card>

        {/* ── Progress ─────────────────────────────────────────────────────── */}
        {isRunning && (
          <Card>
            <Toolbar style={{ marginBottom: 14 }}>
              <SectionHead
                title={phase === 'building'
                  ? t('fingerprint.progress.phase1')
                  : t('fingerprint.progress.phase2')}
                style={{ marginBottom: 0, flex: 1 }}
              />
              <Button variant="ghost" size="sm" icon="x" onClick={handleStop}>
                {t('fingerprint.progress.stop')}
              </Button>
            </Toolbar>

            {phase === 'building' && buildStatus ? (
              <ProgressBar done={buildStatus.done} total={buildStatus.total} current={buildStatus.current} />
            ) : phase === 'building' ? (
              <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('common.loading')}</div>
            ) : null}

            {phase === 'identifying' && idStatus ? (
              <ProgressBar done={idStatus.done} total={idStatus.total} current={idStatus.current} />
            ) : phase === 'identifying' ? (
              <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('common.loading')}</div>
            ) : null}
          </Card>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {phase === 'done' && idStatus && (
          <Card>
            <Toolbar style={{ marginBottom: 12 }}>
              <SectionHead
                title={t('fingerprint.results.title')}
                subtitle={`${idStatus.results.length} ${t('fingerprint.results.filesIdentified')}`}
                style={{ marginBottom: 0, flex: 1 }}
              />
              <Button variant="ghost" size="sm" icon="trash" onClick={cleanup}>
                {t('fingerprint.results.cleanup')}
              </Button>
            </Toolbar>

            {idStatus.results.length === 0 ? (
              <div style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)', padding: '8px 0' }}>
                {t('fingerprint.results.noResults')}
              </div>
            ) : (
              <div style={{ borderRadius: 6, border: '1px solid var(--lbb-border)', overflow: 'hidden' }}>
                <TableShell stickyHeader>
                  <thead>
                    <tr>
                      <TH>{t('fingerprint.results.yourFile')}</TH>
                      <TH>{t('fingerprint.results.bestMatch')}</TH>
                      <TH>{t('fingerprint.results.location')}</TH>
                      <TH align="right">{t('fingerprint.results.score')}</TH>
                      <TH>{t('fingerprint.results.confident')}</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {idStatus.results.map((res, i) => {
                      const best = res.candidates[0]
                      const tone = best?.confident ? 'ok' : best ? 'warn' : 'mute'
                      return (
                        <TR key={i} edge={tone}>
                          <TD mono dim>{res.user_file}</TD>
                          <TD mono>
                            {best
                              ? `LB-${String(best.lb_number).padStart(5, '0')}`
                              : <span style={{ color: 'var(--lbb-fg3)' }}>{t('fingerprint.results.noMatch')}</span>}
                          </TD>
                          <TD>{best ? (lbLocationMap[best.lb_number] || '—') : '—'}</TD>
                          <TD align="right" mono>{best ? best.score : '—'}</TD>
                          <TD>
                            {best && (
                              <Pill tone={best.confident ? 'ok' : 'warn'} soft dot>
                                {best.confident ? t('fingerprint.results.yes') : t('fingerprint.results.no')}
                              </Pill>
                            )}
                          </TD>
                        </TR>
                      )
                    })}
                  </tbody>
                </TableShell>
              </div>
            )}

            {idStatus.errors.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-bad-fg)' }}>
                {t('fingerprint.results.errors', { count: idStatus.errors.length })}
              </div>
            )}
          </Card>
        )}

      </div>
    </div>
  )
}
