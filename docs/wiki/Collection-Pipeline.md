# Collection Pipeline

> Sources: `PROJECT.md` §Routing & Pipeline Filing (~line 1511), §Integrity
> Monitor (~1532), §pipeline tables (~490) ·
> `instructions/complete/PIPELINE_STRUCTURAL_TIER_DESIGN.md` · `backend/filer.py` ·
> Status: seeded 2026-07-22

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

- `pipeline_file_hash` — per-file hash cache (md5/ffp/sha256) keyed by
  folder+relpath; a read hits only when stored `(size, mtime)` match a fresh
  stat (rule R1).
- `pipeline_folder_state` — per-folder cached step verdicts under a
  stat-sweep `fingerprint` (never the dir's own mtime); valid only while the
  recomputed fingerprint matches (R2/R3). `force` bypasses; warm-start
  (`/api/pipeline/state`) repaints GUI buckets after restart. The file step
  is display-only in cache — always re-resolved live (P8).

## Filing (step 5)

Year-based routing: `collection_mounts` (with live online/disk-usage checks) +
`collection_routes` (year → mount + sub_path; bulk upsert, per-year preview
dry-run). Filing guards: `stale_verify` (folder changed since last pipeline
check), `no_date`, `no_route`, `mount_offline`, `dest_exists`. Whenever data
is actually copied, the copy is **SHA-256 tree-verified against the source**
(`filer.hash_tree`) before the original is removed — a mismatch deletes the
bad copy and leaves the source untouched (`hash_mismatch`).

## After filing

- Renames audit to `rename_history`; sticky folder→LB links in
  `folder_lb_link`.
- **Integrity monitor** (TODO-111): background per-mount or whole-collection
  scans → `collection_integrity_scans` (history) +
  `collection_integrity_status` (latest per-LB verdict:
  pass/content_issue/tag_issue/missing_files/no_lbdir/error) → per-mount GUI
  badges. Watchdog file-change alerts land in `integrity_events`.
- NFT folder-suffix guidance comes from `lb_master`
  ([Master-Data-Sync](Master-Data-Sync.md)).

## Gotchas

- Paths with lone surrogates are never cached (SQLite TEXT can't bind them) —
  always hashed fresh.
- Cross-device moves fall back to copy+delete and get the same hash
  verification as copies.
