# Pipeline Structural Tier — Design Doc (P7 + P1 + P2, with P3 + P8)

**TODO-205.** Source spec: `instructions/FABLE_PIPELINE_DEVLOOP_IDEATION.md`
(P1 §33–37, P2 §39–43, P3 §45–49, P7 §69–73, P8 §75–79, sequencing §159–163,
invariants §165–171).
**Author:** Fable 5 (orchestrated), 2026-07-07.
Design only — no code changes in this document.

---

## 1. Goal & Scope

The quick-win tier (D1/D2/D3/P5) shipped 2026-07-07, including an **Auto-collect**
toggle that files clean folders with no click. Auto-collect trusts the pipeline's
verify verdicts, so the structural tier must never let a *stale* "pass" reach it.

This doc designs the four structural ideas the spec says to design **together**,
because they share one SQLite cache/state layer and one job model:

| Idea | What it delivers | Covered here |
|---|---|---|
| **P7** | Persist pipeline row state; resume across restart | §2 (state table), §3, §7 |
| **P1** | Shared per-file hash cache; one hash pass per folder | §2 (hash table), §3, §4 |
| **P2** | Async multi-folder job model (replace serial per-folder POSTs) | §4 |
| **P3** | Background LBDIR prefetch out of the stage chain | §5 |
| **P8** | Collect `blocked` as a live view, not an attention verdict | §6 |

**Out of scope** (deferred per spec §163): **P4** (verify∥lookup single-parse),
**P6** (filing queue / per-mount workers — `_FILE_JOB` stays a singleton),
**P9** (reason-grouped triage), **P10** (merge Rename into Collect). These are
GUI/ergonomic changes that do not touch the cache or the stage-1–4 job model.

---

## 2. The Shared SQLite Layer — one design for P1 + P7

Two tables, one migration, one staleness key. Both follow the repo convention:
`CREATE TABLE IF NOT EXISTS` in `SCHEMA_SQL` **plus** a `PRAGMA table_info` +
`ALTER TABLE` block in `init_db` for additive columns (in `init_db`, db.py:1566,
mirroring the `location_geocoded` additive-column precedent at db.py:1629–1632).

### 2a. `pipeline_file_hash` — the per-file hash cache (P1)

```sql
CREATE TABLE IF NOT EXISTS pipeline_file_hash (
    folder_path TEXT NOT NULL,      -- absolute, normalised (filer.normalise_path)
    rel_path    TEXT NOT NULL,      -- posix, str(Path.relative_to(root))
    size        INTEGER NOT NULL,   -- os.stat st_size  — validation key
    mtime       REAL    NOT NULL,   -- os.stat st_mtime — validation key
    md5         TEXT,               -- full-file md5 hex (NULL until computed)
    ffp         TEXT,               -- FLAC fingerprint hex (audio only, else NULL)
    sha256      TEXT,               -- full-file sha256 hex — feeds filing tree digest
    hashed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (folder_path, rel_path)
);
```

**Key design decision — PK vs. logical cache key.** The spec calls the cache key
`(path, size, mtime)`. We make the *primary key* `(folder_path, rel_path)` and treat
`(size, mtime)` as **validation columns**, not key columns. A read is a **hit** only
when the row exists *and* its stored `(size, mtime)` equals the file's current
`os.stat`. This is functionally "keyed on `(folder_path, rel_path, size, mtime)`"
for hit/miss purposes but avoids accumulating one dead row per in-place edit — an
edit overwrites the same PK row rather than orphaning the old one.

**Critical precision — the cache must cover *every* file, not just audio.**
`verify_folder` hashes audio files only, but `filer.hash_tree` hashes **every file
under root** (`root.rglob("*")` — includes `.ffp`, `.txt`, `.jpg`, cover art). To
serve filing's source digest from cache (§2c) the single hash pass must compute and
store `sha256` for *all* files in the tree, populating `md5`/`ffp` only for the audio
subset that verify/lbdir need. Rows with `sha256` but NULL `md5`/`ffp` are normal.

### 2b. `pipeline_folder_state` — per-folder row state (P7)

