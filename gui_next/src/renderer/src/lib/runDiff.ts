/**
 * The §12 run diff — a pure function of two run snapshots.
 *
 * README §12: "diffing is a pure function of two run artifacts and is computed
 * client-side; neither run is mutated by viewing". Both snapshots come from
 * `GET /api/tapematch/run_snapshot`, which reads observations.db read-only.
 *
 * What this file deliberately does NOT compute is §12.1, "what changed in the
 * pipeline". That list can't be derived from two artifacts' numbers — it needs
 * the runs to record their own threshold set, which they don't (DECISIONS Q2
 * made that forward-only). The view says so in place of guessing.
 */

/** One recording, as a run saw it. */
export interface SnapshotSource {
  lb_number: number
  family_id: number | string | null
  folder_name: string | null
  speed_kind: string | null
  speed_ppm: number | null
}

/** One pair, as a run measured it. */
export interface SnapshotPair {
  lb_a: number
  lb_b: number
  corr: number | null
  emb_score: number | null
  windowed_frac: number | null
  hiss_median: number | null
  fp_score: number | null
  family_id_a: number | string | null
  family_id_b: number | string | null
  tapematch_verdict: string | null
  human_judgment: string | null
}

export interface RunMeta {
  run_id: string
  run_at?: string | null
  n_sources_ran?: number | null
  n_families?: number | null
  duration_sec?: number | null
}

export interface RunSnapshot {
  run: RunMeta | null
  sources: SnapshotSource[]
  pairs: SnapshotPair[]
}

/**
 * §12's implementation note: the pair key is the two LB numbers **numerically
 * sorted** and joined by `|`. A mis-sorted key fails silently — the lookup
 * misses, the pair falls through to "unchanged", and a flipped call vanishes
 * from the matrix, the table and the counts. The design's prototype asserts
 * the invariant at load; this is the equivalent guard.
 */
export function diffPairKey(a: number, b: number): string {
  const [lo, hi] = a <= b ? [a, b] : [b, a]
  return `${lo}|${hi}`
}

function keyOf(p: SnapshotPair): string {
  return diffPairKey(p.lb_a, p.lb_b)
}

/** True when a run put the two recordings in one family. */
function sameFamily(p: SnapshotPair): boolean | null {
  if (p.family_id_a == null || p.family_id_b == null) {
    // Fall back to the run's own verdict string when family ids are absent.
    if (p.tapematch_verdict == null) return null
    return /same/i.test(p.tapematch_verdict)
  }
  return String(p.family_id_a) === String(p.family_id_b)
}

export interface PairDelta {
  key: string
  lbA: number
  lbB: number
  /** Present only in one run: the pair was added or removed by the re-run. */
  presence: 'both' | 'base-only' | 'head-only'
  corrBase: number | null
  corrHead: number | null
  winBase: number | null
  winHead: number | null
  sameBase: boolean | null
  sameHead: boolean | null
  /** The call changed — the urgent case, whatever the magnitude. */
  flipped: boolean
  /** |Δcorr|, or 0 when either side is missing. */
  absDelta: number
  judgment: string | null
}

export interface FamilyRow {
  /** Head-run family id, or the base id for a family that vanished. */
  id: string
  /** 1-based display index in head-family order, for `F1`/`F2` and colours. */
  index: number
  members: number[]
  /** Members the successor base family had but this head family doesn't. */
  gone: number[]
  /** Members that moved in from another base family. */
  movedIn: number[]
  verdict: 'held' | 'merged' | 'split' | 'regrouped'
  /** The §12.2 sub-line: `unchanged`, `was 2 families`, `split out of base F1`. */
  note: string
}

export interface JudgmentImpact {
  key: string
  lbA: number
  lbB: number
  judgment: string
  kind: 'unchanged' | 'corroborated' | 'contradicted' | 'orphaned'
}

export interface RunDiff {
  base: RunMeta | null
  head: RunMeta | null
  tiles: {
    familiesBase: number
    familiesHead: number
    merged: number
    split: number
    flipped: number
    heldButMoved: number
    judgmentsToReexamine: number
  }
  families: FamilyRow[]
  pairs: PairDelta[]
  /** Recordings present in one run only — never silently dropped (§12.2). */
  addedLbs: number[]
  removedLbs: number[]
  judgments: JudgmentImpact[]
  /** Pairs that moved less than the table's floor, for its closing line. */
  unchangedCount: number
  /** Violations of the pair-key invariant, surfaced rather than swallowed. */
  keyWarnings: string[]
}

