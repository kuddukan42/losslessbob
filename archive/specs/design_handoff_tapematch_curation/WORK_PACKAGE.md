# TapeMatch Curation — build work package

Live resume tracking for the build. Started 2026-07-28.

Sources of truth, in precedence order:
1. `DESIGN_ANSWERS_B.md` (B1–B3) — supersedes A5/A7 where they conflict
2. `DESIGN_ANSWERS.md` (A1–A9)
3. `DECISIONS.md` (tj, Q1–Q5 + Q11)
4. `README.md` (§1–§12)

`real_output/` holds six real dates (analysis.md + report.md each) — the only
acceptable test fixtures. `tm-data.js` is shape reference, not data.

---

## Standing constraints

- No re-crawl, no `observations.db` schema change, no generator change.
- Render what the ~3,900 existing runs already have on disk; degrade the view
  rather than re-analyse the corpus.
- `/gui-check` after every phase. `/verify` (Tier A) on any phase that changes
  layout or visuals.

## Build decisions taken by this session (not from design)

- **D1 — DONE 2026-07-28. New screen built alongside, then swapped in.**
  `screens/ScreenTapeMatchCuration.tsx` now serves `/tapematch` and
  `ScreenTapeMatch.tsx` is deleted; `/tapematch/curation` redirects, query
  string intact. The swap waited for the Phase 6 write path (parity =
  matrix + dossier + A/B player + judgment write path) and carried over the
  three things only the old screen had: crawl start/stop, the `/library?lb=`
  deep-link, and the raw `analysis.md` view. Known cost, accepted: the
  curation screen is hardcoded English, so TapeMatch lost its five
  translations until TODO-275.
- **D2 — tokens map onto the existing `--lbb-*` system.** The design's hex table
  is a dark-grade palette; gui_next has a light/dark theme engine whose
  `ok/warn/bad/info/mute` tokens are already fg/bar/bg triples. Hardcoding the
  design's hexes would break light mode. Semantic colours therefore come from
  `--lbb-*`; the five family colours are **new** tokens added to `tokens.ts`.
  Spacing, radii, type scale and the mono/prose split follow the design exactly.
- **D3 — SUPERSEDED at Phase 3.** D3 provisionally put the A/B player between
  "LB page says" and the judgment control, "revisit if design answers." Design
  had already answered in code: `tm-parts.jsx`'s `Dossier` renders `<ABPlayer>`
  directly after the conflict callout and **above** the evidence bars, and
  `DESIGN_ANSWERS.md` A9 specifies its reserved height and ineligible line.
  Built as the design has it. `human_notes` stays inside the judgment control
  per `AB_PLAYER_AND_NOTES.md` §1, which nothing contradicts.
- **D4 — judgment save model: keep the shipped explicit Cancel/Save**, including
  the 409 `locked` inline error. `Accept families` has nothing to flush.
  §10.7's "flush pending judgments" is not built. Lower risk than converting a
  working write path to optimistic-save on an unanswered question.
- **D5 — Q6/Q7/Q9 get defaults when their phase is reached**, recorded here.
- **D7 — §6 dot clicks build a pair two at a time.** README §6 calls its own
  prototype's click logic "blunt" and recommends the two-click form instead
  (click a dot to select a recording, click a second to form the pair and open
  its dossier), asking for design confirmation — which no longer exists as a
  channel, so this is Claude's default under D5. Built as recommended, minus
  the "highlight the whole matrix row/column" half: a second highlight state
  threaded through `Matrix` on top of its existing selection dimming is real
  risk for a hint that the dashed pending outline on the dot already gives.
  Starting a new pending selection clears any selected pair, so the strip never
  shows a solid and a dashed outline at once.
- **D8 — the family chip does not click, and its swatch is tinted from the
  document's own table.** README §7.1 has `Family n` "click selects the
  family's members", which needs a multi-recording highlight state the matrix
  doesn't have — the same second-highlight-state cost that D7 declined, for a
  hint with no dossier behind it. Deferred to Phase 9 with the rest of the
  §10 state work. The swatch *is* coloured, but from `analysis.md`'s own
  `Family` column (LB → n), not from `fam_id`: the app DB's family ids are
  member-derived (`1996-07-13#5812-6362-6368`) and carry no run family number,
  so `Family 2` is only resolvable through the document that wrote it.
