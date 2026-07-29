"""Rule-based auto-triage for TapeMatch dates (instructions/complete/TAPEMATCH_AUTOFLAG_SPEC.md).

Only ~43% of dates with a completed TapeMatch run have an ``analysis.md``, and
``tapematch_sync._read_review_flag`` reads the human "needs review" verdict out
of that prose — so the rest carry no review signal at all.  This module derives a
*machine* verdict (``clear`` / ``attention``) for every date straight from
``observations.db``, so the un-analysed backlog can be prioritised instead of
being uniformly unknown.

It deliberately does **not** try to reproduce the human verdict: calibrated
against the 1,362 labelled dates the rules flag with only ~0.19 precision,
because the human reads info-file lineage prose the rules cannot see.  Their
value is the other direction — ~97% of the dates where no rule fires were
human-judged clean.  Treat ``attention`` as "analyse this one first", never as
"this is broken", and keep it out of ``review_flag``, which means a human
actually read the prose.

Usage:
    .venv/bin/python3 -m backend.tapematch_autoflag            # calibration report
"""
import json
import logging
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from backend.paths import TAPEMATCH_RUNS_DIR, TOOLS_DIR

log = logging.getLogger(__name__)

DEFAULT_OBSERVATIONS_DB_PATH = TOOLS_DIR / "tapematch" / "observations.db"

# --- Rule thresholds ---------------------------------------------------------
# A correlation at or below this is "near zero" — no shared audio at all.
NEAR_ZERO_CORR = 0.05
# Duration outlier band, as a ratio against the date's median perf_dur_sec.
DUR_RATIO_LOW = 0.90
DUR_RATIO_HIGH = 1.10
# R7 only means something once a date has enough sources that *every* pair
# failing to correlate is more plausibly an alignment failure than 4+ genuinely
# unrelated tapes of the same show.
ALL_ZERO_MIN_SOURCES = 4

VERDICT_CLEAR = "clear"
VERDICT_ATTENTION = "attention"

# Rule name -> one-line meaning, for --report and for anyone reading the JSON
# reasons column later.
RULES: "dict[str, str]" = {
    "R1_contradiction": "an info-file same-source claim contradicted by near-zero correlation",
    "R3_dur_outlier": "a source whose performance duration is well off the date's median",
    "R5_label_suspect": "tapematch marked a pair's LB labelling suspect",
    "R7_all_zero_multi": "4+ sources and not one pair correlates (likely alignment failure)",
}


def _col(row: sqlite3.Row, key: str, default=None):
    """Read ``key`` from ``row``, or ``default`` if that column doesn't exist.

    observations.db has grown columns over time (``label_suspect`` and the
    fingerprint/embedding scores are recent), and test fixtures build minimal
    tables, so no rule may assume a column is present.
    """
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


def date_signals(run_row: sqlite3.Row, sources: "list[sqlite3.Row]",
                 pairs: "list[sqlite3.Row]") -> "set[str]":
    """Return the set of rule names firing on one run.

    Args:
        run_row: The ``runs`` row for this run (unused by the current rule set,
            accepted so run-level rules can be added without a signature change).
        sources: This run's ``sources`` rows.
        pairs: This run's ``pairs`` rows.

    Returns:
        The names of the fired rules, a subset of :data:`RULES`.
    """
    fired: set[str] = set()

    for p in pairs:
        corr = _col(p, "corr")
        # R1 — the taper/uploader says these are the same tape but there is no
        # shared audio, and tapematch agreed they're unrelated.  The single
        # highest-recall rule in the calibration.
        if (_col(p, "lb_says_same") == 1 and corr is not None and corr < NEAR_ZERO_CORR
                and _col(p, "family_id_a") != _col(p, "family_id_b")):
            fired.add("R1_contradiction")
        if _col(p, "label_suspect") == 1:
            fired.add("R5_label_suspect")

    durs = [d for d in (_col(s, "perf_dur_sec") for s in sources) if d]
    if len(durs) >= 2:
        median = statistics.median(durs)
        if median and any(d / median < DUR_RATIO_LOW or d / median > DUR_RATIO_HIGH
                          for d in durs):
            fired.add("R3_dur_outlier")

    corrs = [c for c in (_col(p, "corr") for p in pairs) if c is not None]
    if len(sources) >= ALL_ZERO_MIN_SOURCES and corrs and max(corrs) < NEAR_ZERO_CORR:
        fired.add("R7_all_zero_multi")

    return fired


