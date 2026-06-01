// screen-lbdir.jsx
// LBDIR · Reconcile folders against the official lbdir*.txt sidecar from the
// LosslessBob archive. Four sub-flows:
//   • Check     — verify lbdir vs disk (per-file MD5/FFP/shntool)
//   • Retrieve  — copy lbdir from data/attachments cache (scrape if needed)
//   • Reconcile — find moved/misnamed files and propose disk renames
//   • Extras    — list files not referenced in lbdir + delete UI

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD } = window;

  // ── Sample queue + per-folder data ──
  const QUEUE = [
    { p: "/mnt/HOPPER/1982-06-06 PASADENA, CA (LB-08621)",  lb: "LB-8621",   file: "LBF-08621-lbdir-md5.txt",      state: "pass",          mode: "flac", total: 70,  pass: 70, miss: 0,  mism: 0 },
    { p: "/mnt/HOPPER/1983-02-16 Lone Star Cafe",           lb: "LB-13680",  file: "LBF-13680-lbdir.txt",          state: "pass",          mode: "flac", total: 15,  pass: 15, miss: 0,  mism: 0 },
    { p: "/mnt/HOPPER/1982-06-06 Peace Sunday Rally",       lb: "LB-810",    file: "LBF-00810-lbdir-shnf.txt",     state: "missing_files", mode: "shn",  total: 18,  pass: 15, miss: 3,  mism: 0 },
    { p: "/mnt/HOPPER/1983-xx-xx First Infidels",           lb: "LB-1964",   file: "LBF-01964-lbdir.txt",          state: "fail",          mode: "flac", total: 9,   pass: 0,  miss: 9,  mism: 0 },
    { p: "/mnt/HOPPER/bd2025-07-26 Charlotte NC",           lb: null,        file: null,                            state: "no_lb",         mode: "flac", total: 0,   pass: 0,  miss: 0,  mism: 0 },
    { p: "/mnt/HOPPER/bd2026.03.30 Waukegan IL",            lb: "LB-16590",  file: null,                            state: "no_lbdir",      mode: "flac", total: 0,   pass: 0,  miss: 0,  mism: 0 },
  ];

  // Per-file detail (active = Peace Sunday Rally — 3 missing)
  const DETAIL_CHECK = [
    { n: "d01t01.shn", mdE: "8c1d2f8a9c…", mdA: "8c1d2f8a9c…", md: "pass", shE: "67a44b…",   shA: "67a44b…",   sh: "pass", disk: true,  ok: "pass",
      len: "4:42.20", expand: "49.7 MB",   cdr: true,  wave: "—",            fmt: "SHN", ratio: "0.62" },
    { n: "d01t02.shn", mdE: "5e9f0a3b21…", mdA: "5e9f0a3b21…", md: "pass", shE: "a8b932…",   shA: "a8b932…",   sh: "pass", disk: true,  ok: "pass",
      len: "3:18.04", expand: "34.9 MB",   cdr: true,  wave: "—",            fmt: "SHN", ratio: "0.61" },
    { n: "d01t03.shn", mdE: "7d22cc0817…", mdA: "—",           md: "miss", shE: "3290fe…",   shA: "—",         sh: "miss", disk: false, ok: "miss",
      len: "",        expand: "",          cdr: null,  wave: "missing",      fmt: "",    ratio: "" },
    { n: "d01t04.shn", mdE: "9f12cc88e0…", mdA: "—",           md: "miss", shE: "b1aa99…",   shA: "—",         sh: "miss", disk: false, ok: "miss",
      len: "",        expand: "",          cdr: null,  wave: "missing",      fmt: "",    ratio: "" },
    { n: "d02t01.shn", mdE: "11ff44aa9b…", mdA: "—",           md: "miss", shE: "ee9001…",   shA: "—",         sh: "miss", disk: false, ok: "miss",
      len: "",        expand: "",          cdr: null,  wave: "missing",      fmt: "",    ratio: "" },
    { n: "notes.txt",  mdE: "aabb88112d…", mdA: "aabb88112d…", md: "pass", shE: "—",         shA: "—",         sh: "na",   disk: true,  ok: "pass",
      len: "",        expand: "1.4 KB",    cdr: null,  wave: "—",            fmt: "TXT", ratio: "" },
  ];

  // Reconcile proposals
  const RECON = [
    { from: "extras/d01t03.flac.shn",                 to: "d01t03.shn",         md5: "7d22cc0817…" },
    { from: "_unsorted/track4.shn",                   to: "d01t04.shn",         md5: "9f12cc88e0…" },
    { from: "renamed badly/d02 - track 1.shn",        to: "d02t01.shn",         md5: "11ff44aa9b…" },
  ];

  // Extras (files in folder not in lbdir)
  const EXTRAS = [
    { p: "notes-personal.txt",    sz: "2.1 KB",    sel: true  },
    { p: ".DS_Store",             sz: "8 KB",      sel: true  },
    { p: "Thumbs.db",             sz: "12 KB",    sel: true  },
    { p: "extras/album-art.png",  sz: "1.2 MB",   sel: false },
    { p: "extras/cover-back.jpg", sz: "780 KB",   sel: false },
  ];

  // Retrieve queue results
  const RETRIEVE = [
    { folder: "1982-06-06 PASADENA, CA",   lb: "LB-8621",  result: "copied",       msg: "Found in cache · copied to folder" },
    { folder: "1982-06-06 Peace Sunday",   lb: "LB-810",   result: "copied",       msg: "Found in cache · copied to folder" },
    { folder: "1983-xx-xx First Infidels", lb: "LB-1964",  result: "scraped",      msg: "Not cached · scraped + copied" },
    { folder: "bd2025-07-26 Charlotte",    lb: null,       result: "no_lb",        msg: "No LB# known · run Lookup first" },
    { folder: "bd2026.03.30 Waukegan",     lb: "LB-16590", result: "not_found",    msg: "No lbdir on LB.com for this entry" },
  ];

  const STATE_LABEL = {
    pass:           { tone: "ok",   label: "Pass" },
    fail:           { tone: "bad",  label: "Fail · mismatches" },
    missing_files:  { tone: "bad",  label: "Missing files" },
    no_lbdir:       { tone: "warn", label: "No lbdir · retrievable" },
    no_lb:          { tone: "mute", label: "No LB#" },
  };

  function FolderRow({ row, active, onClick }) {
    const s = STATE_LABEL[row.state] || STATE_LABEL.no_lbdir;
    const color = s.tone === "ok" ? "var(--lbb-ok-bar)" : s.tone === "bad" ? "var(--lbb-bad-bar)" : s.tone === "warn" ? "var(--lbb-warn-bar)" : "var(--lbb-fg3)";
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "7px 10px", marginBottom: 1, borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid " + (active ? "var(--lbb-accent-line)" : "transparent"),
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flex: "0 0 8px" }} />
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.p.split("/").pop()}</span>
          <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>
            {row.lb ? <span style={{ color: "var(--lbb-accent-mid)" }}>{row.lb}</span> : <span style={{ color: "var(--lbb-fg3)" }}>—</span>}
            {row.total > 0 && <> · {row.pass}/{row.total} pass</>}
            {row.miss > 0 && <> · <span style={{ color: "var(--lbb-bad-fg)" }}>{row.miss} miss</span></>}
          </span>
        </span>
      </button>
    );
  }

  // ── Sub-flow panes ─────────────────────────────────────────────────
  function CheckPane({ row, detail }) {
    return (
      <>
        <div style={{ padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 13, fontWeight: 600 }}>{row.p.split("/").pop()}</span>
            {row.lb && <Pill tone="info" soft style={{ fontFamily: "var(--lbb-mono)" }}>{row.lb}</Pill>}
            {row.file && <Pill tone="mute" soft style={{ fontFamily: "var(--lbb-mono)" }}>{row.file}</Pill>}
            <Pill tone="mute" soft>{row.mode.toUpperCase()}</Pill>
            <Pill tone={STATE_LABEL[row.state].tone} soft dot={row.state !== "pass"}>{STATE_LABEL[row.state].label}</Pill>
            <div style={{ flex: 1 }} />
            <Button variant="secondary" size="sm" icon="reveal">Open lbdir.txt</Button>
            <Button variant="primary" size="sm" icon="lbdir">Re-check this folder</Button>
          </div>
          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
            {[
              { l: "Total",    v: row.total },
              { l: "Pass",     v: row.pass, c: row.pass > 0 ? "var(--lbb-ok-fg)" : "var(--lbb-fg3)" },
              { l: "Mismatch", v: row.mism, c: row.mism > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)" },
              { l: "Missing",  v: row.miss, c: row.miss > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)" },
              { l: "Extras",   v: 5 }, // computed from EXTRAS for demo
            ].map((s, i) => (
              <div key={i} style={{ padding: "6px 10px", borderRadius: 6, background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)" }}>
                <div style={{ fontSize: 9.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>{s.l}</div>
                <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "var(--lbb-mono)", fontVariantNumeric: "tabular-nums", color: s.c || "var(--lbb-fg)" }}>{s.v}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 280px", minHeight: 0 }}>
          {/* Detail table */}
          <div style={{ overflow: "auto", padding: "16px 16px 16px 24px" }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} />
                <col />
                <col style={{ width: 108 }} /><col style={{ width: 108 }} /><col style={{ width: 50 }} />
                <col style={{ width: 88 }} /><col style={{ width: 88 }} /><col style={{ width: 50 }} />
                <col style={{ width: 50 }} /><col style={{ width: 70 }} />
              </colgroup>
              <thead><tr>
                <TH> </TH><TH>Filename</TH>
                <TH align="right">MD5 expected</TH><TH align="right">MD5 actual</TH><TH align="center">MD5</TH>
                <TH align="right">Shn exp.</TH><TH align="right">Shn act.</TH><TH align="center">Shn</TH>
                <TH align="center">Disk</TH><TH>Overall</TH>
              </tr></thead>
              <tbody>
                {detail.map((f, i) => {
                  const edge = f.ok === "pass" ? "ok" : f.ok === "miss" ? "warn" : "bad";
                  return (
                    <TR key={i} edge={edge}>
                      <TD mono style={{ color: f.ok === "pass" ? "var(--lbb-fg)" : "var(--lbb-bad-fg)" }}>{f.n}</TD>
                      <TD align="right" mono dim>{f.mdE}</TD>
                      <TD align="right" mono style={{ color: f.md === "pass" ? "var(--lbb-fg2)" : "var(--lbb-fg3)" }}>{f.mdA}</TD>
                      <TD align="center">{f.md === "pass" ? <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} /> : f.md === "miss" ? <Icon name="x" size={12} style={{ color: "var(--lbb-warn-fg)" }} /> : <span style={{ color: "var(--lbb-fg3)" }}>na</span>}</TD>
                      <TD align="right" mono dim>{f.shE}</TD>
                      <TD align="right" mono style={{ color: f.sh === "pass" ? "var(--lbb-fg2)" : "var(--lbb-fg3)" }}>{f.shA}</TD>
                      <TD align="center">{f.sh === "pass" ? <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} /> : f.sh === "miss" ? <Icon name="x" size={12} style={{ color: "var(--lbb-warn-fg)" }} /> : <span style={{ color: "var(--lbb-fg3)" }}>na</span>}</TD>
                      <TD align="center">{f.disk ? <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} /> : <Icon name="x" size={12} style={{ color: "var(--lbb-warn-fg)" }} />}</TD>
                      <TD><Pill tone={edge} soft>{f.ok === "pass" ? "Pass" : "Missing"}</Pill></TD>
                    </TR>
                  );
                })}
              </tbody>
            </TableShell>
          </div>

          {/* Side info panel — shntool_len for selected row */}
          <aside style={{
            background: "var(--lbb-surface)", borderLeft: "1px solid var(--lbb-border)",
            padding: 16, overflowY: "auto",
          }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>
              Shntool · d01t01.shn
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "5px 14px", fontSize: 12 }}>
              {[
                ["Length",         "4:42.20"],
                ["Expanded",       "49.7 MB"],
                ["CDR",            "✓ valid"],
                ["WAVE problems",  "—"],
                ["Format",         "SHN seekable"],
                ["Compression",    "0.62"],
                ["MD5 (audio)",    "8c1d2f8a9c…"],
              ].map(([k, v], i) => (
                <React.Fragment key={i}>
                  <span style={{ color: "var(--lbb-fg3)" }}>{k}</span>
                  <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>{v}</span>
                </React.Fragment>
              ))}
            </div>

            <div style={{
              marginTop: 18, padding: "10px 12px",
              background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)", borderRadius: 6,
              fontSize: 11, color: "var(--lbb-fg2)",
            }}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <Icon name="info" size={12} style={{ color: "var(--lbb-info-fg)", marginTop: 2 }} />
                <div>This folder is missing 3 files referenced in <span style={{ fontFamily: "var(--lbb-mono)" }}>{row.file}</span>. Switch to <strong>Reconcile</strong> to see if they're on disk under different names.</div>
              </div>
            </div>
          </aside>
        </div>
      </>
    );
  }

  function RetrievePane() {
    return (
      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
            Retrieve lbdir from cache
          </span>
          <Pill tone="ok" soft>3 copied</Pill>
          <Pill tone="warn" soft>1 scraped</Pill>
          <Pill tone="bad" soft>1 not found</Pill>
          <Pill tone="mute" soft>1 no LB#</Pill>
        </div>
        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} /><col /><col style={{ width: 100 }} />
            <col style={{ width: 140 }} /><col /><col style={{ width: 100 }} />
          </colgroup>
          <thead><tr>
            <TH> </TH><TH>Folder</TH><TH>LB#</TH><TH>Result</TH><TH>Message</TH><TH align="right"> </TH>
          </tr></thead>
          <tbody>
            {RETRIEVE.map((r, i) => {
              const tone = r.result === "copied" || r.result === "scraped" ? "ok" : r.result === "not_found" ? "bad" : r.result === "no_lb" ? "mute" : "warn";
              const label = r.result === "copied" ? "Copied" : r.result === "scraped" ? "Scraped + copied" : r.result === "not_found" ? "Not on LB.com" : "No LB# known";
              return (
                <TR key={i} edge={tone}>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>{r.folder}</TD>
                  <TD mono style={{ color: r.lb ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontWeight: 600 }}>{r.lb || "—"}</TD>
                  <TD><Pill tone={tone} soft dot={tone !== "ok"}>{label}</Pill></TD>
                  <TD style={{ color: "var(--lbb-fg2)", fontSize: 11.5 }}>{r.msg}</TD>
                  <TD align="right">
                    {r.result === "no_lb" ? <Button size="sm" variant="secondary" icon="lookup">Run Lookup</Button> :
                     r.result === "not_found" ? <Button size="sm" variant="ghost" icon="reveal">LB.com</Button> :
                     <Button size="sm" variant="ghost" icon="reveal">Open</Button>}
                  </TD>
                </TR>
              );
            })}
          </tbody>
        </TableShell>

        <div style={{
          marginTop: 16, padding: "10px 14px", borderRadius: 6,
          background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)",
          fontSize: 11.5, color: "var(--lbb-fg2)", display: "flex", alignItems: "flex-start", gap: 10,
        }}>
          <Icon name="info" size={13} style={{ color: "var(--lbb-info-fg)", marginTop: 1 }} />
          <div>Cached <span style={{ fontFamily: "var(--lbb-mono)" }}>lbdir*.txt</span> files live in <span style={{ fontFamily: "var(--lbb-mono)" }}>data/attachments/LB-XXXXX/</span>. Retrieve copies the file to the audio folder. If no cache hit, the Scraper auto-fetches from LB.com.</div>
        </div>
      </div>
    );
  }

  function ReconcilePane() {
    return (
      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
            Reconcile · find moved files
          </span>
          <Pill tone="info" soft>3 proposals · 0 unmatched</Pill>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm">Re-scan disk</Button>
          <Button variant="primary" size="sm" icon="check">Apply 3 renames</Button>
        </div>

        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} /><col style={{ width: 32 }} />
            <col /><col style={{ width: 24 }} /><col /><col style={{ width: 140 }} />
          </colgroup>
          <thead><tr>
            <TH> </TH><TH><input type="checkbox" /></TH>
            <TH>Disk file (current path)</TH><TH> </TH><TH>Will move to</TH><TH>MD5 match</TH>
          </tr></thead>
          <tbody>
            {RECON.map((r, i) => (
              <TR key={i} edge="info">
                <TD><input type="checkbox" defaultChecked /></TD>
                <TD mono style={{ color: "var(--lbb-fg2)" }}>{r.from}</TD>
                <TD align="center"><Icon name="chevRight" size={12} style={{ color: "var(--lbb-fg3)" }} /></TD>
                <TD mono style={{ color: "var(--lbb-ok-fg)" }}>{r.to}</TD>
                <TD mono dim>{r.md5}</TD>
              </TR>
            ))}
          </tbody>
        </TableShell>

        <div style={{
          marginTop: 16, padding: "12px 16px", borderRadius: 6,
          background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)",
          fontSize: 12, color: "var(--lbb-fg2)", display: "flex", alignItems: "flex-start", gap: 10,
        }}>
          <Icon name="info" size={14} style={{ color: "var(--lbb-info-fg)", marginTop: 1 }} />
          <div>
            <strong style={{ color: "var(--lbb-info-fg)" }}>How reconcile works.</strong>
            <br />
            For each missing file in <span style={{ fontFamily: "var(--lbb-mono)" }}>lbdir*.txt</span>, we MD5 every file in the folder tree and propose moves where the disk MD5 matches the lbdir MD5. <strong>Files are moved, never deleted or copied.</strong> Subdirectories are created as needed. Empty source dirs stay put (use Extras to clean up).
          </div>
        </div>
      </div>
    );
  }

  function ExtrasPane() {
    const selected = EXTRAS.filter(e => e.sel).length;
    const totalSize = "10.2 KB"; // demo
    return (
      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
            Extra files · not in lbdir
          </span>
          <Pill tone="warn" soft>{EXTRAS.length} files</Pill>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm">Select system files only</Button>
          <Button variant="danger" size="sm" icon="trash" disabled={selected === 0}>Delete {selected} ({totalSize})</Button>
        </div>

        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} /><col style={{ width: 32 }} />
            <col /><col style={{ width: 90 }} /><col style={{ width: 110 }} />
          </colgroup>
          <thead><tr>
            <TH> </TH><TH><input type="checkbox" /></TH>
            <TH>Path</TH><TH align="right">Size</TH><TH>Hint</TH>
          </tr></thead>
          <tbody>
            {EXTRAS.map((e, i) => {
              const isSystem = e.p === ".DS_Store" || e.p === "Thumbs.db";
              return (
                <TR key={i} edge={e.sel ? "warn" : null}>
                  <TD><input type="checkbox" defaultChecked={e.sel} /></TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>{e.p}</TD>
                  <TD align="right" mono dim>{e.sz}</TD>
                  <TD>{isSystem ? <Pill tone="mute" soft>System</Pill> : <Pill tone="info" soft>User file</Pill>}</TD>
                </TR>
              );
            })}
          </tbody>
        </TableShell>

        <div style={{
          marginTop: 16, padding: "12px 16px", borderRadius: 6,
          background: "var(--lbb-bad-bg)", border: "1px solid var(--lbb-bad-fg)",
          fontSize: 12, color: "var(--lbb-fg2)", display: "flex", alignItems: "flex-start", gap: 10,
        }}>
          <Icon name="info" size={14} style={{ color: "var(--lbb-bad-fg)", marginTop: 1 }} />
          <div>
            <strong style={{ color: "var(--lbb-bad-fg)" }}>Permanent deletion.</strong>
            &nbsp;Selected files will be removed from disk, not moved to the trash. Empty subdirectories are pruned automatically. Review carefully before confirming.
          </div>
        </div>
      </div>
    );
  }

  // ── Screen ─────────────────────────────────────────────────────────
  function ScreenLBDIR() {
    const [tab, setTab]           = React.useState("check");
    const [activeIdx, setActiveIdx] = React.useState(2); // Peace Sunday (missing files)
    const row = QUEUE[activeIdx];

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Header */}
        <div style={{
          padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="lbdir" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>LBDIR</h1>
              <Pill tone="mute" soft>official sidecar reconciliation</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              Check, retrieve, and reconcile the <span style={{ fontFamily: "var(--lbb-mono)" }}>lbdir*.txt</span> file from the LosslessBob archive.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 14, padding: "0 12px", borderRight: "1px solid var(--lbb-border)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--lbb-fg2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-warn-bar)" }} /> shntool
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--lbb-fg2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} /> attachments cache
            </span>
          </div>
          <Button variant="ghost" size="sm" icon="folderPlus">Add folders…</Button>
        </div>

        {/* Sub-flow tabs */}
        <div style={{
          padding: "0 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "stretch", gap: 0, background: "var(--lbb-surface)",
        }}>
          {[
            { k: "check",     l: "Check",     icon: "verify",  hint: "verify lbdir vs disk" },
            { k: "retrieve",  l: "Retrieve",  icon: "download", hint: "copy lbdir from cache" },
            { k: "reconcile", l: "Reconcile", icon: "rename",  hint: "find moved files" },
            { k: "extras",    l: "Extras",    icon: "trash",   hint: "files not in lbdir" },
          ].map(t => (
            <button key={t.k} onClick={() => setTab(t.k)}
              style={{
                padding: "10px 16px 12px", borderBottom: `2px solid ${tab === t.k ? "var(--lbb-accent-mid)" : "transparent"}`,
                background: "transparent", border: "none", borderBottom: `2px solid ${tab === t.k ? "var(--lbb-accent-mid)" : "transparent"}`,
                color: tab === t.k ? "var(--lbb-fg)" : "var(--lbb-fg2)",
                fontFamily: "inherit", fontSize: 12.5, fontWeight: tab === t.k ? 600 : 500,
                cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
              }}>
              <Icon name={t.icon} size={13} />
              {t.l}
              <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontWeight: 500 }}>{t.hint}</span>
            </button>
          ))}
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Queue rail (always visible) */}
          <aside style={{
            width: 280, flex: "0 0 280px",
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <Icon name="folder" size={13} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.1, textTransform: "uppercase" }}>Folders</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{QUEUE.length}</span>
              </div>
              <Input icon="search" placeholder="Filter…" size="sm" style={{ width: "100%" }} />
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {QUEUE.map((r, i) => <FolderRow key={i} row={r} active={i === activeIdx} onClick={() => setActiveIdx(i)} />)}
            </div>
            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="lbdir" block>Check all folders</Button>
              <Button variant="secondary" size="sm" icon="download" block>Retrieve missing lbdir</Button>
              <Button variant="ghost" size="sm" icon="folderPlus" block>Add root folder…</Button>
            </div>
          </aside>

          {/* Active sub-flow */}
          <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            {tab === "check"     && <CheckPane row={row} detail={DETAIL_CHECK} />}
            {tab === "retrieve"  && <RetrievePane />}
            {tab === "reconcile" && <ReconcilePane />}
            {tab === "extras"    && <ExtrasPane />}
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenLBDIR = ScreenLBDIR;
})();
