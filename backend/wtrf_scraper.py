"""Search the Watching the River Flow (WTRF) SMF forum for torrent posts
matching LosslessBob entries, then download the .torrent file.

Matching strategy (strongest to weakest signal):
  1. FFP checksum match in post body  — definitive (unique per recording)
  2. Audio filename match in post body — near-definitive
  3. Equipment/source-chain token match from entries.source_chain/description
  4. Taper name match from entries.taper_name

Multiple posts can exist for the same date and city (different tapers / sources).
Signal scoring disambiguates them; the torrent is only downloaded when confidence
is at least 'medium'.  Ambiguous or low-confidence results are logged in
wtrf_downloads with status='skipped' for manual review.

All HTTP requests are throttled via a configurable ``delay`` parameter (default
2 s between page fetches, at least 10 s between search queries — the WTRF
forum's flood-control rejects searches issued less than 5 s apart).  Callers
should NOT issue concurrent requests against the same session.
"""
import logging
import re
import time
from calendar import month_abbr, month_name
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from backend.credentials import SERVICE_WTRF, get_credentials
from backend.forum_poster import FORUM_BASE, _get_session

logger = logging.getLogger(__name__)

_DEFAULT_DELAY = 2.0   # seconds between page fetches
_SEARCH_DELAY  = 10.0  # floor for seconds between search2 queries — the WTRF
                        # forum's flood-control rejects searches < 5s apart

# Confidence levels ordered weakest → strongest for comparison
_CONF_ORDER = ("not_found", "needs_review", "ambiguous", "medium", "high", "definitive")


# ── URL helpers ────────────────────────────────────────────────────────────────

def _resolve_url(href: str) -> str:
    if href and not href.startswith("http"):
        return FORUM_BASE + "/" + href.lstrip("/")
    return href


def _normalise_topic_url(url: str) -> str:
    """Strip msg anchor and page offset so the same topic isn't fetched twice."""
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"(\?topic=\d+)\.\d+", r"\g<1>.0", url)
    return url


# ── Date variant generation ────────────────────────────────────────────────────

def _date_variants(date_str: str) -> list[str]:
    """Convert an LB date_str (M/D/YY or M/D/YYYY) to multiple human-readable
    formats used in forum topic titles.

    Returns an ordered list (most specific first).  Returns [] when the date
    contains ``xx`` placeholders or cannot be parsed.

    Args:
        date_str: LB date string, e.g. ``"4/23/26"`` or ``"4/23/2026"``.

    Returns:
        List of date format strings to try as search queries.
    """
    parts = date_str.strip().split("/")
    if len(parts) != 3:
        return []
    month_s, day_s, year_s = (p.strip() for p in parts)
    if "x" in month_s.lower() or "x" in day_s.lower():
        return []
    try:
        m = int(month_s)
        d = int(day_s)
        y = int(year_s)
        if y < 100:
            y = 1900 + y if y >= 49 else 2000 + y
    except ValueError:
        return []
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return []

    mname = month_name[m]   # "April"
    mabbr = month_abbr[m]   # "Apr"
    return [
        f"{y:04d}-{m:02d}-{d:02d}",       # 2026-04-23  (ISO — most reliable)
        f"{mname} {d}, {y:04d}",           # April 23, 2026
        f"{mabbr} {d}, {y:04d}",           # Apr 23, 2026
        f"{d} {mname} {y:04d}",            # 23 April 2026
        f"{m:02d}/{d:02d}/{y:04d}",        # 04/23/2026
        f"{m}/{d}/{y:04d}",                # 4/23/2026
        f"{mname} {d}",                    # April 23  (broad fallback)
    ]


# ── Signal extraction ──────────────────────────────────────────────────────────

