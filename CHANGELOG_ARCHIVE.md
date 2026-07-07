# CHANGELOG Archive

Entries rotated out of CHANGELOG.md (rolling ~2-month window there). Newest first.

[2026-05-31] — chore(tests): pipeline smoke-test 500-folder run; 2 more bugs added
Added: BUGS.md BUG-120: 2 folders with verify mismatch (audio changed since checksumming); BUG-121: Farm Aid LB-12347 in collection but checksums absent from DB
Changed: BUGS.md BUG-117: confirmed 12% rate over 500-folder run (was 11%/100); BUG-118: expanded to 11 conflicts including 5-way match and phantom LB-04994/03029/06748/11900 pattern

[2026-05-31] — chore(tests): pipeline smoke-test script + 3 new bugs documented
Added: tests/test_pipeline_smoke.py: random-sample 100 collection folders through all 4 pipeline steps (verify/lookup/rename/lbdir); outputs detail report + reproducible bug list
Added: BUGS.md BUG-117/118/119: no-checksum folders in collection, lookup conflict (3 shared-checksum pairs), NFT rename strips date/location

[2026-05-31] — fix(backend): forum post description showed checksums instead of entry info text
Fixed: backend/forum_poster.py: _read_lb_txt now excludes double-extension files (.ffp.txt, .md5.txt) via f.suffixes == ['.txt']; prefers file containing LB-{number} in its name as the main info file over alphabetical first

[2026-05-31] — fix(backend): verify_folder shows files as Missing when audio is in subfolders
Fixed: backend/checksum_utils.py: detect_folder_mode now uses rglob instead of glob; verify_folder builds a name→path map with rglob so audio files in subdirectories are found and resolved correctly instead of showing as Missing

[2026-05-31] — fix(backend): LBDIR check inflates track count for SHN recordings with shntool hashes
Fixed: backend/checksum_utils.py: verify_folder_lbdir() normalizes shntool-section filenames via non-alphanumeric → '_' collapse on both sides before matching against md5 keys; handles shntool's space AND special-char (e.g. '&') → '_' substitution, preventing duplicate file rows

[2026-05-31] — fix(backend): LBDIR check reports 0 tracks / false Pass for flat-format lbdir files
Fixed: backend/checksum_utils.py: parse_lbdir_file now has a flat-format fallback — if no section headers (=== MD5 for: / === FFP for:) are found after the main parse pass, re-scans each line directly as MD5/FFP entries; handles *.flacf.md5.txt and *.wavf.md5.txt lbdir variants that contain plain HASH  filename lines without section structure

[2026-05-31] — fix(backend/gui_next): LBDIR "Check all folders" crash on missing files or no lbdir
Fixed: backend/checksum_utils.py: status 'incomplete' renamed to 'missing_files' to match frontend LbdirState; parse-error early-return now emits full schema (status='no_lbdir', mode='unknown', files=[]) instead of bare error dict
Fixed: backend/app.py: no-lbdir branch now returns complete schema (status='no_lbdir', mode='unknown', files=[]) so all fields exist when the folder is rendered
Added: gui_next/src/renderer/src/lib/lbdirStore.ts: 'shntool_missing' added to LbdirState union
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: shntool_missing → STATE_LABEL entry (tone='warn', label='Shntool not installed')

[2026-05-31] — fix(gui_next): ScreenSearch rating filter — full grade scale and ASCII hyphen fix
Fixed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: rating chips were missing A+, C+, C-, D+, D, D-, F; Unicode minus U+2212 replaced with ASCII hyphen so A- filter now matches DB values; RATING_RANK, VALID_RATINGS, RatingGrade type, ratingTone, ratingItems, and "Rated A or A-" built-in view all updated

