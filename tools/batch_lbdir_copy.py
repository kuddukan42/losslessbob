#!/usr/bin/env python3
"""
batch_lbdir_copy.py

For every folder in my_collection, check whether a lbdir*.txt file exists
on disk. If not, find the matching lbdir file in the local attachment cache
(data/attachments/LB-XXXXX/ or data/site/files/) and copy it to the folder.

Usage:
    python batch_lbdir_copy.py [--db PATH] [--dry-run] [--verbose]

Defaults:
    --db   <script_dir>/data/losslessbob.db
"""

import argparse
import glob
import os
import shutil
import sqlite3
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_lbdir_in_dir(directory: str) -> str | None:
    """Return the first lbdir*.txt path found in directory, or None."""
    if not os.path.isdir(directory):
        return None
    pattern = os.path.join(directory, "lbdir*.txt")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def find_cached_lbdir(lb_number: int, data_root: str) -> str | None:
    """
    Look for a cached lbdir file in:
      1. data/attachments/LB-{N:05d}/lbdir*.txt   (per-entry download cache)
      2. data/site/files/LBF-{N}-lbdir*.txt        (site mirror)

    Returns the first found path, or None.
    """
    # 1. Attachment cache (primary — this is what retrieve uses)
    att_dir = os.path.join(data_root, "attachments", f"LB-{lb_number:05d}")
    match = find_lbdir_in_dir(att_dir)
    if match:
        return match

    # 2. Site mirror files directory
    files_dir = os.path.join(data_root, "site", "files")
    if os.path.isdir(files_dir):
        # Pattern: LBF-{N}-lbdir*.txt  (N not zero-padded in filename prefix)
        for candidate in glob.glob(os.path.join(files_dir, f"LBF-{lb_number}-lbdir*.txt")):
            return candidate
        # Also try zero-padded variant just in case
        for candidate in glob.glob(os.path.join(files_dir, f"LBF-{lb_number:05d}-lbdir*.txt")):
            return candidate

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Copy missing lbdir files to collection folders.")
    parser.add_argument("--db", default=None,
                        help="Path to losslessbob.db (default: <script_dir>/data/losslessbob.db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be copied without doing anything")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print all folders including those already OK")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = args.db or os.path.join(script_dir, "data", "losslessbob.db")
    data_root = os.path.dirname(db_path)  # data/

    if not os.path.isfile(db_path):
        sys.exit(f"ERROR: database not found: {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # Fetch all collection entries that have a disk_path and lb_number
    rows = con.execute(
        "SELECT lb_number, disk_path FROM my_collection "
        "WHERE disk_path IS NOT NULL AND disk_path != '' "
        "ORDER BY lb_number"
    ).fetchall()
    con.close()

    if not rows:
        sys.exit("No collection entries with disk_path found.")

    total      = len(rows)
    ok         = 0
    copied     = 0
    no_cache   = 0
    no_folder  = 0
    errors     = 0

    print(f"Checking {total} collection entries...\n")

    for row in rows:
        lb      = row["lb_number"]
        folder  = row["disk_path"]
        lb_tag  = f"LB-{lb:05d}"

        # 1. Folder must exist on disk
        if not os.path.isdir(folder):
            if args.verbose:
                print(f"[SKIP ] {lb_tag}  folder missing on disk: {folder}")
            no_folder += 1
            continue

        # 2. Already has a lbdir file?
        existing = find_lbdir_in_dir(folder)
        if existing:
            if args.verbose:
                print(f"[OK   ] {lb_tag}  {os.path.basename(existing)}")
            ok += 1
            continue

        # 3. Find in cache
        cached = find_cached_lbdir(lb, data_root)
        if not cached:
            print(f"[MISS ] {lb_tag}  no cached lbdir — run retrieve first: {folder}")
            no_cache += 1
            continue

        src_name = os.path.basename(cached)
        dest     = os.path.join(folder, src_name)

        # Never overwrite — dest must not exist
        if os.path.exists(dest):
            print(f"[SKIP ] {lb_tag}  dest already exists (not overwriting): {dest}")
            ok += 1
            continue

        if args.dry_run:
            print(f"[DRY  ] {lb_tag}  would copy {src_name}  →  {folder}")
            copied += 1
            continue

        try:
            shutil.copy2(cached, dest)
            print(f"[COPY ] {lb_tag}  {src_name}  →  {folder}")
            copied += 1
        except OSError as exc:
            print(f"[ERROR] {lb_tag}  {exc}")
            errors += 1

    # Summary
    print()
    print("=" * 60)
    if args.dry_run:
        print(f"DRY RUN — no files written")
    print(f"Total entries : {total}")
    print(f"Already OK    : {ok}")
    print(f"Copied        : {copied}")
    print(f"No cache      : {no_cache}  (need lbdir retrieve)")
    print(f"No disk folder: {no_folder}")
    if errors:
        print(f"Errors        : {errors}")


if __name__ == "__main__":
    main()
