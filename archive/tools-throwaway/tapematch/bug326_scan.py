#!/usr/bin/env python3
"""(BUG-326 / TODO-323) List concert dates whose source folders held
duplicate tracks before the ingest de-dup fix. Prints one date per line."""
import collections, os, subprocess, sys
from pathlib import Path

ROOTS = ["/mnt/DYLAN1/Concerts", "/mnt/DYLAN2/Concerts"]
EXTS = (".flac", ".wav", ".shn", ".ape", ".m4a", ".mp3", ".aiff", ".aif")

pred = []
for i, e in enumerate(EXTS):
    if i:
        pred.append("-o")
    pred += ["-iname", f"*{e}"]
find = ["find", *ROOTS, "-type", "f", "(", *pred, ")", "-printf", "%h\t%f\n"]
out = subprocess.run(find, capture_output=True, text=True).stdout

concerts = collections.defaultdict(list)
for line in out.splitlines():
    d, f = line.split("\t", 1)
    for r in ROOTS:
        if d.startswith(r + "/"):
            parts = Path(d[len(r) + 1:]).parts
            if len(parts) >= 2:
                concerts[os.path.join(r, parts[0], parts[1])].append((d, f))
            break

affected = set()
for base, files in concerts.items():
    by_stem = collections.defaultdict(set)
    for d, f in files:
        s, e = os.path.splitext(f)
        by_stem[(d, s.lower())].add(e.lower())
    if any(len(v) > 1 for v in by_stem.values()):
        affected.add(base); continue
    subs = collections.defaultdict(list)
    for d, f in files:
        rel = os.path.relpath(d, base)
        subs[rel.split(os.sep)[0] if rel != "." else "."].append((d, f))
    sigs = set()
    for top, mem in subs.items():
        if top == ".":
            continue
        try:
            sig = frozenset((os.path.splitext(f)[0].lower(),
                             os.path.getsize(os.path.join(d, f))) for d, f in mem)
        except OSError:
            continue
        if len(sig) != len(mem):
            continue
        if sig in sigs:
            affected.add(base); break
        sigs.add(sig)

dates = sorted({os.path.basename(p)[:10] for p in affected
                if os.path.basename(p)[:10].count("-") == 2
                and os.path.basename(p)[:4].isdigit()
                and os.path.basename(p)[5:7].isdigit()
                and os.path.basename(p)[8:10].isdigit()})
print(f"# {len(affected)} affected folders -> {len(dates)} dates", file=sys.stderr)
for d in dates:
    print(d)