```sql
CREATE TABLE IF NOT EXISTS pipeline_folder_state (
    folder_path   TEXT PRIMARY KEY,   -- normalised absolute path
    fingerprint   TEXT NOT NULL,      -- content fingerprint, see §3
    verify_json   TEXT,               -- last verify step result (dict) as JSON
    lookup_json   TEXT,
    lbdir_json    TEXT,
    rename_json   TEXT,
    file_json     TEXT,               -- stored for warm-start ONLY; never trusted (P8)
    steps_json    TEXT,               -- which steps have been run
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pipeline_state_fp ON pipeline_folder_state(fingerprint);
```

One row per folder. Each step's verdict dict (the sub-dicts of the
`_pipeline_process_folder` row) is stored as JSON. `file_json` is persisted so the
GUI can warm-start a row's appearance, but the **File step is a live view (P8) and its
cached verdict is never authoritative** — it is always re-resolved.

### 2c. Deriving filing's tree digest from the cache — byte-for-byte

`filer.hash_tree(root)` (filer.py:322) must be reproducible from cached `sha256`s.
Its algorithm, exactly:

```
tree = sha256()
rel_paths = sorted( str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() )
for rel_path in rel_paths:
    file = sha256(); for each 1 MiB chunk of content: file.update(chunk)
    tree.update( rel_path.encode("utf-8", "surrogatepass") )   # NOTE: surrogatepass
    tree.update( file.digest() )                               # raw 32 bytes, not hex
return tree.hexdigest()
```

To reproduce from cache, the derived digest MUST:

1. Enumerate the **same file set** — every file under root, from cache rows whose
   `(size, mtime)` still validate (§3). Any un-validated file forces a fresh read.
2. Sort by `rel_path` using the identical string form (`str(relative_to)`, posix on
   Linux — the running platform).
3. For each, `tree.update(rel_path.encode("utf-8", "surrogatepass"))` — the
   `surrogatepass` error handler is load-bearing for filenames with lone surrogates;
   plain `"utf-8"` would diverge. Then `tree.update(bytes.fromhex(cached_sha256))`.
   Store hex, convert to the raw 32-byte digest at combine time to match
   `file.digest()`.

**Invariant — destination is always freshly hashed.** Filing computes
`hash_tree(dest) != hash_tree(source)` (filer.py:517–536). Only the **source** side may
be served from cache. The **destination** digest is *always* computed from bytes on
disk after the copy — never cached, never derived. This preserves hash-verify-before-
remove (§8) unconditionally.

---

## 3. Staleness Model

The whole cache lives or dies on staleness correctness. Three rules:

**R1 — validate at consumption, not at write.** A cache row is written once when the
hash is computed. It is validated *every time it is read* by comparing stored
`(size, mtime)` against a fresh `os.stat` of the file. A `(size, mtime)` mismatch is a
**miss** → re-hash → overwrite the row. Never assume a written row is still valid.

**R2 — the directory-mtime pitfall.** A directory's mtime does **not** change when a
file's *content* is edited in place. Therefore the folder fingerprint (P7) must be a
**per-file aggregate**, not the folder's own mtime:

```
fingerprint = sha256( "\n".join( f"{rel_path}\t{size}\t{mtime}"
                                 for rel_path,size,mtime in sorted(stat_of_every_file) )
                    ).hexdigest()
```

Computed over every file under root (audio + checksum + art), this is a cheap
`os.stat`-only sweep — no content reads. `pipeline_folder_state.fingerprint` stores it.
Cached step verdicts are reusable **only** when the recomputed fingerprint equals the
stored one; otherwise all cached verdicts for the folder are considered stale.

**R3 — cheap revalidation sweep.** Before serving *any* cached verdict, run the
fingerprint stat-sweep (milliseconds even for large sets — no bytes read). Fingerprint
match ⇒ verdicts valid. Fingerprint miss ⇒ re-run the affected steps. This sweep also
naturally covers R1 for the hash cache: the per-file `(size, mtime)` used to build the
fingerprint is the same tuple that validates each `pipeline_file_hash` row.

### 3a. Auto-collect hard rule (P5 interaction)

Auto-collect (shipped) fires when all four stages are `ok` and `file.status == ready`.
Because it moves data with no further human check, cached verdicts feeding it get an
extra guard:

> **HARD RULE.** An auto-collect must **never** fire on a folder whose verify verdict
> was served from cache unless the R3 fingerprint stat-sweep has been re-run *in the
> same request that arms the collect* and passes. A stale "pass" that reaches
> Auto-collect would file corrupted/edited data. If the sweep fails, the row's verify
> verdict is invalidated and re-run before Auto-collect is even considered.

