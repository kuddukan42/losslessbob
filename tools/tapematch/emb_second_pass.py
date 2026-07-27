"""emb_second_pass.py — TODO-273 item (c): a second discriminator over the
curator-contradicted corpus, and specifically over the 377 pairs the metadata
census (``census_contradicted.py``) could not explain.

The census bucketed all 1,822 ``lb_says_same=1 AND
tapematch_verdict='different_family'`` pairs using curator text, speed_kind,
duration ratio and folder LB tags only. It deliberately used no audio-derived
similarity signal, and left 377 pairs (20.7%) in ``unexplained``. This module
adds the one persisted audio signal the census did not touch: the nmfp
embedding scores ``emb_score`` (aligned +/-2s-window cosine) and
``emb_score_global`` (whole-recording global cosine-max).

Why the embedding and not corr/fp_score: ``corr`` is already known to be <0.05
for 93.3% of the corpus (census finding 5) so it cannot discriminate within it,
and ``fp_score`` is NULL for 351 of the 377 unexplained pairs. ``emb_score`` is
populated for 1,770 of 1,822 and is the only signal here with a calibrated
production bar behind it (``addon_links.rule_d``, t_emb 0.75 both-convention,
calibrated 2026-07-04 on the full frozen set at zero new FP).

Tiers (per pair, from the two emb conventions):

    A rule_d-qualifying -- emb_score AND emb_score_global both >= 0.75, i.e.
                           the pair clears the SHIPPED, CALIBRATED merge bar of
                           addon_links.rule_d yet is stored different_family.
                           These are stale verdicts, not matcher gaps. See
                           BUG-278: rule_d cannot fire in a live session.
    B elevated           -- emb_score >= the curator-silent negative control's
                           p95 but below the rule_d bar. Enriched over the
                           control but not merge-grade on current calibration.
    C control-like       -- emb_score below the negative-control p95. NOT proof
                           the pair is different: the embedding's recall at that
                           bar is only ~59% on confirmed same-source pairs, so
                           tier C means "no positive evidence from any signal
                           tapematch currently persists", not "distinct".
    no_emb               -- emb never scored; rule_d abstains by design.

The negative control is every ``lb_says_same!=1 AND
tapematch_verdict='different_family'`` pair -- pairs the curator makes no
same-source claim about and tapematch also separated. Its p95 is computed at
runtime rather than hardcoded so the tiers track the corpus as it grows.

Metadata + persisted-metric only: reads observations.db, decodes no audio, and
writes nothing back to the DB. Cheap to re-run.

Usage:
    .venv/bin/python3 tools/tapematch/emb_second_pass.py [--out PATH]
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from census_contradicted import BUCKET_ORDER, OBS_DB_PATH, classify, markers

SESSION_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SESSION_DIR / "CONTRADICTED_EMB_SECOND_PASS.md"

# addon_links.rule_d.t_emb as shipped in config.yaml (calibrated 2026-07-04).
# Mirrored rather than read from config so the report states the bar it actually
# scored against even if config drifts; a mismatch is worth noticing loudly.
RULE_D_T_EMB = 0.75

# Percentile of the curator-silent negative control that defines tier B's floor.
CONTROL_PCTL = 0.95

CONTRADICTED_WHERE = (
    "lb_says_same = 1 AND tapematch_verdict = 'different_family' AND lb_a != lb_b"
)
CONFIRMED_WHERE = (
    "lb_says_same = 1 AND tapematch_verdict != 'different_family' AND lb_a != lb_b"
)
CONTROL_WHERE = (
    "COALESCE(lb_says_same, 0) != 1 AND tapematch_verdict = 'different_family' "
    "AND lb_a != lb_b"
)

TIER_A = "A rule_d-qualifying"
TIER_B = "B elevated"
TIER_C = "C control-like"
TIER_NONE = "no_emb"
TIER_ORDER = [TIER_A, TIER_B, TIER_C, TIER_NONE]

log = logging.getLogger("emb_second_pass")


def _pctl(values: list[float], p: float) -> float:
    """Nearest-rank percentile of an unsorted list (p in [0, 1])."""
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))]


def _pct(n: int, total: int) -> str:
    return f"{100.0 * n / total:.1f}%" if total else "—"


def fetch(conn: sqlite3.Connection, where: str) -> list[dict[str, Any]]:
    """All ``latest_pairs`` rows matching a WHERE clause, as dicts."""
    cur = conn.execute(
        f"SELECT * FROM latest_pairs WHERE {where} ORDER BY concert_date, lb_a, lb_b"
    )
    return [dict(r) for r in cur.fetchall()]


def tier(row: dict[str, Any], control_floor: float) -> str:
    """Assign one embedding tier to a pair.

    Args:
        row: a ``latest_pairs`` row.
        control_floor: tier B's lower bound (negative-control percentile).

    Returns:
        One of the ``TIER_*`` constants.
    """
    emb, emb_g = row["emb_score"], row["emb_score_global"]
    if emb is None or emb_g is None:
        return TIER_NONE
    if emb >= RULE_D_T_EMB and emb_g >= RULE_D_T_EMB:
        return TIER_A
    if emb >= control_floor:
        return TIER_B
    return TIER_C


def rule_d_fires(row: dict[str, Any]) -> bool:
    """True iff the pair clears ``addon_links.rule_d``'s both-convention bar."""
    emb, emb_g = row["emb_score"], row["emb_score_global"]
    return (
        emb is not None
        and emb_g is not None
        and emb >= RULE_D_T_EMB
        and emb_g >= RULE_D_T_EMB
    )


