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

