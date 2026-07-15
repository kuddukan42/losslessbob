# WORK_PACKAGE_2026-07-14 — queue for the week of 7/14

Drafted by Fable 5 at the 07-13 window edge (5% usage left). Successor to
`complete/WORK_PACKAGE_NEXT.md` (its LISTENING window landed 100%: TODO-215,
TODO-230, TODO-231 all closed). Strike rows as they land.

---

## State at handoff (2026-07-13)

- **Uncommitted on main: today's entire 07-13 session** — TODO-225 setlist
  fingerprint review queue (`backend/setlist_fingerprint.py`, ScreenFingerprint,
  tests), TODO-158 batch forum posting, TODO-157 torrent auto-create, TODO-159
  LBDIR verify gate, TODO-108 header fix, TODO-154 docs close, plus the
  instructions/ reorg (unified-library + library → `complete/`, SHARING_FEATURE
  → `future/`), instructions/README.md index fix, and BUG-248 closure.
  **First action of next session: review + commit this** (likely 2–3 commits by
  scope), then `/backend-restart` so :5174 serves the fingerprint routes.
- Bookkeeping is otherwise current: CHANGELOG/TODO/TODO_DONE were updated
  in-session on 07-13; BUG-248 closed 07-13 (fix had shipped 07-11).
- Untracked `backend/taper_review.html` — confirm it's intentional (TODO-213
  scaffolding?) before committing; don't let it ride along blind.

## Manual verification checklist (tj — can't be auto-tested)

Recent shipped work that only ears/eyes can sign off:

- [ ] **A/B player (TODO-231)**: in ScreenTapeMatch pick an `ab_eligible` pair,
      load a clip — does audio actually play now (CSP fix), does the A/B toggle
      switch instantly, do the two sources sound time-aligned?
- [ ] **Song index (TODO-230)**: browse `/songs` — search a few songs, sanity of
      best-first ordering, LB deep-link jumps to the right Library entry.
- [ ] **Fingerprint review queue (TODO-225)**: open the new screen, check the
      suggested show identifications look sane, accept/reject one and confirm it
      persists after reload.
- [ ] **Forum posting chain (TODO-157/158/159) — OUTWARD-FACING, verify
      carefully**: post one test LB (preview before submit); confirm the LBDIR
      verify gate blocks a failing entry; confirm the torrent is created and
      appears in qBittorrent; then try a small batch paste.
- [ ] **Collection header (TODO-108)**: visual check, incl. German locale (long
      strings were the trigger).
- [ ] **About credits (TODO-226B)**: cards render, bobserve/setlist.fm/
      bobdylan.com links open.
- [ ] **TapeMatch v2 (TODO-215)**: judgment panel saves, crawl start/stop
      buttons behave, drag-resizable DetailPanel.
- [ ] **Geocoder GUI (TODO-224/229)**: run it, watch skipped_not_concert and
      stopping states render.
- [ ] **TODO-213 input (gates the High-priority session below)**: collect
      concrete wrong TAPER-badge examples in the Library — which LB, what the
      badge said, what it should say. 3–5 examples is enough to start tracing.

## Standing preempt (any window)

~~**TODO-213 (High) — taper-badge data curation.**~~ **CLOSED 2026-07-14 (tj's
call).** The attribution-curation half shipped; the badge weight-tuning half was
cancelled as unnecessary — only ~22 taper-badge conflicts remain, all
series-vs-series and well understood, owned by TODO-234 (family over-merge), not
a weight-tuning problem. No standing preempt anymore.

## Session 1 — housekeeping + data-safety (small bite)

1. ~~Commit the 07-13 backlog (see State), restart backend.~~ **DONE 2026-07-14**
   — the uncommitted tree was actually a newer *complete* inflight session
   (the 07-13 backlog had already shipped in ea7f82e4/ab29045b). Verified
   (ab_clips 37 / taper 25 / gui-check PASS) and committed as two scoped
   commits: `674968d6` A/B listening (TODO-232 closed, TODO-233 pt1) +
   `398b498f` TODO-213 taper conflict queue. Backend restarted; new routes
   confirmed live (kind=bad→400, kind=mention→0, kind=series→22).
2. ~~**BUG-246 remaining audit**~~ **DONE 2026-07-14 — BUG-246 CLOSED.** Swept
   all db_path-taking writers. Two unguarded matches found + fixed with the
   picks-style `_run_write` path-match guard: `taper_attribution._write_attributions`
   (wipe class) and `flat_file.apply_flat_file_release` (desync class); the
   single-row taper confirm/reject/mark_unresolved routed through it too.
   tapematch_sync (same-conn, no queue), parse_lineage/scrapers/geocoder/importer
   (upsert-only/external-driven), song_index/setlist_fingerprint (already guarded)
   = clean. Regression test added; 42 taper+show_picks tests pass.
3. Opportunistic: BUG-249 repro attempts (2–3 full pytest runs, note the
   preceding tests).

## Session 2 — TODO-213 curation pass — CANCELLED 2026-07-14

