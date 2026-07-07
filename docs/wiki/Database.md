# Database

> Sources: `PROJECT.md` §Database Schema (lines ~186–690) · `docs/schema.html` ·
> `docs/data_ownership.md` · `backend/db.py` · Status: seeded 2026-07-06

Single SQLite database managed by `backend/db.py`. Interactive schema browser:
**losslessbob-schema.pages.dev** (auto-deployed from `docs/schema.html`).

## MASTER vs USER tables

Tables are split by data ownership (details in `docs/data_ownership.md`):

- **MASTER** — curator-authored / centrally published, distributed via the flat-file
  publish/subscribe pipeline: `lb_missing`, `lb_alias`, `bootleg_titles`,
  `bootleg_scrapes`, `dylan_performances`, `recording_families` +
  `tapematch_family_meta`, `lb_problems`, `curated_lists`, `scrape_sessions`,
  `site_inventory`, `location_geocoded`, `flat_file_releases`.
- **USER** — local per-installation state: `folder_lb_link`, `quality_scans` /
  `quality_recording_metrics` / `quality_recording_scores` (Concert Ranker),
  `entry_lineage`, `archive_org_uploads`, `collection_mounts`, `collection_routes`,
  collection integrity tables.

## Core tables

- `checksums` — the core lookup table (checksum → LB entry).
- `entries` — entry metadata scraped from losslessbob.com; `entry_files` for
  attachments; `entries_fts` (FTS5) for full-text search; `entry_changes` for
  field-level scrape diffs.
- `torrents`, `rename_history`, `forum_posts` — operational logs.
- `integrity_events` + `collection_integrity_status/scans` — file-change watchdog
  and per-LB integrity scan results (TODO-111 lineage).
- `meta` — key-value config store.

## Conventions

- Schema changes: idempotent `ALTER TABLE` wrapped in try/except — never assume a
  clean DB.
- Legacy md5/checksum files may be **cp1252**-encoded; watch for `\x92`-style bytes
  and Unicode-normalization mismatches (curly vs straight apostrophes).
- Known taper handles are curated in `_KNOWN_TAPER_ALIASES` in `db.py`.
