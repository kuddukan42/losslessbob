# TapeMatch Curation — design answers B1–B2

Design, 2026-07-26. Answers to `../../prompt2.md`. A1–A9 stand; nothing below reopens
them, and nothing needs a field the files don't already carry.

The three round-2 documents are in `real_output/` (byte-for-byte, alongside the round-1
three) and in `tm-real.js`. **Rendered proof:** `TapeMatch Real Output.html` now switches
across all six dates — `1993-06-27` is the ref-only stack, `1998-06-14` the title-only
card plus the B2 vocabulary, `1996-07-13` the `Audit table`, the family-subject card and
the 316-character verdict. Changed code: `tm-realparse.js` (heading subjects, body
blocks, tone table), `tm-parts.jsx` (`VerdictCards`), `tm.css`, `tm-realdemo.jsx`.

---

## B1 — §7's card shape follows the heading's **subject**, not its em-dash

The spec's mistake was reading `### <ref> — <headline>` as a format. It isn't: it's a
**subject** and a **claim about it**, and the corpus writes either half optionally. So the
rule is one line:

> A `###` heading has a subject or it doesn't. With a subject it is a card. Without one it
> is a statement, not a card. A missing headline collapses; nothing is promoted into it.

Three subject kinds, matched on the text left of the first ` — ` (or on the whole heading
when there is no dash):

| left side matches | subject | shape |
|---|---|---|
| `LB-#####` — one, or several joined by `/ → × vs , + and`, optional `(Family n)` tail | ref | card, ref chip (as A7: quoted verbatim) |
| `Family n` | family | card, **family chip** — swatch + label, click selects the family's members |
| anything else | none | **statement block**, no chip, no tone bar |

`Family n` is new here and is the reason the answer is "subject", not "ref": `1996-07-13`'s
`### Family 2 — tight pair confirmed, third member's link uncorroborated` is a finding about
recordings and belongs in the stack — it just isn't keyed to a pair. The family chip already
exists (date header, matrix headers, `.rpLb`); reuse it and the card needs nothing new. The
prototype's swatch is mute because the demo has no per-date family colours; production tints
it with the family colour.

Note this also fixes a live bug the round-1 files hid: `### Coverage gap — 2 of 10 DB entries
not found on disk` **has** an em-dash, so the old rule would have put `Coverage gap` in the
ref slot as mono text with a click target that resolves to nothing. Em-dash presence was
never the right test.

### B1.1 — ref-only cards: the chip stays, the headline row collapses

Of your three options: **the chip stays and the headline row collapses.** Not promotion of
the ref to headline weight, not promotion of the body's first line.

- **The ref is not promoted.** It is already the loudest thing in the card at 11px/700 mono
  against 11.5px prose. Restyling it to headline weight would mean a 20-card stack
  (`1993-06-27`) alternates between two treatments of the same element for a reason the
  curator can't see, and it would put the one piece of quoted text in the card at the one
  weight A7 reserved for the generator's own claim.
- **The body's first line is not promoted.** On every one of the 172 real cases that line is
  `LB commentary notes: "…"` — a scrape fragment, sometimes a fragment *of another file's
  audit table* (`"| LB-00912 / LB-04883 | **DISAGREES** — commentary says same"`). Promoting
  that manufactures a headline the generator didn't write, out of the least trustworthy text
  in the document, and A7's rule is that §7 quotes rather than composes.
- **No em-dash is rendered.** A dash with nothing after it reads as a truncation bug.

**What the empty slot is paid for with: the body gets structure.** The finding lives in the
body, so the body stops being one wrapped paragraph. Lines the generator writes as
`label: value` become a two-column row — 104px uppercase key in `--fg3`, value in `--fg2` —
and a value that opens with a quote takes the quote treatment already used for LB commentary
in the dossier and in §11 (2px `--border2` left rule, `--surface2` fill). Bullets stay
bullets. Everything else stays prose.

That is what makes the 11-card stack readable: every card's keys are identical, so the eye
lands on what differs — the quote, and `tapematch: Family 2 vs Family 6.` Without it, eleven
cards of unbroken wrapped text differ only in the middle of paragraph two.

**Tone on a headline-less card keys on the body — and never on quoted commentary.**
This is a rule worth having in general, not just here: only text the *generator* wrote votes
on tone. Scraped LB text carries `DISAGREES`, `MISS` and similar words out of tables it was
swept up from (A8 keeps that debris deliberately visible), and letting it drive a red bar
would mean the card's severity is set by a scraper bug. With the quoted spans excluded,
`1993-06-27`'s eleven cards all resolve to **info** — which is correct: that date's verdict
line is *"all sources confirmed different"* and the generator claims no problem with any of
them. An eleven-card info stack is the honest rendering; escalation has to come from the
generator saying something, in text, that the tone table can see.

### B1.2 — title-only cards: A6 applies, they are statements

**Yes, this is an A6 situation.** A card means "here is a finding about a recording to
review." `Audit table`, `Coverage gap`, `Merge basis`, `No tapematch comparison was possible`
are statements about the run. They get A6's statement treatment, which already exists for
exactly this class — the `ALGORITHM NOTE` block: dashed `--border2` border, `--surface`
fill, an uppercase key carrying the heading, the rest of the heading as a 12px/600 lead line
when the heading had a dash, then the body.

Reasoning, in order:

1. **A6's argument reaches these directly.** It was written about a sentence that isn't a
   finding; these are paragraphs that aren't findings. Dressing them as cards devalues the
   card, and the card here can't even be complete — no chip, no click target, no dossier.
