# New-User Onboarding & Data Sync — Design Spec

Spec author: Fable 5, 2026-07-06. Execution target: Sonnet session(s).
New work (no existing TODOs consolidated); allocate TODO IDs at session close.
Companion reading: PROJECT.md §Master Data (export/import, GitHub release flow),
`backend/db.py:37` (`MASTER_TABLES`), `backend/paths.py:46` (`SITE_DIR` layout).

---

## 1. Problem

A person installing LosslessBob from scratch today must discover and correctly
sequence **four disconnected mechanisms** before the app is useful:

| Mechanism | Routes | What it delivers | Fresh-install gap |
|---|---|---|---|
| Master snapshot (GitHub Releases, tag `master-YYYY-MM-DD`) | `GET /api/master/github_check`, `POST /api/master/github_install` (SSE) | All of `MASTER_TABLES`: entries, checksums, lb_master, geocoded locations, setlists, tapematch families, curated lists, flat-file history | Works, but hidden behind Setup → Master Data; nothing points a new user at it |
| Flat-file pipeline | `/api/flat_file/*` | Monthly checksum deltas from the LB site | Redundant on day one — the master snapshot already embeds `flat_file_releases`/`flat_file_changelog` |
| Scrape/site data (`data/site/`) | `POST /api/package/scrape_data` (export), `POST /api/package/restore` (local zip path only) | Cached detail pages, attachments, lbbcd, artwork | **No distribution channel.** Restore needs a zip the new user has no way to obtain; the alternative is re-scraping the entire LB site |
| Scraper | ScreenScraper + `/api/scrape/*` | Same data as above, slowly, hammering the LB site | Should be curator-only; nothing tells the user that |

Plus: README.md still documents the retired PyQt flow (`python main.py`,
"Setup tab → Import Database File → flat file first") and actively misleads.

Goal: **install → launch → one guided screen → fully populated app**, with the
LB site never scraped by end users.

## 2. Design principles

- **The master GitHub release is the single onboarding artifact.** Everything a
  new user needs either rides on it or is discoverable from it. No new sync
  machinery — consolidate what exists.
- **End users download; only curators scrape.** Nominatim geocoding already
  follows this pattern (pre-geocoded coords ship in master); extend it to site
  pages and attachments.
- **Skippable, resumable, idempotent.** The wizard is a convenience wrapper
  around existing endpoints. Skipping it leaves a persistent checklist; re-running
  any step is safe (master import + restore are already idempotent).
- **Curator flow stays manual.** Publishing site data is an explicit curator
  action with its own cadence — never bundled silently into every master publish.

## 3. Site-data packaging (the real gap)

Measured 2026-07-06:

| Subtree | Raw size | Contents |
|---|---|---|
| `site/files/` | 2.4 GB | 94,169 files — ~80k `.txt` (md5/ffp/st5 text), ~14k `.html` (DigiFlawFinder) |
| `site/detail/` | 67 MB | per-LB detail pages |
| `site/lbbcd/` | 8.7 MB | artwork index pages |
| `site/lbjpg/` | 2.6 MB | artwork thumbnails |
| `site/bynumber/` + root html | <1 MB | index pages |

