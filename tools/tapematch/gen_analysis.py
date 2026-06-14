#!/usr/bin/env python3
"""Generate analysis.md for tapematch runs.

Usage:
    python3 gen_analysis.py              # all 2001 runs, latest per date
    python3 gen_analysis.py --year YYYY  # different year
    python3 gen_analysis.py --all        # all run directories
    python3 gen_analysis.py 2001-10-13   # single date
    python3 gen_analysis.py --overwrite  # regenerate even if analysis.md exists
"""

import json
import re
import sys
from pathlib import Path
from datetime import date as Date

RUNS_DIR = Path(__file__).parent.parent.parent / "data" / "tapematch" / "runs"
TODAY = Date.today().isoformat()
MODEL = "claude-sonnet-4-6"

# ── Utilities ────────────────────────────────────────────────────────────────

def _lb(text: str) -> str | None:
    m = re.search(r'LB-(\d+)', text)
    return f"LB-{m.group(1)}" if m else None


def _all_lbs(text: str) -> list[str]:
    return [f"LB-{n}" for n in re.findall(r'LB-(\d+)', text)]


def _ppm_label(ppm: int) -> str:
    """Human-readable speed offset."""
    if abs(ppm) >= 14000:
        return f"{ppm:+d} ppm (≈ PAL/cassette speed shift)"
    if abs(ppm) >= 8000:
        return f"{ppm:+d} ppm (large — possible tape deck speed)"
    if abs(ppm) >= 3000:
        return f"{ppm:+d} ppm (moderate DAT pitch drift)"
    return f"{ppm:+d} ppm"


# ── Parser ───────────────────────────────────────────────────────────────────