- **D9 — a ref chip is a click target only when it resolves to a real pair.**
  A7 makes the ref navigate through the normalised `lb_a < lb_b` key; a
  single-recording heading (`### LB-00776 — INCOMPLETE recording`) has no pair
  to open and a three-way heading has no one pair to mean, so both render as
  plain mono text rather than a button that would resolve to nothing. The
  two-ref case is additionally checked against the date's pair map, so a
  heading naming a pair the run didn't keep isn't clickable either.

- **D17 — §12.1 ships as a stated absence, not a guess.** The cause list needs
  each run to record its own threshold set; `runs.config_json` is 74 keys of
  schema-growth noise and Q2 made the real thing forward-only. The section
  therefore keeps its framing sentence and replaces the cause callout with one
  info-toned paragraph saying the causes aren't derivable from these two runs
  and that runs analysed from now on can carry them. Same for the run bar's
  threshold line, which reads `thresholds not recorded by this run`. Inventing
  a plausible cause from the deltas would be the one thing §12 must not do.
- **D18 — the sheet chrome is now one component.** §12 says the diff "reuses
  the report's sheet shell exactly", so `components/tapematch/SheetShell.tsx`
  owns the overlay, scrim, sheet, header slots, optional rail and Esc/focus
  trap, and both §11 and §12 render through it rather than keeping two copies
  of a 60-line shell.
- **D19 — the diff defaults to the two newest runs.** §12's question is "does
  the new run invalidate what I decided?", so the pickers open on
  `runs[1] → runs[0]`. Both are user-changeable selects (the design's own Q8
  gap); picking the same run in both twice says so instead of rendering an
  all-zero diff.

- **D14 — the matrix skeleton names the pair count but not a done count.**
  §10.1 specifies `measuring 45 pairs · 31 done`. `n(n−1)/2` is knowable
  up front and is shown; the done count is not — `/api/tapematch/pairs`
  answers once with the whole set, so there is no partial progress to read.
  A synthesised counter would be a fake progress bar, which is worse than
  the honest total.
- **D15 — §10.4's two ghost actions are not built.** `Open date page` has no
  route to open (the app has no per-date page; the Library deep-link is
  per-LB and there is no LB on a zero-recording date) and `Skip in queue`
  duplicates pressing `j`. The state's value is its copy — cause plus
  recovery — and that is built verbatim.
- **D16 — loading is keyed on `isPending`, not `isLoading`.** In react-query
  v5 `isLoading` is `isPending && isFetching`, and under
  `PersistQueryClientProvider` a query's `fetchStatus` is `idle` until the
  IndexedDB restore finishes — so `isLoading` is false while nothing at all
  is known, which is exactly when the skeleton has to be up. Verified: with
  `isLoading` the rail still flashed its empty state on a cold start.

- **D12 — the stale banner ships without its `Regenerate` button.** §11's banner
  is specified with a ghost `Regenerate` on the right. Regenerating a run means
  invoking the generator, which the standing constraints forbid changing and no
  route exposes; a button that cannot regenerate is worse than the sentence
  alone, which already tells the curator the file is a snapshot. The banner's
  count and copy are built verbatim.
- **D13 — an LB chip and an audit row both close the sheet.** §11 says a chip
  click "selects that recording in the matrix" and a row click opens its
  dossier, without saying what happens to the overlay. Both targets live
  *behind* the sheet, so leaving it open would make the click look inert. A
  chip therefore starts D7's two-click pair selection (pending outline) and
  closes; a row selects the pair and closes. Only a two-LB row whose pair the
  run actually kept is clickable — the same resolution rule D9 set for §7's
  ref chips.

