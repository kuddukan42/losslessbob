"""Sync TapeMatch family clustering from tools/tapematch/observations.db.

Ingests the offline TapeMatch CLI's per-show family detection results into
the main app DB (``recording_families`` / ``tapematch_family_meta``) so the
Library screen's recording lens can read ``fam`` / ``fam_label`` / ``fam_conf``
/ ``fam_by`` per recording with no clustering logic of its own. See
instructions/design_handoff_unified_library/07-tapematch-backend-integration.md
for the full design.
"""
import logging
import sqlite3
import time
from pathlib import Path

from backend.db import get_connection
from backend.paths import TOOLS_DIR

log = logging.getLogger(__name__)

DEFAULT_OBSERVATIONS_DB_PATH = TOOLS_DIR / "tapematch" / "observations.db"

_OPEN_RETRY_ATTEMPTS = 3
_OPEN_RETRY_BACKOFF_SEC = 1.0


def _open_observations_db(observations_db_path: "Path | str") -> sqlite3.Connection:
    """Open observations.db read-only, retrying briefly if it's write-locked.

    The tapematch CLI may hold a write lock mid-run; retry a few times before
    failing with a message the caller can surface to the user, rather than
    raising a bare ``sqlite3.OperationalError``.
    """
    uri = f"file:{Path(observations_db_path)}?mode=ro"
    last_err: sqlite3.OperationalError | None = None
    for attempt in range(_OPEN_RETRY_ATTEMPTS):
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            # Force the connection open / readable now, not lazily on first query.
            conn.execute("SELECT 1")
            return conn
        except sqlite3.OperationalError as e:
            last_err = e
            if attempt < _OPEN_RETRY_ATTEMPTS - 1:
                time.sleep(_OPEN_RETRY_BACKOFF_SEC * (attempt + 1))
    raise RuntimeError(
        "Could not open tapematch observations.db (it may be locked by an "
        "in-progress tapematch run). Try the sync again in a moment."
    ) from last_err


def _pick_best_run(obs_conn: sqlite3.Connection) -> dict[str, str]:
    """Return {concert_date: run_id} for the best run per date.

    Best = highest n_sources_ran, ties broken by latest run_id. A later
    timestamp is not always an improvement (a partial rerun can score lower),
    so n_sources_ran is the primary signal.
    """
    best: dict[str, tuple[int, str]] = {}
    for row in obs_conn.execute(
        "SELECT run_id, concert_date, n_sources_ran FROM runs"
    ):
        date = row["concert_date"]
        n_ran = row["n_sources_ran"] or 0
        run_id = row["run_id"]
        current = best.get(date)
        if current is None or (n_ran, run_id) > current:
            best[date] = (n_ran, run_id)
    return {date: run_id for date, (_, run_id) in best.items()}


def sync_tapematch_families(
    db_path=None,
    observations_db_path: "Path | str | None" = None,
) -> dict:
    """Ingest TapeMatch family clusters into the main DB.

    Args:
        db_path: Main app DB path, or None for the default.
        observations_db_path: Path to tapematch's observations.db, or None
            for the default location under tools/tapematch/.

    Returns:
        Stats dict: ``{dates_processed, families_written, recordings_linked,
        errors}``.
    """
    observations_db_path = observations_db_path or DEFAULT_OBSERVATIONS_DB_PATH
    if not Path(observations_db_path).exists():
        raise FileNotFoundError(f"observations.db not found: {observations_db_path}")

    obs_conn = _open_observations_db(observations_db_path)
    conn = get_connection(db_path)

    stats = {
        "dates_processed": 0,
        "families_written": 0,
        "recordings_linked": 0,
        "errors": [],
    }

    try:
        best_run_by_date = _pick_best_run(obs_conn)

        for concert_date, run_id in best_run_by_date.items():
            try:
                _sync_one_date(obs_conn, conn, concert_date, run_id, stats)
                stats["dates_processed"] += 1
            except Exception as e:  # noqa: BLE001 — one bad date shouldn't abort the rest
                log.exception("tapematch sync failed for %s (run %s)", concert_date, run_id)
                stats["errors"].append(f"{concert_date} ({run_id}): {e}")
    finally:
        obs_conn.close()

    return stats


