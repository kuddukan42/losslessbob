// screen-home.jsx — Home / Dashboard
// Hero ingest dropzone + quick-jumps + stats + recent activity + resume card.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Card, SectionHead, Stat, Chip,
          TableShell, TH, TR, TD, Banner } = window;

  function ScreenHome({ onNav }) {
    return (
      <div style={{ padding: "24px 28px 36px", maxWidth: 1680, margin: "0 auto" }}>
        {/* Welcome strip */}
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 22, gap: 24 }}>
          <div>
            <div style={{ fontSize: 11, letterSpacing: 0.14, textTransform: "uppercase", color: "var(--lbb-fg3)", fontWeight: 600 }}>
              Welcome back, Rolling
            </div>
            <h1 style={{ margin: "6px 0 0", fontSize: 28, fontWeight: 700, letterSpacing: -0.015 }}>
              Your collection · <span style={{ fontVariantNumeric: "tabular-nums" }}>15,967</span> entries
            </h1>
            <div style={{ marginTop: 4, fontSize: 13, color: "var(--lbb-fg3)" }}>
              DB up to date · <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)" }}>LB-16630</span> · imported 4 days ago
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button icon="refresh" variant="secondary" size="md">Check for DB update</Button>
            <Button icon="drop" variant="primary" size="md" onClick={() => onNav("pipeline")}>Ingest new folders</Button>
          </div>
        </div>

        {/* Two-column primary */}
        <div style={{ display: "grid", gridTemplateColumns: "1.45fr 1fr", gap: 18, marginBottom: 18 }}>
          {/* Hero ingest */}
          <div style={{
            background: "linear-gradient(180deg, var(--lbb-accent-soft), var(--lbb-surface))",
            border: "1px solid var(--lbb-accent-mid)",
            borderRadius: 12, padding: 22, position: "relative", overflow: "hidden",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{
                fontSize: 10, letterSpacing: 0.14, textTransform: "uppercase",
                color: "var(--lbb-accent-mid)", fontWeight: 700,
                padding: "2px 7px", borderRadius: 4,
                background: "var(--lbb-surface)", border: "1px solid var(--lbb-accent-mid)",
              }}>PRIMARY WORKFLOW</span>
              <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>The new-acquisition pipeline</span>
            </div>
            <h2 style={{ margin: "2px 0 4px", fontSize: 22, fontWeight: 700, letterSpacing: -0.01 }}>
              Ingest new music
            </h2>
            <p style={{ margin: "0 0 16px", color: "var(--lbb-fg2)", fontSize: 13.5, maxWidth: 60 + "ch" }}>
              Drop folders here — the pipeline runs <strong>verify → lookup → rename → LBDIR</strong> on the whole batch.
              No more bouncing tabs.
            </p>

            {/* Dropzone */}
            <button
              onClick={() => onNav("pipeline")}
              style={{
                width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 14,
                padding: "30px 20px", borderRadius: 10,
                background: "var(--lbb-surface)",
                border: "2px dashed var(--lbb-accent-mid)",
                color: "var(--lbb-fg2)", fontSize: 13.5, cursor: "pointer", fontFamily: "inherit",
              }}>
              <Icon name="folderPlus" size={22} style={{ color: "var(--lbb-accent-mid)" }} />
              <span><strong style={{ color: "var(--lbb-fg)" }}>Drag folders here</strong> &nbsp;·&nbsp; or click to browse</span>
            </button>

            {/* Step pills */}
            <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {[
                { n: 1, label: "Verify checksums", icon: "verify" },
                { n: 2, label: "Lookup LB#",       icon: "lookup" },
                { n: 3, label: "Rename folder",    icon: "rename" },
                { n: 4, label: "Check LBDIR",      icon: "lbdir" },
              ].map(s => (
                <div key={s.n} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "9px 10px", borderRadius: 8,
                  background: "var(--lbb-surface)",
                  border: "1px solid var(--lbb-border)",
                }}>
                  <span style={{
                    width: 18, height: 18, borderRadius: "50%",
                    background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    fontSize: 10, fontWeight: 700,
                  }}>{s.n}</span>
                  <Icon name={s.icon} size={14} style={{ color: "var(--lbb-fg2)" }} />
                  <span style={{ fontSize: 11.5, fontWeight: 500, color: "var(--lbb-fg2)" }}>{s.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Stats + quick links */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Card title="At a glance" subtitle="your collection right now" pad={16}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <Stat value="15,967" label="in My Collection" delta="+12" tone="ok" />
                <Stat value="663"    label="missing entries" />
                <Stat value="3"      label="on wishlist" />
                <Stat value="1,380"  label="bootleg titles" />
              </div>
              <div style={{ marginTop: 14, padding: "10px 12px", borderRadius: 8,
                            background: "var(--lbb-surface2)",
                            border: "1px solid var(--lbb-border)",
                            display: "flex", alignItems: "center", gap: 10, fontSize: 11.5, color: "var(--lbb-fg2)" }}>
                <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />
                <span><strong style={{ color: "var(--lbb-fg)" }}>704,624</strong> checksums indexed across <strong style={{ color: "var(--lbb-fg)" }}>4</strong> mounts</span>
              </div>
            </Card>

            <Card title="Jump to" pad={14}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[
                  { id: "collection", icon: "collection",  label: "My Collection",   sub: "15,967" },
                  { id: "search",     icon: "search",      label: "Search master DB", sub: "16,630" },
                  { id: "bootlegs",   icon: "bootlegs",    label: "Bootleg catalog",  sub: "1,380" },
                  { id: "map",        icon: "map",         label: "Concert map",      sub: "6,676 pinned" },
                ].map(l => (
                  <button key={l.id} onClick={() => onNav(l.id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 10, padding: "9px 10px",
                      background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
                      borderRadius: 8, cursor: "pointer", textAlign: "left", fontFamily: "inherit",
                      color: "var(--lbb-fg)",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--lbb-surface2)"}
                    onMouseLeave={e => e.currentTarget.style.background = "var(--lbb-surface)"}
                  >
                    <span style={{
                      width: 30, height: 30, borderRadius: 7,
                      background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)",
                      display: "inline-flex", alignItems: "center", justifyContent: "center",
                    }}><Icon name={l.icon} size={15} /></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600 }}>{l.label}</div>
                      <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{l.sub}</div>
                    </div>
                    <Icon name="chevRight" size={12} style={{ color: "var(--lbb-fg3)" }} />
                  </button>
                ))}
              </div>
            </Card>
          </div>
        </div>

        {/* Recent + Resume */}
        <div style={{ display: "grid", gridTemplateColumns: "1.45fr 1fr", gap: 18 }}>
          <Card
            title="Recent activity"
            subtitle="last 7 days · imports, renames, verifies"
            action={<button style={{
              background: "transparent", border: "none", color: "var(--lbb-accent-mid)",
              fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
            }}>View full log →</button>}
            pad={0}
          >
            <TableShell stickyHeader={false}>
              <colgroup>
                <col style={{ width: 3 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 150 }} />
                <col />
                <col style={{ width: 220 }} />
              </colgroup>
              <thead>
                <tr>
                  <TH style={{ background: "var(--lbb-surface)" }}> </TH>
                  <TH>When</TH>
                  <TH>Action</TH>
                  <TH>Target</TH>
                  <TH>Result</TH>
                </tr>
              </thead>
              <tbody>
                <TR edge="ok"><TD mono>2h ago</TD><TD>Flat-file import</TD><TD style={{ color: "var(--lbb-fg)" }}>LB-16630</TD><TD><Pill tone="ok" soft dot>+2,324 added · Δ 5,831</Pill></TD></TR>
                <TR edge="ok"><TD mono>yesterday</TD><TD>Verify</TD><TD style={{ color: "var(--lbb-fg)" }}>bd2026-03-27 La Crosse WI</TD><TD><Pill tone="ok" soft>Pass · 70/70</Pill></TD></TR>
                <TR edge="ok"><TD mono>yesterday</TD><TD>Rename</TD><TD style={{ color: "var(--lbb-fg)" }}>7 folders</TD><TD><Pill tone="ok" soft>Applied</Pill></TD></TR>
                <TR edge="info"><TD mono>2 days ago</TD><TD>Add to collection</TD><TD style={{ color: "var(--lbb-fg)" }}>12 folders</TD><TD><Pill tone="info" soft>Indexed</Pill></TD></TR>
                <TR edge="warn"><TD mono>3 days ago</TD><TD>Verify</TD><TD style={{ color: "var(--lbb-fg)" }}>bd2025-07-26 Charlotte NC</TD><TD><Pill tone="warn" soft dot>Incomplete · 18/36</Pill></TD></TR>
                <TR edge="ok"><TD mono>4 days ago</TD><TD>Scrape</TD><TD style={{ color: "var(--lbb-fg)" }}>18,550 entry pages</TD><TD><Pill tone="ok" soft>Done</Pill></TD></TR>
                <TR edge="mute"><TD mono>5 days ago</TD><TD>Backup DB</TD><TD style={{ color: "var(--lbb-fg)" }}>checksum_lookup.db</TD><TD><Pill tone="mute" soft>241 MB · OK</Pill></TD></TR>
              </tbody>
            </TableShell>
          </Card>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Card title="Continue where you left off" pad={14}>
              <div style={{
                padding: "12px 14px", borderRadius: 8,
                background: "var(--lbb-warn-bg)", border: "1px solid var(--lbb-warn-bar)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <Icon name="alert" size={13} style={{ color: "var(--lbb-warn-fg)" }} />
                  <Pill tone="warn">Verify · incomplete</Pill>
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4, color: "var(--lbb-fg)" }}>
                  bd2025-07-26 Charlotte NC FLAC
                </div>
                <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>
                  18 of 36 files missing · paused 3 days ago
                </div>
                <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
                  <Button variant="primary" size="sm" icon="play" onClick={() => onNav("pipeline")}>Resume in Pipeline</Button>
                  <Button variant="ghost" size="sm">Dismiss</Button>
                </div>
              </div>
            </Card>

            <Card title="Tips" pad={14}>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <Icon name="cmd" size={14} style={{ color: "var(--lbb-fg3)", marginTop: 2 }} />
                  <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", lineHeight: 1.5 }}>
                    Press <span className="kbd-pill">⌘K</span> on any screen to jump straight to an LB# or folder.
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <Icon name="user" size={14} style={{ color: "var(--lbb-fg3)", marginTop: 2 }} />
                  <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", lineHeight: 1.5 }}>
                    Maintaining master data? Enable <strong>Curator mode</strong> in Settings to reveal DB&nbsp;Editor and Scraper.
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <Icon name="star" size={14} style={{ color: "var(--lbb-fg3)", marginTop: 2 }} />
                  <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", lineHeight: 1.5 }}>
                    Star a filter combo in <strong>Search</strong> to make it a one-click saved view.
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  window.LBB_ScreenHome = ScreenHome;
})();