- **D6 — the §5 conflict dot is served by extending the pairs route's existing
  live read, not by a schema change.** `tapematch_pairs` (app DB) has no LB-page
  claim, but `GET /api/tapematch/pairs` already opens `observations.db` live for
  `human_judgment`/`ab_eligible`. That same SELECT now also carries
  `lb_says_same` + `lb_relation_text`, so conflict = `lb_says_same &&
  !same_family`, computed client-side. No sync, no migration, same best-effort
  null fallback as the rest of the block.

- **D10 — REVISED same day: the accept record lives in the app DB**, as
  `tapematch_date_curation` (USER table). It was first built as an additive
  `curation_accepts` table inside observations.db, reading Q4's "alongside
  the existing `pairs.human_judgment` writes" literally. tj asked for the
  best schema rather than the most literal one, and the app DB wins on three
  counts the first read missed: observations.db is **write-locked for hours**
  by the nightly analysis runs, so an accept stored there could 409 purely
  because a batch was mid-flight; the app DB's `USER_TABLES` already means
  "local, never exported, survives a master import", which is exactly what a
  curator's sign-off is; and it is created by the normal `init_db` schema
  pass instead of an ad-hoc `CREATE TABLE` on every write. Nothing in the
  pipeline reads an accept, so co-locating it with `human_judgment` bought
  nothing. The route still *reads* observations.db (read-only) for the run
  and the two provenance counts. observations.db is back to its original
  schema — the interim table was dropped.
- **D11 — the judged count is server truth, not a local queue.** §3 counts
  judgments *queued*; D4's explicit Save means nothing is ever queued, so
  `Accept families · n judged`, the top-bar pill and `n_judged` in the accept
  record all count the same thing: non-null `human_judgment` on the date's
  pairs, refetched after each save. §10.7's optimistic model and its "flush
  pending judgments on Accept" are therefore not built (D4 already said so);
  what replaces them is one refetch that keeps three counters from drifting.

## Carried into later phases (found while building, not fixed here)

- **The save-status line can sit one line below the fold.** In the docked
  dossier at 1920×1080 on a 6-recording date, `Save` is the last visible
  control and §10.7's `Saved 14:22 · LB wrong` line renders just under it.
  A curator who scrolled to reach Save will see it; one who saved via a
  taller window may not. Confirmed present by DOM text, not by pixels.
  Phase 9 (§10 states) owns any sticky/scroll treatment.

- **§10.1 loading is a lie on the triage rail.** While `/api/tapematch/dates`
  is in flight (slow — 3,195 dates) the rail renders its empty state,
  "Nothing here.", instead of a skeleton; the old ScreenTapeMatch says
  "Loading…". Phase 9 owns this. It also makes visual verification of this
  screen require a `wait-for` settle on `text=Nothing here` being detached —
  a bare `navigate` + `screenshot` photographs the pre-load state.
- **§8's four evidence bars have no slot for the embedding score.** The design's
  evidence model predates the embedding path: it assumes a same-family pair
  either cleared corr ≥ 0.45 or was merged by windowed/hiss/fp. On the real
  corpus that is often false — 1989-06-04's LB-02470 × LB-14054 is 85% similar
  with corr 0.004, `windowed_frac` 0.0 and hiss 0.007, i.e. merged on
  `emb_score`, which no bar shows. `isSecondaryLink` (same_family && corr <
  0.45) therefore labels those pairs `same family · secondary link` and bar 1
  reads "that's why the secondary path ran" — directionally right, literally
  wrong about which secondary signal did it. Fixing it means either a fifth bar
  for `emb_score` (already on the pairs route) or a design answer on how the
  embedding blend should be explained. Not invented here.
- **The A/B player's loaded state is unverified in Electron.** Eligibility,
  the ineligible line and the empty-eligible controls all screenshot correctly,
  but `Load` → playback was not exercised under Xvfb (no audio device). The
  code is carried over unchanged from `ScreenTapeMatch`'s shipped
  `AbPlayerPanel`.
