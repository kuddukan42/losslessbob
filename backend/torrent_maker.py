"""Torrent file generation for LosslessBob collection entries.

Each LB folder produces one .torrent written to data/torrents/.
All torrents are private=True (disables DHT/PEX/LSD on all compliant clients).
Tracker list is fetched live from ngosang/trackerslist via jsDelivr and cached
in-process for the session.
"""
import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path

from backend import db
from backend.paths import TORRENTS_DIR

logger = logging.getLogger(__name__)

# ── Tracker list configuration ────────────────────────────────────────────────

TRACKER_LISTS = ["best", "all", "all_udp", "all_http", "all_https"]
_TRACKER_CDN = (
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_{name}.txt"
)

_tracker_cache: dict[str, list[str]] = {}
_tracker_lock = threading.Lock()

# Guaranteed fallback TCP (http/https) trackers injected when the fetched list
# has fewer than 2 TCP entries.
_FALLBACK_TCP_TRACKERS: list[str] = [
    "https://tracker.opentrackr.org/announce",
    "https://open.tracker.cl/announce",
]

# ── Exclusion rules ───────────────────────────────────────────────────────────

# Exact filenames always excluded
TORRENT_EXCLUDE_NAMES = frozenset({
    "rename_log.txt",
    "Thumbs.db",
    ".DS_Store",
})

# File extensions always excluded
TORRENT_EXCLUDE_EXTS = frozenset({".torrent"})

# Regex patterns matched against the filename (case-insensitive)
_EXCLUDE_PATTERNS = [
    re.compile(r'.*_mychecksums\.(ffp|md5|st5)$', re.IGNORECASE),
]


def fetch_trackers(list_name: str = "best", force_refresh: bool = False) -> list[str]:
    """Fetch and cache the tracker list from jsDelivr CDN.

    Args:
        list_name: One of TRACKER_LISTS ('best', 'all', 'all_udp', …).
        force_refresh: Bypass the in-process cache and re-fetch.

    Returns:
        List of tracker announce URLs.  Empty list on network error.
    """
    import requests as _req
    if list_name not in TRACKER_LISTS:
        list_name = "best"
    with _tracker_lock:
        if not force_refresh and list_name in _tracker_cache:
            return _tracker_cache[list_name]
    try:
        url = _TRACKER_CDN.format(name=list_name)
        resp = _req.get(url, timeout=15)
        resp.raise_for_status()
        trackers = [line.strip() for line in resp.text.splitlines() if line.strip()]
    except Exception as exc:
        logger.warning("Could not fetch tracker list '%s': %s", list_name, exc)
        trackers = []
    with _tracker_lock:
        _tracker_cache[list_name] = trackers
    return trackers


def _ensure_tcp_trackers(trackers: list[str]) -> list[str]:
    """Ensure at least 2 TCP (http/https) trackers are present.

    If the list has fewer than 2 http/https entries, injects from
    _FALLBACK_TCP_TRACKERS until the minimum is met.
    """
    tcp_count = sum(1 for t in trackers if t.startswith(("http://", "https://")))
    if tcp_count >= 2:
        return trackers
    needed = 2 - tcp_count
    extras = [t for t in _FALLBACK_TCP_TRACKERS if t not in trackers][:needed]
    if extras:
        logger.info("Injecting %d fallback TCP tracker(s) to meet minimum: %s", len(extras), extras)
    return trackers + extras


def _is_excluded(path: Path) -> bool:
    """Return True if the file at path should be excluded from the torrent."""
    name = path.name
    if name in TORRENT_EXCLUDE_NAMES:
        return True
    if path.suffix.lower() in TORRENT_EXCLUDE_EXTS:
        return True
    for pat in _EXCLUDE_PATTERNS:
        if pat.match(name):
            return True
    return False


def _parse_date(date_str: str) -> str:
    """Convert LosslessBob date_str (M/D/YY or M/D/YYYY) to YYYY-MM-DD.

    Unknown month/day components written as ``xx`` are preserved as ``xx``
    in the output (e.g. ``xx/xx/65`` -> ``1965-xx-xx``, ``3/xx/72`` ->
    ``1972-03-xx``), matching the ISO-style placeholders already used by
    existing folder names. Falls back to the original string when parsing
    fails entirely (e.g. an unparseable year).
    """
    if not date_str:
        return ""
    parts = date_str.split("/")
    if len(parts) != 3:
        return date_str.strip()
    month_str, day_str, year_str = (p.strip() for p in parts)
    try:
        year = int(year_str)
        if year < 100:
            year = 1900 + year if year >= 49 else 2000 + year
        month = "xx" if month_str.lower() == "xx" else f"{int(month_str):02d}"
        day = "xx" if day_str.lower() == "xx" else f"{int(day_str):02d}"
        return f"{year:04d}-{month}-{day}"
    except ValueError:
        return date_str.strip()


def _torrent_name(lb_number: int, db_path=None) -> str:
    """Build the torrent name string from the entries table.

    Format: ``YYYY-MM-DD Location (LB-XXXXX)``
    Falls back to ``LB-XXXXX`` when entry metadata is unavailable.
    """
    entry_data = db.get_entry(lb_number, db_path=db_path)
    if entry_data:
        entry = entry_data.get("entry", {})
        date_str = _parse_date(entry.get("date_str") or "")
        location = (entry.get("location") or "").strip()
        if date_str and location:
            return f"{date_str} {location} (LB-{lb_number:05d})"
        if location:
            return f"{location} (LB-{lb_number:05d})"
    return f"LB-{lb_number:05d}"


