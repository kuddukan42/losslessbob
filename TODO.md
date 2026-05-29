TODO-129: Audio format + bitrate detection — surface FLAC/WAV/SHN and 16/44.1 vs 24/96
Priority: Medium
Status: Open
Added: 2026-05-28
Description: Detect and display the audio container format and bit-depth/sample-rate for each
  collection entry, replacing the hardcoded "FLAC · 16/44" pill in ScreenCollection's detail
  panel (see TODO-127).
  Goals:
    • Backend probe: for a given entry's disk_path, inspect representative audio file(s) and
      report container format (FLAC / WAV / SHN / APE / etc.) and bit depth + sample rate
      (e.g. 16/44.1, 24/48, 24/96). Use soundfile/libsndfile where it can read the subtype;
      fall back to ffprobe (and shntool/ffmpeg for SHN/shorten) for formats libsndfile can't open.
    • Aggregate per folder: if files are mixed, report the dominant format/rate or flag "mixed".
    • Caching: store results so repeated views don't re-probe (new column on the collection/entry
      record or a small cache keyed by disk_path + mtime); runs in a QThread/background worker,
      never on the main thread.
    • Expose via a backend route (e.g. GET /api/collection/<lb>/audioinfo) returning
      {format, bit_depth, sample_rate, mixed, files_probed}.
    • Surface in the GUI: real format + bitrate pill in the My Collection detail panel; consider
      a column/badge in the collection table and reuse in the Verify tab where useful.
    • Handle missing/offline folders gracefully (show "—" rather than erroring).

---

TODO-128: gui_next ScreenCollection — cross-tab nav + replace coming-soon stubs
Priority: Low
Status: Open
Added: 2026-05-28
Description: Parity with old collection_tab.py. New screen lacks the old "Go to LB" navigation
  (history rows → My Collection, missing → Lookup) and stubs three detail actions with toasts.
  Goals:
    • Wire "Attachments", "Spectrograms", "On map" detail buttons to their real screens
      (ScreenAttachments / ScreenSpectrograms / ScreenMap) instead of "coming soon" toast.
    • Add cross-screen navigation: detail/history → open LB in Lookup; Missing row → Lookup.
    • Mirror old lookup_lb / send_to_spectrograms signal behaviour via the renderer router.

---

TODO-127: gui_next ScreenCollection — real Size/codec data or drop placeholder pills
Priority: Low
Status: Open
Added: 2026-05-28
Description: Detail panel shows hardcoded `size: ''` and a static "FLAC · 16/44" pill that are
  not backed by real data. Either compute folder size / audio format from the backend and
  populate them, or remove the placeholder fields to avoid showing fake metadata.

---

TODO-126: gui_next ScreenCollection — column header sorting
Priority: Low
Status: Open
Added: 2026-05-28
Description: Old collection_tab.py supports click-to-sort on every column header (with persisted
  widths). The new virtualized table only filters/searches. Add sortable headers (LB#, Status,
  Date, Location, Folder, Disk path, Confirmed, FP) with typed sort keys.

---

TODO-125: gui_next ScreenCollection — bulk Update Location + standard-name/NFT cross-check
Priority: Medium
Status: Open
Added: 2026-05-28
Description: New "Update location" requires exactly one row and just PATCHes disk_path/folder_name
  with no validation. Old tab supports multi-row relocate and runs _cross_check_folder /
  _get_standard_lb_name (canonical YYYY-MM-DD Location (LB-XXXXX)[-NFT] naming) on relocate.
  Goals:
    • Allow bulk relocate across multiple selected rows.
    • Cross-check folder name against /api/folder_naming/standard/<lb> and surface mismatches
      (reuse the reconcile/standard-name pattern); honour NFT suffix via /api/lb_master/<lb>/nft.

---

TODO-124: gui_next ScreenCollection — non-recursive Scan Directory + owned-aware preview
Priority: Medium
Status: Open
Added: 2026-05-28
Description: New UI's "Scan directory" and "Scan tree…" both call /api/pipeline/scan-tree
  (recursive) and skip the old scan-preview dialog. Old tab distinguishes a non-recursive
  Scan Directory from recursive Scan Tree and shows a preview listing each found folder with
  an "Already Owned" column before adding.
  Goals:
    • Restore non-recursive directory scan (depth-1) distinct from recursive tree scan.
    • Add a scan-results preview modal with LB / Folder / Path / Already Owned columns and an
      "Add All" action (cross-reference /api/collection/lb_numbers for owned state).

---

TODO-123: gui_next ScreenCollection — Notes column + notes field in Add dialog
Priority: Medium
Status: Open
Added: 2026-05-28
Description: Old tab has a Notes column (COLL_HEADERS) and lets the user edit LB / Folder Name /
  Disk Path / Notes when adding. New AddFolderModal only captures the LB number and the table
  has no Notes column.
  Goals:
    • Add a Notes column to the collection table (from c.notes).
    • Add an editable Notes field (and editable folder name) to AddFolderModal, persisted via
      POST /api/collection.

---

