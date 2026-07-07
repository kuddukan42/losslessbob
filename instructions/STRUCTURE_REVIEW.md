# Structural & Consistency Review — 2026-07-04

Scope: backend + gui_next (PyQt6 `gui/` frozen — excluded; tapematch excluded).
Focus: PROJECT.md drift, duplicated logic, dead code, error-handling/logging consistency.
Not covered: line-level correctness bugs.

---

## P1 — PROJECT.md drift (the doc is the per-session map; it has fallen well behind)

The pattern behind all of these: recent changes were logged in the PROJECT.md
Change Log table but the corresponding *reference sections* (file tree, schema,
routes, GUI tables) were never updated.

1. **88 Flask routes exist in code but are absent from the routes section**
   (`PROJECT.md:678-978` vs `backend/app.py` — 238 unique paths in code, 150 documented).
   Entire groups are missing: `/api/bobdylan/*`, `/api/setlistfm/*`, `/api/share/*`,
   `/api/trading/*`, `/api/wishlist*`, `/api/fingerprint/*`, `/api/collection/*`,
   `/api/update/*`, `/api/wtrf/*`, `/api/pipeline/*`, `/api/dbedit/query`,
   `/api/credentials/*`, `/api/package/*`, purge routes, `/api/status`, `/api/app/version`.
   *Fix: add one route table per missing group; consider generating the list from
   `@app.route` decorators to keep it honest.*

2. **14 tables are created in code but have no schema section** (`PROJECT.md:172-677`):
   `lb_master`, `lb_status_history`, `my_collection`, `my_wishlist`, `collection_meta`,
   `fingerprints`, `audio_tracks`, `friend_collections`, `friend_collection_entries`,
   `bobdylan_shows`, `bobdylan_setlist`, `setlistfm_shows`, `setlistfm_setlist`,
   `wtrf_downloads`. `lb_master` is referenced 27 times elsewhere in PROJECT.md yet
   never defined. *Fix: add a `###` schema block per table, flagging MASTER vs USER.*

3. **The file-structure tree omits `gui_next/` entirely** (`PROJECT.md:36-168`) even
   though the same document calls it the PRIMARY GUI at `PROJECT.md:1463`. It also
   omits 11 backend modules that exist on disk: `archive_org.py`, `bobdylan_scraper.py`,
   `debug_forum_post.py`, `filer.py`, `paths.py`, `setlistfm.py`, `sharing.py`,
   `tapematch_sync.py`, `updater.py`, `version.py`, `wtrf_scraper.py` — plus
   `instructions/`, `docs/schema.html`, `docs/lb_missing_vs_missing_status.md`, and
   5 newer test files (`test_batch_verify.py`, `test_concert_ranker.py`,
   `test_db_lookup.py`, `test_lineage.py`, `test_pipeline_smoke.py`).
   *Fix: regenerate the tree from disk and add one-line comments for the new modules.*

4. **The gui_next screens table is stale** (`PROJECT.md:1467-1487`): header says
   "16 fully wired", the table lists 17, the `screens/` directory has 22.
   Missing rows: `ScreenDbEditor`, `ScreenFingerprint`, `ScreenScraper`,
   `ScreenSharing`, `ScreenTrading`. The shared-stores table (`PROJECT.md:1489-1499`)
   is missing `lib/lbUrl.ts` (added for BUG-221). *Fix: add the 5 screen rows +
   lbUrl.ts row and drop the hardcoded count from the header.*

5. **Stale `data/pages/` / `data/attachments/` references in current-behavior
   sections**: the Key Data Flows scrape diagram (`PROJECT.md:1528-1543`), the
   `/api/lbdir/retrieve` route doc (`PROJECT.md:970`), the `use_local_pages` meta-key
   doc (`PROJECT.md:557`), and the `entry_files.downloaded` column doc
   (`PROJECT.md:213`). `backend/paths.py:45` states these dirs were replaced by
   `data/site/detail/` and `data/site/files/`. *Fix: update the four references to
   the `data/site/` layout.*

6. **Preload IPC list is stale** (`PROJECT.md:1465`): documents 5 handlers
   (`openPath, pickFile, pickFiles, pickDir, pickFolders`) but
   `gui_next/src/preload/index.ts` exposes 10 (`flaskPort`, `flaskBase`, `platform`,
   `saveFile`, `pickAndReadFile`, `pickAndReadFiles` are missing; `pickFiles` no
   longer exists under that name). *Fix: list the actual bridge surface.*

7. **Port note points at the dead GUI** (`PROJECT.md:1598`): says 5174 is hardcoded
   in "`backend/app.py` and `gui/` tabs"; in gui_next it lives in
   `gui_next/src/main/index.ts` and `gui_next/src/preload/index.ts:7`
   (plus `run_backend.py:40`, `main.py:15`, `cli.py:16`). *Fix: enumerate the actual
   5174 sites so the CLAUDE.md "change atomically" rule is followable.*

8. **GUI Conventions section is 100% Qt/QSS** (`PROJECT.md:1563-1591`) — it describes
   the frozen PyQt6 GUI as if it were current convention, and no gui_next conventions
   (zustand stores, `version-bump refetch`, virtual tables, Toast, i18n `t()` rules)
   are documented anywhere. *Fix: retitle it "Legacy GUI Conventions (frozen)" and add
   a short gui_next conventions section.*

---

## P2 — Duplicated logic / divergent conventions

