#!/usr/bin/env python3
"""Snapshot the Olof tables before a reparse, then diff and explain every change.

Reparse diff gate for the show-dossier redesign (TODO-342, audit P9,
instructions/SHOW_DOSSIER_REDESIGN_PLAN.md Phase 1). The plan changes
backend/olof_parser.py in seven named ways, P1a–P1g. A full reparse rewrites
every DSN event, so this tool proves the rewrite did only those things:

1. ``snapshot`` copies olof_events / olof_songs into ``.debug/olof_before.db``.
2. Run the reparse: ``.venv/bin/python3 -m backend.olof_parser``.
3. ``diff`` compares the snapshot with the live tables, explains each change by
   the fix that accounts for it and writes ``.debug/olof_reparse_diff.md``. A
   change no rule explains lands in UNEXPLAINED and the command exits 1 — the
   reparse is not committed until every such change is understood, and either
   the parser or a rule here is corrected.

Usage::

    .venv/bin/python3 tools/olof_reparse_diff.py snapshot [--force]
    .venv/bin/python3 tools/olof_reparse_diff.py diff

Run from the project root.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.olof_parser import (  # noqa: E402
    HISTORY_DATE_RE,
    ROTATION_LESS_RE,
    ROTATION_PREV_RE,
    ROTATION_TOUR_RE,
)
from backend.paths import DB_PATH  # noqa: E402

# MONTH_YEAR_RE / ROTATION_FRAGMENT_RE live in backend/qc/rules.py (TODO-342 Phase 2,
# R-O3) since backend must not import from tools/; this tool and
# tools/dossier_acceptance.py both import the shared copy from there.
from backend.qc.rules import MONTH_YEAR_RE, ROTATION_FRAGMENT_RE  # noqa: E402

_log = logging.getLogger(__name__)

DEBUG_DIR = _PROJECT_ROOT / ".debug"
DEFAULT_SNAPSHOT = DEBUG_DIR / "olof_before.db"
DEFAULT_REPORT = DEBUG_DIR / "olof_reparse_diff.md"

BUCKETS = ("P1a", "P1b", "P1c", "P1d", "P1e", "P1f", "P1g")
UNEXPLAINED = "UNEXPLAINED"
_MAX_LISTED = 150  # events listed per explained bucket; UNEXPLAINED is always listed in full


def _strip_stat(text: str) -> str:
    """Cut every rotation-stat phrase the parser recognises (P1d) out of *text*."""
    for rx in (ROTATION_PREV_RE, ROTATION_TOUR_RE, ROTATION_LESS_RE):
        text = rx.sub(" ", text)
    return text


# Wording P1f strips from a release token: 'and part of 22 released on X' → 'X'.
_RELEASE_PREFIX_RE = re.compile(
    r"^(?:\((?:part|uncertain)\)\s*)*"
    r"(?:(?:,\s*(?:and|or)?|and|or)\s*(?:part\s+of\s+)?\d+(?:\s*-\s*\d+)?\s*)*"
    r"(?:(?:partly|fragments?)\s+)?(?:(?:released|available)\s+(?:on|in|as|from)\s+)?",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[^\W_]+")

# Event columns a Phase 1 fix may legitimately change; every other column must not move.
_EVENT_MOVABLE = frozenset({
    "notes", "releases_raw", "bobtalk", "references_raw", "rotation_new", "rotation_pct",
    "tour_new_count", "venue_history_raw",
})
# Section text the P1c list and the P1d stat can sit in (whichever label precedes them).
_SECTION_COLS = ("notes", "releases_raw", "bobtalk", "references_raw")
_ROTATION_COLS = ("rotation_new", "rotation_pct", "tour_new_count")
# Song columns with their own rule below; every other column must not move.
_SONG_HANDLED = frozenset({
    "event_id", "position", "song_title", "credits", "subtitle", "annotations", "released_on",
})


@dataclass
class EventDiff:
    """What changed on one event and which Phase 1 fix explains it."""

    event_id: int
    date_str: str
    buckets: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """True when anything moved, explained or not."""
        return bool(self.buckets or self.problems)


def _blank(value):
    return "" if value is None else value


def _ws(text) -> str:
    return " ".join(str(text or "").split())


def _wordy(text: str) -> str:
    return " ".join(t for t in text.split() if re.search(r"\w", t))


def _tokens(text) -> list[str]:
    return [t.strip() for t in str(text or "").split(";") if t.strip()]


def _words(*parts) -> Counter:
    return Counter(w.casefold() for p in parts for w in _WORD_RE.findall(str(p or "")))


def _release_norm(token: str) -> str:
    return _ws(_RELEASE_PREFIX_RE.sub("", token, count=1)).casefold()


def _ranges(nums: list[int]) -> str:
    out: list[str] = []
    start = prev = nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if n is not None:
            start = prev = n
    return ", ".join(out)


def _explain_moved_text(d: EventDiff, before: dict, after: dict) -> None:
    """notes / releases_raw / venue_history_raw: only P1c and P1d may move text."""
    vh_before = _ws(before.get("venue_history_raw"))
    vh_after = _ws(after.get("venue_history_raw"))
    blobs: list[str] = []
    if vh_after != vh_before:
        chunks = [_ws(c) for c in str(after.get("venue_history_raw") or "").split("\n\n")]
        if vh_before:
            d.problems.append("venue_history_raw changed from a non-empty value")
        elif all(c in _ws(before.get("raw_text")) for c in chunks):
            blobs = chunks
            d.buckets.add("P1c")
            d.notes.append(f"{len(chunks)} venue-history list(s) lifted")
        else:
            d.problems.append("venue_history_raw set to text the page does not contain")
    for col in _SECTION_COLS:
        old, new = _ws(before.get(col)), _ws(after.get(col))
        if old == new:
            continue
        residual, used = old, []
        for blob in blobs:
            if blob in residual:
                residual = _ws(residual.replace(blob, " "))
                used.append("P1c")
        stripped = _ws(_strip_stat(residual))
        if stripped != residual:
            residual = stripped
            used.append("P1d")
        if used and _wordy(residual) == _wordy(new):  # a stray '.' paragraph may stay behind
            used = list(dict.fromkeys(used))
            d.buckets.update(used)
            d.notes.append(f"{col}: {'+'.join(used)} text removed")
        else:
            d.problems.append(f"{col} changed beyond the P1c/P1d removals")


def _explain_rotation(d: EventDiff, before: dict, after: dict) -> None:
    """rotation_* / tour_new_count may only go from NULL to a value the page states."""
    if all(before.get(c) == after.get(c) for c in _ROTATION_COLS):
        return
    if any(before.get(c) is not None for c in _ROTATION_COLS):
        d.problems.append("rotation stats changed from non-NULL values")
    elif ROTATION_FRAGMENT_RE.search(before.get("raw_text") or ""):
        d.buckets.add("P1d")
        d.notes.append("rotation stats " + "/".join(str(after.get(c)) for c in _ROTATION_COLS))
    else:
        d.problems.append("rotation stats set, but the page text has no stat line")


def _explain_song(d: EventDiff, pos: int, old: dict, new: dict, context: str,
                  raw: str, venue_history: str = "") -> None:
    """One song position present before and after."""
    for col in sorted((set(old) | set(new)) - _SONG_HANDLED):
        if _blank(old.get(col)) != _blank(new.get(col)):
            d.problems.append(f"song {pos}: {col} changed")

    title_cols = ("song_title", "credits", "subtitle")
    if any(_blank(old.get(c)) != _blank(new.get(c)) for c in title_cols):
        if _words(*(old.get(c) for c in title_cols)) == _words(*(new.get(c) for c in title_cols)):
            d.buckets.add("P1e")
        else:
            d.problems.append(f"song {pos}: title/credits text changed, not just re-split")

    old_ann, new_ann = Counter(_tokens(old.get("annotations"))), Counter(_tokens(new.get("annotations")))
    new_rel_norm = {_release_norm(t) for t in _tokens(new.get("released_on"))}
    for tok in (new_ann - old_ann).elements():
        d.problems.append(f"song {pos}: annotation added {tok!r}")
    for tok in (old_ann - new_ann).elements():
        if _release_norm(tok) in new_rel_norm:
            d.buckets.add("P1f")  # "released in/as ..." now read as a release line
        elif MONTH_YEAR_RE.match(tok) or HISTORY_DATE_RE.match(f"{pos} {tok}"):
            d.buckets.add("P1b")
        elif ROTATION_FRAGMENT_RE.search(tok):
            d.buckets.add("P1d")
        elif _ws(tok).casefold() in venue_history:
            d.buckets.add("P1c")
        elif _ws(tok).casefold() in context:
            d.buckets.add("P1g")
        else:
            d.problems.append(f"song {pos}: annotation removed {tok!r}")

    old_rel, new_rel = Counter(_tokens(old.get("released_on"))), Counter(_tokens(new.get("released_on")))
    if old_rel == new_rel:
        return
    old_n = Counter(_release_norm(t) for t in old_rel.elements())
    new_n = Counter(_release_norm(t) for t in new_rel.elements())
    explained = True
    for tok in (old_n - new_n).elements():
        explained = False
        d.problems.append(f"song {pos}: release dropped {tok!r}")
    for tok in (new_n - old_n).elements():
        if not re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", raw):
            explained = False
            d.problems.append(f"song {pos}: release {tok!r} is not in the page text")
    if explained:
        d.buckets.add("P1f")


def classify_event(event_id: int, before: dict | None, after: dict | None,
                   before_songs: list[dict], after_songs: list[dict]) -> EventDiff:
    """Explain every difference between an event's snapshot and live rows.

    Args:
        event_id: The olof_events key.
        before: Snapshot event row as a dict, or None if the event is new.
        after: Live event row as a dict, or None if the event is gone.
        before_songs: Snapshot olof_songs rows for the event.
        after_songs: Live olof_songs rows for the event.

    Returns:
        EventDiff whose ``buckets`` name the fixes that explain the changes and
        whose ``problems`` list every change no rule explains.
    """
    d = EventDiff(event_id, _blank((after or before or {}).get("date_str")))
    if before is None or after is None:
        d.problems.append("event added" if before is None else "event removed")
        return d

    for col in sorted((set(before) | set(after)) - _EVENT_MOVABLE):
        if _blank(before.get(col)) != _blank(after.get(col)):
            d.problems.append(f"event.{col} changed")
    _explain_moved_text(d, before, after)
    _explain_rotation(d, before, after)

    b = {s["position"]: s for s in before_songs}
    a = {s["position"]: s for s in after_songs}
    lost, gained = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
    if lost:
        d.problems.append(f"songs lost at positions {_ranges(lost)}")
    if gained:
        d.buckets.add("P1a")
        d.notes.append(f"songs {len(b)} -> {len(a)}")
    context = _ws(f"{_blank(before.get('bobtalk'))} {_blank(before.get('references_raw'))}").casefold()
    raw = _ws(before.get("raw_text")).casefold()
    venue_history = _ws(after.get("venue_history_raw")).casefold()
    for pos in sorted(b.keys() & a.keys()):
        _explain_song(d, pos, b[pos], a[pos], context, raw, venue_history)
    return d


def _ro_uri(path: Path) -> str:
    return Path(path).resolve().as_uri() + "?mode=ro"


def snapshot(db_path: Path, out: Path, force: bool = False) -> dict[str, int]:
    """Copy olof_events / olof_songs from *db_path* into a fresh *out* file.

    Args:
        db_path: Live DB, opened read-only.
        out: Snapshot file to create.
        force: Replace an existing snapshot. Without it an existing file is kept,
            because it is the pre-reparse baseline.

    Returns:
        Row counts copied, keyed by table.

    Raises:
        FileExistsError: *out* exists and *force* is false.
    """
    out = Path(out)
    if out.exists():
        if not force:
            raise FileExistsError(f"{out} exists (the pre-reparse baseline); pass --force")
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(out.resolve().as_uri() + "?mode=rwc", uri=True)
    try:
        dst.execute("ATTACH DATABASE ? AS live", (_ro_uri(db_path),))
        counts = {}
        for table in ("olof_events", "olof_songs"):
            dst.execute(f"CREATE TABLE main.{table} AS SELECT * FROM live.{table}")
            counts[table] = dst.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        dst.execute("CREATE TABLE snapshot_meta (key TEXT PRIMARY KEY, value TEXT)")
        dst.executemany("INSERT INTO snapshot_meta VALUES (?, ?)", [
            ("taken_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
            ("source_db", str(db_path)),
        ])
        dst.commit()
    finally:
        dst.close()
    return counts


def _load(conn: sqlite3.Connection, schema: str) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    events = {r["event_id"]: dict(r) for r in conn.execute(f"SELECT * FROM {schema}.olof_events")}
    songs: dict[int, list[dict]] = defaultdict(list)
    for r in conn.execute(f"SELECT * FROM {schema}.olof_songs ORDER BY event_id, position"):
        songs[r["event_id"]].append(dict(r))
    return events, songs


def diff(db_path: Path, snapshot_path: Path) -> tuple[list[EventDiff], dict[str, str]]:
    """Classify every event that differs between *snapshot_path* and *db_path*.

    Args:
        db_path: Live DB (read-only).
        snapshot_path: File written by :func:`snapshot`.

    Returns:
        (one EventDiff per event in either side, snapshot_meta as a dict).
    """
    conn = sqlite3.connect(_ro_uri(db_path), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("ATTACH DATABASE ? AS snap", (_ro_uri(snapshot_path),))
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM snap.snapshot_meta")}
        b_events, b_songs = _load(conn, "snap")
        a_events, a_songs = _load(conn, "main")
    finally:
        conn.close()
    diffs = [
        classify_event(eid, b_events.get(eid), a_events.get(eid),
                       b_songs.get(eid, []), a_songs.get(eid, []))
        for eid in sorted(b_events.keys() | a_events.keys())
    ]
    return diffs, meta


def render_report(diffs: list[EventDiff], db_path: Path, snapshot_path: Path,
                  meta: dict[str, str]) -> str:
    """Markdown report: bucket table, UNEXPLAINED in full, then each bucket's events."""
    changed = [x for x in diffs if x.changed]
    unexplained = [x for x in changed if x.problems]
    lines = [
        f"# Olof reparse diff — {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- Snapshot: `{snapshot_path}` (taken {meta.get('taken_at', '?')})",
        f"- Live: `{db_path}`",
        f"- Events compared: {len(diffs)}; changed: {len(changed)}; "
        f"{UNEXPLAINED}: {len(unexplained)}",
        "",
        "| Bucket | Events |",
        "|---|---|",
        f"| {UNEXPLAINED} | {len(unexplained)} |",
    ]
    lines += [f"| {b} | {sum(1 for x in changed if b in x.buckets)} |" for b in BUCKETS]
    lines += ["", f"## {UNEXPLAINED} ({len(unexplained)})", ""]
    for x in unexplained:
        also = f" (also {', '.join(sorted(x.buckets))})" if x.buckets else ""
        lines.append(f"- {x.event_id} {x.date_str} — {'; '.join(x.problems)}{also}")
    for b in BUCKETS:
        members = [x for x in changed if b in x.buckets]
        lines += ["", f"## {b} ({len(members)})", ""]
        for x in members[:_MAX_LISTED]:
            lines.append(f"- {x.event_id} {x.date_str} — {'; '.join(x.notes) or b}")
        if len(members) > _MAX_LISTED:
            lines.append(f"- … and {len(members) - _MAX_LISTED} more")
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Live DB (default: data/).")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="Copy the Olof tables before a reparse.")
    snap.add_argument("--force", action="store_true", help="Replace an existing snapshot.")
    rep = sub.add_parser("diff", help="Explain every change since the snapshot.")
    rep.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = _parse_args(argv)
    if args.cmd == "snapshot":
        try:
            counts = snapshot(args.db, args.snapshot, force=args.force)
        except FileExistsError as exc:
            _log.error("%s", exc)
            return 2
        _log.info("snapshot %s  events=%d songs=%d", args.snapshot,
                  counts["olof_events"], counts["olof_songs"])
        return 0
    diffs, meta = diff(args.db, args.snapshot)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(diffs, args.db, args.snapshot, meta), encoding="utf-8")
    changed = [x for x in diffs if x.changed]
    unexplained = sum(1 for x in changed if x.problems)
    per_bucket = " ".join(f"{b}={sum(1 for x in changed if b in x.buckets)}" for b in BUCKETS)
    _log.info("diff  changed=%d  %s=%d  %s  -> %s", len(changed), UNEXPLAINED, unexplained,
              per_bucket, args.report)
    return 1 if unexplained else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
