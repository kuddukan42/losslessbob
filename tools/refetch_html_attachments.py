"""Re-fetch every mirrored ``/files/*.html`` attachment as verbatim bytes.

Until TODO-329 was fixed, ``site_crawler._save`` decided by extension alone, so
an uploader's DigiFlawFinder report or md5 listing was parsed by BeautifulSoup
and re-serialised on the way to ``data/site/files/``.  The mirrored copy is
therefore not the file the uploader attached — typically 5-8 % larger, and on
malformed input measurably *smaller*, because the parser dropped what it could
not understand.  A torrent seeded from the collection needs those bytes exact,
so ``seed_overlay`` cannot source a re-serialised sidecar and leaves it to the
swarm.

This pass repairs the mirror in place.  A row whose file already hashes to the
recorded ``body_sha256`` is skipped without a request, so only genuinely broken
copies cost network.  Saving goes through ``site_crawler._save`` rather than a
private copy of the logic, so the two can never drift.

Usage::

    .venv/bin/python3 tools/refetch_html_attachments.py --dry-run
    .venv/bin/python3 tools/refetch_html_attachments.py --limit 20
    .venv/bin/python3 tools/refetch_html_attachments.py --delay-ms 1000
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import requests  # noqa: E402

from backend import site_crawler as sc  # noqa: E402
from backend.db import upsert_inventory  # noqa: E402
from backend.db_queue import init_write_queue  # noqa: E402
from backend.paths import DB_PATH, SITE_DIR  # noqa: E402

logger = logging.getLogger("refetch_attachments")

SELECT_ROWS = """
SELECT url, relative_path, body_sha256
  FROM site_inventory
 WHERE url LIKE '%/files/%' AND url LIKE '%.html'
   AND relative_path IS NOT NULL
 ORDER BY url
"""


def _needs_refetch(rel_path: str, body_sha256: str | None) -> bool:
    """Return True when the mirrored file is not the raw body it was fetched from.

    Args:
        rel_path: Path under ``data/site/``.
        body_sha256: sha256 of the raw HTTP body recorded at fetch time.

    Returns:
        True when the file is absent, unhashed, or differs from the raw body.
    """
    if not body_sha256:
        return True
    path = Path(SITE_DIR) / rel_path
    if not path.exists():
        return True
    return hashlib.sha256(path.read_bytes()).hexdigest() != body_sha256


def main() -> int:
    """Repair every re-serialised ``.html`` attachment in the site mirror."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--delay-ms", type=int, default=1000,
                   help="Base delay between requests (default 1000).")
    p.add_argument("--limit", type=int, default=0, help="Stop after N re-fetches.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be re-fetched, send no requests.")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    init_write_queue(str(DB_PATH))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SELECT_ROWS).fetchall()
    todo = [r for r in rows if _needs_refetch(r["relative_path"], r["body_sha256"])]
    print(f"{len(rows)} .html attachment(s) mirrored, {len(todo)} need a verbatim re-fetch")
    if args.dry_run:
        for r in todo[:20]:
            print(f"  {r['relative_path']}")
        if len(todo) > 20:
            print(f"  … and {len(todo) - 20} more")
        return 0
    if args.limit:
        todo = todo[: args.limit]

    session = requests.Session()
    sc._load_robots(session)

    fixed = unchanged = failed = 0
    for i, row in enumerate(todo, 1):
        url = row["url"]
        if not sc._robots_allowed(url):
            logger.info("[%d/%d] robots disallow %s", i, len(todo), url)
            failed += 1
            continue
        status, body, new_lm = sc._fetch_page(session, url, None, args.delay_ms)
        if status != 200 or body is None:
            logger.warning("[%d/%d] HTTP %s — %s", i, len(todo), status, url)
            upsert_inventory(url, http_status=status,
                             last_checked_at="CURRENT_TIMESTAMP")
            failed += 1
            continue

        before = b""
        path = Path(SITE_DIR) / row["relative_path"]
        if path.exists():
            before = path.read_bytes()
        saved_path, local_sha = sc._save(url, body)
        raw_sha = hashlib.sha256(body).hexdigest()
        if local_sha != raw_sha:
            # _save must not rewrite an attachment; if it did, the fix regressed.
            logger.error("[%d/%d] NOT VERBATIM after save — %s", i, len(todo), url)
            failed += 1
            continue

        upsert_inventory(
            url,
            relative_path=str(saved_path.relative_to(SITE_DIR)),
            content_type="application/octet-stream",
            status="downloaded",
            last_fetched_at="CURRENT_TIMESTAMP",
            last_checked_at="CURRENT_TIMESTAMP",
            last_modified=new_lm,
            body_sha256=raw_sha,
            local_sha256=local_sha,
            size_bytes=len(body),
            http_status=status,
        )
        if before == body:
            unchanged += 1
        else:
            fixed += 1
            logger.info("[%d/%d] repaired %s (%d -> %d bytes)",
                        i, len(todo), row["relative_path"], len(before), len(body))

    print(f"\nrepaired={fixed}  already-correct-on-disk={unchanged}  failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
