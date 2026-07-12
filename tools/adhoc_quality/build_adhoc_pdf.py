"""Render the adhoc TapeMatch + Quality results as a print-ready HTML report.

Reads ``adhoc_quality.json`` for exact metrics; the TapeMatch matrix/families are
embedded from the parsed run log. Emits ``adhoc_report.html`` (LibreOffice then
converts it to PDF). Styling is deliberately table-based + inline colors so the
LibreOffice HTML importer renders it faithfully.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
rows = json.load(open(ROOT / "adhoc_quality.json"))

# ---- short labels (order = residual matrix order) --------------------------
LABELS = {
    "1997-11-11 Lisle, IL (DAT from D master)": "DAT / D-master",
    "1997-11-11 Lisle, IL (LB-13287)": "LB-13287",
    "1997-11-11 Lisle, Illinois (LB-04283)": "LB-04283",
    "1997-11-11 Lisle, Illinois (LB-09042)": "LB-09042",
    "1997-11-11 Lisle, Illinois (LB-9394) NO TORRENT": "LB-9394",
    "1997-11-11 Lisle, Illinois, Benedictine University - Dan and Ada Rice Athletic Center (LB-04854)": "LB-04854",
    "1997-11-11 Lisle, Illinois, Benedictine University, Dan and Ada Rice Athletic Center (LB-01126)": "LB-01126",
}
FAMILY = {  # folder-name -> (family label, verdict)
    "DAT / D-master": ("Family 1", "distinct source"),
    "LB-13287": ("Family 2", "same source (core)"),
    "LB-04283": ("Family 3", "distinct source"),
    "LB-09042": ("Family 2", "same source (core)"),
    "LB-9394": ("Family 4", "distinct source"),
    "LB-04854": ("Family 2", "same source (core)"),
    "LB-01126": ("Family 2", "tentative (unverified)"),
}

MATRIX_ORDER = ["DAT / D-master", "LB-13287", "LB-04283", "LB-09042",
                "LB-9394", "LB-04854", "LB-01126"]
MATRIX = [
    [1.000, 0.046, 0.010, 0.009, 0.062, 0.038, 0.035],
    [0.046, 1.000, 0.012, 0.914, 0.021, 0.991, 0.003],
    [0.010, 0.012, 1.000, 0.007, 0.008, 0.008, 0.007],
    [0.009, 0.914, 0.007, 1.000, 0.018, 0.959, 0.008],
    [0.062, 0.021, 0.008, 0.018, 1.000, 0.020, 0.128],
    [0.038, 0.991, 0.008, 0.959, 0.020, 1.000, 0.018],
    [0.035, 0.003, 0.007, 0.008, 0.128, 0.018, 1.000],
]


def grade_color(letter: str) -> str:
    if letter.startswith("A"):
        return "#1a7f37"   # green
    if letter.startswith("B"):
        return "#9a6700"   # amber
    return "#8b3a2b"       # red-brown


def cell_color(v: float) -> str:
    """Heatmap: same-source high = green, mid = amber, independent = pale."""
    if v >= 0.999:
        return "#c9cdd2"                     # diagonal (self)
    if v >= 0.90:
        return "#7fc99a"                     # strong same-source
    if v >= 0.40:
        return "#bfe3cd"
    if v >= 0.13:
        return "#f3e3b3"                     # weak
    return "#f6f7f8"                         # independent


def bar(value: float, vmax: float, color: str, segments: int = 10) -> str:
    """Reliable text-block bar (LibreOffice HTML ignores sized nested tables)."""
    frac = max(0.0, min(1.0, value / vmax))
    filled = round(frac * segments)
    return (f'<span style="color:{color};letter-spacing:-1px;font-size:11px">'
            f'{"&#9608;" * filled}</span>'
            f'<span style="color:#dfe3e6;letter-spacing:-1px;font-size:11px">'
            f'{"&#9608;" * (segments - filled)}</span>')


def m(row, key):
    v = row["metrics"].get(key)
    return v if isinstance(v, (int, float)) else None


by_label = {LABELS[r["folder"]]: r for r in rows}
ranked = sorted(rows, key=lambda r: -r.get("abs_score", 0))

# --------------------------------------------------------------------------- #
parts: list[str] = []
A = parts.append

A('<div class="wrap">')
A('<div class="hdr">')
A('<div class="kicker">Adhoc Analysis · Bob Dylan live archive</div>')
A('<h1>1997-11-11 &mdash; Lisle, Illinois</h1>')
A('<div class="sub">Benedictine University, Dan &amp; Ada Rice Athletic Center &nbsp;·&nbsp; '
  '7 audience recordings &nbsp;·&nbsp; ~108&nbsp;min each</div>')
A('<div class="meta">TapeMatch source clustering + Concert&nbsp;Ranker quality scoring '
  '&nbsp;|&nbsp; run <code>20260711_142949</code> &nbsp;|&nbsp; generated 2026-07-11</div>')
A('</div>')

# ---- KPI strip ----
n_ok = sum(1 for r in rows if r["status"] == "ok")
A('<table class="kpi"><tr>')
for big, small in [("7", "sources scanned"), ("4", "distinct source lineages"),
                   ("3", "confirmed same-source"), ("A / B+", "quality grade range")]:
    A(f'<td><div class="kpi-big">{big}</div><div class="kpi-small">{small}</div></td>')
A('</tr></table>')

# ---- Section 1: combined table ----
A('<h2>1 &nbsp; Combined summary</h2>')
A('<table class="grid"><thead><tr>'
  '<th style="text-align:left">Recording</th><th>Grade</th><th>Score</th>'
  '<th>Class</th><th>Tracks</th><th>Length</th>'
  '<th style="text-align:left">TapeMatch family</th><th style="text-align:left">Source verdict</th>'
  '</tr></thead><tbody>')
for r in ranked:
    lab = LABELS[r["folder"]]
    fam, verdict = FAMILY[lab]
    gc = grade_color(r["abs_grade"])
    dur = f'{r["duration_sec"]/60:.0f} min'
    vclass = "vok" if "same" in verdict else ("vwarn" if "tentative" in verdict else "vdist")
    A(f'<tr><td style="text-align:left"><b>{lab}</b></td>'
      f'<td><span class="badge" style="background:{gc}">{r["abs_grade"]}</span></td>'
      f'<td>{r["abs_score"]:.1f}</td><td>{r["source_class"]}</td>'
      f'<td>{r["n_tracks"]}</td><td>{dur}</td>'
      f'<td style="text-align:left">{fam}</td>'
      f'<td style="text-align:left" class="{vclass}">{verdict}</td></tr>')
A('</tbody></table>')
A('<div class="note">All 7 decoded and scored, including the Shorten (<code>.shn</code>) '
  'LB-01126 and the two-disc LB-04283. Ranked best quality first.</div>')

# ---- Section 2: families ----
A('<h2>2 &nbsp; TapeMatch &mdash; source clustering</h2>')
A('<p class="lead">Four independent recording lineages. Only one same-source cluster '
  '(Family&nbsp;2) exists; everything else is an independent recording.</p>')
fam_cards = [
    ("Family 2", "same", "One taper &mdash; 3 confirmed copies",
     "<b>LB-13287, LB-09042, LB-04854</b> share a recording chain: primary residual "
     "correlation <b>0.91&ndash;0.99</b> (unambiguous same source). "
     "<b>LB-01126</b> is attached but <i>chain-unverified</i> &mdash; its correlation to the "
     "trio is ~0.00, merged only via a secondary/fingerprint path. Treat as unconfirmed."),
    ("Family 1", "dist", "DAT from D-master", "Distinct source &mdash; best cross-family corr 0.062."),
    ("Family 3", "dist", "LB-04283", "Distinct source &mdash; best cross-family corr 0.012."),
    ("Family 4", "dist", "LB-9394 (NO TORRENT)", "Distinct source &mdash; best cross-family corr 0.128."),
]
A('<table class="cards"><tr>')
for i, (fam, kind, title, body) in enumerate(fam_cards):
    edge = "#1a7f37" if kind == "same" else "#5b6470"
    if i == 2:
        A('</tr><tr>')
    A(f'<td class="card" style="border-left:5px solid {edge}">'
      f'<div class="card-fam">{fam}</div><div class="card-title">{title}</div>'
      f'<div class="card-body">{body}</div></td>')
A('</tr></table>')

# ---- residual matrix heatmap ----
A('<h3>Residual correlation matrix</h3>')
A('<table class="matrix"><thead><tr><th></th>')
for lab in MATRIX_ORDER:
    A(f'<th>{lab.replace("DAT / D-master","DAT")}</th>')
A('</tr></thead><tbody>')
for i, lab in enumerate(MATRIX_ORDER):
    A(f'<tr><th class="rlab">{lab.replace("DAT / D-master","DAT")}</th>')
    for j in range(len(MATRIX_ORDER)):
        v = MATRIX[i][j]
        strong = "font-weight:700;" if (v >= 0.90 and i != j) else ""
        A(f'<td style="background:{cell_color(v)};{strong}">{v:.3f}</td>')
    A('</tr>')
A('</tbody></table>')
A('<div class="legend">'
  '<span class="sw" style="background:#7fc99a"></span>&ge;0.90 same source &nbsp;&nbsp;'
  '<span class="sw" style="background:#f3e3b3"></span>0.13&ndash;0.90 weak &nbsp;&nbsp;'
  '<span class="sw" style="background:#f6f7f8;border:1px solid #ccc"></span>&lt;0.13 independent '
  '&nbsp;&nbsp;<span class="sw" style="background:#c9cdd2"></span>self</div>')
A('<div class="note">23 pairs were flagged <code>speed-unknown</code> (ratio confidence '
  '&lt; 6.0) and routed to fingerprint only &mdash; real speed offsets (up to +25000&nbsp;ppm '
  'on LB-01126) mean those cross-family scores sit at the floor by construction, not proof '
  'of difference. The three strong Family-2 links aligned cleanly and are unaffected.</div>')

# ---- Section 3: quality ----
A('<h2>3 &nbsp; Quality scoring &mdash; Concert Ranker (AUD model)</h2>')
A('<table class="grid quality"><thead><tr>'
  '<th style="text-align:left">Recording</th><th>Grade</th>'
  '<th style="text-align:left">Score / 100</th>'
  '<th>HF ceiling</th><th style="text-align:left">Crowd SNR (perf vs. crowd)</th>'
  '<th>Clipping</th></tr></thead><tbody>')
for r in ranked:
    lab = LABELS[r["folder"]]
    gc = grade_color(r["abs_grade"])
    hf = m(r, "hf_ceiling_hz"); snr = m(r, "crowd_snr_db")
    clip = m(r, "clip_fraction")
    A(f'<tr><td style="text-align:left"><b>{lab}</b></td>'
      f'<td><span class="badge" style="background:{gc}">{r["abs_grade"]}</span></td>'
      f'<td style="text-align:left;white-space:nowrap">'
      f'<span class="barval" style="margin:0 6px 0 0">{r["abs_score"]:.1f}</span>'
      f'{bar(r["abs_score"],100,gc)}</td>'
      f'<td>{hf/1000:.1f} kHz</td>'
      f'<td style="text-align:left;white-space:nowrap">'
      f'<span class="barval" style="margin:0 6px 0 0">{snr:.2f} dB</span>'
      f'{bar(snr or 0,8,"#3b7dd8")}</td>'
      f'<td>{clip*100:.1f}%</td></tr>')
A('</tbody></table>')
A('<div class="note">Within the confirmed same-source Family&nbsp;2, <b>LB-09042 grades '
  'highest (A&minus;, 84.0)</b> &mdash; the copy to keep. LB-04283 (B+) is the weakest of '
  'the seven. All sources: 0% clipping, full ~14&ndash;15&nbsp;kHz HF content.</div>')

# ---- Section 4: takeaways ----
A('<h2>4 &nbsp; What to keep</h2>')
A('<table class="take"><tr>'
  '<td class="keep"><div class="tk-h">Keep &mdash; 4 independent sources</div>'
  '<ul><li><b>DAT / D-master</b> (A, 87.6)</li>'
  '<li><b>LB-04283</b> (B+, 76.2)</li>'
  '<li><b>LB-9394</b> (A&minus;, 86.6)</li>'
  '<li><b>LB-09042</b> (A&minus;, 84.0) &mdash; best copy of Family&nbsp;2</li></ul></td>'
  '<td class="dedup"><div class="tk-h">De-dup candidates</div>'
  '<ul><li><b>LB-13287</b>, <b>LB-04854</b> &mdash; same recording as LB-09042 '
  '(corr 0.96&ndash;0.99)</li>'
  '<li><b>LB-01126</b> &mdash; unconfirmed Family-2 link; highest quality grade '
  '(A, 90.9), so keep pending a manual check</li></ul></td>'
  '</tr></table>')

A('<div class="foot">Sources: <code>adhoc_tapematch.log</code> &middot; '
  '<code>adhoc_quality.json</code> &middot; archived run '
  '<code>data/tapematch/runs/20260711_142949_1997-11-11/</code>. '
  'Quality = Concert Ranker AUD model (no DB writes). '
  'HF ceiling read at native rate; TapeMatch analysis runs at 16&nbsp;kHz so its internal '
  'lineage HF figures are not comparable.</div>')
A('</div>')

body = "\n".join(parts)

CSS = """
@page { size: A4; margin: 14mm 13mm; }
* { box-sizing: border-box; }
body { font-family: 'Liberation Sans','DejaVu Sans',Arial,sans-serif; color:#1c2126;
       font-size:13px; line-height:1.5; }
