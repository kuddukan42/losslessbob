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

Each source is judged against two independent references, which answer two
different questions:

``db``
    The ``checksums`` table.  "Is the value users are scored against wrong?"

``lbdir``
    The site's own ``lbdir-*`` manifest for that LB.  Jeff does not transcribe the
    uploader's checksums — he generates his own from the folder *after* he has
    downloaded it.  So this reference asks a question the DB cannot: **the uploader
    published one set of checksums; did Jeff actually receive the fileset exactly
    as the uploader intended?**  A disagreement here means the bytes that landed on
    Jeff's disk are not the bytes the uploader hashed — a truncated or corrupted
    transfer, a re-encode, or a different fileset altogether.  It is visible even
    for filesets the DB never ingested, and it is the upstream cause of a DB value
    that is "wrong" while faithfully recording what was received.

Within either reference, two shapes have to be told apart:

``isolated_mismatch``
    The source agrees with the reference on most of its rows and disagrees on one
    or two.  Against the DB that is the signature of a corrupted individual value;
    against the lbdir it is a single file that did not survive the transfer.

``set_divergence``
    The source disagrees on most of its rows.  That is a different fileset or a
    different version of the recording filed under the same LB number (remasters
    reuse track filenames), not a per-file fault.

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
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number          INTEGER NOT NULL,
    filename           TEXT NOT NULL,   -- filename as the reference records it
    chk_type           TEXT NOT NULL,   -- m | f | s
    reference_kind     TEXT NOT NULL,   -- db | lbdir  (what the source was compared against)
    reference_checksum TEXT NOT NULL,   -- what that reference holds
    reference_file     TEXT,            -- lbdir attachment name, NULL when reference_kind='db'
    source_checksum    TEXT NOT NULL,   -- what the uploader's file holds
    source_file        TEXT NOT NULL,   -- LBF-* attachment basename
    source_kind        TEXT NOT NULL,   -- lbdir | uploader
    source_scope       TEXT NOT NULL,   -- self | xref
    source_suspect     INTEGER NOT NULL DEFAULT 0,  -- name marks it bad/old/superseded
    displaced_to       TEXT,            -- reference filename holding the source's value, if any
    kind               TEXT NOT NULL,   -- isolated_mismatch | set_divergence
    confidence         TEXT NOT NULL,   -- high | medium | low
    rows_agree         INTEGER NOT NULL,
    rows_disagree      INTEGER NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open',  -- open | confirmed | dismissed
    note               TEXT,
    detected_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lb_number, filename, chk_type, source_checksum, source_file, reference_kind)
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

# An "isolated" disagreement — the per-file-fault signature. A source file must
# agree with the reference on at least MIN_AGREE rows (so it is demonstrably
# describing the same fileset) and disagree on no more than MAX_DISAGREE_RATIO.
MIN_AGREE = 3
MAX_DISAGREE_RATIO = 0.25

# Types as stored in checksums.chk_type, keyed by parse_lbdir_file section.
_SECTION_TO_TYPE = {"md5": "m", "ffp": "f", "shntool": "s"}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the ``checksum_disputes`` table and its indexes if absent.

    A pre-``reference_kind`` table (the shape shipped earlier the same day) is
    dropped rather than migrated: every row is derived data that ``run_audit()``
    regenerates from the attachment mirror in seconds.

    Args:
        conn: Open connection to the LosslessBob database.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(checksum_disputes)")]
    if cols and "reference_kind" not in cols:
        logger.info("checksum_disputes: pre-reference_kind shape found, rebuilding")
        conn.execute("DROP TABLE checksum_disputes")
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


class Reference:
    """The set of checksums a source file is judged against.

    Two references matter, and they answer different questions. The DB reference
    asks "is the value users are scored against wrong?". The lbdir reference holds
    the checksums Jeff generated from the folder he downloaded, so comparing an
    uploader's own manifest against it asks "did Jeff receive this fileset exactly
    as the uploader published it?" — an independent fault, and the upstream cause
    of a DB value that faithfully records a file that arrived damaged.

    Attributes:
        kind: ``db`` or ``lbdir``.
        by_file: (lb, basename, chk_type) → {checksum: filename as the reference
            records it}. A key holds several checksums when an LB legitimately
            carries more than one fileset, and a source value is a mismatch only
            when it matches none of them.
        by_checksum: (lb, chk_type) → {checksum: filename}, the inverse index —
            used to spot a value that is present but filed under another track.
        file_for: lb → the attachment the reference came from (lbdir only).
    """

    def __init__(self, kind: str):
        self.kind = kind
        self.by_file: dict[tuple[int, str, str], dict[str, str]] = defaultdict(dict)
        self.by_checksum: dict[tuple[int, str], dict[str, str]] = defaultdict(dict)
        self.file_for: dict[int, str] = {}

    def add(self, lb: int, filename: str, chk_type: str, checksum: str) -> None:
        """Index one reference checksum."""
        checksum = checksum.lower()
        self.by_file[(lb, _basename(filename), chk_type)][checksum] = filename
        self.by_checksum[(lb, chk_type)].setdefault(checksum, filename)


