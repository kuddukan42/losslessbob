# LosslessBob — Python Best Practices

Project-specific conventions for all backend Python code.  
These complement PEP 8 and are binding for all new and modified files.

---

## 1. Language and Formatting

- Python 3.11+. Use modern syntax: `X | Y` union types, `match`/`case`, `tomllib`, etc.
- PEP 8: 4-space indent, max **100 chars/line**.
- No tabs, no trailing whitespace.
- Imports: stdlib → third-party → local, each group separated by a blank line.
- Never use `print()` — use `logging` everywhere.

---

## 2. Logging

```python
# Module-level logger — use the module name, never root logger directly
_log = logging.getLogger(__name__)

# Level guide
_log.debug("detail useful during development")
_log.info("normal lifecycle events")
_log.warning("unexpected but recoverable")
_log.error("operation failed, caller should know")
_log.exception("error with traceback — only inside except blocks")
```

- One `_log = logging.getLogger(__name__)` at the top of every module; never in functions.
- Do not configure handlers inside library modules (`app.py` owns the root handler setup).
- Prefer `%s` lazy formatting (`_log.debug("found %d rows", n)`) over f-strings so the
  string is never built when the level is disabled.

### Structured context with `extra`

Pass searchable key/value context via `extra=` rather than embedding values in the message
string. This makes log lines filterable without regex:

```python
_log.info("lookup complete", extra={"lb_number": lb, "match_count": len(results)})
_log.error("scrape failed", extra={"url": url, "status_code": resp.status_code})
```

Keys passed via `extra` appear as top-level fields when a structured formatter (e.g.
`python-json-logger`) is in use, and are still visible in plain-text logs as part of the
`LogRecord`. Use `snake_case` key names. Never pass sensitive values (passwords, tokens)
through `extra`.

> Reference: [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html) and
> the companion [Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html).

---

## 3. Type Hints

Apply to all **public** functions and classes (those without a leading underscore):

```python
def get_entry(lb_number: int, db_path: str | None = None) -> dict | None:
    ...
```

- Use `X | None` (PEP 604) rather than `Optional[X]`.
- Use `list[str]`, `dict[str, int]`, `tuple[str, ...]` (lowercase generics, PEP 585).
- Private helpers (`_foo`) may omit hints if the signature is obvious from context,
  but adding them is still preferred.
- Return types must always be annotated for public functions.

### TypedDict for structured dicts

When a function returns (or accepts) a dict with a fixed, known shape, prefer `TypedDict`
over `dict[str, Any]`. This makes the contract explicit and enables editor type-checking:

```python
from typing import TypedDict, NotRequired  # NotRequired: PEP 655, Python 3.11+

class LookupMatch(TypedDict):
    lb_number: int
    title: str
    match_type: str
    confidence: NotRequired[float]  # present only on fuzzy matches
```

Use `TypedDict` for return types of public `db.*` functions that currently return plain
dicts (e.g. `get_entry`, `get_collection`). Inline `dict[str, ...]` is fine for small,
short-lived intermediate shapes.

---

## 4. Docstrings

Google style on all new public functions, methods, and classes:

```python
def lookup_checksums(parsed_entries: list[dict], db_path: str | None = None) -> dict:
    """Match parsed checksum entries against the database.

    Args:
        parsed_entries: Output of parse_checksum_text(); list of dicts with
            keys ``filename`` and ``checksum``.
        db_path: Override the default DB path (tests only).

    Returns:
        Dict with ``summary`` (list of match dicts) and ``detail`` (per-file rows).

    Raises:
        sqlite3.DatabaseError: If the DB is corrupt or locked past retry budget.
    """
```

- First line: one sentence, imperative mood, no trailing period.
- Omit obvious sections: a `get_stats()` that never raises needs no `Raises:`.
- Never describe what the code does line-by-line inside the docstring.

---

## 5. Database Access

### Connections

```python
# Always go through get_connection() — never open sqlite3.connect() directly
conn = get_connection()
```

- `get_connection()` uses a thread-local pool (one connection per thread, re-used).
- Pass `db_path` only in tests or CLI overrides, never hardcode paths.

### Writes

```python
# All writes go through DatabaseWriteQueue
queue = get_write_queue()
queue.enqueue(_run)        # _run(conn) callback; queue owns commit/rollback
```

- Never call `conn.commit()` or `conn.execute()` for writes outside the queue callback.
- The one exception is `import_master_db()` — it holds `_write_lock` across an
  ATTACH/DETACH sequence that cannot be split.

