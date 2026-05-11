import hashlib
from datetime import datetime
from pathlib import Path

from backend.db import get_connection, init_db, get_meta, set_meta, DB_PATH

from backend.paths import DATA_DIR


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_flat_file(flat_path, temp_db_path):
    """Parse tab-delimited flat file into temporary SQLite database."""
    init_db(temp_db_path)
    conn = get_connection(temp_db_path)
    inserted = 0
    with open(flat_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO checksums(checksum, filename, chk_type, lb_number, xref) VALUES(?,?,?,?,?)",
                    (parts[0], parts[1], parts[2], int(parts[3]), int(parts[4]) if len(parts) > 4 else 0)
                )
                inserted += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    return inserted


def run_import(source_path, progress_callback=None, db_path=None):
    """
    Import a flat file into the main database.
    Returns dict with new_lb_count, total_lb_count, new_lb_numbers.
    """
    source_path = Path(source_path)
    db_path = db_path or DB_PATH

    if progress_callback:
        progress_callback("Checking file hash...")

    file_hash = md5_file(source_path)
    stored_hash = get_meta("import_hash", db_path)
    if file_hash == stored_hash:
        return {"skipped": True, "reason": "Already imported (same hash)"}

    init_db(db_path)

    with get_connection(db_path) as conn:
        before_lbs = {r[0] for r in conn.execute("SELECT DISTINCT lb_number FROM checksums").fetchall()}

    temp_db_path = DATA_DIR / "temp_import.db"
    if temp_db_path.exists():
        temp_db_path.unlink()

    if progress_callback:
        progress_callback("Parsing source file...")

    _import_flat_file(source_path, temp_db_path)

    if progress_callback:
        progress_callback("Merging new records...")

    with get_connection(temp_db_path) as temp_conn:
        temp_lbs = {r[0] for r in temp_conn.execute("SELECT DISTINCT lb_number FROM checksums").fetchall()}
        new_lbs = temp_lbs - before_lbs

        if not temp_lbs:
            temp_db_path.unlink(missing_ok=True)
            return {"error": "No checksums found in file. Check the file format."}

        with get_connection(db_path) as main_conn:
            rows = temp_conn.execute("SELECT checksum, filename, chk_type, lb_number, xref FROM checksums").fetchall()
            main_conn.executemany(
                "INSERT OR IGNORE INTO checksums(checksum, filename, chk_type, lb_number, xref) VALUES(?,?,?,?,?)",
                [(r["checksum"], r["filename"], r["chk_type"], r["lb_number"], r["xref"]) for r in rows]
            )

    temp_db_path.unlink(missing_ok=True)

    now = datetime.utcnow().isoformat()
    with get_connection(db_path) as conn:
        after_max = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0
        total_lbs = conn.execute("SELECT COUNT(DISTINCT lb_number) FROM checksums").fetchone()[0]

    set_meta("last_import_date", now, db_path)
    set_meta("last_lb_number", str(after_max), db_path)
    set_meta("import_hash", file_hash, db_path)

    if progress_callback:
        progress_callback(f"Import complete. {len(new_lbs)} new LB numbers.")

    return {
        "new_lb_count": len(new_lbs),
        "total_lb_count": total_lbs,
        "new_lb_numbers": sorted(new_lbs),
        "scrape_queued": len(new_lbs) > 0,
    }
