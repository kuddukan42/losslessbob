// Variant B — Two-column dashboard. Left = configuration, right = live state.
// Single scrolling page; no nav drill-down.
(() => {
  const c = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#f5f5f4", fontFamily: 'ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif',
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

    // Two-column body
    body: { display: "grid", gridTemplateColumns: "1fr 380px", flex: 1, minHeight: 0 },

    // LEFT: config column (scrollable)
    configCol: { padding: "24px 28px 28px 36px", overflowY: "auto", minWidth: 0 },
    pageTitle: { fontSize: 22, fontWeight: 700, margin: "0 0 4px 0", color: "#1c1917" },
    pageSub: { fontSize: 13, color: "#78716c", marginBottom: 22 },

    sectionLabel: {
      fontSize: 11, fontWeight: 700, color: "#78716c", letterSpacing: "0.08em",
      textTransform: "uppercase", margin: "8px 0 10px 0",
    },
    card: {
      background: "#fff", border: "1px solid #e7e5e4", borderRadius: 10,
      padding: "18px 20px", marginBottom: 14,
    },
    cardHead: {
      display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
    },
    cardTitle: { fontSize: 15, fontWeight: 600, color: "#1c1917" },
    cardSub: { fontSize: 13, color: "#78716c", marginLeft: 6 },
    statusPill: {
      marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5,
      fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 10,
    },
    pillOk: { background: "#d1fae5", color: "#047857" },
    pillWarn: { background: "#fef3c7", color: "#92400e" },
    pillOff: { background: "#f5f5f4", color: "#78716c" },
    dot: { width: 5, height: 5, borderRadius: "50%", background: "currentColor" },

    formGrid: {
      display: "grid", gridTemplateColumns: "130px 1fr 130px 1fr",
      columnGap: 12, rowGap: 10, alignItems: "center",
    },
    formGridWide: {
      display: "grid", gridTemplateColumns: "130px 1fr",
      columnGap: 12, rowGap: 10, alignItems: "center",
    },
    fieldLabel: { fontSize: 13, color: "#57534e", fontWeight: 500 },
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
    btnDanger: {
      background: "#fff", color: "#b91c1c", border: "1px solid #fecaca",
      padding: "0 12px", height: 30, fontSize: 13, fontWeight: 500,
      cursor: "pointer", borderRadius: 6,
    },
    inlineAction: { marginLeft: "auto", fontSize: 12, color: "#6b1f7a", cursor: "pointer", background: "transparent", border: "none", fontWeight: 500 },

    // Danger zone
    dangerCard: {
      background: "#fff", border: "1px solid #fecaca", borderRadius: 10,
      padding: "18px 20px", marginBottom: 14,
    },
    dangerHead: { fontSize: 14, fontWeight: 700, color: "#b91c1c", marginBottom: 4 },
    dangerSub: { fontSize: 13, color: "#78716c", marginBottom: 14 },
    dangerRow: {
      display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center",
      padding: "10px 0", borderTop: "1px solid #fef2f2", gap: 12,
    },
    dangerLabel: { fontSize: 13, color: "#1c1917" },
    dangerHint: { fontSize: 12, color: "#a8a29e", marginTop: 2 },

    // RIGHT: status column
    statusCol: {
      background: "#fff", borderLeft: "1px solid #e7e5e4",
      padding: "24px 24px 28px 24px", overflowY: "auto", display: "flex",
      flexDirection: "column", gap: 18,
    },
    statusH: { fontSize: 13, fontWeight: 700, color: "#1c1917", textTransform: "uppercase", letterSpacing: "0.06em" },

    statCard: {
      border: "1px solid #e7e5e4", borderRadius: 10, padding: "14px 16px",
      background: "#fafaf9",
    },
    statNum: { fontSize: 26, fontWeight: 700, color: "#1c1917", lineHeight: 1.1 },
    statLabel: { fontSize: 12, color: "#78716c", marginTop: 2 },
    statGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 },

    toolRow: {
      display: "flex", alignItems: "center", padding: "9px 0",
      borderTop: "1px solid #f0eeec", gap: 10,
    },
    toolName: { fontSize: 13, fontWeight: 600, color: "#1c1917", width: 80 },
    toolVer: { fontSize: 12, color: "#78716c", fontFamily: 'ui-monospace, monospace' },
    toolOk: { marginLeft: "auto", color: "#047857", fontSize: 13 },
    toolBad: { marginLeft: "auto", color: "#b91c1c", fontSize: 13 },

    histRow: {
      display: "flex", flexDirection: "column", padding: "10px 0",
      borderTop: "1px solid #f0eeec", gap: 2,
    },
    histTop: { display: "flex", alignItems: "center", gap: 8, fontSize: 13 },
    histStatus: {
      fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    histApplied: { background: "#d1fae5", color: "#047857" },
    histDetected: { background: "#fef3c7", color: "#92400e" },
    histFile: { fontFamily: 'ui-monospace, monospace', fontSize: 12, color: "#1c1917" },
    histMeta: { fontSize: 12, color: "#78716c", marginLeft: 24 },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "8px 18px", fontSize: 12, color: "#78716c",
      borderTop: "1px solid #e7e5e4", background: "#fafaf9", flexShrink: 0,
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];

  function DashboardUI() {
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

          {/* LEFT — Configuration */}
          <div style={c.configCol}>
            <h1 style={c.pageTitle}>Setup</h1>
            <div style={c.pageSub}>All configuration in one place. Live status is on the right.</div>

            {/* Database */}
            <div style={c.sectionLabel}>Database</div>
            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>Active database</span>
                <select style={{...c.input, width: 220, marginLeft: 6}}>
                  <option>LosslessBob</option>
                  <option>Grateful Dead etree</option>
                </select>
                <button style={{...c.inlineAction}}>Open data folder ↗</button>
              </div>
              <div style={c.actions}>
                <button style={c.btnPrimary}>Import flat file…</button>
                <button style={c.btnGhost}>Check for update</button>
              </div>
            </div>

            {/* Master Data */}
            <div style={c.sectionLabel}>Master Data Publishing</div>
            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>Curator mode</span>
                <span style={{...c.cardSub}}>publish snapshots that ship to other users</span>
                <span style={{...c.statusPill, ...c.pillOff}}><span style={c.dot}></span> Disabled</span>
              </div>
              <div style={{...c.formGridWide, marginTop: 4}}>
                <span style={c.fieldLabel}>Status</span>
                <span style={{fontSize: 13, color: "#78716c"}}>Master version: (not yet published)</span>
              </div>
              <div style={c.actions}>
                <button style={{...c.btnPrimary, opacity: 0.5}}>Publish master update…</button>
                <button style={c.btnGhost}>Install master update…</button>
              </div>
            </div>

            {/* Integrations */}
            <div style={c.sectionLabel}>Integrations</div>

            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>qBittorrent</span>
                <span style={c.cardSub}>torrent client</span>
                <span style={{...c.statusPill, ...c.pillOk}}><span style={c.dot}></span> Connected</span>
              </div>
              <div style={c.formGrid}>
                <span style={c.fieldLabel}>Host</span><input style={c.input} defaultValue="localhost" />
                <span style={c.fieldLabel}>Port</span><input style={c.input} defaultValue="8080" />
                <span style={c.fieldLabel}>Username</span><input style={c.input} defaultValue="admin" />
                <span style={c.fieldLabel}>Password</span><input type="password" style={c.input} defaultValue="••••••••" />
                <span style={c.fieldLabel}>API key</span>
                <div style={{gridColumn: "2 / span 3"}}>
                  <input type="password" style={c.input} placeholder="qBittorrent 5+ — overrides username/password" />
                </div>
                <span style={c.fieldLabel}>Category</span><input style={c.input} defaultValue="losslessbob" />
                <span style={c.fieldLabel}>Tags</span><input style={c.input} placeholder="comma-separated" />
              </div>
              <div style={c.actions}>
                <button style={c.btnPrimary}>Save</button>
                <button style={c.btnGhost}>Test</button>
                <button style={c.btnGhost}>Clear</button>
              </div>
            </div>

            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>Watching the River Flow Forum</span>
                <span style={{...c.statusPill, ...c.pillWarn}}><span style={c.dot}></span> Not tested</span>
              </div>
              <div style={c.formGrid}>
                <span style={c.fieldLabel}>Username</span><input style={c.input} />
                <span style={c.fieldLabel}>Password</span><input type="password" style={c.input} />
                <span style={c.fieldLabel}>Board ID</span>
                <div><input style={{...c.input, width: 100}} defaultValue="42" /></div>
                <span></span><span></span>
              </div>
              <div style={c.actions}>
                <button style={c.btnPrimary}>Save</button>
                <button style={c.btnGhost}>Test</button>
                <button style={c.btnGhost}>Clear</button>
              </div>
            </div>

            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>Web GUI</span>
                <span style={c.cardSub}>password for the web interface</span>
                <span style={{...c.statusPill, ...c.pillOff}}><span style={c.dot}></span> No password</span>
              </div>
              <div style={c.formGridWide}>
                <span style={c.fieldLabel}>Password</span>
                <input type="password" style={{...c.input, maxWidth: 280}} placeholder="Leave empty to disable auth" />
              </div>
              <div style={c.actions}>
                <button style={c.btnPrimary}>Save</button>
                <button style={c.btnGhost}>Clear</button>
              </div>
            </div>

            <div style={c.card}>
              <div style={c.cardHead}>
                <span style={c.cardTitle}>Torrent tracker list</span>
                <span style={c.cardSub}>used when creating new torrents</span>
              </div>
              <div style={c.formGridWide}>
                <span style={c.fieldLabel}>List</span>
                <select style={{...c.input, maxWidth: 240}}>
                  <option>best</option><option>all_ws</option><option>all_https</option>
                </select>
              </div>
              <div style={c.actions}>
                <button style={c.btnGhost}>Refresh trackers</button>
                <span style={{marginLeft: "auto", fontSize: 12, color: "#a8a29e"}}>87 trackers · refreshed 4d ago</span>
              </div>
            </div>

            {/* Preferences */}
            <div style={c.sectionLabel}>Preferences</div>
            <div style={c.card}>
              <div style={c.formGrid}>
                <span style={c.fieldLabel}>Language</span>
                <select style={c.input}>
                  <option>English</option><option>Français</option><option>Deutsch</option>
                </select>
                <span style={c.fieldLabel}>Results / page</span>
                <input style={c.input} defaultValue="50" />
              </div>
              <div style={c.actions}>
                <span style={c.fieldLabel} style={{...c.fieldLabel, fontWeight: 500}}>Column widths:</span>
                <button style={c.btnGhost}>Save as defaults</button>
                <button style={{...c.btnGhost, opacity: 0.5}}>Restore mine</button>
                <button style={c.btnGhost}>Restore factory</button>
              </div>
            </div>

            {/* Danger zone */}
            <div style={c.sectionLabel}>Advanced</div>
            <div style={c.dangerCard}>
              <div style={c.dangerHead}>Danger zone</div>
              <div style={c.dangerSub}>Destructive operations. None of these can be undone.</div>

              <div style={c.dangerRow}>
                <div>
                  <div style={c.dangerLabel}>Reset entire database</div>
                  <div style={c.dangerHint}>Drop all data and reinitialize from scratch.</div>
                </div>
                <button style={c.btnDanger}>Reset database…</button>
              </div>

              {[
                ["Purge My Collection", "Folders, ratings, alerts"],
                ["Purge Wishlist", ""],
                ["Purge personal ratings & tags", ""],
                ["Purge watchdog alerts", ""],
                ["Purge scrape diff changelog", ""],
              ].map(([label, hint]) => (
                <div key={label} style={c.dangerRow}>
                  <div>
                    <div style={c.dangerLabel}>{label}</div>
                    {hint && <div style={c.dangerHint}>{hint}</div>}
                  </div>
                  <button style={c.btnDanger}>Purge…</button>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT — Live status column */}
          <div style={c.statusCol}>
            <div>
              <div style={c.statusH}>Database</div>
              <div style={{...c.statGrid, marginTop: 10}}>
                <div style={c.statCard}>
                  <div style={c.statNum}>1.25M</div>
                  <div style={c.statLabel}>Checksums</div>
                </div>
                <div style={c.statCard}>
                  <div style={c.statNum}>24,118</div>
                  <div style={c.statLabel}>LB entries</div>
                </div>
                <div style={c.statCard}>
                  <div style={c.statNum}>LB-24118</div>
                  <div style={c.statLabel}>Latest LB</div>
                </div>
                <div style={c.statCard}>
                  <div style={{fontSize: 14, fontWeight: 600, color: "#1c1917"}}>3 days ago</div>
                  <div style={c.statLabel}>Last import</div>
                </div>
              </div>
            </div>

            <div>
              <div style={c.statusH}>External tools</div>
              <div style={c.toolRow}>
                <span style={c.toolName}>SoX</span>
                <span style={c.toolVer}>v14.4.2</span>
                <span style={c.toolOk}>✓ Found</span>
              </div>
              <div style={c.toolRow}>
                <span style={c.toolName}>ffmpeg</span>
                <span style={c.toolVer}>v6.1.1</span>
                <span style={c.toolOk}>✓ Found</span>
              </div>
              <div style={c.toolRow}>
                <span style={c.toolName}>shntool</span>
                <span style={c.toolVer}>v3.0.10</span>
                <span style={c.toolOk}>✓ Found</span>
              </div>
              <div style={{...c.actions, marginTop: 8, paddingTop: 10}}>
                <button style={c.btnGhost}>Re-check</button>
              </div>
            </div>

            <div>
              <div style={c.statusH}>Flat-file history</div>
              <div style={c.histRow}>
                <div style={c.histTop}>
                  <span style={{...c.histStatus, ...c.histApplied}}>Applied</span>
                  <span style={c.histFile}>lb_20260522.zip</span>
                </div>
                <span style={c.histMeta}>2026-05-22 · +312 / ~48 / −0</span>
              </div>
              <div style={c.histRow}>
                <div style={c.histTop}>
                  <span style={{...c.histStatus, ...c.histApplied}}>Applied</span>
                  <span style={c.histFile}>lb_20260508.zip</span>
                </div>
                <span style={c.histMeta}>2026-05-08 · +280 / ~22 / −2</span>
              </div>
              <div style={c.histRow}>
                <div style={c.histTop}>
                  <span style={{...c.histStatus, ...c.histDetected}}>Detected</span>
                  <span style={c.histFile}>lb_20260427.zip</span>
                </div>
                <span style={c.histMeta}>2026-04-27 · deferred</span>
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

  window.SetupDashboardUI = DashboardUI;
})();
