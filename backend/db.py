import re
import sqlite3
import threading
from pathlib import Path

from pybloom_live import ScalableBloomFilter as _SBF

from backend.paths import DB_PATH  # noqa: F401  — re-exported for callers
from backend.paths import to_long_path

# --- Thread-local persistent connection pool (DB-02) ---
_local = threading.local()

# --- Bloom filter for fast NOT-FOUND short-circuit (DB-07) ---
_bloom: _SBF | None = None
_bloom_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checksums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checksum TEXT NOT NULL,
    filename TEXT NOT NULL,
    chk_type TEXT NOT NULL,
    lb_number INTEGER NOT NULL,
    xref INTEGER DEFAULT 0,
    UNIQUE(checksum, lb_number)
);
CREATE INDEX IF NOT EXISTS idx_checksum ON checksums(checksum);
CREATE INDEX IF NOT EXISTS idx_lb_number ON checksums(lb_number);
CREATE INDEX IF NOT EXISTS idx_chk_covering
    ON checksums(checksum, lb_number, chk_type, filename, xref);
CREATE INDEX IF NOT EXISTS idx_lb_xref0
    ON checksums(lb_number, checksum) WHERE xref=0;

CREATE TABLE IF NOT EXISTS entries (
    lb_number INTEGER PRIMARY KEY,
    date_str TEXT,
    location TEXT,
    cdr TEXT,
    rating TEXT,
    timing TEXT,
    description TEXT,
    setlist TEXT,
    status TEXT DEFAULT 'ok',
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entry_files (
    lb_number INTEGER NOT NULL,
    filename TEXT NOT NULL,
    clean_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    downloaded INTEGER DEFAULT 0,
    PRIMARY KEY (lb_number, filename)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS my_collection (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL UNIQUE,
    folder_name  TEXT NOT NULL,
    disk_path    TEXT NOT NULL,
    confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes        TEXT,
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);

CREATE TABLE IF NOT EXISTS entry_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL,
    field      TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_changes_lb ON entry_changes(lb_number, changed_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    description,
    setlist,
    location,
    date_str,
    content='entries',
    content_rowid='lb_number',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS entries_fts_insert
AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, description, setlist, location, date_str)
    VALUES (new.lb_number, new.description, new.setlist, new.location, new.date_str);
END;

CREATE TRIGGER IF NOT EXISTS entries_fts_update
AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, description, setlist, location, date_str)
    VALUES ('delete', old.lb_number, old.description, old.setlist, old.location, old.date_str);
    INSERT INTO entries_fts(rowid, description, setlist, location, date_str)
    VALUES (new.lb_number, new.description, new.setlist, new.location, new.date_str);
END;

CREATE TRIGGER IF NOT EXISTS entries_fts_delete
AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, description, setlist, location, date_str)
    VALUES ('delete', old.lb_number, old.description, old.setlist, old.location, old.date_str);
END;
"""

_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_SHA1_RE = re.compile(r'^([0-9a-fA-F]{40})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)

TRACKED_ENTRY_FIELDS = ("date_str", "location", "cdr", "rating", "timing",
                        "description", "setlist", "status")


def get_connection(db_path=None):
    """Return a persistent per-thread SQLite connection with WAL and performance PRAGMAs."""
    path = str(to_long_path(Path(db_path or DB_PATH)))
    cache = getattr(_local, "connections", None)
    if cache is None:
        _local.connections = {}
        cache = _local.connections
    if path not in cache:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-65536")
        conn.execute("PRAGMA mmap_size=536870912")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        cache[path] = conn
    return cache[path]


def rebuild_bloom(db_path=None):
    """Load all checksums into an in-process bloom filter. Call after import/init."""
    global _bloom
    bf = _SBF(mode=_SBF.LARGE_SET_GROWTH, error_rate=0.01)
    conn = get_connection(db_path)
    for row in conn.execute("SELECT checksum FROM checksums"):
        bf.add(row[0])
    with _bloom_lock:
        _bloom = bf


def _rebuild_bloom_bg(db_path=None) -> None:
    try:
        rebuild_bloom(db_path)
    except Exception:
        pass  # Non-fatal; lookups fall through to SQLite until filter is ready


def checksum_in_bloom(chk: str) -> bool:
    """Returns False only if chk is DEFINITELY not in DB. True means possible match."""
    with _bloom_lock:
        if _bloom is None:
            return True
        return chk in _bloom


def init_db(db_path=None):
    """Create schema, run migrations, rebuild FTS index if needed, seed bloom filter."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
    if "status" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN status TEXT DEFAULT 'ok'")
        conn.commit()

    # Populate FTS index if empty (first run after adding FTS)
    fts_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if fts_count == 0 and entry_count > 0:
        conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        conn.commit()

    # Build bloom filter in background so startup is not blocked.
    # checksum_in_bloom() returns True while _bloom is None, so all lookups
    # fall through to SQLite until the filter is ready.
    threading.Thread(target=_rebuild_bloom_bg, args=(db_path,), daemon=True).start()


