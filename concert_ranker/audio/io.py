"""Real audio decode — the only place concert_ranker touches the filesystem.

Two reads per file, by design (see CC_CONCERT_RANKER.md, decision #2):

1. ONE bulk decode of the whole file to ``BULK_SR`` (22.05 kHz), mono+stereo,
   feeding :func:`concert_ranker.audio.cache.build_track_cache`. Every bulk-rate
   feature rides on this single decode + STFT.
2. A handful of short ``NATIVE_SR`` (44.1 kHz) windows for the HF probe — a
   cheap, *targeted* second read (ffmpeg ``-ss`` seeks), NOT a second full
   decode. Hiss/air/HF-ceiling/lossy are stationary enough that 8×20 s suffices.

Decoding goes through ffmpeg (resampling in-process) so only the analysis-rate
output ever lands in Python memory — the same approach as
``tools/tapematch/tapematch/audio.py``. This matters for hi-res sources whose
native-rate array would be many times larger.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from concert_ranker.audio.cache import (
    NativeProbe,
    TrackCache,
    build_native_probe,
    build_track_cache,
)
from concert_ranker.config import (
    BULK_SR,
    NATIVE_N_WINDOWS,
    NATIVE_SR,
    NATIVE_WINDOW_SEC,
    STFT_HOP,
    STFT_N_FFT,
)


class UnreadableAudioError(RuntimeError):
    """Raised when a file's audio cannot be probed or decoded by ffmpeg."""


def _ffprobe_info(path: str) -> dict:
    """Return ``{channels, samplerate, duration}`` via ffprobe.

    Some formats (SHN and friends) carry no frame count, so duration falls back
    to a decode-to-null pass that reads the final timestamp.
    """
    import re as _re
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels,sample_rate:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise UnreadableAudioError(f"ffprobe failed for {path!r}: {e}") from e
    try:
        data = json.loads(r.stdout)
        stream = data["streams"][0]
        channels = int(stream["channels"])
        samplerate = int(stream["sample_rate"])
    except (ValueError, KeyError, IndexError) as e:
        raise UnreadableAudioError(f"no audio stream in {path!r}: {e}") from e

    raw_dur = data.get("format", {}).get("duration")
    if raw_dur:
        duration = float(raw_dur)
    else:
        r2 = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-stats", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        matches = _re.findall(r"time=(\d+):(\d+):([\d.]+)", r2.stderr)
        if not matches:
            raise UnreadableAudioError(f"could not determine duration for {path!r}")
        h, mi, s = matches[-1]
        duration = int(h) * 3600 + int(mi) * 60 + float(s)
    return {"channels": channels, "samplerate": samplerate, "duration": duration}


def _ffmpeg_decode(path: str, target_sr: int, *, channels: int,
                   start: float | None = None, length: float | None = None) -> np.ndarray:
    """Decode (a slice of) a file to float32 PCM at ``target_sr``.

    Returns shape ``(n, channels)``. ``start``/``length`` (seconds) request a
    targeted window via ffmpeg seeking.
    """
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if length is not None:
        cmd += ["-t", f"{length:.3f}"]
    cmd += ["-f", "f32le", "-ar", str(target_sr), "-ac", str(channels), "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise UnreadableAudioError(f"ffmpeg decode failed for {path!r}: {e}") from e
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, channels)


# ─────────────────────────────────────────────────────────────────────────────
# Bulk cache (one decode per file)
# ─────────────────────────────────────────────────────────────────────────────
def load_bulk_cache(path: str | Path, *, sr: int = BULK_SR) -> TrackCache:
    """Decode the whole file once at ``sr`` and build the shared TrackCache."""
    path = str(path)
    info = _ffprobe_info(path)
    out_ch = 2 if info["channels"] >= 2 else 1
    x = _ffmpeg_decode(path, sr, channels=out_ch)
    if x.size == 0:
        raise UnreadableAudioError(f"decoded zero samples from {path!r}")
    if out_ch == 2:
        left, right = x[:, 0].copy(), x[:, 1].copy()
        mono = x.mean(axis=1)
    else:
        left = right = None
        mono = x[:, 0]
    return build_track_cache(mono, sr, left=left, right=right,
                             n_fft=STFT_N_FFT, hop=STFT_HOP, path=path)


# ─────────────────────────────────────────────────────────────────────────────
# Native HF probe (cheap targeted windows)
# ─────────────────────────────────────────────────────────────────────────────
def _window_starts(duration: float, n: int, win: float) -> list[float]:
    """Evenly spread ``n`` window start offsets across the performance body."""
    if duration <= win:
        return [0.0]
    usable_lo = 0.05 * duration
    usable_hi = max(usable_lo, 0.95 * duration - win)
    if usable_hi <= usable_lo:
        return [max(0.0, (duration - win) / 2)]
    return list(np.linspace(usable_lo, usable_hi, n))


def load_native_probe(path: str | Path, *, sr: int = NATIVE_SR,
                      n_windows: int = NATIVE_N_WINDOWS,
                      win_sec: float = NATIVE_WINDOW_SEC,
                      duration: float | None = None) -> NativeProbe:
    """Sample short native-rate windows and build the HF NativeProbe.

    Each window is a separate, cheap ffmpeg seek+decode (mono) — not a second
    full decode of the file.
    """
    path = str(path)
    if duration is None:
        duration = _ffprobe_info(path)["duration"]
    windows = []
    for start in _window_starts(duration, n_windows, win_sec):
        w = _ffmpeg_decode(path, sr, channels=1, start=start, length=win_sec)
        if w.size:
            windows.append(w[:, 0])
    return build_native_probe(windows, sr)


def load_caches(path: str | Path) -> tuple[TrackCache, NativeProbe]:
    """Build both caches for one file: bulk decode + native HF probe.

    Returns ``(TrackCache, NativeProbe)``. The bulk decode happens once; the
    native windows are sampled separately at NATIVE_SR.
    """
    cache = load_bulk_cache(path)
    probe = load_native_probe(path, duration=cache.duration_sec)
    return cache, probe