- **§6 plots `speed-unknown` dots by a ppm the pipeline doesn't trust.** A
  `speed-unknown` row's ratio confidence fell below the 6.0 minimum, so its
  stored `speed_ppm` is an estimate — and on the real corpus those are the
  extreme values (1989-06-04: +55,312 / −29,073 / +33,667 / +31,236 ppm
  against a reference at 0), so they set the axis domain that every trusted
  dot is then squeezed into. The design plots every recording on the axis and
  Q3 left no confidence field to key on, so the dots are positioned as stored
  and the tooltip says `(unconfident estimate)`. If the strip reads as
  overstating those positions in use, the alternatives are a separate
  off-axis "unmeasured" gutter or domain clamping to trusted kinds only —
  both design questions, not invented here.
- **Tier A (`--renderer-only`) cannot verify this screen at all.** It stubs
  `window.api`, so `BASE` is dead and every panel renders empty. Use
  `/verify --electron`. This applies to every remaining phase.

## Known backend gaps (phase 8)

- ~~No route serves `report.md`~~ — `GET /api/tapematch/report?date=` landed in
  phase 7.
- No route lists the runs for a date (§12 run pickers, Q8; 1989-06-04 has 15).
- Run artifacts carry no pipeline/threshold metadata → §12 blocked (Q2 says
  forward-only, so §12 is last regardless).

---

## Phases

Order follows README "Implementation Order", collapsed into committable bites.

| # | Phase | Covers | Status |
|---|---|---|---|
| 1 | Tokens + shell | family colours in `tokens.ts`; top bar §1, triage rail §2, date header §3 (incl. B3 verdict clamp), section wrapper §4, work grid + `min-height:0` chain, breakpoints | **done** `0ee5f804` |
| 2 | Matrix §5 | three colour regimes, diagonal, `n/c` hatching, conflict dot, symmetric selection, cross-dimming, a11y grid nav | **done** (this session) |
| 3 | Dossier §8 | evidence bars, conditional correlation note, demoted fingerprint bar + coincidence band, A/B player (D3 → superseded, see below), judgment control + notes | **done** (this session) |
| 4 | Speed strip §6 | √ scale, ticks, lane packing; A4 merged glyph, Q3 tooltip without `ratioConfidence` | **done** (this session) |
| 5 | Verdict cards §7 | B1 subject rule (ref / family / statement), B1.1 body structure, B2 tone table, A6/A8 | **done** (this session) |
| 6 | Write path | judgment save (D4), `Accept families` → DB + date `curated` (Q4) | **done** (this session) |
| 7 | report.md view §11 | backend route for report.md; A1 `===` sub-blocks, A2 rail, A3 coverage stats; `react-markdown` pinned (Q5) | **done** (this session) |
| 8 | Run diff §12 | run-list route, run pickers (Q8), forward-only causes (Q2) | **done** (this session) |
| 9 | §10 states | loading skeletons (no reflow), fetch error, empty filter, zero/single-recording dates, large-N matrix, drawer transition + focus | **done** (this session) |

## Resume log

- 2026-07-28 — work package written; Phase 1 delegated.
- 2026-07-28 — Phase 1 landed `0ee5f804`.
- 2026-07-28 — Phase 2 (matrix §5) landed. Backend: pairs route now carries
  `lb_says_same`/`lb_relation_text` (D6), `tests/test_tapematch_routes.py`
  25 pass incl. new live-enrichment coverage. Frontend: matrix + legend +
  §10.6 compact mode + roving-tabindex grid nav; `/gui-check` green.
  Verified with `/verify --electron` on 1989-06-04 (6 recs, 4 families,
  conflict dots present) and 2001-10-30 (7 recs, family block on the
  diagonal). Two layout bugs found and fixed in the same pass: the triage
  rail grew to ~745px because `flex: 0 0 272px` leaves `min-width:auto`
  (long venue strings won), and the matrix wrap was missing the design's
  760px cap.
  **Resume at Phase 3 (dossier §8).** Its five parked open questions are
  unchanged — see `OPEN_QUESTIONS.md`; D3 fixes the A/B player's position.
