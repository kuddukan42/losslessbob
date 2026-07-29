# TapeMatch Curation — design answers A1–A9

Design, 2026-07-26. Answers to `DESIGN_ASKS.md`. Nothing in `DECISIONS.md`'s "already
decided" list is reopened.

Every answer below was checked against the three documents in `real_output/`. Nothing here
needs a field the files don't already carry — no re-crawl, no schema change, no generator
change.

**Rendered proof:** `TapeMatch Real Output.html` renders §7 and §11 against all three real
files, switchable. `2018-08-26` is the A6 empty state and the A3 not-found row;
`1991-02-13` is the ASCII-heavy document; `1987-09-26` is the MISS card and the only file
with an audit section. New/changed code: `tm-real.js` (verbatim copies of the six files),
`tm-realparse.js` (the parsers), `tm-report.jsx`, `tm-parts.jsx`, `tm.css`.

---

## A1 — `## tapematch output` renders as sub-blocks split on its own `===` markers

**Decision.** Not one panel, not collapsed-as-a-whole. Split the fenced block on
`^=== (.+) ===$` and render **one collapsible monospace panel per marker**, in document
order, inside a `## tapematch output` section that has no count.

Each panel:

- **Header row**, always visible: caret · marker label in mono 10px/700 · `N lines`
  (plus `· N cols` when the widest line exceeds 110 characters) · and, when collapsed, a
  single-line peek of the first content line, ellipsised.
- **Body**, when open: `<pre>` at 10.5px mono, `white-space: pre`, in a container with
  `overflow-x: auto` and `overscroll-behavior-x: contain`. The lines never wrap and the
  scroll is trapped in the panel. The document column and the page body cannot scroll
  sideways — that constraint is met structurally, not by CSS defence.
- **Open by default: `DIAGNOSTICS` and `CLUSTERS`.** Those two are the curation signal —
  what the algorithm concluded and what it flagged. Everything else (ingest, trim, anchors,
  lag curves, matrices, lineage) is provenance you go looking for, so it opens on demand.
  A curator scrolling past this section sees the conclusions, not 64 lines of scaffolding.
- **`Expand all` / `Collapse all`** sits in the section header.
- **A single short line renders inline, not as a panel.** `DIAGNOSTICS` on a clean date is
  `(no anomalies detected)` — a collapsible affordance around six words is worse than the
  words. Rule: one content line **and** ≤ 90 characters → label and value on one row, no
  caret. `ANCHORS` (one line, 100+ chars) stays a panel.
- **Bracketed tokens are tinted in place**: `[INCOMPLETE]` and `[LOW CONFIDENCE]` warn,
  `[DISTINCT SOURCE]` info. Same vocabulary as A5, applied inside the monospace instead of
  around it. This is the one liberty taken with verbatim text and it changes no characters.
- **Print expands every panel** (`beforeprint`), at 7pt, and there long lines *do* wrap,
  with a 5 mm hanging indent. Checked against the real files: matrices and the lineage
  table are ~60 columns and never reach the measure; the only lines that wrap are the
  150-column diagnostic and lag-curve lines, which are sentences, not grids, and read fine
  wrapped. A collapsed panel must never reach the PDF — silently dropping generator lines
  from an archival print is the one unacceptable outcome.

**Why not one big panel with one scrollbar:** at 64 lines the section becomes a wall you
scroll past, and the horizontal scroll position is shared between a 60-column matrix and a
173-column diagnostic list, so one of them is always wrong.

## A2 — the rail nests the ASCII markers; countless entries carry no count; absent sections drop out

**Decision, three parts.**

1. **A countless entry shows nothing in the count slot.** No dash, no `—`, no `n/a`. The
   count is a right-aligned mono figure; where there is no figure the slot is empty. A dash
   reads as "zero" or "unknown", and `tapematch output` is neither — the concept of a count
   does not apply. Absence of a number is the honest rendering.
2. **The `===` markers become indented sub-entries under `tapematch output`.** That is what
   makes a four-entry rail earn its width: the rail is 4 top-level entries plus 8–10
   sub-entries, so it is the document's real table of contents, and clicking a sub-entry
   scrolls to that panel. `.rpOutLink.sub` already existed in the stylesheet for this. Sub-
   entries show the marker up to its first parenthesis (`ANCHORS`, not
   `ANCHORS (ref=1991-02-13 Hammersmith Odeon London, England (LB-01939))`); when two
   markers collapse to the same short label — `2018-08-26` has `LAG CURVES / SPEED` twice —
   the parenthetical is kept, truncated, on both.
