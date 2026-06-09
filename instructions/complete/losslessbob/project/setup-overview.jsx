// Variant C — Sidebar nav with "Overview" as the first page.
// Overview IS the dashboard; other pages are focused settings.
(() => {
  const ov = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#fafaf9", fontFamily: 'ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif',
      fontSize: 14, color: "#1c1917",
    },
    titleBar: {
      background: "#fafaf9", color: "#1c1917", height: 38, display: "flex",
      alignItems: "center", padding: "0 14px", fontSize: 13, fontWeight: 600,
      borderBottom: "1px solid #e7e5e4", gap: 14,
    },
    appMark: {
      width: 18, height: 18, borderRadius: 5, background: "#6b1f7a",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#fff", fontSize: 11, fontWeight: 800,
    },
    menuItem: { color: "#57534e", fontSize: 13, cursor: "pointer", fontWeight: 500 },
    winCtrls: { marginLeft: "auto", display: "flex", gap: 14, color: "#a8a29e", fontSize: 13 },

    topTabs: {
      display: "flex", gap: 2, padding: "0 14px",
      borderBottom: "1px solid #e7e5e4", background: "#fafaf9",
    },
    topTab: {
      padding: "10px 14px", fontSize: 13, cursor: "pointer", color: "#57534e",
      background: "transparent", border: "none", borderBottom: "2px solid transparent",
      marginBottom: -1, fontFamily: "inherit",
    },
    topTabActive: { color: "#6b1f7a", fontWeight: 600, borderBottom: "2px solid #6b1f7a" },

    body: { display: "flex", flex: 1, minHeight: 0 },

    sidebar: {
      width: 240, borderRight: "1px solid #e7e5e4", padding: "20px 12px",
      display: "flex", flexDirection: "column", gap: 1, background: "#fafaf9",
      flexShrink: 0,
    },
    sideHeader: {
      fontSize: 12, fontWeight: 700, color: "#a8a29e", letterSpacing: "0.06em",
      textTransform: "uppercase", padding: "0 10px 8px 10px",
    },
    sideItem: {
      padding: "8px 12px", fontSize: 14, cursor: "pointer", borderRadius: 6,
      color: "#1c1917", display: "flex", alignItems: "center", gap: 10,
      background: "transparent", border: "none", textAlign: "left",
      fontFamily: "inherit",
    },
    sideItemActive: { background: "#f2e8f4", color: "#6b1f7a", fontWeight: 600 },
    sideIcon: { width: 18, color: "currentColor", fontSize: 14 },
    sideBadge: {
      marginLeft: "auto", background: "#fef3c7", color: "#92400e",
      fontSize: 11, fontWeight: 600, padding: "1px 6px", borderRadius: 10,
    },
    sideDanger: { color: "#b91c1c" },

    main: {
      flex: 1, display: "flex", flexDirection: "column", minWidth: 0,
      background: "#fff", overflowY: "auto",
    },
    pageHeader: {
      padding: "24px 36px 16px 36px", borderBottom: "1px solid #f0eeec",
      display: "flex", alignItems: "flex-end", gap: 16,
    },
    pageTitle: { fontSize: 22, fontWeight: 700, margin: 0, color: "#1c1917" },
    pageDesc: { marginTop: 4, fontSize: 13, color: "#78716c" },
    lastSync: { marginLeft: "auto", fontSize: 12, color: "#78716c" },

    content: { padding: "24px 36px 36px 36px" },

    // Overview layout — two columns (60/40) of richer stat cards & feeds
    grid: { display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20 },

    sectionH: {
      fontSize: 11, fontWeight: 700, color: "#78716c", letterSpacing: "0.08em",
      textTransform: "uppercase", margin: "0 0 12px 0",
      display: "flex", alignItems: "center", gap: 8,
    },
    sectionAction: {
      marginLeft: "auto", fontSize: 12, color: "#6b1f7a", cursor: "pointer",
      background: "transparent", border: "none", fontWeight: 500,
    },

    // Big stats row
    bigStats: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 24 },
    bigCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, padding: "16px 18px",
      background: "#fafaf9",
    },
    bigNum: { fontSize: 26, fontWeight: 700, color: "#1c1917", lineHeight: 1.1 },
    bigLabel: { fontSize: 12, color: "#78716c", marginTop: 4 },
    bigSub: { fontSize: 11, color: "#a8a29e", marginTop: 2, fontFamily: 'ui-monospace, monospace' },

    // Integration health list (left col)
    intCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, background: "#fff",
      padding: "6px 0", marginBottom: 24,
    },
    intRow: {
      display: "flex", alignItems: "center", padding: "12px 18px",
      borderTop: "1px solid #f0eeec", gap: 14,
    },
    intRowFirst: { borderTop: "none" },
    intIcon: {
      width: 32, height: 32, borderRadius: 8, background: "#f2e8f4",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#6b1f7a", fontSize: 13, fontWeight: 700, flexShrink: 0,
    },
    intName: { fontSize: 14, fontWeight: 600, color: "#1c1917" },
    intDetail: { fontSize: 12, color: "#78716c", marginTop: 2 },
    intStatus: { marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 },
    statusPill: {
      display: "inline-flex", alignItems: "center", gap: 5,
      fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 10,
    },
    pillOk: { background: "#d1fae5", color: "#047857" },
    pillWarn: { background: "#fef3c7", color: "#92400e" },
    pillOff: { background: "#f5f5f4", color: "#78716c" },
    dot: { width: 5, height: 5, borderRadius: "50%", background: "currentColor" },
    intCog: {
      width: 28, height: 28, borderRadius: 6, border: "1px solid #e7e5e4",
      background: "#fff", color: "#78716c", cursor: "pointer",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
    },

    // Tool checks (right col)
    toolCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, background: "#fff",
      padding: "6px 0", marginBottom: 24,
    },
    toolRow: {
      display: "flex", alignItems: "center", padding: "11px 18px",
      borderTop: "1px solid #f0eeec", gap: 12,
    },
    toolRowFirst: { borderTop: "none" },
    toolName: { fontSize: 14, fontWeight: 600, color: "#1c1917", width: 78 },
    toolVer: { fontSize: 12, color: "#78716c", fontFamily: 'ui-monospace, monospace' },
    toolOk: { marginLeft: "auto", color: "#047857", fontSize: 13, fontWeight: 500 },

    cardFoot: {
      padding: "10px 18px", borderTop: "1px solid #f0eeec",
      display: "flex", alignItems: "center", gap: 8,
    },
    btnGhost: {
      background: "#fff", color: "#1c1917", border: "1px solid #e7e5e4",
      padding: "0 12px", height: 30, fontSize: 13, fontWeight: 500,
      cursor: "pointer", borderRadius: 6,
    },
    btnPrimary: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "0 14px", height: 30, fontSize: 13, fontWeight: 600,
      cursor: "pointer", borderRadius: 6,
    },
    footMeta: { marginLeft: "auto", fontSize: 12, color: "#a8a29e" },

    // Flat-file history feed (right col)
    histCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, background: "#fff",
      padding: "6px 0", marginBottom: 24,
    },
    histRow: {
      display: "flex", flexDirection: "column", padding: "11px 18px",
      borderTop: "1px solid #f0eeec", gap: 3,
    },
    histRowFirst: { borderTop: "none" },
    histTop: { display: "flex", alignItems: "center", gap: 10, fontSize: 13 },
    histStatus: {
      fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    histApplied: { background: "#d1fae5", color: "#047857" },
    histDetected: { background: "#fef3c7", color: "#92400e" },
    histFile: { fontFamily: 'ui-monospace, monospace', fontSize: 13, color: "#1c1917" },
    histMeta: { fontSize: 12, color: "#78716c", marginLeft: 28 },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "8px 18px", fontSize: 12, color: "#78716c",
      borderTop: "1px solid #e7e5e4", background: "#fafaf9", flexShrink: 0,
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];

  const sideNav = [
    { id: "overview",  label: "Overview",            icon: "◉" },
    { id: "database",  label: "Database",            icon: "▤" },
    { id: "integ",     label: "Integrations",        icon: "⇄" },
    { id: "tools",     label: "Tools & Diagnostics", icon: "✓" },
    { id: "display",   label: "Display & Columns",   icon: "▦" },
    { id: "master",    label: "Master Data",         icon: "⇪", badge: "Curator" },
    { id: "advanced",  label: "Advanced",            icon: "⚡", danger: true },
  ];

  function SetupOverviewUI() {
    return (
      <div style={ov.win}>
        <div style={ov.titleBar}>
          <span style={ov.appMark}>L</span>
          <span>LosslessBob</span>
          <span style={{color: "#a8a29e", fontWeight: 400}}>· Checksum Lookup</span>
          <span style={{...ov.menuItem, marginLeft: 18}}>File</span>
          <span style={ov.menuItem}>Database</span>
          <span style={ov.menuItem}>Help</span>
          <div style={ov.winCtrls}><span>—</span><span>▢</span><span>×</span></div>
        </div>

        <div style={ov.topTabs}>
          {topTabs.map(t => (
            <button key={t} style={{...ov.topTab, ...(t === "Setup" ? ov.topTabActive : {})}}>{t}</button>
          ))}
        </div>

        <div style={ov.body}>
          <div style={ov.sidebar}>
            <div style={ov.sideHeader}>Setup</div>
            {sideNav.map(item => (
              <button
                key={item.id}
                style={{
                  ...ov.sideItem,
                  ...(item.id === "overview" ? ov.sideItemActive : {}),
                  ...(item.danger ? ov.sideDanger : {}),
                }}
              >
                <span style={ov.sideIcon}>{item.icon}</span>
                <span>{item.label}</span>
                {item.badge && <span style={ov.sideBadge}>{item.badge}</span>}
              </button>
            ))}
          </div>

          <div style={ov.main}>
            <div style={ov.pageHeader}>
              <div>
                <h1 style={ov.pageTitle}>Overview</h1>
                <div style={ov.pageDesc}>Database health, integration status, and recent activity at a glance.</div>
              </div>
              <span style={ov.lastSync}>Last refresh · 2s ago</span>
            </div>

            <div style={ov.content}>

              {/* Big stats row */}
              <div style={ov.bigStats}>
                <div style={ov.bigCard}>
                  <div style={ov.bigNum}>1.25M</div>
                  <div style={ov.bigLabel}>Checksums</div>
                  <div style={ov.bigSub}>+312 in last release</div>
                </div>
                <div style={ov.bigCard}>
                  <div style={ov.bigNum}>24,118</div>
                  <div style={ov.bigLabel}>LB entries</div>
                  <div style={ov.bigSub}>latest: LB-24118</div>
                </div>
                <div style={ov.bigCard}>
                  <div style={ov.bigNum}>3d ago</div>
                  <div style={ov.bigLabel}>Last import</div>
                  <div style={ov.bigSub}>2026-05-22 14:03</div>
                </div>
                <div style={ov.bigCard}>
                  <div style={ov.bigNum}>0</div>
                  <div style={ov.bigLabel}>Folders in collection</div>
                  <div style={ov.bigSub}>scan a directory to start</div>
                </div>
              </div>

              <div style={ov.grid}>
                {/* LEFT — Integrations */}
                <div>
                  <div style={ov.sectionH}>
                    Integrations
                    <button style={ov.sectionAction}>Manage →</button>
                  </div>
                  <div style={ov.intCard}>
                    <div style={{...ov.intRow, ...ov.intRowFirst}}>
                      <span style={ov.intIcon}>qB</span>
                      <div>
                        <div style={ov.intName}>qBittorrent</div>
                        <div style={ov.intDetail}>localhost:8080 · v5.0.3 · tested 2 min ago</div>
                      </div>
                      <div style={ov.intStatus}>
                        <span style={{...ov.statusPill, ...ov.pillOk}}><span style={ov.dot}></span> Connected</span>
                        <button style={ov.intCog}>⚙</button>
                      </div>
                    </div>
                    <div style={ov.intRow}>
                      <span style={ov.intIcon}>W</span>
                      <div>
                        <div style={ov.intName}>WTRF Forum</div>
                        <div style={ov.intDetail}>No credentials saved</div>
                      </div>
                      <div style={ov.intStatus}>
                        <span style={{...ov.statusPill, ...ov.pillWarn}}><span style={ov.dot}></span> Not configured</span>
                        <button style={ov.intCog}>⚙</button>
                      </div>
                    </div>
                    <div style={ov.intRow}>
                      <span style={ov.intIcon}>🌐</span>
                      <div>
                        <div style={ov.intName}>Web GUI</div>
                        <div style={ov.intDetail}>Auth disabled — accessible without password</div>
                      </div>
                      <div style={ov.intStatus}>
                        <span style={{...ov.statusPill, ...ov.pillOff}}><span style={ov.dot}></span> Open</span>
                        <button style={ov.intCog}>⚙</button>
                      </div>
                    </div>
                    <div style={ov.intRow}>
                      <span style={ov.intIcon}>⛓</span>
                      <div>
                        <div style={ov.intName}>Tracker list</div>
                        <div style={ov.intDetail}>"best" · 87 trackers · refreshed 4d ago</div>
                      </div>
                      <div style={ov.intStatus}>
                        <span style={{...ov.statusPill, ...ov.pillOk}}><span style={ov.dot}></span> Loaded</span>
                        <button style={ov.intCog}>⚙</button>
                      </div>
                    </div>
                  </div>

                  {/* Flat file history */}
                  <div style={ov.sectionH}>
                    Recent flat-file releases
                    <button style={ov.sectionAction}>View all →</button>
                  </div>
                  <div style={ov.histCard}>
                    <div style={{...ov.histRow, ...ov.histRowFirst}}>
                      <div style={ov.histTop}>
                        <span style={{...ov.histStatus, ...ov.histApplied}}>Applied</span>
                        <span style={ov.histFile}>lb_20260522.zip</span>
                      </div>
                      <div style={ov.histMeta}>2026-05-22 · +312 added · ~48 changed · −0 removed</div>
                    </div>
                    <div style={ov.histRow}>
                      <div style={ov.histTop}>
                        <span style={{...ov.histStatus, ...ov.histApplied}}>Applied</span>
                        <span style={ov.histFile}>lb_20260508.zip</span>
                      </div>
                      <div style={ov.histMeta}>2026-05-08 · +280 added · ~22 changed · −2 removed</div>
                    </div>
                    <div style={ov.histRow}>
                      <div style={ov.histTop}>
                        <span style={{...ov.histStatus, ...ov.histDetected}}>Detected</span>
                        <span style={ov.histFile}>lb_20260427.zip</span>
                      </div>
                      <div style={ov.histMeta}>2026-04-27 · deferred (1 day)</div>
                    </div>
                    <div style={ov.cardFoot}>
                      <button style={ov.btnPrimary}>Check for new release</button>
                      <span style={ov.footMeta}>Auto-check daily at 03:00</span>
                    </div>
                  </div>
                </div>

                {/* RIGHT — Tools, DB, Master */}
                <div>
                  <div style={ov.sectionH}>External tools</div>
                  <div style={ov.toolCard}>
                    <div style={{...ov.toolRow, ...ov.toolRowFirst}}>
                      <span style={ov.toolName}>SoX</span>
                      <span style={ov.toolVer}>v14.4.2</span>
                      <span style={ov.toolOk}>✓ Found</span>
                    </div>
                    <div style={ov.toolRow}>
                      <span style={ov.toolName}>ffmpeg</span>
                      <span style={ov.toolVer}>v6.1.1</span>
                      <span style={ov.toolOk}>✓ Found</span>
                    </div>
                    <div style={ov.toolRow}>
                      <span style={ov.toolName}>shntool</span>
                      <span style={ov.toolVer}>v3.0.10</span>
                      <span style={ov.toolOk}>✓ Found</span>
                    </div>
                    <div style={ov.cardFoot}>
                      <button style={ov.btnGhost}>Re-check</button>
                      <span style={ov.footMeta}>All required tools present</span>
                    </div>
                  </div>

                  <div style={ov.sectionH}>Database</div>
                  <div style={ov.toolCard}>
                    <div style={{...ov.toolRow, ...ov.toolRowFirst, gap: 14}}>
                      <span style={{...ov.toolName, width: "auto"}}>Active</span>
                      <span style={{...ov.intName, fontSize: 13}}>LosslessBob</span>
                      <span style={ov.toolOk}>·</span>
                    </div>
                    <div style={{...ov.toolRow, gap: 14}}>
                      <span style={{...ov.toolName, width: "auto"}}>Size</span>
                      <span style={ov.toolVer}>847 MB</span>
                    </div>
                    <div style={{...ov.toolRow, gap: 14}}>
                      <span style={{...ov.toolName, width: "auto"}}>Storage</span>
                      <span style={ov.toolVer}>~/.losslessbob/data</span>
                    </div>
                    <div style={ov.cardFoot}>
                      <button style={ov.btnGhost}>Import flat file…</button>
                      <button style={ov.btnGhost}>Open data folder</button>
                    </div>
                  </div>

                  <div style={ov.sectionH}>Master Data</div>
                  <div style={ov.toolCard}>
                    <div style={{...ov.toolRow, ...ov.toolRowFirst, gap: 14}}>
                      <span style={{...ov.toolName, width: "auto"}}>Mode</span>
                      <span style={ov.toolVer}>Consumer</span>
                      <span style={{...ov.statusPill, ...ov.pillOff, marginLeft: "auto"}}>
                        <span style={ov.dot}></span> Curator off
                      </span>
                    </div>
                    <div style={{...ov.toolRow, gap: 14}}>
                      <span style={{...ov.toolName, width: "auto"}}>Version</span>
                      <span style={ov.toolVer}>(none installed)</span>
                    </div>
                    <div style={ov.cardFoot}>
                      <button style={ov.btnGhost}>Install master update…</button>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

        <div style={ov.statusBar}>
          <span>DB: <strong style={{color: "#1c1917", fontWeight: 600}}>LB-24118</strong></span>
          <span>·</span>
          <span>Checksums: <strong style={{color: "#1c1917", fontWeight: 600}}>1,247,392</strong></span>
          <span>·</span>
          <span>Last import: 2026-05-22 14:03</span>
        </div>
      </div>
    );
  }

  window.SetupOverviewUI = SetupOverviewUI;
})();
