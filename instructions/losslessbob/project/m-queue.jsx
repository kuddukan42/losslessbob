// m-queue.jsx — Queue tab · monitor studio-pc pipeline + approve batch actions

(() => {
  const { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_LargeHeader: H,
          LBM_ConnChip: ConnChip, LBM_TabBar: TabBar, LBM_GroupLabel: GroupLabel,
          LBM_Card: Card } = window;

  function Step({ label, state }) {
    const map = { done: T.ok, run: T.info, wait: T.mute };
    const c = map[state];
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
        <span style={{ width: 22, height: 22, borderRadius: 11, background: state === "wait" ? T.card2 : c.bar,
                       border: state === "wait" ? "1.5px solid " + T.fg3 : "none",
                       display: "flex", alignItems: "center", justifyContent: "center" }}>
          {state === "done" && <Ic name="check" size={13} color="#fff" sw={3} />}
          {state === "run" && <span style={{ width: 7, height: 7, borderRadius: 4, background: "#fff" }} />}
        </span>
        <span style={{ fontSize: 11, fontWeight: state === "run" ? 700 : 500,
                       color: state === "wait" ? T.fg3 : c.fg }}>{label}</span>
      </div>
    );
  }

  const RECENT = [
    { t: "2h ago",  a: "Flat-file import", tgt: "LB-16630", tone: "ok",   r: "+2,324 · Δ 5,831" },
    { t: "1d ago",  a: "Verify",           tgt: "La Crosse WI", tone: "ok",   r: "Pass · 70/70" },
    { t: "1d ago",  a: "Rename",           tgt: "7 folders", tone: "ok",   r: "Applied" },
    { t: "3d ago",  a: "Verify",           tgt: "Charlotte NC", tone: "warn", r: "18/36" },
  ];

  function ScreenQueue({ onNav }) {
    return (
      <div style={{ height: "100%", background: T.bg, position: "relative", overflow: "hidden", fontFamily: T.sf }}>
        <div style={{ height: "100%", overflowY: "auto", paddingBottom: 96 }}>
          <H title="Queue" count="studio-pc · 1 task running" right={<ConnChip state="busy" />} />

          {/* Needs you — remote approval */}
          <GroupLabel>Needs you</GroupLabel>
          <div style={{ margin: "0 16px", borderRadius: 18, overflow: "hidden",
                        background: T.warn.bg, border: "1px solid " + T.warn.bar }}>
            <div style={{ padding: "14px 16px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <Ic name="alert" size={16} color={T.warn.fg} sw={2.2} />
                <span style={{ fontSize: 13, fontWeight: 700, color: T.warn.fg }}>Approval needed</span>
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.fg }}>Apply 7 folder renames?</div>
              <div style={{ fontSize: 13.5, color: T.fg2, marginTop: 3 }}>
                Lookup matched all 7 to LB numbers. Rename to canonical form on studio-pc.
              </div>
              <div style={{ marginTop: 8, padding: "8px 11px", borderRadius: 9, background: "rgba(255,255,255,0.6)",
                            fontFamily: T.mono, fontSize: 11.5, color: T.fg2, lineHeight: 1.5 }}>
                bd2026.03.30.Waukegan.IL.flac<br/>→ 2026-03-30 Waukegan IL (LB-16590)
              </div>
            </div>
            <div style={{ display: "flex", gap: 0, borderTop: "1px solid " + T.warn.bar }}>
              <button style={{ all: "unset", cursor: "pointer", flex: 1, textAlign: "center", padding: "12px 0",
                               fontSize: 15.5, fontWeight: 600, color: T.fg2, borderRight: "1px solid " + T.warn.bar }}>Review</button>
              <button style={{ all: "unset", cursor: "pointer", flex: 1, textAlign: "center", padding: "12px 0",
                               fontSize: 15.5, fontWeight: 800, color: T.accent }}>Approve</button>
            </div>
          </div>

          {/* Running now */}
          <GroupLabel right={<span style={{ fontSize: 13, color: T.fg3, fontWeight: 600 }}>Pause all</span>}>Running now</GroupLabel>
          <Card>
            <div style={{ padding: "14px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Pill tone="info" dot>Pipeline</Pill>
                <span style={{ flex: 1, fontFamily: T.mono, fontSize: 13, color: T.fg, fontWeight: 600,
                               overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>bd2026-03-27 La Crosse WI</span>
                <Ic name="pause" size={18} color={T.fg3} />
              </div>
              {/* progress */}
              <div style={{ marginTop: 12, height: 6, borderRadius: 3, background: T.card2, overflow: "hidden" }}>
                <div style={{ width: "62%", height: "100%", background: T.accent, borderRadius: 3 }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 12.5, color: T.fg2 }}>
                <span>Lookup · matching checksums</span>
                <span style={{ fontFamily: T.mono }}>43 / 70</span>
              </div>
              {/* steps */}
              <div style={{ display: "flex", marginTop: 16, position: "relative" }}>
                <div style={{ position: "absolute", top: 11, left: "12%", right: "12%", height: 1.5, background: T.sep }} />
                <Step label="Verify" state="done" />
                <Step label="Lookup" state="run" />
                <Step label="Rename" state="wait" />
                <Step label="LBDIR" state="wait" />
              </div>
            </div>
          </Card>

          {/* Recent */}
          <GroupLabel right={<span style={{ fontSize: 13, color: T.accent, fontWeight: 600 }}>Full log →</span>}>Recent</GroupLabel>
          <Card style={{ marginBottom: 18 }}>
            {RECENT.map((r, i, a) => {
              const c = T[r.tone];
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 11, padding: "12px 16px", position: "relative" }}>
                  <span style={{ width: 8, height: 8, borderRadius: 4, background: c.bar, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, color: T.fg }}>{r.a} · <span style={{ color: T.fg2, fontWeight: 500 }}>{r.tgt}</span></div>
                    <div style={{ fontSize: 12.5, color: T.fg3, fontFamily: T.mono, marginTop: 1 }}>{r.t}</div>
                  </div>
                  <Pill tone={r.tone} soft>{r.r}</Pill>
                  {i < a.length - 1 && <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
                </div>
              );
            })}
          </Card>
        </div>

        <TabBar active="queue" onNav={onNav} badge="2" />
      </div>
    );
  }

  window.LBM_ScreenQueue = ScreenQueue;
})();