def compute_triage(obs_conn: sqlite3.Connection,
                   best_run_by_date: "dict[str, str]") -> "dict[str, tuple[str, str]]":
    """Triage every date in ``best_run_by_date``.

    Args:
        obs_conn: Open connection to tapematch's ``observations.db``.
        best_run_by_date: ``{concert_date: run_id}``, as chosen by
            ``tapematch_sync._pick_best_run`` — passed in rather than re-derived
            so the triage always describes the same run whose families are
            synced.

    Returns:
        ``{concert_date: (verdict, reasons_json)}`` where verdict is
        ``'clear'`` or ``'attention'`` and ``reasons_json`` is a JSON array of
        fired rule names (``"[]"`` when clear).
    """
    wanted = set(best_run_by_date.values())

    runs: dict[str, sqlite3.Row] = {}
    for row in obs_conn.execute("SELECT * FROM runs"):
        if row["run_id"] in wanted:
            runs[row["run_id"]] = row

    sources_by_run: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in obs_conn.execute("SELECT * FROM sources"):
        if row["run_id"] in wanted:
            sources_by_run[row["run_id"]].append(row)

    pairs_by_run: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in obs_conn.execute("SELECT * FROM pairs"):
        if row["run_id"] in wanted:
            pairs_by_run[row["run_id"]].append(row)

    out: dict[str, tuple[str, str]] = {}
    for concert_date, run_id in best_run_by_date.items():
        run_row = runs.get(run_id)
        if run_row is None:
            continue
        fired = date_signals(run_row, sources_by_run.get(run_id, []),
                             pairs_by_run.get(run_id, []))
        verdict = VERDICT_ATTENTION if fired else VERDICT_CLEAR
        out[concert_date] = (verdict, json.dumps(sorted(fired)))
    return out


def _analysed_dates(runs_dir: "Path | None" = None) -> "set[str]":
    """Return the concert dates that have at least one ``analysis.md`` on disk."""
    runs_dir = runs_dir or TAPEMATCH_RUNS_DIR
    dates: set[str] = set()
    if not runs_dir.exists():
        return dates
    for run_dir in runs_dir.iterdir():
        if (run_dir / "analysis.md").exists():
            dates.add(run_dir.name.split("_")[-1])
    return dates


def calibration_report(observations_db_path: "Path | str | None" = None,
                       db_path=None) -> str:
    """Re-measure the rules against the human-labelled dates.

    The labelled set grows by ~25 dates every ``/tapematch-batch`` night, so the
    operating point is worth re-checking periodically: if the clear bucket's
    purity drops below ~0.95 the thresholds need retuning.

    Args:
        observations_db_path: Path to ``observations.db``, or None for default.
        db_path: Main app DB path, or None for the default.

    Returns:
        A printable multi-line report.
    """
    from backend.db import get_connection
    from backend.tapematch_sync import _open_observations_db, _pick_best_run

    obs_conn = _open_observations_db(observations_db_path
                                     or DEFAULT_OBSERVATIONS_DB_PATH)
    try:
        best = _pick_best_run(obs_conn)
        triaged = compute_triage(obs_conn, best)
    finally:
        obs_conn.close()

    conn = get_connection(db_path)
    labels = {
        row["concert_date"]: row["f"]
        for row in conn.execute(
            "SELECT concert_date, MAX(review_flag) AS f "
            "FROM tapematch_family_meta GROUP BY concert_date"
        )
    }
    analysed = _analysed_dates()

    labelled = [(d, v) for d, v in triaged.items() if d in analysed and d in labels]
    flagged = [d for d, _ in labelled if labels[d] == 1]
    clean = [d for d, _ in labelled if labels[d] != 1]

    lines = [
        f"labelled dates: {len(labelled)}  (human-flagged {len(flagged)} / "
        f"clean {len(clean)})",
        "",
        f"{'rule':<20}{'on flagged':>12}{'on clean':>10}{'precision':>11}{'recall':>9}",
    ]
    for rule in RULES:
        tp = sum(1 for d in flagged if rule in triaged[d][1])
        fp = sum(1 for d in clean if rule in triaged[d][1])
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / len(flagged) if flagged else 0.0
        lines.append(f"{rule:<20}{tp:>12}{fp:>10}{prec:>11.2f}{rec:>9.2f}")

    att_flagged = sum(1 for d in flagged if triaged[d][0] == VERDICT_ATTENTION)
    att_clean = sum(1 for d in clean if triaged[d][0] == VERDICT_ATTENTION)
    clear_n = len(labelled) - att_flagged - att_clean
    clear_pure = (len(clean) - att_clean) / clear_n if clear_n else 0.0

    lines += [
        "",
        f"attention: {att_flagged + att_clean} dates "
        f"({(att_flagged + att_clean) / len(labelled):.0%} of labelled), "
        f"precision {att_flagged / (att_flagged + att_clean) if att_flagged + att_clean else 0:.2f}, "
        f"recall {att_flagged / len(flagged) if flagged else 0:.2f}",
        f"clear:     {clear_n} dates, purity {clear_pure:.3f} "
        f"({len(flagged) - att_flagged} human-flagged dates missed)",
        "",
    ]
    if clear_pure < 0.95:
        lines.append("WARNING: clear-bucket purity below 0.95 — retune thresholds.")

    unanalysed = [d for d in triaged if d not in analysed]
    lines.append(
        f"un-analysed dates: {len(unanalysed)} — "
        f"attention {sum(1 for d in unanalysed if triaged[d][0] == VERDICT_ATTENTION)}, "
        f"clear {sum(1 for d in unanalysed if triaged[d][0] == VERDICT_CLEAR)}"
    )
    return "\n".join(lines)


def _main() -> int:
    """CLI entry point: print the calibration report."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(calibration_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
