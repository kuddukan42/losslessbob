"""Assemble a seedable copy of a recording without touching the collection.

A tracker's torrent usually contains the LosslessBob ``LBF-*`` sidecars
(checksum lists, info text, DigiFlawFinder reports) that the curated collection
folder does not keep alongside the audio. The folder therefore verifies at
99-point-something, and handing that to a BitTorrent client makes it *download*
the remainder into the collection folder.

This module builds a third location — the overlay — that contains:

* the audio, **hardlinked** from the collection (no extra disk space, and the
  bytes are literally the same inode, so the client seeds the real files);
* the sidecars, **copied** from ``data/site/files/`` where the site crawl
  already stored them;
* nothing at all for files no local source can satisfy — the client fetches
  those, into the overlay, never into the collection.

The one sharp edge is piece alignment: a piece can straddle a file boundary, so
a file adjacent to a missing one may be written to while the client completes
that piece. Any collection file sharing a piece with an unresolved file is
therefore **copied instead of hardlinked**, so a write can never reach the
collection's inode.

Nothing here ever opens a file inside the source collection folder for writing.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from backend.torrent_verify import TorrentInfo, VerifyResult, verify_folder

logger = logging.getLogger(__name__)

# Actions the plan can assign to a torrent file.
LINK = "link"        # hardlink from the collection — free, shares the inode
COPY = "copy"        # byte copy — sidecars, and anything a client might write to
REFETCH = "refetch"  # re-download the pristine original from losslessbob.com
FETCH = "fetch"      # no local source; the BitTorrent client downloads it

#: How many of an ambiguous file's pieces to hash before accepting a candidate.
#: A sidecar sits inside a single piece, so it is fully decided by one hash; a
#: multi-piece file is sampled instead of hashed end to end, because two
#: byte-identical-in-length audio files diverge in their very first piece and
#: the whole overlay is piece-verified afterwards regardless.
_DISAMBIGUATION_PIECES = 4


@dataclass
class PlanEntry:
    """One torrent file and how the overlay will satisfy it.

    Attributes:
        rel_path: The torrent's path for this file, root segment included.
        action: One of :data:`LINK`, :data:`COPY`, :data:`REFETCH`,
            :data:`FETCH`.
        size: The exact byte size the torrent expects.
        source: Local path (or URL, for a re-fetch) the bytes come from.
        reason: Which store supplied it, for the human reading the log.
        note: How a size ambiguity was settled, when there was one — set by
            the piece-hash pass and by :func:`repair_overlay`, and kept apart
            from ``reason`` so the piece-safety pass cannot overwrite it.
    """

    rel_path: str
    action: str
    size: int
    source: str = ""
    reason: str = ""
    note: str = ""


@dataclass
class OverlayPlan:
    """What building the overlay would do.

    Attributes:
        target_dir: Overlay directory the plan builds.
        entries: One :class:`PlanEntry` per torrent file, in torrent order.
        note: Optional human-readable remark about the plan as a whole.
        candidates: ``{file index: every equally valid local source}``, in
            preference order, recorded only where more than one local file has
            the exact size the torrent wants. This is what
            :func:`repair_overlay` re-picks from when a built overlay hashes
            short: a size match is not a content match, and the wrong 1 KB
            sidecar strands the piece it shares with a 17 MB flac.
    """

    target_dir: Path
    entries: list[PlanEntry] = field(default_factory=list)
    note: str = ""
    candidates: dict[int, list[Path]] = field(default_factory=dict, repr=False)

    def _bytes(self, action: str) -> int:
        return sum(e.size for e in self.entries if e.action == action)

    @property
    def link_bytes(self) -> int:
        """Bytes satisfied by hardlink (costing no additional space)."""
        return self._bytes(LINK)

    @property
    def copy_bytes(self) -> int:
        """Bytes that will be duplicated on disk."""
        return self._bytes(COPY)

    @property
    def refetch_bytes(self) -> int:
        """Bytes to be re-downloaded from losslessbob.com."""
        return self._bytes(REFETCH)

    @property
    def fetch_bytes(self) -> int:
        """Bytes the BitTorrent client will have to download."""
        return self._bytes(FETCH)

    def count(self, action: str) -> int:
        """Return how many files carry the given action."""
        return sum(1 for e in self.entries if e.action == action)

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        return (
            f"{self.count(LINK)} linked ({self.link_bytes / 1e6:.1f} MB free), "
            f"{self.count(COPY)} copied ({self.copy_bytes / 1e6:.1f} MB), "
            f"{self.count(REFETCH)} re-fetched ({self.refetch_bytes / 1e6:.1f} MB), "
            f"{self.count(FETCH)} left to the swarm ({self.fetch_bytes / 1e6:.1f} MB)"
        )


def _index_sources(dirs: list[Path]) -> dict[str, list[Path]]:
    """Index every file under the given directories by path suffix.

    A tracker's torrent is often nested — ``<root>/<show>/cd-1/01 Track01.flac``
    — while the collection files the same audio under its own layout. Indexing
    only basenames both misses everything below the top level and collides
    (``cd-1/01 Track01.flac`` and ``cd-2/01 Track01.flac`` share a basename), so
    each file is registered under **every** suffix of its relative path:
    ``01 Track01.flac``, ``cd-1/01 Track01.flac``, and so on. The resolver can
    then ask for the most specific match first.

    Directories are walked recursively and earlier ones win, so the caller
    controls precedence.

    Args:
        dirs: Directories to index, most-preferred first.

    Returns:
        A suffix→paths mapping; each list is in directory-preference order.
    """
    found: dict[str, list[Path]] = {}
    for directory in dirs:
        try:
            paths = sorted(directory.rglob("*"))
        except OSError:
            continue
        for path in paths:
            try:
                if not path.is_file():
                    continue
                parts = path.relative_to(directory).parts
            except (OSError, ValueError):
                continue
            for depth in range(1, len(parts) + 1):
                found.setdefault("/".join(parts[-depth:]), []).append(path)
    return found



def _file_offsets(info: TorrentInfo) -> list[int]:
    """Return each file's absolute offset in the torrent's byte stream.

    Args:
        info: Parsed torrent metadata.

    Returns:
        One offset per entry in ``info.files``, same order.
    """
    offsets: list[int] = []
    total = 0
    for _rel_path, size in info.files:
        offsets.append(total)
        total += size
    return offsets


def _read_piece(
    info: TorrentInfo, offsets: list[int], sources: dict[int, Path], index: int
) -> bytes | None:
    """Assemble one piece's bytes from a per-file mapping of local sources.

    Args:
        info: Parsed torrent metadata.
        offsets: Offsets from :func:`_file_offsets`.
        sources: ``{file index: local path}``. Files absent from the mapping
            make the piece uncheckable rather than wrong.
        index: Piece index to assemble.

    Returns:
        Exactly the piece's bytes, or None when any covering file has no
        readable local source of the right length — in which case the caller
        must treat the piece as *unknown*, not as a hash failure.
    """
    start = index * info.piece_length
    end = min(start + info.piece_length, info.total_size)
    if end <= start:
        return None

    out = bytearray()
    for i, (_rel_path, size) in enumerate(info.files):
        f_start = offsets[i]
        f_end = f_start + size
        if f_end <= start or f_start >= end:
            continue
        path = sources.get(i)
        if path is None:
            return None
        lo, hi = max(start, f_start) - f_start, min(end, f_end) - f_start
        try:
            with path.open("rb") as handle:
                handle.seek(lo)
                chunk = handle.read(hi - lo)
        except OSError:
            return None
        if len(chunk) != hi - lo:
            return None
        out.extend(chunk)
    return bytes(out) if len(out) == end - start else None


def _sample_pieces(first: int, last: int, limit: int) -> list[int]:
    """Choose up to ``limit`` piece indices spread across an inclusive range.

    Args:
        first: First piece index of the span.
        last: Last piece index of the span, inclusive.
        limit: Maximum number of indices to return; must be at least 2.

    Returns:
        Ascending piece indices, always including both ends.
    """
    if last - first + 1 <= limit:
        return list(range(first, last + 1))
    step = (last - first) / (limit - 1)
    return sorted({first + round(i * step) for i in range(limit)})


def _score_candidate(
    info: TorrentInfo,
    offsets: list[int],
    ranges: list[tuple[int, int]],
    sources: dict[int, Path],
    index: int,
    candidate: Path,
    pieces: list[int] | None = None,
) -> tuple[int, int]:
    """Hash the pieces one candidate source would occupy.

    Args:
        info: Parsed torrent metadata.
        offsets: Offsets from :func:`_file_offsets`.
        ranges: Piece ranges from :meth:`TorrentInfo.file_piece_ranges`.
        sources: The current ``{file index: local path}`` assignment; the
            neighbours sharing a piece with this file are read from it.
        index: Index of the torrent file being decided.
        candidate: The local file to try for it.
        pieces: Exact piece indices to hash, overriding the spread sample.
            :func:`repair_overlay` passes the pieces that actually failed.

    Returns:
        ``(checked, good)`` — how many of the sampled pieces could be hashed at
        all, and how many matched the torrent. ``checked == 0`` means the
        candidate is undecidable here (a neighbour is still unresolved).
    """
    probe = dict(sources)
    probe[index] = candidate
    first, last = ranges[index]
    wanted = (
        pieces if pieces is not None
        else _sample_pieces(first, last, _DISAMBIGUATION_PIECES)
    )
    checked = good = 0
    for piece in wanted:
        if piece >= info.piece_count:
            continue
        data = _read_piece(info, offsets, probe, piece)
        if data is None:
            continue
        checked += 1
        if hashlib.sha1(data).digest() == info.piece_hash(piece):
            good += 1
    return checked, good


def _pick_by_piece_hash(
    info: TorrentInfo,
    offsets: list[int],
    ranges: list[tuple[int, int]],
    sources: dict[int, Path],
    index: int,
    candidates: list[Path],
    pieces: list[int] | None = None,
) -> Path | None:
    """Choose the candidate whose bytes satisfy the torrent's piece hashes.

    Args:
        info: Parsed torrent metadata.
        offsets: Offsets from :func:`_file_offsets`.
        ranges: Piece ranges from :meth:`TorrentInfo.file_piece_ranges`.
        sources: The current ``{file index: local path}`` assignment.
        index: Index of the torrent file being decided.
        candidates: Every local file of exactly the right size, in preference
            order.
        pieces: Exact piece indices to hash, overriding the spread sample.

    Returns:
        The candidate that hashed clean, or None when none did (or none could
        be checked, because a file sharing its pieces is still unresolved).
    """
    for candidate in candidates:
        checked, good = _score_candidate(
            info, offsets, ranges, sources, index, candidate, pieces
        )
        if checked and checked == good:
            return candidate
    return None


def _disambiguate(
    info: TorrentInfo,
    ranges: list[tuple[int, int]],
    sources: dict[int, Path],
    choices: dict[int, list[Path]],
    entries: dict[int, PlanEntry],
) -> list[int]:
    """Re-pick every size-ambiguous file by hashing the pieces it sits in.

    Several local files can share a torrent entry's exact size — two LB folders
    each holding a 1,095-byte ``.md5`` for the same show, or ``cd-1``/``cd-2``
    tracks of equal length — and a size match says nothing about the bytes.
    Files are decided narrowest-span first, so a sidecar is settled using the
    audio it shares a piece with rather than the other way round.

    Args:
        info: Parsed torrent metadata.
        ranges: Piece ranges from :meth:`TorrentInfo.file_piece_ranges`.
        sources: ``{file index: local path}``, updated in place.
        choices: ``{file index: candidates}`` for the ambiguous entries.
        entries: ``{file index: plan entry}``, whose ``source``/``reason`` are
            updated in place when the pick changes.

    Returns:
        The file indices whose source was changed.
    """
    offsets = _file_offsets(info)
    changed: list[int] = []
    order = sorted(choices, key=lambda i: (ranges[i][1] - ranges[i][0], i))
    for index in order:
        candidates = choices[index]
        chosen = _pick_by_piece_hash(
            info, offsets, ranges, sources, index, candidates
        )
        entry = entries[index]
        if chosen is None:
            entry.note = (
                f"{len(candidates)} same-size candidates, none verified"
            )
            logger.warning(
                "%s: %d local files have the exact size the torrent wants and "
                "none could be settled on the piece hashes (a file sharing its "
                "piece is still unresolved) — keeping %s, which may be the "
                "wrong copy",
                entry.rel_path, len(candidates), sources.get(index),
            )
            continue
        if chosen == sources.get(index):
            continue
        logger.info(
            "%s: %d local files match the size; piece hashes pick %s",
            entry.rel_path, len(candidates), chosen,
        )
        sources[index] = chosen
        entry.source = str(chosen)
        entry.note = f"piece-verified pick of {len(candidates)} same-size copies"
        changed.append(index)
    return changed


#: The prefix losslessbob.com puts on every sidecar it publishes.
_LBF_PREFIX_RE = re.compile(r"^lbf-\d{3,6}-")

#: Format markers the site's filename carries that the taper's original does
#: not, or vice versa — ``lbdir-bd00-07-19a.txt.md5`` on disk is the torrent's
#: ``lbdir-bd00-07-19a.shnf.md5``.
_FORMAT_TOKENS = frozenset({"txt", "shnf", "flacf", "wavf"})


def _alias_keys(name: str) -> set[str]:
    """Reduce a sidecar filename to the forms that survive the site's renaming.

    losslessbob.com republishes a taper's sidecar under a name of its own:
    prefixed with ``LBF-<lb>-``, the containing folder folded into the
    filename, punctuation flattened to dashes, a format marker swapped
    (``…bd00-07-19a.txt.md5`` on disk for the torrent's ``…shnf.md5``) and a
    ``.txt`` appended to anything that is not already text. None of that
    changes the bytes, so a torrent built from the taper's copy and a mirror
    holding the site's copy are the same file under two names — which is why an
    old post can look unseedable when the only thing missing is a 1 KB text
    file we already have.

    Args:
        name: A bare filename.

    Returns:
        Normalised keys: lowercase, the LBF prefix and interior format markers
        dropped, punctuation collapsed to single dashes, plus the variant
        without the site's appended ``.txt``.
    """
    stripped = _LBF_PREFIX_RE.sub("", name.lower())
    tokens = [t for t in re.split(r"[^a-z0-9]+", stripped) if t]
    if not tokens:
        return set()
    # A format marker is noise anywhere but the end, where it is the extension
    # proper — the only thing separating "foo.md5" from "foo.txt".
    kept = [t for i, t in enumerate(tokens)
            if t not in _FORMAT_TOKENS or i == len(tokens) - 1]
    keys = {"-".join(kept)}
    if len(kept) > 2 and kept[-1] == "txt":
        keys.add("-".join(kept[:-1]))
    return keys


def _index_aliases(*indexes: dict[str, list[Path]]) -> list[tuple[set[str], Path]]:
    """Build the alias lookup used for files no exact name matched.

    Args:
        *indexes: Suffix indexes from :func:`_index_sources`, most-preferred
            first.

    Returns:
        (alias keys, path) pairs, one per distinct file, in preference order.
    """
    seen: set[Path] = set()
    pairs: list[tuple[set[str], Path]] = []
    for index in indexes:
        for paths in index.values():
            for path in paths:
                if path in seen:
                    continue
                seen.add(path)
                pairs.append((_alias_keys(path.name), path))
    return pairs


def _alias_candidates(aliases: list[tuple[set[str], Path]], rel_path: str,
                      size: int) -> list[Path]:
    """Find every renamed local copy of one torrent entry.

    A candidate qualifies when it shares an alias key with the wanted file, or
    when one of its keys *ends* with one — the site folds the containing folder
    into the name, so ``BD---Toads-Place-d5-bd1990-1-12-d5-Toads-LTE.txt`` ends
    with the key of the torrent's ``bd1990-1-12-d5-Toads-LTE.txt``. The size
    must match exactly; where several renamed copies match it, the caller
    settles the choice on the piece hashes.

    Args:
        aliases: Pairs from :func:`_index_aliases`.
        rel_path: The torrent's path for this file.
        size: The exact byte size the torrent expects.

    Returns:
        The renamed local files of exactly that size, exact key matches first,
        then suffix matches; empty when nothing matches.
    """
    wanted = _alias_keys(Path(rel_path).name)
    if not wanted:
        return []
    exact_hits: list[Path] = []
    suffix_hits: list[Path] = []
    for keys, path in aliases:
        exact = bool(keys & wanted)
        if not exact and not any(k.endswith(f"-{w}") for k in keys for w in wanted):
            continue
        try:
            if path.stat().st_size != size:
                continue
        except OSError:
            continue
        (exact_hits if exact else suffix_hits).append(path)
    return exact_hits + suffix_hits


def _resolve_candidates(
    index: dict[str, list[Path]], rel_path: str, size: int
) -> list[Path]:
    """Find every indexed file that could satisfy one torrent entry.

    Suffixes are tried longest-first, so ``cd-1/01 Track01.flac`` ranks above
    the ambiguous bare ``01 Track01.flac``, and only files of exactly the right
    size are accepted. Equally specific candidates of the same size are *not*
    interchangeable — two LB folders can hold a same-length, different-bytes
    ``.md5`` for the same show — so all of them are returned and the caller
    settles the choice on the piece hashes.

    The torrent's own root segment is dropped before matching, since the
    collection never repeats the uploader's name for it.

    Args:
        index: Mapping from :func:`_index_sources`.
        rel_path: The torrent's path for this file, root segment included.
        size: The exact byte size the torrent expects.

    Returns:
        Matching local files, most specific (and within a depth, most preferred
        directory) first, without duplicates. Empty when nothing matches.
    """
    parts = Path(rel_path).parts
    if len(parts) > 1:
        parts = parts[1:]        # drop the torrent's root directory
    found: list[Path] = []
    seen: set[Path] = set()
    for depth in range(len(parts), 0, -1):
        for candidate in index.get("/".join(parts[-depth:]), []):
            if candidate in seen:
                continue
            try:
                if candidate.stat().st_size != size:
                    continue
            except OSError:
                continue
            seen.add(candidate)
            found.append(candidate)
    return found


def _resolve_source(
    index: dict[str, list[Path]], rel_path: str, size: int
) -> Path | None:
    """Return the single best indexed file for one torrent entry.

    Args:
        index: Mapping from :func:`_index_sources`.
        rel_path: The torrent's path for this file, root segment included.
        size: The exact byte size the torrent expects.

    Returns:
        The first of :func:`_resolve_candidates`, or None when nothing of that
        size matches.
    """
    candidates = _resolve_candidates(index, rel_path, size)
    return candidates[0] if candidates else None


def resolvable_files(info: TorrentInfo, dirs: list[str | Path]) -> int:
    """Count how many of a torrent's files the given folders can supply.

    Uses exactly the matching rule :func:`plan_overlay` will use — recursive,
    path-suffix keyed, exact size — so the number is a truthful preview of how
    much of the torrent those folders would satisfy, not a basename guess.

    Args:
        info: Parsed torrent metadata.
        dirs: Collection folders to score, most-preferred first.

    Returns:
        The number of torrent files with a local source in ``dirs``.
    """
    index = _index_sources([Path(d) for d in dirs])
    return sum(
        1 for rel_path, size in info.files
        if _resolve_source(index, rel_path, size) is not None
    )


def rank_source_folders(
    info: TorrentInfo, folders: list[str | Path]
) -> list[tuple[str, int]]:
    """Score candidate collection folders by how much of a torrent they supply.

    Args:
        info: Parsed torrent metadata.
        folders: Candidate collection folders.

    Returns:
        ``(folder, resolvable file count)`` pairs, highest count first, ties
        left in the order given.
    """
    scored = [(str(f), resolvable_files(info, [f])) for f in folders]
    return sorted(scored, key=lambda pair: -pair[1])


def choose_source_folder(
    info: TorrentInfo,
    folders: list[str | Path],
    named: list[str | Path] | None = None,
) -> str | None:
    """Pick the collection folder to assemble an overlay from, by content.

    A tracker's own attribution is not authoritative: two recordings repaired
    by hand on 2026-09-06 were filed against the wrong LB number outright, and
    the folder whose *name* equals the torrent root is no more trustworthy than
    the rest. Selection is therefore by resolvable-file count, using exactly
    the matching rule :func:`plan_overlay` will use; a name match only breaks a
    tie, where it is the better bet at no cost.

    Args:
        info: Parsed torrent metadata.
        folders: Candidate collection folders, all known to exist.
        named: The subset of ``folders`` whose directory name equals the
            torrent's root name, in preference order.

    Returns:
        The best-matching folder, or None when none supplies a single file.
    """
    ranked = rank_source_folders(info, folders)
    if not ranked or ranked[0][1] == 0:
        return None
    best = ranked[0][1]
    tied = [folder for folder, hits in ranked if hits == best]
    preferred = {str(f) for f in (named or [])}
    for folder in tied:
        if folder in preferred:
            return folder
    winner = tied[0]
    if preferred and winner not in preferred:
        logger.info(
            "overlay source: %s resolves %d files, more than the %r-named "
            "folder(s) the tracker points at — using it instead",
            winner, best, info.name,
        )
    return winner


def plan_overlay(
    info: TorrentInfo,
    source_folder: str | Path,
    overlay_root: str | Path,
    sidecar_dirs: list[str | Path] | None = None,
    site_urls: dict[str, str] | None = None,
    link_dirs: list[str | Path] | None = None,
    overlay_name: str = "",
) -> OverlayPlan:
    """Decide how each torrent file will be satisfied, without touching disk.

    Sources are tried in order: the collection folder (hardlink), any further
    collection folders in ``link_dirs`` (hardlink), the sidecar store (copy),
    the original URL on losslessbob.com (re-fetch), and finally the BitTorrent
    swarm.

    Within a source, a match is by path suffix and exact size — and where more
    than one local file matches that size, the choice is settled by hashing the
    pieces the file occupies, not by taking the first. Every candidate list is
    kept on the plan for :func:`repair_overlay`.

    Args:
        info: Parsed torrent metadata.
        source_folder: The collection folder holding the audio.
        overlay_root: Directory the overlay folder is created inside. Should be
            on the same filesystem as ``source_folder`` so hardlinks work.
        sidecar_dirs: Extra read-only directories to source missing files from,
            typically ``data/site/files``. Files found here are **copied**.
        site_urls: {filename: url} from :func:`db.get_site_file_urls`, used
            when the stored sidecar is the wrong size (link-rewritten HTML).
        link_dirs: Further collection folders, most-preferred first, whose
            files are **hardlinked** like ``source_folder``'s. A tracker's
            torrent can span more than one LB entry — a two-CD boot posted as
            one ``.torrent`` covering LB-14777 and LB-14778, say — and each
            entry is filed in its own collection folder. Passing the others
            here assembles the whole torrent at no extra disk cost. Must be on
            the same filesystem as ``overlay_root`` for the link to succeed.
        overlay_name: Folder name to create inside ``overlay_root``. Defaults
            to the torrent's own root name, which is not unique across a
            tracker — roots like ``track`` or ``FLAC`` recur, and two LB
            entries then assemble into one directory, the second build
            relinking over the first. Callers that can tell the entries apart
            pass a disambiguated name; see :func:`unique_overlay_name`.

    Returns:
        An OverlayPlan. Building it is a separate call.
    """
    source_folder = Path(source_folder)
    target_dir = Path(overlay_root) / (overlay_name or info.name)
    plan = OverlayPlan(target_dir=target_dir)

    sidecars = _index_sources([Path(d) for d in (sidecar_dirs or [])])
    # The primary folder and any siblings are all curated collection folders,
    # so all of them are hardlink sources, the primary taking precedence.
    collection = _index_sources(
        [source_folder] + [Path(d) for d in (link_dirs or [])]
    )
    ranges = info.file_piece_ranges()
    #: Built on first use — indexing the sidecar store is not free, and most
    #: torrents resolve every file by name without ever needing it.
    aliases: list[tuple[set[str], Path]] | None = None

    # Pass 1 — resolve a local source for each file, by exact size match.
    resolved: list[tuple[PlanEntry, Path | None]] = []
    #: {file index: local path} and {file index: every same-size candidate},
    #: the inputs piece-hash disambiguation and repair both work from.
    sources: dict[int, Path] = {}
    choices: dict[int, list[Path]] = {}
    by_index: dict[int, PlanEntry] = {}
    for idx, ((rel_path, size), _rng) in enumerate(
        zip(info.files, ranges, strict=True)
    ):
        name = Path(rel_path).name
        entry = PlanEntry(rel_path=rel_path, action=FETCH, size=size)
        by_index[idx] = entry

        collection_hits = _resolve_candidates(collection, rel_path, size)
        if collection_hits:
            in_collection = collection_hits[0]
            entry.action = LINK
            entry.source = str(in_collection)
            entry.reason = (
                "collection" if in_collection.is_relative_to(source_folder)
                else f"collection ({in_collection.parent.name})"
            )
            sources[idx] = in_collection
            if len(collection_hits) > 1:
                choices[idx] = collection_hits
            resolved.append((entry, in_collection))
            plan.entries.append(entry)
            continue

        sidecar_hits = _resolve_candidates(sidecars, rel_path, size)
        candidate = sidecar_hits[0] if sidecar_hits else None
        local_size: int | None = None
        if candidate is None:
            # Fall back to any same-named sidecar so a size mismatch can be
            # reported (and re-fetched) rather than silently left to the swarm.
            same_named = sidecars.get(name) or []
            candidate = same_named[0] if same_named else None
        if candidate is not None:
            try:
                local_size = candidate.stat().st_size
            except OSError:
                local_size = None
        if local_size == size:
            entry.action = COPY
            entry.source = str(candidate)
            entry.reason = "sidecar store"
            sources[idx] = candidate
            if len(sidecar_hits) > 1:
                choices[idx] = sidecar_hits
            resolved.append((entry, candidate))
            plan.entries.append(entry)
            continue

        # The crawl rewrote links inside saved HTML, so its copy is the wrong
        # size; the site still serves the original the torrent was built from.
        url = (site_urls or {}).get(name)
        if url:
            entry.action = REFETCH
            entry.source = url
            entry.reason = (
                f"sidecar store has it at {local_size} B, torrent wants {size} B"
                if local_size is not None else "re-fetch original from the site"
            )
            resolved.append((entry, None))
            plan.entries.append(entry)
            continue

        # Last resort before the swarm: the same bytes under the name the LB
        # site gave them. Worth trying on any post, and the only thing that
        # completes an old one whose swarm has nobody left in it.
        if aliases is None:
            aliases = _index_aliases(collection, sidecars)
        alias_hits = _alias_candidates(aliases, rel_path, size)
        if alias_hits:
            renamed = alias_hits[0]
            entry.action = COPY
            entry.source = str(renamed)
            entry.reason = f"renamed copy ({renamed.name})"
            sources[idx] = renamed
            if len(alias_hits) > 1:
                choices[idx] = alias_hits
            resolved.append((entry, renamed))
            plan.entries.append(entry)
            continue

        if local_size is not None:
            entry.reason = (
                f"sidecar store has it at {local_size} B, torrent wants {size} B"
            )
        elif (source_folder / name).exists():
            entry.reason = "present locally but the wrong size"
        else:
            entry.reason = "no local source"

        resolved.append((entry, None))
        plan.entries.append(entry)

    # Pass 1b — a size match is not a content match. Where more than one local
    # file has the exact size the torrent wants, hash the pieces it sits in and
    # keep the candidate that actually belongs there.
    plan.candidates = choices
    if choices:
        _disambiguate(info, ranges, sources, choices, by_index)

    # Pass 2 — pieces still unsatisfied are the only ones a client can write.
    unresolved_pieces: set[int] = set()
    for (entry, _src), (first, last) in zip(resolved, ranges, strict=True):
        if entry.action == FETCH:
            unresolved_pieces.update(range(first, last + 1))

    # Pass 3 — demote any hardlink that shares a piece with unresolved data.
    for (entry, _src), (first, last) in zip(resolved, ranges, strict=True):
        if entry.action != LINK:
            continue
        if any(p in unresolved_pieces for p in range(first, last + 1)):
            entry.action = COPY
            entry.reason = "collection (copied — shares a piece with missing data)"

    if not unresolved_pieces:
        plan.note = "every piece is locally satisfiable — no download needed"
    return plan


def http_fetch(url: str, dest: Path, timeout: int = 60) -> int:
    """Download a URL to a path, returning the byte count written.

    Args:
        url: Source URL.
        dest: Destination path; its parent must exist.
        timeout: Per-request timeout in seconds.

    Returns:
        Bytes written.

    Raises:
        OSError: On any transport or write failure.
    """
    import requests

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OSError(f"fetch failed: {exc}") from exc
    dest.write_bytes(resp.content)
    return len(resp.content)


def _overlay_dest(target_dir: Path, rel_path: str) -> Path:
    """Map a torrent-relative path to its place inside the overlay.

    The torrent's own root segment is stripped, because the overlay directory
    *is* that root.

    Args:
        target_dir: The overlay directory.
        rel_path: The torrent's path for one file, root segment included.

    Returns:
        The absolute destination path.
    """
    return target_dir / Path(rel_path).relative_to(Path(rel_path).parts[0])


def build_overlay(plan: OverlayPlan, dry_run: bool = False, fetcher=None) -> dict:
    """Create the overlay directory described by a plan.

    Hardlinks fall back to a copy when the target is on another filesystem.
    Files marked REFETCH are downloaded with ``fetcher``; if none is given they
    are left for the BitTorrent client instead.

    Args:
        plan: The plan from :func:`plan_overlay`.
        dry_run: Report what would happen without creating anything.
        fetcher: Callable ``(url, dest) -> int`` used for REFETCH entries.
            Defaults to :func:`http_fetch` being skipped entirely when None.

    Returns:
        Dict with ``ok``, ``linked``, ``copied``, ``refetched``, ``skipped``,
        ``errors`` (list of strings) and ``target_dir``.
    """
    result = {
        "ok": True, "linked": 0, "copied": 0, "refetched": 0, "skipped": 0,
        "errors": [], "target_dir": str(plan.target_dir),
    }
    if dry_run:
        result["linked"] = plan.count(LINK)
        result["copied"] = plan.count(COPY)
        result["refetched"] = plan.count(REFETCH) if fetcher else 0
        result["skipped"] = plan.count(FETCH) + (0 if fetcher else plan.count(REFETCH))
        return result

    for entry in plan.entries:
        if entry.action == FETCH or (entry.action == REFETCH and fetcher is None):
            result["skipped"] += 1
            continue

        dest = _overlay_dest(plan.target_dir, entry.rel_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()

            if entry.action == REFETCH:
                written = fetcher(entry.source, dest)
                if written != entry.size:
                    dest.unlink(missing_ok=True)
                    result["skipped"] += 1
                    result["errors"].append(
                        f"{entry.rel_path}: re-fetch gave {written} B, "
                        f"torrent wants {entry.size} B"
                    )
                    continue
                result["refetched"] += 1
                continue

            if entry.action == LINK:
                try:
                    os.link(entry.source, dest)
                    result["linked"] += 1
                    continue
                except OSError as exc:
                    logger.info(
                        "hardlink failed for %s (%s) — copying instead",
                        entry.rel_path, exc,
                    )
            shutil.copy2(entry.source, dest)
            result["copied"] += 1
        except OSError as exc:
            result["ok"] = False
            result["errors"].append(f"{entry.rel_path}: {exc}")

    return result


def verify_overlay(info: TorrentInfo, plan: OverlayPlan) -> VerifyResult:
    """Hash the built overlay against the torrent.

    Args:
        info: Parsed torrent metadata.
        plan: The plan whose ``target_dir`` was built.

    Returns:
        A VerifyResult for the overlay directory.
    """
    return verify_folder(info, plan.target_dir)


def _overlay_sources(info: TorrentInfo, target_dir: Path) -> dict[int, Path]:
    """Map each torrent file index to its built copy inside the overlay.

    Args:
        info: Parsed torrent metadata.
        target_dir: The overlay directory.

    Returns:
        ``{file index: path}`` for the files that exist and are the right size;
        anything absent or short is left out, so the pieces covering it read as
        *unknown* rather than as a wrong pick.
    """
    present: dict[int, Path] = {}
    for idx, (rel_path, size) in enumerate(info.files):
        dest = _overlay_dest(target_dir, rel_path)
        try:
            if dest.stat().st_size == size:
                present[idx] = dest
        except OSError:
            continue
    return present


def bad_pieces(info: TorrentInfo, target_dir: Path) -> list[int]:
    """List the pieces a built overlay has in full but hashes wrong.

    Pieces that merely lack data — a file left to the swarm — are *not*
    included: they are a shortfall, not a mistake. What is left is the set of
    pieces where every byte is present locally and still does not match, which
    means one of the files in them is the wrong file.

    Args:
        info: Parsed torrent metadata.
        target_dir: The overlay directory to inspect.

    Returns:
        Ascending piece indices.
    """
    offsets = _file_offsets(info)
    sources = _overlay_sources(info, target_dir)
    out: list[int] = []
    for piece in range(info.piece_count):
        data = _read_piece(info, offsets, sources, piece)
        if data is None:
            continue
        if hashlib.sha1(data).digest() != info.piece_hash(piece):
            out.append(piece)
    return out


def repair_overlay(info: TorrentInfo, plan: OverlayPlan) -> dict:
    """Re-resolve only the files inside a built overlay's failing pieces.

    An overlay that hashes short is normally handed to the swarm for the
    remainder — but a TUIT torrent's swarm is frequently dead, so a single
    wrongly-picked 1 KB sidecar leaves a 17 MB flac permanently incomplete.
    Where a failing piece is locally complete, the fault is a pick and not a
    shortfall, so every same-size candidate for the files in that piece is
    tried against the piece's own hash before giving up. Only the files that
    change are re-materialised; the rest of the overlay is untouched, and
    nothing here writes to the collection.

    Args:
        info: Parsed torrent metadata.
        plan: The already-built plan whose ``target_dir`` verified short.

    Returns:
        Dict with ``ok`` (the overlay now verifies complete), ``repaired``
        (torrent-relative paths whose source was swapped), ``bad_pieces`` (how
        many locally-complete pieces hashed wrong before the attempt),
        ``errors`` and ``verify`` (a :class:`VerifyResult`, or None when no
        repair was attempted).
    """
    out: dict = {
        "ok": False, "repaired": [], "bad_pieces": 0, "errors": [],
        "verify": None,
    }
    failing = bad_pieces(info, plan.target_dir)
    out["bad_pieces"] = len(failing)
    if not failing:
        return out

    ranges = info.file_piece_ranges()
    offsets = _file_offsets(info)
    sources = _overlay_sources(info, plan.target_dir)
    by_index = {i: e for i, e in enumerate(plan.entries)}
    failing_set = set(failing)

    # Only a file with an alternative local source can be re-picked, and only a
    # locally-sourced one may be replaced at all — a REFETCH or FETCH entry has
    # nothing to choose between.
    suspects = [
        idx for idx in sorted(plan.candidates)
        if by_index.get(idx) is not None
        and by_index[idx].action in (LINK, COPY)
        and any(p in failing_set for p in range(*_span(ranges[idx])))
    ]
    if not suspects:
        logger.info(
            "overlay repair: %d piece(s) hash wrong but no file in them has an "
            "alternative local source", len(failing),
        )
        return out

    for idx in sorted(suspects, key=lambda i: ranges[i][1] - ranges[i][0]):
        entry = by_index[idx]
        pieces = [p for p in range(*_span(ranges[idx])) if p in failing_set]
        chosen = _pick_by_piece_hash(
            info, offsets, ranges, sources, idx, plan.candidates[idx], pieces
        )
        if chosen is None or str(chosen) == entry.source:
            continue
        dest = _overlay_dest(plan.target_dir, entry.rel_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            if entry.action == LINK:
                try:
                    os.link(chosen, dest)
                except OSError:
                    shutil.copy2(chosen, dest)
            else:
                shutil.copy2(chosen, dest)
        except OSError as exc:
            out["errors"].append(f"{entry.rel_path}: {exc}")
            continue
        logger.info(
            "overlay repair: %s re-resolved to %s", entry.rel_path, chosen
        )
        entry.source = str(chosen)
        entry.note = "re-resolved from a failing piece"
        sources[idx] = dest
        out["repaired"].append(entry.rel_path)

    if not out["repaired"]:
        return out
    result = verify_folder(info, plan.target_dir)
    out["verify"] = result
    out["ok"] = result.complete
    return out


def _span(rng: tuple[int, int]) -> tuple[int, int]:
    """Turn an inclusive piece range into a half-open one for ``range()``.

    Args:
        rng: ``(first, last)`` inclusive, from
            :meth:`TorrentInfo.file_piece_ranges`.

    Returns:
        ``(first, last + 1)``.
    """
    return rng[0], rng[1] + 1


def collection_is_untouched(
    source_folder: str | Path, before: dict[str, tuple[int, int]]
) -> list[str]:
    """Compare a folder against a snapshot, returning names that changed.

    A cheap post-condition check for the promise that the collection is never
    written to.

    Args:
        source_folder: Folder to re-inspect.
        before: Snapshot from :func:`snapshot_folder`.

    Returns:
        Names that were added, removed, resized or re-dated. Empty when clean.
    """
    after = snapshot_folder(source_folder)
    changed = [n for n in before if n not in after or after[n] != before[n]]
    changed += [n for n in after if n not in before]
    return sorted(set(changed))


@dataclass
class OverlayStatus:
    """How an existing overlay relates to the collection right now."""

    path: Path
    exists: bool = False
    n_files: int = 0
    shared_bytes: int = 0   # files whose inode has another name (the collection)
    pinned_bytes: int = 0   # files the overlay is the sole holder of

    @property
    def orphaned(self) -> bool:
        """True when the overlay holds audio nothing else references.

        After a same-volume rename the overlay is untouched and still shares
        every inode. After a delete or a cross-volume move (copy + rmtree) the
        link count drops to 1 and the overlay silently keeps those bytes alive,
        so the space is never reclaimed.
        """
        return self.exists and self.pinned_bytes > self.shared_bytes

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        if not self.exists:
            return "overlay directory is gone"
        return (
            f"{self.n_files} files, {self.shared_bytes / 1e6:.1f} MB shared with "
            f"the collection, {self.pinned_bytes / 1e6:.1f} MB held only here"
        )


def overlay_status(overlay_dir: str | Path) -> OverlayStatus:
    """Report whether an overlay still shares its bytes with the collection.

    Uses link counts rather than paths, so it stays correct after the
    collection folder is renamed or moved within its volume.

    Args:
        overlay_dir: The overlay folder to inspect.

    Returns:
        An OverlayStatus.
    """
    path = Path(overlay_dir)
    status = OverlayStatus(path=path)
    try:
        entries = [p for p in path.iterdir() if p.is_file()]
    except OSError:
        return status

    status.exists = True
    for item in entries:
        stat = item.stat()
        status.n_files += 1
        if stat.st_nlink > 1:
            status.shared_bytes += stat.st_size
        else:
            status.pinned_bytes += stat.st_size
    return status


def find_overlays_for_lb(lb_number: int, db_path=None) -> list[Path]:
    """Return recorded overlay/seed folders for an LB number.

    Reads ``tuit_downloads.seed_folder``, so it only knows about seeds this
    tool created.

    Args:
        lb_number: LB number to look up.
        db_path: Optional DB path override.

    Returns:
        Distinct seed folder paths, newest attempt first.
    """
    from backend import db  # imported here to keep module import cheap

    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT seed_folder FROM tuit_downloads "
            " WHERE lb_number=? AND seed_folder IS NOT NULL AND seed_folder <> ''"
            " ORDER BY attempted_at DESC",
            (lb_number,),
        ).fetchall()
    return [Path(r[0]) for r in rows]


def lbs_for_seed_folder(folder: str | Path, db_path=None) -> set[int]:
    """Return the LB numbers already recorded as seeding from ``folder``.

    Reads both tracker tables, so an overlay claimed by a WTRF seed is visible
    to a TUIT run and vice versa.

    Args:
        folder: Seed folder path to look up.
        db_path: Optional DB path override.

    Returns:
        The distinct LB numbers recorded against that folder; empty when the
        folder predates this bookkeeping or was created by hand.
    """
    from backend import db  # imported here to keep module import cheap

    found: set[int] = set()
    with db.get_connection(db_path) as conn:
        for table in ("tuit_downloads", "wtrf_downloads"):
            try:
                rows = conn.execute(
                    f"SELECT DISTINCT lb_number FROM {table} "  # noqa: S608 — fixed literals
                    " WHERE seed_folder=? AND lb_number IS NOT NULL",
                    (str(folder),),
                ).fetchall()
            except sqlite3.Error:      # table absent on an older DB
                continue
            found.update(r[0] for r in rows)
    return found


def unique_overlay_name(
    overlay_root: str | Path, torrent_name: str, lb_number: int | None,
    db_path=None,
) -> str:
    """Pick an overlay folder name that no other LB entry already owns.

    Torrent root names are not unique on a tracker — ``track``, ``FLAC`` and
    ``1`` all recur — so ``overlay_root/<root name>`` silently collides and the
    second build relinks over the first, leaving one of the two torrents
    seeding files that belong to the other show. The name is kept as-is when
    the directory is free or already this LB's, so existing overlays are never
    renamed out from under qBittorrent; only a genuine collision is suffixed.

    Args:
        overlay_root: Directory overlays are created inside.
        torrent_name: The torrent's own root folder name.
        lb_number: LB entry the overlay is being built for.
        db_path: Optional DB path override.

    Returns:
        ``torrent_name``, or ``"<torrent_name> (LB-NNNNN)"`` on a collision.
    """
    candidate = Path(overlay_root) / torrent_name
    if lb_number is None or not candidate.exists():
        return torrent_name
    try:
        owners = lbs_for_seed_folder(candidate, db_path)
    except Exception as exc:   # bookkeeping must never block a seed
        logger.debug("unique_overlay_name: lookup failed for %s: %s", candidate, exc)
        return torrent_name
    if not owners or lb_number in owners:
        return torrent_name
    unique = f"{torrent_name} (LB-{lb_number:05d})"
    logger.info(
        "overlay name %r is already LB-%s's — using %r instead",
        torrent_name, ", LB-".join(f"{n:05d}" for n in sorted(owners)), unique,
    )
    return unique


def warn_if_seeded(lb_number: int, action: str, db_path=None) -> list[str]:
    """Log a warning when an LB about to be moved or deleted has live seeds.

    A same-volume rename is harmless — hardlinks follow the inode. A delete or
    cross-volume move is not: the overlay keeps the old bytes alive, so the
    space is never reclaimed and the seed silently stops shadowing the
    collection copy.

    Args:
        lb_number: LB number being operated on.
        action: Short description used in the log line.
        db_path: Optional DB path override.

    Returns:
        The overlay paths that were warned about (empty when there are none).
    """
    try:
        overlays = find_overlays_for_lb(lb_number, db_path)
    except Exception as exc:  # never let bookkeeping block a file operation
        logger.debug("warn_if_seeded: lookup failed for LB-%s: %s", lb_number, exc)
        return []

    warned: list[str] = []
    for overlay in overlays:
        status = overlay_status(overlay)
        if not status.exists:
            continue
        warned.append(str(overlay))
        logger.warning(
            "LB-%05d is being %s but is seeded from %s (%s). After a delete or "
            "cross-volume move that overlay holds the only copy of those bytes, "
            "so the space is not reclaimed — run "
            "'tools/tuit_sync.py --check-overlays' afterwards.",
            lb_number, action, overlay, status.summary(),
        )
    return warned


def snapshot_folder(folder: str | Path) -> dict[str, tuple[int, int]]:
    """Return {relative path: (size, mtime_ns)} for every file under a folder.

    Walks the whole tree, not just the top level: a collection folder holding
    ``cd-1/``/``cd-2/`` subdirectories would otherwise let a write below the
    root pass the :func:`collection_is_untouched` guard unnoticed.

    Args:
        folder: Directory to snapshot.

    Returns:
        A mapping usable with :func:`collection_is_untouched`.
    """
    root = Path(folder)
    out: dict[str, tuple[int, int]] = {}
    try:
        paths = list(root.rglob("*"))
    except OSError:
        return out
    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
            out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
        except (OSError, ValueError):
            continue
    return out
