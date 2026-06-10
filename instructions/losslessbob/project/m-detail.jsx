// m-detail.jsx — Entry detail (LB metadata · the core browse payoff)

(() => {
  const { LBM_T: T, LBM_Ic: Ic, LBM_Pill: Pill, LBM_NavHeader: NavHeader,
          LBM_GroupLabel: GroupLabel, LBM_Card: Card } = window;

  function KV({ k, v, mono, tone, last }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", position: "relative", fontFamily: T.sf }}>
        <span style={{ fontSize: 15, color: T.fg2, width: 104, flexShrink: 0 }}>{k}</span>
        <span style={{ flex: 1, fontSize: 15, color: tone || T.fg, textAlign: "right",
                       fontFamily: mono ? T.mono : T.sf, fontWeight: mono ? 500 : 500,
                       overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v}</span>
        {!last && <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
      </div>
    );
  }

  function Action({ icon, label }) {
    return (
      <button style={{ all: "unset", cursor: "pointer", flex: 1, display: "flex", flexDirection: "column",
                       alignItems: "center", gap: 7 }}>
        <span style={{ width: 50, height: 50, borderRadius: 25, background: T.accentSoft, color: T.accent,
                       display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Ic name={icon} size={23} color={T.accent} />
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: T.fg2 }}>{label}</span>
      </button>
    );
  }

  const TRACKS = ["01  Like a Rolling Stone", "02  Maggie's Farm", "03  It Ain't Me Babe", "04  Don't Think Twice"];
  const HIST = [
    { d: "2024-08-12", f: "LB-18.A.Birds.Nest.torrent", tag: <Pill tone="ok" soft>In qBt</Pill> },
    { d: "2023-02-04", f: "LB-18.full-show.v2.torrent", tag: <Pill tone="mute">Local</Pill> },
  ];

  function ScreenDetail({ onBack }) {
    return (
      <div style={{ height: "100%", background: T.bg, position: "relative", overflow: "hidden", fontFamily: T.sf }}>
        {/* sticky-ish glass nav */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 20,
                      background: "rgba(239,236,227,0.8)", backdropFilter: "blur(14px)",
                      WebkitBackdropFilter: "blur(14px)" }}>
          <NavHeader title="LB-18" right={<>
            <span style={{ width: 32, height: 32, borderRadius: 16, background: T.card, display: "flex",
                           alignItems: "center", justifyContent: "center", boxShadow: "0 1px 2px rgba(0,0,0,0.06)" }}>
              <Ic name="star" size={17} color={T.fg2} sw={1.8} />
            </span>
            <span style={{ width: 32, height: 32, borderRadius: 16, background: T.card, display: "flex",
                           alignItems: "center", justifyContent: "center", boxShadow: "0 1px 2px rgba(0,0,0,0.06)" }}>
              <Ic name="more" size={18} color={T.fg2} />
            </span>
          </>} />
        </div>

        <div style={{ height: "100%", overflowY: "auto", paddingTop: 94, paddingBottom: 40 }}>
          {/* Hero */}
          <div style={{ padding: "0 20px 4px" }}>
            <div style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: T.accent, letterSpacing: 0.4 }}>LB-18</div>
            <h1 style={{ margin: "5px 0 0", fontSize: 27, fontWeight: 800, letterSpacing: -0.5, lineHeight: 1.1, color: T.fg }}>
              A Bird's Nest In Your Hair
            </h1>
            <div style={{ fontSize: 15, color: T.fg2, marginTop: 6 }}>1981-06-29 · Earl's Court, London · 2 CDs</div>
            <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
              <Pill tone="ok" dot>Owned</Pill>
              <Pill tone="info" soft>Public</Pill>
              <Pill tone="mute">FLAC 16/44.1</Pill>
              <Pill tone="ok" soft>Rated A−</Pill>
            </div>
          </div>

          {/* Primary streaming action (PC serves it) */}
          <div style={{ display: "flex", gap: 9, padding: "16px 16px 4px" }}>
            <button style={{ all: "unset", cursor: "pointer", flex: 1, height: 46, borderRadius: 14, background: T.accent,
                             color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                             fontSize: 16, fontWeight: 700, boxShadow: "0 2px 8px rgba(43,95,208,0.3)" }}>
              <Ic name="play" size={19} color="#fff" fill /> Stream from studio-pc
            </button>
            <button style={{ all: "unset", cursor: "pointer", width: 46, height: 46, borderRadius: 14, background: T.card,
                             display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 1px 2px rgba(0,0,0,0.06)" }}>
              <Ic name="download" size={21} color={T.accent} />
            </button>
          </div>

          {/* Quick actions */}
          <div style={{ display: "flex", gap: 4, padding: "18px 12px 6px" }}>
            <Action icon="spectro" label="Spectrograms" />
            <Action icon="map" label="On map" />
            <Action icon="attach" label="Attachments" />
            <Action icon="forum" label="Forum" />
          </div>

          {/* Metadata */}
          <GroupLabel>Database record</GroupLabel>
          <Card>
            <KV k="Folder"        v="1981-06-29 Earl's Court" mono />
            <KV k="Disk path"     v="/mnt/DYLAN2/1981/" mono tone={T.fg2} />
            <KV k="Size"          v="624 MB · 26 files" />
            <KV k="Confirmed"     v="2026-05-13" mono />
            <KV k="Fingerprint"   v="acoustid · matched" tone={T.ok.fg} />
            <KV k="Checksums"     v="26 / 26 verified" tone={T.ok.fg} last />
          </Card>

          {/* Tracks */}
          <GroupLabel right={<span style={{ fontSize: 13, color: T.accent, fontWeight: 600 }}>All 26 →</span>}>Setlist</GroupLabel>
          <Card>
            {TRACKS.map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", position: "relative" }}>
                <Ic name="wave" size={17} color={T.fg3} sw={1.6} />
                <span style={{ flex: 1, fontSize: 15, color: T.fg, fontFamily: T.mono }}>{t}</span>
                <Ic name="play" size={16} color={T.fg3} />
                {i < TRACKS.length - 1 && <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
              </div>
            ))}
            <div style={{ padding: "10px 16px", fontSize: 13.5, color: T.fg3, fontFamily: T.mono }}>+22 more · d1t05 … d2t11</div>
          </Card>

          {/* History */}
          <GroupLabel right={<span style={{ fontSize: 13, color: T.fg3, fontWeight: 600 }}>Torrents · Forum</span>}>History</GroupLabel>
          <Card style={{ marginBottom: 18 }}>
            {HIST.map((h, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", position: "relative" }}>
                <span style={{ fontFamily: T.mono, fontSize: 12.5, color: T.fg2 }}>{h.d}</span>
                <span style={{ flex: 1, fontFamily: T.mono, fontSize: 12.5, color: T.fg,
                               overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.f}</span>
                {h.tag}
                {i < HIST.length - 1 && <span style={{ position: "absolute", left: 16, right: 0, bottom: 0, height: 0.5, background: T.sep }} />}
              </div>
            ))}
          </Card>
        </div>
      </div>
    );
  }

  window.LBM_ScreenDetail = ScreenDetail;
})();
