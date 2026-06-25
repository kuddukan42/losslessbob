TODO-185: tapematch — segment-level overlap rescue (clapping-wav / partial-source matching)
Priority: Medium
Status: Open
Added: 2026-06-24
Description: The 1991-11-05 polarity dry-run (TODO-184 step 3) showed the dominant remaining
  driver of false "distinct" verdicts on the contradicted-claim dates is NOT channel inversion
  but PARTIAL OVERLAP: curators assert same-source from a SHORT shared region ("same clapping
  wavs at end of d1t1/d1t8/d1t10") inside patchwork/composite recordings (e.g. LB-09174 = a
  cassette+CD splice, performance trimmed to 4934s vs ~6100s for its siblings). The primary
  residual matrix takes the MEDIAN residual_corr across whole-recording anchors, so a genuine
  match confined to a few track-boundary segments is averaged out to ~0.003 and the pair is
  called distinct. Whole-recording metrics (incl. the TODO-184 polarity cross-terms) cannot
  recover this by construction.
  Goal: detect and surface localized same-source overlap so these pairs read as "same source,
  partial" rather than "distinct".
  Notes / direction (not yet decided):
    - secondary_corr_pair already computes a windowed-coverage FRACTION (fraction of 60s windows
      above a per-window threshold) + a quiet-segment hiss pass; cluster() can link on
      W[i,j] >= w_threshold. So some machinery exists — first step is to audit why the
      windowed/hiss path did NOT link these known-partial pairs (threshold too high? composite's
      matching region too short relative to the window grid? speed offset defeating per-window
      lag?). Calibrate against the curator-confirmed partial pairs as positives.
    - Consider an explicit "best contiguous run" statistic (longest stretch of consecutive
      high-corr windows / hiss segments) instead of, or alongside, the global fraction — a
      30-60s genuine overlap is a strong same-chain signal even at low whole-recording coverage.
    - Reuse the TODO-184 side memmaps: a partial overlap can ALSO be polarity-inverted, so the
      segment search should run on the best polarity pairing per window.
    - Report as evidence for manual ratify (like lineage), not an automatic whole-source merge —
      a partial match means shared lineage of a SECTION, which is exactly the patchwork story.
  Depends on / relates to: [[TODO-184]] (polarity rescue: side memmaps, rescue plumbing,
  keep-if-improves safety pattern).

TODO-184: tapematch — rescue same-source false-negatives (channel-polarity inversion + partial overlap)
Priority: Medium
Status: In Progress
Added: 2026-06-24
Description: Across the Jun-22 analysis batch, tapematch repeatedly contradicts LB curator
  "same recording" commentary with near-zero correlation (~37 contradicted vs 3 corroborated
  among verdicts that cite an explicit same-source claim). Root-cause audit:
    - SPEED OFFSET — ALREADY HANDLED. estimate_ratio search is ±30000 ppm, lag-slope
      refine_speed_ratio (config refine.enabled) and the high_ppm secondary_corr_pair path
      were committed 2026-06-21. The opus Winnipeg (1990-06-17) analysis that flagged speed
      as the cause was written 2026-06-20, i.e. before that fix landed.
    - CHANNEL-POLARITY INVERSION — NOT handled. Curator notes like "right channel inverted"
      / "channels swapped and wavs inverted" (e.g. 1991-11-05 LB-10660) defeat correlation
      because Pass 1 ingests MONO ONLY (cli.py:143 mono=True, a deliberate RAM optimisation),
      so the L-R side signal needed to detect a one-channel polarity flip is discarded before
      matching. residual_corr's abs() only catches a WHOLE-signal flip (both channels), not
      one inverted channel, and a pure L<->R swap (no inversion) already survives the L+R
      mixdown. So the unhandled subset is specifically single-channel polarity inversion.
    - PARTIAL OVERLAP / PATCHWORK COMPOSITES — partially handled. secondary_corr_pair's
      windowed-coverage fraction can link a partial match, but whole-recording median corr
      still collapses and the verdict reports needs-review.
  PLAN (staged):
    1. [done] Config-gated polarity block + polarity-aware correlation helper + unit test
       (synthetic inverted-channel pair must be rescued; independent pair must NOT merge).
    2. [done] Wired stereo ingest behind the flag: Pass 1 (cli.py) now decodes stereo when
       polarity.enabled and writes an L-R "side" memmap per stereo source (same trim bounds as
       mid); the residual matrix loop re-scores a near-zero pair (med < rescue_corr_ceiling) via
       match.polarity_rescue (mid-side / side-mid, each with its OWN per-anchor lag lock, speed-
       corrected by the pair ratio), keeps the max, logs POLARITY_RESCUE. _mmap_side helper +
       side_paths dict added; default path is flag-guarded and byte-identical. 6 polarity tests +
       22-test matcher subset green.
    3. [todo] Re-run the ~37 contradicted-claim dates with polarity: true on (validate the
       Pass-1 stereo memory profile on real multi-source dates first); confirm rescues are
       genuine (curator-claimed) and no spurious merges appear; then consider default-on.
    DRY-RUN 2026-06-24 (1991-11-05 Madison, 5 sources, polarity:true via temp config, non-
    destructive — staged symlinks, package CLI direct, no archive/DB write):
      - PLUMBING VALIDATED: all 5 sources decoded stereo + got side memmaps; POLARITY_RESCUE
        fired on 4 eligible pairs. Memory peaked RSS ~2.7 GB (vs ~1.1 GB mono estimate) — the
        resample of BOTH mid and side for high-ppm pairs is the spike; acceptable but real.
      - SAFETY VALIDATED: every off-diagonal stayed ~0.002-0.007 (max 0.0065); rescue nudged
        only 0.002->0.003; n_families 5 == baseline 5. No false merge despite all pairs eligible.
      - NO RESCUE WIN HERE: LB-10660's "channels swapped and wavs inverted" is NOT a whole-
        recording single-channel inversion — the curator match is SEGMENT-level ("same clapping
        wavs at end of d1t1/d1t8/d1t10") inside patchwork composites (LB-09174 is cassette+CD,
        perf trimmed to 4934s). A whole-recording cross-term corr averages over mostly non-
        matching material -> stays near-zero. This date is really the PARTIAL-OVERLAP class.
      - IMPLICATION: partial-overlap/segment matching (clapping-wav level) looks like the bigger
        remaining lever for the contradicted-claim dates than polarity. To demonstrate a polarity
        WIN, pick a date whose curator note is a clean whole-recording "right channel inverted"
        (not segment clapping-wav). Consider a new TODO for segment-level overlap rescue.

