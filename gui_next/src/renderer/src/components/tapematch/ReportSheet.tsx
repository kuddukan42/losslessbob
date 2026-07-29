/**
 * §11 — the `report.md` overlay for the TapeMatch curation screen (Phase 7).
 *
 * Sources of truth, in the WORK_PACKAGE's precedence order: DESIGN_ANSWERS A1
 * (the `## tapematch output` fence renders as one collapsible panel per
 * `=== MARKER ===`), A2 (the outline rail nests those markers, carries counts
 * only where a count means something, and never shows an absent section), A3
 * (Coverage's summary line is a stat row; not-on-disk rows are a warn variant,
 * not a grey one), then README §11 for the shell, the LB chips, the clickable
 * rows and the judgment annotation, and §11.1 for print.
 *
 * The document is read-only — it is a generated artifact. What this view adds
 * over an editor is the two things §11 names: it links every LB number and
 * every audit row back into the workspace, and it marks where the curator's
 * judgments have moved on from what the report claims.
 *
 * Parsing lives in `lib/reportMd.ts`; prose bodies go through `react-markdown`
 * (DECISIONS Q5) rather than being hand-rendered.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Pill } from '../primitives'
import { SheetShell } from './SheetShell'
import { Icon } from '../Icon'
import {
  lbsIn, outlineOf, panelDomId, parseReportMd,
  type AuditRow, type OutputPanel, type ReportDoc, type ReportSection,
} from '../../lib/reportMd'

const JUDGMENT_LABEL: Record<string, string> = {
  confirmed_same: 'Same source',
  confirmed_different: 'Different',
  uncertain: 'Uncertain',
  lb_wrong: 'LB wrong',
}
const JUDGMENT_TONE: Record<string, 'ok' | 'info' | 'warn' | 'bad'> = {
  confirmed_same: 'ok',
  confirmed_different: 'info',
  uncertain: 'warn',
  lb_wrong: 'bad',
}

/**
 * Does a judgment contradict what the report's audit row claimed?
 *
 * The generator writes AGREES/DISAGREES about the *LB page commentary* vs the
 * run's families, so "the report said these are the same source" is
 * `AGREES`. `uncertain` contradicts nothing — it is the absence of a claim.
 */
function judgmentDiffers(verdictWord: string, judgment: string): boolean {
  if (judgment === 'uncertain') return false
  const reportSaysSame = verdictWord === 'AGREES'
  if (judgment === 'confirmed_same') return !reportSaysSame
  if (judgment === 'confirmed_different') return reportSaysSame
  return false // lb_wrong is a claim about the LB page, not about the run
}

function pad5(lb: number): string {
  return String(lb).padStart(5, '0')
}

// ── LB chips ────────────────────────────────────────────────────────────────

function LbChip({
  lb, colorOf, onClick,
}: {
  lb: number
  colorOf: (lb: number) => string
  onClick: ((lb: number) => void) | null
}) {
  const inner = (
    <>
      <span style={{
        width: 6, height: 6, borderRadius: 2, background: colorOf(lb), flex: '0 0 auto',
      }} />
      LB-{pad5(lb)}
    </>
  )
  const base: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
    borderRadius: 4, padding: '1px 6px',
    font: '600 11px var(--lbb-mono)', color: 'var(--lbb-fg2)',
    verticalAlign: 'baseline',
  }
  if (!onClick) return <span className="rpLb" style={base}>{inner}</span>
  return (
    <button
      type="button"
      className="rpLb"
      onClick={() => onClick(lb)}
      title={`Select LB-${pad5(lb)} in the workspace`}
      style={{ ...base, cursor: 'pointer' }}
    >
      {inner}
    </button>
  )
}

/** Every `LB-#####` in a string becomes a chip; everything else stays text. */
function withChips(
  text: string,
  colorOf: (lb: number) => string,
  onLb: ((lb: number) => void) | null,
  keyPrefix: string,
): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const re = /LB-(\d{3,6})/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(
      <LbChip key={`${keyPrefix}-${i++}`} lb={Number(m[1])} colorOf={colorOf} onClick={onLb} />,
    )
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

// ── Section renderers ───────────────────────────────────────────────────────

const TH: React.CSSProperties = {
  font: '700 9.5px var(--lbb-font)', textTransform: 'uppercase', letterSpacing: '.07em',
  color: 'var(--lbb-fg3)', textAlign: 'left', padding: '0 9px 6px 0',
  borderBottom: '1px solid var(--lbb-border)', whiteSpace: 'nowrap',
}
const TD: React.CSSProperties = {
  padding: '7px 9px 7px 0', borderBottom: '1px solid var(--lbb-border)',
  color: 'var(--lbb-fg2)', verticalAlign: 'top',
}