Closed by tj's decision (see Standing preempt above): the taper badge state is
trustworthy enough, the ~22 remaining conflicts are series-vs-series (TODO-234),
and the weight-tuning pass is not worth doing. Not a blocker on anything below.

## Session 3 — TODO-222: setlist.fm city coords + bounded venue search

Cheapest well-specified win in the geocoder chain: store the city coords the
API already returns (column adds w/ PRAGMA guards), then the bounded Nominatim
venue query. Sets up TODO-223.

## Session 4 — pick one

- **TODO-223 venue gazetteer** (natural follow-on to Session 3), or
- ~~**TODO-228 Olof 2022+ PDF chronicles**~~ **DONE 2026-07-14 — pivoted mid-session.**
  The PDF premise didn't hold (2013+ chronicle PDFs have no per-show setlists,
  confirmed by extracting real 2022/2023 PDFs — calendar + itinerary table only).
  bobserve.com's own setlist database (`/setlist?event=N`) is the real 2022+
  source; built `backend/bobserve_fetcher.py` + `backend/bobserve_parser.py`
  instead. Full 2022-2026 crawl: 391 events / 6137 songs, 0 fetch errors, 18
  legitimate partials (mostly not-yet-played 2026 shows). Feeds TODO-224/225
  with no further wiring. Scraping bobserve.com/setlist was cleared with tj
  despite its robots.txt explicitly disallowing ClaudeBot — see session note.
- **TapeMatch post-7/12 rescore** — CALIBRATION_PROGRESS.md tail has three
  queued levers (corroborating-signal gate, staircase-pair-scoped 0.40 bar,
  `cluster_threshold_staircase` toward 0.47). Now past its 7/12 gate; needs a
  dedicated window, never concurrent with a live session.

## Session 5 (2026-07-14) — TODO-214 taper fingerprints: DESIGN DONE, impl not started

Session ended at usage cap right at the implementation-delegation step. Zero code
changed; no session-close needed. Full design below is decided (Fable) — next session
should hand it straight to a sonnet subagent and then calibrate. tj's directive:
**exclude the TODO-234 problem families, then build 214.**

