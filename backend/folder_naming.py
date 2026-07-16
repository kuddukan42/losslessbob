"""Shared folder-name helpers for LosslessBob.

Provides :func:`apply_nft_suffix`, :func:`nft_discrepancy`, and
:func:`build_standard_name` so that every part of the GUI that builds or
validates proposed folder names applies consistent formatting and the -NFT
marker correctly.

Xref-aware naming (FABLE_XREF_INCORPORATION.md D2 / docs/XREF_SEMANTICS.md §3):
an xref id names the alternate circulating fileset a folder matches, distinct
from the LB number itself. :func:`lb_tag` and :func:`parse_xref_tag` are the
shared build/parse primitives; :func:`strip_lb_tag` removes a trailing LB tag
block (single- or multi-LB, with or without an xref suffix) so callers can
rebuild it without producing duplicate or stale tags.
"""

import re

_NFT_SUFFIX = "-NFT"

# Wild xref variants already on disk (docs/XREF_SEMANTICS.md §3): hyphenated
# ("xref-01995"), capitalised ("Xref-1292"), or bare ("xref2141"). This module
# always *writes* the 5-digit "xrefYYYYY" form (D2) but must *parse* all of them.
_XREF_TAG_RE = re.compile(r'[Xx]ref[- ]?0*(\d+)')

# Trailing parenthesized LB tag block: one or more "LB-NNNNN[-xrefMMMMM]"
# segments joined by "+", e.g. "(LB-00002)", "(LB-00002-xref00961)",
# "(LB-00002+LB-00003-xref01292)". Used to strip a stale tag before rebuilding.
_LB_TAG_BLOCK_RE = re.compile(
    r'\s*\(\s*LB-\d+(?:[-\s]?[Xx]ref[- ]?0*\d+)?'
    r'(?:\s*\+\s*LB-\d+(?:[-\s]?[Xx]ref[- ]?0*\d+)?)*\s*\)\s*$',
    re.IGNORECASE,
)


def lb_tag(lb_number: int, xref: int = 0) -> str:
    """Build a single LB tag component.

    Args:
        lb_number: LosslessBob entry number.
        xref: Xref fileset id (0 = canonical fileset, no suffix).

    Returns:
        ``LB-XXXXX`` when xref is 0, else ``LB-XXXXX-xrefYYYYY`` (both
        zero-padded to 5 digits per docs/XREF_SEMANTICS.md §3 / D2 — this
        supersedes the legacy 4-digit ``LB-{n}-xref{v:04d}`` format).
    """
    base = f"LB-{lb_number:05d}"
    return f"{base}-xref{xref:05d}" if xref else base


def parse_xref_tag(name: str) -> int:
    """Extract an xref fileset id from a folder name or tag fragment.

    Matches the wild variants already on disk (``xref-01995``, ``Xref-1292``,
    ``xref2141``) in addition to this module's own ``xrefYYYYY`` output, per
    docs/XREF_SEMANTICS.md §3 / FABLE_XREF_INCORPORATION.md D2.

    Args:
        name: Folder name or fragment to search.

    Returns:
        The parsed xref id, or 0 if no xref tag is present.
    """
    m = _XREF_TAG_RE.search(name)
    return int(m.group(1)) if m else 0


def strip_lb_tag(name: str) -> str:
    """Remove a trailing parenthesized LB tag block from a folder name.

    Matches single- or multi-LB tags, with or without an xref suffix, and
    the wild xref variants already on disk (see :data:`_LB_TAG_BLOCK_RE`).

    Args:
        name: Folder name, ideally with any -NFT suffix already stripped via
            :func:`strip_nft_suffix`.

    Returns:
        Name with the trailing tag block removed and trailing whitespace
        trimmed; unchanged if no tag block is found at the end.
    """
    return _LB_TAG_BLOCK_RE.sub("", name).rstrip()


def apply_nft_suffix(name: str, lb_status: str | None) -> str:
    """Append -NFT if lb_status is 'private'. Idempotent and case-normalising.

    Args:
        name: Proposed folder name.
        lb_status: 'public', 'private', 'missing', or None.

    Returns:
        Name with -NFT appended when lb_status is 'private', unchanged
        otherwise.  If the name already ends in -nft (any case), normalises
        the suffix to uppercase -NFT without double-appending.
    """
    if lb_status != "private":
        return name
    if name.upper().endswith(_NFT_SUFFIX):
        # Normalise case (e.g. -nft → -NFT) without double-appending
        return name[: -len(_NFT_SUFFIX)] + _NFT_SUFFIX
    return name + _NFT_SUFFIX


