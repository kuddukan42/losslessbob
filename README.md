# LosslessBob Checksum Lookup

Cross-platform replacement for the original Windows Checksum_Lookup utility for the [LosslessBob](http://www.losslessbob.wonderingwhattochoose.com/) Bob Dylan lossless recording archive.

## Prerequisites

- Python 3.11 or newer
- pip (comes with Python)
- **Windows:** Microsoft Visual C++ Redistributable (for PyQt6)

## Installation

```bash
git clone <repo>
cd losslessbob
pip install -r requirements.txt
python main.py
```

## First Database Import

1. Download the latest zip from the LosslessBob downloads page
2. Unzip — you will find a flat file (`.txt`)
3. Open the app, go to the **Setup** tab, click **Import Database File...**
4. Select the `.txt` flat file
5. Wait for import to complete (progress shown in status bar)
6. Optionally start the scraper to fetch entry metadata

## Monthly Update Workflow

1. Click **Check for Update** in the Setup tab (or Database menu)
2. If an update is available, download the new zip from the LosslessBob site
3. Drop the new flat file (`.txt`) into the `data/` folder
4. The app detects the new file automatically (via file watcher) and starts import
5. Only new LB entries are processed — takes seconds, not minutes

## Features

- **Lookup tab:** Paste checksum text from clipboard or drag-drop files/folders to look up LB numbers
- **Color coding:** Green = complete match, Orange = not found, Pink = incomplete set, Yellow = duplicate
- **Rename Folders tab:** Propose and execute folder renames to append LB numbers
- **Verify tab:** Verify audio files against their checksum files (FFP, MD5, ST5)
- **lbdir tab:** Check and retrieve lbdir verification files from the LosslessBob cache
- **Search tab:** Full-text search across entry metadata (date, location, description)
- **My Collection tab:** Track which LB entries you own, scan directories, export missing list
- **Attachments tab:** Browse locally cached files (ffp, txt, html) for each LB entry
- **Setup tab:** Import database, configure scraper, check for updates

## Map Tab

The **Map** tab displays concert locations on an interactive OpenStreetMap map (Leaflet).

- Requires `PyQt6-WebEngine` (already in `requirements.txt`)
- The map can also be viewed in any browser at `http://localhost:5174/map` while the app is running
- **Geocoding (curators only):** Run `python tools/geocode_locations.py` once to populate coordinates
  via Nominatim. End users receive pre-geocoded coordinates as part of the master data release and
  never call Nominatim themselves.
- OSM tile requests reveal your IP address to OpenStreetMap's tile CDN
- Attribution: © OpenStreetMap contributors

## Packaging with PyInstaller

Use the provided `losslessbob.spec`:

```bash
pip install pyinstaller
pyinstaller losslessbob.spec
```

Output is in `dist/LosslessBob/`. Keep the `data/` folder alongside the executable — do not bundle it, so it persists across updates.

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
