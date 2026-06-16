"""Flat-file release discovery, download, diff, and apply pipeline.

Replaces the old check_for_update() scraper approach. Checks the official
LosslessBob download page for a new flat-file zip, downloads it, diffs against
the live DB, and applies changes with a full audit trail in flat_file_releases
and flat_file_changelog.
"""
from __future__ import annotations

import hashlib
import logging
import re
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from . import db as database
from .paths import DATA_DIR

logger = logging.getLogger(__name__)

_PAGE_URL = (
    "http://www.losslessbob.wonderingwhattochoose.com"
    "/checksum_lookup/checksum_lookup_lb_zip_download.htm"
)
_DOWNLOADS_DIR = DATA_DIR / "downloads"
_ZIP_PATTERN = re.compile(
    r"Checksum_Lookup_flat_file_LastLB_(\d+)\.zip", re.IGNORECASE
)
_SIZE_PATTERN = re.compile(r"([\d.]+)\s*(Meg|MB|KB|GB|B)", re.IGNORECASE)


def _parse_size(text: str) -> int:
    """Parse a human-readable size string to bytes.

    Args:
        text: String possibly containing e.g. '4.2 Meg', '1024 KB', '2 GB'.

    Returns:
        Integer byte count, or 0 if no recognisable size is found.
    """
    m = _SIZE_PATTERN.search(text)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2).lower()
    mult = {"meg": 1024 ** 2, "mb": 1024 ** 2, "kb": 1024, "gb": 1024 ** 3, "b": 1}.get(
        unit, 1
    )
    return int(num * mult)


def _load_txt_from_zip(zip_path: Path) -> list[tuple[str, str, str, int, int]]:
    """Extract and parse the flat-file .txt from a downloaded zip.

    The flat file is tab-delimited:
        checksum<TAB>filename<TAB>chk_type<TAB>lb_number[<TAB>xref]

    Args:
        zip_path: Path to the downloaded .zip file.

    Returns:
        List of (checksum, filename, chk_type, lb_number, xref) tuples.

    Raises:
        ValueError: If no .txt file is found in the zip.
    """
    rows: list[tuple[str, str, str, int, int]] = []
    with zipfile.ZipFile(zip_path) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_names:
            raise ValueError("No .txt file found in zip")
        with zf.open(txt_names[0]) as txt:
            for raw in txt:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 4:
                    continue
                try:
                    rows.append((
                        parts[0].strip(),
                        parts[1].strip(),
                        parts[2].strip(),
                        int(parts[3].strip()),
                        int(parts[4].strip()) if len(parts) > 4 else 0,
                    ))
                except (ValueError, IndexError):
                    pass
    return rows


