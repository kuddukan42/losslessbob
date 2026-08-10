// TapeMatch curation — app shell
(() => {
  const { FAM, REC, DATE, NOTES, QUEUE, STATUS, short } = window.TM;
  const { TMMatrix, TMSpeedStrip, TMVerdictCards, TMDossier, TMReport, TMDiff } = window;

  function useMedia(q) {
    const [m, setM] = React.useState(() => window.matchMedia(q).matches);
    React.useEffect(() => {
      const mq = window.matchMedia(q); const fn = () => setM(mq.matches);
      mq.addEventListener("change", fn); return () => mq.removeEventListener("change", fn);
    }, [q]);
    return m;
  }

  const FILTERS = [
    { k:"needs", label:"Needs you" }, { k:"conflict", label:"Conflicts" }, { k:"all", label:"All" }, { k:"curated", label:"Done" },
  ];
  function match(f, d) {
    if (f === "all") return true;
    if (f === "needs") return d.status === "conflict" || d.status === "review";
    if (f === "conflict") return d.status === "conflict";
    return d.status === "curated";
  }

  function Rail({ filter, setFilter, active, setActive, narrow, cursor, setCursor, listRef }) {
    const list = QUEUE.filter((d) => match(filter, d));
    const needs = QUEUE.filter((d) => match("needs", d)).length;
    return (
      <aside className={"tmRail" + (narrow ? " narrow" : "")}>
        <div className="tmRailHead">
          <div className="tmRailTitle">Triage queue <span className="tmRailCount">{needs} need you</span></div>
          <div className="tmRailFilters">
            {FILTERS.map((f) => (
              <button key={f.k} className={"chip" + (filter === f.k ? " on" : "")} onClick={() => setFilter(f.k)}>{f.label}</button>
            ))}
          </div>
        </div>
        <div className="tmRailList" ref={listRef}>
          {list.map((d, i) => {
            const st = STATUS[d.status];
            return (
              <button key={d.date} data-row={i} className={"tmDateRow" + (active === d.date ? " on" : "") + (cursor === i ? " cur" : "")}
                onClick={() => { setCursor(i); setActive(d.date); }}>
                <span className="tmStDot" style={{ background: `var(--${st.tone}-bar)` }}></span>
                <span className="tmDateMain">
                  <span className="tmDateD mono">{d.date}</span>
                  <span className="tmDateLoc">{d.loc}</span>
                </span>
                <span className="tmDateN mono">{d.recs}<span className="dim">→</span><strong>{d.fams}</strong></span>
              </button>
            );
          })}
          {!list.length && <div className="tmRailEmpty">Nothing here.</div>}
        </div>
        <div className="tmRailFoot">
          <span className="dim"><kbd>j</kbd> / <kbd>k</kbd> to move · <kbd>enter</kbd> to open · <kbd>esc</kbd> to close</span>
        </div>
      </aside>
    );
  }

  function DateHeader({ judged, onReport, onDiff }) {
    return (
      <div className="tmDateHead">
        <div className="tmDateHeadL">
          <div className="tmDateHeadTop">
            <span className="tmDateBig mono">{DATE.date}</span>
            <span className="tmVenue">{DATE.venue} · {DATE.loc}</span>
            <button className="pill sm mute mono" style={{ border: "1px solid var(--border)", cursor: "pointer" }} onClick={onDiff} title="Compare with the previous run">run {DATE.run} <span className="dim">· diff</span></button>
          </div>
          <div className="tmVerdictLine">
            <span className={"pill " + DATE.tone}>needs review</span>
            <span className="tmVerdictTx">{DATE.verdict}</span>
            <span className="tmModel mono">{DATE.model} · {DATE.ran}</span>
          </div>
        </div>
        <div className="tmDateHeadR">
          <div className="tmFams">
            {[1,2,3,4,5].map((f) => (
              <span key={f} className="tmFamChip">
                <span className="tmFamDot" style={{ background: FAM[f] }}></span>
                F{f}
                <span className="tmFamMembers mono">{REC.filter(r=>r.fam===f).map(r=>short(r.lb)).join(" ")}</span>
              </span>
            ))}
          </div>
          <div className="tmHeadActions">
            <button className="btn ghost" onClick={onDiff}>Compare runs</button>
            <button className="btn ghost" onClick={onReport}>Open report.md</button>
            <button className="btn primary" disabled={!judged}>Accept families{judged ? ` · ${judged} judged` : ""}</button>
          </div>
        </div>
      </div>
    );
  }

  function Section({ title, hint, children }) {
    return (
      <div className="tmSection">
        <div className="tmSecHead"><span className="tmSecTitle">{title}</span>{hint && <span className="tmSecHint">{hint}</span>}</div>
        {children}
      </div>
    );
  }

  function App() {
    const [filter, setFilter] = React.useState("needs");
    const [active, setActive] = React.useState("2001-11-19");
    const [sel, setSel] = React.useState([0, 5]); // conflict pair pre-selected
    const [judgments, setJudgments] = React.useState({});
    const [report, setReport] = React.useState(false);
    const [diff, setDiff] = React.useState(false);
    const [cursor, setCursor] = React.useState(() => Math.max(0, QUEUE.filter((d) => match("needs", d)).findIndex((d) => d.date === "2001-11-19")));
    const listRef = React.useRef(null);
    const drawer = useMedia("(max-width: 1520px)");
    const narrowRail = useMedia("(max-width: 1380px)");
    const judged = Object.values(judgments).filter(Boolean).length;
    const onJudge = (k, v) => setJudgments((s) => ({ ...s, [k]: v }));
    const featured = QUEUE.find((d) => d.date === active)?.featured;
    const visible = QUEUE.filter((d) => match(filter, d));

    // clamp the cursor whenever the filtered list changes; keep it on the open date if present
    React.useEffect(() => {
      const i = visible.findIndex((d) => d.date === active);
      setCursor((c) => (i > -1 ? i : Math.min(Math.max(c, 0), Math.max(visible.length - 1, 0))));
    }, [filter, active, visible.length]);

    // keep the cursor row in view without scrollIntoView
    React.useEffect(() => {
      const box = listRef.current; if (!box) return;
      const row = box.querySelector(`[data-row="${cursor}"]`); if (!row) return;
      const top = row.offsetTop - box.offsetTop, bottom = top + row.offsetHeight;
      if (top < box.scrollTop) box.scrollTop = top - 6;
      else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 6;
    }, [cursor, filter]);

    React.useEffect(() => {
      const onKey = (e) => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const t = e.target;
        if (t && (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName))) return;
        const step = (d) => { e.preventDefault(); setCursor((c) => Math.min(Math.max(c + d, 0), Math.max(visible.length - 1, 0))); };
        if (e.key === "j" || e.key === "ArrowDown") return step(1);
        if (e.key === "k" || e.key === "ArrowUp") return step(-1);
        if (e.key === "Enter") { const d = visible[cursor]; if (d) { e.preventDefault(); setActive(d.date); } return; }
        if (e.key === "Escape") { if (diff) { e.preventDefault(); setDiff(false); } else if (report) { e.preventDefault(); setReport(false); } else if (sel) { e.preventDefault(); setSel(null); } return; }
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [visible, cursor, sel, report, diff]);

    return (
      <div className="tmApp">
        <header className="tmTop">
          <span className="tmCrumb">LosslessBob <span className="dim">/</span> Library <span className="dim">/</span> <strong>TapeMatch</strong></span>
          <span className="tmTopSub">Curation — review the algorithm's family calls, pair by pair</span>
          <span className="tmTopRight">
            <span className="tmCrawl"><span className="tmStDot" style={{ background:"var(--ok-bar)" }}></span> crawl idle · 2,226 runs · 2,075 dates</span>
            {judged > 0 && <span className="pill sm info">{judged} judgment{judged>1?"s":""} queued</span>}
          </span>
        </header>
        <div className="tmBody">
          <Rail filter={filter} setFilter={setFilter} active={active} setActive={setActive} narrow={narrowRail} cursor={cursor} setCursor={setCursor} listRef={listRef} />
          <main className="tmMain">
            {featured ? (
              <React.Fragment>
                <DateHeader judged={judged} onReport={() => setReport(true)} onDiff={() => setDiff(true)} />
                <div className={"tmWork" + (drawer ? " single" : "")}>
                  <div className="tmWorkL">
                    <Section title="Similarity matrix" hint="family-ordered · % is the banded corr+embedding blend · click a cell for the dossier">
                      <TMMatrix sel={sel} onSel={setSel} />
                    </Section>
                    <Section title="Speed & lag" hint="why a pair's correlation looks the way it does">
                      <TMSpeedStrip sel={sel} onSelRec={(i) => setSel(sel && sel[0] === i ? null : [i, sel && sel[0] !== i ? sel[0] : (i+1) % REC.length])} />
                    </Section>
                    <Section title="Analysis verdict" hint="parsed from analysis.md — the human/AI review layer">
                      <TMVerdictCards notes={NOTES} />
                    </Section>
                  </div>
                  {!drawer && <TMDossier sel={sel} judgments={judgments} onJudge={onJudge} />}
                </div>
                {drawer && sel && <div className="tmScrim" onClick={() => setSel(null)}></div>}
                {drawer && <TMDossier sel={sel} judgments={judgments} onJudge={onJudge} onClose={() => setSel(null)} drawer />}
              </React.Fragment>
            ) : (
              <div className="tmPlaceholder">
                <div className="tmDossEmptyIcon">☰</div>
                <div className="tmDossEmptyHead mono">{active}</div>
                <div className="tmDossEmptyTx">Summary-only in this demo. The featured date — <button className="tmLink" onClick={() => setActive("2001-11-19")}>2001-11-19 New York</button> — carries the full artifact set.</div>
              </div>
            )}
          </main>
        </div>
        <div className="tmPrintNotice">
          <div className="pnHead">Nothing to print yet</div>
          <div className="pnTx">The curation workspace is an interactive screen, not a document. To print or export this date, open <strong>report.md</strong> from the date header and print from there.</div>
          <div className="pnMeta">LosslessBob TapeMatch · curation · {active}</div>
        </div>
        {diff && <TMDiff judgments={judgments} onClose={() => setDiff(false)}
          onOpenPair={(i, j) => { setSel([i, j]); setDiff(false); }} />}
        {report && <TMReport judgments={judgments} onClose={() => setReport(false)}
          onOpenPair={(i, j) => { setSel([i, j]); setReport(false); }}
          onOpenRec={(lb) => { const i = REC.findIndex((r) => r.lb === lb); setSel([i, (i + 1) % REC.length]); setReport(false); }} />}
      </div>
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