def load_db_reference(
    conn: sqlite3.Connection, lb_numbers: Sequence[int] | None = None
) -> Reference:
    """Build the reference from the ``checksums`` table.

    Args:
        conn: Open database connection.
        lb_numbers: Restrict to these LB numbers, or None for the whole table.

    Returns:
        A populated :class:`Reference` with ``kind='db'``.
    """
    sql = "SELECT lb_number, filename, chk_type, checksum FROM checksums"
    params: tuple = ()
    if lb_numbers is not None:
        placeholders = ",".join("?" * len(lb_numbers))
        sql += f" WHERE lb_number IN ({placeholders})"
        params = tuple(lb_numbers)
    ref = Reference("db")
    for lb, fname, chk_type, checksum in conn.execute(sql, params):
        ref.add(lb, fname, chk_type, checksum)
    return ref


def load_lbdir_reference(
    files_dir: str | Path | None = None, lb_numbers: Sequence[int] | None = None
) -> Reference:
    """Build the reference from the ``lbdir`` manifests in the attachment mirror.

    Args:
        files_dir: Attachment mirror; defaults to ``data/site/files/``.
        lb_numbers: Restrict to these LB numbers, or None for all.

    Returns:
        A populated :class:`Reference` with ``kind='lbdir'``.
    """
    files_dir = Path(files_dir) if files_dir else SITE_FILES_DIR
    ref = Reference("lbdir")
    if not files_dir.exists():
        return ref
    wanted = set(lb_numbers) if lb_numbers is not None else None
    for entry in sorted(files_dir.iterdir()):
        if not entry.is_file():
            continue
        info = classify_source(entry.name)
        # Only an LB's own lbdir speaks for it; an xref manifest describes a
        # different entry's fileset and would poison the reference.
        if info is None or info["kind"] != "lbdir" or info["scope"] != "self":
            continue
        if wanted is not None and info["lb_number"] not in wanted:
            continue
        lb = info["lb_number"]
        try:
            rows = list(iter_source_rows(entry))
        except Exception:
            logger.exception("Failed to read lbdir manifest %s", entry.name)
            continue
        if rows:
            ref.file_for.setdefault(lb, entry.name)
        for base, chk_type, checksum in rows:
            ref.add(lb, base, chk_type, checksum)
    return ref


def classify_collection_source(path: str | Path, lb_number: int) -> dict | None:
    """Classify a checksum sidecar sitting in one of the user's collection folders.

    These matter because the attachment mirror is not complete evidence: an entry
    may have only an ``.ffp`` attached while the ``.md5`` the uploader shipped
    inside the torrent exists nowhere on the site. LB-15933 is exactly that shape —
    its uploader MD5 lives only in the collection folder, so a mirror-only audit
    could never see the disagreement that was reported against it.

    Files the app itself wrote (``*_mychecksums_*``) are excluded: they are hashes
    of the user's own copy, not a statement of what the uploader published. So are
    ``lbdir*.txt`` copies, which are Jeff's manifest and already the lbdir
    reference.

    Args:
        path: Path to a file inside a collection folder.
        lb_number: LB the folder is confirmed to hold.

    Returns:
        A :func:`classify_source`-shaped dict with ``kind='uploader'`` and
        ``origin='collection'``, or None when the file is not uploader evidence.
    """
    name = Path(path).name
    low = name.lower()
    if not low.endswith((".ffp", ".md5", ".st5")):
        return None
    if "_mychecksums_" in low or "lbdir" in low:
        return None
    return {
        "lb_number": lb_number,
        "kind": "uploader",
        "scope": "self",
        "xref_lb": None,
        "suspect": bool(_SUSPECT_RE.search(name)),
        "origin": "collection",
    }


