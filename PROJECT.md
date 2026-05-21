# LosslessBob Checksum Lookup — Project Overview

**Purpose:** Cross-platform desktop replacement for the original Windows-only `Checksum_Lookup` utility used by collectors of Bob Dylan lossless recordings from the [LosslessBob archive](http://www.losslessbob.wonderingwhattochoose.com). Users paste or load checksum files (FFP, MD5, ST5/SHA1) and the app matches them against the archive database to identify which LosslessBob entry (LB number) a recording belongs to, and whether the set is complete or has missing/duplicate files.

---

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| GUI | PyQt6 | 6.7.1 |
| Web view (attachments) | PyQt6-WebEngine | 6.7.0 |
| REST backend | Flask + Flask-CORS | 3.0.3 / 4.0.1 |
| WSGI server (optional) | Waitress | 3.0.0 |
| Database | SQLite3 | (stdlib) |
| Bloom filter | pybloom-live | 4.0.0 |
| Web scraping | BeautifulSoup4 + lxml | 4.12.3 / 6.1.0 |
| HTTP client | Requests | 2.32.3 |
| File watching | Watchdog | 4.0.1 |
| Torrent generation | torf | 4.3.1 |
| Credential storage | keyring | 25.7.0 |
| Numerical computing | numpy | 2.4.6 |
| Audio fingerprinting | librosa | 0.11.0 |
| Audio I/O | soundfile | 0.13.1 |
| Signal processing | scipy | 1.17.1 |
| JIT compilation | numba | 0.65.1 |
| Language | Python | 3.11+ |

**Architecture pattern:** The GUI and backend are separated by a local Flask REST API (port 5174). The GUI makes HTTP requests to `localhost:5174` for all data operations. Flask runs in a daemon thread started before the PyQt6 event loop.

---

## File Structure

```
losslessbob/
├── main.py                   # Entrypoint: starts Flask thread, then PyQt6 app
├── cli.py                    # Headless CLI: lookup / search / stats / import / serve
├── run_backend.py            # Headless entrypoint: Flask only, no GUI (phone/LAN use)
├── requirements.txt
├── PROJECT.md                # This file
├── backend/
│   ├── app.py                # Flask REST API — all routes
│   ├── admin.html            # Mobile-friendly admin control panel (served at /admin)
│   ├── db.py                 # SQLite layer, checksum parsing, search
│   ├── checksum_utils.py     # Shared: FFP/MD5/shntool compute, lbdir parse, verify, generate
│   ├── credentials.py        # OS keyring credential storage (SERVICE_QBT, SERVICE_WTRF)
│   ├── flat_file.py          # Flat-file update pipeline: discover/download/diff/apply + audit tables
│   ├── importer.py           # Flat-file import logic (legacy: imports from local file path)
│   ├── folder_naming.py      # Shared helpers: apply_nft_suffix, strip_nft_suffix, nft_discrepancy, build_standard_name
│   ├── rename.py             # write_rename_log() — rename_log.txt + rename_history DB row
│   ├── scraper.py            # Web scraper for losslessbob.com (per-entry metadata)
│   ├── site_crawler.py       # Full-domain BFS site mirror spider (data/site/)
│   ├── html_utils.py         # rewrite_links(): server-absolute → relative for file:// browsing
│   ├── bootleg_scraper.py    # Bootleg-CD catalog (LBBCD index) scraper
│   ├── scheduler.py          # Watchdog file watcher, auto-import
│   ├── fingerprint.py        # Acoustic fingerprinting engine (Wang/Shazam landmark algorithm)
│   ├── sox_utils.py          # SoX/ffmpeg tool detection + spectrogram generation
│   ├── startup_log.py        # Startup timing logger → data/startup.log
│   ├── torrent_maker.py      # torf-based .torrent generation; tracker CDN fetch
│   ├── qbittorrent.py        # qBittorrent WebUI API v2 integration
│   ├── forum_poster.py       # SMF 2.x WTRF forum topic posting
│   └── geocoder.py           # Nominatim geocoder: geocode_one, place_manual, run_batch, get_progress
├── gui/
│   ├── main_window.py        # Main window, tab container, menu, status bar
│   ├── lookup_tab.py         # Core feature: paste/load checksums, view results
│   ├── verify_tab.py         # Verify local checksum files (.ffp/.md5/.st5) against audio
│   ├── lbdir_tab.py          # Verify official lbdir*.txt files against audio on disk
│   ├── search_tab.py         # Full-text search across entries
│   ├── bootlegs_tab.py       # Bootleg-CD catalog browser (LBBCD)
│   ├── scraper_tab.py        # Scraper tab: site crawler, entry scraper, bootleg catalog, session history
│   ├── setup_tab.py          # Import, DB management, credentials, SoX status
│   ├── attachments_tab.py    # Browse and preview cached attachment files
│   ├── rename_tab.py         # Propose and execute folder renames based on LB match
│   ├── spectrogram_tab.py    # Generate and view per-file SoX spectrograms
│   ├── dbedit_tab.py         # DB Editor: browse/edit/delete rows, export CSV
│   ├── theme_tab.py          # Color theme picker and custom color editor
│   ├── map_tab.py            # Map tab: "Open in Browser" button + URL filter builder + curator geocoding panel
│   ├── i18n.py               # Translation loader: load_language(), supported_languages(); reads gui/locales/*.qm
│   ├── styles.py             # Generates Qt stylesheets from color dict
│   ├── locales/              # Qt Linguist translation files (.ts source + .qm compiled binary per language)
│   ├── resources/
│   │   ├── map.html          # Leaflet map page served at GET /map; fetches /api/map/data
│   │   └── leaflet/          # Bundled Leaflet 1.9.4 + markercluster 1.5.3 + leaflet.heat 0.2.0 assets
│   └── widgets/
│       ├── state_store.py       # GuiStateStore: column widths + window geometry → data/gui_state.json
│       ├── sort_keys.py         # SortableTableItem + sort_key_for() for typed client-side sort
│       └── reconcile_dialog.py  # AudioReconcileDialog: shared preview dialog for audio file renames
├── tests/
│   ├── test_lb_master.py     # lb_master schema, reconcile, override, forum guard, GUI presence
│   └── test_master_data.py   # MASTER/USER table classification, export/import, SHA + schema-version guards
├── tools/
│   └── geocode_locations.py  # CLI: batch-geocode entries.location via Nominatim (--limit, --retry-failed, --dry-run)
├── docs/
│   ├── index.html            # GitHub Pages marketing/landing page
│   └── screenshots/          # Screenshot placeholders (replace with real app screenshots)
│       └── README.md         # Guide for which screenshots to capture
└── data/
    ├── losslessbob.db        # SQLite database
    ├── *_flat_file.txt       # Tab-delimited flat-file (user-provided)
    ├── site/                 # Offline mirror of losslessbob.wonderingwhattochoose.com
    │   ├── detail/
    │   │   └── LB-{N}.html   # Entry detail pages (links rewritten for file:// browsing)
    │   ├── files/
    │   │   └── LBF-{N}-*.ext # Attachment files (.ffp, .txt, .md5, etc.)
    │   ├── lbbcd/
    │   │   └── LBBCD-{N}.html# LBBCD detail pages
    │   └── bynumber/
    │       └── *.html        # Bynumber index pages
    ├── gui_state.json        # Persistent GUI state: column widths, window geometry (user data — not in master)
    ├── backups/              # Auto + manual DB backups (VACUUM INTO snapshots, last 10 kept)
    ├── downloads/            # Downloaded flat-file zips (kept after apply for audit purposes)
    ├── exports/              # Master-data snapshots + .manifest.json sidecars for publishing
    └── torrents/
        └── *.torrent          # Generated .torrent files (excluded from git)
```

---

## Database Schema

**File:** `data/losslessbob.db`

### `checksums` — Core lookup table
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| checksum | TEXT NOT NULL | MD5/SHA1/FFP hash value |
| filename | TEXT NOT NULL | Audio filename |
| chk_type | TEXT | `'f'` FFP, `'s'` ST5/SHA1, `'m'` MD5 |
| lb_number | INTEGER NOT NULL | Links to LosslessBob entry |
| xref | INTEGER | 1 = cross-reference entry (not primary) |

Unique index on `(checksum, lb_number)`.

### `entries` — Entry metadata scraped from losslessbob.com
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LosslessBob number |
| date_str | TEXT | Concert date |
| location | TEXT | Venue / city |
| cdr | TEXT | CDR info |
| rating | TEXT | Archive rating |
| timing | TEXT | Recording length |
| description | TEXT | Full text description |
| setlist | TEXT | Setlist text |
| status | TEXT | `'ok'`, `'missing'` |
| scraped_at | TIMESTAMP | When row was last scraped |

### `entry_files` — Attachment files per entry
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER NOT NULL | |
| filename | TEXT | Remote filename (`LBF-N-name.ext`) |
| clean_name | TEXT | Display name (prefix stripped) |
| file_url | TEXT | Full remote URL |
| downloaded | INTEGER | 1 = cached locally in `data/attachments/` |

PK: `(lb_number, filename)`.

### `entries_fts` — FTS5 full-text search index (virtual table)
Content table over `entries`. Columns: `description`, `setlist`, `location`, `date_str`. Maintained by `entries_fts_insert/update/delete` triggers. Rebuilt by `init_db()` on first run when index is empty but `entries` is not.

### `entry_changes` — Field-level scrape diff log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER NOT NULL | Entry that changed |
| field | TEXT NOT NULL | Field name from `TRACKED_ENTRY_FIELDS` |
| old_value | TEXT | Previous value |
| new_value | TEXT | New value after scrape |
| changed_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

Index: `idx_changes_lb ON entry_changes(lb_number, changed_at DESC)`.

### `integrity_events` — Watchdog file-change alert log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | Owning collection entry |
| disk_path | TEXT | Path being watched |
| event_type | TEXT | e.g. `'deleted'`, `'modified'` |
| detail | TEXT | Human-readable description |
| occurred_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| acknowledged | INTEGER | 0 = unread, 1 = dismissed |

### `torrents` — Generated .torrent file records
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | FK to entries |
| torrent_path | TEXT | Absolute path to .torrent in data/torrents/ |
| source_folder | TEXT | Absolute path to LB folder on disk |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| infohash | TEXT | Read from .torrent via torf at creation time |
| added_to_qbt | INTEGER | 0 / 1 |
| added_to_qbt_at | TIMESTAMP | NULL if never added |
| qbt_infohash_confirmed | INTEGER | 0 / 1 |
| last_seen_at | TIMESTAMP | Last time source_folder verified on disk |
| excluded_files | TEXT | JSON list of files excluded from torrent |

### `rename_history` — Folder rename audit log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | FK to entries (nullable) |
| old_path | TEXT | Full path before rename |
| new_path | TEXT | Full path after rename |
| renamed_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| source | TEXT | 'rename_tab', 'collection_tab', or 'auto' |
| notes | TEXT | Warnings, mismatch details, relocation notes |

### `forum_posts` — Forum post log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | FK to entries |
| subject | TEXT | Post subject line |
| topic_url | TEXT | Full URL to the created topic |
| board_id | INTEGER | SMF board number posted to |
| posted_at | TEXT | UTC datetime, defaults to datetime('now') |

### `lb_alias` — Curator-authored alias mappings (MASTER table)
| Column | Type | Notes |
|--------|------|-------|
| alias_lb | INTEGER PK | The secondary / duplicate LB number |
| canonical_lb | INTEGER NOT NULL | The authoritative LB number it maps to |
| relationship | TEXT NOT NULL | `'duplicate'`, `'supersedes'`, or `'see_also'` (default `'duplicate'`) |
| note | TEXT | Optional curator note |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

CHECK constraint: `alias_lb != canonical_lb`. Chains are rewritten to max 1 hop on insert.
Index: `idx_lb_alias_canonical ON lb_alias(canonical_lb)`.

### `folder_lb_link` — User-saved folder→LB sticky links (USER table)
| Column | Type | Notes |
|--------|------|-------|
| folder_path | TEXT PK | Absolute path of the folder |
| lb_number | INTEGER NOT NULL | LB number the user pinned this folder to |
| linked_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| note | TEXT | Optional user note |

Index: `idx_folder_link_lb ON folder_lb_link(lb_number)`.

### `bootleg_titles` — LBBCD catalog index (MASTER table)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER NOT NULL | Canonical LB this bootleg maps to |
| title | TEXT | As displayed; empty string when blank on page |
| date_str | TEXT | Raw page date string, e.g. `"xx/xx/67"` |
| date_iso | TEXT | Best-effort ISO date (`YYYY-MM-DD`, `YYYY-MM`, or `YYYY`); NULL if unparseable |
| year | INTEGER | 4-digit year for fast filtering; NULL if wholly unknown |
| location | TEXT | |
| cd_count | INTEGER | 0 is valid (vinyl-only / unreleased) |
| lbbcd_id | INTEGER | e.g. 275 from `LBBCD-275.html`; NULL if no link |
| lbbcd_url | TEXT | Relative URL to the LBBCD detail page; NULL if no link |
| scraped_at | TIMESTAMP | |

Natural key for diffing: `(lb_number, title, date_str)`. Indexes: `idx_bootleg_lb`, `idx_bootleg_lbbcd` (partial WHERE lbbcd_id NOT NULL), `idx_bootleg_year`, `idx_bootleg_title COLLATE NOCASE`.

### `bootleg_scrapes` — Scrape audit log (MASTER table)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| source_url | TEXT NOT NULL | |
| scraped_at | TIMESTAMP | |
| http_etag | TEXT | |
| http_last_modified | TEXT | |
| body_sha256 | TEXT | |
| rows_total | INTEGER | |
| rows_added | INTEGER | |
| rows_changed | INTEGER | |
| rows_removed | INTEGER | |
| status | TEXT NOT NULL | `success`, `no_change`, or `failed` |

### `scrape_sessions` — Crawler session log (MASTER table)
One row per site-crawler run started via POST /api/crawler/start.
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| started_at | TIMESTAMP | Session start time (DEFAULT CURRENT_TIMESTAMP) |
| finished_at | TIMESTAMP | Session end time |
| scope | TEXT | `'full'`, `'incremental'`, etc. |
| start_url | TEXT | Entry-point URL for this session |
| pages_fetched | INTEGER | HTTP 200 responses (new/changed body saved) |
| pages_304 | INTEGER | HTTP 304 (unchanged) responses |
| pages_skipped | INTEGER | Skipped by robots.txt or duplicate |
| pages_failed | INTEGER | Network errors or non-200/304 responses |
| files_fetched | INTEGER | Attachment files downloaded |
| status | TEXT | `'running'`, `'done'`, `'stopped'`, `'error'` |
| notes | TEXT | Optional freeform notes |

### `site_inventory` — Per-URL crawl state (MASTER table)
One row per unique URL discovered or fetched by the site crawler.
| Column | Type | Notes |
|--------|------|-------|
| url | TEXT PK | Absolute URL |
| status | TEXT | `'pending'`, `'downloaded'`, `'not_found'`, `'failed'`, `'skipped'` |
| relative_path | TEXT | Path relative to `data/site/`, e.g. `detail/LB-00001.html` |
| content_type | TEXT | MIME type from response header |
| size_bytes | INTEGER | Body size in bytes |
| http_status | INTEGER | Last HTTP status code received |
| last_fetched_at | TIMESTAMP | When the body was last saved |
| last_checked_at | TIMESTAMP | When the URL was last checked (including 304 hits) |
| last_modified | TEXT | `Last-Modified` header from last fetch |
| body_sha256 | TEXT | SHA-256 of the saved body |
| discovered_by | TEXT | URL of the page that linked here, or `'start'` |
| session_id | INTEGER | FK → `scrape_sessions.id` of last session that touched this row |

Indexes: `idx_inventory_status`, `idx_inventory_session`.

### `location_geocoded` — Geocoded concert locations (MASTER TABLE)
| Column | Type | Notes |
|--------|------|-------|
| location_text | TEXT PK | Matches `entries.location` verbatim |
| lat | REAL | WGS-84 latitude (NULL if geocoding failed) |
| lon | REAL | WGS-84 longitude (NULL if geocoding failed) |
| source | TEXT NOT NULL | `'nominatim'` / `'manual'` / `'failed'` |
| confidence | TEXT | `'high'` / `'medium'` / `'low'` / NULL |
| display_name | TEXT | Full display name returned by Nominatim |
| manual_override | INTEGER | 1 = curator-placed pin; batch run never overwrites |
| note | TEXT | Optional curator note |
| geocoded_at | TIMESTAMP | Last geocode attempt timestamp |

Index: `idx_geo_source ON location_geocoded(source)`.
Populated by `backend/geocoder.py:run_batch()` or `place_manual()`. Included in master-data export/import (`MASTER_TABLES`).

### `meta` — Key-value configuration store
Persists settings between runs. Key examples:
- `import_hash` — MD5 of last imported flat file (skip re-import if unchanged)
- `last_import_date` — ISO timestamp of last import
- `auto_scrape` — `'1'` or `'0'`
- `scrape_delay_ms` — Delay between scrape requests
- `download_files` — Whether to cache attachment files
- `use_local_pages` — `'1'` or `'0'` — read metadata from `data/pages/` instead of web when available
- `search_page_size` — integer string, results per page in Search tab (default `'50'`)
- `qbt_host` — qBittorrent WebUI hostname (default `'localhost'`)
- `qbt_port` — qBittorrent WebUI port (default `'8080'`)
- `qbt_category` — optional category label for added torrents
- `qbt_tags` — optional comma-separated tag string for added torrents
- `tracker_list` — tracker list name for torrent generation (default `'best'`)
- `ui_language` — ISO 639-1 language code for the GUI (`'en'` default; `'de'`/`'fr'`/`'es'`/`'it'`/`'nl'` once translation files are installed)

### `flat_file_releases` — Flat-file update release log (MASTER table)
One row per discovered/downloaded/applied release of the LosslessBob flat-file zip.
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| detected_at | TIMESTAMP | When the release was first noticed |
| downloaded_at | TIMESTAMP | When the zip was fully downloaded |
| applied_at | TIMESTAMP | When the release was applied to the DB |
| deferred_until | TIMESTAMP | Set when user defers the prompt |
| source_page_url | TEXT | URL of the download page |
| zip_url | TEXT | Direct URL of the zip |
| zip_filename | TEXT | e.g. `Checksum_Lookup_flat_file_LastLB_12345.zip` |
| last_lb_in_name | INTEGER | LB number parsed from zip filename |
| page_timestamp | TEXT | Timestamp string shown on the download page |
| http_last_modified | TEXT | HTTP Last-Modified header from zip URL |
| zip_size_bytes | INTEGER | File size in bytes |
| zip_sha256 | TEXT | SHA-256 of the downloaded zip |
| rows_added | INTEGER | Checksum rows added on apply |
| rows_changed | INTEGER | Checksum rows updated on apply |
| rows_removed | INTEGER | Checksum rows deleted on apply |
| new_lb_min | INTEGER | Lowest LB touched by apply |
| new_lb_max | INTEGER | Highest LB touched by apply |
| status | TEXT | `detected`, `downloaded`, `applied`, `applied_legacy`, `deferred`, `failed` |
| failure_reason | TEXT | Error detail if status=failed |

Index: `idx_flat_releases_status ON flat_file_releases(status, detected_at DESC)`.

### `flat_file_changelog` — Per-row diff log for each applied release (MASTER table)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| release_id | INTEGER | FK → flat_file_releases.id |
| lb_number | INTEGER | LB number of the changed checksum |
| op | TEXT | `add`, `change`, or `remove` |
| checksum | TEXT | The checksum value |
| filename | TEXT | New filename (after op) |
| chk_type | TEXT | `f` / `s` / `m` |
| xref | INTEGER | Cross-reference flag (0 or 1) |
| old_filename | TEXT | Previous filename (op=change only) |
| old_xref | INTEGER | Previous xref (op=change only) |

Indexes: `idx_flat_changelog_release(release_id)`, `idx_flat_changelog_lb(lb_number)`.

---

## Backend: Flask API (`backend/app.py`)

**Base URL:** `http://localhost:5174`

### Checksum Lookup
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/lookup` | Parse text input and match checksums. Body: `{text}`. Returns `{summary, detail}` arrays. |

### Database Management
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/db/stats` | Row counts, latest LB number, last import date |
| GET | `/api/db/missing_lb_numbers` | List of integers in 1..max_lb absent from checksums table |
| POST | `/api/db/import` | Start async flat-file import. Returns `{ok, running}` immediately. |
| GET | `/api/db/import/status` | Poll import progress: `{running, stage, rows_parsed, rows_total, rows_merged, new_lb_count, message, error}` |
| GET | `/api/db/settings` | Load all `meta` key-value pairs |
| POST | `/api/db/settings` | Save `meta` key-value pairs |
| POST | `/api/db/reset` | Drop and recreate all tables (destructive) |
| POST | `/api/db/backup` | Create a manual DB backup via VACUUM INTO. Body `{reason?}`. Returns `{ok, path, size_bytes}`. |

### Flat File Update Pipeline
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/flat_file/discover` | Live check for a new flat-file release on the download page. Returns `{available, current_release, last_applied_release, error}`. Inserts a `detected` row in `flat_file_releases` when a new release is found. |
| POST | `/api/flat_file/download/<id>` | Download the zip for a detected release. Long-running. Returns `{path, release_id}`. |
| GET | `/api/flat_file/diff/<id>` | Return `{rows_added, rows_changed, rows_removed, new_lb_min, new_lb_max}` without applying. Release must be in `downloaded` status. |
| POST | `/api/flat_file/apply/<id>` | Apply a downloaded release. Auto-backs up DB first. Updates checksums, writes changelog, reconciles lb_master. Returns diff counts. |
| POST | `/api/flat_file/defer/<id>` | Defer prompting. Body: `{days: int}` or `{until_next: true}`. |
| GET | `/api/flat_file/releases` | List all `flat_file_releases` rows, newest first. |
| GET | `/api/flat_file/changelog/<id>` | Paginated `flat_file_changelog` for a release. Query params: `limit` (default 100), `offset` (default 0). |

### Master Data (publish / subscribe)
| Method | Route | Description |
|--------|-------|-------------|
| GET  | `/api/curator` | Returns `{is_curator: bool}` (reads `meta.is_curator`). |
| POST | `/api/curator` | Body `{enabled: bool}`. Toggles the curator flag (local-only, never shipped). |
| POST | `/api/master/export` | **Curator-only** (returns 403 `curator_required` otherwise). Builds a master-only snapshot in `data/exports/`: VACUUM INTO → drops every `USER_TABLES` table → filters `meta` to `MASTER_META_KEYS` → stamps `master_version` / `master_published_at` / `master_schema_version` → verifies (no user data leaked) → SHA256 → writes `.manifest.json` sidecar. Returns `{ok, path, manifest_path, manifest}`. |
| POST | `/api/master/import` | Body `{path}`. Validates manifest SHA256, refuses schema versions newer than this client (400 `schema_too_new`), takes a `pre_master_import` backup, ATTACHes the snapshot, copies only `MASTER_TABLES` rows, replaces only `MASTER_META_KEYS` rows in `meta`, rebuilds `entries_fts`. Returns the import summary (row counts, pre/post status distribution, backup path). Errors: 400 `sha256_mismatch`, 404 `not_found`. |

### LB Master Integrity
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/lb_master/stats` | Return `{public, private, missing, max_lb, overrides, needs_review}` counts. |
| GET | `/api/lb_master` | Paginated lb_master rows. Query params: `status`, `override=1`, `review=1`, `limit` (max 2000), `offset`. |
| GET | `/api/lb_master/<lb>` | Single lb_master row joined with entry metadata. |
| POST | `/api/lb_master/reconcile` | Full rebuild of lb_master. Backs up DB first. Returns `{ok, stats}`. |
| GET | `/api/lb_master/history/<lb>` | Transition history for an LB, newest first. Query param: `limit` (default 50). |
| PUT | `/api/lb_master/<lb>/manual` | Set a manual override. Body: `{status, notes}`. |
| DELETE | `/api/lb_master/<lb>/manual` | Clear a manual override and immediately reconcile. Returns `{ok, new_status}`. |
| GET | `/api/lb_master/<lb>/nft` | Return `{nft: bool, reason}` for folder naming guidance. |
| GET | `/api/lb_master/overrides/export` | Export all `manual_override=1` rows as a JSON array. Read-only; no curator check required. Returns `[{lb_number, manual_status, manual_notes, manual_set_by, manual_set_at}, ...]`. |
| POST | `/api/lb_master/overrides/import` | **Curator-only.** Body: same JSON array. Upserts each row via `set_lb_manual_override`, writes `lb_status_history` with `trigger_event='import'`, skips lb_numbers outside current max. Returns `{imported, skipped}`. |

### Folder Naming
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/folder_naming/standard/<lb>` | Return `{standard_name, lb_status, nft}` — canonical `YYYY-MM-DD Location (LB-XXXXX)[-NFT]` folder name for an LB. Falls back to `LB-XXXXX` when the entry has no metadata. |

### LB Alias (disambiguation — master data)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/lb_alias` | List all `lb_alias` rows. Optional query param `canonical_lb` to filter. |
| POST | `/api/lb_alias` | **Curator-only.** Add alias. Body: `{alias_lb, canonical_lb, relationship, note}`. Rewrites chains (max 1 hop). Returns `{alias_lb, canonical_lb, rewrote_chain}`. 403 if not curator; 400 on validation error. |
| DELETE | `/api/lb_alias/<alias_lb>` | **Curator-only.** Remove an alias entry. |
| GET | `/api/lb_alias/resolve` | Collapse a list of LB numbers through alias table. Query param `lbs=1,2,3`. Returns `{canonical: [int, ...]}` — de-duped, order-preserving. |

### Folder→LB Sticky Links (user data)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/folder_link` | Get the sticky link for a folder. Query param `path=...`. Returns `{folder_path, lb_number, linked_at, note}` or `{}` if not linked. |
| PUT | `/api/folder_link` | Set or replace a link. Body: `{folder_path, lb_number, note?}`. Returns `{ok}`. |
| DELETE | `/api/folder_link` | Clear a link. Query param `path=...`. Returns `{ok}`. |

### Entry Detail
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/entry/<lb>` | Full entry record + checksums + files |
| GET | `/api/entry/<lb>/files` | List attachment files for entry |
| GET | `/api/entry/<lb>/changes` | Field-level scrape diff history. Query param: `limit` (default 50). Returns `[{field, old_value, new_value, changed_at}]`. |
| GET | `/api/attachment/<lb>/<filename>` | Serve cached attachment file |
| POST | `/api/entry/<lb>/scrape` | Trigger scrape of single entry |

### Search
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/search?q=&field=` | `field`: `all`, `location`, `date`, `description`. Returns all matching entries (no limit). |
| GET | `/api/checksums/xref_lb_numbers` | Return sorted list of lb_numbers that have at least one xref checksum (xref > 0). |
| GET | `/api/checksums/xref_map` | Return `{lb_number: [xref_values]}` for all LBs with xref checksums. |
| POST | `/api/checksums/reconcile_audio` | Validate proposed audio file renames. Body: `{proposals:[{checksum, input_filename, db_filename, folder}]}`. Returns each proposal annotated with `status: ok\|from_missing\|to_exists`. Non-audio extensions skipped. |
| POST | `/api/checksums/apply_reconcile_audio` | Apply audio file renames on disk. Body: `{renames:[{from, to}]}`. Returns `{applied, errors}`. |

### Site Mirror Crawler
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/crawler/start` | Start a full-domain crawl in a background thread. Body: `{scope?, force?, delay_ms?, daily_cap?}`. Returns `{ok}` or `{ok:false, error:"already running"}`. |
| GET | `/api/crawler/status` | Poll crawler state: `{running, stage, current_url, fetched, not_modified, skipped, failed, not_found, queue_size, session_id, message, stop_requested}` |
| POST | `/api/crawler/stop` | Request crawler to stop after current URL |
| GET | `/api/crawler/sessions` | Recent `scrape_sessions` rows. Query: `limit` (max 100, default 20). |
| GET | `/api/crawler/inventory` | Paginated `site_inventory` rows. Query: `status`, `path_prefix`, `limit` (max 1000), `offset`. Returns `{rows, total}`. |
| GET | `/api/crawler/inventory/stats` | Aggregate counts from `site_inventory` grouped by status. |

### Entry Metadata Scraper
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/scrape/start` | Start bulk scrape. Body: `{lb_numbers, force, download_files, delay_ms}` |
| GET | `/api/scrape/status` | Poll progress: `{running, current_lb, done, total, errors, skipped, last_action, last_source}` |
| POST | `/api/scrape/stop` | Request stop |
| POST | `/api/scrape/private_rescrape` | Force re-scrape all Private LBs (from lb_master) to detect newly-published pages. Returns `{ok, total}` |
| POST | `/api/scrape/download_pages` | Fetch and cache `data/site/detail/LB-XXXXX.html` for a range of LBs without parsing metadata or writing to the DB. Body: `{start_lb?, end_lb?, force?}`. Returns `{ok, total}`. |

### Bootleg-CD Catalog
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/bootlegs/scrape` | Start a catalog scrape. Body: `{force: bool}`. Returns `{ok, running}`. |
| GET | `/api/bootlegs/scrape/status` | Poll scrape progress: `{running, stage, rows_total, rows_added, rows_changed, rows_removed, message, error}`. |
| GET | `/api/bootlegs/lb_numbers` | Sorted list of lb_numbers that have at least one bootleg title. Used for 🎵 badge in Search tab. |
| GET | `/api/bootlegs` | Paginated filtered list. Query params: `q`, `year_min`, `year_max`, `cd_min`, `cd_max`, `lb_status`, `owned` (true/false), `has_lbbcd` (true/false), `sort_col`, `sort_dir`, `limit` (max 1000), `offset`. Returns `{rows, total}`. |
| GET | `/api/bootlegs/by_lb/<lb>` | All bootleg titles for one LB. |
| GET | `/api/bootlegs/scrapes` | Recent scrape history. Query param: `limit` (default 20). |
| GET | `/api/bootlegs/stats` | Summary: `{total, last_scraped_at, last_status}`. |

### Collection Data Management
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/collection/purge` | Purge a data scope. Body: `{scope}`. Scopes: `collection`, `wishlist`, `personal_meta`, `integrity_events`, `entry_changes`. |
| POST | `/api/collection/delete_bulk` | Remove specific entries from My Collection. Body: `{lb_numbers:[...]}`. Returns `{ok, deleted}`. |

### DB Editor
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/dbedit/tables` | List all tables with row counts and edit flags (`readonly`, `audit`, `warn`). |
| GET | `/api/dbedit/table/<name>/schema` | Return `PRAGMA table_info` for the named table. |
| GET | `/api/dbedit/table/<name>/rows` | Paginated rows. Query params: `page`, `limit` (max 500), `search`, `sort_col`, `sort_dir`. Returns `{columns, rows, total, page, limit}`. |
| PATCH | `/api/dbedit/table/<name>/row` | Update one row by rowid. Body: `{rowid, updates:{col:val,...}}`. Blocked for readonly/audit tables. |
| DELETE | `/api/dbedit/table/<name>/rows` | Delete rows by rowid list. Body: `{rowids:[...]}`. Blocked for readonly tables. |
| GET | `/api/dbedit/table/<name>/export` | Download entire table as CSV attachment. |

### Torrent Generation
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/torrent/create` | Generate a .torrent for one LB entry. Body: `{lb_number, source_folder, tracker_list?}`. Returns `{ok, torrent_path, infohash, torrent_id, name, excluded_files}`. |
| GET | `/api/torrent/<lb>` | List all torrent records for an LB entry. Each row includes `source_folder_exists` and `torrent_file_exists` booleans. |
| PATCH | `/api/torrent/<id>` | Update a torrents row (e.g. source_folder after relocation). |
| GET | `/api/torrents` | List all torrent records across every LB entry, newest first. Each row includes `source_folder_exists`, `torrent_file_exists`, `date_str`, `location`. |
| GET | `/api/trackers` | Return tracker list. Query params: `list_name`, `force_refresh`. |

### qBittorrent Integration
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/qbt/test` | Test WebUI connectivity. Body: `{host, port, username?, password?}`. Returns `{ok, version}`. |
| POST | `/api/qbt/add` | Add torrent(s) to qBittorrent. Body: `{torrent_id?, lb_numbers?, host?, port?, username?, password?, category?, tags?}`. Returns `{ok, added, total, results}`. |

### Forum Posting
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/wtrf/test` | Test WTRF forum credentials. Body: `{username?, password?}`. Returns `{ok, username}`. |
| GET | `/api/entry/<lb>/preview_forum` | Return the auto-generated subject and BBcode body for an LB entry without posting. Returns `{subject, body}`. |
| POST | `/api/entry/<lb>/post_forum` | Post a topic to the WTRF forum. Body: `{username?, password?, torrent_id?, subject?, body?}`. Optional `subject`/`body` override the auto-generated values (used when the user edits the preview). Returns `{ok, topic_url}`. |
| GET | `/api/entry/<lb>/forum_posts` | List all logged forum posts for an LB entry, newest first. |
| DELETE | `/api/forum_post/<id>` | Delete a forum post log record by id. |
| GET | `/api/forum_posts` | List all logged forum posts across every LB entry, newest first. Includes `date_str` and `location` from entries. |

### Map
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/map` | Serve `gui/resources/map.html` — Leaflet map page (OpenStreetMap tiles, OSM attribution). |
| GET | `/leaflet/<filename>` | Serve bundled Leaflet JS/CSS from `gui/resources/leaflet/`. |
| GET | `/api/map/data` | Marker data with optional query filters (`year`, `owned`, `lb_status`). Returns `[{lb_number, lat, lon, date_str, location, display_name, owned}]`. |
| GET | `/api/entries/by_lb_list` | Fetch search-compatible entry dicts for `?lbs=1,2,3` (comma-separated LB numbers, max 500). Used by Map → List in Search. |

### Geocoding
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/geocode/run` | **Curator-only.** Start batch Nominatim geocode of all un-geocoded `location` values. Returns `{ok, queued}` immediately; progress polled via `/api/geocode/status`. |
| GET | `/api/geocode/status` | Poll batch geocode state: `{running, done, total, errors, last_location}`. |
| POST | `/api/geocode/location` | **Curator-only.** Manually place or correct a coordinate. Body: `{location, lat, lon}`. Sets `manual=1` so the batch geocoder never overwrites it. |
| GET | `/api/geocode/locations` | **Curator-only.** List all rows in `location_geocoded` with geocode status. Returns `[{location, lat, lon, display_name, geocoded_at, manual}]`. |

### Admin
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/admin` | Serve mobile-friendly admin control panel (`backend/admin.html`). |
| GET | `/api/admin/status` | Combined snapshot: `{db, scrape, import_status, master, uptime_seconds}`. |
| POST | `/api/admin/restart` | Restart the entire process (`os.execv`) to pick up code changes. Returns 202 before exit. |

### Spectrogram
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/spectrogram/check` | Tool availability: `{sox_available, sox_version, ffmpeg_available}` |
| POST | `/api/spectrogram/generate` | Start batch generation. Body: `{folders, width, height, dyn_range, force}` |
| GET | `/api/spectrogram/status` | Poll batch state: `{status, current, done, total, errors, skipped, stop_requested}` |
| POST | `/api/spectrogram/stop` | Request stop after current file |
| POST | `/api/spectrogram/list` | Inventory PNGs per folder. Body: `{folders}`. Returns `{folder -> [{audio_file, audio_name, png_path, has_png}]}` |

### Verify (Local Checksums)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/verify` | Verify audio files against `.ffp`/`.md5`/`.st5` in each folder. Body: `{folders:[...]}`. |
| POST | `/api/verify/generate` | Generate `_mychecksums.ffp` and/or `_mychecksums.md5` for each folder. Body: `{folders:[...]}`. |

### LBDir
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/lbdir/check` | Find `lbdir*.txt` in each folder, parse, and verify all listed files. Returns extended result with `lbdir_found`, `lbdir_path`, `lb_number`, plus `length`/`expanded_size`/`cdr`/`wave_problems`/`fmt`/`ratio` per file from shntool_len section. |
| POST | `/api/lbdir/retrieve` | Copy `lbdir*.txt` from `data/attachments/LB-{N:05d}/` to the target folder (triggering a scrape if not yet cached). Looks up LB number from `my_collection` by `disk_path`. |
| POST | `/api/lbdir/reconcile` | Preview-only: scan disk files recursively, compute MD5, match against missing lbdir entries. Returns `{results: [{folder, proposals:[{disk_rel,lbdir_rel,md5}], unmatched_lbdir, unmatched_disk, warnings}]}`. Does NOT move any files. |
| POST | `/api/lbdir/apply_reconcile` | Apply selected rename proposals from `/api/lbdir/reconcile`. Body: `{folder, renames:[{from,to}]}`. Uses `shutil.move`; creates subdirectories as needed; never deletes. Returns `{applied, errors}`. |
| POST | `/api/lbdir/find_extra` | List files in each folder not referenced in the lbdir MD5 section (lbdir file itself excluded). Returns `{results: [{folder, extra:['rel/path',...], lbdir_rel}]}`. |
| POST | `/api/lbdir/delete_extra` | Permanently delete selected extra files. Body: `{folder, files:['rel/path',...]}`. After deletion, prunes empty subdirectories bottom-up. Returns `{deleted, removed_dirs, errors}`. |

---

## Backend: Database Layer (`backend/db.py`)

### Checksum parsing (`parse_checksum_text`)
Regex-based parser supporting three formats:

```
FFP:   filename.flac:8d08d2e3b1e3c3c8...
MD5:   8d08d2e3b1e3c3c8...  filename.flac
       8d08d2e3b1e3c3c8... *filename.flac
ST5:   8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3c3c3c3c3 *filename.shn  (40-char hex)
```

### Lookup logic (`lookup_checksums`)
For each parsed checksum, queries `checksums` table, then aggregates per LB number:
- **MATCHED** — all files in the DB set were found in input
- **MATCHED (INCOMPLETE)** — some files from DB set not in input
- **DUPLICATE** — same checksum exists in multiple LB entries
- **NOT FOUND** — no DB match at all
- **XREF** — matched, but entry is a cross-reference

### Map data (`get_map_data`)
Returns `{"markers": [...], "unplottable_count": int}`. Each marker dict: `{lb_number, date_str, location, lb_status, owned (bool), lat, lon, display_name}`. Entries with no geocoded coordinates are counted in `unplottable_count` and omitted from `markers`. Supported filter keys: `status` (str), `owned` (bool), `year_min` (int), `year_max` (int), `q` (text LIKE on lb_number/location).

---

## Backend: Geocoder (`backend/geocoder.py`)

Nominatim-based geocoder for concert location strings. Uses stdlib `urllib` only — no extra dependencies.

| Function | Description |
|----------|-------------|
| `geocode_one(location_text)` | Single Nominatim lookup. Returns dict with lat, lon, display_name, source, confidence. source='failed' on error or no result. |
| `place_manual(location_text, lat, lon, note)` | UPSERT with manual_override=1; batch run never overwrites manual rows. |
| `run_batch(limit, retry_failed, dry_run, db_path)` | Batch-geocode all un-geocoded entries.location values. Sleeps 1.1 s between requests (Nominatim ToS). Updates thread-safe _progress dict. |
| `get_progress()` | Snapshot of {running, done, total, current, errors} for GUI polling. |

**CLI tool:** `tools/geocode_locations.py` — run `python tools/geocode_locations.py --help` from project root.

---

## Backend: Checksum Utilities (`backend/checksum_utils.py`)

Shared module for local file verification and checksum generation. Used by `/api/verify`, `/api/verify/generate`, `/api/lbdir/check`, and `/api/lbdir/retrieve`.

### Functions

| Function | Description |
|----------|-------------|
| `parse_lbdir_file(path)` | Parse a `lbdir*.txt` into `{mode, md5, ffp, shntool, shntool_len}` sections. Detects mode from content. Maps shntool `.wav` → `.shn`. |
| `compute_ffp(filepath)` | Scan FLAC metadata blocks for STREAM_INFO, return bytes 18–33 as 32-char hex (MD5 of unencoded audio). Returns `None` if not valid FLAC. |
| `compute_md5(filepath)` | Streaming `hashlib.md5` of full file bytes. Returns `None` on IOError. |
| `compute_shntool(filepath)` | Shell out to `shntool md5 <file>`, parse `[shntool]` line. Raises `ShntoolNotFoundError` if binary not in PATH. |
| `detect_folder_mode(folder_path)` | Returns `'flac'`, `'shn'`, or `'mixed'` by globbing for `.flac`/`.shn` files. |
| `_mychecksums_path(folder, basename, ext)` | Returns `<folder>/<basename>_mychecksums.<ext>`, incrementing to `_mychecksums_2`, `_mychecksums_3`, … until a non-existent path is found. |
| `verify_folder(folder_path)` | Verify audio files against standalone `.ffp`/`.md5`/`.st5` checksum files in the folder. |
| `verify_folder_lbdir(folder_path, lbdir_path)` | Verify all files listed in a `lbdir*.txt` (audio + non-audio), including `length`/`cdr`/`wave_problems` from shntool_len section. |
| `find_reconcilable_files(folder_path, lbdir_path)` | Scan disk files recursively, compute MD5, match against missing lbdir entries. Returns `{proposals, unmatched_lbdir, unmatched_disk, warnings}`. |
| `find_extra_files(folder_path, lbdir_path)` | Return all disk files not referenced in the lbdir MD5 section (lbdir file itself excluded). Returns `{extra:['rel/path',...], lbdir_rel}`. |
| `generate_checksums(folder_path)` | FLAC: write `_mychecksums.ffp` + `_mychecksums.md5`. SHN: write `_mychecksums.md5` with shntool `[shntool]` format lines. Never overwrites existing files. |

### Verify result schema (per folder)
```json
{
  "folder": "/path",
  "mode": "flac|shn|mixed",
  "status": "pass|fail|incomplete|shntool_missing",
  "total": 12, "pass": 10, "mismatch": 1, "missing": 1, "extra": 0,
  "missing_types": ["ffp"],
  "files": [
    {
      "filename": "01 - Track.flac",
      "md5_expected": "...", "md5_actual": "...", "md5_status": "pass|fail|missing|na",
      "ffp_expected": "...", "ffp_actual": "...", "ffp_status": "pass|fail|missing|na",
      "shntool_expected": null, "shntool_actual": null, "shntool_status": "na",
      "st5_expected": null, "st5_status": "na",
      "on_disk": true, "overall": "pass|fail|missing|extra"
    }
  ]
}
```
`/api/lbdir/check` adds `lbdir_found`, `lbdir_path`, `lb_number` at the top level and `length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio` per file (all six shntool_len fields).

### lbdir file format
```
=== md5 for: LB-01234 ===
d41d8cd98f00b204e9800998ecf8427e *01 - Track.flac

=== ffp for: LB-01234 ===
01 - Track.flac:a9f1234...

=== shntool md5/hash for: LB-01234 ===
e5d3a...  [shntool]  01 - Track.wav

=== shntool len for: LB-01234 ===
  3:47.15  39,684,620  -  ---  FLAC  0.5012  01 - Track.wav
```

---

## Backend: Importer (`backend/importer.py`)

Accepts a tab-delimited flat file:
```
checksum<TAB>filename<TAB>type<TAB>lb_number<TAB>xref
```

**Process:**
1. MD5-hash the source file
2. Compare against stored `import_hash` in meta — skip if identical
3. Parse into temporary SQLite
4. `INSERT OR IGNORE` merge into main DB
5. Store new hash + timestamp in meta

---

## Backend: Scraper (`backend/scraper.py`)

**Target site:** `http://www.losslessbob.wonderingwhattochoose.com`

**URL pattern:** `http://...losslessbob.wonderingwhattochoose.com/detail/LB-{N:05d}.html`
- LB numbers are zero-padded to 5 digits (e.g., `LB-00042`, `LB-01025`)

**Single entry scrape:**
1. If `use_local_pages=True` and `data/site/detail/LB-{N:05d}.html` exists → read from disk (no network request)
2. Otherwise fetch `/detail/LB-{N:05d}.html` → save HTML to `data/site/detail/LB-{N:05d}.html` for future reuse
3. Parse HTML table for date, location, CDR, rating, timing
4. Extract description from `<p>` tags + bare text nodes
5. Extract setlist from numbered lines (`1. song`, `2. song`)
6. Find attachment links matching `/files/LBF-*`
7. Optionally download files to `data/site/files/`; skip if file already on disk unless `force=True` and `use_local_pages=False`
8. 404 → write `status='missing'` to DB

**Rate limiting:** 3 retries with exponential backoff; 60-second pause on HTTP 429.

**Skip logic:** `scrape_entry` skips an entry (returns `{skipped: True}`) when `force=False` and any of:
- Entry exists in DB with `status='missing'`
- Entry exists and `download_files=False` (metadata already present)
- Entry exists and all `entry_files` records have `downloaded=1` (including files synced from disk — see below)

**Filesystem sync:** Before counting pending downloads, the skip check updates any `downloaded=0` record to `downloaded=1` if the corresponding file already exists in `data/site/files/`. This handles files placed there from external sources.

**Bulk scrape:** Thread-safe progress state `{running, current_lb, done, total, errors, skipped, last_action, last_source, stop_requested}` polled by GUI every 1 second. `last_action` is `'scraped'`, `'skipped'`, or `'error'`. `last_source` is `'local'`, `'web'`, or `None`.

**Delay suppression:** The inter-request delay is suppressed when an entry was read from a local page file (`last_source='local'`) since no network I/O occurred. Web fallbacks still observe the configured delay.

---

## Backend: Scheduler (`backend/scheduler.py`)

Watchdog observer monitors the `data/` directory for `.txt` file changes.

**On file change:**
1. Debounce 2 seconds
2. MD5-hash the file
3. Compare to `import_hash` in meta
4. If different: call `run_import()` in background thread
5. If `auto_scrape` meta is `'1'`: scrape any newly imported LB numbers

---

## Backend: Site Crawler (`backend/site_crawler.py`)

Full-domain BFS spider that produces a complete offline mirror of `losslessbob.wonderingwhattochoose.com` under `data/site/`. Uses `If-Modified-Since` for efficient incremental updates.

**Entry point:** `crawl(start_url, scope, force, delay_ms, daily_cap)` — run in a daemon thread via `POST /api/crawler/start`.

**Change detection:** Per-page GET with `If-Modified-Since: <stored last_modified>`. HTTP 304 = unchanged (only `last_checked_at` updated). HTTP 200 = changed (body saved, links rewritten, inventory updated).

**Link discovery:** `_extract_links(html, page_url)` finds all same-domain `<a href>` and `<link href>` targets. External links, `mailto:`, `javascript:`, `data:`, and fragment-only anchors are ignored. Binary file extensions (`.flac`, `.mp3`, `.zip`, etc.) are skipped.

**Link rewriting:** `backend/html_utils.rewrite_links()` converts server-absolute paths to relative paths so cached pages work in a browser via `file://`.

**URL → disk mapping:** `_url_to_local(url)` maps site paths to `data/site/` sub-dirs:
- `/detail/LB-XXXXX.html` → `data/site/detail/LB-XXXXX.html`
- `/files/LBF-*` → `data/site/files/LBF-*`
- `/lbbcd/LBBCD-*.html` → `data/site/lbbcd/LBBCD-*.html`
- `/bynumber/*.html` → `data/site/bynumber/*.html`
- `/` → `data/site/index.html`

**Rate limiting:** 1500ms base delay ±20% jitter. On HTTP 429: honor `Retry-After` header (default 60s). On connection error: exponential backoff 5s → 15s → 45s. Configurable daily request cap (default 5,000). Always sequential (no concurrency). `robots.txt` read once per session.

**State:** Separate `_crawler_state` dict and `_crawler_lock` (no shared state with `scraper.py`). Fields: `running`, `stage`, `current_url`, `fetched`, `not_modified`, `skipped`, `failed`, `not_found`, `queue_size`, `session_id`, `message`, `stop_requested`.

---

## GUI: Scraper Tab (`gui/scraper_tab.py`)

Dedicated tab containing all scraping functions. Replaces the scraper controls previously in the Setup tab.

**Panel 1 — Site Mirror Crawler:**
- Scope selector (`incremental` / `full`), Force re-fetch checkbox
- Delay (ms) and Daily cap spinboxes (saved to DB settings)
- Start Crawl / Stop buttons
- Live URL status label + counts label (Fetched / 304 / Not found / Skipped / Failed / Queue)
- Progress bar (indeterminate while running)

**Panel 2 — Crawler Session History:**
- `QTableWidget` showing the 20 most recent `scrape_sessions` rows (Started, Finished, Scope, Status, Fetched, 304, Failed)
- Color-coded by status (green=done, yellow=stopped, red=error)
- Refresh button

**Panel 3 — Site Inventory:**
- Paginated `QTableWidget` showing `site_inventory` rows with Status and Path-prefix filters
- Columns: URL, Status, Size, HTTP, Last Fetched, Last Modified
- 100 rows per page with Prev/Next pagination

**Panel 4 — Entry Pages & Metadata Scraper:**
- Options: Auto-scrape after import, Download attachments, Force re-scrape, Use local pages, Delay (ms)
- Actions: Scrape All Missing, Scrape Range, Single Entry, Re-scrape Private LBs, Download Missing Pages
- Progress bar + stop button (shared `_scrape_state` from `scraper.py`)
- Embedded scraper log (read-only `QPlainTextEdit`, 500 lines)

**Panel 5 — Bootleg-CD Catalog (LBBCD):**
- Scrape Bootleg Catalog button + Force checkbox + status label
- History table (5 columns: Scraped at, Status, Total, Added, Changed)

**Background threads:** `_CrawlerStatusThread` (polls `/api/crawler/status` every 1s), `_ScrapeStatusThread` (polls `/api/scrape/status` every 1s), `_SingleScrapeThread` (one-shot single-entry scrape).

---

## GUI: Main Window (`gui/main_window.py`)

Fourteen tabs in order: **Lookup**(0) · **Rename Folders**(1) · **Verify**(2) · **lbdir**(3) · **Search**(4) · **Bootlegs**(5) · **My Collection**(6) · **Attachments**(7) · **Spectrograms**(8) · **DB Editor**(9) · **Scraper**(10) · **Setup**(11) · **Themes**(12) · **Map**(13, graceful-fallback if PyQt6-WebEngine absent)

**Menu bar:**
- File → Exit
- Database → Check for Update / Select Database / Open DB Folder (all navigate to Setup via `tabs.indexOf(setup_tab)`)
- Help → Help / About

**Status bar:** Refreshes every 10 seconds with latest DB stats (most recent LB, checksum count, last import date).

**Settings persistence:** Window geometry saved/restored via `QSettings`.

**Tab index policy:** All `setCurrentIndex()` calls use `self.tabs.indexOf(self.whichever_tab)` rather than hardcoded integers so the order can change without breaking navigation.

---

## GUI: Lookup Tab (`gui/lookup_tab.py`)

The primary user-facing feature.

**Left panel:** File list (drag-and-drop). Buttons: Lookup Clipboard, Lookup Listbox, Add Files, Add Folders, Clear List, Generate Checksums. Toggle to filter `_mychecksums` files.

**Right panel — Summary table** (per-LB aggregate):
- Columns: LB Number, Source, Given, Matched, Not Found, Missing, Dups, Xrefs, Status

**Right panel — Detail table** (per-checksum):
- Columns: Checksum, Filename, Type, LB Number, Xref, Status, Source

**Color coding:**
| Color | Meaning |
|-------|---------|
| Green | MATCHED (complete set) |
| Orange | NOT FOUND |
| Pink/rose | MATCHED INCOMPLETE (missing files) |
| Yellow | DUPLICATE (in multiple LBs) |
| Light blue | XREF (cross-reference entry) |

**Checksum generation:** Posts to `POST /api/verify/generate` with the selected folder path(s). The backend (`backend/checksum_utils.py`) computes FFP (FLAC STREAM_INFO bytes 18–34) and MD5 hashes and writes `<foldername>_mychecksums.ffp` and `<foldername>_mychecksums.md5`, incrementing the suffix (`_mychecksums_2`, etc.) if files already exist. Generated file paths and any errors are shown in the status area below the file list.

**Double-click summary row:** Opens the LosslessBob detail page in the system browser.

**Signal to Rename tab:** After each lookup, emits results so the Rename tab can auto-populate folder rename proposals.

**Threading:** `_LookupWorker` (QThread) performs API calls without blocking the UI.

---

## GUI: Verify Tab (`gui/verify_tab.py`)

Verifies audio files against **locally-generated** checksum files (`.ffp`, `.md5`, `.st5`) — distinct from lbdir_tab which checks the official archive record.

**Left panel:** Folder list (drag-drop, dirs only). Buttons: Add Folders, Add Root Folder (recursive audio scan), Remove Selected, Clear List, Verify Folders, Generate Checksums, Retrieve from LB.

**Summary table** (one row per folder):
Columns: Folder | Mode | FFP | MD5 | Shntool | Total | Pass | Mismatch | Missing | Extra | Status

**Detail table** (one row per audio file in selected folder):
Columns: Filename | MD5 | FFP/Shntool | ST5 | On Disk | Overall
Default: problem rows only. Toggle: "Show all files" checkbox.

**Row colors:**
| Color | Meaning |
|-------|---------|
| Green | PASS |
| Red | FAIL (mismatch) |
| Orange | MISSING FILES (files not on disk) |
| Yellow | INCOMPLETE (missing checksum type) |

**Workers:**
- `_VerifyWorker` → `POST /api/verify`
- `_GenerateWorker` → `POST /api/verify/generate`, then auto-triggers verify
- `_RetrieveWorker` → `POST /api/lbdir/retrieve`, then auto-triggers verify

shntool missing → yellow row + status label install hint.

---

## GUI: lbdir Tab (`gui/lbdir_tab.py`)

Verifies the **official lbdir*.txt** file for each folder against actual files on disk. The lbdir file is the archive's authoritative checksum record scraped from losslessbob.com.

**Left panel:** Folder list (drag-drop, dirs only). Buttons: Add Folders, Add Root Folder, Remove Selected, Clear List, Check lbdir Files (all folders), Retrieve lbdir (selected or all → auto-triggers check).

**Summary table** (one row per folder):
Columns: Folder | LB# | lbdir File | Mode | Total | Pass | Mismatch | Missing | Status

**Row colors:**
| Color | Meaning |
|-------|---------|
| Green | PASS |
| Red | FAIL, MISSING FILES, SHNTOOL MISSING, PARSE ERROR |
| Yellow | NO LBDIR (lbdir absent but LB# known, retrievable) |
| Grey | NO LB# (cannot retrieve, entry unknown) |

**Double-click summary row:** Opens `http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html`.

**Detail table** (one row per file listed in lbdir):
Columns: Filename | MD5 Exp. | MD5 Act. | MD5 | FFP/Shn Exp. | FFP/Shn Act. | FFP/Shn | On Disk | Overall
Hash columns truncated to 12 chars with full hash in tooltip. Column-0 `UserRole` stores the original file index so the "Show all files" toggle correctly maps visible rows to file data.

**Info panel** (right of detail table): Displays shntool_len data for the selected detail row — Length, Expanded Size, CDR, WAVE Problems, Format, Ratio. Populated from `/api/lbdir/check` per-file fields; blank for non-audio files or when no shntool_len data is available.

**Retrieve lbdir button:** Uses selected listbox items if any, otherwise all folders. Status messages distinguish `copied` (local cache), `scraped_and_copied` (fresh scrape), `not_found`, and `no_lb_number` (folder not in My Collection).

**Workers:**
- `_LbdirCheckWorker` → `POST /api/lbdir/check`
- `_LbdirRetrieveWorker` → `POST /api/lbdir/retrieve`, then auto-triggers check

---

## GUI: Search Tab (`gui/search_tab.py`)

Search field + field selector (All / Location / Date / Description) + year dropdown. All matching entries are fetched from the API and paginated client-side. Columns: LB Number, Date, Location, Rating, Description, Owned.

**Pagination:** Prev/Next buttons and a "Page X of Y (N results)" label appear between the search bar and table whenever results exceed the configured page size. Page size defaults to 50 and is set in the Setup tab. `set_page_size(n)` resets to page 1 and re-renders.

**Client-side filters (checkboxes, all AND-combined):**
- **Missing only** — show only rows with `status == "missing"` (yellow highlighted)
- **Owned only** — show only rows whose LB number is in My Collection
- **Not owned** — show only rows NOT in My Collection
- Combining "Missing only" + "Owned" = missing entries that are owned; combining "Owned only" + "Not owned" = empty result (contradictory)

**Owned data** is fetched from `GET /api/collection/lb_numbers` after each search result arrives. If an owned filter is active when data loads, the page is re-rendered automatically.

**Double-click col 0:** Switches to Lookup tab. **Double-click any other column:** Opens `LB-{lb:05d}.html` on losslessbob.com (5-digit zero-padded).

**🎵 Bootleg badge:** LB Number cells show a `🎵 N` suffix when that LB has entries in `bootleg_titles`. The badge set is pushed from `BootlegsTab.bootleg_lbs_loaded` on startup and after each scrape.

---

## GUI: Bootlegs Tab (`gui/bootlegs_tab.py`)

Browse the LosslessBob Bootleg-CD catalog (LBBCD index page). Backed by `bootleg_titles` + `bootleg_scrapes` tables (MASTER data, ships in curator releases).

**Filter bar:** Free-text search (title + location, debounced 300 ms), year range (two spinboxes), CDs combobox (All / 0 / 1 / 2 / 3+), Status filter (public/private/missing), Owned filter (All/Owned/Not owned), LBBCD filter (All/Has link/No link), Clear button.

**Table columns:** LB Number, Title, Date, Year, Location, CDs, LBBCD (e.g. `LBBCD-275`), Status (lb_master colour), Owned (✓).

**Pagination:** Prev/Next with "Page X of Y · N results" label. Default page size 200.

**Detail pane (right):** Title, date, location, CD count, lb_master status, LBBCD identifier. Two buttons: "Open in Search Tab" (emits `open_lb_in_search` → MainWindow switches to Search and pre-fills the LB number); "Open LBBCD Page" (opens browser). "Other bootleg titles for this LB" sub-panel lists sibling rows.

**Signals:**
- `open_lb_in_search(int)` — connected by MainWindow to `_on_bootleg_open_lb`
- `bootleg_lbs_loaded(set)` — connected by MainWindow to `search_tab.set_bootleg_lbs`

**Double-click row:** Opens the LB detail page on losslessbob.com.

---

## GUI: Setup Tab (`gui/setup_tab.py`)

**Database section:** Stats display, Import Database File button, Check for Update, Open DB Folder, destructive Reset button.

**Search section:** "Results per page" spinner (range 10–500, step 10, default 50). Saved to meta as `search_page_size`. Emits `search_page_size_changed(int)` signal picked up by the Search tab.

**Scraper section:**
- Checkboxes: Auto-scrape after import, Download attachment files, Force re-scrape (ignore already-complete entries), **Use local pages for metadata (data/pages/)**
- Delay spinner (500–10000 ms, default 1500 ms)
- Scrape All / Stop buttons
- Single-entry scrape (enter one LB number)
- Range scrape (start, end, optional Fill Gaps mode)
- Progress bar + scrolling log (max 500 lines)

**Force re-scrape checkbox:** When checked, passes `force=True` to all three scrape modes (single, range, all), bypassing the skip-if-already-complete logic. Persisted in `meta` as `force_scrape`.

**Skip LB numbers with no checksum data:** For LB numbers in the range not present in the checksum DB, inserts a `status='missing'` placeholder entry (renamed from "Mark sequential gaps as MISSING").

**Scraper log:** Shows "Scraped LB-X [local]" / "Scraped LB-X [web]", "Skipped LB-X — already complete", or "Error scraping LB-X" per entry. Uses `last_lb` (the just-completed entry) paired with `last_source`/`last_action` from the status poll so the source tag always matches the logged LB number. Completion message includes skipped and error counts.

**Scraper log file:** Every log line is appended to `data/scraper.log`. The Scraper Log group shows the current file size, an "Open Log File" button, and a "Purge Log" button that truncates the file and clears the in-app widget.

**Background threads:**
- `_ImportThread` — calls `/api/db/import`
- `_ResetThread` — calls `/api/db/reset`
- `_SingleScrapeThread(flask_port, lb_number, force)` — calls `/api/entry/<lb>/scrape`
- `_ScrapeStatusThread` — polls `/api/scrape/status` every 1 second; updates progress bar and log

---

## GUI: Attachments Tab (`gui/attachments_tab.py`)

**Left panel:** Tree of entries that have locally cached files, with file count. Only entries with at least one downloaded file appear.

**Right panel (stacked widget):**
- Text viewer for `.txt`, `.ffp`, `.md5`, `.st5`
- Web viewer (PyQt6-WebEngine) for `.html`
- Generic panel with Open Externally button for other types

**Re-download button:** Forces a fresh scrape of the selected entry.

**Manual file placement:** Files dropped directly into `data/attachments/LB-XXXXX/` (matching the zero-padded naming convention) are displayed in the tree after clicking Refresh — no DB write required. The "Refresh / Re-download" button will overwrite manually placed files, so avoid using it on manually populated entries.

---

## GUI: Rename Tab (`gui/rename_tab.py`)

Populated automatically after each lookup. Shows folders from the input file list alongside proposed new names. Constructor takes `flask_port` (default 5174) for backend resolution calls.

**Row states and colors:**
| State | Color | Meaning |
|-------|-------|---------|
| `has_lb` / `renamed` | Green `#C8E6C9` | Correct LB already in name / just renamed |
| `needs_rename` | Orange `#FFE0B2` | Match found, rename to `{folder}-LB-{N}` |
| `wrong_lb` | Purple `#E1BEE7` | Folder has a *different* LB number — needs strip + rename |
| `multiple_ids` | Cyan `#B2EBF2` | Multiple LBs found, unresolved |
| `no_match` | Red `#FFCDD2` | No match |

**Disambiguation resolution order** (applied per folder during `populate_from_lookup`):
1. `folder_lb_link` lookup — if an exact path match exists in the DB, use that LB directly. LB Found cell shows `🔗 LB-XXXXX` prefix.
2. `lb_alias` collapse — call `GET /api/lb_alias/resolve`. If all candidates collapse to one canonical, use it automatically.
3. Fall back to `multiple_ids` state (cyan) for manual resolution.

**Right-click context menu (multiple_ids rows):**
- **Resolve — Apply…** submenu — pick a specific candidate LB to resolve the row (session-only, not persisted)
- **Link this folder to specific LB…** — prompts for an LB number, saves via `PUT /api/folder_link`, updates row to resolved state with `🔗` indicator
- **Save as master alias…** *(curator-only)* — opens `_AliasDialog` to create a `lb_alias` mapping; re-runs resolution for the row after save

**Right-click context menu (linked rows, indicated by `🔗`):**
- **Unlink this folder** — calls `DELETE /api/folder_link`, resets row to non-linked state

**Wrong-LB workflow:** When a folder already contains an LB number that doesn't match the correct one, the row shows "Wrong LB in name" (purple). Use **Select Wrong LB** to batch-select all such rows, then **Strip Wrong LB from Selected** to rewrite proposed names from `OldFolder-LB-old-LB-new` → `OldFolder-LB-new`. Then click **Rename Selected** to apply.

**Select All** checks only actionable rows (`needs_rename` + `wrong_lb`); green/red rows are left unchecked.

**Execute:** Rename Selected → moves folders into a `0. Processed/` subdirectory alongside the source.

---

## GUI: DB Editor Tab (`gui/dbedit_tab.py`)

Paginated browse, inline-edit, and delete for every SQLite table. Left sidebar has a table list (with row counts), a **DB Integrity** panel, and an **LB Aliases** panel.

**DB Integrity sub-panel:**
- Live stats label: Public / Private / Missing / Max LB / Overrides / Needs review counts (from `GET /api/lb_master/stats`).
- **Reconcile All** — recomputes lb_master status for every LB. Backs up DB first.
- **Show Needs Review** — filters the lb_master table to rows with `needs_review=1`.
- **Export Overrides** — calls `GET /api/lb_master/overrides/export`, saves JSON file.
- **Import Overrides** — loads a JSON file, calls `POST /api/lb_master/overrides/import`. Curator-gated.
- **Backup DB Now** — manual snapshot (`POST /api/db/backup`).

**LB Aliases panel:**
- `QTableWidget` with columns: Alias LB | → | Canonical LB | Relationship | Note
- Auto-loaded on `load_tables()`. Add/Delete buttons curator-only. Non-curators read-only.

**Right panel:** Editable data table. Supports: Load Records, per-LB filter, column search, pagination, sort (header click), inline cell edit, Save Changes, Delete Selected, Export CSV.

---

## GUI: Theme Tab (`gui/theme_tab.py`)

Fourteen preset themes (Light, Dark, Black, Dracula, Blue, Purple, Red, Nord, Gruvbox, Monokai, Tokyo Night, Solarized, Everforest, Catppuccin) plus custom color picker. Color changes apply immediately via `styles.py` which generates Qt QSS from a color dictionary. Theme name and per-color overrides persist in `QSettings`.

---

## Key Data Flows

### Lookup
```
User pastes text / drops files
  → POST /api/lookup {text}
    → parse_checksum_text() — regex extraction
    → lookup_checksums() — SQLite query per checksum
    → aggregate per LB number
  ← {summary[], detail[]}
  → Color-code tables
  → Signal → Rename tab auto-populates
```

### Import
```
User clicks Import / file dropped in data/
  → POST /api/db/import {file_path}
    → MD5 hash file; skip if matches stored import_hash
    → parse tab-delimited rows
    → INSERT OR IGNORE into checksums
    → store import_hash in meta
  → If auto_scrape: scrape new LB numbers
```

### Scrape
```
User clicks Scrape All / Range / Single
  → POST /api/scrape/start {lb_numbers, force, use_local_pages}
    → Background thread: for each LB:
        if use_local_pages and data/pages/LB-N.html exists:
            read HTML from disk (no network)
        else:
            GET /detail/LB-{N:05d}.html
            save HTML → data/pages/LB-{N:05d}.html
        Parse HTML → entries table
        Download missing files → data/attachments/LB-{N:05d}/
        Sleep delay_ms only if source was web
  ← GET /api/scrape/status every 1s
  → Progress bar + log update ([local] / [web] label per entry)
```

---

## Checksum Format Reference

```
# FFP (FLAC Fingerprint)
filename.flac:8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3

# MD5 (with or without asterisk)
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3 *filename.flac
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3  filename.flac

# ST5 / SHA1 (40-hex)
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3c3c3c3c3 *filename.shn
```

---

## GUI Conventions

- **Table column resizing:** All `QTableView` instances use `QHeaderView.ResizeMode.Interactive` for the horizontal header so the user can drag column borders freely. After data loads, call `view.resizeColumnsToContents()` once to set sensible initial widths. Never use `ResizeToContents` or `Stretch` as the persistent resize mode.

- **Qt style base:** `QApplication.setStyle("Fusion")` is set in `main.py` before any QSS is applied. Fusion renders consistently cross-platform and is required for QSS overrides (especially rounded corners and flat buttons) to work correctly.

- **Stylesheet generation:** All QSS is generated in `gui/styles.py` → `build_stylesheet(theme_dict)`. The stylesheet is applied to the main window and regenerated whenever the user changes themes. Key QSS rules:
  - `QPushButton`: `border-radius 6px`, `padding 5px 14px`; accent-colored background with hover/pressed/disabled states; no 3D border.
  - `QLineEdit`, `QComboBox`, `QSpinBox`: `border-radius 4px`, `padding 2px 6px`.
  - `QTabBar::tab`: `border: none`, `border-radius 4px 4px 0 0`; selected tab gets a `border-bottom: 2px solid accent` underline indicator instead of a raised appearance.
  - `QGroupBox`: `border-radius 6px`, `margin-top 1.5em`, `padding-top 6px`; title via `subcontrol-position: top left`.
  - `QProgressBar`: `border: none`, 6 px fixed height, `border-radius 3px`; chunk also rounded. No text overlay.
  - `font-weight`: always 700 — never 500 (inconsistent cross-platform).

- **Drop shadows:** `styles.apply_panel_shadow(widget)` attaches a `QGraphicsDropShadowEffect` (blurRadius 12, offset 0,2, color rgba 0,0,0,60) to a widget. Applied in `main_window.py → _apply_shadows()` to the 1–2 main result panels per tab:
  - Lookup: `summary_container`, `detail_container`
  - Rename: `view`
  - Verify: `summary_container`, `detail_container`
  - lbdir: `summary_container`, `detail_container`
  - Search: `view`
  - Collection: `coll_view`, `miss_view`
  Do **not** apply globally or to the window frame.

- **QTableWidget vs QTableView:** The Lookup and Rename tabs use `QTableView` + custom `QAbstractTableModel`. The Verify and lbdir tabs use `QTableWidget` (no model class) since their data is repopulated wholesale on each run and per-cell color/tooltip control is simpler with `QTableWidgetItem`. Both use `QHeaderView.ResizeMode.Interactive` and `resizeColumnsToContents()` after load.

- **Worker pattern:** All background operations use `QThread` subclasses with `finished(dict)` and `error(str)` signals, matching `_LookupWorker`. Workers that auto-chain (generate→verify, retrieve→check) call the next `_start_*` method from the `finished` handler in the main thread.

- **Folder index in detail tables:** When the Verify or lbdir detail table filters rows (show-problems-only mode), column-0 of each visible row stores the original index into the full file list via `item.setData(Qt.ItemDataRole.UserRole, file_idx)`. This allows the info panel click handler to correctly retrieve shntool_len data regardless of which rows are hidden.

---

## Notable Implementation Details

- **LB number URL padding:** LosslessBob URLs use 5-digit zero-padded numbers (`LB-00042`). The scraper and directory names use `f"{lb_number:05d}"` formatting.
- **Checksum generation (FFP):** Reads raw FLAC file bytes 18–34 from the `STREAM_INFO` metadata block, which is the MD5 signature of the decoded audio stream — not a hash of the file itself.
- **Local API port:** Flask runs on port 5174. If this conflicts with another service, it is hardcoded in `backend/app.py` and `gui/` tabs that construct the base URL.
- **File access restriction:** `.claude/settings.json` restricts Claude Code to read/write only within this project directory and `~/.claude/` (memory). Bash commands are not path-restricted.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-05-19 | Mobile-friendly admin panel: `backend/admin.html` + 3 routes (`GET /admin`, `GET /api/admin/status`, `POST /api/admin/restart`). Dark theme, no external deps, auto-polls every 5 s, DB stats/backup/reset, flat-file update, scraper start/stop, LB master reconcile, server restart. (TODO-042) |
| 2026-05-18 | Disambiguation: `lb_alias` (MASTER) and `folder_lb_link` (USER) tables; 7 new endpoints under `/api/lb_alias` + `/api/folder_link`; Rename tab resolution order + 🔗 indicator + Link/Unlink/Alias context menu; DB Editor LB Aliases panel (curator-gated). (CC_LB_INTEGRITY item 8, TODO-019) |
| 2026-05-18 | Flat-file update check rework: new `backend/flat_file.py` pipeline (discover/download/diff/apply); `flat_file_releases` + `flat_file_changelog` tables in MASTER_TABLES; 7 new `/api/flat_file/*` endpoints; removed broken `check_for_update()` from scraper.py; Setup tab "Check for Flat File Update" button + `_UpdateAvailableDialog` + Flat File History panel. (CC_LB_INTEGRITY item 9, TODO-026) |
| 2026-05-18 | Click-to-sort on all major tables: `gui/widgets/sort_keys.py` (SortableTableItem + sort_key_for); lbdir/verify QTableWidget client-side sort; search/collection/dbedit server-side sort via sectionClicked; backend /api/search, /api/collection, /api/collection/missing accept sort_col/sort_dir. (CC_LB_INTEGRITY item 10, TODO-025) |
| 2026-05-18 | Override export/import JSON: `export_overrides()` + `import_overrides()` in db.py; `GET /api/lb_master/overrides/export` + `POST /api/lb_master/overrides/import`; DB Editor Export/Import Overrides buttons in Integrity panel. (TODO-024) |
| 2026-05-19 | Map tab added: `gui/map_tab.py` (QWebEngineView + Open-in-Browser fallback), `gui/resources/map.html` (Leaflet 1.9.4, markercluster, leaflet.heat, filter bar, stats bar). |
| 2026-05-17 | Standardize folder name: `build_standard_name()` in `backend/folder_naming.py`; `GET /api/folder_naming/standard/<lb>`; "Standardize Selected" button + right-click action in Rename tab; `RenameModel.update_state()`; fixed BUG-064 (_on_strip_wrong_lb now transitions state to needs_rename). (CC_LB_INTEGRITY item 13) |
| 2026-05-17 | lb_status filter + tinting across Lookup (filter combobox + row tint), Attachments tree (page-level batch tint), Rename LB Found column, Lbdir LB# column. `get_lb_statuses_batch()` in db.py. (TODO-021) |
| 2026-05-17 | -NFT suffix for Private LB folder names: new `backend/folder_naming.py` module; `should_mark_nft()` + `lb_status` annotation in `lookup_checksums()` in `db.py`; Rename tab applies NFT suffix to proposed names and shows discrepancy colours; Collection tab `_get_standard_lb_name()` calls `/api/lb_master/<lb>/nft`. (TODO-018) |
| 2026-05-17 | Re-scrape Private LBs button in Setup tab (Row 3 of Scraper grid): `POST /api/scrape/private_rescrape` + GUI handler with confirmation dialog, progress tracking, and promotion count in completion message. (TODO-017) |
| 2026-05-17 | Master/user data ownership split: `MASTER_TABLES`/`USER_TABLES`/`MASTER_META_KEYS`/`MASTER_SCHEMA_VERSION` constants in `backend/db.py`. New `export_master_db()` and `import_master_db()` with SHA256 manifest and schema-version guard. Curator mode (`meta.is_curator`) gates publish UI. Endpoints `GET/POST /api/curator`, `POST /api/master/export`, `POST /api/master/import`. Setup tab "Master Data" group adds Curator-mode checkbox + Publish/Install Master Update buttons. 13 tests in `tests/test_master_data.py`. (TODO-020) |
| 2026-05-06 | Fixed scraper URL/directory formatting: LB numbers now zero-padded to 5 digits (`LB-{n:05d}`) in `backend/scraper.py` |
| 2026-05-06 | Added `.claude/settings.json` — restricts file access to project directory + deny rules for sensitive system paths |
| 2026-05-06 | Created this document |
| 2026-05-06 | Removed SDF/Wine/ExportSqlCE40 import path; flat-file only. Renamed `sdf_hash` meta key to `import_hash`. Deleted `tools/` directory. |
| 2026-05-06 | QSS modernization: Fusion base style, rounded corners, flat buttons, tab underline indicator, slim progress bar, `font-weight 700`, drop shadows on result panels. |
| 2026-05-06 | Rename tab: added `wrong_lb` state (purple) for folders with mismatched LB numbers; "Select Wrong LB" and "Strip Wrong LB from Selected" buttons; "Select All" now only checks actionable rows. |
| 2026-05-06 | Scraper: skip logic no longer fires delay for already-complete entries; `_scrape_state` gains `skipped` count and `last_action`; log distinguishes scraped vs skipped. |
| 2026-05-06 | Setup tab: added "Force re-scrape" checkbox applied to all three scrape modes; `_SingleScrapeThread` accepts `force` parameter. |
| 2026-05-06 | Added `backend/checksum_utils.py`: FFP/MD5/shntool compute, lbdir parsing, `verify_folder`, `verify_folder_lbdir`, `generate_checksums`, `_lbgen_path`. |
| 2026-05-06 | Added four new API routes: `POST /api/verify`, `POST /api/verify/generate`, `POST /api/lbdir/check`, `POST /api/lbdir/retrieve`. |
| 2026-05-06 | Lookup tab: checksum generation now calls `POST /api/verify/generate` instead of doing file I/O in the GUI worker; output uses `_lbgen` naming convention. |
| 2026-05-07 | Added `gui/verify_tab.py`: folder-level verification against local checksum files; three workers (verify, generate, retrieve); summary + detail tables with color coding. |
| 2026-05-07 | Added `gui/lbdir_tab.py`: verification against official lbdir*.txt archive records; detail table with truncated hash columns + tooltip; info panel for shntool_len data; double-click opens LB detail page. |
| 2026-05-07 | `checksum_utils.verify_folder_lbdir` now passes all six shntool_len fields per file (`length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio`). |
| 2026-05-07 | Tab order updated: Lookup(0) Rename(1) Verify(2) lbdir(3) Search(4) Collection(5) Attachments(6) Setup(7) Themes(8). All `setCurrentIndex` calls replaced with `indexOf()` for future-proofing. |
| 2026-05-07 | lbdir_tab, verify_tab: "Show all files" checkbox now checked by default. |
| 2026-05-07 | scraper.py: Fixed three skip/download bugs (see BUGS.md BUG-001–003). |
| 2026-05-07 | scraper.py, app.py, setup_tab.py: Added `use_local_pages` feature — metadata scraped from `data/pages/LB-XXXXX.html` when available; web scrapes cache HTML to `data/pages/` for reuse; delay suppressed for local reads; `last_source` field in scrape state. |
| 2026-05-07 | data/pages/: New directory for cached detail page HTML files. |
| 2026-05-07 | Search tab: client-side pagination with Prev/Next buttons; Setup tab: "Results per page" spinner (10–500); db.py search_entries limit removed; search_page_size meta key added. |
| 2026-05-07 | Scraper log now persisted to data/scraper.log; log management UI (size, Open, Purge) added; [web]/[local] label bug fixed via last_lb state field; error entries now logged explicitly. |
| 2026-05-07 | Search tab: added Missing only / Owned only / Not owned client-side filter checkboxes (AND-combinable); fixed double-click URL to zero-pad LB number to 5 digits. Setup tab: renamed "Mark sequential gaps as MISSING" → "Skip LB numbers with no checksum data"; Scrape All/Scrape/Scrape Range buttons moved to same grid column so they render at equal width. My Collection tab: auto-loads on startup; client-side pagination (shares Results per page from Setup tab); year dropdown filter. |
| 2026-05-12 | DB-01/02: WAL mode + performance PRAGMAs; persistent per-thread connection pool in db.py. |
| 2026-05-12 | DB-03: idx_chk_covering and idx_lb_xref0 partial index added to checksums. |
| 2026-05-12 | DB-04: lookup_checksums uses temp table JOIN instead of IN clause. |
| 2026-05-12 | DB-05: entries_fts FTS5 virtual table + triggers; search_entries uses FTS MATCH with LIKE fallback. |
| 2026-05-12 | DB-06: PRAGMA optimize called after import (importer.py) and after scrape_range (scraper.py). |
| 2026-05-12 | DB-07: ScalableBloomFilter pre-filters definite-miss checksums; pybloom-live==4.0.0 added. |
| 2026-05-12 | DB-08: entry_changes table + record_entry_changes(); GET /api/entry/lb/changes endpoint; db_reset drops FTS and entry_changes. |
| 2026-05-12 | Import progress: async import with stage/row-count state; GET /api/db/import/status; import progress bar in Setup tab. |
| 2026-05-12 | Added backend/sox_utils.py: SoX/ffmpeg detection, generate_spectrogram(), spectrogram batch worker. Five /api/spectrogram/* routes. |
| 2026-05-12 | Added gui/spectrogram_tab.py: two-pane spectrogram viewer tab. Registered as tab 7 (Spectrograms). |
| 2026-05-12 | gui/setup_tab.py: SoX availability indicator with Re-check button added to Database group. |
| 2026-05-13 | FEAT-13: integrity_events schema added; purge_* / delete_collection_entries in db.py; POST /api/collection/purge and /delete_bulk; Select All/None + bulk _on_remove in collection_tab; Data Management group in setup_tab. |
| 2026-05-13 | FEAT-14: _DBEDIT constants and 6 /api/dbedit/* routes in app.py; gui/dbedit_tab.py (DbEditTab) created; registered as DB Editor tab (index 8) in main_window.py. Tab count: 11. |
| 2026-05-13 | Added backend/startup_log.py; instrumented main.py, backend/app.py, gui/main_window.py with startup timing probes → data/startup.log. |
| 2026-05-13 | Lookup: duplicate resolution prefers MATCHED over INCOMPLETE; folder/summary click filtering; verify NO CHECKSUMS yellow status; lookup→verify folder carry. |
| 2026-05-14 | Rename: Multiple IDs cyan color + right-click resolve; xref-aware naming (LB-N-xrefXXXX); _fmt_lb helper; populate_from_lookup filters to MATCHED status only. |
| 2026-05-14 | Added GET /api/checksums/xref_lb_numbers; db.get_xref_lb_numbers(); "Xref only" filter on Search and Collection tabs. |
| 2026-05-14 | Phase 1: Added torrents + rename_history tables; backend/credentials.py, rename.py, torrent_maker.py, qbittorrent.py, forum_poster.py; 7 new API routes; qBt/WTRF/Torrent sections in Setup tab; Create Torrent/Add to qBt/Post to Forum in My Collection; write_rename_log() wired to Rename tab; torf==4.3.1 + keyring==25.7.0 added. |
| 2026-05-14 | Added POST /api/wtrf/test and "Test Connection" button to WTRF Forum group in Setup tab. |
| 2026-05-14 | Forum preview: GET /api/entry/lb/preview_forum; preview_lb_topic() in forum_poster.py; preview dialog with editable subject+body before posting. |
| 2026-05-14 | TODO-012/013: Torrent history sub-panel in My Collection — lists all torrents records per selected entry with green/red/orange status indicator, per-row context menu, Add to qBittorrent / Regenerate / Relocate Source buttons; path relocation flow with file cross-check, rename_log.txt logging, and optional rename to standard format. |
| 2026-05-15 | lbdir Reconcile Files: find_reconcilable_files() in checksum_utils.py; POST /api/lbdir/reconcile + /apply_reconcile; ReconcilePreviewDialog + "Reconcile Files" button in lbdir_tab.py; _find_lbdir_in_folder() DRY refactor in app.py. |
| 2026-05-16 | Added 7 new preset themes to theme_tab.py: Nord, Gruvbox, Monokai, Tokyo Night, Solarized, Everforest, Catppuccin (14 total). |
| 2026-05-16 | Added "Forum History" and "Torrent History" inner tabs to My Collection — global all-entry views backed by GET /api/forum_posts and GET /api/torrents; db.get_all_forum_posts() and db.get_all_torrents() added. |
| 2026-05-16 | Search tab: added "Xref" column (col 5) showing xref numbers per entry; GET /api/checksums/xref_map added. Collection "Xref only" filter now matches folder_name containing "xref" instead of checking the master DB xref list. |
| 2026-05-17 | CC_LB_INTEGRITY item 11: GuiStateStore in gui/widgets/state_store.py; all tabs migrated from QSettings/hardcoded widths to attach_table / data/gui_state.json; window geometry migrated too. |
| 2026-05-18 | Override export/import JSON: export_overrides() + import_overrides() in db.py; GET /api/lb_master/overrides/export + POST /api/lb_master/overrides/import in app.py; "Export Overrides" + "Import Overrides" buttons in DB Integrity panel (dbedit_tab.py). |
| 2026-05-18 | CC_LB_INTEGRITY item 10: Click-to-sort on all major tables. gui/widgets/sort_keys.py added. lbdir+verify QTableWidget tables use SortableTableItem. Search/Collection/Missing QTableView tables sort in-memory via sectionClicked. DB Editor sectionClicked wired to server-side sort. Backend /api/search, /api/collection, /api/collection/missing accept sort_col/sort_dir. |
| 2026-05-18 | Download Missing Pages: `download_pages_range()` in scraper.py; `POST /api/scrape/download_pages`; Row 4 "Download Missing Pages" button in Setup tab scraper grid. (TODO-002) |
| 2026-05-18 | Bootleg-CD Catalog (LBBCD): `backend/bootleg_scraper.py`; `bootleg_titles` + `bootleg_scrapes` tables (MASTER); MASTER_SCHEMA_VERSION→2; 7 `/api/bootlegs/*` routes; `gui/bootlegs_tab.py` (Bootlegs tab, index 5); 🎵 badge in Search tab; Scrape Bootleg Catalog button + history panel in Setup tab; Bootlegs count in status bar. (TODO-030) |
| 2026-05-19 | Map feature: location_geocoded table (MASTER) + get_map_data(); backend/geocoder.py (Nominatim); tools/geocode_locations.py CLI; GET /map + /api/map/data + /api/geocode/* routes; gui/map_tab.py + gui/resources/map.html (Leaflet); curator geocoding UI in setup_tab + dbedit_tab; Map tab wired into main_window.py. |
| 2026-05-19 | Map feature complete (CC_MAP_FEATURE.md): bundled Leaflet assets in gui/resources/leaflet/ (served via GET /leaflet/<filename>); QWebChannel bridge (_MapBridge) in map_tab.py for "Open in Search" popup button + "List in Search" viewport filter; _LbListWorker + SearchTab.load_lb_list() in search_tab.py; get_entries_by_lb_list() in db.py; GET /api/entries/by_lb_list in app.py. |
| 2026-05-19 | i18n infrastructure (TODO-067): gui/i18n.py (load_language, supported_languages); gui/locales/ directory for .ts/.qm files; ui_language meta key; Preferences group in Setup tab; startup language load in main.py; "ui_language" added to GET /api/db/settings. |
| 2026-05-20 | Audio filename reconcile: db_filename added to lookup_checksums() detail dicts; POST /api/checksums/reconcile_audio + apply_reconcile_audio routes; gui/widgets/reconcile_dialog.py (AudioReconcileDialog); "Reconcile Audio Files" button on Lookup tab (auto-enabled on filename mismatch) and Rename tab (_ReconcileAudioWorker scans checksum files in checked folders). |
| 2026-05-20 | Map tab rework (TODO-074): map_tab.py rewritten as browser-only (no QWebEngineView); Open Map in Browser button + Map Filters group (year, lb_status, owned, text); Geocoding group + Location Overrides group moved from setup_tab/dbedit_tab; curator_mode_changed signal added to SetupTab; Tech Stack updated (WebEngine for attachments only). |
