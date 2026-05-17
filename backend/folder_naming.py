"""Shared folder-name helpers for LosslessBob.

Provides :func:`apply_nft_suffix`, :func:`nft_discrepancy`, and
:func:`build_standard_name` so that every part of the GUI that builds or
validates proposed folder names applies consistent formatting and the -NFT
marker correctly.
"""

_NFT_SUFFIX = "-NFT"


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
) -> str:
    """Build the canonical ``YYYY-MM-DD Location (LB-XXXXX)[-NFT]`` folder name.

    Args:
        lb_number: LosslessBob entry number.
        date_str: Date string in M/D/YY format from the database.
        location: Event location string.
        lb_status: 'public', 'private', 'missing', or None.

    Returns:
        Canonical folder name with optional -NFT suffix applied via
        :func:`apply_nft_suffix`.  Falls back to ``LB-XXXXX[-NFT]`` when
        date or location is missing.
    """
    from backend.torrent_maker import _parse_date

    iso_date = _parse_date(date_str) if date_str else ""
    loc = location.strip() if location else ""
    if iso_date and loc:
        base = f"{iso_date} {loc} (LB-{lb_number:05d})"
    else:
        base = f"LB-{lb_number:05d}"
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
