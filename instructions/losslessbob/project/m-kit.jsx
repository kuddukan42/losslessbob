// m-kit.jsx — shared iOS primitives + theme for LosslessBob Mobile.
// Warm-tinted iOS look that matches the desktop app identity.

(() => {
  const T = {
    bg:       "#efece3",   // grouped background, warm
    card:     "#ffffff",
    card2:    "#f6f4ee",
    fg:       "#1c1a17",
    fg2:      "#6f685b",
    fg3:      "#a39b8a",
    sep:      "rgba(60,55,45,0.12)",
    accent:   "#2b5fd0",
    accentSoft:"#e6ecf9",
    mono:     'ui-monospace, "SF Mono", Menlo, monospace',
    sf:       '-apple-system, "SF Pro Text", system-ui, sans-serif',
    ok:   { fg:"#1f7a3e", bar:"#39a360", bg:"#e7f2e2" },
    warn: { fg:"#9a6800", bar:"#cc9f3d", bg:"#f8eed3" },
    bad:  { fg:"#b03f30", bar:"#d8604f", bg:"#fbe6df" },
    info: { fg:"#1f5b8f", bar:"#4c89c4", bg:"#e2ecf6" },
    mute: { fg:"#857d6b", bar:"#a8a293", bg:"#ecebe4" },
  };

  // ── Icons (simple line glyphs) ──────────────────────────────
  function Ic({ name, size = 24, color = "currentColor", sw = 2, fill = false }) {
    const p = { fill: "none", stroke: color, strokeWidth: sw, strokeLinecap: "round", strokeLinejoin: "round" };
    const paths = {
      library:  <><rect x="3" y="4" width="18" height="16" rx="2.5" {...p}/><path d="M3 9h18M8 13h9M8 16.5h6" {...p}/></>,
      search:   <><circle cx="11" cy="11" r="7" {...p}/><path d="M16.5 16.5L21 21" {...p}/></>,
      queue:    <><rect x="3" y="5" width="18" height="5" rx="2" {...p}/><rect x="3" y="14" width="12" height="5" rx="2" {...p}/></>,
      map:      <><path d="M12 21s7-6.5 7-12a7 7 0 10-14 0c0 5.5 7 12 7 12z" {...p}/><circle cx="12" cy="9" r="2.4" {...p}/></>,
      chevR:    <path d="M9 5l7 7-7 7" {...p}/>,
      chevL:    <path d="M15 5l-7 7 7 7" {...p}/>,
      chevDown: <path d="M5 9l7 7 7-7" {...p}/>,
      more:     <><circle cx="5" cy="12" r="1.6" fill={color} stroke="none"/><circle cx="12" cy="12" r="1.6" fill={color} stroke="none"/><circle cx="19" cy="12" r="1.6" fill={color} stroke="none"/></>,
      check:    <path d="M5 12.5l4.5 4.5L19 6.5" {...p}/>,
      x:        <path d="M6 6l12 12M18 6L6 18" {...p}/>,
      plus:     <path d="M12 5v14M5 12h14" {...p}/>,
      star:     <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 17l-5.2 2.6 1-5.8-4.3-4.1 5.9-.9z" {...p}/>,
      wave:     <path d="M3 12h2.5l2-6 3 14 3-10 2 4 2-2h3.5" {...p}/>,
      spectro:  <><rect x="3" y="4" width="18" height="16" rx="2" {...p}/><path d="M6 14l2-4 2 6 2-9 2 5 2-2 2 3" {...p} strokeWidth="1.4"/></>,
      attach:   <path d="M19 11l-7.5 7.5a4 4 0 01-5.6-5.6L13 5.4a2.6 2.6 0 013.7 3.7l-7 7a1.2 1.2 0 01-1.7-1.7L14 8" {...p}/>,
      forum:    <path d="M4 5h16v10H9l-4 4v-4H4z" {...p}/>,
      download: <><path d="M12 4v11m0 0l-4-4m4 4l4-4" {...p}/><path d="M5 20h14" {...p}/></>,
      play:     <path d="M7 5l11 7-11 7z" {...p} fill={fill?color:"none"}/>,
      pause:    <><rect x="7" y="5" width="3.5" height="14" rx="1" fill={color} stroke="none"/><rect x="13.5" y="5" width="3.5" height="14" rx="1" fill={color} stroke="none"/></>,
      alert:    <><path d="M12 4l9 16H3z" {...p}/><path d="M12 10v4M12 17h.01" {...p}/></>,
      wifi:     <><path d="M2.5 9a14 14 0 0119 0M5.5 12.5a9 9 0 0113 0M8.5 16a4.5 4.5 0 017 0" {...p}/><circle cx="12" cy="19" r="1.1" fill={color} stroke="none"/></>,
      bolt:     <path d="M13 3L5 13h6l-1 8 8-10h-6z" {...p} fill={fill?color:"none"}/>,
      disc:     <><circle cx="12" cy="12" r="8.5" {...p}/><circle cx="12" cy="12" r="2.2" {...p}/></>,
      cal:      <><rect x="4" y="5" width="16" height="15" rx="2" {...p}/><path d="M4 9h16M8 3v4M16 3v4" {...p}/></>,
      pinSmall: <path d="M12 21s6-5.5 6-10.5A6 6 0 106 10.5C6 15.5 12 21 12 21z" {...p}/>,
      filter:   <path d="M4 6h16M7 12h10M10 18h4" {...p}/>,
      back:     <path d="M14 6l-6 6 6 6" {...p}/>,
      reveal:   <><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" {...p}/></>,
      scan:     <><path d="M4 8V6a2 2 0 012-2h2M16 4h2a2 2 0 012 2v2M20 16v2a2 2 0 01-2 2h-2M8 20H6a2 2 0 01-2-2v-2" {...p}/><path d="M4 12h16" {...p} strokeWidth="1.6"/></>,
    };
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: "block", flexShrink: 0 }}>
        {paths[name] || null}
      </svg>
    );
  }

  // ── Status pill ─────────────────────────────────────────────
  function Pill({ tone = "mute", children, soft = true, dot = false, style = {} }) {
    const c = T[tone] || T.mute;
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        height: 22, padding: "0 9px", borderRadius: 11,
        background: soft ? c.bg : c.bar, color: soft ? c.fg : "#fff",
        fontSize: 12, fontWeight: 600, letterSpacing: 0.1,
        fontFamily: T.sf, whiteSpace: "nowrap", ...style,
      }}>
        {dot && <span style={{ width: 6, height: 6, borderRadius: 3, background: c.bar }} />}
        {children}
      </span>
    );
  }

  // ── Status-edge entry row (for lists) ───────────────────────
  function EntryRow({ lb, title, sub, tone = "ok", right, onClick, last }) {
    const c = T[tone] || T.mute;
    return (
      <button onClick={onClick} style={{
        all: "unset", boxSizing: "border-box", cursor: "pointer",
        display: "flex", alignItems: "center", gap: 12, width: "100%",
        padding: "11px 16px 11px 14px", position: "relative",
        fontFamily: T.sf,
      }}>
        <span style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3.5, borderRadius: 2, background: c.bar }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.accent }}>{lb}</span>
            {right}
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: T.fg, marginTop: 2, letterSpacing: -0.2,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{title}</div>
          <div style={{ fontSize: 13, color: T.fg2, marginTop: 1,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>
        </div>
        <Ic name="chevR" size={16} color={T.fg3} sw={2.4} />
        {!last && <span style={{ position: "absolute", left: 14, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
      </button>
    );
  }

  // ── Large title header (clears status bar / island) ─────────
  function LargeHeader({ title, count, right, search }) {
    return (
      <div style={{ padding: "56px 16px 0", fontFamily: T.sf }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 32, fontWeight: 800, letterSpacing: -0.6, color: T.fg, lineHeight: 1.05 }}>{title}</h1>
            {count && <div style={{ fontSize: 13.5, color: T.fg2, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{count}</div>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 4 }}>{right}</div>
        </div>
        {search && (
          <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 9,
                        background: "rgba(118,110,95,0.12)", borderRadius: 12, padding: "0 12px", height: 38 }}>
            <Ic name="search" size={17} color={T.fg3} sw={2.2} />
            <span style={{ fontSize: 16, color: T.fg3, flex: 1 }}>{typeof search === "string" ? search : "Search"}</span>
          </div>
        )}
      </div>
    );
  }

  // ── Compact nav header with back ────────────────────────────
  function NavHeader({ title, right }) {
    return (
      <div style={{ paddingTop: 50, fontFamily: T.sf }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "0 8px 0 6px", height: 44 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 1, color: T.accent,
                          fontSize: 17, fontWeight: 500 }}>
            <Ic name="back" size={26} color={T.accent} sw={2.4} />
            <span style={{ marginLeft: -2 }}>Library</span>
          </span>
          <span style={{ fontSize: 16, fontWeight: 700, color: T.fg, position: "absolute", left: 0, right: 0,
                          textAlign: "center", pointerEvents: "none" }}>{title}</span>
          <span style={{ display: "flex", gap: 6 }}>{right}</span>
        </div>
      </div>
    );
  }

  // ── Connection chip (subtle) ────────────────────────────────
  function ConnChip({ state = "online" }) {
    const map = {
      online:  { c: T.ok,   label: "studio-pc", icon: "wifi" },
      offline: { c: T.mute, label: "Offline · cached", icon: "bolt" },
      busy:    { c: T.info, label: "studio-pc", icon: "wifi" },
    };
    const m = map[state] || map.online;
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 30, padding: "0 11px",
                     borderRadius: 15, background: T.card, boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                     fontFamily: T.sf, fontSize: 13, fontWeight: 600, color: T.fg2 }}>
        <span style={{ width: 7, height: 7, borderRadius: 4, background: m.c.bar }} />
        {m.label}
      </span>
    );
  }

  // ── Bottom tab bar ──────────────────────────────────────────
  function TabBar({ active = "library", onNav, badge }) {
    const tabs = [
      { id: "library", label: "Library", icon: "library" },
      { id: "search",  label: "Search",  icon: "search" },
      { id: "queue",   label: "Queue",   icon: "queue" },
      { id: "map",     label: "Map",     icon: "map" },
    ];
    return (
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 40,
        paddingBottom: 22, paddingTop: 9, fontFamily: T.sf,
        background: "rgba(247,245,239,0.82)", backdropFilter: "blur(18px) saturate(180%)",
        WebkitBackdropFilter: "blur(18px) saturate(180%)",
        borderTop: "0.5px solid " + T.sep,
        display: "flex", justifyContent: "space-around",
      }}>
        {tabs.map(tb => {
          const on = tb.id === active;
          return (
            <button key={tb.id} onClick={() => onNav && onNav(tb.id)} style={{
              all: "unset", cursor: "pointer", flex: 1,
              display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
              color: on ? T.accent : T.fg3, position: "relative",
            }}>
              <div style={{ position: "relative" }}>
                <Ic name={tb.icon} size={26} sw={on ? 2.3 : 2} />
                {tb.id === "queue" && badge && (
                  <span style={{ position: "absolute", top: -3, right: -7, minWidth: 16, height: 16, padding: "0 4px",
                                 borderRadius: 8, background: T.bad.bar, color: "#fff", fontSize: 10.5, fontWeight: 700,
                                 display: "flex", alignItems: "center", justifyContent: "center" }}>{badge}</span>
                )}
              </div>
              <span style={{ fontSize: 10.5, fontWeight: on ? 700 : 500, letterSpacing: 0.1 }}>{tb.label}</span>
            </button>
          );
        })}
      </div>
    );
  }

  // Section label (grouped-list style)
  function GroupLabel({ children, right }) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "16px 20px 7px", fontFamily: T.sf }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: T.fg2, letterSpacing: 0.2 }}>{children}</span>
        {right}
      </div>
    );
  }

  function Card({ children, style = {} }) {
    return <div style={{ background: T.card, borderRadius: 18, margin: "0 16px", overflow: "hidden",
                         boxShadow: "0 1px 2px rgba(40,30,15,0.05)", ...style }}>{children}</div>;
  }

  Object.assign(window, { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_EntryRow: EntryRow,
    LBM_LargeHeader: LargeHeader, LBM_NavHeader: NavHeader, LBM_ConnChip: ConnChip,
    LBM_TabBar: TabBar, LBM_GroupLabel: GroupLabel, LBM_Card: Card });
})();
