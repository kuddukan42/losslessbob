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
    "checksum_disputes",
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
    "tapematch_date_curation",
    "pipeline_file_hash",
    "pipeline_folder_state",
    "file_inventory",
    "file_integrity_scans",
    "song_canonical",
    "song_performances",
    "setlist_fingerprint_suggestions",
    "xref_ingest_filesets",
    "xref_ingest_rows",
    "user_taper_aliases",
    "qc_findings",
    "qc_decision_log",
    "qc_runs",
    "release_classifications",
    "corrections",
    "user_taper_flags",
    "taper_decision_log",
    "refresh_step_runs",
    "refresh_chain_runs",
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
    "refresh_version_taper_aliases",
    "refresh_version_ranker_scan_config",
    "refresh_version_ranker_rank_config",
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

CREATE INDEX IF NOT EXISTS idx_entries_date_location ON entries(date_str, location);

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

-- TODO-346: venue -> enwiki article cache. Filled offline by
-- tools/venue_wiki_lookup.py (Wikidata lookup by venue name + city, paced,
-- polite User-Agent) or by a curator override row; the dossier render path
-- (backend.dossier_fields.venue_wiki_link) only ever reads this table --
-- it never hits the network. A cached row with wiki_url NULL and
-- source='override' is an explicit "no link" override (a confident match
-- was checked for and isn't there), which is why wiki_url has no NOT NULL:
-- absence of a row means "not looked up yet", not "no link".
CREATE TABLE IF NOT EXISTS venue_wiki_links (
    venue_norm   TEXT NOT NULL,
    city_norm    TEXT NOT NULL,
    venue        TEXT,
    city         TEXT,
    wiki_title   TEXT,
    wiki_url     TEXT,
    source       TEXT NOT NULL,
    confidence   TEXT,
    note         TEXT,
    looked_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (venue_norm, city_norm)
);
CREATE INDEX IF NOT EXISTS idx_venue_wiki_source ON venue_wiki_links(source);

-- F7: date -> Bob Links tour-guide page URL, crawled offline by
-- tools/import_boblinks_index.py (boblinks.com's dates*.html / pre1995s.html guide
-- pages, followed politely -- sequential, 1s delay). The dossier's _build_xref
-- (backend.dossier._boblinks_url) only ever reads this table; a date with no row
-- renders "no Bob Links page for this date" rather than guessing a URL pattern
-- (probing showed the MMDDYYs.html guess 404s for some real dates).
CREATE TABLE IF NOT EXISTS boblinks_pages (
    date_iso  TEXT PRIMARY KEY,
    url       TEXT NOT NULL,
    found_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

-- Curator overrides on top of backend.db._NOT_TAPER (TODO-313), which is a
-- code-level frozenset and therefore un-editable from the UI. USER-tier, never
-- exported. Rows key on a *canonical* taper name, not an alias key:
--   'not_taper' — exclude this canonical from _TAPER_UNIVERSE. The parser still
--     collapses its spellings to one token (it stays a _KNOWN_TAPER_ALIASES
--     value), but the attribution engine will never seed it as a candidate.
--     This is the dolphinsmile/lk/jtt call — curator or transferer, not taper.
--   'is_taper' — the inverse: re-admit a canonical that the builtin _NOT_TAPER
--     excludes, for when a local curator disagrees with the shipped judgement.
-- Applied in reload_taper_aliases; see set_taper_flag / clear_taper_flag.
CREATE TABLE IF NOT EXISTS user_taper_flags (
    canonical   TEXT PRIMARY KEY,
    action      TEXT NOT NULL CHECK(action IN ('not_taper', 'is_taper')),
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS refresh_step_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id        TEXT NOT NULL,          -- refresh.STEPS step_id
    started_at     TIMESTAMP NOT NULL,     -- 'YYYY-MM-DD HH:MM:SS', naive local
    finished_at    TIMESTAMP,
    status         TEXT NOT NULL DEFAULT 'running',  -- running|ok|noop|stopped|error
    trigger_source TEXT,                   -- 'route' | 'cli' | 'cron'
    counters_json  TEXT,                   -- worker summary dict, verbatim
    notes          TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_step_runs_step
    ON refresh_step_runs(step_id, finished_at);

CREATE TABLE IF NOT EXISTS refresh_chain_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_kind   TEXT NOT NULL,          -- 'step' | 'trigger'
    scope_value  TEXT NOT NULL,          -- step_id or 'T1'
    started_at   TIMESTAMP NOT NULL,
    finished_at  TIMESTAMP,
    status       TEXT NOT NULL,          -- ok|partial|stopped|error
    steps_json   TEXT,                   -- the frozen plan + per-step outcome
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_chain_runs_started
    ON refresh_chain_runs(started_at);

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
    body_sha256     TEXT,       -- sha256 of the RAW HTTP body (HTML is rewritten on save,
                                -- so this does NOT match the file on disk for HTML)
    local_sha256    TEXT,       -- sha256 of the file AS SAVED — the mirror-integrity baseline
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
    auto_triage     TEXT,
    auto_triage_reasons TEXT,
    -- TODO-333: which tapematch calibration produced this family, carried
    -- through from observations.db runs.calibration_hash. NULL means the run
    -- predates the column, so the family's provenance is unknown rather than
    -- current. See tools/tapematch/tapematch/calibration.py.
    calibration_hash TEXT,
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
-- across recompute). See archive/specs/FABLE_TAPER_ATTRIBUTION.md + finding F2 in
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

-- taper_decision_log: append-only audit trail behind the /taper-review console
-- (TODO-312). The *decisions* themselves live in the MASTER-tier
-- `taper_confirmations` above — this is the local history of how they got there,
-- so it is USER-tier and never exported. Every write goes through
-- `taper_attribution.{confirm,reject,mark_unresolved,revert_decision}`, which
-- capture the pre-write `taper_confirmations` state in prev_action/prev_taper;
-- that pair is what makes a decision revertible without a full recompute.
CREATE TABLE IF NOT EXISTS taper_decision_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number         INTEGER NOT NULL,
    action            TEXT NOT NULL,      -- 'confirm'/'reject'/'unresolved'/'revert'
    taper_normalised  TEXT,               -- taper the decision applies to (NULL if none resolved)
    prev_action       TEXT,               -- taper_confirmations.action before this write
    prev_taper        TEXT,               -- NULL prev_action = no prior decision existed
    source            TEXT NOT NULL DEFAULT 'ui',  -- 'ui'/'bulk'/'cli'/'revert'
    note              TEXT,
    decided_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_taper_declog_lb ON taper_decision_log(lb_number, id DESC);

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

-- bobserve.com eventsperiod index rows, every year (dossier deep links to setlist?event=N)
CREATE TABLE IF NOT EXISTS bobserve_event_index (
    event_id    INTEGER PRIMARY KEY,             -- bobserve's ?event= id
    date_str    TEXT NOT NULL DEFAULT '',        -- '1963-10-26' ('1963-10-00' = month only)
    location    TEXT NOT NULL DEFAULT '',        -- 'New York, NY'
    venue       TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL DEFAULT '',        -- Concert | Soundcheck | Studio | ...
    indexed_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bobserve_event_index_date ON bobserve_event_index(date_str);

-- one row per event; joins to entries/bobdylan_shows/setlistfm_shows via date_str
--
-- The column bodies below carry NO comments on purpose: SQLite's ALTER TABLE
-- DROP COLUMN rewrites the stored CREATE text by deleting back through
-- whitespace to the end of the preceding token, and before 3.46 that let a
-- nearby `--` comment swallow the closing paren, leaving the table unreadable
-- ("incomplete input"). It broke CI on 2026-09-11. Column notes live here:
--   event_id          DSN number; appendix shows get year*1000+seq (e.g.
--                     2022017 -- no collision, DSN maxes ~5 digits)
--   source            dsn | chronicle_appendix
--   event_type        concert | session | rehearsal | broadcast | interview | other
--   date_str          ISO yyyy-mm-dd ('' if unparsed)
--   tour_name         from DSN segment title / chronicle tour section
--   session_title     'The 3rd Blonde On Blonde session, produced by ...'
--   concert_no_net    'Concert # 186 of The Never-Ending Tour'
--   concert_no_year   '1990 concert # 16'
--   recording_info    'Stereo audience recording, 100 minutes.'
--   recording_kind    audience | soundboard | studio | broadcast | ''
--   updated_raw       'Session info updated 6 February 2001'
--   raw_text          full block plain text (search + reparse safety net)
-- Dossier redesign Phase 1 (TODO-342); NULL/'' on bobserve rows. Also added by
-- init_db's migration, so this order matches a migrated DB:
--   rotation_new      'N new songs (P%) compared to previous concert'
--   rotation_pct      the P of that line
--   tour_new_count    'N new songs for this tour'
--   venue_history_raw 'Other Bob Dylan shows in X:' blob, out of notes
CREATE TABLE IF NOT EXISTS olof_events (
    event_id        INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT '',
    page_filename   TEXT NOT NULL REFERENCES olof_pages(filename),
    event_type      TEXT NOT NULL DEFAULT '',
    date_str        TEXT NOT NULL DEFAULT '',
    date_raw        TEXT NOT NULL DEFAULT '',
    venue           TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    region          TEXT NOT NULL DEFAULT '',
    country         TEXT NOT NULL DEFAULT '',
    tour_name       TEXT NOT NULL DEFAULT '',
    session_title   TEXT NOT NULL DEFAULT '',
    concert_no_net  INTEGER,
    concert_no_year INTEGER,
    lineup          TEXT NOT NULL DEFAULT '',
    recording_info  TEXT NOT NULL DEFAULT '',
    recording_kind  TEXT NOT NULL DEFAULT '',
    recording_mins  INTEGER,
    notes           TEXT NOT NULL DEFAULT '',
    bobtalk         TEXT NOT NULL DEFAULT '',
    releases_raw    TEXT NOT NULL DEFAULT '',
    references_raw  TEXT NOT NULL DEFAULT '',
    updated_raw     TEXT NOT NULL DEFAULT '',
    raw_text        TEXT NOT NULL DEFAULT '',
    rotation_new      INTEGER,
    rotation_pct      INTEGER,
    tour_new_count    INTEGER,
    venue_history_raw TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_olof_events_date ON olof_events(date_str);
CREATE INDEX IF NOT EXISTS idx_olof_events_tour ON olof_events(tour_name);

-- one row per performed song / studio take (TODO-162 P3, FABLE_OLOF_FILES.md S4)
-- Comment-free body for the DROP COLUMN reason documented on olof_events above.
--   credits      cover writer(s) from parens
--   take_number  studio rows only
--   take_status  complete | breakdown | rehearsal | false start | incomplete
--   annotations  'acoustic w band', 'harmonica', ...
--   released_on  release titles resolved from position ranges, '; '-joined;
--                '(part) ' / '(uncertain) ' prefixes
--   subtitle     parenthetical alternate title, not a credit (TODO-342)
CREATE TABLE IF NOT EXISTS olof_songs (
    event_id     INTEGER NOT NULL REFERENCES olof_events(event_id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    song_title   TEXT NOT NULL DEFAULT '',
    credits      TEXT NOT NULL DEFAULT '',
    is_encore    INTEGER NOT NULL DEFAULT 0,
    take_number  INTEGER,
    take_status  TEXT NOT NULL DEFAULT '',
    annotations  TEXT NOT NULL DEFAULT '',
    released_on  TEXT NOT NULL DEFAULT '',
    subtitle     TEXT NOT NULL DEFAULT '',
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

-- ── Collection Integrity Monitor (TODO-284) ────────────────────────────────
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

-- ── File-level integrity inventory (TODO-267) ──────────────────────────────
-- Durable per-file hash record for EVERY file under a collection mount — not a
-- stat-keyed cache like pipeline_file_hash. Bit rot does not touch mtime, so a
-- cache that skips on matching (size, mtime) can never detect it; this table
-- keeps the hash so a later full re-read can be compared against it.
-- Both hashes come from ONE read pass: xxh3_128 is the rot workhorse, sha256
-- exists to cross-check findings against `checksums` / lbdir manifests /
-- site_inventory.local_sha256. Reads are ~181 MB/s, both hashes >2 GB/s, so
-- the second digest is free.
CREATE TABLE IF NOT EXISTS file_inventory (
    mount_id      INTEGER NOT NULL REFERENCES collection_mounts(id) ON DELETE CASCADE,
    rel_path      TEXT NOT NULL,      -- posix-style, relative to mounts.root_path
    lb_number     INTEGER,            -- owning LB folder, when resolvable
    size          INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    xxh3          TEXT NOT NULL,      -- xxh3_128 hex — primary rot detector
    sha256        TEXT,               -- interop digest (nullable for old rows)
    status        TEXT NOT NULL DEFAULT 'ok',  -- ok|rot|changed|missing|unreadable
    first_seen    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_hashed   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- content last read
    last_verified TIMESTAMP,          -- last deep verify that MATCHED (drives rolling)
    PRIMARY KEY (mount_id, rel_path)
);
-- Rolling deep-verify picks the oldest last_verified first; NULLs sort first in
-- SQLite ASC, so never-verified files are naturally at the head of the queue.
CREATE INDEX IF NOT EXISTS idx_finv_verify ON file_inventory(mount_id, last_verified);
CREATE INDEX IF NOT EXISTS idx_finv_status ON file_inventory(status) WHERE status != 'ok';
CREATE INDEX IF NOT EXISTS idx_finv_lb ON file_inventory(lb_number);
CREATE INDEX IF NOT EXISTS idx_finv_sha ON file_inventory(sha256);
-- Move detection (TODO-297): find an existing ok row for a hash before
-- declaring the rel_path it used to live at missing.
CREATE INDEX IF NOT EXISTS idx_finv_xxh3_ok ON file_inventory(xxh3) WHERE status = 'ok';

CREATE TABLE IF NOT EXISTS file_integrity_scans (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    mount_id         INTEGER REFERENCES collection_mounts(id) ON DELETE CASCADE,
    mode             TEXT NOT NULL,   -- index | verify
    status           TEXT NOT NULL DEFAULT 'running',
    started_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMP,
    files_seen       INTEGER DEFAULT 0,
    files_hashed     INTEGER DEFAULT 0,
    files_new        INTEGER DEFAULT 0,
    files_ok         INTEGER DEFAULT 0,
    files_rot        INTEGER DEFAULT 0,
    files_changed    INTEGER DEFAULT 0,
    files_missing    INTEGER DEFAULT 0,
    files_moved      INTEGER DEFAULT 0,
    files_unreadable INTEGER DEFAULT 0,
    bytes_hashed     INTEGER DEFAULT 0,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS idx_fiscans_mount
    ON file_integrity_scans(mount_id, started_at DESC);

-- ── Concert Ranker (audio quality) — USER-tier derived data ──────────────────
-- Quality data is the user's own analysis of their own copies. RAW aggregated
-- metrics (quality_recording_metrics.metric_json) are stored separately from the
-- derived scores so re-banding/re-ranking never needs an audio rescan.
CREATE TABLE IF NOT EXISTS quality_scans (
    scan_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_json    TEXT,
    notes          TEXT,
    -- Hash of the extraction-relevant config only (TODO-311). Scans sharing a
    -- key hold interchangeable measurements, so a backlog run appends to one
    -- instead of re-measuring the corpus after a scoring-only config change.
    extraction_key TEXT
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
    event_id         INTEGER,              -- olof_events show ranked (C32 D3); NULL if none
    PRIMARY KEY (concert_date, lb_number, event_id)
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

-- ── TapeMatch date curation (USER — the curator accepted a date's families) ───
-- Written by POST /api/tapematch/dates/accept, the curation screen's §3
-- `Accept families`; read back as the `curated` state on GET
-- /api/tapematch/dates. One row per date, replaced on re-accept.
--
-- Deliberately in the app DB rather than tools/tapematch/observations.db, even
-- though the pair-level `human_judgment` it summarises lives there: this is the
-- curator's own verdict, nothing in the tapematch pipeline reads it, and
-- observations.db is write-locked for hours by the nightly analysis runs — an
-- accept must never fail because a batch is mid-flight. `n_judged` is a
-- snapshot of how many of the date's pairs were judged at accept time (counted
-- server-side from observations.db), kept for provenance; the live count is
-- always recomputed from the pairs themselves.
CREATE TABLE IF NOT EXISTS tapematch_date_curation (
    concert_date TEXT PRIMARY KEY,
    run_id       TEXT,                 -- run accepted (a rerun can move it)
    accepted_at  TEXT NOT NULL,        -- ISO-8601 UTC
    n_judged     INTEGER,              -- pairs with a human_judgment at accept time
    n_families   INTEGER,              -- runs.n_families for the accepted run
    note         TEXT
);

-- ── WTRF Torrent Downloads (USER — fetch attempts for missing items) ──────────
CREATE TABLE IF NOT EXISTS wtrf_downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    topic_url    TEXT,
    torrent_path TEXT,
    confidence   TEXT,    -- 'definitive'/'high'/'medium'/'needs_review'/'ambiguous'/'not_found'
    signals_json TEXT,    -- JSON scoring details
    status       TEXT NOT NULL DEFAULT 'pending',
                 -- 'pending'/'downloaded'/'qbt_added'/'not_seeded'/'failed'/'skipped'
                 -- 'not_seeded' = fetched but refused a seed (not public, no
                 -- matching folder, or the folder is not 100% complete)
    error        TEXT,
    seed_folder  TEXT,   -- folder handed to qBittorrent (collection or overlay)
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

-- LB catalogue snapshot history (TODO-305): one row per master-snapshot import,
-- written by import_master_db(). Feeds GET /api/lb/snapshots and the
-- /lbdir/sync screen, which is the only place the per-update diff is visible —
-- the meta table only ever holds the *current* master_version.
CREATE TABLE IF NOT EXISTS lb_snapshot_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    master_version      TEXT,
    master_published_at TEXT,
    imported_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source              TEXT,           -- 'github' | 'file' | 'unknown'
    entries_total       INTEGER,        -- lb_master rows after the import
    entries_held        INTEGER,        -- of those, in my_collection
    entries_added       INTEGER,        -- lb_master delta vs the previous row
    lb_status_changes   INTEGER,
    status_counts_json  TEXT,           -- post-import lb_status histogram
    row_counts_json     TEXT,           -- rows written per master table
    backup_path         TEXT
);
CREATE INDEX IF NOT EXISTS idx_lb_snapshot_hist_at ON lb_snapshot_history(imported_at DESC);

-- ── TUIT tracker mirror (USER — scraped catalogue of tangledupintorrents.org) ─
-- One row per site recording id. Every field the site renders is kept, so the
-- data can be compared against lb_master later without a re-crawl; list-shaped
-- fields (lineage nodes, setlist, file list, sibling sources) are JSON blobs.
CREATE TABLE IF NOT EXISTS tuit_recordings (
    rec_id          INTEGER PRIMARY KEY,   -- site /recordings/<id>
    show_id         INTEGER,               -- site /shows/<id>
    lb_number       INTEGER,
    detail_url      TEXT,
    title           TEXT,                  -- 'Providence, Civic Center'
    eyebrow         TEXT,                  -- '7 Oct 1978 · Street Legal Tour · Audience'
    headline        TEXT,                  -- 'Source 1 of 2 circulating for this show…'
    date_str        TEXT,
    venue           TEXT,
    location        TEXT,
    tour            TEXT,
    source_type     TEXT,                  -- AUD / SBD / FM / MTX
    source_label    TEXT,                  -- 'Audience', 'Soundboard', …
    format          TEXT,                  -- 'FLAC 16/44'
    quality         TEXT,                  -- 'Very good'
    quality_slug    TEXT,                  -- 'very-good'
    info_hash       TEXT,
    size_label      TEXT,
    size_bytes      INTEGER,
    n_files         INTEGER,
    n_sources       INTEGER,
    seeders         INTEGER,
    leechers        INTEGER,
    snatched        INTEGER,
    freeleech       INTEGER DEFAULT 0,
    lb_verified     INTEGER DEFAULT 0,
    taper           TEXT,
    uploader        TEXT,
    uploader_url    TEXT,
    uploaded_label  TEXT,
    added_at        TEXT,                  -- ISO-8601 from the listing <time>
    lineage         TEXT,                  -- ' > '-joined lineage chain
    lineage_json    TEXT,
    info_text       TEXT,                  -- the recording's info-file body
    setlist_json    TEXT,
    files_json      TEXT,
    siblings_json   TEXT,
    spectrogram_url TEXT,
    preview_url     TEXT,
    torrent_url     TEXT,
    first_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tuit_rec_lb   ON tuit_recordings(lb_number);
CREATE INDEX IF NOT EXISTS idx_tuit_rec_hash ON tuit_recordings(info_hash);
CREATE INDEX IF NOT EXISTS idx_tuit_rec_date ON tuit_recordings(date_str);
CREATE INDEX IF NOT EXISTS idx_tuit_rec_seen ON tuit_recordings(added_at DESC);

-- Fetch/seed attempts against TUIT (USER). Mirrors wtrf_downloads.
CREATE TABLE IF NOT EXISTS tuit_downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_id       INTEGER NOT NULL,
    lb_number    INTEGER,
    torrent_path TEXT,
    seed_folder  TEXT,     -- collection folder matched via folder_lb_link
    status       TEXT NOT NULL DEFAULT 'pending',
                 -- 'pending'/'downloaded'/'qbt_added'/'not_seeded'/'failed'
                 -- 'not_seeded' = fetched but refused a seed (not public, no
                 -- matching folder, or the folder is not 100% complete)
    error        TEXT,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    qbt_added_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tuit_dl_rec
    ON tuit_downloads(rec_id, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_tuit_dl_status
    ON tuit_downloads(status, attempted_at DESC);

-- Outbound counterpart of tuit_downloads (USER): one row per attempt to post a
-- recording to TUIT's /upload form. 'prepared' rows are dry runs — the payload
-- was composed and the torrent built, but nothing was POSTed. info_hash is the
-- duplicate key a later attempt checks against tuit_recordings.
CREATE TABLE IF NOT EXISTS tuit_uploads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    rec_id       INTEGER,              -- /recordings/<id> once the POST lands
    info_hash    TEXT,
    torrent_path TEXT,
    show_id      INTEGER,
    source_folder TEXT,
    payload_json TEXT,                 -- the exact form fields sent
    status       TEXT NOT NULL DEFAULT 'prepared',
                 -- 'prepared'/'uploaded'/'seeded'/'rejected'/'failed'
    error        TEXT,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_at  TIMESTAMP,
    seeded_at    TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tuit_up_lb
    ON tuit_uploads(lb_number, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_tuit_up_status
    ON tuit_uploads(status, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_tuit_up_hash ON tuit_uploads(info_hash);

-- TUIT's live-history spine: every show the tracker knows about, circulating
-- or not (LOCAL). Scraped from /tour/<name>; keyed by (date, venue) because a
-- gap row links to /shows/<id> while a circulating row links to a recording,
-- so no single site id spans the table.
CREATE TABLE IF NOT EXISTS tuit_shows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date_str      TEXT NOT NULL,          -- ISO 'YYYY-MM-DD'
    venue         TEXT NOT NULL,
    location      TEXT,
    tour          TEXT,
    row_url       TEXT,
    rec_id        INTEGER,                -- top /recordings/<id>, when taped
    show_id       INTEGER,                -- /shows/<id>, set on gap rows
    circulating   INTEGER DEFAULT 0,      -- 0 = TUIT has no tape for this show
    in_collection INTEGER DEFAULT 0,      -- the site's own "in your collection"
    has_sbd       INTEGER DEFAULT 0,
    has_aud       INTEGER DEFAULT 0,
    seeders       INTEGER,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date_str, venue)
);
CREATE INDEX IF NOT EXISTS idx_tuit_shows_date ON tuit_shows(date_str);
CREATE INDEX IF NOT EXISTS idx_tuit_shows_tour ON tuit_shows(tour);
CREATE INDEX IF NOT EXISTS idx_tuit_shows_circ ON tuit_shows(circulating);

-- TUIT's venue register (LOCAL), scraped from /venue. Venue names repeat
-- across cities, so the key is (venue, city, country).
CREATE TABLE IF NOT EXISTS tuit_venues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    venue         TEXT NOT NULL,
    city          TEXT,
    country       TEXT,
    year_first    INTEGER,
    year_last     INTEGER,
    n_shows       INTEGER,
    venue_url     TEXT,
    source        TEXT DEFAULT 'register',  -- 'register' | 'shows' (backfill)
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue, city, country)
);
CREATE INDEX IF NOT EXISTS idx_tuit_venues_name ON tuit_venues(venue);

-- TUIT's songbook (LOCAL), scraped from /songs. The index's own performance
-- count is kept alongside the rows actually listed on the song page: the two
-- disagree on the site itself (All Along The Watchtower is 2,285 vs 2,252).
CREATE TABLE IF NOT EXISTS tuit_songs (
    song           TEXT PRIMARY KEY,
    song_url       TEXT,
    n_performances INTEGER,          -- as advertised by the /songs index
    n_listed       INTEGER,          -- rows actually parsed off /song/<title>
    year_first     INTEGER,
    year_last      INTEGER,
    scraped_at     TIMESTAMP,        -- set when the song page itself was read
    first_seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-performance rows from /song/<title> (LOCAL). n_sources is the tracker's
-- circulating-source count for that night, and note is its lineup annotation
-- ('Bob on electric keyboard') — neither exists in the Olof-derived spine.
-- show_id is part of the key: a date can hold an afternoon and an evening show
-- whose rendered venue_text is identical, and only the show id separates them.
CREATE TABLE IF NOT EXISTS tuit_song_performances (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    song          TEXT NOT NULL,
    date_str      TEXT NOT NULL,     -- ISO 'YYYY-MM-DD'
    venue_text    TEXT,              -- 'Venue — City, Country' as rendered
    show_id       INTEGER,
    n_sources     INTEGER,           -- NULL when nothing circulates
    is_encore     INTEGER DEFAULT 0,
    note          TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song, date_str, venue_text, show_id)
);
CREATE INDEX IF NOT EXISTS idx_tuit_sperf_song ON tuit_song_performances(song);
CREATE INDEX IF NOT EXISTS idx_tuit_sperf_date ON tuit_song_performances(date_str);
CREATE INDEX IF NOT EXISTS idx_tuit_sperf_show ON tuit_song_performances(show_id);

-- Dossier redesign Phase 2 (TODO-342): QC findings, decisions, runs, and
-- curator-supplied corrections/classifications. All five tables are USER-tier
-- (see USER_TABLES above) — they hold locally-computed findings and this
-- install's curator decisions, never exported in master data. See
-- instructions/SHOW_DOSSIER_REDESIGN_PLAN.md "Phase 2" for the rule engine and
-- "Decision vocabulary" for the status state machine that backend/qc/store.py
-- implements against qc_findings.status.
CREATE TABLE IF NOT EXISTS qc_findings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id        TEXT NOT NULL,
    entity_kind    TEXT NOT NULL,
    entity_key     TEXT NOT NULL,
    severity       TEXT NOT NULL,      -- error | warn | info
    detail         TEXT NOT NULL DEFAULT '',
    evidence_json  TEXT NOT NULL DEFAULT '{}',
    evidence_hash  TEXT NOT NULL DEFAULT '',
    first_seen     TEXT NOT NULL,      -- UTC ISO 8601
    last_seen      TEXT NOT NULL,      -- UTC ISO 8601
    status         TEXT NOT NULL DEFAULT 'open',  -- open|confirmed|false_positive|corrected|fixed
    decided_by     TEXT,
    decided_at     TEXT,
    note           TEXT,
    UNIQUE(rule_id, entity_kind, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_qc_findings_status ON qc_findings(status, severity);

-- qc_decision_log: append-only audit trail behind /qc-review, mirroring
-- taper_decision_log above. Every status transition the run engine or a
-- curator makes gets a row here; qc_findings itself only ever holds current
-- state.
CREATE TABLE IF NOT EXISTS qc_decision_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id    INTEGER NOT NULL REFERENCES qc_findings(id) ON DELETE CASCADE,
    rule_id       TEXT NOT NULL,
    entity_key    TEXT NOT NULL,
    prev_status   TEXT,
    new_status    TEXT NOT NULL,
    note          TEXT,
    decided_by    TEXT NOT NULL DEFAULT 'qc-run',  -- 'qc-run'/'ui'/'bulk'/'cli'
    decided_at    TEXT NOT NULL      -- UTC ISO 8601
);
CREATE INDEX IF NOT EXISTS idx_qc_declog_finding ON qc_decision_log(finding_id, id DESC);

-- qc_runs: one row per rule invocation, for the /qc-review trend lines.
CREATE TABLE IF NOT EXISTS qc_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id      TEXT NOT NULL,
    started_at   TEXT NOT NULL,       -- UTC ISO 8601
    finished_at  TEXT NOT NULL,       -- UTC ISO 8601
    n_open       INTEGER NOT NULL DEFAULT 0,
    n_new        INTEGER NOT NULL DEFAULT 0,
    n_fixed      INTEGER NOT NULL DEFAULT 0,
    n_reopened   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_qc_runs_rule ON qc_runs(rule_id, run_id DESC);

-- release_classifications: curator verdicts on release titles (R-R1). D-03
-- reads the asset allowlist plus this table, and this table wins.
CREATE TABLE IF NOT EXISTS release_classifications (
    title_key   TEXT PRIMARY KEY,
    official    INTEGER NOT NULL DEFAULT 0,
    decided_by  TEXT,
    decided_at  TEXT,
    note        TEXT
);

-- corrections: curator-supplied field overrides from the /qc-review
-- correction form. Source tables are never edited in place — a dossier field
-- with an open 'corrected' finding renders this value instead, with a
-- tooltip showing the original.
CREATE TABLE IF NOT EXISTS corrections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_kind  TEXT NOT NULL,
    entity_key   TEXT NOT NULL,
    field        TEXT NOT NULL,
    original     TEXT,
    corrected    TEXT,
    reason       TEXT,
    decided_by   TEXT,
    decided_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_corrections_entity ON corrections(entity_kind, entity_key, field);
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


_SERIES_CANONICAL_RE = re.compile(r'^(?:lt[a-z]|net taper [a-z])$')
# A taper phrase directly before a series code binds it ("taped by nti",
# "Source: LTB", "Taper=LTA", "Carsten reports this to be NTF", "matches to NTD").
# "same recording as LTD" binds too -- it names the tape this one is.
# Comparison words ("as", "than", "vs", "different from") are deliberately absent.
_SERIES_BINDING_PREFIX_RE = re.compile(
    r'(?:\b(?:taped|recorded|recording|source|taper|lineage|master|by|be|is|reports?|aka|'
    r'match(?:es)?(?:\s+to)?|identified\s+as|(?:is|are)\s+from|'
    r'same\s+(?:recording|source|tape|transfer)\s+as)\b|=)'
    r'[\s:=\-–>,"\'(]*(?:(?:the|an?)\s+)?$',
    re.IGNORECASE,
)
# The spelled-out label form "Net Taper: I" / "Net Taper - F".
_NET_TAPER_LABEL_RE = re.compile(r'\bnet\s*taper\s*[:\-#]\s*([a-z])\b', re.IGNORECASE)
# What may precede a series code that "starts the lineage": nothing, or a
# version tag ('version "b";'), within the code's own line.
_SERIES_LEAD_RE = re.compile(r'^[\s(\["\'*]*(?:version\s*"?\w{1,3}"?\s*[;,:]\s*)?$', re.IGNORECASE)


def _series_code_bound(text: str, m: re.Match) -> bool:
    """Whether a series-code match in *text* is a credit rather than a passing mention.

    Bound when the matched alias spells out "taper" itself ("net taper i",
    "legendary taper b"), when a taper phrase sits directly before it, or when
    it starts the lineage -- the first thing on its line, optionally after a
    version tag, or a bare comma-separated item early in the header line.

    Args:
        text: The scanned description window.
        m: A match whose group 1 is the series-code alias.

    Returns:
        True when the code should be read as the taper credit.
    """
    if 'taper' in m.group(1).lower():
        return True
    before = text[max(0, m.start() - 40):m.start()]
    if _SERIES_BINDING_PREFIX_RE.search(before):
        return True
    line_start = text.rfind('\n', 0, m.start()) + 1
    if _SERIES_LEAD_RE.match(text[line_start:m.start()]):
        return True
    # A bare comma-list item early in the header line ("Off DAT clone(s), LTF, Source").
    return (line_start == 0 and m.start() < 80
            and bool(re.search(r'[,;]\s*$', text[:m.start()]))
            and bool(re.match(r'\s*[,;]', text[m.end():])))


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
    # A series code (lta-ltz, nta-ntz) only counts when it is bound to a taper
    # phrase or starts the lineage (plan E4: "not as warm as nti" is a comparison
    # with another source, not a credit); unbound ones are skipped, not fatal.
    for m0 in _KNOWN_TAPER_RE.finditer(d600):
        raw_h = m0.group(1)
        norm_h = _normalise_alias_key(raw_h)
        canonical = _KNOWN_TAPER_ALIASES.get(norm_h, raw_h)
        if _SERIES_CANONICAL_RE.match(canonical) and not _series_code_bound(d600, m0):
            continue
        taper_name = canonical
        break
    if not taper_name:
        m_nt = _NET_TAPER_LABEL_RE.search(d600)
        if m_nt:
            taper_name = f"net taper {m_nt.group(1).lower()}"
    if not taper_name:
        for m_lt in _LT_TAPER_RE.finditer(d600):
            if _series_code_bound(d600, m_lt):
                taper_name = m_lt.group(1).lower()
                break

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
    r'not\s+the\s+same|'
    # Golden review 3 (LB-14054): "Alternate to LB-2470/..." names a different
    # recording, even when it goes on to say the others share one source.
    r'\balternat(?:e|ive)\s+(?:recording\s+|source\s+|version\s+)?to\b',
    re.IGNORECASE,
)
_LB_REF_RE = re.compile(r'\bLB-0*(\d+)\b', re.IGNORECASE)
# Sentence boundary for binding a same/different phrase to the LB refs it talks
# about. LB descriptions join fields with ", ", so commas are NOT boundaries.
_REF_SENTENCE_SPLIT_RE = re.compile(r';|\.\s|\n\s*\n')
# A ref introduced as this set's own LB entry, an earlier version or the entry it
# fixes names the same recording ("LosslessBob entry: LB-2710", "Fix of LB-7948",
# "Previous version = LosslessBob LB-201"). Checked on the text right before the ref.
_SAME_REF_LEAD_RE = re.compile(
    r'(?:LosslessBob\s+entry(?:\s+for\s+lineage\s+above)?\s*[:=]?|'
    r'\bfix(?:ed)?(?:\s+of)?|previous\s+version\s*=|previos\s+version\s*=|'
    r'corrected\s+version\s+of)\s*(?:LosslessBob\s*-?\s*)?$',
    re.IGNORECASE,
)
# "recorded by" / "recording by" are explicit credits too (plan E5), but only
# when bound to the parsed handle -- taper_attribution._layer0_seed checks that
# binding for these two forms (and for "a <handle> recording", which no static
# regex can express) rather than trusting a match anywhere in the text.
_EXPLICIT_TAPER_LABEL_RE = re.compile(
    r'\bTaper\s*:|\btaped\b[\w\s,]{0,40}?\bby\b|\brecord(?:ed|ing)\s+by\b', re.IGNORECASE,
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
    # Self-stated "Taper: 3dogs" on 21 entries, one rig throughout (tj, 2026-10-01).
    "3dogs": "3dogs",
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
    # Travelin' Man Records is Legendary Taper F's own handle: entries read "Taper F
    # (Travelin' Man Records)", and crediting it separately made every LTF family that
    # also holds a TMR-credited copy a false R-T6 taper conflict (TODO-357).
    "travelin man records": "ltf",
    "travelin man": "ltf",
    "tmr": "ltf",
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

def _run_queued_write(fn, db_path: str | None, label: str = "write"):
    """Route a write through the write queue, matching the BUG-246 guard used
    elsewhere (taper_attribution.py, song_index.py, xref_ingest.py): the write
    queue singleton is first-caller-wins, so under pytest (each test module's
    own temp DB) it may be bound to a different DB than *db_path*.

    Args:
        fn: Callable taking a ``sqlite3.Connection`` and performing the write.
        db_path: Optional database path the caller intended to target.
        label: Short description used only in the mismatch warning log.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        logger.warning(
            "%s: write queue bound to %s but this write targets %s"
            " — writing directly", label, queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _run_alias_write(fn, db_path: str | None):
    """Route a user_taper_aliases write through the write queue (see
    :func:`_run_queued_write`)."""
    return _run_queued_write(fn, db_path, label="user_taper_aliases")


def record_step_run(
    step_id: str, *, status: str = "ok",
    started_at: str | None = None, finished_at: str | None = None,
    counters: dict | None = None, notes: str | None = None,
    trigger_source: str = "route", db_path: str | None = None,
) -> int:
    """Insert one completed ``refresh_step_runs`` row (TODO-306).

    One insert at completion, not a start/finish pair: "currently running" is
    already fully covered by ``activity.snapshot()``, and a single insert
    avoids carrying a rowid across a thread boundary and avoids orphan
    ``running`` rows after a crash.

    Args:
        step_id: ``refresh.STEPS`` step id this run corresponds to.
        status: One of ``ok | noop | stopped | error``.
        started_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to
            ``finished_at`` (or now) when omitted.
        finished_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to now.
        counters: Worker summary dict, stored verbatim as JSON.
        notes: Optional free-text note (e.g. a version-change reason).
        trigger_source: ``route | cli | cron``.
        db_path: Optional database path override.

    Returns:
        The new row's id.
    """
    finished = finished_at or time.strftime("%Y-%m-%d %H:%M:%S")
    started = started_at or finished
    counters_json = json.dumps(counters) if counters is not None else None

    def _do(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """INSERT INTO refresh_step_runs
                   (step_id, started_at, finished_at, status, trigger_source,
                    counters_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (step_id, started, finished, status, trigger_source, counters_json, notes),
        )
        return cur.lastrowid

    return _run_queued_write(_do, db_path, label="refresh_step_runs")


def record_chain_run(
    scope_kind: str, scope_value: str, *, status: str,
    started_at: str | None = None, finished_at: str | None = None,
    steps: list | dict | None = None, notes: str | None = None,
    db_path: str | None = None,
) -> int:
    """Insert one completed ``refresh_chain_runs`` row (Phase 3).

    One insert at completion, mirroring :func:`record_step_run`: the frozen
    plan plus per-step outcomes are the history record, while
    ``refresh_step_runs`` remains the authoritative freshness signal.

    Args:
        scope_kind: ``'step'`` or ``'trigger'``.
        scope_value: The step id or trigger id (e.g. ``'T1'``) the chain
            was planned against.
        status: One of ``ok | partial | stopped | error``.
        started_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to
            ``finished_at`` (or now) when omitted.
        finished_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to now.
        steps: The frozen plan plus per-step outcome, stored verbatim as JSON.
        notes: Optional free-text note.
        db_path: Optional database path override.

    Returns:
        The new row's id.
    """
    finished = finished_at or time.strftime("%Y-%m-%d %H:%M:%S")
    started = started_at or finished
    steps_json = json.dumps(steps) if steps is not None else None

    def _do(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """INSERT INTO refresh_chain_runs
                   (scope_kind, scope_value, started_at, finished_at, status,
                    steps_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scope_kind, scope_value, started, finished, status, steps_json, notes),
        )
        return cur.lastrowid

    return _run_queued_write(_do, db_path, label="refresh_chain_runs")


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

    # Curator overrides on the code-level _NOT_TAPER set (TODO-313). 'not_taper'
    # rows exclude extra canonicals; 'is_taper' rows re-admit builtin-excluded
    # ones. Applied after the subtraction so an 'is_taper' row always wins over
    # the shipped judgement — a local curator's explicit call beats a default.
    flag_rows = conn.execute(
        "SELECT canonical, action FROM user_taper_flags"
    ).fetchall()
    user_not = {r["canonical"] for r in flag_rows if r["action"] == "not_taper"}
    user_is = {r["canonical"] for r in flag_rows if r["action"] == "is_taper"}

    global _TAPER_UNIVERSE, _KNOWN_TAPER_KEYS_SORTED, _KNOWN_TAPER_RE
    _TAPER_UNIVERSE = (
        (frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER - user_not) | user_is
    )
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
        "universe": len(_TAPER_UNIVERSE),
        "user_not_taper": len(user_not),
        "user_is_taper": len(user_is),
    }
    logger.info(
        "reload_taper_aliases: builtin=%(builtin)d user_add=%(user_add)d "
        "user_remove=%(user_remove)d merged=%(merged)d universe=%(universe)d "
        "user_not_taper=%(user_not_taper)d user_is_taper=%(user_is_taper)d", counts,
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


# ── Master taper vocabulary curation (TODO-313) ───────────────────────────────
# The alias helpers above are alias-keyed; everything below is *canonical*-keyed,
# which is the unit a curator actually reasons about ("is this person a taper?",
# "are these two names the same person?").

def list_taper_vocabulary(db_path: str | None = None) -> dict:
    """Return the canonical-centric master taper list.

    Groups the flat alias table by canonical name and joins in whether each
    canonical is in the live ``_TAPER_UNIVERSE``, why it is or isn't, and how
    much of the corpus currently depends on it. Reloads the merged tables first,
    so it always reflects the DB rather than a stale import-time snapshot.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{"tapers": [...], "counts": {...}}``. Each taper dict has: canonical,
        aliases (list of ``{alias, origin}``), alias_count, origin
        (``builtin``/``user``/``mixed`` — where its aliases come from),
        in_universe, not_taper_origin (``builtin``/``user``/None — why it is
        excluded), flag (the ``user_taper_flags`` action, if any), note,
        attributions (rows in ``taper_attributions``) and confirmations (rows in
        ``taper_confirmations``).
    """
    reload_taper_aliases(db_path)
    conn = get_connection(db_path)

    grouped: dict[str, list[dict]] = {}
    for alias, canonical in _KNOWN_TAPER_ALIASES.items():
        grouped.setdefault(canonical, []).append({
            "alias": alias,
            "origin": "builtin" if alias in _BUILTIN_TAPER_ALIASES else "user",
        })

    flags = {
        r["canonical"]: dict(r)
        for r in conn.execute("SELECT canonical, action, note FROM user_taper_flags")
    }

    # Most _NOT_TAPER names are exclusion tokens only — they are never alias
    # *values*, so grouping the alias table alone would hide them and there
    # would be no way to reverse the call from the UI. dolphinsmile is the case
    # that matters (a real person judged a curator rather than a taper); the
    # rest are source-chain noise ('sbd', 'aud', 'poor sound'). They appear here
    # with no aliases, and the "Not a taper" filter is where a curator finds
    # them, so the default view stays the list of actual tapers.
    for name in _NOT_TAPER | set(flags):
        grouped.setdefault(name, [])
    attr_counts = {
        r["taper_normalised"]: r["n"] for r in conn.execute(
            "SELECT taper_normalised, COUNT(*) AS n FROM taper_attributions"
            " GROUP BY taper_normalised")
    }
    conf_counts = {
        r["taper_normalised"]: r["n"] for r in conn.execute(
            "SELECT taper_normalised, COUNT(*) AS n FROM taper_confirmations"
            " WHERE action = 'confirm' GROUP BY taper_normalised")
    }

    tapers = []
    for canonical, aliases in grouped.items():
        aliases.sort(key=lambda a: a["alias"])
        origins = {a["origin"] for a in aliases} or {"builtin"}
        flag = flags.get(canonical)
        in_universe = canonical in _TAPER_UNIVERSE
        # Distinguish "the shipped list says no" from "this install said no" —
        # only the latter is revertible from the UI without a code change.
        if in_universe:
            not_taper_origin = None
        elif flag and flag["action"] == "not_taper":
            not_taper_origin = "user"
        else:
            not_taper_origin = "builtin"
        tapers.append({
            "canonical": canonical,
            "aliases": aliases,
            "alias_count": len(aliases),
            "origin": origins.pop() if len(origins) == 1 else "mixed",
            "in_universe": in_universe,
            "not_taper_origin": not_taper_origin,
            "flag": flag["action"] if flag else None,
            "note": flag["note"] if flag else None,
            "attributions": attr_counts.get(canonical, 0),
            "confirmations": conf_counts.get(canonical, 0),
        })
    tapers.sort(key=lambda t: (-t["attributions"], t["canonical"]))

    return {
        "tapers": tapers,
        "counts": {
            "canonicals": len(tapers),
            "in_universe": sum(1 for t in tapers if t["in_universe"]),
            "not_taper": sum(1 for t in tapers if not t["in_universe"]),
            "aliases": len(_KNOWN_TAPER_ALIASES),
            "unused": sum(1 for t in tapers if t["in_universe"] and not t["attributions"]),
        },
    }


def set_taper_flag(canonical: str, is_taper: bool, note: str | None = None,
                   db_path: str | None = None) -> dict:
    """Mark a canonical as not-a-taper, or re-admit a builtin-excluded one.

    ``is_taper=False`` writes a 'not_taper' row, excluding the canonical from
    ``_TAPER_UNIVERSE``; the name stays a ``_KNOWN_TAPER_ALIASES`` value so the
    parser still collapses its spellings to one token, but the attribution
    engine will never seed it as a candidate. ``is_taper=True`` writes an
    'is_taper' row, which re-admits a canonical the code-level ``_NOT_TAPER``
    excludes. Existing ``taper_attributions`` rows are unaffected until the next
    recompute — the caller should say so.

    Args:
        canonical: Canonical taper name (lowercased here).
        is_taper: True to admit, False to exclude.
        note: Optional free-text provenance note.
        db_path: Optional database path override.

    Returns:
        ``{"canonical", "action", "in_universe"}`` after the reload.

    Raises:
        ValueError: *canonical* is missing or blank.
    """
    canonical_norm = (canonical or "").strip().lower()
    if not canonical_norm:
        raise ValueError("canonical must be non-empty")
    action = "is_taper" if is_taper else "not_taper"
    init_db(db_path)

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO user_taper_flags (canonical, action, note, created_at, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(canonical) DO UPDATE SET
                   action     = excluded.action,
                   note       = excluded.note,
                   updated_at = CURRENT_TIMESTAMP""",
            (canonical_norm, action, note),
        )

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    return {"canonical": canonical_norm, "action": action,
            "in_universe": canonical_norm in _TAPER_UNIVERSE}


def clear_taper_flag(canonical: str, db_path: str | None = None) -> dict:
    """Drop a curator not_taper/is_taper override, restoring the shipped default.

    Args:
        canonical: Canonical taper name.
        db_path: Optional database path override.

    Returns:
        ``{"canonical", "cleared": bool, "in_universe": bool}``.
    """
    canonical_norm = (canonical or "").strip().lower()
    init_db(db_path)
    conn = get_connection(db_path)
    existed = conn.execute(
        "SELECT 1 FROM user_taper_flags WHERE canonical = ?", (canonical_norm,)
    ).fetchone() is not None

    def _do(c: sqlite3.Connection) -> None:
        c.execute("DELETE FROM user_taper_flags WHERE canonical = ?", (canonical_norm,))

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    return {"canonical": canonical_norm, "cleared": existed,
            "in_universe": canonical_norm in _TAPER_UNIVERSE}


def merge_tapers(source: str, target: str, db_path: str | None = None) -> dict:
    """Repoint every alias of *source* at *target*, and carry decisions across.

    Use for "these two names are the same person" (merge) and for "this name is
    wrong" (rename — merge into a target that doesn't exist yet). Three things
    move:

    1. **User alias rows** for source are rewritten to target in place.
    2. **Builtin alias keys** for source get a user 'add' override pointing at
       target — the builtin table is code and is never edited, so an override is
       the only way to redirect one.
    3. **``taper_confirmations``** rows naming source are rewritten to target.
       These are sticky MASTER-tier curator calls; leaving them behind would
       point them at a canonical nothing resolves to any more, silently voiding
       real decisions.

    Derived ``taper_attributions`` rows are deliberately *not* rewritten: they
    are recomputed output, and the next recompute rebuilds them from the
    rewritten vocabulary. The returned ``attributions_pending`` says how many
    rows are stale until then.

    Args:
        source: Canonical name being merged away.
        target: Canonical name to merge into.
        db_path: Optional database path override.

    Returns:
        ``{"source", "target", "aliases_moved", "confirmations_moved",
        "attributions_pending"}``.

    Raises:
        ValueError: Either name is blank, they are equal, or *source* is not a
            known canonical.
    """
    src = (source or "").strip().lower()
    dst = (target or "").strip().lower()
    if not src or not dst:
        raise ValueError("source and target must be non-empty")
    if src == dst:
        raise ValueError("source and target must differ")

    reload_taper_aliases(db_path)
    if src not in set(_KNOWN_TAPER_ALIASES.values()):
        raise ValueError(f"{src!r} is not a known canonical taper")

    conn = get_connection(db_path)
    src_aliases = [a for a, c in _KNOWN_TAPER_ALIASES.items() if c == src]
    attributions_pending = conn.execute(
        "SELECT COUNT(*) FROM taper_attributions WHERE taper_normalised = ?", (src,)
    ).fetchone()[0]

    def _do(c: sqlite3.Connection) -> None:
        for alias in src_aliases:
            c.execute(
                """INSERT INTO user_taper_aliases
                       (alias_norm, canonical, action, approved, note, created_at, updated_at)
                   VALUES (?, ?, 'add', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                   ON CONFLICT(alias_norm) DO UPDATE SET
                       canonical  = excluded.canonical,
                       action     = 'add',
                       approved   = 1,
                       note       = excluded.note,
                       updated_at = CURRENT_TIMESTAMP""",
                (alias, dst, f"merged from {src}"),
            )
        c.execute(
            "UPDATE taper_confirmations SET taper_normalised = ? WHERE taper_normalised = ?",
            (dst, src),
        )

    confirmations_moved = conn.execute(
        "SELECT COUNT(*) FROM taper_confirmations WHERE taper_normalised = ?", (src,)
    ).fetchone()[0]
    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)

    return {
        "source": src,
        "target": dst,
        "aliases_moved": len(src_aliases),
        "confirmations_moved": confirmations_moved,
        "attributions_pending": attributions_pending,
    }


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

    A reference negated in its own clause ("it has none of the flaws described in
    LB-0301/LB-4356") is never a same_as claim, whatever the window around it
    says (plan E1: a nearby "close eac match" otherwise linked four unrelated
    1999-06-11 sources).

    Silver review (2026-09-25) binds each same/different phrase to its sentence:
    a "same recording" phrase whose sentence names LB refs vouches only for those
    refs ("of the other 3 LB-1116 is most distant ...; LB-14078 is same recording
    as this" links LB-14078, not LB-1116), and a "different recording than" phrase
    earlier in a ref's sentence, with no "same" phrase in between, refuses it
    ("different recording than LB-837, LB-972 (which are all the same recording)").
    """
    mentions: list[list] = []
    same_as: list[int] = []
    derived_from: list[int] = []
    better_than: list[int] = []

    refs = list(_LB_REF_RE.finditer(description))
    bounds = [0] + [b.end() for b in _REF_SENTENCE_SPLIT_RE.finditer(description)]

    def _sentence(pos: int) -> tuple[int, int]:
        lo = max(b for b in bounds if b <= pos)
        nxt = _REF_SENTENCE_SPLIT_RE.search(description, pos)
        return lo, (nxt.start() if nxt else len(description))

    def _same_binds(same_m: re.Match, ref_start: int) -> bool:
        lo, hi = _sentence(same_m.start())
        in_sentence = [r.start() for r in refs if lo <= r.start() < hi]
        return not in_sentence or ref_start in in_sentence

    for m in refs:
        lb_num = int(m.group(1))

        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(description), m.end() + 200)
        ctx = description[ctx_start:ctx_end]

        mid = (m.start() + m.end()) // 2
        snip_start = max(0, mid - 100)
        snip_end = min(len(description), mid + 100)
        snippet = description[snip_start:snip_end]

        mentions.append([lb_num, snippet])

        same_count = sum(1 for s in _SAME_RE.finditer(description, ctx_start, ctx_end)
                         if _same_binds(s, m.start()))
        diff_count = len(_DIFF_RE.findall(ctx))
        own_lo, _ = _sentence(m.start())
        before = description[own_lo:m.start()]
        last_diff = max((d.end() for d in _DIFF_RE.finditer(before)), default=-1)
        diff_led = last_diff >= 0 and not _SAME_RE.search(before, last_diff)
        if _SAME_REF_LEAD_RE.search(description[max(0, m.start() - 60):m.start()]):
            same_count += 1

        # Negation guard: the clause leading up to this reference (back to the
        # nearest bracket / comma / sentence / line break, at most 120 chars;
        # chained "LB-x/LB-y" lists share one clause) negates it.
        clause = description[max(0, m.start() - 120):m.start()]
        clause = re.split(r'[()\n;,]|\.\s', clause)[-1]
        negated = bool(re.search(
            r"\b(?:none|no|not|never|neither|nor|unlike|without|"
            r"(?:is|was|does|did|has)n'?t)\b",
            clause, re.IGNORECASE,
        ))
        # Golden review 3: "Alternate to LB-a/LB-b" negates same_as *and* derived_from;
        # a generic "not" doesn't block derived_from ("is not LB-67; it is derived from it").
        alternate = bool(re.search(
            r"\balternat(?:e|ive)\s+(?:recording\s+|source\s+|version\s+)?to\s*"
            r"(?:LB-\d+\s*[/&]\s*)*$",
            clause, re.IGNORECASE,
        ))
        negated = negated or alternate

        if same_count > 0 and same_count >= diff_count and not negated and not diff_led:
            if lb_num not in same_as:
                same_as.append(lb_num)
        if _DERIVED_RE.search(ctx) and not alternate and lb_num not in derived_from:
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
