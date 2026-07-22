#!/usr/bin/env python3
"""Report which docs/wiki/ pages are stale relative to their declared sources.

Each wiki page declares its inputs in a blockquote header::

    > Sources: `PROJECT.md` §Foo (~line 123) · `backend/dossier.py` ·
    > Status: fresh 2026-07-22

A page is *stale* when any of its source paths has a commit on a **later day**
than the page's Status date (same-day commits are ignored so a page refreshed
today is not flagged by that session's own bookkeeping). Section markers
(``§…``) and ``(~line N)`` annotations are ignored; only tokens that resolve to
real files or directories are checked.

Usage::

    .venv/bin/python3 tools/wiki_staleness.py [--verbose]

Prints one line per stale page (``<Page>  <n> commit(s) since <date>``) or a
single "current" line; always exits 0 (briefing hooks must never fail).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "docs" / "wiki"
_PATH_EXTS = (".md", ".py", ".mjs", ".sh", ".yml", ".yaml", ".json", ".html", ".ts", ".tsx")
_STATUS_RE = re.compile(r"Status:\s*\w+\s+(\d{4}-\d{2}-\d{2})")

logger = logging.getLogger("wiki_staleness")


def _parse_header(page: Path) -> tuple[dt.date | None, list[str]]:
    """Extract the Status date and existing source paths from a page header.

    Args:
        page: Wiki page file.

    Returns:
        ``(status_date, source_paths)`` — date is None when no Status line is
        found; paths are repo-relative strings that exist on disk.
    """
    header_lines: list[str] = []
    for line in page.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            header_lines.append(line.lstrip("> ").strip())
        elif header_lines:
            break
    header = " ".join(header_lines)

    m = _STATUS_RE.search(header)
    status_date = dt.date.fromisoformat(m.group(1)) if m else None

    paths: list[str] = []
    for token in re.split(r"[\s·]+", header):
        candidate = token.strip("`,()·").rstrip(".")
        if not candidate or candidate.startswith(("§", "~", "(", "/")):
            continue  # section markers, line annotations, and bare/absolute paths
        if "/" not in candidate and not candidate.endswith(_PATH_EXTS):
            continue
        if "*" in candidate:  # glob source, e.g. `backend/olof_*.py`
            for hit in sorted(REPO_ROOT.glob(candidate)):
                rel = hit.relative_to(REPO_ROOT).as_posix()
                if rel not in paths:
                    paths.append(rel)
        elif (REPO_ROOT / candidate).exists() and candidate not in paths:
            paths.append(candidate)
    return status_date, paths


def _commits_since(paths: list[str], since: dt.date) -> list[str]:
    """Return one-line commits touching *paths* strictly after *since* day."""
    threshold = since + dt.timedelta(days=1)
    out = subprocess.run(
        ["git", "log", "--oneline", f"--since={threshold.isoformat()} 00:00", "--", *paths],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Always returns 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true", help="list the newer source commits")
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    pages = sorted(p for p in WIKI_DIR.glob("*.md") if p.name != "Home.md")
    stale = 0
    for page in pages:
        try:
            status_date, paths = _parse_header(page)
            if status_date is None or not paths:
                logger.info("%s  no parseable Status/Sources header — check manually", page.stem)
                stale += 1
                continue
            commits = _commits_since(paths, status_date)
            if commits:
                stale += 1
                logger.info("%s  %d commit(s) since %s", page.stem, len(commits), status_date)
                if args.verbose:
                    for ln in commits[:5]:
                        logger.info("    %s", ln)
        except Exception as exc:  # briefing must never fail
            logger.info("%s  check failed (%s)", page.stem, exc)
    if stale == 0:
        logger.info("all %d wiki pages current", len(pages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
