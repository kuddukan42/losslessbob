# Collection Pipeline

> Sources: `PROJECT.md` §Collection Routing & Pipeline Filing, §Collection
> Integrity Monitor, §`pipeline_file_hash` · `archive/specs/PIPELINE_STRUCTURAL_TIER_DESIGN.md` ·
> `backend/filer.py` · `backend/integrity_monitor.py` · `tools/lb_nc.py` ·
> Status: fresh 2026-10-18

The path a new folder takes from "dropped in the queue" to "filed, verified,
and monitored in the collection". GUI: ScreenPipeline (+ shared
`folderQueueStore` across Pipeline/Library/Collection/Spectrograms) —
[screenshot](../screenshots/pipeline.png).

## Pipeline steps

`verify → lookup → lbdir → rename → file` — stages 1–4 run via
`/api/pipeline/run/start` (async, TODO-205 P2: folders grouped by source
device, max one in-flight per device, 1–4 workers); the actual file *move*
stays on `/api/pipeline/file/start` (single-folder, background thread).

## Structural tier (TODO-205, all phases shipped)

`pipeline_file_hash` caches per-file md5/ffp/sha256, valid only while the stored
`(size, mtime)` matches a fresh stat. `pipeline_folder_state` caches per-folder step
verdicts under a stat-sweep `fingerprint`; `force` bypasses, `/api/pipeline/state`
warm-starts the GUI buckets. The file step is always re-resolved live. Schema:
PROJECT.md §`pipeline_file_hash`.

## Filing (step 5)

Year-based routing: `collection_mounts` (live online/disk checks) + `collection_routes`
(year -> mount + sub_path). Guards: `stale_verify`, `no_date`, `no_route`,
`mount_offline`, `dest_exists`. Copies (`filer._copy_verified`) stage in a hidden
`.<name>.partial`, fsync, are SHA-256 tree-verified (`filer.hash_tree`), then renamed
into place before the source is removed; failure leaves the source untouched
(`hash_mismatch` / `fs_error`).

## Terminal commander (`tools/lb-nc`)

Two-pane NC-style TUI (`tools/lb_nc.py`) over the collection mounts. Marks each LB
folder canonical / misfiled / stray / duplicate / blocked against the year route; F7
files to the route, F6 moves to the other pane's mount, F8 lists misfiled rows. It has
no filesystem code of its own for filing — writes go through `/api/pipeline/file/*`
(rename via `/api/folder/rename`). Refuses a cross-drive batch leaving < 2 GB free.
The move queue persists in `data/lb_nc_queue.json` (resumed at next start; a move still
running in the backend is adopted), undo journal is `data/lb_nc_undo.jsonl`, duplicate
losers go to `_duplicates/`. Key list: PROJECT.md `lb_nc.py` entry and the in-app help.

## After filing

- Renames audit to `rename_history`; sticky links in `folder_lb_link`.
- **Integrity monitor** (TODO-284): background per-mount or whole-collection
  scans → `collection_integrity_scans` (history) +
  `collection_integrity_status` (latest per-LB verdict:
  pass/content_issue/tag_issue/missing_files/no_lbdir/error) → per-mount GUI
  badges. Watchdog file-change alerts land in `integrity_events`.
- NFT folder-suffix guidance comes from `lb_master`
  ([Master-Data-Sync](Master-Data-Sync.md)).

## Gotchas

- `pipeline_file_hash` / `pipeline_folder_state` are pruned daily by
  `scheduler.start_pipeline_cache_pruner` (`db.prune_pipeline_cache`, TODO-364): only
  rows whose folder is gone *and* whose parent dir still exists — an unmounted drive
  never triggers a prune.
- Paths with lone surrogates are never cached (SQLite TEXT can't bind them) —
  always hashed fresh.
- Cross-device moves fall back to copy+delete with the same hash verification.
