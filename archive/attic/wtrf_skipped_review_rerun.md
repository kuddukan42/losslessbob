# WTRF skipped-review re-run — 2026-07-01 (TODO-197)

Re-ran all 85 LB entries from `wtrf_skipped_review.md` through
`tools/wtrf_fetch_missing.py --lbs <list> --delay 2.0 --add-to-qbt --paused`
after the checksum body-search + cross-recording guard (BUG-231/232) landed.

Command: 20:03–22:47 (2h44m — much longer than the ~30 min estimate; several
entries had 20–37 candidate posts to score, each requiring a checksum-body fetch).

## Result vs. original categorization

| Original category (wtrf_skipped_review.md) | Count | New outcome |
|---|---|---|
| No candidate post found (47) | 47 | 24 confirmed `not_found` (genuinely absent/disqualified), 13 `needs_review`, 10 `ambiguous` |
| One low-confidence candidate (21) | 21 | 15 downloaded/qbt_added (definitive/high/medium), 4 `needs_review`, 2 `not_found` |
| Two tied candidates (17) | 17 | 15 downloaded/qbt_added (definitive), 1 `not_found`, 1 still `ambiguous` |

## New confidence breakdown (85 total)

| Confidence | Count | Status |
|---|---|---|
| definitive | 28 | 14 qbt_added, 14 downloaded (blocked by qBittorrent "Conflict" — see note) |
| high | 1 | qbt_added |
| medium | 1 | downloaded |
| needs_review | 13 | skipped, unchanged — score too low to auto-match |
| ambiguous | 11 | skipped — still two tied candidates |
| not_found | 31 | skipped — all candidates disqualified or none found |

**30 of 85 (35%) now resolve automatically** — up from 0 in the original pass.
The date-parsing failures from the original report ("Cannot derive date variants
from date_str=...") no longer appear as their own failure mode this run.

## Genuinely absent from WTRF (31 not_found)

LB-16101, 16107, 16219, 16260, 16362, 16389, 16392 → later resolved, 16393 → resolved,
16440, 16458, 16459, 16463, 16464, 16465, 16477, 16511, 16520, 16521, 16533, 16547,
16548, 16551, 16565, 16566, 16567, 16586, 16588, 16621, 16628, 16632, 16633, 16634, 16635

Most disqualify every candidate as "explicitly tagged for a different LB entry" or
"posted before the 6-month download window" — these look like real absences, not
matcher failures.

## New false-match risk found — needs manual review

Two definitive matches point at the **same single WTRF topic** for entries that
turn out to be genuinely different shows:

| LB | Date | Location | Matched topic |
|---|---|---|---|
| LB-16404 | 5/13/25 | Phoenix, AZ | topic=55005 |
| LB-16405 | 5/15/25 | Chula Vista, CA | topic=55005 |
| LB-16406 | 5/25/25 | George, WA | topic=55005 |

Three different dates/venues, same forum post — this is a confirmed false match
(one is right, the other two are not), not a duplicate-catalog-entry case. Filed
as **BUG-234**.

By contrast, LB-16308 and LB-16340 (both matched topic=51358) checked out fine —
both are `5/10/95, San Diego, CA`, i.e. genuine duplicate catalog entries for the
same show, so that collision is correct behavior.

## Data-loss consequence of BUG-233 (junk filename)

BUG-233 (open) means every downloaded `.torrent` in a batch run lands at the
identical path `data/downloads/wtrf/UTF-8.torrent`. Confirmed on disk after this
run: only **one** file exists there (13,295 bytes, matching the last entry
processed, LB-16649) — the other 29 downloaded files from this run were
overwritten mid-batch and are gone. The 16 entries that made it into qBittorrent
are fine (the add happens before the next entry's download can overwrite the
file), but the 14 `downloaded`-only entries (no qbt add — mostly blocked by a
qBittorrent "Conflict", i.e. already present) have no retrievable file on disk
and would need to be re-fetched individually (`--lb <N>`) once BUG-233 is fixed.

## Follow-up

- BUG-233 fix is now higher priority — it's not just a cosmetic filename issue,
  it silently destroys batch-run output.
- BUG-234 (new): investigate why checksum body-search matched 3 different shows
  to WTRF topic 55005; likely an over-broad checksum/equipment signal collision.
- The 13 `needs_review` and 11 `ambiguous` entries remain candidates for manual
  review at the linked topic URLs (see `wtrf_downloads` table).
