"""Review private collection LBs missing canonical-naming metadata, then write the fixes.

Canonical folder names need a date and a location on the ``entries`` row
(backend.folder_naming.build_standard_name); without them lb-nc can't rename the
folder. This tool closes that gap in two steps:

    build  writes a standalone HTML page (data/exports/private_meta_review.html) listing
           every private my_collection LB with a blank date or location, each with
           the olof_events rows for its date as suggestions. Confirm or edit rows in
           the page, then Export — it downloads private_meta_decisions.json.
    apply  reads that JSON and writes the confirmed date/location onto entries.
           Dry-run by default; --apply backs the DB up to data/backups, runs
           quick_check, and skips any row whose values changed since the page was built.

Usage:
    .venv/bin/python3 tools/private_meta_review.py build
    .venv/bin/python3 tools/private_meta_review.py apply ~/Downloads/private_meta_decisions.json
    .venv/bin/python3 tools/private_meta_review.py apply <json> --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.folder_naming import build_standard_name  # noqa: E402
from backend.paths import DATA_DIR, DB_PATH  # noqa: E402
from backend.torrent_maker import _parse_date  # noqa: E402

log = logging.getLogger("private_meta_review")

OUT_HTML = DATA_DIR / "exports" / "private_meta_review.html"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
US_COUNTRIES = {"", "usa", "us", "united states"}
TYPE_ORDER = {"concert": 0, "broadcast": 1, "session": 2, "rehearsal": 3}

ROWS_SQL = """
SELECT e.lb_number, e.date_str, e.location, e.taper_name, e.description,
       e.metadata_source, COALESCE(l.lb_status, e.status) AS lb_status,
       m.folder_name, m.disk_path, COALESCE(m.xref, 0) AS xref
FROM my_collection m
JOIN entries e ON e.lb_number = m.lb_number
LEFT JOIN lb_master l ON l.lb_number = m.lb_number
WHERE COALESCE(l.lb_status, e.status) = 'private'
  AND (TRIM(COALESCE(e.location, '')) = '' OR TRIM(COALESCE(e.date_str, '')) = '')
