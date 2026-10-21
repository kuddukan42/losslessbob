import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path

from pybloom_live import ScalableBloomFilter as _SBF

from backend.checksum_utils import _APOSTROPHE_TRANS  # reused for title normalization
from backend.db_queue import get_write_queue, init_write_queue  # DB-09
from backend.paths import (
    DB_PATH,  # noqa: F401  — re-exported for callers
    SITE_BASE_URL,
    detail_url,
    to_long_path,
)

logger = logging.getLogger(__name__)

# --- Thread-local persistent connection pool (DB-02) ---
_local = threading.local()

# _write_lock retained for the import_master_db() ATTACH/DETACH workflow which
# needs to hold a broader lock across multiple statements that cannot be split
# into a single queue callable (ATTACH/DETACH are connection-level, not
# transaction-level, and must run on the same connection as the DML).
_write_lock = threading.RLock()

# --- Bloom filter for fast NOT-FOUND short-circuit (DB-07) ---
_bloom: _SBF | None = None
_bloom_db_path: str | None = None  # path the filter was built from (BUG-187)
_bloom_count: int | None = None  # checksums row count the filter was built from (BUG-261)
_bloom_lock = threading.Lock()
_bloom_rebuilding: set[str] = set()  # db paths with a rebuild in flight


_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_SHA1_RE = re.compile(r'^([0-9a-fA-F]{40})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)
_AUDIO_EXTS = {'.flac', '.shn', '.wav', '.ape', '.m4a', '.wv', '.aif', '.aiff'}

TRACKED_ENTRY_FIELDS = ("date_str", "location", "cdr", "rating", "timing",
                        "description", "setlist", "status")

_LB_MISSING_SEEDS: tuple[int, ...] = (
    7, 36, 42, 63, 65, 241, 288, 374, 375, 433,
    1346, 1407, 1455, 1614, 1641, 1768, 1909, 2101,
    2685, 2799, 2835, 3108, 3305, 3327, 3328, 3976,
    4408, 8989, 9284, 9743, 11748, 12132, 12191, 12345,
    13797, 14215,
)


def get_connection(db_path=None):
    """Return a persistent per-thread SQLite connection with WAL and performance PRAGMAs."""
    path = str(to_long_path(Path(db_path or DB_PATH)))
    cache = getattr(_local, "connections", None)
    if cache is None:
        _local.connections = {}
        cache = _local.connections
    if path not in cache:
        conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
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


def close_connection(db_path) -> None:
    """Close and evict the per-thread connection for *db_path*.

    Call this after deleting a temporary database file so the stale handle is
    not returned by the next get_connection() call on the same thread.

    Args:
        db_path: Database path, or None/falsy to resolve to the default
            DB_PATH (matching get_connection()'s own fallback).
    """
    path = str(to_long_path(Path(db_path or DB_PATH)))
    cache = getattr(_local, "connections", None)
    if cache and path in cache:
        try:
            cache[path].close()
        except Exception:
            pass
        del cache[path]


def rebuild_bloom(db_path=None):
    """Load all checksums into an in-process bloom filter. Call after import/init."""
    global _bloom, _bloom_db_path, _bloom_count
    bf = _SBF(mode=_SBF.LARGE_SET_GROWTH, error_rate=0.01)
    conn = get_connection(db_path)
    count = 0
    for row in conn.execute("SELECT checksum FROM checksums"):
        bf.add(row[0])
        count += 1
    with _bloom_lock:
        _bloom = bf
        _bloom_db_path = str(db_path or DB_PATH)
        _bloom_count = count


def _rebuild_bloom_bg(db_path=None) -> None:
    try:
        rebuild_bloom(db_path)
    except Exception:
        pass  # Non-fatal; lookups fall through to SQLite until filter is ready


def _start_bloom_rebuild(db_path=None) -> None:
    """Rebuild the bloom for *db_path* in a background thread, at most one at a time.

    Building the filter is ~13s of pure-Python hashing on a 700k-row checksums
    table and holds the GIL throughout; every concurrent request thread that
    steps a SQLite cursor convoys behind it (GET /api/library/performances went
    from 0.3s to 6s at startup). So the build is lazy — lookup_checksums()
    starts it on first need — and deduplicated per path.

    Args:
        db_path: Database path, or None for the default DB_PATH.
    """
    path = str(db_path or DB_PATH)
    with _bloom_lock:
        if path in _bloom_rebuilding:
            return
        _bloom_rebuilding.add(path)

    def _run() -> None:
        try:
            _rebuild_bloom_bg(db_path)
        finally:
            with _bloom_lock:
                _bloom_rebuilding.discard(path)
            close_connection(db_path)  # fire-and-forget thread (BUG-263)

    threading.Thread(target=_run, name="bloom-rebuild", daemon=True).start()


def checksum_in_bloom(chk: str) -> bool:
    """Returns False only if chk is DEFINITELY not in DB. True means possible match."""
    with _bloom_lock:
        if _bloom is None:
            return True
        return chk in _bloom


def init_db(db_path=None):
    """Create schema, run migrations, rebuild FTS index if needed, seed bloom filter."""
    init_write_queue(str(db_path or DB_PATH))
    with _write_lock:
        conn = get_connection(db_path)
        conn.executescript(SCHEMA_SQL)
        # checksum_disputes lives with its module (backend.checksum_provenance) so the
        # DDL sits next to the code that interprets it; imported here so a fresh DB
        # still gets the table.
        from backend import checksum_provenance
        checksum_provenance.ensure_schema(conn)
        from backend import wtrf_discovery
        wtrf_discovery.ensure_schema(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
        if "status" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN status TEXT DEFAULT 'ok'")
            conn.commit()
        if "taper_name" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN taper_name TEXT")
            conn.execute("ALTER TABLE entries ADD COLUMN source_chain TEXT")
            conn.commit()
            # Backfill from existing descriptions
            _rows = conn.execute(
                "SELECT lb_number, description FROM entries WHERE description IS NOT NULL AND description != ''"
            ).fetchall()
            for _lb, _desc in _rows:
                _t, _s = extract_taper_and_source(_desc)
                if _t or _s:
                    conn.execute(
                        "UPDATE entries SET taper_name=?, source_chain=? WHERE lb_number=?",
                        (_t, _s, _lb),
                    )
            conn.commit()
            logger.info(
                "entries: backfilled taper_name/source_chain for %d rows", len(_rows)
            )

        if "lb_category" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN lb_category TEXT")
            conn.commit()

        if "source_type" not in cols:
            # Curator-edited (Soundboard/Audience/FM-Pre-FM/Master/Mixed) — unlike
            # taper_name/source_chain/lb_category this is never heuristically
            # backfilled from description text; it stays NULL until a curator sets it.
            conn.execute("ALTER TABLE entries ADD COLUMN source_type TEXT")
            conn.commit()

        if "metadata_source" not in cols:
            # Provenance of the row's metadata. NULL = scraped from the public
            # site; 'private_import' = filled from tj's private-entry material
            # (TODO-245). A later successful scrape resets it to NULL via the
            # scraper's INSERT OR REPLACE, so public data always supersedes.
            conn.execute("ALTER TABLE entries ADD COLUMN metadata_source TEXT")
            conn.commit()

        # Populate FTS index if empty (first run after adding FTS)
        fts_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
        entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        if fts_count == 0 and entry_count > 0:
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
            conn.commit()

        # One-time cleanup: fix entries that stored the server's soft-404 error page
        # as their description (server returned HTTP 200 with a 404 error HTML body).
        soft_404_affected = conn.execute(
            "UPDATE entries SET status='missing', date_str='', location='', cdr='', "
            "rating='', timing='', description='', setlist='' "
            "WHERE description LIKE '%The requested URL was not found on this server%'"
        ).rowcount
        if soft_404_affected > 0:
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        # One-time fix: performances-sourced geocodes stored 'low' confidence because
        # Nominatim importance penalises specific venues.  Promote them to 'medium'.
        conn.execute(
            "UPDATE location_geocoded SET confidence='medium' "
            "WHERE source='performances' AND confidence='low'"
        )
        # Migration: add lb_number column to location_geocoded (TODO-099)
        _geo_cols = [r[1] for r in conn.execute("PRAGMA table_info(location_geocoded)").fetchall()]
        if "lb_number" not in _geo_cols:
            conn.execute("ALTER TABLE location_geocoded ADD COLUMN lb_number TEXT")
        # Migration: add lbdir_verified_at to my_collection
        _mc_cols = [r[1] for r in conn.execute("PRAGMA table_info(my_collection)").fetchall()]
        if "lbdir_verified_at" not in _mc_cols:
            conn.execute("ALTER TABLE my_collection ADD COLUMN lbdir_verified_at TIMESTAMP")
        # Migration: add mount_id to integrity_events (TODO-284)
        _ie_cols = [r[1] for r in conn.execute("PRAGMA table_info(integrity_events)").fetchall()]
        if "mount_id" not in _ie_cols:
            conn.execute("ALTER TABLE integrity_events ADD COLUMN mount_id INTEGER")
        # Migration: Olof columns for the show-dossier redesign (TODO-342 Phase 1) —
        # the rotation stat and the venue-history blob move out of notes, and
        # parenthetical subtitles out of credits.
        _oe_cols = {r[1] for r in conn.execute("PRAGMA table_info(olof_events)").fetchall()}
        for _col, _ddl in (
            ("rotation_new", "INTEGER"),
            ("rotation_pct", "INTEGER"),
            ("tour_new_count", "INTEGER"),
            ("venue_history_raw", "TEXT NOT NULL DEFAULT ''"),
        ):
            if _col not in _oe_cols:
                conn.execute(f"ALTER TABLE olof_events ADD COLUMN {_col} {_ddl}")
        _os_cols = {r[1] for r in conn.execute("PRAGMA table_info(olof_songs)").fetchall()}
        if "subtitle" not in _os_cols:
            conn.execute("ALTER TABLE olof_songs ADD COLUMN subtitle TEXT NOT NULL DEFAULT ''")
        # Migration: add files_moved to file_integrity_scans (TODO-297)
        _fis_cols = [
            r[1] for r in conn.execute("PRAGMA table_info(file_integrity_scans)").fetchall()
        ]
        if "files_moved" not in _fis_cols:
            conn.execute(
                "ALTER TABLE file_integrity_scans ADD COLUMN files_moved INTEGER DEFAULT 0"
            )
        # Migration: tuit_song_performances was first created with
        # UNIQUE(song, date_str, venue_text), which silently collapsed the two
        # shows some dates carry (an afternoon and an evening at one venue render
        # the same text). Rebuild it with show_id in the key; the table is a pure
        # scrape cache, so dropping it costs only a re-sync.
        _tsp = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table'"
            " AND name='tuit_song_performances'"
        ).fetchone()
        if _tsp and "UNIQUE(song, date_str, venue_text)" in (_tsp["sql"] or ""):
            conn.execute("DROP TABLE tuit_song_performances")
            conn.execute("UPDATE tuit_songs SET scraped_at=NULL, n_listed=NULL")
            conn.executescript(SCHEMA_SQL)  # recreate it with the new key

        # Migration: add source to tuit_venues — the /venue register's paginated
        # listing is unstable (no tiebreak on its sort), so it both repeats and
        # drops rows; venues recovered from tuit_shows are marked 'shows'.
        _tv_cols = [r[1] for r in conn.execute("PRAGMA table_info(tuit_venues)").fetchall()]
        if _tv_cols and "source" not in _tv_cols:
            conn.execute(
                "ALTER TABLE tuit_venues ADD COLUMN source TEXT DEFAULT 'register'"
            )
        # Migration: add city_lat/city_lon/city_state to setlistfm_shows (TODO-222) —
        # setlist.fm's API returns venue.city.coords + stateCode on every setlist;
        # storing them gives a zero-geocoding, guaranteed city-level coordinate.
        _sfs_cols = [r[1] for r in conn.execute("PRAGMA table_info(setlistfm_shows)").fetchall()]
        if "city_lat" not in _sfs_cols:
            conn.execute("ALTER TABLE setlistfm_shows ADD COLUMN city_lat REAL")
            conn.execute("ALTER TABLE setlistfm_shows ADD COLUMN city_lon REAL")
            conn.execute(
                "ALTER TABLE setlistfm_shows ADD COLUMN city_state TEXT NOT NULL DEFAULT ''"
            )
        # Migration: add review_flag/review_reason to tapematch_family_meta —
        # carries the tapematch-batch skill's human "needs review" verdict
        # (parsed from each run's analysis.md) into the synced family rows.
        _tmm_cols = [r[1] for r in conn.execute("PRAGMA table_info(tapematch_family_meta)").fetchall()]
        if "review_flag" not in _tmm_cols:
            conn.execute(
                "ALTER TABLE tapematch_family_meta ADD COLUMN review_flag INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute("ALTER TABLE tapematch_family_meta ADD COLUMN review_reason TEXT")
        # Migration: add auto_triage/auto_triage_reasons to tapematch_family_meta —
        # backend.tapematch_autoflag's machine-derived 'clear'/'attention' verdict,
        # computed from observations.db for every date including the ~57% with no
        # analysis.md.  Deliberately separate from review_flag/review_reason: those
        # mean a human read the prose, this is a ~0.19-precision prioritisation hint.
        if "auto_triage" not in _tmm_cols:
            conn.execute("ALTER TABLE tapematch_family_meta ADD COLUMN auto_triage TEXT")
            conn.execute(
                "ALTER TABLE tapematch_family_meta ADD COLUMN auto_triage_reasons TEXT"
            )
        # Migration: add calibration_hash to tapematch_family_meta (TODO-333) —
        # the identity of the tapematch config that produced this family,
        # carried through from observations.db runs.calibration_hash so a family
        # can be asked which calibration decided it. NULL = run predates the
        # column; that is "unknown provenance", not "current".
        if "calibration_hash" not in _tmm_cols:
            conn.execute("ALTER TABLE tapematch_family_meta ADD COLUMN calibration_hash TEXT")
        # Migration: add local_sha256 to site_inventory (preservation stack B1) —
        # body_sha256 is the hash of the raw HTTP body, but HTML is saved
        # link-rewritten, so it can never match the file on disk.  local_sha256
        # records the on-disk bytes, giving the mirror a verifiable baseline.
        _si_cols = [r[1] for r in conn.execute("PRAGMA table_info(site_inventory)").fetchall()]
        if "local_sha256" not in _si_cols:
            conn.execute("ALTER TABLE site_inventory ADD COLUMN local_sha256 TEXT")
        # Cleanup: upsert_inventory once bound the literal string 'CURRENT_TIMESTAMP'
        # into the crawl timestamps. The real times are unrecoverable — null them.
        for _col in ("last_fetched_at", "last_checked_at"):
            conn.execute(
                f"UPDATE site_inventory SET {_col}=NULL WHERE {_col}='CURRENT_TIMESTAMP'"
            )
        # Migration: wtrf_downloads.seed_folder — the folder (collection or
        # overlay) that was actually handed to qBittorrent, mirroring
        # tuit_downloads.seed_folder. Added when WTRF gained seed-from-links.
        _wd_cols = [r[1] for r in conn.execute("PRAGMA table_info(wtrf_downloads)").fetchall()]
        if "seed_folder" not in _wd_cols:
            conn.execute("ALTER TABLE wtrf_downloads ADD COLUMN seed_folder TEXT")
        # Migration: collection_mounts / collection_routes tables (pipeline step 5)
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
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('pipeline_file_mode', 'move')"
        )
        # Migration: recreate lb_master when the schema is missing 'nonexistent' status or
        # public_no_checksums column.  SQLite only supports CHECK changes via table recreation.
        _lbm_schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='lb_master'"
        ).fetchone()
        _lbm_schema_sql = _lbm_schema_row[0] if _lbm_schema_row else ""
        if _lbm_schema_sql and (
            "nonexistent" not in _lbm_schema_sql or "public_no_checksums" not in _lbm_schema_sql
        ):
            _pnc_col = "public_no_checksums" if "public_no_checksums" in [
                r[1] for r in conn.execute("PRAGMA table_info(lb_master)").fetchall()
            ] else "0"
            conn.executescript(f"""
                PRAGMA foreign_keys = OFF;
                CREATE TABLE lb_master_new (
                    lb_number            INTEGER PRIMARY KEY,
                    lb_status            TEXT NOT NULL CHECK (lb_status IN
                                            ('public','private','missing','nonexistent')),
                    has_webpage          INTEGER NOT NULL DEFAULT 0,
                    has_checksums        INTEGER NOT NULL DEFAULT 0,
                    has_attachments      INTEGER NOT NULL DEFAULT 0,
                    first_seen_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_status_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    previous_status      TEXT,
                    manual_override      INTEGER NOT NULL DEFAULT 0,
                    manual_status        TEXT,
                    manual_notes         TEXT,
                    manual_set_by        TEXT,
                    manual_set_at        TIMESTAMP,
                    needs_review         INTEGER NOT NULL DEFAULT 0,
                    public_no_checksums  INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO lb_master_new
                    (lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                     first_seen_at, last_status_at, previous_status, manual_override,
                     manual_status, manual_notes, manual_set_by, manual_set_at,
                     needs_review, public_no_checksums)
                SELECT lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                       first_seen_at, last_status_at, previous_status, manual_override,
                       manual_status, manual_notes, manual_set_by, manual_set_at,
                       needs_review, {_pnc_col}
                FROM lb_master;
                DROP TABLE lb_master;
                ALTER TABLE lb_master_new RENAME TO lb_master;
                CREATE INDEX IF NOT EXISTS idx_lb_master_status
                    ON lb_master(lb_status);
                CREATE INDEX IF NOT EXISTS idx_lb_master_override
                    ON lb_master(manual_override) WHERE manual_override = 1;
                CREATE INDEX IF NOT EXISTS idx_lb_master_review
                    ON lb_master(needs_review) WHERE needs_review = 1;
                CREATE INDEX IF NOT EXISTS idx_lb_master_public_no_chk
                    ON lb_master(public_no_checksums) WHERE public_no_checksums = 1;
                PRAGMA foreign_keys = ON;
            """)

        # Ensure index exists whether table was just created or just migrated.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lb_master_public_no_chk"
            " ON lb_master(public_no_checksums) WHERE public_no_checksums = 1"
        )

        # Migration: seed lb_missing with confirmed-not-existing LB numbers.
        for _seed_lb in _LB_MISSING_SEEDS:
            conn.execute(
                "INSERT OR IGNORE INTO lb_missing(lb_number, confirmed_date, notes)"
                " VALUES(?, '2026-05-26', 'Confirmed: LB number allocated but page never existed.')",
                (_seed_lb,),
            )

        # Migration: backfill setlist from description for entries that were scraped
        # before the scraper learned to detect track-listing paragraphs.
        # Gated by a meta flag so it only runs once.
        if not conn.execute("SELECT 1 FROM meta WHERE key='setlist_backfill_v1'").fetchone():
            _need_backfill = conn.execute(
                "SELECT lb_number, description FROM entries "
                "WHERE (setlist IS NULL OR length(setlist) <= 10) "
                "AND description IS NOT NULL AND length(description) > 30"
            ).fetchall()
            _backfilled = 0
            for _row in _need_backfill:
                _sl = extract_setlist_from_description(_row["description"])
                if _sl:
                    conn.execute(
                        "UPDATE entries SET setlist=? WHERE lb_number=?",
                        (_sl, _row["lb_number"]),
                    )
                    _backfilled += 1
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('setlist_backfill_v1', '1')"
            )
            if _backfilled:
                conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
            logger.info(
                "entries: backfilled setlist for %d rows", _backfilled
            )

        # One-time backfill: classify entries using bobdylan_shows + dylan_performances + keywords.
        # v2 (2026-06-18, TODO-151): _PERF_CATEGORY_MAP gained GUEST/NET/SIDEMAN mappings that
        # were missing from v1 — bumped to force reclassification on existing installs.
        if not conn.execute("SELECT 1 FROM meta WHERE key='lb_category_backfill_v2'").fetchone():
            _classified = classify_entry_categories(db_path, conn=conn)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('lb_category_backfill_v2', '1')"
            )
            logger.info(
                "entries: classified lb_category for %d rows (concert=%d, unknown=%d)",
                _classified["classified"],
                _classified.get("concert", 0),
                _classified.get("unknown", 0),
            )

        # One-time migration: rename_history.renamed_at previously defaulted to
        # SQLite's CURRENT_TIMESTAMP, which is UTC. Convert existing rows to local
        # time to match the now-explicit local timestamps written going forward.
        if not conn.execute("SELECT 1 FROM meta WHERE key='rename_history_localtime_v1'").fetchone():
            conn.execute(
                "UPDATE rename_history SET renamed_at = datetime(renamed_at, 'localtime') "
                "WHERE renamed_at IS NOT NULL"
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('rename_history_localtime_v1', '1')"
            )

        # Migration: folder_lb_link composite PK to support multi-LB folder links.
        # Detected via PRAGMA table_info's pk flag rather than a raw SQL-text
        # match — sqlite_master.sql includes the original column-alignment
        # whitespace, which previously made a plain substring check silently
        # never match and left old databases stuck on the single-column PK.
        _fll_info = conn.execute("PRAGMA table_info(folder_lb_link)").fetchall()
        _fll_pk_cols = [r[1] for r in _fll_info if r[5]]
        if _fll_pk_cols == ["folder_path"]:
            _fll_has_xref = any(r[1] == "xref" for r in _fll_info)
            _fll_cols_sql = "folder_path, lb_number, linked_at, note" + (
                ", xref" if _fll_has_xref else ""
            )
            conn.executescript(f"""
                PRAGMA foreign_keys = OFF;
                CREATE TABLE folder_lb_link_new (
                    folder_path    TEXT NOT NULL,
                    lb_number      INTEGER NOT NULL,
                    linked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    note           TEXT,
                    xref           INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (folder_path, lb_number)
                );
                INSERT OR IGNORE INTO folder_lb_link_new
                    ({_fll_cols_sql})
                    SELECT {_fll_cols_sql}
                    FROM folder_lb_link;
                DROP TABLE folder_lb_link;
                ALTER TABLE folder_lb_link_new RENAME TO folder_lb_link;
                CREATE INDEX IF NOT EXISTS idx_folder_link_lb
                    ON folder_lb_link(lb_number);
                PRAGMA foreign_keys = ON;
            """)

        # Migration: add xref to folder_lb_link and my_collection
        # (FABLE_XREF_INCORPORATION.md D3). Copy-level xref: 0 = canonical
        # fileset, N = the alternate xref-N fileset this folder/copy matches.
        # Placed after the folder_lb_link PK migration above so the ALTER
        # below always targets the table's final (composite-PK) shape.
        _fll_cols = [r[1] for r in conn.execute("PRAGMA table_info(folder_lb_link)").fetchall()]
        if "xref" not in _fll_cols:
            conn.execute("ALTER TABLE folder_lb_link ADD COLUMN xref INTEGER NOT NULL DEFAULT 0")
        if "xref" not in _mc_cols:
            conn.execute("ALTER TABLE my_collection ADD COLUMN xref INTEGER NOT NULL DEFAULT 0")

        # Migration: add concert_date_iso to show_picks (LISTENING spec §9 —
        # "this night in Dylan history"). Populated by concert_ranker/picks.py
        # at recompute time; NULL until the next recompute runs.
        _sp_cols = [r[1] for r in conn.execute("PRAGMA table_info(show_picks)").fetchall()]
        if "concert_date_iso" not in _sp_cols:
            conn.execute("ALTER TABLE show_picks ADD COLUMN concert_date_iso TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_show_picks_date_iso"
                " ON show_picks(concert_date_iso)"
            )

        # Migration (C32 D3): per-show picks. show_picks gains event_id, and on a
        # two-show day an unassigned LB is ranked in both shows, so the key widens
        # to (concert_date, lb_number, event_id). SQLite can't alter a primary key:
        # rebuild once, copying the existing rows (event_id NULL until recompute).
        _sp_cols = [r[1] for r in conn.execute("PRAGMA table_info(show_picks)").fetchall()]
        if _sp_cols and "event_id" not in _sp_cols:
            conn.execute("ALTER TABLE show_picks RENAME TO show_picks_pre_c32")
            conn.execute(
                "CREATE TABLE show_picks ("
                " concert_date TEXT NOT NULL, lb_number INTEGER NOT NULL,"
                " pick_score REAL NOT NULL, pick_rank INTEGER NOT NULL,"
                " evidence_json TEXT NOT NULL, concert_date_iso TEXT,"
                " computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, event_id INTEGER,"
                " PRIMARY KEY (concert_date, lb_number, event_id))"
            )
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank,"
                " evidence_json, concert_date_iso, computed_at)"
                " SELECT concert_date, lb_number, pick_score, pick_rank, evidence_json,"
                " concert_date_iso, computed_at FROM show_picks_pre_c32"
            )
            conn.execute("DROP TABLE show_picks_pre_c32")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_show_picks_lb ON show_picks(lb_number)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_show_picks_date_iso"
                " ON show_picks(concert_date_iso)"
            )

        # Migration (TODO-311): extraction_key on quality_scans, backfilled from
        # each scan's stored config. Mirrors concert_ranker/lb/repo.py's own
        # ensure_schema migration so the freshness card can resolve the active
        # scan on a DB that has not been re-scanned since the column landed.
        _qs_cols = [r[1] for r in conn.execute("PRAGMA table_info(quality_scans)").fetchall()]
        if "extraction_key" not in _qs_cols:
            conn.execute("ALTER TABLE quality_scans ADD COLUMN extraction_key TEXT")
            from concert_ranker.lb import repo as _cr_repo
            _cr_repo.backfill_extraction_keys(conn)

        # Always commit: UPDATE above opens a Python implicit transaction regardless
        # of rowcount.  Without this, a zero-row UPDATE leaves the read connection
        # holding a RESERVED lock that blocks the write queue's first transaction.
        conn.commit()

    def _run_bg(fn) -> None:
        """Run a one-shot init_db() background task, then close its connection.

        These threads are fire-and-forget — nothing joins them or reuses their
        thread-local get_connection(db_path) cache afterward, so leaving the
        connection open for GC to eventually reclaim just holds 3 file
        descriptors (db+wal+shm in WAL mode) open indefinitely per thread.
        Harmless for a long-lived real install (one init_db() call per
        process), but a test suite calling init_db() on a fresh db_path
        hundreds of times in quick succession can exhaust the FD limit before
        GC catches up (BUG-263).
        """
        try:
            fn()
        finally:
            close_connection(db_path)

    # The bloom filter is NOT built here: lookup_checksums() builds it lazily
    # via _start_bloom_rebuild() (a startup build per init_db() call starved
    # every request of the GIL for ~30s). Lookups fall through to SQLite until
    # the filter is ready.

    # One-time backfill: populate lb_master if table is empty and checksums exist.
    # wait=False (BUG-262): nothing waits on this thread's result, so don't
    # block it against a write queue a fast-moving caller may be tearing down.
    threading.Thread(
        target=lambda: _run_bg(lambda: migrate_lb_master(db_path, wait=False)),
        daemon=True,
    ).start()

    # One-time backfill: create a synthetic applied_legacy row for pre-feature imports.
    threading.Thread(
        target=lambda: _run_bg(lambda: _bootstrap_flat_file_legacy(db_path)),
        daemon=True,
    ).start()

    # One-time import: load Dylan performance data from ODS if not yet imported.
    threading.Thread(
        target=lambda: _run_bg(lambda: import_dylan_performances(db_path)),
        daemon=True,
    ).start()


