"""Scraper for TUIT (tangledupintorrents.org), a private Bob Dylan tracker.

TUIT is a Laravel application: login is a POST of a CSRF ``_token`` plus
credentials, after which a session cookie authorises every other page. There is
no JSON API, so the catalogue is read from HTML.

Two surfaces are parsed:

* ``/browse`` — a paginated listing (50 rows/page). Each row already carries
  source type, date, venue, LB number, lineage, format, quality, swarm counts,
  taper and uploader.
* ``/recordings/<id>`` — the detail page, adding the full info hash, size, file
  list, setlist, sibling sources for the same show, the info-file text and the
  spectrogram/preview media URLs.

Politeness: TUIT is a ~21-member private tracker whose ``robots.txt`` blanket-
disallows crawlers (its own comment scopes that to search indexes). Every
request here is separated by ``delay`` seconds and callers are expected to work
in small batches rather than sweeping all ~33 listing pages at once. Nothing in
this module issues concurrent requests against a session.

Credentials come from the OS keyring under ``SERVICE_TUIT`` — never from a file
in the project.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from backend.credentials import SERVICE_TUIT, SERVICE_TUIT_RSS, get_credentials
from backend.wtrf_scraper import _filename_from_content_disposition as _cd_filename

logger = logging.getLogger(__name__)

BASE_URL = "https://tangledupintorrents.org"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
DEFAULT_DELAY = 3.0

# The /rss feed is a rolling window of this many newest uploads. A poll that
# comes back with a full window and no overlap against what we already hold
# cannot prove the window did not roll past unseen uploads — see the
# --rss-backfill-pages fallback in tools/tuit_sync.py.
RSS_WINDOW = 50

_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


# ──────────────────────────────────────────────────────────────────────────────
# Small parsing helpers
# ──────────────────────────────────────────────────────────────────────────────
def _text(node) -> str:
    """Return a node's collapsed text, or '' when the node is None."""
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_size(label: str) -> int | None:
    """Convert a human size label such as '1,006.42 MB' to bytes.

    Args:
        label: Size string as rendered by TUIT.

    Returns:
        Size in bytes, or None when the label cannot be parsed.
    """
    m = re.search(r"([\d,.]+)\s*(TB|GB|MB|KB|B)\b", label or "", re.I)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(value * _SIZE_UNITS[m.group(2).upper()])


def _int_or_none(value: str) -> int | None:
    """Return value parsed as an int with separators stripped, else None."""
    digits = re.sub(r"[^\d-]", "", value or "")
    return int(digits) if digits not in ("", "-") else None


def recording_id_from_url(url: str) -> int | None:
    """Extract the numeric recording id from a /recordings/<id> URL."""
    m = re.search(r"/recordings/(\d+)", url or "")
    return int(m.group(1)) if m else None


