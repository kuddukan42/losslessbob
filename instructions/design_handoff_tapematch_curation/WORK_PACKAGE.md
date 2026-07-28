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
- **D3 — Q10 (unanswered by design): A/B player sits between "LB page says" and
  the judgment control.** It is evidence, so it belongs with the evidence, and
  the judgment control stays last as §8 specifies. `human_notes` stays inside the
  judgment control per `AB_PLAYER_AND_NOTES.md` §1. Revisit if design answers.
- **D4 — judgment save model: keep the shipped explicit Cancel/Save**, including
  the 409 `locked` inline error. `Accept families` has nothing to flush.
  §10.7's "flush pending judgments" is not built. Lower risk than converting a
  working write path to optimistic-save on an unanswered question.
- **D5 — Q6/Q7/Q9 get defaults when their phase is reached**, recorded here.

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
| 1 | Tokens + shell | family colours in `tokens.ts`; top bar §1, triage rail §2, date header §3 (incl. B3 verdict clamp), section wrapper §4, work grid + `min-height:0` chain, breakpoints | **in progress** |
| 2 | Matrix §5 | three colour regimes, diagonal, `n/c` hatching, conflict dot, symmetric selection, cross-dimming, a11y grid nav | not started |
| 3 | Dossier §8 | evidence bars, conditional correlation note, demoted fingerprint bar + coincidence band, A/B player (D3), judgment control + notes | not started |
| 4 | Speed strip §6 | √ scale, ticks, lane packing; A4 merged glyph, Q3 tooltip without `ratioConfidence` | not started |
| 5 | Verdict cards §7 | B1 subject rule (ref / family / statement), B1.1 body structure, B2 tone table, A6/A8 | not started |
| 6 | Write path | judgment save (D4), `Accept families` → DB + date `curated` (Q4) | not started |
| 7 | report.md view §11 | backend route for report.md; A1 `===` sub-blocks, A2 rail, A3 coverage stats, A9; `react-markdown` pinned (Q5) | not started |
| 8 | Run diff §12 | run-list route, run pickers (Q8), forward-only causes (Q2) | not started |
| 9 | §10 states | loading skeletons (no reflow), fetch error, empty filter, zero/single-recording dates, large-N matrix, drawer transition + focus | not started |

## Resume log

- 2026-07-28 — work package written; Phase 1 delegated.
