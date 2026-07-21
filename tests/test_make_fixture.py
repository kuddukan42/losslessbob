"""Tests for tools/make_fixture_db.py (CI fixture spec B2, TODO-261).

Verifies the D3 coverage checklist (counts + one probe per shape) and D2's
determinism guarantee: generate into tmp_path twice and confirm the two DBs
are identical apart from timestamp columns.
"""
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from tools.make_fixture_db import build

_REPO_ROOT = Path(__file__).parent.parent

_TS_COLS = {
    "scraped_at", "confirmed_at", "changed_at", "created_at", "updated_at",
    "parsed_at", "computed_at", "imported_at", "geocoded_at", "posted_at",
    "first_seen_at", "last_status_at", "manual_set_at", "fetched_at", "added_at",
}


def _dump(db_path: Path, tables: list[str]) -> dict:
    conn = sqlite3.connect(str(db_path))
    out = {}
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        keep = [c for c in cols if c not in _TS_COLS]
        rows = conn.execute(
            f"SELECT {','.join(keep)} FROM {t} ORDER BY {','.join(keep)}"
        ).fetchall()
        out[t] = rows
    conn.close()
    return out


def test_generation_under_60s(tmp_path: Path) -> None:
    start = time.monotonic()
    build(tmp_path / "fixture")
    assert time.monotonic() - start < 60


def test_coverage_checklist(tmp_path: Path) -> None:
    db_path = build(tmp_path / "fixture")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    assert count("SELECT COUNT(*) FROM entries") >= 100
    assert count("SELECT COUNT(*) FROM entries WHERE status='private'") >= 1
    assert count("SELECT COUNT(DISTINCT fam_id) FROM recording_families") >= 2
    assert count("SELECT COUNT(*) FROM show_picks") > 0
    assert count("SELECT COUNT(*) FROM song_performances") > 0
    assert count("SELECT COUNT(*) FROM taper_attributions") > 0

    # two-show date: same date_str, two distinct locations
    two_show = conn.execute(
        "SELECT date_str, COUNT(DISTINCT location) AS n_locations, COUNT(*) AS n"
        " FROM entries GROUP BY date_str HAVING n_locations > 1"
    ).fetchall()
    assert two_show, "expected a same-date/different-location pair"

    # xx-date entry present
    assert count("SELECT COUNT(*) FROM entries WHERE date_str LIKE '%xx%'") >= 1

    # private entry has a matching lb_master row
    private_lb = conn.execute(
        "SELECT lb_number FROM entries WHERE status='private' LIMIT 1"
    ).fetchone()["lb_number"]
    master_row = conn.execute(
        "SELECT lb_status FROM lb_master WHERE lb_number = ?", (private_lb,)
    ).fetchone()
    assert master_row is not None and master_row["lb_status"] == "private"

    # lb_master spans public/private/missing/nonexistent
    statuses = {r[0] for r in conn.execute("SELECT DISTINCT lb_status FROM lb_master")}
    assert statuses == {"public", "private", "missing", "nonexistent"}

    # xref group: a canonical (xref=0) and alternate (xref>0) fileset on one LB
    xref_lb = conn.execute(
        "SELECT lb_number FROM checksums WHERE xref > 0 LIMIT 1"
    ).fetchone()["lb_number"]
    canonical_count = count(
        f"SELECT COUNT(*) FROM checksums WHERE lb_number={xref_lb} AND xref=0"
    )
    alt_count = count(
        f"SELECT COUNT(*) FROM checksums WHERE lb_number={xref_lb} AND xref>0"
    )
    assert canonical_count > 0 and alt_count > 0

    # curated list with 2-3 members
    list_size = count("SELECT COUNT(*) FROM curated_list_entries")
    assert 2 <= list_size <= 3

    # song rarity: one song at exactly one event ("only"), one at several
    song_counts = dict(
        conn.execute(
            "SELECT song_norm, COUNT(DISTINCT event_id) FROM song_performances"
            " GROUP BY song_norm"
        ).fetchall()
    )
    assert 1 in song_counts.values()
    assert max(song_counts.values()) > 1

    # cross-refs present
    assert count("SELECT COUNT(*) FROM bobdylan_shows") >= 1
    assert count("SELECT COUNT(*) FROM setlistfm_shows") >= 1

    # my_collection points inside the fixture dest, folders not required to exist
    coll_row = conn.execute("SELECT disk_path FROM my_collection LIMIT 1").fetchone()
    assert coll_row is not None
    assert not (db_path.parent.parent / coll_row["disk_path"]).exists()

    conn.close()


def test_two_runs_are_deterministic(tmp_path: Path) -> None:
    """Two separate CLI invocations of the generator must agree exactly.

    Run as subprocesses, not two in-process build() calls: backend.db's
    write-queue is a first-caller-wins process-global singleton (BUG-246), so
    a second in-process build() against a different db_path would exercise
    the queue's cross-DB fallback path instead of the normal write path —
    not what "two runs" is meant to test here.
    """
    tables = [
        "entries", "checksums", "lb_master", "recording_families",
        "tapematch_family_meta", "curated_lists", "curated_list_entries",
        "olof_pages", "olof_events", "olof_songs", "bobdylan_shows",
        "setlistfm_shows", "entry_files", "my_collection", "collection_mounts",
        "entry_lineage", "taper_attributions", "show_picks", "song_performances",
        "song_canonical", "user_taper_aliases", "meta",
    ]
    dest1, dest2 = tmp_path / "run1", tmp_path / "run2"
    for dest in (dest1, dest2):
        subprocess.run(
            [sys.executable, "tools/make_fixture_db.py", "--dest", str(dest)],
            cwd=str(_REPO_ROOT), check=True, capture_output=True, text=True,
        )

    dump1 = _dump(dest1 / "data" / "losslessbob.db", tables)
    dump2 = _dump(dest2 / "data" / "losslessbob.db", tables)

    for t in tables:
        assert dump1[t] == dump2[t], f"non-deterministic output in table {t}"
