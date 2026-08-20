"""Read-only audit of my_collection rows: routed vs unrouted, name vs canonical."""
import collections, os, re, sqlite3
from pathlib import Path

c = sqlite3.connect("data/losslessbob.db")
mounts = {r[0]: (r[1], r[2]) for r in c.execute("select id,label,root_path from collection_mounts")}
routes = {r[0]: (r[1], r[2]) for r in c.execute("select year,mount_id,sub_path from collection_routes")}
roots = {lbl: rp for _, (lbl, rp) in mounts.items()}
routed_roots = tuple(sorted(rp.rstrip("/") + "/" for _, rp in mounts.values()))

STD = re.compile(r"^(\d{4})-\d{2}-\d{2} .+ \(LB-\d{5}")
buckets = collections.Counter()
trees = collections.Counter()
missing = 0
samples = collections.defaultdict(list)

rows = c.execute("select lb_number, folder_name, disk_path, xref from my_collection").fetchall()
for lb, fname, dpath, xref in rows:
    if not dpath:
        buckets["no_disk_path"] += 1
        continue
    p = dpath.replace("\\", "/").rstrip("/")
    routed = p.startswith(routed_roots)
    exists = os.path.isdir(p)
    if not exists:
        missing += 1
    key = "routed" if routed else "UNROUTED"
    buckets[key] += 1
    if not routed:
        # tree = first two path components under /mnt
        parts = p.split("/")
        trees["/".join(parts[:4])] += 1
        canon = bool(STD.match(Path(p).name))
        buckets["unrouted_canonical_name" if canon else "unrouted_nonstandard_name"] += 1
        if len(samples["UNROUTED"]) < 10:
            samples["UNROUTED"].append(f"LB-{lb:05d} x{xref} {p}  exists={exists}")

print("rows", len(rows), "| missing on disk", missing)
for k, v in buckets.most_common():
    print(f"{k:28s} {v}")
print("\nunrouted by tree:")
for k, v in trees.most_common(20):
    print(f"{v:7d}  {k}")
print()
for s in samples["UNROUTED"]:
    print("  ", s)
