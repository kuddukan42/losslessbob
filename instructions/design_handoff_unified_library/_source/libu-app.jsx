// libu-app.jsx
// Merged Library app: ONE screen, ONE toggle. The same catalogue seen two
// ways — "By performance" (shows, families nested) and "By recording"
// (flat LB#-keyed rows). Shared chrome, shared theming. Each standalone
// HTML file renders this with a different defaultView, keeping the two
// deliverables in lockstep.

(() => {
  const AppShell = window.LBB_AppShell;
  const { LBB_TOKENS } = window;
  const { TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakSelect, TweakSlider, TweakToggle } = window;
  const Icon = window.LBB_Icon;

  const NAV = [
    { label: null, items: [{ id: "home", label: "Home", icon: "home" }] },
    {
      label: "Ingest",
      items: [
        { id: "pipeline", label: "Pipeline", icon: "pipeline" },
        { id: "verify",   label: "Verify",   icon: "verify" },
        { id: "lookup",   label: "Lookup",   icon: "lookup" },
        { id: "rename",   label: "Rename",   icon: "rename" },
        { id: "lbdir",    label: "LBDIR",    icon: "lbdir" },
      ],
    },
    {
      label: "Library",
      items: [
        { id: "library",  label: "Library",  icon: "library", count: 16630, featured: true },
        { id: "bootlegs", label: "Bootlegs", icon: "bootlegs", count: 1380 },
      ],
    },
    {
      label: "Assets",
      items: [
        { id: "attachments",  label: "Attachments",  icon: "attachments" },
        { id: "spectrograms", label: "Spectrograms", icon: "spectro" },
        { id: "map",          label: "Map",          icon: "map" },
      ],
    },
    {
      label: "Settings",
      items: [
        { id: "setup",  label: "Setup",  icon: "setup" },
        { id: "themes", label: "Themes", icon: "themes" },
      ],
    },
  ];

  // ── View toggle — the heart of "two ways of looking at the same data" ──
  function ViewToggle({ value, onChange }) {
    const OPTS = [
      { id: "performance", label: "By performance", icon: "collection" },
      { id: "recording",   label: "By recording",   icon: "library" },
    ];
    return (
      <div style={{
        display: "flex", padding: 2, borderRadius: 8, flex: "0 0 auto",
        background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
      }}>
        {OPTS.map(o => {
          const active = value === o.id;
          return (
            <button key={o.id} type="button" onClick={() => onChange(o.id)} title={`Switch to ${o.label}`} style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              height: 28, padding: "0 12px", borderRadius: 6,
              background: active ? "var(--lbb-surface)" : "transparent",
              color: active ? "var(--lbb-fg)" : "var(--lbb-fg2)",
              border: active ? "1px solid var(--lbb-border2)" : "1px solid transparent",
              boxShadow: active ? "var(--lbb-shadow)" : "none",
              fontSize: 12, fontWeight: active ? 650 : 500,
              cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
            }}>
              <Icon name={o.icon} size={14} style={{ color: active ? "var(--lbb-accent-mid)" : "currentColor" }} />
              {o.label}
            </button>
          );
        })}
      </div>
    );
  }

  function Placeholder({ onBack }) {
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "var(--lbb-fg3)" }}>
        <Icon name="info" size={22} />
        <div style={{ fontSize: 13 }}>This prototype focuses on the unified <strong style={{ color: "var(--lbb-fg2)" }}>Library</strong>.</div>
        <window.Button variant="secondary" size="sm" onClick={onBack}>Back to Library</window.Button>
      </div>
    );
  }

  function App({ defaultView }) {
    const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
      "mode":           "dark",
      "palette":        "slate",
      "accent":         "indigo",
      "density":        "default",
      "cardStyle":      "framed",
      "scopeStyle":     "segmented",
      "groupFamilies":  true,
      "showMatch":      true,
      "showLBColumn":   true,
      "autoExpandMulti": false,
      "detailWidth":    400
    }/*EDITMODE-END*/;

    const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
    const [active, setActive] = React.useState("library");
    const [viewMode, setViewMode] = React.useState(defaultView || "performance");

    React.useEffect(() => {
      LBB_TOKENS.applyTheme({ mode: t.mode, accent: t.accent, density: t.density, palette: t.palette });
    }, [t.mode, t.accent, t.density, t.palette]);

    // Framed-card separation. data-mode + data-sep both live on #frame so
    // the framed shadow recipe can adapt per mode (see app.css).
    React.useEffect(() => {
      const frame = document.getElementById("frame");
      if (!frame) return;
      frame.setAttribute("data-mode", t.mode);
      if (t.cardStyle === "framed") frame.setAttribute("data-sep", "framed");
      else frame.removeAttribute("data-sep");
    }, [t.cardStyle, t.mode]);

    const viewSwitch = <ViewToggle value={viewMode} onChange={setViewMode} />;

    const crumbs = active === "library"
      ? ["LosslessBob", "Library", viewMode === "performance" ? "By performance" : "By recording"]
      : ["LosslessBob", "…"];

    return (
      <AppShell
        nav={NAV}
        active={active}
        onNav={setActive}
        curatorMode={false}
        crumbs={crumbs}
        statusExtra={
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "var(--lbb-fg3)" }}>{viewMode === "performance" ? "Shows covered:" : "Owned:"}</span>
            <span style={{ color: "var(--lbb-fg2)", fontWeight: 600 }}>
              {viewMode === "performance" ? "5,104 / 5,988" : "15,967 / 16,630"}
            </span>
          </span>
        }
      >
        <div data-screen-label={active === "library" ? `Library (by ${viewMode})` : active} style={{ height: "100%" }}>
          {active === "library"
            ? (viewMode === "performance"
                ? <window.LBB_LibU_Performance tweaks={t} viewSwitch={viewSwitch} />
                : <window.LBB_LibU_Recording tweaks={t} viewSwitch={viewSwitch} />)
            : <Placeholder onBack={() => setActive("library")} />}
        </div>

        <TweaksPanel title="Tweaks">
          <TweakSection label="Theme" />
          <TweakRadio label="Mode" value={t.mode} options={["light", "dark"]} onChange={(v) => setTweak("mode", v)} />
          <TweakSelect label="Frame theme" value={t.palette}
            options={["slate", "blue", "purple", "green", "graphite"]}
            onChange={(v) => setTweak("palette", v)} />
          <TweakSelect label="Accent" value={t.accent}
            options={["indigo", "plum", "rust", "forest", "teal", "amber", "gray", "crimson"]}
            onChange={(v) => setTweak("accent", v)} />
          <TweakRadio label="Density" value={t.density} options={["compact", "default", "comfortable"]} onChange={(v) => setTweak("density", v)} />

          <TweakSection label="Library cards" />
          <TweakRadio label="Separation" value={t.cardStyle} options={["framed", "flush"]} onChange={(v) => setTweak("cardStyle", v)} />
          <TweakRadio label="Scope control" value={t.scopeStyle} options={["segmented", "chips"]} onChange={(v) => setTweak("scopeStyle", v)} />

          <TweakSection label="TapeMatch grouping" />
          <TweakToggle label="Group recordings into families" value={t.groupFamilies} onChange={(v) => setTweak("groupFamilies", v)} />
          <TweakToggle label="Show match confidence" value={t.showMatch} onChange={(v) => setTweak("showMatch", v)} />

          <TweakSection label="View options" />
          <TweakToggle label="Show LB# under each show" value={t.showLBColumn} onChange={(v) => setTweak("showLBColumn", v)} />
          <TweakToggle label="Auto-expand multi-source shows" value={t.autoExpandMulti} onChange={(v) => setTweak("autoExpandMulti", v)} />
          <TweakSlider label="Detail panel width" value={t.detailWidth} min={340} max={480} step={10} onChange={(v) => setTweak("detailWidth", v)} />
        </TweaksPanel>
      </AppShell>
    );
  }

  window.LBB_LibUnifiedApp = App;
})();
