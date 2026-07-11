# LosslessBob Checksum Lookup

Cross-platform desktop app for the [LosslessBob](http://www.losslessbob.wonderingwhattochoose.com/) Bob Dylan lossless recording archive: checksum lookup, collection tracking, verification, and browsing — Electron/React frontend over a local Flask backend.

## Quickstart

1. Download the installer for your platform from the latest `v*` release on the [Releases page](https://github.com/kuddukan42/losslessbob/releases) — `LosslessBob-<version>-linux-x86_64.AppImage` or `LosslessBob-<version>-windows-Setup.exe` (a portable `.exe` is also available).
2. Launch the app.
3. Follow the first-run wizard — it downloads the full dataset, optional cached site pages, and points you at adding your collection folders. No manual imports needed.

## How the data gets to you

| Release | Contents | Cadence |
|---|---|---|
| `master-YYYY-MM-DD` | The full database snapshot: all LB entries, checksums, curated status, geocoded concert locations, setlists, TapeMatch families, curated lists, flat-file history | Roughly monthly, published by the curator |
| `sitedata-YYYY-MM-DD` | Cached LB site pages: detail pages, artwork, lbbcd indexes (core), plus optional checksum/fingerprint text attachments (files) | On demand, changes slowly |
| Monthly flat file | Checksum deltas from the LB site, applied between master snapshots via Setup → Monthly update | Monthly, from the LB site |

The first-run wizard installs the master snapshot and (optionally) site data. After that, the in-app monthly update keeps checksums current between master releases. End users never scrape the LB site — scraping and geocoding are curator tasks whose output ships in the releases above.

## Development setup

```bash
git clone git@github.com:kuddukan42/losslessbob.git
cd losslessbob
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 run_backend.py        # Flask backend on port 5174
cd gui_next && npm install && npm run dev   # Electron/React frontend
```

Architecture, DB schema, Flask routes, and screen inventory live in `PROJECT.md`. Distribution builds: `npm run dist:linux` / `npm run dist:win` from `gui_next/`.

## Flat File Format

The LosslessBob flat file is tab-delimited:

```
checksum<TAB>filename<TAB>type<TAB>lb_number<TAB>xref
```

Where `type` is: `f` = ffp (FLAC fingerprint), `s` = st5 (shntool), `m` = md5

## Supported Checksum Formats

- **FFP:** `filename.flac:checksum`
- **MD5:** `checksum *filename.flac` or `checksum filename.flac`
- **ST5:** `checksum *filename.shn`
