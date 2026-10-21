"""lb_alias + folder_lb_link helpers (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── lb_alias helpers ──────────────────────────────────────────────────────────

def resolve_aliases(lb_numbers: list[int], db_path=None) -> list[int]:
    """Collapse alias LBs to their canonical LBs. Returns de-duped canonical list.

    Each alias maps to exactly one canonical (max 1 hop; chain rewrites are
    enforced on insert by :func:`add_lb_alias`).

    Args:
        lb_numbers: List of LB numbers to resolve.
        db_path: Optional path to the SQLite database file.

    Returns:
        De-duplicated list of canonical LB numbers, preserving order of
        first occurrence.
    """
    if not lb_numbers:
        return []
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(lb_numbers))
    alias_map = {
        r["alias_lb"]: r["canonical_lb"]
        for r in conn.execute(
            f"SELECT alias_lb, canonical_lb FROM lb_alias WHERE alias_lb IN ({placeholders})",
            lb_numbers,
        )
    }
    resolved = [alias_map.get(lb, lb) for lb in lb_numbers]
    # De-dup preserving order of first occurrence
    seen: set[int] = set()
    out: list[int] = []
    for lb in resolved:
        if lb not in seen:
            seen.add(lb)
            out.append(lb)
    return out


def get_folder_links(folder_path: str, db_path=None) -> list[dict]:
    """Return all folder_lb_link rows for a path, sorted by lb_number.

    Args:
        folder_path: Absolute path of the folder.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of row dicts (keys: folder_path, lb_number, linked_at, note).
        Empty list if no links are stored.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM folder_lb_link WHERE folder_path=? ORDER BY lb_number",
        (folder_path,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_folder_link(folder_path: str, db_path=None) -> dict | None:
    """Return the first folder_lb_link row for a path, or None.

    Prefer get_folder_links() when multi-LB links are possible.
    """
    rows = get_folder_links(folder_path, db_path)
    return rows[0] if rows else None


def set_folder_link(
    folder_path: str, lb_number: int, note: str = "", xref: int = 0, db_path=None,
) -> None:
    """Add a folder→LB link, or refresh its xref if the pair already exists.

    The note and linked_at timestamp are only set on first insert (never
    overwritten on a re-run); ``xref`` is always kept current so a folder
    whose matched fileset changes on a later lookup (e.g. after a DB update)
    is reflected here too (FABLE_XREF_INCORPORATION.md D3).

    Args:
        folder_path: Absolute path of the folder.
        lb_number: LB number to link this folder to.
        note: Optional user note (first-insert only).
        xref: Xref fileset id this folder matches (0 = canonical).
        db_path: Optional path to the SQLite database file.
    """
    _fp, _lb, _note, _xref = folder_path, lb_number, note, xref
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO folder_lb_link (folder_path, lb_number, note, xref, linked_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(folder_path, lb_number) DO UPDATE SET xref=excluded.xref",
            (_fp, _lb, _note, _xref),
        )
    )


def replace_folder_link(
    folder_path: str, lb_number: int, note: str = "", xref: int = 0, db_path=None,
) -> None:
    """Replace all links for a folder with a single folder→LB link.

    Used by the user "Pin & continue" flow: a re-pin must supersede any
    previous pin (or auto-written multi-LB links) for the folder, unlike
    :func:`set_folder_link`, which is additive.

    Args:
        folder_path: Absolute path of the folder.
        lb_number: LB number the folder should be pinned to.
        note: Optional user note.
        xref: Xref fileset id this folder matches (0 = canonical).
        db_path: Optional path to the SQLite database file.
    """
    _fp, _lb, _note, _xref = folder_path, lb_number, note, xref

    def _run(c):
        c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_fp,))
        c.execute(
            "INSERT INTO folder_lb_link (folder_path, lb_number, note, xref, linked_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
            (_fp, _lb, _note, _xref),
        )

    get_write_queue().execute(_run)


def delete_folder_link(folder_path: str, db_path=None) -> None:
    """Remove a folder→LB link.

    Args:
        folder_path: Absolute path of the folder whose link should be deleted.
        db_path: Optional path to the SQLite database file.
    """
    _fp = folder_path
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_fp,))
    )


