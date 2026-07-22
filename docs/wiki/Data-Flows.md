# Data Flows

> Sources: `PROJECT.md` §Key Data Flows (~line 1978), §Checksum Format Reference
> (~line 2022), §Backend routes (~1171) · `docs/data_ownership.md` ·
> `docs/lb_missing_vs_missing_status.md` · Status: fresh 2026-07-22

## Main flows

1. **Checksum lookup** — user drops folder/checksum file → `checksum_utils.py`
   parses (md5/ffp/st5; cp1252-aware) → match against `checksums` → LB entry
   (+ xref fileset detection).
2. **Scrape** — `scraper.py` pulls entry metadata from losslessbob.com (local
   mirror pages preferred, web fallback) → `entries`/`entry_files`, diffs logged
   to `entry_changes`; `site_crawler.py` maintains a full mirror inventory;
   `wtrf_scraper.py` fetches forum torrents for missing items.
3. **Setlist corpus ingest** — Olof DSN + bobserve.com + Yearly Chronicles
   mirrored and parsed into `olof_events`/`olof_songs`/`olof_chronicle`
   ([Setlist-Sources](Setlist-Sources.md)); bobdylan.com + setlist.fm into
   their MASTER tables.
4. **Derived-data recompute** — `/api/derived/recompute` SSE chain in canonical
   order: `parse_lineage` → `attribute_tapers` → `compute_show_picks` →
   `song_index`. Rewrites only USER-tier derived tables; manual trigger
   (onboarding "Done" + curator button).
5. **Master data publish/subscribe** — curator publishes MASTER tables as
   flat-file releases (`flat_file_releases`); subscribers apply with per-row
   diffs in `flat_file_changelog`. Export channels: `public` (private metadata
   stripped; the only channel uploadable to the public GitHub repo) vs `full`
   (friends only). Site-mirror xref ingest is a separate *reviewed* import path
   (staging → review → apply, TODO-252 — approvals never automatic).
6. **Collection filing** — folder → LB identification → rename
   (`rename_history`) → routing by year via `collection_mounts`/
   `collection_routes` → integrity monitoring (`collection_integrity_*`,
   `integrity_events`).
7. **TapeMatch → app** — family clustering + per-date pair scores sync into
   `recording_families`/`tapematch_family_meta`/`tapematch_pairs` via the
   Family Sync API.
8. **Concert Ranker** — audio scan stores RAW metrics once → rerank derives
   scores/verdicts → `show_picks` unified ranking → Library badges, Picks tab,
   [Show-Dossier](Show-Dossier.md) recommendation.
9. **Read surfaces** — [gaps view](Setlist-Sources.md) classifies coverage
   live from `olof_events` vs `entries`; dossier assembles everything known
   about one date, with HTML/BBcode exports.

## Checksum format notes

See PROJECT.md §Checksum Format Reference. Gotchas: legacy files may be
Windows-1252; Unicode normalization differences (curly vs straight apostrophes)
break naive filename matching — always check both.

## lb_missing vs missing status

Distinct concepts — `lb_missing` is the MASTER table of confirmed non-existent
LB numbers; "missing" status elsewhere means *not in local collection*. Full
explanation: `docs/lb_missing_vs_missing_status.md`.
