/**
 * Parser for a TapeMatch run's `analysis.md`, for the curation screen's §7
 * verdict cards.
 *
 * Ported from the design handoff's `tm-realparse.js` (rules: DESIGN_ANSWERS
 * A5/A6/A7/A8, DESIGN_ANSWERS_B B1/B1.1/B1.2/B2). No schema change and no
 * re-crawl: everything here is read out of the markdown that `gen_analysis.py`
 * already writes for the ~3,900 runs on disk. If a field isn't derivable from
 * that text, it isn't here.
 */

export type CardTone = 'bad' | 'warn' | 'info' | 'mute'

export type CardBlock =
  | { kind: 'p'; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'kv'; k: string; v: string; quote: boolean }

export interface VerdictCard {
  /** B1 — the heading's *subject* decides the shape, not its em-dash. */
  kind: 'ref' | 'family' | 'statement'
  /** Heading left side, quoted verbatim (A7). Empty on statements. */
  ref: string
  /** LB numbers found in the subject, in document order. */
  refs: number[]
  /** Family number when the subject is `Family n`. */
  fam: number | null
  /** Statement blocks only: the uppercase key, and the lead line after the dash. */
  title: string
  lead: string
  /** Headline right of the em-dash; empty when the document wrote none (B1.1). */
  head: string
  tone: CardTone
  blocks: CardBlock[]
}

export interface AnalysisDoc {
  cards: VerdictCard[]
  /** `Not on disk: LB-13725` — A6's mute meta line. */
  notOnDisk: string[]
  /** `## Algorithm note` body — A6's dashed statement block. */
  algoNote: string
  /** Trailing prose; A6's clean-date sentence when the run produced no cards. */
  epilogue: string[]
  /** LB number → the Family column of the document's own table. */
  famByLb: Map<number, number>
}

/**
 * A5 + B2 — tone from the vocabulary the corpus actually uses. Ordered, first
 * match wins. Row 2 (contradiction) shares `bad` with `MISS`: both are "the
 * library's record and the measurement do not match", and it is the tone the
 * date itself already carries in the rail.
 */
const TONE_RULES: [RegExp, CardTone][] = [
  [/\bMISS\b/, 'bad'],
  [/contradicted|contradicts|\bdisagrees?\b|conflicts with/i, 'bad'],
  [/\bINCOMPLETE\b/i, 'warn'],
  [/speed offset/i, 'warn'],
  [/\bLOW CONFIDENCE\b/i, 'warn'],
  // reliability caveats are the algorithm marking its own confidence, not a
  // contradiction of anything — warn, so they never outrank a real conflict
  [/mismatch|unreliable|uncorroborated|coincidence|inflated|needs review/i, 'warn'],
  // A3's gap language, so a title-only coverage note keys the same way as the
  // coverage table's own not-on-disk rows in §11
  [/coverage gap|not found on disk|no tapematch comparison/i, 'warn'],
]

/**
 * B2/B1.1 — tone never keys on quoted commentary. Scraped LB text carries
 * words like DISAGREES out of tables it was swept up from; letting that vote
 * would mean a scraper bug sets a card's severity.
 */
function unquoted(s: string): string {
  return (s || '').replace(/"[^"]*"/g, ' ').replace(/[“][^”]*[”]/g, ' ')
}

/** Tone for a piece of generator prose (headline, or a headline-less card's body). */
export function toneOf(text: string): CardTone {
  const stripped = unquoted(text)
  const hit = TONE_RULES.find(([re]) => re.test(stripped))
  return hit ? hit[1] : 'info'
}

/**
 * A5 — the tone bar carries the alarm, so the source's own trailing ⚠️ is a
 * second, weaker copy of it. Stripped on render; `analysis.md` is untouched.
 */
export function cleanHead(h: string): string {
  return h.replace(/\s*[⚠❗!]+️?\s*$/u, '').trim()
}

/**
 * A8 — HTML entities are decoded. Nobody wrote `&amp;`; the scraper failed to
 * decode it, and passing it through is a rendering bug, not honesty. (Scrape
 * *debris* is a different thing and stays visible.)
 */
export function decodeEntities(s: string): string {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
}

// B1 — 21% of real `###` headings are not `<ref> — <headline>`. Three subject
// kinds, matched on the text left of the first em-dash (or the whole heading
// when there is no dash).
const REF_RE = /^LB-\d{3,}(?:\s*(?:\/|→|×|x|vs\.?|,|\+|and)\s*LB-\d{3,})*(?:\s*\([^)]*\))?$/i
const FAM_RE = /^Family\s+(\d+)$/i

function lbNumbers(s: string): number[] {
  return (s.match(/LB-(\d{3,})/gi) ?? []).map(m => parseInt(m.slice(3), 10))
}

function subjectOf(left: string): Pick<VerdictCard, 'kind' | 'ref' | 'refs' | 'fam'> | null {
  const s = left.trim()
  if (REF_RE.test(s)) return { kind: 'ref', ref: s, refs: lbNumbers(s), fam: null }
  const f = s.match(FAM_RE)
  if (f) return { kind: 'family', ref: s, refs: [], fam: parseInt(f[1], 10) }
  return null
}

