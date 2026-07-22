# Backend API

> Sources: `PROJECT.md` §Backend: Flask API (lines ~1171–1705) · `backend/app.py` ·
> Status: fresh 2026-07-22

Flask API served on **port 5174** (hardcoded). Restart with `/backend-restart`
before verifying any backend change — stale processes are the #1 source of
"fix didn't work" confusion. Error shape convention: PROJECT.md §API Error-Shape.

## Route groups (per PROJECT.md §Backend: Flask API)

**Core**: Checksum Lookup · Database Management · App Update & Data Download ·
Search (FTS5) · Entry Listing/Detail/Reclassification · DB Editor · Admin · Misc
**Master data**: Flat File Update Pipeline · Master publish/subscribe ·
Site-Data Packaging & Onboarding · LB Master Integrity · LB Missing · LB Alias ·
LB Problems · Curated Lists · Site-Mirror Xref Ingest (reviewed import, TODO-252)
**Setlists & shows**: Dylan Performances · bobdylan.com Scraper · Setlist.fm ·
Olof Björner · Setlist Fingerprinting · Gaps View · Show Dossier ·
Library performance/show grouping · Map · Geocoding
**Derived data**: Derived-Data Recompute (SSE chain: lineage → tapers → picks →
song index) · Taper Attribution · TapeMatch Family + Pairs Sync · Songs index
**Collection**: My Collection · Wishlist · Collection Data Management · Routing &
Pipeline Filing · Integrity Monitor · Folder Naming · Folder→LB Sticky Links ·
Rename · Verify · LBDir · Spectrogram
**Sharing & external**: Torrent Generation · qBittorrent · Credentials · Forum
Posting · WTRF Torrent Search · Archive.org Upload · Trading/Friend Collections ·
File Sharing (Cloudflare Tunnel) · Site Mirror Crawler · Entry Metadata Scraper ·
Bootleg-CD Catalog

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
| `gap_analysis.py` / `dossier.py` | Gaps view · [Show-Dossier](Show-Dossier.md) |
| `filer.py` / `integrity_monitor.py` / `folder_naming.py` | Collection pipeline & watchdog |
| `sharing.py` / `forum_poster.py` / `qbittorrent.py` / `archive_org.py` | Outbound integrations |
| `scheduler.py` / `db_queue.py` / `activity.py` | Background jobs, write queue, activity feed |
| `geocoder.py` | Concert location geocoding (`location_geocoded`, venue gazetteer) |

Logs are consolidated under `data/logs/`.