9. **The losslessbob.com base URL is an independent literal in 7 backend places** —
   `backend/scraper.py:32`, `backend/site_crawler.py:43`, `backend/flat_file.py:27`,
   `backend/forum_poster.py:371`, `backend/db.py:2155`, `backend/db.py:5201`,
   `backend/app.py:1663`. This is the backend twin of BUG-221 (which consolidated the
   GUI side into `lbUrl.ts`), and the drift is already visible: `backend/db.py:2155`
   builds `detail/LB-{lb}.html` from an INTEGER `lb_number` **without zero-padding**
   (→ `LB-42.html`, a 404) while `backend/forum_poster.py:369-372` correctly pads.
   *Fix: add `SITE_BASE_URL` + `detail_url(lb)` to `backend/paths.py` (next to
   `detail_page_path`) and route all 7 call sites through it.*

10. **`LB-` label formatting is re-implemented 58 times across 18 renderer files**
    (`padStart(5, '0')` in `ScreenSearch.tsx`, `ScreenCollection.tsx`, `AppShell.tsx`,
    `ScreenLibrary.tsx`, …). `lbUrl.ts` consolidated the URL variant only.
    *Fix: export `lbLabel(lb): string` from `gui_next/src/renderer/src/lib/lbUrl.ts`
    and migrate call sites opportunistically.*

11. **`ScreenScraper.tsx:324` and `:968` hardcode the site base URL** to strip it
    from displayed crawler URLs, duplicating the private constant in `lbUrl.ts:4`.
    *Fix: export `LB_SITE_BASE` from `lbUrl.ts` and import it in ScreenScraper.*

12. **Two API error-response shapes coexist in `backend/app.py`**:
    `jsonify({"error": …})` (294 uses) vs `jsonify({"ok": False, …})` (46 uses), and
    there is no `@app.errorhandler(Exception)`, so an unhandled exception returns
    Flask's HTML 500 page to a client that always expects JSON. *Fix: pick the
    `{"error"}` shape for new code, add a JSON `errorhandler(Exception)`, and note the
    convention in PROJECT.md.*

13. **File-MD5 hashing is implemented twice**: `backend/importer.py:46` (`md5_file`,
    also imported by `scheduler.py`) and inline in `backend/checksum_utils.py:342`.
    *Fix: keep one canonical helper in `checksum_utils.py` and have importer/scheduler
    import it.*

14. **Module-logger naming diverges across backend**: `logger =` (flat_file,
    geocoder, wtrf_scraper, qbittorrent, filer, …), `log =` (`sharing.py:18`),
    `_log =` (`scheduler.py:14`), and `backend/db.py` has no module logger at all —
    it calls `logging.getLogger(__name__)` inline at 11 sites (e.g. `db.py:1592`,
    `db.py:3860`, `db.py:4517`). *Fix: standardize on one module-level
    `logger = logging.getLogger(__name__)` per module; db.py first.*

15. **26 fetch calls in the renderer swallow errors with `.catch(() => {})`**
    (heaviest: `ScreenScraper.tsx` ×5, `ScreenPipeline.tsx` ×3, `ScreenLBDIR.tsx` ×3,
    `ScreenCollection.tsx` ×3) while the rest of the codebase surfaces failures via
    Toast. Fine for polling loops, wrong for user-initiated actions. *Fix: audit the
    26 sites and keep silent-catch only on interval polls.*

---

## P3 — Dead code / leftover artifacts

16. **`backend/losslessbob.db`** — a 0-byte SQLite file (2026-05-31) sitting inside
    the package; the real DB is `data/losslessbob.db`. Stray artifact from running
    with the wrong cwd. *Fix: delete it.*

17. **`tests/pipeline_smoke_bugs.md` and `tests/pipeline_smoke_results.txt`** — run
    output committed into the test package. *Fix: move to `docs/` or delete; add to
    `.gitignore` if regenerated.*

18. **`tools/_wtrf_batch_85_runner.py`** — untracked one-off batch runner left at
    `tools/` root after the WTRF batch-85 run. *Fix: delete or fold into the
    documented wtrf tooling.*

19. **concert_ranker test layout is split three ways**: `concert_ranker/test_pipeline.py`
    at package root, an **empty** `concert_ranker/tests/` directory, and
    `tests/test_concert_ranker.py` in the repo-level suite. `concert_ranker/BUILD_REPORT.md`
    is also a leftover build artifact, and `quality_score.py` / `text_features.py`
    are missing from the PROJECT.md concert_ranker listing (`PROJECT.md:69-85`).
    *Fix: move `test_pipeline.py` into the repo `tests/` suite, delete the empty dir,
    and update the PROJECT.md module list.*

20. **`backend/debug_forum_post.py`** — standalone SMF-posting diagnostic living
    inside the importable `backend` package, referenced by nothing and undocumented.
    *Fix: move to `tools/` (it's a CLI diagnostic, not backend code) and document it.*

---

## Verified clean (checked, no action)

- All 22 screens are registered in `App.tsx`; no orphan screens.
- All 6 locale files have identical key counts (1379) — i18n parity holds.
- `const BASE = window.api.flaskBase` is used uniformly (21 files); no renderer
  hardcodes the port.
- No `print()` in backend modules outside CLI `__main__` blocks
  (`tapematch_sync.py:344` is a documented CLI entry point).
- No detail-page URL construction remains in the renderer outside `lbUrl.ts`
  (BUG-221 consolidation held).
- `components/index.ts` barrel exports all match real, used components.
