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

TODO-070: i18n integration testing — all 5 languages end-to-end
Priority: Medium
Status: Open
Added: 2026-05-19
Description: For each of the 5 languages: set ui_language in meta, restart app,
  verify tab titles, button labels, column headers, placeholder text, and QMessageBox
  dialogs are translated. Verify LB numbers and checksums are not garbled. Verify
  English still works as default. Run py_compile on all gui files.
  Prerequisite: TODO-069. See instructions/CC_I18N.md TODO-070 section for checklist.
