// pipeline2-shell.jsx
// App shell for the refined workspace. Same chrome as the production shell, but
// the Ingest section is consolidated: Pipeline is the one workflow; the four
// old sub-tools are demoted into a collapsible "Advanced tools" disclosure to
// signal they're now folded into the Pipeline.

(() => {
  const Icon = window.LBB_Icon;
  const { TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakSelect } = window;

  const NAV = [
    { items: [{ id: "home", label: "Home", icon: "home" }] },
    { label: "Ingest", items: [{ id: "pipeline", label: "Pipeline", icon: "pipeline", featured: true }] },
    { label: "Library", items: [
      { id: "collection", label: "My Collection", icon: "collection", count: 15971 },
      { id: "trading", label: "Trading", icon: "library" },
      { id: "sharing", label: "Sharing", icon: "upload" },
      { id: "search", label: "Search", icon: "search" },
      { id: "bootlegs", label: "Bootlegs", icon: "bootlegs", count: 1380 },
    ]},
    { label: "Assets", items: [
      { id: "attachments", label: "Attachments", icon: "attachments" },
      { id: "spectrograms", label: "Spectrograms", icon: "spectro" },
      { id: "map", label: "Map", icon: "map" },
      { id: "fingerprint", label: "Fingerprint", icon: "lookup" },
    ]},
    { label: "Settings", items: [
      { id: "setup", label: "Setup", icon: "setup" },
      { id: "themes", label: "Themes", icon: "themes" },
    ]},
  ];

  const ADVANCED = [
    { id: "verify", label: "Verify", icon: "verify" },
    { id: "lookup", label: "Lookup", icon: "lookup" },
    { id: "rename", label: "Rename", icon: "rename" },
    { id: "lbdir",  label: "LBDIR",  icon: "lbdir" },
  ];

  function NavButton({ item, active, onNav, dim, collapsed }) {
    return (
      <button type="button" onClick={() => onNav(item.id)} className="lbb-nav-item" title={collapsed ? item.label : undefined} style={{
        width: "100%", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", gap: 10,
        padding: collapsed ? "9px 0" : "7px 10px", marginBottom: 1, border: "1px solid transparent", borderRadius: 6,
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : dim ? "var(--lbb-fg3)" : "var(--lbb-fg2)",
        fontSize: dim ? 12 : 12.5, fontWeight: active ? 600 : 500, textAlign: "left", cursor: "pointer", lineHeight: 1.2, fontFamily: "inherit", position: "relative",
      }}
      onMouseEnter={e => !active && (e.currentTarget.style.background = "var(--lbb-surface2)")}
      onMouseLeave={e => !active && (e.currentTarget.style.background = "transparent")}>
        <Icon name={item.icon} size={dim ? 13 : 15} />
        {!collapsed && <span style={{ flex: 1 }}>{item.label}</span>}
        {!collapsed && item.featured && !active && <span style={{ fontSize: 8.5, fontWeight: 700, padding: "0 5px", borderRadius: 3, background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)", letterSpacing: 0.06 }}>HUB</span>}
        {!collapsed && item.count !== undefined && <span style={{ fontSize: 10.5, color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", fontWeight: 500 }}>{item.count.toLocaleString()}</span>}
        {collapsed && (item.count !== undefined || item.featured) && <span style={{ position: "absolute", top: 6, right: 12, width: 5, height: 5, borderRadius: "50%", background: "var(--lbb-accent-mid)" }} />}
      </button>
    );
  }

  function Sidebar({ active, onNav, collapsed, onToggleCollapse }) {
    const [advOpen, setAdvOpen] = React.useState(false);
    return (
      <aside style={{ width: collapsed ? 64 : 224, flex: collapsed ? "0 0 64px" : "0 0 224px", background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", minHeight: 0, transition: "width 140ms ease" }}>
        <div style={{ padding: collapsed ? "16px 0 12px" : "16px 18px 14px", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", gap: 10, borderBottom: "1px solid var(--lbb-border)" }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14, letterSpacing: -0.02, boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset, 0 1px 2px rgba(0,0,0,0.12)", flex: "0 0 auto" }}>LB</div>
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: -0.01, lineHeight: 1.1 }}>LosslessBob</div>
              <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 2, letterSpacing: 0.04 }}>Checksum Lookup · v1.1.0</div>
            </div>
          )}
          {!collapsed && (
            <button onClick={onToggleCollapse} title="Collapse sidebar" style={{ width: 22, height: 22, borderRadius: 5, border: "1px solid var(--lbb-border2)", background: "var(--lbb-surface)", color: "var(--lbb-fg3)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}><Icon name="chevLeft" size={13} /></button>
          )}
        </div>
        {collapsed && (
          <button onClick={onToggleCollapse} title="Expand sidebar" style={{ margin: "8px auto 2px", width: 34, height: 26, borderRadius: 6, border: "1px solid var(--lbb-border2)", background: "var(--lbb-surface)", color: "var(--lbb-fg3)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="chevRight" size={14} /></button>
        )}
        <div style={{ flex: 1, overflowY: "auto", padding: collapsed ? "6px 8px 16px" : "10px 8px 16px" }}>
          {NAV.map((group, gi) => (
            <div key={gi} style={{ marginTop: gi === 0 ? 0 : (collapsed ? 6 : 14) }}>
              {group.label && !collapsed && <div style={{ fontSize: 10, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.12, textTransform: "uppercase", padding: "6px 10px" }}>{group.label}</div>}
              {group.label && collapsed && gi !== 0 && <div style={{ height: 1, background: "var(--lbb-border)", margin: "5px 8px 6px" }} />}
              {group.items.map(item => <NavButton key={item.id} item={item} active={item.id === active} onNav={onNav} collapsed={collapsed} />)}
              {/* Advanced tools disclosure, nested under Ingest */}
              {group.label === "Ingest" && !collapsed && (
                <div style={{ marginTop: 2 }}>
                  <button onClick={() => setAdvOpen(o => !o)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "none", border: "none", color: "var(--lbb-fg3)", fontFamily: "inherit", fontSize: 11, cursor: "pointer", letterSpacing: 0.02 }}>
                    <Icon name={advOpen ? "chevDown" : "chevRight"} size={12} />
                    <span style={{ flex: 1, textAlign: "left" }}>Advanced tools</span>
                    <span style={{ fontSize: 9, opacity: 0.8 }}>{ADVANCED.length}</span>
                  </button>
                  {advOpen && (
                    <div style={{ paddingLeft: 8 }}>
                      {ADVANCED.map(item => <NavButton key={item.id} item={item} active={item.id === active} onNav={onNav} dim />)}
                      <div style={{ padding: "4px 10px 6px 30px", fontSize: 10, color: "var(--lbb-fg3)", lineHeight: 1.4 }}>Run a single step in isolation. Everyday work happens in the Pipeline.</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
        <div style={{ padding: collapsed ? "10px 0" : "10px 12px", borderTop: "1px solid var(--lbb-border)", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", gap: 10 }}>
          <div title={collapsed ? "rolling.thunder · Local · 4 mounts" : undefined} style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "var(--lbb-fg2)", flex: "0 0 auto" }}>RW</div>
          {!collapsed && (
            <>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.1 }}>rolling.thunder</div>
                <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)" }}>Local · 4 mounts</div>
              </div>
              <Icon name="more" size={14} style={{ color: "var(--lbb-fg3)" }} />
            </>
          )}
        </div>
      </aside>
    );
  }

  function Topbar({ crumbs }) {
    return (
      <header style={{ height: 52, flex: "0 0 52px", padding: "0 20px", display: "flex", alignItems: "center", gap: 16, borderBottom: "1px solid var(--lbb-border)", background: "var(--lbb-surface)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: "var(--lbb-fg3)", fontSize: 12 }}>/</span>}
              <span style={{ fontSize: 13, fontWeight: i === crumbs.length - 1 ? 600 : 500, color: i === crumbs.length - 1 ? "var(--lbb-fg)" : "var(--lbb-fg2)" }}>{c}</span>
            </React.Fragment>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button style={{ display: "inline-flex", alignItems: "center", gap: 10, height: 32, padding: "0 10px 0 12px", background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)", borderRadius: 8, color: "var(--lbb-fg3)", fontSize: 12.5, cursor: "pointer", minWidth: 280, fontFamily: "inherit" }}>
          <Icon name="search" size={14} />
          <span style={{ flex: 1, textAlign: "left" }}>Find LB#, folder, location…</span>
          <span className="kbd-pill">⌘K</span>
        </button>
        <button style={{ width: 34, height: 34, borderRadius: 8, background: "transparent", border: "1px solid transparent", color: "var(--lbb-fg2)", cursor: "pointer", position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="bell" size={16} />
          <span style={{ position: "absolute", top: 7, right: 8, width: 7, height: 7, borderRadius: "50%", background: "var(--lbb-bad-bar)", border: "1.5px solid var(--lbb-surface)" }} />
        </button>
      </header>
    );
  }

  function StatusBar() {
    const item = (label, value, tone) => (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        {tone && <span style={{ width: 6, height: 6, borderRadius: "50%", background: `var(--lbb-${tone}-bar)` }} />}
        <span style={{ color: "var(--lbb-fg3)" }}>{label}</span>
        <span style={{ color: "var(--lbb-fg2)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</span>
      </span>
    );
    return (
      <footer style={{ height: 28, flex: "0 0 28px", padding: "0 20px", display: "flex", alignItems: "center", gap: 20, borderTop: "1px solid var(--lbb-border)", background: "var(--lbb-surface)", fontSize: 11, fontFamily: "var(--lbb-mono)" }}>
        {item("DB:", "LB-16630", "ok")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Checksums:", "704,624")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Last import:", "2026-05-21")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Bootlegs:", "1,380")}
        <div style={{ flex: 1 }} />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--lbb-fg3)" }}><Icon name="shield" size={11} /> Synced · idle</span>
      </footer>
    );
  }

  // Placeholder for the demoted advanced tools — reinforces the consolidation.
  function AdvancedPlaceholder({ id, onNav }) {
    const label = (ADVANCED.find(a => a.id === id) || {}).label || id;
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <div style={{ maxWidth: 460, textAlign: "center" }}>
          <div style={{ width: 52, height: 52, borderRadius: 12, background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}><Icon name={id} size={24} style={{ color: "var(--lbb-fg2)" }} /></div>
          <h2 style={{ margin: "0 0 8px", fontSize: 18, fontWeight: 700 }}>{label} now lives inside the Pipeline</h2>
          <p style={{ margin: "0 0 18px", fontSize: 13, color: "var(--lbb-fg2)", lineHeight: 1.55 }}>Open any folder in the Pipeline and step straight to <strong>{label}</strong> — with the same controls, in context, without losing your place. This isolated view stays for power users who want to run one step across many folders.</p>
          <button onClick={() => onNav("pipeline")} style={{ display: "inline-flex", alignItems: "center", gap: 8, height: 36, padding: "0 16px", background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>
            <Icon name="pipeline" size={15} /> Go to Pipeline
          </button>
        </div>
      </div>
    );
  }

  function Root() {
    const [t, setTweak] = useTweaks({ mode: "light", accent: "indigo", density: "default", screen: "pipeline" });
    const [navOpen, setNavOpen] = React.useState(true);
    React.useEffect(() => { window.LBB_TOKENS.applyTheme({ mode: t.mode, accent: t.accent, density: t.density }); }, [t.mode, t.accent, t.density]);
    const onNav = (id) => setTweak("screen", id);
    const isAdvanced = ADVANCED.some(a => a.id === t.screen);
    const crumbs = t.screen === "pipeline" ? ["LosslessBob", "Ingest", "Pipeline"]
      : isAdvanced ? ["LosslessBob", "Ingest", "Advanced", (ADVANCED.find(a => a.id === t.screen) || {}).label]
      : ["LosslessBob", t.screen];

    return (
      <div style={{ width: 1920, height: 1080, display: "flex", flexDirection: "column", background: "var(--lbb-bg)", color: "var(--lbb-fg)", overflow: "hidden" }}>
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <Sidebar active={t.screen} onNav={onNav} collapsed={!navOpen} onToggleCollapse={() => setNavOpen(o => !o)} />
          <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <Topbar crumbs={crumbs} />
            <div data-screen-label="Pipeline" style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
              {t.screen === "pipeline" ? <window.LBB_ScreenPipeline2 />
                : isAdvanced ? <AdvancedPlaceholder id={t.screen} onNav={onNav} />
                : <AdvancedPlaceholder id="pipeline" onNav={onNav} />}
            </div>
          </main>
        </div>
        <StatusBar />
        <TweaksPanel title="Tweaks">
          <TweakSection label="Theme" />
          <TweakRadio label="Mode" value={t.mode} options={["light", "dark"]} onChange={v => setTweak("mode", v)} />
          <TweakSelect label="Accent" value={t.accent} options={["indigo", "plum", "rust", "forest", "teal", "amber", "gray", "crimson"]} onChange={v => setTweak("accent", v)} />
          <TweakRadio label="Density" value={t.density} options={["compact", "default", "comfortable"]} onChange={v => setTweak("density", v)} />
        </TweaksPanel>
      </div>
    );
  }

  window.LBB_P2_Root = Root;
})();