### Schema migrations

```python
try:
    c.execute("ALTER TABLE entries ADD COLUMN lb_category TEXT")
except sqlite3.OperationalError:
    pass  # column already exists — idempotent migration
```

- Always use `ALTER TABLE` + `try/except OperationalError` for new columns.
- Never `DROP` and recreate a table in a migration unless it is brand new.
- Bump `MASTER_SCHEMA_VERSION` in `db.py` when any MASTER table schema changes.

### SQL style

- Write multi-line SQL as triple-quoted strings, not concatenated fragments.
- Use `?` placeholders; never f-string user input into SQL.
- Table and column names used in f-strings must pass `_SAFE_IDENT` validation first.

---

## 6. Error Handling

- Catch the **narrowest** exception possible (`sqlite3.OperationalError`, not `Exception`).
- Use bare `except Exception` only at the outermost boundary (Flask route handlers),
  never inside utility functions.
- Always log before returning an error response; include the original exception with
  `_log.exception(...)` or `_log.error("...: %s", e)`.
- Flask route pattern:

```python
try:
    result = do_work()
    return jsonify(result)
except ValueError as e:
    return jsonify({"error": str(e)}), 400
except Exception as e:
    _log.exception("route /foo failed")
    return jsonify({"error": str(e)}), 500
```

### Exception chaining (PEP 3151)

Always use `raise … from …` when re-raising or wrapping an exception. This preserves the
full cause chain in tracebacks and is invaluable when diagnosing a 3am incident:

```python
# Good — traceback shows both the DB error and the LookupError
try:
    row = _fetch_row(lb_number, conn)
except sqlite3.OperationalError as exc:
    raise LookupError(f"DB read failed for LB {lb_number}") from exc

# Suppress the cause when it adds no information (rare)
raise ValueError("invalid checksum format") from None
```

Never swallow the original exception by raising a new one without `from exc`. A bare
`raise NewError(str(e))` discards the original traceback and makes root-cause analysis
much harder.

---

## 7. Module-level Constants and Paths

```python
# Correct — use backend.paths, never hardcode
from backend.paths import DB_PATH, DATA_DIR

# Wrong
DB_PATH = "/home/user/.local/share/losslessbob/lb.db"
```

- All configurable paths live in `backend/paths.py`.
- `Path` objects over raw strings everywhere; convert to `str` only at the last moment
  (e.g., passing to SQLite or a subprocess).
- Port 5174 is the single hardcoded exception; any change to it must be done atomically
  across all files and logged in `CHANGELOG.md`.

---

## 8. Function Size and Structure

- Functions over ~60 lines are candidates for splitting; over 100 lines must be split.
- `init_db()` is the current known exception (migration accumulation) — new code must
  not follow its pattern.
- Extract inner `def _run(c)` callbacks for queue-submitted DB writes; keep them local
  to the function that owns the transaction.
- Avoid late imports (imports inside function bodies). The only valid use is breaking a
  circular import — document why with an inline comment.

---

## 9. Threading

- All GUI↔backend calls happen over HTTP (port 5174). The backend must stay
  importable headless — no GUI-toolkit imports in backend modules.
- Backend is multi-threaded (Flask + Waitress). Assume any function may be called
  concurrently; do not use module-level mutable state without a lock.
- Use `threading.local()` for per-thread state (connection pool pattern in `db.py`).
- `_write_lock` is an `RLock` to allow re-entrant acquisition within the same thread.

---

## 10. Flask Routes

- Define routes **inside** `create_app()` as closures, not at module level.
- Route functions should do minimal work: validate input, call a `db.*` or domain
  function, return JSON. Business logic lives in the domain module, not the route.
- Return `jsonify({"error": "..."})` with an appropriate HTTP status code on all error
  paths — never raise an unhandled exception from a route.
- Use `request.get_json(silent=True)` and check for `None` before accessing keys.

---

## 11. Testing

- Tests live in `tests/` and use `pytest`.
- `conftest.py` resets `DatabaseWriteQueue` and thread-local connections between tests —
  do not create your own fixtures that duplicate this.
- Hit a real (in-memory or temp-file) SQLite DB; never mock `sqlite3`.
- Name test functions `test_<what>_<condition>`, e.g. `test_lookup_returns_empty_on_miss`.
- One assertion cluster per test; split into multiple tests rather than one giant one.

### Parametrize over repeated test bodies

Use `@pytest.mark.parametrize` whenever the same test logic runs against multiple inputs.
It produces a named sub-test for each case and gives an exact failing input in the output:

