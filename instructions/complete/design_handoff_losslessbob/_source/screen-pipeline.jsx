// screen-pipeline.jsx
// The unified Ingest pipeline — built for 50–100 folder batches.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Card, Chip,
          TableShell, TH, TR, TD, GroupRow, Banner, IconButton, Input } = window;

  // Sample data — 82 folders, mixed states.
  const SEED = [
    // status: verify / lookup / rename / lbdir, lbnum, selected?
    { name: "bd2025-07-25 Alpharetta GA",       v: "warn",  l: "bad",   r: "mute", d: "mute", lb: null,      sel: false, severity: "attn" },
    { name: "bd2025-07-26 Charlotte NC",        v: "bad",   l: "mute",  r: "mute", d: "mute", lb: null,      sel: false, severity: "attn" },
    { name: "bd2025-09-18 Noblesville IN",      v: "ok",    l: "ok",    r: "warn", d: "mute", lb: "LB-16401",sel: true,  severity: "ready" },
    { name: "bd2026-04-02 Madison WI",          v: "ok",    l: "ok",    r: "warn", d: "ok",   lb: "LB-16591",sel: true,  severity: "ready" },
    { name: "bd2026-03-27 La Crosse WI",        v: "ok",    l: "ok",    r: "ok",   d: "ok",   lb: "LB-16588",sel: false, severity: "done" },
    { name: "bd2026.03.30 Waukegan IL",         v: "ok",    l: "ok",    r: "warn", d: "mute", lb: "LB-16590",sel: false, severity: "ready" },
    { name: "bd2026-04-05 Minneapolis MN",      v: "ok",    l: "ok",    r: "warn", d: "ok",   lb: "LB-16592",sel: false, severity: "ready" },
    { name: "bd2026-04-08 Chicago IL",          v: "ok",    l: "ok",    r: "ok",   d: "ok",   lb: "LB-16593",sel: false, severity: "done" },
    { name: "bd2026-04-12 Detroit MI",          v: "ok",    l: "ok",    r: "warn", d: "ok",   lb: "LB-16594",sel: false, severity: "ready" },
    { name: "bd2026-04-15 Cleveland OH",        v: "ok",    l: "ok",    r: "ok",   d: "ok",   lb: "LB-16595",sel: false, severity: "done" },
    { name: "bd2026-04-19 Pittsburgh PA",       v: "ok",    l: "warn",  r: "mute", d: "mute", lb: "LB-16596?",sel: false, severity: "attn" },
    { name: "bd2026-04-22 Philadelphia PA",     v: "ok",    l: "ok",    r: "warn", d: "mute", lb: "LB-16597",sel: false, severity: "ready" },
    { name: "bd2026-04-25 New York NY (Beacon)",v: "ok",    l: "ok",    r: "warn", d: "ok",   lb: "LB-16598",sel: false, severity: "ready" },
    { name: "bd2026-04-28 Boston MA",           v: "ok",    l: "ok",    r: "ok",   d: "ok",   lb: "LB-16599",sel: false, severity: "done" },
    { name: "bd2026-05-02 Toronto ON",          v: "warn",  l: "mute",  r: "mute", d: "mute", lb: null,      sel: false, severity: "attn" },
  ];

  const QUEUE = [
    "/mnt/HOPPER/bd2025-07-25 Alpharetta GA FLAC",
    "/mnt/HOPPER/bd2025-07-26 Charlotte NC FLAC",
    "/mnt/HOPPER/bd2025-09-18 Noblesville IN FLAC",
    "/mnt/HOPPER/bd2026-03-27 La Crosse WI",
    "/mnt/HOPPER/bd2026.03.30 Waukegan IL",
    "/mnt/HOPPER/bd2026-04-02 Madison WI",
    "/mnt/HOPPER/bd2026-04-05 Minneapolis MN",
    "/mnt/HOPPER/bd2026-04-08 Chicago IL",
    "/mnt/HOPPER/bd2026-04-12 Detroit MI",
    "/mnt/HOPPER/bd2026-04-15 Cleveland OH",
    "/mnt/HOPPER/bd2026-04-19 Pittsburgh PA",
    "/mnt/HOPPER/bd2026-04-22 Philadelphia PA",
    "/mnt/HOPPER/bd2026-04-25 New York NY",
    "/mnt/HOPPER/bd2026-04-28 Boston MA",
    "/mnt/HOPPER/bd2026-05-02 Toronto ON",
  ];

  function StepPill({ tone, label }) {
    if (tone === "mute") return <Pill tone="mute" soft style={{ minWidth: 56, justifyContent: "center" }}>—</Pill>;
    return <Pill tone={tone} soft dot style={{ minWidth: 56, justifyContent: "center" }}>{label}</Pill>;
  }

  function ScreenPipeline() {
    const [filter, setFilter] = React.useState("all");
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Top banner — live progress strip */}
        <div style={{
          padding: "12px 24px", borderBottom: "1px solid var(--lbb-border)",
          background: "linear-gradient(180deg, var(--lbb-accent-soft) 0%, transparent 140%)",
          display: "flex", alignItems: "center", gap: 18,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 9,
            background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset",
          }}><Icon name="pipeline" size={18} /></div>

          <div style={{ minWidth: 320 }}>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.01 }}>
              Pipeline · 82 folders queued
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg2)", marginTop: 2 }}>
              Last run finished 14 minutes ago · drop more folders any time
            </div>
          </div>

          {/* Stage counters */}
          <div style={{ display: "flex", gap: 8, marginLeft: 12 }}>
            <Pill tone="ok"   soft dot>36 done</Pill>
            <Pill tone="warn" soft dot>32 ready to rename</Pill>
            <Pill tone="bad"  soft dot>14 need attention</Pill>
          </div>

          <div style={{ flex: 1 }} />

          {/* Bulk apply hero */}
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Button variant="ghost" size="md" icon="more">Bulk actions</Button>
            <Button variant="primary" size="md" icon="check">Apply all 32 proposed renames</Button>
          </div>
        </div>

        {/* Main two-pane layout */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "264px 1fr", minHeight: 0 }}>
          {/* Folder queue rail */}
          <aside style={{
            background: "var(--lbb-surface)",
            borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="folder" size={13} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.1, textTransform: "uppercase" }}>
                  Folder queue
                </span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>82</span>
              </div>
              <div style={{ marginTop: 8 }}>
                <Input icon="search" placeholder="Filter queue…" size="sm" style={{ width: "100%" }} />
              </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "6px 8px" }}>
              {QUEUE.map((path, i) => {
                const name = path.split("/").pop();
                const status = SEED[i] || {};
                const active = i === 0;
                return (
                  <button key={i} style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px", marginBottom: 1, borderRadius: 6,
                    background: active ? "var(--lbb-accent-soft)" : "transparent",
                    color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                    border: "1px solid transparent", textAlign: "left",
                    fontFamily: "inherit", fontSize: 11.5, cursor: "pointer",
                  }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: 2,
                      background: status.severity === "done" ? "var(--lbb-ok-bar)"
                                : status.severity === "ready" ? "var(--lbb-warn-bar)"
                                : status.severity === "attn"  ? "var(--lbb-bad-bar)"
                                : "var(--lbb-fg3)",
                      flex: "0 0 8px",
                    }}/>
                    <span style={{
                      flex: 1, minWidth: 0, whiteSpace: "nowrap",
                      overflow: "hidden", textOverflow: "ellipsis",
                      fontFamily: "var(--lbb-mono)", fontSize: 11,
                    }}>{name}</span>
                  </button>
                );
              })}
              <div style={{ padding: "6px 8px", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic" }}>
                + 67 more (scroll…)
              </div>
            </div>

            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="folderPlus" block>Add folders…</Button>
              <Button variant="secondary" size="sm" icon="search" block>Scan tree…</Button>
              <Button variant="ghost" size="sm" icon="trash" block>Clear queue</Button>

              <div style={{
                marginTop: 10, padding: "8px 10px",
                background: "var(--lbb-surface2)", borderRadius: 6,
                border: "1px solid var(--lbb-border)",
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>
                  Run on selected (82)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <Button variant="primary" size="sm" icon="play" block>Run all 4 steps</Button>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                    <Button variant="secondary" size="sm">Verify</Button>
                    <Button variant="secondary" size="sm">Lookup</Button>
                    <Button variant="secondary" size="sm">Rename</Button>
                    <Button variant="secondary" size="sm">LBDIR</Button>
                  </div>
                </div>
              </div>
            </div>
          </aside>

          {/* Main table area */}
          <section style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            {/* Filter chips */}
            <div style={{
              padding: "12px 20px", display: "flex", alignItems: "center", gap: 6,
              borderBottom: "1px solid var(--lbb-border)", flexWrap: "wrap",
            }}>
              <Chip active={filter==="all"} onClick={() => setFilter("all")} count={82}>All</Chip>
              <Chip active={filter==="attn"} onClick={() => setFilter("attn")} count={14}>Need attention</Chip>
              <Chip active={filter==="ready"} onClick={() => setFilter("ready")} count={32}>Ready to rename</Chip>
              <Chip active={filter==="done"} onClick={() => setFilter("done")} count={36}>Done</Chip>
              <span style={{ width: 1, height: 16, background: "var(--lbb-border)", margin: "0 4px" }} />
              <Chip count={6}>Not found</Chip>
              <Chip count={3}>Mismatch</Chip>
              <Chip count={5}>Incomplete</Chip>
              <div style={{ flex: 1 }} />
              <Input icon="filter" placeholder="Filter folders…" size="sm" style={{ width: 240 }} />
              <IconButton icon="more" title="Density" />
              <IconButton icon="reveal" title="Open queue location" />
            </div>

            {/* Selection bar (visible when ≥1 row is selected) */}
            <div style={{
              padding: "8px 20px", display: "flex", alignItems: "center", gap: 12,
              borderBottom: "1px solid var(--lbb-border)",
              background: "var(--lbb-accent-soft)",
              fontSize: 12,
            }}>
              <span style={{ fontWeight: 600, color: "var(--lbb-accent-mid)" }}>
                2 selected
              </span>
              <span style={{ color: "var(--lbb-fg2)" }}>· shift-click to extend · ⌘A all in view</span>
              <div style={{ flex: 1 }} />
              <Button size="sm" variant="ghost">Clear</Button>
              <Button size="sm" variant="secondary" icon="verify">Verify selected</Button>
              <Button size="sm" variant="secondary" icon="lookup">Lookup selected</Button>
              <Button size="sm" variant="primary" icon="check">Apply 2 selected renames</Button>
            </div>

            {/* Table */}
            <div style={{ flex: 1, overflow: "auto", minHeight: 0, position: "relative" }}>
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 36 }} />
                  <col />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 110 }} />
                  <col style={{ width: 140 }} />
                  <col style={{ width: 124 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH> </TH>
                    <TH><input type="checkbox" /></TH>
                    <TH>Folder</TH>
                    <TH align="center"><span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--lbb-fg2)" }}>1</span>Verify</span></TH>
                    <TH align="center"><span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--lbb-fg2)" }}>2</span>Lookup</span></TH>
                    <TH align="center"><span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--lbb-fg2)" }}>3</span>Rename</span></TH>
                    <TH align="center"><span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--lbb-fg2)" }}>4</span>LBDIR</span></TH>
                    <TH>LB#</TH>
                    <TH align="right"> </TH>
                  </tr>
                </thead>
                <tbody>
                  <GroupRow label="Need attention" count={14} expanded={true} colSpan={8} />
                  {SEED.filter(r => r.severity === "attn").map((r, i) => (
                    <TR key={"a"+i} edge={r.severity === "attn" ? "bad" : null}>
                      <TD><input type="checkbox" /></TD>
                      <TD mono style={{ color: "var(--lbb-fg)" }}>{r.name}</TD>
                      <TD align="center"><StepPill tone={r.v} label={r.v === "warn" ? "Incomplete" : "Mismatch"} /></TD>
                      <TD align="center"><StepPill tone={r.l} label={r.l === "bad" ? "Not found" : r.l === "warn" ? "Conflict" : "—"} /></TD>
                      <TD align="center"><StepPill tone={r.r} label="—" /></TD>
                      <TD align="center"><StepPill tone={r.d} label="—" /></TD>
                      <TD mono dim>{r.lb || "—"}</TD>
                      <TD align="right">
                        <Button size="sm" variant="secondary" icon="reveal">Open</Button>
                      </TD>
                    </TR>
                  ))}

                  <GroupRow label="Ready to rename" count={32} expanded={true} colSpan={8} />
                  {SEED.filter(r => r.severity === "ready").map((r, i) => (
                    <TR key={"r"+i} edge="warn" selected={r.sel}>
                      <TD><input type="checkbox" defaultChecked={r.sel} /></TD>
                      <TD mono style={{ color: "var(--lbb-fg)" }}>{r.name}</TD>
                      <TD align="center"><StepPill tone="ok" label="Pass" /></TD>
                      <TD align="center"><StepPill tone="ok" label={r.lb && r.lb.replace("LB-","")} /></TD>
                      <TD align="center"><StepPill tone="warn" label="Proposed" /></TD>
                      <TD align="center"><StepPill tone={r.d} label={r.d === "ok" ? "Pass" : "No LBDIR"} /></TD>
                      <TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
                      <TD align="right">
                        <Button size="sm" variant="primary" icon="check">Apply</Button>
                      </TD>
                    </TR>
                  ))}

                  <GroupRow label="Done" count={36} expanded={true} colSpan={8} />
                  {SEED.filter(r => r.severity === "done").map((r, i) => (
                    <TR key={"d"+i} edge="ok">
                      <TD><input type="checkbox" /></TD>
                      <TD mono style={{ color: "var(--lbb-fg2)" }}>{r.name}</TD>
                      <TD align="center"><StepPill tone="ok" label="Pass" /></TD>
                      <TD align="center"><StepPill tone="ok" label={r.lb && r.lb.replace("LB-","")} /></TD>
                      <TD align="center"><StepPill tone="ok" label="Renamed" /></TD>
                      <TD align="center"><StepPill tone="ok" label="Pass" /></TD>
                      <TD mono style={{ color: "var(--lbb-fg2)" }}>{r.lb}</TD>
                      <TD align="right">
                        <Pill tone="ok" soft>Done</Pill>
                      </TD>
                    </TR>
                  ))}
                  <tr><td colSpan={9} style={{
                    textAlign: "center", padding: "10px 0",
                    fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic",
                  }}>
                    … 67 more folders below · virtual scroll, sticky header …
                  </td></tr>
                </tbody>
              </TableShell>
            </div>
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenPipeline = ScreenPipeline;
})();
