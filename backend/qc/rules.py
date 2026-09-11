"""QC rule definitions for the Show Dossier redesign (TODO-342 Phase 2).

Each rule is a pure function ``(conn) -> Iterable[Finding]`` registered in
:data:`RULES`. Rules never write to the database — :mod:`backend.qc.store`
owns all writes to ``qc_findings``/``qc_decision_log``/``qc_runs``.

``MONTH_YEAR_RE`` and ``ROTATION_FRAGMENT_RE`` are defined here (not in
``tools/``) because backend code must not import from ``tools/``; both
``tools/olof_reparse_diff.py`` and ``tools/dossier_acceptance.py`` import them
from this module instead of defining their own copies.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

# 'March 1978' — what a venue-history date line ('1 March 1978') leaves behind
# once its leading day is read as a song position (P1b).
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
MONTH_YEAR_RE = re.compile(rf"^(?:\d{{1,2}}\s+)?(?:{_MONTHS})\s+\d{{4}}\.?$", re.IGNORECASE)

# Any fragment of Olof's rotation-stat line (P1d).
ROTATION_FRAGMENT_RE = re.compile(
    r"compared to previous concert|new songs? for this tour", re.IGNORECASE
)

# A numbered setlist line ('12. Like A Rolling Stone'), used to count how many
# songs Olof's raw page text lists versus how many the parser produced.
_NUMBERED_LINE_RE = re.compile(r"^(\d+)\.(?:\s|$)", re.MULTILINE)


def _tokens(text) -> list[str]:
    """Split a ';'-joined annotations/released_on string into trimmed tokens."""
    return [t.strip() for t in str(text or "").split(";") if t.strip()]


@dataclass
class Finding:
    """One QC finding a rule function emits for a single entity.

    Attributes:
        entity_kind: What kind of row this finding is about (e.g. 'olof_event').
        entity_key: Stable string key identifying the entity within its kind.
        severity: 'error', 'warn', or 'info'.
        detail: Human-readable one-line explanation.
        evidence: JSON-serialisable dict backing the finding, hashed by the
            run engine to detect whether the underlying data changed.
    """

    entity_kind: str
    entity_key: str
    severity: str
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass
class RuleDef:
    """A registered QC rule.

    Attributes:
        rule_id: Stable ID, e.g. 'R-O1'.
        description: One-line description shown in the CLI/console.
        severity: Default severity for findings this rule emits.
        func: ``(conn) -> Iterable[Finding]``.
    """

    rule_id: str
    description: str
    severity: str
    func: Callable[[sqlite3.Connection], Iterable[Finding]]


def rule_o1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O1: an Olof concert's raw numbered-song count exceeds its parsed count.

    Mirrors the truncated-concert count in ``tools/dossier_acceptance.py``
    (``parser_metrics``): counts distinct numbered lines ('12. ...') in
    ``raw_text`` and compares against the row count in ``olof_songs``.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per truncated concert.
    """
    song_counts = dict(conn.execute("SELECT event_id, COUNT(*) FROM olof_songs GROUP BY event_id"))
    rows = conn.execute(
        "SELECT event_id, date_str, raw_text FROM olof_events"
        " WHERE event_type='concert' AND source != 'bobserve'"
    )
    for ev in rows:
        raw = ev["raw_text"] or ""
        numbered = len(set(_NUMBERED_LINE_RE.findall(raw)))
        parsed = song_counts.get(ev["event_id"], 0)
        if parsed < numbered:
            yield Finding(
                entity_kind="olof_event",
                entity_key=str(ev["event_id"]),
                severity="error",
                detail=(
                    f"{ev['date_str'] or '?'}: parsed {parsed} songs but the raw page "
                    f"lists {numbered} numbered lines"
                ),
                evidence={"date": ev["date_str"], "parsed": parsed, "numbered": numbered},
            )


def rule_o3(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O3: a song's annotations contain a date-shaped or stat-shaped fragment.

    Mirrors ``tools/dossier_acceptance.py``'s ``date_line_annotation_rows`` /
    ``rotation_stat_song_rows`` counters: an annotation token matching
    ``MONTH_YEAR_RE`` (a stray venue-history date) or ``ROTATION_FRAGMENT_RE``
    (a stray rotation-stat fragment) means the parser left page furniture in
    the song row instead of stripping it.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per affected song row.
    """
    rows = conn.execute(
        "SELECT s.event_id, s.position, s.song_title, s.annotations, e.date_str"
        " FROM olof_songs s JOIN olof_events e USING (event_id)"
        " WHERE e.source != 'bobserve'"
    )
    for row in rows:
        tokens = _tokens(row["annotations"])
        bad = [
            t for t in tokens
            if MONTH_YEAR_RE.match(t) or ROTATION_FRAGMENT_RE.search(t)
        ]
        if bad:
            yield Finding(
                entity_kind="olof_song",
                entity_key=f"{row['event_id']}:{row['position']}",
                severity="error",
                detail=(
                    f"{row['date_str'] or '?'}: song '{row['song_title']}' annotation "
                    f"looks like a stray date/stat fragment: {bad!r}"
                ),
                evidence={
                    "date": row["date_str"],
                    "song_title": row["song_title"],
                    "tokens": tokens,
                },
            )


RULES: dict[str, RuleDef] = {
    "R-O1": RuleDef(
        rule_id="R-O1",
        description="Olof raw numbered-song count exceeds parsed count",
        severity="error",
        func=rule_o1,
    ),
    "R-O3": RuleDef(
        rule_id="R-O3",
        description="Date-shaped or stat-shaped song annotation",
        severity="error",
        func=rule_o3,
    ),
}
