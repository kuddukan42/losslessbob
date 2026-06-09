// screen-settings.jsx — Setup + Themes screens.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Card, Chip, Input, IconButton,
          TableShell, TH, TR, TD } = window;

  // ─── Setup ─────────────────────────────────────────────────────────
  function SetupCard({ title, badge, children, style }) {
    return (
      <div style={{
        background: "var(--lbb-surface)",
        border: "1px solid var(--lbb-border)", borderRadius: 10,
        padding: 18, ...style,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <h4 style={{ margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg)" }}>{title}</h4>
          {badge}
        </div>
        {children}
      </div>
    );
  }

  function ScreenSetup({ curatorMode, onSetCurator }) {
    return (
      <div style={{ padding: "24px 32px 40px", maxWidth: 1500, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: -0.01 }}>Setup</h1>
          <div style={{ fontSize: 13, color: "var(--lbb-fg3)", marginTop: 3 }}>
            Database, integrations, preferences, and master-data tooling.
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Database */}
          <SetupCard title="Database" badge={<Pill tone="ok" soft dot>connected</Pill>}>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 14px", fontSize: 12, color: "var(--lbb-fg2)", alignItems: "center" }}>
              <span style={{ color: "var(--lbb-fg3)" }}>Active</span>
              <span><Button variant="secondary" size="sm" iconRight="chevDown">LossLessBob</Button></span>
              <span style={{ color: "var(--lbb-fg3)" }}>Checksums</span>
              <span style={{ fontFamily: "var(--lbb-mono)" }}><strong style={{ color: "var(--lbb-fg)" }}>704,624</strong></span>
              <span style={{ color: "var(--lbb-fg3)" }}>LB entries</span>
              <span style={{ fontFamily: "var(--lbb-mono)" }}><strong style={{ color: "var(--lbb-fg)" }}>16,523</strong> · latest <strong style={{ color: "var(--lbb-fg)" }}>LB-16630</strong></span>
              <span style={{ color: "var(--lbb-fg3)" }}>Last import</span>
              <span style={{ fontFamily: "var(--lbb-mono)" }}>2026-05-21 01:08:18</span>
              <span style={{ color: "var(--lbb-fg3)" }}>DB size</span>
              <span style={{ fontFamily: "var(--lbb-mono)" }}>241 MB · WAL 4 MB</span>
            </div>
            <div style={{ marginTop: 14, display: "flex", gap: 6, flexWrap: "wrap" }}>
              <Button size="sm" variant="secondary" icon="download">Import DB file…</Button>
              <Button size="sm" variant="secondary" icon="refresh">Check for update</Button>
              <Button size="sm" variant="ghost" icon="reveal">Open data folder</Button>
              <Button size="sm" variant="danger" icon="trash">Reset DB…</Button>
            </div>
            <div style={{ marginTop: 12, padding: "8px 10px", borderRadius: 6, background: "var(--lbb-surface2)", display: "flex", alignItems: "center", gap: 14, fontSize: 11.5, color: "var(--lbb-fg2)" }}>
              <span>Helpers:</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} /> SoX</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} /> ffmpeg</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-ok-bar)" }} /> shntool</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-warn-bar)" }} /> acoustid</span>
              <Button size="sm" variant="ghost">Re-check</Button>
            </div>
          </SetupCard>

          {/* Master Data — Curator switch */}
          <SetupCard title="Master Data"
            badge={curatorMode ? <Pill tone="warn" soft>Curator mode on</Pill> : null}>
            <div style={{
              display: "flex", alignItems: "center", gap: 14, padding: "12px 14px",
              border: "1px solid var(--lbb-border)", borderRadius: 8,
              background: curatorMode ? "var(--lbb-warn-bg)" : "var(--lbb-surface2)",
            }}>
              <div style={{
                width: 38, height: 38, borderRadius: 9,
                background: curatorMode ? "var(--lbb-warn-bar)" : "var(--lbb-surface)",
                color: curatorMode ? "#fff" : "var(--lbb-fg2)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                border: "1px solid var(--lbb-border2)",
              }}><Icon name="shield" size={18} /></div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Curator mode</div>
                <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>
                  Reveals DB Editor, Scraper, Publish, and geocoding. New users keep this off.
                </div>
              </div>
              <button
                onClick={() => onSetCurator(!curatorMode)}
                style={{
                  width: 44, height: 24, borderRadius: 999,
                  background: curatorMode ? "var(--lbb-accent-mid)" : "var(--lbb-border2)",
                  border: "none", cursor: "pointer", position: "relative",
                  transition: "background 150ms ease",
                }}
              >
                <span style={{
                  position: "absolute", top: 2, left: curatorMode ? 22 : 2,
                  width: 20, height: 20, borderRadius: "50%",
                  background: "#fff", transition: "left 150ms ease",
                  boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                }} />
              </button>
            </div>
            <div style={{ marginTop: 12, fontSize: 12, color: "var(--lbb-fg2)" }}>
              Master version: <span style={{ fontFamily: "var(--lbb-mono)" }}>not yet published</span>
            </div>
            <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
              <Button size="sm" variant="secondary" disabled={!curatorMode}>Publish master update…</Button>
              <Button size="sm" variant="ghost">Install master update…</Button>
            </div>
          </SetupCard>

          {/* Integrations */}
          <SetupCard title="Integrations" style={{ gridColumn: "span 2" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
              <Integ title="qBittorrent" status="ok"
                fields={[["Host", "localhost"], ["Port", "8080"], ["User", "admin"]]}
              />
              <Integ title="Watching the River Flow forum" status="warn"
                fields={[["User", "rolling.thunder"], ["Board", "tradeable"], ["Session", "expires in 4d"]]}
              />
              <Integ title="Torrent web UI" status="mute"
                fields={[["Tracker", "open.tracker.cl"], ["Web GUI", "not configured"]]}
              />
            </div>
          </SetupCard>

          {/* Preferences */}
          <SetupCard title="Preferences">
            <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "8px 12px", fontSize: 12, alignItems: "center" }}>
              <span style={{ color: "var(--lbb-fg2)" }}>Interface language</span>
              <Button variant="secondary" size="sm" iconRight="chevDown" style={{ justifyContent: "space-between" }}>English (US)</Button>
              <span style={{ color: "var(--lbb-fg2)" }}>Results per page</span>
              <div style={{ display: "flex", padding: 2, background: "var(--lbb-surface2)", borderRadius: 6, border: "1px solid var(--lbb-border)", width: "fit-content" }}>
                {["50", "100", "250", "All"].map((v,i) => (
                  <button key={v} style={{
                    padding: "4px 12px", borderRadius: 4,
                    background: i === 0 ? "var(--lbb-surface)" : "transparent",
                    color: i === 0 ? "var(--lbb-fg)" : "var(--lbb-fg2)",
                    fontWeight: i === 0 ? 600 : 500, fontSize: 11.5,
                    border: i === 0 ? "1px solid var(--lbb-border2)" : "1px solid transparent",
                    cursor: "pointer", fontFamily: "inherit",
                  }}>{v}</button>
                ))}
              </div>
              <span style={{ color: "var(--lbb-fg2)" }}>Column widths</span>
              <div style={{ display: "flex", gap: 6 }}>
                <Button size="sm" variant="secondary">Save current</Button>
                <Button size="sm" variant="ghost">Restore</Button>
                <Button size="sm" variant="ghost">Factory</Button>
              </div>
              <span style={{ color: "var(--lbb-fg2)" }}>Auto-scrape on import</span>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}><input type="checkbox" defaultChecked /> Enabled</label>
              <span style={{ color: "var(--lbb-fg2)" }}>Send anon. usage</span>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}><input type="checkbox" /> Disabled</label>
            </div>
          </SetupCard>

          {/* Data purges */}
          <SetupCard title="Data management · purges">
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "8px 14px", fontSize: 12, alignItems: "center" }}>
              <span>My Collection (+ ratings, alerts)</span><Button size="sm" variant="ghost">Purge…</Button>
              <span>Wishlist</span><Button size="sm" variant="ghost">Purge…</Button>
              <span>Personal ratings &amp; tags only</span><Button size="sm" variant="ghost">Purge…</Button>
              <span>Watchdog alerts</span><Button size="sm" variant="ghost">Purge…</Button>
              <span>Scrape diff changelog</span><Button size="sm" variant="ghost">Purge…</Button>
            </div>
            <div style={{ marginTop: 10, fontSize: 10.5, color: "var(--lbb-fg3)" }}>
              User data only. The checksum archive is never affected.
            </div>
          </SetupCard>

          {/* Flat file history */}
          <SetupCard title="Flat file history" style={{ gridColumn: "span 2" }}>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} /><col style={{ width: 170 }} />
                <col /><col style={{ width: 110 }} />
                <col style={{ width: 100 }} /><col style={{ width: 100 }} /><col style={{ width: 120 }} />
              </colgroup>
              <thead><tr>
                <TH> </TH><TH>Detected</TH><TH>Filename</TH><TH>Status</TH>
                <TH align="right">Added</TH><TH align="right">Changed</TH><TH align="right"> </TH>
              </tr></thead>
              <tbody>
                <TR edge="ok"><TD mono>2026-05-19 18:02</TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>Checksum_Lookup_flat_LB_16630.zip</TD>
                  <TD><Pill tone="ok" soft>Applied</Pill></TD>
                  <TD align="right" mono>2,324</TD><TD align="right" mono>5,831</TD>
                  <TD align="right"><Button size="sm" variant="ghost">Open</Button></TD></TR>
                <TR edge="mute"><TD mono>2026-05-19 03:34</TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>Checksum_Lookup_flat_LB_16588.zip</TD>
                  <TD><Pill tone="mute" soft>Detected</Pill></TD>
                  <TD align="right" mono dim>—</TD><TD align="right" mono dim>—</TD>
                  <TD align="right"><Button size="sm" variant="secondary">Apply</Button></TD></TR>
                <TR edge="ok"><TD mono>2026-04-12 10:15</TD>
                  <TD mono style={{ color: "var(--lbb-fg)" }}>Checksum_Lookup_flat_LB_16520.zip</TD>
                  <TD><Pill tone="ok" soft>Applied</Pill></TD>
                  <TD align="right" mono>1,890</TD><TD align="right" mono>3,201</TD>
                  <TD align="right"><Button size="sm" variant="ghost">Open</Button></TD></TR>
              </tbody>
            </TableShell>
          </SetupCard>
        </div>
      </div>
    );
  }

  function Integ({ title, status, fields }) {
    return (
      <div style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid var(--lbb-border)", background: "var(--lbb-surface2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <strong style={{ fontSize: 12, color: "var(--lbb-fg)" }}>{title}</strong>
          {status === "ok"   && <Pill tone="ok"   soft dot>connected</Pill>}
          {status === "warn" && <Pill tone="warn" soft dot>expires soon</Pill>}
          {status === "mute" && <Pill tone="mute" soft>not configured</Pill>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: "3px 10px", fontSize: 11.5 }}>
          {fields.map(([k, v]) => (
            <React.Fragment key={k}>
              <span style={{ color: "var(--lbb-fg3)" }}>{k}</span>
              <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>{v}</span>
            </React.Fragment>
          ))}
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
          <Button size="sm" variant="ghost">Test</Button>
          <Button size="sm" variant="secondary">Edit…</Button>
        </div>
      </div>
    );
  }

  // ─── Themes ────────────────────────────────────────────────────────
  // Driven by the tokens. Lets the user pick mode/accent/density inline.
  function ScreenThemes({ tweaks, setTweak }) {
    const ACCENTS = [
      { k: "indigo",  c: "#2b5fd0" },
      { k: "plum",    c: "#7a3fb1" },
      { k: "rust",    c: "#a8462e" },
      { k: "forest",  c: "#2a7a4a" },
      { k: "teal",    c: "#2b6f7c" },
      { k: "amber",   c: "#9a6800" },
      { k: "gray",    c: "#4a463e" },
      { k: "crimson", c: "#a31a35" },
    ];

    return (
      <div style={{ padding: "24px 32px 40px", maxWidth: 1500, margin: "0 auto" }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: -0.01 }}>Themes</h1>
          <div style={{ fontSize: 13, color: "var(--lbb-fg3)", marginTop: 3 }}>
            Mode × accent × density. Status colors stay fixed for accessibility.
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Mode */}
          <SetupCard title="Mode">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              {[
                { k: "light",  l: "Light",  preview: ["#faf8f3", "#e2dfd2"] },
                { k: "dark",   l: "Dark",   preview: ["#27251d", "#161510"] },
                { k: "system", l: "System", preview: ["#faf8f3", "#161510"] },
              ].map(m => (
                <button key={m.k} onClick={() => setTweak("mode", m.k)}
                  style={{
                    padding: 10, borderRadius: 10,
                    background: "var(--lbb-surface)",
                    border: `2px solid ${tweaks.mode === m.k ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`,
                    cursor: "pointer", fontFamily: "inherit", color: "var(--lbb-fg)",
                  }}>
                  <div style={{ height: 80, borderRadius: 6, overflow: "hidden", border: "1px solid var(--lbb-border2)", display: "grid", gridTemplateColumns: "1fr 2fr" }}>
                    <div style={{ background: m.preview[1] }} />
                    <div style={{ background: m.preview[0], padding: 8 }}>
                      <div style={{ height: 6, background: m.preview[1], opacity: 0.6, borderRadius: 2, marginBottom: 6 }} />
                      <div style={{ height: 4, background: m.preview[1], opacity: 0.3, borderRadius: 2, marginBottom: 4 }} />
                      <div style={{ height: 4, background: m.preview[1], opacity: 0.3, borderRadius: 2, width: "60%" }} />
                    </div>
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600 }}>{m.l}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* Density */}
          <SetupCard title="Density">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              {[
                { k: "comfortable", l: "Comfortable", n: "~25 rows" },
                { k: "default",     l: "Default",     n: "~32 rows" },
                { k: "compact",     l: "Compact",     n: "~55 rows" },
              ].map(d => (
                <button key={d.k} onClick={() => setTweak("density", d.k)}
                  style={{
                    padding: 12, borderRadius: 10,
                    background: "var(--lbb-surface)",
                    border: `2px solid ${tweaks.density === d.k ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`,
                    cursor: "pointer", fontFamily: "inherit", color: "var(--lbb-fg)",
                    textAlign: "left",
                  }}>
                  <div style={{ height: 80, display: "flex", flexDirection: "column", gap: d.k === "compact" ? 2 : d.k === "default" ? 5 : 8 }}>
                    {Array.from({ length: d.k === "compact" ? 8 : d.k === "default" ? 6 : 4 }).map((_,i) => (
                      <div key={i} style={{ height: d.k === "compact" ? 5 : d.k === "default" ? 7 : 11, background: "var(--lbb-surface2)", borderRadius: 2 }} />
                    ))}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600 }}>{d.l}</div>
                  <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)" }}>{d.n}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* Accent */}
          <SetupCard title="Accent" style={{ gridColumn: "span 2" }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {ACCENTS.map(a => (
                <button key={a.k} onClick={() => setTweak("accent", a.k)}
                  style={{
                    padding: 8, borderRadius: 10,
                    background: "var(--lbb-surface)",
                    border: `2px solid ${tweaks.accent === a.k ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`,
                    cursor: "pointer", fontFamily: "inherit",
                    display: "flex", flexDirection: "column", alignItems: "center", gap: 6, width: 84,
                  }}>
                  <div style={{
                    width: 50, height: 50, borderRadius: "50%",
                    background: a.c, border: "1px solid rgba(0,0,0,0.08)",
                    boxShadow: "0 1px 0 rgba(255,255,255,0.3) inset",
                  }}/>
                  <span style={{ fontSize: 11.5, color: "var(--lbb-fg)", fontWeight: 600, textTransform: "capitalize" }}>{a.k}</span>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* Typeface */}
          <SetupCard title="Typeface">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { k: "inter",     l: "Inter",     n: "system default · clean grotesque" },
                { k: "ibm-plex",  l: "IBM Plex Sans", n: "characterful · designed for data" },
                { k: "source",    l: "Source Sans 3", n: "warmer humanist · book-text feel" },
              ].map((f, i) => (
                <button key={f.k} style={{
                  padding: "10px 14px", borderRadius: 8,
                  background: "var(--lbb-surface)",
                  border: `1px solid ${i === 0 ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}`,
                  cursor: "pointer", fontFamily: "inherit", textAlign: "left",
                  display: "flex", alignItems: "center", gap: 12,
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--lbb-fg)" }}>{f.l}</div>
                    <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>{f.n}</div>
                  </div>
                  {i === 0 && <Icon name="check" size={14} style={{ color: "var(--lbb-accent-mid)" }} />}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--lbb-fg3)" }}>Size: 12pt · 13pt · 14pt</div>
          </SetupCard>

          {/* Advanced */}
          <SetupCard title="Advanced">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Button variant="secondary" size="sm" iconRight="chevRight">Custom color tokens…</Button>
              <Button variant="ghost"     size="sm" iconRight="chevRight">Export theme as JSON</Button>
              <Button variant="ghost"     size="sm" iconRight="chevRight">Import theme…</Button>
            </div>
            <div style={{ marginTop: 14, padding: "10px 12px", borderRadius: 6, background: "var(--lbb-surface2)", fontSize: 11.5, color: "var(--lbb-fg2)" }}>
              Pin <strong>status colors</strong> (green / amber / red) live on the row-status bar + pill so they never collide with your accent choice.
            </div>
          </SetupCard>

          {/* Preview */}
          <SetupCard title="Live preview" style={{ gridColumn: "span 2" }} badge={<Pill tone="mute" soft>reflects every change above</Pill>}>
            <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
              <div style={{
                padding: "10px 16px", background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
                fontSize: 12, fontWeight: 600,
                display: "flex", alignItems: "center", gap: 10,
              }}>
                <Icon name="collection" size={14} />
                Library / My Collection
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 11, opacity: 0.85 }}>preview · 4 of 15,967</span>
              </div>
              <div style={{ padding: 16, background: "var(--lbb-bg)" }}>
                <TableShell stickyHeader={false}>
                  <colgroup>
                    <col style={{ width: 3 }} /><col style={{ width: 90 }} /><col style={{ width: 90 }} />
                    <col style={{ width: 100 }} /><col />
                    <col style={{ width: 150 }} />
                  </colgroup>
                  <thead><tr><TH> </TH><TH>LB#</TH><TH>Status</TH><TH>Date</TH><TH>Location</TH><TH align="right">Action</TH></tr></thead>
                  <tbody>
                    <TR edge="ok"><TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>LB-1</TD><TD><Pill tone="ok" soft>Public</Pill></TD><TD mono>5/xx/87</TD><TD style={{ color: "var(--lbb-fg)" }}>Dead Dylan Rehearsals</TD><TD align="right"><Button size="sm" variant="primary">Primary</Button></TD></TR>
                    <TR edge="warn"><TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>LB-7</TD><TD><Pill tone="warn" soft>Missing</Pill></TD><TD mono dim>—</TD><TD dim>—</TD><TD align="right"><Button size="sm" variant="secondary">Secondary</Button></TD></TR>
                    <TR edge="bad"><TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>LB-12</TD><TD><Pill tone="bad" soft>Mismatch</Pill></TD><TD mono>11/11/80</TD><TD style={{ color: "var(--lbb-fg)" }}>Warfield, SF</TD><TD align="right"><Button size="sm" variant="ghost">Ghost</Button></TD></TR>
                    <TR edge="info"><TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>LB-18</TD><TD><Pill tone="info" soft>Public</Pill></TD><TD mono>6/29/81</TD><TD style={{ color: "var(--lbb-fg)" }}>Earl's Court, London</TD><TD align="right"><Button size="sm" variant="danger">Danger</Button></TD></TR>
                  </tbody>
                </TableShell>

                <div style={{ marginTop: 14, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Chip active count={1234}>Active chip</Chip>
                  <Chip count={88}>Filter chip</Chip>
                  <Chip count={12}>Another</Chip>
                  <Pill tone="ok"   soft>ok</Pill>
                  <Pill tone="warn" soft>warn</Pill>
                  <Pill tone="bad"  soft>bad</Pill>
                  <Pill tone="info" soft>info</Pill>
                </div>
              </div>
            </div>
          </SetupCard>
        </div>
      </div>
    );
  }

  // ─── DB Editor ─────────────────────────────────────────────────────
  function ScreenDBEditor() {
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--lbb-border)", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-warn-bg)", color: "var(--lbb-warn-fg)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--lbb-warn-bar)",
          }}><Icon name="dbeditor" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>DB Editor</h1>
              <Pill tone="warn" soft>Curator only</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>Raw table access · LB aliases · integrity counters · direct editing.</div>
          </div>
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "300px 1fr", minHeight: 0 }}>
          {/* Tables list */}
          <aside style={{ background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)", overflowY: "auto" }}>
            <div style={{ padding: "12px 14px 8px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Tables</div>
              <Input icon="search" placeholder="Filter…" size="sm" style={{ width: "100%" }} />
            </div>
            <div style={{ padding: "0 8px" }}>
              {[
                { k: "bootleg_scrapes",       n: 3 },
                { k: "bootleg_titles",        n: 1380 },
                { k: "checksums",             n: 704624 },
                { k: "collection_meta",       n: 0 },
                { k: "dylan_performances",    n: 5127, active: true },
                { k: "entries",               n: 16630 },
                { k: "entry_changes",         n: 62883 },
                { k: "entry_files",           n: 98413 },
                { k: "lb_master",             n: 16630 },
                { k: "lb_status_history",     n: 314 },
                { k: "location_geocoded",     n: 6676 },
                { k: "lbbcd_catalog",         n: 1380 },
                { k: "personal_ratings",      n: 4290 },
                { k: "torrent_history",       n: 1209 },
                { k: "watchdog_alerts",       n: 24 },
              ].map(t => (
                <button key={t.k} style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 8px", marginBottom: 1, borderRadius: 6,
                  background: t.active ? "var(--lbb-accent-soft)" : "transparent",
                  color: t.active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                  border: "1px solid transparent", textAlign: "left",
                  fontFamily: "var(--lbb-mono)", fontSize: 11.5, cursor: "pointer",
                }}>
                  <span style={{ flex: 1 }}>{t.k}</span>
                  <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{t.n.toLocaleString()}</span>
                </button>
              ))}
            </div>

            <div style={{ padding: "14px 14px 8px", marginTop: 8, borderTop: "1px solid var(--lbb-border)" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>DB integrity</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "3px 8px", fontSize: 11.5 }}>
                <span style={{ color: "var(--lbb-fg2)" }}>Public</span>      <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600 }}>15,184</span>
                <span style={{ color: "var(--lbb-fg2)" }}>Private</span>     <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600 }}>1,404</span>
                <span style={{ color: "var(--lbb-fg2)" }}>Missing</span>     <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600 }}>42</span>
                <span style={{ color: "var(--lbb-fg2)" }}>Max LB</span>      <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600 }}>16,630</span>
                <span style={{ color: "var(--lbb-fg2)" }}>Needs review</span><span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600 }}>0</span>
              </div>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                <Button size="sm" variant="secondary" block>Reconcile all</Button>
                <Button size="sm" variant="ghost" block>Backup DB now</Button>
              </div>
            </div>
          </aside>

          {/* Editor */}
          <section style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
            <div style={{ padding: "10px 20px", borderBottom: "1px solid var(--lbb-border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12.5, fontWeight: 600, color: "var(--lbb-accent-mid)" }}>dylan_performances</span>
              <span style={{ fontSize: 11.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>5,127 rows · 18 columns</span>
              <div style={{ flex: 1 }} />
              <Input size="sm" icon="search" placeholder="LB# or text…" style={{ width: 240 }} />
              <Button variant="secondary" size="sm">Load records</Button>
              <Button variant="primary"   size="sm">Run query</Button>
            </div>

            <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} /><col style={{ width: 50 }} /><col style={{ width: 100 }} />
                  <col style={{ width: 100 }} /><col style={{ width: 90 }} /><col />
                  <col style={{ width: 50 }} /><col style={{ width: 60 }} /><col />
                </colgroup>
                <thead><tr>
                  <TH> </TH><TH>rowid</TH><TH>event_id</TH>
                  <TH>date_str</TH><TH>category</TH><TH>city</TH>
                  <TH>state</TH><TH>country</TH><TH>venue</TH>
                </tr></thead>
                <tbody>
                  {[
                    [1,1946010101,"1946-00-00","HOME","Hibbing","MN","USA","The Home of Bob Dylan"],
                    [2,1956122401,"1956-12-24","HOME","St. Paul","MN","USA","?"],
                    [3,1957040501,"1957-04-05","HOME","Hibbing","MN","USA","Hibbing High School"],
                    [4,1961012401,"1961-01-24","MCONCERT","New York City","NY","USA","Cafe Wha?"],
                    [5,1961040501,"1961-04-05","MCONCERT","New York City","NY","USA","University of NY Folk Society"],
                    [6,1961041102,"1961-04-11","MCONCERT","New York City","NY","USA","Gerde's Folk City"],
                    [7,1961061101,"1961-06-11","MCONCERT","New York City","NY","USA","Gaslight Cafe"],
                    [8,1961100501,"1961-10-05","MCONCERT","New York City","NY","USA","Folklore Center"],
                    [9,1961112401,"1961-11-24","MCONCERT","New York City","NY","USA","Carnegie Chapter Hall"],
                  ].map((r,i) => (
                    <TR key={i} edge={i === 3 ? "info" : null}>
                      <TD align="center" mono dim>{r[0]}</TD>
                      <TD mono style={{ color: "var(--lbb-accent-mid)" }}>{r[1]}</TD>
                      <TD mono>{r[2]}</TD>
                      <TD><Pill tone={r[3] === "HOME" ? "mute" : "info"} soft>{r[3]}</Pill></TD>
                      <TD>{r[4]}</TD>
                      <TD mono dim>{r[5]}</TD>
                      <TD mono dim>{r[6]}</TD>
                      <TD style={{ color: "var(--lbb-fg)" }}>{r[7]}</TD>
                    </TR>
                  ))}
                </tbody>
              </TableShell>

              <div style={{ marginTop: 14, display: "flex", gap: 6, alignItems: "center" }}>
                <Button size="sm" variant="ghost">Commit changes</Button>
                <Button size="sm" variant="ghost">Discard</Button>
                <Button size="sm" variant="danger" icon="trash">Delete selected</Button>
                <Button size="sm" variant="ghost" icon="download">Export CSV…</Button>
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 11, color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)" }}>Page 1 / 52</span>
                <Button size="sm" variant="ghost" icon="chevLeft">Prev</Button>
                <Button size="sm" variant="secondary" iconRight="chevRight">Next</Button>
              </div>
            </div>
          </section>
        </div>
      </div>
    );
  }

  // ─── Scraper ──────────────────────────────────────────────────────
  function ScreenScraper() {
    return (
      <div style={{ padding: "20px 24px 32px", maxWidth: 1500, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-warn-bg)", color: "var(--lbb-warn-fg)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--lbb-warn-bar)",
          }}><Icon name="scraper" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: -0.01 }}>Scraper</h1>
              <Pill tone="warn" soft>Curator only</Pill>
            </div>
            <div style={{ fontSize: 13, color: "var(--lbb-fg3)", marginTop: 2 }}>Site mirror crawler · per-entry metadata scraper · LBBCD refresh.</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Site Crawler */}
          <SetupCard title="Site mirror crawler" badge={<Pill tone="mute" soft>Idle · 110,938 rows in site inventory</Pill>}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr) auto", gap: 12, alignItems: "center", marginBottom: 12 }}>
              <Field label="Scope">  <Button variant="secondary" size="sm" iconRight="chevDown" block>incremental</Button></Field>
              <Field label="Delay (ms)"><Input size="sm" placeholder="1500" style={{ width: "100%" }} /></Field>
              <Field label="Daily cap"><Input size="sm" placeholder="99999" style={{ width: "100%" }} /></Field>
              <Field label="Force re-fetch">
                <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, height: 30 }}>
                  <input type="checkbox" /> Yes
                </label>
              </Field>
              <div style={{ display: "flex", gap: 6 }}>
                <Button variant="ghost" size="sm" icon="pause">Stop</Button>
                <Button variant="primary" size="sm" icon="play">Start crawl</Button>
              </div>
            </div>

            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>
              Crawler session history
            </div>
            <TableShell>
              <colgroup>
                <col style={{ width: 3 }} /><col style={{ width: 140 }} /><col style={{ width: 140 }} />
                <col style={{ width: 110 }} /><col style={{ width: 110 }} /><col style={{ width: 100 }} /><col />
              </colgroup>
              <thead><tr>
                <TH> </TH><TH>Started</TH><TH>Finished</TH><TH>Scope</TH><TH>Status</TH><TH align="right">Fetched</TH><TH>Notes</TH>
              </tr></thead>
              <tbody>
                <TR edge="ok"><TD mono>2026-05-24 00:18</TD><TD mono>2026-05-24 00:18</TD><TD mono>incremental</TD><TD><Pill tone="ok" soft>Done</Pill></TD><TD align="right" mono>0</TD><TD style={{ color: "var(--lbb-fg2)" }}>No new rows.</TD></TR>
                <TR edge="ok"><TD mono>2026-05-23 15:22</TD><TD mono>2026-05-23 23:38</TD><TD mono>incremental</TD><TD><Pill tone="ok" soft>Done</Pill></TD><TD align="right" mono>18,550</TD><TD style={{ color: "var(--lbb-fg2)" }}>Caught up after maintenance window.</TD></TR>
                <TR edge="warn"><TD mono>2026-04-29 04:01</TD><TD mono>2026-04-29 08:11</TD><TD mono>full</TD><TD><Pill tone="warn" soft>Partial</Pill></TD><TD align="right" mono>110,938</TD><TD style={{ color: "var(--lbb-fg2)" }}>Rate-limited at row 92,481 · resumed.</TD></TR>
              </tbody>
            </TableShell>
          </SetupCard>

          {/* Entry Pages Scraper */}
          <SetupCard title="Entry pages &amp; metadata scraper" badge={<Pill tone="ok" soft>15,255 cached · 1,375 pending</Pill>}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr) auto", gap: 12, alignItems: "center" }}>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <input type="checkbox" defaultChecked /> Auto-scrape on import
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <input type="checkbox" defaultChecked /> Download attachments
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <input type="checkbox" /> Force re-scrape
              </label>
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                <Button variant="ghost" size="sm" icon="pause">Stop</Button>
                <Button variant="primary" size="sm" icon="play">Scrape missing (1,375)</Button>
              </div>
            </div>

            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "auto auto auto 1fr", gap: 12, alignItems: "center", fontSize: 12 }}>
              <span style={{ color: "var(--lbb-fg2)" }}>Single entry:</span>
              <Input size="sm" placeholder="LB#" style={{ width: 100 }} />
              <Button variant="secondary" size="sm">Scrape one</Button>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "var(--lbb-fg2)" }}>Range:</span>
                <Input size="sm" placeholder="1" style={{ width: 70 }} />
                <span>–</span>
                <Input size="sm" placeholder="100" style={{ width: 70 }} />
                <Button variant="secondary" size="sm">Scrape range</Button>
                <Button variant="secondary" size="sm">Re-scrape private LBs</Button>
              </span>
            </div>

            {/* Log output */}
            <div style={{ marginTop: 14, fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>
              Live log
            </div>
            <pre style={{
              margin: 0, padding: 12,
              background: "#0f0e0a", color: "#dfd9c8",
              border: "1px solid var(--lbb-border)", borderRadius: 6,
              fontFamily: "var(--lbb-mono)", fontSize: 11.5, lineHeight: 1.55,
              height: 180, overflow: "auto",
            }}>{`[2026-05-24 14:32:18] ▶ scraper: starting incremental run
[2026-05-24 14:32:18]   fetching LB-16524 ... 200 OK (2.1KB)
[2026-05-24 14:32:19]   fetching LB-16525 ... 200 OK (3.4KB)
[2026-05-24 14:32:20]   fetching LB-16526 ... 200 OK (2.9KB)
[2026-05-24 14:32:21]   fetching LB-16527 ... 200 OK (1.8KB)
[2026-05-24 14:32:23]   fetching LB-16528 ... 200 OK (2.4KB) · 4 attachments
[2026-05-24 14:32:24]   downloading LBF-16528-lbdir.txt ... 200 OK (1.1KB)
[2026-05-24 14:32:25]   downloading LBF-16528-ffp.txt   ... 200 OK (0.9KB)
[2026-05-24 14:32:26]   fetching LB-16529 ... 200 OK (3.1KB)
[2026-05-24 14:32:27] ⚠ rate-limited, sleeping 4s
[2026-05-24 14:32:31]   fetching LB-16530 ... 200 OK (2.7KB)
…`}</pre>
          </SetupCard>

          {/* LBBCD */}
          <SetupCard title="Bootleg-CD catalog (LBBCD)" badge={<Pill tone="mute" soft>collapsed</Pill>}>
            <div style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>
              <Icon name="chevRight" size={11} style={{ marginRight: 6 }} />
              Click to expand · last refreshed 2026-04-12 · 1,380 titles
            </div>
          </SetupCard>
        </div>
      </div>
    );
  }

  function Field({ label, children }) {
    return (
      <div>
        <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--lbb-fg3)", letterSpacing: 0.06, textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
        {children}
      </div>
    );
  }

  window.LBB_ScreenSetup     = ScreenSetup;
  window.LBB_ScreenThemes    = ScreenThemes;
  window.LBB_ScreenDBEditor  = ScreenDBEditor;
  window.LBB_ScreenScraper   = ScreenScraper;
})();
