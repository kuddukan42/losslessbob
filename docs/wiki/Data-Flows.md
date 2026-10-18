# Data Flows

> Sources: `PROJECT.md` §Key Data Flows, §Checksum Format Reference,
> §Flat File Update Pipeline, §Master Data (publish / subscribe) · `docs/data_ownership.md` ·
> `docs/lb_missing_vs_missing_status.md` · Status: fresh 2026-10-18

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
   `song_index` (steps logged via `record_step_run`). Rewrites only USER-tier derived tables; manual trigger
   (onboarding "Done" + curator button).
5. **Master data publish/subscribe** — two separate channels. (a) Site
   flat-file releases (`flat_file_releases`, per-row diffs in
   `flat_file_changelog`) update `checksums`, then reconcile `lb_master` and
   scrape the release's new LBs ([Release-Update](Release-Update.md)).
   (b) Curator publishes MASTER-table snapshots (`/api/master/export` →
   GitHub release; subscribers `github_check`/`github_install`). Channels:
   `public` (private metadata stripped; the only one uploadable) vs `full`
   (friends only). Site-mirror xref ingest is a separate *reviewed* import
   path (staging → review → apply, TODO-252 — approvals never automatic).
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
9. **Read surfaces** — Show Detail (`gap_analysis.py`, `/api/shows/<iso>/olof`;
   the standalone Gaps screen is gone) classifies coverage live from
   `olof_events` vs `entries`; `/api/dossier` (+ `/html`, `/bbcode`) assembles
   everything known about one date ([Show-Dossier](Show-Dossier.md)).
10. **Seeding/upload out** — folder → torrent → qBittorrent / WTRF / TUIT via
    verified overlays that never write to the collection ([Integrations](Integrations.md)).

## Checksum format notes

See PROJECT.md §Checksum Format Reference. Gotchas: legacy files may be
Windows-1252; Unicode normalization differences (curly vs straight apostrophes)
break naive filename matching — always check both.

## lb_missing vs missing status

Distinct concepts — `lb_missing` is the MASTER table of confirmed non-existent
LB numbers; "missing" status elsewhere means *not in local collection*. Full
explanation: `docs/lb_missing_vs_missing_status.md`.
