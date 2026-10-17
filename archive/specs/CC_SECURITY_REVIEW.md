# Security Review — feat/lb-master-integrity

**Date:** 2026-05-17
**Branch reviewed:** `feat/lb-master-integrity` (merged into `main` at `416a78b3`)
**Scope:** `backend/app.py`, `backend/db.py`, `backend/folder_naming.py`, `gui/setup_tab.py`

---

## Summary Table

| # | Severity | File:Line | Issue |
|---|----------|-----------|-------|
| 1 | **Critical** | `app.py:~1598`, `db.py:~1730` | Path traversal in `/api/master/import` — arbitrary filesystem read via ATTACH DATABASE |
| 2 | **High** | `app.py:~1588` | `/api/master/import` missing curator authorization check |
| 3 | **High** | `app.py:~1452, ~1528` | `/api/lb_master/reconcile` and `/api/db/backup` have no auth gate |
| 4 | **High** | `db.py:~1748` | Manifest SHA256/schema fields not type-checked before use |
| 5 | **High** | `setup_tab.py:~914, ~968` | Blocking HTTP calls on Qt main thread (300s/600s timeout) |
| 6 | **Medium** | `app.py:~1439`, `db.py:~1515` | `status` param not allowlist-validated |
| 7 | **Medium** | `app.py:~1443, ~1465` | `offset`/`limit` accept negatives; history `limit` uncapped |
| 8 | **Medium** | `app.py:~1533, ~1578`, `db.py:~1687` | `reason` field written to manifest without length limit |
| 9 | **Medium** | `app.py:~1406–1610` (all new routes) | Raw `str(exc)` exposes filesystem paths and schema details |
| 10 | **Low** | `db.py:~1606, ~1782` | f-string table name interpolation — safe now, fragile by design |
| 11 | **Low** | `app.py:~1477` | `manual_notes` stored without length cap |
| 12 | **Low** | `app.py:~1550` | Curator flag unauthenticated (documented threat model boundary) |
| 13 | **Info** | `main.py:~41` | Flask correctly bound to 127.0.0.1 only |
| 14 | **Info** | `db.py:~65` | Credentials correctly excluded from master export whitelist |

---

## Findings

### CRITICAL

#### 1. Path traversal in `/api/master/import`
**File:** `app.py:~1598`, `db.py:~1730`

The `path` field from the POST body is passed verbatim to `import_master_db()` with no directory containment check. Any SQLite-compatible file on the local filesystem can be supplied (e.g. a home directory config or credential store), and `ATTACH DATABASE` will open and copy from it into the production `checksums`, `entries`, `lb_master`, and other MASTER_TABLES. The SHA256 check only validates the integrity of whatever file was supplied — not its provenance.

```python
# app.py — no path containment check
body = request.get_json(silent=True) or {}
path = body.get("path")
summary = database.import_master_db(path)  # arbitrary path accepted

# db.py — opens the caller-supplied path
conn.execute(f"ATTACH DATABASE ? AS incoming", (str(snapshot_path),))
```

**Fix:** Resolve and constrain the path to allowed directories before passing it to the DB layer:

```python
from backend.paths import DATA_DIR
snapshot_path = Path(path).resolve()
allowed_dirs = [DATA_DIR / "exports", DATA_DIR / "imports"]
if not any(snapshot_path.is_relative_to(d) for d in allowed_dirs):
    return jsonify({"error": "path_not_allowed",
                    "message": "Snapshot must be in data/exports/ or data/imports/"}), 400
```

Also enforce `.db` extension and no embedded null bytes.

---

### HIGH

#### 2. `/api/master/import` missing curator authorization check
**File:** `app.py:~1588`

`/api/master/export` correctly requires `is_curator()`. The import endpoint has no guard — any local process reaching port 5174 can overwrite the six MASTER_TABLES by POSTing `{"path": "/some/path.db"}`.