def get_meta(key, db_path=None):
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key, value, db_path=None):
    with get_connection(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))


def get_stats(db_path=None):
    with get_connection(db_path) as conn:
        total_checksums = conn.execute("SELECT COUNT(*) FROM checksums").fetchone()[0]
        total_lb = conn.execute("SELECT COUNT(DISTINCT lb_number) FROM checksums").fetchone()[0]
        latest_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0]
        last_import = get_meta("last_import_date", db_path)
    return {
        "total_checksums": total_checksums,
        "total_lb_numbers": total_lb,
        "latest_lb": latest_lb,
        "last_import": last_import,
    }


def parse_checksum_text(text):
    """Parse FFP, MD5, or ST5 checksum text into list of (checksum, filename, type) tuples."""
    results = {}
    for raw_line in re.split(r'\r?\n', text):
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith(';'):
            continue

        # FFP: filename.flac:checksum
        ffp = _FFP_RE.match(line)
        if ffp:
            fname, chk = ffp.group(1), ffp.group(2).lower()
            ext = Path(fname).suffix.lower()
            chk_type = 'f' if ext == '.flac' else 'm'
            if chk not in results:
                results[chk] = (chk, fname, chk_type)
            continue

        # SHA1 (40 hex chars)
        sha1 = _SHA1_RE.match(line)
        if sha1:
            chk, fname = sha1.group(1).lower(), sha1.group(2).strip()
            ext = Path(fname).suffix.lower()
            chk_type = 's' if ext == '.shn' else 'm'
            if chk not in results:
                results[chk] = (chk, fname, chk_type)
            continue

        # MD5/ST5: checksum *filename or checksum filename
        md5 = _MD5_RE.match(line)
        if md5:
            chk, fname = md5.group(1).lower(), md5.group(2).strip()
            ext = Path(fname).suffix.lower()
            chk_type = 's' if ext == '.shn' else 'm'
            if chk not in results:
                results[chk] = (chk, fname, chk_type)

    return list(results.values())


