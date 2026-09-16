#!/usr/bin/env python3
"""Show-dossier golden set (plan row C31, audit Q3): loader, snapshot, fidelity check.

Each ``tests/golden/dossier/*.json`` spec names one show and carries
``expected`` -- the normalized dossier snapshot tj verified by hand (C32), or
``null`` while the file is a placeholder. ``tests/test_dossier_golden.py``
builds every spec against the committed fixture (``fixture.jsonl.gz``, cut by
``tools/make_fixture_db.py --golden``) and fails on any diff.

Usage::

    .venv/bin/python3 tools/dossier_golden.py --check        # fixture == live, per spec
    .venv/bin/python3 tools/dossier_golden.py --show 2010-03-29_spec-sample
    .venv/bin/python3 tools/dossier_golden.py --html ~/Documents/projects/losslessbob_dossiers

``--check`` must pass before a re-cut fixture is committed: a snapshot that
differs between the live DB and the fixture means the cut dropped a row the
dossier reads.
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.make_fixture_db import GOLDEN_DIR, GOLDEN_FIXTURE  # noqa: E402

_log = logging.getLogger(__name__)

# Keys whose value changes on every build or every recompute, stripped at any depth.
_VOLATILE_KEYS = frozenset({"generated_at", "computed_at", "input_fingerprint"})
_QC_KEYS = ("passed", "refused", "withheld", "reasons", "notices")
_MARKER_RE = re.compile(r'data-marker="([^"]+)"')


def golden_specs(golden_dir: Path = GOLDEN_DIR) -> list[tuple[Path, dict]]:
    """Return every golden spec, sorted by filename.

    Args:
        golden_dir: Folder holding the ``*.json`` specs.

    Returns:
        ``(path, spec)`` pairs.
    """
    return [(p, json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(golden_dir.glob("*.json"))]


def load_fixture(db_path: str, fixture: Path = GOLDEN_FIXTURE) -> dict[str, int]:
    """Create a fresh install at *db_path* and load the golden fixture into it.

    Columns the schema gained since the cut simply stay NULL; a fixture column
    the schema lacks raises, since dropping it would silently blank what the
    dossier reads (``abs_grade`` lives in the ranker's own migration).

    Args:
        db_path: Path of the database to create.
        fixture: The ``.jsonl.gz`` cut.

    Returns:
        Row count per table.

    Raises:
        ValueError: A fixture table or column is missing from the schema.
    """
    from backend import db
    from concert_ranker.lb import repo as cr_repo

    db.init_db(db_path)
    conn = sqlite3.connect(db_path)
    cr_repo.ensure_schema(conn)
    columns: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    with gzip.open(fixture, "rt", encoding="utf-8") as fh:
        for line in fh:
            table, row = json.loads(line)
            if table not in columns:
                columns[table] = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            keys = list(row)
            unknown = set(keys) - columns[table]
            if unknown:
                raise ValueError(f"fixture {table} has columns the schema lacks: {sorted(unknown)}")
            conn.execute(
                f'INSERT OR REPLACE INTO "{table}" ({",".join(keys)}) '
                f'VALUES ({",".join("?" * len(keys))})',
                [row[k] for k in keys],
            )
            counts[table] = counts.get(table, 0) + 1
    conn.commit()
    conn.close()
    return counts


def _strip_volatile(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def snapshot(dossier: dict) -> dict:
    """Reduce a dossier payload to the values a golden file pins.

    Kept: every anchor's value/confidence/source, the view rows and claims,
    the map marker kind, and the gate outcome. Dropped: timestamps, the gate
    fingerprint and the map SVG body (geometry is covered by test_dossier_map).

    Args:
        dossier: A :func:`backend.dossier.build_dossier` result.

    Returns:
        A JSON-safe dict.
    """
    if dossier.get("ambiguous"):
        return {"ambiguous": True, "candidates": dossier.get("candidates")}
    view = dossier.get("view") or {}
    marker = _MARKER_RE.search(view.get("map_svg") or "")
    qc = dossier.get("qc") or {}
    out = {
        "fields": {
            key: {"value": f.get("value"), "confidence": f.get("confidence"),
                  "source": f.get("source")}
            for key, f in sorted((view.get("fields") or {}).items())
        },
        "rows": view.get("rows"),
        "claims": view.get("claims"),
        "map_marker": marker.group(1) if marker else None,
        "qc": {k: qc.get(k) for k in _QC_KEYS},
    }
    return _strip_volatile(json.loads(json.dumps(out, default=str)))


def build_snapshot(spec: dict, db_path: str | None = None) -> dict:
    """Build one spec's dossier and return its :func:`snapshot`.

    Args:
        spec: A golden spec (``date``, ``location``, ``channel``).
        db_path: Database to build against (default: the configured DB).

    Returns:
        The normalized snapshot.
    """
    from backend.dossier import build_dossier

    return snapshot(build_dossier(
        spec["date"], location=spec.get("location"),
        channel=spec.get("channel") or "public", db_path=db_path,
    ))


def first_diffs(expected: object, actual: object, path: str = "", limit: int = 20) -> list[str]:
    """List up to *limit* JSON paths where two snapshots differ.

    Args:
        expected: Golden value.
        actual: Freshly built value.
        path: Path prefix (recursion).
        limit: Maximum lines returned.

    Returns:
        ``"<path>: <expected> != <actual>"`` lines, empty when equal.
    """
    out: list[str] = []

    def walk(a: object, b: object, p: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b), key=str):
                walk(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{p}.{k}")
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                walk(x, y, f"{p}[{i}]")
        elif a != b:
            out.append(f"{p or '.'}: {json.dumps(a, default=str)[:120]} != "
                       f"{json.dumps(b, default=str)[:120]}")

    walk(expected, actual, path)
    return out


def _snapshots_json(db_path: str | None) -> dict[str, dict]:
    from backend import db, paths

    if db_path:
        db.DB_PATH = Path(db_path)
        paths.DATA_DIR = Path(db_path).parent
    db.reload_taper_aliases(db_path)
    return {p.stem: build_snapshot(spec, db_path) for p, spec in golden_specs()}


def _child_snapshots(db_path: str | None) -> dict[str, dict]:
    # One process per DB: taper aliases and connection caches are module-global.
    cmd = [sys.executable, __file__, "--snapshots"] + ([db_path] if db_path else ["-"])
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=_PROJECT_ROOT, check=True)
    return json.loads(res.stdout)


def check() -> int:
    """Compare every spec's snapshot built from the live DB and from the fixture.

    Returns:
        Process exit code: 0 when all specs match.
    """
    with tempfile.TemporaryDirectory(prefix="lb_golden_") as tmp:
        fixture_db = str(Path(tmp) / "golden.db")
        load_fixture(fixture_db)
        live = _child_snapshots(None)
        cut = _child_snapshots(fixture_db)
    failed = 0
    for name in sorted(live):
        diffs = first_diffs(live[name], cut.get(name), limit=8)
        failed += bool(diffs)
        sys.stdout.write(f"{'FAIL' if diffs else 'PASS'} {name}\n")
        for line in diffs:
            sys.stdout.write(f"    {line}\n")
    sys.stdout.write(f"{len(live) - failed}/{len(live)} specs match live\n")
    return 1 if failed else 0


def export_html(out_dir: Path) -> int:
    """Render every spec's dossier HTML from the live DB into *out_dir*, plus an index.

    Goes through ``/api/dossier/html`` on a Flask test client, so the pages are
    exactly what the app exports. Feeds the LAN report server (reportserver).

    Args:
        out_dir: Destination folder, created if missing.

    Returns:
        Process exit code: 0 when every spec rendered.
    """
    from html import escape
    from urllib.parse import urlencode

    from backend.app import create_app

    out_dir.mkdir(parents=True, exist_ok=True)
    client = create_app().test_client()
    rows, failed = [], 0
    for path, spec in golden_specs():
        q = {"date": spec["date"], "channel": spec.get("channel") or "public", "inline": "1"}
        if spec.get("location"):
            q["location"] = spec["location"]
        res = client.get(f"/api/dossier/html?{urlencode(q)}")
        name = f"{path.stem}.html"
        if res.status_code == 200:
            (out_dir / name).write_bytes(res.data)
            link = f'<a href="{escape(name)}">{escape(path.stem)}</a>'
        else:
            failed += 1
            link = f"{escape(path.stem)} — HTTP {res.status_code}"
        state = "verified" if spec.get("expected") is not None else "unverified"
        rows.append(f"<li>{link} <small>{escape(spec.get('note') or '')} · {state}</small></li>")
        sys.stdout.write(f"{res.status_code} {path.stem}\n")
    (out_dir / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Golden dossiers</title>'
        '<style>body{font:16px system-ui;margin:16px;color-scheme:light dark}'
        'li{margin:.5em 0}small{opacity:.7}</style>'
        f"<h1>Golden dossiers</h1><ul>{''.join(rows)}</ul>", encoding="utf-8")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true", help="fixture vs live, per spec")
    grp.add_argument("--show", metavar="NAME", help="print one spec's snapshot from the fixture")
    grp.add_argument("--html", metavar="DIR", type=Path,
                     help="render every spec's HTML from the live DB into DIR")
    grp.add_argument("--snapshots", metavar="DB", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.check:
        return check()
    if args.html:
        return export_html(args.html.expanduser())
    if args.snapshots:
        logging.disable(logging.CRITICAL)  # stdout carries the JSON
        json.dump(_snapshots_json(None if args.snapshots == "-" else args.snapshots),
                  sys.stdout)
        return 0
    with tempfile.TemporaryDirectory(prefix="lb_golden_") as tmp:
        fixture_db = str(Path(tmp) / "golden.db")
        load_fixture(fixture_db)
        snaps = _child_snapshots(fixture_db)
    if args.show not in snaps:
        sys.stderr.write(f"no spec named {args.show}\n")
        return 2
    json.dump(snaps[args.show], sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
