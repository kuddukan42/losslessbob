# CC_PIPELINE_FILE.md — Pipeline Step 5: File into Collection

**Feature:** FEAT-XX — Pipeline filing step (move/copy folder to collection mount + register in `my_collection`)  
**Scope:** New DB tables, new backend module, new API routes, new Setup UI section, pipeline integration  
**Principle:** Strictly non-destructive until the move/copy succeeds. All pre-flight checks run before any filesystem operation. No partial state left on failure.

---

## Overview

Step 5 is the final pipeline stage. After verify → lookup → rename → lbdir, the folder is archive-clean. Filing physically moves (or copies) the folder to the correct location on disk — determined by the concert year — and registers it in `my_collection`.

Users organise their collection across multiple drives and subdirectories. A routing table maps each year (1958–2026) to a named mount and a relative sub-path. The year is always extractable from `date_str` (format `M/D/YY` or `M/D/YYYY`; `xx` is valid for day/month but the year component is always a 2-digit or 4-digit number).

---

## 1. Database Schema

Add to `db.py` `_SCHEMA` string. Both tables are **USER tables** — add both to the `USER_TABLES` set, never export in master snapshot.

```sql
-- Named root paths (drives, NAS shares, etc.)
CREATE TABLE IF NOT EXISTS collection_mounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL UNIQUE,        -- e.g. "DYLAN1", "NAS-EXT"
    root_path  TEXT NOT NULL,               -- "/mnt/dylan1" or "D:\Dylan"
    notes      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- One row per year — simple, no range logic, O(1) lookup
CREATE TABLE IF NOT EXISTS collection_routes (
    year      INTEGER PRIMARY KEY,          -- 4-digit: 1958–2026 (or any year)
    mount_id  INTEGER NOT NULL
              REFERENCES collection_mounts(id) ON DELETE RESTRICT,
    sub_path  TEXT NOT NULL DEFAULT ''
    -- Destination: Path(mount.root_path) / sub_path / folder_final_name
    -- sub_path="" → root_path/folder_name (flat)
    -- sub_path="1966" → root_path/1966/folder_name
    -- sub_path="1960s/1966" → root_path/1960s/1966/folder_name
);
CREATE INDEX IF NOT EXISTS idx_routes_mount ON collection_routes(mount_id);
```

Add migration guards in `_migrate_schema()`:

```python
# collection_mounts
if not conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='collection_mounts'"
).fetchone():
    conn.execute("""CREATE TABLE collection_mounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL UNIQUE,
        root_path TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

# collection_routes
if not conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='collection_routes'"
).fetchone():
    conn.execute("""CREATE TABLE collection_routes (
        year INTEGER PRIMARY KEY,
        mount_id INTEGER NOT NULL
            REFERENCES collection_mounts(id) ON DELETE RESTRICT,
        sub_path TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_routes_mount ON collection_routes(mount_id)"
    )
```

Add `"pipeline_file_mode"` to the `keys` list in `db_settings()` GET handler in `app.py`.  
Default value when not set: `"move"`. Valid values: `"move"` | `"copy"`.

---

## 2. New Backend Module: `backend/filer.py`

Create `backend/filer.py`. This module owns all filing logic.

