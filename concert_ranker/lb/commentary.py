"""Mine human commentary out of ``entries.description``.

This builds the *validation oracle* for calibration: the collector's own words
about each recording. ``calibrate.validate_labels`` checks the algorithm's
category labels against these mined keywords — if the algorithm calls something
"muddy" but no human ever did (and vice-versa), the label is miscalibrated.

The keyword vocabulary is the single source of truth in
:data:`concert_ranker.calibrate.LABEL_KEYWORDS`; this module only locates the
text and applies that vocabulary.
"""
from __future__ import annotations

import re
import sqlite3

from concert_ranker.calibrate import LABEL_KEYWORDS


def _compile() -> dict[str, list[re.Pattern]]:
    """Pre-compile word-boundary patterns for each label's keywords."""
    out: dict[str, list[re.Pattern]] = {}
    for label, keywords in LABEL_KEYWORDS.items():
        out[label] = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in keywords
        ]
    return out


_PATTERNS = _compile()


def mined_labels(text: str | None) -> list[str]:
    """Return the category labels whose keywords appear in ``text``.

    Uses word-boundary matching so "no bass" matches but "bassist" does not.
    """
    if not text:
        return []
    found = []
    for label, patterns in _PATTERNS.items():
        if any(p.search(text) for p in patterns):
            found.append(label)
    return found


def commentary_for(conn: sqlite3.Connection, lb_numbers=None) -> dict[int, str]:
    """Return ``{lb_number: description}`` for the requested entries.

    The raw description is the oracle text fed to ``validate_labels`` (which
    re-applies the keyword vocabulary itself).
    """
    sql = "SELECT lb_number, description FROM entries"
    params: list = []
    lbs = list(lb_numbers) if lb_numbers is not None else None
    if lbs:
        sql += " WHERE lb_number IN ({})".format(",".join("?" * len(lbs)))
        params.extend(lbs)
    return {int(r["lb_number"]): (r["description"] or "") for r in conn.execute(sql, params)}


def mine_entries(conn: sqlite3.Connection, lb_numbers=None) -> dict[int, dict]:
    """Mine commentary + asserted labels per entry.

    Returns ``{lb_number: {"commentary": text, "labels": [label, ...]}}`` —
    ``labels`` being the human-asserted categories for quick agreement checks
    against the algorithm's bands.
    """
    out: dict[int, dict] = {}
    for lb, text in commentary_for(conn, lb_numbers).items():
        out[lb] = {"commentary": text, "labels": mined_labels(text)}
    return out
