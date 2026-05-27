import logging
import re
import sqlite3
import threading
from pathlib import Path

from pybloom_live import ScalableBloomFilter as _SBF

from backend.paths import DB_PATH  # noqa: F401  — re-exported for callers
from backend.paths import to_long_path
from backend.db_queue import init_write_queue, get_write_queue  # DB-09

# --- Thread-local persistent connection pool (DB-02) ---
_local = threading.local()

# _write_lock retained for the import_master_db() ATTACH/DETACH workflow which
# needs to hold a broader lock across multiple statements that cannot be split
# into a single queue callable (ATTACH/DETACH are connection-level, not
# transaction-level, and must run on the same connection as the DML).
_write_lock = threading.RLock()

# --- Bloom filter for fast NOT-FOUND short-circuit (DB-07) ---
_bloom: _SBF | None = None
_bloom_lock = threading.Lock()


# --- Master vs. user data ownership model -------------------------------------
# MASTER tables ship in a master-data export and are overwritten on import.
# USER tables stay local to each install and never appear in an export.
# See instructions/CC_LB_INTEGRITY.md §Data Ownership Model.

MASTER_SCHEMA_VERSION = 3  # bumped: dylan_performances promoted to master; lb_problems added

MASTER_TABLES = (
    "lb_missing",
    "checksums",
    "entries",
    "entry_files",
    "entry_changes",
    "lb_master",
    "lb_status_history",
    "flat_file_releases",
    "flat_file_changelog",
    "lb_alias",
    "bootleg_titles",
    "bootleg_scrapes",
    "location_geocoded",
    "dylan_performances",
    "lb_problems",
)
# Note: `entries_fts` is a virtual FTS5 table whose content is mirrored from
# `entries` via triggers. It is NOT copied directly during export/import; the
# triggers (or a one-shot rebuild) keep it in sync once `entries` is replaced.

USER_TABLES = (
    "my_collection",
    "collection_meta",
    "my_wishlist",
    "integrity_events",
    "torrents",
    "rename_history",
    "forum_posts",
    "folder_lb_link",
    "scrape_sessions",
    "site_inventory",
)

# Guard against f-string injection if a table name is ever mis-typed (#10)
_SAFE_IDENT = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
assert all(_SAFE_IDENT.match(t) for t in (*MASTER_TABLES, *USER_TABLES)), \
    "Table name constant contains unsafe identifier"

# meta is mixed: master keys ship, user keys stay local.
MASTER_META_KEYS = frozenset({
    "import_hash",
    "last_import_date",
    "last_lb_number",
    "master_version",
    "master_published_at",
    "master_schema_version",
})

# Sentinel set so callers (and the export verifier) know which keys are
# explicitly user-local and must never be exported. Used for documentation;
# the actual export uses the MASTER_META_KEYS whitelist as the source of truth.
USER_META_KEYS = frozenset({
    "auto_scrape", "scrape_delay_ms", "scrape_attachments", "force_scrape",
    "download_files", "use_local_pages", "search_page_size",
    "qbt_host", "qbt_port", "qbt_category", "qbt_tags",
    "tracker_list",
    "wtrf_board_id", "wtrf_username", "wtrf_password",
    "is_curator",
})

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
CREATE INDEX IF NOT EXISTS idx_chk_covering
    ON checksums(checksum, lb_number, chk_type, filename, xref);
CREATE INDEX IF NOT EXISTS idx_lb_xref0
    ON checksums(lb_number, checksum) WHERE xref=0;
CREATE INDEX IF NOT EXISTS idx_chk_xref_pos
    ON checksums(lb_number, xref) WHERE xref>0;

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

CREATE TABLE IF NOT EXISTS entry_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL,
    field      TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_changes_lb ON entry_changes(lb_number, changed_at DESC);

