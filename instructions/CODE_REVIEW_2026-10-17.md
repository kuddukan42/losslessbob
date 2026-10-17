# Code Review — Obsolete, Orphaned & Simplifiable Code (2026-10-17)

Branch reviewed: `feat/dossier-redesign` @ `6beb1932`. Read-only review: nothing here has been
changed yet. Every item gives the evidence and a recommended action. Effort: S (<30 min),
M (an hour or two), L (a session or more).

**Method.** `ruff` (repo config plus extra rules F/ERA/SIM/B/RET, also over the excluded `tools/`),
`vulture 2.14` (60% confidence, Flask route decorators ignored), a full AST import graph of every
tracked `.py`, a route-usage scan (all 388 Flask routes checked against `gui_next/src`, the
backend HTML pages, `tools/`, `cli.py`, `.claude/` and `tests/`), `tsc --noUnusedLocals` on the
renderer and main process, an export-reference scan of `gui_next/src`, a dependency-usage check
for each package in `requirements.txt`, and a check of tracked-file sizes. `knip` could not run:
it crashes against the repo's TypeScript version (`ts.getDefaultLibFilePath is not a function`).

**Caveat on "orphan".** These are static findings. Anything reached by name at runtime, called by
hand with `curl`, or kept on purpose for a planned feature shows up as a false positive. The
"no caller" lists are leads to confirm before anything is deleted.

---

## 1. Repository hygiene (highest impact)

| # | Finding | Evidence | Recommendation | Effort |
|---|---|---|---|---|
| H1 | **1.6 GB embedding cache is committed to the public repo** | `tools/tapematch/embed_cache_12x/` holds 2,465 `.npz` files, tracked since `936e0a64` (2026-07-06). `.gitignore:64-65` covers `embed_cache/` and `embed_cache_tierc/` but **not** `embed_cache_12x/`. The git pack is 1.68 GiB. No code refers to `embed_cache_12x` by name. | `git rm -r --cached tools/tapematch/embed_cache_12x` and add it to `.gitignore` (or use a glob such as `tools/tapematch/embed_cache*/`). Rewriting history with `git filter-repo` to shrink the clone is optional, but it means a force-push to a public repo, so that is tj's call. | S (untrack) / M (history) |
| H2 | Run logs and generated outputs are tracked | `tools/tapematch/logs/*.log` (6 files; `rescore_20260717.log` is 4 MB), `tools/tapematch/calib_logs/` (85 files), `tools/adhoc_quality/adhoc_report.pdf` + `adhoc_tapematch.log`, `tools/tapematch/calibration_audit.{json,html}` (~5 MB), `last_run.json`, `todo324_recheck_queue.tsv`, `validate_polarity_results.jsonl` | Untrack and ignore `logs/` and `calib_logs/`. Keep the datasets that tests or calibration read (`regression_set*.json`, `*_pairs*.json`). | S |
| H3 | Database binaries in `archive/attic/` | `observations.db` + `observations.db.bak-20260612_124147` (4 MB each) | Delete. A SQLite snapshot from June has no value as history. | S |
| H4 | Three byte-identical 1.7 MB design HTMLs | `instructions/complete/pipeline_new/Pipeline Workspace (standalone).html`, the same file with `(1)`, and `instructions/complete/design_handoff_losslessbob/_source/Pipeline Workspace (standalone).html` (checked with `cmp`) | Keep one copy and delete the other two. | S |
| H5 | Untracked junk in the repo root | `TUIT-Uploader-Setup.exe`, `gluetun-wg-diag.log` | Move them out of the tree or delete them. | S |
| H6 | Throwaway scripts left behind (CLAUDE.md says delete when done) | `tools/_strip_undo_junk.py` (2026-10-01), `tools/tapematch/_survey_fix_siblings.py`, `tools/tapematch/_tierc_probe.py` | Delete. Nothing references any of them. | S |
| H7 | One-off tools nothing references any more (outside CHANGELOG/DONE files) | `tools/tapematch/mem_monitor.py` (06-03), `calib_logs/{rerun_9611,run_catval,run_confsweep}.sh`, `tools/adhoc_quality/build_adhoc_pdf.py`, `tools/tapematch/todo324_scan.py`, `bug326_{diff,scan}.py`, `tools/refetch_html_attachments.py`, `tools/wtrf/wtrf_board_archive.py`, `tools/tuit_overlay_repair.sh`, `tools/wtrf_repair_extras.py`, `tools/wtrf_requeue_disk_full.py`, `tools/migrate_gazetteer_city_country.py` | Move the finished one-shots (todo324/bug326/migrate/repair/requeue) to `archive/tools-throwaway/`. Keep the tools that are still useful and document them in `tools/SCHEDULED_JOBS.md` or a tools README so they are no longer orphans. | S |
| H8 | Windows binaries tracked | `tools/flac.exe`, `tools/libFLAC.dll`, `tools/shntool.exe` | **Keep.** `checksum_utils.py:28-34` and `sox_utils.py:85` load them for the Windows/PyInstaller build. Listed here only so nobody deletes them. | — |

