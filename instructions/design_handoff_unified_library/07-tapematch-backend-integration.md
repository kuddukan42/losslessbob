# 07 · TapeMatch backend integration (planned, not yet implemented)

> **Status: planned only.** Nothing in this doc has been built. This is the
> design for the backend work that `06-gap-analysis.md` §B1 explicitly deferred
> ("ingesting TapeMatch's output into a real DB table + API is a separate future
> project, not part of this implementation pass") — that future project, planned
> out now that the underlying data has grown enough to be worth wiring up.

## Why

The user is actively running `tools/tapematch/` (an offline CLI) across all
~800+ Dylan show dates. It detects when multiple circulating LB# recordings of
the same show are actually the same master tape transferred multiple times
("families") and writes results to a standalone SQLite DB,
`tools/tapematch/observations.db` — currently 834 runs / 804 distinct concert
dates / 3,523 sources / 7,158 pairwise comparisons, and growing.

`03-data-contract.md`'s Family entity (Entity 3) and the no-families fallback
were designed to let the Library screen ship before this data existed. It now
exists in real volume. This doc designs how it gets from `observations.db` into
the main app DB and exposed via API, so that when the Library screen is built,
its recording-lens adapter can read `fam` / `fam_label` / `fam_conf` / `fam_by`
per recording with **zero clustering logic of its own** — matching the
contract's "this documents the shapes the UI reads, not how the backend
clusters."

**Verified, not assumed:** the join key is simply `lb_number` (an INTEGER
already present in tapematch's own `sources` table) — there's no need to
reconcile `entries.date_str`'s messy free-text format (e.g. `'5/xx/87'`,
`'7/28/00'`) against tapematch's clean ISO `concert_date`. Tapematch already
resolved and stored the LB# itself per source.

**Two assumptions from an earlier draft of this plan were checked against the
real `observations.db` data and disproven** — the design below reflects the
corrected versions, not the original guesses:

- *"Latest run wins" is not safe.* E.g. `1995-07-08`'s first run found/ran 9
  sources; two later reruns found/ran only 8. A later timestamp is sometimes a
  **regression** (a partial/interrupted rerun), not an improvement.
- *A naive `fam_id` keyed by the tool's own run-scoped `family_id` integer is
  unsafe.* `family_id` numbering is scoped to a single run and can shift
  between reruns of the same date. A re-sync could silently repoint an
  existing `fam_id` at a *different* set of recordings — a real correctness
  bug (e.g. if a `fam_id` is ever cached/bookmarked client-side), not just a
  UI flicker.

## Design

### 1. New tables (`backend/db.py` `SCHEMA_SQL`)

```sql
CREATE TABLE IF NOT EXISTS recording_families (
    lb_number      INTEGER PRIMARY KEY,
    fam_id         TEXT NOT NULL,
    concert_date   TEXT NOT NULL,
    run_id         TEXT,
    imported_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recording_families_concert_date
    ON recording_families(concert_date);
CREATE INDEX IF NOT EXISTS idx_recording_families_fam_id
    ON recording_families(fam_id);

CREATE TABLE IF NOT EXISTS tapematch_family_meta (
    fam_id          TEXT PRIMARY KEY,
    concert_date    TEXT NOT NULL,
    label           TEXT,
    label_override  TEXT,
    by              TEXT NOT NULL DEFAULT 'ai',
    conf            REAL,
    note            TEXT,
    member_count    INTEGER NOT NULL,
    run_id          TEXT,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **Singletons are synced as `label='Solo'` (member_count 1).** Every tapematch
  `source` row gets *some* `family_id` (even families of one).
  *Originally this plan excluded singletons (`member_count >= 2` only), expecting
  them to fall through to the no-families fallback.* **As shipped (CHANGELOG
  2026-06-19) that was changed:** a singleton is a recording TapeMatch *did*
  process and confirm had no acoustic sibling on the date — that's a real signal,
  not absence of data. Dropping it made the performance lens render a confusing
  bare "Recording LB-XXXXX" fallback row indistinguishable from a never-analysed
  recording. So singletons now get a `fam_id` of `f"{concert_date}#{lb_number}"`,
  `label='Solo'`, `by='ai'`, `conf=NULL`, `member_count=1`, and render as
  "Solo LB-XXXXX". Only recordings TapeMatch never ran at all (no `source` row)
  fall through to the no-families fallback (`03-data-contract.md`).
- **`fam_id` is deterministic, not run-scoped**:
  `f"{concert_date}#" + "-".join(str(lb) for lb in sorted(member_lb_numbers))`.
  Same membership → same id across re-syncs (safe to cache, safe to
  bookmark). Different membership → a genuinely different id, which is
  correct (it's a different cluster) rather than a silent repoint.
- **`label`** is auto-generated per show — `"Family A"` / `"Family B"` / …
  ordered by `member_count` desc (ties broken by lowest tapematch
  `family_id`). No curator effort required for v1.
- **`label_override`** is reserved, unused by this pass, for a future
  curator-naming UI — added now so that feature won't need its own migration
  later.
- **`by`**: `'ai'` by default; bumped to `'ai+lb'` if any in-family pair has
  `lb_says_same=1` (the LB page text itself corroborates the grouping). This
  pipeline never produces bare `'lb'` (purely-manual, no-AI) — that's a
  different, not-yet-built ingestion path (curator-confirmed via a future UI),
  out of scope here.
- **`note`** stays NULL for v1 — no structured source for it yet (tapematch's
  prose `analysis.md` write-ups aren't structured into a one-line note).
- **Add both tables to `MASTER_TABLES`** (`backend/db.py:37-57`) — this is
  derived analysis tied to canonical show/lb_number data, the same category as
  `lb_alias` / `dylan_performances`, not user-local state like
  `my_collection`. Bump `MASTER_SCHEMA_VERSION` (currently 6, `db.py:35`) to 7
  with a comment, matching the existing convention.

### 1a. Required fix to `import_master_db()` — backward-compat guard

Adding these tables to `MASTER_TABLES` plugs them into the existing
`import_master_db()` pipeline (`backend/db.py:3762-3850`), which for every
table in that list unconditionally runs:

```sql
DELETE FROM main.<t>;
INSERT INTO main.<t> SELECT * FROM incoming.<t>;
```

This is pre-existing, intentional, already-safety-netted behavior (automatic
`pre_master_import` backup, SHA256 + schema-version + downgrade guards) — not
new destructive behavior introduced by this plan. **But it has a real gap**:
if anyone ever imports a master snapshot exported *before* this feature
shipped, the attached `incoming` database won't have
`incoming.recording_families` / `incoming.tapematch_family_meta` at all, and
the unconditional `INSERT INTO main.<t> SELECT * FROM incoming.<t>` will
error out (no such table) instead of degrading gracefully.

**Fix, scoped to `import_master_db()`'s existing per-table loop**: before the
`DELETE`+`INSERT` for each table in `MASTER_TABLES`, check whether the table
exists in the attached `incoming` DB (`SELECT name FROM incoming.sqlite_master
WHERE type='table' AND name=?`). If absent, skip that table — leave the local
copy untouched — rather than failing the whole import. This is a general
forward-compatibility fix for *any* future `MASTER_TABLES` addition, not
something special-cased to TapeMatch; it just happens to be the first time
this gap would be hit. Record which tables were skipped in the function's
returned summary dict (e.g. `skipped_tables: [...]`) so a thin/older snapshot
import is visibly reported, not silently incomplete.

### 2. Sync function — new module `backend/tapematch_sync.py`

`sync_tapematch_families(db_path=None, observations_db_path=None) -> dict` (stats):

1. Open `observations.db` **read-only** via URI (`file:{path}?mode=ro`,
   `uri=True`, short timeout), wrapped in a retry/backoff (2–3 attempts)
   catching `sqlite3.OperationalError` — the tapematch CLI may hold a write
   lock mid-run; fail the sync cleanly with a clear "a tapematch run may be in
   progress, try again" message rather than crashing.
2. For each `concert_date`, pick the best run: **highest `n_sources_ran`,
   ties broken by latest `run_id`** — not bare latest-wins (proven unsafe
   above). Note: at least one date (`1996-07-21`, 7 reruns) ties on
   `n_sources_ran` but still produces different family counts across runs,
   implying the tool's calibration drifted over time during development.
   Tie-break-by-latest is the reasonable default (assume later calibration is
   better) but this specific date (and any others like it) is worth a manual
   spot-check — not a blocker for shipping v1.
3. From that run's `sources`, group by `family_id` and compute the
   deterministic `fam_id`. Groups with `member_count >= 2` become normal
   families (`label='Family A/B/…'`); singletons (`member_count == 1`) are
   emitted as `label='Solo'` rows rather than dropped (see §1).
4. From that run's `pairs` (filtered to `tapematch_verdict='same_family' AND
   family_id_a=family_id_b`), average `corr` per family → `conf`; check
   `lb_says_same` for the `by` bump.
5. **Upsert, not delete-then-insert**, all wrapped in one transaction per
   concert_date (`with conn:` / `BEGIN IMMEDIATE`):
   - `tapematch_family_meta`: `INSERT ... ON CONFLICT(fam_id) DO UPDATE SET
     label=excluded.label, by=excluded.by, conf=excluded.conf,
     member_count=excluded.member_count, run_id=excluded.run_id,
     imported_at=excluded.imported_at` — **never touches `label_override`**
     on conflict, so a future curator edit survives re-syncs as long as
     membership (and thus `fam_id`) is unchanged.
   - `recording_families`: same upsert pattern keyed on `lb_number`.
   - Cleanup: `DELETE` rows for that `concert_date` whose `fam_id` (or
     `lb_number`, for the membership table) isn't in this sync's fresh set —
     handles families that genuinely dissolved or changed membership.
6. Returns `{dates_processed, families_written, recordings_linked, errors: [...]}`.

This avoids a delete-then-reinsert race entirely: a concurrent reader of the
families endpoint mid-sync sees either the old or new row for a given
`fam_id`/`lb_number`, never a window with neither.

### 3. Trigger — manual endpoint, no startup coupling

- `POST /api/tapematch/sync` (new route in `app.py`) → calls
  `tapematch_sync.sync_tapematch_families()`, returns the stats dict. Wire
  this as the last step of the user's existing `/tapematch-batch` workflow
  once a batch of dates is done.
- **Do not** call this synchronously inside `init_db()` (`app.py` calls it at
  startup, `app.py:188` and again at `:569`) — that would make backend
  startup depend on `observations.db` existing and being unlocked, on every
  machine, including fresh clones with no tapematch data at all. If an
  "always fresh on boot" convenience is wanted later, fire it from a
  background daemon thread post-startup (matching the existing
  `_rebuild_bloom_bg`-style pattern in `backend/db.py`), not inline — but
  that's a nice-to-have, not part of this pass.

### 4. Expose via a new, separate endpoint — not bolted onto `/api/search`

`GET /api/tapematch/families` → flat list, no pagination needed (a couple
thousand rows max at full catalog scale): `[{lb_number, fam_id, fam_label,
fam_conf, fam_by, concert_date}]` (`fam_label` = `label_override ?? label`).

**Rejected alternative:** extending `/api/search`'s row-building SQL.
`search_entries()` has three separate hand-written SQL paths (FTS5 / no-query
/ LIKE-fallback) that would all need the same `LEFT JOIN`s kept in sync, and
it would push 4 nullable columns onto `ScreenSearch`/`ScreenCollection`
responses that have nothing to do with this feature. A second small fetch
that the Library screen merges client-side by `lb_number` is the same pattern
the project already uses for show-grouping (`06-gap-analysis.md` §B3: rollups
derived client-side, not server-aggregated) — just applied twice.

### 5. Frontend wiring (when the Library screen is built — not yet)

The Library's recording-lens data adapter fetches `/api/tapematch/families`
alongside its existing recordings fetch, merges by `lb_number` into each
row's `fam` / `fam_label` / `fam_conf` / `fam_by` fields (per
`03-data-contract.md` Entity 1/3), then builds the per-show `fams{}` map by
grouping the merged rows — exactly mirroring the already-planned client-side
`(date_str, location)` show-grouping.

## Explicitly deferred

- `dup` / `upgrade` / `xref` recording-level hints (unrelated to tapematch,
  already deferred in `06-gap-analysis.md` §B7).
- Any curator UI for setting `label_override` or for confirming/rejecting a
  family (`human_judgment` ingestion — currently always NULL in
  `observations.db`, no UI produces it yet).
- `by: 'lb'` pure-manual provenance — not produced by this pipeline at all.
- Background/scheduled auto-sync — manual trigger only for this pass.

## Files to touch (when implemented)

- `backend/db.py` — two new `CREATE TABLE IF NOT EXISTS` blocks in
  `SCHEMA_SQL`, add both table names to `MASTER_TABLES` (`:37-57`), bump
  `MASTER_SCHEMA_VERSION` (`:35`) to 7, and add the missing-table skip guard
  to `import_master_db()`'s per-table loop (`:3762-3850`, see §1a) —
  **required before this ships**, not optional polish.
- `backend/tapematch_sync.py` — new module, `sync_tapematch_families()`.
- `backend/app.py` — two new routes: `POST /api/tapematch/sync`,
  `GET /api/tapematch/families`.
- `CHANGELOG.md` / `PROJECT.md` / `TODO.md` — per project convention, log the
  new routes + DB schema change at implementation time.

## Verification (when implemented)

1. `.venv/bin/python3 -m py_compile backend/tapematch_sync.py backend/db.py backend/app.py`.
2. Restart the backend (per project rule: always restart after backend
   changes before verifying).
3. `curl -X POST http://localhost:5174/api/tapematch/sync` — confirm stats
   JSON, check `dates_processed` / `families_written` look sane (~804 dates;
   `families_written` includes `'Solo'` singleton rows, so it tracks the count
   of distinct analysed recordings, not just multi-member clusters).
4. `curl http://localhost:5174/api/tapematch/families | python3 -m json.tool | head` —
   spot-check a known multi-source date (e.g. `1995-07-08`) appears with the
   right `lb_number`s grouped under one `fam_id`.
5. Re-run sync a second time with no underlying data change — confirm
   `tapematch_family_meta` / `recording_families` row counts are stable
   (upsert idempotency), and any manually-set `label_override` (insert one by
   hand for the test) survives the second sync.
6. Spot-check the `1996-07-21` ambiguous-rerun case manually — confirm which
   run got picked and that its family count looks reasonable, since this is
   the one date flagged as not fully resolved by the "highest `n_sources_ran`,
   latest tie-break" rule.
7. **Backward-compat check (§1a):** construct or use a pre-feature master
   snapshot (one exported before `recording_families`/`tapematch_family_meta`
   existed) and run `import_master_db()` against it. Confirm the import
   succeeds, those two tables are left untouched locally, and they appear in
   the returned `skipped_tables` list — instead of the import erroring out.
