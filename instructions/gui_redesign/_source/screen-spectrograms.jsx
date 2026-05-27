// screen-spectrograms.jsx
// Spectrograms · Batch-generate spectrogram PNGs per folder using SoX/ffmpeg.
// Inventory: PNG-per-audio-file under each folder. Backend /api/spectrogram/*

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD } = window;

  // Sample folder list with PNG inventory + batch state
  const FOLDERS = [
    { p: "/mnt/HOPPER/bd2025-03-25 soomlos",        n: 17, done: 17, active: true,  state: "done"  },
    { p: "/mnt/HOPPER/bd2026-04-02 Madison WI",     n: 14, done: 0,                  state: "queued" },
    { p: "/mnt/HOPPER/bd2026-04-05 Minneapolis MN", n: 16, done: 9,                  state: "running" },
    { p: "/mnt/HOPPER/bd2026-04-08 Chicago IL",     n: 18, done: 18,                 state: "done" },
    { p: "/mnt/HOPPER/bd2026-04-12 Detroit MI",     n: 11, done: 0,                  state: "queued", note: "shn — needs decode" },
  ];

  // Track-level inventory for the active folder (17 files)
  const TRACKS = [
    { idx:  1, n: "bd2025-03-25-t01.flac", durS: "4:42",  has: true,  selected: true },
    { idx:  2, n: "bd2025-03-25-t02.flac", durS: "3:18",  has: true },
    { idx:  3, n: "bd2025-03-25-t03.flac", durS: "6:21",  has: true },
    { idx:  4, n: "bd2025-03-25-t04.flac", durS: "3:51",  has: true },
    { idx:  5, n: "bd2025-03-25-t05.flac", durS: "5:14",  has: true },
    { idx:  6, n: "bd2025-03-25-t06.flac", durS: "4:08",  has: true },
    { idx:  7, n: "bd2025-03-25-t07.flac", durS: "5:44",  has: true },
    { idx:  8, n: "bd2025-03-25-t08.flac", durS: "5:01",  has: true },
    { idx:  9, n: "bd2025-03-25-t09.flac", durS: "7:11",  has: true },
    { idx: 10, n: "bd2025-03-25-t10.flac", durS: "6:33",  has: true },
  ];

  function FolderRow({ row, active, onClick }) {
    const pct = row.n ? Math.round(row.done / row.n * 100) : 0;
    const tone = row.state === "done" ? "ok" : row.state === "running" ? "info" : "mute";
    return (
      <button onClick={onClick} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "7px 10px", marginBottom: 1, borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid " + (active ? "var(--lbb-accent-line)" : "transparent"),
        textAlign: "left", fontFamily: "inherit", cursor: "pointer",
      }}>
        <Icon name="folder" size={11} style={{ color: "var(--lbb-fg3)" }} />
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.p.split("/").pop()}</span>
          <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", display: "flex", alignItems: "center", gap: 5 }}>
            <span>{row.done}/{row.n}</span>
            {row.state === "running" && <Pill tone="info" soft style={{ fontSize: 9, padding: "0 5px" }}>running · {pct}%</Pill>}
            {row.state === "done"    && <Icon name="check" size={10} style={{ color: "var(--lbb-ok-bar)" }} />}
            {row.note && <span style={{ color: "var(--lbb-warn-fg)" }}>· {row.note}</span>}
          </span>
        </span>
      </button>
    );
  }

  function ScreenSpectrograms() {
    const [activeIdx, setActiveIdx]  = React.useState(0);
    const [activeTrack, setActiveTrack] = React.useState(0);
    const [view, setView] = React.useState("spectrogram"); // spectrogram | waveform | fingerprint
    const [zoom, setZoom] = React.useState(100);

    const folder = FOLDERS[activeIdx];
    const track  = TRACKS[activeTrack];

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
          }}><Icon name="spectro" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Spectrograms</h1>
              <Pill tone="mute" soft>SoX batch render</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              Per-track PNG spectrograms cached alongside audio files. Used to spot upsamples, EQ tells, and dropouts.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 14, padding: "0 12px", borderRight: "1px solid var(--lbb-border)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--lbb-fg2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} />
              SoX 14.4.2
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--lbb-fg2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} />
              ffmpeg 6.0
            </span>
          </div>
          <Button variant="ghost" size="sm" icon="folderPlus">Add folder…</Button>
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Folder rail */}
          <aside style={{
            width: 300, flex: "0 0 300px",
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <Icon name="folder" size={13} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.1, textTransform: "uppercase" }}>Folders</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{FOLDERS.length}</span>
              </div>
              <Input icon="search" placeholder="Filter folders…" size="sm" style={{ width: "100%" }} />
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 6px" }}>
              {FOLDERS.map((r, i) => <FolderRow key={i} row={r} active={i === activeIdx} onClick={() => setActiveIdx(i)} />)}
            </div>

            {/* Batch progress */}
            <div style={{ borderTop: "1px solid var(--lbb-border)", padding: "12px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>
                Batch · 76 of 76 tracks
              </div>
              <div className="lbb-prog"><div style={{ width: "100%" }} /></div>
              <div style={{ marginTop: 6, display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--lbb-fg3)" }}>
                <span><Icon name="check" size={10} style={{ color: "var(--lbb-ok-bar)" }} /> 64 done</span>
                <span>· 12 skipped</span>
                <span>· 0 errors</span>
              </div>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                <Button variant="primary" size="sm" icon="play" block>Generate missing (12)</Button>
                <Button variant="secondary" size="sm" icon="pause" block disabled>Stop after current</Button>
                <Button variant="ghost" size="sm" icon="refresh" block>Re-scan inventory</Button>
              </div>
            </div>
          </aside>

          {/* Track + viewer */}
          <section style={{ flex: 1, display: "grid", gridTemplateColumns: "260px 1fr", minHeight: 0 }}>
            {/* Track rail */}
            <aside style={{
              background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
              display: "flex", flexDirection: "column", minHeight: 0,
            }}>
              <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--lbb-border)" }}>
                <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 12, fontWeight: 600 }}>{folder.p.split("/").pop()}</div>
                <div style={{ marginTop: 4, fontSize: 10.5, color: "var(--lbb-fg3)" }}>{folder.done} / {folder.n} tracks rendered</div>
              </div>
              <div style={{ padding: "8px 14px 4px", fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Tracks</div>
              <div style={{ flex: 1, overflowY: "auto", padding: "0 8px 8px" }}>
                {TRACKS.map((t, i) => (
                  <button key={i} onClick={() => setActiveTrack(i)}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 8px", marginBottom: 1, borderRadius: 6,
                      background: i === activeTrack ? "var(--lbb-accent-soft)" : "transparent",
                      color: i === activeTrack ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                      border: "1px solid " + (i === activeTrack ? "var(--lbb-accent-line)" : "transparent"),
                      textAlign: "left", fontFamily: "inherit", cursor: "pointer",
                    }}>
                    <span style={{
                      width: 22, height: 22, borderRadius: 4,
                      background: i === activeTrack ? "var(--lbb-accent-mid)" : "var(--lbb-surface2)",
                      color: i === activeTrack ? "var(--lbb-accent-onMid)" : "var(--lbb-fg3)",
                      display: "inline-flex", alignItems: "center", justifyContent: "center",
                      fontFamily: "var(--lbb-mono)", fontWeight: 700, fontSize: 10,
                    }}>{String(t.idx).padStart(2, "0")}</span>
                    <span style={{ flex: 1, minWidth: 0, fontFamily: "var(--lbb-mono)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.n}</span>
                    <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 10, color: "var(--lbb-fg3)" }}>{t.durS}</span>
                    {t.has
                      ? <Pill tone="ok" soft style={{ fontSize: 9, padding: "0 4px" }}>PNG</Pill>
                      : <Pill tone="mute" soft style={{ fontSize: 9, padding: "0 4px" }}>—</Pill>}
                  </button>
                ))}
                <div style={{ padding: "8px 10px", fontSize: 10.5, color: "var(--lbb-fg3)", fontStyle: "italic" }}>+ 7 more tracks…</div>
              </div>

              {/* Options */}
              <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)" }}>
                <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>
                  Render options
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: "6px 8px", fontSize: 11.5, alignItems: "center" }}>
                  <span style={{ color: "var(--lbb-fg3)" }}>Width</span>
                  <Input size="sm" placeholder="1500" style={{ width: "100%" }} />
                  <span style={{ color: "var(--lbb-fg3)" }}>Height</span>
                  <Input size="sm" placeholder="400" style={{ width: "100%" }} />
                  <span style={{ color: "var(--lbb-fg3)" }}>dB floor</span>
                  <Input size="sm" placeholder="-120" style={{ width: "100%" }} />
                  <span style={{ color: "var(--lbb-fg3)" }}>Window</span>
                  <Button variant="secondary" size="sm" iconRight="chevDown" style={{ justifyContent: "space-between", width: "100%" }}>hann</Button>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--lbb-fg2)", marginTop: 8 }}>
                  <input type="checkbox" /> Force re-render
                </label>
              </div>
            </aside>

            {/* Spectrogram viewer */}
            <div style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
              {/* Toolbar */}
              <div style={{
                padding: "10px 20px", borderBottom: "1px solid var(--lbb-border)",
                display: "flex", alignItems: "center", gap: 8,
              }}>
                <Chip active={view === "spectrogram"} onClick={() => setView("spectrogram")} size="sm" icon="spectro">Spectrogram</Chip>
                <Chip active={view === "waveform"}    onClick={() => setView("waveform")}    size="sm">Waveform</Chip>
                <Chip active={view === "fingerprint"} onClick={() => setView("fingerprint")} size="sm">Fingerprint heatmap</Chip>
                <div style={{ flex: 1 }} />
                <IconButton icon="x" title="Zoom out" onClick={() => setZoom(Math.max(25, zoom - 25))} />
                <span style={{ fontSize: 11, fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)", width: 50, textAlign: "center" }}>{zoom}%</span>
                <IconButton icon="plus" title="Zoom in" onClick={() => setZoom(Math.min(400, zoom + 25))} />
                <Button variant="ghost" size="sm" onClick={() => setZoom(100)}>Fit</Button>
                <span style={{ width: 1, height: 18, background: "var(--lbb-border)", margin: "0 4px" }} />
                <Button variant="ghost" size="sm" icon="reveal">Open PNG</Button>
                <Button variant="primary" size="sm" icon="play">Re-render</Button>
              </div>

              <div style={{ flex: 1, overflow: "auto", padding: 20, background: "var(--lbb-surface2)" }}>
                {/* Meta line */}
                <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginBottom: 8, fontFamily: "var(--lbb-mono)" }}>
                  {track.n} · 0 – 330 s · 0 – 22 kHz · 16-bit / 44.1 kHz
                </div>

                {/* Main canvas */}
                <div className="lbb-spec-canvas" style={{
                  position: "relative", height: 380, borderRadius: 6,
                  border: "1px solid var(--lbb-border2)",
                  filter: view === "waveform" ? "saturate(0.4)" : "none",
                }}>
                  {/* y axis */}
                  <div style={{ position: "absolute", left: 8, top: 6, fontSize: 10.5, color: "rgba(255,255,255,0.75)", fontFamily: "var(--lbb-mono)" }}>22 kHz</div>
                  <div style={{ position: "absolute", left: 8, top: "30%", fontSize: 10.5, color: "rgba(255,255,255,0.6)", fontFamily: "var(--lbb-mono)" }}>16 kHz</div>
                  <div style={{ position: "absolute", left: 8, top: "60%", fontSize: 10.5, color: "rgba(255,255,255,0.6)", fontFamily: "var(--lbb-mono)" }}>5 kHz</div>
                  <div style={{ position: "absolute", left: 8, bottom: 6, fontSize: 10.5, color: "rgba(255,255,255,0.75)", fontFamily: "var(--lbb-mono)" }}>0 Hz</div>
                  {/* x axis */}
                  <div style={{ position: "absolute", right: 8, bottom: 6, fontSize: 10.5, color: "rgba(255,255,255,0.75)", fontFamily: "var(--lbb-mono)" }}>5:30</div>
                  <div style={{ position: "absolute", left: "50%", bottom: 6, fontSize: 10.5, color: "rgba(255,255,255,0.5)", fontFamily: "var(--lbb-mono)" }}>2:45</div>
                  {/* Annotation: 16k hiss-cap (upsample tell) */}
                  <div style={{ position: "absolute", left: 0, right: 0, top: "27%", height: 2, background: "rgba(255,255,255,0.35)", borderTop: "1px dashed rgba(255,255,255,0.6)" }} />
                  <div style={{ position: "absolute", left: 14, top: "calc(27% - 24px)", padding: "2px 6px", background: "rgba(255,200,80,0.85)", color: "#0e0a04", fontSize: 10, fontWeight: 700, borderRadius: 3 }}>
                    16 kHz cap · possible upsample
                  </div>
                  {/* Playhead */}
                  <div style={{ position: "absolute", top: 0, bottom: 0, left: "32%", width: 1, background: "rgba(255,255,255,0.65)" }}>
                    <div style={{ position: "absolute", top: -6, left: -5, width: 10, height: 10, borderRadius: "50%", background: "#fff" }}/>
                  </div>
                  {/* dB legend */}
                  <div style={{ position: "absolute", right: 12, top: 12, padding: "4px 8px", background: "rgba(0,0,0,0.45)", color: "#fff", fontSize: 10, fontFamily: "var(--lbb-mono)", borderRadius: 4 }}>
                    −120 dB → 0 dB
                  </div>
                </div>

                {/* Playback strip */}
                <div style={{
                  marginTop: 10, padding: "8px 12px", borderRadius: 6,
                  background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
                  display: "flex", alignItems: "center", gap: 14, fontSize: 11.5,
                }}>
                  <IconButton icon="play" size={26} />
                  <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>1:46 / 5:30</span>
                  <div style={{ flex: 1 }} className="lbb-prog"><div style={{ width: "32%" }} /></div>
                  <span style={{ color: "var(--lbb-fg3)" }}>Tip: Ctrl+scroll = zoom · drag = pan · double-click = reset</span>
                </div>

                {/* Lower thumb strip */}
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
                  {TRACKS.slice(0, 6).map((t, i) => (
                    <button key={i} onClick={() => setActiveTrack(i)} style={{
                      background: "transparent", border: "none", padding: 0, cursor: "pointer", fontFamily: "inherit",
                    }}>
                      <div className="lbb-spec-canvas" style={{
                        height: 64, borderRadius: 5,
                        border: i === activeTrack ? "1px solid var(--lbb-accent-mid)" : "1px solid var(--lbb-border)",
                        position: "relative",
                        boxShadow: i === activeTrack ? "0 0 0 2px var(--lbb-accent-soft)" : "none",
                      }}>
                        <div style={{
                          position: "absolute", left: 4, bottom: 3,
                          fontSize: 9.5, color: "rgba(255,255,255,0.85)", fontFamily: "var(--lbb-mono)",
                        }}>t{String(t.idx).padStart(2, "0")}</div>
                      </div>
                    </button>
                  ))}
                </div>

                {/* Error / skipped row */}
                <div style={{
                  marginTop: 18, padding: "10px 14px", borderRadius: 6,
                  background: "var(--lbb-warn-bg)", border: "1px solid var(--lbb-warn-bar)",
                  fontSize: 11.5, color: "var(--lbb-fg2)",
                  display: "flex", gap: 10, alignItems: "flex-start",
                }}>
                  <Icon name="info" size={13} style={{ color: "var(--lbb-warn-fg)", marginTop: 1 }} />
                  <div style={{ flex: 1 }}>
                    <strong style={{ color: "var(--lbb-warn-fg)" }}>SHN folder skipped.</strong>&nbsp;
                    bd2026-04-12 Detroit MI contains 11 SHN files. SoX requires decoding to WAV first — this takes 2-3× longer per track. Enable in Setup → Spectrograms → "Decode SHN before rendering".
                  </div>
                  <Button size="sm" variant="ghost">Enable in Setup</Button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    );
  }

  window.LBB_ScreenSpectrograms = ScreenSpectrograms;
})();
