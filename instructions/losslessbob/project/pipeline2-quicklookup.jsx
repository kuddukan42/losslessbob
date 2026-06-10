// pipeline2-quicklookup.jsx
// The home for Lookup's NON-folder sources — paste a listbox, pull from the
// clipboard, or drop loose .md5/.ffp files and identify them against the master
// DB without queueing a folder. This is the one Lookup capability that doesn't
// fit the folder pipeline, so it lives as a lightweight scratch utility.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, TableShell, TH, TR, TD, Banner } = window;
  const { StatusTag } = window.LBB_P2_Parts;

  const SAMPLE = `# paste an Lossless Legs listbox, an .md5, or raw checksums
a17f08cc2e9b41d0  d01t01.flac
5b9920ff1422 a7c  d01t02.flac
7d22cc0817ef99a1  d01t03.flac
c4e1aa0b93ff21d8  d01t04.flac
9f12cc88e0aa17b3  d02t01.flac`;

  // canned identification result for the sample
  const RESULT = {
    total: 5, matched: 4, notfound: 1,
    lb: "LB-08547", detail: "1980-11-22 · San Francisco · Warfield Theatre",
    rows: [
      { md: "a17f08cc2e…", n: "d01t01.flac", lb: "LB-08547", ok: "pass" },
      { md: "5b9920ff14…", n: "d01t02.flac", lb: "LB-08547", ok: "pass" },
      { md: "7d22cc0817…", n: "d01t03.flac", lb: "LB-08547", ok: "pass" },
      { md: "c4e1aa0b93…", n: "d01t04.flac", lb: "LB-08547", ok: "pass" },
      { md: "9f12cc88e0…", n: "d02t01.flac", lb: "—",         ok: "blocked" },
    ],
  };

  function QuickLookup({ onBack, onClose }) {
    const [src, setSrc]   = React.useState("paste"); // paste | clipboard | files
    const [text, setText] = React.useState(SAMPLE);
    const [run, setRun]   = React.useState(false);
    const lines = text.split("\n").filter(l => l.trim() && !l.trim().startsWith("#")).length;

    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
        {/* header */}
        <div style={{ padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)", display: "flex", alignItems: "center", gap: 10 }}>
          <button onClick={onBack} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--lbb-border2)", borderRadius: 6, padding: "4px 10px", color: "var(--lbb-fg2)", fontFamily: "inherit", fontSize: 12, cursor: "pointer" }}>
            <Icon name="chevLeft" size={13} /> Batch
          </button>
          <Icon name="lookup" size={16} style={{ color: "var(--lbb-accent-mid)" }} />
          <span style={{ fontSize: 15, fontWeight: 700 }}>Quick lookup</span>
          <Pill tone="mute" soft>no folder needed</Pill>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>Identify loose checksums straight against the master DB</span>
        </div>

        <div style={{ flex: 1, overflow: "auto", minHeight: 0, padding: "20px 24px", display: "grid", gridTemplateColumns: "minmax(360px, 1fr) 1.2fr", gap: 24, alignItems: "start" }}>
          {/* LEFT — source */}
          <div>
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              <Chip active={src === "paste"} onClick={() => setSrc("paste")} icon="copy">Paste</Chip>
              <Chip active={src === "clipboard"} onClick={() => setSrc("clipboard")} icon="copy">Clipboard</Chip>
              <Chip active={src === "files"} onClick={() => setSrc("files")} icon="attachments">.md5 / .ffp files</Chip>
            </div>

            {src === "files" ? (
              <div style={{ border: "1.5px dashed var(--lbb-border2)", borderRadius: 10, padding: "36px 20px", textAlign: "center", background: "var(--lbb-surface)" }}>
                <Icon name="drop" size={26} style={{ color: "var(--lbb-fg3)" }} />
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 10 }}>Drop .md5, .ffp or .st5 files</div>
                <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 4 }}>Or click to browse — checksums are read and matched, files aren't imported.</div>
                <Button size="sm" variant="secondary" icon="attachments" style={{ marginTop: 14 }}>Choose files…</Button>
              </div>
            ) : (
              <>
                <textarea value={text} onChange={e => setText(e.target.value)}
                  spellCheck={false}
                  style={{ width: "100%", height: 230, resize: "vertical", boxSizing: "border-box", fontFamily: "var(--lbb-mono)", fontSize: 12, lineHeight: 1.6, padding: "12px 14px", borderRadius: 9, border: "1px solid var(--lbb-border)", background: "var(--lbb-surface)", color: "var(--lbb-fg)" }} />
                {src === "clipboard" && <div style={{ fontSize: 11, color: "var(--lbb-fg3)", marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}><Icon name="copy" size={12} /> Pulled {lines} lines from the clipboard — edit before running if needed.</div>}
              </>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}>
              <Button variant="primary" size="md" icon="lookup" disabled={lines === 0} onClick={() => setRun(true)}>
                Look up {lines} checksum{lines === 1 ? "" : "s"}
              </Button>
              {run && <Button variant="ghost" size="md" onClick={() => setRun(false)}>Clear</Button>}
            </div>
          </div>

          {/* RIGHT — results */}
          <div>
            {!run ? (
              <div style={{ border: "1px dashed var(--lbb-border2)", borderRadius: 10, padding: "48px 24px", textAlign: "center", color: "var(--lbb-fg3)", background: "var(--lbb-surface)" }}>
                <Icon name="lookup" size={26} />
                <div style={{ fontSize: 13, marginTop: 10, color: "var(--lbb-fg2)" }}>Results show here once you run a lookup.</div>
                <div style={{ fontSize: 11.5, marginTop: 4 }}>Great for a stray set of checksums you haven't filed into a folder yet.</div>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 16px", marginBottom: 14, background: "var(--lbb-ok-bg)", border: "1px solid var(--lbb-ok-bar)", borderRadius: 9 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 9, background: "var(--lbb-ok-bar)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="check" size={22} /></div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "var(--lbb-mono)", color: "var(--lbb-accent-mid)" }}>{RESULT.lb}</div>
                    <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>{RESULT.detail}</div>
                  </div>
                  <div style={{ flex: 1 }} />
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "var(--lbb-mono)", color: "var(--lbb-ok-fg)" }}>{RESULT.matched}/{RESULT.total}</div>
                    <div style={{ fontSize: 10, color: "var(--lbb-fg3)", textTransform: "uppercase", letterSpacing: 0.06, fontWeight: 700 }}>matched</div>
                  </div>
                </div>
                <TableShell>
                  <colgroup><col style={{ width: 3 }} /><col style={{ width: 132 }} /><col /><col style={{ width: 96 }} /><col style={{ width: 96 }} /></colgroup>
                  <thead><tr><TH> </TH><TH>Checksum</TH><TH>Filename</TH><TH>LB#</TH><TH>Status</TH></tr></thead>
                  <tbody>
                    {RESULT.rows.map((r, i) => (
                      <TR key={i} edge={r.ok === "pass" ? "ok" : "bad"}>
                        <TD mono dim>{r.md}</TD>
                        <TD mono style={{ color: "var(--lbb-fg)" }}>{r.n}</TD>
                        <TD mono style={{ color: r.lb === "—" ? "var(--lbb-fg3)" : "var(--lbb-accent-mid)", fontWeight: r.lb === "—" ? 400 : 600 }}>{r.lb}</TD>
                        <TD><StatusTag state={r.ok}>{r.ok === "pass" ? "Matched" : "Not found"}</StatusTag></TD>
                      </TR>
                    ))}
                  </tbody>
                </TableShell>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14 }}>
                  <Button variant="secondary" size="sm" icon="reveal">Open {RESULT.lb} on LB.com</Button>
                  <Button variant="ghost" size="sm" icon="folderPlus">Queue matching folder…</Button>
                  <div style={{ flex: 1 }} />
                  <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>{RESULT.notfound} not found — likely a different transfer.</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  window.LBB_P2_QuickLookup = QuickLookup;
})();