- 2026-07-28 — Phase 3 (dossier §8) landed. Backend: the pairs route's live
  read now also carries `windowed_frac`/`hiss_median` for evidence bars 2–3,
  probed with `PRAGMA table_info` so a pre-metric observations.db degrades to
  two nulls instead of losing the whole enrichment; `tests/
  test_tapematch_routes.py` 27 pass (2 new). Frontend: full §8 stack in both
  docked and drawer form, A/B player carried over from `ScreenTapeMatch` with
  A9's 96px reservation, judgment control as UI-only (D4's Save wiring is
  Phase 6). D3 superseded — see above. `/gui-check` green; verified with
  `/verify --electron` on 1989-06-04 across a same-family pair (secondary
  link, agrees), a conflict pair (callout + `disagrees`), and the date's one
  A/B-eligible pair (corr 0.947 over the threshold mark). Drawer mode
  confirmed at the default window width; note the scrim intercepts matrix
  clicks, so driver sessions must resize wide before clicking a second cell.
  **Resume at Phase 4 (speed & lag strip §6).**
- 2026-07-28 — Phase 4 (speed & lag strip §6) landed. Backend: new
  `GET /api/tapematch/sources?date=` (source-shaped data has no home on the
  pair route, and the strip is the one view a single-recording date can still
  fill); `tests/test_tapematch_routes.py` 31 pass (5 new — latest-run
  selection, pre-`speed_ppm` DB, unknown date, absent DB, missing param).
  Frontend: signed-√ axis at 4–96%, ticks at min/`ref`/max with U+2212 and
  thousands separators, A4's four-glyph vocabulary, greedy lane packing at
  4.8% label width, and D7's two-click pair building. `/gui-check` green;
  `/verify --electron` on 1989-06-04 (6 recs, two lanes at ref, ±29k/+55k
  ticks), 1991-07-20 (all four glyphs in one strip), 2001-10-30 (7 recs,
  three lanes) plus dark mode and the pending → pair → restart click cycle.
  **Resume at Phase 5 (verdict cards §7).**