---

## 2. Backend — obsolete features

### 2a. Legacy app-updater and data-download stack (from the PyQt era)

Nothing in gui_next calls any of these. They date from the self-updating desktop app, which the
Electron app does not use.

| Item | Location |
|---|---|
| `backend/updater.py`: the whole module; nothing imports it (AST graph) | `backend/updater.py:1-22` |
| `GET /api/app/version`, `/api/update/check`, `/api/update/status`, `POST /api/update/apply` | `backend/app.py:2664-2750` |
| `POST /api/data/download`, `GET /api/data/download/status` | `backend/app.py:2753-2778` |
| `_update_state`, `_data_dl_state` globals | `backend/app.py:81, 90` |
| `_restart_callback` / `set_restart_callback` (wired only by `run_backend.py`) | `backend/app.py:339-349, 9602` |
| Activity "legacy semantics for the app-updater / data-download workers" | `backend/activity.py:305` |
| `github_repo` meta setting, read only by these routes | `app.py:2690, 2740` |

**Recommendation:** delete the stack in one commit, then remove the matching activity rows. Check
first that `/api/app/version` is not used by `tools/` or CI. The scan found no caller. Effort M.

### 2b. Legacy `/api/activity/busy`

`backend/activity.py:7` describes it as AppShell's only consumer, but AppShell no longer calls it:
there is no match anywhere in `gui_next/src`. `busy_snapshot()` (`activity.py:671`) and the
"precedence order" comments at `activity.py:181, 230` exist only for this route. The only other
caller is `tests/test_activity_sse.py:177-197`.

**Recommendation:** remove the route, `busy_snapshot()`, and its test, then simplify the ordering
comments. Effort S.

### 2c. Stale PyQt references

- `gui_next/src/renderer/src/components/AboutDialog.tsx:28-29` still lists "GUI (legacy) — PyQt6
  6.7.1 · frozen" and "Attachments view — PyQt6-WebEngine". The PyQt GUI was removed 2026-07-16.
  Delete both rows.
- `pyproject.toml` `[tool.ruff] exclude` still lists `"gui"`, a directory that no longer exists.
- `pyproject.toml` E501 comment: "Re-enable after the TODO-281 code pass". TODO-281 is closed
  (`TODO_DONE.md:1231`). Either re-enable E501 and fix the violations, or rewrite the comment as a
  standing decision.

---

## 3. Backend — orphaned functions

### 3a. Zero references anywhere (production, tools, tests)

Delete unless one is a known planned hook. Effort S for all of them together.

| Function | Location | Note |
|---|---|---|
| `get_lb_statuses_batch` | `backend/db.py:8093` | docstring says "Attachments tree page" (PyQt-era) |
| `should_mark_nft` | `backend/db.py:8112` | superseded by `folder_naming.apply_nft_suffix` |
| `get_aliases_for_canonical` | `backend/db.py:9095` | |
| `get_lb_problem_count` | `backend/db.py:9513` | see the lb_problems routes in §4 |
| `get_curated_list_entries` | `backend/db.py:9634` | |
| `visible_lbs_hint` | `backend/dossier_anchors.py:837` | |
| `broadcast_clause` | `backend/dossier_fields.py:2896` | |
| `register_import_callback` (and `_import_callbacks` / `_notify`, which never fire) | `backend/scheduler.py:21-35` | the file watcher runs, but no callback is ever registered |
| `stop_file_watcher` | `backend/scheduler.py:112` | |
| `stream_file` | `backend/sharing.py:179` | |
| `decode_to_wav` | `backend/sox_utils.py:302` | one-line wrapper around `_convert_to_wav` |
| `make_torrent_batch` | `backend/torrent_maker.py:274` | |
| `fetch_recent` | `backend/tuit_scraper.py:318` | |
| `upload_and_seed` | `backend/tuit_upload.py:1026` | check against TODO-343 (TUIT uploader validation) before deleting |
| `restart_application` | `backend/updater.py:5` | see §2a |

### 3b. Called only from tests (no production or tool caller)

The code is kept alive only by its own tests. For each one, decide whether it is a supported API.
If it is not, delete the function and its test together.