TODO-122: gui_next ScreenCollection — Wishlist columns/edit + Duplicates grouped tree
Priority: Medium
Status: Open
Added: 2026-05-28
Description: Old tab has dedicated Wishlist and Duplicates sub-views collapsed into flat filter
  chips in the new screen.
  Goals:
    • Wishlist: expose priority / notes / added-date / rating columns and inline edit
      (currently only a star toggle exists).
    • Duplicates: render duplicates grouped-by-show (old used a QTreeWidget) with per-variant
      ratings, plus "Open on LosslessBob" and "Remove from Collection" actions, instead of a
      flat isDuplicate chip.

---

TODO-121: gui_next ScreenCollection — global Forum & Torrent History views
Priority: High
Status: Open
Added: 2026-05-28
Description: Old tab has standalone "Forum History" and "Torrent History" sub-tabs listing ALL
  records across the collection with actions; new screen only shows per-selected-row history as
  read-only pills.
  Goals:
    • Global Forum History list (GET /api/forum_posts): Open in Browser, Remove Record
      (DELETE /api/forum_post/<id>), and go-to-LB navigation.
    • Global Torrent History list (GET /api/torrents) with go-to-LB navigation.
    • Make the per-row history rows actionable rather than display-only.

---


---



TODO-116: gui_next — identify and wire ScreenPipeline remaining 5% stub
Priority: Low
Status: Open
Added: 2026-05-28
Description: PLAN_GUI_WIRING.md notes ScreenPipeline has one pre-existing stub at ~5% (19/20 wired)
  that was not identified during the audit. Audit ScreenPipeline.tsx for any remaining console.log
  stubs, no-op handlers, or missing backend calls; identify the endpoint or IPC it should call;
  wire it up following established patterns.

---

TODO-106: Audio fingerprint matching — identify user recordings by performance date
Priority: High
Status: Open
Added: 2026-05-27
Description: Given a performance date, fingerprint all LosslessBob recordings for that date,
  fingerprint the user's local audio folder, compare them, and report similarity scores to
  determine whether the user's copy is the same recording. Clean up fingerprint data afterward.
  Goals:
    • Date picker: user selects a performance date; system fetches all LB recordings for that date.
    • LB fingerprinting: generate audio fingerprints (e.g. Chromaprint/fpcalc) for each LB
      recording's audio files (or a representative sample per track).
    • User audio ingestion: scan a user-specified folder, generate fingerprints for each audio file.
    • Comparison: score similarity between user files and LB recordings; group by recording/source.
    • Results: ranked list showing which LB recording each user file most closely matches and the
      confidence/similarity score — clearly indicating "likely same recording" vs "different source".
    • Cleanup: delete all generated fingerprint data after the session to avoid stale cache.
    • Runs in a QThread worker; progress shown in GUI.


TODO-105: Checksum lookup — flag matches against user's own collection
Priority: High
Status: Open
Added: 2026-05-27
Description: When the user performs a checksum lookup, indicate whether the checksum matches a
  recording they already have in their collection (My Collection / lb_master).
  Goals:
    • After a checksum resolves to a show, cross-reference the result against the user's
      collection records in losslessbob.db.
    • If the user already owns that recording (same checksum or same show+source), clearly
      flag it in the results — e.g. "You already have this" or a distinct badge/icon.
    • If the checksum differs from what the user has for the same show, flag it as a
      potential upgrade or duplicate-with-mismatch.
    • Works in both the GUI lookup flow and any CLI checksum check path.


TODO-104: Data package restore — import user data and scraped assets from zip
Priority: Medium
Status: Open
Added: 2026-05-27
Description: Provide a restore/import flow that accepts a zip archive produced by TODO-102 or
  TODO-103 and unpacks it into the correct locations.
  Goals:
    • Accept either package type (user data or scraped assets) — detect by manifest contents.
    • For user data: restore losslessbob.db, config, lb_master state; prompt before overwriting.
    • For scraped assets: unpack pages/ and attachments/ into the configured data directory.
    • Validate the manifest (checksums or file count) before committing the restore.
    • Surface progress and any conflicts clearly in the GUI or CLI.
    • Dry-run option: show what would be overwritten without writing anything.


TODO-103: Data package — scraped attachments and pages
Priority: Medium
Status: Open
Added: 2026-05-27
Description: Bundle all scraped data (downloaded HTML pages and attachments from the forum/setlist
  scraper) into a distributable data package archive.
  Goals:
    • Package contents: pages/ folder HTML files and attachments/ folder files.
    • Output: a dated archive (zip or tar.gz) with a manifest listing file count and total size.
    • Provide an export action in the GUI or CLI.
    • Useful for seeding other installs or sharing the scraped corpus without re-scraping.


TODO-102: Data package — user data export
Priority: Medium
Status: Open
Added: 2026-05-27
Description: Bundle all user-generated data (losslessbob.db, any user config, collection state,
  notes, overrides) into a portable export package for backup or migration.
  Goals:
    • Package contents: losslessbob.db, config files, lb_master export if applicable.
    • Output: a dated archive with a human-readable manifest.
    • Provide an import/restore path so the user can seed a fresh install from the package.
    • Exclude scraped assets (covered by TODO-103).


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
