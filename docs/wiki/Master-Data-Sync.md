# Master Data & Sync

> Sources: `PROJECT.md` §lb_master (~line 391), §Flat File / Xref Ingest / Master
> Data / Onboarding routes (~1215–1277) · `docs/data_ownership.md` ·
> `backend/db.py` · `backend/flat_file.py` ·
> Status: seeded 2026-07-22

How curator-authored data reaches every installation, and how per-LB status is
kept trustworthy. Curator flag: `meta.is_curator` (local-only, never shipped);
curator-only routes 403 without it.

## lb_master — the integrity spine

`lb_master` is the single source of truth for whether an LB number is
`public`/`private`/`missing`/`nonexistent`, reconciled from `entries`,
`checksums`, `entry_files`, `lb_missing` by `reconcile_lb_master()` (full
rebuild backs up the DB first). Curator `manual_override` pins a status and
wins over reconciliation; transitions log to `lb_status_history` with a
`trigger_event`. Flags: `needs_review` (ambiguous), `public_no_checksums`.
Feeds GUI badges, the **NFT suffix** for folder naming
(`/api/lb_master/<lb>/nft`), and forum-posting guards. Overrides
export/import as JSON (import is curator-only, history-logged).

## Distribution channels

| Channel | What ships | How |
|---|---|---|
| Flat-file releases | `checksums` updates from the download page | discover → download → diff → apply (auto-backup, changelog per row, lb_master reconcile); prompting deferrable |
| Master snapshots | All `MASTER_TABLES` + `MASTER_META_KEYS` | `export_master_db`: VACUUM INTO → drop USER tables → stamp versions → verify → SHA256 + manifest. **Channels**: `public` (default — private-entry metadata blanked, TODO-253) vs `full` (friends only). GitHub release upload **refuses any non-public manifest** |
| Site-data packages | `data/site/` mirror (core / files parts) | zip + manifest → `sitedata-*` GitHub releases; install verifies SHA256 *before* extraction |
| Xref ingest (TODO-252) | Mirror `LBF-*-xref-*` filesets → `checksums` | **Reviewed import path**: scan → stage → curator approve/reject; approvals never automatic |

Import side: `/api/master/import` validates manifest SHA256, refuses
newer-schema snapshots, takes a `pre_master_import` backup, copies only
MASTER tables/meta keys, rebuilds FTS. GitHub check/install flows are
SSE-streamed with progress. `MASTER_SCHEMA_VERSION = 11`.

## Onboarding

`/api/onboarding/status` gives the first-run checklist (entries, master
version, sitedata parts, mounts, collection); `complete` = entries ∧
master_version ∧ ≥1 mount. Whole-user-data backup/restore via
`/api/package/user_data` + `/api/package/restore`.

## Invariants

- Derived USER tables (`taper_attributions`, `show_picks`, song index) are
  **never** exported — a master import can't clobber local computation
  ([Database](Database.md) tiers).
- Curator decisions that must survive sync live in MASTER tables
  (`taper_confirmations`, `lb_missing`, manual overrides), not derived ones.
- Everything hash-verifies (SHA256 manifest) before it touches the DB or
  `data/site/`.
