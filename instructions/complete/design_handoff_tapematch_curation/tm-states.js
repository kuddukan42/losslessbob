// TapeMatch — designs for the states missing from the main prototype.
(() => {
  const { FAM } = window.TM;
  const el = (t, c, h) => { const n = document.createElement(t); if (c) n.className = c; if (h != null) n.innerHTML = h; return n; };
  const frag = (h) => { const d = document.createElement("div"); d.innerHTML = h; return d; };

  // ── shared chrome ─────────────────────────────────────────────────────────
  const topBar = (right) => `<header class="tmTop"><span class="tmCrumb">LosslessBob <span class="dim">/</span> Library <span class="dim">/</span> <strong>TapeMatch</strong></span><span class="tmTopSub">Curation — review the algorithm's family calls, pair by pair</span><span class="tmTopRight">${right || '<span class="tmCrawl"><span class="tmStDot" style="background:var(--ok-bar)"></span> crawl idle · 2,226 runs · 2,075 dates</span>'}</span></header>`;

  const chips = (on) => ["Needs you","Conflicts","All","Done"].map(l => `<button class="chip${l===on?" on":""}">${l}</button>`).join("");

  const railRows = [
    ["2001-11-19","New York, NY","bad","10","5"],
    ["2001-11-20","New York, NY","warn","4","4"],
    ["2001-11-17","Philadelphia, PA","bad","6","4"],
  ];
  const rail = (opts = {}) => {
    const rows = (opts.rows || railRows).map((r, i) => `<button class="tmDateRow${i===(opts.active??0)?" on":""}"><span class="tmStDot" style="background:var(--${r[2]}-bar)"></span><span class="tmDateMain"><span class="tmDateD mono">${r[0]}</span><span class="tmDateLoc">${r[1]}</span></span><span class="tmDateN mono">${r[3]}<span class="dim">→</span><strong>${r[4]}</strong></span></button>`).join("");
    return `<aside class="tmRail"><div class="tmRailHead"><div class="tmRailTitle">Triage queue <span class="tmRailCount">${opts.count ?? "3 need you"}</span></div><div class="tmRailFilters">${chips(opts.filter || "Needs you")}</div></div><div class="tmRailList">${opts.empty ? `<div class="tmRailEmpty">${opts.empty}</div>` : rows}</div><div class="tmRailFoot"><span class="dim">j / k to move · enter to open</span></div></aside>`;
  };

  const railSkeleton = () => `<aside class="tmRail"><div class="tmRailHead"><div class="tmRailTitle">Triage queue</div><div class="tmRailFilters">${chips("Needs you")}</div></div><div class="tmRailList">${Array.from({length:7},(_,i)=>`<div style="display:flex;align-items:center;gap:9px;padding:9px">
      <span class="sk" style="width:7px;height:7px;border-radius:50%;flex:0 0 7px"></span>
      <span style="flex:1;display:flex;flex-direction:column;gap:5px"><span class="sk skBar" style="width:${62-i%3*8}px;height:8px"></span><span class="sk skBar" style="width:${86-i%4*11}px;height:7px"></span></span>
      <span class="sk skBar" style="width:26px;height:7px"></span></div>`).join("")}</div><div class="tmRailFoot"><span class="dim">j / k to move · enter to open</span></div></aside>`;

  const dateHead = (opts = {}) => `<div class="tmDateHead"><div class="tmDateHeadL"><div class="tmDateHeadTop"><span class="tmDateBig mono">${opts.date || "2001-11-20"}</span><span class="tmVenue">${opts.venue || "Beacon Theatre · New York, NY"}</span>${opts.run===false?"":`<span class="pill sm mute mono">run ${opts.run || "20260602_214402"}</span>`}</div><div class="tmVerdictLine">${opts.pill || ""}<span class="tmVerdictTx">${opts.verdict || ""}</span>${opts.model===false?"":`<span class="tmModel mono">claude-sonnet-4-6 · 2026-06-03</span>`}</div></div><div class="tmDateHeadR">${opts.right || ""}</div></div>`;

  const section = (title, hint, body) => `<div class="tmSection"><div class="tmSecHead"><span class="tmSecTitle">${title}</span>${hint?`<span class="tmSecHint">${hint}</span>`:""}</div>${body}</div>`;

  // ── frame wrapper ─────────────────────────────────────────────────────────
  let CANVAS = null;
  function frame(id, label, note, x, y, w, h, inner) {
    const wrap = el("div", "fr");
    wrap.id = id;
    wrap.setAttribute("data-screen-label", label);
    Object.assign(wrap.style, { position: "absolute", left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
    wrap.innerHTML = `<div class="frLabel"><span class="frName">${label}</span>${note?`<span class="frNote">${note}</span>`:""}</div><div class="frBox"><div class="tmApp">${inner}</div></div>`;
    CANVAS.appendChild(wrap);
  }

  // ── 1. loading ────────────────────────────────────────────────────────────
  const N = 10;
  const mxSkeleton = `<div class="tmMatrixWrap"><div class="tmMatrix" style="grid-template-columns:52px repeat(${N},minmax(0,1fr))"><div></div>${Array.from({length:N},()=>`<div class="tmMxHead"><span class="sk skHead"></span></div>`).join("")}${Array.from({length:N},(_,i)=>`<div class="tmMxRowHead"><span class="sk skRowHead"></span></div>${Array.from({length:N},(_,j)=>i===j?`<div class="tmCell tmCellDiag"></div>`:`<div class="sk skCell"></div>`).join("")}`).join("")}</div><div class="tmSkNote">measuring 45 pairs · 31 done</div></div>`;
  const dossierSkeleton = `<div class="tmDossier"><div class="tmDossHead"><div class="tmDossPair"><span class="sk skBar" style="width:96px;height:12px"></span><span class="tmDossX">×</span><span class="sk skBar" style="width:96px;height:12px"></span></div></div><div class="tmDossVerdict"><div><span class="sk skBar" style="width:74px;height:22px;display:block"></span><span class="sk skBar" style="width:150px;height:7px;display:block;margin-top:7px"></span></div><span class="sk skBar" style="width:82px;height:17px;border-radius:999px"></span></div>${["Primary evidence","Secondary evidence"].map((s,si)=>`<div class="tmDossSec">${s}</div>${Array.from({length:si?3:1},(_,i)=>`<div class="tmEv"><div class="tmEvTop"><span class="sk skBar" style="width:${112-i*9}px;height:8px"></span><span class="sk skBar" style="width:38px;height:8px"></span></div><div class="tmEvTrack"></div><div style="margin-top:6px"><span class="sk skBar" style="width:${180-i*22}px;height:6px"></span></div></div>`).join("")}`).join("")}</div>`;

  // ── 6. large-N matrix ─────────────────────────────────────────────────────
  function bigMatrix() {
    const FAMS = [3,5,2,4,6,3,2,4,5]; // 34 recordings across 9 families
    const recs = []; let lb = 10480;
    FAMS.forEach((size, f) => { for (let i = 0; i < size; i++) recs.push({ id: String(lb += 137 + i * 29), fam: (f % 5) + 1, famIdx: f }); });
    // extended family ramp: same L/C as FAM 1-5, hue rotated onward (README §Design Tokens)
    const RAMP = [FAM[1], FAM[2], FAM[3], FAM[4], FAM[5], "oklch(0.65 0.10 285)", "oklch(0.63 0.09 190)", "oklch(0.66 0.10 110)", "oklch(0.61 0.09 340)"];
    const hue = (f) => RAMP[f % RAMP.length];
    const n = recs.length;
    const cells = recs.map((a, i) => {
      const head = `<div class="tmMxRowHead"><span>${a.id}</span><span class="tmFamDot" style="background:${hue(a.famIdx)};width:6px;height:6px"></span></div>`;
      const row = recs.map((b, j) => {
        if (i === j) return `<div class="tmCell tmCellDiag"></div>`;
        const same = a.famIdx === b.famIdx;
        const seed = ((i * 31 + j * 17) % 97) / 97;
        if (!same && seed > 0.94) return `<div class="tmCell" style="background:repeating-linear-gradient(45deg,var(--surface2),var(--surface2) 3px,var(--surface) 3px,var(--surface) 6px)"></div>`;
        const sim = same ? 86 + Math.round(seed * 13) : Math.round(4 + seed * 34);
        const bg = same ? `color-mix(in oklab,${hue(a.famIdx)} ${(30 + sim * 0.55).toFixed(0)}%,var(--surface))`
          : `color-mix(in oklab,var(--accent) ${(Math.pow(sim / 100, 0.8) * 72).toFixed(0)}%,var(--surface))`;
        const conflict = (i === 2 && j === 19) || (i === 19 && j === 2);
        return `<div class="tmCell" style="background:${bg}" title="LB-${a.id} × LB-${b.id} — ${sim}%">${conflict?'<span class="tmConfDot"></span>':""}</div>`;
      }).join("");
      return head + row;
    }).join("");
    return `<div class="tmMatrixWrap wide"><div class="tmMatrix compact" style="grid-template-columns:46px repeat(${n},22px)"><div></div>${recs.map(r=>`<div class="tmMxHead"><span class="tmFamDot" style="background:${hue(r.famIdx)};width:6px;height:6px"></span><span>${r.id}</span></div>`).join("")}${cells}</div><div class="tmMxLegend"><span class="lgSwatch" style="background:color-mix(in oklab,var(--accent) 12%,var(--surface))"></span> unrelated<span class="lgSwatch" style="background:color-mix(in oklab,var(--accent) 55%,var(--surface))"></span> check<span class="lgSwatch" style="background:${FAM[1]}"></span> same family<span class="lgConf"><span class="tmConfDot static"></span> conflict</span><span class="tmDensity mono">34 recordings · 9 families · 561 pairs · values in tooltip below 28px</span></div></div>`;
  }

  // ── save-state trio ───────────────────────────────────────────────────────
  const judgeGrid = (on) => `<div class="tmJudge">${[["Same source","ok"],["Different","info"],["Uncertain","warn"],["LB wrong","bad"]].map(([l,t])=>`<button class="tmJudgeBtn ${t}${l===on?" on":""}">${l}</button>`).join("")}</div>`;

  function build() {
    CANVAS = document.body;
    // 1 — loading
    frame("st-loading", "Loading", "matrix + dossier skeleton · rail loads first", 0, 0, 1440, 900,
      topBar('<span class="tmCrawl"><span class="tmStDot" style="background:var(--warn-bar)"></span> measuring pairs…</span>') +
      `<div class="tmBody">${railSkeleton()}<main class="tmMain">` +
      `<div class="tmDateHead"><div class="tmDateHeadL"><div class="tmDateHeadTop"><span class="sk skBar" style="width:132px;height:18px"></span><span class="sk skBar" style="width:210px;height:11px"></span></div><div class="tmVerdictLine"><span class="sk skBar" style="width:88px;height:17px;border-radius:999px"></span><span class="sk skBar" style="width:280px;height:9px"></span></div></div><div class="tmDateHeadR"><div class="tmFams">${Array.from({length:5},()=>'<span class="sk skBar" style="width:74px;height:19px;border-radius:999px"></span>').join("")}</div><div class="tmHeadActions"><span class="sk skBar" style="width:112px;height:27px;border-radius:6px"></span><span class="sk skBar" style="width:132px;height:27px;border-radius:6px"></span></div></div></div>` +
      `<div class="tmWork"><div class="tmWorkL">${section("Similarity matrix","holding the final grid size — no reflow when values land",mxSkeleton)}</div>${dossierSkeleton}</div></main></div>`);

    // 2 — fetch error
    frame("st-error", "Fetch error", "date artifacts unreachable · rail still usable", 1520, 0, 1440, 900,
      topBar() + `<div class="tmBody">${rail({active:1})}<main class="tmMain">` +
      dateHead({ date:"2001-11-20", venue:"Beacon Theatre · New York, NY", run:false, model:false, pill:'<span class="pill bad">unavailable</span>', verdict:"Couldn't load this date's analysis" }) +
      `<div class="tmState"><div class="tmStateIcon bad">⚠</div><div class="tmStateHead">Couldn't load this date</div><div class="tmStateTx">The run's artifacts didn't come back. Nothing has been changed — your queued judgments are safe.</div><div class="tmStateDetail">GET /runs/20260602_214402/pairs → 504 after 30s
run 20260602_214402 · attempt 2 of 2</div><div class="tmStateActions"><button class="btn primary">Retry</button><button class="btn ghost">Open run log</button></div></div></main></div>`);

    // 3 — empty rail
    frame("st-empty-rail", "Empty queue result", "filter matches nothing · main area keeps the open date", 3040, 0, 1440, 900,
      topBar() + `<div class="tmBody">${rail({ filter:"Conflicts", count:"0 need you", empty:"No conflicts left.<div style='margin-top:6px;font-size:10.5px'>Every disagreement on this page is resolved.</div><button class='tmLink' style='margin-top:9px'>Show all dates</button>" })}<main class="tmMain">` +
      dateHead({ date:"2001-11-19", venue:"Madison Square Garden · New York, NY", run:"20260602_211540", pill:'<span class="pill ok">resolved</span>', verdict:"5 families from 10 recordings — all conflicts judged" }) +
      `<div class="tmState"><div class="tmStateIcon">⊞</div><div class="tmStateHead">Nothing left in this filter</div><div class="tmStateTx">The date you were working on stays open. Widen the filter to keep going.</div></div></main></div>`);

    // 4 — zero recordings
    frame("st-zero", "Date with no recordings", "known show, nothing to compare yet", 0, 1000, 1440, 900,
      topBar() + `<div class="tmBody">${rail({ rows:[["2001-11-19","New York, NY","bad","10","5"],["1994-04-08","Kansas City, MO","mute","0","0"],["2001-11-17","Philadelphia, PA","bad","6","4"]], active:1 })}<main class="tmMain">` +
      dateHead({ date:"1994-04-08", venue:"Memorial Hall · Kansas City, MO", run:false, model:false, pill:'<span class="pill mute">no recordings</span>', verdict:"Known date · nothing circulating in the library" }) +
      `<div class="tmState"><div class="tmStateIcon mute">∅</div><div class="tmStateHead">No recordings for this date</div><div class="tmStateTx">The show is in the library but no audience recordings have been indexed, so TapeMatch has nothing to compare. It will re-enter the queue automatically when a recording appears.</div><div class="tmStateActions"><button class="btn ghost">Open date page</button><button class="btn ghost">Skip in queue</button></div></div></main></div>`);

    // 5 — single recording
    frame("st-single", "Single recording", "no pairs exist · matrix and dossier suppressed", 1520, 1000, 1440, 900,
      topBar() + `<div class="tmBody">${rail({ rows:[["2001-11-19","New York, NY","bad","10","5"],["2001-11-15","Washington, DC","ok","1","1"],["2001-11-17","Philadelphia, PA","bad","6","4"]], active:1 })}<main class="tmMain">` +
      dateHead({ date:"2001-11-15", venue:"9:30 Club · Washington, DC", run:"20260602_212218", pill:'<span class="pill ok">clean</span>', verdict:"1 recording — 1 family by definition",
        right:`<div class="tmFams"><span class="tmFamChip"><span class="tmFamDot" style="background:${FAM[1]}"></span>F1<span class="tmFamMembers mono">11902</span></span></div><div class="tmHeadActions"><button class="btn ghost">Open report.md</button><button class="btn primary">Accept families</button></div>` }) +
      `<div class="tmWork single"><div class="tmWorkL">${section("Recording","nothing to compare — pair views only appear from two recordings up",
        `<div class="tmSolo"><div class="tmSoloTop"><span class="tmFamDot" style="background:${FAM[1]}"></span><span class="tmSoloLb">LB-11902</span><span class="pill sm ok">reference</span><span class="pill sm mute">A−</span></div><div class="tmSoloMeta"><span class="tmSoloK">Duration</span><span class="tmSoloV">1:46:32</span><span class="tmSoloK">Speed</span><span class="tmSoloV">0 ppm · reference</span><span class="tmSoloK">Lineage</span><span class="tmSoloV">Neumann km140 &gt; D8 DAT &gt; EAC &gt; FLAC</span></div><div class="tmSoloNote">Sole recording, so it becomes its own family with no evidence needed. Accepting records the family without a human pair judgment.</div></div>`)}
      ${section("Speed & lag","one point, kept for continuity with multi-recording dates",
        `<div class="tmSpeed"><div class="tmSpeedLane" style="height:56px"><span class="tmTick" style="left:50%"><span class="tmTickLine"></span><span class="tmTickLbl">ref</span></span><span class="tmSpeedDot" style="left:50%;top:4px"><span class="tmSpeedGlyph" style="background:${FAM[1]}">◆</span><span class="tmSpeedLb">11902</span></span></div><div class="tmSpeedLegend"><span>◆ reference</span><span class="tmSpeedAxNote">no offsets to plot</span></div></div>`)}</div></div></main></div>`);

    // 6 — large N
    frame("st-large", "Large date · 34 recordings", "compact cells, rotated headers, values move to tooltips", 3040, 1000, 1440, 900,
      topBar() + `<div class="tmBody">${rail({ rows:[["1995-07-09","Chicago, IL","bad","34","9"],["2001-11-19","New York, NY","bad","10","5"],["2001-11-17","Philadelphia, PA","bad","6","4"]], active:0 })}<main class="tmMain">` +
      dateHead({ date:"1995-07-09", venue:"Soldier Field · Chicago, IL", run:"20260602_203311", pill:'<span class="pill bad">needs review</span>', verdict:"9 families from 34 recordings — 3 conflicts",
        right:`<div class="tmHeadActions"><button class="btn ghost">Open report.md</button><button class="btn primary" disabled>Accept families</button></div>` }) +
      `<div class="tmWork single"><div class="tmWorkL">${section("Similarity matrix","cells shrink to 22px and scroll horizontally · hover or select for values",bigMatrix())}</div></div></main></div>`);

    // 7 — save states
    const saveFrame = (cls, body) => `<div class="tmSave ${cls}"><span class="tmSaveDot"></span>${body}</div>`;
    frame("st-save", "Judgment save states", "footer of the dossier judgment block", 0, 2000, 460, 540, "",);
    const f = document.getElementById("st-save");
    f.querySelector(".tmApp").outerHTML = `<div class="tmDossier" style="border-left:none">
      <div class="tmDossSec">Your judgment</div>${judgeGrid("LB wrong")}
      <div class="tmJudgeNote">Writes <span class="mono">human_judgment</span> to <span class="mono">observations.db · pairs</span>.</div>
      ${saveFrame("saving","Saving…")}
      <div class="tmDossSec" style="margin-top:20px">Saved</div>${judgeGrid("LB wrong")}${saveFrame("saved","Saved 14:22 · LB wrong")}
      <div class="tmDossSec" style="margin-top:20px">Save failed</div>${judgeGrid("LB wrong")}
      ${saveFrame("failed",`Couldn't save — kept locally. <button class="tmSaveRetry">Retry</button>`)}
      <div class="tmJudgeNote">Failure keeps the selection and the queued-count pill, so the curator never loses a call to a dropped request.</div></div>`;
  }
  build();
})();
