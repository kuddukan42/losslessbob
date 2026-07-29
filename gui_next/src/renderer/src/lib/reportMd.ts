/**
 * Parser for a TapeMatch run's `report.md`, for the curation screen's §11
 * report view.
 *
 * Rules: DESIGN_ANSWERS A1 (the `## tapematch output` fenced block splits on
 * its own `=== MARKER ===` lines into one panel each), A2 (the outline rail
 * nests those markers and omits counts where a count has no meaning) and A3
 * (Coverage's `DB entries: **n** | Found on disk: **m**` line becomes a stat
 * row, and not-on-disk rows are a warn variant of a normal row).
 *
 * This is *sectioning*, not markdown rendering: prose bodies come out as raw
 * markdown strings and are handed to `react-markdown` (DECISIONS Q5). Only the
 * three structures the design gives row/panel-level semantics to — Coverage,
 * the ASCII block, and the commentary/audit tables — are read into fields
 * here, because those semantics can't be expressed as element styling.
 *
 * Every shape below was checked against the six documents in
 * `instructions/design_handoff_tapematch_curation/real_output/`.
 */

import { decodeEntities } from './analysisMd'

/** One `=== MARKER ===` block of the `## tapematch output` fence (A1). */
export interface OutputPanel {
  /** The marker verbatim, minus its `===` delimiters. */
  label: string
  /** A2 — the marker up to its first parenthesis, for the rail. */
  shortLabel: string
  lines: string[]
  /** Widest line, in characters — A1's `· N cols` hint above 110. */
  cols: number
  /**
   * A1 — one content line and ≤ 90 characters renders inline, with no
   * collapse affordance. `(no anomalies detected)` is the case this exists
   * for; `ANCHORS` (one line, 100+ chars) stays a panel.
   */
  inline: boolean
  /** A1 — DIAGNOSTICS and CLUSTERS are the curation signal; both open. */
  openByDefault: boolean
}

/** One row of the Coverage table (A3). */
export interface CoverageRow {
  lb: number | null
  /** The `On disk` column's `✓`; a `—` (or anything else) is a not-found row. */
  onDisk: boolean
  rating: string
  timing: string
  source: string
  folder: string
}

/** One row of the `## Commentary vs tapematch audit` table. */
export interface AuditRow {
  /** LB numbers named in the Pair cell, in document order. */
  lbs: number[]
  pairText: string
  /** `**DISAGREES** — commentary says same, …` with its bold markers stripped. */
  verdict: string
  /** AGREES / DISAGREES / anything else the generator wrote, uppercased. */
  verdictWord: string
  snippet: string
}

/** One `### LB-xxxxx | rating: … | timing: …` block of the commentary section. */
export interface CommentaryItem {
  lb: number | null
  heading: string
  body: string
}

export type ReportSection =
  | { kind: 'coverage'; id: string; title: string; entries: number | null; found: number | null; rows: CoverageRow[] }
  | { kind: 'output'; id: string; title: string; panels: OutputPanel[] }
  | { kind: 'commentary'; id: string; title: string; items: CommentaryItem[] }
  | { kind: 'audit'; id: string; title: string; rows: AuditRow[] }
  | { kind: 'prose'; id: string; title: string; body: string }

export interface ReportDoc {
  title: string
  /** The `*Generated: …*` line under the title, without its emphasis marks. */
  generated: string | null
  sections: ReportSection[]
}

const LB_RE = /LB-(\d{3,6})/g

/** Every LB number in a string, in document order, deduplicated. */
export function lbsIn(text: string): number[] {
  const out: number[] = []
  for (const m of text.matchAll(LB_RE)) {
    const n = Number(m[1])
    if (!out.includes(n)) out.push(n)
  }
  return out
}

function stripEmphasis(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/(^|\s)\*(.+?)\*(?=\s|$)/g, '$1$2')
}

/** Split a GFM pipe-table row into trimmed cells. */
function cells(line: string): string[] {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return t.split('|').map(c => decodeEntities(c.trim()))
}

function isSeparatorRow(line: string): boolean {
  return /^\|?[\s:-]+\|[\s|:-]*$/.test(line.trim())
}

/** Table rows of a section body, header row dropped. */
function tableRows(body: string): string[][] {
  const lines = body.split('\n').filter(l => l.trim().startsWith('|'))
  const rows = lines.filter(l => !isSeparatorRow(l)).map(cells)
  return rows.length > 1 ? rows.slice(1) : []
}

function slug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section'
}

/** A1/A2 — split the fenced ASCII block into one panel per `=== … ===`. */
function parseOutputPanels(body: string): OutputPanel[] {
  const fence = body.match(/```[a-z]*\n([\s\S]*?)```/)
  const text = fence ? fence[1] : body
  const panels: OutputPanel[] = []
  let current: OutputPanel | null = null
  for (const raw of text.split('\n')) {
    const marker = raw.match(/^\s*===\s*(.+?)\s*===\s*$/)
    if (marker) {
      if (current) panels.push(current)
      const label = marker[1]
      current = {
        label,
        shortLabel: label.split('(')[0].trim() || label,
        lines: [],
        cols: 0,
        inline: false,
        openByDefault: /^(DIAGNOSTICS|CLUSTERS)\b/i.test(label),
      }
      continue
    }
    if (current) current.lines.push(raw.replace(/\s+$/, ''))
  }
  if (current) panels.push(current)

  // A2 — two markers can collapse to the same short label (2018-08-26 has
  // `LAG CURVES / SPEED` twice); when they do, both keep the parenthetical.
  const seen = new Map<string, number>()
  for (const p of panels) seen.set(p.shortLabel, (seen.get(p.shortLabel) ?? 0) + 1)

  for (const p of panels) {
    while (p.lines.length && !p.lines[p.lines.length - 1].trim()) p.lines.pop()
    while (p.lines.length && !p.lines[0].trim()) p.lines.shift()
    p.cols = p.lines.reduce((n, l) => Math.max(n, l.length), 0)
    const content = p.lines.filter(l => l.trim())
    p.inline = content.length === 1 && content[0].trim().length <= 90
    if ((seen.get(p.shortLabel) ?? 0) > 1) p.shortLabel = p.label
  }
  return panels
}

