# Backend API

> Sources: `PROJECT.md` §Backend: Flask API · `backend/app.py` · `backend/refresh.py` ·
> `backend/queues.py` · `backend/qc/` · Status: fresh 2026-10-18

Flask API served on **port 5174** (hardcoded). Restart with `/backend-restart`
before verifying any backend change — stale processes are the #1 source of
"fix didn't work" confusion. Error shape convention: PROJECT.md §API Error-Shape.

## Route groups (per PROJECT.md §Backend: Flask API)

`app.py` (~13k lines) holds ~360 `/api/*` routes plus HTML pages (`/admin`, `/map`,
`/qc-review`, `/taper-review`, `/taper-curation`). Largest prefixes: `collection`,
`tapers`, `tapematch`, `olof`, `lb_master`, `qc`, `pipeline`, `entry`. The
TODO-365 triage (2026-10-18) deleted 15 PyQt-era/superseded routes (e.g.
`/api/collection/search`, `/api/torrents`, `/api/performances`, `/api/lbdir/delete_extra`);
grep before documenting a route.

**Core**: Checksum Lookup · Database Management · App Update & Data Download ·
Search (FTS5) · Entry Listing/Detail/Reclassification · DB Editor · Admin · Misc
**Master data**: Flat File Update Pipeline · Master publish/subscribe ·
Site-Data Packaging & Onboarding · LB Master Integrity · LB Missing · LB Alias ·
LB Problems · Curated Lists · Site-Mirror Xref Ingest (reviewed import, TODO-252)
**Setlists & shows**: Dylan Performances · bobdylan.com Scraper · Setlist.fm ·
Olof Björner · Setlist Fingerprinting · Show Detail (coverage classification,
feeds the Library's uncirculated/upcoming rows; the old Gaps screen/routes are gone) · Show Dossier ·
Library performance/show grouping · Map · Geocoding
**Derived data**: Pipeline Refresh (`/api/refresh/*` status, review queues,
chained execution) · QC (`/api/qc/*` findings/decisions/run) · Timeline ·
BobTalk · Preservation reports · Derived-Data Recompute (SSE chain: lineage → tapers → picks →
song index) · Taper Attribution · TapeMatch Family + Pairs Sync · Songs index
**Collection**: My Collection · Wishlist · Collection Data Management · Routing &
Pipeline Filing · Integrity Monitor · Folder Naming · Folder→LB Sticky Links ·
Rename · Verify · LBDir · Spectrogram
**Sharing & external**: Torrent Generation · qBittorrent · Credentials · Forum
Posting · WTRF Torrent Search · Archive.org Upload · Trading/Friend Collections ·
File Sharing (Cloudflare Tunnel) · Site Mirror Crawler · Entry Metadata Scraper ·
Bootleg-CD Catalog · TUIT/WTRF tracker seeding (`/api/trackers`, `/api/wtrf/*`)

For a specific route: `grep -n <keyword> backend/app.py` — don't read the file whole.

## Key backend modules

| Module | Role |
|---|---|
| `app.py` | All Flask routes |
| `db.py` | Schema creation/migration + query layer |
| `checksum_utils.py` | Checksum parsing/verification (md5/ffp/st5), cp1252-aware |
| `importer.py` / `scraper.py` / `site_crawler.py` | Ingest: checksum files, entry metadata, full site mirror |
| `olof_*`, `bobserve_*`, `setlistfm.py`, `bobdylan_scraper.py` | Setlist corpora ([Setlist-Sources](Setlist-Sources.md)) |
| `taper_attribution.py` / `song_index.py` / `setlist_fingerprint.py` | Derived-data engines |
| `gap_analysis.py` / `dossier.py` | Library performance-lens coverage (uncirculated/upcoming) · [Show-Dossier](Show-Dossier.md) |
| `filer.py` / `integrity_monitor.py` / `folder_naming.py` | Collection pipeline & watchdog |
| `sharing.py` / `forum_poster.py` / `qbittorrent.py` / `archive_org.py` | Outbound integrations |
| `scheduler.py` / `db_queue.py` / `activity.py` | Background jobs, write queue, activity feed |
| `refresh.py` / `refresh_exec.py` / `queues.py` / `job_progress.py` | [Pipeline-Refresh](Pipeline-Refresh.md): step registry, chain runner, review queues, shared job state |
| `qc/` (`rules.py`, `store.py`, `jobs.py`) | QC rule engine + findings/decisions store |
| `dossier*.py` / `taper_curation.py` | Dossier build/QC · taper curation console (`/taper-curation`) |
| `tuit_*.py` / `wtrf_*.py` / `tracker_seed.py` | Private-tracker scrape/upload/seed |
| `geocoder.py` | Concert location geocoding (`location_geocoded`, venue gazetteer) |

Logs are consolidated under `data/logs/`.
