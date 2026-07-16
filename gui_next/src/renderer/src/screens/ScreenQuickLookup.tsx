import React, { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { formatXrefTag, XREF_TONE } from '../components/pipeline/lookupState'
import type { LookupSummaryRow } from '../lib/lookupStore'

const BASE = window.api.flaskBase

// ── Types ──────────────────────────────────────────────────────────────────────

// Per FABLE_XREF_INCORPORATION.md D1: copy-level xref is a dimension
// (`matched_xref > 0`), never a status — there is no "XREF" member here.
type RowStatus = 'matched' | 'incomplete' | 'notfound' | 'duplicate'

interface DetailRow {
  checksum: string
  filename: string
  lb_number: number | null
  status: string
  type?: string
  xref?: number
}

const STATUS_TONE: Record<RowStatus, { tone: 'ok' | 'warn' | 'bad' | 'info' | 'mute'; label: string }> = {
  matched:    { tone: 'ok',   label: 'Matched'    },
  incomplete: { tone: 'warn', label: 'Incomplete' },
  notfound:   { tone: 'bad',  label: 'Not found'  },
  duplicate:  { tone: 'warn', label: 'Duplicate'  },
}

function toRowStatus(status: string): RowStatus {
  if (status === 'MATCHED')               return 'matched'
  if (status === 'MATCHED (INCOMPLETE)')  return 'incomplete'
  if (status === 'INCOMPLETE')            return 'incomplete'
  if (status === 'NOT FOUND')             return 'notfound'
  if (status === 'DUPLICATE')             return 'duplicate'
  return 'notfound'
}

// ── Screen ─────────────────────────────────────────────────────────────────────

export function ScreenQuickLookup(): React.JSX.Element {
  const { t } = useTranslation()
  const [text, setText]       = useState('')
  const [rows, setRows]       = useState<DetailRow[]>([])
  // Copy-level xref (D4): lb_number → winning fileset id, populated from summary.lb_summary
  // alongside the per-checksum rows. Only entries with matched_xref > 0 are kept.
  const [xrefByLb, setXrefByLb] = useState<Map<number, number>>(new Map())
  const [busy, setBusy]       = useState(false)
  const [dragging, setDragging] = useState(false)
  const [toast, setToast]     = useState<string | null>(null)
  const toastTimer            = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const runLookup = useCallback(async (input: string) => {
    if (!input.trim()) return
    setBusy(true)
    try {
      const r = await fetch(`${BASE}/api/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: input }),
      })
      const d = await r.json() as { detail: DetailRow[]; summary?: { lb_summary: LookupSummaryRow[] } }
      setRows(d.detail ?? [])
      const xrefMap = new Map<number, number>()
      for (const s of d.summary?.lb_summary ?? []) {
        if (s.matched_xref > 0) xrefMap.set(s.lb_number, s.matched_xref)
      }
      setXrefByLb(xrefMap)
    } catch {
      showToast(t('quickLookup.toast.failed'))
    } finally {
      setBusy(false)
    }
  }, [showToast, t])

  const handleClipboard = useCallback(async () => {
    try {
      const content = await navigator.clipboard.readText()
      if (!content.trim()) { showToast(t('quickLookup.toast.clipboardEmpty')); return }
      setText(content)
      runLookup(content)
    } catch {
      showToast(t('quickLookup.toast.clipboardFailed'))
    }
  }, [runLookup, showToast, t])

  const readFileList = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files).filter(f => /\.(md5|ffp|st5|sha1|txt)$/i.test(f.name))
    if (!arr.length) { showToast(t('quickLookup.toast.noValidFiles')); return }
    const readers = arr.map(
      f => new Promise<string>(res => {
        const fr = new FileReader()
        fr.onload = () => res(fr.result as string)
        fr.readAsText(f)
      })
    )
    Promise.all(readers).then(contents => {
      const combined = contents.join('\n')
      setText(combined)
      runLookup(combined)
    })
  }, [runLookup, showToast, t])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    readFileList(e.dataTransfer.files)
  }, [readFileList])

  const handleFileBtn = useCallback(async () => {
    const files = await window.api.pickAndReadFiles({
      title: t('quickLookup.filePicker.title'),
      filters: [
        { name: 'Checksum files', extensions: ['md5', 'ffp', 'st5', 'sha1', 'txt'] },
        { name: 'All files', extensions: ['*'] },
      ],
    })
    if (!files.length) return
    const combined = files.map(f => f.content).join('\n')
    setText(combined)
    runLookup(combined)
  }, [runLookup, t])

  const handleClear = useCallback(() => { setText(''); setRows([]); setXrefByLb(new Map()) }, [])

  const matchedCount = rows.filter(r => toRowStatus(r.status) === 'matched').length

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="lookup" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
              {t('quickLookup.title')}
            </h1>
            <Pill tone="mute" soft>{t('quickLookup.subtitle')}</Pill>
          </div>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('quickLookup.desc')}
          </div>
        </div>
        {rows.length > 0 && (
          <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', fontFamily: 'var(--lbb-mono)' }}>
            {matchedCount} / {rows.length} {t('quickLookup.header.matched')}
          </span>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Left: input panel */}
        <aside style={{
          width: 300, flex: '0 0 300px',
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', padding: 16, gap: 10, minHeight: 0,
        }}>
          <div style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
            {t('quickLookup.input.label')}
          </div>

          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={t('quickLookup.input.placeholder')}
            style={{
              flex: 1, minHeight: 100, resize: 'none',
              fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', lineHeight: 1.55,
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              borderRadius: 6, padding: '8px 10px', color: 'var(--lbb-fg)',
            }}
          />

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${dragging ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
              borderRadius: 8, padding: '12px 8px', textAlign: 'center',
              background: dragging ? 'var(--lbb-accent-soft)' : 'transparent',
              color: dragging ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
              fontSize: 'var(--lbb-fs-11)', transition: 'all 0.15s', cursor: 'default',
            }}
          >
            <Icon name="drop" size={16} style={{ display: 'block', margin: '0 auto 4px' }} />
            {t('quickLookup.drop.hint')}
            <span style={{ display: 'block', fontSize: 'var(--lbb-fs-10)', marginTop: 2, color: 'var(--lbb-fg3)' }}>
              {t('quickLookup.drop.ext')}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <Button variant="secondary" size="sm" icon="copy"        block disabled={busy} onClick={handleClipboard}>
              {t('quickLookup.btn.clipboard')}
            </Button>
            <Button variant="secondary" size="sm" icon="attachments" block disabled={busy} onClick={handleFileBtn}>
              {t('quickLookup.btn.files')}
            </Button>
          </div>

          <Button variant="primary" size="sm" icon="lookup" block disabled={busy || !text.trim()} onClick={() => runLookup(text)}>
            {busy ? t('quickLookup.btn.running') : t('quickLookup.btn.lookup')}
          </Button>

          {rows.length > 0 && (
            <Button variant="ghost" size="sm" icon="x" block onClick={handleClear}>
              {t('quickLookup.btn.clear')}
            </Button>
          )}
        </aside>

        {/* Right: results */}
        <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'auto' }}>
          {rows.length === 0 ? (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              gap: 8, color: 'var(--lbb-fg3)',
            }}>
              <Icon name="lookup" size={32} style={{ opacity: 0.12 }} />
              <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg2)' }}>
                {t('quickLookup.empty.title')}
              </span>
              <span style={{ fontSize: 'var(--lbb-fs-11-5)' }}>
                {t('quickLookup.empty.desc')}
              </span>
            </div>
          ) : (
            <TableShell stickyHeader>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 160 }} />
                <col />
                <col style={{ width: 120 }} />
                <col style={{ width: 160 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH> </TH>
                  <TH>{t('quickLookup.table.checksum')}</TH>
                  <TH>{t('quickLookup.table.filename')}</TH>
                  <TH>{t('quickLookup.table.lb')}</TH>
                  <TH>{t('quickLookup.table.status')}</TH>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const st   = toRowStatus(r.status)
                  const info = STATUS_TONE[st]
                  const lbStr = r.lb_number !== null
                    ? `LB-${String(r.lb_number).padStart(5, '0')}`
                    : '—'
                  const matchedXref = r.lb_number !== null ? xrefByLb.get(r.lb_number) : undefined
                  return (
                    <TR key={i} edge={info.tone === 'mute' ? undefined : info.tone}>
                      <TD mono dim>{r.checksum.slice(0, 12)}…</TD>
                      <TD mono style={{ color: 'var(--lbb-fg)' }}>{r.filename}</TD>
                      <TD mono style={{
                        color: r.lb_number !== null ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg3)',
                        fontWeight: r.lb_number !== null ? 600 : 400,
                      }}>
                        {lbStr}
                      </TD>
                      <TD>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          <Pill tone={info.tone} soft dot={st !== 'matched'}>{info.label}</Pill>
                          {matchedXref !== undefined && (
                            <Pill tone={XREF_TONE.tone} soft title={t('quickLookup.xrefPill', { id: formatXrefTag(matchedXref) })}>
                              {formatXrefTag(matchedXref)}
                            </Pill>
                          )}
                        </div>
                      </TD>
                    </TR>
                  )
                })}
              </tbody>
            </TableShell>
          )}
        </section>
      </div>

      {toast && (
        <div style={{
          position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--lbb-accent-mid)', color: '#fff',
          padding: '9px 18px', borderRadius: 8,
          fontSize: 'var(--lbb-fs-13)', fontWeight: 600, zIndex: 9999,
          boxShadow: '0 4px 16px rgba(0,0,0,.25)', pointerEvents: 'none',
        }}>
          {toast}
        </div>
      )}
    </div>
  )
}
