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

- **D1 — new screen, old one stays.** Built as
  `screens/ScreenTapeMatchCuration.tsx` at route `/tapematch/curation`.
  `ScreenTapeMatch.tsx` keeps working and keeps its nav entry until the new
  screen reaches parity (matrix + dossier + A/B player + judgment write path,
  i.e. end of Phase 6). Retiring it is a separate, explicit step.
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
- **D6 — the §5 conflict dot is served by extending the pairs route's existing
  live read, not by a schema change.** `tapematch_pairs` (app DB) has no LB-page
  claim, but `GET /api/tapematch/pairs` already opens `observations.db` live for
  `human_judgment`/`ab_eligible`. That same SELECT now also carries
  `lb_says_same` + `lb_relation_text`, so conflict = `lb_says_same &&
  !same_family`, computed client-side. No sync, no migration, same best-effort
  null fallback as the rest of the block.

## Carried into later phases (found while building, not fixed here)

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
| 4 | Speed strip §6 | √ scale, ticks, lane packing; A4 merged glyph, Q3 tooltip without `ratioConfidence` | **next** |
| 5 | Verdict cards §7 | B1 subject rule (ref / family / statement), B1.1 body structure, B2 tone table, A6/A8 | not started |
| 6 | Write path | judgment save (D4), `Accept families` → DB + date `curated` (Q4) | not started |
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
