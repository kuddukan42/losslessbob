"""Derive a recording's source class (SBD / AUD / FM / UNKNOWN).

Calibration is conditioned *within* source class — an A-rated AUD and an
A-rated SBD do not sit on the same absolute curve — so every recording needs a
class label before thresholds are fitted.

Rather than re-implement lineage parsing, this reuses the recognisers already in
``backend/db.py`` (``classify_source_type`` / ``_classify_source_text``, which
understand ``AUD DAT`` / ``DAUD`` / ``SBD`` / ``soundboard`` / ``pre-FM`` etc.)
and folds their finer-grained output down to the four classes the scoring config
(:data:`concert_ranker.config.SOURCE_CLASSES`) conditions on.
"""
from __future__ import annotations

import sqlite3

# backend's display labels → our four conditioning classes.
# 'Mixed' (matrix) and 'ALD' are deliberately left UNKNOWN: a matrix is part SBD
# part AUD and belongs on neither pure curve, so it must not contaminate either
# class's fitted thresholds.
_LABEL_TO_CLASS = {
    "Soundboard": "SBD",
    "FM/Pre-FM": "FM",
    "Audience": "AUD",
    "Mixed": "UNKNOWN",
    "ALD": "UNKNOWN",
}

# The curator-maintained ``entries.source_type`` column is the authoritative
# label when set (a human read the lineage), so it is preferred over free-text
# mining. Same four-class folding; Mixed/ALD → UNKNOWN.
_CURATOR_TO_CLASS = {
    "Soundboard": "SBD",
    "FM/Pre-FM": "FM",
    "Audience": "AUD",
    "Mixed": "UNKNOWN",
    "ALD": "UNKNOWN",
    "Master": "UNKNOWN",  # a master tape's path to source isn't a listening class
}

VALID_CLASSES = ("SBD", "AUD", "FM", "UNKNOWN")


def derive_source_class(description: str | None, source_chain: str | None,
                        curator_source_type: str | None = None) -> str:
    """Return one of SBD / AUD / FM / UNKNOWN for a single recording.

    The curator-edited ``entries.source_type`` is trusted first when present (a
    human classified it); otherwise fall back to mining the free-text lineage.

    Args:
        description: Free-text ``entries.description``.
        source_chain: Parsed ``entries.source_chain``.
        curator_source_type: ``entries.source_type`` (curator label), or None.
    """
    if curator_source_type:
        return _CURATOR_TO_CLASS.get(curator_source_type, "UNKNOWN")

    from backend.db import classify_source_type  # lazy: avoid import at module load

    label = classify_source_type(description, source_chain)
    return _LABEL_TO_CLASS.get(label or "", "UNKNOWN")


def classify_entries(conn: sqlite3.Connection,
                     lb_numbers=None) -> dict[int, str]:
    """Derive source class for many entries from the DB.

    Prefers the curator ``entries.source_type`` column, falling back to free-text
    lineage mining where it is NULL.

    Args:
        conn: Open connection to ``losslessbob.db``.
        lb_numbers: Optional iterable to restrict to; None classifies all entries.

    Returns:
        ``{lb_number: source_class}``.
    """
    sql = "SELECT lb_number, description, source_chain, source_type FROM entries"
    params: list = []
    lbs = list(lb_numbers) if lb_numbers is not None else None
    if lbs:
        sql += " WHERE lb_number IN ({})".format(",".join("?" * len(lbs)))
        params.extend(lbs)
    out: dict[int, str] = {}
    for row in conn.execute(sql, params):
        out[int(row["lb_number"])] = derive_source_class(
            row["description"], row["source_chain"], row["source_type"]
        )
    return out