# ──────────────────────────────────────────────────────────────────────────────
# Session
# ──────────────────────────────────────────────────────────────────────────────
def get_session(
    username: str = "", password: str = "", delay: float = DEFAULT_DELAY
) -> requests.Session | None:
    """Log in to TUIT and return an authenticated session.

    Args:
        username: TUIT username; read from the keyring when empty.
        password: TUIT password; read from the keyring when empty.
        delay: Seconds to wait between the token fetch and the login POST.

    Returns:
        An authenticated ``requests.Session``, or None when login failed.
    """
    if not username or not password:
        username, password = get_credentials(SERVICE_TUIT)
    if not username or not password:
        logger.warning("TUIT: no credentials stored (keyring service %s)", SERVICE_TUIT)
        return None

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    try:
        page = session.get(f"{BASE_URL}/login", timeout=20)
        page.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("TUIT: cannot reach login page: %s", exc)
        return None

    token = BeautifulSoup(page.text, "html.parser").find(
        "input", attrs={"name": "_token"}
    )
    if not token or not token.get("value"):
        logger.warning("TUIT: no CSRF token on the login page")
        return None

    time.sleep(delay)
    try:
        resp = session.post(
            f"{BASE_URL}/login",
            data={
                "_token": token["value"],
                "username": username,
                "password": password,
                "remember": "on",
            },
            headers={"Referer": f"{BASE_URL}/login"},
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("TUIT: login request failed: %s", exc)
        return None

    if resp.url.rstrip("/").endswith("/login"):
        logger.warning("TUIT: login rejected — check credentials")
        return None
    logger.info("TUIT: logged in as %s", username)
    return session


def _get(
    session: requests.Session, path: str, delay: float
) -> requests.Response | None:
    """Fetch a site-relative path after sleeping ``delay`` seconds.

    Returns None on a transport error or when the session has expired.
    """
    time.sleep(delay)
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    try:
        resp = session.get(url, timeout=30, headers={"Referer": BASE_URL})
    except requests.RequestException as exc:
        logger.warning("TUIT: GET %s failed: %s", path, exc)
        return None
    if resp.url.rstrip("/").endswith("/login"):
        logger.warning("TUIT: session expired while fetching %s", path)
        return None
    if resp.status_code != 200:
        logger.warning("TUIT: GET %s -> HTTP %s", path, resp.status_code)
        return None
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# /browse
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class BrowseRow:
    """One recording as rendered in the /browse listing."""

    rec_id: int | None = None
    detail_url: str = ""
    source_type: str = ""       # AUD / SBD / FM / MTX
    date_str: str = ""
    venue_location: str = ""
    lb_number: int | None = None
    lineage: str = ""
    format: str = ""
    quality: str = ""
    quality_slug: str = ""
    freeleech: bool = False
    seeders: int | None = None
    leechers: int | None = None
    snatched: int | None = None
    taper: str = ""
    uploader: str = ""
    uploader_url: str = ""
    added_at: str = ""          # ISO-8601 from the <time datetime> attribute
    added_label: str = ""       # e.g. "just now"

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return dict(self.__dict__)


_SWARM_RE = re.compile(r"(\d[\d,]*)\s+seeding\D+(\d[\d,]*)\s+leeching"
                       r"(?:\D+(\d[\d,]*)\s+(?:snatched|downloads?))?")
_ADDED_RE = re.compile(r"\((\d{1,2}) (\w{3}) (\d{4}), (\d{1,2}):(\d{2})\)\s*by\s+(\S+)")


def _lb_from(text: str) -> int | None:
    """Return the N of an 'LB-N' label, or None ('none', 'No LB number yet')."""
    m = re.search(r"LB-(\d+)", text or "")
    return int(m.group(1)) if m else None


def _swarm(title: str) -> tuple[int | None, int | None, int | None]:
    """Parse '2 seeding · 0 leeching · 2 snatched' into (seeders, leechers, snatched)."""
    m = _SWARM_RE.search(title or "")
    if not m:
        return None, None, None
    return tuple(_int_or_none(g) if g else None for g in m.groups())  # type: ignore[return-value]


def _added(title: str) -> tuple[str, str, str]:
    """Parse the browse date cell's title into (added_at ISO UTC, label, uploader).

    The title reads 'Added 7 h ago (26 Nov 2026, 19:37) by tabby'; the site
    renders the bracketed time in UTC (it matched the old ``datetime`` attribute).
    """
    m = _ADDED_RE.search(title or "")
    if not m or m.group(2) not in _MONTHS:
        return "", "", ""
    day, mon, year, hh, mm, who = m.groups()
    iso = (f"{int(year):04d}-{_MONTHS[mon]:02d}-{int(day):02d}"
           f"T{int(hh):02d}:{mm}:00+00:00")
    label = re.sub(r"^Added\s+", "", title.split("(")[0]).strip()
    return iso, label, who


def parse_browse(html: str) -> list[BrowseRow]:
    """Parse a /browse listing page into rows.

    The listing (redesigned 2026-11-25) groups recordings by show: a ``.bx-row``
    per show's newest recording, followed by ``.bx-row.is-sub`` rows for its
    other recordings. Sub rows leave the date cell blank and name the recording
    by its equipment, so their date comes from the download link's label.

    Args:
        html: Raw HTML of a listing page.

    Returns:
        One BrowseRow per ``.bx-row``, in page order.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[BrowseRow] = []

    for el in soup.select(".bx-row"):
        row = BrowseRow()
        link = el.select_one("a.bx-link")
        if link and link.get("href"):
            row.detail_url = link["href"]
            row.rec_id = recording_id_from_url(row.detail_url)
        row.source_type = _text(el.select_one(".bx-src .bx-tag")).upper()
        dt = el.select_one(".bx-dt")
        row.date_str = _text(dt)
        if not row.date_str:
            dl = el.select_one("a.bx-dl")
            m = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", (dl.get("aria-label") or "") if dl else "")
            row.date_str = m.group(1) if m else ""
        name = el.select_one(".bx-nm")
        row.venue_location = (name.get("title") or "").strip() if name else ""
        if "is-sub" in (el.get("class") or []):
            row.lineage = _text(link)
        row.lb_number = _lb_from(_text(el.select_one(".bx-lb")))
        row.taper = _text(el.select_one(".bx-tp"))
        peers = el.select_one(".bx-peers")
        row.seeders, row.leechers, row.snatched = _swarm(
            (peers.get("title") or "") if peers else "")
        row.added_at, row.added_label, row.uploader = _added(
            (dt.get("title") or "") if dt else "")
        if row.uploader:
            row.uploader_url = f"{BASE_URL}/profile/{row.uploader}"
        rows.append(row)

    return rows


def browse_total(html: str) -> int | None:
    """Return the catalogue size: the count beside the nav's 'Browse' link."""
    m = re.search(r'class="lbl">\s*Browse\s*</span>\s*<span class="n[^"]*">\s*([\d,]+)',
                  html or "")
    return _int_or_none(m.group(1)) if m else None


def fetch_browse_page(
    session: requests.Session,
    page: int = 1,
    sort: str = "newest",
    delay: float = DEFAULT_DELAY,
    extra: dict | None = None,
) -> tuple[list[BrowseRow], int | None, str]:
    """Fetch and parse one /browse page.

    Args:
        session: Authenticated session.
        page: 1-based page number.
        sort: Sort key accepted by the site (e.g. 'newest').
        delay: Seconds to sleep before the request.
        extra: Additional query parameters (e.g. ``{"source": "sbd"}``).

    Returns:
        (rows, total_recordings, raw_html). ``rows`` is empty when the fetch
        failed.
    """
    params = {"sort": sort, "page": str(page)}
    params.update(extra or {})
    resp = _get(session, f"/browse?{urlencode(params)}", delay)
    if resp is None:
        return [], None, ""
    return parse_browse(resp.text), browse_total(resp.text), resp.text


# ──────────────────────────────────────────────────────────────────────────────
# /recordings/<id>
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Recording:
    """Everything the detail page exposes about one recording."""

    rec_id: int | None = None
    detail_url: str = ""
    show_id: int | None = None
    lb_number: int | None = None
    title: str = ""             # 'Providence, Civic Center'
    eyebrow: str = ""           # '7 Oct 1978 · Street Legal Tour · Audience'
    date_str: str = ""
    venue: str = ""
    location: str = ""
    tour: str = ""
    source_type: str = ""       # AUD / SBD / FM / MTX
    source_label: str = ""      # 'Audience', 'Soundboard', …
    format: str = ""
    quality: str = ""
    quality_slug: str = ""
    info_hash: str = ""
    size_label: str = ""
    size_bytes: int | None = None
    n_files: int | None = None
    n_sources: int | None = None
    seeders: int | None = None
    leechers: int | None = None
    snatched: int | None = None
    freeleech: bool = False
    lb_verified: bool = False
    taper: str = ""
    uploader: str = ""
    uploaded_label: str = ""
    headline: str = ""          # 'Source 1 of 2 circulating…' blurb
    lineage: str = ""
    lineage_nodes: list[str] = field(default_factory=list)
    info_text: str = ""
    setlist: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    siblings: list[dict] = field(default_factory=list)
    spectrogram_url: str = ""
    preview_url: str = ""
    torrent_url: str = ""

    def as_dict(self) -> dict:
        """Return the recording as a plain dict."""
        return dict(self.__dict__)


_FORMAT_RE = re.compile(r"^(FLAC|SHN|WAV|ALAC|APE|DSD|MP3|AAC|OGG)\b", re.I)


def _day_to_iso(label: str) -> str:
    """Convert '2 Nov 1992' to '1992-11-02'; return '' when it does not parse."""
    m = re.match(r"(\d{1,2})\s+(\w{3})\w*\s+(\d{4})$", (label or "").strip())
    if not m or m.group(2)[:3].title() not in _MONTHS:
        return ""
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(2)[:3].title()]:02d}-{int(m.group(1)):02d}"


