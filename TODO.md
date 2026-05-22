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

TODO-084: Export HTML — decade/year filter dropdowns do not populate
Priority: Medium
Status: Open
Added: 2026-05-21
Description: In the exported collection HTML, the "All decades" and "All years" dropdowns
  are always empty. mkDrops() (app.py JS template ~line 3571) builds both lists from
  DATA.map(r=>r.year).filter(Boolean), but year is derived from entries.date_str[:4] via
  a LEFT JOIN in get_collection() (db.py:1056). When entries.date_str is NULL (no
  matching entries row, or date_str not set) year is "", and filter(Boolean) strips it,
  leaving both selects with only their placeholder option.
  Fix: investigate whether date_str is populated for the user's collection rows. If the
  join miss is the root cause, fall back to parsing year from folder_name when date_str
  is absent. Ensure at least one non-empty year reaches the JS to confirm the fix.

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

TODO-082: Restructure — move Verify and lbdir into a "Checksums" compound tab
Priority: Medium
Status: Open
Added: 2026-05-21
Description: Replace the two top-level "Verify" (index 2) and "lbdir" (index 3) tabs with
  a single "Checksums" main tab whose body is a QTabWidget containing "Verify" and "lbdir"
  as sub-tabs. This reduces the top-level tab count and groups the two checksum workflows.
  Changes needed:
    • gui/main_window.py:
      - Replace addTab(verify_tab, "Verify") and addTab(lbdir_tab, "lbdir") with a new
        ChecksumsTab wrapper widget added as addTab(checksums_tab, tr("Checksums")).
      - Update the tab-order comment at main_window.py:111.
      - _on_tab_changed: the widget identity checks for verify_tab and lbdir_tab must
        account for the new nesting — trigger on the Checksums parent tab switching in,
        then inspect the inner sub-tab's currentWidget() to replicate existing behaviour
        (lazy folder preload for Verify, resize_columns_to_font for both).
      - apply_panel_shadow calls for verify_tab and lbdir_tab (main_window.py:199-202)
        must remain functional after the wrapping.
    • Create gui/checksums_tab.py (or inline the QTabWidget wrapper in main_window.py)
      and register it in PROJECT.md file structure.
    • Any setCurrentIndex(2) / setCurrentIndex(3) references elsewhere must be updated
        to target the new Checksums index and switch the inner sub-tab as needed.
    • TODO-081 (cross-tab folder sync) will need updating: lbdir pre-population must
      trigger off the inner sub-tab switch, not the outer tab switch.

---

TODO-081: Cross-tab folder sync — preload all first-4 tabs from Lookup folder selection
Priority: Medium
Status: Open
Added: 2026-05-21
Description: When folders are added on the Lookup tab they should be automatically
  preloaded on the other three first-4 tabs (Rename, Verify, lbdir) so the user does
  not have to re-add the same folders on each tab.
  Current state:
    • Lookup → Rename: already wired (lookup_completed signal → rename_tab.populate_from_lookup,
      main_window.py:186).
    • Lookup → Verify: lazily pre-populated on tab-switch if the Verify list is empty
      (main_window.py:272-275 via get_lookup_folders()).
    • Lookup → lbdir: no connection exists.
  Changes needed:
    • lbdir_tab.py: add a public add_folders_from_lookup(folders: list[str]) method
      mirroring verify_tab.py:374 — only pre-populate when the lbdir folder list is
      currently empty, to avoid overwriting an active session.
    • main_window.py: in the tab-switch handler (_on_tab_changed), when switching to
      lbdir (index 3), call lbdir_tab.add_folders_from_lookup(lookup_tab.get_lookup_folders())
      using the same guard pattern as Verify.
    • Consider also wiring it eagerly via lookup_completed signal (alongside Rename)
      so the preload happens immediately without requiring a tab switch.

---

