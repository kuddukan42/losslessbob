#!/usr/bin/env python3
"""emb_score_pairs.py — Task 6.1 per-pair nmfp emb_score for an arbitrary pairs file.

Generalizes ``embed_eval.py``'s pair-scoring step beyond ``embed_eval_set.json``:
given any pairs JSON in the ``build_fullset_worklist.py`` shape (a flat list under
``"pairs"`` of ``{date, lb_a, lb_b, tag, corr}``) plus an ``embed_cache/`` populated
by ``nmfp_embed.py``, it computes both pair-score conventions from spec 6.1.3 for
every pair — reusing ``embed_eval.py``'s exact scoring functions (``_load_source``,
``_pair_score``) rather than reimplementing them. ``embed_eval.py`` needed no
refactor: those are already plain module-level functions, importable as-is; its
own CLI behaviour is untouched.

    emb_tol2  = ``_pair_score(a, b, tol=2.0)``   — nominal-perf-time ±2s aligned
    emb_tol0  = ``_pair_score(a, b, tol=0.0)``   — global cosine-max (no alignment)

A pair scores null on a tol if either source has no cached npz, or (tol2 only)
no B-window falls in tolerance of any A-window.

Output: ``<input-stem>_scores.json`` next to this script — a list of
``{date, lb_a, lb_b, tag, corr, emb_tol2, emb_tol0}``.

Read-only; never runs audio or a model.

    .venv/bin/python3 tools/tapematch/emb_score_pairs.py fullset_pairs.json
    .venv/bin/python3 tools/tapematch/emb_score_pairs.py pilot_pairs.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import embed_eval as EE  # noqa: E402  (reuse _load_source/_pair_score/_pct, not reimplement)

CACHE_DIR = _HERE / "embed_cache"
TOL_ALIGNED = 2.0
TOL_GLOBAL = 0.0


def score_pair(
    date: str, lb_a: int, lb_b: int, cache: Path,
    src_cache: dict[tuple[str, int], tuple | None]
) -> tuple[float | None, float | None]:
    """Score one pair with both nmfp emb conventions (spec 6.1.3).

    The single importable entry point for the per-pair scoring used by both this
    CLI and the live-session hook (``emb_live.py``): it applies the exact
    ``embed_eval._load_source`` / ``embed_eval._pair_score`` conventions so live
    and offline scores are identical for the same cached embeddings.

    Args:
        date: Concert date ``YYYY-MM-DD`` (the ``embed_cache`` sub-directory).
        lb_a: First LB number of the pair.
        lb_b: Second LB number of the pair. Scoring is order-sensitive
            (``emb_tol0`` is the median over A-windows), so callers must pass the
            same order the offline worklist used — normalized ``min, max``.
        cache: ``embed_cache`` directory holding ``<date>/LB<lb>.npz`` per source.
        src_cache: Mutable per-run memo of loaded sources, keyed ``(date, lb)``;
            values are the loaded ``(emb, t)`` tuple or ``None`` when uncached.

    Returns:
        ``(emb_tol2, emb_tol0)``. Either or both are ``None`` when a source has no
        cached npz, or (``emb_tol2`` only) no B-window falls within tolerance.
    """
    for key in ((date, lb_a), (date, lb_b)):
        if key not in src_cache:
            src_cache[key] = EE._load_source(key[0], key[1], cache)
    a = src_cache[(date, lb_a)]
    b = src_cache[(date, lb_b)]
    if a is None or b is None:
        return None, None
    tol2 = EE._pair_score(a, b, TOL_ALIGNED)
    tol0 = EE._pair_score(a, b, TOL_GLOBAL)
    return tol2, tol0


def _summarize(scores: list[dict]) -> None:
    """Per-tag min/median/p90/max report for both tol conventions."""
    tags = sorted({s["tag"] for s in scores})
    fields = (("emb_tol2", "emb_tol2 (±2s aligned)"), ("emb_tol0", "emb_tol0 (global)"))
    for field, label in fields:
        print(f"\n{label}:")
        for tag in tags:
            vals = [s[field] for s in scores if s["tag"] == tag and s[field] is not None]
            n_missing = sum(1 for s in scores if s["tag"] == tag) - len(vals)
            if not vals:
                print(f"  {tag:<12} n=0  missing={n_missing}")
                continue
            print(f"  {tag:<12} n={len(vals):<5} missing={n_missing:<5} "
                 f"min={min(vals):.3f} median={EE._pct(vals, 50):.3f} "
                 f"p90={EE._pct(vals, 90):.3f} max={max(vals):.3f}")


def main() -> int:
    """Score every pair in a build_fullset_worklist.py pairs JSON. See module docstring."""
    ap = argparse.ArgumentParser(description="Task 6.1 emb_score for an arbitrary pairs file.")
    ap.add_argument("pairs", type=Path, help="pairs JSON (fullset_pairs.json / pilot_pairs.json).")
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    ap.add_argument("--out", type=Path, default=None,
                    help="output path (default: <pairs-stem>_scores.json next to this script).")
    args = ap.parse_args()

    if not args.pairs.exists():
        sys.exit(f"error: {args.pairs} not found — run build_fullset_worklist.py first.")
    data = json.loads(args.pairs.read_text())
    pairs = data["pairs"]

    src_cache: dict[tuple[str, int], tuple | None] = {}
    scores: list[dict] = []
    n_missing = 0
    for p in pairs:
        tol2, tol0 = score_pair(p["date"], p["lb_a"], p["lb_b"], args.cache, src_cache)
        if tol2 is None and tol0 is None:
            n_missing += 1
        scores.append({
            "date": p["date"], "lb_a": p["lb_a"], "lb_b": p["lb_b"],
            "tag": p["tag"], "corr": p.get("corr"),
            "emb_tol2": tol2, "emb_tol0": tol0,
        })

    out = args.out or (_HERE / f"{args.pairs.stem}_scores.json")
    out.write_text(json.dumps(scores, indent=2))

    n_cached = sum(1 for v in src_cache.values() if v is not None)
    print(f"emb_score_pairs: {len(scores)} pairs scored -> {out.name}")
    print(f"  sources referenced: {len(src_cache)}   cached: {n_cached}   "
         f"pairs fully unscorable (both tols null): {n_missing}")
    _summarize(scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
