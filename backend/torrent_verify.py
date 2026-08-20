"""Read .torrent metadata and verify a local folder against it, read-only.

Used before a torrent is handed to a BitTorrent client for seeding. Adding an
incomplete torrent to qBittorrent makes it *download* the missing pieces into
the collection folder, modifying curated files; verifying here means a torrent
is only ever added when the folder already hashes to 100 %.

Nothing in this module opens a file for writing.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Read this many bytes per filesystem read while hashing.
_CHUNK = 1 << 20


class BencodeError(ValueError):
    """Raised when a .torrent file cannot be decoded."""


# ──────────────────────────────────────────────────────────────────────────────
# Minimal bencode reader
# ──────────────────────────────────────────────────────────────────────────────
def _decode(data: bytes, pos: int) -> tuple[object, int]:
    """Decode one bencoded value starting at ``pos``.

    Args:
        data: The full bencoded buffer.
        pos: Offset to start decoding at.

    Returns:
        (value, next_position).

    Raises:
        BencodeError: On malformed input.
    """
    if pos >= len(data):
        raise BencodeError("truncated input")
    char = data[pos:pos + 1]

    if char == b"i":
        end = data.find(b"e", pos)
        if end < 0:
            raise BencodeError("unterminated integer")
        try:
            return int(data[pos + 1:end]), end + 1
        except ValueError as exc:
            raise BencodeError(f"bad integer: {exc}") from exc

    if char == b"l":
        items: list = []
        pos += 1
        while data[pos:pos + 1] != b"e":
            value, pos = _decode(data, pos)
            items.append(value)
        return items, pos + 1

    if char == b"d":
        out: dict = {}
        pos += 1
        while data[pos:pos + 1] != b"e":
            key, pos = _decode(data, pos)
            value, pos = _decode(data, pos)
            if not isinstance(key, bytes):
                raise BencodeError("non-bytes dict key")
            out[key] = value
        return out, pos + 1

    if char.isdigit():
        colon = data.find(b":", pos)
        if colon < 0:
            raise BencodeError("unterminated string length")
        length = int(data[pos:colon])
        start = colon + 1
        if start + length > len(data):
            raise BencodeError("string runs past end of buffer")
        return data[start:start + length], start + length

    raise BencodeError(f"unexpected byte {char!r} at {pos}")


def bdecode(data: bytes) -> object:
    """Decode a complete bencoded buffer.

    Args:
        data: Bencoded bytes.

    Returns:
        The decoded value (normally a dict).

    Raises:
        BencodeError: On malformed input.
    """
    value, _pos = _decode(data, 0)
    return value


# ──────────────────────────────────────────────────────────────────────────────
# Torrent metadata
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class TorrentInfo:
    """The parts of a .torrent's info dict needed to verify local files."""

    name: str
    piece_length: int
    pieces: bytes                                   # concatenated 20-byte SHA1s
    files: list[tuple[str, int]] = field(default_factory=list)  # (rel_path, size)
    single_file: bool = False

    @property
    def total_size(self) -> int:
        """Total size in bytes of every file in the torrent."""
        return sum(size for _p, size in self.files)

    @property
    def piece_count(self) -> int:
        """Number of pieces the torrent declares."""
        return len(self.pieces) // 20

    def piece_hash(self, index: int) -> bytes:
        """Return the expected SHA1 for one piece index."""
        return self.pieces[index * 20:(index + 1) * 20]

    def file_piece_ranges(self) -> list[tuple[int, int]]:
        """Return the inclusive (first_piece, last_piece) each file spans.

        Torrent files are laid out as one contiguous byte stream, so a piece
        can straddle a file boundary. Callers use this to find which files
        share a piece with a file they do not have — those are the only files
        a client can write to while completing the torrent.

        Returns:
            One (first, last) tuple per entry in ``files``, same order. A
            zero-length file yields a range covering its single offset.
        """
        ranges: list[tuple[int, int]] = []
        offset = 0
        for _path, size in self.files:
            first = offset // self.piece_length
            last = max(first, (offset + max(size, 1) - 1) // self.piece_length)
            ranges.append((first, last))
            offset += size
        return ranges


def read_torrent(torrent_path: str | Path) -> TorrentInfo:
    """Parse a .torrent file.

    Args:
        torrent_path: Path to the .torrent.

    Returns:
        A TorrentInfo.

    Raises:
        BencodeError: If the file is not a readable torrent.
    """
    try:
        raw = Path(torrent_path).read_bytes()
    except OSError as exc:
        raise BencodeError(f"cannot read {torrent_path}: {exc}") from exc

    meta = bdecode(raw)
    if not isinstance(meta, dict) or b"info" not in meta:
        raise BencodeError("no info dict in torrent")
    info = meta[b"info"]
    if not isinstance(info, dict):
        raise BencodeError("info is not a dict")

    try:
        name = info[b"name"].decode("utf-8", "replace")
        piece_length = int(info[b"piece length"])
        pieces = info[b"pieces"]
    except (KeyError, AttributeError, TypeError) as exc:
        raise BencodeError(f"info dict missing required key: {exc}") from exc

    if not isinstance(pieces, bytes) or len(pieces) % 20:
        raise BencodeError("pieces is not a multiple of 20 bytes")

    files: list[tuple[str, int]] = []
    single = b"files" not in info
    if single:
        files.append((name, int(info[b"length"])))
    else:
        for entry in info[b"files"]:
            parts = [p.decode("utf-8", "replace") for p in entry[b"path"]]
            files.append((str(Path(name, *parts)), int(entry[b"length"])))

    return TorrentInfo(
        name=name,
        piece_length=piece_length,
        pieces=pieces,
        files=files,
        single_file=single,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class VerifyResult:
    """Outcome of hashing a local folder against a torrent."""

    complete: bool = False
    piece_count: int = 0
    good_pieces: int = 0
    total_bytes: int = 0
    present_bytes: int = 0
    missing_files: list[str] = field(default_factory=list)
    size_mismatches: list[str] = field(default_factory=list)
    extra_note: str = ""

    @property
    def percent(self) -> float:
        """Share of pieces that hashed correctly, 0.0–100.0."""
        if not self.piece_count:
            return 0.0
        return 100.0 * self.good_pieces / self.piece_count

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        if self.complete:
            return f"100% — all {self.piece_count} pieces verified"
        bits = [f"{self.percent:.2f}% ({self.good_pieces}/{self.piece_count} pieces)"]
        if self.missing_files:
            bits.append(f"{len(self.missing_files)} file(s) missing")
        if self.size_mismatches:
            bits.append(f"{len(self.size_mismatches)} wrong size")
        return ", ".join(bits)


def _piece_reader(info: TorrentInfo, root: Path):
    """Yield each piece's bytes in torrent order, zero-filling absent data.

    Files are read strictly read-only; a missing or short file contributes
    zero bytes, which makes the covering pieces fail their hash check.

    Args:
        info: Parsed torrent metadata.
        root: Directory that *contains* the torrent's root folder.

    Yields:
        bytes for each piece, in index order.
    """
    buf = bytearray()
    for rel_path, size in info.files:
        path = root / rel_path
        remaining = size
        try:
            with path.open("rb") as fh:
                while remaining > 0:
                    chunk = fh.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    buf.extend(chunk)
                    remaining -= len(chunk)
                    while len(buf) >= info.piece_length:
                        yield bytes(buf[:info.piece_length])
                        del buf[:info.piece_length]
        except OSError:
            pass  # missing/unreadable — fall through to the zero-fill below
        if remaining > 0:
            # Keep the stream aligned so later files still land on the right
            # piece boundaries; the zero-fill guarantees a hash mismatch.
            buf.extend(b"\0" * remaining)
            while len(buf) >= info.piece_length:
                yield bytes(buf[:info.piece_length])
                del buf[:info.piece_length]
    if buf:
        yield bytes(buf)


def verify_folder(
    info: TorrentInfo, folder: str | Path, stop_at_first_bad: bool = False
) -> VerifyResult:
    """Hash a local folder against a torrent's piece hashes.

    Args:
        info: Parsed torrent metadata.
        folder: The local folder corresponding to ``info.name``. Its *parent*
            is used as the torrent root, matching how a client resolves paths.
        stop_at_first_bad: Return as soon as one piece fails. Faster when the
            caller only needs a yes/no answer.

    Returns:
        A VerifyResult. ``complete`` is True only when every piece matched and
        no file was missing or the wrong size.
    """
    folder = Path(folder)
    root = folder.parent
    result = VerifyResult(piece_count=info.piece_count, total_bytes=info.total_size)

    if folder.name != info.name:
        result.extra_note = (
            f"folder name {folder.name!r} != torrent root {info.name!r}"
        )
        return result

    for rel_path, size in info.files:
        path = root / rel_path
        try:
            actual = path.stat().st_size
        except OSError:
            result.missing_files.append(rel_path)
            continue
        if actual != size:
            result.size_mismatches.append(f"{rel_path} ({actual} != {size})")
        result.present_bytes += min(actual, size)

    for index, piece in enumerate(_piece_reader(info, root)):
        if index >= info.piece_count:
            break
        if hashlib.sha1(piece).digest() == info.piece_hash(index):
            result.good_pieces += 1
        elif stop_at_first_bad:
            return result

    result.complete = (
        result.good_pieces == info.piece_count
        and not result.missing_files
        and not result.size_mismatches
    )
    return result


def verify_torrent_against_folder(
    torrent_path: str | Path, folder: str | Path
) -> VerifyResult:
    """Convenience wrapper: read a .torrent and verify a folder against it.

    Args:
        torrent_path: Path to the .torrent file.
        folder: Local folder to check.

    Returns:
        A VerifyResult; on an unreadable torrent, one with ``extra_note`` set
        and ``complete`` False.
    """
    try:
        info = read_torrent(torrent_path)
    except BencodeError as exc:
        return VerifyResult(extra_note=str(exc))
    return verify_folder(info, folder)