CREATE TABLE IF NOT EXISTS collection_meta (
    lb_number      INTEGER PRIMARY KEY,
    personal_rating INTEGER CHECK(personal_rating BETWEEN 1 AND 5),
    listen_count   INTEGER DEFAULT 0,
    last_listened  TIMESTAMP,
    tags           TEXT,
    FOREIGN KEY (lb_number) REFERENCES my_collection(lb_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS my_wishlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL UNIQUE,
    added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    priority   INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    notes      TEXT,
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE INDEX IF NOT EXISTS idx_wishlist_lb ON my_wishlist(lb_number);

CREATE TABLE IF NOT EXISTS integrity_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number   INTEGER,
    disk_path   TEXT,
    event_type  TEXT,
    detail      TEXT,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS torrents (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number               INTEGER,
    torrent_path            TEXT,
    source_folder           TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    infohash                TEXT,
    added_to_qbt            INTEGER DEFAULT 0,
    added_to_qbt_at         TIMESTAMP,
    qbt_infohash_confirmed  INTEGER DEFAULT 0,
    last_seen_at            TIMESTAMP,
    excluded_files          TEXT
);
CREATE INDEX IF NOT EXISTS idx_torrents_lb ON torrents(lb_number);

CREATE TABLE IF NOT EXISTS rename_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number   INTEGER,
    old_path    TEXT,
    new_path    TEXT,
    renamed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source      TEXT,
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_rename_history_lb ON rename_history(lb_number);

CREATE TABLE IF NOT EXISTS forum_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number   INTEGER NOT NULL,
    subject     TEXT,
    topic_url   TEXT,
    board_id    INTEGER,
    posted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE INDEX IF NOT EXISTS idx_forum_posts_lb ON forum_posts(lb_number, posted_at DESC);

CREATE TABLE IF NOT EXISTS lb_master (
    lb_number            INTEGER PRIMARY KEY,
    lb_status            TEXT NOT NULL CHECK (lb_status IN ('public','private','missing','nonexistent')),
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
CREATE INDEX IF NOT EXISTS idx_lb_master_status   ON lb_master(lb_status);
CREATE INDEX IF NOT EXISTS idx_lb_master_override ON lb_master(manual_override) WHERE manual_override = 1;
CREATE INDEX IF NOT EXISTS idx_lb_master_review   ON lb_master(needs_review)   WHERE needs_review = 1;

CREATE TABLE IF NOT EXISTS lb_status_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number     INTEGER NOT NULL,
    old_status    TEXT,
    new_status    TEXT NOT NULL,
    changed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trigger_event TEXT
);
CREATE INDEX IF NOT EXISTS idx_lb_history_lb ON lb_status_history(lb_number, changed_at DESC);

CREATE TABLE IF NOT EXISTS location_geocoded (
    location_text   TEXT PRIMARY KEY,
    lat             REAL,
    lon             REAL,
    source          TEXT NOT NULL,
    confidence      TEXT,
    display_name    TEXT,
    manual_override INTEGER NOT NULL DEFAULT 0,
    note            TEXT,
    lb_number       TEXT,
    geocoded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_geo_source ON location_geocoded(source);

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

CREATE TABLE IF NOT EXISTS flat_file_releases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    downloaded_at       TIMESTAMP,
    applied_at          TIMESTAMP,
    deferred_until      TIMESTAMP,
    source_page_url     TEXT NOT NULL,
    zip_url             TEXT NOT NULL,
    zip_filename        TEXT NOT NULL,
    last_lb_in_name     INTEGER,
    page_timestamp      TEXT,
    http_last_modified  TEXT,
    zip_size_bytes      INTEGER,
    zip_sha256          TEXT,
    rows_added          INTEGER,
    rows_changed        INTEGER,
    rows_removed        INTEGER,
    new_lb_min          INTEGER,
    new_lb_max          INTEGER,
    status              TEXT NOT NULL,
    failure_reason      TEXT
);
CREATE INDEX IF NOT EXISTS idx_flat_releases_status
    ON flat_file_releases(status, detected_at DESC);

CREATE TABLE IF NOT EXISTS flat_file_changelog (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id    INTEGER NOT NULL REFERENCES flat_file_releases(id),
    lb_number     INTEGER NOT NULL,
    op            TEXT NOT NULL,
    checksum      TEXT NOT NULL,
    filename      TEXT NOT NULL,
    chk_type      TEXT NOT NULL,
    xref          INTEGER NOT NULL DEFAULT 0,
    old_filename  TEXT,
    old_xref      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_flat_changelog_release ON flat_file_changelog(release_id);
CREATE INDEX IF NOT EXISTS idx_flat_changelog_lb      ON flat_file_changelog(lb_number);

CREATE TABLE IF NOT EXISTS lb_alias (
    alias_lb       INTEGER PRIMARY KEY,
    canonical_lb   INTEGER NOT NULL,
    relationship   TEXT NOT NULL DEFAULT 'duplicate',
    note           TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (alias_lb != canonical_lb)
);
CREATE INDEX IF NOT EXISTS idx_lb_alias_canonical ON lb_alias(canonical_lb);

CREATE TABLE IF NOT EXISTS folder_lb_link (
    folder_path    TEXT PRIMARY KEY,
    lb_number      INTEGER NOT NULL,
    linked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_folder_link_lb ON folder_lb_link(lb_number);

CREATE TABLE IF NOT EXISTS scrape_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    scope       TEXT NOT NULL,      -- 'full' | 'incremental' | 'range' | 'entry_pages' | 'attachments'
    start_url   TEXT,
    pages_fetched  INTEGER DEFAULT 0,
    pages_304      INTEGER DEFAULT 0,   -- unchanged (If-Modified-Since honoured)
    pages_skipped  INTEGER DEFAULT 0,
    pages_failed   INTEGER DEFAULT 0,
    files_fetched  INTEGER DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'running',   -- running | done | stopped | failed
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS site_inventory (
    url             TEXT PRIMARY KEY,
    relative_path   TEXT,       -- path under data/site/, e.g. detail/LB-00001.html
    content_type    TEXT,
    discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discovered_by   TEXT,       -- URL of the page where this link was found
    status          TEXT NOT NULL DEFAULT 'pending',
                                -- pending | downloaded | not_found | failed | skipped
    last_fetched_at TIMESTAMP,
    last_checked_at TIMESTAMP,  -- last If-Modified-Since check (may be 304)
    last_modified   TEXT,       -- HTTP Last-Modified stored for next check
    body_sha256     TEXT,
    size_bytes      INTEGER,
    http_status     INTEGER,
    session_id      INTEGER REFERENCES scrape_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_status  ON site_inventory(status);
CREATE INDEX IF NOT EXISTS idx_inventory_session ON site_inventory(session_id);

CREATE TABLE IF NOT EXISTS bootleg_titles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    date_str     TEXT NOT NULL DEFAULT '',
    date_iso     TEXT,
    year         INTEGER,
    location     TEXT NOT NULL DEFAULT '',
    cd_count     INTEGER NOT NULL DEFAULT 0,
    lbbcd_id     INTEGER,
    lbbcd_url    TEXT,
    scraped_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bootleg_lb
    ON bootleg_titles(lb_number);
CREATE INDEX IF NOT EXISTS idx_bootleg_lbbcd
    ON bootleg_titles(lbbcd_id) WHERE lbbcd_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bootleg_year
    ON bootleg_titles(year);
CREATE INDEX IF NOT EXISTS idx_bootleg_title
    ON bootleg_titles(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS bootleg_scrapes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url          TEXT NOT NULL,
    scraped_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    http_etag           TEXT,
    http_last_modified  TEXT,
    body_sha256         TEXT,
    rows_total          INTEGER,
    rows_added          INTEGER,
    rows_changed        INTEGER,
    rows_removed        INTEGER,
    status              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dylan_performances (
    event_id    TEXT PRIMARY KEY,
    date_str    TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    city        TEXT NOT NULL DEFAULT '',
    state       TEXT NOT NULL DEFAULT '',
    country     TEXT NOT NULL DEFAULT '',
    venue       TEXT NOT NULL DEFAULT '',
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_perf_date     ON dylan_performances(date_str);
CREATE INDEX IF NOT EXISTS idx_perf_category ON dylan_performances(category);
CREATE INDEX IF NOT EXISTS idx_perf_country  ON dylan_performances(country);

CREATE TABLE IF NOT EXISTS lb_missing (
    lb_number      INTEGER PRIMARY KEY,
    confirmed_date TEXT,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS lb_problems (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number  INTEGER NOT NULL REFERENCES lb_master(lb_number),
    notes      TEXT NOT NULL DEFAULT '',
    added      TEXT NOT NULL DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_lb_problems_lb ON lb_problems(lb_number);
"""

_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_SHA1_RE = re.compile(r'^([0-9a-fA-F]{40})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)

TRACKED_ENTRY_FIELDS = ("date_str", "location", "cdr", "rating", "timing",
                        "description", "setlist", "status")

# LB numbers confirmed to not exist on the LosslessBob site.  These are seeded
# into lb_missing on first run and are never scraped or retried.
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
    """
    path = str(to_long_path(Path(db_path)))
    cache = getattr(_local, "connections", None)
    if cache and path in cache:
        try:
            cache[path].close()
        except Exception:
            pass
        del cache[path]


def rebuild_bloom(db_path=None):
    """Load all checksums into an in-process bloom filter. Call after import/init."""
    global _bloom
    bf = _SBF(mode=_SBF.LARGE_SET_GROWTH, error_rate=0.01)
    conn = get_connection(db_path)
    for row in conn.execute("SELECT checksum FROM checksums"):
        bf.add(row[0])
    with _bloom_lock:
        _bloom = bf


def _rebuild_bloom_bg(db_path=None) -> None:
    try:
        rebuild_bloom(db_path)
    except Exception:
        pass  # Non-fatal; lookups fall through to SQLite until filter is ready


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
        cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
        if "status" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN status TEXT DEFAULT 'ok'")
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

        # Always commit: UPDATE above opens a Python implicit transaction regardless
        # of rowcount.  Without this, a zero-row UPDATE leaves the read connection
        # holding a RESERVED lock that blocks the write queue's first transaction.
        conn.commit()

    # Build bloom filter in background so startup is not blocked.
    # checksum_in_bloom() returns True while _bloom is None, so all lookups
    # fall through to SQLite until the filter is ready.
    threading.Thread(target=_rebuild_bloom_bg, args=(db_path,), daemon=True).start()

    # One-time backfill: populate lb_master if table is empty and checksums exist.
    threading.Thread(
        target=lambda: migrate_lb_master(db_path), daemon=True
    ).start()

    # One-time backfill: create a synthetic applied_legacy row for pre-feature imports.
    threading.Thread(
        target=lambda: _bootstrap_flat_file_legacy(db_path), daemon=True
    ).start()

    # One-time import: load Dylan performance data from ODS if not yet imported.
    threading.Thread(
        target=lambda: import_dylan_performances(db_path), daemon=True
    ).start()


def _bootstrap_flat_file_legacy(db_path=None) -> None:
    """On first run after feature install: create a synthetic applied_legacy row from existing meta.

    If flat_file_releases is empty but a previous import_hash exists in meta,
    insert a placeholder row so the history panel is not completely empty and
    the discovery logic has a baseline to compare against.
    """
    import logging as _log_mod
    _log = _log_mod.getLogger(__name__)
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
        _log.info("flat_file: bootstrapped legacy applied row (LastLB=%d)", last_lb)
    except Exception as exc:
        _log.warning("flat_file bootstrap failed: %s", exc)


def import_dylan_performances(db_path=None) -> int:
    """One-time import of the Dylan performance ODS into dylan_performances.

    Skips silently if the table already has rows. Searches DATA_DIR for a file
    matching ``*Dylan_Performance_fixed.ods`` and parses it using stdlib only
    (zipfile + xml.etree.ElementTree). Returns the number of rows inserted.
    """
    import xml.etree.ElementTree as ET
    import zipfile as _zf
    from backend.paths import DATA_DIR as _DATA

    _log = logging.getLogger(__name__)

    conn = get_connection(db_path)
    if conn.execute("SELECT COUNT(*) FROM dylan_performances").fetchone()[0] > 0:
        return 0  # already imported

    candidates = sorted(_DATA.glob("*Dylan_Performance_fixed.ods"))
    if not candidates:
        _log.warning("dylan_performances: ODS file not found in %s", _DATA)
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
        _log.error("dylan_performances: failed to read ODS: %s", exc)
        return 0

    sheet = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table")
    if sheet is None:
        _log.error("dylan_performances: no table element found in ODS")
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
    _log.info("dylan_performances: imported %d rows from %s", len(records), ods_path.name)
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
        logging.getLogger(__name__).warning(
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
    return {
        "total_checksums": total_checksums,
        "total_lb_numbers": total_lb,
        "latest_lb": latest_lb,
        "last_import": last_import,
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

    # Bloom pre-filter: separate definite misses from candidates (DB-07)
    candidates = [e for e in parsed_entries if checksum_in_bloom(e[0])]
    definite_misses = [e for e in parsed_entries if not checksum_in_bloom(e[0])]
    checksums = [e[0] for e in candidates]

    # Temp-table bulk lookup — avoids dynamic IN clause and the 999-param limit (DB-04)
    conn = get_connection(db_path)
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
                    "detail_url": f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb}.html",
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

    # Reverse lookup: check completeness per (lb_number, xref_value) group.
    # Evaluating per xref group means a recording that fully matches an xref variant
    # is shown as MATCHED (green) rather than INCOMPLETE — because it IS complete for
    # that xref; the primary LB set simply isn't what the user has.
    _lb_xref_missing: dict = {}
    for (lb, xref_val), matched_set in lb_xref_to_matched.items():
        all_chks = conn.execute(
            "SELECT checksum FROM checksums WHERE lb_number=? AND xref=?",
            (lb, xref_val)
        ).fetchall()
        all_chks_set = {r["checksum"] for r in all_chks}
        _lb_xref_missing[(lb, xref_val)] = all_chks_set - matched_set

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

    # Duplicate resolution: when the same checksum appears in multiple LBs (DUPLICATE),
    # and one of those LBs is fully matched (no missing files) while others are not,
    # prefer the fully-matched LB — reclassify its items as MATCHED so it is the primary result.
    from collections import defaultdict as _dd
    _dup_by_chk: dict = _dd(list)
    for item in detail:
        if item["status"] == "DUPLICATE":
            _dup_by_chk[item["checksum"]].append(item)
    for _items in _dup_by_chk.values():
        fully_matched = [i for i in _items if not i["missing_from_set"]]
        incomplete = [i for i in _items if i["missing_from_set"]]
        if fully_matched and incomplete:
            for item in fully_matched:
                item["status"] = "MATCHED"
                item["is_duplicate"] = False

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

    summary = {
        "given": len(parsed_entries),
        "matched": sum(1 for d in detail if d["lb_number"] is not None),
        "unmatched": unmatched_count,
        "missing_from_db": unmatched_count,
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


def search_entries(query, field="all", year=None, limit=None, db_path=None):
    """Search entries using FTS5 when a query is present, falling back to LIKE on FTS syntax errors."""
    conn = get_connection(db_path)

    year_clause = ""
    year_params: list = []
    if year is not None:
        short = str(year)[-2:]
        long_ = str(year)
        year_clause = "AND (e.date_str LIKE ? OR e.date_str LIKE ?)"
        year_params = [f"%/{short}", f"%/{long_}"]

    if query:
        if field == "location":
            fts_query = f"location:{query}"
        elif field == "date":
            fts_query = f"date_str:{query}"
        else:
            fts_query = query

        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status, lm.lb_status, lm.public_no_checksums
            FROM entries_fts
            JOIN entries e ON e.lb_number = entries_fts.rowid
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE entries_fts MATCH ?
            {year_clause}
            ORDER BY rank
            {limit_clause}
        """
        params: list = [fts_query] + year_params
    else:
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status, lm.lb_status, lm.public_no_checksums
            FROM entries e
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE 1=1 {year_clause}
            ORDER BY e.lb_number
            {limit_clause}
        """
        params = year_params

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # FTS5 syntax error fallback — revert to LIKE
        like = f"%{query}%"
        fallback_sql = (
            "SELECT e.lb_number, e.date_str, e.location, e.rating,"
            " e.description, e.status, lm.lb_status, lm.public_no_checksums"
            " FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
            " WHERE e.description LIKE ? OR e.location LIKE ? OR e.date_str LIKE ?"
            " ORDER BY e.lb_number"
        )
        fallback_params = [like, like, like]
        if limit is not None:
            fallback_sql += " LIMIT ?"
            fallback_params.append(int(limit))
        rows = conn.execute(fallback_sql, fallback_params).fetchall()

    results = [dict(r) for r in rows]

    # When the query is a bare integer, ensure the entry with that lb_number is
    # included even when none of its text fields contain the number (e.g. searching
    # "1797" for LB-01797 whose date/location fields don't contain that token).
    if query:
        try:
            lb_id = int(query)
            if not any(r["lb_number"] == lb_id for r in results):
                direct = conn.execute(
                    "SELECT e.lb_number, e.date_str, e.location, e.rating,"
                    " e.description, e.status, lm.lb_status, lm.public_no_checksums"
                    " FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
                    " WHERE e.lb_number = ?",
                    (lb_id,),
                ).fetchone()
                if direct:
                    results.insert(0, dict(direct))
        except ValueError:
            pass

    return results


def get_entries_by_lb_list(lb_numbers: list[int], db_path=None) -> list[dict]:
    """Return search-compatible entry dicts for a specific list of LB numbers.

    Args:
        lb_numbers: List of integer LB numbers to fetch.
        db_path: Optional path to the database file.

    Returns:
        List of entry dicts with the same keys as :func:`search_entries`.
    """
    if not lb_numbers:
        return []
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT e.lb_number, e.date_str, e.location, e.rating,"
        f" e.description, e.status, lm.lb_status, lm.public_no_checksums"
        f" FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
        f" WHERE e.lb_number IN ({placeholders})"
        f" ORDER BY e.lb_number",
        [int(n) for n in lb_numbers],
    ).fetchall()
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
                   e.date_str, e.location, e.description, e.rating, e.cdr, lm.lb_status
            FROM my_collection c
            LEFT JOIN entries e ON c.lb_number = e.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = c.lb_number
            ORDER BY c.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def add_to_collection(lb_number, folder_name, disk_path, notes=None, db_path=None):
    _lb, _fn, _dp, _n = lb_number, folder_name, disk_path, notes

    def _run(c):
        c.execute(
            "INSERT OR IGNORE INTO my_collection(lb_number, folder_name, disk_path, notes)"
            " VALUES(?,?,?,?)",
            (_lb, _fn, _dp, _n)
        )
        return c.execute("SELECT changes()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection(lb_number, fields, db_path=None):
    allowed = {"folder_name", "disk_path", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    _params = list(updates.values()) + [lb_number]
    _sql = f"UPDATE my_collection SET {set_clause} WHERE lb_number=?"
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


def delete_from_collection(lb_number, db_path=None):
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM my_collection WHERE lb_number=?", (_lb,))
    )


def get_missing_from_collection(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT e.lb_number, e.date_str, e.location, e.rating, e.description,
                   lm.lb_status
            FROM entries e
            LEFT JOIN my_collection c ON e.lb_number = c.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
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


# ── FEAT-03: Per-Entry Personal Metadata ─────────────────────────────────────

def get_collection_meta(lb_number: int, db_path=None) -> dict:
    """Return personal metadata for a collection entry, with defaults if absent."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM collection_meta WHERE lb_number=?", (lb_number,)
        ).fetchone()
    return dict(row) if row else {
        "lb_number": lb_number, "personal_rating": None,
        "listen_count": 0, "last_listened": None, "tags": None,
    }


def set_collection_meta(lb_number: int, fields: dict, db_path=None) -> None:
    """Upsert personal metadata. Accepted keys: personal_rating, listen_count, last_listened, tags."""
    allowed = {"personal_rating", "listen_count", "last_listened", "tags"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    set_clause = ", ".join(f"{k}=?" for k in clean)
    _lb = lb_number
    _params = list(clean.values()) + [lb_number]
    _sql = f"UPDATE collection_meta SET {set_clause} WHERE lb_number=?"

    def _run(c):
        c.execute(
            "INSERT INTO collection_meta(lb_number) VALUES(?) ON CONFLICT(lb_number) DO NOTHING",
            (_lb,)
        )
        c.execute(_sql, _params)

    get_write_queue().execute(_run)


def increment_listen_count(lb_number: int, db_path=None) -> None:
    """Increment listen count and update last_listened timestamp."""
    from datetime import datetime
    _lb = lb_number
    _ts = datetime.utcnow().isoformat()
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_meta(lb_number, listen_count, last_listened) "
            "VALUES(?, 1, ?) ON CONFLICT(lb_number) DO UPDATE SET "
            "listen_count=listen_count+1, last_listened=excluded.last_listened",
            (_lb, _ts)
        )
    )


# ── FEAT-04: Wishlist ─────────────────────────────────────────────────────────

def get_wishlist(db_path=None) -> list:
    """Return all wishlist items joined with entry metadata."""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT w.id, w.lb_number, w.added_at, w.priority, w.notes,
                   e.date_str, e.location, e.rating, e.description
            FROM my_wishlist w
            LEFT JOIN entries e ON e.lb_number = w.lb_number
            ORDER BY w.priority DESC, w.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def add_to_wishlist(lb_number: int, priority: int = 3, notes: str = None, db_path=None) -> int:
    """Add an entry to the wishlist. Returns 1 if inserted, 0 if already present."""
    _lb, _p, _n = lb_number, priority, notes

    def _run(c):
        c.execute(
            "INSERT OR IGNORE INTO my_wishlist(lb_number, priority, notes) VALUES(?,?,?)",
            (_lb, _p, _n)
        )
        return c.execute("SELECT changes()").fetchone()[0]

    return get_write_queue().execute(_run)


def remove_from_wishlist(lb_number: int, db_path=None) -> None:
    """Remove an entry from the wishlist."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM my_wishlist WHERE lb_number=?", (_lb,))
    )


def get_wishlist_lb_numbers(db_path=None) -> list:
    """Return a flat list of lb_numbers currently on the wishlist."""
    with get_connection(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT lb_number FROM my_wishlist").fetchall()]


def get_xref_lb_numbers(db_path=None) -> list:
    """Return distinct lb_numbers that have at least one xref checksum (xref > 0)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lb_number FROM checksums WHERE xref > 0 ORDER BY lb_number"
        ).fetchall()
    return [r[0] for r in rows]


def get_xref_map(db_path=None) -> dict:
    """Return {lb_number: sorted list of distinct xref values} for entries with xref > 0."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lb_number, xref FROM checksums WHERE xref > 0 ORDER BY lb_number, xref"
        ).fetchall()
    result: dict = {}
    for lb, xref_val in rows:
        result.setdefault(lb, []).append(xref_val)
    return result


# ── FEAT-05: Duplicate Concert Detector ──────────────────────────────────────

def get_collection_duplicates(db_path=None) -> list:
    """Find date+location combos where the user owns more than one LB entry.

    Returns a list of groups, each with keys: date_str, location, owned, unowned.
    owned/unowned are lists of dicts with lb_number, rating, description.
    """
    with get_connection(db_path) as conn:
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


# ── FEAT-13: Granular Collection Data Management ──────────────────────────────

def purge_collection(db_path=None) -> None:
    """Delete all rows from collection_meta, integrity_events, and my_collection."""
    def _run(c):
        c.execute("DELETE FROM collection_meta")
        c.execute("DELETE FROM integrity_events")
        c.execute("DELETE FROM my_collection")
    get_write_queue().execute(_run)


def purge_wishlist(db_path=None) -> None:
    """Delete all rows from my_wishlist."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM my_wishlist"))


def purge_collection_meta(db_path=None) -> None:
    """Delete all personal ratings and tags (collection_meta only)."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM collection_meta"))


def purge_integrity_events(db_path=None) -> None:
    """Delete all watchdog integrity events."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM integrity_events"))


def purge_entry_changes(db_path=None) -> None:
    """Delete all scrape diff changelog rows from entry_changes."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM entry_changes"))


# ── Torrents ──────────────────────────────────────────────────────────────────

def get_torrents_for_lb(lb_number: int, db_path=None) -> list:
    """Return all torrent records for an LB entry, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM torrents WHERE lb_number=? ORDER BY created_at DESC",
            (lb_number,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_forum_post(lb_number: int, subject: str, topic_url: str,
                   board_id: int | None = None, db_path=None) -> int:
    """Record a successful forum post and return its new row id."""
    _lb, _s, _tu, _bid = lb_number, subject, topic_url, board_id

    def _run(c):
        cur = c.execute(
            "INSERT INTO forum_posts(lb_number, subject, topic_url, board_id) "
            "VALUES (?, ?, ?, ?)",
            (_lb, _s, _tu, _bid),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def get_forum_posts_for_lb(lb_number: int, db_path=None) -> list:
    """Return all forum post records for an LB entry, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM forum_posts WHERE lb_number=? ORDER BY posted_at DESC",
            (lb_number,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_forum_post(post_id: int, db_path=None) -> None:
    """Delete a forum post record by id."""
    _id = post_id
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM forum_posts WHERE id=?", (_id,))
    )


def get_all_forum_posts(db_path=None) -> list:
    """Return all forum posts across all LB entries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT fp.id, fp.lb_number, fp.subject, fp.topic_url,
                      fp.board_id, fp.posted_at,
                      e.date_str, e.location
               FROM forum_posts fp
               LEFT JOIN entries e ON e.lb_number = fp.lb_number
               ORDER BY fp.posted_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_torrents(db_path=None) -> list:
    """Return all torrent records across all LB entries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT t.id, t.lb_number, t.torrent_path, t.source_folder,
                      t.created_at, t.infohash, t.added_to_qbt, t.added_to_qbt_at,
                      t.qbt_infohash_confirmed, t.last_seen_at, t.excluded_files,
                      e.date_str, e.location
               FROM torrents t
               LEFT JOIN entries e ON e.lb_number = t.lb_number
               ORDER BY t.created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def add_torrent_record(lb_number: int, torrent_path: str, source_folder: str,
                       infohash: str, excluded_files: list | None = None,
                       db_path=None) -> int:
    """Insert a new torrent record. Returns the new row id."""
    import json as _json
    excl = _json.dumps(excluded_files or [])
    _lb, _tp, _sf, _ih, _ex = lb_number, torrent_path, source_folder, infohash, excl

    def _run(c):
        cur = c.execute(
            """INSERT INTO torrents(lb_number, torrent_path, source_folder, infohash, excluded_files)
               VALUES(?,?,?,?,?)""",
            (_lb, _tp, _sf, _ih, _ex)
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_torrent_record(torrent_id: int, fields: dict, db_path=None) -> None:
    """Update fields on a torrents row by id."""
    allowed = {
        "torrent_path", "source_folder", "infohash", "added_to_qbt",
        "added_to_qbt_at", "qbt_infohash_confirmed", "last_seen_at", "excluded_files",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    set_clause = ", ".join(f"{k}=?" for k in clean)
    _sql = f"UPDATE torrents SET {set_clause} WHERE id=?"
    _params = list(clean.values()) + [torrent_id]
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


# ── Rename History ─────────────────────────────────────────────────────────────

def add_rename_history(lb_number: int | None, old_path: str, new_path: str,
                       source: str, notes: str = "", db_path=None) -> None:
    """Insert a rename_history row."""
    _lb, _op, _np, _src, _nt = lb_number, old_path, new_path, source, notes
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT INTO rename_history(lb_number, old_path, new_path, source, notes)
               VALUES(?,?,?,?,?)""",
            (_lb, _op, _np, _src, _nt)
        )
    )


def delete_collection_entries(lb_numbers: list, db_path=None) -> int:
    """Remove specific LB entries from my_collection plus their associated meta/events.

    Returns the number of rows deleted from my_collection.
    """
    if not lb_numbers:
        return 0
    ph = ",".join("?" * len(lb_numbers))
    _lbs = lb_numbers

    def _run(c):
        c.execute(f"DELETE FROM collection_meta WHERE lb_number IN ({ph})", _lbs)
        c.execute(f"DELETE FROM integrity_events WHERE lb_number IN ({ph})", _lbs)
        cur = c.execute(f"DELETE FROM my_collection WHERE lb_number IN ({ph})", _lbs)
        return cur.rowcount

    return get_write_queue().execute(_run)


# ── lb_master integrity system ─────────────────────────────────────────────────

def backup_database(reason: str = "manual", db_path=None) -> "Path":
    """Create a consistent snapshot of the DB using VACUUM INTO.

    Output: data/backups/losslessbob_YYYY-MM-DD_HHMMSS_<reason>.db
    Keeps the 10 most recent backups, pruning older ones.
    Returns the Path of the new backup file.
    """
    import logging
    from datetime import datetime as _dt
    from backend.paths import DATA_DIR as _DATA

    backup_dir = _DATA / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _dt.utcnow().strftime("%Y-%m-%d_%H%M%S_%f")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    out_path = backup_dir / f"losslessbob_{ts}_{safe_reason}.db"

    conn = get_connection(db_path)
    conn.execute("VACUUM INTO ?", (str(out_path),))
    logging.getLogger(__name__).info("Database backed up to %s", out_path)

    # Prune: keep newest 10 backups only
    backups = sorted(backup_dir.glob("losslessbob_*.db"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-10]:
        try:
            old.unlink()
        except OSError:
            pass

    return out_path


def _compute_lb_status(has_web: bool, has_chk: bool, has_att: bool) -> tuple[str, int]:
    """Apply status-precedence rules. Returns (status, needs_review)."""
    if has_web or has_att:
        status = "public"
        # Attachments-only without a confirmed webpage → flag for review
        needs_review = 1 if (has_att and not has_web) else 0
    elif has_chk:
        status = "private"
        needs_review = 0
    else:
        status = "missing"
        needs_review = 0
    return status, needs_review


def migrate_lb_master(db_path=None) -> int:
    """Backfill lb_master for integers 1..MAX(lb_number) from existing data.

    Skipped when lb_master already contains rows (idempotent guard).
    Deletes entries.status='missing' tombstones after populating lb_master.
    Returns number of rows inserted, or 0 if skipped.
    """
    import logging
    conn = get_connection(db_path)

    existing = conn.execute("SELECT COUNT(*) FROM lb_master").fetchone()[0]
    if existing > 0:
        return 0

    max_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0]
    if not max_lb:
        return 0

    backup_database("pre_lb_master_migration", db_path)

    public_set = {r[0] for r in conn.execute(
        "SELECT lb_number FROM entries WHERE status='ok'")}
    checksum_set = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM checksums")}
    attach_set = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM entry_files")}

    missing_set = {r[0] for r in conn.execute("SELECT lb_number FROM lb_missing")}

    rows = []
    for n in range(1, max_lb + 1):
        if n in missing_set:
            status, needs_review = "nonexistent", 0
            hw = hc = ha = 0
        else:
            has_web = n in public_set
            has_chk = n in checksum_set
            has_att = n in attach_set
            status, needs_review = _compute_lb_status(has_web, has_chk, has_att)
            hw, hc, ha = int(has_web), int(has_chk), int(has_att)
        pnc = int(status == "public" and hc == 0)
        rows.append((n, status, hw, hc, ha, needs_review, pnc))

    _rows = rows

    def _run(c):
        c.executemany(
            """INSERT OR REPLACE INTO lb_master
               (lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                needs_review, public_no_checksums)
               VALUES (?,?,?,?,?,?,?)""",
            _rows,
        )
        # Remove tombstone rows — lb_master is now authoritative
        c.execute("DELETE FROM entries WHERE status='missing'")

    get_write_queue().execute(_run)

    logging.getLogger(__name__).info(
        "lb_master populated: %d rows (%d public, %d private, %d missing)",
        len(rows),
        sum(1 for r in rows if r[1] == "public"),
        sum(1 for r in rows if r[1] == "private"),
        sum(1 for r in rows if r[1] == "missing"),
    )
    return len(rows)


def reconcile_lb_status(lb_number: int, trigger: str = "reconcile", db_path=None) -> str:
    """Recompute lb_master status for a single LB from live data.

    Respects manual_override=1: updates has_* columns but does NOT change lb_status.
    Logs transitions to lb_status_history.
    Returns the final (possibly unchanged) lb_status string.
    """
    _lb, _trigger = lb_number, trigger

    def _run(conn) -> str:
        if conn.execute(
            "SELECT 1 FROM lb_missing WHERE lb_number=?", (_lb,)
        ).fetchone():
            auto_status, needs_review = "nonexistent", 0
            has_web = has_chk = has_att = False
        else:
            has_web = bool(conn.execute(
                "SELECT 1 FROM entries WHERE lb_number=? AND status='ok'", (_lb,)
            ).fetchone())
            has_chk = bool(conn.execute(
                "SELECT 1 FROM checksums WHERE lb_number=?", (_lb,)
            ).fetchone())
            has_att = bool(conn.execute(
                "SELECT 1 FROM entry_files WHERE lb_number=?", (_lb,)
            ).fetchone())
            auto_status, needs_review = _compute_lb_status(has_web, has_chk, has_att)

        existing = conn.execute(
            "SELECT lb_status, manual_override FROM lb_master WHERE lb_number=?",
            (_lb,),
        ).fetchone()

        if existing is None:
            initial_status = (
                "public"
                if _trigger == "flat_file_apply" and auto_status == "private"
                else auto_status
            )
            pnc = int(initial_status == "public" and not has_chk)
            conn.execute(
                """INSERT INTO lb_master
                   (lb_number, lb_status, has_webpage, has_checksums, has_attachments,
                    needs_review, public_no_checksums)
                   VALUES (?,?,?,?,?,?,?)""",
                (_lb, initial_status, int(has_web), int(has_chk), int(has_att),
                 needs_review, pnc),
            )
            conn.execute(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
                "VALUES (?,NULL,?,?)",
                (_lb, initial_status, _trigger),
            )
            return initial_status

        old_status = existing["lb_status"]
        manual_override = existing["manual_override"]

        if manual_override:
            pnc = int(old_status == "public" and not has_chk)
            conn.execute(
                """UPDATE lb_master
                   SET has_webpage=?, has_checksums=?, has_attachments=?,
                       needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
            return old_status

        final_status = auto_status
        pnc = int(final_status == "public" and not has_chk)
        if final_status != old_status:
            conn.execute(
                """UPDATE lb_master
                   SET lb_status=?, previous_status=?, has_webpage=?, has_checksums=?,
                       has_attachments=?, needs_review=?, public_no_checksums=?,
                       last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (final_status, old_status,
                 int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
            conn.execute(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
                "VALUES (?,?,?,?)",
                (_lb, old_status, final_status, _trigger),
            )
        else:
            conn.execute(
                """UPDATE lb_master
                   SET has_webpage=?, has_checksums=?, has_attachments=?,
                       needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP
                   WHERE lb_number=?""",
                (int(has_web), int(has_chk), int(has_att), needs_review, pnc, _lb),
            )
        return final_status

    return get_write_queue().execute(_run)


def batch_reconcile_lb_status(lb_numbers: list[int], trigger: str = "reconcile", db_path=None) -> None:
    """Reconcile lb_master for a batch of LB numbers in a single write transaction.

    Equivalent to calling reconcile_lb_status() for each entry individually, but
    uses bulk IN-queries so the total DB work is O(1) queries regardless of batch size
    instead of O(N). Designed for use by scrape_range() to avoid per-entry lock churn.

    Args:
        lb_numbers: LB numbers to reconcile. Duplicates are harmless.
        trigger: Value written to lb_status_history.trigger_event.
        db_path: Override the default database path (used in tests).
    """
    if not lb_numbers:
        return
    ph = ",".join("?" * len(lb_numbers))
    _lbs = lb_numbers
    _trigger = trigger

    def _run(conn) -> None:
        missing_set = {r[0] for r in conn.execute(
            f"SELECT lb_number FROM lb_missing WHERE lb_number IN ({ph})",
            _lbs,
        )}
        web_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM entries WHERE lb_number IN ({ph}) AND status='ok'",
            _lbs,
        )}
        chk_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM checksums WHERE lb_number IN ({ph})",
            _lbs,
        )}
        att_set = {r[0] for r in conn.execute(
            f"SELECT DISTINCT lb_number FROM entry_files WHERE lb_number IN ({ph})",
            _lbs,
        )}
        existing = {r[0]: r for r in conn.execute(
            f"SELECT lb_number, lb_status, manual_override FROM lb_master WHERE lb_number IN ({ph})",
            _lbs,
        )}

        insert_rows: list[tuple] = []
        history_rows: list[tuple] = []
        upd_override: list[tuple] = []
        upd_changed: list[tuple] = []
        upd_same: list[tuple] = []

        for lb in _lbs:
            if lb in missing_set:
                auto_status, needs_review = "nonexistent", 0
                hw = hc = ha = 0
            else:
                has_web = lb in web_set
                has_chk = lb in chk_set
                has_att = lb in att_set
                auto_status, needs_review = _compute_lb_status(has_web, has_chk, has_att)
                hw, hc, ha = int(has_web), int(has_chk), int(has_att)
            pnc = int(auto_status == "public" and hc == 0)

            if lb not in existing:
                initial_status = (
                    "public"
                    if _trigger == "flat_file_apply" and auto_status == "private"
                    else auto_status
                )
                pnc_initial = int(initial_status == "public" and hc == 0)
                insert_rows.append((lb, initial_status, hw, hc, ha, needs_review, pnc_initial))
                history_rows.append((lb, None, initial_status, _trigger))
                continue

            old_status = existing[lb]["lb_status"]
            manual = existing[lb]["manual_override"]
            if manual:
                pnc_manual = int(old_status == "public" and hc == 0)
                upd_override.append((hw, hc, ha, needs_review, pnc_manual, lb))
            elif auto_status != old_status:
                upd_changed.append((auto_status, old_status, hw, hc, ha, needs_review, pnc, lb))
                history_rows.append((lb, old_status, auto_status, _trigger))
            else:
                upd_same.append((hw, hc, ha, needs_review, pnc, lb))

        if insert_rows:
            conn.executemany(
                "INSERT INTO lb_master"
                " (lb_number, lb_status, has_webpage, has_checksums, has_attachments,"
                "  needs_review, public_no_checksums)"
                " VALUES (?,?,?,?,?,?,?)",
                insert_rows,
            )
        if history_rows:
            conn.executemany(
                "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event)"
                " VALUES (?,?,?,?)",
                history_rows,
            )
        if upd_override:
            conn.executemany(
                "UPDATE lb_master SET has_webpage=?, has_checksums=?, has_attachments=?,"
                " needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP"
                " WHERE lb_number=?",
                upd_override,
            )
        if upd_changed:
            conn.executemany(
                "UPDATE lb_master SET lb_status=?, previous_status=?, has_webpage=?,"
                " has_checksums=?, has_attachments=?, needs_review=?, public_no_checksums=?,"
                " last_status_at=CURRENT_TIMESTAMP WHERE lb_number=?",
                upd_changed,
            )
        if upd_same:
            conn.executemany(
                "UPDATE lb_master SET has_webpage=?, has_checksums=?, has_attachments=?,"
                " needs_review=?, public_no_checksums=?, last_status_at=CURRENT_TIMESTAMP"
                " WHERE lb_number=?",
                upd_same,
            )

    get_write_queue().execute(_run)


def reconcile_all_lb_master(db_path=None) -> dict:
    """Full rebuild of lb_master, extending to new max lb_number.

    Respects existing manual_override rows.
    Returns counts by status.
    """
    backup_database("pre_reconcile_all", db_path)

    conn = get_connection(db_path)
    max_lb = conn.execute("SELECT MAX(lb_number) FROM checksums").fetchone()[0] or 0
    # Also include LBs already in lb_master (they may exceed checksums max after deletions)
    master_max = conn.execute("SELECT MAX(lb_number) FROM lb_master").fetchone()[0] or 0
    # Also include scraped entries (public pages with no checksums would be missed otherwise)
    entries_max = conn.execute("SELECT MAX(lb_number) FROM entries").fetchone()[0] or 0
    effective_max = max(max_lb, master_max, entries_max)
    if effective_max == 0:
        return {"public": 0, "private": 0, "missing": 0, "max_lb": 0}

    batch_reconcile_lb_status(list(range(1, effective_max + 1)), trigger="reconcile", db_path=db_path)

    stats = get_lb_master_stats(db_path)
    return stats


def set_lb_manual_override(lb_number: int, status: str, notes: str,
                           set_by: str = "user", db_path=None) -> None:
    """Set a manual override on an lb_master row."""
    from datetime import datetime as _dt
    _lb, _status, _notes, _set_by = lb_number, status, notes, set_by
    _now = _dt.utcnow().isoformat()

    def _run(conn) -> None:
        existing = conn.execute(
            "SELECT lb_status FROM lb_master WHERE lb_number=?", (_lb,)
        ).fetchone()
        old_status = existing["lb_status"] if existing else None
        conn.execute(
            """INSERT INTO lb_master(lb_number, lb_status, manual_override, manual_status,
                   manual_notes, manual_set_by, manual_set_at, needs_review,
                   has_webpage, has_checksums, has_attachments)
               VALUES(?,?,1,?,?,?,?,0,0,0,0)
               ON CONFLICT(lb_number) DO UPDATE SET
                   lb_status=excluded.lb_status,
                   manual_override=1,
                   manual_status=excluded.manual_status,
                   manual_notes=excluded.manual_notes,
                   manual_set_by=excluded.manual_set_by,
                   manual_set_at=excluded.manual_set_at,
                   last_status_at=CURRENT_TIMESTAMP""",
            (_lb, _status, _status, _notes, _set_by, _now),
        )
        conn.execute(
            "INSERT INTO lb_status_history(lb_number, old_status, new_status, trigger_event) "
            "VALUES(?,?,?,'manual')",
            (_lb, old_status, _status),
        )

    get_write_queue().execute(_run)


def clear_lb_manual_override(lb_number: int, db_path=None) -> str:
    """Clear a manual override and immediately reconcile. Returns new auto status."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute(
            """UPDATE lb_master SET manual_override=0, manual_status=NULL,
                   manual_notes=NULL, manual_set_by=NULL, manual_set_at=NULL
               WHERE lb_number=?""",
            (_lb,),
        )
    )
    return reconcile_lb_status(lb_number, trigger="manual_clear", db_path=db_path)


def export_overrides(db_path=None) -> list[dict]:
    """Return all manual overrides as a list of dicts for JSON export.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        List of dicts with keys: lb_number, manual_status, manual_notes,
        manual_set_by, manual_set_at — one per lb_master row where
        manual_override=1, ordered by lb_number ascending.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT lb_number, manual_status, manual_notes, manual_set_by, manual_set_at
           FROM lb_master WHERE manual_override=1 ORDER BY lb_number"""
    ).fetchall()
    return [dict(r) for r in rows]


def import_overrides(overrides: list[dict], db_path=None) -> dict:
    """Upsert a list of override dicts into lb_master.

    Skips entries whose lb_number is out of the valid range (< 1 or greater
    than the current MAX(lb_number) in lb_master).  Writes an
    lb_status_history row with trigger_event='import' for each upserted row.

    Args:
        overrides: List of dicts, each containing at minimum ``lb_number``.
            Optional keys: ``manual_status``, ``manual_notes``,
            ``manual_set_by``.
        db_path: Optional path to the SQLite database file.

    Returns:
        Dict ``{imported: int, skipped: int}``.
    """
    conn = get_connection(db_path)
    max_lb = conn.execute("SELECT MAX(lb_number) FROM lb_master").fetchone()[0] or 0
    imported = 0
    skipped = 0
    for item in overrides:
        lb = item.get("lb_number")
        if not isinstance(lb, int) or lb < 1 or lb > max_lb:
            skipped += 1
            continue
        set_lb_manual_override(
            lb,
            item.get("manual_status", ""),
            item.get("manual_notes", ""),
            item.get("manual_set_by", "import"),
            db_path,
        )
        # The history row for the manual call is already written by
        # set_lb_manual_override; add a second row to record the import event.
        _lb_import = lb
        get_write_queue().execute(
            lambda c: c.execute(
                """INSERT INTO lb_status_history (lb_number, old_status, new_status, trigger_event)
                   SELECT lb_number, previous_status, lb_status, 'import'
                   FROM lb_master WHERE lb_number=?""",
                (_lb_import,),
            )
        )
        imported += 1
    logging.getLogger(__name__).info(
        "import_overrides: %d imported, %d skipped", imported, skipped
    )
    return {"imported": imported, "skipped": skipped}


def get_lb_master_row(lb_number: int, db_path=None) -> dict | None:
    """Return the lb_master row for an LB number, or None if absent."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM lb_master WHERE lb_number=?", (lb_number,)
    ).fetchone()
    return dict(row) if row else None


def get_lb_master_stats(db_path=None) -> dict:
    """Return {public, private, missing, max_lb, overrides, needs_review} counts."""
    conn = get_connection(db_path)
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN lb_status='public'      THEN 1 ELSE 0 END), 0) AS public,
            COALESCE(SUM(CASE WHEN lb_status='private'     THEN 1 ELSE 0 END), 0) AS private,
            COALESCE(SUM(CASE WHEN lb_status='missing'     THEN 1 ELSE 0 END), 0) AS missing,
            COALESCE(SUM(CASE WHEN lb_status='nonexistent' THEN 1 ELSE 0 END), 0) AS nonexistent,
            COALESCE(MAX(lb_number), 0)                                             AS max_lb,
            COALESCE(SUM(manual_override), 0)                                       AS overrides,
            COALESCE(SUM(needs_review), 0)                                          AS needs_review,
            COALESCE(SUM(public_no_checksums), 0)                                   AS public_no_checksums
        FROM lb_master
    """).fetchone()
    return dict(row) if row else {
        "public": 0, "private": 0, "missing": 0, "nonexistent": 0,
        "max_lb": 0, "overrides": 0, "needs_review": 0, "public_no_checksums": 0,
    }


def is_lb_missing(lb_number: int, db_path=None) -> bool:
    """Return True if lb_number is in lb_missing (confirmed to not exist on the LB site)."""
    conn = get_connection(db_path)
    return bool(conn.execute(
        "SELECT 1 FROM lb_missing WHERE lb_number=?", (lb_number,)
    ).fetchone())


def get_lb_missing_list(db_path=None) -> list[dict]:
    """Return all rows in lb_missing ordered by lb_number."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT lb_number, confirmed_date, notes FROM lb_missing ORDER BY lb_number"
    ).fetchall()
    return [dict(r) for r in rows]


def add_lb_missing(lb_number: int, confirmed_date: str = "", notes: str = "",
                   db_path=None) -> None:
    """Add an lb_number to lb_missing and immediately reconcile its lb_master status."""
    _lb, _date, _notes = lb_number, confirmed_date, notes

    def _run(conn) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO lb_missing(lb_number, confirmed_date, notes) VALUES(?,?,?)",
            (_lb, _date, _notes),
        )

    get_write_queue().execute(_run)
    reconcile_lb_status(lb_number, trigger="lb_missing_add", db_path=db_path)


def remove_lb_missing(lb_number: int, db_path=None) -> None:
    """Remove an lb_number from lb_missing and immediately reconcile its lb_master status."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_missing WHERE lb_number=?", (_lb,))
    )
    reconcile_lb_status(lb_number, trigger="lb_missing_remove", db_path=db_path)


def get_lb_status(lb_number: int, db_path=None) -> str | None:
    """Return lb_master.lb_status for a single LB, or None if not in table."""
    row = get_lb_master_row(lb_number, db_path)
    return row["lb_status"] if row else None


def get_lb_statuses_batch(lb_numbers: "list[int]", db_path=None) -> "dict[int, str]":
    """Return {lb_number: lb_status} for every lb_number present in lb_master.

    Missing entries are absent from the result dict.  Intended for bulk
    UI colouring (e.g. the Attachments tree page render) to avoid N individual
    queries.
    """
    if not lb_numbers:
        return {}
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT lb_number, lb_status FROM lb_master WHERE lb_number IN ({})".format(
            ",".join("?" * len(lb_numbers))
        ),
        lb_numbers,
    ).fetchall()
    return {r["lb_number"]: r["lb_status"] for r in rows}


def should_mark_nft(lb_number: int, db_path=None) -> bool:
    """Return True if folders for lb_number should carry the -NFT suffix.

    An LB is marked NFT when lb_status is 'private' — it has checksums
    but no published webpage, indicating the webmaster has not released it.
    """
    return get_lb_status(lb_number, db_path) == "private"


def is_postable_to_forum(lb_number: int, db_path=None) -> tuple[bool, str | None]:
    """Return (allowed, reason) for forum posting.

    Blocks private and missing LBs; passes public ones.
    Blocks with 'status_unknown' if the LB has no lb_master row at all.
    """
    status = get_lb_status(lb_number, db_path)
    if status is None:
        return False, "status_unknown"
    if status == "private":
        return False, "lb_private"
    if status == "missing":
        return False, "lb_missing"
    return True, None


def get_lb_master_list(status: str | None = None, override_only: bool = False,
                       review_only: bool = False, limit: int = 500,
                       offset: int = 0, db_path=None) -> list[dict]:
    """Return paginated lb_master rows with optional filters."""
    conn = get_connection(db_path)
    clauses = []
    params: list = []
    if status:
        clauses.append("lb_status=?")
        params.append(status)
    if override_only:
        clauses.append("manual_override=1")
    if review_only:
        clauses.append("needs_review=1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM lb_master {where} ORDER BY lb_number LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def get_lb_status_history(lb_number: int, limit: int = 50, db_path=None) -> list[dict]:
    """Return transition history for a single LB, newest first."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM lb_status_history WHERE lb_number=? ORDER BY changed_at DESC LIMIT ?",
        (lb_number, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Curator mode (user-local meta flag) ────────────────────────────────────────

def is_curator(db_path=None) -> bool:
    """Return True if the local install is flagged as the curator.

    Curator mode unlocks master-data publishing UI in Setup tab and
    write access to alias/override editing once those features ship.
    The flag is stored in `meta.is_curator='1'|'0'` and never ships in
    a master export (it's in USER_META_KEYS).
    """
    return (get_meta("is_curator", db_path) or "0") == "1"


def set_curator(enabled: bool, db_path=None) -> None:
    """Toggle the curator flag for this install."""
    set_meta("is_curator", "1" if enabled else "0", db_path)


# ── Master data export / import ───────────────────────────────────────────────

def export_master_db(reason: str = "publish", db_path=None) -> "tuple[Path, dict]":
    """Produce a master-only snapshot of the DB plus a manifest sidecar.

    Pipeline:
      1. ``VACUUM INTO`` a snapshot file → consistent point-in-time copy.
      2. On the snapshot: DROP every table in :data:`USER_TABLES`.
      3. Delete every ``meta`` row whose key is not in :data:`MASTER_META_KEYS`.
      4. Stamp ``master_version`` (UTC timestamp), ``master_published_at`` (now),
         and ``master_schema_version`` (current code constant).
      5. ``VACUUM`` to reclaim freed space.
      6. **Verify** the snapshot contains no USER_TABLES and no non-master meta.
      7. Compute SHA256 of the final snapshot file.
      8. Write ``<snapshot>.manifest.json`` sidecar with counts + SHA + version.

    Returns:
        (snapshot_path, manifest_dict)

    Raises:
        RuntimeError: If the verification step finds residual user data.
    """
    import hashlib
    import json
    import logging
    from datetime import datetime as _dt
    from backend.paths import DATA_DIR as _DATA

    log = logging.getLogger(__name__)
    export_dir = _DATA / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    ts = _dt.utcnow().strftime("%Y-%m-%d_%H%M%S")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    out_path = export_dir / f"losslessbob_master_{ts}_{safe_reason}.db"
    manifest_path = export_dir.joinpath(out_path.name + ".manifest.json")

    # Step 1: consistent snapshot via VACUUM INTO
    src = get_connection(db_path)
    src.execute("VACUUM INTO ?", (str(out_path),))
    log.info("Master export snapshot created at %s", out_path)

    # Steps 2-5: clean the snapshot in-place (separate connection on the file)
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
        published_at = _dt.utcnow().isoformat()
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
        snap.commit()
        snap.execute("VACUUM")

        # Step 6: VERIFY
        # 6a. No user tables present
        present = {r[0] for r in snap.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        leaked = present & set(USER_TABLES)
        if leaked:
            raise RuntimeError(
                f"Master export verification failed: user tables present in "
                f"snapshot: {sorted(leaked)}"
            )
        # 6b. No non-master meta keys
        non_master = [r[0] for r in snap.execute(
            f"SELECT key FROM meta WHERE key NOT IN ({placeholders})",
            tuple(MASTER_META_KEYS),
        ).fetchall()]
        if non_master:
            raise RuntimeError(
                f"Master export verification failed: non-master meta keys "
                f"present in snapshot: {sorted(non_master)}"
            )
        # 6c. Sanity: lb_master populated (otherwise this isn't a useful release)
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

    # Step 7: SHA256 of the final file
    sha = hashlib.sha256()
    with open(out_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    sha256 = sha.hexdigest()
    size_bytes = out_path.stat().st_size

    # Step 8: manifest sidecar
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
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    log.info(
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
        lines.append(f"## Status changes ({len(rows)})\n")
        for r in rows:
            old = r["old_status"] or "—"
            new = r["new_status"]
            ts = (r["changed_at"] or "")[:10]
            trigger = r["trigger_event"] or ""
            lines.append(f"- LB-{r['lb_number']:05d}: {old} → {new}  _{ts}_ {trigger}")
        lines.append("")

    if overrides:
        lines.append(f"## Manual overrides ({len(overrides)})\n")
        for o in overrides:
            note = f" — {o['manual_notes']}" if o.get("manual_notes") else ""
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
        owned, lat, lon, display_name.
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
               geo.lat, geo.lon, geo.display_name
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

    for row in rows:
        if row["lat"] is not None and row["lon"] is not None:
            markers.append({
                "lb_number": row["lb_number"],
                "date_str": row["date_str"],
                "location": row["location"],
                "lb_status": row["lb_status"],
                "owned": bool(row["owned"]),
                "lat": row["lat"],
                "lon": row["lon"],
                "display_name": row["display_name"],
            })
        else:
            unplottable_count += 1

    return {"markers": markers, "unplottable_count": unplottable_count}


def import_master_db(snapshot_path: "Path | str", db_path=None) -> dict:
    """Import a master snapshot into the local DB, preserving user data.

    Pipeline:
      1. Load + validate the manifest sidecar (SHA256 must match the .db file).
      2. Schema version guard: refuse if incoming version > local
         :data:`MASTER_SCHEMA_VERSION`.
      3. Take an automatic backup (``reason='pre_master_import'``).
      4. ``ATTACH DATABASE`` the incoming snapshot as ``incoming``.
      5. For each table in :data:`MASTER_TABLES`:
            ``DELETE FROM main.<t>;
             INSERT INTO main.<t> SELECT * FROM incoming.<t>;``
      6. For meta: replace only the keys in :data:`MASTER_META_KEYS`;
         leave user keys (theme, qbt_*, wtrf_*, is_curator, ...) untouched.
      7. ``INSERT INTO entries_fts(entries_fts) VALUES('rebuild');``
      8. ``DETACH DATABASE incoming``.

    Returns:
        Summary dict: ``{master_version, rows_per_table, lb_status_counts,
        backup_path, lb_status_changes}``.

    Raises:
        FileNotFoundError: snapshot or manifest missing.
        ValueError: SHA256 mismatch.
        RuntimeError: schema version too new for this client.
    """
    import hashlib
    import json
    import logging
    from datetime import datetime as _dt

    log = logging.getLogger(__name__)
    snapshot_path = Path(snapshot_path)
    manifest_path = snapshot_path.with_name(snapshot_path.name + ".manifest.json")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Master snapshot not found: {snapshot_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found alongside snapshot: {manifest_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
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
    log.info("Pre-import backup written to %s", backup_path)

    # Step 4-7: copy under a transaction
    conn = get_connection(db_path)
    # Snapshot pre-import lb_status distribution so we can report what changed
    pre_status = {r[0]: r[1] for r in conn.execute(
        "SELECT lb_status, COUNT(*) FROM lb_master GROUP BY lb_status"
    ).fetchall()}

    with _write_lock:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(f"ATTACH DATABASE ? AS incoming", (str(snapshot_path),))
            try:
                row_counts: dict[str, int] = {}
                # Order matters when FKs exist (entries before entry_files etc.),
                # but with foreign_keys OFF for this scope it doesn't.
                for tbl in MASTER_TABLES:
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
                    log.warning("FTS rebuild failed (will rebuild on next FTS access): %s", e)
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

    return {
        "master_version": manifest.get("master_version"),
        "master_published_at": manifest.get("master_published_at"),
        "row_counts": row_counts,
        "pre_status_counts": pre_status,
        "post_status_counts": post_status,
        "lb_status_changes": changed,
        "backup_path": str(backup_path),
        "imported_at": _dt.utcnow().isoformat(),
    }


# ── lb_alias helpers ──────────────────────────────────────────────────────────

def resolve_aliases(lb_numbers: list[int], db_path=None) -> list[int]:
    """Collapse alias LBs to their canonical LBs. Returns de-duped canonical list.

    Each alias maps to exactly one canonical (max 1 hop; chain rewrites are
    enforced on insert by :func:`add_lb_alias`).

    Args:
        lb_numbers: List of LB numbers to resolve.
        db_path: Optional path to the SQLite database file.

    Returns:
        De-duplicated list of canonical LB numbers, preserving order of
        first occurrence.
    """
    if not lb_numbers:
        return []
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(lb_numbers))
    alias_map = {
        r["alias_lb"]: r["canonical_lb"]
        for r in conn.execute(
            f"SELECT alias_lb, canonical_lb FROM lb_alias WHERE alias_lb IN ({placeholders})",
            lb_numbers,
        )
    }
    resolved = [alias_map.get(lb, lb) for lb in lb_numbers]
    # De-dup preserving order of first occurrence
    seen: set[int] = set()
    out: list[int] = []
    for lb in resolved:
        if lb not in seen:
            seen.add(lb)
            out.append(lb)
    return out


def get_folder_link(folder_path: str, db_path=None) -> dict | None:
    """Return the folder_lb_link row for a path, or None.

    Args:
        folder_path: Absolute path of the folder.
        db_path: Optional path to the SQLite database file.

    Returns:
        Row as a dict with keys folder_path, lb_number, linked_at, note,
        or None if no link is stored.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM folder_lb_link WHERE folder_path=?", (folder_path,)
    ).fetchone()
    return dict(row) if row else None


def set_folder_link(folder_path: str, lb_number: int, note: str = "", db_path=None) -> None:
    """Create or replace a folder→LB link.

    Args:
        folder_path: Absolute path of the folder.
        lb_number: LB number to link this folder to.
        note: Optional user note.
        db_path: Optional path to the SQLite database file.
    """
    _fp, _lb, _note = folder_path, lb_number, note
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT OR REPLACE INTO folder_lb_link (folder_path, lb_number, note, linked_at) "
            "VALUES (?,?,?,CURRENT_TIMESTAMP)",
            (_fp, _lb, _note),
        )
    )