def _facts(soup: BeautifulSoup) -> dict[str, str]:
    """Return {dt label (lower): dd text} for the page's first ``dl.rc-facts``."""
    dl = soup.select_one("dl.rc-facts")
    out: dict[str, str] = {}
    for div in dl.find_all("div", recursive=False) if dl else []:
        label = _text(div.find("dt")).lower()
        if label:
            out[label] = _text(div.find("dd"))
    return out


def _sibling(row) -> dict:
    """Return one 'Recordings of this show' row as a sibling dict."""
    link = row.select_one("a.rc-link")
    href = (link.get("href") or "") if link else ""
    name = row.select_one(".rc-nm")
    bold = name.find("b") if name else None
    note = bold.find_next_sibling("span") if bold else None
    sizes = row.select(".bx-sz")
    done = next((s for s in sizes if "completed" in (s.get("title") or "")), None)
    size = next((s for s in sizes if s is not done), None)
    return {
        "title": _text(bold),
        "note": _text(note),
        "source_type": _text(row.select_one(".bx-src .bx-tag")).upper(),
        "url": href,
        "rec_id": recording_id_from_url(href),
        "is_current": "cur" in (row.get("class") or []),
        "lb_number": _lb_from(_text(row.select_one(".bx-lb"))),
        "size_label": _text(size),
        "seeders": _int_or_none(_text(row.select_one(".bx-mn"))),
        "snatched": _int_or_none(_text(done)),
        "lb_match": any("lossless bob match" in _text(p).lower()
                        for p in row.select(".rc-pill")),
    }


