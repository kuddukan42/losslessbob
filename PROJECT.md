# LosslessBob Checksum Lookup — Project Overview

**Purpose:** Cross-platform desktop replacement for the original Windows-only `Checksum_Lookup` utility used by collectors of Bob Dylan lossless recordings from the [LosslessBob archive](http://www.losslessbob.wonderingwhattochoose.com). Users paste or load checksum files (FFP, MD5, ST5/SHA1) and the app matches them against the archive database to identify which LosslessBob entry (LB number) a recording belongs to, and whether the set is complete or has missing/duplicate files.

---

## Contents

Grep for the exact `## ` header to jump to a section:
Tech Stack · File Structure · Database Schema ·
Backend: Flask API / Database Layer / Geocoder / Checksum Utilities / Importer /
Scraper / Scheduler / Site Crawler ·
GUI (legacy tabs): Scraper / Main Window / Lookup / Verify / lbdir / Search /
Bootlegs / Setup / Attachments / Rename / DB Editor / Theme ·
GUI (Next): Electron/React Frontend ·
Key Data Flows · Checksum Format Reference · GUI Conventions ·
Notable Implementation Details · Change Log

---

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| GUI (primary) | Electron + React + TypeScript | electron-vite |
| GUI (legacy) | PyQt6 | 6.7.1 — **frozen**, no new features |
| Web view (attachments) | PyQt6-WebEngine | 6.7.0 — used by legacy GUI only |
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
| Audio I/O | soundfile | 0.13.1 |
| Signal processing | scipy | 1.17.1 |
| Language | Python | 3.11+ |

**Architecture pattern:** The GUI and backend are separated by a local Flask REST API (port 5174). The GUI makes HTTP requests to `localhost:5174` for all data operations. `gui_next` (Electron/React) is the active development target; Flask is launched as a child process from the Electron main process. The legacy `gui/` (PyQt6) starts Flask in a daemon thread and is frozen at its current state — no new features will be added there.

**GUI strategy (as of 2026-05-29):** All new screens, features, and bug fixes target `gui_next`. The PyQt6 GUI (`gui/`) is locked in place as a fallback reference; it receives no further changes.

---

## File Structure

```
losslessbob/
├── main.py                   # Legacy entrypoint: starts Flask thread, then PyQt6 app (frozen)
├── cli.py                    # Headless CLI: lookup / search / stats / import / serve
├── run_backend.py            # Headless entrypoint: Flask only, no GUI (phone/LAN use)
├── requirements.txt
├── PROJECT.md                # This file
├── backend/
│   ├── app.py                # Flask REST API — all routes
│   ├── admin.html            # Mobile-friendly admin control panel (served at /admin)
│   ├── db.py                 # SQLite layer, checksum parsing, search
│   ├── db_queue.py           # DB-09: DatabaseWriteQueue — single writer thread, serialises all writes
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
│   ├── olof_fetcher.py       # Olof Björner (bobserve.com) page mirror → data/olof/pages/ (TODO-162 P1)
│   ├── olof_parser.py        # DSN event+song parser: olof_pages → olof_events + olof_songs (TODO-162 P2–P3)
│   ├── olof_chronicle_parser.py  # Yearly Chronicles parser: calendar + new-tapes (+2022+ appendix, dormant) (TODO-162 P4)
│   ├── scheduler.py          # Watchdog file watcher, auto-import, scheduled integrity scans
│   ├── integrity_monitor.py  # TODO-111: lbdir-based collection integrity scan engine
│   ├── sox_utils.py          # SoX/ffmpeg tool detection + spectrogram generation
│   ├── startup_log.py        # Startup timing logger → data/logs/startup.log
│   ├── taper_attribution.py  # Taper attribution engine: evidence harvest → confirmed/propagated/inferred designations
│   ├── song_index.py         # Song-centric index: song_canonical seeding + song_performances recompute (TODO-230)
│   ├── setlist_fingerprint.py # Setlist fingerprinting: score entries.setlist vs olof_songs, curator suggestion queue (TODO-225)
│   ├── torrent_maker.py      # torf-based .torrent generation; tracker CDN fetch
│   ├── qbittorrent.py        # qBittorrent WebUI API v2 integration
│   ├── forum_poster.py       # SMF 2.x WTRF forum topic posting
│   └── geocoder.py           # Nominatim geocoder: geocode_one, place_manual, run_batch, get_progress
├── concert_ranker/           # Audio quality scoring + ranking (TODO-183). Run: python -m concert_ranker.cli
│   ├── config.py             # All thresholds/weights/bands (# CALIBRATE markers), externalized
│   ├── features.py           # DSP feature extractors: clarity/crowd/tonal/distortion/spatial/hf_native
│   ├── scoring.py            # Banding, hard disqualifiers, MAD-z sibling normalization, fusion, explain
│   ├── calibrate.py          # Calibration harness: score_separation/fit_thresholds/validate_labels
│   ├── scan.py               # Per-folder decode→extract→aggregate (one decode/STFT per track)
│   ├── runner.py             # Process-pool driver + producer/consumer staging loop (crash=scrap)
│   ├── families.py           # Rank within recording_families; standalone fallback (absolute bands)
│   ├── picks.py              # Per-date "best of show" pick scoring → show_picks (FABLE_UNIFIED_RANKING §3/§4)
│   ├── calibration.py        # Orchestration: stratified rating×source_class sample → scan → fit
│   ├── cli.py                # scan / calibrate / rerank / report subcommands
│   ├── audio/
│   │   ├── cache.py          # TrackCache + NativeProbe — the one-decode/one-STFT shared cache
│   │   └── io.py             # ffmpeg decode (bulk 22.05k + 8×20s native 44.1k windows)
│   └── lb/                   # LosslessBob DB bridge
│       ├── repo.py           # USER-table persistence (quality_scans / *_metrics / *_scores)
│       ├── source_type.py    # SBD/AUD/FM/UNKNOWN derivation (reuses backend.db classifier)
│       └── commentary.py     # Mine entries.description → calibrate.LABEL_KEYWORDS (validation oracle)
├── gui/                      # FROZEN — PyQt6 legacy GUI; no new features or bug fixes
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
├── conftest.py               # pytest: autouse fixture resets DatabaseWriteQueue singleton + thread-local connections between tests
├── tests/
│   ├── test_lb_master.py     # lb_master schema, reconcile, override, forum guard, GUI presence
│   ├── test_master_data.py   # MASTER/USER table classification, export/import, SHA + schema-version guards
│   ├── test_scraper_crawler.py # scrape_sessions + site_inventory table write functions
│   ├── test_scraper.py       # backend/scraper.py: entry metadata parsing, scrape_entry/scrape_range, download_pages_range
│   ├── test_bootleg_scraper.py # backend/bootleg_scraper.py: date/row parsing, diff/apply, scrape_bootlegs (mocked HTTP)
│   ├── test_bobdylan_scraper.py # backend/bobdylan_scraper.py: sitemap + show-page parsing, run_discover/run_scrape/run_update (mocked HTTP)
│   ├── test_setlistfm.py     # backend/setlistfm.py: date/setlist parsing, API key storage, run_update pagination (mocked HTTP)
│   ├── test_geocoder.py      # backend/geocoder.py: date conversion, performances/bobdylan_shows/olof_events/setlistfm_shows lookup + priority, concert eligibility, geocode_one/run_batch (mocked urllib)
│   ├── test_checksum_utils_site_recovery.py # find_site_recoverable_files: MD5 + filename-fallback matching against data/site/files/
│   └── test_db_writes.py     # 114-test battery: all DB write functions, constraint violations, rollback, thread safety
├── losslessbob_backend.spec  # PyInstaller onefile spec: backend-only (no PyQt6); bundled inside Electron AppImage
├── losslessbob_linux.spec    # LEGACY — old PyInstaller full-app spec (PyQt6 GUI); superseded by losslessbob_backend.spec + electron-builder
├── Dockerfile                # Docker image: python:3.11-slim + Xvfb + x11vnc + noVNC + Qt6 runtime
├── docker-compose.yml        # Compose: port 6080 (noVNC), named data volume, music-folder mount examples
├── .dockerignore             # Excludes .git, .venv, data/, dist/ from build context
├── docker/
│   └── entrypoint.sh         # Container startup: Xvfb → x11vnc → websockify/noVNC → app
├── secrets/                  # Docker secret files (git-ignored *.txt; safe *.example templates)
│   ├── qbt_username.txt      # qBittorrent username (empty = unused)
│   ├── qbt_password.txt      # qBittorrent password
│   ├── qbt_apikey_user.txt   # qBittorrent API key label
│   ├── qbt_apikey.txt        # qBittorrent API key value
│   ├── wtrf_username.txt     # WTRF forum username
│   └── wtrf_password.txt     # WTRF forum password
├── tools/
│   ├── ledger.py              # CLI: BUG/TODO ledger ops (next-id, bug-open/close, todo-open/close, --dry-run); used by /session-close
│   ├── geocode_locations.py  # CLI: batch-geocode entries.location via Nominatim (--limit, --retry-failed, --dry-run)
│   ├── import_curated_lists.py # CLI: import curator "best of" picks (TODO-181) — carbonbit's FLglist.xlsx + 10haaf's dylan_boots.zip/years.zip → curated_lists/curated_list_entries
│   ├── attribute_tapers.py   # CLI wrapper: backend.taper_attribution recompute → taper_attributions (--dry-run)
│   ├── compute_show_picks.py # CLI wrapper: concert_ranker.picks recompute → show_picks (--dry-run)
│   ├── compute_song_performances.py # CLI wrapper: backend.song_index recompute → song_performances (--dry-run)
│   ├── losslessbob.iss       # Inno Setup 6 script — builds LosslessBob_Setup_<ver>.exe from dist/LosslessBob/
│   ├── build_windows.bat     # Local helper: pyinstaller + iscc in sequence (Windows only)
│   ├── shntool.exe           # Windows shntool binary (GPL-2); bundled into PyInstaller dist via losslessbob.spec
│   ├── flac.exe              # Windows flac 1.5.0 Win64 binary (GPL-2); bundled via losslessbob.spec (TODO-146)
│   └── libFLAC.dll           # Required by tools/flac.exe (LGPL-2.1); bundled alongside it
├── docs/
│   ├── index.html            # GitHub Pages marketing/landing page
│   ├── CLI.md                # CLI usage reference
│   ├── scraping.md           # Scraper behaviour and queue logic
│   ├── data_ownership.md     # Master vs. user data split, export/import enforcement
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
| taper_name | TEXT | Parsed taper handle/name (via `extract_taper_and_source`) |
| source_chain | TEXT | Parsed recording equipment chain (via `extract_taper_and_source`) |
| lb_category | TEXT | Entry category: `'concert'`, `'interview'`, `'studio'`, `'compilation'`, `'tv'`, `'radio'`, `'rehearsal'`, `'soundcheck'`, `'other'`, `'unknown'`. Populated via `classify_entry_categories()`. |
| source_type | TEXT | Curator-edited source type: `'Soundboard'`, `'Audience'`, `'FM/Pre-FM'`, `'Master'`, `'Mixed'` (SBD/AUD/FM/MST/MTX badge in the Library screen). NULL until a curator sets it — never heuristically parsed or backfilled. |

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

### `integrity_events` — Watchdog file-change / integrity-scan alert log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | Owning collection entry |
| disk_path | TEXT | Path being watched |
| event_type | TEXT | `'missing'` (watcher); `'content_changed'`, `'tags_changed'`, `'files_missing'`, `'restored'` (TODO-111 integrity scan) |
| detail | TEXT | Human-readable description |
| occurred_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| acknowledged | INTEGER | 0 = unread, 1 = dismissed |
| mount_id | INTEGER | TODO-111: FK → `collection_mounts(id)`, set by integrity scans (NULL for watcher events) |

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
| renamed_at | TIMESTAMP | Set explicitly to local time by `add_rename_history()` |
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

### `lb_missing` — Confirmed non-existent LB entries (MASTER table)
Permanently records LB numbers that are allocated but never had (or permanently lost) a page on the LosslessBob site. Seeded with 36 known entries on first run. Entries in this table receive `lb_status='nonexistent'` in `lb_master` and are never scraped.
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LB number confirmed to not exist |
| confirmed_date | TEXT | ISO date when confirmed |
| notes | TEXT | Free-text note |

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

### `pipeline_file_hash` — Pipeline per-file hash cache (USER table, TODO-205 P1)
| Column | Type | Notes |
|--------|------|-------|
| folder_path | TEXT PK part | Absolute folder path, forward-slash normalised |
| rel_path | TEXT PK part | Posix-style path relative to folder_path |
| size | INTEGER NOT NULL | os.stat st_size — validation column, not key |
| mtime | REAL NOT NULL | os.stat st_mtime — validation column, not key |
| md5 | TEXT | Full-file md5 hex (audio subset only; NULL otherwise) |
| ffp | TEXT | FLAC fingerprint hex (FLAC only; NULL otherwise) |
| sha256 | TEXT | Full-file sha256 hex — feeds filing's tree digest (every file) |
| hashed_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

A read is a hit only when stored `(size, mtime)` match a fresh `os.stat` (rule R1).
Paths containing lone surrogates are never cached (SQLite TEXT can't bind them) and
are always hashed fresh. Design: `instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md` §2a.
Inert until structural-tier Phases 3/4 consult it.

### `pipeline_folder_state` — Pipeline per-folder step state (USER table, TODO-205 P7)
| Column | Type | Notes |
|--------|------|-------|
| folder_path | TEXT PK | Absolute folder path, forward-slash normalised |
| fingerprint | TEXT NOT NULL | Per-file stat-sweep aggregate (never the dir's own mtime) |
| verify_json / lookup_json / lbdir_json / rename_json / file_json | TEXT | Cached step verdict dicts as JSON; `file_json` is warm-start display only (P8: File is a live view) |
| steps_json | TEXT | JSON list of step names that have run |
| updated_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

Index: `idx_pipeline_state_fp ON pipeline_folder_state(fingerprint)`. Cached verdicts
are valid only while the recomputed fingerprint matches (rules R2/R3, design §3).

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

### `dylan_performances` — Dylan performance location supplement (MASTER table)
Populated once at startup from `data/2026-05-22_Dylan_Performance_fixed.ods` via
`import_dylan_performances()` when the table is empty. Included in master-data export/import
so all users receive the same reference dataset when installing a master update. Linked to
`entries` by converting `entries.date_str` → ISO via `geocoder._entry_date_to_iso()`.
| Column | Type | Notes |
|--------|------|-------|
| event_id | TEXT PK | e.g. `'1962092201'` (YYYYMMDDNN) |
| date_str | TEXT | ISO date from ODS, e.g. `'1962-09-22'` |
| category | TEXT | `HOME`, `NET` (Never Ending Tour era, not "internet"), `MCONCERT`, `GUEST` (other artist's show), `SIDEMAN`, `RADIO`, etc. — see `_PERF_CATEGORY_MAP` in `db.py` for which map to `entries.lb_category` |
| city | TEXT | City name |
| state | TEXT | State/province code |
| country | TEXT | Country code (e.g. `USA`) |
| venue | TEXT | Venue name |
| imported_at | TIMESTAMP | When the row was loaded |

Indexes: `idx_perf_date`, `idx_perf_category`, `idx_perf_country`.
Queried via `GET /api/performances?lb=<n>` or `?date=YYYY-MM-DD`.

### `recording_families` / `tapematch_family_meta` — TapeMatch family clustering (MASTER tables)
Synced from `tools/tapematch/observations.db` via `backend/tapematch_sync.py:sync_tapematch_families()`,
triggered manually via `POST /api/tapematch/sync` (not run at startup). Groups circulating LB#
recordings of the same show that are the same master tape transferred multiple times. Singletons
(family of one) are excluded — those recordings fall through to the no-families fallback. `fam_id`
is deterministic (`"{concert_date}#" + "-".join(sorted member lb_numbers)`), not tied to tapematch's
own run-scoped `family_id` integer, so re-syncs never silently repoint an existing `fam_id` at a
different recording set. See `instructions/design_handoff_unified_library/07-tapematch-backend-integration.md`.
| Column (`recording_families`) | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | |
| fam_id | TEXT NOT NULL | Deterministic, see above |
| concert_date | TEXT NOT NULL | ISO date |
| run_id | TEXT | tapematch run that produced this membership |
| imported_at | TIMESTAMP | |

| Column (`tapematch_family_meta`) | Type | Notes |
|--------|------|-------|
| fam_id | TEXT PK | |
| concert_date | TEXT NOT NULL | |
| label | TEXT | Auto-generated `"Family A"`/`"Family B"`/… by member_count desc |
| label_override | TEXT | Reserved for a future curator-naming UI; never touched by sync upserts |
| by | TEXT NOT NULL | `'ai'`, bumped to `'ai+lb'` if the LB page text corroborates the grouping |
| conf | REAL | Mean pairwise correlation within the family |
| note | TEXT | Unused (NULL) in this pass |
| member_count | INTEGER NOT NULL | |
| run_id | TEXT | |
| review_flag | INTEGER NOT NULL DEFAULT 0 | Set when the run's `analysis.md` verdict line reads "needs review"; applies to every family on that `concert_date` (the verdict judges the whole show, not one family) |
| review_reason | TEXT | Short reason text parsed from the verdict line, if present |
| imported_at | TIMESTAMP | |

Exposed flat (no clustering logic client-side) via `GET /api/tapematch/families` →
`[{lb_number, fam_id, fam_label, fam_conf, fam_by, concert_date, fam_needs_review, fam_review_reason}]`,
merged client-side by `lb_number` rather than joined into `/api/search`.

Sync trigger: manual only, two equivalent entry points — `POST /api/tapematch/sync` (needs the
Flask backend up) or `.venv/bin/python3 -m backend.tapematch_sync` (standalone CLI, no backend
needed). The latter is wired as the final step of the `/tapematch-batch` skill
(`.claude/commands/tapematch-batch.md`), run once a batch of analysis write-ups is done.

Quality-score corroboration (TODO-210a): during family sync, a family whose members include a
same-scan pair with `|Δabs_score| ≤ 0.5` and the same grade letter gets a one-time
`conf + 0.05` bump (clamped to 1.0). Feature-detected — DBs without Concert Ranker's
`abs_score`/`abs_grade` columns skip it silently.

Duplicate-encode leads (TODO-210b): `GET /api/tapematch/dup_encodes` (or
`python -m backend.tapematch_sync --dup-encodes`) lists same-date pairs whose
`quality_recording_metrics.metric_json` is byte-identical within one scan_id — near-certain
split-only duplicates. Read-only curation signal, never auto-merged; no GUI yet (TODO-215).

### `quality_scans` / `quality_recording_metrics` / `quality_recording_scores` — Concert Ranker (USER tables)
Audio-quality analysis of the user's own copies, produced by the `concert_ranker/` package. USER-tier
(in `USER_TABLES`, never shipped in master). The RAW aggregated metrics (`metric_json`) are stored
**separately** from the derived scores so re-banding/re-ranking (`concert_ranker rerank`) never needs an
audio rescan — the "scan once, store RAW metrics" guarantee. Created by `init_db()`.
| Column (`quality_scans`) | Type | Notes |
|--------|------|-------|
| scan_id | INTEGER PK | Auto-increment; one row per scan run |
| started_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| config_json | TEXT | Thresholds/weights used, for reproducibility |
| notes | TEXT | Free-text |

| Column (`quality_recording_metrics`) | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER | PK part; FK → entries |
| scan_id | INTEGER | PK part; FK → quality_scans |
| source_class | TEXT | SBD/AUD/FM/UNKNOWN (derived at scan time) |
| metric_json | TEXT NOT NULL | RAW aggregated metric dict (`{"_v","metrics","tracks",…}`) |
| completeness | REAL | Sibling-relative; filled at rank time (NULL at scan time) |
| duration_sec | REAL | Absolute recording length |
| scored_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

PK `(lb_number, scan_id)`; index `idx_quality_metrics_scan`.

| Column (`quality_recording_scores`) | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER | PK part; FK → entries |
| scan_id | INTEGER | PK part |
| family_id | INTEGER | Dense per-scan id into `recording_families.fam_id`; NULL if ungrouped |
| final_score | REAL | Fused score; NULL if vetoed |
| rank_in_family | INTEGER | 1 = best transfer of the show; NULL if vetoed/standalone-singleton |
| vetoed | INTEGER | 1 = hard-disqualified (lossy/etc.), excluded from ranking |
| verdict_text | TEXT | `explain_recording()` human-readable verdict |

PK `(lb_number, scan_id)`; indexes `idx_quality_scores_scan`, `idx_quality_scores_family`. Rewritten
wholesale on every rerank (derived data — recomputable from `quality_recording_metrics`).

### `entry_lineage` — Per-LB parsed lineage signals (USER table)
Structured lineage metadata extracted from `entries.description` for use by the recording-family
clustering / learning phase. Never exported in master data. Populated by `tools/parse_lineage.py`.
Exposed via `GET /api/lineage/<lb>`.
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LosslessBob entry number |
| taper_name | TEXT | From `extract_taper_and_source()` |
| source_chain | TEXT | From `extract_taper_and_source()` |
| taper_normalised | TEXT | Lowercase, punctuation-stripped taper_name (e.g. "j smith") |
| mentions_lb | TEXT | JSON: `[[lb_number, snippet], ...]` — all LB refs found in description |
| same_as_lb | TEXT | JSON: `[lb_number, ...]` — LB numbers claimed as same source |
| derived_from_lb | TEXT | JSON: `[lb_number, ...]` — LB numbers this was derived from |
| better_than_lb | TEXT | JSON: `[lb_number, ...]` — LB numbers this supersedes |
| parse_confidence | TEXT | `'high'` / `'medium'` / `'low'` / `'none'` |
| parsed_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| source_text_hash | TEXT | SHA256 of `entries.description` at parse time (skip-guard) |

Index: `idx_lineage_taper_norm ON entry_lineage(taper_normalised) WHERE taper_normalised IS NOT NULL`.

`parse_confidence` rules: `high` = explicit `Taper:` label + source_chain both found;
`medium` = one of the two found; `low` = only heuristic-path taper match, no chain; `none` = both NULL.

### `taper_attributions` — Derived per-LB taper designations (USER table)
Recomputed wholesale by `tools/attribute_tapers.py` (engine in `backend/taper_attribution.py`)
from `entry_lineage` / `recording_families` / `taper_confirmations`. Never exported in master
data — curator decisions live in the MASTER-tier `taper_confirmations` table instead (finding F2,
`instructions/SPEC_INTEGRATION_NOTES.md`), so a master import can never clobber locally-computed
propagation.
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LosslessBob entry number |
| taper_normalised | TEXT NOT NULL | Canonical key into `_KNOWN_TAPER_ALIASES` values |
| confidence | TEXT NOT NULL | `'confirmed'` / `'propagated'` / `'inferred'` |
| evidence_json | TEXT NOT NULL | JSON list of evidence records `{kind, detail, ...}` |
| conflict | INTEGER DEFAULT 0 | 1 = contradictory evidence, needs curator review |
| confirmed_at | TIMESTAMP | Set only for rows sourced from `taper_confirmations` |
| computed_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

Indexes: `idx_taper_attr_name(taper_normalised)`, `idx_taper_attr_conf(confidence)`.

### `show_picks` — Derived per-date "best of" ranking (USER table)
Recomputed wholesale by `tools/compute_show_picks.py` (scoring in `concert_ranker/picks.py`)
from `entries.rating`, `curated_lists`, `entry_lineage`, `quality_recording_scores`, and (if
present) `taper_attributions`. Never exported in master data. Scoring model:
`instructions/FABLE_UNIFIED_RANKING.md` §3/§4.
| Column | Type | Notes |
|--------|------|-------|
| concert_date | TEXT NOT NULL | PK part 1 — raw LB-site format `M/D/YY`, may contain `xx` components |
| lb_number | INTEGER NOT NULL | PK part 2 |
| pick_score | REAL NOT NULL | Comparable within a date only |
| pick_rank | INTEGER NOT NULL | 1 = recommended for the date |
| evidence_json | TEXT NOT NULL | Ordered list of `{kind, detail, points}` |
| concert_date_iso | TEXT | `YYYY-MM-DD` parsed from `concert_date` (two-digit-year pivot 30); NULL when any component is `xx` (LISTENING §9) |
| computed_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

Indexes: `idx_show_picks_lb(lb_number)`, `idx_show_picks_date_iso(concert_date_iso)`.

### `song_canonical` / `song_performances` — Song-centric index (USER tables, TODO-230)
LISTENING §3, olof_songs spine. `song_canonical(alias_norm PK, canonical, source 'auto'|'curator',
updated_at)` — normalised-alias → display-spelling map, auto-seeded from `olof_songs.song_title`
norm-groups (most frequent raw spelling wins); curator rows are sticky against re-seeding.
`song_performances(event_id+position PK, song_norm, song_canonical, concert_date_iso, is_encore,
take_status, event_type, computed_at)` — derived wholesale (guarded DELETE+reinsert) from
`olof_songs JOIN olof_events` by `backend/song_index.py` (`tools/compute_song_performances.py`
CLI; 4th step of `/api/derived/recompute`). Normalisation: NFKD/casefold/apostrophe-unify/
punct→space/ws-collapse. Both USER-tier — never in master export (rebuilt from local olof_*).
Indexes: `idx_song_perf_norm(song_norm)`, `idx_song_perf_date(concert_date_iso)`.

### `setlist_fingerprint_suggestions` — Setlist fingerprinting review queue (USER table, TODO-225)
Curator suggestions only, never auto-applied. `(lb_number+rank PK, event_id, score, matched_count,
entry_song_count, olof_song_count, matches_json, missing_json, status 'pending'|'dismissed',
computed_at)`. `backend/setlist_fingerprint.py:run_fingerprint_scan()` scores every candidate
entry's folder tracklist (`entries.setlist`) against every `olof_songs` setlist and keeps the top
3 by score. Candidates = entries with no clean parseable date or a location parked in
`location_geocoded.source='skipped_not_concert'` (TODO-221) — the unknown/junk-metadata tail
only, not bulk re-dating. Scoring blends entry_coverage (0.5), order_score via longest-increasing-
subsequence of matched positions (0.3), and olof_coverage (0.2); matching reuses
`db.normalize_title_for_match`/`db.titles_match` (same containment-tolerant rule as
`compare_olof_setlist`). Wholesale-replaced per scan but `status` is preserved per (lb_number,
event_id) so a curator's dismiss survives a rescan. USER-tier — never in master export.
Indexes: `idx_fp_suggest_status(status)`, `idx_fp_suggest_event(event_id)`.

### `tapematch_pairs` — Per-date pairwise similarity (USER table)
Slim mirror of `tools/tapematch/observations.db` `pairs`, synced by
`backend/tapematch_sync.py:sync_tapematch_pairs()` (chained after the families sync in both
`POST /api/tapematch/sync` and the standalone CLI). Same latest-complete-run-per-date rule as
`recording_families`; wholesale replaced per `concert_date` so a date's rows never blend two
runs. Never exported in master data. Feeds the TapeMatch screen's similarity matrix
(LISTENING §1, `instructions/FABLE_LISTENING_INSIGHT_IDEAS.md`).
| Column | Type | Notes |
|--------|------|-------|
| concert_date | TEXT NOT NULL | PK part 1 (YYYY-MM-DD) |
| lb_a | INTEGER NOT NULL | PK part 2; always lb_a < lb_b (normalised on sync) |
| lb_b | INTEGER NOT NULL | PK part 3 |
| corr | REAL | Residual cross-correlation (0–1) |
| emb_score | REAL | Pretrained-embedding cosine similarity |
| fp_score | REAL | Fingerprint match score |
| same_family | INTEGER NOT NULL | 1 = tapematch_verdict was `same_family` |
| similarity_pct | INTEGER | 0–100 banded blend (`similarity_pct()`, breakpoints 2026-07-10); NULL = not comparable |
| run_id | TEXT | tapematch run the row came from |
| imported_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

Index: `idx_tapematch_pairs_date(concert_date)`.

### `lb_problems` — Known problems with specific LB entries (MASTER table)
Curator-authored table for flagging LB entries with known issues (bad checksums,
incomplete torrent, corrupt files, mislabelled metadata, etc.). Included in master-data export.
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER NOT NULL | FK → lb_master.lb_number |
| notes | TEXT NOT NULL | Free-text description of the problem |
| added | TEXT NOT NULL | ISO date (YYYY-MM-DD) the note was added |

Index: `idx_lb_problems_lb ON lb_problems(lb_number)`.
Managed via `GET/POST /api/lb_problems` and `PUT/DELETE /api/lb_problems/<id>`.

### `curated_lists` / `curated_list_entries` — Curator "best of" picks (TODO-181, MASTER tables)
Named lists of curator-picked best LB recordings (e.g. carbonbit, 10haaf), imported via
`tools/import_curated_lists.py` from `data/lists/`. Routes: `GET/POST /api/curated_lists`,
`DELETE /api/curated_lists/<name>` (POST/DELETE curator-gated). Surfaced as performance-lens
filter views + badges on the Library screen (TODO-181/186, closed 2026-07-09).
| Column (`curated_lists`) | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT NOT NULL UNIQUE | Slug, e.g. `'carbonbit'`, `'10haaf'` |
| label | TEXT NOT NULL | Display name, e.g. `"carbonbit's picks"` |
| source | TEXT NOT NULL | Free-text note on the source file(s) |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

| Column (`curated_list_entries`) | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| list_id | INTEGER NOT NULL | FK → curated_lists.id |
| lb_number | INTEGER NOT NULL | |
| note | TEXT NOT NULL | Free-text context (e.g. carbonbit's date/venue line); empty for 10haaf |
| added_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

UNIQUE `(list_id, lb_number)` — a date can have multiple LB picks (multiple rows, same list_id),
but re-running the import is idempotent. Indexes: `idx_curated_entries_lb`, `idx_curated_entries_list`.

### `taper_confirmations` — Curator taper attribution decisions (MASTER table)
Sticky curator confirm/reject decisions on taper attribution, exported in master data (finding
F2, `instructions/SPEC_INTEGRATION_NOTES.md`). `tools/attribute_tapers.py` reads it first on
every recompute: `'confirm'` rows seed a sticky confirmed-tier attribution; `'reject'` rows
suppress that pair from output. Phase 1 ships schema + recompute support only — the
confirm/reject curator API lands in TAPER phase 2.
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LosslessBob entry number |
| taper_normalised | TEXT NOT NULL | Canonical key into `_KNOWN_TAPER_ALIASES` values |
| action | TEXT NOT NULL | `'confirm'` / `'reject'` (convention only, no CHECK) |
| decided_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

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

### `olof_pages` / `olof_events` / `olof_songs` — Olof Björner mirror + parsed events (TODO-162, local-only)
Spec: `instructions/FABLE_OLOF_FILES.md` §4 (authoritative column list). `olof_pages` = one row
per mirrored bobserve.com page (filename PK, url, corpus `'dsn'`/`'chronicle'`, segment_title,
year, sha256, fetched_at, parsed_at, parse_status, event_count); pages live verbatim in
`data/olof/pages/` via `backend/olof_fetcher.py`. `olof_events` = one row per Still On The Road
event (event_id PK = DSN number; date_str ISO + raw, venue/city/region/country split fields,
event_type `concert|session|rehearsal|broadcast|interview|other`, tour_name, NET/year concert
numbers, lineup, recording kind/mins, notes, bobtalk, releases_raw, references_raw, raw_text
safety net) via `backend/olof_parser.py`. `olof_songs` = one row per performed song / studio
take (event_id+position PK, song_title, credits, is_encore, take_number, take_status,
annotations, released_on — annotation/release position-ranges resolved per song).
`olof_chronicle` = one row per dated calendar/diary entry (year+seq PK, date_str ISO where
resolvable, date_raw, entry_text — Word field junk stripped); `olof_new_tapes` = one row per
'New tapes & bootlegs' subsection (year+seq PK, title, date_str ISO show date or '', body_text)
— both via `backend/olof_chronicle_parser.py`. 2022+ appendix setlists parse into
`olof_events`/`olof_songs` with synthetic `year*1000+seq` IDs (source `'chronicle_appendix'`)
but the path is dormant — 2013+ chronicles are PDF-only on bobserve (TODO-228). Indexes:
`idx_olof_events_date`, `idx_olof_events_tour`, `idx_olof_songs_title`,
`idx_olof_chronicle_date`, `idx_olof_new_tapes_date`. Not in `MASTER_TABLES` yet —
master/sitedata export tier is a P5 decision.

### `location_geocoded` — Geocoded concert locations (MASTER TABLE)
| Column | Type | Notes |
|--------|------|-------|
| location_text | TEXT PK | Matches `entries.location` verbatim |
| lat | REAL | WGS-84 latitude (NULL if geocoding failed) |
| lon | REAL | WGS-84 longitude (NULL if geocoding failed) |
| source | TEXT NOT NULL | `'nominatim'` / `'performances'` / `'bobdylan_shows'` / `'olof_events'` / `'setlistfm_shows'` (each also with `-city` suffix for the venue-stripped fallback) / `'manual'` / `'failed'` / `'skipped_not_concert'` |
| confidence | TEXT | `'high'` / `'medium'` / `'low'` / NULL |
| display_name | TEXT | Full display name returned by Nominatim |
| manual_override | INTEGER | 1 = curator-placed pin; batch run never overwrites |
| note | TEXT | Optional curator note |
| lb_number | TEXT | LB entry that prompted this override (traceability) |
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

### `archive_org_uploads` — Internet Archive upload history (USER table)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER NOT NULL | LB entry being uploaded |
| identifier | TEXT NOT NULL | IA item identifier (e.g. `losslessbob-lb-01234`) |
| folder_path | TEXT NOT NULL | Absolute path to source folder |
| files_total | INTEGER | Number of audio files to upload |
| files_uploaded | INTEGER | Files successfully uploaded |
| status | TEXT NOT NULL | `pending`, `running`, `done`, `failed`, `stopped` |
| started_at | TIMESTAMP | Upload start time |
| finished_at | TIMESTAMP | NULL until complete |
| error | TEXT | Error message if status=failed |

Indexes: `idx_archive_uploads_lb(lb_number)`, `idx_archive_uploads_status(status, started_at DESC)`.

### `collection_mounts` — User-defined collection storage mounts (USER table)
Named root paths where filed recordings are stored. Referenced by `collection_routes`.
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| label | TEXT NOT NULL UNIQUE | Human-readable name (e.g. `"NAS"`, `"External SSD"`) |
| root_path | TEXT NOT NULL | POSIX-normalised absolute path to mount root |
| notes | TEXT | Optional free-text notes |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

### `collection_routes` — Year → mount routing table (USER table)
Maps each concert year to a destination mount + optional sub-path. Used by `filer.py` to resolve where to file a recording.
| Column | Type | Notes |
|--------|------|-------|
| year | INTEGER PK | Concert year (1958–2026+) |
| mount_id | INTEGER NOT NULL | FK → `collection_mounts(id)` ON DELETE RESTRICT |
| sub_path | TEXT NOT NULL | Sub-directory under mount root (default `''`) |

Index: `idx_routes_mount ON collection_routes(mount_id)`.
`meta` key `pipeline_file_mode` (`'move'` or `'copy'`) controls whether `filer.py` moves or copies folders.

### `collection_integrity_status` — TODO-111: latest per-LB integrity scan result
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | Owning collection entry |
| mount_id | INTEGER | FK → `collection_mounts(id)` ON DELETE SET NULL; best-prefix match of `disk_path` |
| disk_path | TEXT NOT NULL | Folder verified |
| status | TEXT NOT NULL | `pass \| content_issue \| tag_issue \| missing_files \| no_lbdir \| error` |
| content_issues | INTEGER | Count of files with `ffp_status == 'fail'` (bitrot/corruption) |
| tag_issues | INTEGER | Count of files with `md5_status == 'fail'` and `ffp_status` pass/na (tags-only edit) |
| missing_count | INTEGER | Count of lbdir-listed files with `overall == 'missing'` |
| total_files | INTEGER | Total lbdir-listed files considered (excludes `overall == 'extra'`) |
| checked_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP, updated on each scan |

Index: `idx_cistatus_mount ON collection_integrity_status(mount_id, status)`.

### `collection_integrity_scans` — TODO-111: integrity scan run history
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| mount_id | INTEGER | FK → `collection_mounts(id)` ON DELETE CASCADE; NULL = whole-collection scan |
| status | TEXT NOT NULL | `running \| done \| error \| cancelled` |
| started_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| finished_at | TIMESTAMP | NULL while running |
| folders_checked / folders_pass / folders_content_issue / folders_tag_issue / folders_missing / folders_no_lbdir | INTEGER | Aggregate per-status folder counts |
| error | TEXT | Error message if status=error |

Index: `idx_ciscans_mount ON collection_integrity_scans(mount_id, started_at DESC)`.
`meta` key `integrity_scan_interval_hours` (default `"0"` = disabled) controls the
scheduled scan interval, checked hourly by `scheduler._integrity_scan_worker`.

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
| GET | `/api/home/stats` | `{collection_count, wishlist_count, missing_count, bootleg_count, checksum_count, latest_lb, last_import, collection_size}` — single-query counts for the Home dashboard and AppShell footer. `collection_size` is `{bytes, human, folders, computed_at, computing}` — total on-disk bytes across all `my_collection` folders, cached in `meta` (`collection_size_bytes`/`_folders`/`_computed_at`) and refreshed via a background thread (`backend/filer.py: get_collection_size_stats()`) when older than 24h rather than walked per request. |
| GET | `/api/activity/busy` | `{busy, activity}` — polls import/scrape/bootleg-scrape/integrity-scan/file-job workers plus app-update/data-download state. `activity` is one of `importing`, `scraping`, `scraping_bootlegs`, `scanning`, `filing`, `updating_app`, `downloading_data`, or `null` when idle. Used by the AppShell footer busy indicator. |
| GET | `/api/system/uptime` | `{uptime_seconds}` since the Flask process started (About screen uptime clock) |
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
| GET  | `/api/master/github_check` | Queries `kuddukan42/losslessbob`'s latest GitHub release, downloads its `.manifest.json` sidecar, and compares `master_version` against the local `meta` table. Returns `{available, tag, remote_version, remote_published_at, local_version, local_published_at, asset_name, asset_size, release_url}`, or `{available: false, message}` if no usable release exists. |
| POST | `/api/master/github_install` | `text/event-stream`. Downloads the latest master `.db` + `.manifest.json` from GitHub Releases into `data/imports/`, verifies SHA256, and applies via `import_master_db()`. Events: `progress` (`label`, `pct`), `done` (`summary`), `error` (`error`, `message`) — same shape as `/api/master/github_release`. |

### Site-Data Packaging & Onboarding (FABLE_ONBOARDING_SYNC §3–§4, P1+P2)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/package/scrape_data` | Bundles `data/site/` into a dated zip in `data/exports/` + `.manifest.json` sidecar (`type`, `created_at`, `file_count`, `total_bytes`, `sha256`). Query `part=core` (all but `files/`, `type: sitedata_core`), `part=files` (`files/` only, `type: sitedata_files`); omitted = legacy whole-tree zip (`type: scrape_data`, backward compatible with ScreenSetup / gui/setup_tab.py). Returns `{ok, path, manifest_path, manifest}`; 400 `invalid_part` / `no_site_data`. |
| POST | `/api/sitedata/github_release` | **Curator-only** (403 otherwise). `text/event-stream`. Builds core+files zips + manifests, creates GitHub release `sitedata-YYYY-MM-DD[.N]` on `kuddukan42/losslessbob`, uploads 4 assets (2 zips + 2 manifest sidecars) with progress. Same event shapes as the master release flow. First release published 2026-07-10 (`sitedata-2026-07-10`). |
| GET | `/api/sitedata/github_check` | Latest `sitedata-*` release on `kuddukan42/losslessbob`. Matches part zips by `_core_`/`_files_` substring (collision-suffix tolerant) + `.manifest.json` sidecar pairing; parts missing their sidecar are omitted. Returns `{available, tag, release_url, published_at, parts: {core?, files?: {asset_name, asset_size, manifest}}}` or `{available: false, message}`. |
| POST | `/api/sitedata/github_install` | `text/event-stream`, same event shapes as master install. Body `{parts: ["core"\|"files", …]}` (default `["core"]`, 400 `invalid_part`). Per part: downloads zip to `data/imports/`, verifies SHA256 vs manifest **before** extraction (mismatch deletes zip, errors, site dir untouched), extracts into `data/site/` (overwrite semantics), writes `.sitedata_<part>_manifest.json` marker in `data/site/`. |
| GET | `/api/onboarding/status` | Cheap first-run progress for wizard/Home checklist (spec §4): `{entries_count, master_version, sitedata_core_present, sitedata_files_count, mounts_configured, collection_count, complete}`. `complete` = entries ∧ master_version ∧ ≥1 mount. Reads install markers when present; falls back to dir checks/scandir. Live: ~63 ms. |

### LB Master Integrity
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/lb_master/stats` | Return `{public, private, missing, nonexistent, max_lb, overrides, needs_review, public_no_checksums}` counts. |
| GET | `/api/lb_master` | Paginated lb_master rows. Query params: `status`, `override=1`, `review=1`, `limit` (max 2000), `offset`. |
| GET | `/api/lb_master/<lb>` | Single lb_master row joined with entry metadata. |
| POST | `/api/lb_master/reconcile` | Full rebuild of lb_master. Backs up DB first. Returns `{ok, stats}`. |
| GET | `/api/lb_master/history/<lb>` | Transition history for an LB, newest first. Query param: `limit` (default 50). |
| PUT | `/api/lb_master/<lb>/manual` | Set a manual override. Body: `{status, notes}`. |
| DELETE | `/api/lb_master/<lb>/manual` | Clear a manual override and immediately reconcile. Returns `{ok, new_status}`. |
| GET | `/api/lb_master/<lb>/nft` | Return `{nft: bool, reason}` for folder naming guidance. |
| GET | `/api/lb_master/overrides/export` | Export all `manual_override=1` rows as a JSON array. Read-only; no curator check required. Returns `[{lb_number, manual_status, manual_notes, manual_set_by, manual_set_at}, ...]`. |
| POST | `/api/lb_master/overrides/import` | **Curator-only.** Body: same JSON array. Upserts each row via `set_lb_manual_override`, writes `lb_status_history` with `trigger_event='import'`, skips lb_numbers outside current max. Returns `{imported, skipped}`. |

### LB Missing (confirmed non-existent entries)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/lb_missing` | List all lb_missing rows ordered by lb_number. |
| POST | `/api/lb_missing` | **Curator-only.** Add entry. Body: `{lb_number, confirmed_date?, notes?}`. Returns `{ok, lb_number}`. |
| DELETE | `/api/lb_missing/<lb>` | **Curator-only.** Remove entry; immediately reconciles lb_master status. Returns `{ok, lb_number}`. |

### Dylan Performances
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/performances` | Query `dylan_performances`. Params: `date` (YYYY-MM-DD), `lb` (int — resolved via entries.date_str), `category`, `limit` (default 200), `offset`. Returns list of `{event_id, date_str, category, city, state, country, venue}`. |

### TapeMatch Family + Pairs Sync
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/tapematch/sync` | Ingests `tools/tapematch/observations.db` into `recording_families`/`tapematch_family_meta` then `tapematch_pairs` (chained, one trigger). Manual trigger only. Returns `{ok, dates_processed, families_written, recordings_linked, pairs_synced, pair_dates, errors}`. |
| GET | `/api/tapematch/families` | Flat list for client-side merge by `lb_number`. Returns `[{lb_number, fam_id, fam_label, fam_conf, fam_by, concert_date}]`. |
| GET | `/api/tapematch/pairs?date=` | One date's `tapematch_pairs` rows for the similarity matrix: `{date, run_id, pairs: [{lb_a, lb_b, corr, emb_score, fp_score, same_family, similarity_pct, human_judgment, human_notes, ab_eligible}]}`. `human_*` and `ab_eligible` (TODO-231) read LIVE (best-effort) from observations.db; null on lock/missing. `ab_eligible` is resolved per pair via `ab_clips.get_pair_source_info` (each pair's own latest common tapematch run), matching what `POST /api/ab_clip` will accept — not the (possibly stale) run_id synced into `tapematch_pairs`. 200 with `pairs: []` for un-synced dates. |
| POST | `/api/tapematch/pairs/judgment` | Curator match feedback (TODO-215). Body `{date, lb_a, lb_b, run_id?, judgment, notes?}`; `judgment` ∈ `confirmed_same\|confirmed_different\|uncertain\|lb_wrong` or null to clear. Writes `human_judgment`/`human_notes` into observations.db pairs (read-write). 400 `bad_judgment`/`missing_fields`, 404 `no_run`/`pair_not_found`, 409 `locked`. |
| GET | `/api/tapematch/analysis?date=` | Best run's `analysis.md` for a date: `{date, run_id, verdict: {needs_review, reason}\|null, analysis_md\|null}`. 409 `locked` when observations.db is write-locked. |
| GET | `/api/tapematch/dates` | Left-rail summary, date DESC: `{dates: [{date, run_id, n_lbs, n_pairs, has_analysis, needs_review, location}]}`. `location` resolved via the date's LB numbers (entries.date_str is US-format, never joined on). has/needs fields null when observations.db missing/locked. |
| GET | `/api/tapematch/crawl/status` | Read-only crawl status (mirrors `tools/tapematch/crawl_status.sh`): `{running, pid, runs_on_disk, distinct_dates, log_tail}`. |
| POST | `/api/tapematch/crawl/start` | Launches the detached library crawl via `crawl_start.sh` (script is the single-instance authority). Optional body `{min_entries?, allow_missing?}` → script flags. 200 `{ok, message}`; 409 `already_running` when the script's pgrep guard refuses; 400 bad body. |
| POST | `/api/tapematch/crawl/stop` | Stops the crawl via `crawl_stop.sh` (SIGINT, no-op if idle — always 200 `{ok, message}`). |
| GET | `/api/tapematch/dup_encodes` | Likely-duplicate-encode curation leads (TODO-210b): same-date pairs with byte-identical `metric_json` within one scan_id. `{candidates: [{date, lb_a, lb_b, scan_id, same_family, reason}]}`. Read-only, never auto-merges; no GUI yet (TODO-215). |
| POST | `/api/ab_clip` | Aligned A/B listening (LISTENING §2, TODO-231). Body `{date, lb_a, lb_b, t_sec, dur_sec?}` (`dur_sec` clamped 5-60, default 20). v1 restricted to pairs where both sources' `speed_kind ∈ {reference, aligned}` in observations.db `sources` (latest common run). Maps `t_sec` to each source's local audio offset via `trim_head_sec`, extracts WAV clips (16-bit/44.1k/stereo, may span track boundaries) from `my_collection.disk_path` via `backend/ab_clips.py`, caches in `data/ab_clips/` (LRU-pruned to 40). Returns `{date, lb_a, lb_b, t_sec, dur_sec, clip_a, clip_b}` (`/api/ab_clip/<name>` URLs). 400 `bad_request`/`t_out_of_range`, 404 `pair_not_found`/`folder_missing`, 409 `not_eligible`/`locked`. |
| GET | `/api/ab_clip/<name>` | Serves one cached A/B WAV clip from `data/ab_clips/`. 404 `clip_not_found` if pruned/absent. |