Manual filing is already protected by the destination re-hash on copy paths; this rule
extends that guarantee to the *decision to file automatically*.

---

## 4. Async Job Model (P2)

Model on `backend/integrity_monitor.py` (`_SCAN_JOB` + `_SCAN_LOCK` + `_CANCEL_EVENT` +
daemon thread; routes app.py:5711–5744). The `_FILE_JOB` singleton (filer.py) is
**untouched** — this parallelizes **stages 1–4 only** (verify, lookup, lbdir, rename +
the file *resolution* view; not the file *move*).

### 4a. Job state

```python
_PIPELINE_LOCK = threading.Lock()
_PIPELINE_JOB: dict = {
    "running": False,
    "folders_total": 0,
    "folders_done": 0,
    "in_progress": [],        # list of paths (N workers, unlike _SCAN_JOB's single str)
    "results": {},            # {folder_path: row}  — rows land here as they complete
    "errors": [],             # [{folder, message}]
    "steps": [],              # requested steps
    "started_at": None,
}
_PIPELINE_CANCEL_EVENT: "threading.Event | None" = None
_PIPELINE_THREAD: "threading.Thread | None" = None   # coordinator
```

All mutations under `_PIPELINE_LOCK`. `start` checks `running` under lock and returns
`busy` if set (same guard as `start_scan_async`, integrity_monitor.py:300).

### 4b. Endpoints

| Method | Path | Body / returns |
|---|---|---|
| POST | `/api/pipeline/run/start` | `{folders:[...], steps:[...], workers?:N}` → `{ok, started}` or `{ok:false, error:"busy"}` |
| GET  | `/api/pipeline/run/status` | `{running, folders_done, folders_total, in_progress, results:{path:row}, errors}` |
| POST | `/api/pipeline/run/cancel` | sets `_PIPELINE_CANCEL_EVENT`; workers stop after their current folder |

Cancel is **cooperative, per-folder**: each worker checks `is_set()` before starting
the next folder (integrity_monitor.py:211), never mid-hash.

### 4c. Workers and the same-spindle caveat

`workers = 2–3`. Naïve N-wide hashing of folders on the **same physical disk** causes
seek thrash and can be *slower* than serial (spec §43). Mitigation: group folders by
source device (`os.stat(folder).st_dev`) and run **at most one worker per device**,
capped globally at N. Implementation: a per-`st_dev` FIFO plus a global semaphore of N;
a coordinator thread dispatches. Devices with fast random access (SSD/NVMe) still get
parallelism across *different* devices; a single spinning NAS volume effectively
serializes, which is correct.

### 4d. Where the cache is consulted

`_pipeline_process_folder` (app.py:5871) is the single choke point and stays the unit of
work per folder. Inside it, per step:

- **On entry:** load `pipeline_folder_state`; run the R3 fingerprint sweep. If
  fingerprint matches and the step's JSON is present and the caller did not pass
  `force`, return the cached verdict tagged `cached: true`. Else compute.
- **verify / lbdir-verify:** consult `pipeline_file_hash` per file (§2a, R1 validation);
  compute misses in one pass; upsert results. Verify and lbdir keep **distinct verdict
  attribution** (local checksum files vs. lbdir manifest) — only the *hash pass* is
  shared, never the *verdicts* (spec §37).
- **file (source digest):** derive from cached `sha256`s per §2c; destination always
  fresh.
- **On completion:** write the fresh verdicts + current fingerprint back to
  `pipeline_folder_state`.

### 4e. SQLite write discipline

Connections are per-thread, `check_same_thread=False`, WAL, `busy_timeout=30s` (db.py).
At N=2–3 workers, cache upserts are small and infrequent, but concurrent writers still
contend on WAL's single-writer lock. **Decision: route all `pipeline_file_hash` /
`pipeline_folder_state` upserts through the existing `db_queue.py` write-queue** (which
already serializes scraper writes). Workers *read* directly via their per-thread
connection (WAL readers never block); they *write* by enqueuing, so no worker ever
blocks another on a write lock. This reuses proven infrastructure and keeps the
workers' hot path lock-free.

### 4f. Backward compatibility