Facts verified this session (don't re-derive):
- Phase 3 is BACKEND-ONLY. `inferred` tier already handled end-to-end: API
  `confidence=` param (app.py:5004), Library filter + DetailPanel evidence (gui_next),
  `_summarize` counts it, pill stays confirmed-only.
- Live data: 2,657 confirmed + 4,045 propagated sources; 22 conflict=1 rows
  (all series-vs-series, TODO-234); 15,207 entry_lineage rows; 15,184 entries with
  description >50 chars (load descriptions from `entries` directly, NOT via lineage join).

Design (implement exactly; module `backend/taper_fingerprints.py`, stdlib only):
1. Tokenize: `[a-z0-9]+(?:['&+-][a-z0-9]+)*` on lowercased text; drop pure digits +
   len<2.
2. Profiles: weighted log-odds w/ informative Dirichlet prior (Monroe "Fightin'
   Words"); constants MIN_PROFILE_ENTRIES=8, MAX_GLOBAL_DF=0.10 (DF filter replaces
   stopword lists), PRIOR_MASS=500.0, PROFILE_TOP_K=40 tokens with z>=1.96, weight=z.
   Exclude the taper's OWN alias tokens (from `_KNOWN_TAPER_ALIASES`, db.py) from its
   profile — kills mention-tier circularity.
3. Scoring: sum of distinct matched profile-token weights; MIN_MATCHED_TOKENS=3;
   argmax profile wins if score >= INFERRED_SCORE_THRESHOLD (placeholder 15.0 —
   calibrate on live DB before shipping; spec bar >=90% precision). Ties → taper-name
   sort; all iteration sorted (idempotency, spec §7).
4. **Poisoned-component exclusion (tj's ask):** DSU (reuse `_DSU`) over fam cliques +
   same_as + derived_from adjacency, same edges as `_propagate_strong`. Any component
   containing conflict=1 or curator-`unresolved` lb contributes NO source docs.
5. Sources: attrs tier in (confirmed, propagated), conflict=0, not poisoned, has
   description. Score only entries with a description and NO attrs row. Evidence: one
   record kind='fingerprint', detail='matched tokens: <top10 by weight>',
   score=round(,2). Never overwrite existing attrs.
6. Integration: call `infer(...)` in `recompute()` AFTER `_propagate_weak`, BEFORE the
   second `_apply_rejects`/`_apply_unresolved` pass (so curator suppressions gate
   inferred rows; L2 never feeds L1). Minimal refactor: extract `_compute_layers01()`
   so a new `--calibrate-fingerprints` flag in tools/attribute_tapers.py can reach the
   intermediate attrs.
7. `calibrate()`: deterministic holdout = confirmed source lbs with lb%5==0; build
   profiles without them, score them, report precision/coverage per threshold
   (5,10,15,20,25,30,40).
8. Tests: NEW backend/tests/test_taper_fingerprints.py (conventions from
   test_taper_attribution.py): tokenizer, >=8-doc gate, DF filter, own-alias exclusion,
   <3-matches/below-threshold no-ops, poisoned-component exclusion, no-overwrite,
   recompute integration (inferred rows land; reject suppresses; run-twice idempotent).
   Verify: `.venv/bin/python3 -m pytest backend/tests/test_taper_fingerprints.py
   backend/tests/test_taper_attribution.py -q` (not the full suite).

Resume plan: (1) sonnet subagent implements 1–8 verbatim; (2) Fable reviews diff;
(3) run `--calibrate-fingerprints` on live DB, set INFERRED_SCORE_THRESHOLD from the
>=90%-precision row (prefer higher threshold on ties — precision beats recall);
(4) full recompute + spot-check ~10 inferred rows' evidence; (5) /session-close
(TODO-214 → done; note threshold + calibration table in the entry).

## Session 6 (2026-07-15) — TODO-214 BUILT + CALIBRATED; shipping gated OFF
### DECIDED (tj, 2026-07-15): option 1 — leave disabled, revisit later.
TODO-214 closed (won't-ship), spec moved to instructions/complete/. The
mechanism, tests, and `--calibrate-fingerprints` harness stay in the tree;
flipping `taper_fingerprints.LAYER2_ENABLED` (after a rare-token gate or a
suggestion-queue rescope, options 2/3 below) is the revisit path.

Implementation is COMPLETE and tested (44/44: 18 new tests in
tests/test_taper_fingerprints.py + 26 existing attribution tests). The Session-5
design shipped with three review fixes (edge-less unresolved lbs now poisoned;
`_compute_layers01` returns rejects; deterministic tie-breaks) and, after
calibration, a substantially hardened gate design:

- **Three gates**: score >= 150 AND top1−top2 margin >= 80 AND winner in the
  *reliable-taper set* (tapers whose own 5-fold cross-val predictions at those
  gates hit >=90% precision with >=10 assignments — recomputed each run, grows
  with curation). Profiles exclude ALL known taper alias tokens, not just own.
- Holdout numbers at shipped gates: **96.2% precision, 23.6% coverage, 12
  reliable tapers**; 93 inferred rows would be written on the live DB.

**Why it is NOT enabled** (`taper_fingerprints.LAYER2_ENABLED = False`;
recompute() skips Layer 2): spot-checks of the would-be rows found systematic
misattributions the holdout cannot detect, across FOUR design iterations
(baseline; +margin+reliability; era-matched backgrounds; gear-token-only
vocabulary). Profiles latch onto confounds that are self-consistent inside the
confirmed set — era/setlist vocabulary (song titles, band-member credits:
dickinson/hiatt/cooder ⇒ "ltd"), description formatting/prose style ("spot"
profile matched function words), and format-spec boilerplate (16bit/44.1khz ⇒
"hide"). Proven errors in samples: LB-6124 ("Taper: Walkin' Dude") → romeo,
LB-16183 ("Taped by: mary_lynch") → dk-wi, LB-13918 ("Recording & Transfer by
Ray Ackerman") → ltd, LB-10270 ("source: hanno") → hide. Estimated true
precision on the real unattributed pool: ~60–75% — below the spec bar.
The one genuinely clean signal: rare rig-chain tokens (hide's
COS-11PTs>CPS161>TCD-D100 / DTC-ZE700>RPD-500 cluster, LB-46xx ≈ 6 rows).

**tj decided: option 1** (kept for the record — the options were):
1. **Accept won't-ship** — close TODO-214 as "built, gated off by calibration
   verdict"; revisit only if/when TODO-213 curation broadens the confirmed set.
2. **Curated-evidence tier** — keep gates + add a "rare-token" requirement
   (matched tokens must include >=2 tokens below a corpus-frequency ceiling),
   which would shrink output to roughly the hide-cluster-quality rows (~10–20)
   at plausibly spec-grade precision. ~1 short session incl. recalibration.
3. **Review-queue instead of auto-write** — write the 93 rows as suggestions
   into a curator queue (like setlist_fingerprint_suggestions), never as attrs.
   Rescopes 214 from "inferred tier" to "curation feed". ~1 session.

Useful artifacts either way: `--calibrate-fingerprints` CLI (gate sweep +
reliable-taper table), an explicit-credit-guard regex prototyped in-session
(vetoes docs crediting unknown tapers; not yet in the module), and the
finding that "holdout precision" overstates this method — any future variant
must be judged by spot-checks on the unattributed pool.

## Parked / explicitly not this week

- TODO-226A BobTalk search (good GUI filler if a session runs short).
- ~~TODO-214 taper fingerprints~~ — un-parked 2026-07-14 by tj; see Session 5 above.
- TODO-212 recording-lens badges, TODO-209 ledger dedup (Low, cosmetic).
- Escalated tapematch analysis backlog (329) — recognized token sink; schedule
  deliberately or not at all.
- `future/SHARING_FEATURE.md`, CC_TRADING_PLAN, CC_CONCERT_RANKER — untriaged
  spec backlog; triage only when the above dries up.
