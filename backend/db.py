import logging
import re
import sqlite3
import threading
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
_bloom_lock = threading.Lock()


# --- Master vs. user data ownership model -------------------------------------
# MASTER tables ship in a master-data export and are overwritten on import.
# USER tables stay local to each install and never appear in an export.
# See instructions/CC_LB_INTEGRITY.md §Data Ownership Model.

MASTER_SCHEMA_VERSION = 11  # bumped: entries.metadata_source added (TODO-245)

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
    "bobdylan_shows",
    "bobdylan_setlist",
    "setlistfm_shows",
    "setlistfm_setlist",
    "recording_families",
    "tapematch_family_meta",
    "curated_lists",
    "curated_list_entries",
    "taper_confirmations",
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
    "collection_mounts",
    "collection_routes",
    "quality_scans",
    "quality_recording_metrics",
    "quality_recording_scores",
    "entry_lineage",
    "taper_attributions",
    "show_picks",
    "tapematch_pairs",
    "pipeline_file_hash",
    "pipeline_folder_state",
    "song_canonical",
    "song_performances",
    "setlist_fingerprint_suggestions",
    "xref_ingest_filesets",
    "xref_ingest_rows",
    "user_taper_aliases",
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
    "setlistfm_api_key",
})

# Degenerate checksums identify no recording: hashes of zero-byte input, plus
# the all-zero FLAC fingerprint written when STREAMINFO carries no audio MD5.
# The same value appears under many unrelated LB entries (BUG-118 "phantom"
# conflicts: LBs 04994/03029/06748/11900 share the empty-file MD5), so lookup
# treats them as non-evidence in both directions — they neither support a
# match nor count as missing from a set.
_DEGENERATE_CHECKSUMS = frozenset({
    "d41d8cd98f00b204e9800998ecf8427e",           # MD5 of zero-byte input
    "da39a3ee5e6b4b0d3255bfef95601890afd8709d",   # SHA-1 of zero-byte input
})


def _is_degenerate_checksum(checksum: str) -> bool:
    """Return True if this checksum value cannot identify a recording.

    Args:
        checksum: Hex checksum string as stored/parsed (any case).

    Returns:
        True for hashes of empty input and all-zero fingerprints.
    """
    c = (checksum or "").strip().lower()
    return c in _DEGENERATE_CHECKSUMS or (len(c) >= 16 and set(c) == {"0"})

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
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    taper_name TEXT,
    source_chain TEXT,
    lb_category TEXT,
    source_type TEXT,
    metadata_source TEXT
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
    xref         INTEGER NOT NULL DEFAULT 0,
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

-- TODO-223: venue-level gazetteer. One coordinate per DISTINCT (venue, city),
-- solved once so every show/entry at that venue inherits the pin; manual fixes
-- persist per-venue forever (manual_override=1). Seeded unresolved (source=
-- 'seeded', lat/lon NULL) from the concert venues in olof_events/bobdylan_shows/
-- setlistfm_shows; the resolution ladder fills coords in a later pass.
CREATE TABLE IF NOT EXISTS venue_geocoded (
    venue_norm      TEXT NOT NULL,
    city_norm       TEXT NOT NULL,
    venue           TEXT,
    city            TEXT,
    region          TEXT,
    country         TEXT,
    lat             REAL,
    lon             REAL,
    source          TEXT NOT NULL,
    confidence      TEXT,
    manual_override INTEGER NOT NULL DEFAULT 0,
    note            TEXT,
    geocoded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (venue_norm, city_norm)
);
CREATE INDEX IF NOT EXISTS idx_venue_geo_source ON venue_geocoded(source);

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

-- Site-mirror xref checksum ingest staging (TODO-252 / B8): audit trail /
-- provenance only, never a checksums schema change. See backend/xref_ingest.py.
CREATE TABLE IF NOT EXISTS xref_ingest_filesets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    xref         INTEGER NOT NULL,
    source_file  TEXT NOT NULL,
    row_count    INTEGER NOT NULL,
    new_count    INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'staged',
    staged_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at   TIMESTAMP,
    UNIQUE(lb_number, xref)
);
CREATE INDEX IF NOT EXISTS idx_xref_ingest_filesets_status
    ON xref_ingest_filesets(status);

