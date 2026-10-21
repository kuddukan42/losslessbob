"""dylan_performances import + date lookup (from backend.db, TODO-369 S2)."""

import logging

from backend.db import get_connection
from backend.db_queue import get_write_queue

logger = logging.getLogger(__name__)


def import_dylan_performances(db_path=None) -> int:
    """One-time import of the Dylan performance ODS into dylan_performances.

    Skips silently if the table already has rows. Searches DATA_DIR for a file
    matching ``*Dylan_Performance_fixed.ods`` and parses it using stdlib only
    (zipfile + xml.etree.ElementTree). Returns the number of rows inserted.
    """
    import xml.etree.ElementTree as ET
    import zipfile as _zf

    from backend.paths import DATA_DIR as _DATA

    conn = get_connection(db_path)
    if conn.execute("SELECT COUNT(*) FROM dylan_performances").fetchone()[0] > 0:
        return 0  # already imported

    candidates = sorted(_DATA.glob("*Dylan_Performance_fixed.ods"))
    if not candidates:
        logger.warning("dylan_performances: ODS file not found in %s", _DATA)
        return 0
    ods_path = candidates[-1]  # take the most recent if multiple

    NS = {
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text":  "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }

    try:
        with _zf.ZipFile(ods_path) as z:
            root = ET.fromstring(z.read("content.xml"))
    except Exception as exc:
        logger.error("dylan_performances: failed to read ODS: %s", exc)
        return 0

    sheet = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table")
    if sheet is None:
        logger.error("dylan_performances: no table element found in ODS")
        return 0

    rows = sheet.findall("table:table-row", NS)
    if not rows:
        return 0

    def _cell_text(cell) -> str:
        p = cell.find("text:p", NS)
        return (p.text or "").strip() if p is not None else ""

    records = []
    for row in rows[1:]:  # skip header
        cells = row.findall("table:table-cell", NS)
        if len(cells) < 7:
            cells = cells + [None] * (7 - len(cells))
        vals = [_cell_text(c) if c is not None else "" for c in cells[:7]]
        date_str, event_id, category, city, state, country, venue = vals
        if not event_id:
            continue
        records.append((event_id, date_str, category, city, state, country, venue))

    if not records:
        return 0

    _records = records
    get_write_queue().execute(
        lambda c: c.executemany(
            """INSERT OR IGNORE INTO dylan_performances
               (event_id, date_str, category, city, state, country, venue)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            _records,
        )
    )
    logger.info("dylan_performances: imported %d rows from %s", len(records), ods_path.name)
    return len(records)


def get_performance_by_date(date_str: str, db_path=None) -> dict | None:
    """Return the dylan_performances row for an ISO date string (YYYY-MM-DD), or None.

    When two performances share the same date (rare), returns the first and logs a
    warning so callers can decide whether to surface an ambiguity flag.

    Args:
        date_str: ISO date string, e.g. ``'1978-11-16'``.  Must already be in
                  YYYY-MM-DD format; use ``_entry_date_to_iso()`` in geocoder.py
                  to convert entries.date_str values first.
        db_path:  Optional path override; defaults to :data:`DB_PATH`.

    Returns:
        Dict with keys ``event_id``, ``date_str``, ``category``, ``city``,
        ``state``, ``country``, ``venue``; or ``None`` if no match.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT event_id, date_str, category, city, state, country, venue "
        "FROM dylan_performances WHERE date_str = ?",
        (date_str,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "get_performance_by_date: %d performances on %s — returning first",
            len(rows), date_str,
        )
    return dict(rows[0])
