TODO-150: Unified Library — TapeMatch backend integration + Library screen
Priority: High
Status: In Progress
Added: 2026-06-18
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
  "don't ship placeholder data" rule argues against. i18n (step 10) deferred per user
  decision (2026-06-18): English-only is fine for now, multi-locale translation of the
  in-screen Library strings is not being done this pass. See TODO-151 (now in TODO_DONE.md)
  for the lb_category audit this step also prompted.
  Decision (2026-06-18): performance lens (step 6/`get_performances()`) now filters to
  `lb_category = 'concert'` only — radio/tv/interview/studio/rehearsal/soundcheck/
  compilation/other/unknown recordings have no real venue/setlist/tour and would render
  as bare, misleading show rows. They remain visible via the recording lens. TODO-151
  (now closed, see TODO_DONE.md) audited `lb_category` accuracy and decided/implemented
  the fix: `get_performances()` now also includes date+location-complete 'unknown' rows
  as degraded `confirmed: false` shows, recovering 198 real performances bobdylan_shows
  didn't track (mostly guest spots at other artists' shows).

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

