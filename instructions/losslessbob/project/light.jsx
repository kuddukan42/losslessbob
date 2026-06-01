// Refined light variant — clean, dense, purple as accent only.
(() => {
  const lightStyles = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#fafaf9", fontFamily: 'ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif',
      fontSize: 13, color: "#1c1917",
      "--accent": "#6b1f7a",
    },
    titleBar: {
      background: "#fafaf9", color: "#1c1917", height: 36, display: "flex",
      alignItems: "center", padding: "0 12px", fontSize: 13, fontWeight: 600,
      borderBottom: "1px solid #e7e5e4",
      gap: 14,
    },
    appMark: {
      width: 16, height: 16, borderRadius: 4, background: "#6b1f7a",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#fff", fontSize: 10, fontWeight: 800,
    },
    menuItem: { color: "#57534e", fontSize: 13, cursor: "pointer", fontWeight: 500 },
    winCtrls: { marginLeft: "auto", display: "flex", gap: 14, color: "#a8a29e", fontSize: 13 },

    body: { display: "flex", flex: 1, minHeight: 0 },

    sidebar: {
      width: 168, borderRight: "1px solid #e7e5e4", padding: "10px 8px",
      display: "flex", flexDirection: "column", gap: 1, background: "#fafaf9",
    },
    sideGroupLabel: {
      fontSize: 11, fontWeight: 700, color: "#a8a29e", letterSpacing: "0.04em",
      textTransform: "uppercase", padding: "10px 8px 4px 8px",
    },
    sideItem: {
      padding: "5px 10px", fontSize: 13, cursor: "pointer", borderRadius: 5,
      color: "#1c1917", display: "flex", alignItems: "center",
      background: "transparent", border: "none", textAlign: "left",
    },
    sideItemActive: {
      background: "#f2e8f4", color: "#6b1f7a", fontWeight: 600,
    },

    main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },

    subTabs: {
      display: "flex", gap: 2, padding: "10px 16px 0 16px",
      borderBottom: "1px solid #e7e5e4",
    },
    subTab: {
      padding: "8px 12px", fontSize: 13, cursor: "pointer", color: "#57534e",
      background: "transparent", border: "none", borderBottom: "2px solid transparent",
      marginBottom: -1,
    },
    subTabActive: {
      color: "#6b1f7a", fontWeight: 600, borderBottom: "2px solid #6b1f7a",
    },

    actionBar: {
      padding: "12px 16px", display: "flex", gap: 8, alignItems: "center",
      borderBottom: "1px solid #f0eeec",
    },
    btnPrimary: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "0 12px", height: 30, fontSize: 13, fontWeight: 600,
      cursor: "pointer", borderRadius: 6,
      display: "inline-flex", alignItems: "center", gap: 6,
    },
    btnGhost: {
      background: "transparent", color: "#1c1917",
      border: "1px solid #e7e5e4", padding: "0 11px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    btnText: {
      background: "transparent", color: "#57534e",
      border: "none", padding: "0 8px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    btnDanger: {
      background: "transparent", color: "#b91c1c",
      border: "1px solid #fecaca", padding: "0 11px", height: 30,
      fontSize: 13, fontWeight: 500, cursor: "pointer", borderRadius: 6,
    },
    divider: { width: 1, height: 20, background: "#e7e5e4", margin: "0 4px" },
    spacer: { flex: 1 },

    tableControls: {
      padding: "10px 16px", display: "flex", gap: 8, alignItems: "center",
      background: "#fafaf9",
    },
    filterInput: {
      flex: 1, height: 30, padding: "0 10px 0 30px", border: "1px solid #e7e5e4",
      background: "#fff", fontSize: 13, borderRadius: 6, outline: "none",
      color: "#1c1917",
    },
    filterWrap: { flex: 1, position: "relative", display: "flex" },
    filterIcon: {
      position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)",
      color: "#a8a29e", pointerEvents: "none",
    },
    select: {
      height: 30, padding: "0 8px", border: "1px solid #e7e5e4",
      background: "#fff", fontSize: 13, borderRadius: 6, color: "#1c1917",
    },
    checkLabel: { display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#57534e" },
    iconBtn: {
      width: 30, height: 30, border: "1px solid #e7e5e4", background: "#fff",
      borderRadius: 6, cursor: "pointer", display: "inline-flex",
      alignItems: "center", justifyContent: "center", color: "#57534e",
    },

    tableWrap: {
      flex: 1, margin: "0 16px", border: "1px solid #e7e5e4",
      background: "#fff", borderRadius: 8, display: "flex", flexDirection: "column",
      minHeight: 0, overflow: "hidden",
    },
    thead: {
      display: "grid",
      gridTemplateColumns: "90px 90px 90px 220px 1fr 200px 100px 80px 110px",
      background: "#fafaf9", borderBottom: "1px solid #e7e5e4",
      padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "#78716c",
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    tbody: { flex: 1, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center" },
    empty: {
      display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
      color: "#78716c", textAlign: "center", padding: 32,
    },
    emptyIcon: {
      width: 40, height: 40, borderRadius: 10, background: "#f2e8f4",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      color: "#6b1f7a",
    },

    summaryRow: {
      display: "flex", alignItems: "center", padding: "8px 18px",
      fontSize: 12, color: "#78716c",
    },

    historySection: {
      borderTop: "1px solid #e7e5e4", background: "#fafaf9",
    },
    historyHead: {
      display: "flex", alignItems: "center", padding: "10px 16px 0 16px", gap: 16,
    },
    historyTitle: { fontSize: 12, fontWeight: 700, color: "#1c1917", textTransform: "uppercase", letterSpacing: "0.04em" },
    historyTabs: { display: "flex", gap: 2, marginLeft: 8 },
    historyTab: {
      padding: "4px 10px", fontSize: 12, background: "transparent", border: "none",
      cursor: "pointer", color: "#78716c", borderRadius: 5,
    },
    historyTabActive: { background: "#fff", color: "#1c1917", fontWeight: 600, border: "1px solid #e7e5e4" },
    historyHint: { marginLeft: "auto", fontSize: 12, color: "#a8a29e", fontStyle: "italic" },
    historyBody: {
      margin: "8px 16px 12px 16px", border: "1px solid #e7e5e4",
      borderRadius: 8, background: "#fff",
    },
    histThead: {
      display: "grid",
      gridTemplateColumns: "160px 1fr 1fr 120px",
      borderBottom: "1px solid #e7e5e4",
      padding: "8px 14px", fontSize: 11, fontWeight: 600, color: "#78716c",
      textTransform: "uppercase", letterSpacing: "0.04em",
    },
    histBody: { height: 70 },
    histActions: {
      borderTop: "1px solid #f0eeec", padding: "8px 12px", display: "flex", gap: 6,
    },
    btnDisabled: {
      background: "#fafaf9", color: "#a8a29e",
      border: "1px solid #f0eeec", padding: "0 11px", height: 28,
      fontSize: 12, fontWeight: 500, borderRadius: 6, cursor: "not-allowed",
    },

    statusBar: {
      display: "flex", alignItems: "center", gap: 14,
      padding: "6px 16px", fontSize: 12, color: "#78716c",
      borderTop: "1px solid #e7e5e4", background: "#fafaf9",
    },
    statusDot: { width: 6, height: 6, borderRadius: "50%", background: "#9ca3af" },
  };

  const sideItems = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];
  const subTabs = ["My Collection", "Missing", "Wishlist", "Duplicates", "Forum History", "Torrent History"];
  const headers = ["LB #", "Status", "Date", "Location", "Folder Name", "Disk Path", "Confirmed", "Notes", "Fp."];

  function LightUI() {
    return (
      <div style={lightStyles.win}>
        <div style={lightStyles.titleBar}>
          <span style={lightStyles.appMark}>L</span>
          <span>LosslessBob</span>
          <span style={{color: "#a8a29e", fontWeight: 400}}>· Checksum Lookup</span>
          <span style={{...lightStyles.menuItem, marginLeft: 18}}>File</span>
          <span style={lightStyles.menuItem}>Database</span>
          <span style={lightStyles.menuItem}>Help</span>
          <div style={lightStyles.winCtrls}><span>—</span><span>▢</span><span>×</span></div>
        </div>

        <div style={lightStyles.body}>
          <div style={lightStyles.sidebar}>
            <div style={lightStyles.sideGroupLabel}>Library</div>
            {["Lookup", "Search", "My Collection", "Bootlegs"].map(t => (
              <button key={t} style={{...lightStyles.sideItem, ...(t==="My Collection"?lightStyles.sideItemActive:{})}}>{t}</button>
            ))}
            <div style={lightStyles.sideGroupLabel}>Manage</div>
            {["Verify", "Rename Folders", "lbdir", "Attachments", "Spectrograms"].map(t => (
              <button key={t} style={lightStyles.sideItem}>{t}</button>
            ))}
            <div style={lightStyles.sideGroupLabel}>Tools</div>
            {["DB Editor", "Scraper", "Map", "Themes", "Setup"].map(t => (
              <button key={t} style={lightStyles.sideItem}>{t}</button>
            ))}
          </div>

          <div style={lightStyles.main}>
            <div style={lightStyles.subTabs}>
              {subTabs.map(t => (
                <button key={t} style={{...lightStyles.subTab, ...(t==="My Collection"?lightStyles.subTabActive:{})}}>{t}</button>
              ))}
            </div>

            <div style={lightStyles.actionBar}>
              <button style={lightStyles.btnPrimary}>
                <span style={{fontSize: 14, lineHeight: 1}}>+</span> Scan Directory
              </button>
              <button style={lightStyles.btnGhost}>Add Single Folder</button>
              <button style={lightStyles.btnGhost}>Scan Tree…</button>
              <div style={lightStyles.divider}></div>
              <button style={lightStyles.btnText}>Create Torrent</button>
              <button style={lightStyles.btnText}>Add to qBittorrent</button>
              <button style={lightStyles.btnText}>Post to Forum</button>
              <div style={lightStyles.spacer}></div>
              <button style={lightStyles.btnGhost}>Export HTML</button>
              <button style={lightStyles.btnGhost}>Export M3U</button>
            </div>

            <div style={lightStyles.tableControls}>
              <div style={lightStyles.filterWrap}>
                <span style={lightStyles.filterIcon}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
                </span>
                <input style={lightStyles.filterInput} placeholder="Filter by LB number, folder name, or path…" />
              </div>
              <select style={lightStyles.select}><option>All Years</option></select>
              <label style={lightStyles.checkLabel}><input type="checkbox" /> Xref only</label>
              <label style={lightStyles.checkLabel}><input type="checkbox" /> Word wrap</label>
              <div style={lightStyles.divider}></div>
              <button style={lightStyles.btnText}>Select all</button>
              <button style={lightStyles.btnText}>Clear</button>
              <button title="Refresh" style={lightStyles.iconBtn}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/></svg>
              </button>
            </div>

            <div style={lightStyles.tableWrap}>
              <div style={lightStyles.thead}>
                {headers.map(h => <div key={h}>{h}</div>)}
              </div>
              <div style={lightStyles.tbody}>
                <div style={lightStyles.empty}>
                  <div style={lightStyles.emptyIcon}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9z"/><path d="M3 7.5 12 12l9-4.5"/><path d="M12 12v9"/></svg>
                  </div>
                  <div style={{fontSize: 14, fontWeight: 600, color: "#1c1917"}}>No folders in collection yet</div>
                  <div style={{fontSize: 13, maxWidth: 340}}>Scan a directory to import folders and match them against LB numbers, or add one folder at a time.</div>
                  <div style={{display: "flex", gap: 8, marginTop: 6}}>
                    <button style={lightStyles.btnPrimary}>Scan Directory</button>
                    <button style={lightStyles.btnGhost}>Add Single Folder</button>
                  </div>
                </div>
              </div>
            </div>

            <div style={lightStyles.summaryRow}>
              <span>0 items · 0 confirmed · 0 fingerprinted</span>
              <div style={lightStyles.spacer}></div>
              <button style={{...lightStyles.btnDanger, opacity: 0.5}}>Remove selected</button>
            </div>

            <div style={lightStyles.historySection}>
              <div style={lightStyles.historyHead}>
                <span style={lightStyles.historyTitle}>History</span>
                <div style={lightStyles.historyTabs}>
                  <button style={{...lightStyles.historyTab, ...lightStyles.historyTabActive}}>Torrents</button>
                  <button style={lightStyles.historyTab}>Forum Posts</button>
                </div>
                <span style={lightStyles.historyHint}>Select an entry above to view its history</span>
              </div>
              <div style={lightStyles.historyBody}>
                <div style={lightStyles.histThead}>
                  <div>Created</div><div>Torrent file</div><div>Source folder</div><div>Added to qBt</div>
                </div>
                <div style={lightStyles.histBody}></div>
                <div style={lightStyles.histActions}>
                  <button style={lightStyles.btnDisabled}>Add to qBittorrent</button>
                  <button style={lightStyles.btnDisabled}>Regenerate</button>
                  <button style={lightStyles.btnDisabled}>Relocate source…</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style={lightStyles.statusBar}>
          <span style={lightStyles.statusDot}></span>
          <span>DB: <strong style={{color:"#1c1917", fontWeight: 600}}>LB-None</strong></span>
          <span>·</span>
          <span>Checksums: <strong style={{color:"#1c1917", fontWeight: 600}}>0</strong></span>
          <span>·</span>
          <span>Last import: never</span>
        </div>
      </div>
    );
  }

  window.LightUI = LightUI;
})();
