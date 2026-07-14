"""Aligned A/B listening clip service — LISTENING spec §2 (TODO-231 / TODO-233).

Eligible TapeMatch pairs: both sources must have an eligible ``speed_kind`` in
``tools/tapematch/observations.db`` — ``reference``/``aligned`` (which share
the reference time-base directly, TODO-231) or ``constant-speed-offset`` (a
single constant tape-speed error, resampled to reference speed here, TODO-233)
— from a run on/after the 2026-07-06 confidence gate (:func:`is_run_eligible`).
For such a pair the two recordings can be brought onto a common performance
time-base, so a curator can toggle A<->B at the *same musical instant* and hear
a like-for-like comparison.

The service turns a *performance-time* request ``(date, lb_a, lb_b, t_sec,
dur_sec)`` into two WAV clips:

- For each LB, performance time ``t`` maps to a source-local audio offset
  ``trim_head_sec + t * factor`` (:func:`source_offset`), where ``factor`` is
  derived from the source's ``speed_ppm`` (:func:`speed_factor`); the extracted
  span is resampled back to reference speed and the two clips are RMS
  level-matched before serving (:func:`build_clip`, TODO-233 / TODO-232).
- Each LB's folder (``my_collection.disk_path``) holds an ordered sequence of
  FLAC tracks; the source-local offset is located within the *concatenated*
  sequence using per-file durations from ``ffprobe``
  (:func:`plan_extraction`), cached per folder in memory.
- A clip may straddle a track boundary, so extraction pulls from up to N
  adjacent files and concatenates them (ffmpeg concat demuxer).
- Clips land in ``data/ab_clips/`` under a deterministic cache filename
  (:func:`cache_filename`, a hash of ``lb_number/offset/dur/speed_ppm``) so repeat requests
  are free; the cache is LRU-pruned to the newest :data:`CACHE_LIMIT` files
  after every write.

The extraction/ffprobe helpers shell out to system ``ffmpeg``/``ffprobe``; the
offset-math functions (:func:`source_offset`, :func:`plan_extraction`,
:func:`clamp_dur`, :func:`cache_filename`) are pure and unit-testable without
any audio.

When a caller omits ``t_sec``, :func:`generate_ab_clips` auto-picks a start
point (TODO-232 part 2) via :func:`auto_pick_t_sec`: it decodes a bounded
performance-time search window of the pair's reference-speed source (falling
back to ``lb_a``) with the ``concert_ranker`` audio pipeline
(:func:`concert_ranker.audio.cache.build_track_cache`) and scores candidate
windows with the pure, audio-free :func:`pick_start_frame` — preferring the LB
curator method (TODO-187) of a musically quiet passage where a vocal is still
clearly present. Auto-pick never raises: any decode/analysis failure logs a
warning and falls back to a safe fixed offset.

Entry points: :func:`generate_ab_clips` (the POST /api/ab_clip backing
function) and :func:`get_pair_source_info` (also used by the GET
/api/tapematch/pairs ``ab_eligible`` enrichment, so both routes agree on
which run/speed_kind decides eligibility for a given pair). :func:`
eligible_lb_set` is a coarser single-run lookup, kept for callers that only
need "is this LB eligible in run X" without pairing semantics.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import numpy as np

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

# A/B eligibility (TODO-231 + TODO-233):
#   reference / aligned         — share the reference time-base directly; a
#                                 straight cut aligns them (v1, TODO-231).
#   constant-speed-offset       — a single constant tape-speed error; the
#                                 performance->source map is the linear
#                                 ``trim_head + t*factor`` with factor derived
#                                 from ``speed_ppm``, and the extracted window
#                                 is resampled back to reference speed before
#                                 serving (TODO-233 part 1).
# staircase/splice and speed-unknown stay excluded (per-segment / unknown
# warping — TODO-233 parts 2/3).
ELIGIBLE_SPEED_KINDS = frozenset({"reference", "aligned", "constant-speed-offset"})

# Below this |speed_ppm| the source runs within a few ms of reference over a
# clip and we keep the v1 straight-cut fast path (no resample re-encode). At
# 50 ppm the drift over a 60 s clip is 3 ms — inaudible. reference rows are
# exactly 0 ppm and aligned rows sit within ~175 ppm.
RESAMPLE_MIN_ABS_PPM = 50.0

# Stale-label recency gate (TODO-233): the 2026-07-06 confidence tightening
# (commit 936e0a64) made speed classification stricter, so ``aligned`` /
# ``constant-speed-offset`` labels from earlier runs can no longer be trusted
# for A/B eligibility. Only runs on/after this run_id qualify. run_id is a
# lexically sortable ``YYYYMMDD_HHMMSS`` timestamp.
MIN_ELIGIBLE_RUN_ID = "20260706_000000"

# RMS level-match (TODO-232 part 1): each clip is normalised to a common
# target so the listener judges fidelity, not loudness. Gain is capped to
# avoid amplifying near-silence, and further limited per clip so the corrected
# peak never exceeds the ceiling (no clipping).
AB_RMS_TARGET_DBFS = -20.0
AB_PEAK_CEIL_DBFS = -1.0
AB_MAX_GAIN_DB = 30.0

# Auto-pick start point (TODO-232 part 2): search a bounded performance-time
# window, skipping tuning/applause at both ends, for a quiet-vocal passage.
AUTO_PICK_SKIP_HEAD_SEC = 60.0
AUTO_PICK_SKIP_TAIL_SEC = 60.0
# Cap on how much performance time is decoded/analyzed per pick, so a 2h show
# is never decoded in full just to find a start point.
AUTO_PICK_SEARCH_SPAN_SEC = 300.0
AUTO_PICK_WIN_SEC = 20.0
AUTO_PICK_STEP_SEC = 5.0
AUTO_PICK_SR = 22050
# Vocal/speech band (LB curator method) vs. the broadband-quiet weight.
AUTO_PICK_VOCAL_BAND_HZ = (1000.0, 4000.0)
AUTO_PICK_FLOOR_PERCENTILE = 20.0
AUTO_PICK_BROADBAND_ALPHA = 0.5

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


def speed_factor(speed_ppm: float | None) -> float:
    """Return the source's speed factor relative to reference.

    Mirrors the tapematch embedding convention (``embed_extract.py``):
    ``nominal_t = (source_local - trim_head) / factor`` with
    ``factor = 1 + speed_ppm * 1e-6``. A source running fast (positive ppm)
    has ``factor > 1``.

    Args:
        speed_ppm: Measured speed deviation in parts-per-million (None -> 0).

    Returns:
        The multiplicative speed factor (1.0 for reference / unknown).
    """
    return 1.0 + float(speed_ppm or 0.0) * 1e-6


def source_offset(
    t_sec: float, trim_head_sec: float | None, factor: float = 1.0
) -> float:
    """Map a performance-time position to a source-local audio offset.

    Inverts the tapematch nominal-time convention
    ``nominal_t = (source_local - trim_head) / factor`` to
    ``source_local = trim_head + t * factor``. For reference / aligned sources
    *factor* is 1.0 and this reduces to the v1 ``t + trim_head``.

    Args:
        t_sec: Performance time in seconds (0 = first sounded note, post-trim).
        trim_head_sec: Seconds trimmed from the front of this source (may be
            None -> treated as 0).
        factor: Source speed factor from :func:`speed_factor` (1.0 = reference).

    Returns:
        The source-local audio offset in seconds.
    """
    return float(trim_head_sec or 0.0) + float(t_sec) * float(factor)


def raw_take_sec(dur_sec: float, factor: float) -> float:
    """Source-local span that resamples down to *dur_sec* at reference speed.

    A performance-time window of ``dur_sec`` occupies ``dur_sec * factor``
    seconds of the source's own (speed-offset) audio; extracting that raw span
    and resampling by ``1/factor`` yields ``dur_sec`` at reference speed.

    Args:
        dur_sec: Desired output (reference-speed) clip duration in seconds.
        factor: Source speed factor from :func:`speed_factor`.

    Returns:
        The raw source-local duration to extract, in seconds.
    """
    return float(dur_sec) * float(factor)


def is_run_eligible(run_id: str | None) -> bool:
    """Whether *run_id* is recent enough to trust its speed labels (TODO-233).

    Pre-936e0a64 runs classified speed too loosely, so their ``aligned`` /
    ``constant-speed-offset`` labels are not trustworthy for A/B eligibility.

    Args:
        run_id: The ``YYYYMMDD_HHMMSS`` run identifier (None -> not eligible).

    Returns:
        True when ``run_id >= MIN_ELIGIBLE_RUN_ID``.
    """
    return run_id is not None and str(run_id) >= MIN_ELIGIBLE_RUN_ID


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


def cache_filename(
    lb_number: int, offset_sec: float, dur_sec: int, speed_ppm: float = 0.0
) -> str:
    """Return the deterministic cache filename for one source's clip.

    The name depends on ``(lb_number, offset_sec, dur_sec, speed_ppm)`` where
    ``offset_sec`` is the resolved source-local offset (performance time +
    ``trim_head_sec``), NOT the raw performance time — a later run can change
    a source's trim, and keying on the post-trim offset means a changed trim
    produces a new file instead of serving a stale cached clip. ``speed_ppm``
    is folded in because a constant-speed-offset source is resampled to
    reference speed (TODO-233): the same lb/offset/dur at a different ppm is a
    different served clip. Values are rounded (ms / whole ppm) to avoid float
    representation noise.

    Args:
        lb_number: LB catalogue number of the source.
        offset_sec: Source-local start offset in seconds (post-trim).
        dur_sec: Clip duration in seconds.
        speed_ppm: The source's speed deviation in ppm (0 for reference).

    Returns:
        A ``ab_<lb>_<hash>.wav`` filename (no directory component).
    """
    key = (
        f"{int(lb_number)}:{round(float(offset_sec), 3)}:{int(dur_sec)}"
        f":{round(float(speed_ppm or 0.0))}"
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"ab_{int(lb_number)}_{digest}.wav"


def is_eligible_speed(speed_kind: str | None) -> bool:
    """Return whether *speed_kind* qualifies for A/B listening (TODO-231/233)."""
    return speed_kind in ELIGIBLE_SPEED_KINDS


# ── Auto-pick start point (TODO-232 part 2) ──────────────────────────────────
def pick_start_frame(
    cache: TrackCache,  # noqa: F821 - concert_ranker.audio.cache.TrackCache
    win_sec: float,
    step_sec: float,
) -> float | None:
    """Score sliding windows of *cache* and return the best clip start time.

    Implements the LB curator method (TODO-187): prefer a passage that is
    MUSICALLY QUIET (low broadband energy — the instrumentation has thinned
    out) but where a VOCAL is still clearly present (the 1-4 kHz speech/vocal
    band sits well above its own quiet-passage floor). Neither signal alone is
    enough — a silent gap is quiet but has no vocal to compare A/B on; a loud
    chorus has plenty of vocal but is dominated by everything else.

    The 1-4 kHz per-frame level is computed directly from ``cache.stft_mag``
    (masked to that band), not from ``cache.band_db`` — the latter is a single
    whole-track PSD scalar, whereas this needs a per-frame time series to find
    a *local* window. The floor is a low percentile of that same per-frame
    band series (i.e. the level during the track's quietest vocal moments —
    typically crowd/hiss noise rather than a singer), following
    :meth:`TrackCache.quiet_frame_mask`'s convention of using a percentile of
    a per-frame series as a floor.

    Args:
        cache: A :class:`concert_ranker.audio.cache.TrackCache` built from the
            decoded search-region audio.
        win_sec: Candidate window length in seconds (the eventual clip dur).
        step_sec: Hop between candidate window starts, in seconds.

    Returns:
        The winning window's start time in seconds into *cache* (i.e. an
        index into ``cache.times``' timeline), or ``None`` if the cache has
        too few frames to fit even one window.
    """
    times = cache.times
    n_frames = len(times)
    if n_frames < 2:
        return None
    frame_dt = float(times[1] - times[0])
    if frame_dt <= 0:
        return None

    win_frames = max(1, int(round(win_sec / frame_dt)))
    step_frames = max(1, int(round(step_sec / frame_dt)))
    if win_frames > n_frames:
        return None

    lo, hi = AUTO_PICK_VOCAL_BAND_HZ
    vocal_mask = (cache.freqs >= lo) & (cache.freqs < hi)
    if not vocal_mask.any():
        return None
    vocal_energy = (cache.stft_mag[vocal_mask, :].astype(np.float64) ** 2).sum(axis=0)
    vocal_db = 10.0 * np.log10(vocal_energy + 1e-12)

    vocal_floor_db = float(np.percentile(vocal_db, AUTO_PICK_FLOOR_PERCENTILE))
    broadband_floor_db = float(
        np.percentile(cache.frame_energy_db, AUTO_PICK_FLOOR_PERCENTILE)
    )

    best_score: float | None = None
    best_start = 0
    for start in range(0, n_frames - win_frames + 1, step_frames):
        end = start + win_frames
        vocal_snr = float(vocal_db[start:end].mean()) - vocal_floor_db
        broadband_excess = float(cache.frame_energy_db[start:end].mean()) - broadband_floor_db
        score = vocal_snr - AUTO_PICK_BROADBAND_ALPHA * broadband_excess
        if best_score is None or score > best_score:
            best_score = score
            best_start = start

    if best_score is None:
        return None
    return float(times[best_start])


def _decode_mono_region(
    files: list[str], segments: list[tuple[int, float, float]], sr: int
) -> np.ndarray:
    """Decode and concatenate a (possibly multi-file) span to mono float32 @ sr.

    Mirrors ``tools/tapematch/embed_extract.py``'s ``_decode_excerpt`` pattern
    (ffmpeg -> raw ``f32le`` on stdout) rather than :func:`_extract_segment`,
    which writes a served WAV file — this is an in-memory analysis buffer only.

    Args:
        files: Absolute FLAC paths in playback order.
        segments: ``plan_extraction`` output for the span to decode.
        sr: Target sample rate.

    Returns:
        A mono float32 array (empty if *segments* is empty).
    """
    parts: list[np.ndarray] = []
    for idx, start, take in segments:
        proc = subprocess.run(
            [
                FFMPEG_BIN, "-nostdin", "-v", "error",
                "-ss", f"{start:.3f}", "-t", f"{take:.3f}", "-i", files[idx],
                "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
            ],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            raise AbClipError(
                f"ffmpeg decode failed: {proc.stderr.decode(errors='replace')[:200]}"
            )
        parts.append(np.frombuffer(proc.stdout, dtype=np.float32))
    if not parts:
        return np.array([], dtype=np.float32)
    return np.concatenate(parts)


def auto_pick_t_sec(
    disk_path: str,
    trim_head_sec: float | None,
    factor: float,
    perf_dur_sec: float | None,
) -> float:
    """Auto-pick a performance-time clip start point for one source (TODO-232).

    Searches a bounded performance-time region (skipping ``AUTO_PICK_SKIP_
    HEAD_SEC`` / ``AUTO_PICK_SKIP_TAIL_SEC`` of tuning/applause at each end,
    and capped to ``AUTO_PICK_SEARCH_SPAN_SEC`` so a multi-hour show is never
    decoded in full), decodes the corresponding source-local span, builds a
    :class:`~concert_ranker.audio.cache.TrackCache` and scores it with
    :func:`pick_start_frame`, then maps the winning window back to performance
    time.

    Never raises: any decode or analysis failure is logged as a warning and a
    safe fallback (the skip-head offset, or 0.0 if the performance is too
    short to skip both ends) is returned instead — auto-pick must not block a
    clip request.

    Args:
        disk_path: Absolute path to the LB folder to analyze.
        trim_head_sec: Seconds trimmed from the front of this source.
        factor: Source speed factor from :func:`speed_factor` (1.0 = reference).
        perf_dur_sec: The source's known performance duration in seconds, or
            None if unknown.

    Returns:
        A performance-time position in seconds, always >= 0.
    """
    fallback = AUTO_PICK_SKIP_HEAD_SEC
    try:
        if perf_dur_sec is None:
            log.warning("auto_pick_t_sec: no perf_dur_sec for %s; using fallback", disk_path)
            return fallback

        region_start = AUTO_PICK_SKIP_HEAD_SEC
        region_end = float(perf_dur_sec) - AUTO_PICK_SKIP_TAIL_SEC
        if region_end - region_start < AUTO_PICK_WIN_SEC:
            # Too short to skip both ends and still fit a window.
            return 0.0
        region_end = min(region_end, region_start + AUTO_PICK_SEARCH_SPAN_SEC)

        tracks = folder_flac_durations(disk_path)
        files = [f for f, _ in tracks]
        durations = [d for _, d in tracks]
        if not files:
            log.warning("auto_pick_t_sec: no FLAC files in %s; using fallback", disk_path)
            return fallback

        src_start = source_offset(region_start, trim_head_sec, factor)
        src_span = raw_take_sec(region_end - region_start, factor)
        segments = plan_extraction(durations, src_start, src_span)
        if not segments:
            log.warning(
                "auto_pick_t_sec: search region out of range for %s; using fallback",
                disk_path,
            )
            return fallback

        mono = _decode_mono_region(files, segments, AUTO_PICK_SR)
        if mono.size < AUTO_PICK_SR * AUTO_PICK_WIN_SEC:
            log.warning(
                "auto_pick_t_sec: decoded region too short for %s; using fallback",
                disk_path,
            )
            return fallback

        from concert_ranker.audio.cache import build_track_cache

        cache = build_track_cache(mono, AUTO_PICK_SR)
        picked = pick_start_frame(cache, AUTO_PICK_WIN_SEC, AUTO_PICK_STEP_SEC)
        if picked is None:
            return fallback

        # `picked` is source-local time relative to src_start (the decode is
        # not speed-corrected, so it advances at `factor` source-seconds per
        # performance-second); map back to performance time and clamp to the
        # searched region as a safety net against rounding at the edges.
        t_perf = region_start + picked / float(factor or 1.0)
        return float(max(region_start, min(t_perf, region_end)))
    except Exception:
        log.warning("auto_pick_t_sec failed for %s", disk_path, exc_info=True)
        return fallback


# ── observations.db reads ────────────────────────────────────────────────────
def _open_obs_ro(obs_path: Path | str) -> sqlite3.Connection:
    """Open observations.db read-only. Raises :class:`ClipLockedError` if locked."""
    from backend import tapematch_sync as _tapematch_sync

    try:
        return _tapematch_sync._open_observations_db(obs_path)
    except RuntimeError as exc:
        raise ClipLockedError(str(exc)) from exc


def _speed_ppm_select(obs_conn: sqlite3.Connection) -> str:
    """Return the ``speed_ppm`` SELECT term, tolerating older DBs that lack it.

    The live observations.db always carries ``speed_ppm``; a legacy DB without
    it falls back to a literal 0.0 (treated as reference / no resample).
    """
    cols = {r[1] for r in obs_conn.execute("PRAGMA table_info(sources)")}
    return "speed_ppm" if "speed_ppm" in cols else "0.0 AS speed_ppm"


def get_source_info(
    obs_conn: sqlite3.Connection, concert_date: str, lb_number: int
) -> dict | None:
    """Return the most-recent ``sources`` row for one (date, LB), or None.

    Args:
        obs_conn: Open (read-only) observations.db connection.
        concert_date: ISO concert date.
        lb_number: LB catalogue number.

    Returns:
        A dict with ``trim_head_sec``, ``speed_kind``, ``speed_ppm``,
        ``perf_dur_sec``, ``total_dur_sec``, ``folder_name`` and ``run_id``
        from the latest run for this source, or None when no row exists.
    """
    row = obs_conn.execute(
        f"""
        SELECT trim_head_sec, speed_kind, {_speed_ppm_select(obs_conn)},
               perf_dur_sec, total_dur_sec, folder_name, run_id
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
        "speed_ppm": row["speed_ppm"],
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
        f"""
        SELECT lb_number, trim_head_sec, speed_kind, {_speed_ppm_select(obs_conn)},
               perf_dur_sec, total_dur_sec, folder_name, run_id
        FROM sources
        WHERE concert_date = ? AND run_id = ? AND lb_number IN (?, ?)
        """,
        (concert_date, run_row["run_id"], lb_a, lb_b),
    ):
        infos[int(row["lb_number"])] = {
            "trim_head_sec": row["trim_head_sec"],
            "speed_kind": row["speed_kind"],
            "speed_ppm": row["speed_ppm"],
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


_VOLUMEDETECT_RE = re.compile(r"(mean|max)_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")


def _measure_rms_dbfs(path: str) -> tuple[float | None, float | None]:
    """Return ``(mean_volume_db, max_volume_db)`` for a WAV via ffmpeg volumedetect.

    Args:
        path: Path to the (already extracted) clip.

    Returns:
        ``(mean_db, max_db)`` in dBFS, or ``(None, None)`` if detection failed
        (caller then skips level-matching for this clip).
    """
    proc = subprocess.run(
        [FFMPEG_BIN, "-nostdin", "-i", path, "-af", "volumedetect",
         "-f", "null", os.devnull],
        capture_output=True, text=True, timeout=120,
    )
    found = {k: float(v) for k, v in _VOLUMEDETECT_RE.findall(proc.stderr)}
    return found.get("mean"), found.get("max")


def compute_gain_db(mean_db: float | None, max_db: float | None) -> float:
    """Gain (dB) to bring a clip to ``AB_RMS_TARGET_DBFS`` without clipping.

    The gain moves the clip's mean level to the target, but is capped at
    ``AB_MAX_GAIN_DB`` (so near-silent clips are not blown up) and further
    limited so the boosted peak stays at/below ``AB_PEAK_CEIL_DBFS``.
    Attenuation is unbounded.

    Args:
        mean_db: Measured mean (RMS) level in dBFS, or None.
        max_db: Measured peak level in dBFS, or None.

    Returns:
        The gain in dB (0.0 when *mean_db* is unavailable).
    """
    if mean_db is None:
        return 0.0
    gain = AB_RMS_TARGET_DBFS - mean_db
    gain = min(gain, AB_MAX_GAIN_DB)
    if max_db is not None:
        gain = min(gain, AB_PEAK_CEIL_DBFS - max_db)
    return round(gain, 2)


def _finalize_clip(raw_path: str, out_path: str, factor: float, gain_db: float) -> None:
    """Resample a raw clip to reference speed and level-match it, into *out_path*.

    Applies, as one ffmpeg pass over the raw extraction:
      * speed correction (``asetrate``/``aresample``) when |ppm| warrants it —
        a constant-speed-offset source is played back at reference speed so it
        lines up in pitch and tempo with its partner (TODO-233);
      * an RMS gain (``volume``) for level-matching (TODO-232).
    When neither is needed (reference/aligned at unit gain) the raw file is
    moved to *out_path* unchanged.

    Args:
        raw_path: The raw extracted WAV (source-local, un-corrected).
        out_path: Destination clip path.
        factor: Source speed factor (1.0 = reference).
        gain_db: RMS level-match gain in dB (0.0 = none).
    """
    filters: list[str] = []
    if abs(factor - 1.0) * 1e6 >= RESAMPLE_MIN_ABS_PPM:
        # Reinterpret the raw samples at a scaled rate (correcting the tape
        # speed error, pitch included), then resample back to 44.1k.
        target_rate = int(round(44100 * factor))
        filters.append(f"asetrate={target_rate}")
        filters.append("aresample=44100")
    if abs(gain_db) >= 0.01:
        filters.append(f"volume={gain_db}dB")

    if not filters:
        # raw_path is in a scratch tmpdir (possibly another filesystem).
        shutil.move(raw_path, out_path)
        return
    _run_ffmpeg([
        "-i", raw_path, "-af", ",".join(filters),
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", out_path,
    ])


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
    disk_path: str,
    offset_sec: float,
    dur_sec: int,
    out_name: str,
    factor: float = 1.0,
    normalize: bool = True,
) -> str:
    """Extract one source's clip into the cache and return its filename.

    Idempotent: an already-cached clip (same *out_name*) is reused without
    re-extraction. The raw span extracted is ``dur_sec * factor`` seconds of
    the source's own (possibly speed-offset) audio; :func:`_finalize_clip`
    then resamples it to ``dur_sec`` at reference speed and RMS level-matches
    it (TODO-233 / TODO-232).

    Args:
        disk_path: Absolute path to the LB folder (already verified to exist).
        offset_sec: Source-local start offset in seconds.
        dur_sec: Output (reference-speed) clip duration in seconds.
        out_name: Deterministic cache filename (from :func:`cache_filename`).
        factor: Source speed factor from :func:`speed_factor` (1.0 = reference).
        normalize: Whether to RMS level-match the clip before serving.

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
    segments = plan_extraction(durations, offset_sec, raw_take_sec(dur_sec, factor))
    if not segments:
        raise BadRequestError(
            "requested position is beyond the recorded audio", error="t_out_of_range"
        )

    tmp_dir = tempfile.mkdtemp(prefix="ab_raw_")
    try:
        raw_path = os.path.join(tmp_dir, "raw.wav")
        _extract_clip(files, segments, raw_path)
        gain_db = 0.0
        if normalize:
            gain_db = compute_gain_db(*_measure_rms_dbfs(raw_path))
        _finalize_clip(raw_path, str(out_path), factor, gain_db)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    prune_cache()
    return out_name


def _resolve_auto_t_sec(
    main_conn: sqlite3.Connection,
    lb_a: int,
    info_a: dict,
    lb_b: int,
    info_b: dict,
) -> float:
    """Auto-pick a shared performance-time ``t_sec`` for an omitted request.

    Analyzes the pair's reference source when one side is ``speed_kind ==
    "reference"`` (its audio needs no speed correction), else falls back to
    ``lb_a``. Only one side is decoded/analyzed — the picked ``t_sec`` is a
    performance-time value shared by both clips.

    Args:
        main_conn: Open main-app DB connection (for ``my_collection``).
        lb_a: First LB number.
        info_a: :func:`get_source_info`-shaped dict for *lb_a*.
        lb_b: Second LB number.
        info_b: :func:`get_source_info`-shaped dict for *lb_b*.

    Returns:
        A performance-time position in seconds (see :func:`auto_pick_t_sec`
        for the fallback behavior on decode/analysis failure).
    """
    if info_a.get("speed_kind") == "reference":
        lb, info = lb_a, info_a
    elif info_b.get("speed_kind") == "reference":
        lb, info = lb_b, info_b
    else:
        lb, info = lb_a, info_a

    disk_path = resolve_disk_path(main_conn, lb)
    if not disk_path or not os.path.isdir(disk_path):
        # The main per-source loop below will raise the proper
        # FolderMissingError for whichever LB is actually missing; auto-pick
        # just needs a safe t so we get there instead of crashing here.
        log.warning("auto-pick: folder unavailable for LB-%s; using fallback t", lb)
        return AUTO_PICK_SKIP_HEAD_SEC

    factor = speed_factor(info.get("speed_ppm"))
    return auto_pick_t_sec(
        disk_path, info.get("trim_head_sec"), factor, info.get("perf_dur_sec")
    )


# ── Top-level orchestration ──────────────────────────────────────────────────
def generate_ab_clips(
    main_conn: sqlite3.Connection,
    obs_path: Path | str,
    concert_date: str,
    lb_a: int,
    lb_b: int,
    t_sec: float | None,
    dur_sec: int,
) -> dict:
    """Build both aligned A/B clips for a pair and return their metadata.

    Args:
        main_conn: Open main-app DB connection (for ``my_collection``).
        obs_path: Path to observations.db (trim/eligibility source of truth).
        concert_date: ISO concert date.
        lb_a: First LB number.
        lb_b: Second LB number.
        t_sec: Performance-time position in seconds (>= 0), or None to
            auto-pick a quiet-vocal-passage start point (TODO-232 part 2).
        dur_sec: Clip duration in seconds (already clamped by the caller).

    Returns:
        ``{"date", "lb_a", "lb_b", "t_sec", "dur_sec", "clip_a", "clip_b"}``
        where ``clip_a``/``clip_b`` are ``/api/ab_clip/<name>`` URLs and
        ``t_sec`` is the resolved (possibly auto-picked) value.

    Raises:
        BadRequestError, NotEligibleError, PairNotFoundError,
        FolderMissingError, ClipLockedError: Per the failure taxonomy.
    """
    if t_sec is not None and t_sec < 0:
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
            "pair is not cleanly aligned for A/B listening",
            speed_kind_a=info_a["speed_kind"], speed_kind_b=info_b["speed_kind"],
        )

    # Stale-label recency gate (TODO-233): the pair shares one run_id; an
    # eligible speed_kind from a pre-936e0a64 run is not trustworthy.
    if not is_run_eligible(info_a["run_id"]):
        raise NotEligibleError(
            "pair's speed labels predate the 2026-07-06 confidence gate; "
            "re-run tapematch to enable A/B listening",
            speed_kind_a=info_a["speed_kind"], speed_kind_b=info_b["speed_kind"],
            run_id=info_a["run_id"],
        )

    if t_sec is None:
        t_sec = _resolve_auto_t_sec(main_conn, lb_a, info_a, lb_b, info_b)

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
        ppm = info.get("speed_ppm")
        factor = speed_factor(ppm)
        offset = source_offset(t_sec, info["trim_head_sec"], factor)
        out_name = cache_filename(lb, offset, dur_sec, ppm or 0.0)
        clips[lb] = build_clip(disk_path, offset, dur_sec, out_name, factor=factor)

    return {
        "date": concert_date,
        "lb_a": lb_a,
        "lb_b": lb_b,
        "t_sec": t_sec,
        "dur_sec": dur_sec,
        "clip_a": f"/api/ab_clip/{clips[lb_a]}",
        "clip_b": f"/api/ab_clip/{clips[lb_b]}",
    }
