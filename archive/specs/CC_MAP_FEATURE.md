# Plan: Map View of LB Locations

## Implementation Status (last audited 2026-05-17)

⬜ **Not started — deferred to end of implementation queue (may be cut).** Nothing in this plan has been built yet.

- No `location_geocoded` table in `backend/db.py`.
- No `backend/geocoder.py`, no `tools/geocode_locations.py`.
- No `gui/map_tab.py` or `gui/resources/leaflet/` assets.
- `PyQt6-WebEngine` is not yet in `requirements.txt` (though the package is already imported elsewhere — `gui/attachments_tab.py` uses `QWebEngineView` for its in-app browser pane, so the dep is effectively present even if not pinned).

Prerequisite from the main integrity plan that **is** already shipped: the `lb_master` table and the `lb_status` Public/Private/Missing classification used for marker coloring.

## Context

`entries.location` is freeform text — useful in lists but invisible spatially. Plotting LBs on a world map turns "Dylan toured Europe in 1981" from text into a glance: clusters in Germany/UK/Netherlands, sparser dots in Eastern Europe. Useful for browsing ("what's that show in Norway?"), for spotting gaps in coverage ("never owned anything from the Australia leg"), and for the curator to validate that location strings are clean.

The whole stack is free: OpenStreetMap tiles + Leaflet.js (rendering) + Nominatim (one-time geocoding) + the QtWebEngine widget that PyQt6 supports.

## Dependencies on Main Integrity Plan

This feature builds on items defined in `CC_LB_INTEGRITY.md`. Read that first if any of these are unfamiliar:

- **`lb_master` table** with `lb_status ∈ {public, private, missing}` — drives marker colors.
- **`my_collection` table** (user data) — drives the "owned" marker outline.
- **`MASTER_TABLES` / `USER_TABLES` lists** — defines what ships in master exports. `location_geocoded` is added to `MASTER_TABLES`.
- **`lb_status_style(status, needs_review)` helper** — shared color/icon helper for status visualization across all tabs. Map markers reuse it.
- **Curator mode** (`meta.is_curator='1'`) — gates the geocoding tools so end users never run them.
- **DB Editor tab and Setup tab** — both gain new sub-panels for this feature.

This file is self-contained on the data model and UI but assumes the main integrity plan's infrastructure exists.

## Architecture in Two Phases

**Phase 1 — Geocoding (curator-side, ships in master).** Convert each unique `entries.location` string into a (lat, lon) pair once. Cache results in a master-data table so every end user gets the geocoded coordinates as part of the master release. End users never call any external geocoding service.

**Phase 2 — Map rendering (end-user side).** A new "Map" tab embeds a Leaflet map in a `QWebEngineView`. Pulls joined `entries` + `location_geocoded` + `lb_master` + `my_collection` rows from the local DB and renders as marker clusters. All tile fetches go directly to OpenStreetMap; no other external calls.

## Schema (master data — ships)

```sql
CREATE TABLE IF NOT EXISTS location_geocoded (
    location_text   TEXT PRIMARY KEY,             -- exact entries.location value
    lat             REAL,                          -- decimal degrees, NULL if ungeocodable
    lon             REAL,
    source          TEXT NOT NULL,                 -- 'nominatim' | 'manual' | 'failed'
    confidence      TEXT,                          -- 'high' | 'medium' | 'low' (heuristic on Nominatim importance)
    display_name    TEXT,                          -- Nominatim's canonical name, for UI
    manual_override INTEGER NOT NULL DEFAULT 0,    -- 1 = curator hand-edited coordinates
    note            TEXT,                          -- curator note (e.g. "Dylan's home, approximated")
    geocoded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_geo_source ON location_geocoded(source);
```

Added to `MASTER_TABLES` (defined in main integrity plan).

**Override semantics** match `lb_master`: when `manual_override=1`, batch geocoding skips the row. Curator can hand-place tricky locations ("Big Pink", "Dylan's home in Woodstock, NY") with approximate coordinates and a note explaining the approximation.

## Phase 1: Geocoding Tool (Curator)

New CLI script `tools/geocode_locations.py`:

```
python tools/geocode_locations.py [--limit N] [--retry-failed] [--dry-run]
```

Algorithm:
1. Read all distinct `entries.location` values not already in `location_geocoded` (or with `source='failed'` if `--retry-failed`).
2. For each, query Nominatim:
   - URL: `https://nominatim.openstreetmap.org/search?q=<location>&format=json&limit=1`
   - User-Agent header set to `LosslessBob-Geocoder/1.0 (tjjenkin42@gmail.com)` — Nominatim ToS requires identifying contact.
   - Sleep 1.1s between requests (Nominatim ToS: max 1 req/sec; 100ms margin for politeness).
