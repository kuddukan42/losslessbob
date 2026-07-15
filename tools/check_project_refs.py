#!/usr/bin/env python3
"""Drift checker: PROJECT.md reference sections vs. the code on disk.

Extracts four kinds of "ground truth" straight from the source tree and checks
that each item is mentioned *somewhere* in ``PROJECT.md``:

    * Flask route paths   — ``@app.route(...)`` decorators in ``backend/app.py``
    * SQLite table names  — ``CREATE TABLE [IF NOT EXISTS] ...`` in ``backend/*.py``
    * gui_next screens    — component files in ``gui_next/src/renderer/src/screens/``
    * Backend modules     — ``*.py`` files directly under ``backend/``

This is a cheap, no-dependency substring/regex check — it does not verify that
the *documentation is correct*, only that PROJECT.md has not silently gone
stale by omitting something that exists in code (STRUCTURE_REVIEW.md P1,
TODO-244). Run after any PROJECT.md reference-section edit; it should exit 0.

Usage:
    .venv/bin/python3 tools/check_project_refs.py
    .venv/bin/python3 tools/check_project_refs.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("check_project_refs")

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_MD = REPO_ROOT / "PROJECT.md"
APP_PY = REPO_ROOT / "backend" / "app.py"
BACKEND_DIR = REPO_ROOT / "backend"
SCREENS_DIR = REPO_ROOT / "gui_next" / "src" / "renderer" / "src" / "screens"

# Backend modules that are never individually documented (package plumbing,
# not a feature module) — excluded from the check.
_MODULE_EXCLUDES = {"__init__.py"}

_ROUTE_RE = re.compile(r'@app\.route\(\s*"([^"]+)"(?:\s*,\s*methods=\[([^\]]*)\])?')
_TABLE_RE = re.compile(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)")
# PROJECT.md route mentions, e.g. `/api/foo/<lb>` or `/api/foo?q=`
_DOC_ROUTE_RE = re.compile(r"`(/[a-zA-Z0-9_/<>:.\-?=&]+)`")


def extract_routes() -> list[tuple[str, str]]:
    """Extract (method, path) pairs from every ``@app.route`` decorator.

    Returns:
        List of (HTTP method, raw Flask route path) tuples, one per method
        the route accepts (a route with two methods yields two entries).
    """
    src = APP_PY.read_text(encoding="utf-8")
    pairs: list[tuple[str, str]] = []
    for path, methods in _ROUTE_RE.findall(src):
        if methods:
            method_list = [m.strip().strip("\"'") for m in methods.split(",")]
        else:
            method_list = ["GET"]
        for method in method_list:
            pairs.append((method, path))
    return pairs


def extract_tables() -> list[str]:
    """Extract SQLite table names from every ``CREATE TABLE`` statement.

    Scans all ``backend/*.py`` files (schema DDL lives in ``db.py`` but this
    stays generic in case a future module defines its own tables). Tables
    ending in ``_new`` are excluded — the repo's migration convention is
    ``CREATE TABLE x_new (...) ... ALTER TABLE x_new RENAME TO x;``, so the
    ``_new`` name is a transient rename target, never a documented table in
    its own right (e.g. ``lb_master_new``, ``folder_lb_link_new``).

    Returns:
        Sorted list of unique table names, virtual tables included.
    """
    tables: set[str] = set()
    for py_file in BACKEND_DIR.glob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        tables.update(_TABLE_RE.findall(text))
    return sorted(name for name in tables if not name.endswith("_new"))


def extract_screens() -> list[str]:
    """Extract gui_next screen component names from the screens/ directory.

    Returns:
        Sorted list of screen names without the ``.tsx`` extension, e.g.
        ``ScreenHome``.
    """
    if not SCREENS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SCREENS_DIR.glob("Screen*.tsx"))


def extract_backend_modules() -> list[str]:
    """Extract backend module filenames directly under ``backend/``.

    Returns:
        Sorted list of ``*.py`` filenames (e.g. ``db.py``), excluding
        ``__init__.py``.
    """
    return sorted(
        p.name
        for p in BACKEND_DIR.glob("*.py")
        if p.name not in _MODULE_EXCLUDES
    )


def _normalise_route(path: str) -> str:
    """Collapse a Flask/doc route to a converter-agnostic, query-free form.

    Both ``<int:lb_number>`` (code) and ``<lb>`` (doc prose) collapse to the
    same ``<X>`` placeholder so cosmetic parameter-name differences don't
    register as drift.

    Args:
        path: A raw route path, with or without a trailing query string.

    Returns:
        The normalised path.
    """
    path = path.split("?", 1)[0]
    return re.sub(r"<(?:\w+:)?\w+>", "<X>", path)


def find_missing_routes(doc_text: str, routes: list[tuple[str, str]]) -> list[str]:
    """Find routes with no corresponding mention in PROJECT.md.

    Args:
        doc_text: Full text of PROJECT.md.
        routes: (method, path) pairs from ``extract_routes()``.

    Returns:
        Human-readable ``"METHOD /path"`` strings for each route not found.
    """
    doc_routes = {_normalise_route(p) for p in _DOC_ROUTE_RE.findall(doc_text)}
    missing = []
    for method, path in routes:
        if _normalise_route(path) not in doc_routes:
            missing.append(f"{method} {path}")
    return missing


def find_missing(doc_text: str, names: list[str]) -> list[str]:
    """Find plain-text names with no substring mention in PROJECT.md.

    Used for tables, screens, and backend modules — anything documented as a
    literal token (backticked or not) rather than a route path.

    Args:
        doc_text: Full text of PROJECT.md.
        names: Candidate names to look for.

    Returns:
        The subset of ``names`` not found anywhere in ``doc_text``.
    """
    return [name for name in names if name not in doc_text]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        0 if PROJECT.md references everything found on disk, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="check_project_refs.py",
        description="Check PROJECT.md reference sections against code on disk.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print counts even when clean."
    )
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    doc_text = PROJECT_MD.read_text(encoding="utf-8")

    routes = extract_routes()
    tables = extract_tables()
    screens = extract_screens()
    modules = extract_backend_modules()

    missing_routes = find_missing_routes(doc_text, routes)
    missing_tables = find_missing(doc_text, tables)
    missing_screens = find_missing(doc_text, screens)
    missing_modules = find_missing(doc_text, modules)

    for item in missing_routes:
        logger.info("MISSING route: %s", item)
    for item in missing_tables:
        logger.info("MISSING table: %s", item)
    for item in missing_screens:
        logger.info("MISSING screen: %s", item)
    for item in missing_modules:
        logger.info("MISSING backend module: %s", item)

    total_missing = (
        len(missing_routes)
        + len(missing_tables)
        + len(missing_screens)
        + len(missing_modules)
    )

    if args.verbose or total_missing:
        logger.info(
            "checked: %d routes, %d tables, %d screens, %d backend modules "
            "(%d missing)",
            len(routes),
            len(tables),
            len(screens),
            len(modules),
            total_missing,
        )

    return 1 if total_missing else 0


if __name__ == "__main__":
    sys.exit(main())