def _bootstrap_flat_file_legacy(db_path=None) -> None:
    """On first run after feature install: create a synthetic applied_legacy row from existing meta.

    If flat_file_releases is empty but a previous import_hash exists in meta,
    insert a placeholder row so the history panel is not completely empty and
    the discovery logic has a baseline to compare against.
    """
    try:
        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM flat_file_releases").fetchone()[0]
        if count > 0:
            return
        import_hash = get_meta("import_hash", db_path)
        if not import_hash:
            return
        last_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0
        last_date = get_meta("last_import_date", db_path) or ""
        _zip_name = f"Checksum_Lookup_flat_file_LastLB_{last_lb}.zip"
        get_write_queue().execute(
            lambda c: c.execute(
                """INSERT INTO flat_file_releases
                   (source_page_url, zip_url, zip_filename, last_lb_in_name, zip_sha256,
                    applied_at, status, failure_reason)
                   VALUES (?, ?, ?, ?, ?, ?, 'applied_legacy',
                           'Backfilled from pre-feature import history.')""",
                ("", "", _zip_name, last_lb, import_hash, last_date)
            )
        )
        logger.info("flat_file: bootstrapped legacy applied row (LastLB=%d)", last_lb)
    except Exception as exc:
        logger.warning("flat_file bootstrap failed: %s", exc)


