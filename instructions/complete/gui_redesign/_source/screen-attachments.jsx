// screen-attachments.jsx
// Attachments · Browse + view every cached file under data/attachments/LB-XXXXX/.
// Per-file viewer specialises by extension (text / HTML / generic).

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD } = window;

  // ── Sample tree: LBs that have local attachments ──
  const LB_TREE = [
    { lb: "LB-1",     title: "Dead/Dylan Rehearsals 1987 1 & 2",    files: 16, active: true, status: "current" },
    { lb: "LB-2",     title: "Dead/Dylan Rehearsals 1987 3",        files: 12, status: "current" },
    { lb: "LB-3",     title: "1987 G.E. Smith Tour Practice",       files: 3,  status: "current" },
    { lb: "LB-10",    title: "1979-11-09 Fox Warfield SF",          files: 24, status: "current" },
    { lb: "LB-16",    title: "1980-11-11 Fox Warfield SF",          files: 11, status: "stale" },
    { lb: "LB-18",    title: "1981-06-29 Earl's Court London",      files: 9,  status: "current" },
    { lb: "LB-70",    title: "1976-04-22 Bellevue, WA",             files: 6,  status: "current" },
    { lb: "LB-130",   title: "1989-05-30 Christchurch NZ",          files: 4,  status: "stale" },
    { lb: "LB-456",   title: "1992-04-04 Hamilton ON",              files: 12, status: "current" },
    { lb: "LB-810",   title: "1982-06-06 Peace Sunday Rally",       files: 18, status: "current" },
    { lb: "LB-1964",  title: "1983-xx-xx First Infidels Rehearsals", files: 5,  status: "missing" },
    { lb: "LB-13680", title: "1983-02-16 Lone Star Cafe NYC",       files: 8,  status: "current" },
  ];

  // Files for active LB (LB-1)
  const FILES_LB1 = [
    { n: "bd87-05.txt",                       ext: "txt",  sz: "4.2 KB",  mtime: "2024-08-12 18:22", active: true,  kind: "text" },
    { n: "bd87-05.md5.txt",                   ext: "md5",  sz: "1.1 KB",  mtime: "2024-08-12 18:22",                kind: "text" },
    { n: "bd87-05.ffp",                       ext: "ffp",  sz: "0.9 KB",  mtime: "2024-08-12 18:22",                kind: "text" },
    { n: "LBF-00001-lbdir-md5.txt",           ext: "txt",  sz: "2.4 KB",  mtime: "2024-08-12 18:22",                kind: "text" },
    { n: "LBF-00001-DigiFlawFinder.html",     ext: "html", sz: "12.8 KB", mtime: "2024-08-12 18:22",                kind: "html" },
    { n: "LBF-00001-shntool-len.txt",         ext: "txt",  sz: "1.6 KB",  mtime: "2024-08-12 18:22",                kind: "text" },
    { n: "notes.txt",                         ext: "txt",  sz: "780 B",   mtime: "2025-01-04 12:08",                kind: "text" },
    { n: "cover.jpg",                         ext: "jpg",  sz: "248 KB",  mtime: "2024-08-12 18:22",                kind: "image" },
    { n: "cover-back.jpg",                    ext: "jpg",  sz: "212 KB",  mtime: "2024-08-12 18:22",                kind: "image" },
    { n: "spectrogram-d01t01.png",            ext: "png",  sz: "1.4 MB",  mtime: "2025-02-18 09:14",                kind: "image" },
    { n: "forum-thread-12491.html",           ext: "html", sz: "44 KB",   mtime: "2024-09-02 13:00",                kind: "html" },
    { n: "info.txt",                          ext: "txt",  sz: "2.1 KB",  mtime: "2024-08-12 18:22",                kind: "text" },
    { n: "info.docx",                         ext: "docx", sz: "16 KB",   mtime: "2024-08-12 18:22",                kind: "binary" },
  ];

  const STATUS_COLOR = { current: "var(--lbb-ok-bar)", stale: "var(--lbb-warn-bar)", missing: "var(--lbb-bad-bar)" };
  const STATUS_LABEL = { current: "current", stale: "stale", missing: "missing" };

  const EXT_ICON = (ext, kind) => {
    if (kind === "html")  return "attachments";
    if (kind === "image") return "spectro";
    if (kind === "binary")return "attachments";
    if (ext === "md5" || ext === "ffp" || ext === "st5") return "verify";
    return "attachments";
  };

  // Sample text payload for the viewer
  const SAMPLE_TXT = `Dylan & Dead Rehearsals  1987 1 & 2  4CDR
Catalog: LB-1
Status:  PUBLIC

CD1 (sbd cassette master > dats > cdrs)
  01   The Times They Are A-Changin'        4:42
  02   When I Paint My Masterpiece          3:18
  03   Man Of Peace                         6:21
  04   I'll Be Your Baby Tonight            3:51
  05   Heart Of Mine                        4:08
  06   Watching The River Flow              5:13
  07   I Want You                           4:02

CD2 (sbd cassette master > dats > cdrs)
  01   Knockin' On Heaven's Door            5:44
  02   It's All Over Now, Baby Blue         5:01
  03   Maggie's Farm                        7:11
  04   Slow Train                           6:33
  05   Tangled Up In Blue                   6:08
  06   Forever Young                        5:11

CD3-4: bonus rehearsal jams · unreleased outtakes

Notes: Master cassettes from G.E. Smith. Transferred to DAT in 1991,
then to CDR in 2003. Source quality is uneven; CDR-3 has tape wow
on tracks 2-4. Lineage trail provided by the original taper.

Cross-reference: LB-2 (same lineage, different tape generation).
Forum discussion: https://wtrf.example/threads/12491

— catalogued by ${"<curator name>"} on 2007-04-18
`;

  function FileRow({ f, active, onClick }) {
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "6px 10px", marginBottom: 1, borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid " + (active ? "var(--lbb-accent-line)" : "transparent"),
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}>
        <Icon name={EXT_ICON(f.ext, f.kind)} size={11} style={{ color: "var(--lbb-fg3)" }} />
        <span style={{ flex: 1, minWidth: 0, fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.n}</span>
        <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{f.sz}</span>
      </button>
    );
  }

  // Viewer panes ─────────────────────────────────────────
  function TextViewer({ name, text }) {
    return (
      <pre style={{
        margin: 0, flex: 1, padding: "20px 24px",
        fontFamily: "var(--lbb-mono)", fontSize: 12.5, lineHeight: 1.6,
        color: "var(--lbb-fg)", whiteSpace: "pre-wrap",
        background: "var(--lbb-bg)", overflow: "auto",
      }}>{text}</pre>
    );
  }

  function HtmlViewer({ name }) {
    return (
      <div style={{ flex: 1, overflow: "auto", padding: 20, background: "#ffffff" }}>
        <div style={{
          maxWidth: 900, margin: "0 auto",
          fontFamily: "Georgia, serif", fontSize: 14, lineHeight: 1.55, color: "#1c1a17",
        }}>
          <h2 style={{ margin: "0 0 6px", fontSize: 22, color: "#2b5fd0" }}>DigiFlawFinder Report</h2>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8e8676", marginBottom: 16 }}>{name}</div>
          <table cellPadding={6} style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f0ede2" }}>
                <th align="left">File</th><th align="right">Length</th><th align="right">CDR</th><th align="right">Flaws</th><th align="left">Notes</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["d01t01.flac", "4:42.20", "✓", "0", ""],
                ["d01t02.flac", "3:18.04", "✓", "0", ""],
                ["d01t03.flac", "6:21.08", "✓", "1", "click @ 0:14"],
                ["d01t04.flac", "3:51.50", "✓", "0", ""],
                ["d02t01.flac", "5:44.10", "✓", "2", "dropouts @ 1:08, 2:33"],
              ].map((r,i) => (
                <tr key={i} style={{ borderBottom: "1px solid #e8e3d3", background: i%2 ? "#fdfbf4" : "white" }}>
                  {r.map((c, j) => <td key={j} align={j===0||j===4?"left":"right"} style={{ fontFamily: j===0||j===4?"Georgia":"monospace" }}>{c}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ marginTop: 20, fontSize: 12, color: "#5b554a" }}>
            <em>Report generated 2014-09-03 with DigiFlawFinder v2.7. 3 flaws detected across 7 tracks. Recommend re-pressing CDR-2.</em>
          </p>
        </div>
      </div>
    );
  }

  function ImageViewer({ name }) {
    return (
      <div style={{
        flex: 1, padding: 24, background: "var(--lbb-bg)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          width: "min(560px, 80%)", aspectRatio: "1/1",
          borderRadius: 8, overflow: "hidden",
          background: "linear-gradient(135deg, #1c1a17 0%, var(--lbb-accent-mid) 100%)",
          backgroundImage: `linear-gradient(135deg, #1c1a17 0%, var(--lbb-accent-mid) 100%), repeating-linear-gradient(45deg, transparent 0 12px, rgba(255,255,255,0.06) 12px 13px)`,
          backgroundBlendMode: "overlay",
          display: "flex", flexDirection: "column", justifyContent: "flex-end",
          padding: 20, color: "#fff",
          boxShadow: "0 16px 36px rgba(0,0,0,0.3)",
        }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.2, textTransform: "uppercase", opacity: 0.7 }}>LB-1 · cover</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>Dylan &amp; Dead Rehearsals</div>
          <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>1987 · 4CDR · LB-1</div>
        </div>
      </div>
    );
  }

  function BinaryViewer({ name, sz }) {
    return (
      <div style={{
        flex: 1, padding: 40, background: "var(--lbb-bg)",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14,
      }}>
        <div style={{
          width: 72, height: 72, borderRadius: 12,
          background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "var(--lbb-fg3)",
        }}><Icon name="attachments" size={32} /></div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 13, fontWeight: 600 }}>{name}</div>
          <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 4 }}>Binary file · {sz} · no in-app preview</div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Button variant="primary" size="sm" icon="reveal">Open externally</Button>
          <Button variant="secondary" size="sm" icon="download">Download a copy</Button>
        </div>
      </div>
    );
  }

  function ScreenAttachments() {
    const [activeLB,   setActiveLB]   = React.useState("LB-1");
    const [activeFile, setActiveFile] = React.useState("bd87-05.txt");

    const active = LB_TREE.find(x => x.lb === activeLB) || LB_TREE[0];
    const file = FILES_LB1.find(f => f.n === activeFile) || FILES_LB1[0];

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Header */}
        <div style={{ padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}><Icon name="attachments" size={18} /></div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Attachments</h1>
                <Pill tone="mute" soft>data/attachments/</Pill>
              </div>
              <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
                Cached files (lbdir, ffp, md5, info, html, cover art) — 15,133 / 16,523 LBs · 91.6%
              </div>
            </div>
            <div style={{ flex: 1 }} />
            <Pill tone="ok" soft>15,133 current</Pill>
            <Pill tone="warn" soft>2 stale</Pill>
            <Pill tone="bad" soft>1 missing</Pill>
            <Button variant="ghost" size="sm" icon="refresh">Refresh tree</Button>
            <Button variant="secondary" size="sm" icon="download">Cache missing</Button>
          </div>
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "260px 280px 1fr", minHeight: 0 }}>
          {/* LB rail */}
          <aside style={{
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--lbb-border)" }}>
              <Input icon="search" placeholder="Jump to LB# or title…" size="sm" style={{ width: "100%" }} />
              <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
                <Chip active size="sm" count={15133}>Current</Chip>
                <Chip size="sm" count={2}>Stale</Chip>
                <Chip size="sm" count={1}>Missing</Chip>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {LB_TREE.map((r, i) => (
                <button key={r.lb} onClick={() => setActiveLB(r.lb)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 10px", marginBottom: 1, borderRadius: 6,
                    background: r.lb === activeLB ? "var(--lbb-accent-soft)" : "transparent",
                    color: r.lb === activeLB ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                    border: "1px solid " + (r.lb === activeLB ? "var(--lbb-accent-line)" : "transparent"),
                    textAlign: "left", fontFamily: "inherit", cursor: "pointer",
                  }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: STATUS_COLOR[r.status], flex: "0 0 6px" }} />
                  <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                    <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600, fontSize: 11.5 }}>{r.lb}</span>
                    <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.title}</span>
                  </span>
                  <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{r.files}</span>
                </button>
              ))}
              <div style={{ padding: "8px 10px", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic" }}>+ 15,121 more LBs…</div>
            </div>
          </aside>

          {/* File list for active LB */}
          <aside style={{
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 13, fontWeight: 700, color: "var(--lbb-accent-mid)" }}>{active.lb}</span>
                <Pill tone={active.status === "current" ? "ok" : active.status === "stale" ? "warn" : "bad"} soft>{STATUS_LABEL[active.status]}</Pill>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 4 }}>{active.title}</div>
              <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 2, fontFamily: "var(--lbb-mono)" }}>{active.files} files · data/attachments/{active.lb}/</div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {FILES_LB1.map((f, i) => <FileRow key={i} f={f} active={f.n === activeFile} onClick={() => setActiveFile(f.n)} />)}
            </div>
            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="refresh" block>Re-download {active.lb}</Button>
              <Button variant="ghost" size="sm" icon="reveal" block>Open folder…</Button>
            </div>
          </aside>

          {/* Viewer */}
          <section style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            {/* File meta + actions */}
            <div style={{
              padding: "10px 24px", borderBottom: "1px solid var(--lbb-border)",
              display: "flex", alignItems: "center", gap: 12,
              background: "var(--lbb-surface)", fontSize: 11.5,
            }}>
              <Icon name={EXT_ICON(file.ext, file.kind)} size={14} style={{ color: "var(--lbb-fg2)" }} />
              <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600, color: "var(--lbb-fg)" }}>{file.n}</span>
              <span style={{ color: "var(--lbb-fg3)" }}>{file.sz}</span>
              <span style={{ color: "var(--lbb-fg3)" }}>Modified <span style={{ fontFamily: "var(--lbb-mono)" }}>{file.mtime}</span></span>
              <span style={{ color: "var(--lbb-fg3)" }}>UTF-8</span>
              <div style={{ flex: 1 }} />
              <Button variant="ghost" size="sm" icon="copy">Copy contents</Button>
              <Button variant="ghost" size="sm" icon="reveal">Open externally</Button>
              <Button variant="ghost" size="sm" icon="download">Download</Button>
            </div>

            {/* Type-specific viewer */}
            {file.kind === "text"   && <TextViewer name={file.n} text={SAMPLE_TXT} />}
            {file.kind === "html"   && <HtmlViewer name={file.n} />}
            {file.kind === "image"  && <ImageViewer name={file.n} />}
            {file.kind === "binary" && <BinaryViewer name={file.n} sz={file.sz} />}

            {/* Hint footer */}
            <div style={{
              padding: "8px 24px", borderTop: "1px solid var(--lbb-border)",
              background: "var(--lbb-surface)", fontSize: 11, color: "var(--lbb-fg3)",
              display: "flex", alignItems: "center", gap: 14,
            }}>
              <Icon name="info" size={12} />
              Files dropped into <span style={{ fontFamily: "var(--lbb-mono)" }}>data/attachments/{active.lb}/</span> show up here after Refresh. Re-download will overwrite manual files.
              <div style={{ flex: 1 }} />
              <span style={{ fontFamily: "var(--lbb-mono)" }}>{active.lb} · {file.n}</span>
            </div>
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenAttachments = ScreenAttachments;
})();
