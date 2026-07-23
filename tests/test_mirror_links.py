"""
Tests for the mirror restore test (preservation stack B3).

Covers tools/check_mirror_links.py:
  - internal links that resolve, and ones that do not
  - external / mailto / fragment links are skipped, not reported as broken
  - directory-style and URL-encoded targets resolve correctly
  - seed pages gate the exit code; sample findings are report-only
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import check_mirror_links as cml  # noqa: E402


@pytest.fixture
def mirror(tmp_path: Path):
    """Build a tiny mirror containing one valid and one broken link.

    The home page is named after the real seed page so seed-gating is exercised.
    """
    site = tmp_path / "site"
    (site / "detail").mkdir(parents=True)
    (site / "bynumber").mkdir()

    (site / "LosslessBob.html").write_text(
        "<html><body>"
        "<a href='detail/LB-00001.html'>ok</a>"
        "<a href='detail/LB-99999.html'>gone</a>"
        "<a href='http://example.com/x'>external</a>"
        "<a href='mailto:jeff@example.com'>mail</a>"
        "<a href='#top'>anchor</a>"
        "<img src='detail/pic.png'>"
        "</body></html>",
        encoding="utf-8",
    )
    (site / "detail" / "LB-00001.html").write_text(
        "<html><a href='../LosslessBob.html'>home</a></html>", encoding="utf-8"
    )
    (site / "detail" / "pic.png").write_bytes(b"\x89PNG")
    # The remaining seed pages must exist or the run fails on missing seeds.
    for seed in cml.SEED_PAGES:
        path = site / seed
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<html>seed</html>", encoding="utf-8")
    return site


# ── Extraction ────────────────────────────────────────────────────────────────

def test_extract_links_skips_non_navigable():
    """External, protocol and fragment links are not mirror links."""
    html = ("<a href='a.html'>1</a><a href='http://x.com/y'>2</a>"
            "<a href='//cdn.example/z.css'>3</a><a href='mailto:a@b.c'>4</a>"
            "<a href='#frag'>5</a><img src='p.png'><form action='post.php'>")
    internal, skipped = cml.extract_links(html)
    assert internal == ["a.html", "p.png", "post.php"]
    assert skipped == 4  # external, protocol-relative, mailto, fragment


def test_word_export_scaffolding_is_not_a_link():
    """Word's <link rel="File-List"> tags are not reference continuity.

    Most of losslessbob.com was authored in Microsoft Word, which emits these on
    every page. Counting them would fail all four seed pages over files no
    browser ever fetches.
    """
    html = ("<link href='X_files/filelist.xml' rel='File-List'/>"
            "<link href='X_files/themedata.thmx' rel='themeData'/>"
            "<link href='X_files/colorschememapping.xml' rel='colorSchemeMapping'/>"
            "<link href='style.css' rel='stylesheet'/>"
            "<a href='real.html'>real</a>")
    internal, skipped = cml.extract_links(html)

    assert internal == ["style.css", "real.html"], "stylesheets still matter"
    assert skipped == 3


def test_resolve_link_handles_relative_absolute_and_encoded(tmp_path):
    """Targets resolve relative to the page, or to the mirror root if absolute."""
    site = tmp_path / "site"
    resolve = cml.resolve_link

    assert resolve(site, "detail/LB-1.html", "../index.html") == site / "index.html"
    assert resolve(site, "index.html", "/detail/LB-1.html") == site / "detail" / "LB-1.html"
    assert resolve(site, "index.html", "files/a%20b.txt") == site / "files" / "a b.txt"
    assert resolve(site, "index.html", "detail/x.html?v=2#frag") == site / "detail" / "x.html"
    assert resolve(site, "index.html", "bynumber/") == site / "bynumber" / "index.html"


# ── Checking ──────────────────────────────────────────────────────────────────

def test_finds_broken_link_and_ignores_external(mirror):
    """One dead link is reported; external and mailto links are not."""
    res = cml.check_links(mirror, full=True)

    assert len(res.broken) == 1
    broken = res.broken[0]
    assert broken.page == "LosslessBob.html"
    assert broken.target == "detail/LB-99999.html"
    assert broken.seed is True
    # ok link, dead link, img, plus the back-link on the detail page
    assert res.links == 4
    # home + detail page + the three link-free seed stubs
    assert res.pages == 5
    assert res.seed_pages_checked == len(cml.SEED_PAGES)


def test_seed_break_fails_the_run(mirror):
    """A break on a page people navigate from must fail."""
    res = cml.check_links(mirror, full=True)
    assert res.failed()


def test_clean_mirror_passes(mirror):
    """With the dead link removed, the run is clean."""
    (mirror / "detail" / "LB-99999.html").write_text("<html>now here</html>", encoding="utf-8")

    res = cml.check_links(mirror, full=True)

    assert res.broken == []
    assert not res.failed()


def test_missing_seed_pages_are_reported(tmp_path):
    """A mirror without the seed pages fails — it is not usable for lookup."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "stray.html").write_text("<html>x</html>", encoding="utf-8")

    res = cml.check_links(site, full=True)

    assert len(res.missing_seeds) == len(cml.SEED_PAGES)
    assert res.failed()


