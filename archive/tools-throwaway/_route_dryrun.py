"""Read-only dry-run: canonical name + filing destination for every unrouted
my_collection folder. Writes .debug/unrouted_plan.csv. Moves nothing."""
import collections, csv, os, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import db as database, filer  # noqa: E402
from backend.folder_naming import build_standard_name  # noqa: E402

c = sqlite3.connect("data/losslessbob.db")
c.row_factory = sqlite3.Row
roots = tuple(r["root_path"].rstrip("/") + "/" for r in c.execute("select root_path from collection_mounts"))

rows = [r for r in c.execute("select lb_number, folder_name, disk_path, xref from my_collection")
        if r["disk_path"] and not r["disk_path"].replace("\\", "/").startswith(roots)]

buckets = collections.Counter()
out = []
for r in rows:
    lb, xref = r["lb_number"], r["xref"] or 0
    src = r["disk_path"].replace("\\", "/").rstrip("/")
    ent = database.get_entry(lb) or {}
    e = ent.get("entry") or {}
    status = (e.get("status") or None)
    canon = build_standard_name(lb, e.get("date_str") or "", e.get("location") or "", status, xref)
    res = filer.resolve_destination_for_lb(lb, str(Path(src).parent / canon))
    code = res.get("error_code") or "ok"
    nested = sum(1 for _ in Path(src).parents if False)  # placeholder
    depth = len(Path(src).relative_to("/mnt").parts)
    buckets[code] += 1
    buckets["status:" + str(status)] += 1
    out.append({
        "lb": f"LB-{lb:05d}", "xref": xref, "status": status or "",
        "src": src, "src_depth": depth,
        "canonical_name": canon, "dest": res.get("dest") or "",
        "verdict": code, "detail": res.get("error") or "",
        "rename_needed": int(Path(src).name != canon),
    })

Path(".debug").mkdir(exist_ok=True)
with open(".debug/unrouted_plan.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0]))
    w.writeheader(); w.writerows(out)

print("unrouted folders:", len(out))
for k, v in buckets.most_common():
    print(f"  {k:22s} {v}")
print("renames needed:", sum(o['rename_needed'] for o in out))
tree = collections.Counter("/".join(o["src"].split("/")[:4]) + "  ->  " + o["verdict"] for o in out)
print("\nby tree x verdict:")
for k, v in tree.most_common(20):
    print(f"  {v:6d}  {k}")