/** A3 — the stat row, the table, and the closing line when a row is missing. */
function CoverageSection({
  section, colorOf, onLb,
}: {
  section: Extract<ReportSection, { kind: 'coverage' }>
  colorOf: (lb: number) => string
  onLb: (lb: number) => void
}) {
  const missing = section.rows.filter(r => !r.onDisk)
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap', margin: '10px 0 12px' }}>
        <Stat value={section.entries} label="DB entries" />
        <Stat value={section.found} label="found on disk" />
        {missing.length > 0 && (
          <span className="rpWarn" style={{ fontSize: 11.5, color: 'var(--lbb-warn-fg)' }}>
            {missing.length} not on disk — {missing.map(r => r.lb ? `LB-${pad5(r.lb)}` : '?').join(', ')}
          </span>
        )}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="rpTable" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
          <thead>
            <tr>
              <th style={TH}>LB</th><th style={TH}>Rating</th><th style={TH}>Timing</th>
              <th style={TH}>Source</th><th style={TH}>Folder</th>
            </tr>
          </thead>
          <tbody>
            {section.rows.map((r, i) => (
              <tr key={i} style={!r.onDisk ? {
                // A3 — a 2px warn bar groups the missing rows; the row itself
                // keeps full contrast, because it is the one to notice.
                boxShadow: 'inset 2px 0 0 var(--lbb-warn-bar)',
              } : undefined}>
                <td style={{ ...TD, whiteSpace: 'nowrap', paddingLeft: r.onDisk ? 0 : 8 }}>
                  {r.lb != null
                    ? <LbChip lb={r.lb} colorOf={colorOf} onClick={onLb} />
                    : <span style={{ color: 'var(--lbb-fg3)' }}>·</span>}
                  {!r.onDisk && (
                    <span style={{ marginLeft: 6 }}>
                      <Pill tone="warn" soft>not on disk</Pill>
                    </span>
                  )}
                </td>
                <td style={TD}>{r.rating || <Dim />}</td>
                <td style={TD}>{r.timing || <Dim />}</td>
                <td style={TD}>{r.source || <Dim />}</td>
                <td style={{ ...TD, color: r.onDisk ? 'var(--lbb-fg2)' : 'var(--lbb-warn-fg)' }}
                    className={r.onDisk ? undefined : 'rpWarn'}>
                  {r.onDisk ? r.folder : 'no folder found — DB entry only'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {missing.length > 0 && (
        <p style={{ margin: '10px 0 0', fontSize: 12, lineHeight: 1.6, color: 'var(--lbb-fg3)' }}>
          A not-on-disk row is a gap in the library, not a failure of this run — the DB knows
          the recording, the crawl never found audio for it.
        </p>
      )}
    </>
  )
}

function Dim() {
  return <span style={{ color: 'var(--lbb-fg3)' }}>·</span>
}

function Stat({ value, label }: { value: number | null; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 5 }}>
      <span style={{
        font: '700 12.5px var(--lbb-mono)', color: 'var(--lbb-fg)',
        fontVariantNumeric: 'tabular-nums',
      }}>{value ?? '—'}</span>
      <span style={{ fontSize: 10, color: 'var(--lbb-fg3)' }}>{label}</span>
    </span>
  )
}

/**
 * A1 — one collapsible monospace panel per `=== MARKER ===`, with its own
 * x-scroll. The lines never wrap and the scroll is trapped in the panel, so
 * the document column can't be dragged sideways by a 250-column diagnostic.
 */
function OutputPanelBlock({
  panel, domId, open, onToggle,
}: {
  panel: OutputPanel
  domId: string
  open: boolean
  onToggle: () => void
}) {
  const peek = panel.lines.find(l => l.trim())?.trim() ?? ''
  if (panel.inline) {
    return (
      <div id={domId} style={{
        display: 'flex', gap: 10, alignItems: 'baseline', padding: '6px 0',
        borderBottom: '1px solid var(--lbb-border)',
      }}>
        <span style={{ font: '700 10px var(--lbb-mono)', color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>
          {panel.label}
        </span>
        <span style={{ font: '500 10.5px var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>
          {tintTokens(peek)}
        </span>
      </div>
    )
  }
  return (
    <div id={domId} className="rpPanel" style={{ borderBottom: '1px solid var(--lbb-border)' }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '6px 0',
          background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left',
          color: 'var(--lbb-fg2)',
        }}
      >
        <Icon name={open ? 'chevDown' : 'chevRight'} size={11} />
        <span style={{ font: '700 10px var(--lbb-mono)', whiteSpace: 'nowrap' }}>{panel.label}</span>
        <span style={{ font: '500 10px var(--lbb-mono)', color: 'var(--lbb-fg3)', whiteSpace: 'nowrap' }}>
          {panel.lines.length} lines{panel.cols > 110 ? ` · ${panel.cols} cols` : ''}
        </span>
        {!open && (
          <span style={{
            font: '500 10px var(--lbb-mono)', color: 'var(--lbb-fg3)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0,
          }}>{peek}</span>
        )}
      </button>
      {open && (
        <div style={{
          overflowX: 'auto', overscrollBehaviorX: 'contain', paddingBottom: 8,
        }}>
          <pre style={{
            margin: 0, whiteSpace: 'pre', font: '500 10.5px/1.55 var(--lbb-mono)',
            color: 'var(--lbb-fg2)',
          }}>{panel.lines.map((l, i) => (
            <React.Fragment key={i}>{tintTokens(l)}{'\n'}</React.Fragment>
          ))}</pre>
        </div>
      )}
    </div>
  )
}

/**
 * A1 — bracketed tokens are tinted in place, inside the monospace, changing no
 * characters. Same vocabulary as A5: `[INCOMPLETE]` / `[LOW CONFIDENCE]` warn,
 * `[DISTINCT SOURCE]` info.
 */
function tintTokens(line: string): React.ReactNode {
  const re = /\[(INCOMPLETE|LOW CONFIDENCE|DISTINCT SOURCE)\]/g
  const out: React.ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) out.push(line.slice(last, m.index))
    const tone = m[1] === 'DISTINCT SOURCE' ? 'info' : 'warn'
    out.push(
      <span key={i++} className={tone === 'warn' ? 'rpWarn' : undefined}
            style={{ color: `var(--lbb-${tone}-fg)`, fontWeight: 600 }}>{m[0]}</span>,
    )
    last = m.index + m[0].length
  }
  if (last < line.length) out.push(line.slice(last))
  return out.length ? out : line
}

/** §11 — the audit table's rows are clickable, and carry the judgment layer. */
function AuditSection({
  section, colorOf, onLb, onOpenPair, judgmentFor, pairExists,
}: {
  section: Extract<ReportSection, { kind: 'audit' }>
  colorOf: (lb: number) => string
  onLb: (lb: number) => void
  onOpenPair: (a: number, b: number) => void
  judgmentFor: (a: number, b: number) => string | null
  pairExists: (a: number, b: number) => boolean
}) {
  return (
    <>
      <p style={{ margin: '8px 0 10px', fontSize: 12, lineHeight: 1.6, color: 'var(--lbb-fg3)' }}>
        Rows are clickable — each opens its pair's dossier in the workspace.
      </p>
      <table className="rpTable" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
        <thead>
          <tr><th style={TH}>Pair</th><th style={TH}>Verdict</th><th style={TH}>Commentary snippet</th></tr>
        </thead>
        <tbody>
          {section.rows.map((r, i) => (
            <AuditRowBlock
              key={i} row={r} colorOf={colorOf} onLb={onLb} onOpenPair={onOpenPair}
              judgmentFor={judgmentFor} pairExists={pairExists}
            />
          ))}
        </tbody>
      </table>
    </>
  )
}

function AuditRowBlock({
  row, colorOf, onLb, onOpenPair, judgmentFor, pairExists,
}: {
  row: AuditRow
  colorOf: (lb: number) => string
  onLb: (lb: number) => void
  onOpenPair: (a: number, b: number) => void
  judgmentFor: (a: number, b: number) => string | null
  pairExists: (a: number, b: number) => boolean
}) {
  // Only a two-LB row names one pair; anything else has nothing to open.
  const openable = row.lbs.length === 2 && pairExists(row.lbs[0], row.lbs[1])
  const judgment = openable ? judgmentFor(row.lbs[0], row.lbs[1]) : null
  const differs = judgment ? judgmentDiffers(row.verdictWord, judgment) : false
  const tone = row.verdictWord === 'DISAGREES' ? 'bad' : row.verdictWord === 'AGREES' ? 'ok' : 'mute'
  return (
    <>
      <tr
        className={openable ? 'click' : undefined}
        onClick={openable ? () => onOpenPair(row.lbs[0], row.lbs[1]) : undefined}
        style={openable ? { cursor: 'pointer' } : undefined}
      >
        <td style={{ ...TD, whiteSpace: 'nowrap', borderBottom: judgment ? 'none' : TD.borderBottom }}>
          {row.lbs.map((lb, i) => (
            <React.Fragment key={lb}>
              {i > 0 && <span style={{ color: 'var(--lbb-fg3)', margin: '0 4px' }}>/</span>}
              <LbChip lb={lb} colorOf={colorOf} onClick={onLb} />
            </React.Fragment>
          ))}
        </td>
        <td style={{ ...TD, borderBottom: judgment ? 'none' : TD.borderBottom }}>
          <Pill tone={tone} soft>{row.verdictWord || 'verdict'}</Pill>
          <span style={{ marginLeft: 6, color: 'var(--lbb-fg3)' }}>
            {row.verdict.replace(/^[A-Z]+\s*—?\s*/, '')}
          </span>
        </td>
        <td style={{ ...TD, borderBottom: judgment ? 'none' : TD.borderBottom }}>{row.snippet}</td>
      </tr>
      {judgment && (
        <tr>
          <td colSpan={3} style={{ ...TD, paddingTop: 0 }}>
            {/* The dashed border marks content that is NOT part of the
                generated file — the report is a snapshot, judgments came
                after it. */}
            <div className={differs ? 'rpJudge differs' : 'rpJudge'} style={{
              display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
              background: differs ? 'var(--lbb-bad-bg)' : 'var(--lbb-surface2)',
              border: `1px dashed ${differs ? 'var(--lbb-bad-bar)' : 'var(--lbb-border2)'}`,
              borderRadius: 6, padding: '7px 11px',
              color: differs ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg2)',
            }}>
              <span style={{
                font: '700 9.5px var(--lbb-font)', textTransform: 'uppercase',
                letterSpacing: '.07em', color: 'var(--lbb-fg3)',
              }}>Your judgment</span>
              <Pill tone={JUDGMENT_TONE[judgment] ?? 'mute'} soft>
                {JUDGMENT_LABEL[judgment] ?? judgment}
              </Pill>
              {differs && <span>— differs from the report</span>}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── The sheet ───────────────────────────────────────────────────────────────

export interface ReportSheetProps {
  date: string
  runId: string | null
  runDir: string | null
  /** The file's text; null once loading finished and no report.md exists. */
  md: string | null
  loading: boolean
  error: boolean
  /** Non-null `human_judgment` count for the date — drives the stale banner. */
  judgedCount: number
  judgmentFor: (a: number, b: number) => string | null
  pairExists: (a: number, b: number) => boolean
  colorOf: (lb: number) => string
  onClose: () => void
  onOpenPair: (a: number, b: number) => void
  onSelectLb: (lb: number) => void
}

export function ReportSheet(props: ReportSheetProps): React.JSX.Element {
  const {
    date, runId, runDir, md, loading, error, judgedCount,
    judgmentFor, pairExists, colorOf, onClose, onOpenPair, onSelectLb,
  } = props

  const [mode, setMode] = useState<'rendered' | 'raw'>('rendered')
  const [copied, setCopied] = useState(false)
  const docRef = useRef<HTMLDivElement>(null)
  const [activeId, setActiveId] = useState<string | null>(null)

  const doc: ReportDoc | null = useMemo(() => md ? parseReportMd(md) : null, [md])
  const outline = useMemo(() => doc ? outlineOf(doc) : [], [doc])

  // A1 — DIAGNOSTICS and CLUSTERS open; everything else is provenance you go
  // looking for. Keyed by DOM id so `Expand all` and the rail agree.
  const [openPanels, setOpenPanels] = useState<Record<string, boolean>>({})
  useEffect(() => {
    if (!doc) return
    const next: Record<string, boolean> = {}
    for (const s of doc.sections) {
      if (s.kind !== 'output') continue
      for (const p of s.panels) next[panelDomId(s.id, p.label)] = p.openByDefault
    }
    setOpenPanels(next)
  }, [doc])

  // Esc, the focus trap and open-focus now live in SheetShell (D18); the
  // caller still restores focus to `Open report.md` on close.

  // §11 — clicking an outline entry sets scrollTop by offset arithmetic, never
  // scrollIntoView (which would scroll the app shell behind the overlay too).
  const scrollTo = (id: string) => {
    const box = docRef.current
    const el = box?.querySelector<HTMLElement>(`[id="${CSS.escape(id)}"]`)
    if (!box || !el) return
    box.scrollTop = el.offsetTop - box.offsetTop - 14
    setActiveId(id)
  }

  const copy = async () => {
    if (!md) return
    try {
      await navigator.clipboard.writeText(md)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard unavailable — the raw view is still selectable */ }
  }

  const download = () => {
    if (!md) return
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${date}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  // A1 — a collapsed panel must never reach the PDF: expand everything before
  // the print snapshot, and leave it expanded (the curator can see what was
  // printed rather than the view silently reverting under them).
  useEffect(() => {
    const onBeforePrint = () => setOpenPanels(prev => {
      const next: Record<string, boolean> = {}
      for (const k of Object.keys(prev)) next[k] = true
      return next
    })
    window.addEventListener('beforeprint', onBeforePrint)
    return () => window.removeEventListener('beforeprint', onBeforePrint)
  }, [])

  const actions = (
    <>
      <div className="rpSeg" style={{
        display: 'flex', background: 'var(--lbb-surface3)',
        border: '1px solid var(--lbb-border)', borderRadius: 6, padding: 2,
      }}>
        {(['rendered', 'raw'] as const).map(m => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            style={{
              border: 'none', borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              font: '600 11px var(--lbb-font)',
              background: mode === m ? 'var(--lbb-surface)' : 'transparent',
              color: mode === m ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
            }}
          >{m === 'rendered' ? 'Rendered' : 'Raw'}</button>
        ))}
      </div>
      <Button variant="ghost" size="sm" onClick={copy} disabled={!md}>
        {copied ? 'Copied' : 'Copy'}
      </Button>
      <Button variant="ghost" size="sm" onClick={download} disabled={!md}>Download</Button>
      <Button variant="ghost" size="sm" onClick={() => window.print()} disabled={!md}>
        Print
      </Button>
      <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close report">✕</Button>
    </>
  )

  const banner = (
    // §11 stale banner — only when judgments exist. No `Regenerate`: the
    // standing constraint is no generator change, and a button that can't
    // regenerate is worse than the sentence alone.
    judgedCount > 0 && md ? (
          <div className="rpStale" style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
            background: 'var(--lbb-warn-bg)', color: 'var(--lbb-warn-fg)',
            borderBottom: '1px solid var(--lbb-warn-bar)', fontSize: 11.5, flex: '0 0 auto',
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--lbb-warn-bar)' }} />
            {judgedCount} human judgment{judgedCount === 1 ? '' : 's'} recorded since this report
            was generated — it doesn&rsquo;t reflect them yet.
          </div>
    ) : null
  )

  const rail = (
    <>
            <div style={{
              font: '700 9.5px var(--lbb-font)', textTransform: 'uppercase',
              letterSpacing: '.07em', color: 'var(--lbb-fg3)', padding: '0 7px 6px',
            }}>Contents</div>
            {mode === 'raw' ? (
              <div style={{ padding: '0 7px', fontSize: 11, color: 'var(--lbb-fg3)' }}>
                Switch to Rendered to navigate.
              </div>
            ) : outline.map(e => (
              <button
                key={e.id}
                type="button"
                onClick={() => scrollTo(e.id)}
                title={e.label}
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 6, width: '100%',
                  padding: e.sub ? '4px 7px 4px 18px' : '5px 7px', borderRadius: 5,
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                  font: `${e.sub ? 500 : 600} ${e.sub ? 10.5 : 11.5}px var(--lbb-font)`,
                  fontFamily: e.sub ? 'var(--lbb-mono)' : 'var(--lbb-font)',
                  background: activeId === e.id ? 'var(--lbb-accent-soft)' : 'transparent',
                  color: activeId === e.id ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                }}
              >
                <span style={{
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0,
                }}>{e.label}</span>
                {/* A2 — no dash, no `n/a`: where a count has no meaning the
                    slot is simply empty. */}
                {e.count != null && (
                  <span style={{
                    marginLeft: 'auto', font: '500 10px var(--lbb-mono)', color: 'var(--lbb-fg3)',
                  }}>{e.count}</span>
                )}
              </button>
            ))}
    </>
  )

  const body = (
    <>
            {loading ? (
              <div style={{ color: 'var(--lbb-fg3)', fontSize: 12 }}>Loading report.md…</div>
            ) : error ? (
              <div style={{ color: 'var(--lbb-bad-fg)', fontSize: 12 }}>
                Couldn&rsquo;t load report.md for this date.
              </div>
            ) : !md || !doc ? (
              <div style={{ color: 'var(--lbb-fg3)', fontSize: 12, lineHeight: 1.6 }}>
                This date&rsquo;s run has no <code>report.md</code> on disk
                {runDir ? <> — nothing at <span style={{ fontFamily: 'var(--lbb-mono)' }}>{runDir}/report.md</span></> : null}.
                Older runs predate the report writer.
              </div>
            ) : mode === 'raw' ? (
              <RawView md={md} />
            ) : (
              <div className="rpDocIn" style={{ maxWidth: 720 }}>
                <h1 className="rpH1" style={{
                  margin: 0, font: '700 19px/1.3 var(--lbb-font)', color: 'var(--lbb-fg)',
                }}>{doc.title}</h1>
                <div className="rpMeta" style={{
                  display: 'flex', gap: 8, marginTop: 6,
                  font: '500 10.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
                }}>
                  {runId && <span>run {runId}</span>}
                  {doc.generated && <span>{doc.generated}</span>}
                </div>
                {doc.sections.map(s => (
                  <section key={s.id} id={s.id} style={{ marginTop: 28, paddingTop: 12, borderTop: '1px solid var(--lbb-border)' }}>
                    <h2 className="rpH2" style={{
                      margin: 0, font: '700 13px var(--lbb-font)', color: 'var(--lbb-fg)',
                      display: 'flex', alignItems: 'baseline', gap: 8,
                    }}>
                      {s.title}
                      {s.kind === 'output' && (
                        <button
                          type="button"
                          onClick={() => setOpenPanels(prev => {
                            const ids = s.panels.map(p => panelDomId(s.id, p.label))
                            const anyClosed = ids.some(id => !prev[id])
                            const next = { ...prev }
                            for (const id of ids) next[id] = anyClosed
                            return next
                          })}
                          style={{
                            marginLeft: 'auto', background: 'transparent', border: 'none',
                            cursor: 'pointer', font: '600 10.5px var(--lbb-font)',
                            color: 'var(--lbb-accent-mid)', padding: 0,
                          }}
                        >
                          {s.panels.every(p => openPanels[panelDomId(s.id, p.label)]) ? 'Collapse all' : 'Expand all'}
                        </button>
                      )}
                    </h2>
                    <SectionBody
                      section={s} colorOf={colorOf} onLb={onSelectLb} onOpenPair={onOpenPair}
                      judgmentFor={judgmentFor} pairExists={pairExists}
                      openPanels={openPanels}
                      onTogglePanel={id => setOpenPanels(prev => ({ ...prev, [id]: !prev[id] }))}
                    />
                  </section>
                ))}
                <div className="rpFoot" style={{
                  marginTop: 30, paddingTop: 10, borderTop: '1px solid var(--lbb-border)',
                  font: '500 10.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
                }}>
                  Source of truth is observations.db; this file is a rendering of it.
                </div>
              </div>
            )}
    </>
  )

  return (
    <SheetShell
      name="report.md"
      path={runDir ?? (runId ? `run ${runId}` : date)}
      label={`report.md — ${date}`}
      actions={actions}
      banner={banner}
      rail={rail}
      css={PRINT_CSS}
      docRef={docRef}
      onClose={onClose}
    >{body}</SheetShell>
  )
}

function SectionBody({
  section, colorOf, onLb, onOpenPair, judgmentFor, pairExists, openPanels, onTogglePanel,
}: {
  section: ReportSection
  colorOf: (lb: number) => string
  onLb: (lb: number) => void
  onOpenPair: (a: number, b: number) => void
  judgmentFor: (a: number, b: number) => string | null
  pairExists: (a: number, b: number) => boolean
  openPanels: Record<string, boolean>
  onTogglePanel: (id: string) => void
}): React.JSX.Element {
  if (section.kind === 'coverage') {
    return <CoverageSection section={section} colorOf={colorOf} onLb={onLb} />
  }
  if (section.kind === 'output') {
    return (
      <div style={{ marginTop: 8 }}>
        {section.panels.map(p => {
          const id = panelDomId(section.id, p.label)
          return (
            <OutputPanelBlock
              key={id} panel={p} domId={id} open={!!openPanels[id]}
              onToggle={() => onTogglePanel(id)}
            />
          )
        })}
      </div>
    )
  }
  if (section.kind === 'audit') {
    return (
      <AuditSection
        section={section} colorOf={colorOf} onLb={onLb} onOpenPair={onOpenPair}
        judgmentFor={judgmentFor} pairExists={pairExists}
      />
    )
  }
  if (section.kind === 'commentary') {
    return (
      <div>
        {section.items.map((it, i) => (
          <div key={i} style={{ marginTop: 16 }}>
            <h3 className="rpH3" style={{
              margin: 0, font: '600 12.5px var(--lbb-font)', color: 'var(--lbb-fg)',
              display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
            }}>
              {withChips(it.heading, colorOf, onLb, `c${i}`)}
            </h3>
            <blockquote className="rpQuote" style={{
              margin: '7px 0 0', padding: '8px 11px', fontSize: 12, lineHeight: 1.6,
              color: 'var(--lbb-fg2)', background: 'var(--lbb-surface2)',
              borderLeft: '2px solid var(--lbb-border2)', borderRadius: '0 6px 6px 0',
            }}>
              {it.body ? withChips(it.body, colorOf, onLb, `cb${i}`)
                : <span style={{ color: 'var(--lbb-fg3)' }}>No commentary text.</span>}
            </blockquote>
          </div>
        ))}
      </div>
    )
  }
  return <Prose body={section.body} colorOf={colorOf} onLb={onLb} />
}

/**
 * Prose sections go through `react-markdown` (DECISIONS Q5) with the §11
 * element styles applied as component overrides; LB numbers inside them still
 * become chips.
 */
function Prose({
  body, colorOf, onLb,
}: {
  body: string
  colorOf: (lb: number) => string
  onLb: (lb: number) => void
}): React.JSX.Element {
  // react-markdown's `components` map only covers *element* nodes, so the LB
  // chips are injected by walking each block's children and replacing the
  // string leaves — the "post-process the rendered output" route of §11's
  // implementation note, applied to React children rather than to HTML.
  const chip = (children: React.ReactNode): React.ReactNode =>
    React.Children.map(children, (c, i) =>
      typeof c === 'string' ? withChips(c, colorOf, onLb, `md${i}`) : c)
  return (
    <div style={{ fontSize: 12.5 }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p style={{ margin: '10px 0 0', font: '400 12.5px/1.6 var(--lbb-font)', color: 'var(--lbb-fg2)' }}>
              {chip(children)}
            </p>
          ),
          ul: ({ children }) => (
            <ul style={{ margin: '10px 0 0', paddingLeft: 17, font: '400 12.5px/1.6 var(--lbb-font)', color: 'var(--lbb-fg2)' }}>
              {chip(children)}
            </ul>
          ),
          h3: ({ children }) => (
            <h3 style={{ margin: '18px 0 0', font: '600 12.5px var(--lbb-font)', color: 'var(--lbb-fg)' }}>
              {chip(children)}
            </h3>
          ),
          table: ({ children }) => (
            <div style={{ overflowX: 'auto' }}>
              <table className="rpTable" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, marginTop: 10 }}>
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => <th style={TH}>{children}</th>,
          td: ({ children }) => <td style={TD}>{chip(children)}</td>,
          blockquote: ({ children }) => (
            <blockquote className="rpQuote" style={{
              margin: '10px 0 0', padding: '8px 11px', fontSize: 12, color: 'var(--lbb-fg2)',
              background: 'var(--lbb-surface2)', borderLeft: '2px solid var(--lbb-border2)',
              borderRadius: '0 6px 6px 0',
            }}>{chip(children)}</blockquote>
          ),
          code: ({ children }) => (
            <code style={{ font: '500 11.5px var(--lbb-mono)', color: 'var(--lbb-fg2)' }}>{children}</code>
          ),
        }}
      >{body}</ReactMarkdown>
    </div>
  )
}

