#!/usr/bin/env python3
"""Automated audit of a rendered show-dossier export (Phase G, GOLDEN_DOSSIER_FIX_PLAN.md).

Turns the ad-hoc ``.debug/dossier_review`` review scripts (``extract.py``, ``cmp.py``,
``lbcheck.py``, ``shot2.mjs``) into a repeatable checker over an export directory
produced by ``tools/dossier_golden.py --html``.

Usage::

    .venv/bin/python3 tools/dossier_audit.py ~/Documents/projects/losslessbob_dossiers
    .venv/bin/python3 tools/dossier_audit.py <dir> --offline
    .venv/bin/python3 tools/dossier_audit.py <dir> --no-browser
    .venv/bin/python3 tools/dossier_audit.py <dir> --cache .debug/dossier_audit_cache

Checks:

1. External links -- HTTP status, parked/placeholder detection, LB detail page date
   match, bobserve ``setlist?event=`` date match, bobdylan.com page existence.
2. Internal relative links resolve to files inside the export.
3. Setlist diff vs bobserve (``data-clipboard-text``) and bobdylan.com song links.
4. Structural lints on the HTML (python list repr, "0 min", "-- disc", EXCLUDED
   sources listed as alternates, a dossier with zero songs while its linked
   bobserve/bobdylan.com page lists some, non-contiguous family bands,
   source/family id mismatches, stream/kbps wording in the pick's LB lineage,
   two-show cross-picks).
5. Optional phone-width (390px) overflow check via playwright-core.

Every fetch is cached on disk under ``--cache``, keyed by URL. ``--offline`` refuses
to fetch and uses only what is already cached. Fetching is sequential, uses a 20s
timeout and a normal browser User-Agent -- be polite to bobserve.com/bobdylan.com/
the LB catalog mirror.

Exit status is 1 if any *structural* finding was reported (checks 2 and 4), 0
otherwise. External-link and setlist-diff findings never affect the exit status --
some are known, accepted upstream differences (see the plan doc).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import logging
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_S = 20

_PARKED_MARKERS = (
    "coming soon",
    "namebright",
    "is almost here",
    "domain is for sale",
    "buy this domain",
    "this domain may be for sale",
)

# Checks that count as "structural" for the exit-code gate.
_STRUCTURAL_CHECKS = frozenset(
    {
        "internal-link",
        "list-repr",
        "zero-min",
        "em-dash-disc",
        "excluded-in-alternates",
        "setlist-missing",
        "family-noncontiguous",
        "family-id-mismatch",
        "pick-stream-lineage",
        "two-show-cross-pick",
        "phone-overflow",
    }
)


@dataclass
class Finding:
    """One audit finding.

    Attributes:
        page: Basename of the dossier HTML file the finding concerns.
        check: Short check name (used for the summary tally and exit code).
        detail: Free-text detail for the report line.
    """

    page: str
    check: str
    detail: str

    def line(self) -> str:
        """Format as a single report line."""
        return f"{self.page} | {self.check} | {self.detail}"


class FetchCache:
    """Disk cache for HTTP fetches, keyed by URL.

    Each URL is stored as two files under ``cache_dir``: ``<key>.body`` (raw
    response bytes, or empty on error) and ``<key>.meta`` (``status\\nurl``).

    Attributes:
        cache_dir: Directory the cache files live in.
        offline: When true, ``get`` never performs a network request and
            raises :class:`FileNotFoundError` on a cache miss.
    """

    def __init__(self, cache_dir: Path, offline: bool) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = None

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.md5((url + "\n").encode("utf-8")).hexdigest()[:16]

    def get(self, url: str) -> tuple[int, str]:
        """Fetch ``url``, using and populating the cache.

        Returns:
            A ``(status_code, text)`` tuple. ``status_code`` is ``-1`` on a
            connection-level failure (timeout, DNS, refused, etc).

        Raises:
            FileNotFoundError: In offline mode when ``url`` is not cached.
        """
        key = self._key(url)
        body_path = self.cache_dir / f"{key}.body"
        meta_path = self.cache_dir / f"{key}.meta"
        if body_path.exists() and meta_path.exists():
            meta = meta_path.read_text(encoding="utf-8").splitlines()
            status = int(meta[0]) if meta else -1
            text = body_path.read_text(encoding="utf-8", errors="replace")
            return status, text
        if self.offline:
            raise FileNotFoundError(f"not cached (offline): {url}")
        status, text = self._fetch(url)
        body_path.write_text(text, encoding="utf-8")
        meta_path.write_text(f"{status}\n{url}\n", encoding="utf-8")
        return status, text

    def _fetch(self, url: str) -> tuple[int, str]:
        import requests

        if self._session is None:
            self._session = requests.Session()
            self._session.headers["User-Agent"] = _USER_AGENT
        try:
            resp = self._session.get(url, timeout=_TIMEOUT_S)
        except requests.RequestException as exc:
            _log.warning("fetch failed for %s: %s", url, exc)
            return -1, ""
        return resp.status_code, resp.text


# ---------------------------------------------------------------------------
# Title folding (check 3)
# ---------------------------------------------------------------------------

_TALKIN_RE = re.compile(r"\btalkin\b")


def fold_title(title: str) -> str:
    """Normalize a song title for cross-source comparison.

    Unescapes HTML entities, normalizes curly/straight apostrophes, strips
    parentheticals, folds "Talkin'"/"Talking" to one spelling, lowercases and
    collapses to alphanumeric tokens.

    Args:
        title: Raw song title text, possibly HTML-escaped.

    Returns:
        A normalized string suitable for equality comparison across sources.
    """
    s = html.unescape(html.unescape(title))
    s = s.replace("’", "'").replace("‘", "'")
    s = s.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9']+", " ", s)
    s = re.sub(r"\btalking\b", "talkin", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# HTML field extraction helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s)).strip()


def data_lb_fields(page_html: str, key: str) -> list[str]:
    """Return the (tag-stripped, unescaped) text of every ``data-lb="key"`` element.

    Args:
        page_html: Raw dossier page HTML.
        key: The ``data-lb`` attribute value to match exactly (e.g. ``song[].title``).

    Returns:
        Text content of each matching element, in document order.
    """
    pattern = r'data-lb="' + re.escape(key) + r'"[^>]*>(.*?)</'
    return [_strip_tags(m) for m in re.findall(pattern, page_html, re.S)]


def _dossier_date_for(basename: str) -> str | None:
    """Extract the YYYY-MM-DD date prefix from a dossier filename, if present."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", basename)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _lb_want_date(iso_date: str) -> str:
    """Convert an ISO date (YYYY-MM-DD) to the LB catalog's M/D/YY timing format."""
    y, mo, d = iso_date.split("-")
    return f"{int(mo)}/{int(d)}/{y[2:]}"


