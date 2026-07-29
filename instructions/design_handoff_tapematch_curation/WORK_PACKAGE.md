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

## Known backend gaps (become phases 7–8)

- No route serves `report.md` (only `/api/tapematch/analysis` → analysis.md).
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
| 7 | report.md view §11 | backend route for report.md; A1 `===` sub-blocks, A2 rail, A3 coverage stats, A9; `react-markdown` pinned (Q5) | not started |
| 8 | Run diff §12 | run-list route, run pickers (Q8), forward-only causes (Q2) | not started |
| 9 | §10 states | loading skeletons (no reflow), fetch error, empty filter, zero/single-recording dates, large-N matrix, drawer transition + focus | not started |

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
