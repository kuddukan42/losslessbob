#!/usr/bin/env python3
"""batch_verify.py — Headless CLI for lbdir-centric batch collection verification.

Talks to the Flask backend exclusively via HTTP (default port 5174).
The backend must be running before invocation:
    python run_backend.py          # headless
    python main.py                 # with legacy GUI

Ground truth: the lbdir*.txt file is the canonical record for each folder.
Existing FFP/MD5/ST5 files are used only for LB-number identification (Phase 0).

Usage examples:
    # Use folders from the collection DB (recommended):
    python tools/batch_verify.py --from-collection
    python tools/batch_verify.py --from-collection --resume
    python tools/batch_verify.py --from-collection --resume --reprocess fail,missing_files
    python tools/batch_verify.py --from-collection --dry-run

    # Or walk a root directory:
    python tools/batch_verify.py --root /mnt/music/dylan

    # Reports:
    python tools/batch_verify.py --report
    python tools/batch_verify.py --report --status fail
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("batch_verify")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_PORT = 5174
DEFAULT_DB = "data/batch_verify.db"
DEFAULT_DELAY = 0.05

AUDIO_EXTS = {".flac", ".shn"}

# Status values
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_MISSING_FILES = "missing_files"
STATUS_NO_LBDIR = "no_lbdir"
STATUS_NO_LB = "no_lb"
STATUS_LOOKUP_MULTI = "lookup_multi"
STATUS_LOOKUP_NOT_FOUND = "lookup_not_found"
STATUS_PARSE_ERROR = "parse_error"
STATUS_RETRIEVE_ERROR = "retrieve_error"
STATUS_API_ERROR = "api_error"
STATUS_DRY_RUN = "dry_run"

# Map lbdir/check API status → batch verify_status
_VERIFY_STATUS_MAP = {
    "pass": STATUS_PASS,
    "fail": STATUS_FAIL,
    "incomplete": STATUS_MISSING_FILES,
    "no_lbdir": STATUS_NO_LBDIR,
    "parse_error": STATUS_PARSE_ERROR,
}


# ── Report database ───────────────────────────────────────────────────────────

def open_report_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the report database at db_path."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS batch_results (
            folder               TEXT PRIMARY KEY,
            lb_number            INTEGER,
            lb_source            TEXT,
            lbdir_found          INTEGER,
            lbdir_retrieved      INTEGER,
            verify_status        TEXT,
            pass_count           INTEGER,
            mismatch_count       INTEGER,
            missing_count        INTEGER,
            reconcile_proposals  INTEGER,
            last_run             TEXT,
            notes                TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at    TEXT,
            finished_at   TEXT,
            root          TEXT,
            total         INTEGER,
            pass          INTEGER,
            fail          INTEGER,
            missing_files INTEGER,
            no_lbdir      INTEGER,
            no_lb         INTEGER,
            error         INTEGER,
            args          TEXT
        )
    """)
    conn.commit()
    return conn


def db_get(conn: sqlite3.Connection, folder: Path) -> sqlite3.Row | None:
    """Fetch a batch_results row by folder path."""
    return conn.execute(
        "SELECT * FROM batch_results WHERE folder=?", (str(folder),)
    ).fetchone()


def db_upsert(conn: sqlite3.Connection, *, folder: Path, **kwargs) -> None:
    """Insert or replace a batch_results row, stamping last_run."""
    kwargs["folder"] = str(folder)
    kwargs["last_run"] = datetime.now(timezone.utc).isoformat()
    cols = list(kwargs.keys())
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO batch_results ({col_list}) VALUES ({placeholders})",
        [kwargs[c] for c in cols],
    )
    conn.commit()