# ---------------------------------------------------------------------------
# Structural lints (check 4) -- pure functions over raw HTML, no network.
# ---------------------------------------------------------------------------

_DATA_LB_ELEM_RE = re.compile(r'data-lb="([\w.\[\]]+)"[^>]*>(.*?)</', re.S)


def check_list_repr(page: str, page_html: str) -> list[Finding]:
    """Flag any ``data-lb`` field whose text is a raw Python list repr."""
    out = []
    for key, raw in _DATA_LB_ELEM_RE.findall(page_html):
        text = _strip_tags(raw)
        if text.startswith("['") or text.startswith('["'):
            out.append(Finding(page, "list-repr", f'{key}: {text[:80]!r}'))
    return out


def check_zero_min(page: str, page_html: str) -> list[Finding]:
    """Flag any runtime field literally rendered as "0 min"."""
    out = []
    for key, raw in _DATA_LB_ELEM_RE.findall(page_html):
        if not key.endswith("runtime") and key != "pick.runtime":
            continue
        if _strip_tags(raw) == "0 min":
            out.append(Finding(page, "zero-min", f"{key} rendered as '0 min'"))
    return out


def check_em_dash_disc(page: str, page_html: str) -> list[Finding]:
    """Flag any ``— disc`` placeholder (missing disc-count value)."""
    out = []
    for m in re.finditer(r"[^<]*— disc[^<]*", page_html):
        out.append(Finding(page, "em-dash-disc", m.group(0).strip()[:80]))
    return out


_LB_ID_RE = re.compile(r"LB-(\d+)")


