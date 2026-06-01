// Variant D — Sidebar nav + persistent contextual right column.
// Right column adapts to current settings page. Shows Integrations + integration health.
(() => {
  const hy = {
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

    // 3-column body
    body: { display: "grid", gridTemplateColumns: "220px 1fr 360px", flex: 1, minHeight: 0 },

    // Sidebar
    sidebar: {
      borderRight: "1px solid #e7e5e4", padding: "20px 12px",
      display: "flex", flexDirection: "column", gap: 1, background: "#fafaf9",
      overflowY: "auto",
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

    // Center pane (config)
    main: {
      display: "flex", flexDirection: "column", minWidth: 0,
      background: "#fff", overflowY: "auto",
    },
    pageHeader: {
      padding: "24px 32px 16px 32px", borderBottom: "1px solid #f0eeec",
    },
    pageTitle: { fontSize: 22, fontWeight: 700, margin: 0, color: "#1c1917" },
    pageDesc: { marginTop: 4, fontSize: 13, color: "#78716c", maxWidth: 680 },

    content: { padding: "20px 32px 32px 32px", display: "flex", flexDirection: "column", gap: 16 },

    integCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, background: "#fff",
      overflow: "hidden",
    },
    integHead: {
      padding: "14px 18px", display: "flex", alignItems: "center", gap: 12,
      borderBottom: "1px solid #f0eeec",
    },
    integIcon: {
      width: 34, height: 34, borderRadius: 8, background: "#f2e8f4",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#6b1f7a", fontSize: 14, fontWeight: 700, flexShrink: 0,
    },
    integTitle: { fontSize: 15, fontWeight: 600, color: "#1c1917" },
    integSub: { fontSize: 12, color: "#78716c", marginTop: 1 },
    integBody: { padding: "14px 18px 16px 18px" },
    formGrid: {
      display: "grid", gridTemplateColumns: "120px 1fr 120px 1fr",
      columnGap: 12, rowGap: 10, alignItems: "center",
    },
    formGridWide: {
      display: "grid", gridTemplateColumns: "120px 1fr",
      columnGap: 12, rowGap: 10, alignItems: "center",
    },
    fieldLabel: { fontSize: 13, color: "#57534e", fontWeight: 500 },
    fieldHint: { fontSize: 12, color: "#a8a29e", marginTop: 2 },
    input: {
      height: 32, padding: "0 10px", border: "1px solid #e7e5e4",
      background: "#fff", fontSize: 13, borderRadius: 6, color: "#1c1917",
      fontFamily: "inherit", outline: "none", width: "100%", boxSizing: "border-box",
    },
    actions: {
      marginTop: 14, paddingTop: 12, borderTop: "1px solid #f0eeec",
      display: "flex", gap: 8, alignItems: "center",
    },
    btnPrimary: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "0 14px", height: 30, fontSize: 13, fontWeight: 600,
      cursor: "pointer", borderRadius: 6,
    },
    btnGhost: {
      background: "#fff", color: "#1c1917", border: "1px solid #e7e5e4",
      padding: "0 12px", height: 30, fontSize: 13, fontWeight: 500,
      cursor: "pointer", borderRadius: 6,
    },
    lastTest: { marginLeft: "auto", fontSize: 12, color: "#a8a29e" },

    statusPill: {
      marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5,
      fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 10,
    },
    pillOk: { background: "#d1fae5", color: "#047857" },
    pillWarn: { background: "#fef3c7", color: "#92400e" },
    pillOff: { background: "#f5f5f4", color: "#78716c" },
    dot: { width: 5, height: 5, borderRadius: "50%", background: "currentColor" },

    // RIGHT column — contextual
    right: {
      background: "#fafaf9", borderLeft: "1px solid #e7e5e4",
      padding: "20px 20px 24px 20px", display: "flex", flexDirection: "column", gap: 18,
      overflowY: "auto",
    },
    rightLabel: {
      fontSize: 10, fontWeight: 700, color: "#a8a29e", letterSpacing: "0.1em",
      textTransform: "uppercase",
    },
    rightTitle: {
      fontSize: 14, fontWeight: 700, color: "#1c1917", margin: "2px 0 0 0",
    },
    rightSection: {
      display: "flex", flexDirection: "column", gap: 8,
    },
    rightCard: {
      background: "#fff", border: "1px solid #e7e5e4", borderRadius: 8,
      padding: "12px 14px",
    },
    rcRow: {
      display: "flex", alignItems: "center", gap: 10, padding: "8px 0",
      borderTop: "1px solid #f0eeec",
    },
    rcRowFirst: { borderTop: "none", paddingTop: 0 },
    rcIcon: {
      width: 26, height: 26, borderRadius: 6, background: "#f2e8f4",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#6b1f7a", fontSize: 11, fontWeight: 700, flexShrink: 0,
    },
    rcName: { fontSize: 13, fontWeight: 600, color: "#1c1917" },
    rcMeta: { fontSize: 11, color: "#78716c", marginTop: 1 },
    rcStatus: { marginLeft: "auto" },

    miniPill: {
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 8,
    },

    tipBox: {
      background: "#fff", border: "1px solid #e7e5e4", borderRadius: 8,
      padding: "12px 14px", fontSize: 12, color: "#57534e", lineHeight: 1.5,
    },
    tipTitle: { fontSize: 12, fontWeight: 700, color: "#1c1917", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "8px 18px", fontSize: 12, color: "#78716c",
      borderTop: "1px solid #e7e5e4", background: "#fafaf9", flexShrink: 0,
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];

  const sideNav = [
    { id: "general",  label: "General",             icon: "⚙" },
    { id: "database", label: "Database",            icon: "▤" },
    { id: "integ",    label: "Integrations",        icon: "⇄" },
    { id: "tools",    label: "Tools & Diagnostics", icon: "✓" },
    { id: "display",  label: "Display & Columns",   icon: "▦" },
    { id: "master",   label: "Master Data",         icon: "⇪", badge: "Curator" },
    { id: "advanced", label: "Advanced",            icon: "⚡", danger: true },
  ];

  function SetupHybridUI() {
    return (
      <div style={hy.win}>
        <div style={hy.titleBar}>
          <span style={hy.appMark}>L</span>
          <span>LosslessBob</span>
          <span style={{color: "#a8a29e", fontWeight: 400}}>· Checksum Lookup</span>
          <span style={{...hy.menuItem, marginLeft: 18}}>File</span>
          <span style={hy.menuItem}>Database</span>
          <span style={hy.menuItem}>Help</span>
          <div style={hy.winCtrls}><span>—</span><span>▢</span><span>×</span></div>
        </div>

        <div style={hy.topTabs}>
          {topTabs.map(t => (
            <button key={t} style={{...hy.topTab, ...(t === "Setup" ? hy.topTabActive : {})}}>{t}</button>
          ))}
        </div>

        <div style={hy.body}>
          {/* LEFT — sidebar */}
          <div style={hy.sidebar}>
            <div style={hy.sideHeader}>Setup</div>
            {sideNav.map(item => (
              <button
                key={item.id}
                style={{
                  ...hy.sideItem,
                  ...(item.id === "integ" ? hy.sideItemActive : {}),
                  ...(item.danger ? hy.sideDanger : {}),
                }}
              >
                <span style={hy.sideIcon}>{item.icon}</span>
                <span>{item.label}</span>
                {item.badge && <span style={hy.sideBadge}>{item.badge}</span>}
              </button>
            ))}
          </div>

          {/* CENTER — Integrations page */}
          <div style={hy.main}>
            <div style={hy.pageHeader}>
              <h1 style={hy.pageTitle}>Integrations</h1>
              <p style={hy.pageDesc}>
                Connect LosslessBob to qBittorrent, the WTRF forum, and configure web GUI access.
                Connection health stays visible on the right.
              </p>
            </div>

            <div style={hy.content}>

              {/* qBittorrent */}
              <div style={hy.integCard}>
                <div style={hy.integHead}>
                  <span style={hy.integIcon}>qB</span>
                  <div>
                    <div style={hy.integTitle}>qBittorrent</div>
                    <div style={hy.integSub}>Torrent client for downloading & seeding</div>
                  </div>
                  <span style={{...hy.statusPill, ...hy.pillOk}}><span style={hy.dot}></span> Connected</span>
                </div>
                <div style={hy.integBody}>
                  <div style={hy.formGrid}>
                    <span style={hy.fieldLabel}>Host</span><input style={hy.input} defaultValue="localhost" />
                    <span style={hy.fieldLabel}>Port</span><input style={hy.input} defaultValue="8080" />
                    <span style={hy.fieldLabel}>Username</span><input style={hy.input} defaultValue="admin" />
                    <span style={hy.fieldLabel}>Password</span><input type="password" style={hy.input} defaultValue="••••••••" />
                    <span style={hy.fieldLabel}>API Key</span>
                    <div style={{gridColumn: "2 / span 3"}}>
                      <input type="password" style={hy.input} placeholder="qBittorrent 5+ — overrides username/password" />
                    </div>
                    <span style={hy.fieldLabel}>Category</span><input style={hy.input} defaultValue="losslessbob" />
                    <span style={hy.fieldLabel}>Tags</span><input style={hy.input} placeholder="comma-separated (optional)" />
                  </div>
                  <div style={hy.actions}>
                    <button style={hy.btnPrimary}>Save</button>
                    <button style={hy.btnGhost}>Test connection</button>
                    <button style={hy.btnGhost}>Clear</button>
                    <span style={hy.lastTest}>Last tested 2 min ago</span>
                  </div>
                </div>
              </div>

              {/* WTRF Forum */}
              <div style={hy.integCard}>
                <div style={hy.integHead}>
                  <span style={hy.integIcon}>W</span>
                  <div>
                    <div style={hy.integTitle}>Watching the River Flow Forum</div>
                    <div style={hy.integSub}>SMF forum for posting & scraping bootleg announcements</div>
                  </div>
                  <span style={{...hy.statusPill, ...hy.pillWarn}}><span style={hy.dot}></span> Not tested</span>
                </div>
                <div style={hy.integBody}>
                  <div style={hy.formGrid}>
                    <span style={hy.fieldLabel}>Username</span><input style={hy.input} />
                    <span style={hy.fieldLabel}>Password</span><input type="password" style={hy.input} />
                    <span style={hy.fieldLabel}>Board ID</span>
                    <div><input style={{...hy.input, width: 100}} defaultValue="42" /></div>
                    <span></span><span></span>
                  </div>
                  <div style={hy.actions}>
                    <button style={hy.btnPrimary}>Save</button>
                    <button style={hy.btnGhost}>Test connection</button>
                    <button style={hy.btnGhost}>Clear</button>
                  </div>
                </div>
              </div>

              {/* Web GUI */}
              <div style={hy.integCard}>
                <div style={hy.integHead}>
                  <span style={hy.integIcon}>🌐</span>
                  <div>
                    <div style={hy.integTitle}>Web GUI Access</div>
                    <div style={hy.integSub}>Optional password for the web interface</div>
                  </div>
                  <span style={{...hy.statusPill, ...hy.pillOff}}><span style={hy.dot}></span> No password</span>
                </div>
                <div style={hy.integBody}>
                  <div style={hy.formGridWide}>
                    <span style={hy.fieldLabel}>Password</span>
                    <input type="password" style={{...hy.input, maxWidth: 300}} placeholder="Leave empty to disable auth" />
                  </div>
                  <div style={hy.actions}>
                    <button style={hy.btnPrimary}>Save</button>
                    <button style={hy.btnGhost}>Clear</button>
                  </div>
                </div>
              </div>

              {/* Tracker list */}
              <div style={hy.integCard}>
                <div style={hy.integHead}>
                  <span style={hy.integIcon}>⛓</span>
                  <div>
                    <div style={hy.integTitle}>Torrent Tracker List</div>
                    <div style={hy.integSub}>Trackers added when creating new torrents</div>
                  </div>
                  <span style={{...hy.statusPill, ...hy.pillOk}}><span style={hy.dot}></span> 87 loaded</span>
                </div>
                <div style={hy.integBody}>
                  <div style={hy.formGridWide}>
                    <span style={hy.fieldLabel}>Tracker list</span>
                    <select style={{...hy.input, maxWidth: 240}}>
                      <option>best</option><option>all_ws</option><option>all_https</option>
                    </select>
                  </div>
                  <div style={hy.actions}>
                    <button style={hy.btnGhost}>Refresh trackers</button>
                    <span style={hy.lastTest}>Refreshed 4 days ago</span>
                  </div>
                </div>
              </div>

            </div>
          </div>

          {/* RIGHT — contextual to "Integrations" page */}
          <div style={hy.right}>
            <div>
              <div style={hy.rightLabel}>Context</div>
              <h3 style={hy.rightTitle}>Integration health</h3>
            </div>

            <div style={hy.rightCard}>
              <div style={{...hy.rcRow, ...hy.rcRowFirst}}>
                <span style={hy.rcIcon}>qB</span>
                <div>
                  <div style={hy.rcName}>qBittorrent</div>
                  <div style={hy.rcMeta}>localhost:8080 · v5.0.3</div>
                </div>
                <span style={hy.rcStatus}>
                  <span style={{...hy.miniPill, ...hy.pillOk}}><span style={hy.dot}></span> OK</span>
                </span>
              </div>
              <div style={hy.rcRow}>
                <span style={hy.rcIcon}>W</span>
                <div>
                  <div style={hy.rcName}>WTRF Forum</div>
                  <div style={hy.rcMeta}>Not configured</div>
                </div>
                <span style={hy.rcStatus}>
                  <span style={{...hy.miniPill, ...hy.pillWarn}}><span style={hy.dot}></span> —</span>
                </span>
              </div>
              <div style={hy.rcRow}>
                <span style={hy.rcIcon}>🌐</span>
                <div>
                  <div style={hy.rcName}>Web GUI</div>
                  <div style={hy.rcMeta}>Open (no password)</div>
                </div>
                <span style={hy.rcStatus}>
                  <span style={{...hy.miniPill, ...hy.pillOff}}><span style={hy.dot}></span> Open</span>
                </span>
              </div>
              <div style={hy.rcRow}>
                <span style={hy.rcIcon}>⛓</span>
                <div>
                  <div style={hy.rcName}>Trackers</div>
                  <div style={hy.rcMeta}>87 loaded · 4d ago</div>
                </div>
                <span style={hy.rcStatus}>
                  <span style={{...hy.miniPill, ...hy.pillOk}}><span style={hy.dot}></span> OK</span>
                </span>
              </div>
            </div>

            <div>
              <div style={hy.rightLabel}>Recent activity</div>
            </div>
            <div style={hy.rightCard}>
              <div style={{...hy.rcRow, ...hy.rcRowFirst, flexDirection: "column", alignItems: "flex-start", gap: 2}}>
                <div style={{...hy.rcName, fontSize: 12}}>qBt login succeeded</div>
                <div style={hy.rcMeta}>2 min ago · admin@localhost:8080</div>
              </div>
              <div style={{...hy.rcRow, flexDirection: "column", alignItems: "flex-start", gap: 2}}>
                <div style={{...hy.rcName, fontSize: 12}}>Tracker list refreshed</div>
                <div style={hy.rcMeta}>4 days ago · 87 trackers · "best"</div>
              </div>
              <div style={{...hy.rcRow, flexDirection: "column", alignItems: "flex-start", gap: 2}}>
                <div style={{...hy.rcName, fontSize: 12}}>3 torrents added to qBt</div>
                <div style={hy.rcMeta}>2026-05-22 · category: losslessbob</div>
              </div>
            </div>

            <div style={hy.tipBox}>
              <div style={hy.tipTitle}>Tip</div>
              On qBittorrent 5+ an API key takes priority over username/password — safer for sharing config files. Generate one in qBt → Tools → Options → Web UI.
            </div>
          </div>

        </div>

        <div style={hy.statusBar}>
          <span>DB: <strong style={{color: "#1c1917", fontWeight: 600}}>LB-24118</strong></span>
          <span>·</span>
          <span>Checksums: <strong style={{color: "#1c1917", fontWeight: 600}}>1,247,392</strong></span>
          <span>·</span>
          <span>Last import: 2026-05-22 14:03</span>
        </div>
      </div>
    );
  }

  window.SetupHybridUI = SetupHybridUI;
})();
