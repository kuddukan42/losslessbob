import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "losslessbob.db"

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
"""

_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_SHA1_RE = re.compile(r'^([0-9a-fA-F]{40})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)


def get_connection(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
        if "status" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN status TEXT DEFAULT 'ok'")


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

    checksums = [e[0] for e in parsed_entries]
    chk_map = {e[0]: e for e in parsed_entries}

    with get_connection(db_path) as conn:
        placeholders = ','.join('?' * len(checksums))
        rows = conn.execute(
            f"SELECT checksum, filename, chk_type, lb_number, xref FROM checksums WHERE checksum IN ({placeholders})",
            checksums
        ).fetchall()

    matched_chks = {}
    for row in rows:
        chk = row["checksum"]
        if chk not in matched_chks:
            matched_chks[chk] = []
        matched_chks[chk].append(dict(row))

    detail = []
    lb_to_given = {}
    lb_to_matched = {}

    for chk, fname, chk_type in parsed_entries:
        if chk in matched_chks:
            matches = matched_chks[chk]
            is_duplicate = len(matches) > 1
            for m in matches:
                lb = m["lb_number"]
                lb_to_given.setdefault(lb, set()).add(chk)
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

    # Reverse lookup: find checksums in DB for matched LBs that weren't in input
    with get_connection(db_path) as conn:
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


def insert_missing_entry(lb_number, db_path=None):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO entries(lb_number, date_str, location, cdr, rating, timing, description, setlist, status)
               VALUES(?, '', '', '', '', '', '', '', 'missing')""",
            (lb_number,)
        )


def search_entries(query, field="all", year=None, limit=100, db_path=None):
    conditions = []
    params = []

    if year is not None:
        short = str(year)[-2:]
        long_ = str(year)
        conditions.append("(date_str LIKE ? OR date_str LIKE ?)")
        params.extend([f"%/{short}", f"%/{long_}"])

    if query:
        like = f"%{query}%"
        if field == "location":
            conditions.append("location LIKE ?")
            params.append(like)
        elif field == "date":
            conditions.append("date_str LIKE ?")
            params.append(like)
        elif field == "description":
            conditions.append("description LIKE ?")
            params.append(like)
        else:
            conditions.append(
                "(CAST(lb_number AS TEXT) LIKE ? OR location LIKE ? OR date_str LIKE ?"
                " OR description LIKE ? OR status LIKE ?)"
            )
            params.extend([like, like, like, like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (
        f"SELECT lb_number, date_str, location, rating, description, status "
        f"FROM entries {where} ORDER BY lb_number LIMIT ?"
    )
    params.append(limit)
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
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
