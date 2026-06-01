TODO-106: Trading — multi-friend batch compare
Priority: Low
Status: Open
Added: 2026-05-30
Description: Extend the Trading screen to compare your collection against multiple friends at
  once — show a matrix view (friends × shows) so you can find the best candidate to trade
  any given recording with. Also: add a GET /api/trading/friends/<id>/entries route so the
  GUI can retrieve raw friend entries without going through the compare diff endpoint.

---

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

---

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