def import_dylan_performances(db_path=None) -> int:
    """One-time import of the Dylan performance ODS into dylan_performances.

    Skips silently if the table already has rows. Searches DATA_DIR for a file
    matching ``*Dylan_Performance_fixed.ods`` and parses it using stdlib only
    (zipfile + xml.etree.ElementTree). Returns the number of rows inserted.
    """
    import xml.etree.ElementTree as ET
    import zipfile as _zf

    from backend.paths import DATA_DIR as _DATA

    conn = get_connection(db_path)
    if conn.execute("SELECT COUNT(*) FROM dylan_performances").fetchone()[0] > 0:
        return 0  # already imported

    candidates = sorted(_DATA.glob("*Dylan_Performance_fixed.ods"))
    if not candidates:
        logger.warning("dylan_performances: ODS file not found in %s", _DATA)
        return 0
    ods_path = candidates[-1]  # take the most recent if multiple

    NS = {
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text":  "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }

    try:
        with _zf.ZipFile(ods_path) as z:
            root = ET.fromstring(z.read("content.xml"))
    except Exception as exc:
        logger.error("dylan_performances: failed to read ODS: %s", exc)
        return 0

    sheet = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table")
    if sheet is None:
        logger.error("dylan_performances: no table element found in ODS")
        return 0

    rows = sheet.findall("table:table-row", NS)
    if not rows:
        return 0

    def _cell_text(cell) -> str:
        p = cell.find("text:p", NS)
        return (p.text or "").strip() if p is not None else ""

    records = []
    for row in rows[1:]:  # skip header
        cells = row.findall("table:table-cell", NS)
        if len(cells) < 7:
            cells = cells + [None] * (7 - len(cells))
        vals = [_cell_text(c) if c is not None else "" for c in cells[:7]]
        date_str, event_id, category, city, state, country, venue = vals
        if not event_id:
            continue
        records.append((event_id, date_str, category, city, state, country, venue))

    if not records:
        return 0

    _records = records
    get_write_queue().execute(
        lambda c: c.executemany(
            """INSERT OR IGNORE INTO dylan_performances
               (event_id, date_str, category, city, state, country, venue)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            _records,
        )
    )
    logger.info("dylan_performances: imported %d rows from %s", len(records), ods_path.name)
    return len(records)


def get_performance_by_date(date_str: str, db_path=None) -> dict | None:
    """Return the dylan_performances row for an ISO date string (YYYY-MM-DD), or None.

    When two performances share the same date (rare), returns the first and logs a
    warning so callers can decide whether to surface an ambiguity flag.

    Args:
        date_str: ISO date string, e.g. ``'1978-11-16'``.  Must already be in
                  YYYY-MM-DD format; use ``_entry_date_to_iso()`` in geocoder.py
                  to convert entries.date_str values first.
        db_path:  Optional path override; defaults to :data:`DB_PATH`.

    Returns:
        Dict with keys ``event_id``, ``date_str``, ``category``, ``city``,
        ``state``, ``country``, ``venue``; or ``None`` if no match.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT event_id, date_str, category, city, state, country, venue "
        "FROM dylan_performances WHERE date_str = ?",
        (date_str,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "get_performance_by_date: %d performances on %s — returning first",
            len(rows), date_str,
        )
    return dict(rows[0])


def get_meta(key, db_path=None):
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key, value, db_path=None):
    _k, _v = key, value
    get_write_queue().execute(
        lambda c: c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (_k, _v))
    )


