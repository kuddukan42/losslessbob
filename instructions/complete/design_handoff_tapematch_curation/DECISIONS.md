# TapeMatch Curation — decisions on Q1–Q5 + Q11

tj, 2026-07-25. Answers to `OPEN_QUESTIONS.md`. **Q6–Q10 are still with design.**

The through-line across every answer: **no re-crawl, no schema change, render what the
3,556 existing runs already have on disk.** Where the design assumed data that isn't
persisted, the decision was consistently to degrade the view rather than re-analyse the
corpus — so several pieces of §6, §11 and §12 will render with less than the handoff
specifies. Those degradations are listed below because they change the design, not just
the implementation.

---

## Q1 — `report.md` → **Option B, style the document that exists**

The generator is untouched. §11's outline rail, LB chips and judgment annotations get
applied to what `tapematch_session.py` writes today.

**What this changes in the design:** the outline rail's entries are the real sections,
not §11's. So instead of

> Summary · Families 5 · Conflicts 1 · Pair evidence 7 · Speed & lag 10 · Recordings 10 · Thresholds · Your judgments

the rail reads

> Coverage 10 · tapematch output · LB page commentary 6 · Commentary vs tapematch audit 4

§11's pair-selection rule ("tabulates 7 of 45 pairs: every same-family pair, every
conflict, and anything at or above 40% similarity") has no equivalent — the document
has no pair-evidence table to select into. **Design input welcome on whether the rail's
count treatment and the section-active behavior still hold with four sections instead of
eight, and what the rail should do for `tapematch output`, which has no natural count.**

## Q2 — §12 causes → **Option A, forward-only**

tj authors a pipeline changelog as calibration changes happen. Nothing is backfilled, so
runs predating the first entry render their threshold lines with **no cause list**. §12 is
last in the implementation order regardless.

## Q3 — unpersisted fields → **Option B, render what exists**

No `sources` schema change. Two concrete losses against §6 and §11:

- `ratioConfidence` is dropped from the §6 dot tooltip and the §11 Speed & lag table.
  The tooltip becomes `LB-11340 · -1,512 ppm · constant-speed-offset`. **§11's warn-amber
  treatment for sub-6.0 confidences has nothing to key on and goes away.**
- ▤ (staircase) and ✂ (splice) **collapse into one glyph with one legend entry**, since
  `speed_kind` stores them as the single value `staircase/splice` across 2,560 rows.
  **Design input needed: which glyph survives, and what the merged legend line reads.**

Also unresolved from the original list: `insufficient` (2 rows) has no glyph in the
design's vocabulary at all.

## Q4 — `Accept families` → **writes to the DB, and marks the date `curated`**

The accept record lands in `observations.db` alongside the existing
`pairs.human_judgment` writes, and flipping the date's status gives the rail's fourth
state (`curated`, mute tone) its only path in — without it that pill is unreachable.

## Q5 — markdown → **add `react-markdown`, pinned**

§11's styling applies through component overrides rather than CSS selectors. Separately,
§11.1's `<meta name="omelette-owns-print">` print mechanism doesn't carry to Electron and
needs its own approach — **if the intent was "host PDF export produces the document, not
the screen," design should say whether that's a requirement or a nicety.**

## Q11 — verdict-card tone → **infer from the headline**

A narrow documented keyword rule — "Conflict" → bad, "Speed-unknown" / "needs review"
→ warn, everything else → info, falling back to `info`. `analysis.md` is not changed, so
this works on all 3,556 existing files. It will mislabel some cards; the fixture's four
(bad / info / warn / info) all classify correctly under the rule.

---

## Still open — design's call

**Q6** speed-dot click behavior · **Q7** §10.6 sticky headers and family boundaries ·
**Q8** §12 run pickers (1989-06-04 has 15 runs) · **Q9** viewports below ~900px ·
**Q10** where the A/B player and `human_notes` sit in the dossier's vertical order.

Q10 is the one that blocks dossier layout: both are shipped features of the current
screen that tj wants carried forward, and §8 specifies the stack end-to-end (header →
verdict → conflict callout → evidence bars → LB page says → judgment) with no slot for
either.
