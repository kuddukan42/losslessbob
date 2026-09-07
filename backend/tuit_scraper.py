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

import requests
from bs4 import BeautifulSoup

from backend.credentials import SERVICE_TUIT, SERVICE_TUIT_RSS, get_credentials

logger = logging.getLogger(__name__)

BASE_URL = "https://tangledupintorrents.org"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
DEFAULT_DELAY = 3.0

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


def parse_browse(html: str) -> list[BrowseRow]:
    """Parse a /browse listing page into rows.

    Args:
        html: Raw HTML of a listing page.

    Returns:
        One BrowseRow per ``article.source-row``, in page order.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[BrowseRow] = []

    for art in soup.select("article.source-row"):
        row = BrowseRow()
        row.source_type = _text(art.select_one(".src-pill")).upper()

        link = art.select_one("a.row-title-link")
        if link and link.get("href"):
            row.detail_url = link["href"]
            row.rec_id = recording_id_from_url(row.detail_url)

        row.date_str = _text(art.select_one(".row-date"))
        row.venue_location = _text(art.select_one(".row-venue"))
        row.freeleech = art.select_one(".free-tag") is not None

        sub = _text(art.select_one(".row-sub"))
        m = re.match(r"LB-(\d+)\s*·\s*(.*)$", sub)
        if m:
            row.lb_number = int(m.group(1))
            row.lineage = m.group(2).strip()
        else:
            row.lineage = sub

        row.format = _text(art.select_one(".format-cell"))
        qual = art.select_one(".quality-cell")
        row.quality = _text(qual)
        row.quality_slug = (qual.get("data-q") or "") if qual else ""

        for kind, attr in (("seed", "seeders"), ("leech", "leechers"),
                           ("snatch", "snatched")):
            cell = art.select_one(f".metric.{kind}")
            if cell:
                # The visible number is the cell's own text minus the sr-only label.
                sr = cell.select_one(".sr-only")
                if sr:
                    sr.extract()
                setattr(row, attr, _int_or_none(_text(cell)))

        taper = art.select_one(".taper-cell .taper-name")
        row.taper = _text(taper)

        up = art.select_one(".uploader-cell a.uploader-link")
        if up:
            row.uploader = _text(up)
            row.uploader_url = up.get("href", "")

        added = art.select_one("time.added-date")
        if added:
            row.added_at = added.get("datetime", "")
            row.added_label = _text(added)

        rows.append(row)

    return rows


def browse_total(html: str) -> int | None:
    """Return the '1,635 recordings' total advertised on a listing page."""
    m = re.search(r"([\d,]+)\s+recordings", html or "")
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
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = _get(session, f"/browse?{query}", delay)
    if resp is None:
        return [], None, ""
    return parse_browse(resp.text), browse_total(resp.text), resp.text


def fetch_recent(
    session: requests.Session, limit: int = 5, delay: float = DEFAULT_DELAY
) -> list[BrowseRow]:
    """Return the ``limit`` most recently added recordings.

    Only as many listing pages as needed are fetched (50 rows per page).

    Args:
        session: Authenticated session.
        limit: Maximum number of rows to return.
        delay: Seconds between requests.

    Returns:
        Newest-first list of BrowseRow, at most ``limit`` long.
    """
    collected: list[BrowseRow] = []
    page = 1
    while len(collected) < limit:
        rows, _total, _html = fetch_browse_page(session, page=page, delay=delay)
        if not rows:
            break
        collected.extend(rows)
        page += 1
    return collected[:limit]


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


def _info_grid(soup: BeautifulSoup) -> dict[str, tuple[str, str]]:
    """Return {label: (text, title_attr)} for every .kv pair on the page."""
    out: dict[str, tuple[str, str]] = {}
    for kv in soup.select(".kv"):
        label = _text(kv.find("span"))
        value_node = kv.find("b")
        if label:
            out[label.lower()] = (
                _text(value_node),
                (value_node.get("title") or "") if value_node else "",
            )
    return out


def _spec_values(soup: BeautifulSoup) -> dict[str, str]:
    """Return {label: value} for the Size/Files/Sources/Uploaded spec strip."""
    out: dict[str, str] = {}
    for spec in soup.select(".spec"):
        label = _text(spec.find("span"))
        value = _text(spec).removeprefix(label).strip()
        if label:
            out[label.lower()] = value
    return out


def parse_recording(html: str, rec_id: int | None = None) -> Recording:
    """Parse a /recordings/<id> detail page.

    Args:
        html: Raw HTML of the detail page.
        rec_id: Known recording id; otherwise read from the page.

    Returns:
        A populated Recording. Missing sections simply stay at their defaults.
    """
    soup = BeautifulSoup(html, "html.parser")
    rec = Recording(rec_id=rec_id)

    if rec.rec_id is None:
        node = soup.select_one("[data-id]")
        if node:
            rec.rec_id = _int_or_none(node.get("data-id", ""))
    if rec.rec_id is not None:
        rec.detail_url = f"{BASE_URL}/recordings/{rec.rec_id}"

    kv = _info_grid(soup)
    rec.date_str = kv.get("date", ("", ""))[0]
    rec.venue = kv.get("venue", ("", ""))[0]
    rec.location = kv.get("location", ("", ""))[0]
    rec.tour = kv.get("tour", ("", ""))[0]
    rec.source_label = kv.get("source", ("", ""))[0]
    rec.format = kv.get("format", ("", ""))[0]
    rec.lb_number = _int_or_none(kv.get("lb number", ("", ""))[0])
    hash_text, hash_title = kv.get("info hash", ("", ""))
    # The grid truncates the hash; the untruncated value lives in title=.
    rec.info_hash = hash_title or hash_text.replace("…", "")

    rec.source_type = _text(soup.select_one(".src-pill")).upper()
    qual = soup.select_one("[data-q]")
    if qual:
        rec.quality = _text(qual)
        rec.quality_slug = qual.get("data-q", "")

    specs = _spec_values(soup)
    rec.size_label = specs.get("size", "")
    rec.size_bytes = parse_size(rec.size_label)
    rec.n_files = _int_or_none(specs.get("files", ""))
    rec.n_sources = _int_or_none(specs.get("sources", ""))
    rec.uploaded_label = specs.get("uploaded", "")

    for cls, attr in (("seed", "seeders"), ("leech", "leechers"),
                      ("snatch", "snatched")):
        cell = soup.select_one(f".swarm-stat.{cls}") or soup.select_one(f".metric.{cls}")
        if cell:
            sr = cell.select_one(".sr-only")
            if sr:
                sr.extract()
            setattr(rec, attr, _int_or_none(_text(cell)))

    page_text = soup.get_text(" ", strip=True)
    rec.freeleech = "Freeleech" in page_text
    rec.lb_verified = "LB verified" in page_text

    uploader = soup.select_one(".uploader b")
    rec.uploader = _text(uploader)
    taper = soup.select_one(".taper-name")
    rec.taper = _text(taper)

    rec.lineage_nodes = [_text(n) for n in soup.select(".lineage-node")]
    rec.lineage = " > ".join(rec.lineage_nodes)

    info = soup.select_one("p.description")
    if info:
        rec.info_text = info.get_text("\n", strip=False).strip()

    for item in soup.select(".set-item"):
        song = item.select_one(".song")
        rec.setlist.append({
            "track": _text(item.select_one(".track")),
            "song": _text(song),
            "song_url": (song.get("href") or "") if song else "",
        })

    for frow in soup.select(".file-row"):
        size_label = _text(frow.select_one(".right"))
        name_node = frow.find("b")
        rec.files.append({
            "name": _text(name_node),
            "size_label": size_label,
            "size_bytes": parse_size(size_label),
        })

    for card in soup.select(".compare-row"):
        href = card.get("href", "") if card.name == "a" else ""
        title = card.select_one(".compare-title")
        rec.siblings.append({
            "title": _text(title.find("b")) if title else "",
            "note": _text(card.select_one(".compare-def")),
            "source_type": _text(card.select_one(".src-pill")).upper(),
            "url": href,
            "rec_id": recording_id_from_url(href),
            "is_current": "current" in (card.get("class") or []),
            "size_label": _text(card.select_one(".compare-size")),
            "seeders": _int_or_none(_text(card.select_one(".compare-seed"))),
            "snatched": _int_or_none(_text(card.select_one(".compare-snatch"))),
        })

    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        if "/storage/spectrograms/" in url and not rec.spectrogram_url:
            rec.spectrogram_url = url
        elif "/storage/samples/" in url and not rec.preview_url:
            rec.preview_url = url

    dl = soup.find("a", href=re.compile(r"/show/\d+/download"))
    if dl:
        rec.torrent_url = dl["href"]
        m = re.search(r"/show/(\d+)/download", rec.torrent_url)
        if m:
            rec.show_id = int(m.group(1))

    rec.headline = _text(soup.select_one(".hero-copy p.subtitle"))
    rec.title = _text(soup.select_one(".hero-copy h1"))
    rec.eyebrow = _text(soup.select_one(".hero-copy .eyebrow"))

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
    """Return the filename in a Content-Disposition header, if any."""
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header or "")
    if not m:
        return None
    name = m.group(1).strip()
    return re.sub(r"[^\w.\-+() ]", "_", name) or None


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


def torrent_root_name(torrent_path: str | Path) -> str | None:
    """Return the root folder name declared inside a .torrent file.

    Parsed with a minimal bencode reader so no extra dependency is needed.

    Args:
        torrent_path: Path to a .torrent file.

    Returns:
        The ``info.name`` value, or None when it cannot be read.
    """
    try:
        data = Path(torrent_path).read_bytes()
    except OSError:
        return None
    m = re.search(rb"4:name(\d+):", data)
    if not m:
        return None
    start = m.end()
    length = int(m.group(1))
    try:
        return data[start:start + length].decode("utf-8", "replace")
    except Exception:
        return None


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
    """Parse one ``/tour/<name>`` page into show rows.

    The row's ``.tl-date`` carries only 'Mon D'; the year comes from the
    ``.tl-year`` divider that precedes it in document order. Deriving the year
    from month wrap-around instead is wrong — tours such as ``Country/Nashville``
    (1969–1974) and ``Infidels/Empire`` (1984–1987) skip whole years.

    Args:
        html: Raw HTML of a tour page.
        tour: Tour name to stamp on each row; falls back to the page heading.

    Returns:
        List of :class:`TourShow`, in page order. Rows with an unparseable
        date are skipped.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    if not tour:
        heading = soup.find("h1")
        tour = _text(heading)

    shows: list[TourShow] = []
    year = 0
    for node in soup.select(".tl-year, a.tl-row"):
        classes = node.get("class") or []
        if "tl-year" in classes:
            year = _int_or_none(_text(node)) or year
            continue

        m = re.match(r"([A-Z][a-z]{2})\s+(\d{1,2})", _text(node.select_one(".tl-date")))
        if not m or not year:
            continue
        month = _MONTHS.get(m.group(1))
        if not month:
            continue

        main = node.select_one(".tl-main")
        meta = node.select_one(".tl-meta")
        href = node.get("href", "")
        seed = meta.select_one(".num") if meta else None
        row = TourShow(
            tour=tour,
            date_str=f"{year:04d}-{month:02d}-{int(m.group(2)):02d}",
            venue=_text(main.find("b")) if main else "",
            location=_text(main.find("small")) if main else "",
            row_url=href,
            circulating=not (meta and meta.select_one(".tl-missing")),
            in_collection=bool(meta and meta.select_one('[title="In your collection"]')),
            has_sbd=bool(meta and meta.select_one(".mini-src.sbd")),
            has_aud=bool(meta and meta.select_one(".mini-src.aud")),
            seeders=_int_or_none(re.sub(r"\D", "", _text(seed))) if seed else None,
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
    m = re.search(r"page\s+\d+\s+of\s+([\d,]+)", html or "")
    return _int_or_none(m.group(1)) or 1 if m else 1


def parse_venue_page(html: str) -> list[TuitVenue]:
    """Parse one ``/venue`` listing page into venue rows.

    Args:
        html: Raw HTML of a venue listing page.

    Returns:
        List of :class:`TuitVenue` in page order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.select_one("table.tbl")
    rows: list[TuitVenue] = []
    if table is None:
        return rows

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        link = cells[0].find("a", href=True)
        years = re.findall(r"\d{4}", _text(cells[3]))
        rows.append(
            TuitVenue(
                venue=_text(cells[0]),
                city=_text(cells[1]),
                country=_text(cells[2]),
                year_first=_int_or_none(years[0]) if years else None,
                year_last=_int_or_none(years[-1]) if years else None,
                n_shows=_int_or_none(_text(cells[4])),
                venue_url=link["href"] if link else "",
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
    """Parse one ``/songs`` listing page into songbook rows.

    Args:
        html: Raw HTML of a songs listing page.

    Returns:
        List of :class:`TuitSong` in page order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.select_one("table.tbl")
    rows: list[TuitSong] = []
    if table is None:
        return rows

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        link = tr.find("a", href=True)
        if len(cells) < 6 or link is None or "/song/" not in link["href"]:
            continue
        title = _text(link)
        rows.append(
            TuitSong(
                song=title,
                song_url=song_url_for(title),
                n_performances=_int_or_none(re.sub(r"\D", "", _text(cells[3]))),
                year_first=_int_or_none(_text(cells[4])),
                year_last=_int_or_none(_text(cells[5])),
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
    """Return the '1 of 17 pages' page total, or 1 when absent."""
    m = re.search(r"\d+\s+of\s+([\d,]+)\s+pages", html or "")
    return _int_or_none(m.group(1)) or 1 if m else 1


def parse_song_page(html: str, song: str = "") -> list[TuitSongPerformance]:
    """Parse one ``/song/<title>`` page into performance rows.

    Every decade section is present in the HTML — the ``<details>`` elements are
    collapsed, not lazily loaded — so one fetch yields the song's full history.
    A ``.perf-note`` follows the row it annotates as a sibling, so the nodes are
    walked in document order rather than selected separately.

    Args:
        html: Raw HTML of a song page.
        song: Song title to stamp on each row; falls back to the page heading.

    Returns:
        List of :class:`TuitSongPerformance` in page order (newest first).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    if not song:
        song = _text(soup.select_one(".song-hero h1") or soup.find("h1"))

    rows: list[TuitSongPerformance] = []
    for node in soup.select(".perf-row, .perf-note"):
        classes = node.get("class") or []
        if "perf-note" in classes:
            if rows:
                rows[-1].note = _text(node)
            continue

        date_iso = _parse_long_date(_text(node.select_one(".perf-date")))
        if not date_iso:
            continue
        venue = node.select_one("a.venue")
        tags = [_text(t) for t in node.select(".perf-src .tag")]
        src = next((t for t in tags if re.match(r"\d+\s+src", t)), "")
        rows.append(
            TuitSongPerformance(
                song=song,
                date_str=date_iso,
                venue_text=_text(venue),
                show_id=(
                    _int_or_none(venue["href"].rstrip("/").rsplit("/", 1)[-1])
                    if venue and "/shows/" in venue.get("href", "") else None
                ),
                n_sources=_int_or_none(re.sub(r"\D", "", src)) if src else None,
                is_encore=any(t.lower() == "encore" for t in tags),
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

    def as_dict(self) -> dict:
        """Return the item as a plain dict."""
        return dict(self.__dict__)


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
        items.append(
            RssItem(
                rec_id=rec_id,
                title=_text(node.find("title")),
                detail_url=link,
                pub_date=_text(node.find("pubDate")),
                description=_text(node.find("description")),
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
