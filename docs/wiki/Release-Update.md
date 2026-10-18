# Release Update

> Sources: `backend/flat_file.py` · `backend/app.py` (`/api/flat_file/apply/<id>`,
> `/api/scrape/*`, `/api/derived/recompute`) · `backend/scraper.py:plan_range` ·
> `backend/db.py` (`reconcile_lb_status`, `batch_reconcile_lb_status`,
> `_keep_unscraped_public`) · `backend/refresh.py` (`scrape_entries`) · BUG-365 ·
> Status: fresh 2026-10-18

The order of operations when the site publishes a new
`Checksum_Lookup_flat_file_LastLB_<N>.zip`. Since 2026-10-14 (BUG-365) Apply does
the scrape and reconcile itself — the steps below are the whole flow.

## The order

1. **Setup → Check for update → Download → Review & Apply.** Apply backs up the DB,
   diffs `checksums` (add / change / remove, one `flat_file_changelog` row each),
   marks the release's new LBs `public` in `lb_master`, then **scrapes every new
   LB with no `entries` row** in the background. A toast says the scrape started.
   When it finishes, `scrape_range` batch-reconciles those LBs — `ok` page →
   `public`, 404 / soft-404 → `private`.
2. **Home → Updates → Update** (or `POST /api/derived/recompute`): lineage →
   tapers → show picks → song index. This rebuilds everything; it can't be
   limited to particular LBs. Run it after the scrape has finished.

That's it. **Reconcile All** (DB Editor) and **Scrape All** (Scraper) are no
longer part of the release flow. Running either one too early is now harmless.

## Checking it worked

- The Updates card's `scrape_entries` backlog counts LBs that have checksums
  but no `entries` row (and aren't in `lb_missing`). It should read 0 after the
  scrape. Before BUG-365 it was always 0, whatever the state.
- `/api/scrape/status` → `last_lb` should be the release's highest LB.
- If the Apply toast said *another scrape is running*, run Scraper → Scrape All
  once that scrape ends. `plan_range` still picks up unscraped LBs.

## Why the old order broke

Before BUG-365, Apply never scraped. Reconcile treated a new LB as `private`
(checksums but no page), and `plan_range` skips `private` LBs. So running
Reconcile before Scrape stranded the release: LB-16731..16738 sat unscraped
until 2026-10-14. Two rules now prevent that:

- **Reconcile** won't demote a `public` LB that has no `entries` row
  (`_keep_unscraped_public`). Only a scrape that writes a row can make it
  `private`.
- **plan_range** includes `private` LBs with no `entries` row.

## Gotchas

- "Auto-scrape on import" only affects **Import file manually…** (the legacy
  `/api/db/import` path, insert-only, md5-hashed). Apply always scrapes.
- Bad metadata on the site page comes in as-is (LB-16734 had a taper notice in
  Location). A direct `entries` fix survives normal scrapes, which skip `ok`
  entries, but a **forced** re-scrape overwrites it.
- Scraper-screen options (delay, attachments, local pages) are pre-filled from
  saved settings and sent with each scrape; omitted options fall back to settings.
- Private LBs whose page later gets published are found by Scraper →
  **Re-scrape private** (~1,100 LBs, about 30 min at a 1.5 s delay). That's not
  part of a release.
