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
