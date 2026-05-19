TODO-001: Show local pages coverage count in Setup tab
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: Display a count of HTML files present in `data/pages/` next to the "Use local pages" checkbox (e.g. "13,124 pages cached") so the user knows how much local coverage they have without opening the folder.

---

TODO-002: Bulk-download pages HTML to pages/ folder without scraping metadata
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: Add a separate "Download Pages Only" button that fetches and caches all missing `LB-XXXXX.html` files to `data/pages/` without parsing metadata or writing to the DB. Useful for seeding the cache quickly before a metadata scrape.

---

TODO-003: Add type hints and Google-style docstrings to scraper.py public functions
Priority: Medium
Status: Open
Added: 2026-05-07
Description: `scrape_entry`, `scrape_range`, `get_scrape_status`, `stop_scrape`, and `check_for_update` currently have no type hints or docstrings. Required by code standards.

---

TODO-004: Add type hints and docstrings to app.py route handlers
Priority: Low
Status: Open
Added: 2026-05-07
Description: Flask route functions lack type hints and Google-style docstrings as required by project code standards.

---

TODO-005: GUI viewer for entry change history (DB-08 follow-up)
Priority: Low
Status: Open
Added: 2026-05-12
Description: The entry_changes table is populated on every re-scrape but there is no GUI to view it. A small "History" button on the detail panel (or in Attachments tab) could call GET /api/entry/<lb>/changes and display a table of field diffs with timestamps.

---

TODO-006: Close stale temp-DB connection in importer._import_flat_file
Priority: Low
Status: Done
Added: 2026-05-12
Closed: 2026-05-18
Description: With the persistent thread-local connection pool (DB-02), the connection to temp_import.db is never closed after the file is deleted. On the next import in the same thread, get_connection(temp_db_path) returns the stale handle. Workaround: delete the cached entry from _local.connections for the temp path after unlink, or use a separate in-memory SQLite for temp import.

---

TODO-007: FEAT-13 — Granular Collection Data Management
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: Add fine-grained purge control for user data (collection, wishlist, personal meta, integrity events, entry changes). Bulk delete from collection tab. Select All/None buttons in My Collection.

---

TODO-008: FEAT-14 — Database Editor Tab
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: Add DB Editor tab (gui/dbedit_tab.py) with table browser, paginated row viewer, inline cell editing, row deletion, CSV export. Backend routes: GET /api/dbedit/tables, schema, rows, PATCH row, DELETE rows, GET export.

---

TODO-009: Rename tab — Multiple IDs right-click resolution
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: When rename reason is "Multiple IDs", provide a right-click context menu to select which found LB to apply for renaming. Allow rename only after user resolves the ambiguity. Optionally allow selecting multiple IDs (e.g. pick 1, 2, or all 3). Give Multiple IDs a unique color (not red). If no resolution is chosen, block the rename action.

---

TODO-010: xref support in lookup, rename, search, collection
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: xref is an alternate LB number variant. Naming: LB-XXXXX-xrefXXXX (XXXX zero-padded to 4 digits, e.g. xref216 == xref0216). Checksums for all xrefs are in the checksum DB (xref column stores the xref identifier). Tasks: (1) Lookup duplicate resolution already prefers fully-matched over incomplete; (2) Rename applies xref suffix when match is via xref checksum; (3) Search and Collection tabs have xref filter; (4) complete xref match wins over partial primary LB match via duplicate resolution.

---

TODO-011: xref filter on Search and Collection tabs
Priority: Low
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: Added "Xref only" checkbox to Search tab and My Collection tab. Backed by GET /api/checksums/xref_lb_numbers (db.get_xref_lb_numbers). Filter shows only entries that have at least one xref checksum in the DB.

---

TODO-012: Torrent history panel in My Collection tab
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: Add a torrent history sub-panel to the My Collection tab that lists all torrents table records for the selected entry. Show green/red indicator for source_folder_exists; Regenerate button when torrent_path is missing; Add to qBittorrent and added_to_qbt_at per record. Phase 1 adds the buttons but not the history panel UI.

---

TODO-013: Path relocation flow for stale torrent records
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: When a torrent's source_folder is no longer valid (red indicator in the history panel), allow the user to browse for the new folder location, cross-check files against checksums, and optionally rename the folder to the standard format. Described in the Implementation Guide qBittorrent section.

