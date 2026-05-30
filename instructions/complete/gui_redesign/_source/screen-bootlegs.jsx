// screen-bootlegs.jsx — Library / Bootlegs catalog + detail panel.
(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, TableShell, TH, TR, TD } = window;

  const ROWS = [
    { lb: "LB-00018", title: "A Bird's Nest In Your Hair", date: "06/29/81", year: 1981, loc: "Earl's Court, London",         cds: 2, status: "Public",  own: true,  sel: true },
    { lb: "LB-00047", title: "Cardiff International Arena", date: "09/23/00", year: 2000, loc: "International Arena, Cardiff", cds: 2, status: "Public",  own: true },
    { lb: "LB-00049", title: "Dublin Point Theatre",        date: "09/14/00", year: 2000, loc: "The Point Theatre, Dublin",    cds: 2, status: "Public",  own: true },
    { lb: "LB-00070", title: "Knoxville Holy Grail",        date: "02/05/80", year: 1980, loc: "Civic Coliseum, Knoxville",    cds: 2, status: "Public",  own: true },
    { lb: "LB-00130", title: "Houston Soundboard",          date: "11/19/81", year: 1981, loc: "The Summit, Houston",          cds: 2, status: "Public",  own: true },
    { lb: "LB-00388", title: "Going Going Guam",            date: "xx/xx/76", year: 1976, loc: "Going Going Guam",             cds: 4, status: "Public",  own: true },
    { lb: "LB-00456", title: "Rock Solid",                  date: "04/19/80", year: 1980, loc: "Massey Hall, Toronto",         cds: 2, status: "Public",  own: true },
    { lb: "LB-00608", title: "Stockholm Sundance",          date: "06/27/84", year: 1984, loc: "Johanneshov, Stockholm",       cds: 3, status: "Private", own: false },
    { lb: "LB-00911", title: "Hard To Find",                date: "xx/xx/86", year: 1986, loc: "various",                       cds: 4, status: "Public",  own: false },
    { lb: "LB-01023", title: "I'll Remember You",           date: "06/24/86", year: 1986, loc: "Reseda CA",                     cds: 2, status: "Public",  own: true },
  ];

  function ScreenBootlegs() {
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div style={{ padding: "18px 24px 12px", borderBottom: "1px solid var(--lbb-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: -0.01 }}>Bootleg titles</h1>
            <span style={{ fontSize: 13, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>1,380 titles · LBBCD catalog</span>
            <div style={{ flex: 1 }} />
            <Button variant="ghost" size="sm" icon="download">Export CSV</Button>
            <Button variant="secondary" size="sm" icon="refresh">Refresh LBBCD</Button>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
            <Input icon="search" placeholder="Search title or location…" size="sm" style={{ width: 360 }} />
            <Button variant="ghost" size="sm" iconRight="chevDown">Year</Button>
            <Button variant="ghost" size="sm" iconRight="chevDown">CDs</Button>
            <Button variant="ghost" size="sm" iconRight="chevDown">All statuses</Button>
            <Chip count={1210}>Owned</Chip>
            <Chip count={170}>Unowned</Chip>
            <Chip count={42}>Private</Chip>
            <div style={{ flex: 1 }} />
            <Button variant="ghost" size="sm">Clear</Button>
          </div>
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 380px", minHeight: 0 }}>
          <div style={{ overflow: "auto", minHeight: 0 }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 100 }} />
                <col />
                <col style={{ width: 90 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 220 }} />
                <col style={{ width: 50 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 60 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH> </TH>
                  <TH>LB#</TH>
                  <TH>Title</TH>
                  <TH>Date</TH>
                  <TH>Year</TH>
                  <TH>Location</TH>
                  <TH align="center">CDs</TH>
                  <TH>Status</TH>
                  <TH align="center">Owned</TH>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r, i) => (
                  <TR key={i} edge={r.status === "Public" ? "ok" : "info"} selected={r.sel}>
                    <TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
                    <TD style={{ color: "var(--lbb-fg)", fontWeight: r.sel ? 600 : 500 }}>{r.title}</TD>
                    <TD mono>{r.date}</TD>
                    <TD mono>{r.year}</TD>
                    <TD>{r.loc}</TD>
                    <TD align="center" mono>{r.cds}</TD>
                    <TD><Pill tone={r.status === "Public" ? "ok" : "info"} soft>{r.status}</Pill></TD>
                    <TD align="center">{r.own ? <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }}/> : <Icon name="x" size={12} style={{ color: "var(--lbb-fg3)" }}/>}</TD>
                  </TR>
                ))}
                <tr><td colSpan={9} style={{ textAlign: "center", padding: "10px 0", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic" }}>
                  … 1,370 more titles below · virtual scroll …
                </td></tr>
              </tbody>
            </TableShell>
          </div>

          {/* Detail */}
          <aside style={{ borderLeft: "1px solid var(--lbb-border)", background: "var(--lbb-surface)", overflowY: "auto", padding: 18 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Bootleg detail</div>
            <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 14, color: "var(--lbb-accent-mid)", fontWeight: 700 }}>LB-00018</div>
            <h2 style={{ margin: "4px 0 4px", fontSize: 20, fontWeight: 700, letterSpacing: -0.01 }}>A Bird's Nest In Your Hair</h2>
            <div style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>1981-06-29 · Earl's Court, London · 2 CDs · LBBCD-00231</div>

            {/* Cover placeholder */}
            <div style={{
              marginTop: 14, height: 200, borderRadius: 8,
              background: "linear-gradient(135deg, #1c1a17 0%, var(--lbb-accent-lo) 100%)",
              color: "#fff", padding: 18, display: "flex", flexDirection: "column", justifyContent: "flex-end",
              position: "relative", overflow: "hidden",
            }}>
              <div style={{ position: "absolute", inset: 0, opacity: 0.25,
                background: "repeating-linear-gradient(45deg, transparent 0 12px, rgba(255,255,255,0.08) 12px 13px)" }} />
              <div style={{ position: "relative", fontSize: 10.5, letterSpacing: 0.14, textTransform: "uppercase", opacity: 0.7 }}>Bird's Nest Records · 1981</div>
              <div style={{ position: "relative", fontSize: 17, fontWeight: 700, marginTop: 2 }}>A Bird's Nest In Your Hair</div>
              <div style={{ position: "relative", fontSize: 11.5, opacity: 0.8, marginTop: 2 }}>2-CD set · Earl's Court · 1981</div>
            </div>

            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "90px 1fr", gap: "5px 12px", fontSize: 12 }}>
              <span style={{ color: "var(--lbb-fg3)" }}>Disc 1</span>
              <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>11 tracks · 65:14</span>
              <span style={{ color: "var(--lbb-fg3)" }}>Disc 2</span>
              <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>9 tracks · 52:08</span>
              <span style={{ color: "var(--lbb-fg3)" }}>Source</span>
              <span>Audience master, mid-gen cass</span>
              <span style={{ color: "var(--lbb-fg3)" }}>Notes</span>
              <span style={{ color: "var(--lbb-fg2)" }}>Bootleg series · early UK release · listed as "ABNH" in some catalogs</span>
            </div>

            <div style={{ marginTop: 14, display: "flex", gap: 6 }}>
              <Button size="sm" variant="primary" icon="search">Open in search</Button>
              <Button size="sm" variant="secondary">Open LBBCD</Button>
            </div>

            <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--lbb-border)" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>Other titles for this LB</div>
              <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", padding: "10px 12px", border: "1px dashed var(--lbb-border2)", borderRadius: 6 }}>
                Only bootleg title issued for LB-18.
              </div>
            </div>
          </aside>
        </div>
      </div>
    );
  }

  window.LBB_ScreenBootlegs = ScreenBootlegs;
})();
