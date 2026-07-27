#!/usr/bin/env python3
"""TODO-273 — classify the curator-contradicted pairs into failure classes.

A "contradicted" pair is one where LB curator commentary asserts the two
recordings share a source (``lb_says_same=1``) but the latest tapematch run
placed them in different families. Nobody has ever measured what that
population actually consists of; TODO-185 characterised a single date
(1991-11-05 Madison) and the patchwork/segment-overlap reading was
generalised from that one example without being checked.

This is deliberately a METADATA census -- it reads ``observations.db`` only
and decodes no audio, so it is cheap to re-run as the corpus grows. It
assigns every pair to exactly one bucket using a priority-ordered rule chain
(first match wins), and separately reports the non-exclusive marker overlaps
so the ordering choice can be audited rather than trusted.

Buckets, in priority order:
    lb_collision      -- BUG-277: a folder name carries more than one distinct
                         LB tag, so the pair may be attributed to the wrong
                         entry entirely. Checked first because it invalidates
                         the pair's identity, not merely its verdict.
    label_contradiction -- the curator text backing the same-source claim also
                         contains explicit "different recording" language.
                         Marker 1 of TODO-201, applied corpus-wide here rather
                         than to the frozen set only.
    duration_mismatch -- speed-corrected performance durations differ by more
                         than ``DURATION_RATIO_THR``. Marker 2 of TODO-201:
                         either the claim is wrong or one side is incomplete.
    alignment_failure -- at least one side is speed-unknown or staircase/splice,
                         i.e. the ratio estimator never locked and the pair was
                         routed to the fingerprint path. TODO-204's territory.
    segment_patchwork -- curator text makes a localised, track-scoped claim
                         (the TODO-185 class, known unrescuable with current
                         signals).
    unexplained       -- none of the above.

Usage:
    .venv/bin/python3 tools/tapematch/census_contradicted.py [--out PATH]
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

SESSION_DIR = Path(__file__).resolve().parent
OBS_DB_PATH = SESSION_DIR / "observations.db"
DEFAULT_OUT = SESSION_DIR / "CONTRADICTED_CENSUS.md"

# Speed-corrected duration ratio above which the two sides cannot be the same
# performance (TODO-201 marker 2 uses the same 15% bar).
DURATION_RATIO_THR = 1.15

# Explicit curator disclaimers. Deliberately narrow: these phrases are only
# written when someone is denying a match, so a hit alongside lb_says_same=1
# means the claim and the disclaimer sit in the same blob.
RE_DIFFERENT = re.compile(
    r"different recording|different source|not the same (?:recording|source|tape)"
    r"|unrelated|distinct source|is not LB-",
    re.I,
)

# TRUE patchwork/composite markers -- the TODO-185 class. Note what is NOT here:
# "same clapping wavs at end of dNtN" was tried first and is wrong. That phrase
# is not a description of a patchwork composite, it is the STOCK JUSTIFICATION
# LB curators write when asserting any same-source claim ("same recording as
# LB-NNNN based on same clapping wavs at end of d1t7"). It appears in 54.7% of
# contradicted claims but also 39.7% of claims tapematch confirms, and in 0.0%
# of pairs where the curator is silent -- an evidence-provenance marker, not a
# failure-class marker. It is reported separately under RE_CLAP_EVIDENCE.
RE_SEGMENT = re.compile(
    r"patch(?:ed|work)|filler|incomplete|missing (?:track|song|material)"
    r"|spliced from|composite",
    re.I,
)

# The curator's stock same-source justification (see note above). Orthogonal to
# the failure buckets: it says how the claim was made, not why it failed.
RE_CLAP_EVIDENCE = re.compile(r"clapping wavs|same clap", re.I)

RE_LB_TAG = re.compile(r"LB-(\d+)")

# speed_kind values meaning "the aligner did not lock".
UNLOCKED_SPEED_KINDS = {"speed-unknown", "staircase/splice", "insufficient"}

BUCKET_ORDER = [
    "lb_collision",
    "label_contradiction",
    "duration_mismatch",
    "alignment_failure",
    "segment_patchwork",
    "unexplained",
]

log = logging.getLogger("census")


def duration_ratio(row: dict[str, Any]) -> float | None:
    """Ratio of the longer to the shorter performance duration, or None."""
    a, b = row["perf_dur_sec_a"], row["perf_dur_sec_b"]
    if not a or not b:
        return None
    return max(a, b) / min(a, b)


def folder_lb_tags(folder: str | None) -> set[int]:
    """Distinct LB numbers appearing in a source folder name."""
    return {int(n) for n in RE_LB_TAG.findall(folder or "")}


def markers(row: dict[str, Any]) -> dict[str, bool]:
    """Compute every marker for one pair, independent of bucket priority."""
    text = row["lb_relation_text"] or ""
    ratio = duration_ratio(row)
    return {
        "lb_collision": (
            len(folder_lb_tags(row["folder_a"])) > 1
            or len(folder_lb_tags(row["folder_b"])) > 1
            or row["lb_a"] == row["lb_b"]
        ),
        "label_contradiction": bool(RE_DIFFERENT.search(text)),
        "duration_mismatch": ratio is not None and ratio > DURATION_RATIO_THR,
        "alignment_failure": (
            row["speed_kind_a"] in UNLOCKED_SPEED_KINDS
            or row["speed_kind_b"] in UNLOCKED_SPEED_KINDS
        ),
        "segment_patchwork": bool(RE_SEGMENT.search(text)),
    }


def classify(mk: dict[str, bool]) -> str:
    """Assign one bucket by first-match-wins over BUCKET_ORDER."""
    for name in BUCKET_ORDER[:-1]:
        if mk[name]:
            return name
    return "unexplained"


def load_rows(db_path: Path) -> list[dict[str, Any]]:
    """Fetch the contradicted-claim population from latest_pairs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """SELECT * FROM latest_pairs
           WHERE lb_says_same = 1 AND tapematch_verdict = 'different_family'
           ORDER BY concert_date, lb_a, lb_b"""
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _pct(n: int, total: int) -> str:
    return f"{100.0 * n / total:.1f}%" if total else "—"


