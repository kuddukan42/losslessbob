# Architecture

> Sources: `PROJECT.md` §Tech Stack, §File Structure · `.claude/CLAUDE.md` ·
> Status: fresh 2026-07-22

## Big picture

LosslessBob is a local-first desktop app for managing a Bob Dylan lossless recording
archive: checksum lookup, metadata scraping from losslessbob.com, collection
integrity monitoring & pipeline filing, recording-family matching (TapeMatch),
concert quality ranking (Concert Ranker), setlist cross-referencing (Olof/bobserve),
and curator publishing (master data, dossiers, forum posts).

```
┌─────────────────────┐     HTTP :5174      ┌──────────────────────┐
│ gui_next             │◄───────────────────►│ Flask backend         │
│ Electron + React     │                     │ backend/app.py        │
│ 20 screens           │                     │ SQLite (single DB)    │
└─────────────────────┘                     │ backend/db.py         │
                                            └──────────┬───────────┘
        tools/tapematch/  ──── family sync ────────────┘
        (audio matching pipeline, own CLI + config)
```

## Components

- **`backend/`** — Flask API on hardcoded port **5174**. ~40 modules; core:
  `app.py` (all routes), `db.py` (schema + queries), `checksum_utils.py`,
  `importer.py`, `scraper.py`, `site_crawler.py`, `scheduler.py`. Feature
  clusters: setlist corpora (`olof_*`, `bobserve_*`, `setlistfm.py`,
  `bobdylan_scraper.py`), derived data (`taper_attribution.py`, `song_index.py`,
  `setlist_fingerprint.py`, `gap_analysis.py`, `dossier.py`), collection ops
  (`filer.py`, `integrity_monitor.py`, `qbittorrent.py`, `sharing.py`,
  `forum_poster.py`). See [Backend-API](Backend-API.md).
- **`gui_next/`** — Electron + React + TypeScript, the sole GUI (legacy PyQt6
  removed 2026-07-16). i18n via locale JSON (en/de/fr/es/it/nl). Verify with
  `/gui-check` (typecheck + build) + `/verify` screenshots for visual changes
  (see [Visual-Verification](Visual-Verification.md)).
- **`tools/`** — CLIs & drivers: derived-data recompute steps (`parse_lineage`,
  `attribute_tapers`, `compute_show_picks`, `compute_song_performances`),
  `ledger.py` (BUGS/TODO bookkeeping), `electron_driver.mjs` (screenshot engine).
- **`tools/tapematch/`** — standalone audio-matching pipeline ([TapeMatch](TapeMatch.md));
  run artifacts in `data/tapematch/runs/`.
- **`concert_ranker/`** — quality-scan / ranking package ([Concert-Ranker](Concert-Ranker.md)).
- **`docs/`** — CLI docs, `schema.html` (auto-deploys to losslessbob-schema.pages.dev),
  data-ownership notes, this wiki. **`instructions/`** — FABLE_* spec pack (read
  `SPEC_INTEGRATION_NOTES.md` before implementing any spec).
- **CI** — `.github/workflows/ci.yml`: backend suite + gui-check on every push.

## Environment invariants

- Python: `.venv/bin/python3` only (bare `python` not on PATH). Python 3.11+.
- Backend port 5174 is hardcoded everywhere — changing it is an atomic, logged change.
- Single SQLite DB; migrations are idempotent `ALTER TABLE` in try/except.
- `requirements.txt` pins exact versions. Logs consolidated under `data/logs/`.