[2026-05-31] — fix(backend/gui_next): stale torrent records cleanup + ghost torrent_file_exists fix
Fixed: backend/db.py: add delete_torrent_record(); add clear_superseded_torrent_paths() — nulls out torrent_path on older sibling records when a regen reuses the same filename, preventing false torrent_file_exists=True
Fixed: backend/app.py: torrent_create route calls clear_superseded_torrent_paths after regen; new DELETE /api/torrent/<id> route deletes DB record + file (blocked if still in qBt)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: "Del record" button in HISTORY torrent panel + GlobalTorrentPanel (disabled if added_to_qbt=1); ConfirmDialog for both
Added: gui_next/src/renderer/src/locales/*.json: delRecord, recordTitle, recordBody, torrentRecordDeleted keys in all 6 locales

[2026-05-31] — fix(backend): pipeline scan-tree now detects SHN-only folders
Fixed: backend/app.py:4702: Added '.shn' to _AUDIO extension set in pipeline_scan_tree(); folders containing only SHN files were previously invisible to the scan and never added to the pipeline queue.

[2026-05-31] — feat(backend/scraper): setlist from LBBCD track table for all bootleg-CD entries
Added: backend/scraper.py: _extract_setlist_from_lbbcd() — queries bootleg_titles for lbbcd_id, parses cached LBBCD-{id}.html track table, formats numbered setlist with CD headers for multi-disc sets; always preferred over scraped free-text when LBBCD page exists; tries LBBCD-N.html then LBBCD-NNN.html (3-digit pad) to cover both naming conventions; bulk-applied to all 327 existing entries

[2026-05-31] — fix(backend/gui_next): qBt remove robustness + auto-detect manually removed torrents
Fixed: backend/qbittorrent.py: remove_torrent now accepts HTTP 204 as success (qBt 5+ compat); check_torrent_presence() added to detect absent torrents via /api/v2/torrents/info
Fixed: backend/app.py: qbt_remove route — if remove fails but torrent is already gone from qBt, clears DB flag anyway; added GET /api/torrent/<id>/qbt_check route for presence sync
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: fetchTorrentRecords auto-syncs qBt status on load — records marked "In qBt" that were manually removed now update without user action

[2026-05-31] — fix(gui_next): detail panel shows "No forum history" when forum API fails silently
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: initialize forumBusy=true; add forumError state; surface API failures as error message instead of "No forum history"; fix copy-paste bug (loadingTorrents key used in forum tab)
Added: gui_next/src/renderer/src/locales/*.json: loadingForum and forumLoadError i18n keys in all 6 locales

[2026-05-31] — fix(backend): forum post subject uses BOOTLEG title instead of location for BOOTLEG entries
Changed: backend/forum_poster.py: extracted _build_subject helper; uses entry["bootleg_title"] over location when present
Changed: backend/app.py: enrich entry dict with bootleg_title from bootleg_titles table before preview_forum / post_forum calls

[2026-05-31] — feat(gui_next): My Collection — remove fingerprint chips/column, add Post to forum button and right-click actions
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: removed Unconfirmed + No fingerprint filter chips and FP column; added Post to forum header button; added Post to forum / Create torrent / Add to qBittorrent to right-click context menu; all three actions work on multi-selected rows; context menu uses checked rows when the right-clicked row is among them

[2026-05-31] — feat(gui_next/backend): redesign Data Purges card — hierarchy, danger zone, recoverable-space signal
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: split PURGE_ITEMS into SCOPE_ITEMS + ALL_USER_DATA_ITEM; add PurgeRow + PurgeDangerZone sub-components; new card layout with subtitle, magnitude bars, hover-reveal red buttons, isolated danger zone, green archive callout
Changed: backend/app.py: purge_stats adds recoverable_bytes (sum of data/site/ + fingerprints.db disk usage)
Changed: gui_next/src/renderer/src/locales/en.json: add desc/unit strings and new card i18n keys for purges section

[2026-05-31] — refactor(gui_next): move row highlight colors checkbox from Setup to Themes page
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: add useSettingsStore + rowHighlight checkbox in Advanced card
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: remove rowHighlight state and checkbox JSX
Changed: gui_next/src/renderer/src/locales/en.json: add themes.advanced.rowHighlight key

[2026-05-31] — fix(gui_next): typeface Source Sans 3 not loading; font size selector had no effect
Fixed: gui_next/src/renderer/index.html: add IBM Plex Sans + Source Sans 3 to Google Fonts link (only Inter was loaded)
Fixed: gui_next/src/renderer/src/lib/tokens.ts: applyTheme now emits --lbb-fs-* CSS variables scaled by fontSize/13 for all 19 sizes in use
Changed: gui_next/src/renderer/src/ (23 files): replace 538 hardcoded inline fontSize literals with var(--lbb-fs-*) references so they respond to the font size setting

[2026-05-31] — feat(gui_next): global row highlight toggle in Preferences
Added: gui_next/src/renderer/src/store.ts: rowHighlight boolean (default true) + setRowHighlight action persisted in lbb-settings
Changed: gui_next/src/renderer/src/components/table.tsx: TR reads rowHighlight from store; when off, row background and left status bar both render transparent
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: "Row highlight colors" checkbox in Preferences card
Added: gui_next/src/renderer/src/locales/en.json: setup.preferences.rowHighlight key

[2026-05-31] — feat(gui_next): language selector in sidebar user chip
Added: gui_next/src/renderer/src/components/AppShell.tsx: globe+language-code button in sidebar footer; click opens popover with 6 language options; wired to existing useSettingsStore language/setLanguage

[2026-05-31] — feat(backend/gui_next): purge row counts in Data Purges panel
Added: backend/app.py: GET /api/purge/stats — returns row counts for rename_history, flat_file, scraper, fingerprint, and all-user-data groups
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: fetch purge stats on mount and after each purge; display count dimmed next to each item label

[2026-05-30] — fix(backend/gui_next): Attachments screen blank-white crash
Fixed: backend/app.py: added ef.downloaded to SELECT in attachments_cached — missing column caused IndexError → 500 → undefined total → toLocaleString() crash
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: setTotal(d.total ?? 0) to guard against backend error responses

[2026-05-30] — feat(gui_next/backend): DB stats on LB Crawler and Entry Metadata strip cards
Changed: backend/db.py: get_stats() now returns ok_entries and total_entries counts from entries table
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: LB Crawler card shows inventory URL count from /api/crawler/inventory/stats; Entry Metadata card shows ok_entries when idle, session progress when running

[2026-05-30] — feat(gui_next/backend): geocoder cache and coverage stats
Added: backend/app.py: /api/geocode/stats route — returns total_cached, geocoded, failed, manual, entries_total, entries_covered, pct_covered from location_geocoded and entries tables
Added: gui_next/src/renderer/src/screens/ScreenScraper.tsx: GeoStats interface, state, and fetch; GeocoderTab renders Cache Stats and Coverage StatGrids; strip card shows pct_covered and geocoded count

[2026-05-30] — fix(db): correct swapped columns in bobdylan_shows for 2046 pending rows
Fixed: data/losslessbob.db: bobdylan_url and date_str were swapped in 2046 rows inserted by older discover code; one-time UPDATE swapped them back so the scraper can fetch valid URLs

[2026-05-30] — fix(gui_next): remove duplicate AppShell nesting in Trading, Sharing, Scraper screens
Fixed: gui_next/src/renderer/src/screens/ScreenTrading.tsx: removed inner AppShell wrapper — App.tsx already wraps all routes in one, causing double sidebar + title bar
Fixed: gui_next/src/renderer/src/screens/ScreenSharing.tsx: same fix
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: same fix; deriveCrumbs already auto-resolves "LosslessBob / Curator / Scraper" from NAV_GROUPS

[2026-05-30] — fix(backend): replace inotify collection watcher with polling thread
Fixed: backend/scheduler.py: start_collection_watcher crashed at startup on systems where Electron exhausts the 128 inotify-instance limit; replaced watchdog Observer with a 60-second polling thread — no inotify usage, works on any system

[2026-05-30] — feat(backend/gui_next): archive.org upload integration on Sharing screen
Added: backend/archive_org.py: IA S3-like upload module — credentials test, stream-PUT per-file, thread-safe progress state, stop support
Added: backend/db.py: archive_org_uploads table + create_archive_upload / finish_archive_upload / get_archive_uploads functions
Changed: backend/credentials.py: added SERVICE_IA constant for archive.org keyring slot
Changed: backend/app.py: added 7 /api/archive_org/ routes (credentials CRUD+test, upload start/stop/status, history)
Changed: gui_next/.../ScreenSharing.tsx: added ArchiveOrgSection component — credential form, upload form with progress bar, history table
Changed: gui_next/.../locales/en.json: added archiveOrg translation namespace

[2026-05-30] — feat(backend/gui_next): collection trading + file sharing features (branch feat/trading-and-sharing)
Added: backend/sharing.py: ephemeral token-based share state, ZIP streaming, Cloudflare Tunnel lifecycle, expiry reaper daemon thread, HTML listing page renderer
Added: gui_next/.../ScreenTrading.tsx: friend collection import/export, diff compare, trading list export
Added: gui_next/.../ScreenSharing.tsx: create/revoke file shares, tunnel status banner, LAN + cloudflared modes
Changed: backend/db.py: added friend_collections + friend_collection_entries tables to _ensure_schema()
Changed: backend/app.py: added 5 /api/trading/ routes + 7 /api/share/ routes + sharing module import
Changed: gui_next/.../AppShell.tsx: added Trading and Sharing nav items under Library group
Changed: gui_next/.../App.tsx: registered /trading and /sharing routes + screen imports
Changed: gui_next/.../Icon.tsx: added trading and share icons
Changed: gui_next/.../locales/en.json: added trading and sharing nav labels

[2026-05-30] — feat(gui_next): ScreenScraper — full 6-tab scraper management screen
Added: gui_next/src/renderer/src/screens/ScreenScraper.tsx: new screen with status strip (all 6 scrapers at a glance), tab switcher, left controls + right live log panel per tab, session/scrape history tables; covers LB Crawler, Entry Metadata, Bootleg Catalog, Dylan.com, Setlist.fm, Geocoder
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen for /scraper route with ScreenScraper; added import
Changed: gui_next/src/renderer/src/index.css: added lbb-pulse and lbb-indeterminate CSS keyframe animations used by the scraper screen

[2026-05-30] — feat(backend): setlist.fm API integration
Added: backend/setlistfm.py: run_update(api_key, force) paginates /artist/{mbid}/setlists (~160 pages, ~0.55s/req); stores tour_name, venue, city, country, show info; setlist split by set_index/set_name/is_encore + song-level info/is_cover/cover_artist/is_tape; get_status()/stop()/save_api_key()/get_api_key() helpers
Added: backend/db.py: setlistfm_shows (PK setlistfm_id, date_str indexed, tour_name indexed) + setlistfm_setlist (PK setlistfm_id+position, set_index, track_name indexed); added to MASTER_TABLES; MASTER_SCHEMA_VERSION bumped to 5; setlistfm_api_key added to USER_META_KEYS
Added: backend/app.py: POST /api/setlistfm/key, /update, /stop + GET /api/setlistfm/key, /status, /show?date=YYYY-MM-DD, /stats

[2026-05-30] — feat(backend): bobdylan.com official setlist scraper
Added: backend/bobdylan_scraper.py: new module — fetch_sitemap_urls() discovers 4139 show URLs from 3 WordPress sitemaps; parse_show_page() parses venue/location/track list from each /date/ page; run_discover() upserts URL+date rows; run_scrape(force) scrapes unscraped pages; run_update(force) runs both idempotently; get_status()/stop() for progress/cancellation
Added: backend/db.py: bobdylan_shows table (bobdylan_url PK, date_str indexed) and bobdylan_setlist table (bobdylan_url+position PK, track_name, song_url); both added to MASTER_TABLES; MASTER_SCHEMA_VERSION bumped to 4
Added: backend/app.py: POST /api/bobdylan/update, /discover, /scrape, /stop + GET /api/bobdylan/status, /show?date=YYYY-MM-DD, /stats routes; join to entries/dylan_performances via date_str

[2026-05-30] — feat(gui_next/scraper): setlist file-name fallback + scrape always repopulates setlist
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: EntryDetailPanel setlist section falls back to entry_files list when no setlist available — shows track index, download status icon, and filename in monospace; Files section suppressed when fallback is active to avoid duplication
Changed: backend/scraper.py: setlist now always re-derived on scrape — if _is_setlist_para() finds nothing, falls back to extract_setlist_from_description() on the built description so a re-scrape never wipes a populated setlist

[2026-05-30] — fix(db/scraper/gui_next): setlist coverage 10% → 69% via backfill + scraper + parser fixes
Changed: backend/db.py: added _SL_DOT/_SL_NUM regexes; extract_setlist_from_description() — detects track-listing paragraphs via ≥3 dot/paren markers or num-only sequential pattern; init_db() migration setlist_backfill_v1 — one-time backfill of 9,794 entries using extract_setlist_from_description()
Changed: backend/scraper.py: replaced track_pattern bare-text-node-only detection with _is_setlist_para() helper (same two-pattern logic) applied to all <p> tags — future scrapes now correctly route track listings to setlist column
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: updated parseSetlist() to handle zero-padded numbers (01.), comma-separated dot format (1. Song, 2. Song), comma-separated num-only (1 Song, 2 Song), and space-separated num-only (1 Song 2 Song) formats; added normNum() to strip leading zeros

[2026-05-30] — feat(gui_next): setlist rendered as structured track table in entry detail panel
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: added parseSetlist() helper — detects inline format ("1. Song 2. Song …" all on one line) vs newline-separated format; splits inline format on /\s+(?=\d{1,2}[.)]\s)/ boundaries; parses each part with "N. Title" / "N) Title" regex into {kind:'track',num,title} items, other non-empty lines become section headers; replaced raw <pre> setlist block in EntryDetailPanel with a two-column table (track # | song title), header rows span columns; collapse defaults to first 12 items with "Show N more…" toggle; setlist label shows track count

[2026-05-30] — feat(db/scraper/gui_next): taper_name + source_chain columns extracted from description
Added: backend/db.py: extract_taper_and_source() — 14-step regex extractor covering Taper:/Recording:/Source:/Lineage:/BOOTLEG: labels, raw > chains, AUD DAT codes, short taper handles, legendary/NET taper patterns; ~80.5% coverage on 16k entries; two new TEXT columns taper_name + source_chain on entries table; ALTER TABLE migration with one-time backfill
Added: backend/scraper.py: compute taper_name/source_chain via extract_taper_and_source() on every scrape; included in INSERT OR REPLACE
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: Taper and Source columns in search table (toggleable, with col widths); taper/source rows in entry detail panel meta grid; SearchRow interface extended; CSV export updated

[2026-05-30] — feat(gui_next): best-per-date filter on Search screen
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: RATING_RANK constant; bestPerDate state; bestPerDateRows memo (keeps only highest-rated entry per unique concert date, pass-through for undated rows); "Best per date" checkbox in facet sidebar with description; filter chip in result strip; clearAll + hasActiveFilters wired to new toggle

[2026-05-30] — feat(backend/gui): FEAT-11 remote data ZIP retrieval
Added: backend/app.py: POST /api/data/download + GET /api/data/download/status routes; _do_data_download() background worker; _DATA_PROTECTED/EXTS guards; _data_dl_state + _data_dl_lock
Added: gui/setup_tab.py: Remote Data group — ZIP URL field, Download & Extract button, progress bar, _DataDownloadThread, polling logic

[2026-05-30] — feat(backend/gui): FEAT-10 GitHub auto-updater + enhanced About dialog
Added: VERSION: single source of truth for app version (1.2.0)
Added: backend/version.py: get_version() reads VERSION file; VERSION constant
Added: backend/updater.py: restart_application() — cross-platform process relaunch
Added: backend/app.py: GET /api/app/version, GET /api/update/check, GET /api/update/status, POST /api/update/apply; _do_update() background download+apply; github_repo/data_zip_url in settings keys
Changed: gui/main_window.py: VERSION now imported from backend.version; _on_about shows Python/PyQt6/Qt/platform info
Added: gui/setup_tab.py: Application Updates group — GitHub repo field, Check/Download/Restart buttons, progress bar, _UpdateCheckThread, _UpdateApplyThread

[2026-05-30] — feat(backend/gui): FEAT-09 collection folder integrity watchdog
Added: backend/db.py: log_integrity_event(), get_integrity_events(), ack_integrity_events() helpers
Added: backend/scheduler.py: _CollectionEventHandler + start_collection_watcher() — watches all my_collection disk_path dirs for deletions/moves
Added: backend/app.py: GET /api/integrity/events + POST /api/integrity/ack routes; call start_collection_watcher() at startup
Added: gui/main_window.py: yellow ⚠ alert label in status bar; click opens dialog listing events with Acknowledge All button
Cancelled: instructions/CC_INSTRUCTIONS.md: FEAT-06 (info.txt generator) marked cancelled

[2026-05-30] — feat(gui_next): finish wiring gaps — disambiguation panel, NFT suffix, Cache missing, queue location
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: added `candidates[]` to RenameRow; added NFT suffix logic (applyNftSuffix); replaced stub disambiguation panel with fully wired panel that fetches GET /api/folder_link + GET /api/lb_alias/resolve, shows LB candidate buttons, and wires Pin (PUT /api/folder_link), Unlink (DELETE /api/folder_link), and Standardize (GET /api/folder_naming/standard) actions.
Added: gui_next/src/renderer/src/locales/en.json: new i18n keys for rename.disambiguate (pin/unpin/loading/pinned/standardize) and rename.toast (pinned/unpinned/pinFailed/unpinFailed/standardized/standardizeFailed).
Added: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: "Cache missing" batch button — POSTs /api/entry/<lb>/scrape for each missing entry, shows progress, reloads tree on completion.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: wired "Open queue location" IconButton to openPath(parent of first queued folder).

[2026-05-29] — chore(deploy): switch Windows installer + portable to Electron/React (gui_next)
Changed: losslessbob_backend.spec: made cross-platform — Windows uses watchdog.observers.read_directory_changes, no fingerprinting stack, bundles shntool.exe; Linux keeps fingerprinting + inotify.
Changed: backend/paths.py: frozen Windows now uses %LOCALAPPDATA%\LosslessBob for data dir (backend binary lives inside resources/backend/ which is read-only in the installed app).
Changed: gui_next/package.json: added NSIS + portable Windows targets; file associations (.ffp/.md5/.st5); dist:win script.
Changed: gui_next/src/main/index.ts: packaged backend binary name is LosslessBobBackend.exe on Windows, LosslessBobBackend on Linux.
Changed: .github/workflows/release.yml: build-windows job now builds backend onefile → npm ci → copies binary to resources → electron-builder --win → uploads Setup.exe + portable.exe.

[2026-05-29] — chore(deploy): switch Linux AppImage to Electron/React (gui_next)
Changed: .github/workflows/release.yml: build-linux job now builds the backend as a PyInstaller onefile binary, bundles it as an Electron extraResource, and packages the gui_next Electron app as the AppImage via electron-builder instead of PyInstaller + manual AppDir.
Added: losslessbob_backend.spec: backend-only onefile PyInstaller spec (no PyQt6, no GUI); produces dist/LosslessBobBackend for bundling.
Changed: gui_next/package.json: added electron-builder ^25 devDependency + dist:linux script + build config (AppImage target, extraResources for backend binary).
Changed: gui_next/src/main/index.ts: ensureBackend() now branches on app.isPackaged — packaged mode spawns resources/backend/LosslessBobBackend, dev mode uses .venv/python3 as before.

[2026-05-29] — fix(backend): TOCTOU race + missing error guards in background task start routes
Fixed: backend/app.py: All four background-task start routes (spectrogram generate, fingerprint build, dup scan, identify-folder) had a TOCTOU race — the "already running" guard ran inside the lock but the thread started after the lock released, allowing concurrent requests to start two workers. Fixed by claiming status="running" inside the lock before releasing it. Guard widened from status=="running" to not-in-(idle, done, error) so the "scanning" phase is also covered.
Fixed: backend/app.py: Added top-level try/except to _do_fp_build, _do_fp_dup_scan, _do_fp_identify_folder, and _do_spectro_batch so that import failures or unexpected crashes reset status to "error" rather than leaving it permanently stuck at "running".

[2026-05-29] — feat(gui_next+backend): SQL query panel in DB Editor (TODO-101)
Added: backend/app.py: POST /api/dbedit/query — run arbitrary SQL, returns columns+rows for SELECT or rows_affected for DML; blocks DROP/TRUNCATE/VACUUM/ATTACH/DETACH
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: SqlQueryPanel component (textarea, Run/Clear, results table, status line with row count / error); toggle button in action row; Ctrl+Enter shortcut to run
Changed: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: added dbeditor.query.* keys

[2026-05-29] — feat(gui_next): ScreenDbEditor — full DB editor screen ported from legacy dbedit_tab
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: full DB editor screen with table browser, inline editing, pagination, sort, search, Commit/Discard/Delete/Export CSV, DB Integrity panel (reconcile, overrides, backup), and LB Aliases panel (curator-gated add/delete)
Changed: gui_next/src/renderer/src/App.tsx: wired ScreenDbEditor at /dbeditor, replacing PlaceholderScreen
Changed: gui_next/src/renderer/src/components/AppShell.tsx: moved DB Editor nav item from Curator group to Settings group (alongside Setup and Themes); Curator group now only contains Scraper
Changed: gui_next/src/renderer/src/locales/en.json: added dbeditor i18n section (80+ keys)
Changed: gui_next/src/renderer/src/locales/{de,es,fr,it,nl}.json: added dbeditor section (English placeholder text, ready for DeepL pass)

[2026-05-29] — chore(i18n): gui_next locale refresh — add 60 missing keys, DeepL fill all gaps
Added: .claude/commands/gui-next-i18n.md: new skill for React locale workflow (Step 1 count → Step 2 Qt port warning → Step 3 DeepL → Step 4 verify)
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: 60 new keys added (fingerprint, collection toast strings); ~582 strings per language translated via DeepL (57,254 chars total); 53 remaining gaps are intentional proper-noun/abbrev strings (Pipeline, LBDIR, LB#, etc.)
Changed: .claude/settings.local.json: DEEPL_API_KEY added to env block for future sessions

[2026-05-29] — feat(gui_next+backend): ScreenFingerprint — audio fingerprint match by date (TODO-106)
Added: gui_next/src/renderer/src/screens/ScreenFingerprint.tsx: new screen under Assets group; date picker finds collection entries for that date, builds LB fingerprints via existing /api/fingerprint/build, then identifies a user mystery folder; two-phase progress view; ranked results table; cleanup button; all strings wrapped with t() for i18n
Added: backend/app.py: GET /api/fingerprint/collection_by_date, POST /api/fingerprint/identify_folder, GET /api/fingerprint/identify_folder/status, POST /api/fingerprint/identify_folder/stop; _do_fp_identify_folder worker; _fp_id_state/_fp_id_lock/_fp_id_stop module-level state
Added: gui_next/src/renderer/src/components/Icon.tsx: fingerprint icon (scan-crosshair)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: Fingerprint nav item added to Assets group
Changed: gui_next/src/renderer/src/App.tsx: /fingerprint route registered
Changed: gui_next/src/renderer/src/locales/en.json: appShell.nav.fingerprint + full fingerprint i18n namespace

[2026-05-29] — docs: lock gui/ (PyQt6) as frozen; gui_next is sole development target
Changed: PROJECT.md: tech stack, architecture pattern, file structure, GUI strategy note, and change log all updated to reflect gui_next as the only active GUI; gui/ marked FROZEN

[2026-05-29] — feat(gui_next): DeepL machine-translation pass for all 5 gui_next locales
Added: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ~520 previously-untranslated strings (new GUI text with no Qt equivalent) translated via DeepL API; {{varName}} placeholders protected before transmission and restored after, 0 broken vars; coverage now 92–94% per locale
Added: scripts/deepl_translate_gui_next.py: one-off DeepL translation script (retranslates strings still identical to English or with broken {{var}} placeholders)

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in AppShell + ScreenHome
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added useTranslation to Sidebar, Topbar, StatusBar; wrapped appShell.* keys including brand, version, nav group/item labels (dynamic via item.id), curator badge/hint/enable, search placeholder, and status bar labels
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: added useTranslation; wrapped all home.* keys including collection title, DB status, buttons, hero card (with dangerouslySetInnerHTML for HTML desc), step strips, stats, jump tiles, recent activity table, tips, and all toasts

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in ScreenSetup + ScreenCollection; add TypeScript key safety
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: added useTranslation to ScreenSetup, CuratorToggle, IntegCard; wrapped all setup.* keys (database, masterData, integrations, torrent, preferences, purges, packages, flatFile, all toasts); added language selector to Preferences card bound to store.language/setLanguage
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: added useTranslation to 9 sub-components; wrapped all collection.* keys (PersonalInfoModal, ScanPreviewModal, AddFolderModal, ForumModal, DetailPanel, ConfirmDialogs, GlobalForumPanel, GlobalTorrentPanel, main table headers, all toasts)
Added: gui_next/src/renderer/src/i18next.d.ts: TypeScript CustomTypeOptions declaration for compile-time t() key safety
Added: gui_next/src/renderer/src/locales/en.json: added setup.toast.buildingArchive, setup.toast.noRecognisableFiles, setup.toast.scrapedExported keys

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in six screen files
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added useTranslation hook; wrapped all pipeline.* keys including header, status pills, bulk actions, queue rail labels, filter chips, selection bar, empty state, and table headers
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: added useTranslation to ScreenLookup and ListboxModal; wrapped all lookup.* keys including header, sources rail, status counters, summary/detail table headers, footer, and all toast messages
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: added useTranslation to ScreenRename and StateChip; wrapped all rename.* keys including header, state labels (in render), hints, bulk bar, table headers, disambiguate panel, dry-run banner, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: added useTranslation to ScreenVerify and StateBadge; wrapped all verify.* keys including header, rail, stats labels, toolbar, shntool warning, file-state pills, showing-problems text, table headers, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: added useTranslation to ScreenThemes and CustomTokenEditor; wrapped all themes.* keys including page title, mode/density/accent/typeface/advanced cards, token labels, preview section, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: added useTranslation hook; wrapped all map.* keys including header, filter rail labels, ownership buttons, display options, selected venue panel, entries section, and info hint

[2026-05-29] — fix(gui_next): embed real Leaflet map in ScreenMap
Changed: gui/resources/map.html: added postMessage listener (type:'applyFilters') so React panel can push filter updates without navigation; added ?embedded=1 support to hide the built-in filter bar when shown inside the Electron UI
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: replaced fake static canvas + hardcoded pin overlays with a live iframe pointing to http://localhost:5174/map?embedded=1; wired Apply filters, Reset to defaults, Copy share URL, and Open live map buttons

[2026-05-29] — fix(gui_next): HTML attachments blocked by CSP in iframe
Fixed: gui_next/src/renderer/index.html: added frame-src directive to CSP to allow iframes to load from http://127.0.0.1:5174; default-src 'self' was blocking HTML attachment previews with ERR_BLOCKED_BY_CSP

[2026-05-29] — feat(gui_next): integrations startup status check
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: added loadQbtStatus + loadWtrfStatus silent startup checks so integration cards show real status on mount without requiring a manual Test click; also fixes WTRF status label showing "error" instead of "not tested" when tone is warn

[2026-05-29] — fix(backend): all attachment entries shown as stale
Fixed: backend/app.py: attachments_cached omitted "downloaded" field from file objects; frontend stale check (f.downloaded === 1) saw undefined for every file and marked every entry stale.

[2026-05-29] — fix(gui_next): attachment viewer 404 for all file types
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: frontend was passing raw LBF-prefixed filename to /api/attachment route which queries by clean_name; changed to use clean_name || filename in both the text-fetch and fileUrl.

[2026-05-29] — chore: merge feat/gui-redesign → main (gui_next v1.0 complete)
Changed: PROJECT.md: gui_next marked as PRIMARY GUI, gui/ marked legacy/deprecated; Tech Stack updated
Note: All 14 gui_next screens now on main with full backend wiring; feat/gui-redesign branch retired

[2026-05-29] — feat(gui_next): wire ScreenPipeline Bulk actions menu (TODO-116)
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: inline popover on "Bulk actions" button with Select all visible, Clear selection (conditional), and Clear queue (destructive) — closes TODO-116

[2026-05-29] — feat(gui_next): shared folder queue across Pipeline and detail screens
Added: gui_next/src/renderer/src/lib/folderQueueStore.ts: new Zustand store holding the canonical folder list
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: addFolders/clearQueue syncs to folderQueueStore; useEffect picks up folders added from other screens
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: reads folders from folderQueueStore instead of verifyStore
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: reads folders from folderQueueStore instead of lbdirStore
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: reads folders from folderQueueStore; pending folders also routed through shared queue
Changed: gui_next/src/renderer/src/lib/verifyStore.ts: removed folders/setFolders (moved to folderQueueStore)
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: removed folders/setFolders (moved to folderQueueStore)
Changed: gui_next/src/renderer/src/lib/spectrogramStore.ts: removed folders/setFolders (moved to folderQueueStore)

[2026-05-29] — feat(backend+gui): data package restore from zip (TODO-104)
Added: backend/app.py: POST /api/package/restore — detects package type, dry_run preview, restores user_data or scrape_data, validates zip
Added: gui/setup_tab.py: _PackageRestoreThread; "Restore from Zip…" button; dry-run + confirm dialog flow; _set_pkg_buttons_enabled helper
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handleRestorePackage; ConfirmDialog conflict preview; "Restore from zip…" card in Data Packages SetupCard

[2026-05-29] — feat(gui_next): ScreenSetup — Data Packages card with user data and scraped site data export (TODO-102, TODO-103)
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: pkgBusy/pkgUserResult/pkgScrapeResult state; handleExportUserData and handleExportScrapeData handlers; "Data Packages" SetupCard with per-type sub-cards, inline result display (path, file count, size), and clickable path link

[2026-05-29] — feat(backend+gui+cli): data package export — user data and scraped site data (TODO-102, TODO-103)
Added: backend/app.py: POST /api/package/user_data — zips losslessbob.db + settings.ini + gui_state.json into data/exports/losslessbob_userdata_YYYY-MM-DD.zip with JSON manifest
Added: backend/app.py: POST /api/package/scrape_data — zips all of data/site/ into data/exports/losslessbob_sitedata_YYYY-MM-DD.zip with JSON manifest
Added: gui/setup_tab.py: _PackageUserDataThread, _PackageScrapeDataThread worker classes; "Data Packages" QGroupBox with Export User Data and Export Scraped Site Data buttons and result dialog
Added: cli.py: package user-data / package scrape-data subcommands with optional --out path

[2026-05-29] — fix(backend): guarantee ≥2 TCP trackers on every torrent (TODO-132)
Added: backend/torrent_maker.py: _FALLBACK_TCP_TRACKERS constant and _ensure_tcp_trackers() helper
Changed: backend/torrent_maker.py: make_torrent() calls _ensure_tcp_trackers() after fetch_trackers() so any chosen list always has at least 2 http/https trackers

[2026-05-29] — feat(gui_next): complete TODO-122, TODO-125..130 — ScreenCollection batch of improvements
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: sortable column headers (LB#, Status, Date, Location, Folder, Disk path, Confirmed, FP) with ▲▼ indicators (TODO-126)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: batch torrent-create and qBittorrent progress bar showing N/M live count (TODO-130)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: bulk Update Location — multi-row picks parent dir and scans for matching LB-XXXXX subfolders; single-row validates name against /api/folder_naming/standard/<lb> and toasts mismatches (TODO-125)
Added: backend/app.py: /api/collection/<lb>/audioinfo — probes FLAC/WAV with soundfile, falls back to ffprobe for SHN/APE; caches by mtime fingerprint; returns format, bit_depth, sample_rate, mixed (TODO-129)
Added: backend/app.py: /api/wishlist/<lb> PATCH — update priority/notes on a wishlist entry (TODO-122)
Added: backend/db.py: update_wishlist() function (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Wishlist filter view — extra Priority/Notes/Added/Rating columns with inline click-to-edit (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Duplicates filter view — grouped tree by show (date·location) with "Open on LosslessBob", "Open folder", and "Remove" actions per variant (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: detail panel fetches /api/collection/<lb>/audioinfo and displays real format·bit/rate pill (TODO-129)
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: detail panel Attachments → /attachments, Spectrograms → real handler, On map → /map (no more "coming soon" toasts) (TODO-128)
Changed: gui_next/src/renderer/src/components/table.tsx: TH now accepts onClick + sorted prop with ▲▼⇅ sort indicators
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: removed hardcoded "FLAC · 16/44" placeholder pill from detail panel (TODO-127)

[2026-05-29] — fix: resolve BUG-107, BUG-108, BUG-109
Fixed: backend/app.py: POST /api/lookup/scan_folders endpoint added — recursively finds checksum sidecar files (.ffp, .md5, .st5, .sha1) under given folders (BUG-109)
Fixed: backend/app.py: pipeline_scan_tree now checks root itself before rglob so flat folders with audio at the root level are included in results (BUG-108)
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: handleFolders calls scan_folders endpoint to populate source content, so folder sources work with "Lookup all sources" (BUG-109)
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: webUiTone converted to useState('ok') — badge now defaults to "connected" and reflects live test results instead of password config (BUG-107)

[2026-05-28] — fix(gui_next): Pipeline screen no longer loses state when navigating away
Fixed: gui_next/src/renderer/src/App.tsx: ScreenPipeline was unmounted by React Router on route change, wiping all useState (folders, queue, run status). Replaced the /pipeline Route with a KeepAlivePipeline wrapper that keeps the component permanently mounted and toggles visibility via display:none / display:contents.

[2026-05-28] — perf(gui_next): Collection screen now loads instantly on every visit
Added: backend/app.py: /api/collection/prefetch endpoint — bundles all 9 collection-screen datasets into a single HTTP response
Added: gui_next/package.json: @tanstack/react-query dependency
Changed: gui_next/src/renderer/src/App.tsx: wrapped app in QueryClientProvider; prefetch query fires at module load so cache is warm before user clicks Collection tab
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replaced version counter + 8-fetch Promise.allSettled + separate missing useEffect with a single useQuery (staleTime: Infinity); refetch now calls queryClient.invalidateQueries so mutations still trigger a reload

[2026-05-28] — fix(gui_next): Pipeline step pills now align under column headers
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: switched virtualizer from absolute-row to padding-based approach — absolute-positioned <tr> breaks table layout so colgroup widths don't apply to cells; replaced position:absolute+top with top/bottom spacer <tr> elements so real rows stay in normal table flow and the colgroup 110px step columns align correctly under their headers

[2026-05-28] — feat(gui_next): Pipeline live progress, column alignment, and Stop button
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: runSteps now processes folders one at a time (sequential fetch per folder) so each row updates as it completes; added stopRun + stopRef/abortRef to abort the in-progress run; StepPill accepts running prop and shows ··· in mute cells instead of — while processing; removed inline "running…" text from folder cell to restore column alignment; Stop button replaces Bulk actions in the top bar while a run is active

[2026-05-28] — chore(gui_next): dark mode palette shifted to neutral gray
Changed: gui_next/src/renderer/src/lib/tokens.ts: MODES.dark bg/surface/border/fg tokens replaced warm-brown values with flat neutral grays; mute status bg/fg/bar updated to match

[2026-05-29] — feat(gui_next): ScreenCollection — non-recursive Scan Directory + owned-aware ScanPreviewModal (TODO-124)
Added: backend/app.py: /api/pipeline/scan-dir route (POST {root, recursive}) — depth-1 or recursive walk matching LB-named folders; returns {entries: [{lb_number, folder_name, path}], skipped}
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: ScanPreviewModal component shows LB# / Folder / Path / Already Owned table (fetches /api/collection/lb_numbers for owned state), per-row Add buttons, and "Add all (N)" bulk action; handleScanDir (depth-1) and handleScanTree (recursive) are now distinct handlers both opening ScanPreviewModal; "Scan tree…" button wired to handleScanTree

[2026-05-29] — feat(gui_next): ScreenCollection — Notes column and editable Folder Name / Notes in AddFolderModal (TODO-123)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Notes column added to owned-collection table (reads c.notes from GET /api/collection); AddFolderModal FolderEntry now carries folderNameInput (editable, defaulted from path) and notesInput fields; both POSTed to /api/collection on add; colSpan updated 10→11 for virtualiser padding rows

[2026-05-29] — feat(gui_next): ScreenCollection — global Forum & Torrent History views + actionable per-row forum history (TODO-121)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: two new filter chips "All forum posts" (filter='forum_global') and "All torrents" (filter='torrent_global'); GlobalForumPanel renders GET /api/forum_posts with columns Posted/LB#/Show/Subject/Actions, actions: Open in Browser (window.open topic_url), Remove Record (DELETE /api/forum_post/<id> with confirm dialog), Go to LB (snaps back to 'all' filter and selects row); GlobalTorrentPanel renders GET /api/torrents with columns Created/LB#/Show/Filename/Status/Actions, actions: Add qBt (POST /api/qbt/add), Go to LB; both panels have a local search box; DetailPanel forum tab now fetches GET /api/entry/<lb>/forum_posts on open (like torrent tab) and shows per-post Open in Browser + Remove Record buttons with confirm dialog, replacing the old read-only pills

[2026-05-28] — feat(gui_next): ScreenCollection — per-torrent-record management in History tab (TODO-120)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: DetailPanel fetches GET /api/torrent/<lb> on open to load full TorrentRecord list; each record displays source-folder-exists and torrent-file-exists status dots; per-record action buttons: Add/Remove qBt, Regen (POST /api/torrent/create), Relocate Source (PATCH /api/torrent/<id>), Delete .torrent file (DELETE /api/torrent/<id>/file, with confirm dialog); forum tab unchanged; bottom "Regenerate" renamed to "Create torrent"

[2026-05-28] — feat(gui_next): ScreenCollection — personal rating, listen count, Log Listen in detail panel (TODO-119)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: DetailPanel fetches /api/collection/<lb>/meta on open; shows "My Rating" (personal_rating 1–5) and "Listens" (listen_count + last_listened) in meta grid; "Log Listen" button POSTs to /api/collection/<lb>/listen; "Edit Personal Info" button opens PersonalInfoModal from panel; saving via modal bumps personalSaveVer to refresh meta without full reload

[2026-05-28] — feat(gui_next): ScreenCollection — restore Missing (un-owned LB) view + CSV export (TODO-117)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: "Not in collection" chip backed by GET /api/collection/missing; separate table with LB# / LB Status / Date / Location / Rating / Description columns; Export CSV button; double-click row opens in Lookup
Changed: gui_next/src/renderer/src/components/table.tsx: added onDoubleClick prop to TR

[2026-05-28] — fix(gui_next): screen state lost on tab switch — move per-screen state to Zustand stores
Added: gui_next/src/renderer/src/lib/verifyStore.ts: Zustand store for ScreenVerify state (folders, results, activeIdx, showAll, filter) + exported types
Added: gui_next/src/renderer/src/lib/lbdirStore.ts: Zustand store for ScreenLBDIR state (all tab results, selections, filter, activeFolder)
Added: gui_next/src/renderer/src/lib/attachmentsStore.ts: Zustand store for ScreenAttachments persistent state (activeLb, search, statusFilter)
Changed: gui_next/src/renderer/src/lib/spectrogramStore.ts: extended with full screen state (folders, activeFolder, inventory, activeTrack, render settings, zoom); exported SpectroTrack type
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: added filter, filterMy, activeSource fields so Lookup UI state survives navigation
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: use useVerifyStore — folders/results/filter/selections persist across tab changes
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: use useLbdirStore — folders, results, tab, selections persist
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: use useSpectrogramStore — folders, inventory, active track, render settings persist
Changed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: use useAttachmentsStore — active LB, search, status filter persist
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: use lookupStore for filter/filterMy/activeSource

[2026-05-28] — fix(gui_next): CSP missing img-src for Flask origin — spectrogram PNGs broken
Fixed: gui_next/src/renderer/index.html: added img-src http://127.0.0.1:5174 to CSP so <img> tags can load spectrogram PNGs from Flask (connect-src alone does not cover image requests)

[2026-05-28] — feat(gui_next): spectrogramStore + context-menu navigate to Spectrograms screen
Added: gui_next/src/renderer/src/lib/spectrogramStore.ts: Zustand store for pending folder queue (addPending / takePending)
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: drain pending folders from store on mount, auto-select first added folder
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Generate Spectrograms context-menu action now seeds the store and navigates to /spectrograms

[2026-05-28] — feat(gui_next): row context menu + Personal Info modal in ScreenCollection (TODO-118)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: ContextMenu component (right-click on any row, ESC/click-outside to dismiss); 7 actions: Open Folder, View LB Entry, Scrape Entry, Fingerprint Folder, Play in VLC, Generate Spectrograms, Edit Personal Info
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: PersonalInfoModal with personal_rating 1-5 and tags fields backed by GET/POST /api/collection/<lb>/meta
Added: backend/app.py: POST /api/open/vlc endpoint — launches VLC via gui.platform_utils.open_in_vlc
Changed: gui_next/src/renderer/src/components/table.tsx: added onContextMenu prop to TRProps/TR

[2026-05-28] — feat(gui_next): finish ScreenCollection wiring + AppShell nav badge (TODO-115)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: fetch GET /api/home/stats on mount; show collection_count as live count badge beside "My Collection" nav item
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: add removeProgress state; render inline progress bar during batch-remove DELETE loop

[2026-05-28] — docs: log gui_next My Collection parity gaps as TODO-117..128
Added: TODO.md: 12 tasks (TODO-117..128) capturing old collection_tab.py vs new ScreenCollection.tsx
  feature gaps from parity audit — Missing/Wishlist/Duplicates views, global Forum/Torrent History,
  per-torrent-record mgmt, Personal Info, row context menu, Notes, scan preview, bulk relocate,
  sorting, cross-tab nav. All backing Flask endpoints confirmed present in backend/app.py.

[2026-05-28] — feat(gui_next): wire all stub screens + new backend routes (gap audit)
Changed: gui_next/src/renderer/src/screens/ScreenBootlegs.tsx: add toast; wire Refresh LBBCD response handler
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: add wishlist add/remove toggle in detail panel
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: full backend wiring — folder IPC, verify/generate/retrieve, tool dots
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: full backend wiring — check/retrieve/reconcile/extras panes
Changed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: full backend wiring — LB rail, file list, file viewer (text/html/image)
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: full backend wiring — inventory, generate/stop/poll, PNG display
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: full backend wiring — clipboard/listbox/files/folders sources, Zustand store
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: consume useLookupStore, wire Apply renames → POST /api/rename/apply
Added: gui_next/src/renderer/src/lib/lookupStore.ts: Zustand store (sources, summary, detail, folderList)
Added: backend/app.py: POST /api/rename/apply (shutil.move + write_rename_log per item)
Added: backend/app.py: GET /api/spectrogram/png (serve PNG by absolute path for viewer)
Added: gui_next/src/main/index.ts: dialog:pickAndReadFiles IPC (multi-select + read)
Changed: gui_next/src/preload/index.ts: expose pickAndReadFiles
Changed: gui_next/src/renderer/src/env.d.ts: add pickAndReadFiles type

[2026-05-28] — chore(docs): close PLAN_GUI_WIRING.md — all 6 sprints done
Changed: gui_next/PLAN_GUI_WIRING.md → instructions/complete/PLAN_GUI_WIRING.md: plan complete, moved to archive
Added: TODO.md: TODO-115 (ScreenCollection remaining 10%), TODO-116 (ScreenPipeline remaining 5% stub)
Changed: TODO.md / TODO_DONE.md: closed TODO-094 (UI redesign), swept Done entries (113/110/108) out of TODO.md

[2026-05-28] — chore(gui_next): wire ScreenSpectrograms into router
Changed: gui_next/src/renderer/src/App.tsx: import ScreenSpectrograms, replace PlaceholderScreen on /spectrograms route

[2026-05-28] — feat(gui_next): TODO-114 — port ScreenLBDIR from source JSX
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: four sub-tabs (Check/Retrieve/Reconcile/Extras), folder queue rail with state dots, per-file MD5+shntool detail table with side inspector, retrieve results table, reconcile rename proposals, extras deletion UI with controlled checkboxes
Changed: gui_next/src/renderer/src/App.tsx: wire /lbdir route to ScreenLBDIR, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-113 — port ScreenLookup from source JSX
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: sources rail (clipboard/listbox/files/folders), 5-state status counter bar (matched/incomplete/not-found/duplicate/xref), per-LB summary table with filterable state, per-checksum detail table, help banner, footer with Rename link and Confirm matches action
Changed: gui_next/src/renderer/src/App.tsx: wire /lookup route to ScreenLookup, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-112 — port ScreenRename from source JSX
Added: gui_next/src/renderer/src/screens/ScreenRename.tsx: 5 row states (has_lb/needs_rename/wrong_lb/multiple_ids/no_match), state filter chips, bulk action bar with checkbox selection, expandable disambiguation rows for multi-LB conflicts, dry-run banner
Changed: gui_next/src/renderer/src/App.tsx: wire /rename route to ScreenRename, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-111 — port ScreenSpectrograms from source JSX
Added: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: folder rail with batch progress, track rail with PNG inventory, spectrogram viewer (.lbb-spec-canvas), thumbnail strip, render options (width/height/dB floor/window), SHN skip warning

[2026-05-28] — feat(gui_next): TODO-110 — port ScreenVerify from source JSX
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: folder queue rail, 7-stat cards, MD5/FFP/ST5 detail table, shntool error state, per-file inspector panel
Changed: gui_next/src/renderer/src/App.tsx: wire /verify route to ScreenVerify, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-109 — port ScreenAttachments from source JSX
Added: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: three-column layout (LB rail, file list, viewer); viewer dispatches on kind: text/html/image/binary
Changed: gui_next/src/renderer/src/App.tsx: wire /attachments route to ScreenAttachments, replacing PlaceholderScreen

[2026-05-28] — feat(backend,gui): TODO-107 — master publish upload progress via GitHub REST API
Changed: backend/app.py: /api/master/github_release now streams SSE; replaces gh CLI subprocess with requests + gh auth token; uploads .db and manifest in 1 MB chunks with byte-accurate progress events
Changed: gui/setup_tab.py: _GithubReleaseThread consumes SSE stream; adds progress signal (label, pct); _on_publish_progress switches progress bar from indeterminate to determinate during upload

[2026-05-28] — feat(gui_next): TODO-108 — port ScreenMap from source JSX
Added: gui_next/src/renderer/src/screens/ScreenMap.tsx: filter rail (year range + decade chips, ownership toggle, LB status radio), static world map with absolute-positioned pin buttons, selected-venue side panel
Changed: gui_next/src/renderer/src/App.tsx: replace PlaceholderScreen with ScreenMap on /map route

[2026-05-28] — feat(gui_next): Sprint 6 — wire ScreenThemes (~44% → 100%)
Changed: gui_next/src/renderer/src/lib/tokens.ts: add Font/FontSize types, FONT_STACKS, FONTS/FONT_SIZES exports, DEFAULT_THEME export; extend ThemeOptions with font/fontSize/customTokens; update applyTheme to set --lbb-font and --lbb-font-size CSS vars and apply customTokens; update loadTheme to load/validate new fields
Changed: gui_next/src/renderer/src/index.css: font-family and font-size now driven by --lbb-font/--lbb-font-size CSS variables (defaults preserved in :root)
Added: gui_next/src/main/index.ts: dialog:saveFile IPC (showSaveDialog + writeFile) and dialog:pickAndReadFile IPC (showOpenDialog + readFile)
Changed: gui_next/src/preload/index.ts: expose saveFile and pickAndReadFile via contextBridge
Changed: gui_next/src/renderer/src/env.d.ts: add saveFile and pickAndReadFile to Window.api
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: typeface buttons wired (onClick setTweak font, active state, per-button font preview); font size 12/13/14pt buttons replace static text; Custom color tokens button toggles inline CustomTokenEditor (7 CSS tokens, color inputs, per-token reset, reset-all); Export JSON calls window.api.saveFile; Import JSON calls window.api.pickAndReadFile → parse/validate/apply; Toast component added
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 6 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 5 — wire ScreenBootlegs (79% → 100%)
Changed: gui_next/src/renderer/src/screens/ScreenBootlegs.tsx: Year filter popover (derived from loaded rows, sorted descending; active-highlight; outside-click close); CDs filter popover (All / 1 CD / 2 CDs / 3+ CDs; active-highlight; outside-click close); both wired into filteredRows useMemo and clearFilters; Export CSV button wired — Blob download of filteredRows as losslessbob_bootlegs.csv
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 5 marked done; audit table updated

[2026-05-28] — feat(gui_next,backend): Sprint 4 — wire ScreenHome to backend (70% → 100%)
Added: backend/app.py: GET /api/activity/log — unified activity feed from flat_file_releases, rename_history, forum_posts; supports ?limit= param
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: "Check for DB update" wired to /api/flat_file/discover with busy state + toast; "View full log" wired to open full-log modal fetching /api/activity/log?limit=0; Recent activity table renders real rows from /api/activity/log?limit=10 with colour-coded type dots; Toast component added; local fmtActivity + TYPE_COLOUR helpers
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 4 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 3 — wire ScreenSearch to backend (69% → ~95%)
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: all stubs wired; row click opens EntryDetailPanel fetching /api/entry/<lb> with description/setlist/files/scrape action; sort popover (6 client-side sort options, localStorage); CSV export via Blob download; Group-by-year toggle with active highlight; Columns visibility popover with localStorage persistence; Saved views (3 built-ins + user-created stored in localStorage with delete); owned field fixed — fetches /api/collection/lb_numbers on mount; per-row ⋯ menu (position:fixed, Scrape entry action); Toast component added
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 3 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 2 — wire ScreenCollection to backend (33% → 90%)
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: full rewrite; all 17 stubs wired; Export HTML/M3U blob downloads; Reveal on disk via openPath IPC; Remove with confirm dialog + DELETE /api/collection/<lb>; Add single folder via pickFolders → AddFolderModal with per-row LB# input; Scan directory/tree via pickDir → /api/pipeline/scan-tree → same modal; Update location via pickDir → PATCH /api/collection/<lb>; All years filter with popover dropdown from /api/search/years; Xref only checkbox from /api/checksums/xref_lb_numbers; Create torrent/Add to qBt header buttons act on checked/selected rows; Regenerate torrent and Post to forum (with BBCode preview modal) in detail panel; Attachments/Spectrograms/Map stub toasts; added lbNumberInt and isXref fields to CollectionRow; version-bump refetch pattern

[2026-05-27] — feat(gui_next,backend): IntegCard clear-credentials + DELETE credential endpoints
Added: backend/app.py: DELETE /api/credentials/qbt — removes qBt username/password and API key from keyring
Added: backend/app.py: DELETE /api/credentials/wtrf — removes WTRF credentials from keyring
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: IntegCard gains optional onClear prop; shows inline "Clear creds → Sure? / Yes, clear / Cancel" confirmation flow; handleQbtClear and handleWtrfClear handlers added

[2026-05-27] — fix(gui_next): ScreenSetup Integrations — Admin web UI card + Torrent Settings card
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: renamed "Torrent web UI" stub → "Admin web UI" (wired to /admin + web_password setting); added 4th "Torrent Settings" card with tracker list dropdown and Refresh Trackers button; added web_password/tracker_list to AppSettings interface; added handlers handleWebUiSave, handleWebUiTest, handleTrackerListChange, handleRefreshTrackers; Integrations grid changed from 3→4 columns

[2026-05-27] — feat(gui_next,backend): Sprint 1 — wire ScreenSetup to backend (6% → 100%)
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: full rewrite; all 16 stubs wired to Flask endpoints; real DB stats, master status, flat file history, helpers status loaded on mount; confirm dialogs, toast feedback, inline integration edit forms
Added: gui_next/src/main/index.ts: pickFile IPC handler (dialog:pickFile)
Added: gui_next/src/preload/index.ts: window.api.pickFile() bridge
Added: gui_next/src/renderer/src/env.d.ts: pickFile type declaration
Added: backend/app.py: POST /api/credentials/wtrf — save WTRF credentials to keyring
Added: backend/app.py: POST /api/credentials/qbt — save qBt credentials to keyring
Added: backend/app.py: POST /api/rename_history/purge — clear rename_history (lookup history)
Added: backend/app.py: POST /api/flat_file/purge — clear flat_file_releases + flat_file_changelog
Added: backend/app.py: POST /api/scraper/purge — clear scrape_sessions + site_inventory
Added: backend/app.py: POST /api/fingerprint/purge — delete fingerprints.db file
Changed: backend/app.py: /api/db/settings GET now includes data_dir in response
Changed: backend/app.py: /api/spectrogram/check GET now includes flac_available

[2026-05-27] — fix(gui_next): resolve TypeScript errors in ScreenPipeline and table components
Fixed: gui_next/src/renderer/src/components/table.tsx: added onClick to TDProps/TD and style to GroupRowProps/GroupRow
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: cast File to Electron-extended type with path property

[2026-05-27] — fix(gui,backend): master publish progress bar + timeout increase
Added: gui/setup_tab.py: indeterminate QProgressBar shown during export+upload, hidden on success or error
Fixed: backend/app.py: gh subprocess timeout raised from 120s → 600s (was hitting limit on large snapshots); error message updated to match
Fixed: gui/setup_tab.py: requests timeout raised from 150s → 660s to match backend

[2026-05-27] — fix(gui_next): fix Collection table column alignment with virtualizer
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replaced position:absolute rows with spacer-row pattern so tbody rows stay in normal table flow and colgroup widths apply correctly; widened Confirmed column from 90→160px

[2026-05-27] — fix(gui_next): auto-start Flask backend from Electron main process
Changed: gui_next/src/main/index.ts: spawn run_backend.py if port 5174 is not already open; wait for port before creating the window; kill child on quit

[2026-05-27] — feat(gui_next,backend): wire Collection screen to existing backend endpoints
Changed: backend/db.py: extend get_collection() SELECT to include e.description, e.rating, e.cdr
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replace single /api/collection fetch with Promise.allSettled of 6 existing endpoints (fingerprint/lb_numbers, wishlist, collection/duplicates, forum_posts, torrents); merge into CollectionRow[] client-side matching old GUI pattern

[2026-05-27] — fix(gui_next,backend): wire Pipeline folder-add, scan-tree, and Open actions
Fixed: gui_next/src/main/index.ts: add ipcMain.handle for dialog:pickFolders, dialog:pickDir, shell:openPath
Fixed: gui_next/src/preload/index.ts: expose pickFolders/pickDir/openPath via contextBridge
Fixed: gui_next/src/renderer/src/env.d.ts: add new methods to Window.api interface
Added: backend/app.py: POST /api/pipeline/scan-tree — walks root dir, returns subdirs containing audio files
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: wire "Add folders…" (×2) to pickFolders, "Scan tree…" (×2) to pickDir+scan-tree, "Open" to openPath

[2026-05-27] — feat(gui_next): Phase 4c — My Collection screen with virtualizer, filter chips, and detail panel
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: full Collection screen — heading row with export/qBittorrent buttons, stateful filter chips (All/Missing/Wishlist/Duplicates/Forum/Torrent/Unconfirmed/No FP), inline action toolbar, TanStack-virtualized 10-col table (edge bars, checkbox, LB#, Status, Date, Location, Folder, Disk path, Confirmed, FP), slide-in 360px detail panel (pill row, ID+title block, meta grid, action buttons, history sub-tabs); backend fetch against GET /api/collection with SAMPLE_DATA fallback
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen at /collection with ScreenCollection

[2026-05-27] — feat(gui_next): Phase 3 — curator mode toggle, Setup screen, and gated route guards
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: full Setup screen — Database card, Master Data card with animated curator toggle (44×24 knob, warn-tinted icon, persist via Zustand), Integrations card (3-col qBit/forum/web), Preferences card, Data purges card, Flat file history table
Changed: gui_next/src/renderer/src/App.tsx: /setup now routes to ScreenSetup; /dbeditor and /scraper wrapped in CuratorRoute guard (redirects to / when curatorMode is false); added Navigate import and CuratorRoute component

[2026-05-27] — feat(gui_next,backend): Phase 4a Pipeline screen — batch ingest workflow with virtualizer, selection, drag-drop, backend integration
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: full pipeline screen — top progress banner, folder queue rail, virtualised table (TanStack), filter chips, selection bar with shift-click/⌘A, drag-drop folder ingestion, per-row and bulk apply renames; calls POST /api/pipeline/run and POST /api/folder/rename
Added: backend/app.py: POST /api/pipeline/run — runs verify/lookup/rename/lbdir steps on a list of folders, returns PipelineRow-shaped results
Added: backend/app.py: POST /api/folder/rename — renames a folder on disk to a new name within the same parent directory
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen at /pipeline with ScreenPipeline
Added: gui_next/package.json: @tanstack/react-virtual ^3.13.26

[2026-05-27] — feat(gui_next,backend): Phase 4b Home/Dashboard screen wired to real backend data
Added: gui_next/src/renderer/src/screens/ScreenHome.tsx: full Home screen — welcome strip, hero ingest card with 4-step pipeline strip, At a glance stats, Jump to tiles, recent activity table (placeholder), Tips card; fetches /api/home/stats on mount
Added: backend/app.py: GET /api/home/stats — single-query route returning collection_count, wishlist_count, missing_count, bootleg_count, checksum_count, latest_lb, last_import
Changed: gui_next/src/renderer/src/App.tsx: replaced PrimitivesScreen at / with ScreenHome; import added

[2026-05-27] — feat(gui_next): Phase 2 app shell — Sidebar, Topbar, StatusBar, AppShell, Zustand settings store, react-router routing
Added: gui_next/src/renderer/src/store.ts: Zustand settings store with curatorMode persisted to localStorage
Added: gui_next/src/renderer/src/components/AppShell.tsx: Sidebar (224px, NAV_GROUPS, curator promo, user chip), Topbar (breadcrumbs, search, bell), StatusBar (DB stats), AppShell (composes all; reads active route from react-router, curatorMode from store)
Changed: gui_next/src/renderer/src/components/index.ts: barrel-export AppShell + AppShellProps
Changed: gui_next/src/renderer/src/App.tsx: replaced smoke-test root with HashRouter + AppShell + all 16 placeholder routes; PrimitivesScreen moved to /home route
Changed: instructions/gui_redesign/README.md: Phase 3 app shell marked ✅ Done; 3b curator mode marked 🔄 In Progress (gating works, toggle not in settings UI yet)
Changed: instructions/gui_redesign/13-implementation-plan.md: Phase 2 marked ✅ Done, Phase 3 promoted to NEXT
Verified: sidebar nav active-state, breadcrumbs, curator promo card, status bar — all confirmed via Firefox headless screenshots at /home and /pipeline routes

[2026-05-27] — feat(gui_next): Phase 1 primitives — Icon, Pill, Chip, Button, IconButton, Input, Kbd, Card, Toolbar, Banner, Stat, SectionHead, TableShell, TH, TR, TD, GroupRow
Added: gui_next/src/renderer/src/components/Icon.tsx: embedded LBB icon paths (Lucide-compatible), no added dependency
Added: gui_next/src/renderer/src/components/primitives.tsx: all 11 primitive components, full TypeScript prop types
Added: gui_next/src/renderer/src/components/table.tsx: TableShell+TH+TR+TD+GroupRow; TR injects 3px edge-bar <td> automatically
Added: gui_next/src/renderer/src/components/index.ts: barrel re-export of all components and types
Changed: gui_next/src/renderer/src/App.tsx: smoke-test UI exercises all primitives (stats, pills, buttons, input, table with edge bars and grouping)
Changed: instructions/gui_redesign/README.md: Phase 2 primitives marked ✅ Done
Changed: instructions/gui_redesign/13-implementation-plan.md: Phase 1 items 3-5 marked ✅ Done; Phase 2 marked 🔲 NEXT

[2026-05-27] — feat(gui_next): Phase 1 design tokens — theme engine, global CSS, font wiring
Added: gui_next/src/renderer/src/lib/tokens.ts: TypeScript port of lbb-tokens.js — applyTheme/loadTheme/saveTheme, 2 modes × 8 accents × 3 densities, status palette, full type exports
Changed: gui_next/src/renderer/src/index.css: replaced placeholder with full app.css port (scrollbars, sticky headers, focus rings, density rows, kbd-pill, spec/map canvas helpers)
Changed: gui_next/src/renderer/index.html: CSP widened for Google Fonts; Inter + JetBrains Mono preloaded
Changed: gui_next/src/renderer/src/main.tsx: applyTheme(loadTheme()) called before React.createRoot to prevent FOUC
Changed: gui_next/src/renderer/src/App.tsx: placeholder updated to smoke-test tokens (swatches, status pills, mode/accent/density toggles)

[2026-05-27] — feat(gui_next): replace PyQt6 scaffold with Electron + React + Vite + TS project
Changed: gui_next/: removed __init__.py and main_window.py (PyQt6 stub); replaced with full Electron+Vite project
Added: gui_next/package.json: Electron 42, React 18, Vite 7, electron-vite 5, TypeScript 5 — zero audit vulnerabilities
Added: gui_next/src/main/index.ts: Electron main process — 1440×900 window, loads Vite dev server in dev / built files in prod
Added: gui_next/src/preload/index.ts: contextBridge exposes flaskBase (http://127.0.0.1:5174) to renderer
Added: gui_next/src/renderer/: React+TS entry, placeholder App.tsx, index.css with LBB warm-cream base

[2026-05-27] — chore: create feat/gui-redesign branch and gui_next scaffold
Added: gui_next/__init__.py: new package for redesigned UI
Added: gui_next/main_window.py: stub MainWindow scaffold (same constructor interface as gui/)
Added: run_next.py: launcher for gui_next — shares Flask backend (port 5174) and DB; logs to losslessbob_next.log

[2026-05-27] — fix(backend): master update GitHub publish crash
Fixed: backend/db.py: generate_release_notes() called .get() on a sqlite3.Row (unsupported); changed to subscript access o["manual_notes"] which returns None for NULL, preserving the existing truthiness check

[2026-05-26] — feat(gui): add/remove override buttons in DB Integrity panel
Added: gui/dbedit_tab.py: "Add Override…" button opens a dialog (LB#, status dropdown, notes) and calls PUT /api/lb_master/<lb>/manual; "Remove Override…" prompts for LB# and calls DELETE /api/lb_master/<lb>/manual; both refresh integrity stats on success

[2026-05-26] — fix(db): startup crash on old DBs missing public_no_checksums column
Fixed: backend/db.py: moved idx_lb_master_public_no_chk index out of SCHEMA_SQL (which ran before the migration that adds the column) and into a post-migration CREATE INDEX IF NOT EXISTS call; fixes sqlite3.OperationalError on existing databases

[2026-05-26] — docs: add data_ownership.md explaining master vs. user data split
Added: docs/data_ownership.md: documents MASTER_TABLES, USER_TABLES, MASTER_META_KEYS, USER_META_KEYS, export/import enforcement, and schema versioning

[2026-05-26] — fix(backend): downgrade guard for master import; bundle shntool.exe on Windows

Fixed: backend/db.py: import_master_db() now raises ValueError if the incoming snapshot's
  master_version is older than the currently installed one, preventing accidental data loss
  from installing a stale file. (BUG-112)
Changed: backend/checksum_utils.py: _find_shntool() on Windows now checks the bundled
  PyInstaller path (_MEIPASS/tools/shntool.exe) and the dev-tree path
  (project_root/tools/shntool.exe) before falling back to WSL or PATH. (TODO-091)
Changed: losslessbob.spec: added tools/shntool.exe to datas so PyInstaller bundles it
  into the Windows distribution under _internal/tools/. (TODO-091)
Fixed: BUGS.md/BUGS_DONE.md: closed BUG-113 (hardcoded table backgrounds) — fully
  addressed by the theme-live refactor committed earlier today.

[2026-05-26] — refactor(gui): make all color lookups theme-live; no more stale QColor snapshots

Changed

  gui/lbdir_tab.py: Removed _C_PASS/_FAIL/_MISSING/_NO_LB/_GREY module-level aliases and
    class-level _LB_STATUS_COLOR dict. All call sites now reference styles.* directly so
    each paint picks up the current theme without any signal wiring.

  gui/verify_tab.py: Same pattern; 7 module-level aliases removed.

  gui/rename_tab.py: Removed module-level _STATE_COLORS and _NFT_DISC_COLORS dicts; data()
    builds inline dicts on each call.

  gui/attachments_tab.py: Removed class-level _STATUS_BG dict; data() uses inline lookup.

  gui/bootlegs_tab.py, gui/search_tab.py: Removed module-level _BG_STATUS string dicts;
    data() returns styles.ROW_PRIVATE/ROW_GREY directly. Unused QColor import removed.

  gui/collection_tab.py: Removed module-level _BG_LB_STATUS string dict; both model
    data() methods use inline lookup. Unused QColor import removed.

[2026-05-26] — refactor(gui): extend theme token vocabulary and eliminate all hardcoded hex colors

Changed

  gui/styles.py: Added 21 new module-level constants (ROW_FAIL, ROW_MISSING_FILE, ROW_GREY,
    ROW_PRIVATE, ROW_WRONG_LB, ROW_MULTIPLE_IDS, ROW_DIRTY, ROW_AUDIT, ROW_READONLY,
    ROW_NFT_MISSING, ROW_NFT_STALE, ROW_NFT_UNKNOWN, STATUS_OK, STATUS_WARN, STATUS_ERROR,
    STATUS_NEUTRAL, FG_MUTED, FG_LINK, FG_DANGER, FG_SUCCESS, FG_WARNING). All wired into
    apply_theme() with theme-dict keys; defaults are Light-theme values.

  gui/theme_tab.py: All 13 named themes updated with dark-adapted values for every new token.
    COLOR_LABELS extended with 21 new swatch entries so users can customise them.

  gui/lbdir_tab.py, gui/verify_tab.py: _C_PASS/FAIL/MISSING/NO_LB/GREY aliases now reference
    styles.ROW_OWNED/FAIL/MISSING_FILE/DUPLICATE/GREY. Danger/muted inline styles tokenised.

  gui/rename_tab.py: ROW_STATUS_COLORS and NFT_STATUS_COLORS dicts replaced with styles tokens.
    Legend swatches updated to use .name() from the same tokens.

  gui/dbedit_tab.py: _C_DIRTY/WARN/AUDIT/RDONLY lazy-aliased to styles row tokens.
    setForeground calls use FG_MUTED/FG_DANGER/FG_LINK.

  gui/spectrogram_tab.py: Drop-zone and hint labels use FG_MUTED; dup highlight uses ROW_FAIL.

  gui/scraper_tab.py: All Bootstrap status-color dicts use STATUS_OK/WARN/ERROR/NEUTRAL.
    Count labels use FG_MUTED.

  gui/setup_tab.py: Reset button uses FG_DANGER. All 19 tool-status setStyleSheet("color: X")
    calls replaced with FG_SUCCESS/DANGER/WARNING. Migration status uses STATUS_* tokens.

  gui/attachments_tab.py, gui/bootlegs_tab.py, gui/search_tab.py: private/missing color
    dicts consolidated to ROW_PRIVATE/ROW_GREY (previously duplicated in 7 files).

  gui/lookup_tab.py: lb_status colors use ROW_PRIVATE/GREY; warning row uses
    ROW_MISSING_FILE/FG_WARNING.

  gui/collection_tab.py: All foreground color calls replaced with semantic FG_* tokens.

[2026-05-26] — feat(map): add geocoding cache purge (TODO-097)

Added

  backend/app.py: POST /api/geocode/purge — curator-only route; scope="failed" deletes rows
    where source='failed' or lat IS NULL; scope="all" deletes entire location_geocoded table.
    Returns {ok, deleted}.

  gui/map_tab.py: _PurgeGeoThread — background worker calling /api/geocode/purge.
    Two new buttons in the Geocoding group (curator-only): "Purge Failed/Null" and
    "Purge All…" (requires confirmation). Status label shows deleted row count and
    prompts user to re-run geocoder.

[2026-05-26] — feat(setup): one-click master update from GitHub Releases (TODO-088)

Added

  gui/setup_tab.py: _GitHubMasterThread — fetches latest release via GitHub API,
    streams the .db asset with progress reporting, verifies SHA256, saves sidecar
    manifest to data/imports/, then applies via existing /api/master/import route.
  gui/setup_tab.py: "Check for Updates" button in Master Data section; progress label
    shows download %; _on_check_github/_on_github_progress/_on_github_done handlers.

Changed

  gui/setup_tab.py: Renamed "Install Master Update…" button to "Install from File…"
    for clarity now that the primary path is the GitHub download.

---

[2026-05-26] — feat(map): add lb_number column to location_geocoded for override traceability (TODO-099)

Added

  backend/db.py: Added lb_number TEXT column to location_geocoded schema; migration via
    ALTER TABLE with try/except-style PRAGMA guard for idempotency.
  backend/geocoder.py: place_manual() now accepts optional lb_number parameter; stored on
    INSERT and preserved (COALESCE) on UPDATE.
  backend/app.py: POST /api/geocode/location reads lb_number from body and passes to
    place_manual(). GET /api/geocode/locations now JOINs entries to return lb_numbers
    (comma-separated list of all LBs using each location string).
  gui/map_tab.py: Location Overrides table expanded to 8 columns with LB# column;
    _on_geo_row_dblclick() includes lb_number in POST payload when present.

Changed

  PROJECT.md: location_geocoded schema updated to include lb_number column.

---

[2026-05-26] — feat(search): Public / no checksums filter in Search tab (TODO-095)

Added

  gui/search_tab.py: New "Public / no checksums" option in the status filter combo.
    Filters search results to lb_status='public' entries where public_no_checksums=1,
    surfacing entries that have a known webpage but zero checksum records in the DB.

Changed

  backend/db.py: All SELECT branches in search_entries() and get_entries_by_lb_list()
    now include lm.public_no_checksums so the flag is present in every search result row.

---

[2026-05-26] — feat(db): Dylan performances promoted to MASTER; lb_problems table added (TODO-086, TODO-090)

Added

  backend/db.py: `lb_problems` table in SCHEMA_SQL (id, lb_number FK→lb_master, notes, notes, added).
    Indexed on lb_number. Added 4 DB functions: get_lb_problems(), add_lb_problem(),
    update_lb_problem(), delete_lb_problem(), get_lb_problem_count().

  backend/db.py: `dylan_performances` added to MASTER_TABLES (was unclassified/USER).
    `lb_problems` also added to MASTER_TABLES. MASTER_SCHEMA_VERSION bumped 2→3.

  backend/app.py: GET /api/performances — query dylan_performances by ?date=, ?lb= (auto-resolves
    entry date_str to ISO), ?category=, with pagination.

  backend/app.py: GET /api/lb_problems, POST /api/lb_problems (curator-only),
    PUT /api/lb_problems/<id> (curator-only), DELETE /api/lb_problems/<id> (curator-only).

---

[2026-05-26] — fix(scraper): "Scrape All Missing Entries" no longer queues private LBs (TODO-100)

Fixed

  backend/app.py (/api/scrape/start): Build the scrape list with a LEFT JOIN to lb_master and
    exclude rows where lb_status = 'private'. Private LBs are handled exclusively by
    /api/scrape/private_rescrape ("Re-scrape Private LBs" button) to prevent the two actions
    from overlapping. Updated docstring to document the exclusion.

---

[2026-05-26] — fix(gui): curator panels not shown on map tab at startup if curator mode already enabled (BUG-109)

Fixed

  gui/main_window.py: curator_mode_changed fires during SetupTab.__init__ (via _load_curator_status)
    before MapTab is created and before the signal connection is wired. Added a one-shot
    set_curator_mode(curator_cb.isChecked()) call immediately after connecting the signal so the
    map tab reflects the persisted curator state on every startup, not just after toggling. (BUG-109)

---

[2026-05-26] — fix(gui): AppImage open-folder fix (BUG-110) + BUG-111/115/107 housekeeping

Fixed

  gui/platform_utils.py: open_folder() and open_file() on Linux now call
    QDesktopServices.openUrl(QUrl.fromLocalFile(p)) instead of subprocess.run(["xdg-open", ...]).
    In AppImage environments the modified PATH may hide system xdg-open; QDesktopServices
    is Qt-native and handles file-manager launch reliably regardless of PATH. xdg-open kept
    as a fallback if QDesktopServices returns False. (BUG-110)

  gui/setup_tab.py: _on_open_folder: replaced silent except Exception: pass with
    _log.warning() so failures are visible in the log rather than silently discarded. (BUG-110)

  backend/app.py: (previously fixed, now documented) The allowed_dirs containment check
    ("Snapshot must be in data/exports/ or data/imports/") was removed from
    /api/master/import. The route now accepts any readable .db file. (BUG-111)

Changed

  BUGS.md: moved BUG-110, BUG-111, BUG-115, BUG-107 (all Fixed) to BUGS_DONE.md.

[2026-05-26] — feat(db): lb_missing table (TODO-102) + public_no_checksums flag (TODO-098) + nonexistent status

Added

  backend/db.py: lb_missing table (INTEGER PK, confirmed_date, notes) — MASTER_TABLE seeded
    with 36 confirmed-not-existing LB numbers on init_db(). _LB_MISSING_SEEDS constant.
    is_lb_missing / add_lb_missing / remove_lb_missing / get_lb_missing_list CRUD functions.

  backend/db.py: public_no_checksums column on lb_master (INTEGER NOT NULL DEFAULT 0) and
    partial index idx_lb_master_public_no_chk. Set to 1 when lb_status='public' AND
    has_checksums=0 across all reconcile paths. Count exposed in get_lb_master_stats.

  backend/db.py: 'nonexistent' added as a 4th valid lb_status value (via table recreation
    migration that also adds public_no_checksums). lb_missing entries are classified
    'nonexistent' by all reconcile paths.

  backend/scraper.py: scrape_entry() returns {skipped, reason='nonexistent'} for lb_missing
    entries before any network or DB work.

  backend/app.py: GET/POST /api/lb_missing, DELETE /api/lb_missing/<lb> routes.

  tests/test_db_writes.py: TestLbMissing (8 tests) + TestPublicNoChecksums_Flag (6 tests).
    Total test count: 121 → 135.

[2026-05-26] — fix(db): reconcile_all_lb_master bails early when checksums table is empty (BUG-116b)

Fixed

  backend/db.py: reconcile_all_lb_master now includes MAX(entries.lb_number) when computing
    effective_max, so a fresh install with scraped entries but no checksums no longer short-
    circuits and leaves public-page LBs unclassified.

Added

  tests/test_db_writes.py: test_reconcile_all_no_checksums_public_entry regression test in
    TestPublicNoChecksums — seeds LB-1506 as status='ok' with no checksums, calls
    reconcile_all_lb_master, and asserts lb_status='public'.  All 6 tests in the class pass.

[2026-05-25] — test(db): add regression tests for public-page LB with no checksums (BUG-116)

Added

  tests/test_db_writes.py: TestPublicNoChecksums — 5 tests covering reconcile_lb_status,
    batch_reconcile_lb_status, missing→public transition, get_missing_lb_numbers exclusion,
    and _compute_lb_status(True, False, False) unit check.  All pass; regression guard for
    BUG-116 (reconcile_all_lb_master edge case with zero checksums remains open).

[2026-05-25] — fix(scraper): batch-repair 61 missing entries that had locally cached pages

Fixed

  backend/scraper.py / data: Ran scrape_entry(use_local_pages=True) over all 103 missing
    lb_master entries.  61 had locally cached pages with real content (saved by
    download_pages_range but never parsed after the entry was marked missing).  All 61 now
    have lb_status='public' with parsed metadata.  42 remain missing (no local page);
    a live network scrape will re-check those automatically with the new skip-logic fix.

[2026-05-24] — fix(geocoder): bump performances-sourced confidence from low → medium

Fixed

  backend/geocoder.py: After setting source='performances', promote confidence 'low' → 'medium'
    because Nominatim's importance score penalises specific venues (stadiums, conference centres)
    even when the structured venue+city+state+country query is accurate.  The label 'low' was
    misleading for geocodes that are correct.
  backend/db.py: One-time migration to retroactively fix existing location_geocoded rows where
    source='performances' AND confidence='low'.

[2026-05-24] — fix(scraper): live scrapes now re-check entries previously marked missing

Fixed

  backend/scraper.py: Skip condition for `status='missing'` entries changed from
    `not (use_local_pages and local_page.exists())` to `use_local_pages and not local_page.exists()`.
    Old logic always skipped missing entries during live network scrapes, so pages added to the
    archive after the initial scrape were never rediscovered.  New logic: live scrapes always
    re-fetch missing entries from the server; local-page mode skips only when no local file exists.
    LB-05126 was repaired in-place by re-scraping from its locally cached page (now public, 10/12/89).

[2026-05-24] — fix(db): rewrote DatabaseWriteQueue._worker — isolation_level=None, explicit BEGIN/COMMIT/ROLLBACK, startup ready-event; fixed implicit transaction leak in init_db(); added conftest.py test isolation fixture; updated stale TestWriteConnectionRollback tests

Changed

  backend/db_queue.py: _run() now opens the writer connection with isolation_level=None so
    Python's sqlite3 module never issues implicit BEGIN/ROLLBACK of its own. Transaction
    boundaries are fully explicit: BEGIN before fn(), COMMIT on success, ROLLBACK on error.
    Removed PRAGMA busy_timeout=0 — contention on the single writer is a bug, not a condition
    to mask with a timeout. Increased cache_size to -32000 pages. Added a _ready Event so
    __init__() blocks until the writer has finished its PRAGMA setup (including
    journal_mode=WAL) before returning — eliminating the race between the writer thread and
    init_db()'s get_connection() call on a brand-new database file. shutdown() now also closes
    the writer connection after the thread joins.

  backend/db.py: init_db() now calls conn.commit() unconditionally after the soft-404 UPDATE,
    regardless of rowcount. Previously a zero-row UPDATE left an implicit Python transaction
    open on the read connection, holding a RESERVED lock that blocked the write queue's first
    transaction on every fresh (empty) database.

  conftest.py (new): autouse pytest fixture that shuts down and resets the DatabaseWriteQueue
    singleton and thread-local read connections between every test, preventing the singleton
    from routing writes to the first test's database file in subsequent tests.

  tests/test_db_writes.py: TestWriteConnectionRollback updated to use get_write_queue().execute()
    instead of the removed db.write_connection() context manager.

Fixed

  backend/db_queue.py: "database is locked" OperationalError in site_crawler and
    lb_master_reconcile caused by BEGIN IMMEDIATE competing with Python's implicit transaction
    management on the same connection.

[2026-05-24] — feat(geocoder): performances-table lookup before Nominatim geocoding (TODO-087)

Changed

  backend/geocoder.py: run_batch() now checks dylan_performances for each location before
    calling Nominatim. _entry_date_to_iso() converts M/D/YY entries.date_str to YYYY-MM-DD;
    _get_performance_location_string() scans associated dates and returns a structured
    "venue, city, state, country" query string. If a match is found, that string is geocoded
    and stored with source='performances' + note showing the derived query for provenance.
    Falls back to the raw entries.location text when no performance record exists.
    UPSERT now keys by the raw location text (not the geocode input) so the existing
    map JOIN (entries.location = geo.location_text) remains intact.

Added

  backend/db.py: get_performance_by_date(date_str) — public helper returning the
    dylan_performances row for an ISO date string; logs a warning on rare same-date doubles.

[2026-05-24] — fix(fingerprint): emit scan-progress updates so UI shows activity during initial folder scan

Fixed

  backend/fingerprint.py: build_fingerprint_db() now emits status="scanning" with folder
    progress every 50 rows during the initial file-collection phase, so the GUI label
    updates from "[0/0]" instead of appearing frozen during large collection scans.

  gui/spectrogram_tab.py: _on_fp_build_status() handles status="scanning" by updating
    the build label and returning early (no queue/count changes during scan phase).

---

[2026-05-24] — fix(attachments): route _RefreshTreeThread through Flask API to fix "database is locked" (BUG-114)

Fixed

  gui/attachments_tab.py: Removed direct get_connection() calls from _RefreshTreeThread.
    Thread now calls POST /api/attachments/reconcile then GET /api/attachments/cached via
    HTTP (requests). Removed the backend.db import entirely. Constructor now takes flask_port.

Added

  backend/app.py: POST /api/attachments/reconcile — runs the UPDATE entry_files SET
    downloaded=1 reconcile query inside Flask's connection and returns {updated: N}.
    GET /api/attachments/cached — returns grouped entry_files data + total checksums count
    as {entries: [...], total: N}, replacing the in-thread SELECT.

[2026-05-24] — fix(gui): switch QT_QPA_PLATFORM to wayland, fixing BUG-090 black screen flickers

Fixed

  main.py: default QT_QPA_PLATFORM changed from "xcb" to "wayland" on Linux. Running under
    XWayland was causing intermittent black screen flickers due to compositor interaction with
    Qt's rendering pipeline. Native Wayland eliminates the issue. User env override still honoured.

[2026-05-24] — feat(fingerprint): fingerprinting queue preview with prominent progress counter and up-next list

Added

  backend/fingerprint.py: queue_preview state key — build_fingerprint_db() now emits the next 10 filenames
    (relative "parent/name" form) after the current position on every state update, clearing to [] when done.

  backend/app.py: GET /api/fingerprint/build/queue endpoint returning {pending: N, preview: [...]}.
    queue_preview added to _fp_build_state initial dict so /api/fingerprint/build/status also carries it.

  gui/spectrogram_tab.py: Fingerprint DB sub-tab now shows a bold "X of Y" count label and a QListWidget
    (≤15 rows, "Up next:" header) that updates every 800 ms during a build. _FpBuildStatusThread.run()
    fetches both /status and /queue per tick and merges results into a single emitted dict.

---

[2026-05-24] — feat(collection): add "Play in VLC" context menu action for My Collection entries

Added

  gui/platform_utils.py: open_in_vlc(paths) — cross-platform VLC detection (PATH, common Windows/macOS install
    locations) and subprocess launch. Returns (bool, error_msg) so callers can surface failures gracefully.

  gui/collection_tab.py: "Play in VLC" context menu item in My Collection. Enabled when selected row(s) have a
    valid disk_path on disk. Multiple rows pass all their folder paths to one VLC instance as a playlist.
    Shows a QMessageBox.warning if VLC is not found rather than silently failing.

---

[2026-05-24] — DB-09: Replace ad-hoc write_connection() locking with DatabaseWriteQueue

Changed

  backend/db_queue.py: New module. DatabaseWriteQueue holds ONE persistent sqlite3 connection
    and serialises every write via queue.Queue + threading.Event. All callers call
    get_write_queue().execute(fn) or .execute_async(fn); fn(conn) runs exclusively in the
    single writer thread — eliminating all concurrent-writer races under WAL mode.
  backend/db.py: All write_connection() call sites migrated to get_write_queue().execute();
    write_connection() removed. _write_lock retained only for import_master_db() ATTACH/DETACH
    workflow. Singleton initialised inside init_db().
  backend/scraper.py: Five write_connection() call sites replaced with get_write_queue().
    PRAGMA optimize kept as direct get_connection() op (not DML, no lock needed).
  backend/site_crawler.py: One write_connection() call site replaced.
  backend/app.py: Two database.write_connection() calls (dbedit row update/delete) replaced;
    rowcount returned through queue result box.
  backend/importer.py: Chunked executemany merge submitted as single queue item (timeout=300s).
  backend/flat_file.py: All four write functions (discover, download, apply, defer) routed
    through write queue. apply_flat_file_release() pre-computes all mutations as Python lists
    and submits one atomic executemany batch; set_meta calls follow after queue item commits.
  backend/geocoder.py: save_manual_geocode() and per-iteration run_batch() writes routed
    through write queue.

Fixed

  sqlite3.OperationalError: database is locked — root cause was multiple threads opening
    concurrent write_connection() calls, each racing for the WAL write lock. The write queue
    removes the race entirely.

[2026-05-23] — fix(db): use BEGIN IMMEDIATE in write_connection to prevent database-locked race

Fixed

  backend/db.py: write_connection() now issues BEGIN IMMEDIATE before yielding, acquiring
    the WAL write lock before any reads. Prevents SQLITE_BUSY when out-of-band writers
    (e.g. PRAGMA optimize/ANALYZE from scraper) hold the SQLite write lock after reconcile
    has already completed its read phase. Nested calls detect conn.in_transaction=True and
    skip inner BEGIN/COMMIT so the outermost call owns the transaction.
  backend/scraper.py: PRAGMA optimize at end of scrape_range moved into write_connection
    so it goes through _write_lock instead of competing with other writers outside Python's
    serialisation layer.

[2026-05-23] — fix(scraper): eliminate 15 s startup block from synchronous HTTP calls in ScraperTab

Fixed

  gui/scraper_tab.py: Three methods (_load_crawler_settings, _load_sessions_history,
    _load_bootlegs_history) were making synchronous requests.get/post calls on the main Qt
    thread, each with a 5 s timeout. Additionally, _load_crawler_settings was triggering
    _save_crawler_settings and _save_entry_settings via valueChanged/stateChanged signals as it
    set widget values, causing further blocking POSTs. Combined effect: ~15 s startup freeze.
    Fix: all three methods now fire a _Worker thread and populate widgets via finished signal.
    _load_crawler_settings uses blockSignals() while applying loaded values to suppress the
    spurious save cascade.
  gui/scraper_tab.py: _refresh_pages_count() was also calling glob("*.html") synchronously.
    Replaced with os.scandir() in a _Worker thread (contributing fix from previous attempt).

[2026-05-23] — fix(db): reconcile_all_lb_master uses batch write to fix database-locked error

Fixed

  backend/db.py: reconcile_all_lb_master() replaced per-LB reconcile_lb_status() loop
    (acquires/releases _write_lock N times) with a single batch_reconcile_lb_status() call,
    eliminating the sqlite3.OperationalError: database is locked caused by concurrent writers
    fighting over the lock across thousands of iterations.
  backend/app.py: /api/lb_master/reconcile route now holds _reconcile_lock (non-blocking
    acquire) and returns 409 if a reconcile is already in progress, preventing two simultaneous
    reconcile requests from interleaving writes.

[2026-05-23] — feat(db): import dylan_performances table from ODS on first startup

Added

  backend/db.py: new dylan_performances table (event_id PK, date_str, category, city,
    state, country, venue) added to SCHEMA_SQL with indexes on date_str, category, country.
  backend/db.py: import_dylan_performances() function — one-time ODS parser using stdlib
    zipfile + ElementTree; skips if table already populated; wired into init_db() background
    thread. Source file: data/2026-05-22_Dylan_Performance_fixed.ods (5,129 rows).

---

[2026-05-23] — feat(db): flat_file_apply inserts new LBs as 'public' instead of 'private'

Changed

  backend/db.py: reconcile_lb_status() and batch_reconcile_lb_status() now initialise
    brand-new lb_master rows to 'public' when trigger='flat_file_apply' and the computed
    auto_status would have been 'private' (checksums-only, no web presence). The scraper
    can still demote to 'private' after it confirms no web entry exists. Existing rows
    and any other trigger are unaffected.

[2026-05-23] — feat(map): display LB number on individual map dots

Changed

  gui/resources/map.html: Replaced L.circleMarker with L.divIcon + L.marker so each
    single-concert dot renders the LB number as centred text inside the coloured circle.
    Visual style (colour, owned gold ring, shadow) is preserved.

[2026-05-23] — fix(scraper): detect soft-404 pages (server returns HTTP 200 with error body)

Fixed

  backend/scraper.py: Added _SOFT_404_MARKER constant and _is_soft_404() helper.
    scrape_entry() now checks the HTML content for the server's soft-404 signature
    before parsing; treats it as a true 404 (deletes bad cached page, marks entry
    missing, returns {"error": "404", "missing": True}).

  backend/db.py: init_db() now runs a one-time cleanup UPDATE that finds existing
    entries whose description contains the soft-404 error text and resets them to
    status='missing' with cleared fields. Rebuilds the FTS index afterwards if any
    rows were affected. 68 previously bad entries will be fixed on next app start.

[2026-05-23] — feat(gui): platform-aware install hints for SoX, ffmpeg, shntool (TODO-086)

Changed

  gui/setup_tab.py: Added _sox_tool_hint() static helper that returns an HTML
    install hint (with clickable download link) for each external tool based on
    sys.platform — winget commands on Windows, brew on macOS, apt on Linux.
    SoX, ffmpeg, and shntool status labels now use RichText format with
    setOpenExternalLinks(True) so links are clickable. Windows shntool hint
    notes no native package and suggests WSL or Chocolatey as alternatives.
  backend/sox_utils.py: Replaced hard-coded Linux install commands in
    SoxNotFoundError, ConversionError (ffmpeg missing), and SpectrogenError
    (PNG support missing) with dict-based platform lookups covering win32,
    darwin, and Linux defaults.

[2026-05-23] — docs(backend): update stale docstrings referencing old data/pages/ and data/attachments/ paths

Changed

  backend/scraper.py: Updated download_pages_range docstring — save path is now
    data/site/detail/LB-{n:05d}.html (was data/pages/).
  backend/app.py: Updated /api/download-pages docstring and _start_scrape_thread
    docstring to reference data/site/detail/ instead of data/pages/.
  backend/forum_poster.py: Updated three attachments_dir parameter docstrings
    to reference data/site/files/ instead of data/attachments/LB-XXXXX/.

[2026-05-23] — fix(backend): fix master DB install failing with "internal_error" on Windows (BUG-105)

Changed

  backend/app.py: Removed is_curator() guard from master_import route — export stays
    curator-only but import is open to all (design intent: "Curator publishes, end users
    install"). Removed the path_not_allowed directory-containment check that blocked
    selecting a snapshot from outside data/exports/ or data/imports/ (e.g. USB drive or
    Downloads folder); kept the .db suffix check. Added sqlite3.Error to the caught
    exception list so SQLite failures (ATTACH, VACUUM INTO backup, table operations)
    surface a real error message instead of bare "internal_error". Added "message" field
    to the generic internal_error response. Added import sqlite3 at module level.

[2026-05-23] — fix(db): serialise upsert_inventory writes through _write_lock to prevent DB locked errors

Fixed

  backend/db.py: upsert_inventory() was calling get_connection() directly and committing
    outside the _write_lock, allowing concurrent Flask/crawler writes to race. Swapped to
    write_connection() context manager so all writes go through _write_lock.
  backend/site_crawler.py: inline entry_files downloaded=1 update also used get_connection()
    directly; swapped to write_connection(). Replaced now-unused get_connection import with
    write_connection.

[2026-05-23] — feat(release): add Docker image build and push to GHCR in release workflow

Added

  .github/workflows/release.yml: build-docker job — logs in to ghcr.io with GITHUB_TOKEN,
    uses docker/metadata-action to tag semver + sha + latest (latest only on tag pushes),
    builds with docker/build-push-action and GHA layer cache.
  .github/workflows/release.yml: added packages: write to top-level permissions so
    GITHUB_TOKEN can push to GitHub Container Registry.
  .dockerignore: added secrets/ so credential files are never copied into the image.

---

[2026-05-23] — docs(website): remove macOS install option, add Docker install card

Changed

  docs/index.html: removed macOS install card; added Docker card (docker compose up → noVNC at
    localhost:6080); updated hero platforms line (macOS → Docker); updated og:description;
    updated install section subtitle to reflect Docker as a no-Python-required option.

---

[2026-05-23] — feat(docker): Docker secrets support for pre-loading credentials in containers

Added

  backend/credentials.py: _SECRET_MAP, _read_docker_secret(), _get_from_docker_secrets()
    — get_credentials() now falls back to /run/secrets/ files after keyring; credentials_stored()
    checks secrets too. Mapping: SERVICE_QBT → qbt_username/qbt_password,
    SERVICE_QBT_KEY → qbt_apikey_user/qbt_apikey, SERVICE_WTRF → wtrf_username/wtrf_password.
  docker-compose.yml: secrets: block wires six secret files into the container; comments
    explain how to copy .example files and fill in values.
  secrets/: empty *.txt files (git-ignored) and *.example templates for all six secrets.
  .gitignore: secrets/*.txt excluded to prevent accidental credential commits.

---

[2026-05-22] — feat(docker): add Docker + noVNC support for browser-based GUI access

Added

  Dockerfile: single-stage build on python:3.11-slim; installs Xvfb, x11vnc, noVNC,
    websockify, SoX, and all Qt6/Chromium runtime libs; sets QTWEBENGINE_CHROMIUM_FLAGS
    --no-sandbox so QtWebEngine works in unprivileged containers.
  docker/entrypoint.sh: starts Xvfb :1 → x11vnc → websockify/noVNC on port 6080 →
    launches the app; users open http://localhost:6080 in a browser.
  docker-compose.yml: maps port 6080, named volume for data/, shm_size 256m for
    Chromium, PYTHON_KEYRING_BACKEND=null (credentials are session-only in containers);
    includes commented music-folder volume examples.
  .dockerignore: excludes .git, .venv, data/, dist/, AppDir/ from the build context.

---

[2026-05-22] — fix(paths): use XDG_DATA_HOME for data dir on frozen Linux (AppImage)

Fixed

  backend/paths.py: On Linux with a PyInstaller frozen build the executable lives inside a
    read-only AppImage squashfs mount (or an ephemeral temp dir with --appimage-extract-and-run).
    _app_root() now returns $XDG_DATA_HOME/LosslessBob (defaulting to
    ~/.local/share/LosslessBob) so data/ is writable and persists across runs.
    Windows behaviour is unchanged.

---

[2026-05-22] — fix(release): bundle Qt xcb dependencies for Linux AppImage

Fixed

  .github/workflows/release.yml: Added libxcb-cursor0, libxcb-icccm4, libxcb-image0,
    libxcb-keysyms1, libxcb-render-util0, and libxkbcommon-x11-0 to the apt-get install step so
    PyInstaller can find and bundle them. Without these, the Qt xcb platform plugin fails to load
    on systems that don't have them pre-installed (Qt 6.5+ requires libxcb-cursor0 specifically).

---

[2026-05-22] — feat(release): add Linux AppImage build to GitHub Actions release workflow

Added

  losslessbob_linux.spec: New PyInstaller spec for Linux. Identical to the Windows spec except
    numpy, scipy, librosa, soundfile, and numba are NOT excluded, so the fingerprinting stack is
    bundled. Platform-specific hiddenimports trimmed to Linux (inotify watchdog observer only).
  .github/workflows/release.yml: Added build-linux job on ubuntu-latest. Installs libgl1 and
    upx-ucl, runs PyInstaller with the Linux spec, assembles an AppDir (AppRun + .desktop + icon),
    downloads appimagetool (AppImageKit continuous), and builds a self-contained
    LosslessBob-<ver>-linux-x86_64.AppImage. Both Windows and Linux jobs upload independently to
    the same GitHub Release via softprops/action-gh-release@v2. Workflow renamed to "Release".

---

[2026-05-22] — fix(release): remove invalid "checked" flag from Inno Setup [Tasks] section

Fixed

  tools/losslessbob.iss: Lines 53–54 used `Flags: checked` in the [Tasks] section. "checked"
    is not a valid Inno Setup task flag — tasks are checked by default with no flag. Removed
    the `Flags: checked` parameter from the startmenuicon and desktopicon task entries.

[2026-05-22] — fix(release): ISS preprocessor error and update GHA actions to Node 24

Fixed

  tools/losslessbob.iss: Inno Setup ISPP preprocessor treated standalone `#13#10 +` lines as
    unknown directives, aborting the installer build with exit code 1. Merged the bare blank-line
    `#13#10 +` expressions onto the preceding string lines so `#` never starts a source line.
  .github/workflows/release.yml: Bumped actions/checkout v4→v5 and actions/setup-python v5→v6
    to resolve Node.js 20 deprecation warning (forced to Node.js 24 from 2026-06-02).

[2026-05-22] — fix(backend): correct wrong column names in generate_release_notes

Fixed

  backend/db.py: generate_release_notes queried `notes` and `updated_at` from lb_master,
    which don't exist. Corrected to `manual_notes` and `manual_set_at` (BUG-103).

[2026-05-22] — chore(release): bump version to 1.0.4

Changed

  backend/paths.py: APP_VERSION 1.0 → 1.0.4

[2026-05-22] — feat(release): add file associations, startup option, and data cleanup to Windows installer

Added

  tools/losslessbob.iss [Tasks]: fileassoc task (unchecked by default) registers .ffp/.md5/.st5
    extensions to LosslessBob.Checksum ProgID in HKCU so double-clicking checksum files opens the app.
  tools/losslessbob.iss [Tasks]: startupregistry task (unchecked by default) adds the exe to
    HKCU\...\Run so LosslessBob launches with Windows.
  tools/losslessbob.iss [Code]: CurUninstallStepChanged prompts to delete data\ on uninstall;
    auto-cleans app dir if empty. All registry keys created by the installer are removed automatically.

[2026-05-22] — feat(release): add Inno Setup installer for Windows releases

Added

  tools/losslessbob.iss: Inno Setup 6 script that wraps the PyInstaller dist/LosslessBob/
    directory into a LosslessBob_Setup_<version>.exe wizard installer. Installs to
    %LocalAppData%\LosslessBob (no UAC required); creates data\ dir; Desktop + Start Menu
    shortcuts optional. Output goes to tools/Output/.
  .github/workflows/release.yml: Updated to build the installer after PyInstaller, then
    upload both LosslessBob_Setup_<ver>.exe and a portable .zip to the GitHub Release.

[2026-05-22] — fix(gui): lookup folders now propagate to lbdir and verify immediately on lookup_completed

Fixed

  gui/main_window.py: Connected lookup_tab.lookup_completed to add_folders_from_lookup
    on both verify_tab and lbdir_tab so folders appear immediately after lookup, not only
    on tab switch.
  gui/lbdir_tab.py (add_folders_from_lookup): Removed "only if empty" guard; now merges
    new folders in, skipping duplicates. lbdir list is no longer locked after first use.
  gui/verify_tab.py (add_folders_from_lookup): Same guard removal and merge logic.

---

[2026-05-22] — fix(cli): daemon start uses DETACHED_PROCESS on Windows instead of POSIX-only start_new_session (TODO-078)

Fixed

  cli.py (_daemon_start): Added platform check — Windows now uses
    subprocess.DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP via creationflags;
    POSIX still uses start_new_session=True.

---

[2026-05-22] — fix(backend): Export HTML decade/year dropdowns now populate via folder_name fallback (TODO-084)

Fixed

  backend/app.py (collection_export_html): When entries.date_str is NULL for a collection
    row (LEFT JOIN miss), year was "" and JS filter(Boolean) stripped it, leaving both the
    "All decades" and "All years" selects empty. Now falls back to a regex search on
    folder_name for a 19xx/20xx year, so the dropdowns populate even when date_str is absent.

---

[2026-05-22] — feat(gui): pre-populate lbdir folder list from Lookup tab on tab switch (TODO-081)

Added

  gui/lbdir_tab.py: add_folders_from_lookup(folders) — mirrors verify_tab's implementation; only pre-populates when the lbdir folder list is currently empty, so active sessions are not overwritten.

Changed

  gui/main_window.py (_on_tab_changed): when switching to lbdir_tab, call add_folders_from_lookup with the current Lookup folders, matching the existing Verify tab guard pattern.

---

[2026-05-22] — feat(gui): embed all LB alias numbers in proposed folder name after alias collapse (TODO-080)

Added

  backend/db.py: get_aliases_for_canonical(canonical_lb) — thin helper returning sorted list[int] of alias_lb values for a given canonical, using the existing get_lb_aliases() query.

Changed

  gui/rename_tab.py (populate_from_lookup): after alias collapse resolves to a canonical, fetches all aliases via GET /api/lb_alias?canonical_lb=<lb>. Builds combined suffix LB-canonical-LB-alias1-... and uses it for the proposed folder name. Display column shows all LBs separated by " + " (e.g. "LB-12345 + LB-67890"). Existing _lb_in_name/_has_wrong_lb checks still use the canonical alone so state detection is unaffected.
  gui/rename_tab.py (_on_save_alias): same alias fetch applied after in-place re-resolution so rows updated from the right-click "Save as master alias…" action also reflect the combined suffix immediately.

---

[2026-05-22] — fix(gui): fingerprint build and crawler status polling blocks main thread (BUG-099 through BUG-102)

Fixed

  gui/spectrogram_tab.py: Replaced QTimer-based _fp_poll_build and _fp_poll_dup (which ran
    blocking requests.get on the main thread) with background QThread pollers
    (_FpBuildStatusThread, _FpDupStatusThread) that emit status_update signals to the main
    thread — the same pattern used by the crawler. Fingerprint build stop now shows
    "Stopping…" immediately on the label. _fp_stop_dup_scan was calling the wrong endpoint
    (/api/fingerprint/build/stop) and blocking the main thread; both are fixed. The
    _on_fp_dup_status slot properly cleans up the thread on completion.

  gui/scraper_tab.py: Crawler "Start" and "Stop" buttons were calling requests.post directly
    on the main GUI thread (freezing the app for up to 10 s / 5 s respectively). Both now
    dispatch via a _Worker QThread. Added self._workers list to ScraperTab.

  backend/app.py: Added /api/fingerprint/duplicates/scan/stop endpoint (the old stop button
    was misfiring to /api/fingerprint/build/stop). Added stop_requested field to
    _fp_dup_state so the GUI can show "Stopping…" while the scan winds down.

[2026-05-22] — fix(gui): curator checkbox error dialog on toggle (BUG-098)

Fixed

  gui/setup_tab.py: Moved curator_cb.toggled signal connection to after publish_master_btn is
    created, eliminating the AttributeError risk if the signal fires during _build_ui before its
    dependent widget exists. Added logging.exception in the except block so the actual error text
    is now captured in losslessbob.log. Improved error display: Flask's JSON error body is parsed
    so the dialog shows the plain message rather than raw JSON. Fixed _on_curator_toggled docstring
    (removed incorrect 'geocoder group' claim — that gating happens via curator_mode_changed →
    map_tab.set_curator_mode).

  backend/app.py: Added logging.exception to the curator_set route's except block so any
    server-side failure is captured in the log.

[2026-05-21] — fix(backend): sticky table header broken in exported HTML collection page

Fixed

  backend/app.py: Switched from a page-scroll layout to a flex-column viewport layout.
    Root cause: `overflow-x:auto` on `.card` implicitly forces `overflow-y:auto` (CSS spec),
    making `.card` a vertical scroll container — and `position:sticky` cannot escape its own
    scroll container. No single overflow value fixes this while also enabling horizontal
    scroll and border-radius clipping simultaneously.
    Fix: `html/body` are now `height:100%;overflow:hidden;display:flex;flex-direction:column`.
    `.card` gets `flex:1;min-height:0;overflow:auto` (fills remaining viewport, scrolls
    internally). `thead th` sticks at `top:0` relative to `.card`'s scroll context instead
    of the viewport. `.hdr`, `.pg`, `.ftr` get `flex-shrink:0`. `watchHdr()` and `--hh`
    removed (no longer needed). `go()` now scrolls `.card` instead of `window`. Print
    media query overrides flex layout to restore full-page rendering. (BUG-097)

[2026-05-21] — feat(cli): add fingerprint command (build/stop/status/identify/stats/scan-dupes/dupes)

Added

  cli.py: `fingerprint` subcommand wired into _build_parser(), _execute(), _HELP_TEXT,
          _help_text() (narrow), _COMMAND_HELP, and _COMPLETIONS.
          Sub-actions: build [--force] [--watch], stop, status [--json],
          identify <FILE> [--json], stats [--json], scan-dupes [--watch], dupes [--json].
          _watch_fp_build() — polls /api/fingerprint/build/status with a progress bar.
          _watch_fp_dupes() — polls /api/fingerprint/duplicates until scan finishes.
          _print_fp_status() — formatted build-progress output.
          _print_fp_identify() — ranked candidate list with CONFIDENT flag.
          _print_fp_dupes() — duplicate pair list with lb_a ↔ lb_b and file paths.
          All output adapts to narrow (<50 col) and wide terminal widths.

[2026-05-21] — feat(cli): daemon mode — persistent background backend + auto-attach

Added

  cli.py: _is_flask_running(port) — checks if :5174 is already accepting connections.
          _daemon_start/_daemon_stop/_daemon_status helpers — fork run_backend.py as
          a detached OS process (start_new_session=True), write data/backend.pid,
          redirect output to data/backend.log. SIGTERM on stop.
          `daemon start|stop|status` subcommand added to _build_parser(), _execute(),
          _HELP_TEXT, _COMMAND_HELP, and _COMPLETIONS.
          _run_interactive() now checks _is_flask_running() first; if a backend is
          already up it attaches instead of starting a new server.
          One-shot main() same: skips thread start when port already listening.
          `daemon` command excluded from Flask startup check (needs no backend).

  run_backend.py: Added --port argument (argparse) so cli.py daemon start can pass
                  the configured port when forking the process.

  main.py: Added _wait_for_port(..., timeout=0.5) check before spawning the Flask
           thread. If a daemon backend is already up, the GUI attaches to it; the
           Flask thread and restart-callback registration are skipped. Closing the
           GUI window no longer kills a running daemon.

[2026-05-21] — ux(cli): tabular scraper/crawler status for narrow mobile output

Changed

  cli.py: Added _print_scrape_status() — narrow mode prints an _hr("scraper") block with
          Status / LB / Progress / Errors / Skipped / Action rows (label col 10 chars).
          scrape status dispatch now calls _print_scrape_status() instead of _fmt_scrape_status().
          _watch_scrape() narrow mode: \r-overwrite progress bar [███░░░] N/total LB-NNNNN,
          bar width computed to fill exactly w chars.
          _watch_crawler() narrow mode: single line per URL using HH:MM timestamp (saves 3
          chars vs HH:MM:SS) with inline Q:N count appended — no separate counts line.
          crawler status idle narrow: _hr("crawler") + Status / Fetched table rows.
          crawler start confirmation narrow: two-line "Crawler started / scope: X".
          Removed dead code: _fmt_crawler_status() was defined but never called.

[2026-05-21] — ux(cli): tabular single-line column layout for narrow mobile output

Changed

  cli.py: Replaced 2-line search/recent format with single-line columnar rows that fill
          exactly w chars: LB-NNNNN  YYYY-MM-DD  location (location truncated to w-22).
          lookup narrow: single row LB-NNNNN  m:N  ?:N  status (status fills remaining).
          stats narrow: _hr("stats") section header + aligned two-column key-value table
          (Entries / Checksums / Latest LB / Imported, label col 11 chars wide).

[2026-05-21] — ux(cli): optimise all output for 40-character mobile terminals

Changed

  cli.py: Added `import textwrap`.  All outputs now adapt to the current terminal width
          with a narrow-mode threshold of < 50 columns.
    _fmt_scrape_status(): narrow mode drops errors/skipped/action; shows run/idle + LB only.
    _counts(): narrow mode shows ↓N Q:N (fetched + queue) and drops 304/404 breakdowns.
    _print_show(): values truncated to fit within terminal width (val_w = w - 14).
    _print_diff(): db_sfx shortens to " [DB]" on narrow; fn_w computed per-suffix.
    _print_verify(): narrow mode moves missing-type tag to its own line; fn_w tightened.
    search output: 2-line format (LB+date / location) when w < 50.
    lookup output: narrow 2-line format (LB + m:N ?:N / status) when w < 50.
    recent output: 2-line format matching search when w < 50.
    scrape start: narrow confirmation is 2-line "Scrape started / N entries".
    Interactive banner and Ctrl-C hint: shortened for w < 50.
    _help_text(): new function — returns 10-column compact command list on narrow screens,
                  full _HELP_TEXT on wide screens.
    _fmt_help(): new function — word-wraps per-command help pages to terminal width.
    help/? dispatch: uses _help_text() and _fmt_help(); "No help for X" wraps on narrow.

[2026-05-21] — feat(cli): add 8 new commands — show, open, diff, verify, missing, export, backup, recent

Added

  cli.py: Eight new commands implemented against existing Flask API endpoints.
    show <LB>              Full concert record: metadata, checksums, cached files.
                           Accepts "123", "00123", or "LB-00123" via _parse_lb().
    open <LB>              Opens losslessbob.com detail page in the default browser.
    diff <file> ...        Diff-style lookup: ✓ matched, ✗ missing from input (fetches
                           entry detail to show filenames), ? not in DB at all.
    verify <dir> ...       Wraps POST /api/verify; shows pass/fail + problem files.
    missing [--field ...]  --field checksums → GET /api/db/missing_lb_numbers;
                           --field metadata → paginates GET /api/lb_master?status=missing.
    export [--format ...]  csv → GET /api/dbedit/table/entries/export (streamed bytes);
                           json/txt → paginated GET /api/dbedit/table/entries/rows.
    backup [<dest>]        POST /api/db/backup; optional shutil.copy2 to dest path.
    recent [N]             GET /api/dbedit/table/entries/rows sorted by scraped_at DESC.
    Added _parse_lb(), _LB_URL, _TYPE_LABELS constants; _print_show(), _print_diff(),
    _print_verify() formatters; all 8 commands in _build_parser(), _execute(),
    _COMMAND_HELP, _COMPLETIONS, and _HELP_TEXT.

[2026-05-21] — feat(cli): clear screen on startup and add `clear` shell command

Changed

  cli.py: Added `_clear_screen()` (ANSI `\033[2J\033[H`) so the terminal is wiped clean
    once Flask is ready and the welcome message always starts at line 1. Added `clear`
    as a REPL command (tab-completable) that clears the screen mid-session. Added `clear`
    to the `help` output and `_COMPLETIONS` list.

[2026-05-21] — feat(cli): detect terminal width and adapt all output formatting

Changed

  cli.py: Added `shutil.get_terminal_size()`-based `_term_width()` helper. All output
    formatters now query the live terminal width instead of using hardcoded constants.
    - Removed `_MOB_W = 44` constant; `_hr()` and `_watch_crawler()` use `_term_width()`
    - `_watch_scrape()`: status line capped to terminal width to prevent wrap on narrow TTYs
    - `_watch_crawler()`: `url_w` and message chunk width computed from live terminal size
    - `_fmt_crawler_status()`: URL truncated to available space after the fixed prefix
    - `stats`: vertical (one-field-per-line) layout on terminals narrower than 72 columns
    - `lookup`: two-line-per-result layout on terminals narrower than 70 columns
    - `search`: location field truncated to `max(20, term_width - 27)` instead of fixed 50

[2026-05-21] — feat(cli): interactive REPL shell with per-command help and tab-completion

Changed

  cli.py: Running `cli.py` with no arguments now opens a persistent interactive shell
    (prompt `lb> `) instead of printing usage and exiting.  Flask starts once in a
    background daemon thread on entry; all subsequent commands reuse the running backend.
    One-shot invocation (`cli.py <command> [args]`) is fully backward-compatible.
    Added:
      - _run_interactive(): REPL loop with Ctrl-C safety, EOFError/Ctrl-D exit
      - _setup_readline(): readline history persisted to ~/.losslessbob_history, tab-
          completion for all top-level commands and scrape/crawler sub-commands
      - _build_parser(): extracted parser construction so it can be reused both in
          interactive (_SilentParser, no sys.exit) and one-shot modes
      - _execute(): extracted dispatch logic called by both modes
      - _SilentParser / _UsageError: subclass of ArgumentParser that raises instead of
          calling sys.exit so parse errors don't kill the REPL
      - _HELP_TEXT: structured overview with examples shown by `help` / `?`
      - _COMMAND_HELP dict: full per-command reference (arguments, flags, output format,
          examples) shown by `help <command>` (e.g. `help search`, `help crawler`)
      - --port N with no subcommand also enters interactive mode on the given port

[2026-05-21] — feat(cli): crawler status live tail log for mobile screens

Changed

  cli.py: `crawler status` now enters a live tail-log mode instead of printing
    one snapshot. Each URL change and stage transition prints a new log entry
    (scrolling, not overwriting) sized for ~44-char mobile SSH sessions.
    Format: timestamp + arrow (↓ new / ↺ conditional GET) + short path, then
    counts (ok / 304 / 404 / err / queue) on a second line.
    If no crawl is running it prints "idle — no crawl running" and exits.
    `--json` still produces a raw snapshot and exits as before.
    Added _MOB_W, _short_path(), _counts(), _hr() helpers; _watch_crawler()
    rewritten to use the new format (also used by `crawler start --watch`).

[2026-05-21] — fix(gui): crawler status poll race condition shows "idle" immediately after start

Fixed

  gui/scraper_tab.py: _on_crawler_status now ignores the initial idle state (running=False,
    stage="idle") so the poll thread doesn't stop itself before the crawler thread has had a
    chance to set running=True. UI only resets when stage is a terminal value (done/stopped/error).

[2026-05-21] — feat(cli): add scrape and crawler start/stop/status subcommands

Added

  cli.py: `scrape start/stop/status` and `crawler start/stop/status` subcommands.
    `scrape start` accepts --start-lb, --end-lb, --force, --watch.
    `crawler start` accepts --scope, --force, --delay-ms, --daily-cap, --watch.
    --watch polls the respective status endpoint every 2 s and prints progress until done.
    Extracted _wait_for_flask() helper to clean up the startup probe.

[2026-05-21] — perf(scraper): reduce per-entry DB write overhead in scrape_range

Changed

  backend/scraper.py: Skip-check now uses get_connection (read-only) for reads and only
    acquires write_connection when marking attachment files downloaded; uses executemany
    instead of individual UPDATE per file. Attachment download loop now batches all
    downloaded=1 updates into one executemany after the loop instead of one write_connection
    per file. Added _reconcile param (default True) to scrape_entry so scrape_range can
    defer lb_master reconciliation. Moved NavigableString import to module level.
    Added _RECONCILE_BATCH = 100 constant.
  backend/db.py: Added batch_reconcile_lb_status() — reconciles N lb_master rows in a
    single write transaction using bulk IN-queries (4 SELECTs + executemany) instead of
    the O(N) per-entry pattern (N × 4 queries). Used by scrape_range every 100 entries
    and on stop/finish.

---

[2026-05-21] — test: add comprehensive DB write function test battery (test_db_writes.py)

Added

  tests/test_db_writes.py: 115-test battery covering all database write functions in backend/db.py.
    Grouped into 17 test classes: set_meta, collection CRUD, collection_meta upserts,
    listen-count increment, wishlist, record_entry_changes, insert_missing_entry,
    lb_master reconcile/override/clear, overrides export/import, lb_alias (chain rewrite,
    cycle detection, dedup), folder_lb_link, torrent records, forum posts, rename history,
    all purge functions, scrape sessions, upsert_inventory, write_connection rollback, and
    a dedicated SQL constraint class that deliberately triggers UNIQUE, CHECK, NOT NULL,
    PK, and FK violations. Includes a concurrent-writes thread-safety test.

[2026-05-21] — fix(backend): eliminate SQLite database locking errors under concurrent scrape + fingerprint

Changed

  backend/db.py: Added `_write_lock = threading.RLock()` and `write_connection()` context manager.
    All DML functions now acquire the write lock before opening a write transaction, serialising
    writers at the Python level so SQLite's busy_timeout is never exceeded. Also fixed
    `sqlite3.connect(timeout=30)` to align Python's internal retry with the PRAGMA value.
  backend/scraper.py: Converted three `with get_connection()` write blocks to `write_connection()`.
  backend/app.py: Converted three direct DML routes (DB reset, dbedit UPDATE, dbedit DELETE)
    to use `write_connection()` / `_write_lock`.

[2026-05-20] — fix(backend): exported HTML collection shows no rows (TDZ crash in boot IIFE)

Fixed

  backend/app.py: `const SM` and `const BC` were declared after the boot IIFE in
    _COLLECTION_HTML_TEMPLATE, placing them in the temporal dead zone when mkStats() and
    draw() were called. Moved both declarations before the IIFE so they are initialized
    before boot() runs.

[2026-05-20] — feat(gui/map): custom cluster icon colors with vivid tier-based palette

Changed

  gui/resources/map.html: Replaced default MarkerCluster CSS bubble colors with a custom
    iconCreateFunction. Five count tiers: cyan (<10), mint green (<50), amber (<150),
    deep orange (<500), vivid purple (500+). Bubble size scales with count. Glowing ring
    via box-shadow. Previous STATUS_COLORS changes also preserved for individual markers.

[2026-05-20] — feat(backend): rework HTML collection export into modern interactive single-file report

Changed

  backend/app.py: Rewrote GET /api/collection/export/html. Now generates a self-contained
    interactive HTML report via _COLLECTION_HTML_TEMPLATE (module-level constant). Features:
    • Dark/light mode via prefers-color-scheme CSS media query
    • Stats pills bar: total recordings + per-status counts (Public/Private/Missing/Unknown)
    • Live search with 150 ms debounce across LB#, date, location, folder, notes
    • Search-term highlighting in results (<mark> elements)
    • Column sorting (all 6 columns, toggle asc/desc, visual ▲/▼ arrows)
    • Status filter dropdown (Public/Private/Missing/Unknown)
    • Decade filter dropdown (auto-built from data: 1960s, 1970s, …)
    • Year filter dropdown (auto-built from data)
    • Client-side pagination (100 rows/page default; 50/100/200/500 selector) — essential
      for 16 000+ entry collections; only the current page renders as DOM, full dataset in JSON
    • Keyboard shortcuts: / or Ctrl+K to focus search; Escape to clear; ← → to page
    • CSV download button exports the currently filtered+sorted view with BOM (Excel-safe)
    • Copy LB#s button copies all visible LB numbers to clipboard via navigator.clipboard
    • Sticky header with ResizeObserver so table thead offset tracks header height dynamically
    • Toast notifications for clipboard/CSV actions
    • Print-friendly media query (hides controls)
    • Generation timestamp in header and footer
    All 16 k entries embed as a JSON array (~3–4 MB); JS renders 100 rows at a time.
    No external dependencies — single self-contained file, works fully offline.

[2026-05-20] — feat(gui+backend): export My Collection as HTML table or M3U playlist (FEAT-07)

Added

  backend/app.py: GET /api/collection/export/html — initial simple HTML table (superseded above).
  backend/app.py: GET /api/collection/export/m3u — returns an #EXTM3U playlist walking each
    entry's disk_path for audio files (.flac/.shn/.ape/.wav/.mp3); skips missing folders.
  gui/collection_tab.py: "Export HTML…" and "Export M3U…" buttons in My Collection panel;
    each GETs the corresponding API endpoint and writes the response bytes to a user-chosen
    file via QFileDialog.getSaveFileName(); status label updated on success or error.

[2026-05-20] — feat(gui): more vivid map marker colors and significantly larger popup text

Changed

  gui/resources/map.html: STATUS_COLORS replaced with vivid palette (public #00C853,
    private #00B0FF, missing #FF6D00, unknown #E040FB); fillOpacity 0.85→0.95; owned
    marker ring changed from white to gold (#FFD600); popup title 15px→20px, body
    13px→15px, status label 13px→15px, search button 12px→14px, owned star 11px→15px.

[2026-05-20] — feat(gui): larger map bubbles and popup text for LB markers

Changed

  gui/resources/map.html: increased circleMarker radius from 8 → 12, owned-marker
    border weight from 3 → 4 (non-owned 1 → 1.5); popup title font-size 13px → 15px,
    added base .lb-popup font-size 13px with line-height 1.5, status text bumped to 13px,
    search button font 11px → 12px and padding slightly increased.

[2026-05-20] — fix(gui): rework Attachments tab — QTableView replaces QTreeWidget (BUG-092)

Changed

  gui/attachments_tab.py: full rework of the Cached view.
    - _LbModel(QAbstractTableModel): two-column model (LB Number, Files) read directly from
      the in-memory list; Qt renders only visible rows so all entries display without any
      pagination — page nav buttons removed.
    - QSortFilterProxyModel on the table provides instant text filtering; numeric input
      (e.g. "1234") is normalized to "LB-01234" automatically.
    - QListWidget below the table shows files for the selected LB; connected once in _build_ui
      to avoid repeated signal connections.
    - lb_status fetched via LEFT JOIN lb_master inside _RefreshTreeThread so _render_tree_page's
      blocking get_lb_statuses_batch() call on the main thread is eliminated.
    - Removed: PAGE_SIZE, _page, _render_tree_page, prev/next page buttons, _jump_to_lb, the
      old _tree_context_menu and _LB_STATUS_BG dict; all replaced by the model/proxy approach.
    - Removed import of get_lb_statuses_batch (no longer needed).

[2026-05-20] — fix(gui): Setup tab stats not refreshed after flat file apply (BUG-091)

Fixed

  gui/setup_tab.py: _on_discover_done() now calls _refresh_stats() after the update dialog
    closes, so the DB stats label (total checksums, LB entries, latest LB) updates immediately
    when a flat file is applied. Previously it required an app restart to reflect the new counts.

[2026-05-20] — feat(gui+backend): Fingerprinted column in My Collection; fingerprint progress shows folder name

Added

  gui/collection_tab.py: new "Fingerprinted" column (col 8) in My Collection table. Shows "Yes"
    (green) when at least one audio track for that LB number has been fingerprinted. Tooltip
    shows hash count. Column is sortable. Data is fetched async via the new API endpoint and
    merged into rows without blocking the collection load.
  backend/app.py: GET /api/fingerprint/lb_numbers — returns {lb_number: n_hashes} dict for
    all fingerprinted LBs, used by the new collection column.

Changed

  backend/fingerprint.py: build_fingerprint_db() now sets current to "FolderName / filename"
    instead of just "filename", so the Fingerprinting tab progress label shows which folder is
    being processed.

[2026-05-20] — fix(fingerprint): duplicate scan used raw hash count instead of temporal coherence (BUG-089)

Fixed

  backend/fingerprint.py: find_duplicate_recordings() was grouping by (track_a, track_b)
    and counting raw hash collisions. Any two files sharing spectral content in unrelated
    passages could accumulate enough raw hits to pass MATCH_THRESHOLD, producing mass
    false positives. Fixed by applying the same temporal-coherence approach as
    identify_file(): matches are bucketed by their time-offset delta (rounded to 0.1 s)
    and the peak bin count — not the total hit count — is used as the score.

[2026-05-20] — fix(deps): install numpy/librosa/scipy/soundfile/numba into venv (BUG-088)

Fixed

  requirements.txt: added numpy==2.4.6, numba==0.65.1; bumped librosa to 0.11.0,
    soundfile to 0.13.1, scipy to 1.17.1. All packages now installed in .venv.
    Previously fingerprint_file() failed with "No module named 'numpy'" on every call.
  PROJECT.md: updated Tech Stack table to reflect actual installed versions.

[2026-05-20] — feat(gui+backend): right-click "Fingerprint Folder" in My Collection tab

Added

  gui/collection_tab.py: "Fingerprint Folder" action in the My Collection context menu.
    Appears for any selected row(s) whose disk_path exists on disk. Calls the build
    endpoint with only the selected folder(s) so the full collection is not re-scanned.
  backend/app.py: /api/fingerprint/build now accepts an optional `folders` list of
    {disk_path, lb_number} dicts in the JSON body. When provided, only those rows are
    fingerprinted instead of the whole collection.

[2026-05-20] — fix(fingerprint): remove blocking rglob scan from get_fp_stats (BUG-087)

Fixed

  backend/fingerprint.py: get_fp_stats() no longer walks the filesystem to compute
    coverage_pct. The rglob scan caused the /api/fingerprint/stats endpoint to block for
    10+ seconds on large collections, triggering the GUI read timeout. coverage_pct now
    returns None; the GUI already handles this gracefully.

[2026-05-21] — fix(fingerprint): post-review fixes — temporal coherence, DB timeout, rglob, force wiring

Fixed

  backend/fingerprint.py: _get_fp_conn now passes timeout=30 to sqlite3.connect()
    and sets PRAGMA busy_timeout=30000, matching db.py's get_connection() pattern (BUG-086).
  backend/fingerprint.py: identify_file now uses temporal coherence scoring — hashes must
    agree on a consistent time-offset delta (db_offset − query_offset) to score, not just
    raw hit count. This filters hash collisions and makes matching significantly more robust
    against unrelated tracks (BUG-085).
  backend/fingerprint.py: build_fingerprint_db now uses rglob("*") instead of iterdir()
    so multi-disc folders (Disc1/, Disc2/) are traversed correctly.
  backend/fingerprint.py: find_duplicate_recordings self-join now has LIMIT 500 to prevent
    catastrophic query times on large collections.
  backend/fingerprint.py: get_fp_stats now returns coverage_pct alongside track_count and
    hash_count.

Changed

  backend/fingerprint.py: build_fingerprint_db accepts a force: bool parameter, threaded
    through from the GUI checkbox → POST body → Flask route → _do_fp_build → fingerprint_file.
  backend/app.py: fp_build() route reads force from request JSON and passes to _do_fp_build.
  gui/spectrogram_tab.py: _fp_start_build passes force=checkbox state in POST body;
    progress bar starts indeterminate (setRange(0,0)) until total is known; setMaximum
    called only once per build run.
  gui/spectrogram_tab.py: _fp_stop_build now uses _Worker instead of blocking main thread.
  gui/spectrogram_tab.py: stats label shows coverage_pct when available.

[2026-05-21] — feat(fingerprint): add acoustic fingerprinting engine and UI

Added

  backend/fingerprint.py: Wang/Shazam-style landmark fingerprinting engine.
    Stores spectral-peak hashes in data/fingerprints.db. Public API:
    init_fp_db, fingerprint_file, build_fingerprint_db, identify_file,
    find_duplicate_recordings, get_fp_stats.

  backend/paths.py: Added FP_DB_PATH = DATA_DIR / "fingerprints.db".

  backend/sox_utils.py: Added decode_to_wav() public wrapper around
    _convert_to_wav() for use by the fingerprint engine.

Changed

  backend/app.py: Added _fp_build_state/_fp_dup_state module-level dicts,
    _fp_build_lock/_fp_dup_lock/_fp_build_stop/_fp_dup_stop thread primitives,
    _do_fp_build/_do_fp_dup_scan background workers, init_fp_db() call in
    create_app(), and 7 new routes under /api/fingerprint/*.

  gui/spectrogram_tab.py: Refactored _build_ui into inner QTabWidget with
    "Spectrograms" and "Fingerprinting" sub-tabs. Fingerprinting tab has
    three panels: Fingerprint DB (build/stats/stop), Identify File (file drop
    + browse + results table), Find Duplicates (SQL scan + CSV export).

  requirements.txt: Added librosa==0.10.2, soundfile==0.12.1, scipy==1.13.1.

---

[2026-05-20] — chore(release): bump version to 1.0.2

Changed

  gui/main_window.py: VERSION "1.0.1" → "1.0.2"

---

[2026-05-20] — fix(gui): Attachments tab lag — background thread + SQL-join reconcile (BUG-083)

Fixed

  gui/attachments_tab.py: Replaced blocking _reconcile_site_files() filesystem scan
    (24 k+ iterdir() + 50 batched SQL UPDATEs on the main thread) with a single
    UPDATE…IN(SELECT site_inventory) SQL join. Moved all DB work into
    _RefreshTreeThread(QThread); main thread stays responsive. Removed HTTP round-trip
    to /api/db/stats (now uses COUNT(DISTINCT lb_number) in the worker).

---

[2026-05-20] — refactor(gui): Map tab browser-only + geocoding consolidation (TODO-074)

Changed

  gui/map_tab.py: Replaced QWebEngineView with browser-open button. Added Map Filters
    group (year range, lb_status, owned, text search). Added Geocoding group (Run
    Geocoder, status polling) and Location Overrides group (table + double-click edit),
    both curator-only. PyQt6-WebEngine no longer required for the Map tab.
  gui/setup_tab.py: Removed Geocode Locations group and worker threads (_GeocodeRunThread,
    _GeocodeStatusThread). Added curator_mode_changed signal. Frees vertical space.
  gui/dbedit_tab.py: Removed Location Geocoding sub-panel (PlaceManualDialog,
    _geo_box and all geo methods). Frees vertical space in the DB Editor integrity/aliases
    section.
  gui/main_window.py: Connected setup_tab.curator_mode_changed to map_tab.set_curator_mode().

---

[2026-05-20] — feat(cli): FEAT-01 CLI/headless mode — cli.py

Added

  cli.py: New headless CLI entrypoint. Commands: lookup <glob>, search <query>, stats,
    import <path>, serve. Uses port-poll instead of time.sleep() for cross-platform
    safety. Uses Waitress on Windows. Flask and PyQt6 never imported in CLI mode.

---

[2026-05-20] — feat(backend+gui): audio filename reconcile on Lookup and Rename tabs

Added

  backend/db.py: lookup_checksums() MATCHED detail dicts now include db_filename — the
    canonical filename stored in the checksums table. NOT FOUND dicts include db_filename: null.

  backend/app.py: POST /api/checksums/reconcile_audio — validates proposed audio renames
    against the filesystem (ok | from_missing | to_exists per proposal, audio exts only).
    POST /api/checksums/apply_reconcile_audio — executes Path.rename() for each approved pair.

  gui/widgets/reconcile_dialog.py: AudioReconcileDialog — shared preview dialog showing
    checkbox | Current Filename | DB Canonical Filename | Checksum. Pre-checks ok proposals,
    flags problematic ones in yellow. Returns only checked ok renames via get_selected_renames().

  gui/lookup_tab.py: "Reconcile Audio Files" button — enabled after a lookup when any MATCHED
    row has a filename differing from the DB canonical name. Builds proposals from _last_detail
    + source_file path, calls reconcile API, shows AudioReconcileDialog, applies renames.

  gui/rename_tab.py: "Reconcile Audio Files" button — _ReconcileAudioWorker scans checksum
    files (.ffp/.md5/.st5/.sha1/.shn) in each checked folder, runs /api/lookup, extracts
    filename mismatches, then follows the same reconcile → dialog → apply flow.

---

[2026-05-20] — feat(backend+gui): TODO-064/065 — web GUI basic-auth middleware and Setup tab password control

Added

  backend/app.py: before_request hook (_enforce_web_auth) enforces HTTP Basic Auth on /web/*
    and /frontend/* routes when meta key web_password is set. /api/* routes remain open.
    web_password added to db_settings() GET response as "set"/"" (never exposes actual value).
    import base64 added.
  gui/setup_tab.py: "Web GUI Access" QGroupBox in the connection row. Password-mode QLineEdit,
    Save and Clear buttons, status label. _on_web_password_save(), _on_web_password_clear(),
    and _load_web_password_status() handlers wired up. Status loaded on startup.

[2026-05-20] — feat(gui): TODO-028 — click-to-sort on Rename tab main table

Added

  gui/rename_tab.py: RenameSortProxy (QSortFilterProxyModel) wraps RenameModel. lessThan()
    sorts col 1 (Current Folder Name) and col 2 (Proposed Name) by basename text, col 3
    (LB Found) by first numeric LB (multi-LB rows use smallest LB), col 4 (Reason/State)
    by state rank (needs_rename → has_lb → wrong_lb → multiple_ids → renamed → no_match).
    Default sort: Current Folder Name ASC. _on_cell_clicked and _on_context now map
    proxy→source indices before mutating source model rows.

---

[2026-05-20] — feat(i18n): TODO-069 COMPLETE — .qm files compiled and verified (1067/1067 per language)

Fixed

  scripts/build_qm.py: rewrote pure-Python Qt .qm compiler with correct binary format.
    Previous version had wrong tag IDs (Translation=5 instead of 3, SourceText=3 instead of 6,
    Context=4 instead of 7), wrong section layout (one 0x42 section instead of separate 0x42
    Hashes + 0x69 Messages sections), per-record length prefix (not present in real format),
    and wrong ELF hash shift (>> 23 instead of >> 24). Also added elfHash_finish (0 → 1) and
    hashed sourceText+comment (not just sourceText). Verified: 1067/1067 translations returned
    by QCoreApplication.translate() for all five languages.

[2026-05-20] — feat(gui/i18n): scraper_tab.py wrapped (missed from TODO-068 tracking)

Changed

  gui/scraper_tab.py: wrapped all user-facing strings — groupbox titles, all buttons/labels/
    checkboxes/tooltips, table headers, pagination labels, and all status/error messages;
    inventory status combo fixed from addItems()+currentText() comparison to individual
    addItem(tr(...), userData)+currentData() (same i18n correctness fix as other combos).

[2026-05-20] — feat(gui/i18n): TODO-068 COMPLETE — attachments_tab; widgets confirmed clean

Changed

  gui/attachments_tab.py: wrapped all user-facing strings — toggle buttons, tree header, page
    navigation labels, placeholder text, file preview label, context menu actions, scrape status
    messages, and file-reading error text; widgets/sort_keys.py and widgets/state_store.py
    confirmed to contain no user-facing strings (no changes needed).

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab, collection_tab, dbedit_tab

Changed

  gui/dbedit_tab.py: wrapped all user-facing strings in PlaceManualDialog and DbEditTab — buttons,
    labels, groupbox titles, tooltips, QFileDialog/QMessageBox/QInputDialog calls, table headers,
    and all status/error messages; geo filter combo converted from addItems() + text-based map lookup
    to individual addItem(self.tr(...), userData) + currentData(), fixing the i18n lookup bug.

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab, collection_tab

Changed

  gui/collection_tab.py: wrapped all user-facing strings in _AddDialog, _ScanPreviewDialog,
    _PersonalMetaDialog, and CollectionTab — ~130 strings total including tab names, all buttons,
    labels, tooltips, QFileDialog captions, QMessageBox dialogs, context menu actions,
    QTableWidget/QTreeWidget headers, and all status/error f-string messages; _on_inner_tab_changed
    refactored from fragile tab-text comparison to index-based dispatch (correctness fix for i18n).

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab

Changed

  gui/lookup_tab.py: wrapped all user-facing strings in LookupTab and _ChangeHistoryDialog — button
    labels, tooltips, dialog titles, status messages, context menu actions, table header lists,
    QFileDialog captions, filter labels, and all f-string status messages; _TableModel headers now
    wrapped at construction site via [self.tr(h) for h in CONST]; _ChangeHistoryDialog headers use
    [self.tr(h) for h in self._HEADERS]; lb_status_combo items switched from addItems() to individual
    addItem(self.tr(...)) calls for pylupdate compatibility.

[2026-05-19] — feat(gui/i18n): TODO-068 string wrapping — setup_tab, bootlegs_tab, search_tab, lbdir_tab, rename_tab

Changed

  gui/setup_tab.py: wrapped all remaining user-facing strings in handler methods (stats labels, status
    messages, error dialogs, qBittorrent/WTRF/tracker/geocode sections, purge dialog, master publish/install
    dialogs); also wrapped _build_ui ffmpeg/shntool/re-check label strings.
  gui/bootlegs_tab.py: wrapped _BootlegsModel.headerData, tooltip and (no title) strings; wrapped all
    _build_ui combo items (with userData preserved), buttons, labels; wrapped fetch/pagination status messages.
  gui/search_tab.py: wrapped SearchModel.headerData and tooltips; refactored field_combo to use addItem
    with userData so translated display text does not break the field_map lookup; wrapped all _build_ui
    widgets and handler status/error messages.
  gui/lbdir_tab.py: wrapped ReconcilePreviewDialog and ExtraFilesDialog titles, labels, buttons; wrapped all
    LbdirTab._build_ui button texts and tooltips; converted _result_display_status and _fmt_status from
    @staticmethod to instance methods to enable self.tr(); wrapped all handler status messages and error
    strings; wrapped SUMMARY_HEADERS, DETAIL_HEADERS, and INFO_FIELDS at point of use.
  gui/rename_tab.py: wrapped RenameModel.headerData and NFT tooltip dict (inline at use site); wrapped all
    RenameTab._build_ui legend, buttons, and tooltips; wrapped reason strings in populate_from_lookup;
    wrapped all handler status/error messages and context menu action texts; wrapped _AliasDialog.

[2026-05-19] — chore(scraper): raise site crawler daily_cap from 5000 to 99999

Changed

  backend/site_crawler.py: crawl() default daily_cap 5000 → 99999.
  backend/app.py: POST /api/crawler/start default daily_cap 5000 → 99999; updated docstring.
  gui/scraper_tab.py: spinner max 50000 → 99999, default value 5000 → 99999, load fallback 5000 → 99999.

[2026-05-19] — fix(gui/scraper): Attachments tab showed no crawler-downloaded files — entry_files.downloaded never updated by site_crawler

Fixed

  gui/attachments_tab.py: Added _reconcile_site_files() which scans SITE_FILES_DIR on every
    _refresh_tree() call and bulk-updates entry_files SET downloaded=1 for any file that exists
    on disk. Fixes the 6,000+ existing files the crawler had downloaded but that were invisible
    to the tab. Also added `import logging` at module level.
  backend/site_crawler.py: After saving a /files/ URL to disk, now also updates
    entry_files SET downloaded=1 WHERE filename=? so future crawl sessions keep the tab in sync.
    Added get_connection to DB imports.

[2026-05-19] — feat(gui): i18n infrastructure — language loader, Setup tab selector, startup wiring (TODO-067)

Added

  gui/i18n.py: QTranslator loader with load_language() and supported_languages(); reads compiled
    .qm files from gui/locales/; falls back silently to English if file is missing.

Changed

  main.py: read ui_language from meta table via direct SQLite at startup (before any windows are
    shown) and install the matching QTranslator via load_language().
  backend/app.py: added "ui_language" to the GET /api/db/settings response keys so the Setup tab
    can read the current preference on load.
  gui/setup_tab.py: added "Preferences" group box with interface-language QComboBox; saving
    persists via POST /api/db/settings; restart notice appears on change.

---

[2026-05-19] — feat(docs): GitHub Pages marketing website for community advertising

Added

  docs/index.html: Dark-themed landing page showcasing all features, install instructions,
    screenshot placeholders, and GitHub/release links. Ready for GitHub Pages (docs/ source).
  docs/screenshots/README.md: Guide listing which screenshots to capture and where to save them.

[2026-05-19] — feat(gui/backend): map feature complete — local Leaflet, QWebChannel, viewport filter, List in Search

Changed

  gui/resources/map.html: replaced CDN Leaflet/markercluster/heat refs with local /leaflet/ paths;
    added "Open in Search" button to marker popups (calls QWebChannel bridge);
    added Viewport Filter toggle + "List in Search" button that sends visible LB numbers to Search tab.

Added

  gui/resources/leaflet/: bundled Leaflet 1.9.4, leaflet.markercluster 1.5.3,
    leaflet.heat 0.2.0 — map now works fully offline (tiles still require network).
  gui/map_tab.py: _MapBridge(QObject) with openInSearch/listInSearch slots;
    QWebChannel setup with qwebchannel.js injection from Qt resources;
    open_in_search and list_in_search pyqtSignals forwarded from bridge.
  gui/main_window.py: _on_map_open_in_search + _on_map_list_in_search handlers;
    map_tab signals connected on tab creation.
  gui/search_tab.py: _LbListWorker QThread + SearchTab.load_lb_list() for
    direct LB-number loading (used by Map → List in Search).
  backend/db.py: get_entries_by_lb_list() — fetch entries by LB number list.
  backend/app.py: GET /api/entries/by_lb_list + GET /leaflet/<filename> routes.

---

[2026-05-19] — fix(backend/gui): security hardening — CC_SECURITY_REVIEW items #1–11

Fixed

  backend/app.py: #1 Path traversal in /api/master/import — resolve path and
    reject anything outside DATA_DIR/exports or imports; enforce .db extension.
  backend/app.py: #2 /api/master/import had no curator auth check — added
    is_curator() 403 guard matching the export endpoint.
  backend/app.py: #3 /api/lb_master/reconcile was unprotected — added
    is_curator() guard. /api/db/backup rate-limited to once per 60 s.
  backend/db.py: #4 Manifest sha256/master_schema_version not type-checked —
    validate isinstance and length before use; no longer exposes actual SHA on
    mismatch; added lower-bound check (schema ≥ 1).
  gui/setup_tab.py: #5 Blocking requests.post(timeout=600) on Qt main thread
    in _on_install_master and requests.post(timeout=300) in _on_publish_master —
    added _InstallMasterThread and _ExportMasterThread (QThread); both handlers
    now return immediately after starting their worker thread.
  backend/app.py: #6 status query param on /api/lb_master not allowlist-validated
    — returns 400 for any value outside public|private|missing.
  backend/app.py: #7 offset accepts negatives; history limit uncapped — clamped
    offset to ≥ 0, history limit to 1–500.
  backend/app.py: #8 reason field written to manifest/backup without length cap —
    truncated to 200 chars for export, 100 chars for backup.
  backend/app.py: #9 Raw str(exc) in catch-alls for import/export/reconcile/backup
    — replaced with log.exception + {"error": "internal_error"}.
  backend/db.py: #10 f-string table name interpolation — added _SAFE_IDENT
    assertion at module load to guard MASTER_TABLES and USER_TABLES.
  backend/app.py: #11 manual_notes stored without length cap — truncated to 1000.

[2026-05-19] — fix(gui): HiDPI-aware splash screen pixmap on Windows (TODO-049)

Fixed

  main.py: QPixmap(400, 120) was created at logical size with no device-pixel-ratio
    awareness. On Windows at 125%/150%/200% DPI scaling the splash appeared blurry.
    Now queries qt_app.primaryScreen().devicePixelRatio() after QApplication is
    constructed, creates the pixmap at (400*dpr) × (120*dpr) physical pixels, and
    calls pix.setDevicePixelRatio(dpr) so Qt renders it at native resolution.
    Falls back to dpr=1.0 if primaryScreen() returns None (headless/no display).

[2026-05-19] — feat(backend/gui): GET /api/status merged endpoint, halve status-bar loopback (TODO-048)

Added

  backend/app.py: GET /api/status returns database.get_stats() merged with
    database.get_bootleg_stats() under a "bootlegs" key. Halves per-tick loopback
    round-trips from two sequential GETs to one. Existing /api/db/stats and
    /api/bootlegs/stats routes are unchanged.

Changed

  gui/main_window.py: _do_status_fetch() now calls /api/status instead of
    /api/db/stats + /api/bootlegs/stats. Bootleg count read from s["bootlegs"]["total"].
    Removed the inner try/except for the second request — error path simplified to one
    catch.

[2026-05-19] — fix(gui): replace per-tick status thread with persistent poller (TODO-047)

Changed

  gui/main_window.py: _refresh_status() previously spawned a new daemon threading.Thread
    every 10 s (each QTimer tick). Replaced with a single long-lived "status-poller" daemon
    thread (_status_poll_loop) that sleeps via threading.Event.wait(timeout=10). Calling
    _refresh_status() (e.g. from setup_tab.stats_changed) now simply sets _status_wake,
    waking the sleeping thread immediately for an extra fetch. _status_stop + _status_wake
    events are both set in closeEvent to let the thread exit cleanly without joining.
    Removed QTimer and its import; removed the per-tick Thread spawn.

[2026-05-19] — fix(gui): skip QGraphicsDropShadowEffect on Windows to eliminate repaint lag (TODO-046)

Fixed

  gui/styles.py: apply_panel_shadow() now returns immediately on sys.platform == "win32".
    Qt Fusion (Windows) renders entirely in software, so blurRadius=12 shadow effects on
    11 panel widgets forced per-repaint offscreen blits that caused visible scroll/resize lag
    with large tables. Shadows are unaffected on Linux and macOS.

[2026-05-19] — fix(gui): move "Add Root Folder" rglob scan off main thread (BUG-080/TODO-045)

Fixed

  gui/verify_tab.py: _on_add_root_folder used sorted(root_path.rglob("*")) synchronously
    on the Qt main thread. Added _AddRootWorker(QThread) that runs the directory tree scan
    and per-subfolder audio-file check off-thread. _on_add_root_folder now disables the
    button and starts the worker; _on_add_root_finished calls _add_folder() for each
    discovered path and re-enables the button. Added _on_add_root_error for error reporting.
  gui/lbdir_tab.py: Identical fix — same _AddRootWorker pattern added, same slot structure.

[2026-05-19] — fix(main): skip --disable-gpu WebEngine flag on Windows (TODO-044)

Fixed

  main.py: --disable-gpu was applied to QTWEBENGINE_CHROMIUM_FLAGS unconditionally,
    including on Windows. This flag was added to work around Linux/XWayland issues
    (EGL_BAD_NATIVE_WINDOW, GPU-process blackout). On Windows, Chromium uses
    DirectX/ANGLE and GPU acceleration works correctly; forcing --disable-gpu switched
    the Map and Attachments WebEngine tabs to slow Swiftshader software rendering.
    The flag is now injected only when sys.platform != "win32". --disable-logging
    (suppresses Chromium stderr noise) remains unconditional on all platforms.

[2026-05-19] — chore(docs): Windows performance audit — add TODO-044–049 and BUG-080

Added

  TODO.md: TODO-044 (--disable-gpu on Windows), TODO-045 (rglob main-thread freeze),
    TODO-046 (QGraphicsDropShadowEffect repaint lag), TODO-047 (per-tick thread churn),
    TODO-048 (consolidated /api/status), TODO-049 (HiDPI splash pixmap).
  BUGS.md: BUG-080 — rglob("*") on main GUI thread in verify_tab and lbdir_tab.

[2026-05-19] — fix(backend): flat_file relative path, import concurrency guard, .st5 verification

Fixed

  backend/flat_file.py: _DOWNLOADS_DIR was Path("data/downloads") (relative to CWD).
    Changed to DATA_DIR / "downloads" so download/diff/apply work regardless of CWD.
  backend/app.py: /api/db/import POST had no "already running" guard. Two rapid requests
    could start concurrent imports, corrupting _import_state and double-executing the DB merge.
    Added 409 guard matching the pattern used by all other long-running routes.
  backend/checksum_utils.py: .st5 files parsed correctly (via _SHNTOOL_LINE_RE) but stored
    under 'st5' key only — shn_exp = exp.get('shntool') was always None, so verification
    never ran and st5_status was hardcoded 'na'. Fixed: .st5 entries now also populate the
    'shntool' key (when not already set by a .md5 file) and set has_shntool_entries = True.

[2026-05-19] — feat(backend): run_backend.py standalone launcher for phone/LAN use

Added

  run_backend.py: headless Flask launcher (no Qt GUI). Uses the same make_server
    restart loop as main.py. The Restart Server button on the admin page calls the
    in-process callback — only the Flask server recycles, the process stays alive.
    Start with: .venv/bin/python3 run_backend.py

[2026-05-19] — fix(backend/admin): restart button now restarts only the Flask server, not the GUI

Fixed

  main.py: replaced flask_app.run() with werkzeug make_server + serve_forever loop so the
    server can be shut down and restarted in-process without touching the PyQt6 GUI process.
    Added request_flask_restart() and _flask_restart_event / _flask_server globals.
  backend/app.py: added _restart_callback / set_restart_callback(). The admin_restart route
    now calls the callback (set by main.py on Linux) instead of os.execv, so only the Flask
    server recycles. Falls back to os.execv when no callback is set (Windows/standalone).
  backend/admin.html: updated Server card description — "GUI window stays open."

[2026-05-19] — feat(admin): site-crawler control + live status dialog in admin panel

Added

  backend/admin.html: Site Crawler card — Incremental / Full / Stop buttons, progress bar,
    live status line showing current URL. "Live View" button opens a modal dialog that
    polls /api/crawler/status every 1.5 s, displaying stage, fetched / 304 / skipped /
    failed counts and the current URL being fetched. Dialog closes on backdrop click.
  backend/app.py: GET /api/admin/status now includes "crawler" key
    (site_crawler.get_crawler_status() snapshot).

[2026-05-19] — feat(backend): mobile-friendly admin control panel at /admin

Added

  backend/admin.html: self-contained admin UI — dark theme, responsive grid, no external
    dependencies. Sections: DB stats + backup/reset, flat-file update pipeline,
    scraper start/stop with progress bar, LB master reconcile, server restart.
    Auto-polls /api/admin/status every 5 s; toast notifications for all actions;
    confirm overlay for destructive operations (reset DB, restart server).
  backend/app.py: three new admin routes:
    GET  /admin           — serves admin.html
    GET  /api/admin/status — combined DB/scrape/import/master/uptime snapshot
    POST /api/admin/restart — os.execv restart to pick up code changes (202 before exit)

[2026-05-19] — fix(backend/gui): map showed only 434 markers instead of ~9,700 (BUG-075)

Fixed

  backend/app.py: api_map_data() now passes owned=None (no filter) when the
    'owned' query param is absent; previously defaulted to False which applied
    a "non-owned only" WHERE clause. Also accepts "1" as a truthy value for
    the owned=true filter so the Owned-only checkbox works.
  gui/resources/map.html: JS popup corrected to read m.lb_number, m.date_str,
    m.lb_status instead of non-existent m.lb, m.date, m.status field names.
    owned filter now sends owned=true (was owned=1, not matched by Flask).

[2026-05-19] — chore(backend): add __main__ block to app.py for headless backend

Added

  backend/app.py: `if __name__ == "__main__":` entry point so the Flask
    server can be started without the GUI via `python -m backend.app [port]`.
    Port defaults to 5174; pass an integer argument to override.

[2026-05-19] — fix(db): exclude low-confidence geocodes from map markers (BUG-074)

Fixed

  backend/db.py: get_map_data JOIN on location_geocoded now filters out
    confidence='low' rows. Previously, low-confidence Nominatim matches
    (e.g. "Japan 2001" → a village in Indonesia) were shown as map markers.
    They are now counted as unplottable instead.

[2026-05-19] — chore(main): bind Flask to 0.0.0.0 for LAN accessibility

Changed

  main.py: Flask server now listens on 0.0.0.0 instead of 127.0.0.1, making all routes
    (including /map and /api/*) reachable from other machines on the local network.
    The local readiness probe in _wait_for_port still uses 127.0.0.1.

[2026-05-19] — fix(geocoder): retry on HTTP 429 with 60-second back-off (BUG-069)

Fixed

  backend/geocoder.py: geocode_one() now catches urllib.error.HTTPError before the generic
    Exception handler; a 429 response raises the private _RateLimitError sentinel instead of
    silently producing source='failed'. run_batch() wraps geocode_one() in a retry loop (up
    to _MAX_429_RETRIES=3 attempts); on each _RateLimitError it sets stage='rate_limited',
    sleeps _RATE_LIMIT_SLEEP=60 s, then retries without advancing the progress counter. If
    all retries are exhausted the location is written as source='failed' with a descriptive
    note so it can be picked up by --retry-failed later.

[2026-05-19] — feat(gui): column-width save/restore defaults in Setup tab (TODO-029)

Added

  gui/widgets/state_store.py: import weakref; self._registered list tracks every attach_table()
    call as (weakref.ref(table), key, factory_defaults). New methods: has_user_defaults (property),
    save_user_defaults(), restore_user_defaults(), restore_factory_defaults(), clear_user_defaults(),
    _apply_col_widths(). save/restore write immediately (no debounce); _apply_col_widths uses
    _restoring guard so programmatic resize doesn't trigger spurious live-width saves.
  gui/setup_tab.py: accepts state_store=None; new "Column Widths" QGroupBox with three buttons —
    "Save as Defaults", "Restore My Defaults" (disabled when no snapshot exists), "Restore Factory"
    (confirmation required). Status label shows saved vs. none state. _refresh_col_defaults_status()
    syncs button enable state on init.
  gui/main_window.py: SetupTab now receives state_store=self.state_store.

Fixed

  gui/setup_tab.py: removed duplicate layout.addWidget(ff_group) at end of _build_ui().

[2026-05-19] — feat(gui): click-to-sort on Lookup tab summary and detail tables (TODO-027)

Added

  gui/lookup_tab.py: _LookupSortProxy (QSortFilterProxyModel with lessThan() using sort_key_for());
    _SUMMARY_COL_KINDS / _DETAIL_COL_KINDS column kind arrays; _sum_src_row() / _det_src_row()
    helpers to map proxy→source indices. Both summary (default: LB Number ASC) and detail (default:
    Filename ASC) views now support click-to-sort with sort indicator arrows. All selection handlers,
    context menus, double-click, and _on_select_all_incomplete updated to use source row mapping.

---

[2026-05-19] — feat(backend/gui): auto GitHub release upload from Publish button (TODO-022)

Added

  backend/db.py: generate_release_notes() — markdown from lb_status_history + manual overrides
    since the previous master_published_at.
  backend/app.py: GET /api/master/status (returns master_version + master_published_at);
    POST /api/master/github_release — generates tag (master-YYYY-MM-DD[.N]), builds release notes,
    runs gh release create, returns {ok, tag, url}.
  gui/setup_tab.py: _GithubReleaseThread; _on_publish_master now reads prev master_published_at,
    exports, then uploads to GitHub in a background thread; _on_github_release_done shows tag + URL;
    _publish_status_label shows live progress below the Publish button.

---

[2026-05-19] — feat(gui): entry change history viewer in Lookup tab (TODO-005)

Added

  gui/lookup_tab.py: _ChangeHistoryDialog + _ChangeHistoryWorker; "History…" button in detail
    panel header, enabled when exactly one LB is selected in summary; fetches up to 200 rows from
    GET /api/entry/<lb>/changes and displays field, old value, new value, changed_at in a resizable
    table; background fetch never blocks the GUI thread.

---

[2026-05-18] — feat(gui): add curator geocoding controls to Setup tab and DB Editor tab

Changed

  gui/setup_tab.py: add Geocode Locations group box (curator only) with progress polling; _GeocodeRunThread POSTs /api/geocode/run, _GeocodeStatusThread polls /api/geocode/status every 2 s; group shown/hidden on curator toggle.
  gui/dbedit_tab.py: add Location Geocoding sub-panel (curator only) with filter dropdown (All/Failed/Low Confidence/Manual Only), Load button calling GET /api/geocode/locations, QTableWidget (7 cols, first col stretches), double-click → PlaceManualDialog; PlaceManualDialog pre-fills lat/lon/note, Save POSTs /api/geocode/location; all HTTP calls via _Worker(QThread), never on GUI thread.

---

[2026-05-18] — fix: crawler seeded from wrong URL + test suite (BUG-067, BUG-068)

Fixed

backend/site_crawler.py: Added SITE_HOME_URL = BASE_URL + "/LosslessBob.html" (real site entry point; domain root is a DreamHost placeholder). Changed crawl() default start_url from BASE_URL to SITE_HOME_URL. Added SEED_URLS constant (/bynumber/LBMbynumber.html, /detail/LB-bootleg-by-title.html) seeded on every crawl as safety-net index pages. Changed BeautifulSoup parser from "lxml" to "html.parser" (eliminates lxml import, removes deprecation warnings). Removed unused attachment_path import and unused local variable. (BUG-068)
backend/html_utils.py: Changed BeautifulSoup parser from "lxml" to "html.parser". (BUG-067)
backend/db.py: Fixed get_scrape_sessions() ORDER BY to add id DESC tiebreaker so sessions created within the same second are reliably ordered by insertion sequence.

Added

tests/test_scraper_crawler.py: 59-test suite covering html_utils.rewrite_links() (9 tests), paths.py SITE_DIR hierarchy (7 tests), db.py scrape_sessions+site_inventory helpers (14 tests), site_crawler.py pure URL utilities (18 tests), and /api/crawler/* Flask route smoke tests (7 tests). All 59 pass individually; see BUG-067 for combined-run limitation.

---

[2026-05-18] — feat: Dedicated Scraper tab + full-site mirror crawler (TODO-031)

Added

backend/site_crawler.py: BFS spider for losslessbob.wonderingwhattochoose.com. crawl(start_url, scope, force, delay_ms, daily_cap) runs in a daemon thread. _extract_links() discovers same-domain links. _fetch_page() uses If-Modified-Since for efficient incremental fetches (304 = skip, 200 = save + rewrite links). _url_to_local() maps URLs to data/site/ sub-dirs. Separate _crawler_state/_crawler_lock (no shared state with scraper.py). Rate limiting: 1500ms ±20% jitter, Retry-After on 429, exponential backoff on error, configurable daily cap, robots.txt cached per session.
backend/html_utils.py: rewrite_links(html, page_url, base_domain) — rewrites server-absolute paths to relative paths so cached pages work via file:// browsing. Uses BeautifulSoup; processes href, src, action attributes.
backend/paths.py: SITE_DIR = DATA_DIR / "site" and sub-constants SITE_DETAIL_DIR, SITE_FILES_DIR, SITE_LBBCD_DIR, SITE_BN_DIR replacing old PAGES_DIR/ATTACHMENTS_DIR. detail_page_path(), attachment_path(), find_lbdir_attachment() updated to use SITE_DETAIL_DIR / SITE_FILES_DIR. ensure_data_dirs() creates all site/ sub-dirs.
backend/db.py: scrape_sessions and site_inventory tables added to SCHEMA_SQL and MASTER_TABLES. Helpers: create_scrape_session(), finish_scrape_session(), get_scrape_sessions(), upsert_inventory(), get_inventory_stats(), get_inventory_page(), get_pending_urls(), get_downloaded_urls().
backend/app.py: 6 new routes: POST /api/crawler/start, GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/sessions, GET /api/crawler/inventory, GET /api/crawler/inventory/stats. backend.site_crawler imported at module level. _crawler_thread single-element list for background thread ref.
gui/scraper_tab.py: New Scraper tab. 5 panels (crawler control, session history, site inventory, entry scraper, bootleg catalog). _CrawlerStatusThread + _ScrapeStatusThread poll respective status endpoints every 1s. All scraper controls migrated from SetupTab. Settings (delay, daily cap) persisted to DB via /api/db/settings.
gui/main_window.py: ScraperTab imported and registered at tab index 10 (between DB Editor and Setup). Tab count: 12 → 13. Tab order comment updated.

Changed

gui/setup_tab.py: Removed all scraper controls (panels, buttons, progress bar, log widget, _log/_on_stop_scrape/_refresh_log_size methods, _LOG_FILE import). Kept: DB management, master data, qBittorrent credentials, WTRF Forum credentials, SoX status, flat-file update history, data-management purge controls. Dead _refresh_log_size() call removed from __init__.
backend/scraper.py: All path references updated from data/pages/ / data/attachments/ to data/site/detail/ / data/site/files/ via SITE_DETAIL_DIR / SITE_FILES_DIR / detail_page_path() / attachment_path() from paths.py.

---

[2026-05-18] — feat: Bootleg-CD Catalog (LBBCD) — scraper, Bootlegs tab, cross-tab integrations (TODO-030)

Added

backend/bootleg_scraper.py: scrape_bootlegs(force) — HEAD→diff→apply pipeline for the LBBCD index page. _parse_date() handles M/D/YY with 'xx' unknowns (2-digit year pivot Y>=30→19YY). _diff() uses (lb_number, title, date_str) natural key. Pre-scrape DB backup via backup_database(). bootleg_scrapes audit row written on every run. get_scrape_status() for polling.
backend/db.py: bootleg_titles + bootleg_scrapes tables added to SCHEMA_SQL and MASTER_TABLES. MASTER_SCHEMA_VERSION bumped to 2. Helper functions: get_bootleg_lb_numbers(), get_bootlegs_for_lb(), get_bootleg_stats(), get_bootlegs() (paginated/filtered), get_bootleg_scrape_history(). _BOOTLEG_SOURCE_URL constant.
backend/app.py: 7 new routes: POST /api/bootlegs/scrape, GET /api/bootlegs/scrape/status, GET /api/bootlegs/lb_numbers, GET /api/bootlegs, GET /api/bootlegs/by_lb/<lb>, GET /api/bootlegs/scrapes, GET /api/bootlegs/stats. bootleg_scraper imported.
gui/bootlegs_tab.py: New Bootlegs tab. Filter bar (text, year range, CDs, status, owned, has-LBBCD). Paginated QTableView (QAbstractTableModel). Detail pane with LBBCD link + "other titles for this LB" panel. open_lb_in_search signal → MainWindow switches to Search tab. bootleg_lbs_loaded signal pushes LB-number set to Search tab for badge rendering.
gui/main_window.py: Bootlegs tab registered at index 5 (between Search and My Collection). _on_bootleg_open_lb() handler. bootleg_lbs_loaded wired to search_tab.set_bootleg_lbs(). Shadow applied to bootlegs_tab.view. Status bar includes "Bootlegs: N" count when catalog is populated.
gui/search_tab.py: SearchModel._bootleg_lbs set; LB Number column shows 🎵 badge when lb_number is in the bootleg set; tooltip explains the badge. set_bootleg_lbs() public method on SearchTab.
gui/setup_tab.py: "Bootleg-CD Catalog (LBBCD)" QGroupBox added to layout; "Scrape Bootleg Catalog" button + Force checkbox + status label; bootleg scrape history table (5 columns); _on_scrape_bootlegs(), _poll_bootlegs_scrape(), _load_bootlegs_history() handlers. History loads on showEvent.

---

[2026-05-18] — feat(backend/gui): Download Missing Pages — cache HTML without metadata scrape (TODO-002)

Added

backend/scraper.py: download_pages_range(lb_numbers, force, delay_ms) — fetches detail pages and saves them to data/pages/ using the existing _scrape_state so the progress bar, stop button, and log all work. last_action="downloaded" distinguishes page fetches from full metadata scrapes. 404s are treated as skipped (not errors) since no DB writes occur.
backend/app.py: POST /api/scrape/download_pages — body: {start_lb?, end_lb?, force?}. Builds a full integer range (1..max_lb by default) and delegates to _start_download_pages_thread(); _start_download_pages_thread() added alongside _start_scrape_thread().
gui/setup_tab.py: Row 4 "Download Missing Pages" button added to the scraper grid. _on_download_pages() handler; _page_download_mode flag on SetupTab. _on_scrape_status() updated to use "Downloading" verb, "already cached" skip text, and "Downloaded LB-X [web]" log lines in download mode; completion message shows downloaded/cached/error counts and refreshes the pages-count label.

---

[2026-05-18] — fix/feat: TODO-006 connection leak, TODO-001 pages count, TODO-016 forum footer

Changed

backend/db.py: Added close_connection(db_path) — closes and evicts the per-thread SQLite handle for a given path. Prevents stale handle being returned for temp_import.db after it is deleted.
backend/importer.py: Calls close_connection(temp_db_path) before both unlink() sites in run_import() so the thread-local pool is clean for subsequent imports. (TODO-006)
backend/paths.py: Added APP_VERSION = "1.0" constant.
backend/forum_poster.py: Replaced hardcoded _FOOTER string with _build_footer() function that reads the WTRF username from the OS keyring via get_credentials(SERVICE_WTRF) and uses APP_VERSION; falls back to "kuddukan" when no credential is stored. (TODO-016)
gui/setup_tab.py: "Use local pages" checkbox now shares a row with a grey count label "(N pages cached)" populated by _refresh_pages_count(), which globs data/pages/*.html. Called from _load_settings(). (TODO-001)

---

[2026-05-18] — fix(gui/db): search tab row colours delayed 5–6 s after first display (BUG-066)

Changed

gui/search_tab.py: Removed self._page = 0 / _render_page() call from _on_xref_loaded(). model.set_xref_map() already emits dataChanged for the Xref column; the full model reset was the cause of the delayed colour paint. Added _prefetch_owned() called at __init__ so the owned set is warm before the first search render.
backend/db.py: Added idx_chk_xref_pos partial index ON checksums(lb_number, xref) WHERE xref>0. Eliminates the full checksums table scan in get_xref_map() that caused the 5–6 s delay.

---

[2026-05-18] — feat(backend/gui): lb_alias + folder_lb_link disambiguation (CC_LB_INTEGRITY item 8)

Added

backend/db.py: lb_alias and folder_lb_link tables added to SCHEMA_SQL. lb_alias added to MASTER_TABLES; folder_lb_link added to USER_TABLES. New helpers: resolve_aliases(), get_folder_link(), set_folder_link(), delete_folder_link(), add_lb_alias(), delete_lb_alias(), get_lb_aliases() — all with type hints and Google-style docstrings.
backend/app.py: 7 new endpoints: GET /api/lb_alias, POST /api/lb_alias (curator-only), DELETE /api/lb_alias/<alias_lb> (curator-only), GET /api/lb_alias/resolve, GET /api/folder_link, PUT /api/folder_link, DELETE /api/folder_link.
gui/rename_tab.py: RenameTab now accepts flask_port parameter. Resolution order on populate_from_lookup: (1) folder_lb_link lookup; (2) lb_alias collapse; (3) fall back to multiple_ids. Right-click: "Link this folder…", "Unlink this folder", "Save as master alias…" (curator-only). _AliasDialog for curator alias creation.
gui/main_window.py: Pass flask_port to RenameTab constructor.
gui/dbedit_tab.py: "LB Aliases" QGroupBox panel. Auto-loads on load_tables(). Add/Delete curator-gated.

[2026-05-18] — feat(backend/gui): Flat-file update check rework (CC_LB_INTEGRITY item 9)

Added

backend/flat_file.py: New pipeline module — discover_flat_file_release, download_flat_file_release,
  diff_flat_file_release, apply_flat_file_release, defer_flat_file_release, get_releases,
  get_release_changelog. Discovers new releases from the LosslessBob download page, downloads
  the zip, diffs against the live checksums table (tab-delimited format matching importer.py),
  and applies changes with a full flat_file_changelog audit trail. Auto-backup before apply.
  Reconciles lb_master for touched LBs post-apply.
backend/db.py: flat_file_releases and flat_file_changelog tables added to SCHEMA_SQL and
  MASTER_TABLES. _bootstrap_flat_file_legacy() for first-run migration.
backend/app.py: 7 new endpoints under /api/flat_file/*.
gui/setup_tab.py: "Check for Flat File Update" button, _UpdateAvailableDialog, Flat File History panel.

Changed

backend/scraper.py: Removed broken check_for_update() which scraped the bynumber page.

[2026-05-18] — feat(gui/backend): Click-to-sort on all major tables (CC_LB_INTEGRITY item 10)

Added

gui/widgets/sort_keys.py: SortableTableItem + sort_key_for() with typed sort keys.
gui/widgets/state_store.py: get_sort()/set_sort() for persistent sort state.
gui/lbdir_tab.py, gui/verify_tab.py: Client-side sort via SortableTableItem.
gui/search_tab.py, gui/collection_tab.py, gui/dbedit_tab.py: In-memory/server-side sort via sectionClicked.
backend/app.py: sort_col/sort_dir params on /api/search, /api/collection, /api/collection/missing.

[2026-05-18] — feat(gui/backend): Override export/import JSON endpoints and DB Editor buttons

Added

backend/db.py: export_overrides() and import_overrides() helpers.
backend/app.py: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import.
gui/dbedit_tab.py: "Export Overrides" and "Import Overrides" buttons in DB Integrity panel.

---

[2026-05-18] — feat(db/backend): add location_geocoded schema, Nominatim geocoder, CLI tool

Added

backend/geocoder.py: Nominatim geocoder module. `geocode_one(location_text)` performs a single
  lookup (stdlib urllib only, no extra deps). `place_manual(location_text, lat, lon, note)` inserts
  a manual coordinate with `manual_override=1` so batch runs never overwrite it. `run_batch(limit,
  retry_failed, dry_run)` batch-geocodes all un-geocoded `entries.location` values with a 1.1-second
  sleep between requests (Nominatim ToS). Thread-safe `_progress` dict for future GUI integration.
  `get_progress()` returns a snapshot for polling.

tools/geocode_locations.py: CLI wrapper for `run_batch`. Accepts `--limit N`, `--retry-failed`,
  `--dry-run`. Configures root logging and resolves project root so it can be run directly from the
  project root directory.

Changed

backend/db.py: Added `location_geocoded` table (DDL inside `_SCHEMA`) — columns: location_text
  (PK), lat, lon, source, confidence, display_name, manual_override (DEFAULT 0), note, geocoded_at.
  Index `idx_geo_source` on source column. Table added to `MASTER_TABLES` so it is included in
  master-data export/import. Added `get_map_data(filters, db_path)` — returns `{"markers": [...],
  "unplottable_count": int}` for a future map tab; joins entries, location_geocoded, lb_master, and
  my_collection; supports filters: status, owned, year_min, year_max, q.

---

[2026-05-18] — feat(backend): add /map, /api/map/data, /api/geocode/* routes

Changed

  backend/app.py: add GET /map, GET /api/map/data, POST /api/geocode/run, GET /api/geocode/status, POST /api/geocode/location, GET /api/geocode/locations. Also added send_from_directory to Flask imports.

---

[2026-05-18] — feat(gui): add Map tab with Leaflet world map, marker clusters, heatmap toggle, browser view

Added

  gui/map_tab.py: Map tab widget with QWebEngineView + Open in Browser fallback
  gui/resources/map.html: Leaflet map page with filters, marker clustering, heatmap mode

---

[2026-05-18] — feat(gui/backend): Map tab wired into main window, PyQt6-WebEngine added to requirements

Changed

  gui/main_window.py: register Map tab after ThemeTab via graceful try/except import fallback so the
    app starts normally even when gui/map_tab.py is not yet present in the worktree
  requirements.txt: PyQt6-WebEngine already pinned at 6.7.0; requests already pinned at 2.32.3 — no
    version changes required
  PROJECT.md: document map feature: new files (map_tab.py, map.html, geocoder.py,
    geocode_locations.py), location_geocoded schema, six new API routes (GET /map,
    GET /api/map/data, POST/GET /api/geocode/*), tab count updated to 11

---

[2026-05-19] — docs(backend): add type hints and Google-style docstrings to all app.py route handlers (TODO-004)

Changed

backend/app.py: Added `Response` to module-level Flask imports. Added `-> Flask` return type and one-line docstring to `create_app()`. Added `-> Response` return types to all 67 route handler functions. Added URL path-parameter type hints across all parameterised routes. Added Google-style docstrings to 47 route functions that previously had none; left 20 existing docstrings unchanged. Added docstring and parameter types to `_start_scrape_thread()` and `_do_spectro_batch()` helpers.

[2026-05-17] — fix(gui): Column widths now actually persist across restarts (GuiStateStore root-cause fix)

Fixed

gui/widgets/state_store.py: Two root causes identified and fixed via headless regression test.
  Bug A — Qt fires sectionResized for all columns during initial layout, AFTER _on_resized is
  connected but BEFORE _restore sets _restoring. _on_resized saved the auto-calculated garbage
  widths; _restore then read them back. Fix: set _restoring.add(tid) at the very start of
  attach_table, before any signal or timer is wired.
  Bug B — _migrate_from_qsettings was copying column widths from old QSettings into the new JSON.
  Those QSettings were written by the same buggy _on_resized, so they contained auto-layout garbage
  (e.g. 5340px for "Description"). Fix: skip column-width migration entirely; only geometry is
  safe to migrate. Added 10 <= w <= 3000 sanity guard in get_col_widths as a second line of
  defence against any future garbage reaching the store.
Also cleared garbage from system QSettings (LosslessBob/SearchTab col_widths).

[2026-05-17] — feat(gui): Reliable column width persistence via GuiStateStore (CC_LB_INTEGRITY item 11)

Added

gui/widgets/state_store.py: `GuiStateStore` — single source of truth for persistent GUI widget state. Stores column widths, window geometry in `data/gui_state.json`. Atomic writes (tempfile + os.replace), 500 ms debounced saves, `_restoring` guard to suppress spurious saves during programmatic restore. One-time QSettings migration on first run.

Changed

gui/main_window.py: Removed `QSettings` window geometry; replaced with `state_store.restore_window` / `save_window`. `closeEvent` calls `state_store.flush()` before close. `GuiStateStore` instance created at startup and passed to all tabs with tables.
gui/search_tab.py: Removed `_qsettings`, `_col_widths`, `_widths_applied`, `_resizing_programmatically`, `_load_col_widths`, `_save_col_widths`, `_on_col_resized`, `_set_default_col_widths`, `_apply_col_widths`. Now calls `state_store.attach_table(view, "search.results")`. `_render_page` no longer snapshots/restores widths around model resets.
gui/dbedit_tab.py: Removed `QSettings` and `_SETTINGS_PATH`. `_snapshot_and_save` / `_load_saved_widths` / `_on_col_resized` now use `state_store.get_col_widths` / `set_col_widths` with key `dbedit.<table_name>`.
gui/collection_tab.py: Removed `_coll_col_widths`, `_miss_col_widths`, `_wish_col_widths` in-memory tracking and `_apply_coll_col_widths` / `_apply_miss_col_widths`. All 7 tables (my_collection, missing, wishlist, forum_history, torrent_history, entry_torrents, entry_forum_posts) now use `state_store.attach_table`.
gui/lbdir_tab.py: `summary_table` now uses `state_store.attach_table`; removed `resizeColumnsToContents()` call from `_populate_summary` that clobbered user widths on each check run.
gui/rename_tab.py: Removed hardcoded `setColumnWidth(0, 50)` in `_build_ui`; replaced with `state_store.attach_table`.

[2026-05-17] — feat(gui): Standardize folder name button in Rename tab (CC_LB_INTEGRITY item 13)

Added

backend/folder_naming.py: `build_standard_name(lb_number, date_str, location, lb_status)` — builds canonical `YYYY-MM-DD Location (LB-XXXXX)[-NFT]` folder name. Shared between Rename tab and Collection tab. Imports `_parse_date` lazily from `backend/torrent_maker`.

backend/app.py: `GET /api/folder_naming/standard/<lb>` — returns `{standard_name, lb_status, nft}`. Looks up entry metadata and lb_master status; applies NFT suffix via `build_standard_name`.

gui/rename_tab.py: "Standardize Selected" button — for each checked single-LB row, fetches canonical name via `get_entry()` + `get_lb_status()` + `build_standard_name()`, updates the proposed name, and escalates state to `needs_rename` when the standard name differs from the current folder name. Right-click "Standardize Name (YYYY-MM-DD Location…)" action applies the same transform to a single row.

gui/rename_tab.py: `RenameModel.update_state(idx, state)` — new method to update a row's state and emit `dataChanged` for the full row.

Fixed

gui/rename_tab.py: `_on_strip_wrong_lb()` now calls `update_state(i, "needs_rename")` after updating the proposed name. Previously the state stayed `wrong_lb`, which is not in the rename-eligible set, so stripped rows could never be renamed by the "Rename Selected" button. (BUG-064)

---

[2026-05-17] — feat(gui): lb_status filter + tinting across Lookup, Attachments, Rename, Lbdir tabs (TODO-021)

Changed

backend/db.py: `get_lb_statuses_batch(lb_numbers)` — single batch SELECT from lb_master, returns {lb_number: lb_status} dict for bulk UI colouring. Also stamps lb_status onto each lb_summary dict in lookup_checksums() for the filter combobox.

gui/lookup_tab.py: "All LB statuses / Public only / Private only / Missing only" QComboBox in Summary header row. `_lb_status_filter` + `_sum_lb_statuses` list drive filter guard in `_apply_filters()`. Private → #B3E5FC, Missing → #E0E0E0 row tinting ahead of match-quality colors.

gui/rename_tab.py: LB Found column (col 3) tinted #B3E5FC/E0E0E0 for Private/Missing when no NFT discrepancy is active.

gui/attachments_tab.py: `_render_tree_page()` batch-fetches lb_status for the current page via `get_lb_statuses_batch()`, tints Private parent items light blue and Missing items gray, with tooltip text.

gui/lbdir_tab.py: `_populate_summary()` batch-fetches lb_status and tints the LB# column (col 1) by lb_status; verification-result color still applies to all other columns.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Changed

backend/db.py: lookup_checksums() now also stamps lb_status onto each lb_summary dict (reusing the same _lb_status_map batch query that already annotates detail items).

gui/lookup_tab.py: Added "All LB statuses / Public only / Private only / Missing only" QComboBox to the Summary header row. _lb_status_filter state drives a new guard in _apply_filters() that filters sum_indices by _sum_lb_statuses. _process_result() populates _sum_lb_statuses (parallel to _sum_lb_nums) from s["lb_status"]. Private rows get light-blue (#B3E5FC) and Missing rows get light-gray (#E0E0E0) background overrides ahead of match-quality colors. lb_status stored in sum_user_data per row.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Added

backend/folder_naming.py: New module. `apply_nft_suffix(name, lb_status)` appends -NFT when lb_status='private', idempotent, case-normalises existing suffix. `strip_nft_suffix(name)` removes trailing -NFT. `has_nft_suffix(name)` predicate. `nft_discrepancy(folder_name, lb_status)` returns 'missing'|'stale'|'unknown'|None for discrepancy detection.

backend/db.py: `should_mark_nft(lb_number)` returns True when lb_status='private'. `lookup_checksums()` now annotates each detail item with `lb_status` from lb_master via a single batch lookup, making the status available to downstream callers (rename tab, etc.) without extra API calls.

gui/rename_tab.py: Imports `apply_nft_suffix`, `strip_nft_suffix`, `nft_discrepancy` from `backend.folder_naming`. `populate_from_lookup()` builds a `lb_status_map` from detail item annotations, applies NFT suffix to proposed names for Private LBs, proposes stripping -NFT for Public LBs that still have it, and escalates state to `needs_rename` when the proposed name differs from current. Multi-LB rows conservatively inherit `lb_status='private'` if any candidate LB is Private. `RenameModel.data()` overrides BackgroundRole and adds ToolTipRole for NFT discrepancy states (_NFT_DISC_COLORS / _NFT_DISC_TIPS). `_on_strip_wrong_lb()` also applies NFT suffix when rebuilding proposed names. Legend gains three new NFT-discrepancy swatches.

gui/collection_tab.py: `_get_standard_lb_name()` calls `/api/lb_master/<lb>/nft` and appends -NFT to the returned base name when the response is `{nft: true}`.

---

[2026-05-17] — feat(integrity): Re-scrape Private LBs button in Setup tab (TODO-017)

Added

backend/app.py: POST /api/scrape/private_rescrape — queries lb_master for all lb_status='private' rows, starts the scraper with force=True on those lb_numbers, returns {ok, total}. Uses existing _start_scrape_thread so standard /api/scrape/status polling applies.

gui/setup_tab.py: "Re-scrape Private LBs" button added as Row 3 in the Scraper section grid. Clicking it fetches the current private count from /api/lb_master/stats, shows a confirmation dialog with the count, and calls the new endpoint. Uses the existing _ScrapeStatusThread + _on_scrape_status machinery for progress/completion. On completion, fetches updated stats and appends "N promoted to Public, M private remain." to the status message. _on_scrape_all and _on_scrape_range now also disable this button while a scrape is running.

---

[2026-05-17] — feat(db): master/user data ownership split + master publish/install + curator mode (TODO-020)

Added

backend/db.py: MASTER_TABLES, USER_TABLES, MASTER_META_KEYS, USER_META_KEYS, MASTER_SCHEMA_VERSION constants formalise which tables ship in a master release and which stay local. New `is_curator()` / `set_curator()` helpers backed by `meta.is_curator='1'|'0'` (user-local, never shipped). New `export_master_db(reason)` produces a master-only snapshot in `data/exports/` via `VACUUM INTO` → drop every USER_TABLES table → filter `meta` to MASTER_META_KEYS → stamp `master_version` / `master_published_at` / `master_schema_version` → VACUUM → verify (no user tables, no non-master meta keys) → SHA256 → write `<file>.manifest.json` sidecar. New `import_master_db(snapshot_path)` validates the manifest SHA256, refuses incoming schema versions newer than this client, takes a `pre_master_import` backup, ATTACHes the snapshot, copies only MASTER_TABLES, replaces only MASTER_META_KEYS in `meta`, rebuilds the `entries_fts` virtual table, and returns a summary (row counts, pre/post status distribution, backup path).

backend/app.py: GET /api/curator and POST /api/curator endpoints toggle the curator flag (body `{enabled: bool}`). POST /api/master/export requires `is_curator=true` (returns HTTP 403 `error=curator_required` otherwise); returns `{ok, path, manifest_path, manifest}`. POST /api/master/import (body `{path}`) returns the import summary or 400/404 with `error=sha256_mismatch | schema_too_new | not_found`.

gui/setup_tab.py: New "Master Data" QGroupBox below Database. Curator-mode checkbox persists via `/api/curator`. Publish Master Update button (curator-only, gated by checkbox) runs the export and shows a confirmation dialog with version, sha256 prefix, row counts, status distribution, and override count. Install Master Update button opens a file picker (defaults to `data/exports/`) and applies the chosen snapshot with a pre/post status diff in the result dialog. New `_load_curator_status()` called at init reflects the persisted flag in the UI.

tests/test_master_data.py: 13 pytest tests covering the MASTER/USER table constants and disjointness, MASTER_META_KEYS whitelist (no user keys leak), curator-flag round-trip, export-excludes-user-data, SHA256-matches-file-contents, version-stamping, end-to-end import preserves user collection + user meta keys (qbt_*, search_page_size, is_curator) while replacing master tables and master meta keys (import_hash, master_version), SHA-mismatch rejection (ValueError), schema-too-new rejection (RuntimeError), pre-import backup creation, and Flask 403 guard when curator mode is off.

---

[2026-05-16] — feat(integrity): lb_master status system, forum post guard, Search/Collection status columns, DB Editor integrity panel

Changed

backend/db.py: Added lb_master and lb_status_history tables to SCHEMA_SQL. Added backup_database(), migrate_lb_master(), reconcile_lb_status(), reconcile_all_lb_master(), set_lb_manual_override(), clear_lb_manual_override(), get_lb_master_row(), get_lb_master_stats(), get_lb_status(), is_postable_to_forum(), get_lb_master_list(), get_lb_status_history(). search_entries() now LEFT JOINs lb_master to return lb_status on every row. get_collection() and get_missing_from_collection() also return lb_status. migrate_lb_master() is called once from init_db() background thread and deletes entries.status='missing' tombstones after populating lb_master. lb_master.lb_status CHECK constraint enforces 'public'|'private'|'missing'. backup_database() uses VACUUM INTO with microsecond-precision timestamps to avoid filename collisions; keeps last 10 backups.

backend/app.py: Added 9 new endpoints: GET /api/lb_master/stats, GET /api/lb_master/<lb>, GET /api/lb_master, POST /api/lb_master/reconcile, GET /api/lb_master/history/<lb>, PUT /api/lb_master/<lb>/manual, DELETE /api/lb_master/<lb>/manual, GET /api/lb_master/<lb>/nft, POST /api/db/backup. Added forum post guard to preview_forum() and post_forum(): returns HTTP 403 with error=lb_private|lb_missing|status_unknown for non-public LBs.

backend/importer.py: After flat-file merge, calls migrate_lb_master() on first import (lb_master empty) or reconcile_lb_status() for every touched LB on subsequent imports.

backend/scraper.py: Calls reconcile_lb_status() after every scrape_entry() success and 404, wiring the scraper into the lb_master lifecycle.

gui/search_tab.py: Added "Status" column (col 1) to HEADERS. Replaced "Missing only" checkbox with LBStatusComboBox-style QComboBox (All statuses / Public only / Private only / Missing only / Needs review). _filtered_results() uses the status combobox. Background coloring now reads lb_status from result rows (public=default, private=light blue #B3E5FC, missing=light gray #E0E0E0).

gui/collection_tab.py: Added "Status" column (col 1) to COLL_HEADERS and MISS_HEADERS. _CollectionModel.data() and _MissingModel.data() display lb_status and apply matching background colors. _on_post_forum() adds a hard blocking modal dialog for private/missing LBs before attempting any network call. _on_post_forum_done() surfaces backend 403 forum-guard errors with the same modal (handles stale-status race).

gui/dbedit_tab.py: Added "DB Integrity" QGroupBox to the left panel with: live stats label (Public/Private/Missing/Max/Overrides/Needs Review), Reconcile All button (→ POST /api/lb_master/reconcile with confirmation), Show Needs Review button (selects lb_master + applies needs_review:1 search), Backup DB Now button (→ POST /api/db/backup with result dialog). load_tables() now also calls load_integrity_stats().

Added

tests/test_lb_master.py: 27 pytest tests covering schema creation, migrate_lb_master idempotency and status precedence, reconcile_lb_status transitions and override respect, stats counts, importer integration, is_postable_to_forum logic, Flask forum endpoint guard (HTTP 403 for private/missing), and GUI column/widget presence checks (skipped without DISPLAY).

[2026-05-16] — fix(gui): crash on theme apply due to non-existent self.table reference

Fixed

gui/collection_tab.py: resize_columns_to_font() referenced self.table, which only exists on the unrelated _ScanPreviewDialog class — not on CollectionTab. Caused AttributeError on every theme/font change and aborted the app. Removed the stray block; the other view/table resizes were already covering CollectionTab's real widgets.

---

[2026-05-16] — feat(gui): resize table columns to fit whenever font size changes

Added

gui/search_tab.py: resize_columns_to_font() — calls resizeColumnsToContents() on the search results view.
gui/collection_tab.py: resize_columns_to_font(font_size) — resizeColumnsToContents() on coll/miss/wish views and the LB lib table; scales torrent_history_table and forum_posts_table hardcoded pixel widths by font_size/9.
gui/dbedit_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the data table.
gui/lookup_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail views.
gui/rename_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the rename view.
gui/verify_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/lbdir_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/main_window.py: _on_theme_applied() now reads the current font size from theme_tab and calls resize_columns_to_font() on every tab after applying the stylesheet.

---

[2026-05-16] — feat(dbedit): add LB# search field to DB Editor toolbar

Added

gui/dbedit_tab.py: "LB#:" label + lb_input QLineEdit (width 80px) added to the toolbar between "Load Records" and the text search field. Pressing Enter in the field triggers the search; the field is cleared on table switch and "Load Records".
backend/app.py: dbedit_rows now accepts an optional lb_number query param; when the table has an lb_number column and the value is a valid integer, it appends AND lb_number = ? to the WHERE clause (combinable with the existing text search).

---

[2026-05-16] — feat(gui): add font family and font size controls to the Themes tab

Added

gui/styles.py: build_stylesheet() and apply_theme() now accept font_family and font_size keyword args; the chosen font is prepended to the platform stack and the size replaces the hardcoded 9pt.
gui/theme_tab.py: Font row (QComboBox + QSpinBox) inserted in _build_ui() below the colour swatches; _on_apply(), _save_settings(), and load_and_apply_saved() wired to read, persist, and restore font settings via QSettings keys theme/font_family and theme/font_size.

Changed

gui/search_tab.py: _prev_btn / _next_btn setFixedWidth(80) → setMinimumWidth(80) so buttons expand at larger font sizes.
gui/collection_tab.py: _coll_prev_btn / _coll_next_btn setFixedWidth(80) → setMinimumWidth(80).
gui/dbedit_tab.py: prev_btn / next_btn setFixedWidth(70) → setMinimumWidth(70).

---

[2026-05-16] — fix(db): searching a bare integer now always returns the matching lb_number entry

Fixed

backend/db.py: After the FTS5 search in search_entries, if the query is a bare integer and the matching lb_number is not already in the FTS results, a direct lb_number lookup is performed and the matching entry is prepended. Fixes entries like LB-01797 (Paris, 7/6/78) that have a webpage and metadata but no text fields containing their own lb_number, making them invisible to numeric search queries.

---

[2026-05-16] — fix(db): redefine "missing" as entries with no webpage, not entries with no checksums

Fixed

backend/db.py: get_missing_lb_numbers now queries entries.status instead of the checksums table. An entry is missing only when status='missing' (scraper confirmed no page) or the lb_number was never scraped. Entries with status='ok' are real entries and are never returned as missing even if they have no checksums or attachments (e.g. LB-12404). Previously the function returned any lb_number in range 1..max_lb absent from the checksums table, which incorrectly included hundreds of real entries that simply have no downloadable content.

---

[2026-05-16] — fix(attachments): tree page change glitches — viewport not reset after clear

Fixed

gui/attachments_tab.py: _render_tree_page now calls scrollToTop() after populating the new page so the viewport always lands at the top. Also wrapped clear+populate in setUpdatesEnabled(False/True) to suppress incremental repaints during the bulk insert, eliminating visual tearing.

---

[2026-05-16] — feat(attachments): paginate cached LB tree to 1000 entries per page with prev/next buttons

Added

gui/attachments_tab.py: Added PAGE_SIZE = 1000 class constant and _page / _all_lb_dirs state. Split _refresh_tree into a collector phase (builds sorted list of non-empty LB dirs) and _render_tree_page (populates tree for the current page slice). Added ◀ Prev / page label / Next ▶ navigation row that auto-shows in cached view and hides in missing view. _jump_to_lb now calculates the target page from _all_lb_dirs and navigates there before scrolling. Buttons are disabled when at the first or last page.

---

[2026-05-16] — fix(attachments): move WebEngine warmup to app startup instead of first tab visit

Fixed

gui/attachments_tab.py: QWebEngineView initialization (and about:blank warmup) now scheduled via QTimer.singleShot(0) in __init__ so it fires on the first event-loop tick after the main window appears — while the user is still on the Lookup tab — rather than on the first Attachments tab visit. Removed _web_initialised flag and the lazy-init block from showEvent. Added early-return guard in _init_web_view to prevent double-init. Removed the fallback _init_web_view() call from _open_lb_in_webview since the view is always ready by the time the user can interact.

---

[2026-05-16] — fix(main): disable Chromium GPU process to fix full-window blackout and GBM format errors on Linux

Fixed

main.py: Added --disable-gpu to QTWEBENGINE_CHROMIUM_FLAGS. Chromium's GPU process was hijacking the shared OpenGL context (AA_ShareOpenGLContexts) on Qt 6.7/XWayland, causing the entire application window to flash black. --disable-gpu prevents the GPU process from starting; Chromium uses Swiftshader software rendering instead, which is sufficient for the simple pages this app displays. Also eliminates the spurious "Unknown or not supported format: 808530000" (P010 GBM probe) stderr errors.

---

[2026-05-16] — fix(attachments): warm up WebEngine GPU process on tab open to prevent first-load window flash

Fixed

gui/attachments_tab.py: Loading about:blank immediately after QWebEngineView is added to the stack during _init_web_view. This forces the GPU/renderer subprocess to start while the tab is quietly initialising rather than on the first user-triggered URL load, eliminating the native-window flash on Linux.

---

[2026-05-16] — feat(attachments): right-click "Open in browser pane" on tree and missing list

Added

gui/attachments_tab.py: Right-click context menu on both the cached tree and the missing list shows "Open LB-NNNNN in browser pane". Selecting it loads the DETAIL_URL for that entry directly into the embedded QWebEngineView (right panel) instead of opening an external browser. DETAIL_URL imported from backend.scraper; QUrl moved to top-level import and removed from inline lazy import in _preview_file.

---

[2026-05-16] — feat(attachments): Missing LB list with scrape capability

Added

backend/db.py: get_missing_lb_numbers() — returns list of integers in range 1..max_lb absent from the checksums table.
backend/app.py: GET /api/db/missing_lb_numbers route backed by get_missing_lb_numbers().
gui/attachments_tab.py: _MissingThread fetches missing list from backend. Left panel now has Cached/Missing toggle buttons that swap a QStackedWidget between the existing tree and a new QListWidget. Jump-to search box works in both views. "Scrape Selected Entry" button in Missing view calls the same _ScrapeThread; on success the entry is removed from the missing list and the cached tree is marked stale. "No attachments found" status confirms true gaps.

---

[2026-05-16] — fix(gui): xref checkbox — search adds Xref column; collection filters on owned xref folders only

Changed

gui/search_tab.py: Added "Xref" column (col 5) to the search results table showing which xref numbers exist for each entry. _XrefWorker now calls GET /api/checksums/xref_map (returns {lb: [xref_values]}) instead of the bare LB list; SearchModel gains _xref_map and set_xref_map(); _on_xref_loaded converts string JSON keys to ints and pushes the map to the model.

gui/collection_tab.py: "Xref only" checkbox now filters to collection entries where the folder_name contains "xref" (i.e., the user has an xref-named folder in their collection). Previously it filtered on whether the LB exists in the master DB xref list, which was wrong — it showed any LB that has xref variants, not specifically the entries the user collected as xref folders.

backend/db.py: Added get_xref_map() — returns {lb_number: [xref_val, ...]} for all lb_numbers with xref checksums.

backend/app.py: Added GET /api/checksums/xref_map route backed by get_xref_map().

---

[2026-05-16] — feat(gui): attachments tab layout overhaul — wider tree, stat label moved, LB jump-to search box

Changed

gui/attachments_tab.py: Moved the "Entries with cached files" stat label into the left panel (above the tree) so it no longer floats in dead space. Splitter initial sizes changed from 300/700 to 420/580 to give the tree more room. Outer VBoxLayout now uses stretch=1 on the splitter so it fills the full widget height. Added QLineEdit + "Go" button at the bottom of the left panel to jump the tree selection to a typed LB number (accepts plain digits, "LB-NNNNN", or "LBNNNNN").

---

[2026-05-16] — feat(gui): add Forum History and Torrent History tabs to My Collection

Added

gui/collection_tab.py: Two new inner tabs ("Forum History" and "Torrent History") beside Duplicates. Each shows a global, all-entry table loaded lazily on first activation with a Refresh button. Forum History shows LB#, Date, Location, Posted timestamp, Subject with Open in Browser and Remove Record actions and a right-click context menu. Torrent History shows LB#, Date, Location, Created timestamp, Source Folder, Added to qBt status. Right-click on either table offers "Go to LB-XXXXX in My Collection" navigation.

backend/db.py: Added get_all_forum_posts() and get_all_torrents() — full-table queries joined with entries for date_str and location.

backend/app.py: Added GET /api/forum_posts and GET /api/torrents routes.

---

[2026-05-16] — feat(gui): add hover highlight to tab bar tabs

Added

gui/styles.py: Added `QTabBar::tab:hover` rule that blends `tab_bg` halfway toward `tab_selected` using the existing `_blend_hex()` helper, giving a subtle visual cue as the mouse moves over inactive tabs without affecting the selected tab's appearance.

---

[2026-05-16] — fix(gui): button text color now auto-contrasts against accent instead of using header_fg

Fixed

gui/styles.py: `QPushButton` text was hardcoded to `{t['header_fg']}` (Table Header Text), which had no logical connection to buttons and gave wrong results on many themes. Added `_button_text_color()` which picks black or white based on the accent's luminance — the same approach the theme swatch labels use. Each button state (normal, hover, pressed) now gets its own computed text color.

---

[2026-05-16] — fix(gui): disabled buttons now match the active theme instead of rendering as hardcoded gray

Fixed

gui/styles.py: `QPushButton:disabled` was hardcoded to `#A0A0A0` / `#E0E0E0` regardless of theme. On dark themes like Tokyo Night the gray buttons clashed visually with the dark background. Added `_blend_hex()` helper and replaced the hardcoded values with theme-derived colors (accent blended 65% toward app_bg for background, app_fg blended 55% toward app_bg for text).

---

[2026-05-16] — feat(gui): move theme swatches to left side and split into 2-column grid

Changed

gui/theme_tab.py: Restructured `_build_ui` so the swatch panel sits immediately right of the preset list (no right-side expansion). The `QGridLayout` now uses 4 columns (label-A | swatch-A | label-B | swatch-B), distributing the 22 color entries across 11 rows × 2 columns. Added `layout.addStretch()` at the end so the panels stay left-anchored.

---

[2026-05-16] — fix(gui): search tab column widths no longer reset to 100px on every launch

Fixed

gui/search_tab.py: Added `_widths_applied` flag to guard the pre-reset snapshot in `_render_page()`. The snapshot was executing before `_apply_col_widths()` had ever run, so Qt's 100px default widths overwrote the values loaded from QSettings, destroying saved preferences. The snapshot is now skipped until widths have been applied at least once.

---

[2026-05-16] — fix(scraper): use correct SMF form field name "description" instead of "desc"

Fixed

backend/forum_poster.py: Changed "desc": lb_id to "description": lb_id in both the initial POST payload and the retry payload. The SMF modify/post form uses name="description" (confirmed from live page source); the previous key "desc" was silently ignored by the server, so the LB number never appeared in the topic description field. Updated debug log line to match.

---

[2026-05-16] — feat(gui): add 7 new preset themes (Nord, Gruvbox, Monokai, Tokyo Night, Solarized, Everforest, Catppuccin)

Added

gui/theme_tab.py: Nord (Arctic blue-gray), Gruvbox (earthy retro dark), Monokai (vivid dark with cyan accents), Tokyo Night (neon city dark), Solarized (precision warm light), Everforest (forest dark-green), Catppuccin Mocha (soft pastel dark). All 14 row-color keys verified for luminance contrast against each theme's table background. Preset list now shows 14 named themes plus Custom.

Changed

PROJECT.md: Updated Theme Tab description from "Six preset themes" to fourteen.

---

[2026-05-15] — fix(gui): search-tab "missing" row hardcoded yellow; dark-theme row luma audit

Fixed

gui/search_tab.py: Hardcoded QColor("#FFFF99") for status=="missing" rows didn't respect the active theme. Added module-level `import gui.styles as styles`; replaced hardcoded color with `styles.ROW_MISSING` and replaced lazy per-call `from gui.styles import ROW_OWNED` with `styles.ROW_OWNED`. "Row: Missing" in the theme editor now controls search-tab missing-entry rows.
gui/theme_tab.py: Audited all dark-theme row colors for luminance contrast against their table backgrounds. Fixed Dark (row_missing/row_xref/row_owned/row_wishlist all had luma at or below table_bg=58), Black (row_xref luma=20 identical to table_bg; row_missing/row_wishlist below table_alt=28), and Dracula (row_xref/row_missing/row_wishlist at or below table_bg=43). Also fixed Red theme row_xref. Removed unused QApplication import.

---

[2026-05-15] — feat(lbdir): Remove Extra Files — delete disk files not listed in the lbdir, with confirmation dialog

Added

backend/checksum_utils.py: Added find_extra_files(folder_path, lbdir_path) — parses lbdir MD5 section, scans folder recursively, returns files not in the expected set (lbdir file itself excluded).
backend/app.py: Added POST /api/lbdir/find_extra (list extra files per folder) and POST /api/lbdir/delete_extra (unlink selected files by relative path, then prune empty subdirectories).
gui/lbdir_tab.py: Added _LbdirFindExtraWorker and _LbdirDeleteExtraWorker workers. Added ExtraFilesDialog — checkable file list with red delete button and warning label; never deletes without explicit user confirmation. Added "Remove Extra Files" button; handlers re-run Check lbdir Files after deletion.

---

[2026-05-15] — fix(gui): dark-theme row colors always showed light-theme green/purple; add Red theme

Fixed

gui/collection_tab.py: `from gui.styles import ROW_OWNED, ROW_WISHLIST` captured the values at import time; reassignment inside apply_theme() never propagated. Replaced with `import gui.styles as styles` and updated both usages to `styles.ROW_OWNED` / `styles.ROW_WISHLIST`.
gui/lookup_tab.py: Same stale-import bug for ROW_MATCHED/ROW_NOT_FOUND/ROW_MISSING/ROW_DUPLICATE/ROW_XREF. Replaced top-level `from gui.styles import …` with `import gui.styles as styles`; updated all 10 bare references to `styles.ROW_*`; removed redundant lazy `from gui import styles` inside refresh_colors().
gui/styles.py: apply_theme() now updates ROW_WISHLIST global (was never updated on theme switch). Added row_wishlist to the default apply_theme call at module load.
gui/theme_tab.py: Added row_owned and row_wishlist to every theme with dark-appropriate colors for Dark/Black/Dracula. Added both to COLOR_LABELS so they appear in the theme editor.

Added

gui/theme_tab.py: New "Red" dark theme — crimson/dark-red palette with dark-appropriate row colors.

---

[2026-05-15] — fix(gui): suppress GBM "Unknown format" stderr noise from Chromium GPU process

Fixed

main.py: Added --disable-features=VaapiVideoDecoder to QTWEBENGINE_CHROMIUM_FLAGS so Chromium's GPU process no longer probes unsupported hardware video-decode pixel formats (P010/HDR) via GBM, eliminating repeated "Unknown or not supported format: 808530000" stderr errors on Linux.

---

[2026-05-15] — feat(lbdir): Reconcile Files — match missing lbdir entries to disk files by MD5 and propose renames

Added

backend/checksum_utils.py: Added find_reconcilable_files(folder_path, lbdir_path) — parses lbdir MD5 section, identifies entries not on disk, scans all disk files recursively for MD5 matches, returns proposals/unmatched_lbdir/unmatched_disk/warnings.
backend/app.py: Extracted _find_lbdir_in_folder() module-level helper (DRY refactor of lbdir_check and lbdir_retrieve inline lbdir detection). Added POST /api/lbdir/reconcile (preview, read-only) and POST /api/lbdir/apply_reconcile (shutil.move renames, creates subdirs, never deletes).
gui/lbdir_tab.py: Added _LbdirReconcileWorker and _LbdirApplyReconcileWorker QThread workers. Added ReconcilePreviewDialog (checkable table of From→To proposals, Select All/Deselect All, Apply Selected/Cancel). Added "Reconcile Files" button; _on_reconcile, _on_reconcile_done, _apply_reconcile, _on_apply_reconcile_done handlers; re-runs Check lbdir Files after apply.

---

[2026-05-15] — fix(backend): _parse_date swapped month/day — forum post subjects used YYYY-DD-MM instead of YYYY-MM-DD

Fixed

backend/torrent_maker.py: _parse_date was treating parts[0] as day and parts[1] as month (D/M/YY, European), but LosslessBob stores dates in M/D/YY (US) format. Swapped variable assignment so month=parts[0], day=parts[1]. Updated docstring. All subject lines generated from _parse_date (forum posts and torrent names) now produce correctly ordered ISO dates.

---

[2026-05-15] — feat(gui): "Best match only" checkbox in Lookup summary — hides secondary DUPLICATE/INCOMPLETE rows when a full MATCHED result exists

Added

gui/lookup_tab.py: Added "Best match only" QCheckBox (default checked) to the Summary header row. When enabled and at least one summary row is MATCHED, _apply_filters() suppresses all non-MATCHED summary rows and their corresponding detail rows. Unchecking restores the full view. Toggle is instant with no re-lookup required.

---

[2026-05-15] — fix(main): force XWayland (xcb) on Linux to prevent fatal Wayland EGL crash

Fixed

main.py: Set QT_QPA_PLATFORM=xcb before QApplication construction on Linux when not already overridden. Native Wayland + AA_ShareOpenGLContexts + QtWebEngine can produce an unrecoverable EGL_BAD_NATIVE_WINDOW (0x300d) error that kills the Wayland connection (BUG-053). XWayland is stable for this workload with no functional loss.

---

[2026-05-15] — fix(gui): suppress Chromium stderr noise and fix WebEngine profile teardown-order warning on exit

Fixed

main.py: Set QTWEBENGINE_CHROMIUM_FLAGS=--disable-logging before QApplication is created to silence Chromium sandbox and path-override diagnostics that bypass Python logging.
gui/attachments_tab.py: Removed Qt parent from QWebEngineProfile so its lifetime is not tied to the tab's child list. Connected QApplication.aboutToQuit to new _cleanup_webengine() which uses sip.delete() to force destruction order view → page → profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning (BUG-026 reopened and re-fixed).

---

[2026-05-15] — fix(backend): summary row for superseded duplicate LB shows DUPLICATE (yellow) not INCOMPLETE (pink)

Fixed

backend/db.py: After building the per-LB summary, any LB where every matched detail item is still a duplicate (none promoted by resolution) now gets status "DUPLICATE" instead of "INCOMPLETE". This prevents a secondary LB that shares some checksums with the winning LB from appearing as if the user is missing files — it is correctly shown as a yellow duplicate entry alongside the green MATCHED winner.

---

[2026-05-15] — fix(backend): xref lookup completeness — evaluate per (lb, xref) group so full xref match shows MATCHED not INCOMPLETE

Fixed

backend/db.py: lookup_checksums reverse lookup now tracks matched checksums per (lb_number, xref_value) group and queries completeness against that specific xref group (`WHERE lb_number=? AND xref=?`) instead of the whole primary set (`AND xref=0`). A recording that provides all checksums for xref variant N is now correctly shown as MATCHED (green). The summary missing_from_set count is aggregated across all xref groups that had matched items.

---

[2026-05-15] — feat(backend): populate SMF Description field with LB number when posting to forum

Added

backend/forum_poster.py: `lb_id` is now computed unconditionally before the subject branch; `"desc": lb_id` added to both the initial payload and the retry payload so the SMF topic Description (Optional) field is populated with e.g. "LB-10002".

---

[2026-05-15] — fix(backend): lbdir xref file detection — match 'lbdir' anywhere in filename, not just at start

Fixed

backend/app.py: lbdir_check and lbdir_retrieve._find_lbdir now use `'lbdir' in f.name.lower()` instead of `startswith('lbdir')` so xref lbdir files named LBF-XXXXX-xref-NNNN-lbdir.txt are correctly found in both local folders and the attachment cache.

---

[2026-05-15] — feat(backend/gui): torrent history context menu — Remove from qBittorrent + Delete .torrent file from disk

Added

backend/qbittorrent.py: remove_torrent() — calls POST /api/v2/torrents/delete with deleteFiles=false so only the qBt entry is removed; audio files on disk are untouched.
backend/app.py: POST /api/torrent/<id>/qbt_remove — removes from qBt via infohash, clears added_to_qbt in DB on success. DELETE /api/torrent/<id>/file — deletes the .torrent file from disk, clears torrent_path in DB.
gui/collection_tab.py: Added separator + two new context menu actions to torrent history: "Remove from qBittorrent" (disabled when no infohash stored) and "Delete .torrent File from Disk" (disabled when file doesn't exist). Both show a confirmation dialog, refresh the history panel on completion, and update the status label.

---

[2026-05-15] — feat(backend/gui): log forum posts to DB; consolidated History panel with Torrents + Forum Posts tabs; LB detail hyperlink in post header

Added

backend/db.py: forum_posts table (lb_number, subject, topic_url, board_id, posted_at). Added add_forum_post(), get_forum_posts_for_lb(), delete_forum_post() functions.
backend/app.py: post_forum route now calls database.add_forum_post() on success. Added GET /api/entry/<lb>/forum_posts and DELETE /api/forum_post/<id> routes.
backend/forum_poster.py: LB-XXXXX tag in post header is now a [url=...] hyperlink to the LB detail page on losslessbob.wonderingwhattochoose.com.
gui/collection_tab.py: Replaced separate Torrent History and Forum Post History group boxes with a single "History" QGroupBox containing a QTabWidget (Torrents tab + Forum Posts tab). Forum Posts tab shows posted date, subject, URL with Open in Browser and Remove Record buttons. After a successful post the tab switches to Forum Posts automatically. Removed unused QSplitter import.

---

[2026-05-15] — feat(gui): My Collection context menu now has "Generate Spectrograms" action that sends selected folders to the Spectrograms tab

Added

gui/collection_tab.py: Added `send_to_spectrograms = pyqtSignal(list)` signal; added "Generate Spectrograms" action to `_on_coll_context` — visible only when one or more selected rows have a valid `disk_path` directory. Emits the list of paths.

gui/main_window.py: Connected `collection_tab.send_to_spectrograms` to `_on_send_to_spectrograms` which calls `spectrogram_tab._add_folders(folders)` then switches to the Spectrograms tab.

---

[2026-05-15] — fix(backend): forum poster comprehensive reliability overhaul — correct POST URL, hidden-element guards, Firefox UA, board-redirect success on both paths

Changed

backend/forum_poster.py: (1) Removed _post_url() — was hardcoding action=post;sa=post2 which is the wrong SMF handler; the form's own action= attribute is now the authoritative POST URL. _scrape_form_fields() now returns (fields, form_action, diag) and _find_post_form() extracts the action URL directly. (2) post_lb_topic() now posts with allow_redirects=False so the raw Location header can be inspected before following any redirect. (3) Board-redirect success detection: SMF on this forum signals a successful new topic with a 302 → board=N.0 redirect (not topic=), so both the initial post and the retry path now detect this, follow the board URL sorted by first_post desc, and call _find_newest_topic() to return the correct topic link. (4) Lock-warning check now calls _is_element_hidden() before treating #lock_warning as a real warning — the element is present (display:none) on every compose page and was incorrectly firing the retry path on every failed post. (5) _extract_smf_error() now skips hidden elements for the same reason — the empty errorbox present on every compose page was generating phantom SMF error strings. (6) Removed not_approved from payload — not a real SMF field. (7) User-Agent updated to a current Firefox/126.0 string to avoid UA-based blocking.

---

[2026-05-15] — fix(gui): torrent history section no longer expands to fill space; collection table now stretches correctly

Changed

gui/collection_tab.py: Added stretch=1 to the coll_view addWidget call so the collection table claims all available vertical space, keeping the Torrent History group compact at the bottom.

---

[2026-05-15] — feat(gui): Post to Forum auto-creates torrent and adds to qBittorrent if none exists

Changed

gui/collection_tab.py: _on_post_forum now checks for an existing torrent file before building the preview. If none is found it calls /api/torrent/create (using the collection row's disk_path as source_folder), then /api/qbt/add to seed it, then proceeds with the normal preview → confirm → post workflow. If creation fails the error is surfaced in the status bar. qBittorrent add failures are non-fatal — the post proceeds regardless.

---

[2026-05-15] — fix(backend/gui): wrong topic URL in success popup; torrent history stale after auto-create

Fixed

backend/forum_poster.py: _find_newest_topic now uses a three-pass strategy: (1) subject-text match — finds the link whose visible text contains the posted subject, immune to sticky ordering; (2) first non-sticky link — skips <tr>/<div>/<li> ancestors whose class includes "sticky"; (3) last resort, first topic= link found. Subject is now threaded through from post_lb_topic into both the initial-post and retry board-redirect paths.
gui/collection_tab.py: Added _history_gen counter to _load_torrent_history/_populate_torrent_history so stale API responses (earlier load completing after a newer one) are discarded instead of overwriting fresh data. _on_preview_forum_ready now triggers a history refresh so a torrent auto-created during forum-post pre-flight appears immediately without requiring a re-selection.

---

[2026-05-15] — fix(backend): post-success topic URL wrong — board page returns busiest thread, not newest

Fixed

backend/forum_poster.py: _find_newest_topic was picking the first topic= link on the board listing page, which is sorted by last-reply date by default. A busy thread bumped after our post appeared first, returning the wrong URL. Added _board_url_sorted() which appends sort=first_post;desc=1 to the board redirect URL before fetching it, ensuring our newly created topic is always at the top. Applied to both the first POST and retry code paths.

---

[2026-05-15] — fix(backend): forum post line breaks stripped; redesign header with size/hr/red LB number, remove broken spoiler tag, normalise CRLF

Changed

backend/forum_poster.py: (1) Normalise body to \r\n before placing it in the multipart/form-data payload — bare \n is silently stripped by SMF when the request is multipart-encoded due to a file attachment. Applied to both first POST and retry payload. (2) Metadata header now wrapped in [size=13pt] for visibility, LB number appended in [color=red][b]...[/b][/color], followed by [hr] on the next line. (3) Replaced non-working [spoiler=Checksums] with plain [b]Checksums[/b] + [code] block. (4) Footer separated by [hr] above it.

---

[2026-05-15] — feat(backend): redesign forum post body format with structured header, LB txt content, spoilered lbdir checksums, and footer attribution

Changed

backend/forum_poster.py: Replaced the raw-file-dump approach in _build_body with a structured BBcode format. New format: (1) bold labeled metadata header (Date | Location | CDR | Rating | Timing) from entry dict; (2) content from the LB-numbered txt file in the attachment dir (first header line skipped), falling back to entry.description; (3) lbdir checksum manifest in a [spoiler=Checksums][code] block at the end; (4) italicised grey "Brought to you by kuddukan, via the Bob-O-Matic v1.0." footer. Added _read_lb_txt and _read_lbdir helper functions. Updated preview_lb_topic and post_lb_topic to pass lb_number into _build_body.

---

[2026-05-14] — fix(backend): retry payload overrode lock=0, re-introducing the warning it was meant to clear

Fixed

backend/forum_poster.py: The warning page returned by SMF includes lock=1 (server-corrected to match the board's requirement). The retry payload was explicitly overriding lock=0, reintroducing the mismatch that caused the warning on the first POST and making the retry fail identically. Removed lock/sticky/move overrides from the retry payload so the warning page's corrected values pass through. Also removed them from the first POST payload where they were pointless.

---

[2026-05-14] — fix(backend): SMF board lock warning requires confirmation resubmit — add automatic retry

Fixed

backend/forum_poster.py: Board 16 is configured for admin/mod-only posting, so SMF always returns a "warning preview" page asking for confirmation instead of creating the topic immediately. The attachment is already temp-stored server-side at this point. Added lock-warning detection: re-scrapes fresh hidden fields (new seqnum/CSRF) from the warning page and resubmits without the file on a second POST.

---

[2026-05-14] — fix(backend): admin compose page sets lock=1, causing SMF to bounce post with a lock warning

Fixed

backend/forum_poster.py: Admin users' compose pages have lock=1 pre-set as a hidden field. SMF treats this as a locked-topic flag and returns the form with a warning instead of creating the topic. Override lock, sticky, and move to 0 in the payload so admin-default hidden values don't affect the new topic.

---

[2026-05-14] — fix(backend): board ID missing from POST URL — SMF rejected every post as "board doesn't exist"

Fixed

backend/forum_poster.py: _POST_URL was a static constant without a board parameter. SMF requires the board in the POST URL (action=post;sa=post2;board=N.0) just as it does in the compose URL. Replaced _POST_URL with _post_url(board_id) that mirrors _compose_url(board_id).

---

[2026-05-14] — fix(backend/gui): hardcoded forum board ID replaced with configurable setting

Changed

backend/forum_poster.py: Removed FORUM_BOARD=16 constant and module-level _COMPOSE_URL. post_lb_topic() now accepts board_id: int and builds the compose URL dynamically. _scrape_form_fields() accepts compose_url as a parameter.
backend/app.py: wtrf_board_id added to /api/db/settings GET key list. post_forum route reads board_id from meta and returns a clear error if unset.
gui/setup_tab.py: Board ID QSpinBox added to WTRF section (row 2). Saved via _on_wtrf_board_changed on change; loaded in _load_wtrf_settings from /api/db/settings.

---

[2026-05-14] — feat(main): write app module logs to data/losslessbob.log (rotating, 5 MB × 3)

Added

main.py: _configure_logging() installs a RotatingFileHandler on data/losslessbob.log. Root logger stays at WARNING (keeps urllib3/requests/werkzeug quiet); backend.* and gui.* namespaces are set to DEBUG so all our module logging lands in the file.

Added

main.py: _configure_logging() sets up a RotatingFileHandler on data/losslessbob.log (DEBUG level, 5 MB × 3 backups) and a stderr StreamHandler (WARNING+). Called at startup before Flask thread starts so all backend modules log to file from the first request.

---

[2026-05-14] — fix(backend): forum post reports false success — SMF rejects submission silently

Fixed

backend/forum_poster.py: post_lb_topic() was reporting success on any HTTP 200 response, but SMF returns 200 when it bounces the post back to the compose form (e.g. CSRF failure, attachment rejection). Fixed success detection to require 'topic=' in the final URL (the redirect SMF sends only on a real post). Added Referer and Origin headers to the POST request so SMF's CSRF check passes. Added additional_options=1 to the payload so SMF processes the attachment field. Improved error reporting: collects errorbox/error_list/post_error div text, and returns the page title + URL as fallback so the failure reason is always visible.

---

[2026-05-14] — fix(backend): forum post blocked by hardcoded 'sc' field check — WTRF uses hashed CSRF token name

Fixed

backend/forum_poster.py: WTRF's SMF install uses a dynamically-hashed field name for the CSRF token (e.g. 'a9c55b28') instead of the literal 'sc'. Removed the 'sc' presence check; seqnum alone is used to confirm the post form was found. All hidden fields including the hashed token were already forwarded via **hidden, so the post itself was correct. Also added diagnostic output to the error message and improved form-field scraping to target the post form specifically.

---

[2026-05-14] — fix(backend): forum post fails with "sc/seqnum missing" — compose page redirect not detected

Fixed

backend/forum_poster.py: _scrape_form_fields now detects when SMF silently redirects the compose URL to the login page (unauthenticated session) and returns empty instead of scraping login-form fields. Added targeted post-form lookup by action attribute so unrelated hidden inputs on the page don't pollute the result. Added Referer header to the compose-page request. Validation now reports exactly which fields are absent (sc vs seqnum).

---

[2026-05-14] — fix(gui): torrent history panel now refreshes after torrent creation

Fixed

gui/collection_tab.py: _on_torrent_done() never called _load_torrent_history(), so the history panel stayed empty after creating a torrent until the user re-selected the entry. Now reloads history for the currently-displayed LB after a successful create.

---

[2026-05-14] — fix(scraper): fetch tracker list from raw GitHub instead of jsDelivr CDN

Fixed

backend/torrent_maker.py: jsDelivr caches GitHub content and can lag by hours/days. Switched _TRACKER_CDN to raw.githubusercontent.com so the tracker list is always current. Also removed unused json import.

---

[2026-05-14] — fix(backend): handle qBittorrent 5 JSON response for torrents/add

Fixed

backend/qbittorrent.py: qBittorrent 5+ returns a JSON object from /api/v2/torrents/add instead of plain "Ok.". Added a JSON fallback check (failure_count==0 and success_count>0) so successful adds are no longer reported as failures.

---

[2026-05-14] — feat: qBittorrent API key authentication (qBittorrent 5+)

Added

backend/credentials.py: SERVICE_QBT_KEY constant for keyring storage of the API key.
backend/qbittorrent.py: api_key parameter on test_connection(), add_torrent_for_seeding(), and add_torrent_from_db(). When set, a Bearer token header is used and the login/logout flow is skipped entirely. Refactored shared session setup into _make_session() and login logic into _login().
backend/app.py: /api/qbt/test and /api/qbt/add routes now retrieve and forward the stored API key; api_key takes priority over username/password.
gui/setup_tab.py: API Key field added to the qBittorrent section (row 2, password-masked, spanning full width). Save/Clear/Test/Load handlers all updated to prefer the API key when filled.

---

[2026-05-14] — fix(backend): add Origin+Referer headers to qBittorrent login, improve error detail

Fixed

backend/qbittorrent.py: Added both Referer and Origin headers to test_connection() and add_torrent_for_seeding(). Fixed login check to accept HTTP 204 No Content (qBittorrent's response when "Bypass authentication for clients on localhost" is enabled) alongside the normal 200 "Ok." response. Error message now includes HTTP status code and shows "<empty>" for blank bodies.

---

[2026-05-14] — feat(gui/backend): Forum post preview dialog before submitting to WTRF

Added

backend/forum_poster.py: preview_lb_topic() builds subject + body without logging in or posting.
backend/app.py: GET /api/entry/<lb>/preview_forum returns {subject, body} for the GUI to display.
gui/collection_tab.py: "Post to Forum" now opens a preview dialog showing the subject and editable BBcode body; the post only fires after the user clicks "Post to Forum" in the dialog. Subject and body edits in the dialog are forwarded to the backend.
backend/forum_poster.py: post_lb_topic() accepts subject_override and body_override kwargs so user edits from the preview are used verbatim.

---

[2026-05-14] — fix(backend): WTRF forum login failures due to wrong domain and bad URL check

Fixed

backend/forum_poster.py: FORUM_BASE corrected from watchingtheriverflow.com to watchingtheriverflow.org.
backend/forum_poster.py: Login success check was matching "action=login" as a substring of "action=login2" (the POST endpoint), causing every login to be flagged as failed. Fixed to only treat a redirect back to the GET login page as failure. This forum returns 200 with empty body at login2 on success.
backend/forum_poster.py: _get_session now collects all hidden fields from the login form (not just hash_passwrd) to include sc and any other CSRF fields.

---

[2026-05-14] — fix(gui): WTRF and qBittorrent password fields blank on restart

Fixed

gui/setup_tab.py: _load_wtrf_settings and _load_qbt_settings now populate both username and password from keyring (was discarding password with _).

---

[2026-05-14] — feat(gui/backend): WTRF forum "Test Connection" button on Setup tab

Added

gui/setup_tab.py: _WtrfTestThread QThread; "Test Connection" button in the WTRF Forum group; _on_wtrf_test / _on_wtrf_test_finished handlers; green/red status label feedback.
backend/app.py: POST /api/wtrf/test — calls forum_poster._get_session() to verify credentials without posting. Falls back to stored keyring creds if body fields are empty.

---

[2026-05-14] — refactor(gui): setup tab two-column layout to eliminate wasted right-side space

Changed

gui/setup_tab.py: Replaced single-column lower section with a two-column QHBoxLayout. Left column holds Web Scraper and Scraper Log groups (stretch=3); right column holds qBittorrent, WTRF Forum, and Torrent Settings groups (stretch=2). Scraper log switched from fixed height to minimumHeight so it expands to fill available space.

---

[2026-05-14] — fix(checksum): rename generated checksum files from _lbgen to _mychecksums (TODO-014)

Changed

backend/checksum_utils.py: Renamed _lbgen_path() to _mychecksums_path(). All generated checksum files are now named <folder>_mychecksums.ffp / _mychecksums.md5 (incrementing to _mychecksums_2, etc.) instead of _lbgen.*. TORRENT_EXCLUDE in torrent_maker.py already matched this pattern — no change needed there.

---

[2026-05-14] — feat(collection): torrent history panel and path relocation flow (TODO-012, TODO-013)

Changed

gui/collection_tab.py: Added torrent history sub-panel to My Collection tab. Selecting a single entry loads all torrents table records via GET /api/torrent/<lb>. Each row shows a green/red/orange indicator (source_folder_exists / torrent_file_exists), created_at, torrent filename, source folder, and qBt added status. Regenerate button enabled when torrent file is missing. Relocate Source button opens folder browser, cross-checks folder contents against checksums for the entry, updates source_folder via PATCH /api/torrent/<id>, writes a rename_log.txt relocation entry, and optionally renames the folder to the standard YYYY-MM-DD Location (LB-XXXXX) format (calling write_rename_log + shutil.move). Added _STANDARD_LB_NAME_RE module constant. Added _build_torrent_history_panel(), _on_coll_selection_changed(), _load_torrent_history(), _populate_torrent_history(), _get_selected_history_record(), _on_history_context(), _history_add_record(), _on_history_qbt_done(), _history_regen_record(), _on_history_regen_done(), _history_relocate_record(), _cross_check_folder(), _get_standard_lb_name() methods.

---

[2026-05-14] — feat(phase1): Torrent generation, qBittorrent seeding, WTRF forum posting, credentials keyring, rename log

Changed

backend/db.py: Added torrents and rename_history tables to SCHEMA_SQL. Added get_torrents_for_lb(), add_torrent_record(), update_torrent_record(), add_rename_history() helpers.

backend/paths.py: Added TORRENTS_DIR = data/torrents/; ensure_data_dirs() now creates it.

requirements.txt: Added torf==4.3.1 and keyring==25.7.0 (+ transitive deps).

backend/app.py: Added POST /api/torrent/create, GET /api/torrent/<lb>, PATCH /api/torrent/<id>, GET /api/trackers, POST /api/qbt/test, POST /api/qbt/add, POST /api/entry/<lb>/post_forum. Extended GET /api/db/settings to include qbt_host, qbt_port, qbt_category, qbt_tags, tracker_list keys.

gui/rename_tab.py: Calls write_rename_log() before each shutil.move so every folder rename is recorded in rename_log.txt and rename_history.

gui/setup_tab.py: Added qBittorrent section (host, port, username/password, category, tags, Save/Test/Clear), WTRF Forum section (username/password, Save/Clear), and Torrent Settings section (tracker list selector, Refresh Trackers button).

gui/collection_tab.py: Added Create Torrent, Add to qBittorrent, and Post to Forum buttons to the My Collection panel.

Added

backend/credentials.py: Keyring-backed credential storage. SERVICE_QBT / SERVICE_WTRF constants. keyring_available(), save_credentials(), get_credentials(), delete_credentials(), credentials_stored(), prompt_if_missing().

backend/rename.py: write_rename_log() helper — appends a timestamped line to rename_log.txt and inserts a rename_history DB row. Used by rename_tab and (future) collection_tab path relocation.

backend/torrent_maker.py: torf-based .torrent generation. TORRENT_EXCLUDE rules (rename_log.txt, _mychecksums.*, .torrent, Thumbs.db, .DS_Store). fetch_trackers() fetches ngosang/trackerslist via jsDelivr CDN and caches per session. make_torrent() and make_torrent_batch().

backend/qbittorrent.py: qBittorrent WebUI API v2 integration. test_connection(), add_torrent_for_seeding(), add_torrent_from_db(). Sets save_path to parent of source_folder so seeding starts immediately.

backend/forum_poster.py: SMF 2.x HTTP session login + post. post_lb_topic() scrapes sc/seqnum fields, builds body from cached .txt/.ffp attachments (falls back to entry table), attaches .torrent as multipart POST.

[2026-05-14] — feat(rename/xref): Multiple IDs cyan color + right-click resolve; xref-aware naming; xref filter on Search and Collection tabs

Changed

gui/rename_tab.py: Multiple IDs rows now use a distinct cyan color (#B2EBF2) instead of red. Right-click a Multiple IDs row to get a "Resolve — Apply…" submenu listing each candidate LB (with xref suffix when applicable). Choosing one resolves the row into a single-LB rename. Rename is blocked for unresolved multiple_ids rows. Updated legend to include the new color. populate_from_lookup now filters detail items to MATCHED/MATCHED (INCOMPLETE) status only, preventing resolved duplicate losers from triggering spurious "Multiple IDs" rows. xref-aware: lb_str and proposed names include "-xref{N:04d}" suffix when the match is via a cross-reference checksum. _lb_in_name, _has_wrong_lb, and _strip_lb_from_name all handle the xref suffix. _fmt_lb() helper added.

backend/db.py: Added get_xref_lb_numbers() — returns distinct lb_numbers that have any xref checksum (xref > 0).

backend/app.py: Added GET /api/checksums/xref_lb_numbers route.

gui/search_tab.py: Added "Xref only" checkbox filter — fetches xref lb_numbers on startup and filters search results to entries that have xref variants in the DB.

gui/collection_tab.py: Added "Xref only" checkbox filter to My Collection — same xref lb_number set, filters owned entries to those with xref variants.

[2026-05-13] — feat(lookup/verify): duplicate resolution, folder/summary filtering, verify NO CHECKSUMS, lookup→verify folder carry

Changed

backend/db.py: lookup_checksums() now resolves duplicate-checksum ambiguity — when the same checksum appears in multiple LB entries and one is fully MATCHED while others are INCOMPLETE, the fully-matched LB is preferred and its items are reclassified from DUPLICATE to MATCHED.

backend/checksum_utils.py: verify_folder() now returns status='no_checksums' (instead of 'pass') when audio files are present but no checksum files (.ffp/.md5/.st5) exist at all.

gui/lookup_tab.py: Added folder filter (click a listbox item to show only that folder's rows in summary and detail; click again to clear). Added summary LB filter (click a summary row to show only that LB's detail items; click again to clear). Filter state shown in section header labels. No-checksum folder detection now requires audio files to be present (folders with neither audio nor checksums are not flagged). No-checksum summary rows are now built inline in _on_lookup_done for both 'listbox' and 'scan-tree' sources. Added get_lookup_folders() method.

gui/verify_tab.py: NO CHECKSUMS status shown in yellow when a folder has audio but no checksum files. Added add_folders_from_lookup(folders) method to receive folders from the Lookup tab.

gui/main_window.py: On switching to the Verify tab, lookup folders are automatically carried over if the Verify folder list is empty.

[2026-05-13] — fix(checksum): SHN shntool hash now works when shorten is not installed (BUG-040)

Fixed

backend/checksum_utils.py: compute_shntool() silently returned None for .shn files on systems without the shorten decoder — shntool requires shorten to decode SHN, but shorten is not in standard Linux repos. Added _compute_shntool_via_ffmpeg() fallback: when shntool hash produces no output for a .shn file, ffmpeg decodes it to a temp WAV and shntool hashes the WAV instead (lossless, produces identical PCM data). Also updated generate_checksums() for SHN mode to write both file-MD5 hashes and shntool audio hashes into the generated .md5 file, matching the lbdir format.

[2026-05-13] — fix(rename): individual checkboxes on Rename tab now toggle on click

Fixed

gui/rename_tab.py: NoEditTriggers blocked Qt's delegate from routing mouse clicks to setData() for CheckStateRole changes, so clicking a checkbox had no effect. Connected view.clicked to a new _on_cell_clicked() handler that calls model.setData() directly, bypassing the edit-trigger restriction.

[2026-05-13] — fix(lbdir): compute shntool hash for WAV files; include in overall verdict (BUG-039)

Fixed

backend/checksum_utils.py: verify_folder_lbdir() only ran compute_shntool() when is_shn was True, leaving shn_actual=None for .wav files → FAIL display despite passing MD5. Extended compute condition to (is_shn or is_wav) and added shntool check to the else-branch so WAV audio integrity is verified and counted in the overall verdict.

[2026-05-13] — fix(lbdir): WAV-format recordings no longer show phantom .shn MISSING entries

Fixed

backend/checksum_utils.py: parse_lbdir_file() was unconditionally converting every .wav filename in the shntool and shntool_len sections to .shn and forcing has_shn=True. For WAV-format recordings (lbdir *.wavf.txt) the files on disk are .wav, so the conversion created nonexistent .shn keys reported as MISSING and set the mode to SHN incorrectly. Fix: conversion is now conditional on has_shn already being True (i.e. the md5 section already saw real .shn filenames).

[2026-05-13] — feat(rename): allow "LB already in name" rows to be moved to 0. Processed without renaming

Changed

gui/rename_tab.py: _on_rename() now processes two eligible states: "needs_rename" (Complete match) renames and moves; "has_lb" (LB already in name) moves under the existing folder name with no rename. The confirm dialog and status message distinguish between the two operations. All other statuses remain blocked.

[2026-05-13] — fix(rename): restrict rename+move to "Complete match" rows only

Changed

gui/rename_tab.py: _on_rename() now filters the selected rows to only those in "needs_rename" state (Complete match). Rows with any other status (No match, LB already in name, Wrong LB, Multiple IDs) are silently skipped — they are not renamed and not moved to "0. Processed". The confirm dialog count and message now reflect only the eligible rows. If no eligible rows exist among the selection, a descriptive status message is shown and the dialog is not raised.

[2026-05-13] — feat(lookup): show all input folders in summary, including those with no DB match

Added

gui/lookup_tab.py: After building LB summary rows, group NOT FOUND detail items by their source folder (using source_file set by the worker). Any folder whose checksums produced zero DB matches now gets its own NOT FOUND summary row showing the count of unmatched checksums. Folders that share items with a matched LB are excluded to avoid double-counting. Clipboard lookups with no source file fall back to a single "NOT FOUND" label row.

[2026-05-13] — fix(lbdir): normalize Windows backslash path separators in lbdir filenames on Linux

Fixed

backend/checksum_utils.py: parse_lbdir_file() extracted filenames verbatim from lbdir files, preserving Windows-style backslashes (e.g. artwork\back.JPG). On Linux, pathlib treats backslashes as literal characters rather than path separators, so fpath.exists() returned False for all files in subdirectories. Added .replace('\\', '/') on every fname extracted in the md5, ffp, shntool, and shntool_len parsing blocks so keys and paths are consistently normalized before use.

[2026-05-13] — fix(startup): defer AttachmentsTab tree load to first activation — removes 3s startup block

Fixed

gui/attachments_tab.py: _refresh_tree() (HTTP request + directory scan) was called in __init__, blocking main-thread tab construction for ~3s. Replaced with a _tree_loaded flag; tree now populates in showEvent on first activation, matching the existing lazy WebEngine pattern.

[2026-05-13] — feat(setup): add shntool status indicator alongside SoX and ffmpeg; split into three separate rows

Changed

backend/checksum_utils.py: Added check_shntool_version() — calls shntool -v, returns first line of output or empty string if unavailable.
backend/app.py: /api/spectrogram/check now imports check_shntool_version and returns shntool_available and shntool_version alongside existing sox/ffmpeg fields.
gui/setup_tab.py: SoX/ffmpeg/shntool indicators split into three separate labelled rows (SoX:, ffmpeg:, shntool:). _check_sox() updated to populate each label independently. "Re-check" button moved to the shntool row. ffmpeg shown in orange when missing (non-critical), shntool in red (required for SHN verification).

[2026-05-13] — fix(lookup): Scan Tree now populates listbox and uses path-based lookup (BUG-036)

Fixed

gui/lookup_tab.py: _on_scan_tree was reading file contents and passing them as raw text to _run_lookup (clipboard mode), so found files were never added to the listbox and source_file was never populated on detail items. Replaced with _ScanTreeWorker(QThread) that does the rglob off the main thread; _on_scan_tree_done adds found paths to _all_paths, refreshes the listbox, then starts a path-based _LookupWorker. Also fixed inverted _mychecksums filter logic (was keeping _mychecksums files and dropping others, should be the reverse).

[2026-05-13] — fix(collection): scan now recognises "LB XXXXX" (space separator) folder names; remove unused QSpinBox import

Changed

gui/collection_tab.py: _LB_RE updated from r'LB-0*(\d+)' to r'LB[- ]0*(\d+)' so folders named "LB 12345" are matched alongside "LB-12345". Removed unused QSpinBox import.

[2026-05-13] — fix(collection): Scan Directory / Scan Tree froze UI on large drives (BUG-034)

Fixed

gui/collection_tab.py: Moved filesystem walk (iterdir / rglob) and /api/collection/lb_numbers network call out of the main thread into a new _ScanWorker QThread. Both _on_scan_directory and _on_scan_tree now start the worker and show a "Scanning…" status; _on_scan_finished presents the preview dialog and calls _bulk_add when results arrive.

[2026-05-13] — chore(startup): add startup timing logger to data/startup.log

Added

backend/startup_log.py: New module — init(path) truncates the log and records start time; t(label) appends a wall-clock timestamp + elapsed seconds entry. Thread-safe via lock; no-ops silently if not yet initialized.

Changed

main.py: Calls startup_log.init() after ensure_data_dirs(); adds t() probes at flask-thread-start, QApplication creation, splash shown, flask-port-ready, main_window import, MainWindow created, and window.show().
backend/app.py: create_app() adds t() probes around init_db(), start_file_watcher(), and route registration.
gui/main_window.py: __init__ adds t() probes around each build phase; _build_tabs adds t() probes before and after each tab module import and each tab instantiation.

[2026-05-13] — refactor(setup): move Data Management into Database group; add column-width persistence to DB Editor

Changed

gui/setup_tab.py: Database QGroupBox restructured as a horizontal split — existing archive controls on the left, Data Management (purge buttons) on the right with a vertical divider. coll_stats_label added showing live counts for My Collection, Wishlist, Personal Ratings, Watchdog Events, and Scrape Diff Rows. _refresh_collection_stats() added; called from _refresh_stats() on startup and after each purge. Standalone purge_group at the bottom of the tab removed.
gui/dbedit_tab.py: Column width persistence added — widths stored per-table in settings.ini under DbEditTab/<table>/col_widths. Right-click on any column header shows "Set width…", "Fit to contents", and "Fit all columns" options. sectionResized auto-saves on drag. Saved widths restored on table switch; first load falls back to resizeColumnsToContents.

[2026-05-13] — fix(dbedit): rows failed to load due to sqlite3.Row.description AttributeError; added Load Records button

Fixed

backend/app.py: dbedit_rows route now captures cursor before fetchall() and reads column names from cur.description (cursor attribute) instead of rows[0].description (which does not exist on sqlite3.Row). Empty tables also handled correctly.

Added

gui/dbedit_tab.py: "Load Records" button in toolbar clears search and reloads the first page for the current table. Removed unused QFont import.

[2026-05-13] — fix(verify): redefine "incomplete" as missing files on disk, not missing checksum types

Changed

backend/checksum_utils.py: In both verify_folder and verify_folder_lbdir, status logic updated. "incomplete" now means one or more audio files referenced by checksums are absent from disk. "fail" now means hash mismatches only. A folder with only an .md5 file where all hashes match now correctly returns "pass" instead of "incomplete".

[2026-05-13] — feat: FEAT-13 + FEAT-14 — Granular Collection Data Management and DB Editor Tab

Added

backend/db.py: integrity_events table added to SCHEMA_SQL; purge_collection, purge_wishlist, purge_collection_meta, purge_integrity_events, purge_entry_changes, delete_collection_entries functions added.
backend/app.py: _DBEDIT_READONLY/AUDIT/WARN constants; POST /api/collection/purge, POST /api/collection/delete_bulk, GET /api/dbedit/tables, GET /api/dbedit/table/<name>/schema, GET /api/dbedit/table/<name>/rows, PATCH /api/dbedit/table/<name>/row, DELETE /api/dbedit/table/<name>/rows, GET /api/dbedit/table/<name>/export routes.
gui/dbedit_tab.py: New DB Editor tab — table browser, paginated row viewer, inline cell editing with dirty-state tracking, row deletion with confirmation, context menu, CSV export.
gui/collection_tab.py: "Select All" and "Select None" buttons added to My Collection panel; _on_remove() replaced with bulk-delete via POST /api/collection/delete_bulk.
gui/setup_tab.py: "Data Management" group added with per-scope purge buttons (collection, wishlist, personal_meta, integrity_events, entry_changes) and confirmation dialogs.
gui/main_window.py: DbEditTab registered as "DB Editor" tab (after Spectrograms); lazy table load on first activation via _on_tab_changed.

[2026-05-13] — feat(gui): Scan Tree button in My Collection tab — recursive LB-folder discovery

Added

gui/collection_tab.py: "Scan Tree…" button added to My Collection panel beside "Scan Directory". _on_scan_tree() uses rglob to find LB-numbered directories at any depth under a root. For LB numbers found at multiple depths the shallowest folder is kept. Reuses the existing _ScanPreviewDialog preview and _bulk_add workflow.

[2026-05-13] — feat(gui): FEAT-08 — Scan Tree batch lookup button in Lookup tab

Added

gui/lookup_tab.py: "Scan Tree…" button added to left panel below "Add Folders…". _on_scan_tree() recursively finds all .ffp/.md5/.st5/.sha1/.shn files under a user-selected root directory, concatenates their contents, and feeds them to _run_lookup() as a single combined lookup. Respects the _filter_mychecksums flag to skip _mychecksums files when the filter is active.

[2026-05-13] — fix(gui): spectrogram panning overshoot caused by stale label-local coordinates after scroll

Fixed

gui/spectrogram_tab.py: _ImageViewer.eventFilter — changed pan tracking from event.position() (label-local coords) to event.globalPosition() (screen coords). When the scrollbar value was updated on each MouseMove, the label shifted on screen, making the stored _pan_start invalid for the next delta calculation and causing overshoot-then-correction jitter. Global coordinates are unaffected by the widget's scroll position.

[2026-05-12] — feat(backend,gui): SoX spectrogram generation with two-pane viewer tab (SPEC-01 through SPEC-06)

Added

backend/sox_utils.py: New module — SoX/ffmpeg tool detection (cached per process), format classification (_SOX_NATIVE / _NEEDS_CONVERSION / AUDIO_EXTS_ALL), convert-to-temp-WAV pipeline for non-native formats (SHN, APE, WV, M4A, MP3, OGG), generate_spectrogram() public API, check_sox_version(), SoxNotFoundError / ConversionError / SpectrogenError exception hierarchy. Original audio files are never modified; temp WAVs are always deleted in a finally block.
backend/app.py: _spectro_state dict + _spectro_lock for thread-safe batch state; _do_spectro_batch() worker (module-level); five new routes: GET /api/spectrogram/check, POST /api/spectrogram/generate, GET /api/spectrogram/status, POST /api/spectrogram/stop, POST /api/spectrogram/list.
gui/spectrogram_tab.py: New tab — _DropFolderList (drag-drop folders), _ImageViewer (fit-width + Ctrl+scroll zoom + double-click reset), _Worker (QThread), SpectrogramTab (folder/track inventory, generate/stop/poll, right-click context menus, salmon highlight for missing PNGs).
gui/main_window.py: SpectrogramTab registered as tab index 7 (between Attachments and Setup); _on_tab_changed() handler connected to tabs.currentChanged — refreshes inventory on Spectrograms activation and triggers SoX check on first Setup activation.
gui/setup_tab.py: SoX status row added to Database group with Re-check button; _check_sox() calls GET /api/spectrogram/check and shows version + ffmpeg availability with green/red colour.

[2026-05-12] — fix(gui): search tab description column default width 1400→600; column widths now persist across view switches and sessions

Fixed

gui/search_tab.py: _DESC_DEFAULT_W reduced from 1400 to 600px. Added QSettings persistence (LosslessBob/SearchTab) so column widths survive tab switches and restarts. Connected sectionResized signal to update _col_widths immediately on user drag. Added _resizing_programmatically guard to prevent spurious saves during programmatic column sizing. Removed _col_widths = None reset in _on_results so user-set widths are preserved across new searches.

[2026-05-12] — feat(db,backend,gui): FEAT-03 per-entry personal metadata, FEAT-04 wishlist tab, FEAT-05 duplicate concert detector

Added

backend/db.py: New tables collection_meta and my_wishlist in SCHEMA_SQL. New functions get_collection_meta, set_collection_meta, increment_listen_count (FEAT-03); get_wishlist, add_to_wishlist, remove_from_wishlist, get_wishlist_lb_numbers (FEAT-04); get_collection_duplicates (FEAT-05).
backend/app.py: Routes GET/POST /api/collection/<lb>/meta and POST /api/collection/<lb>/listen (FEAT-03); GET/POST /api/wishlist and DELETE /api/wishlist/<lb> (FEAT-04); GET /api/collection/duplicates (FEAT-05).
gui/styles.py: Added ROW_WISHLIST color (#E8D5FF) for wishlist row backgrounds.
gui/collection_tab.py: Added _WishlistModel, _PersonalMetaDialog classes. Wishlist inner tab with context menu (remove, view web). Duplicates inner tab using QTreeWidget showing owned (green) and unowned (grey) LBs per show; lazy-loaded on first activation. "Edit Personal Info…" context menu item on My Collection rows opens rating/tags/listen dialog.
gui/lookup_tab.py: "Add to Wishlist" added to summary right-click context menu.
gui/search_tab.py: Row-level right-click context menu with "Add to Wishlist".

[2026-05-12] — refactor(scraper,gui): remove redundant "fill gaps" checkbox; gap-filling is now unconditional

Changed

backend/app.py: Removed fill_gaps parameter. Gap-filling (marking every sequential LB number not in checksums as MISSING) now always runs for both "Scrape All Missing" and explicit range scrapes. The effective upper bound is derived from the highest checksums lb_number when no end_lb is given.
gui/setup_tab.py: Removed fill_gaps_cb checkbox and all references. _on_scrape_range no longer sends fill_gaps in the payload.

[2026-05-12] — fix(scraper,db): BUG-032 — "Scrape All Missing" left gap LB numbers absent from database; BUG-031 — skip bypassed local page recovery

Fixed

backend/app.py: scrape_start now derives effective_end from the highest checksums lb_number when end_lb is absent ("Scrape All Missing" path). Every sequential gap between start_lb and effective_end is unconditionally passed through insert_missing_entry, ensuring no LB number is left out of the database. For explicit range scrapes the fill_gaps checkbox is still respected.
backend/db.py: insert_missing_entry changed from INSERT OR REPLACE to INSERT OR IGNORE — gap-filling can no longer overwrite a row that already has real scraped data.
backend/scraper.py: Moved local_page resolution before the skip block in scrape_entry(). The status=='missing' guard now permits scraping when use_local_pages=True and the local HTML file exists, so previously-404'd entries can be recovered from disk.

[2026-05-12] — fix(gui,backend): BUG-030 — auto-scrape fires after import post-DB-reset

Fixed

gui/setup_tab.py: _on_reset_finished now calls self._save_settings() after a successful reset so the user's current checkbox states are persisted back to the freshly-wiped meta table. Prevents auto_scrape reverting to NULL (which was treated as enabled).
backend/app.py: on_complete now uses explicit None-check (_val is None or _val != "0") to document the intended default-on behaviour and guard against future Python type surprises.

[2026-05-12] — feat(importer): real-time import progress status

Changed

backend/importer.py: Import is now async. Added _import_state dict (stage, rows_parsed, rows_total, rows_merged, new_lb_count, message, error), get_import_status(), and start_import_async(). run_import() updates state throughout, including per-chunk row counts during the merge step (10k-row batches). _import_flat_file reports row count every 10k lines.
backend/app.py: POST /api/db/import now fires start_import_async() and returns immediately; auto-scrape trigger moved into on_complete callback. Added GET /api/db/import/status endpoint.
gui/setup_tab.py: _ImportThread now uses a 15 s timeout (fire-and-forget start). Added _ImportStatusThread polling /api/db/import/status every 500 ms. Added import_progress QProgressBar to Database group: indeterminate during hash/parse/optimise stages, determinate (rows_merged / rows_total) during merge. Label updates live with stage messages.

[2026-05-12] — BUG-029: 2–4 s startup delay from eager QWebEngineView construction

Fixed

gui/attachments_tab.py: QWebEngineView (and its QWebEngineProfile/QWebEnginePage) are now created lazily on the first showEvent of the Attachments tab via QTimer.singleShot(0, _init_web_view), deferring the WebEngine GPU-process spawn until the user actually visits that tab. _preview_file updated to use setCurrentWidget instead of hardcoded setCurrentIndex so stack order no longer matters.

[2026-05-12] — BUG-028: ~7 s Flask startup delay from synchronous bloom filter build

Fixed

backend/db.py: rebuild_bloom() in init_db() was iterating every checksum row on the startup thread, blocking Flask for ~7 s on large databases. Moved to a daemon background thread via _rebuild_bloom_bg(). checksum_in_bloom() already returns True when _bloom is None so all lookups fall through to SQLite until the filter is ready.

[2026-05-12] — BUG-027: ~10 s Linux startup delay from missing AA_ShareOpenGLContexts

Fixed

main.py: Added QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts) before QApplication(sys.argv). QtWebEngine requires this flag at construction time; without it the GPU process falls back to a slow separate-context path on Linux.

[2026-05-12] — BUG-026: WebEnginePage/Profile teardown order warning on shutdown

Fixed

gui/attachments_tab.py: QWebEnginePage is now parented to QWebEngineProfile (not to the tab widget). Qt destroys a parent's children before the parent itself, so page is always destroyed before profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning.

[2026-05-12] — BUG-025: db_reset "FOREIGN KEY constraint failed" after DB-01 enabled FK enforcement

Fixed

backend/app.py: db_reset now prepends PRAGMA foreign_keys=OFF to the DROP script so my_collection's FK on entries doesn't block the drop, then explicitly re-enables with PRAGMA foreign_keys=ON before calling init_db().

[2026-05-12] — DB-01–DB-08: Database performance pass (WAL, thread-local pool, covering indexes, temp-table lookup, FTS5 search, PRAGMA optimize, bloom filter, scrape diff changelog)

Changed

backend/db.py: DB-01/02 — WAL + performance PRAGMAs (synchronous=NORMAL, cache_size=-65536, mmap_size=536MB, temp_store=MEMORY); persistent per-thread connection pool via threading.local() — eliminates repeated connect/close overhead.
backend/db.py: DB-03 — Added idx_chk_covering (covering index on checksums) and idx_lb_xref0 (partial index WHERE xref=0) to SCHEMA_SQL.
backend/db.py: DB-04 — lookup_checksums() now uses CREATE TEMP TABLE + JOIN instead of dynamic IN clause; fixes 999-param SQLite limit for large lookups.
backend/db.py: DB-05 — Added entries_fts FTS5 virtual table (content='entries') with insert/update/delete triggers; init_db() rebuilds index on first run; search_entries() now uses FTS MATCH with LIKE fallback on syntax error.
backend/db.py: DB-07 — ScalableBloomFilter loaded from checksums on startup; lookup_checksums() skips SQLite entirely for definite-miss checksums.
backend/db.py: DB-08 — Added entry_changes table + idx_changes_lb index to SCHEMA_SQL; record_entry_changes() records field-level diffs before each entry upsert.
backend/importer.py: DB-02 — Removed conn.close() from _import_flat_file(); DB-06 — added PRAGMA optimize after bulk import; DB-07 — rebuild_bloom() called after each successful import.
backend/scraper.py: DB-06 — PRAGMA optimize called at end of scrape_range(); DB-08 — record_entry_changes() called before INSERT OR REPLACE INTO entries.
backend/app.py: DB-08 — Added GET /api/entry/<lb>/changes endpoint; db_reset now drops entries_fts, its triggers, and entry_changes before recreating schema.
requirements.txt: Added pybloom-live==4.0.0.

[2026-05-12] — WIN-05/06/07/08/09/10/11/12/13/14/15/16: Full Windows compat pass

Added

backend/paths.py: to_long_path() prefixes \\?\ on Windows for MAX_PATH bypass. WEBENGINE_DIR constant. ensure_data_dirs() warns when data path exceeds 200 chars on Windows.
gui/platform_utils.py: _subprocess_flags() helper for CREATE_NO_WINDOW. url_to_local_path() strips spurious leading slash from Qt6 Windows QUrl.toLocalFile().
tools/build_windows.bat: Windows build script (runs pyinstaller losslessbob.spec, creates dist/LosslessBob/data/).

Changed

backend/checksum_utils.py: _no_window_kwargs() suppresses console windows for subprocess on Windows. _find_shntool()/_get_shntool_cmd() auto-detect shntool via WSL on Windows; compute_shntool uses WSL path conversion and _no_window_kwargs. compute_md5/compute_ffp wrap open() with to_long_path. All shutil.which('shntool') replaced with _get_shntool_cmd() is not None.
backend/db.py: get_connection wraps DB path with to_long_path before sqlite3.connect.
backend/scraper.py: lb_dir and local_page wrapped with to_long_path at construction.
backend/scheduler.py: _handle() filters Thumbs.db/desktop.ini; delayed() cleans _pending in finally block. start_file_watcher uses WindowsApiObserver on Windows (falls back to Observer).
gui/styles.py: _platform_font_stack() selects Segoe UI on Windows, -apple-system on macOS, Ubuntu/Cantarell on Linux.
gui/rename_tab.py: Rename block uses Path objects; splits PermissionError/FileExistsError/OSError into separate handlers with actionable messages; validates for Windows-illegal characters; appends Windows Explorer tip when permission errors occur. Removed unused import os.
gui/verify_tab.py: shntool_missing message shows WSL install instructions on Windows. dropEvent uses url_to_local_path (WIN-14).
gui/lookup_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/lbdir_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/main_window.py: QSettings migrated to INI format at data/settings.ini (WIN-11). All 9 tab imports moved inside _build_tabs() for lazy loading (WIN-16). _refresh_status moved to background thread; initial fire delayed to 3000ms (WIN-16).
gui/attachments_tab.py: QWebEngineView now uses named profile with storage redirected to data/webengine_cache (WIN-15). Removed stale __file__-relative ATTACHMENTS_DIR definition.
main.py: Splash screen shown during Flask startup wait; QApplication created before _wait_for_port; error dialog and main window both use the same QApplication instance (WIN-16).
requirements.txt: Promoted waitress from optional comment to required dependency (WIN-06).
losslessbob.spec: Added waitress.task and waitress.server to hiddenimports (WIN-12).

[2026-05-12] — WIN-03 + WIN-04: Cross-platform file/folder opener; SQLite lock timeout

Added

gui/platform_utils.py: New shared module with open_folder(), open_file(), open_url(). Centralises all sys.platform branching for launching files and folders; uses os.startfile on Windows, open on macOS, xdg-open on Linux.

Changed

gui/collection_tab.py: _open_folders now delegates to open_folder() from platform_utils. Removed top-level import subprocess.
gui/attachments_tab.py: _open_externally now delegates to open_file() from platform_utils. Removed top-level import subprocess and import sys.
gui/setup_tab.py: _on_open_folder and _on_open_log now delegate to open_folder()/open_file() from platform_utils. Removed top-level import os, import subprocess, and import sys.
backend/db.py: get_connection() now passes timeout=30 and check_same_thread=False to sqlite3.connect(). Adds PRAGMA busy_timeout=30000 on every new connection so SQLite retries for up to 30 seconds before raising OperationalError on Windows lock contention.

[2026-05-10] — WIN-01 + WIN-02: Unified path resolution for frozen builds; Flask readiness poll replacing time.sleep

Added

backend/paths.py: New central path resolver. _app_root() returns Path(sys.executable).parent in PyInstaller frozen builds (sys.frozen=True) and Path(__file__).parent.parent otherwise. Exports APP_ROOT, DATA_DIR, DB_PATH, ATTACHMENTS_DIR, PAGES_DIR, LOG_FILE, TOOLS_DIR, and ensure_data_dirs().

Changed

backend/db.py: Replaced inline DB_PATH definition with import from backend.paths (re-exported so existing callers are unaffected).
backend/app.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR definitions with import from backend.paths.
backend/scraper.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR/PAGES_DIR definitions with import from backend.paths. Removed now-unused pathlib import.
backend/scheduler.py: Replaced inline DATA_DIR definition with import from backend.paths.
backend/importer.py: Replaced inline DATA_DIR definition with import from backend.paths.
gui/setup_tab.py: Replaced __file__-relative _LOG_FILE and data_dir with LOG_FILE and DATA_DIR from backend.paths.
main.py: Replaced time.sleep(0.5) with _wait_for_port() TCP poll (100ms interval, 15s timeout). On Windows uses Waitress as WSGI server for stable port binding. Deferred gui.main_window import to inside main() to avoid PyInstaller/DPI issues. Added fatal error dialog if Flask does not start within timeout. Added ensure_data_dirs() call at Flask startup.

[2026-05-10] — WIN-17: Fix drag-and-drop crash caused by OLE COM reentrancy on Windows

Fixed

gui/lookup_tab.py: Moved event.acceptProposedAction() before signal emission in DropListWidget.dropEvent so OLE marks the transaction complete before any widget modification. Removed self._refresh_listbox() from _add_path() — callers now own the refresh call. Updated _on_files_dropped to defer _refresh_listbox() via QTimer.singleShot(0, ...) so listbox.clear() never runs while the COM Drop() call is on the stack. Added explicit self._refresh_listbox() to _on_add_folders to restore the refresh it previously relied on from _add_path().

gui/verify_tab.py: Same acceptProposedAction-first fix in DropFolderListWidget.dropEvent. Changed _on_folders_dropped to use QTimer.singleShot(0, self._refresh_listbox) instead of a synchronous call.

gui/lbdir_tab.py: Identical fix to verify_tab.py.

[2026-05-08] — Fix Search tab column sizing: description default width, width retention on paging, right-click header width entry

Fixed

gui/search_tab.py: Description column now defaults to 1400 px instead of expanding to fit content; other columns still use `resizeColumnsToContents()` on first load. Column widths are now snapshotted from the header immediately before each `set_rows()` call so any user drag-resize is preserved when paging (Qt resets QHeaderView sections on model reset). Right-click on any column header opens a "Set column width…" dialog (QInputDialog) to enter an exact pixel value; the stored widths are updated so paging continues to respect the change.

[2026-05-08] — Fix column widths jumping on page navigation; add Word wrap toggle to Search and Collection tabs

Fixed

gui/search_tab.py: Column widths are now computed once via `resizeColumnsToContents()` on the first page with data and stored as absolute pixel values. Subsequent page renders restore those stored widths instead of re-calling `resizeColumnsToContents()`, so columns stay stable while paging.

gui/collection_tab.py: Same fix applied to My Collection (`coll_view`) and Missing (`miss_view`). Widths are reset and recomputed on each fresh data load.

Added

gui/search_tab.py: "Word wrap" checkbox in the search bar row. When checked, enables word wrap on the results table and auto-sizes rows; when unchecked, restores fixed single-line rows. Description text is no longer truncated at 120 chars.

gui/collection_tab.py: "Word wrap" checkbox added to My Collection button row and Missing button row, with the same on/off behaviour. Description text truncation removed from `_MissingModel`.

---

[2026-05-08] — Fix Results per page resetting to 50 on every startup

Fixed

gui/setup_tab.py: Added `_loading` flag set to True during `_load_settings` and False in a finally block. `_save_settings` returns early while the flag is set. Previously, each `setChecked`/`setValue` call during loading fired connected signals (`stateChanged`, `valueChanged`) that triggered `_save_settings` before `search_page_spin` had been populated from the DB, overwriting the stored value with the widget default of 50.

---

[2026-05-07] — Uniform fixed width on all four scraper action buttons

Changed

gui/setup_tab.py: Set all four scraper buttons (Scrape All Missing Entries, Stop Scraper, Scrape, Scrape Range) to a shared fixed width of 180px via a local constant `_SCRAPE_BTN_W`.

---

[2026-05-07] — Search filters, collection pagination/year filter, scraper grid and label fixes

Added

gui/search_tab.py: Three client-side filter checkboxes on the search bar — "Missing only" (status == 'missing'), "Owned only" (LB in My Collection), "Not owned" (LB not in My Collection). All three are AND-combined. Combining "Owned only" + "Not owned" yields an empty result. The owned filter re-renders automatically when `_OwnedWorker` finishes loading after a search.

gui/collection_tab.py: My Collection panel now auto-loads on startup (blank-screen fix). Added client-side pagination (Prev/Next, page label) driven by the shared Results per page setting. Added year dropdown filter populated from date_str of loaded entries. Text + year filters combined with AND; both reset to page 0 on change.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `collection_tab.set_page_size` so the Results per page spinner also controls My Collection pagination.

Fixed

gui/search_tab.py: Double-click URL now formats LB number as 5-digit zero-padded (`LB-{lb:05d}.html`). Previously used bare integer, producing 404 for any LB below 10000.

gui/setup_tab.py: "Mark sequential gaps as MISSING" checkbox renamed to "Skip LB numbers with no checksum data" per user request. Grid restructured so Scrape All Missing Entries, Scrape (single), and Scrape Range buttons all occupy column 2 of the grid, making them the same width. Stop Scraper moved to column 3. Status label and fill-gaps checkbox now span columns 3–4.

---

[2026-05-07] — Yellow highlight for status=missing search rows; fixed scraper button layout and height clipping

Fixed

gui/search_tab.py: SearchModel.data() now returns a yellow QColor("#FFFF99") for the BackgroundRole when a row has status="missing", so gap-placeholder entries are visually distinct instead of appearing as blank uncoloured rows.

gui/setup_tab.py: Replaced three stacked QHBoxLayout rows in the Web Scraper section with a QGridLayout (4 columns: label, input, action button, extras). All three rows — bulk scrape, single entry, and range — now align in a clean grid with no visual overlap.

gui/styles.py: Added min-height: 20px to the QPushButton stylesheet rule so buttons in mixed-height rows are never clipped.

---

[2026-05-07] — Persistent scraper log file; fixed [web]/[local] source labels; error entries now logged

Added

gui/setup_tab.py: `_LOG_FILE = data/scraper.log` — every `_log()` call now appends to this file in addition to the in-app widget. Log file management row added to the Scraper Log group: a size label (auto-refreshed after each write and on startup), an "Open Log File" button, and a "Purge Log" button (truncates the file and clears the in-app widget after confirmation).

Fixed

backend/scraper.py: Added `last_lb` field to `_scrape_state`, set to the LB number that just finished processing (alongside `last_source`/`last_action`). Previously `current_lb` was set at the START of processing while `last_source` was set at the END, so the GUI polled them out of sync and log lines showed the wrong source tag.

gui/setup_tab.py: `_on_scrape_status` now logs `last_lb` (the just-completed entry) instead of `current_lb` (the one currently being processed). This ensures every log line's `[local]`/`[web]` tag correctly matches the logged LB number. Added an explicit "Error scraping LB-X" log line for error entries (previously silently dropped, causing the next entry to appear with no source tag).

---

[2026-05-07] — Scraper progress bar enlarged to show percentage text

Changed

gui/styles.py: Added `QProgressBar#scrapeProgress` override — 20 px tall with centered text. The global QProgressBar rule (6 px, no text) still applies to the thin activity bars in Verify and lbdir tabs.

gui/setup_tab.py: Set `objectName("scrapeProgress")` on the scraper progress bar so the taller QSS rule targets only that widget.

---

[2026-05-07] — Search tab pagination and configurable results-per-page setting

Changed

backend/db.py: `search_entries` default limit changed from 100 to `None` (unlimited). Caller can still pass an explicit limit. Search tab now fetches all matching entries and paginates client-side.

backend/app.py: `GET /api/db/settings` now returns `force_scrape` and `search_page_size` in addition to the existing keys.

gui/search_tab.py: Added client-side pagination. All results are fetched from the API and stored in `_all_results`; only the current page slice is shown in the table. Prev/Next buttons and a "Page X of Y (N results)" label appear between the search bar and table whenever there is more than one page. A new `set_page_size(n)` public method resets to page 1 and re-renders; called by the setup tab signal. `_load_page_size` reads `search_page_size` from meta on startup.

gui/setup_tab.py: Added "Search" group with a "Results per page" spinner (range 10–500, step 10, default 50). Saved to meta as `search_page_size`. Emits `search_page_size_changed(int)` signal on change. `_load_settings` now loads `search_page_size` and `force_scrape` from meta.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `search_tab.set_page_size`.

---

[2026-05-07] — Local pages cache, scrape skip fixes, use_local_pages setting, [local]/[web] log labels

Changed

backend/scraper.py: Added `PAGES_DIR = DATA_DIR / "pages"` constant. `scrape_entry` now accepts `use_local_pages` parameter — reads `data/pages/LB-XXXXX.html` from disk when available instead of hitting the network, falling back to web only when no local file exists. When fetching from web, the HTML is saved to `data/pages/` for future reuse. Added `last_source` field (`'local'` or `'web'`) to `_scrape_state` and to the `scrape_entry` return dict. `scrape_range` accepts and threads `use_local_pages`; suppresses the inter-entry delay when `local_source=True`. `scrape_entry` attachment download now respects `use_local_pages` — existing files on disk are never re-downloaded when `use_local_pages=True`, even if `force=True`.

backend/app.py: `use_local_pages` added to `/api/db/settings` GET key list. Single-entry scrape route and `/api/scrape/start` route both read `use_local_pages` from meta and pass it through. `_start_scrape_thread` gains `use_local_pages` parameter forwarded to `scrape_range`.

gui/setup_tab.py: Added "Use local pages for metadata (data/pages/)" checkbox, saved/loaded via `use_local_pages` meta key. Scraper log now appends `[local]` or `[web]` after each "Scraped LB-X" entry using `last_source` from the status poll.

Fixed

backend/scraper.py: Scrape skip logic incorrectly re-scraped entries when `download_files=False` — any entry with `entry_files` rows (even with `downloaded=0`) was not being skipped because the pending-count check always fired. Fixed by returning `{skipped: True}` immediately when `not download_files` and the entry row exists.

backend/scraper.py: Entries with attachment files placed in `data/attachments/` from an external source were never marked `downloaded=1` in the DB, causing the scraper to repeatedly re-scrape them. Fixed by scanning the filesystem for each `downloaded=0` record and updating the DB before evaluating the pending count.

backend/scraper.py: `force=True` caused the attachment download loop to re-download files already present on disk when `use_local_pages=True`. Fixed by changing the skip condition to `local_path.exists() and (not force or use_local_pages)`.

gui/lbdir_tab.py: "Show all files" checkbox was unchecked by default, hiding pass rows and requiring a manual toggle. Changed default to checked.

gui/verify_tab.py: Same as above — "Show all files" now checked by default.

Added

backend/scraper.py: `last_source` field in `_scrape_state` (`'local'` | `'web'` | `None`) so the GUI can distinguish the metadata source per entry.

gui/setup_tab.py: "Use local pages for metadata (data/pages/)" checkbox — persisted in meta as `use_local_pages`.