**Decision: keep the synchronous `/api/pipeline/run` (app.py:6267) during and after
migration; do not version it.** Justification: (a) the async endpoints are purely
additive, lowest-risk; (b) the sync route already delegates to
`_pipeline_process_folder`, so once caching lands there, the sync path gets caching
"for free" with zero route change; (c) tests and any non-GUI caller keep working. The
sync route becomes a thin single-folder convenience wrapper; the GUI migrates to
start/poll (§7) on its own schedule.

---

## 5. LBDIR Prefetch (P3)

Today the lbdir step can block a folder's whole run on a live `scraper.scrape_entry`
(app.py:6080–6092) — the slowest, least reliable link, mid-chain.

**Trigger.** The moment Lookup resolves an `lb_number` *inside a job worker*, submit an
async prefetch of that LB's lbdir attachment (if `find_lbdir_attachment` — paths.py:68
— reports it uncached).

**Per-LB lock (does not exist today).** scraper.py has only a global scrape-status lock,
no per-LB lock. Define one:

```python
_LBDIR_PREFETCH_LOCK = threading.Lock()          # guards the registry
_LBDIR_PREFETCH_INFLIGHT: set[int] = set()        # LB numbers currently fetching
_LBDIR_PREFETCH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lbdir-fetch")
```

Submit only if `lb_number not in _LBDIR_PREFETCH_INFLIGHT` (checked under lock);
dedupes concurrent folders that resolve to the same LB. Idempotent because
`scrape_entry` (scraper.py:192) already checks DB + `attachment_path().exists()` before
downloading.

**Concurrency cap & politeness.** `max_workers=2` bounds site concurrency. Reuse
`scrape_entry`'s existing politeness (retry backoff, 60s sleep on HTTP 429, 0.5s between
attachment downloads) — no new rate-limit logic. The forum/WTRF guards stay in force.

**`lbdir: pending-fetch` state (new).** If the lbdir step runs while a prefetch for that
LB is still inflight, the step returns a new non-blocking status **`pending-fetch`**
(rather than blocking on a synchronous scrape or marking `mute`). The folder is **not**
escalated to attn. When the prefetch completes, invalidate the folder's `lbdir_json`
(clear it in `pipeline_folder_state`) so the next status/auto-complete pass re-runs
lbdir and finds the file cached.

**Auto-complete integration.** The existing GUI auto-complete effect
(ScreenPipeline.tsx:1549–1560) already resumes rows where `lookup.status === 'ok' &&
lbdir.status === 'mute'`; extend its predicate to also resume
`lbdir.status === 'pending-fetch'`. Same resume machinery, one extra status value.
(Not to be confused with the *auto-rename* effect at ScreenPipeline.tsx:1661–1682,
which requires `lbdir.status === 'ok'` and is unrelated.)

---

## 6. Collect `blocked` as a Live View (P8)

Today `_pipeline_process_folder` severity (app.py:6247–6263) escalates **any**
`file.status == 'blocked'` to `attn`, pushing already-verified work into `needs` for a
pointless full re-run. But `start_file_job` re-resolves at start anyway, so the run-time
resolution is only a *preview*.

**Split the error_codes.** `_file_blocked_label` (app.py:5862) knows five codes:

| error_code | Meaning | New treatment |
|---|---|---|
| `no_date` | Folder has no parseable date → can't route | **true attn** (needs human config) |
| `no_route` | No collection route for the year | **true attn** (needs human config) |
| `mount_offline` | Destination mount asleep/unplugged | **transient → shelf** (live re-resolve) |
| `dest_exists` | Target already exists (TOCTOU-y) | **transient → shelf** (live re-resolve) |
| `db_error` | Transient DB read failure | **transient → shelf** (retryable) |

**Severity change (app.py:6253).** Replace the unconditional
`or file_status == "blocked"` with: escalate to attn only when
`file_status == "blocked" and error_code in {"no_date", "no_route"}`. Transient blocks
fall through to the existing `shelf`/`done` logic and land in **shelf** with a
"mount offline / already exists" chip (GUI).

**GUI bucketing (serverRowToPipeline, ScreenPipeline.tsx:209–232).** A blocked row with
a transient code maps to **shelf**, not needs, carrying its chip. `no_date`/`no_route`
still map to needs.

