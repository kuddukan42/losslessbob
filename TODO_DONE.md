# Completed TODO Archive
# Active/open tasks are in TODO.md. Entries here are Done or Cancelled.

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
