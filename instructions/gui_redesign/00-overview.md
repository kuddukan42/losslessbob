# 00 · Product Overview

## What LosslessBob is

A desktop app for collectors of Bob Dylan live recordings. It maintains:

- A **master checksum database** (LB-numbered "entries", ~16,630 of them) — the canonical catalog of every known Dylan recording
- A user's **personal collection** of audio folders on disk (~15,967 owned, across multiple mounts)
- A **bootleg-CD title catalog** (LBBCD, ~1,380 titles)
- Concert metadata, performer history, attachments (LBDIR / FFP text files), spectrograms, geocoded venues

The app's reason for existing is **the ingest pipeline**: a user drops a batch of new folders, and the app runs them through verify → lookup → rename → LBDIR-attach so they land in the collection correctly tagged. This was previously a multi-tab dance; the new design unifies it into one screen.

## Who uses it

Two personas, gated by a **Curator mode** toggle:

| Persona | What they do | Default state |
|---|---|---|
| **Collector** (most users) | Ingest folders, search the master DB, manage their library | Curator mode **off** — DB Editor + Scraper hidden |
| **Curator** (maintains the master DB) | Edits LB entries, runs scrapers, publishes DB updates | Curator mode **on** — extra nav group revealed |

## Screen inventory

| # | Screen | Built? | Purpose |
|---|---|---|---|
| 1 | Home | ✅ | Dashboard — quick-jumps, stats, recent activity, resume card |
| 2 | Pipeline | ✅ | **Primary workflow.** Drop folders → verify/lookup/rename/LBDIR for batches of 50–100 |
| 3 | Verify | stub | Sub-tool: checksum verification of one folder |
| 4 | Lookup | stub | Sub-tool: find LB# for an unknown folder |
| 5 | Rename | stub | Sub-tool: standardize folder names |
| 6 | LBDIR | stub | Sub-tool: generate/attach LBDIR text file |
| 7 | My Collection | ✅ | The user's owned recordings (15,967 rows, virtualized) |
| 8 | Search | ✅ | Search master DB with facets (16,630 rows) |
| 9 | Bootlegs | ✅ | LBBCD catalog (1,380 titles) w/ cover art + tracklist |
| 10 | Attachments | stub | LBDIR/FFP text-file viewer |
| 11 | Spectrograms | stub | Spectrogram image gallery |
| 12 | Map | stub | Concert-venue map (6,676 pinned) |
| 13 | DB Editor | ✅ | **Curator only.** Raw table access to all DB tables |
| 14 | Scraper | ✅ | **Curator only.** Crawl + scrape entry pages |
| 15 | Setup | ✅ | DB/integrations/preferences |
| 16 | Themes | ✅ | Mode × accent × density picker |

"Stub" screens have well-defined slots in the app shell + nav, but a full design wasn't requested. Their MD section describes intended behavior; treat them as future work.

## Visual identity in one sentence

Information-dense desktop tool with a warm cream/dark-graphite palette, status-color edge bars on every data row (green/amber/red/blue/grey live at the left edge of `<tr>`), and small monospace numerics. Think "modern Bloomberg terminal meets Linear" — dense but legible, lots of subtle border hairlines, no decorative gradients.