**Live re-resolution.** The Collect panel already re-resolves dest via
`POST /api/pipeline/file/preview` on mount override (`CollectReadyDetail`,
ScreenPipeline.tsx:1003–1044). Extend that to re-resolve **on panel open and on a poll
tick**, so a shelved transient-block row clears itself when the mount returns — without a
full pipeline re-run. Mount online-ness already arrives inside the file step's `mounts`
array, so no new poll is needed here.

**Retry-blocked sweep.** Add a "retry blocked collects" action (and/or auto-retry when a
mount comes back online, piggybacking existing reachability checks) that re-runs only the
**file** step for shelved transient-block rows. `no_date`/`no_route` rows are excluded —
they need human input.

---

## 7. GUI Migration

| Area | Today | After |
|---|---|---|
| `runSteps` (1496–1530) | serial, 1 folder per `POST /api/pipeline/run`, AbortController + stopRef | `POST /api/pipeline/run/start` once, then poll `GET /run/status`, applying `mergeServerRow` as rows land — reuse the **400ms filing-poll pattern** (1755–1780) |
| `_pipelineCache` Map (155–156) | in-memory, lost on reload | **warm-start only**: hydrate row appearance from the last known state; server `pipeline_folder_state` is the source of truth. On screen mount, one status/state fetch rehydrates buckets |
| Queue persistence | `useFolderQueueStore` has **no** persist middleware — queued paths are lost on restart (spec §65 was wrong) | add zustand **persist** middleware (localStorage key e.g. `'lbb-pipeline-queue'`, mirroring `useSettingsStore`'s `'lbb-settings'`). Paths persist client-side; verdicts persist server-side. Two-part by design: cheap path list local, expensive verdicts in SQLite |
| Cancel | AbortController + stopRef | `POST /api/pipeline/run/cancel` stops the backend job; keep `stopRef` to stop the client poll loop |

**Key decision — queue vs. state split.** The *queue* (which folders the user is working)
is a small path list and belongs in localStorage (matches the existing settings-store
pattern, no schema needed). The *row state* (verdicts, hashes) is expensive and belongs
in SQLite (`pipeline_folder_state`). P7 "resume across restart" = localStorage restores
*which* folders + SQLite restores *their verdicts*, joined on screen mount. This fixes the
gap the spec mis-attributed (it assumed the queue already persisted).

---

## 8. Invariants (restated against this design)

| Invariant (spec §165–171) | How this design preserves it |
|---|---|
| **Hash-verify-before-remove** | P1 caches **source** hashes only, revalidated by `(size,mtime)` at filing time (R1); the **destination** is always freshly `hash_tree`'d after copy (§2c). The Auto-collect hard rule (§3a) forbids firing on an unswept cached verify verdict |
| **LBDIR-before-Rename** (TODO-137) | Stage order in `_pipeline_process_folder` is unchanged; P3 only *prefetches* the lbdir file earlier, it does not reorder the lbdir *stage* |
| **Single-writer filing** | `_FILE_JOB` singleton untouched; P2 parallelizes stages 1–4 only; no per-mount filing parallelism (that's P6, out of scope) |
| **SQLite idempotency** | Both new tables use `CREATE TABLE IF NOT EXISTS` + the `PRAGMA table_info`/`ALTER TABLE` additive-column pattern (db.py:1566) |
| **Pins survive renames** (BUG-212) & **qBittorrent sync on path change** | Untouched — this tier changes hashing, job dispatch, and bucketing, not `folder_lb_link` rekeying or qbt sync |

---

## 9. Phased Implementation Plan

Each phase is session-sized, independently verifiable, and ships value or is inert.
Ordering rationale below the table.

| Phase | Scope | Verify |
|---|---|---|
| **1. Schema** | Add `pipeline_file_hash` + `pipeline_folder_state` to `SCHEMA_SQL`; ALTER-idempotency block in `init_db`; db helpers: `upsert_file_hash`, `get_file_hash`, `folder_fingerprint`, `get/put_folder_state`. No behaviour change | `py_compile`; `/backend-restart`; unit test: fingerprint stability + hash-cache round-trip; **derived tree digest == `hash_tree(fixture)`** on a folder with a surrogate-containing filename |
| **2. P2 async plumbing** | `_PIPELINE_JOB`/lock/cancel/thread; `/run/start`, `/run/status`, `/run/cancel`; per-`st_dev` grouping + N-semaphore. `_pipeline_process_folder` still reads nothing from cache. Keep sync `/run` | `/backend-restart`; curl start→status→cancel on a small folder set; confirm sync `/run` unchanged |
| **3. P7 state persistence** | `_pipeline_process_folder` writes verdicts + fingerprint to `pipeline_folder_state` after each run; reads cached verdicts (`cached:true`) on fingerprint match; honours `force`; writes via `db_queue` | `/backend-restart`; re-run a folder → verdicts return `cached:true`; touch a file → fingerprint miss → re-run |
| **4. P1 hash consultation** | `verify_folder` / `verify_folder_lbdir` consult `pipeline_file_hash` (R1 validation); one hash pass fills md5/ffp/sha256 for audio + sha256 for all files; filing source digest derived from cache; destination always fresh; wire the Auto-collect §3a sweep | `/backend-restart`; verify verdict byte-identical to pre-change on a fixture; hash-equivalence test; deliberately edit a file post-verify → sweep blocks auto-collect |
| **5. P3 prefetch** | Per-LB lock + registry + `_LBDIR_PREFETCH_POOL`; prefetch on lookup resolution; `pending-fetch` status; invalidate `lbdir_json` on completion; extend GUI auto-complete predicate | `/backend-restart`; simulate uncached LB → lbdir shows `pending-fetch`, then resumes cached; `/gui-check` |
| **6. P8 bucketing** | Severity split (transient vs. true-attn error_codes) at app.py:6253; GUI shelf chip + `serverRowToPipeline` mapping; live re-resolve on panel open/poll; retry-blocked sweep | `/gui-check`; asleep-mount folder lands in shelf not needs; wake mount → clears without full re-run |
| **7. GUI migration** | `runSteps`→start/poll; `_pipelineCache`→warm-start; queue `persist` middleware; cancel→`/run/cancel` + poll stop | `/gui-check`; restart app → queue + verdicts restored; cancel mid-run stops backend + client |

**Ordering rationale.**
- **Phase 1 first** because P1 and P7 share the same tables and fingerprint; building
  the schema once avoids doing it twice.
- **P2 (Phase 2) before P1 consultation (Phase 4)** — spec §162's explicit "do before
  P1" note. The job model decides *where* the cache is read/written (worker threads,
  connection discipline, write-queue routing); wiring cache reads into
  `_pipeline_process_folder` before the concurrency story exists would have to be
  redone once workers land.
- **P7 (Phase 3) before P1 (Phase 4)** because P1's per-file hashes are consumed by, and
  revalidated through, the same fingerprint/state layer P7 establishes.
- **P3, P8, GUI last** — additive and lower-risk; P8 and the GUI migration depend on the
  async endpoints and the persisted state existing first.

---

## 10. Open Questions / Deferred to Implementation

1. **Cache eviction / growth.** `pipeline_file_hash` grows with every distinct file ever
   hashed. Do we prune rows whose `folder_path` no longer exists, or whose `hashed_at`
   is older than N months? Proposed: a cheap startup sweep dropping rows for missing
   folders; decide the age cap during Phase 1.
2. **`ffp` for non-FLAC / SHN.** `ffp` is FLAC-only; SHN sets use shntool. Confirm the
   column stays NULL for SHN and that lbdir/verify never read `ffp` for SHN folders.
3. **Worker count default.** N=2 vs. 3 — measure on the real NAS. The per-`st_dev`
   grouping caps same-disk concurrency at 1 regardless, so N mostly matters for
   multi-device imports.
4. **`force`/re-check affordance.** Spec §72 wants a GUI "re-check" button to bypass the
   cache. Confirm placement (per-row vs. header) and whether it clears state or just sets
   `force` on the next run.
5. **Fingerprint cost on huge trees.** The stat-sweep is O(files) `os.stat` calls. For a
   folder with thousands of files this is still milliseconds, but confirm no pathological
   set (deeply nested art dumps) makes it noticeable; if so, cache the fingerprint keyed
   on the folder's own mtime as a *fast-path only when it changed* (never as the sole
   staleness signal — R2).
6. **`pending-fetch` timeout.** If a prefetch never completes (site down), how long
   before `pending-fetch` degrades to the old synchronous-scrape fallback or a soft
   error? Propose a per-LB deadline; decide value in Phase 5.
```
