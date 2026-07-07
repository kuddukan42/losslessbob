"""One-off audit dump: every frozen calibration pair, its truth label, and the
current shipped verdict, for manual sanity-checking. Reuses regression.py's
exact scoring internals so the TP/FN/FP/TN split matches the reported
41.6%/98.6% numbers exactly (not a reimplementation).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import regression as R
import yaml

frozen = R._load_frozen()
truth_map = R._truth_map(frozen)
cfg = yaml.safe_load(Path(R.CONFIG_PATH).read_text())
baseline_cfg = cfg
lineage = R.V.load_lineage_pairs(R.LB_DB_PATH) if R.LB_DB_PATH.exists() else set()

dates = sorted(R._dates_of(frozen))
conn = R._connect(R.OBS_DB_PATH)
cols = R._pair_columns(conn)

cand_pred = {}
for date in dates:
    cp, _ = R._candidate_verdicts_for_date(conn, cols, date, cfg, lineage, baseline_cfg)
    cand_pred.update(cp)

# Pull per-pair context columns for the audit (one row per (date, lb_a, lb_b)).
extra = {}
q = ("SELECT concert_date, lb_a, lb_b, corr, fp_score, hiss_median, "
     "lb_says_same, lb_relation_text, human_judgment, human_notes, "
     "label_suspect, folder_a, folder_b FROM latest_pairs")
for row in conn.execute(q):
    (date, a, b, corr, fp_score, hiss_median, ss, rel_text, hj, hn,
     suspect, fa, fb) = row
    if a is None or b is None:
        continue
    key = (date, min(a, b), max(a, b))
    extra[key] = dict(corr=corr, fp_score=fp_score, hiss_median=hiss_median,
                       lb_says_same=ss, lb_relation_text=rel_text,
                       human_judgment=hj, human_notes=hn,
                       label_suspect=suspect, folder_a=fa, folder_b=fb)
conn.close()

pairs_by_key = {}
for a, b, date in frozen["positives"]:
    pairs_by_key.setdefault((min(a, b), max(a, b)), []).append((date, 1))
for a, b, date in frozen["negatives"]:
    pairs_by_key.setdefault((min(a, b), max(a, b)), []).append((date, 0))

rows_out = []
for (a, b), entries in pairs_by_key.items():
    for date, truth in entries:
        pred = cand_pred.get((a, b))
        if truth == 1 and pred:
            category = "TP"
        elif truth == 1 and not pred:
            category = "FN"
        elif truth == 0 and pred:
            category = "FP"
        else:
            category = "TN"
        ctx = extra.get((date, a, b), {})
        rows_out.append({
            "date": date,
            "lb_a": a,
            "lb_b": b,
            "truth": "same" if truth == 1 else "different",
            "verdict_category": category,
            "scored": pred is not None,
            "corr": ctx.get("corr"),
            "fp_score": ctx.get("fp_score"),
            "hiss_median": ctx.get("hiss_median"),
            "lb_says_same": ctx.get("lb_says_same"),
            "lb_relation_text": ctx.get("lb_relation_text"),
            "human_judgment": ctx.get("human_judgment"),
            "human_notes": ctx.get("human_notes"),
            "label_suspect": ctx.get("label_suspect"),
            "folder_a": ctx.get("folder_a"),
            "folder_b": ctx.get("folder_b"),
        })

rows_out.sort(key=lambda r: (r["date"], r["lb_a"], r["lb_b"]))

out_path = Path(__file__).resolve().parent / "calibration_audit.json"
out_path.write_text(json.dumps(rows_out, indent=1))

from collections import Counter
cat_counts = Counter(r["verdict_category"] for r in rows_out)
suspect_count = sum(1 for r in rows_out if r["label_suspect"])
unscored = sum(1 for r in rows_out if not r["scored"])
print(f"total rows: {len(rows_out)}")
print(f"category counts: {dict(cat_counts)}")
print(f"label_suspect=1: {suspect_count}")
print(f"unscored (no cand_pred, not on a run date): {unscored}")
print(f"unique LB numbers involved: {len(set(r['lb_a'] for r in rows_out) | set(r['lb_b'] for r in rows_out))}")
print(f"wrote {out_path}")