3. Parse response:
   - First result → `(lat, lon, display_name, importance)`. Importance ≥ 0.5 = high confidence, 0.3–0.5 = medium, < 0.3 = low.
   - Empty result → `source='failed'`, lat/lon NULL.
4. UPSERT into `location_geocoded`.
5. Progress reporting every 10 rows (script will run for hours on first pass — thousands of locations × 1.1s each).

**Backend endpoint** mirrors the script for in-app use (in case the curator prefers a button over CLI):
- `POST /api/geocode/run` — starts the geocode worker (long-running, status via existing import-progress mechanism).
- `GET /api/geocode/status` — current progress.
- `POST /api/geocode/location` — body `{location, lat, lon, note}` for manual placement.

Setup tab (curator-only) gains a **"Geocode Locations"** button + progress bar.

## Phase 2: Map Tab (End User)

New `gui/map_tab.py`. Layout:

```
┌─ Map ────────────────────────────────────────────────────────┐
│  [Filter bar: status | owned | year range | text]            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│                   ┌──────────────────┐                       │
│                   │                  │                       │
│                   │   World Map      │                       │
│                   │   (Leaflet in    │                       │
│                   │   QWebEngineView)│                       │
│                   │                  │                       │
│                   └──────────────────┘                       │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Stats: 14,820 LBs plotted | 1,768 locations | 432 unplottable│
└─────────────────────────────────────────────────────────────┘
```

**Implementation:**

