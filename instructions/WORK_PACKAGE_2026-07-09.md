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
| **Day 3–4: spec step 5** | ✅ DONE 07-09 (commit 947845bd; 3 sonnet agents, Fable-reviewed): TAPER phase 2 — confirm/reject API (MASTER `taper_confirmations`, F2, recompute-equivalent immediate apply), GET single/list routes, confirmed-only Library pill + 2 filter views (review queue per §5), DetailPanel TaperZone (shared `EvidenceList` + tab-strip, curator-gated buttons). i18n 5 locales, 535 tests, tsc/build clean. TODO-213 example-collection NOT folded in (still needs tj's examples); phase 3 fingerprints → TODO-214 | Medium | 173 (192 was already closed) |
| **Stretch (budget permitting)** | ✅ DONE 07-10: LISTENING §1 pairs sync (`tapematch_pairs` 9,037 pairs / 1,094 dates, `similarity_pct` banded blend calibrated on 10,369 real pairs) + TapeMatch screen v1 (tj-approved sketch: date rail / similarity matrix / family chips / analysis.md viewer / crawl strip; read-only). 5 new API routes; 35 tests; i18n 5 locales; tsc+build clean. TODO-170 closed, TODO-215 opened (v2: corrections, run controls, deep-links) | High | 170 |
| **Fill (idle moments)** | TODO-210 + TODO-184 as small bounded tasks; a few `/tapematch-batch` batches only if triage script leaves ambiguous backlog | Low each | 210, 184 |

Parallel, zero-token: tj's curator review of the 265 census-flagged pairs
(TODO-201) while runs churn. — Update 07-09: batches 1+2 (128 pairs) reviewed,
83 FLIPs tj-approved and applied → `regression_set_v3.json`; remaining 136
duration-only pairs need a different method (partial/incomplete-set judgment).
Rescoring against v3 stays behind the calibration freeze.

---

## Phase 2 — surplus schedule (agreed 2026-07-10)

Original package fully landed by 07-10 (all slots incl. stretch). ~2.5 days of
window remain. Decisions (Fable 5 + tj, 2026-07-10):

1. **ONBOARDING P1→P3 pulled forward** into this window — the 07-09 deferral was
   a budget call and the budget didn't get spent. Spec step 7 prerequisites all
   exist (F1 recompute chain, taper confirmations in master, public repo for the
   sitedata release).
2. **TODO-213 (High) stays tj-gated and opportunistic**: tj unsure he can curate
   wrong-badge examples in the next 2 days. If examples arrive, tracing them
   preempts any slot below; otherwise TODO-213 carries past 7/12 as the top
   priority of the next window.
3. Escalated analysis backlog (329, of which 210 merge-judgment) remains a
   recognized token sink — untouched this window.

### Phase 2 timeline

| Slot | Work | Token cost | Closes |
|---|---|---|---|
| **7/10: finish spec step 6** | ~~LISTENING §9 "tonight card"~~ **DONE 07-10** (backend 70392d14, frontend 09e57b11). Shipped: `concert_date_iso` M/D/YY→ISO reconciliation (14,618/15,204 populated; 586 NULL = 'xx' dates by design), `GET /api/picks?date=` + `GET /api/picks/tonight` (?mmdd= override), Home-screen tonight card (random candidate + shuffle, hidden when empty, no deep-links — TODO-215), i18n all 5 locales, `/gui-check` PASS. TODO-212's date-ISO item satisfied; TODO-212 stays open for the Recording-lens badge work. BUG-246 detour done earlier in slot (73266f6b); bug stays open for the same-class audit of other db_path-taking writers: tapematch_sync, parse_lineage, taper_attribution, scrapers. | Medium | step 6 complete ✓ |
| **7/10–11: ONBOARDING P1** | ~~Site-data packaging~~ **DONE 07-10** (55501726): split export `?part=core\|files` + manifest sidecars, `POST /api/sitedata/github_release`; first release published: `sitedata-2026-07-10` (core 24.9 MB `_2`-suffixed asset, files 187 MB, 2 manifests). 581 tests pass. | Medium | spec §7 P1 ✓ |
| **7/11: ONBOARDING P2** | ~~sitedata check/install + onboarding/status~~ **DONE 07-10 a day early** (a9759209, TODO-216 closed): leftover diff reviewed sound, 7 P2 tests written (15/15), live-verified against the real sitedata-2026-07-10 release (status 63 ms, both parts paired). | Medium | spec §7 P2 ✓ |
| **7/11–12: ONBOARDING P3** | ~~Wizard + checklist + copy~~ **DONE 07-10 (824140c6, TODO-217 closed)**: OnboardingWizard 4-step modal (master SSE / sitedata SSE / mounts-pipeline nav / done + F1 recompute), ScreenHome once-per-launch auto-open + checklist resume card, flat-file "Monthly update" + Scraper curator note. `/gui-next-i18n` (5 locales) + `/gui-check` PASS (tsc 0 errors). | Medium-high | spec §7 P3 ✓ |
| **7/10 eve: Olof P1+P2** | ~~fetcher + event parser~~ **DONE 07-10** (tj-directed, off-plan): `backend/olof_fetcher.py` + `olof_pages` (P1), `backend/olof_parser.py` + `olof_events` (P2) per FABLE_OLOF_FILES §6. Full mirror fetched (213 DSN + chronicle pages, 0 errors); DSN corpus parsed: 4,533 events, 99.7% anchor→event, 95% ISO date, event_type split concert 3,879 / session 205 / broadcast 91 / interview 63 / rehearsal 6 / other 293. 5-date archive spot-check PASS (incl. 1966-05-17 Manchester-vs-RAH catch). Also fixed crawl merged-folder crash (`copy_folders` dedupe, uncommitted with rest). NEXT Olof bites: P3 olof_songs → P4 chronicles → P5 surfacing; riders TODO-224/225/226 unblock at P2/P3. | Medium | 162 partial (P1–P2) |
| **7/10: Olof P3** | ~~song/take parser~~ **DONE 07-10 (3c8b9ea3)**: `olof_songs` schema + parser per FABLE_OLOF_FILES §6 P3 — both song-line layouts, take statuses, encore flag, annotation/release range resolution (lineup-guard), dup-position renumbering, idempotent reinsert. 61,708 rows; 97.8% concerts / 95.1% sessions covered. Gate PASS: DSN01225 17/17 takes; DSN11050 19/19 vs setlistfm bd4a956; P2 coverage byte-identical. NEXT Olof bites: P4 chronicles (olof_chronicle + olof_new_tapes + 2022+ appendix setlists) → P5 surfacing; setlist riders TODO-224/225 now unblocked (olof_songs live). | Medium | 162 partial (P1–P3) |
| **7/10: Olof P4** | ~~chronicles parser~~ **DONE 07-10 (0ec45d18)**: `backend/olof_chronicle_parser.py` + `olof_chronicle`/`olof_new_tapes` per FABLE_OLOF_FILES §6 P4 — 1,244 calendar rows (43 yrs), 79 new-tapes rows (17 yrs), 253 ok / 2 partial / 0 error, junk-free, idempotent, DSN untouched. **Finding: 2013+ chronicles are PDF-only on bobserve** → 2022+ appendix path dormant (0 synthetic events, structurally validated on 2002 A.htm); TODO-228 opened (PDF fetch+extract). NEXT Olof bite: P5 surfacing (endpoints, tour-name fallback TODO-153, setlist-vs-folder report, gui_next panel + i18n); spec §8 riders still deferred. | Medium | 162 partial (P1–P4); 228 opened |
| **Small bounded (idle)** | TODO-210 implementation (investigation done 07-09): (a) family-sync conf bump for same-date abs_score-within-0.5 + same-grade shortlisted pairs; (b) "likely duplicate encode" review flag for same-scan-config metric_json-identical same-date pairs (never auto-merge) | Low | 210 |
| **If it fits** | ~~ONBOARDING P4 (README rewrite)~~ **DONE 07-10 (5cf6c1c7, TODO-218 closed)**: README rewritten (Releases-installer quickstart + wizard, data-model table, dev setup), PyQt flow docs retired, ONBOARDING spec → `instructions/complete/`. **ONBOARDING track fully shipped P1–P4.** | Low | spec §7 P4 ✓ |

Preempt rule: tj wrong-badge examples → TODO-213 evidence_json tracing takes the
slot. Parallel, zero-token: crawl keeps churning (1,319 runs / 1,169 dates as of
07-10); check `crawl_status.sh` at session open.

## Explicitly deferred past 7/12

~~Onboarding (spec order puts it after step 5)~~ (pulled forward 07-10, see
Phase 2), LISTENING §3+, concert ranker scoring calibration, TODO-204 probe,
trading / sharing / web-GUI specs. TODO-213 joins this list if tj's examples
don't arrive by 7/12.

## Session hygiene

Each GUI slot ends with `/gui-next-i18n` + `/gui-check`; every code session ends
with `/session-close`. Spec work follows `SPEC_INTEGRATION_NOTES.md` §2 order and
its F1–F6 amendments.
