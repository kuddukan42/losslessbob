"""BUG-328: LB numbers cited in uploader prose must be date-checked before attaching.

Uploader commentary routinely carries typo'd or cross-referenced LB numbers
(``"Source: LB-0897"`` on a 1999-06-20 show, where the real reference was
LB-00857). Attaching those info files inline made the analysis writer reconcile
prose from a different concert as if it were this run's lineage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prep_analysis_input as prep  # noqa: E402

REPORT = """# tapematch session — 1999-06-20 — Anaheim, California, Arrowhead Pond

## Coverage
DB entries: **2** | Found on disk: **2**

| LB | On disk | Rating |
|----|---------|--------|
| LB-00857 | ✓ | B+ |
| LB-11925 | ✓ | B+ |

## LB page commentary

### LB-11925
This is a fixed version of the following torrent: Source: LB-0897, all repairs
made with Audacity. See also LB-04242 for the same tour.
"""

DATE_MAP = {
    "00857": ("6/20/99", "Anaheim, California"),
    "11925": ("6/20/99", "Anaheim, California"),
    "00897": ("6/30/81", "Earle's Court, London"),
    "04242": ("6/20/99", "Anaheim, California"),
}


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "20260710_120810_1999-06-20"
    d.mkdir()
    (d / "report.md").write_text(REPORT, encoding="utf-8")
    return d


@pytest.fixture()
def site_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    files = tmp_path / "files"
    files.mkdir()
    for lb in ("00857", "11925", "00897", "04242", "09999"):
        (files / f"LBF-{lb}-info.txt").write_text(
            f"lineage prose for LB-{lb}, long enough to clear the minimum prose length\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(prep, "SITE_FILES_DIR", files)
    return files


def test_run_date_comes_from_the_dir_name(run_dir: Path) -> None:
    assert prep.run_date_iso(run_dir, "") == "1999-06-20"


def test_run_date_falls_back_to_the_report_title(tmp_path: Path) -> None:
    assert prep.run_date_iso(tmp_path / "hand-made-run", REPORT) == "1999-06-20"


def test_coverage_table_lb_numbers_are_the_runs_own_sources() -> None:
    assert prep.coverage_lb_numbers(REPORT) == {"00857", "11925"}


@pytest.mark.parametrize(
    ("date_str", "iso", "expected"),
    [
        ("6/20/99", "1999-06-20", True),
        ("06/20/99", "1999-06-20", True),
        ("6/30/81", "1999-06-20", False),
        ("6/20/99", "1999-06-21", False),
        ("6/26/66", "1966-06-26", True),
        ("", "1999-06-20", False),
        ("June 20 1999", "1999-06-20", False),
    ],
)
def test_db_date_matches_iso(date_str: str, iso: str, expected: bool) -> None:
    assert prep.db_date_matches_iso(date_str, iso) is expected


def test_off_date_prose_reference_is_segregated(run_dir: Path, site_files: Path) -> None:
    bundle = prep.build_bundle(run_dir, DATE_MAP)
    head, _, cross = bundle.partition("## Cross-references from commentary")

    assert "LBF-00857-info.txt" in head and "LBF-11925-info.txt" in head
    # LB-04242 is prose-only but on the run's date, so it stays inline.
    assert "LBF-04242-info.txt" in head
    # LB-00897 is the typo'd 1981 show and must not sit among this run's sources.
    assert "LBF-00897-info.txt" not in head
    assert "LBF-00897-info.txt" in cross
    assert "[DIFFERENT DATE: 6/30/81, Earle's Court, London]" in cross


def test_lb_number_missing_from_the_db_is_flagged_not_trusted(
    run_dir: Path, site_files: Path
) -> None:
    (run_dir / "report.md").write_text(
        REPORT.replace("LB-04242", "LB-09999"), encoding="utf-8"
    )
    bundle = prep.build_bundle(run_dir, DATE_MAP)
    head, _, cross = bundle.partition("## Cross-references from commentary")

    assert "LBF-09999-info.txt" not in head
    assert "[DATE UNKNOWN — not in the entries table]" in cross


def test_no_cross_reference_section_when_every_reference_is_on_date(
    run_dir: Path, site_files: Path
) -> None:
    (run_dir / "report.md").write_text(
        REPORT.replace("Source: LB-0897, ", ""), encoding="utf-8"
    )
    assert "## Cross-references" not in prep.build_bundle(run_dir, DATE_MAP)


def test_missing_db_yields_an_empty_date_map(tmp_path: Path) -> None:
    assert prep.lb_dates(tmp_path / "nope.db") == {}


def test_missing_db_pushes_prose_references_out_of_the_source_section(
    run_dir: Path, site_files: Path
) -> None:
    """With no date map, an unverifiable prose reference is never inlined."""
    bundle = prep.build_bundle(run_dir, {})
    head, _, cross = bundle.partition("## Cross-references from commentary")

    # Coverage-table sources need no DB lookup — they are on-date by construction.
    assert "LBF-00857-info.txt" in head and "LBF-11925-info.txt" in head
    assert "LBF-00897-info.txt" in cross and "LBF-04242-info.txt" in cross