```python
"""backend/filer.py — Pipeline step 5: file a folder into the collection."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from backend import db as database

logger = logging.getLogger(__name__)


# ── Year extraction ────────────────────────────────────────────────────────────

def year_from_date_str(date_str: str) -> int | None:
    """Extract 4-digit year from entries.date_str (M/D/YY or M/D/YYYY).

    The day and month components may be 'xx'; only the year component matters.
    Returns None only if date_str is empty, missing, or the year field is
    non-numeric (should not occur in practice).

    2-digit cutoff: >= 49 → 19xx, else 20xx  (matches existing project convention).
    """
    if not date_str:
        return None
    parts = date_str.split('/')
    if len(parts) != 3:
        return None
    y = parts[2].strip()
    if not y.isdigit():
        return None
    y_int = int(y)
    if y_int < 100:
        y_int = 1900 + y_int if y_int >= 49 else 2000 + y_int
    return y_int


# ── Route resolution ───────────────────────────────────────────────────────────

def resolve_destination(folder_path: str, db_path=None) -> dict:
    """Resolve the filing destination for a folder.

    Looks up the LB number from my_collection (the folder must have been
    registered during a prior pipeline run — lookup step populates lb_number
    in pipeline state; the rename step writes disk_path if already in
    collection, but the folder is NOT yet in my_collection at this point).

    For pipeline use, lb_number and date_str are passed in from pipeline state
    rather than read from DB here. Call resolve_destination_for_lb() instead.

    This entry point is for direct API use where only folder_path is known.
    It reads lb_number from the pipeline state cache or returns an error.
    """
    # For direct API calls the caller must supply lb_number + date_str.
    # This function is a thin wrapper; see resolve_destination_for_lb().
    raise NotImplementedError(
        "Call resolve_destination_for_lb(lb_number, folder_path, db_path) directly."
    )


def resolve_destination_for_lb(
    lb_number: int,
    folder_path: str,
    db_path=None,
) -> dict:
    """Resolve the filing destination for a known LB entry.

    Returns a dict:
        ok (bool)
        year (int | None)
        mount_id (int | None)
        mount_label (str)
        mount_root (str)
        sub_path (str)
        dest_parent (str)   — absolute path; folder will land at dest_parent/folder_name
        dest (str)          — full absolute destination path
        error (str | None)  — human-readable; set when ok=False
        error_code (str)    — machine-readable: "no_date" | "no_route" | "mount_offline"
                               | "dest_exists" | "db_error"
    """
    folder = Path(folder_path)
    folder_name = folder.name

    # 1. Get date_str from entries
    try:
        entry_data = database.get_entry(lb_number, db_path=db_path)
    except Exception as exc:
        return _err("db_error", f"DB error reading LB-{lb_number:05d}: {exc}")

    if not entry_data:
        return _err("db_error", f"LB-{lb_number:05d} not found in entries")

    date_str = (entry_data.get("entry") or {}).get("date_str") or ""

    # 2. Resolve year
    year = year_from_date_str(date_str)
    if year is None:
        return _err(
            "no_date",
            f"Cannot determine year from date_str '{date_str}' — "
            "no route can be selected",
        )

    # 3. Find route for year
    try:
        with database.get_connection(db_path) as conn:
            route = conn.execute(
                """SELECT r.year, r.mount_id, r.sub_path,
                          m.label, m.root_path
                   FROM collection_routes r
                   JOIN collection_mounts m ON m.id = r.mount_id
                   WHERE r.year = ?""",
                (year,),
            ).fetchone()
    except Exception as exc:
        return _err("db_error", f"DB error reading routes: {exc}")

    if route is None:
        return _err(
            "no_route",
            f"No route configured for year {year} — "
            "add one in Settings → Mounts & Routes",
        )

    mount_label = route["label"]
    mount_root = route["root_path"]
    sub_path = route["sub_path"] or ""

    # 4. Check mount is accessible
    if not Path(mount_root).is_dir():
        return _err(
            "mount_offline",
            f"Mount '{mount_label}' is not accessible at {mount_root}",
        )

    # 5. Build destination
    dest_parent = Path(mount_root) / sub_path if sub_path else Path(mount_root)
    dest = dest_parent / folder_name

    # 6. Destination must not exist
    if dest.exists():
        return _err(
            "dest_exists",
            f"Destination already exists: {dest}",
        )

    return {
        "ok": True,
        "year": year,
        "mount_id": route["mount_id"],
        "mount_label": mount_label,
        "mount_root": mount_root,
        "sub_path": sub_path,
        "dest_parent": str(dest_parent),
        "dest": str(dest),
        "error": None,
        "error_code": None,
    }


def _err(code: str, message: str) -> dict:
    return {
        "ok": False,
        "year": None,
        "mount_id": None,
        "mount_label": "",
        "mount_root": "",
        "sub_path": "",
        "dest_parent": "",
        "dest": "",
        "error": message,
        "error_code": code,
    }


# ── Filing execution ───────────────────────────────────────────────────────────

def file_folder(
    lb_number: int,
    folder_path: str,
    file_mode: str = "move",
    db_path=None,
) -> dict:
    """Resolve destination and physically move or copy the folder.

    Args:
        lb_number:   LB number (must be in entries table).
        folder_path: Absolute path to the source folder on disk.
        file_mode:   "move" (default) or "copy". Read from meta at call site.
        db_path:     Optional override for SQLite path.

    Returns:
        {
            ok (bool),
            filed_to (str),        — mount label, e.g. "DYLAN4"
            dest (str),            — final absolute path
            file_mode (str),       — "move" or "copy"
            error (str | None),
            error_code (str | None),
        }
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Source folder not found: {folder_path}",
            "error_code": "src_missing",
        }

    # Pre-flight resolution (all checks, no filesystem writes)
    resolution = resolve_destination_for_lb(lb_number, folder_path, db_path)
    if not resolution["ok"]:
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": resolution["error"],
            "error_code": resolution["error_code"],
        }

    dest_parent = Path(resolution["dest_parent"])
    dest = Path(resolution["dest"])
    mount_label = resolution["mount_label"]

    # Create year subfolder if needed (idempotent)
    try:
        dest_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Cannot create destination directory {dest_parent}: {exc}",
            "error_code": "mkdir_failed",
        }

    # Move or copy
    try:
        if file_mode == "copy":
            shutil.copytree(str(folder), str(dest))
        else:
            shutil.move(str(folder), str(dest))
    except Exception as exc:
        # Clean up partial copy if copytree failed mid-way
        if file_mode == "copy" and dest.exists():
            try:
                shutil.rmtree(str(dest))
            except Exception:
                pass
        return {
            "ok": False,
            "filed_to": "",
            "dest": "",
            "file_mode": file_mode,
            "error": f"Filesystem {file_mode} failed: {exc}",
            "error_code": "fs_error",
        }

    # Register in my_collection
    folder_name = folder.name
    try:
        database.add_to_collection(
            lb_number,
            folder_name,
            str(dest),
            notes=None,
            db_path=db_path,
        )
    except Exception as exc:
        # Filesystem op succeeded but DB write failed.
        # Log loudly; the collection integrity poller will catch the orphaned folder.
        logger.error(
            "file_folder: filesystem %s succeeded but my_collection insert failed "
            "for LB-%05d at %s: %s",
            file_mode,
            lb_number,
            dest,
            exc,
        )
        return {
            "ok": False,
            "filed_to": mount_label,
            "dest": str(dest),
            "file_mode": file_mode,
            "error": (
                f"Folder {file_mode}d to {dest} but collection registration failed: {exc}. "
                "The folder exists on disk — use My Collection → Add folder to register it manually."
            ),
            "error_code": "db_write_failed",
        }

    logger.info(
        "file_folder: LB-%05d %sd to %s (mount: %s)",
        lb_number,
        file_mode,
        dest,
        mount_label,
    )

    return {
        "ok": True,
        "filed_to": mount_label,
        "dest": str(dest),
        "file_mode": file_mode,
        "error": None,
        "error_code": None,
    }
```