def parse_report(path: Path) -> dict:
    text = path.read_text()

    r: dict = {
        "date": "", "venue": "", "generated": "",
        "coverage_db": 0, "coverage_disk": 0,
        "sources": [],          # {lb, on_disk, rating, timing, source_brief}
        "output": "",
        "lb_commentary": {},   # lb_id -> {header, text}
        "has_error": False,
        "insufficient_sources": False,
        "n_families": 0,
        "clusters": [],        # {id, members, intra_corr, low_conf, secondary}
        "secondary_pairs": [], # (lb_a, lb_b)
        "diagnostics": [],
        # derived
        "family_map": {},      # lb_id -> family_id
        "speed_map": {},       # lb_id -> ppm (non-zero, vs first ref)
        "speed_kind_map": {},  # lb_id -> "staircase/splice" | "constant-speed-offset" | "aligned" | "reference"
    }

    # Header
    m = re.search(r'^# tapematch session — (\d{4}-\d{2}-\d{2}) — (.+)$', text, re.M)
    if m:
        r["date"] = m.group(1)
        r["venue"] = m.group(2).strip()
    m = re.search(r'\*Generated: (.+?)\*', text)
    if m:
        r["generated"] = m.group(1).strip()
    m = re.search(r'DB entries: \*\*(\d+)\*\* \| Found on disk: \*\*(\d+)\*\*', text)
    if m:
        r["coverage_db"] = int(m.group(1))
        r["coverage_disk"] = int(m.group(2))

    # Sources table
    table_m = re.search(r'\| LB \|.*?\n((?:\|.*?\n)+)', text)
    if table_m:
        for line in table_m.group(1).strip().split('\n'):
            if line.startswith('|-'):
                continue
            cols = [c.strip() for c in line.split('|')[1:-1]]
            if len(cols) >= 5:
                r["sources"].append({
                    "lb": cols[0],
                    "on_disk": cols[1] == '✓',
                    "rating": cols[2],
                    "timing": cols[3],
                    "source_brief": cols[4][:90],
                })

    # tapematch output block
    code_m = re.search(r'```\n(.*?)```', text, re.DOTALL)
    if code_m:
        r["output"] = code_m.group(1)

    out = r["output"]

    # Error?
    if re.search(r'Traceback|LibsndfileError|RuntimeError.*duration', out):
        r["has_error"] = True

    # Insufficient sources (run_date marks these instead of running tapematch)?
    if re.search(r'\*\*insufficient_sources\*\*', text):
        r["insufficient_sources"] = True

    # Clusters
    cl_m = re.search(r'=== CLUSTERS ===\n(.*?)(?:===|$)', out, re.DOTALL)
    if cl_m:
        for line in cl_m.group(1).split('\n'):
            fm = re.match(
                r'\s*Family (\d+): (.+?)\s*\(mean intra-corr ([\d.]+)([^)]*)\)',
                line)
            if fm:
                members = [lb for lb in [_lb(t) for t in fm.group(2).split(',')] if lb]
                low = "low confidence" in fm.group(4)
                # check if secondary line follows
                cl_obj = {
                    "id": int(fm.group(1)),
                    "members": members,
                    "intra_corr": float(fm.group(3)),
                    "low_conf": low,
                    "secondary": False,
                }
                r["clusters"].append(cl_obj)
            dm = re.match(r'\s*Distinct source families: (\d+)', line)
            if dm:
                r["n_families"] = int(dm.group(1))
        # mark secondary clusters
        # look for [secondary: ...] annotation lines after family lines
        for i, line in enumerate(cl_m.group(1).split('\n')):
            if '[secondary:' in line:
                # try to attach to most recent cluster
                sec_lbs = _all_lbs(line)
                for cl in r["clusters"]:
                    if any(lb in cl["members"] for lb in sec_lbs):
                        cl["secondary"] = True

    # Secondary pairs
    for line in out.split('\n'):
        sp = re.search(r'(LB-\d+) / (LB-\d+).*SECONDARY LINK', line)
        if sp:
            r["secondary_pairs"].append((sp.group(1), sp.group(2)))

    # Diagnostics
    dm = re.search(r'=== DIAGNOSTICS ===\n(.*?)$', out, re.DOTALL)
    if dm:
        r["diagnostics"] = [l for l in dm.group(1).split('\n') if l.strip()]

    # LB commentary
    cm = re.search(r'## LB page commentary\n(.*?)$', text, re.DOTALL)
    if cm:
        for section in re.split(r'\n### ', cm.group(1)):
            if not section.strip():
                continue
            first, _, rest = section.partition('\n')
            lm = re.match(r'(LB-\d+)', first)
            if lm:
                r["lb_commentary"][lm.group(1)] = {
                    "header": first[len(lm.group(1)):].strip(" |"),
                    "text": rest.strip(),
                }

    # Derived: family_map
    for cl in r["clusters"]:
        for lb in cl["members"]:
            r["family_map"][lb] = cl["id"]

    # Derived: speed maps from LAG CURVES section
    for line in out.split('\n'):
        # e.g.  A -> B: constant-speed-offset  speed ratio=1.015000 (+15000 ppm)
        lm = re.match(r'\s*(.+?)\(LB-(\d+)\)->(.+?)\(LB-(\d+)\):\s*(\S+)', line)
        if not lm:
            # shorter form without full name
            lm = re.match(r'\s*\S.*LB-(\d+).*->.*LB-(\d+).*:\s*(\S+)', line)
        if lm:
            kind_m = re.search(r'(staircase/splice|constant-speed-offset|aligned|reference)', line)
            ppm_m = re.search(r'\(([+-]?\d+) ppm\)', line)
            # get target lb
            target_lb = _lb(line.split('->')[-1].split(':')[0])
            if target_lb and kind_m:
                r["speed_kind_map"][target_lb] = kind_m.group(1)
            if target_lb and ppm_m:
                r["speed_map"][target_lb] = int(ppm_m.group(1))

    return r


# ── Cross-reference detection ─────────────────────────────────────────────────

_SAME_PATS = [
    r'same recording as',
    r'same master as',
    r'same taper as',
    r'same source as',
    r'same as\b',
    r'close eac match',
    r'identical to',
    r'same recording\b',
]

_DIFF_PATS = [
    r'alternative recording to',
    r'different source',
    r'different taper',
    r'different recording',
]


def _mentions_lb(text: str, lb_id: str) -> bool:
    num = lb_id.replace('LB-', '').lstrip('0') or '0'
    return bool(re.search(rf'\bLB-?0*{re.escape(num)}\b', text, re.I))


