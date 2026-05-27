TODO-101: Add SQL query box to DB Editor for manual query execution
Priority: Medium
Status: Open
Added: 2026-05-25
Description: Add a SQL input box to the DB Editor tab so the user can run arbitrary queries
  against losslessbob.db directly from the GUI without needing an external SQLite tool.
  Goals:
    • Add a multi-line text input (QPlainTextEdit) and a "Run" button to the DB Editor.
    • Execute the query via the backend (Flask route or direct db call in a QThread worker).
    • Display results in a table view (QTableWidget or reuse existing table component).
    • Show row count and any error messages clearly below the results.
    • Read-only safety: optionally warn or block on destructive statements (DROP, DELETE, etc.)
        unless the user confirms.



TODO-094: Rework UI per Claude design prototype
Priority: Medium
Status: Open
Added: 2026-05-24
Description: Overhaul the PyQt6 GUI to match the design prototype produced by Claude.
  Goals:
    • Implement the new layout, colour scheme, and component structure from the prototype.
    • Ensure all existing functionality is preserved during the rework.
    • Verify Qt repaint/viewport behaviour after layout changes.
    • Update PROJECT.md file structure and GUI section to reflect new tab/widget organisation.

---

TODO-093: Archive.org uploader
Priority: Low
Status: Open
Added: 2026-05-24
Description: Add an uploader that can publish items (releases, checksums, metadata) to
  archive.org (Internet Archive). Goals:
    • Authenticate with archive.org via API key / S3-like credentials.
    • Upload release files and/or checksum manifests to a designated IA collection.
    • Track upload status per item in the database to avoid re-uploading.
    • Expose upload controls in the GUI (select item → upload button, progress, status).
    • Respect IA rate limits and handle retries gracefully.

---



TODO-089: Add acknowledgements section to About dialog
Priority: Low
Status: Open
Added: 2026-05-24
Description: Add an Acknowledgements section to the About dialog crediting key contributors
  and resources, including at minimum:
    • Losslessbob (the original archive/project that inspired this tool)
    • Robert Cook (contributor)
    • Rumrunners (community/resource)
  Include a scrollable or expandable area if the list grows long. Keep styling consistent
  with the existing About dialog layout.

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
