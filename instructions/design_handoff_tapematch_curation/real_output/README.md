# Real `analysis.md` + `report.md` — six dates, unedited

Straight off disk from `data/tapematch/runs/`, byte-for-byte. §7 renders `analysis.md`;
§11 renders `report.md`. The fixtures in `tm-data.js` were reasonable guesses — these
are the actual documents, and they differ in ways that change the design.

**Round 1** — the three files the A1–A9 answers in `DESIGN_ANSWERS.md` were written
against:

| Date | Why it's here |
|---|---|
| **2018-08-26** Auckland | The common case. 3 recordings, 2 families, one LB not on disk, clean verdict. `analysis.md` has a coverage table and **zero verdict cards**. |
| **1991-02-13** London | The rich case. 5 recordings, 5 families, **5 verdict cards** — four speed anomalies and one INCOMPLETE. Longest `report.md` of the three. |
| **1987-09-26** Stockholm | The conflict case. LB commentary says two recordings are the same source, tapematch disagreed. Has the `## Commentary vs tapematch audit` section — the thing §11's Conflicts section is really about. |

**Round 2** — added 2026-07-26 for the B1/B2 asks in `../../prompt2.md`. These three
carry card shapes the round-1 sample happens not to contain, found by checking all 3,923
runs rather than three:

| Date | Why it's here |
|---|---|
| **1993-06-27** | **B1, ref-only cards.** 11 consecutive `### LB-15460 → LB-00912` cards — a pair ref with **no headline at all**, the finding living entirely in the body — followed by 9 conventional ones. 20 cards, more than half of them a shape §7 has no spec for. |
| **1998-06-14** | **B1 title-only + B2.** Opens with `### Coverage gap — 2 of 10 DB entries not found on disk` (a card with no ref, so nothing to put in a chip and nothing to click) and carries two `commentary claims same recording, tapematch disagrees` headlines. Also has real not-on-disk rows, so A3's answer gets a second check. |
| **1996-07-13** | **B1 title-only + B2 + A1.** Has `### Audit table` — the clearest case that some of these may be A6 statement lines rather than cards — a `contradicted by near-zero correlation` headline, and `[INCOMPLETE]/splice` tokens appearing **inside an `analysis.md` headline**, where A5 assumed they live only in `report.md`'s ASCII. Its `## Verdict:` line is 316 characters. |

Everything below this line is round 1, kept as written. `DESIGN_ANSWERS.md` answers all
of it; nothing here is an open ask.

---

## What these change about §11

**1. `## tapematch output` is a fenced code block, and it's most of the document.**
In `1991-02-13_report.md` it runs ~64 of the file's 96 lines. It is fixed-width ASCII —
correlation matrices, anchor timestamp lists, per-source diagnostic lines — that **cannot
reflow**. Individual lines run past 150 characters:

```
  1991-02-13 Hammersmith Odeon London, England (LB-01939)->1991-02-13 London, England (LB-09166): constant-speed-offset  speed ratio=0.986000 (-14000 ppm)
```

This is the single biggest thing option B has to solve. The section needs its own
horizontal scroll container, and the page body must never scroll sideways. **How should
this block be treated — monospace panel with x-scroll, collapsed-by-default with an
expand, or something else?** It has no count for the outline rail either.

**2. The section set varies by date.** `1987-09-26` has the audit section; the other two
don't, because there was nothing to disagree about. So the outline rail is 3 or 4 entries
depending on the date, and the Conflicts equivalent is often simply absent — not empty.

**3. Coverage carries a count line the design has no slot for:**
`DB entries: **4** | Found on disk: **2**`. Rows for missing recordings render with an
em-dash and `*(not found)*` — LB-13072 and LB-13073 in the Stockholm file. §11 has no
treatment for a known-but-absent recording.

**4. LB page commentary is raw scraped text, and some of it is junk.** The Stockholm
file's LB-05503 entry ends with a swept-up navigation tail:

> … registered users may add a comment about the quality of this recording version Year 1987 Select Year Home

and contains a literal `&amp;`. These bodies are long, unstructured, and occasionally
carry scrape debris. **Does this section clamp with a show-more, or render in full?**

---

## What these change about §7

**1. The tone keyword rule has nothing to key on.** tj's answer to Q11 was "infer the
card tone from the headline," on the assumption that conflicts announce themselves with
the word "Conflict." **No real headline contains it.** The actual vocabulary across these
three files is:

```
### LB-05503 / LB-00790 — MISS ⚠️
### LB-00776 — INCOMPLETE recording
### LB-00776 — speed offset +6000 ppm (moderate DAT pitch drift)
### LB-04212 — speed offset -14000 ppm (≈ PAL/cassette speed shift)
### LB-10616 — speed offset +10500 ppm (large — possible tape deck speed)
```

Plus `[DISTINCT SOURCE]` and `[LOW CONFIDENCE]` as bracketed markers inside `report.md`'s
diagnostics. A workable mapping looks more like **MISS → bad; INCOMPLETE → warn; speed
offset → warn; everything else → info** — but that's design's call, and it's worth noting
`MISS` already carries a ⚠️ in the source text, which may make the tone bar redundant.

**2. Card refs use a slash, not ×, and are sometimes single.** The fixture has
`LB-11201 × LB-11340`; real ones are `LB-05503 / LB-00790` for a pair and bare `LB-00776`
for a single recording. Note the pair is written **B / A** — higher LB first — which is
the opposite of the app's normalised `lb_a < lb_b` ordering.

**3. §7 needs an empty state.** `2018-08-26_analysis.md` has no cards at all — just the
verdict line, the table, and a single closing sentence: *"No cross-reference conflicts,
speed anomalies, or algorithm issues detected. Clean date for calibration."* On a clean
date, which is most dates, the verdict-card stack renders nothing.

**4. `analysis.md` has structure §7 doesn't use.** Every file opens with an italic model
attribution line (`*Claude claude-sonnet-4-6 — 2026-06-12*`), a `## Verdict:` headline
that is already parsed into the app DB, a coverage table, and often a `Not on disk:` line.
Some end with a `## Algorithm note` section. The design's §7 renders only the cards.