TODO-080: Rename tab — embed all LB alias numbers in folder name when aliases are present
Priority: Medium
Status: Open
Added: 2026-05-21
Description: The lb_alias table maps secondary ("alias") LB numbers to a single canonical
  LB. Currently when the Rename tab resolves a multi-candidate folder via alias collapse
  (_resolve_single_lb, rename_tab.py:563) it renames using only the canonical LB number.
  Enhancement: after resolving to the canonical, query lb_alias for all alias_lb entries
  whose canonical_lb matches, then include every alias in the renamed folder name alongside
  the canonical (e.g. "LB12345-LB67890 — Title" when 67890 is an alias of 12345).
  Changes needed:
    • db.py: add get_aliases_for_canonical(canonical_lb) helper returning list[int].
    • backend/app.py: expose via /api/lb_alias/resolve or a new endpoint.
    • rename_tab.py: after resolution, fetch aliases and append them to the LB prefix
      in the candidate folder name before renaming.
    • Define and document the multi-LB folder naming convention (separator, order,
      zero-padding) and update PROJECT.md.

---

TODO-079: i18n — wrap table column headers with tr() across all tabs
Priority: Medium
Status: Open
Added: 2026-05-21
Description: Table column headers set via QTableWidget.setHorizontalHeaderLabels(),
  QHeaderView, or QTreeWidget column titles are not wrapped in self.tr() calls,
  so they are excluded from translation and remain in English in all locales.
  Audit every tab (Collection, DB Editor, Map, Scraper, Setup, Rename, Attachments,
  Fingerprint) and wrap all header strings with tr(), then regenerate .ts/.qm files.

---

TODO-078: CLI daemon — Windows support for start_new_session
Priority: Low
Status: Open
Added: 2026-05-21
Description: _daemon_start() uses start_new_session=True which is a POSIX concept.
  On Windows the equivalent is DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP via
  subprocess creationflags. Add a platform check so daemon start works correctly
  on Windows.

---

TODO-070: i18n integration testing — all 5 languages end-to-end
Priority: Medium
Status: Open
Added: 2026-05-19
Description: For each of the 5 languages: set ui_language in meta, restart app,
  verify tab titles, button labels, column headers, placeholder text, and QMessageBox
  dialogs are translated. Verify LB numbers and checksums are not garbled. Verify
  English still works as default. Run py_compile on all gui files.
  Prerequisite: TODO-069. See instructions/CC_I18N.md TODO-070 section for checklist.

---

TODO-066: Web GUI — docs update after web UI ships
Priority: Low
Status: Open
Added: 2026-05-19
Description: After web GUI feature is complete: update PROJECT.md (frontend/ file tree,
  new routes), README.md (Web UI section, LAN access, password instructions, privacy note),
  CHANGELOG.md. See CC_WEB_GUI_PLAN.md Phase 10.

---

TODO-063: Web GUI — status bar data in nav
Priority: Low
Status: Open
Added: 2026-05-19
Description: Every web page calls GET /api/status on load and displays DB entry count
  + status in the shared nav bar corner. See CC_WEB_GUI_PLAN.md TODO-063.

---

TODO-062: Web GUI — frontend/index.html landing redirect
Priority: Low
Status: Open
Added: 2026-05-19
Description: Simple /frontend/index.html with <meta refresh> redirect to /web/search.
  Shown when user hits http://localhost:5174/ directly. See CC_WEB_GUI_PLAN.md TODO-062.

---

TODO-061: Web GUI — add nav links to admin.html and map.html
Priority: Low
Status: Open
Added: 2026-05-19
Description: Add shared nav bar (or minimal "← App" back-link) to backend/admin.html
  and gui/resources/map.html. See CC_WEB_GUI_PLAN.md TODO-061.

---

TODO-060: Web GUI — frontend/bootlegs.html Bootleg catalog browser
Priority: Low
Status: Open
Added: 2026-05-19
Description: Bootleg catalog browser page. API: GET /api/bootlegs, /api/bootlegs/stats,
  /api/bootlegs/by_lb/<lb>. Filter bar (text/year/format), stats row, paginated table,
  expandable detail panel per row. See CC_WEB_GUI_PLAN.md TODO-060.

---