def get_stats(db_path=None):
    with get_connection(db_path) as conn:
        total_checksums = conn.execute("SELECT COUNT(*) FROM checksums").fetchone()[0]
        total_lb = conn.execute("SELECT COUNT(DISTINCT lb_number) FROM checksums").fetchone()[0]
        latest_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0]
        last_import = get_meta("last_import_date", db_path)
        ok_entries = conn.execute("SELECT COUNT(*) FROM entries WHERE status='ok'").fetchone()[0]
        total_entries = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    return {
        "total_checksums": total_checksums,
        "total_lb_numbers": total_lb,
        "latest_lb": latest_lb,
        "last_import": last_import,
        "ok_entries": ok_entries,
        "total_entries": total_entries,
    }


def get_missing_lb_numbers(db_path=None) -> list[int]:
    """Return LB numbers that have no webpage on the archive site.

    An entry is "missing" only when the scraper confirmed no page exists
    (entries.status = 'missing') or the lb_number has never been scraped.
    Entries with status='ok' are real entries even if they have no checksums
    or attachments, and are never returned here.
    """
    with get_connection(db_path) as conn:
        all_rows = conn.execute(
            "SELECT lb_number, status FROM entries ORDER BY lb_number"
        ).fetchall()
    if not all_rows:
        return []
    max_lb = max(r[0] for r in all_rows)
    ok_set = {r[0] for r in all_rows if r[1] == "ok"}
    return [n for n in range(1, max_lb + 1) if n not in ok_set]


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
            if ext not in _AUDIO_EXTS:
                continue
            chk_type = 's' if ext == '.shn' else 'm'
            if chk not in results:
                results[chk] = (chk, fname, chk_type)
            continue

        # MD5/ST5: checksum *filename or checksum filename
        md5 = _MD5_RE.match(line)
        if md5:
            chk, fname = md5.group(1).lower(), md5.group(2).strip()
            ext = Path(fname).suffix.lower()
            if ext not in _AUDIO_EXTS:
                continue
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

    # Degenerate hashes (empty-file MD5/SHA-1, all-zero ffp) are non-evidence:
    # excluded from matching AND from the given/matched/unmatched counts, but
    # still listed in detail (ignored=True) so the user sees the file was read.
    degenerate_entries = [e for e in parsed_entries if _is_degenerate_checksum(e[0])]
    parsed_entries = [e for e in parsed_entries if not _is_degenerate_checksum(e[0])]

    conn = get_connection(db_path)

    # Bloom pre-filter: separate definite misses from candidates (DB-07).
    # Only use the bloom if it was built for this exact db_path (a filter built
    # from a different DB would give false negatives — BUG-187) AND its stamped
    # row count still matches the live table. init_db() rebuilds the bloom in a
    # background thread that can race ahead of a caller's own checksum inserts
    # made right after init_db() returns (same db_path, so BUG-187's guard alone
    # doesn't catch it) — an empty/partial bloom built too early would otherwise
    # report freshly-inserted checksums as false NOT FOUNDs for the rest of the
    # session (BUG-261). A live COUNT(*) mismatch means the bloom is stale: skip
    # it for this call (falls through to SQLite, always safe) and kick off a
    # fresh background rebuild so later calls get the bloom's speed back.
    active_path = str(db_path or DB_PATH)
    with _bloom_lock:
        _active_bloom = _bloom if _bloom_db_path == active_path else None
        _active_bloom_count = _bloom_count
    if _active_bloom is None:
        _start_bloom_rebuild(db_path)  # lazy first build (or after an import reset)
    else:
        live_count = conn.execute("SELECT COUNT(*) FROM checksums").fetchone()[0]
        if live_count != _active_bloom_count:
            _active_bloom = None
            _start_bloom_rebuild(db_path)
    if _active_bloom is not None:
        candidates = [e for e in parsed_entries if e[0] in _active_bloom]
        definite_misses = [e for e in parsed_entries if e[0] not in _active_bloom]
    else:
        candidates = list(parsed_entries)
        definite_misses = []
    checksums = [e[0] for e in candidates]

    # Temp-table bulk lookup — avoids dynamic IN clause and the 999-param limit (DB-04)
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
    lb_xref_to_matched: dict = {}  # (lb_number, xref_val) -> set of matched checksums

    for chk, fname, chk_type in candidates:
        if chk in matched_chks:
            matches = matched_chks[chk]
            is_duplicate = len(matches) > 1
            for m in matches:
                lb = m["lb_number"]
                lb_xref_to_matched.setdefault((lb, m["xref"]), set()).add(chk)
                status = "DUPLICATE" if is_duplicate else "MATCHED"
                detail.append({
                    "checksum": chk,
                    "filename": fname,
                    "db_filename": m["filename"],
                    "type": chk_type,
                    "lb_number": lb,
                    "xref": m["xref"],
                    "status": status,
                    "is_duplicate": is_duplicate,
                    "missing_from_set": [],
                    "detail_url": detail_url(lb),
                })
        else:
            detail.append({
                "checksum": chk,
                "filename": fname,
                "db_filename": None,
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
            "checksum": chk, "filename": fname, "db_filename": None, "type": chk_type,
            "lb_number": None, "xref": 0, "status": "NOT FOUND",
            "is_duplicate": False, "missing_from_set": [], "detail_url": None,
        })

    # Degenerate entries: visible in detail but flagged ignored so the summary
    # loop below leaves them out of unmatched/missing_from_db counts.
    for chk, fname, chk_type in degenerate_entries:
        detail.append({
            "checksum": chk, "filename": fname, "db_filename": None, "type": chk_type,
            "lb_number": None, "xref": 0, "status": "NOT FOUND",
            "is_duplicate": False, "missing_from_set": [], "detail_url": None,
            "ignored": True,
        })

    # Reverse lookup: check completeness per (lb_number, xref_value) group.
    # Evaluating per xref group means a recording that fully matches an xref variant
    # is shown as MATCHED (green) rather than INCOMPLETE — because it IS complete for
    # that xref; the primary LB set simply isn't what the user has.
    _AUDIO_EXT_RE = re.compile(r'\.(flac|shn|wav|ape|m4a|wv|aif|aiff)$', re.IGNORECASE)
    _DIR_SEP_RE = re.compile(r'^.*[/\\]')

    def _norm_track_base(filename: str) -> str:
        # Strip audio extension, then directory prefix, then normalize & → _
        # (shntool replaces & with _ in decoded WAV names; DB stores both SHN
        # and WAV entries which may also have Disc1\ prefix on one and not the other).
        base = _AUDIO_EXT_RE.sub('', filename).lower()
        base = _DIR_SEP_RE.sub('', base)
        return base.replace('&', '_')

    _lb_xref_missing: dict = {}
    for (lb, xref_val), matched_set in lb_xref_to_matched.items():
        all_rows = conn.execute(
            "SELECT checksum, filename FROM checksums WHERE lb_number=? AND xref=?",
            (lb, xref_val)
        ).fetchall()
        # Build base-filename → checksums map so that foo.shn (md5) and foo.wav
        # (shntool) are treated as the same track.  A track is covered if ANY of
        # its checksums was matched; only uncovered tracks contribute to missing.
        # Uses _norm_track_base to unify Disc1\dead&dylan.shn and dead_dylan.wav.
        base_to_chks: dict = {}
        for row in all_rows:
            base = _norm_track_base(row["filename"])
            base_to_chks.setdefault(base, set()).add(row["checksum"])
        missing: set = set()
        for row in all_rows:
            chk = row["checksum"]
            if chk in matched_set:
                continue
            # A degenerate DB row (empty-file hash, zero ffp) can never be
            # verified against disk — it must not count as missing either.
            if _is_degenerate_checksum(chk):
                continue
            base = _norm_track_base(row["filename"])
            if not (base_to_chks[base] & matched_set):
                missing.add(chk)
        _lb_xref_missing[(lb, xref_val)] = missing

    for item in detail:
        lb = item["lb_number"]
        if lb is None:
            continue
        missing = _lb_xref_missing.get((lb, item["xref"]), set())
        item["missing_from_set"] = list(missing)
        if missing and item["status"] == "MATCHED":
            item["status"] = "MATCHED (INCOMPLETE)"

    # Per-LB total missing count aggregated across all xref groups (for summary display)
    _lb_missing_count: dict = {}
    for (lb, _xv), missing_set in _lb_xref_missing.items():
        _lb_missing_count[lb] = _lb_missing_count.get(lb, 0) + len(missing_set)

    # Duplicate resolution: when the same checksum appears in multiple LBs (DUPLICATE):
    # - If all competing LBs are fully complete → promote ALL to MATCHED (keep is_duplicate=True
    #   so the per-LB duplicates column still shows the overlap count).
    # - If some are complete and others are not → promote only the complete ones and clear
    #   is_duplicate so they are treated as the definitive match.
    from collections import defaultdict as _dd
    _dup_by_chk: dict = _dd(list)
    for item in detail:
        if item["status"] == "DUPLICATE":
            _dup_by_chk[item["checksum"]].append(item)
    for _items in _dup_by_chk.values():
        fully_matched = [i for i in _items if not i["missing_from_set"]]
        incomplete = [i for i in _items if i["missing_from_set"]]
        if fully_matched and incomplete:
            # Clear winner — only the complete LB(s) win.
            for item in fully_matched:
                item["status"] = "MATCHED"
                item["is_duplicate"] = False
        elif fully_matched:
            # All competing LBs are equally complete — show all as MATCHED.
            for item in fully_matched:
                item["status"] = "MATCHED"

    # Provenance rescue (TODO-296): a NOT FOUND can mean the user's file is fine and
    # the DB's own reference value is wrong. checksum_disputes records exactly those
    # cases — DB value vs the original uploader's checksum file. Annotate rather than
    # re-status, so the item still counts as unmatched against the DB while the caller
    # can show *why* it didn't match.
    _not_found = [
        d for d in detail
        if d["status"] == "NOT FOUND" and not d.get("ignored")
    ]
    if _not_found:
        from backend import checksum_provenance
        try:
            _disputes = checksum_provenance.lookup_disputed_checksums(
                conn, [d["checksum"] for d in _not_found]
            )
        except sqlite3.Error:
            _disputes = {}
        for item in _not_found:
            dispute = _disputes.get(item["checksum"].lower())
            if dispute:
                item["dispute"] = {
                    "lb_number": dispute["lb_number"],
                    "db_checksum": dispute["reference_checksum"],
                    "source_file": dispute["source_file"],
                    "confidence": dispute["confidence"],
                    "status": dispute["status"],
                    "detail_url": detail_url(dispute["lb_number"]),
                }

    # Build summary per LB
    lb_summary = {}
    unmatched_count = 0
    for item in detail:
        if item.get("ignored"):
            continue
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
                "missing_from_set": _lb_missing_count.get(lb, 0),
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

    # If every matched item for an LB is still a duplicate (none were promoted to MATCHED
    # by the resolution pass), the entry is superseded by a better-matching LB — show it
    # as DUPLICATE (yellow) rather than INCOMPLETE (pink) so the user isn't misled into
    # thinking they have missing files.
    for s in lb_summary.values():
        if s["duplicates"] == s["given"] and s["status"] == "INCOMPLETE":
            s["status"] = "DUPLICATE"

    # xref_groups / matched_xref (FABLE_XREF_INCORPORATION.md D1): expose, per LB,
    # which (lb, xref) fileset group(s) the input touched and which one "won" —
    # this is a re-packaging of _lb_xref_missing / lb_xref_to_matched, already
    # computed above for the reverse-lookup completeness check, not new analysis.
    # No new lookup status is introduced; copy-level xref stays a dimension
    # (matched_xref) orthogonal to MATCHED/INCOMPLETE/DUPLICATE.
    _group_stats: dict = {}
    for item in detail:
        if item.get("ignored"):
            continue
        lb = item["lb_number"]
        if lb is None:
            continue
        key = (lb, item["xref"])
        gstats = _group_stats.setdefault(key, {"given": 0, "matched": 0})
        gstats["given"] += 1
        if item["status"] in ("MATCHED", "MATCHED (INCOMPLETE)"):
            gstats["matched"] += 1

    for s in lb_summary.values():
        lb = s["lb_number"]
        groups = [
            {
                "xref": gxref,
                "given": gstats["given"],
                "matched": gstats["matched"],
                "missing": len(_lb_xref_missing.get((glb, gxref), set())),
            }
            for (glb, gxref), gstats in _group_stats.items()
            if glb == lb
        ]
        groups.sort(key=lambda g: g["xref"])
        s["xref_groups"] = groups
        # Winning group = fewest missing files; ties broken by lowest xref id,
        # so canonical (0) wins ties against any alternate fileset group.
        s["matched_xref"] = (
            min(groups, key=lambda g: (g["missing"], g["xref"]))["xref"] if groups else 0
        )

    summary = {
        "given": len(parsed_entries),
        "matched": sum(1 for d in detail if d["lb_number"] is not None),
        "unmatched": unmatched_count,
        "missing_from_db": unmatched_count,
        "disputed": sum(1 for d in detail if d.get("dispute")),
        "lb_numbers_found": list(lb_summary.keys()),
        "lb_summary": list(lb_summary.values()),
    }

    # Annotate detail items with lb_status from lb_master so callers (e.g.
    # rename tab) can apply NFT suffix logic without a second DB round-trip.
    _matched_lbs = {item["lb_number"] for item in detail if item["lb_number"] is not None}
    if _matched_lbs:
        _lb_status_map = dict(conn.execute(
            "SELECT lb_number, lb_status FROM lb_master WHERE lb_number IN ({})".format(
                ",".join("?" * len(_matched_lbs))
            ),
            list(_matched_lbs),
        ).fetchall())
    else:
        _lb_status_map = {}
    for item in detail:
        item["lb_status"] = _lb_status_map.get(item["lb_number"])
    # Also annotate lb_summary values so the lookup tab can tint rows and filter
    for s in lb_summary.values():
        s["lb_status"] = _lb_status_map.get(s["lb_number"])

    # Annotate with collection ownership and lbdir verification status so the
    # lookup tab can flag recordings the user already owns.
    if _matched_lbs:
        _owned_rows = conn.execute(
            "SELECT lb_number, lbdir_verified_at FROM my_collection WHERE lb_number IN ({})".format(
                ",".join("?" * len(_matched_lbs))
            ),
            list(_matched_lbs),
        ).fetchall()
        _owned_map = {r["lb_number"]: r["lbdir_verified_at"] for r in _owned_rows}
    else:
        _owned_map = {}
    for item in detail:
        lb = item["lb_number"]
        item["owned"] = lb in _owned_map
        item["lbdir_verified"] = bool(_owned_map.get(lb))
    for s in lb_summary.values():
        lb = s["lb_number"]
        s["owned"] = lb in _owned_map
        s["lbdir_verified"] = bool(_owned_map.get(lb))

    # Annotate with lb_category so views can badge by recording type.
    if _matched_lbs:
        _lb_category_map = dict(conn.execute(
            "SELECT lb_number, lb_category FROM entries WHERE lb_number IN ({})".format(
                ",".join("?" * len(_matched_lbs))
            ),
            list(_matched_lbs),
        ).fetchall())
    else:
        _lb_category_map = {}
    for item in detail:
        item["lb_category"] = _lb_category_map.get(item["lb_number"])
    for s in lb_summary.values():
        s["lb_category"] = _lb_category_map.get(s["lb_number"])

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
        _rows = rows_to_insert
        get_write_queue().execute(
            lambda c: c.executemany(
                "INSERT INTO entry_changes(lb_number, field, old_value, new_value) VALUES(?,?,?,?)",
                _rows
            )
        )
    return changed