def _sync_one_date(
    obs_conn: sqlite3.Connection,
    conn: sqlite3.Connection,
    concert_date: str,
    run_id: str,
    stats: dict,
) -> None:
    """Compute and upsert families for a single concert_date's chosen run."""
    sources = obs_conn.execute(
        "SELECT lb_number, family_id FROM sources "
        "WHERE run_id = ? AND lb_number IS NOT NULL",
        (run_id,),
    ).fetchall()

    members_by_family: dict[int, list[int]] = {}
    for row in sources:
        members_by_family.setdefault(row["family_id"], []).append(row["lb_number"])

    # Singletons aren't a "family" for UI purposes.
    families = {
        fam_id: sorted(set(lbs))
        for fam_id, lbs in members_by_family.items()
        if len(set(lbs)) >= 2
    }

    pair_rows = obs_conn.execute(
        "SELECT family_id_a, corr, lb_says_same FROM pairs "
        "WHERE run_id = ? AND tapematch_verdict = 'same_family' "
        "AND family_id_a = family_id_b",
        (run_id,),
    ).fetchall()
    corrs_by_family: dict[int, list[float]] = {}
    lb_says_same_by_family: dict[int, bool] = {}
    for row in pair_rows:
        fam = row["family_id_a"]
        if row["corr"] is not None:
            corrs_by_family.setdefault(fam, []).append(row["corr"])
        if row["lb_says_same"] == 1:
            lb_says_same_by_family[fam] = True

    # Label order: member_count desc, ties broken by lowest tapematch family_id.
    ordered = sorted(families.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    fresh_fam_ids: set[str] = set()
    fresh_lb_numbers: set[int] = set()
    family_rows = []
    member_rows = []
    for i, (tm_family_id, lb_numbers) in enumerate(ordered):
        fam_id = f"{concert_date}#" + "-".join(str(lb) for lb in lb_numbers)
        label = f"Family {chr(ord('A') + i)}"
        corrs = corrs_by_family.get(tm_family_id, [])
        conf = sum(corrs) / len(corrs) if corrs else None
        by = "ai+lb" if lb_says_same_by_family.get(tm_family_id) else "ai"
        member_count = len(lb_numbers)

        fresh_fam_ids.add(fam_id)
        family_rows.append(
            (fam_id, concert_date, label, by, conf, member_count, run_id)
        )
        for lb_number in lb_numbers:
            fresh_lb_numbers.add(lb_number)
            member_rows.append((lb_number, fam_id, concert_date, run_id))

    with conn:
        conn.execute("BEGIN IMMEDIATE")
        for fam_id, c_date, label, by, conf, member_count, r_id in family_rows:
            conn.execute(
                """
                INSERT INTO tapematch_family_meta
                    (fam_id, concert_date, label, by, conf, member_count, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fam_id) DO UPDATE SET
                    label=excluded.label,
                    by=excluded.by,
                    conf=excluded.conf,
                    member_count=excluded.member_count,
                    run_id=excluded.run_id,
                    imported_at=CURRENT_TIMESTAMP
                """,
                (fam_id, c_date, label, by, conf, member_count, r_id),
            )
        for lb_number, fam_id, c_date, r_id in member_rows:
            conn.execute(
                """
                INSERT INTO recording_families
                    (lb_number, fam_id, concert_date, run_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lb_number) DO UPDATE SET
                    fam_id=excluded.fam_id,
                    concert_date=excluded.concert_date,
                    run_id=excluded.run_id,
                    imported_at=CURRENT_TIMESTAMP
                """,
                (lb_number, fam_id, c_date, r_id),
            )

        # Cleanup: drop rows for this date whose family dissolved or whose
        # membership changed (and thus produced a different fam_id).
        if fresh_fam_ids:
            placeholders = ",".join("?" * len(fresh_fam_ids))
            conn.execute(
                f"DELETE FROM tapematch_family_meta WHERE concert_date = ? "
                f"AND fam_id NOT IN ({placeholders})",
                (concert_date, *fresh_fam_ids),
            )
        else:
            conn.execute(
                "DELETE FROM tapematch_family_meta WHERE concert_date = ?",
                (concert_date,),
            )
        if fresh_lb_numbers:
            placeholders = ",".join("?" * len(fresh_lb_numbers))
            conn.execute(
                f"DELETE FROM recording_families WHERE concert_date = ? "
                f"AND lb_number NOT IN ({placeholders})",
                (concert_date, *fresh_lb_numbers),
            )
        else:
            conn.execute(
                "DELETE FROM recording_families WHERE concert_date = ?",
                (concert_date,),
            )

    stats["families_written"] += len(family_rows)
    stats["recordings_linked"] += len(member_rows)


def _main() -> int:
    """CLI entry point: `.venv/bin/python3 -m backend.tapematch_sync`.

    Runs standalone, without the Flask backend — tapematch batch runs happen
    via shell scripts and may not have the app server up.
    """
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stats = sync_tapematch_families()
    print(json.dumps(stats, indent=2))
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())
