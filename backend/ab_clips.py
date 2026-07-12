"""Aligned A/B listening clip service — LISTENING spec §2 (TODO-231).

v1 is restricted to *cleanly-aligned* TapeMatch pairs: both sources must have
``speed_kind IN ('reference', 'aligned')`` in
``tools/tapematch/observations.db``. For such a pair the two recordings share a
common performance time-base once each source's ``trim_head_sec`` (the seconds
of pre-show noise/tuning trimmed from the front) is accounted for, so a curator
can toggle A<->B at the *same musical instant* and hear a like-for-like
comparison.

The service turns a *performance-time* request ``(date, lb_a, lb_b, t_sec,
dur_sec)`` into two WAV clips:

- For each LB, performance time ``t`` maps to a source-local audio offset
  ``t + trim_head_sec`` (:func:`source_offset`).
- Each LB's folder (``my_collection.disk_path``) holds an ordered sequence of
  FLAC tracks; the source-local offset is located within the *concatenated*
  sequence using per-file durations from ``ffprobe``
  (:func:`plan_extraction`), cached per folder in memory.
- A clip may straddle a track boundary, so extraction pulls from up to N
  adjacent files and concatenates them (ffmpeg concat demuxer).
- Clips land in ``data/ab_clips/`` under a deterministic cache filename
  (:func:`cache_filename`, a hash of ``lb_number/offset/dur``) so repeat requests
  are free; the cache is LRU-pruned to the newest :data:`CACHE_LIMIT` files
  after every write.

The extraction/ffprobe helpers shell out to system ``ffmpeg``/``ffprobe``; the
offset-math functions (:func:`source_offset`, :func:`plan_extraction`,
:func:`clamp_dur`, :func:`cache_filename`) are pure and unit-testable without
any audio.

Entry points: :func:`generate_ab_clips` (the POST /api/ab_clip backing
function) and :func:`eligible_lb_set` (the GET /api/tapematch/pairs
``ab_eligible`` enrichment).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from backend.paths import DATA_DIR

log = logging.getLogger(__name__)

# ── Module constants ─────────────────────────────────────────────────────────
AB_CLIPS_DIR = DATA_DIR / "ab_clips"

FFMPEG_BIN = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/usr/bin/ffprobe"

# Clip duration bounds (seconds). A request may omit dur_sec (-> DEFAULT) or
# pass an out-of-range value, which is clamped rather than rejected.
DEFAULT_DUR_SEC = 20
MIN_DUR_SEC = 5
MAX_DUR_SEC = 60

# Keep only the newest CACHE_LIMIT clips in AB_CLIPS_DIR after each write.
CACHE_LIMIT = 40

# v1 eligibility: only these two speed_kind values share a clean, constant
# performance time-base (staircase/constant-speed-offset/speed-unknown are
# excluded until a later iteration handles their non-trivial time warping).
ELIGIBLE_SPEED_KINDS = frozenset({"reference", "aligned"})

_FLAC_GLOB = "*.flac"

# Per-folder ffprobe duration cache: {disk_path: [(filename, duration_sec), ...]}.
_DURATION_CACHE: dict[str, list[tuple[str, float]]] = {}


# ── Typed errors (each carries an HTTP status + JSON payload for the route) ───
class AbClipError(Exception):
    """Base error carrying an HTTP ``status`` and a JSON ``payload`` dict."""

    status = 500
    error_code = "internal_error"

    def __init__(self, message: str | None = None, **extra: object) -> None:
        super().__init__(message or self.error_code)
        self.payload: dict[str, object] = {"error": self.error_code}
        if message:
            self.payload["message"] = message
        self.payload.update(extra)


class BadRequestError(AbClipError):
    """400 — malformed or out-of-range request parameters."""

    status = 400
    error_code = "bad_request"


class NotEligibleError(AbClipError):
    """409 — pair is not cleanly aligned (wrong speed_kind) in v1."""

    status = 409
    error_code = "not_eligible"


class PairNotFoundError(AbClipError):
    """404 — unknown pair/date (no matching sources rows)."""

    status = 404
    error_code = "pair_not_found"


class FolderMissingError(AbClipError):
    """404 — an LB's disk_path is unknown or not a mounted directory."""

    status = 404
    error_code = "folder_missing"


