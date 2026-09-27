#!/usr/bin/env python3
"""Tag incomplete WTRF torrents in qBittorrent by what they are missing.

Polls qBittorrent for torrents carrying the ``wtrf`` tag whose progress is
below 100%, reads each one's per-file progress, and tags it:

  ``missing music``   at least one audio file is short of 100%
  ``missing extras``  every audio file is complete; only text, artwork,
                      checksums or other extras are missing

The two tags are exclusive — the wrong one is removed when a torrent moves
between them — and both are removed from WTRF torrents that have since
completed. Dry-run by default; ``--apply`` writes the tags.

Usage::

    .venv/bin/python3 tools/wtrf_tag_incomplete.py            # preview
    .venv/bin/python3 tools/wtrf_tag_incomplete.py --apply    # tag

Must be run from the project root directory.
"""
import argparse
import collections
import logging
import sys
from pathlib import Path, PurePosixPath

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend.checksum_utils import AUDIO_EXTS  # noqa: E402
from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials  # noqa: E402
from backend.qbittorrent import _base_url, _login, _make_session  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

WTRF_TAG = "wtrf"
TAG_MUSIC = "missing music"
TAG_EXTRAS = "missing extras"
_AUDIO = AUDIO_EXTS | {".mp3"}


def classify(files: list[dict]) -> str:
    """Return the tag an incomplete torrent's file list earns.

    Args:
        files: qBittorrent ``/torrents/files`` entries (``name``, ``progress``).

    Returns:
        ``TAG_MUSIC`` if any audio file is incomplete, else ``TAG_EXTRAS``.
    """
    for f in files:
        if f["progress"] < 1 and PurePosixPath(f["name"]).suffix.lower() in _AUDIO:
            return TAG_MUSIC
    return TAG_EXTRAS


def main() -> int:
    """Poll qBittorrent and tag incomplete WTRF torrents; return an exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write tags (default: dry run)")
    args = ap.parse_args()

    base = _base_url(database.get_meta("qbt_host") or "localhost",
                     int(database.get_meta("qbt_port") or 8080))
    user, pw = get_credentials(SERVICE_QBT)
    _, key = get_credentials(SERVICE_QBT_KEY)
    s = _make_session(base, key or "")
    if not key and (err := _login(s, base, user or "", pw or "")):
        logger.error(err["error"])
        return 1

    torrents = s.get(base + "/api/v2/torrents/info",
                     params={"tag": WTRF_TAG}, timeout=60).json()
    want: dict[str, list[str]] = {TAG_MUSIC: [], TAG_EXTRAS: []}
    strip: dict[str, list[str]] = {TAG_MUSIC: [], TAG_EXTRAS: []}
    counts: collections.Counter = collections.Counter()

    for t in torrents:
        have = {x.strip() for x in t["tags"].split(",")}
        if t["progress"] >= 1:
            for tag in (TAG_MUSIC, TAG_EXTRAS):
                if tag in have:
                    strip[tag].append(t["hash"])
                    counts["cleared " + tag] += 1
            continue
        files = s.get(base + "/api/v2/torrents/files",
                      params={"hash": t["hash"]}, timeout=30).json()
        tag = classify(files)
        other = TAG_EXTRAS if tag == TAG_MUSIC else TAG_MUSIC
        counts[tag] += 1
        if tag not in have:
            want[tag].append(t["hash"])
        if other in have:
            strip[other].append(t["hash"])
        logger.debug("%-14s %5.1f%%  %s", tag, t["progress"] * 100, t["name"])

    logger.info("wtrf torrents: %d | %s", len(torrents),
                " | ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    for tag in (TAG_MUSIC, TAG_EXTRAS):
        logger.info("%-14s add %d, remove %d", tag, len(want[tag]), len(strip[tag]))

    if not args.apply:
        logger.info("dry run — re-run with --apply to write tags")
        return 0
    for tag in (TAG_MUSIC, TAG_EXTRAS):
        for path, hashes in (("addTags", want[tag]), ("removeTags", strip[tag])):
            for i in range(0, len(hashes), 200):
                r = s.post(base + f"/api/v2/torrents/{path}", timeout=30,
                           data={"hashes": "|".join(hashes[i:i + 200]), "tags": tag})
                r.raise_for_status()
    logger.info("tags written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
