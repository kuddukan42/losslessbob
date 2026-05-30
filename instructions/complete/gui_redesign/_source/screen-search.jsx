// screen-search.jsx
// Library / Search — 16,630 rows, facets, group-by, virtual scroll.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Card, Chip,
          TableShell, TH, TR, TD, GroupRow, Input, IconButton } = window;

  // Sample rows — small set; the virtual-scroll banner sells the scale
  const ROWS_1980 = [
    { lb: "LB-12",  status: "Public",  date: "11/11/80", loc: "Warfield, San Francisco",   rating: "B+", desc: "unknown cass > dat, rated EX–",                xref: "—",   own: true },
    { lb: "LB-70",  status: "Public",  date: "02/05/80", loc: "Knoxville, TN",              rating: "A−", desc: "Holy Grail master from soundboard",            xref: "—",   own: true },
    { lb: "LB-456", status: "Public",  date: "04/19/80", loc: "Massey Hall, Toronto",       rating: "A",  desc: "Rock Solid master, complete 14-track set",     xref: "—",   own: true },
    { lb: "LB-810", status: "Public",  date: "10/15/80", loc: "Fox Theatre, Atlanta",       rating: "B",  desc: "Audience master, low-gen",                     xref: "—",   own: true },
  ];
  const ROWS_1981 = [
    { lb: "LB-18",   status: "Public",  date: "06/29/81", loc: "Earl's Court, London",      rating: "A−", desc: "A Bird's Nest In Your Hair · Bootleg series", xref: "172", own: true },
    { lb: "LB-130",  status: "Public",  date: "11/19/81", loc: "The Summit, Houston",       rating: "B+", desc: "Soundboard master, full show",                 xref: "—",   own: true },
    { lb: "LB-1422", status: "Missing", date: "—",        loc: "—",                          rating: "—",  desc: "—",                                            xref: "—",   own: false },
    { lb: "LB-1571", status: "Public",  date: "07/14/81", loc: "Avignon, France",           rating: "B",  desc: "FM broadcast > pre-FM lineage uncertain",      xref: "—",   own: true },
  ];
  const ROWS_1983 = [
    { lb: "LB-13680", status: "Public", date: "02/16/83", loc: "Lone Star Café, NYC",     rating: "A−", desc: "Late show · 15 tracks · IEM matrix",         xref: "—", own: true },
    { lb: "LB-1964",  status: "Public", date: "xx/xx/83", loc: "First Infidels OTs",      rating: "B",  desc: "Studio outtakes · 9 tracks · early shape",   xref: "—", own: true },
    { lb: "LB-1971",  status: "Private",date: "xx/xx/83", loc: "Power Station OTs",       rating: "B+", desc: "Studio outtakes · 137 fragments · sequenced", xref: "—", own: false },
  ];

  const FACETS = {
    decade: [
      { k: "60s", n: 302 }, { k: "70s", n: 1841 }, { k: "80s", n: 4290, on: true },
      { k: "90s", n: 3820 }, { k: "00s", n: 4109 }, { k: "10s", n: 1720 }, { k: "20s", n: 548 },
    ],
    status: [
      { k: "Public",  n: 15184, on: true },
      { k: "Private", n: 1404 },
      { k: "Missing", n: 42 },
    ],
    rating: [
      { k: "A",  n: 912 }, { k: "A−", n: 1408 }, { k: "B+", n: 2290 },
      { k: "B",  n: 1170 }, { k: "B−", n: 820 },  { k: "C",  n: 312 },
    ],
    source: [
      { k: "Soundboard", n: 4108, on: true }, { k: "FM/Pre-FM", n: 1822 },
      { k: "Audience",   n: 8920 },           { k: "Master",    n: 2304 },
      { k: "Mixed",      n: 1476 },
    ],
  };

  function RatingChip({ value }) {
    const tone = value === "A" ? "ok" : value === "A−" ? "ok" : value === "B+" ? "info" : value === "B" ? "info" : value === "B−" ? "warn" : "mute";
    return <Pill tone={tone} soft>{value}</Pill>;
  }

  function ScreenSearch() {
    return (
      <div style={{ height: "100%", display: "flex", minHeight: 0 }}>

        {/* ────────── Facet rail ────────── */}
        <aside style={{
          width: 260, flex: "0 0 260px",
          background: "var(--lbb-surface)",
          borderRight: "1px solid var(--lbb-border)",
          display: "flex", flexDirection: "column", minHeight: 0,
        }}>
          <div style={{ padding: "16px 16px 10px", borderBottom: "1px solid var(--lbb-border)" }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>Saved views</div>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
              {[
                { label: "My next listens",   n: 47,  active: true },
                { label: "A-rated unowned",   n: 38 },
                { label: "1980s shows",       n: 540 },
                { label: "Soundboards only",  n: 4108 },
              ].map((v, i) => (
                <button key={i} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 8px",
                  background: v.active ? "var(--lbb-accent-soft)" : "transparent",
                  color: v.active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                  border: "1px solid transparent",
                  borderRadius: 6, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
                }}>
                  <Icon name={v.active ? "starFill" : "star"} size={13} />
                  <span style={{ flex: 1, fontSize: 12, fontWeight: v.active ? 600 : 500 }}>{v.label}</span>
                  <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{v.n.toLocaleString()}</span>
                </button>
              ))}
              <button style={{
                display: "flex", alignItems: "center", gap: 8, padding: "6px 8px",
                background: "transparent", color: "var(--lbb-fg3)",
                border: "1px dashed var(--lbb-border2)", borderRadius: 6, cursor: "pointer",
                fontFamily: "inherit", fontSize: 11.5,
              }}>
                <Icon name="plus" size={12} /> Save current filter as view
              </button>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px 16px" }}>
            {/* Decade */}
            <FacetGroup title="Decade" items={FACETS.decade}>
              {FACETS.decade.map((f, i) => (
                <Chip key={i} active={f.on} size="sm" count={f.n}>{f.k}</Chip>
              ))}
            </FacetGroup>
            <FacetGroup title="Status">
              {FACETS.status.map((f, i) => (
                <Chip key={i} active={f.on} size="sm" count={f.n}>{f.k}</Chip>
              ))}
            </FacetGroup>
            <FacetGroup title="Rating">
              {FACETS.rating.map((f, i) => (
                <Chip key={i} active={f.on} size="sm" count={f.n}>{f.k}</Chip>
              ))}
            </FacetGroup>
            <FacetGroup title="Source">
              {FACETS.source.map((f, i) => (
                <Chip key={i} active={f.on} size="sm" count={f.n}>{f.k}</Chip>
              ))}
            </FacetGroup>

            {/* Owned segmented */}
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)", marginBottom: 8 }}>Ownership</div>
              <div style={{ display: "flex", padding: 2, background: "var(--lbb-surface2)", borderRadius: 6, border: "1px solid var(--lbb-border)" }}>
                {["Any", "Owned", "Not owned"].map((opt, i) => (
                  <button key={i} style={{
                    flex: 1, padding: "5px 8px", borderRadius: 4,
                    background: i === 0 ? "var(--lbb-surface)" : "transparent",
                    color: i === 0 ? "var(--lbb-fg)" : "var(--lbb-fg2)",
                    fontWeight: i === 0 ? 600 : 500, fontSize: 11.5,
                    border: i === 0 ? "1px solid var(--lbb-border2)" : "1px solid transparent",
                    cursor: "pointer", fontFamily: "inherit",
                  }}>{opt}</button>
                ))}
              </div>
            </div>

            {/* Year range */}
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)", marginBottom: 8 }}>
                Year range · 1980 – 1989
              </div>
              <div style={{
                position: "relative", height: 28, padding: "10px 0",
              }}>
                <div style={{ height: 4, borderRadius: 2, background: "var(--lbb-surface2)" }} />
                <div style={{
                  position: "absolute", top: 10, left: "15%", right: "55%",
                  height: 4, borderRadius: 2, background: "var(--lbb-accent-mid)",
                }} />
                <span style={{ position: "absolute", top: 6, left: "calc(15% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }} />
                <span style={{ position: "absolute", top: 6, left: "calc(45% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10.5, color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)" }}>
                <span>1961</span>
                <span>2030</span>
              </div>
            </div>

            <div style={{ marginTop: 20, display: "flex", gap: 6 }}>
              <Button variant="ghost" size="sm" block>Clear all filters</Button>
            </div>
          </div>
        </aside>

        {/* ────────── Main results ────────── */}
        <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>

          {/* Big search toolbar */}
          <div style={{
            padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <Input icon="search" placeholder="Search title, location, description, LB# …" size="lg" style={{ flex: 1, height: 38 }} />
            <Button variant="secondary" size="md" iconRight="chevDown">All Fields</Button>
            <span style={{ width: 1, height: 22, background: "var(--lbb-border)" }} />
            <Button variant="secondary" size="md" iconRight="chevDown" icon="filter">Group by year</Button>
            <Button variant="secondary" size="md" iconRight="chevDown">Columns</Button>
            <IconButton icon="download" title="Export CSV" />
            <IconButton icon="more" title="More" />
          </div>

          {/* Result summary strip */}
          <div style={{
            padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)",
            display: "flex", alignItems: "center", gap: 12,
            background: "var(--lbb-surface)", fontSize: 12,
          }}>
            <span style={{ fontWeight: 700, color: "var(--lbb-fg)", fontVariantNumeric: "tabular-nums" }}>
              245 results
            </span>
            <span style={{ color: "var(--lbb-fg3)" }}>of <strong style={{ color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>16,630</strong></span>

            <span style={{ width: 1, height: 14, background: "var(--lbb-border)" }} />

            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              <ActiveFilter label="Decade: 80s" />
              <ActiveFilter label="Status: Public" />
              <ActiveFilter label="Source: Soundboard" />
            </div>

            <div style={{ flex: 1 }} />
            <span style={{ color: "var(--lbb-fg3)" }}>Sort:</span>
            <Button variant="ghost" size="sm" iconRight="chevDown">LB# ↑</Button>
            <Button variant="ghost" size="sm">⌘F find in results</Button>
          </div>

          {/* Results table */}
          <div style={{ flex: 1, overflow: "auto", minHeight: 0, position: "relative" }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 240 }} />
                <col style={{ width: 60 }} />
                <col />
                <col style={{ width: 80 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 50 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH> </TH>
                  <TH>LB#</TH>
                  <TH>Status</TH>
                  <TH>Date</TH>
                  <TH>Location</TH>
                  <TH align="center">★</TH>
                  <TH>Description</TH>
                  <TH align="right">Xref</TH>
                  <TH align="center">Own</TH>
                  <TH> </TH>
                </tr>
              </thead>
              <tbody>
                <GroupRow label="1980 · 18 results" count={18} expanded={true} colSpan={9} />
                {ROWS_1980.map((r, i) => <ResultRow key={"a"+i} r={r} />)}

                <GroupRow label="1981 · 32 results" count={32} expanded={true} colSpan={9} />
                {ROWS_1981.map((r, i) => <ResultRow key={"b"+i} r={r} />)}

                <GroupRow label="1982 · 41 results" count={41} expanded={false} colSpan={9} />

                <GroupRow label="1983 · 22 results" count={22} expanded={true} colSpan={9} />
                {ROWS_1983.map((r, i) => <ResultRow key={"c"+i} r={r} />)}

                <tr><td colSpan={10} style={{
                  textAlign: "center", padding: "10px 0",
                  fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic",
                }}>
                  … 132 more rows below · virtual scroll, sticky header …
                </td></tr>
              </tbody>
            </TableShell>
          </div>
        </section>
      </div>
    );
  }

  function FacetGroup({ title, children }) {
    return (
      <div style={{ marginTop: 16 }}>
        <div style={{
          display: "flex", alignItems: "center", marginBottom: 8,
          fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)",
        }}>
          <span style={{ flex: 1 }}>{title}</span>
          <Icon name="chevDown" size={11} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>{children}</div>
      </div>
    );
  }

  function ActiveFilter({ label }) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "2px 4px 2px 8px", borderRadius: 4,
        background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)",
        fontSize: 11, fontWeight: 600,
      }}>
        {label}
        <button style={{
          width: 16, height: 16, borderRadius: 3,
          background: "transparent", border: "none", color: "currentColor",
          cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="x" size={10} /></button>
      </span>
    );
  }

  function ResultRow({ r }) {
    const edge = r.status === "Public" ? "ok" : r.status === "Missing" ? "warn" : r.status === "Private" ? "info" : "mute";
    return (
      <TR edge={edge}>
        <TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
        <TD><Pill tone={edge} soft>{r.status}</Pill></TD>
        <TD mono>{r.date}</TD>
        <TD style={{ color: "var(--lbb-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.loc}</TD>
        <TD align="center">{r.rating === "—" ? <span style={{ color: "var(--lbb-fg3)" }}>—</span> : <RatingChip value={r.rating} />}</TD>
        <TD style={{ color: "var(--lbb-fg2)" }}>{r.desc}</TD>
        <TD align="right" mono dim>{r.xref}</TD>
        <TD align="center">
          {r.own
            ? <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />
            : <Icon name="x" size={12} style={{ color: "var(--lbb-fg3)" }} />}
        </TD>
        <TD align="right" style={{ paddingRight: 12 }}>
          <Icon name="more" size={13} style={{ color: "var(--lbb-fg3)", cursor: "pointer" }} />
        </TD>
      </TR>
    );
  }

  window.LBB_ScreenSearch = ScreenSearch;
})();
