// screen-rename.jsx
// Rename · Apply canonical names to folders, populated from the last Lookup run.
// 5 row states: has_lb (green), needs_rename (orange), wrong_lb (purple),
// multiple_ids (cyan), no_match (red).

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD, GroupRow } = window;

  // Visual mapping of the 5 row states.
  const STATES = {
    has_lb:       { tone: "ok",   color: "var(--lbb-ok-bar)",   label: "LB# already in name",  bg: "#dff0d8" },
    renamed:      { tone: "ok",   color: "var(--lbb-ok-bar)",   label: "Renamed",              bg: "#dff0d8" },
    needs_rename: { tone: "warn", color: "var(--lbb-warn-bar)", label: "Will rename",          bg: "#ffe0b2" },
    wrong_lb:     { tone: "info", color: "#7a3fb1",             label: "Wrong LB · strip + rename", bg: "#e1beE7" },
    multiple_ids: { tone: "info", color: "#2b8b9a",             label: "Multiple LBs · review", bg: "#b2EBF2" },
    no_match:     { tone: "bad",  color: "var(--lbb-bad-bar)",  label: "No match",             bg: "#ffcdd2" },
  };

  // Resolution source — how we picked the LB#
  const RESOLUTION = {
    link:     { icon: "link",   label: "folder_lb_link · pinned" },
    alias:    { icon: "shield", label: "lb_alias collapse" },
    single:   { icon: "check",  label: "single match" },
    multiple: { icon: "search", label: "ambiguous · review" },
    none:     { icon: "x",      label: "no candidates" },
  };

  // Sample rows — covers every state.
  const ROWS = [
    { sel: true,  state: "has_lb",       cur: "1982-06-06 PASADENA, CA (LB-08621)",   prop: "(no change)",                                          lb: "LB-8621",   res: "link",     hint: "Found via path link to LB-8621",    aliases: [] },
    { sel: true,  state: "needs_rename", cur: "bd2026.03.30.Waukegan.IL.flac",        prop: "bd2026.03.30.Waukegan.IL.flac-LB-16590",               lb: "LB-16590",  res: "single",   hint: "Single complete match in master DB", aliases: [] },
    { sel: true,  state: "needs_rename", cur: "bd2026-04-02 Madison WI",              prop: "bd2026-04-02 Madison WI (LB-16591)",                   lb: "LB-16591",  res: "single",   hint: "Single complete match in master DB", aliases: [] },
    { sel: true,  state: "needs_rename", cur: "bd2026-04-05 Minneapolis MN",          prop: "bd2026-04-05 Minneapolis MN (LB-16592)",               lb: "LB-16592",  res: "single",   hint: "Single complete match in master DB", aliases: [] },
    { sel: true,  state: "needs_rename", cur: "bd2026-04-12 Detroit MI",              prop: "bd2026-04-12 Detroit MI (LB-16594) (LB-16594a)",       lb: "LB-16594",  res: "alias",    hint: "Collapsed via lb_alias · 2 aliases", aliases: ["LB-16594a"] },
    { sel: true,  state: "needs_rename", cur: "bd2026-04-22 Philadelphia PA",         prop: "bd2026-04-22 Philadelphia PA (LB-16597)",              lb: "LB-16597",  res: "single",   hint: "Single complete match in master DB", aliases: [] },
    { sel: true,  state: "needs_rename", cur: "bd2026-04-25 New York NY (Beacon)",    prop: "bd2026-04-25 New York NY (Beacon) (LB-16598)",         lb: "LB-16598",  res: "single",   hint: "Single complete match in master DB", aliases: [] },
    { sel: false, state: "multiple_ids", cur: "bd2026-04-19 Pittsburgh PA",           prop: "(select LB# to populate)",                              lb: "LB-16596?", res: "multiple", hint: "3 candidate LBs · resolve below",     aliases: ["LB-16596", "LB-16596b", "LB-16604"] },
    { sel: false, state: "no_match",     cur: "bd2025-07-25 Alpharetta GA FLAC",      prop: "(no change)",                                          lb: "—",         res: "none",     hint: "0 checksums matched · run Lookup first", aliases: [] },
    { sel: false, state: "wrong_lb",     cur: "1987-05-xx Dead Dylan Rehearsals (LB-1)", prop: "1987-05-xx Dead Dylan Rehearsals (LB-2)",          lb: "LB-2",      res: "single",   hint: "Folder labelled LB-1, checksums match LB-2", aliases: [] },
  ];

  function StateChip({ state, count, active, onClick }) {
    const s = STATES[state];
    return (
      <button onClick={onClick}
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "3px 10px", borderRadius: 999,
          border: `1px solid ${active ? s.color : "var(--lbb-border2)"}`,
          background: active ? `var(--lbb-${s.tone}-bg)` : "var(--lbb-surface)",
          color: active ? `var(--lbb-${s.tone}-fg)` : "var(--lbb-fg2)",
          fontFamily: "inherit", fontSize: 11.5, fontWeight: active ? 600 : 500, cursor: "pointer",
        }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color }} />
        {s.label}
        <span style={{ fontSize: 10, opacity: 0.65, marginLeft: 2 }}>{count}</span>
      </button>
    );
  }

  function ScreenRename() {
    const [filter, setFilter] = React.useState(null);
    const [expandedRow, setExpandedRow] = React.useState(null);

    const counts = ROWS.reduce((a, r) => { a[r.state] = (a[r.state] || 0) + 1; return a; }, {});
    const selected = ROWS.filter(r => r.sel).length;

    const visible = filter ? ROWS.filter(r => r.state === filter) : ROWS;

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Header */}
        <div style={{
          padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="rename" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Rename</h1>
              <Pill tone="mute" soft>{ROWS.length} folders · auto-populated from Lookup</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              Append <span style={{ fontFamily: "var(--lbb-mono)" }}>(LB-XXXXX)</span> to verified folders. Reversible from Recent activity for 30 days.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" icon="refresh">Re-resolve from Lookup</Button>
        </div>

        {/* State chips */}
        <div style={{
          padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
        }}>
          <button onClick={() => setFilter(null)}
            style={{
              padding: "3px 10px", borderRadius: 999,
              border: `1px solid ${!filter ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
              background: !filter ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
              color: !filter ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
              fontFamily: "inherit", fontSize: 11.5, fontWeight: !filter ? 600 : 500, cursor: "pointer",
            }}>All <span style={{ fontSize: 10, opacity: 0.65, marginLeft: 4 }}>{ROWS.length}</span></button>
          {Object.keys(STATES).filter(k => k !== "renamed" && counts[k]).map(k =>
            <StateChip key={k} state={k} count={counts[k] || 0} active={filter === k} onClick={() => setFilter(filter === k ? null : k)} />
          )}
        </div>

        {/* Bulk action bar */}
        <div style={{
          padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)",
          background: selected > 0 ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ fontSize: 12, color: selected > 0 ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)", fontWeight: 600 }}>
            {selected} of {ROWS.length} selected
          </span>
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>· shift-click to extend · ⌘A all in view</span>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm">Clear</Button>
          <Button variant="secondary" size="sm">Select all confident</Button>
          <Button variant="secondary" size="sm">Select wrong LB</Button>
          <Button variant="primary" size="sm" icon="check" disabled={selected === 0}>Apply {selected} renames</Button>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
          <div style={{ padding: "16px 24px" }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 32 }} />
                <col /><col style={{ width: 24 }} /><col />
                <col style={{ width: 130 }} /><col style={{ width: 220 }} />
                <col style={{ width: 36 }} />
              </colgroup>
              <thead><tr>
                <TH> </TH>
                <TH><input type="checkbox" /></TH>
                <TH>Current name</TH>
                <TH> </TH>
                <TH>Proposed name</TH>
                <TH>LB#</TH>
                <TH>State / resolution</TH>
                <TH> </TH>
              </tr></thead>
              <tbody>
                {visible.map((r, i) => {
                  const s = STATES[r.state];
                  const res = RESOLUTION[r.res];
                  const expanded = expandedRow === i;
                  return (
                    <React.Fragment key={i}>
                      <TR edge={s.tone} selected={r.sel}>
                        <TD><input type="checkbox" defaultChecked={r.sel} disabled={r.state === "no_match"} /></TD>
                        <TD mono style={{ color: "var(--lbb-fg)" }}>{r.cur}</TD>
                        <TD align="center"><Icon name="chevRight" size={12} style={{ color: "var(--lbb-fg3)" }} /></TD>
                        <TD mono style={{
                          color: r.state === "no_match" ? "var(--lbb-fg3)" : r.state === "has_lb" ? "var(--lbb-fg3)" : r.state === "wrong_lb" ? "var(--lbb-bad-fg)" : "var(--lbb-ok-fg)",
                          fontStyle: r.prop.startsWith("(") ? "italic" : "normal",
                        }}>{r.prop}</TD>
                        <TD mono style={{ color: r.lb === "—" ? "var(--lbb-fg3)" : "var(--lbb-accent-mid)", fontWeight: 600 }}>
                          {r.res === "link" && r.lb !== "—" && <Icon name="link" size={10} style={{ marginRight: 4, color: "var(--lbb-accent-mid)" }} />}
                          {r.lb}
                        </TD>
                        <TD>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <Pill tone={s.tone} soft dot={r.state !== "has_lb" && r.state !== "renamed"}>{s.label}</Pill>
                          </div>
                          <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 3, display: "flex", alignItems: "center", gap: 4 }}>
                            <Icon name={res.icon} size={9} /> {r.hint}
                          </div>
                        </TD>
                        <TD>
                          {(r.state === "multiple_ids" || r.state === "wrong_lb") && (
                            <IconButton icon={expanded ? "chevDown" : "chevRight"} title="Disambiguate" onClick={() => setExpandedRow(expanded ? null : i)} />
                          )}
                        </TD>
                      </TR>
                      {expanded && r.state === "multiple_ids" && (
                        <tr>
                          <td colSpan={8} style={{ padding: 0 }}>
                            <div style={{
                              padding: "14px 16px 16px 56px",
                              background: "var(--lbb-info-bg)", borderBottom: "1px solid var(--lbb-border)",
                            }}>
                              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-info-fg)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>
                                Disambiguate · pick one
                              </div>
                              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {r.aliases.map((alias, j) => (
                                  <label key={j} style={{
                                    display: "flex", alignItems: "center", gap: 12, padding: "8px 12px",
                                    background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 6,
                                    cursor: "pointer", fontSize: 12,
                                  }}>
                                    <input type="radio" name={`disamb-${i}`} />
                                    <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600, color: "var(--lbb-accent-mid)", width: 100 }}>{alias}</span>
                                    <span style={{ color: "var(--lbb-fg2)", flex: 1 }}>
                                      {j === 0 ? "1981-04-19 · Pittsburgh PA · Civic Arena · 7 checksums match" :
                                       j === 1 ? "1981-04-19 · Pittsburgh PA · Civic Arena · alt source · 4 checksums match" :
                                                  "2004-04-19 · Pittsburgh PA · Mellon Arena · 0 checksums match (location-only)"}
                                    </span>
                                    <Button size="sm" variant="ghost" icon="reveal">LB.com</Button>
                                  </label>
                                ))}
                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                                  <Button size="sm" variant="primary" icon="check">Pin selection · update folder_lb_link</Button>
                                  <Button size="sm" variant="ghost">Mark as new entry…</Button>
                                  <Button size="sm" variant="ghost">Skip for now</Button>
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </TableShell>

            {/* Dry-run banner */}
            <div style={{
              marginTop: 16, padding: "12px 16px", borderRadius: 6,
              background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)",
              fontSize: 12, color: "var(--lbb-fg2)",
              display: "flex", alignItems: "flex-start", gap: 12,
            }}>
              <Icon name="info" size={14} style={{ color: "var(--lbb-info-fg)", marginTop: 1 }} />
              <div style={{ flex: 1 }}>
                <strong style={{ color: "var(--lbb-info-fg)" }}>Dry-run preview</strong> — nothing is renamed until you click <em>Apply selected</em>.
                Renames write to <span style={{ fontFamily: "var(--lbb-mono)" }}>rename_history</span> and are reversible from <strong>Recent activity</strong> for 30 days.
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Button size="sm" variant="ghost" icon="copy">Copy diff…</Button>
                <Button size="sm" variant="secondary" icon="download">Export plan…</Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  window.LBB_ScreenRename = ScreenRename;
})();
