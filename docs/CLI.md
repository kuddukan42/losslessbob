# LosslessBob CLI Reference

`cli.py` is a headless CLI that runs LosslessBob without launching the PyQt6 GUI.
It starts an embedded Flask server on a background thread, issues API requests against it,
and prints results to stdout.

## Synopsis

```
python cli.py [--port PORT] [--json] <command> [command-args]
```

Global options must appear **before** the subcommand.

---

## Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `--port PORT` | `5174` | Port for the embedded Flask server. Must match any other running instance; change only if 5174 is already in use. |
| `--json` | off | Emit raw JSON instead of the human-readable summary line. Applies to `lookup`, `search`, `stats`, and `import`. |

---

## Commands

### `lookup`

Look up one or more checksum files against the LB database.

```
python cli.py lookup <path> [<path> ...]
```

**Arguments**

| Argument | Description |
|----------|-------------|
| `paths` | One or more file paths or glob patterns (e.g. `*.txt`, `checksums/**.ffp`). Glob patterns are expanded relative to the current directory. Each matched file's text content is read and sent to `/api/lookup`. |

**Human-readable output** (one line per matched LB entry):

```
LB-00123  COMPLETE MATCH           matched=42  missing=0
LB-00456  INCOMPLETE SET           matched=37  missing=5
```

**JSON output** (`--json`): the full `/api/lookup` response, including a `summary` object with
`lb_summary`, `unmatched_checksums`, and per-LB detail lists.

**Example**

```bash
# Look up a single FFP file
python cli.py lookup ~/music/dylan-1966-05-17.ffp

# Look up all .txt files in the current directory
python cli.py lookup "*.txt"

# Same, but output JSON for scripting
python cli.py --json lookup "*.txt"
```

---

### `search`

Full-text search across LB entry metadata.

```
python cli.py search <query> [--field {all,location,date,description}]
```

**Arguments**

| Argument | Description |
|----------|-------------|
| `query` | The search term. |

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--field {all,location,date,description}` | `all` | Restrict the search to a specific metadata field. `all` searches across location, date, and description simultaneously. |

**Human-readable output** (one line per result):

```
LB-00789  1966-05-17    Manchester Free Trade Hall
```

**JSON output** (`--json`): raw list of entry objects from `/api/search`.

**Examples**

```bash
# Search everywhere for "Manchester"
python cli.py search Manchester

# Search only the date field for 1966
python cli.py search 1966 --field date

# Search location field and get JSON
python cli.py --json search "Royal Albert Hall" --field location
```

---

### `stats`

Print database statistics.

```
python cli.py stats
```

No subcommand arguments. Queries `/api/db/stats`.

**Human-readable output**:

```
LB entries: 1234  Checksums: 98765  Latest LB: 1234  Last import: 2026-05-01
```

**JSON output** (`--json`): the full stats object, e.g.:

```json
{
  "total_lb_numbers": 1234,
  "total_checksums": 98765,
  "latest_lb": 1234,
  "last_import": "2026-05-01T12:00:00"
}
```

**Example**

```bash
python cli.py stats
python cli.py --json stats
```

---

### `import`

Import a LosslessBob flat file into the database.

```
python cli.py import <path>
```

**Arguments**

| Argument | Description |
|----------|-------------|
| `path` | Path to the tab-delimited flat file (`.txt`) downloaded from the LosslessBob site. The path is resolved to an absolute path before being sent to `/api/db/import`. |

**Output**: the JSON import summary (row counts, new entries, errors) is always printed,
regardless of `--json`. Pass `--json` for pretty-printed output; omit it for a compact `str()`
representation.

**Example**

```bash
python cli.py import ~/Downloads/losslessbob_2026-05.txt
```

---

### `serve`

Start the Flask web server and block (foreground process).

```
python cli.py [--port PORT] serve
```

Use this to run LosslessBob as a headless web server — for example, on a NAS, a home server,
or inside a container. The web UI is then accessible at `http://<host>:<port>/`.

**Options**: only `--port` applies; `--json` has no effect.

**Example**

```bash
# Start on the default port
python cli.py serve

# Start on a custom port
python cli.py --port 8080 serve
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| non-zero | Python exception (e.g. Flask failed to start, network error, invalid path) |

---

## Notes

- For all non-`serve` commands the Flask server starts on a **daemon thread** and is killed
  automatically when the command finishes.
- If another process (e.g. the GUI) is already listening on `--port`, the CLI connects to it
  instead of starting a new one — the socket probe loop detects the existing server.
- The CLI requires the same Python environment as the GUI. Activate the virtualenv first:
  ```bash
  source .venv/bin/activate   # Linux/macOS
  .venv\Scripts\activate      # Windows
  ```
