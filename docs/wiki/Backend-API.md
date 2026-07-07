# Backend API

> Sources: `PROJECT.md` §Backend sections (lines ~692–1180) · `backend/app.py` ·
> Status: seeded 2026-07-06

Flask API served on **port 5174** (hardcoded). Restart with `/backend-restart`
before verifying any backend change — stale processes are the #1 source of
"fix didn't work" confusion.

## Route groups (per PROJECT.md)

Checksum Lookup · Database Management · Flat File Update Pipeline ·
Master Data (publish/subscribe) · LB Master Integrity · LB Missing ·
Dylan Performances · TapeMatch Family Sync · Library (performance/show grouping) ·
LB Problems · Folder Naming · LB Alias · Folder→LB Sticky Links · Entry Detail ·
Search (FTS5) · Site Mirror Crawler · Entry Metadata Scraper · Bootleg-CD Catalog ·
Collection Data Management · Collection Routing & Pipeline Filing ·
Collection Integrity Monitor · DB Editor · Torrent Generation

For a specific route: `grep -n <keyword> backend/app.py` — don't read the file whole.

## Backend modules

| Module | Role |
|---|---|
| `app.py` | All Flask routes |
| `db.py` | Schema creation/migration + query layer |
| `checksum_utils.py` | Checksum parsing/verification (md5/ffp/st5), cp1252-aware |
| `importer.py` | Bulk import of checksum files |
| `scraper.py` | losslessbob.com entry metadata scraper |
| `site_crawler.py` | Full site mirror crawler (`scrape_sessions`, `site_inventory`) |
| `wtrf_scraper.py` | WTRF forum torrent fetcher for missing LB items |
| `scheduler.py` | Periodic background jobs |
| `geocoder.py` | Concert location geocoding (`location_geocoded`) |

Logs are consolidated under `data/logs/` (since 2026-07).