def iter_collection_sources(
    conn: sqlite3.Connection, lb_numbers: Sequence[int] | None = None
) -> Iterator[tuple[Path, dict]]:
    """Yield uploader checksum sidecars found in the user's collection folders.

    Args:
        conn: Open database connection (reads ``my_collection``).
        lb_numbers: Restrict to these LB numbers, or None for all.

    Yields:
        ``(path, info)`` pairs ready for :func:`audit_attachment`. Folders that
        have gone missing (unmounted drive, moved directory) are skipped quietly —
        an offline drive must not look like an absence of evidence.
    """
    sql = "SELECT lb_number, disk_path FROM my_collection WHERE disk_path IS NOT NULL"
    params: tuple = ()
    if lb_numbers is not None:
        if not lb_numbers:
            return
        sql += f" AND lb_number IN ({','.join('?' * len(lb_numbers))})"
        params = tuple(lb_numbers)
    for lb, disk_path in conn.execute(sql, params).fetchall():
        folder = Path(disk_path)
        try:
            if not folder.is_dir():
                continue
            entries = sorted(folder.iterdir())
        except OSError:
            logger.debug("Collection folder unreadable, skipped: %s", disk_path)
            continue
        for entry in entries:
            info = classify_collection_source(entry, lb)
            if info is not None and entry.is_file():
                yield entry, info