---

## 3. New DB Helper Functions (`backend/db.py`)

Add these functions to `db.py`:

```python
# ── Collection Mounts ──────────────────────────────────────────────────────────

def get_collection_mounts(db_path=None) -> list[dict]:
    """Return all mounts with live online status."""
    from pathlib import Path as _Path
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, label, root_path, notes, created_at "
            "FROM collection_mounts ORDER BY label"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["online"] = _Path(r["root_path"]).is_dir()
        result.append(d)
    return result


def add_collection_mount(label: str, root_path: str, notes: str | None = None,
                         db_path=None) -> int:
    """Insert a new mount. Returns new row id."""
    _l, _r, _n = label, root_path, notes

    def _run(c):
        c.execute(
            "INSERT INTO collection_mounts(label, root_path, notes) VALUES(?,?,?)",
            (_l, _r, _n),
        )
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection_mount(mount_id: int, fields: dict, db_path=None) -> None:
    allowed = {"label", "root_path", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [mount_id]
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE collection_mounts SET {set_clause} WHERE id=?", params
        )
    )


def delete_collection_mount(mount_id: int, db_path=None) -> dict:
    """Delete a mount. Returns {ok, error} — fails if routes reference it."""
    _id = mount_id

    def _run(c):
        in_use = c.execute(
            "SELECT COUNT(*) FROM collection_routes WHERE mount_id=?", (_id,)
        ).fetchone()[0]
        if in_use:
            return {"ok": False, "error": f"Mount is referenced by {in_use} route(s)"}
        c.execute("DELETE FROM collection_mounts WHERE id=?", (_id,))
        return {"ok": True, "error": None}

    return get_write_queue().execute(_run)


# ── Collection Routes ──────────────────────────────────────────────────────────

def get_collection_routes(db_path=None) -> list[dict]:
    """Return all routes joined with mount label and root_path, ordered by year."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT r.year, r.mount_id, r.sub_path,
                      m.label AS mount_label, m.root_path
               FROM collection_routes r
               JOIN collection_mounts m ON m.id = r.mount_id
               ORDER BY r.year"""
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_collection_routes(
    year_from: int,
    year_to: int,
    mount_id: int,
    sub_path: str,
    db_path=None,
) -> int:
    """Insert or replace one route row per year in [year_from, year_to] inclusive.

    Returns the number of rows written.
    """
    years = list(range(year_from, year_to + 1))
    _mid, _sp = mount_id, sub_path

    def _run(c):
        c.executemany(
            "INSERT OR REPLACE INTO collection_routes(year, mount_id, sub_path) "
            "VALUES(?,?,?)",
            [(y, _mid, _sp) for y in years],
        )
        return len(years)

    return get_write_queue().execute(_run)


def delete_collection_route(year: int, db_path=None) -> None:
    _y = year
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM collection_routes WHERE year=?", (_y,))
    )
```

