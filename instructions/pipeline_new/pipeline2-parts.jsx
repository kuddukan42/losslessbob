// pipeline2-parts.jsx
// Shared atoms for the refined Pipeline Workspace. All states route through
// LBB_P2.STATE so the vocabulary + color is identical everywhere.

(() => {
  const Icon = window.LBB_Icon;
  const { STATE } = window.LBB_P2;
  const { Pill } = window;

  // ── tiny state glyph (check / ! / x / pending dot / spinner) ───────
  function StateGlyph({ state, size = 12 }) {
    const tone = STATE[state].tone;
    const col = `var(--lbb-${tone}-fg)`;
    if (state === "pass")    return <Icon name="check" size={size} style={{ color: col }} />;
    if (state === "blocked") return <Icon name="x" size={size} style={{ color: col }} />;
    if (state === "action")  return <span style={{ fontWeight: 800, fontSize: size, color: col, lineHeight: 1, fontFamily: "var(--lbb-mono)" }}>!</span>;
    if (state === "running") return <span className="p2-spin" style={{
      width: size, height: size, borderRadius: "50%",
      border: `2px solid color-mix(in oklab, ${col} 30%, transparent)`,
      borderTopColor: col, display: "inline-block",
    }} />;
    return <span style={{ width: size - 4, height: size - 4, borderRadius: "50%", border: `1.5px solid var(--lbb-fg3)` }} />;
  }

  // ── StatusTag — the one badge used for every stage everywhere ───────
  function StatusTag({ state, children, soft = true, style }) {
    const s = STATE[state];
    return (
      <Pill tone={s.tone} soft={soft} style={{ gap: 5, ...style }}>
        <span style={{ display: "inline-flex", width: 12, justifyContent: "center" }}><StateGlyph state={state} size={11} /></span>
        {children || s.label}
      </Pill>
    );
  }

  // ── StageNode — one circle in the tracker ──────────────────────────
  function StageNode({ stage, state, current, n }) {
    const tone = STATE[state].tone;
    const filled = state === "pass" || state === "action" || state === "blocked";
    const bg = filled ? `var(--lbb-${tone}-bar)` : "var(--lbb-surface)";
    const fg = filled ? "#fff" : (state === "running" ? `var(--lbb-info-fg)` : "var(--lbb-fg3)");
    const border = state === "pending" ? "var(--lbb-border2)"
                 : state === "running" ? "var(--lbb-info-bar)"
                 : `var(--lbb-${tone}-bar)`;
    return (
      <span title={`${stage.label}: ${STATE[state].label}`} style={{
        position: "relative", width: 22, height: 22, borderRadius: "50%",
        background: bg, border: `1.5px solid ${border}`, color: fg,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        flex: "0 0 22px", zIndex: 1,
        boxShadow: current ? `0 0 0 3px var(--lbb-accent-soft)` : "none",
      }}>
        {state === "pass"    ? <Icon name="check" size={12} />
        : state === "blocked" ? <Icon name="x" size={11} />
        : state === "action"  ? <span style={{ fontWeight: 800, fontSize: 12, lineHeight: 1 }}>!</span>
        : state === "running" ? <span className="p2-spin" style={{ width: 11, height: 11, borderRadius: "50%", border: "2px solid color-mix(in oklab, var(--lbb-info-fg) 30%, transparent)", borderTopColor: "var(--lbb-info-fg)" }} />
        : <span style={{ fontSize: 10.5, fontWeight: 700 }}>{n}</span>}
      </span>
    );
  }

  // ── StageTracker — the 4-segment glanceable progress object ────────
  // Replaces the four differently-worded pills. Connector after a node is
  // "ok" once that node has passed.
  function StageTracker({ folder, stages, currentKey, onPick }) {
    return (
      <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
        {stages.map((st, i) => {
          const state = folder.steps[st.key].state;
          const next = stages[i + 1];
          const connectorOk = state === "pass";
          return (
            <React.Fragment key={st.key}>
              <button
                type="button"
                onClick={onPick ? (e) => { e.stopPropagation(); onPick(st.key); } : undefined}
                style={{
                  background: "none", border: "none", padding: 0, cursor: onPick ? "pointer" : "default",
                  display: "inline-flex", alignItems: "center",
                }}>
                <StageNode stage={st} state={state} current={currentKey === st.key} n={st.n} />
              </button>
              {next && (
                <span style={{
                  flex: 1, height: 2, minWidth: 14, margin: "0 2px",
                  background: connectorOk ? "var(--lbb-ok-bar)" : "var(--lbb-border2)",
                  borderRadius: 2,
                }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  }

  // ── StageStepper — large clickable stepper for the detail header ────
  function StageStepper({ folder, stages, activeKey, onPick }) {
    return (
      <div style={{ display: "flex", alignItems: "stretch", width: "100%" }}>
        {stages.map((st, i) => {
          const state = folder.steps[st.key].state;
          const active = activeKey === st.key;
          const next = stages[i + 1];
          const s = STATE[state];
          return (
            <React.Fragment key={st.key}>
              <button type="button" onClick={() => onPick(st.key)} style={{
                flex: "0 0 auto", display: "flex", alignItems: "center", gap: 10,
                padding: "8px 12px", borderRadius: 8, cursor: "pointer",
                background: active ? "var(--lbb-accent-soft)" : "transparent",
                border: `1px solid ${active ? "var(--lbb-accent-mid)" : "transparent"}`,
                fontFamily: "inherit", textAlign: "left",
              }}>
                <StageNode stage={st} state={state} current={active} n={st.n} />
                <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg)", letterSpacing: -0.01 }}>{st.label}</span>
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: `var(--lbb-${s.tone}-fg)`, letterSpacing: 0.02 }}>{s.label}</span>
                </span>
              </button>
              {next && (
                <span style={{ flex: 1, minWidth: 24, alignSelf: "center", height: 2,
                  background: state === "pass" ? "var(--lbb-ok-bar)" : "var(--lbb-border2)", borderRadius: 2 }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  }

  // ── QueueRow — folder in the left rail ─────────────────────────────
  function QueueRow({ folder, active, onClick }) {
    const { BUCKET } = window.LBB_P2;
    const b = BUCKET[folder.bucket];
    const name = folder.name;
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 9,
        padding: "8px 10px", marginBottom: 2, borderRadius: 7,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: `1px solid ${active ? "var(--lbb-accent-mid)" : "transparent"}`,
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}
      onMouseEnter={e => !active && (e.currentTarget.style.background = "var(--lbb-surface2)")}
      onMouseLeave={e => !active && (e.currentTarget.style.background = "transparent")}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: `var(--lbb-${b.tone}-bar)`, flex: "0 0 8px" }} />
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{name}</span>
          <span style={{ fontSize: 10, color: `var(--lbb-${b.tone}-fg)`, fontWeight: 600, letterSpacing: 0.02 }}>
            {folder.bucket === "running" && folder.progress
              ? `Verifying ${folder.progress.done}/${folder.progress.total}…`
              : folder.lb ? `${b.label} · ${folder.lb}` : b.label}
          </span>
        </span>
      </button>
    );
  }

  window.LBB_P2_Parts = { StateGlyph, StatusTag, StageNode, StageTracker, StageStepper, QueueRow };
})();