ORDER BY e.lb_number, m.folder_name
"""


def olof_location(city: str, region: str, country: str) -> str:
    """Format an olof_events place the way entries.location usually reads.

    US rows carry no country in Olof, so they read "City, State"; everything
    else reads "City, Country".

    Args:
        city: olof_events.city.
        region: olof_events.region (state/province).
        country: olof_events.country.

    Returns:
        The location string, or "" when Olof has no city.
    """
    city, region, country = (s.strip() for s in (city or "", region or "", country or ""))
    if not city:
        return ""
    tail = region if country.lower() in US_COUNTRIES else country
    return f"{city}, {tail}" if tail else city


def iso_to_lb_date(iso: str) -> str:
    """Turn YYYY-MM-DD into the entries M/D/YY form (2-digit year, as the scraper stores)."""
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}/{y[2:]}"


def collect(conn: sqlite3.Connection) -> list[dict]:
    """Private collection LBs missing date or location, with Olof suggestions.

    Args:
        conn: Open connection to the app DB (row_factory = sqlite3.Row).

    Returns:
        One dict per LB: current fields, its collection folders and candidate events.
    """
    by_lb: dict[int, dict] = {}
    for r in conn.execute(ROWS_SQL):
        rec = by_lb.get(r["lb_number"])
        if rec is None:
            iso = _parse_date(r["date_str"] or "")
            rec = by_lb[r["lb_number"]] = {
                "lb": r["lb_number"], "date_str": r["date_str"] or "",
                "location": r["location"] or "", "iso": iso,
                "status": r["lb_status"], "taper": r["taper_name"] or "",
                "source": r["metadata_source"] or "",
                "description": (r["description"] or "")[:400],
                "folders": [], "candidates": [],
            }
            if len(iso) == 10 and "x" not in iso:
                rec["candidates"] = candidates(conn, iso)
        rec["folders"].append({"name": r["folder_name"], "path": r["disk_path"],
                               "xref": int(r["xref"] or 0)})
    return list(by_lb.values())


def candidates(conn: sqlite3.Connection, iso: str) -> list[dict]:
    """olof_events rows dated `iso`, concerts first, each with a suggested location."""
    rows = conn.execute(
        "SELECT event_id, event_type, venue, city, region, country FROM olof_events "
        "WHERE date_str = ?", (iso,)).fetchall()
    out = [{"event_id": r["event_id"], "type": r["event_type"] or "",
            "venue": r["venue"] or "", "city": r["city"] or "",
            "region": r["region"] or "", "country": r["country"] or "",
            "suggestion": olof_location(r["city"], r["region"], r["country"])}
           for r in rows]
    out.sort(key=lambda c: TYPE_ORDER.get(c["type"], 9))
    return [c for c in out if c["suggestion"]]


def build(out: Path = OUT_HTML) -> Path:
    """Write the review page.

    Args:
        out: Destination HTML path.

    Returns:
        The written path.
    """
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        records = collect(conn)
    finally:
        conn.close()
    payload = json.dumps({"built": dt.datetime.now().isoformat(timespec="seconds"),
                          "db": str(DB_PATH), "rows": records}, ensure_ascii=False)
    page = PAGE.replace("__DATA__", payload.replace("</", "<\\/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    with_cand = sum(1 for r in records if r["candidates"])
    log.info("%d LB(s) need metadata, %d with an Olof match -> %s",
             len(records), with_cand, out)
    return out


def apply(decisions_path: Path, write: bool) -> int:
    """Write confirmed decisions onto entries.

    Args:
        decisions_path: The JSON the page exported.
        write: False = dry run.

    Returns:
        Process exit code.
    """
    data = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions = data.get("decisions", [])
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if write:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dest = BACKUP_DIR / f"pre_private_meta_{dt.datetime.now():%Y%m%d_%H%M%S}.db"
        with sqlite3.connect(dest) as bak:
            conn.backup(bak)
        ok = sqlite3.connect(dest).execute("PRAGMA quick_check").fetchone()[0]
        if ok != "ok":
            log.error("backup %s failed quick_check: %s — nothing written", dest, ok)
            return 1
        log.info("backup %s (quick_check ok)", dest)
    done = stale = same = 0
    for d in decisions:
        lb = int(d["lb"])
        row = conn.execute("SELECT date_str, location, status FROM entries WHERE lb_number=?",
                           (lb,)).fetchone()
        before = d.get("before", {})
        if row is None:
            log.warning("LB-%05d  skip: no entries row", lb)
            stale += 1
            continue
        if (row["date_str"] or "") != before.get("date_str", "") \
                or (row["location"] or "") != before.get("location", ""):
            log.warning("LB-%05d  skip: changed since the page was built (%r, %r)",
                        lb, row["date_str"], row["location"])
            stale += 1
            continue
        new_date = (d.get("date_str") or "").strip()
        new_loc = (d.get("location") or "").strip()
        if new_date == (row["date_str"] or "") and new_loc == (row["location"] or ""):
            same += 1
            continue
        name = build_standard_name(lb, new_date, new_loc, "private")
        log.info("LB-%05d  %r,%r -> %r,%r  => %s", lb, row["date_str"], row["location"],
                 new_date, new_loc, name)
        if write:
            conn.execute("UPDATE entries SET date_str=?, location=? WHERE lb_number=?",
                         (new_date, new_loc, lb))
        done += 1
    if write:
        conn.commit()
    conn.close()
    log.info("%s %d, unchanged %d, skipped %d%s", "wrote" if write else "would write",
             done, same, stale, "" if write else "  (dry run — add --apply to write)")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the review HTML")
    b.add_argument("--out", type=Path, default=OUT_HTML)
    a = sub.add_parser("apply", help="write the page's exported decisions")
    a.add_argument("decisions", type=Path)
    a.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args(argv)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.cmd == "apply":
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(
            LOG_DIR / f"private_meta_apply_{dt.datetime.now():%Y%m%d_%H%M%S}.log"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers)

    if args.cmd == "build":
        build(args.out)
        return 0
    return apply(args.decisions.expanduser(), args.apply)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Private Metadata Review</title>
<style>
:root{--bg:#0f172a;--panel:#1e293b;--line:#334155;--text:#e2e8f0;--dim:#94a3b8;
 --acc:#7dd3fc;--ok:#86efac;--warn:#fcd34d;--bad:#fca5a5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);
 padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
h1{font-size:16px;margin:0 12px 0 0;color:var(--acc)}
.stat{color:var(--dim)} .stat b{color:var(--text)}
button,select,input{font:inherit;color:var(--text);background:var(--panel);
 border:1px solid var(--line);border-radius:6px;padding:5px 10px}
button{cursor:pointer} button:hover{border-color:var(--acc)}
button.primary{background:#0c4a6e;border-color:var(--acc)}
main{padding:12px 16px;max-width:1100px;margin:0 auto}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
 padding:12px;margin-bottom:12px}
.card.confirmed{border-color:var(--ok)} .card.skipped{opacity:.55}
.top{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline}
.lb{font-weight:700;color:var(--acc);font-size:15px}
.tag{font-size:12px;padding:1px 7px;border-radius:10px;border:1px solid var(--line);color:var(--dim)}
.tag.miss{color:var(--bad);border-color:var(--bad)}
.tag.ok{color:var(--ok);border-color:var(--ok)}
.mono{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-all}
.dim{color:var(--dim)}
.grid{display:grid;grid-template-columns:110px 1fr;gap:4px 10px;margin:8px 0}
.cands label{display:block;padding:4px 6px;border-radius:5px;cursor:pointer}
.cands label:hover{background:#0f172a}
.edit{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.edit input.date{width:110px} .edit input.loc{flex:1;min-width:200px}
.preview{background:#0f172a;border:1px dashed var(--line);border-radius:6px;padding:6px 8px}
.preview .new{color:var(--ok)}
.actions{display:flex;gap:8px;margin-top:8px}
details summary{cursor:pointer;color:var(--dim)}
@media (max-width:600px){.grid{grid-template-columns:1fr}}
</style></head><body>
<header>
 <h1>Private LB metadata review</h1>
 <span class="stat" id="stats"></span>
 <select id="filter">
  <option value="pending">Pending</option><option value="confirmed">Confirmed</option>
  <option value="skipped">Skipped</option><option value="olof">Pending, Olof match</option>
  <option value="all">All</option>
 </select>
 <input id="q" placeholder="filter LB / folder / text" style="min-width:180px">
 <button id="acceptAll" title="Confirm every pending row that has exactly one Olof candidate">
  Confirm single-match pending</button>
 <button class="primary" id="export">Export decisions</button>
 <button id="reset">Reset</button>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
const KEY = "pmr:" + DATA.built;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function isoOf(d) {
  const p = (d || "").split("/"); if (p.length !== 3) return (d || "").trim();
  let [m, dd, y] = p.map(s => s.trim()); let yr = parseInt(y, 10);
  if (isNaN(yr)) return d.trim(); if (yr < 100) yr = yr >= 49 ? 1900 + yr : 2000 + yr;
  const f = v => v.toLowerCase() === "xx" ? "xx" : String(parseInt(v, 10)).padStart(2, "0");
  return `${yr}-${f(m)}-${f(dd)}`;
}
function lbDate(iso) { const [y, m, d] = iso.split("-"); return `${+m}/${+d}/${y.slice(2)}`; }
function canon(lb, date, loc, xref) {
  const iso = isoOf(date), l = (loc || "").trim();
  let tag = "LB-" + String(lb).padStart(5, "0"); if (xref) tag += "-xref" + String(xref).padStart(5, "0");
  return (iso && l ? `${iso} ${l} (${tag})` : tag) + "-NFT";
}
function cur(r) {
  const s = state[r.lb] || {};
  let loc = s.location, date = s.date_str;
  if (loc === undefined) loc = r.location || (r.candidates[0] ? r.candidates[0].suggestion : "");
  if (date === undefined) date = r.date_str;
  return {status: s.status || "pending", loc, date, pick: s.pick ?? (r.location ? -1 : 0)};
}
function setS(lb, patch) { state[lb] = Object.assign({}, state[lb], patch); save(); }

function stats() {
  const c = {pending: 0, confirmed: 0, skipped: 0};
  DATA.rows.forEach(r => c[cur(r).status]++);
  const olof = DATA.rows.filter(r => r.candidates.length).length;
  document.getElementById("stats").innerHTML =
    `<b>${DATA.rows.length}</b> LBs · <b>${olof}</b> Olof match · pending <b>${c.pending}</b> · ` +
    `confirmed <b>${c.confirmed}</b> · skipped <b>${c.skipped}</b>`;
}

function card(r) {
  const c = cur(r);
  const miss = f => `<span class="tag ${r[f] ? "ok" : "miss"}">${f === "date_str" ? "date" : f}: ${esc(r[f]) || "missing"}</span>`;
  const cands = r.candidates.length ? r.candidates.map((k, i) =>
    `<label><input type="radio" name="p${r.lb}" value="${i}" ${c.pick === i ? "checked" : ""}>
     <b>${esc(k.suggestion)}</b> <span class="dim">— ${esc(k.venue)} · ${esc(k.type)} · ${esc(k.event_id)}</span></label>`).join("")
    + `<label><input type="radio" name="p${r.lb}" value="-1" ${c.pick === -1 ? "checked" : ""}> <span class="dim">manual / keep typed value</span></label>`
    : `<div class="dim">${r.iso && !r.iso.includes("x") ? "No olof_events row for " + esc(r.iso) : "No usable date — Olof can't be matched; type the values."}</div>`;
  const prev = r.folders.map(f => {
    const n = canon(r.lb, c.date, c.loc, f.xref);
    return `<div class="mono dim">${esc(f.name)}</div><div class="mono new">→ ${esc(n)}</div>`;
  }).join("");
  return `<div class="card ${c.status}" data-lb="${r.lb}">
   <div class="top"><span class="lb">LB-${String(r.lb).padStart(5, "0")}</span>
    ${miss("date_str")} ${miss("location")}
    <span class="tag">${esc(r.source || "no source")}</span>
    ${r.taper ? `<span class="tag">taper ${esc(r.taper)}</span>` : ""}
    <span class="tag">${c.status}</span></div>
   <div class="grid"><span class="dim">Olof ${esc(r.iso || "")}</span><div class="cands">${cands}</div></div>
   <div class="edit"><input class="date" value="${esc(c.date)}" placeholder="M/D/YY">
    <input class="loc" value="${esc(c.loc)}" placeholder="City, State / City, Country"></div>
   <div class="preview">${prev}</div>
   ${r.description ? `<details><summary>description</summary><div class="dim">${esc(r.description)}</div></details>` : ""}
   <div class="actions">
    <button class="primary act" data-a="confirmed">Confirm write</button>
    <button class="act" data-a="skipped">Skip</button>
    <button class="act" data-a="pending">Undo</button></div></div>`;
}

function visible(r) {
  const f = document.getElementById("filter").value, st = cur(r).status;
  if (f === "olof") { if (st !== "pending" || !r.candidates.length) return false; }
  else if (f !== "all" && st !== f) return false;
  const q = document.getElementById("q").value.trim().toLowerCase();
  if (!q) return true;
  return (String(r.lb) + " " + r.folders.map(x => x.name).join(" ") + " " + r.description +
          " " + r.taper).toLowerCase().includes(q);
}
function render() {
  const rows = DATA.rows.filter(visible);
  document.getElementById("list").innerHTML = rows.length ? rows.map(card).join("")
    : `<div class="dim">Nothing here.</div>`;
  stats();
}
function refreshCard(el, r) { el.outerHTML = card(r); stats(); }

const list = document.getElementById("list");
list.addEventListener("change", e => {
  const el = e.target.closest(".card"); if (!el) return;
  const r = DATA.rows.find(x => x.lb == el.dataset.lb);
  if (e.target.type === "radio") {
    const i = +e.target.value, patch = {pick: i};
    if (i >= 0) {
      patch.location = r.candidates[i].suggestion;
      if (!r.date_str && r.iso) patch.date_str = lbDate(r.iso);
    }
    setS(r.lb, patch); refreshCard(el, r);
  }
});
list.addEventListener("input", e => {
  const el = e.target.closest(".card"); if (!el) return;
  const r = DATA.rows.find(x => x.lb == el.dataset.lb);
  if (e.target.classList.contains("loc")) setS(r.lb, {location: e.target.value});
  if (e.target.classList.contains("date")) setS(r.lb, {date_str: e.target.value});
  const c = cur(r);
  el.querySelector(".preview").innerHTML = r.folders.map(f =>
    `<div class="mono dim">${esc(f.name)}</div><div class="mono new">→ ${esc(canon(r.lb, c.date, c.loc, f.xref))}</div>`).join("");
});
list.addEventListener("click", e => {
  const b = e.target.closest(".act"); if (!b) return;
  const el = b.closest(".card"), r = DATA.rows.find(x => x.lb == el.dataset.lb);
  const c = cur(r);
  if (b.dataset.a === "confirmed" && (!c.loc.trim() || !isoOf(c.date))) {
    alert("A canonical name needs both a date and a location."); return;
  }
  setS(r.lb, {status: b.dataset.a, location: c.loc, date_str: c.date});
  if (document.getElementById("filter").value === "all") refreshCard(el, r); else render();
});
document.getElementById("filter").onchange = render;
document.getElementById("q").oninput = render;
document.getElementById("acceptAll").onclick = () => {
  const todo = DATA.rows.filter(r => cur(r).status === "pending" && r.candidates.length === 1);
  if (!confirm(`Confirm ${todo.length} pending LB(s) with exactly one Olof candidate?`)) return;
  todo.forEach(r => { const c = cur(r); if (c.loc.trim() && isoOf(c.date))
    setS(r.lb, {status: "confirmed", location: c.loc, date_str: c.date}); });
  render();
};
document.getElementById("reset").onclick = () => {
  if (confirm("Clear every decision on this page?")) { state = {}; save(); render(); }
};
document.getElementById("export").onclick = () => {
  const decisions = DATA.rows.filter(r => cur(r).status === "confirmed").map(r => {
    const c = cur(r), k = c.pick >= 0 ? r.candidates[c.pick] : null;
    return {lb: r.lb, date_str: c.date.trim(), location: c.loc.trim(),
            olof_event_id: k && k.suggestion === c.loc.trim() ? k.event_id : null,
            before: {date_str: r.date_str, location: r.location}};
  });
  if (!decisions.length) { alert("Nothing confirmed yet."); return; }
  const blob = new Blob([JSON.stringify({built: DATA.built, decisions}, null, 1)], {type: "application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "private_meta_decisions.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
render();
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