def check_excluded_in_alternates(page: str, page_html: str) -> list[Finding]:
    """Flag an EXCLUDED source that still appears in ``verdict.alternates[]``."""
    excluded_ids: set[str] = set()
    for m in re.finditer(
        r'data-lb="source\[\]\.lb_id"[^>]*>.*?(LB-\d+).*?'
        r'data-lb="source\[\]\.character"[^>]*>([^<]*)',
        page_html,
        re.S,
    ):
        lb_id, character = m.group(1), html.unescape(m.group(2))
        if character.strip().upper().startswith("EXCLUDED"):
            excluded_ids.add(lb_id)
    if not excluded_ids:
        return []
    out = []
    alt_blocks = re.findall(
        r'data-lb="verdict\.alternates\[\]"[^>]*>(.*?)</div>', page_html, re.S
    )
    for block in alt_blocks:
        for lb_id in _LB_ID_RE.findall(block):
            full = f"LB-{lb_id}"
            if full in excluded_ids:
                out.append(
                    Finding(
                        page,
                        "excluded-in-alternates",
                        f"{full} is EXCLUDED but listed in verdict.alternates",
                    )
                )
    return out


# F3: family id now lives in a `data-family="<id>"` attribute on the `<tr class="fam-head">`
# itself, with `family[].id` kept as a Jinja comment (no runtime element) for anchor
# coverage. The old hidden-span form (`<span data-lb="family[].id" hidden>…</span>`) is
# still matched so this audit still works against an export made before F3.
_FAM_HEAD_ROW_RE = re.compile(
    r'<tr class="(fam-head[^"]*)"(?: data-family="([^"]*)")?[^>]*>(.*?)</tr>', re.S,
)
_FAM_LABEL_IN_ROW_RE = re.compile(r'data-lb="family\[\]\.label"[^>]*>([^<]*)</span>')
_FAM_ID_SPAN_IN_ROW_RE = re.compile(r'data-lb="family\[\]\.id"[^>]*>([^<]*)</span>')


def _find_fam_heads(page_html: str) -> list[tuple[str, str]]:
    """``[(label, fam_id), ...]`` for every real family header, new or old export
    form. Bounded to one ``<tr>...</tr>`` at a time so a label further down the
    page (e.g. the next real family, after an unlabelled "Other sources" band)
    never gets attached to the wrong header.
    """
    out = []
    for _cls, data_family, body in _FAM_HEAD_ROW_RE.findall(page_html):
        label_m = _FAM_LABEL_IN_ROW_RE.search(body)
        if not label_m:
            continue  # the "Other sources" band (F3): no family[].label at all
        label = label_m.group(1)
        if data_family:  # new form: id is the row's own data-family attribute
            fam_id = data_family
        else:  # old form: id is a hidden span inside the row
            id_m = _FAM_ID_SPAN_IN_ROW_RE.search(body)
            fam_id = id_m.group(1) if id_m else ""
        out.append((label, fam_id))
    return out


def check_family_contiguous(page: str, page_html: str) -> list[Finding]:
    """Flag a family header (by id) that appears more than once, non-adjacently."""
    heads = _find_fam_heads(page_html)
    seen: dict[str, int] = {}
    out = []
    for idx, (label, fam_id) in enumerate(heads):
        if fam_id in seen and seen[fam_id] != idx - 1:
            out.append(
                Finding(
                    page,
                    "family-noncontiguous",
                    f"{label.strip()} ({fam_id}) header repeats non-adjacently",
                )
            )
        seen[fam_id] = idx
    return out


def check_family_membership(page: str, page_html: str) -> list[Finding]:
    """Flag a source row whose lb_id isn't listed in the family header above it."""
    # Split the sources table body into row-fragments (fam-head[-other] or mrow), in
    # order, along with the row's opening tag (for the new data-family attribute).
    rows = re.findall(
        r'<tr class="(fam-head[^"]*|mrow[^"]*)"([^>]*)>(.*?)</tr>', page_html, re.S
    )
    current_id = ""
    out = []
    for cls, attrs, body in rows:
        if cls.startswith("fam-head"):
            m = re.search(r'data-family="([^"]*)"', attrs)
            if m:
                current_id = m.group(1).strip()
            else:
                m = re.search(r'data-lb="family\[\]\.id"[^>]*>([^<]*)</span>', body)
                current_id = m.group(1).strip() if m else ""
            if current_id in ("", "__other__"):
                current_id = ""
            continue
        if "in-fam" not in cls or not current_id:
            continue
        m = re.search(r"LB-0*(\d+)", body)
        if not m:
            continue
        lb_num = m.group(1)
        if lb_num not in re.split(r"[^0-9]+", current_id):
            out.append(
                Finding(
                    page,
                    "family-id-mismatch",
                    f"LB-{lb_num} in-fam row not listed in family id {current_id}",
                )
            )
    return out


