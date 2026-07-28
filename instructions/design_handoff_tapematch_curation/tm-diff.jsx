// TapeMatch — run diff. Compares two analysis runs of the same date.
(() => {
  const { FAM, REC, DATE, pair, short } = window.TM;
  const JLABEL = { confirmed_same:"Same source", confirmed_different:"Different", uncertain:"Uncertain", lb_wrong:"LB wrong" };

  // ── the prior run, as it stood on 2026-04-18 ───────────────────────────────
  // Kept here rather than in tm-data.js: the app's data layer holds the CURRENT
  // run; a real implementation fetches any prior run by id.
  const PREV = {
    run: "20260418_090212", model: "claude-sonnet-4-5", ran: "2026-04-18",
    thresh: { corr: 0.50, win: 0.60, diceGroups: 0.35 },
    // 8 families: staircase and splice lag curves weren't handled, secondary
    // clustering didn't exist, and fingerprint dice could still merge a pair.
    fams: [["LB-11201","LB-11458","LB-11340","LB-11977"],["LB-13022"],["LB-11890"],["LB-12704"],["LB-12455"],["LB-14210"],["LB-14567"]],
    // measured values that moved, keyed like TM.pair
    pairs: {
      "11201|11340": { corr:0.038, win:0.11, fp:0.38, sim:71, same:true },
      "11201|13022": { corr:0.44,  win:0.52, fp:0.55, sim:58, same:false },
      "11458|13022": { corr:0.41,  win:0.49, fp:0.53, sim:55, same:false },
      "11890|12704": { corr:0.19,  win:0.71, fp:0.44, sim:41, same:false },
      "14210|14567": { corr:0.58,  win:0.62, fp:0.51, sim:79, same:true },
      "11340|11977": { corr:0.86,  win:0.94, fp:0.66, sim:97, same:true },
      "11201|11458": { corr:0.94,  win:0.98, fp:0.71, sim:99, same:true },
      "11201|11977": { corr:0.037, win:0.10, fp:0.35, sim:64, same:true },
      "11340|11458": { corr:0.035, win:0.09, fp:0.34, sim:52, same:true },
      "11458|11977": { corr:0.031, win:0.08, fp:0.33, sim:48, same:true },
    },
    causes: [
      ["Fingerprint dice no longer groups.", "Dice ≥ ", "0.35", " used to merge a pair on its own. It is now confirmatory only — this is what surfaced the LB-11201 × LB-11340 conflict."],
      ["Lag curves: staircase and splice handling.", "Re-tracked CDRs and tape-flip splices are now aligned segment by segment instead of whole-file, which raised their residual correlation.", "", ""],
      ["Secondary clustering added.", "Windowed coverage ≥ ", "0.60", " with corroborating quiet-hiss correlation can now merge a pair whose primary correlation is below threshold."],
      ["Primary threshold relaxed.", "Residual correlation cluster threshold moved from ", "0.50 → 0.45", " after the alignment fixes."],
    ],
  };
  Object.keys(PREV.pairs).forEach((k) => {
    const sorted = k.split("|").sort((a, b) => +a - +b).join("|");
    if (k !== sorted) console.warn(`TMDiff: PREV.pairs key "${k}" is not in numerically-sorted form ("${sorted}") and will never match a lookup.`);
  });
  const prevFamOf = (lb) => PREV.fams.findIndex((f) => f.includes(lb)) + 1;
  const prevPair = (a, b) => {
    const k = [short(a), short(b)].sort((x, y) => +x - +y).join("|");
    const v = PREV.pairs[k];
    if (v) return { key: k, ...v };
    const now = pair(a, b);
    return { key: k, corr: now.corr, win: now.win, fp: now.fp, sim: now.sim, same: !!now.same, untouched: true };
  };

  const Delta = ({ from, to, digits = 3, higherBetter = true }) => {
    if (from == null || to == null) return <span className="dfWas">n/c</span>;
    const d = to - from, flat = Math.abs(d) < 0.005;
    return (
      <span className="dfFlow">
        <span className="dfWas">{from.toFixed(digits)}</span><span className="dfTo">→</span>
        <span>{to.toFixed(digits)}</span>
        {!flat && <span className={(d > 0) === higherBetter ? "dfUp" : "dfDown"}>{d > 0 ? "+" : "−"}{Math.abs(d).toFixed(digits)}</span>}
      </span>
    );
  };
  const CallPill = ({ same, secondary }) => (
    <span className={"pill sm " + (same ? (secondary ? "warn" : "ok") : "info")}>{same ? (secondary ? "same · secondary" : "same") : "different"}</span>
  );

  function Diff({ judgments, onClose, onOpenPair }) {
    const [sec, setSec] = React.useState("causes");
    const bodyRef = React.useRef(null);

    // every pair whose call flipped or whose numbers moved
    const changes = [];
    for (let i = 0; i < REC.length; i++) for (let j = i + 1; j < REC.length; j++) {
      const now = pair(REC[i].lb, REC[j].lb), was = prevPair(REC[i].lb, REC[j].lb);
      const flipped = !!now.same !== !!was.same;
      const moved = now.corr != null && was.corr != null && Math.abs(now.corr - was.corr) >= 0.01;
      if (flipped || moved) changes.push({ i, j, now, was, flipped });
    }
    changes.sort((a, b) => (b.flipped - a.flipped) || Math.abs((b.now.corr||0)-(b.was.corr||0)) - Math.abs((a.now.corr||0)-(a.was.corr||0)));

    const nowFams = [1,2,3,4,5].map((f) => ({ f, m: REC.filter((r) => r.fam === f).map((r) => r.lb) }));
    // each base family is inherited by the head family holding most of its members
    // (ties → lowest head family). Head families with no inheritance were carved out.
    const successor = {};
    PREV.fams.forEach((members, pi) => {
      let best = null, bestN = 0;
      nowFams.forEach(({ f, m }) => { const n = m.filter((lb) => members.includes(lb)).length; if (n > bestN) { bestN = n; best = f; } });
      if (best) successor[pi + 1] = best;
    });
    const famDiff = nowFams.map(({ f, m }) => {
      const home = +Object.keys(successor).find((pi) => successor[pi] === f) || null;
      // in a carved-out family nobody "moved in" — the family itself is the change
      const moved = home ? m.filter((lb) => prevFamOf(lb) !== home) : [];
      const gone = home ? PREV.fams[home - 1].filter((lb) => !m.includes(lb)) : [];
      const prevIds = [...new Set(m.map(prevFamOf))];
      const carved = !home;
      const verdict = carved ? "split" : gone.length && prevIds.length > 1 ? "regrouped" : gone.length ? "split" : prevIds.length > 1 ? "merged" : "held";
      const was = carved ? `split out of base F${prevIds[0]}` : gone.length && prevIds.length > 1 ? `regrouped from ${prevIds.length} families`
        : gone.length ? `${gone.length} left for another family` : prevIds.length > 1 ? `was ${prevIds.length} families` : "unchanged";
      return { f, m, home, moved, gone, verdict, was };
    });
    const merged = famDiff.filter((f) => f.verdict === "merged" || f.verdict === "regrouped").length;
    const splits = famDiff.filter((f) => f.verdict === "split" || f.verdict === "regrouped").length;
    const judged = Object.entries(judgments).filter(([, v]) => v);
    const impacts = judged.map(([k, v]) => {
      const [a, b] = k.split("|"); const now = pair("LB-" + a, "LB-" + b), was = prevPair("LB-" + a, "LB-" + b);
      const flipped = !!now.same !== !!was.same;
      const claimsSame = v === "confirmed_same";
      const agreesNow = claimsSame === !!now.same;
      return { k, a, b, v, flipped, agreesNow,
        tone: flipped ? (agreesNow ? "ok" : "bad") : "mute",
        tx: !flipped ? "The algorithm's call for this pair didn't change between runs — your judgment still stands against the same evidence."
          : agreesNow ? "The algorithm flipped its call and now agrees with you. Your judgment is corroborated; nothing to redo."
          : "The algorithm flipped its call and now contradicts you. This judgment was recorded against the older run — re-examine it." };
    });

    const OUT = [["causes","What changed in the pipeline"],["families","Families",`${PREV.fams.length} → ${nowFams.length}`],
      ["matrix","Similarity delta"],["pairs","Pair changes",changes.length],["judgments","Your judgments",judged.length || null]];
    const jump = (id) => { setSec(id); const box = bodyRef.current, el = box && box.querySelector("#df-" + id); if (el) box.scrollTop = el.offsetTop - box.offsetTop - 14; };

    return (
      <div className="rpWrap">
        <div className="rpScrim" onClick={onClose}></div>
        <div className="rpSheet" role="dialog" aria-label="Run diff">
          <div className="rpHead">
            <div className="rpFile">
              <span className="rpFileName">Run diff</span>
              <span className="rpPath">{DATE.date} · {DATE.venue}</span>
            </div>
            <div className="rpHeadR">
              <button className="rpIcoBtn">Export diff</button>
              <button className="rpClose" onClick={onClose} aria-label="Close">✕</button>
            </div>
          </div>
          <div className="rpBody">
            <nav className="rpOutline">
              <div className="rpOutTitle">Sections</div>
              {OUT.map(([id, label, n]) => (
                <button key={id} className={"rpOutLink" + (sec === id ? " on" : "")} onClick={() => jump(id)}>{label}{n != null && <span className="rpOutN">{n}</span>}</button>
              ))}
            </nav>
            <div className="rpDoc" ref={bodyRef}>
              <div className="rpDocIn">
                <div className="dfRunbar">
                  <div className="dfRun">
                    <div className="dfRunK">Base — earlier run</div>
                    <div className="dfRunSel"><span className="dfRunId">{PREV.run}</span><span className="pill sm mute">superseded</span></div>
                    <div className="dfRunMeta">{PREV.model} · {PREV.ran}<br />corr ≥ <b>{PREV.thresh.corr}</b> · win ≥ <b>{PREV.thresh.win}</b> · dice groups ≥ <b>{PREV.thresh.diceGroups}</b></div>
                  </div>
                  <div className="dfArrow">→</div>
                  <div className="dfRun head">
                    <div className="dfRunK">Head — current run</div>
                    <div className="dfRunSel"><span className="dfRunId">{DATE.run}</span><span className="pill sm info">in review</span></div>
                    <div className="dfRunMeta">{DATE.model} · {DATE.ran}<br />corr ≥ <b>0.45</b> · win ≥ <b>0.60</b> · dice <b>confirmatory only</b></div>
                  </div>
                </div>

                <div className="dfStats">
                  <div className="dfStat ok"><div className="dfStatN">{PREV.fams.length}→{nowFams.length}</div><div className="dfStatL">families · {merged} merged · {splits} split</div></div>
                  <div className="dfStat warn"><div className="dfStatN">{changes.filter((c) => c.flipped).length}</div><div className="dfStatL">calls flipped</div></div>
                  <div className="dfStat mute"><div className="dfStatN">{changes.filter((c) => !c.flipped).length}</div><div className="dfStatL">values moved, call held</div></div>
                  <div className={"dfStat " + (impacts.some((i) => i.tone === "bad") ? "bad" : "mute")}><div className="dfStatN">{impacts.filter((i) => i.tone === "bad").length}</div><div className="dfStatL">judgment{impacts.filter((i) => i.tone === "bad").length === 1 ? "" : "s"} to re-examine</div></div>
                </div>

                <h2 className="rpH2" id="df-causes">What changed in the pipeline</h2>
                <p className="rpP">Same audio, same recordings — every difference below comes from the analysis, not the tapes. Read this section first; it explains every change that follows.</p>
                <div className="dfCause">
                  <div className="dfCauseH"><span className="tmStDot" style={{ background: "var(--info-bar)" }}></span>4 pipeline changes between these runs</div>
                  <ul className="dfCauseL">
                    {PREV.causes.map(([h, t1, code, t2], i) => (
                      <li key={i}><b style={{ color: "var(--fg)" }}>{h}</b> {t1}{code && <code>{code}</code>}{t2}</li>
                    ))}
                  </ul>
                </div>

                <h2 className="rpH2" id="df-families">Families<span className="rpH2N">{PREV.fams.length} → {nowFams.length}</span></h2>
                <p className="rpP">Membership as it stands now, marked against the earlier run. <span style={{ color: "var(--ok-fg)" }}>+ moved in</span> from another family, <span style={{ color: "var(--bad-fg)" }}>− left</span> for another one; unmarked members were already together. A family carved out of a larger one reads as <b style={{ color: "var(--warn-fg)" }}>split</b>.</p>
                <div className="dfFams">
                  {famDiff.map(({ f, m, moved, gone, verdict, was }) => (
                    <div key={f} className="dfFamRow">
                      <div>
                        <div className="dfFamId"><span className="tmFamDot" style={{ background: FAM[f] }}></span>F{f}</div>
                        <div className="dfFamWas">{was}</div>
                      </div>
                      <div className="dfMembers">
                        {m.map((lb) => (
                          <span key={lb} className={"dfChip" + (moved.includes(lb) ? " moved" : "")}>{moved.includes(lb) && <span className="dfChipMk">+</span>}{short(lb)}</span>
                        ))}
                        {gone.map((lb) => (
                          <span key={lb} className="dfChip gone" title={`${lb} left this family — now in F${REC.find((r) => r.lb === lb).fam}`}><span className="dfChipMk">−</span>{short(lb)}</span>
                        ))}
                      </div>
                      <div><span className={"pill sm " + (verdict === "held" ? "mute" : verdict === "merged" ? "ok" : "warn")}>{verdict}</span></div>
                    </div>
                  ))}
                </div>
                <p className="rpP rpSmall">No recording changed identity, appeared, or disappeared between these runs. When that does happen, added recordings render as a family row of their own and removed ones stay visible struck through.</p>

                <h2 className="rpH2" id="df-matrix">Similarity delta</h2>
                <p className="rpP">The same matrix, showing <b style={{ color: "var(--fg)" }}>change</b> instead of value: how many points each pair's similarity moved. Cells ringed in white are calls that flipped.</p>
                <div className="dfMxWrap">
                  <div className="dfMx" style={{ gridTemplateColumns: `52px repeat(${REC.length},minmax(0,1fr))` }}>
                    <div></div>
                    {REC.map((r) => (
                      <div key={"h"+r.lb} className="tmMxHead" title={r.lb}><span className="tmFamDot" style={{ background: FAM[r.fam] }}></span><span>{short(r.lb)}</span></div>
                    ))}
                    {REC.map((a, i) => (
                      <React.Fragment key={"r"+a.lb}>
                        <div className="tmMxRowHead"><span>{short(a.lb)}</span><span className="tmFamDot" style={{ background: FAM[a.fam] }}></span></div>
                        {REC.map((b, j) => {
                          if (i === j) return <div key={a.lb+b.lb} className="tmCell tmCellDiag"></div>;
                          const now = pair(a.lb, b.lb), was = prevPair(a.lb, b.lb);
                          if (now.sim == null || was.sim == null) return <div key={a.lb+b.lb} className="dfCell flat" title="not comparable in one or both runs"
                            style={{ background: "repeating-linear-gradient(45deg, var(--surface2), var(--surface2) 4px, var(--surface) 4px, var(--surface) 8px)", cursor: "default" }}>n/c</div>;
                          const d = now.sim - was.sim, flipped = !!now.same !== !!was.same;
                          const t = Math.min(72, Math.abs(d) * 2.4);
                          const bg = Math.abs(d) < 1 ? "var(--surface)" : `color-mix(in oklab, var(--${d > 0 ? "ok" : "bad"}-bar) ${t.toFixed(0)}%, var(--surface))`;
                          return (
                            <button key={a.lb+b.lb} className={"dfCell" + (flipped ? " flip" : "") + (Math.abs(d) < 1 ? " flat" : "")}
                              style={{ background: bg, color: Math.abs(d) >= 18 ? "var(--fg)" : undefined }}
                              title={`${a.lb} × ${b.lb} — ${was.sim}% → ${now.sim}%${flipped ? " · call flipped" : ""}`}
                              onClick={() => onOpenPair(i, j)}>
                              {Math.abs(d) < 1 ? "·" : (d > 0 ? "+" : "−") + Math.abs(d)}
                              {flipped && <span className="dfFlipMk">!</span>}
                            </button>
                          );
                        })}
                      </React.Fragment>
                    ))}
                  </div>
                  <div className="dfLegend">
                    <span className="lgSwatch" style={{ background: "color-mix(in oklab, var(--bad-bar) 60%, var(--surface))" }}></span> less similar
                    <span className="lgSwatch" style={{ background: "var(--surface)" }}></span> unchanged
                    <span className="lgSwatch" style={{ background: "color-mix(in oklab, var(--ok-bar) 60%, var(--surface))" }}></span> more similar
                    <span style={{ marginLeft: 8 }}>◻ white ring + <b style={{ color: "var(--fg)" }}>!</b> = call flipped</span>
                    <span className="tmSpeedAxNote">points of similarity, {PREV.run} → {DATE.run}</span>
                  </div>
                </div>

                <h2 className="rpH2" id="df-pairs">Pair changes<span className="rpH2N">{changes.length} of 45</span></h2>
                <p className="rpP">Flipped calls first, then pairs whose numbers moved by 0.01 or more. Rows open the pair in the matrix.</p>
                <table className="dfTable">
                  <thead><tr><th>Pair</th><th className="num">Residual correlation</th><th className="num">Windowed coverage</th><th>Call</th></tr></thead>
                  <tbody>{changes.map(({ i, j, now, was, flipped }) => (
                    <tr key={now.key} className="click" onClick={() => onOpenPair(i, j)}>
                      <td className="mono">{short(REC[i].lb)} × {short(REC[j].lb)}{flipped && <span className="dfFlipMk" style={{ position: "static", marginLeft: 6 }}>!</span>}</td>
                      <td className="num"><Delta from={was.corr} to={now.corr} /></td>
                      <td className="num"><Delta from={was.win} to={now.win} digits={2} /></td>
                      <td>{flipped ? <span className="dfFlow"><CallPill same={was.same} /><span className="dfTo">→</span><CallPill same={now.same} secondary={now.secondary} /></span> : <span className="dfWas" style={{ fontSize: 11 }}>held · {now.same ? "same" : "different"}</span>}</td>
                    </tr>))}
                  </tbody>
                </table>
                <p className="rpP rpSmall">The other {45 - changes.length} pairs moved by less than 0.01 on every signal and kept their call.</p>

                <h2 className="rpH2" id="df-judgments">Your judgments<span className="rpH2N">{judged.length}</span></h2>
                {judged.length === 0 ? (
                  <div className="dfEmpty" style={{ marginTop: 11 }}>No judgments recorded for this date yet — nothing to reconcile.</div>
                ) : (
                  <React.Fragment>
                    <p className="rpP">A judgment is a call about the tapes, not about a run — so it survives re-analysis. What changes is whether the algorithm still disagrees with you.</p>
                    <div className="dfImp">
                      {impacts.map((im) => (
                        <div key={im.k} className={"dfImpRow " + im.tone}>
                          <span className="mono" style={{ fontSize: 11.5 }}>{im.a} × {im.b}</span>
                          <span className={"pill sm " + (im.v === "confirmed_same" ? "ok" : im.v === "confirmed_different" ? "info" : im.v === "uncertain" ? "warn" : "bad")}>{JLABEL[im.v]}</span>
                          <span className="dfImpTx">{im.tx} <button className="tmLink" onClick={() => onOpenPair(REC.findIndex((r) => r.lb === "LB-" + im.a), REC.findIndex((r) => r.lb === "LB-" + im.b))}>Open pair</button></span>
                        </div>
                      ))}
                    </div>
                    <p className="rpP rpSmall">Judgments are never rewritten or deleted by a re-run. If a pair itself disappears — a recording withdrawn from the library — its judgment is kept and marked orphaned rather than dropped.</p>
                  </React.Fragment>
                )}

                <div className="rpFoot">Diff computed client-side from two run artifacts · base {PREV.run} · head {DATE.run}<br />Neither run is modified by viewing this.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  window.TMDiff = Diff;
})();