2. **The dashed border already means "not a per-recording finding" in this design.** A third
   unit type would be invented for four headings; reuse costs nothing and is already taught.
3. **They stay in document order.** `1998-06-14` opens with `Coverage gap` because it
   qualifies everything after it; `1996-07-13` closes with `Audit table` because it summarises.
   Sorting statements out of the stack would destroy an ordering the generator chose, and
   A7's principle is that the document's own rhetoric survives rendering.
4. **The key is tone-tinted, and nothing else is.** `COVERAGE GAP` reads warn (A3: a gap in
   the library is warn, not bad); `AUDIT TABLE` reads mute. No bar, no fill — the statement
   never competes with a card for the eye, which is the whole point of not making it one.

One addition to the tone table for this: `coverage gap|not found on disk|no tapematch
comparison` → **warn**, so a title-only coverage note keys the same way as the coverage
table's own not-on-disk rows in §11. Same fact, same colour, two surfaces.

---

## B2 — `bad`, and it is **two** rows, not one

**Tier: `bad`, sharing the tier with `MISS`, placed immediately below it** (same tier, so the
order between them is immaterial — kept below only so A5's table reads unchanged from the
top). But the vocabulary you listed isn't one thing, and putting it on one row would mis-tone
half of it:

- **Contradiction → `bad`.** `contradicted`, `contradicts`, `disagrees`, `conflicts with`.
  Your own argument carries: this is the thing §7's bad tone was designed for, under a
  different word. It's also the tone the *date* already carries — a date whose commentary
  disagrees with tapematch is `conflict` status, red, in the rail and the date header. If the
  card that contains that disagreement renders amber while the date renders red, the two
  surfaces disagree about the same fact. `MISS` sharing the tier is right: both are "the
  library's record and the measurement do not match."
- **Reliability caveat → `warn`.** `mismatch`, `unreliable`, `uncorroborated`, `coincidence`,
  `inflated`, `needs review`. `### LB — inflated duration, correlation unreliable` and
  `### LB vs LB — small corr (0.016), likely coincidence` are the algorithm marking its own
  confidence, not a contradiction of anything. Red for those would put `1996-07-13`'s
  third-member note at the same weight as its two contradicted same-recording claims, and
  the date has a real distinction to make between them.

Full table, ordered, first match wins:

| # | pattern | tone |
|---|---|---|
| 1 | `MISS` | **bad** |
| 2 | `contradicted` \| `contradicts` \| `disagrees` \| `conflicts with` | **bad** |
| 3 | `INCOMPLETE` | warn |
| 4 | `speed offset` | warn |
| 5 | `LOW CONFIDENCE` | warn |
| 6 | `mismatch` \| `unreliable` \| `uncorroborated` \| `coincidence` \| `inflated` \| `needs review` | warn |
| 7 | `coverage gap` \| `not found on disk` \| `no tapematch comparison` | warn |
| 8 | anything else | info |

Matched against the heading with quoted spans stripped (B1.1). Ordering note: rows 3–5 are
unchanged and still sit above the new warn row, so `INCOMPLETE`-plus-caveat headlines keep
their existing classification; row 2 above them is what makes
`### LB-03040 — two contradicted same-recording claims, plus its own [INCOMPLETE]/splice flag`
read bad rather than warn, which is correct — the contradiction is the finding, the
`[INCOMPLETE]` flag is its likely explanation.

**A5's assumption about `[INCOMPLETE]`/`[LOW CONFIDENCE]` living only in `report.md` was
wrong, and nothing changes.** They appear in `1996-07-13`'s `analysis.md` headline, table
notes and body. They were already tone-table rows; a bracketed token inside prose is just
text and matches the same way. The inline token *tinting* from A1 stays scoped to the
monospace ASCII, where the token is a column value rather than a word in a sentence —
tinting words mid-sentence in §7 would compete with the tone bar for the same signal.

---

## B3 — volunteered: the verdict line clamps to two lines

You flagged the 316-character `## Verdict:`. Taking the offer: **clamp to 2 lines
(`-webkit-line-clamp`, max-width 640px) with an inline `more` / `less` toggle**, appearing
only when the text exceeds ~160 characters. Rendered in the demo on `1996-07-13`.

Two lines, not one, because at the median 55 characters nothing clamps and at p90 84 nothing
clamps — the control is for the 0.6% tail. The reason is A9's reason: the date header sits
above a click-through-fast surface, and a header that is 1 line on one date and 6 on the next
moves the matrix under the cursor. Truncating with no affordance would be worse — those 316
characters are the most informative sentence on the screen for that date — so it clamps
visibly and opens in place, and never reflows anything below it unless the curator asks.

---

## Notes on your resolved list

Agreed on all six, with two additions:

- **`DIAGNOSTICS` at 104 lines.** Yes, add the hint, and make it structural rather than
  advisory: an open-by-default panel whose content exceeds **40 lines** renders open but
  caps its body at ~28 lines of scroll, with the existing header count (`104 lines`) doing
  the disclosure and a footer row `showing 28 of 104 · expand`. Open still means open — the
  conclusions are visible without a click — but one long panel can't push `CLUSTERS` off the
  screen. Print is unaffected: A1's print rule expands everything, and that requirement is
  unchanged.
- **A1's print requirement under Electron.** The requirement was "a collapsed panel must
  never reach the PDF," not "use `beforeprint`." Substituting the show-dossier pattern is
  correct and needs no sign-off.
