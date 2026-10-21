"""My Collection, personal metadata, wishlist, duplicates, collection data management, folder integrity events (TODO-369)."""

import logging
import os
import re
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend.paths import detail_url

_log = logging.getLogger(__name__)

bp = Blueprint("collection", __name__)


# ── Collection HTML export column picker (TODO-083) ─────────────────────────
# Every key here is always present in each exported entry dict; ?cols= just
# controls which ones the template renders as <th>/<td> and in what order.
_EXPORT_COLUMN_DEFS: dict[str, str] = {
    "lb":           "LB #",
    "status":       "Status",
    "date":         "Date",
    "location":     "Location",
    "folder":       "Folder",
    "notes":        "Notes",
    "disk_path":    "Disk Path",
    "confirmed_at": "Added",
    "source_type":  "Source",
    "lb_category":  "Category",
    "rating":       "Rating",
}
_EXPORT_DEFAULT_COLS = ["lb", "status", "date", "location", "folder", "notes"]

# Column set for the "Not in collection" HTML export — these entries were
# never added to my_collection, so no disk_path/folder/confirmed_at exist.
_EXPORT_MISSING_COLUMN_DEFS: dict[str, str] = {
    "lb":          "LB #",
    "status":      "Status",
    "date":        "Date",
    "location":    "Location",
    "rating":      "Rating",
    "description": "Description",
}
_EXPORT_MISSING_DEFAULT_COLS = ["lb", "status", "date", "location", "rating", "description"]


# ── Collection HTML export template ─────────────────────────────────────────
# Placeholders replaced at request time:
#   __DATA_JSON__     → JSON array of entry dicts (superset of all export columns)
#   __COLS_JSON__     → JSON array of {key, label} dicts — display order/subset
#   __GENERATED_AT__  → UTC timestamp string (no single-quotes, safe in JS string literal)
_COLLECTION_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LosslessBob — My Collection</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#eceff7;--surface:#fff;--s2:#f6f7fb;--bd:#dde3ef;
  --tx:#18202e;--tx2:#6a7390;
  --ac:#4878f5;--acd:#2e5cdf;--acg:rgba(72,120,245,.12);
  --pub-bg:#d1fae5;--pub:#065f46;
  --priv-bg:#dbeafe;--priv:#1e40af;
  --miss-bg:#fee2e2;--miss:#991b1b;
  --unk-bg:#f1f5f9;--unk:#475569;
  --sh1:0 1px 3px rgba(0,0,0,.07),0 2px 8px rgba(0,0,0,.05);
  --sh2:0 4px 12px rgba(0,0,0,.08),0 12px 32px rgba(0,0,0,.06);
  --r:12px
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0b0d16;--surface:#12151f;--s2:#181c28;--bd:#20253a;
  --tx:#d6ddf0;--tx2:#7a86a4;
  --ac:#6490ff;--acd:#4d78f0;--acg:rgba(100,144,255,.14);
  --pub-bg:#052e16;--pub:#4ade80;
  --priv-bg:#172554;--priv:#93c5fd;
  --miss-bg:#450a0a;--miss:#f87171;
  --unk-bg:#1a1f32;--unk:#94a3b8;
  --sh1:0 1px 3px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.2);
  --sh2:0 4px 12px rgba(0,0,0,.4),0 12px 32px rgba(0,0,0,.3)
}}
html,body{height:100%;overflow:hidden}
body{font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:var(--bg);color:var(--tx);font-size:14px;line-height:1.5;
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column}

/* header */
.hdr{flex-shrink:0;background:var(--surface);
  border-bottom:1px solid var(--bd);box-shadow:var(--sh1);padding:14px 20px 10px}
.hdr-top{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.logo{font-size:18px;font-weight:700;letter-spacing:-.4px}
.logo em{font-style:normal;color:var(--ac)}
.gen{font-size:12px;color:var(--tx2);margin-left:auto}

/* stats pills */
.stats{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:99px;font-size:12px;font-weight:500;
  background:var(--s2);border:1px solid var(--bd)}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}