def check_two_show_cross_pick(page: str, page_html: str) -> list[Finding]:
    """Flag a two-show page whose pick lineage names the other show's part."""
    m = re.search(r"--(afternoon|evening)\.html$", page)
    if not m:
        return []
    this_part = m.group(1)
    other_part = "evening" if this_part == "afternoon" else "afternoon"
    out = []
    for key in ("pick.lineage_short", "pick.lineage"):
        for text in data_lb_fields(page_html, key):
            if other_part in text.lower():
                out.append(
                    Finding(
                        page,
                        "two-show-cross-pick",
                        f"{key} mentions '{other_part}' on the {this_part} page: "
                        f"{text[:80]!r}",
                    )
                )
    return out


def run_structural_lints(page: str, page_html: str) -> list[Finding]:
    """Run every network-free structural lint over one page and return findings."""
    findings: list[Finding] = []
    findings += check_list_repr(page, page_html)
    findings += check_zero_min(page, page_html)
    findings += check_em_dash_disc(page, page_html)
    findings += check_excluded_in_alternates(page, page_html)
    findings += check_family_contiguous(page, page_html)
    findings += check_family_membership(page, page_html)
    findings += check_two_show_cross_pick(page, page_html)
    return findings


# ---------------------------------------------------------------------------
# Internal + external links (checks 1 and 2)
# ---------------------------------------------------------------------------

_HREF_RE = re.compile(r'href="([^"]+)"')


def check_internal_links(page: str, page_html: str, export_dir: Path) -> list[Finding]:
    """Flag a relative href that doesn't resolve to a file in the export dir."""
    out = []
    for href in _HREF_RE.findall(page_html):
        if href.startswith(("http://", "https://", "#", "mailto:", "javascript:")):
            continue
        target = href.split("#", 1)[0]
        if not target:
            continue
        if not (export_dir / target).exists():
            out.append(Finding(page, "internal-link", f"broken relative link: {href}"))
    return out


def _extract_external_links(page_html: str) -> list[str]:
    urls = []
    for href in _HREF_RE.findall(page_html):
        if href.startswith(("http://", "https://")):
            urls.append(html.unescape(href))
    return urls


def check_pick_lineage_stream(
    page: str, page_html: str, cache: FetchCache
) -> list[Finding]:
    """Flag when the pick's LB detail page lineage mentions stream/kbps/mp3."""
    m = re.search(r'data-lb="pick\.url"[^>]*href="([^"]+)"', page_html)
    if not m:
        return []
    url = html.unescape(m.group(1))
    try:
        status, text = cache.get(url)
    except FileNotFoundError:
        return [Finding(page, "pick-stream-lineage", f"not cached (offline): {url}")]
    if status != 200:
        return []
    plain = html.unescape(re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)))
    hits = [
        kw for kw in ("stream", "kbps", "mp3")
        if re.search(rf"\b\d*{kw}", plain, re.IGNORECASE)
    ]
    if hits:
        return [
            Finding(
                page,
                "pick-stream-lineage",
                f"pick LB page mentions {', '.join(hits)}: {url}",
            )
        ]
    return []


def check_external_link(
    page: str, url: str, dossier_date: str | None, cache: FetchCache
) -> list[Finding]:
    """Fetch one external URL and run status/parked/date checks against it."""
    out: list[Finding] = []
    try:
        status, text = cache.get(url)
    except FileNotFoundError:
        out.append(Finding(page, "external-link", f"not cached (offline): {url}"))
        return out
    if status == -1:
        out.append(Finding(page, "external-link", f"fetch failed: {url}"))
        return out
    if status == 202:
        # setlist.fm answers automated clients with an empty 202 (bot challenge);
        # the page exists, its content just can't be checked from here.
        _log.info("HTTP 202 (bot challenge), content unchecked: %s", url)
        return out
    if status != 200:
        out.append(Finding(page, "external-link", f"HTTP {status}: {url}"))
        return out

    plain = html.unescape(re.sub(r"\s+", " ", _TAG_RE.sub(" ", text))).lower()
    if any(marker in plain for marker in _PARKED_MARKERS):
        out.append(Finding(page, "parked-page", url))
        return out

    lb_m = re.search(r"/detail/(LB-\d+)\.html", url)
    if lb_m and dossier_date:
        date_m = re.search(r"Timing (\S+)", plain, re.I)
        want = _lb_want_date(dossier_date)
        if date_m and date_m.group(1) != want:
            out.append(
                Finding(
                    page,
                    "lb-date-mismatch",
                    f"{lb_m.group(1)}: LB page date {date_m.group(1)} != want {want}",
                )
            )
        elif not date_m:
            out.append(
                Finding(page, "lb-date-mismatch", f"{lb_m.group(1)}: no Timing found")
            )

    ev_m = re.search(r"bobserve\.com/setlist\?event=(\d+)", url)
    if ev_m and dossier_date:
        date_m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", plain)
        if date_m and date_m.group(1) != dossier_date:
            out.append(
                Finding(
                    page,
                    "bobserve-date-mismatch",
                    f"event {ev_m.group(1)}: {date_m.group(1)} != {dossier_date}",
                )
            )

    return out