class ClipLockedError(AbClipError):
    """409 — observations.db is write-locked by an in-progress run."""

    status = 409
    error_code = "locked"


# ── Pure offset / cache math (unit-testable without audio) ───────────────────
def clamp_dur(dur_sec: float | int | None) -> int:
    """Clamp a requested clip duration to the allowed range.

    Args:
        dur_sec: Requested duration in seconds, or None for the default.

    Returns:
        An int duration in ``[MIN_DUR_SEC, MAX_DUR_SEC]`` (``DEFAULT_DUR_SEC``
        when *dur_sec* is None or non-numeric).
    """
    if dur_sec is None:
        return DEFAULT_DUR_SEC
    try:
        value = int(round(float(dur_sec)))
    except (TypeError, ValueError):
        return DEFAULT_DUR_SEC
    return max(MIN_DUR_SEC, min(MAX_DUR_SEC, value))


def source_offset(t_sec: float, trim_head_sec: float | None) -> float:
    """Map a performance-time position to a source-local audio offset.

    Args:
        t_sec: Performance time in seconds (0 = first sounded note, post-trim).
        trim_head_sec: Seconds trimmed from the front of this source (may be
            None -> treated as 0).

    Returns:
        The source-local audio offset in seconds.
    """
    return float(t_sec) + float(trim_head_sec or 0.0)


def plan_extraction(
    durations: list[float], offset_sec: float, dur_sec: float
) -> list[tuple[int, float, float]]:
    """Locate a ``[offset, offset+dur)`` window within a concatenated sequence.

    Given the per-file durations of a folder's ordered FLAC tracks, work out
    which file(s) the window falls in and how much to take from each — the clip
    may straddle one or more track boundaries.

    Args:
        durations: Per-file durations in seconds, in playback order.
        offset_sec: Source-local start offset in seconds.
        dur_sec: Desired clip length in seconds.

    Returns:
        A list of ``(file_index, start_within_file, take_sec)`` segments, in
        order. Empty if *offset_sec* lies at/after the end of the sequence, or
        truncated if the window runs past the end (best-effort short clip).
    """
    segments: list[tuple[int, float, float]] = []
    if offset_sec < 0 or dur_sec <= 0:
        return segments
    n = len(durations)
    cum = 0.0
    idx = 0
    # Advance to the file that contains offset_sec.
    while idx < n and offset_sec >= cum + durations[idx]:
        cum += durations[idx]
        idx += 1
    if idx >= n:
        return segments
    local = offset_sec - cum
    remaining = float(dur_sec)
    while remaining > 1e-6 and idx < n:
        avail = durations[idx] - local
        if avail <= 0:
            idx += 1
            local = 0.0
            continue
        take = min(avail, remaining)
        segments.append((idx, local, take))
        remaining -= take
        idx += 1
        local = 0.0
    return segments


def cache_filename(lb_number: int, offset_sec: float, dur_sec: int) -> str:
    """Return the deterministic cache filename for one source's clip.

    The name depends on ``(lb_number, offset_sec, dur_sec)`` where
    ``offset_sec`` is the resolved source-local offset (performance time +
    ``trim_head_sec``), NOT the raw performance time — a later run can change
    a source's trim, and keying on the post-trim offset means a changed trim
    produces a new file instead of serving a stale cached clip. Values are
    rounded to milliseconds to avoid float representation noise.

    Args:
        lb_number: LB catalogue number of the source.
        offset_sec: Source-local start offset in seconds (post-trim).
        dur_sec: Clip duration in seconds.

    Returns:
        A ``ab_<lb>_<hash>.wav`` filename (no directory component).
    """
    key = f"{int(lb_number)}:{round(float(offset_sec), 3)}:{int(dur_sec)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"ab_{int(lb_number)}_{digest}.wav"


def is_eligible_speed(speed_kind: str | None) -> bool:
    """Return whether *speed_kind* qualifies for v1 aligned A/B listening."""
    return speed_kind in ELIGIBLE_SPEED_KINDS


# ── observations.db reads ────────────────────────────────────────────────────
def _open_obs_ro(obs_path: Path | str) -> sqlite3.Connection:
    """Open observations.db read-only. Raises :class:`ClipLockedError` if locked."""
    from backend import tapematch_sync as _tapematch_sync

    try:
        return _tapematch_sync._open_observations_db(obs_path)
    except RuntimeError as exc:
        raise ClipLockedError(str(exc)) from exc


