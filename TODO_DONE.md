# Completed TODO Archive
# Active/open tasks are in TODO.md. Entries here are Done or Cancelled.

TODO-224: Olof as geocoder location source + authoritative concert-type filter
Priority: Medium
Status: Done
Added: 2026-07-10
Closed: 2026-07-11
Description: Rider on TODO-221/222/223; depends on TODO-162 (Olof scraper, spec instructions/FABLE_OLOF_FILES.md) P1-P2 landing. olof_events has venue/city/region/country as SEPARATE clean fields for every event 1956-2021 plus event_type (concert|session|rehearsal|broadcast|interview|other). Use: (1) add olof_events to the geocoder structured-source chain in backend/geocoder.py — slot it directly after bobdylan_shows (cleanly split fields beat comma-soup); build query 'venue, city, region, country'. (2) Make TODO-221's concert-only filter authoritative: when a date matches an olof_event, trust event_type — geocode only event_type='concert'; label sessions/interviews/broadcasts as skipped_not_concert with the event_type recorded in note. (3) Seed TODO-223's venue gazetteer from SELECT DISTINCT venue, city, region, country FROM olof_events WHERE event_type='concert' — the definitive list of venues Dylan played, pre-split by locality.
Parts 1+2 shipped 2026-07-11 (sonnet agent, Fable-reviewed): olof_events in _STRUCTURED_SOURCES after bobdylan_shows (split-field query + city-only cascade variant, concert-preference tie-break); _is_concert_location() returns (eligible, skip_note) with olof event_type authoritative (non-concert -> skipped_not_concert + event_type in note), heuristic fallback unchanged; feature-detected via _table_exists. 12 new tests pass. Part 3 (gazetteer seeding from olof_events DISTINCT venues) deferred into TODO-223 where the gazetteer table gets built.

TODO-229: Geocoder GUI: render skipped count + 'stopping' badge in ScreenScraper
Priority: Low
Status: Done
Added: 2026-07-11
Closed: 2026-07-11
Description: Rider from TODO-219/221 close (2026-07-11): backend now returns skipped and stop_requested in /api/geocode/status and skipped in /api/geocode/stats, but gui_next ScreenScraper.tsx GeocoderStatus/GeoStats TS interfaces don't declare them, so nothing renders. Add the fields, show skipped in the stats row, and switch the run badge to 'stopping' while stop_requested && running. Locale updates via /gui-next-i18n.
Shipped 2026-07-11 (sonnet agent, Fable-reviewed): GeocoderStatus/GeoStats interfaces gain skipped/stop_requested; Skipped row in Cache Stats grid; StripCard badge override shows 'stopping' while running && stop_requested. i18n all 5 locales via DeepL; tsc + build clean; live-verified against restarted backend.

TODO-220: Geocoder cascading fallback on Nominatim miss + query provenance in note
Priority: High
Status: Done
Added: 2026-07-10
Closed: 2026-07-11
Description: PROBLEM: run_batch() (backend/geocoder.py ~432-497) picks ONE structured query (bobdylan_shows -> setlistfm_shows -> dylan_performances -> raw entries.location) and gives Nominatim one shot; venue-level queries often miss (Nominatim is weak on venue names, e.g. 'Abilene Auditorium, Abilene, Texas' -> failed) and the row is stored source='failed' with note=NULL, so it looks like LB metadata was used. FIX: on a Nominatim no-result, cascade: (1) next structured source's string, (2) venue-stripped variant of each structured string (city/state/country only — for bobdylan_shows that is the 'location' column alone; for setlistfm 'city, country'), (3) raw entries.location last. Record every attempted query in note (e.g. 'tried: bobdylan_shows:<q1> | bobdylan_shows-cityonly:<q2>') on BOTH success and failure. Keep 1.1s sleep between every Nominatim call including fallback attempts. Set source to the source that actually succeeded; add suffix '-city' when the venue-stripped variant won and cap its confidence at medium. NOTE: 48/117 rows from the 2026-07-10 run are failed; after implementing, re-run with retry_failed=True.
Shipped 2026-07-11: cascade full structured strings -> city-only variants ('-city' source suffix, confidence capped medium) -> raw entries.location; note records every attempted query on success+failure; 1.1s between all Nominatim calls. Re-ran the 48 failed rows: 17 geocoded, 31 skipped_not_concert, 0 failed remain; coverage 69->86.

TODO-221: Geocoder concert-only eligibility filter (skip studio/compilation/interview entries)
Priority: High
Status: Done
Added: 2026-07-10
Closed: 2026-07-11
Description: DESIGN INTENT: geocoding = 'Bob held a concert at this venue, here is where the venue is'. Only routine single-date concert entries with LB numbers qualify; studio bootlegs, multi-date compilations, interviews, radio/TV do NOT. CURRENT: run_batch() geocodes every distinct entries.location, so '1974 Tour Anthology', '65 Outtakes Compilation', 'ABC TV 20/20 Interview' etc get geocoded or fail-spam (and a date match alone is not a concert test: 'ABC TV 20/20 Interview' date-matches dylan_performances and would geocode to Bob's Malibu home). FIX: in the candidate SELECT / loop of run_batch() (backend/geocoder.py ~386-455), only geocode a location when at least one of its entries has a single clean parseable date (no 'xx', no ranges) AND that date matches a bobdylan_shows or setlistfm_shows row (i.e. a documented show). Everything else: write row with new source value 'skipped_not_concert' (lat/lon NULL, manual_override=0) so it is cached, excluded from the map JOIN, not retried every run, and NOT counted in the errors stat — count separately as 'skipped' in _progress and the /api/geocode/stats payload. Keep manual place_manual() as the escape hatch for edge cases. Consider also skipping locations matching obvious non-venue keywords (compilation, outtakes, interview, rehearsal, soundcheck, demos, various) as a secondary guard.
Shipped 2026-07-11: _is_concert_location() keyword guard + clean-date match against bobdylan_shows/setlistfm_shows (dylan_performances excluded); ineligible rows cached as source='skipped_not_concert', excluded from failed stat, counted as skipped in _progress + /api/geocode/stats. Live run: 31/48 previously-failed rows correctly skipped. Known edge: non-venue text on a documented show date (hotel-room recordings) still passes — place_manual() escape hatch.

TODO-219: Geocoder stop support — stop flag in run_batch + POST /api/geocode/stop
Priority: High
Status: Done
Added: 2026-07-10
Closed: 2026-07-11
Description: BUG: GUI Stop button (ScreenScraper.tsx:797) posts /api/geocode/stop but the route does not exist (silent 404), and run_batch() in backend/geocoder.py has no stop-flag check, so a batch can only be killed by restarting the backend. FIX: (1) add module-level _stop_requested bool + threading.Lock use in backend/geocoder.py; check it at the top of each loop iteration in run_batch() and break cleanly (finally block already resets progress); reset the flag at batch start; also honor it inside the 60s rate-limit sleep (sleep in small slices). (2) add POST /api/geocode/stop in backend/app.py next to /api/geocode/run (~line 5747) that sets the flag and returns current progress; mirror the pattern of /api/bobdylan/stop. (3) expose stop_requested in get_progress() so the GUI badge can show 'stopping'.
Shipped 2026-07-11: stop() flag + sliced 429 sleep in backend/geocoder.py, POST /api/geocode/stop in backend/app.py (GUI Stop button 404 fixed), stop_requested exposed in get_progress(). Live-verified: stop endpoint returns progress dict; flag resets at batch start.

TODO-227: run_crawl.sh: backoff / same-date failure guard to prevent hot crash-loops
Priority: Low
Status: Done
Added: 2026-07-10
Closed: 2026-07-11
Description: run_crawl.sh continues on any exit code other than 75 (queue empty) and 130 (Ctrl+C) with no delay, so an unhandled per-date exception hot-loops forever on the same date (BUG-247 looped ~3 h at ~1.2 s/iteration with full clean+copy disk churn each pass). Add: small sleep between iterations after a failure, and abort or skip-with-log after N consecutive failures on the same date (tapematch_session.py could write the date to a skip list that --next respects).
run_crawl.sh: 30s sleep on failure rc, 3 consecutive same-date failures append the date to data/tapematch/crawl_skip.txt (next_run now honors it + writes crawl_last_attempt.txt), 10 consecutive failures overall abort. Latent stale-$rc bug fixed. Live crawl untouched (mv replacement); guard active from next crawl restart.

TODO-210: Detect exact-quality-match splits as family-matching signal (LB-1594/LB-5065)
Priority: Medium
Status: Done
Added: 2026-07-08
Closed: 2026-07-11
Description: User found LB-1594 and LB-5065 have identical quality ratings and are audibly the exact same recording — only difference is track splits a few seconds apart. Investigate using exact/near-identical quality-score equality as an additional signal in family matching (e.g. as a corroborating feature or a targeted check for split-only duplicates), since a quality-rating match this precise is unlikely by chance for unrelated masters.
  Update 2026-07-09 (investigation done; implementation remains): 1594/5065 are ALREADY in
  family 1996-11-20#1594-5065 (conf 0.0156 — the signal's value is corroborating low-conf
  families, not surfacing new ones). abs_score equality alone is unusable library-wide:
  515 same-date exact-score pairs vs 325,858 cross-date coincidences (>99.8% noise; wider
  tolerances get worse). Full metric_json identity is near-collision-free (13 same-date
  candidates vs 6 cross-date library-wide) but only comparable within one scan config version.
  Recommendation: (a) small confidence bump in the tapematch family-sync conf step when a
  same-date shortlisted pair has abs_score within ~0.5 + same grade letter; (b) surface
  same-scan-config metric_json-identical same-date pairs as a "likely duplicate encode"
  review flag (never auto-merge). 429 same-date exact-score non-family candidate pairs exist;
  the 13 metric-identical ones (e.g. 3136/7538 7/8/78, 3147/7523 7/4/78) are prime curation bait.
Implemented per 07-09 investigation: (a) family-sync conf bump +0.05 when a member pair shares scan_id with abs_score within 0.5 and same grade letter (corroboration only, feature-detected columns); (b) read-only duplicate-encode surfacing — duplicate_encode_candidates(), --dup-encodes CLI, GET /api/tapematch/dup_encodes (15 pairs live incl. LB-3136/7538, LB-3147/7523); never auto-merges. GUI surfacing deferred to TODO-215.

TODO-153: Library/perf screen — backfill good tour names across all dates
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-10
Description: The Library screen's tour column (gui_next/src/renderer/src/screens/ScreenLibrary.tsx,
  `p.tour`) is sourced from setlistfm_shows.tour_name joined onto dylan_performances in
  backend/db.py:2121-2206 (tours dict keyed by date_str, applied at line 2204-2206). tour_name is
  empty for a large share of dates, so the column is blank for most performances. Need a way to
  pull/derive good tour names across all dates — likely requires either a better/secondary tour
  data source beyond setlist.fm, or a manual/heuristic backfill (e.g. date-range-based tour
  era tagging) for shows setlist.fm doesn't have tour info for.
Fallback chain setlistfm → olof_events landed in get_performances (backend/db.py, TODO-162 P5a, commit bd48dd4e): setdefault semantics so setlistfm wins, olof concert rows preferred on multi-event dates. Dated shows with a tour name: 3,783 → 4,540 (+757); Olof covers 1956–2021 (e.g. 1974-01-03 'Tour 74'), setlistfm covers recent years. Library tour column now populated for nearly all touring dates.

TODO-162: Add Olof's Files database table + scrape show/tour info into it
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-10
Description: Add a new DB table for Olof's Files (Dylan tour/setlist archive) data, modeled
  on the existing setlistfm_shows table (backend/db.py:533-541), and a new scraper module
  (alongside backend/bobdylan_scraper.py and backend/site_crawler.py) to pull show and tour
  info from olofsfiles.com into it. This is a candidate secondary source for the tour-name
  gaps tracked in TODO-153 — setlist.fm's tour_name field is empty for a large share of
  dates, and Olof's Files may have better/more complete tour coverage.