`db.py`: `get_wishlist_lb_numbers` (5739), `get_tuit_uploads` (6809), `get_tuit_recordings`
(6642), `get_tuit_songs` (7017), `get_tuit_song_performances` (7056), `get_tuit_shows` (7149),
`get_tuit_venues` (7183), `get_file_hash` (10034), `prune_pipeline_cache` (10222).
Others: `qc/store.py:246 quarantined_batch`, `tuit_scraper.py:749 torrent_root_name`,
`wtrf_seed.py:344 parse_topic_links`, `seed_overlay.py:961 verify_overlay`,
`tmp_utils.py:72 reset_cache` (a test hook, so fine), `ab_clips.py:828 clear_duration_cache`
(test hook, fine), `concert_ranker/lb/{commentary.py:62 mine_entries, repo.py:213 get_scan,
source_type.py:65 classify_entries}`.

`prune_pipeline_cache` stands out: nothing ever prunes the pipeline cache in production. Either
schedule it or delete it.

### 3c. Unused `db_path` parameters

Write-queue functions document `db_path: Unused` (`db.py:6926, 6945, 6978, 6999, 10003, 10135`).
Removing the parameter means touching every call site. Do it only alongside other work on those
functions. Effort M.

---

## 4. Backend — Flask routes with no GUI caller

Of 388 routes, 78 have no reference in gui_next or the backend HTML pages. The ones below also
have **no** tool or test reference, so they are likely dead (`T` means a tool uses it; `S` means
only tests use it):

| Feature group | Routes (`backend/app.py` line) |
|---|---|
| Xref ingest (whole feature) | `/api/xref_ingest/{scan,filesets,approve,reject}` 1532-1565 |
| Flat file | `/api/flat_file/defer/<id>` 1495, `/changelog/<id>` 1519 |
| Collection | `/api/collection/{missing 2015, search 2043, duplicates 2293, delete_bulk 2437, audit 2456}`, `/routes/preview/<year>` 9767, `/integrity/scan/history` 9842 |
| LB missing (whole feature) | `/api/lb_missing` GET 5982 / POST 5990, `/api/lb_missing/<lb>` 6012 |
| LB problems (whole feature) | `/api/lb_problems` GET 6156 / POST 6172, `/<id>` 6196 / 6217, plus orphan `get_lb_problem_count` |
| Entries | `/api/entries/year/<year>` 1869, `/api/entries/reclassify` 1885, `/api/entries/by_lb_list` 9260 |
| Misc lookups | `/api/lookup/scan_folders` 1089, `/api/checksums/xref_lb_numbers` 1843, `/api/performances` 6025, `/api/lineage/<lb>` 6234, `/api/lb_master/history/<lb>` 5899, `/api/geocode/locations` 9472, `/api/setlistfm/show` 12267, `/api/olof/event/<id>` 12373, `/api/olof/chronicle/<year>` 12389 |
| Bootlegs | `/api/bootlegs/lb_numbers` 2963, `/by_lb/<lb>` 3013 |
| Preservation | `/api/preservation/reports` 3205, `/report` 3218 |
| LBdir | `/api/lbdir/delete_extra` 3633, `/verified_status` 3664 |
| WTRF | `/api/wtrf/fetch_torrent` 4885, `/api/wtrf/crawl_missing` 4972 |
| Torrents / forum | `/api/torrents` 5364, `/api/forum_posts` 4872 (the GUI uses `/api/entry/<lb>/forum_posts` instead) |
| Checksums | `/api/checksums/reconcile_audio` 9614, `/apply_reconcile_audio` 9648 |
| Bobserve | `/api/bobserve/fetch/status` 5528, `/stop` 5534 |
| TapeMatch / tapers | `/api/tapematch/sync` 6629, `/api/tapers/curation/text/<lb>` 6999 |
| Standalone page | `/taper-curation` 9526 (not linked from the GUI; `/qc-review` is, through locale strings) |
| Updater | see §2a |

Only tools use these (keep, but document them as tool APIs): `/api/status`,
`/api/db/missing_lb_numbers`, `/api/lbdir/find_extra`, `/api/rename/apply`.

Only tests use these. They are job triggers with no GUI button; check whether the Refresh/Data
Freshness card replaced them. `/api/olof/{fetch,fetch/status,fetch/stop,parse,chronicle_parse}`,
`/api/bobserve/{fetch,parse}`, `/api/ranker/rerank`, `/api/qc/decisions`,
`/api/tapematch/{dup_encodes,crawl/start,crawl/stop}`, `/api/ab_clip/<file>`,
`/api/curated_lists` (GET/POST/`<name>`), `/api/dossier/bbcode`.