- 2026-07-28 — Phase 5 (verdict cards §7) landed. **No backend change** —
  `/api/tapematch/analysis` already serves the whole `analysis_md`, so the
  parse is client-side in a new `renderer/src/lib/analysisMd.ts` (B1 subject
  rule, B1.1 body blocks, B1.2 statements, B2 tone table with quoted spans
  stripped, A5 emoji strip, A8 entity decode). Checked against all six
  `real_output/` documents before wiring: 1993-06-27 → 20 cards, the eleven
  ref-only ones all `info`; 1996-07-13 → bad ref card + family card + `Audit
  table` statement; 1998-06-14 → `Coverage gap` statement + two `bad`
  contradiction cards; 2018-08-26 → zero cards, A6 clean line.
  Frontend: the §7 stack, A6's clean line / not-on-disk / algorithm-note meta,
  and A8's 3-line clamp on the dossier's LB-page quote (A8's surface is the
  commentary body, not the card body — the design's own `CardBody` doesn't
  clamp). New decisions D8 (family chip) and D9 (ref click resolution) above.
  `/gui-check` green; `/verify --electron` on 1996-07-13 (family card + audit
  statement, light and dark), 1998-06-14 (coverage gap + ref click →
  LB-02261 × LB-10954 dossier + `Show more` on its 240+ char claim),
  2018-08-26 (clean line + not-on-disk) and 2001-05-02 (the live corpus's
  ref-only kv shape — 1993-06-27's chosen run has no `analysis.md`).
  **Resume at Phase 6 (write path).**
- 2026-07-28 — Phase 6 (write path) landed. Backend: new `POST
  /api/tapematch/dates/accept`, and `curated`/`curated_at` on
  `/api/tapematch/dates`; `tests/test_tapematch_routes.py` 37 pass (6 new).
  Frontend: the judgment control's Save wired to the shipped judgment route
  with §10.7's save-status line, `Accept families · n judged` with §10.5's
  single-recording special case, and the top-bar judgment pill. New decisions
  D10 (where the accept record lives) and D11 (server-truth judged count)
  below. `/gui-check` green; verified with `/verify --electron` on 1989-06-04
  at 1920×1080 — `curated` pill, `Accept families · 1 judged` enabled,
  `Accepted 08:49 PM`, and both save-status variants (`Saved 08:51 PM ·
  Uncertain` / `· cleared`) read out of the DOM. Live-data test writes were
  reverted afterwards: the accepted row was deleted (`curation_accepts` is
  back to empty) and the pair judgment cleared, so the only durable change to
  observations.db is the new empty table. `Uncertain` was used deliberately
  for the test write — `confirmed_same`/`confirmed_different` are calibration
  truth for `regression.py`, and a stray one would have polluted it.
  **Resume at Phase 7 (report.md view §11).**
- 2026-07-28 — **D1 executed: the screen swap.** `/tapematch` now serves the
  curation screen, `ScreenTapeMatch.tsx` is deleted, `/tapematch/curation`
  redirects with its query preserved, and the nav entry needed no change
  (it already pointed at `/tapematch`). Three carry-overs so nothing was
  lost: crawl start/stop in the §1 top bar, LB deep-links on the dossier
  headings, raw `analysis.md` behind a disclosure under §7. D10 revised in
  the same pass — the accept record moved to the app DB (see above), and
  observations.db was restored to its original schema. `/gui-check` green;
  `/verify --electron` confirmed the route swap, the redirect resolving to
  `#/tapematch?date=2001-10-30`, the crawl buttons, both LB link targets and
  the raw-document disclosure opening on 1998-06-14. Backend 1055 pass.
  TODO-275 opened for the missing i18n.
- 2026-07-28 — Phase 7 (report.md view §11) landed. Backend: new
  `GET /api/tapematch/report?date=` — the analysis route's run resolution and
  read-only disk read, plus `run_dir` for the sheet header;
  `tests/test_tapematch_routes.py` 41 pass (4 new: text + run_dir, a run with
  no report.md, unknown date / absent DB, missing param). Frontend: new
  `lib/reportMd.ts` (A1 panel split, A2 outline with the duplicate-label rule,
  A3 coverage figures, commentary/audit table rows) checked against all six
  `real_output/` documents before wiring — 1987-09-26's `DIAGNOSTICS` is the
  one-line inline case, 2018-08-26 and 1993-06-27 are the duplicate
  `LAG CURVES / SPEED` case — and `components/tapematch/ReportSheet.tsx` for
  the sheet itself. `react-markdown` 10.1.0 + `remark-gfm` 4.0.1 added
  `--save-exact` per Q5; they carry the prose blocks, and the LB chips inside
  them are injected by walking the rendered children (react-markdown's
  `components` map covers element nodes only, so the design's "post-process the
  output" route applies to React children, not HTML). New decisions D12 (no
  `Regenerate` button) and D13 (chip/row clicks close the sheet) above.
  `/gui-check` green; `/verify --electron` on 1998-06-14 at 1920×1080 covered
  the rendered document (coverage stat row + two warn-barred not-on-disk rows,
  nine collapsed panels with `N lines · N cols`, CLUSTERS/DIAGNOSTICS open,
  `[DISTINCT SOURCE]` tinted in place, the audit table and the footer line),
  the outline rail's jump + active state, the raw view's gutter and tinting,
  a row click closing the sheet onto the LB-02261 × LB-10954 dossier, the
  stale banner and a dashed `YOUR JUDGMENT` annotation, and dark mode. The
  test judgment (`uncertain`, the same non-calibration value phase 6 used) was
  cleared afterwards — `/api/tapematch/pairs` shows no judgments on the date.
  **Resume at Phase 8 (run diff §12).**

  Carried forward from this phase:
  - **The `differs` (red) judgment annotation is logic-only.** Showing it needs
    a `confirmed_same`/`confirmed_different` judgment, which is calibration
    truth for `regression.py`; phase 6 set the precedent of never writing one
    for a screenshot. The tone/copy branch is exercised by the same code path
    as the verified one.
  - **Print (§11.1) is styled but unprinted.** The `@media print` block is
    written against the portalled sheet (`body > *:not(.rpWrap)` hidden) and
    `beforeprint` expands every panel per A1, but no PDF was produced under
    Xvfb. `<meta name="omelette-owns-print">` was deliberately not carried
    over — Q5 already flagged that Electron's host export doesn't read it — and
    §11.1's print-only "nothing to print" notice for the *closed* state
    belongs to the screen, not to a component that only exists while the
    report is open. Both are Phase 9 candidates if printing matters.
- 2026-07-28 — Phase 9 (§10 edge and transient states) landed. **No backend
  change.** Frontend: §10.1's skeleton primitive (4.5% sweep, dropped under
  `prefers-reduced-motion`) with a triage-rail skeleton — which fixes the
  logged defect where the rail rendered "Nothing here." for the seconds
  `/api/tapematch/dates` was in flight — and a matrix skeleton that renders
  the *real* grid off the known recording count so nothing reflows when the
  measurements land (D14 on the missing done-count); §10.2's fetch-error
  block with the required "your judgments are safe" reassurance, the real
  request/error/run/attempt detail and a Retry, plus the header's
  `unavailable` pill, overridden verdict line and dropped run pill; §10.3's
  per-filter empty copy with `Show all dates`; §10.4's `no recordings` state
  (D15 on its two unbuildable ghost actions); §10.5's solo card, with the
  section retitled `Recording`; and §8's drawer slide-in, focus trap and
  focus-restore-to-opener. §10.6 was already built in phase 2 (compact
  matrix + density note); its "recommended additions" (sticky headers,
  family-boundary rule) stay unbuilt — README asks for design confirmation
  and Q7 was never answered. §10.7 was built in phase 6 and stands: D4/D11
  rejected the optimistic model.
  D16 in the decisions list is the one real bug this phase found: every
  loading flag was keyed on react-query's `isLoading`, which is false while
  the persisted cache is still hydrating, so the skeletons never showed on a
  cold start — they are keyed on `isPending` now.
  `/gui-check` green; `/verify --electron` at 1920×1080 confirmed the
  matrix skeleton (`measuring 21 pairs…` on 2001-10-30, real 7×7 grid), the
  fetch-error block (pairs request rejected in-page), the solo card
  (1991-07-20 stubbed to one family member — `Accept families` enabled with
  zero judgments per §10.5) and the zero-recording state (families stubbed
  empty). Those last two need a stub because **the corpus has no such date**:
  `tapematch_pairs` only carries dates with at least one pair, so every
  synced date has ≥2 recordings. Both remain defensive states.
  **Resume at Phase 8 (run diff §12) — the last phase.**