/* controls */
.ctrl{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.sw{position:relative;flex:1;min-width:160px;max-width:320px}
.si{position:absolute;left:9px;top:50%;transform:translateY(-50%);
  color:var(--tx2);pointer-events:none;display:flex}
input[type=search],select,button{font:13px/1.4 inherit}
input[type=search]{width:100%;padding:6px 10px 6px 30px;border:1px solid var(--bd);
  border-radius:8px;background:var(--s2);color:var(--tx);outline:none;
  transition:border-color .15s,box-shadow .15s}
input[type=search]::-webkit-search-cancel-button{-webkit-appearance:none}
input[type=search]:focus{border-color:var(--ac);box-shadow:0 0 0 3px var(--acg)}
select{padding:6px 26px 6px 10px;border:1px solid var(--bd);border-radius:8px;
  background-color:var(--s2);color:var(--tx);outline:none;
  -webkit-appearance:none;appearance:none;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='11' height='11' viewBox='0 0 24 24'%3E%3Cpath fill='%236a7390' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
  transition:border-color .15s}
select:focus{border-color:var(--ac)}
.btn{padding:6px 12px;border-radius:8px;border:1px solid var(--bd);background:var(--s2);
  color:var(--tx);cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;
  gap:5px;font-weight:500;
  transition:background .12s,border-color .12s,color .12s,transform .08s}
.btn:hover{background:var(--acg);border-color:var(--ac);color:var(--ac)}
.btn:active{transform:scale(.96)}
.btn-p{background:var(--ac);border-color:var(--ac);color:#fff}
.btn-p:hover{background:var(--acd);border-color:var(--acd);color:#fff}
.btn:disabled{opacity:.35;cursor:default;pointer-events:none}
.cr{margin-left:auto;display:flex;align-items:center;gap:8px}
.cnt{font-size:12px;color:var(--tx2);white-space:nowrap}

/* table card */
.card{margin:8px 16px 0;border-radius:var(--r);border:1px solid var(--bd);
  box-shadow:var(--sh2);background:var(--surface);overflow:auto;flex:1;min-height:0}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{position:sticky;top:0;z-index:10;background:var(--s2);
  padding:9px 14px;text-align:left;font-size:11px;font-weight:700;
  text-transform:uppercase;letter-spacing:.55px;color:var(--tx2);
  border-bottom:1px solid var(--bd);cursor:pointer;user-select:none;
  white-space:nowrap;transition:color .1s}
thead th:hover{color:var(--tx)}
.sa{display:inline-block;margin-left:3px;font-size:9px;opacity:.3}
th.asc .sa,th.desc .sa{opacity:1;color:var(--ac)}
th.asc  .sa::after{content:'▲'}
th.desc .sa::after{content:'▼'}
th:not(.asc):not(.desc) .sa::after{content:'⇅'}
tbody tr{border-bottom:1px solid var(--bd);transition:background .08s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:var(--acg)}
tbody td{padding:7px 14px;vertical-align:middle}
.clb a{color:var(--ac);font-weight:600;text-decoration:none;font-variant-numeric:tabular-nums}
.clb a:hover{text-decoration:underline}
.cdt{white-space:nowrap;color:var(--tx2);font-variant-numeric:tabular-nums}
.cfl{font-size:12px;color:var(--tx2);max-width:280px;word-break:break-word}
.cno{font-size:12px;color:var(--tx2);font-style:italic;max-width:200px}

/* badges */
.b{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;
   font-weight:600;letter-spacing:.2px;text-transform:capitalize}
.bp{background:var(--pub-bg);color:var(--pub)}
.br{background:var(--priv-bg);color:var(--priv)}
.bm{background:var(--miss-bg);color:var(--miss)}
.bu{background:var(--unk-bg);color:var(--unk)}

/* highlight */
mark{background:#fde68a;color:#78350f;border-radius:2px;padding:0 1px;font-style:normal}
@media(prefers-color-scheme:dark){mark{background:#5c3706;color:#fcd34d}}

/* empty state */
.empty{padding:80px 20px;text-align:center;color:var(--tx2)}
.eico{font-size:36px;margin-bottom:10px;opacity:.5}

/* pagination */
.pg{flex-shrink:0;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:10px 16px}
.pg-lbl{font-size:13px;color:var(--tx2)}
.pg-sz{padding:5px 22px 5px 8px;border:1px solid var(--bd);border-radius:8px;
  background-color:var(--s2);color:var(--tx);outline:none;
  -webkit-appearance:none;appearance:none;font:12px/1.4 inherit;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='11' height='11' viewBox='0 0 24 24'%3E%3Cpath fill='%236a7390' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 6px center}
.pg-sz:focus{border-color:var(--ac)}
.pg .btn{padding:5px 10px;font-size:13px}
.ml{margin-left:auto}

/* footer */
.ftr{flex-shrink:0;margin-top:0;padding:14px 20px;text-align:center;font-size:12px;
  color:var(--tx2);border-top:1px solid var(--bd);background:var(--surface)}
.ftr a{color:var(--ac);text-decoration:none}

/* toast */
#toast{position:fixed;bottom:20px;right:20px;background:var(--surface);
  border:1px solid var(--bd);border-left:3px solid var(--ac);border-radius:10px;
  padding:9px 16px;font-size:13px;box-shadow:var(--sh2);z-index:9999;
  opacity:0;transform:translateY(10px);
  transition:opacity .2s,transform .2s;pointer-events:none}
#toast.on{opacity:1;transform:translateY(0)}

@media print{
  html,body{height:auto;overflow:visible;display:block}
  .hdr{position:static}
  .ctrl,.pg .btn{display:none!important}
  .card{flex:none;overflow:visible;height:auto;box-shadow:none;border:1px solid #ccc}
  body{background:white;color:black}
}
</style>
</head>
<body>
<header class="hdr" id="hdr">
  <div class="hdr-top">
    <div class="logo">LosslessBob <em>Collection</em></div>
    <span class="gen" id="genTs"></span>
  </div>
  <div class="stats" id="sbar"></div>
  <div class="ctrl">
    <div class="sw">
      <span class="si">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
      </span>
      <input type="search" id="qIn" placeholder="Search LB#, date, location, folder…" autocomplete="off">
    </div>
    <select id="fSt"><option value="">All statuses</option>
      <option value="public">\U0001f7e2 Public</option>
      <option value="private">\U0001f535 Private</option>
      <option value="missing">\U0001f534 Missing</option>
      <option value="unknown">⚪ Unknown</option>
    </select>
    <select id="fDec"><option value="">All decades</option></select>
    <select id="fYr"><option value="">All years</option></select>
    <button class="btn" onclick="clr()">&#x2715; Clear</button>
    <div class="cr">
      <button class="btn" onclick="dlCSV()" title="Download filtered rows as CSV">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>CSV
      </button>
      <button class="btn btn-p" onclick="cpLBs()" title="Copy visible LB numbers to clipboard">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>Copy LB#s
      </button>
      <span class="cnt" id="cntLbl"></span>
    </div>
  </div>
</header>

<div class="card">
  <table>
    <thead><tr id="thRow"></tr></thead>
    <tbody id="tb"></tbody>
  </table>
  <div class="empty" id="emp" style="display:none">
    <div class="eico">\U0001f50d</div>
    <p>No recordings match your filters.</p>
  </div>
</div>

<div class="pg" id="pgBar">
  <button class="btn" id="p1"  onclick="go(1)"         title="First">&laquo;</button>
  <button class="btn" id="pp"  onclick="go(pg-1)"       title="Previous">&lsaquo;</button>
  <span class="pg-lbl" id="pLbl"></span>
  <button class="btn" id="pn"  onclick="go(pg+1)"       title="Next">&rsaquo;</button>
  <button class="btn" id="pl"  onclick="go(totPg())"    title="Last">&raquo;</button>
  <span class="ml">
    <select class="pg-sz" id="pSz" onchange="onPgSz()">
      <option value="50">50 / page</option>
      <option value="100" selected>100 / page</option>
      <option value="200">200 / page</option>
      <option value="500">500 / page</option>
    </select>
  </span>
</div>

<footer class="ftr">
  Generated <span id="ftrTs"></span> &middot;
  <a href="http://www.losslessbob.wonderingwhattochoose.com" target="_blank" rel="noopener">losslessbob.wonderingwhattochoose.com</a>
  &middot; Press <kbd>/</kbd> to search &middot; <kbd>←</kbd><kbd>→</kbd> to page
</footer>
<div id="toast"></div>

<script>
'use strict';
const DATA=__DATA_JSON__;
const COLS=__COLS_JSON__;
const GEN='__GENERATED_AT__';

const SM={public:{l:'Public',c:'#4ade80',r:0},private:{l:'Private',c:'#60a5fa',r:1},
          missing:{l:'Missing',c:'#f87171',r:2},unknown:{l:'Unknown',c:'#94a3b8',r:3}};
const BC={public:'bp',private:'br',missing:'bm'};
const CELL={
  lb:      (r,q)=>`<td class="clb"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.lb_str)}</a></td>`,
  status:  (r,q)=>`<td><span class="b ${BC[r.status]??'bu'}">${esc(r.status)}</span></td>`,
  date:    (r,q)=>`<td class="cdt">${hl(r.date,q)}</td>`,
  folder:  (r,q)=>`<td class="cfl" title="${esc(r.folder)}">${hl(r.folder,q)}</td>`,
  notes:   (r,q)=>`<td class="cno">${hl(r.notes,q)}</td>`,
  disk_path: (r,q)=>`<td class="cfl" title="${esc(r.disk_path)}">${hl(r.disk_path,q)}</td>`,
  confirmed_at: (r,q)=>`<td class="cdt">${hl(r.confirmed_at,q)}</td>`,
};
function cellFor(r,key,q){return (CELL[key]??((r,q)=>`<td>${hl(r[key],q)}</td>`))(r,q);}
let sc='lb',sd=1,qr='',fSt='',fDec='',fYr='',pg=1,pz=100,fil=[];

(function boot(){
  document.getElementById('genTs').textContent=GEN;
  document.getElementById('ftrTs').textContent=GEN;
  mkHead();mkDrops();mkStats();bindEvt();srt('lb');
})();

function mkHead(){
  document.getElementById('thRow').innerHTML=COLS.map(c=>
    `<th data-col="${c.key}" onclick="srt('${c.key}')">${esc(c.label)} <span class="sa"></span></th>`
  ).join('');
}

function mkDrops(){
  const yrs=[...new Set(DATA.map(r=>r.year).filter(Boolean))].sort().reverse();
  const decs=[...new Set(yrs.map(y=>String(Math.floor(+y/10)*10)))].sort().reverse();
  const yEl=document.getElementById('fYr');
  yrs.forEach(y=>{yEl.add(new Option(y,y))});
  const dEl=document.getElementById('fDec');
  decs.forEach(d=>{dEl.add(new Option(d+'s',d))});
}

function mkStats(){
  const cnt={public:0,private:0,missing:0,unknown:0};
  DATA.forEach(r=>{const k=r.status in cnt?r.status:'unknown';cnt[k]++;});
  const tot=DATA.length;
  const bits=[`<span class="pill"><strong>${tot.toLocaleString()}</strong>&thinsp;recordings</span>`];
  Object.entries(SM).filter(([k])=>cnt[k]>0).forEach(([k,m])=>{
    bits.push(`<span class="pill"><span class="dot" style="background:${m.c}"></span>${cnt[k].toLocaleString()}&thinsp;${m.l}</span>`);
  });
  document.getElementById('sbar').innerHTML=bits.join('');
}

function bindEvt(){
  let tmr;
  document.getElementById('qIn').addEventListener('input',e=>{
    clearTimeout(tmr);tmr=setTimeout(()=>{qr=e.target.value;pg=1;draw();},150);
  });
  ['fSt','fDec','fYr'].forEach(id=>{
    document.getElementById(id).addEventListener('change',e=>{
      if(id==='fSt')fSt=e.target.value;
      else if(id==='fDec')fDec=e.target.value;
      else fYr=e.target.value;
      pg=1;draw();
    });
  });
  document.addEventListener('keydown',e=>{
    const inp=document.getElementById('qIn');
    if(document.activeElement!==inp&&(e.key==='/'||(e.ctrlKey&&e.key==='k'))){
      e.preventDefault();inp.focus();inp.select();
    }
    if(document.activeElement===inp&&e.key==='Escape'){
      inp.value='';qr='';pg=1;draw();inp.blur();
    }
    if(!e.ctrlKey&&!e.altKey&&!e.metaKey&&document.activeElement!==inp){
      if(e.key==='ArrowRight'){e.preventDefault();go(pg+1);}
      if(e.key==='ArrowLeft'){e.preventDefault();go(pg-1);}
    }
  });
}

function apFil(){
  const q=qr.trim().toLowerCase();
  return DATA.filter(r=>{
    if(fSt&&r.status!==fSt)return false;
    if(fYr&&r.year!==fYr)return false;
    if(fDec&&String(Math.floor(+r.year/10)*10)!==fDec)return false;
    if(q){
      const h=COLS.map(c=>c.key==='lb'?r.lb_str:r[c.key]).join(' ').toLowerCase();
      if(!h.includes(q))return false;
    }
    return true;
  });
}

function apSort(rows){
  return rows.slice().sort((a,b)=>{
    if(sc==='lb')return(a.lb-b.lb)*sd;
    if(sc==='status'){const ra=SM[a.status]?.r??9,rb=SM[b.status]?.r??9;return(ra-rb)*sd;}
    const av=(a[sc]||'').toLowerCase(),bv=(b[sc]||'').toLowerCase();
    return av<bv?-sd:av>bv?sd:0;
  });
}

function srt(col){
  if(sc===col)sd*=-1;else{sc=col;sd=1;}
  document.querySelectorAll('thead th').forEach(th=>{
    th.classList.remove('asc','desc');
    if(th.dataset.col===col)th.classList.add(sd===1?'asc':'desc');
  });
  pg=1;draw();
}

function esc(s){
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function hl(txt,q){
  if(!q)return esc(txt);
  const s=esc(txt);
  return s.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')})`, 'gi'),'<mark>$1</mark>');
}

function totPg(){return Math.max(1,Math.ceil(fil.length/pz));}

function draw(){
  fil=apSort(apFil());
  const tb=document.getElementById('tb');
  const emp=document.getElementById('emp');
  if(!fil.length){tb.innerHTML='';emp.style.display='';document.getElementById('cntLbl').textContent='0 results';updPg();return;}
  emp.style.display='none';
  const q=qr.trim().toLowerCase();
  const st=(pg-1)*pz;
  tb.innerHTML=fil.slice(st,st+pz).map(r=>
    `<tr>${COLS.map(c=>cellFor(r,c.key,q)).join('')}</tr>`
  ).join('');
  const n=fil.length,t=DATA.length;
  document.getElementById('cntLbl').textContent=n===t?`${n.toLocaleString()} recordings`:`${n.toLocaleString()} of ${t.toLocaleString()}`;
  updPg();
}

function updPg(){
  const tp=totPg();
  document.getElementById('pLbl').textContent=`Page ${pg} of ${tp}`;
  document.getElementById('p1').disabled=pg<=1;
  document.getElementById('pp').disabled=pg<=1;
  document.getElementById('pn').disabled=pg>=tp;
  document.getElementById('pl').disabled=pg>=tp;
  document.getElementById('pgBar').style.display=fil.length<=pz?'none':'';
}

function go(n){
  const tp=totPg();pg=Math.max(1,Math.min(tp,n));
  document.getElementById('tb').innerHTML='';
  draw();document.querySelector('.card').scrollTo({top:0,behavior:'smooth'});
}

function onPgSz(){pz=+document.getElementById('pSz').value;pg=1;draw();}

function clr(){
  document.getElementById('qIn').value='';
  document.getElementById('fSt').value='';
  document.getElementById('fDec').value='';
  document.getElementById('fYr').value='';
  qr='';fSt='';fDec='';fYr='';pg=1;draw();
}

function dlCSV(){
  const rows=[COLS.map(c=>c.label),
    ...fil.map(r=>COLS.map(c=>c.key==='lb'?r.lb_str:r[c.key]))];
  const csv=rows.map(r=>r.map(c=>`"${String(c??'').replace(/"/g,'""')}"`).join(',')).join('\\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,\\ufeff'+encodeURIComponent(csv);
  a.download='collection.csv';a.click();
  toast(`${fil.length.toLocaleString()} rows exported`);
}

function cpLBs(){
  navigator.clipboard.writeText(fil.map(r=>r.lb_str).join('\\n')).then(
    ()=>toast(`${fil.length.toLocaleString()} LB numbers copied`),
    ()=>toast('Clipboard access denied')
  );
}

let _tt;
function toast(msg){
  const el=document.getElementById('toast');
  el.textContent=msg;el.classList.add('on');
  clearTimeout(_tt);_tt=setTimeout(()=>el.classList.remove('on'),2800);
}
</script>
</body>
</html>"""


# ── My Collection ────────────────────────────────────────────────────────

@bp.route("/api/collection", methods=["GET"])
def collection_list() -> Response:
    """Return all entries in the user's collection.

    Returns:
        JSON list of my_collection row dicts.
    """
    # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
    # performs in-memory sorting on the full result set.
    try:
        sort_col = request.args.get("sort_col", "")
        sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
        _COLL_SORT_COLS = {
            "lb_number":   lambda r: r.get("lb_number") or 0,
            "date_str":    lambda r: (r.get("date_str") or "").lower(),
            "location":    lambda r: (r.get("location") or "").lower(),
            "folder_name": lambda r: (r.get("folder_name") or "").lower(),
            "lb_status":   lambda r: {"public": 0, "private": 1,
                                      "missing": 2}.get(
                                     r.get("lb_status") or "", 99),
        }
        results = database.get_collection()
        if sort_col and sort_col in _COLL_SORT_COLS:
            results.sort(key=_COLL_SORT_COLS[sort_col],
                         reverse=(sort_dir == "DESC"))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection", methods=["POST"])
def collection_add() -> Response:
    """Add an LB entry to the user's collection.

    Body: {lb_number, folder_name, disk_path, notes?, xref?}
    ``xref`` (default 0) is the copy-level fileset id this folder matches
    (0 = canonical fileset — FABLE_XREF_INCORPORATION.md D3).
    Returns:
        JSON {ok, added} or 400 if required fields are missing.
    """
    try:
        data = request.get_json() or {}
        lb = data.get("lb_number")
        folder_name = data.get("folder_name", "")
        disk_path = data.get("disk_path", "")
        notes = data.get("notes")
        xref = data.get("xref") or 0
        if not lb or not folder_name or not disk_path:
            return jsonify({"error": "lb_number, folder_name, disk_path required"}), 400
        added = database.add_to_collection(
            int(lb), folder_name, disk_path, notes, xref=int(xref),
        )
        return jsonify({"ok": True, "added": added > 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/<int:lb>", methods=["PATCH"])
def collection_update(lb: int) -> Response:
    """Update fields on an existing collection entry.

    Args:
        lb: The LB number to update.

    Body: {field: value, ...}
    Returns:
        JSON {ok: true}.
    """
    try:
        data = request.get_json() or {}
        database.update_collection(lb, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/<int:lb>", methods=["DELETE"])
def collection_delete(lb: int) -> Response:
    """Remove an LB entry from the user's collection.

    Args:
        lb: The LB number to remove.

    Returns:
        JSON {ok: true}.
    """
    try:
        database.delete_from_collection(lb)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/reassign", methods=["POST"])
def collection_reassign() -> Response:
    """Move a filed folder from one LB entry to another (TODO-259).

    Repoints the my_collection row and its personal metadata; the folder on
    disk is untouched. Validation (target exists, not already owned) happens
    in the DB layer and surfaces as a 400.

    Body: {old_lb: int, new_lb: int}
    Returns:
        JSON {ok: true}, or {error} with 400 on a validation failure.
    """
    data = request.get_json() or {}
    old_lb = data.get("old_lb")
    new_lb = data.get("new_lb")
    if old_lb is None or new_lb is None:
        return jsonify({"error": "old_lb and new_lb required"}), 400
    try:
        database.reassign_collection(int(old_lb), int(new_lb))
        return jsonify({"ok": True})
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/missing", methods=["GET"])
def collection_missing() -> Response:
    """Return collection entries whose disk_path no longer exists on disk.

    Returns:
        JSON list of collection row dicts with missing paths.
    """
    # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
    # performs in-memory sorting on the full result set.
    try:
        sort_col = request.args.get("sort_col", "")
        sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
        _MISS_SORT_COLS = {
            "lb_number": lambda r: r.get("lb_number") or 0,
            "date_str":  lambda r: (r.get("date_str") or "").lower(),
            "location":  lambda r: (r.get("location") or "").lower(),
            "lb_status": lambda r: {"public": 0, "private": 1,
                                    "missing": 2}.get(
                                   r.get("lb_status") or "", 99),
        }
        results = database.get_missing_from_collection()
        if sort_col and sort_col in _MISS_SORT_COLS:
            results.sort(key=_MISS_SORT_COLS[sort_col],
                         reverse=(sort_dir == "DESC"))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/lb_numbers", methods=["GET"])
def collection_lb_numbers() -> Response:
    """Return all LB numbers currently in the user's collection.

    Returns:
        JSON list of integer LB numbers.
    """
    try:
        return jsonify(database.get_owned_lb_numbers())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FEAT-03: Personal Metadata ───────────────────────────────────────────

@bp.route("/api/collection/<int:lb>/meta", methods=["GET"])
def get_coll_meta(lb: int) -> Response:
    """Return personal metadata for a collection entry.

    Args:
        lb: The LB number to retrieve metadata for.

    Returns:
        JSON dict of personal metadata key/value pairs.
    """
    try:
        return jsonify(database.get_collection_meta(lb))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/<int:lb>/meta", methods=["POST"])
def set_coll_meta(lb: int) -> Response:
    """Set personal metadata for a collection entry.

    Args:
        lb: The LB number to update metadata for.

    Body: {key: value, ...}
    Returns:
        JSON {ok: true}.
    """
    try:
        database.set_collection_meta(lb, request.get_json() or {})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/<int:lb>/listen", methods=["POST"])
def log_listen(lb: int) -> Response:
    """Increment the listen count for a collection entry.

    Args:
        lb: The LB number to log a listen for.

    Returns:
        JSON {ok: true}.
    """
    try:
        database.increment_listen_count(lb)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Audio info cache (in-memory, keyed by disk_path + mtime fingerprint) ──
_audioinfo_cache: dict = {}


@bp.route("/api/collection/<int:lb>/audioinfo", methods=["GET"])
def collection_audioinfo(lb: int) -> Response:
    """Return audio format / bit-depth / sample-rate for a collection entry.

    Args:
        lb: LB number of the collection entry.

    Returns:
        JSON {format, bit_depth, sample_rate, mixed, files_probed, offline?}.
    """
    import json as _json
    import subprocess

    import soundfile as sf

    _empty = {"format": None, "bit_depth": None, "sample_rate": None,
              "mixed": False, "files_probed": 0}
    try:
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb,)
            ).fetchone()
        if not row or not row["disk_path"]:
            return jsonify(_empty)
        disk_path = row["disk_path"]
        if not os.path.isdir(disk_path):
            return jsonify({**_empty, "offline": True})

        AUDIO_EXTS = {'.flac', '.wav', '.aiff', '.aif', '.shn', '.ape', '.ogg', '.mp3'}
        audio_files = [
            os.path.join(root, f)
            for root, _, files in os.walk(disk_path)
            for f in files
            if os.path.splitext(f.lower())[1] in AUDIO_EXTS
        ]
        if not audio_files:
            return jsonify(_empty)

        try:
            mtime_sum = sum(int(os.path.getmtime(f) * 1000) for f in audio_files[:20])
        except Exception:
            mtime_sum = 0
        cache_key = (disk_path, mtime_sum)
        if cache_key in _audioinfo_cache:
            return jsonify(_audioinfo_cache[cache_key])

        sample = audio_files[:5]
        results = []
        for fpath in sample:
            ext = os.path.splitext(fpath.lower())[1]
            fmt = bit_depth = rate = None
            try:
                info = sf.info(fpath)
                fmt = info.format.upper()
                rate = info.samplerate
                st = info.subtype.upper()
                if 'PCM_16' in st:
                    bit_depth = 16
                elif 'PCM_24' in st:
                    bit_depth = 24
                elif 'PCM_32' in st:
                    bit_depth = 32
                elif 'FLOAT' in st or 'DOUBLE' in st:
                    bit_depth = 32
                elif '8' in st:
                    bit_depth = 8
            except Exception:
                try:
                    out = subprocess.run(
                        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                         '-show_streams', '-select_streams', 'a:0', fpath],
                        capture_output=True, text=True, timeout=10,
                    )
                    if out.returncode == 0:
                        streams = _json.loads(out.stdout).get('streams', [])
                        if streams:
                            s = streams[0]
                            fmt = ext.lstrip('.').upper()
                            rate = int(s.get('sample_rate', 0)) or None
                            bits = s.get('bits_per_raw_sample') or s.get('bits_per_sample')
                            bit_depth = int(bits) if bits else None
                except Exception:
                    pass
            if fmt:
                results.append({'format': fmt, 'bit_depth': bit_depth, 'sample_rate': rate})

        if not results:
            return jsonify({**_empty, "files_probed": len(sample)})

        fmts   = {r['format']      for r in results if r['format']}
        depths = {r['bit_depth']   for r in results if r['bit_depth']}
        rates  = {r['sample_rate'] for r in results if r['sample_rate']}
        mixed  = len(fmts) > 1 or len(depths) > 1 or len(rates) > 1
        result = {
            "format":       sorted(fmts)[0]   if fmts   else None,
            "bit_depth":    sorted(depths)[0] if depths else None,
            "sample_rate":  round(sorted(rates)[0] / 1000, 1) if rates else None,
            "mixed":        mixed,
            "files_probed": len(sample),
        }
        _audioinfo_cache[cache_key] = result
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FEAT-04: Wishlist ────────────────────────────────────────────────────

@bp.route("/api/wishlist", methods=["GET"])
def wishlist_list() -> Response:
    """Return all entries in the user's wishlist.

    Returns:
        JSON list of wishlist row dicts.
    """
    try:
        return jsonify(database.get_wishlist())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/wishlist", methods=["POST"])
def wishlist_add() -> Response:
    """Add an LB entry to the user's wishlist.

    Body: {lb_number, priority?, notes?}
    Returns:
        JSON {ok, added} or 400 if lb_number is missing.
    """
    try:
        data = request.get_json() or {}
        lb = data.get("lb_number")
        if not lb:
            return jsonify({"error": "lb_number required"}), 400
        added = database.add_to_wishlist(int(lb), data.get("priority", 3), data.get("notes"))
        return jsonify({"ok": True, "added": added > 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/wishlist/<int:lb>", methods=["PATCH"])
def wishlist_update(lb: int) -> Response:
    """Update priority and/or notes on a wishlist entry.

    Body: {priority?, notes?}
    Returns:
        JSON {ok: true}.
    """
    try:
        data = request.get_json() or {}
        database.update_wishlist(lb, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/wishlist/<int:lb>", methods=["DELETE"])
def wishlist_remove(lb: int) -> Response:
    """Remove an LB entry from the user's wishlist.

    Args:
        lb: The LB number to remove.

    Returns:
        JSON {ok: true}.
    """
    try:
        database.remove_from_wishlist(lb)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FEAT-05: Duplicate Detector ──────────────────────────────────────────

@bp.route("/api/collection/duplicates", methods=["GET"])
def collection_duplicates() -> Response:
    """Return collection entries that share the same LB number (duplicates).

    Returns:
        JSON list of duplicate collection row dicts.
    """
    try:
        return jsonify(database.get_collection_duplicates())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/prefetch", methods=["GET"])
def collection_prefetch() -> Response:
    """Return all data needed by the Collection screen in a single request.

    Bundles collection, missing, wishlist, duplicates, forum_posts,
    torrents, xref_lb_numbers, and years so the GUI only needs one
    round-trip to warm its React Query cache.

    Returns:
        JSON dict with one key per dataset.
    """
    try:
        torrents = database.get_all_torrents()
        for row in torrents:
            row["source_folder_exists"] = (
                bool(row.get("source_folder"))
                and Path(row["source_folder"]).is_dir()
            )
            row["torrent_file_exists"] = (
                bool(row.get("torrent_path"))
                and Path(row["torrent_path"]).exists()
            )
        # `description` is ~1 KB per row and ~26 MB of this payload, all of
        # it a repeat of /api/search — the GUI joins it from that catalog
        # by lb_number instead.
        collection = database.get_collection()
        for row in collection:
            row.pop("description", None)
        duplicates = database.get_collection_duplicates()
        for group in duplicates:
            for row in (*group.get("owned", []), *group.get("unowned", [])):
                row.pop("description", None)
        return jsonify({
            "collection":     collection,
            "missing":        database.get_missing_from_collection(),
            "wishlist":       database.get_wishlist(),
            "duplicates":     duplicates,
            "forum_posts":    database.get_all_forum_posts(),
            "torrents":       torrents,
            "xref_lb_numbers": database.get_xref_lb_numbers(),
            "years":          database.get_distinct_years(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FEAT-13: Granular Collection Data Management ─────────────────────────

@bp.route("/api/collection/purge", methods=["POST"])
def collection_purge() -> Response:
    """Purge all rows from a named user-data table.

    Body: {scope: collection|wishlist|personal_meta|integrity_events|entry_changes}
    Returns:
        JSON {ok, scope} or 400 for unknown scope.
    """
    try:
        scope = (request.get_json() or {}).get("scope", "collection")
        dispatch = {
            "collection":       database.purge_collection,
            "wishlist":         database.purge_wishlist,
            "personal_meta":    database.purge_collection_meta,
            "integrity_events": database.purge_integrity_events,
            "entry_changes":    database.purge_entry_changes,
        }
        if scope not in dispatch:
            return jsonify({"error": f"Unknown scope: {scope}"}), 400
        dispatch[scope]()
        return jsonify({"ok": True, "scope": scope})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/rename_history/purge", methods=["POST"])
def purge_rename_history() -> Response:
    """Purge all rows from rename_history (lookup history)."""
    try:
        with database._write_lock:
            conn = database.get_connection()
            conn.execute("DELETE FROM rename_history")
            conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/flat_file/purge", methods=["POST"])
def purge_flat_file_history() -> Response:
    """Purge all flat_file_releases and flat_file_changelog rows (import log)."""
    try:
        with database._write_lock:
            conn = database.get_connection()
            conn.execute("DELETE FROM flat_file_changelog")
            conn.execute("DELETE FROM flat_file_releases")
            conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/scraper/purge", methods=["POST"])
def purge_scraper_cache() -> Response:
    """Purge all scrape_sessions and site_inventory rows (scraper cache)."""
    try:
        with database._write_lock:
            conn = database.get_connection()
            conn.execute("DELETE FROM site_inventory")
            conn.execute("DELETE FROM scrape_sessions")
            conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/purge/stats", methods=["GET"])
def purge_stats() -> Response:
    """Return row counts for each purgeable data group, plus recoverable disk bytes."""
    try:
        conn = database.get_connection()

        def count(table: str) -> int:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        lookup = count("rename_history")
        import_log = count("flat_file_releases") + count("flat_file_changelog")
        scraper = count("scrape_sessions") + count("site_inventory")
        collection_rows = (
            count("my_collection") + count("my_wishlist") + count("collection_meta")
            + count("integrity_events") + count("entry_changes")
        )

        # Recoverable disk bytes: scraper HTML cache
        from backend.paths import SITE_DIR
        recoverable = 0
        if SITE_DIR.exists():
            recoverable += sum(f.stat().st_size for f in SITE_DIR.rglob("*") if f.is_file())

        return jsonify({
            "lookup_history":    lookup,
            "import_log":        import_log,
            "scraper_cache":     scraper,
            "all_user_data":     lookup + import_log + scraper + collection_rows,
            "recoverable_bytes": recoverable,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/collection/audit", methods=["GET"])
def collection_audit() -> Response:
    """Cross-check my_collection against the checksums table.

    Returns:
        JSON {total, missing_checksums, entries:[{lb_number, folder_name,
        disk_path, date_str, location, lb_status}]} listing every
        collection entry that has no checksum rows in the DB.
    """
    try:
        return jsonify(database.audit_collection_checksums())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/export/html", methods=["GET"])
def collection_export_html() -> Response:
    """Export My Collection as a modern, interactive single-file HTML report.

    The file embeds all entries as JSON and renders via client-side JS:
    live search with highlight, column sorting, status/decade/year filters,
    100-row pagination (adjustable), CSV download, LB# clipboard copy, dark
    mode, and keyboard shortcuts. Handles 16k+ entries without DOM thrashing.

    Query params:
        cols: comma-separated column keys to display, in order (see
              _EXPORT_COLUMN_DEFS). Unknown keys are dropped; falls back
              to _EXPORT_DEFAULT_COLS if empty/all-unknown. "lb" is
              always included since it anchors the detail-page link.
        lb_numbers: optional comma-separated LB numbers to restrict the
              export to (e.g. the GUI's currently filtered/searched
              rows). Omit for the full collection.

    Returns:
        HTML file attachment (collection.html), fully self-contained.
    """
    try:
        import json as _json
        from datetime import UTC, datetime

        requested = [c.strip() for c in request.args.get("cols", "").split(",") if c.strip()]
        cols = [c for c in requested if c in _EXPORT_COLUMN_DEFS] or list(_EXPORT_DEFAULT_COLS)
        if "lb" not in cols:
            cols = ["lb"] + cols

        rows = database.get_collection()
        lb_numbers_param = request.args.get("lb_numbers", "")
        if lb_numbers_param:
            wanted = {int(x) for x in lb_numbers_param.split(",") if x.strip().isdigit()}
            rows = [r for r in rows if r.get("lb_number") in wanted]
        entries = []
        for r in rows:
            lb = r.get("lb_number", 0) or 0
            date_str = r.get("date_str", "") or ""
            year = date_str[:4] if len(date_str) >= 4 and date_str[:4].isdigit() else ""
            if not year:
                _fm = re.search(r'\b((?:19|20)\d{2})\b', r.get("folder_name", "") or "")
                if _fm:
                    year = _fm.group(1)
            entries.append({
                "lb": lb,
                "lb_str": f"LB-{lb:05d}",
                "url": detail_url(lb),
                "status": r.get("lb_status") or "unknown",
                "date": date_str,
                "year": year,
                "location": r.get("location", "") or "",
                "folder": r.get("folder_name", "") or "",
                "notes": r.get("notes", "") or "",
                "disk_path": r.get("disk_path", "") or "",
                "confirmed_at": (r.get("confirmed_at") or "")[:10],
                "source_type": r.get("source_type", "") or "",
                "lb_category": r.get("lb_category", "") or "",
                "rating": r.get("rating") if r.get("rating") is not None else "",
            })

        data_json = _json.dumps(entries, ensure_ascii=False)
        cols_json = _json.dumps(
            [{"key": c, "label": _EXPORT_COLUMN_DEFS[c]} for c in cols],
            ensure_ascii=False,
        )
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        html = (
            _COLLECTION_HTML_TEMPLATE
            .replace("__DATA_JSON__", data_json)
            .replace("__COLS_JSON__", cols_json)
            .replace("__GENERATED_AT__", generated_at)
        )
        return Response(
            html,
            mimetype="text/html",
            headers={"Content-Disposition": "attachment; filename=collection.html"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/export/html/missing", methods=["GET"])
def collection_export_html_missing() -> Response:
    """Export the "Not in collection" LB list as the same interactive HTML report.

    Reuses _COLLECTION_HTML_TEMPLATE with a column set suited to entries
    never added to my_collection (no disk path / folder / confirmed date).

    Query params:
        lb_numbers: optional comma-separated LB numbers to restrict the
              export to (e.g. the GUI's public/private toggle within the
              "Not in collection" tab). Omit for the full missing list.

    Returns:
        HTML file attachment (missing_lbs.html), fully self-contained.
    """
    try:
        import json as _json
        from datetime import UTC, datetime

        rows = database.get_missing_from_collection()
        lb_numbers_param = request.args.get("lb_numbers", "")
        if lb_numbers_param:
            wanted = {int(x) for x in lb_numbers_param.split(",") if x.strip().isdigit()}
            rows = [r for r in rows if r.get("lb_number") in wanted]

        cols = list(_EXPORT_MISSING_DEFAULT_COLS)
        entries = []
        for r in rows:
            lb = r.get("lb_number", 0) or 0
            date_str = r.get("date_str", "") or ""
            year = date_str[:4] if len(date_str) >= 4 and date_str[:4].isdigit() else ""
            entries.append({
                "lb": lb,
                "lb_str": f"LB-{lb:05d}",
                "url": detail_url(lb),
                "status": r.get("lb_status") or "unknown",
                "date": date_str,
                "year": year,
                "location": r.get("location", "") or "",
                "rating": r.get("rating") if r.get("rating") is not None else "",
                "description": r.get("description", "") or "",
            })

        data_json = _json.dumps(entries, ensure_ascii=False)
        cols_json = _json.dumps(
            [{"key": c, "label": _EXPORT_MISSING_COLUMN_DEFS[c]} for c in cols],
            ensure_ascii=False,
        )
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        html = (
            _COLLECTION_HTML_TEMPLATE
            .replace("__DATA_JSON__", data_json)
            .replace("__COLS_JSON__", cols_json)
            .replace("__GENERATED_AT__", generated_at)
            .replace("LosslessBob <em>Collection</em>", "LosslessBob <em>Not in Collection</em>")
        )
        return Response(
            html,
            mimetype="text/html",
            headers={"Content-Disposition": "attachment; filename=missing_lbs.html"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/collection/export/m3u", methods=["GET"])
def collection_export_m3u() -> Response:
    """Export My Collection (or a subset) as an M3U playlist.

    Iterates each entry's disk_path folder and includes all audio files
    (FLAC, SHN, APE, WAV, MP3) in sorted order.  Entries with no valid
    disk_path are silently skipped.

    Query args:
        lb_numbers: optional comma-separated LB numbers to restrict the
            export to (e.g. a single show's owned recordings in the
            Library performance lens). Omit for the full collection.

    Returns:
        M3U file attachment (collection.m3u, or show.m3u when filtered).
    """
    try:
        rows = database.get_collection()
        lb_numbers_param = request.args.get("lb_numbers", "")
        filtered = bool(lb_numbers_param)
        if filtered:
            wanted = {int(x) for x in lb_numbers_param.split(",") if x.strip().isdigit()}
            rows = [r for r in rows if r.get("lb_number") in wanted]
        audio_exts = {".flac", ".shn", ".ape", ".wav", ".mp3"}
        lines = ["#EXTM3U"]
        for r in rows:
            dp = r.get("disk_path", "")
            if not dp or not Path(dp).is_dir():
                continue
            for f in sorted(Path(dp).iterdir()):
                if f.suffix.lower() in audio_exts:
                    lines.append(
                        f"#EXTINF:-1,{r.get('date_str', '')} - "
                            f"{r.get('location', '')}"
                    )
                    lines.append(str(f))
        filename = "show.m3u" if filtered else "collection.m3u"
        return Response(
            "\n".join(lines),
            mimetype="audio/x-mpegurl",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FEAT-09: Collection Folder Integrity ──────────────────────────────────

@bp.route("/api/integrity/events", methods=["GET"])
def integrity_events_route() -> Response:
    """Return watchdog integrity events.

    Query params:
        unacked (default 1): 1 = unacknowledged only, 0 = all
    Returns:
        JSON list of event rows.
    """
    unacked = request.args.get("unacked", "1") == "1"
    return jsonify(database.get_integrity_events(unacked_only=unacked))


@bp.route("/api/integrity/ack", methods=["POST"])
def integrity_ack() -> Response:
    """Acknowledge integrity events by ID.

    Body: {ids: [int, ...]}
    Returns:
        JSON {ok: true}
    """
    ids = (request.get_json() or {}).get("ids", [])
    database.ack_integrity_events(ids)
    return jsonify({"ok": True})