def build_report(rows: list[dict[str, Any]]) -> str:
    """Render the census as a markdown report."""
    total = len(rows)
    all_markers = [markers(r) for r in rows]
    buckets = [classify(mk) for mk in all_markers]
    bcount = Counter(buckets)
    mcount = Counter(k for mk in all_markers for k, v in mk.items() if v)
    n_markers = Counter(sum(mk.values()) for mk in all_markers)

    out: list[str] = []
    out.append("# Curator-contradicted pair census (TODO-273)\n")
    out.append(
        f"Population: **{total} pairs** across "
        f"**{len({r['concert_date'] for r in rows})} dates** where "
        "`lb_says_same=1` but the latest run said `different_family`.\n"
    )
    out.append(
        "Metadata only — no audio decoded. Regenerate with "
        "`.venv/bin/python3 tools/tapematch/census_contradicted.py`.\n"
    )

    out.append("\n## Buckets (priority-ordered, mutually exclusive)\n")
    out.append("| Bucket | Pairs | Share |")
    out.append("|---|---:|---:|")
    for name in BUCKET_ORDER:
        out.append(f"| `{name}` | {bcount.get(name, 0)} | {_pct(bcount.get(name, 0), total)} |")

    out.append("\n## Markers (non-exclusive — a pair can carry several)\n")
    out.append("| Marker | Pairs | Share |")
    out.append("|---|---:|---:|")
    for name in BUCKET_ORDER[:-1]:
        out.append(f"| `{name}` | {mcount.get(name, 0)} | {_pct(mcount.get(name, 0), total)} |")

    out.append("\nMarkers per pair:\n")
    out.append("| Markers matched | Pairs |")
    out.append("|---:|---:|")
    for k in sorted(n_markers):
        out.append(f"| {k} | {n_markers[k]} |")

    out.append("\n## Correlation of the contradicted population\n")
    cs = [r["corr"] for r in rows if r["corr"] is not None]
    bands = [("< 0.05", lambda x: x < 0.05), ("0.05–0.20", lambda x: 0.05 <= x < 0.20),
             ("0.20–0.40", lambda x: 0.20 <= x < 0.40), ("≥ 0.40", lambda x: x >= 0.40)]
    out.append("| corr band | Pairs |")
    out.append("|---|---:|")
    for label, fn in bands:
        out.append(f"| {label} | {sum(1 for x in cs if fn(x))} |")

    out.append("\n## Curator evidence standard (orthogonal to the buckets)\n")
    out.append(
        "LB curators justify most same-source claims with one stock formula: "
        "_\"same recording as LB-NNNN based on same clapping wavs at end of dXtY\"_ "
        "— a single localised waveform comparison. Base rates below show how far "
        "that evidence standard carries.\n"
    )
    out.append("| Population | Pairs | Clap-phrase | Rate |")
    out.append("|---|---:|---:|---:|")
    conn = sqlite3.connect(OBS_DB_PATH)
    conn.row_factory = sqlite3.Row
    groups = [
        ("curator says SAME, tapematch agrees",
         "lb_says_same=1 AND tapematch_verdict='same_family'"),
        ("curator says SAME, tapematch contradicts",
         "lb_says_same=1 AND tapematch_verdict='different_family'"),
        ("curator says DIFFERENT", "lb_says_same=0"),
        ("curator silent", "lb_says_same IS NULL"),
    ]
    agree_with = agree_without = contra_with = contra_without = 0
    for label, where in groups:
        recs = conn.execute(
            f"SELECT lb_relation_text FROM latest_pairs WHERE {where}"
        ).fetchall()
        hits = sum(1 for r in recs if RE_CLAP_EVIDENCE.search(r[0] or ""))
        out.append(f"| {label} | {len(recs)} | {hits} | {_pct(hits, len(recs))} |")
        if where == groups[0][1]:
            agree_with, agree_without = hits, len(recs) - hits
        elif where == groups[1][1]:
            contra_with, contra_without = hits, len(recs) - hits
    conn.close()

    with_tot = agree_with + contra_with
    without_tot = agree_without + contra_without
    out.append(
        f"\nSo a same-source claim justified by clapping-wavs is confirmed by tapematch "
        f"**{_pct(agree_with, with_tot)}** of the time ({agree_with}/{with_tot}); one "
        f"justified some other way is confirmed **{_pct(agree_without, without_tot)}** "
        f"of the time ({agree_without}/{without_tot}). The heuristic is measurably "
        "weaker, but it is not noise — it is right more often than not-quite-half the "
        "time, and it is absent entirely from pairs the curator does not claim.\n"
    )

    out.append("\n## Worked examples per bucket\n")
    for name in BUCKET_ORDER:
        picks = [r for r, b in zip(rows, buckets) if b == name][:5]
        out.append(f"\n### `{name}` ({bcount.get(name, 0)} pairs)\n")
        if not picks:
            out.append("_none_\n")
            continue
        out.append("| Date | Pair | corr | dur ratio | speed_kind a/b |")
        out.append("|---|---|---:|---:|---|")
        for r in picks:
            ratio = duration_ratio(r)
            out.append(
                f"| {r['concert_date']} | LB-{r['lb_a']}/LB-{r['lb_b']} | "
                f"{(r['corr'] or 0):.4f} | {ratio:.3f} | "
                f"{r['speed_kind_a']}/{r['speed_kind_b']} |"
                if ratio is not None else
                f"| {r['concert_date']} | LB-{r['lb_a']}/LB-{r['lb_b']} | "
                f"{(r['corr'] or 0):.4f} | — | {r['speed_kind_a']}/{r['speed_kind_b']} |"
            )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"report path (default: {DEFAULT_OUT.name})")
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rows = load_rows(args.db)
    log.info("loaded %d contradicted pairs", len(rows))
    args.out.write_text(build_report(rows))
    log.info("report -> %s", args.out)

    bcount = Counter(classify(markers(r)) for r in rows)
    for name in BUCKET_ORDER:
        log.info("  %-20s %5d", name, bcount.get(name, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