**Recommendation:** go through the table one feature group at a time with tj. Each whole-feature
group (xref_ingest, lb_missing, lb_problems) is one decision: delete the routes, the db helpers,
and the tests, or wire the feature into the GUI. Effort M per group.

---

## 5. Backend — simplification

| # | Finding | Evidence | Recommendation | Effort |
|---|---|---|---|---|
| S1 | **`app.py` is a 13,742-line monolith** | All 388 routes and 22 `threading.Thread(` spawns live in one file. There are no Blueprints. | Split into per-domain Blueprints (`routes/collection.py`, `tapematch.py`, `dossier.py`, `scrape.py`, …), one domain per commit, with no behaviour change. Removing the §2 and §4 dead routes first shrinks the job. | L |
| S2 | `db.py` is 10,754 lines | TUIT, curated-list, lb_master, pipeline-cache and flat-file helpers all in one module | Split by table family into a `backend/db/` package that re-exports from `__init__` so callers keep working. | L |
| S3 | **The inline job-state pattern is still in 10 modules**, although `JobState` exists for it | `job_progress.py:1-14` documents the check-then-set race in the inline `_progress["running"]` pattern. Still inline: `app.py` (`_spectro_state` 401), `bobdylan_scraper.py:41`, `bootleg_scraper.py:33`, `geocoder.py:107`, `importer.py:25`, `preservation.py:52`, `scraper.py:47`, `setlistfm.py:37`, `site_crawler.py:77`. Only 5 modules use `JobState`. | Move them to `JobState` one at a time. This also fixes the double-start race. | M |
| S4 | `_ProgressFile` class duplicated | `app.py:6499` and `app.py:11642`. Both are identical upload-progress wrappers that `open()` without a context manager (ruff SIM115). | Move it to one module-level class (`backend/http_utils.py`) with `close()` / `__exit__`. | S |
| S5 | `_parse_date` is implemented 4 times | `bobserve_parser.py:153`, `bootleg_scraper.py:58`, `setlistfm.py:95`, `torrent_maker.py:112` | The input formats differ, so this is not a straight merge. Check whether `torrent_maker` and `setlistfm` (both ISO in, ISO out) can share one helper. | S |
| S6 | Unused "crowd" cuts | `concert_ranker/config.py:~326`: "retained for reference but unused" | Delete them, or move them into the comment. | S |
| S7 | Ruff findings with real value (the rest is style) | B905 `zip()` without `strict=` ×24, SIM105 ×30 (`try/except/pass` → `contextlib.suppress`), SIM102 ×17, B007 unused loop vars ×12, RET504 ×12 | Enable `B905` in `pyproject.toml`: a silent zip truncation is a real bug class. The rest can go in one `ruff --fix` commit. | S |
| S8 | `ERA001` "commented-out code": 18 hits, **all benign** | e.g. `dossier_fields.py:2524` is a documented provenance query, not dead code | No action. Listed so a future pass does not "fix" them. | — |

### Unused imports and variables in `tools/` (ruff excludes `tools/`, so nothing catches these)

`tools/dossier_acceptance.py:1064` Counter · `tools/ledger_dedup.py:31` field ·
`tools/parse_lineage.py:37` get_write_queue · `tools/test_site_headers.py:11` sys ·
`tools/tapematch/calibrate_staircase.py:24` align · `embedding/data.py:28` os ·
`nmfp_embed.py:135` tensorflow (may be a deliberate import side effect, so check) ·
`tapematch/align.py:16` and `tapematch/cli.py:16` to_mono · `tapematch/match.py:14` stft ·
unused locals at `gen_analysis.py:504 n_fam`, `tapematch/cli.py:870 fp_thr`,
`tapematch_session.py:883 src_path`. Fix with `ruff check --isolated --select F401,F841 --fix tools`
(leave `vendor/` alone). Consider removing `"tools"` from the ruff exclude for F-rules only.

---

## 6. GUI (`gui_next/src`)

### 6a. Unused locals and imports (`tsc --noUnusedLocals`: 25 errors)