# ---------------------------------------------------------------------------
# Setlist diff (check 3)
# ---------------------------------------------------------------------------

_CLIP_RE = re.compile(r'data-clipboard-text="(.*?)"', re.S)
_BD_SONG_RE = re.compile(r'href="https://www\.bobdylan\.com/songs/[^"]*"[^>]*>([^<]*)')


def check_setlist_missing(
    page: str, dossier_count: int, source: str, source_count: int
) -> list[Finding]:
    """Flag a dossier page with zero songs when a linked source has some.

    Args:
        page: Basename of the dossier HTML file.
        dossier_count: Number of ``song[].title`` spans found on the page.
        source: Name of the external source being compared ("bobserve" or
            "bobdylan.com"), used only in the finding detail text.
        source_count: Number of songs the linked external page lists.

    Returns:
        A single-element list with a ``setlist-missing`` finding when the
        dossier has no setlist but the linked source has at least one song;
        an empty list otherwise.
    """
    if dossier_count == 0 and source_count >= 1:
        return [
            Finding(
                page,
                "setlist-missing",
                f"dossier has 0 songs but {source} lists {source_count}",
            )
        ]
    return []


def check_setlist_diff(
    page: str, page_html: str, external_urls: list[str], cache: FetchCache
) -> list[Finding]:
    """Diff the dossier setlist against bobserve and bobdylan.com, when linked."""
    out: list[Finding] = []
    songs = data_lb_fields(page_html, "song[].title")
    folded = [fold_title(s) for s in songs]

    bobserve_url = next(
        (u for u in external_urls if "bobserve.com/setlist?event=" in u), None
    )
    if bobserve_url:
        try:
            status, text = cache.get(bobserve_url)
        except FileNotFoundError:
            out.append(
                Finding(page, "setlist-diff-bobserve", f"not cached: {bobserve_url}")
            )
            status, text = -1, ""
        if status == 200:
            m = _CLIP_RE.search(text)
            clip = html.unescape(m.group(1)) if m else ""
            bs_songs = [
                re.sub(r"^\d+\.\s*", "", ln)
                for ln in clip.split("\n")
                if re.match(r"^\d+\.\s", ln)
            ]
            bs_folded = [fold_title(s) for s in bs_songs]
            if not folded:
                out += check_setlist_missing(page, 0, "bobserve", len(bs_folded))
            elif folded != bs_folded:
                out.append(
                    Finding(
                        page,
                        "setlist-diff-bobserve",
                        f"dossier has {len(folded)} songs, bobserve has "
                        f"{len(bs_folded)}",
                    )
                )

    bd_url = next((u for u in external_urls if "bobdylan.com/date/" in u), None)
    if bd_url:
        try:
            status, text = cache.get(bd_url)
        except FileNotFoundError:
            out.append(Finding(page, "setlist-diff-bobdylan", f"not cached: {bd_url}"))
            status, text = -1, ""
        if status == 200:
            bd_songs = [html.unescape(s) for s in _BD_SONG_RE.findall(text)]
            bd_folded = [fold_title(s) for s in bd_songs]
            if not folded:
                out += check_setlist_missing(page, 0, "bobdylan.com", len(bd_folded))
                bd_folded = []
            only_dossier = [s for s in folded if s not in bd_folded]
            only_bd = [s for s in bd_folded if s not in folded]
            if folded and (only_dossier or only_bd):
                out.append(
                    Finding(
                        page,
                        "setlist-diff-bobdylan",
                        f"only-dossier={only_dossier[:5]} only-bobdylan={only_bd[:5]}",
                    )
                )

    return out


# ---------------------------------------------------------------------------
# Phone-width overflow (check 5)
# ---------------------------------------------------------------------------


