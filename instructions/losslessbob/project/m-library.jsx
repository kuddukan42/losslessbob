// m-library.jsx — Library tab (browse collection · primary surface)

(() => {
  const { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_EntryRow: EntryRow,
          LBM_LargeHeader: H, LBM_ConnChip: ConnChip, LBM_TabBar: TabBar,
          LBM_GroupLabel: GroupLabel, LBM_Card: Card } = window;

  const RECENT = [
    { lb: "LB-16590", title: "Genesee Theatre, Waukegan IL", sub: "2026-03-30 · FLAC 16/44 · just synced", tone: "info", pill: <Pill tone="info" dot>New</Pill> },
    { lb: "LB-16588", title: "La Crosse Center, WI",          sub: "2026-03-27 · FLAC 16/44 · 2 CDs · 071 MB", tone: "ok", pill: <Pill tone="ok" soft>Added</Pill> },
  ];
  const ALL = [
    { lb: "LB-18",   title: "A Bird's Nest In Your Hair", sub: "1981-06-29 · Earl's Court, London · A−", tone: "ok",   pill: <Pill tone="mute">FLAC</Pill> },
    { lb: "LB-456",  title: "Massey Hall, Toronto ON",     sub: "1980-04-19 · FLAC 16/44 · 1 CD", tone: "ok",   pill: <Pill tone="mute">FLAC</Pill> },
    { lb: "LB-12",   title: "Warfield, San Francisco",     sub: "1980-11-11 · FLAC 16/44 · 2 CDs", tone: "ok",   pill: <Pill tone="mute">FLAC</Pill> },
    { lb: "LB-1422", title: "Unidentified soundboard",     sub: "Date unknown · not on disk", tone: "warn", pill: <Pill tone="warn" dot>Missing</Pill> },
    { lb: "LB-810",  title: "Fox Theatre, Atlanta GA",     sub: "1980-10-15 · FLAC 16/44 · 2 CDs", tone: "ok",   pill: <Pill tone="mute">FLAC</Pill> },
  ];

  function ScreenLibrary({ onNav, onOpen }) {
    const [seg, setSeg] = React.useState(0);
    const segs = [["All", "15,967"], ["Wishlist", "3"], ["Missing", "663"]];
    return (
      <div style={{ height: "100%", background: T.bg, position: "relative", overflow: "hidden", fontFamily: T.sf }}>
        <div style={{ height: "100%", overflowY: "auto", paddingBottom: 96 }}>
          <H title="Library"
             count="15,967 entries · 1,380 bootlegs"
             right={<ConnChip state="online" />}
             search="Find LB#, venue, date…" />

          {/* Segmented control */}
          <div style={{ margin: "16px 16px 4px", background: "rgba(118,110,95,0.12)", borderRadius: 11,
                        padding: 2, display: "flex" }}>
            {segs.map((s, i) => (
              <button key={i} onClick={() => setSeg(i)} style={{
                all: "unset", cursor: "pointer", flex: 1, textAlign: "center", padding: "7px 0", borderRadius: 9,
                background: seg === i ? T.card : "transparent",
                boxShadow: seg === i ? "0 1px 2px rgba(0,0,0,0.12)" : "none",
                fontSize: 13.5, fontWeight: seg === i ? 700 : 500, color: seg === i ? T.fg : T.fg2,
              }}>
                {s[0]} <span style={{ color: T.fg3, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{s[1]}</span>
              </button>
            ))}
          </div>

          {/* Filter chips */}
          <div style={{ display: "flex", gap: 7, padding: "10px 16px 2px", overflowX: "auto" }}>
            {["All years", "FLAC only", "A-rated", "On disk", "Fingerprinted"].map((c, i) => (
              <span key={c} style={{ flexShrink: 0, height: 30, padding: "0 13px", borderRadius: 15,
                background: i === 0 ? T.accentSoft : T.card, color: i === 0 ? T.accent : T.fg2,
                display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13.5, fontWeight: 600,
                boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                {c}{i === 0 && <Ic name="chevDown" size={14} color={T.accent} sw={2.4} />}
              </span>
            ))}
          </div>

          <GroupLabel right={<span style={{ fontSize: 13, color: T.accent, fontWeight: 600 }}>Activity →</span>}>Recently synced</GroupLabel>
          <Card>
            {RECENT.map((r, i) => (
              <EntryRow key={r.lb} {...r} right={r.pill} last={i === RECENT.length - 1}
                        onClick={() => onOpen && onOpen(r.lb)} />
            ))}
          </Card>

          <GroupLabel right={<span style={{ fontSize: 13, color: T.fg3, fontWeight: 600 }}>Date ↓</span>}>All entries · A–Z by year</GroupLabel>
          <Card>
            {ALL.map((r, i) => (
              <EntryRow key={r.lb} {...r} right={r.pill} last={i === ALL.length - 1}
                        onClick={() => onOpen && onOpen(r.lb)} />
            ))}
          </Card>
          <div style={{ textAlign: "center", padding: "16px 0 4px", fontSize: 13, color: T.fg3, fontFamily: T.mono }}>
            15,962 more · cached for offline
          </div>
        </div>

        <TabBar active="library" onNav={onNav} badge="2" />
      </div>
    );
  }

  window.LBM_ScreenLibrary = ScreenLibrary;
})();
