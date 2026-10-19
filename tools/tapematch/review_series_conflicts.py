#!/usr/bin/env python3
"""TODO-234 -- per-case evidence for series-vs-series taper conflicts.

A ``taper_attributions`` row with ``conflict=1`` whose contesting candidates are
all formal series codes (``lt[a-z]`` / ``net taper [a-z]``) means a taper
propagation *component* holds two real tapers. The component is the union of
strong ``recording_families`` families plus curator ``same_as`` / ``derived_from``
lineage edges (see ``backend.taper_attribution``), so the cause is either a
TapeMatch over-merge (anchors share a family) or a lineage edge (anchors sit in
different families). The conflict rows themselves are the *unattributed* members
of the component; their evidence names the confirmed anchors (``via_lb``).

For each case this pulls the anchors, the conflict members, every stored pairwise
row among them from ``observations.db`` (``latest_pairs``) with the link
mechanism from ``verdict.link_mechanism``, the lineage edges, and emits a
split/keep recommendation.

Read-only: both DBs are opened ``mode=ro``; decodes no audio; splits nothing.

Usage:
    .venv/bin/python3 tools/tapematch/review_series_conflicts.py \
        [--app-db PATH] [--obs-db PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

SESSION_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SESSION_DIR))
REPO = SESSION_DIR.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tapematch import verdict as V  # noqa: E402
from backend.taper_attribution import _is_series_vs_series  # noqa: E402

log = logging.getLogger("series_conflict_review")

DEFAULT_APP_DB = REPO / "data" / "losslessbob.db"
DEFAULT_OBS_DB = SESSION_DIR / "observations.db"
DEFAULT_OUT = SESSION_DIR / "SERIES_CONFLICT_REVIEW.md"
CONFIG_PATH = SESSION_DIR / "config.yaml"

# Hand-reviewed calls (2026-10-19), keyed by concert date. The auto call only reads
# link mechanisms; these also weigh lb_says_same, emb_score and family conf.
HAND: dict[str, tuple[str, str]] = {
    "1988-07-17": ("NOT-MERGE", "TapeMatch already has 1297 (ltg) and the 10935 family "
                   "(ltc) as different_family (corr <= 0.012). The conflict is carried by "
                   "curator same_as edges (1297 -> 7126/7541/14671) that waveform "
                   "contradicts. Nothing to split; review the 1297 same_as edges."),
    "1990-10-11": ("NOT-MERGE", "Anchor 5859 (lte) has no observation rows and no family; "
                   "166 is tied to both anchors only by same_as lineage. Taper-curation "
                   "question (lte vs lta), not a family split."),
    "1993-02-07": ("KEEP (relabel)", "Core 5882/12768/16364 (lta) is primary 0.90-0.98. "
                   "1343 (ltb) joins at corr 0.29-0.32 on hiss/fingerprint, but emb "
                   "0.93-0.95 and LB says same (1343-5882). Corr is depressed by 1343's "
                   "staircase/splice speed. Likely one tape with a wrong series credit."),
    "1995-03-14": ("NOT-MERGE", "ltj anchor 10658 has no family; link is lineage only "
                   "(10385-10658, 8517-10387 same_as). Core 1922/2972/3483 is primary "
                   ">= 0.89; 8517 (ltb) attaches weakly (fingerprint 0.33, emb 0.44-0.53) "
                   "- optional split of 8517 only. 1029 same_as 3483 is contradicted by "
                   "waveform (0.002) and LB (says different) - bad lineage edge."),
    "1995-03-16": ("KEEP (relabel, low conf)", "Family conf 0.22. 1618/3491 primary 0.89; "
                   "556 and 5768 attach on fingerprint/windowed/rule_d at corr 0.02-0.17, "
                   "but emb 0.74-0.93 and LB says same for 556-5768 and 1618-5768. "
                   "Listen to 5768 (net taper i) before splitting."),
    "1995-10-02": ("KEEP (relabel)", "Already review_flag=1, conf 0.14. 5915-6390 hiss "
                   "0.21, emb 0.79, LB says same; 3842 rides rule_d at 0.03 with emb 0.93. "
                   "Weak waveform but consistent embeddings and curator commentary."),
    "1995-12-09": ("SPLIT", "6083 (net taper j) vs 6104/15211 (lta): corr 0.005, no leg, "
                   "emb 0.29-0.30, and LB says DIFFERENT for 6083-6104. 6104-15211 is a "
                   "genuine pair (windowed 0.42, emb 0.91, LB same). Split 6083 out."),
    "1997-04-05": ("SPLIT (curator disagrees)", "Two tight clusters {3344,3559} (primary "
                   "0.988) and {8854,9240} (primary 0.972) bridged only by fingerprint at "
                   "corr 0.02-0.24, emb 0.46-0.57. Different series credits. Curator "
                   "same_as edges tie 9240 to all - listen before splitting."),
    "1998-06-03": ("NOT-MERGE", "Anchor 13992 (net taper f) has no family or observation "
                   "rows; the contest is a 3325 same_as 13992 lineage edge. No tapematch "
                   "lever."),
    "1998-06-12": ("SPLIT", "6465 (net taper f) has no leg to 5800/6462 (net taper i): "
                   "corr 0.03-0.04, emb 0.34-0.70. It is in the family only by chain via "
                   "4436 (windowed 0.02-0.13). Family conf 0.20, already flagged. Split "
                   "6465 out; 4436 is itself weak."),
    "2000-05-25": ("KEEP (relabel)", "14518 (ltb) same_as 14519 (net taper f): one tape "
                   "carrying two series credits. No observation rows; fix the "
                   "attribution, no split."),
}

_CAND_RE = re.compile(r"candidate taper '([^']+)'")


def _ro(path: Path) -> sqlite3.Connection:
    """Open *path* read-only with Row factory."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class _DSU:
    """Tiny union-find over ints."""

    def __init__(self) -> None:
        self.p: dict[int, int] = {}

    def find(self, x: int) -> int:
        """Root of *x*."""
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        """Join the sets of *a* and *b*."""
        self.p[self.find(a)] = self.find(b)