def insert_run_log(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Insert a run_log row and return its id."""
    args_json = json.dumps(vars(args), default=str)
    cur = conn.execute(
        "INSERT INTO run_log (started_at, root, args) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), getattr(args, "root", None), args_json),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def finalize_run_log(conn: sqlite3.Connection, run_id: int) -> None:
    """Update run_log with finished_at timestamp and status summary counts."""
    total = conn.execute("SELECT COUNT(*) FROM batch_results").fetchone()[0]

    def _count(status: str) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM batch_results WHERE verify_status=?", (status,)
        ).fetchone()[0]

    conn.execute(
        """UPDATE run_log
           SET finished_at=?, total=?, pass=?, fail=?, missing_files=?,
               no_lbdir=?, no_lb=?, error=?
           WHERE id=?""",
        (
            datetime.now(timezone.utc).isoformat(),
            total,
            _count(STATUS_PASS),
            _count(STATUS_FAIL),
            _count(STATUS_MISSING_FILES),
            _count(STATUS_NO_LBDIR),
            _count(STATUS_NO_LB),
            _count(STATUS_API_ERROR),
            run_id,
        ),
    )
    conn.commit()


# ── Backend connectivity ───────────────────────────────────────────────────────

def check_backend(api: str) -> None:
    """Verify the backend is reachable; print a clear error and exit if not."""
    try:
        r = requests.get(f"{api}/api/db/stats", timeout=5)
        r.raise_for_status()
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to backend at {api}", file=sys.stderr)
        print("Start the backend first:  python run_backend.py", file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print(f"ERROR: Backend at {api} timed out during health check", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"ERROR: Backend returned HTTP {e.response.status_code}", file=sys.stderr)
        sys.exit(1)


# ── API calls ─────────────────────────────────────────────────────────────────

def _api_get_folder_link(folder: Path, api: str) -> int | None:
    """GET /api/folder_link for folder; return lb_number or None."""
    try:
        r = requests.get(
            f"{api}/api/folder_link",
            params={"path": str(folder)},
            timeout=10,
        )
        if r.status_code == 200:
            lb = r.json().get("lb_number")
            return int(lb) if lb is not None else None
    except Exception:
        pass
    return None


def _api_put_folder_link(folder: Path, lb_number: int, api: str) -> None:
    """PUT /api/folder_link to persist a folder→LB mapping."""
    try:
        requests.put(
            f"{api}/api/folder_link",
            json={
                "folder_path": str(folder),
                "lb_number": lb_number,
                "note": "batch_verify auto-identified",
            },
            timeout=10,
        )
    except Exception as exc:
        log.warning("folder_link PUT failed for %s: %s", folder, exc)


def _api_lookup(text: str, api: str) -> dict:
    """POST /api/lookup; return parsed JSON (may include 'error' key)."""
    r = requests.post(f"{api}/api/lookup", json={"text": text}, timeout=30)
    return r.json()


def _api_retrieve(folder: Path, api: str) -> dict:
    """POST /api/lbdir/retrieve for one folder; return result dict."""
    try:
        r = requests.post(
            f"{api}/api/lbdir/retrieve",
            json={"folders": [str(folder)]},
            timeout=60,
        )
        if r.status_code >= 400:
            return {"status": "http_error", "error": r.text[:200]}
        results = r.json().get("results", [{}])
        return results[0] if results else {"status": "error"}
    except requests.ConnectionError:
        return {"status": "connection_error"}
    except requests.Timeout:
        return {"status": "timeout_error"}


def _api_verify(folder: Path, api: str) -> dict:
    """POST /api/lbdir/check for one folder; return result dict."""
    try:
        r = requests.post(
            f"{api}/api/lbdir/check",
            json={"folders": [str(folder)]},
            timeout=120,
        )
        if r.status_code >= 400:
            return {"status": "api_error", "error": r.text[:200]}
        results = r.json().get("results", [{}])
        return results[0] if results else {"status": "api_error"}
    except requests.ConnectionError:
        return {"status": "api_error", "error": "ConnectionError"}
    except requests.Timeout:
        return {"status": "api_error", "error": "Timeout"}


def _api_reconcile(folder: Path, api: str) -> tuple[int, str | None]:
    """POST /api/lbdir/reconcile (read-only preview); return (proposal_count, error_note).

    Returns (-1, error_note) on any failure.
    """
    try:
        r = requests.post(
            f"{api}/api/lbdir/reconcile",
            json={"folders": [str(folder)]},
            timeout=120,
        )
        if r.status_code >= 400:
            return -1, f"reconcile HTTP {r.status_code}: {r.text[:100]}"
        results = r.json().get("results", [{}])
        if results and "error" in results[0]:
            return -1, f"reconcile: {results[0]['error'][:100]}"
        proposals = results[0].get("proposals", []) if results else []
        return len(proposals), None
    except Exception as exc:
        return -1, f"reconcile: {exc}"


# ── Folder discovery ──────────────────────────────────────────────────────────

def has_lbdir(folder: Path) -> bool:
    """Return True if any lbdir*.txt exists directly in folder."""
    return any(True for _ in folder.glob("lbdir*.txt"))


def _is_generated_file(name: str) -> bool:
    """Return True for script-generated checksum files that are unreliable for ID."""
    lower = name.lower()
    return "_lbgen" in lower or "_mychecksums" in lower


def _find_checksum_file(folder: Path) -> Path | None:
    """Return the best checksum file for identification, or None.

    Priority: lbdir*.txt > *.ffp > *.md5 > *.st5
    Generated files (_lbgen*, _mychecksums*) are always skipped.
    """
    for pattern in ("lbdir*.txt", "*.ffp", "*.md5", "*.st5"):
        for f in sorted(folder.glob(pattern)):
            if f.is_file() and not _is_generated_file(f.name):
                return f
    return None


def discover_from_collection(api: str) -> list[tuple[Path, int]]:
    """Fetch disk_path + lb_number pairs from GET /api/collection.

    Returns a list of (folder_path, lb_number) sorted by lb_number.
    Entries with a null/empty disk_path are skipped with a warning.
    """
    try:
        r = requests.get(f"{api}/api/collection", timeout=30)
        r.raise_for_status()
        rows = r.json()
    except Exception as exc:
        print(f"ERROR: Could not fetch collection: {exc}", file=sys.stderr)
        sys.exit(1)

    result: list[tuple[Path, int]] = []
    skipped = 0
    for row in rows:
        dp = row.get("disk_path") or ""
        lb = row.get("lb_number")
        if not dp or lb is None:
            skipped += 1
            continue
        result.append((Path(dp), int(lb)))

    if skipped:
        print(f"  ({skipped} collection entries skipped: no disk_path recorded)")
    return result


def discover_folders(root: str) -> list[Path]:
    """Return immediate subdirectories of root that contain audio (.flac/.shn) at any depth."""
    root_path = Path(root)
    result: list[Path] = []
    try:
        entries = sorted(os.scandir(str(root_path)), key=lambda e: e.name)
    except PermissionError as exc:
        print(f"ERROR: Cannot scan root directory: {exc}", file=sys.stderr)
        return result
    for entry in entries:
        if not entry.is_dir():
            continue
        subdir = Path(entry.path)
        try:
            has_audio = any(
                p.suffix.lower() in AUDIO_EXTS
                for p in subdir.rglob("*")
                if p.is_file()
            )
        except PermissionError:
            log.warning("Permission denied scanning %s — skipped", subdir)
            continue
        if has_audio:
            result.append(subdir)
    return result


# ── Phase 0: Identify ─────────────────────────────────────────────────────────

def identify_lb(folder: Path, api: str) -> tuple[int | None, str | None]:
    """Determine the LB number for a folder via a 3-step cascade.

    Returns (lb_number, source) on success, or (None, error_status) on failure.
    source is one of: 'name', 'folder_link', 'lookup'
    error_status is one of: STATUS_NO_LB, STATUS_LOOKUP_MULTI, STATUS_LOOKUP_NOT_FOUND
    """
    # Step 1: folder name regex
    m = re.search(r"LB-(\d+)", folder.name, re.IGNORECASE)
    if m:
        return int(m.group(1)), "name"

    # Step 2: folder_link DB lookup
    lb = _api_get_folder_link(folder, api)
    if lb is not None:
        return lb, "folder_link"

    # Step 3: checksum file lookup
    cs_file = _find_checksum_file(folder)
    if cs_file is None:
        return None, STATUS_NO_LB

    try:
        text = cs_file.read_text(errors="replace")
    except OSError:
        return None, STATUS_NO_LB

    data = _api_lookup(text, api)

    if "error" in data:
        return None, STATUS_LOOKUP_NOT_FOUND

    summary = data.get("summary", [])
    matched = [s for s in summary if "MATCHED" in str(s.get("status", ""))]

    if len(matched) == 1:
        lb_number = matched[0].get("lb_number")
        if lb_number:
            _api_put_folder_link(folder, int(lb_number), api)
            return int(lb_number), "lookup"
        return None, STATUS_LOOKUP_NOT_FOUND

    if len(matched) > 1:
        return None, STATUS_LOOKUP_MULTI

    return None, STATUS_LOOKUP_NOT_FOUND


# ── Phase 2 helper ────────────────────────────────────────────────────────────

def _map_verify_status(api_status: str) -> str:
    """Map lbdir/check API status to our verify_status value."""
    return _VERIFY_STATUS_MAP.get(api_status, STATUS_API_ERROR)


# ── Per-folder pipeline ───────────────────────────────────────────────────────

def process_folder(
    folder: Path,
    api: str,
    conn: sqlite3.Connection,
    *,
    dry_run: bool,
    no_retrieve: bool,
    delay: float,
    known_lb: int | None = None,
    known_lb_source: str | None = None,
) -> None:
    """Run the full 4-phase pipeline for a single folder.

    known_lb / known_lb_source: supply when the LB number is already
    known (e.g. from --from-collection) to skip Phase 0 identification.
    """
    row = db_get(conn, folder)

    # Phase 0 — Identify
    if row and row["lb_number"]:
        lb: int = row["lb_number"]
        lb_source: str = row["lb_source"]
    elif known_lb is not None:
        lb = known_lb
        lb_source = known_lb_source or "collection"
    else:
        lb, lb_source = identify_lb(folder, api)  # type: ignore[assignment]

    if lb is None:
        db_upsert(
            conn, folder=folder,
            verify_status=lb_source,
            notes=f"identification failed: {lb_source}",
        )
        return

    # Phase 1 — Retrieve
    lbdir_present = has_lbdir(folder)
    lbdir_retrieved = False

    if not lbdir_present and not dry_run and not no_retrieve:
        result = _api_retrieve(folder, api)
        lbdir_retrieved = True
        retrieve_status = result.get("status", "error")

        if retrieve_status in ("copied", "scraped_and_copied"):
            lbdir_present = True
        elif retrieve_status in ("not_found", "no_lb_number"):
            db_upsert(
                conn, folder=folder,
                lb_number=lb, lb_source=lb_source,
                lbdir_found=0, lbdir_retrieved=1,
                verify_status=STATUS_NO_LBDIR,
                notes=f"retrieve: {retrieve_status}",
            )
            return
        else:
            error_detail = result.get("error", retrieve_status)
            db_upsert(
                conn, folder=folder,
                lb_number=lb, lb_source=lb_source,
                lbdir_found=0, lbdir_retrieved=1,
                verify_status=STATUS_RETRIEVE_ERROR,
                notes=f"retrieve: {error_detail}"[:200],
            )
            return

    if not lbdir_present:
        db_upsert(
            conn, folder=folder,
            lb_number=lb, lb_source=lb_source,
            lbdir_found=0, lbdir_retrieved=0,
            verify_status=STATUS_NO_LBDIR,
            notes="no lbdir on disk, retrieve skipped",
        )
        return

    # Dry-run: identification done, stop here
    if dry_run:
        db_upsert(
            conn, folder=folder,
            lb_number=lb, lb_source=lb_source,
            lbdir_found=1, lbdir_retrieved=int(lbdir_retrieved),
            verify_status=STATUS_DRY_RUN,
        )
        return

    # Phase 2 — Verify
    vr = _api_verify(folder, api)
    api_status = vr.get("status", "")
    notes: str | None = None

    if api_status == "shntool_missing":
        status = STATUS_FAIL if vr.get("mismatch", 0) > 0 else STATUS_PASS
        notes = "shntool unavailable; shn checksums excluded"
    else:
        status = _map_verify_status(api_status)
        if "error" in vr:
            notes = str(vr["error"])[:200]

    # Phase 3 — Reconcile preview (read-only)
    reconcile_proposals: int | None = None
    if status == STATUS_MISSING_FILES:
        count, rec_err = _api_reconcile(folder, api)
        reconcile_proposals = count
        if rec_err:
            notes = (notes + "; " if notes else "") + rec_err

    db_upsert(
        conn, folder=folder,
        lb_number=lb, lb_source=lb_source,
        lbdir_found=1, lbdir_retrieved=int(lbdir_retrieved),
        verify_status=status,
        pass_count=vr.get("pass", 0),
        mismatch_count=vr.get("mismatch", 0),
        missing_count=vr.get("missing", 0),
        reconcile_proposals=reconcile_proposals,
        notes=notes,
    )

    time.sleep(delay)


# ── Output ────────────────────────────────────────────────────────────────────

def _progress_suffix(row: sqlite3.Row | None) -> str:
    if row is None:
        return ""
    status = row["verify_status"] or ""
    parts: list[str] = []
    if status == STATUS_MISSING_FILES and row["reconcile_proposals"] is not None:
        parts.append(f"proposals={row['reconcile_proposals']}")
    if row["lbdir_retrieved"]:
        parts.append("→ retrieved")
    if status == STATUS_API_ERROR and row["notes"]:
        parts.append(f"→ {row['notes'][:60]}")
    return "  " + "  ".join(parts) if parts else ""


def print_progress(i: int, total: int, folder: Path, row: sqlite3.Row | None) -> None:
    """Print a single per-folder progress line."""
    status = (row["verify_status"] if row else "?") or "?"
    suffix = _progress_suffix(row)
    print(f"[{i:6d}/{total}]  {status:<15s} {folder}{suffix}")


def print_summary(
    conn: sqlite3.Connection,
    skipped_pass: int = 0,
    run_id: int | None = None,
) -> None:
    """Print the final run summary to stdout."""
    rows = conn.execute(
        "SELECT verify_status, COUNT(*) AS n FROM batch_results GROUP BY verify_status"
    ).fetchall()
    counts: dict[str, int] = {r["verify_status"]: r["n"] for r in rows}
    total = sum(counts.values())

    recon_row = conn.execute(
        "SELECT SUM(reconcile_proposals) AS s FROM batch_results"
        " WHERE verify_status='missing_files'"
    ).fetchone()
    recon_total = recon_row["s"] or 0

    def _pct(n: int) -> str:
        return f"  ({100 * n / total:.1f}%)" if total else ""

    n_pass = counts.get(STATUS_PASS, 0)
    n_fail = counts.get(STATUS_FAIL, 0)
    n_mf = counts.get(STATUS_MISSING_FILES, 0)
    n_nolbdir = counts.get(STATUS_NO_LBDIR, 0)
    n_nolb = counts.get(STATUS_NO_LB, 0)
    n_multi = counts.get(STATUS_LOOKUP_MULTI, 0)
    n_err = counts.get(STATUS_API_ERROR, 0)

    print("\n=== batch_verify complete ===")
    print(f"{'Total folders':<20s}: {total:6d}")
    print(f"{'pass':<20s}: {n_pass:6d}{_pct(n_pass)}")
    print(f"{'fail':<20s}: {n_fail:6d}")
    recon_note = f"   (reconcile proposals: {recon_total})" if n_mf else ""
    print(f"{'missing_files':<20s}: {n_mf:6d}{recon_note}")
    print(f"{'no_lbdir':<20s}: {n_nolbdir:6d}")
    nolb_note = "  ← manual queue" if n_nolb else ""
    print(f"{'no_lb':<20s}: {n_nolb:6d}{nolb_note}")
    multi_note = "  ← manual queue" if n_multi else ""
    print(f"{'lookup_multi':<20s}: {n_multi:6d}{multi_note}")
    print(f"{'api_error':<20s}: {n_err:6d}")
    if skipped_pass:
        print(f"{'(skipped pass)':<20s}: {skipped_pass:6d}")


def print_report(db_path: str, status_filter: str | None = None) -> None:
    """Print a summary from an existing report DB and exit."""
    path = Path(db_path)
    if not path.exists():
        print(f"ERROR: Report DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    print(f"=== batch_verify report: {db_path} ===")

    if status_filter:
        rows = conn.execute(
            "SELECT folder, mismatch_count, missing_count, reconcile_proposals"
            " FROM batch_results WHERE verify_status=? ORDER BY folder",
            (status_filter,),
        ).fetchall()
        print(f"{status_filter} ({len(rows)}):")
        for r in rows:
            detail = ""
            if r["mismatch_count"]:
                detail = f"mismatch={r['mismatch_count']}"
            elif r["missing_count"]:
                detail = f"missing={r['missing_count']}"
            elif r["reconcile_proposals"] is not None:
                detail = f"proposals={r['reconcile_proposals']}"
            print(f"  {r['folder']:<80s} {detail}")
    else:
        rows = conn.execute(
            "SELECT verify_status, COUNT(*) AS n FROM batch_results GROUP BY verify_status"
        ).fetchall()
        for r in rows:
            print(f"{r['verify_status']:<20s}: {r['n']:6d}")

    conn.close()


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Batch lbdir verification pipeline for LosslessBob collections. "
            "Requires the Flask backend running on --port."
        )
    )
    p.add_argument(
        "--root", metavar="PATH",
        help="Root directory to walk (required unless --from-collection or --report)",
    )
    p.add_argument(
        "--from-collection", action="store_true",
        help="Use disk_path values from the backend collection DB instead of --root",
    )
    p.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Flask backend port (default: {DEFAULT_PORT})",
    )
    p.add_argument(
        "--db", default=DEFAULT_DB,
        help=f"Report SQLite path (default: {DEFAULT_DB}); never touches losslessbob.db",
    )
    p.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Seconds between API calls (default: {DEFAULT_DELAY})",
    )
    p.add_argument(
        "--resume", action="store_true",
        help="Skip folders already at verify_status='pass'",
    )
    p.add_argument(
        "--reprocess", metavar="STATUSES",
        help="Comma-separated statuses to reprocess when --resume is active "
             "(e.g. fail,missing_files)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Phase 0 only: identify LB number but skip retrieve and verify",
    )
    p.add_argument(
        "--no-retrieve", action="store_true",
        help="Skip Phase 1: verify whatever lbdir is already on disk",
    )
    p.add_argument(
        "--report", action="store_true",
        help="Print summary from existing DB and exit without running",
    )
    p.add_argument(
        "--status", metavar="STATUS",
        help="With --report: list folder paths of one specific status",
    )
    p.add_argument(
        "--limit", type=int,
        help="Stop after N folders (for testing)",
    )
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if args.report:
        print_report(args.db, args.status)
        return

    if not args.root and not args.from_collection:
        print(
            "ERROR: --root or --from-collection is required unless --report is specified",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.root and args.from_collection:
        print("ERROR: --root and --from-collection are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    api = f"http://localhost:{args.port}"
    check_backend(api)

    # Build the work list: (folder_path, known_lb_or_None)
    if args.from_collection:
        print("Fetching collection folders from backend …")
        coll_pairs = discover_from_collection(api)
        work: list[tuple[Path, int | None]] = [(f, lb) for f, lb in coll_pairs]
        print(f"Found {len(work)} collection entries with disk_path.")
    else:
        print(f"Discovering folders under {args.root} …")
        plain_folders = discover_folders(args.root)
        work = [(f, None) for f in plain_folders]
        print(f"Found {len(work)} audio folders.")

    if args.limit:
        work = work[: args.limit]
    total = len(work)

    conn = open_report_db(args.db)
    run_id = insert_run_log(conn, args)

    skipped_pass = 0

    for i, (folder, known_lb) in enumerate(work, 1):
        # --resume skip logic (mirrors spec pseudocode exactly)
        if args.resume:
            row = db_get(conn, folder)
            if row and row["verify_status"] == STATUS_PASS:
                if not args.reprocess or STATUS_PASS not in args.reprocess.split(","):
                    skipped_pass += 1
                    continue
            if args.reprocess and row:
                if row["verify_status"] not in args.reprocess.split(","):
                    skipped_pass += 1
                    continue

        try:
            process_folder(
                folder, api, conn,
                dry_run=args.dry_run,
                no_retrieve=args.no_retrieve,
                delay=args.delay,
                known_lb=known_lb,
                known_lb_source="collection" if known_lb is not None else None,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            db_upsert(conn, folder=folder, verify_status=STATUS_API_ERROR, notes=str(exc))

        print_progress(i, total, folder, db_get(conn, folder))

    finalize_run_log(conn, run_id)
    print_summary(conn, skipped_pass=skipped_pass, run_id=run_id)

    db_abs = Path(args.db).resolve()
    print(f"\nReport DB : {db_abs}")
    print(f"Run log   : run_log id={run_id}")

    conn.close()


if __name__ == "__main__":
    main()
