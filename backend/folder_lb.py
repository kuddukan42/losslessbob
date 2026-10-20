"""Folder → LB helpers shared by the LBDir routes and app.py (TODO-369).

Locate a folder's lbdir manifest and resolve which LB / fileset xref a folder belongs to.
"""

import re
from pathlib import Path

from backend import db as database

_LBF_NAME_RE = re.compile(r'^LBF-(\d+)-', re.IGNORECASE)


def _lbdir_file_lb(path: Path) -> "int | None":
    """LB# a manifest filename declares (``LBF-01234-lbdir.txt`` → 1234), or None."""
    m = _LBF_NAME_RE.match(path.name)
    return int(m.group(1)) if m else None


def _find_lbdir_in_folder(
    folder: Path, lb_number: "int | None" = None, strict: bool = False,
) -> "Path | None":
    """Return the folder's lbdir*.txt manifest, or None.

    With *lb_number* the search is ordered by how well a manifest is attributed
    to that LB: an ``LBF-NNNNN-…`` file whose number matches (or matches the
    LB's canonical, which an alias legitimately carries), then an untagged
    ``lbdir*.txt`` (folder-supplied, unattributable — assumed to be the
    folder's own), then any other LB's manifest.

    *strict* stops before that last step: it answers "does this folder already
    hold **this LB's** manifest?", which is what the retrieve paths must ask so
    an LB override re-fetches instead of leaving the previously-matched LB's
    manifest authoritative (BUG-315). The non-strict fallback keeps a folder
    whose pinned LB has no lbdir attachment of its own (common for double-LB
    pairs, where only one entry carries the manifest) verifying against the
    manifest that *is* there rather than against nothing.

    Args:
        folder: Folder to search (non-recursive).
        lb_number: LB to prefer the manifest of, or None to accept any.
        strict: Reject manifests belonging to a different LB instead of
            falling back to them.

    Returns:
        Path of the chosen manifest, or None when the folder has none that
        qualifies.
    """
    if not folder.exists():
        return None
    candidates = [
        f for f in sorted(folder.iterdir())
        if f.is_file() and 'lbdir' in f.name.lower() and f.suffix.lower() == '.txt'
    ]
    if lb_number is None:
        return candidates[0] if candidates else None
    untagged: Path | None = None
    tagged: list[tuple[int, Path]] = []
    for f in candidates:
        file_lb = _lbdir_file_lb(f)
        if file_lb == lb_number:
            return f
        if file_lb is None:
            if untagged is None:
                untagged = f
        else:
            tagged.append((file_lb, f))
    if untagged is not None:
        return untagged
    if not tagged:
        return None
    # An alias LB legitimately carries its canonical's manifest (the retrieve
    # paths fall back to the canonical when the alias has no attachment).
    try:
        canonicals = database.resolve_aliases([lb_number])
        canonical = canonicals[0] if canonicals else lb_number
    except Exception:
        canonical = lb_number
    for file_lb, f in tagged:
        if file_lb == canonical:
            return f
    return None if strict else tagged[0][1]


def _pinned_lb_for_folder(folder: Path) -> int | None:
    """LB# of a *single* explicit folder→LB pin, or None.

    A pin (folder_lb_link, written by "Pin & continue" / the pipeline "Override
    LB#" control) is the user's explicit override and must win over the
    my_collection/name-regex heuristics: otherwise a folder whose stale
    my_collection row or ambiguous "(LB-A+LB-B)" name disagrees with the pin
    keeps resolving to the wrong LB even after the user overrides it (BUG-257).
    Multiple links (a legacy multi-LB auto-link) are ambiguous, so this returns
    None and the caller's existing order applies until the user re-pins one.
    """
    links = database.get_folder_links(str(folder))
    return links[0]["lb_number"] if len(links) == 1 else None


def _resolve_xref_for_folder(folder: Path, lb_number: "int | None") -> int:
    """Copy-level fileset id (my_collection.xref) a folder's lbdir lookup should use.

    0 = canonical fileset, N>0 = alternate fileset xref-N (docs/XREF_SEMANTICS.md
    §3). Prefers the my_collection row (authoritative, set by the pipeline's
    lookup match) over the folder name's own ``-xrefNNNNN`` tag, which is only
    present once the folder has actually been renamed. Getting this wrong hands
    find_lbdir_attachment() the wrong manifest for the folder's real fileset
    (BUG-310).
    """
    if lb_number is not None:
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT xref FROM my_collection WHERE disk_path=?", (str(folder),)
            ).fetchone()
        if row is not None:
            return row["xref"] or 0
    from backend.folder_naming import parse_xref_tag
    return parse_xref_tag(folder.name)


def _resolve_lb_number_for_folder(folder: Path) -> int | None:
    """Best-effort LB# for a folder: single pin, then my_collection row, then name regex.

    Used by the LBDIR reconcile/extras endpoints to know which lb_number's
    qBittorrent tracking (if any) needs a file-path sync after files move
    within folder.
    """
    pinned = _pinned_lb_for_folder(folder)
    if pinned is not None:
        return pinned
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT lb_number FROM my_collection WHERE disk_path=?", (str(folder),)
        ).fetchone()
    if row:
        return row["lb_number"]
    m = re.search(r'LB-(\d+)', folder.name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    link = database.get_folder_link(str(folder))
    return link["lb_number"] if link else None