TODO-059: Web GUI — frontend/lb_master.html LB Master viewer
Priority: Medium
Status: Open
Added: 2026-05-19
Description: LB Master status browser. API: GET /api/lb_master, /api/lb_master/stats,
  /api/lb_master/history/<lb>. Stats bar (counts by status), filter bar, paginated table,
  inline history expansion on row click. See CC_WEB_GUI_PLAN.md TODO-059.

---

TODO-058: Web GUI — frontend/entry.html Entry detail page
Priority: High
Status: Open
Added: 2026-05-19
Description: Entry detail page at /web/entry?lb=<lb_number>. Shows entry metadata,
  checksum table, file list, change history, LB master record, personal notes, and
  Add to Collection / Forum Preview actions. Linked from Search, Collection, Lookup
  result rows. See CC_WEB_GUI_PLAN.md TODO-058.

---

TODO-057: Web GUI — Collection tab write operations
Priority: Medium
Status: Open
Added: 2026-05-19
Description: Add Remove from Collection button (DELETE /api/collection/<lb>) with confirm
  dialog, Add to Wishlist button for Missing rows (POST /api/wishlist), and counts update
  after mutations. See CC_WEB_GUI_PLAN.md TODO-057.

---

TODO-056: Web GUI — frontend/collection.html Collection tab (read)
Priority: High
Status: Open
Added: 2026-05-19
Description: My Collection page with three pill-tab panels: Owned (GET /api/collection),
  Missing (GET /api/collection/missing), Wishlist (GET /api/wishlist). Filters, pagination,
  status badges. See CC_WEB_GUI_PLAN.md TODO-056.

---

TODO-055: Web GUI — frontend/lookup.html Lookup tab
Priority: High
Status: Open
Added: 2026-05-19
Description: Checksum lookup page. Textarea for FFP/MD5/ST5 paste, POST /api/lookup,
  summary table + detail table, status colour coding, LB links to /web/entry, Copy TSV
  button. See CC_WEB_GUI_PLAN.md TODO-055.

---

TODO-054: Web GUI — Search tab owned column async load
Priority: Medium
Status: Open
Added: 2026-05-19
Description: After search results render, fire background GET /api/collection/lb_numbers
  and update the Owned column cells in-place. Matches _OwnedWorker pattern from the
  desktop search tab. See CC_WEB_GUI_PLAN.md TODO-054.

---

TODO-053: Web GUI — frontend/search.html Search tab
Priority: High
Status: Open
Added: 2026-05-19
Description: Main search page. Filter bar (text, field, year, status, xref-only), results
  table (LB# | Status | Date | Location | Rating | Description | Xref | Owned), client-side
  sort, pagination, status row colouring, row click → /web/entry. API: GET /api/search,
  /api/search/years, /api/collection/lb_numbers, /api/checksums/xref_lb_numbers.
  See CC_WEB_GUI_PLAN.md TODO-053.

---

TODO-052: Web GUI — frontend/utils.js shared JS utilities
Priority: High
Status: Open
Added: 2026-05-19
Description: Create frontend/utils.js with: apiFetch(), escapeHtml(), statusBadge(),
  formatDate(), paginate(), debounce(). Used by all web pages.
  See CC_WEB_GUI_PLAN.md TODO-052.

---

TODO-051: Web GUI — frontend/base.css shared dark theme
Priority: High
Status: Open
Added: 2026-05-19
Description: Create frontend/base.css porting CSS variables and component styles from
  backend/admin.html. Components: :root vars, body, nav, data table, pagination, filter
  bar, buttons, badges, spinner, error banner. See CC_WEB_GUI_PLAN.md TODO-051.

---

TODO-050: Web GUI — Flask routes for frontend static files
Priority: High
Status: Open
Added: 2026-05-19
Description: Add to backend/app.py: GET / redirect to /web/search; GET /web/<page> serves
  frontend/<page>.html (allowlist validated); GET /frontend/<path> serves frontend/ dir.
  Create frontend/ directory. Verify no / route conflict exists.
  See CC_WEB_GUI_PLAN.md TODO-050.
