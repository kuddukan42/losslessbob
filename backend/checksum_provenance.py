"""Cross-check LB-database checksums against the uploader-provided checksum files.

The LB database's ``checksums`` table is the reference every user lookup is scored
against.  Its values were transcribed from the site's ``lbdir`` manifests, and a
handful are wrong relative to their own provenance — mistyped, mis-sourced, or
carried over from a superseded version of a track.  When that happens a user whose
audio file is perfectly good gets a NOT FOUND, and there is nothing in the schema
to say the DB itself is at fault.

This module detects those cases by re-reading the attachment files already mirrored
under ``data/site/files/`` (``LBF-{lb:05d}-*``).  Roughly 34,500 of them are
uploader-supplied FFP/MD5/ST5 manifests, which are an independent witness to what
the fileset's checksums should be.  No network access and no collection-folder
crawling is involved.

Two failure modes have to be told apart, because only the first is a DB error:

``db_mismatch``
    A source file agrees with the DB on most of its rows and disagrees on one or
    two.  That is the signature of a corrupted individual DB value.

``set_divergence``
    A source file disagrees with the DB on most of its rows.  That is a different
    fileset or a different version of the recording filed under the same LB number
    (remasters reuse track filenames), not a DB error.

Findings are persisted to ``checksum_disputes`` so lookups can annotate a
NOT FOUND that is explained by a known-bad DB value, and so a human verdict
(``confirmed`` / ``dismissed``) survives re-running the audit.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

from backend.checksum_utils import parse_lbdir_file
from backend.paths import SITE_FILES_DIR

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checksum_disputes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number       INTEGER NOT NULL,
    filename        TEXT NOT NULL,   -- filename as stored in checksums.filename
    chk_type        TEXT NOT NULL,   -- m | f | s
    db_checksum     TEXT NOT NULL,   -- what the LB database holds
    source_checksum TEXT NOT NULL,   -- what the uploader's file holds
    source_file     TEXT NOT NULL,   -- LBF-* attachment basename
    source_kind     TEXT NOT NULL,   -- lbdir | uploader
    source_scope    TEXT NOT NULL,   -- self | xref
    source_suspect  INTEGER NOT NULL DEFAULT 0,  -- name marks it bad/old/superseded
    kind            TEXT NOT NULL,   -- db_mismatch | set_divergence
    confidence      TEXT NOT NULL,   -- high | medium | low
    rows_agree      INTEGER NOT NULL,
    rows_disagree   INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',  -- open | confirmed | dismissed
    note            TEXT,
    detected_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lb_number, filename, chk_type, source_checksum, source_file)
);
CREATE INDEX IF NOT EXISTS idx_disputes_lb ON checksum_disputes(lb_number);
CREATE INDEX IF NOT EXISTS idx_disputes_source_chk ON checksum_disputes(source_checksum);
CREATE INDEX IF NOT EXISTS idx_disputes_status ON checksum_disputes(status, confidence);
"""

# LBF-{lb}-{rest}: every mirrored attachment is named this way.
_ATTACHMENT_RE = re.compile(r"^LBF-(\d+)-(.*)$", re.IGNORECASE)
# LBF-{lb}-xref-{other}-...: a manifest for a *different* LB's identical fileset.
_XREF_RE = re.compile(r"^xref-(\d+)-", re.IGNORECASE)
# Filenames whose own words say the checksums inside are the discarded ones.
# The left boundary also accepts a digit, because the corpus glues the marker
# straight onto a date (``bd00-09-23bad.md5.txt``); requiring a separator there
# would miss it, while a bare word boundary would fire on "bold", "gold", …
_SUSPECT_RE = re.compile(
    r"(?:^|[-_. ]|(?<=\d))(bad|old|wrong|orig|original|prev|previous|before|broken"
    r"|corrupt|obsolete|superseded|unfixed|incorrect|error|errors)(?:[-_. ]|$)",
    re.IGNORECASE,
)
_AUDIO_EXT = (".flac", ".shn", ".wav", ".ape", ".wv", ".aif", ".aiff", ".m4a")

# An "isolated" disagreement — the DB-error signature. A source file must agree
# with the DB on at least MIN_AGREE rows (so it is demonstrably describing the
# same fileset) and disagree on no more than MAX_DISAGREE_RATIO of them.
MIN_AGREE = 3
MAX_DISAGREE_RATIO = 0.25

