# Show Dossier

> Sources: `PROJECT.md` §Show Dossier routes (~line 1336) · `backend/dossier.py` ·
> `backend/templates/dossier.html` · `instructions/FABLE_SHOW_DOSSIER.md` ·
> Status: seeded 2026-07-22

One-call answer to "everything the app knows about one show date"
(TODO-257/260, shipped 2026-07-17). `backend/dossier.py:build_dossier()`
assembles it; `filter_dossier_sections()`/`render_bbcode()` are the shared
presentation layer.

## Routes

| Route | Output |
|---|---|
| `GET /api/dossier?date=&location?=&channel?=` | Full JSON dossier |
| `GET /api/dossier/html` | Self-contained print-first HTML attachment (`dossier-<date>.html`) — first Jinja template in the repo; sepia design + inline SVG Mercator locator map (`_render_locator_svg()`, GeoJSON in `backend/assets/`) |
| `GET /api/dossier/bbcode` | Compact BBcode digest for forum posts — same filtered view as HTML, so the two can never disagree |

HTML/BBcode add `sections?=` (toggle context/setlist) and `local_analysis?=0`
(strip picks/quality/curated/recommendation → outward-facing facts only).

## What's in a dossier

Show identity · historical context (`olof_chronicle`/bobtalk/notes/lineup) ·
rarity-flagged setlist (`song_performances` counts; `only`/`first`/`last`/
`rare` ≤10) · sources grouped by TapeMatch family with taper credit
(conflicted attributions skipped) · lineage notes · pick ranking + evidence ·
quality verdicts · curated-list endorsements · alt-fileset counts · a rank-1
`recommendation`.

## Design invariants

- **Feature-detected sections** — every section is omitted (never null-faked)
  when its source table is absent/empty; a fresh install still gets a valid,
  smaller dossier.
- **Ambiguity** — two-show days detected via distinct `olof_events.venue`
  values (not `entries.location` free text) → HTTP 300 with candidates when
  `location` isn't given. See [Setlist-Sources](Setlist-Sources.md).
- **Channels** — `public` (default) reduces private sources to
  `{lb, private: true}`; `full` includes everything. Disk paths, collection
  ownership, friend data and wishlists are never included in either.

## GUI

Export via `DossierExportModal.tsx` from the Library screen
([GUI](GUI.md)). Tests: `tests/test_dossier.py` (fresh-install degrade,
channel gating, rarity, ambiguity, family grouping, bbcode digest).
