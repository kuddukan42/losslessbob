# Master Data & Sync

> Sources: `PROJECT.md` §Flat File Update Pipeline, §Site-Mirror Xref Ingest,
> §Master Data (publish / subscribe), §Site-Data Packaging & Onboarding,
> §LB Master Integrity, `lb_master` table · `docs/data_ownership.md` ·
> `backend/db.py` · `backend/flat_file.py` · `backend/xref_ingest.py` ·
> `backend/folder_naming.py` · Status: fresh 2026-10-18

How curator-authored data reaches every installation, and how per-LB status is
kept trustworthy. Curator flag: `meta.is_curator` (local-only, never shipped);
curator-only routes 403 without it.

## lb_master — the integrity spine

`lb_master` is the single source of truth for whether an LB number is
`public`/`private`/`missing`/`nonexistent`, reconciled from `entries`,
`checksums`, `entry_files`, `lb_missing` by `reconcile_lb_status()` per LB /
`reconcile_all_lb_master()` (full rebuild via `/api/lb_master/reconcile` backs up the DB first). Curator `manual_override` pins a status and
wins over reconciliation; transitions log to `lb_status_history` with a
`trigger_event`. Flags: `needs_review` (ambiguous), `public_no_checksums`.
Feeds GUI badges, the **NFT suffix** for folder naming
(`/api/lb_master/<lb>/nft`; helpers in `folder_naming.py`), and forum-posting guards. Overrides
export/import as JSON (import is curator-only, history-logged).

## Distribution channels

| Channel | What ships | How |
|---|---|---|
| Flat-file releases | `checksums` updates from the download page | discover → download → diff → apply (auto-backup, changelog per row, lb_master reconcile, then a background scrape of the release's never-scraped LBs so Reconcile cannot strand them, BUG-365); prompting deferrable — order of operations: [Release-Update](Release-Update.md) |
| Master snapshots | All `MASTER_TABLES` + `MASTER_META_KEYS` | `export_master_db`: VACUUM INTO → drop USER tables → stamp versions → verify → SHA256 + manifest. **Channels**: `public` (default — private-entry metadata blanked, TODO-253) vs `full` (friends only). GitHub release upload **refuses any non-public manifest** |
| Site-data packages | `data/site/` mirror (core / files parts) | zip + manifest → `sitedata-*` GitHub releases; install verifies SHA256 *before* extraction |
| Xref ingest (TODO-252) | Mirror `LBF-*-xref-*` filesets → `checksums` | **Reviewed import path**: scan → stage → curator approve/reject; approvals never automatic |

Import side: `/api/master/import` validates manifest SHA256, refuses
newer-schema snapshots, takes a `pre_master_import` backup, copies only
MASTER tables/meta keys, rebuilds FTS. GitHub flows (`/api/master/github_{release,check,install}`,
`/api/sitedata/github_{release,check,install}`) are SSE-streamed; release is
curator-only and needs `gh auth token`. `MASTER_SCHEMA_VERSION = 11`.

## Onboarding

`/api/onboarding/status` gives the first-run checklist (entries, master
version, sitedata parts, mounts, collection); `complete` = entries ∧
master_version ∧ ≥1 mount. Packaging: `/api/package/scrape_data` (site mirror zip),
`/api/package/user_data` (DB + settings + gui_state) and `/api/package/restore`.

## Invariants

- Derived USER tables (`taper_attributions`, `show_picks`, song index) are
  **never** exported — a master import can't clobber local computation
  ([Database](Database.md) tiers).
- Curator decisions that must survive sync live in MASTER tables
  (`taper_confirmations`, `lb_missing`, manual overrides), not derived ones.
- Everything hash-verifies (SHA256 manifest) before it touches the DB or
  `data/site/`.