def make_torrent(
    lb_number: int,
    source_folder: str | Path,
    tracker_list: str = "best",
    force_refresh_trackers: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    db_path=None,
) -> dict:
    """Generate a .torrent file for one LB entry folder.

    Fetches trackers, builds the torf.Torrent, hashes all included files,
    writes the .torrent to data/torrents/, and inserts a record into the
    torrents table.

    Args:
        lb_number: LosslessBob entry number.
        source_folder: Absolute path to the recording folder on disk.
        tracker_list: Tracker list name (see TRACKER_LISTS).
        force_refresh_trackers: Re-fetch tracker list even if cached.
        on_progress: Optional callback(pieces_done, pieces_total).
        db_path: DB path override for testing.

    Returns:
        Dict with keys: torrent_path, infohash, torrent_id, excluded_files, name.
        On error raises RuntimeError with a description.
    """
    try:
        from torf import TorfError, Torrent
    except ImportError as exc:
        raise RuntimeError("torf is not installed. Run: pip install torf") from exc

    source = Path(source_folder)
    if not source.is_dir():
        raise RuntimeError(f"Source folder not found: {source}")

    TORRENTS_DIR.mkdir(parents=True, exist_ok=True)

    name = _torrent_name(lb_number, db_path=db_path)
    trackers = fetch_trackers(tracker_list, force_refresh=force_refresh_trackers)
    trackers = _ensure_tcp_trackers(trackers)

    # Collect excluded filenames relative to source root
    excluded: list[str] = []
    for f in source.rglob("*"):
        if f.is_file() and _is_excluded(f):
            excluded.append(str(f.relative_to(source)))

    t = Torrent(
        path=source,
        name=name,
        private=True,
    )
    if trackers:
        t.trackers = trackers

    # Apply exclusion: use exclude_regexs for exact-name matches and patterns
    excl_regexs = []
    for excl_name in TORRENT_EXCLUDE_NAMES:
        excl_regexs.append(re.escape(excl_name) + "$")
    for ext in TORRENT_EXCLUDE_EXTS:
        excl_regexs.append(re.escape(ext) + "$")
    for pat in _EXCLUDE_PATTERNS:
        excl_regexs.append(pat.pattern)
    t.exclude_regexs = excl_regexs

    def _cb(torrent, filepath, pieces_done, pieces_total):
        if on_progress and pieces_total:
            on_progress(pieces_done, pieces_total)

    try:
        t.generate(callback=_cb, interval=0.5)
    except TorfError as exc:
        raise RuntimeError(f"Torrent generation failed: {exc}") from exc

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", name)
    out_path = TORRENTS_DIR / f"{safe_name}.torrent"
    # Avoid overwriting if the exact file already exists
    counter = 1
    while out_path.exists():
        out_path = TORRENTS_DIR / f"{safe_name}_{counter}.torrent"
        counter += 1

    try:
        t.write(out_path)
    except TorfError as exc:
        raise RuntimeError(f"Could not write .torrent file: {exc}") from exc

    infohash = t.infohash or ""
    torrent_id = db.add_torrent_record(
        lb_number=lb_number,
        torrent_path=str(out_path),
        source_folder=str(source),
        infohash=infohash,
        excluded_files=excluded,
        db_path=db_path,
    )

    return {
        "torrent_path": str(out_path),
        "infohash": infohash,
        "torrent_id": torrent_id,
        "excluded_files": excluded,
        "name": name,
    }


def make_torrent_batch(
    entries: list[dict],
    tracker_list: str = "best",
    on_entry_start: Callable[[int, int, int], None] | None = None,
    on_entry_done: Callable[[int, dict], None] | None = None,
    on_error: Callable[[int, str], None] | None = None,
    db_path=None,
) -> list[dict]:
    """Generate torrents for multiple LB entries. Skip-and-continue on error.

    Args:
        entries: List of dicts with keys lb_number and source_folder.
        tracker_list: Tracker list name.
        on_entry_start: Optional callback(lb_number, index, total).
        on_entry_done: Optional callback(lb_number, result_dict).
        on_error: Optional callback(lb_number, error_message).
        db_path: DB path override for testing.

    Returns:
        List of result dicts (one per successful entry).
    """
    results = []
    total = len(entries)
    # Pre-fetch trackers once for the whole batch
    fetch_trackers(tracker_list)

    for idx, entry in enumerate(entries):
        lb = entry["lb_number"]
        folder = entry["source_folder"]
        if on_entry_start:
            on_entry_start(lb, idx, total)
        try:
            result = make_torrent(lb, folder, tracker_list=tracker_list, db_path=db_path)
            results.append(result)
            if on_entry_done:
                on_entry_done(lb, result)
        except Exception as exc:
            msg = str(exc)
            logger.error("make_torrent failed for LB-%d: %s", lb, msg)
            if on_error:
                on_error(lb, msg)
    return results