def delete_folder_link(folder_path: str, db_path=None) -> None:
    """Remove a folder→LB link.

    Args:
        folder_path: Absolute path of the folder whose link should be deleted.
        db_path: Optional path to the SQLite database file.
    """
    _fp = folder_path
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_fp,))
    )


def add_lb_alias(
    alias_lb: int,
    canonical_lb: int,
    relationship: str = "duplicate",
    note: str = "",
    db_path=None,
) -> dict:
    """Add an alias mapping. Validates no cycles, rewrites chains if needed.

    Each alias is stored with max 1 hop: if canonical_lb is itself an alias,
    the target is rewritten to its canonical before storing.

    Args:
        alias_lb: The LB number being aliased (the 'wrong' or secondary one).
        canonical_lb: The LB number this alias resolves to.
        relationship: One of 'duplicate', 'supersedes', 'see_also'.
        note: Optional curator note.
        db_path: Optional path to the SQLite database file.

    Returns:
        Dict with keys alias_lb (int), canonical_lb (int), rewrote_chain (bool).

    Raises:
        ValueError: If alias_lb == canonical_lb, or if adding the alias
            would create a cycle.
    """
    if alias_lb == canonical_lb:
        raise ValueError("alias_lb and canonical_lb must differ")
    conn = get_connection(db_path)

    # Chain rewrite: if canonical_lb is itself an alias, use its canonical
    canon_of_canon = conn.execute(
        "SELECT canonical_lb FROM lb_alias WHERE alias_lb=?", (canonical_lb,)
    ).fetchone()
    rewrote = False
    if canon_of_canon:
        canonical_lb = canon_of_canon["canonical_lb"]
        rewrote = True

    # Cycle prevention: canonical must not be an alias of alias_lb
    would_cycle = conn.execute(
        "SELECT 1 FROM lb_alias WHERE alias_lb=? AND canonical_lb=?",
        (canonical_lb, alias_lb),
    ).fetchone()
    if would_cycle:
        raise ValueError(
            f"Adding alias {alias_lb}→{canonical_lb} would create a cycle"
        )

    _a, _c, _r, _n = alias_lb, canonical_lb, relationship, note
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT OR REPLACE INTO lb_alias (alias_lb, canonical_lb, relationship, note) "
            "VALUES (?,?,?,?)",
            (_a, _c, _r, _n),
        )
    )
    return {"alias_lb": alias_lb, "canonical_lb": canonical_lb, "rewrote_chain": rewrote}


