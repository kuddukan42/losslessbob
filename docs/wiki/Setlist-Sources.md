# Setlist Sources

> Sources: `PROJECT.md` §olof tables (~line 1400–1560), §Olof routes (grep `/api/olof`) ·
> `backend/olof_*.py` · `backend/bobserve_*.py` · `backend/bobdylan_scraper.py` ·
> `backend/setlistfm.py` · `backend/song_index.py` · `backend/setlist_fingerprint.py` ·
> `backend/gap_analysis.py` · `backend/qc/corroborate.py` · `tools/olof_reparse_diff.py` ·
> `tools/tuit_olof_spine.py` · Status: fresh 2026-10-25

The app cross-references external setlist corpora against `entries`. Parsed `olof_*`
data is **local-only** (not in MASTER export).

## The corpora

| Corpus | Modules | Tables | Notes |
|---|---|---|---|
| Olof Björner (Still On The Road) | `olof_fetcher.py` → `olof_parser.py` | `olof_pages` → `olof_events` + `olof_songs` | DSN pages mirrored to `data/olof/pages/`; event_id = DSN number |
| bobserve.com (2022+) | `bobserve_fetcher.py` → `bobserve_parser.py` | same tables, `source='bobserve'`, ids 9M+ | real 2022+ setlist source (TODO-228 pivot); `--index-only` also fills an index used for pre-2022 deep links |
| bobdylan.com + setlist.fm | `bobdylan_scraper.py`, `setlistfm.py` | `bobdylan_shows/_setlist`, `setlistfm_shows/_setlist` (MASTER) | setlist.fm via API key, joined by `date_str` |

Yearly Chronicles are parsed only for calendar/diary + new-tapes data
(`olof_chronicle_parser.py` → `olof_chronicle`, `olof_new_tapes`); no setlists.

## Derived layers

- **Song spine** — `song_performances` + `song_canonical` rebuilt from `olof_songs JOIN
  olof_events` (`song_index.py`); feeds dossier rarity flags.
- **Setlist fingerprinting** (TODO-225) — `setlist_fingerprint.py` scores
  `entries.setlist` text against `olof_songs` into `setlist_fingerprint_suggestions`.
- **Cross-source corroboration** (TODO-342) — `backend/qc/corroborate.py`
  (`setlist_quorum`, `venue_check`) compares Olof/setlist.fm/bobdylan.com; feeds QC rule
  R-O4 and the dossier identity gate G1. `tools/tuit_olof_spine.py` (TODO-338) crosses
  TUIT's show spine against `olof_events` (read-only report).
- **Coverage classification** — `gap_analysis.py` classifies each `olof_events` concert
  date covered/partial/gap/future against `entries`, live. The Gaps screen and `/api/gaps/*`
  were deleted (TODO-270); it now feeds the Library's `uncirculated`/`upcoming` rows and
  `GET /api/shows/<iso>/olof` (DetailPanel Olof tab).

## Consumers

- `/api/olof/*` (fetch, parse, chronicle_parse, date, event, chronicle, status,
  bobtalk_search, compare) — GUI gates Olof UI on `/api/olof/status` `events > 0`.
- Library DetailPanel Olof tab incl. per-copy comparison via `POST /api/olof/compare`.
- [Show Dossier](Show-Dossier.md) — identity/ambiguity from `olof_events.venue` (never
  `entries.location`); setlist, completeness and claims all read Olof.
- Geocoder priority chain (`location_geocoded.source`).

## Gotchas

- Titles match via `db.normalize_title_for_match` (cp1252 apostrophe fold, punct
  collapse, leading-"The" strip).
- Event ids occupy disjoint ranges (DSN / `year*1000+seq` / 9M+ bobserve).
- bobserve `olof_songs` rows are title+credits only; DSN rows carry annotations/takes.
- Reparse through the diff gate: `tools/olof_reparse_diff.py --snapshot X snapshot`, then
  `python -m backend.olof_parser --file <page>`, then `diff` (UNEXPLAINED must be 0), then
  `song_index.run()`. Never overwrite `.debug/olof_before.db` (the C14 baseline).
- Olof's pages splice the next song's credit mid-word ("Like A Rolling St (…)one");
  `SPLICED_CREDIT_RE` repairs it with or without spaces (BUG-347, regressed as BUG-388).
