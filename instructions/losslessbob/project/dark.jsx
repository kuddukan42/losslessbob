// Refined dark variant — workshop / power-user feel.
(() => {
  const darkStyles = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#15131a", fontFamily: 'ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif',
      fontSize: 13, color: "#e5e0eb",
    },
    titleBar: {
      background: "#0e0c13", color: "#e5e0eb", height: 36, display: "flex",
      alignItems: "center", padding: "0 12px", fontSize: 13, fontWeight: 600,
      borderBottom: "1px solid #221d2b",
      gap: 14,
    },
    appMark: {
      width: 16, height: 16, borderRadius: 4,
      background: "linear-gradient(135deg, #c084fc 0%, #7e22ce 100%)",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#0e0c13", fontSize: 10, fontWeight: 800,
    },
    menuItem: { color: "#9b94a8", fontSize: 13, cursor: "pointer", fontWeight: 500 },
    winCtrls: { marginLeft: "auto", display: "flex", gap: 14, color: "#5b5468", fontSize: 13 },

    body: { display: "flex", flex: 1, minHeight: 0 },

    sidebar: {
      width: 168, borderRight: "1px solid #221d2b", padding: "10px 8px",
      display: "flex", flexDirection: "column", gap: 1, background: "#0e0c13",
    },
    sideGroupLabel: {
      fontSize: 11, fontWeight: 700, color: "#5b5468", letterSpacing: "0.04em",
      textTransform: "uppercase", padding: "10px 8px 4px 8px",
    },
    sideItem: {
      padding: "5px 10px", fontSize: 13, cursor: "pointer", borderRadius: 5,
      color: "#cabfd8", background: "transparent", border: "none",
      textAlign: "left", fontFamily: "inherit",
    },
    sideItemActive: {
      background: "rgba(192, 132, 252, 0.14)", color: "#e9d5ff", fontWeight: 600,
      boxShadow: "inset 2px 0 0 #c084fc",
    },

    main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: "#15131a" },

    subTabs: {
      display: "flex", gap: 2, padding: "10px 16px 0 16px",
      borderBottom: "1px solid #221d2b",
    },
    subTab: {
      padding: "8px 12px", fontSize: 13, cursor: "pointer", color: "#9b94a8",
      background: "transparent", border: "none", borderBottom: "2px solid transparent",
      marginBottom: -1, fontFamily: "inherit",
    },
    subTabActive: {
      color: "#e9d5ff", fontWeight: 600, borderBottom: "2px solid #c084fc",
    },

    actionBar: {
      padding: "12px 16px", display: "flex", gap: 8, alignItems: "center",
      borderBottom: "1px solid #221d2b",
    },
    btnPrimary: {
      background: "#a855f7", color: "#fff", border: "none",
      padding: "0 12px", height: 30, fontSize: 13, fontWeight: 600,
      cursor: "pointer", borderRadius: 6,
      display: "inline-flex", alignItems: "center", gap: 6,
      boxShadow: "0 1px 0 rgba(255,255,255,0.15) inset, 0 1px 2px rgba(0,0,0,0.4)",
    },
    btnGhost: {
      background: "#1c1825", color: "#e5e0eb",
      border: "1px solid #2d2638", padding: "0 11px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    btnText: {
      background: "transparent", color: "#9b94a8",
      border: "none", padding: "0 8px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    btnDanger: {
      background: "transparent", color: "#fca5a5",
      border: "1px solid #4c1d24", padding: "0 11px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    divider: { width: 1, height: 20, background: "#2d2638", margin: "0 4px" },
    spacer: { flex: 1 },

    tableControls: {
      padding: "10px 16px", display: "flex", gap: 8, alignItems: "center",
    },
    filterInput: {
      flex: 1, height: 30, padding: "0 10px 0 30px",
      border: "1px solid #2d2638", background: "#1c1825",
      fontSize: 13, borderRadius: 6, outline: "none", color: "#e5e0eb",
      fontFamily: "inherit",
    },
    filterWrap: { flex: 1, position: "relative", display: "flex" },
    filterIcon: {
      position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)",
      color: "#5b5468", pointerEvents: "none",
    },
    select: {
      height: 30, padding: "0 8px", border: "1px solid #2d2638",
      background: "#1c1825", fontSize: 13, borderRadius: 6, color: "#e5e0eb",
      fontFamily: "inherit",
    },
    checkLabel: { display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#9b94a8" },
    iconBtn: {
      width: 30, height: 30, border: "1px solid #2d2638", background: "#1c1825",
      borderRadius: 6, cursor: "pointer", display: "inline-flex",
      alignItems: "center", justifyContent: "center", color: "#9b94a8",
    },

    tableWrap: {
      flex: 1, margin: "0 16px", border: "1px solid #221d2b",
      background: "#1a1721", borderRadius: 8, display: "flex", flexDirection: "column",
      minHeight: 0, overflow: "hidden",
    },
    thead: {
      display: "grid",
      gridTemplateColumns: "90px 90px 90px 220px 1fr 200px 100px 80px 110px",
      background: "#1c1825", borderBottom: "1px solid #221d2b",
      padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "#7a7188",
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    tbody: { flex: 1, background: "#1a1721", display: "flex", alignItems: "center", justifyContent: "center" },
    empty: {
      display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
      color: "#9b94a8", textAlign: "center", padding: 32,
    },
    emptyIcon: {
      width: 40, height: 40, borderRadius: 10, background: "rgba(192, 132, 252, 0.12)",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#c084fc",
    },

    summaryRow: {
      display: "flex", alignItems: "center", padding: "8px 18px",
      fontSize: 12, color: "#9b94a8",
    },

    historySection: {
      borderTop: "1px solid #221d2b", background: "#0e0c13",
    },
    historyHead: {
      display: "flex", alignItems: "center", padding: "10px 16px 0 16px", gap: 16,
    },
    historyTitle: { fontSize: 12, fontWeight: 700, color: "#cabfd8", textTransform: "uppercase", letterSpacing: "0.04em" },
    historyTabs: { display: "flex", gap: 2, marginLeft: 8 },
    historyTab: {
      padding: "4px 10px", fontSize: 12, background: "transparent", border: "none",
      cursor: "pointer", color: "#9b94a8", borderRadius: 5, fontFamily: "inherit",
    },
    historyTabActive: { background: "#1c1825", color: "#e9d5ff", fontWeight: 600, border: "1px solid #2d2638" },
    historyHint: { marginLeft: "auto", fontSize: 12, color: "#5b5468", fontStyle: "italic" },
    historyBody: {
      margin: "8px 16px 12px 16px", border: "1px solid #221d2b",
      borderRadius: 8, background: "#1a1721",
    },
    histThead: {
      display: "grid",
      gridTemplateColumns: "160px 1fr 1fr 120px",
      borderBottom: "1px solid #221d2b",
      padding: "8px 14px", fontSize: 11, fontWeight: 600, color: "#7a7188",
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    histBody: { height: 70 },
    histActions: {
      borderTop: "1px solid #221d2b", padding: "8px 12px", display: "flex", gap: 6,
    },
    btnDisabled: {
      background: "transparent", color: "#5b5468",
      border: "1px solid #221d2b", padding: "0 11px", height: 28,
      fontSize: 12, fontWeight: 500, borderRadius: 6, cursor: "not-allowed",
    },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "6px 16px", fontSize: 12, color: "#7a7188",
      borderTop: "1px solid #221d2b", background: "#0e0c13",
      fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
    },
    statusDot: { width: 6, height: 6, borderRadius: "50%", background: "#5b5468" },
  };

  const subTabs = ["My Collection", "Missing", "Wishlist", "Duplicates", "Forum History", "Torrent History"];
  const headers = ["LB #", "Status", "Date", "Location", "Folder Name", "Disk Path", "Confirmed", "Notes", "Fp."];

  function DarkUI() {
    return (
      <div style={darkStyles.win}>
        <div style={darkStyles.titleBar}>
          <span style={darkStyles.appMark}>L</span>
          <span>LosslessBob</span>
          <span style={{color: "#5b5468", fontWeight: 400}}>· Checksum Lookup</span>
          <span style={{...darkStyles.menuItem, marginLeft: 18}}>File</span>
          <span style={darkStyles.menuItem}>Database</span>
          <span style={darkStyles.menuItem}>Help</span>
          <div style={darkStyles.winCtrls}><span>—</span><span>▢</span><span>×</span></div>
        </div>

        <div style={darkStyles.body}>
          <div style={darkStyles.sidebar}>
            <div style={darkStyles.sideGroupLabel}>Library</div>
            {["Lookup", "Search", "My Collection", "Bootlegs"].map(t => (
              <button key={t} style={{...darkStyles.sideItem, ...(t==="My Collection"?darkStyles.sideItemActive:{})}}>{t}</button>
            ))}
            <div style={darkStyles.sideGroupLabel}>Manage</div>
            {["Verify", "Rename Folders", "lbdir", "Attachments", "Spectrograms"].map(t => (
              <button key={t} style={darkStyles.sideItem}>{t}</button>
            ))}
            <div style={darkStyles.sideGroupLabel}>Tools</div>
            {["DB Editor", "Scraper", "Map", "Themes", "Setup"].map(t => (
              <button key={t} style={darkStyles.sideItem}>{t}</button>
            ))}
          </div>

          <div style={darkStyles.main}>
            <div style={darkStyles.subTabs}>
              {subTabs.map(t => (
                <button key={t} style={{...darkStyles.subTab, ...(t==="My Collection"?darkStyles.subTabActive:{})}}>{t}</button>
              ))}
            </div>

            <div style={darkStyles.actionBar}>
              <button style={darkStyles.btnPrimary}>
                <span style={{fontSize: 14, lineHeight: 1}}>+</span> Scan Directory
              </button>
              <button style={darkStyles.btnGhost}>Add Single Folder</button>
              <button style={darkStyles.btnGhost}>Scan Tree…</button>
              <div style={darkStyles.divider}></div>
              <button style={darkStyles.btnText}>Create Torrent</button>
              <button style={darkStyles.btnText}>Add to qBittorrent</button>
              <button style={darkStyles.btnText}>Post to Forum</button>
              <div style={darkStyles.spacer}></div>
              <button style={darkStyles.btnGhost}>Export HTML</button>
              <button style={darkStyles.btnGhost}>Export M3U</button>
            </div>

            <div style={darkStyles.tableControls}>
              <div style={darkStyles.filterWrap}>
                <span style={darkStyles.filterIcon}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
                </span>
                <input style={darkStyles.filterInput} placeholder="Filter by LB number, folder name, or path…" />
              </div>
              <select style={darkStyles.select}><option>All Years</option></select>
              <label style={darkStyles.checkLabel}><input type="checkbox" /> Xref only</label>
              <label style={darkStyles.checkLabel}><input type="checkbox" /> Word wrap</label>
              <div style={darkStyles.divider}></div>
              <button style={darkStyles.btnText}>Select all</button>
              <button style={darkStyles.btnText}>Clear</button>
              <button title="Refresh" style={darkStyles.iconBtn}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/></svg>
              </button>
            </div>

            <div style={darkStyles.tableWrap}>
              <div style={darkStyles.thead}>
                {headers.map(h => <div key={h}>{h}</div>)}
              </div>
              <div style={darkStyles.tbody}>
                <div style={darkStyles.empty}>
                  <div style={darkStyles.emptyIcon}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9z"/><path d="M3 7.5 12 12l9-4.5"/><path d="M12 12v9"/></svg>
                  </div>
                  <div style={{fontSize: 14, fontWeight: 600, color: "#e5e0eb"}}>No folders in collection yet</div>
                  <div style={{fontSize: 13, maxWidth: 340}}>Scan a directory to import folders and match them against LB numbers, or add one folder at a time.</div>
                  <div style={{display: "flex", gap: 8, marginTop: 6}}>
                    <button style={darkStyles.btnPrimary}>Scan Directory</button>
                    <button style={darkStyles.btnGhost}>Add Single Folder</button>
                  </div>
                </div>
              </div>
            </div>

            <div style={darkStyles.summaryRow}>
              <span>0 items · 0 confirmed · 0 fingerprinted</span>
              <div style={darkStyles.spacer}></div>
              <button style={{...darkStyles.btnDanger, opacity: 0.5}}>Remove selected</button>
            </div>

            <div style={darkStyles.historySection}>
              <div style={darkStyles.historyHead}>
                <span style={darkStyles.historyTitle}>History</span>
                <div style={darkStyles.historyTabs}>
                  <button style={{...darkStyles.historyTab, ...darkStyles.historyTabActive}}>Torrents</button>
                  <button style={darkStyles.historyTab}>Forum Posts</button>
                </div>
                <span style={darkStyles.historyHint}>Select an entry above to view its history</span>
              </div>
              <div style={darkStyles.historyBody}>
                <div style={darkStyles.histThead}>
                  <div>Created</div><div>Torrent file</div><div>Source folder</div><div>Added to qBt</div>
                </div>
                <div style={darkStyles.histBody}></div>
                <div style={darkStyles.histActions}>
                  <button style={darkStyles.btnDisabled}>Add to qBittorrent</button>
                  <button style={darkStyles.btnDisabled}>Regenerate</button>
                  <button style={darkStyles.btnDisabled}>Relocate source…</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style={darkStyles.statusBar}>
          <span style={darkStyles.statusDot}></span>
          <span>DB: <strong style={{color:"#e5e0eb", fontWeight: 600}}>LB-None</strong></span>
          <span>·</span>
          <span>Checksums: <strong style={{color:"#e5e0eb", fontWeight: 600}}>0</strong></span>
          <span>·</span>
          <span>Last import: never</span>
        </div>
      </div>
    );
  }

  window.DarkUI = DarkUI;
})();