def discover_flat_file_release(db_path=None) -> dict:
    """Check the download page for a new flat-file release.

    Makes a live HTTP request to the download page, scrapes the zip filename,
    page timestamp, and HTTP Last-Modified header. Compares against the most
    recently applied release to determine whether an update is available.
    If a genuinely new release is found and no pending 'detected' row exists
    for it yet, inserts a 'detected' row into flat_file_releases.

    Args:
        db_path: Optional DB path override.

    Returns:
        dict with keys:
            available (bool | None): True if update available, False if up to
                date, None if the check itself failed.
            current_release (dict | None): Info about the available release
                (only set when available=True).
            last_applied_release (dict | None): Most recently applied release.
            error (str | None): Error message if discovery failed.
    """
    conn = database.get_connection(db_path)
    last_applied = conn.execute(
        """SELECT * FROM flat_file_releases
           WHERE status IN ('applied', 'applied_legacy')
           ORDER BY detected_at DESC LIMIT 1"""
    ).fetchone()
    last_row = dict(last_applied) if last_applied else None

    try:
        resp = requests.get(
            f"{_PAGE_URL}?t={int(datetime.now(UTC).timestamp())}",
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("flat_file discover: page fetch failed: %s", exc)
        return {
            "available": None,
            "current_release": None,
            "last_applied_release": last_row,
            "error": str(exc),
        }

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find anchor matching the flat-file zip (not the exe/db-version zip)
    anchor = None
    for a in soup.find_all("a", href=True):
        if _ZIP_PATTERN.search(a["href"]):
            anchor = a
            break

    if not anchor:
        return {
            "available": None,
            "current_release": None,
            "last_applied_release": last_row,
            "error": "Could not find flat file download link on page.",
        }

    href = anchor["href"]
    zip_filename = Path(href).name
    m = _ZIP_PATTERN.search(zip_filename)
    last_lb_in_name = int(m.group(1)) if m else None

    # Resolve to absolute URL
    from urllib.parse import urljoin
    zip_url = urljoin(_PAGE_URL, href)

    # Parse page-displayed timestamp from surrounding text
    page_text = soup.get_text()
    ts_match = re.search(r"this page was updated:\s*([^\)]+)\)", page_text)
    page_timestamp = ts_match.group(1).strip() if ts_match else None

    # Parse size from the table row containing this anchor
    row_text = ""
    parent = anchor.parent
    while parent and parent.name not in ("tr", "table", "body"):
        parent = parent.parent
    if parent and parent.name == "tr":
        row_text = parent.get_text()
    zip_size_bytes = _parse_size(row_text)

    # HEAD request for Last-Modified header
    http_last_modified = None
    try:
        head = requests.head(zip_url, timeout=10, allow_redirects=True)
        http_last_modified = head.headers.get("Last-Modified")
    except Exception as exc:
        logger.debug("flat_file HEAD failed: %s", exc)

    current: dict = {
        "zip_filename": zip_filename,
        "zip_url": zip_url,
        "last_lb_in_name": last_lb_in_name,
        "page_timestamp": page_timestamp,
        "http_last_modified": http_last_modified,
        "zip_size_bytes": zip_size_bytes,
        "source_page_url": _PAGE_URL,
    }

    # Determine whether this constitutes a new release
    available = False
    if not last_row:
        available = True
    else:
        if (
            current["zip_filename"] != last_row.get("zip_filename")
            or current["page_timestamp"] != last_row.get("page_timestamp")
            or (
                http_last_modified
                and http_last_modified != last_row.get("http_last_modified")
            )
        ):
            available = True

    if available:
        # Avoid duplicate 'detected' rows for the same filename
        existing = conn.execute(
            """SELECT id FROM flat_file_releases
               WHERE zip_filename=? AND status IN ('detected', 'downloaded')
               LIMIT 1""",
            (zip_filename,),
        ).fetchone()
        if not existing:
            _zip_fn = zip_filename
            _ivals = (
                current["source_page_url"], zip_url, zip_filename, last_lb_in_name,
                page_timestamp, http_last_modified, zip_size_bytes,
            )

            def _detect(c) -> None:
                dup = c.execute(
                    """SELECT id FROM flat_file_releases
                       WHERE zip_filename=? AND status IN ('detected', 'downloaded')
                       LIMIT 1""",
                    (_zip_fn,),
                ).fetchone()
                if not dup:
                    c.execute(
                        """INSERT INTO flat_file_releases
                           (source_page_url, zip_url, zip_filename, last_lb_in_name,
                            page_timestamp, http_last_modified, zip_size_bytes, status)
                           VALUES (?,?,?,?,?,?,?,'detected')""",
                        _ivals,
                    )

            database.get_write_queue().execute(_detect)
            logger.info("flat_file: new release detected: %s", zip_filename)
        # Fetch the id for the response
        release_row = conn.execute(
            """SELECT * FROM flat_file_releases
               WHERE zip_filename=? AND status IN ('detected', 'downloaded')
               ORDER BY detected_at DESC LIMIT 1""",
            (zip_filename,),
        ).fetchone()
        if release_row:
            current["id"] = release_row["id"]

    return {
        "available": available,
        "current_release": current if available else None,
        "last_applied_release": last_row,
        "error": None,
    }


def download_flat_file_release(
    release_id: int,
    progress_cb: Callable[[int, int], None] | None = None,
    db_path=None,
) -> Path:
    """Download the zip for a detected release.

    Args:
        release_id: Row id in flat_file_releases.
        progress_cb: Optional callback(bytes_downloaded, total_bytes) for
            progress reporting.
        db_path: Optional DB path override.

    Returns:
        Path to the downloaded zip file.

    Raises:
        ValueError: If no release with the given id exists.
        requests.HTTPError: If the download request fails.
    """
    conn = database.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM flat_file_releases WHERE id=?", (release_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"No flat_file_release with id={release_id}")

    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _DOWNLOADS_DIR / row["zip_filename"]

    resp = requests.get(row["zip_url"], stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    done = 0

    hasher = hashlib.sha256()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            hasher.update(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)

    sha256 = hasher.hexdigest()
    _sha, _sz, _rid = sha256, dest.stat().st_size, release_id
    database.get_write_queue().execute(
        lambda c: c.execute(
            """UPDATE flat_file_releases
               SET zip_sha256=?, zip_size_bytes=?,
                   downloaded_at=CURRENT_TIMESTAMP, status='downloaded'
               WHERE id=?""",
            (_sha, _sz, _rid),
        )
    )
    logger.info(
        "flat_file: downloaded %s (sha256=%s)", dest.name, sha256
    )
    return dest


def diff_flat_file_release(release_id: int, db_path=None) -> dict:
    """Compute what would change if this release were applied, without applying it.

    Loads the zip into an in-memory SQLite table and compares against the
    live checksums table.

    Args:
        release_id: Row id in flat_file_releases (must be in 'downloaded' status).
        db_path: Optional DB path override.

    Returns:
        dict with keys: rows_added, rows_changed, rows_removed,
        new_lb_min, new_lb_max.

    Raises:
        ValueError: If release not found or not in 'downloaded' state.
        FileNotFoundError: If the downloaded zip is missing from disk.
    """
    conn = database.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM flat_file_releases WHERE id=?", (release_id,)
    ).fetchone()
    if not row or row["status"] not in ("downloaded",):
        raise ValueError(f"Release {release_id} not in 'downloaded' state")

    zip_path = _DOWNLOADS_DIR / row["zip_filename"]
    if not zip_path.exists():
        raise FileNotFoundError(f"Downloaded zip not found: {zip_path}")

    incoming = _load_txt_from_zip(zip_path)

    # Build dicts keyed by (checksum, lb_number)
    current_rows: dict[tuple, dict] = {
        (r["checksum"], r["lb_number"]): dict(r)
        for r in conn.execute(
            "SELECT checksum, lb_number, filename, chk_type, xref FROM checksums"
        )
    }
    incoming_rows: dict[tuple, dict] = {
        (chk, lb): {
            "checksum": chk,
            "filename": fn,
            "chk_type": ct,
            "lb_number": lb,
            "xref": xref,
        }
        for chk, fn, ct, lb, xref in incoming
    }

    added = [v for k, v in incoming_rows.items() if k not in current_rows]
    removed = [v for k, v in current_rows.items() if k not in incoming_rows]
    changed = [
        {"incoming": inc, "current": current_rows[k]}
        for k, inc in incoming_rows.items()
        if k in current_rows
        and (
            inc.get("filename") != current_rows[k].get("filename")
            or inc.get("xref") != current_rows[k].get("xref")
        )
    ]

    new_lbs = [r["lb_number"] for r in added]
    return {
        "rows_added": len(added),
        "rows_changed": len(changed),
        "rows_removed": len(removed),
        "new_lb_min": min(new_lbs) if new_lbs else None,
        "new_lb_max": max(new_lbs) if new_lbs else None,
    }


def apply_flat_file_release(release_id: int, db_path=None) -> dict:
    """Apply a downloaded flat-file release to the database.

    Takes an automatic DB backup first. Updates the checksums table (adds,
    changes, removes rows) and writes flat_file_changelog rows for every
    operation. Triggers lb_master reconciliation for all touched LBs and
    calls migrate_lb_master() to extend to any new max LB.

    Args:
        release_id: Row id in flat_file_releases (must be in 'downloaded' status).
        db_path: Optional DB path override.

    Returns:
        dict with keys: rows_added, rows_changed, rows_removed,
        new_lb_min, new_lb_max.

    Raises:
        ValueError: If release not found or not in the expected state.
    """
    conn = database.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM flat_file_releases WHERE id=?", (release_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Release {release_id} not found")
    if row["status"] != "downloaded":
        raise ValueError(
            f"Release {release_id} status is '{row['status']}', expected 'downloaded'"
        )

    database.backup_database(f"pre_flat_apply_{row['zip_filename']}", db_path)

    zip_path = _DOWNLOADS_DIR / row["zip_filename"]
    incoming = _load_txt_from_zip(zip_path)

    current_rows: dict[tuple, dict] = {
        (r["checksum"], r["lb_number"]): dict(r)
        for r in conn.execute(
            "SELECT checksum, lb_number, filename, chk_type, xref FROM checksums"
        )
    }
    incoming_rows: dict[tuple, dict] = {
        (chk, lb): {
            "checksum": chk,
            "filename": fn,
            "chk_type": ct,
            "lb_number": lb,
            "xref": xref,
        }
        for chk, fn, ct, lb, xref in incoming
    }

    # Pre-compute all mutations so they can be submitted as one atomic queue item
    touched_lbs: set[int] = set()
    _chk_add: list = []
    _log_add: list = []
    _chk_upd: list = []
    _log_chg: list = []
    _chk_del: list = []
    _log_rem: list = []

    for k, inc in incoming_rows.items():
        if k not in current_rows:
            _chk_add.append((inc["checksum"], inc["lb_number"], inc["filename"],
                             inc.get("chk_type", ""), inc.get("xref", 0)))
            _log_add.append((release_id, inc["lb_number"], "add", inc["checksum"],
                             inc["filename"], inc.get("chk_type", ""), inc.get("xref", 0)))
            touched_lbs.add(inc["lb_number"])

    for k, inc in incoming_rows.items():
        if k in current_rows:
            cur = current_rows[k]
            if inc.get("filename") != cur.get("filename") or inc.get("xref") != cur.get("xref"):
                _chk_upd.append((inc["filename"], inc.get("xref", 0),
                                 inc["checksum"], inc["lb_number"]))
                _log_chg.append((release_id, inc["lb_number"], "change", inc["checksum"],
                                 inc["filename"], inc.get("chk_type", ""), inc.get("xref", 0),
                                 cur["filename"], cur.get("xref", 0)))
                touched_lbs.add(inc["lb_number"])

    for k, cur in current_rows.items():
        if k not in incoming_rows:
            _chk_del.append((cur["checksum"], cur["lb_number"]))
            _log_rem.append((release_id, cur["lb_number"], "remove", cur["checksum"],
                             cur["filename"], cur.get("chk_type", ""), cur.get("xref", 0)))
            touched_lbs.add(cur["lb_number"])

    rows_added = len(_chk_add)
    rows_changed = len(_chk_upd)
    rows_removed = len(_chk_del)
    touched_list = sorted(touched_lbs)
    new_lb_min = min(touched_list) if touched_list else None
    new_lb_max = max(touched_list) if touched_list else None

    _rel_id = release_id
    _ra, _rc, _rr = rows_added, rows_changed, rows_removed
    _nlmin, _nlmax = new_lb_min, new_lb_max

    def _apply_writes(c) -> None:
        if _chk_add:
            c.executemany(
                "INSERT OR IGNORE INTO checksums "
                "(checksum, lb_number, filename, chk_type, xref) VALUES (?,?,?,?,?)",
                _chk_add,
            )
        if _log_add:
            c.executemany(
                "INSERT INTO flat_file_changelog "
                "(release_id, lb_number, op, checksum, filename, chk_type, xref) "
                "VALUES (?,?,?,?,?,?,?)",
                _log_add,
            )
        if _chk_upd:
            c.executemany(
                "UPDATE checksums SET filename=?, xref=? WHERE checksum=? AND lb_number=?",
                _chk_upd,
            )
        if _log_chg:
            c.executemany(
                "INSERT INTO flat_file_changelog "
                "(release_id, lb_number, op, checksum, filename, chk_type, "
                "xref, old_filename, old_xref) VALUES (?,?,?,?,?,?,?,?,?)",
                _log_chg,
            )
        if _chk_del:
            c.executemany(
                "DELETE FROM checksums WHERE checksum=? AND lb_number=?",
                _chk_del,
            )
        if _log_rem:
            c.executemany(
                "INSERT INTO flat_file_changelog "
                "(release_id, lb_number, op, checksum, filename, chk_type, xref) "
                "VALUES (?,?,?,?,?,?,?)",
                _log_rem,
            )
        c.execute(
            """UPDATE flat_file_releases
               SET status='applied', applied_at=CURRENT_TIMESTAMP,
                   rows_added=?, rows_changed=?, rows_removed=?,
                   new_lb_min=?, new_lb_max=?
               WHERE id=?""",
            (_ra, _rc, _rr, _nlmin, _nlmax, _rel_id),
        )

    database.get_write_queue().execute(_apply_writes)

    # Update meta keys to reflect the new state (each goes through queue separately)
    database.set_meta("import_hash", row["zip_sha256"] or "", db_path)
    database.set_meta(
        "last_import_date",
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        db_path,
    )
    if new_lb_max:
        database.set_meta("last_lb_number", str(new_lb_max), db_path)

    # Reconcile lb_master for every touched LB number
    for lb in touched_list:
        database.reconcile_lb_status(lb, trigger="flat_file_apply", db_path=db_path)
    # Extend lb_master range if new LBs were added
    database.migrate_lb_master(db_path)

    logger.info(
        "flat_file: applied release %d — +%d ~%d -%d",
        release_id, rows_added, rows_changed, rows_removed,
    )
    return {
        "rows_added": rows_added,
        "rows_changed": rows_changed,
        "rows_removed": rows_removed,
        "new_lb_min": new_lb_min,
        "new_lb_max": new_lb_max,
    }