def audit_attachment(
    path: str | Path,
    reference: Reference,
    source_info: dict | None = None,
) -> list[dict]:
    """Compare one attachment's checksums against a reference.

    Args:
        path: Path to the attachment file.
        reference: Result of :func:`load_db_reference` or
            :func:`load_lbdir_reference`.
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
    if reference.kind == "lbdir" and info["kind"] == "lbdir":
        # Comparing the lbdir against itself proves nothing.
        return []

    agree = 0
    disagreements: list[tuple[str, str, str, str]] = []  # ref name, type, source, ref
    for base, chk_type, checksum in iter_source_rows(path):
        known = reference.by_file.get((lb, base, chk_type))
        if not known:
            # A filename the reference has no row for: a bonus track, a rename,
            # or a fileset never ingested. Not evidence either way.
            continue
        if checksum in known:
            agree += 1
        else:
            ref_checksum, ref_filename = next(iter(known.items()))
            disagreements.append((ref_filename, chk_type, checksum, ref_checksum))

    if not disagreements:
        return []

    total = agree + len(disagreements)
    isolated = agree >= MIN_AGREE and (len(disagreements) / total) <= MAX_DISAGREE_RATIO
    if isolated:
        kind = "isolated_mismatch"
        confidence = "high" if (info["scope"] == "self" and not info["suspect"]) else "medium"
    else:
        kind = "set_divergence"
        confidence = "low"

    out = []
    for ref_filename, chk_type, source_checksum, ref_checksum in disagreements:
        # The source's value is present in the reference, but under a different
        # track name: the same audio arrived intact and only the naming differs
        # (track renumbering, a differently-ordered rip). Worth flagging, but it
        # is not a damaged or missing file.
        displaced_to = reference.by_checksum.get((lb, chk_type), {}).get(source_checksum)
        out.append({
            "lb_number": lb,
            "filename": ref_filename,
            "chk_type": chk_type,
            "reference_kind": reference.kind,
            "reference_checksum": ref_checksum,
            "reference_file": reference.file_for.get(lb),
            "source_checksum": source_checksum,
            "source_file": path.name,
            # 'collection' marks evidence that came from the user's own folder
            # rather than the site mirror — same uploader authority, different
            # provenance, and worth being able to filter on.
            "source_kind": ("collection" if info.get("origin") == "collection"
                            else info["kind"]),
            "source_scope": info["scope"],
            "source_suspect": int(info["suspect"]),
            "displaced_to": displaced_to,
            "kind": kind,
            "confidence": confidence,
            "rows_agree": agree,
            "rows_disagree": len(disagreements),
        })
    return out


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
            lb_number, filename, chk_type, reference_kind, reference_checksum,
            reference_file, source_checksum, source_file, source_kind,
            source_scope, source_suspect, displaced_to,
            kind, confidence, rows_agree, rows_disagree
        ) VALUES (
            :lb_number, :filename, :chk_type, :reference_kind, :reference_checksum,
            :reference_file, :source_checksum, :source_file, :source_kind,
            :source_scope, :source_suspect, :displaced_to,
            :kind, :confidence, :rows_agree, :rows_disagree
        )
        ON CONFLICT(lb_number, filename, chk_type, source_checksum, source_file,
                    reference_kind)
        DO UPDATE SET
            reference_checksum = excluded.reference_checksum,
            reference_file     = excluded.reference_file,
            displaced_to       = excluded.displaced_to,
            kind               = excluded.kind,
            confidence         = excluded.confidence,
            rows_agree         = excluded.rows_agree,
            rows_disagree      = excluded.rows_disagree
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
    lbdir_reference: bool = True,
    include_collection: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Cross-check every mirrored attachment against both references, and store it.

    Each source attachment is judged twice: against the ``checksums`` table (did
    the DB record the right value?) and against the LB's own ``lbdir`` manifest
    (did Jeff receive the fileset the uploader published?). The two are recorded
    as separate rows, distinguished by ``reference_kind``.

    Args:
        conn: Open database connection.
        files_dir: Attachment mirror; defaults to ``data/site/files/``.
        lb_numbers: Restrict the pass to these LB numbers, or None for all.
        include_lbdir: Also use the ``lbdir`` manifests as *sources*. Off by
            default — against the DB they test the ingest path rather than the
            provenance, and against themselves they prove nothing.
        lbdir_reference: Build and check the lbdir reference. On by default;
            turning it off makes the pass DB-only (and skips parsing every
            ``lbdir-*`` manifest).
        include_collection: Also read the uploader sidecars sitting in the user's
            own collection folders (:func:`iter_collection_sources`). Off by
            default because it walks every folder in ``my_collection`` and is
            disk-bound, but it is the only way to see checksums the uploader
            shipped inside a torrent and never attached to the site.
        progress: Optional callback ``(done, total)`` invoked every 500 files.

    Returns:
        Summary dict with counts by kind, confidence and reference.
    """
    files_dir = Path(files_dir) if files_dir else SITE_FILES_DIR
    ensure_schema(conn)
    if not files_dir.exists():
        logger.warning("Attachment mirror not found: %s", files_dir)
        return {"files_scanned": 0, "disputes": 0}

    wanted = set(lb_numbers) if lb_numbers is not None else None
    references = [load_db_reference(conn, lb_numbers)]
    if lbdir_reference:
        references.append(load_lbdir_reference(files_dir, lb_numbers))

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

    if include_collection:
        collection = list(iter_collection_sources(conn, lb_numbers))
        logger.info("Collection sidecars found: %d", len(collection))
        candidates.extend(collection)

    summary = {
        "files_scanned": 0,
        "files_with_disputes": 0,
        "disputes": 0,
        "isolated_mismatch": 0,
        "set_divergence": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "ref_db": 0,
        "ref_lbdir": 0,
        "src_collection": 0,
        "lb_numbers": set(),
    }
    total = len(candidates)
    batch: list[dict] = []
    for i, (entry, info) in enumerate(candidates, 1):
        summary["files_scanned"] += 1
        found: list[dict] = []
        for reference in references:
            try:
                found.extend(audit_attachment(entry, reference, info))
            except Exception:  # one malformed attachment must not stop the pass
                logger.exception("Failed to audit attachment %s", entry.name)
        if found:
            summary["files_with_disputes"] += 1
            for d in found:
                summary["disputes"] += 1
                summary[d["kind"]] += 1
                summary[d["confidence"]] += 1
                summary["ref_" + d["reference_kind"]] += 1
                if d["source_kind"] == "collection":
                    summary["src_collection"] += 1
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
    kind: str | None = "isolated_mismatch",
    confidence: Sequence[str] | None = ("high", "medium"),
    reference_kind: str | None = None,
) -> list[dict]:
    """Read stored disputes, filtered to the actionable ones by default.

    Args:
        conn: Open database connection.
        lb_number: Restrict to one LB entry, or None for all.
        status: Restrict to this status, or None for any.
        kind: Restrict to this kind, or None for any.
        confidence: Restrict to these confidence levels, or None for any.
        reference_kind: Restrict to ``db`` or ``lbdir``, or None for both.

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
    if reference_kind:
        where.append("reference_kind = ?")
        params.append(reference_kind)
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
        status: ``open``, ``confirmed`` (the reference value is at fault) or
            ``dismissed``.
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
    fine — its checksum is exactly what the original uploader published — and the
    DB holds a different value, so the plain lookup returns NOT FOUND. Only
    ``reference_kind='db'`` rows can explain that, since the DB is what the lookup
    scored against; an lbdir dispute is a finding about the site's copy, not about
    the user's file.

    Args:
        conn: Open database connection.
        checksums: Checksums that failed to match the ``checksums`` table.

    Returns:
        Mapping of checksum → dispute row (dict) for those the uploader vouches
        for. Dismissed disputes and whole-set divergences are excluded; a
        ``confirmed`` dispute outranks an ``open`` one.
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
              AND kind = 'isolated_mismatch'
              AND reference_kind = 'db'
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