---

## 4. New API Routes (`backend/app.py`)

Add a new **Collection Mounts & Routes** section. Insert after the existing Collection Data Management block.

```python
# ── Collection Mounts & Routes ────────────────────────────────────────────────

@app.route("/api/collection/mounts", methods=["GET"])
def collection_mounts_list():
    """List all configured mounts with live online status."""
    try:
        return jsonify(database.get_collection_mounts())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/mounts", methods=["POST"])
def collection_mounts_create():
    """Create a new mount. Body: {label, root_path, notes?}"""
    try:
        data = request.get_json() or {}
        label = (data.get("label") or "").strip()
        root_path = (data.get("root_path") or "").strip()
        if not label or not root_path:
            return jsonify({"error": "label and root_path are required"}), 400
        mount_id = database.add_collection_mount(
            label, root_path, data.get("notes")
        )
        return jsonify({"ok": True, "id": mount_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/mounts/<int:mount_id>", methods=["PATCH"])
def collection_mounts_update(mount_id: int):
    """Update label/root_path/notes for a mount."""
    try:
        data = request.get_json() or {}
        database.update_collection_mount(mount_id, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/mounts/<int:mount_id>", methods=["DELETE"])
def collection_mounts_delete(mount_id: int):
    """Delete a mount. Fails if any routes reference it."""
    try:
        result = database.delete_collection_mount(mount_id)
        if not result["ok"]:
            return jsonify(result), 409
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/routes", methods=["GET"])
def collection_routes_list():
    """List all year routes joined with mount info."""
    try:
        return jsonify(database.get_collection_routes())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/routes/bulk", methods=["POST"])
def collection_routes_bulk():
    """Insert or replace routes for a year range.

    Body: {year_from, year_to, mount_id, sub_path}
    Replaces any existing routes for years in the range.
    """
    try:
        data = request.get_json() or {}
        year_from = data.get("year_from")
        year_to = data.get("year_to")
        mount_id = data.get("mount_id")
        sub_path = data.get("sub_path", "")
        if year_from is None or year_to is None or mount_id is None:
            return jsonify({"error": "year_from, year_to, mount_id required"}), 400
        year_from, year_to = int(year_from), int(year_to)
        if year_from > year_to:
            return jsonify({"error": "year_from must be <= year_to"}), 400
        count = database.upsert_collection_routes(
            year_from, year_to, int(mount_id), sub_path or ""
        )
        return jsonify({"ok": True, "rows_written": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/routes/<int:year>", methods=["DELETE"])
def collection_routes_delete(year: int):
    """Remove the route for a single year."""
    try:
        database.delete_collection_route(year)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collection/routes/preview/<int:year>", methods=["GET"])
def collection_routes_preview(year: int):
    """Dry-run: show what year YYYY would resolve to without filing anything.

    Returns: {ok, year, mount_label, mount_root, sub_path, dest_parent,
              mount_online, error?, error_code?}
    """
    try:
        from pathlib import Path as _Path
        with database.get_connection() as conn:
            route = conn.execute(
                """SELECT r.year, r.sub_path, m.id, m.label, m.root_path
                   FROM collection_routes r
                   JOIN collection_mounts m ON m.id = r.mount_id
                   WHERE r.year = ?""",
                (year,),
            ).fetchone()
        if route is None:
            return jsonify({
                "ok": False,
                "year": year,
                "error": f"No route configured for {year}",
                "error_code": "no_route",
            })
        root = route["root_path"]
        sub = route["sub_path"] or ""
        dest_parent = str(_Path(root) / sub) if sub else root
        return jsonify({
            "ok": True,
            "year": year,
            "mount_label": route["label"],
            "mount_root": root,
            "sub_path": sub,
            "dest_parent": dest_parent,
            "mount_online": _Path(root).is_dir(),
            "error": None,
            "error_code": None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Pipeline: File step ────────────────────────────────────────────────────────

@app.route("/api/pipeline/file", methods=["POST"])
def pipeline_file():
    """Execute step 5: file one or more folders into the collection.

    Body: {folders: [{path: str, lb_number: int}, ...]}
    Each entry is processed independently; failures do not abort the batch.

    Returns:
        {results: [{path, lb_number, ok, filed_to, dest, file_mode, error, error_code}]}
    """
    try:
        from backend.filer import file_folder
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400
        file_mode = database.get_meta("pipeline_file_mode") or "move"
        results = []
        for item in folders:
            path = item.get("path", "")
            lb = item.get("lb_number")
            if not path or not lb:
                results.append({
                    "path": path,
                    "lb_number": lb,
                    "ok": False,
                    "filed_to": "",
                    "dest": "",
                    "file_mode": file_mode,
                    "error": "path and lb_number are required",
                    "error_code": "bad_input",
                })
                continue
            result = file_folder(int(lb), path, file_mode=file_mode)
            result["path"] = path
            result["lb_number"] = lb
            results.append(result)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/file/preview", methods=["POST"])
def pipeline_file_preview():
    """Pre-flight check: resolve destinations without moving anything.

    Body: {folders: [{path: str, lb_number: int}, ...]}
    Returns: {results: [{path, lb_number, ok, year, mount_label, dest_parent,
                         dest, mount_online, error, error_code}]}
    """
    try:
        from backend.filer import resolve_destination_for_lb
        from pathlib import Path as _Path
        data = request.get_json() or {}
        folders = data.get("folders", [])
        results = []
        for item in folders:
            path = item.get("path", "")
            lb = item.get("lb_number")
            if not path or not lb:
                results.append({
                    "path": path, "lb_number": lb,
                    "ok": False, "error": "path and lb_number required",
                    "error_code": "bad_input",
                })
                continue
            r = resolve_destination_for_lb(int(lb), path)
            r["path"] = path
            r["lb_number"] = lb
            if r["ok"]:
                r["mount_online"] = _Path(r["mount_root"]).is_dir()
            results.append(r)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

## 5. Pipeline State Integration (`backend/app.py` — `_pipeline_process_folder`)

Add a step 5 key to the `PipelineRow` dict returned by `_pipeline_process_folder`. Append after the lbdir block:

```python
# ── Step 5: File (resolve only — no filesystem action here) ──────────────────
if "file" in steps and lb_number:
    from backend.filer import resolve_destination_for_lb
    from pathlib import Path as _Path
    resolution = resolve_destination_for_lb(lb_number, folder_path)
    if resolution["ok"]:
        mount_online = _Path(resolution["mount_root"]).is_dir()
        if mount_online:
            row["file"] = {
                "status": "ready",
                "label": "Ready to file",
                "dest_parent": resolution["dest_parent"],
                "dest": resolution["dest"],
                "mount_label": resolution["mount_label"],
                "year": resolution["year"],
                "error": None,
                "error_code": None,
            }
        else:
            row["file"] = {
                "status": "blocked",
                "label": "Mount offline",
                "dest_parent": "",
                "dest": "",
                "mount_label": resolution["mount_label"],
                "year": resolution["year"],
                "error": resolution["error"] or f"Mount '{resolution['mount_label']}' is offline",
                "error_code": "mount_offline",
            }
    else:
        row["file"] = {
            "status": "blocked",
            "label": _file_blocked_label(resolution["error_code"]),
            "dest_parent": "",
            "dest": "",
            "mount_label": "",
            "year": resolution["year"],
            "error": resolution["error"],
            "error_code": resolution["error_code"],
        }