# Types as stored in checksums.chk_type, keyed by parse_lbdir_file section.
_SECTION_TO_TYPE = {"md5": "m", "ffp": "f", "shntool": "s"}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the ``checksum_disputes`` table and its indexes if absent.

    Args:
        conn: Open connection to the LosslessBob database.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def classify_source(attachment_name: str) -> dict | None:
    """Classify a mirrored attachment filename as a checksum-provenance source.

    Args:
        attachment_name: Basename of a file in ``data/site/files/``, e.g.
            ``LBF-15933-dylan-1974-01-14aft-rm-goody.ffp.txt``.

    Returns:
        A dict with ``lb_number``, ``kind`` (``lbdir``/``uploader``), ``scope``
        (``self``/``xref``), ``xref_lb`` (int or None) and ``suspect`` (bool), or
        None when the file cannot carry checksums (HTML pages, DFF reports) or the
        name is not an ``LBF-`` attachment at all.
    """
    m = _ATTACHMENT_RE.match(attachment_name)
    if not m:
        return None
    rest = m.group(2)
    low = rest.lower()
    if low.endswith((".html", ".htm")):
        return None
    if low.startswith("digiflawfinder"):
        # DigiFlawFinder reports describe WAVE defects, not checksums.
        return None

    xm = _XREF_RE.match(rest)
    if xm:
        scope, xref_lb = "xref", int(xm.group(1))
        kind = "lbdir" if "lbdir" in low else "uploader"
    else:
        scope, xref_lb = "self", None
        kind = "lbdir" if low.startswith("lbdir-") else "uploader"

    return {
        "lb_number": int(m.group(1)),
        "kind": kind,
        "scope": scope,
        "xref_lb": xref_lb,
        "suspect": bool(_SUSPECT_RE.search(rest)),
    }


def iter_source_rows(path: str | Path) -> Iterator[tuple[str, str, str]]:
    """Read one attachment and yield the checksums it asserts.

    Uses :func:`backend.checksum_utils.parse_lbdir_file`, which understands both
    the sectioned ``lbdir`` layout and the flat FFP/MD5 layout an uploader's own
    ``.ffp``/``.md5``/``.st5`` file uses.

    Args:
        path: Path to the attachment file.

    Yields:
        ``(basename, chk_type, checksum)`` triples, lower-cased, restricted to
        audio filenames.
    """
    parsed = parse_lbdir_file(path)
    for section, chk_type in _SECTION_TO_TYPE.items():
        for fname, checksum in parsed.get(section) or []:
            base = _basename(fname)
            if base.endswith(_AUDIO_EXT):
                yield base, chk_type, checksum.lower()