/** Group a run's sources into `family id -> members`, in LB order. */
function familiesOf(snap: RunSnapshot): Map<string, number[]> {
  const out = new Map<string, number[]>()
  for (const s of [...snap.sources].sort((a, b) => a.lb_number - b.lb_number)) {
    const fam = s.family_id == null ? `solo:${s.lb_number}` : String(s.family_id)
    out.set(fam, [...(out.get(fam) ?? []), s.lb_number])
  }
  return out
}

const CORR_FLOOR = 0.01 // §12.4 — the table lists moves of at least this much

/**
 * Diff two run snapshots.
 *
 * @param base The earlier run.
 * @param head The later run.
 * @returns Every section §12 renders, plus the counts its stat tiles show.
 */
export function diffRuns(base: RunSnapshot, head: RunSnapshot): RunDiff {
  const keyWarnings: string[] = []
  const basePairs = new Map<string, SnapshotPair>()
  const headPairs = new Map<string, SnapshotPair>()
  for (const [snap, map] of [[base, basePairs], [head, headPairs]] as const) {
    for (const p of snap.pairs) {
      if (p.lb_a > p.lb_b) {
        // Not fatal — keyOf sorts anyway — but it means the producer emitted
        // an unsorted pair, and §12 says this failure mode must be visible.
        keyWarnings.push(`unsorted pair row ${p.lb_a}/${p.lb_b}`)
      }
      map.set(keyOf(p), p)
    }
  }

  const pairs: PairDelta[] = []
  let flipped = 0
  let heldButMoved = 0
  let unchangedCount = 0
  for (const key of new Set([...basePairs.keys(), ...headPairs.keys()])) {
    const b = basePairs.get(key) ?? null
    const h = headPairs.get(key) ?? null
    const [lbA, lbB] = key.split('|').map(Number)
    const sameBase = b ? sameFamily(b) : null
    const sameHead = h ? sameFamily(h) : null
    const isFlipped = b != null && h != null && sameBase != null && sameHead != null
      && sameBase !== sameHead
    const corrBase = b?.corr ?? null
    const corrHead = h?.corr ?? null
    const absDelta = corrBase != null && corrHead != null
      ? Math.abs(corrHead - corrBase) : 0
    if (isFlipped) flipped += 1
    else if (absDelta >= CORR_FLOOR) heldButMoved += 1
    else if (b && h) unchangedCount += 1
    pairs.push({
      key, lbA, lbB,
      presence: b && h ? 'both' : b ? 'base-only' : 'head-only',
      corrBase, corrHead,
      winBase: b?.windowed_frac ?? null,
      winHead: h?.windowed_frac ?? null,
      sameBase, sameHead,
      flipped: isFlipped,
      absDelta,
      // The judgment lives on the pair, not on a run: prefer the head row, but
      // a pair the head run dropped keeps the judgment the base row carries.
      judgment: h?.human_judgment ?? b?.human_judgment ?? null,
    })
  }
  // §12.4 — flipped first, then by magnitude.
  pairs.sort((x, y) =>
    (Number(y.flipped) - Number(x.flipped)) || (y.absDelta - x.absDelta))

  const baseFams = familiesOf(base)
  const headFams = familiesOf(head)
  const baseLbs = new Set(base.sources.map(s => s.lb_number))
  const headLbs = new Set(head.sources.map(s => s.lb_number))
  const famOfLbBase = new Map<number, string>()
  for (const [fam, members] of baseFams) for (const lb of members) famOfLbBase.set(lb, fam)

  // §12.2's successor mapping: each BASE family is inherited by the head family
  // holding the plurality of its members (ties → the lowest head index). Doing
  // it the other way round — iterating head families and asking where members
  // came from — can never see a departure, so a family carved out of a larger
  // one would report itself unchanged.
  const headOrder = [...headFams.keys()]
  const successorOf = new Map<string, string>() // base fam -> head fam
  for (const [fam, members] of baseFams) {
    const tally = new Map<string, number>()
    for (const lb of members) {
      const hf = headOrder.find(k => (headFams.get(k) ?? []).includes(lb))
      if (hf) tally.set(hf, (tally.get(hf) ?? 0) + 1)
    }
    let best: string | null = null
    let bestN = 0
    for (const hf of headOrder) {
      const n = tally.get(hf) ?? 0
      if (n > bestN) { best = hf; bestN = n }
    }
    if (best) successorOf.set(fam, best)
  }

  const inheritedBy = new Map<string, string[]>() // head fam -> base fams
  for (const [bf, hf] of successorOf) inheritedBy.set(hf, [...(inheritedBy.get(hf) ?? []), bf])

  let merged = 0
  let split = 0
  const families: FamilyRow[] = headOrder.map((hf, i) => {
    const members = headFams.get(hf) ?? []
    const inherited = inheritedBy.get(hf) ?? []
    // The base family this head family primarily continues: the one it kept
    // the most members of. Everything else that arrived is a move-in, whether
    // it came from a solo family or a bigger one.
    const primary = inherited
      .map(bf => ({
        bf,
        kept: (baseFams.get(bf) ?? []).filter(lb => members.includes(lb)).length,
      }))
      .sort((a, b) => b.kept - a.kept || a.bf.localeCompare(b.bf))[0]?.bf
    const primaryMembers = primary ? (baseFams.get(primary) ?? []) : []
    const gone = primaryMembers.filter(lb => !members.includes(lb)).sort((a, b) => a - b)
    const movedIn = members.filter(
      lb => baseLbs.has(lb) && famOfLbBase.get(lb) !== primary)
    let verdict: FamilyRow['verdict'] = 'held'
    let note = 'unchanged'
    if (inherited.length === 0) {
      // Carved out of a larger base family. Its members are NOT marked `+`:
      // nobody moved in, the family itself is the change (§12.2).
      const from = members.map(lb => famOfLbBase.get(lb)).find(Boolean)
      const fromIdx = from ? [...baseFams.keys()].indexOf(from) + 1 : null
      split += 1
      return {
        id: hf, index: i + 1, members, gone: [], movedIn: [],
        verdict: 'split' as const,
        note: fromIdx ? `split out of base F${fromIdx}` : 'new family',
      }
    }
    if (gone.length && movedIn.length) {
      verdict = 'regrouped'
      note = `regrouped — ${movedIn.length} in, ${gone.length} out`
      merged += 1
      split += 1
    } else if (gone.length) {
      verdict = 'split'
      note = gone.length === 1 ? '1 left for another family'
        : `${gone.length} left for another family`
      split += 1
    } else if (movedIn.length) {
      // Absorbing a whole base family is a merge; so is a single recording
      // joining. The sub-line says which, the pill says the kind.
      verdict = 'merged'
      note = inherited.length > 1 ? `was ${inherited.length} families`
        : movedIn.length === 1 ? '1 recording moved in'
          : `${movedIn.length} recordings moved in`
      merged += 1
    }
    return { id: hf, index: i + 1, members, gone, movedIn, verdict, note }
  })

  // §12.5 — a judgment is a call about the tapes, so it survives re-analysis;
  // what changes is whether the algorithm still disagrees with the curator.
  const judgments: JudgmentImpact[] = []
  for (const p of pairs) {
    if (!p.judgment) continue
    let kind: JudgmentImpact['kind'] = 'unchanged'
    if (p.presence !== 'both') kind = 'orphaned'
    else if (p.flipped) {
      const agreesNow = p.judgment === 'confirmed_same' ? p.sameHead === true
        : p.judgment === 'confirmed_different' ? p.sameHead === false
          : null
      kind = agreesNow === true ? 'corroborated'
        : agreesNow === false ? 'contradicted' : 'unchanged'
    }
    judgments.push({ key: p.key, lbA: p.lbA, lbB: p.lbB, judgment: p.judgment, kind })
  }

  return {
    base: base.run,
    head: head.run,
    tiles: {
      familiesBase: baseFams.size,
      familiesHead: headFams.size,
      merged,
      split,
      flipped,
      heldButMoved,
      judgmentsToReexamine: judgments.filter(
        j => j.kind === 'contradicted' || j.kind === 'orphaned').length,
    },
    families,
    pairs,
    addedLbs: [...headLbs].filter(lb => !baseLbs.has(lb)).sort((a, b) => a - b),
    removedLbs: [...baseLbs].filter(lb => !headLbs.has(lb)).sort((a, b) => a - b),
    judgments,
    unchangedCount,
    keyWarnings,
  }
}
