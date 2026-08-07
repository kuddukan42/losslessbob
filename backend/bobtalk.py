"""Locate Olof's curated bobtalk quotes inside our own recordings (TODO-303).

The approach inverts TODO-293's failed one. Open ASR transcription of a Dylan
audience tape is not trustworthy — see ``CALIBRATION_PROGRESS.md`` "§3
banter/ASR signal" — but we do not need it to be. Olof already supplies the
words in ``olof_events.bobtalk``; ASR only has to be right *enough to recognise
text we already hold*. Fuzzy-matching a garbled decode against a known target
is a far easier problem than authoring one, so the decoder's fidelity ceiling
stops mattering.

What this module owns: parsing a bobtalk block into quotes, scoring quotes
against decoded audio windows, deciding confidence, and persistence. It
deliberately has **no ASR dependency** so it stays unit-testable without
faster-whisper installed; the decode pass lives in ``tools/bobtalk_locate.py``
and hands token sets in here.

The stored artifact is a *timestamp*, never a transcript: the quote text
already lives in ``olof_events.bobtalk`` in this same database, so a location
row references it by index rather than copying it.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass

log = logging.getLogger(__name__)

# ── tuning ───────────────────────────────────────────────────────────────────
# A quote must clear this Dice overlap against a window's decoded tokens before
# it can be considered located at all. Measured on the 1978-12-16 PoC: genuine
# matches landed 0.54-0.82, non-matches 0.00-0.10.
MIN_DICE = 0.30

# ...and it must beat the RUNNER-UP window by this factor. This is the load
# bearing rule and the reason no absolute threshold needs careful tuning: on the
# PoC every true match beat its runner-up by 3-6x (0.82/0.17, 0.76/0.14,
# 0.72/0.12, 0.59/0.14, 0.54/0.15) while every failure TIED its runner-up
# (0.00/0.00, 0.10/0.10). Separation, not magnitude, is what distinguishes
# "found it" from "matched noise equally badly everywhere".
MIN_RATIO = 2.0

# Below this many content tokens a quote cannot be matched reliably — short
# stock lines ("Thank you") collide with everything.
MIN_QUOTE_TOKENS = 4

# Olof's bobtalk field occasionally carries release/catalogue lines rather than
# speech (55 of 859 blocks are suspiciously short). These are dropped.
MIN_QUOTE_CHARS = 40

_STOPWORDS = frozenset("""
a an and are as at be been but by can did do does for from had has have he her
his i if in into is it its me my no not of on or our out she so than that the
their them then there these they this to too up very was we were what when
which who will with would you your
""".split())

# Catalogue / release noise: "Wanted Man WMM 58/59.", "Bootleg", "CD 1-2".
# The code pattern is deliberately CASE-SENSITIVE: real catalogue codes are
# upper-case, and matching case-insensitively would swallow ordinary speech —
# "In 1963, ..." reads as <2+ letters><number> and would be discarded, which
# silently dropped the strongest match on the 1978-12-16 PoC.
_CATALOGUE_CODE_RE = re.compile(r"\b[A-Z]{2,}\s*\d+(?:[/-]\d+)?\b")
_RELEASE_PREFIX_RE = re.compile(r"^\s*(bootleg|cd|disc|vol\.?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Quote:
    """One parsed bobtalk utterance.

    Attributes:
        index: Position within the event's bobtalk block, 0-based. This is the
            stable key a location row references; the text itself is not copied.
        text: The quote as Olof wrote it.
        tokens: Content tokens used for matching.
    """

    index: int
    text: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class Match:
    """A quote's best-scoring window, with the runner-up that qualifies it.

    Attributes:
        quote_index: The :class:`Quote` this match belongs to.
        window_index: Index of the winning window in the decoded sequence.
        t_start: Window start in source-local seconds.
        dice: Dice overlap of the winning window.
        runner_up: Dice overlap of the second-best window.
        confident: Whether the match clears both gates.
    """

    quote_index: int
    window_index: int
    t_start: float
    dice: float
    runner_up: float
    confident: bool


def content_tokens(text: str) -> frozenset[str]:
    """Reduce text to lowercase content tokens for Dice comparison.

    Mirrors ``tapematch.asr.content_tokens`` so a quote and a decoded window are
    tokenised identically. Apostrophes are kept inside words ("rollin'"), and
    stopwords are dropped so two utterances are compared on what they are about
    rather than on grammar.

    Args:
        text: Raw text.

    Returns:
        The frozen set of content tokens.
    """
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def dice(a: frozenset[str], b: frozenset[str]) -> float:
    """Return the Dice coefficient of two token sets (0.0 when either is empty)."""
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / float(len(a) + len(b))


def is_metadata_line(line: str) -> bool:
    """Return True when a bobtalk line is release/catalogue noise, not speech.

    Olof's ``bobtalk`` field bleeds catalogue references in some events (a
    "Bootleg" label, a release code). Those must not be searched for in audio.

    Args:
        line: One stripped line from a bobtalk block.

    Returns:
        True if the line looks like metadata rather than something said aloud.
    """
    if not line:
        return True
    return bool(_CATALOGUE_CODE_RE.search(line) or _RELEASE_PREFIX_RE.match(line))


def parse_bobtalk(block: str | None) -> list[Quote]:
    """Split an ``olof_events.bobtalk`` block into matchable quotes.

    Args:
        block: The raw bobtalk text, or None.

    Returns:
        Quotes long enough and distinctive enough to locate, in document order.
        Indexes are assigned over the *retained* quotes so they stay stable for
        a given block.
    """
    if not block:
        return []
    out: list[Quote] = []
    for raw in block.splitlines():
        line = " ".join(raw.split())
        if len(line) < MIN_QUOTE_CHARS or is_metadata_line(line):
            continue
        toks = content_tokens(line)
        if len(toks) < MIN_QUOTE_TOKENS:
            continue
        out.append(Quote(index=len(out), text=line, tokens=toks))
    return out


def match_quote(quote: Quote, windows: list[tuple[float, frozenset[str]]]) -> Match | None:
    """Pick the window that best matches *quote*, and qualify it by separation.

    Every window is scored and the best is compared against the runner-up.
    Crucially this makes **no assumption about where in the show the quote
    belongs**: inferring the window from the setlist position was tried on the
    PoC and drifts, failing in both directions.

    Args:
        quote: The quote to place.
        windows: ``(t_start, decoded_tokens)`` for each candidate window, in
            time order.

    Returns:
        The best :class:`Match`, or None when there are no windows. A returned
        match may still have ``confident=False``.
    """
    if not windows:
        return None
    scored = sorted(
        ((dice(toks, quote.tokens), i, t) for i, (t, toks) in enumerate(windows)),
        key=lambda s: (-s[0], s[1]),
    )
    best_d, best_i, best_t = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    confident = best_d >= MIN_DICE and best_d >= MIN_RATIO * runner
    return Match(quote_index=quote.index, window_index=best_i, t_start=best_t,
                 dice=round(best_d, 4), runner_up=round(runner, 4), confident=confident)


def locate_quotes(quotes: list[Quote],
                  windows: list[tuple[float, frozenset[str]]]) -> list[Match]:
    """Match every quote against the decoded windows.

    Args:
        quotes: Parsed quotes from :func:`parse_bobtalk`.
        windows: ``(t_start, decoded_tokens)`` per window, in time order.

    Returns:
        One :class:`Match` per quote that produced one, in quote order.
    """
    out = []
    for q in quotes:
        m = match_quote(q, windows)
        if m is not None:
            out.append(m)
    return out


# ── persistence ──────────────────────────────────────────────────────────────
def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the ``bobtalk_locations`` table and index if absent.

    Idempotent per the repo's SQLite rules: ``CREATE TABLE IF NOT EXISTS`` plus
    a ``PRAGMA table_info`` check before any ``ALTER``.

    Args:
        conn: Open connection to the main database.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bobtalk_locations (
            lb_number   INTEGER NOT NULL,   -- the recording searched
            event_id    INTEGER NOT NULL,   -- olof_events.event_id supplying the text
            quote_index INTEGER NOT NULL,   -- index into parse_bobtalk(block)
            t_start     REAL    NOT NULL,   -- source-local seconds
            dice        REAL    NOT NULL,
            runner_up   REAL    NOT NULL,
            confident   INTEGER NOT NULL,   -- 1 = clears MIN_DICE and MIN_RATIO
            model       TEXT,               -- ASR model that produced the decode
            located_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lb_number, event_id, quote_index)
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bobtalk_locations)")}
    for name, decl in (("model", "TEXT"),):
        if name not in cols:
            conn.execute(f"ALTER TABLE bobtalk_locations ADD COLUMN {name} {decl}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bobtalk_loc_lb ON bobtalk_locations(lb_number)"
    )


def save_locations(conn: sqlite3.Connection, lb_number: int, event_id: int,
                   matches: list[Match], model: str | None = None) -> int:
    """Upsert located quotes for one recording.

    A re-run replaces that recording's rows for the event, so re-locating with a
    better model does not leave stale timestamps behind.

    Args:
        conn: Open connection to the main database.
        lb_number: The recording the timestamps refer to.
        event_id: ``olof_events.event_id`` the quotes came from.
        matches: Matches to store (both confident and not).
        model: ASR model identifier for provenance.

    Returns:
        Number of rows written.
    """
    ensure_schema(conn)
    conn.execute("DELETE FROM bobtalk_locations WHERE lb_number = ? AND event_id = ?",
                 (int(lb_number), int(event_id)))
    rows = [(int(lb_number), int(event_id), m.quote_index, float(m.t_start),
             float(m.dice), float(m.runner_up), 1 if m.confident else 0, model)
            for m in matches]
    conn.executemany(
        """INSERT INTO bobtalk_locations
           (lb_number, event_id, quote_index, t_start, dice, runner_up, confident, model)
           VALUES (?,?,?,?,?,?,?,?)""", rows)
    conn.commit()
    return len(rows)


def ordered_tracks(disk_path: str) -> list[str]:
    """Return a folder's audio tracks in the locate pass's concatenation order.

    This MUST agree with ``tapematch.ingest.list_tracks``: a stored ``t_start``
    is an offset into that concatenation, so discovering or ordering tracks
    differently here would play the wrong moment. tapematch recurses into disc
    subfolders and sorts directory components first, then naturally within a
    filename — plain ``glob`` on the folder would miss ``d1/``-style layouts
    entirely.

    Args:
        disk_path: Absolute path to the LB folder.

    Returns:
        Absolute track paths in playback order.

    Raises:
        RuntimeError: If the tapematch ingest module cannot be imported.
    """
    import sys

    from backend import paths as _paths

    tm = str(_paths.APP_ROOT / "tools" / "tapematch")
    if tm not in sys.path:
        sys.path.insert(0, tm)
    try:
        from tapematch import ingest  # noqa: PLC0415 — optional, heavy
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(f"tapematch ingest unavailable: {exc}") from exc
    from pathlib import Path

    exts = {".flac", ".shn", ".wav", ".ape", ".m4a", ".aif", ".aiff", ".mp3"}
    return [str(p) for p in ingest.list_tracks(Path(disk_path), exts)]


def build_quote_clip(disk_path: str, t_start: float, dur_sec: int = 30,
                     lead_in: float = 3.0) -> str:
    """Extract a playable WAV clip at a located quote and return its filename.

    Reuses the A/B clip cache and ffmpeg helpers, but resolves tracks through
    :func:`ordered_tracks` so the offset means the same thing it did at locate
    time. No speed correction and no normalisation are applied: this is a
    "listen to what he said" clip, not a level-matched A/B comparison.

    Args:
        disk_path: Absolute path to the LB folder.
        t_start: Source-local start offset in seconds (from a location row).
        dur_sec: Clip length in seconds.
        lead_in: Seconds of head-room before *t_start*, so the clip does not
            open mid-syllable.

    Returns:
        The cache filename, servable via ``/api/ab_clip/<filename>``.

    Raises:
        ValueError: If the folder holds no audio, or the offset is past its end.
    """
    import os
    import shutil
    import tempfile

    from backend import ab_clips as _ab

    files = ordered_tracks(disk_path)
    if not files:
        raise ValueError("no audio tracks in folder")
    durations = [_ab._ffprobe_duration(f) for f in files]
    offset = max(0.0, float(t_start) - float(lead_in))
    segments = _ab.plan_extraction(durations, offset, float(dur_sec))
    if not segments:
        raise ValueError("requested position is beyond the recorded audio")

    out_name = _ab.cache_filename(0, offset, int(dur_sec)).replace("ab_0_", "bt_")
    out_path = _ab.AB_CLIPS_DIR / out_name
    _ab.AB_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        return out_name

    tmp_dir = tempfile.mkdtemp(prefix="bt_raw_")
    try:
        raw_path = os.path.join(tmp_dir, "raw.wav")
        _ab._extract_clip(files, segments, raw_path)
        shutil.move(raw_path, str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    _ab.prune_cache()
    return out_name


def get_locations(conn: sqlite3.Connection, lb_number: int,
                  confident_only: bool = True) -> list[dict]:
    """Return located bobtalk quotes for a recording, with their text.

    The text is joined back from ``olof_events.bobtalk`` at read time rather
    than stored, so this returns whatever Olof currently says.

    Args:
        conn: Open connection to the main database.
        lb_number: Recording to look up.
        confident_only: Drop matches that failed the separation gate. A
            low-confidence row means "do not offer a play button here".

    Returns:
        Dicts with ``quote_index``, ``text``, ``t_start``, ``dice``,
        ``runner_up``, ``confident`` and ``event_id``, ordered by timestamp.
    """
    ensure_schema(conn)
    sql = ("SELECT l.event_id, l.quote_index, l.t_start, l.dice, l.runner_up, "
           "l.confident, e.bobtalk FROM bobtalk_locations l "
           "JOIN olof_events e ON e.event_id = l.event_id WHERE l.lb_number = ?")
    if confident_only:
        sql += " AND l.confident = 1"
    sql += " ORDER BY l.t_start"
    out: list[dict] = []
    cache: dict[int, list[Quote]] = {}
    for eid, qidx, t, d, ru, conf, block in conn.execute(sql, (int(lb_number),)):
        quotes = cache.setdefault(eid, parse_bobtalk(block))
        if qidx >= len(quotes):
            # Olof's text changed under us; the index no longer resolves.
            log.warning("bobtalk quote %d missing for event %s (lb %s)", qidx, eid, lb_number)
            continue
        out.append({"event_id": eid, "quote_index": qidx, "text": quotes[qidx].text,
                    "t_start": t, "dice": d, "runner_up": ru, "confident": bool(conf)})
    return out
