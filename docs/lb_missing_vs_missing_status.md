# lb_missing vs. "Missing" in DB Integrity

There are two separate "missing" concepts in LosslessBob that count different things from different tables.

## DB Integrity panel — "Missing: N"

Source: `lb_master` table, `lb_status = 'missing'`

These are LB numbers within the scraped range that the scraper could not successfully fetch — either a 404 response or a number that has never been attempted yet. They are **unresolved gaps**: the system knows the number exists in the range but has no confirmed status for it.

## lb_missing table — 36 rows

Source: `lb_missing` table (separate from `lb_master`)

These are LB numbers that have been **manually confirmed** to never exist on the LB site (the page was allocated but never published). When a number is added here via the DB Editor, `reconcile` runs automatically and sets `lb_master.lb_status = 'nonexistent'` for that number.

## Status flow

```
Scraper hits 404 → lb_master.lb_status = 'missing'   (unconfirmed, shows in DB Integrity)
        ↓
Manual confirmation → inserted into lb_missing table
        ↓
reconcile() runs → lb_master.lb_status = 'nonexistent'  (resolved, no longer counted as missing)
```

## Why the counts differ

The DB Integrity panel only counts `lb_status = 'missing'` rows — unresolved gaps. The 36 entries in `lb_missing` have already been resolved to `'nonexistent'` in `lb_master` and are not shown as a problem. They are two stages of the same lifecycle, not duplicates.

## DB Integrity panel — "Needs review: N"

Source: `lb_master` table, `needs_review = 1`

A flag set by `_compute_lb_status()` when an LB number has **local attachment data but no confirmed webpage** (`has_att=True`, `has_web=False`). The status-precedence rules treat attachments as enough evidence to call it `public`, but attachments alone are ambiguous — the page may have been taken down or the attachment may be misattributed. These are flagged so they can be manually checked.

`needs_review` is independent of `lb_status`. An LB can be `public` and also `needs_review = 1` at the same time.

## lb_master lb_status values

| Status | Meaning |
|---|---|
| `public` | LB page exists and is publicly visible |
| `private` | LB page exists but is private/hidden (checksums in DB, no web page) |
| `missing` | Not yet scraped or returned 404; unconfirmed |
| `nonexistent` | Confirmed to never have existed; entry in lb_missing |

## lb_master flags

| Flag | Meaning |
|---|---|
| `needs_review` | `public` status inferred from attachments only — no confirmed webpage |
| `manual_override` | Status was set manually and reconcile will not auto-change it |
| `public_no_checksums` | LB page is public but no checksums have been imported yet |
