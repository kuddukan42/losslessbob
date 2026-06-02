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
    """Return {source_name: [ordered track paths]} for each top-level subfolder."""
    root = Path(root)
    sources = {}
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        sources[sub.name] = sub
    return sources


def list_tracks(source_dir: Path, exts):
    exts = {e.lower() for e in exts}
    tracks = [p for p in Path(source_dir).rglob("*") if p.suffix.lower() in exts]
    return sorted(tracks, key=_natural_key)


def source_report(source_dir: Path, exts):
    tracks = list_tracks(source_dir, exts)
    total = sum(audio.duration_sec(t) for t in tracks)
    return {"n_tracks": len(tracks), "total_sec": total, "tracks": tracks}


def concat_source(source_dir: Path, exts, target_sr, mono=False):
    """Load every track in order and concatenate into one continuous stream.
    Returns (samples (n,ch), sr, boundaries) where boundaries are the sample
    offsets of each track start (useful for mapping anchors back to tracks)."""
    tracks = list_tracks(source_dir, exts)
    if not tracks:
        raise ValueError(f"no audio in {source_dir}")
    chunks, boundaries, pos = [], [], 0
    ch = None
    for t in tracks:
        x, sr = audio.load(t, target_sr, mono=mono)
        if ch is None:
            ch = x.shape[1]
        elif x.shape[1] != ch:
            # normalize channel count (mono<->stereo) so concat is clean
            x = x.mean(axis=1, keepdims=True) if ch == 1 else np.repeat(x, ch, axis=1)
        boundaries.append(pos)
        chunks.append(x)
        pos += x.shape[0]
    stream = np.concatenate(chunks, axis=0)
    return stream, target_sr, np.array(boundaries)


def fmt_hms(sec):
    sec = int(round(sec))
    return f"{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"
