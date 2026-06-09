"""
Acoustic fingerprinting engine (Wang/Shazam-style landmark algorithm).

Identifies audio recordings by their spectral content, not their checksums.
Robust to encoding changes, level differences, partial recordings, and moderate EQ.

DB is data/fingerprints.db — separate from losslessbob.db, never exported.
"""
import hashlib
import logging
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from backend.paths import FP_DB_PATH

_log = logging.getLogger(__name__)

# ── Algorithm constants ───────────────────────────────────────────────────────

SAMPLE_RATE      = 8_000
N_FFT            = 512
HOP_LENGTH       = 256
PEAK_FILTER_SIZE = 15
FAN_OUT          = 15
TARGET_T_DELTA   = 20
TARGET_F_RANGE   = 10
MATCH_THRESHOLD  = 20

AUDIO_EXTS = frozenset({
    ".flac", ".wav", ".wave", ".aif", ".aiff",
    ".shn", ".ape", ".wv", ".m4a", ".mp3", ".ogg",
})

# ── Thread-local DB connection ────────────────────────────────────────────────

_local = threading.local()


def _get_fp_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a thread-local connection to fingerprints.db."""
    p = str(db_path or FP_DB_PATH)
    conn = getattr(_local, "fp_conn", None)
    if conn is None or getattr(_local, "fp_conn_path", None) != p:
        conn = sqlite3.connect(p, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.fp_conn = conn
        _local.fp_conn_path = p
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_fp_db(db_path: Path | None = None) -> None:
    """Create fingerprints.db schema. Idempotent — safe to call on startup."""
    p = db_path or FP_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_fp_conn(p)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audio_tracks (
            id               INTEGER PRIMARY KEY,
            lb_number        INTEGER NOT NULL,
            file_path        TEXT NOT NULL UNIQUE,
            file_hash        TEXT,
            duration_secs    REAL,
            fingerprinted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            n_hashes         INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS fingerprints (
            hash        INTEGER NOT NULL,
            track_id    INTEGER NOT NULL REFERENCES audio_tracks(id),
            time_offset REAL    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fp_hash ON fingerprints(hash);
    """)
    conn.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _load_audio_mono(path: Path) -> tuple[object, int]:
    """Load audio file as a mono float32 array resampled to SAMPLE_RATE.

    Returns (samples_ndarray, sample_rate).
    Uses soundfile for native formats; sox_utils.decode_to_wav for others.
    """
    import soundfile as sf

    ext = path.suffix.lower()
    tmp_wav: Path | None = None

    try:
        if ext in (".flac", ".wav", ".wave", ".aif", ".aiff", ".ogg", ".mp3"):
            samples, sr = sf.read(str(path), dtype="float32", always_2d=False)
        else:
            from backend.sox_utils import decode_to_wav
            tmp_wav = decode_to_wav(path)
            samples, sr = sf.read(str(tmp_wav), dtype="float32", always_2d=False)
    finally:
        if tmp_wav is not None:
            tmp_wav.unlink(missing_ok=True)

    # Mix to mono if multi-channel
    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    # Resample to SAMPLE_RATE if needed
    if sr != SAMPLE_RATE:
        import librosa
        samples = librosa.resample(samples, orig_sr=sr, target_sr=SAMPLE_RATE)

    return samples, SAMPLE_RATE


