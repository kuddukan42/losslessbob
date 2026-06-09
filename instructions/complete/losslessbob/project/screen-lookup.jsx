// screen-lookup.jsx
// Lookup · Match checksums against the master DB.
// Primary user-facing feature: paste/drag checksums or folders → see LB# matches.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD, GroupRow } = window;

  // ── Sample sources (mixes folders, files, listbox, clipboard) ──
  const SOURCES = [
    { kind: "folder",    name: "bd2025-07-25 Alpharetta GA",    n: 48, active: false },
    { kind: "folder",    name: "bd2025-07-26 Charlotte NC",     n: 36, active: true  },
    { kind: "folder",    name: "bd2025-09-18 Noblesville IN",   n: 14, active: false },
    { kind: "listbox",   name: "Pasted listbox · 137 lines",    n: 137, active: false },
    { kind: "file",      name: "LB-810-md5.txt",                n: 18, active: false },
    { kind: "file",      name: "LB-1964-ffp.txt",               n: 9,  active: false },
    { kind: "clipboard", name: "Clipboard · 7 checksums",       n: 7,  active: false },
  ];

  // ── Per-LB summary (one row per detected LB) ──
  const SUMMARY = [
    { lb: "LB-810",   src: "file",      given: 18, matched: 18, missing: 0, notFound: 0, dups: 0, xrefs: 0, state: "matched" },
    { lb: "LB-1964",  src: "file",      given: 9,  matched: 2,  missing: 9, notFound: 0, dups: 0, xrefs: 0, state: "incomplete" },
    { lb: "LB-1971",  src: "file",      given: 7,  matched: 0,  missing: 137, notFound: 0, dups: 7, xrefs: 0, state: "duplicate" },
    { lb: "LB-13680", src: "listbox",   given: 15, matched: 15, missing: 0, notFound: 0, dups: 0, xrefs: 0, state: "matched" },
    { lb: "LB-16573", src: "clipboard", given: 4,  matched: 4,  missing: 0, notFound: 0, dups: 0, xrefs: 4, state: "xref" },
    { lb: "—",        src: "folder",    given: 36, matched: 0,  missing: 0, notFound: 36, dups: 0, xrefs: 0, state: "notfound" },
  ];

  // Per-checksum detail rows (active = Charlotte NC, all not-found)
  const DETAIL = [
    { sum: "982eed1f4a3f5d29",  fn: "01 Like a Rolling Stone.flac",  type: "f", lb: "—",        xref: false, st: "notfound", src: "folder" },
    { sum: "9f22f83e1c1b27ee",  fn: "01 Like a Rolling Stone.flac",  type: "m", lb: "—",        xref: false, st: "notfound", src: "folder" },
    { sum: "e9fe9cd3aa1d40b1",  fn: "02 Maggie's Farm.flac",         type: "m", lb: "—",        xref: false, st: "notfound", src: "folder" },
    { sum: "4421aabc7088afe0",  fn: "02 Maggie's Farm.flac",         type: "f", lb: "LB-16573?",xref: true,  st: "xref",     src: "folder" },
    { sum: "7798aa1cef9981ee",  fn: "03 It Ain't Me Babe.flac",      type: "m", lb: "LB-1971",  xref: false, st: "duplicate", src: "folder" },
    { sum: "7798aa1cef9981ee",  fn: "03 It Ain't Me Babe.flac",      type: "m", lb: "LB-7042",  xref: false, st: "duplicate", src: "folder" },
    { sum: "112ccb44f0098ab1",  fn: "04 Don't Think Twice.flac",     type: "f", lb: "—",        xref: false, st: "notfound", src: "folder" },
  ];

  const STATE_TONE = {
    matched:    { tone: "ok",   label: "Matched",    color: "var(--lbb-ok-fg)" },
    incomplete: { tone: "warn", label: "Incomplete", color: "var(--lbb-warn-fg)" },
    notfound:   { tone: "bad",  label: "Not found",  color: "var(--lbb-bad-fg)" },
    duplicate:  { tone: "warn", label: "Duplicate",  color: "#a08200" },
    xref:       { tone: "info", label: "XRef",       color: "var(--lbb-info-fg)" },
  };

  const SRC_ICON = { folder: "folder", file: "attachments", listbox: "search", clipboard: "copy" };

  function SourceRow({ src, active, onClick }) {
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "6px 10px", marginBottom: 1, borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid " + (active ? "var(--lbb-accent-line)" : "transparent"),
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}>
        <Icon name={SRC_ICON[src.kind] || "folder"} size={12} style={{ color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)" }} />
        <span style={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontFamily: "var(--lbb-mono)", fontSize: 11 }}>{src.name}</span>
        <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{src.n}</span>
      </button>
    );
  }

  function ScreenLookup() {
    const [filter, setFilter] = React.useState("all");
    const [filterMy, setFilterMy] = React.useState(true);

    const counts = SUMMARY.reduce((a, r) => {
      a[r.state] = (a[r.state] || 0) + 1;
      a.total = (a.total || 0) + 1;
      a.totalSums = (a.totalSums || 0) + r.given;
      return a;
    }, {});

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Header */}
        <div style={{
          padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="lookup" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Lookup</h1>
              <Pill tone="mute" soft>checksums → master DB</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              Identifies LB numbers for any set of checksums. Per-LB summary + per-checksum detail.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: "var(--lbb-fg2)", fontFamily: "var(--lbb-mono)" }}>
            {counts.totalSums?.toLocaleString()} checksums · {counts.total} LBs
          </span>
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Sources rail */}
          <aside style={{
            width: 280, flex: "0 0 280px",
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Sources</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 8 }}>
                <Button variant="secondary" size="sm" icon="copy" block>Clipboard</Button>
                <Button variant="secondary" size="sm" icon="search" block>Listbox…</Button>
                <Button variant="secondary" size="sm" icon="attachments" block>Files…</Button>
                <Button variant="secondary" size="sm" icon="folderPlus" block>Folders…</Button>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--lbb-fg2)" }}>
                <input type="checkbox" checked={filterMy} onChange={() => setFilterMy(!filterMy)} />
                Hide <span style={{ fontFamily: "var(--lbb-mono)" }}>_mychecksums</span> files
              </label>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {SOURCES.map((s, i) => <SourceRow key={i} src={s} active={s.active} />)}
            </div>
            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="lookup" block>Lookup all sources</Button>
              <Button variant="secondary" size="sm" icon="plus" block>Generate missing</Button>
              <Button variant="ghost" size="sm" icon="trash" block>Clear sources</Button>
            </div>
          </aside>

          {/* Main */}
          <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            {/* Status counters */}
            <div style={{
              padding: "12px 24px", borderBottom: "1px solid var(--lbb-border)",
              background: "var(--lbb-surface)",
              display: "flex", alignItems: "stretch", gap: 8,
            }}>
              {[
                { k: "matched",    l: "Matched",    n: counts.matched    || 0 },
                { k: "incomplete", l: "Incomplete", n: counts.incomplete || 0 },
                { k: "notfound",   l: "Not found",  n: counts.notfound   || 0 },
                { k: "duplicate",  l: "Duplicates", n: counts.duplicate  || 0 },
                { k: "xref",       l: "Cross-refs", n: counts.xref       || 0 },
              ].map(c => {
                const t = STATE_TONE[c.k];
                const active = filter === c.k;
                return (
                  <button key={c.k} onClick={() => setFilter(active ? "all" : c.k)}
                    style={{
                      flex: 1, padding: "8px 12px", borderRadius: 6,
                      background: active ? `var(--lbb-${t.tone}-bg)` : "var(--lbb-surface)",
                      border: `1px solid ${active ? t.color : "var(--lbb-border)"}`,
                      cursor: "pointer", fontFamily: "inherit", textAlign: "left",
                      display: "flex", flexDirection: "column", gap: 2,
                    }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: t.color }} />
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: t.color, letterSpacing: 0.06, textTransform: "uppercase" }}>{c.l}</span>
                    </div>
                    <span style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg)", lineHeight: 1.1 }}>{c.n}</span>
                  </button>
                );
              })}
            </div>

            <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
              {/* Summary table */}
              <div style={{ padding: "16px 24px 6px", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
                  Match summary
                </span>
                <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>per LB number · double-click to open on LB.com</span>
                <div style={{ flex: 1 }} />
                <Button variant="ghost" size="sm" icon="copy">Copy summary</Button>
                <Button variant="ghost" size="sm" icon="download">Export CSV…</Button>
              </div>
              <div style={{ padding: "0 24px" }}>
                <TableShell>
                  <colgroup>
                    <col style={{ width: 3 }} />
                    <col style={{ width: 110 }} /><col style={{ width: 100 }} />
                    <col style={{ width: 70 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} />
                    <col style={{ width: 80 }} /><col style={{ width: 70 }} /><col style={{ width: 70 }} />
                    <col /><col style={{ width: 100 }} />
                  </colgroup>
                  <thead><tr>
                    <TH> </TH>
                    <TH>LB#</TH><TH>Source</TH>
                    <TH align="right">Given</TH><TH align="right">Matched</TH><TH align="right">Not found</TH>
                    <TH align="right">Missing</TH><TH align="right">Dups</TH><TH align="right">Xrefs</TH>
                    <TH>Status</TH><TH align="right"> </TH>
                  </tr></thead>
                  <tbody>
                    {SUMMARY.filter(r => filter === "all" || r.state === filter).map((r, i) => {
                      const t = STATE_TONE[r.state];
                      return (
                        <TR key={i} edge={t.tone} selected={r.lb === "—"}>
                          <TD mono style={{ color: r.lb === "—" ? "var(--lbb-fg3)" : "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
                          <TD mono dim style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <Icon name={SRC_ICON[r.src]} size={10} /> {r.src}
                          </TD>
                          <TD align="right" mono>{r.given}</TD>
                          <TD align="right" mono style={{ color: r.matched > 0 ? "var(--lbb-ok-fg)" : "var(--lbb-fg3)" }}>{r.matched || "—"}</TD>
                          <TD align="right" mono style={{ color: r.notFound > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)" }}>{r.notFound || "—"}</TD>
                          <TD align="right" mono style={{ color: r.missing > 0 ? "var(--lbb-warn-fg)" : "var(--lbb-fg3)" }}>{r.missing || "—"}</TD>
                          <TD align="right" mono style={{ color: r.dups > 0 ? "#a08200" : "var(--lbb-fg3)" }}>{r.dups || "—"}</TD>
                          <TD align="right" mono style={{ color: r.xrefs > 0 ? "var(--lbb-info-fg)" : "var(--lbb-fg3)" }}>{r.xrefs || "—"}</TD>
                          <TD><Pill tone={t.tone} soft dot={r.state !== "matched"}>{t.label}</Pill></TD>
                          <TD align="right">
                            <Button size="sm" variant="ghost" icon="reveal">Open</Button>
                          </TD>
                        </TR>
                      );
                    })}
                  </tbody>
                </TableShell>
              </div>

              {/* Active source label */}
              <div style={{ padding: "20px 24px 6px", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
                  Checksum detail
                </span>
                <span style={{ fontSize: 11.5, color: "var(--lbb-fg2)", fontFamily: "var(--lbb-mono)" }}>
                  bd2025-07-26 Charlotte NC · 36 checksums · not found in master DB
                </span>
                <div style={{ flex: 1 }} />
                <Button variant="secondary" size="sm" icon="plus">Mark as new entry…</Button>
              </div>
              <div style={{ padding: "0 24px 24px" }}>
                <TableShell>
                  <colgroup>
                    <col style={{ width: 3 }} />
                    <col style={{ width: 170 }} /><col />
                    <col style={{ width: 50 }} /><col style={{ width: 100 }} />
                    <col style={{ width: 60 }} /><col style={{ width: 110 }} /><col style={{ width: 80 }} />
                  </colgroup>
                  <thead><tr>
                    <TH> </TH>
                    <TH>Checksum</TH><TH>Filename</TH>
                    <TH align="center">Type</TH><TH>LB#</TH>
                    <TH align="center">Xref</TH><TH>Status</TH><TH>Source</TH>
                  </tr></thead>
                  <tbody>
                    {DETAIL.map((r, i) => {
                      const t = STATE_TONE[r.st];
                      return (
                        <TR key={i} edge={t.tone}>
                          <TD mono dim>{r.sum.slice(0, 12)}…</TD>
                          <TD mono style={{ color: "var(--lbb-fg)" }}>{r.fn}</TD>
                          <TD align="center" mono style={{ color: "var(--lbb-fg3)" }}>{r.type}</TD>
                          <TD mono style={{ color: r.lb !== "—" ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontWeight: r.lb !== "—" ? 600 : 400 }}>{r.lb}</TD>
                          <TD align="center">{r.xref ? <Icon name="check" size={11} style={{ color: "var(--lbb-info-fg)" }} /> : <span style={{ color: "var(--lbb-fg3)" }}>—</span>}</TD>
                          <TD><Pill tone={t.tone} soft>{t.label}</Pill></TD>
                          <TD mono dim style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <Icon name={SRC_ICON[r.src]} size={10} /> {r.src}
                          </TD>
                        </TR>
                      );
                    })}
                  </tbody>
                </TableShell>

                {/* Help banner */}
                <div style={{
                  marginTop: 14, padding: "10px 14px", borderRadius: 6,
                  background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)",
                  fontSize: 11.5, color: "var(--lbb-fg2)",
                  display: "flex", alignItems: "flex-start", gap: 10,
                }}>
                  <Icon name="info" size={14} style={{ color: "var(--lbb-info-fg)", marginTop: 1 }} />
                  <span><strong style={{ color: "var(--lbb-info-fg)" }}>Not found?</strong> Either this is a new entry the master DB doesn't know about yet, or the checksums in your folder don't match what's on file. If you're confident it's new, click <em>Mark as new entry…</em> — that drops it into the Curator queue for review.</span>
                </div>
              </div>
            </div>

            {/* Footer action */}
            <div style={{
              padding: "10px 24px", borderTop: "1px solid var(--lbb-border)",
              display: "flex", alignItems: "center", gap: 8, background: "var(--lbb-surface)",
            }}>
              <span style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>Results auto-populate the <strong style={{ color: "var(--lbb-fg2)" }}>Rename</strong> tab</span>
              <div style={{ flex: 1 }} />
              <Button variant="ghost" size="sm">Re-lookup all</Button>
              <Button variant="secondary" size="sm" icon="rename">Go to Rename →</Button>
              <Button variant="primary" size="sm" icon="check" disabled={counts.notfound > 0}>Confirm matches</Button>
            </div>
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenLookup = ScreenLookup;
})();
