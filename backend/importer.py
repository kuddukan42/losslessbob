import hashlib
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from backend.db import (
    DB_PATH,
    close_connection,
    get_connection,
    get_meta,
    init_db,
    migrate_lb_master,
    rebuild_bloom,
    reconcile_lb_status,
    set_meta,
)
from backend.db_queue import get_write_queue
from backend.paths import DATA_DIR

# --- Shared import progress state (mirrors _scrape_state pattern) ---
_import_state: dict = {
    "running": False,
    "stage": "idle",      # idle | hashing | parsing | merging | optimizing | done | error
    "rows_parsed": 0,
    "rows_total": 0,      # set after parsing completes; used for merge progress bar
    "rows_merged": 0,
    "new_lb_count": 0,
    "message": "",
    "error": None,
}
_import_lock = threading.Lock()


def get_import_status() -> dict:
    """Return a snapshot of the current import progress state."""
    with _import_lock:
        return dict(_import_state)


def _set_state(**kwargs) -> None:
    with _import_lock:
        _import_state.update(kwargs)


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_flat_file(flat_path, temp_db_path):
    """Parse tab-delimited flat file into temporary SQLite database.

    Uses a raw sqlite3 connection (not init_db) so no background threads are
    spawned against the temp file.  On Windows, background threads keep the
    file locked, making unlink() fail after the import completes.
    """
    # Only the checksums table is needed in the temp DB.
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS checksums"
        "(checksum TEXT, filename TEXT, chk_type TEXT, lb_number INTEGER, xref INTEGER)"
    )
    inserted = 0
    with open(flat_path, encoding="utf-8", errors="replace") as f:
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
                if inserted % 10_000 == 0:
                    _set_state(rows_parsed=inserted, message=f"Parsing flat file — {inserted:,} rows read")
            except Exception:
                pass
    conn.commit()
    conn.close()
    _set_state(rows_parsed=inserted, rows_total=inserted,
               message=f"Parsed {inserted:,} rows")
    return inserted


def run_import(source_path, progress_callback=None, db_path=None):
    """
    Import a flat file into the main database.
    Returns dict with new_lb_count, total_lb_count, new_lb_numbers.
    Updates _import_state throughout so callers can poll get_import_status().
    """
    source_path = Path(source_path)
    db_path = db_path or DB_PATH

    _set_state(running=True, stage="hashing", rows_parsed=0, rows_total=0,
               rows_merged=0, new_lb_count=0, message="Checking file hash…", error=None)

    if progress_callback:
        progress_callback("Checking file hash...")

    file_hash = md5_file(source_path)
    stored_hash = get_meta("import_hash", db_path)
    if file_hash == stored_hash:
        _set_state(running=False, stage="done", message="Already imported (no changes).")
        return {"skipped": True, "reason": "Already imported (same hash)"}

    init_db(db_path)

    with get_connection(db_path) as conn:
        before_lbs = {r[0] for r in conn.execute("SELECT DISTINCT lb_number FROM checksums").fetchall()}

    temp_db_path = DATA_DIR / "temp_import.db"
    if temp_db_path.exists():
        temp_db_path.unlink()

    _set_state(stage="parsing", message="Parsing flat file…")
    if progress_callback:
        progress_callback("Parsing source file...")

    _import_flat_file(source_path, temp_db_path)

    _set_state(stage="merging", message="Merging into database…")
    if progress_callback:
        progress_callback("Merging new records...")

    with get_connection(temp_db_path) as temp_conn:
        temp_lbs = {r[0] for r in temp_conn.execute("SELECT DISTINCT lb_number FROM checksums").fetchall()}
        new_lbs = temp_lbs - before_lbs
        rows = (
            temp_conn.execute(
                "SELECT checksum, filename, chk_type, lb_number, xref FROM checksums"
            ).fetchall()
            if temp_lbs else []
        )

    # Close and delete the temp DB outside the with-block so its __exit__ (commit)
    # runs on an open connection regardless of the early-exit path below.
    close_connection(temp_db_path)
    temp_db_path.unlink(missing_ok=True)

    if not temp_lbs:
        _set_state(running=False, stage="error", error="No checksums found in file.")
        return {"error": "No checksums found in file. Check the file format."}

    # Batch merge with row-count progress updates
    CHUNK = 10_000
    total_rows = len(rows)
    _set_state(rows_total=total_rows)
    _all_rows, _total, _chsz = rows, total_rows, CHUNK

    def _do_merge(conn) -> None:
        for i in range(0, _total, _chsz):
            chunk = _all_rows[i:i + _chsz]
            conn.executemany(
                "INSERT OR IGNORE INTO checksums"
                "(checksum, filename, chk_type, lb_number, xref) VALUES(?,?,?,?,?)",
                [(r["checksum"], r["filename"], r["chk_type"], r["lb_number"], r["xref"])
                 for r in chunk],
            )
            _set_state(rows_merged=i + len(chunk),
                       message=f"Merging — {i + len(chunk):,} / {_total:,} rows")

    get_write_queue().execute(_do_merge, timeout=300.0)

    _set_state(stage="optimizing", message="Updating statistics…")
    if progress_callback:
        progress_callback(f"Import complete. {len(new_lbs)} new LB numbers.")

    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        after_max = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0
        total_lbs = conn.execute("SELECT COUNT(DISTINCT lb_number) FROM checksums").fetchone()[0]

    set_meta("last_import_date", now, db_path)
    set_meta("last_lb_number", str(after_max), db_path)
    set_meta("import_hash", file_hash, db_path)

    # Update query planner statistics after bulk insert
    with get_connection(db_path) as conn:
        conn.execute("PRAGMA optimize")

    rebuild_bloom(db_path)

    # Populate or extend lb_master for all LBs touched by this import.
    # migrate_lb_master() is a no-op when lb_master is already populated (idempotent guard),
    # so for subsequent imports we reconcile only the LBs from this file.
    _set_state(stage="optimizing", message="Updating integrity status…")
    lb_master_count = 0
    with get_connection(db_path) as _c:
        lb_master_count = _c.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]

    if lb_master_count == 0:
        migrate_lb_master(db_path)
    else:
        for lb in sorted(temp_lbs):
            reconcile_lb_status(lb, trigger="import", db_path=db_path)

    _set_state(running=False, stage="done", new_lb_count=len(new_lbs),
               message=f"Done — {len(new_lbs):,} new LB entries added.")

    return {
        "new_lb_count": len(new_lbs),
        "total_lb_count": total_lbs,
        "new_lb_numbers": sorted(new_lbs),
        "scrape_queued": len(new_lbs) > 0,
    }


def start_import_async(source_path, db_path=None, on_complete=None) -> None:
    """
    Launch run_import() in a daemon thread. Returns immediately.
    on_complete(result_dict) is called from the import thread when done.
    """
    def _run():
        try:
            result = run_import(source_path, db_path=db_path)
        except Exception as e:
            result = {"error": str(e)}
            _set_state(running=False, stage="error", error=str(e), message=str(e))
        if on_complete:
            on_complete(result)

    threading.Thread(target=_run, daemon=True).start()