def _basename(filename: str) -> str:
    """Return the lower-cased basename of a possibly Windows-style path."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def _load_db_checksums(
    conn: sqlite3.Connection, lb_numbers: Sequence[int] | None = None
) -> dict[tuple[int, str, str], dict[str, str]]:
    """Load the DB's reference checksums keyed by (lb, basename, chk_type).

    Args:
        conn: Open database connection.
        lb_numbers: Restrict to these LB numbers, or None for the whole table.

    Returns:
        Mapping of key → {checksum: filename-as-stored}. A key can hold several
        checksums (xref variants, remasters filed under one LB), and a source
        value is only a mismatch when it matches none of them.
    """
    sql = "SELECT lb_number, filename, chk_type, checksum FROM checksums"
    params: tuple = ()
    if lb_numbers is not None:
        placeholders = ",".join("?" * len(lb_numbers))
        sql += f" WHERE lb_number IN ({placeholders})"
        params = tuple(lb_numbers)
    out: dict[tuple[int, str, str], dict[str, str]] = defaultdict(dict)
    for lb, fname, chk_type, checksum in conn.execute(sql, params):
        out[(lb, _basename(fname), chk_type)][checksum.lower()] = fname
    return out


def audit_attachment(
    path: str | Path,
    db_checksums: dict[tuple[int, str, str], dict[str, str]],
    source_info: dict | None = None,
) -> list[dict]:
    """Compare one attachment's checksums against the DB's reference values.

    Args:
        path: Path to the attachment file.
        db_checksums: Result of :func:`_load_db_checksums`.
        source_info: Pre-computed :func:`classify_source` result, or None to
            derive it from the filename.

    Returns:
        Dispute dicts ready for :func:`record_disputes`. Empty when the file is
        not a checksum source, asserts nothing comparable, or fully agrees.
    """
    path = Path(path)
    info = source_info or classify_source(path.name)
    if info is None:
        return []
    lb = info["lb_number"]

    agree = 0
    disagreements: list[tuple[str, str, str, str]] = []  # base, type, source, db
    for base, chk_type, checksum in iter_source_rows(path):
        known = db_checksums.get((lb, base, chk_type))
        if not known:
            # Filename the DB has no row for: a bonus track, an artwork-era
            # rename, or a fileset never ingested. Not evidence either way.
            continue
        if checksum in known:
            agree += 1
        else:
            db_checksum, db_filename = next(iter(known.items()))
            disagreements.append((db_filename, chk_type, checksum, db_checksum))

    if not disagreements:
        return []

    total = agree + len(disagreements)
    isolated = agree >= MIN_AGREE and (len(disagreements) / total) <= MAX_DISAGREE_RATIO
    if isolated:
        kind = "db_mismatch"
        confidence = "high" if (info["scope"] == "self" and not info["suspect"]) else "medium"
    else:
        kind = "set_divergence"
        confidence = "low"

    return [
        {
            "lb_number": lb,
            "filename": db_filename,
            "chk_type": chk_type,
            "db_checksum": db_checksum,
            "source_checksum": source_checksum,
            "source_file": path.name,
            "source_kind": info["kind"],
            "source_scope": info["scope"],
            "source_suspect": int(info["suspect"]),
            "kind": kind,
            "confidence": confidence,
            "rows_agree": agree,
            "rows_disagree": len(disagreements),
        }
        for db_filename, chk_type, source_checksum, db_checksum in disagreements
    ]


def record_disputes(conn: sqlite3.Connection, disputes: Iterable[dict]) -> int:
    """Upsert dispute rows, preserving any human verdict already recorded.

    Args:
        conn: Open database connection (schema already ensured).
        disputes: Dispute dicts from :func:`audit_attachment`.

    Returns:
        Number of rows written.
    """
    rows = list(disputes)
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO checksum_disputes (
            lb_number, filename, chk_type, db_checksum, source_checksum,
            source_file, source_kind, source_scope, source_suspect,
            kind, confidence, rows_agree, rows_disagree
        ) VALUES (
            :lb_number, :filename, :chk_type, :db_checksum, :source_checksum,
            :source_file, :source_kind, :source_scope, :source_suspect,
            :kind, :confidence, :rows_agree, :rows_disagree
        )
        ON CONFLICT(lb_number, filename, chk_type, source_checksum, source_file)
        DO UPDATE SET
            db_checksum   = excluded.db_checksum,
            kind          = excluded.kind,
            confidence    = excluded.confidence,
            rows_agree    = excluded.rows_agree,
            rows_disagree = excluded.rows_disagree
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def run_audit(
    conn: sqlite3.Connection,
    files_dir: str | Path | None = None,
    lb_numbers: Sequence[int] | None = None,
    include_lbdir: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Cross-check every mirrored attachment against the DB and store the findings.

    Args:
        conn: Open database connection.
        files_dir: Attachment mirror; defaults to ``data/site/files/``.
        lb_numbers: Restrict the pass to these LB numbers, or None for all.
        include_lbdir: Also re-check the ``lbdir`` manifests the DB was built
            from. Off by default — those are the DB's own source, so they test
            the ingest path rather than the provenance.
        progress: Optional callback ``(done, total)`` invoked every 500 files.

    Returns:
        Summary dict with counts by kind and confidence.
    """
    files_dir = Path(files_dir) if files_dir else SITE_FILES_DIR
    ensure_schema(conn)
    if not files_dir.exists():
        logger.warning("Attachment mirror not found: %s", files_dir)
        return {"files_scanned": 0, "disputes": 0}

    wanted = set(lb_numbers) if lb_numbers is not None else None
    db_checksums = _load_db_checksums(conn, lb_numbers)

    candidates = []
    for entry in sorted(files_dir.iterdir()):
        if not entry.is_file():
            continue
        info = classify_source(entry.name)
        if info is None:
            continue
        if wanted is not None and info["lb_number"] not in wanted:
            continue
        if info["kind"] == "lbdir" and not include_lbdir:
            continue
        candidates.append((entry, info))

    summary = {
        "files_scanned": 0,
        "files_with_disputes": 0,
        "disputes": 0,
        "db_mismatch": 0,
        "set_divergence": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "lb_numbers": set(),
    }
    total = len(candidates)
    batch: list[dict] = []
    for i, (entry, info) in enumerate(candidates, 1):
        summary["files_scanned"] += 1
        try:
            found = audit_attachment(entry, db_checksums, info)
        except Exception:  # a single malformed attachment must not stop the pass
            logger.exception("Failed to audit attachment %s", entry.name)
            continue
        if found:
            summary["files_with_disputes"] += 1
            for d in found:
                summary["disputes"] += 1
                summary[d["kind"]] += 1
                summary[d["confidence"]] += 1
                summary["lb_numbers"].add(d["lb_number"])
            batch.extend(found)
        if len(batch) >= 500:
            record_disputes(conn, batch)
            batch = []
        if progress and i % 500 == 0:
            progress(i, total)
    record_disputes(conn, batch)
    if progress:
        progress(total, total)

    summary["lb_numbers"] = len(summary["lb_numbers"])
    return summary