/**
 * §11's raw view — the same document, its actual markdown source, with a line
 * gutter and four token colours. It exists so a curator can see exactly what
 * will land in a commit or a paste.
 */
function RawView({ md }: { md: string }): React.JSX.Element {
  const lines = md.split('\n')
  return (
    <div className="rpRawIn" style={{
      display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr)',
      font: '500 11.5px/1.75 var(--lbb-mono)',
    }}>
      <div className="rpGut" style={{
        textAlign: 'right', padding: '0 10px 0 0', background: 'var(--lbb-surface2)',
        borderRight: '1px solid var(--lbb-border)', userSelect: 'none',
        color: 'var(--lbb-fg3)', opacity: 0.65,
      }}>
        {lines.map((_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <div className="rpSrc" style={{
        whiteSpace: 'pre', overflowX: 'auto', padding: '0 0 0 12px', color: 'var(--lbb-fg2)',
      }}>
        {lines.map((l, i) => <div key={i}>{tintSource(l) }</div>)}
      </div>
    </div>
  )
}

/** Four token colours, no more — this is a diffable artifact, not a playground. */
function tintSource(line: string): React.ReactNode {
  if (/^#{1,6}\s/.test(line)) {
    return <span className="mdH" style={{ color: 'var(--lbb-fg)', fontWeight: 700 }}>{line || ' '}</span>
  }
  if (/^\s*\*Generated|^\s*<!--/.test(line)) {
    return <span className="mdMeta" style={{ color: 'var(--lbb-fg3)' }}>{line}</span>
  }
  if (line.trim().startsWith('|')) {
    const parts = line.split('|')
    return parts.map((p, i) => (
      <React.Fragment key={i}>
        {i > 0 && <span className="mdPipe" style={{ color: 'var(--lbb-border2)' }}>|</span>}
        {/^\s*[\d.+-]+\s*$/.test(p) && p.trim()
          ? <span className="mdNum" style={{ color: 'var(--lbb-info-fg)' }}>{p}</span>
          : p}
      </React.Fragment>
    ))
  }
  return line || ' '
}

/**
 * §11.1 — the report inverts to ink on paper, and with the report open only
 * the report prints. The sheet is portalled to `document.body`, so hiding
 * every other body child is the whole scoping rule; §11.1's `:has()` variant
 * exists because the prototype had no portal.
 *
 * Not carried over: `<meta name="omelette-owns-print">` (Electron's host
 * export doesn't read it — Q5 flagged this) and the print-only "nothing to
 * print" notice for the closed state, which belongs to the screen, not to a
 * component that only exists while the report is open.
 */
const PRINT_CSS = `
@media print {
  body > *:not(.rpWrap) { display: none !important; }
  .rpWrap { position: static !important; padding: 0 !important; display: block !important; }
  .rpWrap > div:first-child { display: none !important; }
  .rpSheet {
    position: static !important; width: auto !important; height: auto !important;
    border: none !important; border-radius: 0 !important; box-shadow: none !important;
    overflow: visible !important; background: #fff !important;
  }
  .rpHead, .rpOutline, .rpSeg { display: none !important; }
  .rpBody { display: block !important; }
  .rpDoc { overflow: visible !important; padding: 0 !important; }
  .rpDocIn { max-width: none !important; }
  .rpStale {
    background: none !important; border: none !important;
    border-bottom: 0.5pt solid #b9c0cb !important; color: #3c4553 !important;
    padding: 0 0 6pt !important; font-size: 8.5pt !important;
  }
  .rpSheet, .rpSheet * { color: #3c4553 !important; }
  .rpH1 { font-size: 17pt !important; color: #14181f !important; }
  .rpH2 { font-size: 12pt !important; color: #14181f !important; border-top-color: #b9c0cb !important; break-after: avoid; }
  .rpH3 { font-size: 10.5pt !important; color: #14181f !important; break-after: avoid; }
  .rpMeta, .rpFoot { font-size: 8.5pt !important; color: #6b7482 !important; }
  .rpTable { font-size: 9pt !important; }
  .rpTable th { font-size: 7.5pt !important; color: #6b7482 !important; border-bottom-color: #d6dbe3 !important; }
  .rpTable td { border-bottom-color: #d6dbe3 !important; }
  .rpTable thead { display: table-header-group; }
  .rpTable tr { break-inside: avoid; }
  .rpQuote { background: #f4f6f9 !important; border-left-color: #b9c0cb !important; break-inside: avoid; }
  .rpJudge { break-inside: avoid; background: none !important; border: 1pt dashed #6b7482 !important; }
  .rpLb { background: none !important; border: 0.5pt solid #6b7482 !important; color: #14181f !important; }
  .rpLb span { print-color-adjust: exact; -webkit-print-color-adjust: exact; outline: 0.5pt solid #6b7482; }
  .rpWarn, .rpTable td.rpWarn { color: #7a5b12 !important; font-weight: 600 !important; }
  .rpPanel pre { font-size: 7pt !important; white-space: pre-wrap !important; text-indent: -5mm; padding-left: 5mm; }
  .rpPanel div[style*="overflow-x"] { overflow: visible !important; }
  .rpGut { display: none !important; }
  .rpSrc { white-space: pre-wrap !important; overflow-wrap: break-word; font-size: 8pt !important; }
  @page { margin: 14mm 15mm; }
}
`

export { lbsIn }