TODO-183: Concert Ranker — audio quality scoring & ranking
Priority: Medium
Status: In Progress
Added: 2026-06-23
Description: New `concert_ranker/` package (repo root) that scores the audio quality of the user's
  own copies and ranks the best transfer of each show. The "scoring brain" (config/scoring/features/
  calibrate/audio.cache) arrived pre-built + synthetic-tested in the v1 package; this session wired it
  to the real machine per instructions/CC_CONCERT_RANKER.md — DONE: DB integration (lb/repo.py + USER
  tables quality_scans/quality_recording_metrics/quality_recording_scores), source-class derivation
  (lb/source_type.py), commentary mining (lb/commentary.py), real ffmpeg decode (audio/io.py),
  per-folder scan + producer/consumer staging loop (scan.py/runner.py, crash=scrap), recording_families
  ranking + standalone fallback (families.py), calibration harness orchestration (calibration.py), and
  the scan/calibrate/rerank/report CLI (cli.py). 11 pytest tests pass; verified end-to-end on real
  generated audio (scan→rank→rerank→report).
  CALIBRATION (done 2026-06-23): ran `calibrate` on a 117-show sample (73 AUD + 44 SBD), staged via
  /mnt/DATA2, recorded as scan_id 3. Replaced the first-principles SIGNED/SEVERITY/QUALITY band cutoffs
  + crowd_snr "buried" disqualifier in config.py with values fitted from the AUD percentiles (label-fires
  476→171; muddy/dull/boomy no longer fire on ~everything; harsh/hissy/thin/bright now functional).
  Source-class derivation switched to trust the curator entries.source_type column. Staging added to
  scan/calibrate CLI.
  ROUND 2 (done 2026-06-23): de-confounded harsh_ratio_db (now a local 2-5 kHz bump; rating rho
  +0.44->+0.06) and hiss_floor_db (now quiet-vs-loud HF persistence; rho +0.31->-0.52, correctly
  negative). Re-scanned the 117-show sample as scan_id 4, refit harsh/hiss bands — "hissy"/"harsh"
  now fire only on B-/C/D shows (zero A-tier false positives, verified against LB comments).
  ROUND 3 (done 2026-06-24): reworked dropout_count (isolated-discontinuity detection + worst-track
  aggregation; clean shows now 0, glitchy tracks surfaced) and hum_excess_db (50/60 Hz harmonic comb;
  no longer confounded by bass). Added decade-stratified sampler + `calibrate --by-decade`. Launched
  overnight scan_id 6 = 697 recordings across all 6 decades (all bad-tier included) for further iteration.
  ROUND 4 (done 2026-06-24): ran the overnight 697-show decade scan (scan_id 6, 696/697 ok), fixed a
  score_separation None-handling crash, and refit ALL bands + the dropout disqualifier (->6900, worst-
  track p95) from the 697-set into config.py. De-confounding held at scale (hiss -0.64 = top predictor);
  crowd-heavy recall restored. label-fires 1117->930; verdicts validated vs LB comments.
  ROUND 5 (done 2026-06-24): PER-DECADE bands implemented — config.DECADE_BANDS (1960s-2010s, AUD
  percentiles from scan_id 6); scoring.all_bands/explain_recording + families.rank_scan band each
  recording against its own era (global fallback when decade unknown). 'hissy' now ~10%/decade instead
  of vintage-over-flagged / modern-never-flagged. 13 tests pass.
  ROUND 6 (done 2026-06-24): PER-CLASS bands (hybrid). config.CLASS_BANDS["SBD"] + resolve_band_set();
  SBD/FM band hiss + tonal against soundboard norms. crowd_snr held GLOBAL/absolute for all classes —
  full per-class relativization wrongly made ~60% of soundboards read "crowd-heavy"; within-class
  fairness is already in the MAD-z ranking. 14 tests pass.
  ABSOLUTE SCORE (done 2026-06-24): concert_ranker/quality_score.py + config.QUALITY_MODEL — ridge
  model gives every recording a 0-100 score + A+..F grade (prepended to verdicts; stored as
  quality_recording_scores.abs_score/abs_grade). Held-out CV correlation to LB rating: Spearman 0.65,
  93% within one letter tier. Middle filled via scan_id 7 (C tier 7->132).
  REMAINING:
    - QUALITY_MODEL is AUD-fit, applied to all classes — fit/validate a separate SBD model; refit when
      scan 6 is re-scanned with the current dropout detector for a fully clean combined set.
    - SBD-per-decade bands (deferred — sparse, esp. 2010s n=7); per-decade DISQUALIFIERS (still global).
    - dropout_count FIXED (2026-06-24): reworked to locally-normalized roughness; rho vs rating
      +0.43 -> -0.04, counts sane. Threshold now provisional 150 — REFIT from a fresh full scan
      (scan_id 6's stored dropout values are from the old detector).
    - hum_excess_db comb detector fires on the bigger set with a mild residual +0.22 lean — investigate.
    - lossy_flag never fires — NOT calibratable without labeled known-lossy files; needs a handful of
      known-lossy recordings to tune the 25 dB brick-wall. Parked/inert.
    - True 5–9 kHz sibilance + dynamic_range_dr from the NativeProbe (not yet produced by the scan).
    - Polish band-label phrasing; GUI surface for quality scores/verdicts (backend + CLI only so far).

TODO-182: Explore "best LB per date" via user voting — unsure how this would work
Priority: Low
Status: Open
Added: 2026-06-22
Description: Idea: let users vote on which LB recording is the best source for a given
  date, surfaced as a "community pick" per date. Not yet scoped/decided how this would work.
  Key tradeoff: this app is single-user/local (SQLite + local Flask backend, no shared
  server), so real cross-user voting would need either (a) a new shared backend service to
  aggregate votes, which is a big architectural lift, or (b) piggybacking on the WTRF forum —
  e.g. a sticky "best of" thread that gets scraped/parsed similarly to the curated lists in
  TODO-181 — which fits the existing architecture far better. Needs a decision before any
  implementation.

TODO-181: Add curated "best of" lists as filter views (carbonbit, 10haaf)
Priority: Medium
Status: In Progress
Added: 2026-06-22
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

TODO-180: Show total collection size in GB somewhere in the UI
Priority: Medium
Status: Open
Added: 2026-06-22
Description: No metric currently exists for the actual size of the user's recording
  collection content. get_disk_usage_stats (backend/filer.py:61-81) only reports per-mount
  disk free/total/used_pct (filesystem-level, not collection content), surfaced on
  ScreenMounts.tsx. Need to compute total bytes across all my_collection folders (sum of
  on-disk folder sizes for owned LBs) and surface it somewhere in the UI — candidates:
  Collection screen header/stats, Home screen, or the AppShell footer stats bar
  (AppShell.tsx:814-820, alongside checksum_count/bootleg_count).

TODO-179: Consider removing the top bar to gain vertical space
Priority: Low
Status: Open
Added: 2026-06-22
Description: Tentative idea (user said "maybe") — consider removing the Topbar component
  (gui_next/src/renderer/src/components/AppShell.tsx:565+, breadcrumbs + actions, 52px height)
  to reclaim vertical space for screen content. Needs a decision on where breadcrumbs/
  per-screen actions would go instead (e.g. fold into each screen's own header) before
  actually removing it — not yet committed, just flagged as worth considering.

TODO-178: Minimized left sidebar — new icon-only nav representation
Priority: Low
Status: Open
Added: 2026-06-22
Description: No collapsed/minimized sidebar mode currently exists in
  gui_next/src/renderer/src/components/AppShell.tsx (Sidebar component, ~lines 120-561) —
  nav items always render icon + label. Implementing "new icons for when left bar is
  minimized" depends on first adding a minimize/collapse toggle for the sidebar, then
  rendering a icon-only nav state (just the Icon, no label, narrower width) using new icon
  assets suited to that compact form.

TODO-177: Implement the new app icon
Priority: Low
Status: Open
Added: 2026-06-22
Description: Replace the app icon with a new design. No icon asset exists yet in the repo
  (gui_next/resources/ only has installer.nsh; no .ico/.icns/.png app icon found) and no new
  asset has been provided yet — needs the actual icon file before implementation, then wire
  it into the Electron build config (gui_next build resources) and installer.

TODO-176: Performance page year dropdown — switch to a tabulated (grid) layout for readability
Priority: Low
Status: Open
Added: 2026-06-22
Description: The Year filter dropdown on gui_next/src/renderer/src/screens/ScreenBootlegs.tsx:
  243-277 (yearsOpen/yearsDropRef) renders years as a single-column scrollable list
  (maxHeight: 280, overflowY: 'auto') — across ~60+ years of touring this is a long, hard-to-
  scan list. Change it to a tabulated/grid layout (e.g. multiple columns of years, decade-
  grouped) so it's easier to read and pick a year at a glance.

TODO-175: DB Editor LB filter box — support multiple comma/space-separated LB numbers
Priority: Low
Status: Open
Added: 2026-06-22
Description: The LB# filter box on gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:1428-1432
  (lbFilter state, dbeditor.lbFilter label) only matches a single LB number — backend
  /api/dbedit/table/<name>/rows (backend/app.py:2800-2864) requires lb_filter to be a single
  integer (`lb_filter.lstrip("-").isdigit()` → `lb_number = ?`). If the user types multiple
  numbers (e.g. "4929, 5683, 9627") it should pull up rows for all of those LB numbers
  (lb_number IN (...)) instead of only matching/accepting one.

TODO-174: Investigate consolidating attachment downloading — metadata scraper vs site crawler overlap
Priority: Low
Status: Open
Added: 2026-06-22
Description: Two separate mechanisms both download attachment files: the metadata scraper's
  download_files option (backend/scraper.py:195-247,423,453-501, wired through every scrape
  path in app.py via the scrape_attachments meta flag) downloads attachments while scraping
  an individual LB detail page; site_crawler.py (the incremental site crawler) independently
  discovers and downloads /files/ URLs site-wide and keeps entry_files.downloaded in sync
  (site_crawler.py:412-426). Neither is deprecated — both are still actively used — but the
  overlap may be worth consolidating into one path. Flagged as possibly complicated to
  untangle (the two paths have different triggers/granularity: per-LB vs site-wide), so this
  needs careful investigation before touching either, not a quick fix.

TODO-173: Confirmed taper tag on LB entries (soomlos, spot, hide, lta, etc.) — only show when confirmed
Priority: Medium
Status: Open
Added: 2026-06-22
Description: entries.taper_name (backend/db.py:137) already exists and is populated
  heuristically by extract_taper_and_source() (db.py:678-811), which parses free-text
  descriptions for "Taper:" labels etc. — but it's unconfirmed/best-guess text, no curation
  or confidence flag, and nothing gates whether it's shown. Add a real taper tag concept:
  a curated set of known taper names (soomlos, spot, hide, lta, and others as identified)
  with a confirmed flag per entry, and only display the tag in the UI when an entry's taper
  is confirmed — not just whatever extract_taper_and_source guessed from the description text.
  Needs a DB field/table for the confirmed flag (separate from or alongside taper_name) and
  UI work to surface the tag (e.g. as a pill) on confirmed entries.

TODO-172: DB Editor — make it more like a real SQL management tool (SSMS-style)
Priority: Low
Status: Open
Added: 2026-06-22
Description: Note: column-header click-to-sort already exists (ScreenDbEditor.tsx:1492-1509,
  with ▲/▼ indicator) — not a gap. Broader ask is to make gui_next/src/renderer/src/screens/
  ScreenDbEditor.tsx feel more like SQL Server Management Studio generally. Candidate
  features to scope out: resizable/reorderable columns, a schema tree sidebar (tables/views
  grouped, expandable to show columns+types), multi-tab query windows (multiple
  SqlQueryPanel instances open at once, ScreenDbEditor.tsx:566), copyable cell/row selection
  in the results grid, query history/favorites, pinned/frozen first column, and per-column
  type-aware cell formatting (dates, booleans, NULL styling) in the rows view.

TODO-171: Add TapeMatch's observations.db as a selectable database in DB Editor
Priority: Low
Status: Open
Added: 2026-06-22
Description: DB Editor (gui_next/src/renderer/src/screens/ScreenDbEditor.tsx) currently
  only supports two databases via activeDb: 'losslessbob' (main DB) and 'batchverify'
  (BATCH_VERIFY_DB_PATH) — db picker at ScreenDbEditor.tsx:1290-1304, backend resolution in
  _dbedit_db_path()/_dbedit_is_batchverify() (backend/app.py:96-103), used throughout the
  /api/dbedit/* routes (app.py:2742-2973). Add a third option for TapeMatch's observations.db
  (tools/tapematch/, per project memory) so its tables can be browsed/edited the same way,
  likely read-only given it's tool-generated data.

TODO-170: Add a dedicated TapeMatch screen — visualize results, review logs, provide user
  feedback/corrections, and manage running the scripts
Priority: Medium
Status: Open
Added: 2026-06-22
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

TODO-169: Home screen — remove ingest box, doesn't serve a purpose and takes up space
Priority: Low
Status: Open
Added: 2026-06-22
Description: Remove the "Hero ingest card" on gui_next/src/renderer/src/screens/ScreenHome.tsx
  (~lines 187-214, home.ingestNew/home.ingestTitle/home.ingestDesc i18n keys). User finds it
  doesn't serve a purpose and just takes up space on the Home screen. Remove the card and
  its now-unused locale keys from all 6 locale files.

TODO-168: Sidebar bottom-left shows hardcoded fake username — replace with real WTRF username
Priority: Medium
Status: Open
Added: 2026-06-22
Description: gui_next/src/renderer/src/components/AppShell.tsx:440-464 hardcodes a fake
  identity in the sidebar's bottom-left: "RW" avatar initials and the name "rolling.thunder"
  (with "Local · 4 mounts" subtitle). Replace with the actual WTRF forum username — the same
  value saved via /api/credentials/wtrf and surfaced in ScreenSetup.tsx (wtrf_username,
  handleWtrfSave/handleWtrfTest) — or render blank/no-name state if no WTRF credential is
  configured.

TODO-167: Geocode locations from setlistfm_shows and bobdylan_shows tables
Priority: Medium
Status: Open
Added: 2026-06-22
Description: backend/geocoder.py (run_batch, _get_performance_location_string) currently only
  geocodes location strings sourced from the `performances` table (raw LB metadata,
  source='performances' in location_geocoded). It does not pull venue/city from
  setlistfm_shows (db.py:530-541, venue_name/city/country columns) or bobdylan_shows
  (db.py:508-518). Extend geocoding to cover these two tables as additional sources — likely
  relevant to fixing the blank Map screen (BUG-215) since more complete location_geocoded
  coverage means more pins on the map.

TODO-166: Collection screen — view/filter folders stored in nonstandard locations (not matching mount routing)
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a view or filter on gui_next/src/renderer/src/screens/ScreenCollection.tsx
  to surface my_collection folders whose disk_path doesn't match the expected mount/year
  routing — i.e. _mount_for_path (backend/integrity_monitor.py:115) resolves to a mount
  other than the one upsert_collection_routes (backend/db.py:5057) says that folder's year
  should route to, or resolves to no configured mount at all. Lets the user spot folders
  that drifted to a nonstandard location instead of finding them by accident.

TODO-165: Deprecate old fingerprinting — remove code and UI
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Remove the old fingerprinting feature: backend/fingerprint.py, its routes in
  backend/app.py, references in backend/integrity_monitor.py, and the
  gui_next/src/renderer/src/screens/ScreenFingerprint.tsx screen + its nav entry in App.tsx.
  Need to confirm integrity_monitor.py doesn't depend on fingerprint.py for anything still
  in active use before deleting (check usage there first) — being replaced by/superseded by
  whatever the new approach is (not specified yet).

TODO-164: Theme screen — add high-contrast toggle (bright white text on dark themes)
Priority: Low
Status: Open
Added: 2026-06-22
Description: gui_next/src/renderer/src/screens/ScreenThemes.tsx manages the theme CSS vars
  (--lbb-bg, --lbb-surface, --lbb-fg, etc., see vars list starting ~line 83) but has no
  accessibility/high-contrast option. Add a toggle on the Themes screen that, when enabled,
  bumps text color (--lbb-fg and related fg vars) to bright white on dark themes for better
  readability/contrast.

TODO-163: Unified Library context panel — show actual attachments list, not just a count
Priority: Medium
Status: Open
Added: 2026-06-22
Description: AssetStrip in gui_next/src/renderer/src/components/library/DetailPanel.tsx:506-544
  currently only shows an attachment count (t('library.assets.attachments', { count: attachCount })
  / noAttachments). Add the actual list of attachments (names/links, not just a number) to the
  Unified Library context/detail panel so users can see and open individual attachments
  without leaving the panel.

TODO-162: Add Olof's Files database table + scrape show/tour info into it
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a new DB table for Olof's Files (Dylan tour/setlist archive) data, modeled
  on the existing setlistfm_shows table (backend/db.py:533-541), and a new scraper module
  (alongside backend/bobdylan_scraper.py and backend/site_crawler.py) to pull show and tour
  info from olofsfiles.com into it. This is a candidate secondary source for the tour-name
  gaps tracked in TODO-153 — setlist.fm's tour_name field is empty for a large share of
  dates, and Olof's Files may have better/more complete tour coverage.

TODO-161: Pipeline — show inactive/disabled action buttons instead of blank space until they appear
Priority: Low
Status: Open
Added: 2026-06-22
Description: In gui_next/src/renderer/src/screens/ScreenPipeline.tsx, action buttons (e.g.
  Verify/Lookup/Rename/File and similar per-row actions) are currently not rendered at all
  until their step becomes actionable, leaving blank space in the row/detail panel. Render
  them in an inactive/disabled state from the start instead, so the layout stays visually
  consistent and buttons simply enable when their step becomes actionable rather than
  popping in from empty space.

TODO-160: Revamp curator mode — consolidate options and hide existence from normal users
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Curator mode currently exposes itself to every user: AppShell.tsx:400-424 always
  renders a visible "curatorHint" block + "Enable curator mode" link in the sidebar when
  curatorMode is off, so any user can discover and turn it on. The "Curator" nav group
  (AppShell.tsx:78, gated at :226 via `group.gatedGroup && !curatorMode`) and the
  curatorMode/setCuratorMode flag (store.ts:5-17) otherwise work as a simple client-side
  toggle with no real access control. Needs a revamp: (1) consolidate whatever curator-only
  options exist into one coherent settings surface instead of scattering gated items, and
  (2) replace the always-visible hint/link with a hidden trigger (e.g. a secret key
  combo, hidden settings entry, or build-time flag) so normal users have no visible
  indication curator mode exists at all.

TODO-158: Batch forum posting via multi-select or pasted LB list
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Forum posting (backend/forum_poster.py:post_lb_topic, UI in
  gui_next/src/renderer/src/screens/ScreenCollection.tsx) currently posts one LB at a time.
  Add a batch mode: either multi-select rows in the Collection screen or paste/enter a list
  of LB numbers, then post_lb_topic for each in sequence (with per-item success/failure
  reporting) instead of requiring one post action per LB.

TODO-159: LBDIR verify prior to forum post, to ensure integrity before posting
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Before calling post_lb_topic (backend/forum_poster.py), run an LBDIR verify pass
  (backend/checksum_utils.py:verify_folder, same check used in the Pipeline verify step) on
  the folder being posted, to confirm the on-disk audio still matches its checksums. Currently
  nothing blocks a forum post if the folder's integrity has degraded (see BUG-120 for examples
  of verify-fail folders); add a pre-post integrity gate so a bad/modified recording can't be
  posted without at least a warning.

TODO-157: Auto-create torrent + add to qBittorrent on forum post when no torrent exists
Priority: Medium
Status: Open
Added: 2026-06-22
Description: When posting to the forum for a recording that has no torrent yet, the forum-post
  flow should automatically generate the torrent (backend/torrent_maker.py) and add it to
  qBittorrent (backend/qbittorrent.py) as part of a single one-click "post" action in
  backend/forum_poster.py, instead of requiring the torrent to be created/added manually
  beforehand.

TODO-156: Populate all the LB problem entries
Priority: Medium
Status: Open
Added: 2026-06-22
Description: The lb_problems table (backend/db.py:497-503, CRUD in db.py:4803-4894, API at
  app.py:3827+) exists but is not populated for all known problem LB numbers. Need to go
  through known problem cases (e.g. lookup conflicts in BUG-118, verify mismatches in
  BUG-120, reconcile issues in BUG-175) and add corresponding lb_problems rows so they
  surface consistently via get_lb_problem_count()/the lb_problems UI instead of only living
  in BUGS.md.

TODO-155: Improve xref handling
Priority: Medium
Status: Open
Added: 2026-06-22
Description: xref handling needs improvement. Current xref logic lives in the `checksums`
  table (backend/db.py:114, idx_lb_xref0 partial index at :121-122), importer.py:65-164,
  and flat_file.py:362-530 (sync/diff logic comparing xref values between incoming and
  current rows). Lookup-side, the Pipeline Lookup UI surfaces an "Xref" status pill
  (see BUG-201, LookupDetail.tsx STATE_TONE). Specific improvements not yet scoped —
  needs follow-up on what's currently breaking/missing in xref handling before
  implementation.

TODO-154: New DB field for r#### source info (e.g. r9453)
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a new database field to capture "r####"-style source info seen in info
  filenames (e.g. LBF-04929-bd1990-08-16.info.r9453.txt — see
  data/tapematch/runs/20260616_200028_1990-08-16/analysis_input.md:95). This r#### id is not
  currently parsed or stored anywhere in backend/db.py or the importer; need to determine
  which table it belongs on (likely tied to the recording/LB record or a per-file source
  table) and what the r#### value actually identifies (taper/source catalog id) before
  implementing.

TODO-153: Library/perf screen — backfill good tour names across all dates
Priority: Medium
Status: Open
Added: 2026-06-22
Description: The Library screen's tour column (gui_next/src/renderer/src/screens/ScreenLibrary.tsx,
  `p.tour`) is sourced from setlistfm_shows.tour_name joined onto dylan_performances in
  backend/db.py:2121-2206 (tours dict keyed by date_str, applied at line 2204-2206). tour_name is
  empty for a large share of dates, so the column is blank for most performances. Need a way to
  pull/derive good tour names across all dates — likely requires either a better/secondary tour
  data source beyond setlist.fm, or a manual/heuristic backfill (e.g. date-range-based tour
  era tagging) for shows setlist.fm doesn't have tour info for.

TODO-152: Pipeline — Auto-unselect row when it transitions to Filed / In Collection
Priority: Low
Status: Open
Added: 2026-06-18
Description: When a row's file step completes successfully and its bucket becomes 'done'
  (Filed / In Collection), automatically clear its checkbox (set selected: false) in the
  setRows update inside applyFile (ScreenPipeline.tsx ~line 1787). Without this, bulk-filing
  a batch leaves all processed rows still checked, so the user ends up with a growing set of
  selected rows they've already finished working with.

TODO-151: Pipeline — Open button uses stale path after rename/collect
Priority: Low
Status: Open
Added: 2026-06-18
Description: After a folder is renamed or collected (moved), the "Open" button in the
  pipeline detail panel still resolves the old folder name/location. The button should
  use the updated path (post-rename / post-collect destination) rather than the path
  that was current at pipeline run time.

TODO-149: setlist.fm scraper — true incremental update (early-exit pagination)
Priority: Low
Status: Open
Added: 2026-06-17
Description: run_update() in setlistfm.py always walks every API page even when
  force=False. The API returns shows newest-first, so pagination can stop as soon
  as a setlistfm_id is found that already exists in setlistfm_shows. Implement
  early-exit: after INSERT OR IGNORE, check if the row was already present; if a
  full page of shows is all-known, stop paginating. Reduces API calls from ~200
  pages to however many new shows there are since the last sync.

TODO-148: Scraper — persist live log across tab navigation
Priority: Low
Status: Open
Added: 2026-06-17
Description: The live log panel on the Scraper screen is cleared/lost whenever the
user navigates to another tab and returns. Log messages emitted during a run are not
retained, so the full session log is unrecoverable after leaving the screen. Fix should
buffer log lines in component or app state (not re-fetched from backend) so the log
panel re-renders the accumulated history when the screen is revisited. Also consider
a max-line cap to prevent unbounded memory growth during long scrape runs.

TODO-146: Setup — bundle flac.exe in tools/ like shntool.exe
Priority: Low
Status: Open
Added: 2026-06-15
Description: flac is detected via shutil.which("flac") only, so it shows yellow on
every fresh Windows install. flac.exe is a small static binary (~1 MB). Bundle it in
tools/flac.exe and update _find_flac() logic in app.py's spectrogram_check route to
probe tools/flac.exe before PATH (same pattern as _find_shntool() in checksum_utils.py
lines 24-35). This would make flac silently green on all installs with zero user
friction, matching the shntool experience.
  Source: https://xiph.org/flac/download.html  (Windows builds — grab flac.exe only)
  Winget fallback (for TODO-147 hint): winget install xiph.FLAC

TODO-140: tapematch — low-band/time-warp fallback for speed-offset misses
Priority: Low
Status: Open
Added: 2026-06-13
Description: Follow-up from TODO-139 Task 4 (CC_TAPEMATCH_FIXES.md step 5). On
1989-06-04 and 1990-01-12, predicted-lag mode activates correctly but doesn't
recover any of the 8/9 baseline misses — windowed/hiss correlation is ~100x below
threshold at every lag for these pairs, not just near zero, so the limiting factor
is signal content, not search range. Spec's fallback: low-band (250-2000 Hz)
envelope comparison with time-warped *features* (never resample waveforms — see
WORKFLOW.md prohibition). Investigate whether envelope-domain comparison surfaces
correlation these HF-residual/hiss checks miss for these specific pairs. See
tools/tapematch/BASELINE.md "Task 4 results" for full diagnostics (windowed_median/
hiss_median/fp_score ranges per pair).

TODO-144: tapematch — piecewise alignment for staircase/staircase pairs
Priority: Low
Status: Open
Added: 2026-06-13
Description: Follow-up from TODO-139 Task 5 (CC_TAPEMATCH_FIXES.md step 4,
"implement only if step 3 calibration fails"). Calibration of a 5s/2s
short-window residual_corr pass on 2001-10-30 found no usable gap: the
same-source pair (LB-07888/LB-08413) has median residual_corr 0.0118 vs 0.0153
for the different-source-same-show pair (LB-08413/LB-13258) — the
different-source pair scores *higher*, and both distributions' frac>=0.10 is
~0.000-0.002. No fixed threshold at any window size tried (60s/15s/5s) separates
these. Spec's alternative: piecewise alignment — use the staircase lag curve to
locate splice/edit points, split each recording into contiguous segments between
edits, and align+correlate each segment independently rather than via a single
global lag search. Investigate whether per-segment correlation recovers signal
that whole-recording windowed/hiss correlation misses for staircase/staircase
pairs (2001-10-30: 6 misses, 2001-10-07/1996-07-21 also staircase-heavy). See
tools/tapematch/BASELINE.md "Task 5 results" and calibrate_staircase.py for the
calibration data/tooling.

TODO-136: Post editor form for existing WTRF posts
Priority: Low
Status: Open
Added: 2026-06-10
Description: Add a UI form to edit the subject and body of a WTRF forum topic that was
previously posted through the app (or discovered via TODO-135 scraper). The backend
already has the topic_url stored in forum_posts; use SMF's edit-post endpoint (POST to
index.php?action=post2 with the existing msg ID and sa=useredit or equivalent). The GUI
should surface this as an "Edit post…" action on the forum post history entry for an LB
entry — pre-populate subject/body from a scrape of the existing topic, allow editing in a
textarea, then submit. Depends on TODO-135 for posts not originally made through this app.

TODO-135: Scrape WTRF board for existing LB posts
Priority: Medium
Status: Open
Added: 2026-06-10
Description: Scrape the WTRF SMF board(s) to discover which LB entries already have a forum
topic, regardless of whether they were posted through this app. Parse board index pages
(sorted by date) and individual topic subjects to extract the LB number. Store results in
the existing `forum_posts` table (or a parallel `scraped_posts` table) so the GUI can show
"already posted" status on the Rename/post panel without relying solely on the local log.
Should be runnable on-demand (e.g. "Sync from WTRF" button) and optionally on startup.
Credentials already managed by credentials.py; HTTP session logic already in forum_poster.py.

TODO-109: Python best practices — BP document and code review
Priority: Low
Status: In Progress
Added: 2026-06-03
Description: Create a BEST_PRACTICES.md document summarising agreed Python conventions for
this project. Then do a pass over existing backend files to apply improvements: add missing
type hints to older public functions (db.py, app.py, etc.), break up oversized functions
(e.g. init_db), remove late imports, and fill in missing docstrings on exported functions.
Start with db.py as the reference — it was rated 8/10 and has the most surface area.
Note: BEST_PRACTICES.md written 2026-06-09. ruff + pre-commit configured 2026-06-09.
Code-pass over backend files deferred. 36 pre-existing ruff violations remain (E701 x12,
B023 x9, F841 x5, B905 x3, B007 x2, B904 x2, LOG015 x2, F821 x1) — will surface as
blockers when those files are next edited. E501 suppressed in pyproject.toml until then.

TODO-108: Collection tab — fix header UI problems
Priority: Medium
Status: Open
Added: 2026-06-03
Description: Investigate and fix UI problems with column headers on the Collection tab.
  Exact issues to be identified on investigation (misalignment, overflow, sticky behaviour,
  sort indicators, etc.).

---

TODO-107: Disk Scanner — find audio folders on disk for bulk collection add
Priority: Medium
Status: Open
Added: 2026-06-03
Description: Add a Disk Scanner screen that walks user-defined root paths (e.g. /mnt/nas,
  /home/user/music) using os.scandir() with early pruning, finds all directories containing
  lossless audio files (FLAC, WAV, APE, ALAC, AIFF), and presents them as candidates to
  add to the collection DB.

  Backend:
  - POST /api/scanner/scan — accepts {"roots": [...], "extensions": [...]}; walks each root
    with os.scandir(), skips hidden dirs and a configurable exclude list (system paths,
    node_modules, .git, etc.); returns list of {path, file_count, extensions, in_collection}
    where in_collection is True if the path already exists in lbdir.
  - Scan runs in a background thread; streams progress via SSE or returns a job ID to poll.
  - No persistent index — one-shot on demand. plocate can be used as an optional fast-path
    if installed (locate -r '\.flac$' | dirname | sort -u).

  GUI (new ScreenScanner.tsx):
  - Left panel: editable list of root paths to scan + exclude patterns; Scan button.
  - Right panel: results table — path, file count, extensions found, "In Collection" badge.
  - Checkboxes for bulk selection; "Add Selected to Collection" button calls existing
    LBDIR add logic.
  - Progress bar / spinner during scan; cancel button to abort background job.
  - Already-in-collection rows shown but greyed out so user can see full picture.

---

TODO-106: Trading — multi-friend batch compare
Priority: Low
Status: Open
Added: 2026-05-30
Description: Extend the Trading screen to compare your collection against multiple friends at
  once — show a matrix view (friends × shows) so you can find the best candidate to trade
  any given recording with. Also: add a GET /api/trading/friends/<id>/entries route so the
  GUI can retrieve raw friend entries without going through the compare diff endpoint.

---

---

TODO-085: Map tab — sequential date-linked travel view across the globe
Priority: Low
Status: Open
Added: 2026-05-21
Description: Add a new sub-view (or toggle) on the Map tab that renders concert locations
  as a chronological travel trail — polylines (or an animated path) connecting each
  geocoded entry to the next in date order, visualising movement across the globe over
  the years. Current map just plots pins with no temporal linkage.
  Design considerations:
    • Sort geocoded entries by date_str ascending; skip entries with no lat/lon.
    • Draw a Leaflet polyline (or GeoJSON LineString) through the ordered coordinates.
    • Optionally colour-code segments by decade so different eras are visually distinct.
    • Consider a play/scrub slider to animate the route year-by-year.
    • Hook into the existing MapTab _open_filtered_map() or add a separate "Travel view"
      button that generates a different HTML payload from the /api/map endpoint.
    • Cluster of same-venue returns (same lat/lon) should be shown as a loop or ignored
      to keep the line readable.

---

TODO-083: Export HTML — add column picker with more My Collection fields
Priority: Low
Status: Open
Added: 2026-05-21
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

---

