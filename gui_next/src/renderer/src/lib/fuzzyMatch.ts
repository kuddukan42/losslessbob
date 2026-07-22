// In-house fuzzy scorer for the command palette (no cmdk/fuzzysort dependency).
//
// Case-insensitive subsequence match: every query char must appear in `text`
// in order. Returns null when there is no match, otherwise a score where
// higher is better. Scoring rewards, in order of weight:
//   • consecutive runs of matched chars (contiguous substrings score best)
//   • matches at word starts (after a space, '-', '/', or at index 0)
//   • earlier overall match position
// Pure and side-effect free so it can be unit-tested in isolation.

const WORD_BOUNDARY = /[\s\-/_.]/

export function fuzzyScore(query: string, text: string): number | null {
  const q = query.toLowerCase().trim()
  const t = text.toLowerCase()
  if (q.length === 0) return 0
  if (q.length > t.length) return null

  let score = 0
  let ti = 0
  let firstMatch = -1
  let run = 0 // current consecutive-run length

  for (let qi = 0; qi < q.length; qi++) {
    const ch = q[qi]
    let found = -1
    for (let j = ti; j < t.length; j++) {
      if (t[j] === ch) {
        found = j
        break
      }
    }
    if (found === -1) return null

    if (firstMatch === -1) firstMatch = found

    // Consecutive with the previous matched char?
    if (found === ti) {
      run += 1
      score += 4 + run // longer runs pay increasing dividends
    } else {
      run = 0
      score += 1
    }

    // Word-start bonus.
    if (found === 0 || WORD_BOUNDARY.test(t[found - 1])) {
      score += 6
    }

    ti = found + 1
  }

  // Earlier overall match beats a later one; small full-match sweetener.
  score += Math.max(0, 10 - firstMatch)
  if (q === t) score += 15

  return score
}
