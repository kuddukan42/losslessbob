// Faithful recreation of the original UI — for honest side-by-side comparison.
(() => {
  const origStyles = {
    win: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "#e8d4ec", fontFamily: '"DejaVu Sans", "Segoe UI", sans-serif',
      fontSize: 13, color: "#0a0a0a",
    },
    titleBar: {
      background: "#0a0a0a", color: "#fff", height: 28, display: "flex",
      alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 600,
      position: "relative",
    },
    titleBtns: {
      position: "absolute", right: 8, top: 0, height: 28, display: "flex",
      alignItems: "center", gap: 12, color: "#bbb", fontSize: 14,
    },
    menuBar: {
      background: "#2a2a2a", color: "#ddd", padding: "4px 8px",
      display: "flex", gap: 18, fontSize: 13,
    },
    tabs: {
      display: "flex", gap: 0, padding: "6px 6px 0 6px",
      borderBottom: "1px solid rgba(0,0,0,0.08)",
    },
    tab: {
      padding: "6px 14px", fontSize: 13, cursor: "pointer",
      background: "transparent", border: "none",
    },
    tabActive: { fontWeight: 700, textDecoration: "underline" },
    subTabs: {
      display: "flex", gap: 0, padding: "8px 6px 6px 6px",
    },
    subTab: {
      padding: "4px 12px", fontSize: 13, cursor: "pointer",
      background: "transparent", border: "none",
    },
    subTabActive: { fontWeight: 700, textDecoration: "underline" },
    toolbar: {
      padding: "8px 10px", display: "flex", flexWrap: "wrap", gap: 8,
      alignItems: "center",
    },
    filterRow: {
      padding: "8px 10px 4px 10px", display: "flex", gap: 10, alignItems: "center",
    },
    input: {
      flex: 1, height: 28, padding: "0 10px", border: "1px solid #c5a8cb",
      background: "#fff", fontSize: 13, borderRadius: 0,
    },
    select: {
      height: 28, padding: "0 8px", border: "1px solid #c5a8cb",
      background: "#fff", fontSize: 13,
    },
    btn: {
      background: "#6b1f7a", color: "#fff", border: "none",
      padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
      borderRadius: 6,
    },
    btnDisabled: {
      background: "#c7a8cd", color: "#f0e6f2", border: "none",
      padding: "8px 14px", fontSize: 13, fontWeight: 600,
      borderRadius: 6, cursor: "not-allowed",
    },
    check: { display: "flex", alignItems: "center", gap: 6, fontSize: 13 },
    table: {
      margin: "6px 10px", border: "1px solid #c5a8cb", background: "#fff",
      flex: 1, display: "flex", flexDirection: "column", minHeight: 0,
    },
    thead: {
      display: "grid",
      gridTemplateColumns: "90px 80px 80px 230px 240px 200px 110px 90px 110px",
      background: "#6b1f7a", color: "#fff", fontWeight: 700,
      padding: "8px 10px", fontSize: 13,
    },
    tbody: { flex: 1, background: "#fff" },
    statusRow: {
      padding: "8px 12px", fontSize: 13,
    },
    historyLabel: {
      padding: "0 12px 6px 12px", fontSize: 13, fontWeight: 700,
    },
    histPanel: {
      margin: "0 10px 6px 10px", border: "1px solid #c5a8cb",
      background: "#fff",
    },
    histTabs: {
      display: "flex", gap: 0, padding: "6px 6px 0 6px",
      borderBottom: "1px solid #e0c7e5",
    },
    histTab: { padding: "4px 12px", fontSize: 13, background: "transparent", border: "none" },
    histTabActive: { fontWeight: 700, textDecoration: "underline" },
    histThead: {
      display: "grid",
      gridTemplateColumns: "180px 240px 240px 1fr",
      background: "#6b1f7a", color: "#fff", fontWeight: 700,
      padding: "8px 10px", fontSize: 13,
    },
    histBody: { height: 100, background: "#fff" },
    footerBtns: { padding: "8px 10px", display: "flex", gap: 8 },
    statusBar: {
      padding: "6px 12px", fontSize: 12, color: "#222",
      borderTop: "1px solid #c5a8cb",
    },
  };

  const topTabs = ["Lookup", "Rename Folders", "Verify", "lbdir", "Search", "Bootlegs", "My Collection", "Attachments", "Spectrograms", "DB Editor", "Scraper", "Setup", "Themes", "Map"];
  const subTabs = ["My Collection", "Missing", "Wishlist", "Duplicates", "Forum History", "Torrent History"];
  const headers = [".LB Number", "Status", "Date", "Location", "Folder Name", "Disk Path", "Confirmed", "Notes", "Fingerprinted"];

  function OriginalUI() {
    return (
      <div style={origStyles.win}>
        <div style={origStyles.titleBar}>
          LosslessBob Checksum Lookup
          <div style={origStyles.titleBtns}><span>—</span><span>▢</span><span>×</span></div>
        </div>
        <div style={origStyles.menuBar}>
          <span>File</span><span>Database</span><span>Help</span>
        </div>
        <div style={origStyles.tabs}>
          {topTabs.map((t) => (
            <button key={t} style={{...origStyles.tab, ...(t==="My Collection"?origStyles.tabActive:{})}}>{t}</button>
          ))}
        </div>
        <div style={origStyles.subTabs}>
          {subTabs.map((t) => (
            <button key={t} style={{...origStyles.subTab, ...(t==="My Collection"?origStyles.subTabActive:{})}}>{t}</button>
          ))}
        </div>
        <div style={origStyles.filterRow}>
          <input style={origStyles.input} placeholder="Filter by LB number, folder name, or path…" />
          <select style={origStyles.select}><option>All Years</option></select>
          <label style={origStyles.check}><input type="checkbox" /> Xref only</label>
        </div>
        <div style={origStyles.toolbar}>
          <button style={origStyles.btn}>Add Single Folder</button>
          <button style={origStyles.btn}>Scan Directory</button>
          <button style={origStyles.btn}>Scan Tree…</button>
          <button style={origStyles.btn}>Update Location</button>
          <button style={origStyles.btn}>Remove</button>
          <button style={origStyles.btn}>Select All</button>
          <button style={origStyles.btn}>Select None</button>
          <button style={origStyles.btn}>Refresh</button>
          <label style={origStyles.check}><input type="checkbox" /> Word wrap</label>
          <button style={origStyles.btn}>Export HTML…</button>
          <button style={origStyles.btn}>Export M3U…</button>
        </div>
        <div style={{...origStyles.toolbar, paddingTop: 0}}>
          <button style={origStyles.btn}>Create Torrent</button>
          <button style={origStyles.btn}>Add to qBittorrent</button>
          <button style={origStyles.btn}>Post to Forum</button>
        </div>
        <div style={origStyles.table}>
          <div style={origStyles.thead}>
            {headers.map((h) => <div key={h}>{h}</div>)}
          </div>
          <div style={origStyles.tbody}></div>
        </div>
        <div style={origStyles.statusRow}>0 item(s) in collection.</div>
        <div style={origStyles.historyLabel}>History</div>
        <div style={origStyles.histPanel}>
          <div style={origStyles.histTabs}>
            <button style={{...origStyles.histTab, ...origStyles.histTabActive}}>Torrents</button>
            <button style={origStyles.histTab}>Forum Posts</button>
          </div>
          <div style={{padding: "6px 10px", fontSize: 13}}>Select one entry to view its torrent history.</div>
          <div style={origStyles.histThead}>
            <div>Created</div><div>Torrent File</div><div>Source Folder</div><div>Added to qBt</div>
          </div>
          <div style={origStyles.histBody}></div>
          <div style={origStyles.footerBtns}>
            <button style={origStyles.btnDisabled}>Add to qBittorrent</button>
            <button style={origStyles.btnDisabled}>Regenerate</button>
            <button style={origStyles.btnDisabled}>Relocate Source…</button>
          </div>
        </div>
        <div style={origStyles.statusBar}>DB: LB-None | Checksums: 0 | Last import: None</div>
      </div>
    );
  }

  window.OriginalUI = OriginalUI;
})();