def get_source_info(
    obs_conn: sqlite3.Connection, concert_date: str, lb_number: int
) -> dict | None:
    """Return the most-recent ``sources`` row for one (date, LB), or None.

    Args:
        obs_conn: Open (read-only) observations.db connection.
        concert_date: ISO concert date.
        lb_number: LB catalogue number.

    Returns:
        A dict with ``trim_head_sec``, ``speed_kind``, ``perf_dur_sec``,
        ``total_dur_sec``, ``folder_name`` and ``run_id`` from the latest run
        for this source, or None when no row exists.
    """
    row = obs_conn.execute(
        """
        SELECT trim_head_sec, speed_kind, perf_dur_sec, total_dur_sec,
               folder_name, run_id
        FROM sources
        WHERE concert_date = ? AND lb_number = ?
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (concert_date, lb_number),
    ).fetchone()
    if row is None:
        return None
    return {
        "trim_head_sec": row["trim_head_sec"],
        "speed_kind": row["speed_kind"],
        "perf_dur_sec": row["perf_dur_sec"],
        "total_dur_sec": row["total_dur_sec"],
        "folder_name": row["folder_name"],
        "run_id": row["run_id"],
    }


def get_pair_source_info(
    obs_conn: sqlite3.Connection, concert_date: str, lb_a: int, lb_b: int
) -> tuple[dict, dict] | None:
    """Return both sources' rows from the latest run that contains BOTH LBs.

    Trims are only mutually consistent within a single run: each run picks its
    own reference/performance window, so mixing ``trim_head_sec`` values from
    two different runs can silently misalign the pair. A compared pair always
    shares at least one run (pairs rows are written per run).

    Args:
        obs_conn: Open (read-only) observations.db connection.
        concert_date: ISO concert date.
        lb_a: First LB number.
        lb_b: Second LB number.

    Returns:
        ``(info_a, info_b)`` dicts shaped like :func:`get_source_info` and
        guaranteed to share ``run_id``, or None when no common run exists.
    """
    run_row = obs_conn.execute(
        """
        SELECT run_id FROM sources
        WHERE concert_date = ? AND lb_number IN (?, ?)
        GROUP BY run_id
        HAVING COUNT(DISTINCT lb_number) = 2
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (concert_date, lb_a, lb_b),
    ).fetchone()
    if run_row is None:
        return None
    infos: dict[int, dict] = {}
    for row in obs_conn.execute(
        """
        SELECT lb_number, trim_head_sec, speed_kind, perf_dur_sec,
               total_dur_sec, folder_name, run_id
        FROM sources
        WHERE concert_date = ? AND run_id = ? AND lb_number IN (?, ?)
        """,
        (concert_date, run_row["run_id"], lb_a, lb_b),
    ):
        infos[int(row["lb_number"])] = {
            "trim_head_sec": row["trim_head_sec"],
            "speed_kind": row["speed_kind"],
            "perf_dur_sec": row["perf_dur_sec"],
            "total_dur_sec": row["total_dur_sec"],
            "folder_name": row["folder_name"],
            "run_id": row["run_id"],
        }
    if lb_a not in infos or lb_b not in infos:
        return None
    return infos[lb_a], infos[lb_b]


def eligible_lb_set(
    obs_conn: sqlite3.Connection, concert_date: str, run_id: str | None
) -> set[int]:
    """Return the set of LB numbers eligible for aligned A/B on a given run.

    Used by the GET /api/tapematch/pairs ``ab_eligible`` enrichment: a pair is
    eligible when both of its LBs are in this set.

    Args:
        obs_conn: Open (read-only) observations.db connection.
        concert_date: ISO concert date.
        run_id: Run identifier whose sources to consult; when None, considers
            every run for the date.

    Returns:
        Set of ``lb_number`` values whose ``speed_kind`` is eligible.
    """
    if run_id is None:
        rows = obs_conn.execute(
            "SELECT lb_number, speed_kind FROM sources WHERE concert_date = ?",
            (concert_date,),
        )
    else:
        rows = obs_conn.execute(
            "SELECT lb_number, speed_kind FROM sources "
            "WHERE concert_date = ? AND run_id = ?",
            (concert_date, run_id),
        )
    return {
        r["lb_number"]
        for r in rows
        if r["lb_number"] is not None and is_eligible_speed(r["speed_kind"])
    }


