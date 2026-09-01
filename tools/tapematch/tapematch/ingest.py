"""Ingest layer: one top-level subfolder = one recording.

Walks each source folder recursively, sorts tracks into concert order by
natural path order (so d1/d2 nesting and flat folders both work), and
concatenates into a single continuous stream per source. Filenames are used
ONLY for ordering, then discarded -- we compare ~2-hour waveforms, not tracks.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
from . import audio

log = logging.getLogger(__name__)


_LB_TAG_RE = re.compile(r"LB-(\d+)")
_BRACKETED_RE = re.compile(r"\[[^\]]*\]")


def extract_own_lb_number(name: str) -> int | None:
    """Return the LB number that *name* itself belongs to, or None.

    Folder names occasionally embed a cross-referenced LB tag ahead of the
    folder's own -- e.g. ``"1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v"``
    is LB-10437's folder, which happens to note a relationship to LB-2204.
    A naive "first LB-\\d+ match" regex returns the cross-reference (2204)
    instead of the folder's own number (10437) -- BUG-277. This strips any
    bracketed ``[...]`` segments first (cross-references are conventionally
    parenthesized/bracketed annotations) and then takes the LAST remaining
    ``LB-NNNNN`` match, since the folder's own tag is conventionally trailing.

    Args:
        name: A staged or on-disk source folder name.

    Returns:
        The integer LB number, or None if no ``LB-NNNNN`` pattern is found.
    """
    stripped = _BRACKETED_RE.sub("", name)
    matches = list(_LB_TAG_RE.finditer(stripped))
    if not matches:
        matches = list(_LB_TAG_RE.finditer(name))
    if not matches:
        return None
    return int(matches[-1].group(1))


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


# Preferred order when one track exists in several formats: losslessly-compressed
# first, then uncompressed, then lossy. Anything unlisted sorts last.
_FORMAT_PREFERENCE = [".flac", ".shn", ".ape", ".wav", ".aiff", ".aif", ".m4a", ".mp3"]


def _format_rank(p: Path) -> int:
    """Return the preference rank of *p*'s extension (lower is better)."""
    suffix = p.suffix.lower()
    if suffix in _FORMAT_PREFERENCE:
        return _FORMAT_PREFERENCE.index(suffix)
    return len(_FORMAT_PREFERENCE)


def _dedupe_formats(tracks: list[Path]) -> tuple[list[Path], int]:
    """Keep one file per (parent, stem), preferring the best available format.

    A source folder frequently holds the same show twice — a lossless tree plus
    a decoded or lossy copy alongside it. Since ``audio_exts`` matches every
    format at once, both copies enter the track list, and because ``_natural_key``
    sorts ``x_01.flac`` immediately before ``x_01.wav`` the concatenated stream
    repeats each track back to back, leaving the source unalignable against any
    sibling rather than merely twice as long (BUG-326).

    Args:
        tracks: Candidate track paths, in any order.

    Returns:
        ``(kept, n_dropped)`` — the de-duplicated paths and how many were dropped.
    """
    best: dict[tuple[Path, str], Path] = {}
    for t in tracks:
        key = (t.parent, t.stem.lower())
        incumbent = best.get(key)
        if incumbent is None or _format_rank(t) < _format_rank(incumbent):
            best[key] = t
    kept = list(best.values())
    return kept, len(tracks) - len(kept)


def _dedupe_subtrees(tracks: list[Path], source_dir: Path) -> tuple[list[Path], int]:
    """Drop whole duplicated subtrees that repeat another subtree's contents.

    Some folders carry the same show under two directory layouts — e.g. LB-03685
    holds ``CD 1``..``CD 4`` and ``D1``..``D4`` with identical filenames and
    byte-identical checksum manifests. Each subtree is identified by the multiset
    of its files' ``(stem, size)`` pairs; when two subtrees share a signature only
    the first in natural order is kept (BUG-326).

    Args:
        tracks: Candidate track paths, already format-de-duplicated.
        source_dir: The source root, used to group by top-level subfolder.

    Returns:
        ``(kept, n_dropped)`` — the surviving paths and how many were dropped.
    """
    source_dir = Path(source_dir)
    groups: dict[Path, list[Path]] = {}
    for t in tracks:
        try:
            rel = t.relative_to(source_dir)
        except ValueError:
            rel = Path(t.name)
        # Group by the top-level subfolder; files at the root are their own group.
        top = source_dir / rel.parts[0] if len(rel.parts) > 1 else source_dir
        groups.setdefault(top, []).append(t)

    if len(groups) < 2:
        return tracks, 0

    seen: dict[frozenset, Path] = {}
    kept: list[Path] = []
    dropped = 0
    for top in sorted(groups, key=_natural_key):
        members = groups[top]
        try:
            sig = frozenset((p.stem.lower(), p.stat().st_size) for p in members)
        except OSError:
            sig = None
        if sig is not None and len(sig) == len(members) and sig in seen:
            log.warning("ingest: %s duplicates %s — skipping %d track(s)",
                        top.name, seen[sig].name, len(members))
            dropped += len(members)
            continue
        if sig is not None:
            seen[sig] = top
        kept.extend(members)
    return kept, dropped