else:
    row["file"] = {"status": "mute", "label": "—", "error": None, "error_code": None}
```

Add this helper near the pipeline block:

```python
def _file_blocked_label(error_code: str | None) -> str:
    return {
        "no_date":       "No date",
        "no_route":      "No route",
        "mount_offline": "Mount offline",
        "dest_exists":   "Already exists",
        "db_error":      "DB error",
    }.get(error_code or "", "Blocked")
```

Also add `"file"` as a valid step name in `pipeline_run()`:

```python
steps: set[str] = set(data.get("steps", ["verify", "lookup", "rename", "lbdir", "file"]))
```

---

## 6. Settings Key

In `db_settings()` GET handler, add `"pipeline_file_mode"` to the `keys` list:

```python
keys = [
    "scrape_attachments", "scrape_delay_ms", "auto_scrape", "use_local_pages",
    "force_scrape", "search_page_size", "github_repo", "data_zip_url",
    "qbt_host", "qbt_port", "qbt_category", "qbt_tags",
    "tracker_list", "wtrf_board_id", "ui_language",
    "pipeline_file_mode",   # ← add this
]
```

---

## 7. Setup UI — Mounts & Routes Section

Add a new **Mounts & Routes** `SetupCard` to `ScreenSetup.tsx`. Place it after the Database card, before Integrations.

### 7a. Mounts panel

Displays all rows from `GET /api/collection/mounts`.

Each mount row shows:
- Online/offline dot badge (green = `online: true`, red = `online: false`)
- Label (editable inline)
- Root path (editable inline, with a "Browse…" folder picker on Electron)
- Notes (optional)
- Delete button — shows a confirmation if the delete returns 409 (routes in use)

"Add mount" button opens an inline form: label + root path + notes → `POST /api/collection/mounts`.

### 7b. Routes table

Displays all rows from `GET /api/collection/routes`, one row per year.

Columns: **Year** | **Mount** (label dropdown) | **Sub-path** (text input) | **Resolved destination** (read-only preview: `mount_root / sub_path`) | **Delete** (×)

Unrouted years are NOT shown in the table (no empty rows for all 60+ years). A summary line below the table reads: "X of Y years configured" where Y = max year − min year + 1 for the collection's date range.

**Bulk-fill control** (above the table):

```
Year range: [1958] to [1970]   Mount: [DYLAN1 ▼]   Sub-path: [{year}]
                                                     ○ per-year  ○ flat  ○ custom