**Fix:**
```python
if not database.is_curator():
    return jsonify({"error": "curator_required",
                    "message": "Master import requires curator mode."}), 403
```

Note: if the design intent is that end-users can install updates without curator mode, add an alternative trust mechanism (e.g. manifest signed by a known key, or a one-time confirmation token stored in meta).

---

#### 3. `/api/lb_master/reconcile` and `/api/db/backup` unprotected
**File:** `app.py:~1452, ~1528`

Neither endpoint checks `is_curator()` or any other gate. Any local caller can:
- Trigger repeated `VACUUM INTO` backup operations that fill disk.
- Rewrite all of `lb_master` via a full reconcile, blocking the running app.
- Retrieve the backup file path and size in the response.

**Fix:** Require `is_curator()` for reconcile. Rate-limit `/api/db/backup` via a cooldown timestamp in `meta` (e.g. reject if last backup was less than 60s ago).

---

#### 4. Manifest fields not type-checked before use
**File:** `db.py:~1748`

```python
incoming_schema = int(manifest.get("master_schema_version", 0))
```

- `manifest.get("master_schema_version")` returning `None` → `int(None)` → `TypeError`, caught by the generic `except Exception`, returning raw error text (including internal paths) to the caller.
- A very large string value causes the same.
- No lower-bound check: `master_schema_version: -1` silently passes the `incoming_schema > MASTER_SCHEMA_VERSION` guard, allowing downgrade snapshots.
- `sha256: null` (JSON null) causes `None != actual_sha` → `ValueError` is raised, which is correct, but the error message exposes the actual computed SHA.

**Fix:**
```python
raw_schema = manifest.get("master_schema_version")
if not isinstance(raw_schema, (int, str)):
    raise ValueError("Invalid manifest: master_schema_version missing or wrong type")
incoming_schema = int(raw_schema)
if incoming_schema < 1 or incoming_schema > MASTER_SCHEMA_VERSION:
    raise RuntimeError(f"Schema version {incoming_schema} out of accepted range")

sha = manifest.get("sha256")
if not isinstance(sha, str) or len(sha) != 64:
    raise ValueError("Invalid manifest: sha256 missing or wrong format")
```

---

#### 5. Blocking HTTP calls on Qt main thread
**File:** `setup_tab.py:~914` (`_on_publish_master`), `setup_tab.py:~968` (`_on_install_master`)

Both handlers make synchronous `requests.post(…, timeout=300)` / `requests.post(…, timeout=600)` on the GUI thread. A large export or import freezes the entire window for the duration, violates the project threading rule in CLAUDE.md ("all GUI↔backend calls must be in QThread workers"), and can deadlock if the Flask server is busy.

**Fix:** Move both operations into `QThread` workers following the existing `_ScrapeRangeThread` pattern. Emit progress signals; update UI in the `finished` slot.

---

### MEDIUM

#### 6. `status` query param not allowlist-validated
**File:** `app.py:~1439`, `db.py:~1515`

Any string value passes through to the parameterised SQL query. Safe from injection, but invalid values silently return HTTP 200 with an empty list — callers cannot distinguish "no results" from "bad request."

**Fix:**
```python
VALID_STATUSES = {"public", "private", "missing"}
if status and status not in VALID_STATUSES:
    return jsonify({"error": "invalid_status",
                    "message": f"status must be one of {sorted(VALID_STATUSES)}"}), 400
```

---

#### 7. `offset`/`limit` accept negatives; history `limit` uncapped
**File:** `app.py:~1443, ~1465`

`offset = int(request.args.get("offset", 0))` has no lower-bound guard. SQLite treats a negative OFFSET as "no offset" (implementation-defined). The `/api/lb_master/history/<lb>` limit has no upper-bound cap (unlike the list endpoint which caps at 2000).

**Fix:**
```python
limit = max(1, min(int(request.args.get("limit", 50)), 500))
offset = max(0, int(request.args.get("offset", 0)))
```

---