3. **An absent section is absent from the rail.** No disabled entry, ever. Two of three
   real files have no audit section; a permanently greyed row would teach curators that
   something is missing on the normal case. The rail reflects the document. The *analysis*
   layer is where absence gets stated positively — see A6.

## A3 — Coverage's summary line becomes a stat row; not-found rows are a warn variant, not a grey one

**The summary line.** Rendered as a compact stat row above the table, not as prose and not
as a table caption: `**5** DB entries · **5** found on disk`, mono figures at 12.5px against
10px labels. When `found < entries` a third element appears in warn tone naming the gap:
`1 not on disk — LB-13725`. Warn, not bad: a missing recording is a hole in the library, not
a fault in this run.

**Not-found rows.** They stay in the table, in document (LB) order, and they are **not
greyed**. Treatment:

- the LB chip keeps full contrast — this is the row you are meant to notice;
- a `not on disk` pill in warn tone sits next to it;
- empty metadata cells get a dim `·` rather than blank, so the row doesn't read as broken;
- the source cell reads `no folder found — DB entry only` in warn tone;
- a 2px warn bar on the row's left edge groups them when there are several
  (`1987-09-26` has two).

One line of prose closes the table when any row is missing: *"A not-on-disk row is a gap in
the library, not a failure of this run — the DB knows the recording, the crawl never found
audio for it."* Same fact appears once more in §7 as a mute meta line (A6), because it is a
finding that survives even on an otherwise clean date.

Greyed-out was the wrong instinct: grey means "not applicable here." These rows are the
opposite — they are the only actionable item on most clean dates.

## A4 — `▤` survives; `insufficient` folds into `speed-unknown`

**Glyph.** `▤`. Confirmed against the merged value.

**Merged legend line:** `▤ lag steps — re-tracking or a splice`.

`▤` survives because it is the only one of the two that *depicts* the measurement — a lag
curve that steps — and it stays legible at 9px inside the 18px family dot, which `✂` does
not. `✂` also over-claims: it names a physical cause (tape flip, patched section) that the
stored value `staircase/splice` can no longer distinguish. Rendering a scissors glyph for
2,560 rows where roughly half are re-tracked CDR indices would be a design asserting
something the data doesn't support.

**`insufficient` gets no glyph.** It folds into `speed-unknown` — same `?`, same warn tone,
same fingerprint-path consequence, which is the truth of it: not enough signal to estimate a
ratio. Two rows in 14,617 do not justify a sixth symbol every curator has to learn. The raw
value is preserved in the dot tooltip: `LB-xxxxx · speed-unknown (insufficient)`. Nothing is
hidden; nothing new has to be taught.

Legend goes from five entries to four. Good.

## A5 — tone rule replaced, and the ⚠️ comes off the headline

**Replaces the draft rule.** Ordered, first match wins, on the `### <ref> — <headline>` text:

| pattern | tone |
|---|---|
| `MISS` | **bad** |
| `INCOMPLETE` | **warn** |
| `speed offset` | **warn** |
| `LOW CONFIDENCE` | **warn** |
| anything else | **info** |

`Conflict` is gone — no real headline contains it. `MISS` is the word the generator actually
uses for the thing §7's bad tone was designed for. All nine cards across the three real
files classify correctly.

**On the redundancy you flagged: keep the tone bar, drop the emoji.** The rendered headline
strips a trailing `⚠️`. The bar is the load-bearing signal — it is the only thing that makes
a stack of five cards scannable at a glance, it is positional and consistent, and it is what
carries the same meaning in print. The emoji is the source file's way of doing the same job
without a stylesheet; once the card has a bar, the emoji is a second, weaker copy of it
sitting inside the sentence. `analysis.md` is untouched, so raw view still shows it — the
strip is a rendering decision, reversible, and costs nothing.

**`[DISTINCT SOURCE]` / `[LOW CONFIDENCE]` do not become cards.** They live inside
`report.md`'s ASCII diagnostics, not in `analysis.md`, and they are per-source machine notes,
not review items. They get the inline token tinting described in A1 and no card.

## A6 — the section stays; the clean sentence is a line, not a card

