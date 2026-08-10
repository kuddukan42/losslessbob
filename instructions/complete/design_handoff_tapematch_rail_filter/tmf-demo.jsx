// Demo shell for the rail filter add-on. Demo chrome only — nothing here ships.
(() => {
  const DATES = window.TMF_DATA;
  const { TMFRail } = window;

  function Card({ title, children }) {
    return <div className="tmfCard"><div className="tmfCardH">{title}</div>{children}</div>;
  }
  function Row({ k, children }) { return <div className="tmfRow"><span className="k">{k}</span><span>{children}</span></div>; }

  function App() {
    const [active, setActive] = React.useState("2001-11-19");
    const rec = DATES.find((d) => d.date === active);
    return (
      <div className="tmApp">
        <header className="tmTop">
          <span className="tmCrumb">LosslessBob <span className="dim">/</span> Library <span className="dim">/</span> TapeMatch <span className="dim">/</span> <strong>Rail filter add-on</strong></span>
          <span className="tmTopSub">Change package — the left rail only. The curation screen itself is untouched.</span>
          <span className="tmTopRight"><span className="tmCrawl"><span className="tmStDot" style={{ background: "var(--ok-bar)" }}></span> {DATES.length.toLocaleString()} dates loaded · windowed</span></span>
        </header>
        <div className="tmBody">
          <TMFRail dates={DATES} active={active} onActivate={(d) => setActive(d.date)} />
          <div className="tmfDoc">
            <div className="tmfDocIn">
              <div>
                <div className="tmfDocH">Finding one date in {DATES.length.toLocaleString()}</div>
                <div className="tmfDocSub">The rail today lists the queue and four status chips — fine for a dozen dates, unusable at crawl scale. This add-on layers three cheap moves on top of it: <strong>type what you remember</strong>, <strong>drag the years you care about</strong>, <strong>scroll a list that stays grouped</strong>. Row markup, chips, tokens, spacing and keyboard verbs are unchanged; the rail is still 272px wide.</div>
              </div>
              <div className="tmfGrid">
                <div className="tmfStat"><div className="tmfStatN">1 field</div><div className="tmfStatL">query bar parses dates, years, decades, cities and status words from one string</div></div>
                <div className="tmfStat"><div className="tmfStatN">64 bars</div><div className="tmfStatL">year brush — drag to scope, click a decade chip, bars re-weight as you type</div></div>
                <div className="tmfStat"><div className="tmfStatN">~20 rows</div><div className="tmfStatL">in the DOM at any time, regardless of queue size</div></div>
              </div>
              <Card title="Query grammar — one field, no operators to learn">
                <div className="tmfRows">
                  <Row k="boston">substring on city + date</Row>
                  <Row k="1974">whole year</Row>
                  <Row k="70s · '74">decade / short year</Row>
                  <Row k="1974-05">month prefix</Row>
                  <Row k="5/17">any year, that month + day</Row>
                  <Row k="conflict">status word (also <span className="mono">status:review</span>)</Row>
                  <Row k="74 boston conflict">terms AND together</Row>
                </div>
              </Card>
              <Card title="Behaviour">
                <div className="tmfRows">
                  <Row k="Chips">unchanged — Needs you / Conflicts / All / Done, applied before the query</Row>
                  <Row k="Histogram">counts reflect chips + query, so bars show where your text actually lands; the warm segment is the needs-you share</Row>
                  <Row k="Year brush">pointer-drag across bars sets a range; decade chips set one; × clears</Row>
                  <Row k="Grouping">sticky-free year headers with per-year counts, so scrolling never loses context</Row>
                  <Row k="Result bar">live “N of {DATES.length.toLocaleString()}”, sort flip, one-click reset</Row>
                  <Row k="Keys"><kbd>/</kbd> focus search · <kbd>j</kbd>/<kbd>k</kbd> move (also while typing, via arrows) · <kbd>⏎</kbd> open · <kbd>esc</kbd> clears then blurs</Row>
                </div>
              </Card>
              <Card title="Drop-in — three new files, two edits">
                <div className="tmfCode"><span className="cm">{"// TapeMatch Curation.html — add three lines\n"}</span><span className="add">{'+ <link rel="stylesheet" href="tmf.css">\n'}</span><span className="add">{'+ <script src="tmf-data.js"><\/script>            '}</span><span className="cm">{"// real queue index\n"}</span><span className="add">{'+ <script type="text/babel" src="tmf-rail.jsx"><\/script>\n\n'}</span><span className="cm">{"// tm-app.jsx — swap the rail, delete the local Rail + cursor plumbing\n"}</span><span className="del">{"- <Rail filter={filter} setFilter={setFilter} active={active} setActive={setActive}\n-       narrow={narrowRail} cursor={cursor} setCursor={setCursor} listRef={listRef} />\n"}</span><span className="add">{"+ <TMFRail dates={QUEUE} active={active} onActivate={(d) => setActive(d.date)}\n+          narrow={narrowRail} />"}</span></div>
                <div className="tmfDocSub">The add-on owns filter state, cursor state and the <span className="mono">j/k</span> handler, so the matching <span className="mono">useState</span>/<span className="mono">useEffect</span> blocks in <span className="mono">tm-app.jsx</span> come out with it. Everything else in that file stays as written.</div>
              </Card>
              <Card title="Currently open">
                <div className="tmfRows">
                  <Row k="date">{active}</Row>
                  <Row k="location">{rec ? rec.loc : "—"}</Row>
                  <Row k="status">{rec ? rec.status : "—"} · {rec ? `${rec.recs} recordings → ${rec.fams} families` : ""}</Row>
                </div>
                <div className="tmfDocSub">In the real screen this is the argument to <span className="mono">setActive</span> — the main pane and dossier behave exactly as they do today.</div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    );
  }
  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
