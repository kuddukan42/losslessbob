"""Schema DDL and the master-vs-user table ownership model (from backend.db, TODO-369 S2)."""

import re

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
    "venue_xref",
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

-- lineage_edge_rejects: curator vetoes of an entry_lineage same_as/derived_from
-- edge for taper propagation (TODO-234 E). entry_lineage is re-parsed from LB
-- text, so deleting the row would not stick; taper_attribution drops these
-- edges on every recompute instead. Stored ordered (lb_a < lb_b).
CREATE TABLE IF NOT EXISTS lineage_edge_rejects (
    lb_a              INTEGER NOT NULL,
    lb_b              INTEGER NOT NULL,
    note              TEXT,
    decided_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lb_a, lb_b)
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

-- TUIT <-> Olof venue cross-reference (TODO-338, LOCAL, derived). Pairwise links,
-- never a transitive closure: method 'date' = the two corpora name these venues on
-- the same date(s) (n_dates), 'name' = the geo25 fuzzy-name rule with exactly one
-- Olof candidate. Rebuilt by `python -m backend.venue_xref --apply`.
CREATE TABLE IF NOT EXISTS venue_xref (
    tuit_venue    TEXT NOT NULL,
    tuit_city     TEXT,
    tuit_venue_id INTEGER,              -- tuit_venues.id when the show resolved to the register
    tuit_vn       TEXT NOT NULL,        -- normalised keys (backend.venue_xref.norm_*)
    tuit_cn       TEXT,
    olof_venue    TEXT NOT NULL,
    olof_city     TEXT,
    olof_vn       TEXT NOT NULL,
    olof_cn       TEXT,
    method        TEXT NOT NULL,        -- 'date' | 'name'
    n_dates       INTEGER NOT NULL DEFAULT 0,
    relation      TEXT,                 -- equal | tuit_longer | olof_longer | different
    built_at      TEXT NOT NULL,
    UNIQUE(tuit_vn, tuit_cn, olof_vn, olof_cn)
);
CREATE INDEX IF NOT EXISTS idx_venue_xref_olof ON venue_xref(olof_vn, olof_cn);

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
-- archive/specs/SHOW_DOSSIER_REDESIGN_PLAN.md "Phase 2" for the rule engine and
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
