"""Search the Watching the River Flow (WTRF) SMF forum for torrent posts
matching LosslessBob entries, then download the .torrent file.

Matching strategy (strongest to weakest signal):
  1. FFP or MD5/SHA1 checksum match in post body — definitive (unique per recording)
  2. Audio filename match in post body — near-definitive
  3. Equipment/source-chain token match from entries.source_chain/description
  4. Taper name match from entries.taper_name

Candidates are also hard-disqualified (never scored) when:
  - The post body or attachment filenames carry an explicit "LB-NNNNN" tag for
    a DIFFERENT entry (see BUG-225, BUG-227).
  - The post body's MD5/SHA1 checksums resolve to a DIFFERENT lb_number in the
    checksums table — the post documents another recording (usually a different
    taper of the same show), not this entry (see BUG-231). This prevents a false
    "ambiguous" tie between two other tapers' posts when the entry under review
    simply has no post of its own.
  - The post predates the entry's own acquisition window: entries.description
    ends with a "bittorrent download MM/YY" note recording when the LosslessBob
    curator downloaded that recording; a forum post can't be the source of a
    download that happened more than _DOWNLOAD_WINDOW_MONTHS before it.

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
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from backend.credentials import SERVICE_WTRF, get_credentials
from backend.forum_poster import FORUM_BASE, _get_session

logger = logging.getLogger(__name__)

_DEFAULT_DELAY = 2.0   # seconds between page fetches
_SEARCH_DELAY  = 10.0  # floor for seconds between search2 queries — the WTRF
                        # forum's flood-control rejects searches < 5s apart

# How far before an entry's own "bittorrent download MM/YY" date a candidate
# post is still allowed to have been made. A post can't be the source of a
# download that predates it, but tapers/uploaders sometimes leave a post up
# for a while before the curator gets to it, hence a window rather than an
# exact-month match.
_DOWNLOAD_WINDOW_MONTHS = 6

# Confidence levels ordered weakest → strongest for comparison
_CONF_ORDER = ("not_found", "needs_review", "ambiguous", "medium", "high", "definitive")

# Raw MD5 (32) / SHA1 (40) hex fingerprints as they appear in post bodies, used
# to detect a candidate that documents a DIFFERENT recording (its hashes resolve
# to another lb_number in the checksums table). See BUG-231.
_HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])"
                      r"|(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])")


def _extract_hashes(text: str) -> set[str]:
    """Extract lowercase MD5/SHA1 hex fingerprints from a post body.

    Args:
        text: Plain-text post body (and attachment text) to scan.

    Returns:
        Set of lowercase 32- or 40-char hex strings found in ``text``.
    """
    return {m.group(0).lower() for m in _HASH_RE.finditer(text or "")}


def _checksum_search_terms(checksums: list[dict], limit: int = 3) -> list[str]:
    """Pick distinct checksum hashes to use as full-text WTRF search queries.

    A single track's FFP/MD5/SHA1 hash is unique to one recording, so searching
    the forum body for it resolves straight to the post that lists it — the
    deterministic primary lookup. A handful are returned (not just one) so a
    post that happens to omit the first track still gets hit.

    Args:
        checksums: Rows from the checksums table for the entry.
        limit: Maximum number of hashes to return.

    Returns:
        Up to ``limit`` distinct hash strings, FFP/MD5/SHA1 types only.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for c in checksums:
        if c.get("chk_type") not in ("f", "m", "s"):
            continue
        h = (c.get("checksum") or "").strip()
        if h and h not in seen:
            seen.add(h)
            terms.append(h)
        if len(terms) >= limit:
            break
    return terms


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


# ── Download-window helpers ─────────────────────────────────────────────────────

_DOWNLOAD_DATE_RE = re.compile(r"download\s+(\d{1,2})/(\d{2,4})", re.IGNORECASE)