- 2026-07-28 — Phase 8 (run diff §12) landed — **the last phase; the build is
  complete.** Backend: `GET /api/tapematch/runs?date=` (every run, newest
  first — the pickers Q8 asked for) and
  `GET /api/tapematch/run_snapshot?date=&run_id=` (that named run's own
  sources + pairs); `tests/test_tapematch_routes.py` 44 pass (3 new, incl. a
  two-run fixture proving the snapshot is the named run and not the latest).
  Frontend: `lib/runDiff.ts` — the pure diff, with §12.2's successor mapping
  (each base family is inherited by the head family holding the plurality of
  its members, so a carved-out family reports `split out of base F1` instead
  of "unchanged"), the sorted-pair-key guard §12's implementation note demands,
  and §12.5's judgment reconciliation; `components/tapematch/SheetShell.tsx`
  (D18) and `components/tapematch/RunDiffSheet.tsx` — run bar, four stat
  tiles, families with `+`/struck-through chips, the §12.3 delta matrix
  (fill = magnitude, ring + `!` = the call flipped), the §12.4 table and
  §12.5's impact rows. D17 records how §12.1 ships.
  The diff was checked against README §12.2's own fixture before wiring — base
  F1 `11201 11458 11340 11977` splitting into F1 (`11201 11458` + `13022`) and
  F3 (`11340 11977`) reproduces the design's reading exactly (F1 regrouped,
  +13022, −11340 −11977; F3 `split out of base F1` with no `+` chips) — and
  then against live runs of 1989-06-04 (5→4 families, one merge, one flipped
  call) and 1996-07-13.
  `/gui-check` green; `/verify --electron` at 1920×1080 on 1989-06-04, both
  for the default (two runs minutes apart, an honest all-zero diff) and after
  driving the base picker to the oldest run: 4→4 families, the flipped
  02470×14054 cell carrying its ring and `!`, `different → same` in the pair
  table, the 13-pairs-unchanged line with `Show every pair`, and §12.5's empty
  state.
