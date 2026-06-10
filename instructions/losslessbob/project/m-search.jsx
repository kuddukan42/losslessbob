// m-search.jsx — Search tab · "do I already own this?" verdict, offline-capable

(() => {
  const { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_LargeHeader: H,
          LBM_ConnChip: ConnChip, LBM_TabBar: TabBar, LBM_GroupLabel: GroupLabel,
          LBM_Card: Card } = window;

  function ScreenSearch({ onNav, onOpen }) {
    return (
      <div style={{ height: "100%", background: T.bg, position: "relative", overflow: "hidden", fontFamily: T.sf }}>
        <div style={{ height: "100%", overflowY: "auto", paddingBottom: 96 }}>
          <H title="Search" right={<ConnChip state="offline" />} />

          {/* Search field with scan */}
          <div style={{ padding: "16px 16px 0", display: "flex", gap: 9 }}>
            <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 9, background: T.card,
                          borderRadius: 12, padding: "0 12px", height: 42, boxShadow: "0 1px 2px rgba(0,0,0,0.05)" }}>
              <Ic name="search" size={18} color={T.fg3} sw={2.2} />
              <span style={{ fontSize: 16, color: T.fg, flex: 1, fontWeight: 500 }}>earl's court 1981</span>
              <Ic name="x" size={16} color={T.fg3} sw={2.2} />
            </div>
            <button style={{ all: "unset", cursor: "pointer", width: 42, height: 42, borderRadius: 12, background: T.accent,
                             display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 2px 6px rgba(43,95,208,0.28)" }}>
              <Ic name="scan" size={22} color="#fff" />
            </button>
          </div>
          <div style={{ padding: "8px 18px 0", fontSize: 12.5, color: T.fg3, display: "flex", alignItems: "center", gap: 6 }}>
            <Ic name="bolt" size={13} color={T.mute.bar} fill /> Matched against on-device cache · 704,624 checksums
          </div>

          {/* VERDICT — owned */}
          <div style={{ margin: "16px 16px 0", borderRadius: 20, overflow: "hidden",
                        background: "linear-gradient(180deg, #e7f2e2, #ffffff)", border: "1px solid " + T.ok.bar }}>
            <div style={{ padding: "18px 18px 14px", display: "flex", alignItems: "center", gap: 14 }}>
              <span style={{ width: 46, height: 46, borderRadius: 23, background: T.ok.bar, display: "flex",
                             alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Ic name="check" size={26} color="#fff" sw={3} />
              </span>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, color: T.ok.fg, letterSpacing: -0.3 }}>You own this</div>
                <div style={{ fontSize: 13.5, color: T.fg2, marginTop: 1 }}>1 exact match in your collection</div>
              </div>
            </div>
            <button onClick={() => onOpen && onOpen("LB-18")} style={{ all: "unset", cursor: "pointer", display: "block",
                          background: T.card, margin: "0 0 0", padding: "13px 18px",
                          borderTop: "1px solid " + T.ok.bg }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.accent }}>LB-18</span>
                    <Pill tone="mute">FLAC 16/44</Pill>
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: T.fg, marginTop: 2 }}>A Bird's Nest In Your Hair</div>
                  <div style={{ fontSize: 13, color: T.fg2, marginTop: 1 }}>On disk · /mnt/DYLAN2/1981/ · 624 MB</div>
                </div>
                <Ic name="chevR" size={17} color={T.fg3} sw={2.4} />
              </div>
            </button>
          </div>

          {/* Near matches incl. a not-owned one */}
          <GroupLabel>Also matched · 2</GroupLabel>
          <Card style={{ marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", position: "relative" }}>
              <span style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3.5, borderRadius: 2, background: T.ok.bar }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: T.accent }}>LB-2114</span>
                  <Pill tone="ok" soft>Owned</Pill>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: T.fg, marginTop: 2 }}>Earl's Court (1st night)</div>
                <div style={{ fontSize: 13, color: T.fg2 }}>1981-06-26 · London</div>
              </div>
              <Ic name="chevR" size={16} color={T.fg3} sw={2.4} />
              <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", position: "relative" }}>
              <span style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3.5, borderRadius: 2, background: T.bad.bar }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: T.accent }}>LB-1971</span>
                  <Pill tone="bad" dot>Not owned</Pill>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: T.fg, marginTop: 2 }}>Earl's Court (alt master)</div>
                <div style={{ fontSize: 13, color: T.fg2 }}>1981-06-29 · uncirculated</div>
              </div>
              <button style={{ all: "unset", cursor: "pointer", height: 32, padding: "0 12px", borderRadius: 16,
                               background: T.accentSoft, color: T.accent, fontSize: 13.5, fontWeight: 700,
                               display: "flex", alignItems: "center", gap: 4 }}>
                <Ic name="star" size={15} color={T.accent} sw={2} /> Wishlist
              </button>
            </div>
          </Card>

          <GroupLabel>Recent lookups</GroupLabel>
          <Card>
            {["camden 2000-07-28", "982eed1f4a3f… (checksum)", "warfield sf"].map((q, i, a) => (
              <div key={q} style={{ display: "flex", alignItems: "center", gap: 11, padding: "12px 16px", position: "relative" }}>
                <Ic name="search" size={16} color={T.fg3} sw={2} />
                <span style={{ flex: 1, fontSize: 15, color: T.fg2, fontFamily: q.includes("checksum") ? T.mono : T.sf }}>{q}</span>
                <Ic name="chevR" size={15} color={T.fg3} sw={2.2} />
                {i < a.length - 1 && <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
              </div>
            ))}
          </Card>
        </div>

        <TabBar active="search" onNav={onNav} badge="2" />
      </div>
    );
  }

  window.LBM_ScreenSearch = ScreenSearch;
})();
