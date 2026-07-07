# Data Flows

> Sources: `PROJECT.md` §Key Data Flows (~line 1517), §Checksum Format Reference
> (~line 1561) · `docs/data_ownership.md` · `docs/lb_missing_vs_missing_status.md` ·
> Status: seeded 2026-07-06

## Main flows

1. **Checksum lookup** — user drops folder/checksum file → `checksum_utils.py`
   parses (md5/ffp/st5; cp1252-aware) → match against `checksums` → LB entry.
2. **Scrape** — `scraper.py` pulls entry metadata from losslessbob.com →
   `entries` / `entry_files`, diffs logged to `entry_changes`; `site_crawler.py`
   maintains a full mirror inventory; `wtrf_scraper.py` fetches forum torrents
   for missing items.
3. **Master data publish/subscribe** — curator publishes MASTER tables as flat-file
   releases (`flat_file_releases`); subscribers apply them with per-row diffs
   logged in `flat_file_changelog`.
4. **Collection filing** — folder → LB identification → rename (`rename_history`)
   → routing by year via `collection_mounts`/`collection_routes` → integrity
   monitoring (`collection_integrity_*`, `integrity_events`).
5. **TapeMatch → app** — family clustering results sync into
   `recording_families`/`tapematch_family_meta` via the Family Sync API.
6. **Concert Ranker** — quality scans over recordings → metrics → scores →
   ranked display in gui_next pipeline UI.

## Checksum format notes

See PROJECT.md §Checksum Format Reference. Gotchas: legacy files may be
Windows-1252; Unicode normalization differences (curly vs straight apostrophes)
break naive filename matching — always check both.

## lb_missing vs missing status

Distinct concepts — `lb_missing` is the MASTER table of confirmed non-existent LB
numbers; "missing" status elsewhere means *not in local collection*. Full
explanation: `docs/lb_missing_vs_missing_status.md`.
