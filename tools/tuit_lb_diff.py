"""Diff the mirrored TUIT catalogue against lb_master / my_collection / checksums.

Read-only.  Two findings sets (TODO-315):

(i) ``missing``   TUIT recordings whose LB number the collection does not hold
                  (no ``my_collection`` row), with the LB's ``lb_status``.
(ii) ``filename`` per-recording track-name disagreements between TUIT's
                  ``files_json`` and the ``checksums`` rows of the same LB.  The
                  detail page lists names and sizes only, never hashes, so this
                  compares the *sets of track stems* (extension and case folded);
                  a differing set is a candidate for the checksum-dispute flow
                  (TODO-299) or for a re-source decision.

Also reported: recordings with no LB number or an LB unknown to ``lb_master``,
and LBs with TUIT audio but no ``checksums`` rows at all.

Usage:
    .venv/bin/python3 tools/tuit_lb_diff.py [--db PATH] [--out FILE.md] [--json FILE]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logger = logging.getLogger("tuit_lb_diff")

DEFAULT_DB = _project_root / "data" / "losslessbob.db"
DEFAULT_OUT = _project_root / "docs" / "tuit_lb_diff.md"

AUDIO_EXTS = {".flac", ".shn", ".wav", ".ape", ".wv", ".mp3", ".m4a", ".ogg", ".aif", ".aiff"}
KINDS = ("db_lacks_tracks", "renamed", "mixed", "db_extra")  # most to least actionable
_SHOWN = 40  # rows listed per section in the markdown (full set goes to --json)


def track_stem(name: str) -> str:
    """Normalise a track filename for comparison.

    Args:
        name: Filename as stored by TUIT or in ``checksums.filename``.

    Returns:
        Lower-cased basename with a known audio/checksum extension removed.
    """
    base = re.sub(r"\s+", " ", re.split(r"[\\/]", name.strip())[-1].casefold())
    dot = base.rfind(".")
    if dot > 0 and (base[dot:] in AUDIO_EXTS):
        base = base[:dot]
    return base


def tuit_audio_stems(files_json: str | None) -> set[str]:
    """Return the audio-track stems listed in a ``tuit_recordings.files_json`` value.

    Args:
        files_json: JSON list of ``{"name", "size_bytes", ...}`` or None.

    Returns:
        Set of normalised stems; empty on missing/corrupt JSON.
    """
    try:
        files = json.loads(files_json or "[]")
    except ValueError:
        return set()
    out = set()
    for f in files if isinstance(files, list) else []:
        name = f.get("name", "") if isinstance(f, dict) else ""
        dot = name.rfind(".")
        if dot > 0 and name[dot:].casefold() in AUDIO_EXTS:
            out.add(track_stem(name))
    return out


def db_audio_stems(filenames: list[str]) -> set[str]:
    """Return audio-track stems from ``checksums.filename`` values.

    Args:
        filenames: Filenames of one LB's checksum rows.

    Returns:
        Set of normalised stems for names carrying an audio extension.
    """
    out = set()
    for name in filenames:
        base = re.split(r"[\\/]", name.strip())[-1]
        dot = base.rfind(".")
        if dot > 0 and base[dot:].casefold() in AUDIO_EXTS:
            out.add(track_stem(base))
    return out


def classify(tuit: set[str], db: set[str]) -> str:
    """Classify a track-set disagreement.

    Args:
        tuit: Normalised TUIT audio stems.
        db: Normalised ``checksums`` audio stems for the same LB.

    Returns:
        ``db_lacks_tracks`` (TUIT is a strict superset: the LB's checksums miss
        tracks TUIT ships), ``renamed`` (equal size, disjoint-ish sets: tracks named
        differently), ``db_extra`` (DB is a strict superset: extra/duplicate rows,
        usually multi-disc or multi-format) or ``mixed``.
    """
    if db < tuit:
        return "db_lacks_tracks"
    if tuit < db:
        return "db_extra"
    if len(tuit) == len(db):
        return "renamed"
    return "mixed"


def compute_diff(conn: sqlite3.Connection) -> dict:
    """Build the findings from an open connection (read-only use).

    Args:
        conn: Connection to a DB holding the tuit_*, lb_master, my_collection and
            checksums tables.

    Returns:
        Dict with keys ``stats``, ``missing``, ``unlinked``, ``no_checksums`` and
        ``filename`` (lists of dicts).
    """
    conn.row_factory = sqlite3.Row
    status = {r[0]: r[1] for r in conn.execute("SELECT lb_number, lb_status FROM lb_master")}
    held = {r[0] for r in conn.execute("SELECT DISTINCT lb_number FROM my_collection")}
    names: dict[int, list[str]] = defaultdict(list)
    for r in conn.execute("SELECT lb_number, filename FROM checksums WHERE filename IS NOT NULL"):
        names[r[0]].append(r[1])

    missing, unlinked, no_checksums, filename = [], [], [], []
    recs = conn.execute(
        "SELECT rec_id, lb_number, info_hash, date_str, venue, source_type, format, "
        "files_json FROM tuit_recordings ORDER BY rec_id"
    ).fetchall()
    for r in recs:
        base = {"rec_id": r["rec_id"], "lb_number": r["lb_number"],
                "info_hash": r["info_hash"], "date": r["date_str"], "venue": r["venue"]}
        lb = r["lb_number"]
        if lb is None or lb not in status:
            unlinked.append({**base, "reason": "no LB number" if lb is None
                             else "LB not in lb_master"})
            continue
        if lb not in held:
            missing.append({**base, "lb_status": status[lb], "format": r["format"]})
        tuit = tuit_audio_stems(r["files_json"])
        if not tuit:
            continue
        db = db_audio_stems(names.get(lb, []))
        if not db:
            no_checksums.append({**base, "tuit_tracks": len(tuit)})
            continue
        if tuit != db:
            filename.append({
                **base, "kind": classify(tuit, db), "lb_status": status[lb],
                "tuit_tracks": len(tuit),
                "db_tracks": len(db),
                "only_tuit": sorted(tuit - db), "only_db": sorted(db - tuit),
            })
    stats = {
        "tuit_recordings": len(recs),
        "missing_from_collection": len(missing),
        "missing_distinct_lbs": len({m["lb_number"] for m in missing}),
        "unlinked": len(unlinked),
        "lb_without_checksums": len(no_checksums),
        "filename_disagreements": len(filename),
        "filename_distinct_lbs": len({m["lb_number"] for m in filename}),
    }
    for kind in KINDS:
        stats[f"filename_{kind}"] = sum(1 for m in filename if m["kind"] == kind)
    return {"stats": stats, "missing": missing, "unlinked": unlinked,
            "no_checksums": no_checksums, "filename": filename}


def _table(headers: list[str], rows: list[list]) -> list[str]:
    """Render a markdown table."""
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def render_markdown(diff: dict, generated: str | None = None) -> str:
    """Render the findings as a markdown summary.

    Args:
        diff: Result of :func:`compute_diff`.
        generated: Timestamp string; defaults to now (UTC).

    Returns:
        Markdown text.
    """
    generated = generated or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    s = diff["stats"]
    L = ["# TUIT vs collection diff", "",
         f"Generated {generated} by `tools/tuit_lb_diff.py` (read-only).", "",
         "| Measure | Count |", "|---|---|"]
    L += [f"| {k.replace('_', ' ')} | {v} |" for k, v in s.items()]
    L += ["", "TUIT's detail page lists file names and sizes, not hashes, so (ii) compares "
          "track-name sets only; hash-level disputes still need the `.md5`/`.ffp` sidecars "
          "fetched from the torrent.", ""]
    miss = diff["missing"]
    L += [f"## (i) TUIT recordings the collection lacks ({len(miss)})", ""]
    by_status: dict[str, int] = defaultdict(int)
    for m in miss:
        by_status[m["lb_status"]] += 1
    L += ["By lb_status: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())), ""]
    L += _table(["rec", "LB", "status", "date", "venue", "format"],
                [[m["rec_id"], m["lb_number"], m["lb_status"], m["date"], m["venue"],
                  m["format"]] for m in miss[:_SHOWN]])
    if len(miss) > _SHOWN:
        L += ["", f"...{len(miss) - _SHOWN} more in the --json output."]
    fn = diff["filename"]
    L += ["", f"## (ii) Track-name disagreements ({len(fn)}) - checksum-dispute input", ""]
    for kind in KINDS:
        sub = [m for m in fn if m["kind"] == kind]
        L += [f"### {kind} ({len(sub)})", ""]
        L += _table(["rec", "LB", "TUIT", "DB", "only on TUIT", "only in DB"],
                    [[m["rec_id"], m["lb_number"], m["tuit_tracks"], m["db_tracks"],
                      ", ".join(m["only_tuit"][:3]) + (" ..." if len(m["only_tuit"]) > 3 else ""),
                      ", ".join(m["only_db"][:3]) + (" ..." if len(m["only_db"]) > 3 else "")]
                     for m in sub[:_SHOWN // 2]])
        if len(sub) > _SHOWN // 2:
            L += ["", f"...{len(sub) - _SHOWN // 2} more in the --json output."]
        L += [""]
    L += ["", f"## Unlinked recordings ({len(diff['unlinked'])})", ""]
    L += _table(["rec", "LB", "reason", "date", "venue"],
                [[m["rec_id"], m["lb_number"] or "", m["reason"], m["date"], m["venue"]]
                 for m in diff["unlinked"][:_SHOWN]])
    L += ["", f"## LBs on TUIT with no checksum rows ({len(diff['no_checksums'])})", ""]
    L += _table(["rec", "LB", "tracks"],
                [[m["rec_id"], m["lb_number"], m["tuit_tracks"]]
                 for m in diff["no_checksums"][:_SHOWN]])
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Opens the DB read-only and writes the report."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Markdown summary path.")
    ap.add_argument("--json", default="", help="Also write the full findings as JSON.")
    args = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        diff = compute_diff(conn)
    finally:
        conn.close()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(render_markdown(diff), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(diff, indent=1), encoding="utf-8")
    print("  ".join(f"{k}={v}" for k, v in diff["stats"].items()))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