Split into **two assets** (all-text content compresses well; both stay far under
GitHub's 2 GiB asset limit):

- `losslessbob_sitedata_core_<date>.zip` — everything **except** `files/`
  (~80 MB raw, est. 15–25 MB zipped). Recommended for all users: powers
  Attachments browsing of detail pages, artwork, lbbcd.
- `losslessbob_sitedata_files_<date>.zip` — `files/` only (est. 300–500 MB
  zipped). Optional: checksum/fingerprint text attachments.

Published under a **separate release tag** `sitedata-YYYY-MM-DD` on the same
repo, with a `.manifest.json` sidecar per asset (same shape as the master
manifest: `type`, `created_at`, `file_count`, `total_bytes`, `sha256`). Site
data changes slowly; the curator republishes on demand, not monthly.

Backend changes:

1. Split `package_scrape_data` (`backend/app.py:6507`) into core/files variants
   (query param `part=core|files`), writing the manifest sidecar next to the zip.
2. New `POST /api/sitedata/github_release` (curator, SSE) — mirror of
   `master_github_release`: build both zips + manifests, `gh release create
   sitedata-<date>` with 4 assets.
3. New `GET /api/sitedata/github_check` + `POST /api/sitedata/github_install`
   (SSE) — mirror of the master pair: find latest `sitedata-*` release, download
   chosen asset(s) to `data/imports/`, verify SHA256, extract into `SITE_DIR`
   (extract = restore; reuse `package_restore`'s extraction path, extended to
   accept the new manifest types). Progress events `progress`/`done`/`error`,
   same shape as `github_install` so the frontend SSE helper is reused.

## 4. Onboarding status endpoint

`GET /api/onboarding/status` →

```json
{
  "entries_count": 0,
  "master_version": null,
  "sitedata_core_present": false,
  "sitedata_files_count": 0,
  "mounts_configured": false,
  "collection_count": 0,
  "complete": false
}
```

Cheap queries only (counts + `meta` reads + two directory existence checks).
`complete` = entries present ∧ master version stamped ∧ ≥1 mount. Drives both
the wizard trigger and the Home checklist card.

## 5. First-run wizard (gui_next)

New `OnboardingWizard` component, shown as a modal over ScreenHome when
`entries_count == 0` on startup (checked once per launch; "Skip for now"
dismisses for the session).

Steps (each a thin wrapper over an existing/new endpoint, with the SSE progress
bar already used by ScreenSetup's master install):

1. **Get the dataset** — shows `github_check` result (version, date, size);
   one button → `master/github_install`. Required to proceed (or Skip).
2. **Cached site pages** — two checkboxes (core: recommended, pre-ticked;
   files: optional, with size shown) → `sitedata/github_install`.
3. **Your collection** — brief explainer + button that deep-links to
   ScreenMounts to add a mount, and to Pipeline/Collection scan. No new logic;
   this step is navigation only.
4. **Done** — summary of what was installed.

Home gains a **setup checklist card** (visible while `complete == false`):
one row per unmet item from `/api/onboarding/status`, each linking to the
wizard step or screen. This is the resume path for skippers.

All new strings go through the locale files — run `/gui-next-i18n` before close.

## 6. Demotions & docs

- **Flat file**: no first-run role. Reword Setup copy to "Monthly update" and
  drop it from any onboarding path. No code removal.
- **Scraper**: add a one-line note on ScreenScraper ("End users get scraped data
  via master + site-data releases; scraping is for curators") — copy change only.
- **README.md rewrite** (it currently documents the retired PyQt flow):
  - Quickstart: download installer from GitHub Releases (AppImage / Windows
    setup exe) → launch → follow the first-run wizard. Three lines.
  - Data model note: what the master release contains, what site data adds,
    monthly flat-file updates thereafter.
  - Dev setup: clone, `.venv`, `pip install -r requirements.txt`,
    `run_backend.py` + gui_next dev, pointer to PROJECT.md.
  - Keep flat-file format + checksum format reference sections.

## 7. Phases

| Phase | Scope | Depends on |
|---|---|---|
| P1 | Site-data packaging: split export, `sitedata/github_release`, curator publishes first `sitedata-*` release | — |
| P2 | `sitedata/github_check` + `github_install`; `onboarding/status` | P1 release exists to test against |
| P3 | Wizard + Home checklist card + Setup/Scraper copy changes + i18n | P2 |
| P4 | README rewrite | none (can run any time) |

P1+P2 are backend-only and testable via curl. P3 is frontend-only against P2.

## 8. Acceptance criteria

1. Fresh clone / clean `data/` dir + running curator-published releases: wizard
   takes a new install to `complete: true` with **zero scrapes** of the LB site
   and no manual file placement.
2. `sitedata/github_install` verifies SHA256 before extraction; a corrupted
   download errors without touching `SITE_DIR`.
3. Re-running any wizard step is a no-op or clean overwrite — no duplicate rows,
   no doubled site files.
4. Wizard never blocks the app: Skip always available, checklist card resumes.
5. `/api/onboarding/status` responds <100 ms on a populated DB.
6. Existing installs (entries present) never see the wizard; checklist card only
   if `complete == false`.
7. README quickstart verified against an actual release install by a reader who
   has never used the app (the "new person" test).

## 9. Out of scope

- Auto-update / background polling of releases (existing manual check stands).
- Torrent/qBittorrent, WTRF credentials, tapematch tooling — power-user setup,
  not first-run.
- Any change to master export/import logic or `MASTER_TABLES` membership.
- Bundling site data into the app installer (keeps installers small; data has
  its own cadence).
- Legacy PyQt `gui/` — frozen; wizard is gui_next only.