---

TODO-014: Confirm _mychecksums filename convention and finalize TORRENT_EXCLUDE
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: backend/torrent_maker.py currently excludes files matching .*_mychecksums\.(ffp|md5|st5). Confirm the exact naming convention used in the wild before first use and update TORRENT_EXCLUDE_PATTERNS if needed. Resolved: generate_checksums() renamed from _lbgen_* to _mychecksums_* convention; TORRENT_EXCLUDE_PATTERNS already matched this pattern and requires no change.

---

TODO-015: db_reset should drop torrents and rename_history tables
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: The db_reset route drops legacy tables but not the new torrents and rename_history tables added in Phase 1. Fixed immediately: added DROP TABLE IF EXISTS rename_history and torrents to the executescript drop sequence in backend/app.py:db_reset.

---

TODO-016: Make forum post footer attribution (username/version) configurable
Priority: Low
Status: Done
Added: 2026-05-15
Closed: 2026-05-18
Description: The footer string "Brought to you by kuddukan, via the Bob-O-Matic v1.0." is hard-coded in forum_poster.py as _FOOTER. Consider reading username from forum credentials and version from a project constant so it doesn't need manual updates.

---

TODO-017: Periodic re-scrape of Private LBs to detect newly-published pages
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: Add a "Re-scrape Private LBs" button in Setup tab. Iterates every lb_status='private' row, attempts a fresh scrape, calls reconcile_lb_status() to flip status if a page is now found. Shows a completion summary ("N LBs promoted from Private to Public").

---

TODO-018: NFT folder-name suffix for Private LBs
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: Per CC_LB_INTEGRITY.md §NFT: Rename tab and Collection tab should append -NFT to any proposed folder name whose matched LB is Private. Requires _apply_status_suffix() helper in backend/folder_naming.py, discrepancy detection coloring in Rename tab, and GET /api/lb_master/<lb>/nft integration in the GUI.

---

TODO-019: lb_alias and folder_lb_link disambiguation tables
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-18
Description: Per CC_LB_INTEGRITY.md §Disambiguation: lb_alias (master) and folder_lb_link (user) tables. Rename tab resolution order: folder_lb_link first, lb_alias collapse second, fall back to multiple_ids. Curator creates aliases in DB Editor Aliases panel. 7 API endpoints. Right-click "Link…"/"Unlink…"/"Save as master alias…" actions in Rename tab.

---

TODO-020: Master data publish/subscribe system (curator workflow)
Priority: Low
Status: Done (partial — GitHub release publishing deferred)
Added: 2026-05-16
Closed: 2026-05-17
Description: Per CC_LB_INTEGRITY.md §Master Data: implemented POST /api/master/export (VACUUM INTO, drop user tables, filter meta to MASTER_META_KEYS, stamp version, SHA256, manifest sidecar) and POST /api/master/import (manifest SHA validation, schema-version guard, pre-import backup, ATTACH + table-level copy, preserve user data and user meta). MASTER_TABLES / USER_TABLES / MASTER_META_KEYS constants added to backend/db.py. Curator-mode flag (is_curator) + checkbox in Setup tab gates the Publish button. 13 tests in tests/test_master_data.py. Deferred: GitHub-release-via-gh-CLI upload from inside the Publish button — for now the curator uploads the data/exports/ files manually to kuddukan42/losslessbob releases. Follow-up TODO will track that automation once the repo goes public.

---