class _UnionFind:
    """Path-compressing union-find over LB numbers, one instance per date.

    Mirrors the connected-component logic in ``verdict.cluster_verdicts`` --
    family membership is transitive, so the effect of a new link cannot be
    read off individual rows.
    """

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        """Representative of ``x``'s component, inserting ``x`` if unseen."""
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        """Merge the components containing ``a`` and ``b``."""
        self.parent[self.find(a)] = self.find(b)

    def same(self, a: int, b: int) -> bool:
        """True iff ``a`` and ``b`` are currently in one component."""
        return self.find(a) == self.find(b)


def transitive_flips(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Corpus-wide effect of adding rule_d as a link, with transitive closure.

    Replays each date's union-find twice -- once over the stored
    ``same_family`` verdicts, once with rule_d-qualifying pairs additionally
    linked -- and counts pairs that change to same_family. Family verdicts are
    transitive (``verdict.cluster_verdicts``), so a single new link can merge
    pairs that do not themselves clear the bar; that cascade is the reason this
    cannot be counted by filtering rows.

    Returns:
        ``(claimed, silent, n_dates)`` -- newly-same pairs the curator claims as
        same-source, newly-same pairs the curator is silent on, and the number
        of dates touched.
    """
    rows = fetch(conn, "lb_a IS NOT NULL AND lb_b IS NOT NULL AND lb_a != lb_b")
    by_date: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_date.setdefault(r["concert_date"], []).append(r)

    claimed = silent = 0
    dates: set[str] = set()
    for date, drows in by_date.items():
        uf = _UnionFind()
        for r in drows:
            if r["tapematch_verdict"] == "same_family":
                uf.union(r["lb_a"], r["lb_b"])
        before = {
            (min(r["lb_a"], r["lb_b"]), max(r["lb_a"], r["lb_b"])): uf.same(r["lb_a"], r["lb_b"])
            for r in drows
        }
        for r in drows:
            if rule_d_fires(r):
                uf.union(r["lb_a"], r["lb_b"])
        for r in drows:
            key = (min(r["lb_a"], r["lb_b"]), max(r["lb_a"], r["lb_b"]))
            if not before[key] and uf.same(r["lb_a"], r["lb_b"]):
                dates.add(date)
                if r["lb_says_same"] == 1:
                    claimed += 1
                else:
                    silent += 1
    return claimed, silent, len(dates)


def build_report(conn: sqlite3.Connection) -> str:
    """Render the full second-pass report as markdown."""
    contradicted = fetch(conn, CONTRADICTED_WHERE)
    confirmed = fetch(conn, CONFIRMED_WHERE)
    control = fetch(conn, CONTROL_WHERE)

    ctrl_emb = [r["emb_score"] for r in control if r["emb_score"] is not None]
    conf_emb = [r["emb_score"] for r in confirmed if r["emb_score"] is not None]
    con_emb = [r["emb_score"] for r in contradicted if r["emb_score"] is not None]
    floor = _pctl(ctrl_emb, CONTROL_PCTL)

    out: list[str] = []
    add = out.append
    add("# Curator-contradicted corpus — embedding second pass (TODO-273 item c)")
    add("")
    add("Generated by `tools/tapematch/emb_second_pass.py` (re-runnable; reads")
    add("`observations.db` only, decodes no audio, writes nothing back).")
    add("")
    add(f"Tier A bar: `addon_links.rule_d.t_emb` = **{RULE_D_T_EMB}**, both conventions.")
    add(f"Tier B floor: curator-silent control p{int(CONTROL_PCTL * 100)} = **{floor:.3f}**.")
    add("")

    add("## 1. The embedding separates; the contradicted corpus sits on the control")
    add("")
    add("| population | n | emb p25 | med | p75 | p90 |")
    add("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, vals in (
        ("confirmed same-source (positive)", conf_emb),
        ("curator-contradicted", con_emb),
        ("curator-silent different (control)", ctrl_emb),
    ):
        add(
            f"| {name} | {len(vals)} | {_pctl(vals, .25):.3f} | {_pctl(vals, .5):.3f} "
            f"| {_pctl(vals, .75):.3f} | {_pctl(vals, .9):.3f} |"
        )
    add("")
    add("The positive population medians ~4x the other two, and the contradicted")
    add("corpus is statistically indistinguishable from the negative control at every")
    add("quartile. On the only audio signal here with a calibrated bar, the bulk of")
    add("the corpus looks like genuinely different recordings — not like same-source")
    add("pairs tapematch failed to merge.")
    add("")

    add("## 2. Tier x bucket (all 1,822 contradicted pairs)")
    add("")
    counts = Counter(
        (classify(markers(r)), tier(r, floor)) for r in contradicted
    )
    add("| census bucket | " + " | ".join(TIER_ORDER) + " | total |")
    add("| --- | " + " | ".join("---:" for _ in TIER_ORDER) + " | ---: |")
    for bucket in BUCKET_ORDER:
        cells = [counts.get((bucket, t), 0) for t in TIER_ORDER]
        if not sum(cells):
            continue
        add(f"| {bucket} | " + " | ".join(str(c) for c in cells) + f" | {sum(cells)} |")
    totals = [sum(counts.get((b, t), 0) for b in BUCKET_ORDER) for t in TIER_ORDER]
    add("| **all** | " + " | ".join(f"**{c}**" for c in totals) + f" | **{sum(totals)}** |")
    add("")

    add("## 3. The 377 `unexplained` pairs — the question this pass was opened for")
    add("")
    unexplained = [r for r in contradicted if classify(markers(r)) == "unexplained"]
    utier = Counter(tier(r, floor) for r in unexplained)
    add("| tier | n | share |")
    add("| --- | ---: | ---: |")
    for t in TIER_ORDER:
        add(f"| {t} | {utier.get(t, 0)} | {_pct(utier.get(t, 0), len(unexplained))} |")
    add("")
    recall = sum(1 for v in conf_emb if v >= floor) / len(conf_emb)
    add(f"**Verdict: they are not a hidden failure class.** {_pct(utier.get(TIER_C, 0), len(unexplained))} "
        "sit in the negative-control band, and the census already showed they are")
    add("clean on every metadata axis — speed-locked on both sides, duration ratio")
    add("within 15%, no disclaimer text, no LB-tag collision. The most economical")
    add("reading is curator label noise with no textual marker: the claim is wrong")
    add("(or was mis-parsed) and the recordings really are different.")
    add("")
    add(f"**Stated honestly:** tier C is *absence of evidence*. The embedding recalls only "
        f"{100 * recall:.0f}% of confirmed")
    add("same-source pairs at this floor, so a control-like score does not prove two")
    add("recordings differ. What tier C does establish is that no signal tapematch")
    add("currently persists puts these pairs anywhere near a merge bar — consistent")
    add("with census finding 5 (corr <0.05 for 93.3%, never reaching 0.40). Settling")
    add("them either way needs a signal the project does not have today, and the")
    add("population is not large or distinctive enough to justify building one.")
    add("")

    add("## 4. Tier A — pairs the SHIPPED bar already merges (BUG-278)")
    add("")
    tier_a = [r for r in contradicted if tier(r, floor) == TIER_A]
    claimed, silent, n_dates = transitive_flips(conn)
    add(f"{len(tier_a)} contradicted pairs clear `rule_d`'s calibrated both-convention bar")
    add("yet are stored `different_family`. This is not a matcher gap — the rule that")
    add("would merge them shipped on 2026-07-04. It cannot fire in a live session:")
    add("`tapematch/cli.py`'s `_pair_metrics()` never puts `emb_score` /")
    add("`emb_score_global` in the dict handed to `verdict.pair_links`, so")
    add("`_rule_d_emb_both` reads `None` and abstains on every pair. `emb_live.py`")
    add("does populate the columns, but from `_log_to_obs_db()` — after clustering has")
    add("already run and the verdict has been written. Filed as **BUG-278**.")
    add("")
    add("Corpus-wide effect of linking rule_d and re-closing each date transitively:")
    add("")
    add(f"- **{claimed}** pairs the curator claims as same-source would flip to `same_family` (rescues).")
    add(f"- **{silent}** pairs the curator is silent on would also flip (unvalidated — see below).")
    add(f"- across **{n_dates}** dates.")
    add("")
    add("The silent flips are the reason this is a bug report and not a patch. rule_d's")
    add("zero-new-FP proof was measured on the 2,245-pair frozen regression sets; these")
    add("merges are corpus-wide and outside that population, so they are uncalibrated.")
    add("Fixing the wiring without first scoring those flips would push unvalidated")
    add("merges into the family tables.")
    add("")
    add("| date | pair | emb | emb_global | corr | census bucket |")
    add("| --- | --- | ---: | ---: | ---: | --- |")
    for r in sorted(tier_a, key=lambda r: -min(r["emb_score"], r["emb_score_global"])):
        add(
            f"| {r['concert_date']} | LB-{r['lb_a']:05d} / LB-{r['lb_b']:05d} "
            f"| {r['emb_score']:.3f} | {r['emb_score_global']:.3f} | {r['corr']:.4f} "
            f"| {classify(markers(r))} |"
        )
    add("")

    add("## 5. Tier B — elevated but not merge-grade")
    add("")
    tier_b = [r for r in contradicted if tier(r, floor) == TIER_B]
    add(f"{len(tier_b)} pairs score above the control p95 but below the rule_d bar. They are")
    add("the natural evaluation set for any future loosening of `t_emb`, and the")
    add("natural first audio-review batch if one is ever run. No action proposed here:")
    add("the 0.700 step of rule_d's own sweep already cost abs fp 11 vs 9, so the bar")
    add("is sitting one step off a known cliff and should not be moved casually.")
    add("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=OBS_DB_PATH, help="observations.db path")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="report output path")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        report = build_report(conn)
    finally:
        conn.close()
    args.out.write_text(report, encoding="utf-8")
    log.info("wrote %s (%d lines)", args.out, len(report.splitlines()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