def load_lineage(app: sqlite3.Connection) -> dict[tuple[int, int], str]:
    """Unordered LB pairs joined by curator same_as / derived_from edges."""
    out: dict[tuple[int, int], str] = {}
    for col, tag in (("same_as_lb", "same_as"), ("derived_from_lb", "derived_from")):
        for r in app.execute(
                f"SELECT lb_number, {col} FROM entry_lineage "
                f"WHERE {col} IS NOT NULL AND {col} != '[]'"):
            try:
                others = json.loads(r[1])
            except (ValueError, TypeError):
                continue
            for o in others:
                if isinstance(o, int) and o != r[0]:
                    out.setdefault((min(r[0], o), max(r[0], o)), tag)
    return out


def load_cases(app: sqlite3.Connection) -> list[dict[str, Any]]:
    """Group series-vs-series conflict rows into propagation cases.

    Returns:
        List of ``{conflict_lbs, anchors: {lb: taper}}`` dicts, one per case.
    """
    dsu = _DSU()
    anchors: dict[int, str] = {}
    conflict_lbs: set[int] = set()
    for r in app.execute("SELECT lb_number, taper_normalised, evidence_json "
                         "FROM taper_attributions WHERE conflict = 1"):
        ev = json.loads(r["evidence_json"])
        if not _is_series_vs_series(r["taper_normalised"], ev):
            continue
        conflict_lbs.add(r["lb_number"])
        dsu.find(r["lb_number"])
        for e in ev:
            m = _CAND_RE.search(e.get("detail", ""))
            if e.get("kind") == "conflict" and m and e.get("via_lb"):
                anchors[e["via_lb"]] = m.group(1)
                dsu.union(r["lb_number"], e["via_lb"])
    groups: dict[int, dict[str, Any]] = {}
    for lb in conflict_lbs | set(anchors):
        g = groups.setdefault(dsu.find(lb), {"conflict_lbs": set(), "anchors": {}})
        if lb in conflict_lbs:
            g["conflict_lbs"].add(lb)
        if lb in anchors:
            g["anchors"][lb] = anchors[lb]
    return list(groups.values())


def fam_of(app: sqlite3.Connection, lb: int) -> tuple[str | None, str | None]:
    """(fam_id, concert_date) of *lb*, or (None, None)."""
    r = app.execute("SELECT fam_id, concert_date FROM recording_families "
                    "WHERE lb_number=?", (lb,)).fetchone()
    return (r[0], r[1]) if r else (None, None)


def fam_meta(app: sqlite3.Connection, fam: str | None) -> dict[str, Any]:
    """Family meta row as a dict (empty if none)."""
    if not fam:
        return {}
    r = app.execute("SELECT label, conf, review_flag, member_count "
                    "FROM tapematch_family_meta WHERE fam_id=?", (fam,)).fetchone()
    return dict(r) if r else {}


def source_facts(obs: sqlite3.Connection, lb: int, date: str | None) -> dict[str, Any]:
    """Latest source facts for *lb* (any date if *date* is None)."""
    q = ("SELECT concert_date, dominant_ext, perf_dur_sec, speed_kind FROM sources "
         "WHERE lb_number=?" + (" AND concert_date=?" if date else "") +
         " ORDER BY id DESC LIMIT 1")
    r = obs.execute(q, (lb, date) if date else (lb,)).fetchone()
    return dict(r) if r else {}


