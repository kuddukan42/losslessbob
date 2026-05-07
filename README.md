# LosslessBob Checksum Lookup

Cross-platform replacement for the original Windows Checksum_Lookup utility for the [LosslessBob](http://www.losslessbob.wonderingwhattochoose.com/) Bob Dylan lossless recording archive.

## Prerequisites

- Python 3.11 or newer
- pip (comes with Python)
- **Windows:** Microsoft Visual C++ Redistributable (for PyQt6)
- **Windows (SDF import):** `ExportSqlCE40.exe` — place in `tools/` folder. Download from: https://github.com/ErikEJ/SqlCeToolbox
- **macOS/Linux:** Use the flat file export from the LosslessBob downloads page instead of SDF

## Installation

```bash
git clone <repo>
cd losslessbob
pip install -r requirements.txt
python main.py
```

## First Database Import

1. Download the latest zip from the LosslessBob downloads page
2. Unzip — you will find either a `.sdf` file (Windows) or a flat file (`.txt`)
3. Copy the `.sdf` or flat file into the `data/` folder
4. Open the app, go to the **Setup** tab, click **Import New SDF**
5. Wait for import to complete (progress shown in status bar)
6. Optionally start the scraper to fetch entry metadata

## Monthly Update Workflow

1. Click **Check for Update** in the Setup tab (or Database menu)
2. If an update is available, download the new zip from the LosslessBob site
3. Drop the new `.sdf` or flat file into the `data/` folder
4. The app detects the new file automatically (via file watcher) and starts import
5. Only new LB entries are processed — takes seconds, not minutes

## Features

- **Lookup tab:** Paste checksum text from clipboard or drag-drop files/folders to look up LB numbers
- **Color coding:** Green = complete match, Orange = not found, Pink = incomplete set, Yellow = duplicate
- **Rename Folders tab:** Propose and execute folder renames to append LB numbers
- **Search tab:** Full-text search across entry metadata (date, location, description)
- **Attachments tab:** Browse locally cached files (ffp, txt, html) for each LB entry
- **Setup tab:** Import database, configure scraper, check for updates

## Packaging with PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
  --name "LosslessBobLookup" \
  --add-data "data:data" \
  --hidden-import PyQt6.QtWebEngineWidgets \
  main.py
```

> **Note:** Keep the `data/` folder (SQLite DB + attachments) alongside the executable — do not bundle it, so it can be updated independently.

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
