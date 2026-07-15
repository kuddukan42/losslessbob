import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { Button, Chip, IconButton, Input, Pill } from '../components'
import { FolderQueueRail } from '../components/FolderQueueRail'
import { useSpectrogramStore, SpectroTrack } from '../lib/spectrogramStore'
import { useFolderQueueStore } from '../lib/folderQueueStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

type ToastTone = 'ok' | 'bad' | 'info'

interface ToolStatus {
  sox_available:    boolean
  sox_version:      string | null
  ffmpeg_available: boolean
}

interface GenerateStatus {
  status:          string
  current:         string | null
  done:            number
  total:           number
  errors:          number
  skipped:         number
  stop_requested:  boolean
}

// ── Atoms ──────────────────────────────────────────────────────────────────────

function ToolDot({ ok, label }: { ok: boolean; label: string }): React.JSX.Element {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: ok ? 'var(--lbb-ok-bar)' : 'var(--lbb-bad-fg)' }} />
      {label}
    </span>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenSpectrograms(): React.JSX.Element {
  const {
    activeFolder, inventory, activeTrack, filter, width, height, dynRange, forceRerender, zoom,
    setActiveFolder, setInventory, setActiveTrack, setFilter,
    setWidth, setHeight, setDynRange, setForceRerender, setZoom, takePending,
  } = useSpectrogramStore()
  const { folders, addFolders } = useFolderQueueStore()
  const [tools,      setTools]      = useState<ToolStatus | null>(null)
  const [genStatus,  setGenStatus]  = useState<GenerateStatus | null>(null)
  const [generating, setGenerating] = useState(false)
  const [toast,      setToast]      = useState<{ msg: string; tone: ToastTone } | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  // Load tool status on mount; drain any folders queued from other screens
  useEffect(() => {
    fetch(`${BASE}/api/spectrogram/check`)
      .then(r => r.json())
      .then((d: ToolStatus) => setTools(d))
      .catch(() => {})
    const pending = takePending()
    if (pending.length) {
      addFolders(pending)
      if (!useSpectrogramStore.getState().activeFolder) setActiveFolder(pending[0])
    }
    return () => stopPoll()
  }, [stopPoll, takePending])

  // Reset activeFolder when it's been removed from the shared queue (e.g. cleared on another screen)
  useEffect(() => {
    if (activeFolder && !folders.includes(activeFolder)) setActiveFolder(null)
  }, [folders, activeFolder, setActiveFolder])

  const startPoll = useCallback(() => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${BASE}/api/spectrogram/status`)
        const d = await r.json() as GenerateStatus
        setGenStatus(d)
        if (d.status !== 'running') {
          stopPoll()
          setGenerating(false)
          if (d.status === 'done') showToast(`Done — ${d.done} generated, ${d.errors} errors`, d.errors > 0 ? 'info' : 'ok')
        }
      } catch { stopPoll() }
    }, 800)
  }, [stopPoll, showToast])

  const loadInventory = useCallback(async (folderList?: string[]) => {
    const f = folderList ?? folders
    if (!f.length) return
    try {
      const r = await fetch(`${BASE}/api/spectrogram/list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: f }),
      })
      const d = await r.json() as Record<string, SpectroTrack[]>
      setInventory(d)
      if (activeFolder && d[activeFolder]) {
        setActiveTrack(d[activeFolder][0] ?? null)
      }
    } catch {
      showToast('Inventory scan failed', 'bad')
    }
  }, [folders, activeFolder, showToast])

  const handleAddFolder = useCallback(async () => {
    const picked = await window.api.pickFolders()
    if (!picked.length) return
    addFolders(picked)
    if (!activeFolder) setActiveFolder(picked[0])
    await loadInventory([...new Set([...folders, ...picked])])
  }, [folders, activeFolder, loadInventory, addFolders, setActiveFolder])

  const handleGenerate = useCallback(async (singleFolder?: string) => {
    const target = singleFolder ? [singleFolder] : folders
    if (!target.length) { showToast('Add folders first', 'info'); return }
    try {
      await fetch(`${BASE}/api/spectrogram/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folders: target,
          width: parseInt(width) || 1500,
          height: parseInt(height) || 400,
          dyn_range: Math.abs(parseInt(dynRange) || 120),
          force: singleFolder ? true : forceRerender,
        }),
      })
      setGenerating(true)
      startPoll()
    } catch {
      showToast('Generate failed', 'bad')
    }
  }, [folders, width, height, dynRange, forceRerender, startPoll, showToast])

  const handleStop = useCallback(async () => {
    await fetch(`${BASE}/api/spectrogram/stop`, { method: 'POST' })
      .catch(() => showToast('Stop failed', 'bad'))
  }, [showToast])

  const handleRescan = useCallback(async () => {
    await loadInventory()
  }, [loadInventory])

  const activeTracks = activeFolder ? (inventory[activeFolder] ?? []) : []
  const filteredFolders = filter
    ? folders.filter(f => f.toLowerCase().includes(filter.toLowerCase()))
    : folders

  const pngUrl = activeTrack?.png_path
    ? `${BASE}/api/spectrogram/png?path=${encodeURIComponent(activeTrack.png_path)}`
    : null

  const totalTracks = folders.reduce((n, f) => n + (inventory[f]?.length ?? 0), 0)
  const totalDone   = folders.reduce((n, f) => n + (inventory[f]?.filter(t => t.has_png).length ?? 0), 0)
  const totalMissing = totalTracks - totalDone

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="spectro" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>Spectrograms</h1>
            <Pill tone="mute" soft>SoX batch render</Pill>
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            Per-track PNG spectrograms. Used to spot upsamples, EQ tells, and dropouts.
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 14, padding: '0 12px', borderRight: '1px solid var(--lbb-border)' }}>
          <ToolDot ok={!!tools?.sox_available} label={tools?.sox_version ? `SoX ${tools.sox_version}` : 'SoX'} />
          <ToolDot ok={!!tools?.ffmpeg_available} label="ffmpeg" />
        </div>
        <Button variant="ghost" size="sm" icon="folderPlus" onClick={handleAddFolder}>Add folder…</Button>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Folder rail */}
        <FolderQueueRail
          label="Folders"
          filter={filter}
          onFilterChange={setFilter}
          filterPlaceholder="Filter folders…"
          width={300}
          onClear={() => { setActiveFolder(null); setActiveTrack(null) }}
          footer={<>
            <div style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 8 }}>
              {generating && genStatus ? `Batch · ${genStatus.done} / ${genStatus.total}` : `Batch · ${totalDone} / ${totalTracks} tracks`}
            </div>
            {totalTracks > 0 && (
              <>
                <div className="lbb-prog">
                  <div style={{ width: generating && genStatus
                    ? `${genStatus.total > 0 ? Math.round(genStatus.done / genStatus.total * 100) : 0}%`
                    : `${totalTracks > 0 ? Math.round(totalDone / totalTracks * 100) : 0}%`
                  }} />
                </div>
                {genStatus && generating && (
                  <div style={{ marginTop: 4, fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {genStatus.current ?? '—'}
                  </div>
                )}
                {genStatus && (
                  <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>
                    <span><Icon name="check" size={10} style={{ color: 'var(--lbb-ok-bar)' }} /> {genStatus.done} done</span>
                    <span>· {genStatus.skipped} skipped</span>
                    <span>· {genStatus.errors} errors</span>
                  </div>
                )}
              </>
            )}
            <div style={{ marginTop: totalTracks > 0 ? 10 : 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Button variant="primary"   size="sm" icon="play"    block disabled={generating || !folders.length}
                onClick={() => handleGenerate()}>
                {generating ? 'Generating…' : `Generate missing (${totalMissing})`}
              </Button>
              <Button variant="secondary" size="sm" icon="pause"   block disabled={!generating} onClick={handleStop}>
                Stop after current
              </Button>
              <Button variant="ghost"     size="sm" icon="refresh" block disabled={!folders.length} onClick={handleRescan}>
                Re-scan inventory
              </Button>
            </div>
          </>}
        >
          {filteredFolders.length === 0 ? (
            <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
              {folders.length === 0 ? 'No folders added' : 'No matches'}
            </div>
          ) : filteredFolders.map(f => {
            const tracks = inventory[f] ?? []
            const done   = tracks.filter(t => t.has_png).length
            const name   = f.split('/').pop() ?? f
            const pct    = tracks.length ? Math.round(done / tracks.length * 100) : 0
            return (
              <button key={f} onClick={() => { setActiveFolder(f); setActiveTrack(tracks[0] ?? null) }} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 10px', marginBottom: 1, borderRadius: 6,
                background: f === activeFolder ? 'var(--lbb-accent-soft)' : 'transparent',
                color: f === activeFolder ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                border: '1px solid ' + (f === activeFolder ? 'var(--lbb-accent-line)' : 'transparent'),
                textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
              }}>
                <Icon name="folder" size={11} style={{ color: 'var(--lbb-fg3)' }} />
                <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
                  <span style={{ fontSize: 'var(--lbb-fs-10)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
                    {tracks.length ? `${done}/${tracks.length} · ${pct}%` : 'not scanned'}
                  </span>
                </span>
              </button>
            )
          })}
        </FolderQueueRail>

        {/* Track + viewer */}
        {!activeFolder ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--lbb-fg3)' }}>
            <Icon name="spectro" size={36} style={{ opacity: 0.15 }} />
            <span style={{ fontSize: 'var(--lbb-fs-13)' }}>Add a folder to get started</span>
          </div>
        ) : (
          <section style={{ flex: 1, display: 'grid', gridTemplateColumns: '260px 1fr', minHeight: 0 }}>

            {/* Track rail */}
            <aside style={{
              background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
              display: 'flex', flexDirection: 'column', minHeight: 0,
            }}>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--lbb-border)', flexShrink: 0 }}>
                <div style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>
                  {activeFolder.split('/').pop()}
                </div>
                <div style={{ marginTop: 4, fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>
                  {activeTracks.filter(t => t.has_png).length} / {activeTracks.length} tracks rendered
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
                {activeTracks.length === 0 ? (
                  <div style={{ padding: '24px 10px', textAlign: 'center', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-11)' }}>
                    Click Re-scan inventory to load tracks
                  </div>
                ) : activeTracks.map((t, i) => (
                  <button key={i} onClick={() => setActiveTrack(t)} style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 8px', marginBottom: 1, borderRadius: 6,
                    background: activeTrack?.audio_file === t.audio_file ? 'var(--lbb-accent-soft)' : 'transparent',
                    color: activeTrack?.audio_file === t.audio_file ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                    border: '1px solid ' + (activeTrack?.audio_file === t.audio_file ? 'var(--lbb-accent-line)' : 'transparent'),
                    textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
                  }}>
                    <span style={{
                      width: 22, height: 22, borderRadius: 4,
                      background: activeTrack?.audio_file === t.audio_file ? 'var(--lbb-accent-mid)' : 'var(--lbb-surface2)',
                      color: activeTrack?.audio_file === t.audio_file ? 'var(--lbb-accent-onMid)' : 'var(--lbb-fg3)',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontFamily: 'var(--lbb-mono)', fontWeight: 700, fontSize: 'var(--lbb-fs-10)',
                    }}>{String(i + 1).padStart(2, '0')}</span>
                    <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.audio_name}
                    </span>
                    {t.has_png
                      ? <Pill tone="ok"   soft style={{ fontSize: 'var(--lbb-fs-9)', padding: '0 4px' }}>PNG</Pill>
                      : <Pill tone="mute" soft style={{ fontSize: 'var(--lbb-fs-9)', padding: '0 4px' }}>—</Pill>}
                  </button>
                ))}
              </div>

              {/* Render options */}
              <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)', flexShrink: 0 }}>
                <div style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase', marginBottom: 8 }}>
                  Render options
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr', gap: '6px 8px', fontSize: 'var(--lbb-fs-11-5)', alignItems: 'center' }}>
                  <span style={{ color: 'var(--lbb-fg3)' }}>Width</span>
                  <Input size="sm" value={width} onChange={e => setWidth(e.target.value)} style={{ width: '100%' }} />
                  <span style={{ color: 'var(--lbb-fg3)' }}>Height</span>
                  <Input size="sm" value={height} onChange={e => setHeight(e.target.value)} style={{ width: '100%' }} />
                  <span style={{ color: 'var(--lbb-fg3)' }}>dB range</span>
                  <Input size="sm" value={dynRange} onChange={e => setDynRange(e.target.value)} style={{ width: '100%' }} />
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)', marginTop: 8 }}>
                  <input type="checkbox" checked={forceRerender} onChange={e => setForceRerender(e.target.checked)} /> Force re-render
                </label>
              </div>
            </aside>

            {/* Spectrogram viewer */}
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>

              {/* Toolbar */}
              <div style={{
                padding: '10px 20px', borderBottom: '1px solid var(--lbb-border)',
                display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
              }}>
                <div style={{ flex: 1 }} />
                <IconButton icon="x"    title="Zoom out" onClick={() => setZoom(z => Math.max(25,  z - 25))} />
                <span style={{ fontSize: 'var(--lbb-fs-11)', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg2)', width: 50, textAlign: 'center' }}>{zoom}%</span>
                <IconButton icon="plus" title="Zoom in"  onClick={() => setZoom(z => Math.min(400, z + 25))} />
                <Button variant="ghost" size="sm" onClick={() => setZoom(100)}>Fit</Button>
                <span style={{ width: 1, height: 18, background: 'var(--lbb-border)', margin: '0 4px' }} />
                {activeTrack?.png_path && (
                  <Button variant="ghost" size="sm" icon="reveal" onClick={() => window.api.openPath(activeTrack.png_path!)}>Open PNG</Button>
                )}
                <Button variant="primary" size="sm" icon="play" disabled={generating || !activeFolder}
                  onClick={() => activeFolder && handleGenerate(activeFolder)}>
                  Re-render folder
                </Button>
              </div>

              <div style={{ flex: 1, overflow: 'auto', padding: 20, background: 'var(--lbb-surface2)' }}>
                {!activeTrack ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-13)' }}>
                    Select a track
                  </div>
                ) : !activeTrack.has_png || !pngUrl ? (
                  <div style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    height: 200, gap: 12, color: 'var(--lbb-fg3)',
                  }}>
                    <Icon name="spectro" size={32} style={{ opacity: 0.2 }} />
                    <span style={{ fontSize: 'var(--lbb-fs-13)' }}>No spectrogram yet</span>
                    <Button variant="primary" size="sm" disabled={generating} onClick={() => activeFolder && handleGenerate(activeFolder)}>Generate</Button>
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', marginBottom: 8, fontFamily: 'var(--lbb-mono)' }}>
                      {activeTrack.audio_name}
                    </div>
                    <div style={{ overflow: 'auto' }}>
                      <img
                        src={pngUrl}
                        alt={activeTrack.audio_name}
                        style={{
                          display: 'block',
                          maxWidth: zoom === 100 ? '100%' : undefined,
                          width: zoom !== 100 ? `${zoom}%` : undefined,
                          borderRadius: 4, border: '1px solid var(--lbb-border)',
                        }}
                      />
                    </div>

                    {/* Thumbnail strip */}
                    {activeTracks.filter(t => t.has_png).length > 1 && (
                      <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
                        {activeTracks.filter(t => t.has_png).slice(0, 8).map((t, i) => (
                          <button key={i} onClick={() => setActiveTrack(t)} style={{
                            background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
                          }}>
                            <img
                              src={`${BASE}/api/spectrogram/png?path=${encodeURIComponent(t.png_path!)}`}
                              alt={t.audio_name}
                              style={{
                                width: '100%', height: 60, objectFit: 'cover', borderRadius: 4,
                                border: t.audio_file === activeTrack?.audio_file
                                  ? '2px solid var(--lbb-accent-mid)'
                                  : '1px solid var(--lbb-border)',
                              }}
                            />
                            <div style={{ fontSize: 'var(--lbb-fs-9-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', marginTop: 2, textAlign: 'center' }}>
                              {t.audio_name.split('.')[0]}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      {toast && (
        <div
          style={{
            position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
            background: toast.tone === 'ok' ? 'var(--lbb-ok-bar)' : toast.tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)',
            color: '#fff', padding: '9px 18px', borderRadius: 8,
            fontSize: 'var(--lbb-fs-13)', fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
            pointerEvents: 'none',
          }}
          ref={(el: HTMLDivElement | null) => { if (el) setTimeout(() => setToast(null), 3500) }}
        >{toast.msg}</div>
      )}
    </div>
  )
}