def parse_recording(html: str, rec_id: int | None = None) -> Recording:
    """Parse a /recordings/<id> detail page (layout of 2026-11-25).

    The hero holds date, the 'Venue, City, Country' heading and a stats strip
    (source, LB, format, size, swarm); lineage, facts, info file, setlist, files
    and the show's other recordings sit in ``rc-*`` sections below. The page no
    longer splits venue from location, so the heading is split at its first
    comma — :func:`merge_row_into_recording` keeps that split, and the browse
    row only fills blanks.

    Args:
        html: Raw HTML of the detail page.
        rec_id: Known recording id; otherwise read from the page.

    Returns:
        A populated Recording. Missing sections simply stay at their defaults.
    """
    soup = BeautifulSoup(html, "html.parser")
    rec = Recording(rec_id=rec_id)

    if rec.rec_id is None:
        node = soup.select_one("input[name=recording_id]")
        if node:
            rec.rec_id = _int_or_none(node.get("value", ""))
    if rec.rec_id is not None:
        rec.detail_url = f"{BASE_URL}/recordings/{rec.rec_id}"

    hero = soup.select_one(".rc-hero")
    if hero:
        day = _text(hero.select_one(".rc-date"))
        rec.date_str = _day_to_iso(day)
        rec.title = _text(hero.find("h1"))
        venue, _, location = rec.title.partition(", ")
        rec.venue, rec.location = venue.strip(), location.strip()
        for span in hero.select(".rc-stats > span"):
            text = _text(span)
            tag = span.select_one(".bx-tag")
            if tag:
                rec.source_type = _text(tag).upper()
                rec.source_label = text.removeprefix(_text(tag)).strip()
            elif "seeding" in text:
                rec.seeders, rec.leechers, _ = _swarm(text)
            elif re.fullmatch(r"[\d,]+ downloads?", text):
                rec.snatched = _int_or_none(text)
            elif "LB" in text:
                rec.lb_number = _lb_from(text)
            elif _FORMAT_RE.match(text):
                rec.format = text
            elif parse_size(text) is not None:
                rec.size_label = text
        for pill in hero.select(".rc-pill"):
            if pill.get("data-q"):
                rec.quality = _text(pill)
                rec.quality_slug = pill.get("data-q", "")
            elif _text(pill).lower() == "freeleech":
                rec.freeleech = True
            elif "lossless bob" in _text(pill).lower():
                rec.lb_verified = True

    crumb = soup.find("a", class_="rc-crumb", href=re.compile(r"/browse\?q="))
    rec.tour = _text(crumb)
    rec.eyebrow = " · ".join(x for x in (_text(hero.select_one(".rc-date")) if hero else "",
                                        rec.tour, rec.source_label) if x)

    m = re.search(r"info hash\s+([0-9a-f]{40})", _text(soup.select_one(".rc-hash")), re.I)
    rec.info_hash = m.group(1).lower() if m else ""

    rec.taper = _facts(soup).get("taper", "")
    up = soup.select_one(".rc-up a.rl-member")
    rec.uploader = _text(up)
    rec.uploaded_label = _text(soup.select_one(".rc-up small")).removeprefix("uploaded ").strip()

    rec.lineage_nodes = [_text(li) for li in soup.select(".rc-steps > li")]
    rec.lineage = " > ".join(rec.lineage_nodes)

    nfo = soup.select_one("pre.rc-nfo")
    if nfo:
        rec.info_text = nfo.get_text().strip()

    for item in soup.select(".rc-setlist .rc-tr.sl"):
        song = item.find("a", href=True)
        rec.setlist.append({
            "track": _text(item.select_one(".n")),
            "song": _text(song),
            # Stored relative and '+'-encoded, as the old layout rendered it.
            "song_url": ((song.get("href") or "").removeprefix(BASE_URL).replace("%20", "+")
                         if song else ""),
        })

    for frow in soup.select("#rcPane-files .rc-tr"):
        size_label = _text(frow.select_one(".m"))
        rec.files.append({
            "name": _text(frow.select_one(".nm")),
            "size_label": size_label,
            "size_bytes": parse_size(size_label),
        })
    if rec.files:
        rec.n_files = len(rec.files)
        # The hero rounds ('580 MB'); the file list sums to the real size.
        sizes = [f["size_bytes"] for f in rec.files]
        if all(s is not None for s in sizes):
            rec.size_bytes = sum(sizes)
    if rec.size_bytes is None:
        rec.size_bytes = parse_size(rec.size_label)

    rec.siblings = [_sibling(r) for r in soup.select(".rc-list .rc-row")]
    if rec.siblings:
        rec.n_sources = len(rec.siblings)
        others = len(rec.siblings) - 1
        rec.headline = (f"{len(rec.siblings)} recordings of this show" if others
                        else "The only source for this show")
    current = next((s for s in rec.siblings if s["is_current"]), None)
    if current and current["lb_number"] and not rec.lb_number:
        rec.lb_number = current["lb_number"]

    for url in re.findall(r'(?:src|href|data-audio)="([^"]+)"', html):
        if "/storage/spectrograms/" in url and not rec.spectrogram_url:
            rec.spectrogram_url = url.split("?")[0]  # drop the ?v= cache-buster
        elif "/storage/samples/" in url and not rec.preview_url:
            rec.preview_url = url

    dl = soup.find("a", href=re.compile(r"/show/\d+/download"))
    if dl:
        rec.torrent_url = dl["href"]
        m = re.search(r"/show/(\d+)/download", rec.torrent_url)
        if m:
            rec.show_id = int(m.group(1))

    return rec


