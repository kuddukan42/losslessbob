"""DB integration for concert_ranker — USER tables in ``losslessbob.db``.

Quality data is USER-tier derived data about the user's *own* copies, so it
lives in ``losslessbob.db`` (not a separate db, not MASTER) in three tables:

* ``quality_scans``               — one row per scan run (+ the config used)
* ``quality_recording_metrics``   — the RAW aggregated metric dict per recording
* ``quality_recording_scores``    — derived final score / rank / verdict

The RAW metrics are stored separately from the scores so that re-banding and
re-ranking ("rerank") never need an audio rescan — the whole point of the
"scan once, store RAW metrics" guarantee.

Unlike the Flask process (which serialises writes through a single
``DatabaseWriteQueue``), the scan runs as a pool of independent *processes*
(see :mod:`concert_ranker.runner`). Each opens its own connection here and
commits ONE transaction per recording — consistent with the crash=scrap design:
a crash before commit persists nothing, so there is nothing to clean up.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Mirrors the DDL added to ``backend/db.py`` SCHEMA_SQL. Kept here so a scan (or a
# test) can guarantee the tables exist without importing/initialising the whole
# Flask DB layer. ``IF NOT EXISTS`` makes it harmless when init_db already ran.
SCHEMA_SQL = """
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
"""

# Current metric_json envelope version. Bump if the stored shape changes.
METRIC_JSON_VERSION = 1


def _jsonable(value: Any) -> Any:
    """Coerce numpy scalars / NaN to JSON-safe Python types.

    Feature extractors occasionally return numpy ``float32`` (e.g. event rates
    derived from float32 frame times). Coerce here so stored ``metric_json`` is
    always plain JSON, and NaN becomes ``None`` rather than an invalid token.
    """
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        value = value.item()  # numpy scalar → python scalar
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def default_db_path() -> Path:
    """Return the LosslessBob DB path, falling back to ``data/losslessbob.db``."""
    try:
        from backend.paths import DB_PATH  # noqa: WPS433 (lazy: avoid hard dep)

        return Path(DB_PATH)
    except Exception:
        return Path(__file__).resolve().parents[2] / "data" / "losslessbob.db"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a standalone SQLite connection tuned for concurrent scan writers.

    Each scan process calls this independently. WAL + a long busy_timeout let
    16 consumers commit one-transaction-per-recording without tripping over each
    other; ``foreign_keys`` is left OFF here because a recording may be scored
    before its ``entries`` row exists in a partial/dev DB.
    """
    path = str(db_path or default_db_path())
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the three quality tables if they do not already exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Scans
# ─────────────────────────────────────────────────────────────────────────────
def create_scan(conn: sqlite3.Connection, config: dict | None = None,
                notes: str | None = None) -> int:
    """Insert a new ``quality_scans`` row and return its ``scan_id``.

    Args:
        conn: An open connection (see :func:`connect`).
        config: Threshold/weight config used for this scan, stored verbatim as
            JSON for reproducibility.
        notes: Optional free-text note.
    """
    config_json = json.dumps(config, sort_keys=True) if config is not None else None
    cur = conn.execute(
        "INSERT INTO quality_scans(config_json, notes) VALUES(?, ?)",
        (config_json, notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_scan(conn: sqlite3.Connection, scan_id: int) -> dict | None:
    """Return the scan row as a dict, or None."""
    row = conn.execute(
        "SELECT scan_id, started_at, config_json, notes FROM quality_scans WHERE scan_id=?",
        (scan_id,),
    ).fetchone()
    return dict(row) if row else None


def latest_scan_id(conn: sqlite3.Connection) -> int | None:
    """Return the highest ``scan_id``, or None if no scans exist."""
    row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_scans").fetchone()
    return int(row["m"]) if row and row["m"] is not None else None


# ─────────────────────────────────────────────────────────────────────────────
# Raw metrics  (the scan-once payload)
# ─────────────────────────────────────────────────────────────────────────────
def build_metric_json(aggregate: dict[str, float], tracks: list[dict] | None = None,
                      *, completeness: float | None = None,
                      duration_sec: float | None = None) -> dict:
    """Assemble the versioned metric_json envelope stored per recording.

    ``aggregate`` is the per-recording RAW metric dict (one value per metric,
    aggregated across tracks) that the scoring brain consumes directly. The
    per-track dicts are kept under ``tracks`` for future per-track normalisation
    but are not required by the current scoring path.
    """
    agg = _jsonable(dict(aggregate))
    if completeness is not None:
        agg.setdefault("completeness", completeness)
    return {
        "_v": METRIC_JSON_VERSION,
        "metrics": agg,
        "tracks": _jsonable(tracks or []),
        "n_tracks": len(tracks) if tracks else 0,
        "completeness": completeness,
        "duration_sec": duration_sec,
    }


def persist_recording(conn: sqlite3.Connection, scan_id: int, lb_number: int,
                      source_class: str | None, metric_json: dict,
                      completeness: float | None = None,
                      duration_sec: float | None = None) -> None:
    """Write ONE recording's raw metrics in a single transaction.

    Called by a consumer process after it has computed the entire folder in
    memory. Idempotent on ``(lb_number, scan_id)`` via INSERT OR REPLACE so a
    re-run of the same LB overwrites rather than duplicates.
    """
    if completeness is None:
        completeness = metric_json.get("completeness")
    if duration_sec is None:
        duration_sec = metric_json.get("duration_sec")
    payload = json.dumps(metric_json, sort_keys=True)
    with conn:  # BEGIN ... COMMIT (or ROLLBACK on exception)
        conn.execute(
            "INSERT OR REPLACE INTO quality_recording_metrics"
            "(lb_number, scan_id, source_class, metric_json, completeness, duration_sec)"
            " VALUES(?,?,?,?,?,?)",
            (lb_number, scan_id, source_class, payload, completeness, duration_sec),
        )


def done_lbs(conn: sqlite3.Connection, scan_id: int) -> set[int]:
    """LB numbers already persisted for this scan — used to skip on restart."""
    rows = conn.execute(
        "SELECT lb_number FROM quality_recording_metrics WHERE scan_id=?", (scan_id,)
    ).fetchall()
    return {int(r["lb_number"]) for r in rows}


def load_metrics(conn: sqlite3.Connection, scan_id: int,
                 lb_numbers: Iterable[int] | None = None) -> dict[int, dict]:
    """Load stored raw metrics for a scan.

    Returns ``{lb_number: {"source_class", "metrics": {raw}, "completeness",
    "duration_sec"}}``. ``metrics`` is the flat RAW dict the scoring brain
    consumes — so rerank/report work entirely from here, never re-reading audio.
    """
    sql = ("SELECT lb_number, source_class, metric_json, completeness, duration_sec"
           " FROM quality_recording_metrics WHERE scan_id=?")
    params: list[Any] = [scan_id]
    lbs = list(lb_numbers) if lb_numbers is not None else None
    if lbs:
        sql += " AND lb_number IN ({})".format(",".join("?" * len(lbs)))
        params.extend(lbs)
    out: dict[int, dict] = {}
    for r in conn.execute(sql, params):
        envelope = json.loads(r["metric_json"])
        out[int(r["lb_number"])] = {
            "source_class": r["source_class"],
            "metrics": envelope.get("metrics", {}),
            "tracks": envelope.get("tracks", []),
            "completeness": r["completeness"],
            "duration_sec": r["duration_sec"],
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Derived scores  (recomputable from raw metrics — replaced on every rerank)
# ─────────────────────────────────────────────────────────────────────────────
def clear_scores(conn: sqlite3.Connection, scan_id: int) -> None:
    """Drop all derived scores for a scan (rerank rewrites them from scratch)."""
    with conn:
        conn.execute("DELETE FROM quality_recording_scores WHERE scan_id=?", (scan_id,))


def write_scores(conn: sqlite3.Connection, scan_id: int,
                 rows: list[dict]) -> None:
    """Bulk-write derived score rows in one transaction.

    Each row dict: ``{lb_number, family_id, final_score, rank_in_family,
    vetoed, verdict_text}``.
    """
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO quality_recording_scores"
            "(lb_number, scan_id, family_id, final_score, rank_in_family, vetoed, verdict_text)"
            " VALUES(?,?,?,?,?,?,?)",
            [
                (r["lb_number"], scan_id, r.get("family_id"),
                 r.get("final_score"), r.get("rank_in_family"),
                 1 if r.get("vetoed") else 0, r.get("verdict_text"))
                for r in rows
            ],
        )


def load_scores(conn: sqlite3.Connection, scan_id: int,
                family_id: int | None = None) -> list[dict]:
    """Load derived scores for a scan, optionally restricted to one family."""
    sql = ("SELECT lb_number, family_id, final_score, rank_in_family, vetoed, verdict_text"
           " FROM quality_recording_scores WHERE scan_id=?")
    params: list[Any] = [scan_id]
    if family_id is not None:
        sql += " AND family_id=?"
        params.append(family_id)
    sql += " ORDER BY family_id, rank_in_family"
    return [dict(r) for r in conn.execute(sql, params)]
