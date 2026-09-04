#!/usr/bin/env python3
"""TODO-336 — census the untested polarity: LB says different, tapematch merged.

``census_contradicted.py`` measures one polarity only (``lb_says_same=1`` with
a ``different_family`` verdict — the recall problem). This is its mirror: pairs
where the curator's commentary does NOT claim a shared source
(``lb_says_same=0``) but the latest run put both recordings in the same family.

These matter more per pair than the recall misses. A miss merely leaves two
tapes separate; a false merge silently collapses two distinct tapes into one
family in the app DB, which then under-counts source tapes everywhere
downstream (TODO-335's rarity census included).

The population splits into two queues that must be worked separately, and the
split is by MECHANISM, not by a corr cut:

    lb_error_candidate -- the pair links on primary correlation, i.e. the
                          waveform evidence is decisive and the interesting
                          question is whether the LB pages are wrong. These are
                          catalogue-correction candidates, few enough to listen
                          to by hand.
    weak_link          -- the pair links on a secondary / hiss / fingerprint /
                          triplet / addon-rule leg with primary correlation
                          below ``match.cluster_threshold``. This is exactly
                          the failure class TODO-325 and TODO-319 are chasing;
                          hold these as a validation set for whichever
                          corroboration floor ships rather than adjudicating
                          them by hand first.
    chained            -- no direct leg links the pair at all: the two ended up
                          in one family transitively, through a third source.
                          A false merge here is a property of the chain, not of
                          this pair, so it is TODO-319's territory.

Mechanism attribution runs the shipped ``config.yaml`` through
``verdict.link_mechanism``, which is the same OR-chain the clusterer used, so
a leg named here is the leg the run actually merged on. Two caveats worth
reading the output with: the stored rows are a patchwork of calibration eras
(TODO-333), so re-deciding an old row under today's config can disagree with
the verdict the run recorded; and any leg whose signal column is NULL on a
historical row abstains, which is why ``chained`` is a floor, not an exact
count.

One label-quality caveat the census measures rather than assumes: the
``lb_says_same=0`` label comes from ``extract_lb_relationship``, which searches
a +/-250 character window around a mention of the other side's LB number on
this side's page and returns 0 as soon as ``backend.db._DIFF_RE`` matches
anywhere in that window. Nothing checks that the denial is ABOUT the pair, so a
page reading "different recording than LB-3160" that happens to mention the
pair's other side within the same window is scored as a denial of the pair.
Each row therefore carries a ``denial_scope``: ``third_party`` when the phrase
is immediately followed by some other LB number, ``pair_scoped`` otherwise.
A ``third_party`` row is not evidence the curator disputes this pair at all,
and should not be counted against the matcher.

Metadata only -- reads observations.db and decodes no audio, so it is cheap to
re-run as a floor lands or the corpus grows.

Usage:
    .venv/bin/python3 tools/tapematch/census_false_merge.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

SESSION_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SESSION_DIR))

if str(SESSION_DIR.parents[1]) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR.parents[1]))

from tapematch import verdict as V  # noqa: E402

from backend.db import _DIFF_RE  # noqa: E402

# LB numbers, however the pages write them (LB-1234, LB 01234).
RE_LB_TAG = re.compile(r"LB[-\s]?0*(\d+)", re.I)

# How far after the denial phrase to look for the LB number it is about. The
# curator formula is "different recording than LB-NNNN", so the number sits
# within a few words when it is named at all.
DENIAL_SCOPE_WINDOW = 60

OBS_DB_PATH = SESSION_DIR / "observations.db"
CONFIG_PATH = SESSION_DIR / "config.yaml"
LB_DB_PATH = SESSION_DIR.parents[1] / "data" / "losslessbob.db"
DEFAULT_OUT = SESSION_DIR / "FALSE_MERGE_CENSUS.md"
DEFAULT_JSON = SESSION_DIR.parents[1] / "data" / "tapematch" / "false_merge_queue.json"

# Legs that carry decisive primary correlation vs. everything else.
PRIMARY_LEGS = {"primary"}

QUEUES = ["lb_error_candidate", "weak_link", "chained"]

# Dates already named in the over-merge TODOs, so the census can show its
# overlap with work that is already scoped rather than re-filing it.
TODO_319_DATES = {"1999-10-26", "1997-12-18", "2002-04-28", "2011-10-21", "2007-04-08"}
TODO_325_DATES = {"2008-07-08", "1990-06-01", "2024-03-05", "2024-11-08",
                  "1981-06-21", "2023-04-20", "1995-06-16"}

log = logging.getLogger("false_merge_census")


def load_rows(db_path: Path) -> list[dict[str, Any]]:
    """Fetch the false-merge-candidate population from ``latest_pairs``."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """SELECT * FROM latest_pairs
           WHERE lb_says_same = 0 AND tapematch_verdict = 'same_family'
           ORDER BY concert_date, lb_a, lb_b"""
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def denial_scope(row: dict[str, Any]) -> str:
    """Whether the stored denial phrase is about this pair or a third recording.

    Args:
        row: A ``latest_pairs`` row with ``lb_relation_text``, ``lb_a``, ``lb_b``.

    Returns:
        ``third_party`` if the denial phrase is directly followed by an LB
        number that is neither side of this pair, else ``pair_scoped``.
    """
    text = row["lb_relation_text"] or ""
    m = _DIFF_RE.search(text)
    if not m:
        return "pair_scoped"
    tail = text[m.end():m.end() + DENIAL_SCOPE_WINDOW]
    nums = [int(n) for n in RE_LB_TAG.findall(tail)]
    if nums and nums[0] not in (row["lb_a"], row["lb_b"]):
        return "third_party"
    return "pair_scoped"


def queue_of(mechanism: str | None) -> str:
    """Map a link mechanism to its work queue."""
    if mechanism is None:
        return "chained"
    return "lb_error_candidate" if mechanism in PRIMARY_LEGS else "weak_link"


def classify(rows: list[dict[str, Any]], cfg: dict[str, Any],
             lineage: set[tuple[int, int]]) -> list[tuple[str, str | None]]:
    """Return ``(queue, mechanism)`` for each row, in input order."""
    out: list[tuple[str, str | None]] = []
    for r in rows:
        mech = V.link_mechanism(r, cfg, lineage)
        out.append((queue_of(mech), mech))
    return out


def _pct(n: int, total: int) -> str:
    return f"{100.0 * n / total:.1f}%" if total else "—"


def _corr(r: dict[str, Any]) -> str:
    return "—" if r["corr"] is None else f"{r['corr']:.4f}"


def _todo_mark(date: str) -> str:
    marks = []
    if date in TODO_319_DATES:
        marks.append("319")
    if date in TODO_325_DATES:
        marks.append("325")
    return "/".join(marks) or "—"


def build_report(rows: list[dict[str, Any]],
                 verdicts: list[tuple[str, str | None]],
                 cfg: dict[str, Any]) -> str:
    """Render the census as a markdown report."""
    total = len(rows)
    queues = [q for q, _ in verdicts]
    qcount = Counter(queues)
    mcount = Counter(m or "(none — chained)" for _, m in verdicts)
    thr = (cfg.get("match", {}) or {}).get("cluster_threshold")

    by_date: dict[str, int] = defaultdict(int)
    for r in rows:
        by_date[r["concert_date"]] += 1

    out: list[str] = []
    out.append("# False-merge census — LB says different, tapematch merged (TODO-336)\n")
    out.append(
        f"Population: **{total} pairs** across **{len(by_date)} dates** where "
        "`lb_says_same=0` but the latest run said `same_family`.\n"
    )
    out.append(
        "Metadata only — no audio decoded. Mechanism is attributed by replaying the "
        "shipped `config.yaml` through `verdict.link_mechanism`, so it reflects "
        "TODAY's config, not necessarily the calibration era each row was run under "
        "(TODO-333). Regenerate with "
        "`.venv/bin/python3 tools/tapematch/census_false_merge.py`.\n"
    )

    out.append("\n## Work queues\n")
    out.append("| Queue | Pairs | Share |")
    out.append("|---|---:|---:|")
    for name in QUEUES:
        out.append(f"| `{name}` | {qcount.get(name, 0)} | {_pct(qcount.get(name, 0), total)} |")
    out.append(
        f"\n`lb_error_candidate` = links on primary corr ≥ `match.cluster_threshold` "
        f"({thr}); `weak_link` = links on a secondary/fingerprint/addon leg below it; "
        "`chained` = no direct leg fires under today's config, so the family edge came "
        "through a third source.\n"
    )

    scopes = Counter(denial_scope(r) for r in rows)
    scope_by_queue: dict[str, Counter] = defaultdict(Counter)
    for r, (q, _) in zip(rows, verdicts, strict=True):
        scope_by_queue[q][denial_scope(r)] += 1
    out.append("\n## Denial scope — is the curator actually disputing THIS pair?\n")
    out.append(
        "`lb_says_same=0` is set when a `_DIFF_RE` phrase appears anywhere in a "
        "±250-character window around a mention of the other side's LB number. When "
        "that phrase is immediately followed by a THIRD LB number, the curator was "
        "denying a different match and this pair was caught by proximity — such a row "
        "is not evidence against the matcher.\n"
    )
    out.append("| Queue | pair_scoped | third_party |")
    out.append("|---|---:|---:|")
    for name in QUEUES:
        out.append(f"| `{name}` | {scope_by_queue[name]['pair_scoped']} | "
                   f"{scope_by_queue[name]['third_party']} |")
    out.append(f"| **all** | {scopes['pair_scoped']} | {scopes['third_party']} |")

    out.append("\n## Link mechanism\n")
    out.append("| Mechanism | Pairs |")
    out.append("|---|---:|")
    for name, n in mcount.most_common():
        out.append(f"| `{name}` | {n} |")

    out.append("\n## Correlation distribution\n")
    bands = [("< 0.05", lambda x: x < 0.05), ("0.05–0.20", lambda x: 0.05 <= x < 0.20),
             ("0.20–0.45", lambda x: 0.20 <= x < 0.45), ("0.45–0.75", lambda x: 0.45 <= x < 0.75),
             ("≥ 0.75", lambda x: x >= 0.75)]
    cs = [r["corr"] for r in rows if r["corr"] is not None]
    out.append("| corr band | Pairs |")
    out.append("|---|---:|")
    for label, fn in bands:
        out.append(f"| {label} | {sum(1 for x in cs if fn(x))} |")
    n_null = total - len(cs)
    if n_null:
        out.append(f"| (no corr recorded) | {n_null} |")

    out.append("\n## Dates by pair count\n")
    out.append("| Date | Pairs | Already in TODO |")
    out.append("|---|---:|---|")
    for date, n in sorted(by_date.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        out.append(f"| {date} | {n} | {_todo_mark(date)} |")

    for qname in QUEUES:
        picks = [(r, m) for r, (q, m) in zip(rows, verdicts, strict=True) if q == qname]
        out.append(f"\n## Queue `{qname}` ({len(picks)} pairs)\n")
        if not picks:
            out.append("_none_\n")
            continue
        if qname == "lb_error_candidate":
            out.append(
                "Listen to these. Primary correlation is decisive, so either the "
                "waveform match is real and the LB pages need a catalogue correction, "
                "or the pair identity itself is wrong (BUG-277 folder collisions).\n"
            )
        elif qname == "weak_link":
            out.append(
                "Do NOT adjudicate by hand yet — re-run this census after a TODO-325 "
                "floor ships. A floor that clears these without costing frozen-set "
                "true positives is a floor worth shipping.\n"
            )
        else:
            out.append(
                "Transitive merges: the family edge is a property of the chain, not "
                "of this pair. TODO-319's territory.\n"
            )
        out.append("| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |")
        out.append("|---|---|---:|---|---|---|---|")
        for r, m in picks if qname != "weak_link" else picks[:40]:
            out.append(
                f"| {r['concert_date']} | LB-{r['lb_a']}/LB-{r['lb_b']} | {_corr(r)} | "
                f"`{m or '—'}` | {denial_scope(r)} | "
                f"{r['speed_kind_a']}/{r['speed_kind_b']} | "
                f"{_todo_mark(r['concert_date'])} |"
            )
        if qname == "weak_link" and len(picks) > 40:
            out.append(f"\n_… {len(picks) - 40} more; full list in the JSON queue file._\n")
    return "\n".join(out) + "\n"


def build_queue_json(rows: list[dict[str, Any]],
                     verdicts: list[tuple[str, str | None]]) -> dict[str, Any]:
    """Machine-readable per-queue pair lists, for re-checking after a floor lands."""
    queues: dict[str, list[dict[str, Any]]] = {name: [] for name in QUEUES}
    for r, (q, m) in zip(rows, verdicts, strict=True):
        queues[q].append({
            "concert_date": r["concert_date"],
            "lb_a": r["lb_a"],
            "lb_b": r["lb_b"],
            "corr": r["corr"],
            "mechanism": m,
            "denial_scope": denial_scope(r),
            "windowed_frac": r["windowed_frac"],
            "hiss_frac": r["hiss_frac"],
            "fp_score": r["fp_score"],
            "fp_triplet_score": r["fp_triplet_score"],
            "emb_score": r["emb_score"],
            "emb_score_global": r["emb_score_global"],
            "speed_kind_a": r["speed_kind_a"],
            "speed_kind_b": r["speed_kind_b"],
            "run_at": r["run_at"],
        })
    return {"total": len(rows), "queues": queues}


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"report path (default: {DEFAULT_OUT.name})")
    ap.add_argument("--json-out", type=Path, default=DEFAULT_JSON,
                    help="machine-readable queue path")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    lineage = V.load_lineage_pairs(LB_DB_PATH) if LB_DB_PATH.exists() else set()

    rows = load_rows(args.db)
    log.info("loaded %d false-merge-candidate pairs", len(rows))
    verdicts = classify(rows, cfg, lineage)

    args.out.write_text(build_report(rows, verdicts, cfg))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(build_queue_json(rows, verdicts), indent=2))
    log.info("report -> %s", args.out)
    log.info("queue  -> %s", args.json_out)

    qcount = Counter(q for q, _ in verdicts)
    for name in QUEUES:
        log.info("  %-20s %5d", name, qcount.get(name, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
