// Faithful recreation of the existing Setup tab from gui/setup_tab.py.
// PyQt6 QGroupBox / QGridLayout / QHBoxLayout / QVBoxLayout structure preserved.
(() => {
  const su = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#e8d4ec", fontFamily: '"DejaVu Sans", "Segoe UI", sans-serif',
      fontSize: 13, color: "#0a0a0a", overflow: "hidden",
    },
    titleBar: {
      background: "#0a0a0a", color: "#fff", height: 28, display: "flex",
      alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 600,
      position: "relative", flexShrink: 0,
    },
    titleBtns: {
      position: "absolute", right: 8, top: 0, height: 28, display: "flex",
      alignItems: "center", gap: 12, color: "#bbb", fontSize: 14,
    },
    menuBar: {
      background: "#2a2a2a", color: "#ddd", padding: "4px 8px",
      display: "flex", gap: 18, fontSize: 13, flexShrink: 0,
    },
    tabs: {
      display: "flex", gap: 0, padding: "6px 6px 0 6px",
      borderBottom: "1px solid rgba(0,0,0,0.08)", flexShrink: 0,
    },
    tab: {
      padding: "6px 14px", fontSize: 13, cursor: "pointer",
      background: "transparent", border: "none",
    },
    tabActive: { fontWeight: 700, textDecoration: "underline" },

    // Scrollable content host
    scrollHost: {
      flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 10px 4px 10px",
      display: "flex", flexDirection: "column", gap: 10,
    },

    // QGroupBox — Qt draws a 1px border with the title notched into the top-left.
    groupBox: {
      position: "relative", border: "1px solid #b48bbb", borderRadius: 3,
      padding: "14px 10px 10px 10px", marginTop: 8, background: "transparent",
    },
    groupTitle: {
      position: "absolute", top: -8, left: 10, padding: "0 4px",
      background: "#e8d4ec", fontSize: 13, fontWeight: 600, color: "#0a0a0a",
    },

    // Buttons — same purple as toolbar in original.jsx
    btn: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "6px 12px", fontSize: 13, fontWeight: 500, cursor: "pointer",
      borderRadius: 3,
    },
    btnDanger: {
      background: "#8B1A1A", color: "#fff", border: "none",
      padding: "6px 12px", fontSize: 13, fontWeight: 500, cursor: "pointer",
      borderRadius: 3,
    },
    btnSmall: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "4px 10px", fontSize: 13, fontWeight: 500, cursor: "pointer",
      borderRadius: 3, width: 80,
    },

    // Form controls
    input: {
      height: 24, padding: "0 6px", border: "1px solid #c5a8cb",
      background: "#fff", fontSize: 13, borderRadius: 0, color: "#0a0a0a",
      fontFamily: "inherit",
    },
    select: {
      height: 24, padding: "0 4px", border: "1px solid #c5a8cb",
      background: "#fff", fontSize: 13, borderRadius: 0, color: "#0a0a0a",
      fontFamily: "inherit",
    },
    spin: {
      height: 24, width: 80, padding: "0 4px", border: "1px solid #c5a8cb",
      background: "#fff", fontSize: 13, borderRadius: 0, color: "#0a0a0a",
      fontFamily: "inherit", textAlign: "right",
    },
    check: { display: "flex", alignItems: "center", gap: 6, fontSize: 13 },
    label: { fontSize: 13, color: "#0a0a0a" },
    labelDim: { fontSize: 11, color: "#666" },
    statusLine: { fontSize: 13, color: "#222" },

    row: { display: "flex", alignItems: "center", gap: 8, marginBottom: 6 },

    // Database group split: 3:2 with VLine
    dbInner: { display: "flex", gap: 16, alignItems: "stretch" },
    dbLeft: { flex: 3, display: "flex", flexDirection: "column", gap: 6, minWidth: 0 },
    dbRight: { flex: 2, display: "flex", flexDirection: "column", gap: 6, minWidth: 0 },
    vline: { width: 1, background: "#b48bbb" },

    // Conn row: 4 panels side by side
    connRow: { display: "flex", gap: 12, alignItems: "stretch" },
    connCol: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },

    // Grid layouts inside credential groups
    formGrid: {
      display: "grid", columnGap: 8, rowGap: 6, alignItems: "center",
    },

    // Flat file history table
    ffTable: {
      border: "1px solid #c5a8cb", background: "#fff",
      maxHeight: 160, minHeight: 100, overflow: "auto",
    },
    ffHead: {
      display: "grid",
      gridTemplateColumns: "140px 1fr 110px 80px 80px 80px",
      background: "#6b1f7a", color: "#fff", fontWeight: 700,
      padding: "6px 8px", fontSize: 12,
    },
    ffEmpty: { padding: "20px 12px", color: "#888", fontSize: 12, fontStyle: "italic" },

    // Progress bar (hidden by default in real UI)
    progressGhost: {
      height: 18, border: "1px solid #c5a8cb", background: "#fff",
      borderRadius: 0, display: "none",
    },

    statusBar: {
      padding: "6px 12px", fontSize: 12, color: "#222",
      borderTop: "1px solid #c5a8cb", background: "#e8d4ec", flexShrink: 0,
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];

  const purgeItems = [
    "My Collection (+ ratings, alerts)",
    "Wishlist",
    "Personal Ratings and Tags only",
    "Watchdog Alerts",
    "Scrape Diff Changelog",
  ];

  const trackerLists = ["best", "all_ws", "all_https", "all_http", "all_udp"];

  function Group({ title, children, style }) {
    return (
      <div style={{...su.groupBox, ...(style||{})}}>
        <div style={su.groupTitle}>{title}</div>
        {children}
      </div>
    );
  }

  function SetupOriginalUI() {
    return (
      <div style={su.win}>
        <div style={su.titleBar}>
          LosslessBob Checksum Lookup
          <div style={su.titleBtns}><span>—</span><span>▢</span><span>×</span></div>
        </div>
        <div style={su.menuBar}>
          <span>File</span><span>Database</span><span>Help</span>
        </div>
        <div style={su.tabs}>
          {topTabs.map((t) => (
            <button key={t} style={{...su.tab, ...(t === "Setup" ? su.tabActive : {})}}>{t}</button>
          ))}
        </div>

        <div style={su.scrollHost}>

          {/* ── Database group: archive controls + Data Management ── */}
          <Group title="Database">
            <div style={su.dbInner}>
              {/* LEFT: archive controls */}
              <div style={su.dbLeft}>
                <div style={su.row}>
                  <span style={su.label}>Active database:</span>
                  <select style={{...su.select, width: 200}}>
                    <option>LosslessBob</option>
                    <option>Grateful Dead etree</option>
                  </select>
                </div>

                <div style={su.statusLine}>
                  Total checksums: 1,247,392  |  LB entries: 24,118  |  Latest LB: LB-24118  |  Last import: 2026-05-22 14:03
                </div>

                <div style={{...su.row, flexWrap: "wrap"}}>
                  <button style={su.btn}>Import Database File...</button>
                  <button style={su.btn}>Check for Flat File Update</button>
                  <button style={su.btn}>Open Data Folder</button>
                </div>

                <div style={su.row}>
                  <button style={su.btnDanger} title="Drop all data and reinitialize the database from scratch">
                    Reset Database...
                  </button>
                </div>

                <div style={su.row}>
                  <span style={{...su.label, width: 60}}>SoX:</span>
                  <span style={{...su.statusLine, color: "#1a7a1a"}}>✓ Found (v14.4.2)</span>
                </div>
                <div style={su.row}>
                  <span style={{...su.label, width: 60}}>ffmpeg:</span>
                  <span style={{...su.statusLine, color: "#1a7a1a"}}>✓ Found (v6.1.1)</span>
                </div>
                <div style={su.row}>
                  <span style={{...su.label, width: 60}}>shntool:</span>
                  <span style={{...su.statusLine, color: "#1a7a1a"}}>✓ Found (v3.0.10)</span>
                  <button style={{...su.btn, padding: "3px 10px", width: 80}}>Re-check</button>
                </div>

                <div style={{...su.statusLine, minHeight: 16}}></div>
                <div style={su.progressGhost}></div>
              </div>

              {/* Vertical divider */}
              <div style={su.vline}></div>

              {/* RIGHT: Data Management */}
              <div style={su.dbRight}>
                <div style={{fontSize: 13}}>
                  <b>Data Management</b> — purge operations remove user data only; the checksum archive is never affected.
                </div>
                <div style={su.labelDim}>
                  My Collection: 0  |  Wishlist: 0  |  Personal Ratings: 0  |  Watchdog Events: 0  |  Scrape Diff Rows: 0
                </div>
                <div style={{display: "grid", gridTemplateColumns: "1fr auto", rowGap: 4, columnGap: 12, marginTop: 4}}>
                  {purgeItems.map((label) => (
                    <React.Fragment key={label}>
                      <div style={{...su.label, alignSelf: "center"}}>{label}</div>
                      <button style={su.btnSmall}>Purge…</button>
                    </React.Fragment>
                  ))}
                </div>
                <div style={{...su.statusLine, minHeight: 16, marginTop: 4}}></div>
              </div>
            </div>
          </Group>

          {/* ── Master Data ── */}
          <Group title="Master Data">
            <label style={su.check}>
              <input type="checkbox" />
              <span>Curator mode (publish-enabled)</span>
            </label>
            <div style={{...su.statusLine, marginTop: 8}}>Master version: (not yet published)</div>
            <div style={{...su.row, marginTop: 8}}>
              <button style={{...su.btn, background: "#c7a8cd", color: "#f0e6f2", cursor: "not-allowed"}}>
                Publish Master Update…
              </button>
              <button style={su.btn}>Install Master Update…</button>
            </div>
          </Group>

          {/* ── Search ── */}
          <Group title="Search">
            <div style={su.row}>
              <span style={su.label}>Results per page:</span>
              <input type="number" defaultValue={50} style={su.spin} />
            </div>
          </Group>

          {/* ── Column Widths ── */}
          <Group title="Column Widths">
            <div style={{...su.statusLine, marginBottom: 8}}>
              User defaults: none (factory widths will be used)
            </div>
            <div style={{...su.row, marginBottom: 0}}>
              <button style={su.btn} title="Snapshot current column widths as your personal defaults">
                Save as Defaults
              </button>
              <button style={{...su.btn, background: "#c7a8cd", color: "#f0e6f2", cursor: "not-allowed"}}
                      title="Apply your saved column-width defaults to all tables">
                Restore My Defaults
              </button>
              <button style={su.btn} title="Reset all column widths to factory defaults and clear your saved layout">
                Restore Factory
              </button>
            </div>
          </Group>

          {/* ── Preferences ── */}
          <Group title="Preferences">
            <div style={su.row}>
              <span style={su.label}>Interface language:</span>
              <select style={{...su.select, width: 160}}>
                <option>English</option>
                <option>Français</option>
                <option>Deutsch</option>
                <option>Italiano</option>
                <option>Español</option>
                <option>日本語</option>
              </select>
            </div>
          </Group>

          {/* ── Connection settings row: qBittorrent / WTRF / Torrent / Web GUI ── */}
          <div style={su.connRow}>

            {/* qBittorrent */}
            <div style={su.connCol}>
              <Group title="qBittorrent" style={{height: "100%", marginTop: 8}}>
                <div style={{...su.formGrid, gridTemplateColumns: "auto 1fr auto 1fr"}}>
                  <span style={su.label}>Host:</span>
                  <input style={{...su.input, width: 140}} defaultValue="localhost" />
                  <span style={su.label}>Port:</span>
                  <input type="number" defaultValue={8080} style={{...su.spin, width: 70}} />

                  <span style={su.label}>Username:</span>
                  <input style={{...su.input, width: 140}} />
                  <span style={su.label}>Password:</span>
                  <input type="password" style={{...su.input, width: 140}} />
                </div>
                <div style={{display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 8, rowGap: 6, marginTop: 6, alignItems: "center"}}>
                  <span style={su.label}>API Key:</span>
                  <input type="password" style={{...su.input}}
                         placeholder="qBittorrent 5+ — takes priority over username/password" />

                  <span style={su.label}>Category:</span>
                  <input style={{...su.input, width: 180}} placeholder="e.g. losslessbob (optional)" />

                  <span style={su.label}>Tags:</span>
                  <input style={{...su.input, width: 180}} placeholder="comma-separated (optional)" />
                </div>
                <div style={{...su.row, marginTop: 8, flexWrap: "wrap"}}>
                  <button style={su.btn}>Save Credentials</button>
                  <button style={su.btn}>Test Connection</button>
                  <button style={su.btn}>Clear Credentials</button>
                </div>
                <div style={{...su.statusLine, minHeight: 16, marginTop: 4}}></div>
              </Group>
            </div>

            {/* Watching the River Flow Forum */}
            <div style={su.connCol}>
              <Group title="Watching the River Flow Forum" style={{height: "100%", marginTop: 8}}>
                <div style={{display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 8, rowGap: 6, alignItems: "center"}}>
                  <span style={su.label}>Username:</span>
                  <input style={{...su.input, width: 200}} />

                  <span style={su.label}>Password:</span>
                  <input type="password" style={{...su.input, width: 200}} />

                  <span style={su.label}>Board ID:</span>
                  <input type="number" defaultValue={1} style={su.spin}
                         title="SMF board number from the forum URL (e.g. ?board=42.0 → 42)" />
                </div>
                <div style={{...su.row, marginTop: 8, flexWrap: "wrap"}}>
                  <button style={su.btn}>Save Credentials</button>
                  <button style={su.btn}>Test Connection</button>
                  <button style={su.btn}>Clear Credentials</button>
                </div>
                <div style={{...su.statusLine, minHeight: 16, marginTop: 4}}></div>
              </Group>
            </div>

            {/* Torrent Settings */}
            <div style={su.connCol}>
              <Group title="Torrent Settings" style={{height: "100%", marginTop: 8}}>
                <div style={{...su.row, flexWrap: "wrap"}}>
                  <span style={su.label}>Tracker list:</span>
                  <select style={{...su.select, width: 130}}>
                    {trackerLists.map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div style={{...su.row, marginTop: 6}}>
                  <button style={su.btn}>Refresh Trackers</button>
                  <span style={su.label}>—</span>
                </div>
              </Group>
            </div>

            {/* Web GUI Access */}
            <div style={su.connCol}>
              <Group title="Web GUI Access" style={{height: "100%", marginTop: 8}}>
                <div style={{display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 8, rowGap: 6, alignItems: "center"}}>
                  <span style={su.label}>Password:</span>
                  <input type="password" style={{...su.input, width: 180}}
                         placeholder="Leave empty to disable auth" />
                </div>
                <div style={{...su.row, marginTop: 8}}>
                  <button style={su.btn}>Save</button>
                  <button style={su.btn}>Clear</button>
                </div>
                <div style={{...su.statusLine, minHeight: 16, marginTop: 4}}></div>
              </Group>
            </div>

          </div>

          {/* ── Flat File History ── */}
          <Group title="Flat File History">
            <div style={su.ffTable}>
              <div style={su.ffHead}>
                <div>Detected</div>
                <div>Filename</div>
                <div>Status</div>
                <div>Added</div>
                <div>Changed</div>
                <div>Removed</div>
              </div>
              <div style={su.ffEmpty}>No flat-file releases on record yet.</div>
            </div>
          </Group>

        </div>

        <div style={su.statusBar}>DB: LB-None | Checksums: 0 | Last import: None</div>
      </div>
    );
  }

  window.SetupOriginalUI = SetupOriginalUI;
})();
