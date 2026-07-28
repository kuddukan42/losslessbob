// TapeMatch curation — visual parts
(() => {
  const { FAM, REC, pair, short, THRESH } = window.TM;
  const M = "var(--mono)";

  // ── similarity matrix, family-ordered ──────────────────────────────────────
  function Matrix({ sel, onSel }) {
    const n = REC.length;
    return (
      <div className="tmMatrixWrap">
        <div className="tmMatrix" style={{ gridTemplateColumns: `52px repeat(${n}, minmax(0,1fr))` }}>
          <div></div>
          {REC.map((r) => (
            <div key={"h"+r.lb} className="tmMxHead" title={r.lb}>
              <span className="tmFamDot" style={{ background: FAM[r.fam] }}></span>
              <span>{short(r.lb)}</span>
            </div>
          ))}
          {REC.map((a, i) => (
            <React.Fragment key={"r"+a.lb}>
              <div className="tmMxRowHead">
                <span>{short(a.lb)}</span>
                <span className="tmFamDot" style={{ background: FAM[a.fam] }}></span>
              </div>
              {REC.map((b, j) => {
                if (i === j) return <div key={a.lb+b.lb} className="tmCell tmCellDiag"></div>;
                const p = pair(a.lb, b.lb);
                const sameFam = a.fam === b.fam;
                const isSel = sel && ((sel[0]===i&&sel[1]===j)||(sel[0]===j&&sel[1]===i));
                const dim = sel && !isSel && sel[0]!==i && sel[1]!==i && sel[0]!==j && sel[1]!==j;
                let bg, color = "var(--fg3)", fw = 500;
                if (p.sim == null) bg = "repeating-linear-gradient(45deg, var(--surface2), var(--surface2) 4px, var(--surface) 4px, var(--surface) 8px)";
                else if (sameFam) { bg = `color-mix(in oklab, ${FAM[a.fam]} ${30 + p.sim*0.55}%, var(--surface))`; color = "var(--fg)"; fw = 700; }
                else { const t = Math.pow(p.sim/100, 0.8)*72; bg = `color-mix(in oklab, var(--accent) ${t.toFixed(0)}%, var(--surface))`; if (p.sim >= 45) color = "var(--fg)"; }
                return (
                  <button key={a.lb+b.lb} className={"tmCell" + (isSel ? " sel" : "") + (p.conflict ? " conflict" : "")}
                    style={{ background: bg, color, fontWeight: fw, opacity: dim ? 0.3 : 1 }}
                    title={`${a.lb} × ${b.lb}` + (p.sim==null ? " — not comparable" : ` — ${p.sim}%`)}
                    onClick={() => onSel(isSel ? null : [i, j])}>
                    {p.sim == null ? <span className="tmNc">n/c</span> : p.sim}
                    {p.conflict && <span className="tmConfDot"></span>}
                  </button>
                );
              })}
            </React.Fragment>
          ))}
        </div>
        <div className="tmMxLegend">
          <span className="lgSwatch" style={{ background: "color-mix(in oklab, var(--accent) 12%, var(--surface))" }}></span> unrelated 0–40
          <span className="lgSwatch" style={{ background: "color-mix(in oklab, var(--accent) 55%, var(--surface))" }}></span> check 40–85
          <span className="lgSwatch" style={{ background: FAM[1] }}></span> same family 85–100 · tinted by family
          <span className="lgSwatch" style={{ background: "repeating-linear-gradient(45deg, var(--surface2), var(--surface2) 3px, var(--surface) 3px, var(--surface) 6px)" }}></span> n/c not comparable
          <span className="lgConf"><span className="tmConfDot static"></span> LB-page conflict</span>
        </div>
      </div>
    );
  }

  // ── evidence bar ────────────────────────────────────────────────────────────
  function EvBar({ label, value, max = 1, thresh, band, demote, note, unit }) {
    const pct = value == null ? 0 : Math.min(100, (value / max) * 100);
    return (
      <div className={"tmEv" + (demote ? " demote" : "")}>
        <div className="tmEvTop">
          <span className="tmEvLabel">{label}</span>
          <span className="tmEvVal">{value == null ? "n/c" : value.toFixed(unit === "%" ? 0 : 3) + (unit || "")}</span>
        </div>
        <div className="tmEvTrack">
          {band && <span className="tmEvBand" style={{ left: (band[0]/max)*100 + "%", width: ((band[1]-band[0])/max)*100 + "%" }}></span>}
          {value != null && <span className="tmEvFill" style={{ width: pct + "%" }}></span>}
          {thresh != null && <span className="tmEvThresh" style={{ left: (thresh/max)*100 + "%" }}></span>}
        </div>
        {note && <div className="tmEvNote">{note}</div>}
      </div>
    );
  }

  // ── speed / lag strip ───────────────────────────────────────────────────────
  // A4 — ▤ survives the staircase/splice merge; `insufficient` folds into speed-unknown.
  const KIND_GLYPH = { reference:"◆", aligned:"●", "constant-speed-offset":"●", "staircase/splice":"▤", staircase:"▤", splice:"▤", "speed-unknown":"?", insufficient:"?" };
  const KIND_LABEL = (k) => k === "insufficient" ? "speed-unknown (insufficient)" : k;
  const sym = (p) => Math.sign(p) * Math.sqrt(Math.abs(p));
  function SpeedStrip({ sel, onSelRec }) {
    const vals = REC.map(r => sym(r.ppm));
    const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
    const X = (p) => 4 + ((sym(p) - lo) / span) * 92; // percent
    const ticks = [-1500, 0, 12480];
    // collision-aware lanes: greedy — lowest lane with no dot within label width
    const placed = []; // {x, lane}
    const lane = REC.map((r) => {
      const x = X(r.ppm);
      let L = 0;
      while (placed.some((p) => p.lane === L && Math.abs(p.x - x) < 4.8)) L++;
      placed.push({ x, lane: L });
      return L;
    });
    const maxLane = Math.max(...lane);
    return (
      <div className="tmSpeed">
        <div className="tmSpeedLane" style={{ height: (maxLane + 1) * 34 + 22 }}>
          {ticks.map(t => (
            <span key={t} className="tmTick" style={{ left: X(t) + "%" }}>
              <span className="tmTickLine"></span>
              <span className="tmTickLbl">{t === 0 ? "ref" : (t>0?"+":"−") + Math.abs(t).toLocaleString()}</span>
            </span>
          ))}
          {REC.map((r, i) => (
            <button key={r.lb} className={"tmSpeedDot" + (sel && (sel[0]===i||sel[1]===i) ? " on" : "")}
              style={{ left: X(r.ppm) + "%", top: lane[i] * 34 + 4 }}
              title={`${r.lb} · ${r.ppm>0?"+":""}${r.ppm.toLocaleString()} ppm · ${KIND_LABEL(r.kind)}`}
              onClick={() => onSelRec(i)}>
              <span className="tmSpeedGlyph" style={{ background: FAM[r.fam] }}>{KIND_GLYPH[r.kind]}</span>
              <span className="tmSpeedLb">{short(r.lb)}</span>
            </button>
          ))}
        </div>
        <div className="tmSpeedLegend">
          <span>◆ reference</span><span>● aligned / constant offset</span><span>▤ lag steps — re-tracking or a splice</span>
          <span className="warnTx">? speed-unknown → fingerprint path only</span>
          <span className="tmSpeedAxNote">ppm vs reference · √ scale</span>
        </div>
      </div>
    );
  }

  // ── verdict cards (parsed analysis.md) ──────────────────────────────────────
  // A5 tone comes from the real headline vocabulary (MISS/INCOMPLETE/speed offset).
  // A6 a clean date keeps the section and states the absence in one line, not a card.
  // A7 the ref is quoted from the document verbatim; navigation normalises, display doesn't.
  // B1 — the body carries the finding on a headline-less card, so it gets structure:
  // `label: value` lines become a key/value row, bullets stay bullets, prose stays prose.
  function CardBody({ nt }) {
    const blocks = nt.blocks || (nt.body ? [{ kind: "p", text: nt.body }] : []);
    if (!blocks.length) return null;
    return (
      <div className="tmNoteTx">
        {blocks.map((b, i) => b.kind === "ul"
          ? <ul key={i} className="tmNoteUl">{b.items.map((it, j) => <li key={j}>{it}</li>)}</ul>
          : b.kind === "kv"
            ? <div key={i} className="tmNoteKv">
                <span className="tmNoteKvK">{b.k}</span>
                <span className={b.quote ? "tmNoteKvV quote" : "tmNoteKvV"}>{b.v}</span>
              </div>
            : <p key={i} className="tmNoteP">{b.text}</p>)}
      </div>
    );
  }

  function VerdictCards({ notes, cards, clean, notOnDisk, algoNote, onOpenRef }) {
    const list = cards || notes || [];
    const T = window.TMParse;
    return (
      <div className="tmNotes">
        {list.length === 0 && clean && (
          <div className="tmClean">
            <span className="tmCleanDot"></span>
            <span className="tmCleanTx">{clean}</span>
          </div>
        )}
        {list.map((nt, i) => {
          const tone = nt.tone || (T ? T.tone(nt.head) : "info");
          const head = nt.head && T ? T.cleanHead(nt.head) : nt.head;
          // B1.2 — a heading with no subject is not a finding about a recording. It is a
          // statement about the run, so it takes A6's statement treatment, not a card.
          if (nt.kind === "statement") return (
            <div key={i} className="tmStatement">
              <span className="tmStatementK" style={{ color: `var(--${tone}-fg)` }}>{nt.title}</span>
              {nt.lead && <div className="tmStatementLead">{nt.lead}</div>}
              <CardBody nt={nt} />
            </div>
          );
          const isFam = nt.kind === "family";
          return (
            <div key={i} className={"tmNote" + (head ? "" : " noHead")}>
              <span className="tmNoteBar" style={{ background: `var(--${tone}-bar)` }}></span>
              <div className="tmNoteBody">
                <div className="tmNoteHead">
                  {isFam
                    ? <span className="tmNoteFam mono"><span className="tmNoteFamSw"></span>{nt.ref}</span>
                    : onOpenRef
                      ? <button className="tmNoteRef mono" onClick={() => onOpenRef(nt.ref)} title={"Open " + nt.ref}>{nt.ref}</button>
                      : <span className="mono">{nt.ref}</span>}
                  {/* B1.1 — no headline in the document means no headline here, and no
                      dangling em-dash. Nothing is promoted into the empty slot. */}
                  {head && <React.Fragment><span className="tmNoteDash">—</span>
                    <span style={{ color: `var(--${tone}-fg)` }}>{head}</span></React.Fragment>}
                </div>
                <CardBody nt={nt} />
              </div>
            </div>
          );
        })}
        {notOnDisk && notOnDisk.length > 0 && (
          <div className="tmNoteMeta">Not on disk: {notOnDisk.map((lb, i) => <React.Fragment key={lb}><span className="mono">{lb}</span>{i < notOnDisk.length - 1 ? ", " : ""}</React.Fragment>)} — known to the DB, no audio found by the crawl.</div>
        )}
        {algoNote && <div className="tmNoteMeta algo"><span className="tmNoteMetaK">Algorithm note</span>{algoNote}</div>}
      </div>
    );
  }

  // A9 — the A/B slot reserves the height of its empty-eligible state, so the stack below
  // does not move as you click pair to pair. Loaded state is allowed to grow past it.
  function ABPlayer({ A, B, eligible }) {
    const [loaded, setLoaded] = React.useState(false);
    React.useEffect(() => setLoaded(false), [A.lb, B.lb]);
    return (
      <div className={"tmAB" + (eligible ? "" : " inert")}>
        <div className="tmABTop">
          <span className="tmABTitle">A/B listening</span>
          {!eligible && <span className="pill sm mute">not eligible</span>}
        </div>
        {eligible ? (
          <React.Fragment>
            <div className="tmABRow">
              <label className="tmABF">Position<input className="tmABNum" defaultValue="" placeholder="auto" /></label>
              <label className="tmABF">Duration<input className="tmABNum" defaultValue="20" /></label>
              <button className="btn" style={{ padding: "4px 11px" }} onClick={() => setLoaded(true)}>Load</button>
            </div>
            <div className="tmABHint">Leave position blank to auto-pick a loud aligned moment.</div>
            {loaded && (
              <div className="tmABPlay">
                <button className="btn primary" style={{ padding: "5px 12px" }}>▶ Play</button>
                <button className="tmABChip on">A · {A.lb}</button>
                <button className="tmABChip">B · {B.lb}</button>
              </div>
            )}
          </React.Fragment>
        ) : (
          <div className="tmABInert">Not sample-alignable — the speed offset between these two makes a synced clip pair impossible.</div>
        )}
      </div>
    );
  }

  // ── pair dossier ────────────────────────────────────────────────────────────
  const JUDGMENTS = [
    { k:"confirmed_same", label:"Same source", tone:"ok" },
    { k:"confirmed_different", label:"Different", tone:"info" },
    { k:"uncertain", label:"Uncertain", tone:"warn" },
    { k:"lb_wrong", label:"LB wrong", tone:"bad" },
  ];
  function Dossier({ sel, judgments, onJudge, onClose, drawer }) {
    if (!sel) return (
      <div className="tmDossier empty">
        <div className="tmDossEmpty">
          <div className="tmDossEmptyIcon">⊞</div>
          <div className="tmDossEmptyHead">Select a pair</div>
          <div className="tmDossEmptyTx">Click any matrix cell to open the evidence dossier — every signal TapeMatch measured for that pair, against its threshold.</div>
        </div>
      </div>
    );
    const [i, j] = sel; const A = REC[i], B = REC[j];
    const p = pair(A.lb, B.lb);
    const jd = judgments[p.key];
    const verdict = p.same ? (p.secondary ? { tx:"same family · secondary link", tone:"warn" } : { tx:"same family", tone:"ok" })
      : p.nc ? { tx:"not comparable", tone:"mute" } : { tx:"different family", tone:"info" };
    return (
      <div className={"tmDossier" + (drawer ? " drawer" : "")}>
        <div className="tmDossHead">
          <div className="tmDossPair">
            <span className="tmDossLb"><span className="tmFamDot" style={{ background: FAM[A.fam] }}></span>{A.lb}</span>
            <span className="tmDossX">×</span>
            <span className="tmDossLb"><span className="tmFamDot" style={{ background: FAM[B.fam] }}></span>{B.lb}</span>
          </div>
          {drawer && <button className="tmDossClose" onClick={onClose}>✕</button>}
        </div>
        <div className="tmDossVerdict">
          <div className="tmDossSim">
            <span className="tmDossSimN">{p.sim == null ? "n/c" : p.sim + "%"}</span>
            <span className="tmDossSimL">similarity{p.sim == null ? " — speed ratio unconfident, correlation not comparable" : " · banded blend of corr + embedding"}</span>
          </div>
          <span className={"pill " + verdict.tone}>{verdict.tx}</span>
        </div>
        {p.conflict && (
          <div className="tmConflictBox">
            <strong>Conflict.</strong> LB page says same source; TapeMatch found no acoustic link. This pair is why this date is in the queue.
          </div>
        )}
        <ABPlayer A={A} B={B} eligible={!p.nc && ["reference", "aligned"].includes(A.kind) && ["reference", "aligned"].includes(B.kind)} />
        <div className="tmDossSec">Primary evidence</div>
        <EvBar label="Residual correlation" value={p.corr} thresh={THRESH.corr} note={p.corr == null ? "not measured — speed-unknown source" : p.corr >= THRESH.corr ? "≥ 0.45 cluster threshold — merges on primary evidence" : p.secondary ? "below threshold — that's why the secondary path ran" : "below the 0.45 cluster threshold"} />
        <div className="tmDossSec">Secondary evidence</div>
        <EvBar label="Windowed coverage" value={p.win} thresh={THRESH.win} unit={null} note="fraction of dense 60 s windows correlating — drives secondary clustering" />
        <EvBar label="Quiet-segment hiss corr" value={p.hiss} note="tape hiss survives EQ/NR applied to the music" />
        <EvBar label="Fingerprint dice" value={p.fp} band={[THRESH.fpLo, THRESH.fpHi]} demote
          note="confirmatory only — never groups. Shaded band = 0.15–0.50 coincidence range for two tapers at the same show." />
        <div className="tmDossSec">LB page says</div>
        <div className="tmDossLbSays">
          {p.lbText && p.lbText !== "—" ? (
            <React.Fragment>
              <span className={"pill sm " + (p.conflict ? "bad" : p.lbSays ? "ok" : "mute")}>{p.conflict ? "disagrees" : p.lbSays ? "agrees · same source" : "no claim"}</span>
              <div className="tmDossQuote">{p.lbText}</div>
            </React.Fragment>
          ) : <div className="tmDossQuote muted">No relation claim between these LB numbers on either page.</div>}
        </div>
        <div className="tmDossSec">Your judgment</div>
        <div className="tmJudge">
          {JUDGMENTS.map((o) => (
            <button key={o.k} className={"tmJudgeBtn " + o.tone + (jd === o.k ? " on" : "")} onClick={() => onJudge(p.key, jd === o.k ? null : o.k)}>{o.label}</button>
          ))}
        </div>
        <textarea className="tmJudgeNotes" rows={3} placeholder="notes…"></textarea>
        <div className="tmJudgeNote">Writes <span className="mono">human_judgment</span> + <span className="mono">human_notes</span> to <span className="mono">observations.db · pairs</span> — queued locally in this demo.</div>
      </div>
    );
  }

  Object.assign(window, { TMMatrix: Matrix, TMSpeedStrip: SpeedStrip, TMVerdictCards: VerdictCards, TMDossier: Dossier });
})();
