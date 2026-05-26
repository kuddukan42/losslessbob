# Scraping Behaviour

## Scrape All Missing

The **Scrape All Missing** button queues every LB number present in the `checksums` table, excluding any whose `lb_master.lb_status` is `'private'` (those are handled by the separate private re-scrape route). Sequential gaps between 1 and the highest LB number in the table are pre-inserted as missing entries before the scrape begins.

## Force Checkbox

When **Force** is checked, the normal skip logic in `scrape_entry` (scraper.py:142) is bypassed. Without force, entries are skipped if they already have a database row with all attachment files downloaded. With force, every entry is re-fetched from the live site and re-processed regardless.

### What Force does NOT change

- Entries confirmed nonexistent in the `lb_missing` table are **always skipped** — force has no effect on those.
- Private LBs are excluded at the API level before the queue is built.

## Behaviour by LB state

| LB state | Force off | Force on |
|---|---|---|
| In `lb_missing` (confirmed gone) | Skip | Skip (unchanged) |
| Has DB row + all files downloaded | Skip | Re-scrape + re-download |
| Has DB row, missing some files | Re-download missing files only | Re-scrape + re-download all |
| Marked `missing` in `entries` (soft 404) | Re-check live site | Re-check live site |
| Not in DB at all | Scrape | Scrape |
| `lb_master.lb_status = 'private'` | Skip | Skip (excluded before queue) |

With Force on, the result is effectively a **full re-scrape of the entire archive** — every non-private, non-lb_missing entry is hit again.