def test_non_seed_breaks_are_report_only(tmp_path):
    """Sample findings are surfaced for a human but do not fail the run."""
    site = tmp_path / "site"
    (site / "detail").mkdir(parents=True)
    (site / "bynumber").mkdir()
    for seed in cml.SEED_PAGES:
        path = site / seed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>seed</html>", encoding="utf-8")
    (site / "detail" / "LB-00002.html").write_text(
        "<html><a href='nope.html'>dead</a></html>", encoding="utf-8"
    )

    res = cml.check_links(site, full=True)

    assert len(res.broken) == 1
    assert res.broken[0].seed is False
    assert not res.failed()
    assert res.failed(max_broken=0)


# ── Sampling ──────────────────────────────────────────────────────────────────

def test_sample_is_deterministic_and_includes_seeds(tmp_path):
    """The same mirror yields the same sample on every run."""
    site = tmp_path / "site"
    (site / "detail").mkdir(parents=True)
    (site / "bynumber").mkdir()
    for seed in cml.SEED_PAGES:
        path = site / seed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>seed</html>", encoding="utf-8")
    for i in range(50):
        (site / "detail" / f"LB-{i:05d}.html").write_text("<html>x</html>", encoding="utf-8")

    first = cml.select_pages(site, sample_size=10)
    second = cml.select_pages(site, sample_size=10)

    assert first == second
    assert len(first) == len(cml.SEED_PAGES) + 10
    for seed in cml.SEED_PAGES:
        assert seed in first


def test_full_walks_everything(tmp_path):
    """--full ignores the sample cap."""
    site = tmp_path / "site"
    site.mkdir()
    for i in range(20):
        (site / f"p{i:02d}.html").write_text("<html>x</html>", encoding="utf-8")

    assert len(cml.select_pages(site, full=True)) == 20
    assert len(cml.select_pages(site, full=False, sample_size=5)) == 5


# ── CLI / report ──────────────────────────────────────────────────────────────

def test_cli_exit_codes_and_report(mirror, tmp_path, capsys):
    """main() exits 1 on a seed break, 0 once fixed, and can write a report."""
    argv = ["--site-dir", str(mirror), "--full"]
    assert cml.main(argv) == 1

    (mirror / "detail" / "LB-99999.html").write_text("<html>fixed</html>", encoding="utf-8")
    assert cml.main(argv) == 0

    res = cml.check_links(mirror, full=True)
    report = cml.write_report(res, tmp_path / "exports")
    text = report.read_text(encoding="utf-8")
    assert "http.server" in text, "the report must document how to restore"
    assert "links:" in text


def test_read_only(mirror):
    """The check must not modify the mirror."""
    before = {p: p.stat().st_mtime_ns for p in mirror.rglob("*") if p.is_file()}
    cml.check_links(mirror, full=True)
    after = {p: p.stat().st_mtime_ns for p in mirror.rglob("*") if p.is_file()}
    assert before == after
