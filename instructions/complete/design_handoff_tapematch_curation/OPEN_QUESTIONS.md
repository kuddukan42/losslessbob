# TapeMatch Curation — open questions

> Companion to `IMPLEMENTATION_PLAN.md`. Written 2026-07-25, from the implementation side.
>
> These are places where `README.md` assumes data, a document, or a behavior that
> does not exist in the codebase. Each is a decision, not a bug — recorded here
> rather than solved, because the answers change what gets built.
>
> **Q1–Q5 block work.** Q6–Q11 at the bottom are things the handoff itself marks as
> undesigned; they need an answer eventually but nothing is blocked on them today.

---

## Q1 — `report.md` on disk is a different document from §11's

**What the design renders.** §11's outline rail lists *Summary · Families · Conflicts ·
Pair evidence · Speed & lag · Recordings · Thresholds · Your judgments*, each with a
count (`Families 5`, `Pair evidence 7`, `Speed & lag 10`, `Recordings 10`), and applies
a selection rule — "Pair evidence tabulates 7 of 45 pairs: every same-family pair,
every conflict, and anything at or above 40% similarity."

**What `tools/tapematch/tapematch_session.py` actually writes.** Checked against
`data/tapematch/runs/20260725_164125_1982-06-06/report.md`, sections are:

```
# tapematch session — 1982-06-06 — Peace Sunday Rally, Rose Bowl, Pasadena, California
## Coverage                       (LB | On disk | Rating | Timing | Source | Folder)
## tapematch output
## LB page commentary             (### LB-00810 | rating: B | timing: 33min …)
## Commentary vs tapematch audit  (Pair | Verdict | Commentary snippet)
```

Same filename, different document. There is real overlap in content — Coverage carries
rating/timing/source, the audit table carries the LB-vs-TapeMatch agreement that §11's
Conflicts section is about — but no section maps 1:1, and nothing supplies the outline
counts or the pair-selection rule.

**Scale.** 3,556 runs across 2,902 dates already have the old shape on disk.

### Options

| | Approach | Consequence |
|---|---|---|
| **A** | Rewrite the generator to emit the designed document | Bit-perfect §11. Every existing run renders wrong until re-analysed — and a full re-run is a multi-day crawl. |
| **B** | Apply §11's styling, outline, LB chips and judgment annotations to the document that exists | Works on all 3,556 runs today. The view is right; the document under it is not the designed one. |
| **C** | Generator emits the designed document *alongside* the current one | New runs get bit-perfect §11; old runs fall back to B. Two artifacts per run to maintain. |

---

## Q2 — §12's pipeline cause list cannot be derived

§12's first section, "What changed in the pipeline", carries four authored claims:
dice demoted from grouping to confirmatory, staircase/splice-aware alignment, secondary
clustering added, primary threshold `0.50 → 0.45`. The handoff is explicit that this is
the view's prerequisite:

> *The pipeline-cause list can't be derived from the two artifacts' numbers. It needs
> the runs to record their own pipeline version / threshold set / changelog entry. If
> the backend doesn't store that yet, that's the prerequisite for this view — without
> causes it degrades into an unexplained pile of deltas.*

**Partial good news.** `runs.config_json` *does* store each run's full config, so the
run bar's threshold lines (`corr ≥ 0.5 · win ≥ 0.6 · dice groups ≥ 0.35` versus
`corr ≥ 0.45 · win ≥ 0.60 · dice confirmatory only`) are derivable — that's
`match.cluster_threshold` and friends, present and readable.

**What isn't derivable is the prose.** Diffing the earliest and latest configs for
`1989-06-04` (15 runs) yields **74 changed keys**, of which nearly all are
`None → value` — the config schema growing over time, not pipeline changes:

```
refine.enabled                       (None, True)
fingerprint.triplet.enabled          (None, False)
spectral_stationarity.n_mels         (None, 32)
addon_links.rule_b.t_env             (None, 0.9)
…
```

No mechanical rule separates "the pipeline changed its mind" from "a new config key
appeared."

### Options

| | Approach | Consequence |
|---|---|---|
| **A** | Author a versioned pipeline-changelog in `tools/tapematch/`, keyed by config version, that the diff view reads | §12 as designed. `CALIBRATION_PROGRESS.md` is the existing narrative record of exactly these changes and could seed it — but the entries are tj's to write, not the agent's to invent. |
| **B** | Render the run bar's threshold lines only; omit the cause section | No authoring burden. The handoff's own warning applies: an unexplained pile of deltas. |
| **C** | Build §1–11 first; revisit | §12 is already last in the handoff's implementation order. |

---

## Q3 — Two fields the engine knows but doesn't write down

### 3a. `ratioConfidence`

`tools/tapematch/tapematch/match.py:261` — `estimate_ratio_v2` returns
`(ratio, confidence)`, and the confidence is what decides whether a source becomes
`speed-unknown` (below the 6.0 minimum). It is then discarded: `sources` has no column
for it.

The design surfaces it twice — §6's dot tooltip
(`LB-11340 · -1,512 ppm · constant-speed-offset · confidence 8.8`) and §11's Speed &
lag section, where sub-6.0 confidences render in warn amber.

