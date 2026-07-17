#!/usr/bin/env python3
"""
import_private_metadata.py — TODO-245: fill private LB entries from tj's holdings.

Sources (both in data/private/, git-ignored, never committed):
  lb_summary_all_private.html          Jeff's summary sheet (cp1252): lb, Date,
                                       loc, qual (lineage), desc (notes), rat.
  "No Torrent -LB number overview.xlsx"  Title / LB number / Xref / Date / Taper.

Rules (tj, 2026-07-16):
  * The source files are OLD snapshots — many formerly-private LBs are public
    now. Only LBs whose CURRENT lb_master.lb_status is 'private' are touched.
  * Fill-blank-only: a field is written only when the existing entries value
    is NULL or ''. Scraped/public metadata is never overwritten.
  * Every current private LB gets entries.status='private' (replacing the
    incorrect 'missing'), whether or not metadata was found for it.
  * Rows that received metadata get metadata_source='private_import' so the
    provenance is queryable. A later successful public scrape supersedes all
    of this via the scraper's INSERT OR REPLACE (status→'ok', source→NULL).

Field mapping (verified against 1,032 now-public LBs present in both the HTML
and scraped entries): Date→date_str, loc→location, qual→description,
rat→rating. The HTML 'desc' column is Jeff's private comparison notes (no
public equivalent) — appended to description under a '-- private notes --'
marker. xlsx supplies taper_name and a date_str fallback (Excel serial).

Folder pass (--folders): private collection folders (my_collection.disk_path)
hold free-text info files. Setlists are extracted from numbered track lines,
validated as a sequential 1,2,3… chain (disc restarts allowed) so prose lines
that merely start with a number are dropped; lineage lines fill description
for rows the document pass left blank. Checksums are NOT imported here — the
checksums table already covers 1,403/1,405 private LBs (that coverage is what
derived their 'private' status).

Usage:
  .venv/bin/python3 tools/import_private_metadata.py [--db PATH] [--dry-run]
                                                     [--folders]

  --db PATH    Path to losslessbob.db (default: data/losslessbob.db)
  --dry-run    Report what would change without writing
  --folders    Run the collection-folder txt pass instead of the document pass
"""

import argparse
import glob
import html as html_mod
import os
import re
import sqlite3
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.db import classify_one_entry, extract_taper_and_source  # noqa: E402

PRIVATE_DIR = _project_root / "data" / "private"
HTML_PATH = PRIVATE_DIR / "lb_summary_all_private.html"
XLSX_PATH = PRIVATE_DIR / "No Torrent -LB number overview.xlsx"
NOTES_MARKER = "-- private notes --"

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_EXCEL_EPOCH = date(1899, 12, 30)

# Entry fields the importer may fill (blank-only).
FILL_FIELDS = ("date_str", "location", "description", "rating", "taper_name",
               "source_chain", "lb_category")