def lookup_checksums(parsed_entries, db_path=None):
    """
    Look up a list of (checksum, filename, type) tuples against the DB.
    Returns (summary_dict, detail_list).
    """
    if not parsed_entries:
        return {}, []

    # Bloom pre-filter: separate definite misses from candidates (DB-07)
    candidates = [e for e in parsed_entries if checksum_in_bloom(e[0])]
    definite_misses = [e for e in parsed_entries if not checksum_in_bloom(e[0])]
    checksums = [e[0] for e in candidates]

    # Temp-table bulk lookup — avoids dynamic IN clause and the 999-param limit (DB-04)
    conn = get_connection(db_path)
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _lookup_input (checksum TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _lookup_input")
    if checksums:
        conn.executemany(
            "INSERT OR IGNORE INTO _lookup_input(checksum) VALUES(?)",
            [(c,) for c in checksums]
        )
    rows = conn.execute("""
        SELECT c.checksum, c.filename, c.chk_type, c.lb_number, c.xref
        FROM checksums c
        JOIN _lookup_input t ON t.checksum = c.checksum
    """).fetchall()
    conn.commit()

    matched_chks: dict = {}
    for row in rows:
        chk = row["checksum"]
        if chk not in matched_chks:
            matched_chks[chk] = []
        matched_chks[chk].append(dict(row))

    detail = []
    lb_to_matched: dict = {}

    for chk, fname, chk_type in candidates:
        if chk in matched_chks:
            matches = matched_chks[chk]
            is_duplicate = len(matches) > 1
            for m in matches:
                lb = m["lb_number"]
                lb_to_matched.setdefault(lb, set()).add(chk)
                status = "DUPLICATE" if is_duplicate else "MATCHED"
                detail.append({
                    "checksum": chk,
                    "filename": fname,
                    "type": chk_type,
                    "lb_number": lb,
                    "xref": m["xref"],
                    "status": status,
                    "is_duplicate": is_duplicate,
                    "missing_from_set": [],
                    "detail_url": f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb}.html",
                })
        else:
            detail.append({
                "checksum": chk,
                "filename": fname,
                "type": chk_type,
                "lb_number": None,
                "xref": 0,
                "status": "NOT FOUND",
                "is_duplicate": False,
                "missing_from_set": [],
                "detail_url": None,
            })

    # Append bloom-filtered definite misses as NOT FOUND without querying SQLite
    for chk, fname, chk_type in definite_misses:
        detail.append({
            "checksum": chk, "filename": fname, "type": chk_type,
            "lb_number": None, "xref": 0, "status": "NOT FOUND",
            "is_duplicate": False, "missing_from_set": [], "detail_url": None,
        })

    # Reverse lookup: find checksums in DB for matched LBs that weren't in input
    # Uses idx_lb_xref0 partial index (DB-03)
    for lb, matched_set in lb_to_matched.items():
        all_chks = conn.execute(
            "SELECT checksum FROM checksums WHERE lb_number=? AND xref=0",
            (lb,)
        ).fetchall()
        all_chks_set = {r["checksum"] for r in all_chks}
        missing = all_chks_set - matched_set
        for item in detail:
            if item["lb_number"] == lb:
                item["missing_from_set"] = list(missing)
                if missing and item["status"] == "MATCHED":
                    item["status"] = "MATCHED (INCOMPLETE)"

    # Build summary per LB
    lb_summary = {}
    unmatched_count = 0
    for item in detail:
        lb = item["lb_number"]
        if lb is None:
            unmatched_count += 1
            continue
        if lb not in lb_summary:
            lb_summary[lb] = {
                "lb_number": lb,
                "given": 0,
                "matched": 0,
                "not_found": 0,
                "missing_from_set": len(item["missing_from_set"]),
                "duplicates": 0,
                "xrefs": 0,
                "status": "MATCHED",
                "detail_url": item["detail_url"],
            }
        s = lb_summary[lb]
        s["given"] += 1
        if item["status"] in ("MATCHED", "MATCHED (INCOMPLETE)"):
            s["matched"] += 1
        if item["is_duplicate"]:
            s["duplicates"] += 1
        if item["xref"]:
            s["xrefs"] += 1
        if item["missing_from_set"]:
            s["status"] = "INCOMPLETE"

    summary = {
        "given": len(parsed_entries),
        "matched": sum(1 for d in detail if d["lb_number"] is not None),
        "unmatched": unmatched_count,
        "missing_from_db": unmatched_count,
        "lb_numbers_found": list(lb_summary.keys()),
        "lb_summary": list(lb_summary.values()),
    }

    return summary, detail


def record_entry_changes(lb_number: int, new_data: dict, db_path=None) -> list:
    """
    Compare new_data against the current entries row.
    Insert a row into entry_changes for each field that differs.
    Returns list of changed field names.
    """
    conn = get_connection(db_path)
    existing = conn.execute(
        "SELECT * FROM entries WHERE lb_number=?", (lb_number,)
    ).fetchone()
    if not existing:
        return []
    changed = []
    rows_to_insert = []
    for field in TRACKED_ENTRY_FIELDS:
        old = existing[field] if field in existing.keys() else None
        new = new_data.get(field)
        if old != new and not (old is None and new is None):
            rows_to_insert.append((lb_number, field, old, new))
            changed.append(field)
    if rows_to_insert:
        conn.executemany(
            "INSERT INTO entry_changes(lb_number, field, old_value, new_value) VALUES(?,?,?,?)",
            rows_to_insert
        )
        conn.commit()
    return changed


