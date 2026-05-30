# LosslessBob — Claude Code Implementation Instructions

**Project root assumed throughout:** `losslessbob/`  
**Read `PROJECT.md` before starting any task for schema/architecture context.**  
**Complete DB-layer tasks (DB-01 through DB-06) before any feature tasks that touch `db.py`.**

---

## CATEGORY: DATABASE PERFORMANCE ## COMPLETE

---

### DB-01: WAL Mode + Performance PRAGMAs ## COMPLETE

**Files:** `backend/db.py`  
**Dependencies:** None  
**New packages:** None

**Steps:**

1. Replace the entire `get_connection()` function:

```python
def get_connection(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")
    conn.execute("PRAGMA mmap_size=536870912")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

2. No other changes needed. The `with get_connection(...) as conn:` context manager pattern still works — `sqlite3.Connection` used as a context manager commits on `__exit__` without closing.

**Done when:** App starts, `PRAGMA journal_mode` returns `wal` when queried on the DB.

---

### DB-02: Persistent Per-Thread Connection Pool ## COMPLETE

**Files:** `backend/db.py`  
**Dependencies:** DB-01 must be complete  
**New packages:** None

**Goal:** Eliminate repeated `sqlite3.connect()` / close overhead. Each Flask thread keeps one open connection for its lifetime.

**Steps:**

1. Add at the top of `db.py` after existing imports:

```python
import threading
_local = threading.local()
```

2. Replace `get_connection()` (already modified in DB-01) with:

```python
def get_connection(db_path=None):
    path = str(db_path or DB_PATH)
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
        cache[path] = conn
    return cache[path]
```

3. All callers that use `with get_connection(...) as conn:` must be updated. The `with` form on a persistent connection commits/rolls back but does NOT close it — this is acceptable behavior. Verify no caller calls `conn.close()` explicitly; remove any that do.

4. In `backend/importer.py`: the `_import_flat_file` function calls `conn.close()` explicitly. Remove that line. Add `conn.commit()` before where `conn.close()` was.

**Done when:** App runs 20+ lookup requests without "database is locked" errors and without growing file descriptor count.

---

### DB-03: Covering Index + Partial Index on `checksums` ## COMPLETE

**Files:** `backend/db.py`  
**Dependencies:** None (additive schema change)  
**New packages:** None

**Steps:**

1. In `SCHEMA_SQL`, after the existing index lines (`CREATE INDEX IF NOT EXISTS idx_lb_number ...`), add:

```sql
CREATE INDEX IF NOT EXISTS idx_chk_covering
ON checksums(checksum, lb_number, chk_type, filename, xref);

CREATE INDEX IF NOT EXISTS idx_lb_xref0
ON checksums(lb_number, checksum) WHERE xref=0;
```

2. The existing `idx_checksum ON checksums(checksum)` is now redundant (covered by `idx_chk_covering`). Leave it in place — SQLite will prefer the covering index for the lookup query automatically, and removing it would require a migration.

3. After adding indexes to `SCHEMA_SQL`, run `init_db()` once against any existing DB:

```bash
python -c "from backend.db import init_db; init_db()"
```

This executes `CREATE INDEX IF NOT EXISTS` which is a no-op if the index already exists.

**Done when:** `EXPLAIN QUERY PLAN SELECT checksum, filename, chk_type, lb_number, xref FROM checksums WHERE checksum = 'abc'` shows `USING INDEX idx_chk_covering` (not a table scan).

---

### DB-04: Temp Table Bulk Lookup (Replace `IN` Clause) ## COMPLETE

**Files:** `backend/db.py`  
**Dependencies:** DB-02 (persistent connection required for temp tables to persist within a call)  
**New packages:** None

**Goal:** Replace the dynamically-sized `WHERE checksum IN (?,?,...)` in `lookup_checksums()` with a static-statement JOIN against a temp table. Fixes the SQLite 999-parameter limit and eliminates per-call statement recompilation.

**Steps:**

1. In `lookup_checksums()`, replace this block:

```python
    with get_connection(db_path) as conn:
        placeholders = ','.join('?' * len(checksums))
        rows = conn.execute(
            f"SELECT checksum, filename, chk_type, lb_number, xref FROM checksums WHERE checksum IN ({placeholders})",
            checksums
        ).fetchall()
```

With:

```python
    conn = get_connection(db_path)
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _lookup_input (checksum TEXT PRIMARY KEY)"
    )
    conn.execute("DELETE FROM _lookup_input")
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
```

2. Also replace the reverse-lookup block inside the `for lb, matched_set in lb_to_matched.items():` loop:

```python
    conn = get_connection(db_path)
    for lb, matched_set in lb_to_matched.items():
        all_chks = conn.execute(
            "SELECT checksum FROM checksums WHERE lb_number=? AND xref=0",
            (lb,)
        ).fetchall()