def parse_summary_html(path: Path) -> dict[int, dict[str, str]]:
    """Parse Jeff's cp1252 summary-sheet HTML into {lb: field dict}.

    Returns per-LB dicts with keys date_str, location, description, rating —
    plus 'notes' (Jeff's private comparison column, handled separately).
    """
    raw = path.read_bytes().decode("windows-1252")
    out: dict[int, dict[str, str]] = {}
    for row in re.findall(r"<TR VALIGN=TOP>(.*?)</TR>", raw, re.S):
        cells = [html_mod.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<TD[^>]*>(.*?)</TD>", row, re.S)]
        if len(cells) != 6 or not cells[0].isdigit():
            continue
        out[int(cells[0])] = {
            "date_str": cells[1],
            "location": cells[2],
            "description": cells[3],
            "notes": cells[4],
            "rating": cells[5],
        }
    return out


def _excel_serial_to_date_str(serial: str) -> str:
    """Convert an Excel day serial to the site's m/d/yy date format."""
    d = _EXCEL_EPOCH + timedelta(days=int(float(serial)))
    return f"{d.month}/{d.day}/{d.year % 100:02d}"


def parse_overview_xlsx(path: Path) -> dict[int, dict[str, str]]:
    """Parse the No-Torrent overview xlsx into {lb: {taper_name, date_str}}."""
    z = zipfile.ZipFile(path)
    shared = ["".join(t.text or "" for t in si.iter(f"{_XLSX_NS}t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    out: dict[int, dict[str, str]] = {}
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(f"{_XLSX_NS}row"):
        vals: dict[str, str] = {}
        for cell in row.iter(f"{_XLSX_NS}c"):
            col = re.match(r"[A-Z]+", cell.get("r", "")).group()
            v = cell.find(f"{_XLSX_NS}v")
            if v is None or v.text is None:
                continue
            vals[col] = shared[int(v.text)] if cell.get("t") == "s" else v.text
        lb = vals.get("B", "").strip()
        if not lb.isdigit() or int(lb) == 0:
            continue
        rec: dict[str, str] = {}
        if vals.get("E", "").strip():
            rec["taper_name"] = vals["E"].strip()
        if vals.get("D", "").strip():
            try:
                rec["date_str"] = _excel_serial_to_date_str(vals["D"])
            except ValueError:
                pass
        if rec:
            out[int(lb)] = rec
    return out


def build_candidate(lb: int, html_rec: dict | None, xlsx_rec: dict | None,
                    conn: sqlite3.Connection) -> dict[str, str]:
    """Merge sources into candidate field values for one LB (HTML wins)."""
    cand: dict[str, str] = {}
    if html_rec:
        for f in ("date_str", "location", "rating"):
            if html_rec.get(f):
                cand[f] = html_rec[f]
        desc = html_rec.get("description", "")
        notes = html_rec.get("notes", "")
        if notes:
            desc = f"{desc}\n\n{NOTES_MARKER}\n{notes}" if desc else notes
        if desc:
            cand["description"] = desc
    if xlsx_rec:
        for f, v in xlsx_rec.items():
            cand.setdefault(f, v)
    lineage = html_rec.get("description", "") if html_rec else ""
    if lineage:
        taper, chain = extract_taper_and_source(lineage)
        if taper:
            cand.setdefault("taper_name", taper)
        if chain:
            cand["source_chain"] = chain
    if cand.get("description") or cand.get("date_str"):
        cand["lb_category"] = classify_one_entry(
            cand.get("date_str", ""), cand.get("description", ""),
            cand.get("location", ""), conn)
    return cand


# --------------------------------------------------------------------------
# Folder pass (--folders): setlist + lineage from collection info txt files
# --------------------------------------------------------------------------

# Checksum/fingerprint dumps that live beside the info files — never parsed.
_NON_INFO_TXT = re.compile(r"\.(ffp|st5|md5|shnf|flacf)\.txt$", re.I)
_TRACK_LINE = re.compile(r"^\s*(?:d\d+[t\-]?)?(\d{1,3})[-.)\s:]+\s*(\S.*)$")
_TIME_TAIL = re.compile(r"[\s(\[]*\d{1,2}:\d{2}(?::\d{2})?[\s)\]]*$")
_LINEAGE_LINE = re.compile(r"lineage|source\s*:|taper\s*:|\s->\s|\s>\s", re.I)


def _read_text(path: str) -> str:
    """Read a txt file, tolerating cp1252 (legacy trade files)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Path(path).read_text(encoding="windows-1252", errors="replace")


def info_txt_candidates(folder: str) -> list[str]:
    """Return parseable info txt paths in folder (lbdir/checksum dumps excluded)."""
    txts = glob.glob(os.path.join(folder, "*.txt")) + glob.glob(os.path.join(folder, "*.TXT"))
    return [t for t in txts
            if not os.path.basename(t).lower().startswith("lbdir-")
            and not _NON_INFO_TXT.search(t)]


def extract_setlist(text: str) -> list[str]:
    """Extract track titles from numbered lines, validated as a 1,2,3… chain.

    A candidate line must carry the next expected track number; a '1' mid-file
    starts a new disc segment. Stray numbers (prose like '21 year-old …',
    dates, catalogue codes) break no chain and are skipped.
    """
    pairs: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = _TRACK_LINE.match(line.strip())
        if not m:
            continue
        title = _TIME_TAIL.sub("", m.group(2)).strip(" -\t")
        if len(re.sub(r"[^A-Za-z]", "", title)) < 3:
            continue
        pairs.append((int(m.group(1)), title))

    tracks: list[str] = []
    expected: int | None = None
    for num, title in pairs:
        if num == expected or (num == 1 and expected is None):
            tracks.append(title)
            expected = num + 1
        elif num == 1 and expected is not None and expected > 2:
            tracks.append(title)  # disc restart
            expected = 2
    return tracks


def extract_lineage(text: str) -> str:
    """Return lineage/source/taper lines from an info file (joined, trimmed)."""
    lines = [ln.strip() for ln in text.splitlines()
             if _LINEAGE_LINE.search(ln) and len(ln.strip()) > 8]
    return ", ".join(lines[:6])[:800]


def run_folder_pass(conn: sqlite3.Connection, dry_run: bool) -> None:
    """Fill blank setlist (and description for doc-less rows) from folder txts."""
    rows = conn.execute("""
        SELECT mc.lb_number, mc.disk_path, e.setlist, e.description,
               e.taper_name, e.source_chain, e.metadata_source
          FROM my_collection mc
          JOIN lb_master m ON m.lb_number = mc.lb_number
          LEFT JOIN entries e ON e.lb_number = mc.lb_number
         WHERE m.lb_status = 'private'
         ORDER BY mc.lb_number""").fetchall()
    n_setlist = n_desc = n_nofolder = n_notxt = 0
    for r in rows:
        lb, folder = r["lb_number"], r["disk_path"]
        if not folder or not os.path.isdir(folder):
            n_nofolder += 1
            continue
        cands = info_txt_candidates(folder)
        if not cands:
            n_notxt += 1
            continue
        texts = [_read_text(t) for t in cands]
        updates: dict[str, str] = {}

        if not (r["setlist"] or "").strip():
            best = max((extract_setlist(t) for t in texts), key=len, default=[])
            if len(best) >= 4:
                updates["setlist"] = ", ".join(
                    f"{i} {title}" for i, title in enumerate(best, 1))
                n_setlist += 1

        if not (r["description"] or "").strip():
            lineage = max((extract_lineage(t) for t in texts), key=len, default="")
            if lineage:
                updates["description"] = lineage
                n_desc += 1
                taper, chain = extract_taper_and_source(lineage)
                if taper and not (r["taper_name"] or "").strip():
                    updates["taper_name"] = taper
                if chain and not (r["source_chain"] or "").strip():
                    updates["source_chain"] = chain

        if updates:
            if not r["metadata_source"]:
                updates["metadata_source"] = "private_import"
            if not dry_run:
                sets = ", ".join(f"{k}=?" for k in updates)
                conn.execute(f"UPDATE entries SET {sets} WHERE lb_number=?",
                             (*updates.values(), lb))
    if not dry_run:
        conn.commit()
    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"[{mode}] folder_pass private_in_collection={len(rows)} "
          f"setlist_filled={n_setlist} desc_filled={n_desc} "
          f"no_folder={n_nofolder} no_info_txt={n_notxt}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--db", default=str(_project_root / "data" / "losslessbob.db"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--folders", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)")]
    if "metadata_source" not in cols:
        print("entries.metadata_source column missing — start the backend once "
              "(or run backend.db.init_db) to apply migrations, then re-run.")
        return 1

    if args.folders:
        run_folder_pass(conn, args.dry_run)
        return 0

    html_data = parse_summary_html(HTML_PATH)
    xlsx_data = parse_overview_xlsx(XLSX_PATH)
    private_lbs = [r[0] for r in conn.execute(
        "SELECT lb_number FROM lb_master WHERE lb_status='private' ORDER BY lb_number")]

    n_flag = n_meta = n_nosource = 0
    fills = {f: 0 for f in FILL_FIELDS}
    for lb in private_lbs:
        row = conn.execute("SELECT * FROM entries WHERE lb_number=?", (lb,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO entries(lb_number, status) VALUES(?, 'private')", (lb,))
            row = conn.execute(
                "SELECT * FROM entries WHERE lb_number=?", (lb,)).fetchone()

        cand = build_candidate(lb, html_data.get(lb), xlsx_data.get(lb), conn)
        updates: dict[str, str] = {}
        for f in FILL_FIELDS:
            existing = (row[f] or "").strip()
            # lb_category 'unknown' is a computed placeholder, not scraped
            # data — reclassifying it from newly filled fields is still
            # fill-only, not an overwrite.
            if f == "lb_category" and existing == "unknown":
                existing = ""
            if cand.get(f) and cand[f] != "unknown" and not existing:
                updates[f] = cand[f]
                fills[f] += 1

        if updates:
            updates["metadata_source"] = "private_import"
            n_meta += 1
        elif not cand:
            n_nosource += 1
        if row["status"] != "private":
            updates["status"] = "private"
            n_flag += 1
        if updates and not args.dry_run:
            sets = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE entries SET {sets} WHERE lb_number=?",
                         (*updates.values(), lb))

    if not args.dry_run:
        conn.commit()
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    fill_str = " ".join(f"{k}={v}" for k, v in fills.items())
    print(f"[{mode}] private_lbs={len(private_lbs)} status_flipped={n_flag} "
          f"metadata_filled={n_meta} no_source={n_nosource} | {fill_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