def strip_nft_suffix(name: str) -> str:
    """Remove a trailing -NFT suffix (case-insensitive).

    Args:
        name: Folder name that may end with -NFT.

    Returns:
        Name with the terminal -NFT removed, unchanged if absent.
    """
    if name.upper().endswith(_NFT_SUFFIX):
        return name[: -len(_NFT_SUFFIX)]
    return name


def has_nft_suffix(name: str) -> bool:
    """Return True if *name* ends with -NFT (case-insensitive)."""
    return name.upper().endswith(_NFT_SUFFIX)


def build_standard_name(
    lb_number: int,
    date_str: str,
    location: str,
    lb_status: str | None,
    xref: int = 0,
) -> str:
    """Build the canonical ``YYYY-MM-DD Location (LB-XXXXX)[-NFT]`` folder name.

    Args:
        lb_number: LosslessBob entry number.
        date_str: Date string in M/D/YY format from the database.
        location: Event location string.
        lb_status: 'public', 'private', 'missing', or None.
        xref: Xref fileset id (0 = canonical fileset). When > 0 the LB tag
            becomes ``LB-XXXXX-xrefYYYYY`` (D2) — see :func:`lb_tag`.

    Returns:
        Canonical folder name with optional -NFT suffix applied via
        :func:`apply_nft_suffix`.  Falls back to bare ``LB-XXXXX[-NFT]``
        (or its xref-suffixed form) when date or location is missing.
    """
    from backend.torrent_maker import _parse_date

    iso_date = _parse_date(date_str) if date_str else ""
    loc = location.strip() if location else ""
    tag = lb_tag(lb_number, xref)
    if iso_date and loc:
        base = f"{iso_date} {loc} ({tag})"
    else:
        base = tag
    return apply_nft_suffix(base, lb_status)


def build_multi_lb_name(
    lb_numbers: list[int],
    date_str: str,
    location: str,
    lb_status: str | None,
    xrefs: list[int] | None = None,
) -> str:
    """Build canonical name for a folder matched to multiple LB entries.

    Args:
        lb_numbers: Sorted list of LB numbers (must have ≥ 2).
        date_str: Date string in M/D/YY format from the database.
        location: Event location string.
        lb_status: 'public', 'private', 'missing', or None.
        xrefs: Xref fileset id per entry, aligned index-for-index with
            ``lb_numbers`` (0 = canonical). Defaults to all-canonical when
            omitted. Must be the same length as ``lb_numbers`` if given.

    Returns:
        Canonical name like ``YYYY-MM-DD Location (LB-NNNNN+LB-MMMMM)[-NFT]``,
        with an ``-xrefYYYYY`` suffix on any entry whose xref is > 0 (D2).
        Falls back to ``(LB-NNNNN+LB-MMMMM)[-NFT]`` when date/location missing.

    Raises:
        ValueError: If ``xrefs`` is given and its length doesn't match
            ``lb_numbers``.
    """
    from backend.torrent_maker import _parse_date

    if xrefs is None:
        xrefs = [0] * len(lb_numbers)
    elif len(xrefs) != len(lb_numbers):
        raise ValueError("xrefs must be the same length as lb_numbers")

    iso_date = _parse_date(date_str) if date_str else ""
    loc = location.strip() if location else ""
    pairs = sorted(zip(lb_numbers, xrefs, strict=True), key=lambda p: p[0])
    tag = "+".join(lb_tag(lb, xr) for lb, xr in pairs)
    if iso_date and loc:
        base = f"{iso_date} {loc} ({tag})"
    else:
        base = f"({tag})"
    return apply_nft_suffix(base, lb_status)


def nft_discrepancy(folder_name: str, lb_status: str | None) -> str | None:
    """Classify the NFT-suffix vs lb_status alignment for a folder.

    Args:
        folder_name: Current (not proposed) folder name.
        lb_status: 'public', 'private', 'missing', or None.

    Returns:
        None       — no discrepancy
        'missing'  — LB is private but folder lacks -NFT
        'stale'    — LB is public but folder has -NFT
        'unknown'  — LB is missing/None but folder has -NFT
    """
    has_nft = has_nft_suffix(folder_name)
    if lb_status == "private" and not has_nft:
        return "missing"
    if lb_status == "public" and has_nft:
        return "stale"
    if lb_status in ("missing", None) and has_nft:
        return "unknown"
    return None