- `QWebEngineView` loads a static HTML file `gui/resources/map.html` that includes Leaflet from a local copy (no CDN — works offline once tiles are cached).
- On tab show, Python queries the backend for plot data (joined `entries` + `location_geocoded` + `lb_master` + `my_collection`), passes it to the page via `runJavaScript("loadMarkers(<json>)")`.
- Each marker carries `{lb, date, location, status, owned, lat, lon}`. Status drives the marker color via the shared `lb_status_style()` helper (Public default, Private blue, Missing gray). Owned LBs get a thicker outline.
- Marker clustering via `leaflet.markercluster` plugin (also local copy). Without clustering, ~15k markers tank the renderer.
- Click marker → popup with LB number, date, location, status badge, **"Open in Search"** button (uses Qt's `QWebChannel` to call back into Python and switch tabs with the LB selected).
- Hover cluster → highlight the bounding region.

**Backend endpoint:**
```
GET /api/map/data?status=&owned=&year_min=&year_max=&q=
→ {markers: [{lb, lat, lon, date, location, status, owned, ...}, ...],
   unplottable_count: 432}
```

The query uses the same filter set as Search, returning only rows with non-NULL lat/lon. `unplottable_count` exposes "how many LBs were filtered out due to ungeocoded location" so users know they're not seeing everything.

## Tile Source and Offline Support

- **Default:** OpenStreetMap standard tiles via `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`. Free, attribution required ("© OpenStreetMap contributors" — Leaflet provides the default attribution control).
- **Caching:** Browser cache (QtWebEngine's built-in) handles tile reuse within a session. Persistent offline cache is a separate enhancement — not in v1.
- **No API key needed.** No paid tiers. No tracking pixels.

If usage ever becomes uncomfortable (OSM rate limits, attribution complaints), drop-in alternatives are CartoDB Voyager or Stamen Toner Lite — both also free with attribution.

## Dependency Add: QtWebEngine

PyQt6 ships QtWebEngine as a separate package `PyQt6-WebEngine`. It's substantial (~50 MB) but standard.

- Add to `requirements.txt`: `PyQt6-WebEngine==6.x.x` (match the existing PyQt6 version).
- README and installation docs note the new dependency.
- Map tab is gracefully disabled if QtWebEngine import fails: tab still appears, shows a stub message "QtWebEngine not installed — see README to enable the Map tab." This way the app doesn't break for users on minimal installs.

## Filtering & Interactivity

Filter bar applies the same status/owned/year/text filters as Search. Changes re-issue the backend query and re-call `loadMarkers()`. Cheap because the JSON payload is ~kb-scale even for 15k markers.

**Geographic filtering by viewport (zoom-to-region):** the map's currently-visible bounds can drive a "filter by visible area" toggle that shows a count + a "List these LBs in Search tab" button.

**Heatmap mode** (toggle): swaps marker clusters for a density heatmap (leaflet.heat plugin). Useful for spotting touring patterns at a glance.

## Curator UI for Geocoding Maintenance

DB Editor tab gains a **"Location Geocoding"** sub-panel (curator only):

- Table of `location_geocoded` rows with columns: Location, Source, Confidence, Lat, Lon, Manual?, Note.
- Filter: `All | Failed | Low confidence | Manual overrides`.
- Double-click row → opens a **Place Manually** dialog with a small embedded map; curator drags a pin to the right spot, optionally adds a note, saves → `manual_override=1`, `source='manual'`.
- Failed rows are a curator's punch list — bad scrapes, weird location strings, ambiguous historical names.

## Edge Cases

- **Same location text used by many LBs:** all share one geocoded row; marker clustering handles density. No duplication.
- **Location with multiple plausible places** (e.g., "Springfield" — there are dozens): Nominatim picks the highest-population one. Curator overrides if wrong; the note explains the override reason.
- **Approximate locations** ("Dylan's home", "Big Pink"): geocode as failed by default; curator manually places with approximate coordinates and note like "Approximate — Saugerties, NY area".
- **Locations that change name historically** ("Leningrad" → "St. Petersburg"): Nominatim handles many of these via OSM aliases. If not, manual override.
- **New LBs after geocoding pass:** when a new flat-file release adds entries with new locations, the next master release won't have geocoded coords for them. Map tab shows them as unplottable until the curator runs the geocoder again. Suggest auto-incremental geocoding tied into the flat-file apply step as a follow-up.
- **Ungeocodable locations counted but not lost:** the `unplottable_count` in the map response and the stats footer ensure users always see "you're looking at N of M total entries". No silent omissions.
- **GDPR / network use disclosure:** OSM tile requests reveal IP + viewport to OSM's CDN. Document this in README so privacy-sensitive users know.

## Files to Modify

| File | Change |
|---|---|
| New: `backend/geocoder.py` | Nominatim client, batch driver, manual-override helpers. |
| New: `tools/geocode_locations.py` | CLI runner around the geocoder. |
| `backend/db.py` | Add `location_geocoded` to `init_db()` and `MASTER_TABLES`. Add `get_map_data(filters)` join helper. |
| `backend/app.py` | Add `GET /api/map/data`, `POST /api/geocode/run`, `GET /api/geocode/status`, `POST /api/geocode/location`. |
| New: `gui/map_tab.py` | The Map tab. |
| New: `gui/resources/map.html` | Static page with Leaflet + markercluster + heatmap plugins (local copies). |
| New: `gui/resources/leaflet/` | Local copy of Leaflet JS+CSS and required plugins. |
| `gui/main_window.py` | Register Map tab. Try/except import of QtWebEngine; stub-out if missing. |
| `gui/dbedit_tab.py` | Add Location Geocoding sub-panel (curator only) with manual placement dialog. |
| `gui/setup_tab.py` | "Geocode Locations" button (curator only) + progress bar. |
| `requirements.txt` | Add `PyQt6-WebEngine`. |
| `README.md` | Document the new dependency, OSM attribution, Nominatim ToS compliance for curator. |
| `PROJECT.md` | Document the geocoding pipeline, map tab, master data inclusion. |
| `CHANGELOG.md` | User-visible: new Map tab with marker clusters + filters. |

## Verification

1. **Geocoding — fresh location:** Run geocoder against a known location ("Forest Hills, NY"). Confirm row inserted with reasonable lat/lon.
2. **Geocoding — rate limit:** Run against 5 sequential locations; confirm 1.1s gap between requests (check timestamps).
3. **Geocoding — failed:** Geocode a nonsense location ("xkdjs"). Confirm row inserted with `source='failed'`, lat/lon NULL.
4. **Geocoding — manual override skipped:** Manually place a location, then re-run geocoder with `--retry-failed`. Confirm the manual row is untouched.
5. **Map tab — renders:** Open Map tab. Confirm world map loads with OSM tiles visible.
6. **Map tab — markers:** Confirm clustered markers visible at low zoom; expand at high zoom shows individual pins.
7. **Map tab — status colors:** Spot-check Public/Private/Missing colors on individual markers.
8. **Map tab — owned outline:** Owned LBs render with a distinct outline.
9. **Map tab — popup → Search:** Click marker, click "Open in Search" — confirm Search tab opens with that LB selected.
10. **Map tab — filters:** Apply status=Private filter; confirm only Private markers visible and the unplottable count updates.
11. **Map tab — unplottable count:** Confirm footer shows total vs. plotted accurately.
12. **Heatmap toggle:** Switch to heatmap; confirm density visualization replaces markers without errors.
13. **QtWebEngine missing graceful fail:** Uninstall `PyQt6-WebEngine`. Restart. Confirm Map tab shows stub message; app otherwise works.
14. **Master export contains geocoded:** Export master, confirm `location_geocoded` ships and the end-user's map populates without running the geocoder locally.
15. **Curator manual placement:** Open DB Editor → Location Geocoding → double-click a failed row → drag pin → save. Confirm row updates with `source='manual'`, `manual_override=1`, note saved.
