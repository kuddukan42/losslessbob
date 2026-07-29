// Design answers rendered against the real documents in real_output/.
// Left: §7 as it parses analysis.md. Right: §11 as it renders report.md.
(() => {
  const { parseAnalysis } = window.TMParse;
  const { TMVerdictCards, TMRealDoc, TMRealOutline } = window;
  const CASES = [
    { date: "2018-08-26", label: "clean", tone: "ok", note: "A6 — no verdict cards at all. The common case." },
    { date: "1991-02-13", label: "five-card", tone: "warn", note: "A1 — the ASCII block is two thirds of the document." },
    { date: "1987-09-26", label: "conflict + audit", tone: "bad", note: "A5 — MISS card. A2 — the audit section exists here only." },
    { date: "1993-06-27", label: "ref-only stack", tone: "info", note: "B1.1 — 11 headline-less cards, then 9 conventional ones." },
    { date: "1998-06-14", label: "title-only + conflict", tone: "bad", note: "B1.2 — Coverage gap is a statement, not a card. B2 — two bad-tier disagreements." },
    { date: "1996-07-13", label: "family + audit table", tone: "bad", note: "B1.2/B2/B3 — Audit table statement, family-subject card, 316-char verdict clamped." },
  ];
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  function App() {
    const [date, setDate] = React.useState("1991-02-13");
    const [mode, setMode] = React.useState("rendered");
    const [sec, setSec] = React.useState("coverage");
    const [vOpen, setVOpen] = React.useState(false);
    const docRef = React.useRef(null);
    const cs = CASES.find((c) => c.date === date);
    const an = React.useMemo(() => parseAnalysis(window.TMDOCS[date].analysis), [date]);
    const clean = an.cards.length === 0 ? an.epilogue.join(" ") : null;
    const long = an.verdict.length > 160;
    const jump = (id) => {
      setSec(id); setMode("rendered");
      const box = docRef.current, el = box && box.querySelector("#rp-" + id);
      if (el) box.scrollTop = el.offsetTop - box.offsetTop - 14;
    };

    return (
      <div className="tmApp">
        <div className="tmTop">
          <div className="tmCrumb"><strong>Design answers A1–A9</strong> · rendered against real_output/</div>
          <div className="tmRailFilters" style={{ margin: 0 }}>
            {CASES.map((c) => (
              <button key={c.date} className={"chip" + (c.date === date ? " on" : "")} onClick={() => { setDate(c.date); setSec("coverage"); setVOpen(false); }}>
                {c.date} · {c.label}
              </button>
            ))}
          </div>
          <div className="tmTopRight"><span className="tmTopSub">{cs.note}</span></div>
        </div>
        <div className="tmBody">
          <div className="rdLeft">
            <div className="tmDateHead" style={{ padding: "14px 18px 12px" }}>
              <div>
                <div className="tmDateHeadTop"><span className="tmDateBig">{an.date}</span><span className="tmVenue">{an.loc}</span></div>
                <div className="tmVerdictLine">
                  <span className={"pill " + cs.tone}>{cs.label}</span>
                  <span className={"tmVerdictTx" + (long && !vOpen ? " clamp" : "")}>{an.verdict}</span>
                  {long && <button className="tmVerdictMore" onClick={() => setVOpen(!vOpen)}>{vOpen ? "less" : "more"}</button>}
                </div>
                <div className="tmModel" style={{ marginTop: 6 }}>analysis.md · {an.model} · {an.ran}</div>
              </div>
            </div>
            <div className="rdLeftBody">
              <div className="tmSection" style={{ marginTop: 4 }}>
                <div className="tmSecHead"><span className="tmSecTitle">§7 Analysis verdict</span><span className="tmSecHint">parsed from analysis.md</span></div>
                <TMVerdictCards cards={an.cards} clean={clean} notOnDisk={an.notOnDisk} algoNote={an.algoNote} onOpenRef={() => {}} />
              </div>
              <div className="tmSection">
                <div className="tmSecHead"><span className="tmSecTitle">Coverage table</span><span className="tmSecHint">analysis.md's own copy</span></div>
                <table className="rpTable">
                  <thead><tr>{an.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>{an.rows.map((r) => (
                    <tr key={r.lb}><td className="mono">{r.lb}</td><td className="mono">{r.rating || <span className="rpNil">·</span>}</td>
                      <td className="mono">{r.timing || <span className="rpNil">·</span>}</td>
                      <td className="rpCovSrc">{r.src}</td><td className="mono">{r.fam}</td>
                      <td style={{ fontSize: 10.5, color: "var(--warn-fg)" }}>{r.notes}</td></tr>))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="rdRight">
            <div className="rpSheet rdSheet">
              <div className="rpHead">
                <div className="rpFile">
                  <span className="rpFileName">report.md</span>
                  <span className="rpPath">real_output/{date}_report.md</span>
                </div>
                <div className="rpHeadR">
                  <div className="rpSeg">{["rendered", "raw"].map((m) => (
                    <button key={m} className={"rpSegBtn" + (mode === m ? " on" : "")} onClick={() => setMode(m)}>{m === "raw" ? "Raw" : "Rendered"}</button>))}
                  </div>
                  <button className="rpIcoBtn" onClick={() => window.print()}>Print</button>
                </div>
              </div>
              <div className="rpBody">
                <TMRealOutline date={date} sec={sec} onJump={jump} judged={0} />
                {mode === "rendered"
                  ? <TMRealDoc key={date} date={date} docRef={docRef} />
                  : <div className="rpRaw"><div className="rpRawIn">
                      <div className="rpGut">{window.TMDOCS[date].report.split("\n").map((_, i) => (i + 1) + "\n")}</div>
                      <div className="rpSrc">{window.TMDOCS[date].report}</div>
                    </div></div>}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
