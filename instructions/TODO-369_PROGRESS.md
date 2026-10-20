# TODO-369 progress — app.py → Blueprints (S1), db.py → package (S2)

Spec: instructions/CODE_REVIEW_2026-10-17.md §5 S1/S2. Repeatable night package
`08-blueprint-split`; each run resumes here.

## Method (per domain, one commit each)

1. `.debug/todo369/_extract_bp.py START END MOD "doc"` — cuts the `create_app()` line range into
   `backend/routes/<MOD>.py` (dedent, `@app.route` → `@bp.route`, app.py's import block as
   header) and leaves `from backend.routes.<MOD> import bp; app.register_blueprint(...)` at
   the cut point, so registration order is preserved.
2. Module-level helpers used only by that domain: `.debug/todo369/_move_top.py START END MOD`.
   Helpers/state shared with app.py or other domains go to a small shared module
   (never duplicated). Names tests monkeypatch on `backend.app` stay reachable there.
3. `ruff check --fix` on the new module only (F401/I); never blind-F401 app.py — check
   that a dropped app.py import isn't read as `backend.app.<name>` by tests/tools.
   `app.` inside moved code → `current_app`.
4. `.debug/todo369/_blank2.py backend/routes/<MOD>.py` (2 blank lines between top-level
   defs after the dedent), then `.debug/todo369/_ast_check.py <pre-commit-rev> <MOD>` — every
   moved function's AST must equal the original (docstrings/decorators aside); the only
   allowed differences are the intentional edits listed in the commit message.
   `.debug/todo369/_smoke.py <MOD>` GETs every argument-less GET rule of the Blueprint.
5. `.debug/todo369/_dump_routes.py .debug/routes_after.txt` and diff against
   `.debug/routes_before.txt` (378 rules+methods, dumped once before the split) — must be
   identical. Then the domain's targeted tests + tests/test_refresh.py.

Gotchas (each bit once):
- `nonlocal` create_app closure flags (e.g. `_wtrf_crawl_running`) → module-level + `global`;
  ruff misses it, only `_smoke.py` (SyntaxError on import) catches it.
- `.debug/todo369/_domain.sh START END MOD "doc"` runs steps 1,3,4,5 in one go; END must stop
  before the next `register_blueprint` pair.
- tests/test_refresh.py::test_route_how_to_run_resolves_in_url_map fails when run right after the
  bootleg/crawler tests (db-writer start timeout). Pre-existing, ordering-only; passes alone and in
  the full suite.
- Relative imports in moved code (`from . import flat_file`) resolve to `backend.routes` —
  the extractor now rewrites them to `from backend import …`. Only `_smoke.py` catches this.
- `Path(__file__).parent` in admin/map/taper-page routes (app.py ~8285–8548) must become
  `.parent.parent` once moved.
- Tests that monkeypatch `backend.app.<name>`: `get_spectrogram_status`,
  `get_tapematch_crawl_status`, `get_pipeline_run_status` (test_activity*.py),
  `_lbdir_status_for_lb` (test_lb_master.py), `SITE_DIR`/`SITE_FILES_DIR`/`DATA_DIR`
  (test_sitedata_packaging.py), `database.resolve_aliases` (test_lbdir_manifest_scope.py),
  `_github_upload_asset`, `compute_pipeline_severity`, `_find_lbdir_in_folder`,
  `_lbdir_file_lb` imported from backend.app, `importlib` (test_pipeline_jobs.py, now
  lb_data). Repoint the test when the owner moves. Module imports that ruff calls unused
  in app.py after a cut may still be test patch targets — grep `app_module.` first.

Shared state so far: `backend/routes/_state.py` (`process_start_time`);
`backend/folder_lb.py` (folder→LB / manifest lookup helpers, domain 9);
`backend/spectro_worker.py` (spectrogram state + batch, domain 10; activity.py reads it);
`backend/lbdir_status.py` (`_lbdir_status_for_lb` + verdict helpers, domain 12);
`backend/scrape_worker.py` (scrape thread guard + `_start_scrape_thread` /
`_start_download_pages_thread` / `_start_scrape_worker`; app.py re-imports the first two,
refresh_exec imports it from scrape_worker directly since domain 6; test_scrape_worker.py repointed);
`backend/github_upload.py` (`_ProgressFile` + `_github_upload_asset`, domain 14; app.py's data
package export re-imports it).

