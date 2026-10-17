// pipeline2-stages.jsx
// The four stage-detail panels, folded into the Pipeline Workspace. These are
// the old Verify/Lookup/Rename/LBDIR sub-tools — trimmed to the essentials and
// speaking the ONE shared status vocabulary. Each gets the selected folder.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Input, Chip, TableShell, TH, TR, TD, Banner } = window;
  const { StatusTag } = window.LBB_P2_Parts;

  // tone -> edge mapping shared
  const tdNum = (label, value, color) => (
    <div style={{ padding: "8px 12px", borderRadius: 7, background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)" }}>
      <div style={{ fontSize: 9.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "var(--lbb-mono)", fontVariantNumeric: "tabular-nums", color: color || "var(--lbb-fg)", marginTop: 2 }}>{value}</div>
    </div>
  );

  const StageHead = ({ state, title, sub, right }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
      <StatusTag state={state} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 700, letterSpacing: -0.01 }}>{title}</div>
        {sub && <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>{sub}</div>}
      </div>
      <div style={{ flex: 1 }} />
      {right}
    </div>
  );

  // ════════════════════════ VERIFY ════════════════════════
  function VerifyStage({ folder, onGenerate, onInstallTool }) {
    const [showAll, setShowAll] = React.useState(false);
    const v = folder.verify;
    const st = folder.steps.verify.state;

    // ── Special case: no checksum sidecar on disk → must GENERATE ──
    if (v.noChecksums) {
      return (
        <div>
          <StageHead state={st} title="No checksums in this folder yet"
            sub={folder.steps.verify.reason} />
          <div style={{
            display: "flex", gap: 16, padding: "18px 20px", marginBottom: 14,
            background: "var(--lbb-warn-bg)", border: "1px solid var(--lbb-warn-bar)", borderRadius: 10,
          }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, flex: "0 0 42px", background: "var(--lbb-warn-bar)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="shield" size={22} /></div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Generate checksums for {v.total} files</div>
              <div style={{ fontSize: 12, color: "var(--lbb-fg2)", lineHeight: 1.5, marginBottom: 12 }}>
                There's no <span style={{ fontFamily: "var(--lbb-mono)" }}>.ffp</span> or <span style={{ fontFamily: "var(--lbb-mono)" }}>.md5</span> sidecar here, so there's nothing to verify against. Generate them from the audio on disk — then this folder verifies and looks up automatically.
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Button variant="primary" size="md" icon="shield" onClick={() => onGenerate && onGenerate()}>Generate FFP + MD5</Button>
                <Button variant="ghost" size="md" icon="reveal">Open in Finder</Button>
              </div>
            </div>
          </div>
          <Banner tone="info" icon="info">Writes <span style={{ fontFamily: "var(--lbb-mono)" }}>_mychecksums.ffp</span> and <span style={{ fontFamily: "var(--lbb-mono)" }}>.md5</span> into the folder. Non-destructive — your audio files aren't touched.</Banner>
        </div>
      );
    }

    // ── Special case: SHN source but shntool missing ──
    if (v.shntool === "missing") {
      return (
        <div>
          <StageHead state={st} title="shntool required for .shn files"
            sub={folder.steps.verify.reason} />
          <Banner tone="bad" icon="alert" title="Can't decode .shn without shntool" style={{ marginBottom: 14 }}
            action={<Button size="sm" variant="primary" icon="download" onClick={() => onInstallTool && onInstallTool()}>Install shntool</Button>}>
            These {v.total} tracks are Shorten-encoded. We need <span style={{ fontFamily: "var(--lbb-mono)" }}>shntool</span> to decode them before hashing. Install it once and every SHN folder verifies normally.
          </Banner>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", background: "var(--lbb-surface)", border: "1px dashed var(--lbb-border2)", borderRadius: 8, fontSize: 12, color: "var(--lbb-fg2)" }}>
            <Icon name="info" size={14} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
            <span>Prefer not to install? You can <strong>verify the .st5 sidecar only</strong> (filename + size, no audio hash) — weaker, but unblocks lookup.</span>
            <div style={{ flex: 1 }} />
            <Button size="sm" variant="secondary">Verify .st5 only</Button>
          </div>
        </div>
      );
    }

    const probs = v.files.filter(f => f.ok !== "pass");
    const rows = showAll ? v.files : probs;
    return (
      <div>
        <StageHead state={st} title="Checksums vs audio on disk"
          sub={folder.steps.verify.reason}
          right={<div style={{ display: "flex", gap: 6 }}>
            <Button size="sm" variant="ghost" icon="reveal">Open in Finder</Button>
            <Button size="sm" variant="secondary" icon="refresh">Re-verify</Button>
          </div>} />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8, marginBottom: 16 }}>
          {tdNum("Total", v.total)}
          {tdNum("Pass", v.pass, v.pass === v.total ? "var(--lbb-ok-fg)" : "var(--lbb-fg)")}
          {tdNum("Missing", v.miss, v.miss > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)")}
          {tdNum("Mismatch", v.mism, v.mism > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)")}
          {tdNum("Extra", v.extra, v.extra > 0 ? "var(--lbb-info-fg)" : "var(--lbb-fg3)")}
        </div>

        {st === "running" ? (
          <div style={{ marginBottom: 14 }}>
            <div className="lbb-prog"><div style={{ width: `${Math.round(v.pass / v.total * 100)}%` }} /></div>
            <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 8 }}>Hashing files — {v.pass} of {v.total} done. This folder will advance to Lookup automatically.</div>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Files</span>
              <Chip active={!showAll} onClick={() => setShowAll(false)} size="sm" count={probs.length}>Problems</Chip>
              <Chip active={showAll} onClick={() => setShowAll(true)} size="sm" count={v.files.length}>All</Chip>
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)" }}>Checked: <strong style={{ color: "var(--lbb-fg2)" }}>FFP + MD5</strong></span>
              <Button size="sm" variant="ghost" icon="copy">Copy report</Button>
            </div>
            {rows.length === 0 ? (
              <Banner tone="ok" icon="check" title="Every file checks out">All {v.total} files match their FFP + MD5 checksums. Nothing to fix here.</Banner>
            ) : (
              <TableShell>
                <colgroup><col style={{ width: 3 }} /><col /><col style={{ width: 132 }} /><col style={{ width: 132 }} /><col style={{ width: 58 }} /><col style={{ width: 88 }} /></colgroup>
                <thead><tr><TH> </TH><TH>Filename</TH><TH align="right">FFP</TH><TH align="right">MD5</TH><TH align="center">Disk</TH><TH>Status</TH></tr></thead>
                <tbody>
                  {rows.map((f, i) => {
                    const edge = f.ok === "pass" ? "ok" : "bad";
                    const ffMatch = f.ffA !== "—" && f.ffA === f.ffE;
                    const mdMatch = f.mdA !== "—" && f.mdA === f.mdE;
                    return (
                      <TR key={i} edge={edge}>
                        <TD mono style={{ color: f.ok === "pass" ? "var(--lbb-fg)" : "var(--lbb-bad-fg)" }}>{f.n}</TD>
                        <TD align="right" mono style={{ color: ffMatch ? "var(--lbb-ok-fg)" : "var(--lbb-bad-fg)" }}>{ffMatch ? "match" : f.ffA}</TD>
                        <TD align="right" mono style={{ color: mdMatch ? "var(--lbb-ok-fg)" : "var(--lbb-bad-fg)" }}>{mdMatch ? "match" : f.mdA}</TD>
                        <TD align="center">{f.disk ? <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} /> : <Icon name="x" size={12} style={{ color: "var(--lbb-bad-fg)" }} />}</TD>
                        <TD><StatusTag state={f.ok}>{f.ok === "pass" ? "Pass" : "Missing"}</StatusTag></TD>
                      </TR>
                    );
                  })}
                </tbody>
              </TableShell>
            )}
            {st === "blocked" && (
              <Banner tone="bad" icon="alert" title="This is the blocker" style={{ marginTop: 14 }}>
                {folder.verify.miss} files in the checksum list aren't on disk. Restore the missing files, or drop a complete copy of the folder, then re-verify.
              </Banner>
            )}
          </>
        )}
      </div>
    );
  }

  // ════════════════════════ LOOKUP ════════════════════════
  function LookupStage({ folder, onResolve }) {
    const st = folder.steps.lookup.state;
    const [pick, setPick] = React.useState(folder.candidates ? null : folder.lb);

    if (st === "pending") {
      return <div><StageHead state={st} title="Identify the LB# in the master DB" sub={folder.steps.lookup.reason} />
        <Banner tone="info" icon="info">Lookup runs automatically once Verify passes. Resolve the verify blocker first.</Banner></div>;
    }

    // Ambiguous — candidate picker
    if (folder.candidates) {
      return (
        <div>
          <StageHead state={st} title="Which show is this?"
            sub="Checksums partially match several archive entries. Pick the right LB# to unblock the rename." />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {folder.candidates.map((c, i) => {
              const sel = pick === c.lb;
              const tone = c.match === 0 ? "bad" : c.match >= c.of - 2 ? "ok" : "warn";
              return (
                <label key={i} style={{
                  display: "flex", alignItems: "center", gap: 14, padding: "12px 14px",
                  background: sel ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
                  border: `1px solid ${sel ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`,
                  borderRadius: 8, cursor: "pointer",
                }}>
                  <input type="radio" name="cand" checked={sel} onChange={() => setPick(c.lb)} />
                  <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 700, color: "var(--lbb-accent-mid)", width: 110 }}>{c.lb}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 12.5, color: "var(--lbb-fg)" }}>{c.detail}</span>
                    <span style={{ display: "block", fontSize: 11, color: "var(--lbb-fg3)", marginTop: 2 }}>{c.note}</span>
                  </span>
                  <Pill tone={tone} soft dot>{c.match}/{c.of} checksums</Pill>
                  <Button size="sm" variant="ghost" icon="reveal">LB.com</Button>
                </label>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14 }}>
            <Button variant="primary" size="md" icon="check" disabled={!pick}
              onClick={() => onResolve && onResolve(pick)}>
              Pin {pick || "selection"} &amp; continue
            </Button>
            <Button variant="ghost" size="md">Mark as new entry…</Button>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>Pinning writes <span style={{ fontFamily: "var(--lbb-mono)" }}>folder_lb_link</span> so it never asks again.</span>
          </div>
        </div>
      );
    }

    // Not found
    if (st === "blocked") {
      return (
        <div>
          <StageHead state={st} title="Not in the master DB"
            sub={folder.steps.lookup.reason}
            right={<Button size="sm" variant="secondary" icon="plus">Mark as new entry…</Button>} />
          <Banner tone="bad" icon="alert" title="No matches found" style={{ marginBottom: 14 }}>
            None of these checksums exist in the archive yet. Either this is a brand-new source, or the files differ from what's on file. Confident it's new? <strong>Mark as new entry</strong> drops it into the Curator queue.
          </Banner>
          <TableShell>
            <colgroup><col style={{ width: 3 }} /><col style={{ width: 200 }} /><col /><col style={{ width: 100 }} /></colgroup>
            <thead><tr><TH> </TH><TH>Checksum</TH><TH>Filename</TH><TH>Status</TH></tr></thead>
            <tbody>
              {folder.notfound.slice(0, 8).map((f, i) => (
                <TR key={i} edge="bad">
                  <TD mono dim>{f.mdE}</TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>{f.n}</TD>
                  <TD><StatusTag state="blocked">Not found</StatusTag></TD>
                </TR>
              ))}
              <tr><td colSpan={4} style={{ textAlign: "center", padding: "8px 0", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic" }}>… {folder.notfound.length - 8} more</td></tr>
            </tbody>
          </TableShell>
        </div>
      );
    }

    // Matched
    return (
      <div>
        <StageHead state={st} title={`Matched ${folder.lb}`}
          sub={folder.steps.lookup.reason}
          right={<Button size="sm" variant="ghost" icon="reveal">Open {folder.lb} on LB.com</Button>} />
        <div style={{
          display: "flex", alignItems: "center", gap: 14, padding: "14px 16px", marginBottom: 14,
          background: "var(--lbb-ok-bg)", border: "1px solid var(--lbb-ok-bar)", borderRadius: 8,
        }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, background: "var(--lbb-ok-bar)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="check" size={22} /></div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "var(--lbb-mono)", color: "var(--lbb-accent-mid)" }}>{folder.lb}</div>
            <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>All {folder.verify.total} checksums map to a single archive entry · type <strong>Concert</strong></div>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--lbb-mono)", color: "var(--lbb-ok-fg)" }}>{folder.verify.total}/{folder.verify.total}</div>
            <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", textTransform: "uppercase", letterSpacing: 0.06, fontWeight: 700 }}>matched</div>
          </div>
        </div>
        <Banner tone="info" icon="info">The match flows straight into <strong>Rename</strong> as a confident proposal — no extra step.</Banner>

        {folder.xref && folder.xref.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Icon name="link" size={13} style={{ color: "var(--lbb-info-fg)" }} />
              <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Cross-reference</span>
              <Pill tone="info" soft>{folder.xref.length} shared with other LB#s</Pill>
            </div>
            <Banner tone="info" icon="info" style={{ marginBottom: 8 }}>
              These checksums also appear under other archive entries — shared or duplicate sources. The folder still pins to <strong>{folder.lb}</strong>; this is just so you know it isn't unique.
            </Banner>
            <TableShell>
              <colgroup><col style={{ width: 3 }} /><col style={{ width: 150 }} /><col /><col style={{ width: 220 }} /></colgroup>
              <thead><tr><TH> </TH><TH>Checksum</TH><TH>Also in</TH><TH>Why</TH></tr></thead>
              <tbody>
                {folder.xref.map((x, i) => (
                  <TR key={i} edge="info">
                    <TD mono dim>{x.md}</TD>
                    <TD>
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                        {x.lbs.map(lb => (
                          <span key={lb} style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, fontWeight: 600, padding: "1px 6px", borderRadius: 4, background: lb === folder.lb ? "var(--lbb-ok-bg)" : "var(--lbb-info-bg)", color: lb === folder.lb ? "var(--lbb-ok-fg)" : "var(--lbb-info-fg)" }}>{lb}</span>
                        ))}
                      </div>
                    </TD>
                    <TD style={{ fontSize: 11.5, color: "var(--lbb-fg2)" }}>{x.note}</TD>
                  </TR>
                ))}
              </tbody>
            </TableShell>
          </div>
        )}
      </div>
    );
  }

  // ════════════════════════ RENAME ════════════════════════
  function RenameStage({ folder, onApply, applied }) {
    const st = applied ? "pass" : folder.steps.rename.state;
    const [editing, setEditing] = React.useState(false);
    const [draft, setDraft] = React.useState(folder.proposed || "");
    if (st === "pending") {
      return <div><StageHead state={st} title="Append the canonical (LB-XXXXX)" sub={folder.steps.rename.reason} />
        <Banner tone="info" icon="info">Rename unlocks once a single LB# is confirmed in Lookup.</Banner></div>;
    }
    const proposed = folder.proposed;
    const wrong = folder.wrongLb;
    // current-name renderer: strike the wrong LB# in red when present
    const renderCurrent = () => {
      if (wrong && folder.name.includes(wrong)) {
        const [a, b] = folder.name.split(wrong);
        return <>{a}<mark style={{ background: "var(--lbb-bad-bg)", color: "var(--lbb-bad-fg)", borderRadius: 3, padding: "1px 4px", textDecoration: "line-through" }}>{wrong}</mark>{b}</>;
      }
      return <span style={{ textDecoration: applied ? "line-through" : "none" }}>{folder.name}</span>;
    };
    return (
      <div>
        <StageHead state={st} title={applied ? "Renamed" : wrong ? "Fix the wrong LB# and apply" : "Review the proposed rename"}
          sub={folder.resHint}
          right={<div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {!applied && <Button size="sm" variant="ghost" icon="rename" onClick={() => setEditing(e => !e)}>{editing ? "Cancel edit" : "Edit name…"}</Button>}
            <Pill tone="info" soft style={{ fontFamily: "var(--lbb-mono)" }}>{folder.lb}</Pill>
          </div>} />

        {wrong && !applied && (
          <Banner tone="warn" icon="alert" title={`This folder is mislabeled ${wrong}`} style={{ marginBottom: 12 }}>
            The existing tag doesn't match the archive. Applying will <strong>remove {wrong}</strong> and append the correct <span style={{ fontFamily: "var(--lbb-mono)" }}>{folder.lb}</span> in one step.
          </Banner>
        )}

        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", background: "var(--lbb-bad-bg)" }}>
            <Icon name="x" size={14} style={{ color: "var(--lbb-bad-fg)", flex: "0 0 auto" }} />
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12.5, color: "var(--lbb-fg)" }}>{renderCurrent()}</span>
            <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: "var(--lbb-bad-fg)", textTransform: "uppercase", letterSpacing: 0.06 }}>current</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", background: "var(--lbb-ok-bg)", borderTop: "1px solid var(--lbb-border)" }}>
            <Icon name="check" size={14} style={{ color: "var(--lbb-ok-fg)", flex: "0 0 auto" }} />
            {editing ? (
              <input value={draft} onChange={e => setDraft(e.target.value)} autoFocus style={{ flex: 1, fontFamily: "var(--lbb-mono)", fontSize: 12.5, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--lbb-accent-mid)", background: "var(--lbb-bg)", color: "var(--lbb-fg)" }} />
            ) : (
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12.5, color: "var(--lbb-fg)", fontWeight: 600 }}>
                {proposed.split(folder.lb)[0]}<mark style={{ background: "var(--lbb-ok-bar)", color: "#fff", borderRadius: 3, padding: "1px 4px" }}>{folder.lb}</mark>{proposed.split(folder.lb)[1] || ""}
              </span>
            )}
            <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: "var(--lbb-ok-fg)", textTransform: "uppercase", letterSpacing: 0.06 }}>{applied ? "applied" : editing ? "editing" : "proposed"}</span>
          </div>
        </div>

        {applied ? (
          <Banner tone="ok" icon="check" title="Renamed">Logged to <span style={{ fontFamily: "var(--lbb-mono)" }}>rename_history</span> — reversible from Recent activity for 30 days. LBDIR will reconcile next.</Banner>
        ) : (
          <Banner tone="info" icon="info" title="Dry-run — nothing changes until you apply"
            action={<Button size="sm" variant="ghost" icon="copy">Copy diff</Button>}>
            Applying writes to <span style={{ fontFamily: "var(--lbb-mono)" }}>rename_history</span> and is reversible for 30 days.
          </Banner>
        )}
      </div>
    );
  }

  // ════════════════════════ LBDIR ════════════════════════
  // Folds the old LBDIR sub-tabs (Check · Retrieve · Reconcile · Extras) into
  // one contextual surface: sections appear only when that work is pending.
  function ReconcileSection({ recon, onReconcile }) {
    return (
      <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 9, overflow: "hidden", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--lbb-surface)", borderBottom: "1px solid var(--lbb-border)" }}>
          <Icon name="rename" size={14} style={{ color: "var(--lbb-warn-fg)" }} />
          <span style={{ fontSize: 12.5, fontWeight: 700 }}>Reconcile · moved or misnamed files</span>
          <Pill tone="warn" soft>{recon.length} found on disk</Pill>
          <div style={{ flex: 1 }} />
          <Button size="sm" variant="primary" icon="check" onClick={() => onReconcile && onReconcile()}>Apply {recon.length} moves</Button>
        </div>
        <div style={{ padding: "8px 8px 4px" }}>
          <div style={{ fontSize: 11, color: "var(--lbb-fg2)", padding: "4px 8px 8px", lineHeight: 1.45 }}>
            Each sidecar entry marked <em>missing</em> was matched by MD5 to a file sitting at the wrong path. Applying renames them into place — no re-download.
          </div>
          <TableShell>
            <colgroup><col style={{ width: 3 }} /><col /><col style={{ width: 28 }} /><col style={{ width: 170 }} /><col style={{ width: 120 }} /></colgroup>
            <thead><tr><TH> </TH><TH>On disk now</TH><TH> </TH><TH>Will become</TH><TH align="right">MD5 match</TH></tr></thead>
            <tbody>
              {recon.map((r, i) => (
                <TR key={i} edge="warn">
                  <TD mono dim style={{ color: "var(--lbb-fg2)" }}>{r.from}</TD>
                  <TD align="center"><Icon name="chevRight" size={13} style={{ color: "var(--lbb-fg3)" }} /></TD>
                  <TD mono style={{ color: "var(--lbb-fg)", fontWeight: 600 }}>{r.to}</TD>
                  <TD align="right" mono style={{ color: "var(--lbb-ok-fg)" }}>{r.md}</TD>
                </TR>
              ))}
            </tbody>
          </TableShell>
        </div>
      </div>
    );
  }

  function ExtrasSection({ extras, onMoveExtras }) {
    const [rows, setRows] = React.useState(extras);
    const toggle = (i) => setRows(rs => rs.map((r, j) => j === i ? { ...r, sel: !r.sel } : r));
    const selected = rows.filter(r => r.sel);
    return (
      <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 9, overflow: "hidden", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--lbb-surface)", borderBottom: "1px solid var(--lbb-border)" }}>
          <Icon name="folder" size={14} style={{ color: "var(--lbb-info-fg)" }} />
          <span style={{ fontSize: 12.5, fontWeight: 700 }}>Extras · files not in the sidecar</span>
          <Pill tone="info" soft>{rows.length} files</Pill>
          <div style={{ flex: 1 }} />
          <Button size="sm" variant="ghost" onClick={() => setRows(rs => rs.map(r => ({ ...r, sel: r.sys })))}>Select system junk</Button>
          <Button size="sm" variant="secondary" icon="folder" disabled={selected.length === 0} onClick={() => onMoveExtras && onMoveExtras(selected)}>Move {selected.length} to /extras</Button>
        </div>
        <div style={{ padding: "8px 8px 4px" }}>
          <TableShell>
            <colgroup><col style={{ width: 3 }} /><col style={{ width: 34 }} /><col /><col style={{ width: 90 }} /><col style={{ width: 130 }} /></colgroup>
            <thead><tr><TH> </TH><TH> </TH><TH>File</TH><TH align="right">Size</TH><TH>Kind</TH></tr></thead>
            <tbody>
              {rows.map((e, i) => (
                <TR key={i} edge={e.sel ? "info" : undefined}>
                  <TD><input type="checkbox" checked={e.sel} onChange={() => toggle(i)} /></TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>{e.p}</TD>
                  <TD align="right" mono dim>{e.sz}</TD>
                  <TD>{e.sys ? <Pill tone="mute" soft>system junk</Pill> : <Pill tone="info" soft>extra</Pill>}</TD>
                </TR>
              ))}
            </tbody>
          </TableShell>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 8px 6px", fontSize: 11.5, color: "var(--lbb-fg2)" }}>
            <Icon name="info" size={13} style={{ color: "var(--lbb-info-fg)", flex: "0 0 auto" }} />
            <span>Files move into an <span style={{ fontFamily: "var(--lbb-mono)" }}>/extras</span> subfolder inside this folder — nothing is deleted, and the move is logged so you can pull them back out.</span>
          </div>
        </div>
      </div>
    );
  }

  function LBDIRStage({ folder, onRetrieve, onReconcile, onMoveExtras }) {
    const st = folder.steps.lbdir.state;
    const L = folder.lbdir;

    if (st === "pending") {
      return <div><StageHead state={st} title="Reconcile the official archive sidecar" sub={folder.steps.lbdir.reason} />
        <Banner tone="info" icon="info" title="Runs after rename"
          action={<Button size="sm" variant="secondary" icon="download" onClick={() => onRetrieve && onRetrieve()}>Retrieve sidecar now</Button>}>
          Once renamed, we retrieve <span style={{ fontFamily: "var(--lbb-mono)" }}>lbdir*.txt</span> from the archive cache and reconcile it against the files on disk. You can pull it early if you like.
        </Banner></div>;
    }

    // ACTION — sidecar retrieved, but reconcile and/or extras are pending
    if (st === "action" && L) {
      return (
        <div>
          <StageHead state={st} title="Reconcile against the archive sidecar"
            sub={folder.steps.lbdir.reason}
            right={<div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <Pill tone="ok" soft dot>{L.source === "cache" ? "Sidecar from cache" : "Sidecar scraped"}</Pill>
              <Button size="sm" variant="ghost" icon="reveal">Open lbdir.txt</Button>
            </div>} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8, marginBottom: 16 }}>
            {tdNum("In sidecar", L.sidecarTotal)}
            {tdNum("Present", L.present, "var(--lbb-ok-fg)")}
            {tdNum("Mismatch", L.mismatch, L.mismatch > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)")}
            {tdNum("Missing", L.missing, L.missing > 0 ? "var(--lbb-warn-fg)" : "var(--lbb-fg3)")}
            {tdNum("Extras", L.extras.length, L.extras.length > 0 ? "var(--lbb-info-fg)" : "var(--lbb-fg3)")}
          </div>
          {L.recon && L.recon.length > 0 && <ReconcileSection recon={L.recon} onReconcile={onReconcile} />}
          {L.extras && L.extras.length > 0 && <ExtrasSection extras={L.extras} onMoveExtras={onMoveExtras} />}
        </div>
      );
    }

    // PASS — clean
    return (
      <div>
        <StageHead state={st} title="Reconciled against the archive sidecar"
          sub={folder.steps.lbdir.reason}
          right={<Button size="sm" variant="ghost" icon="reveal">Open lbdir.txt</Button>} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 14 }}>
          {tdNum("In sidecar", folder.verify.total)}
          {tdNum("Pass", folder.verify.total, "var(--lbb-ok-fg)")}
          {tdNum("Mismatch", 0, "var(--lbb-fg3)")}
          {tdNum("Missing", 0, "var(--lbb-fg3)")}
        </div>
        <Banner tone="ok" icon="check" title="Archive-clean">Every file referenced in the official sidecar is present and matches. This folder is fully reconciled.</Banner>
      </div>
    );
  }

  // ════════════════════════ COLLECT ════════════════════════
  // The bridge from the pipeline into My Collection. A reconciled folder is
  // routed to the correct final-storage mount (by show year), moved there, and
  // tagged as owned/public so it appears in the collection.
  function CollectStage({ folder, onFile }) {
    const P2 = window.LBB_P2;
    const { MOUNTS, destPath } = P2;
    const st = folder.steps.collect.state;
    const dest = folder.dest || P2.proposeDest(folder);
    const recommended = dest.mount;
    const [mount, setMount] = React.useState(recommended);
    const finalPath = destPath(mount, dest) + dest.finalName;

    // PENDING — earlier stages not finished
    if (st === "pending") {
      return (
        <div>
          <StageHead state={st} title="File into final storage & tag in the collection" sub={folder.steps.collect.reason} />
          <Banner tone="info" icon="info">
            This is the last step — the bridge into <strong>My Collection</strong>. Once the sidecar reconciles in <strong>LBDIR</strong>, the folder is routed to the right storage mount, moved there, and tagged as owned. Finish the earlier stages first — or use <strong>Mark complete</strong> on any stage to bypass the locks and file from here.
          </Banner>
        </div>
      );
    }

    // PASS — already filed & in the collection
    if (st === "pass") {
      const c = folder.collected || {};
      return (
        <div>
          <StageHead state={st} title="Added to the collection"
            sub={folder.steps.collect.reason}
            right={<div style={{ display: "flex", gap: 6 }}>
              <Button size="sm" variant="ghost" icon="reveal">Reveal on disk</Button>
              <Button size="sm" variant="secondary" icon="collection">Open in My Collection</Button>
            </div>} />
          <div style={{
            display: "flex", alignItems: "center", gap: 14, padding: "16px 18px", marginBottom: 14,
            background: "var(--lbb-ok-bg)", border: "1px solid var(--lbb-ok-bar)", borderRadius: 10,
          }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, flex: "0 0 42px", background: "var(--lbb-ok-bar)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="collection" size={22} /></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Filed to final storage · tagged owned</div>
              <div style={{ fontSize: 12, fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)", marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.path || folder.path}</div>
            </div>
            <div style={{ display: "flex", gap: 6, flex: "0 0 auto" }}>
              <Pill tone="ok" soft dot>Owned</Pill>
              <Pill tone="ok" soft>{c.status || "Public"}</Pill>
            </div>
          </div>
          <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden", marginBottom: 14 }}>
            {[
              ["LB#", folder.lb || "—", true],
              ["Mount", c.mount || dest.mount],
              ["Confirmed", c.confirmed || "today"],
              ["Added", c.at || "today"],
            ].map(([k, v, mono], i) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: i < 3 ? "1px solid var(--lbb-border)" : "none", background: i % 2 ? "var(--lbb-surface)" : "var(--lbb-surface2)" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.04, textTransform: "uppercase", width: 90 }}>{k}</span>
                <span style={{ fontSize: 12.5, fontFamily: mono ? "var(--lbb-mono)" : "inherit", fontWeight: mono ? 700 : 500, color: mono ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{v}</span>
              </div>
            ))}
          </div>
          <Banner tone="info" icon="info">Logged to <span style={{ fontFamily: "var(--lbb-mono)" }}>rename_history</span> as a collection move — reversible for 30 days. The collection row links back to this folder on disk.</Banner>
        </div>
      );
    }

    // ACTION — reconciled, ready to file. The bridge UI.
    const tagRows = [
      ["LB#", folder.lb || "unassigned", true],
      ["Status →", "Public · Owned"],
      ["Confirmed →", "today"],
      ["Fingerprint", "queued · acoustid"],
    ];
    return (
      <div>
        <StageHead state={st} title="File into the collection"
          sub="Move this reconciled folder to its final storage mount and tag it as owned."
          right={folder.lb ? <Pill tone="info" soft style={{ fontFamily: "var(--lbb-mono)" }}>{folder.lb}</Pill> : null} />

        {folder.overridden && (
          <Banner tone="warn" icon="alert" style={{ marginBottom: 14 }}>
            One or more pipeline stages were <strong>marked complete</strong> manually rather than passing on their own. Filing will still move &amp; tag the folder — just double-check it's the right show.
          </Banner>
        )}

        {/* Route: staging → destination */}
        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 10, overflow: "hidden", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--lbb-surface)" }}>
            <Icon name="folder" size={14} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12, color: "var(--lbb-fg2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{folder.path}</span>
            <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: "var(--lbb-fg3)", textTransform: "uppercase", letterSpacing: 0.06, flex: "0 0 auto" }}>staging</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "2px 0", background: "var(--lbb-surface)" }}>
            <Icon name="drop" size={14} style={{ color: "var(--lbb-accent-mid)" }} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "13px 14px", background: "var(--lbb-accent-soft)", borderTop: "1px solid var(--lbb-border)" }}>
            <Icon name="collection" size={15} style={{ color: "var(--lbb-accent-mid)", flex: "0 0 auto" }} />
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12.5, fontWeight: 600, color: "var(--lbb-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              <mark style={{ background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", borderRadius: 3, padding: "1px 4px" }}>{destPath(mount, dest)}</mark>{dest.finalName}
            </span>
            <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: "var(--lbb-accent-mid)", textTransform: "uppercase", letterSpacing: 0.06, flex: "0 0 auto" }}>final storage</span>
          </div>
        </div>

        {/* Mount picker */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Storage mount</span>
          {dest.routed && <Pill tone="info" soft>Routed by year · {dest.year} → {recommended}</Pill>}
          <div style={{ flex: 1 }} />
          {mount !== recommended && <Button size="sm" variant="ghost" icon="refresh" onClick={() => setMount(recommended)}>Reset to suggested</Button>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 16 }}>
          {MOUNTS.map(m => {
            const sel = mount === m.id;
            return (
              <label key={m.id} style={{
                display: "flex", flexDirection: "column", gap: 3, padding: "10px 12px", cursor: "pointer",
                background: sel ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
                border: `1px solid ${sel ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`, borderRadius: 9,
              }}>
                <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <input type="radio" name="mount" checked={sel} onChange={() => setMount(m.id)} />
                  <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 13, fontWeight: 700, color: sel ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{m.id}</span>
                  {m.id === recommended && <Pill tone="ok" soft style={{ marginLeft: "auto" }}>suggested</Pill>}
                </span>
                <span style={{ fontSize: 11, color: "var(--lbb-fg2)" }}>{m.span}</span>
                <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{m.free} free</span>
              </label>
            );
          })}
        </div>

        {/* Tag in the collection */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Icon name="collection" size={13} style={{ color: "var(--lbb-accent-mid)" }} />
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Tag in the collection</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>15,967 → <strong style={{ color: "var(--lbb-ok-fg)" }}>15,968</strong> items</span>
        </div>
        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden", marginBottom: 14 }}>
          {tagRows.map(([k, v, mono], i) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: i < tagRows.length - 1 ? "1px solid var(--lbb-border)" : "none", background: i % 2 ? "var(--lbb-surface)" : "var(--lbb-surface2)" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.04, textTransform: "uppercase", width: 110 }}>{k}</span>
              <span style={{ fontSize: 12.5, fontFamily: mono ? "var(--lbb-mono)" : "inherit", fontWeight: mono ? 700 : 500, color: mono ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{v}</span>
            </div>
          ))}
        </div>

        <Banner tone="info" icon="info" title="What filing does"
          action={<Button variant="primary" size="sm" icon="collection" onClick={() => onFile && onFile({ mount, path: finalPath })}>File into collection</Button>}>
          Moves the folder to <span style={{ fontFamily: "var(--lbb-mono)" }}>{destPath(mount, dest)}</span>, writes the collection row, and tags it <strong>owned · public</strong>. Logged to <span style={{ fontFamily: "var(--lbb-mono)" }}>rename_history</span> — reversible for 30 days.
        </Banner>
      </div>
    );
  }

  window.LBB_P2_Stages = { VerifyStage, LookupStage, RenameStage, LBDIRStage, CollectStage };
})();
