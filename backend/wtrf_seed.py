"""Seed recordings to WTRF from a list of pasted forum topic links.

The WTRF search in :mod:`backend.wtrf_scraper` works the other way round: it
starts from an LB number and hunts the board for the matching topic. This
module starts from links the curator already has — a list pasted out of the
browser — and walks each one to the recording it seeds:

    topic link → first post → LB number + ``.torrent`` attachment
               → download the torrent → :mod:`backend.tracker_seed`

Everything after the download is tracker-agnostic and shared with TUIT,
including the three gates that stop qBittorrent ever being pointed at an
incomplete collection folder, and the ``<mount>/WTRF Seeds`` overlay that
supplies the ``LBF-*`` sidecars a curated folder does not keep.

The LB number is read from the post itself rather than guessed. In priority
order it comes from the attachment's own filename (``LB-00008.torrent`` — the
uploader tagged it, so this is definitive), then the topic title, then the post
body. A body naming several distinct LB numbers is reported as ambiguous and
seeded only when the caller pins the number explicitly, since seeding the wrong
recording publishes the wrong files under someone else's post.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from backend import db as database
from backend.credentials import SERVICE_WTRF, get_credentials
from backend.forum_poster import FORUM_BASE, _get_session
from backend.tracker_seed import SeedOptions, seed_torrent
from backend.wtrf_scraper import (
    _download_torrent,
    _fetch_topic,
    _normalise_topic_url,
    _resolve_url,
)

logger = logging.getLogger(__name__)

#: Default seconds between HTTP requests. WTRF is a small hobbyist forum;
#: this is page fetching, not searching, so the search flood-control floor
#: does not apply.
DEFAULT_DELAY = 2.0

#: An "LB-00123" tag as it appears in titles, bodies and attachment filenames.
#: The separator is optional and the zero padding is not required.
_LB_TAG_RE = re.compile(r"\bLB[-_ ]?(\d{1,5})\b", re.IGNORECASE)

#: A bare URL inside pasted text.
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

#: How the LB number was established, strongest first.
_SOURCE_CONFIDENCE = {
    "explicit": "definitive",     # the caller pinned it
    "attachment": "definitive",   # the uploader named the .torrent LB-NNNNN
    "title": "high",
    "body": "medium",
}


@dataclass
class LinkSpec:
    """One pasted line: a topic URL, plus an LB number if the line pinned one.

    Attributes:
        url: Normalised absolute topic URL.
        lb_number: LB number the caller wrote on the line, or None to read it
            out of the post.
        raw: The line as pasted, for error messages.
    """

    url: str
    lb_number: int | None
    raw: str


def _lb_numbers_in(text: str) -> list[int]:
    """Every distinct LB number tagged in a blob of text, in order of appearance.

    Args:
        text: Post body, title or attachment filename.

    Returns:
        Distinct LB numbers, first occurrence first.
    """
    found: list[int] = []
    for match in _LB_TAG_RE.finditer(text or ""):
        n = int(match.group(1))
        if n and n not in found:
            found.append(n)
    return found


def _host(url: str) -> str:
    """Hostname of a URL, lowercased and stripped of a leading ``www.``.

    Args:
        url: Any URL.

    Returns:
        The bare host, or "" when the URL has none.
    """
    return urlparse(url).hostname.lower().removeprefix("www.") if urlparse(url).hostname else ""


def is_wtrf_topic_url(url: str) -> bool:
    """Whether a URL points at a topic on the WTRF forum.

    Scheme and the ``www.`` prefix are ignored: ``FORUM_BASE`` is plain HTTP
    without a subdomain, but a link copied out of a browser is usually HTTPS
    and usually has one, and both reach the same board.

    Args:
        url: Absolute or forum-relative URL.

    Returns:
        True for a WTRF topic/msg link, False for anything else pasted along
        with it (image hosts, the curator's own notes, other forums).
    """
    resolved = _resolve_url(url)
    if _host(resolved) != _host(FORUM_BASE):
        return False
    return "topic=" in resolved or "msg" in resolved


def _canonical_topic_url(url: str) -> str:
    """Reduce a topic link to one canonical form so a topic is walked once.

    :func:`backend.wtrf_scraper._normalise_topic_url` drops the ``#msg``
    anchor and a numeric page offset, which is enough for search results. A
    link copied out of the address bar can also carry a ``.msgNNNN`` offset
    ("jump to this post"), which names the same topic and must collapse too.

    The origin is rewritten to ``FORUM_BASE`` as well, so the same topic
    pasted as ``https://www.…`` and ``http://…`` is walked once — and is
    fetched on the exact origin the logged-in session holds cookies for.

    Args:
        url: An absolute WTRF topic URL.

    Returns:
        The canonical ``FORUM_BASE/…?topic=<id>.0`` form.
    """
    normalised = re.sub(r"(\?topic=\d+)\.[^&#]*", r"\g<1>.0",
                        _normalise_topic_url(url))
    parts = urlparse(normalised)
    tail = parts.path or "/"
    if parts.query:
        tail += "?" + parts.query
    return FORUM_BASE + tail


def parse_topic_links(text: str) -> list[LinkSpec]:
    """Turn a pasted blob into the topic links to walk, in order.

    Each line may hold a bare URL, or an ``LB-00123 <url>`` pairing when the
    curator already knows which entry the post is for. Lines without a WTRF
    topic URL are dropped; the same topic appearing twice (as a ``#msg`` anchor
    and as a page-2 link, say) is walked once.

    Args:
        text: Pasted text, one link per line or whitespace-separated.

    Returns:
        Deduplicated LinkSpecs in the order they were pasted.
    """
    specs: list[LinkSpec] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        urls = [u for u in _URL_RE.findall(line) if is_wtrf_topic_url(u)]
        if not urls:
            continue
        # An LB tag on the line pins the entry, but only if it isn't merely
        # part of the URL itself.
        pinned = _lb_numbers_in(_URL_RE.sub(" ", line))
        for url in urls:
            norm = _canonical_topic_url(_resolve_url(url))
            if norm in seen:
                continue
            seen.add(norm)
            specs.append(LinkSpec(
                url=norm,
                lb_number=pinned[0] if len(pinned) == 1 else None,
                raw=line.strip(),
            ))
    return specs


def resolve_link(session: requests.Session, spec: LinkSpec,
                 delay: float = DEFAULT_DELAY) -> dict:
    """Fetch one topic and work out which LB it is and where its torrent is.

    Args:
        session: Authenticated WTRF session.
        spec: The pasted link, possibly with a pinned LB number.
        delay: Seconds to sleep before the request.

    Returns:
        Dict with ``lb_number`` (int|None), ``lb_candidates`` (list[int]),
        ``lb_source`` (str), ``confidence`` (str), ``torrent_url`` (str|None),
        ``title`` (str) and ``error`` (str).
    """
    out: dict = {
        "lb_number": spec.lb_number, "lb_candidates": [], "lb_source": "",
        "confidence": "not_found", "torrent_url": None, "title": "", "error": "",
    }
    post = _fetch_topic(session, spec.url, delay)
    out["title"] = post["topic_title"]
    out["torrent_url"] = post["torrent_url"]

    if not post["body_text"] and not post["torrent_url"]:
        out["error"] = "topic unreadable — session expired or the link is dead"
        return out

    if spec.lb_number is not None:
        out["lb_source"] = "explicit"
        out["confidence"] = _SOURCE_CONFIDENCE["explicit"]
    else:
        for field, source in (
            (post["attachment_text"], "attachment"),
            (post["topic_title"], "title"),
            (post["body_text"], "body"),
        ):
            candidates = _lb_numbers_in(field)
            if not candidates:
                continue
            out["lb_candidates"] = candidates
            out["lb_source"] = source
            if len(candidates) == 1:
                out["lb_number"] = candidates[0]
                out["confidence"] = _SOURCE_CONFIDENCE[source]
            else:
                # Several LB numbers in the same field — a lineage discussion,
                # or a post covering a run of shows. Refuse to guess.
                out["confidence"] = "ambiguous"
                out["error"] = (
                    f"{source} names {len(candidates)} LB numbers "
                    f"({', '.join(f'LB-{n:05d}' for n in candidates[:4])}) "
                    f"— pin one by writing it before the link"
                )
            break

    if out["lb_number"] is None and not out["error"]:
        out["error"] = "no LB number in the post's title, body or attachment"
    if out["torrent_url"] is None and not out["error"]:
        out["error"] = "the first post has no .torrent attachment"
    return out


def seed_from_links(
    text: str,
    opts: SeedOptions,
    dest_dir: str | Path,
    delay: float = DEFAULT_DELAY,
    dry_run: bool = False,
) -> Iterator[dict]:
    """Walk every pasted WTRF link and seed the recording it points at.

    Yields one event dict per link as it completes, so a caller can stream
    progress; a final ``{"event": "done", …}`` carries the tallies. Each
    attempt is recorded in ``wtrf_downloads`` exactly as the LB-first search
    path records its own.

    Args:
        text: Pasted blob of topic links.
        opts: Seeding policy (overlay, tolerances, qBittorrent tag).
        dest_dir: Directory to write downloaded ``.torrent`` files into.
        delay: Seconds between HTTP requests.
        dry_run: Resolve and report, but download nothing and seed nothing.

    Yields:
        Event dicts. Per-link events carry ``event="link"``, ``url``,
        ``lb_number``, ``status`` (one of resolved/downloaded/qbt_added/
        not_seeded/failed), ``reason`` and ``error``.
    """
    specs = parse_topic_links(text)
    dest = Path(dest_dir)
    yield {"event": "start", "total": len(specs)}
    if not specs:
        yield {"event": "done", "total": 0, "seeded": 0, "failed": 0,
               "error": "no WTRF topic links found in the pasted text"}
        return

    username, password = get_credentials(SERVICE_WTRF)
    if not username or not password:
        yield {"event": "done", "total": len(specs), "seeded": 0,
               "failed": len(specs), "error": "WTRF credentials not configured"}
        return
    session = _get_session(username, password)
    if session is None:
        yield {"event": "done", "total": len(specs), "seeded": 0,
               "failed": len(specs),
               "error": "WTRF login failed — check the stored credentials"}
        return

    seeded = failed = 0
    for index, spec in enumerate(specs, start=1):
        event = {"event": "link", "index": index, "total": len(specs),
                 "url": spec.url, "lb_number": None, "title": "",
                 "status": "failed", "reason": "", "error": "",
                 "confidence": "not_found", "folder": "", "overlay": False}
        try:
            info = resolve_link(session, spec, delay)
            event.update({
                "lb_number": info["lb_number"], "title": info["title"],
                "confidence": info["confidence"],
            })
            if info["error"] or info["lb_number"] is None:
                event["error"] = info["error"] or "unresolved"
                failed += 1
                _record(info, spec, None, "skipped", event["error"], "")
                yield event
                continue

            if dry_run:
                event.update({"status": "resolved",
                              "reason": f"would seed from {info['torrent_url']}"})
                yield event
                continue

            path = _download_torrent(
                session, info["torrent_url"], dest, info["lb_number"], delay
            )
            if path is None:
                event["error"] = "torrent download failed"
                failed += 1
                _record(info, spec, None, "failed", event["error"], "")
                yield event
                continue

            event["torrent_path"] = str(path)
            result = seed_one(info["lb_number"], str(path), opts)
            event.update({
                "reason": result["reason"], "folder": result["folder"],
                "overlay": result["overlay"],
            })
            if result["ok"]:
                event["status"] = "qbt_added"
                seeded += 1
                dl_id = _record(info, spec, str(path), "downloaded", "",
                                result["folder"])
                database.update_wtrf_download(dl_id, {
                    "status": "qbt_added",
                    "qbt_added_at": datetime.now(UTC).isoformat(),
                })
            elif result["error"]:
                event["status"] = "failed"
                event["error"] = result["error"]
                failed += 1
                _record(info, spec, str(path), "failed", result["error"],
                        result["folder"])
            else:
                event["status"] = "not_seeded"
                failed += 1
                _record(info, spec, str(path), "not_seeded", result["reason"],
                        result["folder"])
        except Exception as exc:                       # one bad link must not
            logger.exception("wtrf_seed: %s", spec.url)  # kill the whole batch
            event["error"] = str(exc)
            failed += 1
        yield event

    yield {"event": "done", "total": len(specs), "seeded": seeded,
           "failed": failed, "error": ""}


def seed_one(lb_number: int, torrent_path: str, opts: SeedOptions) -> dict:
    """Run the shared gate → overlay → qBittorrent sequence for one torrent.

    A thin pass-through to :func:`backend.tracker_seed.seed_torrent`, kept so
    callers of this module never need to know the seeding half is shared.

    Args:
        lb_number: LB number the torrent is for.
        torrent_path: Local ``.torrent`` file.
        opts: Seeding policy.

    Returns:
        The tracker_seed result dict (ok/folder/reason/overlay/error).
    """
    return seed_torrent(lb_number, torrent_path, opts)


def _record(info: dict, spec: LinkSpec, torrent_path: str | None,
            status: str, error: str, seed_folder: str) -> int:
    """Log one attempt to ``wtrf_downloads``.

    Args:
        info: The resolve_link result.
        spec: The pasted link.
        torrent_path: Local .torrent path, or None if nothing was downloaded.
        status: wtrf_downloads status word.
        error: Error/reason text, or "".
        seed_folder: Folder handed to qBittorrent, or "".

    Returns:
        The new row id.
    """
    return database.add_wtrf_download(
        lb_number=info["lb_number"] or 0,
        topic_url=spec.url,
        torrent_path=torrent_path,
        confidence=info["confidence"],
        signals_json=json.dumps({
            "via": "pasted_link",
            "lb_source": info["lb_source"],
            "lb_candidates": info["lb_candidates"],
            "title": info["title"],
        }),
        status=status,
        error=error or None,
        seed_folder=seed_folder or None,
    )