def get_disputes(
    conn: sqlite3.Connection,
    lb_number: int | None = None,
    status: str | None = "open",
    kind: str | None = "db_mismatch",
    confidence: Sequence[str] | None = ("high", "medium"),
) -> list[dict]:
    """Read stored disputes, filtered to the actionable ones by default.

    Args:
        conn: Open database connection.
        lb_number: Restrict to one LB entry, or None for all.
        status: Restrict to this status, or None for any.
        kind: Restrict to this kind, or None for any.
        confidence: Restrict to these confidence levels, or None for any.

    Returns:
        Dispute rows as dicts, ordered by LB number then filename.
    """
    ensure_schema(conn)
    where, params = [], []
    if lb_number is not None:
        where.append("lb_number = ?")
        params.append(lb_number)
    if status:
        where.append("status = ?")
        params.append(status)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if confidence:
        where.append(f"confidence IN ({','.join('?' * len(confidence))})")
        params.extend(confidence)
    sql = "SELECT * FROM checksum_disputes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY lb_number, filename, chk_type"
    return [dict(r) for r in conn.execute(sql, params)]


def set_dispute_status(
    conn: sqlite3.Connection, dispute_id: int, status: str, note: str | None = None
) -> bool:
    """Record a human verdict on a dispute.

    Args:
        conn: Open database connection.
        dispute_id: ``checksum_disputes.id``.
        status: ``open``, ``confirmed`` (the DB value is wrong) or ``dismissed``.
        note: Optional free-text rationale.

    Returns:
        True when a row was updated.

    Raises:
        ValueError: If ``status`` is not one of the three allowed values.
    """
    if status not in ("open", "confirmed", "dismissed"):
        raise ValueError(f"invalid dispute status: {status!r}")
    ensure_schema(conn)
    cur = conn.execute(
        "UPDATE checksum_disputes SET status=?, note=COALESCE(?, note) WHERE id=?",
        (status, note, dispute_id),
    )
    conn.commit()
    return cur.rowcount > 0


def lookup_disputed_checksums(
    conn: sqlite3.Connection, checksums: Sequence[str]
) -> dict[str, dict]:
    """Find user-supplied checksums that an uploader's file vouches for.

    This is the recovery path for the false mismatch: the user's audio file is
    fine, its checksum is exactly what the original uploader published, and only
    the DB's transcription of it is wrong — so the plain lookup returns NOT FOUND.

    Args:
        conn: Open database connection.
        checksums: Checksums that failed to match the ``checksums`` table.

    Returns:
        Mapping of checksum → dispute row (dict) for those explained by a
        known-bad DB value. Dismissed disputes and whole-set divergences are
        excluded; a ``confirmed`` dispute outranks an ``open`` one.
    """
    if not checksums:
        return {}
    try:
        ensure_schema(conn)
    except sqlite3.Error:
        return {}
    out: dict[str, dict] = {}
    lowered = [c.lower() for c in checksums]
    for i in range(0, len(lowered), 500):
        chunk = lowered[i:i + 500]
        rows = conn.execute(
            f"""
            SELECT * FROM checksum_disputes
            WHERE source_checksum IN ({','.join('?' * len(chunk))})
              AND kind = 'db_mismatch'
              AND status != 'dismissed'
              AND confidence IN ('high', 'medium')
            ORDER BY CASE status WHEN 'confirmed' THEN 0 ELSE 1 END,
                     CASE confidence WHEN 'high' THEN 0 ELSE 1 END
            """,
            chunk,
        ).fetchall()
        for row in rows:
            out.setdefault(row["source_checksum"], dict(row))
    return out
