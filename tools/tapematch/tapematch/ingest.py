"""Ingest layer: one top-level subfolder = one recording.

Walks each source folder recursively, sorts tracks into concert order by
natural path order (so d1/d2 nesting and flat folders both work), and
concatenates into a single continuous stream per source. Filenames are used
ONLY for ordering, then discarded -- we compare ~2-hour waveforms, not tracks.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
from . import audio


def _natural_key(p: Path):
    """Sort key: directory components first (d1 before d2), then natural-
    numeric within filename so '2' < '10'."""
    parts = p.relative_to(p.anchor).parts
    key = []
    for part in parts:
        chunks = re.split(r"(\d+)", part)
        key.append([int(c) if c.isdigit() else c.lower() for c in chunks])
    return key


def discover_sources(root: Path):
    """Return {source_name: Path} for each top-level subfolder."""
    root = Path(root)
    sources = {}
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        sources[sub.name] = sub
    return sources


def list_tracks(source_dir: Path, exts):
    exts = {e.lower() for e in exts}
    tracks = [p for p in Path(source_dir).rglob("*")
              if p.is_file()
              and p.suffix.lower() in exts
              and not p.name.startswith("._")
              and "__MACOSX" not in p.parts]
    return sorted(tracks, key=_natural_key)


class UnreadableSourceError(Exception):
    """Raised by source_report when one of a source's tracks can't be decoded.

    Carries the offending source directory and track path so callers can
    exclude the whole source with a clear message rather than aborting.
    """

    def __init__(self, source_dir: Path, track: Path, cause: Exception):
        self.source_dir = source_dir
        self.track = track
        super().__init__(f"source {source_dir} excluded: unreadable file {track} ({cause})")


def source_report(source_dir: Path, exts):
    tracks = list_tracks(source_dir, exts)
    total = 0.0
    for t in tracks:
        try:
            total += audio.duration_sec(t)
        except audio.UnreadableAudioError as e:
            raise UnreadableSourceError(source_dir, t, e) from e
    return {"n_tracks": len(tracks), "total_sec": total, "tracks": tracks}


def concat_source(source_dir: Path, exts, target_sr, mono=False):
    """Load every track in order and concatenate into one continuous stream.

    Pre-allocates the output array from probed durations so each track is
    loaded, copied into the output, and freed immediately — peak RAM is
    output + one track rather than output + all tracks (old np.concatenate
    approach doubled peak memory).

    Returns (samples (n,ch), sr, boundaries) where boundaries are the sample
    offsets of each track start.
    """
    tracks = list_tracks(source_dir, exts)
    if not tracks:
        raise ValueError(f"no audio in {source_dir}")

    # Probe all tracks once: channel count from first, frame totals from all.
    probes = [audio.probe(t, target_sr) for t in tracks]
    ch = 1 if mono else probes[0]["channels"]

    # Estimate total frames — add 1 s headroom for duration→samples rounding.
    total_frames = sum(p["frames"] for p in probes) + target_sr

    out = np.empty((total_frames, ch), dtype="float32")
    boundaries: list[int] = []
    pos = 0

    for t in tracks:
        x, _ = audio.load(t, target_sr, mono=mono)
        if x.ndim == 1:
            x = x.reshape(-1, 1)
        # Normalise channel count if tracks differ (e.g. mono track in stereo set).
        if x.shape[1] != ch:
            x = (x.mean(axis=1, keepdims=True) if ch == 1
                 else np.repeat(x, ch, axis=1))
        n = min(x.shape[0], total_frames - pos)
        boundaries.append(pos)
        out[pos:pos + n] = x[:n]
        pos += n
        del x  # free track immediately

    return out[:pos], target_sr, np.array(boundaries)


def fmt_hms(sec):
    sec = int(round(sec))
    return f"{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"