### 3b. `staircase` vs `splice`

`sources.speed_kind` has six values across 14,617 rows:

```
reference             3,556
speed-unknown         5,055
staircase/splice      2,560
constant-speed-offset 2,050
aligned               1,394
insufficient              2
```

§6 gives staircase and splice **separate glyphs and separate legend entries** — `▤`
(discontinuous lag steps — re-tracked CDR indices) and `✂` (lag jumps at one point —
tape flip / patched section). The DB collapses them into one string. They are probably
separable from `lag_segments_json` (a staircase has many small steps, a splice has one
large one), but the handoff defines no rule and the implementation side won't invent a
threshold.

Note also `insufficient` (2 rows) has no glyph in the design's vocabulary at all.

### Options

| | Approach | Consequence |
|---|---|---|
| **A** | Add both to `sources`, written by `tapematch_session.py` | Bit-perfect §6 and §11 — for dates re-analysed after this ships. Everything older shows blanks. Full backfill is a multi-day re-run. |
| **B** | Render what exists | Drop the confidence from the tooltip and the §11 table; collapse ▤ and ✂ into one glyph with one matching legend entry. No DB change, no re-run, not bit-perfect. |
| **C** | Add the columns, don't backfill | UI renders them when present, hides them when null. Coverage grows as dates get re-analysed. |

---

## Q4 — `Accept families` has no write path

§3 fully specifies the button: primary tone, disabled until at least one pair judgment
exists, label gains `· 2 judged` once judgments accumulate, and §10.5 special-cases it
to **enabled with zero judgments** on a single-recording date ("the 'needs a judgment
first' rule exists to stop rubber-stamping pair decisions, and there are no pair
decisions"). §10.7 adds that it should "flush any pending judgments."

It never says what accepting *writes*, and no endpoint exists.

### Options

| | Approach | Consequence |
|---|---|---|
| **A** | Build the button fully, wire to a stubbed handler, write path specified before ship | Nothing is guessed. The screen is complete except this one action. |
| **B** | Flush pending judgments, then mark the date `curated` | Gives the rail's fourth status a way to be reached — right now `curated` is in the design's status vocabulary with no path into it. |
| **C** | Run the existing `POST /api/tapematch/sync` for this date | Promotes the run's families into `recording_families` / `tapematch_family_meta`. Reuses a shipped path, but that route is currently documented as manual-trigger-only. |

---

## Q5 — No markdown renderer in `gui_next`

§11's implementation notes:

> *Use the codebase's existing markdown renderer with these styles applied — do not
> port the prototype's hand-rolled rendering, and do not write a parser.*

`gui_next/package.json` has no markdown dependency. The current `AnalysisSection`
(`ScreenTapeMatch.tsx:741`) renders `analysis.md` as a raw `<pre>`.

So §11 needs a new pinned dependency — which per project rules means `package.json` +
a PROJECT.md update. Confirming that's acceptable, and whether there's a preference.

Related, smaller: §11.1's print block relies on
`<meta name="omelette-owns-print" content="report.md">` to make host PDF export produce
the document rather than the screen. That's a prototype mechanism; Electron's
print/PDF path differs and will need its own approach.

---

## Undesigned by the handoff itself

Not blocking, but they need an answer before the relevant piece ships. All are places
`README.md` explicitly defers.

**Q6 — §6 speed-dot click behavior.** The prototype's logic is described as
"functional but blunt," a recommended production behavior is given (click one dot to
select a recording, a second to form a pair), and then: *"Confirm with design before
shipping either."*

**Q7 — §10.6 sticky headers and family-boundary rules.** *"The class is in the
stylesheet but not wired — confirm with design before enabling, it adds a lot of
lines."* Relevant for 30+ recording dates.

**Q8 — §12's run pickers.** *"Production fetches any two runs by id — make the run
bar's ids into pickers; the design leaves room for a select in `.dfRunSel` and this is
the one obvious gap."* `1989-06-04` has 15 runs, so this matters in practice.

**Q9 — Viewports below ~900px.** *"The design has no defined behavior… either define a
mobile read-only view with the design team or gate it behind a min-width notice. Do not
naively stack it."*

**Q10 — Where the A/B player and `human_notes` sit in the dossier.** Both are shipped
features of the current `ScreenTapeMatch` (the A/B player was TODO-231) and tj wants
them carried forward, but the design didn't know they existed, so §8 has no slot for
them. The dossier's vertical order is specified end-to-end (header → verdict → conflict
callout → evidence bars → LB page says → judgment), and these are two more blocks to
place in it.

**Q11 — Verdict-card tone.** §7's cards carry a tone (the fixture's four are
bad/info/warn/info) driving the left tone-bar color. `analysis.md` gives
`### <ref> — <headline>` plus a body paragraph, with no tone marker:

```markdown
### LB-07662 — speed offset +21677 ppm (≈ PAL/cassette speed shift)
Speed offset near ±15000 ppm suggests a PAL/NTSC speed mismatch or cassette
played at wrong speed. Correctly isolated as distinct source.
```

Tone would have to be inferred from the text, or written into the file by
`gen_analysis.py`.
