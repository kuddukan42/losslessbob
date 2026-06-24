"""Per-recording scan: folder of audio files → one RAW aggregated metric dict.

This is the in-memory unit of work a consumer process runs (see
:mod:`concert_ranker.runner`). It decodes every track ONCE, extracts the raw
metric families, and aggregates them to a single per-recording dict — the
payload stored in ``quality_recording_metrics.metric_json``.

Nothing here bands, scores, or ranks: per the scan-once guarantee, only RAW
values are produced and stored. Banding/scoring happens later from those values.

Sibling-relative quantities (notably ``completeness`` = this recording's length
vs the longest in its family) are NOT known at scan time — they are derived at
rank time in :mod:`concert_ranker.families`. The scan stores the absolute
``duration_sec`` instead.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from concert_ranker import features as F
from concert_ranker.audio.io import UnreadableAudioError, load_caches

log = logging.getLogger("concert_ranker.scan")

# Lossless + common lossy containers. Lossy ones still get scanned (the lossy
# detector is the point); extension alone is never trusted as a quality signal.
AUDIO_EXTS = {".flac", ".shn", ".wav", ".wave", ".aif", ".aiff", ".ape",
              ".wv", ".m4a", ".alac", ".mp3", ".ogg", ".opus"}


def find_audio_files(folder: str | Path) -> list[Path]:
    """Return audio files in ``folder`` (recursive), sorted for stable order."""
    folder = Path(folder)
    files = [p for p in folder.rglob("*") if p.suffix.lower() in AUDIO_EXTS and p.is_file()]
    return sorted(files)


def extract_track(path: str | Path) -> dict:
    """Decode one file and return its flat RAW metric dict (+ ``duration_sec``).

    Underscore-prefixed internal keys (e.g. ``_mono``) are dropped.
    """
    cache, probe = load_caches(path)
    raw: dict[str, float] = {}
    raw.update(F.extract_clarity(cache))
    raw.update(F.extract_crowd(cache))
    raw.update(F.extract_tonal(cache))
    raw.update(F.extract_distortion(cache))
    raw.update(F.extract_spatial(cache))
    raw.update(F.extract_hf_native(probe))
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    raw["duration_sec"] = cache.duration_sec
    return raw


# Defect counts/fractions where the WORST track defines the recording — one
# badly-glitched or clipped track is a problem even if the rest are clean, so
# median (robust for continuous tonal characteristics) would hide it.
_WORST_TRACK_METRICS = frozenset({"dropout_count", "clip_fraction", "hum_excess_db"})


def aggregate_tracks(track_raws: list[dict]) -> dict[str, float]:
    """Aggregate per-track raw dicts to one per-recording dict.

    Continuous tonal/spatial characteristics use a robust median across tracks;
    defect metrics in :data:`_WORST_TRACK_METRICS` use the max (worst track),
    because a single glitchy/clipped track is a real defect the median would mask.
    NaNs (e.g. ``lr_corr`` on mono tracks) are ignored per metric. ``duration_sec``
    is excluded — the recording duration is summed separately.
    """
    if not track_raws:
        return {}
    keys = set().union(*[set(d.keys()) for d in track_raws]) - {"duration_sec"}
    out: dict[str, float] = {}
    for k in keys:
        vals = np.array([d.get(k, np.nan) for d in track_raws], dtype=float)
        if np.isnan(vals).all():
            out[k] = float("nan")
        elif k in _WORST_TRACK_METRICS:
            out[k] = float(np.nanmax(vals))
        else:
            out[k] = float(np.nanmedian(vals))
    return out


def scan_folder(folder: str | Path) -> dict:
    """Scan one recording folder → aggregated raw metrics + per-track detail.

    Returns ``{"metrics": {aggregated raw}, "tracks": [per-track raw],
    "duration_sec": total, "n_tracks": N}``. Raises
    :class:`~concert_ranker.audio.io.UnreadableAudioError` if no track decodes.
    """
    files = find_audio_files(folder)
    if not files:
        raise UnreadableAudioError(f"no audio files in {folder!r}")
    tracks: list[dict] = []
    total_dur = 0.0
    for f in files:
        try:
            raw = extract_track(f)
        except UnreadableAudioError as e:
            log.warning("skipping unreadable track %s: %s", f, e)
            continue
        total_dur += float(raw.get("duration_sec") or 0.0)
        tracks.append(raw)
    if not tracks:
        raise UnreadableAudioError(f"no decodable audio in {folder!r}")
    return {
        "metrics": aggregate_tracks(tracks),
        "tracks": tracks,
        "duration_sec": total_dur,
        "n_tracks": len(tracks),
    }