def insert_missing_entry(lb_number, db_path=None):
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT OR IGNORE INTO entries(lb_number, date_str, location, cdr, rating, timing,
               description, setlist, status)
               VALUES(?, '', '', '', '', '', '', '', 'missing')""",
            (_lb,)
        )
    )


def purge_entry_changes(db_path=None) -> None:
    """Delete all scrape diff changelog rows from entry_changes."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM entry_changes"))


# ── lb_master integrity system ─────────────────────────────────────────────────

def backup_database(reason: str = "manual", db_path=None) -> "Path":
    """Create a consistent snapshot of the DB using VACUUM INTO.

    Output: data/backups/losslessbob_YYYY-MM-DD_HHMMSS_<reason>.db
    Keeps the 10 most recent backups, pruning older ones.
    Returns the Path of the new backup file.
    """
    from datetime import UTC
    from datetime import datetime as _dt

    from backend.paths import DATA_DIR as _DATA

    backup_dir = _DATA / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _dt.now(UTC).strftime("%Y-%m-%d_%H%M%S_%f")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    out_path = backup_dir / f"losslessbob_{ts}_{safe_reason}.db"

    conn = get_connection(db_path)
    conn.execute("VACUUM INTO ?", (str(out_path),))
    logger.info("Database backed up to %s", out_path)

    # Prune: keep newest 10 backups only
    backups = sorted(backup_dir.glob("losslessbob_*.db"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-10]:
        try:
            old.unlink()
        except OSError:
            pass

    return out_path


# ── Master data export / import ───────────────────────────────────────────────

def export_master_db(reason: str = "publish", db_path=None,
                     include_private: bool = False) -> "tuple[Path, dict]":
    """Produce a master-only snapshot of the DB plus a manifest sidecar.

    Pipeline:
      1. ``VACUUM INTO`` a snapshot file → consistent point-in-time copy.
      2. On the snapshot: DROP every table in :data:`USER_TABLES`.
      3. Delete every ``meta`` row whose key is not in :data:`MASTER_META_KEYS`.
      4. Stamp ``master_version`` (UTC timestamp), ``master_published_at`` (now),
         and ``master_schema_version`` (current code constant).
      5. Unless ``include_private``, blank all private-entry metadata
         (TODO-245/253): rows with ``entries.status='private'`` or
         ``metadata_source='private_import'`` keep only the number-level flag
         (``status='private'``, same information as ``lb_master``); every
         metadata field is emptied and the FTS index rebuilt. Checksums are
         deliberately retained — clients derive 'private' status from them
         and they predate the metadata import (see TODO-253).
      6. ``VACUUM`` to reclaim freed space.
      7. **Verify** the snapshot contains no USER_TABLES, no non-master meta,
         and (public channel) no residual private metadata.
      8. Compute SHA256 of the final snapshot file.
      9. Write ``<snapshot>.manifest.json`` sidecar with counts + SHA +
         version + ``channel`` ('public' stripped / 'full' friends-only).

    Args:
        reason: Free-text tag embedded in the filename and manifest.
        db_path: Source database path (default: live DB).
        include_private: True produces a 'full' snapshot for friends-only
            distribution; it must never be uploaded to a public URL.

    Returns:
        (snapshot_path, manifest_dict)

    Raises:
        RuntimeError: If the verification step finds residual user data or
            (public channel) residual private metadata.
    """
    import hashlib
    from datetime import UTC
    from datetime import datetime as _dt

    from backend.paths import DATA_DIR as _DATA

    export_dir = _DATA / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    ts = _dt.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    out_path = export_dir / f"losslessbob_master_{ts}_{safe_reason}.db"
    manifest_path = export_dir.joinpath(out_path.name + ".manifest.json")

    # Step 1: consistent snapshot via VACUUM INTO
    src = get_connection(db_path)
    src.execute("VACUUM INTO ?", (str(out_path),))
    logger.info("Master export snapshot created at %s", out_path)

    # Steps 2-6: clean the snapshot in-place (separate connection on the file)
    snap = sqlite3.connect(str(out_path))
    snap.row_factory = sqlite3.Row
    try:
        snap.execute("PRAGMA foreign_keys = OFF")
        for tbl in USER_TABLES:
            snap.execute(f"DROP TABLE IF EXISTS {tbl}")
        # Filter meta to whitelist
        placeholders = ",".join("?" * len(MASTER_META_KEYS))
        snap.execute(
            f"DELETE FROM meta WHERE key NOT IN ({placeholders})",
            tuple(MASTER_META_KEYS),
        )
        # Stamp version + publish timestamp + schema version
        master_version = ts  # human-readable + sortable
        published_at = _dt.now(UTC).isoformat()
        for k, v in (
            ("master_version", master_version),
            ("master_published_at", published_at),
            ("master_schema_version", str(MASTER_SCHEMA_VERSION)),
        ):
            snap.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )

        # Step 5: strip private-entry metadata for the public channel
        stripped = 0
        if not include_private:
            cur = snap.execute(
                """UPDATE entries SET date_str='', location='', cdr='',
                       rating='', timing='', description='', setlist='',
                       taper_name=NULL, source_chain=NULL, lb_category=NULL,
                       source_type=NULL, metadata_source=NULL
                   WHERE status='private' OR metadata_source='private_import'"""
            )
            stripped = cur.rowcount
            snap.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        snap.commit()
        snap.execute("VACUUM")

        # Step 7: VERIFY
        # 7a. No user tables present
        present = {r[0] for r in snap.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        leaked = present & set(USER_TABLES)
        if leaked:
            raise RuntimeError(
                f"Master export verification failed: user tables present in "
                f"snapshot: {sorted(leaked)}"
            )
        # 7b. No non-master meta keys
        non_master = [r[0] for r in snap.execute(
            f"SELECT key FROM meta WHERE key NOT IN ({placeholders})",
            tuple(MASTER_META_KEYS),
        ).fetchall()]
        if non_master:
            raise RuntimeError(
                f"Master export verification failed: non-master meta keys "
                f"present in snapshot: {sorted(non_master)}"
            )
        # 7c. Public channel: no residual private metadata (field or FTS side)
        if not include_private:
            residual = snap.execute(
                """SELECT COUNT(*) FROM entries
                   WHERE (status='private' OR metadata_source IS NOT NULL)
                     AND (COALESCE(date_str,'')!='' OR COALESCE(location,'')!=''
                          OR COALESCE(cdr,'')!='' OR COALESCE(rating,'')!=''
                          OR COALESCE(timing,'')!='' OR COALESCE(description,'')!=''
                          OR COALESCE(setlist,'')!='' OR taper_name IS NOT NULL
                          OR source_chain IS NOT NULL
                          OR metadata_source IS NOT NULL)"""
            ).fetchone()[0]
            if residual:
                raise RuntimeError(
                    f"Master export verification failed: {residual} private "
                    f"entries rows still carry metadata in a public-channel "
                    f"snapshot"
                )
        # 7d. Sanity: lb_master populated (otherwise this isn't a useful release)
        lb_count = snap.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
        ck_count = snap.execute("SELECT COUNT(*) FROM checksums").fetchone()[0]
        en_count = snap.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        stats_row = snap.execute(
            "SELECT lb_status, COUNT(*) FROM lb_master GROUP BY lb_status"
        ).fetchall()
        status_counts = {r[0]: r[1] for r in stats_row}
        override_count = snap.execute(
            "SELECT COUNT(*) FROM lb_master WHERE manual_override=1"
        ).fetchone()[0]
    finally:
        snap.close()

    # Step 8: SHA256 of the final file
    sha = hashlib.sha256()
    with open(out_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    sha256 = sha.hexdigest()
    size_bytes = out_path.stat().st_size

    # Step 9: manifest sidecar
    manifest = {
        "filename": out_path.name,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "master_version": master_version,
        "master_published_at": published_at,
        "master_schema_version": MASTER_SCHEMA_VERSION,
        "row_counts": {
            "lb_master": lb_count,
            "checksums": ck_count,
            "entries": en_count,
        },
        "lb_status_counts": status_counts,
        "manual_override_count": override_count,
        "reason": reason,
        "channel": "full" if include_private else "public",
        "private_rows_stripped": stripped,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info(
        "Master export verified: %s rows (lb_master), %s bytes, sha256=%s",
        lb_count, size_bytes, sha256[:12],
    )
    return out_path, manifest


def generate_release_notes(since_timestamp: str | None = None, db_path=None) -> str:
    """Build markdown release notes from lb_status_history and manual overrides.

    Args:
        since_timestamp: ISO timestamp; only history rows after this point are
            included. Pass None to include all rows (first-ever release).
        db_path: Optional path to the SQLite database file. Defaults to DB_PATH.

    Returns:
        Markdown string suitable for a GitHub release body.
    """
    conn = get_connection(db_path)

    # Status transitions since the last published snapshot
    if since_timestamp:
        rows = conn.execute(
            "SELECT lb_number, old_status, new_status, changed_at, trigger_event "
            "FROM lb_status_history WHERE changed_at > ? ORDER BY changed_at",
            (since_timestamp,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT lb_number, old_status, new_status, changed_at, trigger_event "
            "FROM lb_status_history ORDER BY changed_at",
        ).fetchall()

    # Manual override rows with notes
    overrides = conn.execute(
        "SELECT lb_number, lb_status, manual_notes, manual_set_at "
        "FROM lb_master WHERE manual_override = 1 ORDER BY lb_number",
    ).fetchall()

    lines: list[str] = []

    if rows:
        groups: dict[tuple[str, str, str], list[str]] = {}
        for r in rows:
            old = r["old_status"] or "—"
            new = r["new_status"]
            trigger = r["trigger_event"] or ""
            ts = (r["changed_at"] or "")[:10]
            groups.setdefault((old, new, trigger), []).append(ts)

        lines.append(f"## Status changes ({len(rows)})\n")
        for (old, new, trigger), dates in groups.items():
            dmin, dmax = min(dates), max(dates)
            date_str = dmin if dmin == dmax else f"{dmin} – {dmax}"
            trig = f" _{trigger}_" if trigger else ""
            lines.append(f"- {old} → {new}: {len(dates)}  _{date_str}_{trig}")
        lines.append("")

    if overrides:
        lines.append(f"## Manual overrides ({len(overrides)})\n")
        for o in overrides:
            note = f" — {o['manual_notes']}" if o["manual_notes"] else ""
            lines.append(f"- LB-{o['lb_number']:05d}: {o['lb_status']}{note}")
        lines.append("")

    if not lines:
        lines = ["_No status changes since last release._"]

    return "\n".join(lines)


def get_map_data(filters: dict, db_path=None) -> dict:
    """Return marker data and unplottable count for the map view.

    Args:
        filters: Dict with optional keys: status (str), owned (bool),
                 year_min (int), year_max (int), q (str).
        db_path: Optional path to the SQLite database file. Defaults to DB_PATH.

    Returns:
        Dict with keys "markers" (list of dicts) and "unplottable_count" (int).
        Each marker dict contains: lb_number, date_str, location, lb_status,
        owned, lat, lon, display_name, city_level (bool — True when the pin
        is only city-precision rather than a resolved venue, TODO-223 bite 3).
    """
    conn = get_connection(db_path)

    clauses: list[str] = []
    params: list = []

    status = filters.get("status")
    if status:
        clauses.append("lm.lb_status = ?")
        params.append(status)

    owned = filters.get("owned")
    if owned is True:
        clauses.append("mc.lb_number IS NOT NULL")
    elif owned is False:
        clauses.append("mc.lb_number IS NULL")

    year_min = filters.get("year_min")
    if year_min is not None:
        clauses.append("CAST(SUBSTR(e.date_str, INSTR(e.date_str, '/') + INSTR(SUBSTR(e.date_str,"
                       " INSTR(e.date_str, '/') + 1), '/') + INSTR(e.date_str, '/'), 10) AS INTEGER)"
                       " >= ?")
        params.append(int(year_min))

    year_max = filters.get("year_max")
    if year_max is not None:
        clauses.append("CAST(SUBSTR(e.date_str, INSTR(e.date_str, '/') + INSTR(SUBSTR(e.date_str,"
                       " INSTR(e.date_str, '/') + 1), '/') + INSTR(e.date_str, '/'), 10) AS INTEGER)"
                       " <= ?")
        params.append(int(year_max))

    q = filters.get("q")
    if q:
        like = f"%{q}%"
        clauses.append("(e.lb_number LIKE ? OR e.location LIKE ?)")
        params.extend([like, like])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
        SELECT e.lb_number, e.date_str, e.location,
               lm.lb_status,
               CASE WHEN mc.lb_number IS NOT NULL THEN 1 ELSE 0 END AS owned,
               geo.lat, geo.lon, geo.display_name, geo.source, geo.confidence
        FROM entries e
        LEFT JOIN location_geocoded geo
               ON e.location = geo.location_text AND geo.confidence != 'low'
        LEFT JOIN lb_master lm ON e.lb_number = lm.lb_number
        LEFT JOIN my_collection mc ON e.lb_number = mc.lb_number
        {where}
        ORDER BY e.lb_number
    """

    rows = conn.execute(sql, params).fetchall()

    markers: list[dict] = []
    unplottable_count = 0

    city_level_sources = {"setlistfm_city", "city_geocode", "gazetteer_city"}
    for row in rows:
        if row["lat"] is not None and row["lon"] is not None:
            source = row["source"] or ""
            markers.append({
                "lb_number": row["lb_number"],
                "date_str": row["date_str"],
                "location": row["location"],
                "lb_status": row["lb_status"],
                "owned": bool(row["owned"]),
                "lat": row["lat"],
                "lon": row["lon"],
                "display_name": row["display_name"],
                "city_level": source in city_level_sources or source.endswith("-city"),
            })
        else:
            unplottable_count += 1

    return {"markers": markers, "unplottable_count": unplottable_count}


def import_master_db(snapshot_path: "Path | str", db_path=None,
                     source: str = "file") -> dict:
    """Import a master snapshot into the local DB, preserving user data.

    Pipeline:
      1. Load + validate the manifest sidecar (SHA256 must match the .db file).
      2. Schema version guard: refuse if incoming version > local
         :data:`MASTER_SCHEMA_VERSION`.
      3. Take an automatic backup (``reason='pre_master_import'``).
      4. ``ATTACH DATABASE`` the incoming snapshot as ``incoming``.
      5. For each table in :data:`MASTER_TABLES`, if present in ``incoming``:
            ``DELETE FROM main.<t>;
             INSERT INTO main.<t> SELECT * FROM incoming.<t>;``
         Tables absent from ``incoming`` (an older snapshot predating a later
         schema addition) are skipped, not treated as an error, and listed in
         the returned ``skipped_tables``.
      6. For meta: replace only the keys in :data:`MASTER_META_KEYS`;
         leave user keys (theme, qbt_*, wtrf_*, is_curator, ...) untouched.
      7. ``INSERT INTO entries_fts(entries_fts) VALUES('rebuild');``
      8. ``DETACH DATABASE incoming``.
      9. Append a ``lb_snapshot_history`` row (TODO-305) so ``/lbdir/sync`` can
         show the per-update diff; a failure there never fails the import.

    Args:
        snapshot_path: Path to the master ``.db`` snapshot (its
            ``.manifest.json`` sidecar must sit alongside it).
        db_path: Target database; defaults to the app DB.
        source: Where the snapshot came from — ``"github"`` for an installed
            release, ``"file"`` for a local/manual import. Recorded in the
            snapshot-history row only.

    Returns:
        Summary dict: ``{master_version, rows_per_table, lb_status_counts,
        backup_path, lb_status_changes, skipped_tables}``.

    Raises:
        FileNotFoundError: snapshot or manifest missing.
        ValueError: SHA256 mismatch.
        RuntimeError: schema version too new for this client.
    """
    import hashlib
    from datetime import UTC
    from datetime import datetime as _dt

    snapshot_path = Path(snapshot_path)
    manifest_path = snapshot_path.with_name(snapshot_path.name + ".manifest.json")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Master snapshot not found: {snapshot_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found alongside snapshot: {manifest_path}"
        )

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Step 1: SHA256 validation
    sha = hashlib.sha256()
    with open(snapshot_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    actual_sha = sha.hexdigest()
    # Validate sha256 field type before comparing (#4)
    expected_sha = manifest.get("sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("Invalid manifest: sha256 missing or wrong format")
    if expected_sha != actual_sha:
        raise ValueError("Master snapshot SHA256 mismatch. Re-download the file.")

    # Step 2: schema version guard with type-check (#4)
    raw_schema = manifest.get("master_schema_version")
    if not isinstance(raw_schema, (int, str)):
        raise ValueError("Invalid manifest: master_schema_version missing or wrong type")
    incoming_schema = int(raw_schema)
    if incoming_schema < 1:
        raise ValueError("Invalid manifest: master_schema_version must be ≥ 1")
    if incoming_schema > MASTER_SCHEMA_VERSION:
        raise RuntimeError(
            f"Master snapshot schema version {incoming_schema} is newer than "
            f"this app supports (v{MASTER_SCHEMA_VERSION}). Upgrade the app first."
        )

    # Step 2b: downgrade guard — refuse if incoming snapshot is older than installed
    incoming_version: str = manifest.get("master_version", "")
    if incoming_version:
        _conn = get_connection(db_path)
        _row = _conn.execute(
            "SELECT value FROM meta WHERE key = 'master_version'"
        ).fetchone()
        current_version: str | None = _row[0] if _row else None
        if current_version and incoming_version < current_version:
            raise ValueError(
                f"Snapshot version '{incoming_version}' is older than the installed "
                f"version '{current_version}'. Install aborted to prevent data loss."
            )

    # Step 3: backup local DB before destructive replace
    backup_path = backup_database(reason="pre_master_import", db_path=db_path)
    logger.info("Pre-import backup written to %s", backup_path)

    # Step 4-7: copy under a transaction
    conn = get_connection(db_path)
    # Snapshot pre-import lb_status distribution so we can report what changed
    pre_status = {r[0]: r[1] for r in conn.execute(
        "SELECT lb_status, COUNT(*) FROM lb_master GROUP BY lb_status"
    ).fetchall()}

    with _write_lock:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("ATTACH DATABASE ? AS incoming", (str(snapshot_path),))
            try:
                row_counts: dict[str, int] = {}
                skipped_tables: list[str] = []
                # Order matters when FKs exist (entries before entry_files etc.),
                # but with foreign_keys OFF for this scope it doesn't.
                for tbl in MASTER_TABLES:
                    exists = conn.execute(
                        "SELECT 1 FROM incoming.sqlite_master "
                        "WHERE type='table' AND name=?",
                        (tbl,),
                    ).fetchone()
                    if not exists:
                        # Older snapshot predates this table — leave local copy
                        # untouched rather than failing the whole import.
                        skipped_tables.append(tbl)
                        continue
                    conn.execute(f"DELETE FROM main.{tbl}")
                    conn.execute(
                        f"INSERT INTO main.{tbl} SELECT * FROM incoming.{tbl}"
                    )
                    row_counts[tbl] = conn.execute(
                        f"SELECT COUNT(*) FROM main.{tbl}"
                    ).fetchone()[0]
                # meta: replace only master keys, preserve user keys
                placeholders = ",".join("?" * len(MASTER_META_KEYS))
                conn.execute(
                    f"DELETE FROM main.meta WHERE key IN ({placeholders})",
                    tuple(MASTER_META_KEYS),
                )
                conn.execute(
                    f"INSERT INTO main.meta(key, value) "
                    f"SELECT key, value FROM incoming.meta WHERE key IN ({placeholders})",
                    tuple(MASTER_META_KEYS),
                )
                # Rebuild FTS from the freshly-replaced entries
                try:
                    conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
                except sqlite3.OperationalError as e:
                    logger.warning("FTS rebuild failed (will rebuild on next FTS access): %s", e)
                conn.commit()
            finally:
                conn.execute("DETACH DATABASE incoming")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    # Reset bloom filter so the next checksum lookup rebuilds it from new data
    global _bloom
    with _bloom_lock:
        _bloom = None

    post_status = {r[0]: r[1] for r in conn.execute(
        "SELECT lb_status, COUNT(*) FROM lb_master GROUP BY lb_status"
    ).fetchall()}

    # Compute the diff: how many LBs changed status
    changed = 0
    all_keys = set(pre_status) | set(post_status)
    for k in all_keys:
        if pre_status.get(k, 0) != post_status.get(k, 0):
            changed = sum(abs(pre_status.get(k, 0) - post_status.get(k, 0))
                          for k in all_keys) // 2
            break

    imported_at = _dt.now(UTC).isoformat()

    # Snapshot history (TODO-305). Best-effort: the import itself has already
    # committed, so a bookkeeping failure must not turn a good import into an
    # error — /lbdir/sync would just be missing one row.
    try:
        _record_snapshot_history(
            conn,
            master_version=manifest.get("master_version"),
            master_published_at=manifest.get("master_published_at"),
            imported_at=imported_at,
            source=source,
            status_counts=post_status,
            lb_status_changes=changed,
            row_counts=row_counts,
            backup_path=str(backup_path),
        )
    except sqlite3.Error:
        logger.exception("import_master_db: failed recording lb_snapshot_history")

    return {
        "master_version": manifest.get("master_version"),
        "master_published_at": manifest.get("master_published_at"),
        "row_counts": row_counts,
        "pre_status_counts": pre_status,
        "post_status_counts": post_status,
        "lb_status_changes": changed,
        "backup_path": str(backup_path),
        "imported_at": imported_at,
        "skipped_tables": skipped_tables,
    }


def _record_snapshot_history(conn: sqlite3.Connection, *, master_version: str | None,
                             master_published_at: str | None, imported_at: str,
                             source: str, status_counts: dict[str, int],
                             lb_status_changes: int, row_counts: dict,
                             backup_path: str | None) -> None:
    """Append one row to ``lb_snapshot_history`` describing a master import.

    ``entries_added`` is the ``lb_master`` row-count delta against the newest
    existing history row, so the first-ever import reports its full size rather
    than a meaningless zero.

    Args:
        conn: Open connection to the target database (already committed).
        master_version: ``master_version`` from the incoming manifest.
        master_published_at: ``master_published_at`` from the incoming manifest.
        imported_at: ISO-8601 UTC stamp for this import.
        source: ``"github"`` or ``"file"``.
        status_counts: Post-import ``lb_status`` histogram.
        lb_status_changes: Number of LBs whose status moved in this import.
        row_counts: Rows written per master table.
        backup_path: Path of the pre-import backup, if one was taken.
    """
    import json as _json

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lb_snapshot_history (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            master_version      TEXT,
            master_published_at TEXT,
            imported_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source              TEXT,
            entries_total       INTEGER,
            entries_held        INTEGER,
            entries_added       INTEGER,
            lb_status_changes   INTEGER,
            status_counts_json  TEXT,
            row_counts_json     TEXT,
            backup_path         TEXT
        );
    """)

    entries_total = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
    entries_held = conn.execute("""
        SELECT COUNT(*) FROM lb_master lm
        WHERE lm.lb_status != 'nonexistent'
          AND EXISTS (SELECT 1 FROM my_collection mc WHERE mc.lb_number = lm.lb_number)
    """).fetchone()[0]

    prev = conn.execute(
        "SELECT entries_total FROM lb_snapshot_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_total = prev[0] if prev and prev[0] is not None else 0

    conn.execute("""
        INSERT INTO lb_snapshot_history
            (master_version, master_published_at, imported_at, source,
             entries_total, entries_held, entries_added, lb_status_changes,
             status_counts_json, row_counts_json, backup_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (master_version, master_published_at, imported_at, source,
          entries_total, entries_held, entries_total - prev_total, lb_status_changes,
          _json.dumps(status_counts), _json.dumps(row_counts), backup_path))
    conn.commit()


from backend.db.aliases import (  # re-export (TODO-369 S2)
    add_lb_alias,
    delete_folder_link,
    delete_lb_alias,
    get_folder_link,
    get_folder_links,
    get_lb_aliases,
    rekey_folder_link,
    replace_folder_link,
    resolve_aliases,
    set_folder_link,
)
from backend.db.archive_uploads import (  # re-export (TODO-369 S2)
    create_archive_upload,
    finish_archive_upload,
    get_archive_uploads,
)
from backend.db.bootlegs import (  # re-export (TODO-369 S2)
    _BOOTLEG_SOURCE_URL,
    get_bootleg_scrape_history,
    get_bootleg_stats,
    get_bootlegs,
    get_bootlegs_for_lb,
)
from backend.db.collection import (  # re-export (TODO-369 S2)
    _mount_label_for_path,
    _route_status,
    ack_integrity_events,
    add_to_collection,
    add_to_wishlist,
    audit_collection_checksums,
    delete_from_collection,
    get_collection,
    get_collection_duplicates,
    get_collection_meta,
    get_integrity_events,
    get_missing_from_collection,
    get_owned_lb_numbers,
    get_wishlist,
    get_xref_lb_numbers,
    get_xref_map,
    increment_listen_count,
    log_integrity_event,
    purge_collection,
    purge_collection_meta,
    purge_integrity_events,
    purge_wishlist,
    reassign_collection,
    remove_from_wishlist,
    set_collection_meta,
    set_lbdir_verified,
    update_collection,
    update_wishlist,
)
from backend.db.curated import (  # re-export (TODO-369 S2)
    add_curated_list_entries,
    delete_curated_list,
    get_curated_lists,
    get_or_create_curated_list,
    get_picks_for_date,
    get_show_pick_for_lb,
    get_tonight_picks,
)
from backend.db.integrity import (  # re-export (TODO-369 S2)
    _FILE_SCAN_COUNTS,
    delete_file_inventory_rows,
    find_ok_inventory_by_xxh3,
    finish_file_scan,
    finish_integrity_scan,
    get_collection_integrity_status,
    get_file_integrity_problems,
    get_file_integrity_summary,
    get_file_inventory_rows,
    get_file_scan_history,
    get_integrity_scan_history,
    get_mount_integrity_summary,
    get_rolling_verify_batch,
    mark_file_inventory_status,
    record_file_scan_start,
    record_integrity_scan_start,
    touch_file_inventory_verified,
    upsert_collection_integrity_status,
    upsert_file_inventory,
)
from backend.db.lb_master import (  # re-export (TODO-369 S2)
    _compute_lb_status,
    _keep_unscraped_public,
    add_lb_missing,
    batch_reconcile_lb_status,
    clear_lb_manual_override,
    export_overrides,
    get_lb_master_list,
    get_lb_master_row,
    get_lb_master_stats,
    get_lb_missing_list,
    get_lb_status,
    get_lb_status_history,
    import_overrides,
    is_curator,
    is_lb_missing,
    is_postable_to_forum,
    is_seedable_to_tracker,
    migrate_lb_master,
    reconcile_all_lb_master,
    reconcile_lb_status,
    remove_lb_missing,
    set_curator,
    set_lb_manual_override,
)
from backend.db.lb_problems import (  # re-export (TODO-369 S2)
    add_lb_problem,
    delete_lb_problem,
    get_lb_problems,
    update_lb_problem,
)
from backend.db.library import (  # re-export (TODO-369 S2)
    _KEYWORD_RULES,
    _PERF_CATEGORY_MAP,
    _STATUS_LABEL,
    _STATUS_RANK,
    _entry_date_to_iso_local,
    _load_curated_by_lb,
    _load_latest_abs_grades,
    _load_pick_ranks,
    _load_taper_attributions,
    _load_tuit_circulating,
    _year_from_date_str,
    classify_entry_categories,
    classify_one_entry,
    get_distinct_years,
    get_entry,
    get_performances,
    get_pick_badges,
    lookup_checksum_owners,
    search_entries,
)
from backend.db.mounts import (  # re-export (TODO-369 S2)
    add_collection_mount,
    delete_collection_mount,
    delete_collection_route,
    get_collection_mounts,
    get_collection_routes,
    update_collection_mount,
    upsert_collection_routes,
)
from backend.db.olof import (  # re-export (TODO-369 S2)
    _ENTRY_TRACK_MARKER_RE,
    _OLOF_EVENT_COLUMNS,
    _OLOF_LIKE_ESCAPE,
    _TITLE_CONTAINMENT_RATIO,
    _TITLE_LEADING_THE_RE,
    _TITLE_MIN_CONTAINMENT_LEN,
    _TITLE_NONWORD_RE,
    _TITLE_WS_RE,
    _olof_like_pattern,
    _olof_snippet,
    _olof_songs_for_events,
    compare_olof_setlist,
    get_olof_bobtalk_search,
    get_olof_chronicle_year,
    get_olof_date,
    get_olof_event,
    get_olof_status,
    normalize_title_for_match,
    parse_entry_setlist_titles,
    resolve_lb_number_titles,
    titles_match,
)
from backend.db.pipeline_cache import (  # re-export (TODO-369 S2)
    _PIPELINE_STEPS,
    _cacheable,
    _norm_folder,
    derive_tree_digest,
    folder_fingerprint,
    get_file_hash,
    get_folder_hashes,
    get_folder_state,
    prune_pipeline_cache,
    put_folder_state,
    upsert_file_hash,
)
from backend.db.posting import (  # re-export (TODO-369 S2)
    add_forum_post,
    add_rename_history,
    add_torrent_record,
    add_wtrf_download,
    clear_superseded_torrent_paths,
    delete_forum_post,
    delete_torrent_record,
    get_all_forum_posts,
    get_all_torrents,
    get_folders_for_lb,
    get_folders_for_same_date,
    get_forum_posts_for_lb,
    get_site_file_urls,
    get_torrents_for_lb,
    get_wtrf_attempted_topics,
    get_wtrf_downloads,
    get_wtrf_pending_lb_numbers,
    get_wtrf_rejected_topics,
    update_forum_post_subject,
    update_torrent_record,
    update_wtrf_download,
)
from backend.db.site_inventory import (  # re-export (TODO-369 S2)
    create_scrape_session,
    finish_scrape_session,
    get_downloaded_urls,
    get_inventory_last_modified,
    get_inventory_page,
    get_inventory_stats,
    get_missing_attachment_urls,
    get_pending_urls,
    get_scrape_sessions,
    upsert_inventory,
)
from backend.db.taper import (  # re-export (TODO-369 S2)
    _BETTER_RE,
    _BUILTIN_TAPER_ALIASES,
    _CHAIN_TOKEN,
    _DERIVED_RE,
    _DIFF_RE,
    _EXPLICIT_TAPER_LABEL_RE,
    _KNOWN_TAPER_ALIASES,
    _LB_REF_RE,
    _LT_TAPER_RE,
    _NET_TAPER_LABEL_RE,
    _NOT_TAPER,
    _REF_SENTENCE_SPLIT_RE,
    _SAME_RE,
    _SAME_REF_LEAD_RE,
    _SEMI_EXPLICIT_TAPER_RE,
    _SERIES_BINDING_PREFIX_RE,
    _SERIES_CANONICAL_RE,
    _SERIES_LEAD_RE,
    _SL_DOT,
    _SL_NUM,
    _SRC_ALD_RE,
    _SRC_AUD_RE,
    _SRC_FM_RE,
    _SRC_MIXED_RE,
    _SRC_SBD_RE,
    _classify_source_text,
    _compute_parse_confidence,
    _looks_like_chain,
    _normalise_alias_key,
    _normalise_taper,
    _run_alias_write,
    _run_queued_write,
    _series_code_bound,
    _strip_bt_parens,
    add_taper_alias,
    classify_source_type,
    clear_taper_flag,
    extract_lb_references,
    extract_setlist_from_description,
    extract_taper_and_source,
    get_lineage,
    is_known_taper,
    list_taper_aliases,
    list_taper_vocabulary,
    merge_tapers,
    record_chain_run,
    record_step_run,
    reload_taper_aliases,
    remove_taper_alias,
    set_taper_flag,
    upsert_entry_lineage,
)
from backend.db.tuit import (  # re-export (TODO-369 S2)
    TUIT_RECORDING_COLUMNS,
    TUIT_RETRY_STATUSES,
    TUIT_SHOW_COLUMNS,
    TUIT_SONG_COLUMNS,
    TUIT_SONG_PERF_COLUMNS,
    TUIT_VENUE_COLUMNS,
    _int_or_none_str,
    _normalise_venue_key,
    _upsert_tuit_row,
    add_tuit_download,
    add_tuit_upload,
    backfill_tuit_venues_from_shows,
    get_tuit_download_rec_ids,
    get_tuit_downloads,
    get_tuit_recording,
    get_tuit_retry_rec_ids,
    get_tuit_scraped_songs,
    get_tuit_shows,
    get_tuit_song_performances,
    get_tuit_songs,
    get_tuit_uploads,
    get_tuit_venues,
    tuit_has_recording,
    update_tuit_download,
    update_tuit_upload,
    upsert_tuit_recording,
    upsert_tuit_shows,
    upsert_tuit_song_performances,
    upsert_tuit_songs,
    upsert_tuit_venues,
)

# backend.db.taper rebinds these in reload_taper_aliases(); a re-export would go
# stale, so ``db._TAPER_UNIVERSE`` etc. read the live submodule value (PEP 562).
_TAPER_REBOUND = frozenset({"_KNOWN_TAPER_KEYS_SORTED", "_KNOWN_TAPER_RE", "_TAPER_UNIVERSE"})


def __getattr__(name: str):
    """Forward the taper globals rebound by reload_taper_aliases() to backend.db.taper.

    Args:
        name: Attribute looked up on the package and not found in its namespace.

    Returns:
        The current value from backend.db.taper.

    Raises:
        AttributeError: For any other missing name.
    """
    if name in _TAPER_REBOUND:
        from backend.db import taper
        return getattr(taper, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from backend.db.schema import (  # re-export (TODO-369 S2)
    _DEGENERATE_CHECKSUMS,
    _SAFE_IDENT,
    MASTER_META_KEYS,
    MASTER_SCHEMA_VERSION,
    MASTER_TABLES,
    SCHEMA_SQL,
    USER_META_KEYS,
    USER_TABLES,
    _is_degenerate_checksum,
)
