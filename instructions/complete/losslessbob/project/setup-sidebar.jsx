// Variant A — Sidebar navigation. Setup is split into focused sub-pages.
// Currently showing "Integrations" pane since that's the densest part of the original.
(() => {
  const c = {
    // App chrome
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

    // Top tabs (existing pattern from your refined variants)
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

    // Settings layout: sidebar + content
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
    sideItemActive: {
      background: "#f2e8f4", color: "#6b1f7a", fontWeight: 600,
    },
    sideIcon: { width: 18, height: 18, flexShrink: 0, color: "currentColor" },
    sideBadge: {
      marginLeft: "auto", background: "#fef3c7", color: "#92400e",
      fontSize: 11, fontWeight: 600, padding: "1px 6px", borderRadius: 10,
    },
    sideDanger: { color: "#b91c1c" },

    // Main content
    main: {
      flex: 1, display: "flex", flexDirection: "column", minWidth: 0,
      background: "#fff", overflowY: "auto",
    },
    pageHeader: {
      padding: "28px 36px 18px 36px", borderBottom: "1px solid #f0eeec",
    },
    pageTitle: { fontSize: 24, fontWeight: 700, margin: 0, color: "#1c1917" },
    pageDesc: {
      marginTop: 6, fontSize: 14, color: "#78716c", maxWidth: 720,
    },

    content: { padding: "24px 36px 36px 36px", display: "flex", flexDirection: "column", gap: 20 },

    // Integration card (one per service)
    integCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, background: "#fff",
      overflow: "hidden",
    },
    integHead: {
      padding: "14px 18px", display: "flex", alignItems: "center", gap: 12,
      borderBottom: "1px solid #f0eeec",
    },
    integIcon: {
      width: 36, height: 36, borderRadius: 8, background: "#f2e8f4",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#6b1f7a", fontSize: 16, fontWeight: 700, flexShrink: 0,
    },
    integTitleWrap: { display: "flex", flexDirection: "column", gap: 2, minWidth: 0 },
    integTitle: { fontSize: 15, fontWeight: 600, color: "#1c1917" },
    integSub: { fontSize: 13, color: "#78716c" },
    integStatusOk: {
      marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, fontWeight: 500, color: "#047857",
      background: "#d1fae5", padding: "4px 10px", borderRadius: 12,
    },
    integStatusWarn: {
      marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, fontWeight: 500, color: "#92400e",
      background: "#fef3c7", padding: "4px 10px", borderRadius: 12,
    },
    integStatusOff: {
      marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, fontWeight: 500, color: "#78716c",
      background: "#f5f5f4", padding: "4px 10px", borderRadius: 12,
    },
    dot: { width: 6, height: 6, borderRadius: "50%", background: "currentColor" },

    integBody: { padding: "16px 18px 18px 18px" },
    formGrid: {
      display: "grid", gridTemplateColumns: "140px 1fr 140px 1fr",
      columnGap: 14, rowGap: 12, alignItems: "center",
    },
    formGridWide: {
      display: "grid", gridTemplateColumns: "140px 1fr",
      columnGap: 14, rowGap: 12, alignItems: "center",
    },
    fieldLabel: { fontSize: 13, color: "#57534e", fontWeight: 500 },
    fieldHint: { fontSize: 12, color: "#a8a29e", marginTop: 2 },
    input: {
      height: 34, padding: "0 10px", border: "1px solid #e7e5e4",
      background: "#fff", fontSize: 14, borderRadius: 6, color: "#1c1917",
      fontFamily: "inherit", outline: "none", width: "100%", boxSizing: "border-box",
    },
    actions: {
      marginTop: 16, paddingTop: 14, borderTop: "1px solid #f0eeec",
      display: "flex", gap: 8, alignItems: "center",
    },
    btnPrimary: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "0 14px", height: 32, fontSize: 13, fontWeight: 600,
      cursor: "pointer", borderRadius: 6,
    },
    btnGhost: {
      background: "#fff", color: "#1c1917", border: "1px solid #e7e5e4",
      padding: "0 12px", height: 32, fontSize: 13, fontWeight: 500,
      cursor: "pointer", borderRadius: 6,
    },
    btnDanger: {
      background: "#fff", color: "#b91c1c", border: "1px solid #fecaca",
      padding: "0 12px", height: 32, fontSize: 13, fontWeight: 500,
      cursor: "pointer", borderRadius: 6,
    },
    lastChecked: { marginLeft: "auto", fontSize: 12, color: "#a8a29e" },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "8px 18px", fontSize: 12, color: "#78716c",
      borderTop: "1px solid #e7e5e4", background: "#fafaf9", flexShrink: 0,
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];

  const sideNav = [
    { id: "general", label: "General", icon: "⚙" },
    { id: "database", label: "Database", icon: "▤" },
    { id: "master", label: "Master Data", icon: "⇪", badge: "Curator" },
    { id: "integ", label: "Integrations", icon: "⇄" },
    { id: "tools", label: "Tools & Diagnostics", icon: "✓" },
    { id: "display", label: "Display & Columns", icon: "▦" },
    { id: "advanced", label: "Advanced", icon: "⚡", danger: true },
  ];

  function SidebarUI() {
    return (
      <div style={c.win}>
        <div style={c.titleBar}>
          <span style={c.appMark}>L</span>
          <span>LosslessBob</span>
          <span style={{color: "#a8a29e", fontWeight: 400}}>· Checksum Lookup</span>
          <span style={{...c.menuItem, marginLeft: 18}}>File</span>
          <span style={c.menuItem}>Database</span>
          <span style={c.menuItem}>Help</span>
          <div style={c.winCtrls}><span>—</span><span>▢</span><span>×</span></div>
        </div>

        <div style={c.topTabs}>
          {topTabs.map(t => (
            <button key={t} style={{...c.topTab, ...(t === "Setup" ? c.topTabActive : {})}}>{t}</button>
          ))}
        </div>

        <div style={c.body}>
          {/* Sidebar */}
          <div style={c.sidebar}>
            <div style={c.sideHeader}>Setup</div>
            {sideNav.map(item => (
              <button
                key={item.id}
                style={{
                  ...c.sideItem,
                  ...(item.id === "integ" ? c.sideItemActive : {}),
                  ...(item.danger ? c.sideDanger : {}),
                }}
              >
                <span style={c.sideIcon}>{item.icon}</span>
                <span>{item.label}</span>
                {item.badge && <span style={c.sideBadge}>{item.badge}</span>}
              </button>
            ))}
          </div>

          {/* Main pane: Integrations */}
          <div style={c.main}>
            <div style={c.pageHeader}>
              <h1 style={c.pageTitle}>Integrations</h1>
              <p style={c.pageDesc}>
                Connect LosslessBob to qBittorrent for torrent management, the Watching the River Flow forum
                for posting, and configure the optional web GUI password.
              </p>
            </div>

            <div style={c.content}>

              {/* qBittorrent */}
              <div style={c.integCard}>
                <div style={c.integHead}>
                  <span style={c.integIcon}>qB</span>
                  <div style={c.integTitleWrap}>
                    <span style={c.integTitle}>qBittorrent</span>
                    <span style={c.integSub}>Torrent client for downloading & seeding</span>
                  </div>
                  <span style={c.integStatusOk}>
                    <span style={c.dot}></span> Connected
                  </span>
                </div>
                <div style={c.integBody}>
                  <div style={c.formGrid}>
                    <span style={c.fieldLabel}>Host</span>
                    <input style={c.input} defaultValue="localhost" />
                    <span style={c.fieldLabel}>Port</span>
                    <input style={c.input} defaultValue="8080" />

                    <span style={c.fieldLabel}>Username</span>
                    <input style={c.input} defaultValue="admin" />
                    <span style={c.fieldLabel}>Password</span>
                    <input type="password" style={c.input} defaultValue="••••••••" />

                    <span style={c.fieldLabel}>API Key</span>
                    <div style={{gridColumn: "2 / span 3"}}>
                      <input type="password" style={c.input} placeholder="qBittorrent 5+ — takes priority over username/password" />
                      <div style={c.fieldHint}>Leave blank to use username/password authentication.</div>
                    </div>

                    <span style={c.fieldLabel}>Category</span>
                    <input style={c.input} defaultValue="losslessbob" />
                    <span style={c.fieldLabel}>Tags</span>
                    <input style={c.input} placeholder="comma-separated (optional)" />
                  </div>
                  <div style={c.actions}>
                    <button style={c.btnPrimary}>Save</button>
                    <button style={c.btnGhost}>Test connection</button>
                    <button style={c.btnGhost}>Clear credentials</button>
                    <span style={c.lastChecked}>Last tested 2 min ago · v5.0.3</span>
                  </div>
                </div>
              </div>

              {/* Watching the River Flow Forum */}
              <div style={c.integCard}>
                <div style={c.integHead}>
                  <span style={c.integIcon}>W</span>
                  <div style={c.integTitleWrap}>
                    <span style={c.integTitle}>Watching the River Flow Forum</span>
                    <span style={c.integSub}>SMF forum for posting & scraping bootleg announcements</span>
                  </div>
                  <span style={c.integStatusWarn}>
                    <span style={c.dot}></span> Not tested
                  </span>
                </div>
                <div style={c.integBody}>
                  <div style={c.formGrid}>
                    <span style={c.fieldLabel}>Username</span>
                    <input style={c.input} />
                    <span style={c.fieldLabel}>Password</span>
                    <input type="password" style={c.input} />

                    <span style={c.fieldLabel}>Board ID</span>
                    <div style={{gridColumn: "2 / span 1"}}>
                      <input style={{...c.input, width: 100}} defaultValue="42" />
                      <div style={c.fieldHint}>From the forum URL: <code>?board=42.0</code> → 42</div>
                    </div>
                  </div>
                  <div style={c.actions}>
                    <button style={c.btnPrimary}>Save</button>
                    <button style={c.btnGhost}>Test connection</button>
                    <button style={c.btnGhost}>Clear credentials</button>
                  </div>
                </div>
              </div>

              {/* Web GUI Access */}
              <div style={c.integCard}>
                <div style={c.integHead}>
                  <span style={c.integIcon}>🌐</span>
                  <div style={c.integTitleWrap}>
                    <span style={c.integTitle}>Web GUI Access</span>
                    <span style={c.integSub}>Optional password for the web interface</span>
                  </div>
                  <span style={c.integStatusOff}>
                    <span style={c.dot}></span> No password set
                  </span>
                </div>
                <div style={c.integBody}>
                  <div style={c.formGridWide}>
                    <span style={c.fieldLabel}>Password</span>
                    <div>
                      <input type="password" style={{...c.input, maxWidth: 320}} placeholder="Leave empty to disable auth" />
                      <div style={c.fieldHint}>When set, the web GUI prompts for this password before allowing access.</div>
                    </div>
                  </div>
                  <div style={c.actions}>
                    <button style={c.btnPrimary}>Save</button>
                    <button style={c.btnGhost}>Clear</button>
                  </div>
                </div>
              </div>

              {/* Torrent Settings — kept here since it pairs with qBt usage */}
              <div style={c.integCard}>
                <div style={c.integHead}>
                  <span style={c.integIcon}>⛓</span>
                  <div style={c.integTitleWrap}>
                    <span style={c.integTitle}>Torrent Tracker List</span>
                    <span style={c.integSub}>Trackers added when creating new torrents</span>
                  </div>
                  <span style={c.integStatusOk}>
                    <span style={c.dot}></span> 87 trackers loaded
                  </span>
                </div>
                <div style={c.integBody}>
                  <div style={c.formGridWide}>
                    <span style={c.fieldLabel}>Tracker list</span>
                    <select style={{...c.input, maxWidth: 240}}>
                      <option>best</option><option>all_ws</option><option>all_https</option>
                      <option>all_http</option><option>all_udp</option>
                    </select>
                  </div>
                  <div style={c.actions}>
                    <button style={c.btnGhost}>Refresh trackers</button>
                    <span style={c.lastChecked}>Last refreshed 4 days ago</span>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

        <div style={c.statusBar}>
          <span>DB: <strong style={{color: "#1c1917", fontWeight: 600}}>LB-24118</strong></span>
          <span>·</span>
          <span>Checksums: <strong style={{color: "#1c1917", fontWeight: 600}}>1,247,392</strong></span>
          <span>·</span>
          <span>Last import: 2026-05-22 14:03</span>
        </div>
      </div>
    );
  }

  window.SetupSidebarUI = SidebarUI;
})();
