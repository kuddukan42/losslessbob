#!/usr/bin/env python3
"""Dossier export drift check (plan row C33, Phase 8 "Export re-check").

An exported ``dossier-<date>.html`` (from ``/api/dossier/html``) carries two
embedded JSON blocks: ``#lb-qc`` (the QC gate outcome at export time) and
``#lb-dossier-id`` (the identity it was built with -- date/location/show/
channel, added alongside it, C33). This tool rebuilds the dossier from that
identity against the *current* DB and reports whether the QC picture has
drifted since the file was exported -- useful for a file someone's been
sitting on, or a page pulled off a forum months later.

Usage::

    .venv/bin/python3 tools/dossier_verify_export.py dossier-2010-03-29.html
    .venv/bin/python3 tools/dossier_verify_export.py exports/*.html

Exit code: 0 all OK, 1 any DRIFT, 2 any ERROR (unidentifiable file or a
rebuild that itself raised).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_log = logging.getLogger(__name__)

_QC_RE = re.compile(
    r'<script type="application/json" id="lb-qc">(.*?)</script>', re.DOTALL)
_ID_RE = re.compile(
    r'<script type="application/json" id="lb-dossier-id">(.*?)</script>', re.DOTALL)
_DATE_STEM_RE = re.compile(r'(?:^|-)(\d{4}-\d{2}-\d{2})(?:$|-)')

_COMPARE_KEYS = ("input_fingerprint", "refused", "reasons", "notices")


def parse_export(html: str, filename: str) -> tuple[dict | None, dict | None, str | None]:
    """Extract the embedded QC snapshot and identity from an exported file.

    Args:
        html: The file's text content.
        filename: Its name, used for the identity fallback.

    Returns:
        ``(qc, identity, error)`` -- ``error`` is set (and the other two None)
        when the file carries neither ``#lb-dossier-id`` nor a date-bearing
        filename stem, i.e. it can't be identified at all.
    """
    qc_m = _QC_RE.search(html)
    qc = json.loads(qc_m.group(1)) if qc_m else None

    id_m = _ID_RE.search(html)
    if id_m:
        identity = json.loads(id_m.group(1))
        return qc, identity, None

    stem_m = _DATE_STEM_RE.search(Path(filename).stem)
    if stem_m:
        return qc, {"date_iso": stem_m.group(1), "location": None, "show": None,
                    "channel": "public"}, None

    return None, None, "unidentifiable (no lb-dossier-id block and no date in filename)"


def _withheld_set(qc: dict | None) -> set[tuple[str, str, object]]:
    return {(w.get("key"), w.get("rule"), w.get("lb")) for w in (qc or {}).get("withheld") or []}


def verify_file(path: Path) -> tuple[str, list[str]]:
    """Verify one exported file against the current DB.

    Args:
        path: The exported HTML file.

    Returns:
        ``(status, details)`` -- status is ``OK``/``DRIFT``/``ERROR``; details
        is empty on OK, a list of "part differs" notes on DRIFT, or a
        one-item list with the error message on ERROR.
    """
    try:
        html = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "ERROR", [f"could not read file: {exc}"]

    exported_qc, identity, err = parse_export(html, path.name)
    if err:
        return "ERROR", [err]

    from backend.dossier import build_dossier

    try:
        rebuilt = build_dossier(
            identity["date_iso"], location=identity.get("location"),
            channel=identity.get("channel") or "public", show=identity.get("show"),
        )
    except Exception as exc:  # noqa: BLE001 - reported as ERROR, not raised
        _log.exception("rebuild failed for %s", path)
        return "ERROR", [f"rebuild raised: {exc}"]

    if rebuilt.get("ambiguous"):
        return "ERROR", ["rebuilt dossier is ambiguous from this identity "
                         "(date/location/show no longer resolve to one show)"]

    rebuilt_qc = rebuilt.get("qc") or {}
    diffs: list[str] = []
    for key in _COMPARE_KEYS:
        old, new = (exported_qc or {}).get(key), rebuilt_qc.get(key)
        if old != new:
            diffs.append(f"{key}: {old!r} != {new!r}")

    old_withheld, new_withheld = _withheld_set(exported_qc), _withheld_set(rebuilt_qc)
    if old_withheld != new_withheld:
        added = new_withheld - old_withheld
        removed = old_withheld - new_withheld
        parts = []
        if added:
            parts.append(f"+{len(added)} newly withheld")
        if removed:
            parts.append(f"-{len(removed)} no longer withheld")
        diffs.append("withheld: " + ", ".join(parts))

    return ("DRIFT" if diffs else "OK"), diffs


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="exported dossier HTML file(s)")
    args = ap.parse_args(argv)

    worst = 0
    for path in args.files:
        status, diffs = verify_file(path)
        worst = max(worst, {"OK": 0, "DRIFT": 1, "ERROR": 2}[status])
        line = f"{status} {path}"
        if diffs:
            line += ": " + "; ".join(diffs)
        sys.stdout.write(line + "\n")
    return worst


if __name__ == "__main__":
    sys.exit(main())
