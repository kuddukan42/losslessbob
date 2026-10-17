// TapeMatch rail filter — ADD-ON component. Drop-in replacement for <Rail> in tm-app.jsx.
// Same row markup, same chips, same tokens; adds query parsing, a year brush and windowing.
(() => {
  const { useState, useMemo, useRef, useEffect, useCallback, useLayoutEffect } = React;
  const STATUS = (window.TM && window.TM.STATUS) || {
    conflict:{tone:"bad"}, review:{tone:"warn"}, clean:{tone:"ok"}, curated:{tone:"mute"},
  };
  const ROW = 46, HEAD = 26, PAD = 6, OVERSCAN = 8;
  const CHIPS = [{k:"needs",label:"Needs you"},{k:"conflict",label:"Conflicts"},{k:"all",label:"All"},{k:"curated",label:"Done"}];
  const STATUS_WORDS = ["conflict","review","clean","curated"];

  const chipMatch = (f, d) => f === "all" ? true : f === "needs" ? (d.status === "conflict" || d.status === "review") : f === "conflict" ? d.status === "conflict" : d.status === "curated";

  function parseQuery(q) {
    const out = { text: [], statuses: [], years: [], prefixes: [], monthDay: [] };
    q.toLowerCase().split(/\s+/).filter(Boolean).forEach((t) => {
      const s = t.startsWith("status:") ? t.slice(7) : t;
      if (STATUS_WORDS.includes(s)) return out.statuses.push(s);
      if (/^(19|20)\d{2}$/.test(t)) return out.years.push(+t);
      if (/^(19|20)\d0s$/.test(t)) { const d = +t.slice(0, 4); for (let y = d; y < d + 10; y++) out.years.push(y); return; }
      if (/^'?\d{2}$/.test(t)) { const n = +t.replace("'", ""); return out.years.push(n > 30 ? 1900 + n : 2000 + n); }
      if (/^(19|20)\d{2}-\d{1,2}(-\d{1,2})?$/.test(t)) {
        const p = t.split("-"); return out.prefixes.push(p[0] + "-" + p[1].padStart(2,"0") + (p[2] ? "-" + p[2].padStart(2,"0") : ""));
      }
      if (/^\d{1,2}\/\d{1,2}$/.test(t)) { const p = t.split("/"); return out.monthDay.push(p[0].padStart(2,"0") + "-" + p[1].padStart(2,"0")); }
      out.text.push(t);
    });
    return out;
  }
  function queryMatch(d, pq, hay) {
    if (pq.statuses.length && !pq.statuses.includes(d.status)) return false;
    if (pq.years.length && !pq.years.includes(+d.date.slice(0, 4))) return false;
    if (pq.prefixes.length && !pq.prefixes.some((p) => d.date.startsWith(p))) return false;
    if (pq.monthDay.length && !pq.monthDay.includes(d.date.slice(5))) return false;
    for (const t of pq.text) if (hay.indexOf(t) === -1) return false;
    return true;
  }

  function YearBrush({ years, counts, range, setRange }) {
    const ref = useRef(null);
    const drag = useRef(null);
    const max = Math.max(1, ...years.map((y) => counts[y] ? counts[y].all : 0));
    const yearAt = (clientX) => {
      const el = ref.current; if (!el) return null;
      const r = el.getBoundingClientRect();
      const i = Math.min(years.length - 1, Math.max(0, Math.floor(((clientX - r.left) / r.width) * years.length)));
      return years[i];
    };
    const down = (e) => {
      const y = yearAt(e.clientX); if (y == null) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      drag.current = y; setRange([y, y]);
    };
    const move = (e) => { if (drag.current == null) return; const y = yearAt(e.clientX); if (y != null) setRange([Math.min(drag.current, y), Math.max(drag.current, y)]); };
    const up = () => { drag.current = null; };
    const dec = [1960,1970,1980,1990,2000,2010,2020];
    return (
      <div className="tmfBrush">
        <div className="tmfBrushTop">
          <span className="tmfBrushLbl">Years</span>
          <span className="tmfBrushVal">
            {range ? <React.Fragment>{range[0]}{range[1] !== range[0] ? `–${range[1]}` : ""} <button className="tmfClear" style={{position:"static"}} onClick={() => setRange(null)} title="Clear year range">×</button></React.Fragment> : <span className="dim">all · drag to scope</span>}
          </span>
        </div>
        <div className="tmfBars" ref={ref} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
          {years.map((y) => {
            const c = counts[y] || { all: 0, need: 0 };
            const inR = !range || (y >= range[0] && y <= range[1]);
            const h = c.all ? Math.max(2, Math.round((c.all / max) * 32)) : 0;
            const nh = c.all ? Math.round((c.need / c.all) * h) : 0;
            return (
              <span key={y} className={"tmfBar" + (inR ? " in" : "") + (range && range[0] === range[1] && range[0] === y ? " hot" : "")} title={`${y} · ${c.all} dates · ${c.need} need you`}>
                {nh > 0 && <i className="tmfBarNeed" style={{ height: nh }}></i>}
                {h - nh > 0 && <i className="tmfBarRest" style={{ height: h - nh }}></i>}
              </span>
            );
          })}
        </div>
        <div className="tmfDecades">
          {dec.map((d) => {
            const on = range && range[0] === d && range[1] === d + 9;
            return <button key={d} className={"tmfDec" + (on ? " on" : "")} onClick={() => setRange(on ? null : [d, d + 9])}>{String(d).slice(2)}s</button>;
          })}
        </div>
      </div>
    );
  }

  function TMFRail({ dates, active, onActivate, narrow }) {
    const [q, setQ] = useState("");
    const [chip, setChip] = useState("needs");
    const [range, setRange] = useState(null);
    const [asc, setAsc] = useState(false);
    const [cursor, setCursor] = useState(0);
    const [view, setView] = useState({ top: 0, h: 600 });
    const listRef = useRef(null), inputRef = useRef(null);

    const indexed = useMemo(() => dates.map((d) => ({ d, hay: (d.date + " " + d.loc).toLowerCase(), y: +d.date.slice(0, 4) })), [dates]);
    const pq = useMemo(() => parseQuery(q), [q]);
    // stage 1 — chips + query. The histogram is drawn from this, so bars react to typing.
    const staged = useMemo(() => indexed.filter((r) => chipMatch(chip, r.d) && queryMatch(r.d, pq, r.hay)), [indexed, chip, pq]);
    const years = useMemo(() => { const a = indexed.map((r) => r.y); const lo = Math.min(...a), hi = Math.max(...a); return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i); }, [indexed]);
    const counts = useMemo(() => { const m = {}; staged.forEach((r) => { const c = m[r.y] || (m[r.y] = { all: 0, need: 0 }); c.all++; if (r.d.status === "conflict" || r.d.status === "review") c.need++; }); return m; }, [staged]);
    // stage 2 — year brush
    const rows = useMemo(() => {
      let l = range ? staged.filter((r) => r.y >= range[0] && r.y <= range[1]) : staged;
      return asc ? l.slice().reverse() : l;
    }, [staged, range, asc]);

    // flatten to year-grouped items with prefix offsets (uniform heights → O(1) windowing)
    const { items, offsets, total } = useMemo(() => {
      const items = [], offsets = []; let t = 0, prev = null;
      const per = {};
      rows.forEach((r) => { per[r.y] = (per[r.y] || 0) + 1; });
      rows.forEach((r, i) => {
        if (r.y !== prev) { items.push({ t: "y", y: r.y, n: per[r.y] }); offsets.push(t); t += HEAD; prev = r.y; }
        items.push({ t: "d", d: r.d, i }); offsets.push(t); t += ROW;
      });
      return { items, offsets, total: t };
    }, [rows]);

    const dateItemIndex = useMemo(() => { const m = []; items.forEach((it, k) => { if (it.t === "d") m[it.i] = k; }); return m; }, [items]);

    useEffect(() => { setCursor((c) => Math.min(Math.max(c, 0), Math.max(rows.length - 1, 0))); }, [rows.length]);

    useLayoutEffect(() => {
      const el = listRef.current; if (!el) return;
      const onScroll = () => setView({ top: el.scrollTop, h: el.clientHeight });
      onScroll(); el.addEventListener("scroll", onScroll, { passive: true });
      const ro = new ResizeObserver(onScroll); ro.observe(el);
      return () => { el.removeEventListener("scroll", onScroll); ro.disconnect(); };
    }, []);

    // keep cursor visible using the offset table — no scrollIntoView
    useEffect(() => {
      const el = listRef.current, k = dateItemIndex[cursor]; if (!el || k == null) return;
      const top = offsets[k], bottom = top + ROW;
      if (top < el.scrollTop) el.scrollTop = Math.max(0, top - HEAD - 4);
      else if (bottom > el.scrollTop + el.clientHeight) el.scrollTop = bottom - el.clientHeight + 4;
    }, [cursor, dateItemIndex, offsets]);

    const jump = useCallback((d) => { setCursor((c) => Math.min(Math.max(c + d, 0), Math.max(rows.length - 1, 0))); }, [rows.length]);

    useEffect(() => {
      const onKey = (e) => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const t = e.target, typing = t && (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName));
        if (e.key === "/" && !typing) { e.preventDefault(); inputRef.current && inputRef.current.focus(); return; }
        if (typing) {
          if (e.key === "Escape") { e.preventDefault(); if (q) setQ(""); else t.blur(); }
          if (e.key === "Enter") { e.preventDefault(); const r = rows[cursor] || rows[0]; if (r) { setCursor(rows.indexOf(r)); onActivate(r.d); t.blur(); } }
          if (e.key === "ArrowDown") { e.preventDefault(); jump(1); }
          if (e.key === "ArrowUp") { e.preventDefault(); jump(-1); }
          return;
        }
        if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); jump(1); }
        else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); jump(-1); }
        else if (e.key === "Enter") { const r = rows[cursor]; if (r) { e.preventDefault(); onActivate(r.d); } }
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [rows, cursor, q, jump, onActivate]);

    // window slice
    let lo = 0, hi = items.length - 1, first = 0;
    const target = view.top - PAD;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (offsets[mid] < target) { first = mid; lo = mid + 1; } else hi = mid - 1; }
    first = Math.max(0, first - OVERSCAN);
    let last = first;
    while (last < items.length && offsets[last] < view.top + view.h + ROW * OVERSCAN) last++;

    const needs = staged.filter((r) => r.d.status === "conflict" || r.d.status === "review").length;
    const filtered = !!q || !!range || chip !== "all";

    return (
      <aside className={"tmRail" + (narrow ? " narrow" : "")}>
        <div className="tmfHead">
          <div className="tmfTitleRow">
            <span className="tmRailTitle">Triage queue <span className="tmRailCount">{needs.toLocaleString()} need you</span></span>
          </div>
          <div className="tmfSearchWrap">
            <span className="tmfSearchIcon mono">⌕</span>
            <input ref={inputRef} className="tmfSearch" value={q} placeholder="date, city, 1974, 70s, conflict…" onChange={(e) => setQ(e.target.value)} spellCheck="false" />
            {q && <button className="tmfClear" onClick={() => { setQ(""); inputRef.current.focus(); }} title="Clear">×</button>}
          </div>
          <div className="tmRailFilters">
            {CHIPS.map((f) => <button key={f.k} className={"chip" + (chip === f.k ? " on" : "")} onClick={() => setChip(f.k)}>{f.label}</button>)}
          </div>
          <YearBrush years={years} counts={counts} range={range} setRange={setRange} />
        </div>
        <div className="tmfResult">
          <span><b>{rows.length.toLocaleString()}</b> of {dates.length.toLocaleString()} dates</span>
          <span style={{ display: "flex", gap: 6 }}>
            {filtered && <button className="tmfSort" onClick={() => { setQ(""); setRange(null); setChip("all"); }}>reset</button>}
            <button className="tmfSort" onClick={() => setAsc((a) => !a)} title="Toggle sort order">{asc ? "oldest ↑" : "newest ↓"}</button>
          </span>
        </div>
        <div className="tmfList" ref={listRef}>
          {!rows.length && <div className="tmRailEmpty">No dates match.<br /><span className="dim">Try a year, a city, or clear the filters.</span></div>}
          <div className="tmfSpacer" style={{ height: total }}>
            {items.slice(first, last).map((it, n) => {
              const k = first + n, y = offsets[k];
              if (it.t === "y") return <div key={"y" + it.y} className="tmfAbs tmfYear" style={{ top: y }}>{it.y}<span className="tmfYearN">{it.n}</span></div>;
              const d = it.d, st = STATUS[d.status] || { tone: "mute" };
              return (
                <button key={d.date} data-row={it.i} className={"tmfAbs tmDateRow" + (active === d.date ? " on" : "") + (cursor === it.i ? " cur" : "")} style={{ top: y }}
                  onClick={() => { setCursor(it.i); onActivate(d); }}>
                  <span className="tmStDot" style={{ background: `var(--${st.tone}-bar)` }}></span>
                  <span className="tmDateMain">
                    <span className="tmDateD mono">{d.date}</span>
                    <span className="tmDateLoc">{d.loc}</span>
                  </span>
                  <span className="tmDateN mono">{d.recs}<span className="dim">→</span><strong>{d.fams}</strong></span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="tmfFoot">
          <span><kbd>/</kbd> search</span><span><kbd>j</kbd><kbd>k</kbd> move</span><span><kbd>⏎</kbd> open</span><span><kbd>esc</kbd> clear</span>
        </div>
      </aside>
    );
  }

  window.TMFRail = TMFRail;
  window.TMFParseQuery = parseQuery;
})();