def insert_missing_entry(lb_number, db_path=None):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO entries(lb_number, date_str, location, cdr, rating, timing, description, setlist, status)
               VALUES(?, '', '', '', '', '', '', '', 'missing')""",
            (lb_number,)
        )


def search_entries(query, field="all", year=None, limit=None, db_path=None):
    """Search entries using FTS5 when a query is present, falling back to LIKE on FTS syntax errors."""
    conn = get_connection(db_path)

    year_clause = ""
    year_params: list = []
    if year is not None:
        short = str(year)[-2:]
        long_ = str(year)
        year_clause = "AND (e.date_str LIKE ? OR e.date_str LIKE ?)"
        year_params = [f"%/{short}", f"%/{long_}"]

    if query:
        if field == "location":
            fts_query = f"location:{query}"
        elif field == "date":
            fts_query = f"date_str:{query}"
        else:
            fts_query = query

        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status
            FROM entries_fts
            JOIN entries e ON e.lb_number = entries_fts.rowid
            WHERE entries_fts MATCH ?
            {year_clause}
            ORDER BY rank
            {limit_clause}
        """
        params: list = [fts_query] + year_params
    else:
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT lb_number, date_str, location, rating, description, status
            FROM entries
            WHERE 1=1 {year_clause.replace('e.', '')}
            ORDER BY lb_number
            {limit_clause}
        """
        params = year_params

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # FTS5 syntax error fallback — revert to LIKE
        like = f"%{query}%"
        fallback_sql = (
            "SELECT lb_number, date_str, location, rating, description, status "
            "FROM entries WHERE description LIKE ? OR location LIKE ? OR date_str LIKE ? "
            "ORDER BY lb_number"
        )
        fallback_params = [like, like, like]
        if limit is not None:
            fallback_sql += " LIMIT ?"
            fallback_params.append(int(limit))
        rows = conn.execute(fallback_sql, fallback_params).fetchall()

    return [dict(r) for r in rows]


def get_entry(lb_number, db_path=None):
    with get_connection(db_path) as conn:
        entry = conn.execute("SELECT * FROM entries WHERE lb_number=?", (lb_number,)).fetchone()
        checksums = conn.execute("SELECT * FROM checksums WHERE lb_number=?", (lb_number,)).fetchall()
        files = conn.execute("SELECT * FROM entry_files WHERE lb_number=?", (lb_number,)).fetchall()
    if not entry:
        return None
    return {
        "entry": dict(entry),
        "checksums": [dict(r) for r in checksums],
        "files": [dict(r) for r in files],
    }


def get_entries_by_year(year, db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT lb_number, date_str, location, rating FROM entries WHERE date_str LIKE ? ORDER BY lb_number",
            (f"%/{str(year)[-2:]}",)
        ).fetchall()
    return [dict(r) for r in rows]


def get_distinct_years(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date_str FROM entries WHERE date_str IS NOT NULL AND date_str != ''"
        ).fetchall()
    years = set()
    for row in rows:
        parts = str(row[0]).split('/')
        if len(parts) >= 3:
            try:
                y = int(parts[-1].strip())
                if y < 100:
                    y = 1900 + y if y >= 49 else 2000 + y
                years.add(y)
            except ValueError:
                pass
    return sorted(years, reverse=True)


def get_collection(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT c.id, c.lb_number, c.folder_name, c.disk_path, c.confirmed_at, c.notes,
                   e.date_str, e.location
            FROM my_collection c
            LEFT JOIN entries e ON c.lb_number = e.lb_number
            ORDER BY c.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def add_to_collection(lb_number, folder_name, disk_path, notes=None, db_path=None):
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO my_collection(lb_number, folder_name, disk_path, notes) VALUES(?,?,?,?)",
            (lb_number, folder_name, disk_path, notes)
        )
        return conn.execute("SELECT changes()").fetchone()[0]


def update_collection(lb_number, fields, db_path=None):
    allowed = {"folder_name", "disk_path", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE my_collection SET {set_clause} WHERE lb_number=?",
            list(updates.values()) + [lb_number]
        )


def delete_from_collection(lb_number, db_path=None):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM my_collection WHERE lb_number=?", (lb_number,))


def get_missing_from_collection(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT e.lb_number, e.date_str, e.location, e.rating, e.description
            FROM entries e
            LEFT JOIN my_collection c ON e.lb_number = c.lb_number
            WHERE c.lb_number IS NULL AND e.status = 'ok'
            ORDER BY e.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def search_collection(query, db_path=None):
    like = f"%{query}%"
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT c.id, c.lb_number, c.folder_name, c.disk_path, c.confirmed_at, c.notes,
                   e.date_str, e.location
            FROM my_collection c
            LEFT JOIN entries e ON c.lb_number = e.lb_number
            WHERE c.folder_name LIKE ? OR c.disk_path LIKE ? OR CAST(c.lb_number AS TEXT) LIKE ?
            ORDER BY c.lb_number
        """, (like, like, like)).fetchall()
    return [dict(r) for r in rows]


def get_owned_lb_numbers(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT lb_number FROM my_collection").fetchall()
    return [r[0] for r in rows]
