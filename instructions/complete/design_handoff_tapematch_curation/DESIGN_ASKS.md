# TapeMatch Curation — what's left for design

Everything Q1–Q11 has a direction (see `OPEN_QUESTIONS.md`). These are the sub-decisions
*inside* those answers that are still open, filtered down to the ones **design should
answer** — engineering-side leftovers (the `react-markdown` version pin, the Q2 changelog
file format, the Q4 table shape, Electron's print path) are not in this list.

Ground truth for all of it is in `real_output/` — three real dates, `analysis.md` +
`report.md` each, straight off disk. The `tm-data.js` fixtures were reasonable guesses;
these are the actual documents.

**Priority:** A1–A3 change how §11 works and have no current answer at all. A4–A6 are
smaller but block §6/§7. A7–A9 are polish.

---

## A1 — §11: how does `## tapematch output` render?

**The situation.** This section is a fenced code block, and it is roughly **two thirds of
the entire report** — ~64 of 96 lines in `1991-02-13_report.md`. It's fixed-width ASCII:
correlation matrices, anchor timestamp lists, per-source diagnostics. It **cannot
reflow**, and individual lines run past 150 characters:

```
  1991-02-13 Hammersmith Odeon London, England (LB-01939)->1991-02-13 London, England (LB-09166): constant-speed-offset  speed ratio=0.986000 (-14000 ppm)
```

§11 has no treatment for this — the design assumed prose and tables.

**The ask.** Monospace panel with its own horizontal scroll? Collapsed by default with an
expand affordance? Broken into sub-blocks by the `=== SECTION ===` markers, each
separately collapsible? The page body must never scroll sideways, whatever the answer.

## A2 — §11: the outline rail has a variable number of sections, and one has no count

**The situation.** §11's rail was designed for eight fixed sections, each with a count
(`Families 5`, `Pair evidence 7`). The real document has **three or four** — the
`## Commentary vs tapematch audit` section only exists when there's something to disagree
about (`1987-09-26` has it, the other two don't). And `## tapematch output` has no natural
count at all.

So the real rail is:

```
Coverage 10 · tapematch output · LB page commentary 6 · Commentary vs tapematch audit 4
```

**The ask.** Does the count treatment survive a countless entry — blank, a dash, something
else? When the audit section is absent, does the rail simply drop it, or show it disabled?
Does a 3-entry rail still earn its width?

## A3 — §11: Coverage carries a line and a row-state §11 doesn't have

**The situation.** Every report opens Coverage with a summary line —
`DB entries: **4** | Found on disk: **2**` — and the table includes rows for recordings
that are known but absent from disk, rendered with an em-dash and `*(not found)*`
(LB-13072 and LB-13073 in the Stockholm file).

§11 has no slot for the summary line and no treatment for a known-but-absent recording.

**The ask.** How do both render? The not-found rows are a real curation signal — that's a
recording the library is missing — so they may deserve more than a greyed row.

## A4 — §6: which glyph survives the merge, and what does the legend say?

**The situation.** §6 gives staircase (`▤`) and splice (`✂`) separate glyphs and separate
legend entries. The DB stores both as one value, `staircase/splice`, across 2,560 rows,
and tj's Q3 answer was to render what exists rather than re-run the corpus. So the two
collapse into one.

Separately, `speed_kind` has a sixth value, **`insufficient`** (2 rows), which has no
glyph anywhere in the design's vocabulary.

**The ask.** Which glyph survives, and what does the merged legend line read? And does
`insufficient` get a glyph or fold into `speed-unknown`?

## A5 — §7: confirm the tone rule against real headlines

**The situation.** tj's Q11 answer was to infer each card's tone from its headline. The
rule was drafted as `"Conflict" → bad`. **No real headline contains the word "Conflict."**
The actual vocabulary across the sample files:

```
### LB-05503 / LB-00790 — MISS ⚠️
### LB-00776 — INCOMPLETE recording
### LB-00776 — speed offset +6000 ppm (moderate DAT pitch drift)
### LB-04212 — speed offset -14000 ppm (≈ PAL/cassette speed shift)
```

`report.md`'s diagnostics add bracketed `[DISTINCT SOURCE]` and `[LOW CONFIDENCE]`.

**The ask.** Confirm or replace this mapping: **MISS → bad · INCOMPLETE → warn · speed
offset → warn · everything else → info.** Note `MISS` already carries a ⚠️ in the source
text — does the tone bar become redundant on exactly the card that matters most?

## A6 — §7: the empty state

**The situation.** On a clean date — which is **most** dates — `analysis.md` has no
verdict cards at all. `2018-08-26_analysis.md` is the whole pattern: a verdict line, a
coverage table, and one closing sentence.

> No cross-reference conflicts, speed anomalies, or algorithm issues detected. Clean date
> for calibration.

**The ask.** Does §7 render that sentence as a single info-tone card, as plain text, or
does the section disappear entirely? This is the common case, not an edge case.

## A7 — §7: card reference format

Fixture refs read `LB-11201 × LB-11340`. Real ones read `LB-05503 / LB-00790` — a slash,
and **high LB first**, which is the reverse of the app's normalised `lb_a < lb_b` order.
Single-recording cards are a bare `LB-00776`.

**The ask.** Normalise to the design's `×` and the app's ordering, or preserve the
document's own text?

## A8 — §11: LB page commentary is raw scraped text

Bodies are long, unstructured, and sometimes carry scrape debris. The Stockholm file's
LB-05503 entry ends with swept-up site navigation:

> … registered users may add a comment about the quality of this recording version Year
> 1987 Select Year Home

and contains a literal `&amp;`.

**The ask.** Clamp with a show-more, or render in full? Any treatment for obvious junk
tails, or leave them visible as an honest view of the source?

## A9 — §8: the dossier now reflows between pairs

Two decisions interact. The A/B player sits **high** (under the conflict callout, above
the evidence bars), and its ineligible state **collapses to a single muted line** rather
than a dimmed panel. Ineligible is common — most speed-offset and staircase pairs.

So clicking through the matrix changes the height of everything below the callout, pair
to pair. Both decisions are individually right; together they make the stack move.

**The ask.** Worth a fixed-height reservation for that slot, or is the reflow acceptable?

---

## Already decided — don't reopen

`OPEN_QUESTIONS.md` carries the full table. In brief: no re-crawl and no schema change
anywhere; §11 styles the document that exists; `ratioConfidence` is dropped; the A/B
player sits high with `human_notes` inside the judgment control; judgments save
explicitly per pair and `Accept families` marks the date `curated`; sticky headers off;
§12 gets run pickers; a min-width notice below ~900px.
