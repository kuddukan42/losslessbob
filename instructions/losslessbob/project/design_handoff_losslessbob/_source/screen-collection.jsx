// screen-collection.jsx
// Library / My Collection — 15,967 items, virtualized.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Card, Chip, Input, IconButton,
          TableShell, TH, TR, TD, GroupRow } = window;

  const ROWS = [
    { lb: "LB-1",     status: "ok",   date: "5/xx/87",  loc: "Dead Dylan Rehearsals · 1 & 2",         folder: "1987-05-xx Dead Dylan Rehearsals",   path: "/mnt/DYLAN1/early-87/",   conf: "2026-05-13", fp: true },
    { lb: "LB-2",     status: "ok",   date: "7/28/00",  loc: "Tweeter Center, Camden NJ",             folder: "2000-07-28 Camden NJ",               path: "/mnt/DYLAN1/2000/",       conf: "2026-05-13", fp: true },
    { lb: "LB-12",    status: "ok",   date: "11/11/80", loc: "Warfield, San Francisco",               folder: "1980-11-11 Warfield SF",             path: "/mnt/DYLAN2/1980/",       conf: "2026-05-13", fp: true },
    { lb: "LB-18",    status: "ok",   date: "06/29/81", loc: "Earl's Court, London",                  folder: "1981-06-29 Earl's Court",            path: "/mnt/DYLAN2/1981/",       conf: "2026-05-13", fp: true },
    { lb: "LB-456",   status: "ok",   date: "04/19/80", loc: "Massey Hall, Toronto ON",               folder: "1980-04-19 Toronto Massey",          path: "/mnt/DYLAN2/1980/",       conf: "2026-05-13", fp: true },
    { lb: "LB-810",   status: "ok",   date: "10/15/80", loc: "Fox Theatre, Atlanta GA",               folder: "1980-10-15 Atlanta Fox",             path: "/mnt/DYLAN2/1980/",       conf: "2026-05-13", fp: true },
    { lb: "LB-1422",  status: "warn", date: "—",         loc: "—",                                    folder: "—",                                   path: "—",                       conf: "—",          fp: false },
    { lb: "LB-13680", status: "ok",   date: "02/16/83", loc: "Lone Star Café, NYC",                   folder: "1983-02-16 Lone Star Cafe",          path: "/mnt/DYLAN3/1983/",       conf: "2026-05-14", fp: true },
    { lb: "LB-16588", status: "ok",   date: "03/27/26", loc: "La Crosse Center, WI",                  folder: "bd2026-03-27 La Crosse WI (LB-16588)",path: "/mnt/HOPPER/incoming/",   conf: "yesterday",  fp: false },
    { lb: "LB-16590", status: "info", date: "03/30/26", loc: "Waukegan, IL · Genesee Theatre",        folder: "bd2026.03.30.Waukegan.IL.flac",      path: "/mnt/HOPPER/incoming/",   conf: "today",      fp: false },
  ];

  function ScreenCollection() {
    const [tab, setTab] = React.useState("all");
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Heading */}
        <div style={{ padding: "18px 24px 14px", borderBottom: "1px solid var(--lbb-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: -0.01 }}>My Collection</h1>
            <span style={{ fontSize: 13, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>15,967 items · across 4 mounts</span>
            <div style={{ flex: 1 }} />
            <Button variant="ghost" size="sm" icon="download">Export HTML</Button>
            <Button variant="ghost" size="sm" icon="download">Export M3U</Button>
            <Button variant="secondary" size="sm" icon="copy">Create torrent</Button>
            <Button variant="primary" size="sm" icon="upload">Add to qBittorrent</Button>
          </div>

          {/* Filter chips replace second tab row */}
          <div style={{ marginTop: 12, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <Chip active={tab==="all"}        onClick={()=>setTab("all")}        count={15967}>All</Chip>
            <Chip active={tab==="missing"}    onClick={()=>setTab("missing")}    count={663}>Missing</Chip>
            <Chip active={tab==="wishlist"}   onClick={()=>setTab("wishlist")}   count={3}>Wishlist</Chip>
            <Chip active={tab==="duplicates"} onClick={()=>setTab("duplicates")} count={47}>Duplicates</Chip>
            <Chip active={tab==="forum"}      onClick={()=>setTab("forum")}      count={284}>Forum history</Chip>
            <Chip active={tab==="torrent"}    onClick={()=>setTab("torrent")}    count={1209}>Torrent history</Chip>
            <span style={{ width: 1, height: 18, background: "var(--lbb-border)", margin: "0 4px" }} />
            <Chip count={42}>Unconfirmed</Chip>
            <Chip count={128}>No fingerprint</Chip>

            <div style={{ flex: 1 }} />

            <Input icon="search" placeholder="Filter by LB#, folder, path…" size="sm" style={{ width: 320 }} />
            <Button variant="ghost" size="sm" iconRight="chevDown">All years</Button>
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--lbb-fg2)" }}>
              <input type="checkbox" /> Xref only
            </label>
          </div>
        </div>

        {/* Inline action toolbar */}
        <div style={{
          padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", gap: 6, alignItems: "center", background: "var(--lbb-surface)",
        }}>
          <Button size="sm" variant="secondary" icon="folderPlus">Add single folder</Button>
          <Button size="sm" variant="secondary" icon="search">Scan directory</Button>
          <Button size="sm" variant="secondary" icon="search">Scan tree…</Button>
          <span style={{ width: 1, height: 18, background: "var(--lbb-border)", margin: "0 4px" }} />
          <Button size="sm" variant="ghost" icon="reveal">Update location</Button>
          <Button size="sm" variant="danger" icon="trash">Remove</Button>

          <div style={{ flex: 1 }} />

          <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>15,925 confirmed · 15,839 fingerprinted</span>
        </div>

        {/* Two-pane: table + selected-row detail */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 360px", minHeight: 0 }}>
          {/* Table */}
          <div style={{ overflow: "auto", minHeight: 0 }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 36 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 100 }} />
                <col />
                <col style={{ width: 240 }} />
                <col style={{ width: 200 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 40 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH> </TH>
                  <TH><input type="checkbox" /></TH>
                  <TH>LB#</TH>
                  <TH>Status</TH>
                  <TH>Date</TH>
                  <TH>Location</TH>
                  <TH>Folder</TH>
                  <TH>Disk path</TH>
                  <TH>Confirmed</TH>
                  <TH align="center">FP</TH>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r, i) => (
                  <TR key={i} edge={r.status} selected={i === 3}>
                    <TD><input type="checkbox" defaultChecked={i === 3} /></TD>
                    <TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
                    <TD>
                      {r.status === "ok"   && <Pill tone="ok"   soft>Public</Pill>}
                      {r.status === "info" && <Pill tone="info" soft>New</Pill>}
                      {r.status === "warn" && <Pill tone="warn" soft>Missing</Pill>}
                    </TD>
                    <TD mono>{r.date}</TD>
                    <TD style={{ color: "var(--lbb-fg)" }}>{r.loc}</TD>
                    <TD mono>{r.folder}</TD>
                    <TD mono dim>{r.path}</TD>
                    <TD mono dim>{r.conf}</TD>
                    <TD align="center">
                      {r.fp
                        ? <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />
                        : <Icon name="x" size={12} style={{ color: "var(--lbb-fg3)" }} />}
                    </TD>
                  </TR>
                ))}
                <tr><td colSpan={10} style={{
                  textAlign: "center", padding: "10px 0",
                  fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic",
                }}>… 15,957 more rows below · virtual scroll, sticky header …</td></tr>
              </tbody>
            </TableShell>
          </div>

          {/* Detail panel */}
          <aside style={{
            borderLeft: "1px solid var(--lbb-border)",
            background: "var(--lbb-surface)",
            overflowY: "auto",
          }}>
            <div style={{ padding: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Pill tone="ok" soft dot>Owned</Pill>
                <Pill tone="info" soft>Public</Pill>
                <Pill tone="mute" soft>FLAC · 16/44</Pill>
              </div>
              <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 16, fontWeight: 700, color: "var(--lbb-accent-mid)", marginBottom: 2 }}>
                LB-18
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 2 }}>A Bird's Nest In Your Hair</div>
              <div style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>1981-06-29 · Earl's Court, London · 2 CDs</div>

              <div style={{
                marginTop: 14, padding: "10px 12px", borderRadius: 6,
                background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
              }}>
                <div style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: "4px 10px", fontSize: 11.5 }}>
                  <span style={{ color: "var(--lbb-fg3)" }}>Folder</span>
                  <span style={{ fontFamily: "var(--lbb-mono)" }}>1981-06-29 Earl's Court</span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Disk path</span>
                  <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>/mnt/DYLAN2/1981/</span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Size</span>
                  <span><strong>624 MB</strong> · 26 files · FLAC 16/44.1</span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Confirmed</span>
                  <span style={{ fontFamily: "var(--lbb-mono)" }}>2026-05-13</span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Fingerprinted</span>
                  <span><Pill tone="ok" soft>Yes · acoustid</Pill></span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Rating</span>
                  <span><Pill tone="ok" soft>A−</Pill></span>
                </div>
              </div>

              <div style={{ marginTop: 14, display: "flex", gap: 6, flexWrap: "wrap" }}>
                <Button size="sm" variant="secondary" icon="reveal">Reveal on disk</Button>
                <Button size="sm" variant="ghost" icon="attachments">Attachments</Button>
                <Button size="sm" variant="ghost" icon="spectro">Spectrograms</Button>
                <Button size="sm" variant="ghost" icon="map">On map</Button>
              </div>

              {/* History */}
              <div style={{ marginTop: 18 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>History</span>
                  <div style={{ flex: 1 }} />
                  <Chip active={true} size="sm">Torrents</Chip>
                  <Chip size="sm">Forum posts</Chip>
                </div>

                <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 6, overflow: "hidden" }}>
                  {[
                    { d: "2024-08-12", f: "LB-18.A.Birds.Nest.torrent", ok: true },
                    { d: "2023-02-04", f: "LB-18.full-show.v2.torrent", ok: true },
                    { d: "2021-11-18", f: "LB-18.early-master.torrent", ok: false },
                  ].map((h, i) => (
                    <div key={i} style={{
                      padding: "8px 10px", display: "flex", alignItems: "center", gap: 8,
                      borderBottom: i < 2 ? "1px solid var(--lbb-border)" : "none",
                      fontSize: 11.5,
                    }}>
                      <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>{h.d}</span>
                      <span style={{ flex: 1, fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg)" }}>{h.f}</span>
                      {h.ok ? <Pill tone="ok" soft>In qBt</Pill> : <Pill tone="mute" soft>Local</Pill>}
                    </div>
                  ))}
                </div>

                <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
                  <Button size="sm" variant="ghost">Regenerate</Button>
                  <Button size="sm" variant="ghost">Post to forum</Button>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    );
  }

  window.LBB_ScreenCollection = ScreenCollection;
})();