[ Apply to range ]
```

Sub-path mode shortcuts:
- **per-year**: sets `sub_path = str(year)` for each year in the range (calls `POST /api/collection/routes/bulk` once per distinct sub_path value, or loops year by year)
- **flat**: sets `sub_path = ""` for all years in the range
- **custom**: free-text field; same literal `sub_path` for all years in the range

For per-year mode, the bulk call must be made year-by-year (one call per year) since each year gets a different sub_path. Or implement client-side loop: iterate `year_from` to `year_to`, call `POST /api/collection/routes/bulk` with `year_from=y&year_to=y&sub_path=str(y)`. Alternatively implement a dedicated per-year bulk endpoint — simplest is a client loop at the cost of N round trips (max ~70, acceptable).

**Routing preview widget** (below the table):

```
Preview year: [1966]  →  /mnt/dylan1/1966  (DYLAN1 · online)
```

Calls `GET /api/collection/routes/preview/1966` on input change (debounced 300ms). Shows mount online/offline status inline.

### 7c. File mode toggle

Inside the same Mounts & Routes card, below the routes table:

```
Filing mode:   ● Move (default)   ○ Copy
```

Saves to `POST /api/db/settings` as `pipeline_file_mode: "move" | "copy"`.

When Copy is selected, show a persistent inline note:
> "Copy mode: source folders are not removed after filing. Clean up manually."

---

## 8. Pipeline UI — Step 5 Column

In `ScreenPipeline.tsx`, the stages indicator `1 — 2 — 3 — 4 — 5` maps to:
`verify → lookup → rename → lbdir → file`

Step 5 node states:

| `file.status` | Stage dot colour | Row action |
|---|---|---|
| `"mute"` | Grey | — |
| `"ready"` | Orange (action needed) | `File` button |
| `"blocked"` | Red | `Resolve →` button (opens detail) |
| `"filed"` | Green | "In collection" chip |

**"File" button** (single folder): calls `POST /api/pipeline/file` with `{folders: [{path, lb_number}]}`. On success, row moves to IN COLLECTION group, displays "Filed to {mount_label} · tagged owned" (or "Copied to…" in copy mode).

**"File all N ready" batch button** (top bar): collects all rows where `file.status === "ready"`, calls `POST /api/pipeline/file` with the full list. Rows that fail mid-batch surface individually in NEEDS YOU with their specific `file.error`.

**IN COLLECTION group row display:**
- Status: `✓ In collection`
- Sub-label: `Filed to {mount_label}` (or `Copied to {mount_label}`) + `· {dest}` (truncated, full path in tooltip)

**Blocked state tooltip / resolve panel** content by `error_code`:

| error_code | Display text |
|---|---|
| `no_date` | "Date unknown — cannot determine year for routing" |
| `no_route` | "No route for {year} — Settings → Mounts & Routes" |
| `mount_offline` | "Mount '{mount_label}' is offline" |
| `dest_exists` | "Destination already exists at {dest}" |
| `db_error` | "Database error — see logs" |

---

## 9. PROJECT.md Updates

### Schema section — add after `my_collection`:

```markdown
### `collection_mounts` — Named collection root paths (USER table)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| label | TEXT NOT NULL UNIQUE | Human name e.g. "DYLAN4" |
| root_path | TEXT NOT NULL | Absolute path to drive/share root |
| notes | TEXT | Optional |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

