#!/usr/bin/env python3
"""Build a synthetic, fully-populated LosslessBob install for CI/testing (TODO-261).

Per instructions/FABLE_CI_FIXTURE.md D2/D3: a data-shaped miniature of a real
install (~100 entries across ~30 dates) that CI, cloud agents, and onboarding
tests can build in seconds without tj's real 2.4 GB data/ tree. ALL text is
synthetic — fake venues, fake taper handles, seeded-random checksums. Never
real taper names or real checksums.

Deterministic: fixed seed, fixed dates, stable ids. Two runs against a clean
--dest produce identical non-timestamp content.

Usage::

    .venv/bin/python3 tools/make_fixture_db.py --dest data/fixture
    .venv/bin/python3 tools/make_fixture_db.py --dest /tmp/fixture

Must be run from the project root (the folder containing backend/ and tools/).
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend import db  # noqa: E402
from backend import song_index  # noqa: E402
from tools import attribute_tapers, compute_show_picks, parse_lineage  # noqa: E402

_log = logging.getLogger(__name__)

_SEED = 20260721

_TAPERS = ["testtaper_a", "testtaper_b", "testtaper_c", "testtaper_d"]
_SOURCES = [
    "AKG C480 > Sony D8",
    "Schoeps CMC64 > Nakamichi CM-300",
    "Neumann KM140 > Sony TCD-D8",
    "Soundboard > Sony D6",
]
_LINEAGE = [
    "DAT > CDR > EAC > FLAC",
    "Cassette > CDR > EAC(secure) > FLAC",
    "DAT > SBEEXTRACT > FLAC",
]
_RATINGS = ["A+", "A", "A-", "B+", "B", "B-", "C+"]

# 30 fixed dates, deterministic venue/city text — never real LosslessBob data.
_DATES = [
    ("1975-01-11", "Testville Arena", "Testville, TS"),
    ("1975-02-20", "Two Show Hall (Early)", "Duoville, DV"),
    ("1975-02-20", "Two Show Hall (Late)", "Duoville, DV"),
    ("1975-03-05", "Fixture Fieldhouse", "Sampleburg, SB"),
    ("1975-04-18", "Mock Music Hall", "Placeholder City, PC"),
    ("1975-05-02", "Synthetic Stadium", "Genericton, GT"),
    ("1976-01-09", "Testville Arena", "Testville, TS"),
    ("1976-02-14", "Dummy Dome", "Faketown, FT"),
    ("1976-03-10", "Fixture Fieldhouse", "Sampleburg, SB"),
    ("1976-04-22", "Mock Music Hall", "Placeholder City, PC"),
    ("1976-05-30", "Synthetic Stadium", "Genericton, GT"),
    ("1977-01-15", "Dummy Dome", "Faketown, FT"),
    ("1977-02-27", "Testville Arena", "Testville, TS"),
    ("1977-03-19", "Sample Center", "Exampleville, EX"),
    ("1977-04-08", "Fixture Fieldhouse", "Sampleburg, SB"),
    ("1977-05-25", "Mock Music Hall", "Placeholder City, PC"),
    ("1978-01-03", "Sample Center", "Exampleville, EX"),
    ("1978-02-11", "Synthetic Stadium", "Genericton, GT"),
    ("1978-xx-xx", "Unknown Venue", "Unknown, XX"),
    ("1978-04-29", "Dummy Dome", "Faketown, FT"),
    ("1978-05-17", "Testville Arena", "Testville, TS"),
    ("1979-01-21", "Sample Center", "Exampleville, EX"),
    ("1979-02-08", "Mock Music Hall", "Placeholder City, PC"),
    ("1979-03-16", "Fixture Fieldhouse", "Sampleburg, SB"),
    ("1979-04-24", "Synthetic Stadium", "Genericton, GT"),
    ("1979-05-12", "Dummy Dome", "Faketown, FT"),
    ("1980-01-06", "Testville Arena", "Testville, TS"),
    ("1980-02-19", "Sample Center", "Exampleville, EX"),
    ("1980-03-27", "Mock Music Hall", "Placeholder City, PC"),
    ("1980-04-14", "Fixture Fieldhouse", "Sampleburg, SB"),
]
# Sources per date (index-aligned with _DATES) — sums to 100+ entries and
# guarantees date[0] gets 4 sources (multi-source family test) and the two
# Duoville rows stay a 1/2 split (two-show-date disambiguation, D3).
_N_SOURCES = [4, 1, 2, 3, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 1, 4,
              4, 3, 4, 3, 4, 4, 3, 4, 4, 4]


def _rng() -> random.Random:
    return random.Random(_SEED)


def _make_description(rng: random.Random, taper: str, lb_number: int, xrefs: list[str]) -> str:
    """Build synthetic description text carrying real lineage phrases (D3)."""
    parts = [
        f"Taper: {taper}.",
        f"Source: {rng.choice(_SOURCES)}.",
        f"Lineage: {rng.choice(_LINEAGE)}.",
    ]
    parts.extend(xrefs)
    return " ".join(parts)


def _seeded_hex(rng: random.Random, n: int = 32) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def generate(conn, rng: random.Random) -> dict:
    """Insert all synthetic rows (D3 shapes) into *conn*. Returns id bookkeeping."""
    lb = 0
    entries_by_date: dict[str, list[int]] = {}
    all_lbs: list[int] = []

    for (date_str, venue, city), n_sources in zip(_DATES, _N_SOURCES):
        date_lbs = []
        for i in range(n_sources):
            lb += 1
            taper = _TAPERS[lb % len(_TAPERS)]
            xrefs = []
            # First entry of a multi-source date references the next one,
            # giving parse_lineage real same_as/derived_from/better_than hits.
            if i == 0 and n_sources > 1:
                xrefs.append(f"Same source as LB-{lb + 1:05d}.")
            if i == 1 and n_sources > 2:
                xrefs.append(f"Derived from LB-{lb - 1:05d} master tape.")
            if i == 2 and n_sources > 3:
                xrefs.append(f"Better than LB-{lb - 2:05d}, tape hiss removed.")
            description = _make_description(rng, taper, lb, xrefs)
            rating = _RATINGS[(lb + i) % len(_RATINGS)]
            conn.execute(
                "INSERT INTO entries (lb_number, date_str, location, rating, "
                "description, setlist, status, lb_category, source_type) "
                "VALUES (?, ?, ?, ?, ?, ?, 'ok', 'concert', 'audience')",
                (lb, date_str, f"{venue}, {city}", rating, description,
                 f"01 Fixture Song One\n02 Fixture Song Two"),
            )
            date_lbs.append(lb)
            all_lbs.append(lb)

            # Canonical checksum fileset (xref=0) for every entry.
            for fi in range(2):
                conn.execute(
                    "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref) "
                    "VALUES (?, ?, 'f', ?, 0)",
                    (_seeded_hex(rng), f"lb{lb:05d}-d{i+1}t{fi+1:02d}.flac.md5", lb),
                )
        entries_by_date[date_str] = date_lbs

    # ── Private entry + matching lb_master row (D3) ─────────────────────────
    lb += 1
    private_lb = lb
    conn.execute(
        "INSERT INTO entries (lb_number, date_str, location, description, "
        "setlist, status, lb_category, source_type) "
        "VALUES (?, '1980-05-09', 'Private Venue, Hidden City, HC', "
        "'Taper: testtaper_a. Source: AKG C480 > Sony D8. Lineage: DAT > CDR > FLAC.', "
        "'01 Fixture Song One', 'private', 'concert', 'audience')",
        (private_lb,),
    )
    all_lbs.append(private_lb)

    # ── xref group: second fileset (xref=1) on an existing LB (D3) ─────────
    xref_lb = all_lbs[0]
    for fi in range(2):
        conn.execute(
            "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref) "
            "VALUES (?, ?, 'f', ?, 1)",
            (_seeded_hex(rng), f"lb{xref_lb:05d}-alt-t{fi+1:02d}.flac.md5", xref_lb),
        )

    # ── lb_master rows: public / private / missing / nonexistent (D3) ──────
    for i, l in enumerate(all_lbs):
        status = "private" if l == private_lb else "public"
        conn.execute(
            "INSERT INTO lb_master (lb_number, lb_status, has_webpage, has_checksums) "
            "VALUES (?, ?, 1, 1)",
            (l, status),
        )
    missing_lb, nonexistent_lb = lb + 1, lb + 2
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status, has_webpage, has_checksums) "
        "VALUES (?, 'missing', 0, 0)", (missing_lb,),
    )
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status, has_webpage, has_checksums) "
        "VALUES (?, 'nonexistent', 0, 0)", (nonexistent_lb,),
    )
    lb = nonexistent_lb

    # ── recording_families + tapematch_family_meta: 2 families (D3) ────────
    fam1_date, fam1_members = _DATES[0][0], entries_by_date[_DATES[0][0]][:3]
    fam2_date, fam2_members = _DATES[6][0], entries_by_date[_DATES[6][0]][:2]
    for fam_id, concert_date, members in (
        ("FAM-00001", fam1_date, fam1_members),
        ("FAM-00002", fam2_date, fam2_members),
    ):
        for m in members:
            conn.execute(
                "INSERT INTO recording_families (lb_number, fam_id, concert_date, run_id) "
                "VALUES (?, ?, ?, 'fixture-run-1')",
                (m, fam_id, concert_date),
            )
        conn.execute(
            "INSERT INTO tapematch_family_meta "
            "(fam_id, concert_date, label, by, conf, member_count, run_id) "
            "VALUES (?, ?, ?, 'ai', 0.9, ?, 'fixture-run-1')",
            (fam_id, concert_date, f"Fixture family {fam_id}", len(members)),
        )

    # ── curated list with 2-3 members (D3) ──────────────────────────────────
    cur = conn.execute(
        "INSERT INTO curated_lists (name, label, source) "
        "VALUES ('fixture_curator', 'Fixture Curator Picks', 'fixture')"
    )
    list_id = cur.lastrowid
    for m in all_lbs[:3]:
        conn.execute(
            "INSERT INTO curated_list_entries (list_id, lb_number, note) "
            "VALUES (?, ?, 'fixture pick')",
            (list_id, m),
        )

    # ── olof_events / olof_songs: rarity shapes (D3) ────────────────────────
    olof_dates = [_DATES[0][0], _DATES[3][0], _DATES[6][0], _DATES[9][0]]
    event_ids = []
    for idx, (date_str, venue, city) in enumerate(
        [(d, v, c) for d, v, c in _DATES if d in olof_dates][:4]
    ):
        event_id = 90000 + idx
        conn.execute(
            "INSERT INTO olof_pages (filename, url, corpus, segment_title) "
            "VALUES (?, '', 'dsn', 'Fixture Segment')",
            (f"fixture_page_{idx}.htm",),
        )
        conn.execute(
            "INSERT INTO olof_events (event_id, source, page_filename, event_type, "
            "date_str, venue, city) VALUES (?, 'dsn', ?, 'concert', ?, ?, ?)",
            (event_id, f"fixture_page_{idx}.htm", date_str, venue, city),
        )
        event_ids.append(event_id)

    # "Fixture Common Song" performed at every event (common); "Fixture Rare
    # Song" performed at exactly one event (rarity flag "only").
    for pos, event_id in enumerate(event_ids):
        conn.execute(
            "INSERT INTO olof_songs (event_id, position, song_title) VALUES (?, 1, "
            "'Fixture Common Song')",
            (event_id,),
        )
    conn.execute(
        "INSERT INTO olof_songs (event_id, position, song_title) VALUES (?, 2, "
        "'Fixture Rare Song')",
        (event_ids[0],),
    )

    # ── bobdylan_shows + setlistfm_shows cross-refs (D3) ────────────────────
    conn.execute(
        "INSERT INTO bobdylan_shows (bobdylan_url, date_str, venue, location) "
        "VALUES ('https://example.invalid/fixture-show', ?, ?, ?)",
        (_DATES[0][0], _DATES[0][1], _DATES[0][2]),
    )
    conn.execute(
        "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city) "
        "VALUES ('fixture-setlistfm-1', ?, ?, ?)",
        (_DATES[0][0], _DATES[0][1], _DATES[0][2].split(",")[0]),
    )

    # ── entry_files (D3) ─────────────────────────────────────────────────────
    for m in all_lbs[:5]:
        conn.execute(
            "INSERT INTO entry_files (lb_number, filename, clean_name, file_url) "
            "VALUES (?, ?, ?, ?)",
            (m, f"lb{m:05d}.zip", f"LB-{m:05d}.zip",
             f"https://example.invalid/fixture/LB-{m:05d}.zip"),
        )

    # ── collection_mounts + my_collection (D3, folders NOT created) ────────
    conn.execute(
        "INSERT INTO collection_mounts (label, root_path, notes) "
        "VALUES ('fixture_mount', 'collection', 'synthetic fixture mount')"
    )
    for m in all_lbs[:6]:
        conn.execute(
            "INSERT INTO my_collection (lb_number, folder_name, disk_path, xref) "
            "VALUES (?, ?, ?, 0)",
            (m, f"LB-{m:05d}", f"collection/LB-{m:05d}"),
        )

    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('master_version', 'fixture-1.0')")

    conn.commit()
    return {
        "entries": len(all_lbs),
        "private_lb": private_lb,
        "xref_lb": xref_lb,
        "families": 2,
        "olof_events": len(event_ids),
    }


def _assert_coverage(conn, stats: dict) -> None:
    """Fail loudly if the generated + recomputed DB doesn't cover D3's shapes."""
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    checks = [
        ("entries >= 100", count("SELECT COUNT(*) FROM entries") >= 100),
        ("private entries >= 1",
         count("SELECT COUNT(*) FROM entries WHERE status='private'") >= 1),
        ("families >= 2",
         count("SELECT COUNT(DISTINCT fam_id) FROM recording_families") >= 2),
        ("show_picks non-empty", count("SELECT COUNT(*) FROM show_picks") > 0),
        ("song_performances non-empty",
         count("SELECT COUNT(*) FROM song_performances") > 0),
        ("taper_attributions non-empty",
         count("SELECT COUNT(*) FROM taper_attributions") > 0),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        raise RuntimeError(f"fixture coverage assertions failed: {', '.join(failed)}")
    _log.info("fixture coverage OK: %s", ", ".join(name for name, _ in checks))


def build(dest: Path) -> Path:
    """Build a full synthetic install at *dest* (treated as APP_ROOT).

    Args:
        dest: Destination directory; a data/ subfolder is created inside it.

    Returns:
        Path to the generated losslessbob.db.
    """
    data_dir = dest / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(data_dir / "losslessbob.db")

    db.init_db(db_path)
    conn = db.get_connection(db_path)
    rng = _rng()
    generate(conn, rng)

    # Fixture tapers are fake handles, so they aren't in the real, curated
    # _TAPER_UNIVERSE that taper_attribution.py's Layer 0 filters against.
    # Register them the same way a curator would (TODO-241 user_taper_aliases),
    # scoped to this fixture DB only — never touches the real known-taper list.
    for taper in _TAPERS:
        db.add_taper_alias(taper, taper, note="fixture", db_path=db_path)

    _log.info("Running derived recompute chain against fixture DB...")
    parse_lineage.run(db_path=db_path)
    attribute_tapers.run(db_path=db_path, skip_lineage_refresh=True)
    compute_show_picks.run(db_path=db_path, skip_lineage_refresh=True)
    song_index.run(db_path=db_path)

    _assert_coverage(conn, {})
    db.close_connection(db_path)
    return Path(db_path)


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", default="data/fixture",
                     help="Destination dir, treated as APP_ROOT (default: data/fixture)")
    args = ap.parse_args(argv)

    db_path = build(Path(args.dest))
    _log.info("Fixture DB built at %s", db_path)


if __name__ == "__main__":
    main()
