# WORK_PACKAGE_2026-07-09 — usage window through 7/12

Agreed plan (Fable 5 + tj, 2026-07-09). Refer here across sessions; strike rows as
they land. Move to `instructions/complete/` when the window closes.

---

## Decisions locked (2026-07-09)

1. **TapeMatch calibration is FROZEN.** Config stands at t_emb 0.75 / 5× cache /
   Rule D shipped. Close or defer TODO-203 (Tier C retrain — Tier C was rejected;
   recommend close) and TODO-204 (MrMsDTW probe — defer, artifacts retained).
   tj still suspects a breakthrough exists — parked, not forgotten: TODO-204 is the
   parked probe, and FABLE_TAPEMATCH_LISTENING_SIGNALS is the untapped signal class
   for a future window.
2. **Production runs start headless now** (machine compute, zero token cost); the
   TapeMatch screen adds monitoring when it lands — runs are not gated on GUI.
3. **Stretch goal = TapeMatch screen (TODO-170)**, not analysis catch-up.
4. **No external design phase** for the screen — text/ASCII sketch in session,
   tj approves, then build against gui_next patterns (tokens.ts, DetailPanel
   collapsible sections, shared EvidenceList per SPEC_INTEGRATION_NOTES F3/F4).
5. Concert ranker gets **no GUI this window** — ranking lands as Library
   badges/filters per FABLE_UNIFIED_RANKING; the CC_CONCERT_RANKER audio-scoring
   brain stays untouched until it has its own calibration window.

## Key numbers (measured 2026-07-09)

- Collection: 16,361 of 16,653 library entries local; 3,306 show dates have ≥2
  local recordings (tapematch-eligible).
- Runs done: 954 dates (1,103 run dirs) → **~2,350 dates remain** (weeks of
  machine compute — start early, let it churn).
- Analyses: 710 of 1,103 runs have analysis.md → 393 pending (biggest token sink;
  attack with triage script, not raw Claude batches).

## Timeline

| Slot | Work | Token cost | Closes |
|---|---|---|---|
| **Today: unblock** | Commit the 25 pending files; start tapematch runs over the ~2,350 remaining dates as a detached background job | Minimal | — |
| **Today: consolidate** | Retire concluded specs to `complete/` (CC_TAPEMATCH_ADDON, CC_TAPEMATCH_FIXES, TAPEMATCH_PLAN, likely CC_WEB_GUI_PLAN), TODO-209 ledger audit, close superseded TODOs (TODO-182 per notes §3; TODO-203 per decision 1) | Low | 209, backlog relief |
| **Today: triage script** | Script that auto-writes `analysis.md` for trivially clean runs (no candidates / all-verdicts-clear), reserving `/tapematch-batch` for ambiguous ones | Low, saves a lot later | shrinks the 393-run analysis sink |
| **Day 2: spec steps 1–3** | Verify LB_KNOWLEDGE.md (TODO-187) → TAPER phase 1 (schema/harvest/CLI) → RANKING phase 2 (picks + chained recompute endpoint). Backend-only, one or two sessions, sonnet-delegation candidates | Medium | 187 |
| **Day 3: spec step 4** | RANKING phases 3–4: Library payload, badges/filters, EvidenceList. Ends `/gui-next-i18n` + `/gui-check` | Medium-high | 186, 181 |
| **Day 3–4: spec step 5** | TAPER phase 2: confirm/reject API, taper pill, DetailPanel section | Medium | 173, 192 |
| **Stretch (budget permitting)** | LISTENING §1 pairs sync + TapeMatch screen v1 (TODO-170), text-sketch first | High | 170 |
| **Fill (idle moments)** | TODO-210 + TODO-184 as small bounded tasks; a few `/tapematch-batch` batches only if triage script leaves ambiguous backlog | Low each | 210, 184 |

Parallel, zero-token: tj's curator review of the 265 census-flagged pairs
(TODO-201) while runs churn.

## Explicitly deferred past 7/12

Onboarding (spec order puts it after step 5), LISTENING §3+, concert ranker
scoring calibration, TODO-204 probe, trading / sharing / web-GUI specs.

## Session hygiene

Each GUI slot ends with `/gui-next-i18n` + `/gui-check`; every code session ends
with `/session-close`. Spec work follows `SPEC_INTEGRATION_NOTES.md` §2 order and
its F1–F6 amendments.