def check_phone_overflow(export_dir: Path, pages: list[str]) -> list[Finding]:
    """Run the playwright-core phone-width overflow probe over every page.

    Returns:
        One finding per page whose ``documentElement.scrollWidth`` exceeds 390px,
        or a single "unavailable" finding if playwright-core can't be loaded.
    """
    gui_next = Path(__file__).resolve().parent.parent / "gui_next"
    pw_entry = gui_next / "node_modules" / "playwright-core" / "index.mjs"
    if not pw_entry.exists():
        return [Finding("*", "phone-overflow", "playwright-core not available, skipped")]

    files_json = "[" + ",".join(f'"{p}"' for p in pages) + "]"
    script = f"""
import {{ chromium }} from '{pw_entry.as_posix()}';
const dir = '{export_dir.as_posix()}/';
const files = {files_json};
const b = await chromium.launch();
const ctx = await b.newContext({{ viewport: {{ width: 390, height: 900 }} }});
const p = await ctx.newPage();
for (const f of files) {{
  await p.goto('file://' + dir + f);
  await p.waitForTimeout(300);
  const w = await p.evaluate(() => document.documentElement.scrollWidth);
  console.log(f + '\\t' + w);
}}
await ctx.close();
await b.close();
"""
    try:
        proc = subprocess.run(
            ["node", "--input-type=module"],
            input=script,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [Finding("*", "phone-overflow", f"playwright run failed: {exc}")]
    if proc.returncode != 0:
        _log.warning("phone-overflow probe stderr: %s", proc.stderr[-2000:])
        return [
            Finding("*", "phone-overflow", f"playwright run failed: {proc.stderr[-300:]}")
        ]
    out = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        fname, width_s = line.rsplit("\t", 1)
        try:
            width = int(width_s.strip())
        except ValueError:
            continue
        if width > 390:
            out.append(Finding(fname, "phone-overflow", f"scrollWidth={width} > 390"))
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def audit_page(
    path: Path, export_dir: Path, cache: FetchCache, page_html_cache: dict[str, str]
) -> list[Finding]:
    """Run all page-local checks (1-4, minus the shared phone-overflow pass)."""
    page = path.name
    page_html = path.read_text(encoding="utf-8", errors="replace")
    page_html_cache[page] = page_html
    findings: list[Finding] = []

    findings += run_structural_lints(page, page_html)
    findings += check_internal_links(page, page_html, export_dir)

    dossier_date = _dossier_date_for(page)
    external_urls = _extract_external_links(page_html)
    seen: set[str] = set()
    for url in external_urls:
        if url in seen:
            continue
        seen.add(url)
        findings += check_external_link(page, url, dossier_date, cache)

    findings += check_setlist_diff(page, page_html, external_urls, cache)
    findings += check_pick_lineage_stream(page, page_html, cache)

    return findings


def run_audit(
    export_dir: Path, cache: FetchCache, use_browser: bool
) -> list[Finding]:
    """Run the full audit over every ``*.html`` file in ``export_dir``.

    Args:
        export_dir: Directory containing the rendered dossier export.
        cache: Shared fetch cache for external URLs.
        use_browser: Whether to run the playwright phone-overflow check.

    Returns:
        All findings across every page, in file order.
    """
    pages = sorted(p.name for p in export_dir.glob("*.html"))
    findings: list[Finding] = []
    page_html_cache: dict[str, str] = {}
    for name in pages:
        findings += audit_page(export_dir / name, export_dir, cache, page_html_cache)
    if use_browser:
        findings += check_phone_overflow(export_dir, pages)
    return findings


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    """Tally findings per check name."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check] = counts.get(f.check, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path, help="Rendered dossier export dir")
    parser.add_argument(
        "--offline", action="store_true", help="Use only cached fetches, no network"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Skip the phone-overflow check"
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(".debug/dossier_audit_cache"),
        help="Fetch cache directory (default: .debug/dossier_audit_cache)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Debug logging to stderr"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    export_dir = args.export_dir.expanduser().resolve()
    if not export_dir.is_dir():
        _log.error("not a directory: %s", export_dir)
        return 2

    cache = FetchCache(args.cache, offline=args.offline)
    findings = run_audit(export_dir, cache, use_browser=not args.no_browser)

    for f in findings:
        sys.stdout.write(f.line() + "\n")

    counts = summarize(findings)
    sys.stdout.write("\n-- summary --\n")
    for check in sorted(counts):
        sys.stdout.write(f"{check}: {counts[check]}\n")
    sys.stdout.write(f"total: {len(findings)}\n")

    structural = sum(1 for f in findings if f.check in _STRUCTURAL_CHECKS)
    return 1 if structural else 0


if __name__ == "__main__":
    sys.exit(main())