def _equipment_tokens(source_chain: str, description: str) -> list[str]:
    """Extract distinctive equipment phrases from a source/signal chain.

    Splits on ``>`` (the standard chain delimiter) and also on newlines.
    Strips parenthetical quality specs like ``(24-bit / 48000 Hz)``.
    Only keeps segments >= 5 chars (too-short tokens cause false positives).

    Args:
        source_chain: Parsed signal chain from entries.source_chain.
        description: Full description text as fallback.

    Returns:
        List of lowercase equipment token strings.
    """
    text = source_chain or description or ""
    tokens = []
    for seg in re.split(r"[>\n]", text):
        seg = re.sub(r"\(.*?\)", "", seg).strip().rstrip("(").strip()
        if len(seg) >= 5:
            tokens.append(seg.lower())
    return tokens


# ── Candidate scoring ──────────────────────────────────────────────────────────

def _score_candidate(
    post_body: str,
    checksums: list[dict],
    entry: dict,
) -> tuple[int, dict]:
    """Score a candidate post body against an LB entry's known signals.

    Args:
        post_body: Plain-text body of the first (original) post.
        checksums: Rows from checksums table for this lb_number.
        entry: Row dict from the entries table.

    Returns:
        Tuple of (score: int, signals: dict).
    """
    body_lower = post_body.lower()
    signals: dict = {}
    score = 0

    # Round 0 — explicit "LB-NNNNN" tag in the post body. Posts created by this
    # app's forum_poster embed one in the metadata header (see
    # backend/forum_poster.py:_build_body). A tag for a DIFFERENT LB number
    # means the post documents that other show, not this entry — hard
    # disqualify rather than let it compete on weak date/torrent-only signals.
    own_lb = entry.get("lb_number")
    tagged = {int(n) for n in re.findall(r"lb-0*(\d{3,5})\b", body_lower)}
    if own_lb is not None and own_lb in tagged:
        score += 200
        signals["lb_tag_match"] = True
    elif tagged - ({own_lb} if own_lb is not None else set()):
        signals["lb_tag_mismatch"] = sorted(tagged)
        return score, signals

    # Round 1 — FFP checksums (100 pts each, definitive)
    ffp_hits = sum(
        1 for c in checksums
        if c.get("chk_type") == "f" and c.get("checksum") and c["checksum"] in post_body
    )
    if ffp_hits:
        score += ffp_hits * 100
        signals["ffp_matches"] = ffp_hits

    # Round 2 — Audio filenames (10 pts each)
    fname_hits = sum(
        1 for c in checksums
        if c.get("filename") and c["filename"] in post_body
    )
    if fname_hits:
        score += fname_hits * 10
        signals["filename_matches"] = fname_hits

    # Round 3 — Equipment/source-chain tokens (8 pts each)
    eq_tokens = _equipment_tokens(
        entry.get("source_chain") or "",
        entry.get("description") or "",
    )
    eq_hits = sum(1 for tok in eq_tokens if tok and tok in body_lower)
    if eq_hits:
        score += eq_hits * 8
        signals["equipment_matches"] = eq_hits

    # Round 4 — Taper name (20 pts, only when >= 3 chars to avoid short false positives)
    taper = (entry.get("taper_name") or "").strip().lower()
    if taper and len(taper) >= 3 and taper in body_lower:
        score += 20
        signals["taper_match"] = entry.get("taper_name")

    return score, signals