def save_recording_html(html: str, rec_id: int, html_dir: str | Path) -> Path | None:
    """Write the raw detail-page HTML to ``<html_dir>/rec-<id>.html``.

    The parsed fields in the DB are lossy — anything the parser does not yet
    read (new page sections, changed markup) is only recoverable from the page
    itself, and re-fetching costs another hit on a 21-member private tracker.

    Args:
        html: Raw HTML of the detail page.
        rec_id: Site recording id, used for the filename.
        html_dir: Directory to write into; created if missing.

    Returns:
        The path written, or None when the write failed.
    """
    try:
        target = Path(html_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"rec-{rec_id}.html"
        path.write_text(html, encoding="utf-8")
        return path
    except OSError as exc:
        logger.warning("could not save detail HTML for rec %s: %s", rec_id, exc)
        return None


def fetch_recording(
    session: requests.Session,
    rec_id: int,
    delay: float = DEFAULT_DELAY,
    html_dir: str | Path | None = None,
) -> Recording | None:
    """Fetch and parse one recording detail page.

    Args:
        session: Authenticated session.
        rec_id: Site recording id.
        delay: Seconds to sleep before the request.
        html_dir: When given, the raw page is also archived there as
            ``rec-<id>.html``. A failed write is logged, not raised.

    Returns:
        A Recording, or None when the page could not be fetched.
    """
    resp = _get(session, f"/recordings/{rec_id}", delay)
    if resp is None:
        return None
    if html_dir is not None:
        save_recording_html(resp.text, rec_id, html_dir)
    return parse_recording(resp.text, rec_id=rec_id)


def merge_row_into_recording(rec: Recording, row: BrowseRow) -> Recording:
    """Fill blank Recording fields from the listing row that led to it.

    The listing carries a taper name and the freeleech flag more reliably than
    the detail page, so those are treated as authoritative when non-empty.

    Args:
        rec: Recording parsed from the detail page (mutated in place).
        row: The browse row for the same recording.

    Returns:
        The same Recording instance.
    """
    if row.taper:
        rec.taper = row.taper
    if row.uploader and not rec.uploader:
        rec.uploader = row.uploader
    if row.lb_number and not rec.lb_number:
        rec.lb_number = row.lb_number
    if row.lineage and not rec.lineage:
        rec.lineage = row.lineage
    if row.quality and not rec.quality:
        rec.quality = row.quality
        rec.quality_slug = row.quality_slug
    rec.freeleech = rec.freeleech or row.freeleech
    for attr in ("seeders", "leechers", "snatched"):
        if getattr(rec, attr) is None:
            setattr(rec, attr, getattr(row, attr))
    return rec


# ──────────────────────────────────────────────────────────────────────────────
# .torrent download
# ──────────────────────────────────────────────────────────────────────────────
def _filename_from_content_disposition(header: str) -> str | None:
    """Return the filename in a Content-Disposition header, made path-safe.

    Parsing (plain and RFC 5987 ``filename*`` forms) is shared with the WTRF
    scraper so the two never drift; only the character sanitising is local.
    """
    name = _cd_filename(header or "")
    if not name:
        return None
    return re.sub(r"[^\w.\-+() ]", "_", name.strip()) or None


def _unique_torrent_path(
    dest: Path, name: str, body: bytes, rec_id: int | None
) -> Path:
    """Return a path for ``body`` that will not overwrite a different torrent.

    The tracker's Content-Disposition filename is just the torrent's root
    folder name, which is not unique across the site — ``track.torrent``,
    ``FLAC.torrent`` and ``1.torrent`` are each claimed by several unrelated
    recordings. Writing them all to one path leaves the last one standing, so
    the seeder later pairs a torrent with another show's audio. Identical bytes
    still reuse the path, keeping a re-download idempotent and leaving every
    already-saved file exactly where the DB says it is.

    Args:
        dest: Directory the .torrent is written into.
        name: Candidate filename, ``.torrent`` suffix included.
        body: The bytes about to be written.
        rec_id: TUIT recording id, used to disambiguate a real collision.

    Returns:
        The path to write to.
    """
    path = dest / name
    if not path.exists() or rec_id is None:
        return path
    try:
        if path.read_bytes() == body:
            return path
    except OSError:
        return path
    unique = dest / f"{path.stem} [tuit-{rec_id}]{path.suffix}"
    logger.warning(
        "TUIT: %s already holds a different torrent — saving rec %s as %s",
        path.name, rec_id, unique.name,
    )
    return unique


def download_torrent(
    session: requests.Session,
    rec: Recording,
    dest_dir: str | Path,
    delay: float = DEFAULT_DELAY,
) -> dict:
    """Download a recording's personalised .torrent file.

    The tracker embeds the member's passkey in the file, so it must be fetched
    with the authenticated session and never shared.

    Args:
        session: Authenticated session.
        rec: Recording carrying a ``torrent_url`` (or a ``show_id``).
        dest_dir: Directory to write the .torrent into; created if needed.
        delay: Seconds to sleep before the request.

    Returns:
        Dict with ``ok`` (bool) and either ``torrent_path`` or ``error``.
    """
    url = rec.torrent_url or (
        f"{BASE_URL}/show/{rec.show_id}/download" if rec.show_id else ""
    )
    if not url:
        return {"ok": False, "error": "no torrent URL on the recording page"}

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    time.sleep(delay)
    try:
        resp = session.get(
            url, timeout=60, stream=True, headers={"Referer": rec.detail_url or BASE_URL}
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"download failed: {exc}"}

    if resp.status_code != 200:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {url}"}

    body = resp.content
    if not body.startswith(b"d"):  # bencoded dict
        return {"ok": False, "error": "response was not a .torrent (session expired?)"}

    name = _filename_from_content_disposition(
        resp.headers.get("Content-Disposition", "")
    )
    if not name:
        stem = f"LB-{rec.lb_number}" if rec.lb_number else f"tuit-{rec.rec_id}"
        name = f"{stem}.torrent"
    if not name.endswith(".torrent"):
        name += ".torrent"

    path = _unique_torrent_path(dest, name, body, rec.rec_id)
    path.write_bytes(body)
    logger.info("TUIT: saved %s (%d bytes)", path, len(body))
    return {"ok": True, "torrent_path": str(path)}


def recording_to_json_fields(rec: Recording) -> dict:
    """Return the JSON-encoded list fields used by the ``tuit_recordings`` table."""
    return {
        "lineage_json": json.dumps(rec.lineage_nodes, ensure_ascii=False),
        "setlist_json": json.dumps(rec.setlist, ensure_ascii=False),
        "files_json": json.dumps(rec.files, ensure_ascii=False),
        "siblings_json": json.dumps(rec.siblings, ensure_ascii=False),
    }


# ──────────────────────────────────────────────────────────────────────────────
# /tour — the site's live history (every known show, circulating or not)
# ──────────────────────────────────────────────────────────────────────────────
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}


@dataclass
class TourShow:
    """One show row on a ``/tour/<name>`` page.

    The tour pages are the site's concert spine: every show Dylan is known to
    have played, whether or not a recording circulates. A row links to
    ``/recordings/<id>`` when a tape exists and to ``/shows/<id>`` when it does
    not, which is exactly the circulating/gap distinction.
    """

    tour: str = ""
    date_str: str = ""          # ISO 'YYYY-MM-DD'
    venue: str = ""
    location: str = ""
    row_url: str = ""
    rec_id: int | None = None   # top recording, when one circulates
    show_id: int | None = None  # set only on gap rows, which link to /shows
    circulating: bool = False
    in_collection: bool = False  # the ✓ "In your collection" marker
    has_sbd: bool = False
    has_aud: bool = False
    seeders: int | None = None

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return dict(self.__dict__)


