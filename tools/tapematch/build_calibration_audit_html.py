"""Renders calibration_audit.json into a self-contained HTML audit page."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "calibration_audit.json").read_text())

# Drop always-null columns (human_judgment/human_notes are NULL DB-wide).
for r in rows:
    r.pop("human_judgment", None)
    r.pop("human_notes", None)
    r.pop("scored", None)
    r.pop("folder_a", None)
    r.pop("folder_b", None)

cats = Counter(r["verdict_category"] for r in rows)
suspect_n = sum(1 for r in rows if r["label_suspect"])
unique_lb = len(set(r["lb_a"] for r in rows) | set(r["lb_b"] for r in rows))
precision = cats["TP"] / (cats["TP"] + cats["FP"]) * 100
recall = cats["TP"] / (cats["TP"] + cats["FN"]) * 100

data_json = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")

html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>TapeMatch Calibration Audit</title>
<style>
:root {
  --paper: #f5f7f8;
  --ink: #16202b;
  --ink-soft: #4d5c6b;
  --line: #d7dee3;
  --surface: #ffffff;
  --surface-2: #eef2f4;
  --accent: #0f9d94;
  --accent-soft: #0f9d9418;
  --tp: #2f8f5b;
  --tp-bg: #2f8f5b1a;
  --fn: #b8791a;
  --fn-bg: #b8791a1a;
  --fp: #c4453f;
  --fp-bg: #c4453f22;
  --tn: #74848f;
  --tn-bg: #74848f14;
  --suspect: #8654c9;
  --suspect-bg: #8654c91c;
  --font-ui: -apple-system, "Segoe UI", "Inter", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #10151a;
    --ink: #e7edf1;
    --ink-soft: #93a2ae;
    --line: #26333c;
    --surface: #161d23;
    --surface-2: #1c252c;
    --accent: #3bd6c9;
    --accent-soft: #3bd6c920;
    --tp: #57c98a;
    --tp-bg: #57c98a1e;
    --fn: #e0a748;
    --fn-bg: #e0a7481e;
    --fp: #ef6b64;
    --fp-bg: #ef6b6428;
    --tn: #7f909b;
    --tn-bg: #7f909b1a;
    --suspect: #b590ef;
    --suspect-bg: #b590ef22;
  }
}
:root[data-theme="dark"] {
  --paper: #10151a; --ink: #e7edf1; --ink-soft: #93a2ae; --line: #26333c;
  --surface: #161d23; --surface-2: #1c252c; --accent: #3bd6c9; --accent-soft: #3bd6c920;
  --tp: #57c98a; --tp-bg: #57c98a1e; --fn: #e0a748; --fn-bg: #e0a7481e;
  --fp: #ef6b64; --fp-bg: #ef6b6428; --tn: #7f909b; --tn-bg: #7f909b1a;
  --suspect: #b590ef; --suspect-bg: #b590ef22;
}
:root[data-theme="light"] {
  --paper: #f5f7f8; --ink: #16202b; --ink-soft: #4d5c6b; --line: #d7dee3;
  --surface: #ffffff; --surface-2: #eef2f4; --accent: #0f9d94; --accent-soft: #0f9d9418;
  --tp: #2f8f5b; --tp-bg: #2f8f5b1a; --fn: #b8791a; --fn-bg: #b8791a1a;
  --fp: #c4453f; --fp-bg: #c4453f22; --tn: #74848f; --tn-bg: #74848f14;
  --suspect: #8654c9; --suspect-bg: #8654c91c;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-ui);
  line-height: 1.45;
}
.wrap { max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
header h1 {
  font-size: 1.5rem;
  margin: 0 0 0.3rem;
  letter-spacing: -0.01em;
  text-wrap: balance;
}
header p {
  color: var(--ink-soft);
  max-width: 68ch;
  margin: 0.2rem 0 0;
  font-size: 0.92rem;
}
header code {
  font-family: var(--font-mono);
  background: var(--surface-2);
  padding: 0.05em 0.35em;
  border-radius: 4px;
  font-size: 0.88em;
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(108px, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  margin: 1.5rem 0 1.75rem;
}
.stat {
  background: var(--surface);
  padding: 0.85rem 1rem;
}
.stat .n {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 1.35rem;
  font-weight: 600;
}
.stat .l {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-soft);
  margin-top: 0.15rem;
}
.stat.tp .n { color: var(--tp); } .stat.fn .n { color: var(--fn); }
.stat.fp .n { color: var(--fp); } .stat.suspect .n { color: var(--suspect); }
.stat.accent .n { color: var(--accent); }

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
  position: sticky;
  top: 0;
  background: var(--paper);
  padding: 0.75rem 0;
  z-index: 5;
  border-bottom: 1px solid var(--line);
}
#search {
  font: inherit;
  font-family: var(--font-mono);
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink);
  border-radius: 7px;
  padding: 0.5rem 0.75rem;
  min-width: 240px;
  flex: 1 1 240px;
}
#search:focus, .chip:focus-visible, .toggle:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.chipset { display: flex; gap: 0.35rem; flex-wrap: wrap; }
.chip {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-soft);
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
}
.chip[aria-pressed="true"] { color: var(--paper); border-color: transparent; }
.chip.all[aria-pressed="true"] { background: var(--ink-soft); }
.chip.tp[aria-pressed="true"] { background: var(--tp); }
.chip.fn[aria-pressed="true"] { background: var(--fn); }
.chip.fp[aria-pressed="true"] { background: var(--fp); }
.chip.tn[aria-pressed="true"] { background: var(--tn); }
.toggle {
  display: inline-flex; align-items: center; gap: 0.4rem;
  font-size: 0.82rem; color: var(--ink-soft); cursor: pointer;
  border: 1px solid var(--line); border-radius: 999px; padding: 0.4rem 0.75rem;
  background: var(--surface); user-select: none;
}
.toggle input { accent-color: var(--suspect); }
.toggle.active { color: var(--suspect); border-color: var(--suspect); background: var(--suspect-bg); }
#count { font-size: 0.82rem; color: var(--ink-soft); margin-left: auto; font-variant-numeric: tabular-nums; white-space: nowrap; }

.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 0.83rem; }
thead th {
  position: sticky; top: 49px;
  background: var(--surface-2);
  text-align: left;
  padding: 0.55rem 0.7rem;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-soft);
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  white-space: nowrap;
}
thead th:hover { color: var(--ink); }
thead th.sorted { color: var(--accent); }
tbody td {
  padding: 0.5rem 0.7rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: none; }
tbody tr.suspect { box-shadow: inset 3px 0 0 var(--suspect); }
tbody tr.cat-FP { background: var(--fp-bg); }
td.note {
  font-family: var(--font-ui);
  white-space: normal;
  max-width: 46ch;
  color: var(--ink-soft);
  font-size: 0.8rem;
}
.pill {
  display: inline-block; padding: 0.12em 0.55em; border-radius: 5px;
  font-weight: 700; font-size: 0.72rem; letter-spacing: 0.02em;
}
.pill.TP { color: var(--tp); background: var(--tp-bg); }
.pill.FN { color: var(--fn); background: var(--fn-bg); }
.pill.FP { color: var(--fp); background: var(--fp-bg); }
.pill.TN { color: var(--tn); background: var(--tn-bg); }
.susp-mark { color: var(--suspect); font-weight: 700; }
.truth-same { color: var(--ink); } .truth-diff { color: var(--ink-soft); }
tbody td.lb { color: var(--accent); }
footer { margin-top: 1.5rem; color: var(--ink-soft); font-size: 0.78rem; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>TapeMatch Calibration Audit</h1>
  <p>Every pair in the frozen calibration set (<code>regression_set.json</code>), its ground-truth
  label, and the verdict the currently shipped config produces. <strong>Truth</strong> is the LB
  catalog's <code>lb_says_same</code> field (curator/community notes claiming "same recording" or
  "different recording") &mdash; not independently verified audio matching. Rows marked
  <span class="susp-mark">&#9679; suspect</span> have independent evidence (waveform correlation,
  family match) that contradicts the truth label.</p>
</header>

<div class="stats">
  <div class="stat accent"><div class="n">__TOTAL__</div><div class="l">Pairs</div></div>
  <div class="stat accent"><div class="n">__ULB__</div><div class="l">Unique LB#</div></div>
  <div class="stat tp"><div class="n">__TP__</div><div class="l">TP</div></div>
  <div class="stat fn"><div class="n">__FN__</div><div class="l">FN</div></div>
  <div class="stat fp"><div class="n">__FP__</div><div class="l">FP</div></div>
  <div class="stat"><div class="n">__TN__</div><div class="l">TN</div></div>
  <div class="stat suspect"><div class="n">__SUSPECT__</div><div class="l">Suspect labels</div></div>
  <div class="stat accent"><div class="n">__PREC__%</div><div class="l">Precision</div></div>
  <div class="stat accent"><div class="n">__REC__%</div><div class="l">Recall</div></div>
</div>

<div class="controls">
  <input id="search" type="search" placeholder="Search LB#, date, or note text&hellip;" />
  <div class="chipset" id="catchips">
    <button class="chip all" data-cat="ALL" aria-pressed="true">All</button>
    <button class="chip tp" data-cat="TP" aria-pressed="false">TP __TP__</button>
    <button class="chip fn" data-cat="FN" aria-pressed="false">FN __FN__</button>
    <button class="chip fp" data-cat="FP" aria-pressed="false">FP __FP__</button>
    <button class="chip tn" data-cat="TN" aria-pressed="false">TN __TN__</button>
  </div>
  <label class="toggle" id="suspectToggleLabel">
    <input type="checkbox" id="suspectToggle" /> Suspect only (__SUSPECT__)
  </label>
  <span id="count"></span>
</div>

<div class="tablewrap">
<table>
  <thead>
    <tr>
      <th data-key="date">Date</th>
      <th data-key="lb_a">LB A</th>
      <th data-key="lb_b">LB B</th>
      <th data-key="truth">Truth</th>
      <th data-key="verdict_category">Verdict</th>
      <th data-key="corr">Corr</th>
      <th data-key="fp_score">FP score</th>
      <th>Relation note (LB catalog text)</th>
    </tr>
  </thead>
  <tbody id="rows"></tbody>
</table>
</div>

<footer>Generated from <code>observations.db</code> via <code>regression.py score --cached</code>
verdict logic (shipped config: staircase 0.40, triplet/addon rules disabled) &mdash;
confusion matches the reported 41.6% recall / 98.6% precision exactly.</footer>
</div>

<script type="application/json" id="data">__DATA__</script>
<script>
const rows = JSON.parse(document.getElementById('data').textContent);
const tbody = document.getElementById('rows');
const search = document.getElementById('search');
const countEl = document.getElementById('count');
const suspectToggle = document.getElementById('suspectToggle');
const suspectLabel = document.getElementById('suspectToggleLabel');
const chips = [...document.querySelectorAll('#catchips .chip')];
let activeCat = 'ALL';
let sortKey = 'date';
let sortDir = 1;

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtNum(v) {
  return (v === null || v === undefined) ? '&ndash;' : Number(v).toFixed(3);
}

function matches(r, q) {
  if (!q) return true;
  q = q.toLowerCase();
  return String(r.lb_a).includes(q) || String(r.lb_b).includes(q) ||
         r.date.includes(q) || (r.lb_relation_text || '').toLowerCase().includes(q);
}

function render() {
  const q = search.value.trim();
  let filtered = rows.filter(r =>
    (activeCat === 'ALL' || r.verdict_category === activeCat) &&
    (!suspectToggle.checked || r.label_suspect) &&
    matches(r, q)
  );
  filtered.sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (av === null) av = -Infinity; if (bv === null) bv = -Infinity;
    if (typeof av === 'string') return av.localeCompare(bv) * sortDir;
    return (av - bv) * sortDir;
  });
  countEl.textContent = filtered.length.toLocaleString() + ' of ' + rows.length.toLocaleString() + ' pairs';
  const MAX_RENDER = 4000;
  tbody.innerHTML = filtered.slice(0, MAX_RENDER).map(r => {
    const cls = ['cat-' + r.verdict_category];
    if (r.label_suspect) cls.push('suspect');
    const note = r.lb_relation_text ? esc(r.lb_relation_text) : '';
    return `<tr class="${cls.join(' ')}">
      <td>${esc(r.date)}</td>
      <td class="lb">LB-${r.lb_a}</td>
      <td class="lb">LB-${r.lb_b}</td>
      <td class="${r.truth === 'same' ? 'truth-same' : 'truth-diff'}">${r.truth}${r.label_suspect ? ' <span class="susp-mark" title="Independent evidence contradicts this label">&#9679;</span>' : ''}</td>
      <td><span class="pill ${r.verdict_category}">${r.verdict_category}</span></td>
      <td>${fmtNum(r.corr)}</td>
      <td>${fmtNum(r.fp_score)}</td>
      <td class="note" title="${note}">${note.length > 160 ? note.slice(0, 160) + '&hellip;' : note}</td>
    </tr>`;
  }).join('');
}

search.addEventListener('input', render);
suspectToggle.addEventListener('change', () => {
  suspectLabel.classList.toggle('active', suspectToggle.checked);
  render();
});
chips.forEach(c => c.addEventListener('click', () => {
  chips.forEach(x => x.setAttribute('aria-pressed', 'false'));
  c.setAttribute('aria-pressed', 'true');
  activeCat = c.dataset.cat;
  render();
}));
document.querySelectorAll('thead th[data-key]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = 1; }
    document.querySelectorAll('thead th').forEach(x => x.classList.remove('sorted'));
    th.classList.add('sorted');
    render();
  });
});
render();
</script>
</body>
</html>
"""

html = (html
    .replace("__TOTAL__", str(len(rows)))
    .replace("__ULB__", str(unique_lb))
    .replace("__TP__", str(cats["TP"]))
    .replace("__FN__", str(cats["FN"]))
    .replace("__FP__", str(cats["FP"]))
    .replace("__TN__", str(cats["TN"]))
    .replace("__SUSPECT__", str(suspect_n))
    .replace("__PREC__", f"{precision:.1f}")
    .replace("__REC__", f"{recall:.1f}")
    .replace("__DATA__", data_json))

out = HERE / "calibration_audit.html"
out.write_text(html)
print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