# A nested pass counts as a second version of the show when it shares at least
# this fraction of the smaller side's track keys, over at least this many tracks.
_VERSION_MATCH_RATIO = 0.8
_MIN_VERSION_TRACKS = 3


def _version_key(track: Path, base: Path) -> str:
    """Return a track's position within a pass: its directory path plus stem, lowercased."""
    rel = track.relative_to(base)
    return "/".join(rel.parts[:-1] + (rel.stem,)).lower()


def _select_version(
    tracks: list[Path], source_dir: Path
) -> tuple[list[Path], tuple[Path, int, int] | None]:
    """Keep one pass of the show when the folder holds the same show twice (BUG-327).

    Distinct from ``_dedupe_formats`` / ``_dedupe_subtrees``, which only remove
    copies that are the *same* audio in another container or a byte-identical
    subtree. LB-07173 holds ``d1``/``d2`` at the top level and a second, complete
    ``d1``/``d2`` inside ``bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed``,
    with different byte sizes — two legitimately different masterings. Both were
    walked and concatenated into one stream, giving 3:27:33 against a 1:32:48
    date median, an ``[INFLATED]`` flag, and unusable correlations for the whole
    date.

    A nested directory is treated as a second pass when the track keys beneath
    it (directory path + stem, relative to that directory) match the keys of
    everything outside it. The **outer** pass is kept: in every case observed the
    nested copy is a re-master or fix of the folder's own layout, and
    source-identity work wants the least-processed pass. Choosing by track count
    instead would be fooled by patch directories (``d1/fix/Track08.fix.flac``),
    which repeat a track rather than add one. The dropped pass is logged by name
    so it can be analysed by pointing a run at that subfolder.

    A folder that genuinely holds two different concerts under this layout is
    reduced to the outer one, which the log line names; that is preferable to a
    concatenation that corrupts the whole date's verdict silently.

    Args:
        tracks: Candidate track paths, already format- and subtree-de-duplicated.
        source_dir: The source root.

    Returns:
        ``(kept, dropped)`` where ``dropped`` is ``(nested_root, n_inside,
        n_outside)`` for the discarded pass, or None if only one pass was found.
    """
    source_dir = Path(source_dir)
    rels: dict[Path, Path] = {}
    for t in tracks:
        try:
            rels[t] = t.relative_to(source_dir)
        except ValueError:
            return tracks, None  # unexpected layout; leave the source untouched

    candidates = {rel.parts[:k] for rel in rels.values() for k in range(1, len(rel.parts))}

    best: tuple[tuple[int, int], Path, list[Path], list[Path]] | None = None
    for parts in candidates:
        depth = len(parts)
        inside = [t for t, rel in rels.items() if rel.parts[:depth] == parts]
        outside = [t for t, rel in rels.items() if rel.parts[:depth] != parts]
        if min(len(inside), len(outside)) < _MIN_VERSION_TRACKS:
            continue
        nested_root = source_dir.joinpath(*parts)
        keys_in = {_version_key(t, nested_root) for t in inside}
        keys_out = {_version_key(t, source_dir) for t in outside}
        overlap = len(keys_in & keys_out)
        if overlap < _MIN_VERSION_TRACKS:
            continue
        if overlap / min(len(keys_in), len(keys_out)) < _VERSION_MATCH_RATIO:
            continue
        # Most-overlapping pass wins; ties go to the shallowest nesting.
        score = (overlap, -depth)
        if best is None or score > best[0]:
            best = (score, nested_root, inside, outside)

    if best is None:
        return tracks, None
    _, nested_root, inside, outside = best
    return outside, (nested_root, len(inside), len(outside))


def list_tracks(source_dir: Path, exts):
    """Return this source's tracks in concert order, de-duplicated.

    Args:
        source_dir: The source folder to walk.
        exts: Audio extensions to accept (matched case-insensitively).

    Returns:
        Track paths sorted into concert order by natural path order.
    """
    exts = {e.lower() for e in exts}
    tracks = [p for p in Path(source_dir).rglob("*")
              if p.is_file()
              and p.suffix.lower() in exts
              and not p.name.startswith("._")
              and "__MACOSX" not in p.parts]

    tracks, n_fmt = _dedupe_formats(tracks)
    if n_fmt:
        log.warning("ingest: %s holds the same track in several formats — "
                    "dropped %d duplicate file(s)", Path(source_dir).name, n_fmt)

    tracks = sorted(tracks, key=_natural_key)
    # _dedupe_subtrees logs each dropped subtree by name itself.
    tracks, _ = _dedupe_subtrees(tracks, source_dir)

    tracks, dropped_version = _select_version(tracks, source_dir)
    if dropped_version:
        nested_root, n_inside, n_outside = dropped_version
        log.warning(
            "ingest: %s holds the show twice — using the outer pass (%d track(s)) and "
            "skipping the nested copy in %r (%d track(s)); analyse that version by "
            "pointing a run at that subfolder (BUG-327)",
            Path(source_dir).name, n_outside,
            str(nested_root.relative_to(Path(source_dir))), n_inside,
        )

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
