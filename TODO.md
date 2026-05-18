TODO-001: Show local pages coverage count in Setup tab
Priority: Low
Status: Open
Added: 2026-05-07
Description: Display a count of HTML files present in `data/pages/` next to the "Use local pages" checkbox (e.g. "13,124 pages cached") so the user knows how much local coverage they have without opening the folder.

---

TODO-002: Bulk-download pages HTML to pages/ folder without scraping metadata
Priority: Low
Status: Open
Added: 2026-05-07
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
Status: Open
Added: 2026-05-12
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
Status: Open
Added: 2026-05-15
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
Status: Open
Added: 2026-05-16
Description: Per CC_LB_INTEGRITY.md §Disambiguation: add lb_alias (master — alias_lb → canonical_lb) and folder_lb_link (user — folder_path → lb_number) tables. Wire into Rename tab resolution order: folder_lb_link first, lb_alias collapse second, fall back to multiple_ids. Curator creates aliases in DB Editor.

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

TODO-023: Reliable column width persistence (CC_LB_INTEGRITY item 11)
Priority: Medium
Status: Done
Added: 2026-05-17
Closed: 2026-05-17
Description: Per CC_LB_INTEGRITY.md §Reliable Column Width Persistence: implement GuiStateStore in gui/widgets/state_store.py storing state in data/gui_state.json (atomic writes, 500ms debounce, _restoring guard). Migrate all tabs off QSettings / hardcoded setColumnWidth. One-time QSettings migration on first run. Covers Search, Collection (7 tables), DbEdit, lbdir summary, Rename. ThemeTab QSettings and main_window geometry also migrated to GuiStateStore.