def resolve_disk_path(main_conn: sqlite3.Connection, lb_number: int) -> str | None:
    """Return ``my_collection.disk_path`` for an LB, or None if not collected."""
    row = main_conn.execute(
        "SELECT disk_path FROM my_collection WHERE lb_number = ?", (lb_number,)
    ).fetchone()
    if row is None:
        return None
    # sqlite3.Row and tuple both index by 0.
    return row[0]


# ── ffprobe / ffmpeg extraction ──────────────────────────────────────────────
def _ffprobe_duration(flac_path: str) -> float:
    """Return an audio file's duration in seconds via ffprobe (0.0 on failure)."""
    try:
        out = subprocess.run(
            [
                FFPROBE_BIN, "-v", "quiet", "-print_format", "json",
                "-show_format", flac_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            log.warning("ffprobe failed (rc=%s) for %s", out.returncode, flac_path)
            return 0.0
        import json as _json

        fmt = _json.loads(out.stdout).get("format", {})
        return float(fmt.get("duration", 0.0) or 0.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        log.warning("ffprobe error for %s", flac_path, exc_info=True)
        return 0.0


def folder_flac_durations(disk_path: str) -> list[tuple[str, float]]:
    """Return the folder's FLAC tracks (sorted by name) with durations, cached.

    Args:
        disk_path: Absolute path to the LB folder.

    Returns:
        A list of ``(absolute_flac_path, duration_sec)`` in playback (filename)
        order. Cached in memory per folder for the life of the process.
    """
    cached = _DURATION_CACHE.get(disk_path)
    if cached is not None:
        return cached
    flac_files = sorted(Path(disk_path).glob(_FLAC_GLOB))
    result = [(str(p), _ffprobe_duration(str(p))) for p in flac_files]
    _DURATION_CACHE[disk_path] = result
    return result


def clear_duration_cache() -> None:
    """Clear the in-memory per-folder duration cache (for tests / rescans)."""
    _DURATION_CACHE.clear()


def _run_ffmpeg(args: list[str]) -> None:
    """Run an ffmpeg command, raising :class:`AbClipError` on non-zero exit."""
    proc = subprocess.run(
        [FFMPEG_BIN, "-y", "-loglevel", "error", *args],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise AbClipError(f"ffmpeg failed: {proc.stderr.strip()[:200]}")


def _extract_segment(flac_path: str, start: float, dur: float, out_path: str) -> None:
    """Extract ``dur`` seconds from ``start`` of one FLAC as 16-bit/44.1k stereo WAV."""
    _run_ffmpeg([
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", flac_path,
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", out_path,
    ])


def _extract_clip(
    files: list[str], segments: list[tuple[int, float, float]], out_path: str
) -> None:
    """Extract (and, if the window spans tracks, concatenate) a clip to *out_path*.

    Args:
        files: Absolute FLAC paths in playback order.
        segments: ``plan_extraction`` output for this window.
        out_path: Destination WAV path.
    """
    if len(segments) == 1:
        idx, start, take = segments[0]
        _extract_segment(files[idx], start, take, out_path)
        return

    tmp_dir = tempfile.mkdtemp(prefix="ab_clip_")
    try:
        parts: list[str] = []
        for i, (idx, start, take) in enumerate(segments):
            part = os.path.join(tmp_dir, f"part_{i:02d}.wav")
            _extract_segment(files[idx], start, take, part)
            parts.append(part)
        # concat demuxer: all parts share PCM/44.1k/stereo, so -c copy is safe.
        list_path = os.path.join(tmp_dir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as fh:
            for part in parts:
                fh.write(f"file '{part}'\n")
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path,
        ])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def prune_cache(limit: int = CACHE_LIMIT) -> None:
    """Prune AB_CLIPS_DIR to the newest *limit* WAV files by mtime."""
    try:
        clips = sorted(
            AB_CLIPS_DIR.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        return
    for stale in clips[limit:]:
        try:
            stale.unlink()
        except OSError:
            log.warning("Could not prune stale ab_clip %s", stale, exc_info=True)


def build_clip(
    disk_path: str, offset_sec: float, dur_sec: int, out_name: str
) -> str:
    """Extract one source's clip into the cache and return its filename.

    Idempotent: an already-cached clip (same *out_name*) is reused without
    re-extraction.

    Args:
        disk_path: Absolute path to the LB folder (already verified to exist).
        offset_sec: Source-local start offset in seconds.
        dur_sec: Clip duration in seconds.
        out_name: Deterministic cache filename (from :func:`cache_filename`).

    Returns:
        The clip filename (``out_name``).

    Raises:
        BadRequestError: If the offset lies beyond the folder's audio.
    """
    AB_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AB_CLIPS_DIR / out_name
    if out_path.exists():
        return out_name

    tracks = folder_flac_durations(disk_path)
    files = [f for f, _ in tracks]
    durations = [d for _, d in tracks]
    segments = plan_extraction(durations, offset_sec, dur_sec)
    if not segments:
        raise BadRequestError(
            "requested position is beyond the recorded audio", error="t_out_of_range"
        )
    _extract_clip(files, segments, str(out_path))
    prune_cache()
    return out_name


# ── Top-level orchestration ──────────────────────────────────────────────────
def generate_ab_clips(
    main_conn: sqlite3.Connection,
    obs_path: Path | str,
    concert_date: str,
    lb_a: int,
    lb_b: int,
    t_sec: float,
    dur_sec: int,
) -> dict:
    """Build both aligned A/B clips for a pair and return their metadata.

    Args:
        main_conn: Open main-app DB connection (for ``my_collection``).
        obs_path: Path to observations.db (trim/eligibility source of truth).
        concert_date: ISO concert date.
        lb_a: First LB number.
        lb_b: Second LB number.
        t_sec: Performance-time position in seconds (>= 0).
        dur_sec: Clip duration in seconds (already clamped by the caller).

    Returns:
        ``{"date", "lb_a", "lb_b", "t_sec", "dur_sec", "clip_a", "clip_b"}``
        where ``clip_a``/``clip_b`` are ``/api/ab_clip/<name>`` URLs.

    Raises:
        BadRequestError, NotEligibleError, PairNotFoundError,
        FolderMissingError, ClipLockedError: Per the failure taxonomy.
    """
    if t_sec < 0:
        raise BadRequestError("t_sec must be >= 0", error="bad_t_sec")

    obs_conn = _open_obs_ro(obs_path)
    try:
        pair_info = get_pair_source_info(obs_conn, concert_date, lb_a, lb_b)
    finally:
        obs_conn.close()

    if pair_info is None:
        raise PairNotFoundError(
            f"no common tapematch run for date={concert_date} lb={lb_a}/{lb_b}"
        )
    info_a, info_b = pair_info

    if not (is_eligible_speed(info_a["speed_kind"]) and is_eligible_speed(info_b["speed_kind"])):
        raise NotEligibleError(
            "pair is not cleanly aligned for A/B listening in v1",
            speed_kind_a=info_a["speed_kind"], speed_kind_b=info_b["speed_kind"],
        )

    # Performance-time bound: reject t beyond either source's known perf duration.
    for lb, info in ((lb_a, info_a), (lb_b, info_b)):
        perf = info.get("perf_dur_sec")
        if perf is not None and t_sec > float(perf):
            raise BadRequestError(
                f"t_sec {t_sec} exceeds performance duration of LB-{lb}",
                error="t_out_of_range",
            )

    clips: dict[int, str] = {}
    for lb, info in ((lb_a, info_a), (lb_b, info_b)):
        disk_path = resolve_disk_path(main_conn, lb)
        if not disk_path or not os.path.isdir(disk_path):
            raise FolderMissingError(
                f"folder for LB-{lb} is not available: {disk_path or '(uncollected)'}",
                lb_number=lb, path=disk_path,
            )
        offset = source_offset(t_sec, info["trim_head_sec"])
        out_name = cache_filename(lb, offset, dur_sec)
        clips[lb] = build_clip(disk_path, offset, dur_sec, out_name)

    return {
        "date": concert_date,
        "lb_a": lb_a,
        "lb_b": lb_b,
        "t_sec": t_sec,
        "dur_sec": dur_sec,
        "clip_a": f"/api/ab_clip/{clips[lb_a]}",
        "clip_b": f"/api/ab_clip/{clips[lb_b]}",
    }