```python
@pytest.mark.parametrize("raw,expected", [
    ("abc123  track01.flac", ("abc123", "track01.flac")),
    ("ABC123  track01.flac", ("abc123", "track01.flac")),  # normalises to lower
    ("",                     None),                        # empty input → None
])
def test_parse_checksum_line(raw, expected):
    assert parse_checksum_line(raw) == expected
```

Prefer this over a loop inside a single test — a loop stops at the first failure and
hides which input broke; parametrize runs all cases and reports each independently.

> Reference: [pytest parametrize docs](https://docs.pytest.org/en/stable/how-to/parametrize.html).

---

## 12. Code Review Checklist

Before marking a backend PR ready:

- [ ] `_log = logging.getLogger(__name__)` present, no `print()` calls
- [ ] Public functions have type hints and docstrings
- [ ] DB writes go through `DatabaseWriteQueue`
- [ ] Schema changes use idempotent `ALTER TABLE` and bump `MASTER_SCHEMA_VERSION` if needed
- [ ] No hardcoded paths (use `backend.paths`)
- [ ] No `except Exception` inside utility functions
- [ ] Exception re-raises use `raise X from original_exc` (no silent cause discard)
- [ ] Function bodies under ~60 lines
- [ ] No late imports without comment
- [ ] Dict-heavy return types use `TypedDict` rather than `dict[str, Any]`
- [ ] `CHANGELOG.md` updated
- [ ] `ruff check` passes: `.venv/bin/ruff check <file>` (or just commit — the hook runs it)

---

## 13. Tooling Setup

### Install dev tools

```bash
pip install -r requirements-dev.txt
pre-commit install
```

This installs ruff and activates the git pre-commit hook. After that, every `git commit`
automatically runs ruff on staged Python files, auto-fixes safe violations (import
ordering, deprecated syntax, etc.), and blocks the commit if non-auto-fixable violations
remain.

### Running ruff manually

```bash
# Check all backend files
.venv/bin/ruff check backend/

# Check and auto-fix
.venv/bin/ruff check --fix backend/

# Check a single file
.venv/bin/ruff check backend/db.py
```

### Rules enabled

| Code | Ruleset | What it catches |
|------|---------|-----------------|
| `E`/`W` | pycodestyle | Style and whitespace (PEP 8) |
| `F` | pyflakes | Unused imports, undefined names |
| `I` | isort | Import ordering |
| `UP` | pyupgrade | Old-style type hints, deprecated stdlib usage |
| `B` | flake8-bugbear | Common bugs: loop variable capture, bare `raise`, `zip` without `strict` |
| `G` | flake8-logging-format | f-strings in log calls (enforces `%s` lazy format) |
| `LOG` | flake8-logging | Root logger calls, logger hygiene |

### Known temporary suppressions

- **E501** (line-too-long) is configured in `pyproject.toml` but suppressed until the
  TODO-109 code pass cleans up `app.py` (~53) and `db.py` (~22) pre-existing violations.
  New code is still expected to respect the 100-char limit.

### Config files

- `pyproject.toml` — ruff rules, exclusions, pytest config
- `.pre-commit-config.yaml` — pre-commit hook definition
- `requirements-dev.txt` — pinned versions of ruff and pre-commit

---

## 14. External References

Standards and guides this document draws from. Consult these when something is ambiguous
or not covered above.

| Reference | Scope |
|-----------|-------|
| [PEP 8](https://peps.python.org/pep-0008/) | Baseline style |
| [PEP 257](https://peps.python.org/pep-0257/) | Docstring conventions |
| [PEP 484](https://peps.python.org/pep-0484/) / [526](https://peps.python.org/pep-0526/) / [585](https://peps.python.org/pep-0585/) / [604](https://peps.python.org/pep-0604/) | Type hint evolution |
| [PEP 655](https://peps.python.org/pep-0655/) | `Required`/`NotRequired` in TypedDict |
| [PEP 673](https://peps.python.org/pep-0673/) | `Self` type |
| [PEP 3151](https://peps.python.org/pep-3151/) | Exception chaining (`raise X from Y`) |
| [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) | Naming, TODO format, exception policy, broader conventions |
| [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html) | Log level semantics, handler setup |
| [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html) | Structured logging, `extra=`, filters |
| [pytest — How to parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html) | Parametrized test cases |
| *Effective Python* — Brett Slatkin (3rd ed.) | Items 14–16 (generators), 26–28 (comprehensions), 61–68 (concurrency) |
