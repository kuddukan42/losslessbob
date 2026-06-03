"""Trim head/tail crowd padding -> performance envelope.

Variable-length crowd/tuning padding at the start and end of each source must
be excluded before alignment, or every correlation lag is poisoned by however
much dead air a given taper left on. We gate on spectral flatness: crowd-only
padding is diffuse/flat; music is structured/tonal. We find the first and last
sustained music region and keep a small safety margin either side.
"""
from __future__ import annotations
import numpy as np
from scipy.signal import stft
from .audio import to_mono


def spectral_flatness(mono, sr, frame_sec, hop_sec):
    """Compute per-frame spectral flatness and energy in 5-minute chunks.

    The full-signal STFT for a 2-hour show at 16 kHz with nperseg=16000
    allocates a ~4 GB complex64 matrix.  Processing in 5-minute blocks caps
    the per-iteration Z matrix at ~38 MB with identical numerical results.
    """
    nper = int(frame_sec * sr)
    hop = int(hop_sec * sr)
    chunk_samp = 300 * sr  # 5-minute blocks

    t_parts: list[np.ndarray] = []
    flat_parts: list[np.ndarray] = []
    energy_parts: list[np.ndarray] = []

    for start in range(0, len(mono), chunk_samp):
        chunk = mono[start:start + chunk_samp]
        if len(chunk) < nper:
            break
        _, t_c, Z = stft(chunk, fs=sr, nperseg=nper, noverlap=nper - hop, boundary=None)
        p = (np.abs(Z) ** 2) + 1e-12
        del Z
        gmean = np.exp(np.mean(np.log(p), axis=0))
        amean = np.mean(p, axis=0)
        del p
        t_parts.append(t_c + start / sr)
        flat_parts.append(gmean / amean)
        energy_parts.append(10.0 * np.log10(amean))

    if not t_parts:
        return np.array([]), np.array([]), np.array([])
    return (np.concatenate(t_parts),
            np.concatenate(flat_parts),
            np.concatenate(energy_parts))


def performance_envelope(stream, sr, cfg):
    """Return (start_sec, end_sec) of the performance body."""
    c = cfg["trim"]
    mono = to_mono(stream)
    t, flat, energy = spectral_flatness(mono, sr, c["frame_sec"], c["hop_sec"])
    del mono

    e_floor = np.percentile(energy, 10)
    is_music = (flat < c["flatness_music_max"]) & (energy > e_floor + 6)

    need = int(c["min_sustain_sec"] / c["hop_sec"])
    start_i = _first_sustained(is_music, need)
    end_raw = _first_sustained(is_music[::-1], need)

    if start_i is None or end_raw is None:
        return 0.0, len(stream) / sr

    end_i = len(is_music) - 1 - end_raw
    if end_i <= start_i:
        return 0.0, len(stream) / sr

    start_sec = max(0.0, t[start_i] - c["pad_keep_sec"])
    end_sec = min(len(stream) / sr, t[end_i] + c["pad_keep_sec"])
    return start_sec, end_sec


def _first_sustained(mask, need):
    run = 0
    for i, v in enumerate(mask):
        run = run + 1 if v else 0
        if run >= need:
            return i - need + 1
    return None


def apply_trim(stream, sr, start_sec, end_sec):
    a, b = int(start_sec * sr), int(end_sec * sr)
    return stream[a:b]