function newCard(heading: string): VerdictCard & { lines: string[] } {
  const h = heading.trim()
  const split = h.match(/^(.+?)\s+—\s+(.+)$/)
  const subj = subjectOf(split ? split[1] : h)
  if (subj) {
    const head = split ? cleanHead(split[2]) : ''
    return {
      ...subj,
      title: '', lead: '', head, blocks: [], lines: [],
      // B1.1 — no headline means the finding is in the body, so the body
      // decides the tone instead (resolved in finishCard).
      tone: head ? toneOf(split![2]) : 'info',
    }
  }
  // B1.2 — a heading with no subject is a statement about the run, not a
  // finding about a recording. A6's dashed statement treatment, not a card.
  const tone = toneOf(h)
  return {
    kind: 'statement',
    ref: '', refs: [], fam: null,
    title: split ? split[1].trim() : h,
    lead: split ? cleanHead(split[2]) : '',
    head: '',
    // B1.2 — the statement's key is tone-tinted and nothing else is, so a
    // statement the tone table has nothing to say about reads mute rather
    // than info: it must never compete with a card for the eye.
    tone: tone === 'info' ? 'mute' : tone,
    blocks: [], lines: [],
  }
}

/**
 * B1.1 — the body carries structure, because on a headline-less card the
 * finding *is* the body. `label: value` lines become a key/value row; a value
 * opening with a quote takes the dossier's quote treatment; bullets stay
 * bullets; everything else is prose. That is what makes an eleven-card stack
 * scannable — the keys are identical, so the eye lands on what differs.
 */
const KV_RE = /^([A-Za-z][A-Za-z0-9 .]{0,26}):\s*(.+)$/

function finishCard(c: VerdictCard & { lines: string[] }): VerdictCard {
  const blocks: CardBlock[] = []
  for (const raw of c.lines) {
    const ln = raw.trim()
    if (!ln) continue
    const last = blocks[blocks.length - 1]
    let m: RegExpMatchArray | null
    if (/^[-*]\s+/.test(ln)) {
      const item = ln.replace(/^[-*]\s+/, '')
      if (last && last.kind === 'ul') last.items.push(item)
      else blocks.push({ kind: 'ul', items: [item] })
    } else if (!c.head && c.kind !== 'statement' && (m = ln.match(KV_RE))) {
      blocks.push({ kind: 'kv', k: m[1], v: m[2], quote: /^["“]/.test(m[2]) })
    } else if (last && last.kind === 'p') {
      last.text += ' ' + ln
    } else {
      blocks.push({ kind: 'p', text: ln })
    }
  }
  let tone = c.tone
  if (!c.head && c.kind !== 'statement') {
    // only the generator's own lines vote — a quoted kv value is LB commentary
    const own = blocks
      .map(b => (b.kind === 'kv' ? (b.quote ? '' : b.v) : b.kind === 'p' ? b.text : b.items.join(' ')))
      .join(' ')
    tone = toneOf(own)
  }
  return {
    kind: c.kind, ref: c.ref, refs: c.refs, fam: c.fam,
    title: c.title, lead: c.lead, head: c.head, tone, blocks,
  }
}

/** Strip markdown emphasis — the cards render as text, not as markdown. */
function plain(s: string): string {
  return decodeEntities(s)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+$/, '')
}

function tableCells(line: string): string[] {
  return line.replace(/^\||\|$/g, '').split('|').map(c => c.trim())
}

const TABLE_RULE_RE = /^\|[\s:|-]+\|$/

/**
 * Parse a run's `analysis.md` into the §7 verdict stack.
 *
 * Args:
 *   md: the document's full text, as served by `/api/tapematch/analysis`.
 *
 * Returns:
 *   Cards in document order (statements keep their place — the generator's
 *   ordering is part of what it said), plus the A6 meta lines and the table's
 *   LB → family mapping used to tint family chips.
 */
export function parseAnalysisMd(md: string): AnalysisDoc {
  const doc: AnalysisDoc = {
    cards: [], notOnDisk: [], algoNote: '', epilogue: [], famByLb: new Map(),
  }
  if (!md) return doc

  const lines = md.split('\n')
  const cards: (VerdictCard & { lines: string[] })[] = []
  let section: 'front' | 'verdict' | 'algo' | 'card' | 'other' = 'front'
  let sawTableHeader = false

  for (const raw of lines) {
    const line = raw.trim()
    let m: RegExpMatchArray | null
    if (line.startsWith('# ') || /^\*.+\*$/.test(line)) continue
    if ((m = line.match(/^### (.+)$/))) {
      cards.push(newCard(plain(m[1])))
      section = 'card'
      continue
    }
    if ((m = line.match(/^## (.+)$/))) {
      section = /^verdict/i.test(m[1]) ? 'verdict' : /algorithm/i.test(m[1]) ? 'algo' : 'other'
      continue
    }
    if (!line) continue
    if (line.startsWith('|')) {
      if (TABLE_RULE_RE.test(line)) continue
      const cells = tableCells(line)
      // the first table is the per-recording summary; its 5th column is the
      // family number the document's own headings refer to
      if (!sawTableHeader) { sawTableHeader = true; continue }
      const lb = lbNumbers(cells[0] ?? '')[0]
      const fam = parseInt(cells[4] ?? '', 10)
      if (lb != null && Number.isFinite(fam)) doc.famByLb.set(lb, fam)
      continue
    }
    if ((m = line.match(/^Not on disk:\s*(.+)$/))) {
      doc.notOnDisk = m[1].split(/,\s*/).map(s => s.trim()).filter(Boolean)
      continue
    }
    if (section === 'card' && cards.length) { cards[cards.length - 1].lines.push(plain(line)); continue }
    if (section === 'algo') { doc.algoNote += (doc.algoNote ? ' ' : '') + plain(line); continue }
    doc.epilogue.push(plain(line))
  }

  doc.cards = cards.map(finishCard)
  return doc
}