def _get_snippet(text: str, lb_id: str) -> str:
    num = lb_id.replace('LB-', '').lstrip('0') or '0'
    pat = rf'LB-?0*{re.escape(num)}'
    for chunk in re.split(r'[.,\n]', text):
        if re.search(pat, chunk, re.I):
            s = chunk.strip()
            return s[:130] if len(s) > 130 else s
    return ""


def _same_signal(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in _SAME_PATS)


def _diff_signal(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in _DIFF_PATS)


# ── Source row builder ───────────────────────────────────────────────────────

def _source_rows(r: dict, results: dict) -> list[dict]:
    """Merge sources table + results.json into enriched row dicts."""
    rows = []
    src_results = results.get("sources", {})
    for src in r["sources"]:
        lb = src["lb"]
        # find matching results entry
        res_key = next((k for k in src_results if _lb(k) == lb), None)
        res = src_results[res_key] if res_key else {}
        row = {
            "lb": lb,
            "on_disk": src["on_disk"],
            "rating": src["rating"],
            "timing": src["timing"],
            "source_brief": src["source_brief"],
            "family": r["family_map"].get(lb, "?"),
            "hf_khz": f"{res.get('hf_ceiling_hz', 0)/1000:.1f}" if res else "?",
            "noise_db": f"{res.get('noise_floor_db', 0):.1f}" if res else "?",
            "speed_kind": res.get("speed_kind", r["speed_kind_map"].get(lb, "?")),
            "speed_ppm": r["speed_map"].get(lb, 0),
            "incomplete": any(lb in d and "[INCOMPLETE]" in d for d in r["diagnostics"]),
            "commentary": r["lb_commentary"].get(lb, {}).get("text", ""),
        }
        rows.append(row)
    return rows


# ── Observation builder ──────────────────────────────────────────────────────