def defer_flat_file_release(
    release_id: int,
    days: int | None = None,
    until_next: bool = False,
    db_path=None,
) -> None:
    """Defer prompting for a detected release.

    Args:
        release_id: Row id in flat_file_releases.
        days: Number of days to defer (mutually exclusive with until_next).
        until_next: If True, defer until a new release supersedes this one
            (sets deferred_until to a far-future sentinel date).
        db_path: Optional DB path override.

    Raises:
        ValueError: If neither days nor until_next is specified.
    """
    if until_next:
        deferred_until = "9999-12-31 00:00:00"
    elif days is not None:
        deferred_until = (datetime.now(UTC) + timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        raise ValueError("Either days or until_next must be specified")
    _du, _rid = deferred_until, release_id
    database.get_write_queue().execute(
        lambda c: c.execute(
            "UPDATE flat_file_releases SET status='deferred', deferred_until=? WHERE id=?",
            (_du, _rid),
        )
    )
    logger.info(
        "flat_file: deferred release %d until %s", release_id, deferred_until
    )


def get_releases(db_path=None) -> list[dict]:
    """Return all flat_file_releases rows, newest first.

    Args:
        db_path: Optional DB path override.

    Returns:
        List of dicts, one per row, ordered by detected_at DESC.
    """
    conn = database.get_connection(db_path)
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM flat_file_releases ORDER BY detected_at DESC"
        )
    ]


def get_release_changelog(
    release_id: int,
    limit: int = 100,
    offset: int = 0,
    db_path=None,
) -> list[dict]:
    """Return paginated changelog rows for a release.

    Args:
        release_id: Row id in flat_file_releases.
        limit: Maximum rows to return.
        offset: Row offset for pagination.
        db_path: Optional DB path override.

    Returns:
        List of dicts from flat_file_changelog ordered by lb_number, id.
    """
    conn = database.get_connection(db_path)
    return [
        dict(r)
        for r in conn.execute(
            """SELECT * FROM flat_file_changelog
               WHERE release_id=?
               ORDER BY lb_number, id
               LIMIT ? OFFSET ?""",
            (release_id, limit, offset),
        )
    ]