TODO-021: Status filter combobox on remaining tabs (Lookup, Attachments, Rename, Verify, lbdir)
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: Per CC_LB_INTEGRITY.md §Status Filters Across All GUI Elements: add lb_status background coloring and optional filter combobox to Lookup summary/detail, Attachments tree, Rename LB Found column, and (low priority) Verify and lbdir summary tables. Requires shared lb_status_style() in gui/styles.py.
Done: Lookup tab (filter combobox + Private/Missing row tinting), Attachments tree (page-level batch tinting), Rename tab (LB Found col tint), Lbdir summary (LB# col tint). Verify tab skipped — lb_number not available in verify results without backend change.

---

TODO-022: GitHub release upload from "Publish Master Update" button
Priority: Low
Status: Open
Added: 2026-05-17
Description: After the export endpoint produces data/exports/<file>.db + .manifest.json, automate the upload to the kuddukan42/losslessbob GitHub releases via the gh CLI. Tag scheme: master-YYYY-MM-DD with auto-bump (.2, .3) on same-day re-release. Auto-generate release notes from lb_status_history rows since the last published master_version, plus a list of new manual overrides + notes. Currently the curator uploads the two files manually. Repo is private at the moment; this work should land once it goes public so end users can pull releases without auth. See CC_LB_INTEGRITY.md §GitHub Release Publishing.

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
Description: Per CC_LB_INTEGRITY.md §Reliable Column Width Persistence: implement GuiStateStore in gui/widgets/state_store.py storing state in data/gui_state.json (atomic writes, 500ms debounce, _restoring guard). Migrate all tabs off QSettings / hardcoded setColumnWidth. One-time QSettings migration on first run. Covers Search, Collection (7 tables), DbEdit, lbdir summary, Rename. ThemeTab QSettings and main_window geometry also migrated to GuiStateStore.

---

TODO-024: Override export/import JSON
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import. DB Editor buttons for Export and Import Overrides in the Integrity panel.

---

TODO-025: Click-to-sort across all tables
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: CC_LB_INTEGRITY item 10. SortableTableItem and sort_key_for() in gui/widgets/sort_keys.py. Client-side sort via SortableTableItem for lbdir and verify QTableWidget tables (summary + detail). In-memory sort via sectionClicked for Search, Collection, and Missing QTableView tables. Server-side sort for DB Editor (sectionClicked wired, sort_col/sort_dir appended to /api/dbedit/table/rows fetch). Backend /api/search, /api/collection, /api/collection/missing updated to accept sort_col/sort_dir. GuiStateStore.get_sort()/set_sort() added for future sort state persistence.

---

TODO-026: Flat-file update check rework (CC_LB_INTEGRITY item 9)
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: CC_LB_INTEGRITY item 9. New backend/flat_file.py pipeline: discover→download→diff→apply with audit trail in flat_file_releases + flat_file_changelog tables (added to MASTER_TABLES). 7 new API endpoints under /api/flat_file/*. Setup tab UI rework: "Check for Flat File Update" button using _DiscoverThread (non-blocking), _UpdateAvailableDialog with Download & Apply / Defer / Skip, Flat File History panel showing all releases. Removed broken check_for_update() from scraper.py (was scraping bynumber page, missed corrections).

---

TODO-027: Click-to-sort on Lookup tab summary and detail tables
Priority: Low
Status: Open
Added: 2026-05-18
Description: Lookup tab uses QAbstractTableModel + QTableView, so SortableTableItem (QTableWidget-only) does not apply. Add a QSortFilterProxyModel wrapper to both the summary and detail table views. Define a custom lessThan() that uses typed sort keys (lb_number numeric, lb_status rank, text case-insensitive) consistent with sort_key_for() in gui/widgets/sort_keys.py. Wire header sectionClicked to toggle sort direction and update the sort indicator. Default: summary sorted by LB Number ASC, detail by Filename ASC.

---

TODO-028: Click-to-sort on Rename tab main table
Priority: Low
Status: Open
Added: 2026-05-18
Description: Rename tab uses RenameModel (QAbstractTableModel) + QTableView, so SortableTableItem does not apply. Add a QSortFilterProxyModel wrapper around RenameModel. Implement lessThan() to sort by: Current Folder Name (text), LB Found (lb_number for single-LB rows; first LB numerically for multi-LB rows), Proposed Name (text), State (custom rank: needs_rename < has_lb < wrong_lb < multiple_ids < done). Wire header sectionClicked; default sort by Current Folder Name ASC. Ensure the proxy does not break existing row-state updates (RenameModel.update_state, update_proposed_name) — map proxy indices back to source indices before mutating.

---

TODO-029: Save / restore column-width defaults across all GUI tabs
Priority: Medium
Status: Open
Added: 2026-05-18
Description: Allow the user to snapshot their current column layout as reusable defaults and restore to them (or to factory defaults) on demand.

Concepts:
  - Live widths    — what GuiStateStore already persists in gui_state.json under each table key (e.g. "search.results", "collection.main"). Written on every user resize. These should not change.
  - User defaults  — a one-time snapshot of live widths that the user saves deliberately. Stored under a "col_width_defaults" top-level key in gui_state.json. New users start with no user defaults (falls through to factory defaults).
  - Factory defaults — the hardcoded `defaults=[...]` lists already passed to attach_table() in each tab. These are the widths shipped with the app and never change unless a developer edits the code.

GuiStateStore changes (gui/widgets/state_store.py):
  - Track every attach_table() call in a list: self._registered = [(table, key, defaults), ...]
  - save_user_defaults() — copies current col_widths for every registered key into self._state["col_width_defaults"][key]. Writes immediately (no debounce needed — user-triggered).
  - restore_user_defaults() — for each registered (table, key, defaults): reads self._state["col_width_defaults"].get(key) and applies those widths to the table; then copies them into the live col_widths section so sectionResized saves correctly going forward. Falls through to factory defaults for any key not present in user defaults.
  - restore_factory_defaults() — for each registered (table, key, defaults): applies the hardcoded defaults list to the table and saves them as the live col_widths. Clears "col_width_defaults" entirely so the next restore_user_defaults() call also falls through to factory.
  - clear_user_defaults() — removes "col_width_defaults" key from state. Useful so restore_user_defaults() returns to factory behaviour without having to explicitly call restore_factory_defaults().

UI (gui/theme_tab.py or a new "Layout" group in Setup tab):
  - Add a "Column Widths" group with three buttons:
      "Save as Defaults"    → calls state_store.save_user_defaults(); shows confirmation "Layout saved as defaults."
      "Restore My Defaults" → calls state_store.restore_user_defaults(); disabled when no user defaults are saved.
      "Restore Factory"     → calls state_store.restore_factory_defaults() after a confirmation dialog.
  - The group also shows whether user defaults exist: "User defaults: saved" / "User defaults: none (factory widths will be used)".
  - The SetupTab or ThemeTab receives the GuiStateStore reference (it already does via main_window.py) and wires up the buttons.

First-install behaviour:
  - On first launch, gui_state.json does not exist → no "col_width_defaults" key → all tabs use factory defaults (the existing hardcoded lists). No code change required; this already works.
  - After the user clicks "Save as Defaults", subsequent launches restore their layout automatically because restore_user_defaults() is called by the tab's _restore() function... actually: keep it simple — don't change attach_table() at all. Defaults only apply when the user explicitly presses a button. The live widths (already persisted per-resize) are what loads on each startup. "Save as Defaults" / "Restore" are purely on-demand operations.

Implementation note:
  - attach_table() must store the table reference weakly (weakref.ref) to avoid keeping dead widgets alive. Check ref() is not None before applying widths.
  - The _registered list should be cleared when the store is destroyed or reset.
  - restore_user_defaults() and restore_factory_defaults() should set the _restoring guard for each table during the programmatic resize to suppress spurious sectionResized saves.

---

TODO-030: Bootleg-CD Catalog (LBBCD) — scraper, tables, Bootlegs tab, and cross-tab integration
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: The LosslessBob site maintains a separate sub-catalog of named bootleg releases at
  http://www.losslessbob.wonderingwhattochoose.com/detail/LB-bootleg-by-title.html
Each row pairs a bootleg title (e.g. "Zurich Modern Times") with a canonical LB number, date, location, and CD count. Some titles link to a LBBCD-NNN detail page. This is master-class data that should ship to all users.

Source page: single HTML <table>, ~thousands of rows, 5 columns: Date (M/D/YY with "xx" for unknown), Title (may be empty; sometimes an <a> to LBBCD-NNN.html), Location, cd (integer, 0 valid), LB (always LB-NNNNN link). No page-level timestamp — update detection uses HTTP ETag / Last-Modified + body SHA256.

Schema (both tables added to MASTER_TABLES):
  bootleg_titles(id PK, lb_number, title, date_str, date_iso, year, location, cd_count, lbbcd_id, lbbcd_url, scraped_at)
  bootleg_scrapes(id PK, source_url, scraped_at, http_etag, http_last_modified, body_sha256, rows_total, rows_added, rows_changed, rows_removed, status)
  Indexes: idx_bootleg_lb, idx_bootleg_lbbcd (partial WHERE lbbcd_id NOT NULL), idx_bootleg_year, idx_bootleg_title COLLATE NOCASE.

Date parsing (pivot Y>=30 → 19YY, Y<30 → 20YY; document constant for ~2030 revisit):
  - Full M/D/Y → YYYY-MM-DD + year
  - D=xx → YYYY-MM + year
  - M+D=xx → YYYY + year
  - All xx or unparseable → both NULL

New module backend/bootleg_scraper.py — scrape_bootlegs(force=False):
  1. HEAD the page; compare ETag/Last-Modified to most recent bootleg_scrapes row.
  2. If unchanged and force=False → insert no_change row, return early.
  3. GET page, compute SHA256, parse with BeautifulSoup.
  4. Diff incoming rows against current bootleg_titles using (lb_number, title, date_str) as natural key.
  5. Apply adds/changes/removes in a transaction (pre_bootleg_scrape DB backup first).
  6. Insert bootleg_scrapes success row with counts.
  Manual trigger only — no auto-scrape on startup.

API (5 new routes under /api/bootlegs/*):
  POST /api/bootlegs/scrape         — run scrape now; body {force: bool}; returns counts
  GET  /api/bootlegs                — paginated list; filters: q, year_min, year_max, cd_min, cd_max, lb_status, owned, has_lbbcd, sort_col, sort_dir
  GET  /api/bootlegs/<id>           — single row + joined entries/lb_master info
  GET  /api/bootlegs/by_lb/<lb>     — all bootleg titles for one LB (used by Search/Lookup integrations)
  GET  /api/bootlegs/scrapes        — history of past scrapes

New file gui/bootlegs_tab.py — Bootlegs tab registered in main_window.py:
  Filter bar: free-text (title+location, debounced 300ms), year range spinboxes, CDs combobox (All/0/1/2/3+),
              Status filter, Owned filter (All/Owned/Not owned), LBBCD filter (All/Has link/No link).
  Table columns: LB Number, Title, Date, Year, Location, CDs, LBBCD (icon+link), Status (lb_master color), Owned (✓).
  Detail pane (right): full fields, link to Search tab for that LB, LBBCD link opens browser,
                        all other bootleg titles sharing the same LB.

Setup tab additions:
  - "Scrape Bootleg Catalog" button → POST /api/bootlegs/scrape; progress dialog with added/changed/removed/total counts.
  - Bootleg scrape history sub-panel listing bootleg_scrapes rows.
  - Status bar: append "Bootlegs: N catalogued (last scrape: YYYY-MM-DD)".

Cross-tab integrations:
  - Search tab: 🎵 N badge next to LB Number on rows with bootleg titles; click → opens Bootlegs tab filtered to that LB.
  - Lookup tab: bootleg titles listed in match summary when a resolved LB has bootlegs.
  - Collection tab (My Collection): Bootleg column showing title(s) for that LB.
  - DB Editor: bootleg_titles appears in table list; LB Master browser shows bootleg count column.

Curator tie-in:
  - bootleg_titles + bootleg_scrapes included in MASTER_TABLES (ship in master releases).
  - "Publish Master Update" release notes include bootleg-catalog change counts since last publish.
  - Pre-publish Review dialog gains a "Bootleg titles added/changed since last release" section.

Edge cases:
  - Empty/whitespace title → store as "" not NULL; display as "(no title)".
  - LB referenced in bootleg catalog but not in lb_master → insert bootleg row; mark lb_master row needs_review=1 on next reconcile.
  - Same LB+title+date appearing twice on page → deduplicate during parse, log warning.
  - HTTP failure → status='failed', no DB changes, non-blocking UI warning.
  - LBBCD detail pages (LBBCD-NNN.html) are OUT OF SCOPE for v1 — index page only.

Files to create/modify:
  New:    backend/bootleg_scraper.py
  Modify: backend/db.py (tables + indexes + MASTER_TABLES + get_bootlegs/get_bootlegs_for_lb/get_bootleg_stats)
  Modify: backend/app.py (5 new /api/bootlegs/* routes)
  New:    gui/bootlegs_tab.py
  Modify: gui/main_window.py (register Bootlegs tab)
  Modify: gui/search_tab.py (🎵 badge)
  Modify: gui/lookup_tab.py (bootleg titles in match detail)
  Modify: gui/collection_tab.py (Bootleg column in My Collection)
  Modify: gui/setup_tab.py (Scrape button + history panel + status-bar count)
  Modify: gui/dbedit_tab.py (bootleg count on LB Master browser)
  Update: PROJECT.md, CHANGELOG.md

---

TODO-031: Dedicated Scraper tab + full-site crawler (replaces scraping section in Setup)
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Move all scraping controls out of Setup tab into a dedicated Scraper tab. Add a full domain-aware site crawler that produces a complete offline mirror of losslessbob.wonderingwhattochoose.com using If-Modified-Since for efficient incremental updates.

Confirmed server capabilities (tools/test_site_headers.py):
  - HEAD requests: supported
  - If-Modified-Since → 304 Not Modified: YES (both detail pages and index pages)
  - If-None-Match (ETag): ignored by server (falls back to Last-Modified)
  - Last-Modified header: present on all tested pages

Change-detection strategy (confirmed optimal):
  - Per-page: GET with If-Modified-Since: <stored last_modified>
    → 304 = unchanged (skip, store only last_checked_at)
    → 200 = changed (re-cache body, update page_cache_state, re-parse if structured)
  - Site-wide gate: check flat-file download page Last-Modified first.
    If unchanged since last full crawl → offer to skip entirely.
    Website changes at most once per month.
  - On first visit (no stored Last-Modified): full GET, store body + Last-Modified.

Resume logic:
  - page_cache_state table is the authoritative "what has been fetched" record.
  - On start: load all URLs from page_cache_state into visited set.
  - Also scan data/pages/ for .html files on disk but not in DB (fallback).
  - Crawl queue = all discovered URLs minus visited set.
  - Stopping mid-crawl and restarting picks up from where it left off automatically.

Crawl scope — entire losslessbob.wonderingwhattochoose.com domain:
  - Entry point: http://www.losslessbob.wonderingwhattochoose.com/
  - Follow all <a href> links that stay on the same domain.
  - Known structure: /detail/LB-XXXXX.html (~13,000+), /detail/LB-bootleg-by-title.html,
    /lbbcd/LBBCD-NNN.html, /bynumber/LBMbynumber.html, /files/LBF-* (attachments),
    root/home page, any other pages the crawler discovers.
  - Excluded: external domains, mailto:, javascript:, tel:, data:, fragment-only anchors.
  - File types to cache: .html, .txt, .ffp, .md5, .st5, .sha1 (structured/text files).
    Binary audio files are NOT downloaded.

Storage (reuses existing directories — no duplication):
  - data/pages/LB-XXXXX.html   → existing entry detail cache (unchanged)
  - data/pages/lbbcd/           → LBBCD detail pages (new sub-dir)
  - data/pages/site/            → root, bynumber, and other non-LB pages (new sub-dir)
  - data/attachments/LB-XXXXX/ → existing attachment cache (unchanged)
  - SITE_DIR constant added to backend/paths.py

Rate-limiting / politeness:
  - Page delay: 1500ms default (configurable 500–10000ms)
  - Jitter: ±20% random variation
  - If-Modified-Since check delay: 750ms (body usually absent, cheaper)
  - File download delay: 750ms
  - On 429: honor Retry-After header; default 60s if absent
  - On connection error: exponential backoff 5s → 15s → 45s → skip with error log
  - Concurrency: always 1 (sequential)
  - Daily request cap: configurable (default 5,000)
  - robots.txt: read once at session start, cache for session lifetime

New DB tables:
  scrape_sessions(id PK, started_at, finished_at, scope, start_url, pages_fetched,
    pages_304, pages_skipped, pages_failed, files_fetched, status, notes)
  page_cache_state(url TEXT PK, last_fetched_at, last_modified, body_sha256,
    content_type, size_bytes, status_code, session_id FK)

New backend module: backend/site_crawler.py
  - crawl(start_url, session_id, force, scope) — main entry point
  - _discover_links(html, base_url) — extract same-domain links from page
  - _fetch_page(url, stored_last_modified) — GET with If-Modified-Since; returns (status, body, last_modified) 
  - _cache_path(url) — maps URL → file path under data/pages/ or data/attachments/
  - get_crawler_status() / stop_crawler() — mirrors scraper.py pattern
  - Uses separate _crawler_state dict and _crawler_lock (does not share with _scrape_state)

New Scraper tab (gui/scraper_tab.py) — one tab, collapsible QGroupBox sub-panels:
  Panel 1 — Control & Status:
    Scope selector: Full crawl / Incremental (If-Modified-Since) / Entry pages only / Range
    Start / Stop / Pause buttons
    Live status ticker: "Checking LB-XXXXX.html — 304 unchanged" / "Downloaded LB-XXXXX.html (changed)"
    Overall progress bar (queue size vs visited)
    "N pages cached  |  N changed this run  |  N skipped (304)  |  N failed"

  Panel 2 — Entry Pages (existing scraper.py controls, moved here):
    Scrape All Missing / Scrape Range / Single Entry
    Force re-scrape, Use local pages, Download attachments checkboxes
    Re-scrape Private LBs button
    Download Missing Pages button
    Delay spinner
    Progress bar + stop button (same _scrape_state as before)

  Panel 3 — Bootleg Catalog (existing LBBCD scrape, moved here):
    Scrape Bootleg Catalog button + Force checkbox + status label
    Scrape history table

  Panel 4 — Session History:
    Table: Started | Finished | Scope | Fetched | 304s | Failed | Status
    Click row → filters Change Log panel to that session

  Panel 5 — Change Log:
    Queryable table sourced from entry_changes, joined with scrape_sessions
    Filters: date range, LB number, field name, session
    Columns: Timestamp | Session | LB# | Field | Old Value | New Value

  Panel 6 — Settings (moved from Setup):
    Delay between requests (ms)
    Jitter toggle
    Daily request cap
    Auto-scrape after flat-file import
    Force re-scrape global toggle
    Use local pages toggle

Scraper log:
  Moved here from Setup. Plain text + scrollable widget + "Open Log File" + "Purge Log" buttons.

Files to create/modify:
  New:    backend/site_crawler.py
  New:    gui/scraper_tab.py
  Modify: backend/db.py (scrape_sessions + page_cache_state tables, helpers)
  Modify: backend/app.py (/api/crawler/* routes: start, status, stop, history)
  Modify: backend/paths.py (SITE_DIR = DATA_DIR / "pages" / "site")
  Modify: gui/setup_tab.py (remove all scraper controls; keep DB, master data, SoX only)
  Modify: gui/main_window.py (register Scraper tab, update tab order/count)
  Update: PROJECT.md, CHANGELOG.md, TODO.md

Sub-tasks: TODO-032 through TODO-040

---

TODO-032: [TODO-031 Step 1] paths.py — replace PAGES_DIR/ATTACHMENTS_DIR with SITE_DIR hierarchy
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: In backend/paths.py, add SITE_DIR = DATA_DIR / "pages" / "site" and ensure PAGES_DIR and ATTACHMENTS_DIR constants remain unchanged (detail pages and attachments dirs are not moving). Create the data/pages/lbbcd/ and data/pages/site/ sub-directories as needed. No consumer code changes in this step — those follow in TODO-034.

---

TODO-033: [TODO-031 Step 2] db.py — scrape_sessions + page_cache_state tables + helpers
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add scrape_sessions(id PK, started_at, finished_at, scope, start_url, pages_fetched, pages_304, pages_skipped, pages_failed, files_fetched, status, notes) and page_cache_state(url TEXT PK, last_fetched_at, last_modified, body_sha256, content_type, size_bytes, status_code, session_id FK) to db.py init_db(). Add helpers: create_scrape_session(), update_scrape_session(), upsert_page_cache(), get_page_cache(url), get_scrape_sessions(). Use idempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS for safety on existing DBs.

---

TODO-034: [TODO-031 Step 3] Update path refs in scraper.py, app.py, forum_poster.py, attachments_tab.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Audit all imports of PAGES_DIR and ATTACHMENTS_DIR across scraper.py, app.py, forum_poster.py, and gui/attachments_tab.py. Confirm they still point to the correct locations after the SITE_DIR addition in TODO-032. Add SITE_DIR import where site-crawled content will be read. No functional behaviour change — path wiring only.

---

TODO-035: [TODO-031 Step 4] backend/site_crawler.py — spider engine
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create backend/site_crawler.py with: crawl(start_url, session_id, force, scope), _discover_links(html, base_url), _fetch_page(url, stored_last_modified) → (status, body, last_modified), _cache_path(url) mapping URLs to data/pages/ sub-dirs, get_crawler_status(), stop_crawler(). Rate limiting: 1500ms default delay ±20% jitter, 750ms for 304-check-only requests, Retry-After on 429, exponential backoff on connection error. Daily request cap. robots.txt read once per session. Separate _crawler_state dict and _crawler_lock (does not share state with scraper.py).

---

TODO-036: [TODO-031 Step 5] API routes /api/crawler/* in app.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add Flask routes to backend/app.py: POST /api/crawler/start (body: {scope, start_url, force}), GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/history (paginated scrape_sessions rows), GET /api/crawler/page_cache (paginated page_cache_state). Follow existing scraper route patterns. Add migration comment if any existing route signature changes.

---

TODO-037: [TODO-031 Step 6] gui/scraper_tab.py — 6 sub-panels
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create gui/scraper_tab.py with 6 collapsible QGroupBox panels: (1) Control & Status — scope selector, Start/Stop/Pause, live ticker, progress bar, counts; (2) Entry Pages — existing scraper controls moved from Setup tab; (3) Bootleg Catalog — existing LBBCD scrape controls moved from Setup tab; (4) Session History — scrape_sessions table, click-to-filter Change Log; (5) Change Log — queryable entry_changes joined to scrape_sessions; (6) Settings — delay, jitter, daily cap, toggles. Move scraper log widget here from Setup tab.

---

TODO-038: [TODO-031 Step 7] gui/setup_tab.py — strip all scraper controls
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Remove from gui/setup_tab.py: all entry-scraper controls (Scrape All Missing, Scrape Range, Single Entry, Force re-scrape, Use local pages, Download attachments, Re-scrape Private LBs, Download Missing Pages, delay spinner, progress bar, stop button), the Bootleg Catalog scrape section, and the scraper log widget. Keep: DB management, master data import/export, SoX path, and forum credentials. Update any signals/slots that referenced removed widgets.

---

TODO-039: [TODO-031 Step 8] gui/main_window.py — register Scraper tab, update order
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Import ScraperTab from gui/scraper_tab.py. Add it to the tab widget after Setup (or wherever fits the intended tab order). Update tab count assertions or comments if present. Verify no initialization-order issues with other tabs that may reference scraper state.

---

TODO-040: [TODO-031 Step 9] Docs — update PROJECT.md and CHANGELOG.md after scraper work
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: After TODO-032 through TODO-039 are complete: update PROJECT.md file structure tree (new backend/site_crawler.py, gui/scraper_tab.py), DB schema section (scrape_sessions + page_cache_state), API routes section (/api/crawler/*), and Tech Stack table if any new deps were added. Prepend CHANGELOG.md entry summarising the full TODO-031 scraper tab implementation. This TODO should be the last closed item in the TODO-031 work sequence.

---

TODO-041: Backend geocoding API endpoints
Priority: Medium
Status: Open
Added: 2026-05-18
Description: The curator geocoding GUI added in setup_tab.py and dbedit_tab.py requires four backend routes that do not yet exist:
  POST /api/geocode/run        — start geocoder; body {retry_failed: bool}; returns 409 if already running
  GET  /api/geocode/status     — poll running state; returns {running, done, total, current, errors}
  GET  /api/geocode/locations  — list geocoded location rows; query param filter=all|failed|low_confidence|manual
  POST /api/geocode/location   — save a manual lat/lon; body {location, lat, lon, note}
Nominatim (geopy or direct HTTP) should be used with a polite 1-request-per-second rate limit and User-Agent header. DB schema: location_geocodes(location_text PK, source, confidence, lat, lon, is_manual, note, geocoded_at). Add to MASTER_TABLES.
