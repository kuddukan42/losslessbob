[2026-07-23] — feat: site-mirror self-verification (TODO-265 bite B1)
Added: tools/verify_site_mirror.py: preservation-stack B1 — re-hashes the site
  mirror and reports missing files, hash drift, orphans and unbaselined rows.
  `--baseline` records the on-disk hash for rows that lack one; default mode is
  read-only verification; `--report` writes a dated file to data/exports/.
  Non-zero exit on missing/drift. Safe to run while the app is up.
Added: backend/db.py: site_inventory.local_sha256 (idempotent PRAGMA-guarded
  migration + DDL). body_sha256 is the hash of the RAW HTTP body, but HTML is
  saved link-rewritten, so it can never match the file on disk — re-hashing
  against it would have reported ~115k false drift errors. local_sha256 records
  the bytes as saved and is the only sound baseline for HTML.
Changed: backend/site_crawler.py: _save() now returns (path, sha256-of-written-
  bytes) and the crawl loop stores it as local_sha256, so every future fetch
  records both hashes. New public is_rewritten_html() is the single source of
  truth for that HTML-vs-verbatim distinction (previously duplicated inline in
  _save and the content_type expression). HTML is written via write_bytes rather
  than write_text so saved bytes are not newline-translated on Windows.
Added: tests/test_site_mirror_verify.py: 14 tests — baseline populates both
  file kinds, a verbatim file disagreeing with body_sha256 is flagged and
  deliberately NOT baselined (rot must keep surfacing), rewritten HTML never
  false-drifts, tamper/delete/stray → drift/missing/orphan, CLI exit codes.
Note: first real run baselined 114,915 files (26.9 s) and verified clean —
  0 missing, 0 drift, 0 verbatim-hash mismatches, zero false HTML drift. It
  also found 171 orphans (140 files/LBF-*, 31 detail/LB-*.html) — files the
  entry scraper downloaded into the mirror without a site_inventory row, since
  it writes entry_files instead (see site_crawler.py:415-419). Benign and
  self-healing on the next full crawl; noted so B2 stages the directory tree
  rather than building its manifest from the inventory table.

[2026-07-23] — fix: library crawl wedged by read-only example folder (BUG-272)
Fixed: tools/tapematch/tapematch_session.py: BUG-272 — the detached library
  crawl died 2026-07-22 20:06 with "10 consecutive failures overall" and sat
  idle ~17 h with 436 dates outstanding. Root cause: some source folders on the
  archive volumes are mode 0o555 and shutil.copytree preserves that mode on the
  copy it leaves in EXAMPLES_DIR; a read-only directory's entries cannot be
  unlinked, so clean_examples()' rmtree raised PermissionError at step [3] of
  every subsequent date — before any work — on one leftover folder
  ("1974-01-30 … (LB-03652)"). New _make_writable() restores the owner write
  bit across a tree; clean_examples() calls it before rmtree and copy_folders()
  strips the read-only mode right after each copytree, so a read-only source can
  no longer wedge the crawl.
Changed: data/tapematch/crawl_skip.txt: cleared six innocent dates (1974-01-31,
  02-02, 02-03, 02-04, 02-06, 02-09) that run_crawl.sh skip-listed only because
  each hit the shared PermissionError three times; they are back in the queue.
Added: tools/tapematch/tests/test_make_writable.py: regression tests — a 0o555
  tree blocks rmtree, _make_writable un-blocks it, missing paths are a no-op.

[2026-07-22] — feat: persisted Library view + instant relaunch (BUG-271)
Fixed: gui_next App.tsx: BUG-271 — first click on Library/Collection after a
  cold launch still took 12-15 s / 5 s (BUG-270's fix was warm-path only: cold
  954 MB DB page-ins + 3 bulk fetches staggered 3 s after launch + 22 MB JSON
  parse, worsened by library-crawl I/O contention). React-query cache for the
  four bulk keys (collection-prefetch, library-catalog/-performances/-badges)
  is now persisted to IndexedDB (PersistQueryClientProvider + idb-keyval,
  structured clone — no 60 MB JSON.stringify, 7-day maxAge, buster
  lbb-cache-v1); on relaunch the tables render instantly from last session's
  snapshot while a staggered background refetch (skips queries already fetched
  this session) reconciles. gcTime raised to maxAge so restored queries
  survive until re-persisted.
Added: gui_next App.tsx: last-route persistence — the app reopens on the
  screen it was closed on (localStorage lbb-last-route, RouteRestorer inside
  HashRouter; curator-gated routes still redirect via CuratorRoute).
Added: gui_next ScreenLibrary.tsx: useLibraryFilterStore now persisted
  (zustand persist → localStorage lbb-library-filters, Set-aware
  replacer/reviver) and extended with the remaining view state: lens,
  rec/perf groupByYear, collapsedYears, sort key/dir, detail-panel open,
  perf expandedShows/collapsedFams. Closing and reopening the app restores
  the exact filtered view (e.g. Year: 1999). Perf-lens auto-expand of the
  first show is skipped when a persisted expandedShows set was restored.
Changed: gui_next package.json: + @tanstack/react-query-persist-client
  (hoists react-query to 5.101.4 within ^5.80.5) and idb-keyval 6.3.0.
Changed: tools/debug_screens.json: tour now navigates to "/" first — app
  launch no longer lands on Home by default (route restore), so the first
  screenshot must pin its screen. Verified: /gui-check green; Tier B Electron
  two-phase persistence test (set Year:1999, quit, relaunch → Library
  restored, filtered, rendered ~4 s after process start) + full 20-screen
  tour PASS.

[2026-07-22] — fix: open-bug sweep — test temp-file containment (BUG-253/254), dead mirror URLs (BUG-255), lbdir unreconcilable entries (BUG-252), BUG-120 forensics
Fixed: backend/checksum_utils.py: BUG-252 — unreconcilable lbdir entries
  (self-referencing manifests, server-regenerated DigiFlawFinder reports; new
  _REGEN_REPORT_RE + _is_unreconcilable_entry) no longer count as missing or
  fail in verify_folder_lbdir (detail statuses stay visible) and are excluded
  from find_reconcilable_files / find_site_recoverable_files proposals.
  find_reconcilable_files also gained BUG-174's name-based fallback: on-disk
  near-duplicates (LBF-prefix-stripped basename match) surface as
  matched_by:'name' rename proposals with expected_md5.
Changed: gui_next LbdirDetail.tsx + lbdirStore.ts: rename-proposal rows render
  name matches with warn edge + "MD5 mismatch" pill (same treatment as site
  proposals); ReconcileProposal type gains optional expected_md5/matched_by.
Changed: BUGS: BUG-120 closed after full forensics — LB-06548 track 09 and
  LB-12181 d18-2 are non-FLAC corrupt files sharing an identical 420KB prefix
  (cross-linked clusters on DYLAN2 → TODO-264 disk check + re-source);
  LB-12181 d18-7 audio is bit-perfect (PCM md5 matches ffp), container-only
  change; LB-12181 lookup-not-found is expected (site has no checksums for it).
Fixed: conftest.py: BUG-253 — session-scoped autouse fixture routes
  tempfile.tempdir + TMPDIR into pytest's self-pruning basetemp; leaked
  lb_*_test_* dirs / tmp*.wav no longer accumulate in /tmp (verified: two full
  919-test runs, zero leaks; 1,545 stale dirs cleaned up). BUG-254 (flaky
  test_mixed_shn_and_wav_checksums_still_matched) closed as shared root cause —
  its single 2026-07-16 failure matches the ENOSPC casualties BUG-253 documents.
Fixed: backend/site_crawler.py: BUG-255 — entry_files.downloaded is now
  tri-state (0 missing / 1 mirrored / 2 dead): the 404 branch marks the
  matching row downloaded=2 so permanently-dead attachment URLs (stale seeds
  from regenerated pages + source-mangled hrefs, all confirmed not_found/404
  in site_inventory) stop being re-seeded. One-time backfill marked all 88
  residual rows dead — missing-attachments count converged 88 -> 0, with no
  content loss (every affected LB already has corrected-name siblings
  mirrored). Docstring (backend/db.py get_missing_attachment_urls), PROJECT.md
  entry_files schema note, tests in tests/test_scraper_crawler.py.

[2026-07-22] — fix: Collection/Library first-launch load time (BUG-270)
Fixed: backend/db.py: get_collection_duplicates N+1 — one query per duplicate
  group (3,220 full scans, entries had no date_str/location index) cost 3.5 s
  of the 4.1 s /api/collection/prefetch response. Rewritten as a single
  grouped-members query + new idx_entries_date_location. Output is identical
  except the redundant per-entry "owned" flag (unread by the GUI) is dropped.
  Warm endpoint: 4.1 s -> 0.80 s.
Added: backend/app.py: global after_request gzip for JSON responses >= 256 KB
  when the client advertises gzip (level 1, ~0.2 s CPU). Cuts the bulk
  endpoints ~4x on the wire (prefetch 35.8 MB -> 9.9 MB, /api/search
  22.5 MB -> 6.3 MB); Chromium fetch() decompresses transparently, streaming
  (direct_passthrough) responses are skipped.
Changed: gui_next/src/renderer/src/App.tsx: warm-prefetch library-catalog,
  library-performances, and library-badges 3 s after launch (staggered so
  JSON.parse doesn't fight Home's first paint) — first Library visit now hits
  a warm react-query cache, same keys/staleTime as ScreenLibrary.

[2026-07-22] — docs: user-facing docs pass — website restored + real screenshots (BUG-269)
Fixed: docs/index.html: BUG-269 — the GitHub Pages marketing site had been
  clobbered by a copy of the schema page in 7a9548c5 (2026-06-30); restored
  from a32a853d and refreshed for the current app (Electron/React copy,
  12-card feature grid incl. Library/Pipeline/Gaps/TapeMatch/Trading,
  installer-based install cards, first-run wizard notes).
Added: docs/screenshots/: 7 real app captures (home, quicklookup, library,
  search, map, gaps, pipeline) taken with the sanctioned Tier A screenshot
  engine against live data; wired into index.html hero + 5-item showcase.
  QuickLookup shot uses real LB-08287 ffp lines; map retaken with settle wait
  so tiles render. screenshots/README.md rewritten as inventory + refresh
  recipe (was placeholder guide).
Changed: README.md: website/wiki/schema links + hero screenshot added.
Changed: docs/wiki/: GUI.md Screenshots section; Collection-Pipeline.md,
  Setlist-Sources.md screenshot links; Home.md pointer to user-facing
  surfaces. PROJECT.md docs/screenshots/ description updated.

[2026-07-22] — docs: wiki build-out — 5 new pages, all 15 topic pages fresh
Added: docs/wiki/Setlist-Sources.md, Show-Dossier.md, Master-Data-Sync.md,
  Collection-Pipeline.md, Integrations.md — coverage for the setlist corpora,
  dossier, master-data distribution, filing pipeline, and outbound
  integrations subsystems (previously undocumented in the wiki).
Changed: docs/wiki/ — all 10 pre-existing topic pages regenerated from current
  sources (schema v11, export channels, derived-data recompute chain,
  staircase/frozen-set calibration state, /verify sanctioning, 20-screen GUI
  list, TODO-234 rescore counts); Home.md index updated. PROJECT.md file
  structure line for docs/wiki/ updated (8 → 15 topic pages).
Changed: .claude/CLAUDE.md: Context Discipline now directs sessions (and
  subagent prompts) to the matching docs/wiki/ page for subsystem orientation
  before grepping PROJECT.md — wires the wiki into the standard workflow.
Added: tools/wiki_staleness.py — compares each wiki page's `> Sources:` paths
  (globs supported) against git commits newer than its `Status:` date; wired
  into .claude/hooks/session_brief.sh as a `[wiki]` briefing line (+0.03s) and
  into /wiki-update step 1, so staleness is detected automatically instead of
  by hand-maintained status flags. Caught its first error on first run:
  Collection-Pipeline cited instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md,
  which had been retired to instructions/complete/ — header fixed, plus
  Integrations/Master-Data-Sync headers tightened to full repo paths.
Commits: d21b7f2b, 9198df7d, 33030811, c466fde5.

[2026-07-22] — refactor: single screenshot engine — browser_driver.mjs retired into electron_driver.mjs --renderer-only
Removed: tools/browser_driver.mjs — the older Tier A driver (tj's call: one
  engine, keep a fast flag).
Changed: tools/electron_driver.mjs: new --renderer-only mode absorbs Tier A —
  headless Chromium vs the Vite server (dev 5173 / --preview 4173,
  --no-server supported), window.api shim, PNGs → .debug/; Electron mode
  unchanged (PNGs → .debug/electron/). scale-matrix guarded Electron-only;
  main-eval fails cleanly per-step in renderer mode via driver_core caps.
  Build policy: Electron mode builds unless --no-build; renderer dev mode
  never builds; --preview builds unless --no-build.
Changed: tools/driver_core.mjs header, PROJECT.md tools section,
  .claude/skills/verify/SKILL.md (tier table + commands now
  --renderer-only), .claude/settings.json (dropped browser_driver allow
  rule).
Verified: renderer-only full 20-screen tour 47/47 ok; Electron-mode
  navigate+screenshot ok; scale-matrix correctly rejected under
  --renderer-only.

[2026-07-22] — fix: Home screen responsive layout + activity-table column alignment (BUG-265, BUG-266); screenshot engine sanctioned
Fixed: gui_next .../index.css + ScreenHome.tsx: bottom row (Recent activity |
  Tonight/Tips) moved from inline '1.45fr 1fr' grid to .lbb-home-grid-bottom —
  minmax(0, …) columns so content can shrink, stacking to one column below
  1400px. Previously the activity widget was invisible at 1280x768 (the app
  minimum) and a ~40px sliver at 1440x900, with the right column overflowing
  off-screen. Top row likewise → .lbb-home-grid-top. (BUG-265)
Fixed: gui_next .../ScreenHome.tsx: both activity tables (main + full-log
  modal) declared 5-col colgroups against 6-cell body rows (TR auto-injects
  the edge-bar td + manual type-dot TD) — every value rendered one column
  right of its header and WHEN timestamps truncated at all sizes. Added an
  18px dot col + empty TH, widened WHEN to 140px, realigned empty-state rows.
  (BUG-266)
Changed: .claude/CLAUDE.md, .claude/skills/verify/SKILL.md,
  .claude/commands/gui-check.md: screenshot engine (browser/electron drivers)
  sanctioned for use on Claude's own initiative for visual gui_next changes —
  tj cleared it 2026-07-22; /gui-check remains the required baseline.
Verified: electron_driver size-matrix at 1280/1440/1920/2560 + full-log modal
  session; tsc node/web + production build all pass.
Fixed: tools/debug_screens.json: /verify tour file was stale — still navigated
  pre-refactor routes (/lookup, /verify, /rename, /lbdir → blank screens) and
  missed 7 current screens; rewritten to the 20-screen registry from
  lib/navigation.ts. (BUG-268)
Fixed: gui_next locales en/de/fr/es/it/nl: gaps.grid.yearGap split into
  yearGap_one/yearGap_other so year rows with one gap no longer read
  "1 gaps". (BUG-267)
Verified: full Tier A /verify tour (20 screens) — all render, no blank
  screens, no raw i18n keys; scraper/fingerprint redirect Home as designed
  (curator mode off).
Changed: tools/driver_core.mjs: wait-for action now passes through a `state`
  option ('visible'|'attached'|'detached'|'hidden') so sessions can wait for
  loading placeholders to disappear, not just for elements to appear.
Changed: tools/debug_screens.json: settle waits added — text=Loading detached
  (20 s) on library/search/bootlegs/tapematch/songs/attachments/map, first
  date-cell button on gaps — so the tour captures loaded screens instead of
  transient "Loading…" states; a timed-out wait degrades to the old behavior
  (step fails ok:false, tour continues). Re-run: 47/47 steps ok, all
  previously mid-load screens now capture settled data.

[2026-07-21] — feat: command palette (Ctrl+K) — global fuzzy navigation (TODO-263)
Added: gui_next .../lib/navigation.ts — NAV_GROUPS + nav types extracted from
  AppShell.tsx so the sidebar and palette share one screen registry (curator
  gating applies to both); AppShell now imports it.
Added: gui_next .../lib/commandRegistry.ts — framework-free command registry
  (registerCommands/getCommands) as the palette's extension point for future
  specs (activity center, dossier, gaps); v1 built-ins = one nav command per
  screen + action.checkUpdate (GET /api/flat_file/discover, footer outcome).
Added: gui_next .../lib/fuzzyMatch.ts — standalone subsequence scorer (weights
  consecutive runs, word-start hits, match position).
Added: gui_next .../components/CommandPalette.tsx — Ctrl/Cmd+K overlay mounted
  once in AppShell. Ranked query interpretation: LB pattern → "Go to LB-N"
  (/library?lb=N), fuzzy commands, then debounced /api/search entries (≥2 chars,
  stale-response guard, silent degradation). Escape/arrows/Enter/click wired,
  scroll lock + focus restore. SSE-backed actions deferred to the activity
  center per spec D4.
Added: en.json + de/fr/es/it/nl — top-level `palette` locale namespace.
Docs: PROJECT.md (command-palette architecture bullet); instructions spec moved
  to complete/, FABLE_IDEAS UI §1 marked shipped, README index updated.

[2026-07-21] — feat: unified activity center — status-bar job tray (TODO-262)
Added: backend/activity.py — declarative JOB_ADAPTERS table (15 workers) +
  snapshot() normalizing every polled worker into one shape (spec §2 A1),
  50-entry in-memory finished-job history, and an SSE tee registry (track())
  giving the 6 text/event-stream routes presence while streaming. New route
  GET /api/activity/jobs. Implements instructions/FABLE_ACTIVITY_CENTER.md.
Changed: backend/app.py — /api/activity/busy re-based on the same adapter table
  (response byte-compatible), which also closes its blind spots: spectrogram,
  tapematch-crawl, pipeline-run, and archive.org jobs are now visible (spec D-3);
  extracted 5 module-level status getters (zero behavior change); wrapped all 6
  streamed generators in activity.track() (payloads byte-identical).
Added: gui_next lib/activityStore.ts — single ref-counted poller (adaptive 5s
  idle → 2s running) feeding a status-bar activity tray in AppShell.tsx (running
  jobs with progress + elapsed, Stop via cancel_route, click-through to owning
  screen, error badge; §3 defaults D-1/D-2/D-4). 17 new locale keys across
  de/fr/es/it/nl. Old inline activity/busy poller removed.
Tests: tests/test_activity.py (8) + tests/test_activity_sse.py (4). gui-check PASS.

[2026-07-21] — chore(docs): /session-close now commits + pushes automatically
Changed: .claude/commands/session-close.md — added Step 8 (commit + push without
  confirmation) so bookkeeping always lands on the remote at session end; split
  the old Step 7 into consistency-check (7) + report (9). No more per-step
  "want me to commit/push?" prompts.

[2026-07-21] — ci: skip full suite on pure-bookkeeping (**.md-only) pushes
Changed: .github/workflows/ci.yml — added paths-ignore: ['**.md'] to the push
  trigger. The bookkeeping discipline structurally produces .md-only commits
  (CHANGELOG/BUGS_DONE/TODO ledger moves) after every code commit; each was
  re-running the full backend-tests + backend-smoke + gui-check matrix that the
  preceding code commit already ran (5 of the last 8 runs were pure bookkeeping).
  paths-ignore skips a push only when EVERY changed file matches, so mixed
  code+docs commits still run; PR-to-main stays the unconditional gate.

[2026-07-21] — fix(db): writer thread owns its connection's close, not shutdown()'s caller (BUG-264)
Fixed: backend/db_queue.py — DatabaseWriteQueue.shutdown() closed self._conn from
  the caller thread after join(timeout). When a write outlived conftest's 2s join
  under CI's contended disk, the caller freed the connection out from under the
  still-running writer thread — a cross-thread SQLite use-after-free that
  segfaulted the backend-tests job at teardown (exit 139, flaky). The writer
  thread now closes its own connection when it drains the shutdown sentinel;
  shutdown() only signals + joins. Distinct from the BUG-261/262/263 init_db
  thread leaks. Added TestWriteQueueShutdown regression tests; full suite 905
  passed locally.
[2026-07-21] — feat(backend): CI on GitHub Actions + synthetic fixture DB generator (TODO-261)
Added: backend/paths.py — LOSSLESSBOB_APP_ROOT env override (unfrozen branch
  only) so CI/cloud agents/tests can point the whole backend at a throwaway
  data dir without touching real data/.
Added: tools/make_fixture_db.py — deterministic synthetic install generator
  (~101 entries/29 dates): multi-source dates, a two-show date, an xx-date,
  a private entry + lb_master row, an xref fileset group, 2 tapematch
  families, lineage-bearing descriptions, a curated list, olof song/event
  rarity shapes, bobdylan/setlistfm cross-refs, entry_files, my_collection
  rows. Runs the real derived recompute chain in-process; fixture tapers
  registered via the existing user_taper_aliases mechanism (TODO-241) so
  Layer 0 taper attribution produces real rows without fake names in the
  real known-taper list.
Added: tools/ci_smoke.py — builds the fixture, boots the real backend
  against it, curls the 4 cheap boot-smoke routes with a sanity check each.
Added: .github/workflows/ci.yml — backend-tests (compileall + full pytest
  suite), backend-smoke (ci_smoke.py), gui-check (typecheck+build) on every
  push (all branches) + PRs to main. tapematch-tests dropped per tj: its
  suite shells out to live tapematch_session.py/.venv-nmfp subprocesses,
  unsafe against a live crawl and not meaningful without real audio
  fixtures in CI. release.yml unchanged. Verified green on real GitHub
  Actions HEAD (kuddukan42/losslessbob run 29869608572).
Fixed: backend/db.py (BUG-261) — checksum bloom filter could race init_db()'s
  own caller: a background rebuild thread could snapshot the checksums table
  before the caller's own inserts landed (same db_path, so BUG-187's cross-DB
  guard didn't catch it), silently reporting freshly-inserted checksums as
  NOT FOUND for the rest of the session. rebuild_bloom() now stamps the row
  count it was built from; a live-count mismatch skips the bloom for that
  call and kicks off a fresh rebuild.
Fixed: backend/db.py (BUG-262) — migrate_lb_master()'s init_db()-spawned
  background thread could block up to 30s against a write queue a fast test
  suite was already tearing down. Added a wait=False fire-and-forget path
  for that one caller; synchronous callers (importer.py, flat_file.py)
  unaffected.
Fixed: backend/db.py (BUG-263) — the real segfault cause: init_db()'s four
  background threads each open a sqlite3 connection that was never
  explicitly closed (left for GC), leaking 3 FDs (WAL mode) per thread under
  fast test churn until GitHub Actions' runner ran out and crashed the
  interpreter outright. Each background task now explicitly closes its
  connection when done.
Changed: .claude/CLAUDE.md, PROJECT.md, README.md — CI citation rule, new
  files in the file-structure tree, Actions status badge.
[2026-07-21] — feat(gui): Collection "Misrouted" filter — surface folders in nonstandard mount locations (TODO-166)
Added: backend/db.py — _route_status() classifies each my_collection folder's
  disk_path against its show-year's configured routing: compares the mount the
  path actually sits under (_mount_label_for_path, longest-prefix match) with the
  mount collection_routes says that year should route to. Returns route_status
  (ok / wrong_mount / no_mount / no_route / no_date) + actual/expected mount
  labels + year on every get_collection() row. Pure string matching, no disk I/O.
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx — a conditional
  "Misrouted" filter chip (shown only when drift exists) surfacing wrong_mount +
  no_mount rows, a ⚠ marker in the Disk Path cell with an expected-vs-actual
  tooltip, and RouteStatus typing on CollectionRow. Chip label is hardcoded
  English, consistent with the sibling filter chips (no new i18n keys).
Closed: TODO-249 (Improve xref handling) — superseded/already-covered, per tj.
[2026-07-21] — feat(backend): pipeline step labels return i18n key+params, not rendered English (TODO-195)
Changed: backend/app.py — _pipeline_process_folder now emits label_key (stable
  snake_case enum) + label_params (dynamic values) on every pipeline step dict
  (verify/lookup/lbdir/rename/file), alongside the existing English `label` field
  which is retained as a fallback. Added _file_blocked_label_key() helper. Additive
  and backward-compatible — no field removed.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx — added PIPELINE_LABEL
  (label_key → i18n key) map + stepLabelText() helper mirroring the STATE_LABEL/
  ERROR_MSG convention; all 5 raw {step.label} render sites and the deriveFolderStatus
  reason sites now translate via t(key, params) with raw-label fallback; the 4
  frontend-synthesized labels (Renamed/Filed/2×Failed) set label_key/label_params;
  the 'Renamed' text guard now checks label_key === 'renamed'. Locale-invariant data
  labels (matched LB-numbers, arbitrary error strings) deliberately keep label_key null.
Added: gui_next/src/renderer/src/locales/en.json — pipeline.stepLabels.* (29 keys).
  Other locales (de/fr/es/it/nl) fall back to English until a follow-up /gui-next-i18n pass.
[2026-07-21] — fix(scraper): hiss_median floor on the staircase corroboration gate (TODO-255)
Fixed: tools/tapematch/tapematch/verdict.py — _staircase_corroborated: the hiss
  corroboration branch required hiss_frac >= 0.05 with no median requirement, so
  noise-level hiss (hiss_median ~0.05) corroborated a staircase-relaxed fp merge
  (1995-12-09 LB-06083/06104: hiss_frac 0.0504, hiss_median 0.0496, corr ~0). Added
  an optional min_hiss_median floor: when set, the hiss branch also requires the
  median at/above the floor; None median with the floor set does not corroborate.
  Absent key = historical frac-only behaviour (byte-identical).
Changed: tools/tapematch/config.yaml — fingerprint.staircase_corroboration.min_hiss_median: 0.05
  (symmetric to min_hiss_frac; tj sign-off 2026-07-21). Cached frozen-set sweep
  (827 dates / 2,965 labeled pairs): −2 fp, 0 tp cost — strict precision gain, blocks
  the boundary case. Floors >=0.08 sever a real same-cluster edge (min real hiss
  median ~0.085). Evidence table in CALIBRATION_PROGRESS.md.
Added: tools/tapematch/tests/test_staircase_gating.py — 4 tests for the median floor
  (blocks noise, passes real hiss, None median blocks, windowed branch unaffected).

[2026-07-21] — feat(gui): collection-view right-click to reassign a folder's LB or rename it (TODO-259)
Added: backend/db.py — reassign_collection(old_lb, new_lb): atomically moves a
  my_collection row (folder_name/disk_path/notes/xref) to a different LB and carries
  its collection_meta (personal rating/tags/listen count) across so nothing is lost.
  Guards: target must exist in entries, must not already be owned, and can't equal the
  source — all raise ValueError. The folder on disk is untouched (that's what rename is
  for). Scope note: TODO-259's other two needs were already shipped — folder rename via
  /api/folder/rename and the pre-filing LB# override via the pipeline OverridePanel
  (BUG-257) — so this session only added the missing collection-view reassign lever.
Added: backend/app.py — POST /api/collection/reassign {old_lb, new_lb}; validation
  failures surface as 400.
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx — two new row
  context-menu entries, "Reassign LB…" and "Rename Folder…" (both disabled on unfiled
  rows), backed by a shared FolderEditModal. Rename reuses the existing
  /api/folder/rename (qBittorrent-sync aware); reassign hits the new endpoint and
  refetches the collection on success.
Changed: gui_next/.../locales/{en,de,fr,es,it,nl}.json — new collection.folderEdit.*
  strings (DeepL-synced; folderEdit fully covered in all five locales).
Added: tests/test_db_writes.py — TestReassignCollection (5 tests: move, meta migration,
  target-missing, already-owned, same-LB). Full suite green; backend restarted and the
  route live-verified (400s on bad/unknown input).

[2026-07-20] — chore(scraper): corpus rescore batch drained (561/561) — corroboration gate validated, staircase lag curves persisted (TODO-254, TODO-235)
Changed: tools/tapematch/CALIBRATION_PROGRESS.md — the 561-date targeted rescore
  (rescore_queue_20260717.txt, launched 07-17) completed 07-20T07:45. Ran the
  completion runbook: tapematch_sync (2,032 dates / 6,112 families / 0 errors) +
  taper_attribution.recompute() (8,159 total; 130 conflict — expected, families held
  on real evidence, not chased to 0). lag_segments_json now populated for 2,272 sources
  (was 0) → unblocks TODO-233 pt2 staircase A/B. Corroboration gate validated across all
  205 flip-sig dates: 749 staircase pairs in the relaxed fp band [0.40,0.50), 515
  uncorroborated correctly split to different_family (gate fired), no bare fp-only leaks
  (11 residual same_family all carry non-fp evidence). Completion record appended to the
  state file. TODO-234 dispositions + TODO-255 gate-floor sweep remain open (tj decisions).
Changed: instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — refreshed the conflict evidence
  table against the post-drain data (series-vs-series subset 18 → 14; 1990-11-08 / 1990-08-12
  / 1995-05-26 cleared). Fresh evidence flips most dispositions from hand-split to flip-to-
  label-review (families held on windowed/hiss/emb, not bare fp): 5 flips, 1 hand-split
  (1995-12-09, a TODO-255 gate-floor artifact), 1 ambiguous (1997-04-05), 1 edge-fix
  (1988-07-17). Recorded only — no DB changes; the 14 rows stay in the queue by design
  pending tj's per-family taper picks.

[2026-07-19] — fix(backend): keep the extras/ set-aside subtree out of checksum generate + verify (BUG-259, BUG-260)
Fixed: backend/checksum_utils.py — final-pass review of the in-flight BUG-257 work
  found two holes in the same extras/ contract the lookup fix established:
  (1) BUG-259: generate_checksums()'s new multi-disc recursion (rglob) also hashed
  audio under extras/ into a fresh top-level _mychecksums sidecar. Lookup only skips
  sidecars *under* extras/, so one press of "Generate FFP + MD5" on a reconciled
  folder fed the superseded fileset's hashes straight back into lookup — recreating
  the false multi-LB match BUG-257 had just fixed. Audio rglob now filters
  _is_reconciled_extra(); disc subfolders (CD1/…) still covered.
  (2) BUG-260: verify_folder() still parsed sidecars under extras/ (and counted
  extras audio), so a folder in the BUG-257 shape (extras/ holds only the alternate
  transfer's sidecar) wedged Step-1 Verify on 'incomplete' with phantom missing
  files. Both verify scans now skip the extras/ subtree, matching lookup and
  verify_folder_lbdir semantics.
  Both bugs repro'd before fixing; regression tests added
  (tests/test_checksum_extras.py, 4 tests); full suite green (880 + 11 dossier);
  backend restarted and freshness-verified.

[2026-07-19] — feat(backend): Show Dossier polish pass — app-blue dark theme, family grouping, attribution + working deep links
Changed: backend/templates/dossier.html — retheme from the sepia palette to the app's
  own look (gui_next tokens.ts "blue" frame + "indigo" accent; dark is now the default,
  light kept as toggle/print). Reordered sections: recommendation hero + circulating
  sources now sit above the setlist. Tape families are visually grouped (reel-icon header
  row per family with member count, confidence meter bar, review flag, and an accent
  spine down member rows) and buckets/members are ordered by pick rank. AI index grades
  render as colored grade seals (A=green/B=blue/C=amber/D=red, score /100 inline) in the
  sources table, glance strip, and recommendation hero. Tables centered + hover states,
  centered masthead with accent double rule. Per-section attribution credit lines
  (Olof Björner "Still on the Road" for context/setlist, setlist.fm for coordinates,
  LosslessBob for the catalog) and a full footer credits paragraph.
Added: backend/dossier.py — _build_xref(): the cross-reference cards are now built
  server-side with working deep links per show: LB detail page (paths.detail_url on the
  recommended/first source), the exact Olof page the show was ingested from (bobserve
  mirror, page_filename URL-quoted), Boblinks per-date setlist page (MMDDYYs.html,
  1995+ only; site home otherwise — pages are best-effort on their end), and the
  Bobserve year index (eventsperiod?period=YYYY). Each sources-table LB number also
  links to its LosslessBob detail page (member.url). Additive to the D1 JSON shape
  (dossier.xref); render_bbcode untouched. All link patterns verified live (HTTP 200),
  11 dossier tests green, template renders verified for 1966/1987/2002 dates.
  Mobile follow-up: the 7-column sources table now scrolls inside its own
  .tbl-scroll container (min-width 640px) instead of forcing page-level horizontal
  scroll; tightened <=720px padding/typography; overflow-wrap on xref URLs.

[2026-07-18] — fix(importer): private-metadata fill skipped bracketed folders + misread LB-<num>.txt sidecars (BUG-258)
Fixed: tools/import_private_metadata.py — the private-metadata fill appeared to
  stop before completing. Three defects, all in the folder pass:
  (1) info_txt_candidates() called glob.glob() on the raw folder path, and
  private folders carry [LB-NNNNN]/[taper] brackets that glob reads as character
  classes — so 43 folders whose .txt files were right there on disk were
  silently reported as no_info_txt. Fixed with glob.escape(folder).
  (2) _LINEAGE_LINE only matched space-padded ' -> '/' > ', missing unicode
  arrow (→), bare -> and no-space chains like cd>EAC>TLH>flac. Broadened to
  match →, -> and word>word.
  (3) extract_setlist() only read one-track-per-line, so the canonical
  LB-<num>.txt sidecars' inline comma-run setlists ('1 intro, 2 Roving Gambler…')
  never parsed — they wrap across physical lines mid-title, use 1-/1./101
  separators, and run the 'Please retain…' footer onto the last track. Added a
  block-based _setlist_from_inline(): de-wraps -----fenced blocks, splits only on
  ', <n>' boundaries (commas inside titles like "It's Alright, Ma" survive),
  reuses the existing 1,2,3…/disc-restart chain validator, and _clean_title()
  strips inline disc labels (', cd-2, November 16th…') and footer boilerplate.
  Applied to the live DB: setlists 1210 → 1309 (+99), descriptions 1356 → 1362,
  no_info_txt 54 → 11. Remaining gaps (63 setlist-less) are genuinely
  source-less — no sidecar, or metadata-only tab formats with no tracklist.

[2026-07-18] — feat(backend): Show Dossier high-fidelity redesign — sepia template + pre-rendered locator map (TODO-260)
Changed: backend/templates/dossier.html — full rebuild to the design-handoff sepia
  light/dark token system: fixed theme toggle (localStorage-persisted, print-hidden),
  masthead with LB mark, at-a-glance strip, table setlist with encore separator + rare
  badges, sources comparison table (pick-rank ordered, is-rec highlight, taper pill +
  source chain retained), recommended callout with signed scoring ledger, cross-reference
  grid, and print CSS that forces the light palette. All source flattening and glance/xref
  derivation happen in-template — the JSON API and render_bbcode are untouched.
Added: backend/dossier.py — _load_quality surfaces abs_score (numeric AI grade nn/100);
  _build_show adds lat/lng/country/city_line + _COUNTRY_MAP_META (world-atlas country name
  + Mercator scale, US/UK aliasing) sourced from setlistfm_shows-by-date; _render_locator_svg()
  pre-renders the country locator to self-contained inline SVG (replicates
  d3.geoMercator center/scale/translate, polar clamp, viewport clipping) so the downloadable
  dossier needs no CDN/JS/network and prints reliably offline (~28KB doc vs ~390KB if d3 were
  inlined).
Added: backend/assets/world_countries_110m.json — bundled 168KB GeoJSON (177 countries,
  Natural Earth names), decoded once from world-atlas@2.0.2 countries-110m.json; loaded and
  cached at render time. No new pip dependency (stdlib math/os/functools/json only).
Fixed: backend/templates/dossier.html — two Jinja Undefined hazards found during the redesign:
  the fam_conf guard crashed on a family with a label but no confidence (now bucket.get() so a
  missing key is real None), and the locator card was nested under d.context so a show with
  coordinates but no chronicle silently lost its map (now gated on coordinates independently).

[2026-07-18] — fix(backend)+feat(gui): lookup ignores extras/ sidecars; pipeline LB# override (BUG-257)
Fixed: backend/app.py — the pipeline Lookup stage gathered checksum sidecars with
  folder.rglob('*') and read every .ffp/.md5/.st5, INCLUDING those under extras/
  (the move_extras set-aside dir). When extras/ held a different transfer's
  sidecars, the merged input covered two distinct filesets, so lookup_checksums
  reported BOTH LBs as MATCHED and the _all_perfect guard auto-linked + renamed
  the folder "(LB-A+LB-B)" as if identical. Seen on 1975-07-03 The Other End,
  N.Y.: LB-12226 vs LB-16533 share Set I (tracks 01-11) but differ on Set II
  (12-19) — genuinely two transfers, falsely merged. Fix: skip paths matched by
  checksum_utils._is_reconciled_extra() (extras/ subtree + rename_log.txt) when
  building the lookup input. Verified on the live folder: LB-16533 drops
  MATCHED -> DUPLICATE, so the false multi-LB auto-link no longer fires.
Fixed (2): backend/app.py — an explicit folder pin was ignored by the LBDIR
  resolvers. _resolve_lb_number_for_folder + the three inline resolvers in
  /api/lbdir/check, /api/lbdir/retrieve and /api/lbdir/reconcile all resolved
  LB# as my_collection.disk_path -> folder-name regex -> hint/pin, with the pin
  DEAD LAST. So after a user overrode a folder to LB-16533, the LBDIR screen
  still verified against LB-12226 (this folder's stale my_collection row + its
  "(LB-12226+LB-16533)" name both point at 12226). New helper
  _pinned_lb_for_folder() makes a *single* explicit folder_lb_link authoritative
  ahead of the heuristics (multiple links stay ambiguous -> heuristics apply).
  Verified: /api/lbdir/check now returns 16533 and verifies the GOODY-FIXES
  manifest (23/23 pass) even when the GUI passes lb_number_hint=12226.
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx — OverridePanel, an
  "Override LB#" control on the Lookup stage (matched branch). Surfaces one button
  per matched candidate LB plus a manual LB# entry; each force-pins a single LB via
  the existing PUT /api/folder_link (replace_folder_link), which supersedes any
  auto-written multi-LB links and re-runs LBDIR/verify against that entry. Lets a
  user correct a wrong/merged auto-match (e.g. this folder -> pin LB-16533). i18n:
  new pipeline.lookup.override* keys (5) in en.json (de/fr/es/it/nl sync pending).
  node+renderer typecheck and production build PASS.
Note: 5 collection folders carry a "+LB-" merged name and 33 folders were
  auto-linked "multi-LB perfect match" pre-fix — worth an audit; the override
  control repairs them one at a time.

[2026-07-18] — fix(backend): pipeline lookup no longer wedges duplicate-fileset folders (BUG-256)
Fixed: backend/app.py — the pipeline Lookup stage's "complete match" guard used
  full_match = summary["matched"] == summary["given"], but summary["matched"] is
  the GLOBAL match count and double-counts checksums archived under >1 LB entry
  (matched == given*N). A show whose identical fileset lives under a duplicate LB
  (e.g. LB-16353 alias -> LB-16369 canonical) therefore stayed in "Incomplete
  match" forever — and pinning either LB couldn't clear it, since the guard read
  the inflated global count rather than the pinned LB's own totals. Now tested on
  distinct unmatched checksums instead: full_match = summary.get("unmatched", 1)
  == 0. Duplicate-fileset folder resolves ok to the canonical LB (with or without
  a pin); a genuine NOT-FOUND file still blocks. Verified against the live DB.

[2026-07-18] — feat(gui): Known Tapers curation widget on DB Editor (TODO-258)
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx — new "Known Tapers"
  collapsible sidebar SideSection (losslessbob DB only, collapsed by default since
  the builtin alias list is long). TaperPanel component: filterable/scrollable table
  of the merged known-taper aliases with builtin/user origin tags (GET /api/tapers/
  aliases), curator-gated inline add (alias -> canonical, POST) and remove-selected
  (DELETE, with builtin-suppression), and a "Recompute derived data" button that
  streams the chained POST /api/derived/recompute SSE (lineage -> attribution ->
  picks -> song index) with per-step status dots. Local readSSE helper mirrors
  OnboardingWizard's. Backend routes/curator gating all pre-existed (TODO-241) — this
  is GUI-only. i18n: new dbeditor.tapers.* block (27 keys) in en.json, synced to
  de/fr/es/it/nl via DeepL (same run also filled pre-existing locale gaps from
  earlier features). node+renderer typecheck and production build PASS.
Changed: PROJECT.md — ScreenDbEditor GUI-screens row now lists the Known Tapers panel.

[2026-07-17] — feat(gui,backend): Show dossier / liner-notes export ships (TODO-257)
Context: instructions/FABLE_SHOW_DOSSIER.md (FABLE_IDEAS §5, HIGH PRIORITY per tj
  2026-07-13) written and shipped same day, bites B1/B2/B3/B5 (B4 = this entry). One
  command renders everything the app knows about a date: rarity-flagged setlist,
  sources grouped by TapeMatch family with taper credit/pick ranking/quality verdicts,
  historical context, provenance footer. Verified against real data (1987-07-04
  Dylan & The Dead show) — 17 source buckets, correct pick evidence and a correct
  "live debut" rarity flag matching the olof_events notes text.
Added: backend/dossier.py — build_dossier() assembly (feature-detected end to end;
  fresh install degrades to a smaller valid dossier, never errors) + filter_dossier_
  sections()/render_bbcode() presentation layer. Three routes in backend/app.py:
  GET /api/dossier (JSON), /api/dossier/html (self-contained print-first Jinja render,
  backend/templates/dossier.html — first template in the repo), /api/dossier/bbcode
  (forum digest, shares the HTML route's filtered view so they can't drift).
  channel='public' (default) reduces any private entries.status source to
  {lb, private: true} only; channel='full' keeps everything; disk paths/collection/
  friend data are never touched. gui_next: Library performance-lens row action +
  DetailPanel ActionBar "Export dossier..." (components/library/actions.tsx registry),
  new DossierExportModal.tsx (channel/section/format options, remembered via
  useSettingsStore), Electron main-process dossier:printPdf IPC (hidden BrowserWindow
  + webContents.printToPDF, HTML-download fallback outside Electron). i18n in all 6
  locales. tests/test_dossier.py (11 tests).
Fixed: backend/dossier.py — ambiguous-date detection was originally keyed off
  entries.location (free text scraped per-recording, e.g. 9 different spellings of
  the 1987-07-04 Sullivan Stadium show), which false-positived on nearly every
  well-documented date; redesigned to key off the clean olof_events.venue field
  instead, matching get_performances()'s existing trust in that source. Caught during
  B1 verification against the real production DB, not by the unit tests.

[2026-07-17] — feat(gui,backend): Gaps view — "the living Kokay list" ships (TODO-256)
Context: instructions/complete/FABLE_GAPS_VIEW.md (written 2026-07-17, PLATFORM_ROADMAP
  §3) built and shipped same day, bites B1-B4. Read-only end to end: every olof_events
  concert date classified covered/partial/gap/future against entries coverage, computed
  live with no derived table.
Added: backend/gap_analysis.py — classify_date() pure classifier + get_summary/
  get_year_detail/get_date_detail; three GET routes (/api/gaps/summary, /api/gaps/year/
  <year>, /api/gaps/date/<iso>) in backend/app.py, all feature-detecting olof_events.
  gui_next/src/renderer/src/screens/ScreenGaps.tsx — new /gaps screen (Library nav group):
  decade-chip strip, year rows of coverage cells, right-hand tab-group detail pane with
  LB deep-links into Library. tests/test_gap_analysis.py (16 tests).
Changed: backend/geocoder.py — _entry_date_to_iso promoted to public entry_date_to_iso
  (alias kept) + new entry_date_month_key() for xx-partial date matching.

[2026-07-17] — feat(scraper): tapematch staircase corroboration gate live + lag-segment
  persistence (TODO-234 sweep signed off, TODO-235 engine half)
Context: two-part tapematch package (work done 2026-07-16, signed off + landed 2026-07-17).
  Part 1: the 2026-07-11 staircase over-merge hazard (1997-11-11 LB-01126, fp .410/win 0/
  hiss 0 crossing the relaxed 0.40 bar) — mitigations (a)/(b)/(c) measured against the
  frozen set + TODO-234 family replay; tj signed off (a): corroboration gate. Part 2:
  TODO-235 prerequisite — per-segment staircase lag curves were render-only (analysis.md
  text), now persisted numerically for backend ab_clips piecewise maps (TODO-233 pt2).
Added: tapematch/align.py: fit_lag_segments() — piecewise-linear lag model per splice
  segment (offset_sec/rate_ppm/r2, same step detection as locate_splice_points);
  tapematch/verdict.py: fingerprint.staircase_scope (source|pair) + staircase_corroboration
  gate (absent-key = historical behaviour, verified byte-identical tp=684 fp=9);
  tests/test_lag_segments.py + tests/test_staircase_gating.py (17 tests).
Changed: tapematch/cli.py: results.json sources rows now carry lag_ref/lag_segments/
  lag_curve (raw anchor rows kept for re-derivation); tapematch_session.py: observations.db
  sources + lag_ref_lb/lag_segments_json columns (idempotent ALTER); config.yaml:
  fingerprint.staircase_corroboration ENABLED (min_windowed_frac/min_hiss_frac 0.05) —
  new committed frozen baseline tp=671 fp=9 (was 684/9; −13 tp are all fp-only
  zero-corroboration pairs, 0 new FP — verified via regression.py score --cached);
  CALIBRATION_PROGRESS.md: sweep table + decision recorded.
Added: instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — evidence review of all 11
  conflict components; action A (3 curator rejects) applied, queue 22 → 18; actions B
  (same_as edge fixes) + C (lineage parser tie-break bug) ON HOLD pending tj; post-rescore
  validation checklist. TODO-234/235 stay Open: corpus rescore + validation remain.
Session 2 (same day) — CORPUS RESCORE LAUNCHED + priority-date validation:
Added: tools/tapematch/rescore_queue_20260717.txt — targeted 561-date rescore queue
  (8 priority + 200 flip-signature + 353 stale pre-fp-column staircase dates; scope
  rationale in CALIBRATION_PROGRESS.md); batch running detached (setsid), ETA ~07-20,
  resumable via # done markers.
Changed: tools/tapematch/CALIBRATION_PROGRESS.md — rescore launch note, priority-date
  results, and a RESCORE COMPLETION RUNBOOK at the file tail (session briefing surfaces
  it) for the next session to finish sync/recompute/spot-checks/bookkeeping;
  instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — post-rescore validation DONE on live
  re-runs: corroboration gate validated in the wild (1997-11-11 LB-01126 isolated), but
  most expected splits did NOT happen (live evidence: windowed .95 on 1996-07-07, hiss
  .62/.727 on 1993-02-07, plain-bar fp .50+ bridges) — dispositions await tj. Boundary
  artifact logged: 1995-12-09 6083–6104 passed the gate at exactly hiss_frac 0.05.
  Mid-batch tapematch_sync (2,032 dates / 5,811 families / 0 errors) +
  taper_attribution.recompute() run; both must re-run after the queue drains.

[2026-07-16] — refactor(gui): Advanced-tools screens removed; Pipeline absorbed the gaps
Context: tj found the Advanced sidebar section (Verify/Lookup/Rename/LBDIR standalone
  screens) confusing next to the Pipeline, which already runs the same steps per-row via
  the shared stores/detail components. Decision: delete the four screens, port only the
  genuine capability losses into Pipeline, repoint entry points. Net −3,085 lines.
Changed: gui_next screens/ScreenVerify|ScreenLookup|ScreenRename|ScreenLBDIR.tsx deleted;
  App.tsx routes + AppShell.tsx Advanced-tools nav block removed. Entry-point repoints:
  Library "reconfirm" + Collection "Send to →" → Pipeline queue; Collection missing-LB
  dblclick + "LosslessBob" button → Quick Lookup with router-state seed (auto-runs once).
  lookupStore/verifyStore/lbdirStore stripped to shared types (zustand stores dead).
  Locales: 133 dead keys removed, 11 added (en+de/fr/es/it/nl — hand-translated, not DeepL).
Added: ScreenPipeline.tsx — lbdir stage Re-scan button (re-runs POST /api/lbdir/check
  anytime, replaces the "Full screen" link into the deleted screen); rename stage
  multi-LB disambiguation panel ported from ScreenRename ("Choose LB" → /api/folder_link
  + /api/lb_alias/resolve, Pin re-runs lookup+rename, Standardize feeds the proposal via
  overrideProposed, Unpin/Skip). ScreenQuickLookup.tsx seed handling.
Dropped (deliberate, not ported): bulk verify-all (/api/verify), lookup extra sources
  (clipboard/listbox/file), CSV export, wishlist-from-lookup, shallow-scan toggle,
  rename plan export — backend endpoints left in place. Verified: typecheck + prod build
  clean; every t() key cross-checked against all 6 locales (zero dangling).

[2026-07-16] — feat(db): private LB metadata import — TODO-245 shipped (docs + folder txts)
Context: tj supplied data/private/lb_summary_all_private.html (Jeff's cp1252 summary sheet,
  2,213 LBs: date/loc/lineage/notes/rating) and 'No Torrent -LB number overview.xlsx'
  (2,355 LBs: title/xref/date/taper), plus 1,372 private collection folders with info txts.
  tj rules: the docs are OLD snapshots (1,035 of their numbers are public today) — fill blank
  fields only, never overwrite scraped metadata; private LBs flagged 'private', not 'missing'.
Added: tools/import_private_metadata.py — document pass + --folders pass. Targets only
  CURRENT lb_master lb_status='private'; per-field blank-only fill. Field mapping verified
  against 1,032 now-public LBs present in both the HTML and scraped entries (Date→date_str,
  loc→location, qual→description, rat→rating). Jeff's private comparison-notes column
  appended inside description under a '-- private notes --' marker (1,240 rows). Folder pass
  extracts setlists from numbered track lines validated as a sequential 1,2,3… chain (disc
  restarts allowed; prose starting with a number is dropped) + lineage lines for doc-less rows.
Changed: backend/db.py — entries.metadata_source column (NULL=scraped, 'private_import'=from
  private material; idempotent ALTER). MASTER_SCHEMA_VERSION 10→11 (entries is a MASTER table;
  snapshots carry the new column). backend/scraper.py — live scrapes re-check status='private'
  rows like 'missing'; a successful scrape's INSERT OR REPLACE supersedes the private import
  (status→'ok', metadata_source→NULL), so publication always wins.
Data: 1,405 entries.status missing→private; 1,361 rows metadata-filled (date 1,361,
  location 1,243, description 1,243+117 folder-lineage, rating 1,158, taper 1,121,
  source_chain 904, lb_category 1,357); 1,210 setlists (was 1). Checksums deliberately not
  imported — already covered 1,403/1,405 (that coverage is what derived 'private' status).
Verified: 0 public rows carry metadata_source='private_import'; spot-checks (LB-14614 public
  untouched; LB-2606 Supper Club filled incl. setlist); FTS trigger-synced; importer dry-run
  == apply counts. Residual: 36 private LBs fully blank, 54 folders without info txt.
Privacy: data/ is git-ignored (docs can't reach the public repo); schema.html carries no row
  data. Master-export channel decision split to TODO-253 (snapshots now carry private rows —
  friends-only OK, public publication would need export-time stripping).
Closed: TODO-245. Opened: TODO-253.
Follow-up same session (tj: "does that publish to github from our app?" → "do it") — TODO-253
  escalated and shipped: /api/master/github_release uploads snapshots to the PUBLIC repo
  kuddukan42/losslessbob (channel active, master-2026-07-14), so the next release would have
  leaked the imported private metadata. No leak occurred — existing releases predate the import.
Changed: db.py export_master_db(include_private=False) — public channel (default) blanks all
  private-entry metadata (status='private' OR metadata_source='private_import'): fields
  emptied, entries_fts rebuilt, number-level status='private' kept (same info as lb_master);
  checksums retained deliberately (clients derive 'private' from them; pre-existing exposure).
  New verify step 7c: RuntimeError if a public snapshot still carries private metadata.
  Manifest gains channel ('public'/'full') + private_rows_stripped.
Changed: app.py /api/master/export accepts {channel: 'public'(default)|'full'};
  /api/master/github_release refuses (400 private_data) any manifest whose channel is not
  'public' — including legacy manifests without the field. GUI flow unchanged → safe by default;
  friends-only full export via API channel='full' (never uploadable).
Verified: tests/test_master_data.py 14/14 (new test_export_strips_private_metadata_on_public_channel);
  live API export on real DB: channel=public, private_rows_stripped=1405, snapshot has 0 private
  metadata rows, 0 FTS hits for the notes marker, public rows byte-identical; guard returns 400
  for full-channel and legacy manifests; artifacts cleaned up.
Closed: TODO-253.

[2026-07-16] — feat(gui): propagated-taper outline pills in Library (TODO-242 decision)
Context: tj decision — propagated attributions get a pill too, visually distinct
  ("outline or fuzzy"). Outline uses Pill's existing non-soft mode (transparent bg, toned
  border) — zero component changes. Conflict rows stay pill-less (review filter only).
Changed: db.py _load_taper_attributions now carries the taper name for conflict-free
  confidence='propagated' rows ("propagated" key); get_pick_badges + get_performances emit it
  as taperPropagated (docstrings updated).
Changed: ScreenLibrary.tsx — taperPropagated in RecordingRow + both merge paths; all three
  pill sites (recording lens row, perf single-recording, family member row) render an outline
  info Pill with a "propagated from linked recording" tooltip when no confirmed attr exists.
  Solid-confirmed > outline-propagated > mute free-text pill precedence unchanged otherwise.
Added: en.json library.picks.taperPropagatedTitle + DeepL sync de/fr/es/it/nl (4,492 chars;
  residual gaps are the benign SKIP_KEYS/identical-in-target class).
Verified: taper_attribution 26 tests green; gui-check PASS (node+renderer types, build);
  live /api/library/badges: 2,657 taperConfirmed + 4,023 taperPropagated (4,045 review minus
  22 conflicts); tj's original pair resolves — LB-10678 solid 'ltf', LB-14922 outline 'ltf'.
Follow-up same day (tj: "do the backfill and legend too") — Q2 leftovers shipped:
Fixed: tapematch_sync.py _parse_verdict only extracted reasons from the canonical
  "needs review — <reason>" form; the corpus also has "needs review: <reason>" and
  "needs review (<reason>)" variants whose reasons were silently dropped (the actual root
  cause of the 17 NULL review_reason rows). Parser now accepts all three delimiters;
  3 new tests (43 green). Note: sync reads analysis.md from archive_dir (<run_id>_<date>);
  bare <run_id> dirs under data/tapematch/runs/ are stray empties.
Changed: one-off backfill of the 17 flagged NULL-reason tapematch_family_meta rows (5 runs) —
  4 runs re-parsed with the fixed parser; run 20260615_154028's verdict is bare "needs review"
  so its reason was hand-derived from the analysis body (LB-12192-vs-4378 commentary
  contradiction, LB-06940 inflated ingest, LB-01489 not on disk). 0 NULL-reason flagged rows
  remain; reasons verified live in /api/tapematch/families.
Added: ScreenLibrary LegendMenu — "Legend" popover (FilterMenu pattern, both lenses' toolbars)
  with live Pill samples: ★ recommended, solid/outline/mute taper pills, Needs review, family
  best, curated pick. en.json library.legend.* + DeepL sync (6,210 chars).
Verified: gui-check PASS (node+renderer types, build).

[2026-07-16] — feat(backend): taper alias curation conduit — add/remove known-taper handles without code edits (TODO-241)
Context: TODO-222 (tj's pick) turned out already shipped+closed 2026-07-14 (stale work-package
  row); substituted the nearest well-specified open item per tj's "next autonomous win" intent.
  Design Fable, implementation sonnet subagent, review+fix Fable.
Added: db.py user_taper_aliases table (USER-tier, in USER_TABLES, never exported): alias_norm PK,
  canonical, action add|remove (CHECK), approved, note, timestamps. 'add' rows add/override an
  alias; 'remove' rows suppress a builtin key.
Changed: db.py — builtin literal renamed _BUILTIN_TAPER_ALIASES; _KNOWN_TAPER_ALIASES is now the
  merged dict, rebuilt IN PLACE by reload_taper_aliases() (preserves dict identity for importers;
  derived _TAPER_UNIVERSE/_KNOWN_TAPER_KEYS_SORTED/_KNOWN_TAPER_RE reassigned). _normalise_alias_key()
  extracted from _normalise_taper + two inline duplicates. add/remove/list_taper_aliases() with
  BUG-246-style write-queue guard. list_taper_aliases() reloads first so a running backend converges
  on out-of-band CLI edits (gap caught in live smoke: merged count was stale cross-process).
Changed: taper_attribution.py — _ALIAS_KEYS_BY_CANONICAL build extracted to _rebuild_alias_index()
  (called at import + top of recompute()); _TAPER_UNIVERSE now read via db module attribute
  (frozenset reassigned on reload; direct import would go stale) + PEP 562 __getattr__ forwarder.
Added: app.py — reload_taper_aliases() at startup after init_db; GET/POST /api/tapers/aliases +
  DELETE /api/tapers/aliases/<alias> (writes curator-gated, matching adjacent taper routes).
Added: taper_review.html "Taper aliases" collapsible admin section (list w/ builtin|user badges,
  add form, remove/suppress buttons, recompute button); tools/taper_aliases.py CLI (list/add/remove,
  --recompute); tests/test_taper_aliases.py (14 tests).
Verified: 58 targeted (aliases+attribution+fingerprints) + full suite 850 green; backend restarted;
  live smoke: API add/remove, CLI out-of-band add visible to running backend (286→287→286 merged).
Ops (same session): mirror crawl session 33 (seeded 07-16 12:41) confirmed done — 4,269 fetched,
  0 failed; entry_files downloaded=0 4,357→88 (long-tail mangled/double-encoded URLs, 1 xref-named
  but not a checksum fileset). Backend was stale (predated xref_ingest routes) — restarted.
  POST /api/xref_ingest/scan rerun per TODO-252 note: staged 0 new (all 108 missing xref text
  files had landed before the 13:16 scan; TODO-252 import was complete as shipped).

[2026-07-16] — feat(backend): xref B8 promoted — site-mirror xref ingest shipped + 6,632 checksums imported (TODO-252)
Context: tj D-2 decision — promote B8 from report-only to a reviewed import path, then
  directed bulk import ("all these xref should get added, one go"). flat_file.py pattern.
Added: backend/xref_ingest.py — scan_mirror (parse LBF-*-xref-*-text.txt via
  _read_checksum_text + parse_checksum_text; "new" = no (checksum, lb_number) row; idempotent
  rescan, approved/rejected never touched), approve_filesets (INSERT OR IGNORE of is_new rows
  only, refuses non-staged ids), reject_filesets, get_filesets.
Added: db.py xref_ingest_filesets + xref_ingest_rows staging tables (USER tables — audit/
  provenance record, never exported; checksums schema untouched); 4 /api/xref_ingest/* routes;
  tests/test_xref_ingest.py (9 tests; full suite 836 green).
Changed: checksums 705,352 → 711,984 (+6,632). Scan: 2,087 mirror xref text files parsed,
  0 unparseable, 1,801 fully covered by master import already, 286 filesets staged (269 LBs,
  xref ids 9–2149) and all approved per tj. Private-linkage check (tj flagged): zero staged
  LBs among the 62 private pages / entries 'missing' / lb_missing.
Verified: lookup of ingested xref-1143 (LB-01124, 332 rows) resolves with zero NOT FOUND —
  46 matched to LB-01124 (matched_xref 1143) + six member filesets attributed to their
  canonical LBs. GUI review card (P2) dropped per bulk directive; rerun scans via API.

[2026-07-16] — fix(scraper): site mirror now downloads all known attachment links, xref included
Context: tj directive — mirror must cover every link incl. xref attachments. The crawler was
  purely BFS link-discovery, so entry_files URLs not linked from any re-fetched page were
  never queued: 4,357 attachments absent from disk (109 xref: -text.txt/-lbdir.txt/
  -DigiFlawFinder.html), only 9 known to site_inventory.
Added: backend/db.py get_missing_attachment_urls() — entry_files rows with downloaded=0.
Changed: backend/site_crawler.py crawl() seeds those URLs (discovered_by='entry_files',
  same-domain + skip-ext guards) after the index seeds, so the mirror converges on every
  attachment the scraper knows about; existing /files/ handling marks entry_files.downloaded=1
  on fetch. This is mirror-side only — no checksums ingest (B8/D-2 unchanged).
Added: tests/test_scraper_crawler.py::test_get_missing_attachment_urls_returns_undownloaded_only.
Verified: crawler test file 61 passed; backend restarted; incremental crawl session 33 started
  with queue_size 4,348 (the seeded set) — ~1.8 h at the 1.5 s delay.

[2026-07-16] — feat: xref incorporation shipped end to end — copy-level filesets (TODO-246, B1–B7)
Context: instructions/complete/FABLE_XREF_INCORPORATION.md; xref = fileset id (0 = canonical),
  copy-level (this copy IS xref-N) vs entry-level (entry HAS alt filesets) per
  docs/XREF_SEMANTICS.md. Covers B1/B2/B5/B6 committed in the cut-off prior session
  (never logged) + B3/B4/B7 today. B8 site-mirror ingest NOT built per D-2 default —
  master import stays the only checksums write path; D-1 (5-digit xrefYYYYY) and
  D-3 (legacy gui/ frozen) defaults also applied.
Added: backend lookup lb_summary carries matched_xref + xref_groups (B1); my_collection.xref
  + folder_lb_link.xref columns, pipeline names xref copies "… (LB-XXXXX-xrefYYYYY)" (B2).
Fixed: dff_reports rekeyed (lb_number, xref) — LBF-*-xref-* reports attributed to the right
  fileset (B5); cli.py dead XREF guard dropped, missing list uses winning fileset (B6).
Changed: gui_next lookup surfaces (B3) — XREF removed as a status; xref-NNNNN pill augments
  the status pill (quick lookup, summary, checksum groups); Cross-refs bar counts/filters
  matched_xref > 0 (lookupState.ts, lookupStore.ts, ScreenQuickLookup/ScreenLookup,
  LookupDetail).
Changed: gui_next entry-level surfaces (B4) — Search Xref column from xref_map; Collection
  filter split into "My xref copies" (copy-level) vs "Entries with alt filesets"
  (entry-level, detail-pane marker); Library/DetailPanel relabeled "Alt filesets",
  detail checksums grouped by fileset, canonical first (ScreenSearch/ScreenCollection/
  ScreenLibrary, DetailPanel).
Changed: locales de/fr/es/it/nl DeepL-synced (5,487 chars); dead xref keys pruned from all six.
Docs: PROJECT.md schema rows, matched_xref dimension, collection/lookup API fields (B7);
  spec moved to instructions/complete/ + README row.
Verified: /gui-check PASS (node+renderer types, build); fixture LB-2 xref-961 → MATCHED with
  matched_xref 961 + correct xref_groups (after backend restart — stale process gave null);
  backend suite 826 passed. One order-dependent flake logged as BUG-254 (passes solo,
  pre-existing).

[2026-07-16] — chore(docs): repo sweep — stray root files and dead Qt scripts moved to attic/
Context: root had ~19 stray one-off reports/artifacts; grep-verified nothing in live code
  references any of them (attic/README.md documents each file's origin and verdict).
Added: attic/ + attic/README.md — holding pen for deletion candidates, tj to review/purge.
Changed: moved to attic/ — 4 wtrf_*.md reports, shared_checksums_report.md,
  missing_from_collection.tsv, public_not_owned.html, scan.json, batch_verify_run.log,
  notes.todo (pre-TODO.md Qt-era notes, all items done/superseded), 0-byte root
  observations.db + losslessbob.db strays, losslessbob.tar.gz, screenshot_log.txt +
  screenshot-lookup.png, tools/tapematch/observations.db.bak-20260612 (month-old backup),
  and Qt-era scripts/{build_qm,port_qt_to_json,fix_ts,fix_ts2}.py (dead since GUI removal;
  scripts/deepl_translate_gui_next.py kept — used by /gui-next-i18n).
Changed: .gitignore: attic/observations.db.bak-* line (other moved blobs already covered
  by bare-name patterns).
Removed: .claude/worktrees/* — 19 stale agent worktrees, 68 MB (gitignored, no log entry
  impact). Left alone by decision: tapematch .venv-emb/.venv-nmfp (staircase rescore may
  still use fp code), docs/screenshots (live, wiki-referenced). CHANGELOG rotation checked:
  May already archived 07-06, June not due until August.

[2026-07-16] — chore(gui): legacy PyQt6 GUI removed — gui_next is the sole frontend
Context: spec'd and executed same-session (instructions/complete/LEGACY_GUI_REMOVAL_SPEC.md);
  tj signed off D1=delete Docker stack, D5=no frozen-build users. 4 commits (a4326e47,
  674249bb, 88676070 + docs), net ~49k lines removed.
Removed: gui/ (19 modules, 18.5k LOC, Qt locales/resources), main.py, run_next.py (dead
  pre-Electron launcher), losslessbob.spec + losslessbob_linux.spec, tools/losslessbob.iss +
  build_windows.bat, scripts/translate_ts.py, /i18n-update skill, Dockerfile +
  docker-compose.yml + docker/ (noVNC stack), .dockerignore, secrets/ (Docker-only secret
  templates; all .txt were 0 bytes — no real credentials), PyQt6/PyQt6-WebEngine pins
  (+ pytest-qt uninstalled from .venv).
Changed: backend/resources/ now hosts map.html + leaflet/ (moved from gui/resources/;
  /map + /leaflet routes repointed; QWebChannel bridge and Search-tab buttons stripped from
  map.html — postMessage filter path for gui_next's ScreenMap iframe kept). New
  backend/platform_utils.py hosts open_in_vlc (was gui.platform_utils). Qt test classes
  dropped from tests/test_lb_master.py.
Fixed: BUG-249 closed (resolved-by-removal: crashing qtbot test deleted); BUG-106 closed
  (obsolete: legacy Windows installer channel deleted).
Docs: PROJECT.md (tech stack, file tree, GUI sections replaced with removal note, legacy
  conventions cut), .claude/CLAUDE.md, BEST_PRACTICES.md, wiki (GUI/Architecture/
  Dev-Workflow/Home).
Verified: 799 tests pass without Qt; backend restart clean; /map + /leaflet serve 200 from
  new location. tj to eyeball ScreenMap visuals.

[2026-07-16] — chore(db): TODO-240 complete — venue gazetteer fully resolved, all entry locations geocoded
Context: overnight completion of the geo chain started 2026-07-15 (TODO-239 backfill → resolve → geocode).
Changed: venue_geocoded (data): resolve finished 4,071/4,071 — final mix 2,125 bounded_venue,
  1,388 setlistfm_city, 419 wikidata, 124 city_geocode, 15 failed. Pre-backfill city_geocode
  pins were reset + re-laddered (587/726 upgraded to venue-precision/zero-cost sources); old
  pins snapshotted in _city_geocode_backup_20260715 (drop the table once satisfied).
Changed: location_geocoded (data): geocoder run_batch processed all 6,584 remaining
  entries.location values — 6,008 via free gazetteer inheritance (4,003 venue + 2,005 city),
  531 skipped_not_concert, 9 live Nominatim calls. 0 un-geocoded remain.
Verified: db.get_map_data() spot-check — 11,090 markers, city_level 4,506 (40.6%).

[2026-07-15] — fix(db): BUG-118 degenerate-checksum lookup fix + geo backfill (TODO-239) + backlog burn-down (TODO-156/236/242, BUG-251)
Context: autonomous backlog session (xref items TODO-246/249 explicitly parked by tj).
Fixed: backend/db.py: BUG-118 phantom lookup conflicts — new _DEGENERATE_CHECKSUMS /
  _is_degenerate_checksum(); lookup_checksums treats empty-file MD5/SHA-1 and all-zero ffp
  as non-evidence in both directions (no match evidence, never counted missing; detail rows
  kept with ignored=True). Phantom quartet 04994/03029/06748/11900 shared the empty-file MD5.
  Verified: functional test vs real DB + 240 tests green (db_lookup/db_writes/setlistfm/geocoder).
Added: backend/importer.py: de-dup guard — incremental imports (≤500 new LBs) log checksums
  already present under other LB numbers (surfaces future BUG-118-class duplicates at import time).
Added: shared_checksums_report.md (repo root): BUG-118 item-1 report — 5,261 shared
  (checksum,chk_type) groups across 223 LB-sets; top cluster 16054/16101/16440/16511/16621
  shares 718 hashes (likely one recording under six entries; needs curator review).
Changed: lb_problems table (data, TODO-156): 32 rows added covering BUG-118 conflict pairs,
  the six-way 16000-series cluster, BUG-120 verify mismatches, BUG-252 reconcile entries.
Added: docs/wiki/Taper-Attribution-Flow.md (TODO-236): attribution pipeline flowcharts
  (Layer 0/1, disabled Layer 2, curator loop, conflict-queue split) + wiki Home index row.
Changed: data (TODO-239): setlist.fm force re-scrape backfilled city coords — 4,147/4,149
  setlistfm_shows rows now carry city_lat/lon (was 0). venue_gazetteer resolve re-launched
  for the 2,361-seeded remainder (07-14 batch had died at 1,710/4,071); setlistfm_city pins
  confirmed working. Geocoder run_batch still pending → TODO-240 In Progress.
Changed: BUG-251 closed without re-run: contamination scan of all 2,280 tapematch run dirs
  found only the known 20260602_205451 report; clean sibling 20260602_205500 (regenerated 9s
  later) supersedes it — SUPERSEDED.md marker dropped in the dir.
Changed: TODO.md: TODO-242 investigated → decision-ready (propagation works, both LBs carry
  ltf; asymmetry is the spec'd confirmed-only pill policy; "Needs review" = tapematch family
  review_flag with tooltip already wired — decision + optional reason-backfill remain).

[2026-07-15] — chore(docs): TODO-248 ledger ID integrity — open/done collisions fixed, archive frozen (option 1)
Context: 20 duplicate BUG ids in BUGS_DONE.md, 17 duplicate TODO ids across TODO files, and
  2 ids (BUG-175, BUG-200) that named an open bug and an unrelated fixed bug simultaneously,
  making ledger.py bug-close ambiguous. tj decided option 1 ("do 1 thats it"): leave archive
  duplicates frozen as historical noise; renumber only the 2 open bugs that collide.
Changed: BUGS.md: open BUG-200 (tapematch report.md cross-contamination) renumbered to
  BUG-251; open BUG-175 (LBDIR reconcile MD5 mismatch) renumbered to BUG-252; each entry
  carries a "Renumbered:" alias note so pre-2026-07-15 references stay traceable. The fixed
  BUG-175/BUG-200 in BUGS_DONE.md keep their numbers.
Changed: TODO.md: consistency check found 3 open/done TODO collisions of the same class
  (missed by the original TODO-248 census) — open TODO-155 "Improve xref handling" -> TODO-249,
  open TODO-107 "Disk Scanner" -> TODO-250, open TODO-106 "Trading multi-friend batch compare"
  -> TODO-251, each with a "Renumbered:" alias note; the done copies keep their numbers.
  TODO-172 cross-reference updated (BUG-175 -> BUG-252). Historical CHANGELOG/PROJECT.md
  references intentionally untouched. tools/ledger_dedup.py assessed: report-only, no rewrite
  path — hand edit was correct.
Closed: TODO-248 -> TODO_DONE.md (within-archive duplicates remain by decision).

[2026-07-15] — feat(gui): TODO-247 visual-verification driver — bite 4 + spec CLOSED (3b won't-do)
Context: instructions/complete/FABLE_VISUAL_VERIFICATION.md §8. tj chose bite 4 over bite 3b
  when the two were put to him as independent next steps, then killed 3b outright: "not
  enough animation in the app to matter". TODO-247 is CLOSED and the spec is closed in
  full — bites 1/2/3a/4 shipped, bite 3b deliberately never built.
Decision: bite 3b (dev-gated progress fixture) WON'T DO, tj sign-off 2026-07-15. Its only
  consumer was one progress meter (FileProgressBar) and its price was a test-only intercept
  inside start_file_job in PRODUCTION code (backend/filer.py), past three guards, plus a
  simulated _run() and a staged pipeline row (spec finding 12). Accepted consequence:
  acceptance criterion 4 is permanently unmet by choice and the meter's mid-fill state is
  not machine-verifiable. The `watch` ACTION itself is built and works (bite 3a) and still
  runs against real jobs — only the synthetic fixture was dropped; don't read this as
  "watch was cancelled". Finding 12 kept as the record of why, for any future revisit.
Added: .claude/skills/verify/SKILL.md `--electron` mode (Tier B). Documents both tiers as a
  table (driver, PNG dir, extra actions, window.api, cost) and when to reach for B over A:
  window chrome, real sizes, display scale, native preload flows, main-process state.
  Both tiers share tools/debug_screens.json, so the screen tour is identical.
Added: PROJECT.md tools/ listing now names all 7 driver files (browser_driver, driver_core,
  electron_driver, electron_preflight, electron_display, electron_driver.config.json,
  debug_screens.json). Closes a PRE-EXISTING gap — the listing mentioned no driver at all;
  browser_driver.mjs was already absent before this work. check_project_refs.py exits 0
  either way (it checks routes/tables/screens/backend modules, not tools/*.mjs).
Changed: .claude/CLAUDE.md Verification section — /verify is the named exception to the
  "no screenshots" rule, and only on explicit user invocation. Wording is deliberate:
  having the capability is not permission to use it on initiative.
Changed: instructions/FABLE_VISUAL_VERIFICATION.md -> instructions/complete/ (+ README.md
  row, + the instructions/ path references inside the 3 driver source headers).
  complete/ here means "design record for a shipped driver", NOT "every bite landed" —
  the spec's resume block and README row both say bite 3b is deferred.
Verified: full Tier B tour re-run after the path edits — all 17 screens captured to
  .debug/electron/, every action ok, backend on :5174 survived. `node --check` clean on
  all 5 .mjs files; check_project_refs.py exits 0. Screenshots NOT reviewed — that was a
  smoke test of the tool, not a /verify run; tj verifies visuals.
Remaining: nothing. Criteria 1/2/3/5/6 met; criterion 4 withdrawn with the fixture (above).
Verified (example run, tj-requested): 25 PNGs in .debug/electron/ — the 17-screen tour, plus
  size-matrix at exactly 1280x768/1440x900/1920x1080/2560x1440 and scale-matrix on /lookup at
  1440x900/1800x1128/2160x1350/2880x1800. Spot-checked two: live data, nothing clamped.

[2026-07-15] — feat(gui): TODO-247 visual-verification driver — bite 3a: resize/size/scale/watch
Context: instructions/FABLE_VISUAL_VERIFICATION.md §6. Bite 3 split into 3a (driver
  actions, tools/ only) and 3b (progress fixture) — see the Notes below.
Added: driver_core.mjs actions `resize`, `size-matrix`, `watch`, `main-eval`, shared by
  both tiers via a new `caps` opt ({resize, mainEval}) each driver supplies — a driver
  that can't do one omits it and the action fails that step cleanly instead of the run.
  Tier A resize = page.setViewportSize; Tier B = real window; Tier A has no mainEval.
Added: electron_driver.mjs `scale-matrix` (CLI-level, not a session action:
  --force-device-scale-factor is a launch flag, so each scale needs its own launch).
  Pins a 1440x900 DIP baseline per row, so the matrix means "same logical layout,
  varying DPR" rather than inheriting whatever the default window was.
Changed: Tier B resize uses setContentSize, NOT spec §6's setSize (deviation recorded in
  code + spec finding 9). Tier A's setViewportSize sets content size exactly, so an
  outer-frame Tier B would make the shared debug_screens.json produce different PNG
  sizes per tier — setSize gave 2559x1411 for a "2560x1440" shot, the title bar eating
  the difference. The app's minWidth/minHeight are outer constraints, still respected.
Changed: electron_driver.config.json xvfbScreen 2560x1440x24 -> 2920x1860x24. The screen
  is sized by both consumers: max(size-matrix largest content, scale-matrix baseline x
  max scale) + decoration. Undersizing silently CLAMPS rather than erroring — at
  2600x1500 the 2x row capped at 2600x1480, which is 1300x740 logical, below the app's
  own 768 minimum: a frame showing a layout no real user could have. ~22MB of extra
  virtual framebuffer is nothing against a lying screenshot.
Verified: size-matrix PNGs land at exactly 1280x768 / 1440x900 / 1920x1080 / 2560x1440
  (112-186KB each, non-blank); scale-matrix at 1440x900 / 1800x1128 / 2160x1350 /
  2880x1800, nothing clamped; watch emits 5 frames at 300ms and stops on both the
  selector and timeout paths; backend on :5174 survived every run.
Known: scale-matrix 1.25x is 1128px tall, not 1125 — Electron reports a 902 DIP content
  height at fractional DPR (902x1.25=1127.5). Accepted: the capture is honest about the
  window it got, and §10 puts pixel-diff baselines out of scope. Finding 11.
Remaining: bite 3b (progress fixture — finding 12: it needs a start_file_job intercept
  in backend/filer.py, not just driver work), bite 4 (/verify --electron, docs).

[2026-07-15] — feat(gui): TODO-247 Electron visual-verification driver (Tier B) — bites 1-2
Context: instructions/FABLE_VISUAL_VERIFICATION.md, attempt 3 at driving the real app.
  Prior attempts failed because they captured pixels from OUTSIDE the app (compositor/
  VNC) — locked down on Wayland, flaky on NVIDIA. This one captures from inside the
  render pipeline (Playwright page.screenshot() -> CDP), so neither is involved.
Added: tools/electron_preflight.mjs — probes all 4 display backends on this machine
  and records the winner in tools/electron_driver.config.json (committed; the one
  durable output of Bite 1). Result: Xvfb at 2560x1440x24, --ozone-platform=x11
  --disable-gpu --no-sandbox. Wayland and XWayland also booted (~1.6s, same as Xvfb)
  but a window cannot exceed its screen, and size-matrix needs 2560x1440 which no real
  display here provides; Xvfb is also deterministic and session-independent. Ozone
  headless is dead as the spec predicted — CDP attaches, no window is ever created.
Added: tools/electron_driver.mjs — Tier B MVP (screenshot/navigate/click/fill/eval/
  session), same session-JSON format as Tier A; PNGs go to .debug/electron/ so the two
  tiers can share debug_screens.json without overwriting each other. Full tour passes.
Added: tools/driver_core.mjs — action runner extracted and shared with browser_driver
  .mjs (spec §3: don't fork two copies); tools/electron_display.mjs — Xvfb lifecycle +
  X11/Wayland socket discovery, shared by preflight and driver.
Fixed: gui_next main/index.ts ensureBackend() now honors LB_NO_BACKEND_SPAWN=1 (dev
  only, !app.isPackaged) — it kills whatever owns :5174 and respawns, which would
  murder a manually-started backend mid-driver-session.
Notes: three findings amend the spec (§4/§6, recorded there for Bite 3). (1) Display
  env is never inherited — the shell has DISPLAY and WAYLAND_DISPLAY empty with
  XDG_SESSION_TYPE=tty; the sockets exist but must be discovered and set explicitly.
  This is a likely cause of the 2026-06-04 attempt's failure: the missing env, not the
  backend. (2) ready-to-show never fires under Playwright on any backend, and
  index.ts gates win.show() on it — every driver must force show via app.evaluate().
  (3) app.evaluate() has no require in scope; destructure electron off the callback arg.
Remaining: Bite 3 (resize/size-matrix/scale-matrix/watch + progress fixture), Bite 4
  (/verify --electron, docs). Screenshot verification stays user-invoked only.

[2026-07-15] — fix(gui): TODO-243 renderer silent-catch audit — surface user-action failures
Context: STRUCTURE_REVIEW item 15 follow-up. Audited all 29 (was 26) renderer
  `.catch(() => {})` sites; 23 kept (mount-time/passive display fetches, true polls,
  2 deliberate best-effort calls: LBDIR auto-retrieve, Pipeline stopRun server cancel),
  6 fixed where user-initiated actions failed invisibly. No new locale keys: Pipeline
  reuses translated verify.toast.* keys; Scraper/Spectrograms keep their screens'
  hardcoded-English convention. gui-check: node types + renderer types + build PASS.
Fixed: gui_next ScreenPipeline.tsx: VerifyStageContent copy-report now toasts
  ok/bad via shared Toast primitive (was silent; its ScreenVerify twin already toasted).
Fixed: gui_next ScreenScraper.tsx: LogPanel Copy button flashes "Copied ✓"/"Copy failed"
  (screen has no toast infra; local label feedback).
Fixed: gui_next ScreenLibrary.tsx: forum-post toasts no longer claim "link copied" when
  the clipboard write failed — copyUrls returns success and gates the copied-suffix.
Fixed: gui_next ScreenDbEditor.tsx: loadSchema surfaces errors via setStatus (matches loadRows).
Fixed: gui_next ScreenSpectrograms.tsx: Stop button toasts "Stop failed" on request failure.
Fixed: gui_next ScreenTapeMatch.tsx: A/B play() rejection reverts playing state (UI no
  longer stuck showing "playing" after autoplay/decode failure).

[2026-07-15] — docs: TODO-244 PROJECT.md reference sections regenerated from code — STRUCTURE_REVIEW COMPLETE
Context: final STRUCTURE_REVIEW session (P1, items 1-8 + item 19 listing + item 12 convention
  note). Review closed: doc moved to instructions/complete/, sole survivor item 15 -> TODO-243.
  Also committed the uncommitted 07-14/07-15 session tail first (84fa1e1f: TODO-214 fingerprints
  gated OFF, TODO-183 close, ledger moves) so this work got its own clean commit.
Changed: PROJECT.md (+428 lines): route tables for 78 undocumented Flask routes (~26 new
  group sections); 12 missing schema blocks (lb_master, lb_status_history, my_collection,
  collection_meta, my_wishlist, bobdylan_*, setlistfm_*, friend_collection*, wtrf_downloads),
  each flagged MASTER/USER; file tree regenerated from disk (gui_next/ layout, 12 backend
  modules, instructions/, docs/, ~26 test files, 13 tools/ scripts); gui_next screens table
  now 24 files (hardcoded count dropped), +lbUrl.ts/useResizableColumns.ts store rows; 4 stale
  data/pages|attachments refs -> data/site/detail|files; preload IPC list = actual 10-member
  window.api surface; port-5174 note enumerates all real sites; GUI Conventions retitled
  "Legacy GUI Conventions (frozen)" + new gui_next conventions section; concert_ranker listing
  gains quality_score.py/text_features.py; API error-shape convention note added.
Added: tools/check_project_refs.py — drift checker extracting routes/@app.route, tables/CREATE
  TABLE (excl. *_new migration temporaries), gui_next screens, backend modules from disk and
  requiring each to be mentioned in PROJECT.md; exit 1 on drift. Clean run: 294 routes,
  62 tables, 24 screens, 42 modules, 0 missing. Wired into /session-close step 5.
Notes: review's fingerprints/audio_tracks tables (item 2) don't exist in current code
  (taper_fingerprints computes in-memory) — nothing to document. ScreenFingerprint had already
  been documented since 07-04; 4 screen rows were truly missing, not 5.

[2026-07-15] — refactor: STRUCTURE_REVIEW P2+P3 cleared (items 9-14, 16-20) — dead code removed, site URL + conventions consolidated
Context: working through instructions/STRUCTURE_REVIEW.md (2026-07-04) bottom-up. Three commits:
  a305caf2 (P3), 30d97229 (item 9), 8f689b3a (items 10-14). Remaining: item 15 -> TODO-243,
  P1 doc regeneration -> TODO-244.
Fixed: backend/db.py — checksum-lookup detail_url built from int LB without zero-padding
  (LB-42.html -> 404); now uses paths.detail_url() which pads to 5 digits.
Added: backend/paths.py — SITE_BASE_URL + detail_url(lb), single source for losslessbob.com URLs
  (backend twin of BUG-221's lbUrl.ts). backend/app.py — JSON @app.errorhandler(Exception) in
  create_app(): unhandled exceptions return {"error": ...} 500 instead of Flask's HTML page;
  HTTPExceptions pass through. gui_next lib/lbUrl.ts — exports LB_SITE_BASE + lbLabel();
  ScreenScraper's two hardcoded base-URL literals replaced.
Changed: scraper/site_crawler/flat_file/forum_poster/app/db all derive from SITE_BASE_URL;
  checksum_utils.md5_file is the one canonical file-MD5 (raising; compute_md5 delegates,
  importer/scheduler import it); module loggers standardized to logger=getLogger(__name__) in
  db.py (10 inline calls + 3 local variants + 5 orphaned local imports), sharing.py, scheduler.py.
Removed: stray 0-byte backend/losslessbob.db; committed smoke-run output tests/pipeline_smoke_*
  (now gitignored; their BUG-200..202 ids were generator placeholders colliding with real ledger
  ids); tools/_wtrf_batch_85_runner.py; concert_ranker/BUILD_REPORT.md. Moved:
  backend/debug_forum_post.py -> tools/ (standalone CLI diagnostic); concert_ranker/test_pipeline.py
  -> tests/test_concert_ranker_pipeline.py, converted from print-only script (zero asserts, pytest
  collected nothing) to a real test — found its implied orderings no longer hold under production
  calibration (decent-AUD vs muddy-AUD synthetics within 0.009; lossy sibling unflagged); asserts
  kept to the stable invariant (clean SBD ranks #1).
Notes: full suite 799 passed (one order-dependent flake in test_db_lookup: daemon migrate_lb_master
  thread from an earlier test — pre-existing, passes on rerun). Renderer tsc is at 0 errors; the
  14-error ScreenScraper baseline in the gui-check skill doc is stale (updated this session).
  app.py static HTML footer link + html_utils.py docstring keep the URL literal deliberately.

[2026-07-15] — chore(backend): TODO-183 Concert Ranker CLOSED — sibilance_ratio_db demoted to informational, remaining riders won't-do
Context: the ranker has been functionally complete and in production for weeks (13,752 recordings
  scored; AUD CV Spearman 0.66 / SBD 0.56; GUI Quality tab since 07-01). tj signed off closing the
  open riders as not worth the value. One closing code action: resolved the open sibilance decision
  as option (b) from the 06-30 investigation.
Changed: concert_ranker/config.py — POLARITY["sibilance_ratio_db"] -1 -> 0 (informational; never
  de-confounded from brightness: rho +0.34 above 9 kHz hf_ceiling, artifact below it), its
  SEVERITY_BANDS entry ("slightly essy"/"sibilant") removed globally + from _build_decade_bands;
  sibilance_crest (validated, rho -0.34..-0.65 correct sign) kept at polarity -1 as the sibilance
  defect signal. concert_ranker/scoring.py — sibilance_ratio_db removed from FAMILY_METRICS["tonal"]
  fusion. Feature extraction (_sibilance_native) unchanged; both metrics still stored per recording.
Won't-do (documented in TODO_DONE-183): 9kHz-gate rescan, SBD-per-decade bands, pop/click detector,
  DFF-on-Linux, lossy_flag calibration, dynamic_range_dr production, band-label phrasing polish.
Verified: tests/test_concert_ranker.py 49/49 green.

[2026-07-15] — feat(backend): TODO-214 Layer-2 taper fingerprints BUILT + CALIBRATED — gated OFF pending tj sign-off
Context: implemented the Session-5 design (WORK_PACKAGE_2026-07-14.md), then calibration forced a
  redesign: raw argmax scoring was only ~53% precise on a 5-fold confirmed-tier holdout. Shipped
  design uses THREE gates — score >= 150, top1−top2 margin >= 80, and winner in a per-run
  cross-validated reliable-taper set (per-taper precision >= 0.90 with >= 10 gated assignments) —
  plus exclusion of ALL known taper alias tokens from every profile. Holdout at shipped gates:
  96.2% precision / 23.6% coverage / 12 reliable tapers / 93 would-be inferred rows.
Added: backend/taper_fingerprints.py — Monroe weighted-log-odds vocabulary profiles, DSU
  poisoned-component exclusion (conflict=1 / curator-unresolved components contribute no source
  docs), 3-gate infer(), K-fold calibrate(). LAYER2_ENABLED=False kill-switch (see below).
  tests/test_taper_fingerprints.py (18 tests; suite 44/44 green).
Changed: backend/taper_attribution.py — _compute_layers01() extracted from recompute() (returns
  rejects too); recompute() calls Layer 2 between _propagate_weak and the reject/unresolved
  re-apply, gated on LAYER2_ENABLED. tools/attribute_tapers.py — new --calibrate-fingerprints
  (read-only gate sweep + reliable-taper table).
Fixed (pre-ship, in-flight code): _poisoned_lbs missed edge-less curator-unresolved lbs (never
  entered the DSU); non-deterministic evidence-token ordering on tied weights.
Decision: NOT enabled — spot-checks of would-be rows on the real unattributed pool found
  systematic misattributions invisible to the holdout (profiles latch onto era/setlist vocabulary,
  description formatting style, and 16bit/44.1khz-type boilerplate; docs explicitly crediting
  OTHER tapers — Walkin' Dude, mary_lynch, Ray Ackerman, hanno — were assigned to profile owners;
  est. true precision ~60–75%, below the spec's >= 90% bar). Era-matched backgrounds and
  gear-token-only vocabularies were prototyped; neither eliminates the leakage. Verified: 44/44
  tests; --dry-run recompute writes Inferred: 0 with the flag off (6,702 rows, identical to
  pre-Layer-2 output).
Decided (tj, same day): leave disabled, revisit later — TODO-214 closed (won't-ship, revisit
  options preserved in WORK_PACKAGE_2026-07-14.md Session 6); FABLE_TAPER_ATTRIBUTION.md spec
  git-mv'd to instructions/complete/ (all code/doc references repointed, instructions/README.md
  row updated); taper_attribution.py tier docstring updated (inferred tier implemented but gated).

[2026-07-14] — feat(backend): TODO-226 COMPLETE — BobTalk/notes full-text search + Library lens search UI
Context: discovery shrank the scope — Part A's show-page surfacing (BobTalk quote, notes, NET
  concert #, chronicle) had already shipped with the TODO-162 P5b Olof tab in DetailPanel; the
  entry text was stale. Only the search was missing. Data: 859 events with bobtalk, 2,874 with
  notes (of 4,924) — LIKE suffices, no FTS5, no schema change.
Added: backend/db.py get_olof_bobtalk_search() (+_olof_like_pattern/_olof_snippet) — case-
  insensitive LIKE over olof_events.bobtalk/notes with %/_ escaping, ~60-char context snippets,
  both-fields dedupe (bobtalk wins), bobtalk-before-notes then date ordering. backend/app.py
  GET /api/olof/bobtalk_search (q min 2 chars else 400, limit capped 200) in the local-only olof
  route block. tests/test_olof_bobtalk_search.py (10).
Added: gui_next ScreenLibrary.tsx BobTalkSearch — speech-bubble IconButton + dropdown next to the
  performance-lens search (FilterMenu outside-click/Escape idiom), 300ms debounce, results show
  date + venue + snippet (italic for bobtalk); clicking navigates the lens to the show via the
  same selection path as a manual row click (un-collapse year, scrollToIndex, open DetailPanel);
  dates with no library rows render disabled with a "Not in library" hint. New Icon 'message'.
  Locale keys library.olof.search.* — en + DeepL de/fr/es/it/nl (4,730 chars).
Verification: full suite 780 passed / 5 skipped; tsc node+web 0 errors; production build clean.
  Reviewed subagent-reported git-stash incident: working tree verified clean, both pre-existing
  stashes intact, only intended files changed.
Bookkeeping: PROJECT.md olof route table + TODO-226 closed. TODO-240 opened for the TODO-223
  operational tail (trigger run_batch when the venue resolve batch — 652/4071 at close — finishes).

[2026-07-14] — feat(backend): TODO-223 COMPLETE — gazetteer wired into geocoder, map city-level flag (bite 3 of 3)
Context: bites 1–2 built venue_geocoded + the resolution ladder; this bite makes the gazetteer
  actually feed the map. High-value discovery: location_geocoded held only ~117 rows with 6,584
  distinct entry locations un-geocoded — gazetteer inheritance is the mechanism that populates the
  map without burning Nominatim calls.
Added: backend/geocoder.py — _venue_lookup_for_location()/_venue_key_for_location() derive the
  gazetteer (venue_norm, city_norm) key from the structured sources in seeding priority order
  (olof_events, setlistfm_shows, bobdylan_shows), normalizing via venue_gazetteer._norm_venue/_norm_city
  (deferred import; single source of truth for key form). run_batch(): eligible locations first
  inherit a resolved venue_geocoded pin (lat NOT NULL, source NOT IN seeded/failed) with no API call
  and no rate-limit sleep — source='gazetteer_venue', or 'gazetteer_city' + confidence capped
  'medium' for city pins (matches the TODO-222 cap; keeps the map's confidence != 'low' join);
  note records the venue key + gazetteer source. place_manual(): a fix whose location derives a
  venue key also upserts venue_geocoded (source='manual', manual_override=1 — resolve_venues never
  overwrites it) and immediately propagates to every other non-manual, non-skipped location_geocoded
  row at that venue (source='gazetteer_manual').
Added: backend/db.py get_map_data() emits city_level (bool; setlistfm_city/city_geocode/
  gazetteer_city/*-city sources); gui/resources/map.html popup shows a muted "city-level location
  (venue not yet pinned)" hint — deliberate narrow exception to the gui/ freeze: map.html is the
  shared Leaflet renderer that gui_next ScreenMap iframes, so the flag must live there (plain-JS
  page, hardcoded English like its other strings; no gui_next locale change).
Changed: backend/venue_gazetteer.py seed_venues() skips + cleans purely-numeric/empty venue keys
  (_is_numeric_or_empty_venue/_cleanup_numeric_junk; live run deleted 38 junk rows, table now 4071).
Fixed: backend/venue_gazetteer.py resolve_venues() now commits per venue — the 25-row batch commit
  held the SQLite write lock across the next venues' network waits (minutes at a stretch), which
  crashed backend startup with "database is locked" while a resolve batch ran. Found live when the
  post-deploy backend restart collided with the full resolution run.
Verification: +18 tests (tests/test_geocoder.py, test_venue_gazetteer.py) — key derivation/priority/
  miss, run_batch inheritance/fallthrough, place_manual propagation + skip cases, junk seed/cleanup.
  Full suite 770 passed / 5 skipped; gui_next tsc (node+web) + production build clean; backend
  restarted (uptime-verified) and coexists with the live resolve batch after the lock fix.
Operational: full resolution batch running (per-venue commits, ~2h; 280 resolved at last check —
  153 bounded_venue / 25 wikidata / 102 city). Follow-up once it completes: trigger geocoder
  run_batch so the 6,584 un-geocoded locations inherit pins (mostly zero API calls).

[2026-07-14] — backlog completion drive: landed in-flight GUI/docs work, closed 4 TODOs + 1 BUG
Context: session goal was shortening the backlog — close churners, not advance everything a little.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: library picks now show a muted
  known-taper fallback pill (taperBadgeLabel, tone=mute) when a taper is known but not confirmed —
  confirmed tapers keep the info-tone badge (in-flight from 07-13, committed 8fe70a3b after
  gui-check: node types PASS, renderer types PASS at 0 errors — old 14-error ScreenScraper baseline
  is gone — build PASS; reuses existing i18n keys, no locale run needed).
Added: instructions/FABLE_VISUAL_VERIFICATION.md (Electron visual-verification driver spec,
  attempt 3) + README.md index row, status "ready — not started" (in-flight from 07-13, 1d110c99).
Closed (no code change): TODO-233 by rescope (pt1 shipped 07-14, pt2 continues as TODO-235,
  pt3 out of scope); TODO-109 done — the 36 listed ruff violations no longer exist (ruff check
  clean across backend/, pytest 752 passed / 5 skipped; pre-commit auto-fix + feature commits since
  06-09 eliminated them), retroactive polish pass declined; TODO-209 won't-fix (cosmetic legacy
  ids, all in closed/archived entries, ledger.py prevents new collisions); TODO-179 won't-do
  (tentative "maybe"); BUG-230 won't-fix (dev-only cosmetic gear icon, reopen if packaged
  AppImage shows it). All five were user decisions 2026-07-14.

[2026-07-14] — feat(backend): TODO-223 (in progress) — venue gazetteer resolution ladder (bite 2 of 3)
Context: Bite 1 seeded 4109 distinct venues unresolved. This bite adds the ladder that turns a seeded
  venue into a coordinate. Planning premise correction: the ladder was specified to anchor on
  setlist.fm city coords (TODO-222), but those columns (setlistfm_shows.city_lat/city_lon/city_state)
  are entirely NULL — the force re-scrape that backfills them was never run (0/4131 rows). So the
  ladder anchors on a setlist.fm coord WHEN present, else a Nominatim city geocode — self-sufficient
  today, and it auto-upgrades if the backfill later runs.
Added: backend/venue_gazetteer.py resolution ladder, reusing backend.geocoder's geocode_one /
  _city_viewbox / 429-retry constants. Per seeded venue, stopping at the first hit: (1) bounded
  Nominatim venue-name search inside a ~30km box around the city anchor (source='bounded_venue');
  (2) Wikidata P625 via an mwapi EntitySearch SPARQL query, accepted only within 50km of the anchor
  so a same-name venue elsewhere is rejected (source='wikidata', covers demolished venues OSM lacks);
  (3) the city anchor itself as a city-level pin (source='setlistfm_city' or 'city_geocode',
  confidence='city'); else source='failed'. City anchors are cached per city so each city costs at
  most one Nominatim call. resolve_venues() drives the batch — processes source IN ('seeded'[,
  'failed' when retry_failed]), skips manual_override=1, updates in place, commits every 25, honors a
  limit. `python -m backend.venue_gazetteer resolve [N]` runs it. Helpers: _haversine_km,
  _geocode_retry (standalone 429 backoff + 1.1s Nominatim politeness), _city_anchor,
  _setlistfm_city_coord, _wikidata_venue_coord.
Verification: live smoke test (limit=3) resolved 1 bounded_venue + 2 city_geocode, 0 errors. Tests
  tests/test_venue_gazetteer.py +13 (27 total): haversine, anchor setlistfm-vs-geocode + cache,
  each ladder step, Wikidata accept/reject-by-distance/network-error, resolve_venues update + manual
  skip + limit. 88 passed with test_geocoder.
Deferred: the full 4109-venue resolution is a ~1-2h rate-limited Nominatim+Wikidata run — trigger
  it deliberately with `python -m backend.venue_gazetteer resolve`. Bite 3 wires resolved pins into
  geocoder run_batch (inherit, dedupe Nominatim) + place_manual venue propagation. Minor follow-up:
  38 purely-numeric junk venue seeds (~0.9%) should be filtered at seed time; the ladder currently
  falls them back to a city pin.

[2026-07-14] — feat(db): TODO-223 (in progress) — venue gazetteer table + seeding (bite 1 of 3)
Context: Shows repeat venues, so geocoding each show re-solves the same coordinate and scatters any
  manual fix across dates. TODO-223 builds a venue-level table so each distinct venue is solved once
  and every date inherits the pin. This is the first of three bites (table+seed, then the resolution
  ladder, then run_batch inheritance + place_manual propagation).
Added: backend/db.py — venue_geocoded(venue_norm, city_norm, venue, city, region, country, lat, lon,
  source, confidence, manual_override, note, geocoded_at), PK (venue_norm, city_norm), + source
  index. CREATE TABLE IF NOT EXISTS in SCHEMA_SQL (idempotent, additive).
  backend/venue_gazetteer.py — _norm_venue/_norm_city normalization (casefold + drop punctuation +
  collapse whitespace; the CITY key takes only the first comma-segment so a venue does not fragment
  across source-specific city strings like 'Birmingham' vs 'Birmingham, AL' vs 'Birmingham,
  Alabama'; venue keys keep commas since venue names legitimately contain them). seed_venues()
  enumerates DISTINCT concert venues from olof_events (event_type='concert'), setlistfm_shows and
  bobdylan_shows — richest source first — and inserts each unresolved (source='seeded', lat/lon
  NULL) via ON CONFLICT DO NOTHING, so re-seeding never disturbs resolved or manual_override rows.
Data: seeded 4109 distinct venues (the first-comma city key collapsed 6029→4109 by de-duplicating
  the same venue across city-string variants). Idempotent: a re-run inserts 0. bobserve 2022+
  festival venues (e.g. Ameris Bank Amphitheatre) now seed correctly thanks to the event_type fix.
Tests: tests/test_venue_gazetteer.py (14) — normalization keys incl. city-collapse and
  venue-comma-preservation, seed enumeration + concert filter + dedup, re-run idempotency preserving
  a manual row, tolerance of missing optional source tables. Full suite 739 passed, 5 skipped.
Deferred (later bites): resolution ladder (bounded Nominatim near the setlist.fm city coord →
  Wikidata SPARQL for demolished venues → setlistfm_city fallback), then geocoder run_batch
  inheriting gazetteer pins and place_manual writing venue-level fixes.

[2026-07-14] — fix(scraper): bobserve field normalization — 66 festival/benefit concerts now geocode; US location fields de-shifted (TODO-228 follow-up, unblocks TODO-223)
Context: TODO-228 loaded 391 bobserve shows (2022+) into olof_events, but three field-quality bugs
  made the data unusable by the geocoder (which trusts the DSN taxonomy) and by any concert-venue
  seed. (1) bobserve event_type is free text ('concert - outlaw music festival', 'benefit - farm
  aid', 'soundcheck', 'tribute speech - …') where the geocoder tests event_type=='concert' exactly,
  so 64 real festival/benefit concerts were flagged skipped_not_concert. (2) US location lines omit
  country and sometimes carry a district ('Hollywood, Los Angeles, California'); the shared
  _split_city_region_country assumed 'City, Region, Country' and shifted them to
  city=Hollywood/region=Los Angeles/country=California. (3) A few non-standard pages captured
  tour_name='Musicians' (a section header) or an 'Info via bobserve: <url>' line.
Changed: backend/bobserve_parser.py — _normalize_event_type() maps the pre-'-' prefix onto the DSN
  canonical set (concert|session|rehearsal|broadcast|interview|other; benefit→concert since Farm Aid
  et al. are real gigs, soundcheck/tribute→other), preserving any lost detail (festival/benefit/
  soundcheck qualifier) in notes as 'event_type_raw: …' — but only on a real difference, not a
  case-only 'Concert'→'concert' one (74 rows, not 391). _split_bobserve_location() + _US_STATES
  detect a trailing US state → region=state, country='' (matching DSN's empty-country-for-US
  convention), city=the token before the state (leading district dropped); non-US rows still defer
  to _split_city_region_country. tour_name extraction skips 'Musicians' / 'Info via bobserve:' /
  'http…' tail lines. Re-parsed the mirrored data/olof/bobserve_pages/ (idempotent, no network).
Data: source='bobserve' event_type now concert=383 (was 317, +66 to the geocoder), other=7,
  rehearsal=1 — zero 'concert -'-prefixed strings; 270 US rows carry empty country + state region;
  0 tour_name='Musicians' remain.
Tests: tests/test_bobserve_parser.py (new, 25 tests) — event_type mapping table, US 2-part /
  3-part-with-district splits, non-US unchanged, tour_name guard, case-only-no-notes. 86 passed
  (with test_geocoder).

[2026-07-14] — feat(backend): TODO-228 (CLOSED) — bobserve.com setlist scraper supersedes the PDF-chronicle approach for 2022+ shows
Context: TODO-228 assumed the 2013+ Yearly Chronicle PDFs just needed text extraction to feed the
  existing chronicle-appendix setlist parser. Extracting real 2022/2023 chronicle PDFs directly
  found they carry NO per-show setlists at all — a calendar diary + a bare tour-itinerary table
  (date/city/venue only). bobserve.com's own current site instead publishes a full setlist
  database, one page per show at /setlist?event=<id>, with real per-song setlists (incl. cover
  credits), confirmed against real 2022 (Oslo) and 2023 (NYC) pages. That's the actual 2022+
  source; the PDF-itinerary path was not built.
Added: backend/bobserve_fetcher.py — two-step mirror: bobserve.com/eventsperiod?period=<year>
  lists every show's event id chronologically (ids themselves are NOT chronologically assigned,
  confirmed: id 4000 -> a 2004 show, id 3950 -> a 2014 show, so the index page is the only
  reliable id-discovery path), then each event page is fetched once into
  data/olof/bobserve_pages/, registered in the shared olof_pages table (corpus='bobserve').
  Reuses backend.olof_fetcher's browser-UA/retry/rate-limit helpers.
  backend/bobserve_parser.py — extracts each page's `data-clipboard-text` attribute (a clean,
  pre-formatted plain-text show summary bobserve renders for its own copy button) rather than
  the surrounding Tailwind markup; parses date/venue/city/region/country/event_type/songs/
  tour_name/musicians into olof_events (source='bobserve', event_id = 9,000,000 + bobserve's own
  id — a disjoint range from DSN's ~440620 max and chronicle_appendix's year*1000+seq) and
  olof_songs, reusing EventRecord/SongRecord/_split_city_region_country/_split_title_credits
  from olof_parser. A medley entry wraps its second song onto an unnumbered continuation line
  (confirmed: event 4801, '8.Medley To Be Alone With You' / 'Watching The River Flow' with no
  leading number) — folded into the preceding song's title with ' / ' rather than silently
  dropping the whole show's setlist, which the first pass at the song-block detector did.
Data: full crawl of 2022-2026 (391 pages, 0 fetch errors) -> 391 olof_events / 6137 olof_songs,
  source='bobserve'. 373 pages parsed clean; the 18 partial are all legitimate (15 are
  not-yet-played 2026 shows with no setlist posted yet, 3 are non-dated entries like a tribute
  video/rehearsal/speech). /api/olof/date, /api/olof/event, and the setlist-fingerprint scan
  (TODO-225) all query olof_events/olof_songs unfiltered by source, so 2022+ shows surface
  through the existing GUI/matching paths with no further wiring.
Docs: PROJECT.md — documents the three disjoint event_id ranges and marks the chronicle-appendix
  setlist path (source='chronicle_appendix') as superseded/never populated for its stated reason.


Added: backend/setlistfm.py + backend/db.py — setlistfm_shows gains city_lat/city_lon/city_state
  columns (PRAGMA table_info migration guard), populated from the setlist.fm API's
  venue.city.coords/stateCode at scrape time — a zero-geocoding, guaranteed city-level coordinate.
  Existing rows backfill on the next force re-scrape (POST /api/setlistfm/update {force:true}).
Changed: backend/geocoder.py — folded two new steps into the TODO-220 cascade in run_batch():
  (1) once a bare venue name and a known setlist.fm city coordinate are both available, a
  Nominatim search for just the venue name, bounded to a ~30km viewbox around that coordinate
  (source='bounded_venue'), is tried right after the full structured-string attempts —
  Nominatim's unconstrained hit rate on venue names alone is poor but improves once spatially
  constrained; (2) if every attempt up to that point misses, the known setlist.fm city coordinate
  is used directly as a fallback pin with no further Nominatim call (source='setlistfm_city',
  confidence capped medium) before falling to a city-text Nominatim geocode. The four structured
  lookup helpers (_get_bobdylan_shows_location_string etc.) now also return a bare venue_only
  string alongside the existing full/city_only pair. geocode_one() gained optional
  viewbox/bounded params. Wikidata SPARQL (TODO-222's optional step 3, for demolished venues) is
  deferred to TODO-238's venue-level table, which already plans it explicitly.
Tests: tests/test_geocoder.py + tests/test_setlistfm.py — updated the 3 structured-lookup
  functions' expected tuples, added coverage for _get_setlistfm_city_coords, _city_viewbox,
  geocode_one's viewbox/bounded encoding, and both new cascade steps end-to-end via run_batch();
  700 passed, 5 skipped.

[2026-07-14] — fix(backend): BUG-246 (CLOSED) — remaining-writer audit; guard the last two DB writers that could split reads/writes across databases
Context: BUG-246 (live show_picks wiped 2026-07-10) was fixed defensively in picks._write_picks the
  same day; the ticket left a REMAINING AUDIT — sweep the other db_path-taking writers for the same
  first-init-wins exposure (a writer READS current state via get_connection(db_path) but commits a
  state-dependent write through the get_write_queue() singleton, which is first-caller-wins and may
  be bound to a DIFFERENT db). Swept taper_attribution, flat_file, tapematch_sync, parse_lineage,
  the scrapers, geocoder, importer, song_index, setlist_fingerprint.
Found: two unguarded matches. (1) taper_attribution._write_attributions — wholesale DELETE FROM
  taper_attributions + reinsert of read-derived rows through the unguarded queue (WIPE class,
  identical shape to the original show_picks bug). (2) flat_file.apply_flat_file_release — an
  add/change/remove diff computed from a get_connection(db_path) read, committed through the
  unguarded queue (DESYNC class: a path mismatch skips real removals rather than wiping). All other
  swept writers are safe: tapematch_sync reads+writes on the same conn (never uses the queue),
  parse_lineage/scrapers/geocoder/importer are upsert-only or externally-driven (no read-then-
  wholesale-replace), and song_index/setlist_fingerprint already carry the guard.
Fixed: added the sanctioned picks-style _run_write(fn, db_path) helper (mirrors
  setlist_fingerprint.py) to backend/taper_attribution.py and backend/flat_file.py — when
  db_path != the queue's bound db, the write goes DIRECTLY via get_connection(db_path) instead of
  the singleton. Routed taper_attribution._write_attributions (+ single-row confirm/reject/
  mark_unresolved, all of which take db_path) and flat_file.apply_flat_file_release through it. No
  empty-payload refusal added (unlike picks): the path-match guard is the whole fix and
  taper_attributions can be legitimately empty on a minimal DB.
Verified: 42 tests pass (tests/test_taper_attribution.py + tests/test_show_picks.py), including a
  new regression test test_write_targets_db_path_not_queue_binding that binds the queue to DB A,
  recomputes against DB B, and asserts the taper_attributions rows land in B and NOT in A. BUG-246
  closed.

[2026-07-14] — feat(backend): TODO-213 taper conflict queue — 'kind' filter + "can't determine" verdict; mention queue cleared
Context: the /taper-review conflict queue held 53 conflict=1 rows, but 22 are series-vs-series
  (two legitimate taper series on one over-merged recording_families family) — un-pickable in the
  hand queue and owned by TODO-234 (family split), while polluting the review flow. The other 31
  are mention-vs-mention. Separately, a genuine same-family two-taper conflict is a historical
  documentation error with no ground truth, so confirm (fabricates a pill) and reject (implicitly
  picks the sibling on recompute) are both dishonest — the queue had no way to say "attribute
  nothing" and move on. All 53 conflict rows were tier 'propagated' (no pill), so nothing was
  mis-badged; the cost was pure queue-gating.
Added: backend/taper_attribution.py — `_is_series_vs_series()` (reuses `_SERIES_CODE_RE` +
  `_CONFLICT_CAND_RE` to classify a conflict as all-series-code candidates) and a `conflict_kind`
  arg on `list_attributions()` ('mention' excludes series-vs-series, 'series' keeps only them).
  New `mark_unresolved(lb)` curator API (mirrors `reject()`): upserts a sticky `taper_confirmations`
  'unresolved' row + deletes the `taper_attributions` row immediately. `_apply_unresolved()` drops
  every taper for an unresolved lb during recompute (vs reject's single-taper suppression);
  `_apply_confirmations()` now returns `(rejects, unresolved)` and recompute re-applies both after
  propagation. Idempotent + sticky (verified: full recompute keeps 31 parked, 0 attribution rows,
  22 conflicts remain).
Added: backend/app.py — `POST /api/tapers/attributions/<lb>/unresolved` (curator-gated); `kind=`
  param on the attributions list route (validated, 400 on bad value).
Changed: backend/taper_review.html — queue fetches `conflict=1&kind=mention` (series-vs-series no
  longer shown); new "Can't determine (historical conflict)" button → `/unresolved`; done-state
  explains the series exclusion points to TODO-234.
Data: bulk-parked the 31 mention-vs-mention conflicts as 'unresolved' via the live endpoint after
  a DB backup (data/backups/…_pre_unresolved_bulk.db) — /taper-review hand queue now empty; 22
  series-vs-series remain for TODO-234. taper_confirmations ledger: 58 confirm / 10 reject / 31
  unresolved.
Verified: 25 taper-attribution tests pass; apply-logic unit test (unresolved suppresses all tapers,
  reject/confirm unaffected); live endpoint checks (kind=mention→0, kind=series→22, bad kind→400).

[2026-07-14] — feat(backend+gui): TODO-232 part 2 (CLOSES TODO-232) — A/B auto-pick start point (quiet vocal passage) + GUI prefill
Context: TODO-231/232 A/B listening defaulted the start field to 0 s (start of performance). The LB
  curator method (TODO-187) is to A/B on a musically quiet passage where a vocal is still clearly
  present. With part 1 (RMS match) already shipped this session, this closes TODO-232.
Added: backend/ab_clips.py — pick_start_frame() (pure, audio-free scorer over a concert_ranker
  TrackCache: per-frame 1-4 kHz vocal band from stft_mag vs its 20th-pct floor, minus 0.5x the
  broadband-energy excess, so a quiet-but-vocal window wins over both silence and loud
  instrumentation); _decode_mono_region() (ffmpeg f32le decode-to-memory, mirrors embed_extract);
  auto_pick_t_sec() decodes a bounded perf-time search region (skip 60 s head/tail, cap 300 s so a
  2 h show is never fully decoded), builds the TrackCache @22050, scores it, and maps the winning
  window back to perf time (region_start + picked/factor). Blanket-safe: any decode/analysis
  failure logs + returns a fallback t, never blocks a clip request. _resolve_auto_t_sec() analyzes
  the pair's reference source (else lb_a). generate_ab_clips() now takes t_sec: float|None and
  auto-picks when omitted (after the eligibility/recency gates, before the perf-bound check),
  returning the resolved t_sec.
Changed: backend/app.py — POST /api/ab_clip: t_sec is now optional (dropped from missing_fields;
  still 400 bad_t_sec on an unparseable value); omitted -> backend auto-picks. Docstrings updated.
Changed: gui_next ScreenTapeMatch.tsx (AbPlayerPanel) — start field defaults blank ("auto"); blank
  omits t_sec from the POST so the backend auto-picks, and the response's t_sec pre-fills the field
  so the curator can override + reload. New i18n keys tapematch.abPlayer.autoPlaceholder/
  autoPickHint (en + de/fr/es/it/nl via DeepL).
Verified: 37 ab_clips tests pass (4 new: pick_start_frame scorer, None-underflow, generate+route
  omitted-t_sec); real-ffmpeg end-to-end confirms auto-pick lands in a planted quiet-vocal region
  and the factor!=1 perf-time mapping; gui-check (node/renderer types + build) PASS.

[2026-07-14] — feat(backend): TODO-233 part 1 + TODO-232 part 1 — A/B listening: constant-speed-offset eligibility (resampled to reference speed) + RMS level-match
Context: only ~1/3 of sources qualified for A/B listening (reference/aligned only), so most
  ScreenTapeMatch pairs showed "Not cleanly aligned for A/B listening yet". constant-speed-offset
  is the single largest speed bucket (1,854 sources) and its perf->source map is fully derivable
  from the sources table (rate = 1 + speed_ppm/1e6, offset = trim_head_sec) — no run-archive
  parsing needed. speed_ppm confirmed fully populated for those rows; run_id is a sortable
  YYYYMMDD_HHMMSS so the stale-label recency gate is directly expressible.
Added: backend/ab_clips.py — constant-speed-offset added to ELIGIBLE_SPEED_KINDS; speed_factor()/
  raw_take_sec() and a factor arg on source_offset() generalise the perf->source map to
  `trim_head + t*factor` (mirrors embed_extract.py's nominal-time convention); build_clip() now
  extracts the raw dur*factor span, then _finalize_clip() speed-corrects it back to reference via
  `asetrate=44100*factor,aresample=44100` (only above RESAMPLE_MIN_ABS_PPM=50; reference/aligned
  keep the v1 straight cut). RMS level-match (TODO-232 pt1): _measure_rms_dbfs (ffmpeg
  volumedetect) + compute_gain_db normalise every clip to AB_RMS_TARGET_DBFS=-20 with a
  no-clip peak ceiling and a 30 dB max-gain cap. Stale-label recency gate (TODO-233):
  is_run_eligible() rejects speed labels from runs before the 2026-07-06 confidence tightening
  (commit 936e0a64); enforced in generate_ab_clips (409 not_eligible w/ run_id) and mirrored in
  the GET /api/tapematch/pairs ab_eligible enrichment so badges agree with POST. cache_filename
  now keys on speed_ppm too. get_source_info/get_pair_source_info select speed_ppm (PRAGMA-guarded
  for legacy DBs missing the column).
Changed: backend/app.py — ab_eligible enrichment adds is_run_eligible gate; POST /api/ab_clip
  docstring updated for the new eligibility tiers.
Verified: 33 ab_clips + 24 tapematch-route tests pass; real-ffmpeg smoke test confirms a 21 s
  raw clip at factor 1.05 finalises to 20.000 s at the -20 dBFS target under the peak ceiling.
Remaining: TODO-233 pts 2/3 (staircase/splice per-segment offsets; speed-unknown) and TODO-232
  pt2 (auto-pick quiet-vocal start point) stay open.

[2026-07-13] — fix(backend): TODO-213 — taper-attribution curation: exclude non-taper credits (lk/captain acid/jtt/robert), rename cb master→cb, downgrade bare mentions vs confirmed tapers
Context: tj worked the /taper-review conflict queue (68 confirm/reject decisions) and named a
  repeating pattern — NON-TAPER credits (curators / remasterers / transfer engineers) colliding
  with real tapers in a family, which the attribution engine surfaced as bogus conflicts and wrong
  taper-name badges (the specific complaint behind TODO-213).
Changed: backend/db.py — added `lk` (curator), `captain acid` (remaster), `jtt` (transfer/master
  engineer, "Mastered to Digital by JTT") to _NOT_TAPER, so they drop out of _TAPER_UNIVERSE and are
  never seeded as attribution candidates. A mention colliding with a real taper now auto-resolves to
  the real taper with NO conflict / no curation (e.g. LB-1945: ltd via LB-4396 vs captain acid via
  LB-4401 → ltd, conflict cleared). Kept them as _KNOWN_TAPER_ALIASES keys so the parser still
  collapses their spellings to one canonical token. Renamed canonical `cb master`→`cb` (cb is the
  taper; "master" = a master tape from cb). Removed `robert` from _KNOWN_TAPER_ALIASES entirely —
  too generic a bare token, it matched songwriter/personnel credits ("Robert Hunter", "Robert
  Friemark") in setlists (179 of its 198 attributions were false mentions).
Changed: backend/taper_attribution.py _propagate_strong — mention-downgrade rule. A bare `mention`
  (Layer 0's sole non-confirmed tier) no longer raises a conflict against a family's single
  confirmed series-code/explicit taper; per spec §4.2 the strong evidence wins silently and the
  mention member is flood-filled to the confirmed taper. Genuine strong-vs-strong disagreement
  (len(confirmed_tapers) >= 2, i.e. series-vs-series) still conflicts as before.
Data: migrated 185 entry_lineage + 19 taper_confirmations rows (cb master→cb); ran full
  deterministic taper_attribution.recompute() after each rule. Conflict queue 121 (stale 07-09
  snapshot; ~191 on a fresh recompute) → 161 (non-taper credits + cb) → 126 (robert) → 53
  (mention-downgrade). ~1200 spurious attribution rows dropped overall. Remaining 53 = 31
  genuine mention-vs-mention ambiguities (the real /taper-review queue) + 22 series-vs-series
  (tapematch family over-merge, for family-split review). DB backed up to
  data/backups/losslessbob_2026-07-13_221639_pre_todo213_curation.db.

[2026-07-13] — feat(backend+gui): TODO-212 (closes it) — recording-lens pick/curated badges + "any curated pick" view
Added: backend/db.py get_pick_badges() + GET /api/library/badges — flat
  {lb_number: {pickRank, absGrade, curated, taperConfirmed, taperReview}} map. Reuses the exact
  loaders get_performances() uses (so the two lenses can never disagree on a badge); only LBs with
  a signal appear, absent fields omitted. Empty on a fresh install pre-recompute.
Changed: gui_next ScreenLibrary.tsx — the recording lens (sourced from /api/search +
  /api/collection/prefetch, which join none of show_picks/quality/curated_lists/taper_attributions)
  now fetches /api/library/badges and merges it by lb_number client-side, same F4 pattern it already
  uses for TapeMatch families/prefetch (SPEC_INTEGRATION_NOTES.md F4). Rows render ★ recommended,
  curated pills, absGrade (owned), and a confirmed-taper pill that *upgrades* the raw free-text taper
  pill rather than duplicating it. Perf lens gains a combined "Any curated pick" view (curatedAny)
  alongside the per-curator carbonbit/10haaf views. Closes the last two deferred items from TODO-186's
  RANKING phase-4 close.
i18n: library.views.curatedAny added to en.json + de/fr/es/it/nl (DeepL).
Docs: TODO-187 verified complete (no code change) — concert_ranker/LB_KNOWLEDGE.md diffed against
  both live LosslessBob "what-it-means" source pages; all rating/comparison/EAC/notes semantics and
  17 terms / 22 images covered 1:1.

[2026-07-13] — feat(backend+gui): TODO-225 setlist fingerprinting curator review queue
Added: backend/setlist_fingerprint.py — scores an entry's folder tracklist against every Olof
  Björner setlist (olof_songs) to identify shows for entries whose date/location metadata is
  unusable ('various', empty/xx dates, or a location the TODO-221 geocoder filter parked in
  skipped_not_concert); candidates only (not bulk re-dating). Scoring blends entry_coverage,
  order-preservation (longest increasing subsequence of matched positions), and olof_coverage;
  matching reuses db.normalize_title_for_match/titles_match (containment-tolerant, same rule as
  compare_olof_setlist). New setlist_fingerprint_suggestions table (USER-tier, wholesale-
  recomputed per scan, curator dismiss status preserved across rescans). Suggestions only — never
  auto-applied to entries.
Added: backend/app.py — POST /api/fingerprint/scan, GET /api/fingerprint/suggestions, POST
  /api/fingerprint/suggestions/dismiss (curator-gated).
Added: gui_next/src/renderer/src/screens/ScreenFingerprint.tsx — curator review queue at
  /fingerprint (Curator nav group): scan button, status filter (pending/dismissed/all),
  expandable rows showing matched/missing songs, curator-only dismiss. New "fingerprint" Icon,
  nav entry, i18n across all 5 locales.
Added: tests/test_setlist_fingerprint.py — 10 tests (candidate selection, scoring/order,
  scan wholesale-replace + dismissed-status preservation, route + curator gating).
Changed: backend/db.py — _titles_match renamed to titles_match (public; now shared with
  setlist_fingerprint.py, not just compare_olof_setlist).

[2026-07-13] — feat(gui): TODO-158 batch forum posting via pasted LB list
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx — new "Post from list…" button
  opens ForumListModal, letting the user paste/type LB numbers (any separator) instead of
  multi-selecting rows; resolves against the full in-memory collection, shows matched/unmatched
  counts, then reuses the same preview_forum + post_forum sequence as the existing multi-select
  batch flow. Extracted the shared per-item post loop into runForumBatch() so the context-menu,
  toolbar multi-select, and new list-modal paths share one implementation instead of three copies.
Changed: gui_next/src/renderer/src/locales/en.json — added collection.forumList.* strings;
  de/fr/es/it/nl synced via /gui-next-i18n (also swept up unrelated pre-existing translation
  backlog in those five files, ~80-150 strings each, still English before this run).

[2026-07-13] — feat(backend): TODO-157 auto-create torrent + qBittorrent add on forum post
Added: backend/app.py post_forum — when no torrents record exists for the entry (and no
  torrent_id given), generates one via torrent_maker.make_torrent(lb, my_collection.disk_path)
  and adds it to qBittorrent via qbittorrent.add_torrent_from_db, reusing the same
  qbt_host/port/credential resolution as the existing qbt_add route. Runs after the TODO-159
  integrity gate, so a folder that already failed LBDIR verify is never auto-torrented/seeded.
  qBittorrent-add failure is reported (qbt_auto_add in the response) but doesn't block the
  forum post — the .torrent file was still created and can be added manually. Response gains
  torrent_auto_created/qbt_auto_add fields when this path fires.

[2026-07-13] — fix(backend): TODO-159 LBDIR verify gate before forum posting
Added: backend/app.py post_forum — before contacting WTRF, resolves the entry's
  my_collection.disk_path and runs checksum_utils.verify_folder() on it; blocks the post with a
  400 (mismatch/missing counts included) when status is fail or incomplete, so a folder whose
  audio no longer matches its stored checksums (BUG-120) can't be posted undetected. No-op when
  the LB isn't in my_collection.

[2026-07-13] — fix(gui): TODO-108 Collection tab header text overflow + missing i18n
Fixed: gui_next/src/renderer/src/components/table.tsx TH — headers had whiteSpace:nowrap but no
  overflow/textOverflow (unlike TD), so a header label wider than its resized column spilled
  unclipped into the next column instead of ellipsizing. Wrapped header content in a clipped
  inner span; resize-handle hit target unaffected.
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx — "Type"/"Notes" column headers
  were hardcoded English, skipping i18n; now use t('collection.table.type'/'notes').
i18n: de/fr/es/it/nl synced via DeepL for the two new collection.table keys.

[2026-07-13] — docs: TODO-154 closed — r#### filename suffix is not per-recording source info
Investigated: grepped data/site/files/ archive-wide — only 57/7371 *.info.txt attachments carry
  a ".r####." filename suffix, and all 57 share the identical value r9453 across dates 1978-2004
  with no date/taper correlation; the 57 LB numbers cluster tightly in LB-04856..05215 (one
  import/scrape batch). The suffix is a session/collision-avoidance artifact of that batch, not
  a per-recording taper/source catalog id — a DB column would store a constant, not a signal.
  Closed as not-applicable.

[2026-07-12] — fix(gui): TODO-231 A/B player had no audio — missing CSP media-src directive
Fixed: gui_next/src/renderer/index.html — the Content-Security-Policy meta tag whitelisted
  http://127.0.0.1:5174 for connect-src/img-src/frame-src but had no media-src directive, so it
  fell back to default-src 'self' and silently blocked the AbPlayerPanel's <audio src=...> GET
  requests. POST /api/ab_clip (connect-src) succeeded — clips "loaded" fine — but the WAV bytes
  themselves never fetched, so Play produced no sound and no visible error. Added
  media-src 'self' http://127.0.0.1:5174.

[2026-07-12] — feat(backend+gui): TODO-231 (part 2/2, closes it) — A/B player widget
Added: gui_next/src/renderer/src/screens/ScreenTapeMatch.tsx — AbPlayerPanel, rendered next to
  JudgmentPanel when a matrix pair is selected. Position (t_sec) + duration inputs, "Load clips"
  hits POST /api/ab_clip; once loaded, two hidden <audio> elements are started together and stay
  sample-aligned for the clip's fixed duration, so the A/B chip toggle is an instant (un)mute swap
  rather than a reload/reseek. Disabled (inert controls + notEligible pill) when
  pair.ab_eligible !== true. Per-error messaging for the ab_clip failure taxonomy (not_eligible/
  t_out_of_range/folder_missing/locked).
Fixed: backend/app.py tapematch_pairs_for_date — ab_eligible enrichment computed eligibility from
  the (possibly stale) run_id synced into tapematch_pairs, not each pair's actual latest common
  tapematch run; a pair could show ab_eligible: false while POST /api/ab_clip accepted it fine
  (observed live: LB-5953/LB-6162 1995-07-08 — synced run had speed_kind staircase/splice, two
  newer un-synced runs had aligned/reference). Now resolved per-pair via
  ab_clips.get_pair_source_info, the same function generate_ab_clips uses, so the two routes can't
  disagree.
Changed: root adhoc_quality investigation scratch files (adhoc_quality.py/.json, adhoc_report.*,
  adhoc_tapematch.log, build_adhoc_pdf.py) moved to tools/adhoc_quality/; dropped a stray empty
  tools/tapematch/observations.db?mode=ro artifact (accidental sqlite URI-as-filename).
i18n: de/fr/es/it/nl synced via DeepL for the new tapematch.abPlayer.* keys; manually corrected
  three mistranslations of "Position" (fr "Poste", es "Puesto", nl "Functie" — all read as
  employment position, not playback position) to Position/Posición/Positie.

[2026-07-11] — feat(backend): TODO-231 (part 1/2) — LISTENING §2 aligned A/B clip service
Added: backend/ab_clips.py — POST /api/ab_clip {date, lb_a, lb_b, t_sec, dur_sec 5..60} extracts
  two performance-time-aligned WAV clips (16-bit/44.1k/stereo) via ffmpeg from the pair's library
  FLAC folders (my_collection.disk_path; t located across the folder's track sequence via cached
  ffprobe durations, clips may span N adjacent tracks via concat demuxer). Per-source offset =
  t + trim_head_sec from tools/tapematch/observations.db sources. v1 eligibility: both sources
  speed_kind IN ('reference','aligned') — 409 not_eligible otherwise; 404 no-common-run/
  folder_missing (unmounted drive path echoed), 409 locked (obs db write-locked), 400 bad t/dur.
  Clips cached in data/ab_clips/ (gitignored), pruned to newest 40; GET /api/ab_clip/<name> serves.
Added: GET /api/tapematch/pairs rows now carry ab_eligible (live best-effort from observations.db,
  same pattern as human_judgment enrichment; null when db missing/locked).
Fixed (Fable review of agent output, pre-commit): trims for A and B are now taken from the latest
  run containing BOTH sources (get_pair_source_info) — per-source-latest-run selection could mix
  trims from two runs whose performance windows disagree, silently misaligning the pair; clip
  cache key now hashes the post-trim source offset (not raw performance time) so a rerun that
  changes a trim can't serve a stale cached clip.
Tests: 24 in tests/test_ab_clips.py (ffmpeg/ffprobe mocked; offset math, boundary spanning,
  eligibility, cache prune, enrichment, same-run selection). Real-audio smoke test: LB-5953/
  LB-6162 1995-07-08 Munich, 15.0 s clips ffprobe-verified, incl. track-boundary concat path.
Note: part 2/2 (A/B player widget in ScreenTapeMatch + dup-encodes GUI rider) follows.

[2026-07-11] — feat(backend+gui): TODO-230 — LISTENING §3 song-centric index (olof_songs spine)
Added: backend/song_index.py — normalize_song_title (NFKD/casefold/apostrophe-unify/punct-strip),
  song_canonical seeding (most-frequent raw spelling wins; curator rows sticky via
  ON CONFLICT ... WHERE source != 'curator'), song_performances wholesale recompute (empty-replace
  guarded per BUG-246 pattern), upsert_alias, get_songs/get_song_performances queries.
Added: backend/db.py — song_canonical (alias_norm PK, canonical, source auto|curator) +
  song_performances (event_id+position PK, song_norm/song_canonical/concert_date_iso/is_encore/
  take_status/event_type; idx on norm + date) — both USER-tier, never in master export.
Added: tools/compute_song_performances.py CLI (--dry-run); song_index appended as 4th
  feature-detected step of POST /api/derived/recompute (F1 chain).
Added: backend/app.py routes — GET /api/songs?q= (counts + date span + n_dates_with_recordings
  via show_picks), GET /api/songs/performances?song= (venue/city from olof_events; recordings
  {lb_number, pick_rank, abs_grade} via show_picks + latest quality scan; 404 unknown),
  POST /api/songs/alias (curator-gated 403; recompute-on-write).
Added: gui_next ScreenSongs.tsx at /songs (Library nav group) — debounced song search rail,
  performance table (date/venue/event-type pill/take status/encore, LB deep-link buttons with
  pick + grade), date vs best-first sort, curator canonical-rename affordance. i18n songs.* keys,
  5 locales via /gui-next-i18n.
Data: real-DB recompute — 61,707 performance rows, 1,298 songs, 3,994 events (88.1% of all
  olof_events incl. sessions/broadcasts). Verified live: "visions of johanna" → 227 performances
  (220 concerts, 201 dates with local recordings). 13 new tests (tests/test_song_index.py).
Note: canonicalisation table feeds TODO-225 (setlist fingerprinting).

[2026-07-11] — test(backend): un-rot tests/test_geocoder.py (13 failures from TODO-220/224 behavior changes)
Fixed: 6 assertions updated to the (full, city_only) tuple returns introduced by TODO-220
  (9ac938b0); 5 TestRunBatch fixtures gained a blank-field olof_events concert row so the
  TODO-224 (f044dcd2) concert-only eligibility filter passes without adding a competing
  structured source; 3 note assertions updated to the "tried: ..." cascade-log format.
  Tests only — backend/geocoder.py untouched. Suite: 52/52 pass (was 39/52).

[2026-07-11] — feat(backend+gui): TODO-215 (parts 2+3/3, closes it) — crawl run management + LB deep-links
Added: backend/app.py POST /api/tapematch/crawl/start — wraps tools/tapematch/crawl_start.sh
  (optional body min_entries/allow_missing → script flags; the script's pgrep guard stays the
  single-instance authority — 409 already_running when it refuses). POST /api/tapematch/crawl/stop
  wraps crawl_stop.sh (SIGINT, no-op-safe, always 200).
Added: gui_next ScreenTapeMatch.tsx crawl strip — Start/Stop buttons with pending states,
  409-aware error copy (tapematch.crawl.* keys, 5 locales via /gui-next-i18n).
Added: LB deep-links (sub-feature 3): LbLinkButton in matrix headers/cells + family chips
  navigates to /library?lb=<n>; ScreenLibrary consumes the param one-shot (selects the row,
  opens the DetailPanel, clears the param). DetailPanel gains a drag-resizable width
  (useResizableWidth in useResizableColumns.ts, persisted to localStorage) and a horizontally-
  scrollable tab strip so the deep-linked panel never clips.
Tests: 10 new endpoint tests in tests/test_tapematch_routes.py (judgment set/clear/400/404,
  crawl start success/409/400/500, stop success/500; subprocess fully mocked — no real crawl).
Note: TODO-215 closed — TapeMatch screen v2 complete. A/B player + dup-encodes GUI riders
  carry to the LISTENING §2 stream (WORK_PACKAGE_NEXT slot 3).

[2026-07-11] — fix(backend+gui): pipeline severity/state correctness on partial runs, renames and moves
Fixed: backend/app.py — on a partial pipeline run, severity was computed from only the step(s)
  requested this call (others "mute"): _sev_step now folds last-known verdicts from the validated
  folder-state cache, so a re-verify of an already-filed folder keeps "done" instead of being
  demoted, and a lone verify on an unidentified folder is not promoted.
Fixed: gui_next ScreenPipeline.tsx applyRename — a rename promoted rows to "In collection" unless
  the file step was warn; inverted to promote only when file step is ok (rename never files).
Fixed: gui_next ScreenPipeline.tsx file/move — the persisted folder queue kept the old source
  path after a move, re-hydrating as a false "Missing/blocked" on next reload; now swaps in the
  new path (mirrors applyRename).

[2026-07-11] — feat(backend+gui): TODO-215 (part 1/3) — curator match feedback on the TapeMatch matrix
Added: backend/app.py POST /api/tapematch/pairs/judgment — writes human_judgment
  (confirmed_same|confirmed_different|uncertain|lb_wrong, or null to clear) + human_notes
  straight into tools/tapematch/observations.db pairs (opened read-write, unlike the mode=ro
  helper used elsewhere; BEGIN IMMEDIATE + busy_timeout). Vocabulary is authoritative —
  tools/tapematch/regression.py reads confirmed_same/confirmed_different as calibration truth.
  Validation: 400 bad_judgment/missing_fields, 404 no_run/pair_not_found, 409 locked when a
  crawl holds the DB (mirrors the /api/tapematch/analysis 409 pattern).
Added: gui_next ScreenTapeMatch.tsx — matrix cells clickable; a JudgmentPanel below the matrix
  (not a popover — the matrix lives in overflow-x) lets the curator set/clear a judgment + notes;
  judged cells get a tone marker. Saves via the new endpoint + invalidates the pairs query.
Changed: backend/app.py GET /api/tapematch/pairs now enriches each pair with human_judgment/
  human_notes read LIVE (best-effort) from observations.db so edits show without a re-sync.
Fixed: backend/app.py — the enrichment SELECT initially crashed on observations.db pairs rows
  with NULL lb_a/lb_b (single-source rows): sorted((None, int)) raised TypeError, aborting
  enrichment for the whole date so every judgment silently fell back to null. Now filters
  lb_a/lb_b IS NOT NULL in SQL. (Caught pre-commit via end-to-end HTTP verification.)
Note: TODO-215 stays open — sub-features 2 (run start/stop management) and 3 (LB deep-links)
  not yet done. Locales de/fr/es/it/nl updated via /gui-next-i18n.

[2026-07-11] — feat(gui): TODO-226B — About-screen data-source credits (setlist.fm, bobdylan.com, bobserve link)
Changed: gui_next AboutDialog.tsx: TODO-226 Part B — added setlist.fm and bobdylan.com credit
  cards to the Credits tab (after the existing Olof Björner card) and a "bobserve.com · About
  Bob" entry to the About-tab Links list. Ground truth vs. ticket: the Olof/bobserve credit it
  asked to add was already shipped (commit 3b9ca946); the "existing setlist.fm/bobdylan.com
  credits" it referenced did not exist — this fills that real gap. Component is static-English
  constants (no locale keys) so /gui-next-i18n is a no-op. Types + build pass. TODO-226 stays
  open for Part A (BobTalk search + show-page surfacing).

[2026-07-11] — feat(backend+gui): olof_events geocoder source + authoritative concert filter (TODO-224 pts 1–2), geocoder skipped/stopping GUI (TODO-229)
Added: backend/geocoder.py: TODO-224 pt 1 — _get_olof_events_location_string() slotted into
  _STRUCTURED_SOURCES directly after bobdylan_shows: on an entries-date match builds
  "venue, city, region, country" from olof_events' split fields (blank parts dropped) + a
  city-only variant for the TODO-220 cascade; prefers event_type='concert' on multi-event
  dates (mirrors db.compare_olof_setlist tie-break). _table_exists() feature-detects
  olof_events so installs without the Olof scraper degrade to prior behavior.
Changed: backend/geocoder.py: TODO-224 pt 2 — _is_concert_location() now returns
  (eligible, skip_note): an olof_events date match is AUTHORITATIVE (concert → eligible even
  past the keyword blacklist; any other event_type → skipped_not_concert with
  "olof_events: non-concert event_type=<type>" in note); no olof match → original TODO-221
  heuristic unchanged. Pt 3 (gazetteer seeding from olof_events) deliberately deferred to
  TODO-223 with the rest of the gazetteer work.
Added: tests/test_geocoder.py: 12 new tests (olof lookup hit/blank-drop/tie-break/absent-table,
  authoritative eligibility incl. conflict-with-bobdylan_shows case, 2 run_batch end-to-end).
  All 12 pass; 13 pre-existing failures from stale TODO-220/221-era fixtures confirmed present
  before this change (stash-verified) → BUG opened this session.
Changed: gui_next ScreenScraper.tsx: TODO-229 — GeocoderStatus gains skipped/stop_requested,
  GeoStats gains skipped; "Skipped" row in the geocoder Cache Stats grid; StripCard gains an
  optional badge override → geocoder card shows "stopping" while running && stop_requested.
  New scraper.geocoder.* keys in en.json; DeepL pass synced de/fr/es/it/nl (3,409 chars).
  Verified: backend restarted (live /api/geocode/stats serves skipped=31), tsc node+renderer
  0 errors, production build clean.
Added: instructions/WORK_PACKAGE_NEXT.md: queue for post-7/12 windows — LISTENING §3 (song
  index on the olof_songs spine) + §2 (A/B) + TODO-215 next window; TODO-213 standing preempt;
  N+2 slot unassigned (pipeline Phase 7, its original occupant, verified already shipped 07-09).

[2026-07-11] — feat(backend): geocoder stop support (TODO-219), concert-only eligibility filter (TODO-221), cascading Nominatim fallback (TODO-220)
Added: backend/geocoder.py: TODO-219 — stop() sets _progress["stop_requested"] under _lock;
  run_batch() checks it at the top of every location iteration and the 429 backoff sleep is
  sliced (1 s chunks, _StopSignal unwinds into the existing finally). get_progress() exposes
  stop_requested for the GUI badge.
Added: backend/app.py: POST /api/geocode/stop (mirrors /api/bobdylan/stop) — fixes the GUI Stop
  button's silent 404 (ScreenScraper.tsx already posted this path).
Added: backend/geocoder.py: TODO-221 — _is_concert_location(): non-venue keyword guard
  (compilation/outtakes/interview/rehearsal/soundcheck/demos/various) + requires one entry with
  a single clean date matching bobdylan_shows or setlistfm_shows (dylan_performances deliberately
  excluded — it date-matches interviews). Ineligible locations cached as
  source='skipped_not_concert' (lat/lon NULL, never retried, no Nominatim call), counted in new
  _progress["skipped"]; /api/geocode/stats excludes them from failed and reports skipped.
Changed: backend/geocoder.py: TODO-220 — cascading fallback: all structured-source full strings
  (priority order) → venue-stripped city-only variants (source suffix '-city', confidence capped
  at medium) → raw entries.location last; every attempted query recorded in note
  ("tried: <tag>:<query> | …") on success and failure; 1.1 s sleep between every Nominatim call
  incl. fallbacks. Shared _save_geocode_result() extracted for the UPSERT.
Fixed: data: re-ran the 48 source='failed' rows from the 2026-07-10 batch (retry_failed=true,
  limit=48, live-verified on 5174 post-restart): 17 geocoded (9 bobdylan_shows-city,
  1 setlistfm_shows-city, 7 full-string), 31 skipped_not_concert, 0 errors — failed count now 0,
  coverage 69 → 86 locations. Known wart: a non-venue location on a documented show date (e.g.
  "A Hotel Room, Denver" during a Lincoln NE run) passes eligibility and pins to the show's
  city; place_manual() is the escape hatch, gazetteer work (TODO-222/223) will revisit.

[2026-07-11] — feat(backend+scraper): quality-score family corroboration + dup-encode surfacing (TODO-210), crawl hot-loop guard (TODO-227)
Added: backend/tapematch_sync.py: TODO-210a conf bump — _load_latest_abs_scores (per-lb newest
  scored scan, abs_score/abs_grade feature-detected via PRAGMA, degrades to no-op pre-Ranker) +
  _has_quality_match (same scan_id, |Δabs_score| ≤ 0.5, same grade letter); families matching
  get a one-time min(1.0, conf + 0.05) bump in _sync_one_date, logged. Corroboration only —
  investigation showed raw score equality is >99.8% noise for surfacing new families.
Added: backend/tapematch_sync.py: TODO-210b duplicate_encode_candidates() — read-only pairs with
  byte-identical quality_recording_metrics.metric_json within one scan_id, grouped by
  entries.date_str (not via recording_families — the interesting leads aren't in families yet);
  never auto-merges. CLI: python -m backend.tapematch_sync --dup-encodes.
Added: backend/app.py: GET /api/tapematch/dup_encodes → {"candidates": [...]}. Live-verified on
  5174 post-restart: 15 pairs / 13 metric-identical groups incl. investigation's LB-3136/7538 +
  LB-3147/7523 (same_family=False) — GUI surfacing rides TODO-215 (TapeMatch screen v2).
Added: tools/tapematch/run_crawl.sh: TODO-227 failure guard — non-continue rc sleeps 30 s; 3
  consecutive failures on the same date append it to data/tapematch/crawl_skip.txt and move on;
  10 consecutive failures overall abort (systemic). Also fixed latent stale-$rc bug (rc never
  reset on success — would have cascaded false failures once the guard existed). Replaced via
  mv (new inode); the live crawl keeps its old copy until next restart.
Changed: tools/tapematch/tapematch_session.py: next_run() honors crawl_skip.txt (ISO date per
  line, # comments; prints skipped count) and writes the attempted date to
  crawl_last_attempt.txt before run_date so the shell guard knows what failed.
Changed: tests/test_tapematch_sync.py + tests/test_tapematch_routes.py: 26 new tests (bump
  apply/degrade/clamp, dup-encode grouping, route). Suite 607 passed / 5 skipped.

[2026-07-10] — feat(backend+gui): Olof P5 — surfacing: endpoints, tour-name fallback, setlist compare, GUI panel (FABLE_OLOF_FILES §5–§6; closes TODO-162 + TODO-153; Olof spec complete)
Added: backend/db.py: get_olof_date/get_olof_event/get_olof_chronicle_year/get_olof_status
  readers (all degrade to empty — olof_* stays local-only, NOT in MASTER_TABLES; export tier
  deliberately deferred as a redistribution-rights question); normalize_title_for_match (reuses
  checksum_utils apostrophe fold) + conservative containment matcher; parse_entry_setlist_titles
  (entries.setlist free-text tracklists, 11,796 rows); compare_olof_setlist order-independent
  greedy matcher returning matches/missing/match_pct + recording info for duration sanity.
Added: backend/app.py: GET /api/olof/date/<date>, /api/olof/event/<id>, /api/olof/chronicle/<year>,
  /api/olof/status; POST /api/olof/compare ({date_str, titles[] | lb_number}).
Changed: backend/db.py get_performances(): tour-name fallback chain setlistfm → olof_events
  (TODO-153) — setdefault so setlistfm wins, concert rows preferred; dated shows with a tour
  name 3,783 → 4,540 (+757; e.g. 1974-01-03 "Tour '74").
Added: gui_next DetailPanel.tsx: Olof tab on both library lenses — setlist (encore pills, cover
  credits, annotations, take status), NET/year concert #s, recording info, notes, BobTalk quote,
  chronicle entries, circulation provenance, per-copy setlist comparison (match %, missing
  titles, expected minutes). Gated on /api/olof/status events>0 (react-query staleTime Infinity).
Changed: gui_next AboutDialog.tsx: Olof Björner / bobserve.com acknowledgement card (TODO-226
  part B; part A remainder — BobTalk full-text search — stays open on TODO-226).
Changed: locales: 15 new library.olof.* + tabOlof keys; de/fr/es/it/nl via /gui-next-i18n
  (DeepL, 4,857 chars). /gui-check PASS (node+renderer tsc 0 errors, build clean).
Changed: instructions/FABLE_OLOF_FILES.md → instructions/complete/ (all P1–P5 shipped);
  instructions/README.md row removed. Verified live on 5174 post-restart (status counts,
  1990-05-29 panel data, compare normalization smoke test).

[2026-07-10] — feat(scraper): Olof P4 — Yearly Chronicles parser → olof_chronicle + olof_new_tapes (FABLE_OLOF_FILES §6; TODO-162 P4)
Added: backend/db.py: olof_chronicle + olof_new_tapes tables + date indexes (spec §4).
Added: backend/olof_chronicle_parser.py: chronicle corpus parser — heading-based section
  location tolerant of ~50 years of Word export drift, calendar diary entries (date-heading
  shapes: 'D Month', 'Month D', day lists/ranges, Early/Mid/Late), 'New tapes & bootlegs'
  subsections with ISO show-date from title, XE/PAGEREF field-junk stripping, per-year
  delete+reinsert idempotency, olof_pages bookkeeping, CLI mirroring olof_parser.
  Full-mirror parse: 1,244 olof_chronicle rows (43 years), 79 olof_new_tapes (17 years),
  253 pages ok / 2 partial / 0 error; 11 years are PDF-only stubs on Olof's site.
  DSN data untouched (4,533 events / 61,708 songs); rerun idempotent; junk-free (SQL check).
Changed: backend/olof_parser.py: extracted _split_city_region_country, corpus/year params on
  _ensure_page_row — shared with the chronicle parser, DSN behavior unchanged.
Note: 2022+ appendix setlist path (synthetic year*1000+seq event IDs) implemented but dormant —
  bobserve.com publishes 2013+ chronicles as PDF only (2016 excepted), so 0 synthetic events;
  structurally validated on 2002 A.htm incl. spec §7 malformed headers. TODO-228 opened for
  PDF fetch + extraction. Riders NOT parsed (deferred per spec §8): tour stats, uncirculated.
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof row updated — P4 done, next P5.

[2026-07-10] — feat(scraper): Olof P3 — DSN song/take parser → olof_songs (FABLE_OLOF_FILES §6; TODO-162 P3)
Added: backend/db.py: olof_songs table (event_id+position PK, title, cover credits, is_encore,
  take_number/status, annotations, released_on) + idx_olof_songs_title (spec §4).
Added: backend/olof_parser.py: song/take rows threaded through the P2 pipeline — combined
  ("N. Title (credits)") and split-cell session layouts, take statuses (incl. bare-status
  source quirk), encore separator, annotation/release position-range resolution with
  lineup-line guard, duplicate-position renumbering (Olof numbering slips), delete+reinsert
  idempotent upsert; coverage report extended (songs_emitted, % concerts with songs).
  Full-mirror parse: 61,708 song rows; 97.8% of concerts / 95.1% of sessions with ≥1 row.
  Gate: DSN01225 17/17 takes with statuses; DSN11050 19/19 titles match setlistfm bd4a956,
  encore + credits + annotation ranges correct; P2 event coverage byte-identical (4,533
  events), page ok/partial split unchanged. Known soft spot: "released in <country> on …"
  phrasing lands in annotations, not released_on (documented in module).
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof row updated — P3 done, next P4.

[2026-07-10] — feat(scraper): Olof scraper P1+P2 — bobserve.com mirror + DSN event parser (FABLE_OLOF_FILES §6; TODO-162 P1–P2) + tapematch crawl merged-folder crash fix
Added: backend/olof_fetcher.py: verbatim byte mirror of Olof Björner's Still On The Road +
  Yearly Chronicles (browser UA for Cloudflare, ≥2 s throttle, resume-safe skip/backfill,
  --corpus/--limit/--refresh/--dry-run). Full mirror fetched: 471 pages (214 DSN + 257
  chronicle), 324 MB, 0 errors → data/olof/pages/.
Added: backend/olof_parser.py: DSN event parser — windows-1252 Word-HTML, per-paragraph line
  joining, <a name=DSNnnnnn> segmentation; extracts date/venue/city/region/country, NET +
  year concert #, recording kind/mins, notes, BobTalk, releases, raw_text; event_type
  heuristic; coverage report. Full DSN corpus: 4,533 events (99.7% anchor→event, 95% ISO
  date; concert 3,879 / session 205 / broadcast 91 / interview 63 / rehearsal 6 / other 293).
  5-date archive spot-check passed (incl. 1966-05-17 Manchester vs "Royal Albert Hall" label).
Added: backend/db.py: olof_pages + olof_events tables + date/tour indexes (spec §4).
Fixed: tools/tapematch/tapematch_session.py: copy_folders() crashed on merged folders (two LB
  ids sharing one directory, e.g. "… (LB-05034 + LB-07279)") — FileExistsError crash-looped
  the detached crawl ~3 h on 2000-03-12; now dedupes by source path and skips already-copied
  folders. Crawl verified resumed (2000-03-13…16 processed).
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof P1+P2 row added to Phase 2 timeline.

[2026-07-10] — docs: ONBOARDING P4 — README rewrite, retires PyQt flow docs (spec §6; closes TODO-218; ONBOARDING spec complete)
Changed: README.md: full rewrite — quickstart = Releases installer (AppImage / windows-Setup.exe,
  verified against v1.5.2 assets) + first-run wizard; data-model table (master release vs
  sitedata release vs monthly flat file, curator-only scraping note); dev setup (.venv,
  run_backend.py, gui_next npm run dev, dist:linux/win) + PROJECT.md pointer. Kept the
  flat-file + checksum format reference sections. Dropped: python main.py install, manual
  Setup-tab flat-file first-import, PyQt tab feature list, Map/WebEngine + PyInstaller sections.
Changed: instructions/FABLE_ONBOARDING_SYNC.md → instructions/complete/ (all P1–P4 shipped);
  instructions/README.md row swapped for new FABLE_OLOF_FILES.md entry.

[2026-07-10] — feat(gui): ONBOARDING P3 — first-run wizard + Home setup checklist + Setup/Scraper copy (spec §5–§6; closes TODO-217)
Added: gui_next/src/renderer/src/components/OnboardingWizard.tsx: 4-step first-run modal
  (1 master github_check/install SSE — required to proceed; 2 sitedata core/files checkboxes
  → sitedata github_install SSE; 3 navigation-only Mounts/Pipeline links; 4 summary +
  auto-fired POST /api/derived/recompute per SPEC_INTEGRATION_NOTES F1, per-step status list).
  Skip always available; controlled component — ScreenHome owns show/hide.
Added: gui_next/src/renderer/src/screens/ScreenHome.tsx: auto-opens wizard once per launch
  when onboarding/status entries_count==0 (sessionStorage dismiss flag set on Skip/Finish);
  setup-checklist card while complete==false — one row per unmet item (master, sitedata core,
  mounts, collection scan), each reopening the wizard at the right step or navigating.
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: flat-file card reworded to
  "Monthly update" framing (spec §6 demotion — no first-run role, copy only).
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: curator-only banner note
  (end users get scraped data via master + site-data releases).
Changed: gui_next/src/renderer/src/locales/*.json: ~45 new keys (onboarding.*,
  home.setupChecklist.*, scraper.curatorNote, setup.flatFile.*) — de/fr/es/it/nl via DeepL
  (10,294 chars); the 3 residual "gaps" are identical-in-target words (Version/Open), benign.
Verified: tsc node+web 0 errors (ScreenScraper baseline errors no longer present), vite build
  PASS.

[2026-07-10] — feat(backend): ONBOARDING P2 — sitedata github_check/github_install + onboarding/status (spec §3–§4; commit a9759209; closes TODO-216)
Added: backend/app.py: GET /api/sitedata/github_check — latest sitedata-* release, per-part
  (core/files) zip discovery by _core_/_files_ substring (collision-suffix tolerant, per P1's
  _2 core asset) paired with .manifest.json sidecars; parts missing a sidecar are omitted.
Added: backend/app.py: POST /api/sitedata/github_install (SSE, same event shapes as master
  install) — body {parts:[core|files]}, default core; downloads to data/imports/, verifies
  SHA256 against manifest BEFORE extraction (mismatch deletes zip + errors, site dir
  untouched), extracts into data/site/ via shared _restore_sitedata_zip (clean overwrite),
  writes .sitedata_<part>_manifest.json marker for cheap status reads.
Added: backend/app.py: GET /api/onboarding/status — {entries_count, master_version,
  sitedata_core_present, sitedata_files_count, mounts_configured, collection_count, complete};
  complete = entries ∧ master_version ∧ ≥1 mount. Live-verified: 63 ms (<100 ms spec target),
  github_check pairs both parts of the real sitedata-2026-07-10 release.
Changed: backend/app.py: /api/package/restore site-extraction path deduped into
  _restore_sitedata_zip; embedded-manifest types sitedata_core/sitedata_files now accepted.
Added: tests/test_sitedata_packaging.py: 7 P2 tests (mocked GitHub releases API + SSE stream
  parsing: check pairing, sha mismatch aborts pre-extraction, success + marker, invalid part,
  restore manifest types, onboarding status empty/populated) — 15/15 pass.

[2026-07-10] — feat(backend): ONBOARDING P1 — site-data split packaging + first sitedata GitHub release (spec §3; commit 55501726)
Added: backend/app.py: _package_site_data(part) — core (everything but files/) / files (files/
  only) / None (legacy whole-tree) zips of data/site/ with .manifest.json sidecars (type,
  created_at, file_count, total_bytes, sha256 — master manifest convention; new types
  sitedata_core/sitedata_files). POST /api/package/scrape_data grew ?part=core|files, no-arg
  callers (ScreenSetup, gui/setup_tab.py) keep the old whole-tree behavior. New
  POST /api/sitedata/github_release (curator, SSE) mirrors master_github_release: builds both
  zips + manifests, creates sitedata-<date>[.N] release, uploads 4 assets with progress.
Added: tests/test_sitedata_packaging.py — 8 tests (part selection, manifest sha256/counts,
  invalid part, curator gate); full suite 581 pass.
Changed: first sitedata release published to kuddukan42/losslessbob: tag sitedata-2026-07-10,
  core 24.9 MB (16,829 files) + files 187 MB + 2 manifests. Core asset carries a _2 filename
  suffix (collision counter vs a same-day smoke-test zip) — P2 discovery must match assets by
  _core_/_files_ pattern + manifest pairing, not exact filename. Verified: core zip sha256
  matches manifest, zero site/files/ entries in core.
Changed: ledger: TODO-216 (P2 endpoints, High — next session), TODO-217 (P3 wizard, Medium),
  TODO-218 (P4 README, Low) opened per the spec's allocate-at-first-session rule. PROJECT.md:
  show_picks schema corrected (concert_date is raw M/D/YY, + concert_date_iso column/index),
  picks date/tonight routes + Site-Data Packaging routes documented.

[2026-07-10] — feat(backend+gui): LISTENING §9 "tonight card" — concert_date_iso + picks date endpoints + Home card (spec step 6 complete)
Added: concert_ranker/picks.py: _parse_concert_date_iso() — M/D/YY→ISO reconciliation of
  show_picks.concert_date (two-digit year pivot 30, any 'xx' component → NULL); populated on
  every recompute. Live DB: 14,618/15,204 rows ISO-dated (586 NULL = 'xx' unknown-date entries,
  by design). Satisfies TODO-212's deferred GET /api/picks?date= item (TODO-212 stays open for
  the Recording-lens badges + combined curated view).
Added: backend/db.py: show_picks.concert_date_iso column (idempotent PRAGMA-guarded migration)
  + index. backend/app.py: GET /api/picks?date=YYYY-MM-DD exact-date filter and
  GET /api/picks/tonight — month-day match across all years (?mmdd=MM-DD override), returns
  ranked candidates. tests/test_picks_tonight.py (parser + endpoint coverage; suite 573 pass).
Added: gui_next ScreenHome.tsx "Tonight in Dylan history" card (right column, above Tips) —
  one random candidate from /api/picks/tonight (long-form date, rating pill, LB number,
  location, truncated description) + shuffle button (non-repeating; hidden when single
  candidate). Card fully hidden on fetch failure/empty. No deep-links (→ TODO-215). i18n:
  home.tonight.* en + DeepL de/fr/es/it/nl (3,639 chars). gui-check: node+web tsc 0 errors,
  production build clean.
Note: BUG-246 detour committed earlier in this slot (73266f6b, see 07-10 entry below); bug
  stays open for the db_path-writer audit (tapematch_sync, parse_lineage, taper_attribution,
  scrapers). Backend commit 70392d14, frontend 09e57b11. WORK_PACKAGE Phase 2 slot 1 done.

[2026-07-10] — fix(backend): BUG-246 — guard show_picks wholesale write against DB-path splits (73266f6b)
Fixed: live show_picks table found wiped (0 rows) at session open; root cause: a writer taking
  an explicit db_path could target a different DB than the queue-backed connection, letting the
  wholesale DELETE phase land without the INSERT phase. Guards added: empty-replace guard
  (refuse to replace non-empty table with 0 rows), path-mismatch direct write, queue re-init
  warning. 2 regression tests. Data restored via tools.compute_show_picks: 15,204 picks /
  4,031 dates. BUG-246 stays open for the same-class audit of other db_path-taking writers
  (tapematch_sync, parse_lineage, taper_attribution, scrapers).

[2026-07-10] — feat(backend+gui): LISTENING §1 pairs sync + TapeMatch screen v1 (closes TODO-170; work-package stretch slot)
Added: backend/tapematch_sync.py: sync_tapematch_pairs() — slim per-pair mirror of
  observations.db pairs into new USER-tier tapematch_pairs table (db.py schema + USER_TABLES;
  PK (concert_date, lb_a<lb_b), latest-complete-run-per-date via _pick_best_run, wholesale
  DELETE+INSERT per date so rows never blend two runs). similarity_pct() banded monotone blend
  calibrated 2026-07-10 against verdict distributions from 10,369 real pairs (same-family
  renders 85–100 from max(corr,emb) terms, different-family 0–40 from emb (corr fallback),
  both-NULL different-family → NULL = "n/c"). CLI _main() now syncs families then pairs.
  Live sync: 9,037 pairs / 1,094 dates, 0 errors; bands verified (diff mean 8.7, same mean 92).
Added: backend/app.py: POST /api/tapematch/sync chains families→pairs (existing keys unchanged;
  pairs_synced/pair_dates merged in). New GET routes: /api/tapematch/pairs?date= (per-date
  matrix rows), /api/tapematch/analysis?date= (best run's analysis.md text + parsed verdict;
  409 when observations.db locked), /api/tapematch/crawl/status (pgrep + runs-dir counts +
  log tail, read-only), /api/tapematch/dates (left-rail summary: n_lbs/n_pairs/has_analysis/
  needs_review/location). Fixed during review: dates location lookup joined ISO concert_date
  against US-format entries.date_str (matched 0/1,094 rows) — now resolves via the date's LB
  numbers; fixture date_str made US-format so a regression fails the test. 35 tapematch tests
  (tests/test_tapematch_sync.py + new tests/test_tapematch_routes.py); full suite 560 pass.
Added: gui_next ScreenTapeMatch.tsx (route /tapematch, Library nav group, existing tapematch
  icon) — tj-approved sketch built as-is: date rail (all/conflicts/no-analysis views, date+
  location text filter, analysis ✓ / needs-review ⚠ marks), per-date similarity-% matrix
  (color-mix heatmap tint on theme tokens, raw corr/emb/fp + verdict in cell tooltip, n/c for
  never-compared, diagonal —), family chips (F1/F2… by lowest LB from /api/tapematch/families
  fam_id groups), collapsible lazy-fetched analysis.md <pre> viewer, crawl status strip
  (30 s poll). Read-only v1 — no run controls or pair corrections (→ TODO-215). i18n:
  tapematch.* namespace + nav key, en + DeepL de/fr/es/it/nl (5,131 chars; residual gaps are
  benign identical-form strings). gui-check: node+web tsc 0 errors, production build clean.
Changed: ledger: TODO-170 closed (v1 shipped), TODO-215 opened (v2 remainder: pair
  corrections into observations.db, run start/stop, LB deep-links pending an in-app
  deep-link mechanism). WORK_PACKAGE_2026-07-09 stretch slot done.

[2026-07-09] — feat(backend+gui): TAPER phase 2 shipped — curator confirm/reject API, Library taper pill + filters, DetailPanel Taper tab (closes TODO-173)
Added: backend/taper_attribution.py: phase 2 curator API functions — confirm()/reject() write
  sticky MASTER taper_confirmations rows (upsert on lb_number PK, F2) and apply the decision to
  taper_attributions immediately, recompute-equivalent (confirm reuses _confirmed_row's shape via
  extraction from _apply_confirmations; reject uses _apply_rejects' pair-match rule so an
  unrelated attribution is never deleted while the suppression still lands). get_attribution_for_lb(),
  list_attributions() (confidence/taper/conflict filters), _resolve_taper() (explicit taper or
  sourced from existing row; confirm validates against _TAPER_UNIVERSE).
Added: backend/app.py: GET /api/tapers/attributions/<lb> (200 with attribution:null when absent),
  GET /api/tapers/attributions?confidence=&taper=&conflict=1 (spec §5 list), and curator-gated
  POST .../confirm + .../reject (400 on unresolvable taper). 11 new tests in
  tests/test_taper_attribution.py incl. _AppClient route tests (535 pass).
Added: backend/db.py: get_performances() F4 payload extension — optional taperConfirmed
  (confidence='confirmed' only, per spec §7 "no pill below confirmed") and taperReview
  (propagated/inferred/conflict) via _load_taper_attributions() single pre-fetched map,
  feature-detected for pre-attribution DBs.
Added: gui_next ScreenLibrary.tsx: confirmed-taper pill (collapsed + family-member rows) and two
  filter views ("Confirmed taper", "Taper: needs review" — the spec's review queue) with counts,
  mirroring the RANKING filter pattern. Heuristic recording-lens taper_name badge untouched (TODO-212).
Added: gui_next DetailPanel.tsx: Taper tab (TaperZone) — tier/conflict pills, taper Fact, shared
  EvidenceList, lazy fetch; confirm/reject buttons gated on curatorMode (TODO-160 convention),
  response pushed into the React Query cache. i18n: library.taper.* / views/tab keys, en + DeepL
  de/fr/es/it/nl (4,039 chars). gui-check: node/renderer tsc 0 errors, build clean.
Added: backend/db.py: get_performances() payload extension (F4 pattern — flat fields, no N+1):
  each recording gains optional pickRank (show_picks), absGrade (latest quality scan,
  PRAGMA-feature-detected), curated (list names). New delete_curated_list(),
  get_show_pick_for_lb(), 3 loader helpers.
Added: backend/app.py: GET/POST /api/curated_lists + DELETE /api/curated_lists/<name>
  (POST/DELETE curator-gated) — TODO-181 remainder; GET /api/picks/for/<lb> (evidence for
  DetailPanel, 204 pre-recompute). tests/test_library_picks_api.py (6 tests).
Added: gui_next EvidenceList.tsx — the one shared {kind, detail, points} evidence renderer
  (F3), reused by taper/listening specs later. DetailPanel: Picks tab (rank/score Facts +
  EvidenceList, lazy fetch), star/grade/curated badges in identity block + family MemberRow.
  ScreenLibrary: badges on performance-lens rows; 4 new Views filters (recommended,
  superseded, carbonbit's, 10haaf's); fixed latent bug where DetailPanel read the un-merged
  recording-lens row (mergedRowsByLb). i18n: 13 new keys, all 5 locales DeepL'd (3,992 chars).
Changed: ledger: TODO-181 + TODO-186 closed (phase 4 closes both per spec §7); TODO-212 opened
  (flat recording-lens badges + 'any curated pick' view + /api/picks?date= — the deferred
  remainder). FABLE_UNIFIED_RANKING.md retired to instructions/complete/ (all 4 phases done).
Changed: tools/tapematch: TODO-201 batch-1+2 FLIPs (83, tj-approved) applied via new
  make_regression_set_v3.py → regression_set_v3.json (positives 1578→1495, negatives
  1387→1470, total conserved; flip list embedded as v3_flips; v1/v2 untouched). Rescoring
  deferred — calibration frozen this window. FN_LABEL_REVIEW.md + CALIBRATION_PROGRESS.md
  updated. TODO-201 stays open (136 duration-only pairs + 8 UNSURE).
Verified: 34 backend tests pass (525 full suite per implementing agent); tsc node + web clean
  (0 errors, better than 14-error baseline); production build clean. tj visual eyeball:
  badges render, but derived DATA needs curation ("lots of obviously wrong badges but more
  are accurate") → TODO-213 (High) opened — collect wrong-badge examples, trace via the Picks
  tab's evidence trail, then weight-tune picks.py §4 terms. Pipeline itself signed off.
Fixed: backend/db.py: extract_taper_and_source() rule-12 short-handle heuristic captured
  quality/broadcast descriptor phrases ("mono", "poor sound", "dylan radio special hilversum3")
  as taper_name — stopword list didn't cover them (BUG-245). Tightened stopwords; added "poor
  sound"/"mono" to _NOT_TAPER. Added is_known_taper()/_TAPER_UNIVERSE (shared with
  taper_attribution.py, which now imports rather than recomputes it) and a taper_known field
  on every /api/search row, so the recording-lens grid pill and the DetailPanel Taper tab check
  the same curated universe instead of disagreeing. (TODO-212 is unrelated/still open — that's
  pickRank/absGrade/curated payload parity, not this taper pill.)
Changed: gui_next ScreenLibrary.tsx: taper pill now gates on row.taperKnown (backend
  is_known_taper()) in addition to the existing NON_TAPER_LABELS dedup, so unvalidated
  free-text guesses never render as an authoritative-looking pill.

[2026-07-09] — feat(backend): TAPER phase 1 + RANKING phase 2 — taper attribution engine, show picks, chained recompute endpoint
Added: backend/taper_attribution.py: taper attribution engine (FABLE_TAPER_ATTRIBUTION phase 1) —
  harvests evidence from entry_lineage / _KNOWN_TAPER_ALIASES / recording_families and writes
  per-LB designations with confidence tiers (confirmed/propagated/inferred), evidence_json audit
  trail, and conflict flagging. Live run: 7,817 attributions (2,643 confirmed / 5,174 propagated /
  168 conflicts flagged for curator review). tools/attribute_tapers.py CLI wrapper (run()/main,
  --dry-run). tests/test_taper_attribution.py.
Added: concert_ranker/picks.py: per-date "best of show" pick scoring (FABLE_UNIFIED_RANKING
  phase 2, §3/§4 model) over entries.rating, curated_lists, entry_lineage,
  quality_recording_scores, and taper_attributions (F5: attribution runs first so the taper
  reputation term sees fresh rows). tools/compute_show_picks.py CLI wrapper. Dry run against the
  real DB: 15,204 picks over 4,031 dates (median score 85.7). tests/test_show_picks.py.
Added: backend/db.py: new tables — taper_confirmations (MASTER, sticky curator confirm/reject
  decisions per SPEC_INTEGRATION_NOTES F2; curator API lands in TAPER phase 2),
  taper_attributions + show_picks (USER, derived, recomputed wholesale, never exported).
  MASTER_TABLES/USER_TABLES updated accordingly.
Added: backend/app.py: POST /api/derived/recompute — SSE-streamed chained recompute
  (parse_lineage → attribute_tapers → compute_show_picks) per SPEC_INTEGRATION_NOTES F1,
  replacing the ranking spec's standalone /api/picks/recompute; steps skip gracefully when a
  later phase's module isn't importable. Manual trigger only, not curator-gated (USER-tier
  output only).
Changed: tools/tapematch/FN_LABEL_REVIEW.md: TODO-201 batches 1+2 — 128 of 264 census-flagged
  pairs reviewed (83 FLIP / 37 KEEP / 8 UNSURE). Pending tj sign-off, flips would shrink the
  corr<0.05 FN population 830 → ~747. Remaining 136 duration-only pairs need a
  partial/incomplete-set judgment method (future chip); TODO-201 stays open.

[2026-07-09] — feat(tapematch): library crawl launched + analysis auto-triage; backlog consolidation
Added: tools/tapematch/crawl_start.sh / crawl_stop.sh / crawl_status.sh: detached single-instance
  wrapper set around run_crawl.sh, log at data/tapematch/crawl.log. Full-library crawl launched
  2026-07-09 over the 2,232 remaining eligible dates (954 of 3,306 ≥2-recording dates done at launch).
Added: tools/tapematch/triage_analysis.py: classifies the missing-analysis.md backlog into
  AUTO / ESCALATE / SKIP(incomplete); auto-writes gen_analysis-template analyses (honest
  "auto-triage" attribution line) only for complete all-distinct runs whose diagnostics are limited
  to [DISTINCT SOURCE]/[INCOMPLETE] and whose commentary raises no in-set pair notes. First pass:
  395 pending → 11 auto-written, 329 escalated to /tapematch-batch, 55 skipped incomplete.
  backend.tapematch_sync ran after: 892 dates, 2,902 families, 3,743 recordings linked, 0 errors.
Changed: instructions/: CC_TAPEMATCH_ADDON, CC_TAPEMATCH_FIXES, TAPEMATCH_PLAN, CC_WEB_GUI_PLAN
  retired to complete/ (efforts concluded / TODO-050..066 all shipped); README.md index updated.
  WORK_PACKAGE_2026-07-09.md added — agreed 7/09–7/12 window plan (tapematch calibration FROZEN,
  spec-pack order per SPEC_INTEGRATION_NOTES §2, TapeMatch screen as stretch goal).
Changed: ledger: TODO-182 closed (superseded by FABLE_UNIFIED_RANKING §5), TODO-203 closed
  (Tier C rejected twice; frozen), TODO-204 and TODO-209 annotated as deferred past the window.
Changed: tools/tapematch/CLAUDE.md: crawl wrapper + triage-before-batch conventions documented.
  .gitignore: observations.db-shm/-wal + tools/tapematch/tmp/ (live-crawl artifacts).

[2026-07-09] — feat: TODO-146 + TODO-171 + TODO-083 — flac.exe bundling, TapeMatch DB Editor, export column picker
Added: tools/flac.exe + tools/libFLAC.dll: bundled Windows FLAC 1.5.0 (Win64) binaries.
  backend/sox_utils.py: _find_flac()/get_flac() probe bundled tools/flac.exe (PyInstaller
  frozen + dev tree) before PATH/WSL, mirroring checksum_utils._find_shntool(). Wired into
  /api/spectrogram/check so flac shows green on fresh Windows installs with zero user setup.
  losslessbob.spec + losslessbob_backend.spec updated to bundle both files (TODO-146).
Added: backend/paths.py: TAPEMATCH_DB_PATH → tools/tapematch/observations.db. backend/app.py:
  _DBEDIT_READONLY_DBS map generalizes _dbedit_db_path()/_dbedit_is_batchverify() (was
  batchverify-only) to also resolve "tapematch", read-only, reused by dbedit_query()'s ?db=
  param too. gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: DB picker widened from a
  2-way to a 3-way losslessbob/batch_verify/tapematch toggle (TODO-171).
Added: backend/app.py: collection_export_html() now accepts ?cols= (validated against a new
  _EXPORT_COLUMN_DEFS registry: lb/status/date/location/folder/notes plus disk_path/
  confirmed_at/source_type/lb_category/rating), always including lb. The exported HTML's
  thead/row-rendering/CSV-export/search/sort JS was converted from hardcoded 6-column markup
  to a data-driven COLS array injected via a new __COLS_JSON__ placeholder.
  gui_next/src/renderer/src/screens/ScreenCollection.tsx: new ColumnPickerModal (checkboxes
  for the 5 extra fields) + "Columns…" button next to Export HTML (TODO-083).
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: synced via DeepL for the
  new collection.columnPicker.* keys plus a pre-existing backlog of stale strings per locale
  unrelated to this session (nav labels, table headers) that DeepL picked up on this run.

[2026-07-09] — feat(gui): TODO-151 + TODO-152 + TODO-161 + TODO-148 + TODO-163 + TODO-164 — Pipeline/Scraper/Library polish batch
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile's success branch now
  updates the row's folderPath/id to the post-move result.dest (previously only rename did this),
  so the detail panel's Open button no longer resolves the pre-collect path (TODO-151). Same
  branch now clears the row's selected flag on transition to bucket 'done', so bulk-filing no
  longer leaves finished rows checked (TODO-152).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: the row action column always
  renders a fixed-size Button now — enabled Apply/File/Done pill when actionable, a disabled
  placeholder otherwise — instead of leaving blank space until the row becomes actionable
  (TODO-161).
Added: gui_next/src/renderer/src/lib/scraperLogStore.ts: module-level zustand store (not
  localStorage-persisted) holding the Scraper screen's per-tab live log lines.
  gui_next/src/renderer/src/screens/ScreenScraper.tsx: switched from local useState to this
  store so the log buffer survives the screen unmounting when the user navigates to another tab
  and back (TODO-148).
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: AssetStripZone's
  attachments pill now opens an inline popover listing each cached attachment's name (clickable,
  opens via window.api.openPath against data_dir from /api/db/settings), plus a "View all in
  Attachments" link — reuses ScreenLibrary's existing attachments-cached query key so no extra
  network request (TODO-163).
Added: gui_next/src/renderer/src/lib/tokens.ts: ThemeOptions.highContrast — applyTheme()
  brightens --lbb-fg/-fg2/-fg3 on dark themes when enabled (no-op in light mode).
  gui_next/src/renderer/src/screens/ScreenThemes.tsx: toggle added to the Advanced card,
  disabled outside dark mode (TODO-164).
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: synced via DeepL for the two
  new keys (library.assets.viewAll, themes.advanced.highContrast) plus a pre-existing backlog of
  ~90-124 stale strings per locale unrelated to this session (nav labels, table headers) that
  DeepL picked up on this run.

[2026-07-09] — feat(gui): TODO-169 + TODO-192 + TODO-168 + TODO-180 — Home/Library/AppShell UI cleanup batch
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: removed the Hero ingest card and the
  now-dead STEP_STRIPS constant; reflowed "At a glance"/"Jump to" into a 2-column grid to fill
  the freed width (TODO-169).
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: taper_name badge inline in the
  Location column of the recording-lens table, gated by a NON_TAPER_LABELS blocklist (master,
  sbd, bootleg, soundboard, audience, ald, mixed, incomplete, unknown, n/a) so generic
  source-type words parsed into taper_name by the free-text parser don't show as fake taper
  handles. No backend change — /api/search already returns taper_name (TODO-192).
Added: backend/app.py: GET /api/credentials/wtrf returns the stored WTRF username only (never
  the password). gui_next/src/renderer/src/components/AppShell.tsx: sidebar identity now shows
  the real username/initials instead of the hardcoded "rolling.thunder"/"RW", falling back to a
  new appShell.noWtrfAccount blank-state string when no WTRF credential is configured. Removed
  the dead appShell.user/userSub locale keys, which were never referenced (TODO-168).
Added: backend/filer.py: _compute_collection_size()/start_collection_size_scan_async()/
  get_collection_size_stats() — sums on-disk bytes across all my_collection folders, cached in
  meta (collection_size_bytes/_folders/_computed_at) and refreshed via a background thread when
  >24h stale (COLLECTION_SIZE_STALE_HOURS) rather than walking ~16k folders synchronously per
  request. Wired into GET /api/home/stats as collection_size {bytes, human, folders,
  computed_at, computing}; surfaced in the AppShell footer stats bar (TODO-180).
Changed: PROJECT.md: documented the collection_size field on GET /api/home/stats.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: DeepL sync for all new/removed
  keys above (library.columns.taper, appShell.noWtrfAccount, appShell.statusBar.collectionSize/
  computing; removed home.* hero-card keys and appShell.user/userSub).

[2026-07-09] — feat(backend): TODO-167 — geocoder pulls structured location from bobdylan_shows/setlistfm_shows
Changed: backend/geocoder.py: extracted _entries_iso_dates() shared helper; added
  _get_bobdylan_shows_location_string() and _get_setlistfm_location_string(), matching the
  existing dylan_performances lookup pattern. run_batch() now tries three structured sources
  in priority order via _STRUCTURED_SOURCES — bobdylan_shows (most standardized "City, ST"
  strings), then setlistfm_shows, then dylan_performances as a last resort — before falling
  back to the raw entries.location text. location_geocoded.source records whichever table
  matched ('bobdylan_shows' / 'setlistfm_shows' / 'performances') instead of always
  'nominatim'. No route or GUI changes needed — /api/geocode/run already calls run_batch()
  directly.
Changed: PROJECT.md: documented the new source priority order and source column enum.
Added: tests/test_geocoder.py: 13 new tests covering both new lookup functions plus run_batch
  priority ordering (bobdylan_shows > setlistfm_shows > dylan_performances).

[2026-07-09] — chore(backend): TODO-165 — deprecate old acoustic fingerprinting feature
Changed: backend/app.py: removed all /api/fingerprint/* routes (build/status/stop/queue,
  lb_numbers, stats, identify, duplicates/scan/stop, collection_by_date, identify_folder/
  status/stop, purge), the init_fp_db() startup call, background worker state/threads, the
  "fingerprints" key from GET /api/collection/prefetch, and the fingerprint_cache stat from
  GET /api/purge/stats.
Changed: gui_next ScreenCollection.tsx: removed the Fingerprinted column, its filter/sort key,
  and the "Fingerprint Folder" context-menu action (separate integration from the dedicated
  screen, found during scoping — confirmed with user before removing).
Changed: gui_next ScreenSetup.tsx + AboutDialog.tsx: removed the purge-fingerprint-cache option
  and the librosa dependency row.
Changed: requirements.txt + PROJECT.md: dropped librosa/numba/soxr — introduced solely for
  fingerprinting and unused elsewhere (Concert Ranker uses numpy/scipy directly, not these
  three); numpy/scipy kept.
Removed: backend/fingerprint.py (Wang/Shazam landmark acoustic fingerprinting engine),
  gui_next/.../screens/ScreenFingerprint.tsx + its nav entry/icon/route (App.tsx, AppShell.tsx,
  Icon.tsx), backend/paths.py FP_DB_PATH, and the orphaned fingerprint.* / collection.detail.
  fingerprinted* / collection.toast.fingerprint* / setup.purges.fingerprintCache* i18n keys
  across all 6 locales. Legacy gui/ (PyQt6, frozen) and cli.py still reference the deleted
  routes/module — left intentionally broken per user decision (frozen GUI, low-traffic CLI
  path) rather than extending changes into frozen code.

[2026-07-09] — feat(gui): TODO-205 Phase 7 (async job model) + TODO-211 (severity extraction) — pipeline structural tier COMPLETE
Changed: gui_next ScreenPipeline.tsx: TODO-205 Phase 7 GUI migration (design §8) — runSteps no
  longer posts one synchronous /api/pipeline/run per folder. It now enqueues a batch onto a
  client-side queue; a single drainJobQueue driver POSTs /api/pipeline/run/start once, then
  polls /api/pipeline/run/status every 400ms (PIPELINE_POLL_MS), merging each folder's verdict
  as it lands (device-grouped, out of enqueue order). Batches serialise client-side to respect
  the backend's single-job busy guard; concurrent runSteps calls stack and drain sequentially.
  stopRun now POSTs /api/pipeline/run/cancel, clears the client queue, and stops the poll loop.
  Removed the now-dead per-folder updateRow/AbortController path; added rowsRef for stale-free
  id→path resolution in the async driver. The targeted single-step follow-ups (pending-fetch
  retry, detail refresh, blocked-recheck, rename file-refresh) deliberately stay on sync /run.
Added: gui_next folderQueueStore.ts: TODO-205 Phase 7 — zustand persist middleware
  (localStorage 'lbb-pipeline-queue'), so the folder work queue survives an app restart.
  Verdicts stay server-side (P7 cache); only the path list is persisted client-side.
Added: gui_next ScreenPipeline.tsx + backend/app.py: TODO-205 Phase 7 warm-start. New route
  POST /api/pipeline/state returns last-known cached verdicts (fingerprint-validated, design
  R3) for a set of folders, with severity freshly computed. A mount effect hydrates the
  persisted queue's rows so buckets paint immediately after restart — before any re-run, and
  even with autorun off. Rows already running are left untouched; the file step is appearance-
  only (P8) and re-resolved live on the next run.
Changed: backend/app.py: TODO-211 — extracted the pipeline severity computation out of the
  _pipeline_process_folder closure into a module-level pure function compute_pipeline_severity
  (verify/lookup/lbdir/rename + file_status/error_code + lb_number → severity). The closure and
  the new warm-start route both call it, and tests/test_p8_blocked_severity.py now drives the
  REAL function instead of a verbatim mirror — mirror/real drift is now impossible. Behaviour
  unchanged; verified by the existing 4 P8 cases + full pipeline suite (23 passed).

[2026-07-09] — feat(gui): TODO-205 Phase 5 GUI half + Phase 6 P8 — lbdir prefetch retry effect, blocked-collect as live view (structural tier)
Added: gui_next ScreenPipeline.tsx: TODO-205 Phase 5 GUI half (design §5/P3) — pending_fetch
  retry effect. The backend parks a row on a background LBDIR prefetch with lbdir status
  "mute" + pending_fetch:true; the existing auto-complete effect resumes a stale row only
  once (ref-guarded), so a row still inflight at that resume used to park until a manual
  re-run. New effect polls POST /api/pipeline/run {steps:['lbdir']} every 5s (LBDIR_PENDING_
  POLL_MS), capped at 6 attempts (~30s, LBDIR_PENDING_MAX_ATTEMPTS); once pending_fetch
  clears it drops the attempt count and the autocompleteStarted guard so rename/file resume;
  on timeout the row is left a plain mute (no new StepStatus string). pending_fetch added to
  the StepResult type. Implemented by sonnet agent, orchestrated + verified by opus.
Changed: backend/app.py: TODO-205 Phase 6 P8 (design §6) — "blocked as a live view" severity
  split. A blocked file step now escalates to attn ONLY when error_code in {no_date,
  no_route} (structural, need human config); transient codes (mount_offline, dest_exists,
  db_error, and any unknown code — whitelist semantics) fall through to the ready/done/attn
  logic and land in "done", so already-verified work no longer gets forced into "needs" for
  a pointless full re-run.
Added: gui_next ScreenPipeline.tsx: TODO-205 Phase 6 P8 GUI — serverRowToPipeline re-buckets
  a done-severity row with a transient file block (status 'bad') to "shelf" not "In
  collection"; auto re-resolve (re-run ['lookup','file'], ref-guarded once per detail-panel
  open) so a shelved row self-clears when its mount returns; bulk "Retry N blocked collects"
  toolbar button (isTransientBlock predicate) re-running the file step for all transient-
  block shelf rows. Design §6 optional auto-retry-on-mount-reachability NOT built — see
  TODO-205 remaining notes.
Added: tests/test_p8_blocked_severity.py: 4 tests for the P8 severity split (transient →
  done, no_date/no_route → attn, unknown code → done, bad step elsewhere → attn). NB tests a
  mirror of the severity block, not the real closure — see TODO-211 for the extraction fix.
Changed: gui_next locales/*.json: new pipeline.retryBlockedCollects key translated to
  de/fr/es/it/nl via /gui-next-i18n (the run also filled the pending backlog from concurrent
  library-screen work; 3,555 DeepL chars).

[2026-07-08] — feat(backend): TODO-205 Phases 1–5(backend) — pipeline cache schema, async job model, state persistence, hash consultation, lbdir prefetch (structural tier)
Added: backend/app.py: TODO-205 Phase 5 backend half (design §5/P3) — background LBDIR
  prefetch: module-level _LBDIR_PREFETCH_INFLIGHT set + lock (dedupe by LB number, many
  folders can resolve to one LB) + lazy ThreadPoolExecutor(max_workers=2); submitted the
  moment lookup resolves an LB whose lbdir attachment is uncached; worker mirrors the
  inline retrieval incl. canonical-alias fallback, failures swallowed (prefetch is
  advisory). While the LB is inflight the lbdir step returns status "mute" + label
  "Fetching LBDIR…" + pending_fetch:true instead of scraping synchronously; when NOT
  inflight the original synchronous scrape fallback runs unchanged. pending_fetch rides a
  marker field (GUI STATUS_TO_STATE union is closed); pending verdicts are never persisted
  to pipeline_folder_state and never served cached; severity exempts a pending_fetch lbdir
  mute from the "downstream not run" attn escalation. GUI half (pending_fetch retry effect
  in ScreenPipeline.tsx) deliberately deferred — see design §9 Phase 5 row for the handoff.
  Implemented by opus agent; verified: full suite 477 passed, /backend-restart, cold 1.1s →
  warm 95ms cached serve, no spurious pending_fetch on cached-attachment flows.
Added: backend/checksum_utils.py: TODO-205 Phase 4 (design §2a/§3) — _cached_file_hashes():
  verify_folder and verify_folder_lbdir consult pipeline_file_hash per file ((size,mtime)
  R1 validation at consumption); on a miss md5+sha256 are computed in ONE read (sha256 rides
  along to feed filing's tree digest); ffp cached incidentally (header-only read anyway);
  shntool never cached. Cache key is the raw posix rel-path (not the apostrophe-normalised
  matching name) so verify and filing share one keyspace. ANY cache-layer failure degrades
  silently to plain compute — verdicts can never change because the cache is unavailable.
Changed: backend/filer.py: filing's SOURCE-side tree digest now derives from cached sha256s
  (_source_tree_digest → db.derive_tree_digest, hash_tree fallback on any error); the
  DESTINATION is always freshly hashed — a poisoned cache can only cause a false mismatch
  (abort), never a false match, so hash-verify-before-remove holds unconditionally.
Added: backend/filer.py: stale_verify guard in start_file_job (design §3a hard rule,
  enforced for ALL filing, auto + manual): if a pipeline_folder_state row exists and the
  recomputed folder fingerprint differs, filing is refused with error_code "stale_verify"
  ("re-run the pipeline"); folders with no pipeline state proceed as before.
Added: tests/test_hash_cache_verify.py: 9 tests — cold/warm verify identical + md5&sha256
  populated, edited file detected as mismatch (not stale cached Pass), poisoned-stale row
  ignored, cache-failure degradation, source digest == hash_tree cold/warm + fallback,
  stale_verify blocks / matching fingerprint proceeds / no state proceeds. Full suite 477
  passed. Implemented by opus (code) + sonnet (tests) agents; verified live: cold 2×150MB
  verify 0.454s → touch one file → 0.233s (only the touched file re-hashed); edit-then-file
  refused with stale_verify.
Added: backend/app.py: TODO-205 Phase 3 (design §2b/§3/§4d) — _pipeline_process_folder now
  persists all step verdicts + post-run folder fingerprint to pipeline_folder_state after
  every run, and serves the two expensive hash steps (verify, lbdir) from cache with
  cached:true when the recomputed fingerprint matches (the R3 sweep). Three refinements over
  the design (recorded in its §9 as-built notes): lookup/rename/file ALWAYS run fresh
  (cheap + DB-dependent — pins/aliases/status invisible to the fs fingerprint; file is a P8
  live view); cached lbdir verdicts carry the lb_number they verified and are rejected after
  a re-pin (and never re-stamp set_lbdir_verified); persistence uses the post-run fingerprint
  since the lbdir step copies the manifest into the folder mid-run. New optional force:bool
  on sync /api/pipeline/run and async /run/start bypasses the cache. Implemented by an opus
  agent from the pinned spec; verified live: cached serve 15ms vs 220ms fresh (200MB
  fixture), force recomputes, touch → fingerprint miss → fresh → re-cached, mixed
  cached-verify/fresh-lookup row + severity correct, persisted JSON stores no cached flag.
Added: backend/app.py: TODO-205 Phase 2 (design §4) — async multi-folder pipeline job:
  POST /api/pipeline/run/start {folders, steps?, workers?:1-4}, GET /api/pipeline/run/status,
  POST /api/pipeline/run/cancel. Module-level _PIPELINE_JOB state +
  _pipeline_run_async_coordinator: folders grouped by os.stat st_dev (one drain thread per
  device, serial within a device — same-spindle seek-thrash guard), global
  Semaphore(workers) cap, cooperative per-folder cancel, per-folder try/except so one bad
  folder never kills the job. Busy contract mirrors filer.start_file_job
  ({ok:false, error_code:"busy"}). Sync /api/pipeline/run unchanged; GUI still uses it
  (migration is Phase 7). Implemented by a sonnet agent from the design spec; verified live:
  busy guard mid-run, cancel left in-flight folder to finish (verify "Pass") and skipped the
  23 queued, 400 bad_input on unknown steps, sync route byte-identical behaviour.
Changed: PROJECT.md: routes table — documented the three new async pipeline endpoints.
Added: backend/db.py: `pipeline_file_hash` (per-file md5/ffp/sha256 cache; (size, mtime) are
  validation columns per design rule R1) and `pipeline_folder_state` (per-folder step verdicts
  keyed by a per-file stat-sweep fingerprint, rule R2) tables per
  instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md §2; both registered in USER_TABLES so master
  exports drop them (they hold local absolute paths). Helpers: upsert_file_hash / get_file_hash /
  get_folder_hashes, folder_fingerprint, get/put_folder_state (fingerprint-scoped merge — a new
  fingerprint discards all prior verdicts), derive_tree_digest (reproduces filer.hash_tree
  byte-for-byte from cached sha256s with fresh-read write-through on any miss),
  prune_pipeline_cache (missing-folder sweep + 180-day age cap — design §10 Q1 decided). All
  writes route through db_queue (§4e). Inert: nothing consults the tables until Phases 3/4.
Added: tests/test_pipeline_cache.py: 10 tests — fingerprint stability/sensitivity (in-place edit,
  rename), hash-cache round-trip + replace-on-stat-change, folder-state merge/discard, derived
  tree digest == hash_tree on a fixture with a lone-surrogate filename (cold, warm, and
  poisoned-stale cache), USER_TABLES registration, prune. Discovered en route: SQLite TEXT cannot
  bind lone-surrogate paths — guarded via db._cacheable(); such files are never cached, always
  hashed fresh (speed cost only, never correctness).
Changed: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md: Phase 1 marked shipped with as-built
  notes; §10 Q1 (eviction) decided, Q1b surrogate-path constraint recorded.
Changed: TODO.md: TODO-205 retitled/rescoped to implementation tracking (design shipped
  2026-07-07; Phase 1 done, Phases 2–7 remaining). Stays Open.
Changed: PROJECT.md: schema section — documented the two new USER tables.

[2026-07-08] — feat/fix: orchestrated parallel-agent session — 8 items closed (BUG-233/236, TODO-149/174/175/176/207/208) + ledger cleanup
Fixed: backend/wtrf_scraper.py: BUG-233 — Content-Disposition parsing extracted into
  _filename_from_content_disposition(): plain filename= preferred; RFC 5987 filename*= decoded
  (strip charset''lang'', percent-decode); attach-id/LB fallback kept. 11 new tests in
  tests/test_wtrf_scraper.py. Note: the core regex fix was already committed (c3257c02) but the
  ledger was never updated — this session added the testable seam + tests and closed the entry.
Fixed: gui_next renderer: BUG-236 / TODO-206 — all 14 baseline TS errors fixed (two were real
  functional bugs: ScreenCollection addSource sent a wrong payload shape, ScreenPipeline
  shift-click range-select read shiftKey off ChangeEvent — moved to onClick). Pill title /
  IconButton disabled / Input type props added properly. typecheck script added to
  gui_next/package.json; gui-next-typecheck hook wired into .pre-commit-config.yaml alongside
  ruff. tsc -b + production build clean (zero-error baseline).
Changed: backend/setlistfm.py: TODO-149 — run_update() true incremental update: stops paginating
  when force=False and a full page yields zero newly-inserted rows (INSERT OR IGNORE rowcount);
  force=True keeps the full walk; stop_reason/pages_fetched logged. 3 stubbed-API tests.
Changed: backend/app.py: TODO-175 — /api/dbedit rows lb_filter accepts multiple comma/space-
  separated LB numbers via parameterized lb_number IN (...); invalid tokens fall back to
  unfiltered (prior semantics); GUI passes the raw string through so it works end-to-end.
  7 new tests (tests/test_dbedit_lb_filter.py).
Changed: gui_next ScreenBootlegs.tsx: TODO-176 — Year filter popover switched to a 5-column CSS
  grid ('All years' full-width top row); no new i18n keys.
Fixed: backend/scraper.py + backend/site_crawler.py: TODO-174 guardrails — (a) scrape_entry now
  marks already-on-disk files downloaded=1 (fixes permanent flag desync when site_crawler
  fetched the file first); (b) site_crawler skips network fetch for /files/ URLs already on
  disk while keeping inventory + entry_files bookkeeping. Investigation verdict: keep both
  mechanisms (different triggers/granularity), consolidation rejected. 2 new tests.
Added: tools/gui_next_locale_parity.py: TODO-207 — dotted-path key diff of en.json vs
  de/fr/es/it/nl (exit 0/1/2). Current status: full parity, 1381 keys in all 6 locales.
Added: .claude/hooks/session_end_check.sh: TODO-208 — SessionEnd hook (registered in
  .claude/settings.json) flags unrecorded changes to .claude/state/session_end_stale.flag;
  session_brief.sh surfaces the warning at next SessionStart and clears it. .claude/state/
  gitignored. Flag round-trip verified.
Added: tools/ledger_dedup.py: TODO-209 progress — duplicate-header-ID audit (report-only
  default; --apply experimental/unused). Finds 21 duplicated BUG ids + the TODO set, proposes
  keep/renumber per entry, lists all cross-references needing manual attribution. TODO-209
  stays open for the renumbering pass.
Changed: BUGS.md housekeeping — 11 entries that were marked Fixed but never archived moved to
  BUGS_DONE.md verbatim (BUG-193, 195, 202, 203, 204, 205, 208, 213, 214, 217, 223); BUGS.md
  is down to 9 genuinely open bugs. BUG-193's duplicate id (an unrelated importer BUG-193
  already in the archive) noted inline pending the TODO-209 dedup pass.
Tests: full suite 458 passed / 5 skipped; gui_next typecheck + production build clean.

[2026-07-08] — docs: close stale TODO-198 (TapeMatch recall recovery) — work completed 2026-07-02, ledger never updated
Changed: TODO.md/TODO_DONE.md: TODO-198 (CC_TAPEMATCH_FIXES Tasks 2-7) closed via
  `tools/ledger.py todo-close` — text was frozen at a mid-day 2026-07-02 snapshot ("Tasks 2-7
  remaining, curator-lineage/hf_ceiling NOT wired into live cli.py") but later 2026-07-02
  CHANGELOG entries show all of it landed same-day: Task 2 rerun_cat3.py executed (0/6 Cat-3
  flipped), Tasks 3.2/4.1/4.2 wired into live cli.py + validated, Tasks 5-7 implemented and
  calibrated (triplet fingerprint rejected/disabled after live calibration showed false merges).
  Final: recall 41.6%/precision 98.6%/fp=9 vs 38.3%/98.2% baseline; further gains scoped to
  CC_TAPEMATCH_ADDON.md (TODO-199).
Note: found a pre-existing ledger integrity issue while closing this — TODO_DONE.md now has two
  entries both numbered TODO-198 (this one and an unrelated "Quality page" TODO closed
  2026-07-01). Root cause: the TapeMatch entry's number was hand-set rather than assigned via
  `ledger.py next-id todo`, reusing an already-closed id (`_collect_ids` scans both files
  correctly, so this couldn't happen through the tool itself). No other file references
  TODO-198, so a renumber is low-risk whenever addressed. Flagging only, not fixed this session.
Added: TODO-209 — full header-ID audit found 17 duplicated TODO ids and 22 duplicated BUG ids
  across the open/done file pairs (mostly legacy debt predating ledger.py, added 2026-07-07 per
  TODO-205). Scoped as a batch renumbering job, not manual edits.

[2026-07-07] — fix: full-codebase bug hunt — 7 bugs found, confirmed via repro, fixed (BUG-238..244)
Fixed: backend/sharing.py: BUG-238 — _reaper_loop had no exception guard; one corrupt
  expires_at or persist OSError permanently killed share expiry (expired shares kept serving
  over the public tunnel). Loop body now guarded + logs; invalid-expiry shares reaped;
  _persist()'s mkdir moved inside its best-effort try.
Fixed: backend/sharing.py: BUG-239 — list_shares() popped expired shares without
  revoke_share(), skipping _persist() and the stop-tunnel-on-last-share logic (cloudflared
  ran forever with zero shares). Now revokes properly outside the lock.
Fixed: backend/scheduler.py: BUG-240 — scheduled integrity scans compared SQLite
  CURRENT_TIMESTAMP (UTC) against local datetime.now(); on CDT every scan fired 5 h late.
  Now parsed as UTC-aware and compared in UTC.
Fixed: gui_next/src/main/index.ts: BUG-241 — killProcessTree() only tree-killed on Windows;
  Linux/macOS app quit orphaned the backend's ffmpeg/sox/shntool children. Backend now
  spawned detached on POSIX and killed via process-group kill(-pid) with fallback;
  killPortProcess routes through killProcessTree.
Fixed: backend/importer.py: BUG-242 — flat-file import silently dropped malformed rows
  (except: pass). Now counts skips, logs first 5 with line numbers + a summary WARNING;
  except narrowed to (ValueError, sqlite3.Error).
Fixed: backend/db_queue.py: BUG-243 — async write failures left no trace despite the
  docstring's claim of DEBUG logging. Writer thread now logs them at WARNING with traceback.
Fixed: backend/db.py + backend/app.py: BUG-244 — re-pinning a folder to a different LB
  accumulated links (set_folder_link went additive in the composite-PK migration) and the
  old pin won lookups via pinned_lbs[0]. New replace_folder_link() (atomic DELETE+INSERT in
  one write-queue transaction) now backs PUT /api/folder_link.
Changed: tests/test_db_writes.py: stale test_replace_existing (failed on main) split into
  test_set_is_additive (auto-link semantics) + test_replace_existing (re-pin semantics).
Note: repros kept in .debug/ (repro_s1_reaper.py, repro_s2_scan_tz.py + _fixed,
  repro_s3_killtree.mjs, repro_s4_list_shares.py, repro_s5_s6.py). Full pytest suite
  435 passed / 0 failed; gui-check node types + build PASS (renderer baseline still 14
  errors, but now spread over 6 files, not just ScreenScraper.tsx — BUGS.md BUG-236 note
  is stale). Informational, not fixed: /api/spectrogram/png serves any absolute *.png path
  (single-user app, basic-auth web GUI) — flagged only.

[2026-07-07] — feat/chore: pipeline dev-loop quick wins (spec D1/D2/D3/P5) — auto-collect toggle, ledger CLI, advisory hooks, change-log dedup
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Auto-collect" toggle (spec P5) —
  third header toggle, default off, session-only; auto-files rows meeting the fileableRows guard
  (verify/lookup/lbdir/rename all ok), serialized via the existing filing lock, skipConfirm path.
  State ~line 1323, ref ~1378, effect ~1820, toggle UI ~2080.
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: pipeline.autoCollect +
  pipeline.autoCollectHint strings (DeepL-synced for the new toggle).
Added: tools/ledger.py (spec D2): stdlib CLI for BUG/TODO ledger operations (next-id,
  bug-open/close, todo-open/close, --dry-run) — atomic raw-text surgery preserving irregular
  separators byte-exactly; replaces hand-edits of BUGS.md/TODO.md across all four ledger files.
Added: .claude/hooks/py_compile_check.sh (spec D3): PostToolUse hook on Edit|Write of .py files —
  runs py_compile, exit-2 feedback on syntax error.
Added: .claude/hooks/i18n_reminder.sh (spec D3): PostToolUse hook on gui_next en.json edits —
  reminds to sync locale files.
Added: .claude/hooks/changelog_check.sh (spec D3): Stop hook — warns (never blocks) if source
  changed this session but CHANGELOG.md's head entry isn't dated today.
Changed: .claude/settings.json: registered the three new hooks alongside the existing
  schema-deploy/session-brief/access-guard hooks.
Changed: PROJECT.md (spec D1): `## Change Log` table frozen as of 2026-07-07 (historical rows
  kept, notice added at ~line 1619) — CHANGELOG.md is now the sole narrative change log.
Changed: .claude/commands/session-close.md: rewired to route all BUGS/TODO moves through
  tools/ledger.py; PROJECT.md step no longer adds Change Log rows.
Changed: .claude/CLAUDE.md: Bookkeeping + Verification bullets trimmed to match the ledger.py
  workflow and the frozen Change Log table.
Note: structural pipeline items P1/P2/P3/P7/P8 from
  instructions/complete/FABLE_PIPELINE_DEVLOOP_IDEATION.md deliberately deferred pending a
  combined design doc (see TODO-205); the ideation doc was later moved to instructions/complete/
  once its remaining open item (D6) was captured as TODO-207.
Added: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md (TODO-205, design only — no code
  changes): combined design for the structural pipeline tier — P7 (persist pipeline row
  state, resume across restart) + P1 (shared per-file hash cache) + P2 (async multi-folder
  job model), with P3 (LBDIR prefetch) and P8 (blocked-as-live-view bucketing) layered on
  the same cache/state tables; phased 7-step implementation plan. TODO-205 remains OPEN
  (design done, implementation not started). Reviewed and corrected against sources: (1)
  spec correction carried forward — `useFolderQueueStore` (gui_next/src/renderer/src/lib/
  folderQueueStore.ts) has no zustand `persist` middleware, so the folder queue does NOT
  survive a GUI restart today (the ideation doc's §65 assumption was wrong; this design's
  P7 GUI migration adds `persist`, mirroring `useSettingsStore`'s `'lbb-settings'` key); (2)
  documented the exact reproduction requirements for deriving `filer.hash_tree`'s digest
  from the new cache — `rel_path.encode("utf-8", "surrogatepass")` (surrogatepass is
  load-bearing for lone-surrogate filenames), raw 32-byte `file.digest()` output (not hex)
  fed into the tree hash, and `root.rglob("*")` scope covering every file under root (not
  just audio) — verified byte-for-byte against filer.py:322-340; (3) fixed an incorrect
  citation pointing the P3 "auto-complete" GUI-effect predicate at the wrong `useEffect`
  (was citing the unrelated auto-rename effect at ScreenPipeline.tsx:1661-1682; corrected
  to the actual resume effect at ScreenPipeline.tsx:1549-1560, predicate
  `lookup.status === 'ok' && lbdir.status === 'mute'`); (4) corrected a db.py line
  citation for the `location_geocoded` ALTER-TABLE additive-column precedent (was pointing
  at the table's `CREATE TABLE` line 280; the actual precedent is db.py:1629-1632).
Fixed: .claude/CLAUDE.md: Code Rules SQLite bullet corrected — the repo's actual idempotency
  convention is `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` column-existence checks
  before `ALTER TABLE` (db.py:1572-1636), not the previously-stated `ALTER TABLE` + `try/except`.
Added: TODO-206 — gui_next: fix 14 baseline renderer typecheck errors (IconButton `disabled`
  prop, `shiftKey`-on-ChangeEvent in ScreenPipeline.tsx), then wire typecheck into pre-commit
  alongside the existing ruff-only Python gate.
Investigated: backend/checksum_utils.py `verify_folder` — confirmed `.st5` checksums ARE
  effectively verified (not a bug): they're merged into the `shntool` expected slot
  (checksum_utils.py:568-575) and compared against a freshly computed shntool hash for `.shn`
  audio files (:640-643); `st5_status` stays hardcoded `'na'` only because the pass/fail
  surfaces under `shntool_status` instead.
Changed: instructions/FABLE_PIPELINE_DEVLOOP_IDEATION.md retired to instructions/complete/
  (its last open item, D6, captured as TODO-207); added instructions/README.md as an
  active/complete spec index; added a session-close rule to auto-move finished specs into
  instructions/complete/ and update the index; opened TODO-207 (gui_next locale key-parity
  check script, spec D6 remnant).

[2026-07-05] — docs: CLAUDE.md optimization — targeted context reads, skill delegation
Changed: .claude/CLAUDE.md: rewrote for token efficiency — replaced mandatory full reads of
  PROJECT.md/BUGS.md/TODO.md (~3,300 lines/session) with grep-first targeted reads; moved
  BUG/TODO/CHANGELOG entry templates out (now in /session-close); verification + backend-restart
  rules now delegate to /gui-check and /backend-restart skills; added .venv/bin/python3 PATH
  rule; merged Known Pitfalls into Debugging. 108 → 76 lines, no rules dropped.
Changed: .claude/commands/session-close.md: now self-contained source of truth for BUG-<NNN>/
  TODO-<NNN> entry formats (templates inlined, CLAUDE.md pointer removed).
Added: CHANGELOG_ARCHIVE.md: 2026-05 entries (393, ~3,800 lines) rotated out of CHANGELOG.md;
  CHANGELOG.md now keeps a rolling ~2-month window (policy noted in CLAUDE.md Bookkeeping).
Added: gui/CLAUDE.md: legacy-GUI rules (frozen status, QThread-only backend calls, /i18n-update);
  QThread rule moved here from root CLAUDE.md.
Added: tools/tapematch/CLAUDE.md: tapematch conventions (WORKFLOW.md/CALIBRATION_PROGRESS.md
  first, no concurrent live sessions, runs in data/tapematch/runs/, batch rules).
Changed: PROJECT.md: new "## Contents" grep index after the intro; Change Log row added.

[2026-07-05] — test(tapematch): TODO-202 densification probe concluded — 12× REJECTED, 5× Rule D kept
Changed: tools/tapematch/TIER_B_FULLSET_REPORT.md: new "Densification probe" section — full
  12×60s re-embed (embed_cache_12x/, 1942+523 sources) + emb_score_pairs + v1/v2 sweeps;
  gate (flips > 25 at abs fp ≤9/≤6) met only at the both_tol 0.725 plateau edge (26 flips,
  net +1 TP, −3 shipped recoveries regress, one gain 0.015 above bar) — one step from the
  0.700 FP cliff the 5× calibration refused. Kept t_emb 0.75 on the 5× cache; sparse-excerpt
  TP-tail hypothesis falsified as a broad effect. Sweep logs: tools/tapematch/logs/
  fullset_eval_12x_{v1,v2}.log; 12× artifacts retained for TODO-204.
Fixed: tools/tapematch/emb_fullset_eval.py: BUG-237 — acceptance check compared the sweep's
  deliberately pre-Rule-D baseline against post-ship `score --cached` semantics
  (_passthrough_with_rule_d union), a guaranteed 25-TP false MISMATCH; reference now strips
  rule_d (identity re-proven: tp=659/916/9/1381 v1, 662/916/6/1381 v2) and prints the
  shipped confusion + derived ship bar alongside. Docstrings document the replacement framing.
Changed: TODO.md/TODO_DONE.md: TODO-202 → Done (moved); TODO-204 unblocked (sequencing note
  updated); handoff block item 2 marked done. BUGS_DONE.md: BUG-237 added.

[2026-07-04] — chore(docs): skill/command audit — fixed stale paths and rule violations
Changed: .claude/skills/analyze-runs/SKILL.md: repurposed as read-only roll-up of existing
  analysis.md files; old version pointed at nonexistent tools/tapematch/runs/ and used the
  abandoned claude -p subagent-writer approach (superseded by /tapematch-batch).
Changed: .claude/skills/verify/SKILL.md: rewritten around the real tooling
  (tools/browser_driver.mjs + tools/debug_screens.json, /api/status health check); old
  one-liner referenced Electron+Xvfb which the driver explicitly does not use. Marked as
  the explicit user-invoked exception to the no-GUI-screenshots rule.
Changed: .claude/commands/tapematch-batch.md: merged complete-sets-only filter (same-line
  "DB entries | Found on disk" parse, === CLUSTERS === check) and default batch size 25 → 5,
  per established workflow feedback; backlog report now splits eligible vs skipped-incomplete.
Changed: .claude/commands/find-bugs.md: added repo conventions (venv python, backend restart
  before verify, BUGS_DONE/CHANGELOG bookkeeping, encoding pitfalls, known-bug cross-check,
  optional scope argument).
Changed: .claude/commands/i18n-update.md: fixed bare `python` → .venv/bin/python3; DeepL key
  now read from env (settings.local.json) instead of prompting; scoped to legacy PyQt6 GUI.
Changed: .claude/commands/gui-next-i18n.md: added description frontmatter.
Added: .claude/commands/session-close.md: end-of-session bookkeeping skill (CHANGELOG entry,
  BUGS/TODO moves with cross-file next-free numbering, PROJECT.md change-log row, consistency
  check).
Added: .claude/commands/backend-restart.md: full kill+relaunch of run_backend.py with uptime/status
  verification; documents that /api/admin/restart does NOT reload code under run_backend.py (the
  callback only recycles werkzeug in-process — modules stay imported).
Added: .claude/commands/gui-check.md: sanctioned non-visual GUI verification — tsc --noEmit on
  tsconfig.node.json + tsconfig.web.json, then electron-vite build; 14-error renderer baseline
  noted (BUG-236).
Added: BUGS.md: BUG-236 (Open) — 14 pre-existing TS2322 errors in ScreenScraper.tsx, found while
  validating gui-check's typecheck commands.

[2026-07-04] — feat(tapematch): TODO-200 live emb integration + TODO-202 densification probe + dolphinsmile taper fix
Added: tools/tapematch/emb_live.py: live sessions now populate pairs.emb_score/emb_score_global
  (subprocess into .venv-nmfp for cache misses, shared emb_score_pairs.score_pair scoring,
  UPDATE keyed by run_id; any failure leaves NULL → Rule D abstains). Hooked after
  insert_pairs in tapematch_session.py; gated by new config.yaml rule_d.live_embed flag.
  Tests: tools/tapematch/tests/test_emb_live.py (4) + verdict equivalence 177 → 181 pass;
  score --cached byte-identical (tp=684 fn=891 fp=9 tn=1381).
Changed: tools/tapematch/emb_score_pairs.py: `_score_pair` → public `score_pair` (importable
  by emb_live; CLI output verified byte-identical).
Added: tools/tapematch/nmfp_embed.py: `--n-excerpts` flag (default 5, byte-identical) for the
  TODO-202 densification probe. 12×60s pilot (523 sources, embed_cache_12x): kill condition
  NOT triggered — genuine-TN tail max 0.704 both-conv (vs 0.680 at 5×), still under the 0.75
  bar; full-set 12× embed + sweep proceeding.
Fixed: backend/db.py: dolphinsmile removed from _KNOWN_TAPER_ALIASES and added to _NOT_TAPER
  (+ misspelling variants) — he curates/transfers others' tapes, not a taper (curator ruling).
  Backfill: 463 entries.taper_name attributions NULLed in data/losslessbob.db.
Added: TODO.md TODO-203: Tier C retrain with family-aware hard negatives — sampler grouped
  hard negatives by (date, slot) ignoring family_id; 16.2% of same-date pairs are verified
  same-family → contrastive training pushed same-tape transfers apart. Includes
  taper-attribution negatives design (curated _KNOWN_TAPER_ALIASES handles only; raw
  taper_name strings measured NOT truth-grade: 381/2366 diff-raw-taper conflicts).

[2026-07-04] — feat(tapematch): nmfp Rule D SHIPPED (+25 TP, zero new FP) + label-set v2 + FN census
Added: tools/tapematch/tapematch/verdict.py: `_rule_d_emb_both` — both-convention embedding
  merge (emb_score aligned AND emb_score_global ≥ t_emb, cross-source only, NULL abstains);
  wired into `_addon_links`. config.yaml `addon_links.rule_d` ENABLED at t_emb 0.75 after
  full-frozen-set proof: score --cached tp=684 fn=891 fp=9 (recall 41.8%→43.4%, zero new FP);
  v2 labels tp=687 fp=6 (43.5%/99.1%). Full narrative: tools/tapematch/TIER_B_FULLSET_REPORT.md
  (re-opens the 2026-07-03 Tier B rejection — the p10/p90 gap gate tested lone-merge mode; the
  deferred absolute-FP curve through transitive clustering was the decisive measurement).
Added: tools/tapematch/tapematch_session.py: pairs.emb_score + pairs.emb_score_global
  (REAL nullable, idempotent ALTER, fp_triplet_score pattern); populated for 2240 frozen
  pairs via new tools/tapematch/persist_emb_scores.py (read-back verified via latest_pairs).
Changed: tools/tapematch/regression.py: `--set PATH` on the score subcommand (defaults to
  frozen v1 — byte-identical); passthrough branch extended (`_passthrough_with_rule_d`):
  on historical dates Rule D is strictly ADDITIVE over stored SAME_FAMILY edges (metric
  replay is not authoritative there — force-recompute probe collapsed baseline tp 659→512).
Added: tools/tapematch/regression_set_v2.json (+ make_regression_set_v2.py): v1 with the 3
  waveform-contradicted negatives (LB4642/9900, LB6825/9180, LB3431/3455, corr 0.93-0.95,
  label_suspect=1) flipped — real frozen FP count is 6, precision 99.1%. v1 stays frozen.
Added: tools/tapematch/fn_label_census.py (report-only): objective label-noise census over
  all 855 corr<0.05 FN — 265 (31.0%) flagged (128 explicit "different recording" curator
  text, 162 duration >15% off unity, 25 both).
Added: tools/tapematch/emb_fullset_eval.py: pre-registered threshold sweep (15 T × 3
  variants) over the full frozen set with absolute post-transitive-clustering FP counting
  against both label sets; acceptance-checked byte-identical to score --cached. Lone
  aligned-only variant REJECTED (transitive FP floor abs fp≥10 — guard-masking trap
  observed live); self-pair LB-3164/LB-3164 excluded as unmeasurable.
Changed: tools/tapematch/tests/test_verdict_equivalence.py: +3 Rule-D cases (dormant
  byte-identical, NULL abstain, self-pair never links) — 177 pass.

[2026-07-04] — feat(tapematch): Tier B nmfp harness extended to the full frozen set
Added: tools/tapematch/build_fullset_worklist.py: generalizes build_embed_eval_set.py's
  ~180-source pilot population to the entire frozen regression_set.json — every frozen
  negative pair ("neg") plus every frozen positive currently FN (derived exactly as
  `regression.py score --cached` derives it, imported not reimplemented) with corr<0.05
  ("fn_lowcorr"). Writes fullset_pairs.json (flat date/lb_a/lb_b/tag/corr list) +
  fullset_sources.json (embed_eval_set.json-shaped per-source metadata, deduped to the
  kept pairs) — consumable directly by nmfp_embed.py --eval-set. --pilot N --seed 42
  restricts to N random "neg" pairs + their sources for a cheap dry run. Read-only
  against observations.db; no audio/model run. Validated: 2245 kept (1390 neg + 855
  fn_lowcorr), 0 skipped for missing metadata, 726 dates / 2467 sources, <1s runtime.
Added: tools/tapematch/emb_score_pairs.py: computes nmfp emb_score for any
  build_fullset_worklist.py pairs file against embed_cache/, reusing embed_eval.py's
  _load_source/_pair_score verbatim (no refactor needed — already plain module
  functions) for both the tol=2s aligned and tol=0 global conventions. Outputs
  <stem>_scores.json + a min/median/p90/max summary per tag/tol. Validated against the
  existing 184-source embed_cache/ (scored the overlapping pairs correctly, nulled the
  rest as missing-cache).
Changed: tools/tapematch/nmfp_embed.py: docstring only — documented the pre-existing
  (unused-until-now) --eval-set PATH option, which already works generically against
  any embed_eval_set.json-shaped source list including the new fullset/pilot outputs;
  no code change needed. --workers was requested but skipped: forking after the
  TF/essentia model + checkpoint are loaded (and any GPU context init) risks
  duplicated/corrupted TF state across worker processes, so it was not added.

[2026-07-03] — docs(tapematch): Tier C ad hoc calibration probe report — reconfirms REJECT
Added: tools/tapematch/TIER_C_CALIBRATION_PROBE_REPORT.md: user-requested spot-check of the
  dormant Tier C contrastive encoder (ckpt/tierc.pt) against a 7-date/17-source calibration set
  with ground truth sourced independently of tapematch (entry_lineage same_as_lb parsing +
  explicit "different recording" curator-text scan via new tools/tapematch/
  _mine_calibration_candidates.py, cross-validated against observations.db history for 2 of the
  4 mined dates). Result: reconfirms the CC_TAPEMATCH_ADDON Tier C gate rejection on fresh
  out-of-sample data — same-source pairs Tier C didn't need to solve score high (0.85), the two
  hard historical same-source pairs (waveform corr ~0) separate only weakly from distinct pairs
  (0.32 vs 0.28 ceiling), and critically the one deliberately-hard case (2025-11-17 LB-16545, a
  full stem-separated remix of the same base recording) scores indistinguishable from genuinely
  distinct sources (0.22-0.29, inside the 0.18-0.28 distinct band) — Tier C cannot see through
  heavy reprocessing any better than waveform correlation can. No config/verdict/schema changes;
  read-only probe against the already-dormant checkpoint. Script: tools/tapematch/_tierc_probe.py.

[2026-07-03] — fix(tapematch): trim.performance_envelope spurious mistrim on compressed sources (BUG-235)
Fixed: tools/tapematch/tapematch/trim.py: performance_envelope now bails out to the full
  recording when whole-source energy dynamic range (p90-p10) is below the new
  trim.min_dynamic_range_db (10.0). Found via live 2025-11-16/17 Glasgow runs: two sources
  were cut to a 20-second "performance" window because the fixed p10+6dB energy gate
  chattered on heavily-normalised audio with only 6.4-8.5dB of crowd/music contrast, vs.
  11.9-15.4dB on known-good control dates. Re-running both dates post-fix keeps full
  length on all previously-broken sources and turned 2025-11-16's LB-16525/LB-16544
  same-source merge from a low-confidence fingerprint-only link (Dice 0.455) into a
  high-confidence primary correlation (0.924).
Added: tools/tapematch/tests/test_trim.py: synthetic wide/narrow dynamic-range + boundary
  tests for the new guard.
Changed: tools/tapematch/config.yaml: new trim.min_dynamic_range_db: 10.0 knob.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON effort concluded — Tier C rejected, calibration audit tool added
Changed: tools/tapematch/CALIBRATION_PROGRESS.md: confirmed with user that Gate 7.3.2's negative
  result (gap -0.017 tol=0 / -0.074 tol=2, both below the >=0.10 bar and both worse than Tier B's
  -0.034/nmfp baseline) stands as a final REJECT per the pre-agreed protocol — no Rule-C wiring, no
  pairs.emb_score column, no verdict/regression.py changes. Closes out the whole CC_TAPEMATCH_ADDON
  effort (Tiers 0/A/B/C) at the unchanged shipped state: recall 41.6%, precision 98.6%, fp=9.
Added: tools/tapematch/dump_calibration_audit.py + build_calibration_audit_html.py — reuse
  regression.py's exact score --cached internals to dump every frozen pair (2965 pairs, 3157 unique
  LB#s) with its truth label (lb_says_same), current verdict category (TP/FN/FP/TN), corr/fp_score/
  hiss_median, label_suspect flag, and the LB catalog relation-text the truth label was derived from.
  Outputs tools/tapematch/calibration_audit.json (data) + calibration_audit.html (self-contained
  interactive search/filter/sort table, published as a Claude Code artifact) so labels can be
  manually spot-checked against the actual curator notes — motivated by the known ~37% label-noise
  rate in the FN population and 3 confirmed mislabeled negatives found during Tier B.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier C (Task 7) — training run + gates 7.3.1/7.3.2 (decision pending)
Added: tools/tapematch/embedding/aug_sanity.py (Gate 7.3.1) — loads the trained checkpoint, samples
  200 cached windows, compares each window's clean embedding vs one AugmentChain-augmented view via
  cosine similarity, logs mean/median/min/p10. Result: mean=0.9638 median=0.9767 min=0.7921
  p10=0.9147 — PASS (bar >=0.80 mean/median).
Changed: tools/tapematch/embedding/ckpt/ — trained tierc.pt via train.py --device cuda, 30
  epochs/7170 steps, 69.8 min wall time, final loss ~0.029 (throughput measured first:
  --max-steps 100 gave steady-state 1.678 steps/sec, confirming the config default 30 epochs
  already lands in the 1-2h target with no config change needed).
Added: tools/tapematch/embed_cache_tierc/ — infer.py --device cuda over all 184 Task-6 eval
  sources (extracted=184 skip=0 fail=0, 46 dates).
Result: Gate 7.3.2 (decisive, embed_eval.py) — tol=0 gap p10(TP)-p90(TN) = 0.475-0.492 = -0.017;
  tol=2 gap = 0.267-0.341 = -0.074. Both below the >=0.10 bar and worse than the Tier B/nmfp
  -0.034 baseline at tol=2. Ship/reject decision intentionally left PENDING for user review — no
  Rule-C wiring, pairs.emb_score, or regression.py scoring touched. Full numbers in
  tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier C (Task 7) — package + training cache built (PAUSED before training)
Added: tools/tapematch/embedding/ package (isolated torch env .venv-emb, torch 2.6.0+cu124, RTX 3080):
  config.yaml (all hyperparams; embedding.CHECKPOINT + ENABLED=false), melspec.py (shared torchaudio
  log-mel, train/infer parity), data.py (hard-neg mining from observations.db same-date different-family
  EXCL label_suspect + 67 eval dates; time-aligned (date,slot) window cache so same-slot windows across
  a date's sources are same-show hard negatives; RESUMABLE per-source shard build), train.py (GPU NT-Xent
  loop, cosine LR+warmup), infer.py (CPU/GPU batch inference → embed_cache_tierc/, Tier-B harness format).
  augment.py + model.py landed via sonnet agents (see the two entries below).
Added: training cache tools/tapematch/embedding/audio_cache/windows.npy (gitignored) — 61,253 windows
  (float16, 1s@16k) from 1,278 sources / 200 densest multi-source dates; 9,600 (date,slot) groups, ALL
  multi-source (every group carries same-show hard negatives). Verified: no NaNs, sane amplitudes.
Verified: full loop smoke end-to-end (cache→train→infer→embed_eval gate) on a 2-date cache; batches
  carry 42/64 same-show hard negatives; mel(8,1,64,63)→encoder(8,128 unit-norm)→NT-Xent→backward OK.
Note: PAUSED for review BEFORE the training run per user request. Cache/env/nmfp-vendor all gitignored.
  Build ran DETACHED (setsid+nohup) after tool-managed background shells were repeatedly SIGKILLed;
  resumable shards made interruptions safe. NEXT (not started): throughput measure → full training →
  aug-sanity gate 7.3.1 → infer 184 eval sources → decisive p10(TP)-p90(TN) gate vs Tier B -0.034.
  Resume steps in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Task 7.1 — Tier C transfer-chain augmentation
Added: tools/tapematch/embedding/augment.py: AugmentChain(cfg, rng) — synthetic-positive
  generator for the contrastive embedding. Ops (each gated by its own config.yaml AUGMENT.*.P):
  speed warp (Fraction-based resample_poly, +-MAX_PCT), lowpass (6th-order Butterworth
  sosfiltfilt, cutoff in [F_MIN_HZ,F_MAX_HZ]), MP3 round-trip (real ffmpeg subprocess, f32le ->
  mp3 @ random KBPS -> f32le, FFT cross-correlation realignment to strip the ~1105-sample
  LAME encoder/decoder delay so the "positive" stays time-aligned with its source), tape hiss
  (additive gaussian at random SNR_DB), level ride (slow sinusoidal gain envelope, +-MAX_DB),
  EQ tilt (linear-in-frequency spectral tilt via rfft/irfft, +-MAX_DB), wow/flutter (sinusoidal
  time-warp via np.interp, +-MAX_PCT at RATE_HZ). GEN_STACK composes MIN_OPS..MAX_OPS
  (2-3) randomly-ordered distinct ops per call, re-rolling each op's own P; all randomness
  drawn from the injected np.random.Generator for reproducible training. Output is always
  cropped/zero-padded back to the input length (_fix_length) regardless of which
  length-changing ops fired. numpy+scipy only (no librosa); ffmpeg via subprocess.
Added: tools/tapematch/embedding/tests/test_augment.py: 21 pytest cases (parametrized per-op
  finite/same-length/changed checks, MP3 round-trip correlates-but-not-identical, full-chain
  determinism under equal-seed rng, 10-seed log-magnitude-spectrum similarity sanity >=0.3 using
  a band-limited-noise fixture — a pure-tone fixture was tried first and rejected: narrowband
  line spectra decorrelate under a few-% frequency shift even though the augmentation is mild,
  which is a test-signal artifact, not a bug). All pass under .venv-emb.
Fixed: tools/tapematch/embedding/augment.py: MP3 round-trip was silently time-shifting the
  "positive" view by ~1105 samples (69 ms @ 16 kHz, the LAME encoder+decoder delay) relative to
  its source before length-cropping — waveform corr at lag 0 was -0.70 on a caught test signal
  vs 0.997 at the true alignment. Fixed by FFT cross-correlating the decoded PCM (which ffmpeg
  returns ~1280 samples longer than input) against the input over all valid offsets and cropping
  the best-aligned n-sample window, instead of naively taking the first n samples.
Note: implements spec 7.1 (augmentation menu) only. data.py (hard-negative mining/sampler),
  train.py, infer.py are NOT yet implemented — Task 7 is still in progress.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Task 7.2 — Tier C ConvEncoder + NT-Xent loss
Added: tools/tapematch/embedding/model.py: ConvEncoder(cfg) — small conv stack (stem + 4x
  stride-2 Conv2d/BN/ReLU blocks downsampling freq+time jointly) + AdaptiveAvgPool2d + Linear
  projection to EMB_DIM (128) + L2-normalize; (B,1,64,T) log-mel in -> (B,128) unit-norm
  embedding out. 587,712 params (config-driven via MODEL.WIDTH=64/EMB_DIM=128), well under the
  10M hard budget (spec 7.2). Also adds nt_xent(z1, z2, temperature): symmetric NT-Xent/InfoNCE
  over the 2B-row batch (positives z1[i]<->z2[i], all other 2B-2 entries as in-batch negatives)
  — same-show hard negatives from the data sampler (TRAIN.HARD_NEG_MIN_FRAC>=0.25) need no extra
  masking, they simply sit in the negative set.
Added: tools/tapematch/embedding/tests/test_model.py: 5 pytest cases — forward shape + exact
  unit L2 norm, param count <=10M, CPU-only run, NT-Xent scalar/finite/backward, NT-Xent rewards
  agreement (z2==z1 loss < random-z2 loss). All pass under .venv-emb (installed pip+pytest into
  that env via ensurepip; PyYAML was already present).
Note: this implements spec 7.2 model+loss only. data.py (hard-negative mining/sampler),
  augment.py, train.py, infer.py are NOT yet implemented — Task 7 is still in progress.
Added: tools/tapematch/nmfp_embed.py: real embedding extractor (runs under isolated .venv-nmfp,
  TF2.13/essentia/CPU). Reproduces neural-music-fp's exact essentia-mel + FingerPrinter (nmfp-triplet
  ckpt-100) on exactly-8000-sample segments → faithful 128-d L2-normalized fingerprints. Decodes each
  track individually + concatenates PCM (Shorten .shn has no timestamps → ffmpeg concat demuxer stops
  after track 1; fixed by per-file decode). All 184/184 eval sources embedded.
Added: tools/tapematch/TIER_B_EMBED_REPORT.md: full Task 6 report (model justification, distributions,
  gap vs triplet, label-noise analysis, verdict).
Added: tools/tapematch/.venv-nmfp (gitignored): isolated py3.11 env (uv) — tensorflow-cpu 2.13.0,
  numpy 1.24.3, essentia 2.1b6.dev1110, pandas 2.1.4, h5py, pyyaml, soundfile. vendor/neural-music-fp
  repo + Zenodo checkpoint (gitignored, ~200 MB). Main .venv untouched (nmfp deps NOT in requirements.txt).
Result: TP median 0.912 vs same-show-TN median 0.150 (aligned) — learned similarity SEPARATES the
  population that killed every content-based signal (triplet median Δ≈0). BUT p10(TP)-p90(TN) gap
  = -0.034 (aligned) / +0.007 (global), both < 0.10 → REJECT per spec 6.2 (tail overlap; nmfp is
  Rule-C-only). Killer TN tail (max 0.961) is LABEL NOISE: 3 frozen negatives are waveform-contradicted
  (corr 0.92-0.95, same family) — flagged pairs.label_suspect=1 (poison as Tier C hard negatives).
  Excluding them, genuine same-show collisions cap at 0.605; Rule-C bar ~0.65 recovers 8/60 FN with
  0 clean-neg FP (marginal, only over 59 negs; NOT shipped — no emb_score/Rule C wiring, per spec
  "fail gap → stop Tier B"). Strong positive signal for Tier C (Task 7): a PRETRAINED fingerprint
  already separates; contrastive training targets the 0.3-0.6 genuine-collision band this isolates.
Changed: tools/tapematch/embed_extract.py: _NmfpBackend now points to nmfp_embed.py (the real TF-env
  extractor) instead of an in-process wire. tools/tapematch/observations.db: 3 negative label-error
  pairs flagged label_suspect=1. Resume/Tier-C handoff in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier B (Task 6) measurement harness — built + proven, gated on model install
Added: tools/tapematch/build_embed_eval_set.py: Task 6.1.4 eval-set builder. Date-clustered
  selection (embed each source once, reuse across in-stratum pairs) → embed_eval_set.json with
  60 TP (frozen positives, corr>=0.05) / 60 same-date different-source TN / 60 target-FN
  (frozen positives corr<0.05, excluding Task-1 label_suspect). 67 dates, 184 distinct sources.
Added: tools/tapematch/embed_extract.py: Task 6.1 extraction. Pluggable backend — `synthetic`
  (audio/model-free plumbing) proven end-to-end; `nmfp` (raraz15/neural-music-fp, TF2.13/8kHz —
  the spec-ideal degradation-robust FP with a discriminative head) and `muq` (torch foundation
  fallback) real paths written but NotImplementedError until an isolated model env is set up.
  Embeds 1s/0.5s-hop windows over 5×60s excerpts; nominal time = seconds-into-performance (from
  trim_head, speed-corrected) so both transfers of a concert share an origin; caches per-source npz.
Added: tools/tapematch/embed_eval.py: Task 6.2 gate + report (numpy-only, model-free). Per-pair
  emb_score = median A-window cosine-max to B (±tol aligned neighbourhood, or global when tol<=0);
  prints TP/same-show-TN/FN distributions + p10(TP)-p90(TN) gap, mirrors calibrate_triplet.py.
  Ships Tier B only if gap>=0.10 (triplet baseline -0.012); else structural REJECT.
Verified: synthetic backend end-to-end on the real 60/60/60 eval set — all pairs scored, gap ~0
  (noise floor, as expected: different-LB synthetic pairs share no lineage signal). ffmpeg/ffprobe
  present; all sampled eval sources resolve in my_collection with readable audio → real extraction
  de-risked. REMAINING (gated on user's model choice): install model, run live extraction, report
  the real gap. No conda/uv/py3.11 on host → nmfp needs an isolated py3.11 env bootstrap.
Note: torch 2.12 + tensorflow 2.21 both install on py3.13; RTX 3080 (10 GB) available. Main .venv
  stays pinned — model deps go in an isolated env (.venv-nmfp/.venv-emb, gitignored).

[2026-07-03] — test(tapematch): CC_TAPEMATCH_ADDON Phase 2 calibration COMPLETE — Tier A verdict (dormant)
Changed: tools/tapematch/config.yaml: calibration done over 11 dates. flaw_match_score is the one
  precision-SAFE Tier A signal (TN max 0.133 vs TP→0.900, no triplet-style collision) but coverage is
  ~6% of frozen FN, so a precision-safe threshold nets only +1..+2 TP (+0.1 recall pt). The aggressive
  zero-FP bar 0.143 gave abs fp=10 via TRANSITIVE clustering (per-run guard said "new FP: none" — the
  guard-masking trap; absolute fp is the real gate). Left DORMANT: addon_links.rule_a.enabled=false
  (t_flaw documented 0.45 for opt-in), rule_b/c false, flaw/stationarity/env computation flags false.
  spec_stationarity + env_corr REJECTED (individual gaps fail; Rule B AND-gate recovers 0 — content-
  adjacent same-show collision). Config back at the shipped 41.6% recall / fp=9 baseline (byte-identical).
  CONCLUSION: Tier A forensic signals hit their ceiling; the non-correlating FN bulk needs Tier B/C
  learned similarity. Verdict table + resume steps in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-02] — test(tapematch): CC_TAPEMATCH_ADDON Phase 2 live calibration harness + detached run
Added: tools/tapematch/calibrate_addon.py: DB-only calibration analyzer for the three Tier A signals
  (mirrors calibrate_triplet.py). Per signal: TP / same-date-diff-source-TN distributions, p10(TP)−p90(TN)
  gap gate (ship iff ≥0.10), a zero-FP bar (max-TN) for the lineage-pure flaw path, target-FN coverage,
  and a Rule B conjunction (spec_stationarity AND env_corr) scan. Excludes label_suspect=1 from TP.
Added: tools/tapematch/calib_logs/run_addon_measure.sh: detached (nohup, PPID→init) measurement watcher —
  waits for the population batch + any live session to clear, re-runs any unpopulated date (idempotent),
  then runs calibrate_addon.py + `regression.py score --cached` and writes `ADDON_CALIB_DONE`. Survives
  Claude session limits (the calibration agent died on one). Config: three metric-COMPUTATION flags set
  true (no merge armed — addon_links rules stay false); population is precision-safe.
Note: preliminary (8/11 dates) — flaw_match_score shows a clean zero-FP separation (TN max 0.133 vs TP→0.900,
  16/42 TP recoverable at ~0.14, 0 in-sample FP); stationarity/env reject the p10/p90 gap (conjunctive-only,
  content-adjacent). Full 11-date RESULTS land in calib_logs/addon_calib_progress.log. See CALIBRATION_PROGRESS.md.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 5 (Tier A close-out) — evidence combination + coverage instrumentation
Added: tools/tapematch/tapematch/verdict.py: `addon_links` evaluated in `pair_links` alongside
  every other OR-path — `_rule_a_lone_lineage` (`flaw_match_score >= t_flaw` AND both-side
  `flaw_n_events >= min_events`), `_rule_b_two_leg` (`spec_stationarity >= t_stat` AND
  `env_corr >= t_env`, conjunctive by construction — the only route either signal has into a
  verdict), `_rule_c_belt_and_braces` (`emb_score >= t_emb` AND (`flaw_match_score >=
  t_flaw_weak` OR `spec_stationarity >= t_stat`); `emb_score` has no persisted column yet
  (Task 6) so this rule reads it via `dict.get` and abstains defensively rather than crashing).
  Every rule independently gated on its own `enabled` flag (all `enabled: false`); NULL on ANY
  leg means that rule abstains, never coerced to 0.0. No rule reads `lb_says_same` or
  `entry_lineage` (frozen-set validity guard). `METRIC_KEYS` gains `emb_score` for forward
  round-tripping (always None/absent today — no column exists).
Changed: tools/tapematch/tapematch/verdict.py: **reconciled** the Task 2.3 standalone flaw
  OR-path (previously gated solely on `flaw_fingerprint.enabled`, living directly in
  `pair_links`) into Rule A — removed the standalone block so there is exactly one canonical
  flaw-fingerprint merge path, not two competing ones. `flaw_fingerprint.enabled` now only
  gates whether the metric is *computed* (cli.py, unchanged); `addon_links.rule_a.enabled`
  gates whether it may *merge*.
Added: tools/tapematch/config.yaml `addon_links:` block — `rule_a` (`t_flaw: 0.6`,
  `min_events: 8`, carried over unchanged from the superseded `flaw_fingerprint.
  merge_threshold`/`min_events_merge`), `rule_b` (`t_stat: 0.7`, `t_env: 0.90`), `rule_c`
  (`t_emb: 0.70`, `t_flaw_weak: 0.4`, `t_stat: 0.7`) — all `enabled: false`, every threshold
  marked "uncalibrated — set by Calibration protocol". Removed the now-superseded
  `flaw_fingerprint.merge_threshold`/`min_events_merge` keys (comment points to
  `addon_links.rule_a`).
Added: tools/tapematch/regression.py: `_ADDON_METRIC_COLS` + `_addon_coverage()` /
  `_print_addon_coverage()` — Task 5.3 per-signal FN coverage. For each of
  `flaw_match_score`/`spec_stationarity`/`env_corr`/`emb_score` that exists as a `pairs`
  column, counts how many frozen FN pairs (positives the candidate verdicts
  `different_family`) carry a non-NULL value; printed as a new section after `score --cached`'s
  existing confusion-matrix output (columns not yet present, e.g. `env_corr`/`emb_score` in
  the current `observations.db`, are omitted rather than shown as a misleading 0). Bounds each
  signal's max possible recall contribution and surfaces low-coverage signals immediately.
Added: tools/tapematch/tests/test_verdict_equivalence.py — `test_addon_links_rule_a_fires_
  when_enabled_and_gated`, `test_addon_links_rule_a_null_column_is_inert_on_historical_rows`,
  `test_flaw_fingerprint_enabled_alone_no_longer_merges` (proves the reconciliation — the old
  key alone can no longer merge), `test_addon_links_rule_b_two_leg_conjunctive`,
  `test_addon_links_rule_c_abstains_when_emb_score_absent` (both key-missing and
  explicit-None forms), `test_addon_links_rule_c_fires_when_enabled_and_gated`,
  `test_addon_links_all_disabled_is_byte_identical_to_no_addon_links`. Full non-`test_batch_
  queue` suite: 269 passed, 2 pre-existing unrelated failures in
  `test_find_lb_folders_no_audio.py` (untouched by this change — `find_lb_folders` return-type
  drift from an earlier uncommitted `tapematch_session.py` edit), 4 deselected.
Not done: real-audio calibration (CC_TAPEMATCH_ADDON.md Calibration protocol) for any rule —
  all `addon_links` rules `enabled: false`; do not enable without a fresh gap check on frozen
  TP/same-show-TN/FN per rule. Task 6 (`emb_score` column + Rule C activation) and Task 7 not
  started.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 4 (Tier A) — band-limited envelope correlation
Added: tools/tapematch/tapematch/match.py: `envelope_corr(mono_a, mono_b, sr, cfg, hf_ceiling_hz_a,
  hf_ceiling_hz_b, speed_ratio, offset_sec)` — zero-phase Butterworth bandpass both sides to
  `[band_lo_hz, min(hf_ceiling_a, hf_ceiling_b, band_hi_cap_hz)]` (200 Hz / 2000 Hz defaults, never
  above the narrower side's HF ceiling), computes a 20 Hz RMS envelope per side (`_rms_envelope`
  helper), affine speed-maps A's envelope clock onto B's (`t_mapped = offset_sec + speed_ratio *
  t_a`, identical convention to `flaw_match_score`), linearly interpolates B onto the mapped grid,
  and returns Pearson correlation over the overlap. Returns `None` (never 0.0) when the band is
  degenerate (narrower HF ceiling at/below `band_lo_hz`) or mapped overlap < `min_overlap_min`
  (10 min default). **High same-show collision risk** — envelope is music-dominated (the triplet
  failure mode); flagged explicitly in match.py/config.yaml/WORKFLOW.md as conjunctive-only and
  banned from ever becoming a lone-merge OR-path, even post-calibration (spec 4.2 hard rule).
Added: config.yaml `envelope_corr:` block — `band_lo_hz: 200.0`, `band_hi_cap_hz: 2000.0`,
  `filter_order: 6`, `frame_rate_hz: 20.0`, `min_overlap_min: 10.0`, `enabled: false` (uncalibrated).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.env_corr REAL`
  (idempotent ALTER); `insert_pairs` populates it from the run JSON's `secondary_pairs` entries
  (same dormant-NULL pattern as `spec_stationarity`/`flaw_match_score`).
Changed: tools/tapematch/tapematch/cli.py: cross_pairs secondary-match loop computes `env_corr` per
  pair when `envelope_corr.enabled` (reuses the Task 3 lineage pre-pass `hf_ceiling_hz` values and
  the pair's speed ratio/coarse offset, same predicted-lag-aware offset computation as the
  `flaw_match_score` block); `None`/skipped entirely while disabled (zero cost dormant).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains `env_corr` for cached-scoring
  round-tripping. Deliberately **no OR-path** — spec 4.2 bans a lone-merge path for this signal
  permanently (not just pending calibration, unlike `spec_stationarity`); combination rules are
  Task 5's `addon_links` (e.g. AND'd with `spec_stationarity`).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains `env_corr`.
Added: tools/tapematch/tests/test_envelope_corr.py — 7 synthetic tests (no live audio): same
  recording + fixed band-limit/EQ + noise → corr ≥0.9; independent signals → corr ≤0.5; <10 min
  overlap → None; offset pushes overlap out of range → None; ±5000 ppm speed-warp robustness (both
  directions) → corr ≥0.85; HF ceiling below `band_lo_hz` → None. Extended
  tests/test_verdict_equivalence.py with `test_env_corr_null_column_is_inert`, proving the new
  nullable column leaves `pair_links` byte-identical on historical (NULL) and populated-but-dormant
  rows, alongside `spec_stationarity`. Full suite (Tasks 2/3/4 + verdict equivalence): 193 passed.
Not done: real-audio calibration (CC_TAPEMATCH_ADDON.md Calibration protocol) — `enabled: false`,
  no verdict wiring change; do not enable or add to Task 5 `addon_links` before that gap check.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 3 (Tier A) — spectral-ratio stationarity
Added: tools/tapematch/tapematch/match.py: `spectral_ratio_stationarity(mono_a, mono_b, sr, cfg,
  hf_ceiling_hz_a, hf_ceiling_hz_b, noise_floor_db_a, noise_floor_db_b, predicted_lag=None)` —
  reuses the windowed-coverage grid (own `spectral_stationarity.*` knobs; per-window local-lag or
  predicted-lag-centered search, same as `secondary_corr_pair`); per window converts both aligned
  sides to log-mel (32 bands via `librosa.filters.mel`, capped at
  `min(hf_ceiling_a, hf_ceiling_b, 0.45*sr)`), excludes frames where either side is below its own
  `noise_floor_db + noise_floor_margin_db`, takes `R_w[band] = median_t(logmel_A-logmel_B)` over
  kept frames; `stationarity = 1 - mean_band(std_w(R_w)) / stationarity_norm_db` clipped [0,1].
  Returns `None` (never 0.0) below `stationarity_min_windows` (6) usable windows or when the HF cap
  is 0. Phase-blind/magnitude-only, so it works where `residual_corr` dies (corr ~0.005).
Added: config.yaml `spectral_stationarity:` block — grid/mel/noise-floor/norm knobs,
  `stationarity_norm_db: 6.0`, `stationarity_min_windows: 6`, `enabled: false` (uncalibrated).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.spec_stationarity REAL`
  (idempotent ALTER); `insert_pairs` populates it from the run JSON's `secondary_pairs` entries
  (same dormant-NULL pattern as `flaw_match_score`).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains `spec_stationarity` for
  cached-scoring round-tripping. Deliberately **no OR-path** — spec bans a lone-merge path for this
  signal (content-adjacent; combination rules deferred to Task 5's `addon_links`, conjunctive only).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains `spec_stationarity`.
Changed: tools/tapematch/tapematch/cli.py: moved the "lineage pre-pass" (`lineage_evidence` per
  source — `hf_ceiling_hz`/`noise_floor_db`) earlier, ahead of the secondary-match cross_pairs loop
  instead of after it (pure reordering, unconditional either way, no behaviour change) so
  `hf_ceiling`/`noise_floor` are available for the per-pair stationarity call; cross-pair loop scores
  `spec_stationarity` gated on `spectral_stationarity.enabled` (zero cost while dormant).
Added: tools/tapematch/tests/test_spectral_stationarity.py — same-signal+fixed-EQ high
  stationarity, two-different-signals and slowly-time-varying-EQ low/lower stationarity,
  +-0.4s alignment-jitter robustness, None-not-0.0 on too-short/zero-HF-cap inputs, [0,1] clip
  (7 tests).
Changed: tools/tapematch/tests/test_verdict_equivalence.py — 1 new test proving `spec_stationarity`
  is registered in `METRIC_KEYS` but stays fully inert (NULL or populated-and-high, with or without
  the config block) since no OR-path reads it; other legs' outcomes unaffected by its presence
  (185 tests total in the verdict/flaw/stationarity trio, all green).
Verify before calibration: `noise_floor_margin_db`'s quiet-frame gate compares STFT-power dB
  against `lineage_evidence`'s Welch-PSD dB — an intentional same-side-relative simplification (the
  absolute scale differs; only the per-side comparison matters), but the effective margin should be
  sanity-checked against a handful of real hf_ceiling/noise_floor readings before the Calibration
  protocol's >=100-pair real-audio pass.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 2 (Tier A) — shared-flaw event fingerprint
Added: tools/tapematch/tapematch/match.py: `extract_flaw_events(mono, sr, cfg, trim_head_sec,
  trim_tail_sec)` — per-source flaw timeline (dropout: 20ms-hop RMS >20dB below its 2s local
  median for 40-800ms; click: sample-domain residual >6sigma of local 50ms MAD, isolated <5ms,
  capped at 200 strongest; cut: joint 100ms spectral-centroid+RMS discontinuity >4sigma — extends
  the jump-vs-sigma technique `align.locate_splice_points` uses on a pairwise lag curve to a
  per-source RMS/centroid curve instead, so no reference source is needed). Reuses
  `find_quiet_segments` so between-song gaps are never counted as dropouts/cuts. All detectors are
  memmap-block-read (2h-source safe) except the sample-domain click pass, which materializes one
  float32 residual array (consistent with the existing `lowband_envelope_corr` full-array pattern).
Added: tools/tapematch/tapematch/match.py: `flaw_match_score(events_a, events_b, speed_ratio,
  offset_sec, cfg)` — matched/min(|A|,|B|) dropout+click+cut events after mapping A's clock onto
  B's via the pair's speed ratio + coarse offset (tol 0.5s); returns `None` (never 0.0) below
  `flaw_min_events` (5) — absence of flaws is absence of evidence, not evidence of difference.
Added: config.yaml `flaw_fingerprint:` block — all extraction/scoring/verdict thresholds,
  `enabled: false` (uncalibrated; do not enable without a real-audio gap check per the
  Calibration protocol in CC_TAPEMATCH_ADDON.md).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.flaw_match_score REAL`,
  `flaw_n_events_a/b INTEGER` (idempotent ALTER); `insert_pairs` populates them from the run JSON's
  `secondary_pairs` entries (same dormant-NULL pattern as `fp_triplet_score`).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains the three flaw columns;
  `pair_links` gains an OR-path — `flaw_match_score >= flaw_fingerprint.merge_threshold` AND both
  `flaw_n_events_a/b >= min_events_merge` (8), gated on `flaw_fingerprint.enabled`, inert on NULL
  (mirrors the dormant triplet-fingerprint path exactly).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains the three flaw columns so
  `score --cached` recomputes verdicts when they're populated.
Changed: tools/tapematch/tapematch/cli.py: computes `extract_flaw_events` per source upfront
  (full-length, gated on `flaw_fingerprint.enabled` — zero cost while disabled) alongside the
  existing fingerprint/triplet pass; cross-pair loop scores `flaw_match_score` (offset reuses the
  Task-4 predicted-lag anchor-0 lag when already computed, else one fresh `local_lag` call — flaw
  sets are sparse); run JSON `sources[name]` gains `flaw_event_count` + serialized `flaw_events`
  timeline (variable-length, so run-JSON-only per spec, not the DB).
Added: tools/tapematch/tests/test_flaw_fingerprint.py — synthetic dropout/click/cut injection +
  extraction tests, inherited-flaw pair score ~1.0 under +-5000ppm speed warp, independent-flaw
  pair score ~0, None-not-coerced-to-0.0 sanity, between-song quiet-gap exclusion (10 tests).
Changed: tools/tapematch/tests/test_verdict_equivalence.py — 3 new tests proving the flaw OR-path
  is byte-identical-inert when `enabled: false` (default) or when the DB column is NULL
  (historical rows), and fires correctly when enabled + both gates clear (177 tests total, all
  green; pre-existing `test_find_lb_folders_no_audio.py` failures are unrelated/pre-dated this
  session, confirmed via `git stash`).
Unresolved: the "cut" detector's "reuse/extend the CDR re-tracking (staircase) edit detector"
  requirement is honored as a *technique* reuse (jump-vs-robust-sigma, mirroring
  `align.locate_splice_points`), not a literal call — the staircase detector is inherently
  pairwise (two sources' lag curve), while Task 2.1 specifies a single-source detector. Flag for
  review before calibration.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 1 (Tier 0) — FN forensic audit + label-noise quantification
Added: tools/tapematch/audit_fn.py — recomputes the current corr<0.05 FN population (859 pairs,
  same `verdict.cluster_verdicts` path as `regression.py score --cached`), draws a stratified
  60-pair sample (20 speed-corrected/20 speed-unknown/20 staircase x hf_ceiling-gap secondary
  strata), builds a per-pair evidence dossier (LB source/relation text, raw metrics, a throwaway
  4-band envelope-corr quick check via direct ffmpeg window decode — no session/staging-dir use,
  so the live-session concurrency hazard doesn't apply), and a transparent label_assessment
  heuristic (explicit "different recording" text > taper-name conflict > duration-ratio mismatch
  > explanatory lossy/band-limited lineage > envelope-corr hint > indeterminate).
Added: tools/tapematch/FN_AUDIT_REPORT.md — 60-pair dossier + headline: label-noise rate 36.7%
  (22/60, Wilson 95% CI 25.6-49.3%) extrapolated to the 859-pair population (~315 pairs, CI
  220-424) — re-based recall ceiling **~80.0%** (CI 73.1-86.0%), re-scoping Tiers B/C targets
  down from the naive "no perfect matcher could exceed 100%" framing.
Changed: tools/tapematch_session.py: open_obs_db() gains nullable pairs.label_suspect INTEGER
  (idempotent ALTER; NULL=not-assessed, 1=suspect) so Tier C training/eval can exclude flagged
  pairs. 22 pairs flagged from the sample; frozen-set labels themselves left untouched.

[2026-07-02] — docs(tapematch): CC_TAPEMATCH_ADDON spec — add-on approaches past the 42% recall ceiling
Added: instructions/CC_TAPEMATCH_ADDON.md — three-tier spec for the 93% non-correlating FN bulk:
  Tier 0 FN forensic audit + label-noise quantification (Task 1, sets the honest ceiling and
  pairs.label_suspect flag); Tier A content-blind lineage-forensic signals (Tasks 2-5: shared-flaw
  event fingerprint / spectral-ratio stationarity / envelope corr conjunctive-only / verdict
  addon_links + coverage reporting); Tier B pretrained neural-fingerprint embedding eval (Task 6);
  Tier C contrastive lineage embedding with same-show hard negatives, curator labels eval-only
  (Task 7). Codifies the triplet lesson (content-based similarity collides on same-concert
  different-source negatives) as a mandatory calibration protocol: real same-date TN population,
  gap >= 0.10 or structural reject, absolute fp <= 9 guard.
Added: TODO.md — TODO-199 tracking the addon spec.

[2026-07-02] — feat(tapematch): Tasks 5-7 (estimate_ratio_v2 / lag-residual / pyin / triplet fingerprint); triplet REJECTED; ~42% recall ceiling documented
Added: tools/tapematch/tapematch/match.py — estimate_ratio_v2 (prior-centered, confidence-reporting;
  old estimate_ratio kept as estimate_ratio_v1_deprecated for A/B), duration_ratio_prior,
  pitch_ratio_pyin + _pick_pitch_windows (Tasks 5 / 6.2), and a DORMANT ratio-invariant triplet
  fingerprint (triplet_hashes / triplet_window / _fingerprint_peaks / _quant_log, Task 7).
Added: tools/tapematch/tapematch/align.py — residual_ppm_from_lag_curve (r²>0.85 + <4-anchor guards,
  Task 6.1), wired into the PRIMARY residual-corr loop in cli.py only (never before secondary_corr_pair).
Changed: tools/tapematch/tapematch/cli.py — v2 confidence gate (align.ratio_confidence_min) →
  speed_kind="speed-unknown" routing + count; duration prior plumbed from trim_bounds; per-pair
  fp_triplet_score computed when triplet enabled.
Changed: tools/tapematch/tapematch/verdict.py — triplet OR-path (fingerprint.triplet), inert on the
  NULL column → 164 verdict-equivalence tests stay byte-identical.
Added: observations.db pairs.fp_triplet_score column (CREATE + idempotent ALTER in open_obs_db;
  insert_pairs persists it; regression.py auto-selects via METRIC_KEYS). New tools/tapematch/calibrate_triplet.py
  (Task 7.4 DB-only calibrator) + RECALL_RECOVERY_REPORT.md + cat3_rerun_report.md.
Rejected: fingerprint.triplet.enabled=false — live calibration (116 real pairs) showed same-show
  different-source pairs collide (triplet Dice 0.63–0.65, OVERLAPPING true-same-source 0.66, gap −0.012);
  at threshold 0.45 it manufactured 5 false merges on frozen negatives. Disabled; code kept dormant.
Result: final precision-safe recall 41.6% / precision 98.6% / fp=9 (vs 38.3%/98.2% audit baseline).
  estimate_ratio_v2 precision-safe but only +0.2 on Cat-1 dates; ratio_confidence_min sweep 6.0→4.5
  recovered nothing (pairs resample but corr stays 0.002–0.010); Cat-3 re-run 0/6 flipped. 93% of FN
  are non-correlating even when correctly speed-aligned → >80% needs the out-of-scope contrastive-
  embedding model. Full analysis: tools/tapematch/RECALL_RECOVERY_REPORT.md.
Added: tools/tapematch/tests/test_speed_v2_pyin.py (7) + test_triplet_fingerprint.py (4) — 175 tests green.
Config: align.ratio_confidence_min=6.0, align.pyin_fallback=true, fingerprint.triplet.* (enabled=false).

[2026-07-02] — feat(tapematch): calibration verdict — staircase 0.40 KEPT (+5 TP, 0 new FP) + curator/lo-fi live wiring in cli.py
Changed: tools/tapematch/tapematch/cli.py — production-wired Tasks 4.1/4.2: `_pair_metrics` now
  supplies lb_a/lb_b (folder-name regex), lineage pairs (new `--lineage-db`, defaults to
  data/losslessbob.db, inert on failure) and hf_ceiling/nyquist from a lineage-evidence pre-pass
  moved before clustering (print section reuses it; byte-identical output). Validated live on the
  1991-02-10 session (rc=0) + 164 equivalence tests green.
Added: tools/tapematch/CALIBRATION_PROGRESS.md — calibration results: staircase fp bar 0.40 nets
  recall 39.2%→39.6% (+5 TP, all 1996-11-04 staircase pairs fp 0.433–0.447) with ZERO new FP on
  2965 frozen pairs → kept per decision rule. Curator relaxation NOT shipped as measured
  (entry_lineage covers 244/1575; lb_says_same keying tautological — human_judgment NULL DB-wide).
  1993-06-27 staircase FNs (fp 0.27–0.37) overlap negatives (≤0.387) → unrecoverable, Cat-1 land.
Fixed: session concurrency hazard documented — `regression.py score --dates` runs LIVE sessions
  sharing /mnt/DATA0/examples/tapematch staging; a concurrent run killed the batch's 1996-11-04
  session (re-run cleanly after). Never run live sessions concurrently.
Added: tools/tapematch/calib_logs/ — run_batch.sh/run_batch2.sh (detached calibration batches),
  analyze_staircase.sh (A/B + fp/hiss band table), per-date logs, staircase_analysis.txt.

[2026-07-02] — feat(tapematch): Task 1 regression harness + verdict.py extraction (CC_TAPEMATCH_FIXES) + Tasks 2-4 no-audio scaffolding
Recovered: tools/tapematch/observations.db — the labeled-pairs DB (8022 pairs / 885 dates) had
  been moved to ~/.local/share/Trash on 2026-06-25 and the working copies left as 0-byte stubs.
  Restored (copied from Trash, original kept as backup); verified it reproduces the spec baseline
  signature exactly (fn=957; raw-pairs confusion 663/1066/12/1422 = P0.982/R0.383).
Added: tools/tapematch/tapematch/verdict.py — single source of truth for the pairwise clustering
  decision (Task 1.3). Pure `pair_links()` predicate mirroring match.cluster's OR-logic;
  per-pair `fp_threshold()` with staircase- (Task 3.2) and curator-lineage- (Task 4.1) conditional
  fingerprint thresholds; `_effective_hiss_median()` lo-fi relaxation (Task 4.2); transitive
  `cluster_verdicts()` (union-find); `load_lineage_pairs()` from entry_lineage.
Added: tools/tapematch/regression.py — recall/precision regression harness (Task 1.1/1.2/1.3).
  `freeze` extracts labeled pairs from the latest_pairs view (deduped) → regression_set.json,
  records the audit baseline + logs dedup drift; `score --cached` re-scores from stored rows with
  no audio (reproduces baseline exactly: R39.2/P98.6, zero delta, exit 0); `score --dates/
  --all-frozen-dates` re-runs sessions live (audio). New-FP on a frozen negative → exit 1.
Changed: tools/tapematch/tapematch/match.py: cluster() gains an optional `link_fn` predicate so
  cli.py can route the decision through verdict.pair_links (behaviour-identical; proven by
  tests/test_verdict_equivalence.py, 160 randomized cases). tapematch/cli.py clustering now calls
  it via a per-pair metrics builder.
Added: config.yaml fingerprint.cluster_threshold_staircase (0.40) / _curator (0.43) and
  secondary_match.hiss_merge_median_lofi (0.40) / hiss_lofi_ceiling_hz (12000). All optional —
  absent keys restore the prior single-scalar behaviour.
Added: tapematch_session.py: pairs table gains nullable windowed_frac/hiss_frac/hiss_median/
  fp_score/nyquist_capped_a/nyquist_capped_b columns (CREATE + idempotent ALTER migration in
  open_obs_db); insert_pairs now persists them from the run's secondary_pairs/sources JSON so
  Tasks 3/4 become score --cached-able once dates are re-run.
Added: tools/tapematch/rerun_cat3.py — Task 2 focused Cat-3 re-run (stage the pair alone, re-run,
  report before/after verdict). Parameterized (--list/--dates/--limit/--dry-run); execution is
  audio-gated. NOTE: the documented FN query matches 137 pairs, not the spec's stale "6".
Added: tools/tapematch/tests/test_verdict_equivalence.py — 164 tests: refactor equivalence +
  conditional-threshold + lo-fi + transitivity units.
Note: Task 3.1 (either-side staircase fallback) was ALREADY implemented in cli.py (line 497) — the
  spec premise was stale, like the latest_pairs view and migrate_observations.py. Pre-existing:
  the test_batch_queue-family tests hang when run against the real mounted /mnt collection
  (unrelated to this change; the 208 tests touching changed code all pass in 8.4s).

[2026-07-02] — fix(scraper): BUG-233 torrent filename data loss + close BUG-234 as verified-correct
Fixed: backend/wtrf_scraper.py: _download_torrent Content-Disposition parsing (BUG-233) — the old
  regex matched the RFC 5987 `filename*=UTF-8''real.torrent` parameter and captured "UTF-8" instead
  of the real name, so every batch-run download landed at the same "UTF-8.torrent" path and
  overwrote the previous one. Now prefers a plain `filename="..."` parameter and, only when absent,
  parses `filename*=charset''value` per RFC 5987 (strips the charset prefix, URL-decodes the value).
Fixed: BUGS.md/BUGS_DONE.md: BUG-234 closed as Wontfix — logged into WTRF and confirmed topic 55005
  is a legitimate 3-show Crystal Cat "Garden Party" boxset (CD1 Phoenix 5/13/25, CD2 Chula Vista
  5/15/25, CD3 George WA 5/25/25); LB-16404/16405/16406 each genuinely own one CD's checksums, so
  all three matching the same post is correct, not a signal collision.
Changed: backend/wtrf_scraper.py: _download_torrent now prefixes every saved filename with
  `LB-{lb_number:05d}-`, even when a real name comes from Content-Disposition. Needed because
  BUG-234's box-set case has three LB entries sharing one physical .torrent, so the header-derived
  filename alone was still identical across entries and would overwrite on disk per download.

[2026-07-01] — chore(scraper): re-ran WTRF skipped-review batch against checksum-search gains (TODO-197)
Changed: wtrf_skipped_review_rerun.md: re-ran all 85 LB entries from wtrf_skipped_review.md through
  tools/wtrf_fetch_missing.py post-BUG-231/232; 30/85 (35%) now resolve automatically (28
  definitive, 1 high, 1 medium), 13 needs_review, 11 ambiguous, 31 not_found.
Fixed: BUGS.md: BUG-233 note updated — confirmed the junk "UTF-8.torrent" filename causes batch
  runs to silently overwrite all but the last downloaded torrent (data loss, not just cosmetic).
Added: BUGS.md: BUG-234 — checksum body-search false-matched LB-16404/16405/16406 (three different
  shows) to the same WTRF topic 55005; needs investigation into over-broad checksum signal reuse.

[2026-07-01] — feat(gui): Concert Ranker audio metrics visualizations on the Quality tab
Added: backend/app.py: GET /api/quality/<lb_number> now also returns a `metrics` sub-dict —
  stereo/mono + width, clip_fraction, crowd_snr_db, bass/mud/harsh tonal-balance ratios, and
  source-type flags (lossy/minidisc/32k DAT/cassette/TV-band) — read from
  quality_recording_metrics.metric_json and banded to human labels via concert_ranker's own
  scoring.band_metric()/config.resolve_band_set() (same thresholds as verdict_text) so the UI
  never re-implements the banding logic. New helper: backend/app.py:_quality_metrics_for().
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: QualityMetricsPanel renders
  below the LB Rating/AI Quality Index tiles — thin tone-colored MetricBar meters for channels
  (mono/stereo + width), clipping %, crowd separation (dB), and bass/mud/harsh tonal balance, plus
  FlagChip pills for any tripped source-type flags (or a "no flags" note).
Added: gui_next locales (en/de/es/it/nl/fr): library.quality.metrics.{label,channels,mono,stereo,
  clipping,crowdSeparation,tonalBalance,bass,mud,harsh,balanced,sourceFlags,noFlags}.

[2026-07-01] — feat(gui): Quality page in library detail panel (LB Rating + AI Quality Index)
Added: backend/app.py: GET /api/quality/<lb_number> returns the latest Concert Ranker scan's
  abs_score/abs_grade/final_score/rank_in_family/verdict_text for one recording (204 if unscanned).
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: new "Quality" tab on the
  recording detail panel (alongside Overview/Assets/Seed & Share, owned rows only) — QualityZone
  lazy-fetches /api/quality/<lb> and shows the catalog LB Rating side by side with the AI Quality
  Index (Concert Ranker's abs_grade + abs_score/100), bold Fact cards, plus the verdict_text note.
Added: gui_next locales (en/de/es/it/nl/fr): library.panel.tabQuality, library.quality.{label,
  lbRating,aiIndex,notScannedNote}.

[2026-07-01] — fix(scraper): WTRF checksum body-search + cross-recording guard (BUG-231/232)
Added: backend/db.py: lookup_checksum_owners() maps a set of MD5/SHA1 hashes to the lb_numbers
  that own them in the checksums table (chunked to stay under SQLite's parameter limit).
Added: backend/wtrf_scraper.py: deterministic checksum body-search as the primary lookup —
  _search_board gained a subject_only flag (False searches post bodies), _checksum_search_terms
  picks up to 3 of the entry's own hashes, and find_torrent_for_lb tries them first; a full-text
  hit lands directly on the correct taper's post regardless of topic-title date format (BUG-232).
Changed: backend/wtrf_scraper.py: date-variant subject search is now the fallback and unions
  candidates across ALL variants instead of breaking at the first that returns results; entries
  with an unparseable date (xx/xx/YY) are no longer rejected up front when checksums are available
  for a body search.
Fixed: backend/wtrf_scraper.py: candidates whose body checksums resolve to a different lb_number
  are now disqualified (they document another taper's recording), so an entry with no post of its
  own no longer produces a false "ambiguous" tie between two other tapers' posts (BUG-231).
  Verified: LB-16644 (nightly moth, Abilene 2026-05-01) now resolves definitively to topic 60289
  instead of tying LB-16616 (BenM) and LB-16617 (soomlos).

[2026-07-01] — feat(gui): double stage-icon size on pipeline detail screen
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageStepper now passes
  size={48} (was default 24) to StageNode, doubling the Verify/Lookup/LBDIR/Rename/Collect tile icons
  on the pipeline detail screen's stage stepper row.
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineIcon.tsx, index.css: round glyph size
  and tile border-radius to even pixel values (was e.g. 27px glyph / 14.4px radius), which landed on
  half-pixel boundaries and rendered slightly blurred after the size increase; now sharp at any size.

[2026-07-01] — fix(backend): treat missing self-referencing lbdir-*.txt manifest as pass in LBDIR check
Fixed: backend/checksum_utils.py: in verify_folder_lbdir, a listed-but-not-on-disk file whose name
  matches the lbdir-*.txt manifest is now counted as pass (green) instead of missing. The manifest
  self-references its own checksum, which can never match the finished file, so it's unreconcilable —
  a folder whose only "missing" entry is the manifest now reaches status=pass instead of missing_files.
Added: backend/checksum_utils.py: _is_lbdir_manifest_name() helper + _LBDIR_MANIFEST_RE.

[2026-07-01] — feat(gui): custom app icon for Electron window/taskbar + packaged installers (TODO-196)
Added: gui_next/resources/icon.png: LB blue logo icon (1000x1000 PNG) picked up by electron-builder
  buildResources convention for packaged app/installer icons on Windows/macOS/Linux.
Changed: gui_next/src/main/index.ts: added `icon` (path resolved for packaged vs dev) to the
  BrowserWindow constructor. On native Wayland (GNOME) the dock icon is resolved only by matching
  the window's Wayland app_id to an installed .desktop basename, so a documenting comment records
  that the dev app_id is "losslessbob-next" (from package.json "name").
Added: gui_next/resources/losslessbob-next.desktop: dev-helper .desktop template, named to match
  the dev Wayland app_id. Install to ~/.local/share/applications/losslessbob-next.desktop so the
  `npm run dev` window shows the LB icon in the GNOME dock (BrowserWindow `icon` and StartupWMClass
  are ignored on native Wayland). The packaged AppImage gets its own generated .desktop from
  electron-builder and is unaffected.

[2026-07-01] — docs: close BUG-218, already fixed (BUG-218)
Fixed: BUGS.md/BUGS_DONE.md: BUG-218 (performance screen column widths) moved to BUGS_DONE.md as
  Fixed — no code change needed, user confirmed the performance-view table columns are already
  correct. On review, ScreenLibrary.tsx's performance table column model (~1849-2126) is
  internally consistent with the current 10-column layout.

[2026-07-01] — fix(gui): Pipeline screen untranslated English throughout (BUG-201)
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: STATE/BUCKET step-state
  and bucket vocabularies and DEFAULT_STAGES stage labels were plain hardcoded strings baked into
  module-level consts, so StatusTag/StageNode/StageStepper/QueueRow always rendered English text
  regardless of locale. Converted each entry to a `labelKey` resolved via `t()` inside the
  consuming components (all four already are or now are function components with hook access);
  DEFAULT_STAGES reuses the pre-existing but previously-unused `pipeline.queue.{verify,lookup,
  lbdir,rename,collect}` keys.
Fixed: gui_next/src/renderer/src/components/pipeline/lookupState.ts: STATE_TONE lookup-state
  labels (Matched/Incomplete/Not found/Duplicate/XRef) hardcoded; changed to `labelKey` pointing
  at the existing `lookup.states.*` keys, resolved at each of the three call sites in
  LookupDetail.tsx (which already had `useTranslation()`).
Fixed: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: "Type" table header, row
  "Open"/"Pin LB-XXXXX & continue" button title/label, and "{n} row(s)" group-count text were
  hardcoded; wired to `t()` with new `lookup.table.openTitle`/`pinAndContinue` keys and the
  existing `lookup.table.type`/`lookup.status.rows` keys.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: systematic pass replacing ~110
  hardcoded English strings across VerifyStageContent, LookupStageContent, RenameStageContent,
  CollectReadyDetail/CollectStageContent, LbdirStageContent, DetailPanel, the queue rail, table
  headers/row actions, and the context menu. STATE_LABEL (LBDIR status pills) and the file-error
  ERROR_MSG map were frontend-owned lookups keyed by stable backend enum codes (status/error_code)
  — converted their values to translated labelKeys the same way as PipelineParts, since only the
  key is backend-controlled, not the displayed text. deriveFolderStatus() (bucket/reason text for
  the batch table's Status column) now takes a `TFunction` param and returns translated
  label/reason strings instead of hardcoded English, reusing pipeline.stepStates/buckets keys
  where the wording overlaps. Left untouched, by design: raw backend `step.label`/`step.error`
  free-text values (e.g. verify's "Pass"/"Mismatch", lbdir's per-file messages, file-stage
  error.error fallback) — these originate as English strings from backend/app.py with embedded
  dynamic data and can't be safely mapped to locale keys without backend i18n plumbing; see
  TODO-195.
Added: gui_next/src/renderer/src/locales/en.json: ~120 new keys under `pipeline.*` (rerunStage,
  verify.*, lookup.*, rename.*, lbdir.*, collect.* additions, stepStates.*, buckets.*, status.*,
  detail.*, table.* additions, contextMenu.*, queueRow.*) plus `lookup.table.openTitle`/
  `pinAndContinue`.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ran deepl_translate_gui_next.py
  for all new keys, then hand-corrected a handful of single ambiguous words DeepL left as English
  in 4/5 languages (pipeline.buckets.shelf, pipeline.contextMenu.shelve/unshelve) for consistency
  with sibling `pipeline.filter.shelf` wording.

[2026-07-01] — fix(gui): Map screen renders blank — CSP frame-src/origin mismatch (BUG-215)
Fixed: gui_next/src/renderer/src/screens/ScreenMap.tsx:63: MAP_URL hardcoded
  `http://localhost:5174/map` for the live-map iframe src, but index.html's CSP
  frame-src/connect-src/img-src directives only allowlist `http://127.0.0.1:5174`
  (matching window.api.flaskBase, the convention every other screen uses). CSP treats
  localhost and 127.0.0.1 as distinct origins, so the browser silently blocked the
  iframe navigation, leaving the Map screen blank/white. Changed MAP_URL to
  `${window.api.flaskBase}/map`, matching the CSP allowlist and the rest of the app.
Changed: gui_next/src/renderer/src/locales/{en,de,fr,es,nl,it}.json: map.desc text
  updated from "localhost:5174/map" to "127.0.0.1:5174/map" to match the corrected URL.

[2026-07-01] — fix(gui): Library search/filter state survives navigation (BUG-219)
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: react-router unmounts ScreenLibrary
  on route change, so the recording-lens (scope/query/activeDecade/activeStatus/activeRating/
  activeSource/activeHealth) and performance-lens (query/activeDecade/activeYear/activeCoverage/
  activeSource/activeRating/perfView, in the PerformanceLensView child component) filter state
  were plain useState and reset to defaults every time the user navigated away and back. Added a
  new module-scope `useLibraryFilterStore` (zustand, no persist middleware — survives route
  changes within a session, not app restarts) and swapped both lenses' filter useState calls for
  it. Store setters mirror React's `Dispatch<SetStateAction<T>>` signature so existing
  `toggleSet()`/`setX(new Set())` call sites needed no changes. View/selection-only state
  (groupByYear, sortKey/sortDir, selectedLb, detailPanelOpen, checkedIds, expandedShows, etc.)
  intentionally left as local useState — out of scope for a search/filter bug. `tsc --noEmit`
  clean for this file (pre-existing unrelated errors remain in other files).

[2026-07-01] — fix(backend): scrape_start now queues gap LB numbers, not just stubs (BUG-220)
Fixed: backend/app.py: scrape_start's gap-fill loop (~line 1816) inserted a `missing`
  placeholder via insert_missing_entry() for every LB number in [start_lb, effective_end]
  with no existing checksums row, but never added those numbers to `lb_numbers`, so
  `_start_scrape_thread` never actually scraped them — including user-typed start_lb/end_lb
  boundaries. Now gap numbers are appended to `lb_numbers` (and the list re-sorted) after
  stubbing, except any gap number whose lb_master.lb_status is 'private' — preserving the
  route's documented private-LB exclusion. Verified with an isolated temp-DB simulation:
  gaps get queued and end up scraped/re-marked, private gaps are skipped, existing
  checksum'd numbers are untouched.

[2026-07-01] — chore(backend): consolidate all log files under data/logs/
Added: backend/paths.py: `LOGS_DIR = DATA_DIR / "logs"`, created by `ensure_data_dirs()`.
Changed: main.py (`losslessbob.log`, `startup.log`), cli.py (`_daemon_log_file()` ->
  `backend.log`), backend/paths.py (`LOG_FILE` -> `scraper.log`) now all write under
  `data/logs/` instead of loose at `data/` root. Existing loose log files at `data/` root
  and stray scratch logs at the repo root / `tools/tapematch/` moved into `data/logs/`
  (filesystem move only — `data/` is already gitignored wholesale, no tracked-file changes).

[2026-07-01] — fix(gui): consolidate LB detail-page URL construction (BUG-221)
Added: gui_next/src/renderer/src/lib/lbUrl.ts: `lbDetailUrl(lb)` — one helper that always
  zero-pads and "LB-"-prefixes an LB number before building the losslessbob.wonderingwhattochoose.com
  detail-page URL.
Fixed: gui_next/src/renderer/src/components/library/DetailPanel.tsx,
  gui_next/src/renderer/src/screens/ScreenLibrary.tsx,
  gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx,
  gui_next/src/renderer/src/screens/ScreenSearch.tsx,
  gui_next/src/renderer/src/screens/ScreenCollection.tsx: 5 call sites each built the
  detail-page URL inline with inconsistent formats — 2 sites interpolated `row.lb` raw
  (404 whenever it wasn't already zero-padded/prefixed). All 5 now call `lbDetailUrl()`;
  DetailPanel/ScreenLibrary pass `row.lbNumber` instead of `row.lb`.

[2026-06-30] — fix(backend): LBDIR reconcile/move-extras now sync qBittorrent per-file paths (BUG-229)
Fixed: backend/qbittorrent.py: `/api/lbdir/apply_reconcile` (renames a file in place to match the
  lbdir manifest) and `/api/lbdir/move_extras` (moves stray files into `<folder>/extras/`) both
  change file paths *inside* an unchanged root folder. Neither BUG-228's fix nor the prior
  `relocate_tracked_torrent()`/`rename_torrent_root()` machinery covers this — those only handle
  the whole root folder moving or being renamed, via qBittorrent's `renameFolder`/`setLocation`.
  qBittorrent tracks each file's path within a torrent independently, so a same-folder file
  rename/move it wasn't told about shows that file as missing and stalls seeding for it, even
  though the root folder itself never moved. New `rename_file()` (`POST
  /api/v2/torrents/renameFile`, the per-file counterpart to `rename_torrent_root`'s
  `renameFolder`) and `sync_file_renames()` (resolves the tracked torrent for a folder the same
  way `relocate_tracked_torrent()` does, applies each `rename_file()` call, then one recheck).
Added: backend/filer.py: `_sync_qbt_file_renames()`, the credential-loading best-effort wrapper
  around `qbittorrent.sync_file_renames()`, mirroring `_sync_qbt_location()`.
Added: backend/app.py: `_resolve_lb_number_for_folder()` (my_collection row, else `LB-NNNNN` in
  the folder name, else a "Pin & continue" `folder_lb_link`) shared by both endpoints below to
  find which lb_number's qBittorrent tracking needs updating.
Changed: backend/app.py: `lbdir_apply_reconcile` and `lbdir_move_extras` now call
  `_sync_qbt_file_renames()` after successfully applying file moves/renames on disk.

[2026-06-30] — fix(backend): rename endpoints now sync qBittorrent save path/root folder name (BUG-228)
Fixed: backend/app.py: `/api/rename/apply` and `/api/folder/rename` performed the filesystem
  rename and logged rename_history, but never told qBittorrent — a torrent already tracked in
  qBittorrent (added_to_qbt=1) for that lb_number would keep expecting the old folder name/path
  forever unless a later "file" pipeline step happened to trigger a resync, breaking seeding
  in between. Both endpoints now call `backend.filer._sync_qbt_location()` (best-effort, never
  raises) after a successful rename when lb_number is known — `rename_apply` uses the lb_number
  already sent per-item by ScreenRename.tsx; `folder_rename` resolves it from the my_collection
  row (if already filed) or, failing that, a "Pin & continue" folder_lb_link (BUG-212).
Fixed: backend/qbittorrent.py: `relocate_tracked_torrent()`'s DB-tracked branch (an existing
  `torrents` row already matches lb_number+source_folder) called `set_location()` but never
  `rename_torrent_root()` or `recheck_torrent()`, so a rename (with or without a move) on an
  already-synced torrent left qBittorrent's root folder name stale — only the fallback branch
  (used for untracked/first-time syncs) did the full rename+recheck sequence. The DB-tracked
  branch now also calls `rename_torrent_root()` when the folder name changed and always
  triggers `recheck_torrent()` afterward, matching the fallback branch's behavior.

[2026-06-30] — feat(scraper): WTRF candidates gain a download-date window filter + MD5/SHA1 scoring (TODO-194)
Added: backend/wtrf_scraper.py: `_entry_download_date()` parses the curator's own acquisition
  date from the LAST "bittorrent download MM/YY" note in `entries.description`; `_months_before()`
  computes a cutoff `_DOWNLOAD_WINDOW_MONTHS` (6) before it; `_parse_post_date()` reads each
  candidate's "« on: <Month DD, YYYY> »" timestamp from its `div.keyinfo` (a sibling of the post
  body div, so a new `post_date` field was added to `_fetch_topic()`'s return dict). A post can't
  be the source of a download that happened more than 6 months before it was made, so
  `find_torrent_for_lb()` now hard-disqualifies any candidate posted before that cutoff —
  verified live: LB-16627's stale 2024-10-14 candidate is now filtered out while its genuine
  match still downloads `definitive`; LB-16633/16632's only candidate (already disqualified by
  BUG-227's LB-tag check) is independently also disqualified on date (posted 2025-08-06, cutoff
  2025-11-01).
Added: backend/wtrf_scraper.py: `_score_candidate()` Round 1b matches `chk_type in ('m', 's')`
  (MD5/SHA1 checksums, e.g. older SHN-era "checksum *filename" lines) in addition to the existing
  FFP ('f') round — some posts list only MD5/SHA1 sums, not FFP fingerprints. A hit now scores
  `md5_matches` at the same 100 pts/definitive tier as `ffp_matches` in `_classify_confidence()`.

[2026-06-30] — fix(concert-ranker): de-confound sibilance_ratio_db + calibration scan investigation (TODO-183)
Fixed: concert_ranker/features.py: `_sibilance_native()`'s `sibilance_ratio_db` was a plain
  `sib - ref_mid` ratio. A calibration scan (scan_id=20, 107 recordings) showed it correlated
  POSITIVELY with rating in all 4 source classes (rho +0.50 to +0.67) — backwards from its
  polarity=-1, the same overall-brightness confound `harsh_ratio_db` had before its ROUND-2 fix.
  Rewrote as a local excess vs flanking bands (2-5 kHz below, 9-14 kHz above), mirroring the
  proven harsh_ratio_db fix.
Added: A re-scan (scan_id=21, 107 recordings) confirmed the fix only partially worked: rho
  dropped to +0.50/+0.50/+0.57 (SBD/AUD/UNKNOWN), still positive. Diagnosed from the scan_id=21
  per-recording data (no third rescan needed): when hf_ceiling_hz falls inside/near the
  sibilance band, the band + its flanks read noise floor asymmetrically, producing spurious
  deep-negative values for band-limited (low-rated) recordings — an hf_ceiling_hz artifact, not
  sibilance. Splitting by ceiling: <9000 Hz shows rho≈0 (pure floor noise); >=9000 Hz still shows
  rho=+0.34 (p=0.005, n=66) — weaker but not fully neutral. sibilance_crest has no such issue —
  validated cleanly in both scans (rho -0.34 to -0.65, correct sign). DECISION NOT YET MADE on
  whether to gate sibilance_ratio_db by hf_ceiling_hz, drop its defect framing (polarity=0,
  informational like air_ratio_db), or something else — see TODO-183 REMAINING for full writeup.
  sibilance_ratio_db/sibilance_crest remain un-fused (not in QUALITY_MODEL); no scoring behavior
  changed for any existing recording.

[2026-06-30] — fix(scraper): WTRF LB-tag disqualification missed unpadded/attachment-only tags (BUG-227)
Fixed: backend/wtrf_scraper.py: the BUG-225 Round 0 disqualification regex required 3-5 digits,
  missing legacy posts that write the tag unpadded (e.g. "LB-8"); widened to `lb-0*(\d{1,5})\b`.
  `_fetch_topic` now also collects attachment filename text (a sibling div the post body never
  included) into a new `attachment_text` field, concatenated into the scan text in
  `find_torrent_for_lb` — so a tag on either the body or an attachment name (e.g.
  "LB-00008.torrent") triggers disqualification. Confirmed against WTRF topic=54221.msg77946,
  previously a "low-confidence" candidate for both LB-16632 and LB-16633 despite plainly
  documenting LB-8 in both the post text and its attached torrent's filename.

[2026-06-30] — feat(scraper): qBittorrent paused-add option for WTRF batch fetches (TODO-193)
Added: backend/qbittorrent.py: `add_torrent_for_download()` gains a `paused` parameter that
  sends both `paused`/`stopped` form keys on `POST /api/v2/torrents/add` (the accepted key name
  changed across qBittorrent WebUI API versions, so both are sent for compatibility) — lets a
  torrent be queued without starting the download immediately.
Added: tools/wtrf_fetch_missing.py: `--paused` CLI flag, used with `--add-to-qbt`, threaded
  through `_qbt_add()` to the new qBittorrent parameter.
Changed: Ran a full batch against the 220 LB entries above LB-16000 missing from
  `my_collection` (public + not yet held). 113 matched confidently and were added to
  qBittorrent paused for manual review before downloading; 22 downloaded but weren't pushed to
  qBittorrent; 85 had no confident WTRF match (see wtrf_skipped_review.md for the link list).

[2026-06-30] — feat(concert-ranker): true 5-9 kHz sibilance detection from NativeProbe (TODO-183)
Added: concert_ranker/features.py: `_sibilance_native()` computes `sibilance_ratio_db` (native
  sibilance band vs the ref_mid anchor) and `sibilance_crest` (loudest-window vs median-window
  excess across NativeProbe.window_psds_db) — separates bursty essy S/T-consonant sibilance from
  steady HF brightness, which the bulk-rate single-Welch-PSD approximation couldn't distinguish.
  Wired into extract_hf_native(); 6 new tests in tests/test_concert_ranker.py.
Fixed: concert_ranker/test_pipeline.py: removed the `sibilance_ratio_db = harsh_ratio_db`
  stand-in, which was silently overwriting the now-real value from extract_hf_native().
Changed: concert_ranker/scoring.py: added a "sibilance" pretty-name for sibilance_ratio_db in
  verdict text (was falling back to the raw key name).

[2026-06-30] — fix(scraper): WTRF search delay raised to clear forum flood-control
Fixed: backend/wtrf_scraper.py: search_delay was computed as delay * 1.5 (3.0s at the CLI's
  default --delay 2.0), below the WTRF forum's ~5s search flood-control window. Raised
  _SEARCH_DELAY constant to 10.0 and changed find_torrent_for_lb() to
  max(delay * 1.5, _SEARCH_DELAY) so search2 queries never go below the floor. Likely
  explains some of the 'not_found' results in live batch testing — searches may have been
  silently throttled rather than genuinely returning zero candidates. See BUG-226.

[2026-06-30] — fix(scraper): WTRF candidate disqualified when post tagged for a different LB entry
Fixed: backend/wtrf_scraper.py: _score_candidate() now extracts "LB-NNNNN" tag(s) embedded
  in candidate post bodies (forum_poster.py's own posting convention) before scoring. A tag
  matching the target entry's own lb_number is now a strong positive signal (+200,
  classified 'high' in _classify_confidence). A tag for a DIFFERENT lb_number hard-disqualifies
  the candidate — find_torrent_for_lb() now skips it in the scoring loop instead of letting it
  tie/compete on the weak date-match + has_torrent floor (score=5). See BUG-225.

[2026-06-30] — feat(scraper): WTRF fetch CLI accepts LB lists/ranges + prints review URLs
Added: tools/wtrf_fetch_missing.py: --lbs flag (mutually exclusive with --lb) accepting
  comma/space-separated LB numbers and/or inclusive ranges, e.g. '16640-16650,16700'.
  New _parse_lb_spec() helper dedupes and preserves first-seen order; --limit still
  truncates the resulting queue.
Changed: tools/wtrf_fetch_missing.py: _print_row() now prints the matched topic_url
  for 'skipped' rows (needs_review/ambiguous/not_found) so the user can manually open
  and review the candidate post(s) directly from CLI output, without querying
  wtrf_downloads. Ties print both tied URLs.
Changed: backend/wtrf_scraper.py: find_torrent_for_lb() returns topic_url_2 (the
  runner-up topic) on confidence='ambiguous', for the CLI's tie display. Not persisted
  to wtrf_downloads — display-only.

[2026-06-29d] — feat(scraper): WTRF forum torrent fetcher for missing LB items
Added: backend/wtrf_scraper.py: search WTRF board by date variants, multi-round scoring (FFP hashes > filenames > equipment tokens > taper name), confidence classification, torrent download with per-request throttle
Added: backend/qbittorrent.py: add_torrent_for_download() — adds torrent for downloading (no source-folder assumption)
Added: backend/db.py: wtrf_downloads table + add/update/get/get_pending helpers
Added: backend/app.py: POST /api/wtrf/fetch_torrent, POST /api/wtrf/crawl_missing (SSE), GET /api/wtrf/downloads
Added: tools/wtrf_fetch_missing.py: headless CLI for batch missing-item crawl (--limit, --lb, --delay, --add-to-qbt, --dry-run)

[2026-06-29c] — feat(concert-ranker): hard hf_ceiling floors + 30-min duration gate
Changed: concert_ranker/quality_score.py: _HF_FLOOR_RULES constant + _apply_hard_floors() — caps predicted rank after model: hf_ceiling_hz < 4000 → D- ceiling (rank 2); hf_ceiling_hz < 6000 → D ceiling (rank 3). Applied inside grade() after predict_rank(). D- now produced (26 recordings); D increased 1→150. Pearson r 0.66→0.64 (boundary trade-off: some LB C- with restricted HF pushed to D).
Changed: concert_ranker/cli.py: _MIN_CONCERT_DURATION_SEC = 1800 s constant; _filter_short_recordings() removes recordings under 30 min from metrics in-place; called from _rerank alongside other filters. 162 sub-30-min recordings excluded from scan 18; final scored set: 13752 rows.

[2026-06-29b] — fix(concert-ranker): exclude private entries + reclassify xx-date as compilation
Changed: backend/db.py: classify_entry_categories + classify_one_entry: Tier 0 added — if 'xx' in date_str (multi-date, day/month unknown) → 'compilation' before any bobdylan_shows lookup. Reclassified 344 previously-unknown entries; 183 non-concert entries with xx-dates also moved from their old keyword category to compilation (all already excluded from ranker).
Changed: concert_ranker/cli.py: _collection_worklist now LEFT JOINs lb_master and filters lb_status='public', excluding private/missing/nonexistent entries from scan worklists. Added _filter_non_public() helper (mirrors _filter_non_concerts) called from _rerank for the stored-metrics path. Scan 18 reranked: 13914 rows (was 15630); 808 non-concert + 1377 non-public removed.

[2026-06-29] — fix(concert-ranker): skip non-concert recordings + restore hf_ceiling_hz
Changed: concert_ranker/cli.py: _NON_CONCERT_CATEGORIES constant (studio/interview/tv/compilation/rehearsal/radio/soundcheck); _collection_worklist filters these from the scan worklist; _filter_non_concerts() helper removes them from metrics at rerank time. 469 non-concert entries now excluded from scan 18 scores (15630 vs 16099 rows).
Changed: concert_ranker/config.py: QUALITY_MODEL refit with hf_ceiling_hz forced back as 10th predictor (w=+0.42, rho_uni=+0.341). CV impact neutral (Spearman 0.6573 / within-1 76.0%). Moves bandwidth-limited bad recordings down: LB-7351 (F, "very muffled", hf_ceil=3kHz) C-→D+. Reranked scan_id=18.
Changed: concert_ranker/config.py: QUALITY_MODEL refit with hf_ceiling_hz forced back as 10th predictor (w=+0.42, rho_uni=+0.341). Forward selection had dropped it as collinear but scan-18 audit showed D/D-/F recordings have 26–43% incidence of hf_ceiling < 5kHz vs 0.17% for A-tier. CV impact neutral (Spearman 0.6573 / within-1 76.0% vs 0.6588 / 75.8%). Correctly moves bandwidth-limited bad recordings down: LB-7351 ("very muffled", hf_ceil=3kHz, LB=F) C-→D+; LB-7845 (D-) C-→D+. Reranked scan_id=18 (16099 recordings).

[2026-06-27] — feat(db): known-taper curated list + taper_name normalisation (TODO-173)
Changed: backend/db.py: added _KNOWN_TAPER_ALIASES dict (~100+ confirmed taper handles/aliases, all lowercase canonicals); _NOT_TAPER suppression set (mic models, format labels, editorial notes); _LT_TAPER_RE pattern for legendary taper series (lta–ltz); NT series (nta–ntz) aliases; step-0 known-handle scan in extract_taper_and_source fires before all heuristics; prefix-match canonicalization trims equipment bleed-through (e.g. "net taper e schoeps…" → "net taper e"); BOOTLEG: entries now store taper_name='bootleg'; quote-stripping from parsed taper names; taper_name lowercased for case-agnostic storage; _normalise_taper resolves known aliases; _KNOWN_TAPER_KEYS_SORTED pre-computed for prefix lookup
Changed: TODO.md: TODO-173 known tapers list updated with full confirmed set

[2026-06-27] — feat(db): entry_lineage table + batch parser + lineage API (CC_LINEAGE_PARSE)
Added: backend/db.py: entry_lineage USER table schema; _SAME_RE/_DIFF_RE/_DERIVED_RE/_BETTER_RE lineage regexes; extract_lb_references(), _normalise_taper(), _compute_parse_confidence(), upsert_entry_lineage(), get_lineage() functions; "entry_lineage" added to USER_TABLES
Changed: tools/tapematch/tapematch_session.py: _SAME_RE/_DIFF_RE now imported from backend.db (canonical source)
Added: tools/parse_lineage.py: CLI batch script to populate entry_lineage from entries.description (--force/--lb/--limit/--dry-run)
Added: backend/app.py: GET /api/lineage/<lb> route returns entry_lineage row as JSON
Added: tests/test_lineage.py: 8 tests covering extract_lb_references, parse_confidence, taper_normalised, and idempotency

[2026-06-27] — docs(schema): improved contrast, zoom slider, collapse/expand all buttons
Changed: docs/schema.html: raised contrast on col-type/col-note/stat-label/group-count/group-desc/card-desc/legend text; added zoom slider (60–150%) to header; added Expand All / Collapse All buttons scoped to active DB tab

[2026-06-27] — docs(schema): interactive schema viewer with FK navigation, search, tooltips, collapsible groups
Changed: docs/schema.html: added table descriptions, FK jump chips, click-to-highlight FK relationships (gold=focused/blue=related/dimmed), table search/filter, collapsible groups, floating column tooltips; JS auto-assigns data-table from card-name; TABLE_INFO covers all 51 tables; FK_SUPPLEMENT adds 12 undocumented foreign key relationships

[2026-06-26] — fix(scraper): diacritic-dropped locations corrected for 45 LB entries across 9 cities (BUG-211)
Fixed: data/site/detail/LB-*.html (45 files): patched cached HTML so re-scraping from local
  cache preserves correct city names with diacritics
Fixed: data/losslessbob.db entries table: corrected location for 45 entries —
  Saarbrücken (5): LB12124/16153/16154/16155/16167
  Düsseldorf (14): LB10133/11108/11143/11256/11303/11365/11555/12178/12186/13307/15100/16115/16182/16183
  Nürnberg (4): LB13434/16145/16147/16170
  Tübingen (2): LB11985/12043
  Göteborg (3): LB11521/12566/13053
  Malmö (8): LB04999/05212/07579/07751/09510/09715/12930/13273
  Montréal (2): LB14964/15249
  Zürich (6): LB09198/10088/14046/14047/14452/14453
  Jönköping (1): LB10977
  Venue corrections: LB04999 "Slottsmöllan", LB07579 "Malmö Arena", LB12930 "Mölleplatsen, Malmö"

[2026-06-26] — fix(gui): remove unimplemented ⌘K shortcut hints (BUG-222)
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: removed kbd-pill ⌘K span from search button
Fixed: gui_next/src/renderer/src/screens/ScreenHome.tsx: dropped cmd/⌘K tip from TIPS array (3→2 tips); updated render index logic
Fixed: gui_next/src/renderer/src/App.tsx: removed Kbd demo + "Global search" label from dev card; dropped unused Kbd import
Fixed: gui_next/src/renderer/src/locales/{en,fr,es,de,nl,it}.json: deleted tip1 (⌘K), promoted tip2→tip1, tip3→tip2

[2026-06-26] — fix(backend): incremental site crawler misses newly posted LB pages (BUG-217)
Fixed: backend/site_crawler.py: SEED_URLS and start_url are now always removed from
  `visited` before queuing, so index pages are re-fetched on every incremental run;
  their stored Last-Modified is loaded into lm_map so If-Modified-Since is used (304 =
  cheap no-op; 200 = index changed, new links extracted and queued)
Added: backend/site_crawler.py: flat-file download page added to SEED_URLS
  (checksum_lookup/checksum_lookup_lb_zip_download.htm)
Added: backend/db.py: get_inventory_last_modified() — targeted last_modified lookup for
  a list of URLs from site_inventory

[2026-06-26] — fix(gui+backend): spectrograms blank screen + no output (BUG-216)
Fixed: gui_next/src/renderer/src/lib/spectrogramStore.ts: dynRange default '-120' → '120'
Fixed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: dyn_range sent negative to
  SoX -z (requires positive int); now Math.abs(); label corrected to "dB range"
Fixed: backend/app.py: _spectro_state["errors"] was a list of dicts; TypeScript typed it as
  number; React crashed rendering objects in JSX → blank screen. Changed to int count; error
  details now logged via _log.error()

[2026-06-26] — chore(concert_ranker): validate new metrics on scan 17 — none enter QUALITY_MODEL (TODO-191)
Changed: tools/fit_aud_quality_model.py: added brickwall_score + single_ch_transient_count to
  candidate pool; updated speech_band_snr_db comment (rescan no longer pending).
  Findings: speech_band_snr_db (rho=0.409, Δ/σ=0.75) subsumed by existing predictors;
  brickwall_score (rho=-0.179, no signal); single_ch_transient_count BACKWARDS vs commentary.
  QUALITY_MODEL unchanged — scan 8 (2798-sample) fit retained; all three metrics stay in
  POLARITY for family scoring only.

[2026-06-25] — feat(concert_ranker): text features (TODO-188), brickwall/mic-hit waveform detectors (TODO-191), HF source discrimination (TODO-189), TV band detection (TODO-190)
Added: concert_ranker/text_features.py — new module: extract_text_features() parses 18 flaw/artifact
  vocabulary keys from entries.description (txt_clipping, txt_brickwall, txt_digipop, txt_dropout,
  txt_gap, txt_mic_hit, txt_hf_streak, txt_compression, txt_minidisc, txt_floating_parapet, txt_32k_dat,
  txt_talking, txt_singing, txt_limiting, txt_remaster, txt_tv_band, txt_cassette, txt_eac_match).
  Regex patterns cover LB site controlled vocabulary; all keys always present (0.0/1.0 binary).
Added: concert_ranker/features.py — extract_text() wrapper; _brickwall_score() (normalized slope
  variance in mid-amp vs loud frames, captures smooth between-peak ramps); _single_channel_transient_count()
  (L/R ≥2:1 asymmetric impulse events = mic hits, stereo only); _minidisc_parapet_score(), _32k_dat_flag(),
  _cassette_rolloff_flag() (HF ceiling shape discrimination from averaged NativeProbe PSD); _tv_band_flag()
  (narrow elevated band at 14.5-16.5 kHz with per-window pulsing variance check). All added to
  extract_distortion() and extract_hf_native() return dicts.
Changed: concert_ranker/audio/cache.py — NativeProbe gains window_psds_db field (n_windows × n_freqs,
  None by default); build_native_probe() populates it so TV band variance can be measured without a second
  full-file decode.
Changed: concert_ranker/calibration.py — description field threaded through stratified_sample() and
  decade_stratified_sample() into build_samples(); text features injected into calibration metrics dict
  (no rescan needed — DB-side extraction).
Changed: concert_ranker/cli.py — _inject_text() augments metrics dicts at rerank time (mirrors _inject_dff()
  pattern); called in _rerank().
Changed: concert_ranker/config.py — POLARITY entries added for all new features: speech_band_snr_db +1,
  brickwall_score/single_ch_transient_count/minidisc_score/dat32k_flag/cassette_flag -1, tv_band_flag 0,
  all 18 txt_* features (mostly -1, tv_band/cassette_flag 0 for informational ones).
Changed: tests/test_concert_ranker.py — 20 new tests: text feature extraction, brickwall score synthetic
  validation, single-channel transient detection, 32k DAT flag, cassette rolloff, TV band pulsing. 44 pass.

[2026-06-25] — fix(concert_ranker): remove backwards/noise metrics from family scoring and labeling
Changed: concert_ranker/config.py — directness polarity set to 0 (excluded from family comparison):
  scan-8 validation (n=2798 AUD) shows bad recordings score higher (rho=-0.272, commentary Δ/σ=-0.82)
  — the metric measures spectral imbalance, not recording proximity. Labels ("close/direct" /
  "distant/roomy") were inverted relative to actual quality. Removed from QUALITY_BANDS and all
  per-decade QUALITY band dicts. onset_clarity polarity set to 0 (rho=-0.131, commentary Δ/σ=+0.04
  — crowd noise inflates onset_env; no real clarity signal). Both metrics retained in QUALITY_MODEL
  where they contribute CV Spearman with correct negative weights.
Changed: concert_ranker/scoring.py — removed directness and onset_clarity from FAMILY_METRICS
  "clarity" family and from the _PRETTY verdict label map.
Added: concert_ranker/features.py — speech_band_snr_db metric in extract_clarity: 1-4 kHz SNR
  during loud vs quiet frames (same approach as crowd_snr_db but restricted to the vocal
  intelligibility band). Not yet in QUALITY_MODEL — needs rescan to validate against commentary.
Changed: tools/fit_aud_quality_model.py — added commentary audit section (Δ/σ per metric vs
  muffled/distant/upfront labels, with rho column and BACKWARDS detection); added speech_band_snr_db
  to candidate pool; skips candidates with no scan data.

[2026-06-25] — feat(concert_ranker): refit QUALITY_MODEL_SBD on full scan 9 corpus (TODO-183)
Changed: concert_ranker/config.py QUALITY_MODEL_SBD — refit on scan_id=9: 506 SBD+FM recordings
  (479 SBD + 27 FM) all scanned with the current dropout detector. dropout_count tested (rho=-0.077,
  p=0.082, weight ~0) — not predictive with consistent detector values; old rho=0.375 was a
  scan-version artifact from mixing old/new detector outputs across scans 3-7. Same 6 predictors
  as v1 (hiss_floor_db, hf_ceiling_hz, crest_factor_db, air_ratio_db, harsh_ratio_db, directness).
  Validation: AUD model on this set = Spearman 0.429 / 73.5% within one tier; new fit =
  Spearman 0.562 / 80.2% within one tier (5-fold CV, alpha=0.5). 24 tests pass.

[2026-06-25] — concert_ranker: hum_excess_db frequency-resolution fix (Δf 5.4 Hz → 0.5 Hz)
Changed: concert_ranker/features.py: _hum_excess_db now computes a dedicated high-res Welch
  PSD (nperseg=sr×2, Δf=0.5 Hz) instead of reusing the shared cache PSD (nperseg=4096,
  Δf≈5.4 Hz). Root cause of +0.117 rho confound: at 5.4 Hz resolution, G1 bass (49 Hz) and
  50 Hz mains shared the same bin; the 100 Hz and 250 Hz harmonic windows were empty (no bin
  within ±2 Hz). Peak window tightened from ±2 Hz to ±0.5 Hz; harmonics extended from 5 to 7.
  Synthetic validation: 49 Hz bass → 0.00, 58 Hz (A#1) → 0.00, genuine 50/60 Hz comb → fires.
  Needs re-scan to confirm rho improvement (scan_id=8 values computed with broken detector).

[2026-06-25] — concert_ranker: dff_vert_occ added to QUALITY_MODEL; AUD CV Spearman 0.659→0.664
Changed: concert_ranker/config.py: QUALITY_MODEL refit to include dff_vert_occ = log1p(vert_occ)
  from dff_reports; forward selection added it as 7th predictor (CV rho +0.006), weight -0.1274
  (higher vert count → lower rank); 9 total predictors. 5-fold CV Spearman 0.664 / 75.9% within 1 tier.
Changed: concert_ranker/cli.py: _inject_dff() helper — augments metrics dict at rerank time from
  dff_reports table (log1p transform); falls back to model median for LBs without DFF data.
Changed: concert_ranker/calibration.py: build_samples() now injects dff_vert_occ from dff_reports
  so future calibration runs include it automatically.
Added: tools/fit_aud_quality_model.py: fitting script for the AUD ridge model; forward selection over
  14-candidate pool, outputs QUALITY_MODEL dict; accepts --scan-id --alpha --no-forward-select.

[2026-06-25] — tools/parse_dff_reports.py: DFF HTML parser — 12,523 LBs written to dff_reports table
Added: tools/parse_dff_reports.py: parses all DigiFlawFinder HTML reports in data/site/files/,
  extracts drop/clip/horz/vert total occurrence counts (handles both the older Totals-section format
  and the newer "No Flaws Found" format), sums multi-disc primary files per LB, uses xref files only
  for LBs with no primary file, writes to dff_reports table (lb_number PK). 12,523 LBs written,
  67 unresolvable errors (~0.5%), 99.5% parse rate. --summary flag prints vert_occ vs rating table.
Finding: vert_occ gradient confirmed in full corpus: median 1 at A/A- tiers rising to 8 at F.

[2026-06-25] — concert_ranker: dropout_count rework — 3-mode defect detector + DFF vert finding
Changed: concert_ranker/features.py: replaced locally-normalized roughness (rho=+0.417, measuring
  musical transient density) with three DigiFlawFinder-modelled detectors: silence gap (DFF Drops),
  stuck sample (DFF Horizontals), and digipop/vertical (DFF Verticals — exactly-2-wide symmetric
  first-diff spike; min/max ratio >0.5 rejects asymmetric musical attacks). 8 tests, all pass.
Added: tests/test_concert_ranker.py: 8 dropout unit tests including digipop detection.
Finding: DFF vert_occ (from 14,090 downloaded DigiFlawFinder reports) correlates rho=-0.157
  (p=1.5e-14) with AUD rating on scan_id 8 corpus — monotonic A→F (median 1→8). Drop/clip/horz
  near zero. DFF parser to extract per-LB vert counts is the next recommended step.

[2026-06-25] — tapematch: FINDINGS.md — synthesized performance report and architecture limits
Added: tools/tapematch/FINDINGS.md: full findings report — accuracy metrics, all 7 approaches
  tried with outcomes, root-cause analysis, what works, future angles, and recommendation

[2026-06-25] — tapematch: cancel TODO-185/144/140 (all falsified); start TODO-184 polarity batch
Changed: tools/tapematch/tapematch/match.py: added lowband_envelope_corr() (250-2000 Hz zero-phase
  bandpass + log-RMS envelope cross-correlation with lag search; unit tests in
  tests/test_lowband_corr.py, 4 passing). Added windowed_fingerprints() / best_window_fingerprint_match()
  / _fingerprint_hashes() for TODO-185 windowed-overlap investigation (retained, not wired into cli.py).
Changed: tools/tapematch/tapematch/align.py: added locate_splice_points() (extracts step indices from
  lag curve, unit tests in tests/test_splice_points.py, 5 passing; retained, not wired into cli.py).
Added: tools/tapematch/tests/test_fingerprint_windows.py (4 passing), test_splice_points.py (5 passing),
  test_lowband_corr.py (4 passing).
Added: tools/tapematch/calibrate_fingerprint_localize.py, calibrate_fingerprint_baseline.py,
  calibrate_piecewise.py, calibrate_lowband.py — falsify-first pilot scripts (read-only, no cli.py wire).
Changed: tools/tapematch/BASELINE.md: Task 8 (TODO-185 — 3 approaches: contig-run audit, HF-band
  fingerprint, 200-4kHz fingerprint; all falsified); Task 9 (TODO-144 — piecewise pilot, per-seg p50
  same-source 0.004 < different-source 0.005); Task 10 (TODO-140 — 250-2000 Hz envelope pilot,
  confirmed-distinct LB-02470/LB-02478 +0.357 > all missed-pairs max +0.201).
Added: tools/tapematch/validate_polarity.py — batch polarity-rescue dry run across ~474 contradicted-claim
  dates; JSONL checkpoint output; batch in progress (TODO-184 Checkpoint 1 pending).

[2026-06-25] — fix(scheduler): tapematch tmp-dir cleanup race deletes concurrent run's files (BUG-224)
Fixed: tools/tapematch/tapematch_session.py: _clean_stale_tmp_dirs() rmtree'd every
  tapematch_* dir under /mnt/DATA0/tmp unconditionally before each subprocess launch, with no
  liveness check -- two concurrent tapematch_session.py sessions (1989-06-04, 1990-01-12)
  deleted the in-flight memmaps of a separate validate_polarity.py batch run, causing
  cascading FileNotFoundError crashes on 5 dates. Added _tmp_dir_in_use() (open-fd scan via
  /proc + recent-mtime check); cleanup now skips any dir that's still actively written to or
  held open by a running process, regardless of which script or session owns it. New tests:
  tools/tapematch/tests/test_clean_stale_tmp_dirs.py (4 passing).
Added: tools/tapematch/tapematch/match.py: windowed_fingerprints()/best_window_fingerprint_match()
  (TODO-185, revised approach) -- landmark-hash-based localized-overlap evidence to replace the
  falsified "best contiguous run on 60s residual_corr windows" premise (audit on 1991-11-05
  found zero signal differentiation between 5 curator-claimed same-source pairs and a known-
  distinct negative control at both +-10s and +-120s lag search). _fingerprint_hashes() extracted
  from fingerprint_window() as a shared helper. Existing test suite verified unaffected (45
  passed; the only 4 failures are pre-existing and unrelated, in test_batch_queue.py /
  test_find_lb_folders_no_audio.py).

[2026-06-25] — feat(concert_ranker): refit AUD QUALITY_MODEL on scan_id 8 (2798 AUD) (TODO-183)
Changed: concert_ranker/config.py QUALITY_MODEL — refit the absolute-score ridge on the full
  overnight by-decade scan (scan_id 8, 2798 rated AUD, 6x the prior 466-recording basis). New
  predictors chosen by forward selection over a 17-metric pool (alpha=0.3): hiss_floor_db,
  bass_ratio_db, mud_ratio_db, onset_clarity, directness, crowd_snr_db, harsh_ratio_db,
  presence_ratio_db (dropped the collinear HF set hf_ceiling/centroid/air/crest). Every weight's
  sign matches its univariate direction — no confound. 5-fold CV (3 seeds) to LB rating: Spearman
  0.659, 75.6% within one letter tier; verified via the live predict_rank path at 0.661 / 75.9%.
  The previous 466-fit model scored only 0.561 / 46%-within-1 on this full set (mis-centered
  intercept fit on a middle-focused sample); the refit re-centers to the collection's true mean
  rank (~9.8). SBD model (QUALITY_MODEL_SBD) untouched. 16 concert_ranker tests pass.

[2026-06-25] — fix(concert_ranker): disable confounded dropout_count disqualifier (TODO-183)
Changed: concert_ranker/config.py DISQUALIFIERS — removed the dropout_count>150 "has dropouts/
  glitches" entry. The overnight calibration scan (scan_id 8, 2798 AUD, by-decade, all ratings —
  the fresh full scan meant to validate the 06-24 locally-normalized-roughness rework) shows the
  de-confounding did NOT hold at scale: rho vs rating = +0.417 (p=3e-118), median dropout by tier
  A:118 A-:55 B:27 B-:12 ... C/D ~6-17, i.e. the best recordings score highest. The detector still
  tracks transient/HF density, not defects, so the 150 threshold was mislabeling many A-tier
  recordings. Disabled (commented out) until the detector is reworked; comment block corrected
  (previously claimed "the confound is GONE"). dropout_count is not a QUALITY_MODEL predictor, so
  absolute scores/grades are unaffected. 16 concert_ranker tests pass.
Verified: scan_id 8 finished cleanly overnight (2798/2799 scanned; 1 fail = LB1489 empty folder).
  Calibration is report-only; band-cutoff refits from scan_id 8 not yet applied (current basis
  remains scan_id 6).

[2026-06-24] — feat(concert_ranker): dedicated SBD/FM absolute quality model (TODO-183)
Added: concert_ranker/config.py QUALITY_MODEL_SBD — separate ridge model (predictors hiss_floor_db,
  hf_ceiling_hz, crest_factor_db, air_ratio_db, harsh_ratio_db, directness) fit on the 223
  SBD+FM recordings with metrics+rating across scans 3-7 (latest scan per LB). AUD's predictors
  (mud_ratio_db, presence_ratio_db, spectral_centroid_hz, crowd_snr_db) don't separate SBD tiers
  (|rho| < 0.25); harsh_ratio_db/directness do and aren't in the AUD set. dropout_count (rho 0.375)
  deliberately excluded — most of the sample predates the dropout-detector rework, so its values
  aren't comparable to current scans; revisit once SBD is re-scanned with the current detector.
  Validation: applying the AUD model to this SBD+FM set gets a comparable rank correlation
  (Spearman 0.511) but only 48% within-one-letter-tier (wrong absolute level); the dedicated fit
  gets Spearman 0.53 and 69% within one tier (5-fold CV).
Changed: concert_ranker/quality_score.py predict_rank()/grade() take an optional source_class arg
  and route SBD/FM to QUALITY_MODEL_SBD, everything else (incl. unknown/None) to QUALITY_MODEL — same
  pattern as config.resolve_band_set()'s class resolution.
Changed: concert_ranker/families.py rank_group() passes group[lb]["source_class"] into
  quality_score.grade() so each recording's verdict grade uses the right model.
Added: tests/test_concert_ranker.py test_absolute_quality_grade_sbd_model — SBD/FM route to
  QUALITY_MODEL_SBD (not the AUD model) and still discriminate good/bad metrics; 16 tests pass.
Verified: `concert_ranker rerank --scan-id 6` end-to-end against the real DB — SBD/FM grades now
  cluster B-/A (matching the actual top-heavy SBD rating distribution) instead of the AUD curve.

[2026-06-24] — feat(db): curated_lists / curated_list_entries — carbonbit + 10haaf picks (TODO-181)
Added: backend/db.py — curated_lists + curated_list_entries tables (MASTER_TABLES, schema v10);
  CRUD: get_or_create_curated_list, get_curated_lists, add_curated_list_entries,
  get_curated_list_entries.
Added: tools/import_curated_lists.py — stdlib-only (zipfile + ElementTree) importer. Parses
  data/lists/FLglist.xlsx ("front line G list" sheet: one row per date, column C is carbonbit's
  pick(s) — multiple LB numbers per date allowed) and data/lists/dylan_boots.zip +
  data/lists/years.zip (10haaf's per-year HTML bootleg catalogs; every LB-XXXXX found across both
  archives is unioned, since the older per-year pages and the newer allboots.html disagree on
  ~1,100 entries and neither is a clean superset). Idempotent via the entries table's
  UNIQUE(list_id, lb_number) constraint. Ran once against the live DB: carbonbit 4503 entries,
  10haaf 7572 entries.
Note: GUI/filter surfacing on the Library screen (the rest of TODO-181) is intentionally not done
  yet — this pass is DB + import only, per explicit scope decision.

[2026-06-24] — feat(tapematch): polarity-inversion rescue — step 2, wired into the matcher (TODO-184)
Added: tools/tapematch/tapematch/match.py polarity_rescue(): per-anchor driver that re-scores a
  near-zero pair across the L-R cross terms (mid-side / side-mid), each doing its OWN lag search
  (mid-vs-mid can't lock when one channel is inverted), and returns the best median + pairing.
Changed: tools/tapematch/tapematch/cli.py Pass 1 — when polarity.enabled, decode stereo and persist
  an L-R "side" memmap per stereo source (identical trim bounds to the mid memmap; mono sources get
  none); added side_paths dict + _mmap_side() helper. Default OFF, so the mono fast-path is unchanged.
Changed: tools/tapematch/tapematch/cli.py residual matrix loop — after speed refine, a pair whose
  median corr is below polarity.rescue_corr_ceiling is re-scored via match.polarity_rescue (speed-
  correcting both the other source's mid and side by the pair ratio), kept only if it improves, and
  logged as POLARITY_RESCUE. Keep-if-improves means it can rescue a true inverted-channel pair but
  cannot manufacture a false merge.
Added: tools/tapematch/tests/test_polarity_corr.py — 2 driver tests (own-lag recovery of an inverted
  pair; independent sources stay below threshold). 6 polarity tests + 22-test matcher subset pass.
Note: step 3 (enable on the ~37 contradicted-claim dates + validate the stereo Pass-1 memory profile
  on real data, then consider default-on) remains open under TODO-184.

[2026-06-24] — feat(tapematch): polarity-inversion rescue — step 1, config-gated core (TODO-184)
Added: tools/tapematch/tapematch/match.py polarity_aware_corr(): scores an aligned pair across
  mid-mid / mid-side / side-mid channel-polarity variants and keeps the strongest, so a genuine
  same-source copy with one channel polarity-inverted ("right channel inverted") — which collapses
  the L+R mid-vs-mid correlation that Pass 1 ingests — is recovered via the L-R cross term.
Added: tools/tapematch/config.yaml polarity block (enabled: false, rescue_corr_ceiling: 0.60),
  DEFAULT OFF; documents that enabling will require stereo ingest in Pass 1 (raises peak RAM) and
  validation before turning on.
Added: tools/tapematch/tests/test_polarity_corr.py: 4 tests — right/left inverted-channel copies
  rescued ~1.0, independent sources not merged, clean copy still scores on mid-mid.
Note: this is step 1 (testable core). Step 2 (Pass-1 stereo/side-memmap wiring + matrix-loop rescue
  branch) and step 3 (re-run the contradicted-claim dates) remain open under TODO-184. Speed-offset
  false-negatives were found to be ALREADY handled (±30000 ppm + lag-slope refine, committed 06-21).

[2026-06-24] — feat(concert_ranker): absolute quality score — 0-100 + A+..F grade per recording (TODO-183)
Added: concert_ranker/quality_score.py + config.QUALITY_MODEL — a ridge regression predicting the LB
  rating rank (1=F..13=A+) from 8 validated metrics (hiss/hf_ceiling/centroid/crest/crowd_snr/air/mud/
  presence), giving every recording a standalone 0-100 score + +/- letter grade, independent of the
  within-family ranking. Fitted on 466 AUD (scans 6+7). HELD-OUT (5-fold CV) correlation to the real
  LB rating: Spearman 0.65, 93% within one letter tier. Stored-grade check across 873 recordings (incl.
  the C-rich middle): rho 0.67, 94% within one letter; median score per tier A 72 / B 60 / C 46 / D 38.
Changed: families.rank_group now computes the grade per recording and prepends "Grade X (N/100)." to the
  verdict; lb/repo.py quality_recording_scores gained abs_score / abs_grade columns (ensure_schema ALTER
  migration; write_scores/load_scores updated); cli report CSV includes them. Added a unit test (15 total).
  AUD-fit model applied to all classes — SBD/FM grades are approximate (TODO-183).

[2026-06-24] — fix(tapematch): record real model in analysis attribution (BUG-223)
Fixed: .claude/commands/tapematch-batch.md: step 4 hardcoded `*Claude claude-sonnet-4-6 — …*` for
  every session regardless of the running model; now requires the actual session model id. Made all
  per-model quality audits of the analysis corpus impossible.
Fixed: data/tapematch/runs/*/analysis.md (x10): corrected attribution to `claude-haiku-4-5` on the
  analyses proven (via session transcripts) to have been written by haiku, not sonnet — 1989-08-29,
  1989-08-31, 1989-11-02, 1990-06-29, 1990-06-30, 1990-07-07, 1990-07-08, 1990-08-12, 1990-08-20,
  1990-09-05. Opus-stamped files left as-is (correctly self-attributed).

[2026-06-24] — fix(concert_ranker): rework dropout click detector — de-confound from dynamics (TODO-183)
Changed: concert_ranker/features.py _dropout_count(): replaced isolated-2nd-difference detection with
  LOCALLY-NORMALIZED roughness. A click is flagged where |2nd difference| exceeds the LOCAL roughness
  level (a ~12 ms rolling mean via scipy.ndimage.uniform_filter1d), so loud/dynamic passages no longer
  trip it — only narrow (<=3-sample) events count. Validated on a stratified AUD subset: rho vs rating
  +0.43 -> -0.04 (confound eliminated; it's now a neutral defect flag, not a fidelity proxy), counts
  sane (clean ~4-10, glitchy tail ~80-280) vs the old thousands. Much faster too (uniform_filter1d, not
  per-sample median). (A first attempt using a median-filter residual was discarded — it fires on all
  oscillating audio.)
Changed: concert_ranker/config.py DISQUALIFIERS: dropout_count 6900 -> 150 (provisional for the new
  scale). NOTE: scan_id 6's stored dropout values are from the OLD detector — a fresh scan repopulates
  them and the threshold should be refit then.

[2026-06-24] — feat(concert_ranker): per-class bands (hybrid — crowd held absolute) (TODO-183)
Added: concert_ranker/config.py: CLASS_BANDS {"SBD": ...} (fit from 165 SBD in scan_id 6) + resolve_band_set(
  decade, source_class). SBD/FM band hiss + tonal against soundboard norms (SBD hiss floor is much lower,
  median -9.2 vs AUD -5.2, so a soundboard that's hissy FOR a soundboard now flags); FM (n=27) reuses SBD.
Changed: scoring.all_bands / explain_recording + families.rank_group/rank_scan take source_class
  (already present in the loaded metrics) and resolve class+era bands.
Decision: crowd_snr_db is held on the GLOBAL (absolute) band for every class/era inside _build_decade_bands.
  Full per-class relativization made ~60% of soundboards read "some crowd"/"crowd-heavy" (an 8.5-dB SBD
  has far less crowd than any AUD — it should read "clean"); crowd level is meaningful absolutely, and
  within-class fairness is already handled by MAD-z ranking over same-show siblings. Effect: 0 crowd-label
  changes on SBD (the A-rated soundboards that wrongly read "crowd-heavy" now read absolute "some crowd").
  Added tests/test_concert_ranker.py::test_hybrid_crowd_global_hiss_per_class (14 tests pass).

[2026-06-24] — feat(concert_ranker): per-decade bands — era-relative quality labels (TODO-183)
Added: concert_ranker/config.py: _DECADE_CUTS (AUD percentiles per decade from scan_id 6) +
  _build_decade_bands() + DECADE_BANDS {1960..2010: {SIGNED/SEVERITY/QUALITY}} + decade_of(). Recording
  tech shifts the raw scales a lot by era (AUD hiss_floor_db "hissy" cut runs +0.6 in the 1960s tape era
  to -1.4 in the 2000s digital era), so a single global band over-flagged vintage shows as hissy and
  NEVER flagged modern ones. Per-decade bands judge each recording against its own era.
Changed: concert_ranker/scoring.py: band_metric() takes optional per-set band dicts; all_bands(raw,
  decade) + explain_recording(..., decade) select DECADE_BANDS[decade] (global fallback when the decade
  is unknown/unrepresented).
Changed: concert_ranker/families.py: load_decade_map() ({lb: decade} from entries.date_str);
  rank_group/rank_scan thread decades through. cli._rerank passes the decade map so scan/rerank/report
  all band per-era. sibilance/dynamic_range + disqualifiers stay global.
  Effect on scan_id 6 AUD 'hissy': normalized to ~10%/decade (was 1960s-90s over-flagged, 2000s/2010s
  never flagged). Added tests/test_concert_ranker.py::test_decade_bands_are_era_relative (13 tests pass).

[2026-06-24] — feat(concert_ranker): refit all bands from the 697-show decade scan (TODO-183)
Fixed: concert_ranker/calibrate.py score_separation(): forced float dtype so stored None metric values
  (NaN coerced on persist) no longer crash np.isnan — the larger 697-set exposed this (mono spatial /
  empty HF probe produce None). The scan persisted 696/697 fine; only the post-scan report had crashed.
Changed: concert_ranker/config.py: SIGNED/SEVERITY/QUALITY band cutoffs + dropout disqualifier refit
  from scan_id 6 (697 decade-stratified shows, ~320 AUD percentiles — supersedes the scan_id 3 fit).
  At scale the de-confounding held/strengthened: AUD hiss_floor_db -0.64 (now the single strongest
  quality predictor), harsh_ratio_db -0.03 (neutral). crowd_snr tiers widened (p10/p30/p60) to restore
  "crowd-heavy" recall. dropout disqualifier 1000 -> 6900 (worst-track p95) — kept HIGH because the
  metric still correlates +0.43 with rating (isolated-spike test partly catches sharp musical transients
  in dynamic well-rated shows), so a low cutoff would wrongly demote good recordings. Net over 696 shows:
  label-fires 1117 -> 930; verdicts validated against LB comments (A=clean/very-quiet, F=hissy/muddy/buried).
Noted: AUD hiss_floor_db median swings by era (-2.0 1960s tape -> -8.1 2000s digital) — strong candidate
  for per-decade band sets (recorded in config + TODO-183); global bands applied for now.

[2026-06-24] — fix(concert_ranker): rework hum + dropout metrics, worst-track aggregation, decade sampler (TODO-183)
Changed: concert_ranker/features.py:
  - _dropout_count(): replaced the "2nd-difference z>12" test (counted every musical transient —
    medians in the thousands, useless) with ISOLATED-discontinuity detection (z>30 AND both neighbours
    z<8). Clean shows now read 0; LB1233 (comment: "small pop t11 0:15, 1:42…") reads 108 on that track.
  - _hum_excess_db(): now requires a 50/60 Hz harmonic COMB (>=3 harmonics of one mains family above
    the local floor), not the worst single peak — a lone bass bin no longer trips it. Round-3 rho
    +0.45 -> n/a (fires on 0/117, no longer confounded with bass; inert but safe).
Changed: concert_ranker/scan.py aggregate_tracks(): defect metrics (dropout_count, clip_fraction,
  hum_excess_db) now aggregate by WORST track (max) instead of median — median hid one-bad-track
  glitches (e.g. LB2100 had a 1146-glitch track but aggregated to 0). _WORST_TRACK_METRICS set added.
Changed: concert_ranker/config.py DISQUALIFIERS: dropout_count 25000 -> 1000 (provisional from scan_id 5
  worst-track distribution), hum_excess_db 15 -> 10. crowd_snr/bands unchanged.
Added: concert_ranker/calibration.py decade_stratified_sample() + _entry_year() (parses M/D/YY dates);
  `calibrate --by-decade` CLI flag — large decade × rating-tier × source_class sample (every decade
  represented, ALL bad-tier included, good/mid capped at --per-cell). Launched an overnight scan_id 6
  of 697 recordings (all 6 decades, AUD 320/SBD 165/UNKNOWN 184/FM 28) for further iteration.

[2026-06-23] — fix(concert_ranker): de-confound harsh + hiss metrics, calibration round 2 (TODO-183)
Changed: concert_ranker/features.py: two extractors made level-independent after round-1 calibration
  found them confounded with overall HF brightness (both rose WITH the rating):
  - harsh_ratio_db: was harsh(2-5k) - ref_mid; now harsh - 0.5*(ref_mid + sibilance), i.e. a LOCAL
    2-5 kHz prominence above its flanks. Spearman vs rating +0.44 -> +0.06 (no longer fakes harshness
    from brightness).
  - hiss_floor_db: was the absolute native 8-14 kHz level (included musical HF); now computed at bulk
    rate as 8-11 kHz persistence in quiet vs loud frames (new _hiss_floor_db helper) — real hiss is
    constant when music drops, musical HF collapses. Spearman +0.31 -> -0.52 (now correctly predicts
    WORSE ratings, a strong signal). Moved hiss_floor_db out of extract_hf_native into extract_distortion.
Changed: concert_ranker/config.py: harsh_ratio_db + hiss_floor_db SEVERITY bands refit from scan_id 4.
  "hissy"/"harsh" now fire only on B-/C/D shows — zero A-tier false positives (round 1 wrongly tagged
  A-rated LB1419/LB1233 as hissy; both now read "very quiet"). All other metrics/bands unchanged.
Changed: concert_ranker/calibrate.py: (round-1 fix) score_separation `useful` cast to python bool.
  scan_id 4 recorded as the CURRENT calibration basis (supersedes scan 3).

[2026-06-23] — feat(concert_ranker): calibrate bands against real audio + staging support (TODO-183)
Changed: concert_ranker/lb/source_type.py: derive_source_class() now trusts the curator
  entries.source_type column first (Audience→AUD / Soundboard→SBD / FM/Pre-FM→FM / Mixed,ALD,Master→
  UNKNOWN), falling back to free-text mining only when NULL. Real collection split is now
  AUD 11,731 / SBD 480 / FM 28 / UNKNOWN 357 (was ~60% UNKNOWN). classify_entries + calibration +
  cli worklist updated to pass the column.
Added: concert_ranker/runner.py group_by_device(); --staging-dir on `scan` and `calibrate`
  (run_calibration gained classes= + staging_dir=). Staging copies each folder to fast scratch
  (one producer per physical drive via st_dev) before decoding — used /mnt/DATA2 for the cal run.
Fixed: concert_ranker/calibrate.py score_separation(): `useful` was a numpy bool (serialized as the
  string "False"); cast to python bool.
Changed: concert_ranker/config.py: SIGNED/SEVERITY/QUALITY band cutoffs + the crowd_snr "buried"
  disqualifier REPLACED with values fitted from scan_id 3 (117-show sample: 73 AUD + 44 SBD, staged).
  The first-principles guesses fired muddy/dull/boomy on ~95% of real recordings (measured AUD scales
  were far off — mud_ratio_db 18-34 dB, air_ratio_db -44..-24); calibrated cutoffs cut label-fires
  476→171 on the sample and made harsh/hissy/thin/bright labels functional. dropout_count/hum_excess
  parked at "rarely fires" (dropout counts normal transients; hum confounded with level) pending
  metric rework. Calibration findings (Spearman per class, fitted thresholds, label precision/recall)
  in concert_ranker/BUILD_REPORT-style notes; scan_id 3 retained as the fit basis.

[2026-06-23] — feat(backend): Concert Ranker v1 — audio quality scoring + ranking (TODO-183)
Added: concert_ranker/ — new repo-root package. Unzipped the v1 "scoring brain" (config/scoring/
  features/calibrate/audio.cache, pre-built + tested on synthetic audio) and wired it to the real
  machine per instructions/CC_CONCERT_RANKER.md:
  - lb/repo.py: USER-tier persistence (standalone WAL connections, one-transaction-per-recording,
    scan create, raw-metric + score upsert, restart skip, rerank reads). _jsonable() coerces numpy
    float32 / NaN to JSON-safe values.
  - lb/source_type.py: SBD/AUD/FM/UNKNOWN derivation reusing backend.db.classify_source_type
    (Matrix/ALD → UNKNOWN so they never contaminate a pure source-class curve).
  - lb/commentary.py: keyword-mines entries.description into calibrate.LABEL_KEYWORDS (the
    validation oracle), word-boundary matched.
  - audio/io.py: ffmpeg decode (one bulk decode at 22.05 kHz → build_track_cache; 8×20 s windows at
    44.1 kHz → build_native_probe), mirroring tools/tapematch/tapematch/audio.py.
  - scan.py / runner.py: per-folder decode→extract→aggregate(median)→one transaction; direct
    process-pool driver + producer/consumer staging loop (crash=scrap, skip done LBs on restart).
  - families.py: rank within recording_families (MAD-z normalize → fuse → rank_in_family), standalone
    fallback (absolute bands only); sibling-relative completeness injected at rank time.
  - calibration.py: stratified rating×source_class sample → scan → score_separation/fit_thresholds/
    validate_labels; returns a report (does NOT auto-rewrite config.py — human-reviewed step).
  - cli.py: `scan` / `calibrate` / `rerank` / `report` (rerank works purely from stored metric_json).
Added: backend/db.py: USER tables quality_scans / quality_recording_metrics (raw metric_json stored
  separately from scores) / quality_recording_scores, registered in USER_TABLES; init_db creates them.
Added: tests/test_concert_ranker.py — repo roundtrip/idempotency/sanitize, source-class, commentary,
  family ranking, standalone, and rerank-from-stored-metrics (11 tests). No new dependencies
  (numpy/scipy already pinned; ffmpeg is a system binary, as for tapematch).

[2026-06-22] — feat(backend+gui): surface TapeMatch "needs review" verdicts as a queryable DB flag
Added: backend/db.py: tapematch_family_meta.review_flag (INTEGER) and .review_reason (TEXT) columns
  + init_db() migration; MASTER_SCHEMA_VERSION bumped 8->9.
Added: backend/paths.py: TAPEMATCH_RUNS_DIR constant (data/tapematch/runs).
Changed: backend/tapematch_sync.py: parses each synced date's analysis.md "## Verdict:" line
  (_parse_verdict/_read_review_flag/_resolve_run_dir) and writes review_flag/review_reason into
  tapematch_family_meta, so the tapematch-batch skill's "needs review" human judgment calls are no
  longer buried in per-run analysis.md files only — added init_db() call so the standalone CLI sync
  path (`python -m backend.tapematch_sync`) picks up schema migrations even without app.py running.
Changed: backend/app.py: GET /api/tapematch/families now selects fam_needs_review/fam_review_reason.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: recording-lens family rows show a
  "Needs review" warn-tone Pill (with reason as tooltip) when fam.needsReview is set.
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: library.tooltip.tapematchReview,
  library.panel.needsReview.
Added: tests/test_tapematch_sync.py: 7 cases covering _parse_verdict's em-dash verdict-line parsing.

[2026-06-22] — feat(gui): Unified Library visual refinement — type-scale roles + tabbed detail panels
Added: gui_next/src/renderer/src/lib/tokens.ts: nine --t-* type-scale role variables (display/title/
  strong/body/meta/label/micro/mono/mono-sm), four --w-* weight-ramp variables (reg/med/semi/bold),
  and --track-eyebrow, all emitted in applyTheme() and scaled by the active base fontSize. The legacy
  --lbb-fs-* loop stays for other screens. Implements instructions/library Pixel Spec §2/§3.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: replaced every raw fontSize/fontWeight
  literal with --t-*/--w-* roles (650→semi, 800→bold); reworked the performance-table column model —
  dropped the dead 32px spacer, fixed each data column to its longest content (Date 104 · Show 345 ·
  Tour 155 · Families 116 · Recs 52 · ★ 46 · Coverage 112) and added a single trailing flex spacer so
  slack parks at the table's trailing edge; recording-lens ★ column 54→48 (§5/§6). Families column
  was already collapsed to one SRC ×N pill per source family.
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: converted both detail panels
  from a single flat scroll to a pinned identity block + tab strip + swappable pane (new TabStrip
  component). Performance tabs = Overview / Recordings (count) / Setlist / Seed & Share; recording
  tabs = Overview / Assets / Seed & Share. Scroll position resets to top on tab change; Seed & Share
  is now a peer tab reachable in one click. All zone/identity text routed to --t-*/--w-* (§8–§11).
Changed: gui_next/src/renderer/src/components/primitives.tsx: Pill routed to --t-micro/--w-semi,
  centralizing the 650→600 weight normalization (§7).
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: library.panel.tab{Overview,
  Recordings,Setlist,Assets,Share} for the new detail-panel tabs.
Fixed: BUG-217 (summary strip wrapped to two lines and clipped) and BUG-218 (★ rating ellipsized) —
  fixed in passing per the spec's column/summary rework.

[2026-06-21] — fix(gui+scraper): Range Scrape with Force re-scrape ignores end_lb, scrapes all entries
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx:439 was sending lb_numbers array
  instead of start_lb/end_lb parameters; backend route ignored the array and defaulted to
  scraping from LB-1 with no upper limit. Now sends correct start_lb and end_lb parameters.

[2026-06-21] — feat(gui): copy forum topic URL to clipboard after a successful post
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: onForum now reads topic_url from the
  /api/entry/<lb>/post_forum response and writes it to the clipboard on success (single post copies the
  one link; batch copies all successful links newline-joined). Single-post toast switched to
  library.toast.postedForumCopied; batch toast appends library.toast.linksCopiedSuffix.
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: postedForumCopied + linksCopiedSuffix
  (pluralized) toast strings.

[2026-06-21] — fix(scraper): tapematch speed-offset false-distinct — lag-slope ratio refinement
Root cause: across observations.db, curator-says-same pairs that tapematch called "distinct" had
  median |speed| 9500 ppm / median corr 0.004 (vs 0 ppm / 0.815 for the pairs it got right), and 18%
  of ALL pairs railed at the ±20000 ppm edge of estimate_ratio's search range. The primary residual
  matrix resamples by the ~500 ppm coarse envelope ratio before the sample-level residual_corr, but a
  45s window tolerates only ~20 ppm residual speed error (measured: corr 1.0 at ≤20 ppm, 0.015 at
  50 ppm) — so coarse-grid error and clamped >2% offsets decorrelated true matches.
Changed: tools/tapematch/tapematch/match.py: estimate_ratio range/resolution now config-driven
  (match.ratio_search_min/max/steps); added corrected_ratio_from_lags() (pure slope→ratio math,
  refined = ratio/(1+slope)) and refine_speed_ratio() (iterates the lag-slope correction to <5 ppm).
  Lags come from drift-robust music cross-correlation, so they stay measurable when residual_corr has
  collapsed — a far finer, unbounded speed estimate than the envelope grid.
Changed: tools/tapematch/tapematch/cli.py: primary residual matrix refines the ratio for ambiguous
  high-ppm pairs (refine.trigger_min_ppm / trigger_corr_ceiling) and keeps it only if median
  residual_corr improves — self-limiting (cannot manufacture a false merge) and non-regressing.
Changed: tools/tapematch/config.yaml: widened coarse search to ±30000 ppm; new `refine` block.
Added: tools/tapematch/tests/test_ratio_refine.py: recovers offsets incl. +25000 ppm (beyond the old
  rail) to <60 ppm, sign-checked, with a different-source no-merge control. Full suite: 39 pass, 6 new;
  the 4 failing tests (test_batch_queue / test_find_lb_folders_no_audio) are pre-existing and unrelated.
Note: validated synthetically (ratio recovery) + safety guard; production confirmation is a full re-run
  of high-ppm dates (e.g. 1990-06-17, 1990-06-27) to confirm false-distinct splits collapse into the
  curator-confirmed families. See tools/tapematch/BASELINE.md (2026-06-21 section).

[2026-06-20] — feat(gui): TODO-150 step 10 — Library screen i18n (in-screen strings)
Added: gui_next/src/renderer/src/locales/en.json: new top-level `library` namespace (~214 keys:
  lens/actions/groups/bulk/toolbar/facets/views/scope/statusValue/coverageValue/columns/summary/
  empty/tooltip/ctx/toast/panel/coverage/family/setlist/share/assets), with `_one`/`_other` plural
  forms for all counted strings.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx, components/library/DetailPanel.tsx,
  components/library/actions.tsx: extracted every hardcoded English string to `t()` calls. The
  shared action registry (`buildRecordingActions`/`buildPerformanceActions`) and `coverageLabel()`
  are plain functions, so they now take a `TFunction` param threaded from each caller's
  `useTranslation()`; every rendering sub-component gained its own `useTranslation()`. Status/view/
  coverage display values use typed literal-key maps (STATUS_LABEL_KEY/VIEW_LABEL_KEY/
  COVERAGE_LABEL_KEY) so the typed `t()` resolves them without template-literal keys. All three
  files are tsc-clean; `electron-vite build` passes.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: filled the new `library` keys via
  DeepL (~19.7k chars). A few values need a human pass (DeepL quality, not bugs): de
  `lens.byPerformance` → "Nach Leistung" (wrong sense of "performance"), `panel.youHold_other`
  garbled, and `summary.toGo`/`facets.decade` came back English in several locales. (The
  `scripts/deepl_translate_gui_next.py` missing-key/`set_leaf` fixes that made translating a brand-new
  namespace possible were logged in the earlier DeepL-sweep entry below.)

[2026-06-20] — feat(gui): TODO-155 pipeline stage icons — implement design_handoff_pipeline_icons
Added: gui_next/src/renderer/src/components/pipeline/PipelineIcon.tsx: new reusable component
  porting the locked "Pipeline Stage Icons" handoff (Option D tactile tile · Pulse animation ·
  Vivid palette) into the React stack. Exports <PipelineIcon stage status size />, PipelineGlyph,
  PIPELINE_STAGES, and PipelineStage/PipelineStatus types. Glyph paths (verify/lookup/rename/
  lbdir/collect) copied verbatim from the handoff PIPE_GLYPHS; glyph scales to round(size*0.56).
Added: gui_next/src/renderer/src/index.css: appended the .pipe-tile* visual + animation rules
  verbatim from the handoff CSS — radial-gradient fill, bevel/lift box-shadows, status modifiers,
  and the pipeRing/pipeSheen Pulse keyframes wrapped in @media (prefers-reduced-motion:
  no-preference). Derived shades (hi/lo/shadow/glow) computed via color-mix(in oklab,…) off a
  single --pipe-mid per status.
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageNode now renders a
  PipelineIcon tile instead of the old 22px circle (check/x/!/spinner/number), so both the
  per-row StageTracker (queue table) and the full-width StageStepper (detail view) in
  ScreenPipeline show the new tiles. Added STAGE_TO_TILE / STATE_TO_TILE maps (tracker 'file'
  stage → 'collect'; 'mute' state → 'pending'); StageNode gained an optional `size` (default 24)
  and `n` is now unused (kept for API compatibility). The `current` accent ring is preserved as
  an outer box-shadow; running stages now Pulse rather than spin. StageTracker (queue-table row)
  tiles bumped 25% (24→30px), left-aligned with fixed-width connectors and 14px/24px padding so the
  Pulse rings (which expand ~22px past each tile) have room on all sides instead of clipping at the
  column edges; ScreenPipeline.tsx Stages column widened 232→340px, which pulls the icon block
  left. Folder column is the flexible remainder again (~comfortably wide) with word-wrap
  (whiteSpace:normal + overflowWrap:anywhere) so the occasional long folder name wraps instead of
  ellipsis; the right cluster (Stages 340 / Status 420 / LB# 104 / actions 160) is now fixed-width
  and right-anchored, pinning the LB# column to the right edge (a brief earlier pass left actions
  flexible, which pushed LB# inward with a large right gap). Icons column horizontal padding raised
  +50% (24→36px) for extra breathing room on both sides. Status-cell pills constrained to 50%
  width (they were being stretched full-column by the flex-column's default align-items:stretch)
  and centered in the column (container alignItems:center; pill justifyContent:center) so each pill
  sits with equal padding on both sides; the LB# column text is now centered (TD/TH align:center)
  rather than left-justified. Stages and Status column headers also centered (TH align:center) so
  they sit visually over the icon cluster / centered pills. Column widths unchanged. Added light
  vertical column-divider lines to the queue table (index.css .pipe-queue-table cell border-right,
  color-mix 60% of --lbb-border; wrapper div tagged className="pipe-queue-table") — scoped to this
  table only (not the shared TD/TH primitives), skipping the edge-bar and last columns and the
  full-width group-header rows. Centered the select checkboxes (header TH + per-row TD align:center)
  in the left checkbox column.

[2026-06-20] — fix(gui): DeepL i18n sweep — fill all missing/still-English locale strings
Fixed: scripts/deepl_translate_gui_next.py: two bugs that left whole sections untranslated.
  (1) set_leaf() walked into intermediate keys without creating them, so any en.json key whose
  parent subtree was absent from a locale raised KeyError and aborted the run — now uses
  setdefault to create missing parents. (2) The to_translate selection only re-sent keys that
  were present-but-still-English; keys missing entirely from a locale were silently skipped
  (contradicting the skill's documented "missing keys are picked up on the next run"). Added a
  `missing = path not in target_leaves` branch so absent keys are translated too.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ran the fixed script — filled
  ~70 keys per locale that were never propagated (the entire `archiveOrg` upload screen, plus
  `setup.purges`, `rename.disambiguate`, `pipeline.autoRun*`, `lookup.owned.*`) and re-translated
  the remaining still-English strings. All five locales now have 0 keys missing vs en.json;
  residual still-English values are benign (abbreviations LB#/MD5/FFP/ST5, proper nouns
  Pipeline/Bootlegs/qBittorrent, language endonyms Deutsch/Italiano, {{var}}-only strings).
Changed: .claude/settings.local.json: updated the stored DEEPL_API_KEY (the previous one was
  disabled and rejected by DeepL with an authorization failure). DeepL chars used this session: ~13k.

[2026-06-20] — docs(gui+docs): TODO-150 handoff-vs-code gap sweep — theme i18n + doc 07 reconcile
Fixed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: the phase-2 Themes additions
  (Frame theme / Card style controls) shipped with `themes.palette` and `themes.cardStyle` keys in
  en.json only, so ScreenThemes rendered English fallback strings in the other 5 languages —
  violating the "all 6 locales together" rule. Added translated palette/cardStyle blocks to all
  five; all locales now match en's themes keyset exactly.
Changed: instructions/design_handoff_unified_library/07-tapematch-backend-integration.md: reconciled
  the spec with shipped behavior — doc still claimed "singletons are excluded (member_count >= 2
  only)" but tapematch_sync.py syncs them as label='Solo' (per CHANGELOG 2026-06-19). Updated §1,
  the sync step (§2.3), and the verification note to describe the as-shipped Solo behavior.

[2026-06-19] — fix(gui): BUG-215 blank family names in Unified Library performance detail panel
Fixed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: FamilyCard and FamilyMeter
  read fam.label, but the FamilyGroup objects passed from ScreenLibrary carry tmLabel (the field
  was renamed when the source pill replaced the inline source label). The PerfFamily interface
  still declared label, and the call site cast families with `as any`, so the mismatch compiled
  silently and every family card/meter tooltip rendered an empty name. Aligned PerfFamily with
  FamilyGroup (label → tmLabel, dropped unused dupes; famConf widened to number | null) and now
  render `tmLabel ?? src ?? 'Recording'`.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: dropped the `families={... as any}`
  cast on PerformanceDetailPanel so TypeScript verifies the shape and catches future drift.

[2026-06-19] — fix(backend): BUG-212 pin survives folder rename in pipeline
Fixed: backend/app.py: folder_rename() — after physically renaming the folder, the sticky
  "Pin & continue" link in folder_lb_link was left keyed to the old path. The next pipeline
  run (e.g. the file-step refresh that fires right after a rename) re-resolved lookup against
  the new path, found no pin, fell back to the raw "Incomplete match" checksum result, and
  cleared lb_number — leaving the File action unavailable until the user re-pinned manually.
Added: backend/db.py: rekey_folder_link(old_path, new_path) — moves folder_lb_link row(s) from
  old_path to new_path (UPDATE OR IGNORE + cleanup of any row left behind by a PK conflict).
  Wired into folder_rename()'s existing BUG-206 my_collection-sync block.
Added: tests/test_db_writes.py: TestFolderLink gained 4 cases covering rekey_folder_link
  (single link, multi-LB links, PK-conflict cleanup, no-op on nonexistent old path).

[2026-06-19] — refactor(gui): remove dup badges from Unified Library performance lens grouped view
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView family-header row no longer shows the "{N} dup" count Pill, and member rows no longer show the per-recording "dup" Pill — user found them unhelpful. Dropped the now-unused FamilyGroup.dupes field. The flat library list's Dup/Xref column and the DetailPanel's "dup" status pill are unchanged.

[2026-06-19] — refactor(gui): remove acoustic fingerprint references from Unified Library UI
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: dropped the FP column/header from the recording-lens table, the "No FP" health filter, the fp field on RecordingRow, the fpMap prefetch merge, and the onRefp/"Re-fingerprint" context-menu handler — the fingerprint feature is being deprecated.
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: removed the Fingerprint row from the owned-recording metadata card and the "fingerprinted"/"no fingerprint" line from family member rows; dropped fp from DetailRow and PerfRecording.
Changed: gui_next/src/renderer/src/components/library/actions.tsx: removed the onRefp handler and 'refp' (Re-fingerprint) action from the shared Library action registry.
Note: ScreenCollection.tsx and the dedicated Fingerprint screen/backend routes are out of scope — they still reference fingerprinting.

[2026-06-19] — feat(gui): add Expand all / Collapse all toggle to Unified Library performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView filter bar gains an "Expand all"/"Collapse all" button next to the Rating filter — toggles expandedShows for every multi-recording show plus clears collapsedFams in one click, instead of clicking each show's chevron individually; disabled when there are no multi-recording shows to expand

[2026-06-19] — fix(gui): BUG-214 separate source-type label from TapeMatch match-group badge
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: FamilyGroup.label was `famLabel || sourceType`, conflating TapeMatch's match-group name ("Solo"/"Family A"/"Family B") with the tape's source type ("Audience"/"Soundboard"/etc.) in one bold text slot — sibling rows from the same source could show either string with no visual cue they're different dimensions. label now always reflects source type; the TapeMatch name moved to a new tmLabel field rendered as its own info-toned Pill badge with a tooltip.
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: follow-up to the above — the spelled-out source label ("Audience") was then 100% redundant with the existing AUD/SBD source pill since both derived from the same fam.src. Removed FamilyGroup.label and its rendered span; the source pill is now the sole on-screen indicator of source type at the family-row level.

[2026-06-19] — feat(gui): add Year filter to Unified Library performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView filter bar gains a "Year" dropdown next to "Decade" — activeYear state, facetCounts.yearC, filteredPerfs predicate, clearAll/filterChips/perfActiveCount all wired the same way as the existing Decade filter, just keyed on the exact show year instead of the decade bucket

[2026-06-19] — feat(gui): default Unified Library views hide Private/Missing entries (TODO-154)
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: recording lens filteredRows — when no Status filter chip is active (the default), rows with status Private or Missing are now excluded; selecting the Status chip (including Private/Missing themselves) still overrides this and shows exactly the selected statuses, same as any other filter chip
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: performance lens performances memo — recordings with status Private/Missing are now dropped from each show's recordings array before family grouping/coverage rollup, unconditionally (no per-recording Status filter exists in that lens, so there's no chip to opt back in with). Shrinks family/coverage counts accordingly (e.g. "3 of 4 families" becomes "3 of 3" if the 4th member was private); a show whose only recordings were private/missing now rolls up as coverage='Undocumented' instead of showing hidden entries

[2026-06-19] — feat(gui+backend): add ALD (Assisted Listening Device) as a 6th source_type value (TODO-153)
Added: backend/db.py: _SRC_ALD_RE matches \bald\b (case-insensitive); checked first in _classify_source_text(), ahead of Soundboard, since descriptions that mention both (e.g. "Digitally Remastered Soundboard, (assisted listening device (ALD) is the source)") are clarifying the true source, not offering two guesses
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx and gui_next/src/renderer/src/components/library/DetailPanel.tsx: SRC_ABBR/SOURCE_FULL/SRC_HUE maps now include ALD ('ALD' badge, label 'Assisted Listening Device', --lbb-bad-fg hue to stay visually distinct from the other 5)
Changed: data/losslessbob.db: re-tagged the 37 entries whose description names ALD explicitly with source_type='ALD', overriding whatever the earlier bulk passes had swept them into (21 had become Audience, 13 Soundboard, 3 Mixed); backed up DB first

[2026-06-19] — chore(db): bulk-persisted classify_source_type() guesses into entries.source_type (TODO-153)
Changed: data/losslessbob.db: entries.source_type was added at schema v8 as a curator-only field, deliberately "never heuristically backfilled" (see comment at backend/db.py:1078-1082) — at user's explicit request, reversed that for this session: ran classify_source_type() over all rows where source_type was NULL and persisted the result for every confident hit. 3,805 rows updated (Audience 3160, Soundboard 579, Mixed 34, FM/Pre-FM 32); the other ~12,825 rows with no confident keyword signal are untouched and remain NULL.
Changed: data/losslessbob.db: per tape-trading convention (audience is the unstated default for live recordings; soundboard/FM/mixed get called out explicitly because they're notable) — second pass defaults source_type='Audience' for the remaining still-NULL rows where lb_category IN ('concert','unknown') AND description is non-empty (10,972 rows). Deliberately excludes the 408 non-concert rows (studio/tv/interview/compilation/rehearsal/radio/soundcheck — audience-default doesn't fit a TV/radio broadcast or studio session) and the 1,445 rows with a completely empty description (zero text to default from). entries.source_type is now populated for 14,777/16,630 rows (88.8%); 1,853 remain NULL.
Added: data/backups/losslessbob_2026-06-19_194959_780578_source_type_backfill.db and data/backups/losslessbob_2026-06-19_195814_210904_source_type_audience_default.db: pre-write snapshots via backup_database() for both bulk passes, in case either needs to be reverted.

[2026-06-19] — fix(gui): BUG-214 ungrouped recording rows in performance lens now select into DetailPanel
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: fam row onClick called setSelectedId
  (the parent performance) for every family row, including single-member (non-TapeMatch-grouped)
  rows; only true multi-member "member" sub-rows had a click handler that selected the recording
  itself, so clicking an ungrouped recording silently did nothing to the panel. Single fam rows
  now call setSelectedMemberLb(lone.lbNumber), matching member-row behavior, and get the same
  selected-row highlight.

[2026-06-19] — feat(backend): display-only source-type classifier fills SourceBadge gap (TODO-153)
Added: backend/db.py: classify_source_type()/_classify_source_text() — conservative keyword classifier (Soundboard/FM-Pre-FM/Mixed/Audience) over entries.source_chain (preferred, already label-extracted) falling back to raw description; deliberately excludes "Master" (too ambiguous — usually means tape generation, not source type, in trader lineage text); excludes vinyl "Matrix: BDGD"-style runout codes via negative lookahead so they don't get misread as a SBD+AUD matrix mixdown
Fixed: backend/db.py: search_entries() and get_performances() now fall back to classify_source_type() display-only when entries.source_type (curator-edited, NULL for all 16,630 rows) is empty — fixes SourceBadge in the Unified Library performance detail panel always rendering blank; classifies ~3,805/16,630 entries (Audience 3160, Soundboard 579, Mixed 34, FM/Pre-FM 32), never written back to the DB column
Changed: backend/db.py: get_performances() SELECT now also pulls e.description, e.source_chain to feed the classifier

[2026-06-19] — fix(backend): Unified Library date sort now numeric YYYY-MM-DD instead of M/D/YY string
Fixed: backend/db.py: get_unified_library_performances returned "date" as raw M/D/YY date_str; localeCompare on that sorted Oct 2 after Oct 19; now returns ISO date (YYYY-MM-DD) when available so lexicographic sort is chronologically correct

[2026-06-19] — fix(backend): sync TapeMatch singletons as "Solo" to eliminate orphan Recording rows in Library
Fixed: backend/tapematch_sync.py: recordings TapeMatch processed but found no acoustic match were silently dropped by the >= 2 singleton filter; now synced into recording_families / tapematch_family_meta with label='Solo', by='ai' so they render as "Solo LB-XXXXX" in the performance lens instead of the confusing fallback "Recording LB-XXXXX"

[2026-06-19] — feat(gui): PerformanceDetailPanel full rewrite to match prototype perf-parts.jsx
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: complete rewrite of PerformanceDetailPanel; now matches prototype anatomy — DOW badge + CoverageChip identity row → 24px/800-weight date → 14px venue → 12.5px city → 11.5px tour → italic title → ActionBar → weighted FamilyMeter coverage card (with dupe count, upgrade warning, best owned rating) → 3-col Fact cards (Families/Setlist/Length) → RECORDING FAMILIES section with FamilyCard[] (SourceBadge + family label + MatchChip confidence chip + per-member MemberRow with owned/wish/dup pills + fingerprint status) → lazy Setlist from /api/bobdylan/show?date= → AssetStrip scoped to canonical → ShareSeed for owned recordings
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: new subcomponents — CoverageChip, SourceBadge, MatchChip, FamilyMeter, FamilyCard, MemberRow, Setlist, Fact; new PerfFamily and PerfRecording exported interfaces
Added: gui_next/src/renderer/src/components/Icon.tsx: tapematch icon (tape/waveform shape for TapeMatch AI grouping UI)
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceDetailPanel call site now passes families={familiesOf(perf.recordings)}

[2026-06-19] — fix(gui): Library filter bar — FilterMenu styling, Views menu, empty Source fix
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: FilterMenu button height 30→28, borderRadius 7→6, inactive fontWeight 550→500, inactive color lbb-fg→lbb-fg2 to match prototype lbb-ui.jsx spec
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: "Recordings" filter label renamed to "Source"; Source filter in both lenses conditionally rendered only when source_type data exists (currently always NULL in DB, so the empty dropdown is hidden rather than showing a broken menu)
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView now has a Views preset menu (All performances / My collection / Coverage gaps / Wishlist / Duplicates) matching the prototype libu-performance.jsx ViewsMenu; wired to perfView state that applies additional post-facet filtering; clearAll resets perfView; active view shows as chip in summary strip

[2026-06-18] — fix(backend): Library performance lens — shows with varying location strings now group correctly
Fixed: backend/db.py: get_performances() was keying show groups on (date_str, location); recordings for the same concert date with different raw location strings (e.g. "Munich" vs "Munich, West Germany") produced multiple duplicate show rows for the same date. Changed primary grouping key to the resolved ISO date when available — Bob Dylan does not play two venues on the same calendar day, so ISO date alone is the correct deduplication unit. Fallback to raw date_str::location for entries with unresolvable dates (unchanged). Also improved city display: prefers dylan_performances.city over raw entries.location when bobdylan_shows has no match.

[2026-06-18] — feat(gui): Unified Library — detail panel structural fix + performance family auto-expand
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: rewritten to match prototype panel anatomy — aside container now uses --sep-detail-bg/border/radius/shadow token cascade; width 380 (recording) / 400 (performance); proper header with DETAILS label + Open LB page button + chevRight collapse; scrollable inner div; collapsed-to-40px stub state with info icon; recording panel content restructured (owned-dot pills at top, 16px LB# identity, file metadata grid, catalog note for unowned); performance panel accepts nullable perf with empty-state message; both panels accept open/onToggle props
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: added detailPanelOpen state to both recording lens and PerformanceLensView; panels always mounted (collapse to 40px instead of being removed); added useEffect auto-expand of first multi-recording show when performance data loads (mirrors prototype which pre-expands one show so family groups are visible by default)

[2026-06-18] — feat(gui): Unified Library — replace left facet rail with top filter bar per 06-pixel-spec.md
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: removed filterPaneOpen state + <aside> facet rail from both lenses; added FilterMenu, MenuLabel, ViewToggle, ScopeControl components; restructured recording lens and PerformanceLensView to 3-bar header stack (toolbar / filter bar / summary strip) with --sep-* CSS tokens; recording lens colgroup updated to 11-col spec (3·34·92·88·88·auto·54·auto·60·52·52 for all/unowned, 3·34·92·88·88·auto·54·250·180·90·44 for owned); performance lens colgroup updated to 10-col spec (3·30·32·116·auto·210·132·56·56·150); BulkActionBar moved to position:absolute float inside table region; ViewToggle moved into each lens toolbar (no longer a separate bar); GroupRow colSpan updated to match new col counts (colCount-1)

[2026-06-18] — fix(backend): make the ruff pre-commit hook cross-platform
Fixed: .pre-commit-config.yaml: entry hardcoded an absolute Windows path to ruff.exe (set in a
  prior Windows session), which failed every commit on Linux. Switched the hook from
  `language: system` (relies on a hardcoded interpreter path) to `language: python` with
  `additional_dependencies: ["ruff==0.15.16"]` — pre-commit now manages its own isolated venv
  for the hook on whichever OS runs `git commit`, so no machine-specific path is needed.
Fixed: backend/app.py: two ruff-flagged unsorted import blocks (geocoder/integrity_monitor
  imports in _running_jobs_summary, folder_naming imports in _pipeline_process_folder),
  auto-fixed via `ruff check --fix`.

[2026-06-18] — fix(gui): collection "Send to →" now sends all checked rows to pipeline/verify/etc
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: handleCtxSendTo used single row.diskPath; now uses getCtxRows to collect all checked rows' paths into the folder queue. Disabled state updated to match.

[2026-06-18] — feat(gui): collection view right-click "Select All Visible"
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: context menu item at top that adds all currently filtered+sorted rows to checkedIds

[2026-06-18] — fix(backend): TODO-151 follow-up — root-cause the guest-spot/NET classification gap
Changed: backend/db.py: `_PERF_CATEGORY_MAP` gained `GUEST -> concert`, `NET -> concert`,
  `SIDEMAN -> studio`. Root cause of the prior degraded-row workaround: `dylan_performances`
  (already imported, 5127 rows) tags guest appearances at other artists' shows as `GUEST`
  (66 rows) and Never Ending Tour-era shows as `NET` (3433 rows — not "internet"), but neither
  code was in the category map, so classify_entry_categories() silently dropped them to tier-3
  keyword matching or 'unknown' instead of tier-2 `dylan_performances` matching. `SIDEMAN`
  (38 rows, backing-musician studio sessions) was unmapped too.
Changed: backend/db.py: bumped the one-time classification backfill meta key from
  `lb_category_backfill_v1` to `_v2` so existing installs reclassify automatically on next
  launch (verified via a real backend restart, not a raw DB edit): concert 14092->14329
  (+237), unknown 2043->1811 (-232), studio 96->101 (+5).
Changed: backend/db.py: get_performances() now falls back to `dylan_performances.venue` when
  `bobdylan_shows` has no row for a show's date (true for nearly all GUEST dates) — e.g. the
  1986-02-19 Melbourne show now reports "Melbourne Sports And Entertainment Centre" instead of
  just the entry's raw location text.
Note: the prior session's `confirmed: false` degraded-row fallback (TODO-151, below) stays in
  place for whatever this still doesn't cover — it now only fires for ~19 shows instead of 198
  (mostly category `FILM`, e.g. the 1986 Bristol Colston Hall "Hearts of Fire" filming, plus a
  few TV-awards/White-House/studio-session dates with no clean mapping). FILM stays unmapped —
  some FILM rows are non-performance B-roll (hotel rooms, a gas station), not shows.

[2026-06-18] — fix(backend+gui): TODO-151 — performance lens recovers misclassified shows
Changed: backend/db.py: get_performances() now also includes lb_category='unknown' entries
  that have a fully-specified date (no 'xx' placeholder) and a non-blank location, grouping
  them the same way as 'concert' entries but flagging the show `confirmed: False`. Audit of
  the live DB found 252 such 'unknown' rows (of 2043 total); spot-checking ~40 showed most
  are real performances bobdylan_shows doesn't track (guest appearances at other artists'
  shows — Dire Straits, U2, Tom Petty, Grateful Dead, Springsteen, Clapton — plus a few
  legitimate Dylan dates missing from bobdylan_shows, e.g. 1986-09-19 Bristol Colston Hall).
  Recovers 198 shows previously invisible in the performance lens. The other 1791 'unknown'
  rows (no date or only an 'xx' date) have no reliable grouping signal and stay excluded.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx, components/library/DetailPanel.tsx:
  PerformanceRow gained an optional `confirmed` field; show rows and the performance detail
  panel render an "Unconfirmed" pill (tooltip explains it's inferred from the recording's own
  date/location, not a matched show) when `confirmed === false`.
Closed: TODO-151 (was Open in TODO.md, moved to TODO_DONE.md).

[2026-06-18] — feat(gui+backend): TODO-150 step-7 follow-up — wire the m3u performance action
Changed: backend/app.py: GET /api/collection/export/m3u accepts an optional `lb_numbers`
  comma-separated query param to restrict the export to specific LB numbers; returns
  `show.m3u` when filtered (vs `collection.m3u` for the full export). Verified against the
  live backend: full export unchanged, `?lb_numbers=1` produces a correct 2-track playlist,
  non-matching/junk LB numbers degrade to an empty-but-valid `#EXTM3U` file rather than erroring.
Added: gui_next/src/renderer/src/components/library/actions.tsx: `onM3u` to `ActionHandlers`
  and the `m3u` action (Export show as M3U) to `buildPerformanceActions()`, operating on the
  show's owned recordings — this was deferred at step 7 pending the backend filter above.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: added a local `blobDownload()`
  helper (same pattern as ScreenCollection.tsx/ScreenTrading.tsx) and an `onM3u` handler.
  `sources`/`notify` action ids and the TapeMatch family `note` field remain unexposed —
  there's no "find sources"/notification system or family-note write path anywhere in the
  app to wire them to; building either would be a new feature, not a loose end of this ticket.
Note: i18n (TODO-150 step 10, in-screen Library strings) is deferred per user decision —
  English-only is acceptable for now.

[2026-06-18] — feat(gui): TODO-150 phase 9 — Library screen/route/nav wiring
Changed: gui_next/src/renderer/src/App.tsx: replaced the temporary, nav-hidden `/library-dev`
  route with the real `/library` route.
Changed: gui_next/src/renderer/src/components/AppShell.tsx: `NAV_GROUPS`'s Library group gained
  a new item (`{ id: 'library', label: 'Library', icon: 'library', featured: true }`) above
  "My Collection", per instructions/design_handoff_unified_library/05-integration.md's nav
  placement spec — picks up the existing featured "NEW" badge for free. No i18n work needed:
  `appShell.nav.library` already existed in all 6 locales (previously only used for the group
  header, which reads the same word). `tsc --noEmit` and `npm run build` both pass.
  Build order step (9) of TODO-150 is done; step (10) (i18n for in-screen Library strings)
  remains.

[2026-06-18] — feat(gui): TODO-150 phase 8 — Library detail-panel zones
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: `RecordingDetailPanel`
  and `PerformanceDetailPanel`, zoned per instructions/design_handoff_unified_library/
  02-action-system-parity.md — header, `ActionBar` (primary + Reveal + grouped "More" using
  the step-7 action registry/menu), `ShareSeed` (status line + qBittorrent/torrent/forum
  actions + a unified date-sorted activity log merged client-side from the existing
  `/api/collection/prefetch` torrents/forum_posts arrays), `AssetStrip` (attachments/
  spectrograms/map as state chips, spectrogram readiness checked lazily via the existing
  `/api/spectrogram/list`), and an optional Setlist line for the performance panel.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: both lenses now render the
  detail panel as a third column on row selection. Recording lens activates the
  already-existing but previously-unused `selectedLb` state; performance lens adds
  `selectedMemberLb` next to the existing `selectedId` (member-row selection takes
  precedence). Added a bulk `/api/attachments/cached` query and a `historyMap`/
  `attachCountMap` built from `prefetch`, shared by both lenses.

[2026-06-18] — fix(backend): TODO-150 — performance lens excludes non-concert recordings
Changed: backend/db.py: get_performances() now filters its source query to
  `lb_category = 'concert'` so radio/tv/interview/studio/rehearsal/soundcheck/
  compilation/other/unknown recordings no longer get grouped into bare, misleading
  show rows in the Library performance lens; they remain visible via the recording
  lens. Added TODO-151 to audit lb_category classification accuracy now that it gates
  lens membership rather than just a cosmetic badge.

[2026-06-18] — feat(gui): TODO-150 phase 7 — Library shared action registry + bulk bar
Added: gui_next/src/renderer/src/components/library/actions.tsx: the shared Library action
  registry per instructions/design_handoff_unified_library/02-action-system-parity.md — `LibAction`
  vocabulary grouped into open/listen/acquire/share/assets/maintain, `buildRecordingActions()`
  and `buildPerformanceActions()`, a grouped fixed-position `ActionMenu` + `useActionMenu()`
  hook, and `BulkActionBar`.
Added: gui_next/src/renderer/src/components/primitives.tsx: `Toast` and `ConfirmDialog`,
  ported from ScreenCollection.tsx's local copies so other screens can reuse them; exported
  from components/index.ts.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: wired the action registry into
  both lenses. Recording lens gained a checkbox column + `BulkActionBar` (Create torrent / Add
  to qBittorrent / Update location / Remove, batched over the checked set) and a right-click
  context menu; performance lens show rows and member rows now open the matching grouped menu.
  All action handlers call the same backend endpoints ScreenCollection.tsx already uses
  (qbt/add, torrent/create, preview_forum+post_forum, collection PATCH/DELETE, wishlist,
  fingerprint/build, spectrogram/generate, open/vlc, window.api.openPath/pickDir) — no backend
  changes this step. `sources`/`notify`/performance-row `m3u` action ids are omitted (no
  existing backend/UI to wire them to) rather than shipped inert.
  Build order step (7) of TODO-150 is done; steps (8)-(10) (detail-panel zones, screen/route/
  nav, i18n) remain.

[2026-06-18] — feat(gui): TODO-150 phase 6 — Library screen performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: "By performance | By recording"
  segmented toggle (defaults to performance). New `PerformanceLensView` component fetches
  `/api/library/performances` + `/api/tapematch/families`, merging family data into the same
  `RecordingRow` objects the recording lens already built from `/api/search` +
  `/api/collection/prefetch` (by reference, keyed by `lbNumber`) — both lenses always agree on
  a recording's owned/wish/dup/fp state, no second merge implementation. Ported the design
  handoff's `families()`/`rollup()` reference helpers (`_source/perf-data.js`) into TS as
  `familiesOf()`/`rollupOf()`: clusters recordings by `fam` (or by `lb` for ungrouped ones),
  computes per-show coverage (Covered/Upgrade/Gap/Undocumented). Ungrouped recordings become
  singleton families, so the no-families fallback (03-data-contract.md) falls out of the same
  code path with no special-casing. Year-grouped virtualized table with show → family → member
  expand/collapse, own facet rail (decade/coverage/source-available/best-rating). Deliberately
  bare per the step-4 precedent: no detail panel, no bulk bar, no context menu (steps 7/8); the
  family `note` field is omitted since `/api/tapematch/families` doesn't expose it and extending
  that endpoint is out of scope here.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: hoisted `RATING_RANK` and added
  `SOURCE_FULL` to module scope (was recording-lens-local) so the new performance lens can share
  them; extended `RecordingRow` with optional `fam`/`famLabel`/`famConf`/`famBy` fields, set only
  by the performance lens's adapter.

[2026-06-18] — feat(backend): TODO-150 phase 5 — performance/show grouping aggregate endpoint
Added: backend/db.py: `get_performances()` groups `entries` by raw `(date_str, location)` into
  shows, cross-referencing `bobdylan_shows` (venue, setlist key, track count via `bobdylan_setlist`),
  `setlistfm_shows` (tour name), and `bootleg_titles` (release title) — none of which `/api/search`
  exposes. Per the locked TODO-150 decision this is a dedicated backend endpoint, not a client-side
  groupBy over `/api/search` results (06-gap-analysis.md §B3 open decision 1) and not a join bolted
  onto `/api/search` (same reasoning as the TapeMatch families endpoint, 07 §4). Optional fields
  (`dow`, `tour`, `setlist`, `tracks`, `title`) are omitted, never null-faked, when no source data
  exists for a show. Verified against a migrated copy of the live dev DB: 16,630 entries → 10,718
  shows in ~150ms.
Added: backend/app.py: `GET /api/library/performances` — new route, returns `get_performances()`.
  TapeMatch family data deliberately not joined in; the GUI's future performance-lens adapter
  fetches `/api/tapematch/families` separately and merges by `lb_number`, same pattern the
  recording lens already uses for `/api/collection/prefetch`.

[2026-06-18] — feat(gui): TODO-150 phase 4 — Library screen recording lens (no-families fallback)
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: new flat, LB#-keyed table over the
  full catalog — toolbar (search, group-by-year toggle), left facet rail (scope, decade, status,
  rating, source, a derived "health" group for wishlist/duplicates/unconfirmed/no-fingerprint),
  summary strip (live result/owned counts), virtualized year-grouped table. Client-side adapter
  merges the existing `/api/search` catalog with `/api/collection/prefetch` (collection,
  fingerprints, wishlist, duplicates, xref_lb_numbers) — no backend changes. This is also the
  literal no-families fallback row the performance lens (TODO-150 step 6) will reuse. Deliberately
  bare this step: no context menu, no detail panel, no bulk action bar — those are TODO-150 steps
  7/8, scoped separately to avoid building throwaway versions now. Owned-row file-card fields
  (size/files/format/cds) and the design doc's "New" status value are omitted — nothing in the
  backend computes them today and the project doesn't ship placeholder data.
Changed: gui_next/src/renderer/src/App.tsx: registered `/library-dev` as a temporary, nav-hidden
  route (same pattern as the existing `/quicklookup`) so the new screen is reachable during
  development; real nav/route wiring is TODO-150 step 9.

[2026-06-18] — feat(backend): TODO-150 phase 3 — curator-edited entries.source_type column
Added: backend/db.py: new `entries.source_type` column (schema v8, MASTER_SCHEMA_VERSION 7→8)
  for the Library design doc's `src` field (Soundboard/Audience/FM-Pre-FM/Master/Mixed →
  SBD/AUD/FM/MST/MTX badge). Unlike `taper_name`/`source_chain`/`lb_category`, this column is
  never heuristically parsed or backfilled — it stays NULL until a curator sets it via the
  (not-yet-built) detail-panel editor. Migration follows the existing `ALTER TABLE ... ADD
  COLUMN` idiom in `init_db()`. Wired into the existing read paths that already surface
  `lb_category` (`search_entries()`, `get_entries_by_lb_list()`, `get_collection()`) so it's
  available to Search/Collection/Library without a separate fetch.

[2026-06-18] — feat(gui): TODO-150 phase 2 — theme engine additions (frame theme + card style)
Added: gui_next/src/renderer/src/lib/tokens.ts: new `palette` (frame theme: slate/blue/purple/
  green/graphite, tints bg/surface/border/fg over the mode, layered like the existing accent
  system) and `cardStyle` ('framed' | 'flat', default 'flat' — preserves current look) fields on
  ThemeOptions. `PALETTES` table ported verbatim from the design handoff's `_source/lbb-tokens.js`.
Fixed: gui_next/src/renderer/src/lib/tokens.ts: `Mode` now properly includes 'system' as a type
  (previously only reachable via an `as ThemeOptions['mode']` cast in ScreenThemes.tsx that
  silently fell back to light on every reload). `applyTheme()` resolves 'system' to a concrete
  light/dark via `getSystemMode()` before indexing MODES/PALETTES/ACCENT_PALETTES/STATUS, and
  `loadTheme()` now validates 'system' as a legal stored value instead of dropping it.
Added: gui_next/src/renderer/src/index.css: ported the `--sep-*` framed-card CSS token block
  from the design handoff's `app.css` (gutter/card/ring/lift/top-highlight, per-mode shadow
  overrides), adapted from the handoff's nonexistent `#frame` element to `:root` since
  applyTheme() already sets data-mode/data-sep on document.documentElement. Inert until
  data-sep="framed" is set — no existing screen reads these tokens yet.
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: added "Frame theme" (palette
  swatches, with a "Default" tile to opt out / keep current look) and "Card style" (framed/flat
  segmented control) cards to the Themes panel. Fixed handleImportTheme() to round-trip the new
  palette/cardStyle fields instead of silently dropping them on import.
Note: i18n for the two new themes.palette.*/themes.cardStyle.* keys deferred to de/fr/es/it/nl —
  added to en.json only for now; other locales fall back to English until the Library screen
  (TODO-150 build order steps 3-9) is further along.

[2026-06-18] — feat(backend): TODO-150 phase 1 — TapeMatch backend integration
Added: backend/db.py: recording_families + tapematch_family_meta tables (SCHEMA_SQL), added to
  MASTER_TABLES, MASTER_SCHEMA_VERSION bumped 6 → 7.
Added: backend/tapematch_sync.py: sync_tapematch_families() ingests tools/tapematch/observations.db
  into the main DB — picks the best run per concert_date (highest n_sources_ran, tie-break latest
  run_id), computes a deterministic fam_id (not run-scoped), upserts both tables preserving
  label_override across re-syncs, and cleans up dissolved/changed families.
Added: backend/app.py: POST /api/tapematch/sync (manual trigger, not run at startup) and
  GET /api/tapematch/families (flat lb_number → fam_id/fam_label/fam_conf/fam_by list for
  client-side merge).
Fixed: backend/db.py: import_master_db() now checks each MASTER_TABLES table exists in the
  attached incoming DB before DELETE+INSERT, skipping (not erroring on) tables absent from an
  older pre-feature snapshot; skipped tables are reported in the returned skipped_tables list.
Added: backend/tapematch_sync.py: `__main__` CLI entry point (`.venv/bin/python3 -m
  backend.tapematch_sync`) — runs the sync standalone without the Flask backend, since tapematch
  batch runs happen via shell scripts that don't have the app server up. Wired as step 7 of the
  `/tapematch-batch` skill (`.claude/commands/tapematch-batch.md`) per doc 07 §3 — the manual
  trigger point for getting a finished batch's families into the main DB.

[2026-06-18] — fix(tools): BUG-209 — tapematch run_crawl.sh infinite loop on missing-sources date
Fixed: tools/tapematch/tapematch_session.py: run_date() now archives a **missing_sources**
  report.md (mirrors the existing insufficient_sources/rc=2 path) instead of returning rc=3
  with nothing recorded, so next_run()'s --next loop stops re-picking the same unrunnable date
  forever. Delete the run's archive dir under data/tapematch/runs/ to retry once the missing
  source(s) appear on disk.
Changed: tools/tapematch/gen_analysis.py: parse_report/build_analysis/status-line now recognize
  the missing_sources marker, same treatment as insufficient_sources.
Added: tools/tapematch/tests/test_missing_sources.py: regression coverage for the new marker.

[2026-06-18] — feat(backend+gui): multi-LB pipeline — same recording under two archive entries
Added: backend/db.py: folder_lb_link migrated to composite PRIMARY KEY (folder_path, lb_number); added
  get_folder_links() returning all links per folder; set_folder_link now INSERT OR IGNORE (idempotent).
Added: backend/folder_naming.py: build_multi_lb_name() produces compound tag e.g. (LB-16308+LB-16340).
Changed: backend/app.py: lookup step detects all-perfect multi-LB match (all lb_summary statuses
  "MATCHED"), auto-writes links for all LBs, passes lb_numbers list through; rename step builds compound
  folder name when lb_numbers > 1; true ambiguous conflict still blocks as before.
Changed: gui_next/.../ScreenPipeline.tsx: ok lookup block renders multi-LB label ("LB-16308 + LB-16340"),
  "same recording, both entries" annotation, "Multi-LB" status tag, and updated hint text.

[2026-06-17] — fix(backend): BUG-206/207 — pipeline rename leaves stale collection row and logs doubled old_path
Fixed: backend/rename.py: write_rename_log now correctly computes old_path and new_path under both
  calling conventions (folder_path = folder itself, or = parent directory); fixes old_path doubling
  (BUG-207) and pre-existing new_path miscalculation in rename_tab call site.
Fixed: backend/app.py: folder_rename() now queries my_collection after rename and updates disk_path
  + folder_name if the folder was already in the collection (BUG-206).

[2026-06-17] — fix(gui): BUG-208 — pipeline "File all" and explicit filing bypass a pending rename
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: fileableRows/selectedFileable now
  exclude rows where rename.status==='warn' && proposed is set. applyFile bails with a toast if
  rename is pending. CollectReadyDetail gains useTranslation(), a renamePending warning banner, and
  a disabled File button when a rename is outstanding. Also fixes latent crash (t undefined in
  CollectReadyDetail, introduced by BUG-204 fix). 3 i18n keys added to all 6 locale files.

[2026-06-17] — fix(gui): BUG-205 — filing duplicates visible rows and leaves running-state row in shelf section
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: shelfVis was missing !r.running guard, causing
  a row being filed (bucket='shelf', running=true) to appear in both Running and Shelf sections simultaneously.
  Also fixed counts.shelf, fileableRows, and selectedFileable to exclude running rows. Updated _pipelineCache
  on successful filing so component remount restores correct 'done' state instead of stale 'shelf' state.

[2026-06-18] — fix(backend+gui): BUG-204 — filing a folder already in collection silently dropped the new path
Fixed: backend/filer.py: after move/copy, check for existing my_collection row by lb_number;
  call update_collection() to update disk_path/folder_name if already registered, instead of
  relying on INSERT OR IGNORE which silently discarded the new path.
Fixed: backend/app.py: file-step result now includes existing_disk_path from my_collection.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: warn banner shown in Collect
  step when owned=true and existing_disk_path is set, explaining the record will be updated.
Added: all 6 locale files: pipeline.collect.alreadyInCollectionTitle/Body keys.

[2026-06-17] — feat(gui): collection text filter now searches disk path
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: added diskPath to the search predicate so typing any part of the path filters matching rows

[2026-06-17] — fix(gui): BUG-203 — shelving a pipeline folder leaves File button visible
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added `shelved` boolean flag to
  PipelineRow; Shelve sets it, Unshelve clears it and restores computed bucket. File button,
  fileableRows, selectedFileable, and counts.shelf all exclude shelved rows.
  deriveFolderStatus returns "Shelved / Deferred" when flag is set.

[2026-06-17] — fix(backend): BUG-200 — Pipeline Verify tab shows "no checksums" for disc-subfolder layouts
Fixed: backend/checksum_utils.py: verify_folder now uses rglob to find checksum files in subdirectories (disc1/, disc2/ etc.) and qualifies bare filenames with the subdir prefix so they match disk_audio_map keys

[2026-06-17] — fix(gui): pipeline Lookup action column — label, spacing, and column width
Changed: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: renamed "Open" button to "Open on LB Website"; gap between buttons 4→8px; action column 200→360px (pin) / 130→180px (non-pin)
Changed: locales/en|de|fr|es|it|nl.json: updated lookup.table.open to localised "Open on LB Website"

[2026-06-17] — fix(gui): BUG-202 — blocked folders in Pipeline sidebar and stray File button
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: QueueRow now detects
  any step with state 'blocked' and overrides the sidebar dot and label to red/"Blocked" instead
  of yellow/"Needs you"; previously all "attn" severity folders shared the same needs bucket
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: File button in the table row now
  suppressed when any upstream step (verify/lookup/lbdir/rename) has status 'bad'

[2026-06-17] — fix(tools): run_batch OOM after many in-process date runs
Fixed: tools/tapematch/tapematch_session.py: run_batch() now spawns a fresh subprocess per date (same as year_run/crawl_run) instead of calling run_date() in-process; after ~300 iterations the accumulated heap caused an OOM when tapematch tried to mmap 5 audio sources

[2026-06-17] — chore(gui): widen Pipeline table Status and actions columns
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: batch table Status column 240px→420px and actions/buttons column 128px→224px (+75% each); folder name column has no fixed width so it absorbs the difference, shifting the Stages/LB columns left

[2026-06-17] — fix(tools): BUG-199, prep_analysis_input.py misread truncated LB numbers in report.md commentary
Fixed: tools/tapematch/prep_analysis_input.py: LB_TAG_RE now excludes LB numbers immediately followed by an ellipsis ("…"/"...") so a truncated commentary snippet (e.g. "LB-4794…" cut to "LB-47…") can't be misread as a real, distinct LB number and pull in an unrelated info file, while still picking up legitimate untruncated cross-references elsewhere in report.md
Added: 5 more data/tapematch/runs/*/analysis.md write-ups (1998-06-21/23/24/25/26); repo-wide scan of all 923 run dirs for BUG-199 found 2 actually-affected dirs (1998-06-24 already correctly excluded the contamination in its analysis.md; 1990-10-26's stale analysis_input.md regenerated clean) and surfaced a second, separate bug (BUG-200, logged Open) — 1999-02-25 Portland's report.md has another session's tapematch output verbatim

[2026-06-17] — feat(tools): tapematch analysis.md backfill tooling + repeatable batch procedure
Added: tools/tapematch/prep_analysis_input.py: bundles each run's report.md with matched data/site/files/LBF-*.txt lineage prose (checksum/shntool noise stripped) into analysis_input.md
Added: tools/tapematch/ANALYSIS_WRITER_PROMPT.md: fixed spec for writing analysis.md (verdict wording rules, per-LB table/notes/callout conventions) so the procedure doesn't need re-negotiating each run
Added: .claude/commands/tapematch-batch.md: /tapematch-batch slash command — processes the next N missing analysis.md write-ups directly in-session (subagents hit a hard Write-tool block on .md files and cost about the same per file, so direct in-session writing is the reliable path)
Added: 98 of 438 missing data/tapematch/runs/*/analysis.md write-ups generated; caught several real bugs along the way — a report.md with another session's tapematch stdout spliced in (1999-02-25 Portland run), a tapematch ingest crash on a malformed duration read, and a likely date-mis-tagged LB-06939 (its own info file says 1/17/98 New London CT, catalogued under 1998-06-17 Brussels)

[2026-06-17] — fix(backend+gui): BUG-195, incomplete-match folders block downstream pipeline steps
Fixed: backend/app.py: after an incomplete checksum match (e.g. FFP matches but MD5 does not), clear lb_number so lbdir/rename/file steps stay mute unless the folder was explicitly pinned by the user
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: warn+lb_number branch now shows pin option with explanation; handlePin now re-runs all downstream steps after pinning

[2026-06-16] — feat(tapematch): single-date wrapper, decade-priority crawl mode, require-all-sources-by-default
Added: tools/tapematch/run_date.sh: shell wrapper for running a single concert date
Added: tools/tapematch/run_crawl.sh: shell wrapper for --crawl mode
Added: tools/tapematch/tapematch_session.py: get_all_dates(), _decade_priority(), _decade_label(), crawl_run() — processes all unrun dates prioritised 90s→00s→10s→20s→pre-1990, resumable
Changed: tools/tapematch/tapematch_session.py: find_lb_folders() now returns (found, excluded) so truly-missing sources can be distinguished from private/no-audio exclusions
Changed: tools/tapematch/tapematch_session.py: run_date() skips with RC=3 by default when any non-excluded source is absent from disk; --allow-missing overrides
Changed: tools/tapematch/tapematch_session.py: year_run(), crawl_run(), run_batch() propagate allow_missing and handle RC=3 as a labelled [SKIP]

[2026-06-16] — feat(backend+gui): TODO-147 — install hints for missing helper tools in Setup tab
Added: backend/sox_utils.py: get_install_hints() returns per-tool winget/brew/apt install commands for current OS
Changed: backend/app.py: /api/spectrogram/check now includes ffmpeg/sox/flac/shntool _install_hint fields
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: HelpersStrip shows install commands below yellow dots

[2026-06-16] — fix(backend+tools): BUG-187/192, bloom filter path isolation and Windows termios
Fixed: backend/db.py: BUG-187 — track _bloom_db_path alongside _bloom; lookup_checksums skips
  the bloom filter when it was built for a different db_path, preventing stale filters from one
  test's temp DB silently dropping checksums in another test's lookup.
Fixed: tools/batch_verify.py: BUG-192 — moved termios/tty to guarded try/except at module level
  (_HAS_TERMIOS flag); _KeyboardController.start/stop check the flag so the module is importable
  on Windows and pytest collection of test_batch_verify.py no longer fails.

[2026-06-16] — fix(backend+gui): bobdylan scraper intermediate messages now appear in Electron log
Fixed: backend/bobdylan_scraper.py: added _set(message=…) at sitemap index result, per-sitemap
  fetch start/failure, and scrape queue count — these only wrote to Python logger before.
Fixed: gui_next/…/ScreenScraper.tsx: moved bobdylan message→log push outside status==='running'
  gate so terminal messages (done/error) now appear; errors rendered with 'bad' tone.

[2026-06-16] — fix(gui+backend): BUG-195/196/197/198, pipeline display bugs and race conditions
Fixed: backend/app.py: BUG-196 — scan-tree shallow mode no longer adds both parent AND child
  folders when root has direct audio; store root_has_audio once and skip child iteration.
Fixed: backend/app.py: BUG-198 — folder_rename TOCTOU race: inner try/except around
  folder.rename() catches FileExistsError/OSError and returns 409 instead of 500.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: BUG-197 — auto-rename effect
  changed from forEach (all concurrent) to sequential async IIFE (for-of + await applyRename).
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: BUG-195 — added measureElement
  callback to virtualizer so actual DOM heights are used instead of fixed 38 px estimate.
Fixed: gui_next/src/renderer/src/components/table.tsx: BUG-195 — TR and GroupRow converted
  to React.forwardRef so virtualizer can measure their inner <tr> elements.

[2026-06-15] — feat(backend+gui): Bob Dylan scraper card in admin dashboard with stale-reset context
Added: backend/app.py: bobdylan_scraper.get_status() included in /api/admin/status response
Added: backend/admin.html: Bob Dylan Scraper card (status, phase label, progress bar, Start/Stop)
Added: backend/admin.html: updateBdScraperUI() / bdStart() / bdStop() JS; wired into pollStatus()
  The status message (e.g. "Discovered 2000 URLs, 0 new, 7 reset") is shown in the log line.

[2026-06-15] — fix(backend+gui): status bar now reflects all background workers (was always "Idle")
Fixed: backend/app.py: /api/activity/busy was missing site_crawler, bobdylan_scraper,
  setlistfm, and geocoder — four workers that use different status formats. Added them
  with format-aware checks (running bool vs status=="running"). Added matching i18n keys
  in all 6 locale files: crawling, bobdylan_scraping, setlistfm_syncing, geocoding.

[2026-06-15] — fix(backend): dynamic sitemap discovery so new bobdylan.com shows are found
Fixed: backend/bobdylan_scraper.py: replaced hardcoded 3-sitemap list with dynamic index
  fetch (_get_date_sitemap_urls) that reads wp-sitemap.xml and discovers all posts-date
  sitemaps; fallback to _SITEMAP_URLS_FALLBACK if index unavailable. Added 404 WARNING log
  to _fetch so silent failures are visible. Fixes BUG-193.

[2026-06-15] — fix(backend): importer empty-file error, dbedit DoS guard, datetime.utcnow deprecations
Fixed: backend/importer.py:run_import: moved close_connection(temp_db_path) and unlink() outside
  the `with get_connection() as conn:` block. Previously, calling close_connection() inside the
  with-block then returning caused sqlite3's __exit__ to call commit() on the already-closed
  connection, raising ProgrammingError instead of the intended "No checksums found" error.
Fixed: backend/app.py:dbedit_rows: added max(1,...) guard on `limit` and max(0,...) on `page`.
  Previously a caller passing limit=-1 would produce LIMIT -1 in SQLite, returning unlimited
  rows — a memory/timeout hazard on large tables.
Fixed: backend/importer.py, db.py, flat_file.py, qbittorrent.py, app.py: replaced all
  datetime.utcnow() calls with datetime.now(UTC). utcnow() is deprecated since Python 3.12
  and was generating DeprecationWarnings in every test run. Added UTC to relevant imports.

[2026-06-15] — fix(backend): db_reset now wipes all master data, not just early-era tables
Fixed: backend/app.py:db_reset: rewrote to use MASTER_TABLES as the canonical drop list instead
  of a hardcoded 6-table subset. Now clears all 19 master tables (lb_master, lb_alias,
  lb_missing, bootleg_titles, flat_file_releases/changelog, location_geocoded, etc.) and wipes
  MASTER_META_KEYS from meta while preserving all user data. Also removed the incorrect dropping
  of rename_history and torrents (USER_TABLES) that the old reset included.

[2026-06-15] — fix(backend+tests): BUG-190/191 — first Windows pytest run; fixed 2 blocking failures
Fixed: backend/importer.py:_import_flat_file: replaced init_db(temp_db_path) with a raw
  sqlite3.connect() that creates only the checksums table and closes explicitly. init_db spawns
  bloom-filter and migrate_lb_master daemon threads that hold the temp file open; on Windows
  this caused PermissionError on unlink() (BUG-191).
Fixed: tests/test_lb_master.py:test_reconcile_logs_transition: changed test LB from 7 → 11.
  LB 7 is in _LB_MISSING_SEEDS (seeded into lb_missing by init_db), so reconcile_lb_status
  always returned 'nonexistent' rather than 'private' (BUG-190).
Added: BUGS.md: BUG-192 — tools/batch_verify.py imports termios (Unix-only), blocking
  test_batch_verify.py collection on Windows.
Added: pytest installed in .venv (was missing; required for first Windows test run).
Result: 349 passed, 5 skipped, 1 known-flaky (BUG-187 bloom filter race) in 21s.

[2026-06-15] — fix(backend): BUG-189 — master data "Check for Updates" fails when latest app release has no .db asset
Fixed: backend/app.py: master_github_check / master_github_install both used /releases/latest,
  which returns the newest release by tag (e.g. v1.5.1 — an app release with no master snapshot).
  Extracted _find_master_release() helper that pages through /releases (up to 5 pages × 20) and
  returns the first release containing both a .db asset and its .manifest.json sidecar, so master
  data check/install always finds the most recent master data release regardless of app releases
  that arrive in between.

[2026-06-15] — fix(backend+gui): BUG-188 — Windows mount paths display with mixed slashes (c:\/1958/)
Fixed: backend/filer.py:normalise_path: replaced PurePosixPath(Path(raw)).as_posix() with
  Path(raw).as_posix() — on Windows the PurePosixPath wrapper received a backslash-formatted
  str, treated backslash as a literal char, and stored it unchanged in the DB.
Fixed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: added joinRoute() helper that
  strips backslashes (legacy data) and trailing slashes from root_path before joining with
  sub_path, preventing double-slash or mixed-slash display in all four path display sites.

[2026-06-15] — fix(gui+backend): BUG-167 — Scraper shows blank screen on Windows
Fixed: backend/app.py: SQLite SUM() returns NULL on an empty table; wrapped geocoded/
  failed/manual columns in COALESCE(..., 0) so /api/geocode/stats always returns integers
  even when location_geocoded is empty.
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: added (geocoded ?? 0) guard
  on the Geocoder strip-card lastDate; updated GeoStats interface to mark geocoded/failed/
  manual as number|null (accurate).
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: added ScraperErrorBoundary
  so future render crashes show an error message + "Try again" button instead of blank screen.

[2026-06-15] — chore: v1.5.1 release
Changed: gui_next/package.json, gui_next/package-lock.json: version bumped
  1.5.0 -> 1.5.1.

[2026-06-15] — test: add unit test coverage for the scraper/integration backends
Added: tests/test_scraper.py: 20 tests for backend/scraper.py — _is_soft_404,
  _extract_setlist_from_lbbcd, scrape_entry/scrape_range against local cached pages
  (parsing, attachments, soft-404 handling, force re-parse, lb_missing skip path),
  download_pages_range with mocked _fetch, and scrape status/stop helpers.
Added: tests/test_bootleg_scraper.py: 30 tests for backend/bootleg_scraper.py —
  _parse_date (year-pivot/partial-date cases), _parse_row, _diff (add/change/remove/
  dedup), _apply_diff/_record_scrape DB writes, and scrape_bootlegs with mocked
  requests.head/get (ETag no-change, successful scrape, HEAD/GET failures).
Added: tests/test_bobdylan_scraper.py: 15 tests for backend/bobdylan_scraper.py —
  fetch_sitemap_urls (mocked sitemap XML), parse_show_page, run_discover/run_scrape/
  run_update against bobdylan_shows + bobdylan_setlist with mocked _fetch, and status/
  stop/is_running helpers.
Added: tests/test_setlistfm.py: 20 tests for backend/setlistfm.py — _parse_date,
  _fetch_page (429/401/retry handling), _parse_setlist (sets/encore/cover/tape
  flattening), save_api_key/get_api_key, run_update pagination (force vs non-force,
  missing API key, stop mid-pagination) with mocked _fetch_page, and status helpers.
Added: tests/test_geocoder.py: 30 tests for backend/geocoder.py — _entry_date_to_iso,
  _get_performance_location_string, geocode_one (mocked urllib, confidence tiers,
  429 rate-limit, HTTP/generic errors), place_manual, run_batch (dry_run, limit,
  manual_override skip, retry_failed, dylan_performances structured-query path,
  429 retry/exhaustion), and get_progress.
  All 115 new tests mock requests/urllib entirely — no live HTTP calls.
Fixed: BUGS.md: documented BUG-187 (new, Open) — a pre-existing test-isolation issue
  where init_db()'s background bloom-filter rebuild thread leaks a global `_bloom`
  state across test DBs, intermittently breaking tests/test_db_lookup.py in full-suite
  runs. Reproduced on main without the new test files; not caused by this change.

[2026-06-15] — fix: BUG-168 — "Check for update" always reported "already up to date"; add download/apply flow
Fixed: gui_next/src/renderer/src/screens/ScreenHome.tsx: handleCheckUpdate read
  non-existent `data.new_release` / top-level `data.zip_filename` fields from the
  GET /api/flat_file/discover response (which actually returns `available` and
  `current_release.zip_filename`), so the condition was always falsy and the
  "up to date" toast showed even when a new release was available — including on
  a fresh install with no database loaded.
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handleCheckUpdate had the
  same field-name mismatch; fixed identically and now correctly triggers
  loadFlatReleases() when an update is available.
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: Flat file history table now
  has per-row actions — "Download" for detected/failed/deferred releases (POSTs
  /api/flat_file/download/<id>), and "Review & Apply" for downloaded releases (GETs
  /api/flat_file/diff/<id>, shows a confirm dialog with the added/changed/removed
  counts, then POSTs /api/flat_file/apply/<id> on confirm and refreshes db stats).
  Previously "Check for update" could only detect availability with no way to pull
  the file down from the GUI.
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: new
  setup.flatFile.{download,downloading,downloadDone,reviewApply,applying,
  applyConfirmTitle,applyConfirmBody,applyDone} keys (de/fr/es/it/nl pending DeepL
  translation — DEEPL_API_KEY is currently disabled, so these fall back to English).

[2026-06-15] — fix: BUG-186 — footer "Synced · idle" badge now reflects live master-sync and worker activity
Added: backend/app.py: new GET /api/activity/busy aggregates importer/scraper/
  bootleg_scraper/integrity_monitor/filer worker status plus app-update and
  data-download state into {busy, activity}.
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: StatusBar's shield badge
  always read the literal "Synced · idle". Now checks GET /api/master/github_check
  once on mount for "Synced" vs "Update available" (curator's GitHub master-data
  release, not the LB-website flat-file), and polls /api/activity/busy every 5s for
  "Idle" vs a translated activity label (Importing.../Scraping.../Filing folder.../etc).
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: new
  appShell.statusBar.{synced,updateAvailable,idle,activity.*} keys.

[2026-06-15] — fix: BUG-185 — footer status bar now shows live DB stats
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: StatusBar fetched no data and
  rendered hardcoded placeholder values (LB-16630, 704,624, 2026-05-21, 1,380). Now
  fetches GET /api/home/stats on mount and renders live latest_lb, checksum_count,
  last_import, and bootleg_count, matching the pattern already used by Sidebar/ScreenHome.

[2026-06-15] — fix: BUG-146/165/176 — date-prefix, tapematch LB-number resolution, undecodable-source resilience
Fixed: backend/torrent_maker.py: _parse_date now preserves 'xx' month/day placeholders
  as ISO-style 'YYYY-xx-xx' / 'YYYY-MM-xx' instead of returning the raw 'xx/xx/65' string
  (BUG-146), so build_standard_name no longer proposes non-standard date prefixes for
  entries with unknown month/day.
Fixed: tools/tapematch/tapematch_session.py: _lb_num_from_folder now accepts an optional
  name_to_lb map (built from found_folders) and prefers the entry's own DB-resolved LB
  number over a regex scan of the folder name (BUG-165) — fixes degenerate self-pair rows
  in observations.db.pairs for folders whose name embeds a cross-referenced LB number
  ahead of their own (e.g. "...[fixed LB-2204]-LB-10437-v"). insert_sources and
  insert_pairs now build and pass this map; insert_pairs gained a found_folders param.
Fixed: tools/tapematch/tapematch/audio.py, ingest.py, cli.py: a single undecodable source
  track no longer aborts the whole tapematch run (BUG-176). duration_sec() now raises
  UnreadableAudioError on decode failure; ingest.source_report() wraps this into
  UnreadableSourceError(source_dir, track); cli.py main() now drops any source that
  raises this error up front, prints "[SKIP] source excluded: unreadable file <path>",
  and continues with the remaining sources (requires >=2 to proceed).
Added: tools/tapematch/tests/test_unreadable_source.py: covers UnreadableAudioError and
  UnreadableSourceError for a corrupt/non-audio file with a .flac extension.

[2026-06-14] — fix(gui): BUG-184 — backend subprocesses (ffmpeg/sox/shntool) orphaned on quit
Fixed: gui_next/src/main/index.ts: added killProcessTree(pid) — on Windows runs
  `taskkill /F /T /PID` so the entire process tree spawned by LosslessBobBackend.exe is
  killed, not just the exe itself. backendProc.kill('SIGTERM') only TerminateProcess'd
  the backend exe, leaving any in-flight ffmpeg/sox/shntool.exe child process running as
  an orphan after a normal app quit. Used in before-quit and killStalePid; also added
  /T to the existing taskkill in killPortProcess.

[2026-06-14] — fix(gui): BUG-183 — Windows installer "cannot be closed" prompt on orphaned backend
Fixed: gui_next/resources/installer.nsh (new): added `customInit` NSIS macro that force-kills
  any leftover LosslessBobBackend.exe before file extraction. Root cause: that backend
  process can outlive LosslessBob.exe after an abnormal exit (Windows doesn't kill children
  when a parent dies), and electron-builder's built-in "app is running" check only knows
  about LosslessBob.exe, so the locked backend exe made every install/update show
  "LosslessBob cannot be closed. Please close it manually and click Retry to continue."
  electron-builder auto-picks up resources/installer.nsh as the NSIS custom include.

[2026-06-14] — chore: v1.5.0 release
Changed: gui_next/package.json, gui_next/package-lock.json: version bumped
  1.4.0 -> 1.5.0.

[2026-06-13] — fix(tools): TODO-139 Task 7 — tapematch error/no-verdict triage (BUG-180/181/182)
Fixed: tools/tapematch/tapematch/ingest.py: list_tracks now requires p.is_file()
  in addition to suffix matching (BUG-180) — a subdirectory named
  "1987-10-05locarno+asm.flac" was matched as a track and crashed
  audio.duration_sec() with LibsndfileError. Re-run of 1987-10-05 now
  completes (5 sources, 2 families).
Fixed: tools/tapematch/tapematch_session.py: find_lb_folders now drops
  collection folders with no audio files via _has_audio() (BUG-181), printing
  "Excluded (no audio found): LB-XXXXX" — previously such a folder made
  ingest.concat_source raise ValueError("no audio in ...") and crash the
  entire date's run. Re-runs of 1987-10-05/1989-08-26/1989-09-03 now complete
  (2/2/8 families); 1989-09-01 (left with 1 source) now gets the new
  insufficient_sources report below instead of crashing.
Fixed: tools/tapematch/tapematch_session.py: resolve_from_collection now
  catches OSError from p.is_dir() and treats an unreachable collection path
  (e.g. /mnt/DYLAN2 offline) as "missing" instead of crashing the session
  (BUG-182, found during validation).
Added: tools/tapematch/tapematch_session.py: run_date now writes an explicit
  **insufficient_sources** status into report.md (and archives the run) when
  fewer than 2 sources remain after exclusion, instead of returning early with
  nothing written.
Added: tools/tapematch/gen_analysis.py: parse_report/build_analysis/main
  recognize the insufficient_sources marker and render a clean status section
  instead of ERROR.
Added: tools/tapematch/tests/test_ingest_list_tracks.py,
  test_find_lb_folders_no_audio.py, test_insufficient_sources.py (6 new tests;
  full tapematch suite 33/33 pass).
Added: data/tapematch/runs/20260605_214549_2026-06-05/SKIP_REASON,
  20260605_215513_2026-06-05/SKIP_REASON — mark these as test/calibration
  artifacts (2000-03-14 Visalia content under a fake date), kept not deleted.
Note: 1993-04-23 (LB-04994, d1t01.flac, 4186 bytes truncated) and 2001-07-07
  (LB-14942, d1t01.flac, 0 bytes) are genuinely corrupted source files —
  reported to user, not modified per spec. Full writeup in
  tools/tapematch/BASELINE.md "Task 7 results". This completes the TODO-139
  task sequence (Tasks 2-7).

[2026-06-13] — fix(gui): BUG-179 — Pipeline "File all into collection" left stuck-running ghost rows
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now guards
  against re-entrant filing jobs (filingRef/filingActive — bails with a toast if a
  filing job is already in flight) and the "File all N into collection" button is
  disabled while a batch is running. The /api/pipeline/file/status polling loop now
  checks status.path against row.folderPath and bails with a "job mismatch" error
  if the global _FILE_JOB has been taken over by a different job, instead of
  spinning forever with running:true and a frozen progress bar.
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: local toast state +
  showToast() in ScreenPipeline (three existing calls referenced a non-existent
  LbdirStageContent-scoped showToast — also fixed by this).
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: pipeline.file.busy,
  pipeline.file.jobMismatch.

[2026-06-13] — fix(gui): BUG-178 — Pipeline "Final storage" destination stale after Apply rename
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename updated
  row.folderPath/folderName to the renamed path and re-runs the "file" step against
  the new path, merging the refreshed dest/dest_parent/mount_label into the row —
  previously "Final storage" kept showing the destination built from the pre-rename
  folder name even though "Staging" already reflected the applied rename.

[2026-06-13] — fix(gui): BUG-177 — Pipeline "Apply rename" failed silently on duplicate folder
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename ignored error/409
  responses from /api/folder/rename (e.g. "Target already exists" when a folder with the
  proposed name already exists at the destination) and swallowed network errors, leaving the
  Rename step looking unchanged with no feedback. Now stores the error on
  row.steps.rename.error and RenameStageContent shows a "Rename failed" banner with the
  message; status stays 'warn' so the user can edit the name and retry.

[2026-06-13] — fix(gui): TODO-145 — Pipeline table dead space before LB#/Apply/File columns
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: Pipeline queue
  table colgroup gave the Status column no fixed width, so on wide windows it
  absorbed all leftover space while its content stayed left-aligned,
  stranding the LB#/Apply/File columns far to the right. Capped the Status
  column at 240px and made the folder-name column (previously fixed 380px)
  the flexible one that absorbs remaining width.

[2026-06-13] — feat(tools): TODO-139 Task 6 — re-run queue generator + batch mode
Added: tools/tapematch/build_rerun_queue.py: queries observations.db's
  `latest_pairs` view (Task 2) for concert dates with >=1
  `lb_says_same=1 AND tapematch_verdict='different_family'` pair (a miss
  against LB commentary), ordered by miss count desc. Writes
  `tools/tapematch/rerun_queue.txt` (232 dates), one date per line with the
  miss count as a trailing comment. `--since TIMESTAMP|REF` excludes dates
  whose latest run is already at/after a given ISO timestamp or git ref (for
  re-running the queue after a future fix commit lands). `--dry-run` previews
  without writing.
Added: tools/tapematch/tapematch_session.py: `run_batch()` + `--batch FILE`
  consumes a re-run queue file sequentially via the existing `run_date()`.
  Blank/comment/already-`# done`-marked lines are skipped; each completed
  line gets `# done <timestamp>` appended (resumable after interruption or
  KeyboardInterrupt, which leaves the in-progress line unmarked and exits 130).
Added: tools/tapematch/tests/test_build_rerun_queue.py (4 tests),
  tools/tapematch/tests/test_batch_queue.py (4 tests).
Changed: .gitignore: tools/tapematch/rerun_queue.txt is a generated/mutable
  artifact (gets `# done` markers as the queue is processed) — gitignored
  alongside observations.db.
Note: queue currently lists all 232 dates with >=1 lb_says_same miss (no
  --since applied yet — Task 4/5 fixes are uncommitted). Per Task 6 spec
  step 5, dates with 0 misses are never queued. Next: Task 7 (error/no-verdict
  triage).

[2026-06-13] — fix(backend): BUG-176 — pipeline rename now flags folders missing their (LB-NNNNN) tag
Fixed: backend/app.py: in the BUG-119 fallback (rename step when the DB entry has no
  date_str/location), the proposed name was derived from the current folder name with
  no check that it actually contains "(LB-NNNNN)", so untagged folders were reported as
  "Folder name is already correct" and could be promoted to "ready to file". Now, if the
  entry's location is blank but date_str is present, the rename step first looks up
  bobdylan_shows by date to fill in the location, so the standard "date Location (LB-NNNNN)"
  order can still be proposed (e.g. LB-16311 → "2022-10-06 Berlin, Germany (LB-16311)").
  Only when no bobdylan_shows match exists does it fall back to checking for the correct
  "(LB-{lb_number:05d})" tag on the existing name, stripping any stale tag, and proposing
  to append the correct one — without touching date/location (BUG-119 stays fixed).

[2026-06-13] — fix(gui): Animate "Running" spinner in pipeline stage indicators
Fixed: gui_next/src/renderer/src/index.css: the `.p2-spin` class used by
  StateGlyph and StageNode (PipelineParts.tsx) for the "Running" state circle
  had no animation defined, so the spinner rendered static. Added a
  `p2-spin` keyframes rule (360° rotation, 0.8s linear infinite) and the
  `.p2-spin` class.

[2026-06-13] — fix(gui): BUG-166 — Pipeline "In collection" badge shown before filing
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename's success branch
  hardcoded `bucket: 'done'` after a rename, even when the File step (step 5) was still
  `'warn'` (not yet filed). Now derives bucket as `r.steps.file.status === 'warn' ? 'shelf'
  : 'done'`, matching serverRowToPipeline's guard. Fixes the green "In collection"/"Filed to
  <mount>" badge appearing prematurely, and restores the "File all N into collection" button
  (was hidden because these rows weren't counted in counts.shelf).

[2026-06-13] — feat(tapematch): TODO-139 Task 5 — staircase union-flag fix + short-window calibration
Added: tools/tapematch/tapematch/align.py: union_staircase_sources() — a source
  counts as "staircase" if classified "staircase/splice" in either lag-curve pass
  (vs initial ref, or vs re-selected central ref). Fixes a reference-ambiguity bug:
  speed_info[ref_name]["kind"] is always "reference" under a single pass, so a pair
  involving the current reference source could never be flagged staircase on that
  source.
Changed: tools/tapematch/tapematch/cli.py: central-ref lag-curve pass
  (speed_info_central) now computed before the secondary-match loop so
  staircase_sources = union_staircase_sources(speed_info, speed_info_central) can
  drive the existing 15s short-window OR-fallback; central-ref pass still printed
  in its original later output position (section order unchanged).
Changed: tools/tapematch/tapematch/match.py: secondary_corr_pair() takes optional
  return_raw bool — adds win_corrs/hiss_corrs (raw per-window correlations) to the
  returned dict for calibration use.
Added: tools/tapematch/calibrate_staircase.py — one-off tool computing per-window
  residual_corr distributions at a short window size for known same-source /
  different-source-same-show staircase pairs (2001-10-30).
Added: tools/tapematch/config.yaml: secondary_match.staircase_window_sec/hop_sec
  (5.0/2.0) and staircase_window_corr_threshold/coverage_threshold (both null) —
  documented but disabled, see Note below.
Added: tools/tapematch/tests/test_staircase_union.py: 3 tests covering the
  2001-10-30 reference-ambiguity scenario, empty-second-pass case, and the
  no-staircase-sources case.
Note: calibration of the new 5s/2s pass on 2001-10-30 found no usable
  residual_corr gap — same-source median 0.0118 vs different-source-same-show
  median 0.0153 (higher), distributions fully overlap at every threshold tried. Per
  spec, the new pass was NOT wired into cli.py (thresholds left null/disabled). The
  union-flag fix itself is regression-free on 3 control dates and on 2001-10-30
  (byte-identical CLUSTERS/LINEAGE/DIAGNOSTICS, same 6/6 lb_says_same misses,
  identical corr values pre/post fix). Full writeup in
  tools/tapematch/BASELINE.md "Task 5 results". Piecewise alignment (spec step 4)
  deferred — tracked as TODO-144.

[2026-06-13] — fix(gui): BUG-175 — Windows fonts render badly (fallback font + blurry ClearType)
Changed: gui_next/src/renderer/index.html: removed the Google Fonts <link>/preconnect
  tags and tightened the CSP — style-src/font-src no longer allow
  fonts.googleapis.com/fonts.gstatic.com.
Changed: gui_next/package.json: added @fontsource/inter, ibm-plex-sans, source-sans-3,
  jetbrains-mono (pinned exact versions) so fonts ship inside the app bundle.
Changed: gui_next/src/renderer/src/main.tsx: imports local font CSS for every
  weight previously requested from Google Fonts; sets a `platform-<platform>`
  class on <html> before React mounts.
Changed: gui_next/src/preload/index.ts, src/renderer/src/env.d.ts: expose
  `process.platform` to the renderer as `window.api.platform`.
Fixed: gui_next/src/renderer/src/index.css: scoped `-webkit-font-smoothing:
  antialiased` to `html.platform-darwin` only — on Windows this property
  disables ClearType subpixel rendering, making all text look blurry/thin
  regardless of which font is loaded.

[2026-06-13] — feat(backend+gui): TODO-143 — "Check for Updates" master snapshot install from GitHub
Added: backend/app.py: GET /api/master/github_check — queries the latest
  kuddukan42/losslessbob GitHub release, downloads its manifest sidecar, and
  compares master_version against the local meta table to report whether a
  newer master snapshot is available.
Added: backend/app.py: POST /api/master/github_install — text/event-stream
  endpoint that downloads the latest master .db + manifest from GitHub
  Releases into data/imports/, verifies SHA256, and applies it via
  database.import_master_db(), streaming progress events (mirrors
  /api/master/github_release's event shape).
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: CuratorToggle gains
  a "Check for updates" button (handleCheckGithubMaster + runGithubInstall)
  that checks GitHub, confirms with the user, then streams install progress
  as toasts. Existing file-picker button relabeled "Install from file…"
  (installUpdate key) to disambiguate from the new GitHub path.
Changed: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: added
  setup.masterData.checkUpdate/checkingUpdate/githubUpdateBody and
  setup.toast.githubCheckFailed/masterUpToDate; reworded installUpdate to
  "Install from file…".
Note: porting gap from TODO-088 (PyQt _GitHubMasterThread) — gui_next only
  had the file-picker fallback; this restores the GitHub-check path.

[2026-06-13] — fix(gui): Scraper "Single Entry" Go button gave no feedback
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: the Go button's POST
  to /api/entry/<lb>/scrape discarded the response, so a skip (e.g. entry already
  up to date with force/download off) or error appeared as "nothing happened".
  Now awaits the response and writes a result line (done/skipped/error) to the
  Entry Metadata Live Log, and disables the button with a "Working…" label while
  the request is in flight.

[2026-06-13] — feat(tapematch): TODO-139 Task 4 — predicted-lag mode for speed-offset secondary match
Added: tools/tapematch/tapematch/align.py: local_lag_centered() — like local_lag()
  but centers the +-max_lag_sec residual search on an arbitrary lag_center_sec
  instead of zero, via scipy.signal.correlate(mode="valid"). No waveform resampling.
Added: tools/tapematch/config.yaml: secondary_match.high_ppm_threshold: 5000 — pairs
  whose speed offset (ppm, from estimate_ratio) is at or above this center each
  window's lag search on expected_lag(t) = lag_0 + ppm_ratio*(t - anchor0) instead
  of zero; below threshold, behavior unchanged.
Changed: tools/tapematch/tapematch/match.py: secondary_corr_pair() takes optional
  predicted_lag dict (ppm/lag_0/anchor0_sec) and uses local_lag_centered() for the
  windowed-coverage pass when |ppm| >= high_ppm_threshold.
Changed: tools/tapematch/tapematch/cli.py: computes pair_ppm from existing
  pair_ratios and lag_0 from local_lag() at anchors[0] for each cross-pair, passes
  predicted_lag into both secondary_corr_pair() call sites (main + staircase
  short-window fallback); logs PREDICTED_LAG debug lines.
Added: tools/tapematch/tests/test_predicted_lag.py: 3 tests covering
  local_lag_centered (finds a lag beyond +-max_lag_sec when centered correctly,
  not when centered on zero) and secondary_corr_pair predicted-lag activation/
  threshold gating.
Note: validated on 1989-06-04, 1990-01-12 (targets) and 3 control dates incl.
  1988-07-28 (high-ppm) — zero regressions, activates as specified, but does not
  reduce misses on either target date (root cause is not search-range for these
  pairs; see tools/tapematch/BASELINE.md "Task 4 results" and TODO-140).

[2026-06-12] — fix(backend+gui): LBDIR reconcile now recovers self-referencing/regenerated files from site/files (BUG-174)
Fixed: backend/checksum_utils.py: find_site_recoverable_files() only matched
  data/site/files/LBF-{N}-* candidates against missing lbdir entries by exact MD5.
  The lbdir manifest's self-checksum entry and regenerated report files (e.g.
  DigiFlawFinder-*.wavf.html) can never match by MD5 across lbdir revisions — the
  cached site copy is a different version of the same file — so they never produced
  a site_proposal even though a same-named LBF-{N}-* file existed. Added a
  filename-based fallback: strip the LBF-{N:05d}- prefix and compare (case/apostrophe
  -normalised) against the missing entry's basename, returning matched_by:'name' plus
  both md5 (site copy) and expected_md5 (what the folder's lbdir requires) so the user
  can see they differ.
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: SiteProposal gains
  expected_md5 and matched_by:'md5'|'name'.
Changed: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: "Recoverable
  from site/files" rows matched by name only render an "MD5 mismatch" warning pill
  (tooltip shows both hashes) plus a banner explaining the copy won't pass
  verification as-is.
Added: tests/test_checksum_utils_site_recovery.py: covers MD5 match, name-fallback
  match (self-referencing lbdir + DigiFlawFinder report), and the no-missing-entries
  empty case.

[2026-06-12] — fix(backend): qBittorrent save-path sync — match renamed folders moved between staging dirs (BUG-173)
Fixed: backend/qbittorrent.py: find_torrent_by_path()'s BUG-172 rename_history fallback
  computed the pre-rename path as old_folder.parent / <pre-rename name>, assuming the
  pipeline rename happened in the same directory qBittorrent's content_path points at.
  When the folder had been relocated between staging directories (e.g. hopper-bob ->
  1-DYLAN) before that in-place rename, the computed path never matched and sync silently
  no-op'd. Now also matches on the pre-rename folder name alone (basename), regardless of
  directory, when exactly one torrent's content_path basename matches.

[2026-06-12] — fix(backend): qBittorrent save-path sync now also fixes folders renamed before filing (BUG-172)
Fixed: backend/qbittorrent.py: find_torrent_by_path()'s fallback for torrents added outside
  the app workflow only matched on an exact content_path string, so it missed folders
  renamed by the pipeline's rename step before filing (qBittorrent still has the
  pre-rename name recorded). Now also checks rename_history for the most recent row whose
  new_path is the pre-filing folder, and matches qBittorrent torrents against the
  pre-rename name from old_path.
Added: backend/qbittorrent.py: rename_torrent_root() (POST /api/v2/torrents/renameFolder)
  and recheck_torrent() (POST /api/v2/torrents/recheck). relocate_tracked_torrent()'s
  external-match branch now relocates + renames the torrent's root folder to match the
  on-disk name, then triggers a recheck so qBittorrent immediately re-validates against
  the new location without re-downloading.

[2026-06-12] — fix(backend): Publish Master Update — GitHub asset upload returned 400 Bad Request (BUG-171)
Fixed: backend/app.py: master_github_release's _upload_asset() streamed the .db/.manifest
  asset via a plain generator while also setting a manual Content-Length header. requests
  can't size a bare generator, so it added Transfer-Encoding: chunked alongside
  Content-Length — uploads.github.com rejects that combination with 400 Bad Request at
  the first chunk. Replaced the generator with a _ProgressFile object exposing __len__
  (real file size) and read() (1 MB chunks + progress events), so requests sends a real
  Content-Length with no chunked encoding.

[2026-06-12] — fix(backend): Pipeline scan-tree finds top-level folders whose audio is in subfolders (BUG-170)
Fixed: backend/app.py: pipeline_scan_tree's shallow mode checked each immediate child of
  the picked root with `_has_audio()` (direct files only), so release folders whose audio
  lives in CD1/CD2/Extras subfolders (no audio directly in the release folder) were skipped
  entirely after BUG-167 switched the GUI to shallow scanning. Added `_has_audio_anywhere()`
  (rglob-based) for the immediate-children check — a top-level folder is now returned if it
  contains audio anywhere beneath it, while only that top-level path is added (not the
  nested subfolders).

[2026-06-12] — feat(backend): qBittorrent save-path sync now finds torrents added outside the app
Added: backend/qbittorrent.py: find_torrent_by_path() — GET /api/v2/torrents/info (unfiltered)
  and matches each torrent's content_path (or save_path/name fallback) against a folder path.
  _track_external_torrent() records a discovered torrent's infohash into the torrents table
  (updating an existing row or inserting a minimal one) so future relocations use the
  DB-tracked lookup.
Changed: backend/qbittorrent.py: relocate_tracked_torrent() now falls back to
  find_torrent_by_path() when no torrents row has added_to_qbt=1 with a matching
  source_folder/infohash, so folders seeded outside the "Add to qBittorrent" workflow still
  get their save path synced on filing.

[2026-06-12] — feat(backend+gui): sync qBittorrent save path when filing a tracked folder
Added: backend/qbittorrent.py: set_location() (POST /api/v2/torrents/setLocation) and
  relocate_tracked_torrent() — after a pipeline filing move, looks up torrents rows for
  the LB with added_to_qbt=1 and a known infohash whose source_folder matches the
  pre-move path, points qBittorrent at the new parent directory (triggering its normal
  hash recheck so seeding resumes without re-downloading), and updates source_folder in
  the torrents table on success.
Changed: backend/filer.py: start_file_job's _run() calls the new
  _sync_qbt_location() helper after a successful move + collection registration;
  result dict now includes qbt_synced/qbt_error (best-effort — never fails the filing job).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile shows a toast
  on the filing result's qbt_synced/qbt_error. Added pipeline.file.qbtSynced /
  qbtSyncFailed to all 6 locale files.

[2026-06-12] — feat(gui): Pipeline status group headers are now collapsible (TODO-141)
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: per-bucket collapsed
  state (collapsedBuckets) and toggleBucket callback. GroupRow now receives
  expanded/onToggle so clicking NEEDS YOU/READY/RUNNING/ON SHELF/DONE headers
  toggles the chevron and hides/shows that bucket's rows in the virtualized list.

[2026-06-12] — fix(backend): Publish Master Update now refreshes "Master version" / "Last published" (BUG-169)
Fixed: backend/app.py: master_github_release's _work() uploaded the exported snapshot to
  GitHub but never wrote master_version/master_published_at back into the live DB —
  export_master_db() only stamps those keys inside the exported .db, not the source DB.
  /api/master/status reads from the live DB's meta table, so the Setup screen's "Master
  version" / "Last published" fields stayed stale after every publish. Now reads the
  manifest sidecar after both assets upload successfully and calls database.set_meta()
  to write master_version/master_published_at into the live DB before the "done" event.

[2026-06-12] — fix(backend): master release notes summarize status changes by category instead of listing every LB number
Changed: backend/db.py: generate_release_notes now groups lb_status_history rows by
  (old_status, new_status, trigger_event) and emits one summary line per group with a
  count and date range, instead of one line per LB number — a 353-row status change
  (e.g. all "— → private" via flat_file_apply) is now a single "— → private: 353
  _2026-05-21_ flat_file_apply" line rather than 353 individual "LB-NNNNN: ..." lines.

[2026-06-12] — feat(gui): TODO-142 — pipeline batch filing skips per-folder confirmation
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now accepts a
  skipConfirm flag that bypasses the "File into Collection" confirm dialog and applies
  the recommended mount path directly. applyAllFileable and applySelectedFileable pass
  skipConfirm=true so batch filing runs with no per-folder prompts; the single-row
  "File" button still confirms.

[2026-06-12] — fix(gui): Publish Master Update no longer fails with a JSON parse error (BUG-168)
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handlePublishMaster called
  `gr.json()` on the response from POST /api/master/github_release, but that endpoint
  (since TODO-115..120) responds with `text/event-stream` progress events, not JSON —
  `.json()` threw a SyntaxError, surfaced as "Publish failed: ... is not valid JSON",
  and the release was never created. Now reads the SSE stream via `body.getReader()`,
  shows each `progress` event as a toast, and handles `done`/`error` events.

[2026-06-12] — fix(gui): Pipeline "Scan tree…" now scans only 1 level deep (BUG-167)
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: handleScanTree now passes
  shallow: true to POST /api/pipeline/scan-tree (was shallow: false), matching the
  depth-1 behaviour already used by ScreenLBDIR's "Add Root" scan.

[2026-06-12] — feat(tools): TODO-139 Task 3 — OOM audit + validation (1994-02-20 now completes)
Changed: tools/tapematch/tapematch/match.py: removed dead `pairwise_matrix()` — unused
  (no callers anywhere in the repo), held a `streams_mono` dict of every source's full
  mono array in RAM simultaneously. This was the retained-reference pattern the Task 3
  OOM hypothesis described; cli.py's per-pair memmap loop superseded it in the 2026-06-05/06
  OOM fixes (BUG-144 and the Pass-4 OOM fix) but the dead function was left behind.
  tools/tapematch/tapematch/cli.py: added a pre-run estimate log line
  ("est. peak RAM ~X GB (N sources, largest H:MM:SS)") computed from probed durations
  (header reads only) — mono float32 @ analysis_sr is sr*4 bytes/sec; estimate is
  2x the largest source + 300 MB fixed overhead, documented as an order-of-magnitude
  lower bound, not a hard cap.
Fixed: (validation only, no further code change needed) — audited dtype/rate handling
  across ingest.py/audio.py/match.py/align.py/cli.py per CC_TAPEMATCH_FIXES.md Task 3.
  The float64/96kHz-stereo OOM hypothesis was already resolved by prior sessions:
  audio.py's ffmpeg-pipe decode+resample keeps native-rate arrays out of Python entirely
  (only the 16kHz float32 output lands in RAM); ingest.concat_source frees each track
  immediately after copying into a pre-allocated float32 buffer; cli.py Pass 1 writes
  that buffer to a float32 memmap and frees it; resample_ratio uses soxr natively in
  float32. Confirmed empirically (numpy 2.4.6/scipy 1.17.1) that scipy.signal.correlate
  and numpy mean/std preserve float32 — no float64 promotion at any correlation call site.
  1994-02-20 (8 sources, the OOM case study with no prior run dir) now completes:
  5 families, peak RSS 2.6 GB, archived to data/tapematch/runs/20260612_140009_1994-02-20,
  28 pairs logged to observations.db. Re-ran 1993-04-16 (3-source control,
  data/tapematch/runs/20260612_143159_1993-04-16): family assignments, correlation
  matrix, and speed-ppm values are bit-identical to the 2026-06-07 run — float32
  pipeline is deterministic and unchanged.

[2026-06-12] — feat(backend+gui): TODO-110 follow-up — drive stats on Mounts settings screen
Changed: backend/filer.py: disk-usage calculation extracted into new
  get_disk_usage_stats(root_path, online) helper (free/total/used_pct), reused by
  get_mounts_with_stats() and the /api/collection/mounts endpoint.
Changed: backend/app.py: collection_mounts_list() (/api/collection/mounts GET) now
  attaches free/total/used_pct to each mount alongside the existing online flag.
Changed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: CollectionMount gains
  free/total/used_pct; MountCard on the Mounts settings screen now shows "free of
  total" with a colour-coded usage bar (warn at 75%, bad at 90%), matching the
  Collect step's mount picker.
Changed: gui_next locales (en/de/es/fr/it/nl): added mounts.freeOfTotal and
  mounts.usageTooltip.

[2026-06-12] — feat(backend): pipeline filing — hash-verify copies before deleting source
Added: backend/filer.py: hash_tree(root) computes a SHA-256 digest over every file's
  relative path + content under a folder, used to confirm a copy is byte-identical
  to its source. New _HashVerificationError exception.
Changed: backend/filer.py: start_file_job's _run() now hash-verifies the destination
  against the source whenever data is actually copied (file_mode="copy", or a
  cross-device move that falls back to copy+rmtree) — new "verifying" stage before
  comparing hashes, and "removing" stage before deleting the original (move only).
  A hash mismatch deletes the bad copy, leaves the source untouched, and returns
  error_code "hash_mismatch". Same-device moves still use atomic os.rename (no file
  content is rewritten, so no hash check). If the verified copy succeeds but removing
  the original fails, the job still succeeds (warning logged) rather than discarding
  the verified copy.
  gui_next/src/renderer/src/screens/ScreenPipeline.tsx: updated FileProgress stage
  comment to include verifying|removing.
  gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: added
  pipeline.file.progress.verifying/removing labels.
  PROJECT.md: documented new stages and hash_mismatch error code for
  /api/pipeline/file/status.

[2026-06-12] — feat(scraper): TODO-139 Task 2 — observations.db run versioning + latest_pairs view
Added: tools/tapematch/migrate_observations.py: one-shot, idempotent migration. Normalizes
  pair-key ordering (`lb_a < lb_b`, swapping all `*_a`/`*_b` columns on violating rows) and
  creates `idx_pairs_latest` + the `latest_pairs` view (one row per (concert_date, lb_a, lb_b)
  key — the most recent verdict by run_at, ties broken by id). Dry-run by default; `--apply`
  backs up observations.db to `observations.db.bak-<timestamp>` first.
  tools/tapematch/tests/test_migrate_observations.py: unit tests for normalization,
  idempotency, and the latest_pairs view.
Changed: tools/tapematch/tapematch_session.py: OBS_SCHEMA now creates `idx_pairs_latest` and
  `latest_pairs` (idempotent, CREATE IF NOT EXISTS) so fresh/future DBs get them automatically.
  insert_pairs() now normalizes lb_a/lb_b (and all paired fields) to lb_a < lb_b before
  insert, so new rows never violate the ordering migrate_observations.py enforces.
  .gitignore: added `tools/tapematch/observations.db.bak-*`.
Fixed: tools/tapematch/observations.db: migration applied — 1719 of 4318 rows had
  lb_a > lb_b and were normalized (swapped); 0 remain. latest_pairs view verified: 4105
  distinct (concert_date, lb_a, lb_b) keys → 4105 rows. Backed up to
  observations.db.bak-20260612_124147 before applying (gitignored, not committed).
  Found and logged BUG-165 (lb_a==lb_b degenerate rows from a folder-name regex
  cross-reference bug) — out of scope for this task, left for separate triage.

[2026-06-12] — fix(scraper): BUG-164 — TODO-139 Task 1: gen_analysis.py parser fix + re-baseline
Fixed: tools/tapematch/gen_analysis.py: _build_observations no longer treats
  "alternative recording to X/Y ... which all appear to be same recording" snippets
  as a same-source signal for the subject LB — _diff_signal(snip) now suppresses
  _same_signal(snip), falling through to FALSE MERGE / neutral "→" instead of a
  false MISS. See BUG-164 in BUGS_DONE.md.
Added: tools/tapematch/tests/test_gen_analysis.py: unit tests for the ambiguous
  snippet plus clean positive/negative same/diff-source snippets.
  tools/tapematch/BASELINE.md: corrected reference numbers (totals, corr-bucket
  distribution, per-date worst-miss table, lb_says_same caveat, and a documented
  live example of the Task 2 conflicting-verdicts problem on 1996-07-21).
Changed: data/tapematch/runs/*/analysis.md: all 429 regenerated via
  `gen_analysis.py --overwrite --all` (0 errors); analysis.md-level MISS count for
  2001-10-30 dropped 5→0 (confirmed parser noise).

[2026-06-12] — fix(db): BUG-155 — correct "Mnchen" location typo on 5 entries
Fixed: data/losslessbob.db: entries.location for LB-9546, 10083, 12969, 16298,
  16626 corrected from "Mnchen..." (source-site typo, missing "u" — not an
  encoding/ü-drop issue as originally reported) to "Munchen..." matching the
  existing ASCII convention. Cleaned up matching location_geocoded cache rows
  (renamed two, removed two now-duplicate rows); entries_fts updated via the
  existing AFTER UPDATE trigger.
[2026-06-12] — feat(backend+gui): TODO-111 — collection integrity monitor (lbdir-based)
Added: backend/integrity_monitor.py: new scan engine. scan_collection() iterates
  my_collection, locates each folder's lbdir manifest (folder-local or attached),
  and reuses checksum_utils.verify_folder_lbdir() to classify results — ffp_status
  'fail' = content_issue (bitrot/corruption), md5_status 'fail' with ffp pass/na =
  tag_issue (metadata-only edit), overall 'missing' = missing_files. Files with
  overall == 'extra' are ignored. start_scan_async/get_scan_status/cancel_scan
  provide a background-thread job with progress, modeled on filer.py's _FILE_JOB.
Added: backend/db.py: new tables collection_integrity_status (latest per-LB
  result) and collection_integrity_scans (scan history); idempotent
  integrity_events.mount_id column migration; new functions
  upsert_collection_integrity_status, get_collection_integrity_status,
  get_mount_integrity_summary, record_integrity_scan_start, finish_integrity_scan,
  get_integrity_scan_history; log_integrity_event() gains mount_id param.
Added: backend/scheduler.py: _integrity_scan_worker + start/stop_integrity_scan_scheduler
  — hourly check against meta key integrity_scan_interval_hours (default "0" =
  disabled), triggers a whole-collection scan via integrity_monitor.start_scan_async().
Changed: backend/app.py: new routes POST /api/collection/integrity/scan (+/cancel),
  GET /api/collection/integrity/scan/status, /scan/history, /summary, /status;
  /api/db/settings GET now includes integrity_scan_interval_hours;
  start_integrity_scan_scheduler() wired alongside start_collection_watcher().
Changed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: MountCard shows an
  integrity severity badge (corrupt/missing/tag-only/verified) and a per-mount
  "Scan integrity" button. New "4 · Integrity Monitor" section: scan now (whole
  collection or per-mount) with a live progress bar and cancel button, auto-scan
  interval dropdown (off/daily/weekly/monthly), findings table for non-passing
  folders, and a recent-changes list (content/tags/missing/restored) with
  per-row and bulk acknowledge.

[2026-06-12] — fix(backend): BUG-163 — undefined `_time` in admin restart handler
Fixed: backend/app.py: `_do_restart()` called `_time.sleep(0.3)` but only `time`
  is imported; renamed to `time.sleep(0.3)`. Caught by ruff (F821) on commit.

[2026-06-12] — feat(gui): move Mounts & Routes out of Setup into its own screen
Added: gui_next/src/renderer/src/screens/ScreenMounts.tsx: new screen hosting the
  storage-mounts/year-routing/filing-mode card (extracted from ScreenSetup).
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: removed the
  CollectionRoutingCard and its helper components (now in ScreenMounts.tsx);
  dropped now-unused Input/IconButton imports.
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added 'mounts' nav
  item (Settings group, directly below Setup); added 'mounts' to NavId.
Changed: gui_next/src/renderer/src/App.tsx: added /mounts route -> ScreenMounts.
Added: gui_next/src/renderer/src/components/Icon.tsx: new "mounts" (hard-drive)
  icon for the nav entry.
Added: gui_next locales (en/de/es/fr/it/nl): appShell.nav.mounts and new
  mounts.title/mounts.subtitle keys.

[2026-06-12] — feat(backend+gui): TODO-110 — drive stats on pipeline mount cards
Changed: backend/filer.py: get_mounts_with_stats() now also returns total
  capacity (total) and used percentage (used_pct), via shutil.disk_usage(),
  alongside the existing free space and span fields.
Changed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: Mount
  interface gains total/used_pct; MountPicker mount cards now show "free of
  total" and a colour-coded usage bar (warn at 75%, bad at 90%), updating
  reactively as the pipeline re-resolves the Collect step.
Changed: gui_next locales (en/de/es/fr/it/nl): replaced collect.freeAmount with
  collect.freeOfTotal and added total/used % to collect.mountTooltip.

[2026-06-12] — feat(backend+gui): TODO-112 — backend uptime clock on About screen
Added: backend/app.py: new GET /api/system/uptime endpoint returning
  uptime_seconds since the Flask process started.
Changed: backend/app.py: /api/admin/status now shares the same process-start
  timestamp (_process_start_time) instead of its own duplicate.
Changed: gui_next/src/renderer/src/components/AboutDialog.tsx: About tab now
  shows a live "uptime" field (HH:MM:SS) fetched from /api/system/uptime and
  ticked locally, to help confirm whether a backend restart actually happened.

[2026-06-12] — fix(backend+gui): TODO-113 — consolidate app version numbering
Changed: VERSION: bumped 1.3.0 -> 1.4.0 to match gui_next/package.json (now the
  source of truth, mirrored here for the Python backend/CLI).
Changed: backend/paths.py: removed stale duplicate APP_VERSION constant (1.2.0).
Changed: backend/forum_poster.py: forum post footer now uses backend.version.VERSION
  instead of the removed APP_VERSION.
Changed: cli.py: interactive shell banner now uses backend.version.VERSION instead
  of a separate hardcoded _VERSION ("1.0.3").
Changed: gui_next/electron.vite.config.ts: renderer build now defines __APP_VERSION__
  from gui_next/package.json's version field; declared in env.d.ts.
Changed: gui_next/src/renderer/src/components/SplashOverlay.tsx,
  components/AboutDialog.tsx: replaced hardcoded "1.2.0" version strings with
  __APP_VERSION__.
Changed: gui_next/src/renderer/src/components/AppShell.tsx + locales/*.json:
  sidebar tagline "version" string now interpolates {{version}} = __APP_VERSION__
  instead of a stale hardcoded "v1.0.6".

[2026-06-12] — feat(gui): TODO-138 — Pipeline "Auto-rename" toggle
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: new "Auto-rename"
  toggle in the pipeline header (off by default, alongside "Auto-run on drop").
  When on, any folder where verify/lookup/lbdir all pass and rename has a single
  confident proposed name (bucket "ready") is auto-renamed via the existing
  applyRename() path — marking step 4 (rename) green and advancing the row to
  the collect stage — with no "Apply rename" click needed. When off, behavior
  is unchanged: proposed renames sit in the "ready" bucket for manual Apply.
Added: gui_next/src/renderer/src/locales/en.json: pipeline.autoRename /
  pipeline.autoRenameHint strings. Note: DeepL key in .claude/settings.local.json
  is currently disabled (AuthorizationException), so de/fr/es/it/nl translations
  for these two keys (and the pre-existing ~27/N pipeline-section gap in those
  locales) were not refreshed — i18next falls back to English for now.

[2026-06-12] — feat(backend+gui): TODO-137 — pipeline step order: LBDIR now runs before Rename
Changed: backend/app.py: _pipeline_process_folder reorders steps to
  verify -> lookup -> lbdir -> rename -> file (collect); LBDIR retrieve+verify
  is now step 3 and Rename proposal is step 4. Severity status list reordered
  to match. pipeline_run's default steps list/docstring updated.
Changed: backend/app.py: /api/lbdir/check and /api/lbdir/reconcile accept an
  optional lb_number_hint body param, falling back to my_collection ->
  folder-name regex -> hint, since LBDIR now runs before the folder is
  renamed/filed and won't yet have "LB-NNNNN" in its name.
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx:
  DEFAULT_STAGES reordered/renumbered to verify(1)/lookup(2)/lbdir(3)/rename(4)/
  collect(5).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: all step-key
  iteration orders (toFolderRow, firstActiveStage, deriveFolderStatus,
  mergeServerRow, autorun/auto-complete) reordered to verify/lookup/lbdir/
  rename/file; the auto-complete "stale" check now resumes on
  lbdir.status === 'mute' (was rename) and re-runs ['lookup','lbdir','rename',
  'file']. LbdirStageContent passes lb_number_hint (from the Lookup step) to
  /api/lbdir/check and /api/lbdir/reconcile. Updated stage copy: "Runs after
  lookup" (was "after rename"), Lookup's "flows into LBDIR" (was "Rename"),
  and Rename's success banner now says "Ready to collect next" (was "LBDIR
  will reconcile next").

[2026-06-12] — chore(release): v1.4.0 — pipeline v2 (storage mounts, lookup, lbdir, rename, collect)
Changed: gui_next/package.json: version bumped 1.3.0 -> 1.4.0.
Changed: merged feat/pipeline-v2-storage-mounts into main — collection mount management,
  Quick Lookup screen, pipeline lookup/rename/lbdir/collect stage panels, background
  copy/move with progress, and associated bugfixes (see entries below).

[2026-06-12] — fix(backend+gui): BUG-162 — pipeline Lookup no longer Passes on a partial checksum match
Fixed: backend/app.py: _pipeline_process_folder's lookup step now requires
  summary.matched == summary.given (e.g. 42/42) for a resolved LB# to report
  status "ok"/Pass. A single-LB match with fewer matches than given checksums
  (e.g. 21/42 — ffp matches but md5 doesn't) now reports status "warn" /
  label "Incomplete match", with lb_number still set so Rename/LBDIR/Collect
  proceed, plus a row["errors"] entry noting the X/Y ratio.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LookupStageContent
  gained a warn branch for "Incomplete match" (lb_number set, not a Conflict)
  that explains the mismatch and renders <LookupDetail> (summary + per-checksum
  table) so the unmatched (NOT FOUND) checksum rows are visible — previously the
  "ok" branch showed only a green banner with a small "21/42 matched" caption and
  no detail table at all.
Changed: BUGS.md, BUGS_DONE.md: added BUG-162 (Fixed).

[2026-06-11] — fix(gui): BUG-154 — guard against stray tsc-emitted .js shadowing .tsx sources
Fixed: gui_next/.gitignore: added src/{renderer,main,preload}/**/*.js entries. The stale
  build artifacts from BUG-154 were already removed and tsconfig.web.json/tsconfig.node.json
  already set noEmit:true; this closes the remaining gap so a future non --noEmit tsc run
  can't silently reintroduce shadow .js files.
Changed: BUGS.md, BUGS_DONE.md: moved BUG-154 to the archive as Fixed.

[2026-06-11] — chore(docs): move 25 fixed bugs (BUG-122–153) from BUGS.md to BUGS_DONE.md
Changed: BUGS.md, BUGS_DONE.md: moved all "Fixed" entries to the archive, keeping only
  Open bugs (BUG-106, 118, 120, 146, 154, 155) in BUGS.md. Also removed BUG-133/134 from
  BUGS.md — they were duplicates already present in BUGS_DONE.md.

[2026-06-11] — fix(backend): pipeline — Collect "Confirmed" date now stamps on LBDIR pass
Fixed: backend/app.py: BUG-161 — the pipeline's LBDIR step (step 4) computed a "pass"
  result but never called database.set_lbdir_verified(), so the Collect stage's
  "Confirmed" row (my_collection.lbdir_verified_at) never updated for an owned folder
  re-checked in place. Now calls set_lbdir_verified() on pass, same as /api/lbdir/verify;
  no-op for not-yet-filed folders (no matching my_collection.disk_path row).

[2026-06-11] — feat(backend+gui): pipeline — Collect tag preview shows real status/confirmed data
Changed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: TagTable's
  "Status" row now shows the real lb_master.lb_status (Public/Private/Missing/Nonexistent)
  plus owned/not-in-collection, and "Confirmed" shows the real my_collection.lbdir_verified_at
  date (or "Not yet confirmed") instead of hardcoded "Public · Owned" / "Today".
Removed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: dropped the
  "Fingerprint: Queued · AcoustID" row — a stale design-mockup placeholder never wired to a
  real queue (unrelated to the completed audio-fingerprint-identify feature, TODO-106).
Changed: backend/app.py: `/api/pipeline/status` file step now returns lb_status, owned, and
  lbdir_verified_at (queried from lb_master / my_collection) for the Collect stage.
Changed: gui_next/src/renderer/src/locales/*.json: removed rowFingerprint/valueFingerprint/
  valueStatus/valueConfirmed; added statusPublic/statusPrivate/statusMissing/
  statusNonexistent/statusUnknown/ownedYes/ownedNo/notConfirmed (all 6 languages).

[2026-06-11] — feat(backend+gui): pipeline — progress bar for Collect step copy/move
Added: backend/filer.py: replaced synchronous `file_folder()` with `start_file_job()` +
  `get_file_job_status()` — a background-thread job (shared `_FILE_JOB` dict + lock) that
  scans the source tree for file count/bytes, then moves (os.rename, falling back to
  copy+rmtree across filesystems) or copies (shutil.copytree with a progress-tracking
  copy_function) the folder, updating files_done/bytes_done as it goes.
Changed: backend/app.py: `/api/pipeline/file` replaced by `POST /api/pipeline/file/start`
  (returns immediately) and `GET /api/pipeline/file/status` (poll for progress + result).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile() now starts the
  job and polls status every 400ms, storing progress on the row (`fileProgress`). Added
  FileProgressBar component — shown in the Collect detail panel's "File into collection"
  banner and in the table row's action cell while filing is in progress, so large
  copy/move operations no longer look like nothing is happening.
Changed: gui_next/src/renderer/src/locales/*.json: added pipeline.file.progress.{scanning,
  copying,moving} strings (all 6 languages).
Changed: PROJECT.md: updated Collection Routing & Pipeline Filing API table.

[2026-06-11] — fix(backend): db — BUG-160 rename_history.renamed_at now stored in local time
Fixed: backend/db.py: add_rename_history() now writes an explicit local-time timestamp instead
  of relying on SQLite's CURRENT_TIMESTAMP default (which is UTC). init_db() runs a one-time
  migration (meta key rename_history_localtime_v1) converting existing renamed_at values from
  UTC to local time via datetime(renamed_at, 'localtime').
Changed: PROJECT.md: rename_history.renamed_at column note updated.

[2026-06-11] — chore(gui): pipeline — drop inaccurate "reversible for 30 days" claim
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: all "Logged to rename_history"
  notes (Rename and Collect tabs) no longer claim a 30-day reversal window, since
  rename_history has no time-based retention/auto-purge (purge is manual and deletes all
  rows).

[2026-06-11] — fix(backend): lbdir — BUG-159 whitelist extras/ and rename_log.txt for green status
Fixed: backend/checksum_utils.py: verify_folder_lbdir() no longer counts files under `extras/`
  (created by /api/lbdir/move_extras) or `rename_log.txt` (written by write_rename_log) as
  "extra". If those are the only unclaimed files, status now resolves to 'pass' so the lbdir
  step (pipeline step 4) turns green once a folder has been reconciled. Added
  `_is_reconciled_extra()` helper plus `RENAME_LOG_NAME`/`EXTRAS_DIRNAME` constants.

[2026-06-11] — fix(backend+gui): lbdir — BUG-158 detect extra files on disk during lbdir check
Fixed: backend/checksum_utils.py: verify_folder_lbdir() now scans the folder recursively for
  files not claimed by any lbdir md5/ffp/shntool entry (excluding the manifest itself), adds
  them to `files` with overall='extra', and reports a real `extra` count instead of a hardcoded
  0. New 'extra_files' status is returned when checksums otherwise pass but stray files exist,
  so the folder no longer shows green/Pass while hiding extras.
Changed: backend/app.py: pipeline lbdir step now maps 'extra_files' to a "warn"/"Extra N" label
  and includes `extra` in the check detail.
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: LbdirState gains 'extra_files'; CheckResult
  gains `extra: number`.
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx,
  gui_next/src/renderer/src/screens/ScreenPipeline.tsx: STATE_LABEL entries for 'extra_files'
  (warn tone). Since it's not 'pass', the existing canReconcile gate now triggers the
  reconcile/move-to-extras flow for extra-only folders.
Fixed: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: LbdirFileTable rows with
  overall='extra' now render as a "warn" Extra pill instead of a red "Fail".

[2026-06-11] — fix(gui): pipeline — BUG-157 My Collection screen now refreshes after filing a folder
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now calls
  queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] }) on a successful
  /api/pipeline/file result, so a folder filed from the pipeline (e.g. LB-16298) appears
  immediately in My Collection instead of requiring an app restart to refresh the stale
  staleTime: Infinity react-query cache.

[2026-06-11] — fix(gui): pipeline — BUG-156 folder no longer shows "In collection" before it's actually filed
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: serverRowToPipeline reclassifies bucket
  'done' as 'shelf' when the file (Collect) step status is 'warn' (ready to file, not yet filed) —
  fixes status column showing "In collection · Filed to DYLAN1" and the header "1 in collection"
  pill while the detail panel's Collect stage still shows "Action — File into collection". Folder
  now correctly shows "Ready to file" and counts toward the shelf/"File all N into collection"
  group until the Collect step actually runs.

[2026-06-10] — docs(gui): diagnosed BUG-154 — stale tsc-emitted .js files shadow .tsx sources, app ran pre-BUG-149 pipeline code
Added: BUGS.md: BUG-154 (Open) — 45 untracked compiled .js files under gui_next/src/renderer/src (tsc emit, 2026-06-10 17:09) shadow the .tsx sources; Vite resolves .js before .tsx so the running app lacked the BUG-149/151/152/153 fixes (rename/lbdir/file mute, statuses cleared on navigation). Backend verified correct via direct /api/pipeline/run + /api/folder/rename on the Munich example folder.
Added: BUGS.md: BUG-155 (Open) — entries.location for LB-16298 is "Mnchen, Germany" (ü dropped, cp1252 decode suspect); pipeline proposes misspelled rename.
Added: tools/debug_pipeline_rename.json: browser_driver session reproducing the pipeline rename stall (add Munich folder → wait for LB# → open Rename stage).

[2026-06-10] — fix(gui): pipeline — step results persist across tab navigation; partial-step runs no longer wipe steps
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added module-level _pipelineCache (Map keyed by folder path); updateRow writes to cache on every result, queue sync restores from cache on component remount — results survive tab navigation within the session
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: queue sync effect now schedules auto-run for unprocessed (all-mute) rows, so folders already in the queue on page load/tab-return run automatically when auto-run is on
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: runSteps and refreshDetailRow now preserve existing step results for stages not included in the requested steps list — "Check rename" no longer resets Verify/Lookup to mute
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: auto-complete effect detects rows where lookup=ok but rename=mute and automatically runs remaining steps
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: cache cleared on queue Clear and on individual row removal; folder path updated in cache on rename apply

[2026-06-10] — fix(gui): pipeline — per-stage re-run buttons now include lookup so lb_number resolves
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Check rename", "Re-check" (rename/lbdir/file), "Check route now" buttons were sending only their own stage to the backend; since the backend rebuilds everything from scratch, lb_number was always None → rename/lbdir/file stayed mute. All 7 per-stage re-run calls now include 'lookup' in the steps list.

[2026-06-10] — fix(backend+gui): pipeline — false "In collection", mute rename, lbdir retrieve with no LB in folder name
Fixed: backend/app.py: severity logic now returns "attn" (not "done") when lookup resolved an LB# but rename or lbdir steps are still mute (not yet run) — prevents folder from being classified as "In collection" too early
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: auto-run now fires all 5 steps (verify+lookup+rename+lbdir+file) instead of only verify+lookup — rename and lbdir were always mute for auto-dropped folders
Fixed: backend/app.py: lbdir_retrieve now accepts an optional lb_number_hint in the request body; falls back to it when neither my_collection nor folder name contains an LB# — allows "Retrieve sidecar now" to work for un-renamed folders whose LB was resolved by lookup
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: handleRetrieve passes lb_number_hint from row.steps.lookup.lb_number when calling /api/lbdir/retrieve

[2026-06-10] — feat(gui+backend): pipeline v2 phase 6 — polish: running progress, shntool state, collect pass rows, tooltips
Changed: backend/app.py: pipeline verify step now handles shntool_missing status from verify_folder (was falling through to bad/Mismatch); returns {status: "warn", label: "No shntool", shntool_missing: true}
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: VerifyStageContent — running-state banner when step is mute+row.running ("Hashing files…"); shntool-missing banner when step.shntool_missing; shntool_missing added to StepResult interface
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: CollectStageContent pass state — LB#/Mount detail rows added below "Added to collection" banner
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: title= tooltips on all re-run/re-check/re-verify buttons ("Re-run this stage"), Copy diff ("Copy to clipboard"), and DetailPanel Open button ("Reveal folder in Finder")

[2026-06-10] — feat(gui+backend): pipeline v2 cleanup phase 5 — Collect mount picker + tag table
Added: backend/filer.py: get_mounts_with_stats() returns collection_mounts with span (decade
range from collection_routes), free (human-readable via shutil.disk_usage), and online
(_path_reachable); new helpers _human_bytes() and _year_span_label()
Changed: backend/filer.py: resolve_destination_for_lb() and file_folder() take an optional
mount_id_override — when set and different from the year-routed mount, files under that
mount's root while keeping the routed sub_path (year subfolder)
Changed: backend/app.py: _pipeline_process_folder() Step 5 "file" result now includes mounts,
recommended_mount, routed_year, and collection_count when the folder is ready to file;
/api/pipeline/file and /api/pipeline/file/preview accept an optional mount_id per folder item
and pass it through as mount_id_override
Added: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: new shared component —
MountPicker (storage-mount picker grid with span/free/"suggested" pill, routed-by-year pill,
"Reset to suggested") and TagTable ("Tag in the collection" preview rows with live item
counter), composed by CollectDetail
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: StepResult/normalizeFileStep
gain mounts/recommended_mount/routed_year/collection_count; new CollectReadyDetail component
renders the route card + <CollectDetail> and live-previews the destination via
/api/pipeline/file/preview when the user picks a different mount; onFile/applyFile now accept
an optional mountId, forwarded to /api/pipeline/file as mount_id when it differs from the
recommended mount
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: pipeline.collect.* strings
(storageMount, routedByYear, resetToSuggested, suggested, mountOffline, mountTooltip,
freeAmount, tagInCollection, itemsCounter, row*/value* tag-table labels) — de/fr/es/it/nl
translated by hand this session (DeepL API key returned AuthorizationException: key disabled)
Fixed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: MountPicker now
disables radio selection on offline mounts (greyed out, "Offline" label) — previously a user
could select an unreachable mount and the live preview would silently fail, leaving the
picker and route card out of sync
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: CollectReadyDetail's "File into
collection" button is disabled while a mount-override preview is pending/unresolved, and now
passes the previewed dest/mount_label through onFile/applyFile so the confirm dialog shows
the destination that will actually be used (previously showed the recommended mount's
dest/label even when a different mount was selected)

[2026-06-10] — feat(gui): pipeline v2 cleanup phase 4 — harvest LbdirDetail into pipeline LBDIR panel
Added: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: new shared component —
CheckDot, LbdirFileTable (resizable Filename/MD5/Disk/Overall/Length/Fmt/Ratio columns), and
ReconcilePanel (rename proposals, extras-to-/extras/, and site/files recovery section), composed
by LbdirDetail with a compact prop, harvested from ScreenLBDIR.tsx
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: removed inline CheckDot,
ReconcilePanel, file table, and column-resize state; now renders the shared <LbdirDetail>
non-compact; no behavior change
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LbdirStageContent's truncated
12-row file list and reconcile block (which lacked the site/files recovery section) replaced
with <LbdirDetail compact> — the pipeline LBDIR panel now shows the full file table and full
reconcile UI matching the standalone LBDIR screen

[2026-06-10] — chore(gui+docs): data-testid hooks for nav/stage tabs + GUI verification gotchas
Added: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageStepper tab buttons get
data-testid="stage-tab-{verify|lookup|rename|lbdir|file}"
Added: gui_next/src/renderer/src/components/AppShell.tsx: main sidebar nav buttons get
data-testid="nav-{id}"; Advanced Tools sub-nav (Verify/Lookup/Rename/LBDIR) get
data-testid="nav-adv-{id}"
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: Quick Lookup sidebar button gets
data-testid="sidebar-quick-lookup"
Changed: .claude/CLAUDE.md: new "Verification gotchas" subsection under GUI Verification —
prefer curl for data-shape checks, use data-testid selectors instead of :has-text() (which
case-insensitive substring-matched "Lookup" tab vs "Quick lookup" sidebar button this session),
Unicode ellipsis in button labels, wait-for over fixed waits, kill stray dev-server processes,
absolute paths for browser_driver.mjs
Note: prompted by a session retrospective — GUI screenshot verification looped for ~30min on
selector mismatches; these hooks + doc notes target that directly

[2026-06-10] — feat(gui+backend): pipeline v2 cleanup phase 3 — harvest LookupDetail into pipeline lookup panel
Added: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: new shared component —
LookupSummaryTable (per-LB summary with category pill, alias-canonical pill, optional "Pin {lb} &
continue" column), LookupChecksumTable (grouped per-checksum detail with xref column), and
LookupNotFoundHint, harvested from ScreenLookup.tsx; also exports STATE_TONE/apiStatusToState/
categoryPill/LookupState for reuse
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: replaced inline summary/checksum
tables and status-tone helpers with the shared LookupDetail components; no behavior change
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LookupStageContent now renders
LookupDetail scoped to the active folder — matched state shows category pill + {matched}/{given}
stat; ambiguous (Conflict) state shows "Which show is this?" + per-LB "Pin {lb} & continue" wired
to PUT /api/folder_link (writes folder_lb_link, then re-runs lookup); not-found state shows the
shared checksum table + not-found hint; StepResult gains summary/detail fields
Changed: backend/app.py: _pipeline_process_folder lookup step now calls database.lookup_checksums
to get (summary, detail), annotates detail with is_alias_lb/canonical_lb via
database.get_lb_aliases(), includes summary/detail in the lookup result for all branches, and
honors an existing folder_lb_link pin (wins over raw checksum match set) to resolve ambiguity
Note: design doc 14 §2.2/§3 "Mark as new entry…" button intentionally not implemented — no
backend support exists yet for creating new lb_master entries (would be a no-op stub)

[2026-06-10] — chore(gui): replace Electron GUI driver with headless-Chromium browser driver
Added: tools/browser_driver.mjs: Playwright Chromium driver for GUI verification — same
session JSON / CLI shape as the old gui_driver.mjs (screenshot, navigate, click, fill,
eval, session); spawns `npm run dev` (or `npm run preview` with --preview), stubs
window.api (Electron preload bridge) via addInitScript, no Electron/Xvfb/display needed
Removed: gui_next/gui_driver.mjs: Electron+Playwright+Xvfb driver — consistently failed
in this sandbox (Electron CDP target never connects / GTK aborts under headless ozone);
replaced entirely by tools/browser_driver.mjs
Changed: .claude/CLAUDE.md: GUI verification section now documents tools/browser_driver.mjs
and the requirement to start the Flask backend first so the splash clears quickly
Changed: .claude/settings.json: pre-approved Bash rule updated from gui_driver.mjs to
tools/browser_driver.mjs
Changed: package.json/package-lock.json (root): added playwright devDependency (Chromium
browser binary cached via `npx playwright install chromium`)

[2026-06-09] — fix(gui): pipeline screen — remove filter chips, fix column alignment, wire auto-run
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: (1) removed bucket filter Chip bar from content area; (2) added missing 3px edge-bar <th> spacer to thead so headers align with data rows; (3) wired autorun toggle — addFolders now queues new folder IDs in autorunPendingRef and a useEffect drains the queue via runSteps(['verify','lookup']) once rows state settles

[2026-06-10] — feat(gui): pipeline progress banner — bucket pills, auto-run toggle, correct CTAs
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: replaced old banner right-side (bulk menu + conditional CTAs) with: (1) interactive bucket filter pills — one per non-zero bucket (needs/ready/running/shelf/done), clicking toggles table filter, correct labels/tones per spec; (2) auto-run toggle — sliding pill, default on; (3) "Apply all N ready" — always visible, disabled when 0; (4) "File all N into collection" — only shown when shelf > 0; removed dead bulkMenuRef/bulkMenuOpen state and click-away handler; title now "Pipeline · N folders" with fixed subtitle
Changed: gui_next/src/renderer/src/locales/en.json: added titleFolders, autoRun, autoRunHint, applyAllReady, fileAllCollection keys; updated filter.done to "In collection"

[2026-06-09] — fix(gui): pipeline v2 rename panel — full content (Issue 9); applyRename accepts custom name
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: RenameStageContent replaced with full panel — StageHead (state badge, title, LB# pill, Edit name… button), wrong-LB amber banner (auto-detected from folder name vs lookup LB#), diff box (red/green rows; green becomes input in edit mode, with LB# highlighted/struck-through), dry-run info banner with Copy diff, success banner after apply; onRename threaded as (customName?) so edited name reaches applyRename; Issue 8 already resolved (step key 'file' correct throughout)

[2026-06-09] — feat(gui): guaranteed fresh backend on every `npm run dev` launch
Changed: gui_next/src/main/index.ts: added killPortProcess() — after killStalePid(), scans port 5174 with lsof (Linux/Mac) or netstat (Windows) and kills any occupying process before spawning the backend; ensures stale backends started outside Electron are always evicted

[2026-06-09] — fix(gui): pipeline v2 UX corrections — detail layout, nav, queue rail, table columns
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: detail panel now replaces main content area instead of opening as a narrow right drawer (Issue 1); removed Run On Selected panel + singular Add Folder + shallowScan checkbox from queue rail footer; added Scan/Clear two-column grid, Quick Lookup button-link, and drag hint box (Issue 3); added Status column (deriveFolderStatus + StatusTag + reason) between Stages and LB# in batch table (Issue 6); colgroup updated to 7 columns; spacer/grouprow colSpan updated accordingly
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: Verify/Lookup/Rename/LBDIR moved under collapsible "Advanced tools" disclosure (starts closed); removed Quick Lookup from sidebar nav (Issue 4)
Fixed: gui_next/src/renderer/src/locales/en.json + de/es/fr/it/nl: filter.needs → "Needs you"; filter.ready → "Ready to apply"; filter.shelf → "Ready to file"; runHint updated to remove "Run all 5 steps" reference; added advancedTools nav key (Issues 5, 7)

[2026-06-09] — docs: pipeline v2 phase 9 — documentation and verification
Changed: PROJECT.md: added collection_mounts + collection_routes schema tables; added "Collection Routing & Pipeline Filing" API section (10 routes); updated ScreenPipeline to 5-step; added ScreenQuickLookup entry; added Change Log row
Changed: instructions/pipeline_new/CHECKLIST.md: phases 9 items ticked off

[2026-06-09] — feat(gui): pipeline v2 phase 8 — Quick Lookup screen
Added: gui_next/src/renderer/src/screens/ScreenQuickLookup.tsx: new screen — paste input, clipboard button, drag-and-drop .md5/.ffp zone, results table (Checksum | Filename | LB# | Status)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added quicklookup nav entry under Ingest group
Changed: gui_next/src/renderer/src/App.tsx: added /quicklookup route and import
Changed: gui_next/src/renderer/src/locales/*.json: added appShell.nav.quicklookup and quickLookup namespace to all 6 locales

[2026-06-09] — feat(gui+backend): pipeline v2 phase 7 — stage detail panels
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: replaced GenericStageContent stub with four dedicated stage panels — VerifyStageContent (stats grid, no-checksums generate flow, re-verify), LookupStageContent (LB# matched card, conflict/not-found states, re-run), RenameStageContent (current/proposed diff view, apply rename button), CollectStageContent (route box staging→destination, error-code cards for no_date/no_route/mount_offline/dest_exists/db_error, filed success card); DetailPanel gains onRename prop wired to applyRename callback
Changed: backend/app.py: _pipeline_process_folder verify step now includes total/pass/missing/mismatch/extra/no_checksums counts in the step result dict

[2026-06-09] — feat(gui+backend): pipeline v2 phase 6 — Collect step wired into pipeline screen
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added 5th step column "Collect" with StepPill; "File" action button per-row (opens confirm dialog, calls /api/pipeline/file); "File selected" bulk button in selection bar; "File all ready" button in header; "Collect" individual run button in queue rail; "Run All" now runs all 5 steps; ConfirmDialog for file action shows dest path and mount; severity 'blocked' escalates to attn; right-click context menu wired via onContextMenu on TR rows; filter chip and group row labels now use t() with new pipeline.filter.{needs,ready,running,shelf} i18n keys; "File into Collection" action button in detail panel file stage
Changed: backend/app.py: _pipeline_process_folder severity — file_status=='blocked' now escalates to 'attn'; comment explains why 'ready' does not
Added: gui_next/src/renderer/src/components/pipeline/ConfirmDialog.tsx: useConfirm integration in ScreenPipeline
Changed: gui_next/src/renderer/src/locales/en.json + de/fr/es/it/nl: new keys — pipeline.table.collect, pipeline.file.*, pipeline.queue.collect, pipeline.fileAllReady, pipeline.selection.fileSelected; queue.runAll and runHint updated to "5 steps"; ingestDesc updated to include collect step; pipeline.filter.{needs,ready,running,shelf} added for bucket filter chips

[2026-06-09] — feat(backend+gui): Pipeline v2 — Step 5 File into Collection + Mounts & Routes
Added: backend/filer.py: year extraction, route resolution, timeout-guarded mount reachability check, move/copy filing, my_collection registration
Added: backend/db.py: collection_mounts, collection_routes tables + schema migration guards + meta key pipeline_file_mode; DB helper functions for all CRUD
Added: backend/app.py: 10 new API routes (/api/collection/mounts, /api/collection/routes/*, /api/collection/routes/preview/*, /api/pipeline/file, /api/pipeline/file/preview); pipeline_file_mode in db_settings; step 5 in _pipeline_process_folder
Added: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StateGlyph, StatusTag, StageNode, StageTracker, StageStepper, QueueRow
Added: gui_next/src/renderer/src/components/pipeline/ConfirmDialog.tsx: useConfirm hook, ConfirmDialog, ConfirmDialogProvider
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: CollectionRoutingCard (Mounts, Year Routes, Coverage bar, Preview tester, Filing Mode)

[2026-06-09] — chore(backend): set up ruff linter + pre-commit hook
Added: pyproject.toml: ruff config (E/W/F/I/UP/B/G/LOG, line-length 100, py311, excludes gui/ and tools/)
Added: .pre-commit-config.yaml: local pre-commit hook running ruff check --fix on staged Python files
Added: requirements-dev.txt: pinned ruff==0.15.16 and pre-commit==4.6.0
Changed: backend/: 102 auto-fixes applied (import ordering, deprecated typing imports, OSError aliases, unused imports, f-string cleanup, missing newlines)
Changed: BEST_PRACTICES.md: added §13 Tooling Setup (install steps, ruff rules table, config file reference)

[2026-06-09] — docs: expand BEST_PRACTICES.md with external standards and references
Added: BEST_PRACTICES.md: structured logging with extra=, TypedDict for dict-heavy return types, exception chaining (PEP 3151), pytest parametrize guidance, external references table (PEP 8/257/484/585/604/655/673/3151, Google style guide, Logging HOWTO/Cookbook, pytest docs, Effective Python)

[2026-06-09] — docs: add BEST_PRACTICES.md — Python conventions reference for this project
Added: BEST_PRACTICES.md: covers logging, type hints, docstrings, DB access patterns, error handling, threading, Flask routes, testing, and a pre-PR checklist

[2026-06-09] — perf(gui): Map — Canvas renderer + compositor layer promotion reduce pan/zoom lag
Changed: gui/resources/map.html: pass preferCanvas:true to L.map() so Leaflet uses Canvas instead of SVG for marker rendering; SVG DOM is O(n) with marker count, Canvas is not
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: added transform:translateZ(0) to iframe style to promote it to its own GPU compositor layer, reducing repaint cost during interaction

[2026-06-09] — fix(gui): Map tiles offline — add error banner overlay when tiles fail to load
Fixed: gui/resources/map.html: captured tileLayer reference; added tileerror listener that shows a "Map tiles couldn't load — check your internet connection" banner (z-index 1000, pointer-events:none) anchored to the bottom of the map container; added tileload listener that clears it when tiles subsequently succeed (BUG-134)

[2026-06-09] — fix(gui): DB Editor pagination and action bar hidden until a table is selected
Fixed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: wrapped pagination row and action row in {currentTable && ...} so "Page 1/1 (0 rows total)" and all buttons (Commit, Discard, Delete Selected, Export CSV, SQL Query) no longer appear on initial load before any table is chosen (BUG-133)

[2026-06-09] — fix(gui): Attachments empty-state message no longer misleads after auto-load
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: added hasLoaded flag set in loadTree's finally block; empty-state now shows "Loading…" until first load completes, "No attachments cached yet" when the cache is genuinely empty, and "No matches" when a filter narrows an existing list to zero (BUG-132)

[2026-06-07] — fix(tapematch): year_run now skips dates with existing run folders in RUNS_DIR
Changed: tools/tapematch/tapematch_session.py: year_run() augments `done` set by scanning RUNS_DIR for folders named YYYYMMDD_HHMMSS_{date_iso}; catches dates whose DB insert failed or whose runs were archived without a successful observations.db entry

[2026-06-06] — fix(tapematch): OOM kill in Pass 4 + add per-run debug log
Fixed: tools/tapematch/tapematch/audio.py: resample_ratio now uses soxr instead of scipy.signal.resample_poly; soxr operates natively in float32 so the ~1.84 GB float64 intermediate (922 MB input copy + 922 MB output) is eliminated; peak per speed-correction call drops from ~2.3 GB to ~461 MB; falls back to resample_poly if soxr is unavailable; added sr parameter (default 16000)
Changed: tools/tapematch/tapematch/cli.py: pass sr to resample_ratio call in Pass 4; added _rss_mb()/_DebugLog helpers; added --debug-log PATH argument; log elapsed time + RSS at every pass boundary (INGEST per source, PASS1_DONE, ANCHORS, LAG_CURVES_START, MATRIX_START/DONE, each RESAMPLE event with ratio+ppm, FINGERPRINT_START, SECONDARY_START, LINEAGE_START, DONE)
Changed: tools/tapematch/tapematch_session.py: run_tapematch() replaced subprocess.run(capture_output=True) with Popen + line-by-line stream so tapematch progress and any crash output appear immediately in the terminal; removed redundant print(log_text) after the call; passes --debug-log last_debug.log to cli; archive_run() copies last_debug.log to debug.log in each run archive
Added: requirements.txt: soxr==1.1.0

[2026-06-05] — fix(tools): batch_verify --skip-done now auto-reprocesses api_error/retrieve_error
Changed: tools/batch_verify.py: --skip-done treats api_error and retrieve_error as transient (never skips them); updated help text and usage examples to remove api_error from --reprocess examples

[2026-06-05] — feat(tapematch): manual-dir mode for run.sh
Changed: tools/tapematch/run.sh: now calls tapematch_session.py --manual-dir instead of bare tapematch.cli, giving full post-processing (archive, observations.db, report)
Added: tools/tapematch/tapematch_session.py: run_manual() function + --manual-dir/--label/--date CLI args; root_dir parameter threaded through run_tapematch(), insert_sources(), insert_pairs(), _log_to_obs_db()

[2026-06-05] — fix(gui): Flask backend persists after Electron closes
Fixed: gui_next/src/main/index.ts: added PID file tracking so stale Flask processes from prior or hot-reloaded sessions are killed on startup; removed the port-open short-circuit that left backendProc=null when a prior backend was still running; before-quit now also clears the PID file

[2026-06-05] — fix(tapematch): OOM kill in Pass 1 on dates with 6+ sources
Fixed: tools/tapematch/tapematch/cli.py: changed ingest to mono=True always; to_mono() now returns a zero-cost view instead of a ~388 MB copy; trimmed slice written directly to memmap via ravel() view with no intermediate heap array; peak per source drops from ~1.2 GB to ~500 MB (BUG-144)
Changed: tools/tapematch/config.yaml: marked mono_mix as unused

[2026-06-05] — fix(backend): extend apostrophe normalisation to lbdir verify path (BUG-143)
Fixed: backend/checksum_utils.py: parse_lbdir_file now applies _norm_fname() to all parsed filenames (md5/ffp/shntool/shntool_len sections); verify_folder_lbdir replaces bare folder/fname lookup with a normalised _disk_audio_map (relpath→Path) and normalised _subdir_index (basename→Path), matching the same apostrophe-safe pattern as verify_folder

[2026-06-05] — fix(backend): Verify fails to match filenames with curly apostrophes
Fixed: backend/checksum_utils.py: added _norm_fname() to translate typographic apostrophes (U+2018/2019/etc.) → straight apostrophe before building disk_audio_map keys and before storing parsed checksum filenames; prevents mismatch when checksum files use smart-quotes but disk files use straight apostrophes (BUG-143)

[2026-06-05] — fix(backend): pipeline apply-rename missing rename_log.txt and rename_history row
Fixed: backend/app.py: folder_rename route now calls write_rename_log(source='pipeline') before os.rename(), writing rename_log.txt into the folder and inserting a rename_history row (BUG-142)

[2026-06-05] — feat(pipeline+gui): LBDIR retrieve+check in pipeline step 4 with inline reconcile panel
Changed: backend/app.py: _pipeline_process_folder lbdir step now retrieves lbdir*.txt from attachments cache (scraping if needed) and runs verify_folder_lbdir; returns check summary (status/total/pass/missing/mismatch) instead of bare presence flag
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LbdirMiniPanel slide-in right panel shows check stats, per-file status table, reconcile proposals and apply workflow; "LBDIR" action button appears in any pipeline row whose lbdir step is not Pass; action column widened to 172px to fit two buttons

[2026-06-05] — fix(backend): Verify shows shntool-format FLAC checksums as missing duplicates
Fixed: backend/checksum_utils.py: _parse_checksum_file now strips [shntool] prefix from MD5-regex captures and reclassifies as shntool type, preventing bogus "[shntool] filename.flac" entries that don't match disk files (BUG-141)

[2026-06-05] — fix(gui): Lookup folder added once showing twice in sources list
Fixed: ScreenLookup.tsx: handleSingleFolder and handleFolders now guard against duplicate adds by checking sources by path before calling addSource; useEffect queue-sync callbacks also re-check after async fetch resolves to prevent race where a folder already added manually gets added again by the sync

[2026-06-05] — fix(gui): Rename screen always showed "No match" for folder sources that matched in Lookup
Fixed: ScreenLookup.tsx + lookupStore.ts: folder sources now store their full path; handleLookupAll builds a checksum→folder map so detail rows are tagged with source_file (full path) after lookup; without this, buildProposals could never map checksums back to folder paths and showed no_match for every row
Fixed: ScreenRename.tsx: buildProposals now compares the matched LB# against LB numbers already in the folder name; a different existing LB# shows wrong_lb state instead of incorrectly showing has_lb

[2026-06-05] — fix(gui): shared folder queue — bidirectional clear sync across Pipeline, Verify, LBDIR, Spectrograms
Fixed: ScreenPipeline.tsx: sync effect now handles removals bidirectionally — clearing on Verify/LBDIR/Spectrograms now also clears Pipeline rows (previously only additions were synced)
Fixed: ScreenPipeline.tsx: applyRename() now updates folderQueueStore with renamed path so the sync effect stays coherent after a rename
Added: FolderQueueRail.tsx: shared sidebar component (header, filter, scroll area, consistent Clear button + onClear callback for screen-specific state reset)
Changed: ScreenVerify.tsx: replaced inline aside with FolderQueueRail; removed redundant clearFolders destructure
Changed: ScreenLBDIR.tsx: replaced inline aside with FolderQueueRail; onClear resets activeFolder; removed redundant clearFolders destructure
Changed: ScreenSpectrograms.tsx: replaced inline aside with FolderQueueRail (adds Clear list button that was missing); onClear resets activeFolder+activeTrack; added useEffect to reset activeFolder when removed from queue on another screen
Changed: components/index.ts: export FolderQueueRail

[2026-06-05] — fix(backend): lookup duplicate resolution — show all equally-complete matches as Matched
Changed: backend/db.py: when a checksum appears in multiple LBs and all are fully complete, promote all to MATCHED (green) instead of leaving them as DUPLICATE (yellow); per-LB duplicates count still reflects the overlap

[2026-06-05] — feat(gui): clear-list button + right-click remove on all 5 pipeline screens
Added: ScreenPipeline.tsx: right-click queue item → "Remove from list" context menu; "Clear list" replaces clearQueue label
Added: ScreenVerify.tsx: "Clear list" trash button in rail; right-click folder row → remove
Added: ScreenLBDIR.tsx: "Clear list" trash button in rail; right-click folder row → remove
Added: ScreenLookup.tsx: right-click source row → remove single source; existing "Clear sources" button unchanged
Added: ScreenRename.tsx: "Clear list" button in header clears folderList; right-click table row → remove that folder
Added: lookupStore.ts: removeSource(idx) action with active-source index adjustment
Added: locales/en|de|fr|nl|it.json: common.clearList + common.removeFromList keys

[2026-06-04] — feat(gui): add single-folder button to all 5 pipeline screens
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Add folder…" button (pickDir → add directly, no tree scan) in queue rail
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: "Add folder…" button in rail bottom section
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: "Add folder…" button in rail bottom section
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: "Add folder…" button (full-width, spans 2 cols) in sources grid; scans folder via /api/lookup/scan_folders
Added: gui_next/src/renderer/src/screens/ScreenRename.tsx: "Add folder…" button in header; adds path to lookupStore.folderList so rename proposals are built for that folder
Added: locales/en|de|fr|nl|it.json: common.addFolder key

[2026-06-04] — fix(gui): Rename screen folder list never populated from folder scans
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: handleFolders now pushes scanned folder paths into folderList via setFolderList; queue-sync effect does the same for queue-pushed folders; runLookup no longer overwrites folderList with an empty array (source_file is never set by /api/lookup so the derived list was always [])

[2026-06-04] — fix(gui): LBDIR renames table column misalignment
Fixed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: colgroup had 6 <col> entries but TR auto-injects a 3px edge bar making 7 columns — disk_rel path was squeezed into the 24px arrow column; added 7th <col style={{width:32}}/> for the checkbox and matching <TH> in header

[2026-06-04] — fix(backend): combined-set lookup INCOMPLETE and lbdir bare-filename matching failures
Fixed: backend/db.py: _norm_track_base() strips directory prefix and normalizes & → _ before grouping DB checksums by track; BUG-130's fix was ineffective for SHN sets where the DB stored Disc1\dead&dylan.shn (md5) and dead_dylan.wav (shntool) as separate base keys — both now map to the same track, so LB-1332 correctly shows MATCHED instead of INCOMPLETE
Fixed: backend/checksum_utils.py: verify_folder_lbdir _norm now uses basename only; adds audio-only subdirectory fallback so bare-filename lbdirs (e.g. LBF-01334 with dead&dylan2003.8.06.d3t01.shn) resolve against Disc3/ entries in a combined multi-LB folder without ambiguously matching non-audio files like checksum.md5

[2026-06-04] — fix(lbdir): phantom "Missing" rows for SHN sets stored in disc subdirectories
Fixed: backend/checksum_utils.py: parse_lbdir_file now extracts the subdirectory context from shntool section headers (e.g. "=== shntool md5/hash for: archive\Disc1") and prepends it to every file entry in that section; without this, shntool entries for multi-disc SHN sets had no directory prefix and failed the _norm remap against the md5_map's Disc1/dead&dylan2003.* keys, producing 26 phantom "Missing" rows

[2026-06-04] — feat(search): right-click context menu with "Go to LB webpage" option
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: right-clicking any row opens the row menu at the cursor position; "Go to LB webpage" opens the LosslessBob detail URL in the browser

[2026-06-04] — fix(collection): View LB Entry opens webpage instead of navigating to lookup screen
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: handleCtxViewLookup was navigating to /lookup instead of opening the LB entry URL; also removed incorrect diskPath guard that disabled the menu item for unowned entries

[2026-06-04] — fix(lookup): group checksum detail by LB; filter non-audio entries from parser
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: checksum detail table now renders a group header row per LB when multiple LBs are present
Fixed: backend/db.py: parse_checksum_text — MD5/SHA1 entries for non-audio files (.txt, .rtf, .html, etc.) are now skipped; previously these appeared as spurious "Not found" rows in lookup results

[2026-06-04] — chore(tools): move tapematch runs/ to data/tapematch/runs/
Changed: tools/tapematch/tapematch_session.py: RUNS_DIR now points to PROJECT_ROOT/data/tapematch/runs — user data kept out of repo tree
Changed: tools/tapematch/gen_analysis.py: RUNS_DIR updated to match new location
Changed: .gitignore: removed stale tools/tapematch/runs/ entry (/data already covers it)

[2026-06-04] — feat(backend+gui): duplicate LB alias integration across all workflows
Changed: backend/db.py: get_missing_from_collection() — exclude alias partners of owned LBs via NOT EXISTS subqueries; get_collection() — annotate each row with linked_lbs list (bidirectional)
Changed: backend/app.py: /api/lookup route — annotate detail entries with is_alias_lb/canonical_lb; _pipeline_process_folder() — resolve aliases before single/conflict check, store alias_resolved_from; lbdir_retrieve() — cascade fallback to canonical LB when alias has no lbdir attachment
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: LookupDetail — add is_alias_lb, canonical_lb fields
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: show ≡ LB-XXXXX badge on summary rows matched to alias LBs
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: StepResult — add alias_resolved_from field; show ↩ alias note in LB label cell when alias was resolved
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: CollectionRow — add linkedLbs field; show ↔ LB-XXXXX pill in detail panel for entries with linked LBs

[2026-06-04] — chore(dev): Playwright GUI driver for automated screenshots and UI interaction
Added: gui_next/gui_driver.mjs: Playwright-based Electron driver; actions: screenshot, navigate, click, fill, eval, session; auto-starts Xvfb when $DISPLAY is unset; waits for splash overlay to detach before acting
Added: tools/debug_screens.json: session file that screenshots all main screens
Changed: gui_next/src/renderer/src/components/SplashOverlay.tsx: added data-testid="splash-overlay" so driver can reliably detect when splash has cleared
Changed: .claude/settings.json: pre-approved Bash rules for gui_driver.mjs and npm build

[2026-06-04] — fix(gui): Lookup tab now syncs folders from the shared folder queue
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: imported useFolderQueueStore and added a useEffect that watches the shared queue; any folder added on other tabs is scanned and added as a source automatically

[2026-06-04] — feat(gui): LBDIR screen — hide-verified filter
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: "Hide verified" checkbox below the folder search input; when checked, folders with a stored lbdir_verified_at timestamp are excluded from both the listbox and the "Process all folders" operation; sidebar count shows filtered/total when active

[2026-06-04] — feat(tools): tapematch — 1987 analysis-driven diagnostic refinements
Changed: tools/tapematch/tapematch/cli.py: add --set-offset HH:MM:SS flag to clip all sources to a given start time (for co-headline shows where the target set starts mid-recording)
Changed: tools/tapematch/tapematch/cli.py: raise TIMING MISMATCH threshold from 3 min to 8 min; AUD recordings of the same show routinely differ by 3–6 min from crowd-intro variation
Changed: tools/tapematch/tapematch/cli.py: suppress TIMING MISMATCH for INFLATED-flagged sources (the existing [INFLATED] flag already covers the cause)
Changed: tools/tapematch/tapematch/cli.py: replace [low confidence] label with [fp-linked] when a family was assembled purely by fingerprint Dice evidence rather than primary STFT
Changed: tools/tapematch/tapematch/cli.py: add [chain-unverified] note to 3+ member families where at least one pair has only transitive evidence (A→B + B→C but A↔C not directly confirmed)
Changed: tools/tapematch/tapematch_session.py: pass --set-offset through run_date → run_tapematch; expose as CLI arg
Changed: tools/tapematch/tapematch_session.py: load results.json before build_report in both normal and --report-only paths; add _build_commentary_audit() which compares LB page "same recording as" claims against tapematch family assignments and appends an audit table to each report

[2026-06-03] — feat(tools): tapematch — 1989 log analysis + 5 diagnostic/algorithm improvements
Changed: tools/tapematch/tapematch/match.py: extend speed-ratio search to ±2.0% (was ±1.5%); many 1989 recordings sit at 14000–15000 ppm boundary
Changed: tools/tapematch/tapematch/cli.py: suppress TIMING MISMATCH warnings for INCOMPLETE-flagged pair members (removes ~200 redundant lines per year-run)
Changed: tools/tapematch/tapematch/cli.py: exclude INCOMPLETE/INFLATED sources from central-ref selection so anchors come from a well-formed recording
Changed: tools/tapematch/tapematch/cli.py: staircase short-window fallback triggers when EITHER source has splice edits, not both
Changed: tools/tapematch/tapematch/cli.py: [SECONDARY SAME-SOURCE] diagnostic distinguishes NR-processed pairs (music aligns, quiet-segment noise doesn't) from remasters

[2026-06-03] — test: regression tests for BUG-127, BUG-128, BUG-130
Added: tests/test_batch_verify.py: 8 tests for _map_verify_status (BUG-127) + 8 tests for has_lbdir LBF-format detection (BUG-128)
Added: tests/test_db_lookup.py: 4 tests for lookup_checksums SHN completeness grouping (BUG-130) — covers MATCHED, partial INCOMPLETE, and mixed .shn/.wav input

[2026-06-03] — feat(gui): Pipeline + Verify — "1 level only" checkbox for root folder scan
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: shallowScan state + checkbox below "Scan tree…" button; passes shallow: true to /api/pipeline/scan-tree when checked
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: same shallowScan toggle below "Add root folder…" button
Added: gui_next/src/renderer/src/locales/*.json: common.shallowScan key in all 6 locales

[2026-06-03] — fix(backend+gui): Lookup — SHN sets falsely shown as Incomplete/Not Found
Fixed: backend/db.py: completeness check now groups .shn/.wav (and any audio ext) entries by base filename; a matched MD5 of foo.shn covers the shntool checksum for foo.wav, so a full SHN set shows MATCHED instead of INCOMPLETE
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: apiStatusToState() now maps backend 'INCOMPLETE' → incomplete; previously fell through to notfound fallback showing red "Not Found" for SHN sets

[2026-06-03] — feat(backend+gui): LBDIR reconcile — recover missing files from site/files by MD5
Added: backend/checksum_utils.py: find_site_recoverable_files() — scans SITE_FILES_DIR for LBF-NNNNN-* files, matches by MD5 against still-missing lbdir entries
Changed: backend/app.py: /api/lbdir/reconcile appends site_proposals; /api/lbdir/apply_reconcile accepts site_copies and copies matched site files to folder (with SITE_FILES_DIR path guard)
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: SiteProposal type, site_proposals on ReconcileResult, siteSelected + setSiteSelected in store
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: ReconcilePanel "Recoverable from site/files" section with checkboxes; apply wires site_copies

[2026-06-03] — fix(backend+tools): lbdir_retrieve skips copy if lbdir already in folder; has_lbdir matches LBF-format files
Fixed: backend/app.py: lbdir_retrieve now checks for any existing lbdir in folder before copying from cache; previously always overwrote, so a cache update between batch_verify and clicking Process would silently swap in a different lbdir causing a false result change
Fixed: tools/batch_verify.py: has_lbdir used case-sensitive glob "lbdir*.txt" missing LBF-*-lbdir.txt files on Linux; now uses iterdir+lower() matching _find_lbdir_in_folder
Fixed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: pre-check folder dot now neutral gray instead of green for stale lbdir_verified_at; green reserved for live pass

[2026-06-03] — fix(tools): batch_verify — don't persist transient connection errors; add --purge-connection-errors
Changed: tools/batch_verify.py: process_folder Phase 1 — connection_error/timeout_error from _api_retrieve no longer written to DB; resume retries them
Changed: tools/batch_verify.py: process_folder Phase 2 — ConnectionError/Timeout from _api_verify no longer written to DB; resume retries them
Added: tools/batch_verify.py: purge_connection_errors() + --purge-connection-errors CLI flag to delete existing stale connection-error rows

[2026-06-03] — fix(backend): LBDIR reconcile — lbdir file itself no longer appears as an extra
Fixed: backend/checksum_utils.py: find_reconcilable_files — skip the lbdir file when building all_disk_rels so it no longer ends up in unmatched_disk and gets proposed for move to /extras/

[2026-06-03] — fix(gui+backend): LBDIR screen — shallow root-folder scan and resizable file-table columns
Changed: backend/app.py: pipeline_scan_tree — added shallow param; when true, only checks root + immediate subdirs (depth 1) instead of full rglob walk
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: handleAddRoot passes shallow:true to scan-tree; file detail table columns are now drag-resizable via startFileColResize + fileColWidths state

[2026-06-03] — feat(gui+backend): DB Editor — add batch_verify.db as selectable database
Changed: backend/paths.py: added BATCH_VERIFY_DB_PATH constant
Changed: backend/app.py: added _dbedit_db_path()/_dbedit_is_batchverify() helpers; all 7 dbedit routes accept ?db=batchverify param; batch_verify tables are all readonly; dbedit_query accepts db in POST body
Changed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: added activeDb state and switchDb(); db selector buttons above table list; all dbedit fetch calls pass ?db=; integrity/alias panels hidden for batch_verify; SqlQueryPanel receives db prop

[2026-06-03] — feat(gui): Collection screen — chip groups, additive Not-in-collection filter, column alignment fix
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Filter chips divided into three groups with separators (status, history, not-in-collection); "Not in collection" converted from primary filter to independent additive toggle (notOwned state); filteredMissingRows computed by lb_status when Public/Private filter is active; not-owned table uses filteredMissingRows; column alignment fixed by removing stray extra <TD /> from not-owned table body rows; Export CSV uses filtered rows; all filter === 'not_owned' guards replaced with notOwned boolean

[2026-06-03] — feat(gui): Collection screen — resizable columns + Public/Private filter chips + column picker
Changed: gui_next/src/renderer/src/components/table.tsx: TH now accepts onResizeStart prop; renders a col-resize drag handle on the right edge with hover indicator
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: FilterKey extended with 'public'/'private'; counts/filter logic added; Public and Private chips added after All chip; ColKey type + ALL_COLS/COL_LABELS/DEFAULT_COL_WIDTHS constants; colWidths Record + lbColWidth state; visibleCols persisted to localStorage (lbb_collection_cols); Columns popover in filter bar; table colgroup/thead/tbody conditioned on visibleCols; startColResize uses ColKey | 'lb'

[2026-06-03] — feat(gui): Collection screen — dynamic category filter chips
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: category chips now derived dynamically from categoryCounts (sorted by count) instead of hardcoded concert/interview; covers all types (concert, tv, studio, interview, compilation, rehearsal, radio, soundcheck)

[2026-06-03] — feat(gui): LBDIR screen — show prior lbdir-verified status in folder sidebar
Added: backend/app.py: POST /api/lbdir/verified_status — queries my_collection for lbdir_verified_at per folder path
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: added lbdir_verified_at to CheckResult type
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: loads verified_status on mount/folder-change; FolderSideRow shows faded green dot + "✓ YYYY-MM-DD" for folders with prior verification and no current check result

[2026-06-03] — refactor(gui): LBDIR screen — unified process flow, no sub-tabs
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: replaced 4 sub-tabs (Check/Retrieve/Reconcile/Extras) with a single Process action that auto-retrieves lbdir then checks; Reconcile button inline below file table; extras moved to /extras/ subfolder instead of deleted
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: removed tab/retrieveResults/extrasResults/extrasSelected state; added clearReconcileFor action
Added: backend/app.py: POST /api/lbdir/move_extras — moves extra files to <folder>/extras/ preserving relative path structure

[2026-06-03] — feat(tools): batch_verify l=full legend, e=expand toggle, updated progress
Added: tools/batch_verify.py: l key prints full status legend with definitions; e key toggles expanded progress mode (full status name + LB tag + folder name + pass/mismatch/missing counts); h key prints compact abbr legend; print_progress gains expanded kwarg

[2026-06-03] — feat(tools): batch_verify interactive keys (q/h/s) during run
Added: tools/batch_verify.py: _KeyboardController reads single keypresses via termios cbreak; q=clean quit after current folder, h=re-print abbr+key legend, s=live stats summary; terminal restored in finally block; no-op when stdin is not a TTY

[2026-06-03] — feat(tools): batch_verify compact progress output ≤30 chars/line
Changed: tools/batch_verify.py: print_progress replaced with compact format [i/total] {abbr} {lb} [{extra}]; status shown as 2-letter code (OK/FL/MF/NL/ER/etc.); extra shows proposal count (MF) or first 7 chars of notes (ER)

[2026-06-03] — feat(tools): batch_verify --skip-done flag + improved --help
Added: tools/batch_verify.py: --skip-done skips any folder with any existing result (vs --resume which only skips pass); --reprocess still overrides; grouped argparse help with examples and descriptions for every flag

[2026-06-03] — fix(tools): batch_verify misclassifies missing-file folders as api_error
Fixed: tools/batch_verify.py: _VERIFY_STATUS_MAP was missing "missing_files" key; verify_folder_lbdir returns "missing_files" (not "incomplete") when n_missing > 0, so all such folders fell through to STATUS_API_ERROR; added "missing_files" → STATUS_MISSING_FILES to the map

[2026-06-03] — feat(tools): tapematch iteration pass — six accuracy/quality improvements; threshold calibrated 0.35→0.50
Changed: tools/tapematch/config.yaml: max_lag_sec 30→90; local_lag_sec 5→10; short_window_sec/short_hop_sec added; fingerprint hf_band_hz [6000,8000] + cluster_threshold calibrated to 0.50 (empirical bimodal gap 0.47/0.51 confirmed across 3 dates)
Changed: tools/tapematch/tapematch/match.py: fingerprint_window slices STFT to hf_band_hz before peak-finding
Changed: tools/tapematch/tapematch/cli.py: staircase/staircase short-window fallback; cluster() wired to fingerprint (F=FP, fp_cluster_thr); will_merge uses fp_cluster_thr; [TIMING MISMATCH] diagnostic; diagnostic section renumbered
Changed: tools/tapematch/WORKFLOW.md: calibration table added; updated config knobs; updated failure mode table

[2026-06-03] — fix(tools): tapematch year_run spawns a fresh subprocess per date
Fixed: tools/tapematch/tapematch_session.py: year_run() now spawns tapematch_session.py <date> as a subprocess instead of calling run_date() in-process — each date's Python heap, page cache mappings, and OS resources are fully released when the subprocess exits; also added _clean_stale_tmp_dirs() in run_tapematch() to remove any tapematch_* memmaps left by OOM-killed subprocesses

[2026-06-02] — feat(gui): collapsible filter pane in Search screen
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: filterPaneOpen state; aside collapses to 32px strip with chevRight expand button; chevLeft button in open pane collapses it; 180ms CSS transition

[2026-06-02] — fix(gui): Search TYPE filter now shows all categories dynamically
Fixed: gui_next/src/renderer/src/screens/ScreenSearch.tsx:1009: hardcoded ['concert','interview'] replaced with dynamic list from facetCounts.categoryC sorted by count — tv, studio, compilation, rehearsal, radio, soundcheck were missing

[2026-06-02] — feat(tools): tapematch — year batch mode with resume support
Added: tools/tapematch/tapematch_session.py: get_year_dates(), run_date() (extracted from main), year_run() — --year YYYY flag loops all collected+paged dates for a year in chronological order, skipping dates already in observations.db; Ctrl+C prints resume command and exits cleanly; --min-entries N (default 2) controls minimum sources per date
Added: tools/tapematch/run_year.sh: convenience wrapper: ./run_year.sh 1995 [--dry-run]

[2026-06-02] — feat(tools): tapematch — INFLATED duration diagnostic
Added: tools/tapematch/tapematch/cli.py: flags sources with performance duration >30% above group median as [INFLATED?] in TRIM section and [INFLATED] in DIAGNOSTICS; mirrors existing INCOMPLETE flag; catches duplicate-track subfolders (e.g. "fixed tracks" copies) that corrupt correlation results

[2026-06-02] — fix(tools): tapematch — skip __MACOSX metadata files during ingest
Fixed: tools/tapematch/tapematch/ingest.py: list_tracks() now filters out ._-prefixed files and paths containing __MACOSX (AppleDouble resource forks created by macOS zip/copy); was crashing on LB-01961 (Brixton Academy 2003-11-25)

[2026-06-02] — fix(tools): tapematch — hiss-driven merge for staircase/CDR re-tracking pairs
Fixed: tools/tapematch/tapematch/match.py: cluster() now accepts H/H_med matrices; merges pair when hiss_frac >= hiss_merge_frac AND hiss_median >= hiss_merge_median (both required to block room-ambience false positives on modern digital recordings)
Fixed: tools/tapematch/tapematch/cli.py: track H_med matrix; pass to cluster(); SECONDARY MATCH label now says "→ SECONDARY LINK" only when merge will actually happen, "→ hiss evidence (below merge threshold)" otherwise
Changed: tools/tapematch/config.yaml: added hiss_merge_frac: 0.60, hiss_merge_median: 0.65 to secondary_match block; clarified hiss_frac_threshold as display-only

[2026-06-02] — feat(tools): tapematch report — enrich Coverage table + save analysis to run folder
Changed: tools/tapematch/tapematch_session.py: Coverage table now includes Rating, Timing, and source snippet columns from LB page; added _lb_source_snippet() helper; analysis.md written manually to run folder after each session
Added: tools/tapematch/runs/20260602_184543_1993-07-09/analysis.md: Claude analysis of 1993-07-09 La Coruna run

[2026-06-02] — feat(tools): tapematch fingerprint — Shazam-style spectral peak landmark matching
Added: tools/tapematch/tapematch/match.py: _stft_mag(), _find_peaks_2d(), fingerprint_window() — builds (f_anchor, f_target, Δt) hash set from 10-min reference window (skip first 3 min); offset-invariant by construction; fingerprint_score() — Dice coefficient between hash sets
Added: tools/tapematch/tapematch/cli.py: computes fingerprints for all sources upfront; adds fp_score to sec_results per cross-family pair; shows Dice score in SECONDARY MATCH and DIAGNOSTICS sections; does NOT drive clustering (confirmatory only)
Added: tools/tapematch/config.yaml: fingerprint block with window/nperseg/fanout/threshold knobs
Fixed: match_threshold raised 0.10→0.60 after discovering live recordings of the same concert score 0.15–0.50 (same musical notes → same Δt hashes); same-source confirmed pairs score 0.60–0.85; documented in config comment
Verified: 1996-07-21 Pori — LB-06986/LB-00513 scores Dice 0.695 (confirms windowed+hiss evidence); 9 different-source pairs score 0.19–0.49 (correctly below threshold); 4 families preserved

[2026-06-02] — feat(tools): tapematch secondary match — windowed coverage + quiet-segment hiss correlation
Added: tools/tapematch/tapematch/match.py: find_quiet_segments() — finds low-energy between-song sections from memmap-safe block reads; secondary_corr_pair() — dense 60s-window grid corr (per-window local lag ±5s, no speed-correction to preserve HF fine-structure) + quiet-segment hiss corr; cluster() extended with optional W/w_threshold for secondary linkage
Added: tools/tapematch/tapematch/cli.py: secondary match pass runs after primary matrix for cross-family pairs only; prints SECONDARY MATCH section; feeds W matrix into combined cluster(); annotates Family output with secondary evidence; adds [SECONDARY SAME-SOURCE] diagnostic; extends JSON output with secondary_matrix and secondary_pairs
Added: tools/tapematch/config.yaml: secondary_match block with windowed and quiet-segment knobs
Fixed: tools/tapematch/tapematch/cli.py: do NOT apply resample_poly before secondary_corr_pair — resample_poly smears HF fine-structure, killing residual_corr even for same-source pairs; windowed local lag search absorbs speed differences natively
Verified: 1996-07-21 Pori — LB-06986 (LTA remaster of LB-00513) now correctly grouped as Family 3 via windowed 0.69 / hiss 0.59; no false positives on remaining 9 cross-family pairs

[2026-06-02] — fix(tools): tapematch LB page relationship detection — bittorrent stripping + full text extraction
Fixed: tools/tapematch/tapematch_session.py: _page_text used regex tag-stripping which bled bittorrent description paragraphs (describing third-party uploads) into relationship search text; switched to soup.get_text() so bare text nodes between <hr/> separators (where "same recording as LB-XXXX" notes live) are included
Fixed: tools/tapematch/tapematch_session.py: added _strip_bittorrent_blocks() — balanced-paren walker that removes (a bittorrent from ...) parentheticals from curator text before relationship detection; prevents uploader-asserted "same as LB-XXXX" claims from polluting lb_says_same in observations DB
Fixed: tools/tapematch/tapematch_session.py: extract_lb_relationship returned None on first ambiguous LB-number mention (e.g. page header) without checking later occurrences; now iterates all matches and only returns None after exhausting them
Fixed: tools/tapematch/tapematch_session.py: "matching" keyword missed "fingerprints which match"; replaced keyword list with compiled regexes _SAME_RE / _DIFF_RE covering "fingerprints.{0,40}match", "eac match", "close match", "identical"

[2026-06-02] — tune(tools): tapematch cluster_threshold 0.55 → 0.45
Changed: tools/tapematch/config.yaml: cluster_threshold lowered from 0.55 to 0.45; motivated by 1998-10-28 LB-06564/LB-12485 (confirmed same DAT master, different transfer path — CDR trade copy vs fresh 2016 transfer) scoring 0.520 and being missed at 0.55; safety margin above highest observed different-source corr (0.362, 1995-07-08) is 0.083

[2026-06-02] — fix(tools): tapematch trim None crash + stale results.json on failed run
Fixed: tools/tapematch/tapematch/trim.py:63: performance_envelope computed end_i = len - 1 - _first_sustained(...) before checking for None; TypeError when no sustained tail region found (vinyl rips / recordings with no silence tail); split into end_raw variable, guard before arithmetic
Fixed: tools/tapematch/tapematch_session.py:669: stale last_results.json from a prior run was loaded in step 7 when tapematch crashed mid-run without writing new results; now unlinks the file before running tapematch so a crash leaves no stale data to pick up

[2026-06-02] — fix(tools): tapematch page parser + staircase message; private LB path filter; post-matrix central-source reference
Fixed: tools/tapematch/tapematch_session.py: extract_lb_commentary now falls back to first substantial <p> tag (most LB pages store commentary in <p>, not <td>); only LB-01863-style pages with "SOURCE:" text were parsing before
Fixed: tools/tapematch/tapematch_session.py: private LB exclusion changed from page-existence check to disk_path substring match ("PRIVATE", "NOTORRENT", "NO TORRENT") — correctly excludes entries that have a local page but private path
Fixed: tools/tapematch/tapematch/cli.py: removed pre-pass reference selection; post-matrix central-source selection via argmax(M.sum(axis=1)) guarantees selection of most-correlated source; pre-pass failed when median-duration source was a low-corr outlier (cassette)
Changed: tools/tapematch/tapematch/cli.py: staircase lag-curve annotation changed from "consistent with bootleg press or edited master" to neutral "staircase pattern (CDR re-tracking or tape edits)"

[2026-06-02] — feat(tools): tapematch workflow tooling — --suggest, private LB exclusion, smart reference, WORKFLOW.md
Added: tools/tapematch/tapematch_session.py: --suggest flag queries DB for 3–5 entry dates not yet analysed; private LBs (no local page) auto-excluded from runs; smart central-source reference selection (1-anchor pre-pass replaces alphabetical default)
Added: tools/tapematch/tapematch/cli.py: auto-select most-central source as lag-curve reference via quick pre-pass; --json-out flag for structured results
Added: tools/tapematch/WORKFLOW.md: self-contained process doc for context-clear restarts

[2026-06-02] — feat(tools): tapematch observations DB, run archiving, config/diagnostic tuning
Added: tools/tapematch/tapematch_session.py: observations.db (runs/sources/pairs tables with full metrics + LB commentary relationship extraction + null human_judgment columns); run archiving to runs/RUN_ID_DATE/ (log, report, config, results.json); --report-only flag; DB-first path resolution via my_collection
Added: tools/tapematch/tapematch/cli.py: --json-out flag writes structured results JSON; matrix labels now show LB-NNNNN; [DISTINCT SOURCE] replaces spurious [REMASTER?] for near-zero-corr singletons; [SHARED HF CEILING] suppressed when ceiling is Nyquist-limited at analysis_sr
Changed: tools/tapematch/config.yaml: n_anchors 6→12 (more robust to track-break lag errors); cluster_threshold 0.70→0.55 (catches same-source pairs with different CDR splits)

[2026-06-02] — feat(tools): tapematch_session.py — iterative analysis session orchestrator
Added: tools/tapematch/tapematch_session.py: script that queries losslessbob.db for a given date, finds LB folders across DYLAN drives, cleans/populates examples/tapematch/, runs tapematch CLI, extracts LB page commentary, and writes a combined last_run_report.md; supports --dry-run and --no-tapematch flags

[2026-06-02] — feat(tools): tapematch diagnostic output improvements
Changed: tools/tapematch/tapematch/match.py: add cluster_confidence() helper (high/medium/low tier); add asymmetry_dc field to lineage_evidence() return dict
Changed: tools/tapematch/tapematch/cli.py: duration outlier detection with [INCOMPLETE?] flag in TRIM section; speed_info dict persisted across lag-curve pass; staircase/splice explanation text; confidence label on CLUSTERS; DC asymmetry column in LINEAGE; new DIAGNOSTICS section cross-referencing [INCOMPLETE], [REMASTER?], [HIGH/MEDIUM/LOW CONFIDENCE], and [SHARED HF CEILING] diagnostics

[2026-06-02] — feat(gui): lb_category type filter chips on Lookup, Search, and Collection views
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: Concert/Interview Chip row below status bars; filters filteredSummary
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: activeCategory Set state; Type FacetGroup in sidebar; category filter in filteredRows; chips in active-filter strip
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: categoryFilter Set state; Concert/Interview chips in filter bar; category applied to filteredRows

[2026-06-02] — feat(gui): surface lb_category (concert/interview) as Type pill on Lookup, Search, and Collection views
Added: backend/db.py: lb_category included in search_entries, get_entries_by_lb_list, get_collection, and lookup_checksums annotation pass
Added: gui_next/src/renderer/src/lib/lookupStore.ts: lb_category field on LookupDetail and LookupSummaryRow interfaces
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: Type column + pill on summary table rows
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: toggleable "cat" column with Type pill
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Type column with pill; category field on CollectionRow

[2026-06-02] — fix(tools): tapematch — correct trim duration basis and ffprobe final-timestamp bug
Fixed: tools/tapematch/tapematch/cli.py:54: use len(stream)/sr as total_sec in trim_bounds; eliminates negative tail display and performance > total anomaly
Fixed: tools/tapematch/tapematch/audio.py:43: _ffprobe_info fallback uses re.findall[-1] for final ffmpeg stats timestamp; fixes non-deterministic duration for SHN/MP3 sources

[2026-06-02] — feat(gui): lookup — flag owned recordings with collection/lbdir-verified status
Added: backend/db.py: lookup_checksums() annotates each detail+summary item with owned (bool) and lbdir_verified (bool) by joining against my_collection
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: added owned+lbdir_verified fields to LookupDetail and LookupSummaryRow
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: owned/lbdir_verified banner above summary table; owned rows show "In collection · verified" (green) or "In collection" (amber) pill replacing the +WL button; fixed STATE_TONE variable shadow (t → tone) that was breaking button labels
Added: gui_next/src/renderer/src/locales/en.json: lookup.owned.* keys for banner and badge strings
Changed: cli.py: _print_lookup_diff prints [IN COLLECTION · LBDIR VERIFIED] or [IN COLLECTION] on the LB header line when owned

[2026-06-02] — fix(tools): tapematch — write memmaps to /mnt/DATA0/tmp instead of system tmpfs
Fixed: tools/tapematch/tapematch/cli.py: mkdtemp now uses dir=/mnt/DATA0/tmp; avoids filling system tmpfs with ~438 MB memmap per source

[2026-06-02] — feat(backend): track lbdir verify pass timestamp per collection folder
Added: backend/db.py: lbdir_verified_at column migration on my_collection; set_lbdir_verified(disk_path) writer; get_collection() now returns lbdir_verified_at
Changed: backend/app.py: lbdir_check() stamps lbdir_verified_at when result status == "pass", returns timestamp in result dict (covers both GUI and batch_verify.py paths)

[2026-06-02] — fix(tools): tapematch — eliminate OOM on large collections (5 fixes)
Changed: tools/tapematch/tapematch/audio.py: load() always decodes+resamples via ffmpeg pipe; removes sf.read+resample_poly path that held 3–12x native-rate memory for hi-res sources; added probe() helper for channel/frame count without audio decode
Changed: tools/tapematch/tapematch/ingest.py: concat_source() pre-allocates output from probed durations then loads+copies+frees each track; peak drops from 2× source size to output + 1 track
Changed: tools/tapematch/tapematch/trim.py: spectral_flatness() processes in 5-min chunks; per-iteration Z capped at ~38 MB vs the ~4.3 GB full-signal STFT matrix
Changed: tools/tapematch/tapematch/align.py: onset_strength() processes in 1-min chunks with del Z/mag per iteration; per-iteration Z capped at ~7.7 MB
Changed: tools/tapematch/tapematch/match.py: lineage_evidence() replaced full STFT+PSD with scipy.signal.welch (returns 1-D PSD only, never allocates freq×time matrix)
Changed: tools/tapematch/tapematch/cli.py: trim pass now writes trimmed mono to disk as np.memmap (.f32 per source); all analysis phases (lag curves, matrix, lineage) open memmaps instead of holding full arrays; peak process heap for 10×2h sources ≈ 2.3 GB vs ~8 GB+ previously

[2026-06-01] — refactor(tools): tapematch cli.py — sequential pair processing, one source in RAM at a time
Changed: tools/tapematch/tapematch/cli.py: replaced streams/trimmed/monos dicts (all N sources simultaneously) with a single trim_bounds pass; added _load_trimmed_mono helper; inlined pairwise matrix loop so each source is loaded per pair and freed immediately; ref_mono kept in RAM for lag + matrix ref-column to avoid redundant reloads; trim bounds saved to root/.tapematch_meta.json after Pass 1; lineage pass loads stereo stream per source and frees after each

[2026-06-01] — feat(gui): SplashOverlay + AboutDialog — startup splash A and tabbed About C
Added: gui_next/src/renderer/src/components/SplashOverlay.tsx: Splash A "Launch card" — plays real boot-phase sequence at measured speed (~2.4 s), polls Flask for real done signal, indeterminate bar on overrun, fades out on ready
Added: gui_next/src/renderer/src/components/AboutDialog.tsx: About C "Tabbed" — four tabs (About / Tech / Credits / Changes) with double-square brand header, close on Escape or backdrop click
Changed: gui_next/src/renderer/src/App.tsx: mount SplashOverlay on startup; manage showAbout state; pass onAbout to AppShell
Changed: gui_next/src/renderer/src/components/AppShell.tsx: add onAbout prop; wire sidebar "more" button to open About dialog
Changed: gui_next/src/renderer/src/index.css: add @keyframes lbbIndet for splash progress bar indeterminate state

[2026-06-01] — feat(gui_next): collection right-click "Send to →" submenu for pipeline screens
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: import useFolderQueueStore; extend ContextMenu to support children (submenu flyout); add handleCtxSendTo callback; add "Send to →" context menu item with Pipeline / Verify / LBDIR / Spectrograms sub-options

[2026-06-01] — fix(backend): BUG-121 add GET /api/collection/audit — flag collection entries missing checksum rows
Added: backend/db.py:audit_collection_checksums(): query my_collection LEFT JOIN checksums, return {total, missing_checksums, entries} for lb_numbers with zero checksum rows
Added: backend/app.py: GET /api/collection/audit route exposes audit_collection_checksums(); documented in PROJECT.md

[2026-06-01] — fix(backend): BUG-117 checksum rglob + BUG-119 NFT rename preserves folder date/location
Fixed: backend/app.py:4604: BUG-117 — changed iterdir() to rglob("*") in pipeline lookup step so checksum files in subfolders are found (was missing ~12% of collection)
Fixed: backend/app.py:4638: BUG-119 — when DB has no date_str/location for an NFT entry, now preserves current folder name and only toggles -NFT suffix (was proposing bare LB-NNNNN-NFT, silently stripping date/location)

[2026-06-01] — feat(db+scraper): entries.lb_category — add column, classify on scrape, bulk reclassify
Added: backend/db.py: classify_one_entry(date_str, description, location, conn) for per-entry classification inside write closures
Changed: backend/scraper.py: _save_entry now computes and stores lb_category on every INSERT OR REPLACE
Added: backend/db.py: lb_category TEXT column to entries; classify_entry_categories() bulk classify; MASTER_SCHEMA_VERSION→6; POST /api/entries/reclassify (curator)

[2026-06-01] — feat(db): add entries.lb_category column; classify concerts from bobdylan_shows
Added: backend/db.py: lb_category TEXT column to entries; classify_entry_categories() classifies all 16 630 entries (concert via bobdylan_shows date-join, non-concert categories via dylan_performances + keyword heuristics, unknown fallback); one-time backfill in init_db(); MASTER_SCHEMA_VERSION bumped to 6
Added: backend/app.py: POST /api/entries/reclassify (curator-only) to re-run classification after bobdylan_shows updates
Results: concert 84.7%, unknown 12.3%, tv/interview/studio/compilation/rehearsal/radio/soundcheck ~3%

[2026-06-01] — feat(tools): batch collection verification pipeline + --from-collection mode
Added: tools/batch_verify.py: headless CLI for lbdir-centric batch verification of large collections; 4-phase pipeline (identify/retrieve/verify/reconcile-preview); report SQLite DB (data/batch_verify.db); --resume/--dry-run/--reprocess/--report modes; --from-collection fetches disk_path+lb_number from GET /api/collection (skips Phase 0 identify); --root walks a directory tree. (BATCH-VERIFY)

---
Older entries (2026-05 and earlier): see CHANGELOG_ARCHIVE.md
