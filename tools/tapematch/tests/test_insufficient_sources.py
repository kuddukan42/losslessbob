"""Tests for gen_analysis.py's handling of run_date's insufficient_sources report.

Regression for 1989-09-01: after find_lb_folders drops the no-audio LB-01588
folder, only LB-08627 remains (1 source) — run_date now writes a report.md
marked **insufficient_sources** instead of crashing or being silently skipped.
gen_analysis.py must recognize this marker and emit a clean status section
instead of treating the (error-free, cluster-free) output as ERROR.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gen_analysis  # noqa: E402

REPORT_TEXT = """# tapematch session — 1989-09-01 — Park City, Utah
*Generated: 2026-06-13 12:00:00*

## Coverage
DB entries: **3** | Found on disk: **1**

| LB | On disk | Rating | Timing | Source | Folder |
|----|---------|--------|--------|--------|--------|
| LB-01588 | — |  |  |  | *(not found)* |
| LB-08627 | ✓ | B | 56min+52min | version "a" | 1989-09-01 Salt Lake City, Utah (LB-08627) |
| LB-13295 | — |  |  |  | *(not found)* |

## tapematch output
```
(insufficient sources — tapematch not run)
```

## LB page commentary

### LB-08627 | rating: B | timing: 56min+52min
version "a"

## Status

**insufficient_sources** — only 1 of 3 DB entries have a locally analyzable
recording (private/no-torrent and no-audio folders excluded). tapematch
requires ≥2 sources to compare.
"""


def test_parse_report_detects_insufficient_sources(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text(REPORT_TEXT, encoding="utf-8")

    r = gen_analysis.parse_report(report_path)

    assert r["insufficient_sources"] is True
    assert r["has_error"] is False
    assert r["coverage_db"] == 3
    assert r["coverage_disk"] == 1


def test_build_analysis_insufficient_sources_status(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text(REPORT_TEXT, encoding="utf-8")

    r = gen_analysis.parse_report(report_path)
    content = gen_analysis.build_analysis(tmp_path, r, {})

    assert "insufficient sources" in content.lower()
    assert "ERROR" not in content
    assert "LB-08627" in content