def _entry_download_date(entry: dict) -> date | None:
    """Parse the curator's own acquisition date from an entry's description.

    LosslessBob descriptions typically end with a note like
    "bittorrent download 05/26; did not review this" recording when *this*
    entry's recording was acquired. Earlier "download MM/YY" mentions in the
    text are usually notes about OTHER, related LB entries' history (e.g.
    cross-references to a sibling version), so the LAST match is taken as
    this entry's own date.

    Args:
        entry: Row dict from the entries table.

    Returns:
        The 1st of that month/year as a date, or None if no match/unparseable.
    """
    matches = _DOWNLOAD_DATE_RE.findall(entry.get("description") or "")
    if not matches:
        return None
    month_s, year_s = matches[-1]
    month = int(month_s)
    if not 1 <= month <= 12:
        return None
    year = int(year_s)
    if year < 100:
        year += 2000   # LosslessBob's bittorrent-era downloads are all 2000s+
    try:
        return date(year, month, 1)
    except ValueError:
        return None


def _months_before(d: date, months: int) -> date:
    """Return the 1st of the month that is ``months`` months before ``d``."""
    month_index = d.year * 12 + (d.month - 1) - months
    return date(month_index // 12, month_index % 12 + 1, 1)


_POST_DATE_RE = re.compile(r"on:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})")


def _parse_post_date(keyinfo_text: str) -> date | None:
    """Extract a post's creation date from its ``div.keyinfo`` text.

    SMF renders each message's timestamp as "« on: August 06, 2025, ... »"
    for the first post, or "« Reply #N on: ... »" for replies — both end in
    "on: <Month DD, YYYY>", so the same pattern covers both.

    Args:
        keyinfo_text: Text content of the message's keyinfo div.

    Returns:
        The post's date, or None if no timestamp was found/parseable.
    """
    m = _POST_DATE_RE.search(keyinfo_text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").date()
    except ValueError:
        return None


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
    # backend/forum_poster.py:_build_body), always zero-padded to 5 digits, but
    # legacy/non-app posts often write it unpadded (e.g. "LB-8"). A tag for a
    # DIFFERENT LB number means the post documents that other show, not this
    # entry — hard disqualify rather than let it compete on weak
    # date/torrent-only signals. Minimum digit count is 1 (not 3) so short,
    # unpadded numbers aren't missed.
    own_lb = entry.get("lb_number")
    tagged = {int(n) for n in re.findall(r"lb-0*(\d{1,5})\b", body_lower)}
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

    # Round 1b — MD5/SHA1 checksums (100 pts each, definitive). Older/SHN-era
    # posts often list raw MD5 or SHA1 sums ("checksum *filename") instead of
    # FFP-format fingerprints — chk_type 'm' (generic) and 's' (.shn) cover
    # those rows. An exact hash match is just as definitive as an FFP match.
    md5_hits = sum(
        1 for c in checksums
        if c.get("chk_type") in ("m", "s") and c.get("checksum") and c["checksum"] in post_body
    )
    if md5_hits:
        score += md5_hits * 100
        signals["md5_matches"] = md5_hits

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
    if signals.get("ffp_matches", 0) >= 1 or signals.get("md5_matches", 0) >= 1:
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
    subject_only: bool = True,
) -> list[tuple[str, str]]:
    """POST to SMF search2 and return (topic_url, topic_title) pairs.

    Restricted to ``board_id``.  With ``subject_only`` (default) only topic
    titles are searched — used for date-string queries.  With
    ``subject_only=False`` the full message body is searched too, which is what
    lets a checksum query resolve to the exact post that lists it.
    Sleeps ``delay`` seconds before issuing the request.

    Args:
        session: Authenticated requests.Session.
        board_id: SMF board number to restrict the search to.
        query: Search term (a date variant, or a checksum hash).
        delay: Seconds to sleep before the request.
        subject_only: Restrict to subject lines when True; search bodies too
            when False.

    Returns:
        Deduplicated list of (normalised_topic_url, title) tuples.
    """
    time.sleep(delay)
    payload = [
        ("search",              query),
        ("advanced",            "1"),
        ("searchtype",          "1"),   # all words
        ("subject_only",        "1" if subject_only else "0"),
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
        Dict with keys: body_text (str), torrent_url (str|None), topic_title (str),
        attachment_text (str) — visible link text of every attachment in the
        first post (e.g. attachment filenames), which can carry its own
        "LB-NNNNN" tag distinct from the body text — and post_date (date|None),
        the first post's creation date parsed from its keyinfo timestamp.
    """
    time.sleep(delay)
    result: dict = {
        "body_text": "", "torrent_url": None, "topic_title": "",
        "attachment_text": "", "post_date": None,
    }
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

        # Post date: the "« on: <Month DD, YYYY>, HH:MM:SS »" timestamp lives
        # in a sibling div.keyinfo within the same div.postarea, not inside
        # the message body div itself.
        postarea = first_msg.find_parent("div", class_="postarea")
        if postarea:
            keyinfo = postarea.find("div", class_="keyinfo")
            if keyinfo:
                result["post_date"] = _parse_post_date(keyinfo.get_text())

    # Torrent attachment: look only in the FIRST div.attachments on the page
    # (subsequent ones belong to reply posts).  The attachment link has
    # action=dlattach in its href and ".torrent" in its visible text.
    # Attachment filenames live in this div, a sibling of the post body div,
    # so they're never seen by body_text — collect their text separately so
    # an "LB-NNNNN" tag on the attachment itself (e.g. "LB-00008.torrent")
    # still feeds the Round 0 disqualification check in _score_candidate.
    attach_texts: list[str] = []
    for attach_div in soup.find_all("div", class_="attachments"):
        for a in attach_div.find_all(
            "a", href=lambda h: h and "dlattach" in (h or "")
        ):
            text = a.get_text(strip=True)
            attach_texts.append(text)
            if ".torrent" in text.lower() and not result["torrent_url"]:
                result["torrent_url"] = _resolve_url(a["href"])
        if attach_texts:
            break   # stop after first post's attachment section

    result["attachment_text"] = " ".join(attach_texts)
    return result


def _filename_from_content_disposition(content_disposition: str) -> str | None:
    """Extract a filename from a ``Content-Disposition`` header value.

    Prefers the plain ``filename="..."`` parameter. If only the RFC 5987
    extended form ``filename*=charset''value`` is present (e.g.
    ``filename*=UTF-8''real+name.torrent``), the ``charset''`` prefix is
    stripped and the remainder is percent-decoded per RFC 5987 (see BUG-233 —
    a prior regex matched the extended form's ``charset`` token itself,
    yielding a junk ``"UTF-8.torrent"`` filename that collided across every
    download in a batch run).

    Args:
        content_disposition: Raw ``Content-Disposition`` header value.

    Returns:
        The decoded filename, or ``None`` if neither parameter yields one.
    """
    m = re.search(
        r'filename(?!\*)\s*=\s*["\']?([^"\'\n;]+)', content_disposition, re.IGNORECASE
    )
    if m:
        return m.group(1).strip().strip("\"'")

    m_ext = re.search(r"filename\*\s*=\s*([^;\n]+)", content_disposition, re.IGNORECASE)
    if m_ext:
        value = m_ext.group(1).strip().strip("\"'")
        charset, sep, encoded = value.partition("''")
        if sep and encoded:
            try:
                return unquote(encoded, encoding=charset or "utf-8")
            except (LookupError, UnicodeDecodeError):
                return unquote(encoded)
        if value:
            return unquote(value)
    return None


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

        # Filename from Content-Disposition, falling back to attach-id or lb_number.
        cd = resp.headers.get("Content-Disposition", "")
        fname = _filename_from_content_disposition(cd)
        if fname:
            # A Content-Disposition filename identifies the physical torrent, not the
            # LB catalog entry — a single WTRF post (and its one .torrent) can
            # legitimately be the correct match for multiple LB entries (e.g. a
            # multi-show boxset where each entry owns one CD, see BUG-234). Without
            # the LB prefix, downloading it per-entry would overwrite the same path
            # each time.
            fname = f"LB-{lb_number:05d}-{fname}"
        else:
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
    hash_terms = _checksum_search_terms(checksums)

    # A forum post can't be the source of a download that predates it, so
    # anything posted more than _DOWNLOAD_WINDOW_MONTHS before the entry's own
    # "bittorrent download MM/YY" note is out of consideration. None when the
    # description has no such note (older entries / non-bittorrent sources).
    download_date   = _entry_download_date(entry)
    download_cutoff = (
        _months_before(download_date, _DOWNLOAD_WINDOW_MONTHS) if download_date else None
    )

    # A checksum body-search can still find the post even when the date is a
    # placeholder (e.g. "xx/xx/85"), so only bail here if BOTH lookups are
    # unavailable.
    if not variants and not hash_terms:
        return _fail(
            "not_found",
            f"Cannot derive date variants from date_str={date_str!r} "
            "and no checksums available for a body search",
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

    # Phase 1 — checksum body-search (deterministic). A track hash is unique to
    # one recording, so a full-text hit lands directly on the correct taper's
    # post regardless of how the topic title is formatted (BUG-232). Stop as
    # soon as any hash yields a result.
    for term in hash_terms:
        for url, title in _search_board(
            session, board_id, term, search_delay, subject_only=False
        ):
            if url not in seen_urls:
                seen_urls.add(url)
                candidates.append((url, title))
        if candidates:
            logger.info(
                "wtrf_scraper: LB-%05d — checksum body-search matched %d topic(s)",
                lb_number, len(candidates),
            )
            break

    # Phase 2 — date-variant subject search (fallback). Accumulate across ALL
    # variants rather than stopping at the first hit: different tapers title the
    # same show differently (ISO "2026-05-01" vs "May 1, 2026"), so an early
    # break can miss the very post we want (BUG-232).
    if not candidates:
        for variant in variants:
            for url, title in _search_board(session, board_id, variant, search_delay):
                if url not in seen_urls:
                    seen_urls.add(url)
                    candidates.append((url, title))

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
    disqualified_tag = 0
    disqualified_old = 0
    disqualified_foreign = 0

    for topic_url, _title in candidates:
        post = _fetch_topic(session, topic_url, delay)
        if not post["body_text"] and not post["torrent_url"]:
            continue
        if download_cutoff and post["post_date"] and post["post_date"] < download_cutoff:
            disqualified_old += 1
            logger.info(
                "wtrf_scraper: LB-%05d disqualifying %s — posted %s, before the "
                "%d-month window preceding the %s download date (cutoff %s)",
                lb_number, topic_url, post["post_date"],
                _DOWNLOAD_WINDOW_MONTHS, download_date, download_cutoff,
            )
            continue
        # Scan body + attachment filenames together so an "LB-NNNNN" tag on
        # either one (e.g. the attachment is literally named "LB-00008.torrent")
        # triggers the Round 0 disqualification check.
        scan_text = post["body_text"]
        if post["attachment_text"]:
            scan_text = f"{scan_text}\n{post['attachment_text']}"
        sc, sigs = _score_candidate(scan_text, checksums, entry)
        if sigs.get("lb_tag_mismatch"):
            disqualified_tag += 1
            logger.info(
                "wtrf_scraper: LB-%05d disqualifying %s — post tagged for %s",
                lb_number, topic_url, sigs["lb_tag_mismatch"],
            )
            continue
        # Cross-recording guard: a post whose checksums resolve to a DIFFERENT
        # lb_number documents that other recording (typically a different taper
        # of the same show), not this entry. Only applies when none of this
        # entry's own checksums matched — an FFP/MD5 hit for THIS entry already
        # proves ownership and short-circuits above via a positive score.
        if not (sigs.get("ffp_matches") or sigs.get("md5_matches")):
            body_hashes = _extract_hashes(scan_text)
            if body_hashes:
                owners = database.lookup_checksum_owners(body_hashes, db_path=db_path)
                foreign = sorted({
                    lb for lbs in owners.values() for lb in lbs if lb != lb_number
                })
                if foreign and lb_number not in {
                    lb for lbs in owners.values() for lb in lbs
                }:
                    disqualified_foreign += 1
                    logger.info(
                        "wtrf_scraper: LB-%05d disqualifying %s — checksums belong "
                        "to LB entry %s",
                        lb_number, topic_url, foreign,
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
        if disqualified_tag or disqualified_old or disqualified_foreign:
            reasons = []
            if disqualified_tag:
                reasons.append(f"{disqualified_tag} explicitly tagged for a different LB entry")
            if disqualified_foreign:
                reasons.append(
                    f"{disqualified_foreign} carry checksums belonging to a different LB entry"
                )
            if disqualified_old:
                reasons.append(
                    f"{disqualified_old} posted before the {_DOWNLOAD_WINDOW_MONTHS}-month "
                    "download window"
                )
            total = disqualified_tag + disqualified_old + disqualified_foreign
            return _fail(
                "not_found",
                f"All {total} candidate post(s) disqualified: " + "; ".join(reasons),
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
