#!/usr/bin/env python3
"""check_mirror_links.py — prove the site mirror is still browsable offline.

Preservation stack B3 (instructions/FABLE_PRESERVATION_STACK.md §D3). D1 proves
continuity of *data* — that the bytes are intact. This proves continuity of
*reference*: that during a losslessbob.com outage a friend can still look things
up. The mirror's HTML is already link-rewritten to relative paths, so restoring
it is just serving the directory::

    python3 -m http.server -d data/site 8080

This tool walks mirrored HTML, extracts every internal ``href``/``src``/
``action`` target, and asserts each one resolves to a file on disk. Read-only —
it never touches the DB and never edits a page. Broken links it finds are
findings for a human, not something to auto-fix.

Usage::

    python tools/check_mirror_links.py              # 4 seed pages + 500-page sample
    python tools/check_mirror_links.py --full       # every mirrored page
    python tools/check_mirror_links.py --report

The four seed pages — the site home, the LBM by-number master index, the year
index and the bootleg index — are the pages people actually navigate from, so
any break in them fails the run. Sample findings are reported but do not fail
it unless ``--max-broken`` is given.
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

# Ensure project root is on sys.path so ``from backend...`` works when this
# script is run directly (e.g. python tools/check_mirror_links.py).
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bs4 import BeautifulSoup  # noqa: E402

from backend.paths import DATA_DIR, SITE_DIR  # noqa: E402

log = logging.getLogger("check_mirror_links")

# ── Constants ─────────────────────────────────────────────────────────────────

EXPORTS_DIR = DATA_DIR / "exports"

# The pages a person actually starts from. A break here means the restored
# mirror is unusable for lookup, so these gate the exit code.
SEED_PAGES = (
    "LosslessBob.html",              # site home
    "bynumber/LBM-bynumber.html",    # LBM master index, by number
    "detail/LBM-year.html",          # year index
    "LosslessBob-Bootleg-CD.html",   # bootleg index
)

LINK_ATTRS = ("href", "src", "action")
SKIP_PREFIXES = ("mailto:", "javascript:", "data:", "tel:", "#", "ftp:")
HTML_SUFFIXES = (".html", ".htm")

# Much of the site was authored in Microsoft Word, which emits <link> tags
# pointing at export scaffolding no browser ever fetches for display. They are
# not reference continuity — counting them would fail every seed page over
# files that do not matter.
NON_NAVIGABLE_RELS = frozenset({
    "file-list", "themedata", "colorschememapping", "edit-time-data",
    "shortcut icon", "icon",
})

SAMPLE_SIZE = 500
SAMPLE_SEED = 1966  # fixed, so successive runs check the same pages


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class BrokenLink:
    """One internal link that does not resolve to a file on disk.

    Attributes:
        page: Mirror-relative path of the page containing the link.
        target: The raw link value as written in the HTML.
        resolved: Mirror-relative path the link resolved to.
        seed: True if the containing page is one of the seed pages.
    """

    page: str
    target: str
    resolved: str
    seed: bool = False

    def line(self) -> str:
        """Return the single-line report representation."""
        tag = "SEED " if self.seed else ""
        return f"{tag}broken  {self.page}  ->  {self.target}  (no {self.resolved})"


@dataclass
class LinkResult:
    """Outcome of a link-check run.

    Attributes:
        pages: Pages parsed.
        links: Internal links checked.
        skipped: Links skipped as external or non-navigable.
        broken: Every unresolvable internal link found.
        seed_pages_checked: How many seed pages were present and parsed.
        missing_seeds: Seed pages absent from the mirror entirely.
        seconds: Wall-clock duration.
        cancelled: True if a ``should_stop`` callback ended the run early, in
            which case every other field describes the partial run only.
    """

    pages: int = 0
    links: int = 0
    skipped: int = 0
    broken: list[BrokenLink] = field(default_factory=list)
    seed_pages_checked: int = 0
    missing_seeds: list[str] = field(default_factory=list)
    seconds: float = 0.0
    cancelled: bool = False

    @property
    def seed_broken(self) -> list[BrokenLink]:
        """Broken links that live on a seed page."""
        return [b for b in self.broken if b.seed]

    def failed(self, max_broken: int | None = None) -> bool:
        """Return True if this run should exit non-zero.

        Args:
            max_broken: Optional cap on total broken links; when omitted only
                the seed pages gate the result.
        """
        if self.missing_seeds or self.seed_broken:
            return True
        if max_broken is not None and len(self.broken) > max_broken:
            return True
        return False

    def summary(self) -> str:
        """Return the single-line summary for the CLI and report file."""
        parts = [
            f"links: {self.pages} pages",
            f"checked {self.links}",
            f"skipped {self.skipped}",
            f"broken {len(self.broken)}",
            f"seed-broken {len(self.seed_broken)}",
            f"seeds {self.seed_pages_checked}/{len(SEED_PAGES)}",
            f"{self.seconds:.1f}s",
        ]
        if self.cancelled:
            parts.append("CANCELLED")
        return " | ".join(parts)


# ── Link extraction ───────────────────────────────────────────────────────────

def _is_internal(value: str) -> bool:
    """Return True if a link value points inside the mirror.

    Args:
        value: Raw attribute value from the HTML.

    Returns:
        False for empty values, fragments, protocol URIs, protocol-relative
        (``//host/…``) and absolute URLs with a scheme.
    """
    value = value.strip()
    if not value or value.startswith(SKIP_PREFIXES):
        return False
    if value.startswith("//") or "://" in value:
        return False
    return True


def _is_navigable_tag(tag) -> bool:
    """Return False for ``<link>`` tags whose rel is document scaffolding."""
    if tag.name != "link":
        return True
    rel = tag.get("rel")
    if isinstance(rel, list):
        rel = " ".join(rel)
    return not (isinstance(rel, str) and rel.strip().lower() in NON_NAVIGABLE_RELS)


def extract_links(html: str) -> tuple[list[str], int]:
    """Return the internal link values found in *html*, in document order.

    Args:
        html: Page source.

    Returns:
        Tuple of (raw internal attribute values — still relative and still
        URL-encoded, number of link values skipped as external or
        non-navigable).
    """
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    skipped = 0
    for tag in soup.find_all(True):
        navigable = _is_navigable_tag(tag)
        for attr in LINK_ATTRS:
            value = tag.get(attr)
            if not isinstance(value, str) or not value.strip():
                continue
            if navigable and _is_internal(value):
                found.append(value.strip())
            else:
                skipped += 1
    return found, skipped


def resolve_link(site_dir: Path, page_rel: str, target: str) -> Path:
    """Resolve a link found on *page_rel* to the file it should reach.

    Args:
        site_dir: Mirror root.
        page_rel: Mirror-relative path of the containing page.
        target: Raw link value.

    Returns:
        Absolute path the link points at. Directory-style targets resolve to
        their ``index.html``.
    """
    path_part = urlparse(target).path
    path_part = unquote(path_part)
    if path_part.startswith("/"):
        # Server-absolute and never rewritten — resolve from the mirror root.
        candidate = site_dir / path_part.lstrip("/")
    else:
        candidate = (site_dir / page_rel).parent / path_part
    if not path_part or path_part.endswith("/"):
        candidate = candidate / "index.html"
    # Collapse ".." lexically — not resolve(), which would follow symlinks and
    # is needless I/O; this keeps reported paths readable and mirror-relative.
    return Path(os.path.normpath(candidate))


# ── Page selection ────────────────────────────────────────────────────────────

def all_html_pages(site_dir: Path) -> list[str]:
    """Return every mirrored HTML page as a sorted mirror-relative path list."""
    return sorted(
        p.relative_to(site_dir).as_posix()
        for p in site_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in HTML_SUFFIXES
    )


def select_pages(site_dir: Path, full: bool = False,
                 sample_size: int = SAMPLE_SIZE) -> list[str]:
    """Choose which pages to check.

    The sample is seeded, so successive runs check the same pages and a
    regression shows up as a change rather than as sampling noise. Seed pages
    are always included.

    Args:
        site_dir: Mirror root.
        full: Check every page instead of a sample.
        sample_size: Size of the non-seed sample.

    Returns:
        Mirror-relative page paths.
    """
    pages = all_html_pages(site_dir)
    if full:
        return pages
    present_seeds = [s for s in SEED_PAGES if (site_dir / s).exists()]
    rest = [p for p in pages if p not in set(present_seeds)]
    if len(rest) > sample_size:
        rest = sorted(random.Random(SAMPLE_SEED).sample(rest, sample_size))
    return present_seeds + rest


# ── Core pass ─────────────────────────────────────────────────────────────────

def check_links(site_dir: Path | None = None, full: bool = False,
                sample_size: int = SAMPLE_SIZE,
                progress_cb: Callable[[int, int], None] | None = None,
                should_stop: Callable[[], bool] | None = None) -> LinkResult:
    """Walk mirrored pages and report internal links that do not resolve.

    Args:
        site_dir: Mirror root; defaults to ``data/site/``.
        full: Check every page rather than the seeded sample.
        sample_size: Size of the non-seed sample.
        progress_cb: Optional ``(done, total)`` callback fired once per page,
            for GUI progress reporting.
        should_stop: Optional predicate polled once per page; returning True
            ends the run early.

    Returns:
        A :class:`LinkResult`, with ``cancelled`` set if *should_stop* ended
        the run.
    """
    site_dir = Path(site_dir or SITE_DIR)
    started = time.time()
    res = LinkResult()

    res.missing_seeds = [s for s in SEED_PAGES if not (site_dir / s).exists()]
    for seed in res.missing_seeds:
        log.warning("seed page missing from mirror: %s", seed)

    seeds = set(SEED_PAGES)
    pages = select_pages(site_dir, full=full, sample_size=sample_size)
    total = len(pages)
    for done, page_rel in enumerate(pages, 1):
        if progress_cb is not None:
            progress_cb(done, total)
        if should_stop is not None and should_stop():
            res.cancelled = True
            log.warning("link check cancelled after %d/%d pages", done, total)
            break
        path = site_dir / page_rel
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.warning("unreadable page %s: %s", page_rel, exc)
            continue
        res.pages += 1
        is_seed = page_rel in seeds
        if is_seed:
            res.seed_pages_checked += 1
        targets, skipped = extract_links(html)
        res.skipped += skipped
        for target in targets:
            resolved = resolve_link(site_dir, page_rel, target)
            res.links += 1
            if not resolved.exists():
                try:
                    shown = resolved.relative_to(site_dir).as_posix()
                except ValueError:
                    shown = str(resolved)
                res.broken.append(BrokenLink(page_rel, target, shown, seed=is_seed))

    res.seconds = time.time() - started
    return res


# ── Reporting / CLI ───────────────────────────────────────────────────────────

def write_report(res: LinkResult, exports_dir: Path | None = None) -> Path:
    """Write broken-link lines plus the summary to a dated file.

    Args:
        res: Completed run result.
        exports_dir: Destination directory; defaults to ``data/exports/``.

    Returns:
        Path of the written report.
    """
    exports_dir = Path(exports_dir or EXPORTS_DIR)
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = exports_dir / f"site_mirror_links_{stamp}.txt"
    lines = [f"# site mirror link check — {datetime.now().isoformat(timespec='seconds')}"]
    lines += [f"# serve the mirror with: python3 -m http.server -d {SITE_DIR} 8080"]
    lines += [f"missing-seed  {s}" for s in res.missing_seeds]
    lines += [b.line() for b in res.broken]
    lines.append(res.summary())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Check that internal links in the site mirror resolve on disk.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--full", action="store_true",
                        help="check every mirrored page, not the seeded sample")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE,
                        help=f"non-seed pages to sample (default: {SAMPLE_SIZE})")
    parser.add_argument("--max-broken", type=int, default=None,
                        help="fail if total broken links exceed this "
                             "(seed pages always fail on any break)")
    parser.add_argument("--report", action="store_true",
                        help="also write the report to data/exports/")
    parser.add_argument("--site-dir", default=None, help="mirror root (default: data/site/)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code — non-zero if a seed page is broken or missing, or if
        ``--max-broken`` was exceeded.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    res = check_links(
        site_dir=Path(args.site_dir) if args.site_dir else None,
        full=args.full,
        sample_size=args.sample_size,
    )

    for seed in res.missing_seeds:
        log.info("missing-seed  %s", seed)
    for broken in res.broken:
        log.info("%s", broken.line())
    log.info("%s", res.summary())
    if args.report:
        log.info("report: %s", write_report(res))
    log.info("serve the mirror with: python3 -m http.server -d %s 8080", SITE_DIR)
    return 1 if res.failed(args.max_broken) else 0


if __name__ == "__main__":
    sys.exit(main())
