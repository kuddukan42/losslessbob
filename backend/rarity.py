"""Source-tape rarity — how many analysed copies exist of each recording's tape (TODO-335).

A TapeMatch family is one source tape; its member count is the number of
circulating copies the pipeline has heard. ``recording_families`` (synced by
``backend.tapematch_sync``) holds one row per analysed LB, so the per-LB copy
count is just the size of its family.

Two caveats travel with every number, and the GUI must say them:

* **Over-merge** (TODO-319/325) can only move tapes *out* of the single-copy
  bucket, never in, so "only known copy" is a conservative flag; the copy
  counts of large families are the unreliable end.
* **Unanalysed siblings** (TODO-334): entries on the same date that tapematch
  never ingested (private/no-torrent paths, catalogued after the run). A tape
  that is single-copy on a date with unanalysed siblings may have a copy we have
  not measured, so ``unanalysed_on_date`` is returned alongside the flag.

Read-only; never writes the DB.
"""
from __future__ import annotations

import sqlite3
from collections import Counter

from backend.geocoder import entry_date_to_iso

# Compilations reuse other recordings' audio — they are not independent
# captures, so they never count as an unanalysed sibling.
_NON_CAPTURE_CATEGORIES = frozenset({"compilation"})


def unanalysed_by_date(conn: sqlite3.Connection, dates: set[str]) -> Counter:
    """Count catalogued entries per ISO date that have no TapeMatch family.

    Args:
        conn: App DB connection.
        dates: ISO dates to count for (the dates tapematch has run).

    Returns:
        ``Counter`` of ISO date -> entries on that date absent from
        ``recording_families``.
    """
    analysed = {r[0] for r in conn.execute("SELECT lb_number FROM recording_families")}
    out: Counter = Counter()
    for lb, date_str, category in conn.execute(
        "SELECT lb_number, date_str, lb_category FROM entries "
        "WHERE date_str IS NOT NULL AND date_str != ''"
    ):
        if lb in analysed or (category or "") in _NON_CAPTURE_CATEGORIES:
            continue
        iso = entry_date_to_iso(date_str)
        if iso in dates:
            out[iso] += 1
    return out


def lb_rarity(conn: sqlite3.Connection) -> list[dict]:
    """Per-LB copy count and "only known copy" flag over the synced families.

    Args:
        conn: App DB connection.

    Returns:
        One dict per analysed LB, sorted by ``lb_number``: ``lb_number``,
        ``fam_id``, ``concert_date``, ``copies`` (members of its family),
        ``only_known_copy`` (``copies == 1``) and ``unanalysed_on_date``.
    """
    rows = [tuple(r) for r in conn.execute(
        "SELECT lb_number, fam_id, concert_date FROM recording_families"
    )]
    sizes = Counter(r[1] for r in rows)
    unseen = unanalysed_by_date(conn, {r[2] for r in rows})
    return [
        {
            "lb_number": lb,
            "fam_id": fam,
            "concert_date": date,
            "copies": sizes[fam],
            "only_known_copy": sizes[fam] == 1,
            "unanalysed_on_date": unseen.get(date, 0),
        }
        for lb, fam, date in sorted(rows)
    ]