def rekey_folder_link(old_path: str, new_path: str, db_path=None) -> None:
    """Move folder_lb_link rows from old_path to new_path after a folder rename.

    A pin ("Pin & continue") is keyed on the exact folder path, so without this
    the link is orphaned the moment the folder is renamed and downstream steps
    (lbdir/rename/file) lose the pinned LB# on their next run.

    Args:
        old_path: Absolute path of the folder before renaming.
        new_path: Absolute path of the folder after renaming.
        db_path: Optional path to the SQLite database file.
    """
    _old, _new = old_path, new_path

    def _rekey(c):
        c.execute(
            "UPDATE OR IGNORE folder_lb_link SET folder_path=? WHERE folder_path=?",
            (_new, _old),
        )
        # Any rows left under _old conflicted with an existing (_new, lb_number)
        # link and were skipped by OR IGNORE — that link already exists, drop the stale one.
        c.execute("DELETE FROM folder_lb_link WHERE folder_path=?", (_old,))

    get_write_queue().execute(_rekey)


def add_lb_alias(
    alias_lb: int,
    canonical_lb: int,
    relationship: str = "duplicate",
    note: str = "",
    db_path=None,
) -> dict:
    """Add an alias mapping. Validates no cycles, rewrites chains if needed.

    Each alias is stored with max 1 hop: if canonical_lb is itself an alias,
    the target is rewritten to its canonical before storing.

    Args:
        alias_lb: The LB number being aliased (the 'wrong' or secondary one).
        canonical_lb: The LB number this alias resolves to.
        relationship: One of 'duplicate', 'supersedes', 'see_also'.
        note: Optional curator note.
        db_path: Optional path to the SQLite database file.

    Returns:
        Dict with keys alias_lb (int), canonical_lb (int), rewrote_chain (bool).

    Raises:
        ValueError: If alias_lb == canonical_lb, or if adding the alias
            would create a cycle.
    """
    if alias_lb == canonical_lb:
        raise ValueError("alias_lb and canonical_lb must differ")
    conn = get_connection(db_path)

    # Chain rewrite: if canonical_lb is itself an alias, use its canonical
    canon_of_canon = conn.execute(
        "SELECT canonical_lb FROM lb_alias WHERE alias_lb=?", (canonical_lb,)
    ).fetchone()
    rewrote = False
    if canon_of_canon:
        canonical_lb = canon_of_canon["canonical_lb"]
        rewrote = True

    # Cycle prevention: canonical must not be an alias of alias_lb
    would_cycle = conn.execute(
        "SELECT 1 FROM lb_alias WHERE alias_lb=? AND canonical_lb=?",
        (canonical_lb, alias_lb),
    ).fetchone()
    if would_cycle:
        raise ValueError(
            f"Adding alias {alias_lb}→{canonical_lb} would create a cycle"
        )

    _a, _c, _r, _n = alias_lb, canonical_lb, relationship, note
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT OR REPLACE INTO lb_alias (alias_lb, canonical_lb, relationship, note) "
            "VALUES (?,?,?,?)",
            (_a, _c, _r, _n),
        )
    )
    return {"alias_lb": alias_lb, "canonical_lb": canonical_lb, "rewrote_chain": rewrote}


def delete_lb_alias(alias_lb: int, db_path=None) -> None:
    """Remove an alias entry.

    Args:
        alias_lb: The alias LB number whose entry should be removed.
        db_path: Optional path to the SQLite database file.
    """
    _lb = alias_lb
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_alias WHERE alias_lb=?", (_lb,))
    )


def get_lb_aliases(canonical_lb: int | None = None, db_path=None) -> list[dict]:
    """Return alias rows, optionally filtered by canonical_lb.

    Args:
        canonical_lb: If provided, only return aliases that map to this
            canonical LB number.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of row dicts with keys alias_lb, canonical_lb, relationship,
        note, created_at.
    """
    conn = get_connection(db_path)
    if canonical_lb is not None:
        rows = conn.execute(
            "SELECT * FROM lb_alias WHERE canonical_lb=? ORDER BY alias_lb",
            (canonical_lb,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM lb_alias ORDER BY alias_lb"
        ).fetchall()
    return [dict(r) for r in rows]