CREATE TABLE IF NOT EXISTS xref_ingest_rows (
    fileset_id INTEGER NOT NULL,
    checksum   TEXT NOT NULL,
    filename   TEXT NOT NULL,
    chk_type   TEXT NOT NULL,
    is_new     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_xref_ingest_rows_fileset
    ON xref_ingest_rows(fileset_id);

-- Curator/install-local overrides on top of backend.db._BUILTIN_TAPER_ALIASES
-- (TODO-241): audit trail / provenance only, USER-tier, never exported (see
-- USER_TABLES). 'add' rows add/override an alias_norm -> canonical mapping;
-- 'remove' rows suppress a builtin alias key so it no longer resolves. See
-- backend.db.reload_taper_aliases, which merges these into the live
-- _KNOWN_TAPER_ALIASES / _TAPER_UNIVERSE globals.
CREATE TABLE IF NOT EXISTS user_taper_aliases (
    alias_norm  TEXT PRIMARY KEY,
    canonical   TEXT NOT NULL,
    action      TEXT NOT NULL CHECK(action IN ('add', 'remove')),
    approved    INTEGER NOT NULL DEFAULT 1,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_user_taper_aliases_action
    ON user_taper_aliases(action, approved);

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
    folder_path    TEXT NOT NULL,
    lb_number      INTEGER NOT NULL,
    linked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note           TEXT,
    xref           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (folder_path, lb_number)
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

-- TapeMatch family clustering, synced from tools/tapematch/observations.db
-- via backend/tapematch_sync.py. See instructions/design_handoff_unified_library/
-- 07-tapematch-backend-integration.md for the design.
CREATE TABLE IF NOT EXISTS recording_families (
    lb_number      INTEGER PRIMARY KEY,
    fam_id         TEXT NOT NULL,
    concert_date   TEXT NOT NULL,
    run_id         TEXT,
    imported_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recording_families_concert_date
    ON recording_families(concert_date);
CREATE INDEX IF NOT EXISTS idx_recording_families_fam_id
    ON recording_families(fam_id);

CREATE TABLE IF NOT EXISTS tapematch_family_meta (
    fam_id          TEXT PRIMARY KEY,
    concert_date    TEXT NOT NULL,
    label           TEXT,
    label_override  TEXT,
    by              TEXT NOT NULL DEFAULT 'ai',
    conf            REAL,
    note            TEXT,
    member_count    INTEGER NOT NULL,
    run_id          TEXT,
    review_flag     INTEGER NOT NULL DEFAULT 0,
    review_reason   TEXT,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

-- curated_lists / curated_list_entries: named curator "best of" lists
-- (e.g. carbonbit, 10haaf) mapping lb_number -> list. See TODO-181.
CREATE TABLE IF NOT EXISTS curated_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    label      TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curated_list_entries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id   INTEGER NOT NULL REFERENCES curated_lists(id),
    lb_number INTEGER NOT NULL,
    note      TEXT NOT NULL DEFAULT '',
    added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(list_id, lb_number)
);
CREATE INDEX IF NOT EXISTS idx_curated_entries_lb ON curated_list_entries(lb_number);
CREATE INDEX IF NOT EXISTS idx_curated_entries_list ON curated_list_entries(list_id);

-- taper_confirmations (MASTER — curator decisions on taper attribution, sticky
-- across recompute). See instructions/complete/FABLE_TAPER_ATTRIBUTION.md + finding F2 in
-- instructions/SPEC_INTEGRATION_NOTES.md: this table (not a `confirmed_at` flag
-- on the derived, USER-tier `taper_attributions` table) is the curated-knowledge
-- surface exported in master data, so an import can never clobber another
-- install's locally-computed propagation. `tools/attribute_tapers.py` reads this
-- table first on every run: 'confirm' rows seed a sticky confirmed-tier
-- attribution; 'reject' rows suppress that (lb_number, taper_normalised) pair
-- from recompute output. Phase 1 ships schema + recompute support only — the
-- confirm/reject curator API lands in Phase 2.
CREATE TABLE IF NOT EXISTS taper_confirmations (
    lb_number         INTEGER PRIMARY KEY,
    taper_normalised  TEXT NOT NULL,
    action            TEXT NOT NULL,      -- 'confirm' / 'reject' (no CHECK; convention only)
    decided_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- bobdylan.com official setlist data
-- bobdylan_shows: one row per concert page on bobdylan.com/date/
--   date_str is YYYY-MM-DD; join to entries/dylan_performances on date_str
CREATE TABLE IF NOT EXISTS bobdylan_shows (
    bobdylan_url  TEXT PRIMARY KEY,
    date_str      TEXT NOT NULL DEFAULT '',
    venue         TEXT NOT NULL DEFAULT '',
    location      TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    scraped_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bobdylan_shows_date ON bobdylan_shows(date_str);

-- bobdylan_setlist: ordered track list for each show
CREATE TABLE IF NOT EXISTS bobdylan_setlist (
    bobdylan_url  TEXT NOT NULL REFERENCES bobdylan_shows(bobdylan_url) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    track_name    TEXT NOT NULL DEFAULT '',
    song_url      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (bobdylan_url, position)
);
CREATE INDEX IF NOT EXISTS idx_bobdylan_setlist_url ON bobdylan_setlist(bobdylan_url);

-- setlist.fm API data
-- setlistfm_shows: one row per setlist, joined to entries/bobdylan_shows via date_str
CREATE TABLE IF NOT EXISTS setlistfm_shows (
    setlistfm_id   TEXT PRIMARY KEY,
    date_str       TEXT NOT NULL DEFAULT '',
    tour_name      TEXT NOT NULL DEFAULT '',
    venue_name     TEXT NOT NULL DEFAULT '',
    city           TEXT NOT NULL DEFAULT '',
    country        TEXT NOT NULL DEFAULT '',
    info           TEXT NOT NULL DEFAULT '',
    setlistfm_url  TEXT NOT NULL DEFAULT '',
    city_lat       REAL,     -- venue.city.coords.lat from the API (TODO-222)
    city_lon       REAL,     -- venue.city.coords.long from the API (TODO-222)
    city_state     TEXT NOT NULL DEFAULT ''  -- venue.city.stateCode from the API (TODO-222)
);
CREATE INDEX IF NOT EXISTS idx_setlistfm_shows_date ON setlistfm_shows(date_str);
CREATE INDEX IF NOT EXISTS idx_setlistfm_shows_tour ON setlistfm_shows(tour_name);

-- setlistfm_setlist: one row per song; (set_index, position) reconstructs full set structure
CREATE TABLE IF NOT EXISTS setlistfm_setlist (
    setlistfm_id  TEXT NOT NULL REFERENCES setlistfm_shows(setlistfm_id) ON DELETE CASCADE,
    set_index     INTEGER NOT NULL,
    set_name      TEXT NOT NULL DEFAULT '',
    is_encore     INTEGER NOT NULL DEFAULT 0,
    position      INTEGER NOT NULL,
    set_position  INTEGER NOT NULL,
    track_name    TEXT NOT NULL DEFAULT '',
    info          TEXT NOT NULL DEFAULT '',
    is_cover      INTEGER NOT NULL DEFAULT 0,
    cover_artist  TEXT NOT NULL DEFAULT '',
    is_tape       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (setlistfm_id, position)
);
CREATE INDEX IF NOT EXISTS idx_setlistfm_setlist_id   ON setlistfm_setlist(setlistfm_id);
CREATE INDEX IF NOT EXISTS idx_setlistfm_setlist_track ON setlistfm_setlist(track_name);

-- Olof Björner mirror bookkeeping (TODO-162, FABLE_OLOF_FILES.md §4)
-- one row per fetched page (crawl bookkeeping, both corpora)
CREATE TABLE IF NOT EXISTS olof_pages (
    filename      TEXT PRIMARY KEY,          -- 'DSN11050 - 1990 Spring Tour of North America.htm'
    url           TEXT NOT NULL DEFAULT '',
    corpus        TEXT NOT NULL DEFAULT '',  -- dsn | chronicle
    segment_title TEXT NOT NULL DEFAULT '',  -- '1990 SPRING TOUR OF NORTH AMERICA' / 'Bob Dylan 2002'
    year          INTEGER,                   -- chronicle pages only
    sha256        TEXT NOT NULL DEFAULT '',
    fetched_at    TEXT NOT NULL DEFAULT '',
    parsed_at     TEXT NOT NULL DEFAULT '',
    parse_status  TEXT NOT NULL DEFAULT '',  -- ok | partial | error:<msg>
    event_count   INTEGER NOT NULL DEFAULT 0
);

-- one row per event; joins to entries/bobdylan_shows/setlistfm_shows via date_str
CREATE TABLE IF NOT EXISTS olof_events (
    event_id        INTEGER PRIMARY KEY,     -- DSN number; appendix shows get year*1000+seq
                                             -- (e.g. 2022017 — no collision, DSN maxes ~5 digits)
    source          TEXT NOT NULL DEFAULT '',-- dsn | chronicle_appendix
    page_filename   TEXT NOT NULL REFERENCES olof_pages(filename),
    event_type      TEXT NOT NULL DEFAULT '',-- concert | session | rehearsal | broadcast | interview | other
    date_str        TEXT NOT NULL DEFAULT '',-- ISO yyyy-mm-dd ('' if unparsed)
    date_raw        TEXT NOT NULL DEFAULT '',
    venue           TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    region          TEXT NOT NULL DEFAULT '',
    country         TEXT NOT NULL DEFAULT '',
    tour_name       TEXT NOT NULL DEFAULT '',-- from DSN segment title / chronicle tour section
    session_title   TEXT NOT NULL DEFAULT '',-- 'The 3rd Blonde On Blonde session, produced by …'
    concert_no_net  INTEGER,                 -- 'Concert # 186 of The Never-Ending Tour'
    concert_no_year INTEGER,                 -- '1990 concert # 16'
    lineup          TEXT NOT NULL DEFAULT '',
    recording_info  TEXT NOT NULL DEFAULT '',-- 'Stereo audience recording, 100 minutes.'
    recording_kind  TEXT NOT NULL DEFAULT '',-- audience | soundboard | studio | broadcast | ''
    recording_mins  INTEGER,
    notes           TEXT NOT NULL DEFAULT '',
    bobtalk         TEXT NOT NULL DEFAULT '',
    releases_raw    TEXT NOT NULL DEFAULT '',
    references_raw  TEXT NOT NULL DEFAULT '',
    updated_raw     TEXT NOT NULL DEFAULT '',-- 'Session info updated 6 February 2001'
    raw_text        TEXT NOT NULL DEFAULT '' -- full block plain text (search + reparse safety net)
);
CREATE INDEX IF NOT EXISTS idx_olof_events_date ON olof_events(date_str);
CREATE INDEX IF NOT EXISTS idx_olof_events_tour ON olof_events(tour_name);

-- one row per performed song / studio take (TODO-162 P3, FABLE_OLOF_FILES.md §4)
CREATE TABLE IF NOT EXISTS olof_songs (
    event_id     INTEGER NOT NULL REFERENCES olof_events(event_id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    song_title   TEXT NOT NULL DEFAULT '',
    credits      TEXT NOT NULL DEFAULT '',   -- cover writer(s) from parens
    is_encore    INTEGER NOT NULL DEFAULT 0,
    take_number  INTEGER,                    -- studio rows only
    take_status  TEXT NOT NULL DEFAULT '',   -- complete | breakdown | rehearsal | false start | incomplete
    annotations  TEXT NOT NULL DEFAULT '',   -- 'acoustic w band', 'harmonica', …
    released_on  TEXT NOT NULL DEFAULT '',   -- release titles resolved from position ranges, '; '-joined
    PRIMARY KEY (event_id, position)
);
CREATE INDEX IF NOT EXISTS idx_olof_songs_title ON olof_songs(song_title);

-- chronicle calendar/diary entries: one row per dated item (TODO-162 P4)
CREATE TABLE IF NOT EXISTS olof_chronicle (
    year         INTEGER NOT NULL,
    seq          INTEGER NOT NULL,           -- order within the year's calendar
    date_str     TEXT NOT NULL DEFAULT '',   -- ISO where the entry has a resolvable date
    date_raw     TEXT NOT NULL DEFAULT '',   -- '31 January'
    entry_text   TEXT NOT NULL DEFAULT '',   -- cleaned paragraph(s), XE/PAGEREF junk stripped
    PRIMARY KEY (year, seq)
);
CREATE INDEX IF NOT EXISTS idx_olof_chronicle_date ON olof_chronicle(date_str);

-- 'New tapes & bootlegs' subsections: circulation provenance per tape (TODO-162 P4)
CREATE TABLE IF NOT EXISTS olof_new_tapes (
    year         INTEGER NOT NULL,           -- chronicle year = when it entered circulation
    seq          INTEGER NOT NULL,
    title        TEXT NOT NULL DEFAULT '',   -- 'Sydney, Australia, 24 February 1986'
    date_str     TEXT NOT NULL DEFAULT '',   -- ISO show date parsed from title, '' if a range/box set
    body_text    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (year, seq)
);
CREATE INDEX IF NOT EXISTS idx_olof_new_tapes_date ON olof_new_tapes(date_str);

-- ── Collection trading tables (USER — never exported in master snapshot) ─────
CREATE TABLE IF NOT EXISTS friend_collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_name TEXT NOT NULL UNIQUE,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lb_count    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friend_collection_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id  INTEGER NOT NULL REFERENCES friend_collections(id) ON DELETE CASCADE,
    lb_number  INTEGER NOT NULL,
    date_str   TEXT,
    location   TEXT,
    lb_status  TEXT,
    UNIQUE(friend_id, lb_number)
);

-- ── Archive.org upload history (USER — never exported in master snapshot) ──────
CREATE TABLE IF NOT EXISTS archive_org_uploads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number       INTEGER NOT NULL,
    identifier      TEXT NOT NULL,
    folder_path     TEXT NOT NULL,
    files_total     INTEGER DEFAULT 0,
    files_uploaded  INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_archive_uploads_lb ON archive_org_uploads(lb_number);
CREATE INDEX IF NOT EXISTS idx_archive_uploads_status ON archive_org_uploads(status, started_at DESC);

-- ── Collection Mounts & Routes (USER — named storage roots + year routing) ────
CREATE TABLE IF NOT EXISTS collection_mounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL UNIQUE,
    root_path  TEXT NOT NULL,
    notes      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_routes (
    year      INTEGER PRIMARY KEY,
    mount_id  INTEGER NOT NULL
              REFERENCES collection_mounts(id) ON DELETE RESTRICT,
    sub_path  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_routes_mount ON collection_routes(mount_id);

-- ── Collection Integrity Monitor (TODO-111) ────────────────────────────────
CREATE TABLE IF NOT EXISTS collection_integrity_status (
    lb_number      INTEGER PRIMARY KEY,
    mount_id       INTEGER REFERENCES collection_mounts(id) ON DELETE SET NULL,
    disk_path      TEXT NOT NULL,
    status         TEXT NOT NULL,
    content_issues INTEGER DEFAULT 0,
    tag_issues     INTEGER DEFAULT 0,
    missing_count  INTEGER DEFAULT 0,
    total_files    INTEGER DEFAULT 0,
    checked_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cistatus_mount ON collection_integrity_status(mount_id, status);

CREATE TABLE IF NOT EXISTS collection_integrity_scans (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    mount_id              INTEGER REFERENCES collection_mounts(id) ON DELETE CASCADE,
    status                TEXT NOT NULL DEFAULT 'running',
    started_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at           TIMESTAMP,
    folders_checked       INTEGER DEFAULT 0,
    folders_pass          INTEGER DEFAULT 0,
    folders_content_issue INTEGER DEFAULT 0,
    folders_tag_issue     INTEGER DEFAULT 0,
    folders_missing       INTEGER DEFAULT 0,
    folders_no_lbdir      INTEGER DEFAULT 0,
    error                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_ciscans_mount ON collection_integrity_scans(mount_id, started_at DESC);

-- ── Concert Ranker (audio quality) — USER-tier derived data ──────────────────
-- Quality data is the user's own analysis of their own copies. RAW aggregated
-- metrics (quality_recording_metrics.metric_json) are stored separately from the
-- derived scores so re-banding/re-ranking never needs an audio rescan.
CREATE TABLE IF NOT EXISTS quality_scans (
    scan_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_json  TEXT,
    notes        TEXT
);
CREATE TABLE IF NOT EXISTS quality_recording_metrics (
    lb_number    INTEGER NOT NULL,
    scan_id      INTEGER NOT NULL,
    source_class TEXT,
    metric_json  TEXT NOT NULL,
    completeness REAL,
    duration_sec REAL,
    scored_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lb_number, scan_id),
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_scan ON quality_recording_metrics(scan_id);
CREATE TABLE IF NOT EXISTS quality_recording_scores (
    lb_number      INTEGER NOT NULL,
    scan_id        INTEGER NOT NULL,
    family_id      INTEGER,
    final_score    REAL,
    rank_in_family INTEGER,
    vetoed         INTEGER DEFAULT 0,
    verdict_text   TEXT,
    PRIMARY KEY (lb_number, scan_id),
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE INDEX IF NOT EXISTS idx_quality_scores_scan ON quality_recording_scores(scan_id);
CREATE INDEX IF NOT EXISTS idx_quality_scores_family ON quality_recording_scores(scan_id, family_id);

-- ── Entry lineage (USER — per-LB parsed lineage signals) ─────────────────────
-- Structured lineage metadata parsed from entries.description for use by the
-- recording-family clustering / learning phase.  Never exported in master data.
CREATE TABLE IF NOT EXISTS entry_lineage (
    lb_number           INTEGER PRIMARY KEY,
    taper_name          TEXT,
    source_chain        TEXT,
    taper_normalised    TEXT,
    mentions_lb         TEXT,   -- JSON: [[lb_number, snippet], ...]
    same_as_lb          TEXT,   -- JSON: [lb_number, ...]
    derived_from_lb     TEXT,   -- JSON: [lb_number, ...]
    better_than_lb      TEXT,   -- JSON: [lb_number, ...]
    parse_confidence    TEXT,   -- 'high' / 'medium' / 'low' / 'none'
    parsed_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_text_hash    TEXT
);
CREATE INDEX IF NOT EXISTS idx_lineage_taper_norm
    ON entry_lineage(taper_normalised)
    WHERE taper_normalised IS NOT NULL;

-- ── Taper attributions (USER — derived per-LB taper designations) ────────────
-- Recomputed wholesale by tools/attribute_tapers.py from entry_lineage /
-- recording_families / taper_confirmations. Never exported in master data —
-- per finding F2 (instructions/SPEC_INTEGRATION_NOTES.md), curator decisions
-- live in the MASTER-tier taper_confirmations table instead, so a master
-- import can never clobber locally-computed propagation. See
-- backend/taper_attribution.py for the evidence_json record shape.
CREATE TABLE IF NOT EXISTS taper_attributions (
    lb_number         INTEGER PRIMARY KEY,
    taper_normalised  TEXT NOT NULL,      -- canonical key into _KNOWN_TAPER_ALIASES values
    confidence        TEXT NOT NULL,      -- 'confirmed' / 'propagated' / 'inferred'
    evidence_json     TEXT NOT NULL,      -- JSON list of evidence records: {kind, detail, ...}
    conflict          INTEGER NOT NULL DEFAULT 0,  -- 1 = contradictory evidence, needs review
    confirmed_at      TIMESTAMP,          -- set only for rows sourced from taper_confirmations
    computed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_taper_attr_name ON taper_attributions(taper_normalised);
CREATE INDEX IF NOT EXISTS idx_taper_attr_conf ON taper_attributions(confidence);

-- ── Show picks (USER — derived per-date "best of" ranking) ───────────────────
-- Recomputed wholesale by tools/compute_show_picks.py (concert_ranker/picks.py)
-- from entries.rating, curated_lists, entry_lineage, quality_recording_scores,
-- and (if present) taper_attributions. Never exported in master data — like
-- quality_recording_scores, this is the user's own derived analysis, rewritten
-- wholesale and never hand-edited. See instructions/FABLE_UNIFIED_RANKING.md
-- §3/§4 for the scoring model and instructions/SPEC_INTEGRATION_NOTES.md
-- finding F3 for the evidence_json record shape.
CREATE TABLE IF NOT EXISTS show_picks (
    concert_date     TEXT NOT NULL,
    lb_number        INTEGER NOT NULL,
    pick_score       REAL NOT NULL,        -- comparable within a date only
    pick_rank        INTEGER NOT NULL,     -- 1 = recommended for the date
    evidence_json    TEXT NOT NULL,        -- ordered list of {kind, detail, points}
    concert_date_iso TEXT,                 -- YYYY-MM-DD, NULL if unparseable/'xx' (LISTENING §9)
    computed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (concert_date, lb_number)
);
CREATE INDEX IF NOT EXISTS idx_show_picks_lb ON show_picks(lb_number);
-- idx_show_picks_date_iso is created by the concert_date_iso migration below
-- (not here): on an existing DB this CREATE TABLE is a no-op, so an index on
-- the new column at this point would run before the ALTER TABLE adds it.

-- ── Song index (LISTENING §3, TODO-230 — song-centric catalog view) ──────────
-- song_canonical is USER-tier but curator-editable: a normalised-alias ->
-- display-spelling table, seeded automatically from olof_songs.song_title
-- norm-groups (most frequent raw spelling wins) and never overwritten by
-- re-seeding once a curator has hand-edited a row (source='curator'). See
-- backend/song_index.py for the normalisation function and seeding logic.
CREATE TABLE IF NOT EXISTS song_canonical (
    alias_norm  TEXT PRIMARY KEY,          -- normalised grouping key
    canonical   TEXT NOT NULL,             -- display spelling shown in the GUI
    source      TEXT NOT NULL DEFAULT 'auto',  -- 'auto' | 'curator'
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- song_performances is a derived, wholesale-recomputed table (like show_picks)
-- built from olof_songs JOIN olof_events — one row per performed song/take.
-- Never exported in master data (in USER_TABLES): it's rebuilt locally from
-- olof_* (itself local-only, not in MASTER_TABLES) on every recompute, never
-- hand-edited. See backend/song_index.py.
CREATE TABLE IF NOT EXISTS song_performances (
    event_id         INTEGER NOT NULL,
    position         INTEGER NOT NULL,
    song_norm        TEXT NOT NULL,
    song_canonical   TEXT NOT NULL,
    concert_date_iso TEXT,                 -- NULL when olof_events.date_str is unparsed
    is_encore        INTEGER NOT NULL DEFAULT 0,
    take_status      TEXT NOT NULL DEFAULT '',
    event_type       TEXT NOT NULL DEFAULT '',
    computed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, position)
);
CREATE INDEX IF NOT EXISTS idx_song_perf_norm ON song_performances(song_norm);
CREATE INDEX IF NOT EXISTS idx_song_perf_date ON song_performances(concert_date_iso);

-- ── Setlist fingerprint suggestions (USER — TODO-225 curator review queue) ───
-- Wholesale-recomputed by backend/setlist_fingerprint.py:run_fingerprint_scan()
-- for entries whose date/location metadata is unusable ('various', empty/xx
-- dates, or a location parked in location_geocoded.source='skipped_not_concert'
-- by the TODO-221 geocoder filter): scores the entry's folder tracklist
-- against every olof_events setlist and keeps the top few candidate shows.
-- Suggestions only — never auto-applied to entries.status; a curator either
-- fixes entries.date_str by hand after reviewing a match, or dismisses a bad
-- suggestion (status='dismissed', preserved across rescans for the same
-- lb_number+event_id pair so a rescan doesn't resurface it).
CREATE TABLE IF NOT EXISTS setlist_fingerprint_suggestions (
    lb_number         INTEGER NOT NULL,
    rank              INTEGER NOT NULL,     -- 1 = best match for this entry
    event_id          INTEGER NOT NULL,
    score             REAL NOT NULL,        -- 0-1, entry_coverage/order/olof_coverage blend
    matched_count     INTEGER NOT NULL,
    entry_song_count  INTEGER NOT NULL,     -- non-blank titles parsed from entries.setlist
    olof_song_count   INTEGER NOT NULL,     -- songs in the candidate event's Olof setlist
    matches_json      TEXT NOT NULL,        -- [{entry_index, position, matched_title}, ...]
    missing_json      TEXT NOT NULL,        -- Olof songs no entry title matched
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending | dismissed
    computed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lb_number, rank)
);
CREATE INDEX IF NOT EXISTS idx_fp_suggest_status ON setlist_fingerprint_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_fp_suggest_event ON setlist_fingerprint_suggestions(event_id);

-- ── TapeMatch pairwise similarity (USER — per-date match % between LBs) ──────
-- Slim per-pair mirror of tools/tapematch/observations.db's `pairs` table,
-- synced via backend/tapematch_sync.py:sync_tapematch_pairs() (same
-- latest-complete-run-per-date rule as recording_families). Wholesale
-- replaced per concert_date on every sync — a row is never a blend of two
-- different tapematch runs. See instructions/FABLE_LISTENING_INSIGHT_IDEAS.md
-- §1. Never exported in master data — like quality/show_picks, this is the
-- user's own derived analysis, rewritten wholesale, never hand-edited.
CREATE TABLE IF NOT EXISTS tapematch_pairs (
    concert_date    TEXT NOT NULL,
    lb_a            INTEGER NOT NULL,     -- always lb_a < lb_b (normalised on sync)
    lb_b            INTEGER NOT NULL,
    corr            REAL,                 -- residual cross-correlation (0-1)
    emb_score       REAL,                 -- pretrained-embedding cosine similarity
    fp_score        REAL,                 -- fingerprint match score
    same_family     INTEGER NOT NULL DEFAULT 0,  -- 1 = tapematch_verdict='same_family'
    similarity_pct  INTEGER,              -- 0-100, or NULL = "not comparable"
    run_id          TEXT,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (concert_date, lb_a, lb_b)
);
CREATE INDEX IF NOT EXISTS idx_tapematch_pairs_date ON tapematch_pairs(concert_date);

-- ── WTRF Torrent Downloads (USER — fetch attempts for missing items) ──────────
CREATE TABLE IF NOT EXISTS wtrf_downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    topic_url    TEXT,
    torrent_path TEXT,
    confidence   TEXT,    -- 'definitive'/'high'/'medium'/'needs_review'/'ambiguous'/'not_found'
    signals_json TEXT,    -- JSON scoring details
    status       TEXT NOT NULL DEFAULT 'pending',  -- 'pending'/'downloaded'/'qbt_added'/'failed'/'skipped'
    error        TEXT,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    qbt_added_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wtrf_downloads_lb
    ON wtrf_downloads(lb_number, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_wtrf_downloads_status
    ON wtrf_downloads(status, attempted_at DESC);

-- Pipeline structural tier (TODO-205): per-file hash cache (P1).
-- PK is (folder_path, rel_path); (size, mtime) are validation columns, not key
-- columns — a read is a hit only when they still match a fresh os.stat, and an
-- in-place edit overwrites the row instead of orphaning it (design doc §2a).
-- sha256 is stored for EVERY file (feeds filing's tree digest); md5/ffp only
-- for the audio subset verify/lbdir need — NULL md5/ffp rows are normal.
CREATE TABLE IF NOT EXISTS pipeline_file_hash (
    folder_path TEXT NOT NULL,      -- absolute, forward-slash normalised
    rel_path    TEXT NOT NULL,      -- posix-style, relative to folder_path
    size        INTEGER NOT NULL,
    mtime       REAL NOT NULL,
    md5         TEXT,
    ffp         TEXT,
    sha256      TEXT,
    hashed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (folder_path, rel_path)
);

-- Pipeline structural tier (TODO-205): per-folder step state (P7).
-- fingerprint is the stat-sweep aggregate over every file (design doc §3 R2 —
-- never the directory's own mtime). Cached verdicts are only valid while the
-- recomputed fingerprint matches. file_json is warm-start display state only:
-- the File step is a live view (P8) and is always re-resolved.
CREATE TABLE IF NOT EXISTS pipeline_folder_state (
    folder_path   TEXT PRIMARY KEY, -- absolute, forward-slash normalised
    fingerprint   TEXT NOT NULL,
    verify_json   TEXT,
    lookup_json   TEXT,
    lbdir_json    TEXT,
    rename_json   TEXT,
    file_json     TEXT,
    steps_json    TEXT,             -- JSON list of step names that have run
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pipeline_state_fp ON pipeline_folder_state(fingerprint);
"""

_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_SHA1_RE = re.compile(r'^([0-9a-fA-F]{40})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)
_AUDIO_EXTS = {'.flac', '.shn', '.wav', '.ape', '.m4a', '.wv', '.aif', '.aiff'}

TRACKED_ENTRY_FIELDS = ("date_str", "location", "cdr", "rating", "timing",
                        "description", "setlist", "status")

# ── Taper / source-chain extractor ────────────────────────────────────────────

_CHAIN_TOKEN = re.compile(
    r'(?:Schoeps|Neumann|Neuman|DPA|B&K|AKG|AT\d|Sennheiser|Sonic\s*Studios|Core\s*Sound|'
    r'CSB|CSHEB|DSM|Sony|Tascam|Zoom|Marantz|Sharp|Roland|M-Audio|Minidisc|'
    r'\bDAT\b|\bSBD\b|\bAUD\b|\bCDR\b|cassette|FLAC|WAV|SHN|EAC|dbPower|TLH|mkwACT|'
    r'Cooledit|CoolEdit|SoundForge|Wavelab|Sound\s*Devices)',
    re.IGNORECASE,
)

def _looks_like_chain(s: str) -> bool:
    return bool(re.search(r'[>\-–]', s)) and bool(_CHAIN_TOKEN.search(s))


def _strip_bt_parens(text: str) -> str:
    """Remove leading (a bittorrent …) / (a close eac match …) blocks."""
    out = text
    for _ in range(8):
        m = re.match(r'^\s*\([^\)]{20,600}\)\s*;?\s*', out, re.DOTALL)
        if m:
            out = out[m.end():]
        else:
            break
    return out


def _normalise_alias_key(text: str | None) -> str:
    """Lowercase + strip punctuation to the exact key form used in
    :data:`_KNOWN_TAPER_ALIASES` (the pre-lookup half of :func:`_normalise_taper`,
    factored out so a curator-entered alias — TODO-241, ``user_taper_aliases`` —
    hashes to the same key that free-text parsing would produce).

    Args:
        text: Raw text (name, handle, or free-text fragment). May be None.

    Returns:
        The normalised key, or '' for falsy/blank input (never None), so
        callers can treat an empty return as "not a valid alias" uniformly.
    """
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_taper_and_source(description: str) -> tuple[str | None, str | None]:
    """Parse free-text description into (taper_name, source_chain).

    Both values may be None when the description carries no recording metadata
    (pure setlist, or only bittorrent-comparison notes).

    Values are kept short: taper_name ≤ 80 chars, source_chain ≤ 160 chars.
    """
    if not description or not description.strip():
        return None, None

    raw = description.strip()
    d   = _strip_bt_parens(raw)
    if not d:
        d = raw
    d600 = d[:600]
    fl   = d.split('\n')[0][:300].strip()

    taper_name: str | None   = None
    source_chain: str | None = None

    # ── 0. Known taper handles — confirmed names, checked before heuristics ─
    m0 = _KNOWN_TAPER_RE.search(d600)
    if m0:
        raw_h = m0.group(1)
        norm_h = _normalise_alias_key(raw_h)
        taper_name = _KNOWN_TAPER_ALIASES.get(norm_h, raw_h)
    if not taper_name:
        m_lt = _LT_TAPER_RE.search(d600)
        if m_lt:
            taper_name = m_lt.group(1).lower()

    # ── 1. Explicit Taper: label (skip inside parentheticals) ────────────
    for m in re.finditer(
        r'\bTaper\s*:\s*(.+?)(?:[,)]\s*(?=(?:Source|Recording|Lineage|Location|Microphone|Recorder)\s*:)|[\n;]|$)',
        d600, re.IGNORECASE,
    ):
        pre = d600[:m.start()]
        if pre.count('(') > pre.count(')'):
            continue  # inside a parenthetical reference block
        # Trim to first comma-separated token
        v = m.group(1).strip().split(',')[0].strip().rstrip(',;.')
        # Strip trailing parenthetical (email addresses, dates, etc.)
        v = re.sub(r'\s*\([^)]{3,}\)\s*$', '', v).strip().rstrip(',;.')
        # If "by <NAME>" is embedded, extract just the name
        by_m = re.search(r'\bby\s+([A-Z][A-Z\s]{2,40})', v)
        if by_m:
            v = by_m.group(1).strip().title()
        _BAD_TAPER = {'unidentified', 'unknown', 'no info', 'n/a', 'none', 'no taper info'}
        if v and len(v) > 1 and v.lower() not in _BAD_TAPER:
            taper_name = v[:80]
        break

    # ── 2. Recording: label (skip inside parentheticals) → source_chain ──
    for m in re.finditer(
        r'\bRecording\s*:\s*(.+?)(?:,\s*Transfer|;\s*Transfer|[\n]|$)',
        d600, re.IGNORECASE,
    ):
        pre = d600[:m.start()]
        if pre.count('(') > pre.count(')'):
            continue
        v = m.group(1).strip().rstrip(',;.')
        if v and len(v) > 2:
            source_chain = v[:160]
        break

    # ── 3. Source: label (skip inside parentheticals) → source_chain ─────
    if not source_chain:
        for m in re.finditer(
            r'\bSource\s*:\s*(.+?)(?:,\s*(?:Lineage|Transfer|Taper)|;\s*|[\n]|$)',
            d600, re.IGNORECASE,
        ):
            pre = d600[:m.start()]
            if pre.count('(') <= pre.count(')'):
                v = m.group(1).strip().rstrip(',;.')
                if v and len(v) > 2:
                    source_chain = v[:160]
                    break

    # ── 4. Lineage: label (skip inside parentheticals) → source_chain ────
    if not source_chain:
        for m in re.finditer(r'\bLineage\s*:\s*(.+?)(?:[\n]|$)', d600, re.IGNORECASE):
            pre = d600[:m.start()]
            if pre.count('(') <= pre.count(')'):
                v = m.group(1).strip().rstrip(',;.')
                if v and len(v) > 2 and _looks_like_chain(v):
                    source_chain = v[:160]
                    break

    # ── 5. Technical Info: label → source_chain ──────────────────────────
    if not source_chain:
        m = re.search(r'\bTechnical\s*Info\s*:\s*(.+?)(?:[;\n]|$)', d600, re.IGNORECASE)
        if m:
            v = m.group(1).strip().rstrip(',;.')
            if v and len(v) > 4 and _looks_like_chain(v):
                source_chain = v[:160]

    # ── 6. BOOTLEG: title → taper_name = 'bootleg'; rip chain → source_chain
    bm = re.match(r'BOOTLEG\s*:\s*(.+?)(?:;|,|\n|$)', fl, re.IGNORECASE)
    if bm:
        taper_name = 'bootleg'
        if not source_chain:
            # Look only in non-paren lines after the first line
            rest_lines = _strip_bt_parens('\n'.join(d.split('\n')[1:]))
            cm = re.search(r'(?:cd|dvd)\s*(?:>|->)\s*(?:EAC|rip|wav|flac)', rest_lines, re.IGNORECASE)
            if cm:
                candidate = rest_lines[cm.start():cm.start() + 120].split('\n')[0].strip()
                if _looks_like_chain(candidate):
                    source_chain = candidate[:160]

    # ── 7. AUD DAT / DAUD → source_chain ─────────────────────────────────
    if not source_chain:
        am = re.match(
            r'\(?((?:AUD\s*DAT[- ]?\d*|DAUD)[- ]?\d*)\)?\s*,?\s*(?:\[.{1,30}\])?\s*,?\s*(.{0,80}?)(?:[,;]|$)',
            fl, re.IGNORECASE,
        )
        if am:
            prefix = am.group(1).strip()
            rest_part = (am.group(2) or '').strip().rstrip(',;.')
            # Only append rest_part if it looks like equipment info, not a rating/quality note
            if rest_part and _looks_like_chain(rest_part):
                source_chain = (prefix + ', ' + rest_part)[:160]
            else:
                source_chain = prefix

    # ── 8. Raw > chain at first line → source_chain ───────────────────────
    if not source_chain:
        m = re.match(r'^(.{4,160}?>+.{4,120}?)(?:[,;]\s*(?!$)|\n|$)', fl)
        if m:
            v = m.group(1).strip().split('(')[0].strip().rstrip(',;.')
            if _looks_like_chain(v):
                source_chain = v[:160]

    # ── 9. legendary / net taper patterns ────────────────────────────────
    if not taper_name:
        m = re.search(
            r'\b(legendary\s+taper\s+[A-Z]|net\s*taper\s*[A-Z#]?\d*)',
            d[:200], re.IGNORECASE,
        )
        if m:
            taper_name = m.group(1).strip()[:60]

    # ── 10. Seeded … by <name> ────────────────────────────────────────────
    if not taper_name:
        m = re.search(r'\bSeeded\s+\S+\s+\S+\s+by\s+([A-Za-z]\w{1,30})', fl, re.IGNORECASE)
        if m:
            taper_name = m.group(1).strip()[:60]

    # ── 11. version "x" → strip prefix, recurse on rest ──────────────────
    if not taper_name and not source_chain:
        vm = re.match(r'^version\s*["\'][^"\']*["\'][,;]?\s*', fl, re.IGNORECASE)
        if vm:
            rest_line = fl[vm.end():].strip()
            rest_full = rest_line + ('\n' + '\n'.join(d.split('\n')[1:6]) if '\n' in d else '')
            t2, s2 = extract_taper_and_source(rest_full)
            taper_name   = taper_name   or t2
            source_chain = source_chain or s2

    # ── 12. taped by <name> ────────────────────────────────────────────────
    # Checked before the leading-token heuristic (below) on purpose: an
    # explicit "Taped ... by <Name>" credit is unambiguous evidence, while the
    # leading token on the line is often equipment (e.g. "akg568ebs, ...") or
    # a second person's handle mentioned in the same breath (e.g. "merman
    # dolphinsmile 48k, Taped by Merman, ... Produced by Dolphinsmile") — if
    # the weak heuristic runs first it claims taper_name and this strong
    # signal never gets checked. The `[\w\s,]{0,40}?` gap allows compound
    # phrasing like "Taped, Transfered and uploaded by Tony Suraci" while
    # still requiring "taped" itself, so a bare "uploaded by <uploader>" (not
    # a taper credit) doesn't match.
    if not taper_name:
        # The capture stops at the first clause boundary — comma/period/
        # newline, or a connector word ("with", "on", "using", "and", "who")
        # — so an equipment/description clause tacked on right after the name
        # ("Taped by BP with Denon portable...") doesn't get swept into the
        # match. "dolphinsmile" is also a stop word: several descriptions
        # literally start "taped by <handle> dolphinsmile, taped by <handle>
        # with ..." (dolphinsmile is the uploader, credited in the same
        # breath), and without the stop the uploader's name gets appended to
        # the taper's.
        m = re.search(
            r"\b(?i:taped)\b[\w\s,]{0,40}?\b(?i:by)\s+(.+?)"
            r"(?:[,.\n>]|\b(?:with|on|using|and|who|dolphinsmile|live|wit)\b|$)",
            fl,
        )
        if m:
            cand = m.group(1).strip()
            # Drop a stray unmatched paren left by the boundary cut (e.g.
            # "...taped by MT)." captures "MT)" since ')' isn't a boundary
            # char — only "(name)" pairs are meant to survive intact).
            if cand.count('(') < cand.count(')'):
                cand = cand.rstrip(')').rstrip()
            elif cand.count(')') < cand.count('('):
                cand = cand.rstrip('(').rstrip()
            words = cand.split()
            # Reject descriptive filler ("a friend of mine", "that team of 3
            # germans", "a friend who lived in Portland") rather than treat
            # it as a name — these are common in this corpus for anonymised
            # tapers and are strictly worse than falling through to the
            # short-handle heuristic below.
            _TAPED_BY_STOPWORDS = {
                'a', 'an', 'the', 'some', 'someone', 'something', 'who', 'that',
                'which', 'with', 'from', 'friend', 'friends', 'buddy', 'dude',
                'guy', 'local', 'team', 'member', 'members', 'teams', 'non',
                'taper', 'tapers', 'dylanist', 'dylanologist', 'crew',
                'recordist', 'mine', 'of', 'on', 'using', 'him', 'her', 'his',
                'my', 'me', 'i', 'think', 'now', 'is', 'was',
            }
            if (cand and cand[0].isalpha() and 0 < len(words) <= 4
                    and not any(w.lower().strip("'.,") in _TAPED_BY_STOPWORDS for w in words)):
                taper_name = cand[:60]

    # ── 13. Short handle / taper code at start ────────────────────────────
    if not taper_name:
        # Allow 1-char second token (e.g. "sbd f", "lta"), semicolon separators
        handle_re = re.compile(
            r'^([A-Za-z][A-Za-z0-9_\-]{0,20}(?:\s+[A-Za-z0-9_\-]{1,15}){0,3})\s*[,;\n]',
        )
        _STOPWORDS = re.compile(
            r'\b(the|and|or|of|in|a|an|is|was|has|have|from|this|that|by|also|'
            r'bittorrent|version|alternate|audience|recorded|received|transfer|upgrade|'
            r'floor|center|centre|section|row|seat|stage|balcony|orchestra|main|front|back|side|'
            r'mono|stereo|sound|poor|good|excellent|fair|hum|hiss|noise|clipping|'
            r'radio|broadcast|special|dylan|bob)\b',
            re.IGNORECASE,
        )
        m = handle_re.match(fl) or handle_re.match(d)
        if m:
            handle = m.group(1).strip()
            if not _STOPWORDS.search(handle) and len(handle) >= 2:
                # Strip trailing sample-rate token (e.g. "24", "48", "48k", "24bit")
                _tok = handle.split()
                if len(_tok) > 1 and re.match(r'^\d+(?:k(?:hz)?|bit)?$', _tok[-1], re.IGNORECASE):
                    _tok = _tok[:-1]
                # If any non-last token contains a digit (equipment model code like skm140,
                # mk4v, at853), the last token is the taper handle
                if len(_tok) > 1 and any(re.search(r'\d', t) for t in _tok[:-1]):
                    _tok = [_tok[-1]]
                taper_name = ' '.join(_tok)[:60]

    # ── 14. from <X> master/vine/collection ──────────────────────────────
    if not taper_name:
        m = re.search(
            r'\bfrom\s+(?:the\s+)?([A-Za-z][A-Za-z0-9\s_\-]{1,25}?(?:\s+(?:master|vine|collection|recording)))',
            fl, re.IGNORECASE,
        )
        if m:
            v = m.group(1).strip()
            # Strip leading articles
            v = re.sub(r'^(?:the|a|an)\s+', '', v, flags=re.IGNORECASE).strip()
            if v and len(v) > 2:
                taper_name = v[:60]

    # ── Post-process ───────────────────────────────────────────────────────

    def _clean(v: str | None) -> str | None:
        if not v:
            return None
        # Strip incomplete opening parenthetical at end (e.g. "George Wang (email...")
        v = re.sub(r'\s*\([^)]*$', '', v).strip()
        # Strip leading or inline stray closing paren before a chain arrow
        v = re.sub(r'^\)+\s*', '', v).strip()
        v = re.sub(r'\)\s*>', '>', v)
        # Strip surrounding quote characters (e.g. "Bach" → Bach)
        v = re.sub(r'^["\'](.+)["\']$', r'\1', v).strip()
        # Discard if contains unmatched quote characters (leaked from quoted strings)
        if v.count('"') % 2 != 0:
            v = re.sub(r'\s*"[^"]*$', '', v).strip()
        return v.rstrip(',;. ') or None

    taper_name   = _clean(taper_name)
    source_chain = _clean(source_chain)

    # Canonicalize, lowercase, and suppress non-taper labels
    if taper_name:
        _norm = _normalise_alias_key(taper_name)
        if _norm in _NOT_TAPER:
            taper_name = None
        else:
            canonical = _KNOWN_TAPER_ALIASES.get(_norm)
            if canonical is None:
                # Prefix match: trim equipment/chain bleed (e.g. "net taper e schoeps …")
                for _key in _KNOWN_TAPER_KEYS_SORTED:
                    if _norm.startswith(_key + ' '):
                        canonical = _KNOWN_TAPER_ALIASES[_key]
                        break
            taper_name = (canonical or taper_name).lower()

    # Strip taper handle prefix from source_chain if chain starts with same text
    if taper_name and source_chain:
        prefix_pat = re.escape(taper_name.split(',')[0].strip())
        source_chain = re.sub(
            r'^' + prefix_pat + r'\s*[,;]\s*', '', source_chain, flags=re.IGNORECASE,
        ).strip().lstrip(',;').strip() or None

    return taper_name or None, source_chain or None


# Conservative keyword classifier, display-only fallback for the GUI source
# badge when the curator-edited entries.source_type is NULL (true for the
# whole catalog as of 2026-06 — see TODO-153). Never written back to the DB;
# recomputed per API response. Deliberately narrow: "Master" is excluded
# because in trader lineage text it almost always means "first-gen copy off
# a master tape" (a generation, not a source type), not an actual studio/
# soundboard master — guessing wrong there would mislabel audience tapes.
# ALD = Assisted Listening Device — a venue's wireless feed for hard-of-hearing
# patrons, tapped with a receiver. Checked first: when a description calls a
# tape both "soundboard" and "ALD" (e.g. "Digitally Remastered Soundboard,
# (assisted listening device (ALD) is the source)"), the ALD note is a
# clarification of the true source, not a second, lower-confidence guess.
_SRC_ALD_RE = re.compile(r'\bald\b', re.IGNORECASE)
_SRC_SBD_RE = re.compile(r'\b(soundboard|sbd)\b', re.IGNORECASE)
_SRC_FM_RE = re.compile(r'\b(pre-?fm|fm\s*(?:broadcast|stereo|simulcast)|radio\s*broadcast)\b', re.IGNORECASE)
# Excludes "Matrix: BDGD" etc — vinyl runout/matrix-number listings, unrelated
# to a SBD+AUD matrix mixdown (caught a real false positive in LB entries
# with "Source: Audience, ... Matrix: BDGD (1-10)" being misread as Mixed).
_SRC_MIXED_RE = re.compile(r'\bmatrix\b(?!\s*[:#]|\s+\d)', re.IGNORECASE)
_SRC_AUD_RE = re.compile(r'\b(audience|aud)\b', re.IGNORECASE)


def _classify_source_text(text: str) -> str | None:
    if _SRC_ALD_RE.search(text):
        return 'ALD'
    if _SRC_SBD_RE.search(text):
        return 'Soundboard'
    if _SRC_FM_RE.search(text):
        return 'FM/Pre-FM'
    if _SRC_MIXED_RE.search(text):
        return 'Mixed'
    if _SRC_AUD_RE.search(text):
        return 'Audience'
    return None


def classify_source_type(description: str | None, source_chain: str | None) -> str | None:
    """Best-effort source-type guess from free-text lineage, for display only.

    Returns one of 'ALD', 'Soundboard', 'FM/Pre-FM', 'Mixed', 'Audience', or
    None when no confident signal is found. Checks `source_chain` first — it's
    already isolated by the Source:/Recording:/Lineage: label extraction in
    :func:`extract_taper_and_source`, so it's far less noisy than the raw
    description (which may mention an unrelated term, e.g. a vinyl release's
    "Matrix: BDGD" runout code, elsewhere in the same entry). Only falls back
    to scanning the full description when source_chain gives no signal.
    """
    if source_chain:
        hit = _classify_source_text(source_chain)
        if hit:
            return hit
    if description:
        return _classify_source_text(description)
    return None


# ── Lineage cross-reference regexes ───────────────────────────────────────────
# Canonical definitions — also imported by tools/tapematch/tapematch_session.py.

_SAME_RE = re.compile(
    r'same\s+(?:recording|source|tape|transfer|as)|'
    r'fingerprints?.{0,40}match|eac\s+match|close\s+eac|'
    r'\bidentical\b|duplicate\s+of',
    re.IGNORECASE,
)
_DERIVED_RE = re.compile(
    r'\bfrom\b.{0,30}\bmaster\b|\bgen\s+of\b|\bcopy\s+of\b|'
    r'\bderived\s+from\b|\bdubbed\s+from\b|\btransferred\s+from\b',
    re.IGNORECASE,
)
_BETTER_RE = re.compile(
    r'\bbetter\s+than\b|\bsupersedes?\b|\bupgrade\s+of\b|\breplaces?\b',
    re.IGNORECASE,
)
_DIFF_RE = re.compile(
    r'different\s+(?:recording|source|tape|from)|'
    r'not\s+the\s+same',
    re.IGNORECASE,
)
_LB_REF_RE = re.compile(r'\bLB-0*(\d+)\b', re.IGNORECASE)
_EXPLICIT_TAPER_LABEL_RE = re.compile(
    r'\bTaper\s*:|\btaped\b[\w\s,]{0,40}?\bby\b', re.IGNORECASE,
)
_SEMI_EXPLICIT_TAPER_RE = re.compile(
    r'\btaped\s+by\b|\bSeeded\b|\bBOOTLEG\s*:|'
    r'\blegendary\s+taper\b|\bnet\s*taper\b',
    re.IGNORECASE,
)

# Curated known tapers: maps every normalised variant → canonical display name.
# All canonical values are lowercase; taper_name is always stored lowercase.
# Add new tapers here. This is the code-only builtin table; TODO-241 adds a
# `user_taper_aliases` table for install-local additions/suppressions on top
# of it without a code edit — see _KNOWN_TAPER_ALIASES and reload_taper_aliases
# below.
_BUILTIN_TAPER_ALIASES: dict[str, str] = {
    "soomlos": "soomlos",
    "spot": "spot",
    "hide": "hide",
    "lta": "lta",
    "mk": "mk",
    "southside butcher": "southside butcher",
    "southsidebutcher": "southside butcher",
    "ssb": "southside butcher",
    "iar": "iar",
    "improved air remaster": "iar",
    "mjs": "mjs",
    "bw": "bw",
    "jtt": "jtt",
    "pl": "pl",
    "cedar": "cedar",
    "holy grail": "holy grail",
    "holygrail": "holy grail",
    "vw": "vw",
    "cck": "cck",
    "jt": "jt",
    "cta": "cta",
    "tyrus": "tyrus",
    "zimmy21": "zimmy21",
    "fine wine": "fine wine",
    "finewine": "fine wine",
    "hv": "hv",
    "condor": "condor",
    "lowgen": "lowgen",
    "schubert": "schubert",
    "mb": "mb",
    "jersey john": "jersey john",
    "jerseyjohn": "jersey john",
    "theodore": "theodore",
    "mike savage": "mike savage",
    "mikesavage": "mike savage",
    "m&a": "m&a",   # raw form — matched by regex against description text
    "m a": "m&a",   # normalised form (& strips to space)
    "wario": "wario",
    "mani": "mani",
    "manie": "mani",
    "bach": "bach",
    "romeo": "romeo",
    # cb is the taper; "cb master" just means a master tape *from* cb — the
    # "master" is a source descriptor, not part of the handle (TODO-213, 2026-07-13).
    "cb master": "cb",
    "cb": "cb",
    "lk": "lk",
    "hhtfp": "hhtfp",
    "jf": "jf",
    "sullylove": "sullylove",
    "ebr": "ebr",
    "tom moore": "tom moore",
    "dk-wi": "dk-wi",
    "dk wi": "dk-wi",
    "tk": "tk",
    "bt": "bt",
    "vito": "vito",
    "glen dundas": "glen dundas",
    "glendundas": "glen dundas",
    "nightly moth": "nightly moth",
    "nightlymoth": "nightly moth",
    "csheb": "csheb",
    "streetcar visions": "streetcar visions",
    "streetcarvisions": "streetcar visions",
    "sk": "sk",
    "jerseyboy": "jerseyboy",
    "jersey boy": "jerseyboy",
    "spyder9": "spyder9",
    "bob meyer": "bob meyer",
    "bobmeyer": "bob meyer",
    "markp": "markp",
    "mark p": "markp",
    "downfromtheglen": "downfromtheglen",
    "down from the glen": "downfromtheglen",
    "mrsoul": "mrsoul",
    "mr soul": "mrsoul",
    "sh": "sh",
    "sm": "sm",
    "gs": "gs",
    "rcm": "rcm",
    "mike millard": "mike millard",
    "mikemillard": "mike millard",
    "mm": "mike millard",
    "billie": "billie",
    "jgb": "jgb",
    "tompaine56": "tom paine",
    "tom paine 56": "tom paine",
    "tom paine": "tom paine",
    "tp": "tom paine",
    "mango farmer": "mango farmer",
    "mangofamer": "mango farmer",
    "ironchef": "ironchef",
    "iron chef": "ironchef",
    "soledriver": "soledriver",
    "sole driver": "soledriver",
    "goodnitesteve": "goodnitesteve",
    "goodnite steve": "goodnitesteve",
    "clapberry": "clapberry",
    "bigjim": "bigjim",
    "big jim": "bigjim",
    "teddy ballgame": "teddy ballgame",
    "teddyballgame": "teddy ballgame",
    "theshadow": "theshadow",
    "the shadow": "theshadow",
    # "robert" removed 2026-07-13 (TODO-213): too generic a bare token — it
    # matched songwriter/personnel credits ("Robert Hunter", "Robert Friemark")
    # in setlists, not tapers. 179 of its 198 attributions were false mentions.
    "sfy": "sfy",
    "caretaker": "caretaker",
    "beer": "beer",
    "beerly": "beer",
    "mikebeerly": "beer",
    "mike beerly": "beer",
    "caspar": "caspar",
    "jon caspar": "caspar",
    "joncaspar": "caspar",
    "kuddukan": "kuddukan",
    "pdub": "pdub",
    "audiowhore": "audiowhore",
    "arashi": "arashi",
    "dopersan": "dopersan",
    "markitospb": "markitospb",
    "krw_co": "krw co",   # raw form (underscore) for regex match
    "krw co": "krw co",   # normalised form (underscore → space)
    "maloney": "maloney",
    "radioshack": "radioshack",
    "radio shack": "radioshack",
    "kingrue": "kingrue",
    "king rue": "kingrue",
    "warburton": "warburton",
    "jimmy warburton": "warburton",
    "jimmywarburton": "warburton",
    "captain acid": "captain acid",
    "captainacid": "captain acid",
    "acidproject": "captain acid",
    "acid project": "captain acid",
    "andrea82": "andrea82",
    "pike1957": "pike1957",
    "sway": "sway",
    "whofan70": "whofan70",
    "two of us": "two of us",
    "twofus": "two of us",
    "mcforce": "mcforce",
    "thelonius": "thelonius",
    "thelonious": "thelonius",
    "jems": "jems",
    "tarantula": "tarantula",
    "lbp51": "lbp51",
    "unwanted man music": "unwanted man music",
    "unwanted man": "unwanted man music",
    "uww": "unwanted man music",
    "travelin man records": "travelin man records",
    "travelin man": "travelin man records",
    "tmr": "travelin man records",
    "stevemtl": "stevemtl",
    "bourbon": "bobby bourbon",
    "bobby bourbon": "bobby bourbon",
    "bobbybourboon": "bobby bourbon",
    "elliot": "elliot",
    "jvs": "jvs",
    "v4tx": "v4tx",
    # ── Legendary Taper series (LTA, LTB, … distinct from Net Taper series) ──
    # "legendary taper X", "taper X", "lt X", "ltX" all → "lt[a-z]"
    **{f"legendary taper {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"taper {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"lt {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    # ── Net Taper series (NTA, NTB, … distinct from Legendary Taper series) ──
    # "net taper X", "ntX" all → "net taper [a-z]"
    **{f"net taper {c}": f"net taper {c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"nt{c}": f"net taper {c}" for c in "abcdefghijklmnopqrstuvwxyz"},
}

# Live, merged alias table: builtin plus approved `user_taper_aliases` rows
# (TODO-241). Starts as a copy of the builtin table; reload_taper_aliases()
# rebuilds it IN PLACE (.clear() + .update()) rather than reassigning, so every
# module that imported this name directly (backend.taper_attribution,
# backend.taper_fingerprints) sees the update through the same dict object —
# no re-import or process restart needed.
_KNOWN_TAPER_ALIASES: dict[str, str] = dict(_BUILTIN_TAPER_ALIASES)

# Labels that must never be stored as taper_name (mis-parses / source-type labels).
_NOT_TAPER: frozenset[str] = frozenset({
    # dolphinsmile curates/transfers others' tapes — not a taper (curator, 2026-07-04);
    # common misspellings in entry text included
    'dolphinsmile', 'dolphinmile', 'dolphindmile', 'dolphinsme', 'dolphin',
    # Not tapers: lk curates, captain acid remasters existing recordings, and
    # jtt transfers/masters others' tapes ("Mastered to Digital by JTT",
    # "Transfer from Low Generation Cassette JTT" — not generally a taper).
    # TODO-213 curation pass, 2026-07-13. Kept as _KNOWN_TAPER_ALIASES keys so
    # the parser still collapses their spellings to one canonical token, but
    # excluded here so the attribution engine never seeds them as candidates:
    # when such a mention collides with a real taper in a family (e.g. LB-1945 =
    # ltd via LB-4396 vs captain acid via LB-4401), the real taper propagates
    # cleanly with no conflict — no curation required.
    'lk', 'captain acid', 'jtt',
    'sbd', 'aud', 'master', 'series', 'incomplete',
    'aud master', 'master aud', 'excellent sound', 'net tapers',
    'km140s', 'km140',
    'unidentified taper', 'dat master', 'same master',
    'soundcheck', 'low gen reel', 'sp cmc',
    'very good sound', 'same recording', 'not certain',
    'cos11pt', 'zoom h2',
    'late show', 'early show', 'unknown source',
    'poor sound', 'mono',
})

# Whitelist of validated taper names (locked decision, mirrors
# taper_attribution._TAPER_UNIVERSE): canonical values of _KNOWN_TAPER_ALIASES,
# excluding anything in _NOT_TAPER. Free-text parsing (extract_taper_and_source)
# can still store an unrecognised guess in taper_name for curator review (see
# ScreenSearch's scrape-preview use), but any *display* surface aimed at end
# users (e.g. the Library grid's taper pill) must check is_known_taper() first
# so it never shows a guess the attribution engine itself would reject.
_TAPER_UNIVERSE: frozenset[str] = frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER


def is_known_taper(name: str | None) -> bool:
    """Return True if ``name`` normalises to a curated, validated taper.

    Args:
        name: Raw or already-normalised taper name (may be None).

    Returns:
        True if the normalised form is a member of ``_TAPER_UNIVERSE``.
    """
    norm = _normalise_taper(name)
    return norm is not None and norm in _TAPER_UNIVERSE

# Sorted known-taper keys longest-first for prefix-match canonicalization.
_KNOWN_TAPER_KEYS_SORTED: list[str] = sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)

# Compiled regex for step-0 known-handle scan in extract_taper_and_source.
# Sorted longest-first so multi-word phrases match before shorter subsets.
_KNOWN_TAPER_RE = re.compile(
    r'\b(' + '|'.join(
        re.escape(k) for k in sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
    ) + r')\b',
    re.IGNORECASE,
)

# Legendary taper series: LTA, LTB, LTC … matched as a pattern rather than
# enumerating all letters.  Canonical form is lowercase (e.g. "ltb").
_LT_TAPER_RE = re.compile(r'\b(lt[a-z])\b', re.IGNORECASE)


def _normalise_taper(name: str | None) -> str | None:
    """Lowercase, strip punctuation, and resolve known-taper aliases.

    Args:
        name: Raw taper name, e.g. "J. Smith" or "john_smith-taper".

    Returns:
        Canonical normalised string (e.g. "southside butcher"), or None.
    """
    s = _normalise_alias_key(name)
    if not s:
        return None
    return _KNOWN_TAPER_ALIASES.get(s, s)


# ── User taper aliases (TODO-241): add/remove known-taper handles without a
# code edit. `user_taper_aliases` is USER-tier (audit/provenance only, never
# exported — see USER_TABLES); 'add' rows create or override an alias key,
# 'remove' rows suppress a _BUILTIN_TAPER_ALIASES key. reload_taper_aliases()
# is the single place that turns those rows into the live _KNOWN_TAPER_ALIASES
# / _TAPER_UNIVERSE / _KNOWN_TAPER_KEYS_SORTED / _KNOWN_TAPER_RE globals used
# by parsing and attribution.

def _run_alias_write(fn, db_path: str | None):
    """Route a user_taper_aliases write through the write queue, matching the
    BUG-246 guard used elsewhere (taper_attribution.py, song_index.py,
    xref_ingest.py): the write queue singleton is first-caller-wins, so under
    pytest (each test module's own temp DB) it may be bound to a different DB
    than *db_path*.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        logger.warning(
            "user_taper_aliases: write queue bound to %s but this write targets %s"
            " — writing directly", queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def reload_taper_aliases(db_path: str | None = None) -> dict:
    """Rebuild the merged known-taper alias tables from user overrides.

    Reads approved rows from ``user_taper_aliases`` and rebuilds
    :data:`_KNOWN_TAPER_ALIASES` **in place** (``.clear()`` + ``.update()``) so
    every module holding a reference to that same dict object (e.g.
    ``backend.taper_attribution``, ``backend.taper_fingerprints``, both of
    which import it by name) sees the update without being reloaded.
    :data:`_TAPER_UNIVERSE`, :data:`_KNOWN_TAPER_KEYS_SORTED`, and
    :data:`_KNOWN_TAPER_RE` are all derived, and a frozenset/list/compiled
    regex can't be mutated in place, so they are reassigned here instead — any
    consumer that needs a reload to propagate must access them as module
    attributes (``db._TAPER_UNIVERSE``) rather than importing the name
    directly at its own top level (see ``taper_attribution``'s module-level
    ``__getattr__`` for the one existing direct-import consumer).

    Apply order per alias key: start from the builtin table, apply every
    approved 'remove' row (deletes that key if present), then apply every
    approved 'add' row (sets/overrides that key) — so 'add' always wins for a
    given ``alias_norm`` (moot in practice: the table's PRIMARY KEY means one
    ``alias_norm`` can only ever hold one row/action at a time).

    Args:
        db_path: Optional database path override.

    Returns:
        Counts dict: ``{"builtin", "user_add", "user_remove", "merged"}``.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT alias_norm, canonical, action FROM user_taper_aliases WHERE approved = 1"
    ).fetchall()
    removes = [r for r in rows if r["action"] == "remove"]
    adds = [r for r in rows if r["action"] == "add"]

    _KNOWN_TAPER_ALIASES.clear()
    _KNOWN_TAPER_ALIASES.update(_BUILTIN_TAPER_ALIASES)
    for r in removes:
        _KNOWN_TAPER_ALIASES.pop(r["alias_norm"], None)
    for r in adds:
        _KNOWN_TAPER_ALIASES[r["alias_norm"]] = r["canonical"]

    global _TAPER_UNIVERSE, _KNOWN_TAPER_KEYS_SORTED, _KNOWN_TAPER_RE
    _TAPER_UNIVERSE = frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER
    _KNOWN_TAPER_KEYS_SORTED = sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
    _KNOWN_TAPER_RE = re.compile(
        r'\b(' + '|'.join(
            re.escape(k) for k in sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
        ) + r')\b',
        re.IGNORECASE,
    )

    counts = {
        "builtin": len(_BUILTIN_TAPER_ALIASES),
        "user_add": len(adds),
        "user_remove": len(removes),
        "merged": len(_KNOWN_TAPER_ALIASES),
    }
    logger.info(
        "reload_taper_aliases: builtin=%(builtin)d user_add=%(user_add)d "
        "user_remove=%(user_remove)d merged=%(merged)d", counts,
    )
    return counts


def list_taper_aliases(db_path: str | None = None) -> dict:
    """Merged known-taper alias listing with builtin/user provenance.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{"entries": [{"alias", "canonical", "origin": "builtin"|"user"}, ...]
        (alias-sorted), "suppressed": [alias_norm, ...] (builtin keys removed
        by an approved user 'remove' row), "counts": {...}}`` — see
        :func:`reload_taper_aliases` for the counts shape.

    Reloads the merged tables first so a listing (and the counts it reports)
    always reflects the DB — user_taper_aliases can be edited out-of-band by
    tools/taper_aliases.py while a backend process is running, and without the
    reload this process's in-memory merge would be stale.
    """
    reload_taper_aliases(db_path)
    conn = get_connection(db_path)
    user_rows = conn.execute(
        "SELECT alias_norm, canonical, action, approved FROM user_taper_aliases"
    ).fetchall()
    user_add = {r["alias_norm"]: r["canonical"] for r in user_rows
                if r["action"] == "add" and r["approved"]}
    user_remove = {r["alias_norm"] for r in user_rows
                   if r["action"] == "remove" and r["approved"]}

    entries = [
        {"alias": alias, "canonical": canonical, "origin": "builtin"}
        for alias, canonical in _BUILTIN_TAPER_ALIASES.items()
        if alias not in user_remove
    ]
    entries.extend(
        {"alias": alias, "canonical": canonical, "origin": "user"}
        for alias, canonical in user_add.items()
    )
    entries.sort(key=lambda e: e["alias"])

    return {
        "entries": entries,
        "suppressed": sorted(user_remove),
        "counts": {
            "builtin": len(_BUILTIN_TAPER_ALIASES),
            "user_add": len(user_add),
            "user_remove": len(user_remove),
            "merged": len(_KNOWN_TAPER_ALIASES),
        },
    }


def add_taper_alias(alias: str, canonical: str, note: str | None = None,
                     db_path: str | None = None) -> dict:
    """Upsert a user 'add' alias override, then reload the merged tables.

    Args:
        alias: Raw or already-normalised alias text. Normalised the same way
            :func:`_normalise_taper` keys are (lowercase, punctuation-stripped)
            — NOT resolved against the existing alias table, since that's
            exactly the mapping being created/overridden here.
        canonical: Canonical taper name to store (lowercased). Not validated
            against the existing universe — a curator may be introducing a
            brand-new taper the alias is the first handle for.
        note: Optional free-text provenance note.
        db_path: Optional database path override.

    Returns:
        The stored ``user_taper_aliases`` row as a dict.

    Raises:
        ValueError: alias or canonical is missing/blank, or alias normalises
            to the empty string.
    """
    alias_norm = _normalise_alias_key(alias)
    canonical_norm = (canonical or "").strip().lower()
    if not alias_norm or not canonical_norm:
        raise ValueError("alias and canonical must be non-empty")

    init_db(db_path)

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO user_taper_aliases
                   (alias_norm, canonical, action, approved, note, created_at, updated_at)
               VALUES (?, ?, 'add', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(alias_norm) DO UPDATE SET
                   canonical  = excluded.canonical,
                   action     = 'add',
                   approved   = 1,
                   note       = excluded.note,
                   updated_at = CURRENT_TIMESTAMP""",
            (alias_norm, canonical_norm, note),
        )

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    row = get_connection(db_path).execute(
        "SELECT * FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,)
    ).fetchone()
    return dict(row)


def remove_taper_alias(alias: str, db_path: str | None = None) -> str:
    """Remove or suppress a known-taper alias, then reload the merged tables.

    If *alias* is a live user 'add' row, the row is deleted outright (the
    builtin table is untouched, since the alias never existed there). If
    *alias* is a builtin key, an 'remove' row is upserted to suppress it
    locally (the builtin table itself is code, never edited).

    Args:
        alias: Raw or already-normalised alias text.
        db_path: Optional database path override.

    Returns:
        ``"deleted"`` if a user 'add' row was removed, ``"suppressed"`` if a
        builtin key was newly suppressed.

    Raises:
        KeyError: *alias* is neither a user 'add' row nor a builtin key.
    """
    alias_norm = _normalise_alias_key(alias)
    init_db(db_path)
    conn = get_connection(db_path)

    existing = conn.execute(
        "SELECT action FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,)
    ).fetchone()

    if existing is not None and existing["action"] == "add":
        def _do(c: sqlite3.Connection) -> None:
            c.execute("DELETE FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,))
        _run_alias_write(_do, db_path)
        reload_taper_aliases(db_path)
        return "deleted"

    if alias_norm in _BUILTIN_TAPER_ALIASES:
        canonical = _BUILTIN_TAPER_ALIASES[alias_norm]

        def _do(c: sqlite3.Connection) -> None:
            c.execute(
                """INSERT INTO user_taper_aliases
                       (alias_norm, canonical, action, approved, note, created_at, updated_at)
                   VALUES (?, ?, 'remove', 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                   ON CONFLICT(alias_norm) DO UPDATE SET
                       canonical  = excluded.canonical,
                       action     = 'remove',
                       approved   = 1,
                       updated_at = CURRENT_TIMESTAMP""",
                (alias_norm, canonical),
            )
        _run_alias_write(_do, db_path)
        reload_taper_aliases(db_path)
        return "suppressed"

    raise KeyError(alias_norm)


def _compute_parse_confidence(
    description: str, taper_name: str | None, source_chain: str | None
) -> str:
    """Compute parse_confidence label for an entry_lineage row.

    Args:
        description: Raw entry description text.
        taper_name:  Parsed taper name (may be None).
        source_chain: Parsed source chain (may be None).

    Returns:
        One of 'high', 'medium', 'low', 'none'.
    """
    if not taper_name and not source_chain:
        return 'none'
    d600 = description[:600]
    has_taper_label = bool(_EXPLICIT_TAPER_LABEL_RE.search(d600))
    if has_taper_label and taper_name and source_chain:
        return 'high'
    if taper_name and source_chain:
        return 'medium'
    if taper_name and not source_chain and not has_taper_label:
        if not _SEMI_EXPLICIT_TAPER_RE.search(d600):
            return 'low'
    return 'medium'


def extract_lb_references(description: str) -> dict:
    """Parse description for LB number cross-references and classify relationships.

    Returns dict with keys:
        mentions_lb:      list of [lb_number: int, snippet: str] — all LB refs found
        same_as_lb:       list of int — LB numbers claimed as same source
        derived_from_lb:  list of int — LB numbers this was derived from
        better_than_lb:   list of int — LB numbers this supersedes/upgrades

    Classification uses a ±200 char context window around each LB-N mention.
    A single LB number may appear in multiple output lists when multiple
    relationship patterns match its context. Snippet is 200 chars centred on
    the match. `_DIFF_RE` matches are not stored; contradictory same+diff context
    stores in same_as_lb only when same_count >= diff_count in that window.
    """
    mentions: list[list] = []
    same_as: list[int] = []
    derived_from: list[int] = []
    better_than: list[int] = []

    for m in _LB_REF_RE.finditer(description):
        lb_num = int(m.group(1))

        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(description), m.end() + 200)
        ctx = description[ctx_start:ctx_end]

        mid = (m.start() + m.end()) // 2
        snip_start = max(0, mid - 100)
        snip_end = min(len(description), mid + 100)
        snippet = description[snip_start:snip_end]

        mentions.append([lb_num, snippet])

        same_count = len(_SAME_RE.findall(ctx))
        diff_count = len(_DIFF_RE.findall(ctx))

        if same_count > 0 and same_count >= diff_count:
            if lb_num not in same_as:
                same_as.append(lb_num)
        if _DERIVED_RE.search(ctx) and lb_num not in derived_from:
            derived_from.append(lb_num)
        if _BETTER_RE.search(ctx) and lb_num not in better_than:
            better_than.append(lb_num)

    return {
        "mentions_lb": mentions,
        "same_as_lb": same_as,
        "derived_from_lb": derived_from,
        "better_than_lb": better_than,
    }


def upsert_entry_lineage(row: dict, db_path=None) -> None:
    """Insert or replace an entry_lineage row via the write queue.

    Args:
        row: Dict with keys matching entry_lineage columns (JSON fields as strings).
        db_path: Optional database path override.
    """
    _row = row
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT OR REPLACE INTO entry_lineage
               (lb_number, taper_name, source_chain, taper_normalised,
                mentions_lb, same_as_lb, derived_from_lb, better_than_lb,
                parse_confidence, parsed_at, source_text_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)""",
            (
                _row["lb_number"], _row["taper_name"], _row["source_chain"],
                _row["taper_normalised"], _row["mentions_lb"], _row["same_as_lb"],
                _row["derived_from_lb"], _row["better_than_lb"],
                _row["parse_confidence"], _row["source_text_hash"],
            ),
        )
    )


def get_lineage(lb_number: int, db_path=None) -> dict | None:
    """Return the entry_lineage row for an LB number, or None if not parsed yet.

    Args:
        lb_number: LosslessBob entry number.
        db_path:   Optional database path override.

    Returns:
        Dict of column → value, or None.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM entry_lineage WHERE lb_number = ?", (lb_number,)
    ).fetchone()
    return dict(row) if row else None


# ── Track-listing patterns used by extract_setlist_from_description ──────────

_SL_DOT = re.compile(r'\b0?\d{1,2}[.)]\s')                                 # "1. " / "01." / "1) "
_SL_NUM = re.compile(r'(?:^|,\s*)(\d{1,2})\s+[A-Z*\"]', re.MULTILINE)     # "1 Song" num-only


def extract_setlist_from_description(description: str) -> str:
    """Extract track-listing paragraphs from a description string.

    Paragraphs containing ≥ 3 numbered track markers are considered setlists.
    Returns a joined string for the ``setlist`` DB column.  The description
    itself is not modified.
    """
    if not description:
        return ""
    setlist_paras: list[str] = []
    for para in description.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(_SL_DOT.findall(para)) >= 3:
            setlist_paras.append(para)
            continue
        nums = _SL_NUM.findall(para)
        if len(nums) >= 3 and min(int(n) for n in nums) <= 2:
            setlist_paras.append(para)
    return "\n\n".join(setlist_paras)


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
    global _bloom, _bloom_db_path
    bf = _SBF(mode=_SBF.LARGE_SET_GROWTH, error_rate=0.01)
    conn = get_connection(db_path)
    for row in conn.execute("SELECT checksum FROM checksums"):
        bf.add(row[0])
    with _bloom_lock:
        _bloom = bf
        _bloom_db_path = str(db_path or DB_PATH)


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
        # Migration: add mount_id to integrity_events (TODO-111)
        _ie_cols = [r[1] for r in conn.execute("PRAGMA table_info(integrity_events)").fetchall()]
        if "mount_id" not in _ie_cols:
            conn.execute("ALTER TABLE integrity_events ADD COLUMN mount_id INTEGER")
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

    # Bloom pre-filter: separate definite misses from candidates (DB-07).
    # Only use the bloom if it was built for this exact db_path; a filter built
    # from a different DB (common in tests with multiple temp DBs) would give
    # false negatives, silently dropping valid checksums (BUG-187).
    active_path = str(db_path or DB_PATH)
    with _bloom_lock:
        _active_bloom = _bloom if _bloom_db_path == active_path else None
    if _active_bloom is not None:
        candidates = [e for e in parsed_entries if e[0] in _active_bloom]
        definite_misses = [e for e in parsed_entries if e[0] not in _active_bloom]
    else:
        candidates = list(parsed_entries)
        definite_misses = []
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
                   e.description, e.status, lm.lb_status, lm.public_no_checksums,
                   e.taper_name, e.source_chain, e.lb_category, e.source_type
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
                   e.description, e.status, lm.lb_status, lm.public_no_checksums,
                   e.taper_name, e.source_chain, e.lb_category, e.source_type
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
            " e.description, e.status, lm.lb_status, lm.public_no_checksums,"
            " e.taper_name, e.source_chain, e.lb_category, e.source_type"
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
                    " e.description, e.status, lm.lb_status, lm.public_no_checksums,"
                    " e.taper_name, e.source_chain, e.lb_category, e.source_type"
                    " FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
                    " WHERE e.lb_number = ?",
                    (lb_id,),
                ).fetchone()
                if direct:
                    results.insert(0, dict(direct))
        except ValueError:
            pass

    for r in results:
        if not r.get("source_type"):
            r["source_type"] = classify_source_type(r.get("description"), r.get("source_chain"))
        # taper_known lets consumers distinguish a curated taper (display-worthy,
        # e.g. Library grid pill) from an unvalidated free-text guess (still
        # shown raw in the scrape-preview screen, but not as an authoritative badge).
        r["taper_known"] = is_known_taper(r.get("taper_name"))

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
        f" e.description, e.status, lm.lb_status, lm.public_no_checksums,"
        f" e.taper_name, e.source_chain, e.lb_category, e.source_type"
        f" FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
        f" WHERE e.lb_number IN ({placeholders})"
        f" ORDER BY e.lb_number",
        [int(n) for n in lb_numbers],
    ).fetchall()
    return [dict(r) for r in rows]


def _year_from_date_str(date_str: str) -> int:
    """Extract a year from entries.date_str (M/D/YY, possibly 'xx' for M/D).

    Mirrors gui_next's extractYear() so server- and client-derived years
    never disagree for the same row.
    """
    if not date_str:
        return 0
    parts = date_str.split("/")
    if len(parts) < 3:
        return 0
    try:
        n = int(parts[-1].strip())
    except ValueError:
        return 0
    if n < 100:
        return 1900 + n if n >= 49 else 2000 + n
    return n


_STATUS_RANK: dict[str, int] = {"public": 0, "private": 1, "missing": 2}
_STATUS_LABEL: dict[str, str] = {"public": "Public", "private": "Private", "missing": "Missing"}


# ── Library payload extension (FABLE_UNIFIED_RANKING phase 3) ───────────────
# Per instructions/SPEC_INTEGRATION_NOTES.md finding F4, ranking phase 3
# defines the payload-extension pattern for get_performances(): flat fields
# merged onto each recording, no N+1 calls — taper phase 2 follows the same
# pattern for confirmed-taper. All three helpers below feature-detect their
# source table/column so a fresh install (or one that hasn't run a Concert
# Ranker scan yet) degrades to "no extra fields" instead of erroring.

def _load_pick_ranks(conn: sqlite3.Connection) -> dict[int, int]:
    """Return ``{lb_number: pick_rank}`` from ``show_picks``.

    Empty on a fresh install (pre ``POST /api/derived/recompute``) — the
    table always exists (``USER_TABLES``/``SCHEMA_SQL``) but starts empty.
    """
    rows = conn.execute("SELECT lb_number, pick_rank FROM show_picks").fetchall()
    return {r["lb_number"]: r["pick_rank"] for r in rows}


def _load_curated_by_lb(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Return ``{lb_number: [curated_list_name, ...]}`` from curated lists.

    A recording can appear in more than one curator's list (e.g. carbonbit
    and 10haaf agreeing), so the value is always a list.
    """
    rows = conn.execute(
        "SELECT cl.name AS name, ce.lb_number AS lb_number"
        " FROM curated_list_entries ce JOIN curated_lists cl ON cl.id = ce.list_id"
    ).fetchall()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["lb_number"], []).append(r["name"])
    return out


def _load_latest_abs_grades(conn: sqlite3.Connection) -> dict[int, str]:
    """Return ``{lb_number: abs_grade}`` from the most recent scan.

    Mirrors ``concert_ranker/picks.py:_load_latest_quality`` — the newest
    scan is the one that actually wrote ``quality_recording_scores`` rows
    (``quality_scans`` also includes small calibration-only runs), and
    ``abs_grade`` is feature-detected via ``PRAGMA table_info`` because it's
    added by ``concert_ranker/lb/repo.py``'s ``ensure_schema`` migration, not
    this module's ``SCHEMA_SQL``, so a DB that has never been scanned via
    Concert Ranker doesn't have the column yet.
    """
    scan_row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_recording_scores").fetchone()
    scan_id = scan_row["m"] if scan_row else None
    if scan_id is None:
        return {}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    if "abs_grade" not in cols:
        return {}
    rows = conn.execute(
        "SELECT lb_number, abs_grade FROM quality_recording_scores"
        " WHERE scan_id=? AND abs_grade IS NOT NULL",
        (scan_id,),
    ).fetchall()
    return {r["lb_number"]: r["abs_grade"] for r in rows}


def _load_taper_attributions(conn: sqlite3.Connection) -> dict[int, dict]:
    """Return ``{lb_number: {"confirmed"?: str, "propagated"?: str, "review": bool}}``.

    `confidence='confirmed'` rows render the solid taper pill (spec §5).
    Conflict-free `propagated` rows also carry the taper name since 2026-07-16
    (TODO-242 decision): they render a visually-distinct outline pill in the
    Library. `inferred`/`conflict` rows (and propagated ones too) still feed
    the "taper: needs review" filter via `review`. Feature-detected like
    `_load_latest_abs_grades` since `taper_attributions` may not exist yet on an
    older DB that hasn't run `tools/attribute_tapers.py`.
    """
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='taper_attributions'"
        ).fetchall()
    }
    if "taper_attributions" not in tables:
        return {}
    rows = conn.execute(
        "SELECT lb_number, taper_normalised, confidence, conflict FROM taper_attributions"
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        entry: dict = {}
        if r["confidence"] == "confirmed":
            entry["confirmed"] = r["taper_normalised"]
        elif r["confidence"] == "propagated" and not r["conflict"]:
            entry["propagated"] = r["taper_normalised"]
        if r["confidence"] in ("propagated", "inferred") or r["conflict"]:
            entry["review"] = True
        if entry:
            out[r["lb_number"]] = entry
    return out


def get_pick_badges(db_path=None) -> dict[int, dict]:
    """Flat pick/quality/curated/taper badge fields keyed by LB number.

    The Library's recording lens is sourced from ``/api/search`` +
    ``/api/collection/prefetch`` — neither joins ``show_picks``,
    ``quality_recording_scores``, ``curated_lists`` or ``taper_attributions`` —
    so it can't surface the badges the performance lens gets inline from
    ``get_performances``. This feeds a client-side merge-by-``lb_number``, the
    same pattern the recording lens already uses for TapeMatch families and
    collection prefetch (``instructions/SPEC_INTEGRATION_NOTES.md`` F4; the
    TODO-186 remainder). Reuses the exact loaders ``get_performances`` uses, so
    the two lenses can never disagree on a badge.

    Only LB numbers carrying at least one signal appear, and each dict omits
    fields that don't exist for that recording — identical to the per-recording
    shape ``get_performances`` merges.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        ``{lb_number: {"pickRank"?, "absGrade"?, "curated"?, "taperConfirmed"?,
        "taperPropagated"?, "taperReview"?}}`` — empty on a fresh install
        before recompute.
    """
    conn = get_connection(db_path)
    pick_ranks = _load_pick_ranks(conn)
    curated_by_lb = _load_curated_by_lb(conn)
    abs_grades = _load_latest_abs_grades(conn)
    taper_attrs = _load_taper_attributions(conn)

    out: dict[int, dict] = {}
    for lb, rank in pick_ranks.items():
        out.setdefault(lb, {})["pickRank"] = rank
    for lb, grade in abs_grades.items():
        if grade:
            out.setdefault(lb, {})["absGrade"] = grade
    for lb, names in curated_by_lb.items():
        if names:
            out.setdefault(lb, {})["curated"] = names
    for lb, attr in taper_attrs.items():
        if "confirmed" in attr:
            out.setdefault(lb, {})["taperConfirmed"] = attr["confirmed"]
        if "propagated" in attr:
            out.setdefault(lb, {})["taperPropagated"] = attr["propagated"]
        if attr.get("review"):
            out.setdefault(lb, {})["taperReview"] = True
    return out


def get_performances(db_path=None) -> list[dict]:
    """Group catalog entries into shows for the Library screen's performance lens.

    Aggregates by raw `(date_str, location)` — the same pair
    `06-gap-analysis.md` §B3 identifies as the grouping key. This lives in the
    backend (per the TODO-150 step 5 decision) rather than as a client-side
    groupBy because building real show metadata means cross-referencing
    `bobdylan_shows`, `setlistfm_shows`, and `bootleg_titles` — none of which
    `/api/search` exposes, and duplicating those joins client-side would mean
    re-fetching/re-indexing three more tables in the GUI for no benefit.

    TapeMatch family data is deliberately NOT joined in here — per
    `07-tapematch-backend-integration.md` §4, the Library's data adapter
    fetches `/api/tapematch/families` separately and merges by `lb_number`,
    same as it already does for `/api/collection/prefetch`.

    `lb_category = 'concert'` entries are grouped into shows as before — this
    now includes dates whose only source is `dylan_performances` with category
    `GUEST` (appearance at another artist's show, e.g. Dire Straits/U2/Tom
    Petty/Grateful Dead sets) or `NET` (a Never Ending Tour-era tag, not
    "internet" — both were missing from `_PERF_CATEGORY_MAP` until the
    TODO-151 audit, 2026-06-18). When `bobdylan_shows` has no row for the date
    (true for nearly all GUEST dates, since they're not Dylan's own shows),
    `venue` falls back to `dylan_performances.venue` instead of staying null.

    `lb_category = 'unknown'` entries are ALSO included, but only when they
    have a fully-specified date (no `xx` placeholder) and a non-blank
    location — i.e. when the raw data is concrete enough to form a real show
    grouping even though nothing matched. These render as a degraded row
    (`confirmed: False` — no venue/setlist/tour, since by definition nothing
    matched). This is the fallback for cases `dylan_performances` doesn't
    cover either (e.g. category `FILM` — concert-like footage shoots such as
    the 1986 Bristol Colston Hall "Hearts of Fire" filming — deliberately left
    unmapped since some FILM rows are non-performance B-roll, not shows).
    radio/tv/interview/studio/rehearsal/soundcheck/compilation/other
    recordings, and 'unknown' ones with no usable date+location, still have no
    real show to group into; they remain visible in the recording lens instead
    (TODO-150 decision, 2026-06-18).

    Per instructions/FABLE_UNIFIED_RANKING.md §6 and finding F4, each
    recording also carries flat, optional `pickRank` (`show_picks.pick_rank`
    for its date — 1 is the recommended copy), `absGrade` (latest Concert
    Ranker `quality_recording_scores.abs_grade` scan), and `curated` (list of
    curated-list names it appears in, e.g. `["carbonbit"]`) fields, following
    the same "merge flat fields onto each recording, no N+1 calls" pattern
    already used for TapeMatch family data (merged client-side instead, since
    it's a different consumer — see the class docstring's TapeMatch note).

    Per `instructions/complete/FABLE_TAPER_ATTRIBUTION.md` §5 (TAPER phase 2), each
    recording also carries flat, optional `taperConfirmed` (canonical taper
    name, only when `taper_attributions.confidence='confirmed'`),
    `taperPropagated` (canonical taper name for conflict-free
    `confidence='propagated'` rows — outline pill in the Library, TODO-242
    decision 2026-07-16), and `taperReview` (`true` when confidence is
    `propagated`/`inferred` or the row is flagged `conflict`), following the
    same F4 payload-extension pattern.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        List of performance dicts (data contract Entity 2 shape): `id`,
        `date`, `disp`, `year`, `venue`, `city`, `status`, `recordings`
        always present; `dow`, `tour`, `tracks`, `setlist`, `title` omitted
        (not null-faked) when no source data exists for that show; `confirmed`
        omitted (true by default) except `False` on degraded unknown-only rows.
        Each recording additionally omits `pickRank`/`absGrade`/`curated`/
        `taperConfirmed`/`taperReview` when that signal doesn't exist yet for
        its LB number (pre-recompute, never scanned, in no curated list, or
        no taper attribution row).
    """
    from datetime import datetime as _dt

    conn = get_connection(db_path)
    pick_ranks = _load_pick_ranks(conn)
    curated_by_lb = _load_curated_by_lb(conn)
    abs_grades = _load_latest_abs_grades(conn)
    taper_attrs = _load_taper_attributions(conn)

    rows = conn.execute(
        """
        SELECT e.lb_number, e.date_str, e.location, e.rating, e.source_type,
               e.description, e.source_chain, e.lb_category, lm.lb_status
        FROM entries e
        LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
        WHERE e.lb_category IN ('concert', 'unknown')
        """
    ).fetchall()

    bd_shows: dict[str, sqlite3.Row] = {
        r["date_str"]: r
        for r in conn.execute(
            "SELECT date_str, venue, location, bobdylan_url FROM bobdylan_shows"
        ).fetchall()
    }
    # Fallback venue source for shows bobdylan_shows doesn't track (guest spots,
    # tour dates it's missing) — dylan_performances has real venue names for
    # these (TODO-151). Only consulted when bd_shows has no match.
    dp_venues: dict[str, sqlite3.Row] = {}
    for r in conn.execute(
        "SELECT date_str, venue, city, country FROM dylan_performances"
        " WHERE venue NOT IN ('', '?')"
    ).fetchall():
        dp_venues.setdefault(r["date_str"], r)
    setlist_counts: dict[str, int] = {
        r["bobdylan_url"]: r["n"]
        for r in conn.execute(
            "SELECT bobdylan_url, COUNT(*) AS n FROM bobdylan_setlist GROUP BY bobdylan_url"
        ).fetchall()
    }
    tours: dict[str, str] = {}
    for r in conn.execute(
        "SELECT date_str, tour_name FROM setlistfm_shows WHERE tour_name != ''"
    ).fetchall():
        tours.setdefault(r["date_str"], r["tour_name"])
    # Tour-name fallback chain setlistfm -> olof (TODO-153, FABLE_OLOF_FILES.md
    # §5.3): setlistfm's tour_name coverage is thin, olof_events carries the DSN
    # segment title (1956-2021) for nearly every dated event. setdefault() means
    # setlistfm always wins; this only fills dates setlistfm left blank. Ordered
    # so a 'concert' row is tried before session/rehearsal/etc. rows on dates
    # with more than one olof event (e.g. a same-day session write-up).
    for r in conn.execute(
        """SELECT date_str, tour_name FROM olof_events
           WHERE tour_name != '' AND date_str != ''
           ORDER BY (event_type != 'concert'), event_id"""
    ).fetchall():
        tours.setdefault(r["date_str"], r["tour_name"])
    titles: dict[int, str] = {}
    for r in conn.execute(
        "SELECT lb_number, title FROM bootleg_titles WHERE title != ''"
    ).fetchall():
        titles.setdefault(r["lb_number"], r["title"])

    # Group key: ISO date when the date is fully parseable (Bob Dylan never
    # plays two venues on the same calendar day), else raw "date_str::location"
    # for entries whose date can't be resolved (ambiguous/incomplete dates).
    # Using ISO date as the primary key collapses the common case where different
    # recordings of the same show have slightly different `location` strings
    # (e.g. "Munich" vs "Munich, West Germany") that previously produced
    # multiple duplicate show rows for the same concert.
    groups: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        date_str = r["date_str"] or ""
        location = r["location"] or ""
        iso = _entry_date_to_iso_local(date_str)
        if r["lb_category"] == "unknown":
            # Only degraded-confirm 'unknown' rows with a real date + location —
            # see TODO-151 audit note above. Skip the rest (blank/'xx' dates,
            # no location) just like before.
            if not location.strip() or not iso:
                continue
        key = iso if iso else f"{date_str}::{location}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "recordings": [], "best_status": "missing", "any_concert": False,
                "date_str": date_str, "location": location, "iso": iso,
            }
            order.append(key)
        if r["lb_category"] == "concert":
            g["any_concert"] = True
        status_raw = r["lb_status"] or "missing"
        if _STATUS_RANK.get(status_raw, 2) < _STATUS_RANK.get(g["best_status"], 2):
            g["best_status"] = status_raw
        rec_out = {
            "lb": f"LB-{r['lb_number']:05d}",
            "lbNumber": r["lb_number"],
            "src": r["source_type"] or classify_source_type(r["description"], r["source_chain"]),
            "rating": r["rating"] or "",
            "status": _STATUS_LABEL.get(status_raw, "Missing"),
        }
        pick_rank = pick_ranks.get(r["lb_number"])
        if pick_rank is not None:
            rec_out["pickRank"] = pick_rank
        abs_grade = abs_grades.get(r["lb_number"])
        if abs_grade:
            rec_out["absGrade"] = abs_grade
        curated_names = curated_by_lb.get(r["lb_number"])
        if curated_names:
            rec_out["curated"] = curated_names
        taper_attr = taper_attrs.get(r["lb_number"])
        if taper_attr:
            if "confirmed" in taper_attr:
                rec_out["taperConfirmed"] = taper_attr["confirmed"]
            if "propagated" in taper_attr:
                rec_out["taperPropagated"] = taper_attr["propagated"]
            if taper_attr.get("review"):
                rec_out["taperReview"] = True
        g["recordings"].append(rec_out)

    performances: list[dict] = []
    for key in order:
        g = groups[key]
        date_str = g["date_str"]
        location = g["location"]
        iso = g["iso"]
        disp = date_str
        dow = None
        if iso:
            try:
                dt = _dt.strptime(iso, "%Y-%m-%d")
                disp = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
                dow = dt.strftime("%a")
            except ValueError:
                iso = None

        bd = bd_shows.get(iso) if iso else None
        dp = dp_venues.get(iso) if (iso and not bd) else None
        perf: dict = {
            "id": iso or f"{date_str}::{location}",
            "date": iso if iso else date_str,
            "disp": disp,
            "year": _year_from_date_str(date_str),
            "venue": bd["venue"] if bd else (dp["venue"] if dp else None),
            "city": (dp["city"] if dp else None) or location or None,
            "status": _STATUS_LABEL.get(g["best_status"], "Missing"),
            "recordings": sorted(g["recordings"], key=lambda x: x["lbNumber"]),
        }
        if dow:
            perf["dow"] = dow
        if not g["any_concert"]:
            perf["confirmed"] = False
        tour = tours.get(iso) if iso else None
        if tour:
            perf["tour"] = tour
        if bd:
            perf["setlist"] = iso
            n = setlist_counts.get(bd["bobdylan_url"])
            if n:
                perf["tracks"] = n
        title = next((titles[rec["lbNumber"]] for rec in g["recordings"]
                       if rec["lbNumber"] in titles), None)
        if title:
            perf["title"] = title
        performances.append(perf)

    return performances


_PERF_CATEGORY_MAP: dict[str, str] = {
    "MCONCERT":   "concert",
    "NET":        "concert",   # "Never Ending Tour" era tag, not "internet" — real shows
    "GUEST":      "concert",   # guest appearance at another artist's show — still a real show
    "RADIO":      "radio",
    "TV":         "tv",
    "INTERVIEW":  "interview",
    "SESSION":    "studio",
    "SDEMO":      "studio",
    "HOME":       "studio",
    "SIDEMAN":    "studio",    # backing-musician recording session for another artist
    "REHEARSAL":  "rehearsal",
    "SOUNDCHECK": "soundcheck",
    "COMP":       "compilation",
}

# (category, list-of-lowercase-substrings) checked against description + location
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("interview",   ["interview", "press conference", "in conversation with"]),
    ("radio",       ["radio broadcast", "radio show", "radio station", "for radio", "on the radio"]),
    ("tv",          ["television", "tv show", "tv broadcast", "tv appearance", "tv special",
                     "late show", "tonight show", "ed sullivan", "letterman"]),
    ("studio",      ["studio session", "studio recording", "recording session",
                     "demo session", "demo recording"]),
    ("rehearsal",   ["rehearsal"]),
    ("soundcheck",  ["soundcheck", "sound check"]),
    ("compilation", ["compilation", "greatest hits", "best of", "anthology"]),
]


def _entry_date_to_iso_local(date_str: str) -> str | None:
    """Convert entries.date_str (M/D/YY) to YYYY-MM-DD; return None for 'xx' dates."""
    if not date_str or "xx" in date_str.lower():
        return None
    parts = date_str.split("/")
    if len(parts) != 3:
        return None
    try:
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year = 1900 + year if year >= 49 else 2000 + year
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def classify_entry_categories(db_path=None, conn=None) -> dict[str, int]:
    """Classify every entry in the DB and write lb_category.

    Priority:
      1. bobdylan_shows date match → 'concert'
      2. dylan_performances.category → mapped via _PERF_CATEGORY_MAP → known category or 'other'
      3. Keyword search in description + location → non-concert category
      4. Fallback → 'unknown'

    Args:
        db_path: Optional DB path override.
        conn: Optional existing connection (used during init_db backfill to share
              the write-locked connection).

    Returns:
        Dict of counts: {classified, concert, radio, tv, interview, studio,
        rehearsal, soundcheck, compilation, other, unknown}.
    """
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection(db_path)

    # Build a set of all dates present in bobdylan_shows for fast lookup
    bd_dates: set[str] = {
        r[0] for r in conn.execute("SELECT DISTINCT date_str FROM bobdylan_shows").fetchall()
    }
    # Build a dict of ISO date → mapped category from dylan_performances (first match wins)
    perf_map: dict[str, str] = {}
    for row in conn.execute("SELECT date_str, category FROM dylan_performances").fetchall():
        iso = row[0]
        cat = _PERF_CATEGORY_MAP.get((row[1] or "").upper())
        if cat and iso not in perf_map:
            perf_map[iso] = cat

    entries = conn.execute(
        "SELECT lb_number, date_str, description, location FROM entries"
    ).fetchall()

    counts: dict[str, int] = {"classified": 0}
    updates: list[tuple[str, int]] = []

    for row in entries:
        lb       = row[0]
        date_raw = (row[1] or "")
        desc     = (row[2] or "").lower()
        loc      = (row[3] or "").lower()
        text     = desc + " " + loc

        # Tier 0: xx in date_str → multi-date compilation (day/month unknown)
        if "xx" in date_raw.lower():
            category = "compilation"
        else:
            iso = _entry_date_to_iso_local(date_raw)
            # Tier 1: bobdylan.com concert date
            if iso and iso in bd_dates:
                category = "concert"
            # Tier 2: dylan_performances mapping
            elif iso and iso in perf_map:
                category = perf_map[iso]
            # Tier 3: keyword heuristics (non-concert only)
            else:
                category = "unknown"
                for cat, keywords in _KEYWORD_RULES:
                    if any(kw in text for kw in keywords):
                        category = cat
                        break

        updates.append((category, lb))
        counts["classified"] = counts.get("classified", 0) + 1
        counts[category] = counts.get(category, 0) + 1

    conn.executemany("UPDATE entries SET lb_category=? WHERE lb_number=?", updates)
    if _own_conn:
        conn.commit()

    return counts


def classify_one_entry(date_str: str, description: str, location: str, conn) -> str:
    """Return the lb_category for a single entry given its field values and an open connection.

    Uses the same priority order as classify_entry_categories():
      1. bobdylan_shows date match → 'concert'
      2. dylan_performances category map
      3. Keyword heuristics (non-concert)
      4. 'unknown'

    Intended for use inside write-queue closures where the connection is already open.

    Args:
        date_str: Raw entries.date_str value (e.g. '7/28/00').
        description: Entry description text (may be empty).
        location: Entry location text (may be empty).
        conn: Open SQLite connection.

    Returns:
        Category string.
    """
    date_raw = date_str or ""

    # Tier 0: xx in date_str → multi-date compilation (day/month unknown)
    if "xx" in date_raw.lower():
        return "compilation"

    iso = _entry_date_to_iso_local(date_raw)
    if iso:
        if conn.execute("SELECT 1 FROM bobdylan_shows WHERE date_str=? LIMIT 1", (iso,)).fetchone():
            return "concert"
        perf = conn.execute(
            "SELECT category FROM dylan_performances WHERE date_str=? LIMIT 1", (iso,)
        ).fetchone()
        if perf:
            mapped = _PERF_CATEGORY_MAP.get((perf[0] or "").upper())
            if mapped:
                return mapped
            return "other"

    text = (description or "").lower() + " " + (location or "").lower()
    for cat, keywords in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            return cat

    return "unknown"


def lookup_checksum_owners(checksums, db_path=None):
    """Map each checksum to the LB entries that own it in the checksums table.

    Used to detect when a candidate forum post documents a *different*
    recording than the one being matched: a raw hash lifted from the post body
    that resolves to another lb_number means the post belongs to that entry
    (e.g. a different taper of the same show), not the one under consideration.

    Args:
        checksums: Iterable of checksum hash strings (md5/sha1/ffp) to resolve.
        db_path: Optional database path override.

    Returns:
        Dict mapping each matched checksum string to the sorted list of
        lb_numbers that own it. Checksums with no owner are omitted.
    """
    hashes = {h for h in checksums if h}
    if not hashes:
        return {}
    owners: dict[str, set] = {}
    with get_connection(db_path) as conn:
        # Chunk to stay under SQLite's parameter limit on large posts.
        hash_list = list(hashes)
        for start in range(0, len(hash_list), 400):
            chunk = hash_list[start:start + 400]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT checksum, lb_number FROM checksums "
                f"WHERE checksum IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                owners.setdefault(row["checksum"], set()).add(row["lb_number"])
    return {h: sorted(lbs) for h, lbs in owners.items()}


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
                   c.lbdir_verified_at, c.xref,
                   e.date_str, e.location, e.description, e.rating, e.cdr, e.lb_category,
                   e.source_type, lm.lb_status
            FROM my_collection c
            LEFT JOIN entries e ON c.lb_number = e.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = c.lb_number
            ORDER BY c.lb_number
        """).fetchall()
        alias_rows = conn.execute(
            "SELECT alias_lb, canonical_lb FROM lb_alias"
        ).fetchall()

    # Build bidirectional map: lb -> [all linked lbs in either direction]
    linked: dict[int, list[int]] = {}
    for ar in alias_rows:
        a, c = ar["alias_lb"], ar["canonical_lb"]
        linked.setdefault(a, []).append(c)
        linked.setdefault(c, []).append(a)

    result = []
    for r in rows:
        d = dict(r)
        d["linked_lbs"] = sorted(linked.get(d["lb_number"], []))
        result.append(d)
    return result


def add_to_collection(lb_number, folder_name, disk_path, notes=None, xref: int = 0, db_path=None):
    """Insert a new my_collection row (ignored if lb_number already exists).

    Args:
        lb_number: LB entry number.
        folder_name: Folder name at filing time.
        disk_path: Absolute destination path.
        notes: Optional user note.
        xref: Xref fileset id this copy matches (0 = canonical), carried in
            from the pipeline's ``matched_xref`` (FABLE_XREF_INCORPORATION.md D3).
        db_path: Optional path to the SQLite database file.

    Returns:
        Number of rows inserted (0 or 1).
    """
    _lb, _fn, _dp, _n, _xref = lb_number, folder_name, disk_path, notes, xref

    def _run(c):
        c.execute(
            "INSERT OR IGNORE INTO my_collection(lb_number, folder_name, disk_path, notes, xref)"
            " VALUES(?,?,?,?,?)",
            (_lb, _fn, _dp, _n, _xref)
        )
        return c.execute("SELECT changes()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection(lb_number, fields, db_path=None):
    allowed = {"folder_name", "disk_path", "notes", "xref"}
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


def reassign_collection(old_lb, new_lb, db_path=None):
    """Move a filed folder from one LB entry to another.

    Repoints the ``my_collection`` row (folder_name/disk_path/notes/xref) from
    ``old_lb`` to ``new_lb`` and carries any ``collection_meta`` (personal
    rating, listen count, tags) across so it survives the move. The folder on
    disk is untouched — use folder rename for that (TODO-259).

    Args:
        old_lb: LB number the folder is currently filed under.
        new_lb: LB number to move it to.
        db_path: Optional path to the SQLite database file.

    Raises:
        ValueError: If ``old_lb`` is not owned, ``new_lb`` is absent from the
            catalog, ``new_lb`` is already owned, or the two are equal.
    """
    _old, _new = int(old_lb), int(new_lb)
    if _old == _new:
        raise ValueError("Source and target LB are the same")

    def _run(c):
        row = c.execute(
            "SELECT folder_name, disk_path, notes, xref FROM my_collection"
            " WHERE lb_number=?",
            (_old,),
        ).fetchone()
        if row is None:
            raise ValueError(f"LB-{_old:05d} is not in your collection")
        if c.execute("SELECT 1 FROM entries WHERE lb_number=?", (_new,)).fetchone() is None:
            raise ValueError(f"LB-{_new:05d} does not exist in the catalog")
        if c.execute(
            "SELECT 1 FROM my_collection WHERE lb_number=?", (_new,)
        ).fetchone() is not None:
            raise ValueError(f"LB-{_new:05d} is already in your collection")
        folder_name, disk_path, notes, xref = row
        meta = c.execute(
            "SELECT personal_rating, listen_count, last_listened, tags"
            " FROM collection_meta WHERE lb_number=?",
            (_old,),
        ).fetchone()
        c.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path, notes, xref)"
            " VALUES(?,?,?,?,?)",
            (_new, folder_name, disk_path, notes, xref),
        )
        if meta is not None:
            c.execute(
                "INSERT OR REPLACE INTO collection_meta"
                "(lb_number, personal_rating, listen_count, last_listened, tags)"
                " VALUES(?,?,?,?,?)",
                (_new, *meta),
            )
        # Explicit old-meta delete keeps this correct regardless of whether the
        # ON DELETE CASCADE fires (PRAGMA foreign_keys may be off).
        c.execute("DELETE FROM collection_meta WHERE lb_number=?", (_old,))
        c.execute("DELETE FROM my_collection WHERE lb_number=?", (_old,))

    get_write_queue().execute(_run)


def set_lbdir_verified(disk_path: str, db_path=None) -> bool:
    """Stamp lbdir_verified_at = now for the my_collection row with the given disk_path.

    Args:
        disk_path: Absolute folder path (must match my_collection.disk_path).

    Returns:
        True if a row was updated, False if disk_path was not found in the collection.
    """
    _dp = disk_path

    def _run(c):
        cur = c.execute(
            "UPDATE my_collection SET lbdir_verified_at=datetime('now') WHERE disk_path=?",
            (_dp,)
        )
        return cur.rowcount

    rows_updated = get_write_queue().execute(_run)
    return bool(rows_updated)


def get_missing_from_collection(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT e.lb_number, e.date_str, e.location, e.rating, e.description,
                   lm.lb_status
            FROM entries e
            LEFT JOIN my_collection c ON e.lb_number = c.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE c.lb_number IS NULL
              AND e.status = 'ok'
              AND NOT EXISTS (
                  SELECT 1 FROM lb_alias la
                  JOIN my_collection mc ON la.canonical_lb = mc.lb_number
                  WHERE la.alias_lb = e.lb_number
              )
              AND NOT EXISTS (
                  SELECT 1 FROM lb_alias la
                  JOIN my_collection mc ON la.alias_lb = mc.lb_number
                  WHERE la.canonical_lb = e.lb_number
              )
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
    from datetime import UTC, datetime
    _lb = lb_number
    _ts = datetime.now(UTC).isoformat()
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


def update_wishlist(lb_number: int, fields: dict, db_path=None) -> None:
    """Update priority and/or notes on a wishlist entry.

    Args:
        lb_number: LB number to update.
        fields: Dict with keys 'priority' (int 1-5) and/or 'notes' (str).
    """
    allowed = {"priority", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    _params = list(updates.values()) + [lb_number]
    _sql = f"UPDATE my_wishlist SET {set_clause} WHERE lb_number=?"
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


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


def audit_collection_checksums(db_path=None) -> dict:
    """Cross-check my_collection lb_numbers against the checksums table.

    Returns:
        Dict with keys:
            total (int): total entries in my_collection.
            missing_checksums (int): count with zero checksum rows.
            entries (list[dict]): lb_number, folder_name, disk_path,
                date_str, location, lb_status for each entry with no checksums.
    """
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
        rows = conn.execute("""
            SELECT c.lb_number, c.folder_name, c.disk_path,
                   e.date_str, e.location, lm.lb_status
            FROM my_collection c
            LEFT JOIN entries e ON e.lb_number = c.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = c.lb_number
            WHERE NOT EXISTS (
                SELECT 1 FROM checksums ch WHERE ch.lb_number = c.lb_number
            )
            ORDER BY c.lb_number
        """).fetchall()
    return {
        "total": total,
        "missing_checksums": len(rows),
        "entries": [dict(r) for r in rows],
    }


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


def log_integrity_event(lb_number: int, disk_path: str, event_type: str, detail: str,
                         mount_id: int | None = None, db_path=None) -> None:
    """Insert a watchdog filesystem or integrity-scan event into integrity_events."""
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO integrity_events(lb_number, disk_path, event_type, detail, mount_id) "
            "VALUES(?,?,?,?,?)",
            (lb_number, disk_path, event_type, detail, mount_id),
        )
    )


def get_integrity_events(unacked_only: bool = True, limit: int = 100, db_path=None) -> list:
    """Return integrity events, newest first."""
    where = "WHERE acknowledged=0" if unacked_only else ""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM integrity_events {where} ORDER BY occurred_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def ack_integrity_events(ids: list, db_path=None) -> None:
    """Mark the given integrity_events rows as acknowledged."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE integrity_events SET acknowledged=1 WHERE id IN ({placeholders})",
            list(ids),
        )
    )


def purge_integrity_events(db_path=None) -> None:
    """Delete all watchdog integrity events."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM integrity_events"))


# ── TODO-111: Collection Integrity Monitor ───────────────────────────────────

def upsert_collection_integrity_status(
    lb_number: int,
    mount_id: int | None,
    disk_path: str,
    status: str,
    content_issues: int = 0,
    tag_issues: int = 0,
    missing_count: int = 0,
    total_files: int = 0,
    db_path=None,
) -> None:
    """Insert or replace the latest integrity-scan result for a collection entry.

    Args:
        lb_number: Collection entry LB number (primary key of the status row).
        mount_id: Owning collection_mounts.id, or None if unmatched.
        disk_path: Folder path that was verified.
        status: One of pass, content_issue, tag_issue, missing_files, no_lbdir, error.
        content_issues: Count of files with ffp_status == 'fail' (audio/bitrot).
        tag_issues: Count of files with md5 fail but ffp pass/na (tags only).
        missing_count: Count of lbdir-listed files missing from disk.
        total_files: Total lbdir-listed files considered (excluding 'extra').
    """
    _args = (lb_number, mount_id, disk_path, status, content_issues, tag_issues,
             missing_count, total_files)
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_integrity_status "
            "(lb_number, mount_id, disk_path, status, content_issues, tag_issues, "
            " missing_count, total_files, checked_at) "
            "VALUES(?,?,?,?,?,?,?,?,datetime('now')) "
            "ON CONFLICT(lb_number) DO UPDATE SET "
            "mount_id=excluded.mount_id, disk_path=excluded.disk_path, "
            "status=excluded.status, content_issues=excluded.content_issues, "
            "tag_issues=excluded.tag_issues, missing_count=excluded.missing_count, "
            "total_files=excluded.total_files, checked_at=excluded.checked_at",
            _args,
        )
    )


def get_collection_integrity_status(
    mount_id: int | None = None, status: str | None = None, db_path=None
) -> list[dict]:
    """Return collection_integrity_status rows, optionally filtered by mount and status.

    Args:
        mount_id: If given, only rows for this collection_mounts.id.
        status: If given, only rows with this status value.

    Returns:
        List of row dicts, ordered by lb_number.
    """
    where = []
    params: list = []
    if mount_id is not None:
        where.append("mount_id=?")
        params.append(mount_id)
    if status is not None:
        where.append("status=?")
        params.append(status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM collection_integrity_status {clause} ORDER BY lb_number",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_mount_integrity_summary(db_path=None) -> dict[int, dict[str, int]]:
    """Return per-mount counts of integrity statuses for GUI badges.

    Returns:
        Mapping of mount_id (or 0 for unmatched/None) to a dict with keys
        pass, content_issue, tag_issue, missing_files, no_lbdir, error — each
        the count of collection_integrity_status rows with that status.
    """
    statuses = ("pass", "content_issue", "tag_issue", "missing_files", "no_lbdir", "error")
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT COALESCE(mount_id, 0) AS mid, status, COUNT(*) AS n "
            "FROM collection_integrity_status GROUP BY mid, status"
        ).fetchall()
    summary: dict[int, dict[str, int]] = {}
    for r in rows:
        bucket = summary.setdefault(r["mid"], {s: 0 for s in statuses})
        if r["status"] in bucket:
            bucket[r["status"]] = r["n"]
    return summary


def record_integrity_scan_start(mount_id: int | None = None, db_path=None) -> int:
    """Insert a new collection_integrity_scans row in 'running' state.

    Args:
        mount_id: Mount being scanned, or None for a whole-collection scan.

    Returns:
        The new scan row's id.
    """
    def _run(c):
        cur = c.execute(
            "INSERT INTO collection_integrity_scans(mount_id, status) VALUES(?, 'running')",
            (mount_id,),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_integrity_scan(
    scan_id: int,
    status: str,
    counts: dict[str, int],
    error: str | None = None,
    db_path=None,
) -> None:
    """Mark a collection_integrity_scans row finished and record aggregate counts.

    Args:
        scan_id: Row id returned by record_integrity_scan_start.
        status: Final scan status — done, error, or cancelled.
        counts: Dict with keys folders_checked, folders_pass, folders_content_issue,
            folders_tag_issue, folders_missing, folders_no_lbdir.
        error: Optional error message if status == 'error'.
    """
    get_write_queue().execute(
        lambda c: c.execute(
            "UPDATE collection_integrity_scans SET "
            "status=?, finished_at=datetime('now'), "
            "folders_checked=?, folders_pass=?, folders_content_issue=?, "
            "folders_tag_issue=?, folders_missing=?, folders_no_lbdir=?, error=? "
            "WHERE id=?",
            (
                status,
                counts.get("folders_checked", 0),
                counts.get("folders_pass", 0),
                counts.get("folders_content_issue", 0),
                counts.get("folders_tag_issue", 0),
                counts.get("folders_missing", 0),
                counts.get("folders_no_lbdir", 0),
                error,
                scan_id,
            ),
        )
    )


def get_integrity_scan_history(
    mount_id: int | None = None, limit: int = 20, db_path=None
) -> list[dict]:
    """Return recent collection_integrity_scans rows, newest first.

    Args:
        mount_id: If given, only scans for this mount (None matches whole-collection
            scans where mount_id IS NULL).
        limit: Maximum number of rows to return.
    """
    with get_connection(db_path) as conn:
        if mount_id is None:
            rows = conn.execute(
                "SELECT * FROM collection_integrity_scans "
                "WHERE mount_id IS NULL ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM collection_integrity_scans "
                "WHERE mount_id=? ORDER BY started_at DESC LIMIT ?",
                (mount_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


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


def add_wtrf_download(
    lb_number: int,
    topic_url: str | None,
    torrent_path: str | None,
    confidence: str,
    signals_json: str,
    status: str,
    error: str | None = None,
    db_path=None,
) -> int:
    """Insert a wtrf_downloads row and return its new id.

    Args:
        lb_number: LB entry being fetched.
        topic_url: Matched WTRF topic URL (None if not found).
        torrent_path: Local path of downloaded .torrent (None until downloaded).
        confidence: One of definitive/high/medium/needs_review/ambiguous/not_found.
        signals_json: JSON string of scoring detail dict.
        status: One of pending/downloaded/qbt_added/failed/skipped.
        error: Error message string if status=failed.
        db_path: Optional DB path override.

    Returns:
        New row id.
    """
    _lb, _tu, _tp, _conf, _sj, _st, _err = (
        lb_number, topic_url, torrent_path, confidence, signals_json, status, error
    )

    def _run(c):
        cur = c.execute(
            "INSERT INTO wtrf_downloads"
            "(lb_number, topic_url, torrent_path, confidence, signals_json, status, error)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_lb, _tu, _tp, _conf, _sj, _st, _err),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_wtrf_download(download_id: int, fields: dict, db_path=None) -> None:
    """Update one or more columns on a wtrf_downloads row.

    Args:
        download_id: Primary key of the row to update.
        fields: Dict of column→value pairs to set.
        db_path: Optional DB path override.
    """
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [download_id]
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE wtrf_downloads SET {set_clause} WHERE id=?", values
        )
    )


def get_wtrf_downloads(lb_number: int | None = None, db_path=None) -> list[dict]:
    """Return wtrf_downloads rows, optionally filtered by lb_number.

    Args:
        lb_number: If given, return only rows for this LB.
        db_path: Optional DB path override.

    Returns:
        List of row dicts, newest first.
    """
    with get_connection(db_path) as conn:
        if lb_number is not None:
            rows = conn.execute(
                "SELECT * FROM wtrf_downloads WHERE lb_number=? ORDER BY attempted_at DESC",
                (lb_number,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM wtrf_downloads ORDER BY attempted_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_wtrf_pending_lb_numbers(db_path=None) -> list[int]:
    """Return lb_numbers that are public, not in my_collection, and not yet
    successfully fetched (no downloaded/qbt_added row), ordered desc.

    Used by the batch crawl to build the work queue.

    Args:
        db_path: Optional DB path override.

    Returns:
        List of lb_numbers descending.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT lm.lb_number
              FROM lb_master lm
             WHERE lm.lb_status = 'public'
               AND lm.lb_number NOT IN (SELECT lb_number FROM my_collection)
               AND lm.lb_number NOT IN (
                   SELECT lb_number FROM wtrf_downloads
                    WHERE status IN ('downloaded', 'qbt_added')
               )
             ORDER BY lm.lb_number DESC
            """
        ).fetchall()
    return [r[0] for r in rows]


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


def delete_torrent_record(torrent_id: int, db_path=None) -> None:
    """Delete a torrents row by id."""
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM torrents WHERE id=?", (torrent_id,))
    )


def clear_superseded_torrent_paths(lb_number: int, new_id: int, new_path: str,
                                   db_path=None) -> None:
    """Null out torrent_path on older records for the same LB that share new_path.

    Called after a regen so stale records no longer falsely report
    torrent_file_exists=True when the new file was created at the same path as
    a previously-deleted one.
    """
    def _run(c: object) -> None:
        c.execute(  # type: ignore[attr-defined]
            "UPDATE torrents SET torrent_path=NULL WHERE lb_number=? AND id!=? AND torrent_path=?",
            (lb_number, new_id, new_path),
        )
    get_write_queue().execute(_run)


# ── Rename History ─────────────────────────────────────────────────────────────

def add_rename_history(lb_number: int | None, old_path: str, new_path: str,
                       source: str, notes: str = "", db_path=None) -> None:
    """Insert a rename_history row with a local-time timestamp."""
    from datetime import datetime as _dt
    _lb, _op, _np, _src, _nt = lb_number, old_path, new_path, source, notes
    _ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT INTO rename_history(lb_number, old_path, new_path, source, notes, renamed_at)
               VALUES(?,?,?,?,?,?)""",
            (_lb, _op, _np, _src, _nt, _ts)
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

    logger.info(
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
    from datetime import UTC
    from datetime import datetime as _dt
    _lb, _status, _notes, _set_by = lb_number, status, notes, set_by
    _now = _dt.now(UTC).isoformat()

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
        get_write_queue().execute(
            lambda c, _lb=lb: c.execute(
                """INSERT INTO lb_status_history (lb_number, old_status, new_status, trigger_event)
                   SELECT lb_number, previous_status, lb_status, 'import'
                   FROM lb_master WHERE lb_number=?""",
                (_lb,),
            )
        )
        imported += 1
    logger.info(
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
    import json
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


def import_master_db(snapshot_path: "Path | str", db_path=None) -> dict:
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

    Returns:
        Summary dict: ``{master_version, rows_per_table, lb_status_counts,
        backup_path, lb_status_changes, skipped_tables}``.

    Raises:
        FileNotFoundError: snapshot or manifest missing.
        ValueError: SHA256 mismatch.
        RuntimeError: schema version too new for this client.
    """
    import hashlib
    import json
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

    return {
        "master_version": manifest.get("master_version"),
        "master_published_at": manifest.get("master_published_at"),
        "row_counts": row_counts,
        "pre_status_counts": pre_status,
        "post_status_counts": post_status,
        "lb_status_changes": changed,
        "backup_path": str(backup_path),
        "imported_at": _dt.now(UTC).isoformat(),
        "skipped_tables": skipped_tables,
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


def get_folder_links(folder_path: str, db_path=None) -> list[dict]:
    """Return all folder_lb_link rows for a path, sorted by lb_number.

    Args:
        folder_path: Absolute path of the folder.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of row dicts (keys: folder_path, lb_number, linked_at, note).
        Empty list if no links are stored.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM folder_lb_link WHERE folder_path=? ORDER BY lb_number",
        (folder_path,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_folder_link(folder_path: str, db_path=None) -> dict | None:
    """Return the first folder_lb_link row for a path, or None.

    Prefer get_folder_links() when multi-LB links are possible.
    """
    rows = get_folder_links(folder_path, db_path)
    return rows[0] if rows else None


def set_folder_link(
    folder_path: str, lb_number: int, note: str = "", xref: int = 0, db_path=None,
) -> None:
    """Add a folder→LB link, or refresh its xref if the pair already exists.

    The note and linked_at timestamp are only set on first insert (never
    overwritten on a re-run); ``xref`` is always kept current so a folder
    whose matched fileset changes on a later lookup (e.g. after a DB update)
    is reflected here too (FABLE_XREF_INCORPORATION.md D3).

    Args:
        folder_path: Absolute path of the folder.
        lb_number: LB number to link this folder to.
        note: Optional user note (first-insert only).
        xref: Xref fileset id this folder matches (0 = canonical).
        db_path: Optional path to the SQLite database file.
    """
    _fp, _lb, _note, _xref = folder_path, lb_number, note, xref
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO folder_lb_link (folder_path, lb_number, note, xref, linked_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(folder_path, lb_number) DO UPDATE SET xref=excluded.xref",
            (_fp, _lb, _note, _xref),
        )
    )


def replace_folder_link(
    folder_path: str, lb_number: int, note: str = "", xref: int = 0, db_path=None,
) -> None:
    """Replace all links for a folder with a single folder→LB link.

    Used by the user "Pin & continue" flow: a re-pin must supersede any
    previous pin (or auto-written multi-LB links) for the folder, unlike
    :func:`set_folder_link`, which is additive.

    Args:
        folder_path: Absolute path of the folder.
        lb_number: LB number the folder should be pinned to.
        note: Optional user note.
        xref: Xref fileset id this folder matches (0 = canonical).
        db_path: Optional path to the SQLite database file.
    """
    _fp, _lb, _note, _xref = folder_path, lb_number, note, xref

    def _run(c):
        c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_fp,))
        c.execute(
            "INSERT INTO folder_lb_link (folder_path, lb_number, note, xref, linked_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
            (_fp, _lb, _note, _xref),
        )

    get_write_queue().execute(_run)


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


def rekey_folder_link(old_path: str, new_path: str, db_path=None) -> None:
    """Move folder_lb_link rows from old_path to new_path after a folder rename.

    A pin ("Pin & continue") is keyed on the exact folder path, so without this
    the link is orphaned the moment the folder is renamed and downstream steps
    (lbdir/rename/file) lose the pinned LB# on their next run.

    Args:
        old_path: Absolute path of the folder before renaming.
        new_path: Absolute path of the folder after renaming.
        db_path: Optional path to the SQLite database file.
    """
    _old, _new = old_path, new_path

    def _rekey(c):
        c.execute(
            "UPDATE OR IGNORE folder_lb_link SET folder_path=? WHERE folder_path=?",
            (_new, _old),
        )
        # Any rows left under _old conflicted with an existing (_new, lb_number)
        # link and were skipped by OR IGNORE — that link already exists, drop the stale one.
        c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_old,))

    get_write_queue().execute(_rekey)


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

_BOOTLEG_SOURCE_URL = SITE_BASE_URL + "/detail/LB-bootleg-by-title.html"


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


def get_missing_attachment_urls(db_path=None) -> list[str]:
    """Return ``entry_files`` URLs not yet mirrored (``downloaded=0``).

    Used by the site crawler to seed attachment URLs (xref attachments
    included) that no crawled HTML page links to, so the mirror converges
    on every attachment the scraper knows about.

    Args:
        db_path: Override DB path (tests).

    Returns:
        Attachment URLs ordered by URL.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT file_url FROM entry_files WHERE downloaded=0 ORDER BY file_url"
        ).fetchall()
    return [r["file_url"] for r in rows]


def get_downloaded_urls(db_path=None) -> set[str]:
    """Return the set of URLs already downloaded or confirmed not found."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT url FROM site_inventory "
            "WHERE status IN ('downloaded', 'not_found', 'skipped')"
        ).fetchall()
    return {r["url"] for r in rows}


def get_inventory_last_modified(urls: list[str], db_path=None) -> dict[str, str | None]:
    """Return ``{url: last_modified}`` for the given URLs from site_inventory.

    Args:
        urls:    List of absolute URL strings to look up.
        db_path: Optional DB path override.

    Returns:
        Dict mapping each URL to its stored ``Last-Modified`` header value, or
        ``None`` when the row exists but has no ``last_modified`` stored.  URLs
        not present in ``site_inventory`` are omitted from the result.
    """
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT url, last_modified FROM site_inventory WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
    return {r["url"]: r["last_modified"] for r in rows}


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


def get_or_create_curated_list(
    name: str, label: str = "", source: str = "", db_path=None
) -> int:
    """Return the id of the curated list named ``name``, creating it if absent.

    Args:
        name: Unique slug for the list (e.g. ``'carbonbit'``, ``'10haaf'``).
        label: Human-readable display name. Only set on first creation.
        source: Free-text note on where the list came from. Only set on
            first creation.
        db_path: Optional database path override.

    Returns:
        The ``id`` of the curated_lists row.
    """
    conn = get_connection(db_path)
    row = conn.execute("SELECT id FROM curated_lists WHERE name=?", (name,)).fetchone()
    if row is not None:
        return row[0]
    _name, _label, _source = name, label, source

    def _run(c):
        cur = c.execute(
            "INSERT INTO curated_lists(name, label, source) VALUES(?,?,?)",
            (_name, _label, _source),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def delete_curated_list(name: str, db_path=None) -> bool:
    """Delete a curated list and all of its entries, by name.

    Args:
        name: The curated list's unique slug (e.g. ``'carbonbit'``).
        db_path: Optional database path override.

    Returns:
        True if a list with that name was deleted, False if none existed.
    """
    conn = get_connection(db_path)
    row = conn.execute("SELECT id FROM curated_lists WHERE name=?", (name,)).fetchone()
    if row is None:
        return False
    list_id = row[0]

    def _run(c):
        c.execute("DELETE FROM curated_list_entries WHERE list_id=?", (list_id,))
        c.execute("DELETE FROM curated_lists WHERE id=?", (list_id,))

    get_write_queue().execute(_run)
    return True


def get_curated_lists(db_path=None) -> list[dict]:
    """Return all curated lists with their entry counts.

    Args:
        db_path: Optional database path override.

    Returns:
        List of dicts with keys: id, name, label, source, created_at, entry_count.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT cl.id, cl.name, cl.label, cl.source, cl.created_at,"
        " COUNT(ce.id) AS entry_count"
        " FROM curated_lists cl LEFT JOIN curated_list_entries ce ON ce.list_id = cl.id"
        " GROUP BY cl.id ORDER BY cl.name"
    ).fetchall()
    return [dict(r) for r in rows]


def add_curated_list_entries(
    list_id: int, entries: list[tuple[int, str]], db_path=None
) -> int:
    """Bulk-insert (lb_number, note) pairs into curated_list_entries.

    Duplicate (list_id, lb_number) pairs are silently skipped via the
    table's UNIQUE constraint, so re-running an import is idempotent.

    Args:
        list_id: The curated_lists row these entries belong to.
        entries: List of (lb_number, note) tuples.
        db_path: Optional database path override.

    Returns:
        The number of entries passed in (not the number actually inserted,
        since duplicates are ignored without raising).
    """
    _list_id = list_id
    _rows = [(_list_id, lb, note) for lb, note in entries]

    def _run(c):
        c.executemany(
            "INSERT OR IGNORE INTO curated_list_entries(list_id, lb_number, note)"
            " VALUES(?,?,?)",
            _rows,
        )

    get_write_queue().execute(_run)
    return len(entries)


def get_curated_list_entries(
    list_name: str | None = None, lb_number: int | None = None, db_path=None
) -> list[dict]:
    """Return curated_list_entries rows, optionally filtered.

    Args:
        list_name: When provided, only return entries for this list's name.
        lb_number: When provided, only return entries for this LB number.
        db_path: Optional database path override.

    Returns:
        List of dicts with keys: lb_number, note, added_at, list_name, list_label.
    """
    conn = get_connection(db_path)
    clauses = []
    params: list = []
    if list_name is not None:
        clauses.append("cl.name = ?")
        params.append(list_name)
    if lb_number is not None:
        clauses.append("ce.lb_number = ?")
        params.append(lb_number)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        "SELECT ce.lb_number, ce.note, ce.added_at, cl.name AS list_name,"
        " cl.label AS list_label"
        " FROM curated_list_entries ce JOIN curated_lists cl ON cl.id = ce.list_id"
        f" {where} ORDER BY cl.name, ce.lb_number",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ── Show picks lookup (FABLE_UNIFIED_RANKING §6 — GET /api/picks/for/<lb>) ────

def get_show_pick_for_lb(lb_number: int, db_path=None) -> dict | None:
    """Return one LB's ``show_picks`` row (rank/score/evidence), if computed.

    Args:
        lb_number: The LB number to look up.
        db_path: Optional database path override.

    Returns:
        Dict with ``concert_date``, ``lb_number``, ``pick_score``,
        ``pick_rank``, ``evidence`` (parsed from ``evidence_json`` — a list
        of ``{kind, detail, ...}`` records per F3), and ``computed_at``, or
        None if ``show_picks`` has no row for this LB (pre-recompute, or the
        entry has no usable date so it was never a scoring candidate).
    """
    import json

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT concert_date, lb_number, pick_score, pick_rank, evidence_json,"
        " computed_at FROM show_picks WHERE lb_number=?",
        (lb_number,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["evidence"] = json.loads(result.pop("evidence_json"))
    return result


def get_picks_for_date(date_iso: str, db_path=None) -> list[dict]:
    """Return all ``show_picks`` rows for one ISO concert date, rank-ordered.

    Args:
        date_iso: Concert date as ``YYYY-MM-DD``.
        db_path: Optional database path override.

    Returns:
        List of dicts (``concert_date``, ``lb_number``, ``pick_score``,
        ``pick_rank``, ``evidence``, ``concert_date_iso``, ``computed_at``),
        ordered by ``pick_rank`` ascending. Empty list if no picks were
        computed for that date.
    """
    import json

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT concert_date, lb_number, pick_score, pick_rank, evidence_json,"
        " concert_date_iso, computed_at FROM show_picks"
        " WHERE concert_date_iso=? ORDER BY pick_rank ASC",
        (date_iso,),
    ).fetchall()
    out = []
    for row in rows:
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        out.append(result)
    return out


def get_tonight_picks(mmdd: str, db_path=None, limit: int = 10) -> list[dict]:
    """Return rank-1 show picks whose concert date falls on this calendar day
    across all years — "this night in Dylan history" (LISTENING spec §9).

    Args:
        mmdd: Calendar day as ``MM-DD`` (e.g. ``"07-28"``).
        db_path: Optional database path override.
        limit: Max candidates to return, ordered by ``pick_score`` desc.

    Returns:
        List of dicts: ``lb_number``, ``concert_date_iso``, ``year``,
        ``location``, ``rating``, ``pick_score``, ``description``
        (truncated to ~200 chars). Empty list if nothing matches.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT sp.lb_number AS lb_number, sp.concert_date_iso AS concert_date_iso,"
        " sp.pick_score AS pick_score, e.location AS location, e.rating AS rating,"
        " e.description AS description"
        " FROM show_picks sp JOIN entries e ON e.lb_number = sp.lb_number"
        " WHERE sp.pick_rank = 1 AND substr(sp.concert_date_iso, 6, 5) = ?"
        " ORDER BY sp.pick_score DESC LIMIT ?",
        (mmdd, limit),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        desc = d.get("description") or ""
        d["description"] = desc[:200]
        d["year"] = int(d["concert_date_iso"][:4]) if d["concert_date_iso"] else None
        out.append(d)
    return out


# ── Archive.org upload history ────────────────────────────────────────────────

def create_archive_upload(lb_number: int, identifier: str, folder_path: str,
                          files_total: int, db_path=None) -> int:
    """Insert a new archive_org_uploads row in 'running' status and return its id.

    Args:
        lb_number: LosslessBob entry number.
        identifier: Internet Archive item identifier.
        folder_path: Absolute path to the source folder.
        files_total: Total number of files to upload.
        db_path: Optional database path override.

    Returns:
        New row id.
    """
    _lb, _id, _fp, _ft = lb_number, identifier, folder_path, files_total

    def _run(c):
        cur = c.execute(
            "INSERT INTO archive_org_uploads(lb_number, identifier, folder_path, files_total, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            (_lb, _id, _fp, _ft),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_archive_upload(upload_id: int, status: str, error: str | None = None,
                          files_uploaded: int | None = None, db_path=None) -> None:
    """Mark an archive upload row as finished.

    Args:
        upload_id: Row id of the archive_org_uploads row.
        status: Final status string — 'done', 'failed', 'stopped'.
        error: Error message if status is 'failed'.
        files_uploaded: Files successfully uploaded (None = leave unchanged).
        db_path: Optional database path override.
    """
    _uid, _st, _err, _fu = upload_id, status, error, files_uploaded

    def _run(c):
        if _fu is not None:
            c.execute(
                "UPDATE archive_org_uploads "
                "SET status=?, error=?, files_uploaded=?, finished_at=datetime('now') "
                "WHERE id=?",
                (_st, _err, _fu, _uid),
            )
        else:
            c.execute(
                "UPDATE archive_org_uploads "
                "SET status=?, error=?, finished_at=datetime('now') WHERE id=?",
                (_st, _err, _uid),
            )

    get_write_queue().execute(_run)


def get_archive_uploads(lb_number: int | None = None, db_path=None) -> list:
    """Return archive upload rows, newest first.

    Args:
        lb_number: If given, restrict to uploads for this LB. Otherwise return all.
        db_path: Optional database path override.

    Returns:
        List of row dicts.
    """
    with get_connection(db_path) as conn:
        if lb_number is not None:
            rows = conn.execute(
                "SELECT * FROM archive_org_uploads WHERE lb_number=? ORDER BY started_at DESC",
                (lb_number,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT au.*, e.date_str, e.location "
                "FROM archive_org_uploads au "
                "LEFT JOIN entries e ON e.lb_number = au.lb_number "
                "ORDER BY au.started_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


# ── Collection Mounts ──────────────────────────────────────────────────────────

def get_collection_mounts(db_path=None) -> list[dict]:
    """Return all mounts; online status is checked by the caller via filer._path_reachable."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, label, root_path, notes, created_at "
            "FROM collection_mounts ORDER BY label"
        ).fetchall()
    return [dict(r) for r in rows]


def add_collection_mount(label: str, root_path: str, notes: str | None = None,
                         db_path=None) -> int:
    """Insert a new mount. Returns the new row id."""
    _l, _r, _n = label, root_path, notes

    def _run(c):
        c.execute(
            "INSERT INTO collection_mounts(label, root_path, notes) VALUES(?,?,?)",
            (_l, _r, _n),
        )
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection_mount(mount_id: int, fields: dict, db_path=None) -> None:
    """Update allowed fields on a mount row."""
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
    """Delete a mount. Returns {ok, error} — fails if any routes reference it."""
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
            "INSERT OR REPLACE INTO collection_routes(year, mount_id, sub_path) VALUES(?,?,?)",
            [(y, _mid, _sp) for y in years],
        )
        return len(years)

    return get_write_queue().execute(_run)


def delete_collection_route(year: int, db_path=None) -> None:
    """Remove the route for a single year."""
    _y = year
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM collection_routes WHERE year=?", (_y,))
    )


# ── Pipeline hash/state cache (TODO-205 Phase 1) ───────────────────────────────
# Design: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md §2–§3. Inert until the
# later phases wire consultation into _pipeline_process_folder; nothing reads
# these tables yet.

_PIPELINE_STEPS = ("verify", "lookup", "lbdir", "rename", "file")


def _norm_folder(raw: str) -> str:
    """Normalise a folder path to the forward-slash cache-key form.

    Mirrors filer.normalise_path (Path.as_posix) without importing filer,
    which would create a backend.filer ↔ backend.db import cycle.
    """
    return Path(raw).as_posix()


def _cacheable(*texts: str) -> bool:
    """Whether all strings can be stored as SQLite TEXT.

    Paths of files whose on-disk names hold undecodable bytes carry lone
    surrogates (os surrogateescape), which sqlite3 cannot bind as TEXT.
    Such paths are simply never cached — a cache miss means a fresh read,
    so skipping them costs speed, never correctness.
    """
    try:
        for t in texts:
            t.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def upsert_file_hash(folder_path: str, rel_path: str, size: int, mtime: float,
                     md5: "str | None" = None, ffp: "str | None" = None,
                     sha256: "str | None" = None, db_path=None) -> None:
    """Insert or refresh one pipeline_file_hash row.

    Hash columns merge: a NULL argument preserves any previously stored value
    ONLY when (size, mtime) are unchanged — a changed file replaces the whole
    row so no stale hash of older content can survive alongside new stats.

    Args:
        folder_path: Absolute folder path (normalised internally).
        rel_path: Posix-style path of the file relative to folder_path.
        size: Current os.stat st_size — validation column.
        mtime: Current os.stat st_mtime — validation column.
        md5: Full-file md5 hex, if computed.
        ffp: FLAC fingerprint hex, if computed (FLAC audio only).
        sha256: Full-file sha256 hex, if computed.
        db_path: Unused; writes route through the shared write queue.
    """
    _fp, _rel = _norm_folder(folder_path), rel_path
    if not _cacheable(_fp, _rel):
        return

    def _run(c):
        row = c.execute(
            "SELECT size, mtime FROM pipeline_file_hash "
            "WHERE folder_path=? AND rel_path=?", (_fp, _rel),
        ).fetchone()
        same = row is not None and row["size"] == size and row["mtime"] == mtime
        if same:
            c.execute(
                "UPDATE pipeline_file_hash SET "
                "md5=COALESCE(?, md5), ffp=COALESCE(?, ffp), "
                "sha256=COALESCE(?, sha256), hashed_at=CURRENT_TIMESTAMP "
                "WHERE folder_path=? AND rel_path=?",
                (md5, ffp, sha256, _fp, _rel),
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO pipeline_file_hash "
                "(folder_path, rel_path, size, mtime, md5, ffp, sha256, hashed_at) "
                "VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (_fp, _rel, size, mtime, md5, ffp, sha256),
            )

    get_write_queue().execute(_run)


def get_file_hash(folder_path: str, rel_path: str, db_path=None) -> "dict | None":
    """Return one pipeline_file_hash row, or None.

    Raw fetch — the caller must validate (size, mtime) against a fresh os.stat
    before trusting any hash (design rule R1: validate at consumption).
    """
    if not _cacheable(_norm_folder(folder_path), rel_path):
        return None
    row = get_connection(db_path).execute(
        "SELECT * FROM pipeline_file_hash WHERE folder_path=? AND rel_path=?",
        (_norm_folder(folder_path), rel_path),
    ).fetchone()
    return dict(row) if row else None


def get_folder_hashes(folder_path: str, db_path=None) -> "dict[str, dict]":
    """Return all pipeline_file_hash rows for a folder, keyed by rel_path.

    Raw fetch (one query for batch consumers like derive_tree_digest); rows
    still need per-file (size, mtime) validation before use.
    """
    if not _cacheable(_norm_folder(folder_path)):
        return {}
    rows = get_connection(db_path).execute(
        "SELECT * FROM pipeline_file_hash WHERE folder_path=?",
        (_norm_folder(folder_path),),
    ).fetchall()
    return {r["rel_path"]: dict(r) for r in rows}


def folder_fingerprint(folder_path: str) -> "str | None":
    """Compute the per-file stat-aggregate fingerprint of a folder (design §3 R2).

    sha256 over sorted "rel_path\\tsize\\tmtime" lines for every file under the
    folder (audio + checksums + art). Pure os.stat sweep — no content reads —
    so it changes on any add/remove/rename/in-place edit, unlike the
    directory's own mtime.

    Returns:
        Hex digest, or None when the folder does not exist.
    """
    import hashlib

    root = Path(folder_path)
    if not root.is_dir():
        return None
    lines = []
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            lines.append(f"{p.relative_to(root).as_posix()}\t{st.st_size}\t{st.st_mtime}")
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8", "surrogatepass")).hexdigest()


def get_folder_state(folder_path: str, db_path=None) -> "dict | None":
    """Return the cached pipeline row state for a folder, or None.

    Returns:
        Dict with keys folder_path, fingerprint, steps (step name → verdict
        dict, JSON already parsed), steps_run (list) and updated_at. Callers
        must recompute folder_fingerprint and compare before trusting any
        verdict (design §3 R3); the file step is never authoritative (P8).
    """
    import json

    if not _cacheable(_norm_folder(folder_path)):
        return None
    row = get_connection(db_path).execute(
        "SELECT * FROM pipeline_folder_state WHERE folder_path=?",
        (_norm_folder(folder_path),),
    ).fetchone()
    if not row:
        return None
    steps = {}
    for name in _PIPELINE_STEPS:
        raw = row[f"{name}_json"]
        if raw:
            steps[name] = json.loads(raw)
    return {
        "folder_path": row["folder_path"],
        "fingerprint": row["fingerprint"],
        "steps": steps,
        "steps_run": json.loads(row["steps_json"]) if row["steps_json"] else [],
        "updated_at": row["updated_at"],
    }


def put_folder_state(folder_path: str, fingerprint: str,
                     step_results: "dict[str, dict]", db_path=None) -> None:
    """Upsert cached step verdicts for a folder (design §2b).

    Merge semantics: when the stored fingerprint equals *fingerprint*, steps
    absent from *step_results* keep their previous verdicts (partial re-run).
    When it differs, all previous verdicts are discarded — they described
    different bytes and must not survive under the new fingerprint.

    Args:
        folder_path: Absolute folder path (normalised internally).
        fingerprint: Current folder_fingerprint() of the folder.
        step_results: Step name → verdict dict, for the steps just run.
            Unknown step names raise ValueError.
        db_path: Unused; writes route through the shared write queue.
    """
    import json

    bad = set(step_results) - set(_PIPELINE_STEPS)
    if bad:
        raise ValueError(f"Unknown pipeline steps: {sorted(bad)}")
    _fp = _norm_folder(folder_path)
    if not _cacheable(_fp):
        return

    def _run(c):
        row = c.execute(
            "SELECT fingerprint, steps_json FROM pipeline_folder_state "
            "WHERE folder_path=?", (_fp,),
        ).fetchone()
        merge = row is not None and row["fingerprint"] == fingerprint
        if merge:
            prev_run = set(json.loads(row["steps_json"]) if row["steps_json"] else [])
            steps_run = sorted(prev_run | set(step_results))
            sets = ", ".join(f"{n}_json=?" for n in step_results)
            c.execute(
                f"UPDATE pipeline_folder_state SET {sets}, steps_json=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE folder_path=?",
                (*(json.dumps(step_results[n]) for n in step_results),
                 json.dumps(steps_run), _fp),
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO pipeline_folder_state "
                "(folder_path, fingerprint, verify_json, lookup_json, lbdir_json, "
                "rename_json, file_json, steps_json, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (_fp, fingerprint,
                 *(json.dumps(step_results[n]) if n in step_results else None
                   for n in _PIPELINE_STEPS),
                 json.dumps(sorted(step_results))),
            )

    get_write_queue().execute(_run)


def derive_tree_digest(folder_path: str, db_path=None) -> str:
    """Reproduce filer.hash_tree() from cached sha256s, byte-for-byte (design §2c).

    Serves the SOURCE side of filing's hash-verify only: enumerates every file
    under the folder exactly as hash_tree does, uses a cached sha256 when the
    row's (size, mtime) still validate against a fresh os.stat (rule R1), and
    reads + hashes the file fresh on any miss (write-through to the cache).
    The DESTINATION digest after a copy must always come from filer.hash_tree
    on real bytes — never from this function.

    Args:
        folder_path: Absolute folder path.
        db_path: Optional DB path for cache reads.

    Returns:
        Hex digest identical to filer.hash_tree(folder_path).
    """
    import hashlib

    root = Path(folder_path)
    cached = get_folder_hashes(folder_path, db_path)
    tree_digest = hashlib.sha256()
    rel_paths = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    for rel_path in rel_paths:
        # Stored rel_path keys are posix-form; str(relative_to) is identical on
        # posix and differs only on Windows.
        key = Path(rel_path).as_posix()
        st = (root / rel_path).stat()
        row = cached.get(key)
        if (row and row["sha256"]
                and row["size"] == st.st_size and row["mtime"] == st.st_mtime):
            digest = bytes.fromhex(row["sha256"])
        else:
            file_digest = hashlib.sha256()
            with open(root / rel_path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            digest = file_digest.digest()
            upsert_file_hash(folder_path, key, st.st_size, st.st_mtime,
                             sha256=digest.hex(), db_path=db_path)
        tree_digest.update(rel_path.encode("utf-8", "surrogatepass"))
        tree_digest.update(digest)
    return tree_digest.hexdigest()


def prune_pipeline_cache(max_age_days: int = 180, db_path=None) -> dict:
    """Drop pipeline cache rows for missing folders and rows older than the cap.

    Phase-1 decision on design §10 open question 1: prune on demand (missing
    folder sweep + age cap, default 180 days). Not wired into startup yet —
    the tables stay empty until Phase 3/4 write to them; wiring is decided
    when consultation lands.

    Args:
        max_age_days: Delete rows whose hashed_at/updated_at is older.
        db_path: Optional DB path for the folder-list read.

    Returns:
        {"file_hash_deleted": int, "folder_state_deleted": int}
    """
    conn = get_connection(db_path)
    folders = {r[0] for r in conn.execute(
        "SELECT DISTINCT folder_path FROM pipeline_file_hash "
        "UNION SELECT folder_path FROM pipeline_folder_state"
    ).fetchall()}
    gone = [f for f in folders if not Path(f).is_dir()]
    age = f"-{int(max_age_days)} days"

    def _run(c):
        n_hash = n_state = 0
        for f in gone:
            n_hash += c.execute(
                "DELETE FROM pipeline_file_hash WHERE folder_path=?", (f,)
            ).rowcount
            n_state += c.execute(
                "DELETE FROM pipeline_folder_state WHERE folder_path=?", (f,)
            ).rowcount
        n_hash += c.execute(
            "DELETE FROM pipeline_file_hash WHERE hashed_at < datetime('now', ?)", (age,)
        ).rowcount
        n_state += c.execute(
            "DELETE FROM pipeline_folder_state WHERE updated_at < datetime('now', ?)", (age,)
        ).rowcount
        return {"file_hash_deleted": n_hash, "folder_state_deleted": n_state}

    return get_write_queue().execute(_run)


# --- Olof Björner surfacing (FABLE_OLOF_FILES.md P5a) ----------------------
#
# olof_* tables are local-only (not in MASTER_TABLES) — every reader here must
# degrade to empty results/None when the tables are empty or absent rather
# than raising, since a fresh import may not have run the olof scraper yet.

_OLOF_EVENT_COLUMNS = (
    "event_id, source, page_filename, event_type, date_str, date_raw, venue,"
    " city, region, country, tour_name, session_title, concert_no_net,"
    " concert_no_year, lineup, recording_info, recording_kind, recording_mins,"
    " notes, bobtalk, releases_raw, references_raw, updated_raw, raw_text"
)


def _olof_songs_for_events(conn: sqlite3.Connection, event_ids: list[int]) -> dict[int, list[dict]]:
    """Return ``{event_id: [song dict, ...]}`` ordered by position for *event_ids*."""
    if not event_ids:
        return {}
    placeholders = ",".join("?" * len(event_ids))
    rows = conn.execute(
        f"""SELECT event_id, position, song_title, credits, is_encore, take_number,
                   take_status, annotations, released_on
            FROM olof_songs WHERE event_id IN ({placeholders})
            ORDER BY event_id, position""",
        event_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {eid: [] for eid in event_ids}
    for r in rows:
        out[r["event_id"]].append({
            "position": r["position"],
            "song_title": r["song_title"],
            "credits": r["credits"],
            "is_encore": r["is_encore"],
            "take_number": r["take_number"],
            "take_status": r["take_status"],
            "annotations": r["annotations"],
            "released_on": r["released_on"],
        })
    return out


def get_olof_date(date_str: str, db_path=None) -> dict:
    """Return everything Olof Björner's corpus knows about a show date.

    Args:
        date_str: ISO ``yyyy-mm-dd`` show date.
        db_path: Optional path to the SQLite database file.

    Returns:
        dict with keys ``date_str``, ``events`` (each an olof_events row plus
        a nested ``songs`` list ordered by position), ``chronicle`` (matching
        olof_chronicle rows), and ``new_tapes`` (matching olof_new_tapes rows,
        circulation provenance). Every list is empty (never absent/404) when
        the olof tables have no data for this date.
    """
    conn = get_connection(db_path)
    events = conn.execute(
        f"SELECT {_OLOF_EVENT_COLUMNS} FROM olof_events WHERE date_str=? ORDER BY event_id",
        (date_str,),
    ).fetchall()
    songs_by_event = _olof_songs_for_events(conn, [r["event_id"] for r in events])
    events_out = []
    for r in events:
        d = dict(r)
        d["songs"] = songs_by_event.get(r["event_id"], [])
        events_out.append(d)
    chronicle = conn.execute(
        """SELECT year, seq, date_str, date_raw, entry_text FROM olof_chronicle
           WHERE date_str=? ORDER BY year, seq""",
        (date_str,),
    ).fetchall()
    new_tapes = conn.execute(
        """SELECT year, seq, title, date_str, body_text FROM olof_new_tapes
           WHERE date_str=? ORDER BY year, seq""",
        (date_str,),
    ).fetchall()
    return {
        "date_str": date_str,
        "events": events_out,
        "chronicle": [dict(r) for r in chronicle],
        "new_tapes": [dict(r) for r in new_tapes],
    }


def get_olof_event(event_id: int, db_path=None) -> dict | None:
    """Return one olof_events row with all columns and its ordered song list.

    Args:
        event_id: DSN event id (or synthetic chronicle-appendix id).
        db_path: Optional path to the SQLite database file.

    Returns:
        Event dict (all olof_events columns) with a nested ``songs`` list, or
        ``None`` if no such event exists.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        f"SELECT {_OLOF_EVENT_COLUMNS} FROM olof_events WHERE event_id=?", (event_id,)
    ).fetchone()
    if not row:
        return None
    event = dict(row)
    event["songs"] = _olof_songs_for_events(conn, [event_id]).get(event_id, [])
    return event


def get_olof_chronicle_year(year: int, db_path=None) -> list[dict]:
    """Return one chronicle year's entries in calendar (seq) order.

    Args:
        year: Chronicle year, e.g. 2002.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of olof_chronicle row dicts, ordered by ``seq``; empty if the
        year has no chronicle page parsed.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT year, seq, date_str, date_raw, entry_text FROM olof_chronicle
           WHERE year=? ORDER BY seq""",
        (year,),
    ).fetchall()
    return [dict(r) for r in rows]


_OLOF_LIKE_ESCAPE = "\\"


def _olof_like_pattern(q: str) -> str:
    """Escape ``%``/``_``/the escape char itself so *q* matches literally in LIKE."""
    escaped = (
        q.replace(_OLOF_LIKE_ESCAPE, _OLOF_LIKE_ESCAPE * 2)
        .replace("%", _OLOF_LIKE_ESCAPE + "%")
        .replace("_", _OLOF_LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


def _olof_snippet(text: str, q: str, context: int = 60) -> str:
    """Return ~*context* chars of *text* on either side of the first hit of *q*.

    Ellipsizes with ``…`` on whichever side(s) were truncated. Case-insensitive
    match; returns an empty string if *q* is not found (should not happen for
    rows the caller already matched via LIKE).
    """
    idx = text.lower().find(q.lower())
    if idx == -1:
        return ""
    start = max(0, idx - context)
    end = min(len(text), idx + len(q) + context)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def get_olof_bobtalk_search(q: str, limit: int = 50, db_path=None) -> list[dict]:
    """Case-insensitive substring search over olof_events.bobtalk and .notes.

    "Bob said something about X — which night was that?": lets the GUI find
    the show whose BobTalk or notes text mentions *q*, without a schema
    change or FTS5 (the table is small — 4,924 rows).

    Args:
        q: Search text. ``%``/``_`` are escaped so they match literally
           rather than as SQL LIKE wildcards.
        limit: Maximum number of hits to return, applied after ordering.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of hit dicts: ``{event_id, date_str, venue, city, country,
        event_type, concert_no_net, field, snippet}`` where ``field`` is
        ``'bobtalk'`` or ``'notes'``. A row that matches in both fields
        yields only the ``'bobtalk'`` hit (dedupe). Ordered with all
        ``'bobtalk'`` hits before ``'notes'`` hits, and ``date_str``
        ascending within each group. Empty list if *q* is blank.
    """
    q = (q or "").strip()
    if not q:
        return []
    like_pat = _olof_like_pattern(q)
    conn = get_connection(db_path)
    rows = conn.execute(
        f"""SELECT event_id, date_str, venue, city, country, event_type,
                   concert_no_net, bobtalk, notes
            FROM olof_events
            WHERE bobtalk LIKE ? ESCAPE '{_OLOF_LIKE_ESCAPE}'
               OR notes LIKE ? ESCAPE '{_OLOF_LIKE_ESCAPE}'
            ORDER BY date_str ASC""",
        (like_pat, like_pat),
    ).fetchall()

    q_lower = q.lower()
    bobtalk_hits: list[dict] = []
    notes_hits: list[dict] = []
    for r in rows:
        base = {
            "event_id": r["event_id"],
            "date_str": r["date_str"],
            "venue": r["venue"],
            "city": r["city"],
            "country": r["country"],
            "event_type": r["event_type"],
            "concert_no_net": r["concert_no_net"],
        }
        bobtalk = r["bobtalk"] or ""
        notes = r["notes"] or ""
        if q_lower in bobtalk.lower():
            bobtalk_hits.append({
                **base, "field": "bobtalk", "snippet": _olof_snippet(bobtalk, q),
            })
        elif q_lower in notes.lower():
            notes_hits.append({
                **base, "field": "notes", "snippet": _olof_snippet(notes, q),
            })
    return (bobtalk_hits + notes_hits)[:limit]


def get_olof_status(db_path=None) -> dict:
    """Return per-table row counts and the max DSN year, for GUI gating.

    The gui_next show-page panel hides Olof sections entirely when this
    reports zero rows, rather than rendering an empty/broken panel.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        dict: {pages, events, songs, chronicle_rows, new_tapes, chronicle_years,
        max_dsn_year}. ``max_dsn_year`` is the latest calendar year seen among
        DSN (non-chronicle-appendix) event dates, or None if olof_events is
        empty.
    """
    conn = get_connection(db_path)

    def _count(table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    max_year_row = conn.execute(
        """SELECT MAX(CAST(substr(date_str, 1, 4) AS INTEGER)) FROM olof_events
           WHERE source='dsn' AND date_str != ''"""
    ).fetchone()
    return {
        "pages": _count("olof_pages"),
        "events": _count("olof_events"),
        "songs": _count("olof_songs"),
        "chronicle_rows": _count("olof_chronicle"),
        "new_tapes": _count("olof_new_tapes"),
        "chronicle_years": conn.execute(
            "SELECT COUNT(DISTINCT year) FROM olof_chronicle"
        ).fetchone()[0] if _count("olof_chronicle") else 0,
        "max_dsn_year": max_year_row[0] if max_year_row else None,
    }


# --- Title normalization + setlist-vs-folder comparison (spec §5.1) --------

_TITLE_LEADING_THE_RE = re.compile(r"^the\s+")
_TITLE_NONWORD_RE = re.compile(r"[^a-z0-9\s]")
_TITLE_WS_RE = re.compile(r"\s+")

# Below this normalized length, a containment match is too easy to hit by
# accident (e.g. a one-word bogus title matching as a substring of many real
# titles) — require an exact match instead.
_TITLE_MIN_CONTAINMENT_LEN = 4
# The shorter normalized title must cover at least this fraction of the
# longer one for a containment match to count (guards against a short title
# trivially matching as a substring of an unrelated long one).
_TITLE_CONTAINMENT_RATIO = 0.6


def normalize_title_for_match(title: str) -> str:
    """Normalize a song title for cross-source matching (Olof vs folder/input).

    Reuses ``checksum_utils._APOSTROPHE_TRANS`` — the existing cp1252/EAC
    typographic-apostrophe fold used for filename matching — rather than
    re-deriving a curly-quote table. Pipeline: fold curly apostrophes to
    straight, lowercase, drop apostrophes outright (``Maggie's`` and
    ``Maggies`` must normalize identically), strip a leading "The ", replace
    remaining non-alphanumeric characters with a space, then collapse
    whitespace.

    Args:
        title: Raw song title text.

    Returns:
        Normalized comparison key; ``''`` for falsy input.
    """
    if not title:
        return ""
    t = title.translate(_APOSTROPHE_TRANS).lower()
    t = t.replace("'", "")
    t = _TITLE_LEADING_THE_RE.sub("", t)
    t = _TITLE_NONWORD_RE.sub(" ", t)
    return _TITLE_WS_RE.sub(" ", t).strip()


def titles_match(norm_a: str, norm_b: str) -> bool:
    """Whether two already-normalized titles should be treated as the same song.

    Exact match, or a conservative containment check (one is a substring of
    the other and covers at least ``_TITLE_CONTAINMENT_RATIO`` of its length)
    — titles are short enough that fuzzy edit-distance matching isn't needed,
    per FABLE_OLOF_FILES.md §5.1.

    Public (not module-private) because ``backend/setlist_fingerprint.py``
    (TODO-225) reuses it to score a folder tracklist against every Olof
    setlist, not just one date's — same matching rule, different caller.
    """
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    if len(shorter) < _TITLE_MIN_CONTAINMENT_LEN:
        return False
    return shorter in longer and len(shorter) >= _TITLE_CONTAINMENT_RATIO * len(longer)


_ENTRY_TRACK_MARKER_RE = re.compile(r"(?:^|[,\n])\s*(\d{1,3})[.)]?\s+(?=\S)")


def parse_entry_setlist_titles(setlist_text: str) -> list[str]:
    """Split an ``entries.setlist`` free-text tracklist into ordered titles.

    ``entries.setlist`` is scraped free text: numbered tracks ("1. Title",
    "01 Title") separated by commas or newlines, occasionally grouped under
    "Disc N," headers with per-disc numbering restarting at 1. A track marker
    is only recognized when its digits are preceded by a comma/newline (or
    text start) — this is what keeps a title like "Highway 61 Revisited" from
    being split on the embedded "61" (preceded by a letter, not a delimiter).

    Known limitation: a "Disc N:" / "Disc Two [37:20]" header between two
    tracks has no marker of its own, so it gets appended to the tail of the
    preceding title (e.g. "Honest With Me, Disc 2:"). Left uncorrected — the
    comparison endpoint's containment check still matches these against the
    clean Olof title in practice; callers needing a clean split should not
    rely on this for anything beyond best-effort comparison input.

    Args:
        setlist_text: Raw ``entries.setlist`` column value.

    Returns:
        Ordered list of title strings. May include non-song noise entries
        ("Disc 2:", "-encore break-", "band intro") verbatim; these simply
        won't match a real Olof title.
    """
    if not setlist_text:
        return []
    matches = list(_ENTRY_TRACK_MARKER_RE.finditer(setlist_text))
    titles: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(setlist_text)
        title = setlist_text[start:end].strip().strip(",").strip()
        if title:
            titles.append(title)
    return titles


def compare_olof_setlist(date_str: str, titles: list[str], db_path=None) -> dict:
    """Compare a folder's track titles against Olof's setlist for a date.

    Matches each input title against the date's Olof setlist (preferring a
    'concert' event when a date has more than one olof_events row) using
    :func:`normalize_title_for_match` + :func:`titles_match`. Matching is
    greedy per input title against not-yet-claimed Olof positions, order
    -independent — the folder's track order need not match Olof's.

    Args:
        date_str: ISO ``yyyy-mm-dd`` show date to compare against.
        titles: Input track titles, in any order.
        db_path: Optional path to the SQLite database file.

    Returns:
        dict: {date_str, olof_event_id (None if no Olof event for this date),
        olof_setlist: [{position, song_title}], matches: [{input_title,
        matched_position, matched_title}] (position/title None when unmatched),
        olof_missing: [song_title, ...] (Olof songs no input title matched),
        match_pct: percentage of the Olof setlist covered by a matched input
        title (0.0 when Olof has no event/songs for the date), recording_info,
        recording_kind, recording_mins}.
    """
    conn = get_connection(db_path)
    event = conn.execute(
        """SELECT event_id, recording_info, recording_kind, recording_mins
           FROM olof_events WHERE date_str=?
           ORDER BY (event_type != 'concert'), event_id LIMIT 1""",
        (date_str,),
    ).fetchone()
    if not event:
        return {
            "date_str": date_str,
            "olof_event_id": None,
            "olof_setlist": [],
            "matches": [
                {"input_title": t, "matched_position": None, "matched_title": None}
                for t in titles
            ],
            "olof_missing": [],
            "match_pct": 0.0,
            "recording_info": "",
            "recording_kind": "",
            "recording_mins": None,
        }

    songs = conn.execute(
        "SELECT position, song_title FROM olof_songs WHERE event_id=? ORDER BY position",
        (event["event_id"],),
    ).fetchall()
    olof_setlist = [{"position": s["position"], "song_title": s["song_title"]} for s in songs]
    olof_norm = [
        (s["position"], s["song_title"], normalize_title_for_match(s["song_title"]))
        for s in songs
    ]

    matched_positions: set[int] = set()
    matches = []
    for raw_title in titles:
        norm_in = normalize_title_for_match(raw_title)
        found = None
        for pos, song_title, norm_o in olof_norm:
            if pos in matched_positions:
                continue
            if titles_match(norm_in, norm_o):
                found = (pos, song_title)
                break
        if found:
            matched_positions.add(found[0])
            matches.append({
                "input_title": raw_title,
                "matched_position": found[0],
                "matched_title": found[1],
            })
        else:
            matches.append({
                "input_title": raw_title, "matched_position": None, "matched_title": None,
            })

    olof_missing = [s["song_title"] for s in songs if s["position"] not in matched_positions]
    match_pct = round(100.0 * len(matched_positions) / len(songs), 1) if songs else 0.0

    return {
        "date_str": date_str,
        "olof_event_id": event["event_id"],
        "olof_setlist": olof_setlist,
        "matches": matches,
        "olof_missing": olof_missing,
        "match_pct": match_pct,
        "recording_info": event["recording_info"] or "",
        "recording_kind": event["recording_kind"] or "",
        "recording_mins": event["recording_mins"],
    }


def resolve_lb_number_titles(lb_number: int, db_path=None) -> list[str] | None:
    """Resolve an lb_number's stored tracklist into titles for the compare endpoint.

    ``entries.setlist`` is the only per-entry stored tracklist text in the
    schema (``entry_files`` only has on-disk filenames, not song titles).
    Lets ``POST /api/olof/compare`` accept ``{lb_number}`` as an alternative
    to an explicit ``titles`` list.

    Args:
        lb_number: Catalog entry number.
        db_path: Optional path to the SQLite database file.

    Returns:
        Parsed title list (via :func:`parse_entry_setlist_titles`), or
        ``None`` if the entry doesn't exist or has no stored setlist text.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT setlist FROM entries WHERE lb_number=?", (lb_number,)
    ).fetchone()
    if not row or not row["setlist"]:
        return None
    return parse_entry_setlist_titles(row["setlist"])
