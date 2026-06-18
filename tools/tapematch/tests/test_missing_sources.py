"""Tests for gen_analysis.py's handling of run_date's missing_sources report.

Regression for the run_crawl.sh infinite loop: when a DB-listed source is
absent from disk and --allow-missing wasn't passed, run_date now archives a
report.md marked **missing_sources** (instead of returning rc=3 with nothing
archived), so --next/--year/--crawl treat the date as done and stop re-picking
it forever. gen_analysis.py must recognize this marker and emit a clean
status section instead of treating the (error-free, cluster-free) output as
ERROR.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gen_analysis  # noqa: E402

REPORT_TEXT = """# tapematch session — 1991-05-05 — Some Venue
*Generated: 2026-06-18 12:00:00*

## Coverage
DB entries: **3** | Found on disk: **2**

| LB | On disk | Rating | Timing | Source | Folder |
|----|---------|--------|--------|--------|--------|
| LB-01000 | ✓ | B | 56min+52min | version "a" | 1991-05-05 Some Venue (LB-01000) |
| LB-02000 | ✓ | B | 56min+52min | version "b" | 1991-05-05 Some Venue (LB-02000) |
| LB-03000 | — |  |  |  | *(not found)* |

## tapematch output
```
(source(s) missing from disk — tapematch not run)
```

## LB page commentary

## Status

**missing_sources** — 1 of 3 DB entries have no folder on disk: LB-03000. Re-run
with --allow-missing to proceed with what's available, or delete this run's
archive dir under data/tapematch/runs/ once the source(s) appear on disk to
make --next/--year/--crawl pick the date up again.
"""


def test_parse_report_detects_missing_sources(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text(REPORT_TEXT, encoding="utf-8")

    r = gen_analysis.parse_report(report_path)

    assert r["missing_sources"] is True
    assert r["insufficient_sources"] is False
    assert r["has_error"] is False
    assert r["coverage_db"] == 3
    assert r["coverage_disk"] == 2


def test_build_analysis_missing_sources_status(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text(REPORT_TEXT, encoding="utf-8")

    r = gen_analysis.parse_report(report_path)
    content = gen_analysis.build_analysis(tmp_path, r, {})

    assert "missing sources" in content.lower()
    assert "ERROR" not in content
    assert "LB-03000" in content