### `collection_routes` — Year-to-mount routing table (USER table)
| Column | Type | Notes |
|--------|------|-------|
| year | INTEGER PK | 4-digit concert year |
| mount_id | INTEGER NOT NULL | FK → collection_mounts.id (ON DELETE RESTRICT) |
| sub_path | TEXT NOT NULL | Relative path under root_path; `""` = flat into root |

Destination = `Path(root_path) / sub_path / folder_name`.  
Index: `idx_routes_mount ON collection_routes(mount_id)`.
```

### API routes section — add new subsection "Collection Mounts & Routes":

```markdown
### Collection Mounts & Routes
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/collection/mounts` | List mounts with live `online` status |
| POST | `/api/collection/mounts` | Create mount. Body: `{label, root_path, notes?}` |
| PATCH | `/api/collection/mounts/<id>` | Update label/root_path/notes |
| DELETE | `/api/collection/mounts/<id>` | Delete mount; 409 if routes reference it |
| GET | `/api/collection/routes` | All year routes joined with mount label/root_path |
| POST | `/api/collection/routes/bulk` | Upsert routes for year range. Body: `{year_from, year_to, mount_id, sub_path}` |
| DELETE | `/api/collection/routes/<year>` | Remove route for one year |
| GET | `/api/collection/routes/preview/<year>` | Dry-run: resolve dest for year without filing |
| POST | `/api/pipeline/file` | Execute filing. Body: `{folders:[{path,lb_number},...]}` |
| POST | `/api/pipeline/file/preview` | Pre-flight resolve for multiple folders |
```

### Settings key — add to the `GET /api/db/settings` description:

```
pipeline_file_mode  — "move" (default) or "copy"
```

### New file — add to File Structure:

```
│   ├── filer.py              # Pipeline step 5: year resolution, move/copy, my_collection registration
```

---

## 10. Tracking IDs

Assign the next available FEAT number. Add to `CHANGELOG.md` on completion:

```
| {date} | FEAT-XX Pipeline filing step: collection_mounts + collection_routes tables;
  backend/filer.py (year_from_date_str, resolve_destination_for_lb, file_folder);
  8 new API routes (/api/collection/mounts, /api/collection/routes/*, /api/pipeline/file,
  /api/pipeline/file/preview); pipeline_file_mode meta key; step 5 stage node in pipeline UI;
  Mounts & Routes Setup card with bulk-fill, routing preview, and move/copy toggle. |
```

---

## 11. Implementation Order

1. DB schema additions + migration guards (`db.py`)
2. DB helper functions (`db.py`)
3. `backend/filer.py` (full module)
4. API routes — mounts, routes, pipeline/file, pipeline/file/preview (`app.py`)
5. `_pipeline_process_folder` step 5 addition + `_file_blocked_label` helper (`app.py`)
6. `pipeline_file_mode` key in `db_settings()` (`app.py`)
7. Setup UI — Mounts & Routes card (`ScreenSetup.tsx`)
8. Pipeline UI — step 5 column, File button, batch action, IN COLLECTION group (`ScreenPipeline.tsx`)
9. `PROJECT.md` updates
10. `CHANGELOG.md` entry