def pairs_among(obs: sqlite3.Connection, lbs: list[int], cfg: dict,
                lineage: set) -> list[dict[str, Any]]:
    """Latest pair rows with both sides in *lbs*, with link mechanism."""
    ph = ",".join("?" * len(lbs))
    rows = obs.execute(
        f"SELECT * FROM latest_pairs WHERE lb_a IN ({ph}) AND lb_b IN ({ph}) "
        "ORDER BY concert_date, lb_a, lb_b", (*lbs, *lbs)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["mech"] = V.link_mechanism(d, cfg, lineage)
        out.append(d)
    return out


def recommend(case: dict[str, Any]) -> tuple[str, str]:
    """Split/keep call for one case.

    Looks at every differently-credited anchor pair:
      * curator lineage edge between them          -> KEEP (curator says same tape)
      * stored pair, primary corr bridge           -> KEEP (one series credit wrong)
      * stored pair, weak legs only                -> SPLIT
      * stored pair, tapematch said different      -> NOT-A-MERGE (lineage/chain only)
      * no stored pair                             -> see anchor family relation
    """
    anchors = case["anchors"]
    cross = [(a, b) for a in sorted(anchors) for b in sorted(anchors)
             if a < b and anchors[a] != anchors[b]]
    if not cross:
        return ("REVIEW", "anchors agree on series; conflict is a stale/mixed row")
    pmap = {(p["lb_a"], p["lb_b"]): p for p in case["pairs"]}
    notes, calls = [], []
    for a, b in cross:
        key = (a, b) if (a, b) in pmap else (b, a)
        p = pmap.get(key)
        lin = case["lineage"].get((a, b))
        same_fam = case["fam"].get(a) is not None and case["fam"].get(a) == case["fam"].get(b)
        if lin:
            calls.append("KEEP")
            notes.append(f"{a}/{b}: curator lineage {lin}")
        elif p and p["mech"] == "primary":
            calls.append("KEEP")
            notes.append(f"{a}/{b}: primary corr {p['corr']:.2f}")
        elif p and p["mech"]:
            calls.append("SPLIT")
            notes.append(f"{a}/{b}: weak leg {p['mech']} (corr {p['corr']:.3f})")
        elif p:
            calls.append("SPLIT" if same_fam else "NOT-MERGE")
            notes.append(f"{a}/{b}: {p['tapematch_verdict']}, no leg "
                         f"(corr {p['corr']:.3f})" if p["corr"] is not None else
                         f"{a}/{b}: {p['tapematch_verdict']}, no leg")
        else:
            calls.append("SPLIT" if same_fam else "NOT-MERGE")
            notes.append(f"{a}/{b}: no stored pair, "
                         + ("same family (chained)" if same_fam else "different families"))
    if all(c == "KEEP" for c in calls):
        call = "KEEP"
    elif all(c == "KEEP" for c in calls) is False and "KEEP" in calls:
        call = "MIXED"
    elif all(c == "NOT-MERGE" for c in calls):
        call = "NOT-MERGE"
    else:
        call = "SPLIT"
    return (call, "; ".join(notes))


def fmt(v: Any, nd: int = 2) -> str:
    """Format an optional float."""
    return "-" if v is None else f"{v:.{nd}f}"


def build_report(cases: list[dict[str, Any]]) -> str:
    """Render the markdown review."""
    tally: dict[str, int] = defaultdict(int)
    for c in cases:
        tally[HAND.get(c["date"], (c["call"],))[0]] += 1
    n_rows = sum(len(c["conflict_lbs"]) for c in cases)
    out = [
        "# Series-vs-series taper conflict review (TODO-234)", "",
        f"**{len(cases)} cases** ({n_rows} `conflict=1` rows in `taper_attributions`, "
        "all candidates formal series codes). Read-only review - nothing was split.", "",
        "A case is a taper-propagation component: the conflict rows are unattributed "
        "members; the **anchors** are the confirmed members that pull in different "
        "series. Sources: app DB `data/losslessbob.db` (`taper_attributions`, "
        "`recording_families`, `tapematch_family_meta`, `entry_lineage`) and "
        "`latest_pairs` in `observations.db`; mechanism = shipped `config.yaml` replayed "
        "through `verdict.link_mechanism`. Regenerate: "
        "`.venv/bin/python3 tools/tapematch/review_series_conflicts.py`.", "",
        "Calls: **KEEP** = differently-credited anchors are the same tape (curator "
        "lineage or primary-corr bridge) so one series credit is wrong - fix the "
        "attribution, not the family. **SPLIT** = anchors share a family but link only "
        "on weak legs / by chain - a TapeMatch over-merge; split via family review. "
        "**NOT-MERGE** = anchors sit in different families; the conflict arises from "
        "lineage edges (same_as/derived_from), not a TapeMatch merge - nothing to split "
        "in tapematch. **MIXED** = some anchor pairs KEEP, some not.", "",
        "## Summary", "", "| Call | Cases |", "|---|---:|"]
    for k in sorted(tally):
        out.append(f"| {k} | {tally[k]} |")
    out += ["", "| Date | Anchors (LB:series) | Conflict rows | Call |", "|---|---|---:|---|"]
    for c in cases:
        anc = ", ".join(f"{lb}:{t}" for lb, t in sorted(c["anchors"].items()))
        out.append(f"| {c['date']} | {anc} | {len(c['conflict_lbs'])} | "
                   f"**{HAND.get(c['date'], (c['call'],))[0]}** |")
    for c in cases:
        hc, ht = HAND.get(c["date"], (c["call"], ""))
        out += ["", f"## {c['date']} - {hc}", "", ht, "",
                f"Auto: {c['call']} - {c['why']}.", "",
                "| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |",
                "|---:|---|---|---|---:|---:|---|---:|---|"]
        for lb in c["lbs"]:
            role = "anchor" if lb in c["anchors"] else (
                "conflict" if lb in c["conflict_lbs"] else "family")
            fm = c["fmeta"].get(c["fam"].get(lb), {})
            s = c["src"].get(lb, {})
            out.append(f"| {lb} | {role} | {c['anchors'].get(lb, '')} | "
                       f"`{c['fam'].get(lb) or '-'}` | {fmt(fm.get('conf'))} | "
                       f"{fm.get('review_flag', '-')} | {s.get('dominant_ext')} | "
                       f"{fmt(s.get('perf_dur_sec'), 0)} | {s.get('speed_kind')} |")
        if c["lineage_edges"]:
            out += ["", "Lineage: " + "; ".join(f"{a}-{b} {t}" for (a, b), t in
                                                c["lineage_edges"].items())]
        out += ["", "| Pair | corr | verdict | mechanism | fp | emb | LB says same |",
                "|---|---:|---|---|---:|---:|---|"]
        for p in c["pairs"]:
            out.append(f"| {p['lb_a']}-{p['lb_b']} | {fmt(p['corr'], 3)} | "
                       f"{p['tapematch_verdict']} | {p['mech'] or '-'} | "
                       f"{fmt(p['fp_score'])} | {fmt(p['emb_score'])} | "
                       f"{p['lb_says_same']} |")
        if not c["pairs"]:
            out.append("| (no stored pair rows among these LBs) | | | | | | |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    ap.add_argument("--obs-db", type=Path, default=DEFAULT_OBS_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    app, obs = _ro(args.app_db), _ro(args.obs_db)
    lin_all = load_lineage(app)
    same_as = {k for k, v in lin_all.items() if v == "same_as"}
    cases = load_cases(app)
    for c in cases:
        lbs = set(c["anchors"]) | c["conflict_lbs"]
        c["fam"], dates = {}, set()
        for lb in lbs:
            f, d = fam_of(app, lb)
            c["fam"][lb] = f
            if d:
                dates.add(d)
        # also list other members of the anchors' families (context)
        for f in {f for f in c["fam"].values() if f}:
            lbs |= {r[0] for r in app.execute(
                "SELECT lb_number FROM recording_families WHERE fam_id=?", (f,))}
        for lb in lbs:
            c["fam"].setdefault(lb, fam_of(app, lb)[0])
        c["lbs"] = sorted(lbs)
        c["date"] = ", ".join(sorted(dates)) or "?"
        c["fmeta"] = {f: fam_meta(app, f) for f in set(c["fam"].values()) if f}
        c["src"] = {lb: source_facts(obs, lb, None) for lb in lbs}
        c["pairs"] = pairs_among(obs, c["lbs"], cfg, same_as)
        c["lineage"] = {k: v for k, v in lin_all.items() if k[0] in lbs and k[1] in lbs}
        c["lineage_edges"] = c["lineage"]
        c["call"], c["why"] = recommend(c)
    cases.sort(key=lambda c: (c["date"], sorted(c["anchors"])))
    args.out.write_text(build_report(cases))
    log.info("%d cases -> %s", len(cases), args.out)
    tally: dict[str, int] = defaultdict(int)
    for c in cases:
        tally[c["call"]] += 1
    for k, v in sorted(tally.items()):
        log.info("  %-10s %d", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
