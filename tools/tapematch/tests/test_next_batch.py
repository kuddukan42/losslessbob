"""Tests for next_batch.py's --newest-per-date and --stats logic (TODO-326).

TODO-326: ``ranked(newest_per_date=True)`` built ``by_date`` from
``eligible_dirs()``, which already excludes run dirs with an analysis.md.
``members[-1:]`` therefore picked the newest *pending* run, not the newest
run that exists on disk — once a date's true newest run was analysed, its
older superseded runs became eligible again and got handed back, producing
contradictory analysis.md files for one date.

These patch the module-level ``RUNS_DIR``/``APP_DB`` constants to point at a
tmp_path fixture, following the ``monkeypatch.setattr`` seam style used in
test_batch_queue.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import next_batch as nb  # noqa: E402

REPORT_OK = "=== CLUSTERS ===\nDB entries: **3**  Found on disk: **3**\n"


def make_run(runs_dir, name, *, report=True, clusters=True, analysis=False):
    """Create a run dir named ``name`` under ``runs_dir``."""
    run_dir = runs_dir / name
    run_dir.mkdir(parents=True)
    if report:
        run_dir.joinpath("report.md").write_text(
            REPORT_OK if clusters else "no clusters here\n", encoding="utf-8"
        )
    if analysis:
        run_dir.joinpath("analysis.md").write_text("# analysis\n", encoding="utf-8")
    return run_dir


def use_tmp_runs(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    monkeypatch.setattr(nb, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(nb, "APP_DB", tmp_path / "no_such.db")
    return runs_dir


def test_newest_analysed_drops_the_date(monkeypatch, tmp_path):
    """Newest run for a date already analysed -> date dropped entirely."""
    runs_dir = use_tmp_runs(monkeypatch, tmp_path)
    make_run(runs_dir, "20260715_055200_2008-09-01")  # older, still pending
    make_run(runs_dir, "20260718_125804_2008-09-01", analysis=True)  # newest, done

    rows = nb.ranked(newest_per_date=True)
    assert rows == []


def test_newest_pending_with_older_analysed_siblings_returns_newest(monkeypatch, tmp_path):
    """Newest run pending, older sibling already analysed -> newest returned."""
    runs_dir = use_tmp_runs(monkeypatch, tmp_path)
    make_run(runs_dir, "20260715_055200_2009-08-04", analysis=True)  # older, done
    newest = make_run(runs_dir, "20260718_131652_2009-08-04")  # newest, pending

    rows = nb.ranked(newest_per_date=True)
    assert len(rows) == 1
    assert rows[0][0] == newest
    assert rows[0][4] == "1/1"


def test_no_analysis_anywhere_returns_newest(monkeypatch, tmp_path):
    """No analysis.md at all for the date -> the newest pending run returned."""
    runs_dir = use_tmp_runs(monkeypatch, tmp_path)
    make_run(runs_dir, "20260715_133621_2009-11-05")
    newest = make_run(runs_dir, "20260718_132027_2009-11-05")

    rows = nb.ranked(newest_per_date=True)
    assert len(rows) == 1
    assert rows[0][0] == newest


def test_newest_not_itself_eligible_drops_date(monkeypatch, tmp_path):
    """True newest run dir exists but isn't eligible (no clusters) -> dropped,
    not handed back as an older, superseded run."""
    runs_dir = use_tmp_runs(monkeypatch, tmp_path)
    make_run(runs_dir, "20260715_000000_2010-01-01")  # older, eligible
    make_run(runs_dir, "20260718_000000_2010-01-01", clusters=False)  # newest, ineligible

    rows = nb.ranked(newest_per_date=True)
    assert rows == []


def test_stats_excludes_superseded_even_without_flag(monkeypatch, tmp_path):
    """--stats semantics: superseded runs are never 'eligible', flag or not."""
    runs_dir = use_tmp_runs(monkeypatch, tmp_path)
    make_run(runs_dir, "20260715_055200_2008-09-01")  # superseded, still pending
    make_run(runs_dir, "20260718_125804_2008-09-01", analysis=True)  # newest, done
    make_run(runs_dir, "20260715_133621_2009-11-05")  # unaffected date, only one run

    superseded = nb.superseded_eligible_dirs()
    assert [p.name for p in superseded] == ["20260715_055200_2008-09-01"]

    # ranked(newest_per_date=False) itself is unfiltered (it hands back
    # contiguous same-date groups as-is); the CLI --stats path is what
    # strips superseded dirs out using the superseded_eligible_dirs() set.
    rows = nb.ranked(newest_per_date=False)
    drop = {p.name for p in superseded}
    filtered = [r for r in rows if r[0].name not in drop]
    filtered_names = {r[0].name for r in filtered}
    assert "20260715_055200_2008-09-01" not in filtered_names
    assert "20260715_133621_2009-11-05" in filtered_names