Endpoint names gain the blueprint prefix (`dbedit.dbedit_tables`); nothing in the repo
uses `url_for` / `request.endpoint` / `view_functions`, so that is not a behaviour change.

The three throwaway tools live in WT/.debug/todo369/ (gitignored, persists between runs);
recreate from this description if missing. Run them from WT root.

## S1 domains (app.py `create_app()` section markers)

| # | Blueprint module | app.py sections | Commit |
|---|---|---|---|
| 1 | dbedit | FEAT-14 DB Editor | d0cb7546d |
| 2 | core | Checksum Lookup, Database Management (`_process_start_time`) | 9114cc7bc |
| 3 | flat_file | Flat file update pipeline, Site-mirror xref ingest | 10ba106c3 |
| 4 | entries | Entry Detail & Attachments, Search | 5bfa2d7f2 |
| 5 | collection | My Collection, FEAT-03/04/05/13, FEAT-09 integrity events | 67cee89d3 |
| 6 | scrape | Scraper Control (thread helpers already in backend/scrape_worker.py) || 5f9f208d1 |
| 7 | bootlegs | Bootleg-CD Catalog || 57358ac33 |
| 8 | crawler | Site Crawler, Preservation stack || 743251c41 |
| 9 | lbdir | Verify, LBDir || 1ae1664ad |
| 10 | spectrogram | Platform helpers, Spectrogram, rename apply || 51db8315d |
| 11 | torrents | Torrent Generation, qBittorrent || a5b97f7c0 |
| 12 | wtrf | Forum Posting, WTRF fetcher, WTRF fetch review || 3e3d182d7 |
| 13 | lb_master | lb_master integrity, Pipeline refresh Phase 2/3 | 505de347b |
| 14 | lb_data | lb_missing, lb_problems, lineage, curator mode, master publish/subscribe | f2dcfee95 |
| 15 | tapers | Taper attribution/curation/QC review/vocab/aliases | |
| 16 | tapematch | tapematch, tapers, ab_clip, bobtalk, library (6859–8074 block) | |
| 17 | ranking | Curated lists, show picks, song index, show detail, timeline | |
| 18 | dossier | Show dossier | |
| 19 | aliases | lb_alias, folder_lb_link | |
| 20 | map | Map feature routes | |
| 21 | admin | Admin page | |
| 22 | mounts | Collection mounts/routes, integrity monitor, disk scanner, file integrity | |
| 23 | pipeline | Pipeline | |
| 24 | export | Data Package Export | |
| 25 | olof | Olof Björner | |
| 26 | trading | Collection Trading | |
| 27 | sharing | File Sharing | |
| 28 | archive_org | Archive.org Upload | |

Grouping is a plan, not a contract — split or merge when a section's shared state says so.

## S2 — db.py → backend/db/ package

Not started. Plan: package with `__init__` re-exporting every public + test-patched name;
mind `monkeypatch.setattr(database, ...)` targets (a function moved to a submodule and
called from another submodule won't see a patch on the package attribute).

## Run log

- Run 1 (2026-10-20):
- Run 2 (2026-10-20, interactive): domains 6–12. Stopped by tj after 12; next is 13 lb_master.
- Run 3 (2026-10-20, interactive): domain 13 (`_reconcile_lock` moved into lb_master.py).
  One-off failure of test_lb_master.py::TestUnscrapedStaysPublic::test_single_reconcile_keeps_public
  under `pytest -x`; passed alone and in the full run. Next is 14 lb_data.
- Run 4 (2026-10-20, interactive): domain 14. Backup rate-limit state moved into lb_data.py;
  upload helper → backend/github_upload.py. app.py 6,750 lines. Next is 15 tapers.