```

(No change needed here — this query already uses `idx_lb_xref0` added in DB-03.)

3. Remove the second `with get_connection(db_path) as conn:` context block that wraps the reverse lookup loop. Use the persistent `conn` reference obtained above.

**Done when:** `lookup_checksums()` works correctly with 1000+ input checksums without `sqlite3.OperationalError: too many SQL variables`.

---

### DB-05: FTS5 Full-Text Search ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`  
**Dependencies:** DB-01  
**New packages:** None (FTS5 is bundled in Python's `sqlite3`)

**Steps:**

1. In `SCHEMA_SQL` in `db.py`, append after the existing table/index definitions:

```sql
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
```

2. In `init_db()`, after `conn.executescript(SCHEMA_SQL)`, add a one-time FTS rebuild for existing data:

```python
    # Populate FTS index if empty (first run after adding FTS)
    fts_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if fts_count == 0 and entry_count > 0:
        conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        conn.commit()
```

3. Rewrite `search_entries()` in `db.py`. Replace the entire function body with:

```python
def search_entries(query, field="all", year=None, limit=None, db_path=None):
    conn = get_connection(db_path)
    conditions = []
    params = []

    # Year filter always uses the entries table directly
    year_clause = ""
    year_params = []
    if year is not None:
        short = str(year)[-2:]
        long_ = str(year)
        year_clause = "AND (e.date_str LIKE ? OR e.date_str LIKE ?)"
        year_params = [f"%/{short}", f"%/{long_}"]

    limit_val = limit or 100

    if query:
        # FTS path
        if field in ("all", "description"):
            fts_query = query  # FTS5 MATCH syntax; user can use AND/OR/NOT
        elif field == "location":
            fts_query = f"location:{query}"
        elif field == "date":
            fts_query = f"date_str:{query}"
        else:
            fts_query = query

        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status
            FROM entries_fts
            JOIN entries e ON e.lb_number = entries_fts.rowid
            WHERE entries_fts MATCH ?
            {year_clause}
            ORDER BY rank
            LIMIT ?
        """
        params = [fts_query] + year_params + [limit_val]
    else:
        # No text query — just year filter or return all
        sql = f"""
            SELECT lb_number, date_str, location, rating, description, status
            FROM entries
            WHERE 1=1 {year_clause.replace('e.', '')}
            ORDER BY lb_number
            LIMIT ?
        """
        params = year_params + [limit_val]

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # FTS5 syntax error fallback — revert to LIKE
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT lb_number, date_str, location, rating, description, status "
            "FROM entries WHERE description LIKE ? OR location LIKE ? OR date_str LIKE ? "
            "ORDER BY lb_number LIMIT ?",
            [like, like, like, limit_val]
        ).fetchall()

    return [dict(r) for r in rows]
```

4. In `backend/app.py`, the `/api/search` route passes `field` and `year` to `search_entries()` — no change needed there.

**Done when:** `GET /api/search?q=forest+hills` returns results ordered by relevance, faster than the previous LIKE-based implementation. FTS syntax like `q=electric+AND+1966` works.

---

### DB-06: `PRAGMA optimize` After Import and Scrape ## COMPLETE

**Files:** `backend/importer.py`, `backend/scraper.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. In `backend/importer.py`, in `run_import()`, after the line `set_meta("import_hash", file_hash, db_path)`, add:

```python
    # Update query planner statistics after bulk insert
    with get_connection(db_path) as conn:
        conn.execute("PRAGMA optimize")
```

2. In `backend/scraper.py`, in `scrape_range()`, at the very end after `_scrape_state.update({"running": False, ...})`, add:

```python
    from backend.db import get_connection as _gc, DB_PATH as _dbp
    conn = _gc(db_path)
    conn.execute("PRAGMA optimize")
    conn.commit()
```

**Done when:** No observable change in behavior; query plans stay accurate after large imports.

---

### DB-07: Bloom Filter Pre-Check for Lookups ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`, `requirements.txt`  
**Dependencies:** DB-02  
**New packages:** `pybloom-live`

**Steps:**

1. Add to `requirements.txt`:
```
pybloom-live==4.0.0
```

2. In `backend/db.py`, add after imports:

```python
from pybloom_live import ScalableBloomFilter as _SBF

_bloom: _SBF | None = None
_bloom_lock = threading.Lock()


def rebuild_bloom(db_path=None):
    """Load all checksums into an in-process bloom filter. Call after import/init."""
    global _bloom
    bf = _SBF(mode=_SBF.LARGE_SET_GROWTH, error_rate=0.01)
    conn = get_connection(db_path)
    for row in conn.execute("SELECT checksum FROM checksums"):
        bf.add(row[0])
    with _bloom_lock:
        _bloom = bf


def checksum_in_bloom(chk: str) -> bool:
    """Returns False only if chk is DEFINITELY not in DB. True = possible match."""
    with _bloom_lock:
        if _bloom is None:
            return True  # Not initialized — allow through
        return chk in _bloom
```

3. In `init_db()` in `db.py`, at the end of the function, add:

```python
    # Build bloom filter on startup (non-blocking; runs in calling thread)
    try:
        rebuild_bloom(db_path)
    except Exception:
        pass  # Non-fatal; lookups fall through to SQLite
```

4. In `lookup_checksums()` in `db.py`, add pre-filtering before the temp-table insert. After `checksums = [e[0] for e in parsed_entries]`, insert:

```python
    # Bloom pre-filter: separate definite misses from candidates
    candidates = [e for e in parsed_entries if checksum_in_bloom(e[0])]
    definite_misses = [e for e in parsed_entries if not checksum_in_bloom(e[0])]
    # Only query SQLite for candidates
    checksums = [e[0] for e in candidates]
```

Then at the point where NOT FOUND entries are appended to `detail`, also append `definite_misses` as NOT FOUND:

```python
    for chk, fname, chk_type in definite_misses:
        detail.append({
            "checksum": chk, "filename": fname, "type": chk_type,
            "lb_number": None, "xref": 0, "status": "NOT FOUND",
            "is_duplicate": False, "missing_from_set": [], "detail_url": None,
        })
```

5. In `backend/importer.py`, at the end of `run_import()` after `PRAGMA optimize`, add:

```python
    from backend.db import rebuild_bloom
    rebuild_bloom(db_path)
```

**Done when:** `checksum_in_bloom("0000000000000000000000000000000a")` returns `False` for a hash not in the DB. Lookup of 200 non-existent checksums generates zero SQLite queries (verify with `conn.set_trace_callback(print)`).

---

### DB-08: Metadata Changelog (Scrape Diff) ## COMPLETE

**Files:** `backend/db.py`, `backend/scraper.py`, `backend/app.py`  
**Dependencies:** DB-01  
**New packages:** None

**Goal:** Before overwriting an `entries` row on re-scrape, record field-level deltas in a new `entry_changes` table.

**Steps:**

1. Add to `SCHEMA_SQL` in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS entry_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL,
    field      TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_changes_lb ON entry_changes(lb_number, changed_at DESC);
```

2. Add a new function to `db.py`:

```python
TRACKED_ENTRY_FIELDS = ("date_str", "location", "cdr", "rating", "timing",
                         "description", "setlist", "status")

def record_entry_changes(lb_number, new_data: dict, db_path=None):
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
```

3. In `backend/scraper.py`, locate where `entries` is updated (the `INSERT OR REPLACE INTO entries` call). Call `record_entry_changes()` immediately before the upsert, passing the new parsed data dict. Import `record_entry_changes` from `backend.db`.

4. Add API endpoint in `backend/app.py` inside `create_app()`:

```python
    @app.route("/api/entry/<int:lb_number>/changes", methods=["GET"])
    def entry_changes(lb_number):
        try:
            limit = int(request.args.get("limit", 50))
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT field, old_value, new_value, changed_at "
                "FROM entry_changes WHERE lb_number=? "
                "ORDER BY changed_at DESC LIMIT ?",
                (lb_number, limit)
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

**Done when:** After scraping an entry twice with differing data, `GET /api/entry/{lb}/changes` returns the changed fields with old/new values.

---

## CATEGORY: FEATURES — BACKEND + MINIMAL GUI

---

### FEAT-01: CLI / Headless Mode ## COMPLETE

**Files:** `cli.py` (new, in project root), `backend/app.py`  
**Dependencies:** None  
**New packages:** None

**Steps:**

1. Create `cli.py` in the project root:

```python
#!/usr/bin/env python3
"""
Headless CLI for LosslessBob. Starts Flask without PyQt6.
Usage:
  python cli.py lookup <file_or_glob> [--json]
  python cli.py search <query> [--field all|location|date|description] [--json]
  python cli.py stats [--json]
  python cli.py import <path_to_flat_file>
  python cli.py serve [--port 5174]
"""
import argparse
import json
import sys
import threading
from pathlib import Path


def _start_flask(port):
    from backend.app import create_app
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(prog="losslessbob")
    parser.add_argument("--port", type=int, default=5174)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("paths", nargs="+")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--field", default="all",
                          choices=["all", "location", "date", "description"])

    sub.add_parser("stats")

    p_import = sub.add_parser("import")
    p_import.add_argument("path")

    sub.add_parser("serve")

    args = parser.parse_args()
    port = args.port

    # Start Flask in a daemon thread for non-serve commands
    if args.command != "serve":
        t = threading.Thread(target=_start_flask, args=(port,), daemon=True)
        t.start()
        import time; time.sleep(1.2)  # Wait for Flask to bind

    import requests

    if args.command == "serve":
        _start_flask(port)  # Blocking

    elif args.command == "stats":
        r = requests.get(f"http://127.0.0.1:{port}/api/db/stats").json()
        print(json.dumps(r, indent=2) if args.json else
              f"LB entries: {r['total_lb_numbers']}  "
              f"Checksums: {r['total_checksums']}  "
              f"Latest LB: {r['latest_lb']}  "
              f"Last import: {r['last_import']}")

    elif args.command == "lookup":
        text_parts = []
        for pattern in args.paths:
            for p in Path(".").glob(pattern) if "*" in pattern else [Path(pattern)]:
                if p.is_file():
                    text_parts.append(p.read_text(errors="replace"))
        text = "\n".join(text_parts)
        r = requests.post(f"http://127.0.0.1:{port}/api/lookup",
                          json={"text": text}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            for lb in r.get("summary", {}).get("lb_summary", []):
                print(f"LB-{lb['lb_number']:05d}  {lb['status']:25s}  "
                      f"matched={lb['matched']}  missing={lb['missing_from_set']}")

    elif args.command == "search":
        r = requests.get(f"http://127.0.0.1:{port}/api/search",
                         params={"q": args.query, "field": args.field}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            for e in r:
                print(f"LB-{e['lb_number']:05d}  {e.get('date_str',''):12s}  "
                      f"{e.get('location','')[:50]}")

    elif args.command == "import":
        r = requests.post(f"http://127.0.0.1:{port}/api/db/import",
                          json={"file_path": str(Path(args.path).resolve())}).json()
        print(json.dumps(r, indent=2) if args.json else str(r))


if __name__ == "__main__":
    main()
```

2. Make executable: `chmod +x cli.py`

**Done when:** `python cli.py stats` prints DB statistics without launching a GUI window.

---

### FEAT-02: Fuzzy Filename Matching Fallback in Lookup ## WONTFIX

**Files:** `backend/db.py`, `requirements.txt`  
**Dependencies:** DB-04  
**New packages:** `rapidfuzz`

**Goal:** When a checksum is NOT FOUND in DB, attempt a secondary match by comparing input filename against DB filenames for any LB that has partial checksum matches. Returns candidate LB numbers with a confidence score.

**Steps:**

1. Add to `requirements.txt`:
```
rapidfuzz==3.9.3
```

2. Add a new function to `db.py`:

```python
def fuzzy_filename_lookup(parsed_entries, threshold=80, db_path=None):
    """
    For entries that were NOT FOUND by checksum, attempt filename-similarity matching.
    
    Args:
        parsed_entries: list of (checksum, filename, type) — only NOT FOUND ones
        threshold: minimum fuzz score (0-100) to report a candidate
        db_path: optional override
    
    Returns:
        dict mapping input checksum -> list of {lb_number, db_filename, score}
    """
    from rapidfuzz import process, fuzz

    if not parsed_entries:
        return {}

    conn = get_connection(db_path)
    # Load all (filename, lb_number) pairs — grouped for efficiency
    all_db_files = conn.execute(
        "SELECT DISTINCT filename, lb_number FROM checksums ORDER BY lb_number"
    ).fetchall()
    db_filenames = [r["filename"] for r in all_db_files]
    filename_to_lb = {r["filename"]: r["lb_number"] for r in all_db_files}

    results = {}
    for chk, fname, chk_type in parsed_entries:
        # Normalize: strip path, lowercase
        base = Path(fname).name.lower()
        matches = process.extract(
            base,
            [Path(f).name.lower() for f in db_filenames],
            scorer=fuzz.token_sort_ratio,
            limit=5,
            score_cutoff=threshold,
        )
        if matches:
            candidates = []
            for match_name, score, idx in matches:
                orig_fname = db_filenames[idx]
                candidates.append({
                    "lb_number": filename_to_lb[orig_fname],
                    "db_filename": orig_fname,
                    "score": score,
                })
            results[chk] = candidates

    return results
```

3. In `backend/app.py`, modify the `/api/lookup` route to call fuzzy matching for NOT FOUND items and include results:

```python
    @app.route("/api/lookup", methods=["POST"])
    def lookup():
        try:
            data = request.get_json()
            text = data.get("text", "")
            enable_fuzzy = data.get("fuzzy", False)
            parsed = database.parse_checksum_text(text)
            if not parsed:
                return jsonify({"error": "No valid checksums found in input"}), 400
            summary, detail = database.lookup_checksums(parsed)
            if enable_fuzzy:
                not_found = [(d["checksum"], d["filename"], d["type"])
                             for d in detail if d["status"] == "NOT FOUND"]
                if not_found:
                    fuzzy = database.fuzzy_filename_lookup(not_found)
                    for item in detail:
                        if item["status"] == "NOT FOUND" and item["checksum"] in fuzzy:
                            item["fuzzy_candidates"] = fuzzy[item["checksum"]]
            return jsonify({"summary": summary, "detail": detail})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

4. In `gui/lookup_tab.py`, add a "Fuzzy match" checkbox to the left panel. When checked, include `"fuzzy": True` in the POST body. In the detail table, for NOT FOUND rows that have `fuzzy_candidates`, append the top candidate LB number and score to the status cell text, e.g. `NOT FOUND (LB-00123? 87%)`.

**Done when:** A checksum file with slightly renamed files (e.g. track numbers reordered) returns fuzzy candidates with scores.

---

### FEAT-03: Per-Entry Personal Metadata ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. Add to `SCHEMA_SQL` in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS collection_meta (
    lb_number      INTEGER PRIMARY KEY,
    personal_rating INTEGER CHECK(personal_rating BETWEEN 1 AND 5),
    listen_count   INTEGER DEFAULT 0,
    last_listened  TIMESTAMP,
    tags           TEXT,
    FOREIGN KEY (lb_number) REFERENCES my_collection(lb_number) ON DELETE CASCADE
);
```

2. Add to `db.py`:

```python
def get_collection_meta(lb_number, db_path=None):
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM collection_meta WHERE lb_number=?", (lb_number,)
    ).fetchone()
    return dict(row) if row else {"lb_number": lb_number, "personal_rating": None,
                                   "listen_count": 0, "last_listened": None, "tags": None}


def set_collection_meta(lb_number, fields: dict, db_path=None):
    """Upsert personal metadata. fields keys: personal_rating, listen_count,
    last_listened, tags. Unknown keys are ignored."""
    allowed = {"personal_rating", "listen_count", "last_listened", "tags"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO collection_meta(lb_number) VALUES(?) ON CONFLICT(lb_number) DO NOTHING",
        (lb_number,)
    )
    set_clause = ", ".join(f"{k}=?" for k in clean)
    conn.execute(
        f"UPDATE collection_meta SET {set_clause} WHERE lb_number=?",
        list(clean.values()) + [lb_number]
    )
    conn.commit()


def increment_listen_count(lb_number, db_path=None):
    from datetime import datetime
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO collection_meta(lb_number, listen_count, last_listened) "
        "VALUES(?, 1, ?) ON CONFLICT(lb_number) DO UPDATE SET "
        "listen_count=listen_count+1, last_listened=excluded.last_listened",
        (lb_number, datetime.utcnow().isoformat())
    )
    conn.commit()
```

3. Add routes to `backend/app.py` inside `create_app()`:

```python
    @app.route("/api/collection/<int:lb>/meta", methods=["GET"])
    def get_coll_meta(lb):
        return jsonify(database.get_collection_meta(lb))

    @app.route("/api/collection/<int:lb>/meta", methods=["POST"])
    def set_coll_meta(lb):
        database.set_collection_meta(lb, request.get_json() or {})
        return jsonify({"ok": True})

    @app.route("/api/collection/<int:lb>/listen", methods=["POST"])
    def log_listen(lb):
        database.increment_listen_count(lb)
        return jsonify({"ok": True})
```

4. In `gui/collection_tab.py`, add a right-click context menu item "Edit Personal Info" on collection rows. The dialog should have: Rating (1–5 stars, use a `QComboBox`), Tags (free text `QLineEdit`), Listen Count (read-only `QLabel`). On OK, POST to `/api/collection/{lb}/meta`.

**Done when:** Rating and tags persist across app restarts. Listen count increments on each "Log Listen" action.

---

### FEAT-04: Wishlist Tab ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`, `gui/collection_tab.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. Add to `SCHEMA_SQL` in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS my_wishlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL UNIQUE,
    added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    priority   INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    notes      TEXT,
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE INDEX IF NOT EXISTS idx_wishlist_lb ON my_wishlist(lb_number);
```

2. Add to `db.py`:

```python
def get_wishlist(db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT w.id, w.lb_number, w.added_at, w.priority, w.notes,
               e.date_str, e.location, e.rating, e.description
        FROM my_wishlist w
        LEFT JOIN entries e ON e.lb_number = w.lb_number
        ORDER BY w.priority DESC, w.lb_number
    """).fetchall()
    return [dict(r) for r in rows]


def add_to_wishlist(lb_number, priority=3, notes=None, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO my_wishlist(lb_number, priority, notes) VALUES(?,?,?)",
        (lb_number, priority, notes)
    )
    conn.commit()
    return conn.execute("SELECT changes()").fetchone()[0]


def remove_from_wishlist(lb_number, db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM my_wishlist WHERE lb_number=?", (lb_number,))
    conn.commit()


def get_wishlist_lb_numbers(db_path=None):
    conn = get_connection(db_path)
    return [r[0] for r in conn.execute("SELECT lb_number FROM my_wishlist").fetchall()]
```

3. Add routes to `backend/app.py`:

```python
    @app.route("/api/wishlist", methods=["GET"])
    def wishlist_list():
        return jsonify(database.get_wishlist())

    @app.route("/api/wishlist", methods=["POST"])
    def wishlist_add():
        data = request.get_json() or {}
        lb = data.get("lb_number")
        if not lb:
            return jsonify({"error": "lb_number required"}), 400
        added = database.add_to_wishlist(int(lb), data.get("priority", 3), data.get("notes"))
        return jsonify({"ok": True, "added": added > 0})

    @app.route("/api/wishlist/<int:lb>", methods=["DELETE"])
    def wishlist_remove(lb):
        database.remove_from_wishlist(lb)
        return jsonify({"ok": True})
```

4. In `gui/collection_tab.py`, add a third inner tab "Wishlist" in `_build_ui()`, modelled exactly on the "My Collection" panel but calling `/api/wishlist`. Columns: LB Number, Date, Location, Rating, Priority (1–5), Notes, Added.

5. In `gui/lookup_tab.py` and `gui/search_tab.py`, add "Add to Wishlist" to the right-click context menu on result rows. POST `{"lb_number": lb}` to `/api/wishlist`.

6. In `gui/styles.py`, add a wishlist row color (e.g. light purple `#E8D5FF`) to the color dict. Apply it as row background in the Wishlist table model.

**Done when:** Items added via Search right-click appear in the Wishlist tab with priority and notes editable.

---

### FEAT-05: Duplicate Concert Detector ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`, `gui/collection_tab.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. Add to `db.py`:

```python
def get_collection_duplicates(db_path=None):
    """
    Find date+location combinations where the user owns more than one LB entry.
    Also returns unowned LB entries for the same show.
    Returns list of groups: {date_str, location, owned: [...], unowned: [...]}.
    """
    conn = get_connection(db_path)
    # Find owned entries grouped by date+location
    dupes = conn.execute("""
        SELECT e.date_str, e.location, COUNT(*) as cnt
        FROM entries e
        JOIN my_collection c ON c.lb_number = e.lb_number
        WHERE e.date_str IS NOT NULL AND e.date_str != ''
          AND e.location IS NOT NULL AND e.location != ''
        GROUP BY e.date_str, e.location
        HAVING cnt > 1
        ORDER BY e.date_str
    """).fetchall()

    results = []
    for row in dupes:
        # All LBs for this show
        all_lbs = conn.execute("""
            SELECT e.lb_number, e.rating, e.description,
                   (CASE WHEN c.lb_number IS NOT NULL THEN 1 ELSE 0 END) as owned
            FROM entries e
            LEFT JOIN my_collection c ON c.lb_number = e.lb_number
            WHERE e.date_str=? AND e.location=?
            ORDER BY owned DESC, e.lb_number
        """, (row["date_str"], row["location"])).fetchall()
        results.append({
            "date_str": row["date_str"],
            "location": row["location"],
            "owned": [dict(r) for r in all_lbs if r["owned"]],
            "unowned": [dict(r) for r in all_lbs if not r["owned"]],
        })
    return results
```

2. Add route in `backend/app.py`:

```python
    @app.route("/api/collection/duplicates", methods=["GET"])
    def collection_duplicates():
        return jsonify(database.get_collection_duplicates())
```

3. In `gui/collection_tab.py`, add a fourth inner tab "Duplicates" in `_build_ui()`. On tab activation (connect `currentChanged` signal), call `GET /api/collection/duplicates`. Display as a two-level list: top-level is the show (date + location), expandable to show owned LBs (green) and other unowned LBs of the same show (grey). Use a `QTreeWidget` with two columns: LB Number, Rating. Right-click on owned rows: "Remove from Collection". Right-click on unowned rows: "Open on LosslessBob".

**Done when:** A user owning LB-100 and LB-101 from the same date/venue sees them grouped under one show entry.

---

### FEAT-06: Auto-Generate `info.txt` Per Recording ## CANCELLED

**Files:** `backend/app.py`, `gui/collection_tab.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. Add route in `backend/app.py`:

```python
    @app.route("/api/collection/<int:lb>/generate_info", methods=["POST"])
    def generate_info(lb):
        try:
            data = request.get_json() or {}
            target_dir = data.get("disk_path")
            if not target_dir:
                # Look up from collection
                conn = database.get_connection()
                row = conn.execute(
                    "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb,)
                ).fetchone()
                if not row:
                    return jsonify({"error": "Not in collection"}), 404
                target_dir = row["disk_path"]

            entry_data = database.get_entry(lb)
            if not entry_data:
                return jsonify({"error": "Entry not found"}), 404
            e = entry_data["entry"]

            lines = [
                f"LosslessBob Archive — LB-{lb:05d}",
                "=" * 50,
                f"Date:        {e.get('date_str', '')}",
                f"Location:    {e.get('location', '')}",
                f"CDR:         {e.get('cdr', '')}",
                f"Rating:      {e.get('rating', '')}",
                f"Timing:      {e.get('timing', '')}",
                "",
                "Description:",
                e.get("description", "").strip(),
                "",
                "Setlist:",
                e.get("setlist", "").strip(),
                "",
                f"Source: http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html",
            ]
            content = "\n".join(lines)

            out_path = Path(target_dir) / "info.txt"
            out_path.write_text(content, encoding="utf-8")
            return jsonify({"ok": True, "path": str(out_path)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

2. In `gui/collection_tab.py`, add "Generate info.txt" to the right-click context menu (`_on_coll_context`). On click: POST to `/api/collection/{lb}/generate_info` with `{}` body (backend reads disk_path from collection). Show result in `coll_status` label.

**Done when:** Right-click → "Generate info.txt" on a collection row writes a properly-formatted `info.txt` into the recording's folder.

---

### FEAT-07: Portable Export Formats (HTML + M3U) ## COMPLETE

**Files:** `backend/app.py`, `gui/collection_tab.py`  
**Dependencies:** DB-01  
**New packages:** None

**Steps:**

1. Add two routes in `backend/app.py`:

```python
    @app.route("/api/collection/export/html", methods=["GET"])
    def export_collection_html():
        try:
            rows = database.get_collection()
            lines = [
                "<!DOCTYPE html><html><head><meta charset='utf-8'>",
                "<title>My LosslessBob Collection</title>",
                "<style>body{font-family:monospace;font-size:13px}",
                "table{border-collapse:collapse;width:100%}",
                "th,td{border:1px solid #ccc;padding:4px 8px;text-align:left}",
                "th{background:#eee}tr:nth-child(even){background:#f9f9f9}</style></head>",
                "<body><h1>My LosslessBob Collection</h1>",
                f"<p>{len(rows)} recordings</p>",
                "<table><thead><tr>",
                "<th>LB#</th><th>Date</th><th>Location</th><th>Folder</th><th>Notes</th>",
                "</tr></thead><tbody>",
            ]
            for r in rows:
                lb = r.get("lb_number", "")
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
                lines.append(
                    f"<tr><td><a href='{url}'>LB-{lb:05d}</a></td>"
                    f"<td>{r.get('date_str','')}</td>"
                    f"<td>{r.get('location','')}</td>"
                    f"<td>{r.get('folder_name','')}</td>"
                    f"<td>{r.get('notes','') or ''}</td></tr>"
                )
            lines += ["</tbody></table></body></html>"]
            from flask import Response
            return Response("\n".join(lines), mimetype="text/html",
                            headers={"Content-Disposition":
                                     "attachment; filename=collection.html"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/export/m3u", methods=["GET"])
    def export_collection_m3u():
        try:
            rows = database.get_collection()
            audio_exts = {".flac", ".shn", ".ape", ".wav", ".mp3"}
            lines = ["#EXTM3U"]
            for r in rows:
                dp = r.get("disk_path", "")
                if not dp or not Path(dp).is_dir():
                    continue
                for f in sorted(Path(dp).iterdir()):
                    if f.suffix.lower() in audio_exts:
                        lines.append(f"#EXTINF:-1,{r.get('date_str','')} - "
                                     f"{r.get('location','')}")
                        lines.append(str(f))
            from flask import Response
            return Response("\n".join(lines), mimetype="audio/x-mpegurl",
                            headers={"Content-Disposition":
                                     "attachment; filename=collection.m3u"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

2. In `gui/collection_tab.py`, in `_build_collection_panel()`, add two buttons to the button row: "Export HTML…" and "Export M3U". On click, GET the respective endpoint, write the response bytes to a user-chosen save path via `QFileDialog.getSaveFileName()`.

**Done when:** Both export buttons produce valid files. The HTML file opens in a browser and shows a sortable table. The M3U loads in VLC and plays audio files in date order.

---

### FEAT-08: Batch Filesystem Scan → Auto-Lookup ## COMPLETE

**Files:** `gui/lookup_tab.py`  
**Dependencies:** None (uses existing `/api/lookup`)  
**New packages:** None

**Goal:** Add a "Scan Folder Tree" button that recursively finds all checksum files under a root directory and runs a combined lookup, showing per-folder aggregate results.

**Steps:**

1. In `gui/lookup_tab.py`, add a "Scan Tree…" button to the left panel button group, below "Add Folders".

2. Add slot `_on_scan_tree()`:

```python
    def _on_scan_tree(self):
        root = QFileDialog.getExistingDirectory(self, "Select Root Directory")
        if not root:
            return
        root_path = Path(root)
        CHECKSUM_EXTS = {".ffp", ".md5", ".st5", ".sha1", ".shn"}
        found = []
        for p in sorted(root_path.rglob("*")):
            if p.is_file() and p.suffix.lower() in CHECKSUM_EXTS:
                if "_mychecksums" in p.name.lower() and self._filter_cb.isChecked():
                    continue
                found.append(p)
        if not found:
            self._status_label.setText("No checksum files found under selected folder.")
            return
        # Combine all found files into one lookup text blob
        text_parts = []
        for p in found:
            try:
                text_parts.append(p.read_text(errors="replace"))
            except OSError:
                pass
        combined = "\n".join(text_parts)
        # Reuse the existing _LookupWorker path
        self._run_lookup(combined)
```

3. `_run_lookup(text)` is the existing method that POSTs to `/api/lookup` and populates the tables. If it doesn't exist as a named method (the lookup logic may be inline), extract it to a named method first.

**Done when:** Selecting a root folder with 10 subdirectories each containing `.ffp` files returns a combined summary table with one row per matched LB.

---

### FEAT-09: Collection Folder Integrity Watchdog ## COMPLETE

**Files:** `backend/scheduler.py`, `backend/app.py`  
**Dependencies:** DB-01  
**New packages:** None (Watchdog already in requirements)

**Goal:** Watch `disk_path` entries in `my_collection` for file deletions or modifications. Log a warning row to a new `integrity_events` table. Expose events via API so the GUI can display alerts.

**Steps:**

1. Add to `SCHEMA_SQL` in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS integrity_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER,
    disk_path  TEXT,
    event_type TEXT,
    detail     TEXT,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged INTEGER DEFAULT 0
);
```

2. Add to `db.py`:

```python
def log_integrity_event(lb_number, disk_path, event_type, detail, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO integrity_events(lb_number, disk_path, event_type, detail) "
        "VALUES(?,?,?,?)",
        (lb_number, disk_path, event_type, detail)
    )
    conn.commit()


def get_integrity_events(unacked_only=True, limit=100, db_path=None):
    conn = get_connection(db_path)
    where = "WHERE acknowledged=0" if unacked_only else ""
    rows = conn.execute(
        f"SELECT * FROM integrity_events {where} "
        f"ORDER BY occurred_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def ack_integrity_events(ids: list, db_path=None):
    if not ids:
        return
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE integrity_events SET acknowledged=1 WHERE id IN ({placeholders})", ids
    )
    conn.commit()
```

3. In `backend/scheduler.py`, add a second Watchdog observer for collection paths. Add a function `start_collection_watcher()`:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

_collection_observer = None

class _CollectionEventHandler(FileSystemEventHandler):
    def __init__(self, lb_number, disk_path):
        self.lb_number = lb_number
        self.disk_path = disk_path

    def on_deleted(self, event):
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "deleted", f"Deleted: {event.src_path}"
        )

    def on_moved(self, event):
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "moved", f"Moved: {event.src_path} -> {event.dest_path}"
        )


def start_collection_watcher(db_path=None):
    global _collection_observer
    from backend.db import get_connection, DB_PATH
    from pathlib import Path
    if _collection_observer:
        _collection_observer.stop()
    _collection_observer = Observer()
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT lb_number, disk_path FROM my_collection"
    ).fetchall()
    for row in rows:
        dp = Path(row["disk_path"])
        if dp.is_dir():
            handler = _CollectionEventHandler(row["lb_number"], row["disk_path"])
            _collection_observer.schedule(handler, str(dp), recursive=False)
    _collection_observer.start()
```

4. In `backend/app.py`, inside `create_app()`, after `scheduler.start_file_watcher()`, add:
```python
    scheduler.start_collection_watcher()
```

5. Add routes in `backend/app.py`:

```python
    @app.route("/api/integrity/events", methods=["GET"])
    def integrity_events():
        unacked = request.args.get("unacked", "1") == "1"
        return jsonify(database.get_integrity_events(unacked_only=unacked))

    @app.route("/api/integrity/ack", methods=["POST"])
    def integrity_ack():
        ids = (request.get_json() or {}).get("ids", [])
        database.ack_integrity_events(ids)
        return jsonify({"ok": True})
```

6. In `gui/main_window.py`, in the status bar refresh timer (every 10 seconds), also call `GET /api/integrity/events?unacked=1`. If count > 0, append a yellow warning indicator to the status bar text: `⚠ {count} integrity alert(s)`. Clicking the status bar label opens a small dialog listing the events with an "Acknowledge All" button.

**Done when:** Deleting a file from a tracked collection folder causes an unacknowledged event to appear in the status bar within ~10 seconds.

---

## CATEGORY: DEFERRED / HIGH-EFFORT

---

### DEFERRED-01: BLOB Checksum Storage

**Files:** `backend/db.py`, `backend/importer.py`, all callers  
**Dependencies:** All other DB tasks should be complete first  
**Risk:** Full DB migration required. All existing `losslessbob.db` files must be rebuilt.

**Steps:**

1. Change `checksum TEXT NOT NULL` to `checksum BLOB NOT NULL` in `SCHEMA_SQL`.

2. Add hex↔blob helpers at top of `db.py`:

```python
import binascii

def _to_blob(hex_str: str) -> bytes:
    return binascii.unhexlify(hex_str)

def _to_hex(blob: bytes) -> str:
    return blob.hex()
```

3. Wrap every `INSERT` of a checksum value with `_to_blob()` and every `SELECT` result with `_to_hex()`.

4. The covering index from DB-03 still applies; update its definition to `ON checksums(checksum, lb_number, chk_type, filename, xref)` (same SQL, storage shrinks automatically).

5. Provide a migration script `tools/migrate_blob.py` that:
   - Opens the existing DB
   - Creates a new DB at a temporary path with BLOB schema
   - Copies all rows with conversion
   - Swaps files atomically

**Note:** Only do this if profiling shows the covering index is insufficient. At typical LosslessBob archive size (~5M checksums) the TEXT representation is fine with the indexes from DB-03 in place.

---

### DEFERRED-02: Concert Timeline Browser (Qt Canvas)

**Files:** `gui/timeline_tab.py` (new), `gui/main_window.py`  
**Dependencies:** DB-05 (FTS5 for year filtering), FEAT-03 (personal metadata for coloring)  
**New packages:** None

**Goal:** A `QWidget` with a custom `paintEvent` rendering a vertical timeline grouped by year. Nodes colored by ownership status. Click navigates to entry.

**High-level spec:**

- Query `GET /api/entries/year/{year}` for each year in `get_distinct_years()`.
- Owned LB numbers come from `GET /api/collection/lb_numbers`.
- Wishlist from `GET /api/wishlist` (after FEAT-04).
- Paint: year header row, then one dot per LB in that year. Color: green=owned, blue=wishlist, grey=unowned, yellow=status=missing.
- Clicking a dot emits a signal picked up by `main_window.py` to open lookup for that LB.
- Year labels on left axis. Horizontal scroll if needed (many concerts per year).
- Add as tab 7 in `main_window.py`.

---

### DEFERRED-03: External API / Webhook Mode

**Files:** `main.py`, `backend/app.py`  
**Dependencies:** None  
**New packages:** None

**Steps:**

1. In `main.py`, add CLI flag parsing before starting Flask:

```python
import argparse
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--api-only", action="store_true")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=5174)
parser.add_argument("--token", default=None, help="Bearer token for auth")
args, _ = parser.parse_known_args()
```

2. If `--api-only`, skip importing PyQt6 entirely, start Flask with `host=args.host`, and block. This enables running as a headless service.

3. If `--token` is provided, register a `before_request` hook in `create_app()`:

```python
    if token:
        @app.before_request
        def check_auth():
            if request.method == "OPTIONS":
                return
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                return jsonify({"error": "Unauthorized"}), 401
```

4. Store the token in `meta` table under key `api_token`. Add a "Generate Token" button in the Setup tab that writes a random 32-char hex token to meta and displays it once.

---

---

### FEAT-10: GitHub Auto-Updater + Enhanced About Dialog ## COMPLETE

**Files:** `VERSION` (new, project root), `backend/version.py` (new), `backend/app.py`, `gui/main_window.py`, `gui/setup_tab.py`  
**Dependencies:** `backend/paths.py` exists (WIN-01 done)  
**New packages:** None (`requests` already present)

---

#### Part A — Version File (Single Source of Truth)

1. Create `VERSION` in the project root (plain text):

```
1.0.0
```

2. Create `backend/version.py`:

```python
from backend.paths import APP_ROOT

def get_version() -> str:
    try:
        return (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"

VERSION: str = get_version()
```

3. In `gui/main_window.py`, delete `VERSION = "1.0.0"` at module level. Add:

```python
from backend.version import VERSION
```

---

#### Part B — Enhanced About Dialog

Replace `_on_about()` in `gui/main_window.py`:

```python
    def _on_about(self):
        import sys, platform
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        from backend.version import VERSION
        info = (
            f"LosslessBob Checksum Lookup\n"
            f"Version: {VERSION}\n\n"
            f"Python: {sys.version.split()[0]}\n"
            f"PyQt6: {PYQT_VERSION_STR}  |  Qt: {QT_VERSION_STR}\n"
            f"Platform: {platform.system()} {platform.release()} "
            f"({'64-bit' if platform.machine().endswith('64') else '32-bit'})\n\n"
            "Cross-platform replacement for the original Windows Checksum_Lookup utility.\n"
            "Supports the LosslessBob Bob Dylan lossless recording archive.\n\n"
            "Built with Python, PyQt6, and Flask."
        )
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.about(self, "About LosslessBob", info)
```

---

#### Part C — Update API Routes

1. Add `"github_repo"` to the keys list in the `GET /api/db/settings` handler in `backend/app.py`:

```python
keys = ["scrape_attachments", "scrape_delay_ms", "auto_scrape", "use_local_pages",
        "force_scrape", "search_page_size", "github_repo", "data_zip_url"]
```

2. Add module-level update state in `backend/app.py` after `_scrape_thread = None`:

```python
import threading as _threading

_update_state = {
    "status": "idle",      # idle | checking | downloading | applying | done | error
    "progress": 0,
    "message": "",
    "latest_version": None,
    "update_available": False,
}
_update_lock = _threading.Lock()
```

3. Add routes inside `create_app()`:

```python
    @app.route("/api/app/version", methods=["GET"])
    def app_version():
        import sys, platform
        from backend.version import VERSION
        try:
            from PyQt6.QtCore import QT_VERSION_STR
        except Exception:
            QT_VERSION_STR = "n/a"
        return jsonify({
            "version": VERSION,
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "qt": QT_VERSION_STR,
        })

    @app.route("/api/update/check", methods=["GET"])
    def update_check():
        try:
            import requests as _req
            from backend.version import VERSION
            repo = database.get_meta("github_repo") or ""
            if not repo or "/" not in repo:
                return jsonify({"error": "github_repo not configured"}), 400
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            resp = _req.get(api_url, timeout=10,
                headers={"Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"})
            if resp.status_code == 404:
                return jsonify({"error": "No releases found for this repository"}), 404
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            release_notes = data.get("body", "")
            zipball_url = data.get("zipball_url", "")

            def _ver(v):
                try:
                    return tuple(int(x) for x in v.split(".")[:3])
                except Exception:
                    return (0, 0, 0)

            update_available = _ver(latest_tag) > _ver(VERSION)
            with _update_lock:
                _update_state.update({
                    "latest_version": latest_tag,
                    "update_available": update_available,
                })
            return jsonify({
                "current": VERSION, "latest": latest_tag,
                "update_available": update_available,
                "release_notes": release_notes,
                "zipball_url": zipball_url,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/update/status", methods=["GET"])
    def update_status():
        with _update_lock:
            return jsonify(dict(_update_state))

    @app.route("/api/update/apply", methods=["POST"])
    def update_apply():
        try:
            repo = database.get_meta("github_repo") or ""
            if not repo:
                return jsonify({"error": "github_repo not configured"}), 400
            data = request.get_json() or {}
            zipball_url = data.get("zipball_url", "")
            if not zipball_url:
                return jsonify({"error": "zipball_url required"}), 400
            import threading as _t
            _t.Thread(target=_do_update, args=(zipball_url,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

4. Add `_do_update()` at module level in `backend/app.py` (outside `create_app()`):

```python
# Source files updated by _do_update — never touch data/ or user files
_UPDATE_SKIP_DIRS  = frozenset({"data", ".git", "__pycache__", ".venv", "venv", "dist", "build"})
_UPDATE_SKIP_EXTS  = frozenset({".db", ".ini", ".log", ".sdf"})


def _do_update(zipball_url: str) -> None:
    import zipfile, shutil, tempfile
    import requests as _req
    from pathlib import Path
    from backend.paths import APP_ROOT

    def _set(status, progress, message):
        with _update_lock:
            _update_state.update({"status": status, "progress": progress, "message": message})

    try:
        _set("downloading", 5, "Connecting to GitHub…")
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "update.zip"
            resp = _req.get(zipball_url, stream=True, timeout=60,
                            headers={"Accept": "application/octet-stream"})
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 40) + 5 if total else 30
                        _set("downloading", pct, f"Downloading… {downloaded // 1024:,} KB")

            _set("applying", 50, "Extracting…")
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                # GitHub zipballs have a single root dir prefix — strip it
                prefix = (members[0].split("/")[0] + "/") if members else ""
                for i, member in enumerate(members):
                    rel = member[len(prefix):]
                    if not rel or member.endswith("/"):
                        continue
                    parts = Path(rel).parts
                    if parts and parts[0] in _UPDATE_SKIP_DIRS:
                        continue
                    if Path(rel).suffix.lower() in _UPDATE_SKIP_EXTS:
                        continue
                    dest = APP_ROOT / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    pct = int(i / max(len(members), 1) * 45) + 50
                    _set("applying", min(pct, 95), f"Applying… ({i + 1} files)")

        _set("done", 100, "Update applied. Click Restart to reload the application.")
    except Exception as e:
        _set("error", 0, f"Update failed: {e}")
```

---

#### Part D — Restart Helper

Create `backend/updater.py`:

```python
import subprocess
import sys


def restart_application() -> None:
    """
    Relaunch the application and exit the current process.
    Source install: spawns new Python process with identical args.
    Frozen Linux/macOS: re-executes the binary.
    Frozen Windows: raises RuntimeError — user must restart manually.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen and sys.platform == "win32":
        raise RuntimeError(
            "Auto-restart is not supported for Windows packaged builds.\n"
            "Please close and reopen the application to use the updated version."
        )
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([sys.executable] + sys.argv, **kwargs)
    sys.exit(0)
```

---

#### Part E — Setup Tab UI (Updates Group)

In `gui/setup_tab.py`, insert before `layout.addStretch()` at end of `_build_ui()`:

```python
        update_group = QGroupBox("Application Updates")
        upd_layout = QVBoxLayout(update_group)

        repo_row = QHBoxLayout()
        repo_row.addWidget(QLabel("GitHub Repo (owner/repo):"))
        self.github_repo_input = QLineEdit()
        self.github_repo_input.setPlaceholderText("e.g. johndoe/losslessbob")
        self.github_repo_input.editingFinished.connect(self._save_settings)
        repo_row.addWidget(self.github_repo_input)
        upd_layout.addLayout(repo_row)

        upd_btn_row = QHBoxLayout()
        self.check_app_update_btn = QPushButton("Check for Updates")
        self.check_app_update_btn.clicked.connect(self._on_check_app_update)
        upd_btn_row.addWidget(self.check_app_update_btn)
        self.apply_update_btn = QPushButton("Download && Apply Update")
        self.apply_update_btn.setEnabled(False)
        self.apply_update_btn.clicked.connect(self._on_apply_update)
        upd_btn_row.addWidget(self.apply_update_btn)
        self.restart_app_btn = QPushButton("Restart Application")
        self.restart_app_btn.setEnabled(False)
        self.restart_app_btn.clicked.connect(self._on_restart_app)
        upd_btn_row.addWidget(self.restart_app_btn)
        upd_btn_row.addStretch()
        upd_layout.addLayout(upd_btn_row)

        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        upd_layout.addWidget(self.update_progress)
        self.update_status_label = QLabel("")
        upd_layout.addWidget(self.update_status_label)
        layout.addWidget(update_group)
```

Add instance variables in `__init__` (after `self._load_settings()`):

```python
        self._zipball_url: str = ""
        self._update_poll_timer = None
        self._data_dl_poll_timer = None
```

Add to `_load_settings()` inside the `try` block:

```python
            self.github_repo_input.setText(data.get("github_repo") or "")
```

Add to `_save_settings()` JSON dict:

```python
                    "github_repo": self.github_repo_input.text().strip(),
```

Add update slots:

```python
    def _on_check_app_update(self):
        self.check_app_update_btn.setEnabled(False)
        self.apply_update_btn.setEnabled(False)
        self.update_status_label.setText("Checking GitHub…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/update/check", timeout=15
        ).json())
        w.finished.connect(self._on_update_check_done)
        w.error.connect(lambda e: (
            self.update_status_label.setText(f"Check failed: {e}"),
            self.check_app_update_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_update_check_done(self, data):
        self.check_app_update_btn.setEnabled(True)
        if "error" in data:
            self.update_status_label.setText(f"Error: {data['error']}")
            return
        current = data.get("current", "?")
        latest = data.get("latest", "?")
        if data.get("update_available"):
            self._zipball_url = data.get("zipball_url", "")
            self.apply_update_btn.setEnabled(True)
            notes = (data.get("release_notes") or "").strip()[:200]
            self.update_status_label.setText(
                f"Update available: v{current} → v{latest}\n{notes}"
            )
        else:
            self.update_status_label.setText(f"Up to date (v{current})")

    def _on_apply_update(self):
        if not self._zipball_url:
            return
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(
            self, "Apply Update",
            "Download and apply the update now?\n\n"
            "Python source files will be replaced.\n"
            "Your data/ folder and settings are never modified.\n\n"
            "Click Restart after the update completes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self.apply_update_btn.setEnabled(False)
        self.update_progress.setVisible(True)
        self.update_progress.setValue(0)
        self.update_status_label.setText("Starting download…")
        w = _ApiWorker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/update/apply",
            json={"zipball_url": self._zipball_url}, timeout=10,
        ).json())
        w.finished.connect(lambda r: (
            self._start_update_poll() if not r.get("error")
            else self.update_status_label.setText(f"Error: {r['error']}")
        ))
        w.error.connect(lambda e: self.update_status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _start_update_poll(self):
        from PyQt6.QtCore import QTimer
        self._update_poll_timer = QTimer(self)
        self._update_poll_timer.timeout.connect(self._poll_update_status)
        self._update_poll_timer.start(1000)

    def _poll_update_status(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/update/status", timeout=5
            ).json()
            status = r.get("status", "")
            self.update_progress.setValue(r.get("progress", 0))
            self.update_status_label.setText(r.get("message", ""))
            if status in ("done", "error"):
                self._update_poll_timer.stop()
                self.update_progress.setVisible(False)
                if status == "done":
                    self.restart_app_btn.setEnabled(True)
                else:
                    self.apply_update_btn.setEnabled(True)
        except Exception:
            pass

    def _on_restart_app(self):
        try:
            from backend.updater import restart_application
            restart_application()
        except RuntimeError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Restart Required", str(e))
```

**Done when:**
- About dialog shows version, Python version, Qt version, platform string.
- Check for Updates queries GitHub releases, shows version comparison or "Up to date".
- Download & Apply fills progress bar to 100%, extracts `.py` files, leaves `data/` untouched.
- Restart Application relaunches the process.
- `VERSION` file is the only place the version string needs to be changed on release.

**Cross-platform notes:**
- `backend/updater.py` uses `subprocess.CREATE_NO_WINDOW` directly (WIN-05 already applied to codebase).
- Frozen Windows builds show manual restart message instead of crashing.
- GitHub releases API: 60 unauthenticated requests/hour. Rate limit returns HTTP 403 — the `raise_for_status()` call surfaces this as a clear error.

---

### FEAT-11: Remote Data ZIP Retrieval ## COMPLETE

**Files:** `backend/app.py`, `gui/setup_tab.py`  
**Dependencies:** `backend/paths.py` exists (WIN-01 done)  
**New packages:** None

**Purpose:** Download a ZIP archive from a user-configured URL and extract its contents into the `data/` directory. Intended for distributing pre-populated flat files, attachment caches, or database seeds outside of GitHub. The URL is hosted by the maintainer and configured in the Setup tab. The user's database (`losslessbob.db`) and settings are never overwritten.

---

#### Part A — Download State + API Routes

Add module-level state in `backend/app.py` after `_update_state`:

```python
_data_dl_state = {
    "status": "idle",        # idle | downloading | extracting | done | error
    "progress": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "message": "",
    "files_extracted": [],
    "files_skipped": [],
}
_data_dl_lock = _threading.Lock()
```

Add routes inside `create_app()`:

```python
    @app.route("/api/data/download", methods=["POST"])
    def data_download():
        try:
            url = database.get_meta("data_zip_url") or ""
            if not url:
                return jsonify({"error": "data_zip_url not configured"}), 400
            with _data_dl_lock:
                if _data_dl_state["status"] in ("downloading", "extracting"):
                    return jsonify({"error": "Download already in progress"}), 409
            import threading as _t
            _t.Thread(target=_do_data_download, args=(url,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/data/download/status", methods=["GET"])
    def data_download_status():
        with _data_dl_lock:
            return jsonify(dict(_data_dl_state))
```

Add `_do_data_download()` at module level in `backend/app.py`:

```python
# Files/names never overwritten regardless of ZIP contents
_DATA_PROTECTED = frozenset({
    "losslessbob.db", "settings.ini", "scraper.log", "temp_import.db",
})
_DATA_PROTECTED_EXTS = frozenset({".db", ".ini"})


def _do_data_download(url: str) -> None:
    import zipfile, shutil, tempfile
    import requests as _req
    from pathlib import Path
    from backend.paths import DATA_DIR

    def _set(status, progress, message, **kw):
        with _data_dl_lock:
            _data_dl_state.update({"status": status, "progress": progress,
                                    "message": message, **kw})

    try:
        _set("downloading", 2, "Connecting…",
             downloaded_bytes=0, total_bytes=0, files_extracted=[], files_skipped=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "data_update.zip"
            resp = _req.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 45) + 2 if total else 30
                        _set("downloading", pct,
                             f"Downloading… {downloaded // 1024:,} KB"
                             + (f" / {total // 1024:,} KB" if total else ""),
                             downloaded_bytes=downloaded, total_bytes=total)

            if not zipfile.is_zipfile(zip_path):
                _set("error", 0, "Downloaded file is not a valid ZIP archive.")
                return

            _set("extracting", 50, "Extracting…")
            extracted, skipped = [], []

            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                # Detect single top-level directory prefix and strip it
                roots = {m.split("/")[0] for m in members if "/" in m}
                strip_prefix = (list(roots)[0] + "/") if len(roots) == 1 else ""

                for i, member in enumerate(members):
                    rel = member[len(strip_prefix):] if strip_prefix else member
                    if not rel or rel.endswith("/"):
                        continue
                    rel_path = Path(rel)
                    name = rel_path.name
                    if name in _DATA_PROTECTED or rel_path.suffix.lower() in _DATA_PROTECTED_EXTS:
                        skipped.append(rel)
                        continue
                    dest = DATA_DIR / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(rel)
                    pct = int(i / max(len(members), 1) * 45) + 50
                    _set("extracting", min(pct, 95),
                         f"Extracting… ({i + 1}/{len(members)} files)",
                         files_extracted=extracted, files_skipped=skipped)

        _set("done", 100,
             f"Done. {len(extracted)} file(s) extracted, {len(skipped)} skipped (protected).",
             files_extracted=extracted, files_skipped=skipped)
    except Exception as e:
        _set("error", 0, f"Download failed: {e}")
```

---

#### Part B — Setup Tab UI (Remote Data Group)

In `gui/setup_tab.py`, add after the update group (or directly before `layout.addStretch()`):

```python
        data_dl_group = QGroupBox("Remote Data")
        ddl_layout = QVBoxLayout(data_dl_group)

        zip_url_row = QHBoxLayout()
        zip_url_row.addWidget(QLabel("Data ZIP URL:"))
        self.data_zip_url_input = QLineEdit()
        self.data_zip_url_input.setPlaceholderText("https://example.com/losslessbob_data.zip")
        self.data_zip_url_input.editingFinished.connect(self._save_settings)
        zip_url_row.addWidget(self.data_zip_url_input)
        ddl_layout.addLayout(zip_url_row)

        ddl_btn_row = QHBoxLayout()
        self.data_download_btn = QPushButton("Download && Extract Data")
        self.data_download_btn.setToolTip(
            "Download the ZIP from the configured URL and extract into data/.\n"
            "Your database and settings are never overwritten."
        )
        self.data_download_btn.clicked.connect(self._on_data_download)
        ddl_btn_row.addWidget(self.data_download_btn)
        ddl_btn_row.addStretch()
        ddl_layout.addLayout(ddl_btn_row)

        self.data_dl_progress = QProgressBar()
        self.data_dl_progress.setVisible(False)
        ddl_layout.addWidget(self.data_dl_progress)
        self.data_dl_status_label = QLabel("")
        self.data_dl_status_label.setWordWrap(True)
        ddl_layout.addWidget(self.data_dl_status_label)
        layout.addWidget(data_dl_group)
```

Add to `_load_settings()` inside the `try` block:

```python
            self.data_zip_url_input.setText(data.get("data_zip_url") or "")
```

Add to `_save_settings()` JSON dict:

```python
                    "data_zip_url": self.data_zip_url_input.text().strip(),
```

Add data download slots:

```python
    def _on_data_download(self):
        url = self.data_zip_url_input.text().strip()
        if not url:
            self.data_dl_status_label.setText("Configure a Data ZIP URL first.")
            return
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(
            self, "Download Remote Data",
            f"Download and extract data from:\n{url}\n\n"
            "Contents will be placed in the data/ directory.\n"
            "Database, settings, and logs will NOT be overwritten.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self.data_download_btn.setEnabled(False)
        self.data_dl_progress.setVisible(True)
        self.data_dl_progress.setValue(0)
        self.data_dl_status_label.setText("Starting…")
        w = _ApiWorker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/data/download", timeout=10
        ).json())
        w.finished.connect(lambda r: (
            self._start_data_dl_poll() if not r.get("error")
            else (
                self.data_dl_status_label.setText(f"Error: {r['error']}"),
                self.data_download_btn.setEnabled(True),
            )
        ))
        w.error.connect(lambda e: (
            self.data_dl_status_label.setText(f"Error: {e}"),
            self.data_download_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _start_data_dl_poll(self):
        from PyQt6.QtCore import QTimer
        self._data_dl_poll_timer = QTimer(self)
        self._data_dl_poll_timer.timeout.connect(self._poll_data_dl_status)
        self._data_dl_poll_timer.start(1000)

    def _poll_data_dl_status(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/data/download/status",
                timeout=5
            ).json()
            status = r.get("status", "")
            self.data_dl_progress.setValue(r.get("progress", 0))
            self.data_dl_status_label.setText(r.get("message", ""))
            if status in ("done", "error"):
                self._data_dl_poll_timer.stop()
                self.data_dl_progress.setVisible(False)
                self.data_download_btn.setEnabled(True)
                if status == "done":
                    self._refresh_stats()
                    self.stats_changed.emit()
                    skipped = r.get("files_skipped", [])
                    if skipped:
                        self.data_dl_status_label.setText(
                            r.get("message", "") +
                            f"\nSkipped (protected): {', '.join(skipped)}"
                        )
        except Exception:
            pass
```

**Done when:**
- Entering a URL and clicking "Download & Extract Data" shows a progress bar, fills to 100%, reports file count.
- `losslessbob.db`, `settings.ini`, `scraper.log` are never modified by the extraction.
- A flat ZIP (no root dir) AND a ZIP with a single root directory both extract correctly into `data/`.
- A non-ZIP URL returns a clear error message.
- URL and GitHub repo persist across app restarts.

**Cross-platform notes:**
- `tempfile.TemporaryDirectory()` is cross-platform; cleaned up automatically.
- WIN-09 is implemented. Wrap `dest` with `to_long_path()` from `backend/paths.py` inside `_do_data_download()`.
- No subprocess calls — no console window issues on Windows.
- `Content-Length` may be absent from some servers; progress falls back to KB-only display without a percentage.


---

---

### FEAT-12: Import Behavior Clarification and Overwrite Control ## WONTFIX

**Files:** `backend/importer.py`, `backend/app.py`, `gui/setup_tab.py`
**Dependencies:** None
**New packages:** None

#### What currently happens on import

The importer uses `INSERT OR IGNORE` with a UNIQUE constraint on `(checksum, lb_number)`.
Rules in practice:

- New (checksum, lb_number) pairs: inserted normally.
- Existing (checksum, lb_number) pairs: silently skipped — even if filename, chk_type, or xref differ in the new file.
- Same file re-imported (MD5 hash matches stored import_hash): entire import skipped before any DB work, returns {skipped: True}.

Consequence: corrections in a newer flat file (typo in filename, changed xref flag, new audio format) are silently discarded on reimport. The only current path to apply corrections is a full DB reset + reimport.

---

#### Part A: Add import_mode setting

1. Add "import_mode" to the keys list in GET /api/db/settings in backend/app.py:

```python
keys = [...existing keys..., "import_mode"]
```

2. Modify run_import() in backend/importer.py to accept and honour import_mode:

```python
def run_import(source_path, progress_callback=None, db_path=None, import_mode=None):
    source_path = Path(source_path)
    db_path = db_path or DB_PATH
    if import_mode is None:
        import_mode = get_meta("import_mode", db_path) or "ignore"

    # ... existing hash check and parse logic unchanged ...

    if import_mode == "replace":
        sql = ("INSERT OR REPLACE INTO checksums"
               "(checksum, filename, chk_type, lb_number, xref) VALUES(?,?,?,?,?)")
    else:
        sql = ("INSERT OR IGNORE INTO checksums"
               "(checksum, filename, chk_type, lb_number, xref) VALUES(?,?,?,?,?)")

    main_conn.executemany(sql, [(r["checksum"], r["filename"], r["chk_type"],
                                  r["lb_number"], r["xref"]) for r in rows])
```

Add "import_mode" to the return dict:

```python
    return {
        "new_lb_count": len(new_lbs),
        "total_lb_count": total_lbs,
        "new_lb_numbers": sorted(new_lbs),
        "scrape_queued": len(new_lbs) > 0,
        "import_mode": import_mode,
    }
```

3. In the POST /api/db/import route in backend/app.py, pass import_mode:

```python
            import_mode = database.get_meta("import_mode") or "ignore"
            result = importer.run_import(path, progress_callback=progress_cb,
                                         import_mode=import_mode)
```

---

#### Part B: Force re-import route (clear hash)

Add route in backend/app.py:

```python
    @app.route("/api/db/clear_import_hash", methods=["POST"])
    def clear_import_hash():
        try:
            database.set_meta("import_hash", "")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

---

#### Part C: Setup Tab UI

In gui/setup_tab.py, in the Database group below the existing import button row, add:

```python
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Import mode:"))
        self.import_mode_combo = QComboBox()
        self.import_mode_combo.addItem(
            "Add new records only (INSERT OR IGNORE)", "ignore")
        self.import_mode_combo.addItem(
            "Add new + overwrite changed records (INSERT OR REPLACE)", "replace")
        self.import_mode_combo.currentIndexChanged.connect(self._save_settings)
        mode_row.addWidget(self.import_mode_combo)
        db_layout.addLayout(mode_row)

        force_row = QHBoxLayout()
        self.force_reimport_btn = QPushButton("Clear Import Hash")
        self.force_reimport_btn.setToolTip(
            "Clears the stored file hash so the importer runs even if "
            "the flat file has not changed. Use after switching to Replace mode."
        )
        self.force_reimport_btn.clicked.connect(self._on_clear_import_hash)
        force_row.addWidget(self.force_reimport_btn)
        force_row.addStretch()
        db_layout.addLayout(force_row)
```

In _load_settings(), add:

```python
            mode = data.get("import_mode") or "ignore"
            idx = self.import_mode_combo.findData(mode)
            if idx >= 0:
                self.import_mode_combo.setCurrentIndex(idx)
```

In _save_settings() JSON dict, add:

```python
                    "import_mode": self.import_mode_combo.currentData(),
```

Add slot:

```python
    def _on_clear_import_hash(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/clear_import_hash",
                timeout=5
            ).json()
            self.import_status_label.setText(
                "Import hash cleared. Next import will run regardless of file changes."
                if resp.get("ok") else f"Error: {resp.get('error')}"
            )
        except Exception as e:
            self.import_status_label.setText(f"Error: {e}")
```

**Done when:**
- Default mode is ignore (existing behaviour unchanged).
- Switching to replace and reimporting a flat file with a corrected filename updates the existing row.
- "Clear Import Hash" allows force-reimport of an unchanged file.
- Import result label shows which mode was used.

---

### FEAT-13: Granular Collection Data Management ## COMPLETE

**Files:** `backend/db.py`, `backend/app.py`, `gui/collection_tab.py`, `gui/setup_tab.py`
**Dependencies:** DB-01
**New packages:** None

Note on existing reset: POST /api/db/reset drops only checksums, entries, entry_files, meta.
It does NOT touch my_collection, collection_meta, my_wishlist, integrity_events, or entry_changes.
User data survives a checksum DB reset. The routes below add fine-grained purge control.

---

#### Part A: Purge DB functions

Add to backend/db.py:

```python
def purge_collection(db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM collection_meta")
    conn.execute("DELETE FROM integrity_events")
    conn.execute("DELETE FROM my_collection")
    conn.commit()


def purge_wishlist(db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM my_wishlist")
    conn.commit()


def purge_collection_meta(db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM collection_meta")
    conn.commit()


def purge_integrity_events(db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM integrity_events")
    conn.commit()


def purge_entry_changes(db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM entry_changes")
    conn.commit()


def delete_collection_entries(lb_numbers: list, db_path=None):
    if not lb_numbers:
        return 0
    conn = get_connection(db_path)
    ph = ",".join("?" * len(lb_numbers))
    conn.execute(f"DELETE FROM collection_meta WHERE lb_number IN ({ph})",
                 lb_numbers)
    conn.execute(f"DELETE FROM integrity_events WHERE lb_number IN ({ph})",
                 lb_numbers)
    conn.execute(f"DELETE FROM my_collection WHERE lb_number IN ({ph})",
                 lb_numbers)
    conn.commit()
    return conn.execute("SELECT changes()").fetchone()[0]
```

---

#### Part B: Purge API routes

Add inside create_app() in backend/app.py:

```python
    @app.route("/api/collection/purge", methods=["POST"])
    def collection_purge():
        try:
            scope = (request.get_json() or {}).get("scope", "collection")
            dispatch = {
                "collection":       database.purge_collection,
                "wishlist":         database.purge_wishlist,
                "personal_meta":    database.purge_collection_meta,
                "integrity_events": database.purge_integrity_events,
                "entry_changes":    database.purge_entry_changes,
            }
            if scope not in dispatch:
                return jsonify({"error": f"Unknown scope: {scope}"}), 400
            dispatch[scope]()
            return jsonify({"ok": True, "scope": scope})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/collection/delete_bulk", methods=["POST"])
    def collection_delete_bulk():
        try:
            lb_numbers = (request.get_json() or {}).get("lb_numbers", [])
            if not lb_numbers:
                return jsonify({"error": "lb_numbers required"}), 400
            deleted = database.delete_collection_entries(
                [int(lb) for lb in lb_numbers]
            )
            return jsonify({"ok": True, "deleted": deleted})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

---

#### Part C: Collection Tab enhancements

In gui/collection_tab.py, in _build_collection_panel():

Add Select All / Select None buttons to btn_row:

```python
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self.coll_view.selectAll())
        btn_row.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: self.coll_view.clearSelection())
        btn_row.addWidget(select_none_btn)
```

Replace _on_remove() with the bulk-delete endpoint version:

```python
    def _on_remove(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more rows to remove.")
            return
        lb_numbers = [r["lb_number"] for r in rows]
        if QMessageBox.question(
            self, "Confirm Remove",
            f"Remove {len(lb_numbers)} item(s) from My Collection?\n\n"
            "Personal ratings, tags, and watchdog alerts for these entries "
            "will also be removed. Audio files on disk are NOT deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def call():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/delete_bulk",
                json={"lb_numbers": lb_numbers}, timeout=30,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(lambda r: (
            self.coll_status.setText(
                f"Removed {r.get('deleted', 0)} item(s)."
                if not r.get("error") else f"Error: {r['error']}"
            ),
            self.refresh_collection(),
        ))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()
```

---

#### Part D: Setup Tab purge group

In gui/setup_tab.py, add a "Data Management" group before layout.addStretch():

```python
        purge_group = QGroupBox("Data Management")
        purge_layout = QVBoxLayout(purge_group)
        purge_layout.addWidget(QLabel(
            "Purge operations remove user data only. "
            "The checksum archive is never affected."
        ))

        purge_items = [
            ("My Collection (+ ratings, alerts)",
             "collection"),
            ("Wishlist",
             "wishlist"),
            ("Personal Ratings and Tags only",
             "personal_meta"),
            ("Watchdog Alerts",
             "integrity_events"),
            ("Scrape Diff Changelog",
             "entry_changes"),
        ]
        purge_grid = QGridLayout()
        for i, (label, scope) in enumerate(purge_items):
            lbl = QLabel(label)
            btn = QPushButton("Purge...")
            btn.setFixedWidth(80)
            btn.clicked.connect(
                lambda checked=False, s=scope, l=label: self._on_purge(s, l)
            )
            purge_grid.addWidget(lbl, i, 0)
            purge_grid.addWidget(btn, i, 1)

        purge_layout.addLayout(purge_grid)
        self.purge_status_label = QLabel("")
        purge_layout.addWidget(self.purge_status_label)
        layout.addWidget(purge_group)
```

Add slot:

```python
    def _on_purge(self, scope: str, label: str):
        if QMessageBox.question(
            self, "Confirm Purge",
            f"Permanently delete all: {label}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/purge",
                json={"scope": scope}, timeout=15,
            ).json()
            self.purge_status_label.setText(
                f"Purged: {label}" if resp.get("ok") else f"Error: {resp.get('error')}"
            )
            self.stats_changed.emit()
        except Exception as e:
            self.purge_status_label.setText(f"Error: {e}")
```

**Done when:**
- Each purge button removes only its target with a confirmation.
- Purging My Collection does not affect checksums, entries, entry_files, or meta.
- Bulk delete from collection tab removes collection_meta and integrity_events for those LB numbers.
- Select All + Remove on a 500-entry collection completes without timeout.

---

### FEAT-14: Database Editor Tab ## COMPLETE 

**Files:** `gui/dbedit_tab.py` (new), `gui/main_window.py`, `backend/app.py`
**Dependencies:** DB-01 (`backend/paths.py` already exists — WIN-01 done)
**New packages:** None

---

#### Part A: DB Editor backend routes

Define these constants at module level in backend/app.py (outside create_app()):

```python
_DBEDIT_READONLY = frozenset({"entries_fts"})
_DBEDIT_AUDIT    = frozenset({"entry_changes", "integrity_events"})
_DBEDIT_WARN     = frozenset({"checksums", "entries", "entry_files"})
```

Add routes inside create_app():

```python
    @app.route("/api/dbedit/tables", methods=["GET"])
    def dbedit_tables():
        try:
            conn = database.get_connection()
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('table','view') ORDER BY name"
            ).fetchall()
            result = []
            for r in rows:
                name = r["name"]
                # Skip internal FTS5 shadow tables
                if (name.startswith("sqlite_")
                        or any(name.endswith(sfx) for sfx in
                               ("_fts_data","_fts_idx","_fts_content",
                                "_fts_docsize","_fts_config"))):
                    continue
                try:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM [{name}]"
                    ).fetchone()[0]
                except Exception:
                    count = -1
                result.append({
                    "name": name,
                    "row_count": count,
                    "readonly": name in _DBEDIT_READONLY,
                    "audit":    name in _DBEDIT_AUDIT,
                    "warn":     name in _DBEDIT_WARN,
                })
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/schema", methods=["GET"])
    def dbedit_schema(name):
        try:
            conn = database.get_connection()
            cols = conn.execute(
                f"PRAGMA table_info([{name}])"
            ).fetchall()
            return jsonify([dict(c) for c in cols])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/rows", methods=["GET"])
    def dbedit_rows(name):
        try:
            page     = int(request.args.get("page", 0))
            limit    = min(int(request.args.get("limit", 100)), 500)
            search   = request.args.get("search", "").strip()
            sort_col = request.args.get("sort_col", "")
            sort_dir = "DESC" if request.args.get("sort_dir","asc") == "desc" else "ASC"
            conn     = database.get_connection()

            where, params = "", []
            if search:
                text_cols = [
                    c["name"] for c in
                    conn.execute(f"PRAGMA table_info([{name}])").fetchall()
                    if "TEXT" in (c["type"] or "").upper() or not c["type"]
                ]
                if text_cols:
                    clauses = [f"CAST([{c}] AS TEXT) LIKE ?" for c in text_cols]
                    where  = "WHERE " + " OR ".join(clauses)
                    params = [f"%{search}%"] * len(text_cols)

            order = f"ORDER BY [{sort_col}] {sort_dir}" if sort_col else ""
            total = conn.execute(
                f"SELECT COUNT(*) FROM [{name}] {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT rowid, * FROM [{name}] {where} {order} LIMIT ? OFFSET ?",
                params + [limit, page * limit]
            ).fetchall()

            cols = [d[0] for d in rows[0].description] if rows else                    ["rowid"] + [c["name"] for c in
                    conn.execute(f"PRAGMA table_info([{name}])").fetchall()]
            return jsonify({
                "columns": cols,
                "rows":    [list(r) for r in rows],
                "total":   total,
                "page":    page,
                "limit":   limit,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/row", methods=["PATCH"])
    def dbedit_update_row(name):
        if name in _DBEDIT_READONLY or name in _DBEDIT_AUDIT:
            return jsonify({"error": f"Table {name!r} is not editable"}), 403
        try:
            data    = request.get_json() or {}
            rowid   = data.get("rowid")
            updates = data.get("updates", {})
            if rowid is None or not updates:
                return jsonify({"error": "rowid and updates required"}), 400
            conn  = database.get_connection()
            valid = {c["name"] for c in
                     conn.execute(f"PRAGMA table_info([{name}])").fetchall()}
            bad = [k for k in updates if k not in valid]
            if bad:
                return jsonify({"error": f"Unknown columns: {bad}"}), 400
            set_clause = ", ".join(f"[{k}]=?" for k in updates)
            conn.execute(
                f"UPDATE [{name}] SET {set_clause} WHERE rowid=?",
                list(updates.values()) + [rowid]
            )
            conn.commit()
            return jsonify({"ok": True,
                            "affected": conn.execute("SELECT changes()").fetchone()[0]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/rows", methods=["DELETE"])
    def dbedit_delete_rows(name):
        if name in _DBEDIT_READONLY:
            return jsonify({"error": f"Table {name!r} cannot be modified"}), 403
        try:
            rowids = (request.get_json() or {}).get("rowids", [])
            if not rowids:
                return jsonify({"error": "rowids list required"}), 400
            conn = database.get_connection()
            ph   = ",".join("?" * len(rowids))
            conn.execute(f"DELETE FROM [{name}] WHERE rowid IN ({ph})", rowids)
            conn.commit()
            return jsonify({"ok": True,
                            "deleted": conn.execute("SELECT changes()").fetchone()[0]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dbedit/table/<name>/export", methods=["GET"])
    def dbedit_export(name):
        try:
            import csv, io
            conn = database.get_connection()
            rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
            buf  = io.StringIO()
            if rows:
                writer = csv.writer(buf)
                writer.writerow(rows[0].keys())
                writer.writerows(rows)
            from flask import Response
            return Response(
                buf.getvalue(), mimetype="text/csv",
                headers={"Content-Disposition":
                         f"attachment; filename={name}.csv"}
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500
```

---

#### Part B: DB Editor GUI — create gui/dbedit_tab.py

The complete file. Implements: table browser, paginated row view, inline cell editing
with dirty-state tracking, row deletion, context menu, and CSV export.

```python
import requests
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QAction
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QMenu, QComboBox, QApplication,
)

_C_DIRTY  = QColor("#fffbe6")
_C_WARN   = QColor("#fff0f0")
_C_AUDIT  = QColor("#f0f0ff")
_C_RDONLY = QColor("#f4f4f4")


class _Worker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)
    def __init__(self, fn):
        super().__init__()
        self._fn = fn
    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


class DbEditTab(QWidget):

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port       = flask_port
        self._table_meta: dict = {}
        self._current_table   = ""
        self._schema: list    = []
        self._columns: list   = []
        self._page            = 0
        self._limit           = 100
        self._total           = 0
        self._dirty: dict     = {}    # (row, col) -> new_value
        self._rowids: list    = []    # rowid per displayed row
        self._workers: list   = []
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: table list
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.addWidget(QLabel("Tables"))
        self.table_list = QListWidget()
        self.table_list.setFixedWidth(190)
        self.table_list.currentItemChanged.connect(self._on_table_selected)
        ll.addWidget(self.table_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_tables)
        ll.addWidget(refresh_btn)
        splitter.addWidget(left)

        # Right panel: data view
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        # Toolbar row
        toolbar = QHBoxLayout()
        self.table_label = QLabel("Select a table")
        f = self.table_label.font()
        f.setBold(True)
        self.table_label.setFont(f)
        toolbar.addWidget(self.table_label)
        toolbar.addStretch()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search text columns...")
        self.search_input.setFixedWidth(220)
        self.search_input.returnPressed.connect(self._do_search)
        toolbar.addWidget(self.search_input)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        toolbar.addWidget(search_btn)
        rl.addLayout(toolbar)

        # Schema strip
        self.schema_label = QLabel("")
        self.schema_label.setWordWrap(True)
        self.schema_label.setStyleSheet("font-size:10px; color:#888;")
        rl.addWidget(self.schema_label)

        # Data table
        self.data_table = QTableWidget()
        self.data_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.data_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_context)
        self.data_table.itemChanged.connect(self._on_cell_changed)
        rl.addWidget(self.data_table)

        # Pagination row
        page_row = QHBoxLayout()
        self.prev_btn = QPushButton("< Prev")
        self.prev_btn.setFixedWidth(70)
        self.prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self.prev_btn)
        self.page_label = QLabel("")
        page_row.addWidget(self.page_label)
        self.next_btn = QPushButton("Next >")
        self.next_btn.setFixedWidth(70)
        self.next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self.next_btn)
        page_row.addStretch()
        page_row.addWidget(QLabel("Rows per page:"))
        self.limit_combo = QComboBox()
        for v in [50, 100, 200, 500]:
            self.limit_combo.addItem(str(v), v)
        self.limit_combo.setCurrentIndex(1)
        self.limit_combo.currentIndexChanged.connect(self._on_limit_changed)
        page_row.addWidget(self.limit_combo)
        rl.addLayout(page_row)

        # Action row
        act_row = QHBoxLayout()
        self.save_btn = QPushButton("Commit Changes")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_commit)
        act_row.addWidget(self.save_btn)
        self.discard_btn = QPushButton("Discard Changes")
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self._on_discard)
        act_row.addWidget(self.discard_btn)
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete)
        act_row.addWidget(self.delete_btn)
        self.export_btn = QPushButton("Export CSV...")
        self.export_btn.clicked.connect(self._on_export)
        act_row.addWidget(self.export_btn)
        act_row.addStretch()
        self.status_label = QLabel("")
        act_row.addWidget(self.status_label)
        rl.addLayout(act_row)

        splitter.addWidget(right)
        splitter.setSizes([190, 800])
        layout.addWidget(splitter)

    # Table list

    def load_tables(self):
        w = _Worker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/dbedit/tables",
            timeout=10).json())
        w.finished.connect(self._on_tables_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_tables_loaded(self, data):
        self.table_list.clear()
        self._table_meta = {}
        if not isinstance(data, list):
            return
        for t in data:
            name = t["name"]
            self._table_meta[name] = t
            label = f"{name}  ({t['row_count']:,})" if t['row_count'] >= 0                     else name
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if t.get("readonly"):
                item.setForeground(QColor("#888"))
                item.setToolTip("Read-only virtual table")
            elif t.get("warn"):
                item.setForeground(QColor("#c0392b"))
                item.setToolTip("Core archive — deletions affect lookup results")
            elif t.get("audit"):
                item.setForeground(QColor("#2980b9"))
                item.setToolTip("Audit log — delete only, no editing")
            self.table_list.addItem(item)

    def _on_table_selected(self, current, _previous):
        if not current:
            return
        self._current_table = current.data(Qt.ItemDataRole.UserRole)
        self._page = 0
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.search_input.clear()
        self._load_schema()
        self._load_rows()

    # Schema

    def _load_schema(self):
        if not self._current_table:
            return
        name = self._current_table
        w = _Worker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}"
            f"/api/dbedit/table/{name}/schema",
            timeout=5).json())
        w.finished.connect(self._on_schema_loaded)
        self._workers.append(w)
        w.start()

    def _on_schema_loaded(self, data):
        if not isinstance(data, list):
            return
        self._schema = data
        parts = []
        for c in data:
            pk = " [PK]" if c.get("pk") else ""
            nn = " NOT NULL" if c.get("notnull") else ""
            parts.append(f"{c['name']} {c.get('type','')}{pk}{nn}")
        self.schema_label.setText("  |  ".join(parts))

    # Row data

    def _do_search(self):
        self._page = 0
        self._load_rows()

    def _load_rows(self):
        if not self._current_table:
            return
        name   = self._current_table
        search = self.search_input.text().strip()
        url    = (f"http://127.0.0.1:{self.flask_port}"
                  f"/api/dbedit/table/{name}/rows"
                  f"?page={self._page}&limit={self._limit}"
                  + (f"&search={search}" if search else ""))
        self.status_label.setText("Loading...")
        w = _Worker(lambda: requests.get(url, timeout=20).json())
        w.finished.connect(self._on_rows_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_rows_loaded(self, data):
        if "error" in data:
            self.status_label.setText(f"Error: {data['error']}")
            return

        self._total   = data["total"]
        self._columns = data["columns"]
        rows          = data["rows"]
        meta          = self._table_meta.get(self._current_table, {})
        editable      = not meta.get("readonly") and not meta.get("audit")

        self.data_table.blockSignals(True)
        self.data_table.clearContents()
        self.data_table.setRowCount(len(rows))
        self.data_table.setColumnCount(len(self._columns))
        self.data_table.setHorizontalHeaderLabels(self._columns)

        self._rowids = []
        for r_idx, row in enumerate(rows):
            self._rowids.append(row[0])
            for c_idx, val in enumerate(row):
                text = "" if val is None else str(val)
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, val)
                not_editable = (c_idx == 0 or not editable)
                if not_editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c_idx == 0:
                    item.setForeground(QColor("#aaa"))
                if meta.get("warn"):
                    item.setBackground(_C_WARN)
                elif meta.get("audit"):
                    item.setBackground(_C_AUDIT)
                elif meta.get("readonly"):
                    item.setBackground(_C_RDONLY)
                self.data_table.setItem(r_idx, c_idx, item)

        self.data_table.blockSignals(False)
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)

        pages = max(1, -(-self._total // self._limit))
        self.page_label.setText(
            f"Page {self._page + 1}/{pages}  ({self._total:,} rows total)"
        )
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)

        lbl = self._current_table
        if meta.get("readonly"): lbl += " [read-only]"
        if meta.get("audit"):    lbl += " [audit: delete only]"
        if meta.get("warn"):     lbl += "  WARNING: core archive table"
        self.table_label.setText(lbl)
        self.status_label.setText(f"{self._total:,} rows")

    # Pagination

    def _on_limit_changed(self):
        self._limit = self.limit_combo.currentData()
        self._page  = 0
        self._load_rows()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._load_rows()

    def _next_page(self):
        pages = max(1, -(-self._total // self._limit))
        if self._page < pages - 1:
            self._page += 1
            self._load_rows()

    # Inline editing

    def _on_cell_changed(self, item):
        row, col = item.row(), item.column()
        if col == 0:
            return
        original = item.data(Qt.ItemDataRole.UserRole)
        new_val  = item.text()
        if str("" if original is None else original) != new_val:
            self._dirty[(row, col)] = new_val
            item.setBackground(_C_DIRTY)
        else:
            self._dirty.pop((row, col), None)
            item.setBackground(QColor("white"))
        has = bool(self._dirty)
        self.save_btn.setEnabled(has)
        self.discard_btn.setEnabled(has)

    def _on_commit(self):
        if not self._dirty:
            return
        by_row: dict = {}
        for (r, c), val in self._dirty.items():
            by_row.setdefault(r, {})[self._columns[c]] = val

        errors = []
        for r_idx, updates in by_row.items():
            rowid = self._rowids[r_idx]
            name  = self._current_table
            try:
                resp = requests.patch(
                    f"http://127.0.0.1:{self.flask_port}"
                    f"/api/dbedit/table/{name}/row",
                    json={"rowid": rowid, "updates": updates},
                    timeout=10,
                ).json()
                if resp.get("error"):
                    errors.append(f"rowid {rowid}: {resp['error']}")
            except Exception as e:
                errors.append(str(e))

        if errors:
            self.status_label.setText(f"Errors: {errors[0]}")
        else:
            self.status_label.setText(f"Committed {len(by_row)} row(s).")
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self._load_rows()

    def _on_discard(self):
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self._load_rows()

    # Delete

    def _on_delete(self):
        selected = list({idx.row() for idx in
                         self.data_table.selectedIndexes()})
        if not selected:
            self.status_label.setText("Select rows to delete.")
            return
        meta = self._table_meta.get(self._current_table, {})
        if meta.get("readonly"):
            self.status_label.setText("Cannot delete from a read-only table.")
            return

        extra = ""
        if meta.get("warn"):
            extra = ("\n\nWARNING: This is a core archive table. "
                     "Deleting checksums or entries affects lookup results.")

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(selected)} row(s) from '{self._current_table}'?{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        rowids = [self._rowids[r] for r in selected]
        name   = self._current_table
        try:
            resp = requests.delete(
                f"http://127.0.0.1:{self.flask_port}"
                f"/api/dbedit/table/{name}/rows",
                json={"rowids": rowids}, timeout=15,
            ).json()
            if resp.get("error"):
                self.status_label.setText(f"Error: {resp['error']}")
            else:
                self.status_label.setText(f"Deleted {resp.get('deleted',0)} row(s).")
                self._load_rows()
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    # Context menu

    def _on_context(self, pos):
        menu = QMenu(self)
        copy_act = QAction("Copy Cell Value", self)
        copy_act.triggered.connect(self._copy_cell)
        menu.addAction(copy_act)
        del_act = QAction("Delete Selected Row(s)", self)
        del_act.triggered.connect(self._on_delete)
        menu.addAction(del_act)
        menu.exec(self.data_table.mapToGlobal(pos))

    def _copy_cell(self):
        item = self.data_table.currentItem()
        if item:
            QApplication.clipboard().setText(item.text())

    # CSV export

    def _on_export(self):
        if not self._current_table:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            f"{self._current_table}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        name = self._current_table
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}"
                f"/api/dbedit/table/{name}/export",
                timeout=60,
            )
            with open(path, "wb") as fh:
                fh.write(resp.content)
            self.status_label.setText(f"Exported to {Path(path).name}")
        except Exception as e:
            self.status_label.setText(f"Export error: {e}")
```

---

#### Part C: Register in main window

In gui/main_window.py, inside _build_tabs():

```python
        from gui.dbedit_tab import DbEditTab
        self.dbedit_tab = DbEditTab(self.flask_port)
        self.tabs.addTab(self.dbedit_tab, "DB Editor")
```

Lazy-load the table list on first activation. If _on_tab_changed does not yet exist, add:

```python
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if widget is self.dbedit_tab and self.dbedit_tab.table_list.count() == 0:
            self.dbedit_tab.load_tables()
```

**Done when:**
- DB Editor tab shows all tables in the left list with row counts.
- Clicking a table loads paginated rows. The rowid column is always first and non-editable.
- Double-clicking a cell enters edit mode; the cell turns yellow. Commit Changes patches all dirty rows.
- Discard Changes reloads without saving.
- Select rows + Delete Selected shows a confirmation. Core archive tables show an extra warning.
- entries_fts is listed as read-only; all edit/delete buttons do nothing for it.
- Search filters rows across all TEXT columns.
- Export CSV saves the full table (not just the current page) to a file.
- Editing an entry in the entries table via the editor correctly keeps entries_fts in sync because the UPDATE fires the existing triggers.

**Security:**
- No DDL is exposed. Only SELECT, PATCH by rowid, DELETE by rowid.
- Column names in PATCH are validated against PRAGMA table_info before the UPDATE executes, preventing injection via column name.
- entries_fts and its shadow tables are blocked from all writes.


---

## APPENDIX: Implementation Order

Execute in this sequence to minimize rework:

**Note: All WIN tasks (WIN-01 through WIN-17) are already implemented.**
`backend/paths.py`, `gui/platform_utils.py`, and all related files are in place.
No feature task needs to wait on a WIN prerequisite.

```
DB-01 → DB-02 → DB-03 → DB-04 → DB-05 → DB-06 → DB-07 → DB-08
FEAT-01 (no dependencies)
FEAT-02 (after DB-04)
FEAT-03 (after DB-01)
FEAT-04 (after FEAT-03)
FEAT-05 (after FEAT-04)
FEAT-06 (after DB-01)
FEAT-07 (after DB-01)
FEAT-08 (after DB-04)
FEAT-09 (after DB-01)
FEAT-10 (backend/paths.py already exists — no WIN blocker)
FEAT-11 (backend/paths.py already exists — no WIN blocker)
FEAT-12 (no dependencies — standalone)
FEAT-13 (after DB-01)
FEAT-14 (after DB-01 — backend/paths.py already exists)
DEFERRED-01 through DEFERRED-03 last
```

### Amendment to FEAT-10 — GitHub Updater Windows Notes

**No code changes required beyond what is already in the task.** The following behaviors are already handled:

- `backend/updater.py` applies `CREATE_NO_WINDOW` on Windows subprocess spawn.
- Frozen Windows builds (`sys.frozen=True, sys.platform=="win32"`) raise `RuntimeError` with a manual restart message — no crash.
- `_do_update()` uses `open(dest, "wb")` for all file writes — wrap `dest` with `to_long_path()` from `backend/paths.py` (WIN-09 already implemented).
- GitHub API calls use `requests` with `timeout=10` — no blocking main thread issues.
- The `VERSION` file uses `read_text(encoding="utf-8")` — safe on all platforms.

**Additional note for PyInstaller builds:** The updater downloads and replaces `.py` source files. A frozen build does not execute `.py` files — the update will succeed but have no effect until the app is rebuilt. Consider disabling the "Apply Update" button when `getattr(sys, 'frozen', False)` is True and showing an informational message: "Download the latest release from GitHub to update the packaged version."

---

### Amendment to FEAT-11 — Remote Data ZIP Windows Notes

**No code changes required.** All file I/O uses `pathlib` and `open()` which are cross-platform. One optional enhancement:

WIN-09 is already implemented. Apply long-path support in `_do_data_download()`:

```python
# In _do_data_download(), replace:
dest = DATA_DIR / rel_path
# With:
from backend.paths import to_long_path
dest = to_long_path(DATA_DIR / rel_path)
```

`tempfile.TemporaryDirectory()` uses the OS temp dir (`%TEMP%` on Windows, `/tmp` on Linux) — always writable and cleaned up automatically even if the download fails.

---

## APPENDIX: Testing Checklist Per Task

After each task, verify:

- [ ] App starts without import errors
- [ ] `/api/db/stats` returns valid JSON
- [ ] `/api/lookup` with a known checksum returns the correct LB number
- [ ] DB file is not corrupted (`sqlite3 data/losslessbob.db "PRAGMA integrity_check"` returns `ok`)
- [ ] No `sqlite3.OperationalError: database is locked` under concurrent GUI use

After DB-05 (FTS5):
- [ ] `PRAGMA integrity_check` still returns `ok`
- [ ] `SELECT COUNT(*) FROM entries_fts` equals `SELECT COUNT(*) FROM entries`
- [ ] Search for a known venue name returns correct results

After FEAT-07 (exports):
- [ ] HTML export opens in Firefox/Chrome without errors
- [ ] M3U opens in VLC and shows correct track metadata

---

## APPENDIX: Cross-Platform Amendments

**Status: WIN-01 through WIN-17 are all implemented. `backend/paths.py` and `gui/platform_utils.py` exist.**

The amendments below are code changes needed inside each *feature task* (DB-xx, FEAT-xx) to
make that feature work correctly cross-platform. They are independent of the WIN tasks and
still need to be applied when each feature is implemented. Tasks not listed here
(DB-03, DB-04, DB-06, DB-07, DB-08, FEAT-02, FEAT-03, FEAT-04, FEAT-05, all DEFERRED) require
no cross-platform changes.

**Quick reference — already-available helpers to use in new code:**
- Path resolution: `from backend.paths import APP_ROOT, DATA_DIR, DB_PATH, to_long_path`
- File/folder open: `from gui.platform_utils import open_file, open_folder, open_url`
- Drop URL fix: `from gui.platform_utils import url_to_local_path`
- Subprocess flags: `from gui.platform_utils import _subprocess_flags`

---

### Amendment to DB-01 and DB-02 — SQLite Connection Timeout

**Issue:** Both tasks specify `sqlite3.connect(path, check_same_thread=False)` with no timeout. On Windows, SQLite raises `OperationalError: database is locked` immediately (not after a wait) when a second thread tries to write. This crashes any concurrent scrape+read sequence.

**Change in DB-01** — replace the `sqlite3.connect` line:
```python
# Before:
conn = sqlite3.connect(str(path), check_same_thread=False)
# After:
conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
```

**Change in DB-02** — same substitution inside the pool `if path not in cache:` block:
```python
# Before:
conn = sqlite3.connect(path, check_same_thread=False)
# After:
conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
```

Add `PRAGMA busy_timeout=30000` after the other PRAGMAs in both versions:
```python
conn.execute("PRAGMA busy_timeout=30000")  # 30s retry on locked DB
```

---

### Amendment to DB-01 and DB-02 — `mmap_size` Guard for Network and Cloud-Synced Paths

**Issue:** `PRAGMA mmap_size=536870912` (512 MB) silently fails or raises `OSError` on Windows when the DB is on a UNC network path (`\\server\share\...`) or inside a cloud-sync folder (OneDrive, Dropbox, Google Drive File Stream). Windows does not support memory-mapped I/O on remote filesystems.

**Change:** Wrap the `mmap_size` PRAGMA in a try/except in both DB-01 and DB-02's `get_connection()`:

```python
# Replace:
conn.execute("PRAGMA mmap_size=536870912")
# With:
try:
    conn.execute("PRAGMA mmap_size=536870912")
except Exception:
    pass  # Silently skip on network drives and cloud-sync paths (Windows)
```

---

### Amendment to DB-05 — FTS5 Availability Check

**Issue:** `SCHEMA_SQL` includes `CREATE VIRTUAL TABLE ... USING fts5(...)`. FTS5 is compiled into Python's `sqlite3` on CPython official builds, but is absent from the Windows embeddable distribution, some Anaconda/Miniconda builds, and any custom Python compiled without it. `init_db()` would raise `sqlite3.OperationalError: no such module: fts5` at startup, preventing the app from running.

**Change:** In `init_db()` in `db.py`, split the FTS5 DDL out of `SCHEMA_SQL` into a separate guarded block. Remove the FTS5 `CREATE VIRTUAL TABLE` and all three triggers from `SCHEMA_SQL`. After the `conn.executescript(SCHEMA_SQL)` call, add:

```python
    # Attempt FTS5 setup — gracefully disabled if SQLite was compiled without it
    global _FTS5_AVAILABLE
    try:
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                description, setlist, location, date_str,
                content='entries', content_rowid='lb_number',
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
        """)
        _FTS5_AVAILABLE = True
    except Exception:
        _FTS5_AVAILABLE = False  # App continues; search falls back to LIKE queries
```

Add at module level in `db.py`:
```python
_FTS5_AVAILABLE: bool = False  # Set by init_db()
```

In `search_entries()`, guard the FTS branch:
```python
    if query and _FTS5_AVAILABLE:
        # ... existing FTS5 path ...
    else:
        # ... existing LIKE fallback path ...
```

The existing `try/except` fallback in `search_entries()` already handles FTS5 query syntax errors; this change handles the case where FTS5 is entirely absent.

---

### Amendment to FEAT-01 — CLI Cross-Platform Fixes

**Three issues:**

**1. Remove `chmod +x cli.py`** — `chmod` does not exist on Windows. Replace step 2:
```
# Remove: 2. Make executable: chmod +x cli.py
# Replace with:
2. On Linux/macOS, optionally make executable: chmod +x cli.py
   On Windows, invoke as: python cli.py <command>
   On Windows with the Python Launcher: py cli.py <command>
```

**2. Replace `time.sleep(1.2)` with port-poll** — same race condition that WIN-02 fixed in `main.py`. In the `main()` function of `cli.py`, replace:
```python
        import time; time.sleep(1.2)  # Wait for Flask to bind
```
With:
```python
        import socket, time
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
```

**3. Use Waitress on Windows in `_start_flask()`** — the CLI uses the Flask dev server which has the same Windows port-release issues as the GUI (WIN-06 is already applied to the main app — apply the same pattern here). Replace `_start_flask()`:
```python
def _start_flask(port):
    import sys
    from backend.app import create_app
    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    flask_app = create_app()
    if sys.platform == "win32":
        try:
            from waitress import serve as _serve
            _serve(flask_app, host="127.0.0.1", port=port, threads=4)
        except ImportError:
            flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    else:
        flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
```

---

### Amendment to FEAT-06 — `info.txt` Line Endings

**Issue:** `out_path.write_text(content, encoding="utf-8")` uses Python's default text mode, which writes LF (`\n`) line endings on all platforms. Windows Notepad prior to the Win10 21H2 update (and many older text editors) displays LF-only files as a single run-on line.

**Change:** Replace the write call in the `/api/collection/<lb>/generate_info` route:
```python
# Before:
out_path.write_text(content, encoding="utf-8")
# After:
with open(out_path, "w", encoding="utf-8", newline="\r\n") as fh:
    fh.write(content)
```

Using `\r\n` unconditionally is correct here — `info.txt` is a data file for collectors, most of whom are on Windows, and CRLF is valid on Linux and macOS as well.

---

### Amendment to FEAT-07 — M3U Path Separators

**Issue:** `lines.append(str(f))` in the M3U route produces Windows-style paths (`C:\Users\Bob\Music\track.flac`). The M3U standard uses forward slashes or `file:///` URIs. Players on macOS and Linux reading a Windows-generated M3U will fail to resolve the paths. VLC on Windows handles both, but cross-platform players do not.

**Change:** Replace `lines.append(str(f))` with:
```python
# Before:
lines.append(str(f))
# After:
lines.append(f.as_posix())   # Always forward slashes: C:/Users/Bob/Music/track.flac
```

`Path.as_posix()` returns forward-slash paths on all platforms including Windows (`C:/Users/...`). This format is accepted by VLC, foobar2000, Winamp, and standard Unix players.

Also use CRLF line endings in the M3U response for maximum Windows player compatibility:
```python
# Before:
return Response("\n".join(lines), mimetype="audio/x-mpegurl", ...)
# After:
return Response("\r\n".join(lines), mimetype="audio/x-mpegurl", ...)
```

---

### Amendment to FEAT-08 — Wrong Filter Attribute Name (All Platforms)

**Issue:** The `_on_scan_tree` code references `self._filter_cb.isChecked()`. This attribute does not exist in `LookupTab`. The actual filter state is stored as a boolean: `self._filter_mychecksums`. This raises `AttributeError` on all platforms, not just Windows.

**Change** in `_on_scan_tree()`:
```python
# Before:
if "_mychecksums" in p.name.lower() and self._filter_cb.isChecked():
# After:
if "_mychecksums" in p.name.lower() and self._filter_mychecksums:
```

---

### Amendment to FEAT-09 — Watchdog Windows Compatibility

**Three issues in `start_collection_watcher()` in `backend/scheduler.py`:**

**1. Use platform-aware Observer** (WIN-13 is already applied to the main file watcher in `scheduler.py` — apply the same pattern here for the collection watcher):
```python
# Before:
    _collection_observer = Observer()
# After:
    import sys
    if sys.platform == "win32":
        try:
            from watchdog.observers.winapi import WindowsApiObserver
            _collection_observer = WindowsApiObserver()
        except ImportError:
            from watchdog.observers import Observer
            _collection_observer = Observer()
    else:
        from watchdog.observers import Observer
        _collection_observer = Observer()
```

**2. Set daemon + join before stop** — prevents the observer thread from blocking process exit on Windows, and avoids COM deregistration errors on restart:
```python
# Before:
    if _collection_observer:
        _collection_observer.stop()
    _collection_observer = <new observer>
    ...
    _collection_observer.start()
# After:
    if _collection_observer:
        _collection_observer.stop()
        _collection_observer.join(timeout=5)  # Wait for clean COM deregistration
    _collection_observer = <new observer>
    _collection_observer.daemon = True       # Don't block process exit
    ...
    _collection_observer.start()
```

**3. Filter Windows system files in `_CollectionEventHandler`** — Windows Explorer auto-creates `Thumbs.db` and `desktop.ini` in every browsed folder, generating spurious integrity events:
```python
class _CollectionEventHandler(FileSystemEventHandler):
    _IGNORE_NAMES = frozenset({
        "thumbs.db", "desktop.ini", ".ds_store",
    })

    def _should_ignore(self, path: str) -> bool:
        name = Path(path).name.lower()
        return name in self._IGNORE_NAMES or name.startswith("~$")

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "deleted", f"Deleted: {event.src_path}"
        )

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "moved", f"Moved: {event.src_path} -> {event.dest_path}"
        )
```

`~$` prefix filters Microsoft Office lock files (e.g. `~$document.docx`) which are created transiently in any folder a user has open in Office.

---

## APPENDIX: Cross-Platform Testing Additions

Add these to the per-task checklist when testing on Windows:

**DB-01/DB-02:**
- [ ] No `OperationalError: database is locked` when scraping while GUI polls status
- [ ] App starts correctly when `data/losslessbob.db` is on a network drive (mmap_size silently skipped)

**DB-05:**
- [ ] On a Python build without FTS5: app starts, search returns results via LIKE fallback, no crash at startup
- [ ] `_FTS5_AVAILABLE` is `True` on standard CPython Windows build

**FEAT-01:**
- [ ] `python cli.py stats` works on Windows Command Prompt and PowerShell
- [ ] No port-in-use error on second invocation within 10 seconds of first

**FEAT-06:**
- [ ] Generated `info.txt` opens in Windows Notepad with correct line breaks (not one long line)

**FEAT-07:**
- [ ] Generated `.m3u` file opens correctly in VLC on Windows, macOS, and Linux
- [ ] File paths in M3U use forward slashes

**FEAT-08:**
- [ ] "Scan Tree…" button works without `AttributeError` when `_filter_mychecksums` is both `True` and `False`

**FEAT-09:**
- [ ] Creating a file in a watched collection folder generates an integrity event within 10 seconds on Windows
- [ ] Deleting `Thumbs.db` from a watched folder does NOT generate an integrity event
- [ ] App exits cleanly (no hang) when collection watcher is active