def _classify_confidence(score: int, signals: dict) -> str:
    """Map a numeric score + signal dict to a named confidence level.

    Args:
        score: Numeric score from _score_candidate.
        signals: Signal dict from _score_candidate.

    Returns:
        One of: 'definitive', 'high', 'medium', 'needs_review', 'not_found'.
    """
    if signals.get("ffp_matches", 0) >= 1:
        return "definitive"
    if signals.get("lb_tag_match"):
        return "high"
    fname = signals.get("filename_matches", 0)
    eq    = signals.get("equipment_matches", 0)
    tap   = "taper_match" in signals
    if fname >= 3 or (fname >= 1 and tap):
        return "high"
    if (eq >= 2 and tap) or (fname >= 1 and eq >= 2):
        return "medium"
    if score >= 5:
        return "needs_review"
    return "not_found"


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _search_board(
    session: requests.Session,
    board_id: int,
    query: str,
    delay: float,
) -> list[tuple[str, str]]:
    """POST to SMF search2 and return (topic_url, topic_title) pairs.

    Searches subject lines only, restricted to ``board_id``.
    Sleeps ``delay`` seconds before issuing the request.

    Args:
        session: Authenticated requests.Session.
        board_id: SMF board number to restrict the search to.
        query: Search term (typically a date string variant).
        delay: Seconds to sleep before the request.

    Returns:
        Deduplicated list of (normalised_topic_url, title) tuples.
    """
    time.sleep(delay)
    payload = [
        ("search",              query),
        ("advanced",            "1"),
        ("searchtype",          "1"),   # all words
        ("subject_only",        "1"),
        ("sort",                "relevance|asc"),
        (f"brd[{board_id}]",   str(board_id)),
    ]
    try:
        resp = session.post(
            f"{FORUM_BASE}/index.php?action=search2",
            data=payload,
            timeout=20,
            headers={"Referer": FORUM_BASE},
        )
    except Exception as exc:
        logger.warning("WTRF search error for %r: %s", query, exc)
        return []

    if "action=login" in resp.url:
        logger.warning("WTRF search: session expired (redirected to login)")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=lambda h: h and "topic=" in h):
        text = a.get_text(strip=True)
        if text.startswith("Re:") or not text:
            continue
        url = _normalise_topic_url(_resolve_url(a["href"]))
        if url not in seen:
            seen[url] = text
    return list(seen.items())


def _fetch_topic(
    session: requests.Session,
    topic_url: str,
    delay: float,
) -> dict:
    """Fetch a topic page and return the first-post body text and torrent URL.

    Only the first post (original poster) is scanned for torrent attachments
    and body text; reply posts are ignored for scoring purposes.
    Sleeps ``delay`` seconds before issuing the request.

    Args:
        session: Authenticated requests.Session.
        topic_url: Absolute topic URL (normalised, page 0).
        delay: Seconds to sleep before the request.

    Returns:
        Dict with keys: body_text (str), torrent_url (str|None), topic_title (str).
    """
    time.sleep(delay)
    result: dict = {"body_text": "", "torrent_url": None, "topic_title": ""}
    try:
        resp = session.get(topic_url, timeout=20, headers={"Referer": FORUM_BASE})
    except Exception as exc:
        logger.warning("WTRF fetch topic error %s: %s", topic_url, exc)
        return result

    if "action=login" in resp.url:
        logger.warning("WTRF topic fetch: session expired")
        return result

    soup = BeautifulSoup(resp.text, "lxml")

    title_tag = soup.find("title")
    if title_tag:
        result["topic_title"] = title_tag.get_text(strip=True)

    # First post body: the first <div id="msg_NNNN"> element
    first_msg = soup.find("div", id=re.compile(r"^msg_\d+$"))
    if first_msg:
        result["body_text"] = first_msg.get_text(separator="\n")

    # Torrent attachment: look only in the FIRST div.attachments on the page
    # (subsequent ones belong to reply posts).  The attachment link has
    # action=dlattach in its href and ".torrent" in its visible text.
    for attach_div in soup.find_all("div", class_="attachments"):
        for a in attach_div.find_all(
            "a", href=lambda h: h and "dlattach" in (h or "")
        ):
            if ".torrent" in a.get_text(strip=True).lower():
                result["torrent_url"] = _resolve_url(a["href"])
                break
        if result["torrent_url"]:
            break   # stop after first post's attachment section

    return result