#### 8. `reason` field written to manifest without length limit
**File:** `app.py:~1533, ~1578`, `db.py:~1687`

The `reason` string is sanitised for the filename but embedded raw in the manifest JSON. A caller can supply a multi-megabyte string that gets written into `.manifest.json`.

**Fix:** Truncate on receipt: `reason = str(body.get("reason", "manual"))[:200]`

---

#### 9. Raw `str(exc)` exposes internals across all new routes
**File:** `app.py:~1406–1610` (all new integrity routes)

Every catch-all returns `{"error": str(exc)}`. SQLite error strings include full absolute file paths, table names, and constraint details useful for schema fingerprinting. The import and export routes are especially sensitive because paths appear in SQLite errors.

**Fix:** Log the full exception internally; return a sanitised message for the catch-all:
```python
except Exception as exc:
    log.exception("endpoint failed")
    return jsonify({"error": "internal_error"}), 500
```
Retain the specific `FileNotFoundError`, `ValueError`, `RuntimeError` catches that already return structured messages.

---

### LOW

#### 10. f-string table name interpolation in export/import
**File:** `db.py:~1606, ~1782`

```python
for tbl in USER_TABLES:
    snap.execute(f"DROP TABLE IF EXISTS {tbl}")
```

`USER_TABLES` is a hardcoded constant — no current injection risk. However, any future addition of an improperly formed identifier (merge conflict, copy-paste error) silently becomes injectable. SQLite does not support parameterised table names, so this pattern is necessary; add a guard at module load:

```python
import re
_SAFE_IDENT = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
assert all(_SAFE_IDENT.match(t) for t in (*MASTER_TABLES, *USER_TABLES)), \
    "Table name constant contains unsafe identifier"
```

---

#### 11. `manual_notes` stored without length cap
**File:** `app.py:~1477`

**Fix:** `notes = str(body.get("notes", ""))[:1000]`

---

#### 12. Curator flag unauthenticated — threat model boundary
**File:** `app.py:~1550`

Any local process can POST `{"enabled": true}` to `/api/curator` and elevate to curator, then call export. This is acceptable for a single-user desktop app where any local process is already trusted, but the curator guard on `master_export` provides no real protection against a local attacker — only against accidental GUI clicks.

**Document the threat model:** The app's security boundary is the OS user account. If this app is ever run as a multi-user service or with a network-accessible Flask port, the curator flag must be backed by real authentication. This finding becomes **Critical** in that scenario.

---

### INFO

#### 13. Flask bound to 127.0.0.1 only
All three server startup paths in `main.py` bind to `host="127.0.0.1"`. No new routes change this. The attack surface for all findings above is restricted to local processes.

#### 14. Credentials correctly excluded from master export
`wtrf_password`, `wtrf_username`, `qbt_*`, and all other credential-related meta keys are in `USER_META_KEYS` and absent from `MASTER_META_KEYS`. The export verification step explicitly checks for residual non-master meta keys. Credential leak via export is not possible.

---

## Priority Fix Order

All items fixed 2026-05-19. See CHANGELOG.md for details.

1. **#1 Path traversal** ✅ — directory containment + .db extension check in `master_import()`
2. **#2 Missing curator gate on import** ✅ — is_curator() 403 added
3. **#5 Main-thread HTTP** ✅ — `_InstallMasterThread` + `_ExportMasterThread` QThread workers
4. **#4 Manifest type validation** ✅ — isinstance checks, no SHA exposure on mismatch, lower-bound guard
5. **#3 Unprotected reconcile/backup** ✅ — is_curator() on reconcile; 60 s rate-limit on backup
6. **#6 status allowlist** ✅
7. **#7 offset/limit bounds** ✅
8. **#8 reason length cap** ✅
9. **#9 str(exc) exposure** ✅ — log.exception + internal_error on sensitive routes
10. **#10 f-string table names** ✅ — _SAFE_IDENT assertion at module load
11. **#11 manual_notes length** ✅