def delete_lb_alias(alias_lb: int, db_path=None) -> None:
    """Remove an alias entry.

    Args:
        alias_lb: The alias LB number whose entry should be removed.
        db_path: Optional path to the SQLite database file.
    """
    _lb = alias_lb
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_alias WHERE alias_lb=?", (_lb,))
    )


def get_lb_aliases(canonical_lb: int | None = None, db_path=None) -> list[dict]:
    """Return alias rows, optionally filtered by canonical_lb.

    Args:
        canonical_lb: If provided, only return aliases that map to this
            canonical LB number.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of row dicts with keys alias_lb, canonical_lb, relationship,
        note, created_at.
    """
    conn = get_connection(db_path)
    if canonical_lb is not None:
        rows = conn.execute(
            "SELECT * FROM lb_alias WHERE canonical_lb=? ORDER BY alias_lb",
            (canonical_lb,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM lb_alias ORDER BY alias_lb"
        ).fetchall()
    return [dict(r) for r in rows]


def get_aliases_for_canonical(canonical_lb: int, db_path=None) -> list[int]:
    """Return sorted list of alias LB numbers that map to the given canonical.

    Args:
        canonical_lb: The canonical LB number.
        db_path: Optional path to the SQLite database file.

    Returns:
        Sorted list of alias_lb integers pointing to canonical_lb.
    """
    return sorted(r["alias_lb"] for r in get_lb_aliases(canonical_lb, db_path))


# ── Bootleg-CD Catalog ────────────────────────────────────────────────────────

_BOOTLEG_SOURCE_URL = (
    "http://www.losslessbob.wonderingwhattochoose.com/detail/LB-bootleg-by-title.html"
)


def get_bootleg_lb_numbers(db_path=None) -> list[int]:
    """Return sorted list of lb_numbers that have at least one bootleg title."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lb_number FROM bootleg_titles ORDER BY lb_number"
        ).fetchall()
    return [r[0] for r in rows]


def get_bootlegs_for_lb(lb_number: int, db_path=None) -> list[dict]:
    """Return all bootleg_titles rows for one LB, ordered by date_iso NULLS LAST."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bootleg_titles WHERE lb_number=? "
            "ORDER BY date_iso NULLS LAST, title COLLATE NOCASE",
            (lb_number,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_bootleg_stats(db_path=None) -> dict:
    """Return summary counts and most-recent scrape info."""
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM bootleg_titles").fetchone()[0]
        last_scrape = conn.execute(
            "SELECT scraped_at, status, rows_added, rows_changed, rows_removed "
            "FROM bootleg_scrapes ORDER BY scraped_at DESC LIMIT 1"
        ).fetchone()
    result: dict = {"total": total}
    if last_scrape:
        result["last_scraped_at"] = last_scrape["scraped_at"]
        result["last_status"] = last_scrape["status"]
    return result


def get_bootlegs(
    q: str = "",
    year_min: int | None = None,
    year_max: int | None = None,
    cd_min: int | None = None,
    cd_max: int | None = None,
    lb_status: str | None = None,
    owned: bool | None = None,
    has_lbbcd: bool | None = None,
    sort_col: str = "lb_number",
    sort_dir: str = "ASC",
    limit: int = 200,
    offset: int = 0,
    db_path=None,
) -> tuple[list[dict], int]:
    """Paginated, filtered bootleg list joined with lb_master and my_collection.

    Returns (rows, total_count).
    """
    _SORT_COLS = {
        "lb_number": "bt.lb_number",
        "title":     "bt.title COLLATE NOCASE",
        "date_iso":  "bt.date_iso NULLS LAST",
        "year":      "bt.year NULLS LAST",
        "location":  "bt.location COLLATE NOCASE",
        "cd_count":  "bt.cd_count",
        "lbbcd_id":  "bt.lbbcd_id NULLS LAST",
        "lb_status": "lm.lb_status",
    }
    order_expr = _SORT_COLS.get(sort_col, "bt.lb_number")
    direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"

    conditions: list[str] = []
    params: list = []

    if q:
        conditions.append("(bt.title LIKE ? OR bt.location LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    if year_min is not None:
        conditions.append("bt.year >= ?")
        params.append(year_min)
    if year_max is not None:
        conditions.append("bt.year <= ?")
        params.append(year_max)
    if cd_min is not None:
        conditions.append("bt.cd_count >= ?")
        params.append(cd_min)
    if cd_max is not None:
        conditions.append("bt.cd_count <= ?")
        params.append(cd_max)
    if lb_status:
        conditions.append("lm.lb_status = ?")
        params.append(lb_status)
    if owned is True:
        conditions.append("mc.lb_number IS NOT NULL")
    elif owned is False:
        conditions.append("mc.lb_number IS NULL")
    if has_lbbcd is True:
        conditions.append("bt.lbbcd_id IS NOT NULL")
    elif has_lbbcd is False:
        conditions.append("bt.lbbcd_id IS NULL")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    base_sql = f"""
        FROM bootleg_titles bt
        LEFT JOIN lb_master lm ON lm.lb_number = bt.lb_number
        LEFT JOIN my_collection mc ON mc.lb_number = bt.lb_number
        {where}
    """
    conn = get_connection(db_path)
    total = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT bt.*, lm.lb_status, mc.lb_number IS NOT NULL AS owned {base_sql} "
        f"ORDER BY {order_expr} {direction} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def get_bootleg_scrape_history(limit: int = 20, db_path=None) -> list[dict]:
    """Return recent bootleg_scrapes rows, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bootleg_scrapes ORDER BY scraped_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Site crawler sessions + inventory ─────────────────────────────────────────

def create_scrape_session(scope: str, start_url: str = "", db_path=None) -> int:
    """Insert a new scrape_sessions row and return its id."""
    _scope, _url = scope, start_url

    def _run(conn) -> int:
        cur = conn.execute(
            "INSERT INTO scrape_sessions(scope, start_url, status) VALUES(?,?,'running')",
            (_scope, _url),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_scrape_session(
    session_id: int,
    status: str = "done",
    pages_fetched: int = 0,
    pages_304: int = 0,
    pages_skipped: int = 0,
    pages_failed: int = 0,
    files_fetched: int = 0,
    notes: str = "",
    db_path=None,
) -> None:
    """Close a scrape session with final counts."""
    _sid = session_id
    _st, _pf, _p304, _ps, _pfail, _ff, _notes = (
        status, pages_fetched, pages_304, pages_skipped,
        pages_failed, files_fetched, notes,
    )
    get_write_queue().execute(
        lambda c: c.execute(
            """UPDATE scrape_sessions
               SET finished_at=CURRENT_TIMESTAMP, status=?,
                   pages_fetched=?, pages_304=?, pages_skipped=?,
                   pages_failed=?, files_fetched=?, notes=?
               WHERE id=?""",
            (_st, _pf, _p304, _ps, _pfail, _ff, _notes, _sid),
        )
    )


def get_scrape_sessions(limit: int = 50, db_path=None) -> list[dict]:
    """Return recent scrape_sessions rows, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_sessions ORDER BY started_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_inventory(url: str, db_path=None, **fields) -> None:
    """Insert or update a site_inventory row for *url*.

    Keyword args map directly to column names.  Only the supplied keys are
    updated on conflict — unsupplied columns are left unchanged.
    """
    _url = url
    _fields = dict(fields)

    def _run(conn) -> None:
        # Ensure row exists first (INSERT OR IGNORE so discovered_at stays)
        conn.execute(
            "INSERT OR IGNORE INTO site_inventory(url) VALUES(?)", (_url,)
        )
        if _fields:
            set_clause = ", ".join(f"{k}=?" for k in _fields)
            conn.execute(
                f"UPDATE site_inventory SET {set_clause} WHERE url=?",
                list(_fields.values()) + [_url],
            )

    get_write_queue().execute(_run)


def get_inventory_stats(db_path=None) -> dict:
    """Return counts grouped by status plus total discovered."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM site_inventory GROUP BY status"
    ).fetchall()
    stats: dict = {r["status"]: r["n"] for r in rows}
    stats["total"] = sum(stats.values())
    return stats


def get_inventory_page(
    status: str | None = None,
    content_type: str | None = None,
    path_prefix: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db_path=None,
) -> tuple[list[dict], int]:
    """Paginated, filtered site_inventory list. Returns (rows, total)."""
    conditions: list[str] = []
    params: list = []
    if status:
        conditions.append("status=?")
        params.append(status)
    if content_type:
        conditions.append("content_type LIKE ?")
        params.append(f"%{content_type}%")
    if path_prefix:
        conditions.append("relative_path LIKE ?")
        params.append(f"{path_prefix}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    conn = get_connection(db_path)
    total = conn.execute(
        f"SELECT COUNT(*) FROM site_inventory {where}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM site_inventory {where} "
        f"ORDER BY url LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def get_pending_urls(db_path=None) -> list[dict]:
    """Return all URLs with status pending or failed, with last_modified."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT url, last_modified FROM site_inventory "
            "WHERE status IN ('pending', 'failed') ORDER BY url"
        ).fetchall()
    return [dict(r) for r in rows]


def get_downloaded_urls(db_path=None) -> set[str]:
    """Return the set of URLs already downloaded or confirmed not found."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT url FROM site_inventory "
            "WHERE status IN ('downloaded', 'not_found', 'skipped')"
        ).fetchall()
    return {r["url"] for r in rows}


# ── lb_problems ───────────────────────────────────────────────────────────────

def get_lb_problems(lb_number: int | None = None, db_path=None) -> list[dict]:
    """Return lb_problems rows, optionally filtered to a single LB number.

    Args:
        lb_number: When provided, only return rows for that LB number.
        db_path: Optional database path override.

    Returns:
        List of dicts with keys: id, lb_number, notes, added.
    """
    conn = get_connection(db_path)
    if lb_number is not None:
        rows = conn.execute(
            "SELECT id, lb_number, notes, added FROM lb_problems "
            "WHERE lb_number=? ORDER BY added DESC",
            (lb_number,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, lb_number, notes, added FROM lb_problems "
            "ORDER BY lb_number, added DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_lb_problem(lb_number: int, notes: str, added: str | None = None, db_path=None) -> int:
    """Insert an lb_problems row and return the new row id.

    Args:
        lb_number: The LB number this problem applies to.
        notes: Free-text description of the problem.
        added: ISO date string (YYYY-MM-DD); defaults to today.
        db_path: Optional database path override.

    Returns:
        The rowid of the newly-inserted row.
    """
    from datetime import date as _date
    _lb, _n, _d = lb_number, notes, added or _date.today().isoformat()

    def _run(c):
        cur = c.execute(
            "INSERT INTO lb_problems(lb_number, notes, added) VALUES(?,?,?)",
            (_lb, _n, _d),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_lb_problem(problem_id: int, notes: str, db_path=None) -> None:
    """Update the notes field of an lb_problems row by id.

    Args:
        problem_id: The primary key of the row to update.
        notes: Replacement notes text.
        db_path: Optional database path override.
    """
    _id, _n = problem_id, notes
    get_write_queue().execute(
        lambda c: c.execute("UPDATE lb_problems SET notes=? WHERE id=?", (_n, _id))
    )


def delete_lb_problem(problem_id: int, db_path=None) -> None:
    """Delete an lb_problems row by id.

    Args:
        problem_id: The primary key of the row to delete.
        db_path: Optional database path override.
    """
    _id = problem_id
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_problems WHERE id=?", (_id,))
    )


def get_lb_problem_count(lb_number: int, db_path=None) -> int:
    """Return the number of open problem notes for an LB number.

    Args:
        lb_number: The LB number to count problems for.
        db_path: Optional database path override.

    Returns:
        Integer count of rows in lb_problems for this lb_number.
    """
    conn = get_connection(db_path)
    return conn.execute(
        "SELECT COUNT(*) FROM lb_problems WHERE lb_number=?", (lb_number,)
    ).fetchone()[0]
