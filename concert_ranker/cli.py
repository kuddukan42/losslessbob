"""concert_ranker command-line surface.

    concert_ranker scan      --all | --lb N... | --family N
    concert_ranker calibrate --sample-size 30
    concert_ranker rerank    --scan-id N
    concert_ranker report    --family N | --lb N   [--format json|csv|text]

``rerank`` works entirely from stored ``metric_json`` — it never reads audio,
proving the scan-once guarantee. Run from the repo root:

    .venv/bin/python3 -m concert_ranker.cli rerank --scan-id 1
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys

from concert_ranker.config import default_config
from concert_ranker.lb import repo, source_type


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Worklist construction
# ─────────────────────────────────────────────────────────────────────────────
def _collection_worklist(conn, lb_filter=None) -> list[tuple]:
    """Build ``(lb, disk_path, source_class)`` from my_collection."""
    sql = ("SELECT c.lb_number AS lb, c.disk_path AS disk_path,"
           "       e.description AS description, e.source_chain AS source_chain,"
           "       e.source_type AS source_type "
           "FROM my_collection c LEFT JOIN entries e ON c.lb_number = e.lb_number")
    params: list = []
    if lb_filter:
        sql += " WHERE c.lb_number IN ({})".format(",".join("?" * len(lb_filter)))
        params.extend(lb_filter)
    out = []
    for r in conn.execute(sql, params):
        cls = source_type.derive_source_class(
            r["description"], r["source_chain"], r["source_type"])
        out.append((int(r["lb"]), r["disk_path"], cls))
    return out


def _family_lbs(conn, fam_int_or_id) -> list[int]:
    """LB numbers belonging to a family (accepts the text fam_id)."""
    rows = conn.execute(
        "SELECT lb_number FROM recording_families WHERE fam_id = ?",
        (str(fam_int_or_id),),
    ).fetchall()
    return [int(r["lb_number"]) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Subcommands
# ─────────────────────────────────────────────────────────────────────────────
def cmd_scan(args) -> int:
    from concert_ranker.runner import scan_folders

    conn = repo.connect(args.db)
    repo.ensure_schema(conn)

    lb_filter = None
    if args.lb:
        lb_filter = args.lb
    elif args.family:
        lb_filter = _family_lbs(conn, args.family)
        if not lb_filter:
            print(f"no recordings in family {args.family}", file=sys.stderr)
            return 1
    elif not args.all:
        print("specify --all, --lb N..., or --family ID", file=sys.stderr)
        return 2

    worklist = _collection_worklist(conn, lb_filter)
    if not worklist:
        print("no matching recordings in my_collection", file=sys.stderr)
        return 1

    scan_id = args.scan_id or repo.create_scan(
        conn, config=vars(default_config()), notes=args.notes)
    print(f"scan_id={scan_id}: scanning {len(worklist)} recording(s)"
          f"{' via staging' if args.staging_dir else ''}…")
    if args.staging_dir:
        from concert_ranker.runner import group_by_device, run_staged
        run_staged(group_by_device(worklist), args.staging_dir, scan_id,
                   db_path=args.db, n_consumers=args.workers)
        done = repo.done_lbs(conn, scan_id)
        print(f"scanned {len(done & {w[0] for w in worklist})}/{len(worklist)} ok")
    else:
        results = scan_folders(worklist, scan_id, db_path=args.db, workers=args.workers)
        ok = sum(1 for r in results if r["status"] == "done")
        print(f"scanned {ok}/{len(results)} ok")

    # Rank straight after scanning so scores are immediately available.
    _rerank(conn, scan_id)
    print(f"ranked scan {scan_id}. Use: concert_ranker report --scan-id {scan_id}")
    return 0


def _rerank(conn, scan_id: int) -> int:
    """Re-band/rank from stored metrics only (no audio). Returns row count."""
    from concert_ranker import families

    metrics = repo.load_metrics(conn, scan_id)
    if not metrics:
        return 0
    family_map = families.load_family_map(conn, list(metrics.keys()))
    decades = families.load_decade_map(conn, list(metrics.keys()))
    rows = families.rank_scan(metrics, family_map, decades)
    repo.clear_scores(conn, scan_id)
    repo.write_scores(conn, scan_id, rows)
    return len(rows)


def cmd_rerank(args) -> int:
    conn = repo.connect(args.db)
    repo.ensure_schema(conn)
    scan_id = args.scan_id or repo.latest_scan_id(conn)
    if scan_id is None:
        print("no scans exist", file=sys.stderr)
        return 1
    n = _rerank(conn, scan_id)
    print(f"reranked scan {scan_id}: wrote {n} score row(s) from stored metrics")
    return 0


def cmd_calibrate(args) -> int:
    from concert_ranker.calibration import run_calibration

    conn = repo.connect(args.db)
    repo.ensure_schema(conn)
    per_cell = args.per_cell or max(1, args.sample_size // 8)
    classes = tuple(args.classes) if args.classes else None
    report = run_calibration(conn, db_path=args.db, per_cell=per_cell,
                             workers=args.workers, classes=classes,
                             staging_dir=args.staging_dir, by_decade=args.by_decade)
    print(json.dumps(report, indent=2, default=str))
    return 0 if "error" not in report else 1


def cmd_report(args) -> int:
    conn = repo.connect(args.db)
    repo.ensure_schema(conn)
    scan_id = args.scan_id or repo.latest_scan_id(conn)
    if scan_id is None:
        print("no scans exist", file=sys.stderr)
        return 1

    scores = repo.load_scores(conn, scan_id)
    if args.lb:
        scores = [s for s in scores if s["lb_number"] in args.lb]
    elif args.family is not None:
        scores = [s for s in scores if s["family_id"] == args.family]

    if args.format == "json":
        print(json.dumps(scores, indent=2, default=str))
    elif args.format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=[
            "lb_number", "family_id", "final_score", "rank_in_family",
            "vetoed", "verdict_text"])
        w.writeheader()
        w.writerows(scores)
        print(buf.getvalue(), end="")
    else:
        for s in scores:
            print(f"• {s['verdict_text']}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="concert_ranker", description=__doc__)
    p.add_argument("--db", default=None, help="path to losslessbob.db (default: app DB)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scan", help="scan recordings → raw metrics + ranking")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="scan the whole collection")
    g.add_argument("--lb", type=int, nargs="+", help="scan specific LB numbers")
    g.add_argument("--family", help="scan one family (fam_id)")
    sp.add_argument("--scan-id", type=int, default=None,
                    help="append to an existing scan instead of creating one")
    sp.add_argument("--workers", type=int, default=16)
    sp.add_argument("--staging-dir", default=None,
                    help="copy folders here (fast scratch) before decoding "
                         "(one producer per drive); recommended for the full corpus")
    sp.add_argument("--notes", default=None)
    sp.set_defaults(func=cmd_scan)

    cp = sub.add_parser("calibrate", help="fit thresholds against rated samples")
    cp.add_argument("--sample-size", type=int, default=30,
                    help="approx total recordings (per-cell derived as size//8)")
    cp.add_argument("--per-cell", type=int, default=None,
                    help="explicit max recordings per (rating, source_class) cell")
    cp.add_argument("--classes", nargs="+", default=None,
                    choices=("AUD", "SBD", "FM", "UNKNOWN"),
                    help="restrict sample to these source classes")
    cp.add_argument("--by-decade", action="store_true",
                    help="large decade × tier × class sample (all decades, all "
                         "bad-tier); --per-cell caps the good/mid cells")
    cp.add_argument("--staging-dir", default=None,
                    help="copy folders here (fast scratch) before decoding")
    cp.add_argument("--workers", type=int, default=8)
    cp.set_defaults(func=cmd_calibrate)

    rp = sub.add_parser("rerank", help="re-band/rank from stored metrics (no rescan)")
    rp.add_argument("--scan-id", type=int, default=None)
    rp.set_defaults(func=cmd_rerank)

    rep = sub.add_parser("report", help="print scores/verdicts")
    rep.add_argument("--scan-id", type=int, default=None)
    rep.add_argument("--lb", type=int, nargs="+")
    rep.add_argument("--family", type=int, default=None)
    rep.add_argument("--format", choices=("text", "json", "csv"), default="text")
    rep.set_defaults(func=cmd_report)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
