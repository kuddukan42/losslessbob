// m-map.jsx — Map tab · browse shows by place / date

(() => {
  const { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_TabBar: TabBar } = window;

  // fake pins on an abstract map
  const PINS = [
    { x: 28, y: 34, n: 12, label: "London", hot: true },
    { x: 20, y: 30, n: 4,  label: "Manchester" },
    { x: 64, y: 46, n: 31, label: "New York" },
    { x: 57, y: 52, n: 18, label: "Chicago" },
    { x: 48, y: 60, n: 7,  label: "Atlanta" },
    { x: 78, y: 40, n: 5,  label: "Boston" },
    { x: 42, y: 44, n: 9,  label: "Denver" },
  ];

  function ScreenMap({ onNav, onOpen }) {
    return (
      <div style={{ height: "100%", background: T.bg, position: "relative", overflow: "hidden", fontFamily: T.sf }}>
        {/* Map canvas */}
        <div style={{ position: "absolute", inset: 0, background:
          "radial-gradient(120% 90% at 50% 0%, #dfe7ec 0%, #cdd6cf 55%, #c2ccc0 100%)" }}>
          {/* faux landmass blobs */}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.5 }}>
            <path d="M10 22 Q22 14 34 24 Q40 40 28 48 Q14 44 10 34 Z" fill="#aebfa6" />
            <path d="M40 36 Q60 28 84 38 Q90 52 74 64 Q52 70 44 56 Q38 46 40 36 Z" fill="#aebfa6" />
            <path d="M0 70 Q20 64 30 76 L30 100 L0 100 Z" fill="#aebfa6" opacity="0.7" />
          </svg>
          {/* grid */}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.3 }}>
            {[20,40,60,80].map(v => <line key={"h"+v} x1="0" y1={v} x2="100" y2={v} stroke="#7d8a7a" strokeWidth="0.3" />)}
            {[20,40,60,80].map(v => <line key={"v"+v} x1={v} y1="0" x2={v} y2="100" stroke="#7d8a7a" strokeWidth="0.3" />)}
          </svg>
          {/* pins */}
          {PINS.map((p, i) => (
            <div key={i} style={{ position: "absolute", left: p.x + "%", top: p.y + "%", transform: "translate(-50%,-100%)" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <span style={{ minWidth: p.hot ? 36 : 30, height: p.hot ? 36 : 30, padding: "0 5px",
                               borderRadius: 18, background: p.hot ? T.accent : T.card,
                               color: p.hot ? "#fff" : T.fg, border: p.hot ? "none" : "1.5px solid " + T.accent,
                               display: "flex", alignItems: "center", justifyContent: "center",
                               fontSize: p.hot ? 15 : 13, fontWeight: 800, fontVariantNumeric: "tabular-nums",
                               boxShadow: "0 3px 8px rgba(0,0,0,0.22)" }}>{p.n}</span>
                <span style={{ width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent",
                               borderTop: "7px solid " + (p.hot ? T.accent : T.card), marginTop: -1 }} />
              </div>
            </div>
          ))}
        </div>

        {/* Glass header */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, padding: "54px 16px 12px",
                      background: "linear-gradient(180deg, rgba(239,236,227,0.92), rgba(239,236,227,0))" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, letterSpacing: -0.5, color: T.fg }}>Concerts</h1>
            <button style={{ all: "unset", cursor: "pointer", height: 34, padding: "0 13px", borderRadius: 17, background: T.card,
                             display: "flex", alignItems: "center", gap: 6, fontSize: 13.5, fontWeight: 600, color: T.fg2,
                             boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
              <Ic name="cal" size={15} color={T.fg2} sw={2} /> All years
            </button>
          </div>
          <div style={{ marginTop: 11, display: "flex", alignItems: "center", gap: 9, background: T.card,
                        borderRadius: 12, padding: "0 12px", height: 40, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
            <Ic name="search" size={17} color={T.fg3} sw={2.2} />
            <span style={{ fontSize: 16, color: T.fg3, flex: 1 }}>Place, venue, or tour…</span>
          </div>
        </div>

        {/* Bottom sheet — selected city */}
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 84, zIndex: 30 }}>
          <div style={{ margin: "0 12px", background: T.card, borderRadius: 20, padding: "14px 16px 16px",
                        boxShadow: "0 8px 28px rgba(0,0,0,0.18)" }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: T.sep, margin: "0 auto 12px" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Ic name="pinSmall" size={20} color={T.accent} sw={2} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: T.fg, letterSpacing: -0.3 }}>New York, NY</div>
                <div style={{ fontSize: 13, color: T.fg2 }}>31 shows · 1961–2019 · 28 owned</div>
              </div>
              <Pill tone="ok" soft>90% owned</Pill>
            </div>
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                { lb: "LB-998",  v: "Madison Square Garden", d: "1974-01-30", own: true },
                { lb: "LB-7420", v: "Carnegie Hall", d: "1963-10-26", own: true },
                { lb: "LB-1971", v: "Town Hall (alt)", d: "1963-04-12", own: false },
              ].map((s, i, a) => (
                <button key={s.lb} onClick={() => onOpen && onOpen(s.lb)} style={{ all: "unset", cursor: "pointer",
                              display: "flex", alignItems: "center", gap: 11, padding: "10px 0", position: "relative" }}>
                  <span style={{ width: 3.5, alignSelf: "stretch", borderRadius: 2, background: s.own ? T.ok.bar : T.bad.bar }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, color: T.fg }}>{s.v}</div>
                    <div style={{ fontSize: 12.5, color: T.fg2, fontFamily: T.mono }}>{s.d} · {s.lb}</div>
                  </div>
                  {s.own ? <Pill tone="ok" soft>Owned</Pill> : <Pill tone="bad" dot>Missing</Pill>}
                  {i < a.length - 1 && <span style={{ position: "absolute", left: 14, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
                </button>
              ))}
            </div>
          </div>
        </div>

        <TabBar active="map" onNav={onNav} badge="2" />
      </div>
    );
  }

  window.LBM_ScreenMap = ScreenMap;
})();
