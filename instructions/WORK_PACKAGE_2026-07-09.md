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
| **Today: unblock** | ✅ DONE 07-09: committed (39687e37 + 0c2d3e1e); crawl launched detached over 2,232 remaining dates — `tools/tapematch/crawl_start.sh` / `crawl_stop.sh` / `crawl_status.sh`, log at `data/tapematch/crawl.log` | Minimal | — |
| **Today: consolidate** | ✅ DONE 07-09: retired 4 specs to `complete/` (ADDON, FIXES, TAPEMATCH_PLAN, WEB_GUI_PLAN — all TODO-050..066 shipped), closed TODO-182 + TODO-203, deferred TODO-204. TODO-209 renumber DEFERRED past window — report reviewed, all 39 ids are archived-entry cosmetics needing manual cross-ref attribution | Low | 182, 203, backlog relief |
| **Today: triage script** | ✅ DONE 07-09: `tools/tapematch/triage_analysis.py` — AUTO/ESCALATE/SKIP classifier; first pass 395 pending → 11 auto-written, 329 escalated (210 are merges needing judgment), 55 incomplete; families synced (2,902, 0 errors). Run before every future `/tapematch-batch` | Low | analysis sink triaged |
| **Day 2: spec steps 1–3** | ✅ DONE 07-09 (commit 7a304abf): TAPER phase 1 (7,817 attributions: 2,643 confirmed / 5,174 propagated / 168 conflicts) + RANKING phase 2 (`show_picks` 15,204 picks / 4,031 dates; `POST /api/derived/recompute` SSE chain per F1) | Medium | 187 |
| **Day 3: spec step 4** | ✅ DONE 07-09 (sonnet agent, Fable-reviewed; uncommitted at close→committed): payload F4 fields, badges, 4 filter views, Picks tab + shared `EvidenceList` (F3); i18n 13 keys × 5 locales; tsc 0 errors, build clean. TODO-181+186 closed, TODO-212 opened (flat-lens remainder), RANKING spec retired to `complete/`. **tj eyeball verdict: pipeline works, badge DATA needs curation — TODO-213 (High) before trusting badges** | Medium-high | 186, 181 |
| **Day 3–4: spec step 5** | ⏭ NEXT SESSION: TAPER phase 2: confirm/reject API (writes MASTER `taper_confirmations`, F2 — schema already shipped), taper pill, DetailPanel section (reuse `EvidenceList` + tab-strip pattern, NOT F4's collapsible sections — see 07-09 CHANGELOG note). Consider folding TODO-213 example-collection into the same session | Medium | 173, 192 |
| **Stretch (budget permitting)** | LISTENING §1 pairs sync + TapeMatch screen v1 (TODO-170), text-sketch first | High | 170 |
| **Fill (idle moments)** | TODO-210 + TODO-184 as small bounded tasks; a few `/tapematch-batch` batches only if triage script leaves ambiguous backlog | Low each | 210, 184 |

Parallel, zero-token: tj's curator review of the 265 census-flagged pairs
(TODO-201) while runs churn. — Update 07-09: batches 1+2 (128 pairs) reviewed,
83 FLIPs tj-approved and applied → `regression_set_v3.json`; remaining 136
duration-only pairs need a different method (partial/incomplete-set judgment).
Rescoring against v3 stays behind the calibration freeze.

## Explicitly deferred past 7/12

Onboarding (spec order puts it after step 5), LISTENING §3+, concert ranker
scoring calibration, TODO-204 probe, trading / sharing / web-GUI specs.

## Session hygiene

Each GUI slot ends with `/gui-next-i18n` + `/gui-check`; every code session ends
with `/session-close`. Spec work follows `SPEC_INTEGRATION_NOTES.md` §2 order and
its F1–F6 amendments.