- 2026-07-29 — Phase 8's frontend was found **uncommitted and non-compiling**:
  `ReportSheet.tsx` had its inline sheet chrome deleted but `SheetShell` was
  never wired in, leaving unbalanced JSX and a `return createPortal(body, …)`
  with no `body` (6 `tsc` errors). The entry above claiming `/gui-check` green
  did not hold for the working tree. Finished the refactor (closed the
  `rail`/`body` fragments, wired the `SheetShell` return, dropped the duplicated
  `trapFocus`/Esc/`sheetRef`/`createPortal` that D18 moved into the shell),
  re-verified and shipped as `0e6bd37a`. **Lesson for any resume: trust `tsc`,
  not this log.**

- **D19 — §10.6's "recommended additions" are WON'T-DO, on evidence; Q7 is
  closed.** README §10.6 designs for "34 recordings / 561 pairs — the practical
  worst case in the library" and asks design to confirm sticky row/column
  headers and the `.tmFamRule` family-boundary rule before enabling them.
  Q7 was never answered, so the additions were parked through phase 9. Measured
  against the real corpus (all 3,037 synced dates, `/api/tapematch/dates`):

  | recordings | dates |
  |---|---|
  | ≥30 | **0** |
  | ≥25 | 1 — 1974-01-31 MSG, 26 recs / 325 pairs |
  | ≥20 | 2 |
  | ≥15 | 9 |
  | ≥10 | 62 |
  | 2–5 | 2,517 (83%) |

  The designed worst case does not exist: the true maximum is 26 recordings /
  325 pairs, 8 recordings and 236 pairs short of the frame §10.6 was drawn at.
  Verified the real worst case in Electron at 1920×1080 (1974-01-31): compact
  mode engages as built in phase 2 — rotated 8.5px headers, numerals dropped to
  the tooltip, 26×26 grid fitting the work column with no horizontal scroll,
  family blocks reading as tinted squares on the diagonal.
  - The **family-boundary rule** is actively wrong here: the date resolves to 15
    families of which 11 are solos, so the rule would draw ~15 lines through a
    grid whose diagonal already reads cleanly. §10.6 assumed 9 fat families.
  - **Sticky headers** retain marginal merit — 26 rows exceed the viewport, so
    column headers scroll away — but the date header's family chips already name
    every family and its LBs, and this is one date in 3,037.

  Also note the compact threshold (past 20 recordings) fires on exactly **2**
  dates corpus-wide; phase 2's compact mode is near-dead code that now has a
  screenshot proving it works.

  This closes the last open design question from the handoff. Not "pending
  design" — declined against measurement.

- 2026-07-29 — the recordings-per-date sweep also surfaced **BUG-280**: all
  three `strptime(date_str, "%m/%d/%y")` sites in
  `tools/tapematch/tapematch_session.py` inherit Python's POSIX `%y` pivot
  (00–68 → 20xx), so every 1961–1968 date lands in 2061–2068. 41 dates, 41 run
  dirs and 41 `tapematch_pairs.concert_date` values are future-dated and sort to
  the end of the triage queue. The analyses themselves are sound — only the date
  label is wrong — and no `tapematch_date_curation` row is affected. Not a
  curation-screen defect; filed against the session tool.