def parse_tour_index(html: str) -> list[dict]:
    """Parse ``/tour`` into one dict per named tour.

    Args:
        html: Raw HTML of the tour index.

    Returns:
        List of ``{'name', 'url'}`` dicts in page order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    tours: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/tour/" not in href or href in seen:
            continue
        seen.add(href)
        tours.append({"name": tour_name_from_url(href), "url": href})
    return tours


def tour_name_from_url(url: str) -> str:
    """Return the tour name encoded in a ``/tour/<name>`` URL."""
    from urllib.parse import unquote

    return unquote(url.rstrip("/").split("/tour/", 1)[-1]) if "/tour/" in url else ""


def parse_tour_page(html: str, tour: str = "") -> list[TourShow]:
    """Parse one ``/tour/<name>`` page into show rows (layout of 2026-11-25).

    Each show is an ``a.rc-tr.sh-g`` row carrying a full ISO date; ``data-has``
    says whether a recording circulates, and the href points at
    ``/recordings/<id>`` (a tape) or ``/shows/<id>`` (a gap).

    Args:
        html: Raw HTML of a tour page.
        tour: Tour name to stamp on each row; falls back to the page heading.

    Returns:
        List of :class:`TourShow`, in page order. Rows with an unparseable
        date are skipped.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    if not tour:
        tour = _text(soup.find("h1"))

    shows: list[TourShow] = []
    for node in soup.select("a.rc-tr.sh-g"):
        date = _text(node.select_one(".m"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue
        name = node.select_one(".sh-nm")
        bold = name.find("b") if name else None
        place = bold.find_next_sibling("span") if bold else None
        tags = node.select_one(".sh-tags")
        href = node.get("href", "")
        row = TourShow(
            tour=tour,
            date_str=date,
            venue=_text(bold),
            location=_text(place),
            row_url=href,
            circulating=node.get("data-has") == "1",
            in_collection=bool(tags and tags.select_one(".sh-own")),
            has_sbd=bool(tags and tags.select_one(".bx-tag.sbd")),
            has_aud=bool(tags and tags.select_one(".bx-tag.aud")),
            seeders=_int_or_none(_text(node.select_one(".sh-sd")))
            if node.select_one(".sh-sd") and _text(node.select_one(".sh-sd")) else None,
        )
        if "/recordings/" in href:
            row.rec_id = recording_id_from_url(href)
        elif "/shows/" in href:
            row.show_id = _int_or_none(href.rstrip("/").rsplit("/", 1)[-1])
        shows.append(row)

    return shows


def fetch_tour_shows(
    session: requests.Session, delay: float = DEFAULT_DELAY
) -> list[TourShow]:
    """Fetch ``/tour`` and every tour page it lists.

    46 requests at ``delay`` seconds apart — the whole concert spine costs one
    slow pass, so callers should sync it on demand, not per session.

    Args:
        session: Authenticated session.
        delay: Seconds to sleep before each request.

    Returns:
        Every show row across all tours; empty when the index fetch failed.
    """
    resp = _get(session, "/tour", delay)
    if resp is None:
        return []

    shows: list[TourShow] = []
    for tour in parse_tour_index(resp.text):
        page = _get(session, tour["url"], delay)
        if page is None:
            continue
        rows = parse_tour_page(page.text, tour_name_from_url(tour["url"]))
        logger.info("TUIT tour %s: %d show(s)", tour["name"], len(rows))
        shows.extend(rows)
    return shows


# ──────────────────────────────────────────────────────────────────────────────
# /venue — the site's venue register
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class TuitVenue:
    """One row of the paginated ``/venue`` register."""

    venue: str = ""
    city: str = ""
    country: str = ""
    year_first: int | None = None
    year_last: int | None = None
    n_shows: int | None = None
    venue_url: str = ""

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return dict(self.__dict__)


def venue_page_count(html: str) -> int:
    """Return the 'page 1 of 46' page total, or 1 when absent."""
    m = re.search(r"page\s+\d+\s+of\s+([\d,]+)", html or "", re.I)
    return _int_or_none(m.group(1)) or 1 if m else 1


def parse_venue_page(html: str) -> list[TuitVenue]:
    """Parse one ``/venue`` listing page into venue rows (layout of 2026-11-25).

    Args:
        html: Raw HTML of a venue listing page.

    Returns:
        List of :class:`TuitVenue` in page order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[TuitVenue] = []
    for tr in soup.select(".rc-tr.sh-vn"):
        name = tr.select_one(".sh-nm")
        link = name.find("a", href=True) if name else None
        if link is None:
            continue
        city = link.find_next_sibling("span")
        cells = tr.select(".m")
        years = re.findall(r"\d{4}", _text(cells[0])) if cells else []
        rows.append(
            TuitVenue(
                venue=_text(link),
                city=_text(city),
                country=_text(tr.select_one(".sh-c")),
                year_first=_int_or_none(years[0]) if years else None,
                year_last=_int_or_none(years[-1]) if years else None,
                n_shows=_int_or_none(_text(cells[-1])) if len(cells) > 1 else None,
                venue_url=link["href"],
            )
        )
    return rows


def fetch_venues(
    session: requests.Session, delay: float = DEFAULT_DELAY, max_pages: int = 0
) -> list[TuitVenue]:
    """Fetch every page of the ``/venue`` register.

    Args:
        session: Authenticated session.
        delay: Seconds to sleep before each request.
        max_pages: Stop after this many pages; 0 means all of them.

    Returns:
        Every venue row; empty when the first fetch failed.
    """
    resp = _get(session, "/venue", delay)
    if resp is None:
        return []

    total = venue_page_count(resp.text)
    if max_pages:
        total = min(total, max_pages)
    venues = parse_venue_page(resp.text)
    for page in range(2, total + 1):
        nxt = _get(session, f"/venue?page={page}", delay)
        if nxt is None:
            break
        venues.extend(parse_venue_page(nxt.text))
    logger.info("TUIT venues: %d row(s) over %d page(s)", len(venues), total)
    return venues


# ──────────────────────────────────────────────────────────────────────────────
# /songs and /song/<title> — the songbook and per-song performance history
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class TuitSong:
    """One row of the ``/songs`` songbook index."""

    song: str = ""
    song_url: str = ""
    n_performances: int | None = None   # the index's own count
    year_first: int | None = None
    year_last: int | None = None

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return dict(self.__dict__)


@dataclass
class TuitSongPerformance:
    """One performance row on a ``/song/<title>`` page."""

    song: str = ""
    date_str: str = ""          # ISO 'YYYY-MM-DD'
    venue_text: str = ""        # 'Venue — City, Country' as rendered
    show_id: int | None = None
    n_sources: int | None = None  # the row's 'N src' tag, absent when uncirculated
    is_encore: bool = False
    note: str = ""              # e.g. 'Bob on electric keyboard'

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return dict(self.__dict__)


def parse_songs_index(html: str) -> list[TuitSong]:
    """Parse one ``/songs`` listing page into songbook rows (layout of 2026-11-25).

    Args:
        html: Raw HTML of a songs listing page.

    Returns:
        List of :class:`TuitSong` in page order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[TuitSong] = []
    for tr in soup.select(".rc-tr.sg-g"):
        link = tr.select_one(".nm a[href]")
        if link is None or "/song/" not in link["href"]:
            continue
        title = _text(link)
        years = tr.select(".m.r")
        rows.append(
            TuitSong(
                song=title,
                song_url=song_url_for(title),
                n_performances=_int_or_none(_text(tr.select_one(".sg-bar .m"))),
                year_first=_int_or_none(_text(years[0])) if years else None,
                year_last=_int_or_none(_text(years[-1])) if len(years) > 1 else None,
            )
        )
    return rows


def song_url_for(title: str) -> str:
    """Return the ``/song/<title>`` URL for a song, fully percent-encoded.

    The site's own hrefs escape spaces but leave ``#``, ``?`` and ``/`` raw, so
    following them verbatim silently requests the wrong page — ``#`` truncates
    at the fragment, ``?`` starts a query string and ``/`` adds a path segment.
    That cost 26 songs ("Rainy Day Women #12 & 35", "What Good Am I?",
    "The Market Town/Scatter The Mud") on the first sweep, each returning a page
    with no performance rows rather than an error.

    Args:
        title: Song title exactly as the site renders it.

    Returns:
        Absolute URL to the song's page.
    """
    from urllib.parse import quote

    return f"{BASE_URL}/song/{quote(title, safe='')}"


def songs_page_count(html: str) -> int:
    """Return the 'page 1 of 17' page total, or 1 when absent."""
    m = (re.search(r"page\s+\d+\s+of\s+([\d,]+)", html or "", re.I)
         or re.search(r"\d+\s+of\s+([\d,]+)\s+pages", html or ""))
    return _int_or_none(m.group(1)) or 1 if m else 1


def parse_song_page(html: str, song: str = "") -> list[TuitSongPerformance]:
    """Parse one ``/song/<title>`` page into performance rows (layout of 2026-11-25).

    Every decade's ``<details>`` is present in the HTML, so one fetch yields
    the song's full history. Each ``.sg-pf`` row links the show; ``is-bare``
    rows have no recording, and a ``.sg-more`` chip ('+1') counts the show's
    other recordings. The layout no longer marks encores, so ``is_encore`` is
    always False here (the DB keeps earlier markers — see
    ``upsert_tuit_song_performances``).

    Args:
        html: Raw HTML of a song page.
        song: Song title to stamp on each row; falls back to the page heading.

    Returns:
        List of :class:`TuitSongPerformance` in page order (newest first).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    if not song:
        song = _text(soup.find("h1"))

    rows: list[TuitSongPerformance] = []
    for node in soup.select(".sg-pf"):
        date_iso = _text(node.select_one(".bx-dt"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_iso):
            continue
        link = node.select_one("a.bx-link")
        bold = link.find("b") if link else None
        place = link.select_one(".pl") if link else None
        if place and place.select_one(".mdt"):
            place.select_one(".mdt").extract()
        venue_text = " — ".join(x for x in (_text(bold), _text(place)) if x)
        href = (link.get("href") or "") if link else ""
        n_sources = None
        if "is-bare" not in (node.get("class") or []):
            more = node.select_one(".sg-more")
            m = re.search(r"(\d+)\s+recordings?", (more.get("title") or "") if more else "")
            n_sources = int(m.group(1)) if m else 1
        rows.append(
            TuitSongPerformance(
                song=song,
                date_str=date_iso,
                venue_text=venue_text,
                show_id=(_int_or_none(href.rstrip("/").rsplit("/", 1)[-1])
                         if "/shows/" in href else None),
                n_sources=n_sources,
                note=_text(node.select_one(".sg-pf-note")),
            )
        )
    return rows


def _parse_long_date(label: str) -> str:
    """Convert 'Jun 23, 2026' to '2026-06-23'; return '' when unparseable."""
    m = re.match(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})", (label or "").strip())
    if not m or m.group(1) not in _MONTHS:
        return ""
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def fetch_songs(
    session: requests.Session, delay: float = DEFAULT_DELAY, max_pages: int = 0
) -> list[TuitSong]:
    """Fetch the ``/songs`` songbook index.

    Paged with ``sort=alpha``: the default ``sort=plays`` has no tiebreak, so
    songs sharing a performance count drift between pages the way the /venue
    register does. Alphabetical order is unique, so the sweep is complete.

    Args:
        session: Authenticated session.
        delay: Seconds to sleep before each request.
        max_pages: Stop after this many pages; 0 means all of them.

    Returns:
        Every songbook row; empty when the first fetch failed.
    """
    resp = _get(session, "/songs?sort=alpha", delay)
    if resp is None:
        return []

    total = songs_page_count(resp.text)
    if max_pages:
        total = min(total, max_pages)
    songs = parse_songs_index(resp.text)
    for page in range(2, total + 1):
        nxt = _get(session, f"/songs?sort=alpha&page={page}", delay)
        if nxt is None:
            break
        songs.extend(parse_songs_index(nxt.text))
    logger.info("TUIT songbook: %d song(s) over %d page(s)", len(songs), total)
    return songs


def fetch_song_performances(
    session: requests.Session, song: TuitSong, delay: float = DEFAULT_DELAY
) -> list[TuitSongPerformance]:
    """Fetch one song's full performance history.

    Args:
        session: Authenticated session.
        song: A row from :func:`fetch_songs`.
        delay: Seconds to sleep before the request.

    Returns:
        The song's performance rows, or an empty list on a failed fetch.
    """
    resp = _get(session, song.song_url or song_url_for(song.song), delay)
    if resp is None:
        return []
    return parse_song_page(resp.text, song.song)


# ──────────────────────────────────────────────────────────────────────────────
# /rss/<passkey> — the new-uploads feed
# ──────────────────────────────────────────────────────────────────────────────
_RSS_GUID_RE = re.compile(r"tuit-rec-(\d+)")


@dataclass
class RssItem:
    """One entry in TUIT's new-uploads feed.

    The feed is the cheapest discovery surface the tracker has: it needs no
    login, answers in one request, and names the recording id outright, so a
    sync can fetch detail pages only for ids it has not seen.
    """

    rec_id: int | None = None
    title: str = ""
    detail_url: str = ""
    pub_date: str = ""          # RFC-822, as published
    description: str = ""       # 'Tokyo, Japan · taped by Spot · FLAC 16/44'
    torrent_url: str = ""       # passkey-bearing enclosure — treat as a secret
    size_bytes: int | None = None
    taper: str = ""             # from 'taped by …' in the description

    def as_dict(self) -> dict:
        """Return the item as a plain dict."""
        return dict(self.__dict__)

    def as_browse_row(self) -> BrowseRow:
        """Return the item as the sparse listing row it stands in for.

        The detail page carries no taper at all — only the listing and this
        feed name one — so a recording discovered through the feed has to
        merge its taper from here or it is stored without one.
        """
        return BrowseRow(
            rec_id=self.rec_id,
            detail_url=self.detail_url,
            taper=self.taper,
            added_at=_rfc822_to_iso(self.pub_date),
        )


_TAPED_BY_RE = re.compile(r"taped by\s+(.+?)(?:\s+·|\s*$)", re.IGNORECASE)


def _rfc822_to_iso(pub_date: str) -> str:
    """Convert an RSS ``pubDate`` to ISO-8601, or '' when unparseable."""
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(pub_date).isoformat() if pub_date else ""
    except (TypeError, ValueError):
        return ""


def rss_url(passkey: str) -> str:
    """Return the feed URL for a passkey.

    Args:
        passkey: The account's RSS passkey.

    Returns:
        Absolute feed URL.
    """
    return f"{BASE_URL}/rss/{passkey}"


def redact_passkey(text: str, passkey: str) -> str:
    """Blank a passkey out of ``text`` so it never reaches a log or a report.

    Args:
        text: Text that may embed the passkey.
        passkey: The secret to remove.

    Returns:
        ``text`` with every occurrence replaced by ``<passkey>``.
    """
    return text.replace(passkey, "<passkey>") if passkey else text


def parse_rss(xml: str) -> list[RssItem]:
    """Parse the new-uploads feed into items, newest first.

    Args:
        xml: Raw feed body.

    Returns:
        List of :class:`RssItem`. Items whose guid carries no recording id are
        kept with ``rec_id`` None rather than dropped, so a feed-format change
        is visible to the caller instead of silently halving the queue.
    """
    soup = BeautifulSoup(xml or "", "xml")
    items: list[RssItem] = []
    for node in soup.find_all("item"):
        guid = _text(node.find("guid"))
        link = _text(node.find("link"))
        enclosure = node.find("enclosure")
        rec_id = None
        m = _RSS_GUID_RE.search(guid)
        if m:
            rec_id = _int_or_none(m.group(1))
        elif link:
            rec_id = recording_id_from_url(link)
        description = _text(node.find("description"))
        taped = _TAPED_BY_RE.search(description)
        items.append(
            RssItem(
                rec_id=rec_id,
                title=_text(node.find("title")),
                detail_url=link,
                pub_date=_text(node.find("pubDate")),
                description=description,
                taper=taped.group(1).strip() if taped else "",
                torrent_url=enclosure.get("url", "") if enclosure else "",
                size_bytes=(
                    _int_or_none(enclosure.get("length", "")) if enclosure else None
                ),
            )
        )
    return items


def fetch_rss(
    passkey: str = "", delay: float = DEFAULT_DELAY
) -> list[RssItem]:
    """Fetch and parse the new-uploads feed.

    No session is involved: the passkey in the URL is the whole authorisation,
    which is why it is stored in the keyring under ``SERVICE_TUIT_RSS`` and
    never written to a log. The feed is a rolling window of the newest 50
    uploads, so a poll interval long enough to let 50 recordings accumulate
    will miss some — fall back to ``/browse`` paging after a long gap.

    Args:
        passkey: RSS passkey; read from the keyring when empty.
        delay: Seconds to sleep before the request.

    Returns:
        Feed items newest first, or an empty list when the fetch failed or no
        passkey is stored.
    """
    if not passkey:
        _user, passkey = get_credentials(SERVICE_TUIT_RSS)
    if not passkey:
        logger.warning(
            "TUIT: no RSS passkey stored (keyring service %s)", SERVICE_TUIT_RSS
        )
        return []

    time.sleep(delay)
    try:
        resp = requests.get(
            rss_url(passkey), timeout=30, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("TUIT: RSS fetch failed: %s", redact_passkey(str(exc), passkey))
        return []

    items = parse_rss(resp.text)
    logger.info("TUIT RSS: %d item(s)", len(items))
    return items