### Derived-Data Recompute
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/derived/recompute` | SSE-streamed chained recompute: `tools.parse_lineage.run()` → `tools.attribute_tapers.run()` → `tools.compute_show_picks.run()` in canonical order (finding F1/F5, `instructions/SPEC_INTEGRATION_NOTES.md`). Events: `start`/`done` (with per-step `stats`)/`skipped` (module not importable — later phase not shipped)/`error` (aborts chain)/`chain_done`. Manual trigger only (onboarding "Done" step + curator recompute button); not curator-gated — rewrites only USER-tier derived tables (`entry_lineage`, `taper_attributions`, `show_picks`, `song_canonical`/`song_performances` — `backend.song_index.run()` appended as 4th step 2026-07-11, TODO-230). |
| GET | `/api/songs?q=` | Song-centric index (LISTENING §3, TODO-230): distinct songs from `song_performances`, most-performed first; `q` = substring filter on canonical/norm. Returns `{songs: [{song_norm, canonical, n_performances, n_concerts, n_dates_with_recordings, first_date, last_date}]}` (`n_dates_with_recordings` via `show_picks.concert_date_iso`). |
| GET | `/api/songs/performances?song=` | Every performance of one `song_norm`: `{song_norm, canonical, performances: [{date_iso, event_id, event_type, venue, city, is_encore, take_status, recordings: [{lb_number, pick_rank, abs_grade}]}]}` — venue/city from `olof_events`, recordings via `show_picks` + latest quality scan. 404 unknown. |
| POST | `/api/songs/alias` | Curator-only (403). Body `{alias, canonical}` — normalises alias, upserts `song_canonical` `source='curator'` (sticky against re-seeding), re-runs the song_performances recompute. |
| GET | `/api/picks/for/<lb>` | One LB's `show_picks` row: `{concert_date, lb_number, pick_score, pick_rank, evidence, computed_at}` with `evidence` parsed from `evidence_json` (F3 record shape). 204 when no row (pre-recompute, or entry has no usable date). Feeds DetailPanel's Picks tab / `EvidenceList`. |
| GET | `/api/picks?date=` | All `show_picks` rows for one ISO date (`YYYY-MM-DD`, matched on `concert_date_iso`), rank-ordered, evidence parsed (LISTENING §9). |
| GET | `/api/picks/tonight` | Rank-1 picks whose `concert_date_iso` falls on today's month-day across all years (`?mmdd=MM-DD` override for testing), best `pick_score` first. Returns `{mmdd, candidates: [{lb_number, year, concert_date_iso, location, rating, pick_score, description}]}`; empty candidates is a normal 200. Feeds the Home "Tonight in Dylan history" card. |

### Taper Attribution (FABLE_TAPER_ATTRIBUTION phase 2)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/tapers/attributions/<lb>` | One LB's `taper_attributions` row: `{lb_number, attribution: {taper_normalised, confidence, evidence, conflict, confirmed_at, computed_at} \| null}` with `evidence` parsed (F3 record shape). 200 with `attribution: null` when no row. Feeds DetailPanel's Taper tab / `EvidenceList`. |
| GET | `/api/tapers/attributions?confidence=&taper=&conflict=1` | Filtered list with parsed evidence, ordered by `lb_number`. `taper` accepts raw or canonical names (normalised server-side). Open (no curator gate). |
| POST | `/api/tapers/attributions/<lb>/confirm` | Curator-only. Body `{taper?}` (else sourced from the existing attribution row; 400 if neither). Upserts a sticky `taper_confirmations` 'confirm' row (MASTER, F2) and immediately upserts `taper_attributions` to `confidence='confirmed'` — recompute-equivalent, so a later `/api/derived/recompute` is a no-op for this lb. Taper must be in the known-taper universe. |
| POST | `/api/tapers/attributions/<lb>/reject` | Curator-only. Body `{taper?}`. Upserts a sticky 'reject' row and deletes the matching `taper_attributions` row (same pair-match rule as recompute's `_apply_rejects`); future recomputes stay suppressed via `taper_confirmations`. |

### Curated Lists
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/curated_lists` | All curated lists with entry counts. Open (no curator gate). |
| POST | `/api/curated_lists` | Curator-only. Create-or-fetch a list. Body `{name, label?, source?}`; 400 on missing name. |
| DELETE | `/api/curated_lists/<name>` | Curator-only. Delete a list and all its entries; 404 if no such name. |

### Library — Performance/Show Grouping
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/library/performances` | `db.get_performances()` — groups `entries` by raw `(date_str, location)` into shows for the Library screen's performance lens (TODO-150 step 5). `lb_category = 'concert'` entries are always grouped — as of TODO-151 (2026-06-18) this includes dates only known via `dylan_performances` category `GUEST` (guest spot at another artist's show) or `NET` (Never Ending Tour era), both now mapped to `'concert'` in `_PERF_CATEGORY_MAP`; when `bobdylan_shows` has no row for the date, `venue` falls back to `dylan_performances.venue`. `lb_category = 'unknown'` entries are ALSO grouped when they have a fully-specified date + non-blank location, flagged `confirmed: false` (degraded fallback for whatever `dylan_performances` still doesn't cover, e.g. category `FILM` — ~19 shows after the GUEST/NET fix, down from 198). Other non-concert categories (radio/tv/interview/studio/etc.) and bare 'unknown' rows (no date or no location) stay recording-lens-only. Cross-references `bobdylan_shows` (venue/setlist key/track count), `dylan_performances` (venue fallback), `setlistfm_shows` (tour; as of TODO-153/162 P5a dates setlistfm leaves blank fall back to `olof_events.tour_name` — setlistfm always wins, +757 dated shows gained a tour), `bootleg_titles` (release title). Returns `[{id, date, disp, year, venue, city, status, recordings: [{lb, lbNumber, src, rating, status}], dow?, tour?, setlist?, tracks?, title?, confirmed?}]` — optional keys omitted (not null-faked) when no source data exists; `confirmed` omitted (true by default) except `false` on degraded unknown-only rows. TapeMatch family data is **not** joined in; the GUI merges `/api/tapematch/families` client-side by `lb_number`, same pattern as `/api/collection/prefetch`. As of 2026-07-09 (FABLE_UNIFIED_RANKING phase 3, finding F4) each recording also carries flat optional `pickRank` (`show_picks.pick_rank`, 1 = recommended), `absGrade` (latest Concert Ranker scan grade), and `curated` (curated-list names) — omitted when the signal doesn't exist for that LB. |
| GET | `/api/library/badges` | `db.get_pick_badges()` — flat `{lb_number: {pickRank?, absGrade?, curated?, taperConfirmed?, taperReview?}}` map so the **recording** lens (sourced from `/api/search` + `/api/collection/prefetch`, which join none of `show_picks`/`quality_recording_scores`/`curated_lists`/`taper_attributions`) can surface the same badges the performance lens gets inline. Reuses the exact loaders `get_performances()` uses; only LBs with a signal appear, absent fields omitted; empty on a fresh install pre-recompute. GUI merges it client-side by `lb_number`, same pattern as `/api/tapematch/families` (SPEC_INTEGRATION_NOTES.md F4, TODO-212). |

### Olof Björner (Still On The Road + Yearly Chronicles — TODO-162 P5a, local-only tables)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/olof/date/<date_str>` | Everything Olof's corpus knows about an ISO show date: `{date_str, events: [olof_events row + songs: [{position, song_title, credits, is_encore, take_number, take_status, annotations, released_on}]], chronicle: [...], new_tapes: [...]}`. Lists are empty (never 404) — olof_* is local-only, most installs have no data. Feeds DetailPanel's Olof tab. |
| GET | `/api/olof/event/<int:event_id>` | One `olof_events` row (all columns incl. bobtalk/raw trailers) + ordered `songs`. 404 if unknown. |
| GET | `/api/olof/chronicle/<int:year>` | `{year, entries: [olof_chronicle rows]}` in seq order — year-timeline surface. |
| GET | `/api/olof/status` | `{pages, events, songs, chronicle_rows, new_tapes, chronicle_years, max_dsn_year}` — the GUI gates all Olof UI on `events > 0`. |
| POST | `/api/olof/compare` | Setlist-vs-folder comparison. Body `{date_str, titles?: [...], lb_number?}` (`lb_number` resolves titles server-side from `entries.setlist` free text). Returns `{olof_event_id, olof_setlist, matches: [{input_title, matched_position, matched_title}], olof_missing, match_pct, recording_info, recording_kind, recording_mins}`. Order-independent matching via `db.normalize_title_for_match` (cp1252 apostrophe fold, case/punctuation collapse, leading-"The" strip) + conservative containment. 400 without date_str or resolvable titles. |

### Setlist Fingerprinting (TODO-225, `backend/setlist_fingerprint.py`)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/fingerprint/scan` | (Re)scans candidate entries (no clean date, or a `skipped_not_concert` location) and wholesale-rebuilds `setlist_fingerprint_suggestions`. Body `{limit?: int}`. Returns `{candidates_scanned, candidates_matched, suggestions_written, skipped_no_titles}`. Not curator-gated (local-only derived table, like `/api/derived/recompute`); a full-catalog scan takes ~30-40s synchronously. |
| GET | `/api/fingerprint/suggestions` | Query `status` = `pending` (default) \| `dismissed` \| `all`. Returns `{suggestions: [{lb_number, rank, event_id, score, matched_count, entry_song_count, olof_song_count, matched: [...], missing: [...], status, computed_at, entry_date_str, entry_location, event_date, venue, city, region, country, event_type}]}`. |
| POST | `/api/fingerprint/suggestions/dismiss` | Curator-only (403). Body `{lb_number, event_id}` — sets `status='dismissed'`, sticky across rescans. 404 if no matching row. |

### LB Problems (known issues with LB entries)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/lb_problems` | List all lb_problems rows. Optional query param `lb=<int>` to filter to one LB. Returns `[{id, lb_number, notes, added}]`. |
| POST | `/api/lb_problems` | **Curator-only.** Add a problem note. Body: `{lb_number, notes, added?}`. Returns `{ok, id, lb_number}`. |
| PUT | `/api/lb_problems/<id>` | **Curator-only.** Update notes on a row. Body: `{notes}`. Returns `{ok, id}`. |
| DELETE | `/api/lb_problems/<id>` | **Curator-only.** Delete a problem note. Returns `{ok, id}`. |

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
| GET | `/api/quality/<lb>` | Latest Concert Ranker score for one recording from `quality_recording_scores` (`final_score`/`rank_in_family`/`vetoed`/`verdict_text`/`abs_score`/`abs_grade`), plus a `metrics` sub-dict (stereo/mono + width, `clip_fraction`, `crowd_snr_db`, bass/mud/harsh tonal ratios, source-type flags) banded from `quality_recording_metrics.metric_json` via `concert_ranker.scoring.band_metric()`; 204 if never scanned. |
| GET | `/api/attachment/<lb>/<filename>` | Serve cached attachment file |
| POST | `/api/attachments/reconcile` | Mark `entry_files.downloaded=1` for rows present in `site_inventory`. Returns `{updated: N}`. |
| GET | `/api/attachments/cached` | Grouped downloaded files by LB + total entry count. Returns `{entries: [...], total: N}`. |
| POST | `/api/entry/<lb>/scrape` | Trigger scrape of single entry |

### Search
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/search?q=&field=` | `field`: `all`, `location`, `date`, `description`. Returns all matching entries (no limit). As of 2026-07-09 (BUG-245) each entry also carries `taper_known` (bool) — whether `taper_name` canonicalises into `db._TAPER_UNIVERSE`, the same curated set `taper_attribution.py` uses; the gui_next Library grid's taper pill gates on it so unvalidated free-text guesses (rule-12 parser artifacts) never render as if they were attribution-engine output. |
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
| GET | `/api/collection/audit` | Cross-check my_collection against checksums table. Returns `{total, missing_checksums, entries:[{lb_number, folder_name, disk_path, date_str, location, lb_status}]}` for entries with no checksum rows. |
| GET | `/api/collection/export/html` | Download My Collection as a self-contained HTML table. Optional `?cols=` (comma-separated, ordered) picks which columns to render/export — `lb` always included; see `_EXPORT_COLUMN_DEFS` in `app.py` for the full set (base six plus `disk_path`/`confirmed_at`/`source_type`/`lb_category`/`rating`). Falls back to the base six if omitted/invalid. Returns `collection.html` attachment. |
| GET | `/api/collection/export/m3u` | Download My Collection (or a subset) as an M3U playlist of audio files. Walks each entry's `disk_path`; skips missing folders. Optional `?lb_numbers=1,2,3` restricts the export (used by the Library performance lens's "Export show as M3U" action, TODO-150 step 9 follow-up) — returns `show.m3u` when filtered, `collection.m3u` for the full export. |

### Collection Routing & Pipeline Filing (Step 5)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/collection/mounts` | List all mounts with live `online` boolean (concurrent reachability checks) and disk usage. Returns `{mounts:[{id, label, root_path, notes, created_at, online, free, total, used_pct}]}`. |
| POST | `/api/collection/mounts` | Create a mount. Body: `{label, root_path, notes?}`. Normalises `root_path` to POSIX. Returns `{ok, id}`. |
| PATCH | `/api/collection/mounts/<id>` | Update mount fields. Body: any subset of `{label, root_path, notes}`. Returns `{ok}`. |
| DELETE | `/api/collection/mounts/<id>` | Delete mount. Returns 409 if any routes reference it. Returns `{ok}` or `{ok:false, error}`. |
| GET | `/api/collection/routes` | List all year routes joined with mount label. Returns `{routes:[{year, mount_id, sub_path, label, root_path}]}`. |
| POST | `/api/collection/routes/bulk` | Upsert routes for a year range. Body: `{year_from, year_to, mount_id, sub_path}`. Returns `{ok, rows_written}`. |
| DELETE | `/api/collection/routes/<year>` | Remove route for one year. Returns `{ok}`. |
| GET | `/api/collection/routes/preview/<year>` | Dry-run resolve for a year: returns `{ok, year, mount_label, mount_root, sub_path, dest_parent, mount_online, error, error_code}`. |
| POST | `/api/pipeline/file/start` | Start filing one folder into the collection (async, background thread). Body: `{folders:[{path, lb_number, mount_id?}]}` — only the first entry is used. `mount_id`, if given and different from the year-routed mount, overrides the destination mount (same routed sub_path). Returns `{ok, error?, error_code?}` immediately; error codes include `busy`, `src_missing`, `stale_verify` (folder contents changed since its last pipeline check — re-run the pipeline; TODO-205 §3a guard), `no_date`, `no_route`, `mount_offline`, `dest_exists`, `db_error`. Poll `/api/pipeline/file/status` for progress and the final result. |
| GET | `/api/pipeline/file/status` | Poll the running/last filing job started via `/api/pipeline/file/start`. Returns `{running, stage, path, dest, file_mode, lb_number, files_done, files_total, bytes_done, bytes_total, current_file, result}` where `stage` is `idle\|scanning\|copying\|moving\|verifying\|removing\|done\|failed` and `result` (once `running` is false) is `{ok, filed_to, dest, file_mode, error, error_code}`. Whenever data is actually copied (`file_mode=copy`, or a cross-device move that falls back to copy+delete), the copy is SHA-256 hash-verified against the source (`filer.hash_tree`) before the original is removed or the job is reported done; a hash mismatch deletes the bad copy, leaves the source untouched, and returns `error_code: "hash_mismatch"`. |
| POST | `/api/pipeline/file/preview` | Pre-flight resolve without moving files. Same body as `/api/pipeline/file/start` (incl. optional `mount_id`). Returns per-folder `{ok, dest, mount_label, error, error_code}`. |
| POST | `/api/pipeline/run/start` | Start an async multi-folder pipeline job (TODO-205 P2; stages 1–4 + file *resolution* only — the file *move* stays on `/api/pipeline/file/start`). Body: `{folders:[path,...], steps?:[verify\|lookup\|lbdir\|rename\|file], workers?:1–4 (default 2), force?:bool}` (`force` bypasses the P7 folder-state cache; without it, unchanged folders get verify/lbdir served `cached:true` — TODO-205 P7). Folders are grouped by source device (`st_dev`), max one in-flight folder per device, `workers` in flight globally. Returns `{ok, started}` immediately, or `{ok:false, error_code:"busy"}` if a job is running. The synchronous `/api/pipeline/run` keeps working unchanged. |
| GET | `/api/pipeline/run/status` | Poll the async pipeline job. Returns `{running, folders_total, folders_done, in_progress:[path], results:{path: PipelineRow}, errors:[{folder,message}], steps, started_at, cancelled}`. Rows land in `results` as each folder completes. |
| POST | `/api/pipeline/run/cancel` | Cooperatively cancel the async pipeline job: in-flight folders finish, no new folder starts. Returns `{ok, was_running}`. |
| POST | `/api/pipeline/state` | Warm-start (TODO-205 P7): return last-known cached verdicts for a set of folders so the GUI paints buckets immediately after a restart, before any re-run. Body: `{folders:[path,...]}`. Returns `{ok, results:{path: PipelineRow}}` — only folders whose stored fingerprint still matches on disk (design R3) are included, each with a freshly computed `severity`; the file step is appearance-only and re-resolved live on the next run (P8). |

### Collection Integrity Monitor (TODO-111)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/collection/integrity/scan` | Start a background integrity scan. Body: `{mount_id?}` — omit for whole-collection scan. Returns `{ok}` or `409 {ok:false, error}` if a scan is already running. |
| POST | `/api/collection/integrity/scan/cancel` | Request cancellation of the running scan. Returns `{ok}` (false if none running). |
| GET | `/api/collection/integrity/scan/status` | Poll scan progress. Returns `{running, mount_id, folders_done, folders_total, current_folder, result}`. |
| GET | `/api/collection/integrity/scan/history` | Recent scan history. Query param: `mount_id` (optional; omit = whole-collection scans). Returns `{history:[...]}` rows from `collection_integrity_scans`. |
| GET | `/api/collection/integrity/summary` | Per-mount status counts for GUI badges. Returns `{<mount_id>: {pass, content_issue, tag_issue, missing_files, no_lbdir, error}, ...}` (mount_id `"0"` = unmatched). |
| GET | `/api/collection/integrity/status` | Per-LB integrity rows. Query params: `mount_id`, `status` (both optional). Returns `{status:[...]}` rows from `collection_integrity_status`. |

### DB Editor
All routes below accept `?db=` (or body `db` on `/api/dbedit/query`): omitted/unknown →
`losslessbob.db`; `batchverify` → `batch_verify.db`; `tapematch` → `tools/tapematch/observations.db`.
The latter two are always read-only (`_DBEDIT_READONLY_DBS` in `app.py`) — writes 403.

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
| POST | `/api/entry/<lb>/post_forum` | Post a topic to the WTRF forum. Body: `{username?, password?, torrent_id?, subject?, body?}`. Optional `subject`/`body` override the auto-generated values (used when the user edits the preview). Gated by an LBDIR integrity check (`checksum_utils.verify_folder` on the entry's `my_collection.disk_path`, if any) — 400 if status is `fail`/`incomplete`. If no torrent exists, one is auto-generated from the collection folder and added to qBittorrent before posting (qBittorrent failure is non-fatal). Returns `{ok, topic_url, torrent_auto_created?, qbt_auto_add?}`. |
| GET | `/api/entry/<lb>/forum_posts` | List all logged forum posts for an LB entry, newest first. |
| DELETE | `/api/forum_post/<id>` | Delete a forum post log record by id. |
| GET | `/api/forum_posts` | List all logged forum posts across every LB entry, newest first. Includes `date_str` and `location` from entries. |

### Archive.org Upload
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/archive_org/credentials` | Save IA S3 credentials to keyring. Body: `{access_key, secret_key}`. Returns `{ok, label}`. |
| GET | `/api/archive_org/credentials` | Check if IA credentials are stored. Returns `{stored: bool}`. |
| DELETE | `/api/archive_org/credentials` | Clear stored IA credentials. Returns `{ok}`. |
| POST | `/api/archive_org/test` | Test IA S3 credentials. Body: `{access_key?, secret_key?}`. Returns `{ok, error?}`. |
| POST | `/api/archive_org/upload` | Start async upload for one LB. Body: `{lb_number, folder_path, identifier?, collection?, title?, subject?, access_key?, secret_key?}`. Returns `{ok, error?}`. |
| GET | `/api/archive_org/status` | Poll upload progress. Returns `{running, lb_number, identifier, current_file, files_done, files_total, bytes_done, bytes_total, status, error, stop_requested}`. |
| POST | `/api/archive_org/stop` | Request running upload to stop after current file. Returns `{ok}`. |
| GET | `/api/archive_org/uploads` | List upload history rows, newest first. Query param: `lb=<int>`. Returns `[{id, lb_number, identifier, folder_path, files_total, files_uploaded, status, started_at, finished_at, error, date_str?, location?}]`. |

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
| GET | `/api/geocode/status` | Poll batch geocode state: `{running, done, total, errors, skipped, stop_requested, current, stage, succeeded}`. |
| POST | `/api/geocode/stop` | **Curator-only.** Signal the running batch to stop (checked per location + inside 429 backoff); returns current progress dict. |
| POST | `/api/geocode/location` | **Curator-only.** Manually place or correct a coordinate. Body: `{location, lat, lon}`. Sets `manual=1` so the batch geocoder never overwrites it. |
| GET | `/api/geocode/locations` | **Curator-only.** List all rows in `location_geocoded` with geocode status. Returns `[{location, lat, lon, display_name, geocoded_at, manual}]`. |
| POST | `/api/geocode/purge` | **Curator-only.** Purge cached geocoding rows. Body: `{scope: "failed"\|"all"}`. `"failed"` removes source='failed'/lat IS NULL rows; `"all"` removes entire table. Returns `{ok, deleted}`. |

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
| GET | `/api/spectrogram/png` | Serve a spectrogram PNG from an arbitrary absolute path. Query param: `path`. Returns PNG bytes. |

### Rename
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/rename/apply` | Apply folder/file renames on disk and log each to `rename_history`. Body: `{renames: [{old_path, new_path, lb_number?}]}`. Returns `{applied, errors}`. If `lb_number` is given, also best-effort syncs qBittorrent's save path/root folder name (BUG-228). |
| POST | `/api/folder/rename` | Rename a single folder in place (pipeline "rename" step). Body: `{folder, new_name}`. Returns `{ok, new_path}`. Syncs `my_collection`/`folder_lb_link` and, if the folder is qBittorrent-tracked, best-effort syncs qBittorrent's save path/root folder name (BUG-228). |

### Verify (Local Checksums)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/verify` | Verify audio files against `.ffp`/`.md5`/`.st5` in each folder. Body: `{folders:[...]}`. |
| POST | `/api/verify/generate` | Generate `_mychecksums.ffp` and/or `_mychecksums.md5` for each folder. Body: `{folders:[...]}`. |

### LBDir
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/lbdir/check` | Find `lbdir*.txt` in each folder, parse, and verify all listed files. Returns extended result with `lbdir_found`, `lbdir_path`, `lb_number`, plus `length`/`expanded_size`/`cdr`/`wave_problems`/`fmt`/`ratio` per file from shntool_len section. `lb_number` resolves via `my_collection.disk_path` -> `LB-NNNNN` in the folder name -> optional `lb_number_hint` body param (pipeline passes the Lookup step's resolved LB# since LBDIR now runs before Rename). |
| POST | `/api/lbdir/retrieve` | Copy `lbdir*.txt` from `data/attachments/LB-{N:05d}/` to the target folder (triggering a scrape if not yet cached). Looks up LB number from `my_collection` by `disk_path`, then folder name, then optional `lb_number_hint` body param. |
| POST | `/api/lbdir/reconcile` | Preview-only: scan disk files recursively, compute MD5, match against missing lbdir entries. Returns `{results: [{folder, proposals:[{disk_rel,lbdir_rel,md5}], unmatched_lbdir, unmatched_disk, warnings, site_proposals}]}`. Does NOT move any files. `site_proposals` lb_number resolves via `my_collection` -> folder name -> optional `lb_number_hint` body param; each entry is `{site_path, lbdir_rel, md5, expected_md5, matched_by}` where `matched_by` is `'md5'` (exact content match) or `'name'` (filename matches after stripping `LBF-{N:05d}-`, but `md5` != `expected_md5` — site copy is a different lbdir revision, e.g. the manifest's self-checksum or a regenerated DigiFlawFinder report). |
| POST | `/api/lbdir/apply_reconcile` | Apply selected rename proposals from `/api/lbdir/reconcile`. Body: `{folder, renames:[{from,to}]}`. Uses `shutil.move`; creates subdirectories as needed; never deletes. If folder is qBittorrent-tracked, best-effort syncs the new file paths via `renameFile` + recheck (BUG-229) so applied renames don't break seeding. Returns `{applied, errors}`. |
| POST | `/api/lbdir/find_extra` | List files in each folder not referenced in the lbdir MD5 section (lbdir file itself excluded). Returns `{results: [{folder, extra:['rel/path',...], lbdir_rel}]}`. |
| POST | `/api/lbdir/delete_extra` | Permanently delete selected extra files. Body: `{folder, files:['rel/path',...]}`. After deletion, prunes empty subdirectories bottom-up. Returns `{deleted, removed_dirs, errors}`. |
| POST | `/api/lbdir/move_extras` | Move extra files (not in lbdir) to `<folder>/extras/`, preserving relative path structure. Body: `{folder, files:['rel/path',...]}`. Prunes empty subdirs after move. If folder is qBittorrent-tracked, best-effort syncs the new file paths via `renameFile` + recheck (BUG-229) so the move doesn't break seeding. Returns `{moved, errors}`. |
| POST | `/api/lbdir/verified_status` | Return `lbdir_verified_at` timestamp for each folder path. Body: `{folders:[path,...]}`. Returns `{[path]: timestamp\|null}` — null when folder is not in `my_collection` or has never been lbdir-verified. |

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

**Structured-source priority (TODO-167):** before querying Nominatim with the raw
`entries.location` text, `run_batch()` checks three tables in order — via each
entry's ISO date (`entries.date_str` converted by `_entry_date_to_iso()`) — for a
more accurate structured string: `bobdylan_shows` (`_get_bobdylan_shows_location_string`,
most standardized), then `setlistfm_shows` (`_get_setlistfm_location_string`), then
`dylan_performances` (`_get_performance_location_string`) as a last resort. First
match wins; the result's `source` column is set to the matching table name
(`'bobdylan_shows'` / `'setlistfm_shows'` / `'performances'`) instead of `'nominatim'`.

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
| `verify_folder_lbdir(folder_path, lbdir_path)` | Verify all files listed in a `lbdir*.txt` (audio + non-audio), including `length`/`cdr`/`wave_problems` from shntool_len section. Also scans the folder for files not referenced by any lbdir entry (excluding the manifest itself), appends them to `files` with `overall: "extra"`, and reports them in `extra`/status `extra_files`. Files under `extras/` (from `/api/lbdir/move_extras`) and `rename_log.txt` are whitelisted via `_is_reconciled_extra()` — if those are the only unclaimed files, status resolves to `pass` instead of `extra_files`. |
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
`/api/lbdir/check` adds `lbdir_found`, `lbdir_path`, `lb_number` at the top level and `length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio` per file (all six shntool_len fields). Its `status` is one of `pass|fail|missing_files|extra_files|shntool_missing|no_lbdir|no_lb`, where `extra_files` means every lbdir-listed file is present and verified but disk has files not referenced in the lbdir manifest (listed in `files` with `overall: "extra"`).

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
2. `lb_alias` collapse — call `GET /api/lb_alias/resolve`. If all candidates collapse to one canonical, use it automatically. After resolution, all known aliases for that canonical are fetched via `GET /api/lb_alias?canonical_lb=<lb>` and included in the proposed folder name.
3. Fall back to `multiple_ids` state (cyan) for manual resolution.

**Multi-LB folder naming convention** (alias-resolved folders):
- Format: `{original_name}-{canonical}-{alias1}-{alias2}` where each LB token is `LB-NNNNN` (no zero-padding on the number itself, e.g. `LB-12345`).
- Order: canonical first, then aliases in ascending numeric order.
- Example: a folder resolved to canonical LB-12345 with alias LB-67890 gets suffix `LB-12345-LB-67890`.
- The LB Found display column shows all LBs separated by ` + ` (e.g. `LB-12345 + LB-67890`) to distinguish from unresolved multiple IDs (which use `, `).
- `_lb_in_name` / `_has_wrong_lb` / `_row_state` all operate on the canonical LB only, so state detection remains correct.

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
- Live stats label: Public / Private / Missing / Nonexistent / Max LB / Overrides / Needs review / Public-no-checksums counts (from `GET /api/lb_master/stats`).
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

## GUI (Next): Electron/React Frontend (`gui_next/`) — PRIMARY GUI

Second-generation GUI (primary, merged into main 2026-05-29) built with **Electron + React + TypeScript** (Vite + electron-vite). Communicates with the same Flask backend on port 5174 via `fetch()`. Preload bridge (`preload/index.ts`) exposes typed IPC handlers (`openPath`, `pickFile`, `pickFiles`, `pickDir`, `pickFolders`). All screens are registered in `App.tsx` and routed via a sidebar nav. **All future development happens here.** The legacy `gui/` PyQt6 frontend is frozen — it receives no new features or bug fixes.

### Screens (16 fully wired as of 2026-06-12)

| Screen | File | Status |
|--------|------|--------|
| ScreenHome | `screens/ScreenHome.tsx` | Done — dashboard, live stats, activity log, flat-file update; first-run onboarding (TODO-217): auto-opens `components/OnboardingWizard.tsx` (4-step modal: master install → sitedata install → mounts/pipeline nav → done + `/api/derived/recompute`) once per launch when `entries_count == 0`, plus a setup-checklist card while `/api/onboarding/status` `complete == false` |
| ScreenSetup | `screens/ScreenSetup.tsx` | Done — all 16 handlers: credentials, purge, import/export, master, data packages |
| ScreenMounts | `screens/ScreenMounts.tsx` | Done — storage mounts, year routing, filing mode, preview tester (split out of ScreenSetup) |
| ScreenCollection | `screens/ScreenCollection.tsx` | Done — sortable columns, wishlist, forum, torrents, duplicates, batch actions |
| ScreenSearch | `screens/ScreenSearch.tsx` | Done — virtual table, sort, group-by-year, CSV export, column picker, saved views |
| ScreenLibrary | `screens/ScreenLibrary.tsx`, `components/library/actions.tsx`, `components/library/DetailPanel.tsx` | In progress (TODO-150) — "By performance \| By recording" lens toggle (defaults to performance). Both lenses share the same merged `RecordingRow[]` (from `/api/search` + `/api/collection/prefetch` + `/api/library/badges` — the last merged by `lb_number` for pick/curated/taper badges, TODO-212); the performance lens additionally fetches `/api/library/performances` + `/api/tapematch/families` and groups recordings by show → TapeMatch family → member. The recording lens renders ★ recommended / curated / `absGrade` / confirmed-taper (upgrading the raw taper pill) badges inline; the performance lens's view menu includes a combined "Any curated pick" (`curatedAny`) filter alongside the per-curator ones. Each lens has its own facet rail and virtual year-grouped table. Right-click context menu and a checkbox bulk-select bar (recording lens: Create torrent/Add to qBittorrent/Update location/Remove) are wired in via `actions.tsx`'s shared registry. Selecting a row opens a zoned detail panel (`DetailPanel.tsx`: ActionBar/ShareSeed/AssetStrip/Setlist, step 8; recording lens also has a Quality tab showing LB Rating + Concert Ranker AI Quality Index side by side, a Picks tab (show-pick rank/score + `EvidenceList`, lazy `/api/picks/for/<lb>`), and a Taper tab (attribution tier/conflict + `EvidenceList`, lazy `/api/tapers/attributions/<lb>`, confirm/reject buttons in curator mode) as a third column on either lens; TODO-162 P5b added an Olof tab on both lenses (Still On The Road setlist with encore/credits/annotations/take status, NET + year concert #s, recording info, notes, BobTalk quote, chronicle diary entries, circulation provenance, and a per-copy setlist comparison via `POST /api/olof/compare`) — gated on `/api/olof/status` `events > 0` (react-query `staleTime: Infinity`), so it never renders on installs without local Olof data. Live at `/library`, sidebar nav item "Library" (featured, top of the Library group, above My Collection) — step 9. Performance lens show rows and the detail panel render an "Unconfirmed" pill for degraded (`confirmed: false`) shows recovered from the `lb_category='unknown'` bucket (TODO-151). `m3u` (Export show as M3U) is wired for performance rows. `sources`/`notify` row actions and the TapeMatch family `note` field remain unexposed (no backend/UI to wire to). i18n pass (step 10) **done** — all in-screen strings extracted to the `library` namespace in `locales/*.json` and the three files converted to `t()` (the shared action registry takes a `TFunction` param since the builders are plain functions; counts pluralised via `_one`/`_other` keys); the 5 non-English locales filled via DeepL. |
| ScreenBootlegs | `screens/ScreenBootlegs.tsx` | Done — year/CDs filters, catalog browser, CSV export |
| ScreenTapeMatch | `screens/ScreenTapeMatch.tsx` | v1 (2026-07-10, TODO-170 closed) — read-only TapeMatch review at `/tapematch` (Library nav group): date rail (`/api/tapematch/dates`; all/conflicts/no-analysis views + date/location filter), per-date similarity-% matrix (`/api/tapematch/pairs`; heatmap tint, raw corr/emb/fp in tooltip, "n/c" for never-compared), family chips (F1/F2… from `/api/tapematch/families` fam_id groups), collapsible lazy `analysis.md` viewer (`/api/tapematch/analysis`), crawl-status strip (`/api/tapematch/crawl/status`, 30 s poll). v2 (2026-07-11, TODO-215 closed): matrix-cell JudgmentPanel writing `human_judgment`/`human_notes` via `POST /api/tapematch/pairs/judgment`, crawl start/stop buttons on the status strip, LB deep-links (`LbLinkButton` → `/library?lb=<n>`, consumed one-shot by ScreenLibrary). v3 (2026-07-12, TODO-231 closed): AbPlayerPanel next to JudgmentPanel — position/duration inputs, `POST /api/ab_clip` load, two hidden `<audio>` elements started together and (un)muted for an instant A/B toggle (no reload/reseek); inert with a notEligible pill when the selected pair's `ab_eligible !== true`. |
| ScreenSongs | `screens/ScreenSongs.tsx` | Song-centric browser at `/songs` (Library nav group; 2026-07-11, TODO-230). Debounced song search rail (`/api/songs?q=`), per-song performance table (`/api/songs/performances`): date, venue/city, event-type pill, take status, encore marker, recordings as LB deep-link buttons (pick pill for `pick_rank===1`, abs_grade letter). Sort: date (default) or best-first (rank-1 recording's grade). Curator-gated canonical-rename → `POST /api/songs/alias` (hidden for non-curators via `useSettingsStore.curatorMode`). |
| ScreenFingerprint | `screens/ScreenFingerprint.tsx` | Setlist-fingerprinting curator review queue at `/fingerprint` (Curator nav group, gated; 2026-07-13, TODO-225). "Scan for matches" button runs `POST /api/fingerprint/scan`; expandable-row table (`GET /api/fingerprint/suggestions`) lists each suggestion's LB, raw entry date/location, matched show (date/venue/type pill), score %, matched/total song count, and an expand toggle revealing matched vs. missing song lists. Status filter chips (pending/dismissed/all). Curator-only Dismiss button → `POST /api/fingerprint/suggestions/dismiss`. Suggestions are never auto-applied — the curator hand-edits the entry's date via DB Editor after reviewing a match. |
| ScreenThemes | `screens/ScreenThemes.tsx` | Done — mode/density/accent, frame theme (palette) + card style (framed/flat), typeface/font-size, custom color tokens |
| ScreenPipeline | `screens/ScreenPipeline.tsx` | Done — folder queue, 5-step workflow (verify/lookup/lbdir/rename/collect), bulk-actions menu, Auto-run + Auto-rename toggles |
| ScreenQuickLookup | `screens/ScreenQuickLookup.tsx` | Done — paste/clipboard/drop zone, per-row checksum results table |
| ScreenLookup | `screens/ScreenLookup.tsx` | Done — 4-source input, summary + detail tables |
| ScreenVerify | `screens/ScreenVerify.tsx` | Done — folder verify/generate/retrieve workflow |
| ScreenRename | `screens/ScreenRename.tsx` | Done — consumes lookup results, applies bulk renames |
| ScreenLBDIR | `screens/ScreenLBDIR.tsx` | Done — 4-pane check/retrieve/reconcile/extras |
| ScreenAttachments | `screens/ScreenAttachments.tsx` | Done — LB rail, file list, text/HTML/image/binary viewer |
| ScreenSpectrograms | `screens/ScreenSpectrograms.tsx` | Done — tool dots, batch generate, PNG viewer |
| ScreenMap | `screens/ScreenMap.tsx` | Done — filter rail + browser map launcher |

### Shared stores (`lib/`)

| Store | Purpose |
|-------|---------|
| `folderQueueStore.ts` | Canonical folder list shared across Pipeline, Verify, LBDIR, Spectrograms |
| `lookupStore.ts` | Lookup results passed to Rename |
| `verifyStore.ts` | Verify job state |
| `lbdirStore.ts` | LBDIR job state |
| `spectrogramStore.ts` | Spectrogram job state |
| `attachmentsStore.ts` | Attachments viewer state |
| `scraperLogStore.ts` | Scraper screen per-tab live log lines (module-level, survives tab navigation) |
| `tokens.ts` | CSS design tokens (colors, spacing, typography) |

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

**Frozen as of 2026-07-07.** This table is historical only — no new rows are added. The
sole narrative change log is now `CHANGELOG.md` (rolling ~2-month window) plus
`CHANGELOG_ARCHIVE.md` (older entries).

| Date | Change |
|------|--------|
| 2026-07-05 | Docs restructure for context efficiency: `.claude/CLAUDE.md` rewritten (grep-first reads, skill delegation); nested rules added at `gui/CLAUDE.md` + `tools/tapematch/CLAUDE.md`; `CHANGELOG.md` now rolling ~2-month window with 2026-05 entries moved to new `CHANGELOG_ARCHIVE.md`; PROJECT.md gains this `## Contents` index. |
| 2026-07-04 | TapeMatch `addon_links.rule_d` SHIPPED (both-convention nmfp embedding merge, t_emb 0.75): observations.db `pairs` gains `emb_score`/`emb_score_global` (REAL nullable, idempotent ALTER); `verdict.py` `_rule_d_emb_both`; `regression.py` gains `score --set PATH` + additive-passthrough (`_passthrough_with_rule_d`). New label sets/tooling: `regression_set_v2.json` (3 objective negative flips; frozen v1 untouched), `fn_label_census.py`, `emb_fullset_eval.py`, `persist_emb_scores.py`. Frozen-set result: recall 41.8%→43.4% at abs fp=9 (zero new FP); v2 43.5% at fp=6. See `tools/tapematch/TIER_B_FULLSET_REPORT.md`. |
| 2026-07-04 | Tier B nmfp harness extended beyond the pilot eval set to the full frozen set: new `tools/tapematch/build_fullset_worklist.py` (every frozen negative + every currently-FN frozen positive with corr<0.05, sourced/derived via imported `regression.py`/`tapematch.verdict` logic — not reimplemented) writes `fullset_pairs.json`/`fullset_sources.json` (+ `--pilot N --seed 42` restricted variants) in the `embed_eval_set.json` schema so `nmfp_embed.py --eval-set` consumes them unchanged. New `tools/tapematch/emb_score_pairs.py` scores any such pairs file against `embed_cache/` by importing `embed_eval.py`'s existing `_load_source`/`_pair_score` (tol=2s aligned + tol=0 global), writing `<stem>_scores.json`. `nmfp_embed.py` docstring-only update (documents the pre-existing `--eval-set` option); `--workers` was evaluated and deliberately not added (TF/essentia state after model+checkpoint load is not fork-safe). Read-only against `observations.db`; no schema/config/verdict changes, no audio/model runs. |
| 2026-07-03 | BUG-235 fix: `tools/tapematch/tapematch/trim.py` `performance_envelope` gains a dynamic-range guard (`trim.min_dynamic_range_db`, new config key, default 10.0) — skips trim and keeps the full recording when whole-source energy contrast (p90-p10) is too narrow to trust (heavily normalised/compressed sources caused the fixed p10+6dB energy gate to chatter, cutting 30-70% of a recording as spurious "crowd padding"). Found live via 2025-11-16/17 Glasgow test runs. New `tools/tapematch/tests/test_trim.py`. No losslessbob.db schema/route changes. |
| 2026-07-03 | CC_TAPEMATCH_ADDON effort CONCLUDED — Tier C (Task 7) rejected. New isolated env `tools/tapematch/.venv-emb` (torch 2.6.0+cu124) + package `tools/tapematch/embedding/` (config.yaml, melspec.py, augment.py — 7-op AugmentChain, model.py — ConvEncoder 587,712-param contrastive encoder + symmetric NT-Xent, data.py — hard-neg mining from `observations.db`, train.py, infer.py, aug_sanity.py, ckpt/tierc.pt trained checkpoint). Trained 30 epochs/7170 steps (69.8 min) on 61,253 same-show-hard-negative windows; Gate 7.3.1 (aug-sanity) passed, Gate 7.3.2 (decisive TP/TN separation) REJECTED (gap -0.017/-0.074, worse than Tier B's pretrained-nmfp -0.034 baseline) — no verdict/schema/route changes shipped. Closes CC_TAPEMATCH_ADDON at the unchanged **recall 41.6% / precision 98.6% / fp=9**. New audit tooling: `tools/tapematch/dump_calibration_audit.py` + `build_calibration_audit_html.py` → `calibration_audit.json`/`.html` (self-contained interactive table of all 2965 frozen pairs' truth label vs current verdict vs LB catalog relation-text, for manually auditing the `lb_says_same` ground truth — a meaningful slice of which is known to be curator label noise). No losslessbob.db schema/route changes. |
| 2026-07-02 | CC_TAPEMATCH_ADDON Task 3 (Tier A): spectral-ratio stationarity. `match.py` gains `spectral_ratio_stationarity` (windowed-coverage grid, own `spectral_stationarity.*` knobs; per-window log-mel ratio via `librosa.filters.mel`, capped at `min(hf_ceiling_a, hf_ceiling_b, 0.45*sr)`, quiet-frame excluded per side; `1 - mean_band(std_w(R_w))/stationarity_norm_db` clipped [0,1], `None`-safe below `stationarity_min_windows`). `observations.db` `pairs` gains nullable `spec_stationarity` REAL (CREATE + idempotent ALTER; `insert_pairs` persists it). `verdict.py` `METRIC_KEYS` gains the column but **no OR-path** — conjunctive-only per spec, combination rules deferred to Task 5's `addon_links`. New config block `spectral_stationarity:` (**enabled=false**, uncalibrated). `cli.py`'s per-source lineage pre-pass (`hf_ceiling`/`noise_floor`) moved earlier — unconditional, pure reordering — so the cross-pair loop can read it; scores `spec_stationarity` gated on `spectral_stationarity.enabled` (zero cost while dormant). 185 tests green (7 new stationarity + 1 new verdict-equivalence + 177 prior). Not yet calibrated on real audio. No losslessbob.db schema/route changes. |
| 2026-07-02 | CC_TAPEMATCH_ADDON Task 2 (Tier A): shared-flaw event fingerprint. `match.py` gains `extract_flaw_events` (per-source dropout/click/cut timeline — content-blind, lineage-only) and `flaw_match_score` (pair scoring under speed-mapping, `None`-safe below `flaw_min_events`). `observations.db` `pairs` gains nullable `flaw_match_score` REAL, `flaw_n_events_a`/`flaw_n_events_b` INTEGER (CREATE + idempotent ALTER; `insert_pairs` persists them). `verdict.py` OR-path (gated `flaw_fingerprint.enabled`, inert on NULL — same dormant pattern as the triplet path). New config block `flaw_fingerprint:` (**enabled=false**, uncalibrated). `cli.py` computes flaw timelines per source (gated, zero cost while disabled) and persists per-source event count + serialized timeline into the run JSON `sources` section (not the DB — variable-length). 177 tests green (10 new + 167 verdict-equivalence, 3 new proving byte-identical inert behaviour). Not yet calibrated on real audio. No losslessbob.db schema/route changes. |
| 2026-07-02 | CC_TAPEMATCH_ADDON Task 1 (Tier 0): new `tools/tapematch/audit_fn.py` recomputes the current corr<0.05 FN population (859 pairs, via `verdict.cluster_verdicts`), draws a stratified 60-pair sample (speed-corrected/speed-unknown/staircase x hf_ceiling-gap), and assesses each via a transparent `label_assessment` heuristic (explicit "different recording" text, taper-name conflict, duration-ratio mismatch, explanatory lossy/band-limited lineage, throwaway 4-band envelope-corr quick check). Writes `tools/tapematch/FN_AUDIT_REPORT.md`: label-noise rate 36.7% (22/60, Wilson 95% CI 25.6–49.3%) → **re-based recall ceiling ~80.0%** (CI 73.1–86.0%). `observations.db` `pairs` gains nullable `label_suspect` INTEGER (CREATE + idempotent ALTER in `tapematch_session.open_obs_db`; NULL=not-assessed, 1=suspect — 22 rows flagged). Frozen-set labels (`regression_set.json`) not edited. No losslessbob.db schema/route changes. |
| 2026-07-02 | TapeMatch recall-recovery Tasks 5–7 (CC_TAPEMATCH_FIXES) + Phase-2 verdict. `match.py`: `estimate_ratio_v2` (prior-centered, confidence-reporting; old `estimate_ratio`→`estimate_ratio_v1_deprecated` for A/B), `duration_ratio_prior`, `pitch_ratio_pyin` (Tasks 5/6.2), and a DORMANT ratio-invariant triplet fingerprint (`triplet_hashes`/`triplet_window`/`_fingerprint_peaks`, Task 7). `align.py`: `residual_ppm_from_lag_curve` (r²-guarded, Task 6.1) on the primary path only. `cli.py`: v2 confidence gate → `speed-unknown` routing. `verdict.py`: triplet OR-path (inert when disabled). `observations.db` `pairs` gains nullable `fp_triplet_score` (CREATE + idempotent ALTER; `insert_pairs` persists it). New config keys `align.ratio_confidence_min=6.0`, `align.pyin_fallback=true`, `fingerprint.triplet.*` (**enabled=false**). New `calibrate_triplet.py`, `RECALL_RECOVERY_REPORT.md`. **Triplet REJECTED** (same-show pairs collide, made 5 false merges → disabled). Final precision-safe recall **41.6% / precision 98.6% / fp=9** (vs 38.3%/98.2% audit baseline); 93% of FN are non-correlating even when correctly speed-aligned → >80% needs the out-of-scope contrastive-embedding model. 175 tests green. No losslessbob.db schema/route changes. |
| 2026-07-02 | TapeMatch recall-recovery Task 1 (CC_TAPEMATCH_FIXES): new `tools/tapematch/tapematch/verdict.py` (single source of truth for the pairwise clustering decision — `pair_links`, conditional `fp_threshold`, lo-fi `_effective_hiss_median`, transitive `cluster_verdicts`, `load_lineage_pairs`) and `tools/tapematch/regression.py` (freeze/score/score --cached harness reproducing the labeled-pair baseline). `match.cluster()` gains a `link_fn` predicate; `cli.py` routes clustering through `verdict.pair_links`. `observations.db` `pairs` table gains nullable `windowed_frac`/`hiss_frac`/`hiss_median`/`fp_score`/`nyquist_capped_a`/`nyquist_capped_b` (CREATE + idempotent ALTER in `open_obs_db`; populated by `insert_pairs`). New config keys `fingerprint.cluster_threshold_staircase/_curator`, `secondary_match.hiss_merge_median_lofi`/`hiss_lofi_ceiling_hz`. New `tools/tapematch/rerun_cat3.py` (Task 2). Recovered `observations.db` from Trash (was 0-byte stubs). No losslessbob.db schema/route changes. |
| 2026-07-01 | Quality tab gains Concert Ranker raw-signal visualizations: `GET /api/quality/<lb>` (`backend/app.py`, new `_quality_metrics_for()` helper) reads `quality_recording_metrics.metric_json` for the same scan and bands stereo width/mono, `clip_fraction`, `crowd_snr_db`, bass/mud/harsh tonal ratios, and source-type flags (lossy/minidisc/32k DAT/cassette/TV-band) into human labels via `concert_ranker.scoring.band_metric()` + `config.resolve_band_set()` (same thresholds `verdict_text` already uses); `DetailPanel.tsx` gains `QualityMetricsPanel` (tone-colored `MetricBar` meters + `FlagChip` pills) rendered below the LB Rating/AI Quality Index tiles. New i18n keys `library.quality.metrics.*` in all 6 locales. No schema changes. |
| 2026-07-01 | New "Quality" page on the library detail panel: `GET /api/quality/<lb>` (`backend/app.py`) reads the latest Concert Ranker scan row from `quality_recording_scores`; `gui_next/.../DetailPanel.tsx` `RecordingDetailPanel` gains a fourth "Quality" tab (owned rows only) showing bold `Fact` cards for the catalog LB Rating and Concert Ranker's AI Quality Index (`abs_grade` + `abs_score`/100) side by side, plus `verdict_text`. New i18n keys `library.panel.tabQuality` / `library.quality.*` in all 6 locales. No schema changes (reuses existing `quality_recording_scores`). |
| 2026-07-01 | BUG-231/232: `backend/wtrf_scraper.py` WTRF matcher gains a deterministic checksum body-search (primary lookup; `_search_board` gained `subject_only` flag, `_checksum_search_terms` helper) that resolves straight to the correct taper's post regardless of topic-title date format; date-variant subject search demoted to fallback and now unions across all variants. Cross-recording guard disqualifies candidates whose body checksums resolve to a different lb_number (new `backend/db.py` `lookup_checksum_owners()`), ending false "ambiguous" ties. No schema/route changes. |
| 2026-07-01 | BUG-219: `gui_next/src/renderer/src/screens/ScreenLibrary.tsx` gains a module-scope `useLibraryFilterStore` (zustand) holding both lenses' search/filter state, so it survives the screen unmounting on navigation instead of resetting via local useState. No schema/route changes. |
| 2026-07-01 | BUG-220: `/api/scrape/start` (`scrape_start`, `backend/app.py`) now queues gap LB numbers (no existing checksums row within [start_lb, end_lb]) into the actual scrape thread, not just an `insert_missing_entry()` stub — private-status gaps still excluded. No schema/route-signature change. |
| 2026-06-30 | BUG-228: `/api/rename/apply` and `/api/folder/rename` (`backend/app.py`) now best-effort sync qBittorrent's save path/root folder name via `backend.filer._sync_qbt_location()` after a successful rename, so a torrent already tracked in qBittorrent keeps seeding instead of erroring on missing files until an unrelated later "file" step happened to fix it. `relocate_tracked_torrent()`'s DB-tracked branch (`backend/qbittorrent.py`) now also calls `rename_torrent_root()`/`recheck_torrent()`, matching its fallback branch. No schema/dependency changes. |
| 2026-06-30 | TODO-193: `backend/qbittorrent.py` `add_torrent_for_download()` gains a `paused` param (sends `paused`+`stopped` form keys on add); `tools/wtrf_fetch_missing.py` gains `--paused` CLI flag so batch WTRF fetches can queue matches in qBittorrent without starting the download. Used for a full batch run against the 220 missing LB entries above LB-16000 (113 paused-added, 22 downloaded-only, 85 unmatched — see `wtrf_skipped_review.md`). |
| 2026-06-30 | TODO-183: Concert Ranker — true 5-9 kHz sibilance. `concert_ranker/features.py` `_sibilance_native()` computes `sibilance_ratio_db`/`sibilance_crest` from `NativeProbe` (native-rate, per-window PSDs) instead of the bulk-rate averaged-PSD approximation, wired into `extract_hf_native()`. No schema/route changes — new keys ride in the existing `metric_json` blob. Not yet in `QUALITY_MODEL` (needs a calibration run against real scanned audio). |
| 2026-06-29 | TODO-183: Concert Ranker filtering + floors, scan_id=18 (full-library rescan post hum-fix). Non-concert categories (studio/interview/tv/compilation/rehearsal/radio/soundcheck) and private/missing/non-public entries excluded from worklist + rerank (`concert_ranker/cli.py` `_filter_non_concerts()`/`_filter_non_public()`); xx-date entries reclassified to 'compilation' (`backend/db.py` `classify_entry_categories` tier 0). `hf_ceiling_hz` forced back into `QUALITY_MODEL` (10th predictor). New `_HF_FLOOR_RULES`/`_apply_hard_floors()` in `quality_score.py` caps rank post-prediction (hf_ceiling_hz < 4000 Hz -> D-, < 6000 Hz -> D). `_MIN_CONCERT_DURATION_SEC` = 1800s gate drops sub-30-min recordings. Final scored set 13752 rows (was 16099). |
| 2026-06-27 | CC_LINEAGE_PARSE: New USER table `entry_lineage` in `backend/db.py` (schema DDL + USER_TABLES). Lineage regexes (`_SAME_RE`/`_DIFF_RE`/`_DERIVED_RE`/`_BETTER_RE`) now canonical in `backend/db.py` and imported by `tapematch_session.py`. New functions: `extract_lb_references()`, `_normalise_taper()`, `_compute_parse_confidence()`, `upsert_entry_lineage()`, `get_lineage()`. New `tools/parse_lineage.py` batch script. `GET /api/lineage/<lb>` route. `tests/test_lineage.py` (8 tests). |
| 2026-06-24 | TODO-181: New MASTER tables `curated_lists` / `curated_list_entries` (schema v9->v10) for curator "best of" picks. `tools/import_curated_lists.py` (stdlib-only) imports carbonbit's `data/lists/FLglist.xlsx` (4503 entries) and 10haaf's `data/lists/dylan_boots.zip`+`years.zip` (7572 entries, unioned across both archives). DB + import only — no API routes or Library-screen filter yet. |
| 2026-06-24 | TODO-183: Concert Ranker calibrated against real audio (4 rounds + overnight 697-show decade scan). `concert_ranker/features.py` de-confounded harsh/hiss (level-independent) and reworked hum (harmonic comb) + dropout (isolated-discontinuity, worst-track aggregation); `config.py` bands fitted from the corpus and made **per-decade** (`DECADE_BANDS` 1960s-2010s — each recording banded against its own era; `scoring`/`families` thread the decade; `cli --by-decade` sampler). Calibration scans stored as `quality_scans` (scan_id 6 = current basis). hiss is now the strongest AUD quality predictor (rho -0.64). |
| 2026-06-23 | TODO-183: Concert Ranker v1. New repo-root `concert_ranker/` package (audio quality scoring) — the pre-built scoring brain (`config`/`scoring`/`features`/`calibrate`/`audio/cache`) wired to the real machine: `lb/repo.py` (USER-table persistence, scan-once raw metrics + derived scores), `lb/source_type.py` (SBD/AUD/FM/UNKNOWN), `lb/commentary.py` (commentary mining), `audio/io.py` (ffmpeg decode), `scan.py`/`runner.py` (per-folder scan + staging loop, crash=scrap), `families.py` (rank within `recording_families`, standalone fallback), `calibration.py` (rating×source_class fit harness), `cli.py` (`scan`/`calibrate`/`rerank`/`report`). New USER tables `quality_scans` / `quality_recording_metrics` / `quality_recording_scores` in `backend/db.py`. No new deps. `tests/test_concert_ranker.py`. |
| 2026-06-22 | `tapematch_family_meta` gained `review_flag`/`review_reason` (schema v8->v9); `backend/tapematch_sync.py` now parses each date's `analysis.md` "## Verdict:" line and upserts the flag/reason so analysis-write-up "needs review" calls are queryable via `GET /api/tapematch/families` and surfaced as a warn-tone "Needs review" Pill in the Library recording lens. |
| 2026-06-22 | TODO-151: Unified Library visual refinement (instructions/library Pixel Spec). `lib/tokens.ts` gained nine `--t-*` type-scale role variables (display/title/strong/body/meta/label/micro/mono/mono-sm), four `--w-*` weights (reg/med/semi/bold) and `--track-eyebrow`, emitted in `applyTheme()` and scaled by base fontSize (legacy `--lbb-fs-*` retained for other screens). `screens/ScreenLibrary.tsx`: all raw fontSize/fontWeight literals replaced with role vars; performance-table column model reworked (dead 32px spacer removed, fixed widths Date 104·Show 345·Tour 155·Families 116·Recs 52·★ 46·Coverage 112, trailing flex spacer); recording ★ col 54→48; both summary strips height:40·nowrap (fixes BUG-217). `components/library/DetailPanel.tsx`: both detail panels converted from flat scroll to pinned identity + `TabStrip` + swappable pane (perf tabs Overview/Recordings/Setlist/Seed&Share; recording tabs Overview/Assets/Seed&Share; scroll resets on tab change); `ShareSeedZone`/`AssetStripZone` gained `hideLabel`. `components/primitives.tsx`: `Pill` routed to `--t-micro`/`--w-semi`. New i18n keys `library.panel.tab{Overview,Recordings,Setlist,Assets,Share}` in all 6 locales. Fixed BUG-218 (★ clip). |
| 2026-06-20 | TODO-155: implemented the `design_handoff_pipeline_icons` handoff in gui_next — new `components/pipeline/PipelineIcon.tsx` (`<PipelineIcon stage status size />`, `PipelineGlyph`, `PIPELINE_STAGES`, `PipelineStage`/`PipelineStatus` types) for the five-stage Verify→Lookup→Rename→LBDIR→Collect tiles (Option D tactile tile · Pulse animation · Vivid palette). Tile geometry, radial-gradient fill, bevel/lift shadows, and the `pipeRing`/`pipeSheen` keyframes (wrapped in `prefers-reduced-motion: no-preference`) added to `index.css` under `.pipe-tile*`; derived shades via `color-mix(in oklab,…)` off a single `--pipe-mid` per status. Wired in: `StageNode` in `PipelineParts.tsx` now renders a `PipelineIcon` tile (was a 22px circle), so both the per-row `StageTracker` (queue table) and full-width `StageStepper` (detail view) in ScreenPipeline show the tiles; `STAGE_TO_TILE`/`STATE_TO_TILE` maps bridge the tracker's `file`/`mute` vocabulary to `collect`/`pending`, and running stages now Pulse instead of spin. |
| 2026-06-18 | TODO-150 loose ends tied up: (1) TODO-151 audit — root cause was `_PERF_CATEGORY_MAP` missing `GUEST`/`NET`/`SIDEMAN` mappings for `dylan_performances` categories, so guest-spot/Never-Ending-Tour dates fell through to 'unknown' instead of 'concert'; fixed + backfill version bumped to `_v2` to auto-reclassify existing installs (concert 14092→14329). `get_performances()` also gained a `dylan_performances.venue` fallback and a `confirmed: false` degraded-row path for the remainder (~19 shows now, down from an earlier 198-show heuristic-only estimate); GUI renders an "Unconfirmed" pill on these. (2) `m3u` performance-row action wired: `/api/collection/export/m3u` gained an optional `lb_numbers` filter, `buildPerformanceActions()`/`ScreenLibrary.tsx` wired the handler. `sources`/`notify` actions and the TapeMatch family `note` field stay unexposed — no backend/UI to wire to (would be new features, not loose ends). i18n (step 10) deferred per user decision — English-only is fine for now. |
| 2026-06-18 | TODO-150 phase 9: `ScreenLibrary.tsx` wired into real nav/routing — `App.tsx`'s temporary `/library-dev` route replaced with `/library`; `AppShell.tsx`'s `NAV_GROUPS` Library group gained a new featured "Library" item (id `library`, icon `library`) above "My Collection", showing the existing "NEW" badge. No i18n changes needed — `appShell.nav.library` already existed (reused from the group-header translation) in all 6 locales. i18n for in-screen Library strings (step 10) still open. |
| 2026-06-18 | TODO-150 phase 8: new `components/library/DetailPanel.tsx` — `RecordingDetailPanel`/`PerformanceDetailPanel`, zoned per the design handoff (header, ActionBar, ShareSeed, AssetStrip, optional Setlist). ShareSeed's unified activity log is built client-side from `/api/collection/prefetch`'s existing `torrents`/`forum_posts` arrays (no new endpoint); AssetStrip adds a bulk `/api/attachments/cached` query and a lazy per-row `/api/spectrogram/list` check. `ScreenLibrary.tsx`: both lenses render the panel as a third column on row selection (recording lens reuses its existing `selectedLb`; performance lens adds `selectedMemberLb` alongside `selectedId`, member-row selection taking precedence). |
| 2026-06-18 | TODO-150 decision: `get_performances()` filters to `lb_category = 'concert'` — non-concert recordings (radio/tv/interview/studio/rehearsal/soundcheck/compilation/other/unknown) no longer get grouped into bare show rows; recording lens unaffected. See TODO-151 to audit `lb_category` accuracy now that it gates lens membership. |
| 2026-06-18 | TODO-150 phase 7: new `components/library/actions.tsx` — shared Library action registry (`LibAction` vocabulary, `buildRecordingActions()`/`buildPerformanceActions()`, grouped `ActionMenu`/`useActionMenu()`, `BulkActionBar`); `components/primitives.tsx` gained shared `Toast`/`ConfirmDialog` (ported from ScreenCollection.tsx's local copies). `ScreenLibrary.tsx`: recording lens gained a checkbox column + bulk bar (Create torrent/Add to qBittorrent/Update location/Remove, batched); right-click context menu wired into both lenses (recording rows, performance show rows, performance member rows). All handlers reuse ScreenCollection.tsx's existing backend endpoints — no backend changes. `sources`/`notify`/performance `m3u` action ids omitted (no backend/UI to wire to yet). |
| 2026-06-18 | TODO-150 phase 6: `ScreenLibrary.tsx` gained a performance lens — "By performance \| By recording" toggle, new `PerformanceLensView` merging `/api/library/performances` + `/api/tapematch/families` into the recording lens's existing `RecordingRow[]` (shared by reference, not re-derived), `familiesOf()`/`rollupOf()` TS port of the design handoff's family-clustering/coverage helpers, show → family → member expandable virtualized table with its own facet rail. No detail panel/bulk bar/context menu yet (steps 7/8). |
| 2026-06-18 | TODO-150 phase 5: new `db.get_performances()` + `GET /api/library/performances` — groups `entries` by `(date_str, location)` into shows, cross-referencing `bobdylan_shows`/`setlistfm_shows`/`bootleg_titles` for venue/tour/setlist-key/track-count/title. Dedicated backend aggregate endpoint per the locked TODO-150 decision (not client-side groupBy, not bolted onto `/api/search`); family data stays a separate client-side merge of `/api/tapematch/families`. |
| 2026-06-18 | TODO-150 phase 4: new `ScreenLibrary.tsx` recording lens — flat LB#-keyed table, client-side adapter merging `/api/search` (catalog incl. `source_type`) with `/api/collection/prefetch` (collection/fingerprints/wishlist/duplicates/xref), facet rail (scope/decade/status/rating/source/health), virtualized year-grouped table. No backend changes. Deliberately bare: no context menu/detail panel/bulk bar (steps 7/8) and no nav entry yet — reachable via a temporary `/library-dev` route in `App.tsx` (same pattern as `/quicklookup`). |
| 2026-06-18 | TODO-150 phase 3: `entries.source_type` TEXT column added (MASTER_SCHEMA_VERSION 7→8) for the Library design doc's `src` field (Soundboard/Audience/FM-Pre-FM/Master/Mixed). Curator-edited only — never heuristically parsed/backfilled, unlike `taper_name`/`source_chain`/`lb_category`. Wired into `search_entries()`, `get_entries_by_lb_list()`, `get_collection()` read paths. |
| 2026-06-18 | TODO-150 phase 2: theme engine additions (unified Library design handoff doc 01) — `tokens.ts` ThemeOptions gained `palette` (frame theme: slate/blue/purple/green/graphite, tints surfaces over the mode) and `cardStyle` (`framed`\|`flat`, default `flat`); `applyTheme()` now resolves `mode: 'system'` via `getSystemMode()` before indexing any color table, fixing a silent fallback-to-light bug; `index.css` gained the `--sep-*` framed-card token block (inert until `data-sep="framed"`); `ScreenThemes.tsx` gained "Frame theme" and "Card style" panel cards and a fix so theme-JSON import round-trips the new fields. i18n for the two new keys deferred — `en.json` only for now. |
| 2026-06-18 | TODO-150 phase 1: TapeMatch backend integration — `recording_families`/`tapematch_family_meta` MASTER tables (schema v7); `backend/tapematch_sync.py` ingests `tools/tapematch/observations.db` with deterministic, re-sync-safe `fam_id`s; `POST /api/tapematch/sync` + `GET /api/tapematch/families`; `import_master_db()` gained a missing-table skip guard (`skipped_tables` in its return) so older pre-feature snapshots import cleanly. |
| 2026-06-15 | v1.5.1 release: BUG-146/165/168/176/185/186 fixes (flat-file update download/apply flow, live footer status bar, date-prefix and tapematch reliability fixes) plus 115 new scraper/integration unit tests; `gui_next/package.json` version bumped 1.5.0 -> 1.5.1. |
| 2026-06-15 | Added 115 unit tests across 5 new files covering the scraper/integration backends: `tests/test_scraper.py` (entry metadata scraper), `tests/test_bootleg_scraper.py` (LBBCD catalog), `tests/test_bobdylan_scraper.py` (bobdylan.com setlists), `tests/test_setlistfm.py` (setlist.fm API), `tests/test_geocoder.py` (Nominatim geocoding). All network calls mocked via `unittest.mock`. Discovered and documented BUG-187 (pre-existing, Open): a global `_bloom` filter rebuilt by a background thread in `init_db()` leaks between test DBs, causing intermittent `tests/test_db_lookup.py` failures in full-suite runs. |
| 2026-06-15 | BUG-168: `ScreenHome.tsx`/`ScreenSetup.tsx` `handleCheckUpdate` fixed to read the real `/api/flat_file/discover` response shape (`available`/`current_release.zip_filename` instead of nonexistent `new_release`/`zip_filename`), so "Check for update" correctly reports an available release on a fresh install. `ScreenSetup.tsx`'s flat file history table gained per-row "Download" and "Review & Apply" actions wired to the existing `/api/flat_file/download/<id>`, `/diff/<id>`, `/apply/<id>` routes, with a confirm dialog showing added/changed/removed counts before applying. New `setup.flatFile.{download,downloading,downloadDone,reviewApply,applying,applyConfirmTitle,applyConfirmBody,applyDone}` locale keys (de/fr/es/it/nl pending DeepL translation). |
| 2026-06-15 | BUG-185/186: `gui_next/.../AppShell.tsx` footer `StatusBar` now shows live data instead of hardcoded placeholders — `DB/Checksums/Last import/Bootlegs` fetch `GET /api/home/stats`; the "Synced/idle" badge now reflects `GET /api/master/github_check` (master-data sync vs. curator's GitHub release) and a new `GET /api/activity/busy` (aggregates import/scrape/bootleg-scrape/integrity-scan/file-job/update-download worker state, polled every 5s). New backend route `activity_busy()` in `backend/app.py`. New locale keys under `appShell.statusBar.{synced,updateAvailable,idle,activity.*}` in all 6 languages. |
| 2026-06-15 | BUG-146/165/176: `backend/torrent_maker.py` `_parse_date` preserves `xx` month/day placeholders as ISO `YYYY-xx-xx`/`YYYY-MM-xx`; `tools/tapematch/tapematch_session.py` `_lb_num_from_folder` prefers a DB-resolved `name_to_lb` map over its regex scan (fixes self-pair rows from cross-referenced folder names); `tools/tapematch/tapematch/{audio,ingest,cli}.py` add `UnreadableAudioError`/`UnreadableSourceError` so one undecodable source file is skipped with a `[SKIP]` message instead of aborting the whole tapematch run. |
| 2026-06-14 | BUG-184: `gui_next/src/main/index.ts` gains `killProcessTree(pid)` — on Windows `taskkill /F /T /PID` kills the full process tree (not just `LosslessBobBackend.exe`), so in-flight ffmpeg/sox/shntool subprocesses no longer survive a normal app quit. Used in `before-quit` and `killStalePid`; `/T` added to `killPortProcess`'s taskkill. |
| 2026-06-14 | BUG-183: new `gui_next/resources/installer.nsh` (`customInit` NSIS macro, `taskkill /F /IM LosslessBobBackend.exe`) — fixes Windows installer "LosslessBob cannot be closed" prompt caused by an orphaned backend process locking its own exe. |
| 2026-06-14 | v1.5.0 release: tapematch reliability fixes (TODO-139 tasks 2-7), qBittorrent save-path sync, hash-verified pipeline filing, LBDIR site recovery, mount drive stats, pipeline GUI fixes (BUG-166/172-182, TODO-110/143/145), Windows font fix (BUG-175); `gui_next/package.json` version bumped 1.4.0 -> 1.5.0. |
| 2026-06-13 | TODO-143: Restored the GitHub "Check for Updates" path for master snapshots in `gui_next` (previously only the file-picker `Install from file…` fallback was ported from the frozen PyQt GUI's `_GitHubMasterThread`). New `GET /api/master/github_check` and `POST /api/master/github_install` (SSE) routes in `backend/app.py`; new button + handlers in `ScreenSetup.tsx`'s `CuratorToggle`. |
| 2026-06-12 | BUG-172: `find_torrent_by_path()` now also matches torrents renamed by the pipeline's rename step before filing — checks `rename_history` for the pre-rename folder name and matches qBittorrent's `content_path` on that. New `rename_torrent_root()` (`POST /api/v2/torrents/renameFolder`) and `recheck_torrent()` (`POST /api/v2/torrents/recheck`); `relocate_tracked_torrent()`'s external-match branch relocates, renames the root folder to the on-disk name, then rechecks. |
| 2026-06-12 | `backend/qbittorrent.py` gains `find_torrent_by_path()` (unfiltered `GET /api/v2/torrents/info`, matches `content_path`/`save_path`+`name` against a folder path) and `_track_external_torrent()` (records a discovered infohash into `torrents`); `relocate_tracked_torrent()` falls back to these when no DB-tracked row matches, so folders seeded outside the "Add to qBittorrent" workflow still get their save path synced on filing. |
| 2026-06-12 | `backend/qbittorrent.py` gains `set_location()` (`POST /api/v2/torrents/setLocation`) and `relocate_tracked_torrent()`; `backend/filer.py` `start_file_job` calls the new `_sync_qbt_location()` helper after a successful filing move — if the filed folder is tracked in qBittorrent (`torrents.added_to_qbt=1` with a known `infohash`), it points qBittorrent at the new parent directory (qBittorrent hash-rechecks and resumes seeding without re-downloading) and updates `source_folder`. Filing result gains `qbt_synced`/`qbt_error`; `ScreenPipeline.tsx` shows a toast on either outcome (`pipeline.file.qbtSynced`/`qbtSyncFailed`, all 6 locales). |
| 2026-06-12 | BUG-169: `master_github_release` now writes `master_version`/`master_published_at` from the manifest sidecar into the live DB's `meta` table via `database.set_meta()` after a successful GitHub release, so the Setup screen's "Master version" / "Last published" fields update (previously only the exported snapshot's meta was stamped). |
| 2026-06-12 | `backend/filer.py`: `start_file_job` now hash-verifies copied folders. New `hash_tree()` computes a SHA-256 over every file's relative path + content. Whenever data is actually copied (`file_mode="copy"`, or a cross-device move falling back to copy+delete), the destination is hashed and compared against the source before the original is removed (move) or the job is marked done (copy); a mismatch deletes the bad copy and returns `error_code: "hash_mismatch"`, leaving the source untouched. Same-device moves still use atomic `os.rename` (no file content rewritten, so not hash-verified). New job stages `verifying`/`removing` surfaced in `FileProgressBar` (`pipeline.file.progress.*`, all 6 locales). |
| 2026-06-12 | TODO-111: collection integrity monitor — new `backend/integrity_monitor.py` reuses `checksum_utils.verify_folder_lbdir()` per collection folder, classifying `ffp_status`/`md5_status`/`overall` into `content_issue`/`tag_issue`/`missing_files`/`no_lbdir`/`pass` (ignoring `overall == 'extra'`); new `collection_integrity_status`/`collection_integrity_scans` tables, `integrity_events.mount_id` column + new event types, 6 new `/api/collection/integrity/*` routes, optional hourly-checked scheduler (`integrity_scan_interval_hours`); `ScreenMounts.tsx` gains MountCard integrity badges/scan buttons and a "4 · Integrity Monitor" section (scan controls, progress, findings table, change log with acknowledge). |
| 2026-06-12 | GUI reorg: `CollectionRoutingCard` (mounts, year routing, filing mode, preview tester) split out of `ScreenSetup` into a new `ScreenMounts` screen, with its own nav item directly below Setup in the Settings group, `/mounts` route, and "mounts" hard-drive icon. |
| 2026-06-12 | TODO-110: `get_mounts_with_stats()` adds `total` (capacity) and `used_pct` to each mount via `shutil.disk_usage()`; pipeline Collect step's `CollectDetail.tsx` MountPicker cards show "free of total" plus a colour-coded usage bar (warn ≥75%, bad ≥90%), updating reactively as the pipeline re-resolves the Collect step. |
| 2026-06-12 | TODO-110 follow-up: disk-usage calc extracted into `backend/filer.py` `get_disk_usage_stats(root_path, online)`, reused by `get_mounts_with_stats()` and `/api/collection/mounts` (now returns `free`/`total`/`used_pct` per mount); `ScreenMounts.tsx` MountCard shows the same "free of total" usage bar as the Collect step. |
| 2026-06-12 | TODO-112: backend uptime clock — new `GET /api/system/uptime` (`{uptime_seconds}`) sharing a single `_process_start_time` with `/api/admin/status`; About dialog's About tab shows a live HH:MM:SS uptime field next to version/build, to help confirm whether a backend restart actually happened. |
| 2026-06-11 | BUG-161: pipeline `/api/pipeline/run` LBDIR step (step 4) now calls `database.set_lbdir_verified()` on a `pass`, so the Collect stage's "Confirmed" date (`my_collection.lbdir_verified_at`) updates for owned folders re-checked in place. |
| 2026-06-11 | BUG-159: `verify_folder_lbdir()` whitelists `extras/` (from `/api/lbdir/move_extras`) and `rename_log.txt` when computing unclaimed "extra" files — once those are the only leftovers, status resolves to `pass` so pipeline step 4 turns green after a reconcile. |
| 2026-06-11 | BUG-158: `verify_folder_lbdir()` now detects files on disk not referenced by any lbdir entry, reporting them as `overall: "extra"` rows and a real `extra` count; new lbdir status `extra_files` (everything checksums-clean but stray files present) so such folders no longer show green and the reconcile/move-to-extras flow is reachable. |
| 2026-06-10 | Pipeline v2 cleanup phase 5: `backend/filer.py` gains `get_mounts_with_stats()` (mount span/free/online) and a `mount_id_override` param on `resolve_destination_for_lb`/`file_folder`; `/api/pipeline/file` and `/api/pipeline/file/preview` accept optional `mount_id`; pipeline file step result gains `mounts`/`recommended_mount`/`routed_year`/`collection_count`; new `components/pipeline/CollectDetail.tsx` (MountPicker + TagTable) rendered by `CollectReadyDetail` in the pipeline Collect panel, with live `/api/pipeline/file/preview` re-resolve on mount override. |
| 2026-06-10 | Pipeline v2 cleanup phase 4: `components/pipeline/LbdirDetail.tsx` (CheckDot, LbdirFileTable with resizable MD5/Disk/Overall/Length/Fmt/Ratio columns, ReconcilePanel incl. site/files recovery) harvested from ScreenLBDIR, shared by ScreenLBDIR and the pipeline LBDIR panel; pipeline `LbdirStageContent` now shows the full file table and reconcile UI (previously a truncated 12-row list with no site recovery section). |
| 2026-06-10 | Pipeline v2 cleanup phase 3: `components/pipeline/LookupDetail.tsx` (LookupSummaryTable, LookupChecksumTable, LookupNotFoundHint) harvested from ScreenLookup, shared by ScreenLookup and the pipeline Lookup panel; pipeline `LookupStageContent` now shows category pill + matched/given stat, "Which show is this?" picker with per-LB "Pin {lb} & continue" → `PUT /api/folder_link`; backend lookup step returns `summary`/`detail` and honors `folder_lb_link` pins. |
| 2026-06-09 | Pipeline v2: `collection_mounts` + `collection_routes` DB tables; `backend/filer.py` (normalise_path, resolve_destination_for_lb, file_folder); 10 new API routes (mounts CRUD, routes bulk/delete/preview, pipeline/file, pipeline/file/preview); `CollectionRoutingCard` in ScreenSetup (mounts list, year routing, filing mode, preview tester); 5 stage detail panels in ScreenPipeline (VerifyStage, LookupStage, RenameStage, LBDIRStage, CollectStage); ScreenQuickLookup (paste/clipboard/drop zone, results table); pipeline/filer/PipelineParts/ConfirmDialog components added. |
| 2026-05-30 | Archive.org upload integration: `backend/archive_org.py` (IA S3 PUT, progress state, stop support); `archive_org_uploads` table; `SERVICE_IA` keyring slot; 8 `/api/archive_org/` routes; `ArchiveOrgSection` component in `ScreenSharing` with credentials form, upload form, progress bar, history table. (TODO-093) |
| 2026-05-30 | Collection Trading + File Sharing features (branch feat/trading-and-sharing): `friend_collections` + `friend_collection_entries` tables; 5 `/api/trading/` routes; `backend/sharing.py` module (ephemeral share state, ZIP streaming, Cloudflare Tunnel); 7 `/api/share/` routes; `ScreenTrading` + `ScreenSharing` in gui_next; Trading + Sharing nav items under Library group. |
| 2026-06-01 | `lb_category` TEXT column added to `entries` (MASTER_SCHEMA_VERSION→6). `classify_entry_categories()` in `db.py` classifies all entries: concerts via `bobdylan_shows` date-join (84.7%), other categories via `dylan_performances` map + keyword heuristics, fallback to `'unknown'`. One-time backfill in `init_db()`; re-run via `POST /api/entries/reclassify` (curator). |
| 2026-05-30 | `taper_name` + `source_chain` TEXT columns added to `entries` via ALTER TABLE migration. `extract_taper_and_source()` in `db.py` parses free-text descriptions with 14 pattern rules; ~80.5% coverage on 16k entries. Backfill run on first `init_db()` after migration. `scraper.py` computes both columns on every scrape. `ScreenSearch.tsx` shows Taper/Source as toggleable columns and in the detail panel meta grid. |
| 2026-05-29 | Windows installer + portable switched to Electron/React (gui_next): `losslessbob_backend.spec` made cross-platform (Windows watchdog, shntool.exe, no fingerprinting); `backend/paths.py` frozen-Windows data dir → `%LOCALAPPDATA%\LosslessBob`; electron-builder NSIS + portable targets; `release.yml` build-windows rebuilt. |
| 2026-05-29 | Linux AppImage switched to Electron/React (gui_next): new `losslessbob_backend.spec` (onefile PyInstaller, no PyQt6); `gui_next/package.json` gains electron-builder + dist:linux script; `gui_next/src/main/index.ts` ensureBackend() uses bundled binary when packaged; `release.yml` build-linux job rebuilt around electron-builder. |
| 2026-05-29 | TODO-106: ScreenFingerprint (gui_next Assets group) — date → collection_by_date → build LB fingerprints → identify mystery folder → ranked results. New backend routes: GET /api/fingerprint/collection_by_date, POST /api/fingerprint/identify_folder + status + stop. Icon + nav item + route registered. All strings i18n-wrapped. |
| 2026-05-29 | Development direction locked: `gui_next` (Electron/React) is the sole active development target. `gui/` (PyQt6) is frozen — no new features or bug fixes. PROJECT.md, tech stack, architecture note, and file structure all updated to reflect this. |
| 2026-05-28 | gui_next Sprint 6: ScreenThemes fully wired — typeface picker, font size buttons, custom token color editor, export/import JSON. New IPC: `dialog:saveFile`, `dialog:pickAndReadFile`. `tokens.ts` extended with `Font`, `FontSize`, `customTokens` fields; `--lbb-font`/`--lbb-font-size` CSS vars drive global typography. |
| 2026-05-24 | DB-09: DatabaseWriteQueue in `backend/db_queue.py`; all write paths across db.py, scraper.py, site_crawler.py, app.py, importer.py, flat_file.py, geocoder.py routed through single writer thread; write_connection() removed; busy-timeout races eliminated. |
| 2026-05-22 | Cross-tab folder sync: `add_folders_from_lookup()` added to `gui/lbdir_tab.py`; `main_window.py _on_tab_changed` wires lbdir pre-population on tab switch (mirrors existing Verify guard). (TODO-081) |
| 2026-05-22 | Multi-LB alias folder naming: `get_aliases_for_canonical()` in `backend/db.py`; Rename tab `populate_from_lookup` and `_on_save_alias` fetch all aliases via `GET /api/lb_alias?canonical_lb=<lb>` after alias collapse and include them in proposed suffix (`LB-canonical-LB-alias1...`). (TODO-080) |
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
| 2026-05-26 | BUG-112: added downgrade guard to `import_master_db()` (db.py). TODO-091: bundled `tools/shntool.exe` into PyInstaller Windows dist via losslessbob.spec; updated `_find_shntool()` (checksum_utils.py) to resolve bundled and dev-tree paths before WSL/PATH. |
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
| 2026-05-24 | DB-09 fix: rewrote DatabaseWriteQueue._worker with isolation_level=None and explicit BEGIN/COMMIT/ROLLBACK; added startup ready-event to eliminate WAL-pragma race; purged implicit transaction leak from init_db(); added conftest.py test isolation fixture; updated stale TestWriteConnectionRollback tests. |
| 2026-05-26 | TODO-086/090: `dylan_performances` promoted from USER→MASTER (schema v3); new `lb_problems` MASTER table (id, lb_number, notes, added); 4 DB functions; `GET /api/performances` (date/lb/category filter); `GET/POST /api/lb_problems` + `PUT/DELETE /api/lb_problems/<id>` (curator-only write). |
| 2026-05-27 | gui_next Sprint 1 (ScreenSetup 100%): all stubs wired; new backend routes: `POST /api/credentials/wtrf`, `POST /api/credentials/qbt`, `POST /api/rename_history/purge`, `POST /api/flat_file/purge`, `POST /api/scraper/purge`, `POST /api/fingerprint/purge`; `data_dir` added to `GET /api/db/settings`; `flac_available` added to `GET /api/spectrogram/check`; `pickFile` IPC added to main/preload. |
| 2026-05-28 | gui_next Sprint 2 (ScreenCollection ~90%): all 17 stubs wired; `lbNumberInt` + `isXref` fields added to `CollectionRow`; year filter via `/api/search/years`; xref filter via `/api/checksums/xref_lb_numbers`; `AddFolderModal` (per-row LB# input); `ForumModal` with editable BBCode before `preview_forum` → `post_forum`; version-bump refetch pattern established. |
| 2026-05-28 | gui_next Sprint 3 (ScreenSearch ~95%): virtual table sort (6 keys), group-by-year toggle, CSV export, column visibility (localStorage), saved views (localStorage + 3 built-ins), `owned` field wired to `GET /api/collection/lb_numbers`, entry detail panel (`GET /api/entry/<lb>`) with files list + "Scrape entry", per-row ⋯ menu (`position:fixed`, `POST /api/entry/<lb>/scrape`), Toast component. (TODO-094 Stage: Sprint 3 done) |
| 2026-06-01 | Batch verification pipeline: tools/batch_verify.py — lbdir-centric CLI for large collections; 4-phase pipeline (identify/retrieve/verify/reconcile-preview); report SQLite DB (data/batch_verify.db, never touches losslessbob.db); resume/dry-run/reprocess/report modes. (BATCH-VERIFY) |
| 2026-06-11 | BUG-160 fix: `rename_history.renamed_at` now written as local time by `add_rename_history()` instead of SQLite's UTC `CURRENT_TIMESTAMP` default; one-time migration converts existing rows to local time. |
| 2026-06-11 | Pipeline Collect tag preview (`CollectDetail.tsx` TagTable) now shows real data: `lb_master.lb_status` + collection-ownership for "Status" and `my_collection.lbdir_verified_at` for "Confirmed", replacing hardcoded "Public · Owned"/"Today"; removed the unused "Fingerprint: Queued · AcoustID" row. `/api/pipeline/status` file step gains `lb_status`/`owned`/`lbdir_verified_at`. |
| 2026-06-12 | v1.4.0 release: merged `feat/pipeline-v2-storage-mounts` into `main` — collection mount management, Quick Lookup screen, pipeline lookup/rename/lbdir/collect stage panels, background copy/move with progress; `gui_next/package.json` version bumped 1.3.0 -> 1.4.0. |
| 2026-06-12 | TODO-137: pipeline step order swapped so LBDIR (now step 3) reconciles before Rename (now step 4) — `verify -> lookup -> lbdir -> rename -> collect`. `_pipeline_process_folder` reordered; `/api/lbdir/check` and `/api/lbdir/reconcile` gained an `lb_number_hint` fallback (LBDIR runs before the folder has `LB-NNNNN` in its name); `DEFAULT_STAGES` and all step-key iteration orders in ScreenPipeline.tsx updated to match, including the auto-complete "stale" check (now resumes on `lbdir.status === 'mute'`). |
| 2026-06-12 | TODO-138: Pipeline "Auto-rename" toggle added to ScreenPipeline.tsx header (default off). When on, rows with verify/lookup/lbdir all "ok" and a single proposed rename auto-apply via the existing `applyRename()` path, marking step 4 green and advancing to Collect with no manual click. |
| 2026-06-13 | BUG-175 fix: Inter/IBM Plex Sans/Source Sans 3/JetBrains Mono now self-hosted via `@fontsource` (no more fonts.googleapis.com fetch — fixes wrong-fallback-font on offline/firewalled Windows installs); `-webkit-font-smoothing: antialiased` scoped to `html.platform-darwin` only (was disabling ClearType on Windows). `window.api.platform` added via preload. |
