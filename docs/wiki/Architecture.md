# Architecture

> Sources: `PROJECT.md` §Tech Stack, §File Structure · `.claude/CLAUDE.md` · Status: seeded 2026-07-06

## Big picture

LosslessBob is a local-first desktop app for managing a Bob Dylan lossless recording
archive: checksum lookup, metadata scraping from losslessbob.com, collection
integrity monitoring, recording-family matching (TapeMatch), and concert quality
ranking (Concert Ranker).

```
┌─────────────────────┐     HTTP :5174      ┌──────────────────────┐
│ gui_next             │◄───────────────────►│ Flask backend         │
│ Electron + React     │                     │ backend/app.py        │
│                      │                     │ SQLite (single DB)    │
└─────────────────────┘                     │ backend/db.py         │
                                            └──────────┬───────────┘
        tools/tapematch/  ──── family sync ────────────┘
        (audio matching pipeline, own CLI + config)
```

## Components

- **`backend/`** — Flask API on hardcoded port **5174**. Modules: `app.py` (routes),
  `db.py` (schema + queries), `checksum_utils.py`, `importer.py`, `scraper.py`,
  `site_crawler.py`, `wtrf_scraper.py` (forum torrent fetcher), `scheduler.py`,
  `geocoder.py`.
- **`gui_next/`** — Electron + React + TypeScript. The sole GUI (legacy PyQt6
  `gui/` removed 2026-07-16). i18n via locale JSON (en/de/fr/es/it/nl). Verified
  with `/gui-check` (typecheck + build), never screenshots.
- **`tools/tapematch/`** — standalone audio-matching pipeline (see [TapeMatch](TapeMatch.md)).
  Run artifacts live in `data/tapematch/runs/`.
- **`concert_ranker/`** — quality-scan / ranking logic (see [Concert-Ranker](Concert-Ranker.md)).
- **`docs/`** — CLI docs, schema.html (auto-deploys to losslessbob-schema.pages.dev),
  data-ownership notes, this wiki.
- **`instructions/`** — spec pack (FABLE_* specs; read `SPEC_INTEGRATION_NOTES.md`
  before implementing any of them).

## Environment invariants

- Python: `.venv/bin/python3` only (bare `python` not on PATH). Python 3.11+.
- Backend port 5174 is hardcoded everywhere — changing it is an atomic, logged change.
- Single SQLite DB; migrations are idempotent `ALTER TABLE` in try/except.
- `requirements.txt` pins exact versions.
