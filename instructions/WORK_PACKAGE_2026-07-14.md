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

**TODO-213 (High) — taper-badge data curation.** Unchanged from last package:
the moment tj supplies wrong-badge examples (checklist item above), tracing
their `evidence_json` preempts everything below. Start with `taper_attributions`
(168 flagged conflicts + `_KNOWN_TAPER_ALIASES` coverage), NOT picks.py weights.

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

## Session 2 — TODO-213 curation pass

Requires tj's examples. Trace each through the Picks-tab evidence trail before
touching any weights/aliases. This unblocks badge trust, the oldest open High.

## Session 3 — TODO-222: setlist.fm city coords + bounded venue search

Cheapest well-specified win in the geocoder chain: store the city coords the
API already returns (column adds w/ PRAGMA guards), then the bounded Nominatim
venue query. Sets up TODO-223.

## Session 4 — pick one

- **TODO-223 venue gazetteer** (natural follow-on to Session 3), or
- **TODO-228 Olof 2022+ PDF chronicles** (extends setlists past 2021; feeds
  TODO-224/225 for recent shows), or
- **TapeMatch post-7/12 rescore** — CALIBRATION_PROGRESS.md tail has three
  queued levers (corroborating-signal gate, staircase-pair-scoped 0.40 bar,
  `cluster_threshold_staircase` toward 0.47). Now past its 7/12 gate; needs a
  dedicated window, never concurrent with a live session.

## Parked / explicitly not this week

- TODO-226A BobTalk search (good GUI filler if a session runs short).
- TODO-214 taper fingerprints (Low; sequenced after 213's curation anyway).
- TODO-212 recording-lens badges, TODO-209 ledger dedup (Low, cosmetic).
- Escalated tapematch analysis backlog (329) — recognized token sink; schedule
  deliberately or not at all.
- `future/SHARING_FEATURE.md`, CC_TRADING_PLAN, CC_CONCERT_RANKER — untriaged
  spec backlog; triage only when the above dries up.