def _download_torrent(
    session: requests.Session,
    torrent_url: str,
    dest_dir: Path,
    lb_number: int,
    delay: float,
) -> Path | None:
    """Download a torrent file from ``torrent_url`` into ``dest_dir``.

    Derives the filename from the Content-Disposition header when available,
    falling back to an LB-based name.  Sleeps ``delay`` seconds before the
    request.

    Args:
        session: Authenticated requests.Session.
        torrent_url: Full URL of the dlattach torrent link.
        dest_dir: Directory to write the file into (created if absent).
        lb_number: Used for fallback filename construction.
        delay: Seconds to sleep before downloading.

    Returns:
        Path to the saved file, or None on failure.
    """
    time.sleep(delay)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        resp = session.get(
            torrent_url, timeout=30, stream=True, headers={"Referer": FORUM_BASE}
        )
        resp.raise_for_status()

        # Filename from Content-Disposition, falling back to attach-id or lb_number
        fname: str | None = None
        cd = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename[^;=\n]*=\s*["\']?([^"\'\n;]+)', cd, re.IGNORECASE)
        if m:
            fname = m.group(1).strip().strip("\"'")
        if not fname:
            m2 = re.search(r"attach=(\d+)", torrent_url)
            if m2:
                fname = f"LB-{lb_number:05d}-attach{m2.group(1)}.torrent"
            else:
                fname = f"LB-{lb_number:05d}.torrent"
        if not fname.lower().endswith(".torrent"):
            fname += ".torrent"

        dest = dest_dir / fname
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
        logger.info(
            "wtrf_scraper: downloaded %s (%d bytes)", dest.name, dest.stat().st_size
        )
        return dest
    except Exception as exc:
        logger.error("wtrf_scraper: torrent download failed %s: %s", torrent_url, exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def find_torrent_for_lb(
    lb_number: int,
    board_id: int,
    dest_dir: str | Path,
    delay: float = _DEFAULT_DELAY,
    db_path=None,
) -> dict:
    """Search WTRF for a torrent post matching lb_number and download it.

    Workflow:
      1. Gather match signals from DB (checksums, entry metadata).
      2. Log in with stored WTRF credentials.
      3. Search board subjects with each date variant until candidates found.
         Falls back to a year-month search if all date variants fail.
      4. Fetch the first post of each candidate topic and score it.
      5. Classify confidence; auto-download only at 'medium' or above.
      6. On a tie between two candidates, return 'ambiguous'.

    All HTTP requests are separated by at least ``delay`` seconds (search
    queries use ``max(delay * 1.5, 10.0)`` to stay clear of the forum's
    search flood-control).

    Args:
        lb_number: LosslessBob entry number.
        board_id: SMF board number to search (16 = "Up To Me").
        dest_dir: Directory to write downloaded .torrent files into.
        delay: Minimum seconds between HTTP requests (default 2.0).
        db_path: Optional SQLite path override.

    Returns:
        Dict with keys:
          ok (bool), torrent_path (str|None), topic_url (str|None),
          confidence (str), signals (dict), error (str|None).
        On confidence='ambiguous', also includes topic_url_2 (str) — the
        runner-up topic that tied with topic_url, for manual review.
    """
    from backend import db as database

    _fail = lambda conf, err: {   # noqa: E731
        "ok": False, "torrent_path": None, "topic_url": None,
        "confidence": conf, "signals": {}, "error": err,
    }

    # ── Gather DB signals ──────────────────────────────────────────────────────
    entry_data = database.get_entry(lb_number, db_path=db_path)
    if not entry_data:
        return _fail("not_found", f"LB-{lb_number:05d} not in entries table")

    entry     = entry_data["entry"]
    checksums = entry_data["checksums"]
    date_str  = entry.get("date_str") or ""
    variants  = _date_variants(date_str)

    if not variants:
        return _fail(
            "not_found",
            f"Cannot derive date variants from date_str={date_str!r}",
        )

    # ── Login ──────────────────────────────────────────────────────────────────
    username, password = get_credentials(SERVICE_WTRF)
    if not username or not password:
        return _fail("not_found", "WTRF credentials not configured")

    session = _get_session(username, password)
    if session is None:
        return _fail("not_found", "WTRF login failed — check credentials")

    search_delay = max(delay * 1.5, _SEARCH_DELAY)

    # ── Collect candidate topic URLs ───────────────────────────────────────────
    seen_urls: set[str] = set()
    candidates: list[tuple[str, str]] = []   # (url, title)

    for variant in variants:
        results = _search_board(session, board_id, variant, search_delay)
        for url, title in results:
            if url not in seen_urls:
                seen_urls.add(url)
                candidates.append((url, title))
        if candidates:
            break   # stop at first date variant that yields results

    # Broad fallback: year-month only (catches non-standard title formats)
    if not candidates:
        parts = date_str.split("/")
        if len(parts) == 3:
            try:
                m_idx = int(parts[0])
                yr    = int(parts[2])
                if yr < 100:
                    yr = 1900 + yr if yr >= 49 else 2000 + yr
                ym_query = f"{month_name[m_idx]} {yr:04d}"
                for url, title in _search_board(session, board_id, ym_query, search_delay):
                    if url not in seen_urls:
                        seen_urls.add(url)
                        candidates.append((url, title))
            except (ValueError, IndexError):
                pass

    if not candidates:
        return _fail(
            "not_found",
            "No matching posts found on WTRF for this entry's date",
        )

    logger.info(
        "wtrf_scraper: LB-%05d — %d candidate topic(s) to score", lb_number, len(candidates)
    )

    # ── Score each candidate ───────────────────────────────────────────────────
    # Elements: (score, signals, topic_url, torrent_url)
    scored: list[tuple[int, dict, str, str | None]] = []
    disqualified = 0

    for topic_url, _title in candidates:
        post = _fetch_topic(session, topic_url, delay)
        if not post["body_text"] and not post["torrent_url"]:
            continue
        sc, sigs = _score_candidate(post["body_text"], checksums, entry)
        if sigs.get("lb_tag_mismatch"):
            disqualified += 1
            logger.info(
                "wtrf_scraper: LB-%05d disqualifying %s — post tagged for %s",
                lb_number, topic_url, sigs["lb_tag_mismatch"],
            )
            continue
        if post["torrent_url"]:
            sc += 5
            sigs["has_torrent"] = True
        scored.append((sc, sigs, topic_url, post["torrent_url"]))
        logger.debug(
            "wtrf_scraper: LB-%05d topic %s score=%d sigs=%s",
            lb_number, topic_url, sc, sigs,
        )

    if not scored:
        if disqualified:
            return _fail(
                "not_found",
                f"All {disqualified} candidate post(s) explicitly tagged for a different LB entry",
            )
        return _fail("not_found", "Candidates found but none had accessible content")

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_sigs, best_url, best_torrent_url = scored[0]

    # Tie → ambiguous (two posts equally match — need manual review)
    if len(scored) >= 2 and scored[0][0] == scored[1][0] and scored[0][0] > 0:
        logger.warning(
            "wtrf_scraper: LB-%05d ambiguous — top two posts tied at score=%d",
            lb_number, best_score,
        )
        return {
            "ok": False, "torrent_path": None, "topic_url": best_url,
            "topic_url_2": scored[1][2],
            "confidence": "ambiguous", "signals": best_sigs,
            "error": "Two posts match equally — manual review required",
        }

    conf = _classify_confidence(best_score, best_sigs)

    if conf in ("not_found", "needs_review"):
        return {
            "ok": False, "torrent_path": None, "topic_url": best_url,
            "confidence": conf, "signals": best_sigs,
            "error": f"Best match confidence too low ({conf}, score={best_score})",
        }

    if not best_torrent_url:
        return {
            "ok": False, "torrent_path": None, "topic_url": best_url,
            "confidence": conf, "signals": best_sigs,
            "error": "Matched post has no .torrent attachment",
        }

    # ── Download torrent ───────────────────────────────────────────────────────
    torrent_path = _download_torrent(
        session, best_torrent_url, Path(dest_dir), lb_number, delay
    )
    if not torrent_path:
        return {
            "ok": False, "torrent_path": None, "topic_url": best_url,
            "confidence": conf, "signals": best_sigs,
            "error": "Torrent file download failed",
        }

    logger.info(
        "wtrf_scraper: LB-%05d matched (conf=%s score=%d) → %s",
        lb_number, conf, best_score, torrent_path.name,
    )
    return {
        "ok": True,
        "torrent_path": str(torrent_path),
        "topic_url": best_url,
        "confidence": conf,
        "signals": best_sigs,
        "error": None,
    }
