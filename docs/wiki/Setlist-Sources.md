# Setlist Sources

> Sources: `PROJECT.md` §olof tables (~line 912), §bobdylan/setlistfm tables (~570–632),
> §Olof routes (~1371), §gaps routes (~1332) · `backend/olof_*.py` · `backend/bobserve_*.py` ·
> Status: seeded 2026-07-22

The app cross-references three external setlist corpora against `entries`.
All parsed data is **local-only** (not in MASTER export — P5 decision pending).

## The three corpora

| Corpus | Modules | Tables | Notes |
|---|---|---|---|
| Olof Björner (Still On The Road) | `olof_fetcher.py` → `olof_parser.py` | `olof_pages` → `olof_events` + `olof_songs` | DSN pages mirrored to `data/olof/pages/`; event_id = DSN number |
| bobserve.com (2022+) | `bobserve_fetcher.py` → `bobserve_parser.py` | same tables, `source='bobserve'`, ids 9M+ | The real 2022+ setlist source — Yearly Chronicle PDFs carry no setlists (TODO-228 pivot) |
| bobdylan.com + setlist.fm | `bobdylan_scraper.py`, `setlistfm.py` | `bobdylan_shows/_setlist`, `setlistfm_shows/_setlist` (MASTER) | setlist.fm via API key, joined by `date_str` |

Yearly Chronicles are still parsed for **calendar/diary + new-tapes** data
(`olof_chronicle_parser.py` → `olof_chronicle`, `olof_new_tapes`); their
2022+ setlist appendix path is superseded and was never populated.

## Derived layers

- **Song spine** — `song_performances` + `song_canonical` rebuilt from
  `olof_songs JOIN olof_events` (`backend/song_index.py`); feeds dossier
  rarity flags (`only`/`first`/`last`/`rare`).
- **Setlist fingerprinting** (TODO-225) — `setlist_fingerprint.py` scores
  `entries.setlist` free text against `olof_songs`, keeps top matches in
  `setlist_fingerprint_suggestions` (curator review queue).
- **Gaps view** (TODO-256) — `gap_analysis.py` classifies every `olof_events`
  concert date covered/partial/gap/future against `entries`, computed live
  (no derived table). GUI: `ScreenGaps` at `/gaps`.

## Consumers

- `/api/olof/*` routes (date, event, chronicle, status, bobtalk_search,
  compare) — see PROJECT.md ~line 1371. GUI gates all Olof UI on
  `/api/olof/status` `events > 0`.
- Library DetailPanel **Olof tab** (both lenses) incl. per-copy setlist
  comparison via `POST /api/olof/compare`.
- [Show Dossier](Show-Dossier.md) — show identity/ambiguity comes from
  `olof_events.venue` (never `entries.location`, which is noisy free text).
- Geocoder priority chain uses all corpora for coordinates
  (`location_geocoded.source`).

## Gotchas

- Title matching goes through `db.normalize_title_for_match` — cp1252
  apostrophe fold, case/punct collapse, leading-"The" strip.
- Event ids occupy three disjoint ranges (DSN / `year*1000+seq` / 9M+
  bobserve) — no collisions by construction.
- bobserve `olof_songs` rows are title+credits only (parsed from the page's
  `data-clipboard-text` blob); DSN rows carry full annotations/takes.