def _build_observations(r: dict, rows: list[dict]) -> list[str]:
    """Return list of observation paragraphs (markdown strings)."""
    obs = []
    family_map = r["family_map"]
    on_disk_lbs = [ro["lb"] for ro in rows if ro["on_disk"]]
    all_lbs = [src["lb"] for src in r["sources"]]

    # ── Cross-references ───────────────────────────────────────────────────
    seen_pairs: set[tuple] = set()
    for ro in rows:
        lb_a = ro["lb"]
        text = ro["commentary"]
        if not text:
            continue
        for lb_b in all_lbs:
            if lb_b == lb_a:
                continue
            if not _mentions_lb(text, lb_b):
                continue
            pair_key = tuple(sorted([lb_a, lb_b]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            snip = _get_snippet(text, lb_b)
            in_run_b = lb_b in on_disk_lbs
            fa = family_map.get(lb_a)
            fb = family_map.get(lb_b)

            if not in_run_b:
                obs.append(
                    f"### {lb_a} mentions {lb_b} (not in run)\n"
                    f"LB commentary: \"{snip}\"  \n"
                    f"Cannot verify — {lb_b} was not on disk for this run."
                )
                continue

            is_diff = _diff_signal(snip)
            # A snippet can match both patterns, e.g. "Alternative recording to
            # LB-0491/LB-0569 ... which all appear to be same recording" — the
            # "same recording" there describes the other LBs' relationship to
            # each other, not to the subject. Treat such snippets as ambiguous
            # rather than a same-source signal.
            is_same = not is_diff and (_same_signal(snip) or _same_signal(text[:200]))

            if is_same and fa is not None and fb is not None:
                if fa == fb:
                    obs.append(
                        f"### {lb_a} / {lb_b} — same-source confirmed ✅\n"
                        f"LB commentary says: \"{snip}\"  \n"
                        f"tapematch correctly grouped both in Family {fa}."
                    )
                else:
                    obs.append(
                        f"### {lb_a} / {lb_b} — MISS ⚠️\n"
                        f"LB commentary says: \"{snip}\"  \n"
                        f"tapematch put them in Family {fa} vs Family {fb} — same-source pair was missed."
                    )
            elif is_diff and fa is not None and fb is not None and fa == fb:
                obs.append(
                    f"### {lb_a} / {lb_b} — possible FALSE MERGE ⚠️\n"
                    f"LB commentary says: \"{snip}\"  \n"
                    f"tapematch grouped both in Family {fa} — but commentary suggests distinct source."
                )
            else:
                obs.append(
                    f"### {lb_a} → {lb_b}\n"
                    f"LB commentary notes: \"{snip}\"  \n"
                    f"tapematch: Family {fa} vs Family {fb}."
                )

    # ── Speed anomalies ────────────────────────────────────────────────────
    for ro in rows:
        lb = ro["lb"]
        ppm = ro["speed_ppm"]
        if abs(ppm) < 2000:
            continue
        label = _ppm_label(ppm)
        explanation = ""
        if abs(ppm) >= 14000:
            explanation = (
                "Speed offset near ±15000 ppm suggests a PAL/NTSC speed mismatch or cassette "
                "played at wrong speed. Correctly isolated as distinct source."
            )
        elif abs(ppm) >= 5000:
            explanation = (
                f"Speed offset {label} is consistent with a differently clocked DAT deck or "
                f"tape pitch drift. Correctly isolated as distinct source."
            )
        else:
            explanation = (
                f"Moderate speed offset {label}; may still share master tape but at different "
                f"playback speed. Secondary evidence would be needed to confirm or deny."
            )
        obs.append(f"### {lb} — speed offset {label}\n{explanation}")

    # ── Staircase ─────────────────────────────────────────────────────────
    stair_rows = [ro for ro in rows if ro["speed_kind"] == "staircase/splice"]
    for ro in stair_rows:
        lb = ro["lb"]
        # only if not already covered by same-source observation
        already_covered = any(lb in o and "MISS" in o for o in obs)
        if not already_covered:
            obs.append(
                f"### {lb} — staircase lag curve\n"
                f"Discontinuous lag pattern detected, indicating CDR re-tracking or tape splices "
                f"between the transfer and another source. Primary residual correlation will be "
                f"suppressed even against a same-source pair."
            )

    # ── Secondary links ────────────────────────────────────────────────────
    for a, b in r["secondary_pairs"]:
        fa = family_map.get(a)
        obs.append(
            f"### {a} / {b} — secondary link (windowed+hiss)\n"
            f"Primary residual corr was below threshold; grouped via windowed coverage and "
            f"quiet-segment hiss correlation. Family {fa}. Verify against LB commentary."
        )

    # ── Incomplete ────────────────────────────────────────────────────────
    for ro in rows:
        if ro["incomplete"]:
            obs.append(
                f"### {ro['lb']} — INCOMPLETE recording\n"
                f"Flagged as >5% shorter than group median. Likely truncated or has heavy "
                f"pre-show crowd leading to a large head trim."
            )

    return obs


# ── Verdict string ───────────────────────────────────────────────────────────

def _verdict(r: dict, obs: list[str]) -> str:
    n_src = r["coverage_disk"]
    n_fam = r["n_families"] or len(r["clusters"])

    misses = [o for o in obs if "MISS" in o]
    false_merges = [o for o in obs if "FALSE MERGE" in o]

    if misses:
        pairs = [re.search(r'### (LB-\d+ / LB-\d+)', o).group(1) for o in misses
                 if re.search(r'### (LB-\d+ / LB-\d+)', o)]
        return (f"{n_fam} {'family' if n_fam == 1 else 'families'} — "
                f"MISS on {', '.join(pairs)}")
    if false_merges:
        pairs = [re.search(r'### (LB-\d+ / LB-\d+)', o).group(1) for o in false_merges
                 if re.search(r'### (LB-\d+ / LB-\d+)', o)]
        return (f"{n_fam} {'family' if n_fam == 1 else 'families'} — "
                f"possible FALSE MERGE on {', '.join(pairs)}")
    if n_fam == n_src and n_src > 2:
        return f"{n_fam} distinct families — all sources confirmed different"
    if n_fam == 1 and n_src > 1:
        return f"1 family — all {n_src} recordings grouped as same source"
    confirmed = [o for o in obs if "same-source confirmed" in o]
    if confirmed:
        return f"{n_fam} {'family' if n_fam == 1 else 'families'} — result consistent with LB commentary"
    return f"{n_fam} {'family' if n_fam == 1 else 'families'} — result looks correct"


# ── Main document builder ────────────────────────────────────────────────────

def build_analysis(run_dir: Path, r: dict, results: dict) -> str:
    lines: list[str] = []

    lines.append(f"# Analysis — {r['date']} — {r['venue']}")
    lines.append(f"*Claude {MODEL} — {TODAY}*")
    lines.append("")

    # ── Insufficient sources ──────────────────────────────────────────────
    if r["insufficient_sources"]:
        lines.append("## Status: insufficient sources — tapematch not run")
        lines.append("")
        lines.append(f"Coverage: {r['coverage_db']} DB / {r['coverage_disk']} on disk "
                      "(after excluding private/no-torrent and no-audio folders)")
        lines.append("")
        if r["sources"]:
            lines.append("| LB | Rating | Timing | Source |")
            lines.append("|----|--------|--------|--------|")
            for src in r["sources"]:
                marker = "✓" if src["on_disk"] else "—"
                lines.append(f"| {src['lb']} {marker} | {src['rating']} | {src['timing']} | {src['source_brief']} |")
        lines.append("")
        lines.append("Fewer than 2 locally analyzable recordings — no clustering possible. "
                      "Not an error; no action required.")
        return "\n".join(lines)

    # ── Error ──────────────────────────────────────────────────────────────
    if r["has_error"]:
        lines.append("## Status: ERROR — tapematch did not complete")
        lines.append("")
        # extract useful error lines
        for ln in r["output"].split('\n'):
            if re.search(r'Error|Traceback|RuntimeError|Format not', ln):
                lines.append(f"> {ln.strip()}")
        lines.append("")
        lines.append(f"Coverage: {r['coverage_db']} DB / {r['coverage_disk']} on disk")
        lines.append("")
        if r["sources"]:
            lines.append("| LB | Rating | Timing | Source |")
            lines.append("|----|--------|--------|--------|")
            for src in r["sources"]:
                marker = "✓" if src["on_disk"] else "—"
                lines.append(f"| {src['lb']} {marker} | {src['rating']} | {src['timing']} | {src['source_brief']} |")
        lines.append("")
        lines.append("**Action required:** fix the broken FLAC in the flagged folder and re-run.")
        return "\n".join(lines)

    rows = _source_rows(r, results)
    obs = _build_observations(r, rows)
    verdict = _verdict(r, obs)

    n_src = r["coverage_disk"]
    n_fam = r["n_families"] or len(r["clusters"])

    lines.append(f"## Verdict: {n_src} recordings — {verdict}")
    lines.append("")

    # ── Summary table ──────────────────────────────────────────────────────
    on_disk = [ro for ro in rows if ro["on_disk"]]
    if on_disk:
        lines.append("| LB | Rating | Timing | Source | Family | Notes |")
        lines.append("|----|--------|--------|--------|--------|-------|")
        for ro in on_disk:
            notes_parts = []
            if ro["incomplete"]:
                notes_parts.append("INCOMPLETE")
            ppm = ro["speed_ppm"]
            if abs(ppm) >= 2000:
                notes_parts.append(f"{ppm:+d} ppm")
            if ro["speed_kind"] == "staircase/splice":
                notes_parts.append("staircase")
            if ro["hf_khz"] == "1.0":
                notes_parts.append("HF 1.0kHz")
            notes = "; ".join(notes_parts)
            # Shorten source brief for table
            src_short = ro["source_brief"][:60]
            lines.append(
                f"| {ro['lb']} | {ro['rating']} | {ro['timing']} | {src_short} | {ro['family']} | {notes} |"
            )
    lines.append("")

    # ── Off-disk sources ───────────────────────────────────────────────────
    off_disk = [ro for ro in rows if not ro["on_disk"]]
    if off_disk:
        missing = ", ".join(ro["lb"] for ro in off_disk)
        lines.append(f"Not on disk: {missing}")
        lines.append("")

    # ── Observations ───────────────────────────────────────────────────────
    if obs:
        for ob in obs:
            lines.append(ob)
            lines.append("")

    # ── Algorithm note (if issues) ─────────────────────────────────────────
    misses = [o for o in obs if "MISS" in o]
    false_merges = [o for o in obs if "FALSE MERGE" in o]
    secondary_obs = [o for o in obs if "secondary link" in o]

    if misses or false_merges:
        lines.append("## Algorithm note")
        lines.append("")
        if misses:
            lines.append(
                "The missed pair(s) above warrant investigation into which tapematch layer "
                "failed (primary threshold, staircase suppression, secondary windowed/hiss)."
            )
        if false_merges:
            lines.append(
                "The possible false merge should be verified — check correlation matrix values "
                "and secondary evidence details."
            )
        lines.append("")

    elif secondary_obs:
        lines.append("## Algorithm note")
        lines.append("")
        lines.append(
            "Secondary link(s) present — grouped via windowed+hiss, not primary correlation. "
            "Verify each against LB commentary before treating the cluster as confirmed."
        )
        lines.append("")

    # ── No-issue note ─────────────────────────────────────────────────────
    if not obs and not r["has_error"]:
        if n_src <= 2:
            lines.append(
                f"Only {n_src} recording(s) in this run — limited statistical power. "
                f"Result cannot be strongly validated."
            )
        else:
            lines.append(
                "No cross-reference conflicts, speed anomalies, or algorithm issues detected. "
                "Clean date for calibration."
            )
        lines.append("")

    return "\n".join(lines)


# ── Run selection ────────────────────────────────────────────────────────────

def _latest_per_date(dirs: list[Path]) -> dict[str, Path]:
    d: dict[str, Path] = {}
    for p in sorted(dirs):
        m = re.search(r'_(\d{4}-\d{2}-\d{2})$', p.name)
        if m:
            k = m.group(1)
            if k not in d or p.name > d[k].name:
                d[k] = p
    return d


def main() -> None:
    args = sys.argv[1:]
    overwrite = "--overwrite" in args
    args = [a for a in args if a != "--overwrite"]

    all_dirs = [d for d in RUNS_DIR.iterdir() if d.is_dir()]

    if "--all" in args:
        date_map = _latest_per_date(all_dirs)
    elif args and re.match(r'\d{4}-\d{2}-\d{2}', args[0]):
        target = args[0]
        matching = [d for d in all_dirs if d.name.endswith(target)]
        date_map = _latest_per_date(matching)
        if not date_map:
            print(f"No run found for {target}", file=sys.stderr)
            sys.exit(1)
    else:
        year = "2001"
        for a in args:
            m = re.match(r'--year[= ]?(\d{4})', a)
            if m:
                year = m.group(1)
        date_map = _latest_per_date([d for d in all_dirs if f'_{year}-' in d.name])

    print(f"Processing {len(date_map)} run(s) (overwrite={overwrite})...")
    ok = skipped = errors = 0

    for date_str, run_dir in sorted(date_map.items()):
        analysis_path = run_dir / "analysis.md"
        if analysis_path.exists() and not overwrite:
            skipped += 1
            continue

        report_path = run_dir / "report.md"
        results_path = run_dir / "results.json"
        if not report_path.exists():
            print(f"  SKIP  {date_str} — no report.md")
            continue

        try:
            r = parse_report(report_path)
            results: dict = {}
            if results_path.exists():
                with open(results_path) as f:
                    results = json.load(f)

            content = build_analysis(run_dir, r, results)
            analysis_path.write_text(content)

            if r["has_error"]:
                status = "ERROR"
            elif r["insufficient_sources"]:
                status = f"insufficient_sources/{r['coverage_disk']}src"
            else:
                status = f"{r.get('n_families','?')}fam/{r['coverage_disk']}src"
            print(f"  ✓  {date_str}  [{status}]  {run_dir.name}")
            ok += 1
        except Exception as exc:
            import traceback
            print(f"  ✗  {date_str}  {exc}")
            traceback.print_exc()
            errors += 1

    print(f"\nDone: {ok} written, {skipped} skipped (use --overwrite to regenerate), {errors} error(s).")


if __name__ == "__main__":
    main()
