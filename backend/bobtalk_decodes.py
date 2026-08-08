"""Cache of raw ASR window decodes for the bobtalk locate pass (TODO-303).

``backend/bobtalk.py`` deliberately stores a *timestamp* and never a transcript
— the quote text already lives in ``olof_events.bobtalk``. That is the right
rule for the shipped artifact, but it made the expensive half of the pass
disposable: a corpus run costs roughly 7 CPU-minutes per recording, and every
re-tune of ``MIN_DICE`` / ``MIN_RATIO`` or of ``content_tokens`` used to require
decoding the whole corpus again.

This module keeps the decoded window text so re-scoring is free. What stays
cheap and what does not:

* changing a threshold or the tokenizer -> re-score from cache, no ASR at all
* changing the model, the quantisation, or the window geometry (``pre_sec`` /
  ``post_sec``) -> genuinely different text was heard, so the cache key misses
  and the recording is decoded again. The key exists precisely so this can
  never be served stale.

``compute_type`` is in the key but ``device`` is not, and the distinction is
deliberate: CPU-int8 and GPU-float16 decodes of the same audio differ in their
output, while the same quantisation on either device does not. Keying on the
quantisation stops a cheap CPU pass from being silently reused as if it were
the GPU-quality decode; keying on the device too would throw away good cache
entries for no reason.

The cache lives in its own database file (``data/bobtalk_decodes.db``, the
``fingerprints.db`` precedent) rather than the main one. It is derived data:
keeping it separate keeps the main DB and its backups lean, and makes "discard
it later" a single file deletion once the thresholds have settled. ``prune()``
and ``summary()`` support discarding a slice instead of all of it.

Volume, measured on the PoC shape (~29 boundaries per recording, a few hundred
characters of decoded text per window): order 10 KB per recording, so a
3,275-recording corpus run lands around 30-50 MB. Cheap next to the CPU-hours
it makes re-usable.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Window bounds are floats coming from a config constant, so they are rounded
# before they enter the key — otherwise a re-run could miss its own cache on a
# representation difference invisible to the caller.
_GEOM_DP = 3

# A full-show decode has no boundary geometry to key on: it heard everything.
# It is keyed by this sentinel pair instead of by a window size, which keeps the
# existing key columns (and so the boundary decodes already cached) untouched
# while guaranteeing the two passes can never be served for each other.
#
# Deliberately absent from the key: the sliding window/hop the matcher later
# cuts over these utterances. Re-cutting stored utterances is free, so making it
# part of the key would throw away good decodes every time the matcher is tuned.
FULL_SHOW_PRE = -1.0
FULL_SHOW_POST = -1.0
FULL_SHOW_GEOM = (FULL_SHOW_PRE, FULL_SHOW_POST)


@dataclass(frozen=True)
class Window:
    """One decoded stretch of audio.

    Under the boundary geometry this is a listening window around a track split;
    under :data:`FULL_SHOW_GEOM` it is a single ASR utterance, and the matcher
    cuts its own windows over the sequence. Both are ``(t_start, t_end, text)``
    on the source-local clock, so the storage layer needs no second shape.

    Attributes:
        index: Position in the recording's decoded sequence.
        t_start: Start, source-local seconds.
        t_end: End, source-local seconds.
        text: Raw decoded text. Stored un-tokenised so a later tokenizer change
            can be re-scored for free.
    """

    index: int
    t_start: float
    t_end: float
    text: str


def _geom(pre_sec: float, post_sec: float) -> tuple[float, float]:
    """Return window bounds rounded to the precision used in the cache key."""
    return round(float(pre_sec), _GEOM_DP), round(float(post_sec), _GEOM_DP)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the decode-cache tables if absent.

    Idempotent per the repo's SQLite rules: ``CREATE TABLE IF NOT EXISTS`` plus
    a ``PRAGMA table_info`` check before any ``ALTER``.

    Args:
        conn: Open connection to the decode-cache database.
    """
    # A key column added later cannot be ALTERed into a PRIMARY KEY, and this
    # is a *cache*: discarding entries that predate a key change costs CPU to
    # refill but can never lose real data, whereas keeping them risks serving a
    # decode made under settings the caller did not ask for. So a table missing
    # a key column is dropped rather than migrated.
    for table in ("bobtalk_decode_runs", "bobtalk_decode_windows"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and "compute_type" not in cols:
            log.warning("decode cache: %s predates the compute_type key; discarding", table)
            conn.execute(f"DROP TABLE {table}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bobtalk_decode_runs (
            lb_number    INTEGER NOT NULL,
            model        TEXT    NOT NULL,
            compute_type TEXT    NOT NULL,
            pre_sec      REAL    NOT NULL,
            post_sec     REAL    NOT NULL,
            n_windows    INTEGER NOT NULL,
            audio_sec    REAL,
            decode_sec   REAL,
            device       TEXT,
            decoded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lb_number, model, compute_type, pre_sec, post_sec)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bobtalk_decode_windows (
            lb_number    INTEGER NOT NULL,
            model        TEXT    NOT NULL,
            compute_type TEXT    NOT NULL,
            pre_sec      REAL    NOT NULL,
            post_sec     REAL    NOT NULL,
            window_index INTEGER NOT NULL,
            t_start      REAL    NOT NULL,
            t_end        REAL    NOT NULL,
            text         TEXT    NOT NULL,
            PRIMARY KEY (lb_number, model, compute_type, pre_sec, post_sec, window_index)
        )
    """)
    for table, extra in (("bobtalk_decode_runs", (("audio_sec", "REAL"),
                                                  ("decode_sec", "REAL"),
                                                  ("device", "TEXT"))),
                         ("bobtalk_decode_windows", ())):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in extra:
            if name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bobtalk_dec_lb "
                 "ON bobtalk_decode_windows(lb_number)")
    conn.commit()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the decode cache, creating the file and schema on first use.

    Args:
        db_path: Override for the cache database path. Defaults to
            ``paths.BOBTALK_DECODES_DB_PATH``.

    Returns:
        An open connection with the schema ensured.
    """
    if db_path is None:
        from backend import paths  # local: keeps this module importable standalone
        db_path = paths.BOBTALK_DECODES_DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    return conn


def load_windows(conn: sqlite3.Connection, lb_number: int, model: str,
                 compute_type: str, pre_sec: float,
                 post_sec: float) -> list[Window] | None:
    """Return cached windows for a recording, or ``None`` if not cached.

    ``None`` and ``[]`` are different answers, and the distinction is the point
    of the companion run row: a decode killed halfway through leaves windows
    behind, and serving those as a complete pass would silently locate quotes
    against part of a show. Only a recording with a run row counts as cached.

    Args:
        conn: Open connection to the decode-cache database.
        lb_number: Recording to look up.
        model: ASR model the decode must have used.
        compute_type: Quantisation the decode must have used.
        pre_sec: Seconds listened before each boundary.
        post_sec: Seconds listened after each boundary.

    Returns:
        Windows in boundary order, or ``None`` when no complete decode is held.
    """
    pre, post = _geom(pre_sec, post_sec)
    key = (int(lb_number), model, compute_type, pre, post)
    run = conn.execute(
        "SELECT n_windows FROM bobtalk_decode_runs WHERE lb_number = ? AND model = ? "
        "AND compute_type = ? AND pre_sec = ? AND post_sec = ?", key).fetchone()
    if run is None:
        return None
    rows = conn.execute(
        "SELECT window_index, t_start, t_end, text FROM bobtalk_decode_windows "
        "WHERE lb_number = ? AND model = ? AND compute_type = ? AND pre_sec = ? "
        "AND post_sec = ? ORDER BY window_index", key).fetchall()
    if len(rows) != run[0]:
        log.warning("LB-%05d: decode cache holds %d of %d windows; ignoring",
                    lb_number, len(rows), run[0])
        return None
    # A recording whose every window is empty is not a quiet tape, it is a
    # decoder that failed without raising — the shape a missing CUDA library
    # produces, since faster-whisper errors are swallowed per window. Such an
    # entry is refused on read as well as on write, because a cache poisoned
    # before the write-side guard existed would otherwise be served forever.
    if rows and not any((t or "").strip() for _, _, _, t in rows):
        log.warning("LB-%05d: cached decode is wholly textless (failed decoder); "
                    "ignoring — prune it to re-decode", lb_number)
        return None
    return [Window(int(i), float(a), float(b), t) for i, a, b, t in rows]


def save_windows(conn: sqlite3.Connection, lb_number: int, model: str,
                 compute_type: str, pre_sec: float, post_sec: float,
                 windows: list[Window], audio_sec: float | None = None,
                 decode_sec: float | None = None,
                 device: str | None = None) -> int:
    """Store a recording's decoded windows, replacing any previous pass.

    Windows and the run row are written in one transaction, so an interrupted
    save cannot leave a run row claiming windows that are not there.

    Args:
        conn: Open connection to the decode-cache database.
        lb_number: Recording the windows came from.
        model: ASR model that produced the decode.
        compute_type: Quantisation that produced the decode.
        pre_sec: Seconds listened before each boundary.
        post_sec: Seconds listened after each boundary.
        windows: Decoded windows, in boundary order.
        audio_sec: Source duration, for cache accounting.
        decode_sec: Wall-clock decode cost, for cache accounting.
        device: Device used, recorded for provenance only — it is not part of
            the key, so a CPU and a GPU pass at the same quantisation share an
            entry rather than duplicating the work.

    Returns:
        Number of windows written.
    """
    pre, post = _geom(pre_sec, post_sec)
    key = (int(lb_number), model, compute_type, pre, post)
    with conn:
        conn.execute("DELETE FROM bobtalk_decode_windows WHERE lb_number = ? AND model = ? "
                     "AND compute_type = ? AND pre_sec = ? AND post_sec = ?", key)
        conn.executemany(
            """INSERT INTO bobtalk_decode_windows
               (lb_number, model, compute_type, pre_sec, post_sec, window_index,
                t_start, t_end, text)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(*key, w.index, float(w.t_start), float(w.t_end), w.text) for w in windows])
        conn.execute(
            """INSERT INTO bobtalk_decode_runs
               (lb_number, model, compute_type, pre_sec, post_sec, n_windows,
                audio_sec, decode_sec, device)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(lb_number, model, compute_type, pre_sec, post_sec) DO UPDATE SET
                 n_windows = excluded.n_windows, audio_sec = excluded.audio_sec,
                 decode_sec = excluded.decode_sec, device = excluded.device,
                 decoded_at = CURRENT_TIMESTAMP""",
            (*key, len(windows), audio_sec, decode_sec, device))
    return len(windows)


def summary(conn: sqlite3.Connection) -> list[dict]:
    """Return per-model cache accounting, for deciding what to discard.

    Args:
        conn: Open connection to the decode-cache database.

    Returns:
        One dict per ``(model, pre_sec, post_sec)`` with recording and window
        counts, stored characters, and the decode-hours the cache represents.
    """
    rows = conn.execute("""
        SELECT r.model, r.compute_type, r.pre_sec, r.post_sec, COUNT(*) AS recordings,
               SUM(r.n_windows) AS windows, SUM(COALESCE(r.decode_sec, 0)) AS decode_sec,
               MIN(r.decoded_at) AS first_at, MAX(r.decoded_at) AS last_at
        FROM bobtalk_decode_runs r
        GROUP BY r.model, r.compute_type, r.pre_sec, r.post_sec ORDER BY recordings DESC
    """).fetchall()
    out = []
    for model, ctype, pre, post, recordings, windows, decode_sec, first_at, last_at in rows:
        chars = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(text)), 0) FROM bobtalk_decode_windows "
            "WHERE model = ? AND compute_type = ? AND pre_sec = ? AND post_sec = ?",
            (model, ctype, pre, post)).fetchone()[0]
        out.append({"model": model, "compute_type": ctype, "pre_sec": pre, "post_sec": post,
                    "recordings": recordings, "windows": windows or 0,
                    "chars": chars, "decode_hours": (decode_sec or 0) / 3600.0,
                    "first_at": first_at, "last_at": last_at})
    return out


def prune(conn: sqlite3.Connection, model: str | None = None,
          before: str | None = None, lb_numbers: list[int] | None = None) -> int:
    """Discard cached decodes matching every filter given.

    Called with no filters it empties the cache. That is the intended endgame:
    once the thresholds are settled the decodes are dead weight, and this (or
    deleting the database file) reclaims it without touching the located
    timestamps in the main database.

    Args:
        conn: Open connection to the decode-cache database.
        model: Only discard decodes from this model.
        before: Only discard decodes older than this ``decoded_at`` value.
        lb_numbers: Only discard these recordings.

    Returns:
        Number of run rows discarded.
    """
    where, params = [], []
    if model is not None:
        where.append("model = ?")
        params.append(model)
    if before is not None:
        where.append("decoded_at < ?")
        params.append(before)
    if lb_numbers is not None:
        if not lb_numbers:
            return 0
        where.append(f"lb_number IN ({','.join('?' * len(lb_numbers))})")
        params.extend(int(n) for n in lb_numbers)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with conn:
        keys = conn.execute(
            "SELECT lb_number, model, compute_type, pre_sec, post_sec "
            "FROM bobtalk_decode_runs" + clause, params).fetchall()
        conn.executemany(
            "DELETE FROM bobtalk_decode_windows WHERE lb_number = ? AND model = ? "
            "AND compute_type = ? AND pre_sec = ? AND post_sec = ?", keys)
        conn.execute("DELETE FROM bobtalk_decode_runs" + clause, params)
    return len(keys)
