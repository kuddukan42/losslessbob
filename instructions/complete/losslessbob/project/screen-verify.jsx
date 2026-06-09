// screen-verify.jsx
// Verify · Audio files vs locally-generated checksums (.ffp / .md5 / .st5)
// Distinct from LBDIR — this verifies user-generated checksums; LBDIR verifies
// the official archive sidecar.
//
// Wraps backend /api/verify and /api/verify/generate.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD, GroupRow } = window;

  // ── Sample data — matches backend verify_folder schema ─────────────
  const QUEUE = [
    { p: "/mnt/HOPPER/bd2025-07-25 Alpharetta GA FLAC",     mode: "flac",  state: "fail",        total: 32, pass: 16, miss: 16, mism: 0, extra: 0 },
    { p: "/mnt/HOPPER/bd2025-07-26 Charlotte NC FLAC",      mode: "flac",  state: "mismatch",    total: 18, pass: 17, miss: 0,  mism: 1, extra: 0 },
    { p: "/mnt/HOPPER/bd2025-09-18 Noblesville IN FLAC",    mode: "flac",  state: "pass",        total: 14, pass: 14, miss: 0,  mism: 0, extra: 0 },
    { p: "/mnt/HOPPER/bd2026-03-27 La Crosse WI",           mode: "flac",  state: "pass",        total: 22, pass: 22, miss: 0,  mism: 0, extra: 1 },
    { p: "/mnt/HOPPER/bd2026.03.30 Waukegan IL",            mode: "flac",  state: "incomplete",  total: 16, pass: 16, miss: 0,  mism: 0, extra: 0, missingTypes: ["ffp"] },
    { p: "/mnt/HOPPER/bd2026-04-02 Madison WI",             mode: "mixed", state: "shntool",     total: 18, pass: 0,  miss: 0,  mism: 0, extra: 0 },
    { p: "/mnt/HOPPER/bd2026-04-12 Detroit MI",             mode: "shn",   state: "pass",        total: 11, pass: 11, miss: 0,  mism: 0, extra: 0 },
  ];

  // Per-file detail (active = Alpharetta) — mismatched + missing rows
  const FILES = [
    { n: "d01t01.flac",  md5: "pass", ffp: "pass", st5: "na",  disk: true,  ok: "pass",  mdE: "8c1d2f8a9c", mdA: "8c1d2f8a9c", ffE: "4f8a9c211e", ffA: "4f8a9c211e" },
    { n: "d01t02.flac",  md5: "pass", ffp: "pass", st5: "na",  disk: true,  ok: "pass",  mdE: "5e9f0a3b21", mdA: "5e9f0a3b21", ffE: "a821bb4cde", ffA: "a821bb4cde" },
    { n: "d01t03.flac",  md5: "pass", ffp: "pass", st5: "na",  disk: true,  ok: "pass",  mdE: "7d22cc0817", mdA: "7d22cc0817", ffE: "3290fe1d44", ffA: "3290fe1d44" },
    { n: "d02t01.flac",  md5: "miss", ffp: "miss", st5: "na",  disk: false, ok: "miss",  mdE: "9f12cc88e0", mdA: "—",          ffE: "b1aa991dd0", ffA: "—" },
    { n: "d02t02.flac",  md5: "miss", ffp: "miss", st5: "na",  disk: false, ok: "miss",  mdE: "10ff44aa9b", mdA: "—",          ffE: "ee9001cf22", ffA: "—" },
    { n: "d02t03.flac",  md5: "fail", ffp: "pass", st5: "na",  disk: true,  ok: "fail",  mdE: "aabb88112d", mdA: "11aa882dcc", ffE: "660ff19911", ffA: "660ff19911" },
  ];

  // ── visual atoms ──
  function StatusDot({ s }) {
    if (s === "pass") return <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />;
    if (s === "fail") return <Icon name="x" size={13} style={{ color: "var(--lbb-bad-fg)" }} />;
    if (s === "miss") return <Icon name="x" size={13} style={{ color: "var(--lbb-warn-fg)" }} />;
    return <span style={{ color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)", fontSize: 10 }}>na</span>;
  }

  function ToolDot({ status, label }) {
    const c = status === "ok" ? "var(--lbb-ok-bar)" : status === "warn" ? "var(--lbb-warn-bar)" : "var(--lbb-bad-fg)";
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--lbb-fg2)" }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: c }} />
        {label}
      </span>
    );
  }

  function FolderRow({ row, active, onClick }) {
    const tone = row.state === "pass" ? "ok" : row.state === "mismatch" || row.state === "fail" ? "bad" : "warn";
    const dotColor = tone === "ok" ? "var(--lbb-ok-bar)" : tone === "bad" ? "var(--lbb-bad-bar)" : "var(--lbb-warn-bar)";
    const name = row.p.split("/").pop();
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "7px 10px", marginBottom: 1, borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid " + (active ? "var(--lbb-accent-line)" : "transparent"),
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: dotColor, flex: "0 0 8px" }} />
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
          <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>
            {row.mode.toUpperCase()} · {row.pass}/{row.total} pass
            {row.miss > 0 && <> · <span style={{ color: "var(--lbb-warn-fg)" }}>{row.miss} miss</span></>}
            {row.mism > 0 && <> · <span style={{ color: "var(--lbb-bad-fg)" }}>{row.mism} mismatch</span></>}
          </span>
        </span>
      </button>
    );
  }

  function StateBadge({ s }) {
    if (s === "pass")        return <Pill tone="ok" soft>Pass</Pill>;
    if (s === "mismatch")    return <Pill tone="bad" soft dot>Mismatch</Pill>;
    if (s === "fail")        return <Pill tone="bad" soft dot>Fail · missing files</Pill>;
    if (s === "incomplete")  return <Pill tone="warn" soft>Incomplete</Pill>;
    if (s === "shntool")     return <Pill tone="warn" soft dot>shntool missing</Pill>;
    return <Pill tone="mute" soft>—</Pill>;
  }

  function ScreenVerify() {
    const [activeIdx, setActiveIdx] = React.useState(0);
    const [showAll, setShowAll]     = React.useState(false);
    const row = QUEUE[activeIdx];

    const visible = showAll ? FILES : FILES.filter(f => f.ok !== "pass");
    const tone = row.state === "pass" ? "ok" : row.state === "incomplete" || row.state === "shntool" ? "warn" : "bad";

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
          }}><Icon name="verify" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Verify</h1>
              <Pill tone="mute" soft>local checksums · _mychecksums</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              FFP · MD5 · ST5 against audio on disk. Use <strong>LBDIR</strong> for the official archive sidecar.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 14, padding: "0 12px", borderRight: "1px solid var(--lbb-border)" }}>
            <ToolDot status="ok"   label="FFP" />
            <ToolDot status="ok"   label="MD5" />
            <ToolDot status="warn" label="shntool" />
          </div>
          <Button variant="ghost" size="sm" icon="folderPlus">Add folders…</Button>
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Queue rail */}
          <aside style={{
            width: 300, flex: "0 0 300px",
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <Icon name="folder" size={13} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.1, textTransform: "uppercase" }}>Folders</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{QUEUE.length}</span>
              </div>
              <Input icon="search" placeholder="Filter folders…" size="sm" style={{ width: "100%" }} />
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {QUEUE.map((r, i) => <FolderRow key={i} row={r} active={i === activeIdx} onClick={() => setActiveIdx(i)} />)}
            </div>
            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="verify" block>Verify all folders</Button>
              <Button variant="secondary" size="sm" icon="plus" block>Generate checksums</Button>
              <Button variant="ghost" size="sm" icon="download" block>Retrieve from LB</Button>
              <Button variant="ghost" size="sm" icon="folderPlus" block>Add root folder…</Button>
            </div>
          </aside>

          {/* Main pane */}
          <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            {/* Folder summary card */}
            <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <Icon name="folder" size={14} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 13, fontWeight: 600, color: "var(--lbb-fg)" }}>{row.p.split("/").pop()}</span>
                <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg3)" }}>{row.p}</span>
                <div style={{ flex: 1 }} />
                <StateBadge s={row.state} />
                <Pill tone="mute" soft>{row.mode.toUpperCase()}</Pill>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 8 }}>
                {[
                  { l: "Total",     v: row.total, color: "var(--lbb-fg)" },
                  { l: "Pass",      v: row.pass,  color: row.pass === row.total ? "var(--lbb-ok-fg)" : "var(--lbb-fg)" },
                  { l: "Mismatch",  v: row.mism,  color: row.mism > 0 ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)" },
                  { l: "Missing",   v: row.miss,  color: row.miss > 0 ? "var(--lbb-warn-fg)" : "var(--lbb-fg3)" },
                  { l: "Extra",     v: row.extra, color: row.extra > 0 ? "var(--lbb-info-fg)" : "var(--lbb-fg3)" },
                  { l: "FFP",       v: row.missingTypes?.includes("ffp") ? "—" : "✓", color: row.missingTypes?.includes("ffp") ? "var(--lbb-warn-fg)" : "var(--lbb-ok-fg)" },
                  { l: "MD5",       v: row.missingTypes?.includes("md5") ? "—" : "✓", color: row.missingTypes?.includes("md5") ? "var(--lbb-warn-fg)" : "var(--lbb-ok-fg)" },
                ].map((s, i) => (
                  <div key={i} style={{
                    padding: "8px 12px", borderRadius: 6,
                    background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
                  }}>
                    <div style={{ fontSize: 9.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>{s.l}</div>
                    <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--lbb-mono)", fontVariantNumeric: "tabular-nums", color: s.color, marginTop: 2 }}>{s.v}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Toolbar */}
            <div style={{ padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Files</span>
              <Chip active={!showAll} onClick={() => setShowAll(false)} size="sm" count={FILES.filter(f => f.ok !== "pass").length}>Problems</Chip>
              <Chip active={showAll} onClick={() => setShowAll(true)} size="sm" count={FILES.length}>Show all</Chip>
              <div style={{ flex: 1 }} />
              <Button variant="ghost" size="sm" icon="reveal">Open in Finder</Button>
              <Button variant="ghost" size="sm" icon="copy">Copy report</Button>
              <Button variant="secondary" size="sm" icon="plus">Generate missing FFP</Button>
              <Button variant="primary" size="sm" icon="check" disabled={row.state !== "pass"}>Mark verified</Button>
            </div>

            {/* Detail table */}
            <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
              {row.state === "shntool" ? (
                <div style={{ padding: "32px 24px" }}>
                  <div style={{
                    padding: "16px 18px", borderRadius: 8,
                    background: "var(--lbb-warn-bg)", border: "1px solid var(--lbb-warn-bar)",
                    display: "flex", gap: 12, alignItems: "flex-start",
                  }}>
                    <Icon name="info" size={18} style={{ color: "var(--lbb-warn-fg)", flex: "0 0 18px", marginTop: 2 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--lbb-warn-fg)" }}>shntool is not installed</div>
                      <div style={{ fontSize: 12, color: "var(--lbb-fg2)", marginTop: 4 }}>
                        This folder contains SHN files. We can verify FFP/MD5 without shntool, but per-disc length checks and CDR validation require it.
                      </div>
                      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                        <Button variant="secondary" size="sm" icon="download">Install shntool…</Button>
                        <Button variant="ghost" size="sm">Verify without shntool</Button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ padding: "0 24px 24px" }}>
                  <TableShell>
                    <colgroup>
                      <col style={{ width: 3 }} />
                      <col />
                      <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
                      <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
                      <col style={{ width: 60 }} /><col style={{ width: 60 }} /><col style={{ width: 90 }} />
                    </colgroup>
                    <thead><tr>
                      <TH> </TH><TH>Filename</TH>
                      <TH align="right">MD5 expected</TH><TH align="right">MD5 actual</TH><TH align="center">MD5</TH>
                      <TH align="right">FFP expected</TH><TH align="right">FFP actual</TH><TH align="center">FFP</TH>
                      <TH align="center">ST5</TH><TH align="center">Disk</TH><TH>Overall</TH>
                    </tr></thead>
                    <tbody>
                      {visible.map((f, i) => {
                        const edge = f.ok === "pass" ? "ok" : f.ok === "miss" ? "warn" : "bad";
                        return (
                          <TR key={i} edge={edge}>
                            <TD mono style={{ color: f.ok === "pass" ? "var(--lbb-fg)" : f.ok === "miss" ? "var(--lbb-warn-fg)" : "var(--lbb-bad-fg)" }}>{f.n}</TD>
                            <TD align="right" mono dim>{f.mdE}</TD>
                            <TD align="right" mono style={{ color: f.md5 === "fail" ? "var(--lbb-bad-fg)" : f.md5 === "miss" ? "var(--lbb-fg3)" : "var(--lbb-fg2)" }}>{f.mdA}</TD>
                            <TD align="center"><StatusDot s={f.md5} /></TD>
                            <TD align="right" mono dim>{f.ffE}</TD>
                            <TD align="right" mono style={{ color: f.ffp === "fail" ? "var(--lbb-bad-fg)" : f.ffp === "miss" ? "var(--lbb-fg3)" : "var(--lbb-fg2)" }}>{f.ffA}</TD>
                            <TD align="center"><StatusDot s={f.ffp} /></TD>
                            <TD align="center"><StatusDot s={f.st5} /></TD>
                            <TD align="center">{f.disk
                              ? <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} />
                              : <Icon name="x" size={12} style={{ color: "var(--lbb-warn-fg)" }} />}</TD>
                            <TD><Pill tone={edge} soft>{f.ok === "pass" ? "Pass" : f.ok === "miss" ? "Missing" : "Fail"}</Pill></TD>
                          </TR>
                        );
                      })}
                    </tbody>
                  </TableShell>

                  {!showAll && (
                    <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--lbb-fg3)", fontStyle: "italic", textAlign: "center" }}>
                      Showing {visible.length} problem files · <button onClick={() => setShowAll(true)} style={{ background: "none", border: "none", color: "var(--lbb-accent-mid)", cursor: "pointer", textDecoration: "underline", fontStyle: "italic", padding: 0, font: "inherit" }}>show all {FILES.length}</button>
                    </div>
                  )}

                  {/* Per-file inspector */}
                  {row.state !== "pass" && (
                    <div style={{
                      marginTop: 18, padding: "14px 16px",
                      background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 8,
                    }}>
                      <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 10 }}>
                        Inspector · 16 of 32 files referenced in <span style={{ fontFamily: "var(--lbb-mono)" }}>LB-16401-ffp.txt</span>
                      </div>
                      <pre style={{
                        margin: 0, padding: 12, background: "var(--lbb-surface2)",
                        border: "1px solid var(--lbb-border)", borderRadius: 6,
                        fontFamily: "var(--lbb-mono)", fontSize: 11, lineHeight: 1.55,
                        color: "var(--lbb-fg2)", whiteSpace: "pre", overflowX: "auto",
                      }}>{`✓ d01t01.flac    [ffp] 4f8a9c211e…  [md5] 8c1d2f8a9c…   pass
✓ d01t02.flac    [ffp] a821bb4cde…  [md5] 5e9f0a3b21…   pass
✓ d01t03.flac    [ffp] 3290fe1d44…  [md5] 7d22cc0817…   pass
… 13 more pass …
✗ d02t01.flac    MISSING ON DISK — listed in ffp + md5
✗ d02t02.flac    MISSING ON DISK — listed in ffp + md5
✗ d02t03.flac    [md5] expected aabb88112d… got 11aa882dcc…   FAIL
… 14 more missing …`}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenVerify = ScreenVerify;
})();
