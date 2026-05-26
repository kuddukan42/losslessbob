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



TODO-097: Add purge option for geocoding data
Priority: Medium
Status: Open
Added: 2026-05-24
Description: Provide a way to purge cached geocoding data from the database.
  Goals:
    • Add a button or action (likely in the Setup or Map tab) to clear all geocoded
      lat/lon data from the concerts/geocoding table(s).
    • Allow selective purge (e.g. only failed/null results) vs full wipe.
    • After purge, trigger or prompt user to re-run geocoding so fresh data can be fetched.
    • Useful when switching geocoding providers or fixing bad cached coordinates.

---

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

TODO-091: Bundle Windows shntool binary from tools/ into the project distribution
Priority: Medium
Status: Open
Added: 2026-05-24
Description: The Windows shntool binary has been placed in the tools/ folder. It should be
  formally included in the project so it is available to Windows users without a separate
  manual install.
  Steps:
    • Add tools/shntool.exe (or equivalent) to version control (confirm it is not already
      .gitignored).
    • Update the Windows build/packaging process (PyInstaller spec or equivalent) to include
      the binary in the bundled distribution.
    • Update the shntool path-resolution logic to look in tools/ (relative to the app root or
      frozen executable path) before falling back to PATH.
    • Document the binary source/version in PROJECT.md and note any licence considerations.

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

TODO-088: Master update — pull lb_master from GitHub repo instead of local file
Priority: High
Status: Open
Added: 2026-05-23
Description: The "Install Master Update" flow currently looks for a local file to import.
  It should instead download the latest lb_master data directly from the GitHub repository
  (kuddukan42/losslessbob) so users get one-click updates without manually sourcing a file.
  Implementation sketch:
    • Define a canonical URL for the master data asset in the repo (e.g. a release asset
      or a raw file at a known path like data/lb_master.db or data/lb_master.json).
    • Add a download worker (QThread) that fetches the file via requests with progress
      reporting, then hands off to the existing import/merge logic.
    • Show a progress dialog during download; handle network errors and HTTP non-200
      responses gracefully with a user-facing message.
    • Verify a checksum or file signature after download before importing.
    • Keep the local-file fallback path available (e.g. "Install from file…" secondary button)
      for offline or dev use.

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