/** A3 — the summary line's two figures, plus the table's rows. */
function parseCoverage(id: string, title: string, body: string): ReportSection {
  const entriesM = body.match(/DB entries:\s*\*{0,2}(\d+)/i)
  const foundM = body.match(/Found on disk:\s*\*{0,2}(\d+)/i)
  const rows: CoverageRow[] = tableRows(body).map(c => {
    const lbs = lbsIn(c[0] ?? '')
    return {
      lb: lbs.length ? lbs[0] : null,
      onDisk: (c[1] ?? '').includes('✓'),
      rating: c[2] ?? '',
      timing: c[3] ?? '',
      source: c[4] ?? '',
      folder: stripEmphasis(c[5] ?? ''),
    }
  })
  return {
    kind: 'coverage', id, title,
    entries: entriesM ? Number(entriesM[1]) : null,
    found: foundM ? Number(foundM[1]) : null,
    rows,
  }
}

function parseCommentary(id: string, title: string, body: string): ReportSection {
  const items: CommentaryItem[] = []
  let current: CommentaryItem | null = null
  for (const line of body.split('\n')) {
    const h3 = line.match(/^###\s+(.*)$/)
    if (h3) {
      if (current) items.push(current)
      const heading = decodeEntities(h3[1].trim())
      current = { lb: lbsIn(heading)[0] ?? null, heading, body: '' }
      continue
    }
    if (current) current.body += (current.body ? '\n' : '') + line
  }
  if (current) items.push(current)
  for (const it of items) it.body = decodeEntities(it.body).trim()
  return { kind: 'commentary', id, title, items }
}

function parseAudit(id: string, title: string, body: string): ReportSection {
  const rows: AuditRow[] = tableRows(body).map(c => {
    const verdict = stripEmphasis(c[1] ?? '')
    return {
      lbs: lbsIn(c[0] ?? ''),
      pairText: c[0] ?? '',
      verdict,
      verdictWord: (verdict.match(/^[A-Z]+/) ?? [''])[0],
      snippet: c[2] ?? '',
    }
  })
  return { kind: 'audit', id, title, rows }
}

/**
 * Parse a `report.md` into its titled sections.
 *
 * @param md The file's full text.
 * @returns The document's title, generated line and sections in document order.
 */
export function parseReportMd(md: string): ReportDoc {
  const lines = md.split('\n')
  let title = 'report.md'
  let generated: string | null = null
  const sections: ReportSection[] = []

  let heading: string | null = null
  let buf: string[] = []
  const ids = new Set<string>()

  const flush = () => {
    if (heading == null) return
    const body = buf.join('\n').trim()
    let id = slug(heading)
    let n = 2
    while (ids.has(id)) id = `${slug(heading)}-${n++}`
    ids.add(id)
    const lower = heading.toLowerCase()
    if (lower.startsWith('coverage')) sections.push(parseCoverage(id, heading, body))
    else if (lower.includes('tapematch output')) {
      sections.push({ kind: 'output', id, title: heading, panels: parseOutputPanels(body) })
    } else if (lower.includes('commentary vs')) sections.push(parseAudit(id, heading, body))
    else if (lower.includes('commentary')) sections.push(parseCommentary(id, heading, body))
    else sections.push({ kind: 'prose', id, title: heading, body })
    heading = null
    buf = []
  }

  let inFence = false
  for (const line of lines) {
    if (line.trim().startsWith('```')) inFence = !inFence
    if (!inFence && /^#\s+/.test(line)) {
      flush()
      title = decodeEntities(line.replace(/^#\s+/, '').trim())
      continue
    }
    if (!inFence && /^##\s+/.test(line)) {
      flush()
      heading = decodeEntities(line.replace(/^##\s+/, '').trim())
      continue
    }
    if (heading == null) {
      const gen = line.match(/^\*(Generated:.*?)\*\s*$/)
      if (gen) { generated = gen[1]; continue }
      continue
    }
    buf.push(line)
  }
  flush()

  return { title, generated, sections }
}

/**
 * A2 — the outline rail's entries: one per section, with `tapematch output`'s
 * markers nested under it and no count in the slot where a count has no
 * meaning.
 */
export interface OutlineEntry {
  id: string
  label: string
  count: number | null
  sub: boolean
}

export function outlineOf(doc: ReportDoc): OutlineEntry[] {
  const out: OutlineEntry[] = []
  for (const s of doc.sections) {
    if (s.kind === 'output') {
      out.push({ id: s.id, label: s.title, count: null, sub: false })
      for (const p of s.panels) {
        out.push({ id: `${s.id}--${slug(p.label)}`, label: p.shortLabel, count: null, sub: true })
      }
    } else {
      const count =
        s.kind === 'coverage' ? s.rows.length
          : s.kind === 'commentary' ? s.items.length
            : s.kind === 'audit' ? s.rows.length
              : null
      out.push({ id: s.id, label: s.title, count, sub: false })
    }
  }
  return out
}

export function panelDomId(sectionId: string, panelLabel: string): string {
  return `${sectionId}--${slug(panelLabel)}`
}