.wrap { width:100%; }
.hdr { border-bottom:3px solid #1a2733; padding-bottom:9px; margin-bottom:12px; }
.kicker { text-transform:uppercase; letter-spacing:2px; font-size:11px; color:#5b6470;
          font-weight:700; }
h1 { font-size:29px; margin:3px 0 2px; color:#101820; letter-spacing:-0.3px; }
.sub { font-size:15px; color:#33404d; font-weight:600; }
.meta { font-size:11.5px; color:#6b7580; margin-top:4px; }
h2 { font-size:17.5px; margin:18px 0 6px; color:#101820; border-bottom:1px solid #d7dde2;
     padding-bottom:3px; }
h3 { font-size:14.5px; margin:12px 0 5px; color:#26313b; }
p.lead, .lead { font-size:13px; color:#33404d; margin:2px 0 8px; }
code { background:#eef1f3; padding:0 3px; border-radius:2px; font-size:11.5px;
       font-family:'Liberation Mono','DejaVu Sans Mono',monospace; }
.note { font-size:11.5px; color:#5b6470; margin:6px 0 2px; line-height:1.45; }

table.kpi { width:100%; border-collapse:collapse; margin:4px 0 6px; }
table.kpi td { width:25%; text-align:center; border:1px solid #e2e7eb; background:#f7f9fa;
               padding:9px 4px; }
.kpi-big { font-size:25px; font-weight:800; color:#1a2733; }
.kpi-small { font-size:11px; color:#5b6470; text-transform:uppercase; letter-spacing:0.6px; }

table.grid { width:100%; border-collapse:collapse; margin-top:4px; }
table.grid th, table.grid td { border-bottom:1px solid #e4e9ed; padding:5px 6px;
       text-align:center; font-size:12.5px; }
table.grid thead th { background:#1a2733; color:#fff; border-bottom:none; font-size:11px;
       text-transform:uppercase; letter-spacing:0.5px; font-weight:700; }
table.grid tbody tr:nth-child(even) { background:#f7f9fa; }
.badge { display:inline-block; color:#fff; font-weight:700; font-size:13.5px;
         line-height:18px; padding:2px 11px; border-radius:3px; min-width:28px; }
.vok { color:#1a7f37; font-weight:600; }
.vdist { color:#5b6470; }
.vwarn { color:#9a6700; font-weight:600; }
.barval { font-size:11.5px; color:#33404d; margin-left:5px; vertical-align:1px; }

table.cards { width:100%; border-collapse:separate; border-spacing:6px; margin:4px 0; }
td.card { width:50%; background:#f7f9fa; padding:8px 10px; vertical-align:top;
          border:1px solid #e2e7eb; }
.card-fam { font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#5b6470;
            font-weight:700; }
.card-title { font-size:14.5px; font-weight:700; color:#101820; margin:1px 0 3px; }
.card-body { font-size:11.5px; color:#33404d; line-height:1.45; }

table.matrix { border-collapse:collapse; margin:4px 0; font-size:11px;
               page-break-inside:avoid; }
table.cards, table.take, table.kpi { page-break-inside:avoid; }
h2, h3 { page-break-after:avoid; }
table.matrix th { background:#1a2733; color:#fff; padding:4px 5px; font-size:10.5px;
                  font-weight:600; }
table.matrix th.rlab { text-align:right; }
table.matrix td { border:1px solid #fff; padding:4px 6px; text-align:center;
                  color:#1c2126; min-width:38px; }
.legend { font-size:11px; color:#5b6470; margin-top:3px; }
.sw { display:inline-block; width:11px; height:11px; vertical-align:-1px; margin-right:3px; }

table.take { width:100%; border-collapse:separate; border-spacing:6px; }
td.keep, td.dedup { width:50%; vertical-align:top; padding:8px 12px; border:1px solid #e2e7eb; }
td.keep { background:#eef7f0; }
td.dedup { background:#fbf5ea; }
.tk-h { font-size:13px; font-weight:700; margin-bottom:3px; color:#101820; }
td.keep ul, td.dedup ul { margin:0; padding-left:16px; }
td.keep li, td.dedup li { font-size:12px; margin:3px 0; }

.foot { margin-top:16px; padding-top:7px; border-top:1px solid #d7dde2; font-size:10.5px;
        color:#6b7580; line-height:1.4; }
"""

htmlout = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
           f"<title>Adhoc Report 1997-11-11 Lisle</title><style>{CSS}</style></head>"
           f"<body>{body}</body></html>")
(ROOT / "adhoc_report.html").write_text(htmlout)
print("wrote adhoc_report.html")