| File | Unused |
|---|---|
| `App.tsx:171, 197` | `PlaceholderScreen`, `PrimitivesScreen` (plus `ACCENTS`, `DENSITIES`, `SAMPLE_ROWS`, used only by it). That is about 80 lines of dead dev screens. |
| `EvidenceList.tsx:14`, `DossierExportModal.tsx:8`, `ScreenFileIntegrity.tsx:7` | `React` import (not needed with the JSX transform) |
| `library/DetailPanel.tsx:128` | `coverageTone` |
| `pipeline/LookupDetail.tsx:7` | `LookupState` |
| `pipeline/PipelineParts.tsx:5` | `IconName` |
| `ScreenLibrary.tsx` | `SortDir` (18), `extractYear` (20), `hasRecordingFilters` (24), `hasActiveFilters` (650), `setGroupByYear` (1433) |
| `ScreenMap.tsx:32` | `DECADES` |
| `ScreenPipeline.tsx` | `Chip` (8), `isRunning` (1789), `stopRun` (1963). Check whether a Stop button was lost. |
| `ScreenScraper.tsx` | `Card` (4), `statusTone` (153), `TABS` (1515), `geocoderStats` (1545). `geocoderStats` is fetched state that nothing renders, so that fetch may be wasted too. |
| `ScreenSetup.tsx` | `Banner` (4), `pageSize` (554) |
| `ScreenSpectrograms.tsx:3` | `Chip` |
| `ScreenTrading.tsx:290` | `comp` |

**Recommendation:** clean all of these in one commit, then add `"noUnusedLocals": true` to
`tsconfig.web.json` so `/gui-check` catches new ones. The main and preload processes are already
clean. Effort S.

### 6b. Dead exports (exported and never used, including in their own file)

`components/pipeline/PipelineIcon.tsx: PIPELINE_STAGES` · `lib/tokens.ts: FONTS, CARD_STYLES`.
Delete. About 70 more exports are used only inside their own file (props interfaces, helpers in
`DetailPanel.tsx`, `CollectDetail.tsx`, `LbdirDetail.tsx`, `runDiff.ts`, …). Dropping the `export`
on those is cosmetic and low priority.

### 6c. Duplication

| Pattern | Count | Recommendation |
|---|---|---|
| `const BASE = window.api.flaskBase` | 32 files | `lib/api.ts` exporting `BASE` plus a typed `getJson`/`postJson` helper. Most of the hand-rolled `fetch(...).then(r => r.json())` blocks would collapse into it. |
| `fmtBytes` / `fmtSize` | 3 + 1 (`OnboardingWizard:91`, `ScreenFileIntegrity:81`, `ScreenScraper:161`, `ScreenScanner:44`) | `lib/format.ts` |
| `fmtLb` | 4 (`AppShell:459`, `ScreenFingerprint:60`, `ScreenHome:63`, `ScreenSongs:56`) | `lib/format.ts` (`lib/lbUrl.ts` may already be the natural home) |
| `fmtNum` | 3 (`AppShell:463`, `ScreenHome:67`, `ScreenSetup:1419`) | `lib/format.ts` |

Effort M. Do it mechanically, one helper per commit.

### 6d. Stale TODO

`App.tsx:367`: `useState(true) // TODO: re-enable splash screen`. The splash is permanently off.
Either delete the splash component and its state, or file a TODO-NNN. A bare TODO with no ID
breaks the repo's ledger convention.

### 6e. Oversized screens (no action needed now)

`ScreenCollection.tsx` 4,076 lines, `ScreenTapeMatchCuration.tsx` 3,507, `ScreenPipeline.tsx`
3,278, `ScreenLibrary.tsx` 2,375. ScreenPipeline has already been split into
`components/pipeline/*`. ScreenCollection is the next candidate, but only when a feature already
touches it.

---

## 7. Dependencies

Every package in `requirements.txt` is imported somewhere. `lxml` looks unused, but it is the
BeautifulSoup parser (`bobserve_fetcher.py:125`), and the `nvidia-*` wheels are loaded at runtime
by CTranslate2. **No dependency is obsolete.** The root `package.json` (only `playwright`) is the
`/verify` driver, so keep it.

---

## Suggested order

1. **H1–H6** repo hygiene: one `chore` commit, apart from the history-rewrite decision.
2. **6a + 6b + tools F401**: mechanical lint cleanup, then turn on `noUnusedLocals`.
3. **§2a, §2b, §2c** obsolete updater, busy route and PyQt remnants.
4. **§3a** zero-reference functions.
5. **§4** route groups, one feature decision at a time (needs tj).
6. **S3, S4, 6c** simplifications.
7. **S1, S2** structural splits: only after steps 3–5 have shrunk the files.

**Decisions for tj:** H1 history rewrite (force-push to the public repo) · §4 whole-feature groups
(xref_ingest, lb_missing, lb_problems, preservation reports, reconcile_audio) · `upload_and_seed`
versus TODO-343 · test-only API keep/delete (§3b).
