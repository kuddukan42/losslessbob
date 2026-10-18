# Database

> Sources: `PROJECT.md` §Database Schema · `docs/schema.html` ·
> `docs/data_ownership.md` · `backend/db.py` · Status: fresh 2026-10-18

Single SQLite database managed by `backend/db.py`. Interactive schema browser:
**losslessbob-schema.pages.dev** (auto-deployed from `docs/schema.html`).
`MASTER_SCHEMA_VERSION = 11`.

## Ownership tiers (details: `docs/data_ownership.md`)

- **MASTER** — curator-authored, distributed via flat-file publish/subscribe:
  `lb_master` + `lb_status_history` (integrity system), `lb_missing`, `lb_alias`,
  `flat_file_changelog`, `bootleg_titles/scrapes`, `dylan_performances`, `bobdylan_shows/_setlist`,
  `setlistfm_shows/_setlist`, `recording_families` + `tapematch_family_meta`,
  `lb_problems`, `curated_lists`, `checksum_disputes`, `curated_list_entries`,
  `location_geocoded`, `flat_file_releases`. Authoritative list: `MASTER_TABLES` in `db.py`.
  Export has **channels**: `public` (default, strips private metadata — the only
  channel uploadable to GitHub releases) vs `full` (friends only, TODO-253).
- **USER** — local per-installation state: collection tables (`my_collection`,
  `folder_lb_link`, mounts/routes, integrity), Concert Ranker tables,
  `entry_lineage`, pipeline caches, `friend_collections`, `xref_ingest_*` staging,
  `user_taper_aliases`/`user_taper_flags`/`taper_decision_log`, `scrape_sessions`,
  `site_inventory`, `qc_runs`/`qc_findings`/`qc_decision_log`, `release_classifications`,
  `corrections`, `refresh_step_runs`/`refresh_chain_runs`, `file_inventory`,
  `file_integrity_scans` (authoritative: `USER_TABLES` in `db.py`). Other local tables outside
  both lists: `wtrf_downloads`, `archive_org_uploads`, `tuit_*`, `venue_wiki_links`,
  `venue_geocoded`, `bobserve_event_index`, `bobtalk_*`, `boblinks_pages`.
- **Derived USER** — recomputed wholesale, never exported (a master import can
  never clobber them): `taper_attributions`, `show_picks`,
  `song_canonical`/`song_performances`, `setlist_fingerprint_suggestions`,
  `tapematch_pairs`, `tapematch_date_curation`.
- **Local-only corpus** — `olof_pages`/`olof_events`/`olof_songs`,
  `olof_chronicle`, `olof_new_tapes` (see [Setlist-Sources](Setlist-Sources.md));
  master-export tier is a pending P5 decision.

## Core tables

- `checksums` — the core lookup table (checksum → LB entry; xref = fileset id,
  0 = canonical — semantics authority `docs/XREF_SEMANTICS.md`).
- `entries` — scraped entry metadata; `status='private'` rows from the private
  import (TODO-245) with `metadata_source` provenance; `entry_files` attachments;
  `entries_fts` (FTS5); `entry_changes` scrape diffs.
- `lb_master` — unified per-LB status/integrity record driving forum-guard and
  NFT logic; transitions logged in `lb_status_history`.
- `torrents`, `rename_history`, `forum_posts`, `integrity_events` — operational logs.
- `meta` — key-value config store.

## Conventions

- Schema changes: `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` checks
  before `ALTER TABLE` — never assume a clean DB.
- Legacy md5/checksum files may be **cp1252**-encoded; watch for `\x92`-style
  bytes and Unicode-normalization mismatches (curly vs straight apostrophes).
- Known taper handles: `_KNOWN_TAPER_ALIASES` in `db.py`; local overrides in
  `user_taper_aliases` (audit-only, never exported).