All 5 phases of FABLE_OLOF_FILES.md shipped 2026-07-10: P1 fetcher/mirror (471 pages) + P2 events (4,533) + P3 songs (61,708) + P4 chronicles (1,244 calendar + 79 new-tapes rows) + P5 surfacing (/api/olof/* endpoints, tour-name fallback, POST /api/olof/compare setlist matcher, gui_next Olof panel + About credit, i18n). olof_* stays local-only (not MASTER_TABLES) pending a redistribution decision. Follow-ups tracked separately: TODO-228 (2013+ PDF chronicles), TODO-226 Part A remainder (BobTalk search), TODO-224/225 (geocoder/fingerprinting riders).

TODO-218: ONBOARDING P4 — README.md rewrite (retire PyQt flow docs)
Priority: Low
Status: Done
Added: 2026-07-10
Closed: 2026-07-10
Description: Spec §6 (instructions/FABLE_ONBOARDING_SYNC.md): quickstart via GitHub Releases installer + first-run wizard, data-model note (master release vs site data vs monthly flat-file), dev setup (.venv, run_backend.py, gui_next dev), keep flat-file/checksum format reference sections. Can run any time; no dependencies.
Shipped 2026-07-10: README.md rewritten per spec §6 — Releases-installer quickstart + first-run wizard, master/sitedata/flat-file data-model table, .venv + run_backend.py + gui_next dev setup, flat-file/checksum reference sections kept, all PyQt flow docs retired. ONBOARDING spec moved to instructions/complete/.

TODO-217: ONBOARDING P3 — first-run wizard + Home setup-checklist card + Setup/Scraper copy
Priority: Medium
Status: Done
Added: 2026-07-10
Closed: 2026-07-10
Description: Spec §5+§6 (instructions/FABLE_ONBOARDING_SYNC.md): OnboardingWizard modal over ScreenHome when entries_count==0 (4 steps: master install, sitedata install checkboxes, mounts navigation, done — Done fires POST /api/derived/recompute per F1), Home checklist card while onboarding/status complete==false, flat-file 'Monthly update' rewording + ScreenScraper curator-only note. Ends /gui-next-i18n + /gui-check. Depends: P2 (TODO-216).
Shipped 2026-07-10: OnboardingWizard.tsx 4-step modal (master install SSE, sitedata core/files install, mounts/pipeline navigation, done + derived/recompute per F1), ScreenHome setup-checklist card + once-per-launch auto-open (sessionStorage dismiss), Setup flat-file 'Monthly update' rewording, ScreenScraper curator-only note. /gui-next-i18n run (5 locales via DeepL), /gui-check PASS (tsc node+web clean, vite build ok).

TODO-216: ONBOARDING P2 — sitedata github_check/github_install + onboarding/status endpoint
Priority: High
Status: Done
Added: 2026-07-10
Closed: 2026-07-10
Description: Spec instructions/FABLE_ONBOARDING_SYNC.md §3 item 3 + §4. GET /api/sitedata/github_check (latest sitedata-* release; assets carry collision suffixes — match by _core_/_files_ pattern + manifest sidecar pairing, never exact filename), POST /api/sitedata/github_install (SSE; download to data/imports/, verify manifest SHA256 BEFORE extraction, extract into SITE_DIR reusing package_restore's path extended to sitedata_core/sitedata_files manifest types; idempotent re-runs), GET /api/onboarding/status (spec §4 shape; cheap counts + meta reads). Test against the real sitedata-2026-07-10 release. NOTE: a partial, UNVERIFIED implementation from an interrupted agent sits uncommitted in backend/app.py + tests/test_sitedata_packaging.py (2026-07-10) — all 3 routes present and compiling, agent's own P2 tests unwritten; review it rather than trusting it.
Shipped in a9759209: sitedata github_check/github_install (SSE, SHA256-before-extract, install markers) + onboarding/status endpoint; 7 new tests, live-verified against sitedata-2026-07-10 release.

TODO-170: Add a dedicated TapeMatch screen — visualize results, review logs, provide user
  feedback/corrections, and manage running the scripts
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-10
Description: There is currently no GUI screen for TapeMatch at all — only backend sync
  endpoints (/api/tapematch/sync, /api/tapematch/families in backend/app.py:4255-4304,
  backend/tapematch_sync.py) that ingest tools/tapematch/observations.db family clusters
  into recording_families/tapematch_family_meta for display on the Library screen. TapeMatch
  itself is run/managed entirely outside the app via tools/tapematch scripts, with run output
  (results, logs, report.md) in data/tapematch/runs/ (per project memory) and
  observations.db + last_run_report.md at root. Add a new screen that: (1) visualizes
  TapeMatch results/family clusters per run, (2) lets the user review run logs and
  analysis.md/report.md write-ups in-app, (3) provides a way to submit user feedback or
  corrections on a match (e.g. wrong family grouping) that feeds back into the
  observations.db / tapematch_family_meta data, and (4) lets the user kick off/manage
  running the TapeMatch scripts themselves rather than only via the command line.
v1 shipped 2026-07-10: dedicated ScreenTapeMatch (route /tapematch, Library nav group) — date rail with all/conflicts/no-analysis views + text filter, per-date similarity-% matrix (calibrated banded blend from tapematch_pairs, raw corr/emb/fp in tooltip), family chips, collapsible analysis.md viewer, crawl status strip. Backend: LISTENING §1 pairs sync (tapematch_pairs USER table + 4 GET routes + sync chaining). Deferred remainder (pair corrections, run management, LB deep-link) → follow-up TODO.

TODO-173: Confirmed taper tag on LB entries (soomlos, spot, hide, lta, etc.) — only show when confirmed
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: entries.taper_name (backend/db.py:137) already exists and is populated
  heuristically by extract_taper_and_source() (db.py:678-811), which parses free-text
  descriptions for "Taper:" labels etc. — but it's unconfirmed/best-guess text, no curation
  or confidence flag, and nothing gates whether it's shown. Add a real taper tag concept:
  a curated set of known taper names (soomlos, spot, hide, lta, and others as identified)
  with a confirmed flag per entry, and only display the tag in the UI when an entry's taper
  is confirmed — not just whatever extract_taper_and_source guessed from the description text.
  Needs a DB field/table for the confirmed flag (separate from or alongside taper_name) and
  UI work to surface the tag (e.g. as a pill) on confirmed entries.
  Known tapers now implemented in _KNOWN_TAPER_ALIASES (backend/db.py). Curated list:
  soomlos, spot, hide, lta, mk, southside butcher (ssb), iar, mjs, bw, dolphinsmile, jtt,
  pl, cedar, holy grail, vw, cck, jt, cta, tyrus, zimmy21, fine wine, hv, condor, lowgen,
  schubert, mb, jersey john, theodore, mike savage, m&a, wario, mani (=manie), bach, romeo,
  cb master, lk, hhtfp, jf, sullylove, ebr, tom moore, dk-wi, tk, bt, vito, glen dundas,
  nightly moth, csheb, streetcar visions, sk, jerseyboy, spyder9, bob meyer, markp,
  downfromtheglen, mrsoul, sh, sm, gs, rcm, mike millard (=mm), billie, jgb, tom paine (tp/tompaine56),
  mango farmer, ironchef, soledriver, goodnitesteve, clapberry, bigjim, teddy ballgame,
  theshadow, robert, sfy, caretaker, beer (=beerly=mikebeerly), caspar (=jon caspar), kuddukan,
  pdub, audiowhore, arashi, dopersan, markitospb, krw co, maloney, radioshack, kingrue,
  warburton (=jimmy warburton), captain acid (=captainacid=acidproject), andrea82, pike1957,
  sway, whofan70, two of us, mcforce, thelonius (=thelonious), jems, tarantula, lbp51,
  unwanted man music (uww), travelin man records (tmr), stevemtl, bobby bourbon (=bourbon),
  elliot, jvs, v4tx, lta–ltz (legendary taper series), nta–ntz (net taper series)
TAPER phase 2 shipped: confirmed-only taper pill in Library performance lens (taperConfirmed payload field), 'Confirmed taper' + 'Taper: needs review' filter views, DetailPanel Taper tab (tier/conflict/evidence via shared EvidenceList) with curator confirm/reject writing sticky MASTER taper_confirmations (F2). GET/POST /api/tapers/attributions* routes. Heuristic taper_name remains display-fallback only per spec.

TODO-186: Library UI — quality grade + curated-pick badges, saved curated-list filter views
Priority: Medium
Status: Done
Added: 2026-06-24
Closed: 2026-07-09
Description: Surface the two new "best of" signals on the Library screen as at-a-glance chips
  rather than leaving them buried in detail views:
    - Quality grade chip: render concert_ranker's `quality_recording_scores.final_score` /
      A+..F grade (TODO-183) on each recording row/card — likely the recording lens row and
      DetailPanel.tsx, following the existing "Unconfirmed" pill pattern used for
      fam_needs_review (ScreenLibrary.tsx).
    - Curated-pick chip(s): for any LB present in `curated_list_entries`, show a small badge
      naming the curator(s) (e.g. "carbonbit's pick", "10haaf's pick") — a date/recording can
      carry more than one.
    - Saved filter views: add "carbonbit's picks" / "10haaf's picks" (and a combined "any
      curated pick") as selectable filters alongside the existing activeDecade/activeStatus
      filter sets (ScreenLibrary.tsx:336-340), backed by the still-open GET /api/curated_lists
      route from TODO-181.
  Depends on / relates to: [[TODO-181]] (curated_lists DB + import done; GET routes + filter
  wiring explicitly deferred from that pass — this TODO is that deferred UI work plus the new
  badge requirement), [[TODO-183]] (grade field this surfaces).
Shipped 2026-07-09 (RANKING phases 3-4): pickRank/absGrade/curated ride /api/library/performances (flat fields, no N+1, F4 pattern); star + grade + curated-pick badges on performance-lens rows, family MemberRow, and DetailPanel identity block; recommended/superseded/carbonbit/10haaf filter views; Picks tab with shared EvidenceList (F3). Flat recording-lens badges + combined 'any curated pick' view spun off to a follow-up TODO.

TODO-181: Add curated "best of" lists as filter views (carbonbit, 10haaf)
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: No curated-list mechanism currently exists in backend/db.py. Add support for
  named curated lists of best LB recordings (starting with carbonbit and 10haaf's lists) —
  needs a new table (e.g. curated_lists + curated_list_entries mapping lb_number to a list
  name/source) and a way to import each curator's picks. Surface as a filter option on the
  Library screen (alongside the existing activeDecade/activeStatus/etc. filter sets in
  ScreenLibrary.tsx:336-340) so users can filter to "carbonbit's picks" or "10haaf's picks".
  DONE (2026-06-24): curated_lists/curated_list_entries MASTER tables (schema v9->v10) +
  CRUD in backend/db.py; tools/import_curated_lists.py (stdlib-only xlsx/zip parsing) imports
  carbonbit's data/lists/FLglist.xlsx (4503 entries, multiple LB picks per date allowed) and
  10haaf's data/lists/dylan_boots.zip + years.zip (7572 entries, union of both archives — they
  disagree on ~1,100 LB numbers between an older per-year snapshot and a newer allboots.html
  dump, neither a clean superset of the other). Ran once against the live DB.
  REMAINING: GET (and curator-gated POST/DELETE) routes for /api/curated_lists; wire a
  "carbonbit's picks" / "10haaf's picks" filter into ScreenLibrary.tsx. Explicitly deferred —
  this pass was scoped to DB + import only.
Remainder shipped 2026-07-09 (RANKING phase 4): GET /api/curated_lists (open) + curator-gated POST/DELETE routes in backend/app.py; 'carbonbit's picks' / '10haaf's picks' filter views wired into ScreenLibrary.tsx performance-lens Views dropdown. DB + import half was done 2026-06-24.

TODO-203: Tier C retrain with family-aware hard negatives (label-noise fix)
Priority: Low
Status: Done
Added: 2026-07-04
Closed: 2026-07-09
Description: Tier C's HardNegBatchSampler groups hard negatives by (date, slot) only —
embedding/data.py fetches family_id in select_sources() but never uses it. 16.2% of
same-date cross-source pairs in latest_pairs are pipeline-verified same_family, so with
hard_frac>=25% per batch and source-dense dates preferred, a material slice of the
contrastive "push apart" gradient separated same-tape transfers — training the encoder to
destroy the exact invariance TapeMatch needs. The 2026-07-03 clean-truth probe
(TIER_C_CALIBRATION_PROBE_REPORT.md) condemns the checkpoint, not the approach: it never
tested a cleanly-trained model. Re-run proposal: (1) group negatives by (date, family_id),
never same-family; (2) add pipeline-verified same-family cross-source windows as REAL
positives (corr-verified, no curator text); (3) exclude fn_label_census.py-flagged pairs
from the negative pool; (4) taper-attribution negatives (user 2026-07-04): pairs whose
entries resolve to two DIFFERENT curated tapers (_KNOWN_TAPER_ALIASES, backend/db.py) are
provenance-certified hard negatives — measured 138 such pairs agree with pipeline
different_family vs only 9 conflicts (6 of 9 involve "dolphinsmile", likely a
transferer/seeder miscaptured as taper — curator to confirm; raw taper_name strings are
NOT truth-grade: 381/2366 diff-raw-taper pairs are waveform-verified same_family because
the field mixes tapers, transferers, and generic descriptors). Dividend: same-curated-
taper + different_family pairs (21 curated / 142 raw) are a provenance-backed FN mining
list for TODO-201. Expanding the curated alias list directly grows all of these sets.
Gate: same absolute-FP protocol as Rule D; must beat nmfp's zero-FP recovery to earn a
production slot. Sequenced after TODO-202 densification results.
Closed without implementation: Tier C (contrastive embedding) was rejected on the gap gate twice (2026-07-03 initial, 2026-07-04 re-measurement); calibration frozen 2026-07-09 per WORK_PACKAGE_2026-07-09. Retrain-with-better-negatives premise no longer justifies the compute.

TODO-182: Explore "best LB per date" via user voting — unsure how this would work
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: Idea: let users vote on which LB recording is the best source for a given
  date, surfaced as a "community pick" per date. Not yet scoped/decided how this would work.
  Key tradeoff: this app is single-user/local (SQLite + local Flask backend, no shared
  server), so real cross-user voting would need either (a) a new shared backend service to
  aggregate votes, which is a big architectural lift, or (b) piggybacking on the WTRF forum —
  e.g. a sticky "best of" thread that gets scraped/parsed similarly to the curated lists in
  TODO-181 — which fits the existing architecture far better. Needs a decision before any
  implementation.
Superseded by FABLE_UNIFIED_RANKING §5 — WTRF-thread-as-curated-list decision covers the 'best LB per date' voting idea (per SPEC_INTEGRATION_NOTES §3).

TODO-083: Export HTML — add column picker with more My Collection fields
Priority: Low
Status: Done
Added: 2026-05-21
Closed: 2026-07-09
Description: The exported HTML has six fixed columns (LB#, Status, Date, Location,
  Folder, Notes). Add a column-picker UI in the Collection tab's export dialog (or as
  query-params on /api/collection/export/html) so the user can choose which columns
  to include and their order.
  Additional columns available from get_collection() / entries / lb_master to expose:
    • disk_path (full local path)
    • confirmed_at (date added to collection)
    • source / lineage / format / bitrate / sbd (from entries if present)
    • venue / city / state / country (if entries has them split out)
    • audio_fingerprint match status (once fingerprinting lands)
  Implementation sketch:
    • Add a small "Columns…" button next to "Export HTML" in the Collection tab.
    • Pass selected column keys as ?cols=lb,status,date,location,folder,notes,... to
      the /api/collection/export/html route.
    • In collection_export_html() (app.py:882) read the cols param, fetch the extra
      fields (may require extending get_collection()), and inject column definitions
      into the HTML template dynamically rather than hardcoding the <th> block.
collection_export_html() (backend/app.py) now takes ?cols= (validated against new _EXPORT_COLUMN_DEFS registry, always includes lb); entries dict always carries the full superset of fields (adds disk_path, confirmed_at, source_type, lb_category, rating) and the HTML template's thead/row-render/CSV-export/search/sort JS was converted from hardcoded 6-column markup to a data-driven COLS array (__COLS_JSON__ placeholder). gui_next ScreenCollection.tsx got a new ColumnPickerModal (checkboxes for the 5 extra fields) + Columns… button next to Export HTML. Locale keys added + synced via DeepL.

TODO-171: Add TapeMatch's observations.db as a selectable database in DB Editor
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: DB Editor (gui_next/src/renderer/src/screens/ScreenDbEditor.tsx) currently
  only supports two databases via activeDb: 'losslessbob' (main DB) and 'batchverify'
  (BATCH_VERIFY_DB_PATH) — db picker at ScreenDbEditor.tsx:1290-1304, backend resolution in
  _dbedit_db_path()/_dbedit_is_batchverify() (backend/app.py:96-103), used throughout the
  /api/dbedit/* routes (app.py:2742-2973). Add a third option for TapeMatch's observations.db
  (tools/tapematch/, per project memory) so its tables can be browsed/edited the same way,
  likely read-only given it's tool-generated data.
Added TAPEMATCH_DB_PATH (backend/paths.py) pointing at tools/tapematch/observations.db. Generalized _dbedit_db_path()/_dbedit_is_batchverify() in backend/app.py to a _DBEDIT_READONLY_DBS map (batchverify + tapematch, both read-only), extended dbedit_query()'s db param the same way. gui_next ScreenDbEditor.tsx picker widened to a 3-way losslessbob/batchverify/tapematch toggle. Verified read + write-block via curl against all 4 tables (latest_pairs/pairs/runs/sources).

TODO-146: Setup — bundle flac.exe in tools/ like shntool.exe
Priority: Low
Status: Done
Added: 2026-06-15
Closed: 2026-07-09
Description: flac is detected via shutil.which("flac") only, so it shows yellow on
every fresh Windows install. flac.exe is a small static binary (~1 MB). Bundle it in
tools/flac.exe and update _find_flac() logic in app.py's spectrogram_check route to
probe tools/flac.exe before PATH (same pattern as _find_shntool() in checksum_utils.py
lines 24-35). This would make flac silently green on all installs with zero user
friction, matching the shntool experience.
  Source: https://xiph.org/flac/download.html  (Windows builds — grab flac.exe only)
  Winget fallback (for TODO-147 hint): winget install xiph.FLAC
Bundled flac.exe (1.5.0 Win64) + libFLAC.dll in tools/, added _find_flac()/get_flac() to backend/sox_utils.py (bundled-then-PATH-then-WSL probe, mirrors _find_shntool()), wired into spectrogram_check route. Both spec files updated to bundle the two files.

TODO-164: Theme screen — add high-contrast toggle (bright white text on dark themes)
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: gui_next/src/renderer/src/screens/ScreenThemes.tsx manages the theme CSS vars
  (--lbb-bg, --lbb-surface, --lbb-fg, etc., see vars list starting ~line 83) but has no
  accessibility/high-contrast option. Add a toggle on the Themes screen that, when enabled,
  bumps text color (--lbb-fg and related fg vars) to bright white on dark themes for better
  readability/contrast.
Added ThemeOptions.highContrast; applyTheme() overrides --lbb-fg/-fg2/-fg3 to brighter whites when enabled and mode resolves to dark (no-op in light mode). Toggle added to the Themes screen's Advanced card, disabled outside dark mode (lib/tokens.ts, ScreenThemes.tsx).

TODO-163: Unified Library context panel — show actual attachments list, not just a count
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: AssetStrip in gui_next/src/renderer/src/components/library/DetailPanel.tsx:506-544
  currently only shows an attachment count (t('library.assets.attachments', { count: attachCount })
  / noAttachments). Add the actual list of attachments (names/links, not just a number) to the
  Unified Library context/detail panel so users can see and open individual attachments
  without leaving the panel.
AssetStripZone's attachments pill now opens an inline popover listing each cached attachment's clean_name, clickable to open via window.api.openPath (using data_dir from /api/db/settings), plus a 'View all in Attachments' link; reuses ScreenLibrary's existing attachments-cached query key so no extra network call (DetailPanel.tsx).

TODO-148: Scraper — persist live log across tab navigation
Priority: Low
Status: Done
Added: 2026-06-17
Closed: 2026-07-09
Description: The live log panel on the Scraper screen is cleared/lost whenever the
user navigates to another tab and returns. Log messages emitted during a run are not
retained, so the full session log is unrecoverable after leaving the screen. Fix should
buffer log lines in component or app state (not re-fetched from backend) so the log
panel re-renders the accumulated history when the screen is revisited. Also consider
a max-line cap to prevent unbounded memory growth during long scrape runs.
Live log state moved out of ScreenScraper's local useState into a new module-level zustand store (lib/scraperLogStore.ts, not persisted to localStorage), so the log buffer survives the screen unmounting on tab navigation.

TODO-161: Pipeline — show inactive/disabled action buttons instead of blank space until they appear
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: In gui_next/src/renderer/src/screens/ScreenPipeline.tsx, action buttons (e.g.
  Verify/Lookup/Rename/File and similar per-row actions) are currently not rendered at all
  until their step becomes actionable, leaving blank space in the row/detail panel. Render
  them in an inactive/disabled state from the start instead, so the layout stays visually
  consistent and buttons simply enable when their step becomes actionable rather than
  popping in from empty space.
Row action column now always renders a fixed-size Button — enabled Apply/File/Done pill when actionable, a disabled placeholder Button otherwise — so the column no longer pops in from blank space (ScreenPipeline.tsx).

TODO-152: Pipeline — Auto-unselect row when it transitions to Filed / In Collection
Priority: Low
Status: Done
Added: 2026-06-18
Closed: 2026-07-09
Description: When a row's file step completes successfully and its bucket becomes 'done'
  (Filed / In Collection), automatically clear its checkbox (set selected: false) in the
  setRows update inside applyFile (ScreenPipeline.tsx ~line 1787). Without this, bulk-filing
  a batch leaves all processed rows still checked, so the user ends up with a growing set of
  selected rows they've already finished working with.
Same applyFile success branch now sets selected: false when a row transitions to bucket 'done', so bulk-filed rows auto-clear their checkbox (ScreenPipeline.tsx).

TODO-151: Pipeline — Open button uses stale path after rename/collect
Priority: Low
Status: Done
Added: 2026-06-18
Closed: 2026-07-09
Description: After a folder is renamed or collected (moved), the "Open" button in the
  pipeline detail panel still resolves the old folder name/location. The button should
  use the updated path (post-rename / post-collect destination) rather than the path
  that was current at pipeline run time.
applyFile's success branch now updates row.folderPath/id (and clears its 'selected' flag) to the post-file result.dest, so the detail panel's Open button no longer resolves the pre-move path (ScreenPipeline.tsx).

TODO-180: Show total collection size in GB somewhere in the UI
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: No metric currently exists for the actual size of the user's recording
  collection content. get_disk_usage_stats (backend/filer.py:61-81) only reports per-mount
  disk free/total/used_pct (filesystem-level, not collection content), surfaced on
  ScreenMounts.tsx. Need to compute total bytes across all my_collection folders (sum of
  on-disk folder sizes for owned LBs) and surface it somewhere in the UI — candidates:
  Collection screen header/stats, Home screen, or the AppShell footer stats bar
  (AppShell.tsx:814-820, alongside checksum_count/bootleg_count).
Added backend/filer.py: _compute_collection_size()/start_collection_size_scan_async()/get_collection_size_stats(), caching total bytes across all my_collection folders in the meta table (collection_size_bytes/folders/computed_at), refreshed via a background thread when >24h stale (COLLECTION_SIZE_STALE_HOURS) rather than walking ~16k folders per request. Wired into GET /api/home/stats as collection_size {bytes,human,folders,computed_at,computing}. Surfaced in AppShell.tsx footer stats bar via new appShell.statusBar.collectionSize/computing keys.

TODO-168: Sidebar bottom-left shows hardcoded fake username — replace with real WTRF username
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: gui_next/src/renderer/src/components/AppShell.tsx:440-464 hardcodes a fake
  identity in the sidebar's bottom-left: "RW" avatar initials and the name "rolling.thunder"
  (with "Local · 4 mounts" subtitle). Replace with the actual WTRF forum username — the same
  value saved via /api/credentials/wtrf and surfaced in ScreenSetup.tsx (wtrf_username,
  handleWtrfSave/handleWtrfTest) — or render blank/no-name state if no WTRF credential is
  configured.
Added GET /api/credentials/wtrf (username only, never the password) in backend/app.py. AppShell.tsx sidebar now fetches it and shows real initials/username, falling back to a new appShell.noWtrfAccount blank-state string when no WTRF credential is configured. Removed the dead appShell.user/userSub locale keys (never referenced elsewhere).

TODO-192: Library UI — taper name badge on library panel entry rows
Priority: Low
Status: Done
Added: 2026-06-27
Closed: 2026-07-09
Description: Display the taper_name as a small badge/chip on each concert entry row in the library
panel, similar to the quality grade badge. Should be omitted when taper_name is null/empty or a
non-taper source label (e.g. "master", "sbd"). Helps users quickly identify recordings by a
preferred or known taper without opening the detail view.
Added taper_name badge inline in the Location column of the library recording-lens table (ScreenLibrary.tsx), gated by a NON_TAPER_LABELS blocklist (master/sbd/bootleg/soundboard/audience/ald/mixed/incomplete/unknown/n-a). No backend change needed — /api/search already returns taper_name.

TODO-169: Home screen — remove ingest box, doesn't serve a purpose and takes up space
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: Remove the "Hero ingest card" on gui_next/src/renderer/src/screens/ScreenHome.tsx
  (~lines 187-214, home.ingestNew/home.ingestTitle/home.ingestDesc i18n keys). User finds it
  doesn't serve a purpose and just takes up space on the Home screen. Remove the card and
  its now-unused locale keys from all 6 locale files.
Removed Hero ingest card + STEP_STRIPS const from ScreenHome.tsx; removed 10 orphaned home.* locale keys (ingestTitle/ingestDesc/dragHere/orClickBrowse/stepVerify/stepLookup/stepRename/stepLbdir/primaryWorkflow/pipelineTagline) from all 6 locales; reflowed At-a-glance/Jump-to into a 2-col grid.

TODO-167: Geocode locations from setlistfm_shows and bobdylan_shows tables
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: backend/geocoder.py (run_batch, _get_performance_location_string) currently only
  geocodes location strings sourced from the `performances` table (raw LB metadata,
  source='performances' in location_geocoded). It does not pull venue/city from
  setlistfm_shows (db.py:530-541, venue_name/city/country columns) or bobdylan_shows
  (db.py:508-518). Extend geocoding to cover these two tables as additional sources — likely
  relevant to fixing the blank Map screen (BUG-215) since more complete location_geocoded
  coverage means more pins on the map.
Added _get_bobdylan_shows_location_string() and _get_setlistfm_location_string() to backend/geocoder.py, wired into run_batch() via a priority-ordered _STRUCTURED_SOURCES list (bobdylan_shows -> setlistfm_shows -> dylan_performances -> raw text fallback). location_geocoded.source now records the matching table. 13 new tests in tests/test_geocoder.py; PROJECT.md updated.

TODO-165: Deprecate old fingerprinting — remove code and UI
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-07-09
Description: Remove the old fingerprinting feature: backend/fingerprint.py, its routes in
  backend/app.py, references in backend/integrity_monitor.py, and the
  gui_next/src/renderer/src/screens/ScreenFingerprint.tsx screen + its nav entry in App.tsx.
  Need to confirm integrity_monitor.py doesn't depend on fingerprint.py for anything still
  in active use before deleting (check usage there first) — being replaced by/superseded by
  whatever the new approach is (not specified yet).
Deprecated feature removed: backend/fingerprint.py + all /api/fingerprint/* routes, gui_next ScreenFingerprint.tsx + nav entry + AppShell/Icon wiring, ScreenCollection.tsx Fingerprinted column/filter/sort/context-action, ScreenSetup.tsx purge option, AboutDialog.tsx dep listing, orphaned i18n keys (6 locales), and now-unused librosa/numba/soxr deps (requirements.txt + PROJECT.md). Legacy gui/ (PyQt6, frozen) and cli.py intentionally left calling now-404 endpoints per user decision.

TODO-205: Pipeline structural tier: implement P7+P1+P2 (+P3/P8) per design doc — shared hash/state cache, async job model
Priority: Medium
Status: Done
Added: 2026-07-07
Closed: 2026-07-09
Description: Implement instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md (design done 2026-07-07,
reviewed against sources). Phased plan in §9: Phase 1 Schema SHIPPED 2026-07-08 (two cache
tables + db helpers + tests/test_pipeline_cache.py, inert until consumed). Phase 2 async job
plumbing SHIPPED 2026-07-08 (/api/pipeline/run/start|status|cancel, per-st_dev drain threads
+ global worker semaphore; sync /run untouched). Phase 3 P7 state persistence SHIPPED
2026-07-08 (verify/lbdir served cached:true on fingerprint match, lbdir LB-guard, force
param on both routes; see design §9 as-built notes). Phase 4 P1 hash consultation SHIPPED
2026-07-08 (per-file md5+sha256 cache in verify_folder/_lbdir, filing source digest from
cache w/ fallback, stale_verify guard on all filing; tests/test_hash_cache_verify.py).
Phase 5 P3 LBDIR prefetch BACKEND HALF SHIPPED 2026-07-08 (per-LB dedup + 2-worker pool,
pending_fetch marker on lbdir mute, sync-scrape fallback retained; pending verdicts never
persisted/served cached; see design §9 Phase 5 as-built notes). Phase 5 GUI HALF SHIPPED
2026-07-09 (pending_fetch retry effect in ScreenPipeline.tsx: 5s poll, 6-attempt cap, once
lands it clears the autocomplete guard). Phase 6 P8 blocked-as-live-view SHIPPED 2026-07-09
(backend severity split — blocked escalates to attn only for no_date/no_route, transient
codes mount_offline/dest_exists/db_error/unknown fall through to done → GUI re-buckets to
shelf; auto re-resolve once per detail-panel open; bulk "retry blocked collects" toolbar
action; tests/test_p8_blocked_severity.py). Not done: design §6 optional auto-retry-on-
mount-reachability (only the on-open + bulk paths built). Remaining: Phase 7 GUI migration
(swap runSteps to /run/start + poll /run/status, zustand persist on the folder queue,
warm-start buckets from pipeline_folder_state, wire /run/cancel). Quick-win tier
(D1/D2/D3/P5) shipped 2026-07-07.
Phase 7 GUI migration shipped: runSteps→async /run/start+poll /run/status driver, stopRun→/run/cancel, folderQueueStore zustand persist, warm-start via new /api/pipeline/state route + mount hydration. Structural tier (design §9 Phases 1-7) COMPLETE. Verified: gui-check PASS, backend endpoint smoke-tested, 23 pipeline tests pass.

TODO-211: Extract _pipeline_process_folder severity logic into a pure, unit-testable function
Priority: Low
Status: Done
Added: 2026-07-09
Closed: 2026-07-09
Description: tests/test_p8_blocked_severity.py (TODO-205 Ph.6) tests a VERBATIM MIRROR of the severity block, not the real code — _pipeline_process_folder is a closure inside create_app() that boots live file/collection/integrity watchers against the live DB, so it can't be driven from a unit test (test_pipeline_smoke.py set this mirror precedent). Refactor the severity computation (backend/app.py ~6427-6449) into a module-level pure function taking the four step statuses + file_status/error_code + lb_number and returning the severity string; call it from the closure and point the P8 test (and any future severity test) at the real function so mirror/real drift is impossible. Low: current test is correct, just not load-bearing against real-code changes.
Extracted compute_pipeline_severity() as a module-level pure fn in backend/app.py; closure + new /api/pipeline/state warm-start route both call it; test_p8_blocked_severity.py now drives the real fn (mirror deleted). 23 pipeline tests pass.

TODO-174: Investigate consolidating attachment downloading — metadata scraper vs site crawler overlap
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-08
Description: Two separate mechanisms both download attachment files: the metadata scraper's
  download_files option (backend/scraper.py:195-247,423,453-501, wired through every scrape
  path in app.py via the scrape_attachments meta flag) downloads attachments while scraping
  an individual LB detail page; site_crawler.py (the incremental site crawler) independently
  discovers and downloads /files/ URLs site-wide and keeps entry_files.downloaded in sync
  (site_crawler.py:412-426). Neither is deprecated — both are still actively used — but the
  overlap may be worth consolidating into one path. Flagged as possibly complicated to
  untangle (the two paths have different triggers/granularity: per-LB vs site-wide), so this
  needs careful investigation before touching either, not a quick fix.
Investigated: keep both mechanisms (different triggers/granularity), consolidation rejected as high-risk/low-payoff. Two guardrails applied: scrape_entry now flags already-on-disk files downloaded=1 (fixes desync when site_crawler fetched first); site_crawler skips network fetch for /files/ URLs already on disk while keeping inventory + entry_files bookkeeping. 2 new tests; full suite 458 passed.

TODO-176: Performance page year dropdown — switch to a tabulated (grid) layout for readability
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-08
Description: The Year filter dropdown on gui_next/src/renderer/src/screens/ScreenBootlegs.tsx:
  243-277 (yearsOpen/yearsDropRef) renders years as a single-column scrollable list
  (maxHeight: 280, overflowY: 'auto') — across ~60+ years of touring this is a long, hard-to-
  scan list. Change it to a tabulated/grid layout (e.g. multiple columns of years, decade-
  grouped) so it's easier to read and pick a year at a glance.
Year filter popover in ScreenBootlegs.tsx switched from single-column scroll list to a 5-column CSS grid (~12 rows), 'All years' kept as full-width top row; popover widened 110->240. Typecheck + production build clean; no new i18n keys.

TODO-175: DB Editor LB filter box — support multiple comma/space-separated LB numbers
Priority: Low
Status: Done
Added: 2026-06-22
Closed: 2026-07-08
Description: The LB# filter box on gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:1428-1432
  (lbFilter state, dbeditor.lbFilter label) only matches a single LB number — backend
  /api/dbedit/table/<name>/rows (backend/app.py:2800-2864) requires lb_filter to be a single
  integer (`lb_filter.lstrip("-").isdigit()` → `lb_number = ?`). If the user types multiple
  numbers (e.g. "4929, 5683, 9627") it should pull up rows for all of those LB numbers
  (lb_number IN (...)) instead of only matching/accepting one.
Backend /api/dbedit rows lb_filter now accepts comma/space/mixed-separated LB numbers via parameterized lb_number IN (...); any invalid token falls back to unfiltered (prior semantics). GUI box already passes the raw string through, so it works end-to-end. 7 new tests + 162-test regression pass.

TODO-149: setlist.fm scraper — true incremental update (early-exit pagination)
Priority: Low
Status: Done
Added: 2026-06-17
Closed: 2026-07-08
Description: run_update() in setlistfm.py always walks every API page even when
  force=False. The API returns shows newest-first, so pagination can stop as soon
  as a setlistfm_id is found that already exists in setlistfm_shows. Implement
  early-exit: after INSERT OR IGNORE, check if the row was already present; if a
  full page of shows is all-known, stop paginating. Reduces API calls from ~200
  pages to however many new shows there are since the last sync.
run_update() early-exits when force=False and a full page yields zero newly-inserted rows (INSERT OR IGNORE rowcount); force=True keeps the full walk. stop_reason/pages_fetched logged. 3 new stubbed-API tests; full suite 449 passed / 5 skipped.

TODO-208: SessionEnd hook: flag unrecorded changes on /clear, surface in next session brief
Priority: Low
Status: Done
Added: 2026-07-07
Closed: 2026-07-08
Description: SessionEnd hook (fires on /clear and exit) runs the same staleness check as .claude/hooks/changelog_check.sh; if source files changed but CHANGELOG.md head is not today, write a flag file that .claude/hooks/session_brief.sh surfaces at next SessionStart ('previous session ended with unrecorded changes — run /session-close first'), then clear the flag. Closes the bookkeeping gap across the /clear boundary; Stop hook alone only warns per-turn.
.claude/hooks/session_end_check.sh (SessionEnd, registered in settings.json) writes .claude/state/session_end_stale.flag when source changed but CHANGELOG head is stale; session_brief.sh surfaces the warning at next SessionStart and clears the flag. Round-trip verified; .claude/state/ gitignored.

TODO-207: gui_next locale key-parity check script (spec D6 remnant)
Priority: Low
Status: Done
Added: 2026-07-07
Closed: 2026-07-08
Description: A small key-diff script (keys in en.json missing from de/fr/es/it/nl) runnable standalone and from the Stop hook or /gui-check; the DeepL gui-next-i18n skill only reports parity when run manually. Source: instructions/complete/FABLE_PIPELINE_DEVLOOP_IDEATION.md idea D6.
tools/gui_next_locale_parity.py added (dotted-path key diff en.json vs de/fr/es/it/nl, exit 0/1/2). Current status: full parity, 1381 keys in all 6 locales. Standalone only, not hook-wired.

TODO-206: gui_next: fix 14 baseline renderer typecheck errors, then add typecheck to pre-commit
Priority: Low
Status: Done
Added: 2026-07-07
Closed: 2026-07-08
Description: pre-commit currently gates Python only (ruff); the dirty renderer typecheck baseline makes /gui-check's 'no new errors' comparison fuzzy. Known errors include IconButton disabled prop and shiftKey-on-ChangeEvent in ScreenPipeline.tsx. Fix the 14 baseline errors, then wire typecheck into pre-commit alongside ruff.
Done with BUG-236: 14 baseline errors fixed, tsc -b + build clean, typecheck wired into pre-commit alongside ruff.

TODO-198: TapeMatch recall recovery (CC_TAPEMATCH_FIXES) — remaining Tasks 2-7
Priority: Medium
Status: Done
Added: 2026-07-02
Closed: 2026-07-08
Description: Task 1 landed 2026-07-02 (regression.py harness + tapematch/verdict.py single-source-of-
  truth clustering; observations.db recovered from Trash; baseline reproduced via `freeze` +
  `score --cached`, exit 0). No-audio scaffolding for Tasks 2-4 also landed: config keys
  (fingerprint.cluster_threshold_staircase/_curator, secondary_match.hiss_merge_median_lofi/
  hiss_lofi_ceiling_hz), verdict.py conditional thresholds + lo-fi hiss relaxation, and the pairs
  schema gained windowed_frac/hiss_frac/hiss_median/fp_score/nyquist_capped_a/_b (populated by
  insert_pairs going forward). Scope was capped at Tasks 1-4 (pause before the expensive 5-7 audio
  work) per user decision 2026-07-02.
  REMAINING (all need AUDIO re-runs — the budget-gated part):
  - Task 2: run `tools/tapematch/rerun_cat3.py` (Cat-3 focused re-run). NOTE: the documented FN
    query matches 137 pairs, not the spec's stale "6"; bound with --limit/--dates. Records
    before/after verdict; unchanged pairs reassign to Cat 1/2/4.
  - Tasks 3/4 gates: `score --cached` for the staircase/curator/lo-fi threshold changes only becomes
    valid after re-running the affected dates so the new secondary-metric columns are populated
    (historical rows have them NULL). Also: curator-lineage (Task 4.1) and hf_ceiling/nyquist_capped
    (Task 4.2) are NOT yet wired into the LIVE cli.py clustering metrics builder (lb numbers +
    per-source HF evidence aren't threaded to the cluster call) — they work in the harness/verdict
    path but not in a live session. Wire those before running the Task 3/4 audio gates.
  - Task 3.1: already implemented in cli.py (either-side staircase, line ~497) — spec premise was
    stale. Remaining work is the diagnostic (instrument why one-sided-staircase Cat-2 pairs still
    read windowed_frac~0), which needs a live run on a known Cat-2 date.
  - Tasks 5-7 (estimate_ratio_v2 + duration prior + confidence gating; residual_ppm_from_lag_curve;
    pitch_ratio_pyin; ratio-invariant triplet fingerprint) — DEFERRED, out of the current scope cap.
  Pre-existing (not caused by this work): the test_batch_queue-family tapematch tests hang when run
  against the real mounted /mnt collection (run_batch/find_lb_folders scan the live collection). The
  208 tests exercising the changed code all pass. Consider isolating those tests behind a fixture.
  Relates to: [[TODO-184]] (tapematch same-source FN rescue), [[TODO-170]] (TapeMatch GUI).
Confirmed complete: CHANGELOG.md 2026-07-02 entries after the Task-1 snapshot show Tasks 2-7 all landed same-day — Task 2 rerun_cat3.py executed (0/6 Cat-3 flipped), Tasks 3.2/4.1/4.2 staircase+curator-lineage+hf_ceiling wired into live cli.py and validated, Tasks 5-7 (estimate_ratio_v2/residual_ppm_from_lag_curve/pyin/triplet) implemented and calibrated (triplet rejected/disabled after live calibration showed false merges). Final: recall 41.6%/precision 98.6%/fp=9 vs 38.3%/98.2% baseline. Full writeup: tools/tapematch/RECALL_RECOVERY_REPORT.md. Further gains scoped to CC_TAPEMATCH_ADDON.md (TODO-199).

TODO-202: TapeMatch densification probe (12×60s excerpts) for Rule D recovery
Priority: Low
Status: Done
Added: 2026-07-04
Closed: 2026-07-05
Description: Tier B attributed the nmfp TP low tail to a sparse-excerpt artifact (5×60s
excerpts of differently-trimmed transfers sample different songs); re-embedding at 12×60s
could lift the zero-FP recovery above the shipped +25 flips. OUTCOME: full-population 12×
embed (~8.5h, 1942 extracted + 523 pilot-cached, 2 sources absent) + v1/v2 sweeps ran; the
pre-registered gate (flips > 25 at abs fp ≤9 v1 AND ≤6 v2) is met only at the both_tol
0.725 plateau edge — 26 flips, net +1 TP with churn (−3 shipped recoveries, +4 gains, one
gain 0.015 above bar), one step from the 0.700 FP cliff the 5× calibration explicitly
refused (config.yaml "one-step margin" comment). At margin-respecting thresholds ≥0.750,
12× = exactly 25 flips = no improvement; sparse-excerpt hypothesis falsified as a broad
effect. DECISION: 12× REJECTED, kept 5×/t_emb 0.75. Artifacts retained for TODO-204
(embed_cache_12x/, fullset_pairs_12x_scores.json). Side product: BUG-237 found+fixed
(emb_fullset_eval.py acceptance check stale post-Rule-D ship). Full analysis:
tools/tapematch/TIER_B_FULLSET_REPORT.md "Densification probe" section.

TODO-200: TapeMatch live-session embedding integration (Rule D production path)
Priority: Medium
Status: Done
Added: 2026-07-04
Closed: 2026-07-04
Description: Live sessions now populate pairs.emb_score/emb_score_global via
tools/tapematch/emb_live.py, hooked after insert_pairs in tapematch_session.py (same
transaction). Cache misses subprocess into .venv-nmfp (nmfp_embed.py --eval-set, temp
worklist under tools/tapematch/tmp/); scoring shared with emb_score_pairs.score_pair; any
failure (missing venv, crash, timeout) leaves NULL → Rule D abstains safely. Gated by
config.yaml rule_d.live_embed. Never overwrites non-NULL with NULL; self-pairs skipped.
Verified: 4 new unit tests + 177 equivalence tests pass; score --cached byte-identical
(tp=684 fn=891 fp=9 tn=1381); live run 20260704_171831 (1998-10-28) wrote real emb scores
on all 10 fresh pairs rows (cache-hit path) with zero frozen-verdict changes — the one
same_family pair scored emb_global 0.967, independently corroborating its low-confidence
0.520-corr merge.

TODO-199: TapeMatch add-on approaches (CC_TAPEMATCH_ADDON) — lineage forensics + learned similarity
Priority: Medium
Status: Done
Added: 2026-07-02
Closed: 2026-07-03
Progress: All three tiers concluded. Tier 0 (Task 1) DONE — re-based recall ceiling to ~80% (36.7%
  curator label noise in the corr<0.05 FN sample). Tier A (Tasks 2-5) DONE — flaw signal
  precision-safe but marginal (+0.1 recall pt), left dormant; stationarity/env rejected. Tier B
  (Task 6) REJECTED 2026-07-03: nmfp (neural-music-fp ckpt-100) embedded all 184 eval sources;
  gap p10(TP)-p90(TN) = -0.034 aligned / +0.007 global, below the >=0.10 bar, despite strong
  central separation (TP median 0.912 vs same-show-TN 0.150). Killer TN tail was LABEL NOISE (3
  frozen negatives waveform-contradicted corr 0.92-0.95, flagged label_suspect=1). Full report
  tools/tapematch/TIER_B_EMBED_REPORT.md. Tier C (Task 7) REJECTED 2026-07-03: from-scratch
  contrastive encoder (ConvEncoder 587,712 params, augment.py's 7-op AugmentChain, same-show hard
  negatives mined from observations.db) trained 30 epochs/7170 steps (69.8 min, final loss
  ~0.029). Gate 7.3.1 (aug-sanity) PASS (mean=0.964, bar >=0.80). Gate 7.3.2 (decisive,
  embed_eval.py on all 184 eval sources): tol=0 gap -0.017, tol=2 gap -0.074 — both below the
  >=0.10 bar and both WORSE than Tier B's pretrained-model baseline (TP/TN medians barely
  separate: 0.520/0.441 vs nmfp's 0.912/0.150). Confirmed with user: REJECT per the pre-agreed
  protocol, no threshold-shopping — no Rule-C wiring, no pairs.emb_score, no verdict/regression.py
  changes. FINAL STATE (unchanged from CC_TAPEMATCH_FIXES): recall 41.6%, precision 98.6%, fp=9.
  Follow-on: built tools/tapematch/dump_calibration_audit.py + build_calibration_audit_html.py +
  calibration_audit.json/.html — an interactive audit table of all 2965 frozen pairs' truth labels
  vs current verdicts vs the LB catalog relation-text, for manually spot-checking label quality
  (motivated by the label-noise findings above). Full narrative in
  tools/tapematch/CALIBRATION_PROGRESS.md.
Description: Spec written (instructions/CC_TAPEMATCH_ADDON.md) for breaking past the ~42% recall
  ceiling documented in tools/tapematch/RECALL_RECOVERY_REPORT.md (93% of FN are non-correlating;
  hand-engineered waveform/speed levers exhausted at 41.6% R / 98.6% P, fp=9). Three tiers:
  Tier 0 (Task 1) FN forensic audit + curator label-noise quantification → re-based recall ceiling;
  Tier A (Tasks 2-5) content-blind lineage-forensic signals — shared-flaw (dropout/click/cut) event
  fingerprint, spectral-ratio stationarity, band-limited envelope corr (conjunctive-only), verdict
  addon_links rules + coverage instrumentation; Tier B (Task 6) pretrained neural-fingerprint
  embedding eval (inference only, gap-gated); Tier C (Task 7) contrastive embedding trained with
  same-show different-source hard negatives (the triplet failure mode weaponized), curator labels
  eval-only. Every signal gated by the generalized calibration protocol: same-date different-source
  TN population mandatory, TP/TN gap >= 0.10 or structural reject, absolute fp <= 9 on the frozen set.

TODO-197: Re-run the WTRF skipped-review entries to assess BUG-231/232 checksum-search gains
Priority: Medium
Status: Done
Added: 2026-07-01
Closed: 2026-07-01
Description: The checksum body-search + cross-recording guard (BUG-231/232, backend/wtrf_scraper.py)
  landed after the batch-85 pass that produced wtrf_skipped_review.md (85 LB>16000 entries with no
  confident match). Re-ran all 85 with `tools/wtrf_fetch_missing.py --lbs <list> --delay 2.0
  --add-to-qbt --paused` (2h44m — much slower than the ~30 min estimate; many entries had 20–37
  candidate posts, each needing a checksum-body fetch). Result: 30/85 (35%) now resolve
  automatically (28 definitive, 1 high, 1 medium; 14 qbt_added, 16 downloaded-only), 13
  needs_review, 11 ambiguous, 31 not_found (mostly genuinely absent — disqualified as tagged for a
  different LB or outside the 6-month window). Full breakdown in wtrf_skipped_review_rerun.md.
  Found two follow-up issues: BUG-233 (junk "UTF-8.torrent" filename) silently overwrites every
  downloaded torrent in a batch run except the last one and any added to qBittorrent immediately —
  14 of this run's 30 matches have no retrievable file on disk. Filed BUG-234: LB-16404/16405/16406
  (three different dates/venues) all matched the same WTRF topic 55005 — a confirmed false match
  from the checksum search, needs investigation.

TODO-198: Add "Quality" page to library detail panel — LB Rating + AI Quality Index
Priority: Medium
Status: Done
Added: 2026-07-01
Closed: 2026-07-01
Description: New `GET /api/quality/<lb>` route (`backend/app.py`) reads the latest Concert
  Ranker scan row (`quality_recording_scores.abs_grade`/`abs_score`/`final_score`/`verdict_text`).
  `RecordingDetailPanel` in `gui_next/.../DetailPanel.tsx` gains a fourth tab, "Quality" (owned
  rows only, alongside Overview/Assets/Seed & Share), rendering the catalog LB Rating and the AI
  Quality Index (Concert Ranker's letter grade + score/100) as bold side-by-side `Fact` cards,
  plus the verdict text below. New i18n keys `library.panel.tabQuality` / `library.quality.*` in
  all 6 locales (DeepL). No schema changes — reuses the existing Concert Ranker tables.

TODO-196: Add custom app icon (packaged + window/taskbar), replace generic Electron gear icon
Priority: Low
Status: Done
Added: 2026-07-01
Closed: 2026-07-01
Description: Implemented custom LB icon in gui_next/resources/icon.png (512x512 PNG) for both
  packaged app/installer (electron-builder) and running/dev window + Linux taskbar (BrowserWindow
  icon option in gui_next/src/main/index.ts). Icon is picked up by buildResources convention for
  macOS/Windows installers, and explicit icon path for window decoration + taskbar on all platforms.

TODO-191: Concert ranker — validate and integrate speech_band_snr_db + new waveform detectors
Priority: Medium
Status: Done
Added: 2026-06-25
Closed: 2026-06-26
Description: Validated three new metrics (speech_band_snr_db, brickwall_score,
  single_ch_transient_count) on scan 17 (320 rated AUD recordings, decade-stratified).
  Forward selection + commentary Δ/σ audit results:
    - speech_band_snr_db: rho=+0.409, Δ/σ=+0.75 (good commentary signal) but NOT selected
      by forward selection — subsumed by existing predictors (hf_ceiling_hz, crowd_snr_db,
      hiss_floor_db). Kept in POLARITY (+1) for family scoring.
    - brickwall_score: rho=-0.179, Δ/σ=-0.18 (no signal). Kept in POLARITY (-1).
    - single_ch_transient_count: rho=+0.239, BACKWARDS vs commentary (bad recordings have
      MORE transients — confounded by performance energy, not just mic stability). Not selected.
      Kept in POLARITY (-1).
  QUALITY_MODEL not updated — scan 8 (2798 samples) model remains authoritative; scan 17
  fit has higher Spearman (0.716 vs 0.664) but worse within-1-tier (51.7% vs 75.9%)
  due to smaller, stratified sample. tools/fit_aud_quality_model.py updated to include
  all three in candidate pool for future full-corpus rescans.

TODO-190: Concert ranker — TV band detection in HF native probe
Priority: Low
Status: Done
Added: 2026-06-25
Closed: 2026-06-25
Description: Detect CRT monitor scan-frequency artifact (~15.6 kHz) captured during analog
  transfers. Implementation: _tv_band_flag(p) added to features.py — checks for a narrow
  elevated band (>6 dB above 13-14k and 16.5-18k neighbors) in the 14.5-16.5 kHz range with
  high variance across NativeProbe windows (the band pulses in/out; steady tone = 0). tv_band_flag
  (0/1) added to extract_hf_native() return dict and POLARITY (0 = informational, not a quality
  penalty). NativeProbe.window_psds_db field added to audio/cache.py so per-window energy variance
  can be measured without a second decode. 2 tests pass.

TODO-189: Concert ranker — discriminate mini-disc / 32k DAT / cassette in HF detection
Priority: Medium
Status: Done
Added: 2026-06-25
Closed: 2026-06-25
Description: Distinguish three acoustically distinct HF source signatures from the existing
  generic lossy_brickwall flag. Implementation from averaged NativeProbe PSD:
  _minidisc_parapet_score(p): looks for partial-energy shoulder in 15-17k range (ATRAC alternating
  cutoff leaves "stepped" shape averaging to a sub-reference shoulder) with nothing above 17k,
  including an alternation check (|e_15_16 - e_16_17| > 6 dB). Returns 0-1 score.
  _32k_dat_flag(p): clean Nyquist wall at 16k — >30 dB drop from 12-16k to 16-20k with above
  region at noise floor. Most reliable detection of the three.
  _cassette_rolloff_flag(p): gradual slope above 17k (5-25 dB from 15-17k to 17-18k, some signal
  in 18-20k as tape hiss). All three added to extract_hf_native() return dict and POLARITY (-1).
  NativeProbe.window_psds_db populated in build_native_probe(). 4 tests pass.
  Note: minidisc detection is approximate from averaged PSD (the alternating staircase averages
  to a shoulder shape, not the per-frame step visible in the spectrogram); a per-frame STFT pass
  would be more precise but requires a separate decode.

TODO-188: Concert ranker — flaw vocabulary text feature extraction from DB description field
Priority: Medium
Status: Done
Added: 2026-06-25
Closed: 2026-06-25
Description: Parse 18 artifact/flaw vocabulary keys from entries.description using regex patterns
  matching the LB site's controlled vocabulary. Implementation: concert_ranker/text_features.py
  (new file) — extract_text_features(description) → dict with keys txt_clipping, txt_brickwall,
  txt_limiting, txt_digipop, txt_dropout, txt_gap, txt_mic_hit, txt_hf_streak, txt_compression,
  txt_minidisc, txt_floating_parapet, txt_32k_dat, txt_talking, txt_singing, txt_remaster,
  txt_tv_band, txt_cassette, txt_eac_match (all 0.0/1.0). extract_text() wrapper added to
  features.py. Injected into calibration metrics in calibration.py:build_samples() (DB-side,
  no rescan needed) and at rerank time via _inject_text() in cli.py (mirrors _inject_dff()).
  All 18 keys added to config.POLARITY. 9 tests pass.
  Next step: calibration run to fit weights; expect txt_clipping/txt_digipop/txt_eac_match
  to carry strong negative weight; txt_talking/txt_singing moderate negative.

TODO-140: tapematch — low-band/time-warp fallback for speed-offset misses
Priority: Low
Status: Cancelled
Added: 2026-06-13
Closed: 2026-06-25
Description: Falsify-first pilot (calibrate_lowband.py) tested 250–2000 Hz energy-envelope
cross-correlation on 1989-06-04 and 1990-01-12 "missed" pairs. Positive control
(LB-07214/LB-10916) correctly scored +0.938. Confirmed-distinct same-show pair
(LB-02470/LB-02478, no curator claim) scored +0.357 — above every "missed" claimed-same
pair (max +0.201). Several missed pairs scored negative (−0.114 to −0.128), suggesting
genuine source differences or polarity inversion rather than recoverable low-band signal.
No threshold can separate missed pairs from confirmed-distinct pairs. Root cause: the
250–2000 Hz band captures shared musical dynamics (same songs, same concert) equally for
same-source and different-source recordings — the same fundamental problem that eliminated
200–4kHz fingerprinting for TODO-185. match.lowband_envelope_corr() retained in codebase
with unit tests (tests/test_lowband_corr.py, 4 passing) for future use; not wired into
cli.py. Full data table in BASELINE.md Task 10.

TODO-144: tapematch — piecewise alignment for staircase/staircase pairs
Priority: Low
Status: Cancelled
Added: 2026-06-13
Closed: 2026-06-25
Description: Falsify-first pilot on 2001-10-30 (calibrate_piecewise.py). Detected
  splice points via new align.locate_splice_points() (reuses the steps array that
  interpret_curve computed but discarded). Same-source pair (LB-07888/LB-08413) found
  11 splice points on each side (union = 22 boundaries, 23 micro-segments); different-
  source pair (LB-08413/LB-13258) found 1+1. Per-segment windowed_median p50: same-
  source 0.004, different-source 0.005 — different-source scored higher again, same
  conclusion as Task 5. No gap at any granularity. Additional finding: staircase
  detection over-triggers at step_flag_sec=0.5s (10 of 11 detected steps are lag-
  estimation noise; only the 23.4s max_step is a real splice). The union-of-splice-
  points approach creates misaligned segment boundaries that hurt rather than help.
  BASELINE.md Task 9 documents the full data. align.locate_splice_points() and
  tests/test_splice_points.py (5 passing) are retained for potential future use.

TODO-185: tapematch — segment-level overlap rescue (clapping-wav / partial-source matching)
Priority: Medium
Status: Cancelled
Added: 2026-06-24
Closed: 2026-06-25
Description: Three falsify-first pilots run against 1991-11-05 (the motivating example) and
  cross-validated on 2001-10-30 + 1989-06-04. All three approaches failed:
  (1) best contiguous run on 60s residual_corr windows — all pairs (positives and negative
  control) settled to windowed_median 0.002–0.013, longest run above any threshold = 0 windows,
  at both ±10s and ±120s lag search.
  (2) 6–8 kHz HF-band windowed fingerprinting — max-statistic floor ~0.07 for all pairs;
  full-band produces identical results (HF peaks dominate the local-max filter even without
  band restriction).
  (3) 200–4000 Hz crowd/clap-band windowed fingerprinting — found apparent signal on 1991-11-05
  (0.19–0.24 for 3 claimed pairs vs 0.103 negative control), but cross-validation on 2001-10-30
  and 1989-06-04 showed confirmed-distinct same-show pairs scoring 0.235–0.301, entirely
  overlapping the claimed-positive range. The 1991-11-05 negative control (0.103) was an
  anomalously low same-show score. The 200–4kHz band is dominated by shared musical content
  (same songs, same concert) and cannot separate a localized clapping-wav match from
  same-show-different-source background.
  Root cause: the target (a few seconds of shared crowd noise) cannot be separated from
  same-show musical content at 20s window granularity without onset-aligned sub-second event
  matching or a fundamentally different signal. BASELINE.md Task 8 documents all three findings.
  New code added (not wired into cli.py): windowed_fingerprints(), best_window_fingerprint_match(),
  _fingerprint_hashes() in match.py; tests in test_fingerprint_windows.py (4 passing).
  Calibration scripts: calibrate_contig_run.py, calibrate_fingerprint_localize.py,
  calibrate_fingerprint_baseline.py.

TODO-151: Unified Library — visual refinement (typography roles + tabbed detail panels)
Priority: Medium
Status: Done
Added: 2026-06-22
Closed: 2026-06-22
Description: Implement the Unified Library Pixel Spec (instructions/library/Unified Library Pixel
  Spec (standalone).html; reference build "Unified Library (refined)"). Normalize the Library
  screen's 14 sizes / 6 weights down to nine --t-* type roles + four --w-* weights + --track-eyebrow
  (tokens.ts), replacing every raw fontSize/fontWeight literal in ScreenLibrary.tsx and
  DetailPanel.tsx. Convert both detail panels (by-performance and by-recording) from a flat scroll
  to a pinned identity block + tab strip + swappable pane, making Seed & Share a peer tab. Rework the
  performance-table column model (drop dead 32px spacer, fixed widths sized to content, trailing flex
  spacer) and widen the recording ★ column to 48px. Fixed BUG-217 (summary wrap) and BUG-218 (★ clip)
  in passing. Build + typecheck green; visuals verified by user.
  Scope notes: table.tsx left unchanged (shared header; spec marks the change optional); recording-lens
  scope-dependent columns and the existing AssetStripZone/ShareSeedZone reused-in-place rather than
  rewritten into the spec's asset-row layout (per §12 "repositioned, not rewritten").

TODO-150: Unified Library — TapeMatch backend integration + Library screen
Priority: High
Status: Done
Added: 2026-06-18
Closed: 2026-06-20
Description: Build the unified Library screen per instructions/design_handoff_unified_library/
(see README.md for doc index). Decisions locked in: TapeMatch family backend integration
happens FIRST (doc 07 — recording_families + tapematch_family_meta tables, schema v7,
import_master_db() backward-compat guard, backend/tapematch_sync.py, POST /api/tapematch/sync,
GET /api/tapematch/families), so the performance lens reads real family data from day one
instead of shipping the no-families flat fallback. src source-type gets a new curator-edited
DB column (not heuristic-parsed) — populated manually per-entry via the step (8) detail-panel
editor only; no one-time classifier off source_chain/description to pre-seed values, even
though source_chain already has equipment-chain text for ~52% of entries (8613/16630) that
would hint at SBD vs AUD — confirmed-by-curator beats inferred-and-maybe-wrong.
Performance/show grouping gets its own dedicated backend
aggregate endpoint (not client-side, not bolted onto /api/search); family data stays a
separate fetch merged client-side by lb_number (doc 07 §4/§5), not JOINed into that endpoint.
"system" theme mode resolves explicitly via getSystemMode() before indexing the new palette
table. Batched relocate/remove handlers ship as part of bulk-action parity, not deferred.
Search/Collection screens stay live, untouched, not retired this pass.
  Build order: (1) TapeMatch backend integration [doc 07] (2) theme additions [doc 01]
  (3) src column migration (4) recording lens / no-families fallback (5) performance-grouping
  backend endpoint (6) performance lens (7) shared action registry + batched relocate/remove
  (8) detail-panel zones (9) screen/route/nav (10) i18n.
  Build order step (1), TapeMatch backend integration [doc 07], is DONE (2026-06-18):
  schema tables (recording_families/tapematch_family_meta, schema v7), import_master_db()
  backward-compat skip guard, backend/tapematch_sync.py, POST /api/tapematch/sync +
  GET /api/tapematch/families, end-to-end verified against the live DB (859 dates / 552
  families / 1320 recordings linked; idempotency + label_override survival + 1996-07-21
  ambiguous-rerun spot-check + backward-compat import all confirmed).
  Build order step (2), theme additions [doc 01], is DONE (2026-06-18): tokens.ts gained
  `palette` (frame theme: slate/blue/purple/green/graphite, PALETTES table ported verbatim
  from the handoff) and `cardStyle` ('framed'|'flat', default 'flat') on ThemeOptions;
  applyTheme() now resolves 'system' mode via getSystemMode() before indexing
  MODES/PALETTES/ACCENT_PALETTES/STATUS (closes the silent fallback-to-light bug); index.css
  got the --sep-* framed-card token block (adapted from the handoff's #frame to :root, since
  this app has no #frame element); ScreenThemes.tsx got new "Frame theme" and "Card style"
  cards plus a fix so handleImportTheme() round-trips the new fields. tsc --noEmit and
  `npm run build` both pass. i18n for the two new keys deferred to de/fr/es/it/nl per user
  request — revisit once the Library screen itself is further along; en.json has them, other
  locales fall back to English meanwhile.
  Build order step (3), src column migration [doc 03], is DONE (2026-06-18): `entries`
  gained a curator-edited `source_type` TEXT column (schema v8, MASTER_SCHEMA_VERSION
  7→8) for the `Soundboard|Audience|FM/Pre-FM|Master|Mixed` enum (SBD/AUD/FM/MST/MTX
  badge). Unlike `taper_name`/`source_chain`/`lb_category` this is never heuristically
  parsed — stays NULL until a curator sets it (editor UI is step 8, detail-panel zones).
  Wired into search_entries()/get_entries_by_lb_list()/get_collection() read paths.
  py_compile + full pytest suite pass (one pre-existing unrelated failure in
  TestFolderLink::test_replace_existing, from in-flight multi-LB folder-link work,
  not touched here).
  Build order step (4), recording lens / no-families fallback [doc 03], is DONE (2026-06-18):
  new `ScreenLibrary.tsx` — flat LB#-keyed table, client-side adapter merging `/api/search`
  (full catalog, incl. `source_type`) with `/api/collection/prefetch` (collection, fingerprints,
  wishlist, duplicates, xref_lb_numbers); no backend changes. Facet rail (scope/decade/status/
  rating/source/health), summary strip with live owned %, virtualized year-grouped table —
  this row shape is the no-families fallback the performance lens (step 6) will reuse.
  Deliberately bare per user decision: no context menu/detail panel/bulk bar this step (those
  are steps 7/8, to avoid throwaway rework); owned-row file-card fields (size/files/format/cds)
  and the "New" status value omitted (no backing data exists yet, not shipping placeholders).
  Reachable via a temporary nav-hidden `/library-dev` route in `App.tsx` (same pattern as the
  existing `/quicklookup`) pending real nav/route wiring in step 9. `tsc --noEmit` and
  `npm run build` both pass.
  Build order step (5), performance-grouping backend endpoint, is DONE (2026-06-18):
  `backend/db.py` gained `get_performances()`, exposed via new `GET /api/library/performances`
  in `backend/app.py`. Groups `entries` by raw `(date_str, location)` into shows, joining
  `bobdylan_shows` (venue/setlist-key/track-count), `setlistfm_shows` (tour), `bootleg_titles`
  (title) — a dedicated backend endpoint per the locked decision, not a client-side groupBy and
  not bolted onto `/api/search`. TapeMatch family data intentionally excluded (separate
  `/api/tapematch/families` fetch, merged client-side later in step 6). Optional fields (`dow`,
  `tour`, `setlist`, `tracks`, `title`) omitted rather than null-faked when no source data exists.
  Verified against a migrated copy of the live dev DB: 16,630 entries → 10,718 shows, ~150ms.
  py_compile passes on both touched files.
  Build order step (6), performance lens, is DONE (2026-06-18): `ScreenLibrary.tsx` gained a
  "By performance | By recording" lens toggle (defaults to performance — the new, richer view
  per `00-overview.md`). New `PerformanceLensView` fetches `/api/library/performances` +
  `/api/tapematch/families`, merges families by `lb_number` into the SAME `RecordingRow` objects
  already built for the recording lens (no separate owned/wish/dup/fp merge logic — reused
  by reference) so both lenses always agree on a recording's state. Ported `families()`/
  `rollup()` from the handoff's `perf-data.js` reference into TS (`familiesOf`/`rollupOf`):
  groups recordings by `fam` (or by `lb` when ungrouped), derives coverage
  (Covered/Upgrade/Gap/Undocumented). When no recording has a `fam`, every family collapses to
  one member — the no-families fallback falls out of this for free, no separate flat-rendering
  branch needed. Year-grouped virtualized table, show → family → member expand/collapse, its
  own facet rail (decade/coverage/source/best-rating) separate from the recording lens's.
  Deliberately bare per the established step-4 pattern: no detail panel, no bulk bar, no
  context menu, no family `note` (not exposed by `/api/tapematch/families` — out of scope to
  extend that endpoint here) — those remain steps 7/8. `tsc --noEmit` and `npm run build` pass.
  Build order step (7), shared action registry + batched relocate/remove [doc 02], is DONE
  (2026-06-18): new `components/library/actions.tsx` — one `LibAction` vocabulary
  (open/listen/acquire/share/assets/maintain groups), `buildRecordingActions()` and
  `buildPerformanceActions()`, a fixed-position grouped `ActionMenu` + `useActionMenu()` hook
  (same right-click convention as ScreenCollection.tsx's local ContextMenu), and
  `BulkActionBar`. Wired into both `ScreenLibrary.tsx` lenses: recording lens gained a
  checkbox column + multi-select bulk bar (Create torrent / Add to qBittorrent / Update
  location / Remove, batched); right-click on recording rows (both lenses' member rows) and
  performance-lens show rows opens the full grouped menu. All handlers call the SAME backend
  endpoints ScreenCollection.tsx already uses for these ids (qbt/add, torrent/create,
  preview_forum+post_forum, collection PATCH/DELETE, wishlist, fingerprint/build,
  spectrogram/generate, open/vlc, openPath) — no backend changes. Action ids with no existing
  backend/UI integration (`sources`, `notify`, performance-row `m3u`) are omitted rather than
  shipped inert, per 04-seed-data-and-punchlist.md's "wire it or hide it" rule — `m3u` would
  need a new `?lb_numbers=` filter on `/api/collection/export/m3u`, deferred as its own ticket
  rather than scope-creeping into this step. Added shared `Toast`/`ConfirmDialog` to
  `components/primitives.tsx` (ported from ScreenCollection.tsx's local copies) since Library
  needed action feedback and had neither. `tsc --noEmit` and `npm run build` both pass.
  Remaining build-order steps (8)-(10) — detail-panel zones, screen/route/nav, i18n — not
  started.
  Build order step (8), detail-panel zones [doc 02], is DONE (2026-06-18): new
  `components/library/DetailPanel.tsx` — `RecordingDetailPanel` and `PerformanceDetailPanel`,
  each zoned per the handoff: header (title/LB#/rating/source/status badges) -> `ActionBar`
  (1 primary action + Reveal inline, everything else in a `⋯ More` button that opens the
  SAME grouped `ActionMenu`/`openMenu` step 7 already wired for right-click) -> `ShareSeed`
  (status line + Add to qBittorrent / Regenerate / Post… + a single date-sorted, filterable
  torrents+forum activity log) -> `AssetStrip` (Attachments/Spectrograms/Map as state-bearing
  chips, not buttons) -> an optional Setlist line (performance panel only, when `tracks` is
  present). The unified activity log needed by ShareSeed is built **client-side** from
  `prefetch.torrents`/`prefetch.forum_posts` (already bundled by `/api/collection/prefetch`,
  grouped by `lb_number`) — no new backend endpoint, since the raw data already existed and
  ScreenCollection.tsx's own torrent/forum tabs were never actually merged either. Spectrogram
  readiness is the one bit of real per-row state that didn't already exist anywhere: checked
  lazily via the existing `/api/spectrogram/list` while the panel is open, not bulk-fetched.
  Attachment counts come from a new bulk `/api/attachments/cached` query (existing endpoint,
  not previously consumed outside ScreenAttachments.tsx) shared across both lenses. Wired into
  `ScreenLibrary.tsx`: recording lens renders the panel as a third flex column when a row is
  selected (`selectedLb`, already-existing dead state from step 4 — now live); performance
  lens adds `selectedMemberLb` alongside the existing `selectedId` (mutually exclusive —
  clicking a show row opens the performance panel, clicking a member row opens that single
  recording's panel instead). `tsc --noEmit` and `npm run build` both pass.
  Build order step (9), screen/route/nav, is DONE (2026-06-18): `App.tsx`'s temporary
  `/library-dev` route is now the real `/library` route; `AppShell.tsx`'s `NAV_GROUPS` Library
  group gained a featured "Library" nav item (id `library`, icon `library`) above "My
  Collection", per doc 05's nav placement spec — the existing featured "NEW" badge logic
  picks it up for free. No i18n changes needed: `appShell.nav.library` already existed in all
  6 locales (previously only the Library group header used it; same word, no real collision).
  `tsc --noEmit` and `npm run build` both pass. Remaining: step (10), i18n for in-screen
  Library strings (facet labels, lens toggle, etc. are currently hardcoded English).
  Loose ends tied up (2026-06-18): the step-7 `m3u` performance-row action (deferred at
  the time — "would need a new `?lb_numbers=` filter on `/api/collection/export/m3u`") is
  now wired: `/api/collection/export/m3u` accepts an optional `lb_numbers` query param
  (filename becomes `show.m3u` when filtered), `buildPerformanceActions()` gained the
  `m3u` action (exports the show's owned recordings), `ScreenLibrary.tsx` gained an
  `onM3u` handler using the same `blobDownload()` pattern as ScreenCollection.tsx/
  ScreenTrading.tsx. Verified against the live backend (full export still produces
  `collection.m3u`; `?lb_numbers=1` produces a 2-track `show.m3u`; non-matching/junk LB
  numbers degrade gracefully to an empty-but-valid `#EXTM3U` file). `sources`/`notify`
  stay omitted — there is no "find sources" search or notification system anywhere in
  the app to wire them to; building one would be a new feature, not a loose end of this
  ticket. The TapeMatch family `note` field also stays unexposed — `tapematch_family_meta.note`
  is always NULL today (no sync path or curator UI ever writes it), so exposing it via
  `/api/tapematch/families` would just be a permanently-empty field, which the project's
  "don't ship placeholder data" rule argues against. i18n (step 10) is DONE (2026-06-20): all in-screen Library strings extracted to a new
  `library` namespace (~214 keys, plural-aware) and the three files (ScreenLibrary.tsx,
  DetailPanel.tsx, actions.tsx) converted to `t()`; the shared action registry + coverageLabel()
  take a TFunction param since they are plain functions. de/fr/es/it/nl filled via DeepL (a few
  values flagged for a human pass in CHANGELOG). All build-order steps (1)-(10) complete; tsc-clean,
  `npm run build` passes. See TODO-151 (now in TODO_DONE.md)
  for the lb_category audit this step also prompted.
  Decision (2026-06-18): performance lens (step 6/`get_performances()`) now filters to
  `lb_category = 'concert'` only — radio/tv/interview/studio/rehearsal/soundcheck/
  compilation/other/unknown recordings have no real venue/setlist/tour and would render
  as bare, misleading show rows. They remain visible via the recording lens. TODO-151
  (now closed, see TODO_DONE.md) audited `lb_category` accuracy and decided/implemented
  the fix: `get_performances()` now also includes date+location-complete 'unknown' rows
  as degraded `confirmed: false` shows, recovering 198 real performances bobdylan_shows
  didn't track (mostly guest spots at other artists' shows).

TODO-155: Pipeline stage icons — implement design_handoff_pipeline_icons in gui_next
Priority: Medium
Status: Done
Added: 2026-06-20
Closed: 2026-06-20
Description: Ported the locked "Pipeline Stage Icons" handoff (Option D tactile tile · Pulse
  animation · Vivid palette) into the gui_next React + global-CSS stack. New reusable component
  components/pipeline/PipelineIcon.tsx exposes <PipelineIcon stage status size /> plus
  PipelineGlyph, PIPELINE_STAGES, and the PipelineStage/PipelineStatus types. The five glyphs
  (verify/lookup/rename/lbdir/collect) are original 24×24 line paths copied verbatim from the
  handoff. All tile geometry, the radial-gradient fill, the bevel/lift box-shadows, and the
  Pulse keyframes (double expanding ring + diagonal sheen, wrapped in prefers-reduced-motion:
  no-preference) live in index.css under .pipe-tile*; derived shades use color-mix(in oklab,…)
  off a single --pipe-mid per status so the palette stays consistent. Wired into the live pipeline:
  StageNode (PipelineParts.tsx) now renders a PipelineIcon tile instead of the old 22px circle, so
  both the per-row StageTracker in the queue table and the full-width StageStepper in the detail
  view show the tiles; STAGE_TO_TILE / STATE_TO_TILE maps bridge the tracker's 'file'/'mute'
  vocabulary to 'collect'/'pending', running stages now Pulse instead of spin, and the
  current-stage accent ring is preserved.

TODO-154: Unified Library — default views should exclude Private/Missing LB entries
Priority: Medium
Status: Done
Added: 2026-06-19
Closed: 2026-06-19
Description: Both lenses showed Private and Missing-status entries by default, mixed in with
  Public ones, with no visual distinction beyond the Status badge color. User wants both
  hidden from the default view. Recording lens: filteredRows now hides Private/Missing when
  no Status filter chip is active; explicitly selecting the Public/Private/Missing chips still
  works exactly as before (additive toggle), so Private/Missing remain reachable, just not the
  default. Performance lens: has no per-recording Status filter, so Private/Missing recordings
  are now dropped unconditionally from each show's recordings array before family grouping and
  coverage rollup (rollupOf/familiesOf), not just hidden by a default — there's no chip there
  to opt back in with. Side effect: a show whose only recordings were Private/Missing now
  rolls up as coverage='Undocumented' rather than showing hidden entries; family/coverage
  counts shrink accordingly when a private member existed.

TODO-153: Unified Library — SourceBadge always blank (entries.source_type is NULL for all rows)
Priority: Medium
Status: Done
Added: 2026-06-19
Closed: 2026-06-19
Description: Data audit during PerformanceDetailPanel rewrite found entries.source_type
  (curator-edited) is NULL for all 16,630 entries, so SourceBadge in the Unified Library
  detail panel always rendered the dashed empty placeholder. Added classify_source_type()/
  _classify_source_text() in backend/db.py: a conservative keyword classifier over
  entries.source_chain (preferred — already label-extracted by extract_taper_and_source)
  falling back to raw description, recognizing Soundboard/FM-Pre-FM/Mixed/Audience.
  Deliberately excludes "Master" — in trader lineage text it almost always means "first-gen
  copy off a master tape" (a generation marker), not an actual studio/soundboard master
  source; guessing wrong there would mislabel large numbers of audience tapes. Also guards
  against vinyl "Matrix: BDGD"-style runout/catalog codes being misread as a SBD+AUD matrix
  mixdown. search_entries() and get_performances() apply this as a display-only fallback when
  the column is empty. Classifies ~3,805 of 16,630 entries (Audience 3160, Soundboard 579,
  Mixed 34, FM/Pre-FM 32); the rest still show "—" rather than risk a wrong label.
  Follow-up same day, at user's explicit request: bulk-persisted those 3,805 guesses into the
  actual entries.source_type column (backed up DB first via backup_database()), reversing the
  original "never heuristically backfilled" design intent for this field. The live classifier
  fallback in search_entries()/get_performances() is now redundant for those specific rows but
  left in place — harmless, and still useful for any new entries added later.
  Second follow-up same day, at user's explicit request: per tape-trading convention (audience
  is the unstated default for live recordings — soundboard/FM/mixed get called out explicitly
  because they're notable), defaulted source_type='Audience' for the remaining NULL rows where
  lb_category IN ('concert','unknown') AND description is non-empty (10,972 rows; backed up
  DB first). Deliberately skipped the 408 non-concert rows (studio/tv/interview/compilation/
  rehearsal/radio/soundcheck) and the 1,445 rows with a completely empty description — neither
  fits the "default to Audience" rule. entries.source_type is now populated for 14,777/16,630
  rows (88.8%); 1,853 remain NULL.
  Third follow-up same day: user identified a 6th real source category the original taxonomy
  was missing — ALD (Assisted Listening Device, a venue's wireless feed for hard-of-hearing
  patrons, tapped with a receiver; neither true Audience nor true Soundboard). Added _SRC_ALD_RE
  to backend/db.py (checked first, ahead of Soundboard, since "Soundboard...(ALD is the source)"
  is a clarification, not two competing guesses) and ALD entries to the SRC_ABBR/SOURCE_FULL/
  SRC_HUE maps in ScreenLibrary.tsx and DetailPanel.tsx. Re-tagged the 37 entries whose
  description names ALD explicitly with source_type='ALD' (backed up DB first), overriding
  whatever the two earlier bulk passes had swept them into (21 Audience, 13 Soundboard, 3
  Mixed).

TODO-151: Audit lb_category classification accuracy
Priority: Medium
Status: Done
Added: 2026-06-18
Closed: 2026-06-18
Description: classify_entry_categories() (backend/db.py:2138) assigns lb_category via a
  3-tier heuristic. Audited the live DB (16,630 entries): concert=14092, unknown=2043
  (~12.3%), tv=97, studio=96, interview=96, compilation=84, rehearsal=81, radio=30,
  soundcheck=11. Spot-checked the 252 'unknown' rows with a fully-specified date + location
  and found most are real performances bobdylan_shows doesn't track — largely guest
  appearances at OTHER artists' shows (Dire Straits, U2, Tom Petty, Grateful Dead, Bruce
  Springsteen, Eric Clapton).
  Root cause found: `dylan_performances` (5127 rows, imported from a fan-maintained
  performance database) already has these dates tagged with category `GUEST` (66 rows) and
  `NET` (3433 rows — "Never Ending Tour" era, NOT "internet" as the code first suggested;
  ~97% already overlap bobdylan_shows via tier 1, but ~106 long-tail NET dates didn't) —
  neither code was in `_PERF_CATEGORY_MAP`, so tier 2 silently skipped them and they fell
  through to tier 3/unknown. Also found `SIDEMAN` (38 rows, backing-musician studio
  sessions for other artists, e.g. the Harry Belafonte session) unmapped. Fix: added
  GUEST -> concert, NET -> concert, SIDEMAN -> studio to `_PERF_CATEGORY_MAP`; bumped the
  one-time classification backfill from `lb_category_backfill_v1` to `_v2` so existing
  installs reclassify automatically on next launch. Verified end-to-end via a real backend
  restart (not a raw DB script): concert 14092->14329 (+237), unknown 2043->1811 (-232),
  studio 96->101 (+5); confirmed via `/api/library/performances` that 1986-02-19 Melbourne,
  1987-02-19 Palomino Club, 1987-04-20 LA Sports Arena, 1988-05-29 Lone Star Cafe, and
  1992-03-28 Brisbane all now resolve as normal (non-degraded) shows.
  Also added a `get_performances()` venue fallback: when `bobdylan_shows` has no row for a
  show's date (true for nearly all GUEST dates, since they're not Dylan's own shows), venue
  now falls back to `dylan_performances.venue` instead of staying null — e.g. the Melbourne
  show now shows "Melbourne Sports And Entertainment Centre" instead of just the raw
  location text.
  Kept the earlier degraded-row fallback for whatever `dylan_performances` still doesn't
  cover: 'unknown' entries with a non-'xx' date + non-blank location are grouped as a show
  flagged `confirmed: False` (rendered as an "Unconfirmed" pill in ScreenLibrary.tsx /
  PerformanceDetailPanel). After the GUEST/NET/SIDEMAN fix this fallback only fires for ~19
  shows — mostly category `FILM` (e.g. the 1986 Bristol Colston Hall "Hearts of Fire" concert
  scene filming) and a few TV-awards/White-House/studio-session dates with no clean mapping;
  deliberately left FILM unmapped since some FILM rows are non-performance B-roll (hotel
  rooms, a gas station), not shows — a blanket mapping would risk false positives.
  py_compile + full pytest suite pass (same one pre-existing unrelated failure as before,
  TestFolderLink::test_replace_existing). tsc --noEmit + npm run build pass.

TODO-147: Setup — HelpersStrip install hints for missing tools (ffmpeg, sox)
Priority: Low
Status: Done
Added: 2026-06-15
Closed: 2026-06-16
Description: When ffmpeg or sox show yellow in HelpersStrip (ScreenSetup), user had
no idea how to fix it. Added get_install_hints() to sox_utils.py with per-OS hints
(winget/brew/apt) for ffmpeg, sox, flac, shntool. /api/spectrogram/check now includes
*_install_hint fields per tool. HelpersStrip renders a monospace hint row below the
dot strip for each missing tool that has a hint.

TODO-139: tapematch reliability fixes (CC_TAPEMATCH_FIXES sequence)
Priority: Medium
Status: Done
Added: 2026-06-12
Closed: 2026-06-13
Description: Implement instructions/CC_TAPEMATCH_FIXES.md Tasks 2-7 (supersedes
instructions/TAPEMATCH_PLAN.md). Task order: 2) observations.db run versioning +
latest_pairs view, 3) OOM dtype/rate audit (1994-02-20 case study), 4) speed-offset
secondary via predicted lag (1989-06-04, 1990-01-12), 5) staircase short-window
recalibration (2001-10-30, 2001-10-07, 1996-07-21), 6) re-run queue generator,
7) error/no-verdict triage (6 error dates, 7 no-verdict dates). Validate every fix
against tools/tapematch/BASELINE.md (not TAPEMATCH_PLAN.md).
Note (2026-06-12): Task 1 (gen_analysis.py parser fix + re-baseline) done — see
BUG-164 in BUGS_DONE.md. BASELINE.md also flags that 1996-07-21 and 2001-10-07
need a fresh re-run before being used as Task 4/5 control/validation dates, since
their existing observations.db rows reflect a stale experimental run (see
BASELINE.md "Live example of the Task 2 problem").
Note (2026-06-12): Task 2 (run versioning + latest_pairs view) done. run_id +
run_at already covered the run-versioning requirement (no new columns); migration
normalized 1719 lb_a>lb_b rows and added idx_pairs_latest + latest_pairs view
(tools/tapematch/migrate_observations.py, idempotent). tapematch_session.py now
normalizes lb_a<lb_b on insert and creates the index/view in OBS_SCHEMA. Spot-check
on 1996-07-21 confirms latest_pairs surfaces the stale-experimental-run rows flagged
in BASELINE.md as-is (expected — that date still needs the fresh re-run before
Task 4/5 use). Logged BUG-165 (separate _lb_num_from_folder regex issue found during
the audit, left open for triage). Next: Task 3 (OOM dtype/rate audit, 1994-02-20).
Note (2026-06-12): Task 3 (OOM dtype/rate audit) done. Audit found the float64/96kHz-
stereo OOM hypothesis was already resolved by the 2026-06-05/06 sessions (BUG-144 +
Pass-4 OOM fix): ffmpeg-pipe decode keeps native-rate arrays out of Python, ingest
writes float32 mono memmaps and frees streams immediately, soxr resample_ratio stays
float32, and scipy.signal.correlate/numpy mean/std preserve float32 at every
correlation site (confirmed empirically). Removed the one remaining retained-reference
pattern: dead `match.pairwise_matrix()` (unused, held all sources in RAM). Added a
pre-run "est. peak RAM" log line to cli.py. Validation: 1994-02-20 (8 sources, the
case study with no prior run dir) now completes — 5 families, peak RSS 2.6 GB
(data/tapematch/runs/20260612_140009_1994-02-20). Re-ran 1993-04-16 (3-source
control) — family assignments/corr matrix/speed-ppm bit-identical to the 2026-06-07
run (data/tapematch/runs/20260612_143159_1993-04-16). Next: Task 4 (speed-offset
secondary via predicted lag, 1989-06-04 / 1990-01-12).
Note (2026-06-13): Task 4 (predicted-lag mode) done. Added `align.local_lag_centered`,
`secondary_match.high_ppm_threshold` (config.yaml), and threaded per-pair
`pair_ratios`/`lag_0`/`anchor0` from cli.py into `match.secondary_corr_pair`. Unit
tests pass (tests/test_predicted_lag.py, 3/3). Activates correctly on both target
dates (11/14 and 54/65 cross-pairs with plausible lag_0/ppm) and is regression-free
on 3 control dates including a high-ppm control. However miss counts unchanged
(1989-06-04: 8->8 vs target <=2; 1990-01-12: 9->9 vs target <=3) — for every missed
pair, windowed/hiss correlation is ~100x below threshold at every lag, not just the
zero-centered one, so search-range was never the limiting factor for these specific
pairs. Full writeup in tools/tapematch/BASELINE.md "Task 4 results". Code kept (correct,
tested, regression-free, useful for any future pair where drift-range *is* the issue).
Follow-up tracked as TODO-140 (low-band/time-warp fallback, Task 4 spec step 5). Next:
Task 5 (staircase short-window recalibration, 2001-10-30 / 2001-10-07 / 1996-07-21).
Note (2026-06-13): Task 5 (staircase short-window recalibration) done. Added
`align.union_staircase_sources` (union of both lag-curve passes' staircase
classifications — fixes a reference-ambiguity bug where the current ref source
could never be flagged staircase) and wired it into the existing 15s OR-fallback
in cli.py. Unit-tested (tests/test_staircase_union.py, 3/3). Calibration (step 3)
of a new 5s/2s short-window pass on 2001-10-30 found NO usable residual_corr gap —
same-source median 0.0118 vs different-source-same-show median 0.0153 (higher!),
distributions fully overlap. Per spec, the new 5s pass was therefore NOT wired in;
`config.yaml` carries the documented-but-disabled
staircase_window_sec/hop_sec/window_corr_threshold/coverage_threshold knobs
(thresholds null). The union-flag fix itself is regression-free on 3 control
dates (byte-identical CLUSTERS/LINEAGE/DIAGNOSTICS) and on 2001-10-30
(byte-identical output, same 6/6 lb_says_same misses, identical corr values —
the fix newly flags one pair (LB-10594/LB-08413) for the 15s fallback but that
fallback still has no usable signal there either). Target (<=3 misses) not met —
same root cause as Task 4 (signal content, not search mechanism). Full writeup in
tools/tapematch/BASELINE.md "Task 5 results". Piecewise alignment (spec step 4)
deferred — tracked as TODO-144. Next: Task 6 (re-run queue generator).
Note (2026-06-13): Task 6 (re-run queue generator) done. Added
tools/tapematch/build_rerun_queue.py — queries the Task 2 `latest_pairs` view
for dates with >=1 `lb_says_same=1 AND tapematch_verdict='different_family'`
pair, ordered by miss count desc, writes tools/tapematch/rerun_queue.txt
(232 dates currently; `--since TIMESTAMP|REF` will exclude already-revalidated
dates once the Task 4/5 fixes are committed; 0-miss dates never queued per
spec step 5). Added `run_batch()`/`--batch FILE` to tapematch_session.py —
resumable sequential re-run consuming the queue, appending `# done <ts>` to
completed lines, skipping blank/comment/done lines, exits 130 on
KeyboardInterrupt without marking the in-progress line. Unit-tested
(tests/test_build_rerun_queue.py + test_batch_queue.py, 8/8 pass; full
tapematch suite 27/27 pass). rerun_queue.txt gitignored (generated/mutable,
like observations.db). Next: Task 7 (error/no-verdict triage — 6 error dates,
7 no-verdict dates).
Note (2026-06-13): Task 7 (error/no-verdict triage) done — sequence complete.
Fixed two root-cause code bugs found across the 6 error dates: BUG-180
(ingest.list_tracks matched a directory named like a .flac file as a track —
1987-10-05) and BUG-181 (find_lb_folders included no-audio collection folders,
crashing ingest.concat_source for the whole date — 1989-08-26/09-01/09-03).
Also fixed BUG-182 (resolve_from_collection crashed with OSError when
/mnt/DYLAN2 was unreachable), found during validation. Added an explicit
insufficient_sources report path to run_date + matching gen_analysis.py
support, so <2-source dates (1989-09-01) get a clean report instead of
crashing/being skipped. Re-ran all 4 affected dates for real: 1987-10-05 (5
sources, 2 families), 1989-08-26 (2 sources, 2 families), 1989-09-01
(insufficient_sources, 1 source), 1989-09-03 (8 sources, 8 families) — all
complete cleanly. The remaining 2 error dates (1993-04-23, 2001-07-07) are
genuinely corrupted source FLAC files (truncated/0-byte) — reported to user,
not modified per spec. All 7 no-verdict dates resolved: 6 already had valid
verdicts post-Task-1 (no fix needed), 2026-06-05 confirmed as a test/
calibration artifact and marked with SKIP_REASON files (not deleted). 3 new
test files added (6 tests; full suite 33/33 pass). Full writeup in
tools/tapematch/BASELINE.md "Task 7 results".
Overall: TODO-139 (CC_TAPEMATCH_FIXES Tasks 2-7) is complete. Tasks 4/5's
numeric accuracy targets were not met (root cause is recording signal
content, not the alignment mechanism — documented in BASELINE.md); follow-ups
tracked separately as TODO-140 (low-band/time-warp fallback) and TODO-144
(piecewise alignment for staircase pairs).

TODO-145: Pipeline table — fix dead space before LB#/Apply/File columns
Priority: Low
Status: Done
Added: 2026-06-13
Closed: 2026-06-13
Description: On wide windows, the Pipeline folder queue table
(gui_next/src/renderer/src/screens/ScreenPipeline.tsx, colgroup around line
2179) left a large empty gap between the status column and the LB#/Apply/File
columns. The status column was the only `<col />` without a fixed width, so
it absorbed all leftover table width while its content (a short status badge
+ one-line reason) stayed left-aligned, stranding the LB# and action buttons
far to the right.
Fix: Capped the Status column at 240px and removed the fixed 380px width from
the folder-name column, making it the flexible column that absorbs leftover
table width instead.

TODO-143: gui_next — restore "Check for Updates" GitHub path for master snapshots
Priority: Medium
Status: Done
Added: 2026-06-13
Closed: 2026-06-13
Description: TODO-088 added a GitHub-based "Check for Updates" button to the
  PyQt GUI (_GitHubMasterThread: fetch latest release, download .db + manifest,
  verify SHA256, apply via /api/master/import), keeping "Install from File…" as
  an offline fallback. Only the file-picker fallback was ported to gui_next, so
  "Install master update" prompted for a local file with no GitHub path. Added
  GET /api/master/github_check (compares local vs. latest GitHub release
  master_version) and POST /api/master/github_install (text/event-stream:
  downloads latest master .db + manifest into data/imports/, verifies SHA256,
  applies via database.import_master_db(), mirrors /api/master/github_release's
  event shape) to backend/app.py. ScreenSetup.tsx's CuratorToggle gains a
  "Check for updates" button (handleCheckGithubMaster + runGithubInstall);
  existing button relabeled "Install from file…". i18n keys added to all 6
  locales.

TODO-141: Make Pipeline status group headers actually collapsible
Priority: Low
Status: Done
Added: 2026-06-12
Closed: 2026-06-12
Description: On the Pipeline screen, the status group header rows (NEEDS YOU,
READY, RUNNING, ON SHELF, DONE, etc.) already rendered a chevron icon and had
cursor:pointer styling via GroupRow (gui_next/src/renderer/src/components/table.tsx),
but ScreenPipeline.tsx never passed an `onToggle` handler or `expanded` state when
constructing these GroupRow items, so clicking the header did nothing.
Implementation: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added
  collapsedBuckets state (Set<Bucket>) and toggleBucket callback. flatList
  construction now skips pushing row VItems for a bucket whose header is
  collapsed (group header itself is still pushed). GroupRow now receives
  expanded={!collapsedBuckets.has(item.bucket)} and onToggle={() =>
  toggleBucket(item.bucket)}.

TODO-142: Pipeline batch filing — skip per-folder confirmation, auto-apply mount paths
Priority: Medium
Status: Done
Added: 2026-06-12
Closed: 2026-06-12
Description: When filing multiple "ready to file" folders (step 5), applyFile popped
  up a "File into Collection" confirmation dialog for every folder during a batch run.
Implementation: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile gained
  a skipConfirm parameter that bypasses the confirm() dialog and applies the
  recommended mount path (overrideDest ?? row.steps.file.dest) directly. applyAllFileable
  and applySelectedFileable now call applyFile(row, undefined, undefined, undefined, true).
  The single-row "File" button (line 2287) is unchanged and still confirms.

TODO-140: Mounts screen — add drive stats to mount cards (TODO-110 follow-up)
Priority: Low
Status: Done
Added: 2026-06-12
Closed: 2026-06-12
Description: TODO-110 added free/total/used_pct mount stats only to the pipeline
Collect step's mount picker. Extend the same disk-usage display to the Mounts
settings screen's mount cards.
Implementation: backend/filer.py disk-usage calc extracted into
get_disk_usage_stats(root_path, online), reused by get_mounts_with_stats() and the
/api/collection/mounts endpoint (now returns free/total/used_pct per mount).
ScreenMounts.tsx CollectionMount gains free/total/used_pct; MountCard shows "free of
total" with the same colour-coded usage bar (warn ≥75%, bad ≥90%). New locale keys
mounts.freeOfTotal/mounts.usageTooltip added to all 6 locales.

TODO-111: Collection integrity monitor — hash-based change detection for collection folders
Priority: Medium
Status: Done
Added: 2026-06-09
Closed: 2026-06-12
Description: Build a hashing system that watches collection mount folders for file changes.
On initial scan, compute a fast hash for every file and store results in the DB. On
subsequent scans, detect: deleted/missing files, new files, and changed files. Surface
findings in the GUI. Should be runnable on-demand and optionally on a schedule.
Implementation: Reused the existing lbdir batch-verify machinery
(checksum_utils.verify_folder_lbdir) instead of a new fingerprint DB — per-file
ffp_status/md5_status/overall already distinguish bitrot/corruption (ffp fail) from
tag-only edits (md5 fail, ffp pass/na) from missing/moved files (overall missing).
Files with overall == 'extra' are ignored — this tracks integrity of known key files,
not folder tidiness. New backend/integrity_monitor.py orchestrates a per-folder scan
(background thread, progress polling, cancel), new collection_integrity_status/
collection_integrity_scans tables persist results and history, integrity_events gains
mount_id and new transition types (content_changed/tags_changed/files_missing/restored).
Optional hourly-checked scheduler (integrity_scan_interval_hours meta key). GUI:
ScreenMounts.tsx MountCard severity badges + per-mount scan button, plus a new
"4 · Integrity Monitor" section (scan controls/progress, findings table, change log
with acknowledge).

TODO-110: Pipeline — add free space and drive stats to mount cards
Priority: Medium
Status: Done
Added: 2026-06-09
Closed: 2026-06-12
Description: Display disk usage information on each mount card in the Pipeline screen. Show
free space remaining, total capacity, and used percentage for the drive backing each mount
point. Update reactively so the card reflects current state when the pipeline is running.
Implementation: backend/filer.py get_mounts_with_stats() now returns total (capacity) and
used_pct alongside free/span/online via shutil.disk_usage(). gui_next CollectDetail.tsx
MountPicker cards show "free of total" plus a colour-coded usage bar (warn >=75%, bad >=90%);
reactively re-resolved by the existing pipeline polling.

TODO-112: Backend uptime clock for debugging
Priority: Low
Status: Done
Added: 2026-06-10
Closed: 2026-06-12
Description: Added a small running clock showing how long the Flask backend process has
been up, for debugging purposes (e.g. confirming whether a restart actually happened
after a backend code change). Backend exposes process start time via a new
GET /api/system/uptime endpoint (uptime_seconds); /api/admin/status now shares the
same start-time reference. GUI displays it on the About screen's About tab, next to
version/build info, as a live HH:MM:SS clock.

TODO-113: Make app version numbering consistent
Priority: Low
Status: Done
Added: 2026-06-10
Closed: 2026-06-12
Description: The app version number appeared in multiple places (gui_next/package.json,
splash screen, About dialog, sidebar tagline, forum post footer, CLI banner, backend
VERSION file) and these didn't all match (1.0.3 - 1.4.0 across locations). Fix:
gui_next/package.json (1.4.0) is now the source of truth for the GUI; the root
VERSION file (used by backend.version.VERSION) is kept in sync and is the source
of truth for the Python backend/CLI/forum poster. Renderer build now defines
__APP_VERSION__ from package.json for SplashOverlay, AboutDialog, and the
AppShell sidebar tagline (locale "appShell.version" now interpolates {{version}}).
Removed duplicate hardcoded constants: backend/paths.py APP_VERSION (1.2.0),
cli.py _VERSION (1.0.3).

TODO-138: Pipeline — "Auto-rename" toggle for confident single-match renames
Priority: Medium
Status: Done
Added: 2026-06-12
Closed: 2026-06-12
Description: Added an "Auto-rename" toggle to the pipeline screen header, next
to "Auto-run on drop" (off by default). When a folder has verify, lookup, and
lbdir all passing ("ok") and the rename step has resolved a single confident
LB match with a proposed name (bucket "ready"), turning the toggle on applies
that rename automatically via the existing applyRename() path — marking step 4
(rename) green/"Renamed" and advancing the row toward the collect stage (step 5)
without requiring the user to click "Apply rename". When the toggle is off,
behavior is unchanged from before: proposed renames sit in the "ready" bucket
for manual review/Apply. Implemented as a new effect (autoRenamedRef tracks
which rows have already been auto-renamed to avoid re-triggering) in
ScreenPipeline.tsx. Added pipeline.autoRename / pipeline.autoRenameHint locale
strings to en.json; other locales not refreshed (DeepL key currently disabled).

TODO-137: Pipeline — swap step order so LBDIR runs before Rename
Priority: Medium
Status: Done
Added: 2026-06-11
Closed: 2026-06-12
Description: In the pipeline workflow (ScreenPipeline.tsx / backend/app.py
_pipeline_process_folder), step 3 (Rename proposal) used to run before step 4
(LBDIR retrieve + verify). Swapped the order so LBDIR reconcile/verify runs first and
Rename runs after — running Rename before LBDIR has reconciled the folder's contents
could lead to proposing/applying the wrong folder rename. Updated step numbering/labels
in both the backend (_pipeline_process_folder, pipeline_run steps default list) and
the GUI (PipelineRow.steps ordering, step-key iteration order, status derivation) to
match the new order: verify -> lookup -> lbdir -> rename -> collect. Also added an
optional lb_number_hint body param to /api/lbdir/check and /api/lbdir/reconcile (and
wired it from the pipeline's Lookup result) since LBDIR now runs before the folder is
renamed/filed and won't yet have "LB-NNNNN" in its name or my_collection row.

TODO-134: GUI dev launch — kill stale backend, start fresh on every `npm run dev`
Priority: High
Status: Done
Added: 2026-06-09
Closed: 2026-06-09
Description: Added killPortProcess() in gui_next/src/main/index.ts. After the existing killStalePid() call, it uses lsof (Linux/Mac) or netstat+taskkill (Windows) to find and SIGTERM any process on port 5174, then waits 400ms before spawning a fresh backend. Guarantees a clean slate even when the previous backend was started outside Electron or the PID file was missing.

TODO-110: Pipeline — handling for duplicate and linked LBs
Priority: Medium
Status: Done
Added: 2026-06-03
Closed: 2026-06-04
Description: Integrated lb_alias table into all affected workflows:
- Collection missing section: alias partners of owned LBs are suppressed via NOT EXISTS subqueries in get_missing_from_collection()
- Collection owned section: linked_lbs field added to each row; ↔ badge shown in detail panel
- Pipeline lookup step: aliases resolved before single/conflict check; alias_resolved_from stored for display
- Lookup tab: is_alias_lb/canonical_lb annotated on detail rows; ≡ LB-XXXXX badge shown in summary
- lbdir_retrieve: fallback cascade to canonical when alias has no lbdir attachment

TODO-089: Add acknowledgements section to About dialog
Priority: Low
Status: Done
Added: 2026-05-24
Closed: 2026-06-02
Description: Add an Acknowledgements section to the About dialog crediting key contributors
  and resources, including at minimum:
    • Losslessbob (the original archive/project that inspired this tool)
    • Robert Cook (contributor)
    • Rumrunners (community/resource)
  Include a scrollable or expandable area if the list grows long. Keep styling consistent
  with the existing About dialog layout.

---

TODO-105: Checksum lookup — flag matches against user's own collection
Priority: High
Status: Done
Added: 2026-05-27
Closed: 2026-06-02
Description: lookup_checksums() now cross-references resolved LB numbers against
  my_collection and annotates each summary/detail item with owned+lbdir_verified.
  GUI shows a banner (verified=green / unverified=amber) and replaces the +WL button
  with an ownership pill on owned rows. CLI prints [IN COLLECTION · LBDIR VERIFIED]
  or [IN COLLECTION] on the LB header line. No "upgrade" logic — lbdir verification
  is the completeness signal.

---

TODO-093: Archive.org uploader
Priority: Low
Status: Done
Added: 2026-05-24
Closed: 2026-05-30
Description: archive.org S3-like upload via backend/archive_org.py; SERVICE_IA keyring
  slot; 7 Flask routes (/api/archive_org/credentials, /test, /upload, /status, /stop, /uploads);
  archive_org_uploads DB table; ArchiveOrgSection in ScreenSharing — credentials form,
  upload form with progress bar + bytes counter, history table.

TODO-101: Add SQL query box to DB Editor for manual query execution
Priority: Medium
Status: Done
Added: 2026-05-25
Closed: 2026-05-29
Description: POST /api/dbedit/query; SqlQueryPanel in ScreenDbEditor (textarea, Run/Clear,
  results table, row count, error display, Ctrl+Enter shortcut); blocks DROP/TRUNCATE etc.

TODO-106: Audio fingerprint matching — identify user recordings by performance date
Priority: High
Status: Done
Added: 2026-05-27
Closed: 2026-05-29
Description: ScreenFingerprint (gui_next Assets group): date picker → collection_by_date
  → build LB fingerprints via existing /api/fingerprint/build → identify mystery folder
  via new /api/fingerprint/identify_folder → ranked results table → cleanup purge.
  New backend: GET /api/fingerprint/collection_by_date, POST /api/fingerprint/identify_folder,
  GET /api/fingerprint/identify_folder/status, POST /api/fingerprint/identify_folder/stop.
  All strings wrapped with t() for i18n.

---

TODO-079: i18n — wrap table column headers with tr() across all tabs
Priority: Medium
Status: Cancelled
Added: 2026-05-21
Closed: 2026-05-29
Description: Table column headers set via QTableWidget.setHorizontalHeaderLabels(),
  QHeaderView, or QTreeWidget column titles are not wrapped in self.tr() calls,
  so they are excluded from translation and remain in English in all locales.
  Audit every tab (Collection, DB Editor, Map, Scraper, Setup, Rename, Attachments,
  Fingerprint) and wrap all header strings with tr(), then regenerate .ts/.qm files.

---

TODO-070: i18n integration testing — all 5 languages end-to-end
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-29
Description: For each of the 5 languages: set ui_language in meta, restart app,
  verify tab titles, button labels, column headers, placeholder text, and QMessageBox
  dialogs are translated. Verify LB numbers and checksums are not garbled. Verify
  English still works as default. Run py_compile on all gui files.
  Prerequisite: TODO-069. See instructions/CC_I18N.md TODO-070 section for checklist.

---

TODO-133: gui_next — react-i18next full UI translation (all screens)
Priority: High
Status: Done
Added: 2026-05-29
Closed: 2026-05-29
Description: Add react-i18next to gui_next. Install i18next + react-i18next, create
  i18n.ts initialiser, create en/de/fr/es/it/nl locale JSON files ported from Qt .ts
  sources, add language field to store, wire changeLanguage in App.tsx, add language
  selector to ScreenSetup Preferences card, wrap all hardcoded UI strings with t()
  in AppShell + all 10 translatable screen files, add TypeScript key-safety declaration.


TODO-116: gui_next — identify and wire ScreenPipeline remaining 5% stub
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: The unidentified stub was the "Bulk actions" button in the ScreenPipeline header
  (line ~431). Implemented an inline popover menu with: Select all visible, Clear selection
  (conditional on selection), and Clear queue (destructive). Follows the same outside-click
  dismiss pattern as ScreenBootlegs and ScreenSearch.

---

TODO-104: Data package restore — import user data and scraped assets from zip
Priority: Medium
Status: Done
Added: 2026-05-27
Closed: 2026-05-29
Description: Restore flow accepting a zip archive produced by the export routes (TODO-102/103).
  Implemented:
    • POST /api/package/restore (backend/app.py) — detects type from manifest.json or file names;
      dry_run mode returns conflicts without writing; user_data restores db/settings/gui_state;
      scrape_data restores data/site/; validates zip and rejects bad archives.
    • PyQt6 (gui/setup_tab.py) — _PackageRestoreThread, "Restore from Zip…" button in Data Packages
      group; dry-run pass then confirm dialog listing overwrites; final restore with status label.
    • Electron (gui_next ScreenSetup.tsx) — handleRestorePackage; dry-run → ConfirmDialog showing
      conflicts; "Restore from zip…" card added to Data Packages SetupCard.

TODO-103: Data package — scraped attachments and pages
Priority: Medium
Status: Done
Added: 2026-05-27
Closed: 2026-05-29
Description: Bundle all scraped data (data/site/ HTML pages and attachment files) into a
  distributable zip archive with a JSON manifest (file count, total bytes, timestamp).
  Implemented via POST /api/package/scrape_data, GUI button in Setup tab "Data Packages"
  group, and CLI: package scrape-data [--out PATH].

---

TODO-102: Data package — user data export
Priority: Medium
Status: Done
Added: 2026-05-27
Closed: 2026-05-29
Description: Bundle user-generated data (losslessbob.db, settings.ini, gui_state.json)
  into a portable dated zip with a JSON manifest (per-file size + SHA-256).
  Implemented via POST /api/package/user_data, GUI button in Setup tab "Data Packages"
  group, and CLI: package user-data [--out PATH].

---

TODO-132: Guarantee ≥2 TCP trackers on every torrent
Priority: High
Status: Done
Added: 2026-05-29
Closed: 2026-05-29
Description: Regardless of which tracker list is selected, always ensure at least
  2 http/https (TCP) trackers are present before writing the torrent. If the
  fetched list has fewer than 2, inject from _FALLBACK_TCP_TRACKERS.

---

TODO-130: ScreenCollection — multi-select torrent creation / qBittorrent queue
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Multi-select via checkedIds already existed. Added N/M live progress bar for
  batch torrent creation (handleBatchCreateTorrent) and qBt add (handleBatchAddToQbt).
  Operations run sequentially on the frontend; progress bar shows "Creating torrents: N/M…"
  or "Sending to qBittorrent: N/M…". qBt config already present in ScreenSetup.

TODO-129: Audio format + bitrate detection — surface FLAC/WAV/SHN and 16/44.1 vs 24/96
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Added GET /api/collection/<lb>/audioinfo backend route — probes up to 5 audio
  files with soundfile (FLAC/WAV), falls back to ffprobe subprocess for SHN/APE/others;
  caches by disk_path + mtime fingerprint. DetailPanel fetches on row open and shows a real
  "FLAC · 16/44.1" pill (or mixed/offline/absent). Removed the hardcoded placeholder pill.

TODO-128: gui_next ScreenCollection — cross-tab nav + replace coming-soon stubs
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Wired the three stub buttons in the DetailPanel: Attachments → navigate('/attachments'),
  Spectrograms → handleCtxSpectrograms (calls /api/spectrogram/generate then navigates to /spectrograms),
  On map → navigate('/map'). Added onSpectrograms and onNavigate props to DetailPanelProps.

TODO-127: gui_next ScreenCollection — real Size/codec data or drop placeholder pills
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Removed the hardcoded "FLAC · 16/44" pill from the detail panel pill row.
  Real audio format pill is now populated by TODO-129. Size row still shows '—' (no size data).

TODO-126: gui_next ScreenCollection — column header sorting
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Added sortCol/sortDir state and handleSort callback. All main-table headers
  (LB#, Status, Date, Location, Folder, Disk path, Confirmed, FP) are now clickable with ▲▼⇅
  indicators. sortedFilteredRows drives the virtualizer. Wishlist table headers also sortable.
  TH component updated to accept onClick + sorted props.

TODO-125: gui_next ScreenCollection — bulk Update Location + standard-name/NFT cross-check
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: handleUpdateLocation now supports both single and multi-row. Single: picks dir,
  validates folder name against /api/folder_naming/standard/<lb>, toasts mismatch (non-blocking),
  then PATCHes. Multi: picks parent dir, calls /api/pipeline/scan-dir to find matching LB-XXXXX
  subfolders, validates each, PATCHes all matches; shows N updated / N not-found toast.
  Reuses torrentProgress bar for progress feedback.

TODO-122: gui_next ScreenCollection — Wishlist columns/edit + Duplicates grouped tree
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Wishlist filter now shows dedicated table with LB#, Date, Location, Description,
  Rating, Added, Notes, Priority columns. Notes and Priority support click-to-edit inline (input
  + select, saved via PATCH /api/wishlist/<lb>). CollectionRow extended with wishlistPriority,
  wishlistNotes, wishlistAddedAt. Added update_wishlist() to db.py and PATCH /api/wishlist/<lb>
  to app.py. Duplicates filter now shows a grouped tree (GroupRow) organised by date·location,
  with per-variant owned rows showing rating, description, "Open on LosslessBob" (→ /lookup),
  "Open folder", and "Remove from collection" (with confirm dialog).

TODO-124: gui_next ScreenCollection — non-recursive Scan Directory + owned-aware preview
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Added /api/pipeline/scan-dir backend route (depth-1 and recursive variants) that
  matches LB-named folders. Added ScanPreviewModal component to gui_next with LB# / Folder /
  Path / Already Owned columns, per-row Add buttons, and "Add all (N)" bulk action. Scan
  directory and Scan tree… buttons now call distinct handlers (non-recursive vs recursive)
  and both open ScanPreviewModal instead of the old AddFolderModal.

TODO-123: gui_next ScreenCollection — Notes column + notes field in Add dialog
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Added Notes column to owned-collection table (reads c.notes via GET /api/collection).
  AddFolderModal now shows editable Folder Name (pre-filled from path) and Notes inputs per entry;
  both are included in POST /api/collection body.

TODO-121: gui_next ScreenCollection — global Forum & Torrent History views
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-29
Description: Old tab had standalone "Forum History" and "Torrent History" sub-tabs; new screen
  was read-only pills.
  Implemented:
    • GlobalForumPanel component (filter='forum_global' chip): lists all GET /api/forum_posts
      records with Open in Browser, Remove Record (DELETE + confirm), Go to LB actions.
    • GlobalTorrentPanel component (filter='torrent_global' chip): lists all GET /api/torrents
      records with Add qBt and Go to LB actions.
    • DetailPanel forum tab now fetches GET /api/entry/<lb>/forum_posts on open and shows
      per-post Open in Browser + Remove Record buttons (confirm dialog), replacing read-only pills.

TODO-120: gui_next ScreenCollection — per-torrent-record management in detail panel
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: DetailPanel now fetches GET /api/torrent/<lb> on open; each torrent record
  shows source-folder-exists/torrent-file-exists status dots and per-record action buttons:
  Add/Remove qBt, Regen, Relocate Source, Delete .torrent file (with confirm dialog).
  Forum tab remains display-only.

---

TODO-119: gui_next ScreenCollection — Personal Info (rating, tags, listen count)
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: DetailPanel now fetches personal meta on open and shows "My Rating" (personal_rating)
  and "Listens" (listen_count + last_listened) in the meta grid. "Log Listen" button POSTs to
  /api/collection/<lb>/listen and refreshes the panel. "Edit Personal Info" button opens
  PersonalInfoModal from the detail panel. Saving via the modal bumps personalSaveVer to
  re-fetch meta without a full collection reload.

TODO-117: gui_next ScreenCollection — restore Missing (un-owned LB) view + CSV export
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Added "Not in collection" chip backed by GET /api/collection/missing. Renders a
  separate table (LB# / LB Status / Date / Location / Rating / Description), Export CSV button,
  and double-click → Lookup navigation. Also added onDoubleClick prop to TR component.

---

TODO-118: gui_next ScreenCollection — row context menu actions
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Added right-click ContextMenu on every collection row with 7 actions:
  Open Folder, View LB Entry (→ Lookup), Scrape Entry, Fingerprint Folder, Play in VLC,
  Generate Spectrograms, Edit Personal Info (inline modal with rating 1-5 + tags).
  Also added PersonalInfoModal component (rating 1-5 + tags, GET/POST /api/collection/<lb>/meta).
  Added backend POST /api/open/vlc endpoint (wraps gui.platform_utils.open_in_vlc).
  Added onContextMenu prop to TR table component.

---

TODO-115: gui_next — wire ScreenCollection remaining 10%
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: All three items complete:
  • Wishlist add/remove actions — wired to POST /api/wishlist / DELETE /api/wishlist/<lb>.
  • Batch-remove progress bar — inline progress bar renders during sequential DELETEs.
  • "My Collection" nav count badge — AppShell fetches GET /api/home/stats on mount and
    shows collection_count beside the "My Collection" nav item.

---

TODO-094: Rework UI per Claude design prototype
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-28
Description: All 6 sprints of PLAN_GUI_WIRING.md complete. ScreenSetup, ScreenCollection,
  ScreenSearch, ScreenHome, ScreenBootlegs, and ScreenThemes fully wired to backend.
  New layout, colour scheme, and component structure implemented in gui_next (Electron/React).

---

TODO-114: gui_next — port ScreenLBDIR from source JSX
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-lbdir.jsx to gui_next/src/renderer/src/screens/ScreenLBDIR.tsx. Four sub-tabs: Check (per-file MD5/shntool table), Retrieve (copy lbdir from attachments cache), Reconcile (propose renames for moved files), Extras (list + delete files not in lbdir). Highest complexity of the 7 stub screens — do last.

---

TODO-113: gui_next — port ScreenLookup from source JSX
Priority: High
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-lookup.jsx to gui_next/src/renderer/src/screens/ScreenLookup.tsx. Sources rail (clipboard/listbox/files/folders), 5-state status counters (matched/incomplete/not-found/duplicate/xref), per-LB summary table, per-checksum detail table, footer link to Rename. Core feature of the app.

TODO-112: gui_next — port ScreenRename from source JSX
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-rename.jsx to gui_next/src/renderer/src/screens/ScreenRename.tsx. Five row states (has_lb, needs_rename, wrong_lb, multiple_ids, no_match) with filter chips, bulk action bar with checkboxes, expandable disambiguation rows for multi-LB conflicts. Depends on Lookup results being populated first.

---

TODO-111: gui_next — port ScreenSpectrograms from source JSX
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-spectrograms.jsx to gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx. Folder rail with batch progress, track rail with PNG inventory, spectrogram viewer using existing .lbb-spec-canvas CSS class, thumbnail strip, render options (width/height/dB floor/window). SoX/ffmpeg batch generate.

---

TODO-110: gui_next — port ScreenVerify from source JSX
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-verify.jsx to gui_next/src/renderer/src/screens/ScreenVerify.tsx. Folder queue rail, 7-stat summary cards (total/pass/mismatch/missing/extra/FFP/MD5), full MD5+FFP+ST5 detail table, shntool-missing error state, per-file inspector panel. Verifies user-generated checksums (distinct from LBDIR which verifies the official archive sidecar).

---

TODO-109: gui_next — port ScreenAttachments from source JSX
Priority: Medium
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Ported screen-attachments.jsx to ScreenAttachments.tsx. Three-column layout: LB rail with current/stale/missing status dots and search/filter chips; file list for selected LB; viewer pane that dispatches on kind (text → pre, html → rendered table, image → canvas placeholder, binary → no-preview + open-externally). Wired into App.tsx replacing PlaceholderScreen.

---

TODO-107: Master publish — real upload progress via GitHub REST API
Priority: Low
Status: Done
Added: 2026-05-27
Closed: 2026-05-28
Description: Replaced gh CLI subprocess in /api/master/github_release with direct GitHub REST API calls. Token obtained via `gh auth token` subprocess. Route now streams SSE events: progress (label + pct), done, error. .db and manifest uploaded in 1 MB generator chunks so pct is byte-accurate. GUI _GithubReleaseThread consumes the SSE stream and emits progress(str, int) signal; progress bar switches from indeterminate to determinate during upload.

TODO-108: gui_next — port ScreenMap from source JSX
Priority: Low
Status: Done
Added: 2026-05-28
Closed: 2026-05-28
Description: Port instructions/gui_redesign/_source/screen-map.jsx to gui_next/src/renderer/src/screens/ScreenMap.tsx. Filter rail (year range with decade chips, ownership toggle, LB status radio), static map preview using existing .lbb-map-canvas CSS class with absolute-positioned pin buttons, selected-venue side panel. Live interactive map opens in browser at localhost:5174/map — this screen is the filter/launcher.

---

TODO-091: Bundle Windows shntool binary from tools/ into the project distribution
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: tools/shntool.exe was already tracked in git. Added to losslessbob.spec
  datas so PyInstaller bundles it at _internal/tools/shntool.exe. Updated
  _find_shntool() in checksum_utils.py to check the frozen (_MEIPASS) path first,
  then the dev-tree tools/ path, before falling back to WSL/PATH.

---

TODO-097: Add purge option for geocoding data
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: Provide a way to purge cached geocoding data from the database.
Fix: Added POST /api/geocode/purge (curator-only) with scope="failed" (removes
  source='failed'/lat IS NULL rows) and scope="all" (clears entire table). Map tab
  Geocoding panel (curator-only) now has "Purge Failed/Null" and "Purge All…" buttons
  with confirmation dialogs. Status label shows deleted count and prompts re-run.

TODO-082: Restructure — move Verify and lbdir into a "Checksums" compound tab
Priority: Medium
Status: Cancelled
Added: 2026-05-21
Closed: 2026-05-26
Description: Cancelled — tab restructure not desired.

---


TODO-088: Master update — pull lb_master from GitHub repo instead of local file
Priority: High
Status: Done
Added: 2026-05-23
Closed: 2026-05-26
Description: Added _GitHubMasterThread that fetches the latest release from
  https://api.github.com/repos/kuddukan42/losslessbob/releases/latest, streams
  the .db asset with progress, verifies SHA256, saves manifest sidecar to
  data/imports/, and applies via /api/master/import. New "Check for Updates"
  button in Setup → Master Data. "Install from File…" kept as offline fallback.

---


TODO-099: Add lb_number column to location_overrides table
Priority: Low
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: Added lb_number TEXT column to location_geocoded (the "location_overrides"
  table). Migration added to init_db(). place_manual() now accepts lb_number param.
  GET /api/geocode/locations JOINs entries to return lb_numbers (all LBs using each
  location string). GUI Location Overrides table now shows LB# column.

---


TODO-095: Detect webpage exists but no checksum in DB
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: Added "Public / no checksums" filter to the Search tab status combo.
  Filters to lb_status='public' AND public_no_checksums=1 — entries with a known
  webpage but zero checksum records. All search_entries() and get_entries_by_lb_list()
  queries now return public_no_checksums in every result row.

TODO-090: Create lb_problems master data table for flagging problematic LB entries
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: New MASTER table lb_problems (id, lb_number FK→lb_master, notes, added).
  CREATE TABLE IF NOT EXISTS with index; added to MASTER_TABLES. 4 DB functions:
  get_lb_problems, add_lb_problem, update_lb_problem, delete_lb_problem, get_lb_problem_count.
  CRUD API: GET/POST /api/lb_problems + PUT/DELETE /api/lb_problems/<id> (curator-only writes).
  Management via DB Editor (automatic). GUI indicator deferred.

TODO-086: Add Dylan performance table to lb_master data
Priority: Medium
Status: Done
Added: 2026-05-23
Closed: 2026-05-26
Description: dylan_performances table already existed (ODS import). Promoted from unclassified
  to MASTER_TABLES so it ships with master data exports. MASTER_SCHEMA_VERSION bumped 2→3.
  Added GET /api/performances with ?lb= (auto-resolves entry date_str → ISO via
  geocoder._entry_date_to_iso), ?date=, ?category= filters and pagination.

TODO-100: Fix "scrape missing" to only pull missing-status entries, not private LB pages
Priority: Medium
Status: Done
Added: 2026-05-25
Closed: 2026-05-26
Description: The "scrape missing entries" button was queuing private LBs in addition to
  missing-status entries. Fixed by adding a LEFT JOIN to lb_master in the /api/scrape/start
  route and excluding rows where lb_status = 'private'. Private LBs are now handled solely
  by /api/scrape/private_rescrape ("Re-scrape Private LBs" button).

TODO-102: Add lb_missing table for permanently confirmed non-existent LB entries
Priority: Medium
Status: Done
Added: 2026-05-25
Closed: 2026-05-26
Description: lb_missing table (INTEGER PK, confirmed_date, notes) added to schema as a
  MASTER_TABLE. Seeded with 36 confirmed-not-existing LB numbers on init_db(). scrape_entry()
  returns {skipped, reason='nonexistent'} for any entry in lb_missing. reconcile_lb_status and
  batch_reconcile_lb_status set lb_status='nonexistent' (new 4th valid status). CRUD via
  is_lb_missing / add_lb_missing / remove_lb_missing / get_lb_missing_list. API:
  GET/POST /api/lb_missing, DELETE /api/lb_missing/<lb>. DB editor exposes the table.
  8 regression tests added to TestLbMissing.

TODO-098: Add public-but-no-checksums status marker column to lb_master
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-26
Description: public_no_checksums INTEGER NOT NULL DEFAULT 0 added to lb_master via table
  recreation migration (also adds 'nonexistent' to CHECK constraint). Partial index
  idx_lb_master_public_no_chk. Flag is set to 1 when lb_status='public' AND has_checksums=0
  in all reconcile paths (reconcile_lb_status, batch_reconcile_lb_status, migrate_lb_master).
  get_lb_master_stats returns public_no_checksums count. GUI visual marker deferred.
  6 regression tests added to TestPublicNoChecksums_Flag.

TODO-087: Rework geocoding to use Dylan performances table for lb_master locations
Priority: Medium
Status: Done
Added: 2026-05-23
Closed: 2026-05-24
Description: Augmented geocoding to check dylan_performances first (via date match) and
  build a structured "venue, city, state, country" query for Nominatim. Falls back to the
  raw entries.location text when no performance record exists. Results stored with
  source='performances' for provenance. Date conversion (M/D/YY → YYYY-MM-DD) handled
  by _entry_date_to_iso(). Public accessor get_performance_by_date() added to db.py.

---

TODO-092: Fingerprinting queue with progress visibility
Priority: Medium
Status: Done
Added: 2026-05-24
Closed: 2026-05-24
Description: Implement a fingerprinting queue so users can see what is currently being
  fingerprinted and how many files remain. Step A completed (Step B — persistent
  fp_task_queue table — deferred as a separate follow-up TODO if needed).
  Implemented: queue_preview in build_fingerprint_db() state, GET /api/fingerprint/build/queue
  endpoint, bold "X of Y" count label, and "Up next" QListWidget in the Fingerprint DB tab.

---

TODO-096: Play selected My Collection entry in VLC
Priority: Low
Status: Done
Added: 2026-05-24
Closed: 2026-05-24
Description: Add a "Play in VLC" right-click option on My Collection rows so the user can
  immediately listen to a recording without opening a file manager.
  - VLC is detected via PATH (Linux/macOS/Windows) and common Windows/macOS install paths.
  - Multiple selected rows pass all their folder paths to one VLC instance.
  - Shows a warning dialog if VLC is not installed rather than failing silently.

---

TODO-086: Rework external tool dependency hints for Windows
Priority: High
Status: Done
Added: 2026-05-22
Closed: 2026-05-23
Description: The Database tab currently shows Linux apt-get install commands when SoX,
  ffmpeg, or shntool are not found. Rework the dependency-check UI to detect the OS and
  show platform-appropriate install guidance.
Resolution: Added _sox_tool_hint() helper in setup_tab.py; winget commands for Windows,
  brew for macOS, apt for Linux. shntool on Windows directs to WSL/choco.
  Status labels now use RichText + setOpenExternalLinks for clickable download links.
  sox_utils.py error messages updated to use platform dict lookups.

TODO-066: Web GUI — docs update after web UI ships
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-063: Web GUI — status bar data in nav
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-062: Web GUI — frontend/index.html landing redirect
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-061: Web GUI — add nav links to admin.html and map.html
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-060: Web GUI — frontend/bootlegs.html Bootleg catalog browser
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-059: Web GUI — frontend/lb_master.html LB Master viewer
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-058: Web GUI — frontend/entry.html Entry detail page
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-057: Web GUI — Collection tab write operations
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-056: Web GUI — frontend/collection.html Collection tab (read)
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-055: Web GUI — frontend/lookup.html Lookup tab
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-054: Web GUI — Search tab owned column async load
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-053: Web GUI — frontend/search.html Search tab
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-052: Web GUI — frontend/utils.js shared JS utilities
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-051: Web GUI — frontend/base.css shared dark theme
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-050: Web GUI — Flask routes for frontend static files
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

---

TODO-078: CLI daemon — Windows support for start_new_session
Priority: Low
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: _daemon_start() uses start_new_session=True which is a POSIX concept.
  On Windows the equivalent is DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP via
  subprocess creationflags. Add a platform check so daemon start works correctly
  on Windows.

TODO-084: Export HTML — decade/year filter dropdowns do not populate
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: Decade/year dropdowns in exported collection HTML were always empty because
  year was derived solely from entries.date_str, which is NULL for any collection row
  whose lb_number has no matching entries row.
Fix: In collection_export_html() (app.py), after failing to parse a 4-digit year from
  date_str, fall back to a regex search on folder_name for a 19xx/20xx year. This ensures
  rows where the LEFT JOIN misses still contribute a year to the JS DATA array so that
  filter(Boolean) retains them and both dropdowns populate.

---

TODO-081: Cross-tab folder sync — preload all first-4 tabs from Lookup folder selection
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: lbdir tab had no connection to Lookup folder list.
Fix: Added add_folders_from_lookup() to lbdir_tab.py (guard: only when list is empty).
  Wired in main_window.py _on_tab_changed alongside the existing Verify guard.

TODO-080: Rename tab — embed all LB alias numbers in folder name when aliases are present
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: After alias collapse resolves a multi-candidate folder to a canonical LB,
  fetch all known aliases for that canonical and include them in the proposed folder name.
Fix: Added get_aliases_for_canonical() to backend/db.py. In rename_tab.py
  populate_from_lookup and _on_save_alias, after alias collapse fetches aliases via
  GET /api/lb_alias?canonical_lb=<lb> and builds combined suffix LB-canonical-LB-alias1...
  Display column shows "LB-12345 + LB-67890". Named convention documented in PROJECT.md.

TODO-077: Interactive REPL shell for CLI
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-21
Description: Refactor cli.py so running it with no arguments opens a persistent
  interactive shell (lb> prompt) with Flask started once in the background.
  Commands, tab-completion, readline history (~/.losslessbob_history), and
  per-command help (help <command>) all work inside the shell.
  One-shot mode unchanged for backward compatibility.

---

TODO-076: DB write function test battery
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-21
Description: Write a comprehensive pytest battery for all database write functions in
  backend/db.py. Cover happy-path, idempotency, constraint violations (UNIQUE, CHECK,
  NOT NULL, PK, FK), rollback on error, and thread-safety. 115 tests in 17 classes
  across tests/test_db_writes.py.

---

TODO-075: FEAT-07 — Portable Export Formats (HTML + M3U)
Priority: Low
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Export My Collection as a self-contained HTML table (collection.html) or as an
  M3U playlist (collection.m3u). Backend: GET /api/collection/export/html and
  GET /api/collection/export/m3u in backend/app.py. GUI: "Export HTML…" and "Export M3U…"
  buttons in My Collection panel of gui/collection_tab.py.

---

TODO-074: Map tab rework — browser-only, consolidate geocoding
Priority: Medium
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Removed QWebEngineView from Map tab; map now opens in system browser.
  Moved geocoding controls (Run Geocoder, location overrides table) from Setup tab
  and DB Editor tab to Map tab. Map Filters group lets user pre-filter the browser URL.
  Freed space on Setup and DB Editor tabs.

---

TODO-073: FEAT-01 — CLI / Headless Mode
Priority: Low
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Create cli.py in project root providing headless CLI for LosslessBob.
  Commands: lookup, search, stats, import, serve. Cross-platform: port-poll instead of
  time.sleep(), Waitress on Windows, forward-slash M3U paths. On Linux/macOS optionally
  chmod +x; on Windows invoke as python cli.py.

---

TODO-072: Audio filename reconcile on Lookup and Rename tabs
Priority: Medium
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: After a lookup, offer "Reconcile Audio Files" button that renames audio files
  on disk to match canonical filenames in the checksum DB. Available on Lookup tab (auto-enabled
  when mismatches are found) and Rename tab (scans checksum files in checked folders).
  Backend: POST /api/checksums/reconcile_audio + apply_reconcile_audio. GUI: AudioReconcileDialog
  in gui/widgets/reconcile_dialog.py. db_filename field added to lookup detail dicts.

---

TODO-071: FEAT-02 — Fuzzy Filename Matching Fallback
Priority: Low
Status: Cancelled
Added: 2026-05-20
Closed: 2026-05-20
Description: Fuzzy filename matching for NOT FOUND checksums using rapidfuzz.
  Cancelled — not useful. Lookup matches on checksum only; if the checksum doesn't
  match, a similar filename doesn't confirm anything about the recording content.

---

TODO-069: Generate, translate, and compile .ts/.qm files for 5 languages
Priority: Medium
Status: Done
Closed: 2026-05-20
Added: 2026-05-19
Description: Run pylupdate6 against all gui/*.py to extract tr() strings into
  gui/locales/losslessbob_{de,fr,es,it,nl}.ts. Fill all translations (AI-assisted
  batch is fine; review domain-specific terms against the glossary in CC_I18N.md).
  Compile each .ts to .qm with lrelease — target 0 untranslated warnings.
  Commit both .ts and .qm files. Prerequisite: TODO-068.
  See instructions/CC_I18N.md TODO-069 section for full spec and glossary.

---

TODO-068: Wrap all user-facing GUI strings in self.tr()
Priority: Medium
Status: Done
Closed: 2026-05-20
Added: 2026-05-19
Description: Go through all 14 gui/*.py files and gui/widgets/*.py and wrap every
  user-facing string literal in self.tr("..."). Convert f-strings with variables to
  self.tr("template {}").format(var). Do NOT wrap log messages, SQL, API URLs, or
  archive data (LB numbers, checksums, filenames). Run py_compile after each file.
  ~1,209 call sites total. Prerequisite: TODO-067 (i18n.py must exist first).
  See instructions/CC_I18N.md TODO-068 section for rules and file-by-file checklist.

---

TODO-067: i18n infrastructure — language loader, meta key, Setup tab selector
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Create gui/i18n.py with load_language() and supported_languages() helpers.
  Wire language loading at QApplication startup (read ui_language from meta table).
  Add POST /api/meta route to backend if not present (whitelist key=ui_language).
  Add language selector QComboBox to Setup tab Preferences section with restart notice.
  Supported languages: de, fr, es, it, nl (all LTR — no layout mirroring needed).
  See instructions/CC_I18N.md TODO-067 section for full spec.

---

TODO-065: Web GUI — web password setting in Setup tab
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-20
Description: Add "Web GUI Password" QLineEdit (password mode) in Setup tab Network section.
  POSTs to /api/db/settings with {web_password: "..."}. Empty = auth disabled. Add
  web_password to the GET keys list in db_settings() (return "set"/"" not actual value).
  See CC_WEB_GUI_PLAN.md TODO-065.

---

TODO-064: Web GUI — optional basic-auth middleware for web routes
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-20
Description: Add before_request hook in backend/app.py that enforces HTTP Basic Auth on
  /web/* and /frontend/* routes when meta key web_password is set. API routes (/api/*)
  remain unauthenticated (desktop app calls them directly). Flask already binds to
  0.0.0.0 so this is needed before any web UI page ships.
  See CC_WEB_GUI_PLAN.md TODO-064.

---

TODO-049: Windows — HiDPI-aware splash screen pixmap
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: The splash screen in main.py creates QPixmap(400, 120) without considering the
  display's device pixel ratio. On Windows with 125%/150%/200% scaling the splash appears
  blurry. Should query QScreen.devicePixelRatio() before QApplication is shown, create the
  pixmap at (400*dpr) × (120*dpr), and call pixmap.setDevicePixelRatio(dpr) so Qt renders
  it at native resolution.

---

TODO-048: Windows — consolidated /api/status endpoint to halve loopback overhead
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _refresh_status() in main_window.py makes two sequential HTTP GETs every 10 s:
  /api/db/stats then /api/bootlegs/stats. On Windows, loopback TCP has more overhead than
  Linux. Add GET /api/status returning both payloads merged; update _refresh_status() to use
  the single call. Reduces per-tick network cost and simplifies the error path.

---

TODO-047: Windows — replace per-tick daemon thread in _refresh_status with persistent worker
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _refresh_status() in main_window.py (main_window.py:216) spawns a new
  threading.Thread every 10 s. On Windows, thread creation costs ~0.5–2 ms (kernel TLS init
  + scheduler registration) vs ~100 µs on Linux. Over a long session this is measurable churn.
  Replace with a single persistent QThread (or threading.Thread with a threading.Event sleep
  loop) that polls at the same 10 s interval without re-creating OS threads.

---

TODO-046: Windows — QGraphicsDropShadowEffect on 11 panels causes repaint lag
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _apply_shadows() in main_window.py applies a blurRadius=12 QGraphicsDropShadow-
  Effect to 11 widgets (Lookup, Rename, Search, Collection ×2, Verify ×2, lbdir ×2, Bootlegs).
  On Windows, Qt renders the Fusion style entirely in software; the shadow forces each affected
  widget to blit into an offscreen buffer, apply a Gaussian blur, and composite back on every
  repaint. With large tables this causes visible lag during resize/scroll. Options:
    (a) Skip shadows on Windows:  `if sys.platform != "win32": apply_panel_shadow(…)`
    (b) Reduce blurRadius from 12 to 4 and offset from (0,2) to (0,1) to lower cost on all platforms.
  Option (a) is the safest short-term fix. Option (b) benefits all platforms.

---

TODO-045: Windows — rglob("*") on main thread in Verify and lbdir "Add Root Folder"
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: verify_tab._on_add_root_folder (verify_tab.py:304) and
  lbdir_tab._on_add_root_folder (lbdir_tab.py:608) both call sorted(root_path.rglob("*"))
  synchronously on the Qt main thread after the file dialog closes. On Windows with NTFS and
  large collections, this freezes the GUI ("Python not responding"). This is the same pattern
  fixed for collection_tab in BUG-034; see _ScanWorker there for the reference fix.
  Fix: add a _AddRootWorker(QThread) to each tab that runs the rglob traversal off-thread,
  emits the discovered folder list, and lets the main thread update the listbox.
  See also: BUG-080.

---

TODO-044: Windows — --disable-gpu Chromium flag applied on Windows, killing GPU acceleration
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: main.py:157–165 unconditionally appends --disable-gpu and --disable-logging to
  QTWEBENGINE_CHROMIUM_FLAGS. These flags were added to work around Linux/XWayland issues
  (EGL_BAD_NATIVE_WINDOW, GPU-process blackout — see BUG-053, BUG-060). On Windows,
  Chromium uses DirectX/ANGLE for GPU compositing, which works well and produces smooth
  scrolling in the Map tab and Attachments tab. Forcing --disable-gpu switches Chromium to
  Swiftshader software rendering, making both tabs noticeably laggy.
  Fix: wrap the flag injection in `if sys.platform != "win32":` so Windows retains GPU
  acceleration while Linux still gets the XWayland workarounds.

---

TODO-043: Admin panel — site-crawler control and live status dialog
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Extend the /admin panel to control the master website site_crawler.
  Site Crawler card: Incremental / Full / Stop buttons, progress bar, live status line.
  Live View modal: polls /api/crawler/status every 1.5 s; shows stage, fetched/304/skipped/
  failed counts, current URL. /api/admin/status now includes "crawler" snapshot.

TODO-042: Mobile-friendly admin control panel
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Web admin page at /admin for managing the backend from mobile or browser.
  Features: DB stats/backup/reset, flat-file update pipeline, scraper start/stop,
  LB master reconcile, server restart (os.execv). Routes: GET /admin,
  GET /api/admin/status, POST /api/admin/restart.

TODO-041: Backend geocoding API endpoints
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: The curator geocoding GUI added in setup_tab.py and dbedit_tab.py requires four backend routes that do not yet exist:
  POST /api/geocode/run        — start geocoder; body {retry_failed: bool}; returns 409 if already running
  GET  /api/geocode/status     — poll running state; returns {running, done, total, current, errors}
  GET  /api/geocode/locations  — list geocoded location rows; query param filter=all|failed|low_confidence|manual
  POST /api/geocode/location   — save a manual lat/lon; body {location, lat, lon, note}
Nominatim (geopy or direct HTTP) should be used with a polite 1-request-per-second rate limit and User-Agent header. DB schema: location_geocodes(location_text PK, source, confidence, lat, lon, is_manual, note, geocoded_at). Add to MASTER_TABLES.

---

TODO-040: [TODO-031 Step 9] Docs — update PROJECT.md and CHANGELOG.md after scraper work
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: After TODO-032 through TODO-039 are complete: update PROJECT.md file structure tree (new backend/site_crawler.py, gui/scraper_tab.py), DB schema section (scrape_sessions + page_cache_state), API routes section (/api/crawler/*), and Tech Stack table if any new deps were added. Prepend CHANGELOG.md entry summarising the full TODO-031 scraper tab implementation. This TODO should be the last closed item in the TODO-031 work sequence.

---

TODO-039: [TODO-031 Step 8] gui/main_window.py — register Scraper tab, update order
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Import ScraperTab from gui/scraper_tab.py. Add it to the tab widget after Setup (or wherever fits the intended tab order). Update tab count assertions or comments if present. Verify no initialization-order issues with other tabs that may reference scraper state.

---

TODO-038: [TODO-031 Step 7] gui/setup_tab.py — strip all scraper controls
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Remove from gui/setup_tab.py: all entry-scraper controls (Scrape All Missing, Scrape Range, Single Entry, Force re-scrape, Use local pages, Download attachments, Re-scrape Private LBs, Download Missing Pages, delay spinner, progress bar, stop button), the Bootleg Catalog scrape section, and the scraper log widget. Keep: DB management, master data import/export, SoX path, and forum credentials. Update any signals/slots that referenced removed widgets.

---

TODO-037: [TODO-031 Step 6] gui/scraper_tab.py — 6 sub-panels
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create gui/scraper_tab.py with 6 collapsible QGroupBox panels: (1) Control & Status — scope selector, Start/Stop/Pause, live ticker, progress bar, counts; (2) Entry Pages — existing scraper controls moved from Setup tab; (3) Bootleg Catalog — existing LBBCD scrape controls moved from Setup tab; (4) Session History — scrape_sessions table, click-to-filter Change Log; (5) Change Log — queryable entry_changes joined to scrape_sessions; (6) Settings — delay, jitter, daily cap, toggles. Move scraper log widget here from Setup tab.

---

TODO-036: [TODO-031 Step 5] API routes /api/crawler/* in app.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add Flask routes to backend/app.py: POST /api/crawler/start (body: {scope, start_url, force}), GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/history (paginated scrape_sessions rows), GET /api/crawler/page_cache (paginated page_cache_state). Follow existing scraper route patterns. Add migration comment if any existing route signature changes.

---

TODO-035: [TODO-031 Step 4] backend/site_crawler.py — spider engine
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create backend/site_crawler.py with: crawl(start_url, session_id, force, scope), _discover_links(html, base_url), _fetch_page(url, stored_last_modified) → (status, body, last_modified), _cache_path(url) mapping URLs to data/pages/ sub-dirs, get_crawler_status(), stop_crawler(). Rate limiting: 1500ms default delay ±20% jitter, 750ms for 304-check-only requests, Retry-After on 429, exponential backoff on connection error. Daily request cap. robots.txt read once per session. Separate _crawler_state dict and _crawler_lock (does not share state with scraper.py).

---

TODO-034: [TODO-031 Step 3] Update path refs in scraper.py, app.py, forum_poster.py, attachments_tab.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Audit all imports of PAGES_DIR and ATTACHMENTS_DIR across scraper.py, app.py, forum_poster.py, and gui/attachments_tab.py. Confirm they still point to the correct locations after the SITE_DIR addition in TODO-032. Add SITE_DIR import where site-crawled content will be read. No functional behaviour change — path wiring only.

---

TODO-033: [TODO-031 Step 2] db.py — scrape_sessions + page_cache_state tables + helpers
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add scrape_sessions(id PK, started_at, finished_at, scope, start_url, pages_fetched, pages_304, pages_skipped, pages_failed, files_fetched, status, notes) and page_cache_state(url TEXT PK, last_fetched_at, last_modified, body_sha256, content_type, size_bytes, status_code, session_id FK) to db.py init_db(). Add helpers: create_scrape_session(), update_scrape_session(), upsert_page_cache(), get_page_cache(url), get_scrape_sessions(). Use idempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS for safety on existing DBs.

---

TODO-032: [TODO-031 Step 1] paths.py — replace PAGES_DIR/ATTACHMENTS_DIR with SITE_DIR hierarchy
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: In backend/paths.py, add SITE_DIR = DATA_DIR / "pages" / "site" and ensure PAGES_DIR and ATTACHMENTS_DIR constants remain unchanged (detail pages and attachments dirs are not moving). Create the data/pages/lbbcd/ and data/pages/site/ sub-directories as needed. No consumer code changes in this step — those follow in TODO-034.

---

TODO-031: Dedicated Scraper tab + full-site crawler (replaces scraping section in Setup)
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Move all scraping controls out of Setup tab into a dedicated Scraper tab. Add a full domain-aware site crawler that produces a complete offline mirror of losslessbob.wonderingwhattochoose.com using If-Modified-Since for efficient incremental updates. Sub-tasks: TODO-032 through TODO-040.

---

TODO-030: Bootleg-CD Catalog (LBBCD) — scraper, tables, Bootlegs tab, and cross-tab integration
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Scrape and store the LosslessBob bootleg titles catalog from LB-bootleg-by-title.html.
  Schema: bootleg_titles + bootleg_scrapes tables (added to MASTER_TABLES). New backend/bootleg_scraper.py.
  New gui/bootlegs_tab.py. 5 new /api/bootlegs/* routes. Cross-tab integrations: Search (badge),
  Lookup (titles in summary), Collection (Bootleg column), DB Editor (bootleg count).

---

TODO-029: Save / restore column-width defaults across all GUI tabs
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: Allow the user to snapshot their current column layout as reusable defaults and restore to them (or to factory defaults) on demand. GuiStateStore: save_user_defaults(), restore_user_defaults(), restore_factory_defaults(). UI: "Column Widths" group in Setup/Theme tab with Save/Restore/Factory buttons.

---

TODO-028: Click-to-sort on Rename tab main table
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-20
Description: Rename tab uses RenameModel (QAbstractTableModel) + QTableView. Added QSortFilterProxyModel wrapper. lessThan() sorts by: Current Folder Name, LB Found (numeric), Proposed Name, State (custom rank). Wire header sectionClicked; default sort by Current Folder Name ASC. Proxy maps indices back to source before mutating.

---

TODO-027: Click-to-sort on Lookup tab summary and detail tables
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: Lookup tab uses QAbstractTableModel + QTableView. Added QSortFilterProxyModel wrapper to both tables. Custom lessThan() uses typed sort keys consistent with sort_key_for(). Wire header sectionClicked to toggle direction. Default: summary sorted by LB Number ASC, detail by Filename ASC.

---

TODO-026: Flat-file update check rework (CC_LB_INTEGRITY item 9)
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: New backend/flat_file.py pipeline: discover→download→diff→apply with audit trail in flat_file_releases + flat_file_changelog tables. 7 new API endpoints under /api/flat_file/*. Setup tab UI rework with _DiscoverThread, _UpdateAvailableDialog, Flat File History panel. Removed broken check_for_update() from scraper.py.

---

TODO-025: Click-to-sort across all tables
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: SortableTableItem and sort_key_for() in gui/widgets/sort_keys.py. Client-side sort for lbdir and verify QTableWidget tables. In-memory sort for Search, Collection, Missing QTableView tables. Server-side sort for DB Editor. GuiStateStore.get_sort()/set_sort() added.

---

TODO-024: Override export/import JSON
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import. DB Editor buttons for Export and Import Overrides in the Integrity panel.

---

TODO-023: Reliable column width persistence (CC_LB_INTEGRITY item 11)
Priority: Medium
Status: Done
Added: 2026-05-17
Closed: 2026-05-17
Description: GuiStateStore in gui/widgets/state_store.py storing state in data/gui_state.json (atomic writes, 500ms debounce, _restoring guard). Migrated all tabs off QSettings / hardcoded setColumnWidth. One-time QSettings migration on first run. Covers Search, Collection (7 tables), DbEdit, lbdir summary, Rename. ThemeTab QSettings and main_window geometry also migrated to GuiStateStore.

---

TODO-022: GitHub release upload from "Publish Master Update" button
Priority: Low
Status: Done
Added: 2026-05-17
Closed: 2026-05-19
Description: After the export endpoint produces data/exports/<file>.db + .manifest.json, automate the upload to the kuddukan42/losslessbob GitHub releases via the gh CLI. Tag scheme: master-YYYY-MM-DD with auto-bump (.2, .3) on same-day re-release. Auto-generate release notes from lb_status_history rows since the last published master_version.

---

TODO-021: Status filter combobox on remaining tabs (Lookup, Attachments, Rename, Verify, lbdir)
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: lb_status background coloring and optional filter combobox. Done: Lookup tab (filter combobox + Private/Missing row tinting), Attachments tree (page-level batch tinting), Rename tab (LB Found col tint), Lbdir summary (LB# col tint). Verify tab skipped — lb_number not available in verify results without backend change.

---

TODO-020: Master data publish/subscribe system (curator workflow)
Priority: Low
Status: Done (partial — GitHub release publishing deferred)
Added: 2026-05-16
Closed: 2026-05-17
Description: POST /api/master/export and POST /api/master/import. MASTER_TABLES / USER_TABLES / MASTER_META_KEYS constants. Curator-mode flag + checkbox. 13 tests in tests/test_master_data.py. GitHub-release-via-gh-CLI upload deferred (see TODO-022).

---

TODO-019: lb_alias and folder_lb_link disambiguation tables
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-18
Description: lb_alias (master) and folder_lb_link (user) tables. Rename tab resolution order: folder_lb_link first, lb_alias collapse second, fall back to multiple_ids. Curator creates aliases in DB Editor Aliases panel. 7 API endpoints. Right-click "Link…"/"Unlink…"/"Save as master alias…" actions in Rename tab.

---

TODO-018: NFT folder-name suffix for Private LBs
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: _apply_status_suffix() helper in backend/folder_naming.py. Rename tab and Collection tab append -NFT to proposed folder names for Private LBs. GET /api/lb_master/<lb>/nft integration.

---

TODO-017: Periodic re-scrape of Private LBs to detect newly-published pages
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: "Re-scrape Private LBs" button in Setup tab. Iterates every lb_status='private' row, attempts a fresh scrape, calls reconcile_lb_status() to flip status if a page is now found. Shows completion summary.

---

TODO-016: Make forum post footer attribution (username/version) configurable
Priority: Low
Status: Done
Added: 2026-05-15
Closed: 2026-05-18
Description: Read username from forum credentials and version from a project constant. Footer no longer hardcoded in forum_poster.py.

---

TODO-015: db_reset should drop torrents and rename_history tables
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: Added DROP TABLE IF EXISTS rename_history and torrents to the executescript drop sequence in backend/app.py:db_reset.

---

TODO-014: Confirm _mychecksums filename convention and finalize TORRENT_EXCLUDE
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: generate_checksums() renamed from _lbgen_* to _mychecksums_* convention; TORRENT_EXCLUDE_PATTERNS already matched this pattern and requires no change.

---

TODO-013: Path relocation flow for stale torrent records
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: When a torrent's source_folder is no longer valid (red indicator in the history panel), allow the user to browse for the new folder location, cross-check files against checksums, and optionally rename the folder to the standard format.

---

TODO-012: Torrent history panel in My Collection tab
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: Torrent history sub-panel in My Collection tab. Green/red indicator for source_folder_exists; Regenerate button when torrent_path is missing; Add to qBittorrent and added_to_qbt_at per record.

---

TODO-011: xref filter on Search and Collection tabs
Priority: Low
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: "Xref only" checkbox on Search tab and My Collection tab. Backed by GET /api/checksums/xref_lb_numbers (db.get_xref_lb_numbers).

---

TODO-010: xref support in lookup, rename, search, collection
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: xref support across all tabs. Naming: LB-XXXXX-xrefXXXX (zero-padded to 4 digits). Lookup duplicate resolution, Rename xref suffix, Search/Collection xref filters, complete xref match wins over partial primary LB match.

---

TODO-009: Rename tab — Multiple IDs right-click resolution
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: Right-click context menu for "Multiple IDs" rename reason. Select which LB to apply; block rename until ambiguity resolved. Unique color for Multiple IDs.

---

TODO-008: FEAT-14 — Database Editor Tab
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: DB Editor tab (gui/dbedit_tab.py) with table browser, paginated row viewer, inline cell editing, row deletion, CSV export. Backend routes: GET /api/dbedit/tables, schema, rows, PATCH row, DELETE rows, GET export.

---

TODO-007: FEAT-13 — Granular Collection Data Management
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: Fine-grained purge control for user data (collection, wishlist, personal meta, integrity events, entry changes). Bulk delete from collection tab. Select All/None buttons in My Collection.

---

TODO-006: Close stale temp-DB connection in importer._import_flat_file
Priority: Low
Status: Done
Added: 2026-05-12
Closed: 2026-05-18
Description: Delete the cached entry from _local.connections for the temp path after unlink to avoid stale handle on next import in the same thread.

---

TODO-005: GUI viewer for entry change history (DB-08 follow-up)
Priority: Low
Status: Done
Added: 2026-05-12
Closed: 2026-05-19
Description: "History" button on the detail panel calls GET /api/entry/<lb>/changes and displays a table of field diffs with timestamps.

---

TODO-004: Add type hints and docstrings to app.py route handlers
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-19
Description: Flask route functions now have type hints and Google-style docstrings per project code standards.

---

TODO-003: Add type hints and Google-style docstrings to scraper.py public functions
Priority: Medium
Status: Done
Added: 2026-05-07
Closed: 2026-05-19
Description: `scrape_entry`, `scrape_range`, `get_scrape_status`, `stop_scrape`, and `check_for_update` have type hints and docstrings.

---

TODO-002: Bulk-download pages HTML to pages/ folder without scraping metadata
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: "Download Pages Only" button fetches and caches all missing LB-XXXXX.html files to data/pages/ without parsing metadata or writing to the DB.

---

TODO-001: Show local pages coverage count in Setup tab
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: Display a count of HTML files present in `data/pages/` next to the "Use local pages" checkbox (e.g. "13,124 pages cached").

---

TODO-024: Map tab — interactive map of concert locations
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: gui/map_tab.py using QWebEngineView + Leaflet.js to render concert locations from location_geocoded table as clickable markers. Phase 1: basic map. Phase 2 (CC_MAP_FEATURE.md fully implemented): local Leaflet assets, QWebChannel bridge (_MapBridge), Viewport Filter toggle, "List in Search", curator geocoding panel in DB Editor.