**Decision.** §7 does **not** disappear, and the sentence is **not** wrapped in an info-tone
card. It renders as a single statement line: a small ok-tone dot and the generator's own
sentence at 12px in `--fg2`, directly under the section header.

A card means "here is a finding to review." A clean date has no findings, and dressing the
absence of findings as a card devalues the card as a unit — after fifty clean dates the
curator stops reading them. But the section must stay, because a section that vanishes is
indistinguishable from a section that failed to load, and because the page's rhythm
(verdict → §7 → matrix) should not depend on the date's luck.

Under it, still on clean dates, two things may appear as mute meta lines rather than cards:

- `Not on disk: LB-13725 — known to the DB, no audio found by the crawl.`
- the `## Algorithm note` body, when present, in a dashed-border block labelled
  `ALGORITHM NOTE` — it is commentary about the pipeline, not about a recording, so it
  cannot be a card keyed to a ref.

## A7 — preserve the document's own reference text

**Decision.** Render `LB-05503 / LB-00790` exactly as `analysis.md` writes it. Slash, and
the document's own ordering. Drop `×` from §7 entirely.

A verdict card is a **quotation** of a file the curator can open in raw view two clicks
away, and whose own verdict line reads `MISS on LB-05503 / LB-00790`. Silently reordering
the pair makes the card disagree with the document it claims to be showing, and with itself.
Normalisation is a database concern; it belongs to the pair key and the dossier, not to
quoted text.

So: **display follows the document, navigation follows the app.** The ref is a click target;
clicking it resolves through the normalised `lb_a < lb_b` key and opens the dossier, whose
header — app-generated, not quoted — keeps `LB-00790 × LB-05503` and `×`. Single-recording
cards stay a bare `LB-00776`.

## A8 — clamp to three lines, show-more, junk stays

**Decision.** Body clamps to **3 lines** with a `Show more` / `Show less` control, appearing
only past ~240 characters. Expanded shows the full text. The `rating` / `timing` meta row is
always visible.

**No junk-tail cleanup.** Scrape debris — swept-up site navigation, `Select Year Home`,
track listings that ran into a file manifest — stays visible. It is an honest view of the
source and the only place a curator will ever notice that the scrape needs fixing;
silently trimming it makes a data problem invisible. The clamp already keeps it out of the
default view, since tails are by definition at the end.

**One exception, because it is a rendering bug and not content:** HTML entities are decoded.
`&amp;` renders as `&`. Nobody wrote `&amp;` — the scraper failed to decode it, and showing
it is not honesty, it is a mistake passed through.

## A9 — reserve the height; the reflow is not acceptable

**Decision.** Reserve. `min-height: 96px` on the A/B slot — the height of its
**empty-eligible** state (title row + position/duration/Load row + hint). The ineligible
state's single muted line sits inside that reserved box.

The reason is the interaction, not the aesthetics. The matrix is a click-through-fast
surface: a curator arrows or clicks across cells at speed, and the judgment control is the
one thing on the screen that writes to the database. If the block above it changes height
between an eligible and an ineligible pair, `Same source` lands where `LB wrong` was a
moment ago. Ineligible is the *common* case, so this doesn't happen once — it alternates.
96px of dead space on ineligible pairs is a cheap price for a control that stays where the
cursor left it.

**What is not reserved:** the loaded state (Play button + A/B chips) is allowed to grow past
the reservation. That growth is the user's own action on the pair they are already looking
at — movement there is feedback, not instability, and reserving for it would put ~150px of
emptiness on every pair to serve a state that appears on a minority of them.

The ineligible line reads: *"Not sample-alignable — the speed offset between these two makes
a synced clip pair impossible."* It says why, in one line, because "not eligible" alone
invites the curator to go looking for a control that isn't broken.

---

## Two notes for engineering, not decisions

- **§11's overlay now needs a date.** `TMReport` takes a `date` prop and renders the real
  document for it; there is no synthesized markdown left in the prototype, and raw view
  shows the file byte-for-byte. The fixture date `2001-11-19` has no real run on disk, so
  the prototype's overlay defaults to `1991-02-13`. Production reads the run's own path.
- **A/B eligibility** is read from `ab_eligible` on `GET /api/tapematch/pairs`; the
  prototype approximates it as "both sources aligned or reference" purely to exercise both
  states.
