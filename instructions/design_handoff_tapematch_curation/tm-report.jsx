// TapeMatch — §11 report.md viewer, rendered against the real on-disk document.
// Q1 = Option B: this styles what tapematch_session.py writes today. The sections are
// Coverage · tapematch output · LB page commentary · Commentary vs tapematch audit.
// A1 = ASCII block split on its own === markers, each a scroll-contained mono panel.
// A2 = rail nests those markers as sub-entries; countless entries carry no count; absent
//      sections drop out rather than render disabled.
// A3 = Coverage's summary line becomes a stat row; not-found rows are a warn variant.
(() => {
  const { parseReport } = window.TMParse;
  const DOCS = window.TMDOCS;
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  // blocks that carry a curation signal open by default; the rest are one line + a count
  const OPEN_BY_DEFAULT = ["DIAGNOSTICS", "CLUSTERS"];
  const TOK = /(\[(?:[A-Z][A-Z ?]*|low confidence)\])/;
  const TOK_TONE = (t) => /INCOMPLETE|LOW CONFIDENCE/i.test(t) ? "warn" : /DISTINCT SOURCE/i.test(t) ? "info" : "mute";

  const asciiLine = (l, k) => {
    const parts = l.split(TOK);
    return <React.Fragment key={k}>{parts.map((p, n) => TOK.test(p) && p.startsWith("[")
      ? <span key={n} className={"rpTok " + TOK_TONE(p)}>{p}</span> : p)}{"\n"}</React.Fragment>;
  };

  // ── A1 — one === block ──────────────────────────────────────────────────────
  function AsciiBlock({ blk, open, onToggle, id }) {
    const n = blk.content.length;
    if (blk.single) return (
      <div className="rpAsciiBlk inline" id={id}>
        <span className="rpAsciiLbl">{blk.label}</span>
        <span className="rpAsciiInlineVal">{blk.content[0].trim()}</span>
      </div>
    );
    return (
      <div className={"rpAsciiBlk" + (open ? " open" : "")} id={id}>
        <button className="rpAsciiBtn" onClick={onToggle} aria-expanded={open}>
          <span className="rpAsciiCar">{open ? "▾" : "▸"}</span>
          <span className="rpAsciiLbl">{blk.label}</span>
          <span className="rpAsciiN">{n} line{n > 1 ? "s" : ""}{blk.wide > 110 ? " · " + blk.wide + " cols" : ""}</span>
          {!open && <span className="rpAsciiPeek">{blk.content[0].trim()}</span>}
        </button>
        {open && <div className="rpAsciiPre" tabIndex={0}><pre>{blk.lines.map(asciiLine)}</pre></div>}
      </div>
    );
  }

  // ── the document ────────────────────────────────────────────────────────────
  function RealDoc({ date, judgments = {}, docRef, onOpenRec }) {
    const doc = React.useMemo(() => parseReport(DOCS[date].report), [date]);
    const [openBlk, setOpenBlk] = React.useState(() => {
      const s = {}; doc.ascii.forEach((b, i) => { s[i] = b.single || OPEN_BY_DEFAULT.includes(b.label); }); return s;
    });
    React.useEffect(() => {
      const s = {}; doc.ascii.forEach((b, i) => { s[i] = b.single || OPEN_BY_DEFAULT.includes(b.label); }); setOpenBlk(s);
    }, [date]);
    // print expands every block — a collapsed panel would silently drop lines from the PDF
    React.useEffect(() => {
      const all = () => { const s = {}; doc.ascii.forEach((b, i) => { s[i] = true; }); setOpenBlk(s); };
      window.addEventListener("beforeprint", all);
      return () => window.removeEventListener("beforeprint", all);
    }, [doc]);
    const allOpen = doc.ascii.every((b, i) => openBlk[i]);
    const missing = doc.coverage.rows.filter((r) => r.missing);

    return (
      <div className="rpDoc" ref={docRef}>
        <div className="rpDocIn">
          <div className="rpPrintHead"><strong>report.md</strong><span>{doc.date}</span><span>·</span><span>LosslessBob TapeMatch</span></div>
          <h1 className="rpH1">tapematch session — {doc.date} — {doc.loc}</h1>
          <div className="rpMeta"><span>generated {doc.generated}</span></div>

          {/* ── A3 — Coverage ─────────────────────────────────────────────── */}
          <h2 className="rpH2" id="rp-coverage">Coverage<span className="rpH2N">{doc.coverage.rows.length}</span></h2>
          <div className="rpCov">
            <span className="rpCovStat"><b>{doc.coverage.entries}</b> DB entries</span>
            <span className="rpCovSep">·</span>
            <span className="rpCovStat"><b>{doc.coverage.found}</b> found on disk</span>
            {missing.length > 0 && <span className="rpCovMiss">{missing.length} not on disk — {missing.map((r) => r.lb).join(", ")}</span>}
          </div>
          <table className="rpTable rpCovTable">
            <thead><tr><th>LB</th><th>Rating</th><th>Timing</th><th>Source</th><th>Folder</th></tr></thead>
            <tbody>{doc.coverage.rows.map((r) => (
              <tr key={r.lb} className={r.missing ? "rpMissRow" : ""}>
                <td className="mono rpCovLb">
                  {onOpenRec && !r.missing
                    ? <button className="rpLb" onClick={() => onOpenRec(r.lb)}>{r.lb}</button>
                    : <span className="rpLb static">{r.lb}</span>}
                  {r.missing && <span className="pill sm warn">not on disk</span>}
                </td>
                <td className="mono">{r.rating || <span className="rpNil">·</span>}</td>
                <td className="mono">{r.timing || <span className="rpNil">·</span>}</td>
                <td className="rpCovSrc">{r.src || (r.missing ? <span className="rpNil">no folder found — DB entry only</span> : <span className="rpNil">·</span>)}</td>
                <td className="rpCovFolder">{r.folder || <span className="rpNil">·</span>}</td>
              </tr>))}
            </tbody>
          </table>
          {missing.length > 0 && <p className="rpP rpSmall">A not-on-disk row is a gap in the library, not a failure of this run — the DB knows the recording, the crawl never found audio for it.</p>}

          {/* ── A1 — tapematch output ─────────────────────────────────────── */}
          <h2 className="rpH2" id="rp-tapematch-output">tapematch output
            <span className="rpH2Act"><button className="rpMiniBtn" onClick={() => { const s = {}; doc.ascii.forEach((b, i) => { s[i] = b.single || !allOpen; }); setOpenBlk(s); }}>{allOpen ? "Collapse all" : "Expand all"}</button></span>
          </h2>
          <p className="rpP rpSmall">Verbatim generator output — fixed-width, and it cannot reflow. Each block scrolls on its own; the document never does.</p>
          <div className="rpAscii">
            {doc.ascii.map((b, i) => (
              <AsciiBlock key={b.label + i} blk={b} id={"rp-ascii-" + slug(b.label)} open={!!openBlk[i]}
                onToggle={() => setOpenBlk((s) => ({ ...s, [i]: !s[i] }))} />
            ))}
          </div>

          {/* ── A8 — LB page commentary ───────────────────────────────────── */}
          <h2 className="rpH2" id="rp-lb-page-commentary">LB page commentary<span className="rpH2N">{doc.commentary.length}</span></h2>
          <div className="rpComms">{doc.commentary.map((c) => <Comm key={c.lb} c={c} onOpenRec={onOpenRec} />)}</div>

          {/* ── audit — only when the generator wrote one ─────────────────── */}
          {doc.audit && (
            <React.Fragment>
              <h2 className="rpH2" id="rp-commentary-vs-tapematch-audit">Commentary vs tapematch audit<span className="rpH2N">{doc.audit.rows.length}</span></h2>
              <p className="rpP">Where the LB page and TapeMatch disagree about a pair. Present only when there is a disagreement to record.</p>
              <table className="rpTable">
                <thead><tr><th>Pair</th><th>Verdict</th><th>Commentary snippet</th></tr></thead>
                <tbody>{doc.audit.rows.map((r) => (
                  <tr key={r.pair}>
                    <td className="mono">{r.pair}</td>
                    <td>{r.disagrees ? <span className="pill sm bad">disagrees</span> : <span className="pill sm mute">agrees</span>}<div className="rpAuditTx">{r.verdict.replace(/^\S+\s*—\s*/, "")}</div></td>
                    <td className="rpAuditSnip">{r.snippet}</td>
                  </tr>))}
                </tbody>
              </table>
            </React.Fragment>
          )}

          <div className="rpFoot">Generated by tapematch_session.py · {doc.date}<br />Source of truth is observations.db; this file is a rendering of it.</div>
        </div>
      </div>
    );
  }

  // A8 — clamp to three lines, never clean the text
  function Comm({ c, onOpenRec }) {
    const [open, setOpen] = React.useState(false);
    const long = c.body.length > 240;
    return (
      <div className="rpComm">
        <div className="rpCommHead">
          {onOpenRec ? <button className="rpLb" onClick={() => onOpenRec(c.lb)}>{c.lb}</button> : <span className="rpLb static">{c.lb}</span>}
          {c.metaRaw.map((m, i) => <span key={i} className="rpCommMeta">{m}</span>)}
        </div>
        <div className={"rpCommBody" + (open || !long ? " full" : "")}>{c.body}</div>
        {long && <button className="rpMore" onClick={() => setOpen(!open)}>{open ? "Show less" : "Show more"}</button>}
      </div>
    );
  }

  // ── A2 — outline built from the document, not from a fixed list ─────────────
  function Outline({ date, sec, onJump, judged }) {
    const doc = React.useMemo(() => parseReport(DOCS[date].report), [date]);
    const items = [
      { id: "coverage", label: "Coverage", n: doc.coverage.rows.length },
      { id: "tapematch-output", label: "tapematch output", subs: (() => {
        const shortOf = (l) => l.replace(/\s*\(.*$/, "");
        const counts = {}; doc.ascii.forEach((b) => { counts[shortOf(b.label)] = (counts[shortOf(b.label)] || 0) + 1; });
        return doc.ascii.map((b) => ({ id: "ascii-" + slug(b.label), label: counts[shortOf(b.label)] > 1 ? b.label.replace(/^(\S+[^(]*)\((.{0,26}).*$/, "$1($2…)") : shortOf(b.label) }));
      })() },
      { id: "lb-page-commentary", label: "LB page commentary", n: doc.commentary.length },
    ];
    if (doc.audit) items.push({ id: "commentary-vs-tapematch-audit", label: "Commentary vs tapematch audit", n: doc.audit.rows.length });
    return (
      <nav className="rpOutline">
        <div className="rpOutTitle">Contents</div>
        {items.map((it) => (
          <React.Fragment key={it.id}>
            <button className={"rpOutLink" + (sec === it.id ? " on" : "")} onClick={() => onJump(it.id)}>
              {it.label}{it.n != null && <span className="rpOutN">{it.n}</span>}
            </button>
            {it.subs && it.subs.map((s) => (
              <button key={s.id} className={"rpOutLink sub" + (sec === s.id ? " on" : "")} onClick={() => onJump(s.id)}>{s.label}</button>
            ))}
          </React.Fragment>
        ))}
        {judged > 0 && <button className={"rpOutLink" + (sec === "judgments" ? " on" : "")} onClick={() => onJump("judgments")}>Your judgments<span className="rpOutN">{judged}</span></button>}
      </nav>
    );
  }

  // ── overlay shell ───────────────────────────────────────────────────────────
  function Report({ judgments = {}, onClose, onOpenRec, date = "1991-02-13" }) {
    const [mode, setMode] = React.useState("rendered");
    const [sec, setSec] = React.useState("coverage");
    const docRef = React.useRef(null);
    const judged = Object.entries(judgments).filter(([, v]) => v);
    const src = DOCS[date].report;

    const jump = (id) => {
      setSec(id);
      const box = docRef.current, el = box && box.querySelector("#rp-" + id);
      if (el) box.scrollTop = el.offsetTop - box.offsetTop - 14;
    };

    return (
      <div className="rpWrap">
        <div className="rpScrim" onClick={onClose}></div>
        <div className="rpSheet" role="dialog" aria-label="report.md">
          <div className="rpHead">
            <div className="rpFile">
              <span className="rpFileName">report.md</span>
              <span className="rpPath">data/tapematch/runs/{date}/</span>
            </div>
            <div className="rpHeadR">
              <div className="rpSeg">
                {["rendered", "raw"].map((m) => (
                  <button key={m} className={"rpSegBtn" + (mode === m ? " on" : "")} onClick={() => setMode(m)}>{m === "raw" ? "Raw" : "Rendered"}</button>
                ))}
              </div>
              <button className="rpIcoBtn">Copy</button>
              <button className="rpIcoBtn">Download</button>
              <button className="rpIcoBtn" onClick={() => window.print()}>Print</button>
              <button className="rpClose" onClick={onClose} aria-label="Close">✕</button>
            </div>
          </div>
          {judged.length > 0 && (
            <div className="rpStale">
              <span className="tmStDot" style={{ background: "var(--warn-bar)" }}></span>
              {judged.length} human judgment{judged.length > 1 ? "s" : ""} recorded since this report was generated — it doesn't reflect them yet.
              <span className="rpStaleAct"><button className="btn ghost" style={{ padding: "3px 9px" }}>Regenerate</button></span>
            </div>
          )}
          <div className="rpBody">
            <Outline date={date} sec={sec} onJump={jump} judged={judged.length} />
            {mode === "rendered"
              ? <RealDoc date={date} judgments={judgments} docRef={docRef} onOpenRec={onOpenRec} />
              : <div className="rpRaw"><div className="rpRawIn">
                  <div className="rpGut">{src.split("\n").map((_, i) => (i + 1) + "\n")}</div>
                  <div className="rpSrc">{src}</div>
                </div></div>}
          </div>
        </div>
      </div>
    );
  }

  Object.assign(window, { TMReport: Report, TMRealDoc: RealDoc, TMRealOutline: Outline });
})();