def _compute_stft_peaks(samples: object, sr: int) -> list[tuple[int, float]]:
    """Compute STFT, find local spectral peaks.

    Returns list of (freq_bin, time_sec) for each peak.
    """
    import librosa
    import numpy as np
    from scipy.ndimage import maximum_filter

    # STFT → magnitude in dB
    stft = librosa.stft(samples, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = librosa.amplitude_to_db(np.abs(stft), ref=np.max)

    # Local maxima: a cell is a peak if it equals the neighbourhood max
    local_max = maximum_filter(mag, size=(PEAK_FILTER_SIZE, PEAK_FILTER_SIZE))
    peak_mask = (mag == local_max) & (mag > mag.mean())

    freqs, times = np.where(peak_mask)
    time_secs = librosa.frames_to_time(times, sr=sr, hop_length=HOP_LENGTH)

    return list(zip(freqs.tolist(), time_secs.tolist(), strict=False))


def _peaks_to_hashes(peaks: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Convert peak list to (hash, anchor_time_sec) pairs.

    Hash packs (freq_anchor, freq_target, delta_t_frames) into a 32-bit int:
      bits 31-23: freq_anchor  (9 bits)
      bits 22-14: freq_target  (9 bits)
      bits 13-0:  delta_t      (14 bits)
    """
    hashes: list[tuple[int, float]] = []
    # Sort by time so the target-zone window is a forward look
    peaks_sorted = sorted(peaks, key=lambda p: p[1])

    for i, (f1, t1) in enumerate(peaks_sorted):
        count = 0
        for j in range(i + 1, len(peaks_sorted)):
            f2, t2 = peaks_sorted[j]
            dt_secs = t2 - t1
            # Convert time delta to frame units for the hash
            dt_frames = int(dt_secs * SAMPLE_RATE / HOP_LENGTH)
            if dt_frames > TARGET_T_DELTA:
                break
            if abs(f2 - f1) > TARGET_F_RANGE:
                continue
            if dt_frames < 0 or dt_frames > 0x3FFF:
                continue
            f1c = int(f1) & 0x1FF
            f2c = int(f2) & 0x1FF
            dtc = dt_frames & 0x3FFF
            h = (f1c << 23) | (f2c << 14) | dtc
            hashes.append((h, t1))
            count += 1
            if count >= FAN_OUT:
                break

    return hashes


# ── Public API ────────────────────────────────────────────────────────────────

def fingerprint_file(
    path: Path,
    lb_number: int,
    db_path: Path | None = None,
    force: bool = False,
) -> dict:
    """Fingerprint one audio file and store hashes in the DB.

    Skips the file if its SHA-256 matches the stored hash (content unchanged).
    Returns {skipped, n_hashes, track_id, duration_secs, error}.
    """
    result: dict = {"skipped": False, "n_hashes": 0, "track_id": None,
                    "duration_secs": None, "error": None}
    conn = _get_fp_conn(db_path)

    try:
        file_hash = _sha256_file(path)

        # Check if already fingerprinted with same content
        existing = conn.execute(
            "SELECT id, file_hash, n_hashes FROM audio_tracks WHERE file_path=?",
            (str(path),),
        ).fetchone()

        if existing and existing["file_hash"] == file_hash and not force:
            result["skipped"] = True
            result["track_id"] = existing["id"]
            result["n_hashes"] = existing["n_hashes"]
            return result

        samples, sr = _load_audio_mono(path)
        duration = len(samples) / sr
        peaks = _compute_stft_peaks(samples, sr)
        hashes = _peaks_to_hashes(peaks)

        if existing:
            # Delete old fingerprints for this track before re-inserting
            conn.execute("DELETE FROM fingerprints WHERE track_id=?", (existing["id"],))
            conn.execute(
                "UPDATE audio_tracks SET file_hash=?, duration_secs=?, "
                "fingerprinted_at=CURRENT_TIMESTAMP, n_hashes=? WHERE id=?",
                (file_hash, duration, len(hashes), existing["id"]),
            )
            track_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO audio_tracks (lb_number, file_path, file_hash, "
                "duration_secs, n_hashes) VALUES (?,?,?,?,?)",
                (lb_number, str(path), file_hash, duration, len(hashes)),
            )
            track_id = cur.lastrowid

        if hashes:
            conn.executemany(
                "INSERT INTO fingerprints (hash, track_id, time_offset) VALUES (?,?,?)",
                [(h, track_id, t) for h, t in hashes],
            )
        conn.commit()

        result.update({"n_hashes": len(hashes), "track_id": track_id,
                       "duration_secs": duration})
    except Exception as exc:
        _log.warning("fingerprint_file failed for %s: %s", path, exc)
        result["error"] = str(exc)

    return result


def build_fingerprint_db(
    collection_rows: list[dict],
    db_path: Path | None = None,
    force: bool = False,
    state_setter: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
) -> dict:
    """Fingerprint all audio files in the collection.

    Iterates each row's disk_path, globs for audio files, and calls
    fingerprint_file() on each. Skips rows whose disk_path is missing.

    Returns {done, total, skipped, errors}.
    """
    def _set(**kw):
        if state_setter:
            state_setter(kw)

    # Collect all files first so we know the total
    n_total_rows = len(collection_rows)
    all_files: list[tuple[Path, int]] = []
    for scan_idx, row in enumerate(collection_rows):
        disk_path = row.get("disk_path", "")
        lb_number = row.get("lb_number", 0)
        p = Path(disk_path)
        if not p.is_dir():
            _log.info("build_fingerprint_db: skipping missing path %s", disk_path)
            continue
        if stop_event and stop_event.is_set():
            break
        # Emit scanning progress every 50 folders so the UI shows activity
        if scan_idx % 50 == 0 and state_setter:
            state_setter({
                "status": "scanning",
                "current": f"Scanning folders… ({scan_idx}/{n_total_rows})",
                "done": 0, "total": 0, "skipped": 0, "errors": [],
                "stop_requested": False, "queue_preview": [],
            })
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
                all_files.append((f, lb_number))

    def _preview(idx: int) -> list[str]:
        """Return display names for the next 10 files after position idx."""
        return [
            f"{p.parent.name}/{p.name}"
            for p, _ in all_files[idx: idx + 10]
        ]

    _set(status="running", done=0, total=len(all_files),
         skipped=0, errors=[], current="", stop_requested=False,
         queue_preview=_preview(0))

    if not all_files:
        _set(status="done", current="", done=0, queue_preview=[])
        return {"done": 0, "total": 0, "skipped": 0, "errors": []}

    done = 0
    skipped = 0
    errors: list[str] = []

    for i, (audio_path, lb_number) in enumerate(all_files):
        if stop_event and stop_event.is_set():
            break

        _set(
            current=f"{audio_path.parent.name} / {audio_path.name}",
            queue_preview=_preview(i + 1),
        )
        res = fingerprint_file(audio_path, lb_number, db_path=db_path, force=force)

        if res.get("error"):
            errors.append(f"{audio_path.name}: {res['error']}")
        elif res.get("skipped"):
            skipped += 1

        done += 1
        _set(done=done, skipped=skipped, errors=list(errors))

    _set(status="done", current="", done=done,
         skipped=skipped, errors=list(errors), queue_preview=[])
    return {"done": done, "total": len(all_files), "skipped": skipped, "errors": errors}


def identify_file(
    query_path: Path,
    db_path: Path | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Identify an unknown audio file against the fingerprint DB.

    Returns a list of up to top_n candidates, sorted by score descending:
      [{track_id, lb_number, file_path, score, confident}, ...]
    """
    conn = _get_fp_conn(db_path)

    try:
        samples, sr = _load_audio_mono(query_path)
    except Exception as exc:
        _log.error("identify_file: failed to load %s: %s", query_path, exc)
        return []

    peaks = _compute_stft_peaks(samples, sr)
    hashes = _peaks_to_hashes(peaks)

    if not hashes:
        return []

    # Build a lookup from hash value → query time offset (keep first occurrence per hash)
    hash_to_query_offset: dict[int, float] = {}
    for h, t in hashes:
        if h not in hash_to_query_offset:
            hash_to_query_offset[h] = t

    # Temporal coherence histogram: (track_id, rounded_offset_delta) → count
    # Matches must agree on the same time shift, not just share a hash value.
    from collections import Counter
    coherence: dict[int, Counter] = defaultdict(Counter)

    # Batch hash lookups in chunks of 500 (SQLite variable limit is 999)
    hash_vals = list(hash_to_query_offset.keys())
    for i in range(0, len(hash_vals), 500):
        chunk = hash_vals[i:i + 500]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT hash, track_id, time_offset FROM fingerprints"
            f" WHERE hash IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            query_t = hash_to_query_offset[row["hash"]]
            # Round delta to 0.1s bins to tolerate minor timing jitter
            delta = round(row["time_offset"] - query_t, 1)
            coherence[row["track_id"]][delta] += 1

    if not coherence:
        return []

    # Score = peak bin count for each track (temporal coherence, not raw hit count)
    votes = {tid: counter.most_common(1)[0][1] for tid, counter in coherence.items()}

    # Fetch track metadata for the top candidates
    top_ids = sorted(votes, key=lambda tid: votes[tid], reverse=True)[:top_n]
    results = []
    for tid in top_ids:
        track = conn.execute(
            "SELECT id, lb_number, file_path FROM audio_tracks WHERE id=?", (tid,)
        ).fetchone()
        if not track:
            continue
        score = votes[tid]
        results.append({
            "track_id":  tid,
            "lb_number": track["lb_number"],
            "file_path": track["file_path"],
            "score":     score,
            "confident": score >= MATCH_THRESHOLD,
        })

    return results


def find_duplicate_recordings(
    db_path: Path | None = None,
    min_score: int = MATCH_THRESHOLD,
    state_setter: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
) -> list[dict]:
    """Scan the fingerprint DB for tracks that share enough hashes to be the same performance.

    Uses a SQL self-join on the fingerprints table. This can be slow on large DBs;
    stop_event lets the caller cancel.

    Returns [{lb_a, lb_b, file_a, file_b, score, confident}, ...] sorted by score desc.
    """
    def _set(**kw):
        if state_setter:
            state_setter(kw)

    _set(status="running", message="Running duplicate scan…")

    conn = _get_fp_conn(db_path)

    if stop_event and stop_event.is_set():
        _set(status="done", message="Cancelled.")
        return []

    try:
        # Temporal coherence: group hash matches by rounded time-delta between the two
        # tracks, then take the peak bin count as the score.  Raw hash-hit count is NOT
        # used — two files that share spectral content in unrelated passages would
        # otherwise generate many false positives.
        rows = conn.execute(
            """
            SELECT ta, tb, MAX(bin_count) AS score
            FROM (
                SELECT a.track_id AS ta, b.track_id AS tb,
                       ROUND(a.time_offset - b.time_offset, 1) AS delta,
                       COUNT(*) AS bin_count
                FROM fingerprints a
                JOIN fingerprints b
                  ON a.hash = b.hash AND a.track_id < b.track_id
                GROUP BY ta, tb, delta
            )
            GROUP BY ta, tb
            HAVING score >= ?
            ORDER BY score DESC
            LIMIT 500
            """,
            (min_score,),
        ).fetchall()
    except Exception as exc:
        _log.error("find_duplicate_recordings: query failed: %s", exc)
        _set(status="done", message=f"Error: {exc}")
        return []

    results = []
    for row in rows:
        if stop_event and stop_event.is_set():
            break
        ta = conn.execute(
            "SELECT lb_number, file_path FROM audio_tracks WHERE id=?", (row["ta"],)
        ).fetchone()
        tb = conn.execute(
            "SELECT lb_number, file_path FROM audio_tracks WHERE id=?", (row["tb"],)
        ).fetchone()
        if not ta or not tb:
            continue
        score = row["score"]
        results.append({
            "lb_a":     ta["lb_number"],
            "lb_b":     tb["lb_number"],
            "file_a":   ta["file_path"],
            "file_b":   tb["file_path"],
            "score":    score,
            "confident": score >= MATCH_THRESHOLD,
        })

    _set(status="done", message=f"{len(results)} duplicate pair(s) found.")
    return results


def get_fp_stats(db_path: Path | None = None) -> dict:
    """Return summary statistics for the fingerprint DB.

    Returns {track_count, hash_count, coverage_pct} where coverage_pct is
    the percentage of fingerprinted audio tracks vs. total audio files found
    in the user's collection folders (0–100).
    """
    conn = _get_fp_conn(db_path)
    track_count = conn.execute(
        "SELECT COUNT(*) FROM audio_tracks"
    ).fetchone()[0]
    hash_count = conn.execute(
        "SELECT COUNT(*) FROM fingerprints"
    ).fetchone()[0]

    return {
        "track_count":  track_count,
        "hash_count":   hash_count,
        "coverage_pct": None,
    }
