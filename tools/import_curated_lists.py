#!/usr/bin/env python3
"""CLI tool to import curator "best of" picks (TODO-181) into curated_lists /
curated_list_entries.

Two sources are supported out of the box:

  carbonbit — data/lists/FLglist.xlsx ("front line G list" sheet). One row per
    date; column B is the date/venue, column C is carbonbit's pick(s) for
    that date (LB number(s), "NO LB NUMBER", or free-text notes). A date can
    have more than one LB number (e.g. "LB-415 + LB-5993").

  10haaf — data/lists/dylan_boots.zip + data/lists/years.zip. HTML "Bootleg
    Overview" pages, one per year, listing many recordings per date. Every
    distinct LB-XXXXX reference found across both zips is taken as part of
    10haaf's catalog (union of both archives; they disagree on ~1,100 entries
    between an older per-year snapshot and a newer allboots.html dump, so the
    union avoids silently dropping either side).

Both xlsx and zip parsing use only the standard library (zipfile + ElementTree),
matching the project's existing ODS-import pattern in db.import_dylan_performances.

Usage::

    python tools/import_curated_lists.py
    python tools/import_curated_lists.py --carbonbit-only
    python tools/import_curated_lists.py --10haaf-only

Must be run from the project root directory (the folder containing
``backend/`` and ``tools/``).
"""

import argparse
import logging
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db  # noqa: E402
from backend.paths import DATA_DIR  # noqa: E402

_log = logging.getLogger(__name__)

_LISTS_DIR = DATA_DIR / "lists"
_LB_PATTERN = re.compile(r"LB[\s-]?(\d+)", re.IGNORECASE)
_XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _parse_xlsx_sheet1(xlsx_path: Path) -> list[tuple[str, str]]:
    """Return (event, status) text pairs from the first sheet of an .xlsx file.

    Reads xl/sharedStrings.xml + xl/worksheets/sheet1.xml directly (xlsx is a
    zip of XML) so no third-party dependency (openpyxl) is required.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        sst_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = [
            "".join(t.text or "" for t in si.findall(".//m:t", _XLSX_NS))
            for si in sst_root.findall("m:si", _XLSX_NS)
        ]
        sheet_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    def cell_value(c) -> str:
        v = c.find("m:v", _XLSX_NS)
        if v is None or v.text is None:
            return ""
        return shared[int(v.text)] if c.get("t") == "s" else v.text

    pairs = []
    sheet_data = sheet_root.find("m:sheetData", _XLSX_NS)
    for row in sheet_data.findall("m:row", _XLSX_NS):
        cells = {}
        for c in row.findall("m:c", _XLSX_NS):
            col = re.match(r"([A-Z]+)", c.get("r")).group(1)
            cells[col] = cell_value(c)
        event, status = cells.get("B", ""), cells.get("C", "")
        if event or status:
            pairs.append((event, status))
    return pairs


def import_carbonbit(xlsx_path: Path | None = None, db_path=None) -> int:
    """Import carbonbit's per-date picks from FLglist.xlsx.

    Args:
        xlsx_path: Override path to the .xlsx file (default: data/lists/FLglist.xlsx).
        db_path: Optional database path override.

    Returns:
        Number of distinct (lb_number, event) entries written.
    """
    xlsx_path = xlsx_path or (_LISTS_DIR / "FLglist.xlsx")
    if not xlsx_path.exists():
        _log.warning("carbonbit: %s not found, skipping", xlsx_path)
        return 0

    list_id = db.get_or_create_curated_list(
        "carbonbit", label="carbonbit's picks", source=str(xlsx_path.name), db_path=db_path
    )

    entries: list[tuple[int, str]] = []
    for event, status in _parse_xlsx_sheet1(xlsx_path):
        if not event:
            continue  # legend/notes rows in column A bleed into rows with no real event
        for lb_str in _LB_PATTERN.findall(status):
            entries.append((int(lb_str), event.strip()))

    db.add_curated_list_entries(list_id, entries, db_path=db_path)
    _log.info("carbonbit: wrote %d entries (list_id=%d)", len(entries), list_id)
    return len(entries)


def import_10haaf(
    dylan_boots_zip: Path | None = None, years_zip: Path | None = None, db_path=None
) -> int:
    """Import 10haaf's bootleg catalog from dylan_boots.zip + years.zip.

    Every distinct LB-XXXXX reference found across both archives' HTML pages
    is treated as part of the curated set (see module docstring for why the
    union, not a single source, is used).

    Args:
        dylan_boots_zip: Override path (default: data/lists/dylan_boots.zip).
        years_zip: Override path (default: data/lists/years.zip).
        db_path: Optional database path override.

    Returns:
        Number of distinct LB numbers written.
    """
    dylan_boots_zip = dylan_boots_zip or (_LISTS_DIR / "dylan_boots.zip")
    years_zip = years_zip or (_LISTS_DIR / "years.zip")

    lb_numbers: set[int] = set()
    sources = []
    for zip_path in (dylan_boots_zip, years_zip):
        if not zip_path.exists():
            _log.warning("10haaf: %s not found, skipping", zip_path)
            continue
        sources.append(zip_path.name)
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if not name.lower().endswith(".html"):
                    continue
                html = z.read(name).decode("latin-1")
                lb_numbers.update(int(n) for n in _LB_PATTERN.findall(html))

    if not lb_numbers:
        _log.warning("10haaf: no source archives found, skipping")
        return 0

    list_id = db.get_or_create_curated_list(
        "10haaf", label="10haaf's picks", source=", ".join(sources), db_path=db_path
    )
    entries = [(lb, "") for lb in sorted(lb_numbers)]
    db.add_curated_list_entries(list_id, entries, db_path=db_path)
    _log.info("10haaf: wrote %d entries (list_id=%d)", len(entries), list_id)
    return len(entries)


def main() -> None:
    """Entry point: parse arguments and run the requested curated-list import(s)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Import curator 'best of' picks into curated_lists (TODO-181).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--carbonbit-only", action="store_true", help="Only import carbonbit's list."
    )
    parser.add_argument(
        "--10haaf-only", dest="haaf_only", action="store_true",
        help="Only import 10haaf's list.",
    )
    args = parser.parse_args()

    db.init_db()

    if not args.haaf_only:
        import_carbonbit()
    if not args.carbonbit_only:
        import_10haaf()

    for row in db.get_curated_lists():
        _log.info(
            "curated_lists: %s (%s) — %d entries", row["name"], row["label"], row["entry_count"]
        )


if __name__ == "__main__":
    main()
